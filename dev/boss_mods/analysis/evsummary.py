# -*- coding: utf-8 -*-
"""每个模组地图事件：新增 / 改动事件的概况（每个事件用到的关键指令 + 实体编号），方便判断是阶段、召唤、场地还是血条"""
import os, sys, struct, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
import emevd
from evdump import args_of

KEY = ('SpEffect', 'Bullet', 'Health Bar', 'Character Enable', 'Character AI', 'Force Animation', 'Animation', 'Spawn', 'Boss', 'BGM',
       'Music', 'Warp', 'Map Part', 'Asset', 'Object', 'Collision', 'Display', 'Team', 'Invincib', 'HP', 'Ratio', 'Item', 'Award',
       'Camera', 'Gravity', 'Backread', 'Defeat', 'Fog', 'Weather', 'Cutscene', 'Sound', 'SFX', 'Region', 'Area', 'Phase', 'Event Flag',
       'Character Model', 'Model Mask', 'Network', 'Summon', 'Sign', 'Ride', 'Spirit', 'Lock', 'Text', 'Message', 'Map Point')


def brief(ev):
    c = collections.Counter()
    ents = set()
    for i in ev['ins']:
        nm, a = args_of(i['bank'], i['id'], i['args'])
        short = nm.replace('IF ', '').replace('SKIP IF ', '').replace('GOTO IF ', '').replace('END IF ', '')
        if any(k.lower() in nm.lower() for k in KEY):
            c[short] += 1
        for x in a:
            k, _, v = x.partition('=')
            if 'Entity' in k and v.lstrip('-').isdigit() and int(v) > 1000000:
                ents.add(int(v))
    return ', '.join('%s×%d' % (k, n) if n > 1 else k for k, n in c.most_common(10)), sorted(ents)[:12]


for m in sorted(van.ROOTS):
    ed = os.path.join(van.root(m), 'event')
    if not os.path.isdir(ed):
        continue
    for f in sorted(os.listdir(ed)):
        if not f.endswith('.emevd.dcx') or f.startswith('common'):
            continue
        M = {e['id']: e for e in emevd.read(van.unz(open(os.path.join(ed, f), 'rb').read()))['events']}
        V = {e['id']: e for e in emevd.read(van.unz(van.vread('/event/' + f)))['events']}
        print('\n== %s %s %s' % (m, van.NAMES[m], f))
        for k in sorted(M):
            if k in (0, 50):
                continue
            if k in V and [(i['bank'], i['id'], i['args']) for i in M[k]['ins']] == [(i['bank'], i['id'], i['args']) for i in V[k]['ins']]:
                continue
            tag = '新增' if k not in V else '改动(%d→%d条)' % (len(V[k]['ins']), len(M[k]['ins']))
            b, ents = brief(M[k])
            print('  %s %s: %s | 实体 %s' % (k, tag, b[:230], ents))
