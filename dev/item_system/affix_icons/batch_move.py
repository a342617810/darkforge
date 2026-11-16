# -*- coding: utf-8 -*-
"""第 4 批：机动空战 / 闪避（设计清单.md「第 4 批」），照 icons_charm.py 的护符画法。
飞鸿 = 青铜鸿雁坠；凌空 = 带小翅膀的铁马刺；坠星 = 铁丝缠的陨铁；浮空 = 如意云头坠；天堑 = 铁条连起的两片黑石崖；
时隙 = 半开盖的铜怀表；碾压 = 流星锤球；见切 = 刻半睁眼的白骨牌；残心 = 鞘里的短刀；影步 = 黑曜石脚印坠。
用法：PYTHONIOENCODING=utf-8 python batch_move.py [键 ...]（不给键就全画）"""
import math
import os
import sys

import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import MATS, Canvas, W, _blur  # noqa: E402
from icons_charm import DARK  # noqa: E402
from icons_obj import _unit  # noqa: E402

OUT = os.path.join(HERE, 'out')
# 本批自用的材质（只在本进程里加，不改 iconkit.py）：黑曜石 = 黑里透一点紫、宽而软的光泽；陨铁 = 带褐的黑铁
MATS.setdefault('obsidian', ((30, 28, 36), (210, 210, 225), 16, 0.8, (8, 8, 10)))
MATS.setdefault('meteor', ((70, 62, 56), (200, 190, 176), 18, 0.5, (16, 13, 11)))
KEYS = ['dr_leap', 'dr_aerial', 'dr_meteor', 'dr_float', 'dr_chasm',
        'dr_timeslip', 'dr_crush', 'dr_mikiri', 'dr_zanshin', 'dr_shadowstep']


# ------------------------------------------------------------ 小工具
def _cr(pts, k=8, closed=False):
    """Catmull-Rom 平滑（closed = 首尾相接）"""
    P = list(pts)
    if closed:
        P = [P[-1]] + P + [P[0], P[1]]
    else:
        P = [P[0]] + P + [P[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, k, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    if not closed:
        out.append(tuple(pts[-1]))
    return out


def _star(cx, cy, r0, r1, n, rot=0.0):
    pts = []
    for i in range(2 * n):
        a = rot + i * math.pi / n
        r = r1 if i % 2 == 0 else r0
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _ell_pts(cx, cy, rx, ry, ang=0.0, n=80):
    return Canvas.rot([(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in np.linspace(0, 2 * math.pi, n, endpoint=False)], cx, cy, ang)


def _overlay(c, m, mat, dh=0.07, hw=0.008):
    """贴在现有表面上的一条（铁丝、箍）：跟着底下的起伏，自己再隆起一个圆截面"""
    e = m > 0.5
    dist = ndimage.distance_transform_edt(e) / W
    prof = np.sin(np.clip(dist / max(hw, 1e-6), 0, 1) * math.pi / 2)
    base = _blur(c.h, 0.006)
    c.h = np.where(e, base + dh * prof, c.h)
    c.mat = np.where(e, c._mat_id(mat), c.mat)
    c.alpha = np.maximum(c.alpha, m)
    c.custom = np.where(e, 0.0, c.custom)
    c.gloss = np.where(e, 0.0, c.gloss)
    return c


def _ticks(c, pts, w, depth=0.05, step=0.8):
    """沿一条线刻斜纹（拧过的铁丝 / 缠绳）"""
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        seg = math.hypot(bx - ax, by - ay)
        if seg < 1e-6:
            continue
        ux, uy = (bx - ax) / seg, (by - ay) / seg
        for t in np.arange(0, seg, w * step):
            cx, cy = ax + ux * t, ay + uy * t
            c.engrave(c.stroke([(cx - uy * w * 0.55 - ux * w * 0.3, cy + ux * w * 0.55 - uy * w * 0.3),
                                (cx + uy * w * 0.55 + ux * w * 0.3, cy - ux * w * 0.55 + uy * w * 0.3)], w=0.0035), depth=depth, soft=0.0008)


def _resample(pts, step):
    """把折线按固定间距重新取点（刻纹用，免得点太密太慢）"""
    out = [pts[0]]
    acc = 0.0
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        seg = math.hypot(bx - ax, by - ay)
        t = step - acc
        while t <= seg:
            out.append((ax + (bx - ax) * t / seg, ay + (by - ay) * t / seg))
            t += step
        acc = (acc + seg) % step
    out.append(pts[-1])
    return out


def _feather_pts(x, y, ang, L, w, n=16, point=False):
    """一根羽毛（根窄、中宽；point = 尖头的飞羽，否则圆头）"""
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux
    left, right = [], []
    for t in np.linspace(0, 1, n):
        hw = w * 0.5 * (0.55 + 0.45 * math.sin(min(1.0, t * 2.2) * math.pi / 2))
        if point and t > 0.55:
            hw *= ((1 - t) / 0.45) ** 0.7
        elif not point and t > 0.68:
            hw *= math.sqrt(max(0.0, 1 - ((t - 0.68) / 0.32) ** 2))
        bx, by = x + ux * L * t, y + uy * L * t
        left.append((bx + px * hw, by + py * hw))
        right.append((bx - px * hw, by - py * hw))
    return left + right[::-1]


def _wing(c, S, Wr, mat, h0, prim=(5, -0.5, 0.05, 0.42, 0.32), sec=(5, 0.25, 0.75, 0.25, 0.17), fw=0.058, edge_w=0.03, cov=1.0):
    """铸出来的一只翅膀：翼角 Wr（上）到肩 S（下）。prim / sec = (根数, 第一根方向, 最后一根方向, 第一根长, 最后一根长)：
    飞羽从翼角呈扇形散开（尖头），次级飞羽沿前臂往肩排（圆头）；根部盖两排覆羽（小圆头羽片），前缘一道圆棱"""
    np_, pa0, pa1, pL0, pL1 = prim
    ns, sa0, sa1, sL0, sL1 = sec

    def arm(u):
        return Wr[0] + (S[0] - Wr[0]) * u, Wr[1] + (S[1] - Wr[1]) * u

    def ang(u):
        return float(np.interp(u, [0, 0.16, 0.3, 0.95], [pa0, pa1, sa0, sa1]))

    feathers = []
    for i in range(ns):                              # 次级飞羽（从肩往翼角排，后画的压在前面）
        v = i / max(1, ns - 1)
        u = 0.95 - 0.65 * v
        feathers.append((u, sa1 + (sa0 - sa1) * v, sL1 + (sL0 - sL1) * v, False))
    for i in range(np_):                             # 飞羽（从里往外）
        v = i / max(1, np_ - 1)
        u = 0.16 * (1 - v)
        feathers.append((u, pa1 + (pa0 - pa1) * v, pL1 + (pL0 - pL1) * v, True))
    allm = np.zeros((W, W))
    hh = h0
    for u, a, L, pt in feathers:
        ax, ay = arm(u)
        m = c.poly(_feather_pts(ax, ay, a, L, fw * (0.92 if pt else 1.0), point=pt))
        c.add(m, mat, h=hh, bevel=0.013, dome=0.12)
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        c.engrave(c.stroke([(ax + ux * L * 0.25 - px * fw * 0.12, ay + uy * L * 0.25 - py * fw * 0.12),
                            (ax + ux * L * 0.9 - px * fw * 0.05, ay + uy * L * 0.9 - py * fw * 0.05)], w=0.0045, wfn=lambda t: 1 - 0.6 * t) * m, depth=0.05)
        for t in np.linspace(0.45, 0.8, 3):          # 羽枝
            bx, by = ax + ux * L * t, ay + uy * L * t
            c.engrave(c.stroke([(bx, by), (bx + px * fw * 0.42 + ux * 0.02, by + py * fw * 0.42 + uy * 0.02)], w=0.0035) * m, depth=0.035)
        allm = np.maximum(allm, m)
        hh += 0.025
    # 覆羽：大覆羽一排、小覆羽一排
    for k, (n, off, Lc, wc) in enumerate(((7, 0.035, 0.1, 0.05), (8, 0.012, 0.06, 0.036))):
        hh += 0.04
        for i in range(n):
            u = 0.03 + 0.9 * (1 - i / (n - 1))
            ax, ay = arm(u)
            a = ang(u)
            ex, ey = ax + math.cos(a) * (off + Lc * 0.4), ay + math.sin(a) * (off + Lc * 0.4)
            m = c.poly(_ell_pts(ex, ey, Lc * 0.5 * cov, wc * 0.5, a, 40))
            c.add(m, mat, h=hh, bevel=0.012, dome=0.25)
            hh += 0.012
    mid = ((S[0] + Wr[0]) / 2 - 0.012, (S[1] + Wr[1]) / 2)
    c.add(c.stroke(_cr([S, mid, Wr], 6), w=edge_w, wfn=lambda t: 1 - 0.3 * t), mat, h=hh + 0.06, bevel=0.014)
    return allm


def _cord_loop(c, x0, y0, x1, y1, top, rgb, w=0.015, h=0.6, knot=True, spread=0.045):
    """从 (x0,y0) 和 (x1,y1) 两个点往上收、在 top 打结、再绕一个小圈的挂绳"""
    kx, ky = (x0 + x1) / 2, top + 0.075
    a = _cr([(x0, y0), (x0 - spread * 0.4, (y0 + ky) / 2), (kx - 0.008, ky)], 6)
    b = _cr([(x1, y1), (x1 + spread * 0.4, (y1 + ky) / 2), (kx + 0.008, ky)], 6)
    loop = _cr([(kx - 0.006, ky), (kx - 0.03, top + 0.035), (kx - 0.022, top + 0.006), (kx, top), (kx + 0.022, top + 0.006),
                (kx + 0.03, top + 0.035), (kx + 0.006, ky)], 5)
    c.cord(_resample(loop, 0.01), rgb=rgb, w=w * 0.9, h=h)
    c.cord(_resample(a, 0.01), rgb=rgb, w=w, h=h + 0.02)
    c.cord(_resample(b, 0.01), rgb=rgb, w=w, h=h + 0.02)
    if knot:
        km = c.ellipse(kx, ky + 0.004, w * 1.3, w * 1.05)
        c.add(km, 'cloth', h=h + 0.1, bevel=w * 0.8, dome=0.4)
        c.tint(km, tuple(int(v * 0.85) for v in rgb), 0.9)
        c.engrave(c.stroke([(kx - w * 1.1, ky + 0.004), (kx + w * 1.1, ky + 0.004)], w=0.0035), depth=0.06)
    return c


def _save_knockout(c, path, holes, **kw):
    """带透雕孔的东西：iconkit 的出图按透明度算「离边多远」来做体积明暗，孔一多，孔与孔之间的中线会显出一道道假棱。
    所以出图时先把孔当实心画（全尺寸、不缩放），再把孔挖掉，最后照 iconkit 的 fit / 缩小 / 锐化做一遍"""
    import iconkit
    from PIL import Image, ImageFilter
    kw = dict(kw)
    fit = kw.pop('fit', 0.0)
    old = iconkit.OUT
    iconkit.OUT = W
    try:
        im = c.render(fit=0.0, **kw)
    finally:
        iconkit.OUT = old
    a = np.asarray(im.getchannel('A'), float) * (1 - np.clip(holes, 0, 1))
    im.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    if fit:
        bb = im.getchannel('A').point(lambda v: 255 if v > 140 else 0).getbbox()
        if bb:
            k = fit * W / max(bb[2] - bb[0], bb[3] - bb[1])
            bx, by = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            im = im.transform((W, W), Image.AFFINE, (1 / k, 0, bx - W / 2 / k, 0, 1 / k, by - W / 2 / k), resample=Image.BICUBIC)
    im = im.resize((old, old), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=1))
    im.save(path)
    return im


# ------------------------------------------------------------ 飞鸿
def dr_leap(path):
    """展翅的鸿雁：青铜铸，侧面飞姿，双翅上扬（远侧那只往右上错开），挂环铸在近侧翼角上"""
    c = Canvas(401)
    M = 'bronze'
    o = 0.06                                          # 整体往下挪，翅尖别出画布

    def Y(pts):
        return [(x, y + o) for x, y in pts]

    _wing(c, (0.6, 0.53 + o), (0.58, 0.2 + o), M, 0.0, prim=(5, -0.82, -0.3, 0.31, 0.26), sec=(4, -0.1, 0.4, 0.2, 0.14), fw=0.052)
    body = c.poly(_cr(Y([(0.27, 0.6), (0.33, 0.68), (0.46, 0.725), (0.62, 0.725), (0.76, 0.69), (0.91, 0.665), (0.8, 0.6),
                         (0.62, 0.56), (0.44, 0.545), (0.32, 0.555)]), 8, closed=True))
    c.add(body, M, h=0.1, bevel=0.06, dome=0.6)
    for k in range(4):                                # 尾羽
        a = -0.25 + 0.17 * k
        c.engrave(c.stroke([(0.8, 0.645 + o), (0.8 + 0.11 * math.cos(a), 0.645 + o + 0.11 * math.sin(a))], w=0.0045) * body, depth=0.06)
    for k in range(3):                                # 胸腹的羽鳞
        y = 0.6 + 0.035 * k + o
        for j in range(5):
            x = 0.34 + 0.06 * j + 0.03 * (k % 2)
            c.engrave(c.stroke(c.arc(x, y - 0.012, 0.022, 0.5, 2.6, 10), w=0.004) * body, depth=0.05)
    neck = c.stroke(_cr(Y([(0.34, 0.6), (0.25, 0.555), (0.18, 0.505), (0.125, 0.47)]), 8), w=0.066, wfn=lambda u: 1 - 0.42 * u)
    c.add(np.clip(neck - body, 0, 1), M, h=0.1, bevel=0.03, dome=0.25)
    for k in range(2):
        x = 0.27 + 0.025 * k
        c.engrave(c.stroke(Y([(x - 0.012, 0.535 - 0.012 * k), (x + 0.018, 0.59 - 0.012 * k)]), w=0.0045) * neck, depth=0.06)
    head = c.ellipse(0.115, 0.462 + o, 0.047, 0.035)
    c.add(head, M, h=0.16, bevel=0.03, dome=0.3)
    beak = c.poly(_cr(Y([(0.08, 0.446), (0.04, 0.462), (0.016, 0.478), (0.022, 0.488), (0.05, 0.486), (0.085, 0.484)]), 4))
    c.add(beak, 'oldgold', h=0.2, bevel=0.012)
    c.engrave(c.stroke(Y([(0.082, 0.47), (0.03, 0.481)]), w=0.0035), depth=0.05)
    c.gem(c.circle(0.112, 0.452 + o, 0.0095), (46, 30, 18))
    _wing(c, (0.5, 0.585 + o), (0.43, 0.2 + o), M, 0.3, prim=(5, -0.4, 0.08, 0.42, 0.33), sec=(5, 0.3, 0.85, 0.27, 0.18), edge_w=0.038)
    c.bail(0.43, 0.125 + o, M, r=0.03, w=0.015, h=1.2, down=0.035)
    c.hammer(0.014)
    c.scratches(60)
    c.patina((64, 74, 60), 0.4, scale=0.012, thr=0.5)
    return c.save(path, chip=0.6, tilt=4, **DARK)


# ------------------------------------------------------------ 凌空
def dr_aerial(path):
    """带一对小翅膀的铁马刺：U 形踵带（斜上方看）、往后伸的颈、星形转轮；踵带上长一只银翅膀，挂链"""
    c = Canvas(402)
    cx, cy, rx, ry = 0.36, 0.52, 0.22, 0.11
    # 星轮（在颈后面）
    hx, hy = 0.765, 0.6
    star = c.poly(_star(hx, hy, 0.045, 0.135, 8, 0.2))
    c.add(star, 'iron', h=0.1, bevel=0.03, profile='ridge')
    c.engrave(c.ring_mask_edge(c.circle(hx, hy, 0.05), 0.004), depth=0.06)
    # 远侧踵带（上半圈）
    far = [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in np.linspace(-math.radians(152), 0.05, 40)]
    c.add(c.stroke(far, w=0.036), 'iron', h=0.1, bevel=0.014, profile='flat')
    # 颈：从踵后往星轮
    neck = c.stroke(_cr([(cx + rx - 0.01, cy + 0.005), (0.66, 0.56), (hx, hy)], 6), w=0.04, wfn=lambda u: 1 - 0.35 * u)
    c.add(neck, 'iron', h=0.35, bevel=0.016)
    c.add(c.circle(hx, hy, 0.03), 'oldgold', h=0.5, bevel=0.012, dome=0.4)
    c.add(c.circle(hx, hy, 0.012), 'iron', h=0.7, bevel=0.006)
    # 近侧踵带（下半圈）
    near = [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in np.linspace(-0.05, math.radians(152), 40)]
    nm = c.stroke(near, w=0.044)
    c.add(nm, 'iron', h=0.3, bevel=0.016, profile='flat')
    c.engrave(c.stroke([(cx + rx * 0.93 * math.cos(a), cy + ry * 0.93 * math.sin(a)) for a in np.linspace(0.3, 2.4, 30)], w=0.004) * nm, depth=0.05)
    # 两头的皮带扣钉
    for a, hh in ((-math.radians(152), 0.25), (math.radians(152), 0.45)):
        x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
        c.add(c.circle(x, y, 0.026), 'oldgold', h=hh, bevel=0.012, dome=0.3)
        c.add(c.circle(x, y, 0.01), 'iron', h=hh + 0.25, bevel=0.006)
    # 翅膀：踵带右上方伸出，往后上扬
    _wing(c, (0.53, 0.45), (0.47, 0.25), 'silver', 0.45, prim=(4, -0.75, -0.2, 0.27, 0.21), sec=(3, 0.0, 0.45, 0.16, 0.12), fw=0.05, edge_w=0.026, cov=0.85)
    c.add(c.circle(0.53, 0.45, 0.024), 'oldgold', h=0.95, bevel=0.01, dome=0.3)
    # 链子：从远侧扣钉往上
    x0, y0 = cx + rx * math.cos(-math.radians(152)), cy + ry * math.sin(-math.radians(152))
    c.chain((x0, y0 - 0.02), (x0 + 0.03, 0.14), 'iron', link=0.045, w=0.01, h=0.6)
    c.bail(x0 + 0.032, 0.105, 'iron', r=0.026, w=0.013, h=0.65, down=0.0)
    c.hammer(0.013)
    c.scratches(60)
    c.patina((58, 50, 42), 0.35)
    return c.save(path, chip=0.6, **DARK)


# ------------------------------------------------------------ 坠星
def dr_meteor(path):
    """黑色陨铁块：表面一个个指印坑、亮的金属斑，铁丝十字缠住、顶上拧成挂圈；下沿（坠落的迎风面）烧着暗火"""
    c = Canvas(403)
    cx, cy, rx, ry = 0.5, 0.58, 0.25, 0.28
    pts = []
    p1, p2 = c.rng.uniform(0, 6.3, 2)
    for i in range(18):
        a = i / 18 * 2 * math.pi
        r = 1 + 0.1 * math.cos(3 * a + p1) + 0.05 * math.cos(5 * a + p2) + c.rng.normal(0, 0.025)
        pts.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a)))
    pts = Canvas.rot(pts, cx, cy, 0.35)
    lump = c.poly(_cr(pts, 8, closed=True))
    c.add(lump, 'meteor', h=0.0, bevel=0.1, dome=0.7)
    inside = lump > 0.5
    c.h += 0.14 * c._noise(0.03) * inside              # 大块的起伏
    ys, xs = np.nonzero(ndimage.binary_erosion(inside, iterations=int(0.02 * W)))
    for _ in range(44):                               # 指印坑（陨铁表面那种一个挨一个的浅圆坑）
        i = c.rng.integers(0, len(xs))
        c.engrave(c.circle(xs[i] / W, ys[i] / W, c.rng.uniform(0.018, 0.038), soft=0.007) * lump, depth=c.rng.uniform(0.12, 0.22), soft=0.003)
    # 金属斑：凸起处磨出来的亮铁（不规则的小碎块）
    fl = np.clip((c._noise(0.004) - 0.5) * 6, 0, 1) * np.clip((c.h - _blur(c.h, 0.015)) * 14, 0, 1) * inside
    c.tint(fl, (160, 156, 148), 0.9, gloss=0.7)
    # 下沿的余火：裂缝透光 + 迎风面发红
    yy = np.mgrid[0:W, 0:W][0] / W
    hot = lump * np.clip((yy - 0.66) / 0.18, 0, 1)
    c.cracks(hot * (hot > 0.25), (230, 96, 34), n=4, k=0.55, w=0.006)
    edge = np.clip(1 - ndimage.distance_transform_edt(inside) / W / 0.05, 0, 1) * inside
    c.emit += (_blur(edge * hot, 0.006))[..., None] * np.array([0.34, 0.09, 0.02])[None, None, :]
    # 银丝笼：三道从顶上分开往下兜住，腰上再绕一圈
    top = np.nonzero(inside[:, int(0.5 * W)])[0].min() / W
    ys_, xs_ = np.nonzero(inside)
    x0_, x1_, y1_ = xs_.min() / W, xs_.max() / W, ys_.max() / W
    my = (top + y1_) / 2
    wires = [_cr([(0.5, top + 0.01), (0.5 - (0.5 - x0_) * 0.55, my - 0.08), (0.5 - (0.5 - x0_) * 0.62, my + 0.08), (0.43, y1_ + 0.01)], 8),
             _cr([(0.5, top + 0.01), (0.5 + (x1_ - 0.5) * 0.55, my - 0.08), (0.5 + (x1_ - 0.5) * 0.62, my + 0.08), (0.57, y1_ + 0.01)], 8),
             _cr([(0.5, top + 0.01), (0.505, my), (0.5, y1_ + 0.01)], 8),
             _cr([(x0_ - 0.01, my - 0.01), (0.35, my + 0.03), (0.5, my + 0.045), (0.65, my + 0.03), (x1_ + 0.01, my - 0.01)], 8)]
    dil = ndimage.binary_dilation(inside, iterations=int(0.012 * W)).astype(float)
    for wp in wires:
        m = c.stroke(wp, w=0.021) * dil
        _overlay(c, m, 'silver', dh=0.1, hw=0.01)
        _ticks(c, _resample(wp, 0.02), 0.021, depth=0.05)
    # 顶上拧起来 + 挂圈
    stem = [(0.5, top + 0.03), (0.5, top - 0.045)]
    c.add(c.stroke(stem, w=0.026), 'silver', h=0.75, bevel=0.012)
    _ticks(c, _resample(stem, 0.01), 0.026, depth=0.07, step=0.6)
    c.add(c.ring(0.5, top - 0.085, 0.037, 0.017), 'silver', h=0.8, bevel=0.008)
    # 两缕往上拖的暗火尾
    for s, (x0, y0), L in ((-1, (0.33, 0.8), 0.32), (1, (0.69, 0.78), 0.2)):
        fp = [(x0 + s * 0.06 * math.sin(u * 1.6) - s * 0.01 * u, y0 - L * u) for u in np.linspace(0, 1, 24)]
        c.wisp(fp, (200, 74, 26), w=0.018, k=0.32, r=0.012, wfn=lambda u: (1 - u) ** 0.8, core=0.35)
    c.hammer(0.016)
    c.scratches(50)
    c.patina((70, 48, 34), 0.3, scale=0.01, thr=0.55)
    return c.save(path, chip=0.9, tilt=-5, **DARK)


# ------------------------------------------------------------ 浮空
def dr_float(path):
    """如意云头：三瓣云（左右两瓣往里卷）+ 下尖，铜铸鎏金，边缘磨亮，顶上穿绳"""
    c = Canvas(404)
    cx, cy = 0.5, 0.55
    shape = np.clip(c.circle(cx - 0.165, cy, 0.15) + c.circle(cx + 0.165, cy, 0.15) + c.circle(cx, cy - 0.13, 0.15)
                    + c.poly([(cx - 0.2, cy + 0.08), (cx + 0.2, cy + 0.08), (cx, cy + 0.29)])
                    + c.circle(cx, cy + 0.03, 0.14), 0, 1)
    # 瓣与瓣之间刻进去（三瓣云），两边云脚往里卷
    for s in (-1, 1):
        shape = np.clip(shape - c.circle(cx + s * 0.15, cy - 0.17, 0.052), 0, 1)
        shape = np.clip(shape - c.circle(cx + s * 0.205, cy + 0.2, 0.07), 0, 1)
    c.add(shape, 'oldgold', h=0.0, bevel=0.035, dome=0.25)
    inner = ndimage.binary_erosion(shape > 0.5, iterations=int(0.028 * W)).astype(float)
    c.engrave(c.ring_mask_edge(inner, 0.006), depth=0.1)
    # 左右两瓣的卷云（双线涡纹）
    for s in (-1, 1):
        sp = Canvas.spiral(cx + s * 0.165, cy + 0.0, 0.012, 0.1, 1.3, start=(math.pi if s < 0 else 0) + 0.3 * s, n=90)
        sp = [(cx + s * 0.165 + (x - cx - s * 0.165) * s, y) for x, y in sp]
        c.emboss(c.stroke(sp, w=0.022, wfn=lambda u: 0.4 + 0.6 * u), h=0.12, line=0.004, depth=0.06)
    # 顶瓣：一颗小如意心
    heart = np.clip(c.circle(cx - 0.03, cy - 0.14, 0.036) + c.circle(cx + 0.03, cy - 0.14, 0.036)
                    + c.poly([(cx - 0.063, cy - 0.128), (cx + 0.063, cy - 0.128), (cx, cy - 0.06)]), 0, 1)
    c.emboss(heart, h=0.14, line=0.004, depth=0.06)
    c.gem(c.circle(cx, cy - 0.13, 0.019), (60, 110, 96))
    # 下尖的三道云纹
    for k in range(3):
        c.engrave(c.stroke(c.arc(cx, cy + 0.15 + 0.032 * k, 0.065 - 0.017 * k, 0.35, math.pi - 0.35, 20), w=0.006), depth=0.07)
    # 穿绳的孔 + 挂绳
    for s in (-1, 1):
        c.engrave(c.circle(cx + s * 0.045, cy - 0.235, 0.012), depth=0.3)
    _cord_loop(c, cx - 0.045, cy - 0.235, cx + 0.045, cy - 0.235, 0.09, (96, 34, 26), w=0.015, h=0.5)
    c.hammer(0.012)
    c.scratches(70)
    c.patina((62, 82, 70), 0.45, scale=0.012, thr=0.5)
    return c.save(path, chip=0.6, **DARK)


# ------------------------------------------------------------ 天堑
def dr_chasm(path):
    """两片尖峭的黑石崖，中间一道深缝，上面一根铁条横跨两边（两头箍住石头），铁条正中挂链"""
    c = Canvas(405)
    gl, gr = 0.45, 0.55                               # 缝的两边
    # 两块悬着的崖：朝缝的一面是直上直下的陡壁，外侧一级级往下，底下断成尖
    shards = [
        ([(0.41, 0.07), (0.44, 0.18), (gl, 0.3), (gl, 0.62), (0.44, 0.72), (0.41, 0.83), (0.36, 0.92), (0.32, 0.85), (0.26, 0.78),
          (0.19, 0.72), (0.12, 0.66), (0.07, 0.57), (0.11, 0.51), (0.16, 0.47), (0.19, 0.39), (0.25, 0.36), (0.29, 0.27), (0.33, 0.24), (0.36, 0.13)], 0.0),
        ([(0.6, 0.04), (0.65, 0.12), (0.68, 0.2), (0.74, 0.23), (0.78, 0.32), (0.84, 0.35), (0.87, 0.44), (0.92, 0.5), (0.93, 0.58), (0.87, 0.66),
          (0.8, 0.73), (0.74, 0.8), (0.68, 0.9), (0.63, 0.86), (0.59, 0.78), (0.56, 0.7), (gr, 0.6), (gr, 0.28), (0.56, 0.16)], 0.0),
        # 前面叠的几片小石
        ([(0.12, 0.62), (0.17, 0.5), (0.24, 0.45), (0.3, 0.52), (0.33, 0.66), (0.27, 0.76), (0.18, 0.7)], 0.45),
        ([(0.3, 0.3), (0.36, 0.2), (0.41, 0.26), (0.43, 0.42), (0.39, 0.56), (0.33, 0.48)], 0.4),
        ([(0.7, 0.32), (0.76, 0.28), (0.83, 0.4), (0.86, 0.55), (0.79, 0.64), (0.72, 0.52)], 0.45),
        ([(0.58, 0.62), (0.64, 0.56), (0.7, 0.66), (0.69, 0.8), (0.64, 0.82), (0.6, 0.74)], 0.4),
    ]
    rock = np.zeros((W, W))
    for pts, h0 in shards:
        jag = []
        for i in range(len(pts)):
            (ax, ay), (bx, by_) = pts[i], pts[(i + 1) % len(pts)]
            jag.append((ax, ay))
            if not (ax == bx and ax in (gl, gr)):
                for u in (0.33, 0.66):
                    jag.append((ax + (bx - ax) * u + c.rng.normal(0, 0.006), ay + (by_ - ay) * u + c.rng.normal(0, 0.006)))
        m = c.poly(jag)
        e = m > 0.5
        dist = ndimage.distance_transform_edt(e) / W
        prof = np.clip(dist / 0.09, 0, 1)                 # 斜面一直斜到中棱，像劈开的石片
        c.h = np.where(e, h0 + 1.0 * prof, c.h)
        c.alpha = np.maximum(c.alpha, m)
        c.mat = np.where(e, c._mat_id('stone'), c.mat)
        rock = np.maximum(rock, m)
    c.tint(rock, (72, 68, 64), 0.85)
    c.hammer(0.05, scale=0.006)
    for k in range(9):                                # 岩层（往外侧斜下）+ 裂纹
        y = 0.16 + 0.08 * k + c.rng.normal(0, 0.015)
        c.engrave(c.stroke([(0.04, y + 0.1 + c.rng.normal(0, 0.01)), (0.25, y + 0.04 + c.rng.normal(0, 0.01)), (gl, y), (gr, y),
                            (0.75, y + 0.05 + c.rng.normal(0, 0.01)), (0.96, y + 0.11)], w=0.0055) * rock, depth=0.1)
    c.cracks(rock, (0, 0, 0), n=5, depth=0.12, k=0.0, w=0.005)
    # 缝里的两面陡壁更暗
    for x0, s in ((gl, -1), (gr, 1)):
        wall = c.poly([(x0, 0.3), (x0 + s * 0.035, 0.3), (x0 + s * 0.035, 0.9), (x0, 0.9)]) * rock
        c.engrave(_blur(wall, 0.008), depth=0.25)
    # 铁条 + 两头的铁箍
    by = 0.4
    bar = c.stroke([(0.2, by + 0.01), (0.5, by), (0.83, by + 0.01)], w=0.034)
    c.add(bar, 'iron', h=1.6, bevel=0.012, profile='flat')
    for x in (0.27, 0.38, 0.62, 0.73):
        c.add(c.circle(x, by + 0.004, 0.012), 'oldgold', h=1.75, bevel=0.006, dome=0.3)
    for x0 in (0.2, 0.83):
        c.add(c.stroke([(x0, by - 0.055), (x0, by + 0.065)], w=0.03), 'iron', h=1.7, bevel=0.012)
    c.add(c.ellipse(0.5, by - 0.014, 0.022, 0.03), 'iron', h=1.8, bevel=0.01)
    c.chain((0.5, by - 0.045), (0.5, 0.12), 'iron', link=0.045, w=0.01, h=1.8)
    c.bail(0.5, 0.09, 'iron', r=0.026, w=0.013, h=1.85, down=0.0)
    c.scratches(40)
    c.patina((52, 50, 46), 0.4)
    return c.save(path, chip=1.0, **DARK)


# ------------------------------------------------------------ 时隙
def dr_timeslip(path):
    """铜怀表：表盖往左翻开一半；骨白表盘、刻度、两根铁指针，分针后面拖着几道淡残影；表冠上挂链 + T 字扣"""
    c = Canvas(406)
    cx, cy, R = 0.53, 0.57, 0.25
    # 翻开的表盖（在左边，斜着看成椭圆，露出内面）
    lx, lrx, lry = cx - R - 0.075, 0.085, 0.235
    lid = c.poly(_ell_pts(lx, cy, lrx, lry, 0.0))
    c.add(lid, 'bronze', h=0.0, bevel=0.02, dome=0.1)
    lin = c.poly(_ell_pts(lx + 0.006, cy, lrx * 0.8, lry * 0.88, 0.0))
    c.engrave(lin, depth=0.12, soft=0.006)
    c.engrave(c.ring_mask_edge(c.poly(_ell_pts(lx + 0.006, cy, lrx * 0.55, lry * 0.65, 0.0)), 0.004), depth=0.05)
    c.add(c.stroke([(cx - R + 0.005, cy - 0.05), (cx - R + 0.005, cy + 0.05)], w=0.026), 'oldgold', h=0.25, bevel=0.01)
    # 表壳 + 表圈
    c.add(c.circle(cx, cy, R), 'bronze', h=0.1, bevel=0.03, dome=0.15)
    c.add(c.ring(cx, cy, R - 0.035, 0.03), 'oldgold', h=0.35, bevel=0.012)
    c.beads(cx, cy, R - 0.012, 40, 0.005, h=0.05)
    # 表盘
    dial = c.circle(cx, cy, R - 0.052)
    c.add(dial, 'bone', h=0.12, bevel=0.01, profile='flat')
    c.tint(dial, (176, 164, 136), 0.8)
    for k in range(12):
        a = k / 12 * 2 * math.pi
        r0 = R - 0.1 if k % 3 == 0 else R - 0.085
        c.engrave(c.stroke([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + (R - 0.065) * math.cos(a), cy + (R - 0.065) * math.sin(a))],
                           w=0.009 if k % 3 == 0 else 0.0055), depth=0.08)
    c.engrave(c.ring_mask_edge(c.circle(cx, cy, R - 0.105), 0.003), depth=0.04)
    # 残影：分针前几刻的位置，越早越淡
    am = -math.pi / 2 + 1.05
    for k, kk in ((1, 0.32), (2, 0.2), (3, 0.11)):
        a = am - 0.32 * k
        c.wisp([(cx, cy), (cx + 0.16 * math.cos(a), cy + 0.16 * math.sin(a))], (170, 200, 220), w=0.012, k=kk, r=0.008,
               wfn=lambda u: 1 - 0.5 * u, core=kk)
    c.wisp(c.arc(cx, cy, 0.135, am - 1.1, am - 0.1, 30), (170, 200, 220), w=0.008, k=0.22, r=0.01, core=0.2)
    # 指针
    ah = -math.pi / 2 - 1.1
    c.add(c.stroke([(cx - 0.02 * math.cos(ah), cy - 0.02 * math.sin(ah)), (cx + 0.1 * math.cos(ah), cy + 0.1 * math.sin(ah))], w=0.016,
                   wfn=lambda u: 1 - 0.6 * u), 'darkiron', h=0.4, bevel=0.006)
    c.add(c.ring(cx + 0.075 * math.cos(ah), cy + 0.075 * math.sin(ah), 0.012, 0.006), 'darkiron', h=0.4, bevel=0.004)
    c.add(c.stroke([(cx - 0.025 * math.cos(am), cy - 0.025 * math.sin(am)), (cx + 0.165 * math.cos(am), cy + 0.165 * math.sin(am))], w=0.012,
                   wfn=lambda u: 1 - 0.7 * u), 'darkiron', h=0.45, bevel=0.005)
    c.add(c.circle(cx, cy, 0.016), 'oldgold', h=0.55, bevel=0.008, dome=0.4)
    # 表冠 + 表环 + 链 + T 字扣
    c.add(c.stroke([(cx, cy - R + 0.01), (cx, cy - R - 0.03)], w=0.036), 'oldgold', h=0.3, bevel=0.01)
    for k in range(4):
        c.engrave(c.stroke([(cx - 0.016 + 0.011 * k, cy - R - 0.026), (cx - 0.016 + 0.011 * k, cy - R + 0.005)], w=0.004), depth=0.05)
    c.add(c.oring(cx, cy - R - 0.065, 0.042, 0.034, 0.014), 'oldgold', h=0.4, bevel=0.007)
    c.chain((cx + 0.01, cy - R - 0.1), (cx + 0.15, 0.08), 'oldgold', link=0.042, w=0.009, h=0.45)
    tb = (cx + 0.165, 0.065)
    c.add(c.stroke([(tb[0] - 0.07, tb[1] - 0.012), (tb[0] + 0.07, tb[1] + 0.012)], w=0.018), 'oldgold', h=0.55, bevel=0.008)
    for s in (-1, 1):
        c.add(c.circle(tb[0] + s * 0.07, tb[1] + s * 0.012, 0.013), 'oldgold', h=0.6, bevel=0.006, dome=0.3)
    c.hammer(0.012)
    c.scratches(70)
    c.patina((56, 66, 54), 0.35, scale=0.012, thr=0.52)
    return c.save(path, chip=0.5, **DARK)


# ------------------------------------------------------------ 碾压
def dr_crush(path):
    """流星锤：铁球一圈尖刺 + 正面几根朝外的刺、腰上一道铆钉箍；顶上的耳挂一小段链子"""
    c = Canvas(407)
    cx, cy, R = 0.5, 0.6, 0.21
    for k in range(1, 10):                            # 轮廓上的刺（在球后面）
        a = -math.pi / 2 + k * 2 * math.pi / 10 + c.rng.normal(0, 0.05)
        L = R + c.rng.uniform(0.09, 0.115)
        ux, uy = math.cos(a), math.sin(a)
        b = R * 0.8
        tri = c.poly([(cx + ux * b - uy * 0.04, cy + uy * b + ux * 0.04), (cx + ux * L, cy + uy * L), (cx + ux * b + uy * 0.04, cy + uy * b - ux * 0.04)])
        c.add(tri, 'iron', h=0.05, bevel=0.03, profile='ridge')
    ball = c.circle(cx, cy, R)
    c.add(ball, 'darkiron', h=0.0, bevel=R, dome=0.5)
    c.tint(ball, (84, 80, 76), 0.6)
    # 腰箍（略往下弯，有立体感）
    belt = c.poly([(cx + R * 1.1 * math.cos(a), cy + 0.03 + 0.04 * math.sin(a) - 0.018) for a in np.linspace(math.pi, 0, 30)]
                  + [(cx + R * 1.1 * math.cos(a), cy + 0.03 + 0.04 * math.sin(a) + 0.018) for a in np.linspace(0, math.pi, 30)]) * ball
    _overlay(c, belt, 'iron', dh=0.08, hw=0.01)
    for a in np.linspace(0.35, math.pi - 0.35, 6):
        x, y = cx + R * 0.98 * math.cos(math.pi - a), cy + 0.03 + 0.04 * math.sin(a)
        c.relief(c.circle(x, y, 0.009) * ball, h=0.05, mat='oldgold')
    # 正面的刺：朝外斜着（透视）
    for k, (rho, a) in enumerate(((0.11, -2.4), (0.12, -0.75), (0.13, 1.0), (0.12, 2.3), (0.0, 0.0))):
        x, y = cx + rho * math.cos(a), cy + rho * math.sin(a) - (0.04 if rho == 0 else 0)
        if rho:
            ux, uy = math.cos(a), math.sin(a)
            tip = (x + ux * 0.08, y + uy * 0.08)
            m = np.clip(c.circle(x, y, 0.032) + c.poly([(x - uy * 0.032, y + ux * 0.032), tip, (x + uy * 0.032, y - ux * 0.032)]), 0, 1)
        else:
            m = c.circle(x, y, 0.036)
        c.add(m, 'iron', h=c.h[int(y * W), int(x * W)] + 0.05, bevel=0.034, profile='ridge' if rho else 'round', dome=0.0 if rho else 0.6)
    # 顶上的耳 + 链 + 挂环
    c.add(c.ellipse(cx, cy - R + 0.005, 0.04, 0.025), 'iron', h=0.5, bevel=0.012, dome=0.3)
    c.add(c.oring(cx, cy - R - 0.03, 0.022, 0.03, 0.012), 'iron', h=0.55, bevel=0.006)
    c.chain((cx, cy - R - 0.06), (cx, 0.13), 'iron', link=0.048, w=0.011, h=0.6)
    c.bail(cx, 0.1, 'iron', r=0.026, w=0.013, h=0.65, down=0.0)
    c.hammer(0.016)
    c.scratches(70)
    c.patina((70, 52, 38), 0.35, scale=0.012, thr=0.5)
    return c.save(path, chip=0.8, **DARK)


# ------------------------------------------------------------ 见切
def dr_mikiri(path):
    """白骨圆牌：正中刻一只半睁的眼（上眼皮压下来），眼周一圈刀痕；顶上穿绳"""
    c = Canvas(408)
    cx, cy, R = 0.5, 0.57, 0.3
    disc = c.circle(cx, cy, R)
    c.add(disc, 'bone', h=0.0, bevel=0.04, dome=0.2)
    c.tint(disc, (188, 170, 132), 0.55)
    c.relief(c.ring(cx, cy, R - 0.025, 0.03), h=0.1)
    c.engrave(c.ring_mask_edge(c.circle(cx, cy, R - 0.042), 0.005), depth=0.08)
    # 眼：上眼皮压到瞳孔中间（半睁），眼缝下沿一道弧
    ex0, ex1 = cx - 0.17, cx + 0.17
    ey = cy + 0.01
    up = [(ex0 + (ex1 - ex0) * u, ey - 0.012 * math.sin(math.pi * u)) for u in np.linspace(0, 1, 30)]
    lo = [(ex0 + (ex1 - ex0) * u, ey + 0.07 * math.sin(math.pi * u) ** 0.85) for u in np.linspace(0, 1, 30)]
    opening = c.poly(up + lo[::-1])
    c.engrave(opening, depth=0.14, soft=0.004)
    iris = c.circle(cx, ey + 0.004, 0.068) * opening
    c.relief(iris, h=0.08)
    c.tint(iris, (112, 92, 66), 0.75)
    c.engrave(c.ring_mask_edge(c.circle(cx, ey + 0.004, 0.068), 0.004) * opening, depth=0.06)
    pupil = c.circle(cx, ey + 0.006, 0.03) * opening
    c.engrave(pupil, depth=0.06)
    c.tint(pupil, (22, 16, 14), 1.0, gloss=0.8)
    # 厚上眼皮（压下来的一条肉棱）+ 眼皮褶 + 眉弓
    lidtop = [(ex0 + (ex1 - ex0) * u, ey - 0.012 * math.sin(math.pi * u) - 0.05 * math.sin(math.pi * u) ** 0.8) for u in np.linspace(0, 1, 30)]
    lid = c.poly(up + lidtop[::-1])
    c.relief(lid, h=0.16, soft=0.005)
    c.engrave(c.stroke(up, w=0.009), depth=0.1)
    c.engrave(c.stroke(lidtop[2:-2], w=0.006), depth=0.08)
    c.engrave(c.stroke(lo, w=0.007), depth=0.08)
    c.engrave(c.stroke([(ex0 + (ex1 - ex0) * u, ey - 0.085 - 0.05 * math.sin(math.pi * u)) for u in np.linspace(0.08, 0.92, 30)], w=0.007,
                       wfn=lambda u: math.sin(math.pi * u) ** 0.5), depth=0.08)
    for s in (-1, 1):                                 # 眼角的尾线
        c.engrave(c.stroke([(cx + s * 0.17, ey + 0.0), (cx + s * 0.215, ey + 0.012)], w=0.007, wfn=lambda u: 1 - 0.7 * u), depth=0.08)
    # 一圈刀痕（深浅、方向都乱）
    n = 15
    for k in range(n):
        a = k / n * 2 * math.pi + c.rng.normal(0, 0.1)
        r = c.rng.uniform(0.2, 0.225)
        L = c.rng.uniform(0.045, 0.075)
        t = a + math.pi / 2 + c.rng.normal(0.6, 0.3)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        c.engrave(c.stroke([(x - L / 2 * math.cos(t), y - L / 2 * math.sin(t)), (x + L / 2 * math.cos(t), y + L / 2 * math.sin(t))], w=0.009,
                           wfn=lambda u: math.sin(math.pi * u) ** 0.5), depth=c.rng.uniform(0.14, 0.22), soft=0.001)
    c.cracks(np.clip(disc - c.circle(cx, cy, 0.17), 0, 1), (0, 0, 0), n=3, depth=0.06, k=0.0, w=0.004)
    # 穿绳孔 + 绳
    for s in (-1, 1):
        c.engrave(c.circle(cx + s * 0.04, cy - R + 0.05, 0.012), depth=0.3)
    _cord_loop(c, cx - 0.04, cy - R + 0.05, cx + 0.04, cy - R + 0.05, 0.1, (58, 44, 34), w=0.015, h=0.5)
    c.hammer(0.012)
    c.scratches(80)
    c.patina((96, 80, 58), 0.35, scale=0.01, thr=0.5)
    return c.save(path, chip=0.8, **DARK)


# ------------------------------------------------------------ 残心
def _braid(c, pts, rgb, w=0.018, h=0.6):
    """编绳：一条软绳 + 人字纹（两个方向的斜纹交替）"""
    m = c.stroke(pts, w=w)
    c.add(m, 'cloth', h=h, bevel=w * 0.5)
    c.tint(m, rgb, 0.9)
    rp = _resample(pts, w * 0.75)
    for i in range(len(rp) - 1):
        (ax, ay), (bx, by) = rp[i], rp[i + 1]
        seg = math.hypot(bx - ax, by - ay)
        if seg < 1e-6:
            continue
        ux, uy = (bx - ax) / seg, (by - ay) / seg
        px, py = -uy, ux
        mx, my = (ax + bx) / 2, (ay + by) / 2
        for s in (1, -1):                              # 一个 V：左右两边各一道斜纹，尖朝前
            c.engrave(c.stroke([(mx + s * px * w * 0.48 - ux * w * 0.3, my + s * py * w * 0.48 - uy * w * 0.3), (mx + ux * w * 0.1, my + uy * w * 0.1)],
                               w=0.0035), depth=0.06, soft=0.0008)
    return m


def dr_zanshin(path):
    """残心：一枚圆铁镡当吊坠——厚铁盘、凸起的亮边（耳），透雕一弯新月和几道浪，正中楔形茎孔、两边小孔；
    编绳从右边小孔穿出、在上面打结挂起；边上一道新砍的亮缺口"""
    c = Canvas(409)
    cx, cy, R = 0.5, 0.57, 0.355
    disc = c.ellipse(cx, cy, R * 0.97, R)
    holes = np.zeros((W, W))
    # 茎孔（上宽下尖的楔形）
    holes = np.maximum(holes, c.poly(_cr([(cx - 0.022, cy - 0.085), (cx + 0.022, cy - 0.085), (cx + 0.016, cy + 0.0), (cx + 0.006, cy + 0.075),
                                          (cx - 0.006, cy + 0.075), (cx - 0.016, cy + 0.0)], 4, closed=True)))
    # 两个小孔：左边圆头长方（小柄孔），右边半月（笄孔）
    holes = np.maximum(holes, c.poly(_cr([(cx - 0.135, cy - 0.04), (cx - 0.105, cy - 0.04), (cx - 0.105, cy + 0.035), (cx - 0.12, cy + 0.045),
                                          (cx - 0.135, cy + 0.035)], 3, closed=True)))
    holes = np.maximum(holes, np.clip(c.ellipse(cx + 0.12, cy, 0.022, 0.042) - c.ellipse(cx + 0.104, cy, 0.012, 0.03), 0, 1))
    # 透雕：左上一弯新月
    moon = np.clip(c.circle(cx - 0.15, cy - 0.165, 0.085) - c.circle(cx - 0.122, cy - 0.183, 0.078), 0, 1)
    holes = np.maximum(holes, moon)
    # 透雕：下半几道卷浪（钩形）
    for (wx, wy, sc, flip) in ((cx - 0.14, cy + 0.18, 1.15, 1), (cx + 0.07, cy + 0.235, 1.0, 1), (cx + 0.205, cy + 0.1, 0.85, -1)):
        crest = [(wx - flip * sc * (0.12 - 0.05 * u), wy + sc * 0.03 * (1 - u)) for u in np.linspace(0, 1, 8)]   # 浪身
        for u in np.linspace(0, 1, 40):                                                                             # 浪头往里卷
            a = math.pi - 1.85 * math.pi * u
            r = sc * (0.06 - 0.038 * u)
            crest.append((wx + flip * r * math.cos(a) - flip * sc * 0.0, wy - r * math.sin(a)))
        holes = np.maximum(holes, c.stroke(crest, w=0.028 * sc, wfn=lambda u: 0.5 + 0.7 * math.sin(math.pi * min(1.0, u * 1.3)) - 0.3 * u))
    body = np.clip(disc - holes, 0, 1)
    # 新砍的缺口（左下边缘一个 V）
    nx, ny = cx + R * 0.97 * math.cos(2.35), cy + R * math.sin(2.35)
    notch = c.poly([(nx + 0.05 * math.cos(2.35) - 0.03, ny + 0.05 * math.sin(2.35) - 0.026), (nx - 0.03 * math.cos(2.35) + 0.004, ny - 0.03 * math.sin(2.35) - 0.006),
                    (nx + 0.05 * math.cos(2.35) + 0.03, ny + 0.05 * math.sin(2.35) + 0.026)])
    body = np.clip(body - notch, 0, 1)
    top = cy - R
    rgb = (98, 50, 40)
    kx, ky = cx + 0.025, top - 0.06
    _braid(c, _cr([(cx - 0.035, top + 0.03), (cx - 0.016, top - 0.025), (kx - 0.012, ky)], 6), rgb, w=0.024, h=0.25)   # 后面那股（先画，被镡挡住）
    c.add(disc, 'darkiron', h=0.0, bevel=0.03, dome=0.1)          # 整块铁盘的厚度按外轮廓算，透雕的孔再单独刻
    c.h = c.h - 0.45 * _blur(holes, 0.002)            # 孔先当实心（出图时再挖掉，见 _save_knockout），孔壁陡一点好打出亮边
    c.custom = np.where(body > 0.5, 0.0, c.custom)
    c.tint(body, (82, 78, 74), 0.6)
    # 耳：一圈凸起的亮边
    rim = np.clip(disc - c.ellipse(cx, cy, R * 0.97 - 0.04, R - 0.04), 0, 1) * (body > 0.5)
    _overlay(c, rim, 'iron', dh=0.22, hw=0.016)
    c.tint(rim, (118, 112, 102), 0.7)
    c.engrave(c.ring_mask_edge(c.ellipse(cx, cy, R * 0.97 - 0.042, R - 0.042), 0.004) * (body > 0.5), depth=0.08)
    # 切羽台（茎孔周围的平台）+ 两道刻线
    seppa = c.ellipse(cx, cy - 0.005, 0.06, 0.125) * (body > 0.5)
    c.relief(seppa, h=0.06, soft=0.003)
    c.engrave(c.ring_mask_edge(c.ellipse(cx, cy - 0.005, 0.06, 0.125), 0.004) * (body > 0.5), depth=0.06)
    # 锤目纹 + 透雕边上一圈暗线
    c.hammer(0.04, scale=0.006)
    holes_edge = ndimage.binary_dilation(holes > 0.5, iterations=int(0.007 * W)) & (body > 0.5)
    c.engrave(holes_edge.astype(float), depth=0.05)
    # 缺口的两壁：亮的新铁
    fresh = ndimage.binary_dilation(notch > 0.5, iterations=int(0.016 * W)) & (body > 0.5)
    fresh = _blur(fresh.astype(float), 0.002)
    c.tint(fresh, (214, 210, 198), 1.0, gloss=1.0)
    c.emit += _blur(fresh, 0.003)[..., None] * np.array([0.08, 0.08, 0.07])[None, None, :]
    c.engrave(c.stroke([(nx + 0.01, ny - 0.01), (nx + 0.075, ny - 0.07)], w=0.004, wfn=lambda u: 1 - u) * (body > 0.5), depth=0.06)
    c.tint(c.stroke([(nx + 0.01, ny - 0.01), (nx + 0.075, ny - 0.07)], w=0.004, wfn=lambda u: 1 - u) * (body > 0.5), (176, 174, 168), 0.8, gloss=0.6)
    # 编绳：从右孔穿出往上，在镡顶上打结；另一股从镡后面绕上来；结上再留一个挂圈
    _braid(c, _cr([(cx + 0.118, cy - 0.025), (cx + 0.112, cy - 0.17), (cx + 0.075, top + 0.03), (kx + 0.012, ky + 0.004)], 8), rgb, w=0.024, h=0.7)
    loop = _cr([(kx - 0.008, ky - 0.004), (kx - 0.042, ky - 0.045), (kx - 0.024, ky - 0.088), (kx + 0.012, ky - 0.095), (kx + 0.042, ky - 0.064),
                (kx + 0.01, ky - 0.006)], 6)
    _braid(c, loop, rgb, w=0.02, h=0.75)
    km = c.ellipse(kx, ky, 0.032, 0.024)
    c.add(km, 'cloth', h=0.95, bevel=0.016, dome=0.4)
    c.tint(km, tuple(int(v * 0.85) for v in rgb), 0.9)
    c.engrave(c.stroke([(kx - 0.02, ky + 0.003), (kx + 0.02, ky - 0.003)], w=0.0035), depth=0.06)
    for s in (-1, 1):                                 # 结下垂的两个短穗头
        c.add(c.stroke([(kx + s * 0.012, ky + 0.014), (kx + s * 0.034, ky + 0.05)], w=0.016, wfn=lambda u: 1 - 0.4 * u), 'cloth', h=0.9, bevel=0.008)
        c.tint(c.stroke([(kx + s * 0.012, ky + 0.014), (kx + s * 0.034, ky + 0.05)], w=0.016), rgb, 0.9)
    c.scratches(70)
    c.patina((70, 50, 36), 0.35, scale=0.012, thr=0.52)
    return _save_knockout(c, path, np.clip(holes + notch, 0, 1), chip=0.6, **DARK)


# ------------------------------------------------------------ 影步
def dr_shadowstep(path):
    """影步：椭圆黑曜石小镜坠——抛光的黑镜面镶在串珠边的银框里，镜里映着一个模糊的暗紫人影（边上一线微光）；
    顶上挂环，一侧拖一缕极淡的影子"""
    c = Canvas(410)
    cx, cy, rx, ry = 0.5, 0.57, 0.235, 0.3
    fw = 0.05
    frame = c.ellipse(cx, cy, rx + fw, ry + fw)
    # 框顶的小托（接挂环）+ 底下一颗小坠
    tab = np.clip(c.circle(cx, cy - ry - fw - 0.012, 0.03) + c.poly([(cx - 0.05, cy - ry - fw + 0.02), (cx + 0.05, cy - ry - fw + 0.02), (cx, cy - ry - fw - 0.04)]), 0, 1)
    drop = c.teardrop(cx, cy + ry + fw + 0.012, 0.022)
    c.add(np.clip(frame + tab + drop, 0, 1), 'silver', h=0.0, bevel=0.02, dome=0.1)
    c.engrave(c.circle(cx, cy - ry - fw - 0.012, 0.011), depth=0.12)
    # 串珠边 + 内外两道棱
    n = 46
    for i in range(n):
        a = i / n * 2 * math.pi
        x, y = cx + (rx + fw * 0.52) * math.cos(a), cy + (ry + fw * 0.52) * math.sin(a)
        c.add(c.circle(x, y, 0.0115), 'silver', h=0.2, bevel=0.0115, dome=0.5)
    for k in (0.08, 0.95):
        c.relief(np.clip(c.ellipse(cx, cy, rx + fw * k + 0.004, ry + fw * k + 0.004) - c.ellipse(cx, cy, rx + fw * k - 0.004, ry + fw * k - 0.004), 0, 1), h=0.08, soft=0.002)
    # 镜面：抛光黑曜石（浅凸面），光从左上来，面上偏亮一点，越往右下越黑
    mirror = c.ellipse(cx, cy, rx, ry)
    c.add(mirror, 'obsidian', h=0.05, bevel=0.03, dome=0.35)
    yy, xx = np.mgrid[0:W, 0:W] / W
    t = np.clip(((xx - cx) / rx * 0.5 + (yy - cy) / ry * 0.7 + 0.6) / 1.3, 0, 1)
    sheen = np.dstack([58 - 38 * t, 54 - 36 * t, 70 - 44 * t])
    c.color = np.where(mirror[..., None] > 0.5, sheen, c.color)
    c.custom = np.maximum(c.custom, mirror)
    c.gloss = np.maximum(c.gloss, 0.5 * mirror)
    # 镜里的人影：头 + 颈 + 肩，模糊，比镜面更暗，边上一线紫光
    hx, hy = cx + 0.035, cy - 0.055
    fig = np.clip(c.poly(_ell_pts(hx, hy, 0.062, 0.08, 0.25)) + c.poly([(hx - 0.03, hy + 0.06), (hx + 0.025, hy + 0.06), (hx + 0.01, hy + 0.11), (hx - 0.04, hy + 0.11)])
                  + c.poly(_ell_pts(hx - 0.03, cy + 0.23, 0.2, 0.15, 0.1)), 0, 1) * mirror
    figb = _blur(fig, 0.014) * mirror
    c.color = c.color * (1 - 0.8 * figb[..., None]) + np.array([10, 6, 16])[None, None, :] * 0.8 * figb[..., None]
    rim_l = np.clip(_blur(fig, 0.006) - _blur(fig, 0.016), 0, 1) * mirror
    rim_l = rim_l * np.clip((hx + 0.04 - xx) / 0.1, 0, 1) * np.clip((cy + 0.2 - yy) / 0.1, 0.0, 1)   # 只有迎光（左上）那一侧有一线微光（头 + 左肩）
    c.emit += (rim_l / (rim_l.max() + 1e-9))[..., None] * np.array([0.09, 0.055, 0.15])[None, None, :]
    # 镜面上一道斜的反光 + 左上一点亮斑
    streak = c.poly([(cx - rx * 0.8, cy - ry * 0.2), (cx - rx * 0.5, cy - ry * 0.72), (cx - rx * 0.34, cy - ry * 0.64), (cx - rx * 0.7, cy - ry * 0.08)]) * mirror
    c.emit += _blur(streak, 0.012)[..., None] * np.array([0.12, 0.12, 0.15])[None, None, :]
    c.emit += _blur(c.ellipse(cx - rx * 0.45, cy - ry * 0.55, 0.018, 0.012), 0.004)[..., None] * np.array([0.25, 0.25, 0.3])[None, None, :]
    # 挂环
    c.bail(cx, cy - ry - fw - 0.065, 'silver', r=0.028, w=0.014, h=0.45, down=0.02)
    # 一缕极淡的影子，从右边拖出去
    fp = [(cx + rx + fw - 0.01 + 0.13 * u, cy + 0.12 - 0.3 * u + 0.03 * math.sin(u * 5)) for u in np.linspace(0, 1, 30)]
    c.wisp(fp, (60, 46, 80), w=0.03, k=0.22, r=0.018, wfn=lambda u: (1 - u) ** 0.8, core=0.0)
    c.hammer(0.006)
    c.scratches(40, mask=(frame - mirror).clip(0, 1))
    c.patina((40, 40, 46), 0.35, scale=0.01, thr=0.5)
    return c.save(path, chip=0.35, **DARK)


# ------------------------------------------------------------
def main():
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    want = [k for k in sys.argv[1:] if k in KEYS] or KEYS
    g = globals()
    for k in want:
        g[k](os.path.join(OUT, 'charm_' + k + '.png'))
        print('画好', k)
    sheet = Image.new('RGBA', (160 * len(KEYS), 160), (40, 36, 30, 255))
    for i, k in enumerate(KEYS):
        f = os.path.join(OUT, 'charm_' + k + '.png')
        if os.path.exists(f):
            sheet.alpha_composite(Image.open(f).convert('RGBA'), (i * 160, 0))
    sheet.save(os.path.join(OUT, 'sheet_move.png'))
    sheet.resize((320 * len(KEYS), 320), Image.LANCZOS).save(os.path.join(OUT, 'sheet_move_x2.png'))


if __name__ == '__main__':
    main()
