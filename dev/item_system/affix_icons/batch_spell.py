# -*- coding: utf-8 -*-
"""第 6 批：法术 / 重击处决（设计清单.md「第 6 批」）。画法照 icons_charm.py（护符 / 饰品，压暗做旧，发光克制）。
挂法轮流用：挂环 = 血涌 / 迸发 / 破绽 / 处刑；链 = 星群 / 寸劲 / 余裕 / 千钧；绳 = 血契 / 涌流 / 盈满 / 碎骨。
用法：python batch_spell.py [键 ...]（不给键 = 全画）；出 out/charm_<键>.png + out/sheet_spell.png + out/sheet_spell_x2.png"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import Canvas, W, _blur  # noqa: E402
from icons_charm import DARK  # noqa: E402
from icons_obj import _unit  # noqa: E402

OUT = os.path.join(HERE, 'out')
YY, XX = np.mgrid[0:W, 0:W] / W

KEYS = ['dr_blood_pact', 'dr_blood_surge', 'dr_orb_flow', 'dr_orb_burst', 'dr_orb_swarm', 'dr_hawk',
        'dr_steady', 'dr_crack', 'dr_opening', 'dr_execute', 'dr_composure', 'dr_thousand']


# ------------------------------------------------------------------ 小工具
def _spline(pts, n=8, closed=False):
    """Catmull-Rom 平滑折线"""
    P = list(pts)
    P = ([P[-1]] + P + [P[0], P[1]]) if closed else ([P[0]] + P + [P[-1]])
    res = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            res.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    if not closed:
        res.append(P[-2])
    return res


def _rrect(x0, y0, x1, y1, r, n=8):
    """圆角矩形的点"""
    pts = []
    for (cx, cy, a0) in ((x1 - r, y0 + r, -math.pi / 2), (x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, math.pi / 2), (x0 + r, y0 + r, math.pi)):
        for a in np.linspace(a0, a0 + math.pi / 2, n):
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _shift(m, dx, dy):
    return np.clip(ndimage.shift(m, (dy * W, dx * W), order=1), 0, 1)


def _union(*ms):
    m = ms[0]
    for k in ms[1:]:
        m = np.maximum(m, k)
    return m


def _add(c, mask, mat, **kw):
    """c.add + 清掉遮罩里之前的 tint / 光泽 / 自发光（盖在染过色的东西上面时用，不然会继承下面的颜色）"""
    c.add(mask, mat, **kw)
    m = mask > 0.5
    c.custom[m] = 0.0
    c.gloss[m] = 0.0
    c.emit[m] = 0.0
    return c


def _bead(c, x, y, r, rgb, h=0.2, emit=0.3, gloss=0.7, dome=0.8):
    """一颗小圆珠（辉石珠等）：圆顶 + 自定义色 + 左上一点透光"""
    m = c.circle(x, y, r)
    c.add(m, 'silver', h=h, bevel=r, dome=dome)
    c.tint(m, rgb, 1.0, gloss=gloss)
    d = np.sqrt((XX - x + r * 0.3) ** 2 + (YY - y + r * 0.3) ** 2) / r
    core = np.clip(1 - d, 0, 1) ** 2 * m
    c.emit += core[..., None] * np.array(rgb, float)[None, None, :] / 255.0 * emit
    return m


def _glints(c, x, y, r, n, rgb=(0.45, 0.55, 0.8), k=1.0):
    """辉石里的碎光点"""
    for _ in range(n):
        a, rr = c.rng.uniform(0, 2 * math.pi), r * c.rng.uniform(0.1, 0.85) ** 0.7
        c.emit += c.circle(x + rr * math.cos(a), y + rr * math.sin(a), c.rng.uniform(0.0025, 0.005), soft=0.002)[..., None] * (np.array(rgb) * k)[None, None, :]


def _walks(c, mask, n, L=(0.06, 0.16), w=0.005, step=0.01, turn=0.5, branch=0.2, starts=None):
    """遮罩里随机分叉的细线（血纹、裂纹），只返回遮罩"""
    im = Image.new('L', (W, W), 0)
    d = ImageDraw.Draw(im)
    ys, xs = np.nonzero(mask > 0.5)
    if starts is None:
        idx = c.rng.integers(0, len(xs), n)
        starts = [(xs[i] / W, ys[i] / W) for i in idx]

    def walk(x, y, a, Lr, wd, depth):
        pts = [(x, y)]
        for _ in range(int(Lr / step)):
            a += c.rng.normal(0, turn)
            x += step * math.cos(a)
            y += step * math.sin(a)
            if not (0 <= x < 1 and 0 <= y < 1) or mask[int(y * W), int(x * W)] < 0.5:
                break
            pts.append((x, y))
            if depth and c.rng.random() < branch:
                walk(x, y, a + c.rng.choice([-1, 1]) * c.rng.uniform(0.5, 1.1), Lr * 0.5, wd * 0.6, depth - 1)
        if len(pts) > 1:
            d.line([(px * W, py * W) for px, py in pts], fill=255, width=max(1, int(round(wd * W))))

    for x, y in starts:
        walk(x, y, c.rng.uniform(0, 2 * math.pi), c.rng.uniform(*L), w, 2)
    return c._arr(im, 0.001) * mask


def _finish(c, patina=(54, 50, 44), pk=0.3, ham=0.013, scr=60):
    c.hammer(ham)
    c.scratches(scr)
    c.patina(patina, pk)


# ------------------------------------------------------------------ 血契
def dr_blood_pact(out):
    """银圆符印牌（七芒星法阵纹），一根血红荆棘长针从右上斜穿进去、针尖从左下背后穿出；孔里渗血；红绳挂"""
    c = Canvas(601)
    cx, cy, R = 0.5, 0.57, 0.25
    hx, hy, tx, ty = 0.8, 0.24, 0.18, 0.91
    L = math.hypot(tx - hx, ty - hy)
    ux, uy = (tx - hx) / L, (ty - hy) / L
    px, py = -uy, ux
    ex, ey = cx + 0.012, cy - 0.022
    te = ((ex - hx) * ux + (ey - hy) * uy) / L

    def P(t):
        return hx + ux * L * t, hy + uy * L * t

    wmax = 0.046

    def wid(t):
        return 0.008 + 0.038 * (1 - t) ** 0.8

    def needle(t0, t1, phase):
        ts = np.linspace(t0, t1, 40)
        m = c.stroke([P(t) for t in ts], w=wmax, wfn=lambda u: wid(t0 + (t1 - t0) * u) / wmax)
        k = 0
        t = t0 + 0.04
        while t < t1 - 0.03:
            s = 1 if (k + phase) % 2 else -1
            bx, by = P(t)
            w2 = wid(t) / 2
            sz = 0.7 + 0.6 * (1 - t)
            a1 = (bx + s * px * w2 * 0.6 + ux * 0.02 * sz, by + s * py * w2 * 0.6 + uy * 0.02 * sz)
            a2 = (bx + s * px * w2 * 0.6 - ux * 0.012 * sz, by + s * py * w2 * 0.6 - uy * 0.012 * sz)
            ap = (bx + s * px * (w2 + 0.034 * sz) - ux * 0.028 * sz, by + s * py * (w2 + 0.034 * sz) - uy * 0.028 * sz)
            m = np.maximum(m, c.poly([a1, ap, a2]))
            k += 1
            t += 0.085
        return m

    # 针尖那一截在牌子后面（左下穿出来）
    back = needle(te, 1.0, 1)
    c.add(back, 'darkiron', h=0.0, bevel=0.01)
    c.tint(back, (96, 20, 16), 0.85, gloss=0.35)
    # 牌子顶上的耳朵 + 牌子
    ly = cy - R - 0.012
    c.add(c.circle(cx, ly, 0.044), 'silver', h=0.02, bevel=0.016)
    disc = c.circle(cx, cy, R)
    c.add(disc, 'silver', h=0.0, bevel=0.03, dome=0.12)
    c.relief(c.ring(cx, cy, R * 0.935, R * 0.11), h=0.12, soft=0.003)
    eng = _union(c.ring(cx, cy, R * 0.86, 0.006), c.ring(cx, cy, R * 0.68, 0.006), c.ring(cx, cy, R * 0.3, 0.005))
    pa = [-math.pi / 2 + k * 2 * math.pi / 7 for k in range(7)]
    for k in range(48):                                   # 刻度
        a = k / 48 * 2 * math.pi
        if min(abs((a - b + math.pi) % (2 * math.pi) - math.pi) for b in pa) < 0.12:
            continue
        eng = np.maximum(eng, c.stroke([(cx + R * 0.71 * math.cos(a), cy + R * 0.71 * math.sin(a)),
                                        (cx + R * 0.83 * math.cos(a), cy + R * 0.83 * math.sin(a))], w=0.0045))
    star = [(cx + R * 0.66 * math.cos(a), cy + R * 0.66 * math.sin(a)) for a in pa]
    for k in range(7):                                    # 七芒星 {7/3}
        eng = np.maximum(eng, c.stroke([star[k], star[(k + 3) % 7]], w=0.0065))
    c.engrave(eng * disc, depth=0.09, soft=0.001)
    c.relief(_union(*[c.circle(cx + R * 0.77 * math.cos(a), cy + R * 0.77 * math.sin(a), 0.013) for a in pa]), h=0.08, soft=0.002)
    # 穿孔 + 渗血
    c.engrave(c.circle(ex, ey, 0.03), depth=0.14)
    c.tint(c.circle(ex, ey, 0.024), (36, 8, 6), 0.9)
    drip = _union(c.stroke(_spline([(ex + 0.004, ey + 0.015), (ex - 0.004, ey + 0.06), (ex + 0.004, ey + 0.11), (ex - 0.002, ey + 0.15)], 6),
                           w=0.016, wfn=lambda u: 1 - 0.45 * u),
                  c.circle(ex - 0.002, ey + 0.158, 0.012),
                  c.stroke([(ex - 0.01, ey + 0.012), (ex - 0.04, ey + 0.05), (ex - 0.045, ey + 0.075)], w=0.011, wfn=lambda u: 1 - 0.6 * u))
    c.relief(drip, h=0.05, soft=0.002)
    c.tint(drip, (92, 12, 10), 0.95, gloss=0.8)
    # 前面那一截（针头在右上）
    front = needle(0.0, te + 0.012, 0)
    c.add(front, 'darkiron', h=0.55, bevel=0.016)
    c.tint(front, (100, 22, 17), 0.85, gloss=0.35)
    c.add(c.circle(hx, hy, 0.04), 'darkiron', h=0.6, bevel=0.02, dome=0.3)
    c.gem(c.circle(hx - 0.003, hy - 0.003, 0.023), (118, 16, 12))
    # 耳朵上的孔 + 红绳
    c.engrave(c.circle(cx, ly - 0.01, 0.014), depth=0.35)
    c.tint(c.circle(cx, ly - 0.01, 0.012), (14, 10, 8), 1.0)
    loop = _spline([(cx - 0.004, ly - 0.008), (cx - 0.034, ly - 0.06), (cx - 0.042, ly - 0.12), (cx - 0.02, ly - 0.163),
                    (cx, ly - 0.172), (cx + 0.02, ly - 0.163), (cx + 0.042, ly - 0.12), (cx + 0.034, ly - 0.06), (cx + 0.004, ly - 0.008)], 6)
    c.cord(loop, rgb=(104, 30, 22), w=0.015, h=0.45)
    c.add(c.ellipse(cx, ly - 0.07, 0.04, 0.018), 'cloth', h=0.55, bevel=0.01, dome=0.3)
    c.tint(c.ellipse(cx, ly - 0.07, 0.04, 0.018), (96, 28, 20), 0.9)
    _finish(c, (52, 52, 50), 0.4)
    return c.save(out, chip=0.6, **DARK)


# ------------------------------------------------------------------ 血涌
def dr_blood_surge(out):
    """骨爪（从上往下抓）攥着一块满是血纹的红辉石（切面晶体）；腕骨顶上金箍 + 挂环"""
    c = Canvas(602)
    cx, cy, R = 0.5, 0.6, 0.19
    n = 11
    pts = []
    for k in range(n):
        a = -math.pi / 2 + (k + c.rng.uniform(-0.3, 0.3)) * 2 * math.pi / n
        r = R * c.rng.uniform(0.86, 1.05)
        pts.append((cx + r * math.cos(a) * 0.95, cy + r * math.sin(a) * 1.1))
    stone = c.poly(pts)
    c.add(stone, 'silver', h=0.1, bevel=0.03)
    # 切面：以偏左上的顶点做一个多面锥，每个三角面是平的
    ax, ay = cx - 0.035, cy - 0.04
    Hpk = 1.1
    facet = np.zeros((W, W))
    lines = np.zeros((W, W))
    for k in range(n):
        v1, v2 = pts[k], pts[(k + 1) % n]
        tri = c.poly([(ax, ay), v1, v2], soft=0.0) > 0.5
        ex_, ey_ = v2[0] - v1[0], v2[1] - v1[1]
        nx_, ny_ = -ey_, ex_
        nn = math.hypot(nx_, ny_)
        nx_, ny_ = nx_ / nn, ny_ / nn
        dap = abs((ax - v1[0]) * nx_ + (ay - v1[1]) * ny_)
        lam = np.abs((XX - v1[0]) * nx_ + (YY - v1[1]) * ny_) / dap
        facet = np.where(tri, Hpk * np.clip(lam, 0, 1), facet)
        lines = np.maximum(lines, c.stroke([(ax, ay), v1], w=0.004))
    c.h += facet * (stone > 0.5)
    c.engrave(lines * stone, depth=0.04, soft=0.001)
    # 血纹：深浅不一的红，黑红的纹路，几条亮一点的细纹
    cloud = np.clip(c._noise(0.014) * 1.4 + 0.5, 0, 1)
    col = np.array([66, 6, 6])[None, None, :] * (1 - cloud[..., None]) + np.array([138, 22, 16])[None, None, :] * cloud[..., None]
    c.color = np.where(stone[..., None] > 0.5, col, c.color)
    c.custom = np.maximum(c.custom, stone)
    c.gloss = np.maximum(c.gloss, 0.9 * stone)
    veins = _walks(c, stone, 9, L=(0.08, 0.2), w=0.006, turn=0.55, branch=0.3)
    c.tint(veins, (30, 3, 3), 0.95)
    c.engrave(veins, depth=0.03, soft=0.001)
    hot = _walks(c, stone * c.ellipse(cx, cy + 0.02, R * 0.7, R * 0.75), 4, L=(0.05, 0.1), w=0.004, turn=0.6, branch=0.25)
    c.emit += hot[..., None] * np.array([0.42, 0.08, 0.04])[None, None, :]
    c.emit += (_blur(c.ellipse(cx + 0.01, cy + 0.03, 0.07, 0.08), 0.03) * stone)[..., None] * np.array([0.22, 0.03, 0.02])[None, None, :]
    _glints(c, cx, cy, R * 0.9, 8, (0.5, 0.2, 0.14))
    c.glow(c.ellipse(cx, cy + 0.02, 0.1, 0.11), (150, 30, 20), r=0.05, k=0.12)
    top = Hpk + 0.5

    def finger(pts, w0, hh, knuckles=(0.36, 0.7), claw_len=0.065):
        fp = _spline(pts, 8)
        _add(c, c.stroke(fp, w=w0, wfn=lambda u: 1 - 0.45 * u), 'bone', h=hh, bevel=w0 * 0.45)
        for f in knuckles:
            kx, ky = fp[int(f * (len(fp) - 1))]
            kr = w0 * (0.66 - 0.18 * f)
            km = c.circle(kx, ky, kr)
            _add(c, km, 'bone', h=hh + 0.05, bevel=kr * 0.6, dome=0.2)
            c.engrave(c.ring_mask_edge(km, 0.004), depth=0.07)
        (x1, y1), (x2, y2) = fp[-3], fp[-1]
        dx, dy = _unit(x2 - x1, y2 - y1)
        ix, iy = _unit(cx - x2, cy - y2)
        claw = c.stroke(_spline([(x2 - dx * 0.006, y2 - dy * 0.006), (x2 + dx * claw_len * 0.55 + ix * claw_len * 0.12, y2 + dy * claw_len * 0.55 + iy * claw_len * 0.12),
                                 (x2 + dx * claw_len * 0.7 + ix * claw_len * 0.6, y2 + dy * claw_len * 0.7 + iy * claw_len * 0.6)], 6),
                        w=w0 * 0.72, wfn=lambda u: 1 - 0.92 * u)
        _add(c, claw, 'darkiron', h=hh + 0.1, bevel=0.01)
        c.tint(claw, (40, 34, 30), 0.6, gloss=0.3)

    # 掌骨：一团骨节（没有长腕骨，免得像瓶颈），顶上金箍 + 挂环
    palm = _union(c.ellipse(cx, 0.355, 0.088, 0.06), c.circle(cx, 0.29, 0.045))
    _add(c, palm, 'bone', h=top + 0.1, bevel=0.03, dome=0.35)
    for x, y, r in ((cx - 0.05, 0.37, 0.028), (cx, 0.385, 0.03), (cx + 0.05, 0.37, 0.028), (cx - 0.025, 0.315, 0.024), (cx + 0.025, 0.315, 0.024)):
        c.relief(c.circle(x, y, r), h=0.07, soft=0.003)
        c.engrave(c.ring_mask_edge(c.circle(x, y, r), 0.003) * palm, depth=0.04)
    cap = c.ellipse(cx, 0.255, 0.04, 0.024)
    _add(c, cap, 'oldgold', h=top + 0.3, bevel=0.012, dome=0.3)
    c.engrave(c.stroke([(cx - 0.04, 0.257), (cx + 0.04, 0.257)], w=0.004), depth=0.05)
    # 两边的爪：从掌骨出来，贴着石头的边往下包，爪尖往里勾
    for s in (-1, 1):
        pts = [(cx + s * 0.06, 0.36)]
        for u in np.linspace(0, 1, 5):
            a = -1.1 + 1.55 * u
            r = R * (1.03 - 0.1 * u ** 2)
            pts.append((cx + s * r * math.cos(a) * 0.98, cy + r * math.sin(a) * 1.1))
        finger(pts, 0.054, top + 0.2)
    # 前面两根短爪，压在石头上半
    for s in (-1, 1):
        finger([(cx + s * 0.025, 0.39), (cx + s * 0.05, 0.45), (cx + s * 0.06, 0.51)], 0.044, top + 0.3, knuckles=(0.45,), claw_len=0.055)
    c.bail(cx, 0.19, 'oldgold', r=0.027, w=0.014, h=top + 0.35, down=0.022)
    _finish(c, (70, 58, 40), 0.3)
    return c.save(out, chip=0.5, **DARK)


# ------------------------------------------------------------------ 涌流
def dr_orb_flow(out):
    """银弯月坠（两角朝上），沿月牙从左到右嵌三颗由小到大的蓝辉石；两角穿绳，绳在顶上打结"""
    c = Canvas(603)
    C1x, C1y, R = 0.5, 0.53, 0.3
    C2x, C2y, R2 = 0.5, 0.41, 0.25
    moon = np.clip(c.circle(C1x, C1y, R) - c.circle(C2x, C2y, R2), 0, 1)

    def band(deg):
        a = math.radians(deg)
        dx, dy = math.cos(a), math.sin(a)
        bx, by = C1x - C2x, C1y - C2y
        b = bx * dx + by * dy
        cc = bx * bx + by * by - R2 * R2
        t = -b + math.sqrt(b * b - cc)
        m = (t + R) / 2
        return (C1x + m * dx, C1y + m * dy), R - t

    # 两角的穿绳孔（圆头）
    eyes = [band(d)[0] for d in (209, -29)]
    for x, y in eyes:
        c.add(c.circle(x, y, 0.026), 'silver', h=0.0, bevel=0.012)
    c.add(moon, 'silver', h=0.0, bevel=0.03, dome=0.25)
    for x, y in eyes:
        c.add(c.circle(x, y, 0.026), 'silver', h=0.12, bevel=0.012, dome=0.2)
    # 外沿、内沿各一道刻线 + 波纹（涌流）
    eng = _union(c.ring(C1x, C1y, R - 0.017, 0.005), c.ring(C2x, C2y, R2 + 0.017, 0.005)) * moon
    pts = []
    d0, d1 = 200, -20
    for u in np.linspace(0, 1, 160):
        d = d0 + (d1 - d0) * u
        (mx, my), th = band(d)
        a = math.radians(d)
        off = 0.16 * th * math.sin(u * 2 * math.pi * 8)
        pts.append((mx + off * math.cos(a), my + off * math.sin(a)))
    eng = np.maximum(eng, c.stroke(pts, w=0.005, wfn=lambda u: math.sin(math.pi * u) ** 0.3))
    c.engrave(eng, depth=0.09, soft=0.001)
    # 三颗由小到大的辉石（包边金托）
    for d, r in ((152, 0.024), (98, 0.034), (42, 0.047)):
        (x, y), th = band(d)
        c.add(c.circle(x, y, r + 0.011), 'oldgold', h=0.35, bevel=0.008)
        c.beads(x, y, r + 0.006, max(8, int(r * 420)), 0.0035, h=0.05)
        c.gem(c.circle(x, y, r), (66, 100, 180))
        _glints(c, x, y, r, int(r * 160), (0.4, 0.5, 0.75))
        c.glow(c.circle(x, y, r * 0.8), (90, 140, 230), r=r * 0.8, k=0.08 + r * 1.5)
    for x, y in eyes:
        c.engrave(c.circle(x, y, 0.01), depth=0.35)
        c.tint(c.circle(x, y, 0.009), (12, 10, 8), 1.0)
    # 绳：两角往上收到一个结，结上一个小环
    kx, ky = 0.5, 0.2
    (lx, lyy), (rx, ry) = eyes
    c.cord(_spline([(lx, lyy), (lx + 0.03, lyy - 0.08), (kx - 0.07, ky + 0.05), (kx - 0.012, ky + 0.005)], 8), rgb=(108, 80, 52), w=0.013, h=0.45)
    c.cord(_spline([(rx, ry), (rx - 0.03, ry - 0.08), (kx + 0.07, ky + 0.05), (kx + 0.012, ky + 0.005)], 8), rgb=(108, 80, 52), w=0.013, h=0.45)
    c.cord(_spline([(kx - 0.01, ky - 0.01), (kx - 0.036, ky - 0.06), (kx, ky - 0.1), (kx + 0.036, ky - 0.06), (kx + 0.01, ky - 0.01)], 6), rgb=(108, 80, 52), w=0.013, h=0.45)
    knot = c.ellipse(kx, ky, 0.026, 0.02)
    c.add(knot, 'cloth', h=0.55, bevel=0.012, dome=0.4)
    c.tint(knot, (100, 74, 48), 0.9)
    c.engrave(c.stroke([(kx - 0.02, ky - 0.008), (kx + 0.02, ky + 0.008)], w=0.004), depth=0.06)
    _finish(c, (50, 50, 48), 0.35)
    return c.save(out, chip=0.6, **DARK)


# ------------------------------------------------------------------ 迸发
def dr_orb_burst(out):
    """铸铜小钵（像小香炉 / 炮口：厚唇沿 + 细腰 + 圈足），两侧耳环各挂一条链，在顶上并到一个挂环；
    钵口往上扇形迸出三颗小辉石（左、中间最高、右），每颗身后一道淡彗尾指回钵口，几点小火星（2026-11-11 用户嫌裂石像闪电贴纸，换掉）"""
    c = Canvas(604)
    mx, my = 0.5, 0.615                                   # 钵口中心
    lx, rx, ly = 0.272, 0.728, 0.655                      # 两侧耳环
    # 链子：两侧耳环 → 顶上挂环（最先画，在最后面）
    for s, x in ((-1, lx), (1, rx)):
        c.chain((x, ly - 0.034), (0.5 + s * 0.022, 0.14), 'iron', link=0.044, w=0.011, h=0.15)
    c.bail(0.5, 0.1, 'oldgold', r=0.028, w=0.014, h=0.3, down=0.0)
    for x in (lx, rx):
        c.add(c.ring(x, ly, 0.03, 0.016), 'bronze', h=0.2, bevel=0.008)
    # 钵身：厚唇沿 + 往下收的钵腹 + 细腰 + 外撇的圈足
    prof = _spline([(0.615, 0.205), (0.65, 0.2), (0.7, 0.185), (0.75, 0.155), (0.79, 0.118), (0.815, 0.085), (0.83, 0.075),
                    (0.85, 0.09), (0.87, 0.118), (0.885, 0.122)], 6)
    side = c.poly([(mx - w, y) for y, w in prof] + [(mx + w, y) for y, w in prof[::-1]])
    lip = c.ellipse(mx, my, 0.222, 0.05)
    body = _union(side, lip)
    c.add(body, 'bronze', h=0.3, bevel=0.04, dome=0.3)
    # 唇沿凸起一圈 + 钵口（黑，里面透一点蓝光）
    c.relief(np.clip(lip - c.ellipse(mx, my - 0.002, 0.18, 0.034), 0, 1), h=0.1, soft=0.003)
    mouth = c.ellipse(mx, my - 0.004, 0.17, 0.03)
    c.engrave(mouth, depth=0.35)
    c.tint(mouth, (14, 14, 18), 1.0)
    c.emit += (_blur(c.ellipse(mx, my - 0.008, 0.05, 0.01), 0.008) * mouth)[..., None] * np.array([0.04, 0.07, 0.16])[None, None, :]
    # 钵腹：唇下一道凸箍 + 一排珠点 + 竖肋；腰上一道箍；圈足一道刻线
    band = c.stroke([(mx + 0.2 * math.cos(a), my + 0.03 + 0.05 * math.sin(a)) for a in np.linspace(0.12, math.pi - 0.12, 40)], w=0.016) * body
    c.relief(band, h=0.08, soft=0.002)
    c.engrave(c.ring_mask_edge(band, 0.003), depth=0.05)
    beads = _union(*[c.circle(mx + 0.175 * math.cos(a), my + 0.065 + 0.045 * math.sin(a), 0.0075) for a in np.linspace(0.3, math.pi - 0.3, 13)])
    c.relief(beads * body, h=0.07, soft=0.0015)
    hw = lambda y: float(np.interp(y, [p[0] for p in prof], [p[1] for p in prof]))  # noqa: E731
    ribs = _union(*[c.stroke([(mx + hw(y) * 0.92 * math.sin(th), y) for y in np.linspace(0.715, 0.8, 10)], w=0.005) for th in np.linspace(-1.1, 1.1, 7)])
    c.engrave(ribs * body, depth=0.07, soft=0.001)
    c.relief(body * (YY > 0.818) * (YY < 0.838), h=0.07, soft=0.002)
    c.engrave(c.stroke([(mx - 0.12, 0.868), (mx + 0.12, 0.868)], w=0.005) * body, depth=0.06)
    # 耳环和钵身接口处的小铜疙瘩
    for x in (lx + 0.03, rx - 0.03):
        c.add(c.circle(x, ly, 0.017), 'bronze', h=0.75, bevel=0.009, dome=0.4)
    c.hammer(0.014)
    c.scratches(50)
    c.patina((62, 78, 62), 0.45, scale=0.015, thr=0.5)
    # 三颗迸出的小辉石（扇形：左、中间最高、右），身后一道淡彗尾指回钵口
    for x, y, r in ((0.4, 0.445, 0.037), (0.5, 0.325, 0.043), (0.6, 0.445, 0.037)):
        dx, dy = _unit(mx - x, my - 0.02 - y)
        L = 0.13 if y < 0.4 else 0.1
        x0, y0 = x + dx * r * 0.7, y + dy * r * 0.7
        c.wisp([(x0 + dx * L * u, y0 + dy * L * u) for u in np.linspace(0, 1, 14)], (70, 120, 230),
               w=r * 1.1, k=0.3, r=0.008, wfn=lambda u: (1 - u) ** 1.3, core=0.0)
        c.orb(x, y, r, (80, 120, 210), glow=0.12)
        _glints(c, x, y, r, 3, (0.4, 0.5, 0.75))
    # 几点小火星
    for x, y, a in ((0.44, 0.56, -2.0), (0.57, 0.555, -1.1), (0.47, 0.49, -1.8), (0.535, 0.5, -1.35), (0.36, 0.53, -2.4), (0.645, 0.52, -0.7)):
        c.wisp([(x + 0.016 * u * math.cos(a), y + 0.016 * u * math.sin(a)) for u in np.linspace(0, 1, 5)], (170, 200, 255),
               w=0.005, k=0.35, r=0.003, wfn=lambda u: 1 - 0.7 * u, core=0.5)
    return c.save(out, chip=0.5, **DARK)


# ------------------------------------------------------------------ 星群
def dr_orb_swarm(out):
    """黑铁星盘：铜外圈刻度，盘面刻星座连线，五颗小辉石当星点；顶上铜托挂链"""
    c = Canvas(605)
    cx, cy, R = 0.5, 0.58, 0.27
    ty = cy - R
    throne = c.poly(_spline([(cx - 0.085, ty + 0.03), (cx - 0.07, ty - 0.02), (cx - 0.035, ty - 0.055), (cx, ty - 0.075),
                             (cx + 0.035, ty - 0.055), (cx + 0.07, ty - 0.02), (cx + 0.085, ty + 0.03)], 6))
    c.add(throne, 'bronze', h=0.05, bevel=0.016, dome=0.2)
    disc = c.circle(cx, cy, R)
    c.add(disc, 'darkiron', h=0.0, bevel=0.02, dome=0.08)
    rim = c.ring(cx, cy, R * 0.92, R * 0.16)
    c.add(rim * disc, 'bronze', h=0.12, bevel=0.012)
    tick = np.zeros((W, W))
    for k in range(60):
        a = k / 60 * 2 * math.pi
        r0 = R * (0.86 if k % 5 == 0 else 0.9)
        tick = np.maximum(tick, c.stroke([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + R * 0.97 * math.cos(a), cy + R * 0.97 * math.sin(a))],
                                         w=0.0045 if k % 5 else 0.006))
    c.engrave(tick * disc, depth=0.08, soft=0.001)
    c.engrave(c.ring(cx, cy, R * 0.84, 0.006), depth=0.1)
    # 盘面：赤道圈 + 偏心的黄道圈 + 十字线（浅刻）
    face = c.circle(cx, cy, R * 0.82)
    lines = _union(c.ring(cx, cy, R * 0.52, 0.0045), c.ring(cx + 0.02, cy - 0.045, R * 0.6, 0.0045),
                   c.stroke([(cx - R * 0.82, cy), (cx + R * 0.82, cy)], w=0.004), c.stroke([(cx, cy - R * 0.82), (cx, cy + R * 0.82)], w=0.004))
    c.engrave(lines * face, depth=0.05, soft=0.001)
    # 星座：五颗星，刻线连起来
    st = [(cx - 0.15, cy - 0.02), (cx - 0.07, cy - 0.12), (cx + 0.02, cy - 0.05), (cx + 0.13, cy - 0.11), (cx + 0.09, cy + 0.11)]
    con = _union(*[c.stroke([st[i], st[j]], w=0.0065) for i, j in ((0, 1), (1, 2), (2, 3), (2, 4))])
    c.relief(con, h=0.05, soft=0.0015)
    c.tint(con, (150, 118, 70), 0.6)
    for _ in range(14):                                     # 零碎的小星（刻点）
        a, rr = c.rng.uniform(0, 2 * math.pi), R * c.rng.uniform(0.15, 0.78)
        c.engrave(c.circle(cx + rr * math.cos(a), cy + rr * math.sin(a), 0.006), depth=0.08, soft=0.001)
    for (x, y), r in zip(st, (0.02, 0.017, 0.025, 0.019, 0.022)):
        _add(c, c.circle(x, y, r + 0.008), 'bronze', h=0.3, bevel=0.006)
        c.gem(c.circle(x, y, r), (70, 108, 190))
        _glints(c, x, y, r, 3, (0.4, 0.5, 0.75))
        c.glow(c.circle(x, y, r * 0.7), (100, 150, 240), r=0.016, k=0.22)
        # 四角星芒
        c.wisp([(x - r * 2.2, y), (x + r * 2.2, y)], (140, 180, 255), w=0.004, k=0.25, r=0.003, core=0.35)
        c.wisp([(x, y - r * 2.2), (x, y + r * 2.2)], (140, 180, 255), w=0.004, k=0.25, r=0.003, core=0.35)
    _add(c, c.circle(cx, cy, 0.022), 'bronze', h=0.3, bevel=0.01, dome=0.4)
    c.engrave(c.circle(cx, cy, 0.006), depth=0.1)
    # 铜托上的孔 + 链子
    c.engrave(c.circle(cx, ty - 0.04, 0.015), depth=0.35)
    c.tint(c.circle(cx, ty - 0.04, 0.013), (12, 10, 8), 1.0)
    c.chain((cx, ty - 0.05), (cx, 0.11), 'iron', link=0.046, w=0.011, h=0.4)
    c.bail(cx, 0.085, 'bronze', r=0.026, w=0.013, h=0.45, down=0.0)
    _finish(c, (52, 48, 40), 0.3)
    return c.save(out, chip=0.6, **DARK)


# ------------------------------------------------------------------ 盈满
def dr_hawk(out):
    """一个小网兜装满蓝辉石珠，口子用红绳扎紧，绳子绕个圈挂起来"""
    c = Canvas(606)
    ny0, H = 0.37, 0.49

    def hw(t):
        if t < 0.6:
            return 0.045 + 0.215 * math.sin(math.pi / 2 * t / 0.6) ** 0.9
        return 0.26 * math.sqrt(max(0.0, 1 - ((t - 0.6) / 0.4) ** 2))

    ts = np.linspace(0, 1, 80)
    outline = [(0.5 - hw(t), ny0 + H * t) for t in ts] + [(0.5 + hw(t), ny0 + H * t) for t in ts[::-1]]
    bag = c.poly(outline)
    # 网里面的底（暗）
    c.add(bag, 'cloth', h=0.0, bevel=0.03, dome=0.2)
    c.tint(bag, (30, 32, 40), 0.9)
    # 珠子
    beads = []
    for _ in range(4000):
        t = c.rng.uniform(0.04, 0.97)
        s = c.rng.uniform(-1, 1)
        r = c.rng.uniform(0.03, 0.045)
        w_ = hw(t)
        x, y = 0.5 + s * w_, ny0 + H * t
        if abs(s) * w_ + r * 0.55 > w_ or y + r * 0.5 > ny0 + H * (1 - 0.005):
            continue
        if any(math.hypot(x - bx, y - by) < (r + br) * 0.8 for bx, by, br, _ in beads):
            continue
        beads.append((x, y, r, s))
        if len(beads) > 40:
            break
    pal = [(64, 96, 165), (78, 112, 182), (52, 76, 138), (88, 118, 172), (62, 82, 124), (70, 104, 176)]
    for x, y, r, s in sorted(beads, key=lambda b: 1 - abs(b[3])):
        hb = 0.12 + 0.18 * (1 - abs(s)) + c.rng.uniform(0, 0.04)
        rgb = pal[c.rng.integers(0, len(pal))]
        _bead(c, x, y, r, rgb, h=hb, emit=0.28, gloss=0.6)
        if c.rng.random() < 0.5:
            _glints(c, x, y, r, 2, (0.35, 0.45, 0.7))
    c.glow(bag, (90, 140, 230), r=0.05, k=0.08)
    # 网：两组斜线往网口收拢（按球面投影）
    net = np.zeros((W, W))
    kk, step = 3.2, 0.45
    for sgn in (1, -1):
        for th0 in np.arange(-math.pi - 3.2, math.pi + 0.5, step):
            seg = []
            for t in np.linspace(0.0, 0.995, 70):
                th = th0 + sgn * kk * t
                if abs(th) <= math.pi / 2:
                    seg.append((0.5 + hw(t) * math.sin(th), ny0 + H * t))
                elif len(seg) > 1:
                    net = np.maximum(net, c.stroke(seg, w=0.0085))
                    seg = []
                else:
                    seg = []
            if len(seg) > 1:
                net = np.maximum(net, c.stroke(seg, w=0.0085))
    net = net * bag
    c.add(net, 'cloth', h=0.62, bevel=0.004)
    c.tint(net, (92, 78, 56), 0.9)
    # 挂绳圈（在扎口后面）
    c.cord(_spline([(0.47, 0.33), (0.415, 0.25), (0.415, 0.16), (0.46, 0.1), (0.5, 0.09), (0.54, 0.1), (0.585, 0.16), (0.585, 0.25), (0.53, 0.33)], 6),
           rgb=(108, 32, 24), w=0.015, h=0.4)
    # 收拢的网口 + 上面散开的一撮
    neck = c.poly([(0.445, 0.395), (0.555, 0.395), (0.535, 0.31), (0.465, 0.31)])
    c.add(neck, 'cloth', h=0.55, bevel=0.01, dome=0.2)
    c.tint(neck, (92, 78, 56), 0.9)
    folds = _union(*[c.stroke([(0.452 + 0.019 * i, 0.39), (0.47 + 0.012 * i, 0.315)], w=0.004) for i in range(6)])
    c.engrave(folds * neck, depth=0.06, soft=0.001)
    # 扎口上面散开的网头（几缕不齐的线头）
    for a, Lr in ((-2.2, 0.05), (-1.95, 0.065), (-1.7, 0.055), (-1.45, 0.07), (-1.2, 0.05), (-0.95, 0.058)):
        tuft = c.stroke(_spline([(0.5 + (a + 1.57) * 0.02, 0.315), (0.5 + (a + 1.57) * 0.03 + Lr * 0.4 * math.cos(a), 0.315 + Lr * 0.5 * math.sin(a)),
                                 (0.5 + (a + 1.57) * 0.03 + Lr * math.cos(a), 0.315 + Lr * math.sin(a))], 5), w=0.011, wfn=lambda u: 1 - 0.6 * u)
        c.add(tuft, 'cloth', h=0.5, bevel=0.005)
        c.tint(tuft, (92, 78, 56), 0.9)
    # 扎口：几圈红绳 + 垂下来的两个绳头
    for y in (0.322, 0.338, 0.354):
        c.cord([(0.455, y + 0.004), (0.545, y - 0.004)], rgb=(112, 34, 24), w=0.016, h=0.75)
    c.cord(_spline([(0.545, 0.345), (0.575, 0.38), (0.59, 0.43), (0.585, 0.46)], 6), rgb=(112, 34, 24), w=0.013, h=0.8)
    c.cord(_spline([(0.54, 0.35), (0.555, 0.39), (0.555, 0.42)], 6), rgb=(112, 34, 24), w=0.012, h=0.8)
    for x, y in ((0.585, 0.465), (0.555, 0.425)):
        c.add(c.circle(x, y, 0.012), 'cloth', h=0.85, bevel=0.006, dome=0.4)
        c.tint(c.circle(x, y, 0.012), (100, 30, 22), 0.9)
    c.hammer(0.01)
    c.scratches(30)
    return c.save(out, chip=0.4, **DARK)


# ------------------------------------------------------------------ 寸劲
def dr_steady(out):
    """铁指虎：四个指环连成一排，下面一道弯握把；指环顶上铜钉；正中顶上挂链"""
    c = Canvas(607)
    cy = 0.5
    xs = [0.29, 0.43, 0.57, 0.71]
    ro, ri = 0.078, 0.046
    plate = _union(*[c.circle(x, cy, ro) for x in xs], c.poly([(0.29, cy - 0.04), (0.71, cy - 0.04), (0.71, cy + 0.07), (0.29, cy + 0.07)]))
    grip = c.stroke(_spline([(0.232, cy + 0.03), (0.255, cy + 0.15), (0.37, cy + 0.218), (0.63, cy + 0.218), (0.745, cy + 0.15), (0.768, cy + 0.03)], 8), w=0.062)
    web = c.poly([(0.27, cy + 0.05), (0.73, cy + 0.05), (0.72, cy + 0.17), (0.6, cy + 0.2), (0.4, cy + 0.2), (0.28, cy + 0.17)])
    holes = _union(*[c.circle(x, cy, ri) for x in xs], c.ellipse(0.392, cy + 0.133, 0.068, 0.027), c.ellipse(0.608, cy + 0.133, 0.068, 0.027))
    body = np.clip(_union(plate, grip, web) - holes, 0, 1)
    # 顶上的小环（挂链用），在后面
    c.add(c.ring(0.5, cy - 0.072, 0.02, 0.013), 'iron', h=0.05, bevel=0.006)
    c.add(body, 'iron', h=0.0, bevel=0.03, dome=0.15)
    eng = _union(*[c.ring(x, cy, ri + 0.009, 0.005) for x in xs])
    eng = np.maximum(eng, c.stroke(_spline([(0.27, cy + 0.085), (0.4, cy + 0.088), (0.6, cy + 0.088), (0.73, cy + 0.085)], 6), w=0.005))
    c.engrave(eng * body, depth=0.08, soft=0.001)
    c.hatch(grip * (YY > cy + 0.16) * body, angle=1.2, gap=0.014, w=0.004, depth=0.05)
    for x in xs:
        st = c.circle(x, cy - 0.062, 0.016)
        c.add(st, 'bronze', h=0.42, bevel=0.01, dome=0.5)
    for x in (0.36, 0.5, 0.64):
        c.add(c.circle(x, cy + 0.163, 0.011), 'bronze', h=0.4, bevel=0.006, dome=0.4)
    c.chain((0.5, cy - 0.095), (0.5, 0.18), 'iron', link=0.046, w=0.011, h=0.3)
    c.bail(0.5, 0.15, 'bronze', r=0.026, w=0.013, h=0.35, down=0.0)
    _finish(c, (74, 50, 34), 0.35)
    return c.save(out, chip=0.6, tilt=6, **DARK)


# ------------------------------------------------------------------ 碎骨
def dr_crack(out):
    """一截兽骨（两头骨节），中段被敲出一道裂缝，两边铁箍箍住；上端缠红绳挂起"""
    c = Canvas(608)
    ax, ay, bx, by = 0.33, 0.33, 0.69, 0.82
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    px, py = -uy, ux

    def Q(t, s=0.0):
        return ax + ux * L * t + px * s, ay + uy * L * t + py * s

    sw = 0.12
    shaft = c.stroke([Q(t) for t in np.linspace(0.06, 0.94, 30)], w=sw, wfn=lambda u: 1 - 0.2 * math.sin(math.pi * u))
    endA = _union(c.circle(*Q(0.03, 0.05), 0.066), c.circle(*Q(0.03, -0.048), 0.062), c.circle(*Q(-0.02, 0.0), 0.05))
    endB = _union(c.circle(*Q(0.97, 0.016), 0.076), c.circle(*Q(0.9, -0.058), 0.045))
    bone = _union(shaft, endA, endB)
    # 裂口边上崩掉的一小块
    bone = np.clip(bone - c.poly([Q(0.52, 0.07), Q(0.565, 0.035), Q(0.59, 0.07)]), 0, 1)
    c.add(bone, 'bone', h=0.0, bevel=0.05, dome=0.4)
    c.engrave(c.stroke([Q(-0.07, 0.0), Q(0.07, 0.0)], w=0.01) * bone, depth=0.1)      # 骨节中间的沟
    c.engrave(c.stroke([Q(0.97, -0.03), Q(0.92, -0.035)], w=0.007) * bone, depth=0.08)
    c.hatch(bone * c.circle(*Q(0.25, 0.0), 0.2), angle=math.atan2(uy, ux) + 0.08, gap=0.03, w=0.003, depth=0.025)   # 骨纤维纹
    # 裂缝：横着一道锯齿（裂得开一点，露出里面的暗色），加两条顺着骨头的细裂
    cr = [Q(0.53, -0.075), Q(0.555, -0.045), Q(0.535, -0.015), Q(0.565, 0.012), Q(0.545, 0.04), Q(0.575, 0.075)]
    crack = c.stroke(cr, w=0.016)
    hair = _union(c.stroke([Q(0.535, -0.015), Q(0.48, -0.008), Q(0.44, -0.02), Q(0.38, -0.01)], w=0.007, wfn=lambda u: 1 - 0.8 * u),
                  c.stroke([Q(0.565, 0.012), Q(0.62, 0.022), Q(0.67, 0.01)], w=0.0065, wfn=lambda u: 1 - 0.8 * u),
                  c.stroke([Q(0.545, 0.04), Q(0.5, 0.06)], w=0.005, wfn=lambda u: 1 - 0.7 * u))
    cm = _union(crack, hair) * bone
    c.engrave(cm, depth=0.3, soft=0.001)
    c.tint(cm, (24, 16, 12), 0.95)
    c.tint(np.clip(_blur(crack, 0.012) * 2.5, 0, 1) * bone * (1 - cm), (110, 92, 66), 0.45)
    # 两道铁箍
    for t in (0.4, 0.71):
        hw_ = sw * (1 - 0.2 * math.sin(math.pi * (t - 0.06) / 0.88)) / 2 + 0.012
        band = c.poly([Q(t - 0.03, -hw_), Q(t + 0.03, -hw_), Q(t + 0.03, hw_), Q(t - 0.03, hw_)])
        c.add(band, 'iron', h=0.5, bevel=0.016, dome=0.35)
        c.engrave(c.stroke([Q(t, -hw_), Q(t, hw_)], w=0.005), depth=0.05)
        for s in (-0.6, 0.6):
            c.add(c.circle(*Q(t, s * hw_), 0.011), 'iron', h=0.66, bevel=0.006, dome=0.4)
    # 上端缠绳 + 绳圈
    for i in range(4):
        t = 0.1 + i * 0.03
        c.cord([Q(t - 0.016, -0.072), Q(t + 0.016, 0.072)], rgb=(118, 40, 26), w=0.019, h=0.6)
    p0, p1 = Q(0.1, -0.075), Q(0.19, -0.075)
    c.cord(_spline([p1, (p1[0] + 0.02, p1[1] - 0.07), (0.44, 0.16), (0.39, 0.09), (0.32, 0.08), (0.28, 0.13), p0], 8), rgb=(118, 40, 26), w=0.023, h=0.55)
    _finish(c, (88, 70, 46), 0.35, scr=50)
    return c.save(out, chip=0.6, **DARK)


# ------------------------------------------------------------------ 破绽
def dr_opening(out):
    """铁挂锁被撬开：锁梁一条腿还插在锁身里，另一条腿弹了出来；锁孔边全是撬痕；锁梁勾在一个铜环上挂着"""
    c = Canvas(609)
    rx, ry, rr = 0.5, 0.16, 0.085
    ring = c.ring(rx, ry, rr, 0.026)
    c.add(ring, 'bronze', h=0.3, bevel=0.012)
    sy = 0.3
    arc = Canvas.arc(0.5, sy, 0.1, math.pi, 2 * math.pi, 40)
    shackle = c.stroke([(0.4, 0.55)] + arc + [(0.6, 0.418)], w=0.042)
    c.add(shackle, 'iron', h=0.5, bevel=0.021)
    c.engrave(c.stroke([(0.58, 0.395), (0.62, 0.395)], w=0.007), depth=0.12)          # 锁舌缺口
    c.tint(c.ellipse(0.6, 0.418, 0.02, 0.008), (150, 148, 140), 0.5)
    # 右边交叉处环压在锁梁上（穿过去）
    c.add(ring * c.circle(0.56, 0.22, 0.04), 'bronze', h=0.85, bevel=0.012)
    # 锁身
    body = c.poly(_rrect(0.29, 0.47, 0.71, 0.85, 0.07))
    c.add(body, 'iron', h=0.6, bevel=0.035, dome=0.2)
    for y in (0.5, 0.82):
        c.relief(c.poly(_rrect(0.31, y - 0.012, 0.69, y + 0.012, 0.01)) * body, h=0.07, soft=0.002)
    for x, y in ((0.33, 0.55), (0.67, 0.55), (0.33, 0.77), (0.67, 0.77)):
        c.add(c.circle(x, y, 0.013), 'iron', h=0.75, bevel=0.007, dome=0.5)
    c.engrave(c.ellipse(0.6, 0.48, 0.024, 0.009), depth=0.25)                      # 锁梁弹出来的孔
    c.tint(c.ellipse(0.6, 0.48, 0.022, 0.008), (12, 10, 8), 1.0)
    # 锁孔铜片 + 锁孔
    esc = c.poly(_spline([(0.5, 0.56), (0.56, 0.585), (0.575, 0.66), (0.545, 0.74), (0.5, 0.765), (0.455, 0.74), (0.425, 0.66), (0.44, 0.585)], 6, closed=True))
    c.add(esc, 'bronze', h=0.8, bevel=0.012, dome=0.2)
    kh = _union(c.circle(0.5, 0.64, 0.02), c.poly([(0.49, 0.645), (0.51, 0.645), (0.518, 0.71), (0.482, 0.71)]))
    c.engrave(kh, depth=0.4)
    c.tint(kh, (8, 6, 5), 1.0)
    # 撬痕：锁孔周围几道刮亮的划痕 + 一处被撬翻的铜片
    pry = _union(c.stroke([(0.52, 0.66), (0.555, 0.695), (0.6, 0.705)], w=0.006), c.stroke([(0.515, 0.7), (0.545, 0.73), (0.57, 0.76)], w=0.005),
                 c.stroke([(0.48, 0.62), (0.45, 0.6), (0.41, 0.6)], w=0.005), c.stroke([(0.52, 0.625), (0.56, 0.6)], w=0.004))
    c.engrave(pry, depth=0.07, soft=0.001)
    c.tint(pry, (176, 166, 146), 0.75)
    c.relief(c.poly([(0.52, 0.72), (0.548, 0.735), (0.53, 0.762)]), h=0.08, soft=0.002)
    _finish(c, (80, 54, 36), 0.4)
    return c.save(out, chip=0.6, tilt=-7, **DARK)


# ------------------------------------------------------------------ 处刑
def dr_execute(out):
    """小刽子手斧：宽刃（刃口亮、带干血），斧背短锤头，木柄缠皮，柄头铁球；柄顶挂环"""
    c = Canvas(610)
    hx = 0.6
    # 柄
    c.add(c.stroke([(hx, 0.13), (hx, 0.9)], w=0.052), 'wood', h=0.0, bevel=0.024)
    c.hatch(c.stroke([(hx, 0.4), (hx, 0.66)], w=0.052), angle=1.45, gap=0.03, w=0.003, depth=0.03)
    wrap = c.stroke([(hx, 0.66), (hx, 0.86)], w=0.058)
    c.add(wrap, 'leather', h=0.05, bevel=0.024)
    for y in np.arange(0.665, 0.86, 0.018):
        c.engrave(c.stroke([(hx - 0.03, y), (hx + 0.03, y + 0.013)], w=0.005), depth=0.06)
    c.add(c.circle(hx, 0.905, 0.036), 'iron', h=0.1, bevel=0.018, dome=0.4)
    c.add(c.ellipse(hx, 0.66, 0.036, 0.014), 'iron', h=0.15, bevel=0.008)
    # 斧头：宽刃往左，下面一个长胡子
    edge = _spline([(0.28, 0.1), (0.2, 0.19), (0.165, 0.3), (0.185, 0.42), (0.24, 0.52), (0.3, 0.58)], 8)
    blade_pts = edge + _spline([(0.3, 0.58), (0.37, 0.52), (0.46, 0.45), (0.56, 0.41)], 6) + [(0.56, 0.41), (0.645, 0.41), (0.66, 0.37), (0.7, 0.355), (0.71, 0.21), (0.67, 0.2), (0.645, 0.16), (0.56, 0.16)] + \
        _spline([(0.56, 0.16), (0.45, 0.145), (0.36, 0.12), (0.28, 0.1)], 6)
    blade = c.poly(blade_pts)
    c.add(blade, 'iron', h=0.2, bevel=0.03, dome=0.15)
    eb = c.stroke(edge, w=0.075) * blade
    c.tint(eb, (150, 150, 146), 0.6, gloss=0.4)
    inner = [(x + 0.04, y + (0.008 if y < 0.3 else -0.012)) for x, y in edge]
    c.engrave(c.stroke(inner[3:-4], w=0.005) * blade, depth=0.08)
    c.engrave(c.ring_mask_edge(c.poly([(x * 0.86 + 0.5 * 0.14, y * 0.86 + 0.33 * 0.14) for x, y in blade_pts]), 0.004) * (XX > 0.3), depth=0.05)
    # 斧身上一个圆孔 + 套口两道箍 + 铆钉
    hole = c.circle(0.43, 0.26, 0.026)
    c.engrave(c.ring_mask_edge(c.circle(0.43, 0.26, 0.036), 0.005), depth=0.08)
    c.alpha = np.where(hole > 0.5, 0.0, c.alpha)
    c.relief(c.poly([(0.555, 0.16), (0.575, 0.16), (0.575, 0.41), (0.555, 0.41)]) * blade, h=0.08, soft=0.002)
    for y in (0.21, 0.36):
        c.add(c.circle(hx + 0.02, y, 0.012), 'iron', h=0.6, bevel=0.006, dome=0.4)
    # 刃口的干血
    bl = np.clip(c._noise(0.008) * 1.6 + 0.2, 0, 1) * _blur(c.stroke(edge[10:40], w=0.07), 0.01) * blade
    c.tint(bl, (72, 16, 12), 0.75, gloss=0.3)
    # 柄顶铁帽 + 挂环
    c.add(c.ellipse(hx, 0.13, 0.03, 0.02), 'iron', h=0.5, bevel=0.012, dome=0.3)
    c.bail(hx, 0.07, 'oldgold', r=0.026, w=0.014, h=0.55, down=0.02)
    _finish(c, (70, 48, 32), 0.35)
    return c.save(out, chip=0.6, tilt=14, **DARK)


# ------------------------------------------------------------------ 余裕
def dr_composure(out):
    """铜框小沙漏：上下铜板、两根拧纹铜柱，玻璃里上半还剩一大半沙，下面一小堆；顶上挂链"""
    c = Canvas(611)
    mid = 0.535
    tp = [(0.235, 0.088), (0.255, 0.122), (0.29, 0.138), (0.34, 0.134), (0.4, 0.112), (0.45, 0.074), (0.49, 0.034), (0.52, 0.013)]
    prof = tp + [(2 * mid - y, w) for y, w in tp[::-1]]
    prof = _spline(prof, 6)
    glass = c.poly([(0.5 - w, y) for y, w in prof] + [(0.5 + w, y) for y, w in prof[::-1]])
    c.add(glass, 'glass', h=0.1, bevel=0.05, dome=0.35)
    c.tint(glass, (46, 52, 54), 0.85, gloss=0.5)
    # 沙子
    level = 0.315
    surf = level + 0.022 * np.exp(-((XX - 0.5) / 0.035) ** 2)
    sand_t = glass * (YY > surf) * (YY < mid)
    heap = 0.825 - 0.075 * np.clip(1 - np.abs(XX - 0.5) / 0.13, 0, 1) ** 1.2
    sand_b = glass * (YY > np.minimum(heap, 0.808)) * (YY > mid)
    stream = c.stroke([(0.5, mid - 0.01), (0.5, 0.755)], w=0.005)
    sand = np.clip(sand_t + sand_b + stream * glass, 0, 1)
    sv = np.clip(c._noise(0.004) * 1.2 + 0.5, 0, 1)
    col = np.array([108, 82, 48])[None, None, :] * (1 - sv[..., None]) + np.array([160, 128, 80])[None, None, :] * sv[..., None]
    c.color = np.where(sand[..., None] > 0.5, col, c.color)
    c.custom = np.maximum(c.custom, sand * 0.95)
    c.relief(sand_t * (YY < surf + 0.012), h=-0.02, soft=0.002)
    # 玻璃上的反光（竖条）
    pys, pws = [p[0] for p in prof], [p[1] for p in prof]
    for y0, y1, k in ((0.25, 0.43, 0.3), (0.64, 0.81, 0.22)):
        hl = c.stroke([(0.5 - 0.72 * float(np.interp(y0 + (y1 - y0) * u, pys, pws)), y0 + (y1 - y0) * u) for u in np.linspace(0, 1, 12)],
                      w=0.008, wfn=lambda u: math.sin(math.pi * u))
        c.emit += _blur(hl, 0.002)[..., None] * k * glass[..., None]
    # 上下铜板
    for y0, y1 in ((0.18, 0.238), (0.832, 0.89)):
        pl = c.poly(_rrect(0.275, y0, 0.725, y1, 0.02))
        _add(c, pl, 'bronze', h=0.45, bevel=0.014, dome=0.2)
        for x in np.linspace(0.31, 0.69, 9):
            c.relief(c.circle(x, (y0 + y1) / 2, 0.006), h=0.07, soft=0.001)
    # 两根拧纹铜柱（在玻璃前面）
    for x in (0.318, 0.682):
        col_m = c.stroke([(x, 0.235), (x, 0.835)], w=0.028)
        c.add(col_m, 'bronze', h=0.55, bevel=0.014)
        c.hatch(col_m, angle=0.8, gap=0.02, w=0.004, depth=0.07)
        for y in (0.255, 0.535, 0.815):
            c.add(c.ellipse(x, y, 0.022, 0.012), 'bronze', h=0.65, bevel=0.008, dome=0.3)
    # 底脚 + 顶上小环、链子
    for x in (0.3, 0.7):
        c.add(c.ellipse(x, 0.9, 0.022, 0.014), 'bronze', h=0.4, bevel=0.008, dome=0.3)
    c.add(c.ellipse(0.5, 0.172, 0.03, 0.016), 'bronze', h=0.6, bevel=0.01, dome=0.3)
    c.chain((0.5, 0.16), (0.5, 0.075), 'iron', link=0.044, w=0.011, h=0.5)
    c.bail(0.5, 0.05, 'bronze', r=0.024, w=0.013, h=0.55, down=0.0)
    _finish(c, (60, 70, 50), 0.3, scr=40)
    return c.save(out, chip=0.5, **DARK)


# ------------------------------------------------------------------ 千钧
def dr_thousand(out):
    """沉甸甸的铁砣：梯形多面体（正面平、两侧斜面），底下一圈厚座，顶上圆钮 + 粗提环；提环挂在一段链子上"""
    c = Canvas(612)
    # 提环（在圆钮后面）
    c.add(c.ring(0.5, 0.325, 0.06, 0.034), 'iron', h=0.05, bevel=0.016)
    outline = [(0.4, 0.41), (0.6, 0.41), (0.638, 0.432), (0.758, 0.8), (0.768, 0.836), (0.758, 0.868),
               (0.242, 0.868), (0.232, 0.836), (0.242, 0.8), (0.362, 0.432)]
    body = c.poly(outline)
    face = c.poly([(0.428, 0.428), (0.572, 0.428), (0.672, 0.8), (0.328, 0.8)], soft=0.0) > 0.5
    c.add(body, 'iron', h=0.0, bevel=0.02)
    d = ndimage.distance_transform_edt(~face) / W
    c.h = np.where(body > 0.5, np.maximum(0.95 - 11.0 * d, 0.12) + 0.04 * (body > 0.5), c.h)
    # 底座：一圈厚边
    base = body * (YY > 0.8)
    c.relief(base, h=0.12, soft=0.002)
    c.engrave(c.stroke([(0.24, 0.8), (0.76, 0.8)], w=0.006) * body, depth=0.1)
    c.engrave(c.stroke([(0.24, 0.836), (0.76, 0.836)], w=0.004) * body, depth=0.05)
    # 正面：凸边框 + 中间一块刻纹的空牌 + 四角铆钉
    fm = face.astype(float)
    c.relief(c.ring_mask_edge(fm, 0.012) * fm, h=0.07, soft=0.002)
    card = c.poly(_rrect(0.43, 0.53, 0.57, 0.72, 0.016))
    inner = c.poly(_rrect(0.445, 0.545, 0.555, 0.705, 0.01))
    c.relief(card, h=0.05, soft=0.002)
    c.engrave(inner, depth=0.05, soft=0.002)
    c.hatch(inner, angle=0.785, gap=0.018, w=0.004, depth=0.03)
    c.hatch(inner, angle=-0.785, gap=0.018, w=0.004, depth=0.03)
    for x, y in ((0.45, 0.46), (0.55, 0.46), (0.36, 0.765), (0.64, 0.765)):
        c.add(c.circle(x, y, 0.013), 'iron', h=1.12, bevel=0.007, dome=0.5)
    # 顶上圆钮
    c.add(c.ellipse(0.5, 0.405, 0.075, 0.03), 'iron', h=0.8, bevel=0.016, dome=0.4)
    # 链子穿过提环
    c.chain((0.5, 0.258), (0.5, 0.1), 'iron', link=0.05, w=0.012, h=0.3)
    c.bail(0.5, 0.072, 'oldgold', r=0.027, w=0.014, h=0.35, down=0.0)
    c.hammer(0.02, scale=0.012)
    c.scratches(70)
    c.patina((86, 52, 32), 0.5, scale=0.015, thr=0.5)
    return c.save(out, chip=1.0, **DARK)


# ------------------------------------------------------------------
def main():
    os.makedirs(OUT, exist_ok=True)
    want = [k for k in sys.argv[1:] if k in KEYS] or KEYS
    for k in want:
        globals()[k](os.path.join(OUT, 'charm_' + k + '.png'))
        print('画好', k)
    ims = []
    for k in KEYS:
        p = os.path.join(OUT, 'charm_' + k + '.png')
        if os.path.exists(p):
            ims.append(Image.open(p).convert('RGBA'))
    sheet = Image.new('RGBA', (160 * len(ims), 160), (40, 36, 30, 255))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, (i * 160, 0))
    sheet.save(os.path.join(OUT, 'sheet_spell.png'))
    sheet.resize((sheet.width * 2, 320), Image.LANCZOS).save(os.path.join(OUT, 'sheet_spell_x2.png'))
    dbg = os.environ.get('SPELL_DBG')
    if dbg:                                   # 调试：本次画的几个放大 3 倍拼一张
        sh = Image.new('RGBA', (480 * len(want), 480), (40, 36, 30, 255))
        for i, k in enumerate(want):
            im = Image.open(os.path.join(OUT, 'charm_' + k + '.png')).convert('RGBA')
            sh.alpha_composite(im.resize((480, 480), Image.LANCZOS), (i * 480, 0))
        sh.save(dbg)


if __name__ == '__main__':
    main()
