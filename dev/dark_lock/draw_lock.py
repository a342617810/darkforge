# -*- coding: utf-8 -*-
"""画和原版「装备中」标记（MENU_EquMark，40x42，旧黄铜浮雕）同风格的锁：输出 tex/lock.png 和对比图 tex/compare_x8.png"""
import random
from PIL import Image, ImageDraw, ImageFilter, ImageChops

W, H = 40, 42
S = 8                      # 先画 8 倍再缩小
w, h = W * S, H * S

HI = (214, 198, 160)       # 高光（原版剑刃最亮处）
MID = (140, 122, 88)       # 中间调
LOW = (92, 80, 52)         # 暗面
DEEP = (58, 48, 30)        # 更暗
OUT = (14, 10, 6)          # 描边


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shade(mask, top, bottom, light_dir=(-1, -1)):
    """按从左上到右下的渐变给 mask 着色"""
    img = Image.new('RGB', (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / w * 0.35 + y / h * 0.65)
            px[x, y] = lerp(top, bottom, min(1, max(0, t)))
    return img


def bevel(mask, width):
    """内收 width 的 mask：边缘一圈用来做高光 / 阴影"""
    return mask.filter(ImageFilter.MinFilter(width * 2 + 1))


# ---- 形状（8 倍坐标）
shackle = Image.new('L', (w, h), 0)
d = ImageDraw.Draw(shackle)
cx = w // 2
ow, oh = 22 * S, 25 * S                      # 锁梁外框宽 / 高（半椭圆）
top = 3 * S
thick = int(4.8 * S)
d.ellipse([cx - ow // 2, top, cx + ow // 2, top + oh], fill=255)
d.ellipse([cx - ow // 2 + thick, top + thick, cx + ow // 2 - thick, top + oh - thick], fill=0)
d.rectangle([cx - ow // 2, top + oh // 2, cx + ow // 2, h], fill=0)
# 锁梁两条腿往下延伸到锁身里
d.rectangle([cx - ow // 2, top + oh // 2 - 1, cx - ow // 2 + thick, 22 * S], fill=255)
d.rectangle([cx + ow // 2 - thick, top + oh // 2 - 1, cx + ow // 2, 22 * S], fill=255)

body = Image.new('L', (w, h), 0)
d = ImageDraw.Draw(body)
bx0, by0, bx1, by1 = 6 * S, 17 * S, 34 * S, 40 * S
d.rounded_rectangle([bx0, by0, bx1, by1], radius=4 * S, fill=255)

key = Image.new('L', (w, h), 0)
d = ImageDraw.Draw(key)
kx, ky = cx, 26 * S
d.ellipse([kx - int(3.3 * S), ky - int(3.3 * S), kx + int(3.3 * S), ky + int(3.3 * S)], fill=255)
d.polygon([(kx - int(1.8 * S), ky), (kx + int(1.8 * S), ky), (kx + int(2.6 * S), ky + 8 * S), (kx - int(2.6 * S), ky + 8 * S)], fill=255)

# 锁身上横向的两道浅刻线（呼应原版盾牌上的刻纹）
groove = Image.new('L', (w, h), 0)
d = ImageDraw.Draw(groove)
d.rounded_rectangle([bx0 + int(2.6 * S), by0 + int(2.6 * S), bx1 - int(2.6 * S), by1 - int(2.6 * S)], radius=2 * S, outline=255, width=int(1.1 * S))

# ---- 上色
canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))


def paint(mask, base_top, base_bot, hi_w, edge):
    """一块金属：渐变底色 + 左上高光边 + 右下暗边 + 黑描边"""
    global canvas
    layer = shade(mask, base_top, base_bot)
    inner = bevel(mask, hi_w)
    ring = ImageChops.subtract(mask, inner)
    # 环上左上半亮、右下半暗
    lit = Image.new('L', (w, h), 0)
    lp = lit.load()
    for y in range(h):
        for x in range(w):
            lp[x, y] = 255 if (x - w / 2) * 0.6 + (y - h / 2) < 0 else 0
    ring_hi = ImageChops.multiply(ring, lit)
    ring_lo = ImageChops.subtract(ring, ring_hi)
    layer.paste(Image.new('RGB', (w, h), HI), (0, 0), ring_hi)
    layer.paste(Image.new('RGB', (w, h), DEEP), (0, 0), ring_lo)
    # 描边：mask 外扩一圈
    outline = mask.filter(ImageFilter.MaxFilter(edge * 2 + 1))
    canvas.paste(Image.new('RGBA', (w, h), OUT + (255,)), (0, 0), outline)
    canvas.paste(layer.convert('RGBA'), (0, 0), mask)


paint(shackle, HI, LOW, int(1.2 * S), int(1.3 * S))
paint(body, lerp(HI, MID, 0.12), LOW, int(1.4 * S), int(1.3 * S))
# 刻线：暗线 + 下方一像素亮线
g_dark = groove
g_light = groove.transform(groove.size, Image.AFFINE, (1, 0, -S // 2, 0, 1, -S // 2))
g_light = ImageChops.subtract(g_light, groove)
canvas.paste(Image.new('RGBA', (w, h), LOW + (255,)), (0, 0), ImageChops.multiply(g_dark, body))
canvas.paste(Image.new('RGBA', (w, h), lerp(HI, MID, 0.4) + (255,)), (0, 0), ImageChops.multiply(g_light, body))
# 锁孔：黑 + 右下一点反光
canvas.paste(Image.new('RGBA', (w, h), OUT + (255,)), (0, 0), key)
kh = key.transform(key.size, Image.AFFINE, (1, 0, -S, 0, 1, -S))
kh = ImageChops.subtract(key.filter(ImageFilter.MaxFilter(int(0.8 * S) | 1)), key)
kh = ImageChops.multiply(kh, Image.eval(key.transform(key.size, Image.AFFINE, (1, 0, S, 0, 1, S)), lambda v: v))
canvas.paste(Image.new('RGBA', (w, h), MID + (255,)), (0, 0), kh)

# 做旧：轻微噪点（原版是手绘质感）
random.seed(7)
noise = Image.new('L', (w, h))
npx = noise.load()
for y in range(0, h):
    for x in range(0, w):
        npx[x, y] = 128 + random.randint(-34, 34)
noise = noise.filter(ImageFilter.GaussianBlur(S * 0.45))
r, g, b, a = canvas.split()
r = ImageChops.add(ImageChops.multiply(r, noise), ImageChops.multiply(r, noise))
g = ImageChops.add(ImageChops.multiply(g, noise), ImageChops.multiply(g, noise))
b = ImageChops.add(ImageChops.multiply(b, noise), ImageChops.multiply(b, noise))
canvas = Image.merge('RGBA', (r, g, b, a))

lock = canvas.resize((W, H), Image.LANCZOS)
lock.save('tex/lock.png')

# 对比图：深色底，左原版右锁，放大 8 倍
equ = Image.open('tex/EquMark.png').convert('RGBA')
cmp_ = Image.new('RGBA', (W * 2 + 8, H), (40, 36, 30, 255))
cmp_.alpha_composite(equ, (0, 0))
cmp_.alpha_composite(lock, (W + 8, 0))
cmp_.resize((cmp_.width * 6, cmp_.height * 6), Image.NEAREST).save('tex/compare_x6.png')
# 实际显示大小（0.56 倍）也存一张
small = Image.new('RGBA', (60, 30), (40, 36, 30, 255))
small.alpha_composite(equ.resize((22, 24), Image.LANCZOS), (2, 3))
small.alpha_composite(lock.resize((22, 24), Image.LANCZOS), (34, 3))
small.resize((small.width * 6, small.height * 6), Image.NEAREST).save('tex/compare_real_x6.png')
print('ok')
