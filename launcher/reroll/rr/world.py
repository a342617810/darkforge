# -*- coding: utf-8 -*-
"""原版世界的小改动：随处传送、骨灰召唤范围放宽、开局召魂铃、不受坠落伤害。"""
from .common import *  # noqa: F401,F403
import base64


def fast_travel_anywhere(ctx):
    """地下墓地、洞窟、坑道这些原版要先打倒 Boss 才能传送的地方也能直接传送：
    MapDefaultInfoParam 的 EnableFastTravelEventFlagId（“允许传送的事件标记”，这些地图填的是 Boss 击败标记）清成 0，和野外一样不限制。
    Boss 战中、被入侵时不能传送是另外的机制，不受影响。"""
    if not ctx.S.get('fast_travel_anywhere', True):
        return
    P = erlib.Param(ctx.bnd.get('MapDefaultInfoParam.param'))
    if P.row_size != 64:
        raise RuntimeError('MapDefaultInfoParam 行大小 %d 与预期不符' % P.row_size)
    n = 0
    for row in P.rows.values():
        if struct.unpack_from('<I', row, 4)[0]:
            struct.pack_into('<I', row, 4, 0)
            n += 1
    ctx.bnd.put('MapDefaultInfoParam.param', P.serialize())
    ctx.report.append('传送限制：%d 张地图（地下墓地、洞窟、坑道等）不用先打倒 Boss 也能传送' % n)


# 法魂没给 9999 米的石碑（安瑟尔河 / 腐败湖 m12_01），照抄它的值
SUMMON_RANGE_KEEP = {12010100: 550, 12010102: 550, 12010104: 500, 12010106: 500, 12010108: 300}


def spirit_summon_anywhere(ctx):
    """骨灰的召唤限制放宽（用户 2026-11-13「参考一下法魂改一下骨灰的可召唤范围」→「先只改参数试」）：照法魂改 BuddyStoneParam 的每个石碑——
    activateRange（召唤范围，原版 35~999 米）→ 9999；overwriteActivateRegionEntityId（只能在这个区域里召唤，多是 Boss 房）→ 0；
    eliminateTargetEntityId（附近要有这些敌人才能召唤、召出来专打它们）→ 0；summonedEventFlagId（召唤过一次就亮、亮着这个石碑不能再召唤）→ 0；
    overwriteReturnRange（灵体离开多远被收回，原版少数野外石碑写 55~200 米）→ -1（不覆盖）；warnRegionEntityId（离开范围的警告区域）→ 0。
    法魂另外在本体大地图约 176 个区块、地牢 17 张地图加了看不见的召唤点（c1000 假人，原版石碑的对话角色就是它），大地图才几乎处处能召唤；
    这里先不加，只有地图里本来就有石碑的地方生效（地牢、洞窟、传说地牢整张地图；大地图原版约四成区块有石碑）。
    召唤范围照法魂的例外（SUMMON_RANGE_KEEP）：0 号模板行不动；安瑟尔河 / 腐败湖（m12_01）那 5 个石碑法魂只给 300~550 米，原因不明，照抄"""
    if not ctx.S.get('spirit_summon_anywhere', True):
        return
    import paramdef_min as pdm
    lay = {nm: (fc, o) for nm, fc, o, bp, bits, d in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'BuddyStoneParam.xml')))[0] if not bits}
    want = {'activateRange': 9999, 'overwriteActivateRegionEntityId': 0, 'eliminateTargetEntityId': 0, 'summonedEventFlagId': 0,
            'overwriteReturnRange': -1, 'warnRegionEntityId': 0}
    P = erlib.Param(ctx.bnd.get('BuddyStoneParam.param'))
    end = max(o + struct.calcsize('<' + fc) for fc, o in lay.values())
    if P.row_size < end:
        raise RuntimeError('BuddyStoneParam 行大小 %d 比定义（%d）短' % (P.row_size, end))
    changed = {k: 0 for k in want}
    for rid, row in P.rows.items():
        if rid == 0:
            continue
        for k, v in want.items():
            if k == 'activateRange':
                v = SUMMON_RANGE_KEEP.get(rid, v)
            fc, o = lay[k]
            if struct.unpack_from('<' + fc, row, o)[0] != v:
                struct.pack_into('<' + fc, row, o, v)
                changed[k] += 1
    ctx.bnd.put('BuddyStoneParam.param', P.serialize())
    ctx.report.append('骨灰召唤：%d 个石碑放宽（范围 9999 米 %d、取消区域限制 %d、不用附近有敌人 %d、能再次召唤 %d）' % (
        len(P.rows), changed['activateRange'], changed['overwriteActivateRegionEntityId'], changed['eliminateTargetEntityId'],
        changed['summonedEventFlagId']))


# 开局召魂铃（start_spirit_bell）：新掉落表 SPIRIT_BELL_LOT 只有召魂铃，获取标记沿用原版的 SPIRIT_BELL_FLAG（雷娜的掉落表、
# 圆桌厅双子老妪的商店、教学提示都看它）；sc/start.py 在公共事件里进游戏时发一次，已经有召魂铃的不再发。
# 雷娜给的掉落表 RENNA_LOT 里的召魂铃换成空格、获取标记清零：她照样能对话，后面连着的骨灰（RENNA_LOT + 1）照拿，
# 不会因为标记已经亮了整串被跳过
SPIRIT_BELL, SPIRIT_BELL_FLAG, RENNA_LOT = 8158, 60110, 103900


SPIRIT_BELL_LOT = 10097


def start_spirit_bell(ctx):
    if not ctx.S.get('start_spirit_bell', True):
        return
    P = ctx.P_mp
    if any(r in P.rows for r in (SPIRIT_BELL_LOT - 1, SPIRIT_BELL_LOT, SPIRIT_BELL_LOT + 1)):
        ctx.report.append('开局召魂铃没加上：掉落表编号 %d 附近已被占用' % SPIRIT_BELL_LOT)
        return
    src = P.rows.get(RENNA_LOT)
    bell = [k for k, c, i, _p in erlib.lot_slots(src) if c == 1 and i == SPIRIT_BELL] if src is not None else []
    if not bell:
        ctx.report.append('开局召魂铃没加上：雷娜的掉落表 %d 里没有召魂铃' % RENNA_LOT)
        return
    row = bytearray(src)
    for i in range(8):
        erlib.lot_clear_slot(row, i)
    erlib.lot_set_slot(row, 0, 1, SPIRIT_BELL, 1000, num=1, luck=False, slotflag=0)
    struct.pack_into('<I', row, erlib.LOT_FLAG, SPIRIT_BELL_FLAG)
    P.add_row(SPIRIT_BELL_LOT, row)
    for k in bell:
        pt = struct.unpack_from('<H', src, erlib.LOT_PT + 2 * k)[0]
        erlib.lot_set_slot(src, k, 0, 0, pt, num=0, luck=False, slotflag=0)
    struct.pack_into('<I', src, erlib.LOT_FLAG, 0)
    ctx.features['spirit_bell_lot'] = SPIRIT_BELL_LOT
    ctx.report.append('开局召魂铃：进游戏时送召魂铃（掉落表 %d；已经有的不再送），雷娜的掉落表 %d 去掉召魂铃（后面连着的骨灰照给）'
                      % (SPIRIT_BELL_LOT, RENNA_LOT))


NO_FALL_SP = 369120          # 人物不受坠落伤害的专用效果（sc/hks.py 写的玩家脚本每帧挂上，编号要一致）


NO_DEATH_SP = 369121         # NO_FALL_SP 循环触发的不会摔死效果


def no_fall_damage(ctx):
    """坠落：照抄 ELDEN VINS（data\\nofall_vins.json 里存的 VINS 原行）——
    NO_FALL_SP = 状态 47（游戏本体的「不受坠落伤害」，永久），循环触发 NO_DEATH_SP = 状态 266（「不会摔死」，
    原版玩家脚本里各处的 GetStateChangeType 266 就是它，骑马也算）；VINS 挂在所有腿甲上，整合包由启动时写的玩家脚本每帧挂上（sc/hks.py）。
    骑乘坠落倍率（GameSystemCommonParam）保持原版。掉进深渊 / 即死区域照常死。"""
    if not ctx.S.get('no_fall_damage', True):
        return
    P = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    if NO_FALL_SP in P.rows or NO_DEATH_SP in P.rows:
        raise RuntimeError('不受坠落伤害的效果编号 %d / %d 已被占用' % (NO_FALL_SP, NO_DEATH_SP))
    V = json.load(open(os.path.join(ctx.data_dir, 'nofall_vins.json'), encoding='utf-8'))['SpEffectParam']
    lay, _ = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))
    off = {n: (o, fc) for n, fc, o, *_ in lay}
    for new, src in ((NO_FALL_SP, '9999188'), (NO_DEATH_SP, '9999189')):
        sp = bytearray(base64.b64decode(V[src]))
        if len(sp) != P.row_size:
            raise RuntimeError('不受坠落伤害：VINS 的效果行大小不符（游戏版本变了？）')
        if new == NO_FALL_SP:
            o, fc = off['cycleOccurrenceSpEffectId']
            struct.pack_into('<' + fc, sp, o, NO_DEATH_SP)
        P.add_row(new, sp)
    ctx.bnd.put('SpEffectParam.param', P.serialize())
    ctx.features['no_fall_sp'] = NO_FALL_SP
    ctx.report.append('坠落：人物一直带不受坠落伤害 + 不会摔死的效果 %d / %d（照抄 ELDEN VINS，骑马也算；掉进深渊照常死）' % (NO_FALL_SP, NO_DEATH_SP))
