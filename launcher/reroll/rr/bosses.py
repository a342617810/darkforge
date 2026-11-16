# -*- coding: utf-8 -*-
"""Boss 额外的东西：龙心脏 + 星光碎片（boss_heart_shard）、保底锻造石（boss_smithing_stone），只给一次；融锻之心改由 dark_core 看击败标记发
（fusion_lines，用户 2026-11-04）；
掉落里不再有原版装备（no_vanilla_gear_drops）。"""
from .common import *  # noqa: F401,F403
from . import inherit


GIFTS = ((1, 10060), (1, 1290))          # 龙心脏、星光碎片（道具）


def gift_list(ctx):
    """这次 Boss 多给的道具（每样数量一样）：龙心脏、星光碎片。融锻之心以前也在这里（数量同龙心脏），2026-11-04 改成 fusion_lines：
    平时只有追忆 Boss 给、按难度递增，「死亡」「不可能」里所有 Boss 照龙心脏的数量给——掉落表管不了难度，交给 DLL"""
    return GIFTS


FUSION = 'fusion_drop.json'


def fusion_lines(ctx):
    """dll\\dark_core\\fusion.txt（格式见 dark_core 的 fusion.rs；用户 2026-11-04「追忆boss按照难度从5个开始 依次+5掉落 其余boss不掉落
    融锻之心 然后进入死亡难度以上才是按照现在的boss掉落」）：dark_core 看每场 Boss 战的击败标记从灭变亮发融锻之心——
    平时只有追忆 Boss 战给，按难度第 k 名给 step × k 个、最多 max 个（用户 2026-11-04 改成 3、6、9、12 封顶；data\\fusion_drop.json 的 rank，dev\\item_system\\build_fusion_flags.py 排的）；
    「死亡」「不可能」（lock 档的当前档标记亮着）里所有 Boss 战都给，数量照龙心脏（heart_shard 的算法：地区档 + 追忆多给）。
    每场平时、死亡以上各只给一次（normal / death 标记）。没开装备工坊、关了 fusion_drop 就不给融锻之心（goods 0）。
    许愿石（rr/wishstone.py，用户 2026-11-04）也在这里：死亡以上每场 Boss 战给 boss 个、追忆 Boss 战给 remembrance 个（wish 行、boss 行第 4 个数），
    和融锻之心一起发、共用 death 标记。
    高难度 Boss 卢恩保底（settings 的 hard_runes.boss，用户 2026-11-04「20w起步」）：runefloor 行 + boss 行第 5 个数 = 这场死亡以上的击败奖励
    （GameAreaParam 里 defeatBossFlagId 是这场击败标记的那行的 bonusSoul_single，几行取最大，按 rr/hpunify.py 的压缩曲线换算（dark_core
    hpunify 模块进这几档时改参数），≥ 保底所以 fusion 不补；没有区域奖励的 0），死亡以上第一次打过时 dark_core 补到 floor。
    三样都没有就没有这个文件"""
    from .hpunify import flags as lock_flags
    from . import wishstone
    c = ctx.S.get('fusion_drop') or {}
    fusion = c.get('enabled', True) and inherit.enabled(ctx)
    ws = getattr(ctx, 'wishstone', None)
    from .hpunify import rune_cfg, boss_curve
    rc = rune_cfg(ctx.S)
    floor = int(rc['floor']) if rc else 0
    if not fusion and not ws and floor <= 0:
        return []
    award = {}                                          # 击败标记 → 原版的击败奖励（卢恩）
    if floor > 0:
        GL = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'GameAreaParam.xml')))[0]}
        G = erlib.Param(ctx.bnd.get('GameAreaParam.param'))
        gv = lambda row, f: struct.unpack_from('<' + GL[f][1], row, GL[f][2])[0]
        for row in G.rows.values():
            k = gv(row, 'defeatBossFlagId')
            award[k] = max(award.get(k, 0), gv(row, 'bonusSoul_single'))
    fights = json.load(open(os.path.join(ctx.data_dir, FUSION), encoding='utf-8'))['fights']
    hc = ctx.S.get('boss_heart_shard_count') or {}
    step, top = int(c.get('step', 3)), int(c.get('max', 12))   # 用户 2026-11-04：3、6、9、12，之后都是 12
    out = ['goods %d' % (inherit.GOODS if fusion else 0), 'lock ' + ' '.join(map(str, lock_flags(ctx.S)))]
    if ws:
        out.append('wish %d' % wishstone.GOODS)
    if floor > 0:
        out.append('runefloor %d' % floor)
    for k, v in sorted(fights.items(), key=lambda kv: int(kv[0])):
        if fusion and v['rank'] and v['normal']:
            out.append('rem %s %d %d' % (k, min(step * v['rank'], top) if top > 0 else step * v['rank'], v['normal']))
        n = int(hc.get('base', 1)) + int(hc.get('per_band', 1)) * ctx.band_idx(v['tier']) + (int(hc.get('remembrance', 2)) if v['rank'] else 0)
        w = (ws['remembrance'] if v['rank'] else ws['boss']) if ws else 0
        a = award.get(int(k), 0)
        out.append('boss %s %d %d %d %d' % (k, max(1, min(99, n)) if fusion else 0, v['death'], w, boss_curve(rc)(a) if rc and a > 0 else a))
    return out


from . import bossaward  # noqa: E402


def gift_row(size, cat, gid, flag, template=None, num=1):
    """必掉 num 个道具的一行（权重 1000），带获取标记：拿过就不再给。"""
    row = bytearray(template) if template is not None else bytearray(size)
    if template is None:
        row[137] = 0xFF
        row[148] = 0xFF
    for i in range(8):
        erlib.lot_clear_slot(row, i)
    erlib.lot_set_slot(row, 0, cat, gid, 1000, num=num, luck=False, slotflag=0)
    struct.pack_into('<I', row, erlib.LOT_FLAG, flag)
    return row


def reuse_flag(ctx, P_mp, r, flag):
    """往奖励链里放东西时第 r 行用的获取标记。占用原版就有的空行时保留它自己的标记：不是 0、和链开头不一样的空行是专门点亮标记的
    （蕾娜菈奖励链的 10182 什么都不给、只点亮 177，公共事件 730 数 170~179 亮了几个，无缘诞生者的大卢恩靠它算进大卢恩数量，
    王城大门、Enia 的护符皮带看这个数；以前被我们占掉改成链开头的 197，用户 2026-11-01 报王城进不去、拿不到护符皮带）。
    这种记进 features 的 flag_repair（链开头标记亮了就补点它，sc/start.py 读档时补，修以前被占掉的存档）"""
    own = erlib.lot_flag(P_mp.rows[r]) if r in P_mp.rows else 0
    if own and own != flag:
        rep = ctx.features.setdefault('flag_repair', [])
        if [flag, own] not in rep:
            rep.append([flag, own])
        return own
    return flag


def boss_npcs(ctx, sd):
    """Boss 位置（entity）→ 实际放的敌人参数：开了敌人随机用重随修补后的地图里那个位置引用的（stage3 按位置修正血量 / 档次时
    会复制一行参数、地图改成指向复制品，改随机器原来那行游戏里不生效），否则用 data\\boss_selfdrop.json 里原版的"""
    if not ctx.a.randomizer_dir:
        return {int(e): v['npc'] for e, v in sd.items()}
    if getattr(ctx, 'ent_npc_final', None):
        return ctx.ent_npc_final
    out = {}
    try:
        parts = json.load(open(os.path.join(ctx.a.maps_out, 'stage3_parts.json'), encoding='utf-8'))['parts']
        for plist in parts.values():
            for e, n, _off in plist:
                out.setdefault(e, n)
    except Exception:
        return {}
    return out


def self_drop(P_npc, P_en, npc, new_rows, nid):
    """敌人参数 npc 的掉落改成：new_rows 几行 + 原来的整条掉落表，新表从 nid 起找空号（100 一档），返回下一个可用的 nid"""
    old = struct.unpack_from('<i', P_npc.rows[npc], 48)[0]
    old_rows = []
    r = old
    while old > 0 and r in P_en.rows:
        old_rows.append(bytearray(P_en.rows[r]))
        r += 1
    rows = list(new_rows) + old_rows
    while any((nid + k) in P_en.rows for k in range(len(rows) + 1)):
        nid += 100
    for k, row in enumerate(rows):
        P_en.add_row(nid + k, row)
    struct.pack_into('<i', P_npc.rows[npc], 48, nid)
    return nid + max(100, len(rows) + 1)


def heart_shard(ctx, bosses):
    """每个 Boss 多给龙心脏和星光碎片（boss_heart_shard），只给一次。数量（各，boss_heart_shard_count，用户 2026-10-29）：
    base + per_band × Boss 所在地区档的序号（tier_bands：前期 0 … DLC 后期 5），追忆 Boss（data\\remembrance_bosses.json）再加 remembrance；
    默认 前期 1 个、每往后一档多 1 个（DLC 后期 6 个），追忆 Boss 多 2 个。
    每样一行（一行只出一件）。
    先放进击杀奖励表：清掉 RNG 装备后空出来的行，或者接在表（含追加的传说）后面（后面要留一个空号）；
    放不下的改由事件发放（rr/bossaward.py：击败标记亮起时发，每样一行，带 data\\boss_selfdrop.json 里的获取标记）。
    击杀不发奖励的小 Boss（data\\boss_extra.json：求学洞窟的葛瑞克士兵、南瓜头、王室幽魂……，不在 boss_lots.json 里）：接在它自己的
    掉落表（unidentified.boss_extra_drops 建的「传说 + 原来的掉落」）后面，获取标记从 flags 的末尾取没用过的
    （开头的留给随后接上的保底锻造石，和以前一样）。以前漏了，用户 2026-10-29 报求学洞窟 Boss 没给"""
    S, bnd, P_mp, P_en, chain = ctx.S, ctx.bnd, ctx.P_mp, ctx.P_en, ctx.chain
    if not S.get('boss_heart_shard', True):
        return
    hc = S.get('boss_heart_shard_count') or {}
    try:
        rb = json.load(open(os.path.join(ctx.data_dir, 'remembrance_bosses.json'), encoding='utf-8'))
        rem = {int(e) for part in ('base', 'dlc') for e in rb.get(part, {})}
    except Exception:
        rem = set()
    total = Counter()

    def cnt(b):
        """这个 Boss 给几个（龙心脏、星光碎片各），顺便记总数"""
        n = int(hc.get('base', 1)) + int(hc.get('per_band', 1)) * ctx.band_idx(b['tier']) + (int(hc.get('remembrance', 2)) if b['entity'] in rem else 0)
        n = max(1, min(99, n))
        total['n'] += n
        total['rem'] += b['entity'] in rem
        return n
    gifts = gift_list(ctx)
    try:
        sd = json.load(open(os.path.join(ctx.data_dir, 'boss_selfdrop.json'), encoding='utf-8'))['bosses']
    except Exception:
        sd = {}
    in_table = 0
    need_self = []
    done = set()
    for b in bosses:
        placed = False
        for lot in b['lots']:
            rows = chain(lot)
            if not rows:
                continue
            if rows[-1] in done:                   # 几个 Boss 共用一张奖励表：给过了
                placed = True
                break
            first = P_mp.rows[rows[0]]
            flag = erlib.lot_flag(first)
            if flag == 0:
                continue
            slots = [r for r in rows if not any(iid for _, c, iid, _ in erlib.lot_slots(P_mp.rows[r]))][:len(gifts)]
            end, k = rows[-1], 1
            while len(slots) < len(gifts) and (end + k) not in P_mp.rows and (end + k + 1) not in P_mp.rows:
                slots.append(end + k)
                k += 1
            if len(slots) < len(gifts):
                continue
            n = cnt(b)
            for r, (cat, gid) in zip(slots, gifts):
                row = gift_row(len(first), cat, gid, reuse_flag(ctx, P_mp, r, flag), template=first, num=n)
                if r in P_mp.rows:
                    P_mp.rows[r][:] = row
                else:
                    P_mp.add_row(r, row)
            done.add(chain(lot)[-1])
            in_table += 1
            placed = True
            break
        if not placed:
            need_self.append(b)
    # 放不下的：Boss 自身掉落
    ent_npc = boss_npcs(ctx, sd)
    P_npc = erlib.Param(bnd.get('NpcParam.param'))
    self_n, fail, redirected = 0, [], {}
    nid = 1908100000
    for b in need_self:
        info = sd.get(str(b['entity']))
        npc = ent_npc.get(b['entity'])
        flags = info['flags'][:len(gifts)] if info else []
        if info and len(flags) >= len(gifts) and bossaward.has_flag(ctx, b['entity']):
            n = cnt(b)
            bossaward.add(ctx, b['entity'], [gift_row(152, cat, gid, f, num=n) for (cat, gid), f in zip(gifts, flags)])
            self_n += 1
            continue
        if not info or npc is None or npc not in P_npc.rows or len(flags) < len(gifts):
            fail.append(b['name'])
            continue
        if npc in redirected:                      # 和别的 Boss 共用敌人参数：那张表已经有了（标记按先到的）
            fail.append(b['name'] + '（和' + redirected[npc] + '共用敌人参数）')
            continue
        n = cnt(b)
        nid = self_drop(P_npc, P_en, npc, [gift_row(152, cat, gid, f, num=n) for (cat, gid), f in zip(gifts, flags)], nid)
        redirected[npc] = b['name']
        self_n += 1
    if self_n:
        bnd.put('NpcParam.param', P_npc.serialize())
    # 击杀不发奖励的小 Boss：接在自己的掉落表后面（后面要留一个空号）
    extra_n = 0
    try:
        bx = json.load(open(os.path.join(ctx.data_dir, 'boss_extra.json'), encoding='utf-8'))['bosses']
    except Exception:
        bx = []
    for b in bx:
        if bossaward.extra_by_event(ctx, b):       # 事件发放：获取标记从末尾取没用过的（开头的留给保底锻造石）
            used = {erlib.lot_flag(x) for x in bossaward.rows_of(ctx, b['entity'])}
            flags = [f for f in reversed(b['flags']) if f not in used]
            if len(flags) < len(gifts):
                fail.append(b['name'])
                continue
            n = cnt(b)
            bossaward.add(ctx, b['entity'], [gift_row(152, cat, gid, f, num=n) for (cat, gid), f in zip(gifts, flags)], flag=b['entity'])
            extra_n += 1
            continue
        rows, r = [], b['lot']
        while r in P_en.rows:
            rows.append(r)
            r += 1
        if not rows:                               # 没建掉落表（这一档不给传说、地图上没找到这个位置）
            fail.append(b['name'] + '（没有自身掉落表）')
            continue
        used = {erlib.lot_flag(P_en.rows[x]) for x in rows}
        flags = [f for f in reversed(b['flags']) if f not in used]
        end = rows[-1]
        if len(flags) < len(gifts) or any((end + k) in P_en.rows for k in range(1, len(gifts) + 2)):
            fail.append(b['name'])
            continue
        n = cnt(b)
        for k, ((cat, gid), f) in enumerate(zip(gifts, flags)):
            P_en.add_row(end + 1 + k, gift_row(152, cat, gid, f, num=n))
        extra_n += 1
    ctx.report.append('Boss 龙心脏 + 星光碎片（只给一次，按地区 %d 起每档 +%d、追忆 Boss +%d，共各 %d 个，其中追忆 Boss %d 个）：'
                      '%d 个 Boss 放进击杀奖励表，%d 个改由事件发放，%d 个击杀不发奖励的 Boss（事件发放，个别照旧自身掉落）%s' % (
                          int(hc.get('base', 1)), int(hc.get('per_band', 1)), int(hc.get('remembrance', 2)), total['n'], total['rem'],
                          in_table, self_n, extra_n, '；%d 个没加上：%s' % (len(fail), '、'.join(fail)) if fail else ''))


# 删原版装备时照旧的：大蛇狩猎矛（打拉卡德要用）
KEEP_GEAR = {17030000}


def own_gear(cat, iid):
    """我们自己的装备编号段（容器、开局装备、护符模板、自制护符），删原版装备时不碰"""
    return (cat == CAT_W and iid >= 100000000) or (cat == CAT_P and 29000000 <= iid < 31000000) \
        or (cat == CAT_A and (9000 <= iid < 10000 or 20000 <= iid < 30000 or 4140 <= iid <= 4144))   # 4141~4144：词条疫病的模板（以前的固定护符，编号锁定）


def no_weapons(ctx):
    """掉落里不再有原版装备（no_vanilla_gear_drops）：所有地图掉落表、敌人掉落表里的原版武器 / 防具 / 护符格
    改成「什么都不掉」（点数照旧，同一行别的东西几率不变）；箭矢、大蛇狩猎矛（KEEP_GEAR）照旧，我们自己的装备不碰。
    用户 2026-10-29「Boss 掉落的原版武器也都删除了」、2026-10-30「移除入侵 npc 掉落的原版武器」「全部删掉」「原版装备呢」：
    从 Boss、入侵者扩到所有来源、所有装备类别。宝箱、支线奖励里的原版装备之前已经换成未鉴定物品（unidentified.no_vanilla_gear），
    这里只剩地上 / 尸体光点、事件奖励（精英敌人、特殊敌人、商队宝箱……）、Boss、人形 NPC、普通敌人的掉落。
    敌人掉落表就地改（反正所有敌人都不掉了，不用像以前那样给 Boss 复制一份）。
    要在所有往掉落表加东西的步骤（未鉴定物品、龙心脏、锻造石）之后"""
    if not ctx.S.get('no_vanilla_gear_drops', True):
        return
    from .unidentified import ammo_ids, CAT_CW, KEEP_GEAR, weapon_of
    ammo = ammo_ids(ctx)
    P_mp, P_en, chain = ctx.P_mp, ctx.P_en, ctx.chain

    def strip(row):
        """这一行的原版装备格改成空格（编号、类别 0，点数照旧），返回改了的 [类别]"""
        out = []
        for i, cat, iid, _pt in erlib.lot_slots(row):
            if cat == CAT_CW and weapon_of(cat, iid) is not None and weapon_of(cat, iid) not in KEEP_GEAR:
                pass                     # 第 6 类定制武器（长牙等）：原版武器，照样删
            elif cat not in (CAT_W, CAT_P, CAT_A) or iid <= 0 or own_gear(cat, iid):
                continue
            if cat == CAT_W and (iid in ammo or iid - iid % 10000 in KEEP_GEAR):
                continue
            struct.pack_into('<i', row, erlib.LOT_ID + 4 * i, 0)
            struct.pack_into('<i', row, erlib.LOT_CAT + 4 * i, 0)
            out.append(cat)
        return out
    try:
        bosses = json.load(open(os.path.join(ctx.data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses']
    except Exception:
        bosses = []
    try:
        nl = json.load(open(os.path.join(ctx.data_dir, 'npc_lots.json'), encoding='utf-8'))['lots']
    except Exception:
        nl = {}
    boss_rows = {r for b in bosses for lot in b['lots'] for r in chain(lot)}
    npc_rows = {r for lot in nl for r in chain(int(lot))}
    n = Counter()
    for r, row in P_mp.rows.items():
        src = 'Boss 奖励' if r in boss_rows else '人形 NPC' if r in npc_rows else '地图'
        for cat in strip(row):
            n[(src, cat)] += 1
    for row in P_en.rows.values():
        for cat in strip(row):
            n[('敌人', cat)] += 1
    zh = {CAT_W: '武器', CAT_P: '防具', CAT_A: '护符'}
    parts = ['%s %s' % (s, ' / '.join('%s %d' % (zh[c], n[(s, c)]) for c in zh if n[(s, c)]))
             for s in ('Boss 奖励', '人形 NPC', '地图', '敌人') if any(n[(s, c)] for c in zh)]
    ctx.report.append('掉落里的原版装备删掉（改成什么都不掉，箭矢、大蛇狩猎矛照旧）：%d 格：%s' % (sum(n.values()), '；'.join(parts)))


STONE_KINDS = (set(range(10100, 10108)) | {10140}, set(range(10160, 10169)) | {10200})   # 锻造石（含古龙岩）、失色锻造石（失色 9 = 10200，失色古龙岩 = 10168）


def stone_row(size, ids, num, flag, template=None):
    """必掉一块锻造石的一行：ids 等权（权重合计 1000），带获取标记"""
    row = bytearray(template) if template is not None else bytearray(size)
    if template is None:
        row[137] = 0xFF
        row[148] = 0xFF
    for i in range(8):
        erlib.lot_clear_slot(row, i)
    for j, iid in enumerate(ids[:8]):
        w = 1000 // len(ids[:8]) + (1 if j < 1000 % len(ids[:8]) else 0)
        erlib.lot_set_slot(row, j, 1, iid, w, num=num, luck=False, slotflag=0)
    struct.pack_into('<I', row, erlib.LOT_FLAG, flag)
    return row


def smithing_stones(ctx):
    """Boss 保底锻造石（boss_smithing_stone）：击杀奖励表后面接两行，普通锻造石、失色锻造石各必掉一块（数量 normal / somber），
    等级从 Boss 所在档的怪物掉落池里同种的等级等权抽；沿用奖励表的获取标记，只给一次。
    放进奖励表的方法和龙心脏一样（先用表里的空行，再接在表后面、后面留一个空号）。
    奖励表放不下的（表后面没有空号、表没有获取标记）改由事件发放（rr/bossaward.py），
    获取标记用 data\\boss_stone_flags.json 里每个 Boss 位置固定的两个（93100 起）；和别的 Boss 共用敌人参数的只能给先到的那个。
    击杀不发奖励的 Boss（data\\boss_extra.json）接在它自己的掉落表后面，用还没用过的获取标记。
    放在所有往地图掉落表加固定编号的步骤（开局召魂铃、说明书）之后，不占它们的编号。"""
    S, P_mp, P_en, chain = ctx.S, ctx.P_mp, ctx.P_en, ctx.chain
    cfg = S.get('boss_smithing_stone') or {}
    if not cfg.get('enabled'):
        return
    nums = (int(cfg.get('normal', 1)), int(cfg.get('somber', 1)))
    pools = sorted((S.get('smithing_stone_drop') or {}).get('pools') or [], key=lambda p: p['max_tier'])
    if not pools:
        return

    def kinds(tier):
        mt = ctx.band_for(tier).get('max_tier', 99)
        pool = next((p['items'] for p in pools if mt <= p['max_tier']), pools[-1]['items'])
        return [(sorted(i for i in pool if i in ks), n) for ks, n in zip(STONE_KINDS, nums) if n > 0]
    try:
        bosses = json.load(open(os.path.join(ctx.data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses']
    except Exception:
        bosses = []
    done = set()
    for b in bosses:
        want = [k for k in kinds(b['tier']) if k[0]]
        if not want:
            continue
        for lot in b['lots']:
            rows = chain(lot)
            if not rows:
                continue
            if rows[-1] in done:                   # 几个 Boss 共用一张奖励表：给过了
                break
            first = P_mp.rows[rows[0]]
            flag = erlib.lot_flag(first)
            if flag == 0:
                continue
            slots = [r for r in rows if not any(iid for _, c, iid, _ in erlib.lot_slots(P_mp.rows[r]))][:len(want)]
            end, k = rows[-1], 1
            while len(slots) < len(want) and (end + k) not in P_mp.rows and (end + k + 1) not in P_mp.rows:
                slots.append(end + k)
                k += 1
            if len(slots) < len(want):
                continue
            for r, (ids, n) in zip(slots, want):
                row = stone_row(len(first), ids, n, reuse_flag(ctx, P_mp, r, flag), template=first)
                if r in P_mp.rows:
                    P_mp.rows[r][:] = row
                else:
                    P_mp.add_row(r, row)
            done.add(chain(lot)[-1])
            break
    # 放完再数没加上的：和后面的 Boss 共用奖励链（链尾已经接上锻造石）的不算
    has = [b for b in bosses if any(ids for ids, _ in kinds(b['tier']))]
    missing = [b for b in has if not any(chain(lot) and chain(lot)[-1] in done for lot in b['lots'])]
    in_table = len(has) - len(missing)
    # 奖励表放不下的：Boss 自身掉落
    fail, self_n = [], 0
    try:
        sd = json.load(open(os.path.join(ctx.data_dir, 'boss_selfdrop.json'), encoding='utf-8'))['bosses']
        sf = json.load(open(os.path.join(ctx.data_dir, 'boss_stone_flags.json'), encoding='utf-8'))['bosses']
    except Exception:
        sd, sf = {}, {}
    ent_npc = boss_npcs(ctx, sd) if missing else {}
    P_npc = erlib.Param(ctx.bnd.get('NpcParam.param')) if missing else None
    redirected, nid = {}, 1908200000
    for b in missing:
        want = [k for k in kinds(b['tier']) if k[0]]
        npc = ent_npc.get(b['entity'])
        flags = (sf.get(str(b['entity'])) or {}).get('flags') or []
        if len(flags) >= len(want) and bossaward.has_flag(ctx, b['entity']):
            bossaward.add(ctx, b['entity'], [stone_row(152, ids, n, f) for (ids, n), f in zip(want, flags)])
            self_n += 1
            continue
        if npc is None or npc not in P_npc.rows or len(flags) < len(want):
            fail.append(b['name'])
            continue
        if npc in redirected:                      # 和别的 Boss 共用敌人参数：那张表已经有了（标记按先到的）
            fail.append('%s（和%s共用敌人参数）' % (b['name'], redirected[npc]))
            continue
        nid = self_drop(P_npc, P_en, npc, [stone_row(152, ids, n, f) for (ids, n), f in zip(want, flags)], nid)
        redirected[npc] = b['name']
        self_n += 1
    if self_n:
        ctx.bnd.put('NpcParam.param', P_npc.serialize())
    # 击杀不发奖励的 Boss：自己的掉落表（传说 + 龙心脏、星光碎片）后面接上，用没用过的获取标记
    extra_n = 0
    try:
        bx = json.load(open(os.path.join(ctx.data_dir, 'boss_extra.json'), encoding='utf-8'))['bosses']
    except Exception:
        bx = []
    for b in bx:
        want = [k for k in kinds(b['tier']) if k[0]]
        if want and bossaward.extra_by_event(ctx, b):   # 事件发放：用还没用过的获取标记
            used = {erlib.lot_flag(x) for x in bossaward.rows_of(ctx, b['entity'])}
            flags = [f for f in b['flags'] if f not in used]
            if len(flags) < len(want):
                fail.append(b['name'])
                continue
            bossaward.add(ctx, b['entity'], [stone_row(152, ids, n, f) for (ids, n), f in zip(want, flags)], flag=b['entity'])
            extra_n += 1
            continue
        rows, r = [], b['lot']
        while r in P_en.rows:
            rows.append(r)
            r += 1
        if not want or not rows:                   # 没挂上掉落表的（敌人随机的地图里没找到这个位置等）不加
            continue
        used = {erlib.lot_flag(P_en.rows[x]) for x in rows}
        flags = [f for f in b['flags'] if f not in used]
        end = rows[-1]
        if len(flags) < len(want) or any((end + k) in P_en.rows for k in range(1, len(want) + 2)):
            fail.append(b['name'])
            continue
        for k, ((ids, n), f) in enumerate(zip(want, flags)):
            P_en.add_row(end + 1 + k, stone_row(152, ids, n, f))
        extra_n += 1
    ctx.report.append('Boss 保底锻造石（普通 %d 块 + 失色 %d 块，按 Boss 所在地区的等级，只给一次）：%d 个 Boss 放进击杀奖励表，'
                      '%d 个奖励表放不下的改由事件发放，%d 个击杀不发奖励的 Boss（事件发放，个别照旧自身掉落）%s' % (
                          nums[0], nums[1], in_table, self_n, extra_n, '；%d 个没加上：%s' % (len(fail), '、'.join(fail)) if fail else ''))


def gifts(ctx):
    """每个 Boss（data\boss_lots.json）多给龙心脏和星光碎片（按地区递增、追忆 Boss 多给，见 heart_shard）"""
    try:
        bosses = json.load(open(os.path.join(ctx.data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses']
    except Exception:
        bosses = []
    heart_shard(ctx, bosses)
