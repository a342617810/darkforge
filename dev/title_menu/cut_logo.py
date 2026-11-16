# -*- coding: utf-8 -*-
"""从原版标题 Logo（SB_Title_01 的 MENU_Title_EldenRing_01，2532×1532，黑底）抠出「ELDEN RING」字样和 ™，去掉后面的大卢恩。
做法（2026-11-05 第二版，第一版开运算太狠，™ 和字母的衬线、裂纹边被抠掉了）：
  字母主体 = 亮像素开运算（细的卢恩线去掉、粗的笔画留下）；实心字形 = 主体闭运算（字里的裂纹填上，不会透出背景）；
  字母外一圈（主体外扩 14 像素）里再按颜色留：字母是亮的浅米金石纹（绿/红 ≈0.85、蓝/红 ≈0.57），卢恩线暗、偏红（0.75 / 0.41）；
  ™ 在 G 右上角，单独框出来整块留下。输出 logo_letters.png（RGBA，原图颜色，透明背景）和对比图
用法：python cut_logo.py <原版 Logo PNG（2532×1532）> <输出目录>"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage


# (x0, y0, x1, y1)，原图坐标：ELDEN 的 N 左上衬线左边一块、衬线上沿以上一块（整块擦）
ERASE = ((1012, 548, 1043, 645), (1043, 548, 1082, 577))
# 只留字母颜色亮像素的框：ELDEN 的 N 左上衬线尖、右上衬线上面的凸起、斜笔和右竖笔底部的缝（压着卢恩的灰烟）
STRICT = ((1040, 576, 1062, 606), (1234, 548, 1286, 580), (1222, 780, 1284, 812))


def cut(src):
    a = np.asarray(Image.open(src).convert('RGB')).astype(np.float32)
    mx = a.max(-1)
    r = np.maximum(a[..., 0], 1)
    gr, br = a[..., 1] / r, a[..., 2] / r
    bright = mx > 60
    body = ndimage.binary_opening(bright, structure=np.ones((11, 11)))
    # 留下哪些块：先按大块定出字母那一行的上下沿；这一行以外的（卢恩的光点、底下的光芒）丢掉，
    # 这一行里偏红的（卢恩色）丢掉，别的再小也留（裂纹会把一笔分成几小块，第一次按面积筛把 RING 的 N 右竖笔丢了）
    lab, n = ndimage.label(body)
    idx = range(1, n + 1)
    sizes = ndimage.sum(body, lab, idx)
    cy = [c[0] for c in ndimage.center_of_mass(body, lab, idx)]
    g_r = ndimage.mean(gr, lab, idx)
    big = [i for i in range(n) if sizes[i] > 20000]
    rows = np.nonzero(np.isin(lab, [i + 1 for i in big]).any(1))[0]
    top, bot = rows.min() - 30, rows.max() + 30
    cand = [i for i in range(n) if top <= cy[i] <= bot and sizes[i] > 150 and g_r[i] > 0.72]
    # 小块按亮度分：裂纹分开的笔画碎块平均亮度都在 170 以上（RING 的 I 被切成上下两块、N 的竖笔几块），
    # 卢恩上偏黄的亮点都在 120 以下（N 左上角、中轴竖线的一截、N 和 R 之间底部几块）
    lum = ndimage.mean(mx, lab, idx)
    body = np.isin(lab, [i + 1 for i in cand if sizes[i] > 6000 or lum[i] > 150])
    # 字母轮廓（闭运算，字和字之间的空隙比结构大，不会连起来）：字母外那一圈只在轮廓附近留，卢恩线贴着字的那一截不留
    hull = ndimage.binary_closing(body, structure=np.ones((41, 41))) | ndimage.binary_dilation(body, iterations=6)
    near = ndimage.binary_closing(body, structure=np.ones((31, 31))) | ndimage.binary_dilation(body, iterations=3)
    # 字母里风化碎裂的地方是深褐色（原版故意的，RING 的 I、N、G 都有），不能当背景：轮廓里的暗像素按颜色分——
    # 字母的裂纹偏灰（蓝/红 ≈0.50、饱和度 ≈0.5），卢恩的暗光晕又红又艳（0.22、0.78），卢恩的亮斑灰蓝（蓝/红 > 0.9）
    mn = a.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    crack = (mx > 12) & (br > 0.34) & (br < 0.86) & (sat < 0.7)
    fill = near & (bright | crack)
    zone = ndimage.binary_dilation(body, iterations=14) & ndimage.binary_dilation(hull, iterations=8)
    like = (mx > 150) & (gr > 0.76) & (br > 0.42) & (br < 0.86)     # 字母边缘亮；贴着字的卢恩碎屑暗（≤120）
    keep = body | fill | (zone & like & bright)
    # ™：G 的右上角
    ys, xs = np.nonzero(body)
    gx1, gy0 = xs.max(), ys.min()
    tm = np.zeros_like(keep)
    tm[max(0, gy0 - 120):gy0 + 160, gx1 - 120:min(a.shape[1], gx1 + 120)] = True
    tm &= (mx > 40) & ~zone
    lab2, n2 = ndimage.label(tm)
    if n2:
        sizes2 = ndimage.sum(tm, lab2, range(1, n2 + 1))
        big = [i + 1 for i, s in enumerate(sizes2) if s > 30]
        tm = np.isin(lab2, big)
    keep |= ndimage.binary_dilation(tm, iterations=2)
    # 手工擦掉的：ELDEN 的 N 左上衬线末端压着一团卢恩的灰蓝亮斑和暗褐色烟，和字母连在一起分不开（原版 Logo 是固定素材，按坐标擦）
    for x0, y0, x1, y1 in ERASE:
        keep[y0:y1, x0:x1] = False
    strict = (mx > 140) & (gr > 0.76) & (br > 0.42) & (br < 0.8)
    for x0, y0, x1, y1 in STRICT:
        keep[y0:y1, x0:x1] &= strict[y0:y1, x0:x1]
    # 字母上风化出来的洞（原版透出后面卢恩的暗橙光，RING 的 I、N 左边最明显）：轮廓里没留下的填成深褐灰的碎石色、不透明，
    # 不然洞里透出封面的背景，字看起来像被啃掉了（用户 2026-11-05「右边的 I 和 N 抠多了」）
    holes = ndimage.binary_closing(body, structure=np.ones((25, 25))) & ~keep
    for x0, y0, x1, y1 in ERASE + STRICT:
        holes[y0:y1, x0:x1] = False
    lum = a.mean(-1, keepdims=True)
    dark = np.clip(lum, 18, 70) * np.array([0.95, 0.72, 0.50], np.float32)
    a = np.where(holes[..., None], dark, a)
    keep |= holes
    # 透明度：实心字形不透明；外面那圈和 ™ 按亮度（黑底变透明）
    soft = np.clip(mx / 90.0, 0, 1)
    alpha = np.where(fill | holes, 1.0, soft) * keep
    alpha = ndimage.gaussian_filter(alpha, 0.7)
    out = np.dstack([a, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out), int(tm.sum())


def main(src, outdir):
    img, n_tm = cut(src)
    img.save(os.path.join(outdir, 'logo_letters.png'))
    full = Image.open(src).convert('RGBA')
    bg = Image.new('RGBA', full.size, (40, 40, 48, 255))
    bg.alpha_composite(img)
    side = Image.new('RGB', (full.size[0], full.size[1] * 2))
    side.paste(full.convert('RGB'), (0, 0))
    side.paste(bg.convert('RGB'), (0, full.size[1]))
    side.resize((side.size[0] // 2, side.size[1] // 2), Image.LANCZOS).save(os.path.join(outdir, 'cut_compare.png'))
    for k, (x, y, w, h) in enumerate(((1900, 380, 632, 560), (900, 420, 800, 520), (0, 440, 700, 520))):
        c = Image.new('RGB', (w * 2, h))
        c.paste(full.crop((x, y, x + w, y + h)).convert('RGB'), (0, 0))
        c.paste(bg.crop((x, y, x + w, y + h)).convert('RGB'), (w, 0))
        c.save(os.path.join(outdir, 'cut_zoom%d.png' % k))
    print('ok，™ 像素', n_tm)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
