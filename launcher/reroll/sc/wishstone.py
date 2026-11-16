# -*- coding: utf-8 -*-
"""赐福「暗黑重铸」→「许愿石升级」（rr/wishstone.py 建了许愿石才有，features.json 的 wishstone；只在高难度档列出来，同魇印 / 咒痕）：
  0 列八项能力值（名字同游戏升级界面：生命力、集中力、耐力、力气、灵巧、智力、信仰、感应）→ 1 按选项分；
  100 + k 选了第 k 项：能力值序号写进 attr0 起的标记、弹确认框（占位 #I8 由 dark_core 改写成现有许愿石个数、等级）；「否」回列表；
  200 + k 熄灭上次残留的「没有 / 已满」、点亮请求 → 请求熄了：300 + k 看「没有」（810）/「已满」（815），都没亮就 400 + k 提示这项提升了；
  超时（STATE_TIME_OVER_1）还没熄 = dark_core 没加载（830）。做完都回列表，方便连着用。"""
from .esdutil import ALWAYS, DIALOG_WAIT, MENU_WAIT, STATE_TIME_OVER_1, any_flag_on, flag_is_off, flag_is_on, i32, menu_parts, menu_pick, register

TEXT = 80098000                          # 「暗黑重铸」里的这一项
ATTR_TEXT, DESC_TEXT, DONE_TEXT = 80098010, 80098020, 80098030    # +k：能力值选项、确认框、提升了
NONE_TEXT, MAX_TEXT, MISSING_TEXT = 80098040, 80098041, 80098042
NAMES = {'zh': ('生命力', '集中力', '耐力', '力气', '灵巧', '智力', '信仰', '感应'),
         'en': ('Vigor', 'Mind', 'Endurance', 'Strength', 'Dexterity', 'Intelligence', 'Faith', 'Arcane')}
KIND = 8                                 # 确认框占位的种类（dark_core gear.rs 的 #I 占位，0~7 是鉴定、许愿、回收）
FIELD_LEN = {'zh': 30, 'en': 44}         # 含两端括号的字符数（同 sc/identify.py）


def on(cx):
    f = cx.feat.get('wishstone') or {}
    return f if f.get('req') and f.get('tiers') else None


def field(lang):
    if lang == 'zh':
        body = '#I%d 正在清点许愿石……' % KIND
        return '〔' + body + ' ' * (FIELD_LEN['zh'] - 2 - len(body)) + '〕'
    body = '#I%d counting Wish Stones...' % KIND
    return '[' + body + ' ' * (FIELD_LEN['en'] - 2 - len(body)) + ']'


def esd(cx, groups):
    f = on(cx)
    if not f:
        return
    req, none, mx, a0, nb = (int(f[k]) for k in ('req', 'none', 'max', 'attr0', 'attr_bits'))
    p = menu_parts(groups, cx.root)
    add_cmd, conf_call, yes_eval, no_eval, ret, gid = (p[k] for k in ('add_cmd', 'conf_call', 'yes_eval', 'no_eval', 'ret', 'gid'))
    setf = lambda fl, v: {'bank': 1, 'id': 11, 'args': [i32(fl), i32(v)]}
    say = lambda text: {'bank': 1, 'id': 17, 'args': [i32(7), i32(text), i32(1), i32(0), i32(1)]}
    add = lambda k, text: dict(add_cmd, args=[i32(k), i32(text), i32(-1)])
    to = lambda target, ev: {'target': target, 'eval': ev, 'pass': [], 'sub': []}
    state = lambda entry, conds: {'entry': entry, 'exit': [], 'while': [], 'conds': conds}
    bits = lambda v: [setf(a0 + i, (v >> i) & 1) for i in range(nb)]
    n = len(NAMES['zh'])
    st = {
        0: state([{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}]
                 + [add(1 + k, ATTR_TEXT + k) for k in range(n)] + [add(99, 26000004), {'bank': 1, 'id': 10, 'args': [i32(1)]}],
                 [to(1, MENU_WAIT)]),
        1: state([], [to(100 + k, menu_pick(1 + k)) for k in range(n)] + [to(9, ALWAYS)]),
        810: state([setf(none, 0), say(NONE_TEXT)], [to(0, DIALOG_WAIT)]),
        815: state([setf(mx, 0), say(MAX_TEXT)], [to(0, DIALOG_WAIT)]),
        830: state([setf(req, 0), say(MISSING_TEXT)], [to(0, DIALOG_WAIT)]),
        9: state([], [ret]),
    }
    for k in range(n):
        st[100 + k] = state(bits(k) + [dict(conf_call, args=[i32(DESC_TEXT + k)])], [to(200 + k, yes_eval), to(0, no_eval)])
        st[200 + k] = state([setf(none, 0), setf(mx, 0), setf(req, 1)], [to(300 + k, flag_is_off(req)), to(830, STATE_TIME_OVER_1)])
        st[300 + k] = state([], [to(810, flag_is_on(none)), to(815, flag_is_on(mx)), to(400 + k, ALWAYS)])
        st[400 + k] = state([say(DONE_TEXT + k)], [to(0, DIALOG_WAIT)])
    groups[gid] = st
    register(cx, 'wishstone', TEXT, gid, cond=any_flag_on([int(x) for x in f['tiers']]))   # 「暗黑重铸」子菜单里只在高难度档列出来


def texts(cx, key):
    if not on(cx):
        return {}
    zh = key == 'zh'
    names = NAMES[key]
    out = {TEXT: '许愿石升级' if zh else 'Wish Stone Level Up'}
    for k, name in enumerate(names):
        out[ATTR_TEXT + k] = name
        if zh:
            out[DESC_TEXT + k] = '消耗 1 个许愿石，让%s提升 1 点，\n等级随之提升 1 级，不花卢恩。\n%s\n\n确定提升吗？' % (name, field('zh'))
            out[DONE_TEXT + k] = '%s提升了 1 点，等级提升了 1 级' % name
        else:
            out[DESC_TEXT + k] = 'Use 1 Wish Stone to raise %s by 1.\nYour level rises by 1 as well, at no rune cost.\n%s\n\nRaise it?' % (name, field('en'))
            out[DONE_TEXT + k] = '%s +1, level +1' % name
    if zh:
        out.update({NONE_TEXT: '没有许愿石', MAX_TEXT: '这项能力值已经是 99，不能再提升',
                    MISSING_TEXT: '现在无法升级：暗黑重铸的组件没有加载，请用启动器重新启动游戏。'})
    else:
        out.update({NONE_TEXT: 'You have no Wish Stone.', MAX_TEXT: 'This attribute is already 99.',
                    MISSING_TEXT: "Can't level up right now: a Darkforge component didn't load. Please restart the game from the launcher."})
    return {'EventTextForTalk': out}
