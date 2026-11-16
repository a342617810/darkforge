# -*- coding: utf-8 -*-
"""其它共用文件：aicommon(.luabnd)、systemparam、talkesdbnd、msgbnd（FMG 条目）、c0000.anibnd / chrbnd 里每个模组相对原版改了什么"""
import os, sys, hashlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
from van import erlib


def h(b):
    return hashlib.md5(b).hexdigest()


def bnd_diff(m, rel, show=20):
    p = os.path.join(van.root(m), rel)
    if not os.path.isfile(p):
        return
    v = van.vread('/' + rel.replace('\\', '/'))
    if v is None:
        print('  %s: 原版没有' % rel)
        return
    V = {k.replace('\\', '/').split('/')[-1].lower(): x for k, x in van.bnd_full(v).items()}
    M = {k.replace('\\', '/').split('/')[-1].lower(): x for k, x in van.bnd_full(open(p, 'rb').read()).items()}
    add = sorted(set(M) - set(V))
    rem = sorted(set(V) - set(M))
    chg = sorted(k for k in set(M) & set(V) if h(M[k]) != h(V[k]))
    print('  %s: 原版 %d / 模组 %d 个文件；新增 %d %s；删 %d %s；改 %d %s' % (
        rel, len(V), len(M), len(add), add[:show], len(rem), rem[:show], len(chg), chg[:show]))
    return V, M, add, rem, chg


def fmg_diff(m, rel):
    p = os.path.join(van.root(m), rel)
    if not os.path.isfile(p):
        return
    v = van.vread('/' + rel)
    if v is None:
        return
    V, M = van.bnd_full(v), van.bnd_full(open(p, 'rb').read())
    vk = {k.replace('\\', '/').split('/')[-1]: x for k, x in V.items()}
    out = []
    for k, x in M.items():
        nm = k.replace('\\', '/').split('/')[-1]
        if nm not in vk:
            out.append('%s(新文件)' % nm)
            continue
        a, b = erlib.read_fmg(vk[nm]), erlib.read_fmg(x)
        add = [i for i in b if i not in a]
        chg = [i for i in b if i in a and a[i] != b[i]]
        rem = [i for i in a if i not in b]
        if add or chg:
            sample = '; '.join('%d=%s' % (i, (b[i] or '')[:30].replace('\n', ' ')) for i in (add + chg)[:5])
            out.append('%s +%d ~%d -%d [%s]' % (nm, len(add), len(chg), len(rem), sample))
    print('  %s: %s' % (rel, ' | '.join(out) if out else '无差别'))


for m in sorted(van.ROOTS):
    print('\n== %s %s' % (m, van.NAMES[m]))
    for rel in ('script/aicommon.luabnd.dcx', 'script/aicommon_dlc02.luabnd.dcx', 'param/systemparam/systemparam.parambnd.dcx',
                'chr/c0000.anibnd.dcx', 'chr/c0000.chrbnd.dcx'):
        try:
            bnd_diff(m, rel)
        except Exception as ex:
            print('  %s: 读不了 %s' % (rel, ex))
    td = os.path.join(van.root(m), 'script', 'talk')
    if os.path.isdir(td):
        for f in os.listdir(td):
            if f.endswith('.talkesdbnd.dcx'):
                bnd_diff(m, 'script/talk/' + f)
    for lang in ('engus', 'zhocn', 'jpnjp'):
        md = os.path.join(van.root(m), 'msg', lang)
        if os.path.isdir(md):
            for f in sorted(os.listdir(md)):
                if f.endswith('.msgbnd.dcx'):
                    try:
                        fmg_diff(m, 'msg/%s/%s' % (lang, f))
                    except Exception as ex:
                        print('  msg/%s/%s: %s' % (lang, f, ex))
