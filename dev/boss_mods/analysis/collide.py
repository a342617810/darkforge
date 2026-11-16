# -*- coding: utf-8 -*-
"""模组之间：同一参数表的同一行被两个模组各自改 / 加（内容不同 = 真冲突，相同 = 共用）；
模组自己的行和我们自己重随用的编号段有没有撞（SpEffect 7xxxxxx / 18xxxxxxxx 等，按 rr 代码里出现过的新行编号粗查）"""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van

D = json.load(open(os.path.join(van.HERE, 'reg_diff.json')))
S = json.load(open(os.path.join(van.HERE, 'rows_summary.json')))
own = collections.defaultdict(dict)    # (param,row) -> {m: hash}
for m, ps in S.items():
    for p, x in ps.items():
        for r in x['add'] + x['chg']:
            own[(p, r)][m] = D[m]['params'][p]['hash'][str(r)]
n_conf = n_share = 0
for (p, r), ms in sorted(own.items()):
    if len(ms) > 1:
        same = len(set(ms.values())) == 1
        if same:
            n_share += 1
        else:
            n_conf += 1
        print('%s %s %d: %s' % ('共用' if same else '冲突', p, r, ','.join('%s(%s)' % (m, van.NAMES[m].split()[0]) for m in ms)))
print('冲突 %d 行，共用（内容一样）%d 行' % (n_conf, n_share))
