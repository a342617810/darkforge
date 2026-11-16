# -*- coding: utf-8 -*-
"""额外的赐福（settings.json 的 extra_graces；用户 2026-10-30「在魔法学院大书库门口加一个赐福 位置参考golden age」）：
这里建传送用的 BonfireWarpParam 行和地名（PlaceName），features.json 的 extra_graces 告诉 sc/extragrace.py 去加地图部件和登记事件。
现在一个：雷亚卢卡利亚学院「大书库门前」，全部照 Golden Age 3.6.8（行 140004、传送标记 71404、地名 140004、
资产实体 14001954、点燃标记 14000004）；行照同一张图的 140003（校舍内的教室）复制，只换下面这几项。
地图坐标（posX/Y/Z）用资产的实际位置（原版 140000 也是这样；Golden Age 写的 14, -45 和资产对不上）。"""
from .common import *  # noqa: F401,F403

GRACES = [dict(key='raya_library', map='m14_00_00_00', row=140004, copy=140003, warp_flag=71404, lit_flag=14000004,
               asset=14001954, pos=(99.15069580078125, 154.11599731445312, -47.68484115600586), sort=40, text=140004,
               name={'zh': '大书库门前', 'en': 'In Front of the Grand Library'})]


def enabled(S):
    return bool((S.get('extra_graces') or {}).get('enabled', True))


def build(ctx):
    if not enabled(ctx.S):
        return
    lay, size = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'BonfireWarpParam.xml')))
    off = {n: (o, fc) for n, fc, o, *_ in lay}
    put = lambda row, n, v: struct.pack_into('<' + off[n][1], row, off[n][0], v)
    get = lambda row, n: struct.unpack_from('<' + off[n][1], row, off[n][0])[0]
    P = erlib.Param(ctx.bnd.get('BonfireWarpParam.param'))
    if P.row_size != size:
        raise RuntimeError('额外赐福：BonfireWarpParam 行大小 %d 和定义 %d 对不上' % (P.row_size, size))
    flags = {get(r, 'eventflagId') for r in P.rows.values()}
    made = []
    for g in GRACES:
        if g['row'] in P.rows or g['copy'] not in P.rows or g['warp_flag'] in flags:
            raise RuntimeError('额外赐福 %s：行 %d 已被占用 / 缺少模板行 %d / 传送标记 %d 已被占用' % (g['key'], g['row'], g['copy'], g['warp_flag']))
        row = bytearray(P.rows[g['copy']])
        for f, v in (('eventflagId', g['warp_flag']), ('bonfireEntityId', g['asset']), ('textId1', g['text']),
                     ('bonfireSubCategorySortId', g['sort']), ('posX', g['pos'][0]), ('posY', g['pos'][1]), ('posZ', g['pos'][2])):
            put(row, f, v)
        P.add_row(g['row'], bytes(row))
        made.append({k: g[k] for k in ('key', 'map', 'lit_flag', 'asset')})
    ctx.bnd.put('BonfireWarpParam.param', P.serialize())
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        hdr, ents = erlib.read_fmg_full(mb.get('PlaceName.fmg'))
        d = dict(ents)
        d.update({g['text']: g['name'][lang] for g in GRACES})
        mb.put('PlaceName.fmg', erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.features['extra_graces'] = made
    ctx.report.append('额外赐福：%s（传送行 %s；地图部件和登记事件在游戏脚本覆盖包里加，sc/extragrace.py）'
                      % ('、'.join(g['name']['zh'] for g in GRACES), ' / '.join(str(g['row']) for g in GRACES)))
