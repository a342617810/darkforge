# -*- coding: utf-8 -*-
"""七咒的区域（用户 2026-11-03，设计稿 超限锻造石与高难度.md §9.3）：每场 Boss 战（data\\boss_overlimit_flags.json 的击败标记）
按它第一个 Boss 位置的地图归到 7 个区域之一（随机器 annotations.txt 的 Areas：地图 → 区域文字），写 launcher\\reroll\\data\\boss_curse_regions.json
（随整合包发：正式版不带随机器也能用）。本体里 7 个区域以外的 Boss（地下世界、法姆亚兹拉、最终 Boss）按流程等级归到最接近的区域
（各区域 Boss 流程等级的中位数，一样近取前面的；用户 2026-11-09「dlc不用 本体需要」）；DLC 的不掉碎片，不写。
用法：launcher\\python\\python.exe -X utf8 build_curse_regions.py"""
import json, os, re, statistics
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
OUT = os.path.join(RR, 'data', 'boss_curse_regions.json')
# 区域（顺序就是 rr/curses.py 的区域序号，不能改）：(名字, 随机器区域文字的开头)
GROUPS = [
    ('宁姆格福 + 啜泣半岛', ('Limgrave', 'Stormhill', 'Weeping Peninsula', 'Stormveil Castle', 'Stranded Graveyard', 'Chapel of Anticipation', 'Roundtable Hold')),
    ('利耶尼亚', ('Liurnia', 'Liurnia of the Lakes', 'Raya Lucaria', 'Academy of Raya Lucaria', 'Caria Manor', 'Bellum Highway', 'Moonlight Altar', 'Ruin-Strewn Precipice')),
    ('盖利德 + 龙墓地', ('Caelid', 'Divine Tower of Caelid', 'Dragonbarrow', "Greyoll's Dragonbarrow", 'Redmane Castle', 'Sellia')),
    ('亚坛高原 + 王城', ('Altus Plateau', 'Old Altus Tunnel', 'Altus Tunnel', 'Divine Tower of East Altus', 'Capital Outskirts', 'Leyndell', 'Leyndell, Royal Capital', 'Subterranean Shunning-Grounds', 'Leyndell, Ashen Capital', 'Ashen Leyndell')),
    ('格密尔火山', ('Mt. Gelmir', 'Volcano Manor')),
    ('巨人山顶', ('Mountaintops of the Giants', 'Mountaintops', 'Forbidden Lands', 'Flame Peak')),
    ('圣别雪原 + 圣树 + 蒙格温', ('Consecrated Snowfield', 'Hidden Path to the Haligtree', 'Mohgwyn', 'Mohgwyn Palace', 'Haligtree', "Miquella's Haligtree", 'Elphael')),
]
# 随机器的区域按地图块分，这几个写成巨人山顶，实际在圣别雪原（流程等级 16~18，山顶是 12~13；用户 2026-11-09）：土龙、小黄金树。
# 同一块地图上的死之鸟 1050570800 在山顶，照随机器归巨人山顶（用户同日更正；雪原自己的死之鸟是 1048570800）
SNOWFIELD = {1050560800, 1050570850}
SNOWFIELD_REGION = 6
# DLC 的地图（不掉碎片）：幽影之地本体和它的地下城
DLC_MAPS = ('m20_', 'm21_', 'm22_', 'm25_', 'm28_', 'm40_', 'm41_', 'm42_', 'm43_', 'm61_')


def main():
    ann = open(os.path.join(PALY, 'randomizer', 'diste', 'Base', 'annotations.txt'), encoding='utf-8').read().split('\nAreas:\n', 1)[1]
    map_regions = defaultdict(Counter)
    for block in re.split(r'\n- Name: ', ann):
        t, m = re.search(r'\n  Text: (.+)', block), re.search(r'\n  Maps: (.+)', block)
        if t and m:
            for mp in m.group(1).split():
                map_regions[mp][t.group(1).split(' - ')[0].strip()] += 1
    lots = {b['entity']: b for b in json.load(open(os.path.join(RR, 'data', 'boss_lots.json'), encoding='utf-8'))['bosses']}
    fights = json.load(open(os.path.join(RR, 'data', 'boss_overlimit_flags.json'), encoding='utf-8'))['bosses']
    ent_map = {int(a): b for a, b in re.findall(r'^- ID: (\d+)\n  Map: (\S+)', open(os.path.join(PALY, 'randomizer', 'diste', 'Base', 'enemy.txt'), encoding='utf-8').read(), re.M)}
    out, cnt, other, left = {}, Counter(), 0, []
    for k, v in sorted(fights.items(), key=lambda kv: int(kv[0])):
        b = next((lots[e] for e in v['entities'] if e in lots), None)
        mp = b['map'] if b else ent_map.get(v['entities'][0])         # boss_lots 里没有的（靠自身掉落给东西的小 Boss、真正打死的古龙）按 enemy.txt 的地图
        regs = map_regions.get(mp, Counter()) if mp else Counter()
        top = regs.most_common(1)[0][0] if regs else '?'
        g = next((i for i, (_n, keys) in enumerate(GROUPS) if any(top.startswith(x) for x in keys)), None)
        if int(k) in SNOWFIELD:
            g = SNOWFIELD_REGION
        if g is None:
            left.append((k, v['name'], mp))
            continue
        out[k] = {'region': g, 'name': v['name']}
        cnt[g] += 1
    # 本体里区域以外的：按流程等级（fusion_drop.json 的 tier）归到最接近的区域
    fu = json.load(open(os.path.join(RR, 'data', 'fusion_drop.json'), encoding='utf-8'))['fights']
    tier = lambda k: (fu.get(k) or {}).get('tier') or 0
    med = {g: statistics.median([tier(k) for k, v in out.items() if v['region'] == g and tier(k)]) for g in range(len(GROUPS))}
    near = []
    for k, name, mp in left:
        if not mp or mp.startswith(DLC_MAPS) or not tier(k):
            other += 1
            continue
        g = min(med, key=lambda g: (abs(med[g] - tier(k)), g))
        out[k] = {'region': g, 'name': name, 'nearest': tier(k)}
        cnt[g] += 1
        near.append('%s（%s，等级 %d → %s）' % (name, mp, tier(k), GROUPS[g][0]))
    out = {k: out[k] for k in sorted(out, key=int)}
    doc = {'_说明': '七咒的碎片：击败标记 → 区域序号（dev\\item_system\\build_curse_regions.py 生成；区域顺序见 regions）。不在表里的 Boss 不掉碎片',
           'regions': [n for n, _k in GROUPS], 'bosses': out}
    open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    print('各区域中位等级', med)
    print('按等级归的 %d 场：%s' % (len(near), '；'.join(near)))
    print('7 个区域：%s；不掉碎片 %d 场；写好 %s' % ('、'.join('%s %d' % (GROUPS[i][0], cnt[i]) for i in range(len(GROUPS))), other, OUT))


if __name__ == '__main__':
    main()
