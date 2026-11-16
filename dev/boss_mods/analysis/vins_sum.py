# -*- coding: utf-8 -*-
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van

F = json.load(open(os.path.join(van.HERE, 'files_cmp.json'), encoding='utf-8'))
S = json.load(open(os.path.join(van.HERE, 'rows_summary.json')))
for m in sorted(F):
    c = collections.Counter(r[3] for r in F[m])
    chrs = [r for r in F[m] if r[0].startswith(('chr/', 'script/', 'action/', 'sfx/'))]
    cc = collections.Counter(r[3] for r in chrs)
    tot = sum(len(x['add']) + len(x['chg']) for p, x in S[m].items() if p not in ('AtkParam_Pc', 'EquipParamWeapon', 'EquipParamProtector', 'BehaviorParam_PC', 'SwordArtsParam', 'FinalDamageRateParam', 'HPEstusFlaskRecoveryParam', 'MPEstusFlaskRecoveryParam'))
    same = sum(x['vins_same'] for p, x in S[m].items() if p not in ('AtkParam_Pc', 'EquipParamWeapon', 'EquipParamProtector', 'BehaviorParam_PC', 'SwordArtsParam', 'FinalDamageRateParam', 'HPEstusFlaskRecoveryParam', 'MPEstusFlaskRecoveryParam'))
    diff_files = [r[0] for r in chrs if r[3] != 'VINS同']
    print('%s %-38s 全部文件 %s | 角色/AI/特效文件 %s | 参数行 %d/%d 一样 | 不一样的角色文件: %s' % (
        m, van.NAMES[m], dict(c), dict(cc), same, tot, diff_files[:8]))
