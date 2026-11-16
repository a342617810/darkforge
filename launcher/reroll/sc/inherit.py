# -*- coding: utf-8 -*-
"""赐福「装备工坊」（重随的 rr/inherit.py 开了才有，features.json 的 inherit；用户 2026-10-31）：
赐福「暗黑重铸」子菜单里的「装备工坊」（sc/forge.py；以前在赐福主菜单）。界面是 dll\\dark_ui 自己画的悬浮窗口，这里只负责打开、等它关掉：
  0 熄灭上次残留的应答 / 没界面标记，点亮打开请求 open；
    dark_core 点亮应答 ack → 10；点亮 noui（界面没加载）→ 20 提示；1 秒都没有 = dark_core 没加载 → 30 提示；
  10 窗口开着（人物照旧坐在赐福，游戏输入由 dark_ui 拦住），等 dark_core 熄灭 open（窗口关了）→ 回赐福菜单"""
from .esdutil import DIALOG_WAIT, STATE_TIME_OVER_1, flag_is_off, flag_is_on, register, i32, menu_parts, option_of

OPTION = 38


def on(cx):
    return bool(cx.feat.get('inherit'))


def esd(cx, groups):
    if not on(cx):
        return
    from .esdutil import MENU_GROUP
    if any(option_of(c) == OPTION for s in groups[MENU_GROUP].values() for c in s['entry']):
        raise RuntimeError('赐福菜单的选项编号 %d 已被占用（装备工坊）' % OPTION)
    f = cx.feat['inherit']
    t0, op, ack, noui = int(f['talk0']), int(f['open']), int(f['ack']), int(f['noui'])
    p = menu_parts(groups, cx.root)
    setf = lambda flag, v: {'bank': 1, 'id': 11, 'args': [i32(flag), i32(v)]}
    say = lambda text: {'bank': 1, 'id': 17, 'args': [i32(7), i32(text), i32(1), i32(0), i32(1)]}
    st = {
        0: {'entry': [setf(ack, 0), setf(noui, 0), setf(op, 1)], 'exit': [], 'while': [],
            'conds': [{'target': 10, 'eval': flag_is_on(ack), 'pass': [], 'sub': []},
                      {'target': 20, 'eval': flag_is_on(noui), 'pass': [], 'sub': []},
                      {'target': 30, 'eval': STATE_TIME_OVER_1, 'pass': [], 'sub': []}]},
        10: {'entry': [], 'exit': [], 'while': [],
             'conds': [{'target': 9, 'eval': flag_is_off(op), 'pass': [], 'sub': []}]},
        20: {'entry': [setf(op, 0), setf(noui, 0), say(t0 + 3)], 'exit': [], 'while': [],
             'conds': [{'target': 9, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}]},
        30: {'entry': [setf(op, 0), say(t0 + 1)], 'exit': [], 'while': [],
             'conds': [{'target': 9, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}]},
        9: {'entry': [], 'exit': [], 'while': [], 'conds': [p['ret']]},
    }
    groups[p['gid']] = st
    register(cx, 'inherit', t0, p['gid'])          # 收进赐福最上面的「暗黑重铸」（sc/forge.py）


def texts(cx, key):
    if not on(cx):
        return {}
    t0 = int(cx.feat['inherit']['talk0'])
    zh = key == 'zh'
    return {'EventTextForTalk': {
        t0: '装备工坊' if zh else 'Gear Workshop',
        t0 + 1: ('现在无法打开装备工坊：暗黑重铸的组件没有加载，请用启动器重新启动游戏。' if zh
                 else "Can't open the Gear Workshop right now: a Darkforge component didn't load. Please restart the game from the launcher."),
        t0 + 3: ('现在无法打开装备工坊：暗黑重铸的组件没有加载，请用启动器重新启动游戏。' if zh
                 else "Can't open the Gear Workshop right now: a Darkforge component didn't load. Please restart the game from the launcher.")}}
