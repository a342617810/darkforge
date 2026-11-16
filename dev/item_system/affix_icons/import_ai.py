# -*- coding: utf-8 -*-
"""把 AI 生成的词条图标（Nano Banana 等，纯色底的 JPG / PNG）变成游戏用的 160×160 透明 PNG（用户 2026-11-13）。
提示词见同目录 护符图标提示词.md（直接交给图像生成 AI；要求纯灰底、无投影，按 01~67 编号）。

做法：
  1. 背景：取图片四周一圈的颜色，按位置拟合成平滑曲面（容得下轻微的渐变 / 暗角）。
  2. 像素离背景色多远 + 周围有没有纹理：离得近又平滑的算背景候选；连到图片边上的、或者面积够大的（物件中间镂空的洞，比如羽毛的缝）
     都算背景，别的（颜色碰巧和背景接近、但有纹理的金属）留着。
  3. 边缘一圈按离背景色的远近给半透明，并把混进去的背景色减掉（不留灰边）。
  4. 裁到物件，最长边缩到 160 的 fit（默认 0.9，同 icons_charm.DARK），居中放进 160×160。

用法：python import_ai.py <图片> <词条键> [--out 目录]（默认写 out_ai\\charm_<键>.png 和预览 out_ai\\preview_<键>.png；
      确认后加 --apply 写进 out\\charm_<键>.png，再跑 ..\\make_frames.py 接进游戏）"""
import argparse
import os

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE, FIT = 160, 0.9


def bg_model(a, band):
    """四周一圈拟合二次曲面（每个通道一个），返回整张图的背景色"""
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    m = np.zeros((h, w), bool)
    m[:band], m[-band:], m[:, :band], m[:, -band:] = True, True, True, True
    x, y = xx[m] / w - 0.5, yy[m] / h - 0.5
    A = np.stack([np.ones_like(x), x, y, x * x, y * y, x * y], 1)
    X, Y = xx / w - 0.5, yy / h - 0.5
    B = np.stack([np.ones_like(X), X, Y, X * X, Y * Y, X * Y], -1)
    out = np.zeros_like(a)
    noise = 0.0
    for c in range(3):
        coef, *_ = np.linalg.lstsq(A, a[..., c][m], rcond=None)
        out[..., c] = B @ coef
        noise = max(noise, float(np.std(a[..., c][m] - A @ coef)))
    return out, noise


def matte(a, t1=None, t2=None, smooth=4.0, hole_frac=0.0006, small_frac=0.00004):
    h, w, _ = a.shape
    bg, noise = bg_model(a, max(4, int(0.03 * min(h, w))))
    d = np.sqrt(((a - bg) ** 2).sum(-1))
    t1 = t1 if t1 is not None else max(9.0, 6.0 * noise)
    t2 = t2 if t2 is not None else t1 * 3.5
    lum = a.mean(-1)
    # 纹理窗口要小（σ=1）：羽毛缝这种十来个像素宽的细缝，窗口大了会把两边金属的边算进来，缝就被当成金属
    mu = ndimage.gaussian_filter(lum, 1)
    tex = np.sqrt(np.clip(ndimage.gaussian_filter(lum * lum, 1) - mu * mu, 0, None))
    cand = (d < t1) & (tex < smooth)
    lab, n = ndimage.label(cand)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    md = ndimage.mean(d, lab, range(1, n + 1))
    mt = ndimage.mean(tex, lab, range(1, n + 1))
    keep = np.zeros(n + 1, bool)
    for i in range(1, n + 1):
        # 连到图边上的、够大的洞；小洞（羽毛的细缝这种，用户 2026-11-13 第一张就有）要几乎就是背景色、几乎没有纹理才算
        if i in edge or sizes[i - 1] > hole_frac * h * w or \
                (sizes[i - 1] > small_frac * h * w and md[i - 1] < t1 * 0.85 and mt[i - 1] < smooth * 0.5):
            keep[i] = True
    bgm = keep[lab]
    # 背景区域边上那些「没那么像背景」但其实是背景的像素（JPG 噪声）：在背景附近 2 像素内、离背景色 < t1 × 1.5 的并进来
    near = ndimage.binary_dilation(bgm, iterations=2)
    bgm |= near & (d < t1 * 1.5)
    obj = ~bgm
    # 物件里的小针眼（< 0.02%）填上，零散的小点（< 0.02%）去掉
    lab_o, no = ndimage.label(obj)
    if no:
        so = ndimage.sum(np.ones_like(lab_o), lab_o, range(1, no + 1))
        big = np.zeros(no + 1, bool)
        big[1:] = so > 0.0002 * h * w
        obj = big[lab_o]
    holes = ndimage.binary_fill_holes(obj) & ~obj
    lab_h, nh = ndimage.label(holes)
    if nh:
        sh = ndimage.sum(np.ones_like(lab_h), lab_h, range(1, nh + 1))
        small = np.zeros(nh + 1, bool)
        small[1:] = sh < 0.0002 * h * w
        obj |= small[lab_h]
    # 软边：挨着背景 3 像素内的物件像素按离背景色的远近给透明度
    alpha = obj.astype(float)
    band = obj & ndimage.binary_dilation(~obj, iterations=3)
    alpha[band] = np.clip((d[band] - t1) / (t2 - t1), 0.15, 1.0)
    alpha = np.clip(ndimage.gaussian_filter(alpha, 0.6), 0, 1) * ndimage.binary_dilation(obj, iterations=1)
    # 去背景色：I = α·F + (1-α)·B → F = (I - (1-α)·B) / α
    al = np.clip(alpha, 1e-3, 1)[..., None]
    fg = np.clip((a - (1 - al) * bg) / al, 0, 255)
    return fg, alpha, dict(t1=t1, t2=t2, noise=noise)


def to_icon(fg, alpha, size=SIZE, fit=FIT):
    ys, xs = np.nonzero(alpha > 0.5)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    pad = 4
    y0, x0 = max(0, y0 - pad), max(0, x0 - pad)
    y1, x1 = min(alpha.shape[0], y1 + pad), min(alpha.shape[1], x1 + pad)
    rgba = np.dstack([fg * alpha[..., None], alpha * 255])[y0:y1, x0:x1]          # 预乘再缩放，边缘不发灰
    k = fit * size / max(ys.max() + 1 - ys.min(), xs.max() + 1 - xs.min())
    nw, nh = max(1, round((x1 - x0) * k)), max(1, round((y1 - y0) * k))
    im = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA').resize((nw, nh), Image.LANCZOS)
    r = np.asarray(im).astype(float)
    al = r[..., 3:4] / 255
    r[..., :3] = np.where(al > 0, r[..., :3] / np.maximum(al, 1e-3), 0)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.alpha_composite(Image.fromarray(np.clip(r, 0, 255).astype(np.uint8), 'RGBA'), ((size - nw) // 2, (size - nh) // 2))
    return out


def preview(icon, key, old=None):
    """预览：深色底 / 棋盘格 / 原版护符那种底（同 icons_charm 的样张底色），各放大 2 倍；有旧图就并排"""
    tiles = [icon] + ([old] if old is not None else [])
    cells = []
    for t in tiles:
        for bgc in ((40, 36, 30, 255), None):
            c = Image.new('RGBA', (SIZE, SIZE), bgc or (0, 0, 0, 0))
            if bgc is None:
                ck = np.indices((SIZE, SIZE)).sum(0) // 10 % 2
                c = Image.fromarray(np.dstack([np.where(ck, 90, 60)] * 3 + [np.full((SIZE, SIZE), 255)]).astype(np.uint8), 'RGBA')
            c.alpha_composite(t)
            cells.append(c.resize((SIZE * 2, SIZE * 2), Image.LANCZOS))
    sheet = Image.new('RGBA', (SIZE * 2 * len(cells), SIZE * 2), (0, 0, 0, 255))
    for i, c in enumerate(cells):
        sheet.paste(c, (i * SIZE * 2, 0))
    return sheet


def prompt_keys():
    """序号 → 词条键：设计清单.md 表格里词条的先后顺序，从 1 数（护符图标提示词.md 用同一个顺序编号，里面不写键和名字）"""
    import re
    p = os.path.join(HERE, '设计清单.md')
    if not os.path.isfile(p):
        return {}
    keys = re.findall(r'^\| (dr_\w+) \|', open(p, encoding='utf-8').read(), re.M)
    return {i + 1: k for i, k in enumerate(keys)}


def key_of(path, nums):
    """文件名认词条：带 dr_ 键的（dr_gale.jpg、charm_dr_gale.png）或者开头是提示词序号的（01.jpg、01_疾风.png）"""
    import re
    stem = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r'(dr_[a-z0-9_]+)', stem)
    if m:
        return m.group(1)
    m = re.match(r'(\d+)', stem)
    return nums.get(int(m.group(1))) if m else None


def one(src, key, out, fit, apply):
    img = np.asarray(Image.open(src).convert('RGB')).astype(float)
    fg, alpha, info = matte(img)
    icon = to_icon(fg, alpha, fit=fit)
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, 'charm_%s.png' % key)
    icon.save(p)
    old_p = os.path.join(HERE, 'out', 'charm_%s.png' % key)
    old = Image.open(old_p).convert('RGBA') if os.path.isfile(old_p) else None
    preview(icon, key, old).save(os.path.join(out, 'preview_%s.png' % key))
    cov = float((alpha > 0.5).mean())
    edge = max(alpha[0].max(), alpha[-1].max(), alpha[:, 0].max(), alpha[:, -1].max()) > 0.5
    print('%s：背景噪声 %.1f，阈值 %.0f / %.0f，物件占原图 %.1f%%%s → %s' % (
        key, info['noise'], info['t1'], info['t2'], cov * 100, '（物件碰到图边，可能被切了，看预览）' if edge else '', p))
    if apply:
        icon.save(old_p)
        print('   已写进', old_p)
    return icon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image', nargs='?', help='一张图；或者用 --dir 一次处理整个文件夹')
    ap.add_argument('key', nargs='?', help='词条键（dr_gale）；不写就按文件名认')
    ap.add_argument('--dir', help='文件夹里的图片按文件名认词条（dr_ 键或提示词序号）全部处理，最后拼一张总预览')
    ap.add_argument('--out', default=os.path.join(HERE, 'out_ai'))
    ap.add_argument('--fit', type=float, default=FIT)
    ap.add_argument('--apply', action='store_true', help='写进 out\\charm_<键>.png（替换现在的图标）')
    a = ap.parse_args()
    nums = prompt_keys()
    jobs = []
    if a.dir:
        for f in sorted(os.listdir(a.dir)):
            if os.path.splitext(f)[1].lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                k = key_of(f, nums)
                if k:
                    jobs.append((os.path.join(a.dir, f), k))
                else:
                    print('认不出是哪个词条，跳过：', f)
    elif a.image:
        k = a.key or key_of(a.image, nums)
        if not k:
            raise SystemExit('认不出词条：文件名带 dr_ 键或提示词序号，或者第二个参数写键')
        jobs.append((a.image, k))
    else:
        raise SystemExit('给一张图，或者 --dir 文件夹')
    icons = [(k, one(src, k, a.out, a.fit, a.apply)) for src, k in jobs]
    if len(icons) > 1:                       # 总预览：深色底，一行 10 个
        cols = 10
        rows = (len(icons) + cols - 1) // cols
        sheet = Image.new('RGBA', (cols * SIZE, rows * SIZE), (40, 36, 30, 255))
        for i, (_k, im) in enumerate(icons):
            sheet.alpha_composite(im, ((i % cols) * SIZE, (i // cols) * SIZE))
        sheet.save(os.path.join(a.out, '总预览.png'))
        print('总预览：', os.path.join(a.out, '总预览.png'))


if __name__ == '__main__':
    main()
