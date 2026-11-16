# -*- coding: utf-8 -*-
"""每个模组的 emevd 对比原版：新增 / 删除 / 改动的事件；构造事件（0 / 50）里多了 / 少了哪些 InitializeEvent 调用。
有 DarkScript3 源（.emevd.dcx.js）的，顺便数一下标了 NEW 的行"""
import os, sys, struct, re, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
import emevd


def sig(ev):
    return [(i['bank'], i['id'], i['args'], i['layer']) for i in ev['ins']]


def inits(ev):
    out = []
    for i in ev['ins']:
        if i['bank'] == 2000 and i['id'] in (0, 6) and len(i['args']) >= 8:
            if i['id'] == 0:
                slot, eid = struct.unpack_from('<iI', i['args'], 0)
                rest = i['args'][8:]
            else:
                eid = struct.unpack_from('<I', i['args'], 0)[0]
                slot = None
                rest = i['args'][4:]
            nums = struct.unpack_from('<%di' % (len(rest) // 4), rest) if len(rest) >= 4 else ()
            out.append((i['id'], slot, eid, nums))
    return out


res = {}
for m in sorted(van.ROOTS):
    ed = os.path.join(van.root(m), 'event')
    if not os.path.isdir(ed):
        continue
    for f in sorted(os.listdir(ed)):
        if not f.endswith('.emevd.dcx'):
            continue
        mod = emevd.read(van.unz(open(os.path.join(ed, f), 'rb').read()))
        vr = van.vread('/event/' + f)
        vv = emevd.read(van.unz(vr))
        V = {e['id']: e for e in vv['events']}
        M = {e['id']: e for e in mod['events']}
        add = sorted(set(M) - set(V))
        rem = sorted(set(V) - set(M))
        chg = sorted(k for k in set(M) & set(V) if sig(M[k]) != sig(V[k]))
        print('\n== %s %s   原版 %d 个事件 / 模组 %d 个' % (m, f, len(V), len(M)))
        print('  新增事件 %d: %s' % (len(add), add[:40]))
        print('  删除事件 %d: %s' % (len(rem), rem[:40]))
        print('  改动事件 %d: %s' % (len(chg), chg[:40]))
        for cid in (0, 50):
            if cid in M and cid in V:
                a, b = inits(V[cid]), inits(M[cid])
                sa, sb = set(a), set(b)
                plus = [x for x in b if x not in sa]
                minus = [x for x in a if x not in sb]
                if plus or minus:
                    print('  构造事件 %d：多了 %d 个调用，少了 %d 个' % (cid, len(plus), len(minus)))
                    for x in plus[:30]:
                        print('     + %s' % (x,))
                    for x in minus[:30]:
                        print('     - %s' % (x,))
        js = os.path.join(ed, f + '.js')
        if os.path.isfile(js):
            t = open(js, encoding='utf-8', errors='replace').read()
            n = len(re.findall(r'//\s*NEW', t, re.I))
            print('  DarkScript3 源：%d 行，标 NEW 的 %d 处' % (t.count('\n'), n))
        res['%s/%s' % (m, f)] = {'add': add, 'rem': rem, 'chg': chg}
json.dump(res, open(os.path.join(van.HERE, 'emevd_cmp.json'), 'w'))
