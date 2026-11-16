# -*- coding: utf-8 -*-
"""标题封面（用户 2026-11-05：保留原版 ELDEN RING 字样，不要大卢恩；两张封面，进了「死亡」以上换第二张）。
画布 = 全屏 3840×2160，标题画面上按 0.5 倍铺满（用户「黑色部分太多了，参考初版下半张图的渐变」；原版 Logo 那张 2532×1532 只占中间，框外全黑，
渐变到不了屏幕底边。菜单 menu.py 的 title_gfx 改 gfx 里这张图的尺寸和位置；原版这一层下面本来就垫着全屏不透明的黑，菜单在它上面，盖不住）。
字样 logo_letters.png（2532×1532，原版 Logo 的位置和尺寸，clean_cut.py 由用户手工抠的图做）贴在 (OX, OY)，屏幕上的位置和原版一样。
  普通：四色重铸环（线条是原版大卢恩的碎屑光带，一枚环断成四段，普通 / 稀有 / 史诗 / 传说，补上半屏的空）+ 熔痕 + 炉火烟雾，副标题 DARKFORGE / 暗黑重铸
  死亡以上：魇火 + 咒痕纹章（照原版大卢恩的画法：碎屑光带、交错的圆、竖贯的一道，外环断成七道咒痕），字变灰银
输出：covers\\*.png（封面原图）、covers\\preview_*.png（1920×1080 画面效果）、
      launcher\\reroll\\data\\menu\\dr_title_normal.dds / dr_title_hard.dds（BC7，菜单包 menu.py 放进 02_title）
用法：python make_covers.py"""
import os
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import make_anim

H = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(H, '..', '..'))
FZH = os.path.join(H, 'font', 'LongCang-Regular.ttf')               # 龙藏体（Google Fonts，SIL OFL 1.1）。只画进贴图，字体文件不进发布包
FEN = os.path.join(ROOT, 'out', 'menu', 'dark_ui_font_en.ttf')      # 游戏自带的 Agmena
BC7 = os.path.join(ROOT, 'dev', 'bc7enc', 'target', 'release', 'bc7enc.exe')
OUT_DDS = os.path.join(ROOT, 'launcher', 'reroll', 'data', 'menu')
OUT = os.path.join(H, 'covers')
W, HH = 3840, 2160
LOGO_SIZE = (2532, 1532)
OX, OY = 660, 32                                                        # 原版把 Logo 按 0.5 倍画在屏幕 (329.75, 16.05)，换算到全屏画布
CX = 1262 + OX                                                          # 字样的中线
RING_CY, RING_R = 713 + OY, 700                                         # 两张封面的环：同圆心、同半径。下面的弧从 DARKFORGE 两头外面绕过去，顶上不出屏幕
NAME_EN, NAME_ZH = 'DARKFORGE', '暗黑重铸'


def rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


YY, XX = np.mgrid[0:HH, 0:W].astype(np.float32)


_r = np.sqrt(((XX - W / 2) / (W * 0.72)) ** 2 + ((YY - HH / 2) / (HH * 0.8)) ** 2)
VIG = np.clip(1 - 0.5 * _r ** 2, 0.35, 1).astype(np.float32)[..., None]   # 四角稍暗（不到纯黑）


def blob(cx, cy, rx, ry, col, k=1.0):
    return np.exp(-(((XX - cx) / rx) ** 2 + ((YY - cy) / ry) ** 2))[..., None] * rgb(col) * k


def to_np(layer):
    return np.asarray(layer).astype(np.float32) / 255


def add(img, layer, k=1.0):
    a = to_np(layer)
    img += a[..., :3] * a[..., 3:4] * k


def base(top, bottom):
    """底色：上下渐变（都不是纯黑）"""
    y = (YY / (HH - 1))[..., None]
    return (np.array(top, np.float32) / 255 * (1 - y) + np.array(bottom, np.float32) / 255 * y) * np.ones((HH, W, 3), np.float32)


def over(img, layer):
    a = to_np(layer)
    img[:] = img * (1 - a[..., 3:4]) + a[..., :3] * a[..., 3:4]


def over_top(top, layer):
    """字样这一层（预乘 RGBA）。字和背景分开，火星才能从字后面穿过"""
    a = to_np(layer)
    al = a[..., 3:4]
    top[..., :3] = top[..., :3] * (1 - al) + a[..., :3] * al
    top[..., 3:4] = top[..., 3:4] * (1 - al) + al


def flatten(img, top):
    return img * (1 - top[..., 3:4]) + top[..., :3]


def glow(layer, radius, col, k=1.0):
    a = layer.split()[3].filter(ImageFilter.GaussianBlur(radius))
    g = Image.new('RGBA', layer.size, tuple(int(x * 255) for x in rgb(col)) + (0,))
    g.putalpha(a.point(lambda v: min(255, int(v * k))))
    return g


def text(txt, font, size, col, y, spacing=0):
    f = ImageFont.truetype(font, size)
    L = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    ws = [d.textlength(c, font=f) for c in txt]
    x = CX - (sum(ws) + spacing * (len(txt) - 1)) / 2
    for c, w in zip(txt, ws):
        d.text((x, y), c, font=f, fill=col, anchor='lm')
        x += w + spacing
    return L


def letters(tint=None):
    lg = Image.open(os.path.join(H, 'logo_letters.png')).convert('RGBA')
    if lg.size != LOGO_SIZE:
        raise ValueError('logo_letters.png 不是 %d×%d（先跑 clean_cut.py）' % LOGO_SIZE)
    if tint is not None:
        a = np.asarray(lg).astype(np.float32)
        lum = (a[..., :3] @ np.array([0.3, 0.59, 0.11], np.float32))[..., None]
        a[..., :3] = np.clip(lum * np.array(tint, np.float32), 0, 255)
        lg = Image.fromarray(a.astype(np.uint8))
    L = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    L.paste(lg, (OX, OY))
    return L


def noise(scale, octaves, seed):
    r = np.random.default_rng(seed)
    out = np.zeros((HH, W), np.float32)
    amp = 1.0
    for o in range(octaves):
        s = max(2, int(scale / 2 ** o))
        small = (r.random((HH // s + 3, W // s + 3)) * 255).astype(np.uint8)
        up = np.asarray(Image.fromarray(small).resize(((W // s + 3) * s, (HH // s + 3) * s), Image.BICUBIC)).astype(np.float32)[:HH, :W] / 255
        out += up * amp
        amp *= 0.5
    return out / out.max()


def stone_tile(w, h, seed=4):
    """字样同款的石纹（灰度，拉过对比）：从 logo_letters.png 里抠完全在字里面的小块，随机拼一张"""
    lg = np.asarray(Image.open(os.path.join(H, 'logo_letters.png')).convert('L')), np.asarray(Image.open(os.path.join(H, 'logo_letters.png')).convert('RGBA'))[..., 3]
    r = np.random.default_rng(seed)
    B = 36
    good = [(x, y) for y in range(0, lg[0].shape[0] - B, 9) for x in range(0, lg[0].shape[1] - B, 9) if (lg[1][y:y + B, x:x + B] > 200).mean() > 0.97]
    yy, xx = np.mgrid[0:B, 0:B]
    fe = np.clip(np.minimum(np.minimum(xx, B - 1 - xx), np.minimum(yy, B - 1 - yy)) / (B / 2), 0.02, 1).astype(np.float32)
    tex, wt = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32) + 1e-4
    for k in range(w * h // 180):
        x, y = good[int(r.integers(len(good)))]
        u, v = int(r.integers(-B // 2, w - B // 2)), int(r.integers(-B // 2, h - B // 2))
        u0, v0, u1, v1 = max(u, 0), max(v, 0), min(u + B, w), min(v + B, h)
        tex[v0:v1, u0:u1] += (lg[0][y:y + B, x:x + B].astype(np.float32) / 255 * fe)[v0 - v:v1 - v, u0 - u:u1 - u]
        wt[v0:v1, u0:u1] += fe[v0 - v:v1 - v, u0 - u:u1 - u]
    tex /= wt
    return np.clip((tex - tex.mean()) * 2.4 + 0.5, 0, 1)


def zh_stone(img, top, ramp, glow_col, seed=1):
    """中文副标题：石头材质（用户「石纹确实不明显，亮度可以提」）。这行字在屏幕上只有约 57 像素，细纹理缩下去就糊了，所以靠小尺寸也看得出的东西：
    边缘崩缺、棱边（左上亮右下暗）、大块明暗、凹坑、裂缝。ramp = (暗, 中, 亮) 三个颜色"""
    x0, x1, y0, y1 = CX - 620, CX + 620, 1194 + OY - 150, 1194 + OY + 150       # 只算字附近
    w, h = x1 - x0, y1 - y0

    def blur(a, r):
        return np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255

    def zn(scale, sd):                                                          # 零均值、单位方差的噪声
        n = noise(scale, 3, sd)[y0:y1, x0:x1]
        return (n - n.mean()) / n.std()

    f = ImageFont.truetype(FZH, 115)
    L = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(L)
    ws = [d.textlength(c, font=f) for c in NAME_ZH]
    x = w / 2 - (sum(ws) + 18 * (len(NAME_ZH) - 1)) / 2
    for c, q in zip(NAME_ZH, ws):
        d.text((x, h / 2), c, font=f, fill=255, anchor='lm')
        x += q + 18
    mask = np.clip((blur(np.asarray(L).astype(np.float32) / 255, 1.3) - (0.40 + zn(14, seed + 1) * 0.10)) / 0.10 + 0.5, 0, 1)    # 边缘崩缺（阈值偏低，笔画别蚀太细）
    st = np.asarray(Image.fromarray((stone_tile(w // 2 + 1, h // 2 + 1) * 255).astype(np.uint8)).resize((w + 2, h + 2), Image.BICUBIC)).astype(np.float32)[:h, :w] / 255
    tone = 0.35 * st + 0.65 * np.clip(zn(26, seed + 2) * 0.5 + 0.5, 0, 1)       # 大块明暗 + 字样同款的石纹
    tone = tone * (1 - 0.75 * np.clip((zn(8, seed + 5) - 1.0) * 1.6, 0, 1))      # 凹坑
    gy, gx = np.gradient(blur(mask, 2.2))
    tone = tone + np.clip(-(gx * 0.6 + gy * 0.8) * 3.8, -0.75, 0.75)            # 棱边
    r = np.random.default_rng(seed + 3)                                          # 裂缝：随机走的折线
    C = Image.new('L', (w, h), 0)
    dc = ImageDraw.Draw(C)
    for k in range(40):
        px, py = w / 2 + r.uniform(-300, 300), h / 2 + r.uniform(-70, 70)
        a = r.uniform(0, 6.28)
        for t in range(int(r.integers(4, 11))):
            a += r.normal(0, 0.55)
            ln = r.uniform(7, 17)
            qx, qy = px + np.cos(a) * ln, py + np.sin(a) * ln
            dc.line([(px, py), (qx, qy)], fill=255, width=3 if t < 3 else 2)
            px, py = qx, qy
    tone = np.clip(tone * 0.74 + 0.30, 0, 1)                                     # 整体提亮，明暗还在
    tone = np.clip(tone * (1 - 0.8 * blur(np.asarray(C).astype(np.float32) / 255, 0.6) ** 0.8), 0, 1)[..., None]
    c0, c1, c2 = (np.array(q, np.float32) / 255 for q in ramp)
    col = np.where(tone < 0.5, c0 + (c1 - c0) * tone * 2, c1 + (c2 - c1) * (tone - 0.5) * 2)
    sh = blur(np.roll(np.roll(mask, 3, 0), 2, 1), 4.0)[..., None]                # 暗影把字托起来 + 同色的光
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - 0.8 * sh) + blur(mask, 15)[..., None] * rgb(glow_col) * 0.95
    m = mask[..., None]
    t = top[y0:y1, x0:x1]
    t[..., :3] = t[..., :3] * (1 - m) + col * m
    t[..., 3:4] = t[..., 3:4] * (1 - m) + m


def subtitle(img, top, en_col, zh_ramp, glow_col, gk=1.6):
    t = text(NAME_EN, FEN, 150, en_col, 1062 + OY, spacing=34)
    add(img, glow(t, 26, glow_col, gk), 0.9)
    over_top(top, t)
    zh_stone(img, top, zh_ramp, glow_col)


# ---------------------------------------------------------------- 普通：熔炉 + 四色重铸环
def normal():
    rng = np.random.default_rng(11)
    img = base((16, 10, 8), (12, 6, 4))
    # 下半屏的炉火渐变（照初版：屏幕底边最亮，往上渐暗），字后面一层很淡的暖光，顶上不是纯黑
    img += blob(W / 2, HH + 240, 2000, 980, '#ff6a10', 0.72) + blob(W / 2, 1450, 1500, 170, '#ff8a20', 0.2) + blob(CX, 700, 2000, 680, '#5a2410', 0.32)
    img *= VIG                                                                  # 烟雾是飘动的粒子，make_anim.py 做（静态图取它的一帧）
    origin, arcs = reforge_ring(img, rng)
    top = np.zeros((HH, W, 4), np.float32)
    # 熔痕：字下面烧红的一道接缝，中间白热、两头收细
    seam = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    d = ImageDraw.Draw(seam)
    x0, x1 = 240 + OX, 2290 + OX
    for x in range(x0, x1):
        a = max(0.0, 1 - abs(x - CX) / ((x1 - x0) / 2)) ** 1.5
        y = 942 + OY + 5 * np.sin(x / 61.0) + 3 * np.sin(x / 17.0)
        d.ellipse([x - 2.2, y - 2.2 * a - 0.6, x + 2.2, y + 2.2 * a + 0.6], fill=(255, 236, 190, int(255 * a)))
    add(img, seam.filter(ImageFilter.GaussianBlur(1.2)), 1.0)
    add(img, glow(seam, 18, '#ff6a10', 5), 1.0)
    add(img, glow(seam, 60, '#ff5000', 3), 0.6)
    # 字的余热（下沿透一点橙光）+ 字
    lg = letters()
    hot = glow(lg, 34, '#ff5a00', 1.3)
    add(img, hot.transform(hot.size, Image.AFFINE, (1, 0, 0, 0, 1, -18)), 0.55)
    over_top(top, lg)
    # 副标题后面压暗一点，字不被火星抢
    shade = 1 - 0.45 * np.exp(-(((XX - CX) / 720) ** 2 + ((YY - 1157) / 120) ** 2))[..., None]
    img *= shade
    top[..., :3] *= shade
    subtitle(img, top, (255, 222, 164, 255), ((112, 70, 42), (236, 196, 136), (255, 246, 220)), '#ff7a1a')
    return img, top, dict(origin=origin, arcs=arcs)


# ---------------------------------------------------------------- 死亡以上：魇火 + 咒痕纹章
def arc_pts(cx, cy, R, a0, a1, step=1.5):
    n = max(2, int(abs(a1 - a0) * np.pi / 180 * R / step))
    t = np.radians(np.linspace(a0, a1, n))
    return np.stack([cx + R * np.cos(t), cy + R * np.sin(t)], 1)


def line_pts(x0, y0, x1, y1, step=1.5):
    n = max(2, int(np.hypot(x1 - x0, y1 - y0) / step))
    return np.stack([np.linspace(x0, x1, n), np.linspace(y0, y1, n)], 1)


# 纹章的配色：(暗光带, 碎片的三种颜色)。金色是原版大卢恩的米黄、橙、灰
CURSE = ((120, 16, 40), ((255, 206, 214), (255, 142, 160), (214, 190, 236)))
GOLD = ((150, 70, 18), ((246, 226, 180), (255, 170, 90), (190, 186, 176)))
RARITY = (                                                                      # 四色重铸环：(配色, 光的颜色)，普通 / 稀有 / 史诗 / 传说
    (((110, 105, 100), ((250, 248, 240), (215, 210, 200), (180, 175, 170))), '#d8d4cc'),
    (((40, 60, 140), ((200, 218, 255), (111, 155, 255), (150, 170, 220))), '#5a86ff'),
    (((90, 30, 130), ((240, 190, 255), (209, 75, 255), (190, 150, 220))), '#c040f0'),
    (((150, 90, 12), ((255, 236, 170), (255, 210, 30), (220, 190, 120))), '#ffb820'),
)


def band(dark, bright, pts, rng, w=26.0, density=0.34, taper=False, pal=CURSE):  # noqa: C901
    """照原版大卢恩的笔触画一条粗光带（2026-11-05 放大对比原版：不是细线，是暗光晕上顺着走向排的亮碎片，时疏时密）：
    dark 上画暗的底（之后模糊成光晕），bright 上画碎片。taper：两头收细（竖线）"""
    m = len(pts)
    tang = np.gradient(pts, axis=0)
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-6)
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    t = np.arange(m, dtype=np.float32)
    ph = rng.uniform(0, 6.3, 3)
    dens = np.clip(0.55 + 0.45 * np.sin(t / 53 + ph[0]) * np.sin(t / 19 + ph[1]), 0, 1)     # 时疏时密
    wid = np.ones(m, np.float32)
    if taper:
        wid = np.clip(np.minimum(t, m - 1 - t) / (m * 0.25), 0.25, 1)
    dd = ImageDraw.Draw(dark)
    for k in range(0, m - 6, 6):
        dd.line([tuple(pts[k]), tuple(pts[k + 6])], fill=pal[0] + (int(150 * dens[k] + 60),), width=max(4, int(w * wid[k] * 0.9)))
    db = ImageDraw.Draw(bright)
    n = int(m * density * 1.9)           # 碎片密一些（第一版看着是一串散点，原版连成带）
    for _ in range(n):
        k = int(rng.integers(m))
        if rng.random() > dens[k] * 0.9 + 0.1:
            continue
        off = rng.normal(0, w * wid[k] * 0.34)
        ln = rng.uniform(5, 26)
        th = rng.uniform(1.2, 4.2)
        # 碎片顺着走向，带一点歪斜
        skew = rng.normal(0, 0.35)
        dx, dy = tang[k] + nrm[k] * skew
        cx, cy = pts[k] + nrm[k] * off
        nx, ny = -dy, dx
        poly = [(cx - dx * ln / 2, cy - dy * ln / 2), (cx + nx * th * rng.uniform(.5, 1), cy + ny * th * rng.uniform(.5, 1)),
                (cx + dx * ln / 2, cy + dy * ln / 2), (cx - nx * th * rng.uniform(.5, 1), cy - ny * th * rng.uniform(.5, 1))]
        pick = rng.random()
        col = pal[1][0] if pick < 0.55 else (pal[1][1] if pick < 0.85 else pal[1][2])
        db.polygon(poly, fill=col + (int(rng.uniform(110, 255)),))


def star(bright, x, y, r, col=(255, 232, 236)):
    """交叉点的星形亮点（原版大卢恩的交叉点、底部都有）：十字细光 + 中心一点"""
    d = ImageDraw.Draw(bright)
    for dx, dy, k in ((1, 0, 1.0), (0, 1, 1.5), (.7, .7, .35), (.7, -.7, .35)):
        rr = r * k
        d.polygon([(x - dx * rr, y - dy * rr), (x - dy * 2.2, y + dx * 2.2), (x + dx * rr, y + dy * rr), (x + dy * 2.2, y - dx * 2.2)], fill=col + (235,))
    d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(255, 245, 246, 255))


def reforge_ring(img, rng):
    """四色重铸环（用户 2026-11-05 选的，之前试过铁砧都不合适）：一枚环断成四段，每段一个稀有度，左上起顺时针 普通 → 稀有 → 史诗 → 传说；竖贯一道连起上下两个断口。
    和死亡以上那张的七段咒痕环成对（圆心、半径共用 RING_CY、RING_R）。返回圆心、每段单独的光"""
    cy, R = RING_CY, RING_R
    m = Image.new('L', (W, HH), 0)
    ImageDraw.Draw(m).ellipse([CX - R, cy - R, CX + R, cy + R], fill=255)
    img *= 1 - 0.25 * to_np(m.filter(ImageFilter.GaussianBlur(40)))[..., None]
    gap = 9
    arcs = []                                                                   # 每段单独的光（动画里按段点亮）
    for (a0, a1), (pal, col) in zip(((180 + gap, 270 - gap), (270 + gap, 360 - gap), (gap, 90 - gap), (90 + gap, 180 - gap)), RARITY):
        dark = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
        bright = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
        band(dark, bright, arc_pts(CX, cy, R, a0, a1), rng, w=34, density=0.5, taper=True, pal=pal)
        rune_light(img, dark, bright, col, col)
        ov = np.zeros((HH, W, 3), np.float32)
        rune_light(ov, dark, bright, col, col)
        arcs.append(make_anim.ring_layer(ov))
    dark = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    bright = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    band(dark, bright, line_pts(CX, 6, CX, 1530), rng, w=20, density=0.3, taper=True, pal=GOLD)
    star(bright, CX, cy - R, 54, (255, 236, 196))
    star(bright, CX, cy + R, 54, (255, 236, 196))
    rune_light(img, dark, bright, '#ff9a3c', '#ff7a1a')
    return (float(CX), float(cy)), arcs


def rune_light(img, dark, bright, inner, outer):
    """碎屑光带上光：暗光带模糊成光晕 + 两层同色光 + 碎片本身（比字暗，原版的卢恩也压得很低）"""
    add(img, dark.filter(ImageFilter.GaussianBlur(22)), 0.8)
    add(img, glow(bright, 44, outer, 2.0), 0.24)
    add(img, glow(bright, 9, inner, 1.8), 0.34)
    add(img, bright.filter(ImageFilter.GaussianBlur(0.7)), 0.8)


def sigil(rng):
    dark = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    bright = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    cy0, R = RING_CY, RING_R
    c1, c2 = (CX, cy0 - 108, 360), (CX, cy0 + 257, 257)
    # 竖贯的一道（长度同普通那张）
    band(dark, bright, line_pts(CX, 6, CX, 1530), rng, w=30, density=0.42, taper=True)
    # 交错的两个圆
    for cx, cy, r_ in (c1, c2):
        band(dark, bright, arc_pts(cx, cy, r_, 0, 360), rng, w=26, density=0.4)
    # 外环断成七段（七道咒痕），每个断口一道刻痕。每段单独一层（连同它后面的刻痕和星），动画里顺时针依次亮
    segs = []
    for k in range(7):
        a0 = -90 + k * 360 / 7 + 8
        a1 = a0 + 360 / 7 - 16
        d_ = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
        b_ = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
        band(d_, b_, arc_pts(CX, cy0, R, a0, a1), rng, w=24, density=0.36)
        g = np.radians(a1 + 8)
        p0, p1 = (CX + (R - 62) * np.cos(g), cy0 + (R - 62) * np.sin(g)), (CX + (R + 66) * np.cos(g), cy0 + (R + 66) * np.sin(g))
        band(d_, b_, line_pts(p0[0], p0[1], p1[0], p1[1]), rng, w=16, density=0.8, taper=True)
        star(b_, CX + R * np.cos(g), cy0 + R * np.sin(g), 30)
        segs.append((d_, b_))
        dark, bright = Image.alpha_composite(dark, d_), Image.alpha_composite(bright, b_)
    # 底下的一弯（原版大卢恩下面那一弯）和底部的星
    band(dark, bright, arc_pts(CX, cy0 + R + 55 - 1190, 1190, 60, 120), rng, w=18, density=0.28)       # 最低点在环的下面一点
    star(bright, CX, cy0 + R + 55, 70)
    for x, y, r_ in ((CX, c1[1] - c1[2], 46), (CX, c1[1] + c1[2], 40), (CX, c2[1] + c2[2], 40)):
        star(bright, x, y, r_)
    return dark, bright, segs


def curse_light(img, dark, bright, k=1.0):
    """咒痕上光"""
    add(img, dark.filter(ImageFilter.GaussianBlur(22)), 0.85 * k)               # 暗红的光晕
    add(img, glow(bright, 44, '#7a22d8', 2.0), 0.55 * k)                        # 外面一层紫
    add(img, glow(bright, 9, '#e02448', 1.8), 0.7 * k)
    add(img, bright.filter(ImageFilter.GaussianBlur(0.7)), 0.95 * k)


def hard():
    rng = np.random.default_rng(23)
    img = base((14, 8, 22), (10, 4, 18))
    # 下半屏的魇火：屏幕底边最亮，往上渐暗（同普通那张的版式）
    img += blob(W / 2, HH + 240, 2000, 980, '#6a1cc0', 0.55) + blob(W / 2, 1450, 1500, 170, '#8a2ae0', 0.12) + blob(CX, 760, 2000, 620, '#2a0e4a', 0.4)
    img *= VIG                                                                  # 魇火的烟雾是飘动的粒子，make_anim.py 做（同普通那张）
    dark, bright, segs = sigil(rng)
    curse_light(img, dark, bright)
    arcs = []
    for d_, b_ in segs:
        ov = np.zeros((HH, W, 3), np.float32)
        curse_light(ov, d_, b_, 0.6)                                            # 纹章本来就亮，点亮时不用再翻一倍
        arcs.append(make_anim.ring_layer(ov))
    # 副标题后面压暗：纹章不抢字
    img *= 1 - 0.72 * np.exp(-(((XX - CX) / 620) ** 2 + ((YY - 1125 - OY) / 120) ** 2))[..., None]
    lg = letters(tint=(0.93, 0.89, 1.03))
    top = np.zeros((HH, W, 4), np.float32)
    add(img, glow(lg, 36, '#8a34ee', 1.1), 0.6)
    shade = Image.new('RGBA', (W, HH), (0, 0, 0, 0))
    shade.putalpha(lg.split()[3].filter(ImageFilter.GaussianBlur(10)).point(lambda v: min(255, v * 2)))
    over(img, shade)
    over_top(top, lg)
    subtitle(img, top, (232, 196, 255, 255), ((86, 72, 112), (216, 204, 238), (255, 252, 255)), '#BB2DC2', gk=1.9)
    return img, top, dict(arcs=arcs)


# ---------------------------------------------------------------- 输出
def save_png(img, name):
    # 抖动一点，暗部的大渐变不出色带
    img = img + np.random.default_rng(3).normal(0, 0.5 / 255, img.shape).astype(np.float32)
    rgb8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(rgb8).save(os.path.join(OUT, name + '.png'))
    # 画面效果：1920×1080；下面放一行「按任意键」的示意
    scr = Image.fromarray(rgb8).resize((1920, 1080), Image.LANCZOS)
    ImageDraw.Draw(scr).text((960, 880), 'PRESS ANY BUTTON', font=ImageFont.truetype(FEN, 30), fill=(200, 196, 186), anchor='mm')
    scr.save(os.path.join(OUT, 'preview_' + name + '.png'))
    return rgb8


def bc7_dds(rgb8, path):
    """RGB 或 RGBA → BC7（dev\\bc7enc：输入按 4×4 块排的 RGBA），写 DX10 头的 DDS（一级、不带 mipmap，同原版 SB_Title_01）"""
    h, w = rgb8.shape[:2]
    rgba = rgb8 if rgb8.shape[2] == 4 else np.dstack([rgb8, np.full((h, w), 255, np.uint8)])
    blocks = rgba.reshape(h // 4, 4, w // 4, 4, 4).transpose(0, 2, 1, 3, 4).tobytes()
    with tempfile.TemporaryDirectory() as td:
        src, dst = os.path.join(td, 'in.bin'), os.path.join(td, 'out.bin')
        open(src, 'wb').write(blocks)
        subprocess.run([BC7, src, dst], check=True)
        data = open(dst, 'rb').read()
    if len(data) != (w // 4) * (h // 4) * 16:
        raise RuntimeError('BC7 输出长度不对')
    hdr = struct.pack('<4sIIIIIII44xII4s20xI16x', b'DDS ', 124, 0x81007, h, w, len(data), 0, 1, 32, 0x4, b'DX10', 0x1000)
    dx10 = struct.pack('<IIIII', 98, 3, 0, 1, 0)
    tmp = path + '.tmp'
    open(tmp, 'wb').write(hdr + dx10 + data)
    os.replace(tmp, path)


def main():
    for name, fn in (('normal', normal), ('hard', hard)):
        img, top, info = fn()
        make_anim.build(name, img, top, info, bc7_dds, OUT_DDS)
        rgb8 = save_png(flatten(img + make_anim.smoke_still(HH, W, name), top), name)       # 静态版（动画出问题时的回退）取动画的一帧烟雾
        bc7_dds(rgb8, os.path.join(OUT_DDS, 'dr_title_%s.dds' % name))
        print('ok', name)


if __name__ == '__main__':
    main()
