# -*- coding: utf-8 -*-
"""赐福主菜单「卢恩银行」（在「升级」后面）（用户 2026-11-10「赐福菜单里加一个卢恩银行 可以存取身上的卢恩 然后要显示银行当前卢恩 同时注意存档问题」）：
  - 余额存在存档里：事件标记 BANK0 起 BANK_BITS 位拼成的数（92600~92631，92000 块会存档，同咒痕碎片 92582 起）。
    和身上的卢恩在同一份存档里，回档 / 崩溃 / 换角色都跟着存档走，不会对不上、不会复制；dark_core 只在一帧里同时改两边。
  - 0 列表：第 1 项是余额行（占位 #IB 由 dark_core gear.rs 改写成「银行 X / 身上 Y」，选了只是刷新列表），后面是存取的几种（OPS）、返回；
  - 100 + k：操作序号写进 OP0 起的几个标记，熄灭上次残留的「没有可存取 / 满了」，点亮请求 REQ → 请求熄了：
    200 + k 看 NONE（810）/ FULL（815），都没亮就 400 + k 提示做完了；超时还没熄 = dark_core 没加载（830）。做完都回列表。
  - 处理在 dark_core runebank.rs（编号写在那边的常量里，两边要一起改）。dev\\event_flags\\说明.md 有登记。"""
from .esdutil import ALWAYS, DIALOG_WAIT, MENU_WAIT, STATE_TIME_OVER_1, flag_is_off, flag_is_on, hook_main_after, i32, menu_parts, menu_pick

# 赐福主菜单里的选项编号、文字（放在「升级」后面，用户 2026-11-10）。编号以前是 41，和原版「开始第 N 次的世界」撞了：
# 原版那一项是主菜单调用的子状态机加的、跳转在前面，通关后点卢恩银行会进下一周目（用户 2026-11-13）；
# 现在 esdutil.check_free 连子状态机加的、跳转里比较的都算上，撞了重随时直接报错
OPTION, TEXT = 61, 80099500
LEVEL_UP = 15000540                      # 原版「升级」
BAL_TEXT, OP_TEXT, DONE_TEXT = 80099510, 80099520, 80099530     # 余额行；+k：操作、做完了
NONE_TEXT, FULL_TEXT, MISSING_TEXT = 80099540, 80099541, 80099542
BANK0, BANK_BITS = 92600, 32
REQ, OP0, OP_BITS, NONE, FULL = 92632, 92633, 3, 92636, 92637
# 操作：序号 = OP 标记的值（dark_core runebank.rs 的 Op 同序）
OPS = (('存入全部卢恩', 'Deposit all runes', '身上的卢恩都存进了银行'),
       ('存入一半卢恩', 'Deposit half of your runes', '身上一半的卢恩存进了银行'),
       ('取出全部卢恩', 'Withdraw all runes', '银行里的卢恩都取了出来'),
       ('取出一半卢恩', 'Withdraw half of the savings', '银行里一半的卢恩取了出来'),
       ('取出 10,000 卢恩', 'Withdraw 10,000 runes', '取出了 10,000 卢恩'),
       ('取出 100,000 卢恩', 'Withdraw 100,000 runes', '取出了 100,000 卢恩'))
OPS_EN_DONE = ('All your runes were deposited.', 'Half of your runes were deposited.', 'All savings were withdrawn.',
               'Half of the savings were withdrawn.', 'Withdrew 10,000 runes.', 'Withdrew 100,000 runes.')
KIND = 'B'                               # 占位种类字（gear.rs：0~9、A、B；B = 11 卢恩银行）
FIELD_LEN = {'zh': 40, 'en': 52}         # 含两端括号的字符数（「银行 4,000,000,000 / 身上 999,999,999」要 35 个字）


def field(lang):
    if lang == 'zh':
        body = '#I%s 正在清点卢恩……' % KIND
        return '〔' + body + ' ' * (FIELD_LEN['zh'] - 2 - len(body)) + '〕'
    body = '#I%s counting runes...' % KIND
    return '[' + body + ' ' * (FIELD_LEN['en'] - 2 - len(body)) + ']'


def esd(cx, groups):
    p = menu_parts(groups, cx.root)
    add_cmd, gid = p['add_cmd'], p['gid']
    setf = lambda fl, v: {'bank': 1, 'id': 11, 'args': [i32(fl), i32(v)]}
    say = lambda text: {'bank': 1, 'id': 17, 'args': [i32(7), i32(text), i32(1), i32(0), i32(1)]}
    add = lambda k, text: dict(add_cmd, args=[i32(k), i32(text), i32(-1)])
    to = lambda target, ev: {'target': target, 'eval': ev, 'pass': [], 'sub': []}
    state = lambda entry, conds: {'entry': entry, 'exit': [], 'while': [], 'conds': conds}
    bits = lambda v: [setf(OP0 + i, (v >> i) & 1) for i in range(OP_BITS)]
    n = len(OPS)
    st = {
        0: state([{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}, add(1, BAL_TEXT)]
                 + [add(2 + k, OP_TEXT + k) for k in range(n)] + [add(99, 26000004), {'bank': 1, 'id': 10, 'args': [i32(1)]}],
                 [to(1, MENU_WAIT)]),
        1: state([], [to(0, menu_pick(1))] + [to(100 + k, menu_pick(2 + k)) for k in range(n)] + [to(9, ALWAYS)]),
        810: state([setf(NONE, 0), say(NONE_TEXT)], [to(0, DIALOG_WAIT)]),
        815: state([setf(FULL, 0), say(FULL_TEXT)], [to(0, DIALOG_WAIT)]),
        830: state([setf(REQ, 0), say(MISSING_TEXT)], [to(0, DIALOG_WAIT)]),
        9: state([], [p['ret']]),
    }
    for k in range(n):
        st[100 + k] = state(bits(k) + [setf(NONE, 0), setf(FULL, 0), setf(REQ, 1)], [to(200 + k, flag_is_off(REQ)), to(830, STATE_TIME_OVER_1)])
        st[200 + k] = state([], [to(810, flag_is_on(NONE)), to(815, flag_is_on(FULL)), to(400 + k, ALWAYS)])
        st[400 + k] = state([say(DONE_TEXT + k)], [to(0, DIALOG_WAIT)])
    groups[gid] = st
    hook_main_after(groups, OPTION, TEXT, gid, LEVEL_UP)


def texts(cx, key):
    zh = key == 'zh'
    out = {TEXT: '卢恩银行' if zh else 'Rune Bank', BAL_TEXT: field('zh' if zh else 'en')}
    for k, (a, b, c) in enumerate(OPS):
        out[OP_TEXT + k] = a if zh else b
        out[DONE_TEXT + k] = c if zh else OPS_EN_DONE[k]
    if zh:
        out.update({NONE_TEXT: '没有可以存取的卢恩', FULL_TEXT: '放不下了：身上最多带 999,999,999 卢恩，银行最多存 4,000,000,000 卢恩',
                    MISSING_TEXT: '现在无法存取：暗黑重铸的组件没有加载，请用启动器重新启动游戏。'})
    else:
        out.update({NONE_TEXT: 'There are no runes to move.',
                    FULL_TEXT: 'No room: you can carry up to 999,999,999 runes, and the bank holds up to 4,000,000,000.',
                    MISSING_TEXT: "Can't use the bank right now: a Darkforge component didn't load. Please restart the game from the launcher."})
    return {'EventTextForTalk': out}
