# -*- coding: utf-8 -*-
"""头目复活清单（data/gracemenu/grace_more.esd）的修正：有的野外 Boss 清单里写的是实体编号，不是击败标记（随机器 enemy.txt 的 DefeatFlag，事件脚本点亮的也是它），
熄灭了也复活不了（用户 2026-11-09：死亡难度火焰巨人的位置复活不了）。超限锻造石、咒痕、融锻之心的表以前也按实体编号记，同一份对照表（dev\\item_system\\build_overlimit_flags.py 用）。
还有的 Boss 只熄击败标记不够，场地里另有标记要一起熄（EXTRA_CLEAR）。"""
from .esdutil import calls, esd_int, i32

# 实体编号 → 真的击败标记
DEFEAT_FIX = {
    1036450340: 1036450800, 1036480340: 1036480800, 1037420340: 1037420800, 1038520340: 1038520800, 1039430340: 1039430800,
    1043370340: 1043370800, 1044320340: 1044320800, 1044320342: 1044320850, 1054560800: 1254560800, 2051450720: 2051450800,
}
# 火焰巨人：清单里的 1052520800 是事件编号（事件结束点亮同号标记，要熄灭事件才会再跑），留着；真的击败标记另外熄灭
FIRE_GIANT, FIRE_GIANT_DEFEAT = 1052520800, 1252520800
# 清单里调用参数带这个编号的那一项 → 复活时另外要熄灭的标记（每项在清单里应该只出现 1 次）
EXTRA_CLEAR = {
    FIRE_GIANT: (FIRE_GIANT_DEFEAT,),
    # 蒙葛特：入口雾门（11001800）的显示另由 11000501 管（蒙葛特死后、场地里的机关点过才点亮，点亮后雾门消失），
    # 只熄 11000800 雾门出不来、开不了战（用户 2026-11-13「噩兆王…boss房外没有雾门 无法触发boss」）。再打倒后原版事件 11002501 会重新点亮它
    11000800: (11000501,),
}
EXTRA_FLAGS = tuple(f for fs in EXTRA_CLEAR.values() for f in fs)


def clear_flag(flag):
    """SetEventFlag(flag, 0)"""
    return {'bank': 1, 'id': 11, 'args': [i32(flag), i32(0)]}


def apply(groups):
    """就地修正 grace_more.esd 的状态机，返回 groups；结构对不上时抛 RuntimeError"""
    hits = {k: 0 for k in EXTRA_CLEAR}
    for st in groups.values():
        for s in st.values():
            for c in calls(s):
                if c['bank'] == 6:
                    c['args'] = [i32(DEFEAT_FIX[esd_int(a)]) if esd_int(a) in DEFEAT_FIX else a for a in c['args']]
            for key, extra in EXTRA_CLEAR.items():
                i = next((k for k, c in enumerate(s['entry']) if c['bank'] == 6 and key in map(esd_int, c['args'])), None)
                if i is not None:
                    s['entry'][i:i] = [clear_flag(f) for f in extra]
                    hits[key] += 1
    bad = {k: n for k, n in hits.items() if n != 1}
    if bad:
        raise RuntimeError('头目复活清单里这些 Boss 的调用应该各 1 处，实际：%s' % bad)
    return groups
