# -*- coding: utf-8 -*-
"""骨灰稀有度 + 词条（用户 2026-11-09 / 10，提案 dev\\item_system\\骨灰词条提案.md；settings 的 spirit_ash_rarity）。
做法照装备系统的容器：这里只建空容器和定义文件 dll\\dark_core\\ashes.txt，内容由 dark_core（gear\\ashes.rs）在游戏里按需写——
  - 每个容器 c 占连续 11 个道具编号 GOODS0 + 100c + L（L = 强化等级 0~10；原版骨灰也是本体编号 + 等级，召唤效果编号 = 道具编号），
    同号的召唤效果（照原版骨灰的召唤效果复制），每级一行强化加成效果 DOP0 + 11c + L（召唤参数的 dopingSpEffect_lvL，
    dark_core 照原版那一级的加成复制、再乘稀有度倍率和数值词条），召唤参数 BUDDY0 + PER·c + k（照原版那几行复制，集结多一行）。
    召唤物还是原版那只（敌人参数编号里带模型号，不能复制换号）。
  - 容器按召唤只数分组（pools：召唤 1 / 2 / 3 / 4 / 5 只的各几个；用户 2026-11-10 测出集结那一只没出来）：游戏进存档时按召唤参数的
    触发效果建「召唤效果 → 召唤参数」表，之后 dark_core 再改触发效果不认，所以每个容器的那几行和触发效果这里就写好，
    dark_core 只改行的内容；拿到骨灰时挑只数对得上的那一组。
  - 仿身泪滴另有专用容器（mimic_pools：召唤 2 只 / 3 只的各几个，排在最后）：游戏写死了「这一组召唤参数里有 20700000（原版仿身泪滴
    的银色泪滴那一行）」才复制召唤者的装备和属性（用户 2026-11-10 测出容器里的仿身穿的是默认装备），dark_core（gear\\ashes\\mimic.rs）
    把那两处判断改成这一段的召唤参数也算（ashes.txt 的 mimic 行给编号范围）。仿身那一行原版用自己那套强化加成（290200 系列），
    专用容器另有一套强化加成 DOP1 + 11·c + L（dop1 行）。
  - 文字占位（同装备容器，containers.placeholder）：每个编号的名字 / 简介 / 说明，左边骨灰血条上的名字（GoodsInfo2）用另一个编号
    INFO2_OFF + 道具编号的名字字段（同一个编号两处占位会被写成一样的）。
  - 原版骨灰不改：不管从哪拿到（掉落、宝箱、Boss、商店、NPC 给的），进背包后 dark_core 换成一个容器——种类、强化等级不变，
    稀有度按 weights 抽（用户 2026-11-10「传说概率为10% 史诗20% 稀有30%」），数值词条均匀抽（用户「词条均匀分布」），
    传说必带集结（召唤数量 +1，复制原版最后一行；仿身泪滴是多一个仿身，原版 5 只的变 6 只。以前用玩家形象的不带，
    2026-11-10 看了 ELDEN VINS：它的仿身泪滴一次召唤 5 个共用玩家形象参数的仿身，就放开了）。
  - 第二期（用户 2026-11-10「做一下第二期 然后把日志做好」）：机制前缀（提案的 C 类）爆裂 / 殉道 / 激昂 / 庇护 / 共鸣 / 战意，
    稀有度按 prefix_chance 的几率带一条（每条一样的几率），效果全在 dark_core（gear\\ashes\\fx.rs）运行时做：这里只建它要的参数行——
    爆裂的爆炸子弹 + 攻击行（照词条库的火焰爆炸 BLAST_BULLET 复制，攻击行进 procs.txt 随信仰补正）、激昂挂召唤物的攻击加成、
    庇护 / 共鸣挂召唤者的减伤 / 攻击加成（照咒痕的玩家效果做）；殉道、战意 dark_core 直接改血量，不用参数。
定义文件：cont / rar / aff / lvl / rally / kind 行（格式见 def_lines 的注释）；ashcx 行给词条百科（dll\\dark_ui 的 ui/codex.rs「骨灰」一栏），
dark_core 不读。"""
from .common import *  # noqa: F401,F403
from .affixes import esc
from . import containers
from . import ashtest
from . import ashes as ashshuffle

GOODS0 = 400000                 # 容器道具 / 召唤效果编号的起点：原版骨灰 200000~264010 / 2200000 起，400000~411999 道具、效果都空着。
                                # 2026-11-10 从 150000000 挪下来：那一段菜单读不到道具行（名字 ?GoodsName?、专注消耗 –、持有上限 99），装备容器的大编号没事
INFO2_OFF = 10000000            # 血条名字占位的编号 = 道具编号 + 这个
DOP0, NEUTRAL = 7320000, 7319999   # 强化加成效果；没有原版加成的那一级用的「不加成」效果
BUDDY0, PER = 39900000, 6       # 召唤参数（原版一种骨灰最多 5 只，集结再多一只 = 6）
LEVELS = 11
TRIGGER_TEMPLATE, DOP_TEMPLATE, BUDDY_TEMPLATE = 200000, 290000, 20000000    # 「黑刀」狄希的召唤效果、原版 +0 加成、召唤参数
DEFAULT = dict(enabled=True, pools=[300, 120, 60, 30, 36, 12], weights=[40, 30, 20, 10], mult=[1.0, 1.05, 1.1, 1.2], suffixes=[1, 1, 2, 2], rally=True,
               prefix_chance=[0, 30, 60, 100], mimic_pools=[8, 8], boss_drop=[1, 1], reserve=True)
# reserve：原版骨灰的获取格（地图 / 敌人掉落、商店）直接放容器（用户 2026-11-11「去掉一下原版骨灰的掉落 … 应该是以我们的作为替换」）：
# def_lines 写 src 行，dark_core 进存档时给还没拿的每一格抽好一个、把格子改成它，地上捡起、商店里看到的就是带稀有度、词条的
# boss_drop：难度里标了 lock 的档（死亡 / 不可能）每个 Boss 战第一次击败掉几个随机原版骨灰（dark_core 的 ovldrop 发，进背包照常换容器；
# 用户 2026-11-10「死亡模式下每个boss都会掉落随机骨灰 抽取及分布还是和现在一样 顺便给骨灰容器扩容」）
# 原版骨灰按只数：1 只 53 种、2 只 15、3 只 8、4 只 3、5 只 5（集结 +1，最多 6）；pools 是召唤 1~6 只的各留几个容器
# 数值词条（后缀，提案的 A 类）：键、改的字段、普通 / 稀有 / 史诗 / 传说的数值、说明（# 换成数值）
AFFIXES = [
    ('hp', 'hp', (10, 15, 20, 30), '召唤物的血量上限＋#％', 'Summon max HP +#%'),
    ('atk', 'atk', (8, 12, 16, 24), '召唤物的攻击力＋#％', 'Summon attack +#%'),
    ('cut', 'cut', (5, 8, 11, 15), '召唤物受到的伤害－#％', 'Summon damage taken -#%'),
    ('poise', 'poise', (15, 25, 35, 50), '召唤物受到的削韧－#％', 'Summon poise damage taken -#%'),
    ('resist', 'resist', (20, 35, 50, 80), '召唤物所有异常状态的抗性＋#％', 'Summon status resistance +#%'),
    ('regen', 'regen', (0.5, 0.8, 1.2, 1.5), '召唤物每秒恢复 #％ 的血量', 'Summons restore #% HP per second'),
    ('cost', 'cost', (10, 15, 20, 30), '召唤消耗的专注值－#％', 'Summoning FP cost -#%'),
]
RALLY = ('集结', 'Rallying', '召唤数量＋1', 'Summons one more spirit')
BONUS = ('召唤物的血量上限、攻击力＋#％（稀有度）', 'Summon max HP and attack +#% (rarity)')
# 机制词条（前缀，提案的 C 类；dark_core gear\\ashes\\fx.rs 运行时做）：键、做法、普通 / 稀有 / 史诗 / 传说的数值、参数（激昂 = 血量线 %、
# 战意 = 离召唤者几米内的敌人）、名字、说明（# 换成数值，{a} 换成参数）、各档都一样的补充说明（百科用）
PREFIXES = [
    ('blast', 'blast', (250, 300, 400, 550), 0, '爆裂', 'Bursting', '召唤物倒下时爆炸，造成 # 点火焰伤害（随召唤者的信仰提升）',
     'Summons explode when they fall, dealing # fire damage (scales with your Faith)', ('每只召唤物倒下时各炸一次', 'Each summon explodes once when it falls')),
    ('martyr', 'martyr', (10, 15, 20, 30), 0, '殉道', "Martyr's", '召唤物倒下时，召唤者恢复 #％ 的血量',
     'When a summon falls, you restore #% HP', ('每只召唤物倒下时各回一次', 'Triggers once for each summon that falls')),
    ('fury', 'fury', (15, 20, 30, 40), 30, '激昂', 'Frenzied', '召唤物血量低于 {a}％ 时，攻击力＋#％',
     'Summons below {a}% HP gain +#% attack', ('血量回到 {a}％ 以上就没有了', 'Ends when its HP is back above {a}%')),
    ('shelter', 'shelter', (3, 5, 7, 10), 0, '庇护', 'Sheltering', '有召唤物在场时，召唤者受到的伤害－#％',
     'While a summon is present, you take #% less damage', ('召唤物都倒下或消失后就没有了', 'Ends when no summon is left')),
    ('resonance', 'resonance', (3, 5, 7, 10), 0, '共鸣', 'Resonant', '有召唤物在场时，召唤者的攻击力＋#％',
     'While a summon is present, your attack +#%', ('魔法、祷告也算；召唤物都倒下或消失后就没有了', 'Sorceries and incantations included; ends when no summon is left')),
    ('zeal', 'zeal', (5, 8, 12, 20), 20, '战意', 'Spirited', '召唤者附近的敌人死亡时，所有召唤物恢复 #％ 的血量',
     'When an enemy near you dies, all summons restore #% HP', ('召唤者 {a} 米内的敌人，不管是谁击败的', 'Enemies within {a} m of you, whoever defeats them')),
]
BLAST_BULLET, BLAST_ATK = 93000113, 307000036   # 词条库的火焰爆炸（原地炸开、半径 0.1 → 3.5 米，特效 524083），爆裂照它复制
BULLET0, ATK0 = 94900000, 308900000             # 爆裂的子弹 / 攻击行从这里往后找空号（procs.py 的复制从 94000000 / 308000000 起）
PRE_SP0 = 7319900                               # 激昂 / 庇护 / 共鸣的效果：PRE_SP0 + 10 × 序号 + 稀有度
MIMIC_KIND = 207000                             # 仿身泪滴（专用容器）
DOP1 = 7330000                                  # 专用容器的第二套强化加成（仿身那一行）：DOP1 + 11 × 容器 + 等级（DOP0 那一段扩容后到 7326314）
PLAYER_TEMPLATE = 360400                        # 玩家身上的常驻效果（同 rr/curses.py：长尾猫护符的效果）
PRE_ICON = {'shelter': 20008, 'resonance': 20006}  # 召唤者身上的状态图标：原版的「防御力提升」「攻击力提升」
SPELL_FLAGS = ('magParamChange', 'miracleParamChange', 'shamanParamChange')
CUTS = ('slashDamageCutRate', 'blowDamageCutRate', 'thrustDamageCutRate', 'neutralDamageCutRate',
        'magicDamageCutRate', 'fireDamageCutRate', 'thunderDamageCutRate', 'darkDamageCutRate')
ATKS = ('physicsAttackRate', 'magicAttackRate', 'fireAttackRate', 'thunderAttackRate', 'darkAttackRate')
POWERS = ('physicsAttackPowerRate', 'magicAttackPowerRate', 'fireAttackPowerRate', 'thunderAttackPowerRate', 'darkAttackPowerRate')
# 词条百科「骨灰」一栏：键 → 名字（提案里的）、原图标（dr_frames.txt 第一列，界面换成各稀有度带框的；
# data\\codex_icons.json 里写 ash_<键> 优先）。rarity = 稀有度那一条，rally = 集结
CODEX = {
    'rarity': ('稀有度', 'Rarity', 18040),         # 黄金树的恩惠
    'rally': (RALLY[0], RALLY[1], 18880),          # 祖灵角
    'hp': ('坚韧', 'Sturdy', 18000),               # 红琥珀链坠
    'atk': ('锋锐', 'Keen', 18280),                # 献斗剑护符
    'cut': ('坚甲', 'Armored', 18490),             # 龙徽盾护符
    'poise': ('稳固', 'Steadfast', 18220),         # 大山羊护符
    'resist': ('清明', 'Lucid', 18170),            # 健壮角饰品
    'regen': ('再生', 'Regenerating', 18630),      # 恩惠露滴护符
    'cost': ('节俭', 'Frugal', 18480),             # 源辉石刀
    'blast': ('爆裂', 'Bursting', 18250),          # 火对蝎
    'martyr': ('殉道', "Martyr's", 18750),        # 牺牲细枝
    'fury': ('激昂', 'Frenzied', 18270),           # 红羽七刃剑
    'shelter': ('庇护', 'Sheltering', 18580),      # 献斗盾护符
    'resonance': ('共鸣', 'Resonant', 18810),      # 狂怒咆哮
    'zeal': ('战意', 'Spirited', 18870),           # 战士壶碎片
}


def cfg(S):
    c = S.get('spirit_ash_rarity') or {}
    if not c.get('enabled', True):
        return None
    out = dict(DEFAULT)
    out.update({k: c[k] for k in DEFAULT if k in c and k != 'enabled'})
    return out


def _lay(ctx, xml):
    path = os.path.join(ctx.data_dir, xml + '.xml')
    if not os.path.exists(path):
        path = os.path.join(ctx.a.randomizer_dir or os.path.normpath(os.path.join(ctx.data_dir, '..', '..', '..', 'randomizer')), 'diste', 'Defs', xml + '.xml')
    return {n: (o, fc, bp, bits) for n, fc, o, bp, bits, _ in pdm.layout(pdm.load(path))[0]}


def _get(L, row, f):
    o, fc, bp, bits = L[f]
    v = struct.unpack_from('<' + fc, row, o)[0]
    if bits and bits < 8 * struct.calcsize(fc):
        v = (v >> (bp or 0)) & ((1 << bits) - 1)
    return v


def _put(L, row, f, v):
    o, fc, bp, bits = L[f]
    if bits:
        raise RuntimeError('骨灰容器：%s 是位字段' % f)
    struct.pack_into('<' + fc, row, o, v)


def _bit(L, row, f, on):
    o, fc, bp, bits = L[f]
    row[o] = (row[o] | (1 << (bp or 0))) if on else (row[o] & ~(1 << (bp or 0)))


def _free(P, start, n=1):
    i = start
    while any(i + k in P.rows for k in range(n)):
        i += 1
    return i


def prefix_rows(ctx, S, LS, c):
    """机制前缀要的参数行；返回 [(键, 做法, 四档数值, 参数, 四档编号, 名字中, 名字英, 说明中, 说明英, 补充中, 补充英)]（建不了的前缀不在里面）"""
    if not any(float(x) > 0 for x in c['prefix_chance']):
        return []
    LBu, LAt = _lay(ctx, 'BulletParam'), _lay(ctx, 'AtkParam')
    Bu, At = erlib.Param(ctx.bnd.get('Bullet.param')), erlib.Param(ctx.bnd.get('AtkParam_Pc.param'))
    procs = getattr(ctx, 'procs', None)
    out, note = [], []
    for j, (key, kind, vals, arg, zh, en, tzh, ten, nt) in enumerate(PREFIXES):
        fmt = lambda t: t.replace('{a}', '%g' % arg)
        ids = [0, 0, 0, 0]
        if kind == 'blast':
            if BLAST_BULLET not in Bu.rows or BLAST_ATK not in At.rows:
                note.append('爆裂（没有词条库的爆炸子弹 %d）' % BLAST_BULLET)
                continue
            for r in range(4):
                bid, aid = _free(Bu, BULLET0), _free(At, ATK0)
                a = bytearray(At.rows[BLAST_ATK])
                for f, v in zip(('atkPhys', 'atkMag', 'atkFire', 'atkThun', 'atkDark'), (0, 0, int(vals[r]), 0, 0)):
                    _put(LAt, a, f, v)
                At.add_row(aid, bytes(a))
                b = bytearray(Bu.rows[BLAST_BULLET])
                _put(LBu, b, 'atkId_Bullet', aid)
                Bu.add_row(bid, bytes(b))
                ids[r] = bid
                if procs is not None:
                    procs['atk'][aid] = [0, 0, int(vals[r]), 0, 0]   # 进 procs.txt：火焰伤害随信仰补正
        elif kind in ('fury', 'shelter', 'resonance'):
            for r in range(4):
                rid = PRE_SP0 + 10 * j + r
                if rid in S.rows:
                    raise RuntimeError('骨灰容器：前缀效果编号 %d 已经有人用了' % rid)
                if kind == 'fury':
                    row = bytearray(S.rows[NEUTRAL])                 # 同强化加成（挂召唤物身上）
                    for f in POWERS:
                        _put(LS, row, f, 1 + vals[r] / 100.0)
                else:
                    row = bytearray(S.rows[PLAYER_TEMPLATE])         # 同咒痕的玩家效果：常驻、不存档、死了不删、休息不清，dark_core 补挂 / 摘
                    _put(LS, row, 'iconId', PRE_ICON[kind])
                    _put(LS, row, 'effectEndurance', -1.0)
                    _put(LS, row, 'fallDamageRate', 1.0)
                    _put(LS, row, 'spCategory', 0)
                    _put(LS, row, 'saveCategory', -1)
                    _bit(LS, row, 'eraseOnBonfireRecover', False)
                    _bit(LS, row, 'dontDeleteOnDead', True)
                    if kind == 'shelter':
                        for f in CUTS:
                            _put(LS, row, f, 1 - vals[r] / 100.0)
                    else:
                        for f in ATKS:
                            _put(LS, row, f, 1 + vals[r] / 100.0)
                        for f in SPELL_FLAGS:
                            _bit(LS, row, f, True)
                S.add_row(rid, bytes(row))
                ids[r] = rid
        out.append((key, kind, vals, arg, ids, zh, en, fmt(tzh), fmt(ten), fmt(nt[0]), fmt(nt[1])))
    ctx.bnd.put('Bullet.param', Bu.serialize())
    ctx.bnd.put('AtkParam_Pc.param', At.serialize())
    if note:
        ctx.report.append('骨灰机制前缀：不做 %s' % '、'.join(note))
    return out


def kinds(ctx, G, B, LG, LB):
    """原版骨灰：本体编号 → (能强化到几级 + 1, 用不用玩家形象, 召唤参数行)"""
    by_trig = {}
    for i, r in sorted(B.rows.items()):
        by_trig.setdefault(_get(LB, r, 'triggerSpEffectId'), []).append(i)
    out = {}
    for k, r in sorted(G.rows.items()):
        if k % 100 or _get(LG, r, 'goodsType') not in (7, 8) or k == ashtest.GOODS or GOODS0 <= k < GOODS0 + 100 * 1000:
            continue
        # 召唤参数按道具的召唤效果编号对（本体的骨灰两者一样；DLC 的不一样：咒剑士米拉 2200000 → 召唤效果 20200000）
        rows = by_trig.get(_get(LG, r, 'refId_default'))
        if not rows:
            continue
        lv = 1
        while lv < LEVELS and k + lv in G.rows:
            lv += 1
        special = any(_get(LB, B.rows[i], 'npcPlayerInitParamId') >= 0 for i in rows)
        out[k] = (lv, special, rows[:PER - 1])
    return out


def build(ctx):
    ctx.ashcont = None
    c = cfg(ctx.S)
    if not c or not getattr(ctx, 'containers', None):
        return
    pools = [int(x) for x in c['pools']][:PER]
    LG, LS, LB = _lay(ctx, 'EquipParamGoods'), _lay(ctx, 'SpEffect'), _lay(ctx, 'BuddyParam')
    G, S, B = (erlib.Param(ctx.bnd.get(x)) for x in ('EquipParamGoods.param', 'SpEffectParam.param', 'BuddyParam.param'))
    for P, k in ((G, TRIGGER_TEMPLATE), (S, TRIGGER_TEMPLATE), (S, DOP_TEMPLATE), (B, BUDDY_TEMPLATE)):
        if k not in P.rows:
            raise RuntimeError('骨灰容器：模板 %d 不在参数里' % k)
    ks = kinds(ctx, G, B, LG, LB)
    # 仿身泪滴专用：原版 2 行（银色泪滴 + 仿身），集结 3 行
    mpools = [int(x) for x in c['mimic_pools']][:2] if MIMIC_KIND in ks else [0, 0]
    n_gen = sum(pools)
    n = n_gen + sum(mpools)
    count = [m + 1 for m, k in enumerate(pools) for _ in range(k)] + [2] * mpools[0] + [3] * mpools[1]   # 容器 → 召唤几只
    mimic = list(range(n_gen, n))
    taken = [i for i in range(GOODS0, GOODS0 + 100 * n) if i in G.rows or i in S.rows] + \
        [i for i in range(DOP0 - 1, DOP0 + LEVELS * n) if i in S.rows] + [i for i in range(BUDDY0, BUDDY0 + PER * n) if i in B.rows] + \
        [DOP1 + LEVELS * ci + lv for ci in mimic for lv in range(LEVELS) if DOP1 + LEVELS * ci + lv in S.rows]
    if taken:
        raise RuntimeError('骨灰容器：编号已被占用 %s…' % taken[:5])
    # 「不加成」：照原版 +0 加成复制，倍率都改成 1
    neutral = bytearray(S.rows[DOP_TEMPLATE])
    for f in [f for f in LS if f.endswith('Rate') and LS[f][1] == 'f' and abs(_get(LS, neutral, f) - 1.0) > 1e-6 and
              any(x in f for x in ('maxHp', 'AttackPowerRate', 'DamageCutRate', 'regist', 'saReceive'))]:
        _put(LS, neutral, f, 1.0)
    S.add_row(NEUTRAL, bytes(neutral))
    pres = prefix_rows(ctx, S, LS, c)
    for ci in range(n):
        base = GOODS0 + 100 * ci
        for lv in range(LEVELS):
            g = bytearray(G.rows[TRIGGER_TEMPLATE + lv] if TRIGGER_TEMPLATE + lv in G.rows else G.rows[TRIGGER_TEMPLATE])
            _put(LG, g, 'refId_default', base + lv)
            _put(LG, g, 'reinforceGoodsId', base + lv + 1 if lv + 1 < LEVELS else -1)
            G.add_row(base + lv, bytes(g))
            S.add_row(base + lv, bytes(S.rows[TRIGGER_TEMPLATE]))
            S.add_row(DOP0 + LEVELS * ci + lv, bytes(S.rows[DOP_TEMPLATE]))
            if ci in mimic:
                S.add_row(DOP1 + LEVELS * ci + lv, bytes(S.rows[DOP_TEMPLATE]))
        for k in range(count[ci]):
            r = bytearray(B.rows[BUDDY_TEMPLATE])
            _put(LB, r, 'triggerSpEffectId', base)        # 触发效果写死：游戏只认进存档时的
            B.add_row(BUDDY0 + PER * ci + k, bytes(r))
    for P, name in ((G, 'EquipParamGoods'), (S, 'SpEffectParam'), (B, 'BuddyParam')):
        ctx.bnd.put(name + '.param', P.serialize())
    # 文字：容器的占位；原版骨灰的文字（dark_core 照它拼）
    texts = {}
    ids = [GOODS0 + 100 * ci + lv for ci in range(n) for lv in range(LEVELS)]
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for fmg, field, off in (('GoodsName.fmg', 'N', 0), ('GoodsInfo.fmg', 'I', 0), ('GoodsCaption.fmg', 'C', 0), ('GoodsInfo2.fmg', 'N', INFO2_OFF)):
            if fmg not in mb.entries:
                continue
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            merged = dict(d)
            for dlc in ('_dlc01', '_dlc02'):                     # DLC 骨灰（咒剑士米拉 2200000 这些）的文字在 DLC 那几张表
                name = fmg.replace('.fmg', dlc + '.fmg')
                if name in mb.entries:
                    merged.update({i: t for i, t in erlib.read_fmg_full(mb.get(name))[1] if t})
            texts[(lang, fmg)] = merged
            # 名字每级不一样（＋N）；简介 / 说明 / 血条名字各级一样，共用 +0 那个占位（write_fmg 只存一份，dark_core 写一次）
            share = fmg != 'GoodsName.fmg'
            d.update({i: containers.placeholder((i - i % 100 if share else i) + off, field, lang) for i in ids})
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    tx = lambda lang, fmg, i: (texts.get((lang, fmg)) or {}).get(i) or ''
    kl = []
    for k, (lv, special, rows) in ks.items():
        kl.append((k, lv, special, rows, [tx(l, f, k) for f in ('GoodsName.fmg', 'GoodsInfo.fmg', 'GoodsCaption.fmg', 'GoodsInfo2.fmg') for l in ('zh', 'en')]))
    # 等级后缀：照原版名字（本体名后面接的那一段）
    sample = next((k for k, v in ks.items() if v[0] == LEVELS), None)
    lvl = []
    for lv in range(LEVELS):
        pair = []
        for l in ('zh', 'en'):
            b0, bl = tx(l, 'GoodsName.fmg', sample) if sample else '', tx(l, 'GoodsName.fmg', sample + lv) if sample else ''
            pair.append(bl[len(b0):] if lv and bl.startswith(b0) else ('' if not lv else ('＋%s' % ''.join(chr(0xFF10 + int(x)) for x in str(lv)) if l == 'zh' else ' +%d' % lv)))
        lvl.append(pair)
    ctx.ashcont = dict(c=c, n=n, kinds=kl, lvl=lvl, pre=pres, pools=pools, mimic=(n_gen, mpools))
    ctx.features['ashcont'] = {'goods0': GOODS0, 'n': n}
    ctx.report.append('骨灰稀有度：%d 种原版骨灰，%d 个容器（召唤 1~6 只各 %s 个，仿身泪滴专用 2 只 / 3 只各 %s 个；道具 %d 起每个 100 号、强化加成 %d 起、召唤参数 %d 起），稀有度权重 %s，'
                      '数值词条 %d 条均匀抽，机制前缀 %d 条（%s，几率 %s），传说带集结（dll\\dark_core 拿到原版骨灰时换成容器）'
                      % (len(kl), n, '/'.join(map(str, pools)), '/'.join(map(str, mpools)), GOODS0, DOP0, BUDDY0, c['weights'], len(AFFIXES), len(pres), '、'.join(p[5] for p in pres), c['prefix_chance']))


def def_lines(ctx):
    a = getattr(ctx, 'ashcont', None)
    if not a:
        return []
    c = a['c']
    out = ['# cont <道具起点> <容器数> <强化加成起点> <不加成效果> <召唤参数起点> <每个容器几行> <血条名字占位偏移>',
           'cont\t%d\t%d\t%d\t%d\t%d\t%d\t%d' % (GOODS0, a['n'], DOP0, NEUTRAL, BUDDY0, PER, INFO2_OFF),
           '# pool <召唤几只> <第一个容器> <几个>（召唤参数行和触发效果重随写死了，只能放只数对得上的骨灰）']
    first = 0
    for m, k in enumerate(a['pools']):
        out.append('pool\t%d\t%d\t%d' % (m + 1, first, k))
        first += k
    n_gen, mp = a['mimic']
    if sum(mp):
        out.append('# pool … <原版骨灰本体>：只给这种骨灰用；mimic <召唤参数编号起> <止>：仿身泪滴专用容器的召唤参数（dark_core 改游戏的仿身判断认这一段）；'
                   'dop1 <起>：专用容器的第二套强化加成（仿身那一行），编号 = 起 + 11 × 容器 + 等级')
        out.append('pool\t2\t%d\t%d\t%d' % (n_gen, mp[0], MIMIC_KIND))
        out.append('pool\t3\t%d\t%d\t%d' % (n_gen + mp[0], mp[1], MIMIC_KIND))
        out.append('mimic\t%d\t%d' % (BUDDY0 + PER * n_gen, BUDDY0 + PER * (n_gen + sum(mp))))
        out.append('dop1\t%d' % DOP1)
    ash = (ctx.features or {}).get('difficulty_ash') or []
    if ash:
        out.append('# diffash <玩家身上的难度效果> <召唤物挂的造成伤害效果>：局内难度那一档的造成伤害倍率，召唤物也挂（rr/difficulty.py；用户 2026-11-17「让骨灰也会被难度减伤」）')
        out += ['diffash	%d	%d' % x for x in ash]
    out.append('# rar <稀有度 0~3> <权重> <血量 / 攻击倍率> <数值词条几条> <带不带集结> <带机制前缀的几率 %>')
    out += ['rar\t%d\t%d\t%g\t%d\t%d\t%g' % (r, int(c['weights'][r]), float(c['mult'][r]), int(c['suffixes'][r]), 1 if c['rally'] and r == 3 else 0,
                                          float(c['prefix_chance'][r])) for r in range(4)]
    out.append('# aff <键> <字段 hp/atk/cut/poise/resist/regen/cost> <四档数值> <说明中文> <说明英文>（# 换成数值）；bonus 同格式（稀有度的血量、攻击加成那一行）')
    out += ['aff\t%s\t%s\t%s\t%s\t%s' % (k, f, ','.join('%g' % v for v in vals), esc(zh), esc(en)) for k, f, vals, zh, en in AFFIXES]
    out.append('bonus\t%s\t%s' % (esc(BONUS[0]), esc(BONUS[1])))
    out.append('rally\t%s\t%s\t%s\t%s' % tuple(esc(x) for x in RALLY))
    out.append('# pre <键> <做法 blast/martyr/fury/shelter/resonance/zeal> <四档数值> <参数> <四档编号：爆裂 = 子弹、激昂 / 庇护 / 共鸣 = 效果> '
               '<名字中> <名字英> <说明中> <说明英>（# 换成数值）')
    out += ['pre\t%s\t%s\t%s\t%g\t%s\t%s\t%s\t%s\t%s' % (k, kind, ','.join('%g' % v for v in vals), arg, ','.join(map(str, ids)), esc(zh), esc(en), esc(tzh), esc(ten))
            for k, kind, vals, arg, ids, zh, en, tzh, ten, _, _ in a.get('pre') or []]
    out.append('# lvl <等级> <中文后缀> <英文后缀>（名字里接在本体名后面）')
    out += ['lvl\t%d\t%s\t%s' % (lv, esc(p[0]), esc(p[1])) for lv, p in enumerate(a['lvl'])]
    out.append('# kind <本体编号> <等级数> <用玩家形象 1/0> <召唤参数行,…> <名字 中 / 英> <简介 中 / 英> <说明 中 / 英> <血条名字 中 / 英>')
    out += ['kind\t%d\t%d\t%d\t%s\t%s' % (k, lv, 1 if sp else 0, ','.join(map(str, rows)), '\t'.join(esc(x) for x in t)) for k, lv, sp, rows, t in a['kinds']]
    return out + src_lines(ctx, a) + codex_lines(ctx, c)


def src_lines(ctx, a):
    """原版骨灰的获取格（settings 的 spirit_ash_rarity.reserve）：最后的掉落表 / 商店里放着原版骨灰的格。
    - 地图 / 敌人掉落表：只要有拿过标记的格（格的标记，没有就用整行的）；没有标记的是事件换骨灰用的那几行（约兰那两种 +1~+10），
      拿没拿过看不出来，留原版，进背包后照旧换；许愿池那段（同 ashes.WISH）不算；一格不止 1 个的不算。
    - 商店：限 1 件的给库存计数标记（dark_core 看卖没卖过），不限的给 0（一直备着）。"""
    if not a['c'].get('reserve', True):
        return []
    ids = {k + lv for k, n, *_ in a['kinds'] for lv in range(n)}
    out = ['# src <m 地图 / e 敌人 / s 商店> <行> <格 0~7（商店 0）> <原版骨灰道具> <拿过的标记（商店 = 库存计数标记起点）；0 = 看不出来，一直备着>']
    n_lot, skip = Counter(), 0
    for t, P in (('m', ctx.P_mp), ('e', ctx.P_en)):
        for rid in sorted(P.rows):
            if t == 'm' and ashshuffle.WISH[0] <= rid <= ashshuffle.WISH[1]:
                continue
            row = P.rows[rid]
            lf = struct.unpack_from('<I', row, erlib.LOT_FLAG)[0]
            for i, cat, iid, _pt in erlib.lot_slots(row):
                if cat != 1 or iid not in ids or row[erlib.LOT_NUM + i] != 1:
                    continue
                flag = struct.unpack_from('<I', row, erlib.LOT_SLOTFLAG + 4 * i)[0] or lf
                if not flag:
                    skip += 1
                    continue
                out.append('src\t%s\t%d\t%d\t%d\t%d' % (t, rid, i, iid, flag))
                n_lot[t] += 1
    LP = _lay(ctx, 'ShopLineupParam')
    SP = erlib.Param(ctx.bnd.get('ShopLineupParam.param'))
    n_shop = 0
    for rid in sorted(SP.rows):
        r = SP.rows[rid]
        if _get(LP, r, 'equipType') != 3 or _get(LP, r, 'equipId') not in ids:
            continue
        flag = _get(LP, r, 'eventFlag_forStock') if _get(LP, r, 'sellQuantity') == 1 else 0
        out.append('src\ts\t%d\t0\t%d\t%d' % (rid, _get(LP, r, 'equipId'), flag))
        n_shop += 1
    ctx.report.append('骨灰获取格：地图掉落 %d 格、敌人掉落 %d 格、商店 %d 行直接放容器（dark_core 进存档时抽好）；没有拿过标记的 %d 格留原版（进背包后再换）'
                      % (n_lot['m'], n_lot['e'], n_shop, skip))
    return out


def codex_lines(ctx, c):
    a = ctx.ashcont
    """词条百科「骨灰」一栏（dark_ui 的 ui/codex.rs）：ashcx <键> <名字 中 / 英> <前缀 1 / 后缀 0 / 都不是 -> <原图标×4>
    <普通 中 / 英> <稀有 中 / 英> <史诗 中 / 英> <传说 中 / 英>（这一档没有就空着；同一条各档一样的行界面合起来写一次）"""
    p = os.path.join(ctx.data_dir, 'codex_icons.json')
    over = json.load(open(p, encoding='utf-8')) if os.path.isfile(p) else {}

    def line(key, mech, texts):
        zh, en, icon = CODEX[key]
        icon = over.get('ash_' + key) or icon
        return '\t'.join(['ashcx', 'ash_' + key, esc(zh), esc(en), mech, ','.join([str(icon)] * 4)]
                         + [esc(x) for t in texts for x in t])

    rar = []                                   # 拿到时是哪一档的几率不写（用户 2026-11-10：斗技场试炼按竞技场另有一套）
    for r in range(4):
        bonus = round((float(c['mult'][r]) - 1) * 100)
        n, rally = int(c['suffixes'][r]), c['rally'] and r == 3
        pc = float(c['prefix_chance'][r]) if a.get('pre') else 0
        pz = '' if pc <= 0 else ('，必带 1 条机制前缀' if pc >= 100 else '，%g％ 几率再带 1 条机制前缀' % pc)
        pe = '' if pc <= 0 else (', always 1 mechanic prefix' if pc >= 100 else ', %g%% chance of 1 mechanic prefix' % pc)
        rar.append(('\n'.join([('召唤物的血量上限、攻击力＋%d％' % bonus) if bonus > 0 else '召唤物的血量上限、攻击力不加成',
                               '带 %d 条数值词条%s%s' % (n, pz, '，还有「%s」' % RALLY[0] if rally else ''),
                               '稀有度和词条在拿到之前就定好了（捡起、买下之前就能看到），种类照原版',
                               '每条词条几率一样，同一个骨灰上不重复']),
                    '\n'.join([('Summon max HP and attack +%d%%' % bonus) if bonus > 0 else 'No summon HP or attack bonus',
                               '%d numeric affix%s%s%s' % (n, 'es' if n > 1 else '', pe, ', plus %s' % RALLY[1] if rally else ''),
                               'Rarity and affixes are set before you pick the ash up (shown on the item and in shops); the kind is unchanged',
                               'Every affix is equally likely, never twice on one ash'])))
    out = [line('rarity', '-', rar)]
    if c['rally']:
        out.append(line('rally', '1', [('', '')] * 3 + [(RALLY[2] + '\n名字里带「%s」\n多的那一只照原版最后一只复制：仿身泪滴是多一个仿身' % RALLY[0],
                                                      RALLY[3] + '\nThe name includes %s\nThe extra one copies the last spirit of the ash: the Mimic Tear gets a second mimic' % RALLY[1])]))
    for k, kind, vals, arg, ids, _, _, tzh, ten, nzh, nen in a.get('pre') or []:
        out.append(line(k, '1', [(tzh.replace('#', '%g' % vals[r]) + '\n' + nzh, ten.replace('#', '%g' % vals[r]) + '\n' + nen)
                                 if float(c['prefix_chance'][r]) > 0 else ('', '') for r in range(4)]))
    for k, f, vals, zh, en in AFFIXES:
        out.append(line(k, '0', [(zh.replace('#', '%g' % v), en.replace('#', '%g' % v)) for v in vals]))
    return out
