# -*- coding: utf-8 -*-
"""Boss 模组的场地 → 敌人随机的高难度世界（dev\\boss_mods\\README.md；features.json 的 boss_mods.arena_port）。

不开敌人随机时场地是做好的成品（data\\bossmods\\<键>\\arena），启动器直接挂，这里不管。
敌人随机时：高难度世界（randomizer_hi，一键重随敌人时随机器多跑的一遍）里整合了改版的 Boss 留在原位，但同一张图上别的敌人
随机过，这张图的事件 / 地图是随机器写的，要在它上面移植：
- 事件：成品里的新事件照抄；作者在原版事件里插了几句的那几个（replace_events），只有随机器那份和原版一模一样时才换成成品里的，
  不一样就整个场地不移植（启动日志说一句），免得冲掉随机器的改动；构造事件 0 里加新事件的初始化。
- 地图：在最后生效的那份上（重随修补过的 out\\reroll_maps 或随机器输出）按名字拷成品里的部件
  （dev\\boss_mods\\msbport，和额外赐福一样用随机器单文件包里的 SoulsFormats，sc/extragrace.py 的 tool()）。
结果写进游戏脚本覆盖包（最后加载）。移植不上不影响别的功能（只是没有新阶段 / 召唤，Boss 的新动作照样在）。"""
import difflib
import hashlib
import json
import os
import shutil
import struct
import subprocess

import emevd
import erlib

from . import extragrace
from .common import DATA, REROLL, last_with, vanilla

CACHE_DIR = os.path.join(REROLL, 'cache', 'bossarena')
ENABLE = (2004, 5)        # 事件指令 Change Character Enable State(实体 / 实体组, 开关)


def enabled_ids(raw_ev):
    """解压后的事件里被「启用」（Change Character Enable State 开）过的实体 / 实体组"""
    out = set()
    for ev in emevd.read(raw_ev)['events']:
        for i in ev['ins']:
            if (i['bank'], i['id']) == ENABLE and len(i['args']) >= 5:
                ent, on = struct.unpack_from('<iB', i['args'])
                if on:
                    out.add(ent)
    return out


def part_entities(raw, names):
    """解压后的 MSBE：names 这些部件的 (实体编号, 实体组)（实体数据偏移在部件 +0x60，实体编号在它 +0，8 个实体组在它 +0x1C）"""
    out, pos = {}, 0x10
    while pos:
        cnt = struct.unpack_from('<i', raw, pos + 4)[0]
        noff = struct.unpack_from('<q', raw, pos + 8)[0]
        offs = struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16)
        nxt = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
        if erlib._u16str(raw, noff) == 'PARTS_PARAM_ST':
            for o in offs:
                nm = erlib._u16str(raw, o + struct.unpack_from('<q', raw, o)[0])
                if nm in names:
                    eo = o + struct.unpack_from('<q', raw, o + 0x60)[0]
                    out[nm] = (struct.unpack_from('<i', raw, eo)[0], {g for g in struct.unpack_from('<8i', raw, eo + 0x1C) if g})
        pos = nxt
    return out


HIDE_WAIT_FRAMES = 2


def hide_stray(ev_raw, ar, k, notes=None):
    """移植后的事件里会被「整组启用」、模组自己的事件里从不启用的实体组，拷过去的部件（有自己的实体编号）又在这组里：
    加一个事件，读图后等几帧把这些部件按实体关掉（随机器版初始化事件读图第 0 帧整组启用；之后模组的事件照常按实体开关）。
    不把部件移出这组：Boss 打败后随机器靠整组关掉它们。用户 2026-11-14「为什么有随机开局就被启用了呢」：拉卡德的两把剑
    16000802 / 03 在 Boss 组 16005800 里，随机器版 16002810 开场整组启用，剑一开场就出来；米德拉的分身 28000805~07 同理"""
    if not ar.get('parts'):
        return ev_raw
    stray = enabled_ids(ev_raw) - enabled_ids(erlib.dcx_decompress(open(arena_file(k, rel_event(ar['map'])), 'rb').read()))
    if not stray:
        return ev_raw
    # keep_parts：模组设计里开场就该在的（拉卡德的剑，用户 2026-11-14「让那把剑就开始就出来 分身不用」），不关
    parts = part_entities(erlib.dcx_decompress(open(arena_file(k, rel_map(msb_of(ar))), 'rb').read()), set(ar['parts']) - set(ar.get('keep_parts') or []))
    hit = sorted((ent, nm, sorted(gs & stray)) for nm, (ent, gs) in parts.items() if ent > 0 and gs & stray)
    if not hit:
        return ev_raw
    e = emevd.read(ev_raw)
    have = {x['id'] for x in e['events']}
    # 事件编号也是它的标记（做完会点亮）：放在这张图的 xxxx3900 起，后四位 >= 2000 的标记死亡 / 读档 / 传送就清零，每次读图都会再跑
    nid = max(ar.get('new_events') or ar.get('events') or [0]) // 10000 * 10000 + 3900
    while nid in have:
        nid += 1
    if nid % 10000 < 2000:
        raise RuntimeError('找不到读图后关部件的事件编号')
    body = [emevd.ins(1001, 1, ('s32', HIDE_WAIT_FRAMES))] + [emevd.ins(2004, 5, ('s32', ent), ('u8', 0)) for ent, _nm, _g in hit]
    e['events'].append({'id': nid, 'rest': 0, 'ins': body, 'params': []})
    ev0 = next(x for x in e['events'] if x['id'] == 0)
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', nid), ('u32', 0)))
    if notes is not None:
        notes.append('部件 %s 在随机器会整组启用的实体组 %s 里，加事件 %d 读图后关掉（不然一开场就出来）' % (
            '、'.join(nm for _e, nm, _g in hit), '、'.join(str(g) for g in sorted({g for *_x, gs in hit for g in gs})), nid))
    return emevd.write(e)


def ports(cx):
    """[(键, mod.json 的 arena)]"""
    out = []
    for k in ((cx.feat.get('boss_mods') or {}).get('arena_port') or []):
        p = os.path.join(DATA, 'bossmods', k, 'mod.json')
        if os.path.isfile(p):
            ar = json.load(open(p, encoding='utf-8')).get('arena')
            if ar:
                out.append((k, ar))
    return out


def rel_map(m):
    return os.path.join('map', 'mapstudio', m + '.msb.dcx')


def rel_event(m):
    return os.path.join('event', m + '.emevd.dcx')


def msb_of(ar):
    """部件放在哪张地图（开放世界的 Boss：事件在小地块，部件可能在大地块）"""
    return ar.get('msb_map') or ar['map']


def arena_file(k, rel):
    return os.path.join(DATA, 'bossmods', k, 'arena', rel)


def sources(cx):
    out = []
    for k, ar in ports(cx):
        m = ar['map']
        out += [last_with(cx.sources, rel_event(m)), arena_file(k, rel_event(m))]
        if ar.get('parts'):                          # 只移植事件的（没有要拷的部件）不看地图
            out += [last_with(cx.sources, rel_map(msb_of(ar))), arena_file(k, rel_map(msb_of(ar)))]
    return [p for p in out if p]


def _sig(ev):
    return [(i['bank'], i['id'], i['args'], i['layer']) for i in ev['ins']] if ev else None


def appended(v, r):
    """随机器那份 = 原版 + 末尾追加的几条（参数替换也一样）时返回追加的那几条，否则 None"""
    if not v or not r or v['params'] != r['params'] or v['ins'] and any(i['layer'] is not None for i in r['ins'][len(v['ins']):]):
        return None
    n = len(v['ins'])
    if len(r['ins']) <= n or _sig(dict(r, ins=r['ins'][:n])) != _sig(v):
        return None
    return list(r['ins'][n:])


FLOW_BANKS = (1000, 1001, 1003, 1005, 1014)        # 跳转 / 等待 / 标签类（SKIP 的行数、GOTO 的标签会被增删行打乱）


def merge3(v, d, r):
    """原版 v、成品（模组版）d、随机器那份 r：随机器只改了几条指令的参数（条数不变）、模组只删 / 插 / 换了别的指令时，
    在随机器那份上做模组的改动；对不上或者事件里有跳转类指令（行数会错位）返回 None"""
    if not v or not d or not r or v['params'] != r['params'] or len(v['ins']) != len(r['ins']):
        return None
    if any(i['bank'] in FLOW_BANKS for e in (v, d, r) for i in e['ins']):
        return None
    sig = lambda i: (i['bank'], i['id'], i['args'], i['layer'])
    rch = {k for k, (a, b) in enumerate(zip(v['ins'], r['ins'])) if sig(a) != sig(b)}
    if any((a['bank'], a['id']) != (b['bank'], b['id']) for a, b in zip(v['ins'], r['ins'])):
        return None                                  # 随机器换了指令种类：不是只改参数
    out = list(r['ins'])
    ops = difflib.SequenceMatcher(None, [sig(i) for i in v['ins']], [sig(i) for i in d['ins']], autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in reversed(ops):        # 倒着做，前面的下标不变
        if tag == 'equal':
            continue
        if tag == 'replace' and rch & set(range(i1, i2)):
            return None                              # 两边改了同一条
        out[i1:i2] = d['ins'][j1:j2]                 # 删（j1 == j2）、插（i1 == i2）、换
    return dict(d, ins=out)


def port_events(src_raw, ar, k, notes=None):
    """随机器写的事件（解压后）+ 成品里移植的事件 → 新的事件（解压后）。新事件放不进去抛 RuntimeError；
    作者在原版事件里插了几句的那几个（replace_events），随机器那份和原版不一样时只跳过那一个（notes 里记一句，新阶段照样移植）"""
    e = emevd.read(src_raw)
    done = emevd.read(erlib.dcx_decompress(open(arena_file(k, rel_event(ar['map'])), 'rb').read()))
    van_p = vanilla(rel_event(ar['map']))
    if not van_p:
        raise RuntimeError('拿不到原版的 %s 事件' % ar['map'])
    van = {x['id']: x for x in emevd.read(erlib.dcx_decompress(open(van_p, 'rb').read()))['events']}
    E = {x['id']: x for x in e['events']}
    D = {x['id']: x for x in done['events']}
    changed = list(ar['replace_events']) + list(ar.get('mod_events') or [])
    if any(i['layer'] is not None for eid in ar['new_events'] + changed for i in D[eid]['ins']):
        raise RuntimeError('移植的事件里有分层指令（还没做）')
    for eid in ar['new_events']:
        if eid in E:
            raise RuntimeError('随机器那份里已经有事件 %d' % eid)
    replaced = []
    for eid in changed:
        if eid in E and (eid in (ar.get('force_events') or ()) or _sig(E[eid]) == _sig(van.get(eid))):
            e['events'][e['events'].index(E[eid])] = D[eid]
            replaced.append(eid)
            continue
        tail = appended(van.get(eid), E.get(eid))
        merged = None if tail is not None else merge3(van.get(eid), D[eid], E.get(eid))
        if tail is not None:
            # 随机器只在末尾加了几句（Boss 击败事件末尾的存档请求）：模组版 + 这几句，不影响前面的跳转行数
            e['events'][e['events'].index(E[eid])] = dict(D[eid], ins=list(D[eid]['ins']) + tail)
            replaced.append(eid)
        elif merged is not None:
            # 随机器只改了几条指令的参数、模组改的是别的指令（例如玛莲妮亚删掉原版 BGM 那一句）：两边都留
            e['events'][e['events'].index(E[eid])] = merged
            replaced.append(eid)
        elif notes is not None:
            notes.append('事件 %d 随机器改过，模组的改动没加' % eid)
    for eid in ar['new_events']:
        e['events'].append(D[eid])
    ev0 = next(x for x in e['events'] if x['id'] == 0)
    # 换上的事件：构造事件里它的初始化跟成品走（模组改了参数 / 份数、或者不再初始化）。一样就不动
    sig3 = lambda i: (i['bank'], i['id'], i['args'])
    inits = lambda ins, eid: [i for i in ins if i['bank'] == 2000 and i['id'] in (0, 6) and len(i['args']) >= 8 and
                              struct.unpack_from('<i', i['args'], 4)[0] == eid]
    for eid in replaced:
        a, b = inits(ev0['ins'], eid), inits(D[0]['ins'], eid)
        if sorted(map(sig3, a)) != sorted(map(sig3, b)):
            ev0['ins'] = [i for i in ev0['ins'] if i not in a] + b
    have = {(i['bank'], i['id'], i['args']) for i in ev0['ins']}
    want = set(ar.get('ev0_ints') or [])                 # 构造事件里模组新加的别的指令（例如新赐福的登记），参数里带这些数
    for i in D[0]['ins']:
        if (i['bank'], i['id'], i['args']) in have or len(i['args']) < 4:
            continue
        nums = struct.unpack_from('<%di' % (len(i['args']) // 4), i['args'])
        if i['bank'] == 2000 and i['id'] in (0, 6) and any(eid in nums for eid in ar['new_events']) or want & set(nums):
            ev0['ins'].append(i)
            have.add((i['bank'], i['id'], i['args']))
    return emevd.write(e)


def port_map(src, ar, k):
    """在 src 这张图上按名字拷成品里的部件，返回新地图（DCX）；按来源内容缓存。失败抛 RuntimeError"""
    raw = open(src, 'rb').read()
    done = arena_file(k, rel_map(msb_of(ar)))
    tool_dll = os.path.join(DATA, 'bossmods', '_tools', 'msbport.dll')          # 工具换了也重做
    h = hashlib.sha1(raw + open(done, 'rb').read() + repr(ar['parts']).encode() + open(tool_dll, 'rb').read()).hexdigest()[:20]
    cached = os.path.join(CACHE_DIR, '%s_%s.msb.dcx' % (k, h))
    hit = extragrace.read_cache(cached)              # 不完整的缓存当没有（sc/extragrace.py read_cache）
    if hit is not None:
        return hit
    d, why = extragrace.tool()
    if not d:
        raise RuntimeError(why)
    for n in ('msbport.dll', 'msbport.runtimeconfig.json'):
        s, t = os.path.join(DATA, 'bossmods', '_tools', n), os.path.join(d, n)
        if not os.path.isfile(t) or open(s, 'rb').read() != open(t, 'rb').read():
            shutil.copyfile(s, t)
    a, b, o = (os.path.join(d, 'arena_%s.msb.dcx' % x) for x in ('src', 'done', 'out'))
    open(a, 'wb').write(raw)
    shutil.copyfile(done, b)
    r = subprocess.run([extragrace.DOTNET, 'msbport.dll', a, b, o] + list(ar['parts']), cwd=d, capture_output=True, text=True, timeout=300,
                       encoding='utf-8', errors='replace',          # 输出里有日文部件 / 事件名（宝箱），按系统编码解会出错
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0 or not r.stdout.strip().endswith('ok'):
        raise RuntimeError('msbport 失败：%s' % (r.stdout + r.stderr).strip()[-200:])
    out = extragrace.checked_output(o, 'msbport')
    for p in (a, b, o):
        os.remove(p)
    os.makedirs(CACHE_DIR, exist_ok=True)
    for old in os.listdir(CACHE_DIR):
        if old.startswith(k + '_'):
            os.remove(os.path.join(CACHE_DIR, old))
    extragrace.write_cache(cached, out)              # 先写 .tmp 再换上去
    return out


def files(cx, tmp):
    for k, ar in ports(cx):
        m, mm = ar['map'], msb_of(ar)
        try:
            # 这次前面的功能已经写了这张图（额外赐福 sc/extragrace.py 在大书库加赐福）就接着它的结果移植，免得互相盖掉
            done_ev, done_map = os.path.join(tmp, rel_event(m)), os.path.join(tmp, rel_map(mm))
            ev_src = done_ev if os.path.isfile(done_ev) else (last_with(cx.sources, rel_event(m)) or vanilla(rel_event(m)))
            map_src = (done_map if os.path.isfile(done_map) else (last_with(cx.sources, rel_map(mm)) or vanilla(rel_map(mm)))) if ar.get('parts') else None
            if not ev_src or ar.get('parts') and not map_src:
                raise RuntimeError('找不到 %s 的事件 / 地图' % m)
            part = []
            ev = port_events(erlib.dcx_decompress(open(ev_src, 'rb').read()), ar, k, part)
            ev = hide_stray(ev, ar, k, part)          # 拷过去的部件被随机器的事件整组启用的：读图后关掉（拉卡德的剑、米德拉的分身）
            msb = port_map(map_src, ar, k) if map_src else None
        except Exception as ex:                      # 移植不上不影响别的功能
            cx.notes.append('Boss 模组 %s 的场地没移植上（Boss 照样用新动作，只是没有新阶段 / 召唤）：%s' % (k, ex))
            continue
        for rel, blob in ((rel_event(m), erlib.dcx_compress_dflt(ev, level=6)), (rel_map(mm), msb)):
            if blob is None:
                continue
            os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
            open(os.path.join(tmp, rel), 'wb').write(blob)
        cx.notes.append('Boss 模组 %s 的场地已移植到高难度世界的 %s%s' % (k, m, '（' + '；'.join(part) + '）' if part else ''))
