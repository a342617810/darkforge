# -*- coding: utf-8 -*-
"""游戏字体 → TTF（给装备工坊界面 dll\\dark_ui 用；用户 2026-10-31「能用游戏自带的字体么」）。
游戏的字体在 Data0 的 /font/<语言>/font.gfx：Scaleform GFX（SWF 格式），里面一个 DefineFont3（标签 75）——
每个字形是一串二次贝塞尔轮廓（坐标单位 1/20，em = 1024 × 20），带编码表（UCS-2）和排版表（上升、下降、行距、字宽）。
TrueType 的 glyf 也是二次曲线，直接换算：坐标 ÷ 20、y 翻转，每条 moveTo 起一个轮廓，直线边是落点，曲线边是控制点 + 落点。
只写 stb_truetype（ImGui 用它）要的表：head hhea maxp hmtx cmap(格式 12) loca glyf，外加最简单的 name / post / OS/2。
中文用 simplifiedchinese（方正书宋，9000 多字形），英文用 eu_std（Agmena）。只在本机由 menu.py 转，不打包。"""
import struct
import zlib

EM = 1024


class Bits:
    """按位读（高位在前）：一个字形的字节整个转成大整数，移位取"""
    def __init__(self, data, start, end):
        self.v, self.n, self.p = int.from_bytes(data[start:end], 'big'), (end - start) * 8, 0

    def u(self, n):
        if n == 0:
            return 0
        self.p += n
        return (self.v >> (self.n - self.p)) & ((1 << n) - 1)

    def s(self, n):
        v = self.u(n)
        return v - (1 << n) if n and v >> (n - 1) else v


def define_font3(gfx):
    """GFX / SWF 文件 → DefineFont3 标签的内容"""
    if gfx[:3] in (b'CFX', b'CWS'):
        gfx = gfx[:8] + zlib.decompress(gfx[8:])
    if gfx[:3] not in (b'GFX', b'FWS'):
        raise ValueError('不是 GFX / SWF 文件')
    nbits = gfx[8] >> 3
    off = 8 + (5 + nbits * 4 + 7) // 8 + 4
    while off + 2 <= len(gfx):
        cl = struct.unpack_from('<H', gfx, off)[0]
        code, ln = cl >> 6, cl & 0x3F
        off += 2
        if ln == 0x3F:
            ln = struct.unpack_from('<I', gfx, off)[0]
            off += 4
        if code == 75:
            return gfx[off:off + ln]
        if code == 0:
            break
        off += ln
    raise ValueError('没有 DefineFont3')


def parse(t):
    """DefineFont3 → (字体名, [(编码, 轮廓列表, 字宽)], 上升, 下降, 行距)；轮廓 = [(x, y, 在曲线上)]，单位已经是 em = 1024、y 向上"""
    flags, nl = t[2], t[4]
    name = t[5:5 + nl].split(b'\0')[0].decode('utf-8', 'replace')
    p = 5 + nl
    n = struct.unpack_from('<H', t, p)[0]
    p += 2
    wide = flags & 0x08
    fmt, sz = ('<I', 4) if wide else ('<H', 2)
    otab = p
    offs = [struct.unpack_from(fmt, t, otab + i * sz)[0] for i in range(n)]
    cto = struct.unpack_from(fmt, t, otab + n * sz)[0]
    codes = [struct.unpack_from('<H', t, otab + cto + 2 * i)[0] for i in range(n)]
    q = otab + cto + 2 * n
    asc, desc, lead, adv = EM * 0.86, EM * 0.29, 0, [EM] * n
    if flags & 0x80:
        a, d, l = struct.unpack_from('<HHh', t, q)
        asc, desc, lead = a / 20, d / 20, l / 20
        adv = [struct.unpack_from('<h', t, q + 6 + 2 * i)[0] / 20 for i in range(n)]
    glyphs = []
    for i in range(n):
        end = offs[i + 1] if i + 1 < n else cto
        glyphs.append((codes[i], shape(t, otab + offs[i], otab + end), adv[i]))
    return name, glyphs, asc, desc, lead


def shape(t, start, end):
    """一个字形的 SHAPE → 轮廓（坐标 ÷ 20，y 翻转）"""
    if end - start < 1:
        return []
    b = Bits(t, start, end)
    nfill, nline = b.u(4), b.u(4)
    x = y = 0
    contours, cur = [], None
    pt = lambda xx, yy, on: (xx / 20.0, -yy / 20.0, on)
    while b.p < b.n:
        if b.u(1) == 0:
            st = b.u(5)
            if st == 0:
                break
            if st & 0x01:                      # moveTo
                nb = b.u(5)
                x, y = b.s(nb), b.s(nb)
                cur = [pt(x, y, True)]
                contours.append(cur)
            if st & 0x02:
                b.u(nfill)
            if st & 0x04:
                b.u(nfill)
            if st & 0x08:
                b.u(nline)
            if st & 0x10:
                raise ValueError('字形里有新样式（不认识）')
        else:
            if cur is None:
                cur = [pt(x, y, True)]
                contours.append(cur)
            straight, nb = b.u(1), b.u(4) + 2
            if straight:
                if b.u(1):
                    x += b.s(nb)
                    y += b.s(nb)
                elif b.u(1):
                    y += b.s(nb)
                else:
                    x += b.s(nb)
                cur.append(pt(x, y, True))
            else:
                cx, cy = x + b.s(nb), y + b.s(nb)
                x, y = cx + b.s(nb), cy + b.s(nb)
                cur.append(pt(cx, cy, False))
                cur.append(pt(x, y, True))
    out = []
    for c in contours:
        if len(c) > 1 and c[-1][2] and round(c[-1][0]) == round(c[0][0]) and round(c[-1][1]) == round(c[0][1]):
            c = c[:-1]                          # 回到起点的那个点去掉（TrueType 轮廓自动闭合）
        if len(c) >= 3:
            out.append(c)
    return out


def _glyf(contours):
    """一个简单字形的 glyf 数据（坐标都用 16 位差值），返回 (数据, 边界)"""
    if not contours:
        return b'', (0, 0, 0, 0)
    pts = [(int(round(x)), int(round(y)), on) for c in contours for x, y, on in c]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bb = (min(xs), min(ys), max(xs), max(ys))
    ends, k = [], -1
    for c in contours:
        k += len(c)
        ends.append(k)
    d = struct.pack('>hhhhh', len(contours), *bb) + struct.pack('>%dH' % len(ends), *ends) + struct.pack('>H', 0)
    d += bytes(1 if on else 0 for _, _, on in pts)
    px = py = 0
    dx, dy = [], []
    for x, y, _ in pts:
        dx.append(x - px)
        dy.append(y - py)
        px, py = x, y
    d += struct.pack('>%dh' % len(dx), *dx) + struct.pack('>%dh' % len(dy), *dy)
    if len(d) % 4:
        d += bytes(4 - len(d) % 4)
    return d, bb


def _checksum(b):
    b = b + bytes((4 - len(b) % 4) % 4)
    return sum(struct.unpack('>%dI' % (len(b) // 4), b)) & 0xFFFFFFFF


def to_ttf(gfx):
    """GFX 字体 → (TTF 字节, 字体名, 字形数)"""
    name, raw, asc, desc, lead = parse(define_font3(gfx))
    glyphs = sorted({code: (contours, adv) for code, contours, adv in raw if 0 < code < 0xFFFF}.items())   # 编码 → (轮廓, 字宽)，按编码排
    glyf, loca, hmtx = b'', [0], []
    bbs = []
    for contours, adv in [([], EM / 2)] + [g for _c, g in glyphs]:       # 0 号是 .notdef（空）
        d, bb = _glyf(contours)
        glyf += d
        loca.append(len(glyf))
        hmtx.append((max(0, int(round(adv))), bb[0]))
        if contours:
            bbs.append(bb)
    n = len(hmtx)
    fb = (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs)) if bbs else (0, 0, 0, 0)
    a, dsc, gap = int(round(asc)), -int(round(desc)), max(0, int(round(lead)))
    tables = {}
    tables[b'head'] = struct.pack('>IIIIHHqqhhhhHHhhh', 0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0x000B, EM, 0, 0, *fb, 0, 8, 2, 1, 0)
    tables[b'hhea'] = struct.pack('>IhhhHhhhhhhhhhhhH', 0x00010000, a, dsc, gap, max(h[0] for h in hmtx), min(h[1] for h in hmtx),
                                  0, fb[2], 1, 0, 0, 0, 0, 0, 0, 0, n)
    tables[b'maxp'] = struct.pack('>IH', 0x00005000, n)
    tables[b'hmtx'] = b''.join(struct.pack('>Hh', w, l) for w, l in hmtx)
    tables[b'loca'] = struct.pack('>%dI' % len(loca), *loca)
    tables[b'glyf'] = glyf
    # cmap：格式 12，连续的编码 → 连续的字形号合成一组
    groups = []
    for gid, (code, _) in enumerate(glyphs, 1):
        if groups and groups[-1][1] + 1 == code and groups[-1][2] + (groups[-1][1] - groups[-1][0]) + 1 == gid:
            groups[-1][1] = code
        else:
            groups.append([code, code, gid])
    sub = struct.pack('>HHIII', 12, 0, 16 + 12 * len(groups), 0, len(groups)) + b''.join(struct.pack('>III', *g) for g in groups)
    tables[b'cmap'] = struct.pack('>HHHHI', 0, 1, 3, 10, 12) + sub
    nm = name.encode('utf-16-be')
    tables[b'name'] = struct.pack('>HHH', 0, 2, 6 + 24) + struct.pack('>HHHHHH', 3, 1, 0x409, 1, len(nm), 0) \
        + struct.pack('>HHHHHH', 3, 1, 0x409, 4, len(nm), 0) + nm
    tables[b'post'] = struct.pack('>IIhhIIIII', 0x00030000, 0, 0, 0, 0, 0, 0, 0, 0)
    tables[b'OS/2'] = struct.pack('>HhHHHhhhhhhhhhhh10sIIII4sHHHhhhHH', 1, EM // 2, 400, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                  bytes(10), 0, 0, 0, 0, b'DRUI', 0x40, 0x20, 0xFFFF, a, dsc, gap, max(0, fb[3]), max(0, -fb[1])) + bytes(8)
    tags = sorted(tables)
    nt = len(tags)
    es = max(k for k in range(16) if (1 << k) <= nt)
    head = struct.pack('>IHHHH', 0x00010000, nt, (1 << es) * 16, es, nt * 16 - (1 << es) * 16)
    off = 12 + 16 * nt
    recs, body = b'', b''
    for tg in tags:
        d = tables[tg]
        recs += struct.pack('>4sIII', tg, _checksum(d), off + len(body), len(d))
        body += d + bytes((4 - len(d) % 4) % 4)
    ttf = bytearray(head + recs + body)
    adj = (0xB1B0AFBA - _checksum(bytes(ttf))) & 0xFFFFFFFF
    hoff = struct.unpack_from('>I', ttf, 12 + 16 * tags.index(b'head') + 8)[0]
    struct.pack_into('>I', ttf, hoff + 8, adj)
    return bytes(ttf), name, n
