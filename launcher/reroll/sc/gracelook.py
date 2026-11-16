# -*- coding: utf-8 -*-
"""赐福菜单美化（用户 2026-11-03 选的第二版，参考 Golden Age 的做法）：选项文字前面嵌原版风格的菜单标题图标，再给档位上色。
  - 赐福主菜单、「更多选项」、「暗黑重铸」子菜单每一项都带图标（菜单文字里 <img src='img://名字.png'/> 引用已加载的精灵）。
    图标都在我们自己的图集 SB_DR_Grace（dev\\item_system\\make_icons.py 画，启动时 launcher\\reroll\\menu.py 加进 01_common）：
    原版 MENU_FL_x 复制成 76×76 方图 MENU_DR_FL_x——直接引用原版的，游戏里下边框被截掉、文字往下偏（2026-11-03 用户截图），
    我们自己的方图完整、文字居中；原版没有的：暗黑重铸 MENU_DR_Grace_Forge、离去 Grace_Leave、空白占位 Grace_Blank（「返回」用，文字对齐）。
    图集里没有的名字（没重新生成）照旧引用原版的。
  - 选中框改成金色：menu.py 改对话选项菜单（03_063_talkchoice.gfx）引用的贴图，这里不用管。
  - 「暗黑重铸」入口金色；一键出售 / 武器回收的档位按稀有度上色（和装备名字同色）；难度各档按难易上色，
    当前那一档仍是前面的「装备中」标记（sc/difficulty.py 的 CUR_TEXT，换成图集里的方图 MENU_DR_EquMark）。
原版文字（消磨时间、离去、返回……）别的 NPC 对话也在用，不能直接改：赐福脚本里这几个菜单的加选项命令换成我们的编号
（REMAP，固定编号），新编号的文字 = 图标 + 原文（加载的包改过就用改过的）。我们自己的文字（8000xxxx 以后）直接改。
有几项不是菜单状态机自己加的（2026-11-03 查过，扫描 scratchpad bxtest\\gl_helpers.py）：
  - 圣杯瓶、幽影之地的庇佑：主菜单调小状态机（6:2147483576 / 6:2147483567，参数 = 选项、文字……）替它加，换调用的参数；
  - 改变灵马的外表（主菜单）、从追忆获得力量 / 获得英雄的防具（更多选项）：建列表时调的小状态机里直接加，按文字（HELPER_TEXTS）换；
  - 没加图标（用户 2026-11-03 不要）：开始第 N 次的世界、倾听火焰熏烧的声音（6:2147483595 里加的）。
要在 FEATURES 最后（菜单都建好、文字都给完之后）：esd 换编号，restyle（scripts.py 在各功能的 texts 合好之后调）改文字。"""
import os
import re

from . import darkshop, difficulty, forge, runebank, sell, twin
from .esdutil import MENU_GROUP, esd_int, i32, option_of, text_of

ICON = "<img src='img://%s.png' height='36' width='36' vspace='-18'/> "
FMG = 'EventTextForTalk'
LAYOUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'menu', 'dr_grace.layout')

# 原版文字编号 → (我们的编号, 图标)。编号固定，别挪（存档不记这些，但改了要和 ESD 一起改）
REMAP = {
    15000420: (80094000, 'MENU_FL_BonFire'),            # 消磨时间
    15000540: (80094001, 'MENU_FL_Status'),             # 升级
    15000390: (80094002, 'MENU_FL_Magic'),              # 记忆
    15000510: (80094003, 'MENU_FL_Elixir'),             # 调配灵药
    15000395: (80094004, 'MENU_FL_Repository'),         # 整理木箱
    15000520: (80094005, 'MENU_FL_40152_BigRunes'),     # 大卢恩
    15000530: (80094006, 'MENU_FL_40168_Arts'),         # 战灰
    22230000: (80094007, 'MENU_FL_40165_Dresser'),      # 修改服装
    14000000: (80094008, 'MENU_FL_Sysytem'),            # 更多选项（文字是 VINS 的，data\\gracemenu\\text.json）
    20000009: (80094009, 'MENU_DR_Grace_Leave'),        # 离去
    26000004: (80094010, 'MENU_DR_Grace_Blank'),        # 返回
    26010000: (80094011, 'MENU_FL_Dragon'),             # 龙飨仪式
    22000000: (80094012, 'MENU_FL_40164_Renara'),       # 重新诞生
    22000001: (80094013, 'MENU_FL_CharaMake'),          # 化妆
    22130001: (80094014, 'MENU_FL_WeaponEnhance'),      # 强化武器
    23200000: (80094015, 'MENU_FL_40155_Buddy'),        # 调灵
    22130018: (80094016, 'MENU_FL_40154_MagicStoneCopy'),   # 复制战灰
    15000371: (80094017, 'MENU_FL_40169_Sleep'),        # 圣杯瓶（调小状态机加的，见上）
    20010001: (80094018, 'MENU_DR_Grace_Shadow'),       # 幽影之地的庇佑（同上，6:2147483567 的参数）
    20010070: (80094019, 'MENU_DR_Grace_Steed'),        # 改变灵马的外表（小状态机里直接加的，HELPER_TEXTS）
    21020000: (80094020, 'MENU_FL_40163_BossSoulCopy'),   # 从追忆获得力量（同上）
    21020005: (80094021, 'MENU_FL_Armor_40171'),        # 获得英雄的防具（同上）
}
# 不换编号、图标直接写进原版文字的（只有赐福菜单用，NPC 对话里不会冒出图标）：整理木箱 15000395 是幻化插件（ertransmogrify，
# patch_grace_talk_script）找插入位置的锚点，换了编号它就不插「幻化」（用户 2026-11-07「菜单里装备幻化怎么没了」）
IN_PLACE = {15000395}
# 插件自己那一项「幻化防具」（文字是插件挂钩返回的，不在文本表里）的图标在 dark_core transmogicon.rs 里加，用图集的
# MENU_DR_FL_Armor_40171（改名 / 删图标要一起改那边的 PREFIX）
# 这几个菜单建列表时调的小状态机里直接加的项（文字只有它们用；小状态机里的「返回」之类不动）
HELPER_TEXTS = {20010070, 21020000, 21020005}
# 我们自己的文字 → (图标, 颜色)
OURS = {
    forge.TEXT: ('MENU_DR_Grace_Forge', '#E2BE6A'),     # 暗黑重铸
    twin.TEXT: ('MENU_FL_Talk', None),                  # 双子老妪
    runebank.TEXT: ('MENU_FL_BuySell', None),           # 卢恩银行（赐福主菜单，「升级」后面）
    80000000: ('MENU_FL_40191_Coliseum', None),         # 头目复活（VINS 的文字；石棺图标原版是「从追忆获得力量」的）
}
# 「暗黑重铸」子菜单（esdutil.register 登记的功能名 → 图标；没列的用空白占位）
FORGE_ICONS = {
    'identify': 'MENU_FL_40187_FingerReader',           # 鉴定（一键鉴定、定向鉴定）
    'inherit': 'MENU_FL_40153_SoulForging',             # 装备工坊
    'wish': 'MENU_FL_LevelUp',                          # 向星辰许愿
    'darkshop': 'MENU_FL_BuySell',                      # 暗黑商店
    'sell': 'MENU_FL_Inventory',                        # 一键出售
    'recycle': 'MENU_FL_40160_StoneChange',             # 武器回收
    'difficulty': 'MENU_FL_40192_Veil',                 # 难度调整
    'seal': 'MENU_DR_Grace_Seal',                       # 魇印（只在高难度档列出来）
    'curse': 'MENU_DR_Grace_Curse',                     # 七咒（同上）
    'wishstone': 'MENU_FL_Status',                      # 许愿石升级（同上；图标同原版「升级」）
    'guide': 'MENU_FL_40167_Creed',                     # Dark Reforged 说明
}
RARITY = ('#DADADA', '#A0B4F3', '#BB2DC2', '#D4A900')  # 普通 / 稀有 / 史诗 / 传说（装备名字的颜色）
EASIER = ('#BFD98A', '#8FD18A')                         # 比「普通」低一档、两档……
HARDER = ('#E8C86A', '#E39B4A', '#D9603F', '#C0392B', '#9B2242')
IMG = re.compile(r"^((?:\s*<img [^>]*/>)*\s*)")
_HAVE = []


def ours(name):
    """图集里有方图副本（MENU_FL_x → MENU_DR_FL_x）就用副本，没有照旧用原版的"""
    if not _HAVE:
        _HAVE.append(set(re.findall(r'name="([^"]+)\.png"', open(LAYOUT, encoding='utf-8').read())) if os.path.isfile(LAYOUT) else set())
    if name.startswith('MENU_DR_'):
        return name
    copy = 'MENU_DR_' + name[len('MENU_'):]
    return copy if copy in _HAVE[0] else name


def esd(cx, groups):
    """赐福主菜单、「更多选项」、「暗黑重铸」子菜单里加选项的命令：原版文字编号换成 REMAP 里我们的编号"""
    cx.gl_used = set()
    menus = [g for g in (MENU_GROUP, cx.root, getattr(cx, 'forge_gid', None)) if g in groups]
    called = {c['id'] & 0xFFFFFFFF for g in menus for s in groups[g].values() for c in s['entry'] if c['bank'] == 6}
    for gid in menus + sorted(called - set(menus)):
        for s in groups.get(gid, {}).values():
            for part in ('entry', 'exit', 'while'):
                s[part] = [remap(cx, c, gid in menus) for c in s[part]]


def remap(cx, c, menu):
    if option_of(c) is not None:
        k, t = (1 if c['bank'] == 1 else 2), text_of(c)
    elif menu and c['bank'] == 6 and len(c['args']) >= 2 and esd_int(c['args'][0]) is not None:   # 调小状态机替它加选项（参数 = 选项、文字……）
        k, t = 1, esd_int(c['args'][1])
    else:
        return c
    if t not in REMAP or not (menu or t in HELPER_TEXTS):
        return c
    cx.gl_used.add(t)
    if t in IN_PLACE:
        return c
    return dict(c, args=c['args'][:k] + [i32(REMAP[t][0])] + c['args'][k + 1:])     # 新的命令：原来的可能别处也引用着


def paint(text, color):
    """去掉原来的颜色；给了颜色就把文字（前面的图标不算）包上"""
    text = re.sub(r'</?font[^>]*>', '', text)
    if not color:
        return text
    head = IMG.match(text).group(1)
    return '%s<font color="%s">%s</font>' % (head, color, text[len(head):])


def restyle(cx, key, add, base):
    """add：各功能给的文字（{FMG: {编号: 文字}}，改这里）；base(编号)：加载的包 / 原版里的文字"""
    rows = add.setdefault(FMG, {})
    get = lambda t: rows.get(t) if t in rows else base(t)
    for t in sorted(getattr(cx, 'gl_used', ())):
        nid, icon = REMAP[t]
        if get(t) is not None:
            rows[t if t in IN_PLACE else nid] = ICON % ours(icon) + get(t)
    mine = {**OURS, **{t: (FORGE_ICONS.get(k, 'MENU_DR_Grace_Blank'), None) for k, t, _g in getattr(cx, 'forge', [])}}
    for t, (icon, color) in mine.items():
        if get(t) is not None:
            rows[t] = ICON % ours(icon) + paint(get(t), color)
    tiers = [(sell.TIER_TEXT + k, c) for k, c in enumerate(RARITY)] + [(darkshop.R_TIER_TEXT + k, c) for k, c in enumerate(RARITY)]
    ts = difficulty.tiers(cx)
    nm = difficulty.normal(ts)
    for k in range(len(ts)):
        c = EASIER[min(nm - k, len(EASIER)) - 1] if k < nm else HARDER[min(k - nm, len(HARDER)) - 1] if k > nm else None
        tiers += [(difficulty.TIER_TEXT + k, c), (difficulty.CUR_TEXT + k, c)]
        t = difficulty.CUR_TEXT + k
        if t in rows:
            rows[t] = rows[t].replace("img://MENU_EquMark.png", "img://%s.png" % ours('MENU_EquMark'))
    for t, c in tiers:
        if t in rows and c:
            rows[t] = paint(rows[t], c)
