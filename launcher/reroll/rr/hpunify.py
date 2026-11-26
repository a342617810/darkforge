# -*- coding: utf-8 -*-
"""高难度血量补正（hp_unify，用户 2026-11-03；设计稿 dev\\item_system\\超限锻造石与高难度.md §3）。

「死亡」「不可能」（settings 的 difficulty 里标了 lock 的档）里，小怪血量统一拉到毕业水平、Boss 统一难度。难度在游戏里随时能切，
所以不改参数：由 dll\\dark_core 的 hpunify 模块在这几档里给在场的敌人挂「最大血量倍率」效果。这里按位置算倍率 k：
- 小怪（enemies.hp / stage3 收集的位置和强度）：k = 目标 ÷ 它所在强度加完血以后的中位数（enemy_hp_band.curve）。
  目标：本体 = 强度 mob_goal_tier（19，圣树）的中位数，DLC = DLC 最后一级的中位数（用户定：本体、DLC 分开）。
  只拉高不压低（已经高过目标的强度不挂）。入侵的 NPC 跟着所在强度的小怪乘，和小怪的比例不变。
- Boss（肉度法）：目标 = 目标档 Boss 中位数 × 那一档的 Boss 倍数（boss_goal_band：本体 3 = 法姆 / 雪原 / 圣树，DLC 5 = DLC 后期）
  × 肉度。肉度 = 放进来的 Boss 的原版血量 ÷ 原版里它所在那一档 Boss 位置血量的中位数，夹在 boss_blend 的 min~max
  （同 stage3.boss_targets；放进来的原版不在 Boss 位置时用这个位置原版 Boss 的肉度）；boss_blend.neutral_entities（拉卡德）按 1。
  本体 / DLC 按位置所在的档（dlc_band_from 起算 DLC）。k = 目标 ÷ 现在的实际血量，可升可降（小 Boss 也一样，不打折）。
  DLC 位置的 Boss 目标再 × dlc_boss_mult（settings 1.5，用户 2026-11-24；斗技场 rr/arena.py 用 hpu_calc 的 goal_b，不乘）。
  skip_entities（神皮二人组：原版三个实体共用一条血条，怎么共享的没查清）不动。
- 效果行：maxHpRate = step^i（i 覆盖 k_min~k_max），编号 sp_base 起。每个位置挂最接近的一档；差不到半档（k ≈ 1）的不挂。
- 攻击力（atk，用户 2026-11-03：前期小怪根本打不动人）：原版敌人的攻击力主要靠区域强度效果放大（本体 7000 + 10 × 档、
  DLC 20007000 + 10 × (档 − 21)，physicsAttackPowerRate 等五种：本体 1 档 ×1.10 … 19 档 ×3.80，DLC 各档 ×3.75~3.85），
  所以每个位置 × 目标档的攻击倍率 ÷ 它所在档的（本体目标 mob_goal_tier，DLC 目标 DLC 最后一档；只拉高）。
  小怪、入侵 NPC 按位置的强度档；Boss 按 Boss 位置的流程等级（data\boss_lots.json，同 stage3.boss_tiers）。
  效果行：五种攻击力倍率 = step^j（j 覆盖 1~atk_k_max），编号 atk_sp_base 起；hpunify.txt 的 arange / ae 实体 / an 敌人参数。
- 卢恩（runes，用户 2026-11-04「补正一下高难度下boss的卢恩获取 20w起步」「直接20w不好看找一个算法补偿一下 下限20w就好了」
  「小怪的卢恩掉落也用这个算法补偿」「小怪直接均匀一点好了 因为难度也均匀了」）：
  - 小怪（同血量）：k = 目标档实际卢恩的中位数 ÷ 它所在档的（只拉高；入侵 NPC 不算进中位数、跟着所在档乘）。实际卢恩 = 敌人参数 getSoul ×
    参数挂的效果 × 随机器给这个位置挂的缩放效果的 haveSoulRate（原版说明：敌周回効果用，角色身上的卢恩出去时乘）。
    效果行：haveSoulRate = step^j（j 覆盖 1~rune_k_max），编号 rune_sp_base 起；hpunify.txt 的 rrange / re 实体 / rn 敌人参数，同攻击力。
  - Boss：击败奖励（GameAreaParam 的 bonusSoul_single / multi）按压缩曲线 R(v) = top × (v / top)^k，k 让最小的奖励 lo 正好到保底 floor，
    top 以上不变（settings 的 hard_runes.boss；20 万 ~ 50 万），取整到百；hpunify.txt 的 area 行号 单人 多人，dark_core 进这几档时改、出来改回。
    没有区域奖励的 Boss 战（卢恩在敌人身上）由 fusion 模块补到 floor（rr/bosses.py fusion_lines）。
- 异常抗性（status_resist，用户 2026-11-09「死亡和不可能敌人异常抗性也*2.22和2.5」）：difficulty 里每档一个倍率，一行效果（七种 regist*ChangeRate），
  hpunify.txt 的 sr 当前档标记 效果；dark_core 给敌对的角色都挂当前档的。乘敌人的抗性，累积从哪来都算（武器、法术、道具、油脂的命中时触发）；
  上限超过 999 不等于免疫（Boss 反复发作原版就涨到 ×8.6，见 dark_core plague.rs），免疫靠「XX无效」效果或参数 999，乘了还是免疫。
- dll\\dark_core\\hpunify.txt：flag 这几档的当前档标记；range 效果起点 行数；e 实体 效果；n 敌人参数 效果
  （开了敌人随机都按位置的实体；没开时小怪按敌人参数行，入侵 NPC、Boss 按实体）。
Boss 对照表写在 cache\\hp_unify_bosses.tsv（原版血量、现在血量、肉度、统一后的血量）。"""
from .common import *  # noqa: F401,F403

CUR0 = 9950                    # 难度当前档标记的起点（sc/difficulty.py 的 CUR0）
NPC_HP = 36
NPC_SPEFFECTS = tuple(range(76, 108, 4)) + tuple(range(376, 408, 4)) + tuple(range(488, 552, 4))
TEMPLATE = 90030               # 原版只有「咒死无效」一位的效果（敌人参数挂在九成敌人身上），去掉那一位当底子（同 rr/ailments.py 的特效效果）
DEFAULT = dict(sp_base=7302000, step=1.03, k_min=0.25, k_max=100.0, mob_goal_tier=19, boss_goal_band=[3, 5], dlc_band_from=4,
               skip_entities=[13000850, 13000851, 13000852], atk=True, atk_sp_base=7302300, atk_k_max=6.0, dlc_boss_mult=1.0,
               rune_sp_base=7302400, rune_k_max=200.0, res_sp_base=7302800)
RES_RATES = ('registPoizonChangeRate', 'registDiseaseChangeRate', 'registBloodChangeRate', 'registCurseChangeRate',
             'registFreezeChangeRate', 'registSleepChangeRate', 'registMadnessChangeRate')   # 七种异常抗性的倍率
RUNE_DEFAULT = dict(enabled=True, boss=dict(floor=200000, lo=1300, top=500000))


def rune_cfg(S):
    """settings 的 hard_runes（关掉就 None）"""
    c = S.get('hard_runes') or {}
    if not c.get('enabled', True):
        return None
    out = dict(RUNE_DEFAULT['boss'])
    out.update({k: v for k, v in (c.get('boss') or {}).items() if not k.startswith('_')})
    return out


def boss_curve(rc):
    """Boss 击败奖励的压缩曲线：R(v) = top × (v / top)^k，R(lo) = floor，top 以上不变，取整到百"""
    floor, lo, top = float(rc['floor']), float(rc['lo']), float(rc['top'])
    k = math.log(floor / top) / math.log(lo / top)
    return lambda v: v if v <= 0 or v >= top else int(round(max(floor, top * (v / top) ** k) / 100.0)) * 100
ATK_RATES = ('physicsAttackPowerRate', 'magicAttackPowerRate', 'fireAttackPowerRate', 'thunderAttackPowerRate', 'darkAttackPowerRate')


def cfg(S):
    c = S.get('hp_unify') or {}
    if not c.get('enabled', True):
        return None
    out = dict(DEFAULT)
    out.update({k: v for k, v in c.items() if not k.startswith('_') and k != 'enabled'})
    return out


def flags(S):
    """标了 lock 的难度档的当前档标记（难度没开就没有）"""
    d = S.get('difficulty') or {}
    if not d.get('enabled', True):
        return []
    return [CUR0 + k for k, t in enumerate(d.get('tiers') or []) if t.get('lock')]


def build(ctx):
    import statistics
    ctx.hpu_lines = []
    ctx.hpu_calc = None
    c, fl, src = cfg(ctx.S), flags(ctx.S), getattr(ctx, 'hpu_src', None)
    if not c or not fl or not src:
        ctx.report.append('高难度血量补正：%s，没做' % ('没开' if not c else '没有标 lock 的难度档' if not fl else '没收集到敌人位置'))
        return
    U, hp0 = src['U'], src['hp0']
    P_npc = erlib.Param(ctx.bnd.get('NpcParam.param'))
    P_sp = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    hb = ctx.S.get('enemy_hp_band') or {}
    blend = hb.get('boss_blend') or {}
    boss_mult = [float(x) for x in hb.get('boss') or [1.0]]
    dlc_from = int((hb.get('curve') or {}).get('dlc_from', 21))

    def rate(sid):
        r = P_sp.rows.get(sid)
        return (struct.unpack_from('<f', r, 16)[0] or 1.0) if r is not None else 1.0

    def mult(nid):
        m = 1.0
        for o in NPC_SPEFFECTS:
            sid = struct.unpack_from('<i', P_npc.rows[nid], o)[0]
            if sid > 0:
                m *= rate(sid)
        return m

    def van(nid):
        """原版实际血量（改血量之前的参数血量 × 身上的倍率）"""
        return hp0.get(nid, 0) * mult(nid) if nid in P_npc.rows else 0.0

    step, kmin, kmax = float(c['step']), float(c['k_min']), float(c['k_max'])
    imin, imax = math.floor(math.log(kmin) / math.log(step)), math.ceil(math.log(kmax) / math.log(step))
    base = int(c['sp_base'])

    def sp_of(k):
        i = round(math.log(min(kmax, max(kmin, k))) / math.log(step))
        return None if i == 0 else base + i - imin

    ent_sp, npc_sp = {}, {}
    # 小怪
    final = U['final']
    goal_t = int(c['mob_goal_tier'])
    dlc_ts = [t for t in final if t >= dlc_from]
    goal = {False: final.get(goal_t), True: final[max(dlc_ts)] if dlc_ts else None}

    def k_mob(t):
        g = goal[t >= dlc_from]
        same = [x for x in final if (x >= dlc_from) == (t >= dlc_from)]
        if not g or not same:
            return None
        f = final.get(t) or final[min(same, key=lambda x: (abs(x - t), x))]      # 这一级没有统计（入侵 NPC 的地方没有小怪）：用最近的一级
        return max(1.0, g / f)
    skip = {int(e) for e in c['skip_entities']}
    k_t = {}
    for kind, key, t in U['mobs']:
        k = k_mob(t)
        if k is None or (kind == 'e' and key in skip):
            continue
        k_t[t] = k
        sp = sp_of(k)
        if sp is not None:
            (ent_sp if kind == 'e' else npc_sp)[key] = sp
    n_mob = len(ent_sp) + len(npc_sp)
    # Boss
    rows = U['bosses']
    neutral_ent = {int(e) for e in blend.get('neutral_entities') or ()}
    neutral = {nv for e, nv, _p, _b, _c in rows if e in neutral_ent}
    by_b, own_band = defaultdict(list), {}
    for e, nv, _p, b, _c in rows:
        if nv not in neutral:
            by_b[b].append(van(nv))
        own_band[nv] = min(own_band.get(nv, 99), b)
    med = {b: statistics.median(v) for b, v in by_b.items() if v}
    lo, hi = float(blend.get('min', 0.25)), float(blend.get('max', 3.0))
    gb = [int(x) for x in c['boss_goal_band']]
    dlc_b = int(c['dlc_band_from'])
    goal_b = {s: med[g] * boss_mult[min(g, len(boss_mult) - 1)] if g in med else None for s, g in ((False, gb[0]), (True, gb[1]))}
    dlc_boss = float(c['dlc_boss_mult'])          # DLC 位置的 Boss 目标再乘（斗技场用的 goal_b 不乘）
    # 斗技场试炼（rr/arena.py）的敌人也按这里的算法挂高难度倍率（n / an 行）：把要用的留给它
    # mob_goal / dlc_from：小怪本体、DLC 的目标（斗技场死亡以上照 lock_tiers 选本体 / DLC 目标时换算用，用户 2026-11-20）
    ctx.hpu_calc = dict(sp_of=sp_of, k_mob=k_mob, goal_b=goal_b, dlc_b=dlc_b, lo=lo, hi=hi, mob_goal=goal, dlc_from=dlc_from)

    def tness(nid, b):
        return 1.0 if nid in neutral else van(nid) / med[b]
    try:
        names = {b['entity']: b['name'] for b in json.load(open(os.path.join(ctx.data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses']}
    except (OSError, ValueError, KeyError):
        names = {}
    table, ks, n_skip = [], [], 0
    for e, nv, npc, b, cur in rows:
        if cur is None:                           # 没开敌人随机：按改完的参数算现在的实际血量
            cur = struct.unpack_from('<I', P_npc.rows[npc], NPC_HP)[0] * mult(npc)
        g = goal_b[b >= dlc_b]
        if g is None or cur <= 0:
            continue
        if b >= dlc_b:
            g *= dlc_boss
        ob = own_band.get(npc)
        T = tness(npc, ob) if ob in med else tness(nv, b) if b in med else 1.0
        T = min(hi, max(lo, T))
        k = g * T / cur
        sp = None if e in skip else sp_of(k)
        if e in skip:
            n_skip += 1
        if sp is not None:
            ent_sp[e] = sp
            ks.append(k)
        table.append((b, e, names.get(e, ''), nv, npc, van(npc), cur, T, k, cur * step ** (sp - base + imin) if sp else cur))
    # 血量分在别的实体上的 Boss（幽影树化身的血条代理和身体，rr/stage3.py）：挂和本体一样的倍率
    for e, others in (U.get('linked') or {}).items():
        if e in ent_sp:
            ent_sp.update((x, ent_sp[e]) for x in others)
    # 效果行
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}
    put = lambda row, f, v: struct.pack_into('<' + lay[f][1], row, lay[f][2], v)
    for i in range(imin, imax + 1):
        rid = base + i - imin
        if rid in P_sp.rows:
            raise RuntimeError('高难度血量补正的效果编号 %d 已经有人用了' % rid)
        row = bytearray(P_sp.rows[TEMPLATE])
        o, bit = lay['disableCurse'][2], lay['disableCurse'][3]
        row[o] &= ~(1 << bit)
        put(row, 'iconId', -1)
        put(row, 'effectEndurance', -1.0)
        put(row, 'maxHpRate', step ** i)
        put(row, 'spCategory', 0)
        P_sp.add_row(rid, bytes(row))
    # 攻击力：按位置所在档的区域攻击倍率拉到目标档
    atk_lines, atk_txt = [], '没开'
    if c.get('atk', True):
        from .stage3 import boss_tiers
        atk_off = lay['physicsAttackPowerRate'][2]

        def area_atk(t):
            """这一档的区域强度效果的攻击倍率（本体 0~20、DLC 从 dlc_from 起）"""
            sid = 7000 + 10 * max(0, min(20, t)) if t < dlc_from else 20007000 + 10 * max(0, min(19, t - dlc_from))
            r = P_sp.rows.get(sid)
            return struct.unpack_from('<f', r, atk_off)[0] if r is not None else None
        a_goal = {False: area_atk(goal_t), True: area_atk(max(dlc_ts)) if dlc_ts else None}

        def k_atk(t):
            a, g = area_atk(t), a_goal[t >= dlc_from]
            return max(1.0, g / a) if a and g else 1.0
        akmax = float(c['atk_k_max'])
        jmax = math.ceil(math.log(akmax) / math.log(step))
        abase = int(c['atk_sp_base'])

        def asp_of(k):
            j = round(math.log(min(akmax, max(1.0, k))) / math.log(step))
            return None if j == 0 else abase + j - 1
        ctx.hpu_calc.update(k_atk=k_atk, asp_of=asp_of, atk_goal=a_goal)
        a_ent, a_npc, a_t = {}, {}, {}
        for kind, key, t in U['mobs']:
            sp = asp_of(k_atk(t))
            a_t[t] = k_atk(t)
            if sp is not None:
                (a_ent if kind == 'e' else a_npc)[key] = sp
        rd = ctx.a.randomizer_dir or os.path.normpath(os.path.join(ctx.data_dir, '..', '..', '..', 'randomizer'))
        bt = boss_tiers(rd, ctx.data_dir)
        a_boss = []
        for e, _nv, _npc, _b, _c in rows:
            if e in bt:
                k = k_atk(bt[e])
                sp = asp_of(k)
                if sp is not None:
                    a_ent[e] = sp
                    a_boss.append(k)
        for j in range(1, jmax + 1):
            rid = abase + j - 1
            if rid in P_sp.rows:
                raise RuntimeError('高难度攻击力补正的效果编号 %d 已经有人用了' % rid)
            row = bytearray(P_sp.rows[TEMPLATE])
            o, bit = lay['disableCurse'][2], lay['disableCurse'][3]
            row[o] &= ~(1 << bit)
            put(row, 'iconId', -1)
            put(row, 'effectEndurance', -1.0)
            put(row, 'spCategory', 0)
            for f in ATK_RATES:
                put(row, f, step ** j)
            P_sp.add_row(rid, bytes(row))
        atk_lines = ['arange %d %d' % (abase, jmax)] + ['ae %d %d' % kv for kv in sorted(a_ent.items())] + \
            ['an %d %d' % kv for kv in sorted(a_npc.items())]
        atk_txt = '目标本体 ×%.2f（强度 %d）/ DLC ×%.2f，效果 %d 起 %d 行；小怪 %s；Boss %d 处%s' % (
            a_goal[False] or 0, goal_t, a_goal[True] or 0, abase, jmax,
            ' '.join('%d:×%.2f' % (t, k) for t, k in sorted(a_t.items()) if k > 1.0) or '都不用乘', len(a_boss),
            '（×%.2f~%.2f）' % (min(a_boss), max(a_boss)) if a_boss else '')
    rune_lines, rune_txt = rune_unify(ctx, c, U, P_npc, P_sp, lay, put, goal_t, dlc_from)
    # 小怪掉落统一到 DLC 最后一档（rr/unidentified.py 的 hard_lines，用户 2026-11-04「高难度后小怪爆率统一到dlc后期」）
    drops = ctx.unid.hard_lines() if getattr(ctx, 'unid', None) else []
    if drops:
        rune_lines = rune_lines + drops
        ctx.report.append('高难度掉落统一（同上，dark_core 进这几档时改道具格）：%d 张复制表接上的行换成 DLC 最后一档的（普通 %s 行 / 精英 %s 行）' % (
            sum(1 for l in drops if l.startswith('dropcopy')), *[l.split()[3] for l in drops if l.startswith('droptgt')]))
    # 异常抗性：每档一行，七种抗性乘同一个倍率
    res_lines, res_txt = [], []
    for k, t in enumerate((ctx.S.get('difficulty') or {}).get('tiers') or []):
        m = float(t.get('status_resist', 1))
        if m == 1 or CUR0 + k not in fl:
            continue
        rid = int(c['res_sp_base']) + k
        if rid in P_sp.rows:
            raise RuntimeError('高难度异常抗性的效果编号 %d 已经有人用了' % rid)
        row = bytearray(P_sp.rows[TEMPLATE])
        o, bit = lay['disableCurse'][2], lay['disableCurse'][3]
        row[o] &= ~(1 << bit)
        put(row, 'iconId', -1)
        put(row, 'effectEndurance', -1.0)
        put(row, 'spCategory', 0)
        for f in RES_RATES:
            put(row, f, m)
        P_sp.add_row(rid, bytes(row))
        res_lines.append('sr %d %d' % (CUR0 + k, rid))
        res_txt.append('%s ×%g（效果 %d）' % (t['name'], m, rid))
    if res_txt:
        ctx.report.append('高难度异常抗性（dark_core 给敌对的角色挂当前档的）：' + '、'.join(res_txt))
    ctx.bnd.put('SpEffectParam.param', P_sp.serialize())
    ctx.hpu_lines = ['flag %d' % f for f in fl] + ['range %d %d' % (base, imax - imin + 1)] + \
        ['e %d %d' % kv for kv in sorted(ent_sp.items())] + ['n %d %d' % kv for kv in sorted(npc_sp.items())] + atk_lines + rune_lines + res_lines
    ctx.features['hp_unify'] = {'flags': fl, 'sp_base': base, 'rows': imax - imin + 1}
    try:
        cache = os.path.join(os.path.dirname(ctx.data_dir), 'cache')
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, 'hp_unify_bosses.tsv'), 'w', encoding='utf-8-sig', newline='') as f:
            f.write('档\t位置实体\t位置原版 Boss\t原版敌人参数\t放进来的敌人参数\t放进来的原版血量\t现在血量\t肉度\t倍率\t统一后\r\n')
            for r in sorted(table):
                f.write('%d\t%d\t%s\t%d\t%d\t%.0f\t%.0f\t%.2f\t%.2f\t%.0f\r\n' % r)
    except OSError:
        pass
    mob_txt = ' '.join('%d:×%.1f' % (t, k) for t, k in sorted(k_t.items()) if k > 1.0)
    ctx.report.append('高难度血量补正（标记 %s 亮着时 dark_core 挂，效果 %d 起 %d 行，每档 ×%g）：小怪目标本体 %d（强度 %d）/ DLC %d，'
                      '%d 处 / 行挂上（%s）；Boss 目标中位本体 %d / DLC %d（×%g）× 肉度（夹在 %g~%g），%d 处挂上%s%s' % (
                          '/'.join(map(str, fl)), base, imax - imin + 1, step, goal[False] or 0, goal_t, goal[True] or 0,
                          n_mob, mob_txt or '都不用乘', goal_b[False] or 0, (goal_b[True] or 0) * dlc_boss, dlc_boss, lo, hi, len(ks),
                          '（倍率 %.2f~%.2f，中位 %.2f）' % (min(ks), max(ks), statistics.median(ks)) if ks else '',
                          '，%d 处共用血条的不动' % n_skip if n_skip else ''))
    ctx.report.append('高难度攻击力补正（同上，和血量补正一起挂）：%s' % atk_txt)
    ctx.report.append('高难度卢恩补正（同上）：%s' % rune_txt)


def rune_unify(ctx, c, U, P_npc, P_sp, lay, put, goal_t, dlc_from):
    """小怪按档拉到目标档的卢恩（haveSoulRate 效果，同攻击力）+ Boss 击败奖励的压缩曲线（area 行）。返回 (定义行, 报告)"""
    import statistics
    rc = rune_cfg(ctx.S)
    if rc is None:
        return [], '没开'
    L = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'NpcParam.xml')))[0]}
    soul_of = lambda nid: struct.unpack_from('<' + L['getSoul'][1], P_npc.rows[nid], L['getSoul'][2])[0]
    hs_off = lay['haveSoulRate'][2]

    def hs(sid):
        r = P_sp.rows.get(sid) if sid > 0 else None
        return (struct.unpack_from('<f', r, hs_off)[0] or 1.0) if r is not None else 1.0

    def runes(kind, key):
        nid, sc = (key, ()) if kind == 'n' else (U.get('npc') or {}).get(key, (None, ()))
        if nid is None or nid not in P_npc.rows:
            return 0.0
        m = 1.0
        for o in NPC_SPEFFECTS:
            m *= hs(struct.unpack_from('<i', P_npc.rows[nid], o)[0])
        for sid in sc:
            m *= hs(sid)
        return soul_of(nid) * m
    inv = (U.get('inv') or set()) | (U.get('helpers') or set())     # 入侵 NPC、随机器新加的 Boss 随从（rr/stage3.py）不进中位数
    by_t = defaultdict(list)
    val = {}
    for kind, key, t in U['mobs']:
        v = runes(kind, key)
        val[(kind, key)] = v
        if v > 0 and not (kind == 'e' and key in inv):
            by_t[t].append(v)
    med = {t: statistics.median(v) for t, v in by_t.items() if v}
    dlc_ts = [t for t in med if t >= dlc_from]
    goal = {False: med.get(goal_t), True: med[max(dlc_ts)] if dlc_ts else None}

    def k_of(t):
        g = goal[t >= dlc_from]
        same = [x for x in med if (x >= dlc_from) == (t >= dlc_from)]
        if not g or not same:
            return 1.0
        f = med.get(t) or med[min(same, key=lambda x: (abs(x - t), x))]
        return max(1.0, g / f)
    step = float(c['step'])
    kmax = float(c['rune_k_max'])
    jmax = math.ceil(math.log(kmax) / math.log(step))
    rbase = int(c['rune_sp_base'])

    def sp_of(k):
        j = round(math.log(min(kmax, max(1.0, k))) / math.log(step))
        return None if j == 0 else rbase + j - 1
    r_ent, r_npc, r_t = {}, {}, {}
    for kind, key, t in U['mobs']:
        k = k_of(t)
        r_t[t] = k
        sp = sp_of(k) if val.get((kind, key), 0) > 0 else None
        if sp is not None:
            (r_ent if kind == 'e' else r_npc)[key] = sp
    for j in range(1, jmax + 1):
        rid = rbase + j - 1
        if rid in P_sp.rows:
            raise RuntimeError('高难度卢恩补正的效果编号 %d 已经有人用了' % rid)
        row = bytearray(P_sp.rows[TEMPLATE])
        o, bit = lay['disableCurse'][2], lay['disableCurse'][3]
        row[o] &= ~(1 << bit)
        put(row, 'iconId', -1)
        put(row, 'effectEndurance', -1.0)
        put(row, 'spCategory', 0)
        put(row, 'haveSoulRate', step ** j)
        P_sp.add_row(rid, bytes(row))
    # Boss：击败奖励的压缩曲线（只改有击败标记的区域）
    GL = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'GameAreaParam.xml')))[0]}
    G = erlib.Param(ctx.bnd.get('GameAreaParam.param'))
    gv = lambda row, f: struct.unpack_from('<' + GL[f][1], row, GL[f][2])[0]
    curve = boss_curve(rc)
    area, sample = [], []
    for rid, row in sorted(G.rows.items()):
        v, m = gv(row, 'bonusSoul_single'), gv(row, 'bonusSoul_multi')
        if gv(row, 'defeatBossFlagId') <= 0 or v <= 0:
            continue
        nv = curve(v)
        if nv != v:
            area.append('area %d %d %d' % (rid, nv, int(round(m * nv / v / 100.0)) * 100 if m > 0 else 0))
            sample.append((v, nv))
    ctx.rune_curve = curve
    lines = ['rrange %d %d' % (rbase, jmax)] + ['re %d %d' % kv for kv in sorted(r_ent.items())] + \
        ['rn %d %d' % kv for kv in sorted(r_npc.items())] + area
    pick = sorted(set(sample))
    txt = '小怪目标本体 %.0f（强度 %d）/ DLC %.0f，效果 %d 起 %d 行，%d 处 / 行挂上（%s）；Boss 击败奖励 %d 处按曲线（保底 %d、最小 %d、顶 %d）：%s' % (
        goal[False] or 0, goal_t, goal[True] or 0, rbase, jmax, len(r_ent) + len(r_npc),
        ' '.join('%d:×%.1f' % (t, k) for t, k in sorted(r_t.items()) if k > 1.0) or '都不用乘',
        len(area), int(rc['floor']), int(rc['lo']), int(rc['top']),
        ' '.join('%d→%d' % x for x in pick[::max(1, len(pick) // 8)]))
    return lines, txt


def def_lines(ctx):
    return getattr(ctx, 'hpu_lines', [])
