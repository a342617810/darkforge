# -*- coding: utf-8 -*-
"""未鉴定物品（新装备系统阶段 1，设计文档第 8 节）：在赐福选「一键鉴定」，dark_core 按词条库把它们换成生成的装备。

道具：武器 / 防具 / 护符 × 普通 / 稀有 / 史诗 / 传说 / 传说（幽影之地）共 15 种，编号 GOODS0 + 类别 × 10 + 档；
      照锻造石【1】复制（可堆叠、没有使用效果），图标借砥石小刀（武器）、裁缝工具（防具）、原版护符（护符）。
掉落：照 RNG Lands 时的设定搬过来（用户 2026-10-26：「按照之前的设定搬迁」），原版的东西都不动，未鉴定物品是额外的；
  设置沿用以前的键（settings.json）：
  - 普通敌人（ctx.enemy_bands 里分了档的）：以前「每杀掉东西 enemy_drop_chance、其中材料占 enemy_material_share」，
    装备的期望件数照以前的拆法算出来（gear_lambda）；掉落表后面接每类 ROWS_PER_CAT 行（各自独立判定，开了发现力加成），
    武器 / 防具 / 护符按 gear_category_share 分，稀有度按 tier_bands 这一档的 weights，DLC 两档的传说是传说（幽影之地）。
    精英（elite_enemies，名单 data\\elite_families.json / elite_dlc.json）按下一档；最后一档的精英另外平均每杀多掉
    elite_last_legendary_mean 件传说（内部当成第 NB 档）。
    做法：每个（原掉落表, 档, 是否精英）复制一份整条原表、后面接这几行，敌人参数指向复制的那份（ENEMY_LOT0 起）；
    开了敌人随机时 stage3 按敌人实际被放到的位置换成那一档的（enemies.hp 里调 lot）。
    高难度统一掉落（settings 的 hard_drops，用户 2026-11-04「高难度后小怪爆率统一到dlc后期」）：「死亡」「不可能」里所有复制表接上的那几行
    都换成 DLC 最后一档的（普通敌人 = DLC 后期小怪：稀有度、古龙岩；精英 = 最后一档精英：再多的传说）。参数是全局的、难度游戏里随时能切，
    所以由 dll\\dark_core 的 hpunify 模块进这几档时改、出来改回（只改道具格，原表那几行不动）：这里让每张复制表接上的行数都补到目标的行数
    （多出来的是不掉东西的空行，平时没影响），精英 / 普通分开复制（目标不一样），另外建两组目标行（droptgt），hpunify.txt 写 dropcopy 行。
  - Boss（boss_legendary，data\\boss_lots.json）：击杀奖励多给 tier_bands 各档 boss_legendary 件传说（最多 8），只给一次；
    在龙心脏、锻造石之前先占奖励表的空号（用户要求传说优先），空号不够就一行给几件（同一类）；表放不下的改由 Boss 自身掉落。
  - 宝箱（chest_add_legendary_if_no_gear，data\\treasures.json）：不出装备的宝箱追加一件，稀有度按 chest_rarity_weights（史诗 / 传说）；
    出原版装备的宝箱不追加，装备就地换成同样的未鉴定掉落（no_vanilla_gear，支线奖励也一样）。
  - 黄金卢恩（golden_rune_to_gear）：地上 / 尸体上的黄金卢恩【1】~【13】光点换成这个地区的未鉴定物品（稀有度按 weights）。
  - 砥石刀（whetblade_to_gear，用户 2026-10-30）：铁制 / 灼热 / 神圣 / 辉石 / 漆黑砥石刀的光点（生成的武器不能质变，用不上）
    照黄金卢恩换成这个地区的未鉴定物品；砥石小刀（装战灰）照旧。
  - 人形 NPC（npc_add_legendary_if_no_gear，data\\npc_lots.json）：死亡掉落追加一件传说（拿过一次就不再掉）。"""
from .common import *  # noqa: F401,F403
from . import once

# 掉落表第 6 类「定制武器」：编号是 EquipParamCustomWeapon 的行（第一个字段 baseWepId = 本体，另带强化等级 / 战灰）。
# 原版 18 格：14 格在支线（尤拉的长牙、艾德格的戟……）、4 格是幽影之地的光点；2026-11-10 以前都没认，一直给原版的
CAT_CW = 6
CUSTOM = {}                                    # 定制武器编号 → 本体武器编号（prepare 时读）
GOODS0 = 9200                                  # 道具编号：9200 + 类别 × 10 + 档（9200~9224，原版没用）
CATS = ('weapon', 'armor', 'talisman')
TIERS = RAR + ('LegendaryDLC',)               # 第 5 档：传说（幽影之地），防具更容易三词条
GOODS_TMPL = 10100                             # 锻造石【1】
ICON_FROM = {'weapon': ('goods', 8590), 'armor': ('goods', 8163), 'talisman': ('acc', 1000)}   # 砥石小刀、裁缝工具、赤琥珀链坠
SORT0 = 160000                                 # 排在锻造石（151000 起）后面
ENEMY_LOT0 = 1950000000                        # 敌人掉落的复制表从这里起（10 一格，原版没用）
ROWS_PER_CAT = 2                               # 敌人每类接几行（一次最多掉这么多件同类的；期望件数照以前算）
ROW_LIMIT = 64000                              # 敌人掉落表行数到这里就不再复制（参数表最多 65535 行），剩下的照原表掉
GOLDEN_RUNES = range(2900, 2913)               # 黄金卢恩【1】~【13】
WHETBLADES = range(8970, 8975)                 # 铁制 / 灼热 / 神圣 / 辉石 / 漆黑砥石刀（砥石小刀 8590 不算）
BOSS_MAX = 8
QUEST_LOTS = (100000, 119999)                  # 原版地图掉落表里 NPC 用的一段：NPC 给的、支线奖励、NPC 死后掉的
QUEST_FINAL_N = 3                              # 支线最后一环（data\quest_finals.json，含白面具）多给未鉴定传说武器 / 防具 / 护符各几件（settings 的 quest_final_legendary）
AMMO_TYPES = (81, 83, 85, 86)                  # EquipParamWeapon.wepType：箭、大箭、弩箭、弩炮箭（消耗品，不算装备）
CAT_TEXT = {'zh': ('武器', '防具', '护符'), 'en': ('Weapon', 'Armor', 'Talisman')}
# 说明第一句：流纹文字在哪（叙事方案：词条就是流纹文字，鉴定是辨认文字）
SCRIPT_AT = {'zh': ('表面', '内侧', '背面'), 'en': ('on its surface', 'on its lining', 'on its back')}
EN_ONE = ('A weapon', 'A piece of armor', 'A talisman')     # 英文说明开头（armor 不可数）
RAR_TEXT = {'zh': ('普通', '稀有', '史诗', '传说', '传说'), 'en': ('Common', 'Rare', 'Epic', 'Legendary', 'Legendary')}


def goods_id(cat, tier):
    return GOODS0 + cat * 10 + tier


def cfg(S):
    """新装备系统的掉落设置；各来源沿用 RNG Lands 时的键名和默认值"""
    if not (S.get('unidentified') or {}).get('enabled', True):
        return None
    return {
        'drop_chance': float(S.get('enemy_drop_chance', 0.6)),
        'material_share': float(S.get('enemy_material_share', 0.25)),
        'share': S.get('gear_category_share') or {'weapon': 30, 'armor': 60, 'talisman': 10},
        'elite': bool(S.get('elite_enemies', True)),
        'elite_last_mean': float(S.get('elite_last_legendary_mean', 1.0)),
        'boss': bool(S.get('boss_legendary', True)),
        'chest': bool(S.get('chest_add_legendary_if_no_gear', True)),
        'chest_weights': S.get('chest_rarity_weights') or {'Legendary': 25, 'Epic': 75},
        'chest_extra': max(0, int(S.get('chest_extra_drops', 1))),
        'golden': bool(S.get('golden_rune_to_gear', True)),
        'whetblade': bool(S.get('whetblade_to_gear', True)),
        'npc': bool(S.get('npc_add_legendary_if_no_gear', True)),
    }


def gear_lambda(chance, mshare):
    """以前的分档大表：每杀「至少掉 1 样」的概率 chance 换成总的 λ（P = 1 - e^-λ），再把 λ 在装备 / 材料之间二分，
    让材料的期望件数占 mshare；装备那一份 λ_g 就是每杀装备的期望件数（材料按一行算，和以前的拆法一样）"""
    chance = min(0.95, max(0.05, chance))
    mshare = min(0.9, max(0.0, mshare))
    lam = -math.log(1.0 - chance)
    if mshare <= 0:
        return lam
    lo, hi = 0.0, lam
    for _ in range(60):
        lm = (lo + hi) / 2
        e_m, e_g = 1 - math.exp(-lm), lam - lm
        if e_m / (e_m + e_g) < mshare:
            lo = lm
        else:
            hi = lm
    return lam - lo


def is_dlc(band):
    return band.get('max_tier', 0) > 20


# DLC 小怪掉古龙岩锻造石（settings 的 dlc_mob_stones，用户 2026-11-04「dlc小怪10%概率掉两种古龙」）：开了敌人随机时小怪掉的锻造石跟着怪走
# （本体的怪放进 DLC 只偶尔掉低级石，DLC 位置每杀 100 只只掉约 1 块，原版 DLC 是 5~13 块）。这里按怪所在的位置：
# 位置在 DLC 档（tier_bands 的 max_tier > 20）的分档小怪，复制的掉落表后面再接一行，chance 的概率掉一块，两种古龙岩各一半
DLC_STONES = (10140, 10168)                    # 古龙岩锻造石、古龙岩失色锻造石（10168；10200 是失色【９】，不连号，用户 2026-11-05 发现掉成了失色９）


def dlc_stone_cfg(S):
    """(概率, [道具…])；关了是 None"""
    c = S.get('dlc_mob_stones') or {}
    if not c.get('enabled', True):
        return None
    p = float(c.get('chance', 0.10))
    return (p, [int(g) for g in c.get('goods', DLC_STONES)]) if p > 0 else None


def texts(lib):
    """各道具的（名字, 简介, 说明），按语言"""
    out = {'zh': {}, 'en': {}}
    for c, cat in enumerate(CATS):
        for t, tier in enumerate(TIERS):
            r = RAR[min(t, 3)]
            tag = {lang: lib['rarity_tag'][r][lang] for lang in ('zh', 'en')}
            dlc = t == 4
            rz, re_ = RAR_TEXT['zh'][t] + ('（幽影之地）' if dlc else ''), RAR_TEXT['en'][t] + (' (Realm of Shadow)' if dlc else '')
            what_zh = {'weapon': '武器类型、补正、附加效果、战技', 'armor': '部位、词条', 'talisman': '效果'}[cat]
            what_en = {'weapon': 'weapon type, scaling, effects and skill', 'armor': 'slot and effects', 'talisman': 'effect'}[cat]
            extra_zh = '\n幽影之地的传说防具更容易带三个词条。' if dlc and cat == 'armor' else ''
            extra_en = '\nLegendary armor from the Realm of Shadow is more likely to carry three effects.' if dlc and cat == 'armor' else ''
            out['zh'][(c, t)] = (
                '%s 未鉴定的%s%s' % (tag['zh'], CAT_TEXT['zh'][c], '（幽影之地）' if dlc else ''),
                '在赐福「暗黑重铸」→「鉴定」里鉴定，变成一件随机的%s%s' % (rz, CAT_TEXT['zh'][c]),
                '来历不明的%s。%s的流纹文字已经模糊，无法辨认。\n\n在赐福「暗黑重铸」→「鉴定」：「一键鉴定」把背包里的未鉴定物品一次全部鉴定，各自变成一件随机的%s%s，'
                '%s都在鉴定时决定%s。%s' % (CAT_TEXT['zh'][c], SCRIPT_AT['zh'][c], rz, CAT_TEXT['zh'][c], what_zh,
                                       '；未鉴定武器也可以花卢恩「定向鉴定」成指定的武器类型' if c == 0 else '', extra_zh))
            out['en'][(c, t)] = (
                '%s Unidentified %s%s' % (tag['en'], CAT_TEXT['en'][c], ' (Realm of Shadow)' if dlc else ''),
                'Identify it at a site of grace ("Darkforge" > "Identify") to turn it into a random %s %s' % (re_, CAT_TEXT['en'][c].lower()),
                '%s of unknown origin. The smithscript %s has faded beyond reading.\n\nAt a site of grace, "Darkforge" > "Identify" > "Identify All" identifies every unidentified item in your inventory at once, '
                'each becoming a random %s %s. Its %s are decided at that moment%s.%s' % (
                    EN_ONE[c], SCRIPT_AT['en'][c], re_, CAT_TEXT['en'][c].lower(), what_en,
                    '; unidentified armaments can also be identified as a chosen weapon type for runes (Targeted Identify)' if c == 0 else '', extra_en))
    return out


def make_goods(ctx, lib):
    gl, gsz = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))
    go = {n: (o, fc) for n, fc, o, *_ in gl}
    G = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    A = erlib.Param(ctx.bnd.get('EquipParamAccessory.param'))
    al, _ = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamAccessory.xml')))
    ao = {n: (o, fc) for n, fc, o, *_ in al}
    if gsz != G.row_size or GOODS_TMPL not in G.rows:
        raise RuntimeError('未鉴定物品：EquipParamGoods 行大小不对或缺少锻造石【1】%d' % GOODS_TMPL)
    used = [goods_id(c, t) for c in range(3) for t in range(5) if goods_id(c, t) in G.rows]
    if used:
        raise RuntimeError('未鉴定物品：道具编号 %s 已被占用' % used)

    def icon(cat):
        kind, i = ICON_FROM[cat]
        P, o = (G, go) if kind == 'goods' else (A, ao)
        row = P.rows.get(i)
        return struct.unpack_from('<' + o['iconId'][1], row, o['iconId'][0])[0] if row is not None else None

    for c, cat in enumerate(CATS):
        ic = icon(cat)
        for t in range(5):
            row = bytearray(G.rows[GOODS_TMPL])
            sell = int(lib['sell'][cat][RAR[min(t, 3)]]) // 3
            vals = {'sortId': SORT0 + c * 10 + t, 'rarity': min(t, 3), 'sellValue': sell, 'maxNum': 999, 'maxRepositoryNum': 999}
            if ic is not None:
                vals['iconId'] = ic
            for f, v in vals.items():
                struct.pack_into('<' + go[f][1], row, go[f][0], v)
            G.add_row(goods_id(c, t), bytes(row))
    ctx.bnd.put('EquipParamGoods.param', G.serialize())
    tx = texts(lib)
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for j, fmg in enumerate(('GoodsName.fmg', 'GoodsInfo.fmg', 'GoodsCaption.fmg')):
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            d.update({goods_id(c, t): v[j] for (c, t), v in tx[lang].items()})
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))


def blank_row(template=None, size=152):
    row = bytearray(template) if template is not None else bytearray(size)
    if template is None:
        row[137] = 0xFF
        row[148] = 0xFF
    for i in range(8):
        erlib.lot_clear_slot(row, i)
    struct.pack_into('<I', row, erlib.LOT_FLAG, 0)
    return row


def chance_row(template, slots, p):
    """一行独立判定：概率 p 掉一件（slots = [(道具, 权重)] 按权重挑一种），否则什么都不掉；道具格开发现力加成"""
    row = blank_row(template)
    tot = float(sum(w for _, w in slots)) or 1.0
    k = 0
    for g, w in slots:
        pt = int(round(10000 * p * w / tot))
        if pt > 0:
            erlib.lot_set_slot(row, k, 1, g, pt, num=1, luck=True, slotflag=0)
            k += 1
    used = sum(struct.unpack_from('<H', row, erlib.LOT_PT + 2 * i)[0] for i in range(k))
    erlib.lot_set_slot(row, k, 0, 0, max(0, 10000 - used), num=0, luck=False, slotflag=0)
    return row


def sure_row(U, tier_of, flag, template=None, num=1, weights=None):
    """必掉一行：武器 / 防具 / 护符按 category_share，稀有度按 weights（{档: 权重}，没给就只有 tier_of 那一档）；带获取标记"""
    row = blank_row(template)
    k = 0
    for ci in range(3):
        for t, w in (weights or {tier_of: 1}).items():
            pt = int(round(1000 * U.share[ci] * w / float(sum((weights or {tier_of: 1}).values()))))
            if pt > 0 and k < 8:
                erlib.lot_set_slot(row, k, 1, goods_id(ci, t), pt, num=num, luck=False, slotflag=0)
                k += 1
    struct.pack_into('<I', row, erlib.LOT_FLAG, flag)
    return row


class Drops:
    """敌人掉落的复制表：每个（原掉落表, 档, 是否精英）一份，原表整条照抄、后面接未鉴定物品的几行。
    档 0 ~ NB-1 是 tier_bands；精英往上一档，最后一档的精英是 NB（= 最后一档 + 额外的传说）"""

    def __init__(self, ctx, c):
        self.ctx, self.c = ctx, c
        self.P_en = ctx.P_en
        self.bands = ctx.bands
        self.NB = len(self.bands)
        share = c['share']
        tot = float(sum(share.get(k, 0) for k in CATS)) or 1.0
        self.share = [share.get(k, 0) / tot for k in CATS]
        self.lam = gear_lambda(c['drop_chance'], c['material_share'])
        self.elite_fam = elite_families(ctx.data_dir) if c['elite'] else set()
        self.lots = {}
        self.next = ENEMY_LOT0
        self.n_rows = 0
        self.full = 0                          # 行数到上限、没复制的（原表, 档）
        self.tmpl = None
        self.dlc_stone = dlc_stone_cfg(ctx.S)
        self.n_dlc_stone = 0                   # 接了古龙岩那一行的复制表
        sd = ctx.S.get('smithing_stone_drop') or {}
        self.stone_on = bool(sd.get('enabled', True)) and bool(sd.get('pools'))
        self.stone_p = max(0.0, min(1.0, float(sd.get('chance', 0.3)))) if self.stone_on else 0.0
        self.stone_pools = sorted(sd.get('pools') or [], key=lambda p: p['max_tier'])
        self.n_old_stones = 0                  # 复制表里去掉的原版锻造石格
        from .hpunify import flags as lock_flags
        self.hard = bool((ctx.S.get('hard_drops') or {}).get('enabled', True) and lock_flags(ctx.S))
        self.app = {}                          # 高难度统一掉落：复制表 → (接上的第一行, 行数, 精英)

    def is_elite(self, npc):
        return npc // 10000 in self.elite_fam

    def pos_dlc(self, band, elite):
        """这一档（精英已经往上挪了一档）的敌人实际所在的位置在不在 DLC 档"""
        pos = max(0, min(band - (1 if elite else 0), self.NB - 1))
        return is_dlc(self.bands[pos])

    def target(self, elite):
        """高难度统一掉落的目标（档, 在不在 DLC 位置）：普通敌人 = DLC 最后一档，精英 = 最后一档的精英"""
        band = self.NB if elite else self.NB - 1
        return band, bool(self.dlc_stone) and self.pos_dlc(band, elite)

    def target_len(self, elite):
        band, dlc = self.target(elite)
        return len(self.band_rows(band, self.tmpl or bytes(self.P_en.rows[min(self.P_en.rows)]), dlc))

    def alloc(self, n):
        """n 行连着放的起点（前后各空一号，10 一格）"""
        P = self.P_en
        step = 10 * ((n + 1 + 9) // 10)
        while any((self.next + k) in P.rows for k in range(-1, n + 1)):
            self.next += step
        nid = self.next
        self.next += step
        return nid

    def hard_lines(self):
        """高难度统一掉落：建两组目标行（普通 / 精英），返回 hpunify.txt 的 droptgt / dropcopy 行"""
        if not self.hard or not self.app:
            return []
        tmpl = self.tmpl or bytes(self.P_en.rows[min(self.P_en.rows)])
        out = []
        for elite in (False, True):
            band, dlc = self.target(elite)
            rows = self.band_rows(band, tmpl, dlc)
            nid = self.alloc(len(rows))
            for k, row in enumerate(rows):
                self.P_en.add_row(nid + k, bytes(row))
            self.n_rows += len(rows)
            out.append('droptgt %d %d %d' % (int(elite), nid, len(rows)))
        out += ['dropcopy %d %d %d' % (int(e), first, n) for first, n, e in sorted(self.app.values())]
        return out

    def stone_pool(self, band):
        """这一档小怪锻造石池（settings 的 smithing_stone_drop.pools）"""
        b = self.bands[min(band, self.NB - 1)]
        mt = int(b.get('max_tier', 99))
        return next((p['items'] for p in self.stone_pools if mt <= p['max_tier']), self.stone_pools[-1]['items'])

    def stone_row_pool(self, band, dlc):
        """小怪 30% 基础行的池子：单行最多 8 格；DLC 的两种古龙岩由独立 10% 行负责"""
        pool = [int(i) for i in self.stone_pool(band)]
        if self.dlc_stone and (dlc or len(pool) > 8):
            extra = set(self.dlc_stone[1])
            pool = [i for i in pool if i not in extra]
        if len(pool) > 8:
            raise RuntimeError('小怪锻造石池超过 8 种：%s' % pool)
        return pool

    def band_rows(self, band, template, dlc=False):
        base = min(band, self.NB - 1)
        b = self.bands[base]
        w = b.get('weights') or {}
        rar = [(4 if (r == 'Legendary' and is_dlc(b)) else t, float(w.get(r, 0))) for t, r in enumerate(RAR)]
        out = []
        for ci in range(3):
            p = min(0.95, self.lam * self.share[ci] / ROWS_PER_CAT)        # 每行概率 = 这一类的期望件数 / 行数
            if p > 0:
                out += [chance_row(template, [(goods_id(ci, t), x) for t, x in rar if x > 0], p) for _ in range(ROWS_PER_CAT)]
        if self.stone_on:                      # 小怪锻造石：每杀 stone_p 概率掉一块，从这一档池子等权抽（发现力有效）
            pool = self.stone_row_pool(band, dlc)
            if self.stone_p > 0 and pool:
                out.append(chance_row(template, [(i, 1) for i in pool], self.stone_p))
        if band >= self.NB:                    # 最后一档的精英：再平均多掉 elite_last_legendary_mean 件传说
            leg = 4 if is_dlc(b) else 3
            for ci in range(3):
                p = min(0.95, self.c['elite_last_mean'] * self.share[ci] / ROWS_PER_CAT)
                if p > 0:
                    out += [chance_row(template, [(goods_id(ci, leg), 1)], p) for _ in range(ROWS_PER_CAT)]
        if dlc and self.dlc_stone:             # DLC 位置的小怪：古龙岩锻造石（两种按一样的权重）
            p, goods = self.dlc_stone
            out.append(chance_row(template, [(g, 1) for g in goods], p))
        return out

    def lot(self, orig, band, elite):
        band = max(0, min(band, self.NB))
        dlc = bool(self.dlc_stone) and self.pos_dlc(band, elite)
        key = (orig, band, dlc)               # 同一张原表可能既给精英（往上挪了一档）又给普通敌人用：在不在 DLC 位置分开算
        if self.hard:
            key += (elite,)                   # 高难度统一掉落：精英 / 普通的目标不一样，分开复制
        if key in self.lots:
            return self.lots[key]
        P = self.P_en
        chain = []
        r = orig
        while orig > 0 and r in P.rows:
            row = bytearray(P.rows[r])
            if self.stone_on:
                # 原表里的锻造石不再掉：清掉石格，点数并进一个空格，保持其他物品的原始概率
                ss = [s for s in erlib.lot_slots(row) if s[1] == 1 and s[2] in SMITHING_STONES and s[3] > 0]
                if ss:
                    total = sum(s[3] for s in ss)
                    for i, _cat, _iid, _pt in ss:
                        erlib.lot_clear_slot(row, i)
                    erlib.lot_set_slot(row, ss[0][0], 0, 0, total, num=0, luck=False, slotflag=0)
                    self.n_old_stones += len(ss)
            chain.append(row)
            r += 1
        if self.tmpl is None:
            self.tmpl = bytes(P.rows[min(P.rows)])
        tmpl = chain[0] if chain else self.tmpl
        app = self.band_rows(band, tmpl, dlc)
        if self.hard:                         # 补到目标的行数（空行：只有「什么都不掉」那一格）
            app += [chance_row(tmpl, [], 0.0) for _ in range(self.target_len(elite) - len(app))]
        rows = chain + app
        if len(P.rows) + len(rows) > ROW_LIMIT:
            self.full += 1
            self.lots[key] = orig
            return orig
        nid = self.alloc(len(rows))
        for k, row in enumerate(rows):
            P.add_row(nid + k, bytes(row))
        if self.hard:
            self.app[key] = (nid + len(chain), len(app), elite)
        self.n_rows += len(rows)
        self.n_dlc_stone += dlc
        self.lots[key] = nid
        return nid


def prepare(ctx):
    """道具 + 敌人掉落的复制表（在 enemies.hp 之前：hp 里分完档就让敌人参数指向复制表，敌人随机时 stage3 按位置换）"""
    ctx.unid = None
    c = cfg(ctx.S)
    if not c:
        return
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    CUSTOM.clear()
    C = erlib.Param(ctx.bnd.get('EquipParamCustomWeapon.param'))
    CUSTOM.update({rid: struct.unpack_from('<i', row, 0)[0] for rid, row in C.rows.items()})
    make_goods(ctx, lib)
    ctx.unid = Drops(ctx, c)
    ctx.features['unidentified'] = {'goods0': GOODS0, 'cats': list(CATS), 'tiers': list(TIERS)}


def report_enemy(ctx, n_npc, n_elite):
    U = ctx.unid
    p_any = 1 - math.prod((1 - min(0.95, U.lam * s / ROWS_PER_CAT)) ** ROWS_PER_CAT for s in U.share)
    if U.stone_on:
        ctx.report.append('小怪锻造石：每杀 %.0f%% 掉 1 块，按所在档池子等权抽（发现力 100 基准；%s）；'
                          'DLC 小怪的 30%% 基础行不含 10140/10168，这两种另算 %.0f%%；复制表里去掉原版锻造石格 %d 个' % (
            U.stone_p * 100, '；'.join('<=%s：%s' % (p['max_tier'], ','.join(map(str, p['items']))) for p in U.stone_pools),
            (U.dlc_stone[0] * 100 if U.dlc_stone else 0), U.n_old_stones))
    ctx.report.append('未鉴定物品：道具 %d~%d（武器 / 防具 / 护符 × 普通 ~ 传说（幽影之地））；普通敌人每杀平均 %.2f 件（至少 1 件约 %.0f%%；'
                      '照以前「掉东西 %.0f%%、材料占 %.0f%%」算），武器 / 防具 / 护符 %s；精英按下一档，最后一档的精英再平均多 %g 件传说；'
                      '%d 个敌人参数（精英 %d 个）指向 %d 张复制的掉落表（%d 行）%s' % (
                          GOODS0, goods_id(2, 4), U.lam, p_any * 100, U.c['drop_chance'] * 100, U.c['material_share'] * 100,
                          ' / '.join('%d%%' % round(s * 100) for s in U.share), U.c['elite_last_mean'], n_npc, n_elite, len(U.lots) - U.full, U.n_rows,
                          '；敌人掉落表行数到上限，%d 种组合没加上（这些敌人照原表掉）' % U.full if U.full else ''))
    if U.dlc_stone:
        ctx.report.append('DLC 小怪的古龙岩锻造石：位置在 DLC 档的分档小怪每杀 %g%% 掉一块（%s 各一半；按位置，敌人随机时 stage3 换档也算），'
                          '到这里 %d 张复制表接上了这一行' % (U.dlc_stone[0] * 100, ' / '.join(map(str, U.dlc_stone[1])), U.n_dlc_stone))


def spread(n, m):
    """n 件分到 m 行：每行几件"""
    return [n // m + (1 if k < n % m else 0) for k in range(m)] if m > 0 else []


def boss_drops(ctx):
    """Boss 击杀奖励多给 tier_bands 各档 boss_legendary 件传说（最多 8；DLC 档是传说（幽影之地）），只给一次。
    在龙心脏、星光碎片、保底锻造石之前做（用户要求传说优先）：先占奖励表后面的空号（沿用奖励表的获取标记，后面要留一个空号），
    空号不够 n 行就一行给几件（同一行抽到的类别一样）；表后面一个空号都没有的改由 Boss 自身掉落：敌人参数指向新表
    （最多三行 + 原来的掉落），获取标记用 data\\boss_unid_flags.json 里每个 Boss 位置固定的三个。"""
    from . import bossaward
    from .bosses import boss_npcs, self_drop
    U = getattr(ctx, 'unid', None)
    if not U or not U.c['boss']:
        return

    def load(name):
        try:
            return json.load(open(os.path.join(ctx.data_dir, name), encoding='utf-8'))['bosses']
        except Exception:
            return [] if name == 'boss_lots.json' else {}
    bosses = load('boss_lots.json')
    P, chain = ctx.P_mp, ctx.chain
    done, n_table, n_items, need_self = set(), 0, 0, []
    for b in bosses:
        bi = ctx.band_idx(b['tier'])
        n = min(BOSS_MAX, int(ctx.bands[bi].get('boss_legendary', 0)))
        if n <= 0:
            continue
        tier = 4 if is_dlc(ctx.bands[bi]) else 3
        placed = False
        for lot in b['lots']:
            rows = chain(lot)
            if not rows:
                continue
            if rows[-1] in done:                       # 几个 Boss 共用一张奖励表：给过了
                placed = True
                break
            first = P.rows[rows[0]]
            flag = erlib.lot_flag(first)
            if flag == 0:
                continue
            end = rows[-1]
            room = next((k for k in range(1, n + 2) if (end + k) in P.rows), n + 1) - 1    # 表后面连续的空号，留最后一个空着
            m = min(n, room - 1) if room <= n else n
            if m <= 0:
                continue
            for k, num in enumerate(spread(n, m)):
                P.add_row(end + 1 + k, bytes(sure_row(U, tier, flag, template=first, num=num)))
            done.add(end + m)
            n_table += 1
            n_items += n
            placed = True
            break
        if not placed:
            need_self.append((b, n, tier))
    # 放不下的：事件发放（rr/bossaward.py）；找不到击败标记的才走 Boss 自身掉落（开了敌人随机用这个位置实际放的敌人参数）
    n_self, fail = 0, []
    if need_self:
        flags = load('boss_unid_flags.json')
        ent_npc = boss_npcs(ctx, load('boss_selfdrop.json'))
        P_npc = erlib.Param(ctx.bnd.get('NpcParam.param'))
        redirected, nid = {}, 1908300000
        for b, n, tier in need_self:
            npc = ent_npc.get(b['entity'])
            fl = (flags.get(str(b['entity'])) or {}).get('flags') or []
            if fl and bossaward.add(ctx, b['entity'], [sure_row(U, tier, f, num=num) for f, num in zip(fl, spread(n, min(n, len(fl))))]):
                n_self += 1
                n_items += n
                continue
            if npc is None or npc not in P_npc.rows or not fl:
                fail.append(b['name'])
                continue
            if npc in redirected:                      # 和别的 Boss 共用敌人参数：那张表已经有了（标记按先到的）
                fail.append('%s（和%s共用敌人参数）' % (b['name'], redirected[npc]))
                continue
            m = min(n, len(fl))
            nid = self_drop(P_npc, ctx.P_en, npc, [sure_row(U, tier, f, num=num) for f, num in zip(fl, spread(n, m))], nid)
            redirected[npc] = b['name']
            n_self += 1
            n_items += n
        if n_self:
            ctx.bnd.put('NpcParam.param', P_npc.serialize())
    n_extra, fail_x = boss_extra_drops(ctx, U, load('boss_unid_flags.json'))
    fail += fail_x
    ctx.report.append('未鉴定物品（Boss）：击杀奖励多给传说（各档 %s 件，只给一次）共 %d 件：%d 个 Boss 放进奖励表、%d 个改由事件发放、'
                      '%d 个击杀不发奖励的小 Boss（事件发放，个别照旧自身掉落）%s' % (
                          ' / '.join(str(b.get('boss_legendary', 0)) for b in ctx.bands), n_items, n_table, n_self, n_extra,
                          '；%d 个没加上：%s' % (len(fail), '、'.join(fail)) if fail else ''))


def boss_extra_drops(ctx, U, flags):
    """击杀事件不发奖励、原版靠自身掉落的小 Boss（data\\boss_extra.json：南瓜头、王室幽魂、鲜血贵族、落叶丹恩……）：
    在它的 lot 编号建一张表 =「传说几行 + 原来的整条掉落」，敌人参数指向它（开了敌人随机用这个位置实际放的那行）；
    保底锻造石（bosses.smithing_stones）随后接在这张表后面。获取标记用 boss_unid_flags.json 里标 extra 的（93060 起，每个三个）"""
    try:
        bx = json.load(open(os.path.join(ctx.data_dir, 'boss_extra.json'), encoding='utf-8'))['bosses']
    except Exception:
        return 0, []
    ent_npc = getattr(ctx, 'ent_npc_final', None) if ctx.a.randomizer_dir else None
    P_npc = erlib.Param(ctx.bnd.get('NpcParam.param'))
    P = ctx.P_en
    from . import bossaward
    n, fail = 0, []
    for b in bx:
        bi = ctx.band_idx(b['tier'])
        k = min(BOSS_MAX, int(ctx.bands[bi].get('boss_legendary', 0)))
        fl = (flags.get(str(b['entity'])) or {}).get('flags') or []
        npc = ent_npc.get(b['entity']) if ent_npc else b.get('npc')
        if b.get('randomizer_only') and not ctx.a.randomizer_dir:
            continue
        if b.get('replaced_only') and (not ent_npc or npc == b.get('npc')):
            continue
        if k <= 0 or not fl:
            continue
        if bossaward.extra_by_event(ctx, b):           # 事件发放：不用改敌人参数，它原本的掉落照旧
            tier = 4 if is_dlc(ctx.bands[bi]) else 3
            bossaward.add(ctx, b['entity'], [sure_row(U, tier, f, num=num) for f, num in zip(fl, spread(k, min(k, len(fl))))], flag=b['entity'])
            n += 1
            continue
        if npc is None or npc not in P_npc.rows:
            fail.append(b['name'] + '（地图上没找到）')
            continue
        old = struct.unpack_from('<i', P_npc.rows[npc], 48)[0]
        rows, r = [], old
        while old > 0 and r in P.rows:
            rows.append(bytes(P.rows[r]))
            r += 1
        tier = 4 if is_dlc(ctx.bands[bi]) else 3
        m = min(k, len(fl))
        rows = [bytes(sure_row(U, tier, f, num=num)) for f, num in zip(fl, spread(k, m))] + rows
        lot = b['lot']
        if any((lot + j) in P.rows for j in range(-1, len(rows) + 1)):
            fail.append(b['name'] + '（掉落表编号被占）')
            continue
        for j, row in enumerate(rows):
            P.add_row(lot + j, row)
        struct.pack_into('<i', P_npc.rows[npc], 48, lot)
        n += 1
    if n:
        ctx.bnd.put('NpcParam.param', P_npc.serialize())
    return n, fail


def treasure_lots(ctx):
    """data\\treasures.json 的宝物：掉落表编号 → 宝物（kind：chest / ground / corpse …）"""
    try:
        trs = json.load(open(os.path.join(ctx.data_dir, 'treasures.json'), encoding='utf-8'))['treasures']
    except Exception:
        trs = []
    by_lot = {}
    for t in trs:
        # 宝箱模型（AEG099_013 / 630~633）一律算宝箱：有几个宝箱的宝物事件没标「在宝箱里」
        kind = 'chest' if t['part'][:10] in ('AEG099_013', 'AEG099_630', 'AEG099_631', 'AEG099_632', 'AEG099_633') else t['kind']
        prev = by_lot.get(t['lot'])
        if prev is None or (prev['kind'] != 'chest' and kind == 'chest'):
            by_lot[t['lot']] = dict(t, kind=kind)
    return by_lot


def chest_weights(c, band):
    """宝箱那份未鉴定掉落的稀有度：{档: 权重}（chest_rarity_weights；幽影之地的传说是传说（幽影之地））"""
    cw = c['chest_weights']
    return {(4 if (r == 'Legendary' and is_dlc(band)) else k): float(cw.get(r, 0)) for k, r in enumerate(RAR) if cw.get(r, 0)}


def world_drops(ctx):
    """宝箱、黄金卢恩光点、人形 NPC 的掉落（照以前的 rr/world.py chests_and_pickups）：
    不出装备的宝箱表后面接一行（沿用宝箱的获取标记，要表后面两个空号），稀有度按 chest_rarity_weights；出原版装备的宝箱不追加，
    装备由后面的 no_vanilla_gear 就地换成同样的未鉴定掉落（用户 2026-10-28：追加只给不出装备的宝箱，出装备的是替换；关了 no_vanilla_gear 就照旧都追加）；
    地上 / 尸体上只有黄金卢恩【1】~【13】（或砥石刀）一格的那一行，换成这个地区的未鉴定物品（这一次随机挑类别，稀有度按 weights，获取标记照旧）；
    人形 NPC 的死亡掉落表后面接一件传说（沿用获取标记）；Boss 奖励表（data\\boss_lots.json）里的不算，Boss 那边已经给了"""
    U = getattr(ctx, 'unid', None)
    if not U:
        return
    c, P, chain = U.c, ctx.P_mp, ctx.chain
    by_lot = treasure_lots(ctx)
    tier_of = lambda m: int(ctx.map_tiers.get(m, 1))
    cw = c['chest_weights']
    replace = ctx.S.get('no_vanilla_gear', True)
    ammo = ammo_ids(ctx) if replace else set()
    n_chest = n_chest_skip = n_chest_gear = n_chest_extra = n_gold = n_whet = 0
    for lot, t in sorted(by_lot.items()):
        rows = chain(lot)
        if not rows:
            continue
        b = ctx.band_for(tier_of(t['map']))
        if t['kind'] == 'chest' and c['chest']:
            has_gear = replace and any(gear_slots(P.rows[r], ammo) for r in rows)
            if has_gear:
                n_chest_gear += 1
            # 原逻辑：不出装备的宝箱基础追加 1 件；出装备的由后面的 no_vanilla_gear 替换。
            # 用户 2026-11-08「宝箱掉落 +1」：所有宝箱在以上基础上再追加 chest_extra 行。
            add = (0 if has_gear else 1) + c['chest_extra']
            first = P.rows[rows[0]]
            flag = erlib.lot_flag(first)
            end = rows[-1]
            room = next((k for k in range(1, add + 2) if (end + k) in P.rows), add + 1) - 1
            if flag == 0 or room < add:
                n_chest_skip += 1
                continue
            for k in range(1, add + 1):
                P.add_row(end + k, bytes(sure_row(U, None, flag, template=first, weights=chest_weights(c, b))))
            n_chest += add
            n_chest_extra += c['chest_extra']
        elif t['kind'] in ('ground', 'corpse') and (c['golden'] or c['whetblade']):
            for r in rows:
                row = P.rows[r]
                sl = [s for s in erlib.lot_slots(row) if s[3] > 0]
                if len(sl) != 1 or sl[0][1] != 1:
                    continue
                whet = c['whetblade'] and sl[0][2] in WHETBLADES
                if not (whet or c['golden'] and sl[0][2] in GOLDEN_RUNES):
                    continue
                i0 = sl[0][0]
                slotflag = struct.unpack_from('<I', row, erlib.LOT_SLOTFLAG + 4 * i0)[0]
                ci = once.rng_for(ctx, 'gold', r).choices(range(3), weights=U.share)[0]   # 每行固定（这一局的种子），每次启动一样
                w = b.get('weights') or {}
                for i in range(8):
                    erlib.lot_clear_slot(row, i)
                k = 0
                tot = float(sum(w.get(rr, 0) for rr in RAR)) or 1.0
                for t_, rr in enumerate(RAR):
                    pt = int(round(1000 * w.get(rr, 0) / tot))
                    if pt > 0:
                        tier = 4 if (rr == 'Legendary' and is_dlc(b)) else t_
                        erlib.lot_set_slot(row, k, 1, goods_id(ci, tier), pt, num=1, luck=False, slotflag=slotflag)
                        k += 1
                if whet:
                    n_whet += 1
                else:
                    n_gold += 1
    # 人形 NPC
    n_npc = n_npc_skip = 0
    if c['npc']:
        try:
            nl = json.load(open(os.path.join(ctx.data_dir, 'npc_lots.json'), encoding='utf-8'))['lots']
            boss = json.load(open(os.path.join(ctx.data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses']
        except Exception:
            nl, boss = {}, []
        skip = {r for b in boss for lot in b['lots'] for r in chain(lot)}
        done = set()
        for lot in sorted(int(k) for k in nl):
            rows = chain(lot)
            if not rows or skip.intersection(rows) or done.intersection(rows):
                continue
            first = P.rows[rows[0]]
            flag = erlib.lot_flag(first)
            end = rows[-1]
            if flag == 0 or (end + 1) in P.rows or (end + 2) in P.rows:
                n_npc_skip += 1
                continue
            P.add_row(end + 1, bytes(sure_row(U, 3, flag, template=first)))
            done.update(rows + [end + 1])
            n_npc += 1
    ctx.report.append('未鉴定物品（世界）：宝箱追加 %d 件（%s；每个宝箱在原掉落外再加 %d 件，其中 %d 个出原版装备的宝箱先替换再额外加；%d 个表后面没空号没加）；'
                      '%d 处黄金卢恩【1】~【13】光点、%d 把砥石刀（砥石小刀除外）换成这个地区的未鉴定物品；'
                      '%d 个人形 NPC 的死亡掉落追加一件传说%s' % (
                          n_chest, ' / '.join('%s %g' % (RAR_ZH[r], cw[r]) for r in RAR if cw.get(r)), c['chest_extra'],
                          n_chest_gear, n_chest_skip, n_gold, n_whet, n_npc,
                          '（%d 个没加）' % n_npc_skip if n_npc_skip else ''))


def ammo_ids(ctx):
    """原版武器里的箭矢（编号）"""
    wl = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamWeapon.xml')))[0]
    o, fc = next((o, fc) for n, fc, o, *_ in wl if n == 'wepType')
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    return {i for i, r in W.rows.items() if struct.unpack_from('<' + fc, r, o)[0] in AMMO_TYPES}


# 不换成未鉴定物品的原版装备（同 rr/bosses.py 的 KEEP_GEAR）：大蛇狩猎矛，打拉卡德要用，rr/serpent.py 换成 DR 版本。它的掉落表 16000690 是事件直接发放的
# （data\direct_item_lots.json），以前被这里换成了未鉴定物品，serpent.build 找不到它（用户 2026-11-09）
KEEP_GEAR = {17030000}


def weapon_of(cat, iid):
    """武器格的本体编号（第 6 类定制武器按定制武器表查本体）；不是武器是 None"""
    if cat == CAT_CW:
        b = CUSTOM.get(iid)
        return b - b % 10000 if b and b > 0 else None
    return iid - iid % 10000 if cat == CAT_W else None


def gear_slots(row, ammo):
    """这一行里原版装备（武器 / 定制武器 / 防具 / 护符，箭矢、KEEP_GEAR 不算）的格子 [(格, 类别, 编号, 点数)]"""
    out = []
    for s in erlib.lot_slots(row):
        if s[1] not in (CAT_W, CAT_CW, CAT_P, CAT_A) or s[2] <= 0 or s[3] <= 0:
            continue
        if s[1] == CAT_CW and weapon_of(s[1], s[2]) is None:
            continue
        if s[1] == CAT_W and s[2] in ammo:
            continue
        if s[1] in (CAT_W, CAT_CW) and weapon_of(s[1], s[2]) in KEEP_GEAR:
            continue
        out.append(s)
    return out


def gear_to_unid(U, row, weights, ammo, rng):
    """这一行里每一格原版装备（武器 / 防具 / 护符，箭矢不算）就地换成未鉴定物品：这一格的点数按类别占比 × 稀有度权重分给几格，
    空格不够就按权重挑一种；件数、这一格的获取标记照旧。返回换了几格"""
    n = 0
    for i, cat, iid, pt in gear_slots(row, ammo):
        num = row[erlib.LOT_NUM + i] or 1
        slotflag = struct.unpack_from('<I', row, erlib.LOT_SLOTFLAG + 4 * i)[0]
        erlib.lot_clear_slot(row, i)
        tot = float(sum(weights.values())) or 1.0
        opts = [(goods_id(ci, t), U.share[ci] * w / tot) for ci in range(3) for t, w in weights.items() if U.share[ci] * w > 0]
        free = [i] + [k for k in range(8) if k != i and not struct.unpack_from('<H', row, erlib.LOT_PT + 2 * k)[0]
                      and not struct.unpack_from('<i', row, erlib.LOT_ID + 4 * k)[0]]
        if len(opts) > len(free):
            g = rng.choices([o[0] for o in opts], weights=[o[1] for o in opts])[0]
            opts = [(g, 1.0)]
        share = sum(o[1] for o in opts)
        pts = [int(pt * o[1] / share) for o in opts]
        pts[0] += pt - sum(pts)                       # 点数加起来和原来那一格一样
        for k, ((g, _), p) in zip(free, zip(opts, pts)):
            if p > 0:
                erlib.lot_set_slot(row, k, 1, g, p, num=num, luck=False, slotflag=slotflag)
        n += 1
    return n


QUEST_GEAR_W = (700, 100)      # 开局装备编号段里支线武器的位置、最多几把（0~499 开局装备、500~699 追忆武器、800 大蛇狩猎矛、810~899 特殊货币格子、900~999 商人；remembrance.layout_check）
QUEST_GEAR_P = (1000, 1000)    # 防具（开局防具检查 0~999，这里从 1000 起）


def quest_gear(ctx, U, rows, ammo, rng):
    """支线（用户 2026-11-10「不再把支线里的装备替换成未鉴定装备了 而是替换成相同基底的小极品」「不要换成传说 换成史诗吧」）：
    这些格子里的原版武器 / 防具就地换成同一件本体的生成装备（档 quest_gear.tier，默认史诗；武器的补正只从分布最好的
    scaling_top_pct% 里抽，同商人的小极品，items.txt 的 start 行 full = 1），dll\\dark_core 一启动按种子生成、角色拿到后记进记录；
    本体不在词条库里的、护符（生成的护符按词条挑本体，没有「同一件」）、编号段放满的，换成同档的未鉴定物品。获取标记、点数、件数照旧。
    编号先在这里占好、参数行照本体复制；startgear.build 会清空 start_items，所以 start 行先放 ctx.quest_items，quest_gear_finish 再接上。
    返回（换成生成装备的件数, 换成未鉴定的件数）；关掉（quest_gear.enabled = false）时返回 None，照以前换成未鉴定物品"""
    from . import affixes, startgear
    c = ctx.S.get('quest_gear') or {}
    if not c.get('enabled', True):
        return None
    tier = int(c.get('tier', 2))
    top = int(c.get('scaling_top_pct', 50))
    P = ctx.P_mp
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    wb, pb, nm = affixes.bases(ctx, lib)
    okw, okp = {b['id'] for b in wb}, {b['id'] for b in pb}
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    Pp = erlib.Param(ctx.bnd.get('EquipParamProtector.param'))
    wf = json.load(open(os.path.join(ctx.data_dir, 'weapon_fields.json'), encoding='utf-8'))
    origin = [(o, sz) for f, o, sz in wf['own'] if f.startswith('originEquipWep')]
    w0, ws, p0, ps = startgear.START_W0, 10000, startgear.START_P0, 100
    items, wids, pids, n_unid, names = [], [], [], 0, []
    for r in rows:
        row = P.rows[r]
        rg = rng(r)
        for i, cat, iid, pt in gear_slots(row, ammo):
            base = weapon_of(cat, iid) if cat in (CAT_W, CAT_CW) else iid
            seed = rg.randrange(1 << 31)
            if cat in (CAT_W, CAT_CW) and base in okw and len(wids) < QUEST_GEAR_W[1]:
                nid = w0 + (QUEST_GEAR_W[0] + len(wids)) * ws
                if nid in W.rows:
                    raise RuntimeError('支线的史诗武器：编号 %d 已被占用' % nid)
                startgear.copy_weapon(W, origin, base, nid)
                wids.append(nid)
                items.append({'cat': 0, 'id': nid, 'tier': tier, 'base': base, 'seed': seed, 'maxreq': [99] * 5,
                              'top': top, 'min_status': 0, 'keep': False, 'full': True})
                names.append(nm('zh', 'WeaponName', base))
            elif cat == CAT_P and base in okp and len(pids) < QUEST_GEAR_P[1]:
                nid = p0 + (QUEST_GEAR_P[0] + len(pids)) * ps
                if nid in Pp.rows:
                    raise RuntimeError('支线的史诗防具：编号 %d 已被占用' % nid)
                Pp.add_row(nid, bytes(Pp.rows[base]))
                pids.append(nid)
                items.append({'cat': 1, 'id': nid, 'tier': tier, 'base': base, 'seed': seed, 'maxreq': [99] * 5,
                              'top': 100, 'min_status': 0, 'keep': False, 'full': True})
                names.append(nm('zh', 'ProtectorName', base))
            else:
                ci = {CAT_W: 0, CAT_CW: 0, CAT_P: 1, CAT_A: 2}[cat]
                struct.pack_into('<i', row, erlib.LOT_ID + 4 * i, goods_id(ci, tier))
                struct.pack_into('<i', row, erlib.LOT_CAT + 4 * i, 1)
                n_unid += 1
                continue
            struct.pack_into('<i', row, erlib.LOT_ID + 4 * i, nid)
            struct.pack_into('<i', row, erlib.LOT_CAT + 4 * i, CAT_W if cat == CAT_CW else cat)
    ctx.bnd.put('EquipParamWeapon.param', W.serialize())
    ctx.bnd.put('EquipParamProtector.param', Pp.serialize())
    startgear.placeholders(ctx, wids, pids)
    ctx.quest_items = items
    ctx.report.append('支线装备 → 同本体的%s（武器补正取分布前 %d%%，生成要 dll\\dark_core）：武器 %d 把、防具 %d 件：%s' % (
        RAR_ZH[RAR[tier]], top, len(wids), len(pids), '、'.join(names)))
    return len(items), n_unid


def quest_gear_finish(ctx):
    """startgear.build 之后：支线的生成装备接进 start_items（items.txt 的 start 行）"""
    items = getattr(ctx, 'quest_items', None)
    if not items:
        return
    from . import startgear
    if not hasattr(ctx, 'start_ids'):
        ctx.start_ids = (startgear.START_W0, 10000, startgear.START_P0, 100)
    if not hasattr(ctx, 'start_items'):
        ctx.start_items = []
    ctx.start_items.extend(items)

def region_weights(band):
    """这个地区的未鉴定掉落稀有度：{档: 权重}（tier_bands 的 weights，同黄金卢恩；幽影之地的传说是传说（幽影之地））"""
    w = band.get('weights') or {}
    return {(4 if (r == 'Legendary' and is_dlc(band)) else k): float(w.get(r, 0)) for k, r in enumerate(RAR) if w.get(r, 0)}


def no_vanilla_gear(ctx):
    """宝箱、支线（地图掉落 QUEST_LOTS 那一段，Boss 奖励表除外）不再给原版装备（用户 2026-10-28）：每一格原版武器 / 防具 / 护符
    （箭矢不算）就地换成宝箱那份未鉴定掉落（类别按 gear_category_share，稀有度按 chest_rarity_weights，幽影之地的宝箱是传说（幽影之地）），
    原来几件就多几次；获取标记、件数照旧。支线最后一环（data\\quest_finals.json，含白面具的纯血骑士勋章）后面接 3 行必掉的
    未鉴定传说：武器 / 防具 / 护符各一行、各 quest_final_legendary 件（同一个获取标记）。
    地上 / 尸体上的光点（宝物表 ground / corpse）里的原版装备也一样换，稀有度按这个地区的 weights（同黄金卢恩；用户 2026-10-30
    「如果删除的普通武器掉落是地上的光点 那么补一份当前区域的装备掉落」）——不换的话后面 bosses.no_weapons 会把它删成什么都不掉。
    要在 world_drops 之后（宝箱后面接的那一行已经在了，不受影响）"""
    U = getattr(ctx, 'unid', None)
    if not U or not ctx.S.get('no_vanilla_gear', True):
        return
    c, P, chain = U.c, ctx.P_mp, ctx.chain
    rng = lambda r: once.rng_for(ctx, 'gear', r)   # 每行固定（这一局的种子），每次启动一样
    ammo = ammo_ids(ctx)
    tier_of = lambda m: int(ctx.map_tiers.get(m, 1))
    n_chest = n_chest_slots = 0
    for lot, t in sorted(treasure_lots(ctx).items()):
        if t['kind'] != 'chest':
            continue
        w = chest_weights(c, ctx.band_for(tier_of(t['map'])))
        k = sum(gear_to_unid(U, P.rows[r], w, ammo, rng(r)) for r in chain(lot))
        n_chest += k > 0
        n_chest_slots += k
    n_pick = n_pick_slots = 0
    for lot, t in sorted(treasure_lots(ctx).items()):
        if t['kind'] not in ('ground', 'corpse'):
            continue
        w = region_weights(ctx.band_for(tier_of(t['map'])))
        k = sum(gear_to_unid(U, P.rows[r], w, ammo, rng(r)) for r in chain(lot))
        n_pick += k > 0
        n_pick_slots += k
    try:
        boss = json.load(open(os.path.join(ctx.data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses']
    except Exception:
        boss = []
    skip = {r for b in boss for lot in b['lots'] for r in chain(lot)}
    # 任务事件用 EMEVD 2003:36 / 2003:4 直接指定的 ItemLot（light/dark sword、NPC 任务武器/套装等）：
    # 它们不在宝箱、光点或 QUEST_LOTS 段里，之前会被后面的 no_weapons 清空。这里按事件所在地区一并换成未鉴定物品。
    try:
        direct = json.load(open(os.path.join(ctx.data_dir, 'direct_item_lots.json'), encoding='utf-8'))['lots']
    except Exception:
        direct = {}
    n_direct = n_direct_slots = 0
    # 任务事件直接发放的也是支线奖励（NPC 任务武器 / 套装）：开着 quest_gear 时和支线一起换成同本体的史诗（下面 quest_gear 里做）
    if (ctx.S.get('quest_gear') or {}).get('enabled', True):
        direct = {}
    for lot_s, mapname in sorted(direct.items(), key=lambda kv: int(kv[0])):
        rows = chain(int(lot_s))
        if not rows:
            continue
        wb = chest_weights(c, ctx.band_for(tier_of(mapname)))
        k = sum(gear_to_unid(U, P.rows[r], wb, ammo, rng(r)) for r in rows)
        n_direct += k > 0
        n_direct_slots += k
    w = chest_weights(c, {})
    lo, hi = QUEST_LOTS
    qrows = [r for r in sorted(P.rows) if lo <= r <= hi and r not in skip]
    if (ctx.S.get('quest_gear') or {}).get('enabled', True):
        try:
            dl = json.load(open(os.path.join(ctx.data_dir, 'direct_item_lots.json'), encoding='utf-8'))['lots']
        except Exception:
            dl = {}
        qset = set(qrows)
        qrows += [r for lot_s in sorted(dl, key=int) for r in chain(int(lot_s)) if r not in qset and r not in skip]
    qg = quest_gear(ctx, U, qrows, ammo, rng)
    n_quest = qg[0] + qg[1] if qg else sum(gear_to_unid(U, P.rows[r], w, ammo, rng(r)) for r in qrows)
    # 支线最后一环（用户 2026-11-02「三种类型未鉴定传说各 3 件」，含白面具，以前只有白面具给 4 件）：这一组连着的行后面接 3 行
    # 必掉的未鉴定传说（武器 / 防具 / 护符各一行，每行 n_q 件），同一个获取标记、和原来的奖励一起给（后面要留一个空号）；DLC 的是传说（幽影之地）
    n_q = int(ctx.S.get('quest_final_legendary', QUEST_FINAL_N))
    try:
        finals = json.load(open(os.path.join(ctx.data_dir, 'quest_finals.json'), encoding='utf-8'))['finals'] if n_q > 0 else []
    except Exception:
        finals = []
    q_ok, q_miss = [], []
    for f in finals:
        rows = chain(f['lot'])
        if not rows:
            q_miss.append('%s（%d 不在了）' % (f['npc'], f['lot']))
            continue
        end, first = rows[-1], P.rows[rows[0]]
        if any((end + k) in P.rows for k in range(1, 3 + 2)):
            q_miss.append('%s（%d 后面没有空号）' % (f['npc'], end))
            continue
        for ci in range(3):
            row = blank_row(first)
            erlib.lot_set_slot(row, 0, 1, goods_id(ci, 4 if f.get('dlc') else 3), 1000, num=n_q, luck=False, slotflag=0)
            struct.pack_into('<I', row, erlib.LOT_FLAG, erlib.lot_flag(first))
            P.add_row(end + 1 + ci, bytes(row))
        q_ok.append(f['npc'])
    medal = '支线最后一环多给未鉴定传说武器、防具、护符各 %d 件：%d 条支线%s' % (n_q, len(q_ok), '；没加：' + '、'.join(q_miss) if q_miss else '')
    quest_txt = ('支线奖励（%d~%d，Boss 奖励表除外，含任务事件直接发放的）里的 %d 件换成同本体的生成装备 %d 件、未鉴定物品 %d 件，' % (lo, hi, n_quest, qg[0], qg[1])
                 if qg else '支线奖励（%d~%d，Boss 奖励表除外）里的 %d 件、任务事件直接发放的 %d 个掉落表里的 %d 件换成未鉴定物品，' % (lo, hi, n_quest, n_direct, n_direct_slots))
    ctx.report.append('未鉴定物品（不给原版装备）：%s%d 个宝箱里的 %d 件原版装备换成未鉴定物品（%s）；'
                      '%d 处地上 / 尸体光点里的 %d 件原版装备换成这个地区的未鉴定物品；%s' % (
        quest_txt, n_chest, n_chest_slots,
        ' / '.join('%s %g' % (RAR_ZH[r], c['chest_weights'][r]) for r in RAR if c['chest_weights'].get(r)),
        n_pick, n_pick_slots, medal))
