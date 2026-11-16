# -*- coding: utf-8 -*-
"""检查 dark_core 直接挂给敌人（积木引擎 FoeApply）的效果行有没有「挂给自己」位（effectTargetSelfTarget + AI）。
没有的会被游戏直接拒收（挂完立刻读身上没有，效果一点不起作用），见 自制特效.md「踩过的坑」1。
用法：python check_direct_rows.py [regulation.bin] [runtime.txt]
      默认查 out\\reroll\\regulation.bin 和 dll\\dark_core\\runtime.txt（游戏现在用的）；safe_reroll 的输出就把两个路径传进来。
每组都应该是「N 行，带位的 N 行」，有缺的退出码 1。"""
import os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import extract_affixes as ea  # noqa: E402

erlib, pdm = ea.erlib, ea.pdm
erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer')]


def main():
    reg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PALY, 'out', 'reroll', 'regulation.bin')
    rtp = sys.argv[2] if len(sys.argv) > 2 else os.path.join(PALY, 'dll', 'dark_core', 'runtime.txt')
    P = erlib.Param(erlib.Bnd4(erlib.read_regulation(reg)).get('SpEffectParam.param'))
    bits = {n: (o, bp) for n, fc, o, bp, nb, _ in pdm.layout(pdm.load(os.path.join(ea.RR, 'data', 'SpEffect.xml')))[0] if nb}
    has = lambda r, n: (r[bits[n][0]] >> bits[n][1]) & 1
    groups = defaultdict(set)
    for line in open(rtp, encoding='utf-8').read().splitlines():
        f = line.split('\t')
        if f[0] == 'bursttier' and f[1] not in ('magic', 'pebble'):   # magic / pebble 两套挂在玩家自己身上放子弹，不算
            groups['扣血档 bursttier ' + f[1]].add(int(f[-1]))
        elif f[0] == 'buildup':
            groups['异常累积 buildup'].add(int(f[-1]))
        elif f[0] == 'atkfwd':
            groups['命中效果补挂 atkfwd'].add(int(f[2]))
        elif f[0] == 'rule':
            for k, v in re.findall(r'(target_fx|mfx\d|tfx\d)=([-\d,]+)', line):
                groups['%s %s' % (f[1], k[:3] if k[:3] in ('mfx', 'tfx') else k)].update(int(x) for x in v.split(',') if int(x) > 0)
    bad = 0
    for g, ids in sorted(groups.items()):
        ok = [i for i in ids if i in P.rows and has(P.rows[i], 'effectTargetSelfTarget') and has(P.rows[i], 'effectTargetAI')]
        bad += len(ids) - len(ok)
        print('%-30s %3d 行，带「挂给自己 + AI」位的 %d 行%s' % (g, len(ids), len(ok), '' if len(ok) == len(ids) else '  ← 有挂不上的'))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
