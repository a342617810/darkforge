# -*- coding: utf-8 -*-
"""开局送的东西（公共事件，进游戏时检查）：
  灵马 / 解锁赐福升级（settings.json 的 start_torrent / start_level_up）：没拿过灵马哨笛（原版掉落表 WHISTLE_LOT，拿到点亮 WHISTLE_FLAG）
    就发一次；点亮梅琳娜契约标记 ACCORD_FLAG（赐福菜单的「升级」就看这个标记）。和原版接受契约时给的一样，梅琳娜那边不会再给第二把哨笛；
  召魂铃（rr/world.py 建的掉落表，features.json 的 spirit_bell_lot，获取标记就是原版召魂铃的 SPIRIT_BELL_FLAG）：没有就发一次；
  补标记（features.json 的 flag_repair，rr/bosses.py reuse_flag）：Boss 奖励链里原版「只点标记」的行以前被我们占掉了（蕾娜菈的 177：
    无缘诞生者的大卢恩靠它算进大卢恩数量），链开头的标记亮着就补点（用户 2026-11-01）；
  说明书（rr/manuals.py，features.json 的 manuals：道具和掉落表，掉落表没有获取标记）：每本看背包，没有就发（新老角色都补，卖掉了下次再给）；
    retired（挪进赐福菜单的旧说明书）：背包里有就收走
开局遗物（rr/startgear.py 换成了护符，features.json 的 keepsakes）：角色创建界面里遗物的名字 / 说明写进 GR_MenuText / GR_LineHelp"""
import emevd

START_EVENT, WHISTLE_LOT, WHISTLE_FLAG, ACCORD_FLAG = 1040490750, 100000, 60100, 4680
SPIRIT_BELL_FLAG = 60110
MANUAL_EVENT = 1040490740
ITEM_GOODS, AND_01 = 3, 1               # EMEVD 物品类别（IF Player Has/Doesn't Have Item 3[4]）：道具；条件组 AND_01


def events(cx, e, ev0):
    torrent, level_up = bool(cx.S.get('start_torrent', True)), bool(cx.S.get('start_level_up', True))
    bell = cx.feat.get('spirit_bell_lot')
    repair = cx.feat.get('flag_repair') or []
    if (torrent or level_up or bell or repair) and not any(ev['id'] == START_EVENT for ev in e['events']):
        body = [emevd.ins(1001, 0, ('f32', 2.0))]
        if torrent:
            body += [emevd.ins(1003, 1, ('u8', 1), ('u8', 1), ('u8', 0), ('u32', WHISTLE_FLAG)),           # 拿过哨笛就跳过
                     emevd.ins(2003, 4, ('s32', WHISTLE_LOT))]
        if bell:
            body += [emevd.ins(1003, 1, ('u8', 1), ('u8', 1), ('u8', 0), ('u32', SPIRIT_BELL_FLAG)),       # 已经有召魂铃就跳过
                     emevd.ins(2003, 4, ('s32', bell))]
        if level_up:
            body += [emevd.ins(2003, 66, ('u8', 0), ('u32', ACCORD_FLAG), ('u8', 1))]
        for f0, f in repair:                         # Boss 奖励链里被占掉的「只点标记」行：链开头的标记亮了就补点它（rr/bosses.py reuse_flag）
            body += [emevd.ins(1003, 1, ('u8', 1), ('u8', 0), ('u8', 0), ('u32', f0)),          # 没拿过这条奖励就跳过
                     emevd.ins(2003, 66, ('u8', 0), ('u32', f), ('u8', 1))]
        e['events'].append({'id': START_EVENT, 'rest': 0, 'ins': body, 'params': []})
        ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', START_EVENT), ('u32', 0)))
    books = cx.feat.get('manuals') or {}
    if books.get('goods') and not any(ev['id'] == MANUAL_EVENT for ev in e['events']):
        body = [emevd.ins(1001, 0, ('f32', 3.0))]
        for k, (goods, lot) in enumerate(zip(books['goods'], books['lots'])):
            grp = AND_01 + k                                                               # 每本一个条件组（条件会累加）
            body += [emevd.ins(3, 4, ('s8', grp), ('u8', ITEM_GOODS), ('s32', goods), ('u8', 1)),
                     emevd.ins(1000, 1, ('u8', 1), ('s8', 1), ('s8', grp)),                 # 背包里有这本：跳过下一行
                     emevd.ins(2003, 4, ('s32', lot))]
        n = len(books['goods'])
        if n + len(books.get('retired') or ()) > 7:
            raise RuntimeError('说明书：要看的道具超过 7 个条件组')
        for k, goods in enumerate(books.get('retired') or ()):                             # 挪进赐福菜单的旧说明书：有就收走
            grp = AND_01 + n + k
            body += [emevd.ins(3, 4, ('s8', grp), ('u8', ITEM_GOODS), ('s32', goods), ('u8', 1)),
                     emevd.ins(1000, 1, ('u8', 1), ('s8', 0), ('s8', grp)),                 # 背包里没有：跳过下一行
                     emevd.ins(2003, 24, ('u8', ITEM_GOODS), ('s32', goods), ('s32', 1))]   # RemoveItemFromPlayer(道具, 编号, 1 个)
        e['events'].append({'id': MANUAL_EVENT, 'rest': 0, 'ins': body, 'params': []})
        ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', MANUAL_EVENT), ('u32', 0)))


def texts(cx, key):
    """开局遗物的名字 / 说明；职业介绍里换掉的开局武器名字（rr/startgear.py 的 class_text）"""
    ks = (cx.feat.get('keepsakes') or {}).get(key) or {}
    cls = (cx.feat.get('class_text') or {}).get(key) or {}
    out = {}
    if ks:
        out['GR_MenuText'] = {int(cid): v[0] for cid, v in ks.items()}
        out['GR_LineHelp'] = {int(cid): v[1] for cid, v in ks.items()}
    if cls:
        out.setdefault('GR_LineHelp', {}).update({int(cid): t for cid, t in cls.items()})
    return out
