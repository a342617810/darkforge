# -*- coding: utf-8 -*-
"""稀有度边框图标（用户 2026-10-29：装备按稀有度加颜色边框，所有显示装备的地方都要有）：
生成装备可能用到的每个原版物品图标（MENU_ItemIcon，160×160）各做四份（普通 / 稀有 / 史诗 / 传说），写到 launcher\\reroll\\data\\menu：
  dr_frames_NN.dds / .layout    新加的图集 SB_Icon_DR_NN（4096×2048 BC7，照原版 SB_Icon_00；一张放 72 个图标 × 4）和它的布局行
  dr_frames.txt                 <原图标> <稀有度 0~3> <带框的图标>（启动时 menu.py 合成成功才抄给 dll\\dark_core\\frames.txt）
  边框预览.png（本目录）
图标清单：dll\\dark_core\\affixes.txt（上次重随写的）的武器本体 wbase、防具本体 pbase（男女两个图标）、护符模板 famr，
图标编号从 out\\reroll\\regulation.bin 查；开局装备、追忆、许愿、商店都在这几个本体里。本体名单变了（改词条库 / 本体条件）、改样式就重跑。
编号 50000 + 序号 × 4 + 稀有度（原版物品图标到 41603，图标编号是 u16）。
样式 A「名牌渐变」（用户 2026-10-29 从五种效果图里挑的，照原版详情栏的稀有度底条 MENU_FL_Rar_d1/d2）：
  图标后面从下往上的淡色渐变（左右两边渐隐），底边一条两头渐隐的细亮线 + 一点光；颜色是低饱和的旧银 / 灰蓝 / 暗紫 / 旧金。
  高稀有度更华丽（用户随后挑的「光芒 + 宝石」）：史诗、传说图标后面加从底边中间散开的光（黄金树光那种），底边中间一颗菱形宝石；
  传说的光更亮、宝石两边带渐细的翼线，再加几粒金尘。普通、稀有就是 A。装饰都在装备图后面，不挡装备。
  第一版是 3 像素实线框 + 名字颜色，用户嫌质感差；原版卷草纹饰缩到格子大小会糊，没用。
装饰只看稀有度：四种底层各画一次，每个图标叠上原版图；和原版解出来一样的 4×4 块直接抄原版的，变了的交给
dev\\bc7enc（Rust，和 make_icons.encode_block 逐字节相同，多线程；先 cargo build --release）。
自制道具图标（CUSTOM，编号 CUSTOM_BASE 起）放在最后一张图集的空格里，dr_frames.txt 里写「custom 名字 图标」行
（dark_core 按名字认，重随写的是原版图标，菜单包里有这个才换）：
  fusion_heart 融锻之心（装备工坊继承消耗的道具，rr/inherit.py）：龙心脏图标 3230 改成熔金色、后面一圈橙色柔光（用户 2026-10-31）。
  reforge_stone 武器重铸石：原版图标 3020 原样一份（原版图标不在我们的图集里，装备工坊界面画不出来）。
  overlimit_w / overlimit_a 超限锻造石（武器 / 防具，rr/overlimit.py，用户 2026-11-03）：古龙岩锻造石 / 古龙岩失色锻造石的图标
    改成熔金色 / 冰蓝色，后面一圈同色柔光（同融锻之心的做法）。
  curse_shard / bless_shard / shard_empty 七咒的碎片（「七咒」页每行右边一排，用户 2026-11-03：进度条不好看）：幽影树碎片（图标 3816）
    调成血红 / 金色（反转后）带同色柔光，没拿到的去色压暗、不带光；都裁到图本身再放大填满格子（画得小）。
  wish_stone 许愿石（rr/wishstone.py，用户 2026-11-04）：泪滴幼虫（道具 8185）的图标调成 深靛 → 星紫 → 银白，后面淡紫柔光。
  curse_<键> / bless_<键> 咒痕页每道咒痕的图标（诅咒 / 反转后，馈赠只有 bless_gift；用户 2026-11-05）：原版死亡的咒痕的变体，画法在 make_curse_icons.py。
新词条的饰品图标（用户 2026-11-11「接入游戏 注意稀有度背景」）：launcher\\reroll\\data\\codex_icons.json 里编号在 ART_LO~ART_HI 的词条，
  图是 dev\\item_system\\affix_icons\\out\\charm_<键>.png（那里的 batch_*.py 画的），一样叠四种稀有度底层，放在最后面另开的图集里，
  编号 ART_FRAMED + (虚编号 - ART_LO) × 4 + 稀有度；对照表照常写「虚编号 稀有度 带框的图标」。虚编号只在对照表和词条百科里用，游戏里没有这个图标：
  护符模板的图标照旧是原版的（菜单包合成失败就照原版），dark_core 的 frame_templates 按 affixes.txt 的 famicon 行换成带框的饰品图标。
用法：python make_frames.py（系统 Python，要 Pillow、numpy；读本机 Data0、out\\reroll\\regulation.bin 和 dll\\dark_core\\affixes.txt，都只读）
"""
import glob, json, math, os, random, re, struct, subprocess, sys, tempfile, time
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_icons import RR, OUT, Vanilla, dds_header  # noqa: E402
import make_curse_icons as curse_icons  # noqa: E402
import erlib  # noqa: E402
import paramdef_min as pdm  # noqa: E402

PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
BC7ENC = os.path.join(PALY, 'dev', 'bc7enc', 'target', 'release', 'bc7enc.exe')
S, CELL = 160, 164
ATLAS, BASE_ID, PER_ATLAS = 'SB_Icon_DR_%02d', 50000, 72       # 一张 4096×2048 是 24 × 12 格 = 72 个图标 × 4 种稀有度
# 普通 旧银、稀有 灰蓝、史诗 暗紫、传说 旧金（原版金饰 / 名牌金色渐变附近；名字前的稀有度字照旧）
TINT = [(168, 164, 150), (120, 140, 196), (160, 108, 190), (214, 178, 92)]
# 渐变最深处的不透明度（普通淡一些）、从多高开始、左右渐隐的宽度
GRAD_A, GRAD_A0, GRAD_TOP, GRAD_SIDE = 150, 70, 0.25, 0.18


def gradient(r):
    """名牌渐变的底色：从下往上渐淡，左右两边渐隐"""
    top = GRAD_A if r else GRAD_A0
    ys = Image.linear_gradient('L').resize((S, S))                 # 0（上）→ 255（下）
    vert = ys.point(lambda p: int(top * max(0.0, (p / 255 - GRAD_TOP) / (1 - GRAD_TOP)) ** 1.6))
    xs = ys.rotate(90, expand=True)
    side = ImageChops.darker(xs, xs.transpose(Image.FLIP_LEFT_RIGHT)).point(lambda p: min(255, int(p * 2 / 255 / GRAD_SIDE * 255)))
    bg = Image.new('RGBA', (S, S), TINT[r] + (0,))
    bg.putalpha(ImageChops.multiply(vert, side))
    return bg


# 底边细线、宝石的高度：贴着最底下（用户 2026-10-29：在 S - 4 / S - 5 时常被装备图挡住；不少装备图画到 150 行上下，有的一直到底）
LINE_Y = S - 2


def bottom_line(r):
    """底边一条两头渐隐的细亮线 + 一点光"""
    c = TINT[r]
    line = Image.new('L', (S, S), 0)
    ImageDraw.Draw(line).line((10, LINE_Y, S - 11, LINE_Y), fill=255, width=2)
    xs = Image.linear_gradient('L').resize((S, S)).rotate(90, expand=True)
    fade = ImageChops.darker(xs, xs.transpose(Image.FLIP_LEFT_RIGHT)).point(lambda p: min(255, p * 4))
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    for m, k in ((line.filter(ImageFilter.GaussianBlur(3)), 0.8), (ImageChops.multiply(line, fade), 0.95)):
        out.alpha_composite(_layer(m, c, k))
    return out


def _layer(mask, rgb, k=1.0):
    im = Image.new('RGBA', (S, S), rgb + (0,))
    im.putalpha(mask.point(lambda p: int(p * k)))
    return im


def rays(rgb, n, strength):
    """从底边中间往上散开的光（在图标后面），上面淡、下面亮"""
    m = Image.new('L', (S * 2, S * 2), 0)
    d = ImageDraw.Draw(m)
    cx, cy = S, S * 2 + 30
    rnd = random.Random(7)
    for k in range(n):
        a = -math.pi / 2 + (k - (n - 1) / 2) * 1.8 / n + rnd.uniform(-0.04, 0.04)
        w = rnd.uniform(0.025, 0.05)
        d.polygon([(cx, cy), (cx + math.cos(a - w) * 600, cy + math.sin(a - w) * 600), (cx + math.cos(a + w) * 600, cy + math.sin(a + w) * 600)],
                  fill=int(255 * rnd.uniform(0.5, 1.0)))
    m = m.resize((S, S), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2.2))
    ys = Image.linear_gradient('L').resize((S, S)).point(lambda p: int(255 * max(0.0, (p / 255 - 0.15) / 0.85) ** 1.2))
    return _layer(ImageChops.multiply(m, ys), rgb, strength)


def jewel(rgb, big):
    """底边中间的菱形宝石（压扁一点，贴着最底下；亮芯 + 光晕）；big（传说）两边带渐细的翼线"""
    m = Image.new('L', (S, S), 0)
    d = ImageDraw.Draw(m)
    cx, cy, h = S // 2, LINE_Y - 0.5, (6 if big else 4.5)
    v = h * 0.6
    if big:
        for sgn in (-1, 1):
            d.polygon([(cx + sgn * 4, cy - 1.4), (cx + sgn * 52, cy), (cx + sgn * 4, cy + 1.4)], fill=230)
    d.polygon([(cx, cy - v), (cx + h, cy), (cx, cy + v), (cx - h, cy)], fill=255)
    core = Image.new('L', (S, S), 0)
    k = 2.2 / h
    ImageDraw.Draw(core).polygon([(cx, cy - v * (1 - k)), (cx + h * (1 - k), cy), (cx, cy + v * (1 - k)), (cx - h * (1 - k), cy)], fill=255)
    out = _layer(m.filter(ImageFilter.GaussianBlur(3)), rgb, 0.9)
    out.alpha_composite(_layer(m, rgb, 1.0))
    out.alpha_composite(_layer(core, tuple(min(255, c + 70) for c in rgb), 1.0))
    return out


def dust(rgb, n, seed=3):
    """几粒金尘：小点 + 一点光晕，靠近底边的多（用户 2026-10-29：第一版太亮，调暗后又说亮度取中间值、数量保持）"""
    m = Image.new('L', (S, S), 0)
    d = ImageDraw.Draw(m)
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.uniform(14, S - 14), S - 12 - abs(rnd.gauss(0, 30))
        r = rnd.choice((0.75, 0.95, 1.25))
        d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    out = _layer(m.filter(ImageFilter.GaussianBlur(2.25)), rgb, 0.67)
    out.alpha_composite(_layer(m, tuple(min(255, c + 42) for c in rgb), 0.85))
    return out


def style(art, r):
    """A + 高稀有度的光芒、宝石（传说再加金尘）。装饰都在装备图后面，不挡装备（用户 2026-10-29：亮点挡住装备了）"""
    c = TINT[r]
    im = gradient(r)
    if r >= 2:
        im.alpha_composite(rays(c, 9 if r == 3 else 7, 0.55 if r == 3 else 0.32))
    if r == 3:
        im.alpha_composite(dust(c, 9))
    im.alpha_composite(bottom_line(r))
    if r >= 2:
        im.alpha_composite(jewel(c, r == 3))
    im.alpha_composite(art)
    return im


def style_a(art, r):
    """只有名牌渐变（普通、稀有就是这样）"""
    im = gradient(r)
    im.alpha_composite(bottom_line(r))
    im.alpha_composite(art)
    return im


CUSTOM_BASE = 56000                    # 自制道具图标的编号（边框图标到 50000 + 1306 × 4）


def fusion_heart(v):
    """融锻之心：龙心脏图标的亮度映射到 暗红褐 → 橙 → 浅金（留 15% 原色），后面一圈橙色柔光（不盖住图）"""
    art = v.crop(v.items, 3230)
    a = np.asarray(art, np.float32) / 255.0
    rgb, al = a[..., :3], a[..., 3:]
    t = np.clip(rgb @ np.array([0.299, 0.587, 0.114], np.float32), 0, 1)[..., None] ** 0.8
    lo, mid, hi = (np.array(c, np.float32) / 255 for c in ((40, 12, 4), (200, 90, 20), (255, 225, 140)))
    g = np.where(t < 0.5, lo + (mid - lo) * (t / 0.5), mid + (hi - mid) * ((t - 0.5) / 0.5))
    out = Image.fromarray((np.concatenate([np.clip(g * 0.85 + rgb * 0.15, 0, 1), al], -1) * 255).astype(np.uint8), 'RGBA')
    m = out.getchannel('A').filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(10)).point(lambda x: int(x * 0.9))
    im = Image.new('RGBA', out.size, (255, 140, 40, 0))
    im.putalpha(m)
    im.alpha_composite(out)
    return im


def tinted(v, icon, lo, mid, hi, glow, keep=0.15):
    """原版图标的亮度映射到 lo → mid → hi 三段颜色（留 keep 原色），后面一圈 glow 色的柔光（不盖住图）"""
    art = v.crop(v.items, icon)
    a = np.asarray(art, np.float32) / 255.0
    rgb, al = a[..., :3], a[..., 3:]
    t = np.clip(rgb @ np.array([0.299, 0.587, 0.114], np.float32), 0, 1)[..., None] ** 0.8
    lo, mid, hi = (np.array(c, np.float32) / 255 for c in (lo, mid, hi))
    g = np.where(t < 0.5, lo + (mid - lo) * (t / 0.5), mid + (hi - mid) * ((t - 0.5) / 0.5))
    out = Image.fromarray((np.concatenate([np.clip(g * (1 - keep) + rgb * keep, 0, 1), al], -1) * 255).astype(np.uint8), 'RGBA')
    m = out.getchannel('A').filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(10)).point(lambda x: int(x * 0.9))
    im = Image.new('RGBA', out.size, glow + (0,))
    im.putalpha(m)
    im.alpha_composite(out)
    return im


_goods_icons = {}


def goods_icon(gid):
    """道具在 out\\reroll\\regulation.bin 里的图标编号"""
    if not _goods_icons:
        erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer')]
        bnd = erlib.Bnd4(erlib.read_regulation(os.path.join(PALY, 'out', 'reroll', 'regulation.bin')))
        L = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(RR, 'data', 'EquipParamGoods.xml')))[0]}
        P = erlib.Param(bnd.get('EquipParamGoods.param'))
        _goods_icons.update({i: struct.unpack_from('<' + L['iconId'][1], r, L['iconId'][2])[0] for i, r in P.rows.items()})
    return _goods_icons[gid]


def overlimit_w(v):
    """超限锻造石（武器）：古龙岩锻造石（道具 10140）改成 暗铜 → 金 → 白金，后面金色柔光"""
    return tinted(v, goods_icon(10140), (48, 26, 6), (214, 160, 40), (255, 244, 200), (255, 200, 60))


def overlimit_a(v):
    """超限锻造石（防具）：古龙岩失色锻造石（道具 10200）改成 深蓝 → 钢蓝 → 冰白，后面青蓝柔光"""
    return tinted(v, goods_icon(10200), (10, 20, 44), (70, 130, 200), (225, 242, 255), (90, 170, 255))


def reforge_stone(v):
    """武器重铸石：原版铁制砥石刀的图标 3020 原样（rr/reforge.py 的 ICON_FROM 8970 用的；放进来是为了装备工坊界面能画，dark_core 换上）"""
    return v.crop(v.items, 3020)


SHARD_ICON = 3816                       # 幽影树碎片
SHARD_RED = ((30, 4, 4), (190, 30, 22), (255, 170, 140), (220, 40, 20))
SHARD_GOLD = ((48, 26, 6), (214, 160, 40), (255, 244, 200), (255, 200, 60))


def _fill(img, box):
    """裁到 box（不透明部分），等比放大到格子里（四边留 4 像素）"""
    a = img.crop(box)
    k = (S - 8) / max(a.size)
    a = a.resize((max(1, round(a.width * k)), max(1, round(a.height * k))), Image.LANCZOS)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.alpha_composite(a, ((S - a.width) // 2, (S - a.height) // 2))
    return out


def _shard_box(img):
    return img.getchannel('A').point(lambda x: 255 if x > 24 else 0).getbbox()


def curse_shard(v):
    """七咒碎片（诅咒）：幽影树碎片调成 暗红 → 血红 → 浅粉，后面血红柔光"""
    im = tinted(v, SHARD_ICON, *SHARD_RED)
    return _fill(im, _shard_box(im))


def bless_shard(v):
    """七咒碎片（反转成祝福后）：同一张调成熔金色，后面金色柔光"""
    im = tinted(v, SHARD_ICON, *SHARD_GOLD)
    return _fill(im, _shard_box(im))


def shard_empty(v):
    """没拿到的碎片：原图去色、压暗，不带光（裁的范围和上面一样，大小对得上）"""
    box = _shard_box(tinted(v, SHARD_ICON, *SHARD_RED))
    art = v.crop(v.items, SHARD_ICON)
    a = np.asarray(art, np.float32)
    g = (a[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)) * 0.42 + 10
    out = np.dstack([g, g, g, a[..., 3] * 0.9])
    return _fill(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGBA'), box)


def wish_stone(v):
    """许愿石：泪滴幼虫（道具 8185）改成 深靛 → 星紫 → 银白，后面淡紫柔光"""
    return tinted(v, goods_icon(8185), (14, 10, 40), (128, 104, 224), (244, 240, 255), (160, 136, 255))


CUSTOM = [('fusion_heart', fusion_heart), ('reforge_stone', reforge_stone), ('overlimit_w', overlimit_w), ('overlimit_a', overlimit_a),
          ('curse_shard', curse_shard), ('bless_shard', bless_shard), ('shard_empty', shard_empty), ('wish_stone', wish_stone)]
CUSTOM += [('%s_%s' % ('bless' if rev else 'curse', k), lambda v, k=k, rev=rev: curse_icons.make(v, k, rev))
           for k in curse_icons.KEYS for rev in (False, True)] + [('bless_gift', lambda v: curse_icons.make(v, 'gift', True))]


ART_LO, ART_HI = 45000, 50000           # 新词条饰品图标的虚编号（codex_icons.json 里写的；原版图标到 41603）
ART_FRAMED = 57000                      # 它们带框的图标：57000 + (虚编号 - 45000) × 4 + 稀有度（自制道具图标在 56000 起）
ART_DIR = os.path.join(HERE, 'affix_icons', 'out')


def affix_arts():
    """codex_icons.json 里虚编号在 ART_LO~ART_HI 的词条 → [(键, 虚编号, 160×160 图)]，按虚编号排"""
    over = json.load(open(os.path.join(RR, 'data', 'codex_icons.json'), encoding='utf-8'))
    out = []
    for k, v in over.items():
        if isinstance(v, int) and ART_LO <= v < ART_HI:
            p = os.path.join(ART_DIR, 'charm_%s.png' % k)
            if not os.path.isfile(p):
                raise SystemExit('codex_icons.json 写了 %s = %d，但没有图 %s' % (k, v, p))
            im = Image.open(p).convert('RGBA')
            if im.size != (S, S):
                raise SystemExit('%s 不是 %d×%d' % (p, S, S))
            out.append((k, v, im))
    if len({v for _, v, _ in out}) != len(out):
        raise SystemExit('codex_icons.json 里饰品图标的虚编号有重复')
    return sorted(out, key=lambda x: x[1])


def icon_ids():
    """生成装备可能用到的原版图标：affixes.txt 的 wbase / pbase / famr 本体 → 这次 regulation 里的图标编号（去重、保持顺序）"""
    defs = [l.rstrip('\n').split('\t') for l in open(os.path.join(PALY, 'dll', 'dark_core', 'affixes.txt'), encoding='utf-8')]
    weapons = [int(f[2]) for f in defs if f[0] == 'wbase']
    armor = [int(f[2]) for f in defs if f[0] == 'pbase']
    talismans = list(dict.fromkeys(int(f[4]) for f in defs if f[0] == 'famr' and int(f[4]) > 0))
    erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer')]
    bnd = erlib.Bnd4(erlib.read_regulation(os.path.join(PALY, 'out', 'reroll', 'regulation.bin')))

    def get(xml, ids, fields):
        L = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(RR, 'data', xml + '.xml')))[0]}
        P = erlib.Param(bnd.get(xml + '.param'))
        return [struct.unpack_from('<' + L[f][1], P.rows[i], L[f][2])[0] for i in ids if i in P.rows for f in fields]
    out = get('EquipParamWeapon', weapons, ['iconId']) + get('EquipParamProtector', armor, ['iconIdM', 'iconIdF']) + \
        get('EquipParamAccessory', talismans, ['iconId'])
    print('本体：武器 %d、防具 %d、护符模板 %d' % (len(weapons), len(armor), len(talismans)))
    return [i for i in dict.fromkeys(out) if i > 0]


def blocks_of(arr):
    """160×160×4 → 1600 个块 × 64 字节（块里按行，和 BC7 一样）"""
    return arr.reshape(S // 4, 4, S // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 64)


def vanilla_raw(v, icon):
    """原版图标的 1600 个 BC7 块（行优先）"""
    a, x, y, w, h = v.items[icon]
    if (w, h) != (S, S) or x % 4 or y % 4:
        raise ValueError('图标 %d 不是 160×160 / 没对齐 4 像素' % icon)
    d = v.tex[a]['data']
    aw = struct.unpack_from('<II', d, 12)[1]
    grid = np.frombuffer(d, dtype=np.uint8, offset=148).reshape(-1, aw // 4, 16)
    return grid[y // 4:(y + S) // 4, x // 4:(x + S) // 4].reshape(-1, 16)


def bc7(blocks):
    """一批 RGBA 块交给 dev\\bc7enc 压"""
    if not len(blocks):
        return np.zeros((0, 16), np.uint8)
    with tempfile.TemporaryDirectory() as td:
        src, dst = os.path.join(td, 'in.bin'), os.path.join(td, 'out.bin')
        blocks.tofile(src)
        subprocess.run([BC7ENC, src, dst], check=True)
        return np.fromfile(dst, dtype=np.uint8).reshape(-1, 16)


def main():
    if not os.path.isfile(BC7ENC):
        raise SystemExit('先编译 dev\\bc7enc：cargo build --release')
    t0 = time.time()
    v = Vanilla()
    icons = icon_ids()
    missing = [i for i in icons if i not in v.items]
    icons = [i for i in icons if i in v.items]
    under = [style(Image.new('RGBA', (S, S), (0, 0, 0, 0)), r) for r in range(4)]   # 装饰只看稀有度：四种底层各画一次
    ref = v.tex['SB_Icon_00']['data']
    h, w = struct.unpack_from('<II', ref, 12)
    cols, rows = (w - S) // CELL + 1, (h - S) // CELL + 1
    if cols * rows < PER_ATLAS * 4:
        raise SystemExit('一张图集放不下 %d 格' % (PER_ATLAS * 4))
    for old in glob.glob(os.path.join(OUT, 'dr_frames_*')):
        os.remove(old)                                     # 旧的（包括小验证的 dr_frames_new / 02B）先清掉
    mapping, recoded, preview = [], 0, []
    n_atlas = (len(icons) + PER_ATLAS - 1) // PER_ATLAS
    for ai in range(n_atlas):
        part = icons[ai * PER_ATLAS:(ai + 1) * PER_ATLAS]
        cells = np.empty((len(part) * 4, 1600, 16), np.uint8)
        todo, where = [], []
        for j, icon in enumerate(part):
            art = v.crop(v.items, icon)
            plain = blocks_of(np.asarray(art, np.uint8))
            raw = vanilla_raw(v, icon)
            for r in range(4):
                img = under[r].copy()
                img.alpha_composite(art)
                cur = blocks_of(np.asarray(img, np.uint8))
                diff = np.any(cur != plain, axis=1)
                cells[j * 4 + r] = raw
                todo.append(cur[diff])
                where.append((j * 4 + r, np.nonzero(diff)[0]))
                mapping.append('%d\t%d\t%d' % (icon, r, BASE_ID + (ai * PER_ATLAS + j) * 4 + r))
                if ai == 0 and j < 6:
                    preview.append(img)
        enc = bc7(np.concatenate(todo))
        k = 0
        for c, idx in where:
            cells[c, idx] = enc[k:k + len(idx)]
            k += len(idx)
        recoded += k
        # 自制道具图标接在最后一张的边框图标后面（整张图重编）
        custom_at = {}
        if ai == n_atlas - 1:
            for ci, (name, make) in enumerate(CUSTOM):
                img = make(v)
                img.save(os.path.join(HERE, '自制图标_%s.png' % name))
                cells = np.concatenate([cells, bc7(blocks_of(np.asarray(img, np.uint8)))[None]])
                custom_at[len(cells) - 1] = CUSTOM_BASE + ci
                mapping.append('custom\t%s\t%d' % (name, CUSTOM_BASE + ci))
            if len(cells) > cols * rows:
                raise SystemExit('最后一张图集放不下自制图标（%d 格 > %d）' % (len(cells), cols * rows))
        # 拼图集：格子按行排，空的地方是全透明块
        empty = np.frombuffer(bytes([0x40]) + bytes(15), np.uint8)
        grid = np.tile(empty, (h // 4, w // 4, 1))
        lines = []
        for c in range(len(cells)):
            x, y = (c % cols) * CELL, (c // cols) * CELL
            grid[y // 4:(y + S) // 4, x // 4:(x + S) // 4] = cells[c].reshape(S // 4, S // 4, 16)
            nid = custom_at.get(c, BASE_ID + ai * PER_ATLAS * 4 + c)
            lines.append('<SubTexture name="MENU_ItemIcon_%05d.png" x="%d" y="%d" width="%d" height="%d" half="0"/>' % (nid, x, y, S, S))
        open(os.path.join(OUT, 'dr_frames_%02d.dds' % ai), 'wb').write(dds_header(ref, w, h) + grid.tobytes())
        open(os.path.join(OUT, 'dr_frames_%02d.layout' % ai), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
        print('  图集 %d / %d：%d 个图标，重编 %d 块（%.0f 秒）' % (ai + 1, n_atlas, len(part), k, time.time() - t0), flush=True)
    # 新词条的饰品图标：四种稀有度底层各叠一份，接在后面另开图集（整张重编）
    arts = affix_arts()
    per = cols * rows // 4
    art_preview = []
    for bi in range((len(arts) + per - 1) // per):
        ai = n_atlas + bi
        part = arts[bi * per:(bi + 1) * per]
        imgs, ids = [], []
        for key, vb, art in part:
            for r in range(4):
                img = under[r].copy()
                img.alpha_composite(art)
                imgs.append(img)
                ids.append(ART_FRAMED + (vb - ART_LO) * 4 + r)
                mapping.append('%d\t%d\t%d' % (vb, r, ids[-1]))
                if len(art_preview) < 24:
                    art_preview.append(img)
        enc = bc7(np.concatenate([blocks_of(np.asarray(im, np.uint8)) for im in imgs])).reshape(len(imgs), 1600, 16)
        recoded += len(imgs) * 1600
        empty = np.frombuffer(bytes([0x40]) + bytes(15), np.uint8)
        grid = np.tile(empty, (h // 4, w // 4, 1))
        lines = []
        for c, nid in enumerate(ids):
            x, y = (c % cols) * CELL, (c // cols) * CELL
            grid[y // 4:(y + S) // 4, x // 4:(x + S) // 4] = enc[c].reshape(S // 4, S // 4, 16)
            lines.append('<SubTexture name="MENU_ItemIcon_%05d.png" x="%d" y="%d" width="%d" height="%d" half="0"/>' % (nid, x, y, S, S))
        open(os.path.join(OUT, 'dr_frames_%02d.dds' % ai), 'wb').write(dds_header(ref, w, h) + grid.tobytes())
        open(os.path.join(OUT, 'dr_frames_%02d.layout' % ai), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
        print('  饰品图标图集 %d：%d 个词条 × 4（%.0f 秒）' % (ai + 1, len(part), time.time() - t0), flush=True)
    if art_preview:
        t = int(S * 0.75)
        sheet = Image.new('RGBA', (4 * (t + 6), len(art_preview) // 4 * (t + 6)), (24, 23, 20, 255))
        for k, im in enumerate(art_preview):
            sheet.alpha_composite(im.resize((t, t), Image.LANCZOS), ((k % 4) * (t + 6), (k // 4) * (t + 6)))
        sheet.save(os.path.join(HERE, '饰品图标边框预览.png'))
    art_top = ART_FRAMED + ((max(v for _, v, _ in arts) - ART_LO + 1) * 4 if arts else 0)
    if BASE_ID + len(icons) * 4 > CUSTOM_BASE or CUSTOM_BASE + len(CUSTOM) > ART_FRAMED or art_top > 65535 or max(icons) >= ART_LO:
        raise SystemExit('图标编号重叠 / 超出 u16')
    open(os.path.join(OUT, 'dr_frames.txt'), 'w', encoding='utf-8', newline='\n').write(
        '# 稀有度边框图标（dev\\item_system\\make_frames.py 生成）：原图标 稀有度 带框的图标；custom 名字 图标 = 自制道具图标\n'
        + '\n'.join(mapping) + '\n')
    t = int(S * 0.75)
    sheet = Image.new('RGBA', (4 * (t + 6), len(preview) // 4 * (t + 6)), (24, 23, 20, 255))
    for k, im in enumerate(preview):
        sheet.alpha_composite(im.resize((t, t), Image.LANCZOS), ((k % 4) * (t + 6), (k // 4) * (t + 6)))
    sheet.save(os.path.join(HERE, '边框预览.png'))
    print('带框图标 %d 个（原版图标 %d 个 × 4；图集里找不到的 %d 个照原版：%s；新词条饰品图标 %d 个 × 4），%d 张图集，重编 BC7 块 %d 个；用时 %.0f 秒；写好 %s' % (
        len(mapping), len(icons), len(missing), missing[:10], len(arts), n_atlas + (len(arts) + per - 1) // per, recoded, time.time() - t0, OUT))


if __name__ == '__main__':
    main()
