# -*- coding: utf-8 -*-
"""武器重击的削韧倍率（用户 2026-11-12「削韧不能这么算啊 削韧按照武器的重击作为削韧值」：碾压冲击波的削韧 = 右手武器的重击削韧）
→ launcher\\reroll\\data\\heavy_poise.txt：一行「动作类别 行为变体 倍率％」。
重击 = 单手点按重击的第一下（动画 030505，build_hit_windows.py 实测是点按重击出招）；削韧 = 武器的 saWeaponDamage × 这一下攻击行的 atkSuperArmorCorrection％
（攻击行的 atkSuperArmor 原版武器都是 0）。找攻击行：c0000 的 TAE 段 a<wepmotionCategory>（武器动作类别）里这个动画的攻击行为事件（类型 1）的判定号
→ BehaviorParam_PC（亿位放前缀：判定号不带前缀时是 1 + 行为变体 × 1000 + 判定号 % 1000；这个变体没有这一行就退到百位清零的变体，同游戏）→ refId 的 AtkParam_Pc。
一个动画几个判定取倍率最大的（多段的重击按最重的一下）；找不到的类别不写，dark_core 用默认倍率（DEFAULT_PCT）。
用法：launcher\\python\\python.exe -X utf8 dev\\item_system\\build_heavy_poise.py（读游戏目录的 regulation.bin 和 Data3 里的 c0000 动作包）"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402
import paramdef_min as pdm  # noqa: E402
import tae  # noqa: E402

GAME = os.path.dirname(PALY)
erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), GAME]
OUT = os.path.join(RR, 'data', 'heavy_poise.txt')
KEYS = os.path.join(HERE, 'keys')
HEAVY_ANIM = 30505
DEFAULT_PCT = 200


def main():
    reg = erlib.Bnd4(erlib.read_regulation(os.path.join(GAME, 'regulation.bin')))
    lay = lambda x: {t[0]: t for t in pdm.layout(pdm.load(os.path.join(RR, 'data', x)))[0]}
    LW, LB, LA = lay('EquipParamWeapon.xml'), lay('BehaviorParam.xml'), lay('AtkParam.xml')
    W = erlib.Param(reg.get('EquipParamWeapon.param'))
    BE = erlib.Param(reg.get('BehaviorParam_PC.param'))
    A = erlib.Param(reg.get('AtkParam_Pc.param'))

    def get(L, r, f):
        t = L[f]
        if t[4]:
            return (r[t[2]] >> t[3]) & ((1 << t[4]) - 1)
        return struct.unpack_from('<' + t[1], r, t[2])[0]

    arc = erlib.GameArchive(os.path.join(GAME, 'Data3.bhd'), open(os.path.join(KEYS, 'Data3_key.pem'), encoding='ascii').read())
    b = erlib.Bnd4(erlib.dcx_decompress(arc.read('/chr/c0000.anibnd.dcx')))
    taes = {}
    for n in b.entries:
        m = re.search(r'a(\d+)\.tae$', n.replace('/', '\\').lower())
        if m:
            taes[int(m.group(1))] = b.get(n)
    judges = {}
    for sec, t in taes.items():
        judges[sec] = [struct.unpack_from('<i', t, po + 8)[0] for aid, et, po in tae.events(t) if aid == HEAVY_ANIM and et == 1]

    def corr(cat, bv):
        best = None
        for j in judges.get(cat, []):
            for v in (bv, bv // 100 * 100):
                bid = max(1, j // 1000) * 100000000 + v * 1000 + j % 1000      # 武器的行为前缀是 1（判定号不带前缀）
                if bid in BE.rows:
                    ai = get(LB, BE.rows[bid], 'refId')
                    if ai in A.rows:
                        c = get(LA, A.rows[ai], 'atkSuperArmorCorrection')
                        best = c if best is None else max(best, c)
                    break
        return best

    keys = sorted({(get(LW, r, 'wepmotionCategory'), get(LW, r, 'behaviorVariationId')) for wid, r in W.rows.items() if wid % 10000 == 0 and wid > 0})
    lines, miss = [], []
    for cat, bv in keys:
        c = corr(cat, bv)
        if c is None or c <= 0:
            miss.append((cat, bv))
            continue
        lines.append('%d %d %g' % (cat, bv, c))
    # 每个动作类别再写一行默认（行为变体 -1 = 这个类别里最常见的倍率）：变体对不上（独特武器、表里漏的）先按同类别的
    from collections import Counter, defaultdict
    by_cat = defaultdict(Counter)
    for l in lines:
        c, _bv, v = l.split()
        by_cat[int(c)][v] += 1
    lines += ['%d -1 %s' % (c, cnt.most_common(1)[0][0]) for c, cnt in sorted(by_cat.items())]
    head = ['# 武器重击（单手点按重击第一下，动画 030505）的削韧倍率：动作类别 行为变体 倍率％（dev/item_system/build_heavy_poise.py 生成）。'
            '削韧 = 武器 saWeaponDamage × 倍率 / 100；行为变体 -1 是这个类别的默认；都没有的 dark_core 按 %d％' % DEFAULT_PCT]
    open(OUT, 'w', encoding='utf-8', newline='\n').write('\n'.join(head + lines) + '\n')
    print('写好 %s：%d 种（动作类别, 行为变体），找不到重击的 %d 种：%s' % (OUT, len(lines), len(miss), miss[:30]))


if __name__ == '__main__':
    main()
