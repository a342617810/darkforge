# -*- coding: utf-8 -*-
"""启动器图标（用户 2026-11-11「把低难度的那个大卢恩图拿出来作为启动器在Windows下方的显示图标」）：
普通那张封面上的四色重铸环，按封面的几何（make_covers.reforge_ring：一枚环断成四段，左上起顺时针 普通 → 稀有 → 史诗 → 传说，
断口两边各留 9°；竖贯一道，上下断口各一颗星）重新画成干净的矢量图形。
第一版直接把封面的碎屑光带抠出来：光带底下那层暗光晕抠出来成了很重的黑边，碎片缩小后四色糊成一片白，加粗又把形状弄变了
（用户「形状都有点变了 而且看不出来四色 那个黑边太重了」），所以改成：每段一个实心的稀有度颜色、中间一道亮芯，没有暗色；
大尺寸上再撒一点碎屑亮纹，像封面的笔触。
  python make_icon.py
输出：launcher\\darkforge.ico（16 ~ 256），dev\\title_menu\\covers\\icon_preview.png（深色 / 浅色任务栏上的样子）"""
import io
import os
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ICO = os.path.join(ROOT, 'launcher', 'darkforge.ico')
PREVIEW = os.path.join(HERE, 'covers', 'icon_preview.png')
SIZES = (256, 128, 64, 48, 40, 32, 24, 20, 16)
SS = 8               # 先画大 8 倍，再按预乘透明度平均缩小（边缘干净，没有黑边）
GAP = 9              # 断口两边各留的角度（同封面）

# (边上的颜色, 亮芯的颜色)：四色同封面 RARITY 的光色，边上压一点（浅色任务栏上看得清），芯提亮
ARCS = (
    ((180 + GAP, 270 - GAP), ('#a8a296', '#f4f1ea')),     # 普通（左上）
    ((270 + GAP, 360 - GAP), ('#3d6ef0', '#b4cbff')),     # 稀有（右上）
    ((GAP, 90 - GAP), ('#a632e0', '#ecb4ff')),            # 史诗（右下）
    ((90 + GAP, 180 - GAP), ('#e8a010', '#ffe596')),      # 传说（左下）
)
LINE = ('#e0782a', '#ffd6a6')                             # 竖贯的一道（封面上是橙色的光）
STAR = '#fff4dc'


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def taper(t, k=0.22, lo=0.35):
    """两头收细：t 从 0 到 1，离两头 k 以内渐细到 lo"""
    e = np.clip(np.minimum(t, 1 - t) / k, 0, 1)
    return lo + (1 - lo) * (e * e * (3 - 2 * e))


def arc_poly(cx, cy, R, a0, a1, hw, n=160):
    t = np.linspace(0, 1, n)
    ang = np.radians(a0 + (a1 - a0) * t)
    w = hw * taper(t)
    c, s = np.cos(ang), np.sin(ang)
    outer = np.stack([cx + (R + w) * c, cy + (R + w) * s], 1)
    inner = np.stack([cx + (R - w) * c, cy + (R - w) * s], 1)[::-1]
    return [tuple(p) for p in np.concatenate([outer, inner])]


def line_poly(cx, y0, y1, hw, n=120):
    t = np.linspace(0, 1, n)
    y = y0 + (y1 - y0) * t
    w = hw * taper(t, 0.3, 0.15)
    return [tuple(p) for p in np.concatenate([np.stack([cx + w, y], 1), np.stack([cx - w, y], 1)[::-1]])]


def star(d, x, y, r, col, a=255):
    """四角星（竖的长一些），同封面的 star"""
    for dx, dy, k in ((1, 0, 1.0), (0, 1, 1.5)):
        rr, th = r * k, r * 0.16
        d.polygon([(x - dx * rr, y - dy * rr), (x - dy * th, y + dx * th), (x + dx * rr, y + dy * rr), (x + dy * th, y - dx * th)], fill=col + (a,))
    d.ellipse([x - r * 0.22, y - r * 0.22, x + r * 0.22, y + r * 0.22], fill=col + (a,))


def layer(n):
    return Image.new('RGBA', (n, n), (0, 0, 0, 0))


def draw(s):
    """画一个尺寸（返回 s×s 的 RGBA）"""
    n = s * SS
    small = s <= 32
    aw = s * (0.11 if s <= 20 else 0.10 if s <= 32 else 0.085 if s <= 64 else 0.07)       # 环的粗细（目标尺寸上的像素）
    aw = max(aw, 1.8)
    R = (s / 2 - aw * 0.55 - (0.4 if small else s * 0.06))
    cx = cy = n / 2
    Rn, hw = R * SS, aw * SS / 2
    rng = np.random.default_rng(11)

    out = layer(n)
    base = layer(n)
    db = ImageDraw.Draw(base)
    for (a0, a1), (edge, _core) in ARCS:
        db.polygon(arc_poly(cx, cy, Rn, a0, a1, hw), fill=rgb(edge) + (255,))
    ly0, ly1 = (0.5 if small else s * 0.03) * SS, n - (0.5 if small else s * 0.03) * SS
    db.polygon(line_poly(cx, ly0, ly1, hw * 0.62), fill=rgb(LINE[0]) + (255,))
    if s >= 48:                                     # 同色的光晕（不是暗色），小图标上只会糊
        g = base.filter(ImageFilter.GaussianBlur(s * 0.035 * SS))
        ga = np.asarray(g, np.float32)
        ga[..., 3] *= 0.5
        out = Image.alpha_composite(out, Image.fromarray(ga.astype(np.uint8), 'RGBA'))
    out = Image.alpha_composite(out, base)

    core = layer(n)
    dc = ImageDraw.Draw(core)
    for (a0, a1), (_edge, c) in ARCS:
        dc.polygon(arc_poly(cx, cy, Rn, a0, a1, hw * 0.42), fill=rgb(c) + (255,))
    dc.polygon(line_poly(cx, ly0, ly1, hw * 0.62 * 0.42), fill=rgb(LINE[1]) + (255,))
    out = Image.alpha_composite(out, core.filter(ImageFilter.GaussianBlur(hw * 0.12)))

    if s >= 64:                                     # 碎屑亮纹：顺着环走的短亮条（封面的笔触）
        fl = layer(n)
        df = ImageDraw.Draw(fl)
        for (a0, a1), (_edge, c) in ARCS:
            for _ in range(int(22 * s / 256) + 10):
                t = rng.uniform(0.08, 0.92)
                ang = np.radians(a0 + (a1 - a0) * t)
                r = Rn + rng.normal(0, hw * 0.35 * taper(np.array([t]))[0])
                px, py = cx + r * np.cos(ang), cy + r * np.sin(ang)
                tx, ty = -np.sin(ang), np.cos(ang)
                ln, th = rng.uniform(0.6, 1.6) * hw, rng.uniform(0.10, 0.22) * hw
                col = tuple(min(255, int(v * 0.4 + 255 * 0.6)) for v in rgb(c))
                df.polygon([(px - tx * ln, py - ty * ln), (px + ty * th, py - tx * th), (px + tx * ln, py + ty * ln), (px - ty * th, py + tx * th)],
                           fill=col + (int(rng.uniform(120, 230)),))
        out = Image.alpha_composite(out, fl)

    if s >= 32:                                     # 上下断口的星
        st = layer(n)
        ds = ImageDraw.Draw(st)
        for y in (cy - Rn, cy + Rn):
            star(ds, cx, y, hw * (1.5 if s >= 64 else 1.25), rgb(STAR))
        out = Image.alpha_composite(out, st)
    return shrink(out, SS)


def shrink(im, k):
    """按预乘透明度做 k×k 平均（透明处的颜色不会混进来，边上没有黑边）"""
    a = np.asarray(im, np.float32) / 255
    h = a.shape[0] // k
    pm = a[..., :3] * a[..., 3:4]
    pm = pm.reshape(h, k, h, k, 3).mean(axis=(1, 3))
    al = a[..., 3].reshape(h, k, h, k).mean(axis=(1, 3))
    col = np.where(al[..., None] > 1e-4, pm / np.maximum(al[..., None], 1e-4), 0)
    out = np.concatenate([np.clip(col, 0, 1), al[..., None]], 2)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), 'RGBA')


def dib(im):
    """.ico 里的一张 32 位 BMP：BITMAPINFOHEADER（高度写两倍）+ 自下而上的 BGRA + 1 位的 AND 遮罩（全透明的点为 1）"""
    w, h = im.size
    a = np.asarray(im.convert('RGBA'), np.uint8)
    bgra = a[::-1][..., [2, 1, 0, 3]].tobytes()
    row = ((w + 31) // 32) * 4
    mask = bytearray(row * h)
    for y in range(h):
        src = a[h - 1 - y, :, 3]
        for x in range(w):
            if src[x] == 0:
                mask[y * row + x // 8] |= 0x80 >> (x % 8)
    head = struct.pack('<IiiHHIIiiII', 40, w, h * 2, 1, 32, 0, len(bgra) + len(mask), 0, 0, 0, 0)
    return head + bgra + bytes(mask)


def write_ico(path, imgs):
    """多尺寸 .ico：256 存 PNG，小的存 32 位 BMP（老程序、.NET Framework 的 Icon 都认）"""
    blobs = []
    for im in imgs:
        if im.size[0] >= 256:
            b = io.BytesIO()
            im.save(b, 'PNG', optimize=True)
            blobs.append((im.size[0], b.getvalue()))
        else:
            blobs.append((im.size[0], dib(im)))
    head = struct.pack('<HHH', 0, 1, len(blobs))
    off = 6 + 16 * len(blobs)
    dirs, data = b'', b''
    for s, b in blobs:
        dirs += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(b), off + len(data))
        data += b
    with open(path, 'wb') as f:
        f.write(head + dirs + data)


def preview(imgs):
    """深色、浅色两种任务栏底色上：左边是实际大小，右边是放大 4 倍（小图标）/ 原大（大图标）"""
    row_h = 290
    canvas = Image.new('RGBA', (1560, row_h * 2), (0, 0, 0, 255))
    for r, bg in enumerate(((32, 32, 32, 255), (238, 238, 238, 255))):
        band = Image.new('RGBA', (1560, row_h), bg)
        x = 10
        for im in sorted(imgs, key=lambda i: i.size[0]):
            if im.size[0] <= 48:
                band.alpha_composite(im, (x, 12))
                x += im.size[0] + 10
        x += 20
        for im in imgs:
            s = im.size[0]
            show = im.resize((s * 4, s * 4), Image.NEAREST) if s <= 48 else (im if s <= 128 else im.resize((192, 192), Image.LANCZOS))
            if s in (40, 20):
                continue
            band.alpha_composite(show, (x, row_h - show.size[1] - 12))
            x += show.size[0] + 12
        canvas.paste(band, (0, r * row_h))
    canvas.convert('RGB').save(PREVIEW)


def main():
    imgs = [draw(s) for s in SIZES]
    write_ico(ICO, imgs)
    preview(imgs)
    print('ico', ICO, os.path.getsize(ICO), 'bytes; preview', PREVIEW)


if __name__ == '__main__':
    main()
