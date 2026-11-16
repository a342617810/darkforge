# -*- coding: utf-8 -*-
"""每个模组的每个游戏文件：原版有没有（新文件 / 覆盖原版）、VINS 里同路径的文件是否一模一样；
同一路径被几个模组同时覆盖（互相冲突）；我们自己的输出（out\\、randomizer\\）是否也写这个路径"""
import os, sys, hashlib, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van

SKIP_EXT = ('.bak', '.prev', '.js', '.dsaproj', '.dsasbak', '.json', '.xml', '.luagnl', '.lua', '.txt', '.csv', '.ffxreslist', '.fxr',
            '.hkx', '.tae', '.blf', '.upgrade.bak')
DR = os.path.join(van.ER, 'dark_reforged')
OURS = [os.path.join(DR, 'out', 'reroll'), os.path.join(DR, 'out', 'reroll_maps'), os.path.join(DR, 'out', 'scripts'),
        os.path.join(DR, 'out', 'menu'), os.path.join(DR, 'randomizer')]


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def game_files(rootdir):
    out = {}
    for r, ds, fs in os.walk(rootdir):
        ds[:] = [d for d in ds if not d.startswith('.') and not d.endswith('-dcx') and not d.endswith('-wffxbnd') and d != '[MERGE]'
                 and not d.startswith('_DSAS') and d not in ('diste', 'dll', 'spoiler_logs', 'presets')]
        for f in fs:
            if f.lower().endswith(SKIP_EXT) or f.endswith('.dcx') is False and not f.endswith(('.hks', '.bin', '.bnk', '.wem')):
                continue
            if f.startswith('_') or ' Godrick---' in f or '------' in f:
                continue
            rel = os.path.relpath(os.path.join(r, f), rootdir).replace(os.sep, '/').lower()
            out[rel] = os.path.join(r, f)
    return out


vins = game_files(van.VINS)
ours = {}
for o in OURS:
    for rel in game_files(o):
        ours.setdefault(rel, []).append(os.path.relpath(o, DR))
who = collections.defaultdict(list)
res = {}
for m in sorted(van.ROOTS):
    fs = game_files(van.root(m))
    rows = []
    for rel, p in sorted(fs.items()):
        who[rel].append(m)
        vpath = '/' + rel
        if rel.startswith('map/mapstudio/'):
            vpath = '/map/mapstudio/' + rel.split('/')[-1]
        inv = van.vread(vpath) is not None if rel != 'regulation.bin' else True
        if rel.startswith('sd/'):
            inv = None
        tag_v = '覆盖原版' if inv else ('新文件' if inv is False else '?')
        if rel in vins:
            tag_vins = 'VINS同' if md5(vins[rel]) == md5(p) else 'VINS不同'
        else:
            tag_vins = 'VINS无'
        rows.append((rel, os.path.getsize(p), tag_v, tag_vins, ','.join(ours.get(rel, []))))
    res[m] = rows
    print('\n=== %s %s' % (m, van.NAMES[m]))
    for r in rows:
        print('  %-52s %10d  %-6s %-7s %s' % r)
print('\n=== 多个模组都覆盖的路径')
for rel, ms in sorted(who.items()):
    if len(ms) > 1:
        print('  %-50s %s   ours=%s' % (rel, ','.join(ms), ','.join(ours.get(rel, []))))
json.dump(res, open(os.path.join(van.HERE, 'files_cmp.json'), 'w', encoding='utf-8'), ensure_ascii=False)
