# -*- coding: utf-8 -*-
"""额外的赐福：地图部件和登记事件（传送行和地名在重随的 rr/extragrace.py，它在 features.json 的 extra_graces 写了才做）。
每个赐福 = 赐福资产 AEG099_060（登记用的实体）+ 对话角色 c1000（对话 1000 = 赐福菜单），都从同一张图现成的赐福复制；
事件：这张图的事件脚本（加载的包里最后一份 / 原版）事件 0 照现成的那条加一条 2009[3] RegisterBonfire(点燃标记, 资产实体, …)。
地图：
  - 加载的包里没有这张图（没开敌人随机）→ 用预先做好的固定地图 data/graces/<图>.msb.dcx（原版 + 两个部件，离线 msbtool 做的）；
  - 有（随机器输出 / 重随修补过的）→ 用整合包带的 .NET（launcher\\dotnet）在那张图上跑两次 msbtool clone（SoulsFormats 按名字引用部件，
    编号自己重排；随机器删 / 换了敌人，按字节同步那套对不上）。SoulsFormats、ZstdNet 从随机器的单文件包里取（netbundle.py）放 cache\\msbtool，
    随机器换了才重取；结果按来源地图的内容缓存在 cache\\graces，同一张图下次不再跑。
跑不了（没有 .NET / 随机器、msbtool 失败）就整个赐福不加（不写事件），启动日志里说一句。部件位置等见 data/graces/说明.txt"""
import hashlib
import os
import shutil
import struct
import subprocess

import emevd
import erlib
import netbundle

from .common import DATA, PALY, REROLL, last_with, vanilla

TOOL_DIR = os.path.join(REROLL, 'cache', 'msbtool')
CACHE_DIR = os.path.join(REROLL, 'cache', 'graces')
DOTNET = os.path.join(PALY, 'launcher', 'dotnet', 'dotnet.exe')
RANDOMIZER_EXE = os.path.join(PALY, 'randomizer', 'EldenRingRandomizer.exe')
BUNDLED = ('SoulsFormats.dll', 'ZstdNet.dll')
# 各赐福的部件（照 Golden Age 3.6.8，见 data/graces/说明.txt）：(原部件, 新部件, 实体, 坐标, 朝向[, 碰撞])
# 第三个是玩家部件 = 传送落点 / 复活点（实体 = 赐福资产 − 970）；2026-11-02 补上（用户：传送过去回到学院门口、死了也复活不到这里）
SPEC = {'raya_library': [
    ('AEG099_060_9000', 'AEG099_060_9004', 14001954, (99.15069580078125, 154.11599731445312, -47.68484115600586), 103.92798614501953),
    ('c1000_9000', 'c1000_9012', 14000954, (99.1510009765625, 153.656005859375, -47.685001373291016), 5.909999847412109, 'h009100'),
    ('c0000_9000', 'c0000_9021', 14000984, (99.645226, 154.06, -46.583813), -68.90001)]}


def rel_map(m):
    return os.path.join('map', 'mapstudio', m + '.msb.dcx')


def rel_event(m):
    return os.path.join('event', m + '.emevd.dcx')


def graces(cx):
    return [g for g in (cx.feat.get('extra_graces') or []) if g.get('key') in SPEC]


def sources(cx):
    out = []
    for g in graces(cx):
        out += [last_with(cx.sources, rel_map(g['map'])), last_with(cx.sources, rel_event(g['map'])),
                os.path.join(DATA, 'graces', g['map'] + '.msb.dcx')]
    return [p for p in out if p]


def tool():
    """msbtool 的运行目录（SoulsFormats 等从随机器单文件包里取，随机器换了才重取）；准备不了返回 (None, 原因)"""
    if not os.path.isfile(DOTNET) or not os.path.isfile(RANDOMIZER_EXE):
        return None, '没有整合包带的 .NET 或随机器'
    st = os.stat(RANDOMIZER_EXE)
    stamp = '%d|%d' % (st.st_size, int(st.st_mtime))
    sf = os.path.join(TOOL_DIR, 'stamp.txt')
    os.makedirs(TOOL_DIR, exist_ok=True)
    if not (os.path.isfile(sf) and open(sf, encoding='utf-8').read().strip() == stamp and all(os.path.isfile(os.path.join(TOOL_DIR, n)) for n in BUNDLED)):
        raw = open(RANDOMIZER_EXE, 'rb').read()
        for n in BUNDLED:
            data = netbundle.extract(raw, n)
            if data is None:
                return None, '随机器的单文件包里没有 %s' % n
            open(os.path.join(TOOL_DIR, n), 'wb').write(data)
        shutil.copyfile(os.path.join(os.path.dirname(RANDOMIZER_EXE), 'oo2core_6_win64.dll'), os.path.join(TOOL_DIR, 'oo2core_6_win64.dll'))
        open(sf, 'w', encoding='utf-8').write(stamp)
    for n in ('msbtool.dll', 'msbtool.runtimeconfig.json'):
        src, dst = os.path.join(DATA, 'msbtool', n), os.path.join(TOOL_DIR, n)
        if not os.path.isfile(dst) or open(src, 'rb').read() != open(dst, 'rb').read():
            shutil.copyfile(src, dst)
    return TOOL_DIR, ''


def add_parts(src, key):
    """在 src 这张图上加 key 的部件（msbtool clone，按顺序），返回新地图的字节；按来源内容缓存。失败抛 RuntimeError"""
    raw = open(src, 'rb').read()
    h = hashlib.sha1(raw + repr(SPEC[key]).encode()).hexdigest()[:20]
    cached = os.path.join(CACHE_DIR, '%s_%s.msb.dcx' % (key, h))
    if os.path.isfile(cached):
        return open(cached, 'rb').read()
    d, why = tool()
    if not d:
        raise RuntimeError(why)
    work = [os.path.join(d, 'grace_in.msb.dcx')] + [os.path.join(d, 'grace_%d.msb.dcx' % k) for k in range(len(SPEC[key]))]
    open(work[0], 'wb').write(raw)
    for k, (old, new, ent, pos, yaw, *coll) in enumerate(SPEC[key]):
        args = [DOTNET, 'msbtool.dll', 'clone', work[k], work[k + 1], old, new, str(ent)] + [repr(x) for x in pos] + [repr(yaw)] + list(coll)
        r = subprocess.run(args, cwd=d, capture_output=True, text=True, timeout=300, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if r.returncode != 0 or not r.stdout.strip().endswith('ok'):
            raise RuntimeError('msbtool clone %s 失败：%s' % (new, (r.stdout + r.stderr).strip()[-200:]))
    out = open(work[-1], 'rb').read()
    for p in work:
        os.remove(p)
    os.makedirs(CACHE_DIR, exist_ok=True)
    for old in os.listdir(CACHE_DIR):                 # 同一个赐福只留最新的一份
        if old.startswith(key + '_'):
            os.remove(os.path.join(CACHE_DIR, old))
    open(cached, 'wb').write(out)
    return out


def prebuilt(src, key):
    """src 是 Boss 模组场地成品（data\\bossmods\\<键>\\arena）、而且已经带着这个赐福的部件（dev\\boss_mods\\build.py 做在我们的
    固定地图上，arena\\graces.txt 列着）：直接用，不再拷（没有随机器时也拷不了）"""
    f = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(src))), 'graces.txt')
    return os.path.isfile(f) and key in open(f, encoding='utf-8').read().split()


def register(event_raw, flag, asset):
    """事件 0 里照现成的 2009[3] RegisterBonfire 加一条（点燃标记、资产实体换掉，其余参数照抄）；已经有就不加。返回新的事件脚本（解压后）"""
    e = emevd.read(event_raw)
    ev0 = next(ev for ev in e['events'] if ev['id'] == 0)
    regs = [k for k, x in enumerate(ev0['ins']) if (x['bank'], x['id']) == (2009, 3)]
    if not regs:
        raise RuntimeError('事件 0 里没有现成的 RegisterBonfire 可照抄')
    if any(struct.unpack_from('<I', ev0['ins'][k]['args'], 4)[0] == asset for k in regs):
        return event_raw
    tmpl = ev0['ins'][regs[-1]]
    a = bytearray(tmpl['args'])
    struct.pack_into('<II', a, 0, flag, asset)
    ev0['ins'].insert(regs[-1] + 1, dict(tmpl, args=bytes(a)))
    return emevd.write(e)


def files(cx, tmp):
    for g in graces(cx):
        m = g['map']
        try:
            src = last_with(cx.sources, rel_map(m))
            if src and prebuilt(src, g['key']):
                data = open(src, 'rb').read()
            else:
                data = add_parts(src, g['key']) if src else open(os.path.join(DATA, 'graces', m + '.msb.dcx'), 'rb').read()
            ev_src = last_with(cx.sources, rel_event(m)) or vanilla(rel_event(m))
            if not ev_src:
                raise RuntimeError('找不到 %s 的事件脚本' % m)
            ev = register(erlib.dcx_decompress(open(ev_src, 'rb').read()), g['lit_flag'], g['asset'])
        except Exception as ex:                       # 加不上不影响别的功能
            cx.notes.append('额外赐福 %s 没加上：%s' % (g['key'], ex))
            continue
        for rel, blob in ((rel_map(m), data), (rel_event(m), erlib.dcx_compress_dflt(ev, level=6))):
            os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
            open(os.path.join(tmp, rel), 'wb').write(blob)
