# -*- coding: utf-8 -*-
"""各稀有度武器对比：装备样本（inputs\\pool.tsv，dark_core 自己的生成代码出的）插进随机敌人的 regulation，
按模型的三种加点在各档打到一半时的属性，算每把能不能用（双手够需求）、+0 / 满级攻击力、对这一档参考敌人每下的伤害（含异常折算），
按稀有度（普通 / 稀有 / 史诗 / 传说 / 传说（幽影之地））给中位数、90% 分位和能用的比例；再统计配方本身（补正项数、补正合计、
命中异常、特效、强攻）和强化要的锻造石。只读。
用法（带 numpy 的 Python）：python -X utf8 rarity_compare.py [--profile 全清] [--build 力敏]"""
import argparse, json, os
from collections import Counter

import numpy as np

import dr_pool
import model as M

HERE = M.HERE
RAR = ('普通', '稀有', '史诗', '传说', '传说(DLC)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', default='全清', help='用哪种肝度的各档等级（profiles_summary.json）')
    ap.add_argument('--build', default='力敏')
    a = ap.parse_args()
    S = json.load(open(os.path.join(M.RR, 'settings.json'), encoding='utf-8'))
    prof = next(p for p in json.load(open(os.path.join(HERE, 'profiles_summary.json'), encoding='utf-8'))['profiles'] if p['name'] == a.profile)
    levels = prof['builds'][a.build]['dr']['level']
    reg = M.Reg(os.path.join(HERE, 'inputs', 'rand', 'regulation.bin'))
    arms = M.Arms(reg)
    pool = dr_pool.load(os.path.join(HERE, 'inputs', 'pool.tsv'))
    ids = M.pool_insert(arms, pool)
    refs = json.load(open(os.path.join(HERE, 'inputs', 'bundle_2_rand.json'), encoding='utf-8'))['ref']
    build = M.BUILDS[a.build]
    base, start_lv, _w, _a = M.class_start(reg, build['cls'])
    bands = [b['name'].split('（')[0] for b in S['tier_bands']][:len(levels)]

    # 配方本身
    print('配方（每档 %d 件样本）：' % len(pool['w'][0]))
    print('  稀有度      补正项数  补正合计  能力需求合计  带异常  带特效  强攻  满级  主要补正最高值')
    for t in range(5):
        lst = pool['w'].get(t, [])
        if not lst:
            continue
        ncor = [sum(1 for c in it['cor'] if c > 0) for it in lst]
        scor = [sum(c for c in it['cor'] if c > 0) for it in lst]
        sreq = [sum(it['req']) for it in lst]
        st = sum(1 for it in lst if any(x > 0 for x in it['st'])) / len(lst)
        sp = sum(1 for it in lst if it['spec'] > 0) / len(lst)
        atk = sum(1 for it in lst if it['atk'] > 0) / len(lst)
        mx = Counter(arms.max_level(it['id']) for it in lst).most_common(1)[0][0]
        top = [max(it['cor']) for it in lst]
        print('  %-9s %8.1f %9.0f %12.0f %7.0f%% %6.0f%% %4.0f%%  +%d  %8.0f' % (
            RAR[t], np.mean(ncor), np.median(scor), np.median(sreq), st * 100, sp * 100, atk * 100, mx, np.median(top)))
    stones = S['weapon_upgrade']['stones']
    names = {10100: '锻造石1', 10101: '锻造石2', 10102: '锻造石3', 10103: '锻造石4', 10104: '锻造石5', 10105: '锻造石6', 10106: '锻造石7',
             10107: '锻造石8', 10140: '古龙锻造石', 10160: '失色1', 10161: '失色2', 10162: '失色3', 10163: '失色4', 10164: '失色5',
             10165: '失色6', 10166: '失色7', 10167: '失色8', 10168: '失色9', 10200: '失色古龙'}
    print('  强化要的石头（+1 → +5，每级 1 块）：' + '；'.join('%s %s' % (r, '、'.join(names.get(x, str(x)) for x in v)) for r, v in stones.items()))
    print('  成长：+5 相当于原版的 +%s 级（满级 25）' % ' / '.join('%g' % (g * 25) for g in S['weapon_upgrade']['growth'].values()))

    print('\n%s，%s各档打到一半时的属性；每下伤害 = 对这一档参考敌人（中位防御）的伤害，含异常折算：' % (a.build, a.profile))
    for b, lv in enumerate(levels):
        s = M.allocate(base, start_lv, lv, build)
        ref = refs[b]
        ref = (np.array(ref['def']), np.array(ref['cut']), np.array(ref['atk']), ref['hp'], np.array(ref['res']))
        print('\n%s  Lv%d（力%d 技%d 智%d 信%d 感%d）' % (bands[b], lv, s['str'], s['dex'], s['mag'], s['fai'], s['luc']))
        print('  稀有度      能用   +0攻击力 中位/90%%     满级攻击力 中位/90%%    满级每下伤害 中位/90%%   比稀有（中位）')
        rare_med = None
        rows = []
        for t in range(5):
            lst = [it['id'] for it in pool['w'].get(t, [])]
            ok = [w for w in lst if arms.usable(w, s)]
            if not ok:
                continue
            a0 = [arms.ar(w, 0, s).sum() for w in ok]
            am = [arms.ar(w, arms.max_level(w), s).sum() for w in ok]
            vm = [M.weapon_value(arms, w, arms.max_level(w), s, ref) for w in ok]
            rows.append((t, len(ok) / len(lst), a0, am, vm))
            if t == 1:
                rare_med = np.median(vm)
        for t, share, a0, am, vm in rows:
            print('  %-9s %5.0f%%   %5.0f / %5.0f      %5.0f / %5.0f        %5.0f / %5.0f        %s' % (
                RAR[t], share * 100, np.median(a0), np.percentile(a0, 90), np.median(am), np.percentile(am, 90),
                np.median(vm), np.percentile(vm, 90), '×%.2f' % (np.median(vm) / rare_med) if rare_med else '-'))


if __name__ == '__main__':
    main()
