# -*- coding: utf-8 -*-
"""自制状态图标（buff 图标）：按 extract_affixes.STATUS_ICONS 画好、压成 BC7，写到 launcher\\reroll\\data\\menu：
  dr_status.dds     和原版 SB_Status_00 一样大（1024×512）的 BC7 图集，只有原版图标右边的空白里有我们的图
                    （启动时 launcher\\reroll\\menu.py 把我们那几格的块拷进原版那张，尺寸不改）
  dr_status.layout  要加进原版 SB_Status_00.layout 的 SubTexture 行（MENU_StatusIcon_<编号>）
  图标预览.png（本目录）放大 3 倍的预览，和几个原版图标放在一起对比
画法（用户 2026-10-28：没有原版 buff 图标的自己画，叠层的显示层数，参考 GoldenAge「多才多艺」）：
  照原版护符类图标（20254 钩爪、20285 鲜血君王）的方框 + 护符画（原版 SB_Icon_* 里的道具图标，按不透明部分裁边缩进框里）
  + 右下角升降箭头；叠层的左上角写层数（白字黑边）。原版图从本机游戏的 Data0 读（只读）。
赐福菜单（用户 2026-11-03「按第二版做」，预览见 scratchpad grace_ui；用法见 launcher\\reroll\\sc\\gracelook.py）：单独一张图集
  dr_grace.dds / .layout（1024×512 BC7，照 SB_Status_00 的格式；启动时 menu.py 作为新贴图 SB_DR_Grace 加进 01_common）：
  - 选项前面的图标都是 76×76 方图 MENU_DR_*：原版菜单标题图标（MENU_FL_*，142×146）复制过来（GRACE_COPY，名字 MENU_FL_x → MENU_DR_FL_x）。
    不能直接引用原版的：游戏里直接引用的原版图标下边被截掉 4 像素、文字往下偏，我们自己的方图完整、文字居中（2026-11-03 截图量过）；
  - 原版没有的：Grace_Forge = WeaponEnhance 里的器物调成余烬金（「暗黑重铸」入口）；Grace_Leave = 原版空框（十几个 MENU_FL_*
    逐像素取中位数，边框留下、里面抹掉填底色）+ MENU_Tab_Exit；Grace_Blank = 全透明（「返回」占位，文字对齐）；
  - MENU_DR_EquMark：难度当前档的「装备中」标记补成方图；
  - MENU_DR_Cursor_Wide：对话选项菜单（03_063_talkchoice.gfx，menu.py 把里面的 MENU_FL_Cursor_Wide 换成这个名字）的金色选中框。
用法：python make_icons.py（改了 STATUS_ICONS 或画法就重跑，再重新提取词条库）
"""
import io, os, re, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
sys.path.insert(0, HERE)
import erlib  # noqa: E402
from extract_affixes import STATUS_ICONS, status_icon  # noqa: E402

erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer')]
GAME = os.path.normpath(os.path.join(PALY, '..'))
OUT = os.path.join(RR, 'data', 'menu')
S, CELL = 40, 44                                # 图标边长、格子（留 4 像素空，BC7 的块不跨图标）
ATLAS = 'SB_Status_00'                          # 放进这张原版图集右边的空白（尺寸不改）
FONT = r'C:\Windows\Fonts\arialbd.ttf'


# ---------------------------------------------------------------- 原版的图
def vanilla_common():
    a = erlib.GameArchive(os.path.join(GAME, 'Data0.bhd'), open(os.path.join(OUT, 'data0_key.pem'), encoding='ascii').read())
    tpf = erlib.read_tpf(erlib.dcx_decompress(a.read('/menu/hi/01_common.tpf.dcx')))
    lay = erlib.Bnd4(erlib.dcx_decompress(a.read('/menu/hi/01_common.sblytbnd.dcx')))
    return {x['name']: x for x in tpf['tex']}, {n: lay.get(n).decode('utf-8') for n in lay.entries}


def rects(layouts, prefix):
    out = {}
    for t in layouts.values():
        img = re.search(r'imagePath="([^"]+)\.png"', t)
        for m in re.finditer(r'name="%s_(\d+)\.png" x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"' % prefix, t):
            out[int(m.group(1))] = (img.group(1), *map(int, m.groups()[1:]))
    return out


class Vanilla:
    def __init__(self):
        self.tex, self.lay = vanilla_common()
        self.items, self.status = rects(self.lay, 'MENU_ItemIcon'), rects(self.lay, 'MENU_StatusIcon')
        self.cache = {}

    def atlas(self, name):
        if name not in self.cache:
            self.cache[name] = Image.open(io.BytesIO(self.tex[name]['data'])).convert('RGBA')
        return self.cache[name]

    def crop(self, table, i):
        a, x, y, w, h = table[i]
        return self.atlas(a).crop((x, y, x + w, y + h))

    def sprite(self, name):
        """按精灵名字（不带 .png）裁原版图"""
        for t in self.lay.values():
            m = re.search(r'name="%s\.png" x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"' % re.escape(name), t)
            if m:
                img = re.search(r'imagePath="([^"]+)\.png"', t).group(1)
                x, y, w, h = map(int, m.groups())
                return self.atlas(img).crop((x, y, x + w, y + h))
        raise KeyError(name)


# ---------------------------------------------------------------- 赐福菜单的图标（照原版菜单标题图标 MENU_FL_*，142×146）
GRACE_S = 76
FRAME_SRC = ('MENU_FL_BonFire', 'MENU_FL_Repository', 'MENU_FL_WeaponEnhance', 'MENU_FL_LevelUp', 'MENU_FL_Status', 'MENU_FL_Talk',
             'MENU_FL_Sysytem', 'MENU_FL_Map', 'MENU_FL_Magic', 'MENU_FL_Message', 'MENU_FL_Network', 'MENU_FL_Inventory',
             'MENU_FL_Equipment', 'MENU_FL_Elixir', 'MENU_FL_Craft', 'MENU_FL_BuySell', 'MENU_FL_40152_BigRunes', 'MENU_FL_40168_Arts')
FRAME_INSET, FRAME_CORNER = 13, 30      # 142 宽的框：边框约 12 像素、四角花纹约 30 像素


def empty_frame(v):
    ims = [np.asarray(v.sprite(n).resize((142, 146), Image.LANCZOS)).astype(np.float32) for n in FRAME_SRC]
    med = np.median(np.stack(ims), axis=0)
    h, w = med.shape[:2]
    bg = med[FRAME_INSET + 2:FRAME_INSET + 12, FRAME_CORNER + 4:w - FRAME_CORNER - 4].reshape(-1, 4).mean(axis=0)
    yy, xx = np.mgrid[0:h, 0:w]
    inner = (yy >= FRAME_INSET) & (yy < h - FRAME_INSET) & (xx >= FRAME_INSET) & (xx < w - FRAME_INSET)
    corner = ((yy < FRAME_CORNER) | (yy >= h - FRAME_CORNER)) & ((xx < FRAME_CORNER) | (xx >= w - FRAME_CORNER))
    med[inner & ~corner] = bg
    return Image.fromarray(np.clip(med, 0, 255).astype(np.uint8), 'RGBA')


def beige(img):
    """彩色道具图调成原版菜单标题图标那种米白单色：按亮度映射到米色，拉一点对比"""
    a = np.asarray(img).astype(np.float32)
    a[..., 3] = np.clip((a[..., 3] - 64) * 255 / 191, 0, 255)          # 去掉道具图外面那圈半透明光晕（裁边也不算它）
    lum = (a[..., :3] @ np.array([0.299, 0.587, 0.114])) / 255.0
    solid = lum[a[..., 3] > 128]
    lo, hi = (np.percentile(solid, 3), np.percentile(solid, 99.5)) if solid.size else (0.0, 1.0)
    lum = np.clip((lum - lo) / max(1e-3, hi - lo), 0, 1) ** 0.85          # 按这张图自己的明暗拉满（幽影树碎片很暗）
    a[..., :3] = lum[..., None] * np.array([236, 224, 192])
    a[..., 3] *= np.clip(lum * 3, 0, 1)                                  # 暗的底子（道具图自带的方形暗影）去掉
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')


def framed(v, img, scale):
    """原版空框里放一张图（按不透明部分裁边，等比缩到框内 scale）"""
    fr = empty_frame(v)
    a = art(img, int((142 - 2 * FRAME_INSET) * scale))
    fr.alpha_composite(a, ((142 - a.width) // 2, (146 - a.height) // 2))
    return fr


def grace_leave(v):
    return framed(v, v.sprite('MENU_Tab_Exit'), 0.95)


GRACE_ITEMS = (('MENU_DR_Grace_Shadow', 3816),      # 幽影之地的庇佑：幽影树碎片（道具 2010000 的图标）
               ('MENU_DR_Grace_Steed', 13),         # 改变灵马的外表：灵马哨笛（道具 130）
               ('MENU_DR_Grace_Seal', 3272),        # 魇印（暗黑重铸，高难度档）：温床的诅咒（道具 8193）
               ('MENU_DR_Grace_Curse', 18051))      # 七咒（同上）：拉达冈的糜烂烙印（护符 1051；死亡的咒痕 3228 太淡）


def grace_forge(v):
    """框不动，里面的器物往暖金 / 余烬方向调：亮部偏金、暗部偏红褐"""
    a = np.asarray(v.sprite('MENU_FL_WeaponEnhance').resize((142, 146), Image.LANCZOS)).astype(np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    inner = (yy >= FRAME_INSET) & (yy < h - FRAME_INSET) & (xx >= FRAME_INSET) & (xx < w - FRAME_INSET)
    rgb = a[..., :3]
    lum = rgb.mean(axis=2, keepdims=True) / 255.0
    warm = np.concatenate([np.full_like(lum, 1.18), np.full_like(lum, 0.98), np.full_like(lum, 0.70)], axis=2)
    tinted = np.clip(rgb * warm + (lum ** 2.2) * np.array([60, 30, 0]), 0, 255)
    art = inner & (lum[..., 0] > 0.22)
    rgb[art] = tinted[art]
    a[..., :3] = rgb
    return Image.fromarray(a.astype(np.uint8), 'RGBA')


GRACE_COPY = ('MENU_FL_BonFire', 'MENU_FL_Status', 'MENU_FL_40169_Sleep', 'MENU_FL_Magic', 'MENU_FL_Elixir', 'MENU_FL_Repository',
              'MENU_FL_40152_BigRunes', 'MENU_FL_40168_Arts', 'MENU_FL_40165_Dresser', 'MENU_FL_Sysytem', 'MENU_FL_Talk', 'MENU_FL_Dragon',
              'MENU_FL_40163_BossSoulCopy', 'MENU_FL_40164_Renara', 'MENU_FL_CharaMake', 'MENU_FL_WeaponEnhance', 'MENU_FL_40155_Buddy',
              'MENU_FL_40154_MagicStoneCopy', 'MENU_FL_40187_FingerReader', 'MENU_FL_40153_SoulForging', 'MENU_FL_LevelUp',
              'MENU_FL_BuySell', 'MENU_FL_Inventory', 'MENU_FL_40160_StoneChange', 'MENU_FL_40192_Veil', 'MENU_FL_40167_Creed',
              'MENU_FL_Armor_40171', 'MENU_FL_40191_Coliseum')
GRACE_W, GRACE_H = 1024, 512


def grace_icons(v):
    """[(名字, 76×76 图)]"""
    out = [('MENU_DR_Grace_Forge', grace_forge(v)), ('MENU_DR_Grace_Leave', grace_leave(v))]
    out += [(n, framed(v, beige(v.crop(v.items, icon)), 0.80)) for n, icon in GRACE_ITEMS]
    out += [('MENU_DR_' + n[len('MENU_'):], v.sprite(n)) for n in GRACE_COPY]
    out = [(n, im.resize((GRACE_S, GRACE_S), Image.LANCZOS)) for n, im in out]
    return out + [('MENU_DR_Grace_Blank', Image.new('RGBA', (GRACE_S, GRACE_S), (0, 0, 0, 0)))]


def gold_cursor(v):
    """原版 MENU_FL_Cursor_Wide（米色、不透明度约 60、左右上下渐隐）调成暖金、加深一点，上下各一条细金线"""
    a = np.asarray(v.sprite('MENU_FL_Cursor_Wide')).astype(np.float32)
    h, w = a.shape[:2]
    t = np.linspace(0, 1, w)[None, :, None]
    gold = np.array([238, 194, 108]) * (1 - t) + np.array([206, 150, 70]) * t       # 左边亮、往右偏红
    alpha = a[..., 3:] * 1.55
    rgb = np.broadcast_to(gold, (h, w, 3)).copy()
    fade = (a[h // 2, :, 3] / max(1.0, a[h // 2, :, 3].max()))[None, :]
    for y in (5, h - 7):                                                              # 细线：跟着横向渐隐
        rgb[y] = np.array([246, 214, 140])
        alpha[y, :, 0] = np.maximum(alpha[y, :, 0], 120 * fade[0])
    return Image.fromarray(np.clip(np.concatenate([rgb, alpha], axis=2), 0, 255).astype(np.uint8), 'RGBA')


def equ_mark(v):
    im = v.sprite('MENU_EquMark')
    n = max(im.size)
    sq = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    sq.alpha_composite(im, ((n - im.width) // 2, (n - im.height) // 2))
    return sq


def grace_main(v):
    """dr_grace.dds / .layout + 赐福图标预览.png"""
    atlas = Image.new('RGBA', (GRACE_W, GRACE_H), (0, 0, 0, 0))
    cur = gold_cursor(v)
    atlas.alpha_composite(cur, (0, 0))
    lines = ['<SubTexture name="MENU_DR_Cursor_Wide.png" x="0" y="0" width="%d" height="%d" half="0"/>' % cur.size]
    y0 = (cur.height + 4 + 3) // 4 * 4
    per = GRACE_W // (GRACE_S + 4)
    items = grace_icons(v) + [('MENU_DR_EquMark', equ_mark(v))]
    for k, (name, im) in enumerate(items):
        x, y = (k % per) * (GRACE_S + 4), y0 + (k // per) * (GRACE_S + 4)
        if y + im.height > GRACE_H:
            raise RuntimeError('赐福图集放不下')
        atlas.alpha_composite(im, (x, y))
        lines.append('<SubTexture name="%s.png" x="%d" y="%d" width="%d" height="%d" half="0"/>' % (name, x, y, im.width, im.height))
    dds = dds_header(v.tex[ATLAS]['data'], GRACE_W, GRACE_H) + encode(atlas)
    open(os.path.join(OUT, 'dr_grace.dds'), 'wb').write(dds)
    open(os.path.join(OUT, 'dr_grace.layout'), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    back = Image.open(io.BytesIO(dds)).convert('RGBA')
    used = back.crop((0, 0, GRACE_W, y0 + ((len(items) + per - 1) // per) * (GRACE_S + 4)))
    prev = Image.new('RGBA', used.size, (28, 26, 22, 255))
    prev.alpha_composite(used)
    prev.save(os.path.join(HERE, '赐福图标预览.png'))
    print('赐福图集：选中框 + 图标 %d 个，写好 %s' % (len(items), os.path.join(OUT, 'dr_grace.dds')))


# ---------------------------------------------------------------- 画
def frame():
    """方框：外圈浅米色细线、里面深橄榄底、内侧一圈暗线，中间稍亮（照原版 20254 / 20285）"""
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((2, 2, S - 3, S - 3), fill=(52, 51, 40, 255), outline=(135, 130, 108, 255))
    d.rectangle((3, 3, S - 4, S - 4), outline=(30, 29, 22, 255))
    glow = Image.new('L', (S, S), 0)
    ImageDraw.Draw(glow).ellipse((6, 6, S - 7, S - 7), fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    inner = Image.new('L', (S, S), 0)
    ImageDraw.Draw(inner).rectangle((4, 4, S - 5, S - 5), fill=255)
    light = Image.new('RGBA', (S, S), (90, 88, 70, 255))
    light.putalpha(Image.composite(glow, Image.new('L', (S, S), 0), inner))
    return Image.alpha_composite(im, light)


def art(img, box=33):
    """道具图按不透明部分裁边，等比缩到 box 以内"""
    bb = img.getchannel('A').point(lambda a: 255 if a > 24 else 0).getbbox() or (0, 0, img.width, img.height)
    img = img.crop(bb)
    k = box / max(img.width, img.height)
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)


def arrow(up):
    """右下角的箭头：米色、暗描边（照原版）"""
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y0, y1 = 31, 25, 37
    head = [(x - 4, y0 + 4), (x, y0), (x + 4, y0 + 4)] if up else [(x - 4, y1 - 4), (x, y1), (x + 4, y1 - 4)]
    for w, c in ((4, (25, 22, 16, 255)), (2, (225, 215, 180, 255))):
        d.line((x, y0 + (1 if up else 0), x, y1 - (0 if up else 1)), fill=c, width=w)
        d.line(head, fill=c, width=w, joint='curve')
    return im


def number(n):
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    f = ImageFont.truetype(FONT, 14 if n < 10 else 12)
    ImageDraw.Draw(im).text((4, 2), str(n), font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(10, 8, 6, 255))
    return im


def make_icon(v, item, up, n):
    im = frame()
    a = art(v.crop(v.items, item))
    im.alpha_composite(a, ((S - a.width) // 2 - 1, (S - a.height) // 2 - 1))
    im.alpha_composite(arrow(up))
    if n:
        im.alpha_composite(number(n))
    return im


# ---------------------------------------------------------------- BC7（mode 6：单分区 RGBA，端点 7 位 + p 位，4 位索引）
W16 = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)


def _palette(e0, e1):
    return [tuple(((64 - w) * a + w * b + 32) >> 6 for a, b in zip(e0, e1)) for w in W16]


def _err(p, q):
    a = p[3] / 255.0
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2) * (0.25 + a) + 2.0 * (p[3] - q[3]) ** 2


def _quant(c):
    """端点量化到 7 位 + 共用的 p 位：两个 p 都试，挑误差小的。返回 (7 位的四个值, p, 实际 8 位值)"""
    best = None
    for p in (0, 1):
        q = [min(127, max(0, round((x - p) / 2))) for x in c]
        v = [x * 2 + p for x in q]
        e = sum((a - b) ** 2 for a, b in zip(v, c))
        if best is None or e < best[0]:
            best = (e, q, p, v)
    return best[1], best[2], best[3]


def _fit(px, idx):
    """给定索引，最小二乘求两端点（各通道分开）"""
    t = [W16[i] / 64.0 for i in idx]
    a11 = sum((1 - x) ** 2 for x in t)
    a12 = sum((1 - x) * x for x in t)
    a22 = sum(x * x for x in t)
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-6:
        return None
    e0, e1 = [], []
    for ch in range(4):
        b1 = sum((1 - x) * p[ch] for x, p in zip(t, px))
        b2 = sum(x * p[ch] for x, p in zip(t, px))
        e0.append(min(255, max(0, (a22 * b1 - a12 * b2) / det)))
        e1.append(min(255, max(0, (a11 * b2 - a12 * b1) / det)))
    return e0, e1


def _try(px, c0, c1):
    q0, p0, v0 = _quant(c0)
    q1, p1, v1 = _quant(c1)
    pal = _palette(v0, v1)
    idx, tot = [], 0.0
    for p in px:
        e, i = min((_err(p, q), i) for i, q in enumerate(pal))
        idx.append(i)
        tot += e
    return tot, q0, p0, q1, p1, idx


def encode_block(px):
    if all(p[3] == 0 for p in px):
        return bytes([0x40]) + bytes(15)
    n = len(px)
    mean = [sum(p[c] for p in px) / n for c in range(4)]
    d = [[p[c] - mean[c] for c in range(4)] for p in px]
    cov = [[sum(x[i] * x[j] for x in d) for j in range(4)] for i in range(4)]
    axis = [1.0, 1.0, 1.0, 1.0]
    for _ in range(8):
        v = [sum(cov[i][j] * axis[j] for j in range(4)) for i in range(4)]
        m = max(abs(x) for x in v)
        if m < 1e-9:
            break
        axis = [x / m for x in v]
    t = [sum(x[c] * axis[c] for c in range(4)) for x in d]
    lo, hi = min(t), max(t)
    nn = sum(a * a for a in axis) or 1.0
    c0 = [min(255, max(0, mean[c] + axis[c] * lo / nn)) for c in range(4)]
    c1 = [min(255, max(0, mean[c] + axis[c] * hi / nn)) for c in range(4)]
    best = _try(px, c0, c1)
    for _ in range(2):                                        # 按选出的索引最小二乘修端点，变好才留
        f = _fit(px, best[5])
        if not f:
            break
        cand = _try(px, *f)
        if cand[0] >= best[0]:
            break
        best = cand
    _, q0, p0, q1, p1, idx = best
    if idx[0] >= 8:                                           # 第一个像素的索引最高位必须是 0：两端点对调
        q0, q1, p0, p1 = q1, q0, p1, p0
        idx = [15 - i for i in idx]
    bits, pos = 1 << 6, 7
    for c in range(4):
        for q in (q0[c], q1[c]):
            bits |= q << pos
            pos += 7
    bits |= p0 << pos | p1 << (pos + 1)
    pos += 2
    for k, i in enumerate(idx):
        w = 3 if k == 0 else 4
        bits |= i << pos
        pos += w
    assert pos == 128
    return bits.to_bytes(16, 'little')


def encode(img):
    """RGBA 图（边长 4 的倍数）→ BC7 块数据（逐行）"""
    w, h = img.size
    pix = img.load()
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            out += encode_block([pix[bx + x, by + y] for y in range(4) for x in range(4)])
    return bytes(out)


def dds_header(vanilla_dds, w, h):
    """照原版图集的 DDS 头（DX10、BC7），只改宽高和数据大小"""
    hd = bytearray(vanilla_dds[:148])
    struct.pack_into('<III', hd, 12, h, w, (w // 4) * (h // 4) * 16)
    return bytes(hd)


# ---------------------------------------------------------------- 主流程
def cells(v, w, h):
    """原版图标右边空白里的格子（从原版最右边 + 4 起，对齐 4 像素）"""
    t = v.lay[ATLAS + '.layout']
    right = max(int(x) + int(ww) for x, ww in re.findall(r'x="(\d+)" y="\d+" width="(\d+)"', t))
    x0 = (right + 4 + 3) // 4 * 4
    for r in range(h // CELL):
        for x in range(x0, w - S + 1, CELL):
            yield x, CELL * r


def main():
    v = Vanilla()
    base = v.tex[ATLAS]
    bh, bw = struct.unpack_from('<II', base['data'], 12)
    atlas = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
    lines, spots, placed = [], cells(v, bw, bh), []
    for name, item, arrow_dir, layers in STATUS_ICONS:
        for n in (range(1, layers + 1) if layers else [0]):
            x, y = next(spots)
            atlas.alpha_composite(make_icon(v, item, arrow_dir == 'up', n), (x, y))
            placed.append((x, y))
            lines.append('<SubTexture name="MENU_StatusIcon_%05d.png" x="%d" y="%d" width="%d" height="%d" half="0"/>'
                         % (status_icon(name, n), x, y, S, S))
    # 整张图集大小的 BC7，只编我们放了图的区域（从第一格的 x 往右），其余是空块（启动时只拷我们那几格的块进原版）
    x0 = min(x for x, _ in placed)
    region = atlas.crop((x0, 0, bw, bh))
    blocks = encode(region)
    empty = bytes([0x40]) + bytes(15)
    rb = (bw - x0) // 4
    full = bytearray()
    for by in range(bh // 4):
        full += empty * (x0 // 4) + blocks[by * rb * 16:(by + 1) * rb * 16]
    dds = dds_header(base['data'], bw, bh) + bytes(full)
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, 'dr_status.dds'), 'wb').write(dds)
    open(os.path.join(OUT, 'dr_status.layout'), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    # 自查：解回来和原图比
    back = Image.open(io.BytesIO(dds)).convert('RGBA').crop((x0, 0, bw, bh))
    se = sum(sum((a - b) ** 2 for a, b in zip(p, q)) for p, q in zip(region.getdata(), back.getdata()))
    import math
    psnr = 10 * math.log10(255 ** 2 * 4 * region.width * region.height / se) if se else 99
    icons = [int(re.search(r'_(\d+)\.png', l).group(1)) for l in lines if 'StatusIcon' in l]
    # 预览：原版几个 + 我们的，放大 3 倍
    ref = [v.crop(v.status, i) for i in (20254, 20285, 20406, 20468)]
    tiles = ref + [Image.open(io.BytesIO(dds)).convert('RGBA').crop((x, y, x + S, y + S)) for x, y in placed]
    per = 13
    z = 3
    sheet = Image.new('RGBA', (per * (S * z + 6), ((len(tiles) + per - 1) // per) * (S * z + 6)), (45, 45, 45, 255))
    for k, t in enumerate(tiles):
        sheet.alpha_composite(t.resize((S * z, S * z), Image.NEAREST), ((k % per) * (S * z + 6), (k // per) * (S * z + 6)))
    sheet.save(os.path.join(HERE, '图标预览.png'))
    print('图标 %d 个（编号 %d ~ %d，%s 的 x=%d 往右），BC7 解回来 PSNR %.1f dB；写好 %s' % (len(icons), icons[0], icons[-1], ATLAS, x0, psnr, OUT))
    grace_main(v)


if __name__ == '__main__':
    main()
