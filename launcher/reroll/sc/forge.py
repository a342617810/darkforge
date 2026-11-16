# -*- coding: utf-8 -*-
"""赐福最上面的「暗黑重铸」（Dark Reforged）入口（用户 2026-10-31）：我们的功能不再各自挂在赐福主菜单 / 「更多选项」里，
都收进这个子菜单——一键鉴定、装备工坊、向星辰许愿、暗黑商店、一键出售、武器回收、Dark Reforged 说明（ORDER，用户选的「按流程」顺序；
武器回收原来在暗黑商店子菜单里，用户 2026-10-31 挪过来；
难度调整原来在「更多选项」里，用户 2026-11-03 挪过来，放在说明前面；魇印、七咒 2026-11-03 从装备工坊里拆出来，放在难度调整后面，
只在高难度档列出来——登记时带了条件的项用 AddTalkListDataIf）。
各功能照旧建自己的状态机，只是用 esdutil.register 登记（cx.forge）；这里最后建子菜单，在赐福主菜单最上面（清空列表之后、
原版第一项之前）加入口。子菜单里选完一项（关掉商店、工坊窗口、提示框……）回到子菜单，「返回」回赐福主菜单。
入口文字用金色（「更多选项」原来也是这个金色，2026-10-31 用户让它改回原版白字，data\\gracemenu\\text.json）。
要在所有登记的功能之后（scripts.py 的 FEATURES）。"""
from .esdutil import ALWAYS, MENU_WAIT, hook_main_top, i32, menu_parts, menu_pick

OPTION, TEXT = 39, 80093000        # 赐福主菜单里的选项编号（原版和别的功能都没用）、文字
ORDER = ('identify', 'inherit', 'wish', 'darkshop', 'sell', 'recycle', 'difficulty', 'seal', 'curse', 'wishstone', 'guide')
GOLD = '<font color="#c7ae54">%s</font>'


def esd(cx, groups):
    items = sorted(getattr(cx, 'forge', []), key=lambda x: ORDER.index(x[0]) if x[0] in ORDER else len(ORDER))
    cx.forge_n = len(items)
    if not items:
        return
    p = menu_parts(groups, cx.root)
    add_cmd, gid = p['add_cmd'], p['gid']
    cx.forge_gid = gid                  # sc/gracelook.py 给这个子菜单加图标
    # 先挂入口（拿到主菜单调用子功能的写法：先关菜单再调），子菜单里调各功能照抄它，调完回到列表
    groups[gid] = {}
    tmpl = hook_main_top(groups, OPTION, TEXT, gid)
    clear = [{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}]
    conds = getattr(cx, 'forge_cond', {})

    def add(j, k, t):
        if k in conds:          # AddTalkListDataIf（同暗黑商店子菜单的上架条件）
            return {'bank': 5, 'id': 19, 'args': [conds[k], i32(j + 1), i32(t), i32(-1)]}
        return dict(add_cmd, args=[i32(j + 1), i32(t), i32(-1)])
    st = {0: {'entry': clear + [add(j, k, t) for j, (k, t, _g) in enumerate(items)]
              + [dict(add_cmd, args=[i32(99), i32(26000004), i32(-1)]), {'bank': 1, 'id': 10, 'args': [i32(1)]}],
              'conds': [{'target': 1, 'eval': MENU_WAIT, 'pass': [], 'sub': []}], 'exit': [], 'while': []},
          1: {'entry': [], 'exit': [], 'while': [],
              'conds': [{'target': 10 + j, 'eval': menu_pick(j + 1), 'pass': [], 'sub': []} for j in range(len(items))]
              + [{'target': 9, 'eval': ALWAYS, 'pass': [], 'sub': []}]},
          9: {'entry': [], 'exit': [], 'while': [], 'conds': [p['ret']]}}
    # 调完回到列表：条件照抄主菜单调「更多选项」那一步的「等调用的状态机返回」（b9ba96a1）。
    # 不能写恒真：恒真的话一进调用状态马上跳回列表，被调的功能一闪就没了（2026-10-31 游戏里子菜单的功能全都打不开）
    done = tmpl['conds'][0]['eval']
    if done == ALWAYS:
        raise RuntimeError('赐福主菜单「更多选项」那一步的返回条件是恒真，抄不了')
    for j, (_k, _t, g) in enumerate(items):
        st[10 + j] = {'entry': [{'bank': 6, 'id': g, 'args': []} if c['bank'] == 6 else c for c in tmpl['entry']], 'exit': [], 'while': [],
                      'conds': [{'target': 0, 'eval': done, 'pass': [], 'sub': []}]}
    groups[gid] = st


def texts(cx, key):
    if not getattr(cx, 'forge_n', 0):
        return {}
    return {'EventTextForTalk': {TEXT: GOLD % ('暗黑重铸' if key == 'zh' else 'Darkforge')}}
