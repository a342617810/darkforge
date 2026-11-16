# -*- coding: utf-8 -*-
"""赐福「Dark Reforged 说明」（2026-10-30 起代替开局的几本说明书，开局只留一本「欢迎游玩」，见 rr/manuals.py）：
赐福「暗黑重铸」子菜单最后一项（sc/forge.py；以前在赐福主菜单），子菜单列出 data\\guide.json 的各个主题；选一个主题就一页一页弹提示框，
最后一页关掉回到主题列表，「返回」回赐福菜单。只写机制、不写数值。
提示框照抄剑心修罗的说明（1:17 OpenGenericDialog(3, 文字, 2, 0, 0)，大框，一页能放约 200 字 / 11 行）：
一键鉴定那种 (7, 文字, 1, 0, 1) 的小提示框只显示一行（2026-10-30 游戏里看到的）。
文字编号（EventTextForTalk）：选项 TEXT，主题名 TEXT + 1 起，各页 PAGE0 + 10 × 第几个主题 + 第几页
框的高度按文字里的换行数定，不按自动折行后的行数（用户 2026-11-03：「防具与护符」的框很小、字被截断——那几页是几大段长文字）：
所以每页在这里手动折行（中文一行最多 LINE_ZH 个全角宽、英文 LINE_EN 个字母，标点不放行首），再补空行到 LINES 行，
每一页都是同样大的框（剑心修罗的大框一页 11~13 行、一行最多 37 个字都显示得全）。超过 LINES 行重随时报错，拆成两页。"""
import json
import os
import re
import textwrap
import unicodedata

from .common import DATA
from .esdutil import ALWAYS, DIALOG_WAIT, MENU_WAIT, register, i32, menu_parts, menu_pick, option_of

OPTION, TEXT, PAGE0 = 37, 80091000, 80091100
DIALOG = (3, 2, 0, 0)              # 1:17 的参数：类型 3（大框），文字编号放在类型后面
FILE = os.path.join(DATA, 'guide.json')
MAX_TOPICS, MAX_PAGES = 9, 9
LINE_ZH, LINE_EN, LINES = 32, 64, 13     # 一行最多多宽（中文按全角 1、半角 0.5 算；英文按字母）、每页统一几行
NO_START = set('，。、；：！？）」』》〉…%,.;:!?)]}')   # 不放在行首的标点
PAD = {'zh': '\u3000', 'en': '\u00a0'}  # 补的空行里放一个空白字，免得被当成没有内容去掉
NAME = {'zh': '暗黑重铸说明', 'en': 'Darkforge Guide'}
AILMENT = dict(madness_hp_pct=5.0, madness_poise_pct=30.0, death_resist_cut=30.0, death_secs=60.0)    # 同 rr/ailments.py 的 DEFAULT


def fill(cx, text):
    """页面里的 {名字} 换成设置里的数值（发狂、咒死：settings.json 的 ailment_rework，没写的用默认）；名字写错就报错"""
    v = dict(AILMENT, **{k: x for k, x in (cx.S.get('ailment_rework') or {}).items() if k in AILMENT})
    return re.sub(r'\{(\w+)\}', lambda m: '%g' % float(v[m.group(1)]), text)


def load():
    """{'zh': [{'topic', 'pages'}], 'en': ...}，中英文主题数、页数要一样"""
    if not os.path.isfile(FILE):
        return None
    g = json.load(open(FILE, encoding='utf-8'))
    zh, en = g['zh'], g['en']
    if not zh or len(zh) > MAX_TOPICS or len(zh) != len(en) or any(
            not a['pages'] or len(a['pages']) > MAX_PAGES or len(a['pages']) != len(b['pages']) for a, b in zip(zh, en)):
        raise RuntimeError('赐福说明：data\\guide.json 中英文主题数 / 页数不一样，或超过 %d 个主题、%d 页' % (MAX_TOPICS, MAX_PAGES))
    return g


def sources(cx):
    return [FILE]


def esd(cx, groups):
    g = load()
    cx.guide = bool(g)
    if not g:
        return
    from .esdutil import MENU_GROUP
    if any(option_of(c) == OPTION for s in groups[MENU_GROUP].values() for c in s['entry']):
        raise RuntimeError('赐福菜单的选项编号 %d 已被占用（暗黑重铸说明）' % OPTION)
    topics = g['zh']
    p = menu_parts(groups, cx.root)
    add_cmd, gid = p['add_cmd'], p['gid']
    # 主题列表（写法同向星辰许愿的子菜单）；主题 j 的第 k 页在状态 10 × (j + 1) + k，最后一页回到列表
    st = {0: {'entry': [{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}]
                       + [dict(add_cmd, args=[i32(j + 1), i32(TEXT + 1 + j), i32(-1)]) for j in range(len(topics))]
                       + [dict(add_cmd, args=[i32(99), i32(26000004), i32(-1)]), {'bank': 1, 'id': 10, 'args': [i32(1)]}],
              'conds': [{'target': 1, 'eval': MENU_WAIT, 'pass': [], 'sub': []}], 'exit': [], 'while': []},
          1: {'entry': [], 'exit': [], 'while': [],
              'conds': [{'target': 10 * (j + 1), 'eval': menu_pick(j + 1), 'pass': [], 'sub': []} for j in range(len(topics))]
              + [{'target': 9, 'eval': ALWAYS, 'pass': [], 'sub': []}]},
          9: {'entry': [], 'exit': [], 'while': [], 'conds': [p['ret']]}}
    for j, t in enumerate(topics):
        n = len(t['pages'])
        for k in range(n):
            st[10 * (j + 1) + k] = {
                'entry': [{'bank': 1, 'id': 17, 'args': [i32(DIALOG[0]), i32(PAGE0 + 10 * j + k)] + [i32(x) for x in DIALOG[1:]]}],
                'conds': [{'target': 10 * (j + 1) + k + 1 if k + 1 < n else 0, 'eval': DIALOG_WAIT, 'pass': [], 'sub': []}],
                'exit': [], 'while': []}
    groups[gid] = st
    register(cx, 'guide', TEXT, gid)          # 收进赐福最上面的「暗黑重铸」（sc/forge.py）


def width(ch):
    return 1.0 if unicodedata.east_asian_width(ch) in ('W', 'F') else 0.5


def wrap(text, lang):
    """一段段折成行（原来的换行保留）"""
    out = []
    for par in text.split('\n'):
        if lang != 'zh':
            out += textwrap.wrap(par, LINE_EN) or ['']
            continue
        line, w = '', 0.0
        for ch in par:
            if line and w + width(ch) > LINE_ZH and ch not in NO_START:
                out.append(line)
                line, w = '', 0.0
            line += ch
            w += width(ch)
        out.append(line)
    return out


def page(lang, topic, k, n, body):
    """一页：标题、空一行、正文（手动折行），补空行到 LINES 行"""
    head = ('【%s】' if lang == 'zh' else '[%s]') % (topic if n == 1 else '%s %d/%d' % (topic, k + 1, n))
    lines = [head, ''] + wrap(body, lang)
    if len(lines) > LINES:
        raise RuntimeError('赐福说明：「%s」第 %d 页折行后 %d 行，超过 %d 行（data\\guide.json 拆成两页）' % (topic, k + 1, len(lines), LINES))
    lines += [PAD[lang]] * (LINES - len(lines))
    return '\n'.join(lines)


def texts(cx, key):
    if not getattr(cx, 'guide', False):
        return {}
    out = {TEXT: NAME[key]}
    for j, t in enumerate(load()[key]):
        out[TEXT + 1 + j] = t['topic']
        for k, body in enumerate(t['pages']):
            out[PAGE0 + 10 * j + k] = page(key, t['topic'], k, len(t['pages']), fill(cx, body))
    return {'EventTextForTalk': out}
