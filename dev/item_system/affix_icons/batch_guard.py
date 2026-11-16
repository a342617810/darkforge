# -*- coding: utf-8 -*-
"""第 5 批：防御 / 异常（设计清单.md「第 5 批」）。画法照 icons_charm.py（用户 2026-11-11 认可的护符风格）：
每个词条一件能戴的护符，带挂环 / 链 / 绳（轮流用），压暗、积灰、发光克制。
狼魂 = 狼头侧影黑铁牌 + 蓝石眼（挂环）；壁垒 = 塔盾小铁坠（链）；反震 = 小铜钟（挂环）；
不动如山 = 方铁框里的三峰黑石（绳）；泡盾 = 银丝网兜着的空心水晶球（链）；混沌 = 扭曲的铁丝结 + 暗紫石（绳）；
狂乱共鸣 = 倒挂的铜音叉夹一颗狂乱黄石（挂环）；疫病 = 镂空铜熏球冒淡绿烟（链）；连锁 = 三个互扣铁环各镶一石（绳）。
用法：python batch_guard.py [键 ...]（不给键 = 全画）"""
import math
import os
import sys

import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import Canvas, W, _blur  # noqa: E402
from icons_charm import DARK  # noqa: E402

OUT = os.path.join(HERE, 'out')
KEYS = ['dr_wolf', 'dr_bulwark', 'dr_recoil', 'dr_unshaken', 'dr_bubble', 'dr_chaos', 'dr_resonance', 'dr_pestilence', 'dr_chain']


# ------------------------------------------------------------ 小工具
def _cr(pts, n=10, closed=False):
    """Catmull-Rom：过给定点的平滑曲线"""
    P = list(pts)
    P = ([P[-1]] + P + [P[0], P[1]]) if closed else ([P[0]] + P + [P[-1]])
    res = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            res.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    res.append(P[1] if closed else P[-2])
    return res


def _erode(m, w):
    return ndimage.binary_erosion(m > 0.5, iterations=max(1, int(w * W))).astype(float)


def _grid():
    yy, xx = np.mgrid[0:W, 0:W] / W
    return xx, yy


def _tube(c, pts, zs, w, mat, hk=1.0):
    """圆截面的管子（铁丝、环）：沿折线逐段画，每段高度 = z + 圆截面；跟画布上已有的东西按高度比，高的在上（能做出交叉的上下压）。
    返回露在最上面的那部分遮罩"""
    r = w * W / 2
    H = np.full((W, W), -1e9)
    A = np.zeros((W, W))
    for i in range(len(pts) - 1):
        ax, ay = pts[i][0] * W, pts[i][1] * W
        bx, by = pts[i + 1][0] * W, pts[i + 1][1] * W
        za, zb = zs[i], zs[i + 1]
        x0 = int(max(0, math.floor(min(ax, bx) - r - 2)))
        x1 = int(min(W, math.ceil(max(ax, bx) + r + 3)))
        y0 = int(max(0, math.floor(min(ay, by) - r - 2)))
        y1 = int(min(W, math.ceil(max(ay, by) + r + 3)))
        if x1 <= x0 or y1 <= y0:
            continue
        Y, X = np.mgrid[y0:y1, x0:x1].astype(float)
        X += 0.5
        Y += 0.5
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy + 1e-9
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
        d = np.hypot(X - ax - t * dx, Y - ay - t * dy)
        prof = np.sqrt(np.clip(1 - (d / r) ** 2, 0, 1))
        val = np.where(d < r, za + (zb - za) * t + 0.35 * hk * prof, -1e9)
        H[y0:y1, x0:x1] = np.maximum(H[y0:y1, x0:x1], val)
        A[y0:y1, x0:x1] = np.maximum(A[y0:y1, x0:x1], np.clip(r - d + 0.5, 0, 1))
    m = H > -1e8
    top = m & ((c.alpha <= 0.5) | (H >= c.h))
    c.h = np.where(top, H, c.h)
    c.mat = np.where(top, c._mat_id(mat), c.mat)
    c.custom = np.where(top, 0.0, c.custom)
    c.gloss = np.where(top, 0.0, c.gloss)
    c.alpha = np.maximum(c.alpha, A)
    return top.astype(float)


def _knot(c, x, y, rgb, s=0.018, h=0.6):
    """绳结：一个鼓包 + 几道缠绕的刻纹"""
    m = c.ellipse(x, y, s * 1.25, s)
    c.add(m, 'cloth', h=h, bevel=s * 0.7, dome=0.5)
    c.tint(m, tuple(int(v * 0.9) for v in rgb), 0.9)
    for k in (-1, 0, 1):
        c.engrave(c.stroke([(x + k * s * 0.6 - s * 0.3, y - s * 0.9), (x + k * s * 0.6 + s * 0.3, y + s * 0.9)], w=0.004) * m, depth=0.07, soft=0.0008)


def _hang_cord(c, attach, kx, ky, rgb, w=0.014, h=0.5, loop=0.045):
    """绳挂：从几个系点各拉一股绳到上面的结（kx, ky），结上再打一个绳圈（圈顶在 ky - 2*loop）"""
    for ax, ay in attach:
        mx, my = ax + (kx - ax) * 0.5, ay + (ky - ay) * 0.5
        bend = 0.012 if ax < kx else -0.012
        c.cord(_cr([(ax, ay), (mx - bend, my), (kx + (ax - kx) * 0.06, ky + 0.004)], 6), rgb=rgb, w=w, h=h)
    lp = [(kx + loop * 0.62 * math.sin(a), ky - loop * (1 - math.cos(a))) for a in np.linspace(0.25, 2 * math.pi - 0.25, 40)]
    c.cord(lp, rgb=rgb, w=w * 0.95, h=h + 0.05)
    _knot(c, kx, ky, rgb, s=w * 1.25, h=h + 0.15)


def _finish(c, hammer=0.014, scratches=60, patina=((58, 52, 44), 0.35)):
    c.hammer(hammer)
    c.scratches(scratches)
    if patina:
        c.patina(patina[0], patina[1])


# ------------------------------------------------------------ 狼魂：狼头侧影黑铁牌，蓝石眼，挂环
def dr_wolf(out):
    c = Canvas(501)
    # 侧影（朝左）：钝吻、嘴微张露一颗獠牙、两只耳朵、颈后一圈乱毛
    pts = [(0.088, 0.548), (0.092, 0.515), (0.115, 0.497), (0.2, 0.474), (0.3, 0.452), (0.365, 0.428),
           (0.415, 0.375), (0.455, 0.322), (0.48, 0.265), (0.5, 0.18), (0.518, 0.115), (0.55, 0.165),
           (0.59, 0.235), (0.625, 0.285),
           (0.65, 0.245), (0.68, 0.165), (0.705, 0.125), (0.725, 0.2), (0.745, 0.3),
           (0.79, 0.365), (0.83, 0.45), (0.855, 0.54), (0.825, 0.555), (0.88, 0.64), (0.82, 0.655), (0.865, 0.76),
           (0.795, 0.735), (0.795, 0.85), (0.73, 0.78), (0.675, 0.88), (0.64, 0.775), (0.57, 0.83), (0.55, 0.725),
           (0.49, 0.745), (0.455, 0.69), (0.39, 0.675), (0.31, 0.665), (0.23, 0.655), (0.17, 0.64), (0.13, 0.628),
           (0.115, 0.612), (0.31, 0.613), (0.094, 0.585)]
    head = c.poly(pts)
    c.add(head, 'darkiron', h=0.0, bevel=0.03, dome=0.3)
    inner = _erode(head, 0.016)
    c.relief(np.clip(head - inner, 0, 1), h=0.14, soft=0.002, mat='iron')
    c.engrave(c.ring_mask_edge(inner, 0.004), depth=0.07)
    # 大块的起伏：吻部一道隆起、颊上鼓起、眼窝凹下
    c.relief(c.stroke(_cr([(0.13, 0.52), (0.24, 0.5), (0.34, 0.475)], 6), w=0.05, wfn=lambda u: 1 - 0.3 * u) * inner, h=0.1, soft=0.012)
    c.relief(c.ellipse(0.58, 0.52, 0.13, 0.14) * inner, h=0.14, soft=0.03)
    c.engrave(c.ellipse(0.43, 0.455, 0.045, 0.034), depth=0.1, soft=0.01)
    # 耳窝
    ear = c.poly([(0.498, 0.285), (0.522, 0.17), (0.585, 0.275)])
    c.engrave(ear, depth=0.12, soft=0.003)
    c.hatch(ear, angle=1.2, gap=0.013, depth=0.04)
    c.engrave(c.poly([(0.668, 0.27), (0.702, 0.17), (0.726, 0.29)]), depth=0.1, soft=0.003)
    # 眉弓、眼尾、鼻、嘴、颊线
    c.relief(c.stroke(_cr([(0.37, 0.442), (0.41, 0.418), (0.46, 0.417), (0.5, 0.435)], 6), w=0.016), h=0.12, soft=0.003)
    c.engrave(c.stroke([(0.455, 0.46), (0.505, 0.478), (0.545, 0.473)], w=0.007, wfn=lambda u: 1 - 0.7 * u), depth=0.1)
    nose = c.ellipse(0.106, 0.535, 0.028, 0.026)
    c.add(nose, 'darkiron', h=0.45, bevel=0.012, dome=0.4)
    c.engrave(c.ellipse(0.098, 0.548, 0.008, 0.006), depth=0.12)
    c.engrave(c.stroke(_cr([(0.17, 0.525), (0.27, 0.497), (0.36, 0.472)], 6), w=0.005), depth=0.05)
    c.engrave(c.stroke(_cr([(0.36, 0.52), (0.42, 0.565), (0.455, 0.625), (0.47, 0.69)], 6), w=0.008), depth=0.1)
    # 獠牙（骨色）
    c.add(c.poly([(0.145, 0.594), (0.18, 0.598), (0.158, 0.648)]), 'bone', h=0.35, bevel=0.008)
    c.add(c.poly([(0.235, 0.604), (0.255, 0.606), (0.243, 0.628)]), 'bone', h=0.35, bevel=0.006)
    # 颈毛：凸起的毛簇，旁边一道刻缝
    deep = _erode(head, 0.03)
    n = 0
    while n < 26:
        x, y = c.rng.uniform(0.5, 0.84), c.rng.uniform(0.36, 0.82)
        if deep[int(y * W), int(x * W)] < 0.5 or (x < 0.56 and y < 0.62):
            continue
        a = math.atan2(0.8, 0.45) + c.rng.normal(0, 0.22) - 0.45 * (y < 0.5)
        L = c.rng.uniform(0.06, 0.1)
        b = c.rng.normal(0, 0.3)
        sp = [(x + L * u * math.cos(a + b * u), y + L * u * math.sin(a + b * u)) for u in np.linspace(0, 1, 8)]
        c.relief(c.stroke(sp, w=0.016, wfn=lambda u: 1 - 0.85 * u) * deep, h=0.07, soft=0.004)
        sp2 = [(px + 0.009 * math.cos(a + 1.57), py + 0.009 * math.sin(a + 1.57)) for px, py in sp]
        c.engrave(c.stroke(sp2, w=0.005, wfn=lambda u: 1 - 0.8 * u) * deep, depth=c.rng.uniform(0.06, 0.1), soft=0.0008)
        n += 1
    # 眼：铁圈托一颗蓝石
    c.add(c.circle(0.43, 0.455, 0.026), 'iron', h=0.4, bevel=0.01)
    c.gem(c.circle(0.43, 0.455, 0.018), (52, 96, 150))
    c.glow(c.circle(0.43, 0.455, 0.012), (110, 160, 230), r=0.012, k=0.25)
    c.bail(0.638, 0.2, 'iron', r=0.03, w=0.016, h=0.45, down=0.04)
    _finish(c, 0.014, 70, ((54, 48, 42), 0.35))
    return c.save(out, chip=0.7, tilt=-4, **DARK)


# ------------------------------------------------------------ 壁垒：塔盾形小铁坠，铆钉 + 横箍，链子挂
def dr_bulwark(out):
    c = Canvas(502)
    cx, x0, x1, yt, yb = 0.5, 0.32, 0.68, 0.24, 0.9
    rx = (x1 - x0) / 2
    arc = [(cx + rx * math.cos(a), yt + 0.085 + 0.095 * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 40)]
    shield = c.poly([(x0 + 0.03, yb - 0.012), (x0 + 0.004, yb - 0.06)] + arc + [(x1 - 0.004, yb - 0.06), (x1 - 0.03, yb - 0.012), (cx, yb + 0.018)])
    c.add(shield, 'iron', h=0.0, bevel=0.025)
    xx, yy = _grid()
    c.h += 0.3 * np.sqrt(np.clip(1 - ((xx - cx) / (rx + 0.01)) ** 2, 0, 1)) * (shield > 0.5)
    inner = _erode(shield, 0.026)
    c.relief(np.clip(shield - inner, 0, 1), h=0.16, soft=0.002, mat='bronze')
    c.engrave(c.ring_mask_edge(inner, 0.005), depth=0.08)
    # 盾面几道横纹（铁板的接缝）
    for y in (0.35, 0.53, 0.62, 0.8):
        c.engrave(c.stroke([(x0 + 0.03, y), (x1 - 0.03, y + 0.004)], w=0.005) * inner, depth=0.07)
    # 中间一道竖脊
    spine = c.stroke([(cx, yt + 0.03), (cx, yb - 0.02)], w=0.026) * inner
    c.relief(spine, h=0.12, soft=0.004, mat='darkiron')
    c.engrave(c.ring_mask_edge(spine, 0.004), depth=0.05)
    # 两道凸起的铁箍，上面一排铆钉
    for y in (0.425, 0.735):
        band = c.poly([(x0 + 0.02, y - 0.022), (x1 - 0.02, y - 0.022), (x1 - 0.02, y + 0.022), (x0 + 0.02, y + 0.022)]) * inner
        c.relief(band, h=0.16, soft=0.002, mat='darkiron')
        c.engrave(c.ring_mask_edge(band, 0.004), depth=0.06)
        for x in (x0 + 0.045, x0 + 0.095, x1 - 0.095, x1 - 0.045):
            c.add(c.circle(x, y, 0.011), 'oldgold', h=0.7, bevel=0.008, dome=0.4)
    # 盾心：一个圆凸（盾芯）
    c.add(c.circle(cx, 0.58, 0.058), 'bronze', h=0.55, bevel=0.02, dome=0.6)
    c.engrave(c.ring(cx, 0.58, 0.045, 0.005), depth=0.06)
    c.add(c.circle(cx, 0.58, 0.018), 'oldgold', h=1.0, bevel=0.01, dome=0.5)
    # 边上的铆钉
    for y in np.linspace(yt + 0.12, yb - 0.06, 6):
        for x in (x0 + 0.014, x1 - 0.014):
            c.add(c.circle(x, y, 0.008), 'bronze', h=0.62, bevel=0.006, dome=0.4)
    # 磕痕
    for _ in range(5):
        x, y = c.rng.uniform(x0 + 0.04, x1 - 0.04), c.rng.uniform(yt + 0.1, yb - 0.08)
        c.engrave(c.circle(x, y, c.rng.uniform(0.01, 0.02)) * inner, depth=0.06, soft=0.006)
    # 顶上的耳 + 链子 + 挂环
    c.add(c.ring(cx, yt - 0.012, 0.02, 0.013), 'iron', h=0.55, bevel=0.006)
    c.chain((cx, yt - 0.04), (cx, 0.13), 'iron', link=0.046, w=0.012, h=0.5)
    c.bail(cx, 0.1, 'iron', r=0.027, w=0.014, h=0.55, down=0.0)
    _finish(c, 0.016, 80, ((72, 50, 34), 0.4))
    return c.save(out, chip=0.7, tilt=7, **DARK)


# ------------------------------------------------------------ 反震：小铜钟，钟腰一圈震纹，挂环
def dr_recoil(out):
    c = Canvas(503)
    cx, yt, yl = 0.5, 0.33, 0.73

    def hw(y):
        s = np.clip((y - yt) / (yl - yt), 0, 1)
        return 0.115 + 0.05 * s + 0.12 * s ** 3

    k_e = 0.17                                       # 横截面椭圆的扁度（稍微从上往下看）
    ys = np.linspace(yt, yl, 60)
    body = c.poly([(cx - hw(y), y) for y in ys] + [(cx + hw(y), y) for y in ys[::-1]])
    body = np.clip(body + c.ellipse(cx, yl, hw(yl), hw(yl) * k_e) + c.ellipse(cx, yt, hw(yt), 0.075), 0, 1)
    # 钟舌（在钟后面，从口下面露出来）
    c.add(c.circle(cx, yl + hw(yl) * k_e + 0.026, 0.04), 'iron', h=0.0, bevel=0.03, dome=0.6)
    c.add(body, 'bronze', h=0.0, bevel=0.05)
    xx, yy = _grid()
    u = (xx - cx) / hw(yy)
    c.h += 0.32 * np.sqrt(np.clip(1 - u ** 2, 0, 1)) * (body > 0.5)

    def band(y0, a0=0.04, a1=math.pi - 0.04, n=50, wave=0.0, waves=7):
        r = hw(y0)
        return [(cx + r * math.cos(a), y0 + r * k_e * math.sin(a) + wave * math.sin(a * waves * 2)) for a in np.linspace(a0, a1, n)]

    for y0 in (0.385, 0.565, 0.645):
        c.relief(c.stroke(band(y0), w=0.013) * body, h=0.09, soft=0.002)
        c.engrave(c.stroke(band(y0 + 0.012), w=0.004) * body, depth=0.05)
    c.engrave(c.stroke(band(0.605, n=120, wave=0.01, waves=6), w=0.006) * body, depth=0.09)       # 震纹
    # 钟口：一道厚唇
    c.add(c.stroke(band(yl - 0.004, a0=-0.05, a1=math.pi + 0.05, n=60), w=0.034), 'bronze', h=0.35, bevel=0.016)
    c.engrave(c.stroke(band(yl - 0.024, n=60), w=0.004) * body, depth=0.05)
    # 顶上的钮 + 挂环
    c.add(c.ellipse(cx, yt - 0.045, 0.05, 0.03), 'bronze', h=0.45, bevel=0.015, dome=0.4)
    c.bail(cx, yt - 0.11, 'bronze', r=0.03, w=0.017, h=0.5, down=0.03)
    # （原来两边有几道表示震动的淡弧，像卡通，2026-11-11 去掉）
    _finish(c, 0.014, 60, ((60, 74, 62), 0.3))
    return c.save(out, chip=0.6, tilt=5, **DARK)


# ------------------------------------------------------------ 不动如山：一块雕成三峰的青黑石（山子），山脚卡在铁箍座里，主峰钻孔穿粗绳
# （2026-11-11 用户：方框里的山「不能是一幅画啊」→ 改成实心石雕，不要框和底板）
def dr_unshaken(out):
    from scipy.spatial import cKDTree
    c = Canvas(504)
    cord_rgb = (100, 46, 34)
    hx, hy, hr = 0.5, 0.3, 0.03                        # 主峰上钻的孔
    kx, ky = 0.5, 0.115                                # 绳结
    # 后面那股绳（从峰顶背后绕上来，被石头挡住一截）
    c.cord(_cr([(0.53, 0.3), (0.528, 0.2), (kx + 0.008, ky + 0.006)], 6), rgb=cord_rgb, w=0.02, h=0.2)
    # 石头外形：三座峰，中间最高；直线段 + 少量抖动 = 凿出来的硬棱
    ctrl = [(0.2, 0.8), (0.19, 0.7), (0.205, 0.61), (0.235, 0.535), (0.265, 0.475), (0.295, 0.43), (0.318, 0.402), (0.342, 0.432),
            (0.372, 0.468), (0.395, 0.49), (0.42, 0.42), (0.445, 0.33), (0.47, 0.25), (0.493, 0.205), (0.508, 0.186), (0.524, 0.208),
            (0.547, 0.25), (0.568, 0.315), (0.59, 0.39), (0.61, 0.44), (0.636, 0.4), (0.668, 0.36), (0.698, 0.328), (0.72, 0.362), (0.752, 0.43),
            (0.78, 0.52), (0.8, 0.62), (0.81, 0.72), (0.8, 0.8)]
    ctrl = [(x + c.rng.normal(0, 0.004), y + c.rng.normal(0, 0.004)) for x, y in ctrl]
    stone = c.poly(_cr(ctrl, 3, closed=True))
    c.add(stone, 'stone', h=0.0, bevel=0.1, dome=0.4)
    # 每座峰单独隆起成一道山脊（中峰最靠前），峰与峰之间的鞍部压低
    for (px, py), b0, b1, hh in (((0.318, 0.402), 0.17, 0.46, 0.26), ((0.508, 0.186), 0.33, 0.68, 0.4), ((0.698, 0.328), 0.54, 0.83, 0.3)):
        tri = c.poly([(px, py - 0.03), (b1, 0.84), (b0, 0.84)])
        dist = ndimage.distance_transform_edt(tri > 0.5) / W
        c.h += hh * np.clip(dist / 0.07, 0, 1) * (stone > 0.5)
    for pts in ([(0.395, 0.49), (0.415, 0.6), (0.4, 0.74)], [(0.61, 0.44), (0.592, 0.57), (0.612, 0.72)]):
        c.engrave(c.stroke(_cr(pts, 6), w=0.012, wfn=lambda u: 1 - 0.5 * u) * stone, depth=0.1, soft=0.006)
    # 凿面：石面分成很多小块，每块一个随机斜面（刀凿的平面）
    xx, yy = _grid()
    ys, xs = np.nonzero(stone > 0.5)
    pick = c.rng.integers(0, len(xs), 40)
    seeds = np.stack([xs[pick] / W, ys[pick] / W], 1)
    _, idx = cKDTree(seeds).query(np.stack([xx.ravel(), yy.ravel()], 1))
    idx = idx.reshape(W, W)
    slope = c.rng.normal(0, 0.55, (len(seeds), 2))
    facet = (slope[idx, 0] * (xx - seeds[idx, 0]) + slope[idx, 1] * (yy - seeds[idx, 1]))
    c.h += _blur(facet, 0.003) * (stone > 0.5)
    # 岩层：断断续续、略斜的横向刻线
    deep = _erode(stone, 0.02)
    for _ in range(16):
        x, y = c.rng.uniform(0.22, 0.72), c.rng.uniform(0.3, 0.74)
        if deep[int(y * W), int(x * W)] < 0.5:
            continue
        L, sl, ph = c.rng.uniform(0.06, 0.16), c.rng.normal(0, 0.15), c.rng.uniform(0, 6)
        sp = [(x + L * u, y + sl * L * u + 0.006 * math.sin(u * 7 + ph)) for u in np.linspace(0, 1, 12)]
        c.engrave(c.stroke(sp, w=0.005, wfn=lambda u: math.sin(math.pi * u) ** 0.5) * deep, depth=0.07, soft=0.001)
    # 几棵小松（凸起的三层小尖，刻一道轮廓）
    for px, py, s in ((0.345, 0.52, 1.0), (0.585, 0.5, 0.9), (0.66, 0.44, 0.85), (0.27, 0.6, 0.8), (0.455, 0.56, 0.8)):
        tree = c.stroke([(px, py + 0.012 * s), (px, py + 0.03 * s)], w=0.006)
        for k in range(3):
            ty, tw = py - 0.022 * s + k * 0.013 * s, (0.008 + 0.006 * k) * s
            tree = np.maximum(tree, c.poly([(px, ty - 0.012 * s), (px + tw, ty + 0.01 * s), (px - tw, ty + 0.01 * s)]))
        c.emboss(tree * deep, h=0.08, line=0.003, depth=0.05, soft=0.002)
    # 颜色：青黑石，深浅斑驳
    mix = np.clip(c._noise(0.02) * 0.8 + 0.5, 0, 1)[..., None]
    col = np.array([44, 56, 50], float)[None, None, :] * (1 - mix) + np.array([72, 88, 76], float)[None, None, :] * mix
    c.color = np.where(stone[..., None] > 0.5, col, c.color)
    c.custom = np.maximum(c.custom, stone * 0.92)
    c.gloss = np.maximum(c.gloss, stone * 0.25)
    # 钻孔：真的透空，孔口一圈倒角
    c.engrave(c.ring(hx, hy, hr + 0.008, 0.016) * stone, depth=0.12, soft=0.004)
    hole = c.circle(hx, hy, hr)
    c.alpha = np.where(hole > 0.5, 0.0, c.alpha)
    c.h = np.where(hole > 0.5, 0.0, c.h)
    # 铁箍座：一道厚铁箍卡住山脚，两边各一片铁爪往上扣住石头，一排铆钉
    for s in (-1, 1):
        x = 0.5 + s * 0.255
        claw = c.poly([(x - 0.032, 0.77), (x + 0.032, 0.77), (x + 0.02 * (1 - s) / 2 - 0.004, 0.665), (x - 0.02 * (1 + s) / 2 + 0.004, 0.665)])
        c.add(claw, 'iron', h=0.55, bevel=0.012)
        c.add(c.circle(x, 0.72, 0.011), 'oldgold', h=0.75, bevel=0.007, dome=0.4)
    band = c.poly([(0.175, 0.75), (0.825, 0.75), (0.85, 0.88), (0.15, 0.88)])
    c.add(band, 'iron', h=0.45, bevel=0.02)
    c.h += 0.18 * np.sqrt(np.clip(1 - ((xx - 0.5) / 0.36) ** 2, 0, 1)) * (band > 0.5)
    for y, x0, x1 in ((0.758, 0.18, 0.82), (0.872, 0.155, 0.845)):
        c.relief(c.stroke([(x0, y), (x1, y)], w=0.016) * band, h=0.1, soft=0.002)
    for x in np.linspace(0.24, 0.76, 6):
        c.add(c.circle(x, 0.815, 0.012), 'oldgold', h=0.85, bevel=0.008, dome=0.4)
    # 前面那股绳：石头吊在绳上，绳压在孔的上沿，孔下半露空；往上到结，结上一个绳圈
    c.cord(_cr([(hx - 0.004, hy - hr * 0.45), (0.493, 0.225), (kx - 0.006, ky + 0.006)], 6), rgb=cord_rgb, w=0.019, h=1.0)
    lp = [(kx + 0.05 * 0.62 * math.sin(a), ky - 0.05 * (1 - math.cos(a))) for a in np.linspace(0.3, 2 * math.pi - 0.3, 40)]
    c.cord(lp, rgb=cord_rgb, w=0.018, h=1.0)
    _knot(c, kx, ky, cord_rgb, s=0.024, h=1.1)
    _finish(c, 0.012, 50, ((48, 56, 46), 0.3))
    return c.save(out, chip=0.9, tilt=-3, **DARK)


# ------------------------------------------------------------ 泡盾：空心水晶球，银丝网兜着，链子挂
def dr_bubble(out):
    c = Canvas(505)
    cx, cy, R = 0.5, 0.575, 0.25
    tilt = 0.32
    sph = c.circle(cx, cy, R)
    c.add(sph, 'glass', h=0.0, bevel=R, dome=0.9)
    xx, yy = _grid()
    rr = np.clip(np.hypot(xx - cx, yy - cy) / R, 0, 1)
    ang = np.arctan2(yy - cy, xx - cx)
    fres = rr ** 2.5
    col = np.array([46, 58, 66], float)[None, None, :] * (1 - fres[..., None]) + np.array([150, 166, 174], float)[None, None, :] * fres[..., None]
    swirl = c._noise(0.03) * 0.25
    hue = (ang / (2 * math.pi) * 2 + rr * 1.3 + swirl)
    rain = np.dstack([0.5 + 0.5 * np.cos(2 * math.pi * (hue + k)) for k in (0.0, -1 / 3, -2 / 3)]) * 190
    film = (np.clip((rr - 0.45) / 0.3, 0, 1) * np.clip((1.0 - rr) / 0.06, 0, 1) * 0.5
            + np.clip(c._noise(0.025), 0, 1) * 0.25 * (rr < 0.9))
    col = col * (1 - film[..., None]) + rain * film[..., None]
    c.color = np.where(sph[..., None] > 0.5, col, c.color)
    c.custom = np.maximum(c.custom, sph)
    c.gloss = np.maximum(c.gloss, sph * 0.8)
    # 高光窗 + 背面的折光（空心球：对面内壁亮一道月牙）
    hl = _blur(c.ellipse(cx - R * 0.4, cy - R * 0.44, R * 0.24, R * 0.13), 0.01)
    c.emit += hl[..., None] * np.array([0.42, 0.45, 0.48])[None, None, :]
    c.emit += c.circle(cx - R * 0.5, cy - R * 0.5, 0.01, soft=0.003)[..., None] * 0.75
    cres = _blur(np.clip(c.circle(cx, cy, R * 0.9) - c.circle(cx - R * 0.12, cy - R * 0.14, R * 0.86), 0, 1), 0.008) * sph
    c.emit += cres[..., None] * np.array([0.26, 0.3, 0.3])[None, None, :]
    edge = _blur(c.ring(cx, cy, R * 0.965, 0.008), 0.003) * sph
    c.emit += edge[..., None] * np.array([0.16, 0.18, 0.2])[None, None, :]

    def P(lat, lon):
        x = math.cos(lat) * math.sin(lon)
        y = math.sin(lat)
        z = math.cos(lat) * math.cos(lon)
        y2 = y * math.cos(tilt) + z * math.sin(tilt)
        z2 = -y * math.sin(tilt) + z * math.cos(tilt)
        return cx + R * x, cy + R * y2, z2

    N = 9
    dl = 2 * math.pi / N
    lats = [math.radians(a) for a in (-62, -36, -12, 12, 36, 58, 78)]
    edges = []
    for k in range(len(lats) - 1):
        for j in range(N):
            lon = j * dl + (k % 2) * dl / 2           # 菱形网眼：每个结往下连两个相邻的结
            tg = [j * dl + dl / 2, j * dl - dl / 2] if k % 2 == 0 else [j * dl, j * dl + dl]
            for lon2 in tg:
                edges.append([(lats[k] + (lats[k + 1] - lats[k]) * u, lon + (lon2 - lon) * u) for u in np.linspace(0, 1, 9)])
    for j in range(N):                                # 顶上收口：从银箍到第一排结
        lon = j * dl
        edges.append([(math.radians(-74) + (lats[0] - math.radians(-74)) * u, lon) for u in np.linspace(0, 1, 5)])
        lon = j * dl + ((len(lats) - 1) % 2) * dl / 2   # 底下收到底心
        edges.append([(lats[-1] + (math.radians(89) - lats[-1]) * u, lon) for u in np.linspace(0, 1, 5)])
    back = np.zeros((W, W))
    fronts = []
    for e in edges:
        pp = [P(a, b) for a, b in e]
        seg = []
        for x, y, z in pp:
            if z >= 0:
                seg.append((x, y))
            else:
                if len(seg) > 1:
                    fronts.append(seg)
                seg = []
        if len(seg) > 1:
            fronts.append(seg)
        bk = [(x, y) for x, y, z in pp if z < 0.05]
        if len(bk) > 1:
            back = np.maximum(back, c.stroke(bk, w=0.006))
    # 背面的网线：隔着玻璃看见（暗一点、没有高度）
    c.tint(back * sph, (70, 74, 78), 0.55)
    for seg in fronts:
        zs = [c.h[min(W - 1, int(y * W)), min(W - 1, int(x * W))] + 0.06 for x, y in seg]
        _tube(c, seg, zs, 0.009, 'silver', hk=0.6)
    # 前面的结
    for k, lat in enumerate(lats):
        for j in range(N):
            x, y, z = P(lat, j * dl + (k % 2) * dl / 2)
            if z > 0.1:
                m = c.circle(x, y, 0.0085)
                c.add(m, 'silver', h=c.h[int(y * W), int(x * W)] + 0.05, bevel=0.006, dome=0.4)
    # 顶上的银箍 + 小帽 + 链子
    capc = P(math.radians(-90), 0)
    ring_pts = [P(math.radians(-74), a)[:2] for a in np.linspace(-math.pi / 2 - 0.2, math.pi / 2 + 0.2, 30)]
    c.add(c.ellipse(capc[0], capc[1] - 0.004, 0.07, 0.034), 'silver', h=0.75, bevel=0.016, dome=0.5)
    c.add(c.stroke(ring_pts, w=0.02), 'silver', h=0.85, bevel=0.009)
    for a in np.linspace(-1.2, 1.2, 7):
        x, y, z = P(math.radians(-74), a)
        c.add(c.circle(x, y, 0.007), 'silver', h=1.0, bevel=0.005, dome=0.4)
    c.add(c.ellipse(capc[0], capc[1] - 0.03, 0.026, 0.02), 'silver', h=1.0, bevel=0.012, dome=0.5)
    c.chain((capc[0], capc[1] - 0.035), (capc[0], 0.12), 'silver', link=0.042, w=0.01, h=0.8)
    c.bail(capc[0], 0.09, 'silver', r=0.026, w=0.013, h=0.85, down=0.0)
    c.hammer(0.006)
    c.scratches(40)
    # 玻璃：中间透一点底
    net = np.isin(c.mat, [c._mat_id('silver')])
    see = (sph > 0.5) & ~net
    c.alpha = np.where(see, c.alpha * (1 - 0.38 * (1 - rr ** 2)), c.alpha)
    return c.save(out, chip=0.3, tilt=0, **DARK)


# ------------------------------------------------------------ 混沌：扭曲纠缠的铁丝结，中间一颗暗紫石，绳挂
def dr_chaos(out):
    c = Canvas(506)
    cx, cy = 0.5, 0.57
    # 中间的暗紫石（铁丝从它前后穿过）
    c.add(c.circle(cx, cy, 0.058), 'iron', h=0.25, bevel=0.012, dome=0.2)
    c.gem(c.circle(cx, cy, 0.044), (66, 34, 86))
    c.glow(c.circle(cx, cy, 0.03), (140, 80, 180), r=0.02, k=0.22)

    def wire(p, q, R, r, rot, wob, n=900):
        ts = np.linspace(0, 2 * math.pi, n)
        x = (R + r * np.cos(q * ts)) * np.cos(p * ts)
        y = (R + r * np.cos(q * ts)) * np.sin(p * ts)
        z = r * np.sin(q * ts)
        for k in range(2, 6):
            a, ph = c.rng.normal(0, wob / k), c.rng.uniform(0, 2 * math.pi, 3)
            x = x + a * np.cos(k * ts + ph[0])
            y = y + a * np.sin(k * ts + ph[1])
            z = z + a * np.sin(k * ts + ph[2])
        ax, ay, az = rot
        y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
        x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
        x, y = x * math.cos(az) - y * math.sin(az), x * math.sin(az) + y * math.cos(az)
        return [(cx + a, cy + b) for a, b in zip(x, y)], list(0.42 + z * 4.5)

    tops = []
    for (p, q, R, r, rot, wob, mat, w) in ((2, 3, 0.15, 0.085, (0.5, 0.2, 0.3), 0.045, 'iron', 0.018),
                                           (3, 2, 0.17, 0.06, (-0.4, 0.35, 1.2), 0.05, 'iron', 0.015),
                                           (2, 5, 0.2, 0.05, (0.3, -0.5, 2.1), 0.06, 'iron', 0.013)):
        pts, zs = wire(p, q, R, r, rot, wob)
        _tube(c, pts, zs, w, mat)
        tops.append(min(pts, key=lambda v: v[1]))
    tx, ty = min(tops, key=lambda v: v[1])
    _hang_cord(c, [(tx - 0.018, ty + 0.012), (tx + 0.018, ty + 0.012)], tx, ty - 0.07, (92, 52, 44), w=0.014, h=0.9)
    _finish(c, 0.012, 50, ((70, 48, 36), 0.35))
    return c.save(out, chip=0.3, tilt=0, **DARK)


# ------------------------------------------------------------ 狂乱共鸣：倒挂的铜音叉，两齿之间夹一颗狂乱黄石，挂环
def dr_resonance(out):
    c = Canvas(507)
    cx, yk, rr, tw, ye = 0.5, 0.42, 0.125, 0.058, 0.9
    # 柄 + 柄头圆球
    c.add(c.stroke([(cx, 0.15), (cx, yk - rr + 0.01)], w=0.034), 'oldgold', h=0.0, bevel=0.016)
    c.add(c.circle(cx, 0.15, 0.03), 'oldgold', h=0.05, bevel=0.03, dome=0.5)
    fork = [(cx - rr, ye), (cx - rr, yk)] + c.arc(cx, yk, rr, math.pi, 2 * math.pi, 40) + [(cx + rr, yk), (cx + rr, ye)]
    c.add(c.stroke(fork, w=tw), 'oldgold', h=0.0, bevel=tw / 2)
    c.add(c.ellipse(cx, yk - rr - 0.012, 0.03, 0.018), 'oldgold', h=0.35, bevel=0.012, dome=0.4)
    for s in (-1, 1):                                   # 齿上的刻线
        c.engrave(c.stroke([(cx + s * rr, yk + 0.02), (cx + s * rr, ye - 0.03)], w=0.006), depth=0.06)
        for y in (0.48, 0.5):
            c.engrave(c.stroke([(cx + s * rr - tw * 0.45, y), (cx + s * rr + tw * 0.45, y)], w=0.005), depth=0.07)
    for y in (0.2, 0.22, 0.24):
        c.engrave(c.stroke([(cx - 0.02, y), (cx + 0.02, y)], w=0.004), depth=0.06)
    # 夹石：两根横爪 + 托 + 石
    gy = 0.665
    for s in (-1, 1):
        c.add(c.stroke([(cx + s * (rr - 0.005), gy), (cx + s * 0.05, gy)], w=0.024), 'oldgold', h=0.3, bevel=0.009)
    c.add(c.ellipse(cx, gy, 0.07, 0.09), 'oldgold', h=0.35, bevel=0.014)
    gm = c.ellipse(cx, gy, 0.055, 0.074)
    c.gem(gm, (170, 128, 26))
    slit = c.ellipse(cx, gy, 0.009, 0.042)
    c.tint(slit, (58, 34, 8), 0.9)
    c.glow(c.ellipse(cx, gy, 0.035, 0.05), (240, 190, 60), r=0.025, k=0.3)
    # （原来两边有几道表示震动的淡弧，像卡通，2026-11-11 去掉）
    c.bail(cx, 0.08, 'oldgold', r=0.026, w=0.014, h=0.4, down=0.03)
    _finish(c, 0.013, 60, ((52, 46, 36), 0.35))
    return c.save(out, chip=0.6, tilt=-8, **DARK)


# ------------------------------------------------------------ 疫病：镂空铜熏球，孔里冒淡绿烟，链子挂
def dr_pestilence(out):
    c = Canvas(508)
    cx, cy, R = 0.5, 0.58, 0.245
    tilt = 0.35
    ball = c.circle(cx, cy, R)
    c.add(ball, 'bronze', h=0.0, bevel=R, dome=0.8)

    def P(lat, lon):
        x = math.cos(lat) * math.sin(lon)
        y = math.sin(lat)
        z = math.cos(lat) * math.cos(lon)
        return cx + R * x, cy + R * (y * math.cos(tilt) + z * math.sin(tilt)), -y * math.sin(tilt) + z * math.cos(tilt)

    def shape(lat0, lon0, uv):
        """球面上的一个小图形（uv 是以 (lat0, lon0) 为中心的角度坐标），投影到画面"""
        return c.poly([P(lat0 + v, lon0 + u / max(0.25, math.cos(lat0)))[:2] for u, v in uv])

    def petal(th, d, a, b, n=18):
        return [(d * math.cos(th) + a * math.cos(t) * math.cos(th) - b * math.sin(t) * math.sin(th),
                 d * math.sin(th) + a * math.cos(t) * math.sin(th) + b * math.sin(t) * math.cos(th)) for t in np.linspace(0, 2 * math.pi, n)]

    # 镂空纹：四瓣花（花心留一颗凸点）+ 花与花之间的小圆孔
    holes = np.zeros((W, W))
    hearts = []
    for lat, step, off in ((-46, 50, 0), (-18, 46, 23), (20, 46, 0), (48, 50, 25)):
        for lon in range(-180 + off, 180, step):
            la, lo = math.radians(lat), math.radians(lon)
            if P(la, lo)[2] < 0.12:
                continue
            for k in range(4):
                holes = np.maximum(holes, shape(la, lo, petal(math.pi / 4 + k * math.pi / 2, 0.1, 0.068, 0.034)))
            hearts.append(P(la, lo))
            la2, lo2 = la + math.radians(14 if lat < 0 else -14), lo + math.radians(step / 2)
            if P(la2, lo2)[2] > 0.15:
                holes = np.maximum(holes, shape(la2, lo2, [(0.032 * math.cos(t), 0.032 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 14)]))
    # 上盖一圈小孔
    for lon in range(-180, 180, 30):
        la, lo = math.radians(-70), math.radians(lon)
        if P(la, lo)[2] > 0.1:
            holes = np.maximum(holes, shape(la, lo, [(0.07 * math.cos(t), 0.035 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 14)]))
    holes = holes * ball
    c.engrave(holes, depth=0.3, soft=0.002)
    c.tint(holes, (14, 12, 10), 0.95)
    for x, y, z in hearts:
        c.relief(c.circle(x, y, 0.009 * math.sqrt(z)), h=0.12, soft=0.002)
    lid = [P(math.radians(-60), a)[:2] for a in np.linspace(-math.pi / 2 - 0.3, math.pi / 2 + 0.3, 40)]
    c.relief(c.stroke(lid, w=0.012) * ball, h=0.08, soft=0.002)
    c.engrave(c.stroke([(x, y + 0.008) for x, y in lid], w=0.004) * ball, depth=0.05)
    # 有几个孔里透一点绿
    lit = holes * _blur(c.rng.random((W, W)) > 0.9997, 0.03)
    lit = lit / (lit.max() + 1e-9)
    c.emit += np.clip(lit * 1.5, 0, 1)[..., None] * np.array([0.08, 0.16, 0.05])[None, None, :]
    # 腰线（上下两半合起来的缝）+ 一排小钉
    eq = [P(0, a)[:2] for a in np.linspace(-math.pi / 2 - 0.1, math.pi / 2 + 0.1, 50)]
    c.add(c.stroke(eq, w=0.03) * ball, 'oldgold', h=0.62, bevel=0.012)
    c.engrave(c.stroke(eq, w=0.004) * ball, depth=0.06)
    for a in np.linspace(-1.3, 1.3, 9):
        x, y, z = P(0, a)
        c.add(c.circle(x, y, 0.008), 'oldgold', h=0.95, bevel=0.006, dome=0.3)
    # 顶：盖钮 + 链子
    tx, ty, _ = P(-math.pi / 2, 0)
    c.add(c.ellipse(tx, ty, 0.07, 0.035), 'bronze', h=0.7, bevel=0.015, dome=0.4)
    c.add(c.ellipse(tx, ty - 0.03, 0.022, 0.03), 'oldgold', h=0.9, bevel=0.012, dome=0.5)
    c.chain((tx, ty - 0.06), (tx, 0.11), 'iron', link=0.044, w=0.011, h=0.8)
    c.bail(tx, 0.08, 'iron', r=0.026, w=0.013, h=0.85, down=0.0)
    # 淡绿烟
    for (lat, lon, dx, L, ph) in ((-46, -50, -1, 0.2, 0.0), (-18, 69, 1, 0.24, 1.0), (-46, 50, 1, 0.17, 2.0), (-70, -30, -1, 0.13, 0.5)):
        x, y, _ = P(math.radians(lat), math.radians(lon))
        sp = [(x + dx * (0.025 * math.sin(u * 5.5 + ph) * u + 0.07 * u * u), y - L * u) for u in np.linspace(0, 1, 30)]
        c.wisp(sp, (112, 150, 86), w=0.04, k=0.2, r=0.026, wfn=lambda u: (0.5 + u) * math.sin(math.pi * min(1, 0.15 + u)) ** 0.5, core=0.0)
        c.wisp(sp, (150, 184, 120), w=0.006, k=0.12, r=0.006, wfn=lambda u: math.sin(math.pi * u) ** 0.8, core=0.0)
        c.glow(c.circle(x, y, 0.02), (110, 150, 80), r=0.015, k=0.12)
    _finish(c, 0.014, 60, ((62, 76, 58), 0.35))
    return c.save(out, chip=0.5, tilt=4, **DARK)


# ------------------------------------------------------------ 连锁：三个互扣的铁环，各镶一颗小石，绳挂
def dr_chain(out):
    c = Canvas(509)
    R, w = 0.15, 0.044
    gc = (0.5, 0.575)
    s = R * 1.12                                         # 圆心距
    rho = s / math.sqrt(3)
    C = [(gc[0] + rho * math.cos(a), gc[1] + rho * math.sin(a)) for a in (-math.pi / 2, math.pi * 5 / 6, math.pi / 6)]
    over = [[], [], []]
    under = [[], [], []]
    for i, j in ((0, 1), (1, 2), (2, 0)):
        (px, py), (qx, qy) = C[i], C[j]
        d = math.hypot(qx - px, qy - py)
        a = d / 2
        hgt = math.sqrt(R * R - a * a)
        mx, my = (px + qx) / 2, (py + qy) / 2
        ux, uy = (qx - px) / d, (qy - py) / d
        I1 = (mx - uy * hgt, my + ux * hgt)
        I2 = (mx + uy * hgt, my - ux * hgt)
        over[i].append(I1)
        under[j].append(I1)
        over[j].append(I2)
        under[i].append(I2)
    for k in range(3):
        ccx, ccy = C[k]
        pts = [(ccx + R * math.cos(t), ccy + R * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 220)]
        zs = []
        for x, y in pts:
            z = 0.3
            for I in over[k]:
                z += 0.35 * math.exp(-((x - I[0]) ** 2 + (y - I[1]) ** 2) / 0.05 ** 2)
            for I in under[k]:
                z -= 0.35 * math.exp(-((x - I[0]) ** 2 + (y - I[1]) ** 2) / 0.05 ** 2)
            zs.append(z)
        _tube(c, pts, zs, w, 'iron', hk=0.8)
    # 每个环朝外的一侧镶一颗石
    gems = ((-math.pi / 2, (78, 118, 46)), (math.pi * 5 / 6, (128, 24, 20)), (math.pi / 6, (104, 150, 178)))
    for k, (a, rgb) in enumerate(gems):
        x, y = C[k][0] + R * math.cos(a), C[k][1] + R * math.sin(a)
        c.add(c.circle(x, y, 0.034), 'oldgold', h=0.7, bevel=0.012)
        c.beads(x, y, 0.028, 10, 0.005, h=0.05)
        c.gem(c.circle(x, y, 0.022), rgb)
    tx, ty = C[0][0], C[0][1] - R
    a1, a2 = -math.pi / 2 - 0.62, -math.pi / 2 + 0.62
    att = [(C[0][0] + R * math.cos(a1), C[0][1] + R * math.sin(a1)), (C[0][0] + R * math.cos(a2), C[0][1] + R * math.sin(a2))]
    _hang_cord(c, att, tx, ty - 0.08, (84, 66, 50), w=0.014, h=0.9)
    _finish(c, 0.02, 80, ((74, 52, 36), 0.45))
    return c.save(out, chip=0.5, tilt=0, **DARK)


# ------------------------------------------------------------
def main():
    os.makedirs(OUT, exist_ok=True)
    from PIL import Image
    keys = [k for k in sys.argv[1:] if k in KEYS] or KEYS
    for k in keys:
        globals()[k](os.path.join(OUT, 'charm_' + k + '.png'))
        print('画好', k)
    ims = []
    for k in KEYS:
        fp = os.path.join(OUT, 'charm_' + k + '.png')
        ims.append(Image.open(fp).convert('RGBA') if os.path.exists(fp) else Image.new('RGBA', (160, 160)))
    sheet = Image.new('RGBA', (160 * len(ims), 160), (40, 36, 30, 255))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, (i * 160, 0))
    sheet.save(os.path.join(OUT, 'sheet_guard.png'))
    sheet.resize((sheet.width * 2, 320), Image.LANCZOS).save(os.path.join(OUT, 'sheet_guard_x2.png'))


if __name__ == '__main__':
    main()
