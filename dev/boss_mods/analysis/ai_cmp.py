# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van


def files(raw):
    return {k.replace('\\', '/').split('/')[-1]: v for k, v in van.bnd_full(raw).items()}


for f in ('aicommon.luabnd.dcx', 'aicommon_dlc02.luabnd.dcx'):
    a = files(open(os.path.join(van.root('m07'), 'script', f), 'rb').read())
    b = files(open(os.path.join(van.root('m08'), 'script', f), 'rb').read())
    c = files(open(os.path.join(van.VINS, 'script', f), 'rb').read())
    v = files(van.vread('/script/' + f))
    for k in sorted(set(a) | set(b)):
        if a.get(k) != v.get(k) or b.get(k) != v.get(k):
            print(f, k, 'm07==m08' if a.get(k) == b.get(k) else 'm07!=m08',
                  'vins==m07' if c.get(k) == a.get(k) else ('vins==van' if c.get(k) == v.get(k) else 'vins=其它'),
                  'sizes van/m07/m08/vins', len(v.get(k, b'')), len(a.get(k, b'')), len(b.get(k, b'')), len(c.get(k, b'')), a.get(k, b'')[:5])
    ch = [k for k in c if c.get(k) != v.get(k)]
    print(f, 'VINS 相对原版改了', len(ch), ch[:20])
