# -*- coding: utf-8 -*-
"""对话包：随机器输出 / 我们的脚本输出 改了哪些 ESD，和 Boss 模组改的 ESD 是否同一个"""
import os, sys, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van

DR = os.path.join(van.ER, 'dark_reforged')
SRC = {'随机器': os.path.join(DR, 'randomizer', 'script', 'talk'), '我们': os.path.join(DR, 'out', 'scripts', 'script', 'talk')}
MOD = {'m01': 'm12_05_00_00', 'm05': 'm11_05_00_00', 'm11': 'm11_00_00_00', 'm12': 'm15_00_00_00'}


def esds(raw):
    return {k.replace('\\', '/').split('/')[-1]: hashlib.md5(v).hexdigest() for k, v in van.bnd_full(raw).items()}


for m, mp in MOD.items():
    f = mp + '.talkesdbnd.dcx'
    V = esds(van.vread('/script/talk/' + f))
    M = esds(open(os.path.join(van.root(m), 'script', 'talk', f), 'rb').read())
    mods = {k for k in M if M[k] != V.get(k)}
    line = '%s %s 模组改/加: %s' % (m, mp, sorted(mods))
    for tag, d in SRC.items():
        p = os.path.join(d, f)
        if os.path.isfile(p):
            O = esds(open(p, 'rb').read())
            ch = {k for k in O if O[k] != V.get(k)}
            line += ' | %s改: %s 重叠: %s' % (tag, sorted(ch)[:8], sorted(ch & mods))
        else:
            line += ' | %s: 不写这张图' % tag
    print(line)
