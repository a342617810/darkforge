# -*- coding: utf-8 -*-
"""标题封面的动画（用户 2026-11-05「开始做动态吧」），由 make_covers.py 调用，不单独跑。
05_001_title_logo.gfx 是 Scaleform 时间轴，原版界面的光标就是不带类的子精灵自己循环、混合模式 8（加法），这里照做：
  Logo 精灵（原版 id 7）里：黑底（原版）→ 背景 base（原版那张图的位置）→ 烟雾精灵 → 环精灵 → 字样 top
两张封面做法相同，参数见 STYLE。动画只有两样（用户：不要额外的火焰，不要火星，「四色已经有环作为元素了，火星也是重复」）：
  烟雾飘动：几十团柔和的烟雾粒子从底部往上飘，顺同一个风向走，慢慢变大、淡出。只平移和等比放大，不错切不拉伸（用户：之前以底边为支点摆动「像果冻」）
  环的每一段顺时针依次亮（普通四段，高难七段）
新增的贴图不带 AS3 类，用「形状填充贴图」放（原版有 78 处这种写法），不是 PlaceObject3 直接放（那要 ABC 里有类）。
输出到 launcher\\reroll\\data\\menu：
  dr_title_<封面>_base.dds / _top.dds / _ring0~.dds / _puff0~.dds，dr_title_<封面>_anim.bin（<II 两个长度 + 新定义的标签 + 放进 Logo 精灵的标签）
menu.py 启动时把 anim.bin 拼进原版 gfx。删掉 anim.bin 就回到静态封面。"""
import glob
import os
import struct

import numpy as np
from PIL import Image

SMOKE_L = 480                               # 烟雾的循环长度（帧）：30 帧每秒，16 秒（自己一个精灵，和环各循环各的）
IMG, SHAPE, SPRITE = 1000, 1100, 1200       # 新角色的编号段（原版最大不到 10）
BLEND_ADD = 8
PUFF_N, PUFF_SIZE = 6, 256                  # 烟雾贴图几种、多大
# 每张封面：烟雾颜色、粒子随机种子、烟雾亮度倍数、环转一圈的帧数、点亮的包络指数（段多就窄一点，不糊成一片）
STYLE = {
    'normal': dict(color=(1.0, 0.35, 0.06), seed=31, peak=1.0, ring_l=300, ring_exp=3),      # 炉火（#ff5a10）；10 秒一圈，每段 2.5 秒
    'hard': dict(color=(0.60, 0.17, 1.0), seed=57, peak=1.25, ring_l=420, ring_exp=7),       # 魇火；14 秒一圈，每段 2 秒
}


# ---------------------------------------------------------------- SWF 编码
class Bits:
    def __init__(self):
        self.v, self.n = 0, 0

    def u(self, val, n):
        self.v = (self.v << n) | (int(val) & ((1 << n) - 1))
        self.n += n

    def done(self):
        pad = -self.n % 8
        return (self.v << pad).to_bytes((self.n + pad) // 8, 'big') if self.n else b''


def nbits(*vals):
    return max([1] + [(int(v).bit_length() if v >= 0 else (~int(v)).bit_length()) + 1 for v in vals])


def tag(code, body):
    if len(body) < 63:
        return struct.pack('<H', (code << 6) | len(body)) + body
    return struct.pack('<HI', (code << 6) | 0x3f, len(body)) + body


def rect(x0, x1, y0, y1):
    n = nbits(x0, x1, y0, y1)
    b = Bits()
    b.u(n, 5)
    for v in (x0, x1, y0, y1):
        b.u(v, n)
    return b.done()


def matrix(a=1.0, b=0.0, c=0.0, d=1.0, tx=0.0, ty=0.0):
    """x' = a x + c y + tx，y' = b x + d y + ty；tx、ty 是舞台像素"""
    w = Bits()
    A, B, C, D = (int(round(v * 65536)) for v in (a, b, c, d))
    if A != 65536 or D != 65536:
        n = nbits(A, D)
        w.u(1, 1), w.u(n, 5), w.u(A, n), w.u(D, n)
    else:
        w.u(0, 1)
    if B or C:
        n = nbits(B, C)
        w.u(1, 1), w.u(n, 5), w.u(B, n), w.u(C, n)
    else:
        w.u(0, 1)
    X, Y = int(round(tx * 20)), int(round(ty * 20))
    n = nbits(X, Y) if X or Y else 0
    w.u(n, 5)
    if n:
        w.u(X, n), w.u(Y, n)
    return w.done()


def cx_alpha(alpha):
    """只乘不透明度（alpha 0~1），写法同原版：10 位、RGB 乘 256"""
    w = Bits()
    w.u(0, 1), w.u(1, 1), w.u(10, 4)
    for v in (256, 256, 256, int(round(np.clip(alpha, 0, 1) * 256))):
        w.u(v, 10)
    return w.done()


def ext_image(cid, name, w, h):
    n = name.encode('ascii')
    f = n + b'.tga'
    return tag(1009, struct.pack('<IHHH', cid, 13, w, h) + bytes([len(n)]) + n + bytes([len(f)]) + f)


def bitmap_shape(cid, bitmap, w, h):
    """一个矩形，填充外部贴图，1 贴图像素 = 1 舞台像素。写法同原版（DefineShape、填充类型 0x40、矩阵 ×20）"""
    tw, th = w * 20, h * 20
    body = struct.pack('<H', cid) + rect(0, tw, 0, th) + bytes([1, 0x40]) + struct.pack('<H', bitmap) + matrix(20.0, 0, 0, 20.0) + bytes([0, 0x10])
    s = Bits()
    s.u(0b000101, 6)                        # 样式变更：填充 1、移动
    s.u(1, 5), s.u(0, 1), s.u(0, 1)         # 移动到 (0, 0)
    s.u(1, 1)                               # 填充 1 = 第一个
    for dx, dy in ((tw, 0), (0, th), (-tw, 0), (0, -th)):
        n = nbits(dx, dy)
        v = dx if dx else dy
        s.u(1, 1), s.u(1, 1), s.u(max(n - 2, 0), 4), s.u(0, 1), s.u(0 if dx else 1, 1), s.u(v, max(n, 2))
    s.u(0, 6)
    return tag(2, body + s.done())


def sprite(cid, frames, tags):
    return tag(39, struct.pack('<HH', cid, frames) + tags + b'\x00\x00')


def place2(depth, char=None, mat=None, cx=None, move=False):
    fl = (1 if move else 0) | (2 if char is not None else 0) | (4 if mat is not None else 0) | (8 if cx is not None else 0)
    return tag(26, bytes([fl]) + struct.pack('<H', depth) + (struct.pack('<H', char) if char is not None else b'') + (mat or b'') + (cx or b''))


def place3_blend(depth, char, mat, cx, blend):
    """PlaceObject3 带混合模式（原版光标的写法）"""
    return tag(70, bytes([0x0e, 0x02]) + struct.pack('<HH', depth, char) + mat + cx + bytes([blend]))


SHOW = tag(1, b'')


# ---------------------------------------------------------------- 贴图
def to8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def fill_transparent(rgba):
    """透明处的 RGB 用周围的颜色填（直通 alpha 的贴图双线性采样时不会带出一圈黑边）"""
    a = rgba[..., 3:4].astype(np.float32) / 255
    from PIL import ImageFilter
    pm = Image.fromarray((rgba[..., :3] * a).astype(np.uint8))
    bp = np.asarray(pm.filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    ba = np.asarray(Image.fromarray(rgba[..., 3]).filter(ImageFilter.GaussianBlur(6))).astype(np.float32)[..., None] / 255
    fill = np.clip(bp / np.maximum(ba, 0.004), 0, 255)
    out = rgba.copy()
    m = (a < 0.98)[..., 0]
    out[..., :3][m] = fill[m].astype(np.uint8)
    return out


def bbox4(mask, W, H, unit):
    """mask 非零的范围，左上对齐 2，宽高取 unit 的倍数"""
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = int(xs.min()) & ~1, int(xs.max()) + 1, int(ys.min()) & ~1, int(ys.max()) + 1
    w, h = (x1 - x0 + unit - 1) // unit * unit, (y1 - y0 + unit - 1) // unit * unit
    x0, y0 = min(x0, W - w), min(y0, H - h)
    return x0, y0, w, h


# ---------------------------------------------------------------- 时间轴
def ring_layer(ov):
    """一段环单独的加法层（画布大小 H×W×3）→ (半分辨率 RGB 贴图, 舞台 x, 舞台 y)。模糊的光用不着全分辨率，放的时候缩放 1 正好对上（半分辨率 ×1 = 画布 ×0.5）"""
    H, W = ov.shape[:2]
    rx, ry, rw, rh = bbox4(ov.max(-1) > 1.5 / 255, W, H, 8)
    half = Image.fromarray(to8(ov[ry:ry + rh, rx:rx + rw])).resize((rw // 2, rh // 2), Image.LANCZOS)
    return np.asarray(half), rx / 2, ry / 2


def puff_texture(seed, color):
    """一团烟：幂律噪声 × 径向衰减，边上一定归零（加法层不会露出方框）。RGB 是亮度，不透明度 255"""
    n = PUFF_SIZE
    r = np.random.default_rng(seed)
    f = np.fft.fftfreq(n) * n
    fx, fy = np.meshgrid(f, f)
    rad = np.sqrt(fx * fx + fy * fy)
    rad[0, 0] = 1
    amp = rad ** -1.55
    amp[0, 0] = 0
    v = np.fft.ifft2(amp * np.exp(2j * np.pi * r.random((n, n)))).real
    v = (v - v.mean()) / v.std()
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    rr = np.sqrt(((xx - c) / c) ** 2 + ((yy - c) / c) ** 2)
    fall = np.clip(1 - rr, 0, 1)
    fall = fall * fall * (3 - 2 * fall)
    a = np.clip((0.55 + 0.42 * v) * fall * 1.5 - 0.04, 0, 1)
    a = a / a.max()
    return np.dstack([to8(a[..., None] * np.array(color, np.float32)), np.full((n, n), 255, np.uint8)])


def gen_puffs(seed, peak_mul=1.0):
    """每团烟：贴图号、[(帧, 中心 x, 中心 y, 放大倍数, 不透明度), ...]，x、y 舞台像素"""
    r = np.random.default_rng(seed)
    out = []
    n = 64
    slots = r.permutation(n)                                            # 横向分格、出生时间用黄金分割撒开：不扎堆，亮度不忽明忽暗
    for k in range(n):
        life = int(r.integers(240, 420))
        a = int((k * 0.618034 % 1) * SMOKE_L)
        x0 = -300 + (slots[k] + float(r.random())) * 2520 / n
        y0 = float(r.uniform(960, 1280))                                # 从屏幕下沿附近出来，飘到屏幕中部前就淡完
        vy = float(r.uniform(0.25, 0.60))
        vx = 0.20 + float(r.normal(0, 0.10))                            # 风：大家朝一边走
        amp, per, ph = float(r.uniform(6, 22)), float(r.uniform(180, 420)), float(r.uniform(0, 6.28))     # 微微荡一点
        s0 = float(r.uniform(1.5, 2.9))
        peak = float(r.uniform(0.10, 0.20)) * peak_mul
        pts = []
        for t in range(life):
            u = t / life
            x = x0 + vx * t + amp * np.sin(2 * np.pi * t / per + ph)
            y = y0 - vy * t
            menu = 1 - 0.45 * float(np.exp(-((x - 960) / 420) ** 2 - ((y - 840) / 190) ** 2))      # 飘到标题菜单那一带淡一些，选项读得清
            pts.append(((a + t) % SMOKE_L, x, y, s0 * (1 + 0.32 * u), peak * menu * float(np.sin(np.pi * u)) ** 1.2))
        out.append(dict(tex=int(r.integers(PUFF_N)), rot=float(r.uniform(0, 6.28)), pts=pts))
    return out


def puff_matrix(s_, rot, cx, cy):
    n = PUFF_SIZE / 2
    a, b = s_ * np.cos(rot), s_ * np.sin(rot)
    return a, b, -b, a, cx - (a * n - b * n), cy - (b * n + a * n)


def smoke_still(H, W, name, frame=0):
    """静态图用：动画第 frame 帧的烟雾，加法叠好，画布大小（H×W×3，舞台 ×2）"""
    st = STYLE[name]
    tex = [Image.fromarray(puff_texture(40 + k, st['color'])[..., :3]) for k in range(PUFF_N)]
    acc = np.zeros((1080, 1920, 3), np.float32)
    for p in gen_puffs(st['seed'], st['peak']):
        for f, x, y, s_, al in p['pts']:
            if f != frame:
                continue
            a, b, c, d, tx, ty = puff_matrix(s_, p['rot'], x, y)
            det = a * d - b * c
            inv = (d / det, -c / det, (c * ty - d * tx) / det, -b / det, a / det, (b * tx - a * ty) / det)
            im = tex[p['tex']].transform((1920, 1080), Image.AFFINE, inv, Image.BILINEAR)
            acc += np.asarray(im).astype(np.float32) / 255 * al
    return np.asarray(Image.fromarray(to8(acc)).resize((W, H), Image.BICUBIC)).astype(np.float32) / 255


def smoke_timeline(puffs, shapes):
    """烟雾精灵的标签。同时活着的不共用一层；不透明度没变就不写"""
    frames = [[] for _ in range(SMOKE_L)]
    used = []
    for p in puffs:
        fs = np.array([q[0] for q in p['pts']])
        for d, occ in enumerate(used):
            if not occ[fs].any():
                break
        else:
            d = len(used)
            used.append(np.zeros(SMOKE_L, bool))
        used[d][fs] = True
        last = None
        for i, (f, x, y, s_, al) in enumerate(p['pts']):
            m = matrix(*puff_matrix(s_, p['rot'], x, y))
            q = int(round(al * 256))
            first = i == 0 or f == 0                                    # 回绕到第 0 帧要重新带角色放
            if first:
                frames[f].append(place3_blend(1 + d, shapes[p['tex']], m, cx_alpha(al), BLEND_ADD))
            else:
                frames[f].append(place2(1 + d, mat=m, cx=cx_alpha(al) if q != last else None, move=True))
            last = q
        nxt = (int(fs[-1]) + 1) % SMOKE_L
        if nxt != 0:
            frames[nxt].insert(0, tag(28, struct.pack('<H', 1 + d)))    # 下一帧移除（放在同一帧新放的前面）
    return b''.join(b''.join(fr) + SHOW for fr in frames), len(used)


def ring_timeline(rings, L, exp):
    """环精灵的标签：各段依次亮，每段一个余弦包，错开一段的相位。加法"""
    frames = [[] for _ in range(L)]
    for k, (cid, x, y) in enumerate(rings):
        for f in range(L):
            lit = 0.06 + 0.94 * max(0.0, float(np.cos(2 * np.pi * (f / L - k / len(rings))))) ** exp
            if f == 0:
                frames[f].append(place3_blend(k + 1, cid, matrix(tx=x, ty=y), cx_alpha(lit), BLEND_ADD))
            else:
                frames[f].append(place2(k + 1, cx=cx_alpha(lit), move=True))
    return b''.join(b''.join(fr) + SHOW for fr in frames)


# ---------------------------------------------------------------- 输出
def build(name, base, top, info, write_dds, out_dir):
    """base（H×W×3，不含烟雾）、top（预乘 H×W×4）、info（arcs：四段环单独的加法层），都是画布坐标（画布 = 舞台 ×2）"""
    H, W = base.shape[:2]
    st = STYLE[name]
    prefix = os.path.join(out_dir, 'dr_title_%s_' % name)
    for old in glob.glob(prefix + '*'):                                         # 上一版的贴图（换过内容的话旧的会被一起打进包）
        os.remove(old)
    dither = np.random.default_rng(3).normal(0, 0.5 / 255, base.shape).astype(np.float32)
    write_dds(to8(base + dither), prefix + 'base.dds')
    # 字样层：透明的地方裁掉
    a = top[..., 3]
    x0, y0, w, h = bbox4(a > 0.003, W, H, 4)
    crop = top[y0:y0 + h, x0:x0 + w]
    al = crop[..., 3:4]
    rgba = np.dstack([to8(np.where(al > 0.003, crop[..., :3] / np.maximum(al, 0.003), 0)), to8(al)])
    write_dds(fill_transparent(rgba), prefix + 'top.dds')
    defs, images = [], []

    def add_image(suffix, tw, th):
        cid = IMG + len(images)
        images.append(suffix)
        defs.append(ext_image(cid, 'MENU_Title_DF_' + suffix, tw, th))
        return cid

    next_shape = [SHAPE]

    def add_shape(bitmap, tw, th):
        cid = next_shape[0]
        next_shape[0] += 1
        defs.append(bitmap_shape(cid, bitmap, tw, th))
        return cid

    next_sprite = [SPRITE]

    def wrap(shape):
        sid = next_sprite[0]
        next_sprite[0] += 1
        defs.append(sprite(sid, 1, place2(1, char=shape, mat=matrix()) + SHOW))
        return sid

    top_shape = add_shape(add_image('top', w, h), w, h)
    # 环的每一段
    rings = []
    for k, (tex, rx, ry) in enumerate(info['arcs']):
        th, tw = tex.shape[:2]
        write_dds(np.dstack([tex, np.full((th, tw), 255, np.uint8)]), prefix + 'ring%d.dds' % k)
        rings.append((wrap(add_shape(add_image('ring%d' % k, tw, th), tw, th)), rx, ry))
    # 烟雾
    puff_shapes = []
    for k in range(PUFF_N):
        write_dds(puff_texture(40 + k, st['color']), prefix + 'puff%d.dds' % k)
        puff_shapes.append(wrap(add_shape(add_image('puff%d' % k, PUFF_SIZE, PUFF_SIZE), PUFF_SIZE, PUFF_SIZE)))
    puffs = gen_puffs(st['seed'], st['peak'])
    stl, layers = smoke_timeline(puffs, puff_shapes)
    smoke_id, ring_id = SPRITE + 100, SPRITE + 101
    defs.append(tag(39, struct.pack('<HH', smoke_id, SMOKE_L) + stl + b'\x00\x00'))
    defs.append(tag(39, struct.pack('<HH', ring_id, st['ring_l']) + ring_timeline(rings, st['ring_l'], st['ring_exp']) + b'\x00\x00'))
    places = place2(3, char=smoke_id, mat=matrix()) + place2(4, char=ring_id, mat=matrix()) + place2(5, char=top_shape, mat=matrix(0.5, 0, 0, 0.5, x0 / 2, y0 / 2))
    d = b''.join(defs)
    tmp = prefix + 'anim.bin.tmp'
    open(tmp, 'wb').write(struct.pack('<II', len(d), len(places)) + d + places)
    os.replace(tmp, tmp[:-4])
    alive = sum(len(p['pts']) for p in puffs) / SMOKE_L
    print('动画 %s：烟雾 %d 团（平均同屏 %.0f，占 %d 层）、环 %d 段，定义 %d KB，字样层 %d×%d' % (name, len(puffs), alive, layers, len(rings), len(d) // 1024, w, h))
