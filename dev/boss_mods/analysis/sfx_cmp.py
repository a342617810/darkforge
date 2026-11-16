# -*- coding: utf-8 -*-
"""sfxbnd_commoneffects / sfxbnd_cXXXX：每个模组相对原版新增 / 改动 / 缺少哪些特效（fxr）和资源（tpf / flver / anibnd / reslist）"""
import os, sys, hashlib, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van


def key(name):
    return name.replace('\\', '/').split('/')[-1].lower()


def load(raw):
    return {key(n): hashlib.md5(d).hexdigest() for n, d in van.bnd_full(raw).items()}


def fx_ids(names):
    return sorted(int(m.group(1)) for n in names for m in [re.match(r'f(\d+)\.fxr$', n)] if m)


def short(ids):
    if not ids:
        return '-'
    out, s, p = [], ids[0], ids[0]
    for x in ids[1:] + [None]:
        if x is not None and x == p + 1:
            p = x
            continue
        out.append(str(s) if s == p else '%d-%d' % (s, p))
        if x is not None:
            s = p = x
    return ', '.join(out)


res = {}
cache = {}
targets = []
for m in sorted(van.ROOTS) + ['vins']:
    sd = os.path.join(van.root(m), 'sfx')
    if not os.path.isdir(sd):
        continue
    for f in sorted(os.listdir(sd)):
        if f.endswith('.ffxbnd.dcx'):
            targets.append((m, f))
for m, f in targets:
    if f not in cache:
        v = van.vread('/sfx/' + f)
        cache[f] = load(v) if v else {}
    V = cache[f]
    M = load(open(os.path.join(van.root(m), 'sfx', f), 'rb').read())
    add = sorted(set(M) - set(V))
    rem = sorted(set(V) - set(M))
    chg = sorted(k for k in set(M) & set(V) if M[k] != V[k])
    r = {'add_fx': fx_ids(add), 'chg_fx': fx_ids(chg), 'rem_fx': fx_ids(rem),
         'add_other': [k for k in add if not k.endswith('.fxr')], 'chg_other': [k for k in chg if not k.endswith('.fxr')],
         'rem_other': [k for k in rem if not k.endswith('.fxr')]}
    res['%s/%s' % (m, f)] = r
    print('\n== %s %s  (原版 %d 个文件，模组 %d 个)' % (m, f, len(V), len(M)))
    print('  新增 fxr %d: %s' % (len(r['add_fx']), short(r['add_fx'])[:600]))
    print('  改动 fxr %d: %s' % (len(r['chg_fx']), short(r['chg_fx'])[:600]))
    print('  缺少 fxr %d: %s' % (len(r['rem_fx']), short(r['rem_fx'])[:300]))
    for t in ('add_other', 'chg_other', 'rem_other'):
        if r[t]:
            print('  %s %d: %s' % (t, len(r[t]), ', '.join(r[t][:12])))
json.dump(res, open(os.path.join(van.HERE, 'sfx_cmp.json'), 'w'))
