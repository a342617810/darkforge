# -*- coding: utf-8 -*-
"""每个模组自己的行，按编号归到角色（NpcParam / AtkParam_Npc / NpcThink / Bullet = c 编号前 4 位；BehaviorParam = 2 + c×100000…）
看看有多少行其实是别的 Boss 的（打包时混进来的旧版本 / 别的模组）"""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van

S = json.load(open(os.path.join(van.HERE, 'rows_summary.json')))
MAIN = {'m01': {4800}, 'm02': {4520, 5120}, 'm03': {4750, 4690}, 'm04': {5220}, 'm05': {4720, 4721}, 'm06': {5130, 5140, 5141},
        'm07': {5050, 5051}, 'm08': {5300}, 'm09': {2030, 2031, 2032}, 'm10': {4710, 4711, 4712}, 'm11': {2130, 2190},
        'm12': {2120, 2125, 4481, 4483}}


def chr_of(p, r):
    if p in ('NpcParam', 'NpcThinkParam') and 10000000 <= r < 100000000:
        return r // 10000
    if p in ('AtkParam_Npc', 'Bullet') and 1000000 <= r < 10000000:
        return r // 1000
    if p in ('AtkParam_Npc', 'Bullet') and 200000000 <= r < 300000000:
        return (r - 200000000) // 1000
    if p == 'BehaviorParam' and 200000000 <= r < 300000000:
        return (r - 200000000) // 10000
    return None


for m in sorted(S):
    cnt = collections.Counter()
    for p, x in S[m].items():
        if p in ('AtkParam_Pc', 'EquipParamWeapon', 'EquipParamProtector', 'BehaviorParam_PC', 'SwordArtsParam', 'FinalDamageRateParam',
                 'HPEstusFlaskRecoveryParam', 'MPEstusFlaskRecoveryParam'):
            continue
        for r in x['add'] + x['chg']:
            c = chr_of(p, r)
            tag = '本体' if c in MAIN[m] else ('c%04d' % c if c else '其它(%s)' % p)
            cnt[tag] += 1
    print(m, van.NAMES[m], dict(cnt.most_common(14)))
