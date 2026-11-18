# -*- coding: utf-8 -*-
"""敌人：按区域难度分档、血量按地区（enemy_hp_band）、Boss 战随从不掉东西；开了敌人随机时按新位置修正（stage3）。
分档的结果（ctx.enemy_bands = {档: [敌人参数]}）以后给怪物掉落用。"""
from .common import *  # noqa: F401,F403
from .stage3 import band_hp_plain, boss_npc_tiers, boss_rule_mults, boss_tiers, enemy_positions, hostile_npcs, invader_hp_plain, invader_sp_rows, stage3_retier, vanilla_parts

NPC_LOT, NPC_SCALE, NPC_HP = 48, 88, 36
NPC_SPEFFECTS = tuple(range(76, 108, 4)) + tuple(range(376, 408, 4)) + tuple(range(488, 552, 4))
# 野兽司祭（黑剑玛利喀斯的第一形态，c2110_9000）敌人参数自带的状态效果（stateInfo 420；玛利喀斯是 15291 / 421）
CLERGY_SP = 15290


def clergy_spots(P_npc, placed, positions, vanilla_npc):
    """敌人随机时放了野兽司祭的位置 [[地图, 实体]]，给 sc/clergyfix.py 加「血量打空还没倒下就强制死亡」的保底事件。
    原版里它血量剩 55% 就变身成玛利喀斯，从来打不到 0；这个模型血量打空后不会自己倒下（原版玛利喀斯的击败事件也是先强制死亡），
    随机器的击败 / 转阶段事件却要等它「死了」才往下走，就一直卡着（玩家诊断包 2026-11-18：死亡以上的世界里艾尔登之兽的位置放了野兽司祭，
    打空血以后没有击败、没有结局，重进还要再打；用户「修一下死亡难度以上艾尔登之兽位置的boss打了没正常结算的问题」）。
    原版就是这个模型的位置不算（vanilla_npc：实体 → 原版敌人参数）：野兽司祭自己的位置有原版的变身事件，兽人祭坛的古兰格是 NPC，不能被强制杀死"""
    rows = {n for n, row in P_npc.rows.items()
            if any(struct.unpack_from('<i', row, o)[0] == CLERGY_SP for o in NPC_SPEFFECTS if o + 4 <= len(row))}
    return sorted([positions[e][0], e] for e, n in placed.items()
                  if n in rows and e in positions and vanilla_npc.get(e) is not None and vanilla_npc[e] not in rows)


def classify(ctx, P_npc, P_sp):
    """返回 (members {档: [敌人参数]}, enemy_class(nid), npc_tier(row), 随从 {敌人参数}, 随从的位置 {实体})。
    分档的敌人：随机器分类里的「普通敌人」（data\\enemy_classes.json），有区域强度效果或已知所在地图的流程等级；
    掉落表带获取标记的（一次性掉落）不算。小型动物、野生动物、Boss、NPC、甲虫不分档。
    随从：Boss 战里会被召唤 / 生成的（data\\boss_summons.json，梅瑟、伊米尔的指头、唤灵蜗牛的灵、蕾娜菈召唤的…），
    开了敌人随机时随机器会复制出同类参数（编号紧挨着、只差几个字节），一并算上"""
    data_dir, P_en, band_idx = ctx.data_dir, ctx.P_en, ctx.band_idx

    def hp_rate(sid):
        r = P_sp.rows.get(sid)
        return struct.unpack_from('<f', r, 16)[0] if r is not None else None

    # 本体区域强度 Tier01..Tier21 = 7000..7200；对应的流程等级 1..20
    anchors = [(hp_rate(7000 + 10 * k), max(1, k)) for k in range(21) if hp_rate(7000 + 10 * k)]

    def npc_tier(row):
        s = struct.unpack_from('<i', row, NPC_SCALE)[0]
        if 7000 <= s <= 7200 and s % 10 == 0:
            return max(1, (s - 7000) // 10)
        if 20007000 <= s < 20007400 and s % 10 == 0:          # DLC 区域强度（含人形 NPC 版）
            return min(33, 21 + ((s - 20007000) % 200) // 10)
        if 19351 <= s <= 19370 and anchors:                    # 本体人形 NPC 强度：按血量倍率找最近的区域
            h = hp_rate(s)
            if h is not None:
                return min(anchors, key=lambda x: abs(x[0] - h))[1]
        return None

    try:
        ec = json.load(open(os.path.join(data_dir, 'enemy_classes.json'), encoding='utf-8'))
    except Exception:
        ec = {'by_npc_param': {}, 'by_family': {}}

    def enemy_class(nid):
        return ec['by_npc_param'].get(str(nid)) or ec['by_family'].get(str(nid // 10000)) or 'other'

    def chain_en(start):
        out, r = [], start
        while r in P_en.rows:
            out.append(r)
            r += 1
        return out

    def has_flag(row):
        return erlib.lot_flag(row) or any(struct.unpack_from('<I', row, erlib.LOT_SLOTFLAG + 4 * i)[0] for i in range(8))

    try:
        _bs = json.load(open(os.path.join(data_dir, 'boss_summons.json'), encoding='utf-8'))
        summon_src = {int(k) for k in _bs['npc_params']}
        helper_ents = frozenset(int(k) for k in _bs.get('helper_entities', []))
    except Exception:
        summon_src, helper_ents = set(), frozenset()
    summon_src &= set(P_npc.rows)
    summons = set(summon_src)
    for nid in P_npc.rows:
        for s in summon_src:
            if 0 < nid - s < 100 and sum(1 for x, y in zip(P_npc.rows[nid], P_npc.rows[s]) if x != y) <= 12:
                summons.add(nid)
                break
    members, tier_of = defaultdict(list), {}
    for nid in sorted(P_npc.rows):
        if nid in summons or enemy_class(nid) != 'basic':
            continue
        row = P_npc.rows[nid]
        lot = struct.unpack_from('<i', row, NPC_LOT)[0]
        if any(has_flag(P_en.rows[r]) for r in (chain_en(lot) if lot > 0 and lot in P_en.rows else [])):
            continue                          # 一次性掉落不动
        t = npc_tier(row)
        if t is None:                         # 没有区域强度效果（如熊）：按它原本所在地图的流程等级定档
            t = ec.get('map_tier_by_npc_param', {}).get(str(nid))
        if t is None:
            continue                          # 模板行等，基本不会出现在地图上
        members[band_idx(t)].append(nid)
        tier_of[nid] = t
    return members, enemy_class, npc_tier, summons, helper_ents, ec, tier_of


def hp(ctx):
    """敌人血量按地区（enemy_hp_band）+ Boss 战随从不掉东西；开了敌人随机时（--randomizer-dir / --maps-out）按随机器日志里
    每个位置的目标强度修正血量（stage3_retier：要改的位置复制一行敌人参数、改地图里的引用）"""
    a, S, data_dir, bnd, report, bands, band_idx = ctx.a, ctx.S, ctx.data_dir, ctx.bnd, ctx.report, ctx.bands, ctx.band_idx
    P_npc = erlib.Param(bnd.get('NpcParam.param'))
    P_sp = erlib.Param(bnd.get('SpEffectParam.param'))
    if P_npc.row_size != 736:
        raise RuntimeError('NpcParam 行大小 %d 与预期不符' % P_npc.row_size)
    members, enemy_class, npc_tier, summons, helper_ents, ec, tier_of = classify(ctx, P_npc, P_sp)
    ctx.enemy_bands = members
    ctx.summon_npcs = sorted(summons)          # Boss 战的召唤物：超限锻造石掉落不算（rr/overlimit.py drop_lines）
    # 高难度血量补正（rr/hpunify.py）：改血量之前的参数血量（Boss 的肉度按原版算）+ 下面两种模式各自收集的位置
    HU = dict(mobs=[], bosses=[], final={}, inv=set())
    ctx.hpu_src = dict(U=HU, hp0={nid: struct.unpack_from('<I', row, NPC_HP)[0] for nid, row in P_npc.rows.items()})
    for nid in summons:
        struct.pack_into('<i', P_npc.rows[nid], NPC_LOT, -1)    # -1 = 不掉（0 是掉落表第 0 行，里面有东西）
    # 未鉴定物品（rr/unidentified.py 的 prepare 准备好）：分了档的敌人指向「原掉落表 + 这一档未鉴定物品」的复制表，精英按下一档
    # （最后一档的精英是第 NB 档：最后一档 + 额外的传说）；开了敌人随机时 stage3 再按实际被放到的位置换档（drop_lot）
    U = getattr(ctx, 'unid', None)
    member_band, elite, drop_lot = {}, frozenset(), None
    if U:
        top = len(bands)
        elite = frozenset(nid for lst in members.values() for nid in lst if U.is_elite(nid))
        orig = {}
        for b, lst in members.items():
            for nid in lst:
                orig[nid] = struct.unpack_from('<i', P_npc.rows[nid], NPC_LOT)[0]
                member_band[nid] = min(b + (nid in elite), top)
                struct.pack_into('<i', P_npc.rows[nid], NPC_LOT, U.lot(orig[nid], member_band[nid], nid in elite))

        def drop_lot(npc, b):
            return U.lot(orig[npc], min(b, top), npc in elite)
    st3 = []
    rand = bool(a.randomizer_dir and a.maps_out)
    hb = S.get('enemy_hp_band') or {}
    band_on = bool(hb.get('enabled', True) and (hb.get('normal') or hb.get('boss')))
    # 普通敌人按强度平滑（enemy_hp_band.curve，用户 2026-11-01）：两种模式都用，锚点强度按地区倍数（normal）的加法定
    curve = hb.get('curve') if band_on and hb.get('normal') and (hb.get('curve') or {}).get('enabled', True) else None
    rd = a.randomizer_dir or os.path.normpath(os.path.join(data_dir, '..', '..', '..', 'randomizer'))
    cache = os.path.join(os.path.dirname(data_dir), 'cache')
    if band_on and hb.get('boss') and not rand:            # 敌人随机时按位置定（stage3）
        mset = {nid for lst in members.values() for nid in lst}
        # Boss 所在位置的流程等级：Boss 分档（data/boss_lots.json，按原版地图对到敌人参数）> 自己的区域强度
        bnt = boss_npc_tiers(rd, cache, boss_tiers(rd, data_dir))
        n_boss, by_band = 0, defaultdict(int)
        for nid in sorted(P_npc.rows):
            if nid in mset or enemy_class(nid) != 'boss':
                continue
            t = bnt.get(nid)
            if t is None:
                t = npc_tier(P_npc.rows[nid])
            if t is None:
                t = ec.get('map_tier_by_npc_param', {}).get(str(nid))
            if t is None:
                continue
            b = band_idx(t)
            m = float(hb['boss'][min(b, len(hb['boss']) - 1)])
            if m == 1.0:
                continue
            row = P_npc.rows[nid]
            struct.pack_into('<I', row, NPC_HP, min(0x7FFFFFFF, int(round(struct.unpack_from('<I', row, NPC_HP)[0] * m))))
            n_boss += 1
            by_band[b] += 1
        st3.append('Boss 血量按地区：%d 个 Boss 参数 × %s（按 Boss 自己的区域强度定档：%s）' % (
            n_boss, ' / '.join('%g' % float(x) for x in hb['boss']),
            '，'.join('%s %d' % (bands[b]['name'].split('（')[0], n) for b, n in sorted(by_band.items()))))
    # Boss 位置规则（boss_rules，比如利耶尼亚除追忆外 ×0.8）：开了敌人随机时并进 boss_blend.pos_mult 按位置乘（stage3），
    # 没开时乘原版地图上这些位置放的 Boss 参数行（同一行还放在规则外的 Boss 位置的不乘，免得别处跟着变）
    rule_pm = {}
    if band_on and hb.get('boss_rules'):
        bt_all = boss_tiers(rd, data_dir)
        rb = json.load(open(os.path.join(data_dir, 'remembrance_bosses.json'), encoding='utf-8'))
        rule_pm = boss_rule_mults(hb['boss_rules'], bt_all, {int(e) for part in ('base', 'dlc') for e in rb.get(part, {})})
        if not rand:
            at = defaultdict(set)                   # 敌人参数 → 放在哪些 Boss 位置
            for plist in vanilla_parts(rd, cache).values():
                for e, n in plist:
                    if e in bt_all or e in rule_pm:
                        at[n].add(e)
            n_rule = 0
            for nid, ents in sorted(at.items()):
                ks = {rule_pm.get(e) for e in ents}
                if None in ks or len(ks) != 1 or nid not in P_npc.rows or enemy_class(nid) != 'boss':
                    continue
                k = ks.pop()
                row = P_npc.rows[nid]
                struct.pack_into('<I', row, NPC_HP, min(0x7FFFFFFF, max(1, int(round(struct.unpack_from('<I', row, NPC_HP)[0] * k)))))
                n_rule += 1
            st3.append('Boss 血量按位置规则：%s；%d 个 Boss 参数' % (
                '、'.join('%s ×%g' % (r.get('name', '?'), float(r.get('mult', 1))) for r in hb['boss_rules']), n_rule))
    # 入侵的 NPC（随机器的 HostileNPC）按 Boss 的倍数（invader_as_boss，用户 2026-11-01）；敌人随机时按位置（stage3）
    inv_mult = hb.get('boss') if band_on and hb.get('invader_as_boss', True) else None
    inv_sp = invader_sp_rows(P_sp, data_dir, inv_mult) if inv_mult else None     # 人形 NPC 的血量看生命力和效果，不看 NpcParam.hp
    if inv_mult and not rand:
        st3.append(invader_hp_plain(rd, cache, P_npc, npc_tier, ctx.map_tiers, band_idx, bands, inv_mult, inv_sp))
    if band_on and hb.get('normal') and not rand:
        st3.append(band_hp_plain(rd, cache, P_npc, P_sp, members, enemy_class, ctx.map_tiers, band_idx, bands, hb['normal'],
                                 step=int((S.get('enemy_hp_align') or {}).get('step', 10)),
                                 min_samples=int((S.get('enemy_hp_align') or {}).get('min_samples', 30)), tier_of=tier_of, curve=curve,
                                 final=HU['final']))
    if not rand:
        # 没开敌人随机：小怪按敌人参数行（各自的强度），入侵 NPC、Boss 按原版地图上的实体（Boss 的现在血量到 hpunify 里按改完的参数算）
        HU['mobs'] += [('n', nid, t) for nid, t in tier_of.items()]
        hostile = hostile_npcs(rd)
        bt_all = boss_tiers(rd, data_dir)
        for name, plist in vanilla_parts(rd, cache).items():
            for e, n in plist:
                if n not in P_npc.rows:
                    continue
                if e in hostile:
                    t = npc_tier(P_npc.rows[n])
                    t = t if t is not None else ctx.map_tiers.get(name[:-len('.msb.dcx')])
                    if t is not None:
                        HU['mobs'].append(('e', e, t))
                        HU['inv'].add(e)
                        HU.setdefault('npc', {})[e] = (n, ())
                elif e in bt_all and enemy_class(n) == 'boss':
                    HU['bosses'].append((e, n, n, band_idx(bt_all[e]), None))
    if rand:
        hp_opts = S.get('enemy_hp_align') or {}
        band_mult = hb.get('normal') if band_on else None      # 普通敌人按地区的倍数并进补正里，按实际被放到的地区算
        boss_mult = hb.get('boss') if band_on else None        # Boss 按位置直接定血量（可加可减）
        blend = dict(hb.get('boss_blend') or {})
        if rule_pm:                                 # 位置规则并进 pos_mult（同一处两边都有就相乘）
            pm = {int(e): float(k) for e, k in (blend.get('pos_mult') or {}).items()}
            for e, k in rule_pm.items():
                pm[e] = pm.get(e, 1.0) * k
            blend['pos_mult'] = {str(e): k for e, k in pm.items()}
            st3.append('Boss 血量按位置规则：%s；%d 个 Boss 位置（敌人随机时按位置乘）' % (
                '、'.join('%s ×%g' % (r.get('name', '?'), float(r.get('mult', 1))) for r in hb['boss_rules']), len(rule_pm)))
        hp_align = dict(P_sp=P_sp, cls=enemy_class, map_tiers=ctx.map_tiers, band_idx=band_idx, bands=bands, opts=hp_opts,
                        align=bool(hp_opts.get('enabled', True)), band_mult=band_mult, boss_mult=boss_mult,
                        boss_blend=blend,
                        boss_tier=boss_tiers(a.randomizer_dir, data_dir) if boss_mult else None, invader_mult=inv_mult, invader_sp=inv_sp,
                        data_dir=data_dir, P_init=erlib.Param(bnd.get('CharaInitParam.param')),
                        curve=curve, unify=HU) \
            if hp_opts.get('enabled', True) or band_mult or boss_mult or inv_mult else None
        # 修血量、随从不掉、随机器后挂的缩放效果；有未鉴定物品掉落时按位置换成那一档的复制表（member_band 为空就不换）
        st3 += stage3_retier(a.randomizer_dir, a.maps_out, P_npc, member_band, band_idx, drop_lot or 0, NPC_LOT, elite=elite,
                             helpers=helper_ents, hp_align=hp_align, P_sp=P_sp, placed=ctx.ent_npc_final)
        if hp_align and hp_align.get('avatar_maps'):
            ctx.features['avatar_maps'] = sorted(set(hp_align['avatar_maps']))    # sc/avatarfix.py 改这些图的事件
        spots = clergy_spots(P_npc, ctx.ent_npc_final, enemy_positions(a.randomizer_dir),
                             {e: n for plist in vanilla_parts(rd, cache).values() for e, n in plist})
        ctx.features['clergy_spots'] = spots                                        # sc/clergyfix.py 改这些图的事件
        if spots:
            st3.append('野兽司祭放在 %d 个位置（%s）：血量打空还没倒下就强制死亡，免得击败结算卡住' % (
                len(spots), '、'.join('%s %d' % (m, e) for m, e in spots)))
        # 随机器没写出来的地图（高难度世界里固定了的 Boss 那张图上没有别的敌人要换，例如碎星拉塔恩的大地块 m60_13_09_02）：
        # 上面是原版的 Boss，stage3 只看随机器写出来的图，看不到它们，高难度血量补正和随从就都漏了（用户 2026-11-09）。
        # 按原版地图补进去；现在血量到 rr/hpunify.py 里按参数算
        if hp_align is not None:
            mdir = os.path.join(a.randomizer_dir, 'map', 'mapstudio')
            written = set(os.listdir(mdir)) if os.path.isdir(mdir) else set()
            have = {r[0] for r in HU['bosses']}
            bt_all = boss_tiers(a.randomizer_dir, data_dir)
            extra = []
            for name, plist in vanilla_parts(rd, cache).items():
                if name in written:
                    continue
                for e, n in plist:
                    if e in bt_all and e not in have and n in P_npc.rows and enemy_class(n) == 'boss':
                        HU['bosses'].append((e, n, n, band_idx(bt_all[e]), None))
                        have.add(e)
                        extra.append('%d（%s）' % (e, name[:-len('.msb.dcx')]))
            if extra:
                st3.append('随机器没改动的地图上的 Boss 按原版算进高难度血量补正：%s' % '、'.join(extra))
    bnd.put('NpcParam.param', P_npc.serialize())
    if inv_sp or rand:                          # 入侵 NPC、人形 Boss 的血量上限效果（rr/stage3.py）
        bnd.put('SpEffectParam.param', P_sp.serialize())
    if U:
        from .unidentified import report_enemy
        report_enemy(ctx, len(member_band), len(elite))
    report.append('敌人分档：%d 个普通敌人参数分到 %d 档；Boss 战里召唤 / 生成的随从 %d 个敌人参数不掉东西' % (
        sum(len(v) for v in members.values()), len(members), len(summons)))
    report.extend(st3)


# 粪金龟（掉战灰 / 露滴的甲虫，模型 c4190 / c4191 / c4192 / c6201）的实际血量统一（scarab_hp）：
# 实际血量 = 基础血量 × 身上各特殊效果的血量倍率（主要是区域强度），所以按倍率反推基础血量
SCARAB_FAMILIES = (4190, 4191, 4192, 6201)


def scarab_hp(ctx):
    target = int(ctx.S.get('scarab_hp', 0) or 0)
    if target <= 0:
        return
    P = erlib.Param(ctx.bnd.get('NpcParam.param'))
    SP = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    n = 0
    for k, row in P.rows.items():
        if k // 10000 not in SCARAB_FAMILIES:
            continue
        rate = 1.0
        for o in NPC_SPEFFECTS:
            s = struct.unpack_from('<i', row, o)[0]
            if s > 0 and s in SP.rows:
                rate *= struct.unpack_from('<f', SP.rows[s], 16)[0] or 1.0      # maxHpRate
        struct.pack_into('<I', row, NPC_HP, max(1, int(round(target / rate))))
        n += 1
    ctx.bnd.put('NpcParam.param', P.serialize())
    ctx.report.append('粪金龟：%d 个敌人参数的实际血量统一成 %d（按区域强度倍率反推基础血量）' % (n, target))
