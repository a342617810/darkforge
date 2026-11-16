# -*- coding: utf-8 -*-
"""模组新增 / 改动事件里用到的事件标记，有没有落在我们自己用的标记段（93000-93999、9950-9969、79xx 等）或者两个模组共用"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
import emevd
from evdump import args_of

OURS = [(93000, 93999, '我们的 93xxx'), (9950, 9969, '难度 9950-69'), (7900, 7999, '79xx'), (9990, 9999, '99xx 测试'),
        (1040490000, 1040499999, '1040490xxx 块')]
use = collections.defaultdict(set)
for m in sorted(van.ROOTS):
    ed = os.path.join(van.root(m), 'event')
    if not os.path.isdir(ed):
        continue
    for f in sorted(os.listdir(ed)):
        if not f.endswith('.emevd.dcx'):
            continue
        M = {e['id']: e for e in emevd.read(van.unz(open(os.path.join(ed, f), 'rb').read()))['events']}
        V = {e['id']: e for e in emevd.read(van.unz(van.vread('/event/' + f)))['events']}
        for k, ev in M.items():
            if k in V and [(i['bank'], i['id'], i['args']) for i in ev['ins']] == [(i['bank'], i['id'], i['args']) for i in V[k]['ins']]:
                continue
            for i in ev['ins']:
                nm, a = args_of(i['bank'], i['id'], i['args'])
                for x in a:
                    key, _, v = x.partition('=')
                    if 'Flag' in key and 'Type' not in key and 'State' not in key and v.lstrip('-').isdigit() and int(v) > 0:
                        use[int(v)].add('%s/%s' % (m, f.split('.')[0]))
hits = []
for fl, ms in sorted(use.items()):
    for lo, hi, tag in OURS:
        if lo <= fl <= hi:
            hits.append((fl, tag, sorted(ms)))
    if len({x.split('/')[0] for x in ms}) > 1:
        print('多个模组共用标记 %d: %s' % (fl, sorted(ms)))
print('落在我们标记段里的：')
for h in hits:
    print('  ', h)
print('总共 %d 个不同标记' % len(use))
