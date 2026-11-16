# -*- coding: utf-8 -*-
"""多个敌人随机种子：rand_seeds.ps1 在随机器副本上换种子跑出来的输出（默认 %LOCALAPPDATA%\\DarkReforged_dev\\rz\\seed_<k>），
各做一次重随（make_inputs.py --only rand）、跑一遍模型（model.py），再加上现在 randomizer\\ 里的那份（result.json），
汇总成 seeds_summary.json：各档 DR 随机敌人普通难度的战斗力指数、Boss 指数 ÷ 原版（三套加点的中位数）。report.py 读它画一张表。
用法：python -X utf8 seeds.py [--rz 目录] [--rebuild] [--runs 200]"""
import argparse, glob, json, os, statistics, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def ratios(path):
    r = json.load(open(path, encoding='utf-8'))
    nb = len(r['bands'])
    out = {}
    for m in ('idx', 'bidx', 'h2k', 'bh2k'):
        rows = []
        for b in range(nb):
            van = [s[m][b] for s in r['series'] if s['mode'] == '原版' and s.get(m) and s[m][b]]
            dr = [s[m][b] for s in r['series'] if s['mode'] == 'DR 随机敌人' and s['difficulty'] == '普通' and s.get(m) and s[m][b]]
            v, d = (statistics.median(van) if van else None), (statistics.median(dr) if dr else None)
            rows.append(d / v if v and d else None)
        out[m] = rows
    out['boss_count'] = r['enemies']['DR 随机敌人']['boss_count']
    out['boss_hp'] = r['enemies']['DR 随机敌人']['boss_hp_median']
    out['hp'] = r['enemies']['DR 随机敌人']['hp_median']
    return r['bands'], out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rz', default=os.path.join(os.environ.get('LOCALAPPDATA', ''), 'DarkReforged_dev', 'rz'))
    ap.add_argument('--rebuild', action='store_true', help='重随输出已经有了也重做')
    ap.add_argument('--runs', type=int, default=200)
    a = ap.parse_args()
    seeds = sorted(d for d in glob.glob(os.path.join(a.rz, 'seed_*')) if os.path.isfile(os.path.join(d, 'regulation.bin')))
    results = [('现在的随机器输出', os.path.join(HERE, 'result.json'))]
    for d in seeds:
        name = 'rand_' + os.path.basename(d)
        if a.rebuild or not os.path.isfile(os.path.join(HERE, 'inputs', name, 'regulation.bin')):
            subprocess.run([PY, '-X', 'utf8', os.path.join(HERE, 'make_inputs.py'), '--only', 'rand', '--randomizer-dir', d, '--rand-name', name], check=True)
        out = os.path.join(HERE, 'result_%s.json' % os.path.basename(d))
        subprocess.run([PY, '-X', 'utf8', os.path.join(HERE, 'model.py'), '--runs', str(a.runs), '--rand-name', name, '--randomizer-dir', d, '--out', out],
                       check=True, stdout=subprocess.DEVNULL)
        log = sorted(glob.glob(os.path.join(d, 'spoiler_logs', '*_log_*.txt')))
        seed = os.path.basename(log[-1]).split('_log_')[1].split('_')[0] if log else '?'
        results.append(('种子 %s' % seed, out))
        print('好了：', os.path.basename(d), '种子', seed, flush=True)
    summ = {'runs': a.runs, 'rows': []}
    for label, path in results:
        if not os.path.isfile(path):
            continue
        bands, rr = ratios(path)
        summ['bands'] = bands
        summ['rows'].append({'label': label, **rr})
    json.dump(summ, open(os.path.join(HERE, 'seeds_summary.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for m, name in (('idx', '普通敌人'), ('bidx', 'Boss')):
        print('== DR 随机敌人 ÷ 原版（%s，普通难度）' % name)
        for row in summ['rows']:
            print('  %-16s %s' % (row['label'], '  '.join('%5.2f' % x if x else '   - ' for x in row[m])))


if __name__ == '__main__':
    main()
