# -*- coding: utf-8 -*-
"""局内难度（赐福「更多选项」→「难度调整」，档位参考 ELDEN RING Reforged，不含敌人 AI 变化）。

每档一个玩家身上的特殊效果（SpEffectParam，编号 difficulty.base_id + 档位序号）：
  敌人血量 ×h  →  玩家造成的伤害 ×1/h（物理 / 魔 / 火 / 雷 / 圣，攻击方伤害倍率）；魔法、祷告、咒术也算（SPELL_FLAGS 三个开关，
    照原版仪式之剑护符 330900；模板长猫护符的效果没开，以前法术和被当成法术的战技子弹不受难度影响，用户 2026-10-30 报）
  敌人伤害 ×d  →  玩家受到的伤害 ×d（斩 / 打 / 突 / 普通 / 魔 / 火 / 雷 / 圣，防御方伤害倍率）
  高难度奖励：卢恩 +rune_bonus（1 = +100%）、发现力 +discovery_bonus（1 = +100 发现力）：各自单独一个效果（编号 base_id + 300 / + 350 + 档位序号），
    加成为正时挂原版金色 / 银色圣甲虫的状态图标，状态栏里看得到（用户 2026-10-29）；减成（轻松、休闲）不挂图标。主效果不显示图标
    特殊效果种类（stateInfo）照原版：发现力 66、卢恩 76。原版带 itemDropRate 的效果全是 66、带 soulRate 加成的全是 76；
    以前是 0，人物状态界面的发现力不算它（用户 2026-10-29：「卢恩加成是生效的 buff图标也有 为什么就是状态栏不显示观察力」）
  poise_dealt：玩家造成的削韧倍率（saAttackPowerRate），普通以上的档位才设（大师 0.5）
效果是永久的、不存档（读档时公共事件按存档里的档位标记重新挂，见 SAVE_CATEGORY）、死了也不删、休息不清除；选新的一档时
公共事件先清掉各档的效果再挂上这一档（游戏不认自定义的特殊效果类别，不会自动顶替，见 sc/difficulty.py 的 EVENT）。
赐福菜单里选档位时对话脚本点亮请求标记和当前档位标记，由公共事件挂效果（见 sc/difficulty.py）。"""
from .common import *  # noqa: F401,F403

ATK = (56, 60, 64, 68, 476)                              # physics / magic / fire / thunder / dark AttackRate
CUT = (28, 32, 36, 40, 44, 48, 52, 464)                  # slash / blow / thrust / neutral / magic / fire / thunder / dark DamageCutRate
TEMPLATE = 360400                                        # 长尾猫护符的效果：简单的常驻效果，拿来当底子
SP_CATEGORY = 9100                                       # 原版没用过的类别
# 存档类别：-1 = 不存档（照 ELDEN RING Reforged）。当前档位记在会存档的事件标记里（sc/difficulty.py 的 CUR0），读档时公共事件按标记
# 重新挂效果，效果本身不用存。存档里给特殊效果只留了 13 格（按 saveCategory 一格一个），以前用 5 会和 DLC 岩石心脏 / 女巫心脏的
# 化身古龙（19980~19982）抢同一格
SAVE_CATEGORY = -1
# 卢恩 / 发现力加成的单独效果：编号偏移、状态图标（原版金色圣甲虫 311100 / 银色圣甲虫 311000 的）、类别（原版没用过的）
RUNE_OFF, DROP_OFF = 300, 350              # 3691xx 有训练木桩、坠落，3692xx 是庆典油脂的档位
RUNE_ICON, DROP_ICON = 20228, 20227
SP_CAT_RUNE, SP_CAT_DROP = 9101, 9102
SPELL_FLAGS = ('magParamChange', 'miracleParamChange', 'shamanParamChange')   # 攻击方倍率对魔法 / 祷告 / 咒术也生效（防御方不看这些开关）
STATE_RUNE, STATE_DROP = 76, 66            # stateInfo：原版金色 / 银色圣甲虫（卢恩 / 发现力加成）的种类


def tiers(S):
    d = S.get('difficulty') or {}
    return int(d.get('base_id', 369000)), d.get('tiers') or []


def normal_index(ts):
    """「普通」那一档：敌人血量、伤害都是 ×1 的第一档（和 sc/difficulty.py 一样认）"""
    return next((k for k, t in enumerate(ts) if float(t.get('enemy_hp', 1)) == 1 and float(t.get('enemy_damage', 1)) == 1), 0)


def build(ctx):
    d = ctx.S.get('difficulty')
    if not d or not d.get('enabled', True):
        return
    base, ts = tiers(ctx.S)
    P = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    if P.row_size != 912 or TEMPLATE not in P.rows:
        raise RuntimeError('SpEffectParam 行大小 %d 不对或缺少模板行' % P.row_size)
    lay, _ = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))
    offs = {n: (o, fc) for n, fc, o, *_ in lay}
    spell_bits = [(o, bit) for n, fc, o, bit, *_ in lay if n in SPELL_FLAGS]
    if len(spell_bits) != len(SPELL_FLAGS):
        raise RuntimeError('SpEffect 字段表里没有 %s' % '、'.join(SPELL_FLAGS))
    sa_off, si_off = offs['saAttackPowerRate'], offs['stateInfo']
    def blank(rid, cat, icon, state=0):
        """常驻、不存档、死了不删、休息不清的空效果（照长尾猫护符的效果改）"""
        if rid in P.rows:
            raise RuntimeError('难度特殊效果编号 %d 已被占用' % rid)
        row = bytearray(P.rows[TEMPLATE])
        struct.pack_into('<i', row, 0, icon)             # iconId（-1 = 不显示图标）
        struct.pack_into('<f', row, 8, -1.0)             # effectEndurance：永久
        struct.pack_into('<f', row, 220, 1.0)            # fallDamageRate：模板带的“不受坠落伤害”还原
        struct.pack_into('<H', row, 318, cat)            # spCategory
        struct.pack_into('<' + si_off[1], row, si_off[0], state)  # stateInfo（模板是 0）
        struct.pack_into('<b', row, 321, SAVE_CATEGORY)  # saveCategory：不存档（见 SAVE_CATEGORY）
        row[356] &= ~(1 << 2)                            # eraseOnBonfireRecover = 0
        row[601] |= 1 << 2                               # dontDeleteOnDead = 1
        return row
    extra = {}
    for k, t in enumerate(ts):
        rid = base + k
        row = blank(rid, SP_CATEGORY, -1)
        h, dm = float(t.get('enemy_hp', 1.0)), float(t.get('enemy_damage', 1.0))
        for o in ATK:
            struct.pack_into('<f', row, o, 1.0 / h)
        for o, bit in spell_bits:
            row[o] |= 1 << bit
        for o in CUT:
            struct.pack_into('<f', row, o, dm)
        # 高难度的奖励各自一个效果（带图标）：卢恩（soulRate，倍率，金色圣甲虫是 1.2）、发现力（itemDropRate，加算，银色圣甲虫是 0.75 = +75）
        rb, db = float(t.get('rune_bonus', 0)), float(t.get('discovery_bonus', 0))
        ids = []
        if rb:
            r = blank(base + RUNE_OFF + k, SP_CAT_RUNE, RUNE_ICON if rb > 0 else -1, STATE_RUNE)
            struct.pack_into('<f', r, 224, 1.0 + rb)
            P.add_row(base + RUNE_OFF + k, r)
            ids.append(base + RUNE_OFF + k)
        if db:
            r = blank(base + DROP_OFF + k, SP_CAT_DROP, DROP_ICON if db > 0 else -1, STATE_DROP)
            struct.pack_into('<f', r, 504, db)
            P.add_row(base + DROP_OFF + k, r)
            ids.append(base + DROP_OFF + k)
        extra[str(k)] = ids
        if 'poise_dealt' in t:
            o, fc = sa_off
            struct.pack_into('<' + fc, row, o, float(t['poise_dealt']))
        P.add_row(rid, row)
    ctx.bnd.put('SpEffectParam.param', P.serialize())
    ctx.features['difficulty'] = True
    ctx.features['difficulty_extra'] = extra       # 档位 → 卢恩 / 发现力加成的效果编号（sc/difficulty.py 切换、补挂时一起挂、一起清）
    ctx.report.append('局内难度：%d 档（%s），赐福「更多选项」→「难度调整」里选，没选过就是原版' % (
        len(ts), '、'.join('%s 造成伤害×%g 受到伤害×%g%s%s' % (t['name'], round(1.0 / float(t.get('enemy_hp', 1)), 2), t.get('enemy_damage', 1),
                                                   ' 造成削韧×%g' % t['poise_dealt'] if 'poise_dealt' in t else '',
                                                   ' 卢恩%+d%% 发现力%+d' % (t.get('rune_bonus', 0) * 100, t.get('discovery_bonus', 0) * 100)
                                                   if t.get('rune_bonus') or t.get('discovery_bonus') else '') for t in ts)))
