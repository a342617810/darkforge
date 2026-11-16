# -*- coding: utf-8 -*-
"""原版闪烁提示的公共事件和文字（编号和文字由 rr/notes.py 分好，features.json 的 notes；用户 2026-11-03：夺取魇火的提示用原版提示框）。
dark_core（notes.rs）把编号按位写进 bits 这几个标记，这里的公共事件 NOTE_EVENT：
  每 0.25 秒看一次，一位都没亮 → 重新开始；
  有亮的 → 按编号逐个对：每个编号一段（每一位不对就跳到下一段），对上的显示 EventTextForMap 的 text0 + 编号（2007:4，原版
  「某处的沉重门扉已敞开。」那种提示），等 3 秒、全部熄灭、重新开始；都没对上（不认识的编号）也全部熄灭。
dark_core 等这几位全灭了才写下一条，所以提示一条接一条、不会互相顶掉。
读档时先全部熄灭再开始等：这几个标记会存档，正在显示时退出游戏，下次读档会把那条再显示一遍
（用户 2026-11-05「没有错配时错配的闪烁提示还会残留几秒」：错配时重启提示不停地闪，退出时几乎一定亮着）。
熄灭单独一个事件 CLEAR_EVENT（读档时跑一次），循环靠「重新开始」：不能写成同一个事件里「开头熄灭 + 标签 + 往回跳」，EMEVD 的 Goto 只能往后跳
（原版几千条没有一条往回的），那样事件跑一圈就结束，之后写进来的编号没人显示也没人熄灭，提示全部卡住（13:23 ~ 用户报夺取魇火没提示，v0.9.3 / v0.9.4 都带着）。"""
import emevd

NOTE_EVENT = 1040490870          # 不存档的 1040490 块（dev\event_flags\说明.md）
CLEAR_EVENT = 1040490871         # 读档时熄灭一次
SHOW_SECS = 3.0


def on(cx):
    return cx.feat.get('notes')


def events(cx, e, ev0):
    f = on(cx)
    if not f or any(ev['id'] == NOTE_EVENT for ev in e['events']):
        return
    bits, t0, n = [int(b) for b in f['bits']], int(f['text0']), len(f['zh'])
    if bits != list(range(bits[0], bits[0] + len(bits))) or n >= 1 << len(bits):
        raise RuntimeError('原版提示：标记要连号、编号要放得下（%d 位、%d 条）' % (len(bits), n))
    nb = len(bits)
    skip = lambda lines, state, flag: emevd.ins(1003, 1, ('u8', lines), ('u8', state), ('u8', 0), ('u32', flag))   # 标记是 state 就跳过 lines 行
    clear = emevd.ins(2003, 22, ('u32', bits[0]), ('u32', bits[-1]), ('u8', 0))
    restart = emevd.ins(1000, 4, ('u8', 1))
    body = [skip(nb - 1 - i + 2, 1, b) for i, b in enumerate(bits)]                  # 有一位亮着：跳过等待，去下面按编号分
    body += [emevd.ins(1001, 0, ('f32', 0.25)), restart]
    for v in range(1, n + 1):
        body += [skip(nb - 1 - i + 4, 0 if (v >> i) & 1 else 1, b) for i, b in enumerate(bits)]   # 这一位不对：跳到下一段
        body += [emevd.ins(2007, 4, ('s32', t0 + v)), emevd.ins(1001, 0, ('f32', SHOW_SECS)), clear, restart]
    body += [clear, restart]
    e['events'].append({'id': CLEAR_EVENT, 'rest': 0, 'ins': [clear], 'params': []})   # 读档：熄掉存档里残留的编号（排在循环前面初始化）
    e['events'].append({'id': NOTE_EVENT, 'rest': 0, 'ins': body, 'params': []})
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', CLEAR_EVENT), ('u32', 0)))
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', NOTE_EVENT), ('u32', 0)))


def texts(cx, key):
    f = on(cx)
    if not f:
        return {}
    rows = f['zh'] if key == 'zh' else f['en']
    return {'EventTextForMap': {int(f['text0']) + v + 1: t for v, t in enumerate(rows)}}
