# -*- coding: utf-8 -*-
"""试做第二批：不用吊坠底板，每个词条画成一件独立的东西（用户 2026-11-11「可以不统一成吊坠风格么」）。
疾风 = 带风的鹰羽；燃血 = 裂缝里透火的心脏；凝聚 = 铁爪托着的辉石球 + 两颗环绕的小球；相杀 = 交叉相击、迸出火星的两把剑"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import Canvas  # noqa: E402

OUT = os.path.join(HERE, 'out')


def _unit(dx, dy):
    L = math.hypot(dx, dy)
    return dx / L, dy / L


def gale(path):
    """鹰羽：羽轴 + 两侧羽片（一边宽一边窄）+ 羽枝细纹 + 几道裂口 + 深色横斑；旁边绕两道风"""
    c = Canvas(21)
    x0, y0, x1, y1 = 0.24, 0.92, 0.75, 0.07
    ux, uy = _unit(x1 - x0, y1 - y0)
    px, py = -uy, ux                          # 羽轴的法向（指向右下）

    def P(t):
        bend = 0.05 * math.sin(math.pi * t)
        return x0 + (x1 - x0) * t + px * bend, y0 + (y1 - y0) * t + py * bend

    t0 = 0.2
    ts = np.linspace(t0, 1, 60)

    def wv(t):
        s = (t - t0) / (1 - t0)
        return 0.14 * math.sin(math.pi * min(1.0, s ** 0.7)) ** 0.75 + 0.012 * (s < 0.98)

    left = [(P(t)[0] + px * wv(t), P(t)[1] + py * wv(t)) for t in ts]
    right = [(P(t)[0] - px * wv(t) * 0.78, P(t)[1] - py * wv(t) * 0.78) for t in ts]
    vane = c.poly(left + right[::-1] + [P(t0)])
    # 裂口：顺着羽枝方向切进去的细楔
    for t, side in ((0.42, 1), (0.63, -1), (0.78, 1), (0.55, 1)):
        bx, by = P(t)
        k = wv(t) * (1 if side > 0 else 0.78)
        ox, oy = bx + side * px * k * 1.05 + ux * 0.05, by + side * py * k * 1.05 + uy * 0.05
        ix, iy = bx + side * px * k * 0.35, by + side * py * k * 0.35
        wedge = c.poly([(ox, oy), (ix, iy), (ox - ux * 0.022, oy - uy * 0.022)])
        vane = np.clip(vane - wedge, 0, 1)
    c.add(vane, 'feather', h=0.0, bevel=0.03, dome=0.25)
    # 深色横斑（鹰羽的花纹）+ 羽尖发暗
    bands = np.zeros_like(c.h)
    for t, bw in ((0.35, 0.022), (0.47, 0.03), (0.6, 0.026), (0.72, 0.034), (0.85, 0.028)):
        bx, by = P(t)
        j1, j2 = c.rng.normal(0, 0.012, 2)
        bands = np.maximum(bands, c.stroke([(bx + px * 0.17 + ux * (0.035 + j1), by + py * 0.17 + uy * (0.035 + j1)), (bx + px * 0.07 + ux * 0.012, by + py * 0.07 + uy * 0.012),
                                            (bx, by), (bx - px * 0.14 + ux * (0.035 + j2), by - py * 0.14 + uy * (0.035 + j2))], w=bw, wfn=lambda u: 0.7 + 0.5 * math.sin(math.pi * u)))
    bands = bands * np.clip(0.55 + c._noise(0.006) * 1.2, 0, 1)
    c.tint(bands * vane, (70, 62, 54), 0.85)
    tipm = c.circle(x1, y1, 0.13) * vane
    c.tint(tipm, (52, 48, 44), 0.6)
    # 羽枝细纹：从羽轴斜着往外、往前
    for t in np.arange(t0 + 0.01, 0.99, 0.015):
        bx, by = P(t)
        for side, kk in ((1, 1.0), (-1, 0.78)):
            k = wv(t) * kk
            c.engrave(c.stroke([(bx, by), (bx + side * px * k + ux * 0.045, by + side * py * k + uy * 0.045)], w=0.0042), depth=0.055, soft=0.0008)
    # 根部的绒毛
    for i in range(14):
        t = c.rng.uniform(0.12, 0.26)
        bx, by = P(t)
        side = c.rng.choice([-1, 1])
        L = c.rng.uniform(0.04, 0.08)
        a = c.rng.uniform(-0.5, 0.5)
        ex, ey = bx + side * px * L + ux * L * a, by + side * py * L + uy * L * a
        c.add(c.stroke([(bx, by), ((bx + ex) / 2 + c.rng.normal(0, 0.01), (by + ey) / 2 + c.rng.normal(0, 0.01)), (ex, ey)], w=0.012, wfn=lambda u: 1 - u * 0.85),
              'feather', h=0.05, bevel=0.006)
    # 羽轴：根部（羽管）发白、半透明，往尖上越来越细
    shaft = c.stroke([P(t) for t in np.linspace(0, 0.97, 50)], w=0.022, wfn=lambda u: 1 - 0.75 * u)
    c.add(shaft, 'bone', h=0.18, bevel=0.012)
    c.tint(shaft * c.circle(x0, y0, 0.2), (200, 192, 172), 0.6, gloss=0.4)
    # 风：两道绕过羽毛的淡光
    for k, (cx, cy, r, a0, a1) in enumerate(((0.52, 0.5, 0.3, 2.2, 4.6), (0.47, 0.56, 0.36, 2.6, 4.1))):
        pts = [(cx + r * math.cos(a) * 1.0, cy + r * math.sin(a) * 0.55) for a in np.linspace(a0, a1, 50)]
        pts = Canvas.rot(pts, cx, cy, -0.9)
        c.wisp(pts, (190, 214, 230), w=0.012 - 0.003 * k, k=0.55, r=0.01, core=0.6)
    c.hammer(0.01)
    return c.save(path, chip=0.6, grit=0.25)


def bloodburn(path):
    """心脏：心房 + 心室 + 心尖，上面几根血管；表面的冠状血管凸起，裂缝里透出火光，血管口冒火"""
    c = Canvas(22)
    # 血管（在心脏后面先画）
    tubes = [((0.47, 0.4), (0.45, 0.22), (0.36, 0.17), (0.3, 0.24), 0.075),     # 主动脉弓
             ((0.58, 0.42), (0.6, 0.27), (0.66, 0.2), None, 0.065),               # 肺动脉
             ((0.37, 0.45), (0.31, 0.36), (0.27, 0.3), None, 0.055)]              # 上腔静脉
    ends = []
    for a, b, cc, d, w in tubes:
        pts = [a, b, cc] + ([d] if d else [])
        sm = []
        for i in range(len(pts) - 1):
            for u in np.linspace(0, 1, 12, endpoint=False):
                sm.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u))
        sm.append(pts[-1])
        c.add(c.stroke(sm, w=w), 'flesh', h=0.05, bevel=w / 2)
        ends.append((pts[-1], w))
    for (ex, ey), w in ends:                 # 血管口：黑洞 + 一圈唇
        c.add(c.circle(ex, ey, w * 0.58), 'flesh', h=0.12, bevel=0.01)
        c.engrave(c.circle(ex, ey, w * 0.36), depth=0.3)
        c.tint(c.circle(ex, ey, w * 0.36), (20, 6, 4), 1.0)
    # 心脏主体
    body = np.clip(c.ellipse(0.5, 0.58, 0.2, 0.22) + c.circle(0.38, 0.45, 0.12) + c.circle(0.6, 0.46, 0.13)
                   + c.poly([(0.32, 0.6), (0.68, 0.56), (0.58, 0.85), (0.53, 0.89)]), 0, 1)
    body = np.clip(c._arr(__import__('PIL.Image', fromlist=['Image']).fromarray((body * 255).astype(np.uint8)).rotate(12, center=(320, 360)), 0.003), 0, 1)
    c.add(body, 'flesh', h=0.12, bevel=0.06, dome=0.9)
    # 心室之间的沟 + 冠状血管
    c.engrave(c.stroke([(0.5, 0.42), (0.49, 0.55), (0.52, 0.7), (0.56, 0.84)], w=0.016), depth=0.08)
    for pts in ([(0.5, 0.43), (0.47, 0.55), (0.5, 0.68), (0.54, 0.8)], [(0.48, 0.52), (0.4, 0.6), (0.38, 0.7)],
                [(0.5, 0.62), (0.6, 0.66), (0.63, 0.74)], [(0.36, 0.48), (0.32, 0.58)]):
        sm = []
        for i in range(len(pts) - 1):
            for u in np.linspace(0, 1, 10, endpoint=False):
                sm.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u))
        sm.append(pts[-1])
        c.relief(c.stroke(sm, w=0.014, wfn=lambda u: 1 - 0.6 * u), h=0.06, soft=0.002)
    c.tint(body, (112, 26, 22), 0.5, gloss=0.6)
    # 燃烧：裂缝透火 + 血管口冒火
    c.cracks(np.clip(body - c.circle(0.5, 0.36, 0.06), 0, 1) * (c.ellipse(0.5, 0.62, 0.19, 0.22) > 0.5), (255, 132, 36), n=6, k=1.0, w=0.007)
    for (ex, ey), w in ends:
        for j in range(3):
            dx = (j - 1) * w * 0.35
            fp = [(ex + dx + 0.012 * math.sin(u * 5 + j), ey - 0.01 - u * (0.09 + 0.03 * (j == 1))) for u in np.linspace(0, 1, 20)]
            c.wisp(fp, (255, 120 + 40 * (j == 1), 30), w=w * 0.5, k=0.75, r=0.012, wfn=lambda u: 1 - u, core=0.7)
    c.hammer(0.012)
    return c.save(path, chip=0.4, grit=0.3)


def orb(path):
    """凝聚：铁爪托着一颗大辉石球，两颗小球顺着轨道环绕"""
    c = Canvas(23)
    cx, cy, R = 0.5, 0.48, 0.155
    # 柄
    c.add(c.stroke([(0.5, 0.95), (0.5, 0.7)], w=0.04, wfn=lambda u: 0.8 + 0.2 * u), 'darkiron', h=0.0, bevel=0.02)
    c.add(c.ellipse(0.5, 0.71, 0.06, 0.03), 'darkiron', h=0.12, bevel=0.015)
    c.add(c.ellipse(0.5, 0.85, 0.035, 0.018), 'darkiron', h=0.12, bevel=0.01)

    def side_prong(s):
        """两边的爪：从柄头出来，贴着球的轮廓往上包，过了赤道往里勾"""
        pts = [(0.5 + s * 0.015, 0.7), (0.5 + s * 0.07, 0.665)]
        for u in np.linspace(0, 1, 30):
            a = math.pi / 2 - s * (0.75 + 1.55 * u)
            r = R * (1.06 - 0.16 * u ** 3)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return c.stroke(pts, w=0.036, wfn=lambda u: 1 - 0.85 * u)

    # 后面一根爪（露出顶上一点）
    c.add(c.stroke([(0.5, 0.7), (0.5, cy - R * 1.1)], w=0.03, wfn=lambda u: 1 - 0.8 * u), 'darkiron', h=0.0, bevel=0.012)
    c.orb(cx, cy, R, (90, 140, 255), glow=0.45)
    # 球里的碎光（辉石里的星点）
    for _ in range(14):
        a, rr = c.rng.uniform(0, 2 * math.pi), R * c.rng.uniform(0.1, 0.8) ** 0.7
        sx, sy = cx + rr * math.cos(a), cy + rr * math.sin(a)
        c.emit += c.circle(sx, sy, c.rng.uniform(0.003, 0.007), soft=0.002)[..., None] * np.array([0.6, 0.75, 1.0])[None, None, :]
    for s in (-1, 1):
        c.add(side_prong(s), 'darkiron', h=0.75, bevel=0.016)
    # 前面一根短爪，压在球的下半
    c.add(c.stroke([(0.5, 0.7), (0.497, 0.6), (0.5, cy + R * 0.25)], w=0.04, wfn=lambda u: 1 - 0.85 * u), 'darkiron', h=0.85, bevel=0.018)
    # 轨道 + 两颗小球
    def orbit(a0, a1):
        pts = [(cx + 0.36 * math.cos(a), cy + 0.13 * math.sin(a)) for a in np.linspace(a0, a1, 40)]
        return Canvas.rot(pts, cx, cy, -0.35)
    c.wisp(orbit(2.4, 3.55), (120, 170, 255), w=0.01, k=0.5, r=0.01, wfn=lambda u: u ** 1.5, core=0.5)
    c.wisp(orbit(5.2, 6.6), (120, 170, 255), w=0.01, k=0.5, r=0.01, wfn=lambda u: u ** 1.5, core=0.5)
    for a, r in ((3.6, 0.045), (6.65, 0.04)):
        (x, y), = Canvas.rot([(cx + 0.36 * math.cos(a), cy + 0.13 * math.sin(a))], cx, cy, -0.35)
        c.orb(x, y, r, (110, 160, 255), glow=0.55)
    c.hammer(0.012)
    c.scratches(40)
    return c.save(path, chip=0.5)


def sword(c, x0, y0, x1, y1, w, h, steel='steel'):
    """一把独立的剑：刀身带中棱 + 血槽，金护手，皮握柄缠绳，柄头。(x0,y0) 柄头，(x1,y1) 剑尖"""
    ux, uy = _unit(x1 - x0, y1 - y0)
    px, py = -uy, ux
    L = math.hypot(x1 - x0, y1 - y0)
    g = 0.25
    gx, gy = x0 + (x1 - x0) * g, y0 + (y1 - y0) * g
    hw = w / 2
    blade = c.poly([(gx + px * hw, gy + py * hw), (x1 - ux * w * 1.6 + px * hw * 0.9, y1 - uy * w * 1.6 + py * hw * 0.9), (x1, y1),
                    (x1 - ux * w * 1.6 - px * hw * 0.9, y1 - uy * w * 1.6 - py * hw * 0.9), (gx - px * hw, gy - py * hw)])
    c.add(blade, steel, h=h, bevel=hw, profile='ridge')
    c.engrave(c.stroke([(gx + ux * 0.03, gy + uy * 0.03), (gx + ux * L * 0.45, gy + uy * L * 0.45)], w=w * 0.18), depth=0.06)
    grip = c.stroke([(x0 + ux * 0.04, y0 + uy * 0.04), (gx, gy)], w=w * 0.62)
    c.add(grip, 'leather', h=h, bevel=w * 0.3)
    for t in np.arange(0.05, g * L - 0.01, 0.017):
        c.engrave(c.stroke([(x0 + ux * t + px * w * 0.32, y0 + uy * t + py * w * 0.32), (x0 + ux * (t + 0.01) - px * w * 0.32, y0 + uy * (t + 0.01) - py * w * 0.32)], w=0.004), depth=0.05)
    gw = w * 1.55
    guard = c.stroke([(gx + px * gw + ux * 0.012, gy + py * gw + uy * 0.012), (gx, gy), (gx - px * gw + ux * 0.012, gy - py * gw + uy * 0.012)], w=w * 0.42)
    c.add(guard, 'oldgold', h=h + 0.05, bevel=w * 0.2)
    for s in (1, -1):
        c.add(c.circle(gx + s * px * gw + ux * 0.012, gy + s * py * gw + uy * 0.012, w * 0.3), 'oldgold', h=h + 0.07, bevel=w * 0.15)
    c.add(c.circle(x0 + ux * 0.03, y0 + uy * 0.03, w * 0.45), 'oldgold', h=h + 0.05, bevel=w * 0.25)
    return blade


def clash(path):
    """相杀：两把剑交叉相击，交点迸出火星"""
    c = Canvas(24)
    b1 = sword(c, 0.17, 0.88, 0.83, 0.12, 0.072, 0.0)
    b2 = sword(c, 0.83, 0.88, 0.17, 0.12, 0.072, 0.3)
    # 交点上的豁口
    hit = (0.5, 0.505)
    c.engrave(c.circle(hit[0], hit[1] - 0.02, 0.012) * b1, depth=0.1)
    # 火星：几道放射的亮线 + 中间一团光
    for k in range(13):
        a = c.rng.uniform(0, 2 * math.pi)
        r0, r1 = 0.025, c.rng.uniform(0.09, 0.2)
        bend = c.rng.normal(0, 0.15)
        pts = [(hit[0] + (r0 + (r1 - r0) * u) * math.cos(a + bend * u), hit[1] + (r0 + (r1 - r0) * u) * math.sin(a + bend * u) + 0.03 * u * u)
               for u in np.linspace(0, 1, 16)]
        c.wisp(pts, (255, 196, 90), w=c.rng.uniform(0.005, 0.009), k=0.65, r=0.006, wfn=lambda u: 1 - u, core=0.9)
    c.glow(c.circle(hit[0], hit[1], 0.03), (255, 210, 120), r=0.04, k=0.8)
    c.glow(c.circle(hit[0], hit[1], 0.012), (255, 245, 220), r=0.008, k=1.0)
    c.hammer(0.01)
    c.scratches(60)
    return c.save(path, chip=0.5)


def main():
    os.makedirs(OUT, exist_ok=True)
    from PIL import Image
    ims = []
    for name, f in (('dr_gale', gale), ('dr_bloodburn', bloodburn), ('dr_orb', orb), ('dr_clash', clash)):
        ims.append(f(os.path.join(OUT, 'obj_' + name + '.png')))
        print('画好', name)
    sheet = Image.new('RGBA', (160 * 4, 160), (40, 36, 30, 255))
    for k, im in enumerate(ims):
        sheet.alpha_composite(im, (k * 160, 0))
    sheet.save(os.path.join(OUT, 'obj_sheet.png'))
    sheet.resize((1280, 320), Image.LANCZOS).save(os.path.join(OUT, 'obj_sheet_x2.png'))


if __name__ == '__main__':
    main()
