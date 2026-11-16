# -*- coding: utf-8 -*-
"""双子老妪：「更多选项」里双子老妪的「购买」「卖出」和几项「铃珠交易」（按菜单文字认）收进一个子菜单「双子老妪」，
放在原来「购买」的位置。顺序照原版圆桌厅堂双子老妪的菜单（购买、铃珠交易 1~4、幽影之地、卖出）；
铃珠交易带的「交过这组铃珠才显示」条件原样保留。「铃珠交易 3」在「更多选项」里不是直接加的，是建列表时调一个小状态机
（只加这一项）加的，这里认不出，就按原版的条件在子菜单里补上（MISSING）；那个小状态机的调用跳过（skip_helpers），
不然交过那几个铃珠后「更多选项」里还会多出一个散落的「铃珠交易３」（2026-11-03 查出来的）"""
from .esdutil import ALWAYS, MENU_WAIT, any_flag_on, i32, menu_parts, menu_pick, option_of, text_of

OPTION, TEXT = 36, 80090006
BUY, SELL = 26000010, 20000011
ITEM_TEXTS = (BUY, 26000011, 26000012, 26000013, 26000014, 80090000, SELL)
# 菜单里没有、要补的项：文字 →（「更多选项」分发表里的选项编号, 原版的显示条件：这些标记亮任意一个）
MISSING = {26000013: (4, (11109721, 11109722, 11109723, 11109724, 11109725, 11109728,
                          11109730, 11109731, 11109732, 11109733, 11109734))}


def on(cx):
    return bool(cx.S.get('twin_menu', True))


def esd(cx, groups):
    """收进去的项数记在 cx.twin_items（「更多选项」里「购买」「卖出」不全就是 0，什么都不改）"""
    cx.twin_items = 0
    if not on(cx):
        return
    p = menu_parts(groups, cx.root)
    more, gid, ret = p['more'], p['gid'], p['ret']

    def call_of(option):
        """选了这一项之后调用的状态机、调用完回来的条件；分发表里没有就 None"""
        tgt = next((x['target'] for x in more[p['disp']]['conds'] if x['eval'] == menu_pick(option)), None)
        if tgt is None:
            return None
        for _ in range(3):                       # 选中后可能先经过空状态（「购买」先到一个空状态再调用）
            call = [x for x in more[tgt]['entry'] if x['bank'] == 6]
            if call or len(more[tgt]['conds']) != 1:
                break
            tgt = more[tgt]['conds'][0]['target']
        if len(call) != 1:
            raise RuntimeError('「更多选项」里选项 %d 的调用状态对不上' % option)
        return call[0], more[tgt]['conds'][0]['eval']

    found = []                                   # (所在状态, 「更多选项」里的菜单项命令（补的项是 None）, 子菜单用的菜单项命令, 调用, 回来的条件)
    for text_id in ITEM_TEXTS:
        hit = [(sid, c) for sid, s in more.items() for c in s['entry'] if option_of(c) is not None and text_of(c) == text_id]
        got = None
        if len(hit) == 1:
            got = call_of(option_of(hit[0][1]))
            if got:
                found.append((hit[0][0], hit[0][1], hit[0][1]) + got)
        elif not hit and text_id in MISSING:
            opt, flags = MISSING[text_id]
            got = call_of(opt)
            if got:
                found.append((None, None, {'bank': 5, 'id': 19, 'args': [any_flag_on(flags), i32(opt), i32(text_id), i32(-1)]}) + got)
        if not got and text_id in (BUY, SELL):
            cx.notes.append('「双子老妪」子菜单没加上（更多选项里找不到购买 / 卖出）')
            return
    option = OPTION
    while any(option_of(c) == option for s in more.values() for c in s['entry']):
        option += 1
    first_cmd = found[0][1]                      # 「购买」：它的位置换成「双子老妪」，其他收进去的项从「更多选项」拿掉
    gone = {id(f[1]) for f in found[1:] if f[1] is not None}
    for sid in {f[0] for f in found if f[0] is not None}:
        more[sid] = dict(more[sid], entry=[dict(c, args=[i32(option), i32(TEXT), i32(-1)]) if c is first_cmd else c
                                           for c in more[sid]['entry'] if id(c) not in gone])

    def item(cmd, k):
        """子菜单里的第 k 项：文字、条件照抄，选项号换成 k"""
        if cmd['bank'] == 5:
            return dict(cmd, args=[cmd['args'][0], i32(k), cmd['args'][2], i32(-1)])
        return dict(cmd, args=[i32(k), cmd['args'][1], i32(-1)])
    add_cmd = p['add_cmd']
    st = {0: {'entry': [{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}]
                       + [item(f[2], j + 1) for j, f in enumerate(found)]
                       + [dict(add_cmd, args=[i32(99), i32(26000004), i32(-1)]), {'bank': 1, 'id': 10, 'args': [i32(1)]}],
              'conds': [{'target': 1, 'eval': MENU_WAIT, 'pass': [], 'sub': []}], 'exit': [], 'while': []},
          1: {'entry': [], 'exit': [], 'while': [],
              'conds': [{'target': 10 + j, 'eval': menu_pick(j + 1), 'pass': [], 'sub': []} for j in range(len(found))]
              + [{'target': 9, 'eval': ALWAYS, 'pass': [], 'sub': []}]},
          9: {'entry': [], 'exit': [], 'while': [], 'conds': [ret]}}
    for j, (_, _, _, call, done) in enumerate(found):
        st[10 + j] = {'entry': [call], 'exit': [], 'while': [], 'conds': [{'target': 0, 'eval': done, 'pass': [], 'sub': []}]}
    groups[gid] = st
    sid = max(more) + 1
    more[sid] = dict(p['call'], entry=[{'bank': 6, 'id': gid, 'args': []}])
    s = more[p['disp']]
    more[p['disp']] = dict(s, conds=s['conds'][:-1] + [{'target': sid, 'eval': menu_pick(option), 'pass': [], 'sub': []}] + s['conds'][-1:])
    cx.twin_items = len(found)
    n = skip_helpers(groups, more)
    if n != 1:
        cx.notes.append('「更多选项」里替它加「铃珠交易３」的小状态机找到 %d 个（应该是 1 个），没跳过的话会多出一项' % n)


def skip_helpers(groups, more):
    """「更多选项」里只调一个小状态机、而那个状态机加的选项全是收进子菜单的（ITEM_TEXTS）的状态：指向它的条件改成直接去它的下一步。
    返回跳过了几个"""
    skip = {}
    for sid, s in more.items():
        calls = [c for c in s['entry'] if c['bank'] == 6]
        if len(s['entry']) != 1 or len(calls) != 1 or len(s['conds']) != 1 or s['conds'][0]['target'] is None:
            continue
        adds = [text_of(c) for st in groups.get(calls[0]['id'] & 0xFFFFFFFF, {}).values() for c in st['entry'] if option_of(c) is not None]
        if adds and all(t in ITEM_TEXTS for t in adds):
            skip[sid] = s['conds'][0]['target']

    def fix(c):
        return dict(c, target=skip.get(c['target'], c['target']), sub=[fix(x) for x in c['sub']])
    for sid, s in list(more.items()):
        if sid not in skip:
            more[sid] = dict(s, conds=[fix(c) for c in s['conds']])
    return len(skip)


def texts(cx, key):
    if not getattr(cx, 'twin_items', 0):
        return {}
    return {'EventTextForTalk': {TEXT: '双子老妪' if key == 'zh' else 'Twin Maiden Husks'}}
