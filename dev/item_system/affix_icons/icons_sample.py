# -*- coding: utf-8 -*-
"""试做 4 个新词条图标（给用户看风格）：疾风 / 燃血 / 凝聚 / 相杀"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iconkit import Canvas  # noqa: E402

OUT = os.path.join(HERE, 'out')


def sword(c, x0, y0, x1, y1, w=0.05):
    """一把剑：剑身（尖头）+ 护手 + 握柄 + 柄头 + 血槽。(x0,y0) 柄头端，(x1,y1) 剑尖"""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    g = 0.24
    gx, gy = x0 + dx * g, y0 + dy * g
    blade = [(gx + px * w / 2, gy + py * w / 2), (x1 - ux * w * 1.8 + px * w / 2, y1 - uy * w * 1.8 + py * w / 2), (x1, y1),
             (x1 - ux * w * 1.8 - px * w / 2, y1 - uy * w * 1.8 - py * w / 2), (gx - px * w / 2, gy - py * w / 2)]
    gw = w * 1.45
    guard = [(gx + px * gw - ux * w * 0.4, gy + py * gw - uy * w * 0.4), (gx + px * gw * 1.08 + ux * w * 0.5, gy + py * gw * 1.08 + uy * w * 0.5),
             (gx - px * gw * 1.08 + ux * w * 0.5, gy - py * gw * 1.08 + uy * w * 0.5), (gx - px * gw - ux * w * 0.4, gy - py * gw - uy * w * 0.4)]
    grip = [(x0 + ux * 0.035 + px * w * 0.34, y0 + uy * 0.035 + py * w * 0.34), (gx + px * w * 0.34, gy + py * w * 0.34),
            (gx - px * w * 0.34, gy - py * w * 0.34), (x0 + ux * 0.035 - px * w * 0.34, y0 + uy * 0.035 - py * w * 0.34)]
    fuller = c.stroke([(gx + ux * 0.04, gy + uy * 0.04), (x1 - ux * w * 3.0, y1 - uy * w * 3.0)], w=w * 0.22)
    wraps = [c.stroke([(x0 + ux * t + px * w * 0.34, y0 + uy * t + py * w * 0.34), (x0 + ux * (t + 0.012) - px * w * 0.34, y0 + uy * (t + 0.012) - py * w * 0.34)], w=0.004)
             for t in [0.05 + 0.018 * i for i in range(int((g * L - 0.06) / 0.018))]]
    return c.poly(blade), c.poly(guard), c.poly(grip), c.circle(x0 + ux * 0.025, y0 + uy * 0.025, w * 0.62), fuller, wraps


def gale(path):
    c = Canvas(11)
    c.plate('round', 'bronze', size=0.86)
    c.beads(0.5, 0.53, 0.35, 36, 0.009, h=0.1)
    # 三道风：卷曲的头 + 拖长的尾，越往下越大
    for k, (cy, r) in enumerate(((0.39, 0.075), (0.53, 0.105), (0.67, 0.085))):
        cx = 0.36 + 0.03 * k
        curl = Canvas.spiral(cx, cy, 0.012, r, 1.25, start=math.pi * 0.6, n=110)
        ex, ey = curl[-1]
        tail = [(ex + i * 0.035, ey - 0.006 * i + 0.012 * math.sin(i * 0.9)) for i in range(1, 9)]
        c.emboss(c.stroke(curl + tail, w=0.034, taper=True), h=0.3, line=0.004, soft=0.003)
    for y in (0.31, 0.47, 0.6, 0.75):
        c.engrave(c.stroke([(0.3, y + 0.01), (0.5, y - 0.004), (0.72, y - 0.018)], w=0.005), depth=0.06)
    c.hammer(0.025)
    c.scratches(70)
    c.patina((70, 104, 84), 0.45)
    return c.save(path)


def bloodburn(path):
    c = Canvas(12)
    c.plate('drop', 'darkiron', size=0.86, cy=0.53)
    # 火焰：几条往上卷的舌头（S 形、根粗尖细）
    fl = c.ellipse(0.5, 0.71, 0.15, 0.08)          # 火焰：一团火身 + 往上卷的几条火舌
    for dx, hgt, sw, w in ((-0.12, 0.24, -1, 0.07), (-0.06, 0.33, 1, 0.08), (0.0, 0.42, -1, 0.09), (0.065, 0.32, 1, 0.08), (0.125, 0.23, 1, 0.07)):
        x0, y0 = 0.5 + dx * 0.8, 0.76
        fp = [(x0 + sw * 0.028 * math.sin(t * math.pi * 1.4) + dx * 0.5 * t, y0 - hgt * t) for t in np.linspace(0, 1, 30)]
        fl = np.maximum(fl, c.stroke(fp, w=w, taper=True))
    fl = fl * c.inner
    c.emboss(fl, h=0.22, line=0.005)
    c.tint(fl, (150, 60, 24), 0.5)
    # 血滴（浮雕 + 暗红釉 + 光泽 + 一点红光）
    dm = c.teardrop(0.5, 0.53, 0.13)
    c.emboss(dm, h=0.42, line=0.006)
    c.tint(dm, (110, 10, 8), 1.0, gloss=1.0)
    c.glow(dm, (190, 30, 16), r=0.045, k=0.45)
    c.hammer(0.03)
    c.scratches(80)
    c.patina((96, 54, 34), 0.4)
    return c.save(path)


def orb(path):
    c = Canvas(13)
    ringm = c.ring(0.5, 0.54, 0.27, 0.06)
    c.add(ringm, 'silver', h=0.1, bevel=0.03, dome=0.6)
    for k in range(24):                      # 环上的刻纹
        a = k / 24 * 2 * math.pi
        c.engrave(c.stroke([(0.5 + 0.245 * math.cos(a), 0.54 + 0.245 * math.sin(a)), (0.5 + 0.295 * math.cos(a + 0.08), 0.54 + 0.295 * math.sin(a + 0.08))], w=0.005), depth=0.05)
    loop = c.ring(0.5, 0.235, 0.032, 0.018)
    c.add(loop, 'silver', h=0.15, bevel=0.008)
    for k in range(3):
        a = -math.pi / 2 + k * 2 * math.pi / 3 + math.pi / 3
        x, y = 0.5 + 0.27 * math.cos(a), 0.54 + 0.27 * math.sin(a)
        c.add(c.circle(x, y, 0.085), 'oldgold', h=0.22, bevel=0.025)
        for j in range(4):                   # 爪托的四个爪
            b = a + j * math.pi / 2 + math.pi / 4
            c.relief(c.circle(x + 0.072 * math.cos(b), y + 0.072 * math.sin(b), 0.016), h=0.2)
        c.orb(x, y, 0.06, (96, 150, 255), glow=0.6)
    c.hammer(0.015)
    c.scratches(50)
    c.patina((70, 72, 80), 0.3)
    return c.save(path)


def clash(path):
    c = Canvas(14)
    c.plate('diamond', 'gold', size=0.86)
    c.hatch(c.inner, angle=0.5, gap=0.02, w=0.003, depth=0.02)
    # 两把剑交叉：先画一把，第二把压在上面（emboss 的轮廓缝会切进第一把，看起来就是叠在上面）
    for (x0, y0, x1, y1) in ((0.3, 0.78, 0.72, 0.25), (0.7, 0.78, 0.28, 0.25)):
        blade, guard, grip, pommel, fuller, wraps = sword(c, x0, y0, x1, y1, w=0.064)
        whole = np.clip(blade + guard + grip + pommel, 0, 1)
        top = c.h.copy()
        c.h = np.where(whole > 0.5, np.minimum(c.h, 0.42), c.h)   # 压在上面的那把先把底下削平
        c.emboss(whole, h=0.3, line=0.006)
        c.relief(np.clip(guard + pommel, 0, 1), h=0.1)
        c.engrave(fuller, depth=0.07)
        for wm in wraps:
            c.engrave(wm, depth=0.05)
        del top
    c.hammer(0.02)
    c.scratches(70)
    c.patina((92, 80, 40), 0.35)
    return c.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    from PIL import Image
    ims = []
    for name, f in (('dr_gale', gale), ('dr_bloodburn', bloodburn), ('dr_orb', orb), ('dr_clash', clash)):
        ims.append(f(os.path.join(OUT, name + '.png')))
        print('画好', name)
    sheet = Image.new('RGBA', (160 * 4, 160), (40, 36, 30, 255))
    for k, im in enumerate(ims):
        sheet.alpha_composite(im, (k * 160, 0))
    sheet.save(os.path.join(OUT, 'sample_sheet.png'))
    big = sheet.resize((160 * 4 * 2, 320), Image.LANCZOS)
    big.save(os.path.join(OUT, 'sample_sheet_x2.png'))


if __name__ == '__main__':
    main()
