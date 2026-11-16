# -*- coding: utf-8 -*-
"""每个模组在 sfxbnd_commoneffects 里新增 / 改动的条目总大小（要搬进我们自己的常驻特效包时的体积），以及新增条目的类型"""
import os, sys, hashlib, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van

v = van.vread('/sfx/sfxbnd_commoneffects.ffxbnd.dcx')
V = {k.replace('\\', '/').split('/')[-1].lower(): hashlib.md5(x).hexdigest() for k, x in van.bnd_full(v).items()}
seen = {}
for m in ('m01', 'm02', 'm03', 'm04', 'm06', 'm09', 'm11'):
    M = van.bnd_full(open(os.path.join(van.root(m), 'sfx', 'sfxbnd_commoneffects.ffxbnd.dcx'), 'rb').read())
    tot = collections.Counter()
    n = collections.Counter()
    for k, x in M.items():
        s = k.replace('\\', '/').split('/')[-1].lower()
        if s not in V:
            ext = s.rsplit('.', 1)[-1]
            tot[ext] += len(x)
            n[ext] += 1
            seen.setdefault(s, set()).add(hashlib.md5(x).hexdigest())
    print(m, van.NAMES[m], '新增：', {e: '%d 个 %.1f MB' % (n[e], tot[e] / 1048576) for e in n})
diff = [s for s, hs in seen.items() if len(hs) > 1]
print('同名但内容不同的新增条目（模组之间互相冲突）：', len(diff), diff[:20])
