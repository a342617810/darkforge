# -*- coding: utf-8 -*-
"""每个模组的 regulation.bin 对比当前原版：改了哪些参数表、多少行（新增 / 改 / 删），以及每行的编号。
结果写 reg_diff.json（后面判断“版本差”和“模组本身的改动”用）"""
import os, sys, json, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
from van import erlib

OUT = os.path.join(van.HERE, 'reg_diff.json')


def params(path):
    raw = erlib.read_regulation(path)
    b = erlib.Bnd4(raw)
    ver = bytes(raw[0x18:0x20]).rstrip(b'\0').decode('ascii', 'replace')
    out = {}
    for name in b.entries:
        if not name.endswith('.param'):
            continue
        try:
            p = erlib.Param(b.get(name))
        except Exception as ex:  # noqa
            out[name[:-6]] = {'error': str(ex)}
            continue
        out[name[:-6]] = {'size': p.row_size, 'rows': {rid: hashlib.md5(bytes(p.rows[rid])).hexdigest()[:12] for rid in p.ids}}
    return ver, out


def main():
    vver, vp = params(os.path.join(van.ER, 'regulation.bin'))
    print('vanilla', vver, len(vp), 'params')
    res = {'vanilla_ver': vver}
    targets = sorted(van.ROOTS) + ['vins']
    for m in targets:
        path = os.path.join(van.root(m), 'regulation.bin')
        ver, mp = params(path)
        d = {'ver': ver, 'params': {}}
        for name in sorted(set(vp) | set(mp)):
            a, b = vp.get(name), mp.get(name)
            if a is None or b is None or 'error' in a or 'error' in b:
                d['params'][name] = {'missing': 'mod' if b is None else 'vanilla'}
                continue
            if a['size'] != b['size']:
                d['params'][name] = {'size': [a['size'], b['size']]}
                continue
            ar, br = a['rows'], b['rows']
            add = sorted(set(br) - set(ar))
            rem = sorted(set(ar) - set(br))
            chg = sorted(r for r in set(ar) & set(br) if ar[r] != br[r])
            if add or rem or chg:
                d['params'][name] = {'add': add, 'rem': rem, 'chg': chg,
                                     'hash': {str(r): br[r] for r in add + chg}}
        res[m] = d
        s = ', '.join('%s +%d/~%d/-%d' % (k, len(v.get('add', [])), len(v.get('chg', [])), len(v.get('rem', [])))
                      if 'add' in v else '%s %s' % (k, v) for k, v in d['params'].items())
        print(m, ver, '|', s[:1500])
    json.dump(res, open(OUT, 'w'), indent=0)


if __name__ == '__main__':
    main()
