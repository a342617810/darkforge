# -*- coding: utf-8 -*-
"""dll\\dark_slot 打开的第五个护符槽（原版的誓约槽）：装备栏左上角的槽位名。
原版 GR_MenuText 103050~103053 是「护符１」~「护符４」，誓约槽要的 103054 原版没有（显示 ?MenuText?），Golden Age 也是补这一条。
点进槽位以后列表左上角的标题另有一条：exe 的 .data 里装备槽种类表（2.7.1.0 在 0x3b3a700 起，每种 88 字节、开头是标题），
护符槽是 40509「护符」，誓约槽是 40515（原版也没有这条，用户 2026-11-13「点进去之后左上角的名字还是 ?menutext?」），补成和护符槽一样"""

TEXTS = {'GR_MenuText': {103054: ('Talisman 5', '护符５'), 40515: ('Talismans', '护符')}}


def texts(cx, key):
    return {fmg: {tid: t[0 if key == 'en' else 1] for tid, t in rows.items()} for fmg, rows in TEXTS.items()}
