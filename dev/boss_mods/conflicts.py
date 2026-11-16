# -*- coding: utf-8 -*-
"""几个 Boss 模组同时加载时，参数行有没有打架（launcher\\reroll\\data\\bossmods\\*\\params.json）：
    python conflicts.py
- 两个都「新加」同一行、内容不同 → 冲突（重随按 settings 里 mods 的顺序，后面的盖前面的）
- 两个都「改」同一行、改到同一位、值不同 → 冲突；改的是不同的位 → 两个都生效，不算
- 一个加、一个改同一行 → 冲突（不该出现）
同时检查同一个特效编号（fx）两个模组带的内容是否一样。"""
import os, sys, json, glob, hashlib, collections

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, '..', '..', 'launcher', 'reroll', 'data', 'bossmods'))


def main():
    by = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(OUT, '*', 'params.json'))):
        k = os.path.basename(os.path.dirname(f))
        for r in json.load(open(f, encoding='utf-8'))['rows']:
            by[(r['param'], int(r['id']))].append((k, r))
    bad, same = [], 0
    for key, lst in sorted(by.items()):
        if len(lst) < 2:
            continue
        kinds = {r['kind'] for _k, r in lst}
        if kinds == {'add'}:
            datas = {r['data'] for _k, r in lst}
            if len(datas) == 1:
                same += 1
            else:
                bad.append((key, '都新加、内容不同', [k for k, _r in lst]))
        elif kinds == {'patch'}:
            bits = {}
            clash = False
            for k, r in lst:
                for off, mask, val in r['bits']:
                    for b in range(8):
                        if mask >> b & 1:
                            pos = off * 8 + b
                            v = val >> b & 1
                            if pos in bits and bits[pos][1] != v:
                                clash = True
                            bits[pos] = (k, v)
            if clash:
                bad.append((key, '都改、同一位值不同', [k for k, _r in lst]))
            else:
                same += 1
        else:
            bad.append((key, '一个新加一个改', ['%s:%s' % (k, r['kind']) for k, r in lst]))
    # 特效
    fx = collections.defaultdict(dict)
    for d in sorted(glob.glob(os.path.join(OUT, '*', 'fx'))):
        k = os.path.basename(os.path.dirname(d))
        for n in os.listdir(d):
            fx[n][k] = hashlib.sha1(open(os.path.join(d, n), 'rb').read()).hexdigest()
    fx_bad = [(n, v) for n, v in sorted(fx.items()) if len(set(v.values())) > 1]
    print('同一行被几个模组碰到、但不打架：%d 行' % same)
    print('参数冲突 %d 处：' % len(bad))
    for key, why, ks in bad:
        print('  %s %d：%s（%s）' % (key[0], key[1], why, ', '.join(ks)))
    print('特效同名不同内容 %d 个：%s' % (len(fx_bad), ', '.join('%s（%s）' % (n, '/'.join(v)) for n, v in fx_bad[:20])))
    return bad, fx_bad


if __name__ == '__main__':
    main()
