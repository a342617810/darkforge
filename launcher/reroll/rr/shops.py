# -*- coding: utf-8 -*-
"""商人的商店（v0.3 / v0.4 的商店重抽、甲虫掉战灰、商店价格统一，迁移后补回；原版商品照旧，只是换位置 / 定价）：
  - 商店重抽（shop_reroll，一次性重随：第一次抽了记进 --state 的 shop，以后照旧）：普通商人（data\\shop_merchants.json 的行）
    用卢恩买的法术祷告 / 战灰 / 制作笔记在所有商人之间互换。要解锁才卖的格子只和要解锁的互换，普通格只和普通格；
    制作笔记只和制作笔记互换；专卖法术的商人只拿法术。售罄 / 解锁标记留在原格子，价格、数量跟着物品走；
    制作笔记的库存标记（= 它点亮的配方解锁标记）跟着笔记走，只有解锁标记留在原格子（2026-11-12）。
    换完把多出来的重复战灰格换成商店里没有的战灰，尽量每种战灰都能买到；
  - 甲虫掉战灰（scarab_ashes，一次性重随：记进 shop_scarab）：原版掉战灰的甲虫（data\\scarab_ashes.json）重新分配战灰，
    原本只有甲虫掉、商人买不到（追忆也换不到）的一定还分给甲虫，其余从全部战灰里随机，每只一种、不重复；
  - 不卖原版装备（no_vanilla_gear，用户 2026-10-28；一次性重随：记进 shop_gear）：用卢恩买的原版武器 / 防具 / 护符格换成战灰，
    先补商店里买不到的战灰，其余随机。箭矢、要材料换的（追忆、防具改造）、暗黑商店的不动；
    用特殊货币买的（龙飨祭坛的龙心脏等；开了物品随机随机器才会放装备进来）：武器在 rr/remembrance.py 换成成品传说，
    护符 / 防具在这里换成战灰（一次性重随另记 shop_gear_cur），价格照旧；
  - 价格统一（shop_prices）：普通商人用卢恩买的战灰（含上面换来的）、法术祷告按物品稀有度（1 / 2 / 3 → base × by_rarity），
    制作笔记 base × book。箭、消耗品、材料不动。要在重抽之后（价格跟着物品走）
  - 商人的战灰格换成未鉴定物品 / 小极品传说武器（merchant_loot，用户 2026-11-01：战灰在暗黑商店都能买了，商人卖的没用了；
    一次性重随：记进 shop_loot）：见 merchant_loot。法术祷告格不动（暗黑商店的魔法 / 祷告要打败满月女王才上架，前期还靠商人）"""
from .common import *  # noqa: F401,F403
from . import affixes, once, startgear, unidentified

SPELL_TYPES = (5, 16, 17, 18)            # EquipParamGoods.goodsType：魔法 / 祷告（含自身增益类）
EQUIP_GOODS, EQUIP_GEM = 3, 4
EQUIP_GEAR = {0: 'EquipParamWeapon', 1: 'EquipParamProtector', 2: 'EquipParamAccessory'}   # 商店格的 equipType：武器 / 防具 / 护符
DARK_SHOP = (114000, 119299)             # 暗黑商店的行（rr/darkshop.py，卖的是我们生成的装备；117000 起是回购商店，118000 起是魔法 / 祷告商店，119000 起是战灰商店）
LOT_GEM = 5                              # 掉落表的物品类别：战灰
TEST_SHOP = 900000                       # 900000 起是原版没用的测试行
OWN_WEAPON = 100000000                   # 1 亿起的武器是我们生成的（容器、开局装备、追忆 / 龙飨的成品传说……）
# 「获得英雄的防具」（赐福「更多选项」，恩雅的头目套装商店：1:148 打开 101500~101574，打败对应头目才卖，原版 49 件防具）。
# 2026-11-08 第一版误改了双子老妪普通商店里的 101874~101877 四格（原版骑士套），英雄防具还是被「不卖原版装备」换成战灰、
# 又被商人货架换成未鉴定物品 / 小极品武器（用户 2026-11-13「获得英雄防具的替换还是有问题」「应该替换成小极品防具的」）
HERO_SHOP = (101500, 101574)
HERO_SHOP_OFF, HERO_SHOP_MAX = 5100, 100      # 防具开局编号段 29000000 + (5100 + j)×100
# 第一版的四格：双子老妪那边改回原版规则（换战灰、不进商人货架），生成的四件编号留着（只建参数行、不上架），已经买到的照旧
HERO_OLD = {101874: 0, 101875: 1, 101876: 2, 101877: 3}
HERO_P_OFF = 5000                        # 第一版的四件：29000000 + 5000×100 起，避开普通开局装备扫描的 29000000~29099900


def build(ctx):
    sl = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'ShopLineupParam.xml')))[0]
    lg = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))[0]
    lm = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGem.xml')))[0]
    so = {n: (o, fc) for n, fc, o, bp, bits, d in sl if not bits}
    g = lambda r, f: struct.unpack_from('<' + so[f][1], r, so[f][0])[0]
    x = {'P': erlib.Param(ctx.bnd.get('ShopLineupParam.param')), 'G': erlib.Param(ctx.bnd.get('EquipParamGoods.param')),
         'M': erlib.Param(ctx.bnd.get('Magic.param')), 'Gem': erlib.Param(ctx.bnd.get('EquipParamGem.param')),
         'merch': json.load(open(os.path.join(ctx.data_dir, 'shop_merchants.json'), encoding='utf-8'))['rows'],
         'books': set(json.load(open(os.path.join(ctx.data_dir, 'cookbooks.json'), encoding='utf-8'))['ids']),
         'g': g, 'so': so, 'goods_type': lambda i: pdm.unpack(lg, bytes(x['G'].rows[i]))['goodsType'],
         'gem_rarity': lambda i: pdm.unpack(lm, bytes(x['Gem'].rows[i]))['rarity'],
         'goods_rarity': lambda i: pdm.unpack(lg, bytes(x['G'].rows[i]))['rarity']}
    if ctx.S.get('shop_reroll', True) and ctx.item_rand:
        ctx.report.append('商店重抽：随机器开着物品随机，商店已经打乱过了，这里不再换（双子老妪的铃珠货架也就和商人对得上）')
    elif ctx.S.get('shop_reroll', True):
        reroll(ctx, x)
    if ctx.S.get('scarab_ashes', True):
        scarabs(ctx, x)
    x['converted'] = set()
    x['keep_gear'] = set()
    hl = ctx.S.get('hero_armor_loot') or {}
    if hl.get('enabled', True):
        hero_armor_loot(ctx, x, hl)
    if ctx.S.get('no_vanilla_gear', True):
        gear_to_ash(ctx, x)
    sp = ctx.S.get('shop_prices') or {}
    if sp.get('enabled', True):
        prices(ctx, x, sp)
    ml = ctx.S.get('merchant_loot') or {}
    if ml.get('enabled', True):
        merchant_loot(ctx, x, ml)
    ctx.bnd.put('ShopLineupParam.param', x['P'].serialize())


def kind(x, row):
    """这一格能不能换、算哪一类：book / spell / ash / None"""
    g = x['g']
    if g(row, 'mtrlId') != -1 or g(row, 'costType') != 0:
        return None
    et, eid = g(row, 'equipType'), g(row, 'equipId')
    if et == EQUIP_GOODS and eid in x['books']:
        return 'book'
    if et == EQUIP_GOODS and eid in x['M'].rows and eid in x['G'].rows and x['goods_type'](eid) in SPELL_TYPES:
        return 'spell'
    if et == EQUIP_GEM and eid > 0:
        return 'ash'
    return None


def reroll(ctx, x):
    P, g, so, merch = x['P'], x['g'], x['so'], x['merch']
    F0, F1 = sorted((so['eventFlag_forStock'][0], so['eventFlag_forRelease'][0]))
    groups, kinds_of = defaultdict(list), defaultdict(set)
    for rid in sorted(P.rows):
        m = merch.get(str(rid))
        k = kind(x, P.rows[rid]) if m else None
        if k:
            groups[g(P.rows[rid], 'eventFlag_forRelease') != 0].append((rid, m, k))
            kinds_of[m].add(k)
    if not groups:
        ctx.report.append('商店重抽：没找到能换的格子')
        return
    spell_merch = {m for m, ks in kinds_of.items() if ks - {'book'} == {'spell'}}
    rows = sorted(rid for lst in groups.values() for rid, _m, _k in lst)
    key = once.sig(*[struct.pack('<i', r) + bytes(P.rows[r]) for r in rows])
    plan = once.get(ctx, 'shop', key)
    orig = {r: bytes(P.rows[r]) for r in rows}
    fresh = not plan
    if fresh:
        with once.own_rng(ctx, 'shop'):
            plan = {}
            for gated, lst in sorted(groups.items()):
                books = [rid for rid, m, k in lst if k == 'book']
                book_src = books[:]
                ctx.rng.shuffle(book_src)
                lst = [t for t in lst if t[2] != 'book']
                spells = [rid for rid, m, k in lst if k == 'spell']
                others = [rid for rid, m, k in lst if k != 'spell']
                ctx.rng.shuffle(spells)
                dest_spell = [rid for rid, m, k in lst if m in spell_merch]
                dest_other = [rid for rid, m, k in lst if m not in spell_merch]
                rest = spells[len(dest_spell):] + others
                ctx.rng.shuffle(rest)
                for d, s in list(zip(books, book_src)) + list(zip(dest_spell, spells)) + list(zip(dest_other, rest)):
                    plan[str(d)] = [s, g(orig[s], 'equipType'), g(orig[s], 'equipId')]
            # 重复的战灰格换成商店里没有的战灰（全部战灰 = 所有商店行里出现过的 + 原版甲虫掉的）
            all_ash = {g(r, 'equipId') for r in P.rows.values() if g(r, 'equipType') == EQUIP_GEM and g(r, 'equipId') > 0}
            all_ash |= {gem for _r, _i, gem in scarab_rows(ctx)}
            have = Counter(v[2] for v in plan.values() if v[1] == EQUIP_GEM)
            missing = sorted(all_ash - set(have))
            ctx.rng.shuffle(missing)
            dups = [d for d, v in sorted(plan.items()) if v[1] == EQUIP_GEM]
            ctx.rng.shuffle(dups)
            for need in missing:
                d = next((t for t in dups if have[plan[t][2]] > 1), None)
                if d is None:
                    break
                have[plan[d][2]] -= 1
                dups.remove(d)
                plan[d] = [plan[d][0], EQUIP_GEM, need]
                have[need] += 1
        once.put(ctx, 'shop', key, plan)
    R0 = so['eventFlag_forRelease'][0]
    n = 0
    for d, (s, et, eid) in plan.items():
        d, s = int(d), int(s)
        if d not in orig or s not in orig:
            continue
        new = bytearray(orig[s])
        if et == EQUIP_GOODS and eid in x['books']:
            # 制作笔记：原版买到时点亮的配方解锁标记就是这一格的库存标记（eventFlag_forStock = 配方的 eventFlag_forRelease，
            # 地图上的笔记是掉落格的拿过标记），所以库存标记跟着笔记走，只有上架（解锁）标记留在原格子。
            # 以前两个都留在原格子：买到的笔记解锁的是原来那一格那本的配方（道具商店也按配方标记上架），21 本里 20 本对不上
            # （用户 2026-11-12「商店里购买的制作笔记能正确解锁道具商店的道具上架吗」）
            new[R0:R0 + 4] = orig[d][R0:R0 + 4]
        else:
            new[F0:F1 + 4] = orig[d][F0:F1 + 4]           # 售罄 / 解锁标记留在原格子
        struct.pack_into('<' + so['equipType'][1], new, so['equipType'][0], et)
        struct.pack_into('<' + so['equipId'][1], new, so['equipId'][0], eid)
        P.rows[d][:] = new
        n += d != s or eid != g(orig[s], 'equipId')
    cnt = Counter(k for lst in groups.values() for _r, _m, k in lst)
    ctx.report.append('商店重抽（%s）：%d 格法术祷告 / %d 格战灰 / %d 格制作笔记在商人之间互换（%d 格换了东西；专卖法术的商人 %d 个只拿法术）' % (
        '新抽的' if fresh else '沿用第一次抽的', cnt['spell'], cnt['ash'], cnt['book'], n, len(spell_merch)))


def scarab_rows(ctx):
    try:
        return json.load(open(os.path.join(ctx.data_dir, 'scarab_ashes.json'), encoding='utf-8'))['rows']
    except FileNotFoundError:
        return []


def scarabs(ctx, x):
    P, g, merch = x['P'], x['g'], x['merch']
    sc = scarab_rows(ctx)
    # 只改这一格现在就是战灰的：开了物品随机时随机器会把别的东西放到甲虫身上，不能冲掉
    is_gem = lambda r, i: any(k == i and c == LOT_GEM for k, c, _iid, _pt in erlib.lot_slots(ctx.P_mp.rows[r]))
    slots = [(r, i) for r, i, _gem in sc if r in ctx.P_mp.rows and is_gem(r, i)]
    if not slots:
        return
    all_ash, buyable = {gem for _r, _i, gem in sc}, set()
    for rid, row in P.rows.items():
        if g(row, 'equipType') != EQUIP_GEM or g(row, 'equipId') <= 0:
            continue
        all_ash.add(g(row, 'equipId'))
        if (g(row, 'mtrlId') == -1 and g(row, 'costType') == 0 and str(rid) in merch) or (101800 <= rid <= 101999 and g(row, 'mtrlId') != -1):
            buyable.add(g(row, 'equipId'))                # 商人用卢恩买得到 / 追忆换得到
    # 一定要留在甲虫身上的：原本甲虫掉、商店又买不到的（地图上捡的、Boss 给的不用管，原处还有）；其余格子从全部战灰里随机
    must = sorted({gem for _r, _i, gem in sc} - buyable)
    key = once.sig('s3', slots, sorted(all_ash), must)
    plan = once.get(ctx, 'shop_scarab', key)
    fresh = not plan
    if fresh:
        with once.own_rng(ctx, 'shop_scarab'):
            m2, rest, sl = list(must), sorted(all_ash - set(must)), list(slots)
            ctx.rng.shuffle(m2)
            ctx.rng.shuffle(rest)
            ctx.rng.shuffle(sl)
            plan = {'%d:%d' % k: gem for k, gem in zip(sl, m2 + rest)}
        once.put(ctx, 'shop_scarab', key, plan)
    n = 0
    for (r, i) in slots:
        gem = plan.get('%d:%d' % (r, i))
        if gem in all_ash:
            row = ctx.P_mp.rows[r]
            struct.pack_into('<i', row, erlib.LOT_ID + 4 * i, gem)
            struct.pack_into('<i', row, erlib.LOT_CAT + 4 * i, LOT_GEM)
            n += 1
    other = len(sc) - len(slots)
    if other:      # 开了物品随机：随机器在甲虫身上放了别的东西，那几格没改，原本只有甲虫掉的战灰随机器挪到别处了
        ctx.report.append('甲虫掉战灰（%s）：%d 只甲虫掉的本来就是战灰，重新分配；另外 %d 只掉的是随机器放的别的东西（开了物品随机），没改' % (
            '新抽的' if fresh else '沿用第一次抽的', n, other))
    else:
        ctx.report.append('甲虫掉战灰（%s）：%d 只甲虫重新分配战灰，原本只有甲虫掉、商店买不到的 %d 种都还在甲虫身上，其余 %d 只从全部 %d 种战灰里随机' % (
            '新抽的' if fresh else '沿用第一次抽的', n, len(must), max(0, n - len(must)), len(all_ash)))


def gear_to_ash(ctx, x):
    from .unidentified import ammo_ids
    P, g, so = x['P'], x['g'], x['so']
    ammo = ammo_ids(ctx)
    have = {et: erlib.Param(ctx.bnd.get(p + '.param')).rows for et, p in EQUIP_GEAR.items()}
    rows, cur = [], []
    for rid in sorted(P.rows):
        row = P.rows[rid]
        et, eid = g(row, 'equipType'), g(row, 'equipId')
        if rid in x.get('keep_gear', ()):
            continue
        if (et in EQUIP_GEAR and eid in have[et] and not (et == 0 and eid in ammo) and g(row, 'mtrlId') == -1
                and not DARK_SHOP[0] <= rid <= DARK_SHOP[1]):
            if g(row, 'costType') == 0:
                rows.append((rid, et, eid))
            elif rid < TEST_SHOP and not (et == 0 and eid >= OWN_WEAPON):
                # 特殊货币（龙飨祭坛的龙心脏等）的格子：原版只卖道具和战灰，开了物品随机，随机器可能放原版装备进来；
                # 武器 rr/remembrance.py 已经换成成品传说，剩下的（护符、防具、没法换的武器）在这里换战灰（用户 2026-11-02）
                cur.append((rid, et, eid))
    if not rows and not cur:
        return
    sold = {g(r, 'equipId') for r in P.rows.values() if g(r, 'equipType') == EQUIP_GEM and g(r, 'equipId') > 0}
    all_ash = sorted((sold | {gem for _r, _i, gem in scarab_rows(ctx)}) & set(x['Gem'].rows))
    plan, fresh = {}, False
    if rows:
        key = once.sig('g1', rows, all_ash)
        plan = once.get(ctx, 'shop_gear', key)
        fresh = not plan
        if fresh:
            with once.own_rng(ctx, 'shop_gear'):
                missing = sorted(set(all_ash) - sold)
                ctx.rng.shuffle(missing)
                order = [r for r, _et, _eid in rows]
                ctx.rng.shuffle(order)
                plan = {str(r): (missing[k] if k < len(missing) else ctx.rng.choice(all_ash)) for k, r in enumerate(order)}
            # 格子集合变了（比如 2026-11-13 英雄防具改对了货架）：还在的格子沿用上次抽的战灰，只有新格子用新抽的
            prev = once.last(ctx, 'shop_gear') or {}
            ok = set(all_ash)
            plan.update({r: v for r, v in prev.items() if r in plan and v in ok})
            once.put(ctx, 'shop_gear', key, plan)
    if cur:                    # 另记一项：原来那项的指纹不变，商人那边已经抽好的照旧
        key = once.sig('c1', cur, all_ash)
        cplan = once.get(ctx, 'shop_gear_cur', key)
        if not cplan:
            with once.own_rng(ctx, 'shop_gear_cur'):
                cplan = {str(r): ctx.rng.choice(all_ash) for r, _et, _eid in cur}
            once.put(ctx, 'shop_gear_cur', key, cplan)
            fresh = True
        plan = dict(plan, **cplan)
    n = Counter()
    for rid, et, _eid in rows + cur:
        gem = plan.get(str(rid))
        if gem not in x['Gem'].rows:
            continue
        row = P.rows[rid]
        struct.pack_into('<' + so['equipType'][1], row, so['equipType'][0], EQUIP_GEM)
        struct.pack_into('<' + so['equipId'][1], row, so['equipId'][0], gem)
        x['converted'].add(rid)
        n[('武器', '防具', '护符')[et]] += 1
    ctx.report.append('商店不卖原版装备（%s）：%s 换成战灰（%d 种商店原来买不到的先补上）%s' % (
        '新抽的' if fresh else '沿用第一次抽的', ' / '.join('%s %d 格' % kv for kv in sorted(n.items())), len(set(all_ash) - sold),
        '；其中 %d 格是特殊货币的格子（龙飨祭坛等，开了物品随机）：%s' % (len(cur), '、'.join(str(r) for r, _et, _eid in cur)) if cur else ''))


def prices(ctx, x, sp):
    P, g, so = x['P'], x['g'], x['so']
    base = float(sp.get('base', 5000))
    by_rar = {int(k): float(v) for k, v in (sp.get('by_rarity') or {'1': 1.0, '2': 1.5, '3': 2.0}).items()}
    book = float(sp.get('book', 1.0))
    try:                                 # 商人的商店编号段（新加的行不在 shop_merchants.json 里）
        ranges = json.load(open(os.path.join(ctx.data_dir, 'merchant_ranges.json'), encoding='utf-8'))['ranges']
    except FileNotFoundError:
        ranges = []
    in_shop = lambda r: str(r) in x['merch'] or any(lo <= r <= hi for lo, hi in ranges) or r in x.get('converted', ())
    n = Counter()
    for rid in sorted(P.rows):
        row = P.rows[rid]
        k = kind(x, row) if in_shop(rid) else None
        if not k:
            continue
        eid = g(row, 'equipId')
        if k == 'ash':
            if eid not in x['Gem'].rows:
                continue
            mult, name = by_rar.get(x['gem_rarity'](eid), 1.0), '战灰'
        elif k == 'book':
            mult, name = book, '制作笔记'
        else:
            mult, name = by_rar.get(x['goods_rarity'](eid), 1.0), '法术祷告'
        struct.pack_into('<' + so['value'][1], row, so['value'][0], int(round(base * mult / 100.0)) * 100)
        n[name] += 1
    ctx.report.append('商店价格：%s 统一定价（战灰 / 法术祷告按稀有度 %s 卢恩，制作笔记 %d）' % (
        '、'.join('%s %d 格' % kv for kv in sorted(n.items())), ' / '.join('%d' % (base * v) for _k, v in sorted(by_rar.items())), base * book))


# 开局装备编号段（230000000 起每个 1 万号，到容器的 240000000 为止，共 1000 个）里商人的小极品传说武器占 900~999
#（开局装备 0~499，追忆 500~699，支线武器 700~799，大蛇狩猎矛 800，特殊货币格子 810~899；remembrance.layout_check）
MER_OFF, MER_MAX = 900, 100
EQUIP_WEAPON = 0
EQUIP_PROTECTOR = 1


def hero_armor_loot(ctx, x, c):
    """「获得英雄的防具」（恩雅的头目套装商店 HERO_SHOP）里的防具格全换成小极品传说防具（用户 2026-11-08「全放小极品传说」，
    2026-11-13 改对货架）：本体就是原来那件头目防具（不在词条库的本体里才从同部位随机一件），固定种子生成，
    three_affix = true 时强制三词条（防具版小极品）。解锁标记（打败对应头目）、库存标记照旧，每件只卖 1 件，价格 legendary_runes[price_band]。
    在 gear_to_ash 之前调用；换了的格子放进 x['keep_gear']（不换战灰）和 x['hero_rows']（merchant_loot 只占编号、不写）。
    第一版的四件（HERO_OLD，双子老妪）只建参数行、不上架：已经买到的人身上那件照旧。"""
    x['hero_rows'] = set()
    if not getattr(ctx, 'containers', None) or not (ctx.S.get('unidentified') or {}).get('enabled', True):
        ctx.report.append('英雄防具商店：没有新装备系统，没换')
        return
    P, g, so = x['P'], x['g'], x['so']
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    _wb, pb, nm = affixes.bases(ctx, lib)
    slot_of = {int(b['id']): int(b['slot']) for b in pb}
    by_slot = defaultdict(list)
    for b in pb:
        by_slot[int(b['slot'])].append(int(b['id']))
    Pp = erlib.Param(ctx.bnd.get('EquipParamProtector.param'))
    pl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamProtector.xml')))[0]}
    cat_of = lambda i: struct.unpack_from('<' + pl['protectorCategory'][1], Pp.rows[i], pl['protectorCategory'][2])[0]
    rows = []                                          # (格子, 原来的防具, 部位)
    for rid in sorted(P.rows):
        if not HERO_SHOP[0] <= rid <= HERO_SHOP[1] or g(P.rows[rid], 'equipType') != EQUIP_PROTECTOR:
            continue
        orig = g(P.rows[rid], 'equipId')
        slot = slot_of.get(orig, cat_of(orig) if orig in Pp.rows else -1)
        if by_slot.get(slot):
            rows.append((rid, orig, slot))
    if not rows:
        ctx.report.append('英雄防具商店：没找到防具格')
        return
    if len(rows) > HERO_SHOP_MAX:
        raise RuntimeError('英雄防具商店：%d 格，编号段只放得下 %d 件' % (len(rows), HERO_SHOP_MAX))
    ml = ctx.S.get('merchant_loot') or {}
    price_band = int(c.get('price_band', 1))
    prices = [int(v) for v in (ml.get('legendary_runes') or [50000])]
    price = prices[min(price_band, len(prices) - 1)]
    full = bool(c.get('three_affix', True))
    key = once.sig('h2', rows, price, full)
    plan = once.get(ctx, 'hero_armor_loot', key)
    fresh = not (plan and all(str(r) in plan and plan[str(r)][0] in slot_of for r, _o, _s in rows))
    if fresh:
        with once.own_rng(ctx, 'hero_armor_loot'):
            plan = {str(r): [o if o in slot_of else ctx.rng.choice(by_slot[s]), ctx.rng.getrandbits(62)] for r, o, s in rows}
        once.put(ctx, 'hero_armor_loot', key, plan)
    if not hasattr(ctx, 'start_ids'):
        ctx.start_ids = (startgear.START_W0, 10000, startgear.START_P0, 100)
    if not hasattr(ctx, 'start_items'):
        ctx.start_items = []
    first, step = ctx.start_ids[2], ctx.start_ids[3]
    p_ids, names, n_kept = [], [], 0
    for j, (r, orig, _slot) in enumerate(rows):
        base, seed = plan[str(r)]
        n_kept += int(base) == orig
        i = first + (HERO_SHOP_OFF + j) * step
        if i in Pp.rows:
            raise RuntimeError('英雄防具商店：生成防具编号 %d 已被占用' % i)
        Pp.add_row(i, bytes(Pp.rows[int(base)]))
        row = P.rows[r]
        struct.pack_into('<' + so['equipType'][1], row, so['equipType'][0], EQUIP_PROTECTOR)
        struct.pack_into('<' + so['equipId'][1], row, so['equipId'][0], i)
        struct.pack_into('<' + so['sellQuantity'][1], row, so['sellQuantity'][0], 1)
        struct.pack_into('<' + so['value'][1], row, so['value'][0], price)
        ctx.start_items.append({'cat': 1, 'id': i, 'tier': 3, 'base': int(base), 'seed': int(seed), 'maxreq': [99] * 5,
                                'top': 100, 'min_status': 0, 'keep': False, 'full': full})
        x['keep_gear'].add(r)
        x['hero_rows'].add(r)
        p_ids.append(i)
        names.append(nm('zh', 'ProtectorName', int(base)))
    # 第一版的四件：参数行照原来双子老妪那格的防具复制（运行时按角色记录里的本体重写），不上架、不发 start 行
    old = []
    for j, (r, _slot) in enumerate(sorted(HERO_OLD.items())):
        i = first + (HERO_P_OFF + j) * step
        src = g(P.rows[r], 'equipId') if r in P.rows and g(P.rows[r], 'equipType') == EQUIP_PROTECTOR else 0
        if src not in Pp.rows:                    # 开了物品随机那格不是防具：随便拿一件同部位的占位
            src = by_slot[HERO_OLD[r]][0] if by_slot.get(HERO_OLD[r]) else 0
        if i in Pp.rows or src not in Pp.rows:
            continue
        Pp.add_row(i, bytes(Pp.rows[src]))
        old.append(i)
    ctx.bnd.put('EquipParamProtector.param', Pp.serialize())
    startgear.placeholders(ctx, [], p_ids + old)
    ctx.report.append('英雄防具商店（%s）：%d 格 → 小极品传说防具 %d 件（%s三词条，%d 卢恩 / 件，打败对应头目才卖；本体照原来的 %d 件，'
                      '其余同部位随机；生成要 dll\\dark_core）：%s%s' % (
                          '新抽的' if fresh else '沿用第一次抽的', len(rows), len(p_ids), '强制' if full else '按稀有度', price, n_kept,
                          '、'.join(names), '；第一版的 %d 件只留编号' % len(old) if old else ''))


def merchant_loot(ctx, x, c):
    """商人的战灰格换成这个地区的未鉴定物品和小极品传说武器（用户 2026-11-01：战灰在暗黑商店都能买了，商人卖的没用了）。
    只换有名字的商人（data/shop_merchants.json，地区档位在 data/merchant_tiers.json）用卢恩买、限量的战灰格（含原版装备换来的）；
    售罄 / 解锁标记留在原格子（艾尼亚那些打败 Boss 才卖的照样打败才卖）。每个商人：
      - max(1, round(格数 × legendary_share)) 格换成小极品传说武器：成品传说（DLC 的地区是传说（幽影之地）），本体按词条库传说武器的类型分布随机，
        补正先按原版比例定几项（全能约一成）、再在这个项数里取分布前 scaling_top_pct%（全能和别的项数分开算，不会全是全能；
        dll\\dark_core 按种子生成，同追忆武器，items.txt 的 start 行 full = 1），只卖 1 把，价格 legendary_runes[档]；
      - 其余换成未鉴定物品：稀有度按 rarity_weights[档]、类别按 gear_category_share，数量照原格子，价格 unidentified_runes[稀有度]（DLC 档 × dlc_runes_mult）。
    一次性重随（shop_loot）：第一次抽了以后照旧，点「一次性重随」才重抽。没有新装备系统的容器 / 未鉴定物品就不换"""
    if not getattr(ctx, 'containers', None) or not (ctx.S.get('unidentified') or {}).get('enabled', True):
        ctx.report.append('商人的战灰格：没有新装备系统，没换')
        return
    P, g, so, merch = x['P'], x['g'], x['so'], x['merch']
    tiers = json.load(open(os.path.join(ctx.data_dir, 'merchant_tiers.json'), encoding='utf-8'))['merchants']
    bands = ctx.S.get('tier_bands') or []
    dlc = {k for k, b in enumerate(bands) if int(b.get('max_tier', 0)) > 20}       # 流程等级 20 以上是 DLC（同许愿）
    Gd = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    slots, skipped = defaultdict(list), Counter()
    # 英雄防具的格子（hero_armor_loot 换成了小极品防具）照旧算进来、只占编号不写：2026-11-13 以前它们被当成恩雅的战灰格抽过，
    # 算进来这份抽签的指纹和编号才不变（别的商人已经抽好的照旧，已经买到的小极品武器编号不变）。
    # 第一版英雄防具误改的双子老妪四格（HERO_OLD）以前不在这里，现在也不进来（同样为了指纹不变），换成战灰照常卖
    hero = x.get('hero_rows') or set()
    for rid in sorted(P.rows):
        row = P.rows[rid]
        m = merch.get(str(rid))
        if rid in HERO_OLD or not m or not (rid in hero or kind(x, row) == 'ash') or g(row, 'sellQuantity') <= 0 or not g(row, 'eventFlag_forStock'):
            continue
        if m not in tiers:
            skipped[m] += 1
            continue
        slots[m].append(rid)
    if not slots:
        ctx.report.append('商人的战灰格：没找到能换的格子')
        return
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    wb, _pb, nm = affixes.bases(ctx, lib)
    by_type = defaultdict(list)
    for b in wb:
        by_type[int(b['type'])].append(b['id'])
    wtypes = {int(t): w for t, w in lib['weapon']['types']['Legendary'].items() if int(t) in by_type and w > 0}
    share = float(c.get('legendary_share', 0.2))
    weights = c.get('rarity_weights') or []
    cat_share = ctx.S.get('gear_category_share') or {'weapon': 30, 'armor': 60, 'talisman': 10}
    all_rows = sorted(r for lst in slots.values() for r in lst)
    key = once.sig('l1', [(r, merch[str(r)], tiers[merch[str(r)]]) for r in all_rows], share, weights, cat_share)
    plan = once.get(ctx, 'shop_loot', key)
    ok_w = {b['id'] for b in wb}
    fresh = not (plan and all(str(r) in plan for r in all_rows)
                 and all(v[0] != 'w' or v[1] in ok_w for v in plan.values()))
    if fresh:
        with once.own_rng(ctx, 'shop_loot'):
            pick = lambda d: ctx.rng.choices(list(d), weights=list(d.values()))[0]
            plan = {}
            for m in sorted(slots):
                lst = list(slots[m])
                ctx.rng.shuffle(lst)
                band = int(tiers[m])
                k = min(len(lst), max(1, int(round(len(lst) * share))))
                for r in lst[:k]:
                    t = pick(wtypes)
                    plan[str(r)] = ['w', ctx.rng.choice(sorted(by_type[t])), ctx.rng.getrandbits(62)]
                wt = weights[min(band, len(weights) - 1)] if weights else {'Rare': 1}
                for r in lst[k:]:
                    rar = pick({kk: v for kk, v in wt.items() if v > 0})
                    plan[str(r)] = ['u', pick({kk: v for kk, v in cat_share.items() if v > 0}), rar]
        once.put(ctx, 'shop_loot', key, plan)
    # 写商店行
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    wf = json.load(open(os.path.join(ctx.data_dir, 'weapon_fields.json'), encoding='utf-8'))
    origin = [(o, sz) for f, o, sz in wf['own'] if f.startswith('originEquipWep')]
    if not hasattr(ctx, 'start_ids'):
        ctx.start_ids = (startgear.START_W0, 10000, startgear.START_P0, 100)
    if not hasattr(ctx, 'start_items'):
        ctx.start_items = []
    first, step = ctx.start_ids[0], ctx.start_ids[1]
    leg_runes = [int(v) for v in (c.get('legendary_runes') or [50000])]
    u_runes = c.get('unidentified_runes') or {}
    dlc_mult = float(c.get('dlc_runes_mult', 1.5))
    top = int(c.get('scaling_top_pct', 50))
    put = lambda row, f, v: struct.pack_into('<' + so[f][1], row, so[f][0], v)
    w_ids, n_u, n_w, names, n_hero = [], Counter(), Counter(), [], 0
    wrows = sorted(rr for rr in all_rows if plan[str(rr)][0] == 'w')
    if len(wrows) > MER_MAX:
        raise RuntimeError('商人的小极品传说武器 %d 把，编号段只放得下 %d 把（调小 merchant_loot.legendary_share）' % (len(wrows), MER_MAX))
    for j, r in enumerate(wrows):
        _k, base, seed = plan[str(r)]
        band = int(tiers[merch[str(r)]])
        i = first + (MER_OFF + j) * step
        if i in W.rows:
            raise RuntimeError('商人的小极品传说武器：编号 %d 已被占用' % i)
        startgear.copy_weapon(W, origin, base, i)
        ctx.start_items.append({'cat': 0, 'id': i, 'tier': 4 if band in dlc else 3, 'base': base, 'seed': int(seed), 'maxreq': [99] * 5,
                                'top': top, 'min_status': 0, 'keep': False, 'full': True})
        w_ids.append(i)
        if r in hero:              # 英雄防具格：武器只建出来（以前在这格买到的照旧），格子卖的是小极品防具
            n_hero += 1
            continue
        row = P.rows[r]
        put(row, 'equipType', EQUIP_WEAPON)
        put(row, 'equipId', i)
        put(row, 'sellQuantity', 1)
        put(row, 'value', leg_runes[min(band, len(leg_runes) - 1)])
        n_w[band] += 1
        names.append('%s（%s）' % (nm('zh', 'WeaponName', base), merch[str(r)]))
    for r in all_rows:
        v = plan[str(r)]
        if v[0] != 'u' or r in hero:
            continue
        band = int(tiers[merch[str(r)]])
        cat = unidentified.CATS.index(v[1])
        tier = unidentified.TIERS.index('LegendaryDLC' if v[2] == 'Legendary' and band in dlc else v[2])
        gid = unidentified.goods_id(cat, tier)
        if gid not in Gd.rows:
            continue
        row = P.rows[r]
        put(row, 'equipType', EQUIP_GOODS)
        put(row, 'equipId', gid)
        put(row, 'value', int(round(int(u_runes.get(v[2], 10000)) * (dlc_mult if band in dlc else 1.0) / 100.0)) * 100)
        n_u[v[2]] += 1
    ctx.bnd.put('EquipParamWeapon.param', W.serialize())
    startgear.placeholders(ctx, w_ids, [])
    ctx.report.append('商人的战灰格（%s）：%d 个商人的 %d 格 → 小极品传说武器 %d 把（补正前 %d%%，全能按原版比例、和别的项数分开算，卢恩 %s；生成要 dll\\dark_core）、'
                      '未鉴定物品 %d 格（%s，卢恩 %s）%s' % (
                          '新抽的' if fresh else '沿用第一次抽的', len(slots), len(all_rows), len(w_ids) - n_hero, top, '/'.join(map(str, leg_runes)),
                          sum(n_u.values()), ' / '.join('%s %d' % (RAR_ZH[k], n_u[k]) for k in RAR if n_u[k]),
                          ' / '.join('%s %s' % (RAR_ZH[k], u_runes[k]) for k in RAR if k in u_runes),
                          ('；没在地区表里、没换的商人：%s' % '、'.join('%s %d 格' % kv for kv in sorted(skipped.items())) if skipped else '') +
                          ('；英雄防具的 %d 格只占编号（卖的是小极品防具，以前在这几格抽到的武器 %d 把只建出来）' % (len(hero & set(all_rows)), n_hero) if hero & set(all_rows) else '')))
    ctx.report.append('商人的小极品传说武器：' + '、'.join(names))
