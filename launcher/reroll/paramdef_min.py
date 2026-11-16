# -*- coding: utf-8 -*-
"""最小 paramdef 读取器：按 Smithbox 的 ER Defs XML 算字段偏移，把参数行解成字典。"""
import re, struct, xml.etree.ElementTree as ET

VER = 11711000
FMT = {'s8': 'b', 'u8': 'B', 's16': 'h', 'u16': 'H', 's32': 'i', 'u32': 'I', 'f32': 'f', 'b32': 'i', 'angle32': 'f', 'f64': 'd'}
SZ = {'b': 1, 'B': 1, 'h': 2, 'H': 2, 'i': 4, 'I': 4, 'f': 4, 'd': 8}


def load(path):
    root = ET.parse(path).getroot()
    fields = []
    for f in root.iter('Field'):
        rv, fv = f.get('RemovedVersion'), f.get('FirstVersion')
        if rv and int(rv) <= VER:
            continue
        if fv and int(fv) > VER:
            continue
        d = f.get('Def').strip()
        m = re.match(r'(\w+)\s+(\w+)(?:\[(\d+)\])?(?::(\d+))?(?:\s*=\s*(\S+))?', d)
        typ, nm, arr, bits, dflt = m.groups()
        fields.append((typ, nm, int(arr) if arr else None, int(bits) if bits else None, dflt))
    return fields


def layout(fields):
    out, off, bitpos, bitbase, bittype = [], 0, None, None, None
    for typ, nm, arr, bits, dflt in fields:
        if typ == 'dummy8':
            if bits:                       # dummy8 bitfield: packed like u8 bits
                typ = 'u8'
            else:
                if bitpos is not None:
                    off = bitbase + SZ[FMT[bittype]]; bitpos = None
                off += arr or 1
                continue
        if typ in ('fixstr', 'fixstrW'):
            if bitpos is not None:
                off = bitbase + SZ[FMT[bittype]]; bitpos = None
            off += (arr or 1) * (2 if typ == 'fixstrW' else 1)
            continue
        fc = FMT[typ]
        if bits:
            if bitpos is None or bittype != typ or bitpos + bits > SZ[fc] * 8:
                if bitpos is not None:
                    off = bitbase + SZ[FMT[bittype]]
                bitbase, bitpos, bittype = off, 0, typ
            out.append((nm, fc, bitbase, bitpos, bits, dflt))
            bitpos += bits
            continue
        if bitpos is not None:
            off = bitbase + SZ[FMT[bittype]]; bitpos = None
        n = arr or 1
        for k in range(n):
            out.append((nm if n == 1 else '%s[%d]' % (nm, k), fc, off, None, None, dflt))
            off += SZ[fc]
    if bitpos is not None:
        off = bitbase + SZ[FMT[bittype]]
    return out, off


def unpack(lay, row):
    d = {}
    for nm, fc, off, bp, bits, dflt in lay:
        v = struct.unpack_from('<' + fc, row, off)[0]
        if bits:
            v = (v >> bp) & ((1 << bits) - 1)
        d[nm] = v
    return d
