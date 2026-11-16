# -*- coding: utf-8 -*-
"""排查：一次模拟里各档手里的武器（按稀有度）、能用的、攻击力最高的几把（稀有度、强化等级、攻击力），以及石头库存"""
import json, os, sys
from collections import Counter, defaultdict
import numpy as np
import model as M

B = sys.argv[1]
S = json.load(open(os.path.join(M.RR, 'settings.json'), encoding='utf-8'))
bands_cfg = S['tier_bands']
band_of = lambda t: next((i for i, b in enumerate(bands_cfg) if t <= b.get('max_tier', 99)), len(bands_cfg) - 1)
map_tiers = json.load(open(os.path.join(M.RR, 'data', 'map_tiers.json'), encoding='utf-8'))
reg = M.Reg(os.path.join(B, 'out_pc_plain', 'regulation.bin'))
w = M.World('plain', reg, [os.path.join(M.RD, 'diste', 'Vanilla')], False, map_tiers, band_of)
arms = M.Arms(reg)
build = M.BUILDS['力敏']
base, lv0, sw, sa = M.class_start(reg, build['cls'])
print('开局武器', [(x, arms.info(x)) for x in sw])
D = 107
drops = w.drops(D)
rar_rate = defaultdict(float)
for b in range(6):
    tot = Counter()
    for i, p in drops[b]['w'].items():
        inf = arms.info(i)
        if inf:
            tot[inf['rar']] += p
    print('档', b, '每杀掉武器（按稀有度）', {k: round(v * 1000, 2) for k, v in sorted(tot.items())}, '‰；石头', {k: round(v * 1000, 1) for k, v in sorted(drops[b]['s'].items()) if 10100 <= k <= 10210})
runes = M.cumulative(w, 6, 1.0, 0.0)
rng = np.random.default_rng(3)
import random
r = random.Random(3)
owned = set(sw)
stones = Counter()
for b in range(6):
    k = w.count[b]
    ids, p = list(drops[b]['w']), np.array(list(drops[b]['w'].values()))
    n = rng.poisson(k * p.sum())
    owned |= set(r.choices(ids, weights=p, k=int(n)))
    for sid, pp in drops[b]['s'].items():
        if 10100 <= sid <= 10210:
            stones[sid] += rng.poisson(k * pp)
    L = M.level_from_runes(lv0, runes[b])
    s = M.allocate(base, lv0, L, build)
    use = [x for x in owned if arms.usable(x, s)]
    rows = []
    for x in use:
        inf = arms.info(x)
        lv = 0
        for st in M.UPGRADE_STONES.get(inf['rar'], [])[:arms.max_level(x)]:
            if stones[st] <= 0:
                break
            lv += 1
        rows.append((float(arms.ar(x, lv, s).sum()), inf['rar'], lv, arms.max_level(x), x))
    rows.sort(reverse=True)
    print('档', b, '等级', L, '拥有', Counter(arms.info(x)['rar'] for x in owned if arms.info(x)), '能用', len(use), '前 5：', [(round(a), rr, lv, mx) for a, rr, lv, mx, _ in rows[:5]])
    best_by = {}
    for a, rr, lv, mx, x in rows:
        best_by.setdefault(rr, (round(a), lv, mx))
    print('      各稀有度最好的：', best_by)
