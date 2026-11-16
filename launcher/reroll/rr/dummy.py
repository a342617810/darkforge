# -*- coding: utf-8 -*-
"""训练木桩（参考 ELDEN VINS 圆桌厅堂的那个）：一具不带 AI 的地下墓地骷髅（c5600），血很厚、一直回血、不掉卢恩不掉东西。

这里只在重随版的 regulation 里建它的敌人参数（NpcParam training_dummy.npc_id）和回血特殊效果；
vins_effects：挂上 VINS 木桩的光效和幻影外观（data\\dummy_vins.json 里存的 VINS 原行）；
fixed：不被打退打飞——VINS 的受击硬直等级压低效果 + 韧性 9990（不会被打出硬直）+ 击退削减 100% + 体重 9999（推不动）；
放在圆桌厅堂能战斗的区域（和 VINS 同一个位置），旁边有训练场的「整备点」（更换战灰、记忆法术、调配灵药、重新诞生、恢复，都在 sc/training.py）：
  地图是 data\\dummy 里预先做好的固定文件（敌人参数编号写死在里面，NPC_ID 不能改），sc/training.py 启动时同步随机器的改动后放进覆盖包。
  （圆桌里加第二个赐福会被游戏当成大赐福，所以不用赐福。）"""
from .common import *  # noqa: F401,F403
import base64

TEMPLATE_NPC = 56000000                                  # 原版地下墓地骷髅
TEMPLATE_SP = 360400                                     # 简单的常驻效果当底子（同 difficulty.py）
NPC_HP = 36
NPC_SPEFFECTS = tuple(range(76, 108, 4)) + tuple(range(376, 408, 4)) + tuple(range(488, 552, 4))
NPC_ID = 56009900                                        # 固定地图里木桩用的敌人参数
DISABLE_FIELDS = ('disablePoison', 'disableDisease', 'disableBlood', 'disableCurse', 'disableFreeze', 'disableSleep', 'disableMadness')
# 整备点的对话角色（固定地图里写死用 STATION_NPC）：照抄双子老妪的对话角色参数，只换名字（对话时显示的名字 = NpcName STATION_NAME）
STATION_NPC, STATION_TEMPLATE, STATION_NAME = 500020090, 500020079, 169900
STATION_NAMES = {'zh': '整备', 'en': 'Maintenance'}


def settings(S):
    d = S.get('training_dummy')
    return d if isinstance(d, dict) and d.get('enabled', True) else None


def build(ctx):
    d = settings(ctx.S)
    if not d:
        return
    npc_id, sp_id = NPC_ID, int(d.get('speffect_id', 369100))
    P = erlib.Param(ctx.bnd.get('NpcParam.param'))
    SP = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    if TEMPLATE_NPC not in P.rows or TEMPLATE_SP not in SP.rows:
        raise RuntimeError('训练木桩：缺少模板行')
    if npc_id in P.rows or sp_id in SP.rows:
        raise RuntimeError('训练木桩：编号 %d / %d 已被占用' % (npc_id, sp_id))
    # 回血：每秒回最大血量的 regen_pct_per_sec%（changeHpRate 是负数 = 回血）
    sp = bytearray(SP.rows[TEMPLATE_SP])
    struct.pack_into('<i', sp, 0, -1)                    # iconId：不显示图标
    struct.pack_into('<f', sp, 8, -1.0)                  # effectEndurance：永久
    struct.pack_into('<f', sp, 12, 1.0)                  # motionInterval：每秒一次
    struct.pack_into('<f', sp, 156, -float(d.get('regen_pct_per_sec', 5)))
    struct.pack_into('<f', sp, 220, 1.0)                 # fallDamageRate 还原
    SP.add_row(sp_id, sp)
    lay, size = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'NpcParam.xml')))
    off = {n: (o, fc) for n, fc, o, *_ in lay}
    row = bytearray(P.rows[TEMPLATE_NPC])
    if len(row) != size:
        raise RuntimeError('NpcParam 行大小与字段表不符')
    put = lambda n, v: struct.pack_into('<' + off[n][1], row, off[n][0], v)
    put('hp', int(d.get('hp', 99999)))
    put('getSoul', 0)
    for n in ('itemLotId_enemy', 'itemLotId_map', 'humanityLotId', 'sleepCollectorItemLotId_enemy', 'sleepCollectorItemLotId_map'):
        put(n, -1)
    slot = next((o for o in NPC_SPEFFECTS if struct.unpack_from('<i', row, o)[0] in (0, -1)), None)
    if slot is None:
        raise RuntimeError('训练木桩：敌人参数没有空的特殊效果格')
    struct.pack_into('<i', row, slot, sp_id)
    if d.get('vins_effects', True) or d.get('fixed', True):
        V = json.load(open(os.path.join(ctx.data_dir, 'dummy_vins.json'), encoding='utf-8'))
        sl, _ = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))
        so = {n: (o, fc) for n, fc, o, *_ in sl}
        want = ([1605045, 295002] if d.get('vins_effects', True) else []) + ([9995300] if d.get('fixed', True) else [])
        tables = [('SpEffectParam', SP)]
        for name in ('SpEffectVfxParam', 'PhantomParam'):
            if name in V:
                tables.append((name, erlib.Param(ctx.bnd.get(name + '.param'))))
        for name, T in tables:
            for k, b64 in V.get(name, {}).items():
                k = int(k)
                if name == 'SpEffectParam' and k not in want:
                    continue
                r = bytearray(base64.b64decode(b64))
                if name == 'SpEffectParam' and k == 1605045:     # 只要光效：VINS 这行顺带的攻击 +5%、耐力恢复去掉
                    for f in ('atkPlayerDmgCorrectRate_Physics', 'atkEnemyDmgCorrectRate_Physics'):
                        struct.pack_into('<' + so[f][1], r, so[f][0], 1.0)
                    struct.pack_into('<' + so['staminaRecoverChangeSpeed'][1], r, so['staminaRecoverChangeSpeed'][0], 0)
                if len(r) != T.row_size:
                    raise RuntimeError('训练木桩：%s 行大小不符' % name)
                if k in T.rows:
                    if bytes(T.rows[k]) != bytes(r):
                        raise RuntimeError('训练木桩：%s 编号 %d 已被占用' % (name, k))
                else:
                    T.add_row(k, r)
            if name != 'SpEffectParam':
                ctx.bnd.put(name + '.param', T.serialize())
        free = [o for o in NPC_SPEFFECTS if struct.unpack_from('<i', row, o)[0] in (0, -1)]
        if len(free) < len(want):
            raise RuntimeError('训练木桩：敌人参数的空特殊效果格不够')
        for o, k in zip(free, want):
            struct.pack_into('<i', row, o, k)
    if d.get('resist') is not None:          # 异常抗性：毒 / 腐败 / 出血 / 即死 / 冻伤 / 睡眠 / 发狂都设成这个数，发作后也不涨（不按原来骷髅的免疫）
        for n in ('resist_poison', 'resist_desease', 'resist_blood', 'resist_curse', 'resist_freeze', 'resist_sleep', 'resist_madness'):
            put(n, int(d['resist']))
        for n in ('poison', 'disease', 'blood', 'curse', 'freeze', 'sleep', 'madness'):
            put('resistCorrectId_' + n, -1)
        # 骷髅身上原版的异常免疫效果（disablePoison / Blood / Freeze / Sleep 等位，90000 / 90020 / 90040 / 90300）也去掉：
        # 只改抗性的话这几种照样免疫（2026-11-01：发的出血 / 冻伤武器打木桩不累积）
        sl = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]
        immune = [o for o in NPC_SPEFFECTS if struct.unpack_from('<i', row, o)[0] in SP.rows
                  and any(pdm.unpack(sl, bytes(SP.rows[struct.unpack_from('<i', row, o)[0]])).get(f) for f in DISABLE_FIELDS)]
        n_immune = len(immune)
        for o in immune:
            struct.pack_into('<i', row, o, -1)
    if d.get('absorption') is not None:      # 减伤率（%）：普通 / 斩击 / 打击 / 突刺 / 魔力 / 火 / 雷 / 圣都设成这个数（原来骷髅打击、圣是 -40% 的弱点）；防御力不动
        for n in ('neutral', 'slash', 'blow', 'thrust', 'magic', 'fire', 'thunder', 'dark'):
            put(n + 'DamageCutRate', 1.0 - float(d['absorption']) / 100)
    if d.get('fixed', True):
        put('superArmorDurability', 9990.0)
        put('knockbackRate', 100)                # 击退削减 100%：攻击方的击退初速度全部削掉（VINS 也是 100，原版骷髅是 0）
        put('weight', 9999)                      # 很重：走过去 / 翻滚撞上也推不动
    P.add_row(npc_id, row)
    if STATION_NPC in P.rows or STATION_TEMPLATE not in P.rows:
        raise RuntimeError('整备点：敌人参数 %d 已被占用或缺少双子老妪那行 %d' % (STATION_NPC, STATION_TEMPLATE))
    srow = bytearray(P.rows[STATION_TEMPLATE])
    struct.pack_into('<' + off['nameId'][1], srow, off['nameId'][0], STATION_NAME)
    P.add_row(STATION_NPC, srow)
    ctx.bnd.put('NpcParam.param', P.serialize())
    ctx.bnd.put('SpEffectParam.param', SP.serialize())
    ctx.features['training_dummy'] = True
    ctx.report.append('训练木桩：敌人参数 %d（地下墓地骷髅，血 %d，每秒回 %g%%，不掉卢恩和东西%s%s%s%s），'
                      '放在圆桌厅堂能战斗的区域，旁边有训练场整备点（更换战灰、记忆法术、调配灵药、重新诞生、恢复）' % (
                          npc_id, int(d.get('hp', 99999)), float(d.get('regen_pct_per_sec', 5)),
                          '，VINS 光效 + 幻影外观' if d.get('vins_effects', True) else '',
                          '，打不退打不出硬直' if d.get('fixed', True) else '',
                          '，异常抗性全部 %d（去掉原版的异常免疫效果 %d 个）' % (int(d['resist']), n_immune) if d.get('resist') is not None else '',
                          '，物理和各属性减伤率全部 %g%%' % float(d['absorption']) if d.get('absorption') is not None else ''))


def texts(S, lang):
    """{文字表: {编号: 文字}}：整备点对话时显示的名字（lang = 'zh' / 'en'）"""
    if not settings(S):
        return {}
    return {'NpcName': {STATION_NAME: STATION_NAMES[lang]}}
