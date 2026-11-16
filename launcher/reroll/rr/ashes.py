# -*- coding: utf-8 -*-
"""骨灰一次性打乱（spirit_ashes_shuffle）：所有骨灰（道具类型 7 / 8，只看没强化的本体）在它们原来的获取格之间换位置——
地图掉落（Boss、宝箱、地上、尸体……，不含 RNG Lands 许愿池 200000~527670）和商店格（价格跟着格子），每种还是都拿得到。
第一次重随时抽一次，记进配方文件的 once/ashes，以后启动原样还原，点「一次性重随」才重抽。"""
from .common import *  # noqa: F401,F403
from . import once

WISH = (200000, 527670)


def shuffle(ctx):
    if not ctx.S.get('spirit_ashes_shuffle', True):
        return
    if ctx.item_rand:
        ctx.report.append('骨灰：随机器开着物品随机，已经打乱过了，这里不再打乱')
        return
    lg, gsize = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))
    ls, ssize = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'ShopLineupParam.xml')))
    G = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    P_shop = erlib.Param(ctx.bnd.get('ShopLineupParam.param'))
    if G.row_size != gsize or P_shop.row_size != ssize:
        raise RuntimeError('EquipParamGoods / ShopLineupParam 行大小与字段表不符')
    gt = {n: (o, fc) for n, fc, o, *_ in lg}['goodsType']
    ash = {k for k, r in G.rows.items() if struct.unpack_from('<' + gt[1], r, gt[0])[0] in (7, 8) and k % 100 == 0}
    soff = {n: (o, fc) for n, fc, o, *_ in ls}
    sget = lambda r, n: struct.unpack_from('<' + soff[n][1], r, soff[n][0])[0]
    P_mp = ctx.P_mp
    restored = getattr(ctx, 'npc_restored', set())      # NPC 支线还原过的格子不打乱（world.npc_quest_vanilla）
    slots = [('m', r, i, iid) for r in sorted(P_mp.rows) if not WISH[0] <= r <= WISH[1] and r not in restored
             for i, c, iid, _pt in erlib.lot_slots(P_mp.rows[r]) if c == 1 and iid in ash]
    slots += [('s', r, 0, sget(P_shop.rows[r], 'equipId')) for r in sorted(P_shop.rows)
              if sget(P_shop.rows[r], 'equipType') == 3 and sget(P_shop.rows[r], 'equipId') in ash]
    if len(slots) < 2:
        return
    key = once.sig([(t, r, i, iid) for t, r, i, iid in slots])
    plan = once.get(ctx, 'ashes', key)
    fresh = plan is None
    if fresh:
        with once.own_rng(ctx, 'ashes'):
            perm = [iid for *_x, iid in slots]
            ctx.rng.shuffle(perm)
            plan = {'%s%d:%d' % (t, r, i): g for (t, r, i, _iid), g in zip(slots, perm)}
        once.put(ctx, 'ashes', key, plan)
    moved = 0
    o, fc = soff['equipId']
    for t, r, i, iid in slots:
        g = int(plan.get('%s%d:%d' % (t, r, i), iid))
        if t == 'm':
            struct.pack_into('<i', P_mp.rows[r], erlib.LOT_ID + 4 * i, g)
        else:
            struct.pack_into('<' + fc, P_shop.rows[r], o, g)
        moved += g != iid
    ctx.bnd.put('ShopLineupParam.param', P_shop.serialize())
    ctx.report.append('骨灰（一次性重随，%s）：%d 种骨灰在原来的 %d 个获取格（地图 %d、商店 %d）之间打乱，%d 格换了东西' % (
        '这次新抽' if fresh else '沿用第一次抽的', len({s[3] for s in slots}), len(slots),
        sum(1 for s in slots if s[0] == 'm'), sum(1 for s in slots if s[0] == 's'), moved))
