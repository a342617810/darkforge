# -*- coding: utf-8 -*-
"""追忆换取（settings 的 remembrance；一次性重随：第一次抽了记进 --state 的 remembrance，以后照旧；点「一次性重随」才重抽）。
解指老妪用追忆换的东西（ShopLineupParam ROWS 里材料是追忆的格子）：
  - 接肢的追忆（GODRICK）：第一格换成战灰「熔炉百相之羽」（FLIGHT_GEM，飞行由 dll\\dark_wings 管；还是这一格，已经换过的存档照旧显示换过了），
    原来第一格的武器挪到 AXE_ROW（新的库存标记 AXE_STOCK，照原版「格子 → 标记」的排法），第二格照旧，这两把也按下面换成成品传说
    （用户 2026-10-30「葛瑞克追忆不再只能兑换熔炉百相之羽」；以前是删掉）。它们的种子另记在一次性重随的 remembrance_godrick，
    别的追忆武器的种子（remembrance）指纹不变、照旧；
  - 其他追忆的武器格：换成成品传说，每格一个专用编号（开局装备编号段里 REM_OFF 起，编号 = 第一个 + (REM_OFF + 格子 - ROWS[0]) × 1 万）：
    本体就是原来那把，战技和本体自带的常驻效果保留，补正只从传说分布最高的 scaling_top_pct% 里抽，能力需求照新装备系统的规则；
    dll\\dark_core 一启动按种子生成（同开局装备：items.txt 的 start 行，keep = 1），角色拿到后记进这个角色的记录
    （以后点「一次性重随」只影响还没换的）；
  - 定制武器的格子（商店格类型 5 = EquipParamCustomWeapon：本体 + 强化等级 / 战灰，比如山猪骑士的追忆换的剑型长矛）按它的本体算，
    同样换成成品传说，格子改成普通武器（用户 2026-11-13「追忆里的剑型长矛没有正确替换」：以前只认普通武器，这一格照原版）；
  - 法术、道具、护符等其他格子不动。
用特殊货币买的格子（龙飨祭坛的龙心脏 / 拜尔的心脏、瑟濂的星光碎片……）：原版只卖道具和战灰，开了物品随机，随机器可能放武器进来
  （龙飨祭坛和追忆换取都是它的「高级商店」）→ 武器同样换成成品传说（种子另记在 remembrance_cur，编号按 SLOTS），价格照旧；
  护符 / 防具由 shops.gear_to_ash 换成战灰（用户 2026-11-02「补上龙飨祭坛」）。
要在 startgear.build 之后（开局装备的编号段、start_items）"""
from .common import *  # noqa: F401,F403
from . import affixes, once, startgear

ROWS = (101800, 101999)
REM_OFF = 500                    # 开局装备编号段里，追忆武器从第 500 个起（开局装备用前 500 个）
# 格子段 → 开局装备编号段里的起始位置：追忆换取（含龙飨祭坛 101950~）500~699、DLC 的龙飨 810~839、瑟濂的人偶店 850~899
# （原版 DLC 的龙飨只到 102355、人偶店只到 100340）；700~799 是支线的史诗武器、800 是大蛇狩猎矛、900~999 是商人的小极品，
# 各段不能重叠（layout_check）；不在表里的特殊货币格子不换传说，由 shops.gear_to_ash 换战灰
SLOTS = ((ROWS[0], ROWS[1], REM_OFF), (102350, 102379, 810), (100300, 100349, 850))
GODRICK = 2950                   # 接肢的追忆
FLIGHT_GEM = 200100              # 战灰：熔炉百相之羽
# 接肢第一格原来的武器挪到这一格：追忆换取打开的是 101898~101949（1:111），101949 是原版空号（101897 不行，那是双子老妪普通商店的最后一格）；
# 库存标记照 101900 → 290000、101948 → 290480 的排法，原版没用
AXE_ROW, AXE_STOCK = 101949, 290490
EQUIP_WEAPON, EQUIP_GEM, EQUIP_CUSTOM = 0, 4, 5      # 商店格的 equipType：武器、战灰、定制武器（EquipParamCustomWeapon）
LEGENDARY = 3


def _no_overlap(what, segs, cap):
    segs = sorted(segs, key=lambda t: t[1])
    for a, b in zip(segs, segs[1:]):
        if b[1] < a[2]:
            raise RuntimeError('%s编号段重叠：%s（%d~%d）和%s（%d~%d）' % (what, a[0], a[1], a[2] - 1, b[0], b[1], b[2] - 1))
    if segs[-1][2] > cap:
        raise RuntimeError('%s编号段超出 %d 个：%s 到 %d' % (what, cap, segs[-1][0], segs[-1][2] - 1))


def layout_check():
    """开局装备编号段里各段不能重叠，重叠了开了物品随机时会撞号（重随报「编号已被占用」）。
    武器 230000000 起每个 1 万号、到容器的 240000000 为止（1000 个）；防具 29000000 起每个 100 号、到容器的 30000000 为止（10000 个）"""
    from . import containers, serpent, shops, unidentified
    qw, qp = unidentified.QUEST_GEAR_W, unidentified.QUEST_GEAR_P
    _no_overlap('开局武器', [('开局装备', 0, 500)] +
                [('追忆 / 特殊货币格子 %d~%d' % (lo, hi), off, off + hi - lo + 1) for lo, hi, off in SLOTS] +
                [('支线的史诗武器', qw[0], qw[0] + qw[1]), ('大蛇狩猎矛', serpent.SERPENT_OFF, serpent.SERPENT_OFF + 1),
                 ('商人的小极品', shops.MER_OFF, shops.MER_OFF + shops.MER_MAX)],
                (containers.W0 - startgear.START_W0) // 10000)
    _no_overlap('开局防具', [('开局装备', 0, 1000), ('支线的史诗防具', qp[0], qp[0] + qp[1]),
                           ('英雄防具（第一版，只留编号）', shops.HERO_P_OFF, shops.HERO_P_OFF + len(shops.HERO_OLD)),
                           ('英雄防具商店', shops.HERO_SHOP_OFF, shops.HERO_SHOP_OFF + shops.HERO_SHOP_MAX)],
                (containers.P0 - startgear.START_P0) // 100)


def slot_index(rid):
    """格子 → 开局装备编号段里的位置（SLOTS），不在表里是 None"""
    return next((off + rid - lo for lo, hi, off in SLOTS if lo <= rid <= hi), None)


def build(ctx):
    layout_check()
    c = ctx.S.get('remembrance') or {}
    if not c.get('enabled', True) or not getattr(ctx, 'containers', None):
        return
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    sl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'ShopLineupParam.xml')))[0]}
    ml = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipMtrlSetParam.xml')))[0]}
    g = lambda L, r, f: struct.unpack_from('<' + L[f][1], r, L[f][2])[0]
    s = lambda L, r, f, v: struct.pack_into('<' + L[f][1], r, L[f][2], v)
    P = erlib.Param(ctx.bnd.get('ShopLineupParam.param'))
    M = erlib.Param(ctx.bnd.get('EquipMtrlSetParam.param'))
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    G = erlib.Param(ctx.bnd.get('EquipParamGem.param'))
    C = erlib.Param(ctx.bnd.get('EquipParamCustomWeapon.param'))
    custom = {cid: struct.unpack_from('<i', row, 0)[0] for cid, row in C.rows.items()}    # 定制武器 → 本体（第一个字段 baseWepId）

    def as_weapon(et, eid):
        """定制武器按它的本体（去掉强化 / 质变那几位）算普通武器；别的原样"""
        if et == EQUIP_CUSTOM and custom.get(eid, 0) > 0:
            b = custom[eid]
            return EQUIP_WEAPON, b - b % 10000
        return et, eid
    custom_rids = set()                                # 定制武器的格子（2026-11-13 才开始换，种子沿用要按以前不含它们的指纹找）
    rows = []                                          # (格子, 追忆道具, 类, 编号)；定制武器已经换成本体
    for rid in sorted(P.rows):
        if ROWS[0] <= rid <= ROWS[1]:
            r = P.rows[rid]
            m = g(sl, r, 'mtrlId')
            if m in M.rows:
                if g(sl, r, 'equipType') == EQUIP_CUSTOM:
                    custom_rids.add(rid)
                rows.append((rid, g(ml, M.rows[m], 'materialId01'), *as_weapon(g(sl, r, 'equipType'), g(sl, r, 'equipId'))))
    if not rows:
        ctx.report.append('追忆换取：没找到用追忆换的格子，没改')
        return
    # 接肢的追忆 → 飞行战灰（第一格）+ 原来的两把武器（第一把挪到 AXE_ROW、第二把照旧）
    godrick = [x for x in rows if x[1] == GODRICK]
    gweapons = []
    if c.get('godrick_flight_ash', True) and godrick and FLIGHT_GEM in G.rows:
        rid0, mat0, et0, eid0 = godrick[0]
        if AXE_ROW in P.rows:
            raise RuntimeError('追忆换取：接肢武器要挪去的格子 %d 已被占用' % AXE_ROW)
        moved = bytearray(P.rows[rid0])
        s(sl, moved, 'eventFlag_forStock', AXE_STOCK)
        P.add_row(AXE_ROW, bytes(moved))
        r = P.rows[rid0]
        s(sl, r, 'equipType', EQUIP_GEM)
        s(sl, r, 'equipId', FLIGHT_GEM)
        gweapons = [x for x in [(AXE_ROW, mat0, et0, eid0)] + godrick[1:] if x[2] == EQUIP_WEAPON]
    elif godrick:
        ctx.report.append('追忆换取：没有战灰 %d，接肢的追忆没改' % FLIGHT_GEM)
        godrick = []
    gone = {x[0] for x in godrick}
    # 其他追忆的武器格 → 成品传说
    wb, _pb, nm = affixes.bases(ctx, lib)
    ok = {b['id'] for b in wb}
    weapons = [x for x in rows if x[0] not in gone and x[2] == EQUIP_WEAPON]
    bad = [x for x in weapons + gweapons if x[3] not in ok]
    weapons = [x for x in weapons if x[3] in ok]
    gweapons = [x for x in gweapons if x[3] in ok]
    # 特殊货币的格子里随机器放的武器（开了物品随机才有）
    cur = []
    for rid in sorted(P.rows):
        r = P.rows[rid]
        if g(sl, r, 'equipType') == EQUIP_CUSTOM:
            custom_rids.add(rid)
        et, eid = as_weapon(g(sl, r, 'equipType'), g(sl, r, 'equipId'))
        if g(sl, r, 'costType') != 0 and g(sl, r, 'mtrlId') == -1 and slot_index(rid) is not None \
                and et == EQUIP_WEAPON and eid in ok:
            cur.append((rid, 0, EQUIP_WEAPON, eid))
    if not hasattr(ctx, 'start_ids'):
        ctx.start_ids = (startgear.START_W0, 10000, startgear.START_P0, 100)
    first, step = ctx.start_ids[0], ctx.start_ids[1]
    ids = {x[0]: first + slot_index(x[0]) * step for x in weapons + gweapons + cur}
    used = [i for i in ids.values() if i in W.rows]
    if used:
        raise RuntimeError('追忆武器的编号 %s 已被占用' % used[:5])

    def seeds(kind, lst):
        """一次性重随：这批格子第一次抽的种子（指纹按格子内容算），返回 (种子, 是不是新抽的)"""
        key = once.sig(*[repr(x) for x in lst])
        plan = once.get(ctx, kind, key)
        fresh = not (plan and all(str(x[0]) in plan for x in lst))
        if fresh:
            with once.own_rng(ctx, kind):
                plan = {str(x[0]): ctx.rng.getrandbits(62) for x in lst}
            # 2026-11-13 补上了定制武器的格子：其余格子沿用以前（不含定制武器格子时那份指纹）抽的种子，只有新格子用新抽的。
            # 不能用 once.last：普通世界和死亡以上世界的格子不一样，各记一份，最后记的那份可能是另一个世界的
            old = [x for x in lst if x[0] not in custom_rids]
            prev = (once.get(ctx, kind, once.sig(*[repr(x) for x in old])) if len(old) < len(lst) else None) or {}
            plan.update({r: v for r, v in prev.items() if r in plan})
            once.put(ctx, kind, key, plan)
        return plan, fresh
    plan, fresh = seeds('remembrance', weapons)
    if gweapons:
        gplan, gfresh = seeds('remembrance_godrick', gweapons)
        plan = dict(plan, **gplan)
        fresh = fresh or gfresh
    if cur:
        cplan, cfresh = seeds('remembrance_cur', cur)
        plan = dict(plan, **cplan)
        fresh = fresh or cfresh
    weapons = weapons + gweapons
    wf = json.load(open(os.path.join(ctx.data_dir, 'weapon_fields.json'), encoding='utf-8'))
    origin = [(o, sz) for f, o, sz in wf['own'] if f.startswith('originEquipWep')]
    top = int(c.get('scaling_top_pct', 30))
    for rid, _goods, _t, base in weapons + cur:
        i = ids[rid]
        startgear.copy_weapon(W, origin, base, i)
        s(sl, P.rows[rid], 'equipType', EQUIP_WEAPON)      # 定制武器的格子改成普通武器
        s(sl, P.rows[rid], 'equipId', i)
        ctx.start_items.append({'cat': 0, 'id': i, 'tier': LEGENDARY, 'base': base, 'seed': int(plan[str(rid)]), 'maxreq': [99] * 5,
                                'top': top, 'min_status': 0, 'keep': True})
    ctx.bnd.put('EquipParamWeapon.param', W.serialize())
    ctx.bnd.put('ShopLineupParam.param', P.serialize())
    startgear.placeholders(ctx, list(ids.values()), [])
    ctx.report.append('追忆换取（%s）：%s%d 格武器换成成品传说（本体和战技照原来那把，补正前 %d%%，生成要 dll\\dark_core）：%s%s' % (
        '新抽的' if fresh else '沿用第一次抽的',
        '接肢的追忆第一格换成战灰 %d，原来的武器挪到 %d、和第二格一起换成成品传说；' % (FLIGHT_GEM, AXE_ROW) if godrick else '', len(weapons), top,
        '、'.join(nm('zh', 'WeaponName', x[3]) for x in weapons),
        '；%d 格的武器不在词条库的本体里，没换：%s' % (len(bad), '、'.join(nm('zh', 'WeaponName', x[3]) or str(x[3]) for x in bad)) if bad else ''))
    if cur:
        ctx.report.append('特殊货币的格子（龙飨祭坛等，开了物品随机）：%d 格武器换成成品传说（价格照旧）：%s' % (
            len(cur), '、'.join('%d %s' % (x[0], nm('zh', 'WeaponName', x[3])) for x in cur)))
