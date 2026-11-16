# -*- coding: utf-8 -*-
"""排查：随机敌人模式下每档统计到的普通敌人位置为什么少、血量为什么高（看丢掉的原因、精英占比、和重随报告里的血量补正）"""
import json, os, sys
from collections import Counter
sys.argv = [sys.argv[0]] + sys.argv[1:]
import model as M

B = sys.argv[1]
S = json.load(open(os.path.join(M.RR, 'settings.json'), encoding='utf-8'))
bands_cfg = S['tier_bands']
band_of = lambda t: next((i for i, b in enumerate(bands_cfg) if t <= b.get('max_tier', 99)), len(bands_cfg) - 1)
map_tiers = json.load(open(os.path.join(M.RR, 'data', 'map_tiers.json'), encoding='utf-8'))
reg = M.Reg(os.path.join(B, 'out_pc_rand', 'regulation.bin'))
N = reg.p('NpcParam')
Ln = M.lay('NpcParam')
ec = json.load(open(os.path.join(M.RR, 'data', 'enemy_classes.json'), encoding='utf-8'))
cls = lambda nid: ec['by_npc_param'].get(str(nid)) or ec['by_family'].get(str(nid // 10000)) or 'other'
fams = set(json.load(open(os.path.join(M.RR, 'data', 'elite_families.json'), encoding='utf-8'))['families'])
dirs = [os.path.join(B, 'maps_pc_rand', 'map', 'mapstudio'), os.path.join(M.RD, 'map', 'mapstudio')]
why = {b: Counter() for b in range(6)}
import glob
for vf in sorted(glob.glob(os.path.join(M.RD, 'diste', 'Vanilla', '*.msb.dcx'))):
    name = os.path.basename(vf)
    m = name[:-8]
    if m not in map_tiers:
        continue
    b = band_of(map_tiers[m])
    van = {e: n for e, n in M.map_parts(vf)}
    final = next((os.path.join(d, name) for d in dirs if os.path.isfile(os.path.join(d, name))), None)
    if final is None:
        why[b]['地图不在随机输出里'] += sum(1 for n in van.values() if cls(n) == 'basic')
        continue
    fin = {e: n for e, n in M.map_parts(final)}
    for e, vn in van.items():
        if cls(vn) != 'basic':
            continue
        if e not in fin:
            why[b]['实体不在最终地图'] += 1
            continue
        n = fin[e]
        if n not in N.rows:
            why[b]['参数不在 regulation'] += 1
            continue
        why[b]['ok'] += 1
        why[b]['精英' if n // 10000 in fams else '非精英'] += 1
for b in range(6):
    print(b, dict(why[b]))
for l in open(os.path.join(B, 'out_pc_rand', 'reroll_report.txt'), encoding='utf-8'):
    if '血量' in l:
        print('REPORT', l.strip()[:300])
