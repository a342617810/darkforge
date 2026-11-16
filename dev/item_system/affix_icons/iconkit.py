# -*- coding: utf-8 -*-
"""新词条图标的程序作画工具（用户 2026-11-11「对于每一个新词条 生成一个和名字与效果相对应的贴图 风格要尽量和原版贴近」→「不要用原版拼接了」）。
没有生图模型，所以照原版「金属吊坠 / 浮雕护符」那一类的画法用程序画：高度图（形状 + 浮雕 + 刻痕 + 锤打纹理）→ 法线 → 打光（主光左上），
金属材质（金 / 青铜 / 铁 / 银 / 骨 / 石）、凹处积灰、凸起边缘磨亮；宝石、法球单独着色；魔法类加发光。在 640×640 上画，缩成 160×160（原版图标大小），背景透明。

用法（每个图标一个函数，见 icons_*.py）：
    c = Canvas(seed)
    c.plate('diamond', 'gold', size=0.78)          # 底：菱形 / 圆 / 盾 / 水滴 / 方 吊坠，带挂环
    c.relief(c.poly(points), h=0.6)               # 纹样浮雕（点是 0~1 的坐标）
    c.engrave(c.stroke(path, w=0.01))             # 刻痕
    c.gem(c.circle(0.5, 0.5, 0.08), (180, 20, 20))
    c.glow(mask, (120, 170, 255), r=0.06, k=0.8)
    c.save('out.png')
坐标都是 0~1（左上 0,0）；粗细、半径也按画布边长的比例。"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

W = 640                     # 作画尺寸
OUT = 160                   # 原版图标尺寸
LIGHT = np.array([-0.55, -0.62, 0.56])
LIGHT = LIGHT / np.linalg.norm(LIGHT)

# 材质：（底色 RGB, 高光颜色, 光泽指数, 高光强度, 积灰颜色）
MATS = {
    'gold': ((196, 152, 58), (255, 232, 160), 30, 0.9, (58, 36, 10)),
    'oldgold': ((150, 118, 58), (240, 210, 140), 22, 0.65, (42, 30, 14)),
    'bronze': ((132, 92, 56), (238, 186, 128), 22, 0.7, (38, 26, 16)),
    'iron': ((92, 90, 88), (210, 210, 205), 30, 0.55, (24, 22, 20)),
    'darkiron': ((62, 58, 56), (180, 176, 170), 26, 0.45, (16, 14, 12)),
    'silver': ((150, 152, 156), (245, 245, 250), 40, 0.9, (40, 40, 44)),
    'bone': ((178, 166, 140), (240, 232, 210), 10, 0.25, (60, 50, 38)),
    'stone': ((112, 106, 98), (200, 196, 186), 8, 0.2, (40, 36, 32)),
    'blood': ((120, 18, 14), (255, 120, 100), 60, 0.9, (40, 4, 4)),
    # 不是吊坠的独立物件用（2026-11-11 用户：「可以不统一成吊坠风格么」）
    'steel': ((138, 138, 136), (250, 250, 244), 48, 0.95, (28, 28, 28)),
    'flesh': ((118, 34, 30), (255, 160, 140), 36, 0.55, (34, 8, 8)),
    'feather': ((164, 160, 150), (226, 226, 220), 6, 0.12, (46, 44, 40)),
    'leather': ((84, 58, 40), (180, 150, 120), 10, 0.2, (26, 18, 12)),
    'wood': ((96, 70, 48), (190, 160, 120), 8, 0.15, (30, 22, 14)),
    'cloth': ((96, 88, 76), (170, 160, 140), 4, 0.06, (30, 26, 22)),
    'glass': ((90, 120, 150), (255, 255, 255), 80, 1.0, (20, 30, 40)),
}


def _blur(a, r):
    return ndimage.gaussian_filter(a, r * W) if r > 0 else a


class Canvas:
    def __init__(self, seed=1):
        self.rng = np.random.default_rng(seed)
        self.h = np.zeros((W, W))              # 高度
        self.alpha = np.zeros((W, W))          # 物件范围
        self.mat = np.full((W, W), -1, int)    # 每个像素的材质编号
        self.mats = []
        self.color = np.zeros((W, W, 3))       # 自定义底色（宝石等）
        self.custom = np.zeros((W, W))         # 用自定义底色的权重
        self.gloss = np.zeros((W, W))          # 额外光泽（宝石、釉）
        self.glows = []                        # （遮罩, 颜色, 半径, 强度）
        self.emit = np.zeros((W, W, 3))        # 自发光（法球核心等）

    # ------------------------------------------------------------ 形状（返回 0~1 的遮罩）
    def _img(self):
        return Image.new('L', (W, W), 0)

    def _arr(self, im, soft=0.0015):
        a = np.asarray(im, np.float64) / 255.0
        return _blur(a, soft)

    def poly(self, pts, soft=0.0015):
        im = self._img()
        ImageDraw.Draw(im).polygon([(x * W, y * W) for x, y in pts], fill=255)
        return self._arr(im, soft)

    def circle(self, cx, cy, r, soft=0.0015):
        im = self._img()
        ImageDraw.Draw(im).ellipse([(cx - r) * W, (cy - r) * W, (cx + r) * W, (cy + r) * W], fill=255)
        return self._arr(im, soft)

    def ellipse(self, cx, cy, rx, ry, soft=0.0015):
        im = self._img()
        ImageDraw.Draw(im).ellipse([(cx - rx) * W, (cy - ry) * W, (cx + rx) * W, (cy + ry) * W], fill=255)
        return self._arr(im, soft)

    def teardrop(self, cx, cy, s, soft=0.0015):
        """水滴：上尖下圆（高 2s）"""
        r = s * 0.62
        oy = cy + s - r
        a = math.asin(r / (oy - (cy - s)))
        tx = r * math.cos(a)
        ty = oy - r * math.sin(a)
        tri = self.poly([(cx, cy - s), (cx + tx, ty), (cx - tx, ty)], soft)
        return np.clip(tri + self.circle(cx, oy, r, soft), 0, 1)

    def beads(self, cx, cy, r, n, br, h=0.12):
        """一圈珠点（装饰边）"""
        m = np.zeros((W, W))
        for i in range(n):
            a = i / n * 2 * math.pi
            m = np.maximum(m, self.circle(cx + r * math.cos(a), cy + r * math.sin(a), br))
        return self.relief(m, h=h, soft=0.002)

    def scratches(self, n=60, depth=0.025, mask=None):
        """细划痕（随机短线）"""
        im = self._img()
        d = ImageDraw.Draw(im)
        for _ in range(n):
            x, y = self.rng.uniform(0.1, 0.9, 2) * W
            a = self.rng.uniform(0, math.pi)
            L = self.rng.uniform(0.01, 0.05) * W
            d.line([(x, y), (x + L * math.cos(a), y + L * math.sin(a))], fill=255, width=1)
        m = self._arr(im, 0.0008) * (self.alpha > 0.5)
        if mask is not None:
            m = m * mask
        self.h -= depth * m
        return self

    def patina(self, rgb, amount=0.35, scale=0.02, thr=0.55):
        """铜锈 / 铁锈斑：凹处和随机斑块换成锈色"""
        n = _blur(self.rng.standard_normal((W, W)), scale)
        n = (n - n.min()) / (np.ptp(n) + 1e-9)
        cav = np.clip((_blur(self.h, 0.01) - self.h) * 8, 0, 1)
        m = np.clip((n - thr) * 4, 0, 1) * 0.6 + cav * 0.6
        m = np.clip(m, 0, 1) * amount * (self.alpha > 0.5) * (self.custom < 0.5)
        self.color = np.where(m[..., None] > 0.01, np.array(rgb, float)[None, None, :] * 1.0, self.color)
        self.custom = np.maximum(self.custom, m)
        return self

    def ring(self, cx, cy, r, w, soft=0.0015):
        return np.clip(self.circle(cx, cy, r + w / 2, soft) - self.circle(cx, cy, r - w / 2, soft), 0, 1)

    def stroke(self, pts, w=0.012, soft=0.0015, taper=False, wfn=None):
        """折线（平滑的话多给点）；taper = 两头变细；wfn(u) = 自定粗细倍数（u 从头 0 到尾 1，比如 lambda u: 1 - u 就是越画越细）"""
        im = self._img()
        d = ImageDraw.Draw(im)
        n = len(pts)
        for i in range(n - 1):
            k = 1.0
            u = i / max(1, n - 2)
            if wfn is not None:
                k = max(0.05, wfn(min(max(u, 0.0), 1.0)))
            elif taper:
                k = max(0.15, math.sin(math.pi * min(max(u, 0.0), 1.0)) ** 0.6)
            ww = max(1, int(w * W * k))
            d.line([(pts[i][0] * W, pts[i][1] * W), (pts[i + 1][0] * W, pts[i + 1][1] * W)], fill=255, width=ww)
            r = ww / 2
            d.ellipse([pts[i + 1][0] * W - r, pts[i + 1][1] * W - r, pts[i + 1][0] * W + r, pts[i + 1][1] * W + r], fill=255)
        return self._arr(im, soft)

    def text(self, s, cx, cy, size, font='seguisym.ttf'):
        from PIL import ImageFont
        im = self._img()
        f = ImageFont.truetype(font, int(size * W))
        ImageDraw.Draw(im).text((cx * W, cy * W), s, font=f, fill=255, anchor='mm')
        return self._arr(im)

    @staticmethod
    def spiral(cx, cy, r0, r1, turns, start=0.0, n=120, squash=1.0):
        pts = []
        for i in range(n):
            u = i / (n - 1)
            a = start + u * turns * 2 * math.pi
            r = r0 + (r1 - r0) * u
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a) * squash))
        return pts

    @staticmethod
    def arc(cx, cy, r, a0, a1, n=60):
        return [(cx + r * math.cos(a0 + (a1 - a0) * i / (n - 1)), cy + r * math.sin(a0 + (a1 - a0) * i / (n - 1))) for i in range(n)]

    @staticmethod
    def rot(pts, cx, cy, ang):
        c, s = math.cos(ang), math.sin(ang)
        return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]

    # ------------------------------------------------------------ 材质 / 高度
    def _mat_id(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def add(self, mask, mat, h=0.0, bevel=0.02, dome=0.0, profile='round'):
        """一块实心的东西：遮罩范围里设材质，高度 = h + 边缘倒角（离边越远越高，bevel 宽）+ 隆起 dome。
        后加的盖在先加的上面（遮罩内高度直接换成这块的）。profile：round 圆润 / ridge 中间一道棱（刀身）/ flat 平"""
        m = mask > 0.5
        dist = ndimage.distance_transform_edt(m) / W
        prof = np.clip(dist / max(bevel, 1e-6), 0, 1)
        if profile == 'round':
            prof = np.sin(prof * math.pi / 2)
        elif profile == 'flat':
            prof = np.clip(prof * 3, 0, 1)
        if dome:
            dmax = dist.max() + 1e-9
            prof = prof + dome * (dist / dmax) ** 0.7
        hh = h + 0.35 * prof
        self.h = np.where(mask > 0.5, np.maximum(self.h * (mask <= 0.5) + hh * (mask > 0.5), hh), self.h)
        self.alpha = np.maximum(self.alpha, mask)
        self.mat = np.where(mask > 0.5, self._mat_id(mat), self.mat)
        return self

    def relief(self, mask, h=0.25, soft=0.004, mat=None):
        """在现有表面上凸起（浮雕）：高度加 h × 柔化后的遮罩"""
        self.h += h * _blur(mask, soft)
        if mat:
            self.mat = np.where(mask > 0.5, self._mat_id(mat), self.mat)
        self.alpha = np.maximum(self.alpha, mask * (self.alpha > 0.5))
        return self

    def emboss(self, mask, h=0.3, line=0.005, depth=0.08, soft=0.004):
        """纹样：凸起 + 一圈刻进去的轮廓线（原版浮雕边上都有一道暗缝，小图上才分得清）"""
        self.relief(mask, h=h, soft=soft)
        e = mask > 0.5
        outer = ndimage.binary_dilation(e, iterations=max(1, int(line * W))) & ~e
        return self.engrave(outer.astype(float), depth=depth, soft=0.0015)

    def engrave(self, mask, depth=0.12, soft=0.0025):
        """刻痕：往下凹"""
        self.h -= depth * _blur(mask, soft)
        return self

    def hammer(self, amount=0.015, scale=0.01):
        """锤打 / 铸造的粗糙纹理"""
        n = _blur(self.rng.standard_normal((W, W)), scale)
        n /= np.abs(n).max() + 1e-9
        self.h += amount * n * (self.alpha > 0.5)
        return self

    def tint(self, mask, rgb, k=1.0, gloss=0.0):
        """局部换底色（釉、血、宝石）"""
        self.color = np.where(mask[..., None] > 0.02, np.array(rgb, float)[None, None, :], self.color)
        self.custom = np.maximum(self.custom, k * mask)
        self.gloss = np.maximum(self.gloss, gloss * mask)
        return self

    def gem(self, mask, rgb, h=0.2):
        """宝石：凸起 + 自定义颜色 + 强光泽 + 里面一点透光"""
        self.add(mask, 'silver', h=self.h[mask > 0.5].max() if (mask > 0.5).any() else 0.2, bevel=0.03, dome=0.6)
        self.tint(mask, rgb, 1.0, gloss=1.0)
        core = _blur(mask, 0.02) * mask
        self.emit += core[..., None] * np.array(rgb, float)[None, None, :] / 255.0 * 0.35
        return self

    def orb(self, cx, cy, r, rgb, glow=0.9):
        """发光法球：球面着色 + 亮核 + 外发光"""
        m = self.circle(cx, cy, r)
        self.add(m, 'silver', h=self.h.max() * 0.5 + 0.3, bevel=r, dome=1.2)
        self.tint(m, rgb, 1.0, gloss=0.8)
        yy, xx = np.mgrid[0:W, 0:W] / W
        d = np.sqrt((xx - cx + r * 0.25) ** 2 + (yy - cy + r * 0.25) ** 2) / r
        core = np.clip(1 - d, 0, 1) ** 2 * m
        self.emit += core[..., None] * (np.array(rgb, float) / 255.0 * 0.6 + 0.4)[None, None, :] * 0.9
        self.glow(m, rgb, r=r * 0.9, k=glow)
        return self

    def glow(self, mask, rgb, r=0.04, k=0.7):
        self.glows.append((mask, rgb, r, k))
        return self

    def cracks(self, mask, rgb, n=6, depth=0.06, k=0.9, w=0.006, seed_pts=None):
        """表面的裂纹，裂缝里透出光（燃烧、岩浆、诅咒）：随机分叉的折线，刻下去 + 自发光 + 外发光"""
        im = self._img()
        d = ImageDraw.Draw(im)
        ys, xs = np.nonzero(mask > 0.5)
        if not len(xs):
            return self
        starts = seed_pts or [(xs[i] / W, ys[i] / W) for i in self.rng.integers(0, len(xs), n)]

        def walk(x, y, a, L, wd, depth_left):
            pts = [(x, y)]
            for _ in range(int(L / 0.012)):
                a += self.rng.normal(0, 0.45)
                x += 0.012 * math.cos(a)
                y += 0.012 * math.sin(a)
                if not (0 <= x < 1 and 0 <= y < 1) or mask[int(y * W), int(x * W)] < 0.5:
                    break
                pts.append((x, y))
                if depth_left and self.rng.random() < 0.18:
                    walk(x, y, a + self.rng.choice([-1, 1]) * self.rng.uniform(0.5, 1.1), L * 0.5, wd * 0.6, depth_left - 1)
            if len(pts) > 1:
                d.line([(px * W, py * W) for px, py in pts], fill=255, width=max(1, int(wd * W)))

        for x, y in starts:
            walk(x, y, self.rng.uniform(0, 2 * math.pi), self.rng.uniform(0.08, 0.2), w, 2)
        cm = self._arr(im, 0.001) * mask
        self.engrave(cm, depth=depth, soft=0.001)
        hot = np.array(rgb, float) / 255.0
        self.emit += (_blur(cm, 0.002) * 1.6).clip(0, 1)[..., None] * (hot * 0.8 + 0.2)[None, None, :] * k
        self.glows.append((cm, rgb, 0.012, 0.5 * k))
        return self

    # ------------------------------------------------------------ 饰品的挂件（用户：独立物件也要「看起来像一个护符或者饰品」）
    def bail(self, x, y, mat='oldgold', r=0.03, w=0.016, h=0.3, down=0.03):
        """挂环：一个圈 + 往下接到物件上的一小截（(x, y) 是圈心，物件在下面）"""
        self.add(self.stroke([(x, y + r), (x, y + r + down)], w=w * 1.2), mat, h=h - 0.05, bevel=w * 0.5)
        self.add(self.ring(x, y, r, w), mat, h=h, bevel=w * 0.5)
        return self

    def oring(self, cx, cy, rx, ry, w, ang=0.0, n=90):
        """任意角度的椭圆环遮罩（链环、轨道环）"""
        out = [(cx + (rx + w / 2) * math.cos(a), cy + (ry + w / 2) * math.sin(a)) for a in np.linspace(0, 2 * math.pi, n)]
        inn = [(cx + max(rx - w / 2, 0.001) * math.cos(a), cy + max(ry - w / 2, 0.001) * math.sin(a)) for a in np.linspace(0, 2 * math.pi, n)]
        return np.clip(self.poly(Canvas.rot(out, cx, cy, ang)) - self.poly(Canvas.rot(inn, cx, cy, ang)), 0, 1)

    def chain(self, p0, p1, mat='iron', link=0.05, w=0.011, h=0.25):
        """一段链子：正面的环和侧面的环交替（从 p0 画到 p1）"""
        (x0, y0), (x1, y1) = p0, p1
        L = math.hypot(x1 - x0, y1 - y0)
        ang = math.atan2(y1 - y0, x1 - x0)
        n = max(1, int(round(L / (link * 0.78))))
        for i in range(n):
            u = (i + 0.5) / n
            cx, cy = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
            if i % 2 == 0:
                m = self.oring(cx, cy, link * 0.56, link * 0.32, w, ang)
                self.add(m, mat, h=h, bevel=w * 0.5)
            else:
                dx, dy = math.cos(ang) * link * 0.52, math.sin(ang) * link * 0.52
                self.add(self.stroke([(cx - dx, cy - dy), (cx + dx, cy + dy)], w=w * 1.25), mat, h=h + 0.05, bevel=w * 0.6)
        return self

    def cord(self, pts, rgb=(120, 30, 24), w=0.016, h=0.25):
        """绳 / 线：一条带斜纹的软绳"""
        m = self.stroke(pts, w=w)
        self.add(m, 'cloth', h=h, bevel=w * 0.5)
        self.tint(m, rgb, 0.9)
        for i in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            seg = math.hypot(bx - ax, by - ay)
            if seg < 1e-6:
                continue
            ux, uy = (bx - ax) / seg, (by - ay) / seg
            for t in np.arange(0, seg, w * 0.8):
                cx, cy = ax + ux * t, ay + uy * t
                self.engrave(self.stroke([(cx - uy * w * 0.5 - ux * w * 0.25, cy + ux * w * 0.5 - uy * w * 0.25),
                                          (cx + uy * w * 0.5 + ux * w * 0.25, cy - ux * w * 0.5 + uy * w * 0.25)], w=0.003), depth=0.05, soft=0.0008)
        return self

    def wisp(self, pts, rgb, w=0.012, k=0.7, r=0.012, wfn=None, core=0.8):
        """发光的轨迹（风、法球轨道、火星）：只发光，不占实体"""
        m = self.stroke(pts, w=w, wfn=wfn or (lambda u: math.sin(math.pi * u) ** 0.7))
        self.glows.append((m, rgb, r, k))
        if core:
            self.glows.append((m, tuple(min(255, int(c * 0.5 + 128)) for c in rgb), 0.002, core))
        return self

    # ------------------------------------------------------------ 底板
    def plate(self, kind, mat, size=0.78, loop=True, rim=True, cx=0.5, cy=0.53):
        """吊坠底板：diamond 菱形 / round 圆 / shield 盾 / drop 水滴 / square 方 / oval 椭圆；loop = 顶上挂环；rim = 一圈凸边"""
        s = size / 2
        if kind == 'diamond':
            pts = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
            m = self.poly(pts)
            inner = self.poly([(cx, cy - s * 0.84), (cx + s * 0.84, cy), (cx, cy + s * 0.84), (cx - s * 0.84, cy)])
            top = cy - s
        elif kind == 'round':
            m = self.circle(cx, cy, s)
            inner = self.circle(cx, cy, s * 0.86)
            top = cy - s
        elif kind == 'oval':
            m = self.ellipse(cx, cy, s * 0.8, s)
            inner = self.ellipse(cx, cy, s * 0.8 * 0.86, s * 0.86)
            top = cy - s
        elif kind == 'shield':
            pts = [(cx - s * 0.85, cy - s * 0.8), (cx + s * 0.85, cy - s * 0.8), (cx + s * 0.82, cy + s * 0.1), (cx, cy + s), (cx - s * 0.82, cy + s * 0.1)]
            m = self.poly(pts)
            inner = self.poly([(x * 0.86 + cx * 0.14, y * 0.86 + cy * 0.14) for x, y in pts])
            top = cy - s * 0.8
        elif kind == 'drop':
            m = self.teardrop(cx, cy, s)
            inner = self.teardrop(cx, cy + s * 0.05, s * 0.84)
            top = cy - s
        elif kind == 'square':
            m = self.poly([(cx - s * 0.8, cy - s * 0.8), (cx + s * 0.8, cy - s * 0.8), (cx + s * 0.8, cy + s * 0.8), (cx - s * 0.8, cy + s * 0.8)])
            inner = self.poly([(cx - s * 0.68, cy - s * 0.68), (cx + s * 0.68, cy - s * 0.68), (cx + s * 0.68, cy + s * 0.68), (cx - s * 0.68, cy + s * 0.68)])
            top = cy - s * 0.8
        else:
            raise ValueError(kind)
        self.add(m, mat, h=0.0, bevel=0.03)
        if rim:
            self.relief(np.clip(m - inner, 0, 1), h=0.18, soft=0.003)
            self.engrave(self.ring_mask_edge(inner), depth=0.08)
        if loop:
            lm = self.ring(cx, top - 0.035, 0.03, 0.016)
            self.add(lm, mat, h=0.2, bevel=0.008)
        self.inner = inner
        return self

    def hatch(self, mask, angle=0.6, gap=0.016, w=0.0035, depth=0.05):
        """原版金护符那种底纹：遮罩里刻一排平行细线"""
        yy, xx = np.mgrid[0:W, 0:W] / W
        t = (xx * math.cos(angle) + yy * math.sin(angle)) / gap
        lines = np.clip(1 - np.abs(t - np.round(t)) * gap / w, 0, 1)
        return self.engrave(lines * mask, depth=depth, soft=0.0008)

    def ring_mask_edge(self, m, w=0.006):
        e = m > 0.5
        edge = e & ~ndimage.binary_erosion(e, iterations=max(1, int(w * W)))
        return edge.astype(float)

    # ------------------------------------------------------------ 出图
    def _noise(self, scale):
        n = _blur(self.rng.standard_normal((W, W)), scale)
        return np.clip(n / (3 * n.std() + 1e-9), -1, 1)

    def render(self, light_k=1.2, ambient=0.12, grime=0.9, wear=0.7, sat=0.85, bump=0.03, rim_k=0.3,
               grit=0.35, chip=1.0, ao=0.55, outline=0.4, tilt=0.0, gamma=1.12, fit=0.0):
        # 外轮廓磕缺：离边近的地方按噪声咬掉一点（原版的东西边缘都不齐）
        if chip:
            inside = self.alpha > 0.5
            d_in = ndimage.distance_transform_edt(inside) / W
            bite = np.clip(self._noise(0.004) * 0.7 + self._noise(0.0015) * 0.3 - 0.25, 0, 1) * 0.02 * chip
            self.alpha = np.where(inside & (d_in < bite), 0.0, self.alpha)
        pits = self._noise(0.0015)
        h = _blur(self.h, 0.0012) + 0.006 * pits * (self.alpha > 0.5)
        gy, gx = np.gradient(h * W * bump)
        n = np.dstack([-gx, -gy, np.ones_like(h)])
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        ndl = np.clip(n @ LIGHT, 0, 1)
        half = LIGHT + np.array([0, 0, 1.0])
        half /= np.linalg.norm(half)
        ndh = np.clip(n @ half, 0, 1)
        # 凹处积灰（周围平均比自己高 → 凹）、凸起边缘磨亮
        cav = np.clip((_blur(h, 0.012) - h) * 6, 0, 1)
        convex = np.clip((h - _blur(h, 0.006)) * 10, 0, 1)
        base = np.zeros((W, W, 3))
        spec_c = np.zeros((W, W, 3))
        shin = np.ones((W, W)) * 20
        spk = np.zeros((W, W))
        dirt = np.zeros((W, W, 3))
        for i, name in enumerate(self.mats):
            sel = self.mat == i
            b, sc, sh, sk, dc = MATS[name]
            base[sel] = b
            spec_c[sel] = sc
            shin[sel] = sh
            spk[sel] = sk
            dirt[sel] = dc
        base = base * (1 - self.custom[..., None]) + self.color * self.custom[..., None]
        # 底色的斑驳（大块明暗）
        blot = _blur(self.rng.standard_normal((W, W)), 0.03)
        blot = blot / (np.abs(blot).max() + 1e-9)
        base = base * (1 + 0.12 * blot[..., None])
        # 细颗粒（原版贴图很「脏」：细碎的明暗点 + 黑色污点）
        # （160 图上 1 像素 ≈ 0.006，噪声要到这个尺度才看得见）
        g1, g2 = self._noise(0.0025), self._noise(0.006)
        base = base * (1 + grit * (0.6 * g1 + 0.4 * g2))[..., None]
        specks = np.clip((self._noise(0.003) - 0.5) * 3, 0, 1)
        base = base * (1 - 0.3 * specks)[..., None]
        warm = self._noise(0.04)                 # 冷暖斑驳
        base = base * (1 + 0.06 * np.dstack([warm, warm * 0.2, -warm]))
        base = base * (1 - grime * cav[..., None]) + dirt * grime * cav[..., None]
        base = base * (1 + wear * 0.35 * convex[..., None])
        spk = spk + self.gloss
        shin = shin * (1 + 2 * self.gloss)
        spec = (ndh ** shin) * spk * (1 - 0.7 * cav)
        # 右下的冷色轮廓光（原版图标边上常有一道淡淡的反光）
        rim_l = np.array([0.6, 0.55, 0.3])
        rim_l /= np.linalg.norm(rim_l)
        rim = np.clip(n @ rim_l, 0, 1) ** 3 * rim_k
        # 大的明暗：物件中心偏亮、边上偏暗（像原版那样有体积感）
        dist = ndimage.distance_transform_edt(self.alpha > 0.5) / W
        vol = np.clip(dist / 0.12, 0, 1) ** 0.5
        # 大范围的遮蔽（凹下去的大面整体暗）+ 外轮廓一圈暗边
        occ = np.clip((_blur(h, 0.025) - h) * 2.5, 0, 1) * ao
        edge = np.clip(1 - dist / 0.006, 0, 1) * outline
        shade = (ambient + light_k * 0.9 * ndl * (0.6 + 0.4 * vol)) * (1 - occ) * (1 - edge)
        lit = base / 255.0 * shade[..., None] + spec[..., None] * spec_c / 255.0 * (1 - occ[..., None])
        lit += rim[..., None] * np.array([0.55, 0.6, 0.7])[None, None, :] * (base / 255.0 + 0.2)
        lit = np.clip(lit, 0, None) ** gamma
        lit += self.emit
        rgb = np.clip(lit, 0, 1)
        # 稍微去饱和（原版颜色偏灰）
        g = rgb.mean(axis=2, keepdims=True)
        rgb = g + (rgb - g) * sat
        a = np.clip(self.alpha, 0, 1)
        # 发光：叠在物件外面和上面
        glow_rgb = np.zeros((W, W, 3))
        glow_a = np.zeros((W, W))
        for m, col, r, k in self.glows:
            gl = _blur(m, r)
            gl = gl / (gl.max() + 1e-9) * k
            glow_rgb += gl[..., None] * np.array(col, float)[None, None, :] / 255.0
            glow_a = np.maximum(glow_a, gl)
        out_rgb = rgb * a[..., None] + glow_rgb * (1 - a[..., None] * 0.6)
        out_a = np.clip(a + glow_a * (1 - a), 0, 1)
        out_rgb = np.where(out_a[..., None] > 1e-4, out_rgb / np.maximum(out_a[..., None], 1e-4), 0)
        img = np.dstack([np.clip(out_rgb, 0, 1), out_a])
        im = Image.fromarray((img * 255).astype(np.uint8), 'RGBA')
        if tilt:                               # 稍微歪一点，不要正对镜头
            im = im.rotate(tilt, resample=Image.BICUBIC, center=(W * 0.5, W * 0.5))
        if fit:                                # 原版的东西都占满图标（约 9 成）：按实体范围（不算淡的外发光）整张放大居中
            bb = im.getchannel('A').point(lambda v: 255 if v > 140 else 0).getbbox()
            if bb:
                k = fit * W / max(bb[2] - bb[0], bb[3] - bb[1])
                bx, by = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
                im = im.transform((W, W), Image.AFFINE, (1 / k, 0, bx - W / 2 / k, 0, 1 / k, by - W / 2 / k), resample=Image.BICUBIC)
        im = im.resize((OUT, OUT), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=1))
        return im

    def save(self, path, **kw):
        im = self.render(**kw)
        im.save(path)
        return im
