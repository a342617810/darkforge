# -*- coding: utf-8 -*-
"""事件脚本放音效（编号和标记由 rr/sounds.py 分好，features.json 的 sounds）：公共事件 SOUND_EVENT 每帧看一遍这几个标记，
亮着的在玩家身上放它的音效（2010:2 PlaySE，实体 10000）、熄灭；dark_core 要放就点亮（相杀：防御火花出现时）。"""
import emevd

SOUND_EVENT = 1040490880          # 不存档的 1040490 块（dev\event_flags\说明.md）
PLAYER = 10000


def on(cx):
    return cx.feat.get('sounds')


def events(cx, e, ev0):
    f = on(cx)
    if not f or any(ev['id'] == SOUND_EVENT for ev in e['events']):
        return
    body = []
    for flag, ty, sid in f['list']:
        body += [emevd.ins(1003, 1, ('u8', 2), ('u8', 0), ('u8', 0), ('u32', int(flag))),          # 标记没亮：跳过下面两行
                 emevd.ins(2010, 2, ('u32', PLAYER), ('s32', int(ty)), ('s32', int(sid))),
                 emevd.ins(2003, 66, ('u8', 0), ('u32', int(flag)), ('u8', 0))]
    body += [emevd.ins(1001, 1, ('s32', 1)), emevd.ins(1000, 4, ('u8', 1))]                       # 等一帧，重新开始
    e['events'].append({'id': SOUND_EVENT, 'rest': 0, 'ins': body, 'params': []})
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', SOUND_EVENT), ('u32', 0)))
