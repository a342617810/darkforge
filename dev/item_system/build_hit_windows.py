# -*- coding: utf-8 -*-
"""玩家普通攻击动作的攻击判定时间（相杀按判定算窗口，用户 2026-11-04「那就按照攻击判定算」）：
游戏目录 Data3 里的玩家动作包 chr\\c0000.anibnd.dcx（原版），每个 TAE 文件（aXXX.tae，XXX = 武器动作类别）里动画编号 030000~039999
（轻击、重击、蓄力、冲刺 / 后撤 / 翻滚攻击、跳跃攻击、左手 / 双持；040000 起是战技，不要）的攻击行为事件（TAE 类型 1，判定出现的时间段）
→ 第一个判定的开始时间、最后一个判定的结束时间（秒，动作自己的播放时间，和 dark_core 读到的 play_time 同一套）。
  - 没有攻击行为、有子弹行为（类型 2：调香瓶、弩、放剑气 / 冲击波的重击）的用子弹的时间；
  - 自己一个事件都没有、mini 头是「导入别的动画」（类型 1，+0x18 导入的完整编号；独特武器那些段常这样）的顺着导入的找；
  - 都没有的（蓄力循环、落地、弹刀、没有攻击的动作）不写，积木引擎就不开窗口（用户 2026-11-04「还有查不到动作的吗」）。
  - 动作编号 = 段 × 1000000 + 动画（a20.tae 的 30000 = 20030000，和 dark_core 积木引擎 Frame.anim 一样）；
  - 实测（右手直剑 a20）：轻击第一刀 20030000 判定 0.333–0.400（连击时下一刀在 0.467 接上 = 跳转表 115 开始）、满蓄力重击 20030500 判定
    0.900–1.033（0.69 秒松手）、点按重击出招 20030505 判定 0.300–0.400。
输出 launcher\\reroll\\data\\hit_windows.txt：一行「动作编号 开始 结束」。rr/affixes.py hitwin_lines 写成 dll\\dark_core\\hitwin.txt，
积木引擎 while 的 hit=提前,延后 按它开窗口（rules.rs）。游戏更新改了动作要重跑。
用法：launcher\\python\\python.exe -X utf8 dev\\item_system\\build_hit_windows.py（只读游戏的 Data3）"""
import os
import struct
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402

GAME = os.path.dirname(PALY)
erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), GAME]
OUT = os.path.join(RR, 'data', 'hit_windows.txt')
KEY = os.path.join(RR, 'data', 'menu', 'data3_key.pem')
ANIBND = '/chr/c0000.anibnd.dcx'
ATTACKS = (30000, 39999)        # 普通攻击的动画编号（段内）
ATTACK_EVENT = 1                # TAE 攻击行为（刀刃的判定）
BULLET_EVENT = 2                # TAE 子弹行为（放出去的判定：调香瓶、弩、放剑气的重击…）；没有攻击行为才用它
IMPORT = 1                      # 动画 mini 头类型「导入别的动画」：+0x18 = 导入的完整动画编号；自己没有事件就用导入的那个的


def read_tae(b, sec):
    """一个 TAE 文件 → {完整动画编号: (攻击行为时间段, 子弹行为时间段, 事件数, 导入的动画)}（时间段没有是 None）"""
    if b[:4] != b'TAE ' or b[7] != 0xFF:
        raise ValueError('不是 64 位 TAE')
    q = lambda o: struct.unpack_from('<q', b, o)[0]
    i32 = lambda o: struct.unpack_from('<i', b, o)[0]
    f32 = lambda o: struct.unpack_from('<f', b, o)[0]
    out = {}
    n_anim, anims_off = i32(0x54), q(0x58)
    for k in range(n_anim):
        aid, aoff = q(anims_off + k * 16), q(anims_off + k * 16 + 8)
        ev_off, n_ev = q(aoff), i32(aoff + 32)
        mini = q(aoff + 24)
        imp = i32(mini + 0x18) if i32(mini) == IMPORT else None
        span = {ATTACK_EVENT: None, BULLET_EVENT: None}
        for e in range(n_ev):
            h = ev_off + e * 24
            t = i32(q(h + 16))
            if t in span:
                t0, t1 = f32(q(h)), f32(q(h + 8))
                s = span[t]
                span[t] = (t0, t1) if s is None else (min(s[0], t0), max(s[1], t1))
        out[sec * 1000000 + aid] = (span[ATTACK_EVENT], span[BULLET_EVENT], n_ev, imp)
    return out


def window(info, a, depth=0):
    """(判定开始, 结束, 来源)：自己的攻击行为 → 没有就子弹行为 → 自己一个事件都没有、是导入的就顺着导入的找"""
    v = info.get(a)
    if v is None or depth > 8:
        return None
    hit, bullet, n_ev, imp = v
    for s, how in ((hit, '攻击'), (bullet, '子弹')):
        if s and s[1] > s[0]:
            return s[0], s[1], how
    if n_ev == 0 and imp:
        r = window(info, imp, depth + 1)
        return r and (r[0], r[1], '导入' + r[2])
    return None


def main():
    bhd = os.path.join(GAME, 'Data3.bhd')
    arc = erlib.GameArchive(bhd, open(KEY, encoding='ascii').read())
    bnd = erlib.Bnd4(erlib.dcx_decompress(arc.read(ANIBND)))
    info = {}
    for e in sorted(bnd.entries):
        n = e.replace('\\', '/').split('/')[-1]
        if n.startswith('a') and n.endswith('.tae') and n[1:-4].isdigit():
            info.update(read_tae(bnd.get(e), int(n[1:-4])))
    rows, how, none = [], Counter(), 0
    for a in sorted(info):
        if not ATTACKS[0] <= a % 1000000 <= ATTACKS[1]:
            continue
        w = window(info, a)
        if w:
            rows.append((a, w[0], w[1]))
            how[w[2]] += 1
        else:
            none += 1
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# 玩家普通攻击动作的攻击判定时间（dev/item_system/build_hit_windows.py 从游戏 Data3 的 c0000.anibnd 生成）：动作编号 第一个判定开始 最后一个判定结束（秒）\n')
        f.writelines('%d %.3f %.3f\n' % r for r in rows)
    print('写了 %d 个动作 → %s（%s；这个编号段里没有任何判定的 %d 个：蓄力循环、落地、弹刀之类）' % (
        len(rows), OUT, '、'.join('%s %d' % x for x in how.most_common()), none))
    for a in (20030000, 20030010, 20030500, 20030505, 20030510, 145030955, 266030505):
        print('  ', a, next(((t0, t1) for x, t0, t1 in rows if x == a), None))


if __name__ == '__main__':
    main()
