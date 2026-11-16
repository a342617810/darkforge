# -*- coding: utf-8 -*-
"""chr 编号 → 原版名字（NpcParam 行 c*10000 起的第一个有 nameId 的行 → NpcName，中英文）"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
from van import erlib
import paramdef_min as pdm

CHRS = [4800, 4520, 5120, 4690, 4750, 5220, 4720, 4721, 5130, 5140, 5141, 5051, 5050, 5300, 2030, 2031, 2032, 4710, 4711, 4712, 2130,
        2190, 2120, 2125, 4481, 4483, 8900, 2010, 4502, 4604, 3702, 5170, 4510, 5860, 4600, 3300, 3800]
raw = erlib.read_regulation(os.path.join(van.ER, 'regulation.bin'))
b = erlib.Bnd4(raw)
P = erlib.Param(b.get('NpcParam.param'))
lay = pdm.layout(pdm.load(os.path.join(van.RR, 'data', 'NpcParam.xml')))[0]
off = {n: (o, fc) for n, fc, o, *_ in lay}


def names(lang):
    out = {}
    for f in ('item.msgbnd.dcx', 'item_dlc02.msgbnd.dcx'):
        v = van.vread('/msg/%s/%s' % (lang, f))
        if not v:
            continue
        for k, x in van.bnd_full(v).items():
            if k.replace('\\', '/').split('/')[-1].startswith('NpcName'):
                out.update(erlib.read_fmg(x))
    return out


EN, ZH = names('engus'), names('zhocn')
for c in CHRS:
    rows = [r for r in P.ids if c * 10000 <= r < (c + 1) * 10000]
    nid = None
    for r in rows:
        n = struct.unpack_from('<i', P.rows[r], off['nameId'][0])[0]
        if n > 0 and (EN.get(n) or ZH.get(n)):
            nid = n
            break
    print('c%04d  %-40s %s  (NpcParam %d 行)' % (c, (EN.get(nid) or '')[:40], ZH.get(nid) or '', len(rows)))
