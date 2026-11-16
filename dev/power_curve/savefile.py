# -*- coding: utf-8 -*-
"""读艾尔登法环 PC 存档（ER0000.sl2 / .rng / .rng.co2，BND4，不加密）里每个格子的人物：名字、等级、八项属性、所在地图、
装备着的武器 / 防具 / 护符、持有的所有武器（GaItem 表）。只读，给「按存档算伤害成长」（save_curve.py）用。

格子数据（去掉开头 16 字节 MD5，0x280000）：
  0x00 版本 u32、0x04 地图编号 4 字节（m{[3]}_{[2]}_{[1]}_{[0]}）、0x20 起 GaItem 表 0x1400 项
  （句柄 u32 + 物品编号 u32；句柄高 4 位 8 = 武器再跟 13 字节，9 = 防具再跟 8 字节）；
  后面是人物数据（PlayerGameData）：+0x34 起八项属性，+0x60 等级，+0x94 名字（UTF-16）；
  装备着的物品编号表在 +0x2F4（22 个 u32：左 1、右 1、左 2、右 2、左 3、右 3、箭弩 4 格、2 格空、头身手腿、1 格空、护符……），
  前面 +0x2D8 是「握法、左手第几把、右手第几把……」。
人物数据的位置：找存档摘要（USER_DATA010）里的名字，名字前 0x94 是开头、开头 +0x60 的等级要和摘要一致；
正常角色「八项之和 − 79 = 等级」，对不上的是用工具改过属性的测试角色（stats_ok = False）。"""
import struct

STATS = ('vigor', 'mind', 'endurance', 'str', 'dex', 'mag', 'fai', 'luc')
EMPTY = 0xFFFFFFFF


def bnd_entries(d):
    assert d[:4] == b'BND4', '不是 BND4 存档'
    n = struct.unpack_from('<i', d, 0x0C)[0]
    out = []
    for i in range(n):
        o = 0x40 + i * 0x20
        size = struct.unpack_from('<q', d, o + 8)[0]
        off = struct.unpack_from('<i', d, o + 0x10)[0]
        out.append(d[off:off + size])
    return out


def summary(ent10):
    """存档摘要：{格子: (名字, 等级)}（只列在用的格子）"""
    u = ent10[16:]
    out = {}
    for i in range(10):
        if u[0x1954 + i]:
            base = 0x195E + i * 0x24C
            name = u[base:base + 32].decode('utf-16-le', 'replace').split('\x00')[0]
            out[i] = (name, struct.unpack_from('<I', u, base + 0x22)[0])
    return out


def _gaitems(s):
    """GaItem 表：[(句柄, 物品编号)]"""
    o, items = 0x20, []
    for _ in range(0x1400):
        h, iid = struct.unpack_from('<II', s, o)
        o += 8
        t = h & 0xF0000000
        if t == 0x80000000:
            o += 13
        elif t == 0x90000000:
            o += 8
        if h:
            items.append((h, iid))
    return items


def _find_pgd(s, name, level):
    """人物数据开头：名字（UTF-16 + 结尾 0）前 0x94，开头 +0x60 是等级"""
    nb = (name + '\x00').encode('utf-16-le')
    o = s.find(nb)
    while o != -1:
        pgd = o - 0x94
        if pgd >= 0 and struct.unpack_from('<I', s, pgd + 0x60)[0] == level:
            return pgd
        o = s.find(nb, o + 2)
    return None


def parse(path):
    d = open(path, 'rb').read()
    ents = bnd_entries(d)
    chars = {}
    for slot, (name, level) in summary(ents[10]).items():
        s = ents[slot][16:]
        mp = s[4:8]
        pgd = _find_pgd(s, name, level)
        if pgd is None:
            chars[slot] = {'name': name, 'level': level, 'error': '找不到人物数据'}
            continue
        sv = struct.unpack_from('<8I', s, pgd + 0x34)
        eq = list(struct.unpack_from('<22I', s, pgd + 0x2F4))
        style, lslot, rslot = struct.unpack_from('<3I', s, pgd + 0x2D8)
        weapons = sorted({iid for h, iid in _gaitems(s) if h & 0xF0000000 == 0x80000000 and iid not in (0, EMPTY)})
        chars[slot] = {
            'name': name, 'level': level, 'stats': dict(zip(STATS, sv)), 'stats_ok': sum(sv) - 79 == level,
            'map': 'm%02d_%02d_%02d_%02d' % (mp[3], mp[2], mp[1], mp[0]),
            'equip': {'left': eq[0:6:2], 'right': eq[1:6:2], 'armor': eq[12:16], 'talisman': [x for x in eq[17:22] if x not in (0, EMPTY)]},
            'active': {'style': style, 'left': lslot, 'right': rslot},
            'weapons': weapons,
        }
    return chars


if __name__ == '__main__':
    import sys
    for k, c in sorted(parse(sys.argv[1]).items()):
        if 'error' in c:
            print(k, c)
            continue
        print(k, c['name'], 'Lv', c['level'], '属性对得上' if c['stats_ok'] else '属性被改过（测试角色）', c['map'], c['stats'])
        print('   右手', c['equip']['right'], '左手', c['equip']['left'], '当前', c['active'], '护符', c['equip']['talisman'], '持有武器', len(c['weapons']))
