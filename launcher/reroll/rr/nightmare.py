# -*- coding: utf-8 -*-
"""魇化精英与魇印（settings.json 的 nightmare；用户 2026-11-03，设计稿 dev\\item_system\\超限锻造石与高难度.md §8）。
- 只在 difficulty 里标了 lock 的档（死亡 / 不可能）：普通小怪（hpunify 收集的小怪位置，不含入侵 NPC）dark_core 第一次看到时按档掷 chance% 魇化，
  double% 带两条；休息后重掷。魇化精英带 FAMILIES 里一两条现有词条（用户定：不新做词条、十几种覆盖各个方面），敌人身上挂：
    血量 ×hp（HP_SP，叠在血量补正上）；第一条词条颜色的通用强化（COLOR_SP + 颜色，原版字段）：
    红 攻击力 ×1.3；蓝 动作加快 20%（dark_core 改动作速度，同时隙）；金 受到的伤害 ×0.7、削韧 ×0.6；绿 每秒回复 1% 血量。
  每种强化带颜色描边：幻影颜色覆盖（PhantomParam，照原版红色描边 60 改颜色、加亮；SpEffectVfx 的 phantomParamOverwrite）。
- 魇化精英死了（不要求是你打死的，range 0 = 不限距离）：词条变成玩家的「魇火」（这条词条 ember_rarity 稀有度的效果行直接挂在玩家身上，
  最多 ember_max 个，只在死亡时清掉——用户 2026-11-03：休息不清；存进存档标记 EMBER0 起，退出游戏也还在）；超限锻造石的几率换成 stone_pct%。
- 每夺一次，这条词条的次数 +1（存档的事件标记，COUNT0 起每种 5 位）；次数到 levels 就能在赐福「暗黑重铸」→「魇印」（sc/wspages.py，只在高难度档列出来）刻成魇印
  （Ⅰ~Ⅳ = 普通~传说的效果行），刻印位 SLOT_FLAGS 每位 4 位（0 空、1~14 第几种），开几位看解锁了几种（slots）。魇印所有难度都生效。
dll\\dark_core\\nightmare.txt（def_lines）；执行在 dark_core 的 nightmare.rs，界面在 dll\\dark_ui。"""
from .common import *  # noqa: F401,F403

# 14 种：(词条键, 强化分组 0 攻击 / 1 迅捷 / 2 坚韧 / 3 再生，以前叫红 / 蓝 / 金 / 绿)，设计稿 §8.1 的顺序（顺序就是存档里的序号，不能改）
FAMILIES = [
    ('after_killing_enemy_increase_damage_by_pct_for_s', 0),     # 远征
    ('increase_damage_of_weapon_skills_by_pct', 0),               # 强力战灰
    ('increase_posture_damage_by_pct', 0),                        # 蛮牛
    ('dr_chaos', 0),                                              # 混沌
    ('sorcery_dmg', 1),                                           # 魔法
    ('incantation_dmg', 1),                                       # 祷告
    ('increase_range_of_bows_by_pct_and_raise_attack_p', 1),      # 翔空箭
    ('dr_gale', 1),                                               # 疾风
    ('decrease_physical_damage_taken_by_pct', 2),                 # 土龙鳞
    ('decrease_all_elemental_damage_taken_by_pct', 2),            # 遗忘龙鳞
    ('max_hp_pct', 2),                                            # 生命力
    ('dr_blood_drink', 3),                                        # 饮血
    ('regen_fp_every_seconds_by_pct', 3),                         # 星风
    ('increase_stamina_recovery_speed_by_points', 3),             # 吐息加速
]
SP_BASE = 7303000                        # 血量 7303000，强化 7303001~7303004（效果行和特效行同号）
DRAIN_SP = SP_BASE + 5                   # 夺取魇火时玩家身上的紫色吸取特效（效果行和光效行同号；dark_core 挂，用户 2026-11-03）
DRAIN_FXR = 990006                       # 原版亵渎圣剑战技回血的特效 450344 改成紫色（dev\item_system\sfx\drain.js，make_sfx.py 打包）
DRAIN_FROM = (1565, 8535)                # 原版：亵渎圣剑「夺取者的火焰」打中回血的效果行 / 它的光效行（挂点 220）
PLAYER_TEMPLATE = 360400                 # 能直接挂给自己的效果行（同 rr/curses.py）：夺取特效的作用对象位照它
PHANTOM_BASE = 9910                      # 幻影颜色 9910~9913（原版到 920）
PHANTOM_TEMPLATE = 60                    # 原版红色描边
VFX_TEMPLATE = 260                       # 特效行的底子（同 rr/ailments.py：大型敌人也显示）
SP_TEMPLATE = 90030                      # 效果行的底子（同 rr/hpunify.py：去掉「咒死无效」那一位）
COUNT0 = 93911                           # 次数 14 × 5 位 = 93911~93980（dev\event_flags\说明.md）
# 刻印位各自的第一个标记，每位 4 位：前 3 位 93981~93992 存档里已有不能挪，后面 93993 起是咒痕，所以第 4、5 位在 93492~93499（用户 2026-11-05 加到 5 位）
SLOT_FLAGS = (93981, 93985, 93989, 93492, 93496)
OPEN = 93091                             # 赐福「暗黑重铸」→「魇印」的打开请求（sc/wspages.py；应答 / 没界面和装备工坊共用）
COUNT_BITS, SLOT_BITS, NSLOT = 5, 4, len(SLOT_FLAGS)
EMBER0, EMBER_BITS, EMBER_SLOTS = 93616, 6, 3   # 身上的魇火：3 个 × 6 位 = 93616~93633（第几种 + 1、稀有度 << 4；dev\event_flags\说明.md）
# 魇化的描边：一律紫色（用户 2026-11-03；以前按强化分红 / 蓝 / 金 / 绿）
OUTLINE = (170, 70, 255)
# 四种强化（FAMILIES 第二项的分组）
BUFFS = ['攻击', '迅捷', '坚韧', '再生']
# PhantomParam 的字段（56 字节；dev\vendor\fromsoftware-rs\tools\param-generator\params\eldenring\PhantomParam.xml）
PH_EDGE_A, PH_FRONT_A, PH_EDGE_RGB, PH_FRONT_RGB, PH_EDGE_POWER, PH_GLOW = 0, 4, 20, 23, 48, 52
DEFAULT = dict(chance=[10, 16], double=[0, 30], hp=2.0, ember_rarity=[1, 2], ember_max=3, stone_pct=50, range=0,
               levels=[1, 2, 7, 15], slots=[0, 4, 7, 11, 14], attack=1.3, speed=1.2, cut=0.7, poise=0.6, regen=1.0)


def cfg(S):
    c = S.get('nightmare') or {}
    if not c.get('enabled', True):
        return None
    out = dict(DEFAULT)
    out.update({k: c[k] for k in DEFAULT if k in c})
    return out


def build(ctx):
    """效果行、特效行、幻影颜色；ctx.nightmare = 设置（def_lines 用）"""
    ctx.nightmare = None
    c = cfg(ctx.S)
    from .hpunify import flags as lock_flags
    if not c or not lock_flags(ctx.S) or not getattr(ctx, 'hpu_src', None):
        return
    S = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    V = erlib.Param(ctx.bnd.get('SpEffectVfxParam.param'))
    Ph = erlib.Param(ctx.bnd.get('PhantomParam.param'))
    if Ph.row_size != 56 or PHANTOM_TEMPLATE not in Ph.rows or VFX_TEMPLATE not in V.rows or SP_TEMPLATE not in S.rows:
        raise RuntimeError('魇化：PhantomParam 行大小 %d 不对，或缺少模板行' % Ph.row_size)
    L = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}
    VL = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffectVfx.xml')))[0]}
    put = lambda lay, row, f, v: struct.pack_into('<' + lay[f][1], row, lay[f][2], v)

    def sp_row():
        row = bytearray(S.rows[SP_TEMPLATE])
        o, bit = L['disableCurse'][2], L['disableCurse'][3]
        row[o] &= ~(1 << bit)
        put(L, row, 'iconId', -1)
        put(L, row, 'effectEndurance', -1.0)
        put(L, row, 'spCategory', 0)
        return row
    for i in range(5):
        if SP_BASE + i in S.rows or SP_BASE + i in V.rows:
            raise RuntimeError('魇化：效果 / 特效编号 %d 已经有人用了' % (SP_BASE + i))
    hp = sp_row()
    put(L, hp, 'maxHpRate', float(c['hp']))
    S.add_row(SP_BASE, bytes(hp))
    for k in range(len(BUFFS)):
        pid, vid, sid, rgb = PHANTOM_BASE + k, SP_BASE + 1 + k, SP_BASE + 1 + k, OUTLINE
        if pid in Ph.rows:
            raise RuntimeError('魇化：幻影颜色编号 %d 已经有人用了' % pid)
        ph = bytearray(Ph.rows[PHANTOM_TEMPLATE])
        struct.pack_into('<f', ph, PH_EDGE_A, 0.35)
        struct.pack_into('<f', ph, PH_FRONT_A, 0.06)
        ph[PH_EDGE_RGB:PH_EDGE_RGB + 3] = bytes(rgb)
        ph[PH_FRONT_RGB:PH_FRONT_RGB + 3] = bytes(x // 3 for x in rgb)
        struct.pack_into('<f', ph, PH_EDGE_POWER, 0.6)
        struct.pack_into('<f', ph, PH_GLOW, 1.5)
        Ph.add_row(pid, bytes(ph))
        v = bytearray(V.rows[VFX_TEMPLATE])
        for f in ('midstSfxId', 'initSfxId', 'finishSfxId'):
            put(VL, v, f, -1)
        put(VL, v, 'phantomParamOverwriteType', 2)
        put(VL, v, 'phantomParamOverwriteId', pid)
        V.add_row(vid, bytes(v))
        row = sp_row()
        put(L, row, 'vfxId', vid)
        if k == 0:                                   # 攻击：攻击力
            for f in ('physicsAttackRate', 'magicAttackRate', 'fireAttackRate', 'thunderAttackRate', 'darkAttackRate'):
                put(L, row, f, float(c['attack']))
        elif k == 2:                                 # 坚韧：受到的伤害、削韧
            for f in ('slashDamageCutRate', 'blowDamageCutRate', 'thrustDamageCutRate', 'neutralDamageCutRate',
                      'magicDamageCutRate', 'fireDamageCutRate', 'thunderDamageCutRate', 'darkDamageCutRate'):
                put(L, row, f, float(c['cut']))
            put(L, row, 'saReceiveDamageRate', float(c['poise']))
        elif k == 3:                                 # 再生：每秒回复（changeHpRate 负数 = 回复最大血量的百分比）
            put(L, row, 'changeHpRate', -float(c['regen']))
            put(L, row, 'motionInterval', 1.0)
        S.add_row(sid, bytes(row))                   # 迅捷：只有描边，加快由 dark_core 改动作速度
    # 夺取时的吸取特效：原版回血的效果行去掉回血、作用对象照能挂给自己的模板；光效行换成紫色的特效
    ctx.nightmare_drain = 0
    if DRAIN_FROM[0] in S.rows and DRAIN_FROM[1] in V.rows and PLAYER_TEMPLATE in S.rows:
        if DRAIN_SP in S.rows or DRAIN_SP in V.rows:
            raise RuntimeError('魇化：夺取特效的编号 %d 已经有人用了' % DRAIN_SP)
        v = bytearray(V.rows[DRAIN_FROM[1]])
        put(VL, v, 'midstSfxId', DRAIN_FXR)
        V.add_row(DRAIN_SP, bytes(v))
        row, tpl = bytearray(S.rows[DRAIN_FROM[0]]), S.rows[PLAYER_TEMPLATE]
        put(L, row, 'changeHpRate', 0.0)
        put(L, row, 'changeHpPoint', 0)
        for f, t in L.items():
            if f.startswith('effectTarget') and t[4]:      # 位字段：照模板
                o, b = t[2], t[3]
                row[o] = (row[o] & ~(1 << b)) | (tpl[o] & (1 << b))
        put(L, row, 'vfxId', DRAIN_SP)
        S.add_row(DRAIN_SP, bytes(row))
        ctx.nightmare_drain = DRAIN_SP
    for name, P in (('SpEffectParam', S), ('SpEffectVfxParam', V), ('PhantomParam', Ph)):
        ctx.bnd.put(name + '.param', P.serialize())
    ctx.nightmare = c
    ctx.features['nightmare'] = {'count0': COUNT0, 'slot0': SLOT_FLAGS[0], 'open': OPEN, 'tiers': lock_flags(ctx.S)}   # tiers：入口只在这几档列出来
    ctx.report.append('魇化精英：只在标了 lock 的难度档，普通小怪魇化几率 %s%%（带两条 %s%%），血量 ×%g，攻击 / 迅捷 / 坚韧 / 再生四种强化（效果 %d~%d，'
                      '紫色幻影描边 %d~%d）；魇火 %s 稀有度、最多 %d 个，精英掉超限锻造石 %g%%；魇印 %d 种，次数标记 %d 起、刻印位 %d 起' % (
                          ' / '.join(map(str, c['chance'])), ' / '.join(map(str, c['double'])), float(c['hp']), SP_BASE, SP_BASE + 4,
                          PHANTOM_BASE, PHANTOM_BASE + 3, ' / '.join(RAR_ZH[RAR[int(r)]] for r in c['ember_rarity']), int(c['ember_max']),
                          float(c['stone_pct']), len(FAMILIES), COUNT0, SLOT_FLAGS[0]))


def def_lines(ctx):
    """dll\\dark_core\\nightmare.txt（格式见 dark_core 的 nightmare.rs）"""
    c = getattr(ctx, 'nightmare', None)
    if not c:
        return []
    from .hpunify import flags as lock_flags
    from .overlimit import GOODS_W, GOODS_A
    fl = lock_flags(ctx.S)
    pick = lambda v, k: v[min(k, len(v) - 1)]
    out = ['tier %d %g %g %d %g' % (f, float(pick(c['chance'], k)), float(pick(c['double'], k)), int(pick(c['ember_rarity'], k)),
                                     float(c['stone_pct'])) for k, f in enumerate(fl)]
    out += ['hp %d' % SP_BASE]
    out += ['color %d %d %g' % (k, SP_BASE + 1 + k, float(c['speed']) if k == 1 else 1.0) for k in range(len(BUFFS))]
    out += ['drain %d' % getattr(ctx, 'nightmare_drain', 0)]
    out += ['fam %d %s %d' % (k, key, col) for k, (key, col) in enumerate(FAMILIES)]
    out += ['ember_max %d' % min(int(c['ember_max']), EMBER_SLOTS), 'range %g' % float(c['range']),
            'levels ' + ' '.join(str(int(x)) for x in c['levels']), 'slots ' + ' '.join(str(int(x)) for x in c['slots']),
            'count0 %d %d' % (COUNT0, COUNT_BITS), 'slot_at %d %s' % (SLOT_BITS, ' '.join(map(str, SLOT_FLAGS))), 'ember0 %d %d %d' % (EMBER0, EMBER_BITS, EMBER_SLOTS),
            'goods %d %d' % (GOODS_W, GOODS_A) if getattr(ctx, 'overlimit', None) else 'goods 0 0']
    U = ctx.hpu_src['U']
    inv = U.get('inv', set()) | U.get('helpers', set())      # 入侵 NPC、随机器新加的 Boss 随从（rr/stage3.py）不魇化
    ents = sorted({key for kind, key, _t in U['mobs'] if kind == 'e' and key not in inv})
    npcs = sorted({key for kind, key, _t in U['mobs'] if kind == 'n'})
    out += ['mobe ' + ' '.join(map(str, ents[i:i + 40])) for i in range(0, len(ents), 40)]
    out += ['mobn ' + ' '.join(map(str, npcs[i:i + 40])) for i in range(0, len(npcs), 40)]
    return out
