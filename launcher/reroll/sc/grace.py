# -*- coding: utf-8 -*-
"""赐福「更多选项」菜单（移植自 ELDEN VINS）+ 头目复活（Vawser 的 Boss Resurrection - Lite）。
赐福对话脚本（script/talk/m00_00_00_00.talkesdbnd.dcx 里的 t000001000.esd）随机器输出可能改过，不能直接用 mod 的文件覆盖：
  1. 按 YAFSML [mod] 的加载顺序，取最后一个有这个文件的目录里的赐福脚本（没有就用原版）；
  2. 把 data/gracemenu/grace_more.esd 里的状态机（离线从 VINS / Lite 抽出来、已统一改号）加进去，
     顶层赐福菜单在「离去」前面加「更多选项」（编号 98），选中后打开「更多」；
  3. 菜单文字（「更多选项」、头目复活的 8000xxxx、幽影之地铃珠，data/gracemenu/text.json）。
「更多」里：购买（双子老妪）、铃珠交易 1~4 + 幽影之地、卖出、强化武器、调灵、复制战灰、从追忆获得力量、
获得英雄的防具、龙飨仪式、头目复活、重新诞生、化妆——都是原版的界面和商店行，不改 regulation、不改存档格式。
去掉了 VINS 自己的难度强度系统和地图标记开关（依赖 VINS 的数据）。头目复活免费（Lite 版扣遗迹石的遗留已去掉）。"""
import json
import os

import esd as esdlib

from .common import DATA
from .esdutil import ALWAYS, CONFIRM, DIALOG_WAIT, MENU_GROUP, OPTION, ROOT, calls, dispatch_state, flag_is_on, i32, option_of
from . import revivefix

ADDON = os.path.join(DATA, 'gracemenu', 'grace_more.esd')
TEXT = os.path.join(DATA, 'gracemenu', 'text.json')
# 联机会话里「头目复活」只提示（联机计划 13.2 G5：客机熄了自己的击败标记，和房主的世界对不上）。
# COOP_SESSION 和 dark_core coop.rs 的 SESSION_FLAG 一样（两边一起改）
COOP_SESSION, COOP_TEXT = 92570, 80099544
BOSS_ROOT = json.load(open(os.path.join(DATA, 'gracemenu', 'meta.json'), encoding='utf-8'))['boss_root']


def gate_boss(more, boss):
    """「更多」里调用头目复活的那个状态：前面加一道，会话里弹提示回到原来返回的地方；不是会话里照原样进清单"""
    hit = [sid for sid, s in more.items() if any(c['bank'] == 6 and (c['id'] & 0xFFFFFFFF) == boss for c in s['entry'])]
    if len(hit) != 1:
        raise RuntimeError('「更多选项」里调用头目复活的状态应该 1 个，实际：%s' % hit)
    sid = hit[0]
    if len(more[sid]['conds']) != 1:
        raise RuntimeError('调用头目复活的状态返回不止一条，对不上')
    back = more[sid]['conds'][0]['target']
    moved, dlg = max(more) + 1, max(more) + 2
    more = dict(more)
    more[moved] = more[sid]
    go = lambda t, ev: {'target': t, 'eval': ev, 'pass': [], 'sub': []}
    more[sid] = {'entry': [], 'exit': [], 'while': [], 'conds': [go(dlg, flag_is_on(COOP_SESSION)), go(moved, ALWAYS)]}
    say = {'bank': 1, 'id': 17, 'args': [i32(7), i32(COOP_TEXT), i32(1), i32(0), i32(1)]}
    more[dlg] = {'entry': [say], 'exit': [], 'while': [], 'conds': [go(back, DIALOG_WAIT)]}
    return more


def merge(base):
    """返回（合并后的 ESD, 加进来几个状态机, 改号表）；结构对不上时抛 RuntimeError"""
    lite = esdlib.read(open(ADDON, 'rb').read())
    revivefix.apply(lite['groups'])                 # 清单里有的 Boss 写的不是击败标记，复活不了
    B, L = base['groups'], lite['groups']
    if MENU_GROUP not in B or MENU_GROUP not in L:
        raise RuntimeError('找不到顶层赐福菜单（%d）' % MENU_GROUP)
    # Lite 的状态机：从入口开始的调用闭包
    seen, todo = set(), [ROOT]
    while todo:
        g = todo.pop()
        if g in seen or g not in L or g == MENU_GROUP:
            continue
        seen.add(g)
        todo += [c['id'] & 0xFFFFFFFF for s in L[g].values() for c in calls(s) if c['bank'] == 6]
    reuse = {CONFIRM} if CONFIRM in seen and B.get(CONFIRM) == L.get(CONFIRM) else set()
    remap, nid = {}, 2147300000
    for g in sorted(seen - reuse):
        while nid in B or nid in L:
            nid += 1
        remap[g] = nid
        nid += 1

    def fix_cmds(cs):
        out = []
        for c in cs:
            c = dict(c)
            if c['bank'] == 6 and (c['id'] & 0xFFFFFFFF) in remap:
                c['id'] = remap[c['id'] & 0xFFFFFFFF]
            out.append(c)
        return out

    def fix_conds(cs):
        return [dict(c, **{'pass': fix_cmds(c['pass']), 'sub': fix_conds(c['sub'])}) for c in cs]

    groups = dict(B)
    for g, ng in remap.items():
        groups[ng] = {sid: {'conds': fix_conds(s['conds']), 'entry': fix_cmds(s['entry']),
                            'exit': fix_cmds(s['exit']), 'while': fix_cmds(s['while'])} for sid, s in L[g].items()}

    # 顶层菜单挂入口。模板 = Lite 自己的菜单：哪个状态加的选项、哪个状态按选项跳转
    lm, bm = L[MENU_GROUP], {sid: dict(s) for sid, s in B[MENU_GROUP].items()}
    add_cmd = next(c for s in lm.values() for c in s['entry'] if option_of(c) == OPTION)
    lite_call = next((sid, s) for sid, s in lm.items() if any(c['bank'] == 6 and (c['id'] & 0xFFFFFFFF) == ROOT for c in s['entry']))
    pick = next(c for s in lm.values() for c in s['conds'] if c['target'] == lite_call[0])
    if any(option_of(c) == OPTION for s in bm.values() for c in s['entry']):
        raise RuntimeError('赐福菜单的选项编号 %d 已被占用' % OPTION)
    # 「离开」选项（99）之前加「更多选项」
    leave = [sid for sid, s in bm.items() if any(option_of(c) == 99 for c in s['entry'])]
    if len(leave) != 1:
        raise RuntimeError('找不到赐福菜单的「离开」选项')
    st = bm[leave[0]]
    k = next(i for i, c in enumerate(st['entry']) if option_of(c) == 99)
    bm[leave[0]] = dict(st, entry=st['entry'][:k] + [add_cmd] + st['entry'][k:])
    # 按选项跳转的状态：最后一条是「其他 → 关菜单」，新条件放在它前面（新条件直接比较 GetTalkListEntryResult()，两种写法的菜单都能用）
    disp = dispatch_state(bm, '赐福菜单')
    new_sid = max(bm) + 1
    st = bm[disp]
    bm[disp] = dict(st, conds=st['conds'][:-1] + [dict(pick, target=new_sid)] + st['conds'][-1:])
    back = lite_call[1]['conds'][0]['target']
    if back not in bm or not bm[back]['entry'] or (bm[back]['entry'][0]['bank'], bm[back]['entry'][0]['id']) != (1, 20):
        raise RuntimeError('赐福菜单的「重新列出选项」状态对不上')
    bm[new_sid] = {'conds': fix_conds(lite_call[1]['conds']), 'entry': fix_cmds(lite_call[1]['entry']),
                   'exit': fix_cmds(lite_call[1]['exit']), 'while': fix_cmds(lite_call[1]['while'])}
    groups[MENU_GROUP] = bm
    groups[remap[ROOT]] = gate_boss(groups[remap[ROOT]], remap[BOSS_ROOT])
    return dict(base, groups=groups), len(remap), remap


def texts(cx, key):
    out = {int(k): v for k, v in json.load(open(TEXT, encoding='utf-8'))[key].items()}
    out[COOP_TEXT] = ('联机时不能复活头目：会和房主的世界对不上。离开联机会话后再来。' if key == 'zh' else
                      "Bosses can't be revived during co-op: it would no longer match the host's world. Leave the session first.")
    return {'EventTextForTalk': out}


def sources(cx):
    return [ADDON, TEXT, os.path.join(DATA, 'gracemenu', 'meta.json')]
