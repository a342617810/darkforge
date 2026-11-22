# -*- coding: utf-8 -*-
"""赐福「暗黑重铸」→「许愿石升级」（rr/wishstone.py 建了许愿石才有，features.json 的 wishstone；只在高难度档列出来，同魇印 / 咒痕）：
  0 列八项能力值（名字同游戏升级界面：生命力、集中力、耐力、力气、灵巧、智力、信仰、感应）→ 1 按选项分；
  100 + k 选了第 k 项：能力值序号写进 attr0 起的标记、弹确认框（占位 #I8 由 dark_core 改写成现有许愿石个数、等级）；「否」回列表；
  200 + k 熄灭上次残留的「没有 / 已满」、点亮请求 → 请求熄了：300 + k 看「没有」（810）/「已满」（815），都没亮就 400 + k 提示这项提升了；
  超时（STATE_TIME_OVER_1）还没熄 = dark_core 没加载（830）。做完都回列表，方便连着用。
一次使用 10 个（用户 2026-11-21「许愿石做一个一次使用10个的入口 注意校验加点后不要超过上限」；features 有 ten 才有）：列表最后的
「一次使用 10 个」→ 500 同样八项 → 600 + k 确认框 → 700 + k 点亮 ten 和请求 → 750 看结果：810 / 815 同上，否则 900 提示
（文字里的占位 #IH 由 dark_core 改写成这次实际加了几点：最多 10 个，不够的有几个用几个，加到 99 为止）→ 回 500。"""
from .esdutil import ALWAYS, DIALOG_WAIT, MENU_WAIT, STATE_TIME_OVER_1, any_flag_on, flag_is_off, flag_is_on, i32, menu_parts, menu_pick, register

TEXT = 80098000                          # 「暗黑重铸」里的这一项
ATTR_TEXT, DESC_TEXT, DONE_TEXT = 80098010, 80098020, 80098030    # +k：能力值选项、确认框、提升了
NONE_TEXT, MAX_TEXT, MISSING_TEXT = 80098040, 80098041, 80098042
TEN_TEXT, DONE_TEN_TEXT, DESC_TEN_TEXT = 80098043, 80098044, 80098050    # 一次使用 10 个：入口、结果、确认框 +k
TEN_PICK, TEN_ATTR = 20, 31              # 列表里「一次使用 10 个」的选项号；10 个那张列表里第 k 项是 TEN_ATTR + k
RESULT_KIND = 'H'                        # 结果文字的占位种类（dark_core wishstone.rs 的 RESULT_KIND = 17）
RESULT_LEN = {'zh': 64, 'en': 96}
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


def result_field(lang):
    """一次用 10 个的结果占位（dark_core 改写成实际加了几点；没改写时显示的那句也说得通）"""
    if lang == 'zh':
        body = '#I%s 提升完成，能力值和等级见状态画面' % RESULT_KIND
        return '〔' + body + ' ' * (RESULT_LEN['zh'] - 2 - len(body)) + '〕'
    body = '#I%s Done. See the status screen for your attributes and level.' % RESULT_KIND
    return '[' + body + ' ' * (RESULT_LEN['en'] - 2 - len(body)) + ']'


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
    ten = int(f.get('ten') or 0)
    one = [setf(ten, 0)] if ten else []          # 一个一个用：熄掉「10 个」（上次残留的不算）
    head = [{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}]
    tail = [add(99, 26000004), {'bank': 1, 'id': 10, 'args': [i32(1)]}]
    st = {
        0: state(head + [add(1 + k, ATTR_TEXT + k) for k in range(n)] + ([add(TEN_PICK, TEN_TEXT)] if ten else []) + tail,
                 [to(1, MENU_WAIT)]),
        1: state([], [to(100 + k, menu_pick(1 + k)) for k in range(n)] + ([to(500, menu_pick(TEN_PICK))] if ten else []) + [to(9, ALWAYS)]),
        810: state([setf(none, 0), say(NONE_TEXT)], [to(0, DIALOG_WAIT)]),
        815: state([setf(mx, 0), say(MAX_TEXT)], [to(0, DIALOG_WAIT)]),
        830: state([setf(req, 0)] + one + [say(MISSING_TEXT)], [to(0, DIALOG_WAIT)]),
        9: state([], [ret]),
    }
    for k in range(n):
        st[100 + k] = state(bits(k) + [dict(conf_call, args=[i32(DESC_TEXT + k)])], [to(200 + k, yes_eval), to(0, no_eval)])
        st[200 + k] = state([setf(none, 0), setf(mx, 0)] + one + [setf(req, 1)], [to(300 + k, flag_is_off(req)), to(830, STATE_TIME_OVER_1)])
        st[300 + k] = state([], [to(810, flag_is_on(none)), to(815, flag_is_on(mx)), to(400 + k, ALWAYS)])
        st[400 + k] = state([say(DONE_TEXT + k)], [to(0, DIALOG_WAIT)])
    if ten:
        # 一次使用 10 个：同样八项（选项号 TEN_ATTR + k），确认后点亮 ten 和请求；做完回这张列表，方便连着用
        st[500] = state(head + [add(TEN_ATTR + k, ATTR_TEXT + k) for k in range(n)] + tail, [to(501, MENU_WAIT)])
        st[501] = state([], [to(600 + k, menu_pick(TEN_ATTR + k)) for k in range(n)] + [to(0, ALWAYS)])
        st[750] = state([], [to(812, flag_is_on(none)), to(817, flag_is_on(mx)), to(900, ALWAYS)])
        st[812] = state([setf(none, 0), say(NONE_TEXT)], [to(500, DIALOG_WAIT)])
        st[817] = state([setf(mx, 0), say(MAX_TEXT)], [to(500, DIALOG_WAIT)])
        st[900] = state([say(DONE_TEN_TEXT)], [to(500, DIALOG_WAIT)])
        for k in range(n):
            st[600 + k] = state(bits(k) + [dict(conf_call, args=[i32(DESC_TEN_TEXT + k)])], [to(700 + k, yes_eval), to(500, no_eval)])
            st[700 + k] = state([setf(none, 0), setf(mx, 0), setf(ten, 1), setf(req, 1)],
                                [to(750, flag_is_off(req)), to(830, STATE_TIME_OVER_1)])
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
            # 确认框只看得到前 3 行（sc/difficulty.py 用户 2026-11-06）：说明压进两行，第 3 行是占位
            out[DESC_TEN_TEXT + k] = '消耗最多 10 个许愿石，让%s最多提升 10 点，\n等级同样提升，不花卢恩；到 99 为止，不够就有几个用几个。\n%s\n\n确定提升吗？' % (name, field('zh'))
        else:
            out[DESC_TEXT + k] = 'Use 1 Wish Stone to raise %s by 1.\nYour level rises by 1 as well, at no rune cost.\n%s\n\nRaise it?' % (name, field('en'))
            out[DONE_TEXT + k] = '%s +1, level +1' % name
            out[DESC_TEN_TEXT + k] = ('Use up to 10 Wish Stones: %s +10 at most,\nlevel likewise; stops at 99, uses what you have.\n%s\n\nRaise it?'
                                      % (name, field('en')))
    out[TEN_TEXT] = '一次使用 10 个' if zh else 'Use 10 at once'
    out[DONE_TEN_TEXT] = result_field(key)
    if zh:
        out.update({NONE_TEXT: '没有许愿石', MAX_TEXT: '这项能力值已经是 99，不能再提升',
                    MISSING_TEXT: '现在无法升级：暗黑重铸的组件没有加载，请用启动器重新启动游戏。'})
    else:
        out.update({NONE_TEXT: 'You have no Wish Stone.', MAX_TEXT: 'This attribute is already 99.',
                    MISSING_TEXT: "Can't level up right now: a Darkforge component didn't load. Please restart the game from the launcher."})
    return {'EventTextForTalk': out}
