# -*- coding: utf-8 -*-
"""对话脚本（ESD）的小工具：常量表达式、菜单项命令、往「更多选项」/ 赐福主菜单挂选项"""
import json
import os
import struct

from .common import DATA

_meta = json.load(open(os.path.join(DATA, 'gracemenu', 'meta.json'), encoding='utf-8'))
MENU_GROUP = _meta['template']  # 顶层赐福菜单
ROOT = _meta['root']            # 「更多选项」状态机（合并前的编号；合并后看 cx.root）
CONFIRM = _meta['confirm']      # 通用确认框（原版状态机，参数是文字编号）
OPTION = _meta['option']        # 顶层菜单里「更多选项」的选项编号（98）

MENU_WAIT = bytes.fromhex('7b82010000008200000000868201000000957a82000000008582000000009598820000000095a1')   # 等选项菜单关掉
DIALOG_WAIT = bytes.fromhex('7a820000000085820000000095a1')                                                  # 等提示框关掉
ALWAYS = bytes([0x41, 0xA1])                                                                                  # 恒真
CONFIRM_YES = bytes.fromhex('b9820000000095a1')        # 调用的状态机结果 == 0（确认框选了「是」）
CONFIRM_NO = bytes.fromhex('b9ba96a1')                 # 确认框有结果了、但不是「是」
STATE_TIME_OVER_1 = bytes.fromhex('826600000084820100000094a1')                                               # 进这个状态超过 1（单位没查到，实际远短于 250 毫秒，多半是帧）：等 dark_core 回应的菜单，它那边要每帧读请求


def GRACE_WAIT(kind):
    """赐福脚本里等某个界面关掉的写法"""
    return bytes.fromhex('7b82') + struct.pack('<i', kind) + bytes.fromhex('8200000000867a82000000008582000000009598820000000095a1')


def wait_menu(kind):
    """等某种界面关掉（同 MENU_WAIT，换界面类型：1 选项菜单 / 7 战灰 / 11 记忆法术；写法照抄法魂 mod）"""
    return MENU_WAIT[:2] + struct.pack('<i', kind) + MENU_WAIT[6:]


def i32(v):
    return bytes([0x82]) + int(v).to_bytes(4, 'little', signed=True) + bytes([0xA1])


def esd_int(arg):
    """参数字节码里的单个整数（只认常量）"""
    if len(arg) == 2 and arg[1] == 0xA1 and arg[0] < 0x80:
        return arg[0] - 64
    if len(arg) == 6 and arg[0] == 0x82 and arg[5] == 0xA1:
        return int.from_bytes(arg[1:5], 'little', signed=True)
    return None


def option_of(c):
    """菜单加选项的命令（1:19 AddTalkListData / 5:19 带条件的）→ 选项编号，其他命令 → None"""
    if (c['bank'], c['id']) == (1, 19):
        return esd_int(c['args'][0])
    if (c['bank'], c['id']) == (5, 19):
        return esd_int(c['args'][1])
    return None


def text_of(c):
    """菜单加选项的命令 → 文字编号"""
    if (c['bank'], c['id']) == (1, 19):
        return esd_int(c['args'][1])
    if (c['bank'], c['id']) == (5, 19):
        return esd_int(c['args'][2])
    return None


def calls(state):
    """一个状态里所有命令（入口 / 出口 / 持续，加上各条件里的）"""
    for k in ('entry', 'exit', 'while'):
        for c in state[k]:
            yield c

    def walk(cs):
        for c in cs:
            yield from c['pass']
            yield from walk(c['sub'])
    yield from walk(state['conds'])


def flag_is_off(flag):
    """eval：GetEventFlag(flag) == 0"""
    return bytes([0x4F, 0x82]) + int(flag).to_bytes(4, 'little', signed=True) + bytes([0x85, 0x82, 0, 0, 0, 0, 0x95, 0xA1])


def flag_is_on(flag):
    """eval：GetEventFlag(flag) != 0"""
    return bytes([0x4F, 0x82]) + int(flag).to_bytes(4, 'little', signed=True) + bytes([0x85, 0x82, 0, 0, 0, 0, 0x96, 0xA1])


def any_flag_on(flags):
    """eval：这些标记亮任意一个（GetEventFlag(a) != 0 || GetEventFlag(b) != 0 …）"""
    return b''.join(flag_is_on(f)[:-1] + (bytes([0x99]) if k else b'') for k, f in enumerate(flags)) + bytes([0xA1])


def menu_pick(k):
    """eval：GetTalkListEntryResult() == k"""
    return bytes([0x57, 0x84]) + i32(k)[:-1] + bytes([0x95, 0xA1])


def pick_values(ev):
    """eval 里拿选项结果比较的值：直接比较 GetTalkListEntryResult()（57 84 …）或比较存了结果的寄存器（af …）"""
    res = []
    for i in range(len(ev) - 1):
        if ev[i:i + 2] == bytes([0x57, 0x84]) or ev[i] == 0xAF:
            j = i + (2 if ev[i] == 0x57 else 1)
            if j < len(ev) and ev[j] == 0xA7:          # 先存进寄存器
                j += 1
            if j + 1 < len(ev) and ev[j] < 0x80 and ev[j + 1] == 0x95:
                res.append(ev[j] - 64)
            elif j + 5 < len(ev) and ev[j] == 0x82 and ev[j + 5] == 0x95:
                res.append(int.from_bytes(ev[j + 1:j + 5], 'little', signed=True))
    return res


def used_options(groups, gid):
    """这个菜单状态机已经占用的选项编号：自己加的、跳转里比较的，加上它调用的子状态机往同一个列表里加的。
    原版有的选项不是菜单自己加的：「开始第 N 次的世界」（41）是主菜单调用的子状态机加的，只在跳转里看得到
    （卢恩银行以前也用 41，通关后点它会进下一周目，用户 2026-11-13）"""
    g = groups[gid]
    used, sub = set(), set()
    for s in g.values():
        for c in calls(s):
            o = option_of(c)
            if o is not None:
                used.add(o)
            if c['bank'] == 6 and c['id'] in groups and c['id'] != gid:
                sub.add(c['id'])
        for c in s['conds']:
            used.update(pick_values(c['eval']))
    for sg in sub:                    # 子状态机自己清空列表（1:20）的是另一个菜单，不算
        st = groups[sg]
        if any((c['bank'], c['id']) == (1, 20) for s in st.values() for c in calls(s)):
            continue
        used.update(o for s in st.values() for c in calls(s) for o in [option_of(c)] if o is not None)
    return used


def dup_picks(groups):
    """同一个跳转状态里同一个选项值出现两次的地方 {(组, 状态, 选项值)}：前面那条先成立，后面的永远走不到。
    scripts.py 在各功能改完前后各算一次，多出来的就是新撞的（原版自己就有几处，不算）"""
    out = set()
    for gid, g in groups.items():
        for sid, s in g.items():
            seen = set()
            for c in s['conds']:
                for v in set(pick_values(c['eval'])):
                    if v in seen:
                        out.add((gid, sid, v))
                    seen.add(v)
    return out


def check_free(groups, gid, option, what):
    if option in used_options(groups, gid):
        raise RuntimeError('%s的选项编号 %d 已经有人用了（原版或别的功能），换一个' % (what, option))


def is_pick(ev):
    """按选项跳转的条件：直接比较 GetTalkListEntryResult()（随机器 / RNG Lands 的写法），
    或者原版的写法——第一条把结果存进寄存器（57 84 a7 …），后面的比较寄存器（af …）"""
    return ev[:2] == bytes([0x57, 0x84]) or ev[:1] == bytes([0xAF])


def dispatch_state(states, what):
    """菜单里按选项跳转的那个状态（条件里至少 5 条是按选项跳的）"""
    hit = [sid for sid, s in states.items() if sum(1 for c in s['conds'] if is_pick(c['eval'])) >= 5]
    if len(hit) != 1:
        raise RuntimeError('找不到%s的选项跳转' % what)
    return hit[0]


def menu_parts(groups, root):
    """「更多选项」菜单里加子菜单要用到的现成零件"""
    more = groups[root]
    p = {'more': more, 'groups': groups, 'root': root}
    p['lst'] = next(sid for sid, s in more.items() if any(option_of(c) == 99 for c in s['entry']))     # 「返回」所在的状态
    p['disp'] = next(sid for sid, s in more.items() if sum(1 for c in s['conds'] if c['eval'][:2] == bytes([0x40 + 23, 0x84])) >= 5)
    p['call'] = next(s for s in more.values() if len(s['entry']) == 1 and s['entry'][0]['bank'] == 6 and s['conds'])
    p['ret'] = next(c for st in groups.values() for s in st.values() for c in s['conds']
                    if c['target'] is None and c['pass'] and c['pass'][0]['bank'] == 7)
    p['add_cmd'] = next(c for st in more.values() for c in st['entry'] if (c['bank'], c['id']) == (1, 19))
    # 通用确认框：照抄现成的调用和判断「是」的条件（返回 0 = 是）
    # 调用（参数是文字编号）和两个判断照抄 RNG Lands 许愿的确认框（原版赐福脚本里调确认框都是先存寄存器的写法，抄不了）：
    # 「是」= 状态机结果 == 0；第二个是「确认框已经有结果、而且不是『是』」，写成恒真的话确认框还没弹出就跳走了
    p['conf_call'] = {'bank': 6, 'id': CONFIRM, 'args': [i32(0)]}
    p['yes_eval'] = CONFIRM_YES
    p['no_eval'] = CONFIRM_NO
    gid = 2147399010
    while gid in groups:
        gid += 1
    p['gid'] = gid
    return p


def hook_option(p, option, text_id, gid):
    """「更多选项」里在「返回」前面加一项 option（文字 text_id），选中进状态机 gid"""
    check_free(p['groups'], p['root'], option, '「更多选项」')
    more = p['more']
    s = more[p['lst']]
    k99 = next(i for i, c in enumerate(s['entry']) if option_of(c) == 99)
    more[p['lst']] = dict(s, entry=s['entry'][:k99] + [dict(p['add_cmd'], args=[i32(option), i32(text_id), i32(-1)])] + s['entry'][k99:])
    sid = max(more) + 1
    more[sid] = dict(p['call'], entry=[{'bank': 6, 'id': gid, 'args': []}])
    s = more[p['disp']]
    more[p['disp']] = dict(s, conds=s['conds'][:-1] + [{'target': sid, 'eval': menu_pick(option), 'pass': [], 'sub': []}] + s['conds'][-1:])


def hook_main_option(groups, option, text_id, gid, before=98):
    """赐福主菜单（MENU_GROUP）在「更多选项」（98）前面加一项 option（文字 text_id），选中进状态机 gid；
    调用方式照抄「更多选项」那一项（先关掉菜单再调，回来重新列出选项）"""
    bm = groups[MENU_GROUP]
    check_free(groups, MENU_GROUP, option, '赐福主菜单')
    lst =next(sid for sid, s in bm.items() if any(option_of(c) == before for c in s['entry']))
    disp = dispatch_state(bm, '赐福主菜单')
    tmpl_sid = next(c['target'] for c in bm[disp]['conds'] if c['eval'] == menu_pick(before))
    tmpl = bm[tmpl_sid]
    if sum(1 for c in tmpl['entry'] if c['bank'] == 6) != 1:
        raise RuntimeError('赐福主菜单「更多选项」的调用状态对不上')
    add_cmd = next(c for c in bm[lst]['entry'] if option_of(c) == before)
    s = bm[lst]
    k = next(i for i, c in enumerate(s['entry']) if option_of(c) == before)
    bm[lst] = dict(s, entry=s['entry'][:k] + [dict(add_cmd, args=[i32(option), i32(text_id)] + add_cmd['args'][2:])] + s['entry'][k:])
    sid = max(bm) + 1
    bm[sid] = dict(tmpl, entry=[{'bank': 6, 'id': gid, 'args': []} if c['bank'] == 6 else c for c in tmpl['entry']])
    s = bm[disp]
    bm[disp] = dict(s, conds=s['conds'][:-1] + [{'target': sid, 'eval': menu_pick(option), 'pass': [], 'sub': []}] + s['conds'][-1:])


def hook_main_after(groups, option, text_id, gid, after_text):
    """赐福主菜单（MENU_GROUP）紧跟在加文字 after_text 那一项的命令后面加一项 option（文字 text_id），选中进状态机 gid；
    加选项用「更多选项」那条命令的写法（不带条件），调用方式照抄「更多选项」（先关菜单再调，回来重新列出）。
    原版那一项是带条件加的（AddTalkListDataIf）也照样接在它后面（卢恩银行放在「升级」旁边，用户 2026-11-10）"""
    bm = groups[MENU_GROUP]
    check_free(groups, MENU_GROUP, option, '赐福主菜单')
    hits =[(sid, i) for sid, s in bm.items() for i, c in enumerate(s['entry']) if option_of(c) is not None and text_of(c) == after_text]
    if len(hits) != 1:
        raise RuntimeError('赐福主菜单里加文字 %d 的命令不是一条：%s' % (after_text, hits))
    lst98 = next(sid for sid, s in bm.items() if any(option_of(c) == OPTION for c in s['entry']))
    add_cmd = next(c for c in bm[lst98]['entry'] if option_of(c) == OPTION)
    disp = dispatch_state(bm, '赐福主菜单')
    tmpl = bm[next(c['target'] for c in bm[disp]['conds'] if c['eval'] == menu_pick(OPTION))]
    if sum(1 for c in tmpl['entry'] if c['bank'] == 6) != 1:
        raise RuntimeError('赐福主菜单「更多选项」的调用状态对不上')
    sid, i = hits[0]
    s = bm[sid]
    bm[sid] = dict(s, entry=s['entry'][:i + 1] + [dict(add_cmd, args=[i32(option), i32(text_id)] + add_cmd['args'][2:])] + s['entry'][i + 1:])
    new = max(bm) + 1
    bm[new] = dict(tmpl, entry=[{'bank': 6, 'id': gid, 'args': []} if c['bank'] == 6 else c for c in tmpl['entry']])
    s = bm[disp]
    bm[disp] = dict(s, conds=s['conds'][:-1] + [{'target': new, 'eval': menu_pick(option), 'pass': [], 'sub': []}] + s['conds'][-1:])


def register(cx, key, text_id, gid, cond=None):
    """我们的功能（一键鉴定、装备工坊、许愿、暗黑商店、一键出售、说明）不再各自挂赐福主菜单：登记到 cx.forge，
    sc/forge.py 最后把它们收进赐福最上面的「暗黑重铸」子菜单（用户 2026-10-31）。
    cond（eval 字节）：给了就只在它成立时列出来（AddTalkListDataIf；魇印 / 七咒只在高难度档，sc/wspages.py）"""
    if not hasattr(cx, 'forge'):
        cx.forge = []
        cx.forge_cond = {}
    cx.forge.append((key, text_id, gid))
    if cond is not None:
        cx.forge_cond[key] = cond


def hook_main_top(groups, option, text_id, gid):
    """赐福主菜单（MENU_GROUP）最上面加一项 option（文字 text_id），选中进状态机 gid：
    加在清空选项列表（1:20）之后、原版第一项之前；跳转、调用方式同 hook_main_option（照抄「更多选项」那一项）"""
    bm = groups[MENU_GROUP]
    check_free(groups, MENU_GROUP, option, '赐福主菜单')
    clear =[sid for sid, s in bm.items() if any((c['bank'], c['id']) == (1, 20) for c in s['entry'])]
    if len(clear) != 1:
        raise RuntimeError('赐福主菜单里清空选项列表的状态不是一个：%s' % clear)
    lst = next(sid for sid, s in bm.items() if any(option_of(c) == OPTION for c in s['entry']))
    disp = dispatch_state(bm, '赐福主菜单')
    tmpl = bm[next(c['target'] for c in bm[disp]['conds'] if c['eval'] == menu_pick(OPTION))]
    if sum(1 for c in tmpl['entry'] if c['bank'] == 6) != 1:
        raise RuntimeError('赐福主菜单「更多选项」的调用状态对不上')
    add_cmd = next(c for c in bm[lst]['entry'] if option_of(c) == OPTION)
    s = bm[clear[0]]
    k = next(i for i, c in enumerate(s['entry']) if (c['bank'], c['id']) == (1, 20)) + 1
    bm[clear[0]] = dict(s, entry=s['entry'][:k] + [dict(add_cmd, args=[i32(option), i32(text_id)] + add_cmd['args'][2:])] + s['entry'][k:])
    sid = max(bm) + 1
    bm[sid] = dict(tmpl, entry=[{'bank': 6, 'id': gid, 'args': []} if c['bank'] == 6 else c for c in tmpl['entry']])
    s = bm[disp]
    bm[disp] = dict(s, conds=s['conds'][:-1] + [{'target': sid, 'eval': menu_pick(option), 'pass': [], 'sub': []}] + s['conds'][-1:])
    return tmpl


def write_check(e):
    """写回并读一遍核对状态机数"""
    import esd
    raw = esd.write(e)
    if esd.read(raw)['groups'].keys() != e['groups'].keys():
        raise RuntimeError('对话脚本写回后读回来不对')
    return raw
