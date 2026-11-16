# -*- coding: utf-8 -*-
"""物品弹出菜单（使用 / 放置 / 丢弃）里 dll\\dark_lock 加的「锁定 / 解锁」的文字：GR_MenuText 是选项文字，
GR_LineHelp 是底部说明（编号和 dark_lock 一致）"""

TEXTS = {
    'GR_MenuText': {4190: ('Lock', '锁定'), 4191: ('Unlock', '解锁')},
    'GR_LineHelp': {4190: ('Lock this item: one-click sell skips it', '锁定这件装备：一键出售不会卖掉它'),
                    4191: ('Unlock this item', '解除这件装备的锁定')},
}


def texts(cx, key):
    return {fmg: {tid: t[0 if key == 'en' else 1] for tid, t in rows.items()} for fmg, rows in TEXTS.items()}
