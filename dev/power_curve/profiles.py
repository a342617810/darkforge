# -*- coding: utf-8 -*-
"""按肝度看各区域的成长：几种玩家（小怪清除率 × Boss 清除率）各跑一遍 model.py（result_profile_<名字>.json），
汇总成 profiles_summary.json 并打印每档的等级、攻击力、主力武器稀有度 / 强化、小怪砍几刀、Boss 砍几刀、战斗力指数和原版同肝度的比。
宝箱 / 拾取默认跟小怪清除率走（最多 1，model.py 的 treasure_ratio）。改 PROFILES 就能换玩家类型。
用法（带 numpy 的 Python）：python -X utf8 profiles.py [--runs 200] [--jobs 10] [--only 名字,…] [--summary-only]"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# (名字, 小怪清除率, Boss 清除率, 说明)
PROFILES = [
    ('速通', 0.3, 0.4, '一路跑主线，小怪能绕就绕，只打挡路和顺手的 Boss'),
    ('主线', 0.6, 0.7, '边跑边打，大部分 Boss 打了，地下墓地 / 洞窟去一部分'),
    ('全清', 1.0, 1.0, '每个小怪杀一遍，Boss 全打，宝箱全拿'),
    ('刷怪', 2.0, 1.0, '全清之外再把小怪刷一倍（卡等级、刷掉落）'),
]
MODE = 'DR 随机敌人'
KEYS = ('level', 'ar', 'rarity', 'upgrade', 'hp', 'h2k', 'bh2k', 'idx', 'bidx', 'talx', 'armx')


def weapon_only_h2k(ar, hp, dfn):
    """光看武器（全物理、单手、没有护符 / 词条 / 异常 / 庇佑）：这一档中位血量的小怪砍几刀"""
    import model
    return hp / (ar * float(model.defense_mult(ar / dfn)))


def run(name, kill, boss, a):
    out = os.path.join(HERE, 'result_profile_%s.json' % name)
    cmd = [sys.executable, '-X', 'utf8', os.path.join(HERE, 'model.py'), '--runs', str(a.runs), '--jobs', str(a.jobs),
           '--kill-ratio', str(kill), '--boss-ratio', str(boss), '--out', out]
    print('== %s（小怪 %g、Boss %g）' % (name, kill, boss), flush=True)
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode:
        sys.exit('model.py 失败：%s' % name)
    return out


def summarize():
    rows = {'profiles': [], 'bands': None}
    ref = json.load(open(os.path.join(HERE, 'inputs', 'bundle_2_rand.json'), encoding='utf-8'))['ref']
    for name, kill, boss, note in PROFILES:
        p = os.path.join(HERE, 'result_profile_%s.json' % name)
        if not os.path.isfile(p):
            continue
        r = json.load(open(p, encoding='utf-8'))
        rows['bands'] = r['bands']
        hp = r['enemies'][MODE]['hp_median']
        prof = {'name': name, 'kill': kill, 'boss': boss, 'note': note, 'builds': {}}
        for x in r['series']:
            if x['difficulty'] != '普通' or x['mode'] not in (MODE, '原版'):
                continue
            d = prof['builds'].setdefault(x['build'], {})
            v = {k: x.get(k) for k in KEYS + tuple(k + q for k in ('ar', 'h2k', 'idx') for q in ('_p10', '_p90'))}
            if x['mode'] == MODE:
                v['h2k_weapon'] = [weapon_only_h2k(a, h, ref[b]['def'][0]) if a else None for b, (a, h) in enumerate(zip(v['ar'], hp))]
            d['dr' if x['mode'] == MODE else 'van'] = v
        rows['profiles'].append(prof)
    json.dump(rows, open(os.path.join(HERE, 'profiles_summary.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    f = lambda v, fmt='%.0f': '-' if v is None else fmt % v
    for prof in rows['profiles']:
        print('\n## %s（小怪清除率 %g、Boss 清除率 %g）：%s' % (prof['name'], prof['kill'], prof['boss'], prof['note']))
        for bn, d in prof['builds'].items():
            dr, van = d.get('dr'), d.get('van')
            if not dr:
                continue
            print('  %s    等级  攻击力(10~90%%)      稀有/强化  小怪砍几刀(光武器)  Boss砍几刀  指数   原版指数  DR÷原版 | 原版 等级 攻击力 砍几刀' % bn)
            for b, band in enumerate(rows['bands']):
                vi = van and van['idx'][b]
                print('  %-24s %3s  %5s (%5s~%5s)  %4s/+%-3s  %5s (%5s)     %5s     %6s  %6s  %6s | %4s %5s %5s' % (
                    band[:24], f(dr['level'][b]), f(dr['ar'][b]), f(dr['ar_p10'][b]), f(dr['ar_p90'][b]), f(dr['rarity'][b], '%.1f'),
                    f(dr['upgrade'][b]), f(dr['h2k'][b], '%.1f'), f(dr['h2k_weapon'][b], '%.1f'), f(dr['bh2k'][b], '%.1f'),
                    f(dr['idx'][b], '%.2f'), f(vi, '%.2f'),
                    f(dr['idx'][b] / vi if vi else None, '%.2f'), f(van and van['level'][b]), f(van and van['ar'][b]), f(van and van['h2k'][b], '%.1f')))
    print('\n→', os.path.join(HERE, 'profiles_summary.json'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=200)
    ap.add_argument('--jobs', type=int, default=10)
    ap.add_argument('--only', default='', help='只跑这几种（逗号分隔名字）')
    ap.add_argument('--summary-only', action='store_true', help='不跑模型，只汇总已有的 result_profile_*.json')
    a = ap.parse_args()
    if not a.summary_only:
        only = {x for x in a.only.split(',') if x}
        for name, kill, boss, _note in PROFILES:
            if not only or name in only:
                run(name, kill, boss, a)
    summarize()


if __name__ == '__main__':
    main()
