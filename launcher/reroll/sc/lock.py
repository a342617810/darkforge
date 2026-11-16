# -*- coding: utf-8 -*-
"""物品弹出菜单（使用 / 放置 / 丢弃）里 dll\\dark_lock 加的「锁定 / 解锁」的文字：GR_MenuText 是选项文字，
GR_LineHelp 是底部说明（编号和 dark_lock 一致）"""

TEXTS = {
    'GR_MenuText': {4190: ('Lock', '锁定'), 4191: ('Unlock', '解锁')},
    'GR_LineHelp': {4190: ('Lock this item: one-click sell skips it', '锁定这件装备：一键出售不会卖掉它'),
                    4191: ('Unlock this item', '解除这件装备的锁定')},
}
# 联机时「送给 <队友>」（联机计划 13.7，dark_lock 加选项、dark_core 的 gear/gift.rs 送）：第 i 个队友的选项文字是占位 #IC~#IG，
# dark_core 找到后改写成「送给 名字」（confirm_tick；占位整段被盖掉，所以要留够长度）
GIFT0, GIFT_N, GIFT_LEN = 4192, 5, 24
for _i in range(GIFT_N):
    _k = 'CDEFG'[_i]
    _zh = '#I%s 送给队友 %d' % (_k, _i + 1)
    _en = '#I%s Give to teammate %d' % (_k, _i + 1)
    TEXTS['GR_MenuText'][GIFT0 + _i] = ('[' + _en.ljust(GIFT_LEN + 8) + ']', '〔' + _zh + '　' * max(0, GIFT_LEN - len(_zh)) + '〕')
    TEXTS['GR_LineHelp'][GIFT0 + _i] = ('Give this gear to this teammate: it leaves your inventory only after they receive it',
                                       '把这件新装备送给这位队友：对方收下后才会从你的背包移走')


def texts(cx, key):
    return {fmg: {tid: t[0 if key == 'en' else 1] for tid, t in rows.items()} for fmg, rows in TEXTS.items()}
