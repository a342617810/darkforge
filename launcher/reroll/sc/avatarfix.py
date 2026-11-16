# -*- coding: utf-8 -*-
"""幽影树化身被敌人随机搬到别的场地时，转入第三阶段前的保护（用户 2026-11-09：二阶段就死、战斗结束后血条还在）。
原版第二、三阶段的身体藏在约 89 米外；搬场地后都叠在场地中央，随机器又在开战时解除了本体的无敌。
二阶段血条打空后事件马上把本体和第三阶段的血条代理连上，约 8.5 秒后才显示血条，这段时间打到本体就会把代理打空、判定击败，
事件等完还会照常显示血条，之后再没有人关掉它。这里让本体从开战起一直无敌，到显示第三阶段血条的前一刻才解除。
要改的地图由重随写进 features.json 的 avatar_maps（rr/stage3.py）；事件靠随机器加的阶段标记 6951 和登场效果 20011443 认。"""
import os
import struct

import emevd
import erlib
from .common import last_with, vanilla

PHASE_MARK, ENTER_SP = 6951, 20011443


def rel_event(m):
    return os.path.join('event', m + '.emevd.dcx')


def maps(cx):
    return cx.feat.get('avatar_maps') or []


def sources(cx):
    return [p for p in (last_with(cx.sources, rel_event(m)) for m in maps(cx)) if p]


def _is(i, bank, iid):
    return (i['bank'], i['id']) == (bank, iid)


def patch(raw):
    """返回改好的事件文件；这张图里没有搬过来的化身（比如还在原来的场地）返回 None"""
    e = emevd.read(raw)
    phase, main = None, None
    for ev in e['events']:
        sp = [struct.unpack_from('<II', bytes(i['args']), 0) for i in ev['ins'] if _is(i, 2004, 8)]
        enter = [x for x, s in sp if s == ENTER_SP]
        if enter and any(s == PHASE_MARK for _x, s in sp):
            phase, main = ev, enter[0]
            break
    if phase is None:
        return None
    if phase.get('params'):
        raise RuntimeError('第三阶段事件 %d 带参数替换，插指令会错位' % phase['id'])
    off = [i for ev in e['events'] if ev is not phase for i in ev['ins']
           if _is(i, 2004, 15) and struct.unpack_from('<I', bytes(i['args']), 0)[0] == main and bytes(i['args'])[4] == 0]
    bars = [k for k, i in enumerate(phase['ins']) if _is(i, 2003, 11) and bytes(i['args'])[0] == 1]
    if not off or not bars:
        raise RuntimeError('事件 %d 对不上（解除无敌 %d 处、显示血条 %d 处）' % (phase['id'], len(off), len(bars)))
    phase['ins'].insert(bars[-1], dict(off[0]))
    for i in off:                                    # 只改取值不删指令，前面的跳过 / 跳转不用重算
        a = bytearray(i['args'])
        a[4] = 1
        i['args'] = bytes(a)
    return emevd.write(e)


def files(cx, tmp):
    for m in maps(cx):
        rel = rel_event(m)
        done = os.path.join(tmp, rel)
        src = done if os.path.isfile(done) else (last_with(cx.sources, rel) or vanilla(rel))
        try:
            if not src:
                raise RuntimeError('找不到事件文件')
            out = patch(erlib.dcx_decompress(open(src, 'rb').read()))
        except Exception as ex:                      # 改不上不影响别的功能
            cx.notes.append('幽影树化身 %s 的转阶段保护没加上：%s' % (m, ex))
            continue
        if out is None:
            continue
        os.makedirs(os.path.dirname(done), exist_ok=True)
        open(done, 'wb').write(erlib.dcx_compress_dflt(out, level=6))
