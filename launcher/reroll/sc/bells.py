# -*- coding: utf-8 -*-
"""不杀商人拿铃珠（参照法魂；settings.json 的 merchant_bell_bearings）：商人对话的主菜单（选项 1 =「购买」20000010）里，
「离开」前加「获取铃珠」（这个商人的铃珠获取标记没亮才显示），选了直接给这个商人原本被杀后掉的那张物品表（1:104 AwardItemLot），
等「获得物品」提示关掉回到菜单开头。和杀商人捡铃珠是同一个获取标记：拿过 / 杀过就不再显示。
脚本来源：加载的包里最后生效的那份（开敌人随机时是随机器输出），没有就用随机器自带的原版脚本"""
import os
import re

import erlib
import esd as esdlib

from .common import last_with, vanilla
from .esdutil import ALWAYS, flag_is_off, i32, menu_pick, option_of, text_of, write_check

TEXT = 80090150
MERCHANTS = {          # 地图对话包 → {脚本: (铃珠的获取标记, 物品表)}（和法魂一致；都是原版里杀商人掉铃珠的那几张表）
    'm60_00_00_00': {'t800006000': (400049, 110410), 't801116000': (400901, 119000), 't801126000': (400902, 119005),
                     't801136000': (400903, 119010), 't801146000': (400904, 119015), 't801156000': (400905, 119020),
                     't801166000': (400906, 119025), 't801176000': (400907, 119030), 't801186000': (400908, 119035),
                     't801196000': (400909, 119040), 't801206000': (400910, 119045), 't801216000': (400911, 119050),
                     't801226000': (400912, 119055), 't801236000': (400913, 119060), 't801256000': (400915, 119070),
                     't801266000': (400916, 119075)},
    'm12_01_00_00': {'t801281201': (400918, 119085)},
    'm12_02_00_00': {'t801271202': (400917, 119080)},
    'm12_05_00_00': {'t801291205': (400919, 119090)},
}
BUY_TEXT, LEAVE_TEXT = 20000010, 20000009          # 主菜单的「购买」「离开」（离开的选项编号不一定是 99，咖列是 9）
ITEM_GET_WAIT = bytes.fromhex('7b82160000008200000000867a82000000008582000000009598820000000095a1')    # 等「获得物品」提示关掉


def talk_sources(cx):
    """{地图: 对话包路径}"""
    if not cx.S.get('merchant_bell_bearings', True):
        return {}
    out = {}
    for m in MERCHANTS:
        rel = os.path.join('script', 'talk', m + '.talkesdbnd.dcx')
        p = last_with(cx.sources, rel) or vanilla(rel)
        if p and os.path.isfile(p):
            out[m] = p
    return out


def add_option(e, flag, lot):
    """给一个商人脚本的主菜单加「获取铃珠」，返回改了几个菜单状态机"""
    n = 0
    for g in e['groups'].values():
        build = next((sid for sid, st in g.items()
                      if any(option_of(c) == 1 and text_of(c) == BUY_TEXT for c in st['entry'])
                      and any(text_of(c) == LEAVE_TEXT for c in st['entry'])), None)
        disp = next((sid for sid, st in g.items() if any(c['eval'][:2] == b'\x57\x84' for c in st['conds'])), None)
        start = next((sid for sid, st in g.items() if any((c['bank'], c['id']) == (1, 20) for c in st['entry'])), None)
        if None in (build, disp, start):
            continue
        entry = g[build]['entry']
        used = {option_of(c) for c in entry}
        k = next(i for i in range(1, 99) if i not in used)
        at = next(i for i, c in enumerate(entry) if text_of(c) == LEAVE_TEXT)
        g[build] = dict(g[build], entry=entry[:at] + [{'bank': 5, 'id': 19, 'args': [flag_is_off(flag), i32(k), i32(TEXT), i32(-1)]}] + entry[at:])
        s1 = max(g) + 1
        g[s1] = {'entry': [{'bank': 1, 'id': 104, 'args': [i32(lot)]}], 'exit': [], 'while': [],
                 'conds': [{'target': s1 + 1, 'eval': ALWAYS, 'pass': [], 'sub': []}]}
        g[s1 + 1] = {'entry': [], 'exit': [], 'while': [], 'conds': [{'target': start, 'eval': ITEM_GET_WAIT, 'pass': [], 'sub': []}]}
        conds = g[disp]['conds']
        g[disp] = dict(g[disp], conds=conds[:-1] + [{'target': s1, 'eval': menu_pick(k), 'pass': [], 'sub': []}] + conds[-1:])
        n += 1
    return n


def files(cx, tmp):
    n_m = 0
    for m, src in talk_sources(cx).items():
        bnd = erlib.Bnd4(erlib.dcx_decompress(open(src, 'rb').read()))
        for script, (flag, lot) in MERCHANTS[m].items():
            name = next((x for x in bnd.entries if re.split(r'[\\/]', x)[-1].lower() == script + '.esd'), None)
            if name is None:
                continue
            e = esdlib.read(bytes(bnd.get(name)))
            if not add_option(e, flag, lot):
                continue
            bnd.put(name, write_check(e))
            n_m += 1
        rel = os.path.join('script', 'talk', m + '.talkesdbnd.dcx')
        os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
        erlib.write_dcx_file(os.path.join(tmp, rel), bytes(bnd.data))
    cx.bell_merchants = n_m


def texts(cx, key):
    if not talk_sources(cx):
        return {}
    return {'EventTextForTalk': {TEXT: '获取铃珠' if key == 'zh' else 'Receive bell bearing'}}


def sources(cx):
    return sorted(talk_sources(cx).values())
