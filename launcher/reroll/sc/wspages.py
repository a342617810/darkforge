# -*- coding: utf-8 -*-
"""赐福「暗黑重铸」里的「魇印」「咒痕」（原名七咒；用户 2026-11-03：不放进装备工坊，各自一项；只在切到「死亡」「不可能」之后列出来）。
界面同装备工坊（dll\\dark_ui 的悬浮窗口，只画这一页），这里只负责打开、等它关掉，写法同 sc/inherit.py：
  0 熄灭上次残留的应答 / 没界面标记，点亮这一项自己的打开请求 open（features 的 nightmare / curses 的 open；dark_core 看亮的是哪个，
    告诉界面开哪一页）；应答 ack、没界面 noui 和装备工坊共用（features 的 inherit）：ack → 10；noui → 20 提示；1 秒都没有 = dark_core 没加载 → 30 提示；
  10 窗口开着，等 dark_core 熄灭 open（窗口关了）→ 回子菜单。
列不列出来：AddTalkListDataIf（esdutil.register 的 cond），标了 lock 的难度档（features 的 tiers）当前档标记亮任意一个。
要有装备工坊（界面、应答标记都是它的），在 sc/forge.py 之前（scripts.py 的 FEATURES）。"""
from .esdutil import DIALOG_WAIT, STATE_TIME_OVER_1, any_flag_on, flag_is_off, flag_is_on, i32, menu_parts, register

# (登记名, features 里的功能, 菜单文字编号, 中文, 英文)
PAGES = (('seal', 'nightmare', 80092010, '魇印', 'Seals'),
         ('curse', 'curses', 80092011, '咒痕', 'Cursemarks'))
NO_CORE, NO_UI = 80092012, 80092013          # 两项共用的提示：没加载 dark_core / dark_ui


def on(cx):
    """[(登记名, 打开请求, 难度档标记, 文字编号, 中文, 英文)]：开了的那几项"""
    if not cx.feat.get('inherit'):
        return []
    out = []
    for key, feat, text, zh, en in PAGES:
        f = cx.feat.get(feat) or {}
        if f.get('open') and f.get('tiers'):
            out.append((key, int(f['open']), [int(x) for x in f['tiers']], text, zh, en))
    return out


def esd(cx, groups):
    pages = on(cx)
    if not pages:
        return
    ih = cx.feat['inherit']
    ack, noui = int(ih['ack']), int(ih['noui'])
    setf = lambda flag, v: {'bank': 1, 'id': 11, 'args': [i32(flag), i32(v)]}
    say = lambda text: {'bank': 1, 'id': 17, 'args': [i32(7), i32(text), i32(1), i32(0), i32(1)]}
    for key, op, tiers, text, _zh, _en in pages:
        p = menu_parts(groups, cx.root)
        groups[p['gid']] = {
            0: {'entry': [setf(ack, 0), setf(noui, 0), setf(op, 1)], 'exit': [], 'while': [],
                'conds': [{'target': 10, 'eval': flag_is_on(ack), 'pass': [], 'sub': []},
                          {'target': 20, 'eval': flag_is_on(noui), 'pass': [], 'sub': []},
                          {'target': 30, 'eval': STATE_TIME_OVER_1, 'pass': [], 'sub': []}]},
            10: {'entry': [], 'exit': [], 'while': [],
                 'conds': [{'target': 9, 'eval': flag_is_off(op), 'pass': [], 'sub': []}]},
            20: {'entry': [setf(op, 0), setf(noui, 0), say(NO_UI)], 'exit': [], 'while': [],
                 'conds': [{'target': 9, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}]},
            30: {'entry': [setf(op, 0), say(NO_CORE)], 'exit': [], 'while': [],
                 'conds': [{'target': 9, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}]},
            9: {'entry': [], 'exit': [], 'while': [], 'conds': [p['ret']]},
        }
        register(cx, key, text, p['gid'], cond=any_flag_on(tiers))     # 「暗黑重铸」子菜单里只在高难度档列出来


def texts(cx, key):
    pages = on(cx)
    if not pages:
        return {}
    zh = key == 'zh'
    rows = {text: (z if zh else e) for _k, _o, _t, text, z, e in pages}
    rows[NO_CORE] = ('现在无法打开这一页：暗黑重铸的组件没有加载，请用启动器重新启动游戏。' if zh
                     else "Can't open this page right now: a Darkforge component didn't load. Please restart the game from the launcher.")
    rows[NO_UI] = ('现在无法打开这一页：暗黑重铸的组件没有加载，请用启动器重新启动游戏。' if zh
                   else "Can't open this page right now: a Darkforge component didn't load. Please restart the game from the launcher.")
    return {'EventTextForTalk': rows}
