# -*- coding: utf-8 -*-
"""调试：敌人异常（攻击带的累积、抗性）、原版各档挑的长剑质变、带异常 / 不带异常的指数、单次评估耗时"""
import os, sys, json, time
import numpy as np
import model as M
B = sys.argv[1]
S = json.load(open(os.path.join(M.RR, 'settings.json'), encoding='utf-8'))
M._init({'bands_cfg': S['tier_bands'], 'map_tiers': json.load(open(os.path.join(M.RR, 'data', 'map_tiers.json'), encoding='utf-8')),
         'rng_plain': B + '/out_pc_plain', 'rng_rand': B + '/out_pc_rand', 'rng_rand_maps': B + '/maps_pc_rand', 'runs': 1, 'seed': 1})
w, arms, tals = M._ctx('原版')
for b in range(6):
    e = w.enemies[b]
    wt = e['w']
    has = (e['ebu'] > 0)
    print('档%d 种类 %d 位置 %d | 敌人攻击带异常的位置占比 %s | 抗性中位 %s' % (
        b, len(wt), int(wt.sum()), ' '.join('%s%.0f%%' % (M.ST_NAME[t], 100 * wt[has[:, t]].sum() / wt.sum()) for t in range(6) if has[:, t].any()),
        np.round(w.ref[b][4], 0)))
build = M.BUILDS['力敏']
rb = M.cumulative(w, 6, 1.0, 0.0)
base, start_lv, _, _ = M.class_start(w.reg, build['cls'])
for bname, build in M.BUILDS.items():
    picks = []
    for b in range(6):
        L = M.level_from_runes(start_lv, rb[b])
        s = M.allocate(M.class_start(w.reg, build['cls'])[0], M.class_start(w.reg, build['cls'])[1], L, build)
        lv = min(M.ASSUME['vanilla_upgrade'][b], 25)
        wb = 2000000
        vals = sorted(((M.weapon_value(arms, wb + 100 * k, lv, s, w.ref[b]), k) for k in range(13) if arms.usable(wb + 100 * k, s)), reverse=True)
        picks.append('%d:%s(%.0f)' % (b, ['标准', '重', '锐利', '优质', '火', '火焰', '雷', '神圣', '魔力', '寒气', '毒', '鲜血', '神秘'][vals[0][1]], vals[0][0]))
    print(bname, ' '.join(picks))
# 一次评估耗时：寒气长剑 +12，档 1
b = 1
L = M.level_from_runes(start_lv, rb[b])
s = M.allocate(base, start_lv, L, M.BUILDS['力敏'])
for wid in (2000000, 2000900, 2001100, 2001000):
    a = arms.ar(wid, 12, s)
    pres = M.player_resist(L, s, np.full(6, 60.0), np.zeros(6))
    t0 = time.time()
    ev = M.evaluate(w, b, a, M.hp_from_vigor(s['vit']), 45 + 0.62 * (L - 1), np.full(5, 0.75), 1.0, 1.0, arms.status(wid, 12, s), pres,
                    [(1, 1), (1.5, 1.5), (3, 2)])
    print(wid, 'status', np.round(arms.status(wid, 12, s)[0], 1), '%.1f ms' % ((time.time() - t0) * 1000),
          ' | '.join('h2k %.2f h2d %.2f idx %.2f (不算异常 %.2f)' % x for x in ev))
