# -*- coding: utf-8 -*-
"""共用：读原版游戏文件（Data0-3 / DLC）、各个 Boss 模组的根目录。
用法（2026-11-04 Boss 模组评估，见 ..\\Boss模组整合评估.md）：先把 dark_reforged\\boss\\ 里的 12 个压缩包
按 m01..m12 的顺序（文件名排序）各自解压到 <BOSSMODS>\\m01 … m12（Windows 自带 tar.exe 能解 rar），
再设环境变量 BOSSMODS 指过去；脚本都用 python -P 跑（要用户目录里的 pycryptodome），结果写在本目录。
keys\\ 是 Data0-3 / DLC 的公钥（Data1/2/DLC 从 Smithbox 的 Andre.Formats.dll 取的），只读原版文件用。"""
import os, sys
ER = r'E:\SteamLibrary\steamapps\common\ELDEN RING\Game'
RR = os.path.join(ER, 'dark_reforged', 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa
erlib.DLL_DIRS[:] = [ER]

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.environ.get('BOSSMODS') or os.path.join(os.path.dirname(HERE), '_extracted')
VINS = os.path.join(ER, 'ELDEN VINS', 'mod')

ROOTS = {
    'm01': 'mod', 'm02': 'Placidusax, Ancient Lord (v1.01.3)', 'm03': 'mod',
    'm04': 'Inner Consort v1.06.6 - Main Version', 'm05': 'Inner Godfrey (v1.13)',
    'm06': 'Inner Serpent v1.04.2 (Hotfix)', 'm07': 'midra', 'm08': 'mod', 'm09': 'mod',
    'm10': 'mod', 'm11': 'mod', 'm12': os.path.join('Unalloyed 1.06', 'mod'),
}
NAMES = {
    'm01': 'Mohg 2.00 Complete', 'm02': 'Ancient Elden Lord (Placidusax) 1.01.3', 'm03': 'Godrick overhaul 1.4',
    'm04': 'Inner Consort (Radahn) 1.06.6', 'm05': 'Inner Godfrey 1.13', 'm06': 'Inner Serpent (Messmer) 1.04.2',
    'm07': 'Midra overhaul 1.16.1', 'm08': 'Rellana overhaul 1.0', 'm09': 'Rennala overhaul 1.2',
    'm10': 'Rykard overhaul 1.0', 'm11': 'The Second Release (Morgott) 1.01', 'm12': 'Unalloyed Malenia 1.06',
}


def root(m):
    if m == 'vins':
        return VINS
    return os.path.join(MODS, m, ROOTS[m])


_arcs = None


def arcs():
    global _arcs
    if _arcs is None:
        _arcs = []
        for n in ('Data0', 'Data1', 'Data2', 'Data3', 'DLC'):
            pem = open(os.path.join(HERE, 'keys', n + '_key.pem'), 'rb').read()
            if pem[:2] in (b'\xff\xfe', b'\xfe\xff'):
                pem = pem.decode('utf-16')
            else:
                pem = pem.decode('ascii', 'ignore')
            _arcs.append((n, erlib.GameArchive(os.path.join(ER, n + '.bhd'), pem)))
    return _arcs


def vread(path, which=False):
    """原版文件，例如 /chr/c4750.anibnd.dcx；几个包里都有时用最后一个（DLC 优先）"""
    hit = None
    for n, a in arcs():
        if a.entry(path) is not None:
            hit = (n, a)
    if hit is None:
        return (None, None) if which else None
    data = hit[1].read(path)
    return (hit[0], data) if which else data


def unz(raw):
    return erlib.dcx_decompress(raw) if raw[:4] == b'DCX\0' else raw


def bnd(raw):
    """BND4（可带 DCX）→ {短文件名: 数据}"""
    b = erlib.Bnd4(unz(raw))
    return {k: b.get(k) for k in b.entries}


def bnd_full(raw):
    """→ {完整文件名: 数据}"""
    raw = unz(raw)
    import struct
    b = erlib.Bnd4(raw)
    out = {}
    pos = 0x40
    for k in range(b.count):
        p = pos + 8
        csize = struct.unpack_from('<q', raw, p)[0]
        p += 8
        if b.compr:
            p += 8
        if b.long_off:
            off = struct.unpack_from('<q', raw, p)[0]; p += 8
        else:
            off = struct.unpack_from('<I', raw, p)[0]; p += 4
        if b.has_ids:
            p += 4
        noff = struct.unpack_from('<I', raw, p)[0]
        e = noff
        if b.unicode:
            while raw[e:e + 2] != b'\0\0':
                e += 2
            name = raw[noff:e].decode('utf-16le')
        else:
            name = raw[noff:raw.index(b'\0', noff)].decode('shift_jis')
        out[name] = raw[off:off + csize]
        pos += b.hdr_size
    return out
