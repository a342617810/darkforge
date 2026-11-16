# -*- coding: utf-8 -*-
"""开局说明书（settings 的 mod_manuals；v0.2 加的，新装备系统重写了内容）：「说明书」道具，背包里按确认键看说明。
  - 道具 GOODS0 起按 data\\manuals.json 的顺序（最多 7 本，9150 起被原版占了）：格式照抄原版「说明：赐福」（道具 TEMPLATE，类型 12）；
  - 每本一张掉落表 LOT0 + 2 × 第几本（只有这一本、没有获取标记；隔一个编号，不连成一条链）；
  - 游戏脚本（sc/start.py）进游戏时看背包，缺哪本补哪本：新角色一进游戏就有，老角色也补上，卖掉 / 丢掉了下次进游戏再给。
  - 2026-10-30 起只剩一本「欢迎游玩」，各项说明挪进赐福菜单「Dark Reforged 说明」（sc/guide.py）。以前发过的另外几本（到 GOODS0 + OLD_BOOKS - 1）
    道具行照样留着（老存档里还有），文字改成「已经挪到赐福菜单」；sc/start.py 进游戏时从背包里收走（features 的 retired）。
文字在这里直接写进 item_dlc02（GoodsName / GoodsInfo / GoodsCaption）"""
from .common import *  # noqa: F401,F403
from .unidentified import blank_row

TEMPLATE, GOODS0, MAX_BOOKS, SORT0 = 9100, 9143, 7, 460200
OLD_BOOKS = 7                      # v0.7 以前发过的本数（9143~9149）
LOT0 = 10010050
INFO = {'zh': '关于“%s”的说明\n按下<?keyicon@31?>能确认内容', 'en': 'About %s\nPress <?keyicon@31?> to read'}
RETIRED = {'zh': {'name': '说明书（旧）', 'topic': '暗黑重铸',
                  'text': '这本说明书的内容已经挪到赐福菜单的「暗黑重铸说明」里。\n进游戏时会自动收走。'},
           'en': {'name': 'Manual (old)', 'topic': 'Darkforge',
                  'text': 'The contents of this manual have moved to "Darkforge Guide" in the Site of Grace menu.\n'
                          'It is removed automatically when you load in.'}}


def build(ctx):
    if not ctx.S.get('mod_manuals', True):
        return
    M = json.load(open(os.path.join(ctx.data_dir, 'manuals.json'), encoding='utf-8'))
    n = len(M['zh'])
    if n > MAX_BOOKS or len(M['en']) != n:
        raise RuntimeError('说明书：data\\manuals.json 中英文本数不一样或超过 %d 本' % MAX_BOOKS)
    lg = {k: (o, fc) for k, fc, o, *_ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))[0]}
    G = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    P = ctx.P_mp
    goods = [GOODS0 + k for k in range(n)]
    retired = []                       # 以前的旧说明书不再保留 / 收走（用户 2026-11-10「旧书不用管了」）
    lots = [LOT0 + 2 * k for k in range(n)]
    if TEMPLATE not in G.rows or any(i in G.rows for i in goods + retired):
        raise RuntimeError('说明书：缺少原版说明道具 %d，或道具编号 %d~%d 已被占用' % (TEMPLATE, GOODS0, GOODS0 + max(n, OLD_BOOKS) - 1))
    if any(i in P.rows for i in range(LOT0 - 1, lots[-1] + 2)):
        raise RuntimeError('说明书：掉落表 %d~%d 已被占用' % (LOT0 - 1, lots[-1] + 1))
    for k, i in enumerate(goods + retired):
        row = bytearray(G.rows[TEMPLATE])
        struct.pack_into('<' + lg['sortId'][1], row, lg['sortId'][0], SORT0 + k)
        G.add_row(i, bytes(row))
    for k, i in enumerate(goods):
        lot = blank_row(P.rows[min(P.rows)], P.row_size)
        erlib.lot_set_slot(lot, 0, 1, i, 1000, num=1, luck=False, slotflag=0)
        struct.pack_into('<I', lot, erlib.LOT_FLAG, 0)
        P.add_row(lots[k], lot)
    ctx.bnd.put('EquipParamGoods.param', G.serialize())
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        books = list(zip(goods, M[lang])) + [(i, RETIRED[lang]) for i in retired]
        for fmg, key in (('GoodsName.fmg', 'name'), ('GoodsInfo.fmg', None), ('GoodsCaption.fmg', 'text')):
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            for i, m in books:
                d[i] = m[key] if key else INFO[lang] % m['topic']
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.features['manuals'] = {'goods': goods, 'lots': lots, 'retired': retired}
    ctx.report.append('开局说明书：%d 本（道具 %d~%d：%s），进游戏时背包里缺哪本补哪本（掉落表 %d 起，隔一个编号一本）%s' % (
        n, goods[0], goods[-1], '、'.join(m['topic'] for m in M['zh']), LOT0,
        '；以前的 %d~%d 留着道具行，进游戏时收走' % (retired[0], retired[-1]) if retired else ''))
