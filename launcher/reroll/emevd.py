# -*- coding: utf-8 -*-
"""ELDEN RING 事件脚本（EMEVD，64 位小端）读写。只做整合包要用的：读出事件 / 指令 / 参数替换，
加事件、加指令后原样写回（层、关联文件、字符串表按原字节保留）。

结构：头（0x90）后面依次是事件表（每个 48 字节）、指令表（每条 32 字节）、层表（每个 32 字节）、
参数替换表（每条 32 字节）、关联文件表（8 字节偏移）、参数区、字符串区。各表偏移都记在头里，
指令的参数偏移相对参数区、层偏移相对层表、事件的指令 / 参数偏移相对各自的表。"""
import struct

HEAD = 0x90


def read(raw):
    raw = bytes(raw)
    if raw[:4] != b'EVD\0':
        raise ValueError('不是 EMEVD')
    flags = raw[4:8]
    ver = struct.unpack_from('<I', raw, 8)[0]
    (ev_n, ev_o, in_n, in_o, u_n, u_o, ly_n, ly_o, pa_n, pa_o, lf_n, lf_o, ar_n, ar_o, st_n, st_o) = struct.unpack_from('<16q', raw, 16)
    layers = [raw[ly_o + 32 * k: ly_o + 32 * k + 32] for k in range(ly_n)]
    events = []
    for k in range(ev_n):
        eid, icount, ioff, pcount, poff, rest, _pad = struct.unpack_from('<qqqqqii', raw, ev_o + 48 * k)
        ins = []
        for j in range(icount):
            bank, iid, alen, aoff, loff = struct.unpack_from('<iiqqq', raw, in_o + ioff + 32 * j)
            ins.append({'bank': bank, 'id': iid, 'args': raw[ar_o + aoff: ar_o + aoff + alen],
                        'layer': None if loff < 0 else loff // 32})
        params = [struct.unpack_from('<qqqii', raw, pa_o + poff + 32 * j) for j in range(pcount)]
        events.append({'id': eid, 'rest': rest, 'ins': ins, 'params': params})
    linked = [struct.unpack_from('<q', raw, lf_o + 8 * k)[0] for k in range(lf_n)]
    return {'flags': flags, 'version': ver, 'events': events, 'layers': layers, 'linked': linked,
            'strings': raw[st_o: st_o + st_n], 'unk': (u_n, u_o)}


def _pad(b, n):
    return b + b'\0' * (-len(b) % n)


def write(e):
    ev_tab, in_tab, pa_tab, args = bytearray(), bytearray(), bytearray(), bytearray()
    n_ins = n_par = 0
    for ev in e['events']:
        ev_tab += struct.pack('<qqqqqii', ev['id'], len(ev['ins']), len(in_tab) if ev['ins'] else -1, len(ev['params']),
                              len(pa_tab) if ev['params'] else -1, ev['rest'], 0)
        for ins in ev['ins']:
            a = bytes(ins['args'])
            in_tab += struct.pack('<iiqqq', ins['bank'], ins['id'], len(a), len(args) if a else -1,
                                  -1 if ins['layer'] is None else ins['layer'] * 32)
            args += _pad(a, 4)
            n_ins += 1
        for p in ev['params']:
            pa_tab += struct.pack('<qqqii', *p)
            n_par += 1
    ly_tab = b''.join(e['layers'])
    lf_tab = b''.join(struct.pack('<q', x) for x in e['linked'])
    args = _pad(bytes(args), 16)                     # 参数区整体补到 16 字节，头里记补齐后的长度（和原版一致）
    out = bytearray(HEAD)                            # 顺序同原版：事件、指令、层、参数区、参数替换、关联文件、字符串
    ev_o = len(out); out += ev_tab
    in_o = len(out); out += in_tab
    u_o = len(out)
    ly_o = len(out); out += ly_tab
    ar_o = len(out); out += args
    pa_o = len(out); out += pa_tab
    lf_o = len(out); out += lf_tab
    st_o = len(out); out += e['strings']
    out[0:4] = b'EVD\0'
    out[4:8] = e['flags']
    struct.pack_into('<II', out, 8, e['version'], len(out))
    struct.pack_into('<16q', out, 16, len(e['events']), ev_o, n_ins, in_o, 0, u_o, len(e['layers']), ly_o,
                     n_par, pa_o, len(e['linked']), lf_o, len(args), ar_o, len(e['strings']), st_o)
    return bytes(out)


# ---- 拼指令参数（按 EMEDF 的类型：u8 / s8 / u32 / s32 / f32，每个按自身大小对齐，整体补到 4 字节）
_FMT = {'u8': 'B', 's8': 'b', 'u16': 'H', 's16': 'h', 'u32': 'I', 's32': 'i', 'f32': 'f'}


def pack(*typed):
    b = bytearray()
    for t, v in typed:
        f = _FMT[t]
        size = struct.calcsize(f)
        b += b'\0' * (-len(b) % size)
        b += struct.pack('<' + f, v)
    return bytes(_pad(bytes(b), 4))


def ins(bank, iid, *typed):
    return {'bank': bank, 'id': iid, 'args': pack(*typed), 'layer': None}
