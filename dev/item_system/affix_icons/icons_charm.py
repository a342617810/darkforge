# -*- coding: utf-8 -*-
"""试做第三批：独立物件，但做成「护符 / 饰品」——金属铸的、镶嵌的、带挂环链子绳子，颜色压暗、做旧，尽量贴原版
（用户 2026-11-11「用独立物品可以 但是要看起来像一个护符或者饰品而不是其他东西」「然后尽量贴近原版风格」）。
疾风 = 银铸羽毛坠（羽管包金、缠线、挂环）；燃血 = 心形血晶坠（黑铁荆棘框、晶体里透余烬、底下挂一滴血珠）；
凝聚 = 辉石球坠（爪托 + 一圈带两颗小辉石的轨道环）；相杀 = 交叉双剑坠（交点一枚圆扣，链子挂起）"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import Canvas, W  # noqa: E402
from icons_obj import sword, _unit  # noqa: E402

OUT = os.path.join(HERE, 'out')
DARK = dict(ambient=0.1, light_k=1.15, grime=1.0, sat=0.72, grit=0.38, gamma=1.18, fit=0.9)


def _smooth(pts, k=10):
    sm = []
    for i in range(len(pts) - 1):
        for u in np.linspace(0, 1, k, endpoint=False):
            sm.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u))
    sm.append(pts[-1])
    return sm


def gale(path):
    c = Canvas(31)
    # 挂着的羽毛：羽管朝上，羽尖朝右下
    x0, y0, x1, y1 = 0.42, 0.2, 0.62, 0.93
    ux, uy = _unit(x1 - x0, y1 - y0)
    px, py = -uy, ux

    def P(t):
        bend = -0.045 * math.sin(math.pi * t)
        return x0 + (x1 - x0) * t + px * bend, y0 + (y1 - y0) * t + py * bend

    t0 = 0.16
    ts = np.linspace(t0, 1, 60)

    def wv(t):
        s = (t - t0) / (1 - t0)
        return 0.13 * math.sin(math.pi * min(1.0, s ** 0.75)) ** 0.7 + 0.01 * (s < 0.98)

    left = [(P(t)[0] + px * wv(t), P(t)[1] + py * wv(t)) for t in ts]
    right = [(P(t)[0] - px * wv(t) * 0.8, P(t)[1] - py * wv(t) * 0.8) for t in ts]
    vane = c.poly(left + right[::-1] + [P(t0)])
    for t, side in ((0.5, 1), (0.68, -1)):
        bx, by = P(t)
        k = wv(t) * (1 if side > 0 else 0.8)
        ox, oy = bx + side * px * k * 1.05 + ux * 0.045, by + side * py * k * 1.05 + uy * 0.045
        ix, iy = bx + side * px * k * 0.4, by + side * py * k * 0.4
        vane = np.clip(vane - c.poly([(ox, oy), (ix, iy), (ox - ux * 0.012, oy - uy * 0.012)]), 0, 1)
    c.add(vane, 'silver', h=0.0, bevel=0.03, dome=0.3)
    for side, kk in ((1, 1.0), (-1, 0.8)):            # 铸出来的羽枝槽（间距、长短、深浅都不齐）
        t = t0 + 0.01
        while t < 0.98:
            bx, by = P(t)
            k = wv(t) * kk * c.rng.uniform(0.55, 1.0)
            bend = c.rng.uniform(0.03, 0.05)
            c.engrave(c.stroke([(bx, by), (bx + side * px * k * 0.5 + ux * bend * 0.4, by + side * py * k * 0.5 + uy * bend * 0.4),
                                (bx + side * px * k + ux * bend, by + side * py * k + uy * bend)], w=c.rng.uniform(0.0035, 0.006)),
                      depth=c.rng.uniform(0.04, 0.08), soft=0.0008)
            t += c.rng.uniform(0.012, 0.028)
    shaft = c.stroke([P(t) for t in np.linspace(0.1, 0.97, 50)], w=0.02, wfn=lambda u: 1 - 0.75 * u)
    c.add(shaft, 'silver', h=0.2, bevel=0.01)
    # 羽管包金 + 缠线
    cap0, cap1 = P(0.0), P(0.17)
    c.add(c.stroke([cap0, cap1], w=0.044, wfn=lambda u: 1 - 0.3 * u), 'oldgold', h=0.25, bevel=0.02)
    for t in np.linspace(0.03, 0.15, 5):
        bx, by = P(t)
        c.engrave(c.stroke([(bx - px * 0.024, by - py * 0.024), (bx + px * 0.024, by + py * 0.024)], w=0.004), depth=0.06)
    wrap = c.stroke([P(0.19), P(0.23)], w=0.03)
    c.cord(_smooth([(P(0.18)[0] - px * 0.02, P(0.18)[1] - py * 0.02), (P(0.24)[0] + px * 0.02, P(0.24)[1] + py * 0.02)], 4), rgb=(90, 34, 26), w=0.014, h=0.28)
    del wrap
    # 挂环 + 一颗小绿松石
    c.bail(cap0[0] - ux * 0.035, cap0[1] - uy * 0.035 - 0.012, 'oldgold', r=0.028, w=0.014, h=0.3, down=0.018)
    bx, by = P(0.12)
    c.gem(c.circle(bx + px * 0.0, by + py * 0.0, 0.014), (60, 120, 110))
    c.hammer(0.014)
    c.scratches(60)
    c.patina((58, 54, 46), 0.5, scale=0.012, thr=0.5)
    return c.save(path, chip=0.7, tilt=-6, **DARK)


def _heart_pts(cx, cy, s, n=160):
    pts = []
    for t in np.linspace(0, 2 * math.pi, n):
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s, cy - y * s))
    return pts


def bloodburn(path):
    """燃血：一滴血琥珀，镶在火焰形的黑铁框里，琥珀底部透出暗火"""
    from iconkit import _blur
    c = Canvas(32)
    cx, cy = 0.5, 0.58
    # 火焰框：外圈水滴 + 两边往上卷的火舌 + 顶上一条高火舌（挂环接在它尖上）
    frame = c.teardrop(cx, cy, 0.23)
    for s, (bx, by, hgt, w, bend) in ((1, (0.62, 0.62, 0.36, 0.07, 0.05)), (-1, (0.38, 0.62, 0.32, 0.07, 0.05)),
                                      (1, (0.66, 0.76, 0.24, 0.06, 0.06)), (-1, (0.34, 0.76, 0.26, 0.06, 0.06))):
        fp = [(bx + s * (0.05 * math.sin(u * math.pi * 0.9) - bend * u * u), by - hgt * u) for u in np.linspace(0, 1, 30)]
        frame = np.maximum(frame, c.stroke(fp, w=w, wfn=lambda u: 1 - 0.92 * u))
    frame = np.maximum(frame, c.stroke([(cx + 0.012 * math.sin(u * 7), cy - 0.2 - 0.13 * u) for u in np.linspace(0, 1, 20)], w=0.06, wfn=lambda u: 1 - 0.9 * u))
    c.add(frame, 'darkiron', h=0.0, bevel=0.02, dome=0.2)
    c.engrave(c.ring_mask_edge(c.teardrop(cx, cy + 0.01, 0.19), 0.006), depth=0.08)
    # 火舌上的刻线
    for s in (1, -1):
        for k in range(3):
            fp = [(cx + s * (0.13 + 0.03 * k + 0.03 * math.sin(u * 3)), cy + 0.12 - u * (0.25 - 0.04 * k)) for u in np.linspace(0, 1, 14)]
            c.engrave(c.stroke(fp, w=0.005, wfn=lambda u: 1 - u) * frame, depth=0.05)
    # 血琥珀（凸圆面）：里面有深浅不一的云絮，底部透火
    gem = c.teardrop(cx, cy + 0.015, 0.165)
    c.gem(gem, (112, 12, 10))
    cloud = np.clip(c._noise(0.012) * 1.4 + 0.5, 0, 1)
    c.color = np.where(gem[..., None] > 0.5, (np.array([70, 6, 6])[None, None, :] * (1 - cloud[..., None]) + np.array([132, 22, 14])[None, None, :] * cloud[..., None]), c.color)
    ember = _blur(c.ellipse(cx, cy + 0.1, 0.09, 0.06), 0.03) * gem
    c.emit += ember[..., None] * np.array([0.55, 0.18, 0.04])[None, None, :]
    # 四颗爪钉压住琥珀
    for a in (0.6, 2.54, 1.57, 4.71):
        r = 0.16 if a != 4.71 else 0.2
        x, y = cx + r * math.cos(a) * 0.62, cy + 0.06 + r * math.sin(a) * 0.8
        c.add(c.circle(x, y, 0.016), 'oldgold', h=0.6, bevel=0.01)
    c.bail(cx, cy - 0.4, 'darkiron', r=0.028, w=0.015, h=0.4, down=0.04)
    c.hammer(0.015)
    c.scratches(70)
    c.patina((60, 40, 30), 0.3)
    return c.save(path, chip=0.6, **DARK)


def orb(path):
    c = Canvas(33)
    cx, cy, R = 0.5, 0.42, 0.14
    # 底下两条短链挂的小辉石（先画，在后面）
    for s, L in ((-1, 0.2), (1, 0.27)):
        x0, y0 = cx + s * 0.05, cy + R * 0.95
        x1, y1 = cx + s * 0.1, y0 + L
        c.chain((x0, y0), (x1, y1 - 0.03), 'iron', link=0.04, w=0.009, h=0.1)
        c.add(c.ellipse(x1, y1 - 0.022, 0.016, 0.01), 'oldgold', h=0.2, bevel=0.008)
        c.orb(x1, y1 + 0.006, 0.028, (80, 120, 210), glow=0.12)
    # 爪托：底杯 + 后面一根爪
    c.add(c.stroke([(cx, cy + R * 1.0), (cx, cy - R * 1.12)], w=0.028, wfn=lambda u: 1 - 0.8 * u), 'darkiron', h=0.2, bevel=0.012)
    c.add(c.ellipse(cx, cy + R * 0.95, R * 0.55, R * 0.3), 'oldgold', h=0.3, bevel=0.02, dome=0.4)
    c.orb(cx, cy, R, (80, 120, 210), glow=0.18)
    for _ in range(12):
        a, rr = c.rng.uniform(0, 2 * math.pi), R * c.rng.uniform(0.1, 0.8) ** 0.7
        c.emit += c.circle(cx + rr * math.cos(a), cy + rr * math.sin(a), c.rng.uniform(0.003, 0.006), soft=0.002)[..., None] * np.array([0.45, 0.55, 0.8])[None, None, :]
    for s in (-1, 1):                                  # 两边的爪
        pts = [(cx + s * R * 0.35, cy + R * 0.98)]
        for u in np.linspace(0, 1, 24):
            a = math.pi / 2 - s * (0.6 + 1.55 * u)
            r = R * (1.06 - 0.16 * u ** 3)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        c.add(c.stroke(pts, w=0.04, wfn=lambda u: 1 - 0.8 * u), 'oldgold', h=0.9, bevel=0.017)
    for s in (-1, 1):                                  # 前面两根短爪，斜着压在球的下半
        c.add(c.stroke([(cx + s * R * 0.2, cy + R * 0.98), (cx + s * R * 0.42, cy + R * 0.55), (cx + s * R * 0.5, cy + R * 0.2)], w=0.03, wfn=lambda u: 1 - 0.85 * u),
              'oldgold', h=0.95, bevel=0.014)
    for s in (-1, 1):                                  # 杯沿两颗铆钉
        c.add(c.circle(cx + s * R * 0.32, cy + R * 0.98, 0.011), 'oldgold', h=1.0, bevel=0.006)
    # 顶上的挂环（接在后面那根爪的尖上）
    c.add(c.ellipse(cx, cy - R * 0.97, 0.045, 0.022), 'oldgold', h=0.7, bevel=0.012, dome=0.3)
    c.bail(cx, cy - R - 0.07, 'oldgold', r=0.026, w=0.014, h=0.75, down=0.03)
    c.hammer(0.012)
    c.scratches(50)
    c.patina((50, 50, 46), 0.3)
    return c.save(path, chip=0.5, tilt=5, **DARK)


def clash(path):
    c = Canvas(34)
    hx, hy = 0.5, 0.56
    sword(c, 0.27, 0.27, 0.76, 0.94, 0.06, 0.0, steel='iron')
    sword(c, 0.73, 0.27, 0.24, 0.94, 0.06, 0.3, steel='iron')
    # 交点的圆扣 + 一颗琥珀（火星凝成的）
    c.add(c.circle(hx, hy, 0.055), 'oldgold', h=0.7, bevel=0.02, dome=0.2)
    c.beads(hx, hy, 0.043, 12, 0.006, h=0.06)
    c.gem(c.circle(hx, hy, 0.026), (200, 110, 30))
    c.glow(c.circle(hx, hy, 0.02), (255, 170, 70), r=0.02, k=0.3)
    # 链子挂上去
    c.chain((hx, hy - 0.06), (hx, 0.14), 'iron', link=0.05, w=0.011, h=0.6)
    c.bail(hx, 0.1, 'iron', r=0.026, w=0.013, h=0.65, down=0.0)
    # 交点一点点火星
    for k in range(6):
        a = -math.pi / 2 + c.rng.uniform(-1.3, 1.3)
        r1 = c.rng.uniform(0.09, 0.14)
        pts = [(hx + (0.06 + (r1 - 0.06) * u) * math.cos(a), hy + (0.06 + (r1 - 0.06) * u) * math.sin(a) + 0.02 * u * u) for u in np.linspace(0, 1, 10)]
        c.wisp(pts, (255, 180, 80), w=0.006, k=0.4, r=0.005, wfn=lambda u: 1 - u, core=0.6)
    c.hammer(0.012)
    c.scratches(60)
    c.patina((58, 52, 40), 0.3)
    return c.save(path, chip=0.5, **DARK)


def main():
    os.makedirs(OUT, exist_ok=True)
    from PIL import Image
    ims = []
    for name, f in (('dr_gale', gale), ('dr_bloodburn', bloodburn), ('dr_orb', orb), ('dr_clash', clash)):
        ims.append(f(os.path.join(OUT, 'charm_' + name + '.png')))
        print('画好', name)
    sheet = Image.new('RGBA', (160 * 4, 160), (40, 36, 30, 255))
    for k, im in enumerate(ims):
        sheet.alpha_composite(im, (k * 160, 0))
    sheet.save(os.path.join(OUT, 'charm_sheet.png'))
    sheet.resize((1280, 320), Image.LANCZOS).save(os.path.join(OUT, 'charm_sheet_x2.png'))


if __name__ == '__main__':
    main()
