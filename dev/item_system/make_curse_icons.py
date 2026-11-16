# -*- coding: utf-8 -*-
"""咒痕页的图标（用户 2026-11-05「每个咒痕加图标，贴合原版风格，可以是原版死亡咒痕的变体」）：
底子是原版「死亡的咒痕」（道具图标 3228，缺半的百足伤环）：
  诅咒 = 缺半的环，环心放这道咒痕的图案；反转后 = 两个半环拼成完整的环（原版「死王子的修复卢恩」：两个缺半的百足伤环拼合），调成金色。
图案用同样的刮痕笔触画（放大画、抖动、按噪声打断，再缩回去）：
  众目 眼睛（反转后闭上）、千变 三臂漩涡、烙印 圆里的井字烙印（拉达冈的烙印那种）、黯辉 原版失效的大卢恩（反转后原版发光的大卢恩）、
  蚀甲 被蚀穿的盾（反转后完好）、焚魂 空心的火舌、沉寂 断续渐隐的同心圆（反转后连续的回响）、馈赠 完整的金环 + 一根树枝。
make_frames.py 的 CUSTOM 调 make(v, 键, 反转)；单独跑这个文件只出预览（本目录 咒痕图标预览.png），不碰图集。"""
import math, os, sys
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S, K = 160, 4                      # 图标大小、放大几倍画
WOUND, RUNE_DIM, RUNE_LIT = 3228, 3078, 3201   # 死亡的咒痕；失效的 / 发光的大卢恩（葛瑞克）
KEYS = ('gaze', 'vary', 'brand', 'gloom', 'erode', 'burn', 'echo')
# 暗处 → 中间 → 最亮（诅咒血红、白芯；反转后旧金，同碎片的颜色）、后面的柔光
CURSE = ((34, 8, 6), (150, 44, 36), (238, 222, 214), (150, 26, 18))
BLESS = ((44, 30, 10), (178, 142, 62), (246, 236, 196), (196, 150, 60))
RING_R = 47.0                      # 环的半径（160 格子里）
STROKE = 1.4                       # 图案笔画整体加粗（缩到列表里 72 像素还要认得出）


def _noise(seed, blur, n=S * K):
    a = np.random.RandomState(seed).rand(n // 4, n // 4).astype(np.float32)
    im = Image.fromarray((a * 255).astype(np.uint8), 'L').resize((n, n), Image.BICUBIC).filter(ImageFilter.GaussianBlur(blur))
    b = np.asarray(im, np.float32) / 255
    return (b - b.min()) / max(1e-6, b.max() - b.min())


def _warp(m, seed, amp):
    """按平滑噪声抖动（手画的感觉）：m 是放大后的 0~1 数组"""
    n = m.shape[0]
    dx, dy = ((_noise(seed + i, 14) - 0.5) * 2 * amp * K for i in (0, 1))
    yy, xx = np.mgrid[0:n, 0:n]
    return m[np.clip((yy + dy).astype(int), 0, n - 1), np.clip((xx + dx).astype(int), 0, n - 1)]


def _scratch(canvas, seed, amp=0.9, broken=0.28, hairs=70):
    """放大画好的图案 → 刮痕笔触：抖动、按噪声打断、边上长细毛"""
    m = np.asarray(canvas, np.float32) / 255
    m = _warp(m, seed, amp)
    n = _noise(seed + 7, 3)
    m = m * np.clip((n - 0.5 + (1 - broken)) * 3.2 + (1 - broken) * 0.35, 0.0, 1.0)
    if hairs:
        im = Image.new('L', canvas.size, 0)
        d = ImageDraw.Draw(im)
        rnd = np.random.RandomState(seed + 11)
        ys, xs = np.nonzero(m > 0.6)
        if len(xs):
            for i in rnd.randint(0, len(xs), hairs):
                a, ln = rnd.uniform(0, math.tau), rnd.uniform(1.5, 6.5) * K
                d.line((xs[i], ys[i], xs[i] + math.cos(a) * ln, ys[i] + math.sin(a) * ln), fill=int(rnd.uniform(120, 230)), width=max(1, int(0.4 * K)))
        m = np.maximum(m, np.asarray(im.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255)
    return m


class Pen:
    """160 格子里的坐标（放大 K 倍画）"""

    def __init__(self):
        self.im = Image.new('L', (S * K, S * K), 0)
        self.d = ImageDraw.Draw(self.im)

    def line(self, pts, w, v=255):
        p = [(x * K, y * K) for x, y in pts]
        self.d.line(p, fill=v, width=max(1, int(w * K)), joint='curve')
        for x, y in p:                        # 圆头
            self.d.ellipse((x - w * K / 2, y - w * K / 2, x + w * K / 2, y + w * K / 2), fill=v)

    def taper(self, pts, w0, w1, v=255):
        n = len(pts)
        for i, (x, y) in enumerate(pts):
            r = (w0 + (w1 - w0) * i / max(1, n - 1)) / 2 * K
            self.d.ellipse((x * K - r, y * K - r, x * K + r, y * K + r), fill=v)

    def disc(self, x, y, r, v=255):
        self.d.ellipse(((x - r) * K, (y - r) * K, (x + r) * K, (y + r) * K), fill=v)

    def poly(self, pts, v=255):
        self.d.polygon([(x * K, y * K) for x, y in pts], fill=v)


def _arc(cx, cy, r, a0, a1, n=64):
    return [(cx + math.cos(a0 + (a1 - a0) * i / n) * r, cy + math.sin(a0 + (a1 - a0) * i / n) * r) for i in range(n + 1)]


# ---------------------------------------------------------------- 图案（环心 cx, cy）
def _sk(p, pts, w, rnd, n=3, legs=0.0, leg=(2.5, 6.5), v=255):
    """一笔手划：同一条线抖着划几遍、两头细、粗细不匀，沿线几个亮斑；legs = 每隔多少点长一对细腿（百足伤环那种）"""
    L = len(pts)
    w *= STROKE
    for s in range(n):
        ph1, ph2, ph3 = rnd.uniform(0, math.tau, 3)
        amp = rnd.uniform(0.25, 0.8) * (1 if s else 0.4)
        for i, (x, y) in enumerate(pts):
            t = i / max(1, L - 1)
            env = math.sin(math.pi * t) ** 0.4
            ww = w * (0.3 + 0.7 * env) * (0.5 + 0.5 * math.sin(t * 11 + ph3) ** 2) * (1.0 if s == 0 else 0.5)
            p.disc(x + amp * math.sin(t * 9 + ph1), y + amp * math.sin(t * 7 + ph2), max(0.28, ww / 2), v)
    for _ in range(L // 14):
        x, y = pts[rnd.randint(0, L)]
        p.disc(x + rnd.uniform(-0.5, 0.5), y + rnd.uniform(-0.5, 0.5), w * rnd.uniform(0.35, 0.62), v)
    if legs:
        i = 2
        while i < L - 2:
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i + 1]
            d = math.hypot(x1 - x0, y1 - y0) or 1
            nx, ny = -(y1 - y0) / d, (x1 - x0) / d
            for sgn in (-1, 1):
                if rnd.rand() < 0.75:
                    ln, sk = rnd.uniform(*leg), rnd.uniform(-0.5, 0.5)
                    q = [(x0 + (sgn * nx + sk * (x1 - x0) / d) * ln * j / 8, y0 + (sgn * ny + sk * (y1 - y0) / d) * ln * j / 8) for j in range(9)]
                    p.taper(q, w * 0.42, 0.25, int(v * rnd.uniform(0.55, 0.95)))
            i += int(max(2, legs * rnd.uniform(0.7, 1.3)))


def _grit(p, seed, broken=0.15, dust=70, amp=0.7):
    """手划完：抖动、细碎地打断，周围撒一点灰（原版那种颗粒）"""
    m = _warp(np.asarray(p.im, np.float32) / 255, seed, amp)
    n = _noise(seed + 7, 1.6)
    m = m * np.clip((n - broken) * 4.5, 0.0, 1.0)
    rnd = np.random.RandomState(seed + 11)
    ys, xs = np.nonzero(m > 0.5)
    if len(xs) and dust:
        im = Image.new('L', (S * K, S * K), 0)
        d = ImageDraw.Draw(im)
        for i in rnd.randint(0, len(xs), dust):
            x, y, r = xs[i] + rnd.normal(0, 3.2 * K), ys[i] + rnd.normal(0, 3.2 * K), rnd.uniform(0.25, 0.6) * K
            d.ellipse((x - r, y - r, x + r, y + r), fill=int(rnd.uniform(60, 190)))
        m = np.maximum(m, np.asarray(im, np.float32) / 255)
    return m


def _bow(cx, cy, w, h, sgn, n=26, lean=0.0):
    return [(cx + w * (2 * i / n - 1), cy + lean * (2 * i / n - 1) + sgn * h * math.sin(math.pi * i / n)) for i in range(n + 1)]


def gaze(cx, cy, rev):
    p, rnd = Pen(), np.random.RandomState(201)
    eyes = ((cx + 1, cy, 22, 11, 2.7, 6.2, 0), (cx - 6, cy - 24, 12, 5.6, 2.0, 2.9, -1.5), (cx - 4, cy + 25, 12, 5.6, 2.0, 2.9, 1.5))
    for x, y, w, h, st, pu, lean in eyes:
        if rev:                                          # 反转后：眼睛闭上（敌人的目光移开了）
            lid = _bow(x, y + 1, w, h * 0.75, 1, lean=lean)
            _sk(p, lid, st * 1.15, rnd, n=3)
            for f in (5, 10, 15, 20):                    # 睫毛
                lx, ly = lid[f]
                _sk(p, [(lx + (f - 13) * 0.22 * j / 7, ly + (w * 0.3) * j / 7) for j in range(8)], st * 0.7, rnd, n=1)
        else:
            _sk(p, _bow(x, y, w, h, -1, lean=lean), st, rnd, n=3)
            _sk(p, _bow(x, y, w, h * 0.85, 1, lean=lean), st * 0.75, rnd, n=2)
            p.disc(x, y, pu)
            p.disc(x, y, pu * 0.42, 40)                  # 瞳孔中间暗
    return _grit(p, 301)


def vary(cx, cy, rev):
    p, rnd = Pen(), np.random.RandomState(202)
    n = 150
    turns = 2.1
    pts = [(cx + math.cos(-1.0 + turns * math.tau * i / n) * (33 - 28 * (i / n) ** 0.85),
            cy + math.sin(-1.0 + turns * math.tau * i / n) * (33 - 28 * (i / n) ** 0.85)) for i in range(n + 1)]
    _sk(p, pts, 3.4, rnd, n=3, legs=11, leg=(2.2, 5.0))
    return _grit(p, 302)


def brand(cx, cy, rev):
    p, rnd = Pen(), np.random.RandomState(203)
    moon = Pen()
    moon.disc(cx, cy, 27, 255)
    crater = np.asarray(moon.im, np.float32) / 255 * (0.10 + 0.34 * _noise(390, 7))    # 月面：暗、有斑
    _sk(p, _arc(cx, cy, 27.5, 0.2, math.tau + 0.2, 110), 2.5, rnd, n=3)
    for off in (-8, 8):
        _sk(p, [(cx + off - 3 + 6 * i / 24, cy - 18 + 36 * i / 24) for i in range(25)], 4.0, rnd, n=3)
        _sk(p, [(cx - 18 + 36 * i / 24, cy + off + 3 - 6 * i / 24) for i in range(25)], 4.0, rnd, n=3)
    return np.maximum(_warp(crater, 391, 0.6), _grit(p, 303, broken=0.14))


def gloom(cx, cy, rev, v):
    art = v.crop(v.items, RUNE_LIT if rev else RUNE_DIM)
    a = np.asarray(art, np.float32) / 255
    m = Image.fromarray(((a[..., :3].max(-1) * a[..., 3]) * 255).astype(np.uint8), 'L')
    m = m.crop(m.point(lambda x: 255 if x > 40 else 0).getbbox())
    size = 74 * K
    m = m.resize((size, size), Image.LANCZOS).filter(ImageFilter.MaxFilter(7))
    im = Image.new('L', (S * K, S * K), 0)
    im.paste(m, (int(cx * K - size / 2), int(cy * K - size / 2)))
    out = np.asarray(im, np.float32) / 255
    if rev:
        return np.clip(out * 1.5, 0, 1)
    return np.clip(out * 1.5, 0, 1) * np.clip((_noise(304, 6) - 0.3) * 6, 0, 1) * 0.86     # 失效的：断开、发暗


def erode(cx, cy, rev):
    p, rnd = Pen(), np.random.RandomState(205)
    n = 34
    left = [(cx - 23 + 23 * (i / n) ** 2.0, cy - 25 + 57 * i / n) for i in range(n + 1)]
    right = [(2 * cx - x, y) for x, y in left]
    top = _bow(cx, cy - 26, 23, 3.5, -1, n=26)
    _sk(p, left, 3.2, rnd)
    _sk(p, right, 3.2, rnd)
    _sk(p, top, 3.2, rnd)
    _sk(p, [(cx, cy - 26 + 52 * i / 30) for i in range(31)], 2.2, rnd, n=2)
    if rev:
        return _grit(p, 305, broken=0.1)
    m = _grit(p, 305, broken=0.2, dust=120)
    q = Pen()                                            # 蚀穿的洞，洞口一圈碎边
    for hx, hy, hr in ((cx + 10, cy - 12, 9.5), (cx - 11, cy + 6, 8), (cx + 4, cy + 17, 5)):
        q.disc(hx, hy, hr)
    hole = _warp(np.asarray(q.im, np.float32) / 255, 351, 2.6)
    rim = np.asarray(Image.fromarray((hole * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(9)), np.float32) / 255 - hole
    return np.maximum(m * (1 - hole), rim * np.clip((_noise(352, 1.6) - 0.3) * 4, 0, 1))


def burn(cx, cy, rev):
    p, rnd = Pen(), np.random.RandomState(206)

    def tongue(x0, y0, h, w, lean, side):
        n = 40
        return [(x0 + lean * (i / n) ** 2 + side * w * math.sin(math.pi * (i / n) ** 0.8) ** 0.8 * (1 - i / n) ** 0.25 + math.sin(i / n * 7 + side) * 1.6 * i / n,
                 y0 - h * i / n) for i in range(n + 1)]
    for x0, y0, h, w, lean in ((cx, cy + 30, 62, 19, 4), (cx - 15, cy + 28, 36, 9, -8), (cx + 16, cy + 28, 40, 9, 8)):
        _sk(p, tongue(x0, y0, h, w, lean, -1), 3.0, rnd)
        _sk(p, tongue(x0, y0, h, w, lean, 1), 3.0, rnd)
    for x0, h, lean in ((cx - 4, 28, 3), (cx + 5, 22, -2)):                            # 里面几笔细火苗
        _sk(p, [(x0 + lean * i / 20 + math.sin(i / 20 * 6) * 1.5, cy + 24 - h * i / 20) for i in range(21)], 1.7, rnd, n=2)
    return _grit(p, 306, dust=110)


def echo(cx, cy, rev):
    p, rnd = Pen(), np.random.RandomState(207)
    p.disc(cx, cy, 3.6)
    for k, r in enumerate((10.5, 18.5, 26.5, 34.5)):
        if rev:
            _sk(p, _arc(cx, cy, r, rnd.uniform(0, 6), rnd.uniform(0, 6) + math.tau, 70 + k * 18), 2.5 - k * 0.3, rnd, n=2, v=int(255 - k * 30))
        else:
            seg = 6 - k
            for j in range(seg):                         # 越往外越断、越淡
                a0 = j * math.tau / seg + k * 0.7 + rnd.uniform(-0.15, 0.15)
                _sk(p, _arc(cx, cy, r, a0, a0 + math.tau / seg * (0.55 - k * 0.09), 22), 2.4 - k * 0.35, rnd, n=2, v=int(240 - k * 55))
    return _grit(p, 307, broken=0.12, dust=50)


def gift(cx, cy, rev):
    p, rnd = Pen(), np.random.RandomState(208)
    n = 40
    stem = [(cx - 4 + 8 * i / n + math.sin(i / n * 3.1) * 2.4, cy + 30 - 60 * i / n) for i in range(n + 1)]
    _sk(p, stem, 3.4, rnd)
    for t, sgn, ln in ((0.28, -1, 16), (0.46, 1, 15), (0.64, -1, 12), (0.8, 1, 8)):
        x, y = stem[int(t * n)]
        _sk(p, [(x + sgn * ln * i / 14, y - ln * 0.62 * i / 14 + 2.2 * math.sin(i / 14 * 3.1)) for i in range(15)], 2.2, rnd, n=2)
    return _grit(p, 308, broken=0.1, dust=40)


# ---------------------------------------------------------------- 环
_ring = {}


def _wound_mask(v):
    """原版死亡的咒痕 → 亮度 × 透明度；拟合出环心、半径（只拟合最亮的那些点）"""
    if 'm' not in _ring:
        a = np.asarray(v.crop(v.items, WOUND), np.float32) / 255
        m = a[..., :3].max(-1) * a[..., 3]
        ys, xs = np.nonzero(m > 0.55)
        A = np.c_[2 * xs, 2 * ys, np.ones(len(xs))]
        sol = np.linalg.lstsq(A, xs ** 2 + ys ** 2, rcond=None)[0]
        _ring.update(m=Image.fromarray((m * 255).astype(np.uint8), 'L'), c=(float(sol[0]), float(sol[1])), r=float(math.sqrt(sol[2] + sol[0] ** 2 + sol[1] ** 2)))
    return _ring


def _place(v, cx, cy, rot):
    """半环缩放到 RING_R，环心放到 (cx, cy)；rot = 绕环心转的角度。返回放大后的 0~1 数组"""
    w = _wound_mask(v)
    k = RING_R / w['r'] * K
    a = math.radians(rot)
    co, si = math.cos(a) / k, math.sin(a) / k
    ox, oy = w['c']
    # 输出坐标 → 原图坐标
    coef = (co, si, ox - co * cx * K - si * cy * K, -si, co, oy + si * cx * K - co * cy * K)
    im = w['m'].transform((S * K, S * K), Image.AFFINE, coef, Image.BICUBIC)
    return np.asarray(im, np.float32) / 255


def _ring_mask(v, cx, cy, full):
    m = _place(v, cx, cy, 0)
    if full:
        m = np.maximum(m, _place(v, cx, cy, 180))
    return np.clip(m * 1.25, 0, 1)


def _finish(m, colors):
    """放大的 0~1 遮罩 → 160×160 RGBA：按亮度调色（暗 → 中 → 亮），后面一圈柔光（不盖住图）"""
    small = np.asarray(Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8), 'L').resize((S, S), Image.LANCZOS), np.float32) / 255
    lo, mid, hi, glow = (np.array(c, np.float32) / 255 for c in colors)
    t = np.clip(small, 0, 1)[..., None] ** 0.8
    rgb = np.where(t < 0.5, lo + (mid - lo) * (t / 0.5), mid + (hi - mid) * ((t - 0.5) / 0.5))
    alpha = np.clip(small * 1.5, 0, 1) ** 0.75
    fg = Image.fromarray((np.dstack([rgb, alpha]) * 255).astype(np.uint8), 'RGBA')
    g = Image.fromarray((small * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(5)).point(lambda x: min(255, int(x * 0.5)))
    out = Image.new('RGBA', (S, S), tuple(int(c * 255) for c in glow) + (0,))
    out.putalpha(g)
    out.alpha_composite(fg)
    return out


def make(v, key, rev):
    """一个图标：key 是 KEYS 里的或 'gift'；rev = 反转后（馈赠只有这一面）"""
    if rev:
        cx, cy = 80.0, 80.0
    else:
        cx, cy = 66.0, 80.0                              # 缺半的环在右边，整体往左挪一点，看着居中
    ring = _ring_mask(v, cx, cy, rev)
    mot = {'gaze': gaze, 'vary': vary, 'brand': brand, 'erode': erode, 'burn': burn, 'echo': echo, 'gift': gift}.get(key)
    motif = gloom(cx, cy, rev, v) if key == 'gloom' else mot(cx, cy, rev)
    return _finish(np.maximum(ring, motif), BLESS if rev else CURSE)


def preview():
    from make_icons import Vanilla
    v = Vanilla()
    w = _wound_mask(v)
    print('原版环心 (%.1f, %.1f) 半径 %.1f' % (w['c'][0], w['c'][1], w['r']))
    rows = [[(k, False) for k in KEYS], [(k, True) for k in KEYS] + [('gift', True)]]
    big, small = 160, 72
    sheet = Image.new('RGBA', (8 * (big + 8) + 8, 2 * (big + small + 20) + 8), (22, 20, 17, 255))
    for j, row in enumerate(rows):
        for i, (k, r) in enumerate(row):
            im = make(v, k, r)
            x, y = 8 + i * (big + 8), 8 + j * (big + small + 20)
            sheet.alpha_composite(im, (x, y))
            sheet.alpha_composite(im.resize((small, small), Image.LANCZOS), (x + (big - small) // 2, y + big + 6))
    out = os.path.join(HERE, '咒痕图标预览.png')
    sheet.save(out)
    print(out)


if __name__ == '__main__':
    preview()
