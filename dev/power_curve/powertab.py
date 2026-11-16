# -*- coding: utf-8 -*-
"""词条强度折算（affix_power.json）：常驻特效只是标记、靠 HKS / dark_core 规则生效的词条，按表里的表达式折成模型认的倍率。
MANUAL：特效编号 → 折算好的效果（Tals 读到这个特效就用它，不再读参数）；CHECK：词条库里有、表里没写的键。
效果的键和 model.tal_neutral 一样，另加 flat（每下额外固定伤害）、pct / pcap（每下敌人最大血量的比例 / 上限是自己攻击力的几倍）、
regen / regen_pct（每秒回血，点数 / 最大血量比例）"""
import json, math, os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RR = os.path.normpath(os.path.join(HERE, '..', '..', 'launcher', 'reroll'))
RAR = ('Common', 'Rare', 'Epic', 'Legendary')
TABLE = json.load(open(os.path.join(HERE, 'affix_power.json'), encoding='utf-8'))
ASSUME = TABLE['_假设']
LIB = json.load(open(os.path.join(RR, 'data', 'affixes', 'affixes.json'), encoding='utf-8'))


def neutral():
    return {'dealt': np.ones(5), 'pow': np.ones(5), 'taken': np.ones(5), 'defr': np.ones(5), 'hp': 1.0, 'st': np.zeros(8), 'res': np.zeros(6),
            'flat': 0.0, 'pct': 0.0, 'pcap': math.inf, 'regen': 0.0, 'regen_pct': 0.0}


def period(spec):
    """命中时触发类的触发周期（秒）：写了 proc: [N, E] 的 = max(N ÷ hit_accum × H, E)，没写的用 _假设 的 P"""
    if isinstance(spec, dict) and 'proc' in spec:
        n, e = spec['proc']
        return max(n / ASSUME.get('hit_accum', 1) * ASSUME.get('H', 1.0), e)
    return ASSUME['P']


def _ev(expr, v, r, p):
    env = {'v': v, 'r': r, 'F': ASSUME['F'], 'P': p, 'H': ASSUME.get('H', 1.0)}
    return float(eval(str(expr), {'__builtins__': {}}, env))


def effect(spec, v, r):
    """一条折算（表里的一个对象）在这个稀有度的效果（还没乘覆盖率）；none / auto → None"""
    if not isinstance(spec, dict) or 'none' in spec:
        return None
    p = period(spec)
    e = neutral()
    for k in ('dealt', 'taken'):
        if k in spec:
            x = spec[k]
            e[k] = np.array([_ev(y, v, r, p) for y in x]) if isinstance(x, list) else np.full(5, _ev(x, v, r, p))
    for k in ('hp', 'flat', 'pct', 'pcap', 'regen', 'regen_pct'):
        if k in spec:
            e[k] = _ev(spec[k], v, r, p)
    return e


def apply(acc, e, u):
    """把效果 e 按覆盖率 u 乘进 acc（倍率按 1 + u × (倍率 - 1)，加的东西按 u 倍）"""
    f = lambda m: 1.0 + u * (np.asarray(m) - 1.0)
    for k in ('dealt', 'pow', 'taken', 'defr'):
        acc[k] = acc[k] * f(e[k])
    acc['hp'] *= float(f(e['hp']))
    for k in ('flat', 'pct', 'regen', 'regen_pct'):
        acc[k] += u * e[k]
    acc['pcap'] = min(acc['pcap'], e['pcap'])


def _vals(fam, rar):
    return [float(x) for x in (fam.get('vals') or {}).get(rar) or []]


def build():
    """(MANUAL：特效编号 → (效果, 覆盖率, 键), 每条词条的说明 {键: (类型, 说明)}, 没写的键)"""
    manual, info, missing = {}, {}, []
    for key, fam in LIB['gear'].items():
        spec = TABLE.get(key)
        if spec is None:
            missing.append(key)
            continue
        if spec == 'auto':
            info[key] = ('auto', '直接读游戏参数')
            continue
        if 'none' in spec:
            info[key] = ('none', spec['none'])
            continue
        info[key] = ('manual', spec.get('note', ''))
        for r, rar in enumerate(RAR):
            sp = (fam.get('sp') or {}).get(rar)
            if sp:
                manual[int(sp)] = (effect(spec, _vals(fam, rar), r), float(spec.get('uptime', 1.0)), key)
    for x in LIB['weapon']['special']['pool']:
        spec = TABLE.get(x['key'])
        if spec is None:
            missing.append(x['key'])
            continue
        if isinstance(spec, dict) and 'none' in spec:
            info[x['key']] = ('none', spec['none'])
            continue
        info[x['key']] = ('manual', spec.get('note', '') if isinstance(spec, dict) else '')
        if isinstance(spec, dict):
            manual[int(x['sp'])] = (effect(spec, [], 3), float(spec.get('uptime', 1.0)), x['key'])
    return manual, info, missing


MANUAL, INFO, MISSING = build()
