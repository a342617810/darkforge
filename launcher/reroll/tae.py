# -*- coding: utf-8 -*-
"""Elden Ring 的 TAE（动作事件，"TAE " 64 位，版本 0x1000D）：只读解析 + 原地改定长参数（不动结构）。
结构照 SoulsFormats 的 TAE3：头 0x50 起 [ID, 动画数, 动画表偏移] → 动画表 [编号, 动画头偏移] → 动画头 [事件头偏移, 事件组偏移, 时间偏移,
动画文件偏移, 事件数 s32] → 事件头 [开始时间偏移, 结束时间偏移, 事件数据偏移] → 事件数据 [类型 s32, 0, 参数偏移]。
攻击行为（类型 1）、子弹行为（类型 2）事件的判定号在参数 +8（判定号 = 前缀 × 1000 + 判定，行为编号 = 前缀亿位 + 武器的行为变体 × 1000 + 判定）"""
import struct

BEHAVIOR_EVENTS = (1, 2)


def events(b):
    """[(动画编号, 事件类型, 参数在文件里的偏移)]"""
    if b[:4] != b'TAE ' or b[7] != 0xFF:
        raise ValueError('不是 64 位 TAE')
    q = lambda o: struct.unpack_from('<q', b, o)[0]
    n_anim, anims_off = struct.unpack_from('<i', b, 0x54)[0], q(0x58)
    out = []
    for k in range(n_anim):
        aid, aoff = q(anims_off + k * 16), q(anims_off + k * 16 + 8)
        ev_off, n_ev = q(aoff), struct.unpack_from('<i', b, aoff + 32)[0]
        for e in range(n_ev):
            dat = q(ev_off + e * 24 + 16)
            out.append((aid, struct.unpack_from('<i', b, dat)[0], q(dat + 8)))
    return out


def judges(b):
    """攻击 / 子弹行为事件的 [(判定号, 判定号在文件里的偏移)]"""
    return [(struct.unpack_from('<i', b, p + 8)[0], p + 8) for _a, t, p in events(b) if t in BEHAVIOR_EVENTS]


# 放特效的事件 → 特效编号在参数里的偏移：96 一次性特效（[特效, 挂点…]）、134（[?, 特效, …]）、138（[特效, 挂点…]）
EFFECT_EVENTS = {96: 0, 134: 4, 138: 0}


def effects(b):
    """放特效的事件的 [(特效编号, 编号在文件里的偏移)]"""
    return [(struct.unpack_from('<i', b, p + EFFECT_EVENTS[t])[0], p + EFFECT_EVENTS[t]) for _a, t, p in events(b) if t in EFFECT_EVENTS]


# 放音效的事件 → 音效编号在参数里的偏移：129、133（[种类, 编号, …]）
SOUND_EVENTS = {129: 4, 133: 4}


def sounds(b, anims):
    """这几个动画里放音效的事件的 [(音效编号, 编号在文件里的偏移)]"""
    return [(struct.unpack_from('<i', b, p + SOUND_EVENTS[t])[0], p + SOUND_EVENTS[t]) for a, t, p in events(b) if t in SOUND_EVENTS and a in anims]
