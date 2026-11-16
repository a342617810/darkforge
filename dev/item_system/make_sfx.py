# -*- coding: utf-8 -*-
"""自制特效包：sfx\\sfxbnd_c0000.ffxbnd.dcx（玩家角色 c0000 的特效包，原版没有这个文件，不动任何原版文件）
游戏载入角色时按 SfxBnd_c%04d 找它的特效包，玩家一直在，所以包里的特效和贴图常驻（ELDEN VINS 也这样加自己的特效）。
写到 launcher\\reroll\\data\\sfx\\sfxbnd_c0000.ffxbnd.dcx，重随时拷进 out\\reroll\\sfx（DR_Reroll 挂载）。

现在包里：
  猎印的准星（用户 2026-10-28：自己做一个小瞄准镜的光效，层数越高绿色越深；
  第二版：不要描边，透明度不均匀，隐隐有气流缠绕在上面；第三版：参考游戏里大卢恩的图标）
    大卢恩图标（道具 191~196 的 MENU_ItemIcon 3200~3206）的画法：线条由很多细碎发亮的颗粒组成（像灼烧的纹路），
    粗糙、略有起伏，外面一圈柔光，零星光屑往外飘；没有描边，透明度全靠颗粒疏密和亮度
    贴图 s99001_a：准星（圆圈 + 四道刻线 + 中心点）照这个画法：沿线条撒颗粒（亮度长尾分布）、线条按噪声微微起伏，
                   加一圈柔光和往外飘的光屑；白色，颜色在特效里按层染
    贴图 s99002_a：气流，三股往外旋的光屑流，同样是颗粒（三重对称：转 120° 和原样一样，特效靠这个无缝循环转动）
    特效 990001 / 990002 / 990003：1~3 层，准星染浅绿 / 绿 / 深绿（亮度乘到 1 以上 + 泛光，照原版 4160 发光的写法；
                   轻微呼吸），气流用更淡的同色慢慢转；挂在敌人的锁定点（光效行 midstDmyId 220）
    特效文件由 sfx\\hunt_mark.js 在浏览器里用 @cccode/fxr 生成（见那个文件开头和 自制特效.md），放在 sfx\\f000990001.fxr 等
  预览：本目录 准星预览.png / 准星预览.gif（三层并排在灰底上，gif 是气流转一圈）
  环绕法球 990011~990014（sfx\\orbs.js，借原版魔砾 523002）
  夺取魇火时玩家身上的吸取特效 990006 / 990007（用户 2026-11-03：原版亵渎圣剑战技回血的特效 450344 和它引用的 440322 改成紫色，
    sfx\\drain.js；资源清单照抄原版的）
  咒痕（原名七咒）「烙印」的血月印记（用户 2026-11-03：不用准星，另外做）：贴图 s99005_a 月面（暗斑、亮边由发亮颗粒组成、外圈柔光）、
    s99006_a 符文环（六个相同的符号围一圈，六重对称，转 60° 无缝）；特效 990004 血红 / 990005 金色（反转后），
    悬在敌人锁定点上方，月面轻轻呼吸、符文环慢慢转（sfx\\brand_mark.js）。预览 血月预览.png
  战灰「唤声船」的灵船：boat_model.py 把唤声船 c4950 的船身转成特效模型（s99003 原版幽灵材质、s99004 木头，贴图 s99003_a / _n），
    特效 990021 / 990024（sfx\\boat.js）
  相杀受击的防御火花 990040（sfx\\clash_spark.js，用户 2026-11-04「改一下火花特效 现在太不明显了」）：原版金属防御火花 201001
    放大 2.5 倍、飞散 1.6 倍、火花数量 3 倍、亮度 1.5 倍，资源清单照抄原版
  死亡以上难度错配屏障 990050（sfx\\barrier_dome.js，用户 2026-11-05「屏障缩小到10m … 要加上特效标识屏障存在」）：原版封印监牢圆顶 806700
    缩到半径 10 米 + 圆周上往上飘的光幕 + 地上一圈光（原版光点贴图 10011），资源清单 = 原版那份 + s10011_a
  提灯的光源 990060（sfx\\lantern.js，用户 2026-11-10「改一下油灯的亮度 参考 golden age 不需要改灯光颜色和位置」）：原版 302421
    只把点光源的衰减 unk_ds3_p2_0 从 1.25 改成 Golden Age 幽魂提灯（原版 402030）的 2，颜色、半径、亮度曲线不动；资源清单照抄原版（空的）
  词条触发时一闪的特效（用户 2026-11-13）：猎印被引爆 / 近身清除时的碎裂 990070~990072（sfx\\hunt_burst.js，消耗 1~3 层），
    用猎印的两张贴图 + 原版光点贴图 10011，资源清单 = 我们的贴图 + s10011_a；
    换气 990075（sfx\\second_breath.js 第三版）：原版红露滴回血光 301002 换成精力绿 + 腌制龟颈肉精力光 301202 的余韵，资源清单照抄 301002
  加速光晕 990091~990093（用户 2026-11-14「影步的持续光晕没有生效」）：原版 440700 原样复制、只换编号，影步 / 处刑 / 转念各一份
    （和见切的羽毛特效、彼此之间用同一个特效会被游戏合成一份，一个收掉另一个也没了）
  整条链路（加载原理、生成、挂上、调试、踩过的坑）见本目录 自制特效.md

用法：python make_sfx.py            重画贴图、打包
      python make_sfx.py --debug    打包排查变体（sfx\\debug\\ 里有的特效换成变体；排查完再跑一次不带参数的换回正式的）
      python make_sfx.py --check    用 ELDEN VINS 的 sfxbnd_c0000 验证打包写法（解开再按本工具的写法重写，逐字节比对）
"""
import json, os, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
sys.path.insert(0, HERE)
import erlib  # noqa: E402
from make_icons import encode  # noqa: E402
from erlib import read_bnd4_full, write_bnd4  # noqa: E402

erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), os.path.dirname(PALY)]
SRC = os.path.join(HERE, 'sfx')
OUT = os.path.join(RR, 'data', 'sfx', 'sfxbnd_c0000.ffxbnd.dcx')
ROOT = 'N:\\GR\\data\\INTERROOT_win64\\sfx\\'
HUNT_TEX, HUNT_WISP_TEX = 99001, 99002
# 七咒「烙印」的血月印记：月面、符文环贴图；特效（血红、金色，brand_mark.js 里同样的颜色，这里只画预览）
MOON_TEX, RUNE_TEX = 99005, 99006
BRAND_FXR = (990004, 990005)
BRAND_RGB = ((0.85, 0.06, 0.03), (1.0, 0.76, 0.22))
HUNT_FXR = (990001, 990002, 990003)
# 三层的颜色、气流的颜色和透明度（hunt_mark.js 里同样的值；这里只用来画预览）
HUNT_RGB = ((0.62, 1.0, 0.62), (0.2, 0.82, 0.2), (0.0, 0.42, 0.06))
WISP_MIX, WISP_ALPHA = 0.45, 0.35                   # 气流 = 层色往白色混 45%，透明度 0.35（隐隐能看到）
RET_MULT, WISP_MULT = 2.2, 1.2                      # 亮度倍数（>1 发光，照原版 4160 的 rgbMultiplier 写法）
TEX_SIZE = 256
# 环绕法球（凝聚）：1~4 颗辉石魔砾绕着人物转（sfx\orbs.js 生成）；外观借原版魔砾子弹的飞行特效 523002（资源都在常驻的公共特效包里，
# 资源清单照抄它的）。原版那份从本机 Data0 读（只读），存到 sfx\vanilla\ 给 orbs.js 用
ORBIT_FXR = (990011, 990012, 990013, 990014, 990015, 990016, 990017)   # 1~7 颗（5~7 颗给盈满，2026-11-04）
PEBBLE_FXR = 523002
# 夺取魇火的紫色吸取特效（sfx\drain.js）：(我们的, 原版)——壳 450344（光效行 8535 挂的）和它引用的画面 440322
DRAIN_FXR = ((990006, 450344), (990007, 440322))
# 战灰「唤声船」的灵船（boat_model.py 从唤声船 c4950 取出船身，sfx\boat.js 生成特效）：（特效, 模型）
# 990021 / 99003 = 原版幽灵材质，990024 / 99004 = 普通特效材质的木头船
BOAT_FXR = ((990021, 99003), (990024, 99004))
# 相杀的防御火花（sfx\clash_spark.js 照原版 201001 放大），资源清单照抄原版
CLASH_SPARK_FXR = ((990040, 201001),)
# 死亡以上难度错配屏障（sfx\barrier_dome.js 照原版封印监牢圆顶 806700 缩小，加光幕 / 地面圈）：资源清单 = 原版那份 + 光点贴图
BARRIER_FXR = ((990050, 806700),)
BARRIER_EXTRA_TEX = ('s10011_a',)
# 提灯的光源（sfx\lantern.js 照原版 302421 只改衰减），资源清单照抄原版
LANTERN_FXR = ((990060, 302421),)
# 词条触发时一闪的自制特效：(编号, 生成脚本)；用我们的贴图和原版光点贴图
FLASH_FXR = ((990070, 'hunt_burst.js'), (990071, 'hunt_burst.js'), (990072, 'hunt_burst.js'))
FLASH_EXTRA_TEX = ('s10011_a',)
# 换气（sfx\second_breath.js 第三版，用户 2026-11-13「贴合原版风格」）：原版红露滴圣杯瓶的回血光 301002 照红 → 蓝的规则换成精力绿，
# 加上腌制龟颈肉的精力光 301202 的两个发射节点（限时）；资源清单照抄 301002 的（301202 用的三张贴图都在里面）
BREATH_FXR = ((990075, 301002),)
BREATH_TAIL_FXR = 301202
# 加速光晕（launcher\reroll\rr\sounds.py HASTE_GLOWS）：原版潜雾猛禽羽毛特效里的 440701 的原样副本，只换编号（文件头偏移 12，整个文件只这一处）。
# 以前用 440700：它长在身体里面，穿着铠甲就看不见（用户 2026-11-14 用 F9 的 A / B 对比：只有 B = 440701 看得见），改成 440701。
# 每个加速词条各一份副本，同时在也互不影响；资源清单照抄原版。影步（见切触发）的光晕由 dark_core 晚一点单独挂（rules.rs late_glow_step）
HASTE_GLOW_FXR = (990091, 990092, 990093)
HASTE_GLOW_SRC = 440701
VANILLA_FXR = (PEBBLE_FXR,) + tuple(src for _id, src in DRAIN_FXR) + tuple(src for _id, src in CLASH_SPARK_FXR) + tuple(src for _id, src in BARRIER_FXR) \
    + tuple(src for _id, src in LANTERN_FXR) + tuple(src for _id, src in BREATH_FXR) + (BREATH_TAIL_FXR, HASTE_GLOW_SRC)


def vanilla_fxr(fid):
    """原版特效（公共特效包里的）和它的资源清单：sfx\\vanilla\\ 里没有就从本机 Data0 取一次（解开公共特效包要几秒）"""
    d = os.path.join(SRC, 'vanilla')
    fp, rp = os.path.join(d, 'f%09d.fxr' % fid), os.path.join(d, 'f%09d.ffxreslist' % fid)
    if not (os.path.isfile(fp) and os.path.isfile(rp)):
        key = open(os.path.join(RR, 'data', 'menu', 'data0_key.pem'), encoding='ascii').read()
        arc = erlib.GameArchive(os.path.join(os.path.dirname(PALY), 'Data0.bhd'), key)
        bnd = erlib.Bnd4(erlib.dcx_decompress(arc.read('/sfx/sfxbnd_commoneffects.ffxbnd.dcx')))
        os.makedirs(d, exist_ok=True)
        for v in VANILLA_FXR:
            open(os.path.join(d, 'f%09d.fxr' % v), 'wb').write(bnd.get('f%09d.fxr' % v))
            open(os.path.join(d, 'f%09d.ffxreslist' % v), 'wb').write(bnd.get('f%09d.ffxreslist' % v))
        print('从 Data0 取了原版特效', VANILLA_FXR)
    return open(fp, 'rb').read(), open(rp, 'rb').read()


# ---------------------------------------------------------------- 贴图
def noise(n, cells, seed):
    """平滑的低频噪声（0~1）：随机格点放大"""
    g = np.random.default_rng(seed).random((cells + 1, cells + 1))
    return np.asarray(Image.fromarray((g * 255).astype(np.uint8), 'L').resize((n, n), Image.BICUBIC), dtype=np.float32) / 255.0


def white(alpha):
    """透明度数组（0~1）→ 白色 RGBA 图（颜色在特效里按层染）"""
    a = (np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)
    return Image.merge('RGBA', [Image.new('L', a.shape[::-1], 255)] * 3 + [Image.fromarray(a, 'L')])


def splat(n, xs, ys, vs):
    """把颗粒（坐标、亮度）累加到 n×n 的数组上（双线性分到相邻四个像素，颗粒移动时不会一跳一跳）"""
    acc = np.zeros((n, n), np.float32)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < n) & (yi >= 0) & (yi < n)
        np.add.at(acc, (yi[ok], xi[ok]), (vs * w)[ok])
    return acc


def path_grains(rng, pts, normals, n, density, core, spread, fleck):
    """沿一条路径撒颗粒（大卢恩图标的画法）：pts / normals 是路径上的点和法线（像素），
    core：线芯颗粒离线的标准差；spread：外圈柔散的标准差；fleck：往外飘的光屑比例。返回 (x, y, 亮度)"""
    m = len(pts)
    k = int(m * density)
    idx = rng.integers(0, m, k)
    side = rng.normal(0.0, core, k)
    loose = rng.random(k) < 0.25                     # 四分之一的颗粒散得开一点（线条外的毛边）
    side[loose] = rng.normal(0.0, spread, loose.sum())
    v = rng.random(k) ** 3.0                         # 亮度长尾：少数很亮的颗粒，像火星
    fl = rng.random(k) < fleck                       # 光屑：离线更远、更暗、往外飘
    side[fl] = np.abs(rng.normal(0.0, spread * 3.5, fl.sum())) * np.sign(rng.normal(size=fl.sum()))
    v[fl] *= 0.45
    x = pts[idx, 0] + normals[idx, 0] * side
    y = pts[idx, 1] + normals[idx, 1] * side
    return x, y, v


def glow_texture(acc, size, ss):
    """颗粒累加 → 发光贴图：细颗粒（轻微模糊）+ 一圈柔光，再压一下亮部（1 - e^-x），缩到 size；白色，透明度是亮度"""
    from scipy.ndimage import gaussian_filter
    fine = gaussian_filter(acc, ss * 0.3)
    halo = gaussian_filter(acc, ss * 4.0)
    lum = fine / (np.percentile(fine[fine > 0], 99.5) + 1e-6) + halo / (halo.max() + 1e-6) * 0.45
    lum = 1.0 - np.exp(-2.2 * lum)
    small = np.asarray(Image.fromarray(np.clip(lum * 255, 0, 255).astype(np.uint8), 'L').resize((size, size), Image.LANCZOS),
                       dtype=np.float32) / 255.0
    return white(small)


def reticle(size=TEX_SIZE, ss=2, seed=3101):
    """准星：圆圈 + 上下左右四道刻线（中间留空）+ 中心点，照大卢恩图标的画法——线条由发亮的颗粒组成，
    按噪声微微起伏、亮暗不均，外面一圈柔光，零星光屑往外飘；没有描边。先在 4 倍大的画布上撒颗粒再缩小"""
    n = size * ss
    c = n / 2
    rng = np.random.default_rng(seed)
    wob = noise(n, 6, seed + 1) * 0.6 + noise(n, 16, seed + 4) * 0.4   # 线条起伏（法线方向偏移）：大的弯 + 细的抖
    hot = noise(n, 22, seed + 2) ** 1.6                                 # 沿线的亮暗：有亮斑也有断口
    xs, ys, vs = [], [], []

    def add(pts, normals, density, core=n * 0.012, spread=n * 0.024, fleck=0.10):   # 线芯粗（用户 2026-10-28：要粗很多）
        p = np.asarray(pts, np.float32)
        nm = np.asarray(normals, np.float32)
        xi = np.clip(p[:, 0].astype(int), 0, n - 1)
        yi = np.clip(p[:, 1].astype(int), 0, n - 1)
        p = p + nm * ((wob[yi, xi] - 0.5) * n * 0.018)[:, None]
        x, y, v = path_grains(rng, p, nm, n, density, core, spread, fleck)
        v *= 0.15 + 2.2 * hot[np.clip(y.astype(int), 0, n - 1), np.clip(x.astype(int), 0, n - 1)]  # 亮暗不均
        xs.append(x), ys.append(y), vs.append(v)

    r = n * 0.30                                     # 圆圈
    th = np.linspace(0, 2 * np.pi, 4000, endpoint=False)
    add(np.c_[c + r * np.cos(th), c + r * np.sin(th)], np.c_[np.cos(th), np.sin(th)], 18)
    a, b = n * 0.12, n * 0.44                        # 四道刻线（离中心的内端、外端），外端渐淡
    t = np.linspace(0, 1, 1200)
    for ux, uy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        d = a + (b - a) * t
        add(np.c_[c + ux * d, c + uy * d], np.c_[np.full_like(t, -uy), np.full_like(t, ux)], 15)
        vs[-1] *= np.interp(np.hypot(xs[-1] - c, ys[-1] - c), [a, b * 0.8, b * 1.05], [1.0, 0.9, 0.15])
    th = np.linspace(0, 2 * np.pi, 600, endpoint=False)   # 中心点：一小圈颗粒
    add(np.c_[c + n * 0.022 * np.cos(th), c + n * 0.022 * np.sin(th)], np.c_[np.cos(th), np.sin(th)], 14, core=n * 0.012)
    acc = splat(n, np.concatenate(xs), np.concatenate(ys), np.concatenate(vs))
    return glow_texture(acc, size, ss)


def wisps(size=TEX_SIZE, ss=2, k=3, seed=3202):
    """气流：k 股往外旋的光屑流（颗粒画法同准星，头密尾疏、越往尾越淡）。只撒一股，再转 360/k 度复制，保证 k 重对称
    （特效里转过 360/k 度和刚放出来时一模一样，粒子一批接一批放就看不出接缝）"""
    n = size * ss
    c = n / 2
    rng = np.random.default_rng(seed)
    xs, ys, vs = [], [], []
    gap = noise(n, 14, seed + 1) ** 1.8               # 断续
    for off, r0, r1, sweep, dens in ((0.0, 0.33, 0.47, 115.0, 3.5), (16.0, 0.27, 0.40, 85.0, 2.0)):   # 一股主流 + 一股细的
        t = np.linspace(0, 1, 1500)
        th = np.radians(off + sweep * t)
        rr = n * (r0 + (r1 - r0) * t)
        pts = np.c_[c + rr * np.cos(th), c + rr * np.sin(th)]
        tan = np.gradient(pts, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True)
        nm = np.c_[-tan[:, 1], tan[:, 0]]
        x, y, v = path_grains(rng, pts, nm, n, dens, n * 0.006, n * 0.018, 0.12)
        tt = np.interp(np.hypot(x - c, y - c), [n * r0, n * r1], [0.0, 1.0])
        v *= (1.0 - tt) ** 1.4 * (0.1 + 2.4 * gap[np.clip(y.astype(int), 0, n - 1), np.clip(x.astype(int), 0, n - 1)])
        xs.append(x), ys.append(y), vs.append(v)
    x, y, v = np.concatenate(xs), np.concatenate(ys), np.concatenate(vs)
    allx, ally, allv = [], [], []
    for j in range(k):                               # 绕中心转 360/k 度复制
        a = 2 * np.pi * j / k
        allx.append(c + (x - c) * np.cos(a) - (y - c) * np.sin(a))
        ally.append(c + (x - c) * np.sin(a) + (y - c) * np.cos(a))
        allv.append(v)
    acc = splat(n, np.concatenate(allx), np.concatenate(ally), np.concatenate(allv))
    img = glow_texture(acc, size, ss)
    r, g, b, al = img.split()
    return Image.merge('RGBA', (r, g, b, al.point(lambda q: int(q * 0.9))))


def blood_moon(size=TEX_SIZE, ss=2, seed=4101):
    """血月的月面：圆盘，月海是低频噪声的暗斑，越靠边越亮（边缘发光）；边上一圈发亮的颗粒（同大卢恩图标的画法），外面一圈柔光。白色，颜色在特效里染"""
    from scipy.ndimage import gaussian_filter
    n = size * ss
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    d = np.hypot(xx - c, yy - c) / n
    r = 0.29
    disc = np.clip((r - d) / 0.008, 0.0, 1.0)
    maria = noise(n, 5, seed) * 0.6 + noise(n, 13, seed + 1) * 0.4          # 月海：大块暗斑 + 细碎的
    limb = np.clip(d / r, 0.0, 1.0) ** 4                                    # 边缘变亮
    # 月食的阴影：往左下错开的同样大的圆盖住一半，剩右上一道亮的月牙（血月被蚀的样子），阴影里留一点暗红
    sd = np.hypot(xx - c + 0.11 * n, yy - c - 0.08 * n) / n
    shadow = np.clip((r * 0.98 - sd) / 0.05, 0.0, 1.0)
    fill = disc * (0.06 + 0.6 * maria ** 2.4 + 0.3 * limb) * (1.0 - 0.88 * shadow)
    rng = np.random.default_rng(seed + 2)
    th = np.linspace(0, 2 * np.pi, 5000, endpoint=False)
    pts = np.c_[c + r * n * np.cos(th), c + r * n * np.sin(th)]
    x, y, v = path_grains(rng, pts, np.c_[np.cos(th), np.sin(th)], n, 14, n * 0.006, n * 0.02, 0.12)
    hot = noise(n, 18, seed + 3) ** 1.4
    v *= 0.2 + 2.0 * hot[np.clip(y.astype(int), 0, n - 1), np.clip(x.astype(int), 0, n - 1)]
    rim = gaussian_filter(splat(n, x, y, v), ss * 0.3)
    rim /= np.percentile(rim[rim > 0], 99.5) + 1e-6
    halo = gaussian_filter(disc * (1.0 - 0.7 * shadow) + rim * 0.5, ss * 10.0)
    rim *= 1.0 - 0.8 * shadow
    lum = fill * 1.2 + rim * 0.8 + halo / (halo.max() + 1e-6) * 0.3
    lum = 1.0 - np.exp(-1.7 * lum)
    small = np.asarray(Image.fromarray(np.clip(lum * 255, 0, 255).astype(np.uint8), 'L').resize((size, size), Image.LANCZOS),
                       dtype=np.float32) / 255.0
    return white(small)


def moon_runes(size=TEX_SIZE, ss=2, k=6, seed=4202):
    """符文环：一圈断续的细环 + k 个相同的小月牙，颗粒画法；只画一个再转 360/k 度复制，
    特效里转 360/k 度和刚放出来时一模一样"""
    n = size * ss
    c = n / 2
    rng = np.random.default_rng(seed)
    xs, ys, vs = [], [], []
    R = 0.41

    def stroke(p0, p1, dens=10):
        t = np.linspace(0, 1, 300)[:, None]
        pts = np.asarray(p0) * (1 - t) + np.asarray(p1) * t
        dv = np.asarray(p1, np.float32) - np.asarray(p0, np.float32)
        nm = np.tile(np.array([-dv[1], dv[0]], np.float32) / (np.hypot(*dv) + 1e-6), (len(t), 1))
        x, y, v = path_grains(rng, pts * n, nm, n, dens, n * 0.004, n * 0.012, 0.08)
        xs.append(x), ys.append(y), vs.append(v)
    # 一个符号（以 (0.5, 0.5 - R) 为中心，顶上那一个）：小月牙（外弧 + 内弧围出来）
    cx, cy = 0.5, 0.5 - R
    th = np.linspace(np.radians(200), np.radians(340), 260)          # 新月的外弧
    arc = np.c_[cx + 0.04 * np.cos(th), cy - 0.012 + 0.04 * np.sin(th)] * n
    x, y, v = path_grains(rng, arc, np.c_[np.cos(th), np.sin(th)], n, 12, n * 0.005, n * 0.013, 0.08)
    xs.append(x), ys.append(y), vs.append(v)
    th2 = np.linspace(np.radians(215), np.radians(325), 200)         # 内弧（和外弧围出月牙）
    arc2 = np.c_[cx + 0.032 * np.cos(th2), cy - 0.022 + 0.026 * np.sin(th2)] * n
    x, y, v = path_grains(rng, arc2, np.c_[np.cos(th2), np.sin(th2)], n, 8, n * 0.004, n * 0.011, 0.06)
    xs.append(x), ys.append(y), vs.append(v * 0.8)
    # 符号之间的细环（断续）：只画 0~60 度那一段里符号两边，复制后连成一圈
    gap = noise(n, 20, seed + 1) ** 2.0
    th = np.linspace(np.radians(-90 + 9), np.radians(-90 + 51), 600)
    ring = np.c_[c + R * n * np.cos(th), c + R * n * np.sin(th)]
    x, y, v = path_grains(rng, ring, np.c_[np.cos(th), np.sin(th)], n, 5, n * 0.003, n * 0.01, 0.1)
    v *= 0.15 + 1.6 * gap[np.clip(y.astype(int), 0, n - 1), np.clip(x.astype(int), 0, n - 1)]
    xs.append(x), ys.append(y), vs.append(v * 0.6)
    x, y, v = np.concatenate(xs), np.concatenate(ys), np.concatenate(vs)
    allx, ally, allv = [], [], []
    for j in range(k):
        a = 2 * np.pi * j / k
        allx.append(c + (x - c) * np.cos(a) - (y - c) * np.sin(a))
        ally.append(c + (x - c) * np.sin(a) + (y - c) * np.cos(a))
        allv.append(v)
    return glow_texture(splat(n, np.concatenate(allx), np.concatenate(ally), np.concatenate(allv)), size, ss)


def moon_preview(moon, runes):
    """血月预览.png：血红、金色并排，深色底 / 灰底两行（近似游戏里的发光）"""
    cell, size = 300, 260
    canvas = np.zeros((cell * 2, cell * len(BRAND_RGB), 3), np.float32)
    canvas[:cell] = 0.11
    canvas[cell:] = 0.40
    m_small = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ms = int(size * 0.6 / 1.1)
    m_small.paste(moon.resize((ms, ms), Image.LANCZOS), ((size - ms) // 2, (size - ms) // 2))
    r_big = runes.resize((size, size), Image.LANCZOS)
    for k, rgb in enumerate(BRAND_RGB):
        for row in (0, 1):
            y0, x0 = row * cell + (cell - size) // 2, k * cell + (cell - size) // 2
            part = canvas[y0:y0 + size, x0:x0 + size]
            part = over(part, r_big, tuple(v * 0.7 + 0.3 for v in rgb), 1.3, 0.55)
            canvas[y0:y0 + size, x0:x0 + size] = over(part, m_small, rgb, 1.4, 1.0)
    Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8), 'RGB').save(os.path.join(HERE, '血月预览.png'))


def dds_bc7(img):
    """RGBA 图 → 带完整 mip 的 BC7（sRGB）DDS，头照原版特效贴图（DX10、格式 99）"""
    w, h = img.size
    levels, data = [], bytearray()
    lv = img
    while True:
        levels.append(lv)
        if lv.size == (1, 1):
            break
        lv = lv.resize((max(1, lv.size[0] // 2), max(1, lv.size[1] // 2)), Image.BOX)
    for lv in levels:
        if lv.size[0] < 4:                          # 小于 4×4 的层也占一个块：补到 4×4
            pad = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
            pad.paste(lv, (0, 0))
            lv = pad
        data += encode(lv)
    hd = bytearray(148)
    struct.pack_into('<4sIIIIIII', hd, 0, b'DDS ', 124, 0x000A1007, h, w, (w // 4) * (h // 4) * 16, 1, len(levels))
    struct.pack_into('<II4s', hd, 76, 32, 4, b'DX10')
    struct.pack_into('<I', hd, 108, 0x401008)
    struct.pack_into('<IIIII', hd, 128, 99, 3, 0, 1, 0)
    return bytes(hd) + bytes(data), len(levels)


def dcx_zstd(raw, level=15):
    """ZSTD 压缩的 DCX（头照 ELDEN VINS 的 sfxbnd_c0000：它在游戏里能用）；libzstd.dll 在 randomizer 目录"""
    import ctypes
    z = ctypes.CDLL(os.path.join(PALY, 'randomizer', 'libzstd.dll'))
    z.ZSTD_compressBound.restype = ctypes.c_size_t
    z.ZSTD_compress.restype = ctypes.c_size_t
    cap = z.ZSTD_compressBound(ctypes.c_size_t(len(raw)))
    buf = ctypes.create_string_buffer(cap)
    n = z.ZSTD_compress(buf, ctypes.c_size_t(cap), raw, ctypes.c_size_t(len(raw)), level)
    comp = buf.raw[:n]
    head = (b'DCX\0' + struct.pack('>IIIII', 0x11000, 0x18, 0x24, 0x44, 0x4C)
            + b'DCS\0' + struct.pack('>II', len(raw), len(comp))
            + b'DCP\0' + b'ZSTD' + struct.pack('>I', 0x20) + bytes([level, 0, 0, 0])
            + struct.pack('>IIII', 0, 0, 0, 0x00010100)
            + b'DCA\0' + struct.pack('>I', 8))
    assert len(head) == 0x4C
    out = head + comp
    if erlib.dcx_decompress(out) != raw:
        raise RuntimeError('ZSTD 压缩后解不回来')
    return out


def tpf(name, dds, mips):
    return erlib.write_tpf(dict(flag2=3, enc=1, tex=[dict(name=name, fmt=0, type=0, mips=mips, flags1=0, flags2=0, data=dds)]))


def check():
    p = os.path.join(os.path.dirname(PALY), 'ELDEN VINS', 'mod', 'sfx', 'sfxbnd_c0000.ffxbnd.dcx')
    raw = erlib.read_dcx(p)
    again = write_bnd4(read_bnd4_full(raw), head=raw[:12], version=raw[0x18:0x20])
    same = again == raw
    print('ELDEN VINS 的 sfxbnd_c0000：%d 字节，按本工具重写%s' % (len(raw), '逐字节一致' if same else '不一致'))
    if not same:
        diff = next(i for i in range(min(len(raw), len(again))) if raw[i] != again[i])
        print('  第一个不同在 0x%x（长度 %d / %d）' % (diff, len(raw), len(again)))
    return same


# ---------------------------------------------------------------- 主流程
def over(bg, img, rgb, mult, alpha):
    """近似游戏里的样子：白色贴图乘上颜色 × 亮度倍数（超过 1 的部分算泛光往外溢），按透明度叠到底图上（浮点 RGB 数组）"""
    from scipy.ndimage import gaussian_filter
    a = np.asarray(img.split()[3], dtype=np.float32)[..., None] / 255.0 * alpha
    col = np.asarray(rgb, np.float32) * mult
    out = bg * (1 - a) + np.minimum(col, 1.0) * a
    hot = np.maximum(col - 1.0, 0.0) + 0.15 * col          # 泛光：亮出去的部分模糊后加上去
    return out + gaussian_filter(a[..., 0], 6)[..., None] * hot * 0.9


def preview(ret, wisp, frames=12):
    """三层并排：上面一行深色底（夜里 / 室内）、下面一行灰底；准星（层色发光）+ 气流（更淡的同色，转 120 度一圈）；
    png 是第一帧，gif 是转动"""
    cell, size = 260, 220
    font = ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc', 16)
    rs = int(size * 0.55 / 0.85)                             # 准星 0.55 米、气流 0.85 米
    r_big = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    r_big.paste(ret.resize((rs, rs), Image.LANCZOS), ((size - rs) // 2, (size - rs) // 2))
    w_big = wisp.resize((size, size), Image.LANCZOS)
    shots = []
    for f in range(frames):
        canvas = np.zeros((cell * 2 + 30, cell * len(HUNT_RGB), 3), np.float32)
        canvas[:30 + cell] = 0.11
        canvas[30 + cell:] = 0.40
        wr = w_big.rotate(120.0 * f / frames, Image.BICUBIC)   # 头在前、尾巴拖在后
        for k, rgb in enumerate(HUNT_RGB):
            wc = tuple(v * (1 - WISP_MIX) + WISP_MIX for v in rgb)
            for row in (0, 1):
                y0, x0 = 30 + row * cell + (cell - size) // 2, k * cell + (cell - size) // 2
                part = canvas[y0:y0 + size, x0:x0 + size]
                part = over(part, wr, wc, WISP_MULT, WISP_ALPHA)
                canvas[y0:y0 + size, x0:x0 + size] = over(part, r_big, rgb, RET_MULT, 1.0)
        im = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8), 'RGB')
        d = ImageDraw.Draw(im)
        for k in range(len(HUNT_RGB)):
            d.text((k * cell + cell // 2 - 16, 6), '%d 层' % (k + 1), fill=(255, 255, 255), font=font)
        shots.append(im)
    shots[0].save(os.path.join(HERE, '准星预览.png'))
    shots[0].save(os.path.join(HERE, '准星预览.gif'), save_all=True, append_images=shots[1:], duration=125, loop=0)


def main():
    if '--check' in sys.argv:
        sys.exit(0 if check() else 1)
    ret, wisp = reticle(), wisps()
    preview(ret, wisp)
    moon, runes = blood_moon(), moon_runes()
    moon_preview(moon, runes)
    tex = []
    for tid, img in ((HUNT_TEX, ret), (HUNT_WISP_TEX, wisp), (MOON_TEX, moon), (RUNE_TEX, runes)):
        dds, mips = dds_bc7(img)
        tex.append(('s%05d_a' % tid, tpf('s%05d_a' % tid, dds, mips)))
    debug = '--debug' in sys.argv                   # 排查变体（sfx\debug_variants.js 生成在 sfx\debug\，没有的用正式的）
    names = [name for name, _ in tex] + (['s10011_a', 's34060_a'] if debug else [])   # 变体 B / C 用的原版贴图
    reslist = ''.join(name + '.tif\r\n' for name in names).encode('ascii')    # 每个特效都列这几张
    files, res = [], []
    for k, fid in enumerate(HUNT_FXR):
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if debug and os.path.isfile(os.path.join(SRC, 'debug', 'f%09d.fxr' % fid)):
            p = os.path.join(SRC, 'debug', 'f%09d.fxr' % fid)
            print('排查变体：', p)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, reslist))
    for fid in BRAND_FXR:                            # 七咒「烙印」的血月印记（资源清单同猎印：列我们的几张贴图）
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 brand_mark.js（见 自制特效.md）' % p)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, reslist))
    for fid, src in DRAIN_FXR:                       # 夺取魇火的吸取特效：资源清单照抄原版的（贴图都在常驻的公共特效包里）
        _, drain_res = vanilla_fxr(src)
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 drain.js（见 自制特效.md）' % p)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, drain_res))
    _, pebble_res = vanilla_fxr(PEBBLE_FXR)          # 环绕法球：资源清单照抄原版魔砾的
    for fid in ORBIT_FXR:
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 orbs.js（见 自制特效.md）' % p)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, pebble_res))
    import boat_model                                # 唤声船的灵船：模型、贴图、特效（资源清单列模型和它的贴图，照原版带模型的特效）
    boat_files, boat_res, boat_info = boat_model.files()
    for fid, mid in BOAT_FXR:
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 boat.js（见 自制特效.md）' % p)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, ''.join(n + '\r\n' for n in boat_res[mid]).encode('ascii')))
    for fid, src in CLASH_SPARK_FXR:                 # 相杀的防御火花：资源清单照抄原版
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 clash_spark.js（见 自制特效.md）' % p)
        _, spark_res = vanilla_fxr(src)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, spark_res))
    for fid, src in LANTERN_FXR:                     # 提灯的光源：资源清单照抄原版
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 lantern.js（见 自制特效.md）' % p)
        _, lamp_res = vanilla_fxr(src)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, lamp_res))
    for fid, src in BARRIER_FXR:                     # 死亡以上难度错配屏障
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 barrier_dome.js（见 自制特效.md）' % p)
        _, dome_res = vanilla_fxr(src)
        have = dome_res.decode('ascii', 'replace').split()
        dome_res = ''.join(n + '\r\n' for n in have + [t + '.tif' for t in BARRIER_EXTRA_TEX if t + '.tif' not in have]).encode('ascii')
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, dome_res))
    flash_res = reslist + ''.join(t + '.tif\r\n' for t in FLASH_EXTRA_TEX).encode('ascii')
    for fid, js in FLASH_FXR:                        # 词条触发时一闪的（猎印碎裂）
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 %s（见 自制特效.md）' % (p, js))
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, flash_res))
    glow_fxr, glow_res = vanilla_fxr(HASTE_GLOW_SRC)  # 加速光晕：原版 440701 原样复制、只换文件头的编号
    if struct.unpack_from('<I', glow_fxr, 12)[0] != HASTE_GLOW_SRC:
        raise RuntimeError('原版 %d 的文件头和预想的不一样，换不了编号' % HASTE_GLOW_SRC)
    for fid in HASTE_GLOW_FXR:
        b = bytearray(glow_fxr)
        struct.pack_into('<I', b, 12, fid)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, bytes(b)))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, glow_res))
    vanilla_fxr(BREATH_TAIL_FXR)
    for fid, src in BREATH_FXR:                      # 换气：资源清单照抄原版回血光
        p = os.path.join(SRC, 'f%09d.fxr' % fid)
        if not os.path.isfile(p):
            raise RuntimeError('缺 %s：先用 fxrlab 生成 second_breath.js（见 自制特效.md）' % p)
        _, breath_res = vanilla_fxr(src)
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % fid, open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % fid, breath_res))
    # 范围战灰放大的子弹特效（sfx\aoe_scale.js 按 sfx\aoe_scale.json 生成；资源清单照抄原版那份，贴图都在常驻的公共特效包里）
    aoe = os.path.join(SRC, 'aoe_scale.json')
    for j in (json.load(open(aoe, encoding='utf-8')) if os.path.isfile(aoe) else []):
        p = os.path.join(SRC, 'f%09d.fxr' % j['id'])
        rl = os.path.join(SRC, 'vanilla', 'f%09d.ffxreslist' % j['src'])
        if not os.path.isfile(p) or not os.path.isfile(rl):
            raise RuntimeError('缺 %s 或 %s：先跑 aoe_sfx_fetch.py，再用 fxrlab 生成 aoe_scale.js（见 自制特效.md）' % (p, rl))
        k = len(files)
        files.append((k, ROOT + 'effect\\f%09d.fxr' % j['id'], open(p, 'rb').read()))
        res.append((400000 + k, ROOT + 'ResourceList\\f%09d.ffxreslist' % j['id'], open(rl, 'rb').read()))
    models = []
    # 上面那些特效用到、但不在常驻公共特效包里的原版模型（aoe_sfx_fetch.py 从拉卡德的特效包 c4710 拷的 s88830，狩猎大蛇用）
    am = os.path.join(SRC, 'aoe_models.json')
    for flv, path in (json.load(open(am, encoding='utf-8')).items() if os.path.isfile(am) else []):
        models.append((200000 + len(models), ROOT + path, open(os.path.join(SRC, 'vanilla', 'model', flv), 'rb').read()))
    for name, data in boat_files:
        if name.startswith('tex\\'):
            tex.append((os.path.basename(name)[:-4], data))
        else:
            models.append((200000 + len(models), ROOT + name, data))
    print(boat_info)
    for k, (name, data) in enumerate(tex):
        files.append((100000 + k, ROOT + 'tex\\%s.tpf' % name, data))
    files += models
    raw = write_bnd4(files + res)
    if read_bnd4_full(raw) != files + res:
        raise RuntimeError('打包后读回来不一致')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'wb').write(dcx_zstd(raw))
    print('写好 %s（%d 个文件，%d 字节）' % (OUT, len(files + res), os.path.getsize(OUT)))


if __name__ == '__main__':
    main()
