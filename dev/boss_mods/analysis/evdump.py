# -*- coding: utf-8 -*-
"""把模组 emevd 里新增 / 改动的事件按指令名打印出来（用随机器自带的 er-common.emedf.json 解指令名和参数）
用法：python evdump.py m09 m14_00_00_00 [事件编号 ...]（不给编号 = 新增的全部 + 改动的全部）"""
import os, sys, struct, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
import emevd

EMEDF = json.load(open(os.path.join(van.ER, 'dark_reforged', 'randomizer', 'diste', 'Base', 'er-common.emedf.json'), encoding='utf-8'))
NAMES = {}
for c in EMEDF['main_classes']:
    for ins in c['instrs']:
        NAMES[(c['index'], ins['index'])] = (ins['name'], ins.get('args', []))
TY = {0: 'B', 1: 'H', 2: 'I', 3: 'b', 4: 'h', 5: 'i', 6: 'f', 8: 'I'}
SZ = {'B': 1, 'b': 1, 'H': 2, 'h': 2, 'I': 4, 'i': 4, 'f': 4}


def args_of(bank, iid, raw):
    nm, defs = NAMES.get((bank, iid), ('%d[%02d]' % (bank, iid), []))
    out, off = [], 0
    for a in defs:
        t = TY.get(a.get('type'), 'i')
        al = SZ[t]
        off = (off + al - 1) // al * al
        if off + al > len(raw):
            break
        v = struct.unpack_from('<' + t, raw, off)[0]
        off += al
        out.append('%s=%s' % (a['name'], ('%.4g' % v) if t == 'f' else v))
    if not defs:
        out = [str(x) for x in struct.unpack_from('<%di' % (len(raw) // 4), raw)]
    return nm, out


def dump(ev, label=''):
    print('--- event %d %s (%d 条指令)' % (ev['id'], label, len(ev['ins'])))
    for i in ev['ins']:
        nm, a = args_of(i['bank'], i['id'], i['args'])
        print('   %s(%s)' % (nm, ', '.join(a)))


if __name__ == '__main__':
    m, mp = sys.argv[1], sys.argv[2]
    ids = [int(x) for x in sys.argv[3:]]
    path = os.path.join(van.root(m), 'event', mp + '.emevd.dcx')
    M = {e['id']: e for e in emevd.read(van.unz(open(path, 'rb').read()))['events']}
    V = {e['id']: e for e in emevd.read(van.unz(van.vread('/event/%s.emevd.dcx' % mp)))['events']}
    if not ids:
        ids = sorted(k for k in M if k not in V) + sorted(k for k in M if k in V and k not in (0, 50) and
                                                            [(i['bank'], i['id'], i['args']) for i in M[k]['ins']] != [(i['bank'], i['id'], i['args']) for i in V[k]['ins']])
    for k in ids:
        if k in V and k in M:
            dump(V[k], '[原版]')
            dump(M[k], '[模组]')
        elif k in M:
            dump(M[k], '[新增]')
