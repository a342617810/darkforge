# -*- coding: utf-8 -*-
"""调试：力敏玩家（原版长剑配置）在原版 / RNG 里每档打到一半时挑中的护符（各模拟 3 次）"""
import os, sys, json, random, re
from collections import Counter
import numpy as np
import model as M
OUT = sys.argv[1]
names = M.erlib.read_msgbnd(os.path.join(OUT, 'msg', 'zhocn', 'item_dlc02.msgbnd.dcx'), ['AccessoryName']).get('AccessoryName', {})
nm = lambda i: re.sub(r'<[^>]+>', '', names.get(i, '') or str(i))
S = json.load(open(os.path.join(M.RR, 'settings.json'), encoding='utf-8'))
bands_cfg = S['tier_bands']
band_of = lambda t: next((i for i, b in enumerate(bands_cfg) if t <= b.get('max_tier', 99)), len(bands_cfg) - 1)
map_tiers = json.load(open(os.path.join(M.RR, 'data', 'map_tiers.json'), encoding='utf-8'))
vreg = M.Reg(os.path.join(M.GAME, 'regulation.bin'))
extra = M.talisman_lots(vreg, map_tiers, band_of)
build = M.BUILDS['力敏']
van_maps = [os.path.join(M.RD, 'diste', 'Vanilla')]
for tag, reg, slots in (('原版', vreg, M.ASSUME['talisman_slots']), ('RNG', M.Reg(os.path.join(OUT, 'regulation.bin')), [2, 3, 4, 4, 4, 4])):
    w = M.World(tag, reg, van_maps, False, map_tiers, band_of)
    arms_v, tals = M.Arms(vreg), M.Tals(reg)
    base, start_lv, _w, _a = M.class_start(vreg, build['cls'])
    D = 100 + base['luc']
    drops, md = w.drops(D), w.map_drops(D, map_tiers, band_of, extra)
    rb = M.cumulative(w, 6, 1.0, 0.0)
    print('=====', tag, '每档地图护符件数', [sum(1 for k, i, p in md.get(b, []) if k == 't') for b in range(6)],
          '敌人掉护符期望', ['%.1f' % (sum(drops[b]['t'].values()) * w.count.get(b, 0)) for b in range(6)])
    for run in range(3):
        rng_np, rng = np.random.default_rng(run), random.Random(run)
        owned = set()
        for b in range(6):
            mt = [(i, p) for k, i, p in md.get(b, []) if k == 't']
            got = rng_np.random(len(mt)) < np.array([p for _i, p in mt])
            first = rng_np.random(len(mt)) < 0.5
            owned.update(mt[j][0] for j in np.nonzero(got & first)[0])
            ids, p = list(drops[b]['t']), np.array(list(drops[b]['t'].values()))
            if ids:
                n = rng_np.poisson(w.count.get(b, 0) / 2 * p.sum())
                owned.update(rng.choices(ids, weights=p, k=int(n)) if n else ())
            L = M.level_from_runes(start_lv, rb[b])
            s = M.allocate(base, start_lv, L, build)
            lv = min(M.ASSUME['vanilla_upgrade'][b], arms_v.max_level(build['van']))
            pdef = M.ASSUME['player_def'][0] + M.ASSUME['player_def'][1] * (L - 1)
            eff, picked, gain = M.pick_talismans(tals, owned, slots[b], arms_v, build['van'], lv, s, pdef, np.full(5, 0.75), w.ref[b])
            n_rel = sum(1 for t in owned if tals.effect(t))
            print('  run%d 档%d 有 %d 件（有用 %d）×%.2f：%s' % (run, b, len(owned), n_rel, gain, '、'.join(nm(i) for i in picked)))
            owned.update(mt[j][0] for j in np.nonzero(got & ~first)[0])
            if ids:
                n = rng_np.poisson(w.count.get(b, 0) / 2 * p.sum())
                owned.update(rng.choices(ids, weights=p, k=int(n)) if n else ())
