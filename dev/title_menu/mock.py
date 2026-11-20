# -*- coding: utf-8 -*-
"""标题界面提案效果图（1920×1080）：原版 ELDEN RING 字样（去掉卢恩）+ 各提案的纹章 / 背景 / 副标题"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

H = os.path.dirname(os.path.abspath(__file__))
FZH = os.path.normpath(os.path.join(H, '..', '..', 'out', 'menu', 'dark_ui_font_zh.ttf'))
FEN = os.path.normpath(os.path.join(H, '..', '..', 'out', 'menu', 'dark_ui_font_en.ttf'))
W, HH = 1920, 1080
RAR = ['#DADADA', '#A0B4F3', '#BB2DC2', '#D4A900']
rng = np.random.default_rng(7)

logo0 = Image.open(os.path.join(H, 'logo_clean.png'))
_a = np.asarray(logo0).astype(np.float32)
_a[..., 3] = np.clip(_a[..., 3] * 3.0, 0, 255)   # 字母实心（原图是黑底加法混合，暗部别透出后面的东西）
logo0 = Image.fromarray(_a.astype(np.uint8))
logo0 = logo0.crop(logo0.getbbox())
LW = 1300
logo = logo0.resize((LW, int(logo0.size[1] * LW / logo0.size[0])), Image.LANCZOS)
LX, LY = (W - LW) // 2, 360


def rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


def canvas(top=(6, 6, 8), bottom=(2, 2, 3)):
    y = np.linspace(0, 1, HH)[:, None, None]
    c = np.array(top, np.float32) / 255 * (1 - y) + np.array(bottom, np.float32) / 255 * y
    img = np.repeat(c, W, axis=1)
    yy, xx = np.mgrid[0:HH, 0:W]
    v = 1 - 0.55 * (((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - HH / 2) / (HH * 0.75)) ** 2)
    return img * np.clip(v, 0.3, 1)[..., None]


def glow_blob(img, cx, cy, rx, ry, col, k=1.0):
    yy, xx = np.mgrid[0:HH, 0:W]
    g = np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2))
    img += g[..., None] * rgb(col) * k


def add_layer(img, layer, k=1.0):
    """layer：RGBA PIL 图，按 alpha 叠加（加法）"""
    a = np.asarray(layer).astype(np.float32) / 255
    img += a[..., :3] * a[..., 3:4] * k


def over(img, layer):
    a = np.asarray(layer).astype(np.float32) / 255
    img[:] = img * (1 - a[..., 3:4]) + a[..., :3] * a[..., 3:4]


def text_layer(txt, font, size, col, xy=None, spacing=0, anchor='mm'):
    f = ImageFont.truetype(font, size)
    L = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    if spacing:
        widths = [d.textlength(c, font=f) for c in txt]
        total = sum(widths) + spacing * (len(txt) - 1)
        x = xy[0] - total / 2
        for c, w in zip(txt, widths):
            d.text((x, xy[1]), c, font=f, fill=col, anchor='lm')
            x += w + spacing
    else:
        d.text(xy, txt, font=f, fill=col, anchor=anchor)
    return L


def glow_of(layer, radius, col, k=1.0):
    a = layer.split()[3].filter(ImageFilter.GaussianBlur(radius))
    g = Image.new('RGBA', layer.size, tuple(int(x * 255) for x in rgb(col)) + (0,))
    g.putalpha(a.point(lambda v: min(255, int(v * k))))
    return g


def logo_layer(tint=None, mul=None):
    L = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    lg = logo
    if tint is not None:
        a = np.asarray(lg).astype(np.float32)
        lum = (a[..., :3] @ np.array([0.3, 0.59, 0.11]))[..., None] / 255
        a[..., :3] = np.clip(lum * np.array(tint) * 255, 0, 255)
        lg = Image.fromarray(a.astype(np.uint8))
    if mul is not None:
        a = np.asarray(lg).astype(np.float32)
        a[..., :3] = np.clip(a[..., :3] * np.array(mul), 0, 255)
        lg = Image.fromarray(a.astype(np.uint8))
    L.alpha_composite(lg, (LX, LY))
    return L


def embers(img, n, cx, spread, y0, y1, col, size=(1, 3), streak=6, k=1.0):
    L = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    c = tuple(int(x * 255) for x in rgb(col))
    for _ in range(n):
        x = cx + rng.normal(0, spread)
        y = rng.uniform(y0, y1)
        r = rng.uniform(*size)
        a = int(255 * rng.uniform(0.35, 1.0) * (1 - (y1 - y) / (y1 - y0)) ** 0.6)
        d.line([(x, y), (x + rng.normal(0, 2), y + streak * r)], fill=c + (a,), width=max(1, int(r)))
    add_layer(img, L.filter(ImageFilter.GaussianBlur(0.8)), k)
    add_layer(img, L.filter(ImageFilter.GaussianBlur(6)), k * 0.8)


def footer(img, ver_col='#8a8578'):
    over(img, text_layer('PRESS ANY BUTTON', FEN, 30, (200, 196, 186, 210), (W // 2, 905), spacing=6))
    over(img, text_layer('Dark Reforged  v0.9.3', FEN, 22, tuple(int(x * 255) for x in rgb(ver_col)) + (230,), (W - 60, HH - 40), anchor='rm'))


def subtitle(img, en_col, zh_col, glow, y=600, gk=1.6):
    t = text_layer('DARK  REFORGED', FEN, 64, en_col, (W // 2, y), spacing=10)
    add_layer(img, glow_of(t, 14, glow, gk), 0.9)
    over(img, t)
    z = text_layer('暗 黑 重 铸', FZH, 40, zh_col, (W // 2, y + 66))
    add_layer(img, glow_of(z, 8, glow, 1.0), 0.5)
    over(img, z)


def save(img, name):
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(os.path.join(H, name))
    print('saved', name)


def noise(scale, octaves=4, seed=1):
    r = np.random.default_rng(seed)
    out = np.zeros((HH, W), np.float32)
    amp = 1.0
    for o in range(octaves):
        s = max(2, int(scale / (2 ** o)))
        small = r.random((HH // s + 2, W // s + 2)).astype(np.float32)
        up = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((W + 2 * s, HH + 2 * s), Image.BICUBIC)).astype(np.float32)[:HH, :W] / 255
        out += up * amp
        amp *= 0.5
    return out / out.max()


# ---------------- 提案一 熔炉重铸
def forge():
    img = canvas()
    glow_blob(img, W / 2, HH + 120, 900, 420, '#ff6a10', 0.55)
    glow_blob(img, W / 2, 720, 520, 60, '#ff8a20', 0.25)
    # 熔痕：字下方一道烧红的接缝
    seam = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(seam)
    for i in range(LW):
        x = LX + i
        t = abs(i - LW / 2) / (LW / 2)
        a = int(255 * (1 - t) ** 1.6)
        d.point((x, LY + logo.size[1] + 22 + int(3 * np.sin(i / 37.0))), fill=(255, 230, 170, a))
    add_layer(img, seam.filter(ImageFilter.GaussianBlur(1)), 1.0)
    add_layer(img, glow_of(seam, 10, '#ff7a1a', 4), 1.0)
    # 字下沿的余热
    ll = logo_layer()
    hot = glow_of(ll, 18, '#ff5a00', 1.2)
    add_layer(img, hot.transform(hot.size, Image.AFFINE, (1, 0, 0, 0, 1, -10)), 0.6)
    over(img, ll)
    embers(img, 520, W / 2, 420, 420, HH, '#ffb050', size=(1, 3), streak=5, k=1.0)
    subtitle(img, (255, 214, 150, 255), (222, 170, 110, 235), '#ff7a1a', y=640)
    footer(img, '#b07a4a')
    save(img, 'prop1_forge.png')


# ---------------- 提案二 四色光柱
def beams():
    img = canvas((5, 5, 8), (2, 2, 4))
    xs = [LX + LW * f for f in (0.14, 0.38, 0.62, 0.86)]
    yy, xx = np.mgrid[0:HH, 0:W]
    base = 780
    for x, col in zip(xs, RAR):
        w = 26
        core = np.exp(-((xx - x) / w) ** 2) * np.clip((base - yy) / 900 + 0.15, 0, 1) ** 0.8 * (yy < base + 20)
        halo = np.exp(-((xx - x) / (w * 5)) ** 2) * np.clip((base - yy) / 1100, 0, 1) * (yy < base)
        img += (core * 0.55 + halo * 0.18)[..., None] * rgb(col)
        glow_blob(img, x, base + 6, 150, 26, col, 0.55)
    ll = logo_layer()
    add_layer(img, glow_of(ll, 22, '#000000', 3), 0)
    over(img, ll)
    subtitle(img, (226, 196, 90, 255), (210, 190, 150, 230), '#D4A900', y=640, gk=1.3)
    tag = ['普通', '稀有', '史诗', '传说']
    for i, (t, col) in enumerate(zip(tag, RAR)):
        x = W // 2 + (i - 1.5) * 120
        over(img, text_layer(t, FZH, 26, tuple(int(v * 255) for v in rgb(col)) + (235,), (x, 790)))
    footer(img, '#9a8a5a')
    save(img, 'prop2_beams.png')


# ---------------- 提案三 魇火与咒痕
def nightmare():
    img = canvas((5, 3, 8), (1, 0, 2))
    n = noise(140, 5, seed=3)
    yy, xx = np.mgrid[0:HH, 0:W]
    rise = np.clip((yy - 260) / 820, 0, 1) ** 1.3
    side = np.exp(-((xx - W / 2) / 760) ** 2)
    flame = np.clip(n * 1.25 - 0.45, 0, 1) * rise * side
    img += flame[..., None] * (rgb('#7a22d8') * 0.75 + rgb('#BB2DC2') * 0.35)
    glow_blob(img, W / 2, 520, 760, 260, '#5a1a9a', 0.22)
    # 咒痕：一圈断开的七道红色刻痕
    cs = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(cs)
    cx, cy, R = W / 2, 520, 470
    for k in range(7):
        a0 = -90 + k * 360 / 7
        d.arc([cx - R, cy - R, cx + R, cy + R], a0 + 8, a0 + 40, fill=(200, 24, 42, 230), width=3)
        ang = np.radians(a0 + 24)
        x0, y0 = cx + (R - 16) * np.cos(ang), cy + (R - 16) * np.sin(ang)
        x1, y1 = cx + (R + 22) * np.cos(ang), cy + (R + 22) * np.sin(ang)
        d.line([(x0, y0), (x1, y1)], fill=(230, 40, 60, 240), width=4)
    add_layer(img, cs, 0.9)
    add_layer(img, glow_of(cs, 10, '#ff2040', 2.5), 0.7)
    ll = logo_layer(tint=(0.92, 0.88, 1.02))
    add_layer(img, glow_of(ll, 20, '#9a40ff', 1.4), 0.8)
    over(img, ll)
    subtitle(img, (226, 190, 255, 255), (230, 120, 140, 235), '#BB2DC2', y=640, gk=1.8)
    footer(img, '#8a6aa0')
    save(img, 'prop3_nightmare.png')


# ---------------- 提案四 稀有度圣印
def seal():
    img = canvas()
    L = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    cx, cy = W / 2, 470
    for i, col in enumerate(RAR):
        R = 210 + i * 62
        c = tuple(int(v * 255) for v in rgb(col))
        gap = 26 - i * 4
        for k in range(4):
            a0 = 45 + k * 90 + i * 22
            d.arc([cx - R, cy - R, cx + R, cy + R], a0 + gap / 2, a0 + 90 - gap / 2, fill=c + (200,), width=3 if i < 3 else 4)
    # 竖直的一道光（剑 / 锻打的那一下）
    d.line([(cx, cy - 440), (cx, cy + 300)], fill=(255, 236, 190, 170), width=3)
    add_layer(img, L, 0.75)
    add_layer(img, glow_of(L, 12, '#ffffff', 1.6), 0.35)
    for i, col in enumerate(RAR):
        add_layer(img, glow_of(L, 30, col, 0.6), 0.12)
    ll = logo_layer()
    add_layer(img, glow_of(ll, 26, '#000000', 3), 0)
    shadow = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    sh = ll.split()[3].filter(ImageFilter.GaussianBlur(16))
    shadow.putalpha(sh.point(lambda v: min(255, v * 2)))
    over(img, shadow)
    over(img, ll)
    subtitle(img, (236, 214, 150, 255), (214, 198, 160, 230), '#D4A900', y=640, gk=1.2)
    footer(img, '#8a8578')
    save(img, 'prop4_seal.png')


def hybrid():
    """推荐：熔炉 + 稀有度四色火星（火星按普通 / 稀有 / 史诗 / 传说的颜色飞起来，传说的最少最亮）"""
    img = canvas()
    glow_blob(img, W / 2, HH + 120, 900, 420, '#ff6a10', 0.45)
    glow_blob(img, W / 2, 720, 520, 60, '#ff8a20', 0.22)
    seam = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(seam)
    for i in range(LW):
        t = abs(i - LW / 2) / (LW / 2)
        d.point((LX + i, LY + logo.size[1] + 22 + int(3 * np.sin(i / 37.0))), fill=(255, 230, 170, int(255 * (1 - t) ** 1.6)))
    add_layer(img, seam.filter(ImageFilter.GaussianBlur(1)), 1.0)
    add_layer(img, glow_of(seam, 10, '#ff7a1a', 4), 1.0)
    ll = logo_layer()
    hot = glow_of(ll, 18, '#ff5a00', 1.2)
    add_layer(img, hot.transform(hot.size, Image.AFFINE, (1, 0, 0, 0, 1, -10)), 0.5)
    over(img, ll)
    for col, n, k in zip(RAR, (300, 140, 70, 30), (0.8, 1.0, 1.2, 1.6)):
        embers(img, n, W / 2, 430, 420, HH, col, size=(1, 3.2), streak=5, k=k)
    subtitle(img, (255, 214, 150, 255), (222, 170, 110, 235), '#ff7a1a', y=640)
    footer(img, '#b07a4a')
    save(img, 'prop5_hybrid.png')


if __name__ == '__main__':
    hybrid()
    forge()
    beams()
    nightmare()
    seal()
    ims = [Image.open(os.path.join(H, n)).resize((960, 540), Image.LANCZOS) for n in ('prop1_forge.png', 'prop2_beams.png', 'prop3_nightmare.png', 'prop4_seal.png')]
    sheet = Image.new('RGB', (1920, 1080))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % 2) * 960, (i // 2) * 540))
    sheet.save(os.path.join(H, 'proposals_sheet.png'))
    print('sheet')
