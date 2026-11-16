# -*- coding: utf-8 -*-
"""第 1 批：姿态 / 战技 / 杂项（设计清单.md「第 1 批」，11 个词条）。画法照 icons_charm.py：每个词条一件能戴的护符，
金属铸造 / 镶嵌 / 骨雕 / 绳结，带挂环、链子或绳子，压暗做旧，发光很克制。
挂法轮流：挂环 = 优雅 / 转念 / 心流 / 乘势；链 = 怒意 / 破势 / 霸王 / 拾遗；绳 = 静心 / 换气 / 鸡尾酒。
用法：python batch_stance.py [键 ...]（不给键就全画），出 out/charm_<键>.png + out/sheet_stance.png（+ _x2）"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import Canvas, W, _blur  # noqa: E402
from icons_obj import _unit  # noqa: E402
from icons_charm import DARK, _smooth  # noqa: E402

OUT = os.path.join(HERE, 'out')
KEYS = ['dr_elegance', 'dr_calm', 'dr_rage', 'dr_turn', 'dr_break', 'dr_second_breath',
        'dr_flow', 'dr_overlord', 'dr_momentum', 'dr_cocktail', 'dr_magnet']


# ------------------------------------------------------------------ 小工具（只在本文件里用）
def _bez(p0, p1, p2, p3, n=60):
    pts = []
    for i in range(n):
        t = i / (n - 1)
        a, b, cc, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        pts.append((a * p0[0] + b * p1[0] + cc * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + cc * p2[1] + d * p3[1]))
    return pts


def _frames(pts):
    """每个点的切向 (tx, ty) 和法向 (nx, ny)"""
    out = []
    n = len(pts)
    for i in range(n):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        tx, ty = _unit(b[0] - a[0], b[1] - a[1])
        out.append((tx, ty, -ty, tx))
    return out


def _ribbon(c, pts, wfn, soft=0.0015):
    """沿中心线的变宽带子（比 stroke 的 wfn 平滑，粗的东西用这个：角、号角、马蹄铁）"""
    fr = _frames(pts)
    n = len(pts)
    L, R = [], []
    for i, ((x, y), (tx, ty, nx, ny)) in enumerate(zip(pts, fr)):
        w = wfn(i / (n - 1)) / 2
        L.append((x + nx * w, y + ny * w))
        R.append((x - nx * w, y - ny * w))
    return c.poly(L + R[::-1], soft)


def _rellipse(c, cx, cy, rx, ry, ang=0.0, n=72, soft=0.0015):
    pts = [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in np.linspace(0, 2 * math.pi, n, endpoint=False)]
    return c.poly(Canvas.rot(pts, cx, cy, ang), soft)


def _dots(c, pts, r, soft=0.0015):
    im = c._img()
    d = ImageDraw.Draw(im)
    for x, y in pts:
        d.ellipse([(x - r) * W, (y - r) * W, (x + r) * W, (y + r) * W], fill=255)
    return c._arr(im, soft)


def _cut(c, mask, rim=0.004, depth=0.1):
    """镂空：孔口先往下压一点（有倒角），再挖透"""
    c.engrave(np.clip(_blur(mask, rim) * 1.5, 0, 1), depth=depth)
    c.alpha = np.minimum(c.alpha, 1 - np.clip(mask, 0, 1))


def _mottle(c, mask, ca, cb, scale=0.02, k=1.0, gloss=0.0, bias=0.0, contrast=1.2):
    """局部上色：两种颜色按噪声斑驳混合（玉、琥珀、旧漆）"""
    t = np.clip(c._noise(scale) * contrast + 0.5 + bias, 0, 1)[..., None]
    col = np.array(ca, float) * (1 - t) + np.array(cb, float) * t
    sel = mask > 0.02
    c.color = np.where(sel[..., None], col, c.color)
    c.custom = np.maximum(c.custom, k * mask)
    c.gloss = np.maximum(c.gloss, gloss * mask)


def _patch(c, mask, rgb, amount=0.5, scale=0.015, thr=0.5):
    """只在遮罩里长锈 / 铜绿（patina 是全图的）"""
    n = _blur(c.rng.standard_normal((W, W)), scale)
    n = (n - n.min()) / (np.ptp(n) + 1e-9)
    cav = np.clip((_blur(c.h, 0.01) - c.h) * 8, 0, 1)
    m = np.clip(np.clip((n - thr) * 4, 0, 1) * 0.6 + cav * 0.6, 0, 1) * amount * mask * (c.custom < 0.5)
    c.color = np.where(m[..., None] > 0.01, np.array(rgb, float)[None, None, :], c.color)
    c.custom = np.maximum(c.custom, m)


def _crack(c, x, y, a, L, w, mask, depth=0.1, rgb=(24, 18, 14), branch=2, step=0.01, ember=0.0):
    """一道裂纹（往 a 方向走，随机拐、分叉），刻下去 + 发黑；ember > 0 时缝里透一点暗火"""
    im = c._img()
    d = ImageDraw.Draw(im)

    def walk(x, y, a, L, w, lev):
        pts = [(x, y)]
        for _ in range(int(L / step)):
            a += c.rng.normal(0, 0.32)
            x += step * math.cos(a)
            y += step * math.sin(a)
            if not (0 <= x < 1 and 0 <= y < 1) or mask[int(y * W), int(x * W)] < 0.5:
                break
            pts.append((x, y))
            if lev and c.rng.random() < 0.22:
                walk(x, y, a + c.rng.choice([-1, 1]) * c.rng.uniform(0.5, 1.0), L * 0.45, w * 0.6, lev - 1)
        if len(pts) > 1:
            d.line([(px * W, py * W) for px, py in pts], fill=255, width=max(1, int(w * W)))

    walk(x, y, a, L, w, branch)
    cm = c._arr(im, 0.001) * mask
    c.engrave(cm, depth=depth, soft=0.001)
    c.tint(cm, rgb, 0.9)
    if ember:
        c.emit += (_blur(cm, 0.0015) * 1.4).clip(0, 1)[..., None] * np.array([0.6, 0.22, 0.05])[None, None, :] * ember
    return cm


def _wear(c, ham=0.013, scr=60, pat=(56, 52, 44), pa=0.32, scale=0.02, thr=0.55):
    c.hammer(ham)
    c.scratches(scr)
    c.patina(pat, pa, scale=scale, thr=thr)


# ------------------------------------------------------------------ 优雅：半开的银折扇
def _fan_blade(c, ox, oy, a, R, hw_top, hw_stick=0.012, r_flare=0.15, butt=0.035):
    ux, uy = math.cos(a), math.sin(a)
    px, py = -uy, ux
    prof = [(-butt, hw_stick * 0.9), (0.0, hw_stick), (r_flare, hw_stick * 1.15)]
    for k in np.linspace(0, 1, 14)[1:]:
        r = r_flare + (R - hw_top - r_flare) * k
        prof.append((r, hw_stick * 1.15 + (hw_top - hw_stick * 1.15) * math.sin(k * math.pi / 2)))
    left = [(ox + ux * r + px * hw, oy + uy * r + py * hw) for r, hw in prof]
    right = [(ox + ux * r - px * hw, oy + uy * r - py * hw) for r, hw in prof]
    cx, cy = ox + ux * (R - hw_top), oy + uy * (R - hw_top)
    top = [(cx + hw_top * (math.cos(t) * px + math.sin(t) * ux), cy + hw_top * (math.cos(t) * py + math.sin(t) * uy))
           for t in np.linspace(0, math.pi, 24)]
    return c.poly(left + top + right[::-1])


def dr_elegance(out):
    """半开的银质折扇坠：九片扇骨层层叠开、上半镂空，金铆钉，铆钉下垂一簇暗红流苏；顶上挂环"""
    c = Canvas(101)
    ox, oy = 0.5, 0.64
    n, R = 9, 0.35
    a0, a1 = math.radians(-150), math.radians(-30)
    step = (a1 - a0) / (n - 1)
    hw_top = step * R * 0.62
    for i in range(n):
        a = a0 + step * i
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        guard = i in (0, n - 1)
        bl = _fan_blade(c, ox, oy, a, R, hw_top * (0.85 if guard else 1.0), hw_stick=0.015 if guard else 0.011)
        c.add(bl, 'silver', h=0.03 * i, bevel=0.014, dome=0.15)
        if guard:                                              # 两片护骨镶一道金边
            c.add(np.clip(bl - _fan_blade(c, ox, oy, a, R - 0.012, hw_top * 0.85 - 0.012, hw_stick=0.004), 0, 1), 'oldgold', h=0.03 * i + 0.05, bevel=0.006)
        # 扇骨中线一道棱 + 上半一圈刻线
        c.relief(c.stroke([(ox + ux * 0.02, oy + uy * 0.02), (ox + ux * 0.15, oy + uy * 0.15)], w=0.006) * bl, h=0.05)
        # 镂空：一条长孔 + 上下两个圆孔（放在没被下一片盖住的那半边）
        sx, sy = -px * 0.018, -py * 0.018
        holes = _rellipse(c, ox + ux * 0.255 + sx, oy + uy * 0.255 + sy, 0.042, 0.0105, a)
        holes = np.maximum(holes, c.circle(ox + ux * 0.185 + sx * 0.6, oy + uy * 0.185 + sy * 0.6, 0.0075))
        holes = np.maximum(holes, c.circle(ox + ux * 0.318 + sx, oy + uy * 0.318 + sy, 0.0085))
        _cut(c, holes * bl)
    # 铆钉 + 下面的小环、流苏
    c.add(c.circle(ox, oy, 0.03), 'oldgold', h=0.6, bevel=0.014, dome=0.5)
    c.add(c.circle(ox, oy, 0.011), 'oldgold', h=0.85, bevel=0.006, dome=0.4)
    c.add(c.ring(ox, oy + 0.062, 0.014, 0.008), 'oldgold', h=0.45, bevel=0.004)
    red = (112, 30, 24)
    c.cord([(ox, oy + 0.074), (ox + 0.002, oy + 0.1)], rgb=red, w=0.012, h=0.3)
    tas = c.poly([(ox - 0.017, oy + 0.118), (ox + 0.021, oy + 0.118), (ox + 0.046, oy + 0.29), (ox + 0.02, oy + 0.3),
                  (ox - 0.012, oy + 0.297), (ox - 0.036, oy + 0.288)])
    c.add(tas, 'cloth', h=0.2, bevel=0.016, dome=0.3)
    c.tint(tas, red, 0.92)
    for k in range(10):
        u = k / 9
        c.engrave(c.stroke([(ox - 0.014 + 0.032 * u, oy + 0.13), (ox - 0.034 + 0.078 * u + c.rng.normal(0, 0.003), oy + 0.3)], w=0.0035) * tas,
                  depth=0.07, soft=0.0008)
    for k in range(5):                                        # 流苏下沿不齐
        x = ox - 0.03 + 0.017 * k + c.rng.uniform(-0.004, 0.004)
        c.alpha = np.minimum(c.alpha, 1 - c.poly([(x - 0.006, oy + 0.31), (x + 0.006, oy + 0.31), (x, oy + 0.28 + c.rng.uniform(0, 0.012))]))
    cap = c.ellipse(ox + 0.002, oy + 0.112, 0.022, 0.018)
    c.add(cap, 'oldgold', h=0.4, bevel=0.012, dome=0.4)
    c.add(c.stroke([(ox - 0.02, oy + 0.135), (ox + 0.024, oy + 0.135)], w=0.01), 'oldgold', h=0.38, bevel=0.005)
    # 顶上的挂环（接在中间那片扇骨的顶上）
    c.bail(ox, oy - R - 0.042, 'silver', r=0.024, w=0.013, h=0.7, down=0.022)
    _wear(c, 0.012, 60, (52, 52, 48), 0.35, scale=0.012, thr=0.5)
    return c.save(out, chip=0.5, tilt=-7, **DARK)


# ------------------------------------------------------------------ 静心：青灰玉璧
def dr_calm(out):
    """青灰玉璧（中间带孔的圆玉片，满刻谷纹），一根编绳从孔里穿出、顶上打个纽扣结再绕成挂圈"""
    c = Canvas(102)
    cx, cy, R, r = 0.5, 0.6, 0.27, 0.085
    disc = np.clip(c.circle(cx, cy, R) - c.circle(cx, cy, r), 0, 1)
    c.add(disc, 'stone', h=0.0, bevel=0.04, dome=0.1)
    c.relief(np.clip(c.circle(cx, cy, R) - c.circle(cx, cy, R - 0.028), 0, 1) * disc, h=0.07)
    c.relief(np.clip(c.circle(cx, cy, r + 0.026) - c.circle(cx, cy, r), 0, 1) * disc, h=0.07)
    c.engrave(c.ring(cx, cy, R - 0.031, 0.006), depth=0.07)
    c.engrave(c.ring(cx, cy, r + 0.029, 0.006), depth=0.07)
    g = 0.034
    pts = []
    for j in range(-12, 13):
        for i in range(-12, 13):
            x = cx + (i + 0.5 * (j % 2)) * g
            y = cy + j * g * 0.866
            d = math.hypot(x - cx, y - cy)
            if r + 0.048 < d < R - 0.05:
                pts.append((x + c.rng.normal(0, 0.002), y + c.rng.normal(0, 0.002)))
    grains = _dots(c, pts, 0.0105)
    c.relief(grains, h=0.075, soft=0.003)
    c.engrave(_dots(c, [(x + 0.004, y + 0.004) for x, y in pts], 0.004), depth=0.04)
    # 玉色：青灰底 + 深色云絮 + 几块黄褐沁
    _mottle(c, disc, (122, 142, 120), (66, 84, 70), scale=0.025, k=0.95, gloss=0.4, contrast=1.3)
    qin = np.clip((c._noise(0.02) - 0.38) * 3, 0, 1) * disc
    c.color = np.where(qin[..., None] > 0.05, np.array([126, 102, 64], float)[None, None, :], c.color)
    c.custom = np.maximum(c.custom, qin * 0.8)
    c.emit += (_blur(disc, 0.03) * disc)[..., None] * np.array([0.02, 0.035, 0.025])[None, None, :]
    # 编绳：顶上挂圈 → 纽扣结 → 两股往下压过玉璧上沿，钻进孔里
    cord = (98, 74, 42)
    K = (0.5, 0.245)
    loop = [(0.5 + 0.052 * math.cos(t), 0.158 + 0.088 * math.sin(t)) for t in np.linspace(math.radians(112), math.radians(68) + 2 * math.pi, 50)]
    c.cord(loop, rgb=cord, w=0.017, h=0.3)
    for s in (-1, 1):
        sp = _smooth([(K[0] + s * 0.008, K[1] + 0.01), (cx + s * 0.016, cy - R - 0.01), (cx + s * 0.019, cy - r - 0.03), (cx + s * 0.013, cy - r + 0.022)], 8)
        c.cord(sp, rgb=cord, w=0.018, h=0.62)
    c.engrave(c.ellipse(cx, cy - r + 0.024, 0.03, 0.008), depth=0.15)
    knot = c.circle(K[0], K[1], 0.033)
    c.add(knot, 'cloth', h=0.7, bevel=0.018, dome=0.5)
    c.tint(knot, cord, 0.9)
    for a in (0.4, 1.9, 3.4, 4.9):
        c.engrave(c.stroke(Canvas.arc(K[0] + 0.012 * math.cos(a), K[1] + 0.012 * math.sin(a), 0.022, a + 1.2, a + 3.0, 14), w=0.005) * knot, depth=0.08)
    c.hammer(0.006)
    c.scratches(40, depth=0.02)
    return c.save(out, chip=0.4, **DARK)


# ------------------------------------------------------------------ 怒意：一对牛角
def _horn_pts(s, base, c1, c2, tip):
    X = (lambda p: (0.5 + s * (p[0] - 0.5), p[1]))
    return _bez(X(base), X(c1), X(c2), X(tip), 90)


def dr_rage(out):
    """一对公牛角（骨色，尖端发黑），根部用铁箍扎在一起，箍上缠红绳、垂两截绳头；链子从箍上挂起"""
    c = Canvas(103)
    w0 = 0.125
    wf = (lambda u: w0 * (1 - u) ** 0.8 + 0.006)
    for s, jit in ((-1, 0.0), (1, 0.012)):
        pts = _horn_pts(s, (0.47, 0.64), (0.25, 0.74), (0.1 + jit, 0.52), (0.28 + jit, 0.2 + jit))
        hm = _ribbon(c, pts, wf)
        c.add(hm, 'bone', h=0.0, bevel=0.05, dome=0.25)
        fr = _frames(pts)
        for k in range(9):                                   # 年轮
            u = 0.05 + k * 0.042 + c.rng.uniform(-0.006, 0.006)
            i = int(u * (len(pts) - 1))
            (x, y), (tx, ty, nx, ny) = pts[i], fr[i]
            hw = wf(u) / 2 * 1.1
            c.engrave(c.stroke([(x + nx * hw, y + ny * hw), (x + tx * 0.008, y + ty * 0.008), (x - nx * hw, y - ny * hw)], w=0.005) * hm, depth=0.06)
        for off in (-0.25, 0.1, 0.32):                       # 顺着角的细纹
            fib = [(x + nx * wf(i / 89) / 2 * off, y + ny * wf(i / 89) / 2 * off) for i, ((x, y), (tx, ty, nx, ny)) in enumerate(zip(pts, fr)) if 0.35 < i / 89 < 0.92]
            c.engrave(c.stroke(fib, w=0.004) * hm, depth=0.035)
        tip = pts[-1]
        tm = hm * _blur(c.circle(tip[0], tip[1], 0.13), 0.045)
        c.tint(np.clip(tm * 1.2, 0, 1), (34, 28, 24), 1.0)
    # 铁箍
    band = c.poly([(0.43, 0.575), (0.57, 0.575), (0.578, 0.715), (0.422, 0.715)])
    c.add(band, 'iron', h=0.35, bevel=0.02, dome=0.25)
    for y in (0.59, 0.70):
        c.engrave(c.stroke([(0.425, y), (0.575, y)], w=0.005) * band, depth=0.06)
    for x, y in ((0.442, 0.583), (0.558, 0.583), (0.44, 0.707), (0.56, 0.707)):
        c.add(c.circle(x, y, 0.009), 'iron', h=0.55, bevel=0.005, dome=0.3)
    red = (118, 28, 22)
    for k in range(4):
        y = 0.607 + k * 0.023
        c.cord([(0.417, y), (0.5, y + 0.007), (0.583, y + 0.013)], rgb=red, w=0.017, h=0.62)
    for s in (-1, 1):                                        # 两截绳头
        tail = [(0.5 + s * 0.012, 0.715), (0.5 + s * 0.03, 0.77), (0.5 + s * 0.035, 0.84)]
        c.cord(_smooth(tail, 6), rgb=red, w=0.015, h=0.3)
        c.add(c.circle(0.5 + s * 0.035, 0.85, 0.014), 'cloth', h=0.35, bevel=0.007, dome=0.4)
        c.tint(c.circle(0.5 + s * 0.035, 0.85, 0.014), red, 0.9)
    # 链子
    c.chain((0.5, 0.57), (0.5, 0.16), 'iron', link=0.05, w=0.012, h=0.45)
    c.bail(0.5, 0.125, 'iron', r=0.026, w=0.014, h=0.5, down=0.0)
    _wear(c, 0.012, 70, (60, 48, 36), 0.3)
    return c.save(out, chip=0.6, **DARK)


# ------------------------------------------------------------------ 转念：转环里的铜钱
def dr_turn(out):
    """转环坠：铁环上下两根轴销夹着一枚方孔铜钱，铜钱侧转着露出厚边；铁环顶上挂环"""
    c = Canvas(104)
    cx, cy, Rr = 0.5, 0.56, 0.27
    ring = c.ring(cx, cy, Rr, 0.042)
    c.add(ring, 'iron', h=0.0, bevel=0.02, dome=0.15)
    c.engrave(c.ring(cx, cy, Rr, 0.005), depth=0.05)
    for a in np.linspace(0, 2 * math.pi, 28, endpoint=False):     # 环上一圈刻口
        x0, y0 = cx + (Rr - 0.02) * math.cos(a), cy + (Rr - 0.02) * math.sin(a)
        x1, y1 = cx + (Rr + 0.02) * math.cos(a), cy + (Rr + 0.02) * math.sin(a)
        c.engrave(c.stroke([(x0, y0), (x1, y1)], w=0.004) * ring, depth=0.04)
    Rc, k, t = 0.2, 0.5, 0.034
    for s in (-1, 1):                                        # 轴销
        c.add(c.stroke([(cx, cy + s * (Rr - 0.012)), (cx, cy + s * (Rc - 0.01))], w=0.022), 'iron', h=0.2, bevel=0.01)
        c.add(c.ellipse(cx, cy + s * (Rr - 0.034), 0.025, 0.013), 'iron', h=0.32, bevel=0.008, dome=0.3)
    # 铜钱：先画厚边（往右错开），再画正面
    fx = cx - t / 2
    edge = np.zeros((W, W))
    for u in np.linspace(0, 1, 8):
        edge = np.maximum(edge, c.ellipse(fx + t * u, cy, Rc * k, Rc))
    c.add(edge, 'bronze', h=0.25, bevel=0.012)
    c.tint(edge, (82, 58, 36), 0.7)
    for y in np.linspace(cy - Rc * 0.92, cy + Rc * 0.92, 18):
        c.engrave(c.stroke([(fx + t * 0.5, y), (fx + t + Rc * k, y)], w=0.003) * edge, depth=0.04)
    face = c.ellipse(fx, cy, Rc * k, Rc)
    c.add(face, 'bronze', h=0.35, bevel=0.02, dome=0.12)
    c.relief(np.clip(face - c.ellipse(fx, cy, (Rc - 0.024) * k, Rc - 0.024), 0, 1), h=0.08)
    c.engrave(np.clip(c.ellipse(fx, cy, (Rc - 0.022) * k, Rc - 0.022) - c.ellipse(fx, cy, (Rc - 0.03) * k, Rc - 0.03), 0, 1), depth=0.05)
    hs = 0.05

    def sq(x, half):
        return c.poly([(x - half * k, cy - half), (x + half * k, cy - half), (x + half * k, cy + half), (x - half * k, cy + half)])

    c.relief(np.clip(sq(fx, hs + 0.02) - sq(fx, hs), 0, 1), h=0.08)
    for (dx, dy) in ((0, -0.105), (0, 0.105), (-0.105, 0), (0.105, 0)):   # 四个字的位置只放凸块，不写字
        c.relief(_rellipse(c, fx + dx * k, cy + dy, 0.022 * k, 0.022), h=0.06, soft=0.004)
        c.engrave(_rellipse(c, fx + dx * k, cy + dy, 0.009 * k, 0.012), depth=0.05)
    hole = sq(fx, hs)
    see = hole * sq(fx + t, hs)
    c.engrave(hole, depth=0.25)
    c.tint(hole, (48, 34, 22), 0.85)
    _cut(c, see)
    _mottle(c, face, (118, 88, 54), (96, 74, 48), scale=0.02, k=0.4)
    _patch(c, np.maximum(face, edge), (66, 88, 72), 0.6, scale=0.012, thr=0.45)
    c.bail(cx, cy - Rr - 0.046, 'iron', r=0.025, w=0.014, h=0.3, down=0.02)
    _wear(c, 0.012, 60, (60, 50, 40), 0.3)
    return c.save(out, chip=0.5, tilt=4, **DARK)


# ------------------------------------------------------------------ 破势：小战锤
def dr_break(out):
    """小战锤坠：方锤头朝下，锤面上有几道裂纹（缝里一点暗火），短木柄缠皮，柄尾铁环接链子"""
    c = Canvas(105)
    hx = 0.5
    hd = c.stroke([(hx, 0.64), (hx, 0.28)], w=0.052)
    c.add(hd, 'wood', h=0.0, bevel=0.022)
    for k in range(5):
        x = hx - 0.018 + k * 0.009
        c.engrave(c.stroke([(x, 0.29), (x + c.rng.normal(0, 0.003), 0.62)], w=0.0035) * hd, depth=0.04)
    grip = c.stroke([(hx, 0.34), (hx, 0.5)], w=0.058)
    c.add(grip, 'leather', h=0.08, bevel=0.022)
    for y in np.arange(0.335, 0.5, 0.017):
        c.engrave(c.stroke([(hx - 0.032, y), (hx + 0.032, y + 0.013)], w=0.0045) * grip, depth=0.07)
    c.add(c.poly([(hx - 0.036, 0.262), (hx + 0.036, 0.262), (hx + 0.031, 0.292), (hx - 0.031, 0.292)]), 'iron', h=0.2, bevel=0.01)
    c.add(c.ring(hx, 0.228, 0.029, 0.016), 'iron', h=0.25, bevel=0.008)
    # 锤头：中间方块 + 两头略大的锤面箍
    body = c.poly([(0.29, 0.615), (0.71, 0.615), (0.71, 0.835), (0.29, 0.835)])
    c.add(body, 'iron', h=0.2, bevel=0.03, profile='flat')
    for x0, x1 in ((0.235, 0.3), (0.7, 0.765)):
        c.add(c.poly([(x0, 0.598), (x1, 0.598), (x1, 0.852), (x0, 0.852)]), 'iron', h=0.27, bevel=0.022, profile='flat')
    c.engrave(c.ring_mask_edge(c.poly([(0.325, 0.645), (0.675, 0.645), (0.675, 0.805), (0.325, 0.805)]), 0.005), depth=0.07)
    c.relief(c.poly([(0.5, 0.665), (0.555, 0.725), (0.5, 0.785), (0.445, 0.725)]), h=0.09)
    c.add(c.circle(0.5, 0.725, 0.014), 'iron', h=0.6, bevel=0.007, dome=0.4)
    for x in (0.255, 0.745):
        for y in (0.625, 0.825):
            c.add(c.circle(x, y, 0.009), 'iron', h=0.55, bevel=0.005, dome=0.3)
    c.add(c.poly([(hx - 0.045, 0.585), (hx + 0.045, 0.585), (hx + 0.04, 0.625), (hx - 0.04, 0.625)]), 'iron', h=0.4, bevel=0.012)
    head = np.clip(c.poly([(0.235, 0.598), (0.765, 0.598), (0.765, 0.852), (0.235, 0.852)]), 0, 1)
    right = head * c.poly([(0.56, 0), (1, 0), (1, 1), (0.56, 1)])
    _crack(c, 0.762, 0.655, math.pi + 0.3, 0.28, 0.012, right, depth=0.18, ember=0.12)
    _crack(c, 0.762, 0.8, math.pi - 0.3, 0.26, 0.011, right, depth=0.18, ember=0.12)
    _crack(c, 0.762, 0.73, math.pi, 0.2, 0.009, right, depth=0.16, ember=0.08)
    _crack(c, 0.4, 0.85, -math.pi / 2 + 0.3, 0.08, 0.007, head, depth=0.12, ember=0.0)
    c.hammer(0.012)
    _patch(c, head, (70, 50, 36), 0.5, scale=0.01, thr=0.45)
    c.chain((hx, 0.198), (hx, 0.085), 'iron', link=0.045, w=0.011, h=0.3)
    c.bail(hx, 0.062, 'iron', r=0.024, w=0.013, h=0.35, down=0.0)
    _wear(c, 0.016, 80, (62, 48, 36), 0.35)
    return c.save(out, chip=0.8, **DARK)


# ------------------------------------------------------------------ 换气：小铜号角
def dr_second_breath(out):
    """弯角形小铜号角：吹嘴和喇叭口包银，号身两道银箍各带小环，一根皮绳从两环吊起"""
    c = Canvas(106)
    P = _bez((0.2, 0.3), (0.17, 0.76), (0.6, 0.88), (0.8, 0.42), 100)
    fr = _frames(P)
    wf = (lambda u: 0.034 + 0.14 * u ** 1.7)
    body = _ribbon(c, P, wf)
    c.add(body, 'bronze', h=0.0, bevel=0.05, dome=0.25)

    def seg(u0, u1, extra=0.0):
        i0, i1 = int(u0 * 99), int(u1 * 99)
        i1 = min(99, max(i1, i0 + 2))
        return _ribbon(c, P[i0:i1 + 1], lambda v: wf(u0 + (u1 - u0) * v) + extra)

    for u in (0.8, 0.84):                                     # 号身刻线
        c.engrave(seg(u, u + 0.008), depth=0.07)
    for u in np.arange(0.42, 0.62, 0.02):
        i = int(u * 99)
        (x, y), (tx, ty, nx, ny) = P[i], fr[i]
        hw = wf(u) / 2 * 0.8
        c.engrave(c.stroke([(x + nx * hw, y + ny * hw), (x - nx * hw + tx * 0.012, y - ny * hw + ty * 0.012)], w=0.004), depth=0.05)
    c.add(seg(0.0, 0.07, 0.008), 'silver', h=0.3, bevel=0.012, dome=0.2)
    c.add(c.circle(P[0][0], P[0][1], 0.019), 'silver', h=0.35, bevel=0.01, dome=0.3)
    loops = []
    for u in (0.27, 0.72):
        c.add(seg(u - 0.02, u + 0.02, 0.012), 'silver', h=0.35, bevel=0.01, dome=0.2)
        i = int(u * 99)
        (x, y), (tx, ty, nx, ny) = P[i], fr[i]
        if ny > 0:
            nx, ny = -nx, -ny
        off = wf(u) / 2 + 0.016
        lx, ly = x + nx * off, y + ny * off
        c.add(c.ring(lx, ly, 0.014, 0.008), 'silver', h=0.4, bevel=0.004)
        loops.append((lx + nx * 0.012, ly + ny * 0.012))
    # 喇叭口：一圈银口沿，里面黑
    (x, y), (tx, ty, nx, ny) = P[-1], fr[-1]
    ang = math.atan2(ty, tx)
    mouth = _rellipse(c, x, y, 0.034, wf(1) / 2 + 0.006, ang)
    c.add(mouth, 'bronze', h=0.4, bevel=0.01)
    inner = _rellipse(c, x + tx * 0.004, y + ty * 0.004, 0.024, wf(1) / 2 - 0.008, ang)
    c.engrave(inner, depth=0.3, soft=0.006)
    c.tint(inner, (16, 12, 10), 0.95)
    c.add(c.oring(x, y, 0.03, wf(1) / 2 + 0.002, 0.016, ang), 'silver', h=0.5, bevel=0.007)
    c.add(seg(0.93, 0.965, 0.01), 'silver', h=0.32, bevel=0.01, dome=0.2)
    # 皮绳
    leather = (82, 58, 40)
    top = (0.49, 0.2)
    left = _bez(loops[0], (loops[0][0] + 0.02, loops[0][1] - 0.15), (top[0] - 0.07, top[1] + 0.03), top, 30)
    right = _bez(top, (top[0] + 0.07, top[1] + 0.03), (loops[1][0] - 0.01, loops[1][1] - 0.15), loops[1], 30)
    c.cord(left + right[1:], rgb=leather, w=0.017, h=0.6)
    c.add(c.circle(top[0], top[1] + 0.004, 0.02), 'leather', h=0.68, bevel=0.01, dome=0.4)
    _patch(c, body, (62, 80, 66), 0.45, scale=0.012, thr=0.5)
    _wear(c, 0.013, 60, (50, 42, 34), 0.25)
    return c.save(out, chip=0.5, **DARK)


# ------------------------------------------------------------------ 心流：银镶边螺旋海螺壳
def dr_flow(out):
    """螺旋贝壳（鹦鹉螺式的对数螺线，螺圈一道道鼓起，壳面褐色火焰纹），外沿一圈银镶边，壳口包银、嵌一颗小珍珠；顶上挂环"""
    c = Canvas(107)
    ox, oy = 0.5, 0.56
    R = 0.3
    b = math.log(2.6) / (2 * math.pi)
    te = 0.5

    def rr(t):
        return R * math.exp(b * (t - te))

    def P(t, k=1.0):
        return ox + rr(t) * k * math.cos(t), oy + rr(t) * k * math.sin(t)

    ts = np.linspace(te - 2 * math.pi, te, 240)
    outline = []
    for t in ts:
        flare = 1 + 0.06 * max(0.0, (t - (te - 0.9)) / 0.9) ** 2      # 壳口外翻一点
        outline.append(P(t, flare))
    A, B = P(te - 2 * math.pi), outline[-1]
    gx, gy = -math.sin(te), math.cos(te)                     # 壳口朝的方向（螺线生长方向）
    lip = [(B[0] + (A[0] - B[0]) * u + gx * 0.035 * math.sin(math.pi * u), B[1] + (A[1] - B[1]) * u + gy * 0.035 * math.sin(math.pi * u))
           for u in np.linspace(0, 1, 24)]
    shell = c.poly(outline + lip[1:-1])
    c.add(shell, 'bone', h=0.0, bevel=0.035, dome=0.25)
    yy, xx = np.mgrid[0:W, 0:W] / W
    rho = np.hypot(xx - ox, yy - oy) + 1e-6
    phi = np.arctan2(yy - oy, xx - ox)
    tt = (np.log(rho / R) / b + te - phi) / (2 * math.pi)
    fr = tt - np.floor(tt)
    inside = shell * (rho > 0.012)
    tube = np.sin(np.pi * fr) ** 0.6 * np.clip(rho / R, 0, 1) ** 0.5
    c.h += 0.6 * tube * inside
    suture = np.clip(1 - np.minimum(fr, 1 - fr) / 0.05, 0, 1) * inside
    c.engrave(suture, depth=0.12, soft=0.0012)
    ribs = np.cos(26 * phi + 5 * fr)
    c.h += 0.012 * ribs * inside * np.clip(rho / 0.08, 0, 1)
    stripes = np.clip((np.sin(13 * phi + 7 * fr + 2.0 * c._noise(0.02)) - 0.45) * 3, 0, 1) * (fr > 0.42) * np.clip((rho - 0.09) / 0.06, 0, 1) * inside
    c.tint(_blur(stripes, 0.002), (92, 64, 44), 0.6)
    c.engrave(c.circle(ox, oy, 0.012), depth=0.15)
    # 银镶边：外沿一圈 + 壳口一道
    edge = c.ring_mask_edge(shell, 0.014)
    c.add(_blur(edge, 0.001), 'silver', h=0.32, bevel=0.007)
    c.add(c.stroke(lip[1:-1], w=0.024), 'silver', h=0.4, bevel=0.01, dome=0.2)
    c.engrave(c.stroke(lip[3:-3], w=0.004), depth=0.05)
    # 珍珠（骨底 + 柔光，不要像金属扣）：直接卡在壳口里，三个小爪
    mx, my = lip[len(lip) // 2]
    mx, my = mx - gx * 0.022, my - gy * 0.022
    for a in (math.atan2(gy, gx) + d for d in (0.0, 2.1, -2.1)):
        c.add(c.circle(mx + 0.035 * math.cos(a), my + 0.035 * math.sin(a), 0.009), 'silver', h=0.55, bevel=0.005, dome=0.3)
    pm = c.circle(mx, my, 0.036)
    c.add(pm, 'bone', h=0.75, bevel=0.036, dome=0.5)
    c.tint(pm, (190, 180, 168), 1.0, gloss=0.15)
    c.emit += (pm * 0.6 + _blur(c.circle(mx - 0.012, my - 0.012, 0.012), 0.008) * pm * 1.2)[..., None] * np.array([0.13, 0.12, 0.12])[None, None, :]
    c.emit += (_blur(c.circle(mx + 0.014, my + 0.014, 0.014), 0.008) * pm)[..., None] * np.array([0.08, 0.04, 0.05])[None, None, :]
    # 挂环：壳顶最高处
    ys, xs = np.nonzero(shell > 0.5)
    i = np.argmin(ys)
    bx, by = xs[i] / W, ys[i] / W
    c.bail(bx, by - 0.035, 'silver', r=0.024, w=0.013, h=0.5, down=0.016)
    _wear(c, 0.008, 50, (60, 54, 44), 0.25)
    return c.save(out, chip=0.4, tilt=-10, **DARK)


# ------------------------------------------------------------------ 霸王：青铜狮首衔环
def dr_overlord(out):
    """青铜狮首（铺首衔环的样子）：一圈鬃毛、皱眉、一对琥珀小眼，额上一顶小金冠，口衔一个环；冠顶接链子"""
    c = Canvas(108)
    cx, cy = 0.5, 0.51
    # 鬃毛：一圈火苗状的卷毛，两边都往下卷（左右对称）
    mane = c.circle(cx, cy, 0.19)
    tufts = []
    N = 15
    for i in range(N):
        a = (i + 0.5) / N * 2 * math.pi + c.rng.uniform(-0.06, 0.06)
        sw = 0.5 * (1 if math.cos(a) >= 0 else -1)
        r0, r1 = 0.12, 0.275 + c.rng.uniform(-0.012, 0.008)
        pts = [(cx + r * math.cos(a + sw * ((r - r0) / (r1 - r0)) ** 1.6), cy + r * math.sin(a + sw * ((r - r0) / (r1 - r0)) ** 1.6))
               for r in np.linspace(r0, r1, 22)]
        tufts.append(pts)
        mane = np.maximum(mane, _ribbon(c, pts, lambda u: 0.088 * (1 - u) ** 0.75 + 0.004))
    c.add(mane, 'bronze', h=0.05, bevel=0.035, dome=0.35)
    for pts in tufts:
        fr = _frames(pts)
        for off in (-0.3, 0.05, 0.38):
            ln = [(x + nx * 0.088 * (1 - k / 21) ** 0.75 / 2 * off, y + ny * 0.088 * (1 - k / 21) ** 0.75 / 2 * off)
                  for k, ((x, y), (tx, ty, nx, ny)) in enumerate(zip(pts, fr)) if 0.25 < k / 21 < 0.85]
            c.engrave(c.stroke(ln, w=0.005, wfn=lambda u: 1 - 0.5 * u) * mane, depth=0.08)
    for s in (-1, 1):                                           # 耳朵
        c.add(c.circle(cx + s * 0.112, 0.38, 0.036), 'bronze', h=0.3, bevel=0.016, dome=0.3)
        c.engrave(c.ellipse(cx + s * 0.112, 0.385, 0.017, 0.02), depth=0.12)
    face = np.maximum(c.ellipse(cx, 0.5, 0.136, 0.13), c.ellipse(cx, 0.59, 0.112, 0.08))
    c.add(face, 'bronze', h=0.35, bevel=0.05, dome=0.45)
    for k in range(3):                                          # 额头皱纹
        c.engrave(c.stroke(Canvas.arc(cx, 0.46 - 0.018 * k, 0.05 - 0.008 * k, math.radians(-150), math.radians(-30), 16), w=0.005), depth=0.06)
    for s in (-1, 1):                                           # 眉骨 + 上挑的眼
        brow = c.stroke([(cx + s * 0.022, 0.462), (cx + s * 0.065, 0.442), (cx + s * 0.108, 0.425)], w=0.024, wfn=lambda u: 1 - 0.45 * u)
        c.relief(brow, h=0.11)
        eye = _rellipse(c, cx + s * 0.06, 0.475, 0.03, 0.0125, -s * 0.32)
        c.engrave(eye, depth=0.14)
        c.tint(eye, (28, 20, 14), 0.9)
        c.gem(c.circle(cx + s * 0.058, 0.476, 0.0085), (176, 112, 30))
        c.engrave(c.stroke([(cx + s * 0.1, 0.51), (cx + s * 0.112, 0.55), (cx + s * 0.108, 0.59)], w=0.005), depth=0.06)
    bridge = c.poly([(cx - 0.024, 0.445), (cx + 0.024, 0.445), (cx + 0.036, 0.54), (cx - 0.036, 0.54)])
    c.relief(bridge, h=0.1, soft=0.008)
    pad = c.poly([(cx - 0.052, 0.532), (cx + 0.052, 0.532), (cx + 0.012, 0.582), (cx - 0.012, 0.582)])
    c.relief(pad, h=0.08, soft=0.004)
    c.tint(pad, (44, 32, 24), 0.55)
    for s in (-1, 1):
        c.engrave(_rellipse(c, cx + s * 0.03, 0.552, 0.012, 0.007, s * 0.5), depth=0.1)
        c.relief(c.circle(cx + s * 0.046, 0.614, 0.046), h=0.08, soft=0.006)
        c.engrave(_dots(c, [(cx + s * (0.026 + 0.015 * j), 0.6 + 0.014 * r_) for j in range(3) for r_ in range(2)], 0.0045), depth=0.05)
    c.engrave(c.stroke([(cx, 0.58), (cx, 0.62), (cx - 0.03, 0.645)], w=0.005), depth=0.07)
    c.engrave(c.stroke([(cx, 0.62), (cx + 0.03, 0.645)], w=0.005), depth=0.07)
    mouth = _rellipse(c, cx, 0.672, 0.066, 0.022)
    c.engrave(mouth, depth=0.2)
    c.tint(mouth, (20, 14, 10), 0.95)
    for s in (-1, 1):
        fang = c.poly([(cx + s * 0.05, 0.656), (cx + s * 0.033, 0.656), (cx + s * 0.043, 0.694)])
        c.add(fang, 'bone', h=0.6, bevel=0.005)
    # 环：从嘴里穿出来，挡在下巴前面
    ring = c.ring(cx, 0.778, 0.105, 0.03)
    ring = ring * (c.poly([(0, 0.675), (1, 0.675), (1, 1), (0, 1)]))
    c.add(ring, 'oldgold', h=0.7, bevel=0.014, dome=0.2)
    c.engrave(c.ring(cx, 0.778, 0.105, 0.004) * ring, depth=0.04)
    # 小王冠（压在额顶的鬃毛上）
    crown = c.poly([(cx - 0.07, 0.36), (cx + 0.07, 0.36), (cx + 0.062, 0.32), (cx - 0.062, 0.32)])
    for x, top in ((cx - 0.055, 0.262), (cx, 0.232), (cx + 0.055, 0.262)):
        crown = np.maximum(crown, c.poly([(x - 0.022, 0.325), (x + 0.022, 0.325), (x, top)]))
    c.add(crown, 'oldgold', h=0.75, bevel=0.012, dome=0.2)
    c.add(_dots(c, [(cx - 0.055, 0.262), (cx, 0.232), (cx + 0.055, 0.262)], 0.012), 'oldgold', h=0.9, bevel=0.007, dome=0.4)
    c.engrave(c.stroke([(cx - 0.066, 0.332), (cx + 0.066, 0.332)], w=0.004), depth=0.05)
    c.gem(c.ellipse(cx, 0.343, 0.013, 0.011), (130, 24, 20))
    c.chain((cx, 0.22), (cx, 0.11), 'iron', link=0.045, w=0.011, h=0.8)
    c.bail(cx, 0.085, 'iron', r=0.024, w=0.013, h=0.85, down=0.0)
    _patch(c, np.maximum(mane, face), (66, 86, 72), 0.55, scale=0.012, thr=0.48)
    _wear(c, 0.012, 60, (52, 46, 38), 0.25)
    return c.save(out, chip=0.5, **DARK)


# ------------------------------------------------------------------ 乘势：铜铸卷浪
def _spline(pts, k=10):
    """Catmull-Rom：过每个控制点的平滑曲线"""
    P = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, k, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(tuple(pts[-1]))
    return out


def _crest(c, ox, oy, s):
    """一道往左卷的浪头：(ox, oy) 是浪底，s 是大小。浪背从右下斜着往上，到顶上往左卷成一圈螺旋（约一圈，越卷越细），
    中间留一个浪眼。返回 (中心线, 粗细函数, 遮罩, 浪眼中心)"""
    back = _spline([(0.46, 0.0), (0.41, -0.3), (0.3, -0.62), (0.16, -0.84)], 8)
    ex, ey = -0.05, -0.62
    a0 = math.atan2(back[-1][1] - ey, back[-1][0] - ex)
    r0 = math.hypot(back[-1][0] - ex, back[-1][1] - ey)
    sp = [(ex + r0 * (1 - 0.68 * t) * math.cos(a0 - t * 2 * math.pi * 1.05), ey + r0 * (1 - 0.68 * t) * math.sin(a0 - t * 2 * math.pi * 1.05))
          for t in np.linspace(0, 1, 56)[1:]]
    loc = back + sp
    n = len(loc)
    ub = (len(back) - 1) / (n - 1)

    def wfn(u):
        if u <= ub:
            return s * (0.33 - 0.09 * u / ub)
        v = (u - ub) / (1 - ub)
        return s * (0.24 * (1 - v) ** 0.9 + 0.028)

    pts = [(ox + x * s, oy + y * s) for x, y in loc]
    return pts, wfn, _ribbon(c, pts, wfn), (ox + ex * s, oy + ey * s)


def dr_momentum(out):
    """铜铸卷浪坠：三道浪头从左到右由小到大，最大的一道在右上卷成一圈，浪眼里嵌一颗小琥珀；浪下一条刻着鱼鳞水纹的底座，凹处铜绿；顶上挂环"""
    c = Canvas(109)
    base = c.poly(_spline([(0.11, 0.75), (0.14, 0.71), (0.5, 0.69), (0.87, 0.71), (0.9, 0.76), (0.84, 0.81), (0.5, 0.83), (0.17, 0.81), (0.11, 0.75)], 8))
    c.add(base, 'bronze', h=0.0, bevel=0.03, dome=0.2)
    for row, (y0, r) in enumerate(((0.745, 0.026), (0.785, 0.026))):     # 底座上两排鱼鳞水纹（青海波）
        for k in range(16):
            x = 0.1 + k * 0.052 + (0.026 if row else 0.0)
            arcs = c.stroke(Canvas.arc(x, y0 + r, r, math.pi * 1.05, math.pi * 1.95, 14), w=0.0045)
            c.engrave(arcs * base, depth=0.07, soft=0.0008)
    crests = []
    for ox, oy, s, h0 in ((0.2, 0.745, 0.18, 0.08), (0.375, 0.745, 0.3, 0.16), (0.575, 0.75, 0.54, 0.26)):
        pts, wfn, m, eye = _crest(c, ox, oy, s)
        c.add(m, 'bronze', h=h0, bevel=0.018 + 0.03 * s, dome=0.3)
        fr = _frames(pts)
        n = len(pts)
        for off in (-0.45, 0.0, 0.42):                                 # 顺着浪身、绕着浪眼的水纹
            ln = [(x + nx * wfn(i / (n - 1)) / 2 * off, y + ny * wfn(i / (n - 1)) / 2 * off)
                  for i, ((x, y), (tx, ty, nx, ny)) in enumerate(zip(pts, fr)) if 0.04 < i / (n - 1) < 0.8 - 0.1 * (off < -0.3)]
            if len(ln) > 2:
                c.engrave(c.stroke(ln, w=0.004 + 0.004 * s, wfn=lambda u: 1 - 0.5 * u) * m, depth=0.08)
        crests.append((pts, wfn, m, s, h0, eye))
    pts, wfn, m, s, h0, eye = crests[-1]
    # 浪眼里嵌的琥珀
    ax, ay = eye
    c.add(c.circle(ax, ay, 0.033), 'oldgold', h=0.7, bevel=0.01, dome=0.2)
    c.gem(c.circle(ax, ay, 0.023), (172, 100, 24))
    # 挂环：大浪最高处
    ys, xs = np.nonzero(m > 0.5)
    j = np.argmin(ys)
    c.bail(xs[j] / W, ys[j] / W - 0.036, 'oldgold', r=0.025, w=0.014, h=0.6, down=0.018)
    c.hammer(0.013)
    c.scratches(60)
    c.patina((70, 104, 88), 0.9, scale=0.012, thr=0.42)                  # 凹处、水纹里的铜绿
    return c.save(out, chip=0.6, tilt=-4, **DARK)


# ------------------------------------------------------------------ 鸡尾酒：三只捆在一起的小药瓶
def _place(pts, bx, by, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    return [(bx + x * ca - y * sa, by + x * sa + y * ca) for x, y in pts]


def _vial_outline(kind):
    """瓶身轮廓（本地坐标：瓶底中心为原点，往上是负 y），返回 (轮廓点, 瓶口高度, 瓶颈半宽, 瓶身最宽半宽)"""
    nw = 0.024
    if kind == 'round':                                                 # 圆肚
        r, cyb = 0.096, -0.096
        jy = cyb - math.sqrt(r * r - nw * nw)
        a0 = math.atan2(jy - cyb, -nw)
        a1 = math.atan2(jy - cyb, nw) - 2 * math.pi
        arc = [(r * math.cos(a), cyb + r * math.sin(a)) for a in np.linspace(a0, a1, 60)]
        top = -0.35
        return [(-nw, top)] + arc + [(nw, top)], top, nw, r
    if kind == 'tall':                                                  # 细高
        hw, top = 0.04, -0.53
        bot = [(hw * math.cos(a), -hw + hw * math.sin(a)) for a in np.linspace(math.pi, 0, 20)]
        return [(-nw, top), (-nw, -0.41), (-hw, -0.375)] + bot + [(hw, -0.375), (nw, -0.41), (nw, top)], top, nw, hw
    top = -0.255                                                        # 矮胖
    half = [(-nw, -0.155), (-0.058, -0.14), (-0.088, -0.115), (-0.1, -0.075), (-0.098, -0.032), (-0.084, -0.008), (-0.058, 0.0)]
    half = [(x * 0.92 if abs(x) > nw else x, y) for x, y in half]
    pts = _spline(half + [(-x, y) for x, y in half[::-1]], 6)
    return [(-nw, top)] + pts + [(nw, top)], top, nw, 0.092


def dr_cocktail(out):
    """三只不同形状的小玻璃瓶（圆肚 / 细高 / 矮胖），瓶颈用几圈铁丝捆在一起，各装一种暗色药水（琥珀 / 浑绿 / 暗紫），软木塞；绳子吊起"""
    from scipy import ndimage
    c = Canvas(110)
    yy, xx = np.mgrid[0:W, 0:W] / W
    band_y = 0.44
    # （形状, 瓶颈中心 x, 捆扎点在瓶颈上的本地高度, 倾斜, 药水颜色, 液面 y, 底高）
    vials = [('tall', 0.5, -0.45, 0.0, (70, 86, 58), 0.6, 0.0),
             ('round', 0.428, -0.3, 0.42, (124, 92, 44), 0.6, 0.1),
             ('squat', 0.572, -0.215, -0.42, (82, 62, 98), 0.58, 0.18)]
    glass_all = np.zeros((W, W))
    corks = []
    for kind, nx_, ly, ang, col, level, h0 in vials:
        outline, top, nw, hw = _vial_outline(kind)
        bx = nx_ - (-ly) * math.sin(ang)
        by = band_y + (-ly) * math.cos(ang)
        g = c.poly(_place(outline, bx, by, ang))
        c.emit *= (1 - g)[..., None]                                    # 前面的瓶子挡住后面瓶里的微光
        c.add(g, 'glass', h=h0, bevel=0.03, dome=0.5)
        c.tint(g, (84, 100, 108), 0.6, gloss=0.8)
        inner = (ndimage.distance_transform_edt(g > 0.5) / W > 0.011).astype(float)
        inner = _blur(inner, 0.0012)
        c.tint(inner, (42, 50, 54), 0.9, gloss=1.0)
        liq = inner * np.clip((yy - level) / 0.003, 0, 1)
        c.tint(liq, col, 0.95, gloss=0.7)
        cl = np.clip(c._noise(0.012) * 1.2 + 0.5, 0, 1)                # 药水里浑浊的深浅
        c.color = np.where(liq[..., None] > 0.5, c.color * (0.75 + 0.35 * cl)[..., None], c.color)
        c.emit += _blur(liq, 0.012)[..., None] * (np.array(col, float) / 255.0)[None, None, :] * 0.05
        c.emit += (inner * np.clip(1 - np.abs(yy - level) / 0.0035, 0, 1))[..., None] * (np.array(col, float) / 255.0 * 0.5 + 0.08)[None, None, :] * 0.18
        hl = c.stroke(_place([(-hw * 0.55, -0.03 - hw * 0.4), (-hw * 0.62, top * 0.55)], bx, by, ang), w=0.007, wfn=lambda u: math.sin(math.pi * u) ** 0.5)
        c.emit += _blur(hl * inner, 0.003)[..., None] * np.array([0.2, 0.21, 0.22])[None, None, :]
        lip = _rellipse(c, *_place([(0, top)], bx, by, ang)[0], nw + 0.01, 0.009, ang)
        c.add(lip, 'glass', h=h0 + 0.3, bevel=0.006)
        c.tint(lip, (84, 98, 104), 0.6, gloss=0.8)
        glass_all = np.maximum(glass_all, g)
        corks.append((bx, by, ang, top, nw, h0))
    smudge = np.clip((c._noise(0.012) - 0.2) * 2.5, 0, 1) * glass_all   # 瓶身污渍
    c.color = c.color * (1 - 0.4 * smudge)[..., None]
    c.gloss = c.gloss * (1 - 0.6 * smudge)
    # 软木塞（后面两只先画，中间那只最后）
    for bx, by, ang, top, nw, h0 in corks:
        ck = c.poly(_place([(-nw * 0.9, top + 0.004), (nw * 0.9, top + 0.004), (nw * 1.05, top - 0.05), (-nw * 1.05, top - 0.05)], bx, by, ang))
        c.add(ck, 'wood', h=h0 + 0.45, bevel=0.01, dome=0.3)
        cap = _rellipse(c, *_place([(0, top - 0.05)], bx, by, ang)[0], nw * 1.05, 0.008, ang)
        c.add(cap, 'wood', h=h0 + 0.55, bevel=0.006)
        _mottle(c, np.maximum(ck, cap), (124, 96, 62), (88, 66, 42), scale=0.006, k=0.9)
        c.engrave(_dots(c, _place([(c.rng.uniform(-nw * 0.8, nw * 0.8), c.rng.uniform(top - 0.045, top - 0.005)) for _ in range(5)], bx, by, ang), 0.0035) * ck, depth=0.06)
    # 铁丝：在三根瓶颈上缠几圈，右边留个拧起来的头
    for k in range(4):
        y = band_y - 0.017 + k * 0.011
        c.add(c.stroke([(0.392, y - 0.002), (0.5, y + 0.002), (0.608, y + 0.004)], w=0.009), 'iron', h=1.0, bevel=0.0045)
    c.add(c.stroke([(0.606, band_y + 0.02), (0.622, band_y + 0.03), (0.628, band_y + 0.048), (0.616, band_y + 0.058)], w=0.008), 'iron', h=1.0, bevel=0.004)
    # 绳：从铁丝两头往上，在瓶塞上方打结，再绕成挂圈
    rope = (66, 60, 52)
    K = (0.5, 0.25)
    for s in (-1, 1):
        c.cord(_spline([(0.5 + s * 0.104, band_y + 0.002), (0.5 + s * 0.11, 0.37), (0.5 + s * 0.065, 0.285), (K[0] + s * 0.008, K[1] + 0.008)], 8), rgb=rope, w=0.015, h=1.05)
    loop = [(0.5 + 0.045 * math.cos(t), 0.165 + 0.08 * math.sin(t)) for t in np.linspace(math.radians(108), math.radians(72) + 2 * math.pi, 50)]
    c.cord(loop, rgb=rope, w=0.015, h=0.9)
    knot = c.circle(K[0], K[1], 0.022)
    c.add(knot, 'cloth', h=1.2, bevel=0.012, dome=0.5)
    c.tint(knot, rope, 0.9)
    c.engrave(c.stroke([(K[0] - 0.018, K[1] - 0.006), (K[0] + 0.018, K[1] + 0.008)], w=0.005) * knot, depth=0.06)
    c.hammer(0.006)
    c.scratches(40, depth=0.02)
    return c.save(out, chip=0.3, **DARK)


# ------------------------------------------------------------------ 拾遗：马蹄形磁石
def dr_magnet(out):
    """马蹄形黑铁磁石，两端包银，银端上吸着几根铁屑；弯顶接链子"""
    c = Canvas(111)
    cx, cy, Ra, bw = 0.5, 0.47, 0.185, 0.115
    legL = [(cx - Ra, cy + t) for t in np.linspace(0.27, 0.0, 12)]
    arc = [(cx + Ra * math.cos(a), cy + Ra * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 60)[1:-1]]
    legR = [(cx + Ra, cy + t) for t in np.linspace(0.0, 0.27, 12)]
    pts = legL + arc + legR
    body = _ribbon(c, pts, lambda u: bw)
    c.add(body, 'iron', h=0.0, bevel=0.035, dome=0.15)
    _mottle(c, body, (62, 58, 56), (78, 74, 70), scale=0.03, k=0.55)
    mid = _ribbon(c, pts, lambda u: 0.008)
    c.engrave(mid, depth=0.06)
    for off in (0.4, -0.4):
        fr = _frames(pts)
        side = [(x + nx * bw / 2 * off, y + ny * bw / 2 * off) for (x, y), (tx, ty, nx, ny) in zip(pts, fr)]
        c.engrave(c.stroke(side, w=0.004), depth=0.04)
    yb = cy + 0.27
    for s in (-1, 1):
        x = cx + s * Ra
        cap = c.poly([(x - bw / 2, yb - 0.075), (x + bw / 2, yb - 0.075), (x + bw / 2, yb), (x - bw / 2, yb)])
        c.add(cap, 'silver', h=0.3, bevel=0.016, dome=0.15)
        c.engrave(c.stroke([(x - bw / 2, yb - 0.072), (x + bw / 2, yb - 0.072)], w=0.006), depth=0.08)
        if s > 0:                                            # 右端吸着一根铁钉（钉帽贴在银端上）
            nx0, ny0 = x + 0.02, yb + 0.006
            a = math.pi / 2 + 0.5
            L = 0.1
            nx1, ny1 = nx0 + L * math.cos(a), ny0 + L * math.sin(a)
            c.add(c.stroke([(nx0, ny0), (nx1, ny1)], w=0.02, wfn=lambda u: 1 - 0.8 * u ** 2.5), 'iron', h=0.25, bevel=0.008)
            c.add(_rellipse(c, nx0, ny0 + 0.003, 0.03, 0.011, a - math.pi / 2), 'iron', h=0.35, bevel=0.006)
            for k in range(3):
                u = 0.2 + 0.1 * k
                c.engrave(c.stroke([(nx0 + (nx1 - nx0) * u - 0.008, ny0 + (ny1 - ny0) * u), (nx0 + (nx1 - nx0) * u + 0.008, ny0 + (ny1 - ny0) * u + 0.004)], w=0.003), depth=0.04)
        else:                                                # 左端一小撮铁屑
            for j in range(4):
                fx = x - bw * 0.3 + j * bw * 0.2 + c.rng.uniform(-0.004, 0.004)
                L = c.rng.uniform(0.014, 0.024)
                fa = math.pi / 2 + c.rng.normal(0, 0.35)
                c.add(c.stroke([(fx, yb), (fx + L * math.cos(fa), yb + L * math.sin(fa))], w=0.008, wfn=lambda u: 1 - 0.5 * u), 'iron', h=0.2, bevel=0.004)
    # 弯顶一道铁箍，链子接在箍上
    collar = c.poly([(cx - 0.03, cy - Ra - bw / 2 - 0.01), (cx + 0.03, cy - Ra - bw / 2 - 0.01), (cx + 0.03, cy - Ra + bw / 2 + 0.01), (cx - 0.03, cy - Ra + bw / 2 + 0.01)])
    c.add(collar, 'iron', h=0.4, bevel=0.012, dome=0.3)
    c.add(c.circle(cx, cy - Ra, 0.012), 'iron', h=0.65, bevel=0.006, dome=0.4)
    c.add(c.ring(cx, cy - Ra - bw / 2 - 0.024, 0.015, 0.01), 'iron', h=0.45, bevel=0.005)
    _patch(c, body, (88, 54, 36), 0.5, scale=0.012, thr=0.48)
    c.chain((cx, cy - Ra - bw / 2 - 0.038), (cx, 0.12), 'iron', link=0.045, w=0.011, h=0.4)
    c.bail(cx, 0.094, 'silver', r=0.024, w=0.013, h=0.45, down=0.0)
    _wear(c, 0.014, 70, (66, 46, 34), 0.35)
    return c.save(out, chip=0.7, tilt=-4, **DARK)


# ------------------------------------------------------------------
def main():
    os.makedirs(OUT, exist_ok=True)
    want = [a for a in sys.argv[1:] if a in KEYS] or KEYS
    for k in want:
        globals()[k](os.path.join(OUT, 'charm_' + k + '.png'))
        print('画好', k)
    sheet = Image.new('RGBA', (160 * len(KEYS), 160), (40, 36, 30, 255))
    for i, k in enumerate(KEYS):
        p = os.path.join(OUT, 'charm_' + k + '.png')
        if os.path.exists(p):
            sheet.alpha_composite(Image.open(p).convert('RGBA'), (i * 160, 0))
    sheet.save(os.path.join(OUT, 'sheet_stance.png'))
    sheet.resize((sheet.width * 2, 320), Image.LANCZOS).save(os.path.join(OUT, 'sheet_stance_x2.png'))


if __name__ == '__main__':
    main()
