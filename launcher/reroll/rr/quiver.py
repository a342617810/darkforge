# -*- coding: utf-8 -*-
"""箭袋护符（已停用，2026-10-29 用户：移除箭袋护符）：以前（v0.4 起）戴着时弓、弩不消耗箭矢、精力消耗 +15%，
暗黑商店护符商店最后一格卖，不消耗箭矢由 dll\\dark_sell 开游戏的调试开关。现在不卖、没有效果（dark_sell 也不管了），
不消耗弹药改由新词条「无尽箭袋」（dll\\dark_core 的 free 规则）做。
护符这一行参数还留着：老存档里买过的不会变成参数不存在的物品；名字标成「已停用」，可以卖掉（卖价照旧）。
要在 affixes.build 之后（文字包这时已经有护符模板的文字）。"""
from .common import *  # noqa: F401,F403

QUIVER_ID = 4140
QUIVER_ICON = 18330            # 原版远箭护符的图标
TEMPLATE_TAL = 2100            # 原版远箭护符
QUIVER_SORT = 419999           # 放在所有词条护符模板（410000 起）后面
TEXTS = {
    'zh': ('箭袋护符（已停用）', '已停用，没有效果',
           '这个护符已经移除，佩戴时没有任何效果，可以卖掉或丢掉。\n\n'
           '想让箭、弩箭和投掷道具不再消耗，可以找带「无尽箭袋」的传说护符。'),
    'en': ('Quiver Talisman (retired)', 'Retired: no effect',
           'This talisman has been removed and no longer does anything. Sell or discard it.\n\n'
           'Legendary talismans with Endless Quiver keep arrows, bolts and throwables from being used up.'),
}


def build(ctx):
    """留下护符这一行（没有效果、不上架）和文字，老存档里的不会变成参数不存在的物品"""
    bnd = ctx.bnd
    P_a = erlib.Param(bnd.get('EquipParamAccessory.param'))
    if QUIVER_ID in P_a.rows or TEMPLATE_TAL not in P_a.rows:
        raise RuntimeError('箭袋护符（已停用）：编号 %d 已被占用，或缺少原版底子 %d' % (QUIVER_ID, TEMPLATE_TAL))
    aoff = {n: (o, fc) for n, fc, o, *_ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamAccessory.xml')))[0]}
    row = bytearray(P_a.rows[TEMPLATE_TAL])
    for f, v in (('refId', -1), ('iconId', QUIVER_ICON), ('accessoryGroup', QUIVER_ID), ('rarity', 2), ('sortId', QUIVER_SORT),
                 ('weight', 0.5), ('sellValue', 500), ('residentSpEffectId1', -1), ('residentSpEffectId2', -1),
                 ('residentSpEffectId3', -1), ('residentSpEffectId4', -1)):
        if f in aoff:
            struct.pack_into('<' + aoff[f][1], row, aoff[f][0], v)
    P_a.add_row(QUIVER_ID, row)
    bnd.put('EquipParamAccessory.param', P_a.serialize())
    for code, key in (('engus', 'en'), ('zhocn', 'zh')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for fmg, text in zip(('AccessoryName.fmg', 'AccessoryInfo.fmg', 'AccessoryCaption.fmg'), TEXTS[key]):
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            d[QUIVER_ID] = text
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.report.append('箭袋护符（已停用）：护符 %d 只留参数和文字（没有效果、不上架），老存档里的不会变成参数不存在的物品' % QUIVER_ID)
