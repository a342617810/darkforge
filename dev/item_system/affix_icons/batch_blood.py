# -*- coding: utf-8 -*-
"""第 2 批：反击回血（设计见 设计清单.md「第 2 批」）。画法同 icons_charm.py：每个词条画成一件能戴的护符 / 饰品，压暗、做旧、发光克制。
饮血 = 牛角杯（银口沿，杯口满血溢出，两条链挂到顶环）；反扑 = 铁倒钩（钩尖倒刺带血，红绳穿钩眼做挂绳并缠柄）；
背水 = 断剑尖（断口参差，渗血绷带，穿孔挂环）；绝境 = 骨雕小骷髅（裂缝，眼窝两点暗红，挂绳）；
残躯 = 一排破铁甲片（皮绳串起，挂铁环）；搏命 = 裂纹野猪獠牙（根部铁箍，挂链）；回光 = 小铁灯笼（里面一点将熄的暗金火，挂环）；
血瓮 = 暗红釉小陶瓮（口封蜡，麻绳吊）；血债 = 羊皮卷（细绳扎着，下面吊一枚血红蜡封）；
强韧 = 红色圣杯瓶套铁条笼（挂环）；无敌 = 水晶小瓶里一颗金泪滴（金口，挂链）

用法：PYTHONIOENCODING=utf-8 python batch_blood.py [键 ...]（不给键就全画）"""
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
KEYS = ['dr_blood_drink', 'dr_rally', 'dr_desperate', 'dr_last_stand', 'dr_tattered', 'dr_desperado',
        'dr_last_light', 'dr_blood_urn', 'dr_blood_debt', 'dr_flask_endure', 'dr_physick_ward']


# ---------------------------------------------------------------- 小工具（只在本文件里用）
def spline(pts, n=12):
    """Catmull-Rom：穿过所有控制点的平滑曲线"""
    P = [pts[0]] + list(pts) + [pts[-1]]
    res = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = (np.array(P[j], float) for j in range(i - 1, i + 3))
        for t in np.linspace(0, 1, n, endpoint=False):
            q = 0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3)
            res.append((float(q[0]), float(q[1])))
    res.append((float(pts[-1][0]), float(pts[-1][1])))
    return res


def resample(pts, step):
    """按弧长等距重采样"""
    a = np.array(pts, float)
    seg = np.hypot(*np.diff(a, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.append(np.arange(0, s[-1], step), s[-1])
    return [(float(x), float(y)) for x, y in zip(np.interp(t, s, a[:, 0]), np.interp(t, s, a[:, 1]))]


def frames(pts):
    """每个点：位置、切向、法向"""
    a = np.array(pts, float)
    d = np.gradient(a, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    return a, d, nrm


def at(pts, u):
    a, d, nrm = frames(pts)
    i = int(round(u * (len(a) - 1)))
    return a[i], d[i], nrm[i]


def ribbon(c, pts, wfn, u0=0.0, u1=1.0, extra=0.0):
    """沿中线 pts 的条带遮罩，全宽 wfn(u)；只取 u0~u1 一段；extra = 两边各加宽"""
    a, d, nrm = frames(pts)
    n = len(a)
    L, R = [], []
    for i in range(n):
        u = i / (n - 1)
        if u < u0 - 1e-9 or u > u1 + 1e-9:
            continue
        hw = wfn(u) / 2 + extra
        L.append(tuple(a[i] + nrm[i] * hw))
        R.append(tuple(a[i] - nrm[i] * hw))
    return c.poly(L + R[::-1])


def ufield(pts, wfn=None):
    """每个像素：离中线最近点的 u，以及横向位置 s（给了 wfn 就按半宽归一化，-1~1）"""
    a, d, nrm = frames(pts)
    yy, xx = np.mgrid[0:W, 0:W] / W
    best = np.full((W, W), 9.0)
    idx = np.zeros((W, W), int)
    for i, (x, y) in enumerate(a):
        dd = (xx - x) ** 2 + (yy - y) ** 2
        sel = dd < best
        best[sel] = dd[sel]
        idx[sel] = i
    n = len(a)
    u = idx / (n - 1)
    s = (xx - a[idx, 0]) * nrm[idx, 0] + (yy - a[idx, 1]) * nrm[idx, 1]
    if wfn is not None:
        wv = np.array([wfn(i / (n - 1)) for i in range(n)])
        s = s / (wv[idx] / 2)
    return u, s


def rect(c, x0, y0, x1, y1):
    return c.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def clear(c, mask):
    """新盖上去的东西不继承下面的自定义颜色 / 光泽 / 自发光"""
    m = mask > 0.5
    c.custom = np.where(m, 0, c.custom)
    c.gloss = np.where(m, 0, c.gloss)
    c.emit = np.where(m[..., None], 0, c.emit)


def put(c, mask, mat, h=0.0, bevel=0.02, dome=0.0, profile='round'):
    c.add(mask, mat, h=h, bevel=bevel, dome=dome, profile=profile)
    clear(c, mask)
    return mask


def coat(c, mask, mat, th=0.1, bevel=0.008, smooth=0.006):
    """贴着下面的形状包一层（箍、绷带、溢出的血）：高度 = 下面（柔化后）的高度 + 厚度，边上倒角；可以比下面的轮廓稍宽"""
    m = mask > 0.5
    base = _blur(c.h * (c.alpha > 0.5), smooth)
    dist = ndimage.distance_transform_edt(m) / W
    prof = np.sin(np.clip(dist / bevel, 0, 1) * math.pi / 2)
    c.h = np.where(m, base + th * (0.3 + 0.7 * prof), c.h)
    c.alpha = np.maximum(c.alpha, mask)
    c.mat = np.where(m, c._mat_id(mat), c.mat)
    clear(c, mask)
    return mask


def paint(c, mask, rgb, k=0.9, gloss=0.0):
    """局部上色（软边：和已有的自定义颜色按遮罩混合）"""
    m = np.clip(mask, 0, 1)
    w = np.where(c.custom > 0.05, m, (m > 0.01).astype(float))
    c.color = c.color * (1 - w[..., None]) + np.array(rgb, float)[None, None, :] * w[..., None]
    c.custom = np.maximum(c.custom, k * m)
    c.gloss = np.maximum(c.gloss, gloss * m)


def grad(c, mask, u, stops, k=0.95, gloss=0.0):
    """沿 u 渐变上色"""
    us = [s[0] for s in stops]
    col = np.dstack([np.interp(u, us, [s[1][j] for s in stops]) for j in range(3)])
    sel = (mask > 0.02)[..., None]
    c.color = np.where(sel, col, c.color)
    c.custom = np.maximum(c.custom, k * mask)
    c.gloss = np.maximum(c.gloss, gloss * mask)


def blotch(c, mask, scale=0.012, thr=0.55, sharp=5.0):
    n = c._noise(scale) * 0.5 + 0.5
    return np.clip((n - thr) * sharp, 0, 1) * mask


def crackle(c, mask, n=60, w=0.004, depth=0.03):
    """釉面开片：Voronoi 边"""
    ys, xs = np.nonzero(mask > 0.5)
    idx = c.rng.integers(0, len(xs), n)
    yy, xx = np.mgrid[0:W, 0:W] / W
    d1 = np.full((W, W), 9.0)
    d2 = np.full((W, W), 9.0)
    for i in idx:
        d = np.hypot(xx - xs[i] / W, yy - ys[i] / W)
        d2 = np.minimum(d2, np.maximum(d1, d))
        d1 = np.minimum(d1, d)
    edge = np.clip(1 - (d2 - d1) / w, 0, 1) * mask
    c.engrave(edge, depth=depth, soft=0.0008)
    return edge


def jagged(c, p0, p1, n=10, amp=0.008):
    """两点之间的一道歪扭的裂纹线"""
    pts = [p0]
    for k in range(1, n):
        u = k / n
        pts.append((p0[0] + (p1[0] - p0[0]) * u + c.rng.normal(0, amp), p0[1] + (p1[1] - p0[1]) * u + c.rng.normal(0, amp)))
    pts.append(p1)
    return pts


def knot(c, x, y, rx, ry, rgb, h=0.8):
    """绳结：一团鼓起的绳，上面几道褶"""
    m = c.ellipse(x, y, rx, ry)
    put(c, m, 'cloth', h=h, bevel=min(rx, ry) * 0.8, dome=0.3)
    paint(c, m, rgb, 0.9)
    for k in (-1, 0, 1):
        c.engrave(c.stroke([(x + k * rx * 0.45 - rx * 0.2, y - ry * 0.8), (x + k * rx * 0.45 + rx * 0.2, y + ry * 0.8)], w=0.004) * m, depth=0.06)
    return m


# ---------------------------------------------------------------- 图标
def dr_blood_drink(out):
    """饮血：牛角杯——兽角弯成月牙，银口沿、银箍、银角尖；杯口满着暗红的血，溢出来顺着角身往下淌；两条链从口沿和角尖挂到顶上的环"""
    c = Canvas(201)
    ctr = resample(spline([(0.30, 0.40), (0.315, 0.55), (0.39, 0.69), (0.53, 0.77), (0.68, 0.72), (0.775, 0.57), (0.795, 0.43)], 12), 0.006)
    wf = lambda u: 0.225 * (1 - u) ** 0.95 + 0.022  # noqa: E731
    mx, my = ctr[0]
    rx = wf(0) / 2 + 0.012
    pe, de, ne = at(ctr, 1.0)
    # 两条链 + 顶环 + 口沿、角尖上的小挂耳（在后面先画）
    lug_l = (mx - rx - 0.004, my - 0.012)
    lug_r = (pe[0] + de[0] * 0.05, pe[1] + de[1] * 0.05)
    c.chain((lug_l[0] + 0.006, lug_l[1] - 0.014), (0.47, 0.112), 'iron', link=0.045, w=0.01, h=0.1)
    c.chain((lug_r[0] - 0.004, lug_r[1] - 0.014), (0.53, 0.112), 'iron', link=0.045, w=0.01, h=0.1)
    put(c, c.ring(0.5, 0.083, 0.032, 0.017), 'silver', h=0.3, bevel=0.008)
    for x, y in (lug_l, lug_r):
        put(c, c.ring(x, y, 0.016, 0.01), 'silver', h=0.3, bevel=0.005)
    # 角身：口白、往尖上发褐发黑，打磨过有点光
    horn = ribbon(c, ctr, wf)
    put(c, horn, 'bone', h=0.0, bevel=0.07, dome=0.25)
    uu, ss = ufield(ctr, wf)
    grad(c, horn, uu, [(0, (124, 98, 68)), (0.3, (104, 78, 52)), (0.6, (70, 52, 38)), (0.85, (40, 32, 27)), (1, (30, 25, 22))], k=0.95, gloss=0.35)
    paint(c, blotch(c, horn * (uu > 0.1) * (uu < 0.75), scale=0.02, thr=0.55, sharp=3), (138, 112, 80), 0.6)   # 角里的浅色条斑
    a, d, nrm = frames(ctr)
    n = len(a)
    t = 0.12
    while t < 0.84:                                   # 角上的生长纹（稀、深浅不一）
        i = int(t * (n - 1))
        hw = wf(t) / 2
        bow = d[i] * c.rng.uniform(0.006, 0.02)
        c.engrave(c.stroke([tuple(a[i] + nrm[i] * hw * 1.1), tuple(a[i] + bow), tuple(a[i] - nrm[i] * hw * 1.1)], w=c.rng.uniform(0.0035, 0.005)) * horn,
                  depth=c.rng.uniform(0.02, 0.05), soft=0.0012)
        t += c.rng.uniform(0.05, 0.1)
    for off in (-0.45, 0.1, 0.5):                       # 顺着角的纤维
        line = [tuple(a[i] + nrm[i] * wf(i / (n - 1)) / 2 * off) for i in range(int(0.08 * n), int(0.88 * n))]
        c.engrave(c.stroke(line, w=0.004) * horn, depth=0.025)
    # 银口沿箍、中箍、角尖套 + 尖上的小球
    for u0, u1, th in ((0.0, 0.075, 0.13), (0.40, 0.445, 0.1), (0.86, 1.0, 0.1)):
        band = coat(c, ribbon(c, ctr, wf, u0, u1, extra=0.009), 'silver', th=th)
        c.engrave(c.ring_mask_edge(band, 0.004), depth=0.05)
    pb, db, nb = at(ctr, 0.037)
    for k in np.linspace(-0.75, 0.75, 7):
        coat(c, c.circle(*(pb + nb * wf(0.037) / 2 * k), 0.0075), 'silver', th=0.06, bevel=0.005)
    put(c, c.circle(pe[0] + de[0] * 0.012, pe[1] + de[1] * 0.012, 0.019), 'silver', h=0.55, bevel=0.012, dome=0.3)
    # 杯口：银沿 + 一汪血（略鼓）
    put(c, c.ellipse(mx, my, rx, 0.048), 'silver', h=0.55, bevel=0.014)
    surf = c.ellipse(mx, my + 0.002, rx - 0.017, 0.033)
    put(c, surf, 'blood', h=0.62, bevel=0.012, dome=0.12)
    paint(c, surf, (76, 10, 8), 0.95, gloss=0.7)
    # 溢出来的血：口沿前面一摊，两道顺着角往下淌
    spill = np.maximum(c.ellipse(mx + 0.035, my + 0.036, 0.042, 0.02), c.ellipse(mx - 0.06, my + 0.03, 0.026, 0.014))
    d1 = np.maximum(c.stroke([(mx + 0.045, my + 0.04), (mx + 0.051, my + 0.09), (mx + 0.049, my + 0.13)], w=0.018, wfn=lambda u: 1 - 0.45 * u),
                    c.circle(mx + 0.049, my + 0.137, 0.0125))
    d2 = np.maximum(c.stroke([(mx - 0.066, my + 0.035), (mx - 0.069, my + 0.075)], w=0.014, wfn=lambda u: 1 - 0.4 * u),
                    c.circle(mx - 0.069, my + 0.081, 0.0095))
    bl = np.clip(spill + d1 + d2, 0, 1)
    coat(c, bl, 'blood', th=0.07, bevel=0.01)
    paint(c, bl, (86, 12, 10), 0.95, gloss=0.75)
    c.hammer(0.012)
    c.scratches(60)
    c.patina((52, 50, 46), 0.35, scale=0.012, thr=0.5)
    return c.save(out, chip=0.5, **DARK)


def dr_rally(out):
    """反扑：铁倒钩——鱼钩形，钩尖一根倒刺，钩尖和倒刺沾血；红绳穿过钩眼打结做挂绳，再在钩柄上缠几圈，留一截绳头"""
    c = Canvas(202)
    sx = 0.585
    red = (112, 28, 22)
    ctr = resample(spline([(sx, 0.212), (sx, 0.42), (sx - 0.006, 0.60), (0.552, 0.715), (0.45, 0.772), (0.345, 0.73), (0.298, 0.62),
                           (0.302, 0.52), (0.322, 0.432)], 12), 0.006)
    def wf(u):
        if u < 0.66:
            return 0.06
        if u < 0.965:
            return 0.06 - 0.045 * (u - 0.66) / 0.305
        return 0.014 * (1 - (u - 0.965) / 0.035) + 0.003
    hook = ribbon(c, ctr, wf)
    # 倒刺：在钩尖内侧（朝钩柄那边），尖朝下，和钩身之间留一道缝
    def edge(u, k=0.9):
        p, d_, nn = at(ctr, u)
        inn = nn if nn[0] > 0 else -nn
        return p + inn * wf(u) / 2 * k, inn, d_
    e_hi, inn_hi, _ = edge(0.925)
    e_lo, inn_lo, d_lo = edge(0.845)
    e_tip, inn_tip, d_tip = edge(0.735)
    btip = e_tip + inn_tip * 0.05
    barb = c.poly([tuple(e_hi - inn_hi * 0.012), tuple(e_hi + inn_hi * 0.01), tuple(btip), tuple(e_lo + inn_lo * 0.002)])
    metal = np.clip(hook + barb, 0, 1)
    put(c, metal, 'iron', h=0.0, bevel=0.026)
    c.engrave(c.stroke([tuple(e_hi), tuple(btip)], w=0.004) * barb, depth=0.04)
    # 钩眼
    put(c, c.ring(sx, 0.17, 0.042, 0.025), 'iron', h=0.05, bevel=0.012)
    # 血：钩尖 + 倒刺，边缘破碎；倒刺尖上挂一滴
    uu, ss = ufield(ctr, wf)
    edge_n = c._noise(0.01)
    bmask = np.clip(((uu - 0.86 + 0.05 * edge_n) * 30), 0, 1) * hook
    bmask = np.clip(bmask + barb * c.circle(btip[0], btip[1], 0.04) * np.clip((c._noise(0.006) + 0.3) * 4, 0, 1), 0, 1)
    paint(c, bmask, (98, 16, 12), 0.92, gloss=0.75)
    smear = blotch(c, hook * (uu > 0.55) * (uu < 0.78), scale=0.008, thr=0.62)
    paint(c, smear, (74, 16, 12), 0.75, gloss=0.4)
    drop = c.teardrop(btip[0] + 0.002, btip[1] + 0.022, 0.017)
    put(c, drop, 'blood', h=0.2, bevel=0.012, dome=0.4)
    paint(c, drop, (92, 12, 10), 0.95, gloss=0.9)
    # 挂绳：从钩眼里穿出来，顶上一个绳圈，眼上打结
    loop = spline([(sx - 0.012, 0.172), (sx - 0.022, 0.13), (sx - 0.045, 0.085), (sx - 0.03, 0.038), (sx, 0.026), (sx + 0.03, 0.038),
                   (sx + 0.045, 0.085), (sx + 0.022, 0.13), (sx + 0.012, 0.172)], 8)
    c.cord(resample(loop, 0.022), rgb=red, w=0.017, h=0.45)
    knot(c, sx, 0.128, 0.026, 0.019, red, h=0.6)
    # 柄上缠几圈 + 一截绳头
    for y in np.arange(0.258, 0.37, 0.0185):
        c.cord([(sx - 0.034, y), (sx + 0.034, y + 0.014)], rgb=red, w=0.015, h=0.42)
    tail = spline([(sx + 0.03, 0.372), (sx + 0.058, 0.42), (sx + 0.068, 0.475), (sx + 0.06, 0.525)], 8)
    c.cord(resample(tail, 0.02), rgb=red, w=0.013, h=0.35)
    ex, ey = tail[-1]
    for k in (-1, 0, 1):
        m = c.stroke([(ex, ey), (ex + k * 0.008, ey + 0.022)], w=0.005, wfn=lambda u: 1 - 0.7 * u)
        put(c, m, 'cloth', h=0.3, bevel=0.003)
        paint(c, m, red, 0.9)
    c.hammer(0.016)
    c.scratches(70)
    c.patina((86, 56, 36), 0.5, scale=0.01, thr=0.5)
    return c.save(out, chip=0.6, tilt=-4, **DARK)


def dr_desperate(out):
    """背水：一截断剑尖——断口参差，刃口有豁；中段缠着渗血的绷带，一截绷带头垂下来；断口下钻孔穿一个旧金环"""
    c = Canvas(203)
    put(c, c.ring(0.5, 0.25, 0.05, 0.02), 'oldgold', h=0.1, bevel=0.009)
    brk = [(0.385, 0.33), (0.405, 0.30), (0.43, 0.318), (0.452, 0.278), (0.478, 0.302), (0.5, 0.268), (0.525, 0.296), (0.548, 0.272),
           (0.575, 0.306), (0.598, 0.288), (0.615, 0.315)]
    blade = c.poly(brk + [(0.615, 0.66), (0.60, 0.745), (0.565, 0.835), (0.5, 0.955), (0.435, 0.835), (0.40, 0.745), (0.385, 0.66)])
    for x, y, s in ((0.385, 0.62, 1), (0.615, 0.585, -1), (0.6, 0.735, -1), (0.402, 0.705, 1), (0.615, 0.37, -1)):
        blade = np.clip(blade - c.poly([(x - s * 0.01, y - 0.014), (x + s * 0.017, y + 0.002), (x - s * 0.01, y + 0.012)]), 0, 1)
    put(c, blade, 'steel', h=0.0, bevel=0.115, profile='ridge')
    paint(c, blotch(c, blade, scale=0.01, thr=0.5, sharp=3), (88, 86, 82), 0.6)    # 刃面发乌的斑
    c.engrave(c.stroke([(0.5, 0.37), (0.5, 0.67)], w=0.02, wfn=lambda u: 1 - 0.5 * u), depth=0.07, soft=0.003)
    # 断面：颜色发白、粗糙
    frac = c.poly(brk + [(0.615, 0.345), (0.385, 0.355)]) * blade
    paint(c, frac, (132, 130, 124), 0.55)
    c.h += 0.04 * c._noise(0.002) * frac
    hole = c.circle(0.5, 0.318, 0.016)
    c.engrave(hole, depth=0.25, soft=0.002)
    paint(c, hole, (16, 12, 10), 0.95)
    # 绷带：几道斜着缠，边上起毛
    bandage = np.zeros((W, W))
    for k, y in enumerate((0.405, 0.448, 0.49, 0.532)):
        ang = (0.2 if k % 2 == 0 else -0.14) + c.rng.normal(0, 0.03)
        xs = np.linspace(0.368, 0.632, 14)
        top = [(x, y - 0.024 + c.rng.normal(0, 0.002)) for x in xs]
        bot = [(x, y + 0.024 + c.rng.normal(0, 0.002)) for x in xs[::-1]]
        strip = c.poly(Canvas.rot(top + bot, 0.5, y, ang))
        coat(c, strip, 'cloth', th=0.11, bevel=0.006)
        c.engrave(c.ring_mask_edge(strip, 0.004), depth=0.05)
        for _ in range(3):                              # 布纹褶
            x0 = c.rng.uniform(0.39, 0.6)
            c.engrave(c.stroke(Canvas.rot([(x0, y - 0.012), (x0 + 0.03, y - 0.008)], 0.5, y, ang), w=0.0035) * strip, depth=0.03)
        bandage = np.maximum(bandage, strip)
    tail = ribbon(c, spline([(0.612, 0.515), (0.64, 0.575), (0.658, 0.645), (0.652, 0.715)], 10), lambda u: 0.034 * (1 - 0.25 * u))
    tail = np.clip(tail - c.poly([(0.63, 0.722), (0.643, 0.7), (0.652, 0.718), (0.662, 0.698), (0.675, 0.725)]), 0, 1)
    put(c, tail, 'cloth', h=0.2, bevel=0.008)
    bandage = np.maximum(bandage, tail)
    paint(c, bandage, (146, 136, 112), 0.85)
    # 血从刃口那边渗出来：中间暗红、外圈发褐
    st = _blur(c.circle(0.405, 0.47, 0.05), 0.02) + 0.8 * _blur(c.circle(0.6, 0.43, 0.035), 0.015) + 0.5 * _blur(c.circle(0.655, 0.69, 0.02), 0.01)
    st = st / st.max()
    nz = c._noise(0.008)
    paint(c, np.clip((st + 0.35 * nz - 0.3) * 4, 0, 1) * bandage, (108, 58, 42), 0.85)
    paint(c, np.clip((st + 0.35 * nz - 0.5) * 4, 0, 1) * bandage, (86, 16, 12), 0.92, gloss=0.25)
    trick = np.maximum(c.stroke([(0.545, 0.55), (0.548, 0.6), (0.543, 0.655)], w=0.009, wfn=lambda u: 1 - 0.5 * u), c.circle(0.543, 0.66, 0.007))
    coat(c, trick * blade, 'blood', th=0.03, bevel=0.004)
    paint(c, trick * blade, (80, 12, 10), 0.9, gloss=0.7)
    c.hammer(0.013)
    c.scratches(80)
    c.patina((70, 56, 44), 0.35, scale=0.012, thr=0.5)
    return c.save(out, chip=0.6, tilt=-9, **DARK)


def dr_last_stand(out):
    """绝境：骨雕小骷髅头——头顶钻孔穿皮绳打结挂起，脑壳上一道裂缝，眼窝深处两点暗红"""
    c = Canvas(204)
    cord_c = (92, 66, 46)
    loop = spline([(0.488, 0.235), (0.462, 0.16), (0.47, 0.085), (0.5, 0.06), (0.53, 0.085), (0.538, 0.16), (0.512, 0.235)], 8)
    c.cord(resample(loop, 0.02), rgb=cord_c, w=0.017, h=0.1)
    jaw = c.poly([(0.39, 0.775), (0.61, 0.775), (0.605, 0.85), (0.575, 0.885), (0.425, 0.885), (0.395, 0.85)])
    put(c, jaw, 'bone', h=0.0, bevel=0.03, dome=0.2)
    cran = c.ellipse(0.5, 0.445, 0.215, 0.215)
    face = c.poly([(0.30, 0.48), (0.70, 0.48), (0.69, 0.6), (0.645, 0.69), (0.615, 0.79), (0.385, 0.79), (0.355, 0.69), (0.31, 0.6)])
    cheek = np.maximum(c.ellipse(0.34, 0.615, 0.055, 0.048), c.ellipse(0.66, 0.615, 0.055, 0.048))
    skull = np.clip(cran + face + cheek, 0, 1)
    put(c, skull, 'bone', h=0.05, bevel=0.07, dome=0.55)
    allb = np.clip(skull + jaw, 0, 1)
    paint(c, allb, (122, 106, 80), 0.88)                       # 旧骨头：发黄发暗
    paint(c, blotch(c, allb, scale=0.016, thr=0.52, sharp=3), (90, 76, 56), 0.88)
    paint(c, _blur(c.ring_mask_edge(allb, 0.02), 0.012) * allb, (78, 66, 50), 0.88)
    for s in (-1, 1):                                   # 太阳穴凹进去
        c.engrave(c.ellipse(0.5 + s * 0.2, 0.55, 0.03, 0.06), depth=0.1, soft=0.02)
    # 眼窝（深）+ 眉骨 + 里面两点暗红
    for s in (-1, 1):
        ex, ey = 0.5 + s * 0.088, 0.535
        outline = [(ex + 0.07 * math.cos(t), ey + 0.06 * math.sin(t) * (1.0 if math.sin(t) > 0 else 0.92)) for t in np.linspace(0, 2 * math.pi, 40)]
        sock = c.poly(Canvas.rot(outline, ex, ey, s * 0.18))
        c.relief(c.stroke(c.arc(ex, ey + 0.004, 0.074, math.pi * 1.1, math.pi * 1.9), w=0.022), h=0.07, soft=0.006)
        c.engrave(sock, depth=0.45, soft=0.008)
        paint(c, _blur(sock, 0.004), (26, 20, 16), 0.9)
        pt = c.circle(ex + s * 0.004, ey + 0.01, 0.009)
        c.emit += _blur(pt, 0.004)[..., None] * np.array([0.36, 0.04, 0.03])[None, None, :]
        c.glow(pt, (150, 24, 16), r=0.012, k=0.22)
    nose = c.poly([(0.5, 0.6), (0.53, 0.668), (0.515, 0.684), (0.5, 0.674), (0.485, 0.684), (0.47, 0.668)])
    c.engrave(nose, depth=0.35, soft=0.004)
    paint(c, _blur(nose, 0.003), (28, 22, 18), 0.9)
    # 牙
    c.engrave(c.stroke(spline([(0.385, 0.736), (0.5, 0.728), (0.615, 0.736)], 8), w=0.006), depth=0.08)
    c.engrave(c.stroke([(0.39, 0.79), (0.61, 0.79)], w=0.009), depth=0.16)
    for k in range(9):
        x = 0.398 + k * 0.0255
        c.engrave(c.stroke([(x, 0.74), (x, 0.787)], w=0.0045), depth=0.1)
        if k < 8:
            c.engrave(c.stroke([(x + 0.0128, 0.794), (x + 0.0128, 0.836)], w=0.0045), depth=0.1)
    c.engrave(c.stroke([(0.405, 0.84), (0.595, 0.84)], w=0.005), depth=0.06)
    # 裂缝：头顶往下劈到右眼窝
    cr = jagged(c, (0.535, 0.236), (0.585, 0.478), n=12, amp=0.007)
    crk = c.stroke(cr, w=0.008, wfn=lambda u: 1 - 0.55 * u)
    br = c.stroke(jagged(c, cr[5], (cr[5][0] + 0.05, cr[5][1] + 0.035), n=5, amp=0.004), w=0.005, wfn=lambda u: 1 - 0.7 * u)
    crk = np.maximum(crk, br) * skull
    c.engrave(crk, depth=0.18, soft=0.001)
    paint(c, crk, (34, 26, 20), 0.9)
    # 头顶的孔 + 绳结
    c.engrave(c.circle(0.5, 0.25, 0.014), depth=0.2)
    knot(c, 0.5, 0.236, 0.023, 0.016, cord_c, h=0.85)
    c.hammer(0.011)
    c.scratches(50)
    c.patina((70, 56, 40), 0.45, scale=0.012, thr=0.5)
    return c.save(out, chip=0.5, tilt=3, **dict(DARK, grime=1.2))


def _plate(c, piv, ang, r0, L, wt, wb):
    """一片甲片：顶边窄、底下圆；沿着从 piv 往外的方向挂着。返回遮罩 + 局部坐标 → 画布坐标的函数"""
    dx, dy = math.sin(ang), math.cos(ang)
    px, py = math.cos(ang), -math.sin(ang)
    tx, ty = piv[0] + r0 * dx, piv[1] + r0 * dy
    ch = 0.014
    rb = wb / 2
    yb = L - rb * 0.9
    loc = [(-wt / 2 + ch, 0), (wt / 2 - ch, 0), (wt / 2, ch), (wb / 2, yb)]
    loc += [(rb * math.cos(t), yb + rb * 0.9 * math.sin(t)) for t in np.linspace(0.1, math.pi - 0.1, 18)]
    loc += [(-wb / 2, yb), (-wt / 2, ch)]

    def G(s, v):
        return (tx + s * px + v * dx, ty + s * py + v * dy)
    return c.poly([G(s, v) for s, v in loc]), G


def dr_tattered(out):
    """残躯：五片磨破的铁甲片扇形排开，顶上用一根皮绳穿起来、绳两头穿过一个铁环挂着；缺角、凹坑、锈"""
    c = Canvas(205)
    leather = (86, 62, 42)
    piv = (0.5, -0.12)
    put(c, c.ring(0.5, 0.072, 0.034, 0.018), 'iron', h=0.3, bevel=0.008)
    plates = []
    for k, a0 in enumerate((-0.4, -0.2, 0.0, 0.2, 0.4)):
        ang = a0 + c.rng.normal(0, 0.03)
        L = 0.29 + c.rng.uniform(-0.025, 0.012)
        m, G = _plate(c, piv, ang, 0.46, L, 0.135, 0.165)
        for _ in range(2):                              # 边上磕掉的口
            s = c.rng.choice([-1, 1])
            x, y = G(s * 0.082, c.rng.uniform(0.08, L - 0.07))
            m = np.clip(m - c.circle(x, y, c.rng.uniform(0.009, 0.015)), 0, 1)
        if k == 3:                                      # 一片缺了个角
            m = np.clip(m - c.poly([G(0.0, L + 0.03), G(0.1, L - 0.12), G(0.1, L + 0.03)]), 0, 1)
        if k == 0:
            m = np.clip(m - c.poly([G(-0.1, L - 0.07), G(-0.035, L + 0.02), G(-0.1, L + 0.02)]), 0, 1)
        put(c, m, 'iron', h=0.05, bevel=0.024, dome=0.3)
        c.relief(c.ring_mask_edge(m, 0.012) * m, h=0.05, soft=0.003)          # 卷边
        c.emboss(c.stroke([G(0, 0.07), G(0, L - 0.06)], w=0.02, wfn=lambda u: 1 - 0.4 * u) * m, h=0.07, line=0.003, depth=0.05)
        for s in (-1, 1):
            for v, off in ((0.03, 0.032), (L * 0.6, 0.046)):
                x, y = G(s * off, v)
                hole = c.circle(x, y, 0.0095)
                c.engrave(hole, depth=0.22)
                paint(c, hole, (18, 14, 10), 0.92)
        for _ in range(3):                              # 凹坑
            x, y = G(c.rng.uniform(-0.045, 0.045), c.rng.uniform(0.07, L - 0.04))
            c.engrave(c.circle(x, y, c.rng.uniform(0.01, 0.02)) * m, depth=0.06, soft=0.008)
        if k == 1:                                      # 一道裂
            crk = c.stroke(jagged(c, G(-0.07, L * 0.3), G(-0.012, L * 0.78), n=8, amp=0.005), w=0.006) * m
            c.engrave(crk, depth=0.15, soft=0.001)
            paint(c, crk, (24, 18, 14), 0.85)
        rust = blotch(c, m, scale=0.008, thr=0.58, sharp=4)
        paint(c, rust, (92, 58, 38), 0.7)
        plates.append((L, G))
    # 中段的缝线：相邻两片之间一小截皮绳
    for i in range(4):
        (L0, G0), (L1, G1) = plates[i], plates[i + 1]
        c.cord([G0(0.046, L0 * 0.6), G1(-0.046, L1 * 0.6)], rgb=leather, w=0.014, h=0.75)
    # 顶上穿起来的皮绳：铁环 → 左 → 穿过每片顶上 → 右 → 铁环
    arc = [(piv[0] + 0.49 * math.sin(a), piv[1] + 0.49 * math.cos(a)) for a in np.linspace(-0.42, 0.42, 7)]
    thong = spline([(0.488, 0.074), (0.47, 0.13), (0.4, 0.2), (0.33, 0.275)] + arc + [(0.67, 0.275), (0.6, 0.2), (0.53, 0.13), (0.512, 0.074)], 8)
    c.cord(resample(thong, 0.022), rgb=leather, w=0.02, h=0.7)
    c.hammer(0.016)
    c.scratches(120)
    c.patina((80, 52, 34), 0.3, scale=0.01, thr=0.55)
    return c.save(out, chip=0.9, **dict(DARK, wear=1.1))


def dr_desperado(out):
    """搏命：一颗弯弯的野猪獠牙，牙身一道长裂纹，根部包铁箍（两道箍 + 铆钉），铁箍顶上挂链"""
    c = Canvas(206)
    ctr = resample(spline([(0.64, 0.255), (0.685, 0.42), (0.655, 0.58), (0.545, 0.72), (0.40, 0.785), (0.27, 0.765), (0.185, 0.69)], 12), 0.007)
    wf = lambda u: 0.13 * (1 - u) ** 0.7 + 0.006  # noqa: E731
    p0, d0, n0 = at(ctr, 0.0)
    c.chain((p0[0] - 0.002, p0[1] - 0.05), (0.625, 0.085), 'iron', link=0.045, w=0.011, h=0.1)
    put(c, c.ring(0.623, 0.06, 0.028, 0.015), 'iron', h=0.2, bevel=0.007)
    tusk = ribbon(c, ctr, wf)
    put(c, tusk, 'bone', h=0.0, bevel=0.05, dome=0.35)
    uu, ss = ufield(ctr, wf)
    pm, dm, nm = at(ctr, 0.5)
    sgn = 1 if np.dot(nm, np.array([0.45, 0.5]) - pm) > 0 else -1     # +sgn 那边是弯的内侧
    si = ss * sgn
    grad(c, tusk, uu, [(0, (104, 80, 50)), (0.25, (140, 116, 80)), (0.6, (164, 146, 108)), (1, (178, 164, 132))], k=0.92, gloss=0.15)
    # 外侧一条釉质（更白更亮），尖上内侧磨出的斜面
    paint(c, np.clip((-si - 0.2) * 3, 0, 1) * tusk * (uu > 0.15), (176, 162, 128), 0.9, gloss=0.35)
    paint(c, np.clip((si - 0.1) * 4, 0, 1) * np.clip((uu - 0.74) * 12, 0, 1) * tusk, (190, 178, 148), 0.9, gloss=0.4)
    paint(c, blotch(c, tusk * (uu < 0.7), scale=0.012, thr=0.58, sharp=3), (110, 88, 58), 0.8)      # 发黄的污渍
    a, d, nrm = frames(ctr)
    n = len(a)
    groove = [tuple(a[i] - nrm[i] * sgn * wf(i / (n - 1)) / 2 * 0.25) for i in range(int(0.15 * n), int(0.85 * n))]
    c.engrave(c.stroke(groove, w=0.004) * tusk, depth=0.03)
    # 长裂纹 + 几道横向细纹
    main = [tuple(a[i] + nrm[i] * sgn * wf(i / (n - 1)) / 2 * (0.15 + 0.12 * math.sin(i * 0.4)) + c.rng.normal(0, 0.003, 2))
            for i in range(int(0.16 * n), int(0.64 * n), 3)]
    crk = c.stroke(main, w=0.0075, wfn=lambda u: 1 - 0.6 * u)
    for u0 in (0.3, 0.42, 0.55):
        pc, dc, ncc = at(ctr, u0)
        hw = wf(u0) / 2
        crk = np.maximum(crk, c.stroke(jagged(c, tuple(pc + ncc * hw * 0.2), tuple(pc - ncc * hw * 0.7 + dc * 0.01), n=4, amp=0.003), w=0.004))
    crk = crk * tusk
    c.engrave(crk, depth=0.17, soft=0.001)
    paint(c, crk, (30, 24, 18), 0.9)
    # 根部铁箍：整段包铁 + 两道凸箍 + 两颗铆钉；顶端封口，上面一个小挂耳
    coat(c, ribbon(c, ctr, wf, 0.0, 0.15, extra=0.012), 'iron', th=0.14)
    for u0, u1 in ((0.0, 0.03), (0.12, 0.15)):
        coat(c, ribbon(c, ctr, wf, u0, u1, extra=0.018), 'iron', th=0.1, bevel=0.006)
    for s in (-1, 1):
        pr, dr_, nr = at(ctr, 0.075)
        coat(c, c.circle(*(pr + nr * s * wf(0.075) / 2 * 0.55), 0.011), 'iron', th=0.1, bevel=0.007)
    cap = c.ellipse(p0[0], p0[1], wf(0) / 2 + 0.014, 0.028)
    put(c, cap, 'iron', h=0.5, bevel=0.014, dome=0.3)
    put(c, c.ring(p0[0] - 0.002, p0[1] - 0.04, 0.016, 0.011), 'iron', h=0.55, bevel=0.005)
    c.hammer(0.012)
    c.scratches(60)
    c.patina((84, 56, 38), 0.4, scale=0.01, thr=0.5)
    return c.save(out, chip=0.6, **DARK)


def dr_last_light(out):
    """回光：小铁灯笼——铜顶铜底、铁框，三面暗玻璃，里面一截残烛，一点将熄的暗金火；顶上挂环，底下一个尖坠"""
    c = Canvas(207)
    cx = 0.5
    c.bail(cx, 0.098, 'iron', r=0.03, w=0.016, h=0.6, down=0.035)
    roof = c.poly([(0.474, 0.17), (0.526, 0.17), (0.66, 0.29), (0.34, 0.29)])
    put(c, roof, 'bronze', h=0.15, bevel=0.035, dome=0.15)
    for x in (0.38, 0.44, 0.5, 0.56, 0.62):
        c.relief(c.stroke([(cx + (x - cx) * 0.15, 0.178), (x, 0.284)], w=0.007) * roof, h=0.05, soft=0.002)
    put(c, c.circle(cx, 0.168, 0.026), 'bronze', h=0.45, bevel=0.012, dome=0.3)
    put(c, c.poly([(0.315, 0.283), (0.685, 0.283), (0.67, 0.318), (0.33, 0.318)]), 'bronze', h=0.25, bevel=0.01)
    # 里面：暗玻璃 + 残烛 + 火
    inside = rect(c, 0.36, 0.318, 0.64, 0.675)
    put(c, inside, 'darkiron', h=0.0, bevel=0.006)
    paint(c, inside, (30, 25, 19), 0.95, gloss=0.5)
    candle = np.maximum(rect(c, 0.474, 0.628, 0.526, 0.675), c.ellipse(cx, 0.628, 0.026, 0.008))
    put(c, candle, 'bone', h=0.08, bevel=0.012)
    paint(c, candle, (92, 80, 62), 0.85)
    puddle = c.ellipse(cx, 0.668, 0.05, 0.01)
    put(c, puddle, 'bone', h=0.06, bevel=0.006)
    paint(c, puddle, (86, 74, 56), 0.85)
    drip = c.stroke([(0.479, 0.63), (0.477, 0.66)], w=0.009, wfn=lambda u: 1 - 0.3 * u)
    coat(c, drip * inside, 'bone', th=0.05, bevel=0.004)
    paint(c, drip * inside, (100, 88, 68), 0.85)
    put(c, c.stroke([(cx, 0.628), (cx + 0.003, 0.612)], w=0.0055), 'darkiron', h=0.3, bevel=0.002)
    flame = c.teardrop(cx + 0.002, 0.592, 0.021)
    c.emit += np.clip(_blur(flame, 0.004) * 1.2, 0, 1)[..., None] * np.array([0.62, 0.4, 0.11])[None, None, :]
    c.emit += _blur(c.teardrop(cx + 0.002, 0.6, 0.009), 0.003)[..., None] * np.array([0.3, 0.24, 0.12])[None, None, :]
    c.glow(flame, (190, 125, 45), r=0.03, k=0.32)
    lit = _blur(c.circle(cx, 0.6, 0.05), 0.035) * inside
    c.emit += lit[..., None] * np.array([0.16, 0.09, 0.025])[None, None, :]
    smoke = [(cx + 0.003 + 0.01 * math.sin(u * 7), 0.575 - u * 0.12) for u in np.linspace(0, 1, 20)]
    c.wisp(smoke, (90, 86, 80), w=0.008, k=0.18, r=0.006, core=0.0)
    # 铁框：四根立柱（两边宽、中间窄，像斜着看到三面）+ 上下横档 + 一道中档
    for x, w in ((0.36, 0.03), (0.432, 0.02), (0.568, 0.02), (0.64, 0.03)):
        put(c, rect(c, x - w / 2, 0.31, x + w / 2, 0.685), 'iron', h=0.3, bevel=0.008)
    for y0, y1 in ((0.312, 0.338), (0.655, 0.685)):
        put(c, rect(c, 0.345, y0, 0.655, y1), 'iron', h=0.36, bevel=0.009)
    put(c, rect(c, 0.36, 0.452, 0.64, 0.464), 'iron', h=0.33, bevel=0.005)
    for x in (0.36, 0.432, 0.568, 0.64):                # 铆钉
        for y in (0.325, 0.67):
            put(c, c.circle(x, y, 0.0075), 'iron', h=0.6, bevel=0.005, dome=0.2)
    # 火光照到立柱内侧一点点
    glowmask = _blur(c.circle(cx, 0.6, 0.08), 0.02) * (rect(c, 0.4, 0.46, 0.6, 0.66) > 0.5)
    c.emit += (glowmask * 0.08)[..., None] * np.array([1.0, 0.6, 0.2])[None, None, :]
    # 底座 + 尖坠
    put(c, c.poly([(0.33, 0.682), (0.67, 0.682), (0.655, 0.718), (0.345, 0.718)]), 'bronze', h=0.3, bevel=0.01)
    put(c, c.poly([(0.415, 0.714), (0.585, 0.714), (0.54, 0.775), (0.5, 0.835), (0.46, 0.775)]), 'bronze', h=0.2, bevel=0.02, dome=0.2)
    c.hammer(0.012)
    c.scratches(60)
    c.patina((64, 72, 60), 0.3, scale=0.01, thr=0.55)
    return c.save(out, chip=0.5, tilt=4, **DARK)


def dr_blood_urn(out):
    """血瓮：小陶瓮——上半挂暗红釉（釉往下流出几道舌头，下半露素胎）、釉面开片；瓮口封一团旧蜡；麻绳在颈上缠两道、提成一个吊环"""
    c = Canvas(208)
    cx = 0.5
    hemp = (128, 106, 72)
    # 瓮身：宽肩、往下收成小底（侧影用半宽曲线左右对称拼出来）
    prof_pts = spline([(0.405, 0.105), (0.43, 0.175), (0.47, 0.215), (0.53, 0.224), (0.6, 0.214), (0.68, 0.186), (0.76, 0.142), (0.815, 0.106)], 10)
    body = c.poly([(cx + w, y) for y, w in prof_pts] + [(cx - w, y) for y, w in prof_pts[::-1]])
    put(c, body, 'stone', h=0.0, bevel=0.15, dome=0.45)
    foot = c.poly([(0.405, 0.8), (0.595, 0.8), (0.608, 0.842), (0.392, 0.842)])
    put(c, foot, 'stone', h=0.1, bevel=0.01)
    neck = rect(c, 0.418, 0.33, 0.582, 0.425)
    put(c, neck, 'stone', h=0.28, bevel=0.035)
    lip = c.ellipse(cx, 0.33, 0.1, 0.026)
    put(c, lip, 'stone', h=0.42, bevel=0.012)
    for y in (0.468, 0.488):                            # 肩上两道弦纹
        c.engrave(c.stroke([(cx + 0.19 * math.sin(t), y + 0.026 * math.cos(t)) for t in np.linspace(-1.3, 1.3, 30)], w=0.0055) * body, depth=0.07)
    # 釉：上面暗红，下沿不齐、几道往下流；下面露出素胎
    yy, xx = np.mgrid[0:W, 0:W] / W
    line = 0.64 + 0.012 * np.sin(xx * 47 + 1.3) + 0.006 * np.sin(xx * 113)
    for x0, L in ((0.37, 0.04), (0.45, 0.06), (0.52, 0.025), (0.585, 0.07), (0.635, 0.03)):
        line = line + L * np.exp(-((xx - x0) / 0.011) ** 2)
    pot = np.clip(body + neck + lip, 0, 1)
    glaze = _blur((yy < line).astype(float), 0.002) * pot
    clay = np.clip(body + foot - glaze, 0, 1)
    paint(c, clay, (92, 62, 42), 0.92)
    paint(c, blotch(c, clay, scale=0.01, thr=0.55, sharp=3), (70, 48, 34), 0.92)
    c.relief(glaze * body, h=0.025, soft=0.002)
    paint(c, glaze, (80, 18, 15), 0.95, gloss=0.65)
    paint(c, blotch(c, glaze, scale=0.012, thr=0.6, sharp=3), (58, 14, 12), 0.95, gloss=0.5)
    crackle(c, glaze * body, n=70, w=0.003, depth=0.025)
    chip = blotch(c, c.circle(0.37, 0.53, 0.024), scale=0.004, thr=0.45, sharp=8)
    c.engrave(chip, depth=0.06, soft=0.002)
    paint(c, chip, (96, 74, 56), 0.9)
    c.gloss = np.where(chip > 0.5, 0, c.gloss)
    # 封蜡：一团旧蜡盖住瓮口，往颈上流几道
    wax = np.clip(c.ellipse(cx, 0.312, 0.088, 0.036) + c.stroke([(0.445, 0.33), (0.442, 0.375)], w=0.016, wfn=lambda u: 1 - 0.2 * u)
                  + c.circle(0.442, 0.378, 0.0095) + c.stroke([(0.556, 0.332), (0.559, 0.356)], w=0.012) + c.circle(0.559, 0.358, 0.008), 0, 1)
    put(c, wax, 'leather', h=0.55, bevel=0.015, dome=0.3)
    paint(c, wax, (118, 94, 52), 0.9, gloss=0.35)
    c.engrave(c.oring(cx, 0.306, 0.046, 0.017, 0.006), depth=0.07)
    # 麻绳：颈上两道，两边提上去在顶上打结，再一个吊环
    loop = spline([(0.49, 0.15), (0.466, 0.105), (0.48, 0.07), (0.5, 0.062), (0.52, 0.07), (0.534, 0.105), (0.51, 0.15)], 8)
    c.cord(resample(loop, 0.02), rgb=hemp, w=0.017, h=0.6)
    for y0, y1 in ((0.385, 0.393), (0.408, 0.416)):
        c.cord(resample([(0.41, y0), (0.5, y0 + 0.007), (0.59, y1)], 0.02), rgb=hemp, w=0.016, h=0.75)
    for s in (-1, 1):
        c.cord(resample(spline([(cx + s * 0.088, 0.4), (cx + s * 0.1, 0.34), (cx + s * 0.07, 0.25), (cx + s * 0.016, 0.165)], 8), 0.02),
               rgb=hemp, w=0.016, h=0.7)
    knot(c, cx, 0.158, 0.026, 0.02, hemp, h=0.85)
    c.hammer(0.012)
    c.scratches(50)
    c.patina((70, 58, 44), 0.3, scale=0.012, thr=0.55)
    return c.save(out, chip=0.5, tilt=-3, **DARK)


def dr_blood_debt(out):
    """血债：一卷羊皮契约——横卷着、右端露出卷层，中间细绳扎紧；绳往上做挂圈，往下吊一枚血红蜡封（印面一滴血 + 一圈珠点，无字）"""
    c = Canvas(209)
    cy, r, x0, x1 = 0.40, 0.082, 0.165, 0.835
    twine = (100, 80, 54)
    loop = spline([(0.486, 0.33), (0.458, 0.25), (0.46, 0.17), (0.5, 0.13), (0.54, 0.17), (0.542, 0.25), (0.514, 0.33)], 8)
    c.cord(resample(loop, 0.022), rgb=twine, w=0.019, h=0.1)
    for s in (-1, 1):
        c.cord(resample(spline([(0.5 + s * 0.013, 0.47), (0.5 + s * 0.022, 0.56), (0.5 + s * 0.01, 0.65)], 8), 0.022), rgb=twine, w=0.017, h=0.1)
    body = np.clip(rect(c, x0, cy - r, x1, cy + r) + c.ellipse(x0, cy, 0.026, r), 0, 1)
    put(c, body, 'bone', h=0.0, bevel=r)
    endf = c.ellipse(x1, cy, 0.03, r + 0.002)
    put(c, endf, 'bone', h=0.18, bevel=0.012)
    paint(c, np.clip(body + endf, 0, 1), (150, 120, 78), 0.92, gloss=0.05)
    sp = [(x1 + rr * math.cos(a) * 0.36, cy + rr * math.sin(a)) for rr, a in zip(np.linspace(0.006, r * 0.92, 160), np.linspace(0, 3.4 * 2 * math.pi, 160))]
    sp_m = c.stroke(sp, w=0.0045) * endf
    c.engrave(sp_m, depth=0.1, soft=0.001)
    paint(c, sp_m, (96, 78, 54), 0.8)
    # 外层纸边（一道台阶）+ 污渍 + 边缘发黄发暗
    c.engrave(c.stroke(spline([(x0 + 0.02, cy + 0.032), (0.4, cy + 0.04), (0.65, cy + 0.046), (x1 - 0.03, cy + 0.04)], 8), w=0.005) * body, depth=0.07)
    paint(c, blotch(c, body, scale=0.014, thr=0.58), (110, 84, 54), 0.8)
    paint(c, _blur(c.ring_mask_edge(body, 0.014), 0.008) * body, (84, 62, 40), 0.8)
    for k in range(6):                                  # 纸面的褶
        xk = c.rng.uniform(x0 + 0.03, x1 - 0.05)
        c.engrave(c.stroke([(xk, cy - r * 0.8), (xk + c.rng.uniform(-0.01, 0.01), cy + r * 0.7)], w=0.0035) * body, depth=0.025)
    # 扎绳
    for s in (-1, 1):
        c.cord(resample([(0.5 + s * 0.012, cy - r - 0.012), (0.5 + s * 0.009, cy), (0.5 + s * 0.013, cy + r + 0.012)], 0.022), rgb=twine, w=0.018, h=0.45)
    # 蜡封
    sx, sy, sr = 0.5, 0.715, 0.085
    ang = np.linspace(0, 2 * math.pi, 64, endpoint=False)
    rr = sr * (1 + 0.05 * np.sin(ang * 3 + 0.7) + 0.035 * np.sin(ang * 7 + 2) + 0.015 * c.rng.standard_normal(64))
    seal = c.poly([(sx + q * math.cos(a), sy + q * math.sin(a)) for q, a in zip(rr, ang)])
    put(c, seal, 'blood', h=0.1, bevel=0.03, dome=0.2)
    c.engrave(c.circle(sx, sy, 0.058), depth=0.06, soft=0.004)
    c.engrave(c.ring(sx, sy, 0.058, 0.008), depth=0.12)
    c.relief(c.teardrop(sx, sy - 0.004, 0.029), h=0.12, soft=0.003)
    c.beads(sx, sy, 0.047, 14, 0.0045, h=0.05)
    paint(c, seal, (100, 18, 14), 0.95, gloss=0.35)
    c.hammer(0.01)
    c.scratches(40)
    c.patina((70, 56, 40), 0.25, scale=0.012, thr=0.55)
    return c.save(out, chip=0.4, tilt=-4, **DARK)


def dr_flask_endure(out):
    """强韧：红色圣杯瓶（圆肚长颈、软木塞），外面一圈铁条笼（三根经条 + 一道腰箍 + 颈箍 + 底钮），两根铁丝从颈箍提到顶上挂环"""
    c = Canvas(210)
    cx, cy, R = 0.5, 0.64, 0.18
    neck_top, liquid = 0.3, 0.385
    # 挂环 + 两根提丝（从肩上的颈箍顺着瓶颈两边提上去）
    put(c, c.ring(cx, 0.135, 0.03, 0.016), 'iron', h=0.5, bevel=0.008)
    for s in (-1, 1):
        put(c, c.stroke(spline([(cx + s * 0.062, 0.47), (cx + s * 0.066, 0.36), (cx + s * 0.05, 0.24), (cx + s * 0.008, 0.162)], 8), w=0.014),
            'iron', h=0.3, bevel=0.007)
    # 瓶：圆肚 + 细长颈，红色的液体到颈中间，上面是空的玻璃
    glass = np.clip(c.circle(cx, cy, R) + rect(c, 0.464, neck_top, 0.536, 0.5), 0, 1)
    put(c, glass, 'glass', h=0.0, bevel=0.13, dome=0.55)
    paint(c, glass, (100, 16, 14), 1.0, gloss=1.0)
    yy, xx = np.mgrid[0:W, 0:W] / W
    paint(c, glass * (yy < liquid), (58, 52, 50), 1.0, gloss=1.0)
    deep = _blur(c.circle(cx + 0.03, cy + 0.05, 0.12), 0.04) * glass * (yy >= liquid)
    paint(c, deep, (60, 8, 8), 1.0)
    c.emit += (_blur(c.circle(cx + 0.04, cy + 0.07, 0.07), 0.04) * glass)[..., None] * np.array([0.2, 0.025, 0.015])[None, None, :]
    hl = c.poly(Canvas.rot([(cx - 0.085 + 0.03 * math.cos(t), cy - 0.075 + 0.016 * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 30)], cx - 0.085, cy - 0.075, -0.7))
    c.emit += _blur(hl, 0.006)[..., None] * np.array([0.32, 0.28, 0.27])[None, None, :]
    c.emit += (_blur(c.stroke(c.arc(cx, cy, R * 0.86, 2.3, 3.3), w=0.01), 0.004) * glass)[..., None] * np.array([0.16, 0.12, 0.12])[None, None, :]
    c.emit += (_blur(c.stroke([(0.476, neck_top + 0.02), (0.476, 0.47)], w=0.008), 0.003) * glass)[..., None] * np.array([0.14, 0.13, 0.13])[None, None, :]
    lip = c.ellipse(cx, neck_top, 0.05, 0.016)
    put(c, lip, 'glass', h=0.35, bevel=0.008)
    paint(c, lip, (72, 66, 62), 1.0, gloss=1.0)
    cork = np.maximum(rect(c, 0.47, 0.245, 0.53, neck_top), c.ellipse(cx, 0.245, 0.03, 0.01))
    put(c, cork, 'wood', h=0.4, bevel=0.012)
    for x in (0.484, 0.5, 0.516):
        c.engrave(c.stroke([(x, 0.247), (x + 0.002, neck_top - 0.004)], w=0.0035) * cork, depth=0.03)
    # 铁条笼：五根经条 + 一道腰箍，顶上一圈颈箍，底下一个钮
    straps = np.zeros((W, W))
    for phi in (-1.15, -0.55, 0.0, 0.55, 1.15):
        pts = [(cx + R * math.sin(phi) * math.sin(t), cy - R * math.cos(t)) for t in np.linspace(0.42, math.pi - 0.12, 40)]
        straps = np.maximum(straps, c.stroke(pts, w=0.019))
    band = c.stroke([(cx + R * math.sin(t), cy + 0.04 * math.cos(t)) for t in np.linspace(-math.pi / 2, math.pi / 2, 40)], w=0.026)
    cage = np.clip(straps + band, 0, 1) * (c.circle(cx, cy, R + 0.007) > 0.5)
    coat(c, cage, 'iron', th=0.15, bevel=0.007)
    c.engrave(c.ring_mask_edge(cage, 0.003), depth=0.04)
    for phi in (-1.15, -0.55, 0.0, 0.55, 1.15):
        coat(c, c.circle(cx + R * math.sin(phi) * 0.975, cy + 0.04 * math.cos(phi), 0.0105), 'iron', th=0.1, bevel=0.006)
    coat(c, c.circle(cx, cy + R - 0.012, 0.019), 'iron', th=0.18, bevel=0.01)
    collar = np.clip(c.ellipse(cx, 0.48, 0.072, 0.02) + rect(c, 0.428, 0.462, 0.572, 0.482), 0, 1)
    put(c, collar, 'iron', h=0.75, bevel=0.01)
    for x in (0.45, 0.5, 0.55):
        put(c, c.circle(x, 0.484, 0.0065), 'iron', h=1.05, bevel=0.005, dome=0.2)
    c.hammer(0.01)
    c.scratches(50)
    c.patina((84, 56, 38), 0.4, scale=0.01, thr=0.5)
    return c.save(out, chip=0.4, tilt=5, **DARK)


def _tear_hw(cx, cy, s, y):
    """Canvas.teardrop(cx, cy, s) 在高度 y 处的半宽"""
    r = s * 0.62
    oy = cy + s - r
    a = math.asin(r / (oy - (cy - s)))
    tx, ty = r * math.cos(a), oy - r * math.sin(a)
    if y <= cy - s or y >= oy + r:
        return 0.0
    if y < ty:
        return tx * (y - (cy - s)) / (ty - (cy - s))
    return math.sqrt(max(r * r - (y - oy) ** 2, 0.0))


def dr_physick_ward(out):
    """无敌：一颗发光的结晶泪滴（浅金白、切面，里面透一团柔光），关在镂空的金丝笼里——四根金丝从顶上的金帽包下来、在底下收成一颗小金坠，
    腰上一道金箍，两边各一个小卷花；金帽上挂环"""
    c = Canvas(211)
    cx, cy, s = 0.5, 0.56, 0.25
    tip, bot = cy - s, cy + s
    # 泪滴外形 + 切面：外形上取一圈顶点，和中心连成三角面；每个三角里高度按中心的重心坐标线性变化 → 平的切面，中间削平一块台面
    crys = c.teardrop(cx, cy, s)
    put(c, crys, 'glass', h=0.0, bevel=0.01)
    vy = [tip + 0.004, tip + 0.11, cy - 0.06, cy + 0.06, cy + 0.165, bot - 0.004]
    right = [(cx + _tear_hw(cx, cy, s, y) * 1.02, y) for y in vy[1:-1]]
    V = [(cx, vy[0])] + right + [(cx + 0.004, vy[-1])] + [(2 * cx - x, y + 0.012 * (k % 2)) for k, (x, y) in enumerate(right[::-1])]
    C = (cx - 0.014, cy + 0.035)
    yy, xx = np.mgrid[0:W, 0:W] / W
    H = np.zeros((W, W))
    sec = np.full((W, W), -1)
    for i in range(len(V)):
        A, B = V[i], V[(i + 1) % len(V)]
        den = (A[1] - B[1]) * (C[0] - B[0]) + (B[0] - A[0]) * (C[1] - B[1])
        wC = ((A[1] - B[1]) * (xx - B[0]) + (B[0] - A[0]) * (yy - B[1])) / den
        m = (c.poly([C, A, B], soft=0) > 0.5) & (crys > 0.5)
        H = np.where(m, wC, H)
        sec = np.where(m, i, sec)
    H = np.clip(H, 0, 0.6)
    c.h = np.where(crys > 0.5, 0.05 + 2.4 * H, c.h)
    # 颜色：浅金白，左上的面亮、右下的面暗一点，台面最亮
    fac = [1.12, 1.02, 0.86, 0.74, 0.7, 0.8, 0.92, 1.0, 1.1, 1.16]
    base = np.array([240, 214, 148], float)
    col = np.zeros((W, W, 3))
    for i in range(len(V)):
        fk = fac[i % len(fac)]
        warm = np.array([1.0, 1.0, 1.0]) + max(0.0, 1.05 - fk) * np.array([0.1, -0.05, -0.4])     # 背光的面偏琥珀，不发灰
        col = np.where((sec == i)[..., None], np.clip(base * fk * warm, 0, 255), col)
    col = np.where((sec < 0)[..., None], base * 0.85, col)
    col = np.where((H >= 0.6)[..., None], np.array([244, 232, 188], float), col)
    c.color = np.where((crys > 0.02)[..., None], col, c.color)
    c.custom = np.maximum(c.custom, crys)
    c.gloss = np.maximum(c.gloss, 0.6 * crys)
    # 透光：整颗淡淡发亮，中下部一团柔光；左上切面一道白光、两点闪光；棱线左亮右暗
    c.emit += crys[..., None] * np.array([0.2, 0.17, 0.1])[None, None, :]
    core = _blur(c.teardrop(cx + 0.005, cy + 0.07, 0.11), 0.03) * crys
    c.emit += core[..., None] * np.array([0.46, 0.38, 0.17])[None, None, :]
    for i in range(len(V)):
        A = V[i]
        ln = c.stroke([C, A], w=0.004) * crys
        if A[0] < cx:
            c.emit += _blur(ln, 0.0015)[..., None] * np.array([0.12, 0.11, 0.09])[None, None, :]
        else:
            c.engrave(ln, depth=0.04, soft=0.001)
    c.emit += (_blur(c.stroke([(cx - 0.085, cy - 0.06), (cx - 0.118, cy + 0.04)], w=0.01, wfn=lambda u: math.sin(math.pi * u) ** 0.6), 0.003) * crys)[..., None] \
        * np.array([0.34, 0.33, 0.3])[None, None, :]
    for gx, gy, r0 in ((cx - 0.06, cy - 0.1, 0.022), (cx + 0.07, cy + 0.12, 0.014)):
        star = np.maximum(c.stroke([(gx - r0, gy), (gx + r0, gy)], w=0.003, wfn=lambda u: math.sin(math.pi * u)),
                          c.stroke([(gx, gy - r0), (gx, gy + r0)], w=0.003, wfn=lambda u: math.sin(math.pi * u)))
        c.emit += np.clip(_blur(star, 0.0015) * 1.5 + _blur(c.circle(gx, gy, 0.004), 0.002), 0, 1)[..., None] * np.array([0.5, 0.48, 0.42])[None, None, :]
    c.glow(crys, (236, 214, 150), r=0.04, k=0.2)
    # 金丝笼：两根贴着外轮廓，两根从正面斜着交叉绕过去（交叉处一颗小金珠），上下都收拢；两边各一个小卷花
    def wire(f0, f1, off=0.0):
        pts = []
        for u in np.linspace(0, 1, 60):
            y = tip + 0.06 + (bot + 0.008 - tip - 0.06) * u
            k = u * u * (3 - 2 * u)
            f = f0 + (f1 - f0) * k
            pts.append((cx + f * _tear_hw(cx, cy, s, y) + np.sign(f) * off, y))
        return pts
    for f0, f1, off, w in ((-1.0, -1.0, 0.012, 0.013), (1.0, 1.0, 0.012, 0.013), (-0.62, 0.7, 0.0, 0.0095), (0.62, -0.7, 0.0, 0.0095)):
        coat(c, c.stroke(wire(f0, f1, off), w=w), 'gold', th=0.3, bevel=0.006)
    xy = wire(-0.62, 0.7)[30]
    coat(c, c.circle(xy[0], xy[1], 0.011), 'gold', th=0.42, bevel=0.007)
    gy = cy + 0.03
    R = _tear_hw(cx, cy, s, gy) + 0.012
    for sg in (-1, 1):
        sp = Canvas.spiral(cx + sg * (R + 0.02), gy, 0.004, 0.019, 1.3, start=(0 if sg > 0 else math.pi), n=40)
        coat(c, c.stroke(sp, w=0.008), 'gold', th=0.3, bevel=0.004)
    # 底坠
    put(c, c.circle(cx, bot + 0.012, 0.016), 'gold', h=0.5, bevel=0.01, dome=0.3)
    put(c, c.stroke([(cx, bot + 0.025), (cx, bot + 0.05)], w=0.012, wfn=lambda u: 1 - 0.8 * u), 'gold', h=0.4, bevel=0.005)
    # 金帽（包住泪滴尖）+ 帽沿一圈珠 + 顶钮 + 挂环
    cap = np.clip(c.ellipse(cx, tip + 0.06, 0.05, 0.02) + c.poly([(cx - 0.042, tip + 0.06), (cx + 0.042, tip + 0.06), (cx + 0.018, tip + 0.005), (cx - 0.018, tip + 0.005)]), 0, 1)
    put(c, cap, 'gold', h=1.0, bevel=0.016, dome=0.3)
    for x in np.linspace(cx - 0.04, cx + 0.04, 7):
        coat(c, c.circle(x, tip + 0.068 + 0.012 * (1 - ((x - cx) / 0.045) ** 2), 0.0055), 'gold', th=0.08, bevel=0.004)
    put(c, c.circle(cx, tip - 0.002, 0.014), 'gold', h=1.1, bevel=0.008, dome=0.3)
    c.bail(cx, tip - 0.045, 'gold', r=0.025, w=0.013, h=1.2, down=0.015)
    c.scratches(30)
    c.patina((70, 56, 30), 0.3, scale=0.012, thr=0.55)
    return c.save(out, chip=0.3, **dict(DARK, grit=0.26))


# ---------------------------------------------------------------- 出图
def main():
    os.makedirs(OUT, exist_ok=True)
    from PIL import Image
    want = [k for k in sys.argv[1:] if k in KEYS] or KEYS
    for k in want:
        globals()[k](os.path.join(OUT, 'charm_' + k + '.png'))
        print('画好', k)
    ims = [Image.open(os.path.join(OUT, 'charm_' + k + '.png')).convert('RGBA') for k in KEYS if os.path.exists(os.path.join(OUT, 'charm_' + k + '.png'))]
    sheet = Image.new('RGBA', (160 * len(ims), 160), (40, 36, 30, 255))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, (i * 160, 0))
    sheet.save(os.path.join(OUT, 'sheet_blood.png'))
    sheet.resize((sheet.width * 2, 320), Image.LANCZOS).save(os.path.join(OUT, 'sheet_blood_x2.png'))


if __name__ == '__main__':
    main()
