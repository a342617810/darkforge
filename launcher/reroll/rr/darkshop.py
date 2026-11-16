# -*- coding: utf-8 -*-
"""暗黑商店的商店行（赐福「更多选项」→「暗黑商店」的菜单在 sc/darkshop.py；settings 的 dark_shop）：
  护符商店 TAL_SHOP：词条库的护符模板（EquipParamAccessory 9000 起，每种词条 普通 / 稀有 / 史诗 各一件），龙心脏。
      游戏脚本用龙飨祭坛的商店界面打开，页面里显示持有的龙心脏（模板的名字 / 简介 / 说明是 affixes.build 写的）
  武器商店：近战武器 / 远程武器（弓、弩、法杖、圣印记）/ 盾牌（含火把）三个商店（按武器的 weaponCategory 分，同置物包的分类），
      每种武器类型 普通 / 稀有 / 史诗 各一行，卢恩。参数里先放这类型的原版武器（三把不同的）占位，
      items.txt 的 wshop 行告诉 dll\\dark_core 每行的类型和稀有度：进存档时每格生成一把换上去，买走了换新的。
      商店的「武器」分类页会按类型换行，「全部道具」页不会（游戏本身这样）
  魔法 / 祷告商店 SPELL_SHOPS：原版所有的魔法（goodsType 5 / 17）、祷告（16 / 18），星光碎片，按物品稀有度定价（spell_shards，
      用户 2026-10-29：稀有 3 / 史诗 6 / 传说 9）；游戏脚本用瑟濂卖傀儡的商店界面打开（1:144，页面里显示持有的星光碎片）；
      用户 2026-11-05「魔法祷告商店改为开局就解锁 开局解锁的只售卖基础法术祷告 然后之后保持按地区解锁」：spell_release_flag = 0，菜单项一开始就有，
      basic_spells（开局职业自带的那些）一开始就卖、每个 basic_spell_shards 个星光碎片（用户 2026-11-05「改为1个碎片吧」，其他法术最低 2 个），其余按区域；
      以前是打败满月女王蕾娜菈（RENNALA_DEFEATED，用户 2026-11-01）才上架
  道具商店 ITEM_SHOP：每个制作配方的产物一行，捡到对应的制作笔记（配方的解锁标记）才上架，不限量，卢恩；价格 data/item_shop.json
  回购商店 BUYBACK_SHOP：最后卖掉的 BUYBACK_N 件生成装备（空行，dll\\dark_core 按这个角色的记录改写、点亮标记），卢恩
  战灰商店 ASH_SHOP（用户 2026-10-30）：原版所有战灰（照「复制战灰」的原版清单 data/ash_dup_lineup.json，本体 + DLC，唤声船这种自制的不在里面），
      不限量，龙心脏，价格统一 ash_hearts（默认 3）；游戏脚本和护符商店一样用龙飨祭坛的界面打开；
      后面接专属战技战灰（rr/skillgems.py，用户 2026-11-03；价格 skill_gems.hearts，默认同 ash_hearts）；
      打败葛瑞克（ash_release_flag，默认 GODRICK_DEFEATED）才上架，菜单项也是那时才出现（sc/darkshop.py）
分阶段解锁（dark_shop.staged，用户 2026-11-04「当玩家击败该区域的追忆boss后才解锁原版在该区域能拿到的所有战灰魔法祷告以及箭矢道具」）：
  战灰、魔法 / 祷告、箭矢每一行的上架标记换成「原版最早能拿到它的区域」的追忆 Boss 击败标记（data\\shop_regions.json，
  dev\\item_system\\build_shop_regions.py 生成；21 个区域，用户选的草案）。专属战技战灰跟着它的武器本体所在区域；
  找不到区域的（原版只在开局职业身上的战灰等）跟第一个区域（葛瑞克）。箭矢：basic_arrows 一开始就卖；有区域的按区域；
  没区域、有制作配方的照旧捡到制作笔记才上架（兽骨箭这类）；都没有的跟第一个区域。可制作的道具照旧按制作笔记（用户选的）。
  战灰商店的菜单项在第一个区域的 Boss 打败后出现，魔法 / 祷告商店一开始就有。打败一个区域的 Boss、这个区域有新东西上架时，
  dll\\dark_core（shopstage.rs，定义 stage_lines → shopstage.txt）弹原版闪烁提示「暗黑商店已经可以购买新物品」（rr/notes.py 的 shop）。
各商店每一行都写上页面标题（menuTitleMsgId，文字在 menu 文字包的 GR_MenuText，sc/darkshop.py 写）。
龙飨界面（护符商店）只按物品的 sortId 排：护符模板的 sortId 按词条排（extract_affixes.py 的 sort_templates），同一词条的三件挨着"""
import base64

from .common import *  # noqa: F401,F403

TAL_SHOP = (114000, 114999)
WPN_SHOPS = {'melee': (115000, 115399), 'ranged': (115400, 115699), 'shield': (115700, 115999)}
ITEM_SHOP = (116000, 116999)
SPELL_SHOPS = {'sorcery': (118000, 118499), 'incant': (118500, 118999)}
SPELL_TYPES = {'sorcery': (5, 17), 'incant': (16, 18)}     # goodsType：魔法、辅助魔法 / 祷告、辅助祷告
SPELL_RAR = {1: 'Rare', 2: 'Epic', 3: 'Legendary'}        # 法术的 rarity（0 的是测试用的 [ERROR] 行）
# 回购商店（用户 2026-10-28）：最后卖掉（不在背包 / 仓库里了）的 BUYBACK_N 件生成装备，按卖出价买回。这里只建空行：
# 每格有自己的上架标记（有东西才点亮，没点亮的格子不显示）和卖完标记（数量 1，买了游戏点亮）；放什么、价格、标记都由 dll\dark_core 按记录改
BUYBACK_SHOP, BUYBACK_N = 117000, 50
# 上架标记 50 个；库存计数（eventFlag_forStock 是多位计数，原版每格隔 10 号）挨着放，DLL 每次整段清零，所以留到 STOCK0 + N + 9
BUYBACK_REL0, BUYBACK_STOCK0 = 93505, 93555      # 93505~93554 / 93555~93613（dev\event_flags\说明.md）
ASH_SHOP = (119000, 119299)
GODRICK_DEFEATED = 10000800      # 战灰商店的上架标记：打败葛瑞克（史东薇尔城的 Boss 位置；原版赐福事件 9005810 用的击败标记，用户 2026-10-30）
RENNALA_DEFEATED = 14000800      # 魔法 / 祷告商店的上架标记：打败满月女王蕾娜菈（二阶段，雷亚卢卡利亚学院的 Boss 位置；用户 2026-11-01）
TITLE = {'talisman': 80090011, 'melee': 80090014, 'ranged': 80090015, 'shield': 80090016, 'item': 80090013,
         'buyback': 80090017, 'sorcery': 80090052, 'incant': 80090053, 'ash': 80090054}   # GR_MenuText 里的页面标题
RANGED_CAT, SHIELD_CAT = {8, 10, 11}, {12}       # weaponCategory：法杖 / 圣印记 8、弓 10、弩 / 弩炮 11；盾牌和火把 12；其余近战
SHOP_RAR = ('Common', 'Rare', 'Epic')
EQUIP_WEAPON, EQUIP_ACCESSORY, EQUIP_GOODS, EQUIP_GEM = 0, 2, 3, 4
COST_RUNE, COST_HEART, COST_SHARD = 0, 1, 2      # 卢恩、龙心脏、星光碎片（原版瑟濂的傀儡）


def cfg(S):
    c = S.get('dark_shop') or {}
    return c if c.get('enabled', True) else None


BASIC_ARROWS = (50000000, 51000000, 52000000, 53000000)   # 箭矢、大箭、弩箭、弩炮箭（一开始就卖，用户 2026-11-04）
# 基础法术祷告（一开始就卖，用户 2026-11-05）= 原版开局职业（CharaInitParam 3000~3009）自带的：辉石魔砾、辉石弯弧、魔法辉剑、燃火、紧急恢复、恢复、刺客步法
BASIC_SPELLS = (4000, 4070, 4390, 6000, 6420, 6421, 6510)
BASIC_SPELL_SHARDS = 1


def staged_cfg(S):
    """分阶段解锁的设置（dark_shop.staged）；关了是 None"""
    c = (cfg(S) or {}).get('staged') or {}
    if cfg(S) is None or not c.get('enabled', True):
        return None
    return dict(basic_arrows=list(c.get('basic_arrows', BASIC_ARROWS)), basic_spells=list(c.get('basic_spells', BASIC_SPELLS)))


# 各阶段的解锁标记：追忆 Boss 击败标记 → 它掉落行的获取标记（用户 2026-11-06「进入高难后 boss 复活导致战灰商店重新被锁」）。
# 进「死亡」和赐福「头目复活」都会熄灭击败标记（sc/difficulty.py revive_flags），商店跟着上锁；获取标记不熄灭，老存档打过的也亮着。
# 都核对过不在复活清单里（scratch unlock_check），原版、随机器、重随后的掉落行上一样。蕾娜菈的掉落标记 197 在清单里，
# 所以用她掉落链上只点标记的那一行 10182 的 177（计入大卢恩的那个）。这次的掉落表里找不到的（比如开了物品随机改了标记）照旧用击败标记。
STAGE_UNLOCK = {10000800: 510010, 14000800: 177, 1252380800: 510300, 12090800: 510330, 11000800: 510040, 12030850: 510110, 16000800: 510220,
                12040800: 510080, 1052520800: 510310, 13000800: 510160, 11050800: 510070, 12050800: 510120, 15000800: 510200, 20000800: 510400,
                2048440800: 510900, 22000800: 510480, 21010800: 510460, 2044450800: 510600, 28000800: 510560, 25000800: 510550, 20010800: 510430}


class Stages:
    """data\\shop_regions.json：阶段（追忆 Boss 击败标记）和每件东西最早的阶段；统计每个阶段上架了几件"""

    def __init__(self, ctx, c):
        d = json.load(open(os.path.join(ctx.data_dir, 'shop_regions.json'), encoding='utf-8'))
        self.stages = d['stages']
        self.items = d['items']
        have = {erlib.lot_flag(r) for r in ctx.P_mp.rows.values()}
        self.unlock = [STAGE_UNLOCK.get(int(s['flag']), int(s['flag'])) for s in self.stages]
        self.unlock = [u if u in have else int(s['flag']) for u, s in zip(self.unlock, self.stages)]
        kept = [s['key'] for u, s in zip(self.unlock, self.stages) if u == int(s['flag'])]
        if kept:
            ctx.report.append('暗黑商店分阶段解锁：这些区域找不到掉落的获取标记，照旧看击败标记（Boss 复活后会重新上锁）：%s' % '、'.join(kept))
        self.basic = set(int(x) for x in c['basic_arrows'])
        self.basic_spells = set(int(x) for x in c['basic_spells'])
        self.count = [0] * len(self.stages)
        self.fallback = 0

    def stage(self, equip_type, equip_id):
        k = self.items.get('%d:%d' % (equip_type, equip_id // 10000 * 10000 if equip_type == EQUIP_WEAPON else equip_id))
        return None if k is None else int(k)

    def flag(self, k):
        """阶段 k 的上架标记（k = None：找不到区域，跟第一个区域）"""
        if k is None:
            self.fallback += 1
            k = 0
        self.count[k] += 1
        return self.unlock[k]

    def first(self):
        return self.unlock[0]


def build(ctx):
    """要在 affixes.build 之后（护符模板这时才在 regulation 里）"""
    c = cfg(ctx.S)
    if c is None:
        return
    bnd = ctx.bnd
    sl, ssz = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'ShopLineupParam.xml')))
    so = {nm: (off, fc) for nm, fc, off, bp, bits, d in sl if not bits}
    P_s = erlib.Param(bnd.get('ShopLineupParam.param'))
    if ssz != P_s.row_size:
        raise RuntimeError('ShopLineupParam 行大小与字段表不符')
    for lo, hi in (TAL_SHOP, ITEM_SHOP, ASH_SHOP, (BUYBACK_SHOP, BUYBACK_SHOP + BUYBACK_N - 1)) + tuple(WPN_SHOPS.values()) + tuple(SPELL_SHOPS.values()):
        used = [k for k in P_s.rows if lo <= k <= hi]
        if used:
            raise RuntimeError('暗黑商店的商店行 %s 已被占用' % used[:5])
    tmpl = bytes(P_s.rows[min(P_s.rows)])

    def row(equip_id, equip_type, cost_type, price, title, flag=0):
        r = bytearray(tmpl)
        vals = {'equipId': equip_id, 'value': price, 'mtrlId': -1, 'eventFlag_forStock': 0, 'eventFlag_forRelease': flag,
                'sellQuantity': -1, 'equipType': equip_type, 'costType': cost_type, 'setNum': 1, 'value_Add': 0,
                'value_Magnification': 1.0, 'iconId': -1, 'nameMsgId': -1, 'menuTitleMsgId': title, 'menuIconId': -1}
        for f, v in vals.items():
            off, fc = so[f]
            struct.pack_into('<' + fc, r, off, v)
        return bytes(r)

    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    sc = staged_cfg(ctx.S)
    ctx.shop_stages = Stages(ctx, sc) if sc else None
    n = {}
    n['talisman'] = talisman_shop(ctx, lib, c, P_s, row)
    n.update(weapon_shops(ctx, lib, c, P_s, row))
    n.update(spell_shops(ctx, c, P_s, row))
    n['item'] = item_shop(ctx, P_s, row)
    n['buyback'] = buyback_shop(ctx, c, P_s, row, so)
    n['ash'] = ash_shop(ctx, c, P_s, row)
    bnd.put('ShopLineupParam.param', P_s.serialize())
    ranges = dict(WPN_SHOPS, **SPELL_SHOPS, talisman=TAL_SHOP, item=ITEM_SHOP, buyback=(BUYBACK_SHOP, BUYBACK_SHOP + BUYBACK_N - 1), ash=ASH_SHOP)
    ctx.features['dark_shop'] = {k: [ranges[k][0], ranges[k][0] + n[k] - 1] for k in n if n[k]}
    ctx.features['dark_shop']['titles'] = {k: TITLE[k] for k in n if n[k]}
    ctx.features['dark_shop']['talisman_dragon_ui'] = bool(c.get('talisman_dragon_ui', True))
    ctx.features['dark_shop']['spell_shard_ui'] = bool(c.get('spell_shard_ui', True))
    if n['ash']:
        ctx.features['dark_shop']['ash_release'] = ctx.ash_release
    if n.get('sorcery') or n.get('incant'):
        ctx.features['dark_shop']['spell_release'] = ctx.spell_release
    ctx.report.append('暗黑商店：护符 %d 件（%d 种词条 × 普通 / 稀有 / 史诗，龙心脏 %s）、近战 / 远程 / 盾牌武器 %d / %d / %d 把'
                      '（每种类型三把原版武器，卢恩 %s；进游戏换成生成的要 dll\\dark_core）、魔法 %d / 祷告 %d 个（星光碎片 %s，上架标记 %s）、道具 %d 种（制作配方的产物）、回购 %d 格' % (
                          n['talisman'], n['talisman'] // len(SHOP_RAR), '/'.join(str(price(c, 'talisman_hearts', r)) for r in SHOP_RAR),
                          n['melee'], n['ranged'], n['shield'], '/'.join(str(price(c, 'weapon_runes', r)) for r in SHOP_RAR),
                          n.get('sorcery', 0), n.get('incant', 0), '/'.join(str(price(c, 'spell_shards', r)) for r in SPELL_RAR.values()),
                          getattr(ctx, 'spell_release', 0), n['item'], n['buyback']))
    if n['ash']:
        ctx.report.append('暗黑商店：战灰 %d 种（不限量，龙心脏 %d，上架标记 %d%s）' % (n['ash'], int(c.get('ash_hearts', 3)), ctx.ash_release,
                          '；其中专属战技战灰 %d 种，龙心脏 %d' % ctx.ash_uniq if ctx.ash_uniq[0] else ''))
    st = ctx.shop_stages
    if st:
        ctx.report.append('暗黑商店分阶段解锁（战灰、魔法 / 祷告、箭矢，按原版最早能拿到的区域的追忆 Boss）：%s；找不到区域、跟第一个区域的 %d 件；'
                          '一开始就卖的箭 %d 种' % ('，'.join('%s（%s）%d' % (x['zh'], x['boss'], n_) for x, n_ in zip(st.stages, st.count) if n_),
                                            st.fallback, len(st.basic)))


def stage_lines(ctx):
    """dll\\dark_core\\shopstage.txt（格式见 dark_core 的 shopstage.rs）：note 提示的键；gate 有东西上架的阶段的击败标记 区域名"""
    st = getattr(ctx, 'shop_stages', None)
    if not st or not getattr(ctx, 'notes', None) or not any(k == 'shop' for k, _z, _e in ctx.notes):
        return []
    return ['note shop'] + ['gate %d %s' % (u, x['key']) for u, x, n_ in zip(st.unlock, st.stages, st.count) if n_]


def ash_dup_lines(ctx):
    """dll\\dark_sell\\ash_dup.txt：「战灰编号<TAB>解锁标记」（原版「复制战灰」清单 112000~ 每格的 eventFlag_forRelease，65810~65934，一种战灰一个标记）。
    原版按「这种战灰原来在哪拿」点亮标记，现在那些商店格、光点都换了，战灰又多从暗黑商店买，清单和实际拥有的对不上（用户 2026-11-09）；
    dark_sell 按背包和仓库里实际有的战灰每 2 秒开关这些标记"""
    lay = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'ShopLineupParam.xml')))[0]
    src = json.load(open(os.path.join(ctx.data_dir, 'ash_dup_lineup.json'), encoding='utf-8'))['rows']
    G = erlib.Param(ctx.bnd.get('EquipParamGem.param'))
    rows = (pdm.unpack(lay, base64.b64decode(src[k])) for k in sorted(src, key=int))
    return ['%d\t%d' % (u['equipId'], u['eventFlag_forRelease']) for u in rows if u['equipType'] == EQUIP_GEM and u['equipId'] in G.rows]


def ash_shop(ctx, c, P_s, row):
    """战灰商店：原版「复制战灰」清单里的战灰（这次 regulation 里有的），一种一行，不限量，龙心脏 ash_hearts 个"""
    if not c.get('ash_shop', True):
        return 0
    lay = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'ShopLineupParam.xml')))[0]
    src = json.load(open(os.path.join(ctx.data_dir, 'ash_dup_lineup.json'), encoding='utf-8'))['rows']
    G = erlib.Param(ctx.bnd.get('EquipParamGem.param'))
    gems = []
    for k in sorted(src, key=int):
        u = pdm.unpack(lay, base64.b64decode(src[k]))
        if u['equipType'] == EQUIP_GEM and u['equipId'] in G.rows and u['equipId'] not in gems:
            gems.append(u['equipId'])
    uniq = [g for g in getattr(ctx, 'skill_gems', None) or [] if g in G.rows]      # 专属战技战灰（rr/skillgems.py）接在后面
    if len(gems) + len(uniq) > ASH_SHOP[1] - ASH_SHOP[0] + 1:
        raise RuntimeError('战灰商店：%d 种战灰放不下（%d~%d）' % (len(gems) + len(uniq), *ASH_SHOP))
    price = int(c.get('ash_hearts', 3))
    uprice = int((ctx.S.get('skill_gems') or {}).get('hearts', price))
    release = int(c.get('ash_release_flag', GODRICK_DEFEATED))
    st = getattr(ctx, 'shop_stages', None)
    if st:
        # 分阶段：原版战灰按自己最早的区域；专属战技战灰按它的武器本体最早的区域（rr/skillgems.py 的 weapons）
        weap = {s['gem']: s['weapons'] for s in (getattr(ctx, 'skill_gem_info', None) or [])}
        release = st.first()

        def flag_of(g):
            if g in uniq:
                ks = [st.stage(EQUIP_WEAPON, w) for w in weap.get(g, [])]
                ks = [k for k in ks if k is not None]
                return st.flag(min(ks) if ks else None)
            return st.flag(st.stage(EQUIP_GEM, g))
    else:
        flag_of = lambda g: release
    for j, (g, p) in enumerate([(g, price) for g in gems] + [(g, uprice) for g in uniq]):
        P_s.add_row(ASH_SHOP[0] + j, row(g, EQUIP_GEM, COST_HEART, p, TITLE['ash'], flag_of(g)))
    ctx.ash_release = release
    ctx.ash_uniq = (len(uniq), uprice)
    return len(gems) + len(uniq)


def buyback_shop(ctx, c, P_s, row, so):
    """回购商店的空行（没有新装备系统的容器就不建）；ctx.buyback = (第一行, 行数, 上架标记起, 卖完标记起) 给 items.txt"""
    cont = getattr(ctx, 'containers', None)
    if not c.get('buyback', True) or not cont or not cont['ids']['w']:
        return 0
    for k in range(BUYBACK_N):
        r = bytearray(row(cont['ids']['w'][0], EQUIP_WEAPON, COST_RUNE, 0, TITLE['buyback'], BUYBACK_REL0 + k))
        for f, v in (('sellQuantity', 1), ('eventFlag_forStock', BUYBACK_STOCK0 + k)):
            struct.pack_into('<' + so[f][1], r, so[f][0], v)
        P_s.add_row(BUYBACK_SHOP + k, bytes(r))
    ctx.buyback = (BUYBACK_SHOP, BUYBACK_N, BUYBACK_REL0, BUYBACK_STOCK0)
    return BUYBACK_N


def price(c, key, r):
    dflt = {'talisman_hearts': {'Common': 2, 'Rare': 4, 'Epic': 6}, 'weapon_runes': {'Common': 5000, 'Rare': 15000, 'Epic': 50000},
            'spell_shards': {'Rare': 2, 'Epic': 4, 'Legendary': 6}}
    return int((c.get(key) or {}).get(r, dflt[key][r]))


def spell_shops(ctx, c, P_s, row):
    """魔法 / 祷告商店：原版所有的法术（不算测试用的：稀有度 0、sortGroupId 255），星光碎片，按法术的稀有度定价。返回 {商店: 行数}"""
    if not c.get('spell_shops', True):
        return {}
    Gp = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    gl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))[0]}
    g = lambda row_, f: struct.unpack_from('<' + gl[f][1], row_, gl[f][2])[0]
    n = {k: 0 for k in SPELL_SHOPS}
    release = int(c.get('spell_release_flag', 0))
    st = getattr(ctx, 'shop_stages', None)
    k0 = 0
    if st and release:
        # 分阶段（同战灰商店：每一行按自己最早的区域）。写了 spell_release_flag 的：菜单项在那一档出现，比它早的区域的法术也等到那一档
        # （2026-11-04 是蕾娜菈；用户 2026-11-05 改成开局解锁，settings 写 0：菜单项一开始就有，basic_spells 一开始就卖，其余按自己的区域）
        k0 = next((k for k, s_ in enumerate(st.stages) if int(s_['flag']) == release), 0)
        release = st.unlock[k0]

    def flag_of(i):
        if not st:
            return release
        if not release and i in st.basic_spells:
            return 0
        k = st.stage(EQUIP_GOODS, i)
        if k is None:
            st.fallback += 1
        return st.flag(max(k0, k or 0))
    for i, r in sorted(Gp.rows.items()):
        shop = next((k for k, ts in SPELL_TYPES.items() if g(r, 'goodsType') in ts), None)
        rar = SPELL_RAR.get(g(r, 'rarity'))
        if shop is None or rar is None or g(r, 'sortGroupId') == 255:
            continue
        lo, hi = SPELL_SHOPS[shop]
        if lo + n[shop] > hi:
            raise RuntimeError('法术商店（%s）放不下' % shop)
        basic = bool(st) and not release and i in st.basic_spells   # 基础法术单独定价
        cost = int(c.get('basic_spell_shards', BASIC_SPELL_SHARDS)) if basic else price(c, 'spell_shards', rar)
        P_s.add_row(lo + n[shop], row(i, EQUIP_GOODS, COST_SHARD, cost, TITLE[shop], flag_of(i)))
        n[shop] += 1
    ctx.spell_release = release
    return n


def talisman_shop(ctx, lib, c, P_s, row):
    """护符模板上架（模板的名字 / 简介 / 说明是 affixes.build 写的）"""
    A = erlib.Param(ctx.bnd.get('EquipParamAccessory.param'))
    k = 0
    for key, f in lib['gear'].items():
        for r in SHOP_RAR:
            if tal_weight(f, r) <= 0:                # 停用的词条、只在别的稀有度出的变体（比如普通 / 大型辉剑圆阵）不上架
                continue
            t = f['tal'].get(r)
            if t is None or t not in A.rows:
                raise RuntimeError('护符商店：词条 %s 的%s护符模板 %s 不在 regulation 里' % (key, RAR_ZH[r], t))
            if TAL_SHOP[0] + k > TAL_SHOP[1]:
                raise RuntimeError('护符商店放不下')
            P_s.add_row(TAL_SHOP[0] + k, row(t, EQUIP_ACCESSORY, COST_HEART, price(c, 'talisman_hearts', r), TITLE['talisman']))
            k += 1
    return k


def weapon_shops(ctx, lib, c, P_s, row):
    """每种武器类型（词条库里能生成的类型）三行：这类型编号最小的三把原版武器，按普通 / 稀有 / 史诗定价；
    按这类型原版武器的 weaponCategory 放进近战 / 远程 / 盾牌商店。返回 {商店: 行数}；ctx.weapon_shop = [(行, 类型, 稀有度序号)]"""
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    wl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamWeapon.xml')))[0]}
    g = lambda row_, f: struct.unpack_from('<' + wl[f][1], row_, wl[f][2])[0]
    types = sorted({int(t) for r in RAR for t in lib['weapon']['types'][r]})
    by = defaultdict(list)
    for i, r in sorted(W.rows.items()):
        if i < 100000000 and i % 10000 == 0 and g(r, 'wepType') in types and g(r, 'sortGroupId') != 255:
            by[g(r, 'wepType')].append(i)
    n = {k: 0 for k in WPN_SHOPS}
    ctx.weapon_shop = []
    for t in types:
        if not by[t]:
            continue
        wc = g(W.rows[by[t][0]], 'weaponCategory')
        shop = 'ranged' if wc in RANGED_CAT else 'shield' if wc in SHIELD_CAT else 'melee'
        lo, hi = WPN_SHOPS[shop]
        for j, r in enumerate(SHOP_RAR):
            if lo + n[shop] > hi:
                raise RuntimeError('武器商店（%s）放不下' % shop)
            i = by[t][j % len(by[t])]
            P_s.add_row(lo + n[shop], row(i, EQUIP_WEAPON, COST_RUNE, price(c, 'weapon_runes', r), TITLE[shop]))
            ctx.weapon_shop.append((lo + n[shop], t, j))
            n[shop] += 1
    return n


def item_shop(ctx, P_s, row):
    """制作配方的产物（ShopLineupParam_Recipe 里的道具 / 箭矢），去重；定价表里没有的按卖出价 × 15。
    箭、大箭、弩箭、弩炮箭 dark_shop.ammo_runes 卢恩（用户 2026-11-02「箭类道具在道具商店均售价1卢恩」），卖出价更高的按卖出价卖（否则商店不显示）；
    没有制作配方的箭类（有名字的）直接上架、一开始就卖，有配方的照旧捡到制作笔记才上架（同日「没制作书的直接加 有制作书的就按制作书逻辑走」）"""
    from .unidentified import ammo_ids
    bnd = ctx.bnd
    ammo = ammo_ids(ctx)
    ammo_price = (ctx.S.get('dark_shop') or {}).get('ammo_runes', 1)
    try:
        prices = json.load(open(os.path.join(ctx.data_dir, 'item_shop.json'), encoding='utf-8'))['prices']
    except Exception:
        prices = {}
    sl, _ = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'ShopLineupParam.xml')))
    so = {nm: (off, fc) for nm, fc, off, bp, bits, d in sl if not bits}
    gv = lambda r, f: struct.unpack_from('<' + so[f][1], r, so[f][0])[0]
    rec = erlib.Param(bnd.get('ShopLineupParam_Recipe.param'))
    P_g = erlib.Param(bnd.get('EquipParamGoods.param'))
    P_w = erlib.Param(bnd.get('EquipParamWeapon.param'))
    g_sell = {nm: (off, fc) for nm, fc, off, *_ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))[0]}['sellValue']
    w_sell = {nm: (off, fc) for nm, fc, off, *_ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamWeapon.xml')))[0]}['sellValue']
    items, seen = [], set()
    for _k, r in sorted(rec.rows.items()):
        t, i, flag = gv(r, 'equipType'), gv(r, 'equipId'), gv(r, 'eventFlag_forRelease')
        prow = P_g.rows.get(i) if t == EQUIP_GOODS else P_w.rows.get(i) if t == EQUIP_WEAPON else None
        if prow is None or (t, i) in seen:
            continue
        seen.add((t, i))
        p = prices.get('%d:%d' % (t, i))
        if isinstance(p, dict):                        # 定价表每一项是 {名字, 价格, 定价依据}；直接写数字也认
            p = p.get('价格')
        if p is None:
            off, fc = g_sell if t == EQUIP_GOODS else w_sell
            sv = struct.unpack_from('<' + fc, prow, off)[0]
            p = sv * 15 if sv > 0 else 1000
        if t == EQUIP_WEAPON and i in ammo and ammo_price is not None:
            p = ammo_price
        items.append((i, t, int(p), flag))
    # 没有制作配方的箭类：有中英文名字的（没名字 / [ERROR] 的是原版没用的行）直接上架，不用解锁
    names = {}
    for code in ('zhocn', 'engus'):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        m = erlib.read_msgbnd(mp) if erlib.dcx_exists(mp) else {}
        names[code] = {k: v for fmg, d in m.items() if fmg == 'WeaponName' or fmg.startswith('WeaponName_dlc') for k, v in d.items()}
    n_free = 0
    for i in sorted(ammo):
        zh, en = (names['zhocn'].get(i) or '').strip(), (names['engus'].get(i) or '').strip()
        if (EQUIP_WEAPON, i) in seen or not zh or not en or 'ERROR' in en:
            continue
        seen.add((EQUIP_WEAPON, i))
        if ammo_price is not None:
            p = ammo_price
        else:
            sv = struct.unpack_from('<' + w_sell[1], P_w.rows[i], w_sell[0])[0]
            p = sv * 15 if sv > 0 else 1000
        items.append((i, EQUIP_WEAPON, int(p), 0))
        n_free += 1
    st = getattr(ctx, 'shop_stages', None)
    if st:
        # 分阶段：基础箭一开始就卖；有区域的按区域；没区域、有制作配方的照旧按制作笔记（flag 是配方的）；都没有的跟第一个区域
        for k, (i, t, p, flag) in enumerate(items):
            if t != EQUIP_WEAPON or i not in ammo:
                continue
            if i in st.basic:
                items[k] = (i, t, p, 0)
            else:
                sk = st.stage(EQUIP_WEAPON, i)
                if sk is not None or not flag:
                    items[k] = (i, t, p, st.flag(sk))
        n_free = sum(1 for i, t, _p, f in items if t == EQUIP_WEAPON and i in ammo and f == 0)
    # 卢恩商店不显示买入价低于卖出价的装备：原版的武器、护符、道具行没有一行这样，骨箭卖出价正好是 1 才看得到，
    # 卖出价 10 的基础箭和之后解锁的箭定 1 卢恩就都看不到（用户 2026-11-06「未正常上架基础箭矢」「那就设为卖出价就好」）：售价不低于卖出价
    off, fc = w_sell
    raised = 0
    for k, (i, t, p, flag) in enumerate(items):
        sv = struct.unpack_from('<' + fc, P_w.rows[i], off)[0] if t == EQUIP_WEAPON else 0
        if sv > p:
            items[k] = (i, t, sv, flag)
            raised += 1
    ctx.report.append('暗黑商店道具商店：箭类 %s；%s %d 种直接上架；%d 种箭的售价提到卖出价（否则商店不显示）' % (
        '最低 %s 卢恩' % ammo_price if ammo_price is not None else '照定价表', '一开始就卖的箭' if st else '没有制作配方的箭类', n_free, raised))
    if len(items) > ITEM_SHOP[1] - ITEM_SHOP[0] + 1:
        raise RuntimeError('制作配方太多，道具商店放不下')
    for k, (i, t, p, flag) in enumerate(items):
        P_s.add_row(ITEM_SHOP[0] + k, row(i, t, COST_RUNE, p, TITLE['item'], flag))
    return len(items)
