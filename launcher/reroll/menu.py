# -*- coding: utf-8 -*-
"""Dark Reforged 菜单覆盖包：自制状态图标（buff 图标，画法见 dev\\item_system\\make_icons.py）、赐福菜单图集（同一个脚本）、稀有度边框图标（make_frames.py）。

从本机游戏的 Data0 取原版 menu\\hi、low 的 01_common.tpf.dcx / 01_common.sblytbnd.dcx（只读，不改游戏文件）：
  我们的图标（data\\menu\\dr_status.dds，和原版图集 SB_Status_00 一样大）按 BC7 压缩块拷进原版 SB_Status_00 右边的空白
  （尺寸不改，原版图标一点不动；和原版图标的位置重了就报错）；它的布局 SB_Status_00.layout 末尾加上 data\\menu\\dr_status.layout 的行。
  （第一版把 SB_Status_01_dlc 从 256 扩到 512、编号 21000 起，游戏里没正常显示，2026-10-28 改成这样）
稀有度边框图标（dev\\item_system\\make_frames.py 生成；data\\menu\\dr_frames_NN.dds / .layout 连号成对、加上 dr_frames.txt 才做）：
  每张是一张新图集 SB_Icon_DR_NN（贴图 + 新的布局文件 SB_Icon_DR_NN.layout，照原版 SB_Icon_00 的格式和目录，布局包整个重写）。
  合成成功后把对照表 dr_frames.txt 抄成 dll\\dark_core\\frames.txt（DLL 按它把生成装备的图标换成带框的）；
  一开始先删掉，失败了就没有，DLL 照原版图标（不会指到菜单包里没有的图标）。
赐福菜单（sc\\gracelook.py）：data\\menu\\dr_grace.dds / .layout 作为新贴图 SB_DR_Grace（照 SB_Status_00 的格式，布局文件放它旁边）；
  赐福 / NPC 对话菜单 03_000_shoptop.gfx（标题图标 MENU_FL_BonFire / MENU_FL_Talk 就是它；2026-11-03 第一次误改了 03_063_talkchoice，
  游戏里没变）里引用的选中框 MENU_FL_Cursor_Wide（4 处）换成同样长的 MENU_DR_Cursor_Wide（我们图集里的金色版），
  写 <--out>\\menu\\03_000_shoptop.gfx（原版这张图还有约 40 个别的菜单在用，所以不改原图）。
hi、low 两套都做（原版两套的 SB_Status_00、SB_Icon_* 一模一样，2026-10-29 比过；只改 hi 的话低分辨率下生成装备的图标会空）。
装备工坊界面（dll\\dark_ui，2026-10-31 照原版商店重做）用的原版素材（UI_SPRITES：背景、光条、对话框、页签、手柄按键图标）：
  从 hi 的原版图集里按布局裁出来（扩到 4 像素对齐，压缩块原样拷），写 <--out>\\dark_ui_sprites.bin（只在本机，不打包）。
  格式：第一行 DRUI 1，每个精灵一行「名字 格式(DXGI) 块区宽 块区高 精灵在块区里的 x y 宽 高 偏移 长度」（Tab 分隔），空行，后面是块数据。
  还有游戏自带的字体（用户 2026-10-31）：Data0 的 /font/simplifiedchinese、eu_std/font.gfx 转成 TTF（gfxfont.py），
  写 <--out>\\dark_ui_font_zh.ttf / dark_ui_font_en.ttf（同样只在本机）。
标题封面（用户 2026-11-05：不要原版大卢恩，普通和「死亡」以上各一张；画法见 dev\\title_menu\\make_covers.py）：
  data\\menu\\dr_title_normal / hard.dds（全屏 3840×2160）各做一个小包，<--out 的上一层>\\title\\<封面>\\menu 下放 05_001_title_logo.gfx
  （title_gfx：Logo 贴图名换成同样长的 MENU_Title_DarkForge_01，图的尺寸改成全屏、位置移到左上角，按原来的 0.5 倍正好铺满）
  和 05_000_title.gfx（title_menu_gfx：去掉菜单底下那条渐变黑，原版背景全黑看不出来，封面上是一条黑边）
  封面有 dr_title_<封面>_anim.bin 就是动画版（dev\\title_menu\\make_anim.py 做的）：图换成 _base.dds，新定义拼在 Logo 精灵前面、新放置拼进精灵，
  _top / _ring / _sp 这些贴图叫 MENU_Title_DF_<后缀>，一起放进 02_title。删掉 anim.bin 就是静态版（dr_title_<封面>.dds）。
  和 hi、low 的 02_title.tpf.dcx（原版的开机 Logo 加上我们这张，同法魂的做法：单独一张贴图放 02_title，不动 100 MB 的 01_common，换封面不用重建）。
  启动器按这次的难度挂其中一个（launcher.ps1 Get-MenuLine）。有自己的时间戳，失败了照常出菜单包，只是标题还是原版。
写到 <--out>\\menu\\hi、low（DFLT 压缩，游戏能读）。游戏的 Data0（大小、修改时间）、我们的文件、本工具都没变就不重做
（<--out>\\stamp.txt；不用解开 Data0，约 0.1 秒；边框图集大，按大小和修改时间算）。
菜单图集（stamp.txt）、界面素材和字体（ui_stamp.txt）、两张标题封面（..\\title\\<封面>.stamp.txt）各算各的，代码指纹只算这部分用到的函数和常量（code_fp）。
最后打印一行 JSON（启动器读）：{"ok": true/false, "msg": "..."}；失败时启动器照常启动，只是这次没有自制图标。

用法：python menu.py --out <覆盖包目录> --game <游戏的 Game 目录> --dll-dir <含 oo2core 的目录> [--dll-dir ...] [--core-dir <dark_core 目录>]
"""
import argparse
import ast
import hashlib
import json
import os
import re
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import erlib  # noqa: E402
import gfxfont  # noqa: E402

DATA = os.path.join(HERE, 'data', 'menu')
ATLAS = 'SB_Status_00'
TPF_PATH, LAYOUT_PATH = '/menu/%s/01_common.tpf.dcx', '/menu/%s/01_common.sblytbnd.dcx'
QUALITIES = ('hi', 'low')
CORE_DIR = os.path.join(HERE, '..', '..', 'dll', 'dark_core')
FRAME_ATLAS, REF_ATLAS = 'SB_Icon_DR_%02d', 'SB_Icon_00'   # 边框图集照 SB_Icon_00 的格式
GRACE_ATLAS = 'SB_DR_Grace'                                # 赐福菜单图集，照 SB_Status_00 的格式
TALK_GFX, TALK_CURSOR = '/menu/03_000_shoptop.gfx', (b'MENU_FL_Cursor_Wide', b'MENU_DR_Cursor_Wide')
OLD_GFX = ('03_063_talkchoice.gfx',)                        # 以前写过、现在不要的（启动时删掉）
TITLE_GFX, TITLE_TPF = '/menu/05_001_title_logo.gfx', '/menu/%s/02_title.tpf.dcx'
TITLE_NAME = (b'MENU_Title_EldenRing_01', b'MENU_Title_DarkForge_01')    # 外部图片标签的名字、文件名，AS3 的符号：同样长，一起换
TITLE_COVERS, TITLE_SIZE = ('normal', 'hard'), (3840, 2160)
TITLE_OLD_SIZE, TITLE_OLD_POS = (2532, 1532), (6595, 321)      # 原版这张图的尺寸、位置（1/20 像素：329.75, 16.05），0.5 倍
TITLE_MENU_GFX = '/menu/05_000_title.gfx'
UI_FILE = 'dark_ui_sprites.bin'
UI_FONTS = (('dark_ui_font_zh.ttf', '/font/simplifiedchinese/font.gfx'), ('dark_ui_font_en.ttf', '/font/eu_std/font.gfx'))
UI_SPRITES = (
    'MENU_BaseMain_01', 'MENU_BaseMain_02', 'MENU_TitleBase', 'MENU_Item_waku', 'MENU_SlotBase', 'MENU_SL_Cursor',
    'MENU_FL_scroll_waku', 'MENU_FL_scroll_Bar', 'MENU_FL_scroll_Edge', 'MENU_Br_Line_00', 'MENU_Br_Line_01',
    'MENU_FL_Cursor_Top', 'MENU_FL_Cursor_Wide', 'MENU_FL_Cursor_Ent', 'MENU_FL_Cursor_EntWaku', 'MENU_FL_Cursor_Half',
    'MENU_FL_Dialog', 'MENU_FL_Dialog_02', 'MENU_FL_Unchku_s', 'MENU_FL_Tab_base', 'MENU_FL_Tab_Cursor', 'MENU_FL_BrightWaku',
    'MENU_FL_SelectWaku', 'MENU_FL_Select_Cursor', 'MENU_FL_MenuBase', 'MENU_Line_01', 'MENU_FL_HelpCursor',
    'MENU_FL_Rar_d0', 'MENU_FL_Rar_d1', 'MENU_FL_Rar_d2',
    'MENU_Tab_Armor', 'MENU_Tab_10', 'MENU_Tab_11', 'MENU_Tab_12', 'MENU_Tab_13', 'MENU_Tab_15',
    'MENU_Tab_Weapon', 'MENU_Tab_07', 'MENU_Tab_08', 'MENU_Tab_09', 'MENU_Tab_29_Buddy', 'MENU_EquMark',
    'KG_XboxSeries_R_D', 'KG_XboxSeries_R_R', 'KG_XboxSeries_R_L', 'KG_XboxSeries_R_U', 'KG_XboxSeries_L1', 'KG_XboxSeries_R1',
    'KG_XboxSeries_L2', 'KG_XboxSeries_R2', 'KG_XboxSeries_Start',
    'KG_XboxSeries_L_UD', 'KG_XboxSeries_L_LR', 'KG_XboxSeries_L_UDLR',
)


def dds_size(d):
    h, w = struct.unpack_from('<II', d, 12)
    if d[:4] != b'DDS ' or d[84:88] != b'DX10' or struct.unpack_from('<I', d, 128)[0] != 98:
        raise ValueError('不是 BC7（DX10）的 DDS')
    return w, h


def rects(lines):
    return [tuple(map(int, m.groups())) for m in (re.search(r'x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', l) for l in lines) if m]


def merge_atlas(vanilla, ours, our_rects, vanilla_rects, atlas=ATLAS):
    """我们每个图标那几格的 BC7 块拷进原版图集，返回整张 DDS（尺寸、原版的块都不变）"""
    vw, vh = dds_size(vanilla)
    if dds_size(ours) != (vw, vh):
        raise ValueError('原版 %s 是 %d×%d，和我们的图集（%d×%d）不一样大（游戏更新过？要重画图标）' % ((atlas, vw, vh) + dds_size(ours)))
    data = bytearray(vanilla)
    for x, y, w, h in our_rects:
        if x % 4 or y % 4 or w % 4 or h % 4:
            raise ValueError('图标位置没对齐 4 像素：%d,%d' % (x, y))
        if any(x < vx + vw_ and vx < x + w and y < vy + vh_ and vy < y + h for vx, vy, vw_, vh_ in vanilla_rects):
            raise ValueError('图标 %d,%d 和原版图标的位置重了（游戏更新过？要重画图标）' % (x, y))
        for by in range(y // 4, (y + h) // 4):
            at = 148 + (by * (vw // 4) + x // 4) * 16
            data[at:at + (w // 4) * 16] = ours[at:at + (w // 4) * 16]
    return bytes(data)


def patch_layout(text, lines, taken):
    """布局末尾（</TextureAtlas> 前）加我们的行；编号和原版重了就报错"""
    for l in lines:
        n = re.search(r'name="([^"]+)"', l).group(1)
        if n in taken:
            raise ValueError('图标 %s 原版已经有了' % n)
    end = text.rindex('</TextureAtlas>')
    return text[:end] + ''.join('\t' + l + '\n' for l in lines) + text[end:]


def dds_blocks(d):
    """(DXGI 格式, 宽, 高, 每块字节, 数据起点)：DX10 头的按它的格式，老的 DXT1 / DXT3 / DXT5"""
    h, w = struct.unpack_from('<II', d, 12)
    if d[84:88] == b'DX10':
        fmt = struct.unpack_from('<I', d, 128)[0]
        off = 148
    else:
        fmt = {b'DXT1': 71, b'DXT3': 74, b'DXT5': 77}.get(bytes(d[84:88]))
        off = 128
    if fmt in (71, 72):
        return fmt, w, h, 8, off
    if fmt in (74, 75, 77, 78, 98, 99):
        return fmt, w, h, 16, off
    raise ValueError('不认识的贴图格式 %r' % fmt)


def export_ui(tpf, bnd, path):
    """装备工坊界面（dll\\dark_ui）用的原版素材：按布局裁出 UI_SPRITES，写 path（格式见文件头）。返回导出了几个、缺了哪些"""
    where = {}
    for n in bnd.entries:
        t = bnd.get(n).decode('utf-8', 'replace')
        img = re.search(r'imagePath="([^"]+)\.png"', t)
        if not img:
            continue
        for m in re.finditer(r'name="([^"]+)\.png" x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', t):
            where.setdefault(m.group(1), (img.group(1),) + tuple(int(v) for v in m.groups()[1:]))
    texs = {x['name']: x['data'] for x in tpf['tex']}
    lines, blobs, off, missing = [], [], 0, []
    for name in UI_SPRITES:
        if name not in where or where[name][0] not in texs:
            missing.append(name)
            continue
        atlas, x, y, w, h = where[name]
        d = texs[atlas]
        fmt, aw, ah, bsz, base = dds_blocks(d)
        x0, y0 = x // 4 * 4, y // 4 * 4
        x1, y1 = min(aw, (x + w + 3) // 4 * 4), min(ah, (y + h + 3) // 4 * 4)
        row = aw // 4 * bsz
        part = b''.join(bytes(d[base + by * row + x0 // 4 * bsz: base + by * row + x1 // 4 * bsz]) for by in range(y0 // 4, y1 // 4))
        lines.append('%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d' % (name, fmt, x1 - x0, y1 - y0, x - x0, y - y0, w, h, off, len(part)))
        blobs.append(part)
        off += len(part)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(('DRUI 1\n' + '\n'.join(lines) + '\n\n').encode('utf-8'))
        for b in blobs:
            f.write(b)
    os.replace(tmp, path)
    return len(lines), missing


def frames_files():
    """稀有度边框图标的数据：([(dr_frames_NN.dds, .layout)…], dr_frames.txt)；连号成对、对照表也在才算有"""
    atlases = []
    while os.path.isfile(os.path.join(DATA, 'dr_frames_%02d.dds' % len(atlases))):
        k = len(atlases)
        lay = os.path.join(DATA, 'dr_frames_%02d.layout' % k)
        if not os.path.isfile(lay):
            return None
        atlases.append((os.path.join(DATA, 'dr_frames_%02d.dds' % k), lay))
    txt = os.path.join(DATA, 'dr_frames.txt')
    return (atlases, txt) if atlases and os.path.isfile(txt) else None


def load_frames(frames):
    """[(图集名, DDS, 布局行)]（hi、low 共用一份）"""
    out = []
    for k, (dds, lay) in enumerate(frames[0]):
        data = open(dds, 'rb').read()
        dds_size(data)
        out.append((FRAME_ATLAS % k, data, [l.strip() for l in open(lay, encoding='utf-8').read().splitlines() if l.strip()]))
    return out


def add_frames(tpf, files, atlases, taken, ref_atlas=REF_ATLAS):
    """新图集（边框、赐福菜单）加进贴图包（tpf）和布局包（files：read_bnd4_full 的列表，就地加，编号接在最后）；
    贴图照原版 ref_atlas 的格式、大小要一样，布局文件放在它的旁边"""
    ref = next(x for x in tpf['tex'] if x['name'] == ref_atlas)
    names = {x['name'] for x in tpf['tex']}
    ref_lay = next(f for f in files if f[1].endswith('\\' + ref_atlas + '.layout'))
    folder = ref_lay[1][:ref_lay[1].rindex('\\') + 1]
    nid = max(f[0] for f in files) + 1
    for k, (name, data, lines) in enumerate(atlases):
        if name in names:
            raise ValueError('原版已经有贴图 %s' % name)
        if dds_size(ref['data']) != dds_size(data):
            raise ValueError('原版 %s 的大小变了（游戏更新过？要重画 %s）' % (ref_atlas, name))
        dup = [n for l in lines for n in re.findall(r'name="([^"]+)"', l) if n in taken]
        if dup:
            raise ValueError('图标 %s 原版已经有了' % dup[:3])
        tpf['tex'].append(dict(ref, name=name, data=data))
        text = '<TextureAtlas imagePath="%s.png">\n' % name + ''.join('\t' + l + '\n' for l in lines) + '</TextureAtlas>\n\r\n'
        files.append((nid + k, folder + name + '.layout', text.encode('utf-8')))


def code_fp(roots, stop=()):
    """从 roots 往下用到的本文件函数和常量的语法树指纹（注释、别的部分的代码不算）：
    菜单图集（约 15 秒）、界面素材（约 8 秒）、标题封面各算各的，改一部分不用重做别的（用户 2026-11-05「各部分分别缓存」）"""
    defs = {}
    for n in ast.parse(open(__file__, encoding='utf-8-sig').read()).body:
        if isinstance(n, ast.FunctionDef):
            defs[n.name] = n
        elif isinstance(n, ast.Assign):
            defs.update((t.id, n) for t in n.targets if isinstance(t, ast.Name))
    seen, todo = set(), list(roots)
    while todo:
        k = todo.pop()
        if k in seen or k in stop or k not in defs:
            continue
        seen.add(k)
        todo += [x.id for x in ast.walk(defs[k]) if isinstance(x, ast.Name)]
    return hashlib.sha1('\n'.join(ast.dump(defs[k]) for k in sorted(seen)).encode('utf-8')).hexdigest()


UI_ROOTS = ('export_ui', 'UI_SPRITES', 'UI_FONTS', 'UI_FILE')


def build(out, game, core=CORE_DIR):
    frames_txt = os.path.join(core, 'frames.txt')
    if os.path.exists(frames_txt):
        os.remove(frames_txt)                   # 合成成功才写回去：失败时 DLL 不换图标
    frames = frames_files()
    ours_dds = open(os.path.join(DATA, 'dr_status.dds'), 'rb').read()
    ours_lay = open(os.path.join(DATA, 'dr_status.layout'), encoding='utf-8').read()
    lines = [l.strip() for l in ours_lay.splitlines() if l.strip()]
    grace_paths = [os.path.join(DATA, 'dr_grace' + e) for e in ('.dds', '.layout')]
    grace = all(os.path.isfile(p) for p in grace_paths)
    grace_lines = [l.strip() for l in open(grace_paths[1], encoding='utf-8').read().splitlines() if l.strip()] if grace else []
    icon_msg = '自制状态图标 %d 个%s' % (len(lines), '、赐福菜单图标 %d 个和金色选中框' % (len(grace_lines) - 1) if grace else '')
    bhd = os.path.join(game, 'Data0.bhd')
    st = [os.stat(p) for p in (bhd, bhd[:-4] + '.bdt')]
    big = ([p for pair in frames[0] for p in pair] + [frames[1]] if frames else []) + (grace_paths if grace else [])
    stamp = hashlib.sha1(repr([(s.st_size, s.st_mtime_ns) for s in st + [os.stat(p) for p in big]]).encode('ascii')
                         + ours_dds + ours_lay.encode('utf-8') + code_fp(['build'], UI_ROOTS).encode('ascii')).hexdigest()
    # 装备工坊的界面素材和字体只看原版 Data0 和自己这部分代码，图标、边框变了不用重做
    ui_stamp = hashlib.sha1(repr([(s.st_size, s.st_mtime_ns) for s in st]).encode('ascii') + code_fp(UI_ROOTS).encode('ascii')
                            + open(gfxfont.__file__, 'rb').read()).hexdigest()
    n_frames = sum(1 for l in open(frames[1], encoding='utf-8') if l.strip() and not l.startswith('#')) if frames else 0
    frame_msg = '、稀有度边框图标 %d 个（%d 张图集）' % (n_frames, len(frames[0])) if frames else ''
    targets = {q: [os.path.join(out, 'menu', q, os.path.basename(p % q)) for p in (TPF_PATH, LAYOUT_PATH)] for q in QUALITIES}
    talk_gfx = os.path.join(out, 'menu', os.path.basename(TALK_GFX))
    for f in OLD_GFX:
        if os.path.exists(os.path.join(out, 'menu', f)):
            os.remove(os.path.join(out, 'menu', f))
    stamp_path = os.path.join(out, 'stamp.txt')
    ui_path = os.path.join(out, UI_FILE)
    ui_stamp_path = os.path.join(out, 'ui_stamp.txt')
    ui_files = [ui_path] + [os.path.join(out, f) for f, _ in UI_FONTS]
    same = lambda path, want: os.path.isfile(path) and open(path, encoding='ascii').read().strip() == want
    atlas_ok = all(os.path.isfile(p) for t in targets.values() for p in t) and os.path.isfile(talk_gfx) == grace and same(stamp_path, stamp)
    ui_ok = all(os.path.isfile(p) for p in ui_files) and same(ui_stamp_path, ui_stamp)
    if atlas_ok and ui_ok:
        copy_frames(frames, frames_txt)
        return '%s%s（没变，沿用上次的）' % (icon_msg, frame_msg)
    arc = erlib.GameArchive(bhd, open(os.path.join(DATA, 'data0_key.pem'), encoding='ascii').read())
    atlases = load_frames(frames) if frames and not atlas_ok else []
    graces = [(GRACE_ATLAS, open(grace_paths[0], 'rb').read(), grace_lines)] if grace and not atlas_ok else []
    for done, path in ((atlas_ok, stamp_path), (ui_ok, ui_stamp_path)):
        if not done and os.path.exists(path):
            os.remove(path)                     # 写到一半失败的话下次重做
    ui_msg = ''
    for q in QUALITIES:
        if atlas_ok and q != 'hi':              # 图集没变，只做界面素材（它只要 hi 那一份）
            continue
        tpf = erlib.read_tpf(erlib.dcx_decompress(arc.read(TPF_PATH % q)))
        bnd = erlib.Bnd4(erlib.dcx_decompress(arc.read(LAYOUT_PATH % q)))
        if q == 'hi' and not ui_ok:
            os.makedirs(out, exist_ok=True)
            n_ui, miss = export_ui(tpf, bnd, ui_path)
            ui_msg = '、装备工坊界面素材 %d 个%s' % (n_ui, '（原版没找到：%s）' % '、'.join(miss) if miss else '')
            fonts = []
            for fname, src in UI_FONTS:
                try:
                    ttf, name, n = gfxfont.to_ttf(arc.read(src))
                    tmp = os.path.join(out, fname + '.tmp')
                    open(tmp, 'wb').write(ttf)
                    os.replace(tmp, os.path.join(out, fname))
                    fonts.append('%s %d 字' % (name.split()[0].replace('GR-', ''), n))
                except Exception as e:      # 字体转不出来：界面用系统字体，不影响菜单包
                    fonts.append('%s 转换失败（%s）' % (src, e))
                    open(os.path.join(out, fname), 'wb').close()
            ui_msg += '、游戏字体（%s）' % '、'.join(fonts)
            open(ui_stamp_path, 'w', encoding='ascii').write(ui_stamp + '\n')
        if atlas_ok:
            continue
        taken = {m for n in bnd.entries for m in re.findall(r'name="([^"]+)"', bnd.get(n).decode('utf-8', 'replace'))}
        name = ATLAS + '.layout'
        vanilla_lay = bnd.get(name).decode('utf-8')
        tex = next(x for x in tpf['tex'] if x['name'] == ATLAS)
        tex['data'] = merge_atlas(tex['data'], ours_dds, rects(lines), rects(vanilla_lay.splitlines()))
        bnd.put(name, patch_layout(vanilla_lay, lines, taken).encode('utf-8'))
        lay_raw = bytes(bnd.data)
        if atlases or graces:
            files = erlib.read_bnd4_full(lay_raw)
            add_frames(tpf, files, atlases, taken)
            add_frames(tpf, files, graces, taken, ATLAS)
            lay_raw = erlib.write_bnd4(files, head=lay_raw[:12], version=lay_raw[0x18:0x20])
        os.makedirs(os.path.dirname(targets[q][0]), exist_ok=True)
        for path, raw in zip(targets[q], (erlib.write_tpf(tpf), lay_raw)):
            tmp = path + '.tmp'
            open(tmp, 'wb').write(erlib.dcx_compress_dflt(raw))
            os.replace(tmp, path)
        del tpf
    if not atlas_ok:
        write_talk_gfx(arc, talk_gfx, grace)
        open(stamp_path, 'w', encoding='ascii').write(stamp + '\n')
    copy_frames(frames, frames_txt)
    return '%s%s%s（%s）' % (icon_msg, frame_msg, ui_msg, '图集沿用，界面素材重新生成' if atlas_ok else '已从原版重新生成' if not ui_ok else '界面素材沿用，图集重新生成')


def title_gfx(gfx, anim=None):
    """原版 05_001_title_logo.gfx → 封面用的：外部图片标签（1009）的名字和尺寸；精灵里放这张图的 PlaceObject3（70）矩阵的平移清零（到这里长度不变）。
    anim = (新定义, 新放置)：定义拼在那个精灵前面，放置拼进精灵（它的 ShowFrame 前面），改精灵和文件头的长度。
    原版不是预期的样子（游戏更新过）就报错，不猜"""
    if gfx[:3] == b'CFX':
        gfx = b'GFX' + gfx[3:8] + zlib.decompress(gfx[8:])
    old, new = TITLE_NAME
    if len(old) != len(new) or gfx.count(old) != 4:
        raise ValueError('原版 %s 里 Logo 贴图的引用对不上（游戏更新过？）' % TITLE_GFX)
    b = bytearray(gfx.replace(old, new))

    def bits(pos, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((b[pos >> 3] >> (7 - (pos & 7))) & 1)
            pos += 1
        return v, pos

    def sbits(pos, n):
        v, pos = bits(pos, n)
        return (v - (1 << n) if n and v & (1 << (n - 1)) else v), pos

    n = b[8] >> 3                                   # 舞台矩形（5 位位数 + 4 个值）
    start = 8 + ((5 + 4 * n + 7) >> 3) + 4          # 后面帧率、帧数
    found = {'cid': None, 'img': 0, 'place': 0, 'sprite': None}

    def walk(pos, end, parent=None):
        while pos < end:
            h = struct.unpack_from('<H', b, pos)[0]
            code, ln = h >> 6, h & 0x3f
            tag_at = pos
            pos += 2
            if ln == 0x3f:
                ln = struct.unpack_from('<I', b, pos)[0]
                pos += 4
            if code == 1009 and bytes(b[pos + 11:pos + 11 + b[pos + 10]]) == new:
                cid, _fmt, w, h_ = struct.unpack_from('<IHHH', b, pos)
                if (w, h_) != TITLE_OLD_SIZE:
                    raise ValueError('原版 Logo 图的尺寸是 %d×%d（游戏更新过？）' % (w, h_))
                struct.pack_into('<HH', b, pos + 6, *TITLE_SIZE)
                found['cid'] = cid
                found['img'] += 1
            elif code == 39:
                walk(pos + 4, pos + ln, (tag_at, pos, ln))
            elif code == 70 and found['cid'] is not None and b[pos] & 0x06 == 0x06 and not b[pos + 1] & 0x08 \
                    and struct.unpack_from('<H', b, pos + 4)[0] == found['cid']:
                q = (pos + 6) * 8                   # 矩阵：有缩放 1 位、位数 5 位、两个缩放；有旋转 1 位（这张图没有）；平移位数 5 位、x、y
                has, q = bits(q, 1)
                if has:
                    k, q = bits(q, 5)
                    q += 2 * k
                rot, q = bits(q, 1)
                if rot:
                    raise ValueError('原版 Logo 图带旋转（游戏更新过？）')
                k, q = bits(q, 5)
                tx, q1 = sbits(q, k)
                ty, _ = sbits(q1, k)
                if (tx, ty) != TITLE_OLD_POS:
                    raise ValueError('原版 Logo 图的位置是 %d, %d（游戏更新过？）' % (tx, ty))
                for i in range(q, q + 2 * k):
                    b[i >> 3] &= ~(1 << (7 - (i & 7))) & 0xff
                found['place'] += 1
                found['sprite'] = parent
            pos += ln
            if code == 0:
                break

    walk(start, len(b))
    if found['img'] != 1 or found['place'] != 1:
        raise ValueError('原版 %s 里没找到 Logo 图的标签 / 放置（%r）' % (TITLE_GFX, found))
    if anim is None:
        return bytes(b)
    defs, places = anim
    tag_at, body, ln = found['sprite']
    if body - tag_at != 6 or bytes(b[body + ln - 4:body + ln]) != b'\x40\x00\x00\x00':       # 长标签头；ShowFrame + End
        raise ValueError('原版 %s 的 Logo 精灵不是预期的样子' % TITLE_GFX)
    out = bytearray(b[:tag_at]) + defs + struct.pack('<HI', (39 << 6) | 0x3f, ln + len(places)) + b[body:body + ln - 4] + places + b[body + ln - 4:]
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out)


def title_menu_gfx(gfx):
    """原版 05_000_title.gfx → 封面用的（长度不变）：标题菜单的 BottomShade（形状 500×46，线性渐变 透明 → 黑）不透明那端也改成透明。
    只动这一个字节，这一层和它的实例名都还在，AS 碰它不出错。原版不是预期的样子（游戏更新过）就报错，不猜"""
    if gfx[:3] == b'CFX':
        gfx = b'GFX' + gfx[3:8] + zlib.decompress(gfx[8:])
    rect = bytes.fromhex('758f09c478d00000')                    # 边界 (-250, -46, 250, 0)
    grad = bytes.fromhex('02' '00' '00000000' 'ff' '000000ff')  # 两个渐变点：透明的黑 → 不透明的黑
    at = gfx.find(rect)
    g = gfx.find(grad, at, at + 48) if at >= 0 else -1
    if at < 0 or gfx.count(rect) != 1 or g < 0:
        raise ValueError('原版 %s 里没找到菜单底下的渐变（游戏更新过？）' % TITLE_MENU_GFX)
    b = bytearray(gfx)
    b[g + len(grad) - 1] = 0
    return bytes(b)


def build_title(out, game):
    """标题封面的小包（见文件头）。返回 ({封面: 包目录}, 说明)；没有封面数据返回 ({}, '')"""
    covers = {c: os.path.join(DATA, 'dr_title_%s.dds' % c) for c in TITLE_COVERS}
    if not all(os.path.isfile(p) for p in covers.values()):
        return {}, ''
    root = os.path.join(os.path.dirname(os.path.abspath(out)), 'title')
    packs = {c: os.path.join(root, c) for c in TITLE_COVERS}
    bhd = os.path.join(game, 'Data0.bhd')
    layers = sorted(os.path.join(DATA, f) for f in os.listdir(DATA) if f.startswith('dr_title_'))     # 静态图 + 动画的贴图和 anim.bin
    # 两张封面各算各的（贴图按文件名前缀分）：改一张不重做另一张
    code = code_fp(['build_title'])
    stamps = {c: hashlib.sha1(repr(([(s.st_size, s.st_mtime_ns) for s in [os.stat(p) for p in [bhd, bhd[:-4] + '.bdt']
                                     + [x for x in layers if os.path.basename(x).startswith('dr_title_%s' % c)]]], TITLE_NAME, TITLE_SIZE, code)).encode('ascii')).hexdigest()
              for c in TITLE_COVERS}
    stamp_of = lambda c: os.path.join(root, c + '.stamp.txt')

    def ready(c):
        files = [os.path.join(packs[c], 'menu', os.path.basename(g)) for g in (TITLE_GFX, TITLE_MENU_GFX)] + \
            [os.path.join(packs[c], 'menu', q, os.path.basename(TITLE_TPF % q)) for q in QUALITIES]
        return all(os.path.isfile(p) for p in files) and os.path.isfile(stamp_of(c)) and open(stamp_of(c), encoding='ascii').read().strip() == stamps[c]
    todo = [c for c in TITLE_COVERS if not ready(c)]
    if not todo:
        return packs, '标题封面（没变，沿用上次的）'
    arc = erlib.GameArchive(bhd, open(os.path.join(DATA, 'data0_key.pem'), encoding='ascii').read())
    logo, menu_gfx = arc.read(TITLE_GFX), title_menu_gfx(arc.read(TITLE_MENU_GFX))
    name = TITLE_NAME[1].decode('ascii')
    vanilla = {q: arc.read(TITLE_TPF % q) for q in QUALITIES}
    for c in todo:
        if os.path.exists(stamp_of(c)):
            os.remove(stamp_of(c))              # 写到一半失败的话下次重做
        main_dds, extra, gfx = covers[c], [], None
        anim_path = os.path.join(DATA, 'dr_title_%s_anim.bin' % c)
        if os.path.isfile(anim_path):
            a = open(anim_path, 'rb').read()
            nd, np_ = struct.unpack_from('<II', a)
            gfx = title_gfx(logo, (a[8:8 + nd], a[8 + nd:8 + nd + np_]))
            main_dds = os.path.join(DATA, 'dr_title_%s_base.dds' % c)
            pre = 'dr_title_%s_' % c
            for p in layers:
                f = os.path.basename(p)
                if f.startswith(pre) and f.endswith('.dds') and f != pre + 'base.dds':
                    extra.append(('MENU_Title_DF_' + f[len(pre):-4], open(p, 'rb').read()))
        else:
            gfx = title_gfx(logo)
        dds = open(main_dds, 'rb').read()
        if dds_size(dds) != TITLE_SIZE:
            raise ValueError('封面 %s 不是 %d×%d' % ((main_dds,) + TITLE_SIZE))
        d = os.path.join(packs[c], 'menu')
        os.makedirs(d, exist_ok=True)
        for src, data in ((TITLE_GFX, gfx), (TITLE_MENU_GFX, menu_gfx)):
            tmp = os.path.join(d, os.path.basename(src)) + '.tmp'
            open(tmp, 'wb').write(data)
            os.replace(tmp, tmp[:-4])
        for q in QUALITIES:
            tpf = erlib.read_tpf(erlib.dcx_decompress(vanilla[q]))
            if any(x['name'] == name for x in tpf['tex']):
                raise ValueError('原版 02_title 已经有贴图 %s' % name)
            # 格式 102 = BC7（同原版 01_common 里的 BC7 贴图）；贴图按名字排（原版就是）
            for n_, d_ in [(name, dds)] + extra:
                tpf['tex'].append(dict(name=n_, fmt=102, type=0, mips=1, flags1=0, flags2=0, data=d_))
            tpf['tex'].sort(key=lambda x: x['name'])
            os.makedirs(os.path.join(d, q), exist_ok=True)
            path = os.path.join(d, q, os.path.basename(TITLE_TPF % q))
            tmp = path + '.tmp'
            open(tmp, 'wb').write(erlib.dcx_compress_dflt(erlib.write_tpf(tpf)))
            os.replace(tmp, path)
        open(stamp_of(c), 'w', encoding='ascii').write(stamps[c] + '\n')
    return packs, '标题封面（%s重新生成）' % ('、'.join(todo) if len(todo) < len(TITLE_COVERS) else '都')


def write_talk_gfx(arc, path, on):
    """赐福 / NPC 对话菜单换金色选中框（赐福图集在才做；不在就删掉以前写的，免得引用不存在的图）"""
    if not on:
        if os.path.exists(path):
            os.remove(path)
        return
    raw = arc.read(TALK_GFX)
    if raw[:3] == b'CFX':                       # 压缩的：解开存（游戏两种都认）
        raw = b'GFX' + raw[3:8] + zlib.decompress(raw[8:])
    old, new = TALK_CURSOR
    if len(old) != len(new) or raw.count(old) != 4:    # 外部图片标签的名字、文件名，AS3 的类名、符号表：同样长，一起换
        raise ValueError('原版 %s 里选中框的引用对不上（游戏更新过？）' % TALK_GFX)
    tmp = path + '.tmp'
    open(tmp, 'wb').write(raw.replace(old, new))
    os.replace(tmp, path)


def copy_frames(frames, frames_txt):
    """菜单包里有带框图标了：对照表给 DLL"""
    if frames and os.path.isdir(os.path.dirname(frames_txt)):
        tmp = frames_txt + '.tmp'
        open(tmp, 'wb').write(open(frames[1], 'rb').read())
        os.replace(tmp, frames_txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--game', required=True, help='游戏的 Game 目录（有 Data0.bhd / .bdt）')
    ap.add_argument('--dll-dir', action='append', default=[])
    ap.add_argument('--core-dir', default=CORE_DIR, help='dll\\dark_core（写 frames.txt）')
    a = ap.parse_args()
    erlib.DLL_DIRS = [d for d in a.dll_dir if d]
    # 标题封面单独做：失败了菜单包照常（标题还是原版）
    try:
        title, title_msg = build_title(a.out, a.game)
    except Exception as e:
        title, title_msg = {}, '标题封面没做成（%s: %s），标题还是原版' % (type(e).__name__, e)
    try:
        msg = build(a.out, a.game, a.core_dir)
        print(json.dumps({'ok': True, 'msg': msg + ('、' + title_msg if title_msg else ''), 'title': title}, ensure_ascii=False), flush=True)
    except Exception as e:
        print(json.dumps({'ok': False, 'msg': '%s: %s' % (type(e).__name__, e)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
