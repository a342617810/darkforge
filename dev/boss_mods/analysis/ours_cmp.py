# -*- coding: utf-8 -*-
"""我们自己的重随输出（out\\reroll\\regulation.bin）新增 / 改了哪些行，和各个模组自己的行有没有撞：
- 撞“新增”：同一编号两边都加 → 编号冲突，要换号
- 撞“修改”：我们也改了模组改的那一行（比如 Boss 的 NpcParam 血量）→ 要定先后（一般模组先、我们后）"""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
from van import erlib

S = json.load(open(os.path.join(van.HERE, 'rows_summary.json')))


def load(path):
    raw = erlib.read_regulation(path)
    b = erlib.Bnd4(raw)
    return {n[:-6]: erlib.Param(b.get(n)) for n in b.entries if n.endswith('.param')}


V = load(os.path.join(van.ER, 'regulation.bin'))
O = load(os.path.join(van.ER, 'dark_reforged', 'out', 'reroll', 'regulation.bin'))
ours_add = {p: set(O[p].rows) - set(V[p].rows) for p in O if p in V}
ours_chg = {p: {r for r in set(O[p].rows) & set(V[p].rows) if bytes(O[p].rows[r]) != bytes(V[p].rows[r])} for p in O if p in V}
print('我们新增的行：', {p: len(s) for p, s in ours_add.items() if s})
for m in sorted(S):
    hits_add, hits_chg = collections.defaultdict(list), collections.defaultdict(list)
    for p, x in S[m].items():
        for r in x['add']:
            if r in ours_add.get(p, ()):
                hits_add[p].append(r)
        for r in x['chg']:
            if r in ours_chg.get(p, ()):
                hits_chg[p].append(r)
    print('\n== %s %s' % (m, van.NAMES[m]))
    print('  新增编号和我们撞：', {p: (len(v), v[:8]) for p, v in hits_add.items()} or '无')
    print('  我们也改了的行：', {p: (len(v), v[:8]) for p, v in hits_chg.items()} or '无')
