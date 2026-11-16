# -*- coding: utf-8 -*-
"""调试：每件护符解析出来的倍率（原版全部 + RNG 按效果去重），和 RNG 护符组的分布"""
import os, sys, json
from collections import Counter
import numpy as np
import model as M
OUT = sys.argv[1]
names = M.erlib.read_msgbnd(os.path.join(OUT, 'msg', 'zhocn', 'item_dlc02.msgbnd.dcx'), ['AccessoryName']).get('AccessoryName', {})
def fmt(e):
    a = e[2]
    p = []
    for k in ('dealt', 'pow', 'taken', 'defr'):
        if not np.allclose(a[k], 1):
            p.append('%s=%s' % (k, '/'.join('%.3f' % x for x in a[k])))
    if abs(a['hp'] - 1) > 1e-9:
        p.append('hp=%.3f' % a['hp'])
    if a['st'].any():
        p.append('st=' + ','.join('%s%+.1f' % (s, v) for s, v in zip(M.STATS, a['st']) if v))
    return ' '.join(p)
for tag, path in (('原版', os.path.join(M.GAME, 'regulation.bin')), ('RNG', os.path.join(OUT, 'regulation.bin'))):
    reg = M.Reg(path)
    T = M.Tals(reg)
    seen, n_rel, groups = set(), 0, Counter()
    print('=====', tag)
    for i in sorted(reg.p('EquipParamAccessory').rows):
        e = T.effect(i)
        if e is None:
            continue
        n_rel += 1
        groups[e[1]] += 1
        if e[0] in seen:
            continue
        seen.add(e[0])
        if tag == '原版' or len(seen) <= 400:
            nm = M.re.sub(r'<[^>]+>', '', names.get(i, '')) if hasattr(M, 're') else names.get(i, '')
            print(i, nm[:24], 'g%d' % e[1], fmt(e))
    print(tag, '有影响的护符', n_rel, '不同效果', len(seen), '护符组最多的', groups.most_common(8))
