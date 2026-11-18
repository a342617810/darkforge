# -*- coding: utf-8 -*-
"""敌人随机把野兽司祭（黑剑玛利喀斯的第一形态）放到别的位置时，血量打空后补一个强制死亡（用户 2026-11-18
「修一下死亡难度以上艾尔登之兽位置的boss打了没正常结算的问题」）。
原版里它血量剩 55% 就变身，从来打不到 0；这个模型血量打空后不会自己倒下（原版玛利喀斯的击败事件 13002800 也是血量到 0 先强制死亡），
随机器在别的位置用的是「血量到 0 → 等它死了 → 结算」，它不死就一直卡着：没有击败、没有奖励，艾尔登之兽的位置还没有结局，重进要再打。
这里给每个位置加一个事件：血量到 0 后等 6 秒还在，就强制死亡（给卢恩）；已经死了的再强制死亡没有作用。随机器原来的结算事件照常接着走。
要改的位置由重随写进 features.json 的 clergy_spots（rr/enemies.py），每项 [地图, 实体]。"""
import os

import emevd
import erlib
from .common import last_with, vanilla

WAIT_SECS = 6.0
EV_BASE = 3960          # 事件编号 = 实体的前几位 + 3960 起：后四位 >= 2000 的标记读图 / 死亡 / 传送会清零，每次读图都再跑


def rel_event(m):
    return os.path.join('event', m + '.emevd.dcx')


def spots(cx):
    out = {}
    for m, ent in cx.feat.get('clergy_spots') or []:
        out.setdefault(str(m), []).append(int(ent))
    return out


def sources(cx):
    return [p for p in (last_with(cx.sources, rel_event(m)) for m in spots(cx)) if p]


def body(ent):
    return [
        emevd.ins(4, 14, ('s8', 0), ('u32', ent), ('s8', 5), ('s32', 0), ('s8', 0), ('f32', 1.0)),   # IF Character HP Value(MAIN, 实体, <=, 0)
        emevd.ins(1001, 0, ('f32', WAIT_SECS)),                                                    # WAIT Fixed Time (Seconds)
        emevd.ins(2004, 4, ('u32', ent), ('u8', 1)),                                               # Force Character Death(实体, 给卢恩)
    ]


def patch(raw, ents):
    """返回 (改好的事件文件, [(实体, 事件编号)])"""
    e = emevd.read(raw)
    ev0 = next((x for x in e['events'] if x['id'] == 0), None)
    if ev0 is None:
        raise RuntimeError('没有初始化事件 0')
    have = {x['id'] for x in e['events']}
    done = []
    for ent in ents:
        nid = ent // 10000 * 10000 + EV_BASE
        while nid in have:
            nid += 1
        if nid % 10000 < 2000 or nid // 10000 != ent // 10000:
            raise RuntimeError('实体 %d 找不到空的事件编号' % ent)
        have.add(nid)
        e['events'].append({'id': nid, 'rest': 0, 'ins': body(ent), 'params': []})
        ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', nid), ('u32', 0)))
        done.append((ent, nid))
    return emevd.write(e), done


def files(cx, tmp):
    for m, ents in sorted(spots(cx).items()):
        rel = rel_event(m)
        out_path = os.path.join(tmp, rel)
        src = out_path if os.path.isfile(out_path) else (last_with(cx.sources, rel) or vanilla(rel))
        try:
            if not src:
                raise RuntimeError('找不到事件文件')
            out, done = patch(erlib.dcx_decompress(open(src, 'rb').read()), ents)
        except Exception as ex:                      # 改不上不影响别的功能
            cx.notes.append('野兽司祭 %s 的强制死亡没加上：%s' % (m, ex))
            continue
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, 'wb').write(erlib.dcx_compress_dflt(out, level=6))
        cx.notes.append('野兽司祭 %s：%s 血量打空 %g 秒后还没倒下就强制死亡' % (
            m, '、'.join('%d（事件 %d）' % x for x in done), WAIT_SECS))
