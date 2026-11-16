# -*- coding: utf-8 -*-
"""查一段事件标记编号有没有被用到（挑新标记前跑一遍），只读。

用法：python scan_flags.py 起 止        例：python scan_flags.py 93000 93099

查四类：
  1. 事件脚本（emevd）里的标记类指令、初始化事件 / 批量设标记的参数；
  2. 事件编号本身，以及「事件编号 + 槽位」——事件跑完会点亮同号的标记（9977 死亡事件就是这么误点出售的）；
  3. 对话脚本（esd）里的整数常量；
  4. 参数表里名字带 flag 的字段（随机器的 regulation 和重随包的 regulation）。
范围：原版（randomizer\\diste\\Vanilla）、RNG Lands 基础包、随机器、重随地图包、BossRes 覆盖包。
"""
import collections
import glob
import os
import re
import struct
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
RR = os.path.join(ROOT, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402
import emevd  # noqa: E402
import paramdef_min as pdm  # noqa: E402

GAME = os.path.dirname(ROOT)
erlib.DLL_DIRS[:] = [GAME, os.path.join(ROOT, 'randomizer'), RR]
DIRS = [('Vanilla', os.path.join(ROOT, 'randomizer', 'diste', 'Vanilla')),
        ('RNG Lands', os.path.join(ROOT, 'packs', 'Ruby', 'recommended increased difficulty')),
        ('randomizer', os.path.join(ROOT, 'randomizer')),
        ('Reroll Maps', os.path.join(ROOT, 'out/reroll_maps')),
        ('BossRes', os.path.join(ROOT, 'out/bossres'))]
REGS = [('randomizer', os.path.join(ROOT, 'randomizer', 'regulation.bin')),
        ('Reroll', os.path.join(ROOT, 'out/reroll', 'regulation.bin'))]
# (bank, id) -> 参数里标记所在的偏移
FLAG_OFF = {(3, 0): (4,), (3, 1): (4, 8), (1003, 0): (4,), (1003, 1): (4,), (1003, 2): (4,), (1003, 3): (4, 8), (1003, 4): (4, 8),
            (1003, 101): (4,), (1003, 103): (4, 8), (2003, 17): (0, 4), (2003, 22): (0, 4), (2003, 66): (4,), (2003, 69): (0,),
            (2003, 63): (0,), (2003, 64): (0,), (3, 29): (4,)}
RANGE_INS = ((3, 1), (1003, 3), (1003, 4), (1003, 103), (2003, 17), (2003, 22))


def files():
    for tag, d in DIRS:
        for root, dirs, fs in os.walk(d):
            if tag != 'Vanilla':
                dirs[:] = [x for x in dirs if x != 'diste']
            for f in fs:
                yield tag, os.path.join(root, f)


def read_any(p):
    raw = open(p, 'rb').read()
    return erlib.dcx_decompress(raw) if raw[:4] == b'DCX\0' else raw


def scan(lo, hi):
    hits = collections.defaultdict(set)
    spans = []
    for tag, p in files():
        f = os.path.basename(p)
        if '.emevd' in f:
            try:
                e = emevd.read(read_any(p))
            except Exception as ex:
                print('读不了', p, ex)
                continue
            for ev in e['events']:
                if lo <= ev['id'] <= hi:
                    hits[ev['id']].add('%s:%s 事件编号' % (tag, f))
                for ins in ev['ins']:
                    a, key = ins['args'], (ins['bank'], ins['id'])
                    if key == (2000, 0) and len(a) >= 8:
                        slot, eid = struct.unpack_from('<iI', a, 0)
                        if slot > 0 and lo <= eid + slot <= hi:
                            hits[eid + slot].add('%s:%s 事件 %d 槽 %d' % (tag, f, eid, slot))
                    offs = FLAG_OFF.get(key, ())
                    if key in ((2000, 0), (2000, 6)):
                        offs = tuple(range(8, len(a) - 3, 4))
                    vals = [struct.unpack_from('<I', a, o)[0] for o in offs if o + 4 <= len(a)]
                    for v in vals:
                        if lo <= v <= hi:
                            hits[v].add('%s:%s %d[%d] 事件 %d' % (tag, f, key[0], key[1], ev['id']))
                    if key in RANGE_INS and len(vals) == 2:
                        s, t = sorted(vals)
                        if s <= hi and t >= lo:
                            spans.append((s, t, '%s:%s %d[%d] 事件 %d' % (tag, f, key[0], key[1], ev['id'])))
        elif '.talkesdbnd' in f:
            try:
                b = erlib.Bnd4(read_any(p))
            except Exception as ex:
                print('读不了', p, ex)
                continue
            for nm in b.entries:
                d = bytes(b.get(nm))
                for m in re.finditer(b'\x82', d):
                    k = m.start() + 1
                    if k + 4 <= len(d):
                        v = struct.unpack_from('<i', d, k)[0]
                        if lo <= v <= hi:
                            hits[v].add('%s:%s:%s' % (tag, f, os.path.basename(nm)))
    defs = os.path.join(ROOT, 'randomizer', 'diste', 'Defs')
    for tag, reg in REGS:
        if not os.path.isfile(reg):
            continue
        B = erlib.Bnd4(erlib.read_regulation(reg))
        for nm in B.entries:
            if not nm.endswith('.param'):
                continue
            base = os.path.basename(nm).replace('.param', '.xml')
            xml = next((c for c in (os.path.join(RR, 'data', base), os.path.join(defs, base)) if os.path.exists(c)), None)
            if not xml:
                continue
            try:
                P = erlib.Param(B.get(nm))
                lay, _ = pdm.layout(pdm.load(xml))
            except Exception:
                continue
            fl = [(n, o, fc) for n, fc, o, *_ in lay if 'flag' in n.lower() and fc in ('i', 'I')]
            for row in P.rows.values():
                for n, o, fc in fl:
                    if o + 4 <= len(row):
                        v = struct.unpack_from('<' + fc, row, o)[0]
                        if lo <= v <= hi:
                            hits[v].add('参数(%s):%s.%s' % (tag, os.path.basename(nm), n))
    return hits, spans


def runs(nums):
    out, start, prev = [], None, None
    for v in nums:
        if start is None:
            start = prev = v
        elif v == prev + 1:
            prev = v
        else:
            out.append((start, prev))
            start = prev = v
    if start is not None:
        out.append((start, prev))
    return out


def main():
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    hits, spans = scan(lo, hi)
    print('== %d~%d 里被用到的编号（%d 个）' % (lo, hi, len(hits)))
    for v in sorted(hits):
        s = sorted(hits[v])
        print('  %d：%s%s' % (v, '；'.join(s[:3]), ' 等 %d 处' % len(s) if len(s) > 3 else ''))
    print('== 批量指令的范围跨进这一段的：', spans[:20] or '没有')
    free = [v for v in range(lo, hi + 1) if v not in hits and not any(s <= v <= t for s, t, _ in spans)]
    print('== 没有任何引用的连续段：', '、'.join('%d~%d' % r if r[0] != r[1] else '%d' % r[0] for r in runs(free)) or '没有')


if __name__ == '__main__':
    main()
