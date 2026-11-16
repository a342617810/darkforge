# -*- coding: utf-8 -*-
"""只读：列出 Scaleform GFX（未压缩的 SWF）里的标签——外部图片（编号 → 贴图名）、形状的边界和用的图、
放置（PlaceObject2/3）的矩阵；DefineSprite 里的也展开。用法：python swfdump.py <xxx.gfx>"""
import struct
import sys
import zlib


class Bits:
    def __init__(self, b, pos):
        self.b, self.p = b, pos * 8

    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.p >> 3] >> (7 - (self.p & 7))) & 1)
            self.p += 1
        return v

    def s(self, n):
        v = self.u(n)
        return v - (1 << n) if n and v & (1 << (n - 1)) else v

    def byte(self):
        return (self.p + 7) >> 3


def rect(b, pos):
    r = Bits(b, pos)
    n = r.u(5)
    x0, x1, y0, y1 = (r.s(n) for _ in range(4))
    return (x0 / 20, y0 / 20, x1 / 20, y1 / 20), r.byte()


def matrix(b, pos):
    r = Bits(b, pos)
    sx = sy = 1.0
    r0 = r1 = 0.0
    if r.u(1):
        n = r.u(5)
        sx, sy = r.s(n) / 65536, r.s(n) / 65536
    if r.u(1):
        n = r.u(5)
        r0, r1 = r.s(n) / 65536, r.s(n) / 65536
    n = r.u(5)
    tx, ty = r.s(n) / 20, r.s(n) / 20
    return (sx, sy, r0, r1, tx, ty), r.byte()


def tags(b, pos, end, depth=0, out=None):
    out = [] if out is None else out
    while pos < end:
        h = struct.unpack_from('<H', b, pos)[0]
        code, ln = h >> 6, h & 0x3f
        pos += 2
        if ln == 0x3f:
            ln = struct.unpack_from('<I', b, pos)[0]
            pos += 4
        body = pos
        pad = '  ' * depth
        if code in (1009, 1001):                     # DefineExternalImage2 / DefineExternalImage
            if code == 1009:
                cid, fmt, w, hh = struct.unpack_from('<IHHH', b, body)
                q = body + 10
            else:
                cid, fmt, w, hh = struct.unpack_from('<HHHH', b, body)
                q = body + 8
            nl = b[q]
            name = b[q + 1:q + 1 + nl].decode('latin1')
            print('%s图片 id=%d %dx%d %s' % (pad, cid, w, hh, name))
        elif code in (2, 22, 32, 83):
            cid = struct.unpack_from('<H', b, body)[0]
            bounds, _ = rect(b, body + 2)
            fills = [i for i in range(body, body + ln - 2) if b[i] in (0x40, 0x41, 0x42, 0x43)]
            bmp = []
            # 找填充里的位图编号：类型 0x40~0x43 后跟 2 字节编号
            for i in fills[:6]:
                bmp.append(struct.unpack_from('<H', b, i + 1)[0])
            print('%s形状 id=%d 边界 %s 可能的位图 %s' % (pad, cid, tuple(round(x, 1) for x in bounds), bmp[:3]))
        elif code == 39:
            sid, nf = struct.unpack_from('<HH', b, body)
            print('%s精灵 id=%d 帧数 %d' % (pad, sid, nf))
            tags(b, body + 4, body + ln, depth + 1, out)
        elif code in (26, 70):
            fl = b[body]
            q = body + 1
            if code == 70:
                fl2 = b[q]
                q += 1
            dep = struct.unpack_from('<H', b, q)[0]
            q += 2
            if code == 70 and fl2 & 0x08:            # 有类名
                q = b.index(0, q) + 1
            cid = None
            if fl & 0x02:
                cid = struct.unpack_from('<H', b, q)[0]
                q += 2
            m = None
            if fl & 0x04:
                m, q = matrix(b, q)
            name = None
            if fl & 0x20 and not fl & 0x08:
                pass
            print('%s放置 depth=%d 角色=%s 矩阵=%s' % (pad, dep, cid, tuple(round(x, 3) for x in m) if m else None))
        elif code == 1:
            pass
        pos = body + ln
        if code == 0:
            break
    return out


def main(path):
    b = open(path, 'rb').read()
    if b[:3] == b'CFX':
        b = b[:8] + zlib.decompress(b[8:])
    print('版本', b[3], '长度', struct.unpack_from('<I', b, 4)[0])
    stage, q = rect(b, 8)
    print('舞台', stage)
    fr, fc = struct.unpack_from('<HH', b, q)
    print('帧率', fr / 256, '帧数', fc)
    tags(b, q + 4, len(b))


if __name__ == '__main__':
    main(sys.argv[1])
