# -*- coding: utf-8 -*-
"""用户手工抠的字样（原图缩到 2000×1210 的透明 PNG/WebP，2026-11-05）→ logo_letters.png（2532×1532，原位置）。
透明通道放大回原尺寸，颜色取原版 Logo（比缩放过的清晰）；然后：
  · 字母本体 = 不透明的大块（加 ™ 这种小而亮的块）；本体外面的全清掉：离散的暗斑、上下弧线的淡影（用户「离散的黑斑自动去除」）；
  · 字母上半透明的亮像素补成不透明（ELDEN 的 N 斜笔有一片透出背景）；字里的裂纹是原版纹理，不动。
用法：python clean_cut.py <用户抠的图> <原版 Logo PNG> <输出 PNG>"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

W, H = 2532, 1532
TM = (2445, 495, 2525, 555)     # G 右上角的 ™（原图坐标）


def clean(user, orig):
    A = np.asarray(Image.open(user).convert('RGBA').resize((W, H), Image.LANCZOS)).astype(np.float32)[..., 3]
    o = np.asarray(Image.open(orig).convert('RGB')).astype(np.float32)
    mx = o.max(-1)
    r = np.maximum(o[..., 0], 1)
    gr, br = o[..., 1] / r, o[..., 2] / r
    # 门槛不能高：ELDEN 的 N 斜笔、™ 在手工图里是半透明的（第一次用 180，斜笔被当残留清掉了）；半透明的块靠原图亮度和暗斑分开
    solid = A > 70
    lab, n = ndimage.label(solid)
    idx = range(1, n + 1)
    size = ndimage.sum(solid, lab, idx)
    lum = ndimage.mean(mx, lab, idx)
    big = [i for i in range(n) if size[i] > 3000]
    rows = np.nonzero(np.isin(lab, [i + 1 for i in big]).any(1))[0]
    top, bot = rows.min() - 170, rows.max() + 170                # 字母那一行（™ 在 G 右上角，比字母高一点）
    cy = [c[0] for c in ndimage.center_of_mass(solid, lab, idx)]
    keep = [i for i in range(n) if top <= cy[i] <= bot and size[i] > 25 and lum[i] > 120]
    core = np.isin(lab, [i + 1 for i in keep])
    near = ndimage.binary_dilation(core, iterations=4)
    out = np.where(near, A, 0.0)
    # 半透明的亮字母像素补成不透明
    letter = (mx > 100) & (gr > 0.70) & (br < 0.90)
    fix = ndimage.binary_dilation(core, iterations=10) & letter & (A > 30) & (A < 250)
    fix = ndimage.binary_opening(fix, structure=np.ones((3, 3)))
    out = np.where(fix, 255.0, out)
    # ™：灰色、比字母暗，按上面的亮度筛不出来；位置固定，框里按原图亮度取（黑底变透明）
    x0, y0, x1, y1 = TM
    out[y0:y1, x0:x1] = np.clip(mx[y0:y1, x0:x1] / 110.0, 0, 1) * 255
    out = ndimage.gaussian_filter(out, 0.5)
    stats = dict(comps=n, kept=len(keep), dropped=n - len(keep), fixed=int(fix.sum()), cleared=int(((A > 8) & ~near).sum()))
    return Image.fromarray(np.dstack([o, out]).astype(np.uint8)), stats


if __name__ == '__main__':
    img, st = clean(sys.argv[1], sys.argv[2])
    img.save(sys.argv[3])
    print(st)
