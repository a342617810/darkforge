# -*- coding: utf-8 -*-
"""aicommon：原版是编译后的字节码，模组是反编译后的文本；比较里面出现的函数名 / 目标名集合"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van


def files(raw):
    return {k.replace('\\', '/').split('/')[-1]: v for k, v in van.bnd_full(raw).items()}


for f, k in (('aicommon.luabnd.dcx', 'common_battle_func.lua'), ('aicommon_dlc02.luabnd.dcx', 'goal_list_dlc2.lua'),
             ('aicommon.luabnd.dcx', '029999_battle.lua')):
    v = files(van.vread('/script/' + f))[k]
    vs = set(re.findall(rb'[A-Za-z_][A-Za-z0-9_]{5,}', v))
    for m in ('m07', 'm08'):
        a = files(open(os.path.join(van.root(m), 'script', f), 'rb').read())[k]
        ms = set(re.findall(rb'[A-Za-z_][A-Za-z0-9_]{5,}', a))
        add = sorted(x.decode() for x in ms - vs if not re.match(rb'f\d+_', x))
        rem = sorted(x.decode() for x in vs - ms if not re.match(rb'f\d+_', x))
        print('==', m, k, '文本' if not a.startswith(b'\x1bLua') else '字节码', '| 多了:', add[:30], '| 少了:', rem[:30])
