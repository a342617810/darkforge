# -*- coding: utf-8 -*-
"""第 3 批：远程 / 生存（设计清单.md「第 3 批」）。画法照 icons_charm.py：每个词条一件能戴的护符 / 饰品，
颜色压暗、积灰磨损重、发光克制。挂法轮流：挂环 / 链 / 绳。
用法：python batch_ranged.py [键 ...]（不给键 = 全画）；输出 out/charm_<键>.png + out/sheet_ranged.png / sheet_ranged_x2.png"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import Canvas, W, _blur  # noqa: E402
from icons_obj import _unit  # noqa: E402
from icons_charm import DARK  # noqa: E402

OUT = os.path.join(HERE, 'out')
KEYS = ['dr_deft', 'dr_hunt', 'dr_detonate', 'dr_close', 'dr_salvage',
        'dr_alternate', 'dr_volley', 'dr_unseen', 'dr_quiver_inf', 'dr_flask']


# ------------------------------------------------------------ 小工具
def _cr(pts, n=8, closed=False):
    """Catmull-Rom 平滑（控制点 → 密集点）"""
    P = list(pts)
    P = ([P[-1]] + P + [P[0], P[1]]) if closed else ([P[0]] + P + [P[-1]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    out.append(out[0] if closed else tuple(pts[-1]))
    return out


def _erode(m, w):
    from scipy import ndimage
    return ndimage.binary_erosion(m > 0.5, iterations=max(1, int(w * W))).astype(float)


def _finish(c, ham=0.013, scr=60, pat=(56, 50, 42), pk=0.32):
    c.hammer(ham)
    c.scratches(scr)
    c.patina(pat, pk)


def _arrowhead(c, bx, by, dx, dy, L, wd, mat='iron', h=0.3, barbed=False):
    """箭头：从 (bx,by) 的銎口往 (dx,dy) 方向，长 L，最宽 wd；带中棱"""
    dx, dy = _unit(dx, dy)
    px, py = -dy, dx

    def Q(t, s):
        return bx + dx * L * t + px * s, by + dy * L * t + py * s

    sock = c.stroke([Q(0, 0), Q(0.22, 0)], w=wd * 0.38, wfn=lambda u: 1 - 0.25 * u)
    if barbed:
        pts = [Q(0.2, wd * 0.12), Q(0.3, wd * 0.5), Q(0.24, wd * 0.62), Q(0.42, wd * 0.5), Q(1.0, 0),
               Q(0.42, -wd * 0.5), Q(0.24, -wd * 0.62), Q(0.3, -wd * 0.5), Q(0.2, -wd * 0.12)]
    else:
        pts = [Q(0.2, wd * 0.14), Q(0.38, wd * 0.5), Q(0.58, wd * 0.42), Q(1.0, 0), Q(0.58, -wd * 0.42), Q(0.38, -wd * 0.5), Q(0.2, -wd * 0.14)]
    blade = c.poly(pts)
    c.add(blade, mat, h=h, bevel=wd * 0.42, profile='ridge')
    c.add(sock, mat, h=h + 0.05, bevel=wd * 0.16)
    c.engrave(c.stroke([Q(0.04, -wd * 0.19), Q(0.06, wd * 0.19)], w=0.005), depth=0.06)
    c.engrave(c.stroke([Q(0.15, -wd * 0.19), Q(0.17, wd * 0.19)], w=0.005), depth=0.06)
    return blade


def _arrow(c, x0, y0, x1, y1, w=0.016, mat='bronze', head_mat=None, fl_mat=None, h=0.2, head=0.11, fl=0.13):
    """一整支箭：(x0,y0) 箭尾 → (x1,y1) 箭尖；箭羽两片"""
    ux, uy = _unit(x1 - x0, y1 - y0)
    px, py = -uy, ux
    c.add(c.stroke([(x0 + ux * 0.01, y0 + uy * 0.01), (x1 - ux * head * 0.6, y1 - uy * head * 0.6)], w=w), mat, h=h, bevel=w * 0.5)
    # 箭羽：两边各一片，后掠
    fm = fl_mat or mat
    for s in (1, -1):
        a = (x0 + ux * 0.02, y0 + uy * 0.02)
        vane = c.poly([(a[0] + px * s * w * 0.4, a[1] + py * s * w * 0.4),
                       (a[0] + px * s * w * 2.4 + ux * 0.012, a[1] + py * s * w * 2.4 + uy * 0.012),
                       (a[0] + px * s * w * 1.9 + ux * fl * 0.85, a[1] + py * s * w * 1.9 + uy * fl * 0.85),
                       (a[0] + px * s * w * 0.4 + ux * fl, a[1] + py * s * w * 0.4 + uy * fl)])
        c.add(vane, fm, h=h - 0.03, bevel=0.008)
        for t in np.linspace(0.02, fl * 0.85, 6):
            c.engrave(c.stroke([(a[0] + ux * t + px * s * w * 0.5, a[1] + uy * t + py * s * w * 0.5),
                                (a[0] + ux * (t - 0.016) + px * s * w * 2.1, a[1] + uy * (t - 0.016) + py * s * w * 2.1)], w=0.004), depth=0.05)
    # 箭头
    hp = [(x1, y1), (x1 - ux * head + px * w * 1.7, y1 - uy * head + py * w * 1.7), (x1 - ux * head * 0.82, y1 - uy * head * 0.82),
          (x1 - ux * head - px * w * 1.7, y1 - uy * head - py * w * 1.7)]
    c.add(c.poly(hp), head_mat or mat, h=h + 0.04, bevel=w * 1.2, profile='ridge')
    # 箭尾扣
    c.add(c.circle(x0 + ux * 0.008, y0 + uy * 0.008, w * 0.75), mat, h=h + 0.02, bevel=w * 0.4)


# ------------------------------------------------------------ 巧手：骨扳指 + 皮绳
def dr_deft(fp):
    c = Canvas(301)
    cx, cy, R, r, kk, t = 0.5, 0.5, 0.25, 0.2, 0.56, 0.17
    top_o = c.ellipse(cx, cy, R, R * kk)
    top_i = c.ellipse(cx, cy, r, r * kk)
    bot_o = c.ellipse(cx, cy + t, R, R * kk)
    rect = c.poly([(cx - R, cy), (cx + R, cy), (cx + R, cy + t), (cx - R, cy + t)])
    sil = np.clip(top_o + bot_o + rect, 0, 1)
    through = np.minimum(top_i, c.ellipse(cx, cy + t, r, r * kk))
    inner_wall = np.clip(top_i - through, 0, 1)
    side = np.clip(sil - top_o, 0, 1)
    bone = (196, 168, 118)
    # 外壁（下面那条弧带）
    c.add(side, 'bone', h=0.05, bevel=0.06)
    c.tint(side, bone, 0.7)
    # 外壁上：两道刻线夹一条嵌金细带 + 两排钻点

    def arc(dy, a0=0.22):
        return [(cx + R * math.cos(a), cy + dy + R * kk * math.sin(a)) for a in np.linspace(a0, math.pi - a0, 50)]

    for dy in (0.05, 0.11):
        c.engrave(c.stroke(arc(dy), w=0.007) * side, depth=0.09)
    inlay = c.stroke(arc(0.08, 0.3), w=0.016) * side
    c.add(inlay, 'oldgold', h=0.32, bevel=0.006)
    for dy in (0.028, 0.135):
        for a in np.linspace(0.5, math.pi - 0.5, 8):
            c.engrave(c.circle(cx + R * math.cos(a), cy + dy + R * kk * math.sin(a), 0.006) * side, depth=0.1)
    # 顶面一圈（环口，薄）
    c.add(np.clip(top_o - top_i, 0, 1), 'bone', h=0.2, bevel=0.018, dome=0.15)
    c.tint(np.clip(top_o - top_i, 0, 1), bone, 0.7)
    # 里面能看见的内壁（暗）
    c.add(inner_wall, 'bone', h=-0.05, bevel=0.01)
    c.tint(inner_wall, (70, 58, 44), 0.95)
    # 骨头的旧裂纹（不发光，只刻）
    for pts in ([(0.31, 0.62), (0.33, 0.69), (0.32, 0.74)], [(0.7, 0.58), (0.72, 0.64)]):
        c.engrave(c.stroke(_cr(pts, 6), w=0.005) * sil, depth=0.1)
    # 皮绳：套在环口后沿上（两股压过环口），紧贴着打一个结，往上一个挂绳圈
    ky = cy - R * kk - 0.035
    leather = (96, 64, 42)
    for s in (-1, 1):
        c.cord(_cr([(cx + s * 0.04, cy - r * kk + 0.018), (cx + s * 0.042, cy - R * kk), (cx + s * 0.014, ky)], 8), rgb=leather, w=0.032, h=0.55)
    kn = c.ellipse(cx, ky, 0.05, 0.036)
    c.add(kn, 'cloth', h=0.64, bevel=0.016, dome=0.5)
    c.tint(kn, leather, 0.9)
    c.engrave(c.stroke([(cx - 0.035, ky - 0.022), (cx + 0.032, ky + 0.022)], w=0.005), depth=0.07)
    c.engrave(c.stroke([(cx - 0.012, ky - 0.032), (cx + 0.04, ky + 0.004)], w=0.004), depth=0.06)
    loop = _cr([(cx - 0.016, ky - 0.03), (cx - 0.075, ky - 0.1), (cx - 0.06, ky - 0.19), (cx, ky - 0.215), (cx + 0.06, ky - 0.19),
                (cx + 0.075, ky - 0.1), (cx + 0.016, ky - 0.03)], 8)
    c.cord(loop, rgb=leather, w=0.03, h=0.5)
    _finish(c, 0.012, 50, (70, 60, 46), 0.35)
    return c.save(fp, chip=0.5, tilt=-8, **DARK)


# ------------------------------------------------------------ 猎印：铁准星圈 + 红宝石 + 挂环
def dr_hunt(fp):
    c = Canvas(302)
    cx, cy, R = 0.5, 0.54, 0.29
    # 外圈 + 顶上一个小凸耳（接挂环）
    band = c.ring(cx, cy, R, 0.07)
    for a in (-math.pi / 2,):
        ca, sa = math.cos(a), math.sin(a)
        tab = c.poly([(cx + (R + 0.02) * ca - 0.03 * sa, cy + (R + 0.02) * sa + 0.03 * ca), (cx + (R + 0.075) * ca - 0.017 * sa, cy + (R + 0.075) * sa + 0.017 * ca),
                      (cx + (R + 0.075) * ca + 0.017 * sa, cy + (R + 0.075) * sa - 0.017 * ca), (cx + (R + 0.02) * ca + 0.03 * sa, cy + (R + 0.02) * sa - 0.03 * ca)])
        band = np.maximum(band, tab)
    c.add(band, 'iron', h=0.1, bevel=0.028)
    c.engrave(c.ring(cx, cy, R - 0.005, 0.006), depth=0.08)
    for i in range(32):                                    # 刻度（四个正方向上是长的刻线）
        a = i / 32 * 2 * math.pi
        L = 0.05 if i % 8 == 0 else (0.026 if i % 4 == 0 else 0.016)
        r_out = R + 0.034 if i % 8 else R + 0.036
        c.engrave(c.stroke([(cx + (r_out - L) * math.cos(a), cy + (r_out - L) * math.sin(a)), (cx + r_out * math.cos(a), cy + r_out * math.sin(a))],
                           w=0.007 if i % 8 == 0 else 0.005), depth=0.09 if i % 8 == 0 else 0.07)
    # 内圈细环
    c.add(c.ring(cx, cy, 0.165, 0.022), 'iron', h=0.12, bevel=0.01)
    # 十字准星：外宽内窄的四根辐条（正十字）
    for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        ca, sa = math.cos(a), math.sin(a)
        r0, r1 = R - 0.02, 0.07
        sp = c.poly([(cx + r0 * ca - 0.025 * sa, cy + r0 * sa + 0.025 * ca), (cx + r1 * ca - 0.009 * sa, cy + r1 * sa + 0.009 * ca),
                     (cx + r1 * ca + 0.009 * sa, cy + r1 * sa - 0.009 * ca), (cx + r0 * ca + 0.025 * sa, cy + r0 * sa - 0.025 * ca)])
        c.add(sp, 'iron', h=0.22, bevel=0.012, profile='ridge')
    # 中间的金托 + 红宝石
    c.add(c.circle(cx, cy, 0.075), 'oldgold', h=0.35, bevel=0.02, dome=0.2)
    c.beads(cx, cy, 0.064, 14, 0.0065, h=0.06)
    gm = c.circle(cx, cy, 0.047)
    c.gem(gm, (138, 16, 14))
    c.glow(c.circle(cx, cy, 0.03), (220, 40, 30), r=0.025, k=0.18)
    c.bail(cx, cy - R - 0.075 - 0.04, 'iron', r=0.03, w=0.016, h=0.35, down=0.012)
    _finish(c, 0.014, 70, (52, 44, 36), 0.4)
    return c.save(fp, chip=0.7, tilt=7, **DARK)


# ------------------------------------------------------------ 引爆：黑陶火药罐 + 引信火星 + 系绳
def dr_detonate(fp):
    c = Canvas(303)
    cx = 0.5
    clay = (64, 58, 52)
    # 罐身 + 罐颈 + 罐口
    body = np.clip(c.ellipse(cx, 0.64, 0.25, 0.225) + c.poly([(cx - 0.085, 0.4), (cx + 0.085, 0.4), (cx + 0.15, 0.5), (cx - 0.15, 0.5)]), 0, 1)
    c.add(body, 'stone', h=0.0, bevel=0.07, dome=0.7)
    c.tint(body, clay, 1.0, gloss=0.25)
    # 腹部两道弦纹 + 中间一圈压印
    for y in (0.57, 0.66):
        c.engrave(c.stroke([(cx + 0.24 * math.cos(a), y + 0.035 * math.sin(a)) for a in np.linspace(0.12, math.pi - 0.12, 40)], w=0.007) * body, depth=0.1)
    for k in range(12):
        a = 0.3 + k * (math.pi - 0.6) / 11
        x, y = cx + 0.235 * math.cos(a), 0.615 + 0.035 * math.sin(a)
        c.engrave(c.stroke([(x - 0.012, y - 0.016), (x, y + 0.014), (x + 0.012, y - 0.016)], w=0.005) * body, depth=0.08)
    # 一道旧裂
    c.engrave(c.stroke(_cr([(0.62, 0.73), (0.65, 0.78), (0.64, 0.83), (0.67, 0.86)], 6), w=0.005) * body, depth=0.12)
    # 罐口
    lip = c.ellipse(cx, 0.4, 0.105, 0.036)
    c.add(lip, 'stone', h=0.62, bevel=0.016)
    c.tint(lip, clay, 1.0, gloss=0.25)
    plug = c.ellipse(cx, 0.394, 0.075, 0.024)
    c.add(plug, 'cloth', h=0.66, bevel=0.012, dome=0.6)
    c.tint(plug, (86, 70, 50), 0.9)
    # 颈上缠的系绳（一圈 + 左边结）+ 往左上的挂绳圈
    rope = (110, 86, 58)
    c.cord(_cr([(cx - 0.13, 0.46), (cx, 0.475), (cx + 0.13, 0.46)], 8), rgb=rope, w=0.02, h=0.7)
    kx, ky = cx - 0.13, 0.455
    c.add(c.circle(kx, ky, 0.025), 'cloth', h=0.76, bevel=0.012, dome=0.4)
    c.tint(c.circle(kx, ky, 0.025), rope, 0.9)
    c.cord(_cr([(kx - 0.005, ky - 0.02), (kx - 0.06, ky - 0.12), (kx - 0.055, ky - 0.26), (kx - 0.005, ky - 0.31), (kx + 0.04, ky - 0.26),
                (kx + 0.025, ky - 0.12), (kx + 0.006, ky - 0.02)], 8), rgb=rope, w=0.021, h=0.5)
    c.cord(_cr([(kx - 0.01, ky + 0.015), (kx - 0.04, ky + 0.06), (kx - 0.045, ky + 0.11)], 6), rgb=rope, w=0.015, h=0.72)
    # 引信：从塞子里出来，往右上弯，尖上一点火星
    fuse = _cr([(cx + 0.01, 0.39), (cx + 0.04, 0.31), (cx + 0.12, 0.26), (cx + 0.2, 0.2)], 8)
    c.cord(fuse, rgb=(70, 60, 48), w=0.013, h=0.7)
    tx, ty = fuse[-1]
    c.tint(c.circle(tx, ty, 0.014), (40, 22, 14), 1.0)
    c.emit += (_blur(c.circle(tx + 0.004, ty - 0.004, 0.009), 0.004) * 1.2).clip(0, 1)[..., None] * np.array([0.9, 0.45, 0.12])[None, None, :]
    c.glow(c.circle(tx, ty, 0.012), (255, 140, 50), r=0.022, k=0.35)
    for k in range(4):
        a = -math.pi / 2 + c.rng.uniform(-1.0, 1.2)
        r1 = c.rng.uniform(0.035, 0.06)
        pts = [(tx + (0.012 + r1 * u) * math.cos(a), ty + (0.012 + r1 * u) * math.sin(a) + 0.015 * u * u) for u in np.linspace(0, 1, 8)]
        c.wisp(pts, (255, 170, 80), w=0.004, k=0.35, r=0.004, wfn=lambda u: 1 - u, core=0.5)
    _finish(c, 0.014, 50, (44, 40, 36), 0.25)
    return c.save(fp, chip=0.6, tilt=4, **DARK)


# ------------------------------------------------------------ 近身：铁指爪 + 链
def dr_close(fp):
    c = Canvas(304)
    cx = 0.5
    # 爪刃（先画，从甲片下面伸出来）：往下再往左勾
    cl = _cr([(cx + 0.01, 0.5), (cx + 0.06, 0.66), (cx + 0.04, 0.8), (cx - 0.04, 0.9), (cx - 0.15, 0.93)], 10)
    blade = c.stroke(cl, w=0.11, wfn=lambda u: max(0.04, (1 - u) ** 0.85))
    c.add(blade, 'steel', h=0.05, bevel=0.035, profile='ridge')
    c.engrave(c.stroke(cl[4:-14], w=0.006, wfn=lambda u: 1 - u) * blade, depth=0.06)
    # 三片甲片（下面的先画）
    plates = [(0.56, 0.115, 0.075), (0.47, 0.13, 0.08), (0.38, 0.14, 0.085)]
    for i, (y, hw, hh) in enumerate(plates):
        pm = c.poly(_cr([(cx - hw, y - hh * 0.55), (cx, y - hh * 0.8), (cx + hw, y - hh * 0.55), (cx + hw * 0.85, y + hh * 0.5), (cx, y + hh * 0.85),
                         (cx - hw * 0.85, y + hh * 0.5)], 8, closed=True))
        c.add(pm, 'iron', h=0.12 + 0.1 * i, bevel=0.03, dome=0.4)
        c.engrave(c.ring_mask_edge(c.poly(_cr([(cx - hw * 0.8, y - hh * 0.38), (cx, y - hh * 0.6), (cx + hw * 0.8, y - hh * 0.38), (cx + hw * 0.68, y + hh * 0.36),
                                               (cx, y + hh * 0.62), (cx - hw * 0.68, y + hh * 0.36)], 8, closed=True)), 0.004), depth=0.06)
        for s in (-1, 1):
            c.add(c.circle(cx + s * hw * 0.7, y, 0.012), 'oldgold', h=0.36 + 0.1 * i, bevel=0.006)
    # 指环（斜着看的椭圆环），压在最上面一片甲片上沿
    c.add(c.oring(cx, 0.27, 0.13, 0.062, 0.034), 'bronze', h=0.55, bevel=0.012)
    c.add(c.stroke([(cx - 0.07, 0.33), (cx + 0.07, 0.33)], w=0.03), 'bronze', h=0.5, bevel=0.012)
    # 链子 + 挂环
    c.chain((cx, 0.205), (cx, 0.085), 'iron', link=0.045, w=0.011, h=0.6)
    c.bail(cx, 0.05, 'iron', r=0.026, w=0.013, h=0.65, down=0.0)
    _finish(c, 0.013, 70, (54, 46, 38), 0.35)
    return c.save(fp, chip=0.6, tilt=-10, **DARK)


# ------------------------------------------------------------ 回收：三枚铁箭头串在皮绳上
def dr_salvage(fp):
    c = Canvas(305)
    cx = 0.5
    ky = 0.15
    sx, sy = 0.82, 0.78                          # 绳圈缩小，箭头放大

    def L_(x, y):
        return cx + x * sx, ky + y * sy

    loop = _cr([L_(0, 0), L_(-0.15, 0.06), L_(-0.25, 0.19), L_(-0.24, 0.32), L_(-0.14, 0.41), L_(0, 0.44),
                L_(0.14, 0.41), L_(0.24, 0.32), L_(0.25, 0.19), L_(0.15, 0.06)], 10, closed=True)
    hangs = [(L_(-0.15, 0.405), (-0.55, 1), 0.31, 0.12, False, 'iron'), (L_(0.15, 0.405), (0.55, 1), 0.31, 0.12, False, 'iron'),
             (L_(0, 0.44), (0, 1), 0.4, 0.15, True, 'iron')]
    # 箭头先画，挂圈压在箭头銎口上，再画绳穿过挂圈
    for (bx, by), (dx, dy), L, wd, barbed, mat in hangs:
        ux, uy = _unit(dx, dy)
        _arrowhead(c, bx + ux * 0.022, by + uy * 0.022, dx, dy, L, wd, mat, h=0.1, barbed=barbed)
        c.add(c.oring(bx + ux * 0.012, by + uy * 0.012, 0.025, 0.025, 0.014), 'oldgold' if barbed else 'bronze', h=0.45, bevel=0.007)
    c.cord(loop, rgb=(92, 62, 40), w=0.026, h=0.4)
    # 骨珠
    for x, y in (L_(-0.08, 0.432), L_(0.08, 0.432)):
        bm = c.ellipse(x, y, 0.024, 0.03)
        c.add(bm, 'bone', h=0.5, bevel=0.014, dome=0.4)
        c.tint(bm, (176, 154, 112), 0.4)
        c.engrave(c.stroke([(x - 0.022, y), (x + 0.022, y)], w=0.004), depth=0.05)
    # 顶上的结 + 两条绳尾
    kn = c.ellipse(cx, ky, 0.04, 0.03)
    c.add(kn, 'cloth', h=0.5, bevel=0.014, dome=0.4)
    c.tint(kn, (92, 62, 40), 0.9)
    c.engrave(c.stroke([(cx - 0.025, ky - 0.02), (cx + 0.025, ky + 0.018)], w=0.005), depth=0.06)
    for s in (-1, 1):
        c.cord(_cr([(cx + s * 0.02, ky - 0.015), (cx + s * 0.04, ky - 0.05), (cx + s * 0.035, ky - 0.075)], 6), rgb=(84, 58, 38), w=0.02, h=0.52)
    _finish(c, 0.013, 60, (60, 44, 32), 0.45)
    return c.save(fp, chip=0.6, tilt=3, **DARK)


# ------------------------------------------------------------ 交替：两半圆牌（银：箭 / 铜：火壶）+ 挂环
def dr_alternate(fp):
    c = Canvas(306)
    cx, cy, R = 0.5, 0.55, 0.32
    gap = 0.024
    crack = [(cx + 0.006 * math.sin(y * 47) + c.rng.normal(0, 0.003), y) for y in np.linspace(0, 1, 24)]

    def side_mask(s, off):
        pts = [(x + s * off, y) for x, y in crack]
        edge = 0.0 if s < 0 else 1.0
        return c.poly([(edge, 0)] + pts + [(edge, 1)])

    disc = c.circle(cx, cy, R)
    inner_disc = c.circle(cx, cy, R * 0.83)
    for s, mat in ((-1, 'silver'), (1, 'bronze')):
        half = disc * side_mask(s, gap / 2)
        field = inner_disc * side_mask(s, gap / 2 + 0.045)
        c.add(half, mat, h=0.0, bevel=0.03)
        c.relief(np.clip(half - field, 0, 1), h=0.16, soft=0.003)
        c.engrave(c.ring_mask_edge(field, 0.005), depth=0.08)
        c.hatch(field, angle=0.7 if s < 0 else -0.7, gap=0.017, depth=0.04)
    # 左：一支箭（箭头朝上）
    ax = 0.335
    arrow = c.stroke([(ax, 0.36), (ax, 0.77)], w=0.022)
    arrow = np.maximum(arrow, c.poly([(ax, 0.27), (ax + 0.05, 0.37), (ax, 0.35), (ax - 0.05, 0.37)]))
    for s in (-1, 1):
        arrow = np.maximum(arrow, c.poly([(ax + s * 0.008, 0.67), (ax + s * 0.05, 0.7), (ax + s * 0.05, 0.79), (ax + s * 0.008, 0.77)]))
    c.emboss(arrow, h=0.3, line=0.005, depth=0.07)
    for y in (0.7, 0.73, 0.76):
        for s in (-1, 1):
            c.engrave(c.stroke([(ax + s * 0.012, y + 0.008), (ax + s * 0.045, y - 0.006)], w=0.004), depth=0.05)
    # 右：火壶（壶身 + 颈 + 口 + 上面一簇火）
    px_, py_ = 0.665, 0.65
    pot = np.clip(c.circle(px_, py_, 0.078) + c.poly([(px_ - 0.03, py_ - 0.11), (px_ + 0.03, py_ - 0.11), (px_ + 0.045, py_ - 0.06), (px_ - 0.045, py_ - 0.06)])
                  + c.ellipse(px_, py_ - 0.11, 0.045, 0.014), 0, 1)
    c.emboss(pot, h=0.3, line=0.005, depth=0.07)
    c.engrave(c.stroke([(px_ - 0.07, py_ + 0.0), (px_ + 0.07, py_ + 0.0)], w=0.004) * pot, depth=0.05)
    flame = c.poly(_cr([(px_, py_ - 0.13), (px_ - 0.04, py_ - 0.17), (px_ - 0.025, py_ - 0.22), (px_ - 0.012, py_ - 0.2), (px_, py_ - 0.29),
                        (px_ + 0.02, py_ - 0.22), (px_ + 0.04, py_ - 0.23), (px_ + 0.04, py_ - 0.17)], 8, closed=True))
    c.emboss(flame, h=0.24, line=0.005, depth=0.07)
    c.engrave(c.stroke(_cr([(px_, py_ - 0.15), (px_ - 0.008, py_ - 0.2), (px_, py_ - 0.25)], 6), w=0.004) * flame, depth=0.05)
    # 上下两枚扣片压着缝
    for y, wd in ((cy - R + 0.035, 0.11), (cy + R - 0.03, 0.08)):
        cm = c.poly([(cx - wd / 2, y - 0.03), (cx + wd / 2, y - 0.03), (cx + wd / 2, y + 0.03), (cx - wd / 2, y + 0.03)])
        c.add(cm, 'oldgold', h=0.42, bevel=0.012, dome=0.2)
        for s in (-1, 1):
            c.add(c.circle(cx + s * (wd / 2 - 0.017), y, 0.009), 'oldgold', h=0.56, bevel=0.005)
    c.bail(cx, cy - R - 0.045, 'oldgold', r=0.03, w=0.016, h=0.4, down=0.02)
    _finish(c, 0.014, 70, (48, 52, 44), 0.38)
    return c.save(fp, chip=0.7, tilt=-5, **DARK)


# ------------------------------------------------------------ 连射：三支铜铸小箭穿过一个铁环 + 链
def dr_volley(fp):
    c = Canvas(307)
    ccx, ccy = 0.5, 0.55
    dx, dy = _unit(1.0, -0.86)
    px, py = -dy, dx
    sp = 0.08
    a, b, wr = 0.14, 0.05, 0.034

    def ring_arc(t0, t1):
        pts = [(ccx + px * a * math.cos(t) + dx * b * math.sin(t), ccy + py * a * math.cos(t) + dy * b * math.sin(t)) for t in np.linspace(t0, t1, 40)]
        return c.stroke(pts, w=wr)

    c.add(ring_arc(math.pi, 2 * math.pi), 'iron', h=0.0, bevel=0.01)
    for k, (off, sh) in enumerate(((-sp, -0.05), (0.0, 0.02), (sp, -0.02))):
        x0 = ccx + px * off - dx * (0.37 - sh)
        y0 = ccy + py * off - dy * (0.37 - sh)
        x1 = ccx + px * off + dx * (0.37 + sh)
        y1 = ccy + py * off + dy * (0.37 + sh)
        _arrow(c, x0, y0, x1, y1, w=0.024, mat='bronze', head_mat='oldgold' if k == 1 else 'bronze', h=0.15 + 0.02 * k, head=0.12, fl=0.13)
    c.add(ring_arc(0, math.pi), 'iron', h=0.5, bevel=0.012)
    for t in np.linspace(0.4, math.pi - 0.4, 5):
        x, y = ccx + px * a * math.cos(t) + dx * b * math.sin(t), ccy + py * a * math.cos(t) + dy * b * math.sin(t)
        c.engrave(c.stroke([(x - dx * 0.016, y - dy * 0.016), (x + dx * 0.016, y + dy * 0.016)], w=0.005), depth=0.06)
    # 链：从环的左上端往上
    tx, ty = ccx - px * a, ccy - py * a
    c.chain((tx, ty - 0.02), (tx, 0.2), 'iron', link=0.05, w=0.013, h=0.55)
    c.bail(tx, 0.163, 'iron', r=0.028, w=0.015, h=0.6, down=0.0)
    _finish(c, 0.013, 60, (56, 60, 46), 0.4)
    return c.save(fp, chip=0.6, **DARK)


# ------------------------------------------------------------ 无形：黑铁半脸面具（闭眼缝）+ 细绳
def dr_unseen(fp):
    c = Canvas(308)
    cx = 0.5
    outline = _cr([(0.19, 0.44), (0.23, 0.31), (0.33, 0.22), (0.5, 0.19), (0.67, 0.22), (0.77, 0.31), (0.81, 0.44), (0.79, 0.56), (0.72, 0.62),
                   (0.6, 0.625), (0.56, 0.655), (0.54, 0.69), (0.5, 0.71), (0.46, 0.69), (0.44, 0.655), (0.4, 0.625), (0.28, 0.62), (0.21, 0.56)], 8,
                  closed=True)
    mask = c.poly(outline)
    # 细绳先画（在面具后面）：两边太阳穴往上到顶上打结，再一个小圈
    cord = (66, 40, 32)
    for s in (-1, 1):
        c.cord(_cr([(cx + s * 0.29, 0.45), (cx + s * 0.35, 0.33), (cx + s * 0.3, 0.17), (cx + s * 0.16, 0.09), (cx + s * 0.02, 0.075)], 8), rgb=cord, w=0.015, h=0.0)
    c.add(mask, 'iron', h=0.0, bevel=0.06, dome=1.0)
    c.tint(mask, (62, 60, 58), 0.65)
    # 眉弓
    for s in (-1, 1):
        c.relief(c.stroke(_cr([(cx + s * 0.24, 0.43), (cx + s * 0.14, 0.385), (cx + s * 0.04, 0.42)], 8), w=0.04, wfn=lambda u: 0.5 + 0.5 * math.sin(math.pi * u)),
                 h=0.12, soft=0.008)
    # 鼻梁
    c.relief(c.stroke([(cx, 0.42), (cx, 0.68)], w=0.05, wfn=lambda u: 0.55 + 0.45 * u), h=0.14, soft=0.008)
    for s in (-1, 1):
        c.engrave(c.stroke(_cr([(cx + s * 0.025, 0.66), (cx + s * 0.04, 0.675), (cx + s * 0.05, 0.67)], 4), w=0.006), depth=0.08)
    # 卷边（外轮廓一圈稍微凸起，磨亮）
    c.relief(np.clip(mask - _erode(mask, 0.014), 0, 1), h=0.07, soft=0.003)
    # 闭着的眼缝：往下弯的细缝 + 上眼睑鼓起
    for s in (-1, 1):
        ex = cx + s * 0.135
        c.relief(c.ellipse(ex, 0.46, 0.075, 0.03), h=0.07, soft=0.008)
        c.engrave(c.stroke([(ex - 0.08, 0.465), (ex - 0.04, 0.488), (ex, 0.494), (ex + 0.04, 0.488), (ex + 0.08, 0.465)], w=0.011, taper=True), depth=0.22)
    # 额上刻纹：一道竖线 + 两道弧
    c.engrave(c.stroke([(cx, 0.24), (cx, 0.36)], w=0.006), depth=0.08)
    for r in (0.25, 0.29):
        c.engrave(c.stroke(Canvas.arc(cx, 0.5, r, math.pi * 1.2, math.pi * 1.8), w=0.005) * mask, depth=0.06)
    for a in (1.3, 1.4, 1.6, 1.7):                     # 额上两道弧之间一排小铆钉
        c.relief(c.circle(cx + 0.27 * math.cos(a * math.pi), 0.5 + 0.27 * math.sin(a * math.pi), 0.009), h=0.08, soft=0.002)
    for s in (-1, 1):                                  # 颊上的卷纹
        c.engrave(c.stroke(_cr([(cx + s * 0.07, 0.56), (cx + s * 0.15, 0.585), (cx + s * 0.23, 0.565), (cx + s * 0.265, 0.52)], 8), w=0.006) * mask, depth=0.07)
    # 太阳穴的铆钉（绳子穿在这里）
    for s in (-1, 1):
        c.add(c.circle(cx + s * 0.28, 0.45, 0.018), 'oldgold', h=0.55, bevel=0.008, dome=0.3)
        c.engrave(c.circle(cx + s * 0.28, 0.45, 0.006), depth=0.12)
    # 顶上的结 + 挂圈
    c.add(c.ellipse(cx, 0.075, 0.024, 0.02), 'cloth', h=0.1, bevel=0.01, dome=0.4)
    c.tint(c.ellipse(cx, 0.075, 0.024, 0.02), cord, 0.9)
    c.cord(_cr([(cx - 0.006, 0.06), (cx - 0.035, 0.028), (cx, 0.006), (cx + 0.035, 0.028), (cx + 0.006, 0.06)], 8), rgb=cord, w=0.014, h=0.05)
    _finish(c, 0.012, 60, (48, 46, 44), 0.35)
    return c.save(fp, chip=0.5, tilt=-4, **DARK)


# ------------------------------------------------------------ 无尽箭袋：插满箭的皮箭袋 + 衔尾蛇铜箍 + 链
def dr_quiver_inf(fp):
    c = Canvas(309)
    M = (0.56, 0.36)
    B = (0.48, 0.8)
    dx, dy = _unit(B[0] - M[0], B[1] - M[1])     # 袋身方向（往下）
    qx, qy = dy, -dx                              # 横向（往右）
    wm, wb = 0.145, 0.1

    def ell(rx, sq):
        return c.poly([(M[0] + qx * rx * math.cos(t) + dx * rx * sq * math.sin(t), M[1] + qy * rx * math.cos(t) + dy * rx * sq * math.sin(t))
                       for t in np.linspace(0, 2 * math.pi, 90)])

    def strip(t0, t1, half):
        return c.poly([(M[0] + dx * t0 - qx * half, M[1] + dy * t0 - qy * half), (M[0] + dx * t0 + qx * half, M[1] + dy * t0 + qy * half),
                       (M[0] + dx * t1 + qx * half, M[1] + dy * t1 + qy * half), (M[0] + dx * t1 - qx * half, M[1] + dy * t1 - qy * half)])

    open_o, open_i = ell(wm, 0.34), ell(wm - 0.02, 0.3)
    near = strip(0.0, 0.9, 0.4)                  # 口中线以下（近端）
    # 背后的箍沿（口的远端）+ 黑洞
    c.add(np.clip(open_o - open_i, 0, 1), 'oldgold', h=0.0, bevel=0.008)
    c.add(open_i, 'leather', h=-0.1, bevel=0.01)
    c.tint(open_i, (20, 16, 12), 1.0)
    # 箭：从口里伸出来，往上散开；尾上箭羽
    fl_cols = [(176, 172, 160), (112, 50, 40), (156, 150, 138), (190, 184, 170), (120, 112, 100), (170, 164, 150), (118, 56, 44)]
    n = 7
    up = math.atan2(-dy, -dx)
    for k in range(n):
        v = (k / (n - 1)) * 2 - 1
        bx = M[0] + qx * (wm - 0.04) * v + dx * 0.025
        by = M[1] + qy * (wm - 0.04) * v + dy * 0.025
        a = up + v * 0.3 + c.rng.normal(0, 0.03)
        L = 0.27 + 0.06 * c.rng.random() - 0.04 * abs(v)
        ux, uy = math.cos(a), math.sin(a)
        ex, ey = bx + L * ux, by + L * uy
        px, py = -uy, ux
        sh = c.stroke([(bx, by), (ex, ey)], w=0.016)
        c.add(sh, 'wood', h=0.12 + 0.01 * k, bevel=0.007)
        c.tint(sh, (150, 118, 80), 0.45)
        for s in (-1, 1):
            vane = c.poly([(ex - ux * 0.014 + px * s * 0.005, ey - uy * 0.014 + py * s * 0.005), (ex - ux * 0.024 + px * s * 0.034, ey - uy * 0.024 + py * s * 0.034),
                           (ex - ux * 0.115 + px * s * 0.026, ey - uy * 0.115 + py * s * 0.026), (ex - ux * 0.13 + px * s * 0.005, ey - uy * 0.13 + py * s * 0.005)])
            c.add(vane, 'feather', h=0.18 + 0.01 * k, bevel=0.007)
            c.tint(vane, fl_cols[k], 0.75)
            for t in np.linspace(0.03, 0.115, 5):
                c.engrave(c.stroke([(ex - ux * t + px * s * 0.006, ey - uy * t + py * s * 0.006), (ex - ux * (t - 0.014) + px * s * 0.028, ey - uy * (t - 0.014) + py * s * 0.028)],
                                   w=0.0038) * vane, depth=0.05)
        c.add(c.circle(ex, ey, 0.009), 'wood', h=0.22 + 0.01 * k, bevel=0.004)
    # 袋身：口的近端以下（盖住箭杆下半）
    tube = c.poly([(M[0] - qx * wm, M[1] - qy * wm), (M[0] + qx * wm, M[1] + qy * wm), (B[0] + qx * wb, B[1] + qy * wb), (B[0] - qx * wb, B[1] - qy * wb)])
    tube = np.clip(tube + c.circle(B[0], B[1], wb) + open_o, 0, 1)
    front = np.clip((tube - open_i) * near, 0, 1)
    c.add(front, 'leather', h=0.3, bevel=0.05, dome=0.5)
    # 缝线 + 两道皮带
    for k in range(17):
        t0 = 0.12 + k * 0.022
        sx, sy = M[0] + dx * t0 + qx * wm * 0.5, M[1] + dy * t0 + qy * wm * 0.5
        c.engrave(c.stroke([(sx, sy), (sx + dx * 0.012, sy + dy * 0.012)], w=0.005) * front, depth=0.07)
    for t0 in (0.25, 0.4):
        st = strip(t0, t0 + 0.04, 0.16) * front
        c.relief(st, h=0.07, soft=0.003)
        c.tint(st, (58, 38, 26), 0.8)
        c.add(c.circle(M[0] + dx * (t0 + 0.02) - qx * 0.06, M[1] + dy * (t0 + 0.02) - qy * 0.06, 0.011), 'bronze', h=0.5, bevel=0.005)
    # 口上的铜箍：衔尾蛇鳞纹，正面一个蛇头咬着蛇尾
    band = np.clip(strip(0.0, 0.08, wm + 0.012) + open_o, 0, 1) * near
    band = np.clip(band - open_i, 0, 1)
    c.add(band, 'oldgold', h=0.45, bevel=0.015, dome=0.3)
    rot = math.atan2(dy, dx) - math.pi / 2
    for i in range(13):
        u = (i + 0.5) / 13 * 2 - 1
        for row, sft in ((0.035, 0.0), (0.06, 0.5 / 13)):
            sx, sy = M[0] + qx * wm * 0.95 * (u + sft) + dx * row, M[1] + qy * wm * 0.95 * (u + sft) + dy * row
            c.engrave(c.stroke(Canvas.rot(Canvas.arc(sx, sy, 0.009, 0.2, math.pi - 0.2, 8), sx, sy, rot), w=0.0038) * band, depth=0.06)
    hx, hy = M[0] + qx * 0.02 + dx * 0.05, M[1] + qy * 0.02 + dy * 0.05
    head = c.ellipse(hx, hy, 0.03, 0.022)
    c.add(head, 'oldgold', h=0.62, bevel=0.012, dome=0.4)
    c.engrave(c.circle(hx + 0.01, hy - 0.004, 0.005), depth=0.12)
    c.engrave(c.stroke([(hx - 0.03, hy + 0.004), (hx - 0.012, hy + 0.006)], w=0.004), depth=0.08)
    # 链：从箍左边的耳往左上
    lx, ly = M[0] - qx * (wm + 0.025) + dx * 0.035, M[1] - qy * (wm + 0.025) + dy * 0.035
    c.add(c.oring(lx, ly, 0.022, 0.022, 0.012), 'oldgold', h=0.6, bevel=0.005)
    c.chain((lx - 0.008, ly - 0.025), (0.28, 0.13), 'iron', link=0.045, w=0.012, h=0.55)
    c.bail(0.27, 0.1, 'iron', r=0.026, w=0.013, h=0.6, down=0.0)
    _finish(c, 0.013, 60, (50, 46, 38), 0.32)
    return c.save(fp, chip=0.6, tilt=3, **DARK)


# ------------------------------------------------------------ 圣杯：金高脚杯 + 杯里一滴金红露珠 + 提梁挂环
def dr_flask(fp):
    c = Canvas(310)
    cx = 0.5
    y0, yb = 0.33, 0.6

    def hw(y):
        if y <= yb:
            s = (y - y0) / (yb - y0)
            return 0.035 + 0.165 * math.sqrt(max(0.0, 1 - s ** 2.2))
        if y <= 0.82:
            return 0.024
        s = (y - 0.82) / 0.06
        return 0.024 + 0.13 * s ** 1.6

    ys = np.linspace(y0, 0.88, 80)
    sil = c.poly([(cx + hw(y), y) for y in ys] + [(cx - hw(y), y) for y in ys[::-1]])
    foot = c.ellipse(cx, 0.88, 0.16, 0.035)
    rim_o = c.ellipse(cx, y0, 0.2, 0.055)
    rim_i = c.ellipse(cx, y0 + 0.002, 0.172, 0.043)
    # 提梁（金丝弧，从两边耳环越过杯口到顶上的环）
    ear_y = 0.4
    for s in (-1, 1):
        c.add(c.ring(cx + s * 0.205, ear_y, 0.026, 0.014), 'oldgold', h=0.3, bevel=0.006)
    hoop = [(cx + 0.205 * math.cos(a), ear_y - 0.026 - 0.26 * math.sin(a)) for a in np.linspace(0.02, math.pi - 0.02, 60)]
    c.add(c.stroke(hoop, w=0.014), 'oldgold', h=0.0, bevel=0.006)
    c.add(c.ring(cx, ear_y - 0.026 - 0.26 - 0.022, 0.026, 0.014), 'oldgold', h=0.15, bevel=0.006)
    # 杯身
    c.add(np.clip(sil + foot, 0, 1), 'gold', h=0.1, bevel=0.05, dome=0.3)
    c.add(foot, 'gold', h=0.08, bevel=0.02, dome=0.2)
    c.engrave(c.ring_mask_edge(c.ellipse(cx, 0.875, 0.13, 0.026), 0.004), depth=0.06)
    # 杯身装饰：口沿下一圈珠点 + 下半的竖棱
    for k in range(13):
        a = 0.15 + k * (math.pi - 0.3) / 12
        c.relief(c.circle(cx + 0.175 * math.cos(a), y0 + 0.07 + 0.03 * math.sin(a), 0.008), h=0.08, soft=0.002)
    c.engrave(c.stroke([(cx + 0.188 * math.cos(a), y0 + 0.098 + 0.03 * math.sin(a)) for a in np.linspace(0.15, math.pi - 0.15, 40)], w=0.005), depth=0.06)
    for k in range(7):
        xo = (k - 3) / 3
        c.engrave(c.stroke([(cx + xo * 0.12, y0 + 0.13 + 0.01 * (1 - xo * xo)), (cx + xo * 0.045, yb - 0.01)], w=0.005), depth=0.07)
    # 杯柄上的节 + 一圈珠
    c.add(c.ellipse(cx, 0.71, 0.05, 0.03), 'gold', h=0.45, bevel=0.02, dome=0.4)
    c.add(c.ellipse(cx, 0.615, 0.04, 0.016), 'gold', h=0.42, bevel=0.01)
    c.add(c.ellipse(cx, 0.8, 0.036, 0.014), 'gold', h=0.42, bevel=0.01)
    c.gem(c.circle(cx, 0.71, 0.014), (120, 30, 24))
    # 口沿 + 杯里
    c.add(np.clip(rim_o - rim_i, 0, 1), 'gold', h=0.5, bevel=0.012)
    c.add(rim_i, 'gold', h=0.25, bevel=0.02)
    c.tint(rim_i, (50, 36, 18), 0.8)
    # 杯里一层暗红的液面，正中浮着一颗金红露珠（圆珠，微光）
    liq = c.ellipse(cx, y0 + 0.008, 0.155, 0.033)
    c.add(liq, 'gold', h=0.28, bevel=0.01)
    c.tint(liq, (96, 34, 16), 1.0, gloss=0.7)
    c.emit += (_blur(liq, 0.01) * liq)[..., None] * np.array([0.1, 0.035, 0.01])[None, None, :]
    c.orb(cx + 0.012, y0 + 0.002, 0.026, (214, 116, 40), glow=0.16)
    _finish(c, 0.012, 60, (60, 46, 24), 0.35)
    return c.save(fp, chip=0.5, tilt=-4, **DARK)


# ------------------------------------------------------------ 出图
def main():
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    want = [k for k in sys.argv[1:] if k in KEYS] or KEYS
    for k in want:
        globals()[k](os.path.join(OUT, 'charm_' + k + '.png'))
        print('done', k)
    ims = []
    for k in KEYS:
        f = os.path.join(OUT, 'charm_' + k + '.png')
        ims.append(Image.open(f).convert('RGBA') if os.path.exists(f) else Image.new('RGBA', (160, 160), (0, 0, 0, 0)))
    sheet = Image.new('RGBA', (160 * len(ims), 160), (40, 36, 30, 255))
    for i, im in enumerate(ims):
        sheet.alpha_composite(im, (i * 160, 0))
    sheet.save(os.path.join(OUT, 'sheet_ranged.png'))
    sheet.resize((sheet.width * 2, 320), Image.LANCZOS).save(os.path.join(OUT, 'sheet_ranged_x2.png'))


if __name__ == '__main__':
    main()
