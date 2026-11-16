# -*- coding: utf-8 -*-
"""剧情推进后整块换图、原场地里的 Boss 不见了：把这一仗补进换过的那张图（用户 2026-11-13「花蕾圣女…boss房外没有雾门 无法触发boss」
→「花蕾圣女参考一下golden age的实现」→「这个位置直接固定吧」「只在高难不随机」）。
花蕾教堂：烧了封印树以后游戏加载 m61_44_45_10（解封版），原版的解封版里萝蜜娜的事件（雾门、开战、死亡处理、阶段特效）都在，
只缺地图部件。Golden Age 3.6.8 就是把这几样拷进解封版；这里多拷了二阶段特效用的辅助角色和物件（原版事件 2044452820 / 2821 用）。
进「死亡」以上复活、或者用「头目复活」以后，不补的话这个位置打不了。
  - 要拷的按原版萝蜜娜写死（PARTS / REGIONS）。高难度世界里这个位置固定是萝蜜娜（launcher\\randomize.ps1 Get-BossFixedIds）；
    普通世界开了敌人随机时这个位置是别的 Boss，不补（原版就是这样：解封后这一战打不了），启动日志说一句。
    认法：原版图（_00）里 c5030_9000 这个部件的模型还是萝蜜娜的 c5030。
  - 事件：原版图里参数带击败标记、换过的图里没有的事件，连同构造事件里的初始化（随机器给这个位置加的），拷过去。
  - 两张图都是原版（没开敌人随机，加载的包里没有这两张图）：没有随机器就没有 SoulsFormats，用预先做好的 data\\lostarena 里的地图
    （原版解封版 + 这几样，见 build_fixed）。有随机器 / 重随修补过的图时，用 msbport 在那张图上按名字拷（和 Boss 模组场地移植同一个工具）。
王城（烧黄金树后的灰城）：蒙葛特、葛孚雷之影的场地和灰城的葛孚雷 / 吉德翁重叠，不补（用户 2026-11-13「不补 也不用说明了」），
蒙葛特也不固定（「改回随机」）。"""
import hashlib
import os
import shutil
import struct
import subprocess

import emevd
import erlib
from . import extragrace
from .common import DATA, REROLL, last_with, vanilla

SPECS = [{
    'key': 'romina', 'defeat': 2044450800, 'src': 'm61_44_45_00', 'dst': 'm61_44_45_10', 'name': '花蕾教堂（萝蜜娜的位置）',
    'boss_part': 'c5030_9000', 'boss_model': 'c5030',
    # 萝蜜娜本体、二阶段特效的辅助角色、两道雾门、二阶段特效的物件、开战区域
    'parts': ['c5030_9000', 'c0100_9000', 'AEG099_002_9000', 'AEG099_002_9001', 'AEG099_090_9004'],
    'regions': ['領域 ボス戦闘開始領域'],
}]
CACHE_DIR = os.path.join(REROLL, 'cache', 'lostarena')
FIXED_DIR = os.path.join(DATA, 'lostarena')
TOOL = os.path.join(DATA, 'bossmods', '_tools')          # msbport


def rel_map(m):
    return os.path.join('map', 'mapstudio', m + '.msb.dcx')


def rel_event(m):
    return os.path.join('event', m + '.emevd.dcx')


def sources(cx):
    out = [os.path.join(TOOL, 'msbport.dll')]
    for sp in SPECS:
        for rel in (rel_event(sp['src']), rel_event(sp['dst']), rel_map(sp['src']), rel_map(sp['dst'])):
            p = last_with(cx.sources, rel)
            if p:
                out.append(p)
        fx = os.path.join(FIXED_DIR, sp['dst'] + '.msb.dcx')
        if os.path.isfile(fx):
            out.append(fx)
    return out


def ints(b):
    return list(struct.unpack_from('<%di' % (len(b) // 4), b, 0)) if len(b) >= 4 else []


def part_model(raw, name):
    """解压后的 MSBE 里叫 name 的部件用的模型名（模型表里第 ModelIndex 个）；没有这个部件返回 None"""
    pos, models, idx = 0x10, [], None
    while pos:
        cnt = struct.unpack_from('<i', raw, pos + 4)[0]
        noff = struct.unpack_from('<q', raw, pos + 8)[0]
        offs = struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16)
        nxt = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
        sec = erlib._u16str(raw, noff)
        if sec == 'MODEL_PARAM_ST':
            models = [erlib._u16str(raw, o + struct.unpack_from('<q', raw, o)[0]) for o in offs]
        elif sec == 'PARTS_PARAM_ST':
            for o in offs:
                if erlib._u16str(raw, o + struct.unpack_from('<q', raw, o)[0]) == name:
                    idx = struct.unpack_from('<i', raw, o + 0x14)[0]
        pos = nxt
    return models[idx] if idx is not None and 0 <= idx < len(models) else None


def plan_events(es, et, defeat):
    """原版图 es、换过的图 et（emevd.read 的结果）→（要拷的事件、要拷的初始化指令）：原版图里参数带击败标记、换过的图里没有的事件
    （连同它们里面初始化的事件），构造事件里它们的初始化和参数带击败标记的公共事件初始化"""
    S = {ev['id']: ev for ev in es['events']}
    T = {ev['id']: ev for ev in et['events']}
    if 0 not in S or 0 not in T:
        raise RuntimeError('没有构造事件 0')
    seen = set()
    todo = [i for i, ev in S.items() if i and any(defeat in ints(x['args']) for x in ev['ins'])]
    while todo:
        i = todo.pop()
        if i in seen or i not in S:
            continue
        seen.add(i)
        todo += [ints(x['args'])[1] for x in S[i]['ins'] if (x['bank'], x['id']) == (2000, 0) and len(x['args']) >= 8]
    new_ev = [S[i] for i in sorted(seen) if i not in T]
    have = {(x['bank'], x['id'], bytes(x['args'])) for x in T[0]['ins']}
    new_init = []
    for x in S[0]['ins']:
        if (x['bank'], x['id']) not in ((2000, 0), (2000, 6)) or len(x['args']) < 8 or (x['bank'], x['id'], bytes(x['args'])) in have:
            continue
        v = ints(x['args'])
        if x['id'] == 0 and v[1] in seen or defeat in v[2:]:
            new_init.append(x)
    return new_ev, new_init


def apply_events(raw_t, es, new_ev, new_init):
    """把事件和初始化拷进换过的图（解压后）；分层指令按分层内容在目标里找 / 追加"""
    et = emevd.read(raw_t)
    for ev in new_ev:
        ins = []
        for x in ev['ins']:
            y = dict(x)
            if x['layer'] is not None:
                blob = es['layers'][x['layer']]
                if blob not in et['layers']:
                    et['layers'].append(blob)
                y['layer'] = et['layers'].index(blob)
            ins.append(y)
        et['events'].append(dict(ev, ins=ins))
    ev0 = next(ev for ev in et['events'] if ev['id'] == 0)
    ev0['ins'] = list(ev0['ins']) + [dict(x, layer=None) for x in new_init]
    return emevd.write(et)


def port_map(raw_dst, raw_src, args):
    """在换过的图上用 msbport 按名字拷原版图的部件 / 区域，返回新地图（DCX）；按内容缓存。失败抛 RuntimeError"""
    h = hashlib.sha1(raw_dst + raw_src + '\n'.join(args).encode('utf-8') + open(os.path.join(TOOL, 'msbport.dll'), 'rb').read()).hexdigest()[:20]
    cached = os.path.join(CACHE_DIR, 'port_%s.msb.dcx' % h)
    if os.path.isfile(cached):
        return open(cached, 'rb').read()
    d, why = extragrace.tool()
    if not d:
        raise RuntimeError(why)
    for n in ('msbport.dll', 'msbport.runtimeconfig.json'):
        s, t = os.path.join(TOOL, n), os.path.join(d, n)
        if not os.path.isfile(t) or open(s, 'rb').read() != open(t, 'rb').read():
            shutil.copyfile(s, t)
    a, b, o = (os.path.join(d, 'lostarena_%s.msb.dcx' % x) for x in ('dst', 'src', 'out'))
    open(a, 'wb').write(raw_dst)
    open(b, 'wb').write(raw_src)
    r = subprocess.run([extragrace.DOTNET, 'msbport.dll', os.path.basename(a), os.path.basename(b), os.path.basename(o)] + args, cwd=d,
                       capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace',
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0 or not r.stdout.strip().endswith('ok'):
        raise RuntimeError('msbport 失败：%s' % (r.stdout + r.stderr).strip()[-200:])
    out = open(o, 'rb').read()
    for p in (a, b, o):
        os.remove(p)
    os.makedirs(CACHE_DIR, exist_ok=True)
    for old in os.listdir(CACHE_DIR):
        if old.startswith('port_'):
            os.remove(os.path.join(CACHE_DIR, old))
    open(cached, 'wb').write(out)
    return out


def msb_args(sp):
    return list(sp['parts']) + ['^' + r for r in sp['regions']]


def files(cx, tmp):
    for sp in SPECS:
        s, t = sp['src'], sp['dst']
        try:
            done_ev, done_map = os.path.join(tmp, rel_event(t)), os.path.join(tmp, rel_map(t))
            map_t_pack = done_map if os.path.isfile(done_map) else last_with(cx.sources, rel_map(t))
            map_s_pack = last_with(cx.sources, rel_map(s))
            ev = None
            if not map_t_pack and not map_s_pack:
                # 两张图都是原版（没装随机器时 DLC 的原版地图 / 事件取不到，原版解封版的事件本来就全）：用预先做好的地图
                fx = os.path.join(FIXED_DIR, t + '.msb.dcx')
                if not os.path.isfile(fx):
                    raise RuntimeError('没有预先做好的 %s' % fx)
                msb, how = open(fx, 'rb').read(), '预先做好的地图'
            else:
                raw_ms = open(map_s_pack or vanilla(rel_map(s)), 'rb').read()
                model = part_model(erlib.dcx_decompress(raw_ms), sp['boss_part'])
                if model != sp['boss_model']:
                    cx.notes.append('%s：这个位置的头目随机换过（%s），解封后的地图不补这一战' % (sp['name'], model))
                    continue
                ev_t = done_ev if os.path.isfile(done_ev) else (last_with(cx.sources, rel_event(t)) or vanilla(rel_event(t)))
                ev_s = last_with(cx.sources, rel_event(s)) or vanilla(rel_event(s))
                if not ev_t or not ev_s:
                    raise RuntimeError('找不到事件文件')
                raw_t = erlib.dcx_decompress(open(ev_t, 'rb').read())
                es = emevd.read(erlib.dcx_decompress(open(ev_s, 'rb').read()))
                new_ev, new_init = plan_events(es, emevd.read(raw_t), sp['defeat'])
                ev = apply_events(raw_t, es, new_ev, new_init) if new_ev or new_init else None
                raw_mt = open(map_t_pack or vanilla(rel_map(t)), 'rb').read()
                msb, how = port_map(raw_mt, raw_ms, msb_args(sp)), '拷了 %d 个部件 / 区域，补了事件 %d 个、初始化 %d 条' % (
                    len(msb_args(sp)), len(new_ev), len(new_init))
        except Exception as ex:                      # 补不上不影响别的功能
            cx.notes.append('%s 的 Boss 战没补进解封后的地图：%s' % (sp['name'], ex))
            continue
        for rel, blob in ((rel_event(t), erlib.dcx_compress_dflt(ev, level=6) if ev else None), (rel_map(t), msb)):
            if blob is None:
                continue
            os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
            open(os.path.join(tmp, rel), 'wb').write(blob)
        cx.notes.append('%s：Boss 战补进了解封后的地图（%s）' % (sp['name'], how))


def build_fixed(vanilla_dir):
    """离线做「两张图都是原版」时用的地图（data\\lostarena\\<换过的图>.msb.dcx）：原版换过的图 + 写死的这几样。
    vanilla_dir：原版地图 / 事件平放的目录（随机器的 diste\\Vanilla，2026-11-13 核对过和游戏 DLC 包里的一样）。要随机器（SoulsFormats）"""
    os.makedirs(FIXED_DIR, exist_ok=True)
    for sp in SPECS:
        s, t = sp['src'], sp['dst']
        rd = lambda m, ext: open(os.path.join(vanilla_dir, m + ext), 'rb').read()
        new_ev, new_init = plan_events(*(emevd.read(erlib.dcx_decompress(rd(m, '.emevd.dcx'))) for m in (s, t)), sp['defeat'])
        if new_ev or new_init:
            raise RuntimeError('原版 %s 还缺事件，预先做好的地图不够用：%s' % (t, [e['id'] for e in new_ev]))
        out = os.path.join(FIXED_DIR, t + '.msb.dcx')
        open(out, 'wb').write(port_map(rd(t, '.msb.dcx'), rd(s, '.msb.dcx'), msb_args(sp)))
        print(out, msb_args(sp))
