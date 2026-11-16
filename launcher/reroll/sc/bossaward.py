# -*- coding: utf-8 -*-
"""Boss 奖励事件发放（表由 rr/bossaward.py 建，features.json 的 boss_award = [[击败标记, 掉落表], …]）。
一个带参数的公共事件，每张表初始化一个槽位：先等击败标记灭，再等它亮，亮了发奖励，然后重新开始。
先等灭：读档时已经亮着的（以前打过的）不会补发；Boss 复活后击败标记熄灭，再打一次还会走到发放，但每行有自己的获取标记，拿过的不重复。
循环靠「重新开始」（1000:4）：EMEVD 的 Goto 只能往前跳（见 sc/notes.py）。事件编号在不存档的 1040490 块：事件编号 + 槽位会被点亮成标记，不能落在会存档的块，
也不能碰到别的事件编号，所以分两段：881~959（880 是音效事件，960 是发货事件）、961~999。"""
import emevd

EVENTS = ((1040490881, 79), (1040490961, 39))     # (事件编号, 槽位数)


def events(cx, e, ev0):
    award = cx.feat.get('boss_award')
    if not award or any(ev['id'] == EVENTS[0][0] for ev in e['events']):
        return
    if len(award) > sum(n for _i, n in EVENTS):
        raise RuntimeError('Boss 奖励事件发放：%d 张表，超过 %d 个槽位' % (len(award), sum(n for _i, n in EVENTS)))
    wait = lambda state: emevd.ins(3, 0, ('s8', 0), ('u8', state), ('u8', 0), ('u32', 0))
    k = 0
    for eid, slots in EVENTS:
        part = award[k:k + slots]
        k += slots
        if not part:
            break
        body = [wait(0), wait(1), emevd.ins(2003, 4, ('s32', 0)), emevd.ins(1000, 4, ('u8', 1))]
        # 参数替换：(指令序号, 指令参数里的位置, 初始化参数里的位置, 字节数, 0)
        e['events'].append({'id': eid, 'rest': 0, 'ins': body, 'params': [(0, 4, 0, 4, 0), (1, 4, 0, 4, 0), (2, 0, 4, 4, 0)]})
        for slot, (flag, lot) in enumerate(part):
            ev0['ins'].append(emevd.ins(2000, 0, ('s32', slot), ('u32', eid), ('u32', int(flag)), ('s32', int(lot))))
    cx.notes.append('Boss 奖励事件发放：%d 张表' % len(award))
