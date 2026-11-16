# -*- coding: utf-8 -*-
"""赐福「向星辰许愿」（重随的 rr/wish.py 开了才有，features.json 的 wish）：
赐福「暗黑重铸」子菜单里的「向星辰许愿」（sc/forge.py；以前在赐福主菜单），子菜单「许愿 1 次」「许愿 10 次」；
各自先弹确认框，框里「这个地区每次多少卢恩、免费还剩几次」是固定长度的占位「〔#I1 …〕」/「〔#I2 …〕」（英文用 [ ]），
dll\\dark_core 按人物所在地区和免费次数改写（同一键鉴定的 #I0）。
选「是」点亮请求标记（flag1 / flag10），等 dark_core 熄灭（看到就熄，之后扣免费次数 / 卢恩、生成装备、走鉴定的发货表放进背包）再弹一句提示：
一次都付不起（没有免费次数、卢恩不够）dark_core 先点亮应答 poor，提示「星辰没有收到你的诚意」（用户 2026-10-31），不然「星辰回应了你的愿望」；
1 秒还没熄 = DLL 没加载：熄灭标记、弹「没有加载 dark_core」"""
from .esdutil import ALWAYS, DIALOG_WAIT, MENU_WAIT, STATE_TIME_OVER_1, flag_is_off, flag_is_on, register, i32, menu_parts, menu_pick, option_of

OPTION, TEXT, ONE_TEXT, TEN_TEXT, DESC1, DESC10, DONE_TEXT, MISSING_TEXT = 36, 80090170, 80090171, 80090172, 80090173, 80090174, 80090175, 80090176
POOR_TEXT = 80090177
FIELD_LEN = {'zh': 30, 'en': 44}                   # 含两端括号的字符数（同一键鉴定）


def on(cx):
    return bool(cx.feat.get('wish'))


def field(lang, kind):
    if lang == 'zh':
        body = '#I%d 正在询问价格……' % kind
        return '〔' + body + ' ' * (FIELD_LEN['zh'] - 2 - len(body)) + '〕'
    body = '#I%d checking the price...' % kind
    return '[' + body + ' ' * (FIELD_LEN['en'] - 2 - len(body)) + ']'


def esd(cx, groups):
    if not on(cx):
        return
    from .esdutil import MENU_GROUP
    if any(option_of(c) == OPTION for s in groups[MENU_GROUP].values() for c in s['entry']):
        raise RuntimeError('赐福菜单的选项编号 %d 已被占用（向星辰许愿）' % OPTION)
    w = cx.feat['wish']
    p = menu_parts(groups, cx.root)
    conf_call, yes_eval, no_eval, ret, gid, add_cmd = (p[k] for k in ('conf_call', 'yes_eval', 'no_eval', 'ret', 'gid', 'add_cmd'))
    st = {
        # 子菜单（写法同暗黑商店）
        0: {'entry': [{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []},
                      dict(add_cmd, args=[i32(1), i32(ONE_TEXT), i32(-1)]), dict(add_cmd, args=[i32(2), i32(TEN_TEXT), i32(-1)]),
                      dict(add_cmd, args=[i32(99), i32(26000004), i32(-1)]), {'bank': 1, 'id': 10, 'args': [i32(1)]}],
            'conds': [{'target': 1, 'eval': MENU_WAIT, 'pass': [], 'sub': []}], 'exit': [], 'while': []},
        1: {'entry': [], 'exit': [], 'while': [],
            'conds': [{'target': 10, 'eval': menu_pick(1), 'pass': [], 'sub': []}, {'target': 20, 'eval': menu_pick(2), 'pass': [], 'sub': []},
                      {'target': 9, 'eval': ALWAYS, 'pass': [], 'sub': []}]},
        9: {'entry': [], 'exit': [], 'while': [], 'conds': [ret]},
    }
    poor = int(w.get('poor') or 0)
    setf = lambda f, v: {'bank': 1, 'id': 11, 'args': [i32(f), i32(v)]}
    say = lambda text: {'bank': 1, 'id': 17, 'args': [i32(7), i32(text), i32(1), i32(0), i32(1)]}
    for base, flag, desc in ((10, int(w['flag1']), DESC1), (20, int(w['flag10']), DESC10)):
        st[base] = {'entry': [dict(conf_call, args=[i32(desc)])], 'exit': [], 'while': [],
                    'conds': [{'target': base + 1, 'eval': yes_eval, 'pass': [], 'sub': []}, {'target': 0, 'eval': no_eval, 'pass': [], 'sub': []}]}
        # 点亮请求，等 dark_core 熄灭（看到了）：1 秒没熄 = DLL 没加载（+3）；熄了看「诚意不够」（+5）还是许成了（+6）
        st[base + 1] = {'entry': ([setf(poor, 0)] if poor else []) + [setf(flag, 1)], 'exit': [], 'while': [],
                        'conds': [{'target': base + 4, 'eval': flag_is_off(flag), 'pass': [], 'sub': []},
                                  {'target': base + 3, 'eval': STATE_TIME_OVER_1, 'pass': [], 'sub': []}]}
        st[base + 3] = {'entry': [setf(flag, 0), say(MISSING_TEXT)],
                        'conds': [{'target': 9, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}], 'exit': [], 'while': []}
        st[base + 4] = {'entry': [], 'exit': [], 'while': [],
                        'conds': ([{'target': base + 5, 'eval': flag_is_on(poor), 'pass': [], 'sub': []}] if poor else [])
                        + [{'target': base + 6, 'eval': ALWAYS, 'pass': [], 'sub': []}]}
        if poor:
            st[base + 5] = {'entry': [setf(poor, 0), say(POOR_TEXT)],
                            'conds': [{'target': 0, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}], 'exit': [], 'while': []}
        st[base + 6] = {'entry': [say(DONE_TEXT)],
                        'conds': [{'target': 0, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}], 'exit': [], 'while': []}
    groups[gid] = st
    register(cx, 'wish', TEXT, gid)          # 收进赐福最上面的「暗黑重铸」（sc/forge.py）


def texts(cx, key):
    if not on(cx):
        return {}
    if key == 'zh':
        out = {TEXT: '向星辰许愿', ONE_TEXT: '许愿 1 次', TEN_TEXT: '许愿 10 次', DONE_TEXT: '星辰回应了你的愿望，装备会放进背包',
               POOR_TEXT: '星辰没有收到你的诚意',
               MISSING_TEXT: '现在无法许愿：暗黑重铸的组件没有加载，请用启动器重新启动游戏。',
               DESC1: '向星辰许愿 1 次：随机得到一件这个地区的装备。\n%s\n\n确定许愿吗？' % field('zh', 1),
               DESC10: '向星辰许愿 10 次：随机得到十件这个地区的装备（卢恩不够就少许几次）。\n%s\n\n确定许愿吗？' % field('zh', 2)}
    else:
        out = {TEXT: 'Wish upon the Stars', ONE_TEXT: 'Make a wish', TEN_TEXT: 'Make 10 wishes',
               DONE_TEXT: 'The stars answered. The gear will be put in your inventory.',
               POOR_TEXT: 'The stars did not receive your sincerity.',
               MISSING_TEXT: "Can't make a wish right now: a Darkforge component didn't load. Please restart the game from the launcher.",
               DESC1: 'Wish once: receive a random piece of gear from this region.\n%s\n\nMake the wish?' % field('en', 1),
               DESC10: 'Wish 10 times: receive ten random pieces of gear from this region (fewer if you run out of runes).\n%s\n\nMake the wishes?'
                       % field('en', 2)}
    return {'EventTextForTalk': out}
