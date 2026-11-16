# -*- coding: utf-8 -*-
"""暗黑商店分阶段解锁的区域数据（用户 2026-11-04「当玩家击败该区域的追忆boss后才解锁原版在该区域能拿到的所有战灰魔法祷告以及箭矢道具」）：
原版每件东西（战灰、法术、武器本体、箭矢）最早能在哪个区域拿到 → 那个区域的追忆 Boss（STAGES，用户选的草案）。
  - 物品位置来自随机器的 diste\\Base\\itemslots.txt（每个获取格的区域 Area、来源 shop / lot 编号），区域归属来自 annotations.txt 的 Areas（Text 的
    「 - 」前面那段）；来源编号在原版 regulation（游戏目录的 regulation.bin）里查是什么东西。
  - 一个格子要先满足 QuestReqs（区域、事件、钥匙道具，比如交了巨人的祷告书瑟濂 / 柯林才卖）：取格子本身和各条件里最晚的那个区域；
    钥匙道具按它自己最早能拿到的区域（不再往下追它的条件）。区域是 unknown 的格子不算。
  - 要拿东西换的（圆桌厅用追忆换法术、武器：格子写着「1x for Remembrance of ...」）：换的材料也算条件，按材料自己最早能拿到的区域
    （以前只看圆桌厅这个区域，蕾娜菈的满月、黑剑、米凯拉的光打完葛瑞克就解锁，2026-11-05 魔法祷告商店开局解锁时查到）。
  - 一件东西在几个地方都有：取最早的。
输出 launcher\\reroll\\data\\shop_regions.json：stages（顺序就是解锁顺序）、items {"<商店 equipType>:<编号>": 阶段序号}
（武器按本体编号 = 编号去掉强化 / 质变那几位）。rr/darkshop.py 按它给暗黑商店的行写上架标记。
用法：launcher\\python\\python.exe -X utf8 dev\\item_system\\build_shop_regions.py（只读随机器数据和原版 regulation）"""
import json
import os
import re
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402
import paramdef_min as pdm  # noqa: E402

GAME = os.path.dirname(PALY)
BASE = os.path.join(PALY, 'randomizer', 'diste', 'Base')
OUT = os.path.join(RR, 'data', 'shop_regions.json')

# (键, 区域中文, 追忆 Boss, 击败标记（data\fusion_drop.json 的追忆 Boss 战）, annotations 里的区域名)。顺序 = 解锁顺序
STAGES = [
    ('limgrave', '宁姆格福 / 威尔斯 / 史东薇尔 / 圆桌', '葛瑞克', 10000800,
     ['Chapel of Anticipation', 'Stranded Graveyard', 'Limgrave', 'Limgrave Tunnels', 'Divine Tower of Limgrave', 'Weeping Peninsula',
      'Stormhill', 'Stormveil Castle', 'Roundtable Hold']),
    ('liurnia', '利耶尼亚 / 学院', '蕾娜菈', 14000800,
     ['Liurnia', 'Academy of Raya Lucaria', 'Liurnia Behind Caria Manor', 'Moonlight Altar', 'Bellum Highway', 'Divine Tower of Liurnia',
      'Carian Study Hall', 'Stone Platform', 'Isolated Divine Tower', 'Ruin-Strewn Precipice']),
    ('caelid', '盖利德 / 龙墓', '拉塔恩', 1252380800,
     ['Caelid', 'Dragonbarrow', 'Dragonbarrow Cave', 'Caelid Catacombs', 'Divine Tower of Caelid']),
    ('siofra', '希夫拉河 / 诺克隆', '祖灵之王', 12090800, ['Siofra River', 'Siofra River via Belfries', 'Nokron, Eternal City']),
    ('altus', '亚坛高原 / 王城', '蒙葛特', 11000800,
     ['Altus Plateau', 'Capital Outskirts', 'Leyndell', 'Leyndell Catacombs', 'Subterranean Shunning-Grounds', 'Old Altus Tunnel',
      'Altus Tunnel', 'Divine Tower of East Altus', 'Divine Tower of West Altus', 'Leyndell Divine Bridge']),
    ('deeproot', '深根底层', '龙王佛提萨斯', 12030850, ['Deeproot Depths']),
    ('gelmir', '格密尔火山 / 火山官邸', '拉卡德', 16000800, ['Mt. Gelmir', 'Volcano Manor']),
    ('ainsel', '安瑟尔河 / 腐败湖', '艾丝缇', 12040800, ['Ainsel River', 'Ainsel River Downstream', 'Lake of Rot']),
    ('mountaintops', '巨人山顶 / 圣别雪原', '火焰巨人', 1052520800,
     ['Forbidden Lands', 'Mountaintops of the Giants', 'Mountaintops', 'Flame Peak', 'Consecrated Snowfield',
      'Consecrated Snowfield Catacombs', 'Hidden Path to the Haligtree']),
    ('farum', '法姆亚兹拉', '玛利喀斯', 13000800, ['Farum Azula', 'Farum Azula via Belfries']),
    ('ashen', '灰城罗德尔', '霍拉鲁', 11050800, ['Ashen Leyndell']),
    ('mohgwyn', '蒙格温王朝', '蒙格', 12050800, ['Mohgwyn']),
    ('haligtree', '圣树', '玛莲妮亚', 15000800, ['Haligtree']),
    ('gravesite', '幽影之地：墓地平原 / 贝鲁拉特', '舞狮', 20000800, ['Gravesite Plain', 'Belurat', 'Belurat Swamp', 'Ellac River', 'Fog Rift Fort']),
    ('ensis', '恩希斯城 / 幽影阿尔特斯', '蕾拉娜', 2048440800, ['Castle Ensis', 'Scadu Altus', 'Lower Scadu Altus', 'Scaduview']),
    ('fissure', '石棺裂缝', '腐败骑士', 22000800, ['Stone Coffin Fissure']),
    ('shadowkeep', '幽影城 / 标本储藏室', '梅瑟莫', 21010800, ['Shadow Keep', 'Specimen Storehouse']),
    ('rauh', '劳赫古遗迹', '罗蜜娜', 2044450800, ['Ancient Ruins of Rauh', 'Rauh Base']),
    ('abyssal', '深邃森林', '米德拉', 28000800, ['Abyssal Woods', "Midra's Manse"]),
    ('cerulean', '蓝海岸 / 指头遗迹 / 锯齿山', '梅特尔', 25000800,
     ['Cerulean Coast', 'Finger Ruins of Rhia', 'Finger Ruins of Miyr', 'Finger Ruins of Dheo', 'Finger Birthing Grounds',
      "Charo's Hidden Grave", 'Hinterland', 'Jagged Peak', 'Foot of the Jagged Peak']),
    ('scadutree', '幽影树 / 恩希尔伊林', '拉塔恩（伴侣）', 20010800, ['Scadutree Base', 'Enir-Ilim']),
]
STAGE_OF = {name: k for k, (_key, _zh, _b, _f, names) in enumerate(STAGES) for name in names}
LOT_CAT = {1: 3, 2: 0, 3: 1, 4: 2, 5: 4}      # 掉落表类别 → 商店 equipType（道具 3 / 武器 0 / 防具 1 / 护符 2 / 战灰 4）
KEEP_TYPES = (0, 3, 4)                         # 只记 武器（本体）/ 道具 / 战灰


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def parse_annotations():
    """区域 → 阶段（None = 不在任何阶段）、事件 → 条件里的词"""
    area_stage, events, cur, sect = {}, {}, None, None
    for line in open(os.path.join(BASE, 'annotations.txt'), encoding='utf-8'):
        if re.match(r'^[A-Za-z]+:', line):
            sect = line.split(':')[0]
            continue
        m = re.match(r'- Name: (\S+)', line)
        if m:
            cur = m.group(1)
            continue
        if sect == 'Areas':
            m = re.match(r'  Text: (.+)', line)
            if m and cur:
                area_stage[cur] = STAGE_OF.get(m.group(1).strip().split(' - ')[0])
        elif sect == 'Events':
            m = re.match(r'  Req: (.+)', line)
            if m and cur:
                events[cur] = [t for t in m.group(1).split() if t not in ('AND', 'OR')]
    return area_stage, events


def parse_slots():
    """[{area, reqs, src: [(shop|lot, 编号, 这一行换的材料名或 None)], names: [物品名]}]。一个格子可以有很多行（圆桌厅的追忆兑换整个是一格），材料逐行算"""
    slots, cur = [], None
    for line in open(os.path.join(BASE, 'itemslots.txt'), encoding='utf-8'):
        if line.startswith('- Key:'):
            cur = {'area': None, 'reqs': [], 'src': [], 'names': []}
            slots.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"  - '?(.+?) - (?:enemy )?(shop|lot) (\d+)\[", line)
        if m:
            cur['names'].append(m.group(1))
        mat = re.search(r'\] ?\d+x for (.+?)(?:,| - flag|$)', line.rstrip())   # 换的材料：「1x for Remembrance of the Black Blade - flag 290120」
        for kind, num in re.findall(r' - (?:enemy )?(shop|lot) (\d+)\[', line):
            cur['src'].append((kind, int(num), mat.group(1) if mat else None))
        m = re.match(r'  Area: (\S+)', line)
        if m:
            cur['area'] = m.group(1)
        m = re.match(r'  QuestReqs: (.+)', line)
        if m:
            cur['reqs'] = m.group(1).split()
    return slots


def main():
    area_stage, events = parse_annotations()
    slots = parse_slots()
    # 钥匙道具（QuestReqs 里不是区域 / 事件的词）：按名字找它自己的格子，取最早的区域
    key_stage = {}
    for s in slots:
        st = area_stage.get(s['area'])
        if st is None:
            continue
        for nm in s['names']:
            k = norm(nm)
            key_stage[k] = min(key_stage.get(k, st), st)

    def req_stage(tok, depth=0):
        if tok in area_stage:
            return area_stage[tok]
        if tok in events and depth < 4:
            vals = [req_stage(t, depth + 1) for t in events[tok]]
            vals = [v for v in vals if v is not None]
            return max(vals) if vals else None
        if tok in key_stage:
            return key_stage[tok]
        # 带编号 / 带人名的钥匙道具（irisofgrace1、academyglintstonekeythops）：取能当它开头的最长的道具名
        base = re.sub(r'\d+$', '', tok)
        cand = [k for k in key_stage if base.startswith(k) and len(k) >= 6]
        return key_stage[max(cand, key=len)] if cand else None

    erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), GAME]
    bnd = erlib.Bnd4(erlib.read_regulation(os.path.join(GAME, 'regulation.bin')))
    D = os.path.join(RR, 'data')
    sl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(D, 'ShopLineupParam.xml')))[0]}
    sg = lambda r, n: struct.unpack_from('<' + sl[n][1], r, sl[n][2])[0]
    SHOP = erlib.Param(bnd.get('ShopLineupParam.param'))
    lots = [erlib.Param(bnd.get('ItemLotParam_map.param')), erlib.Param(bnd.get('ItemLotParam_enemy.param'))]
    best, unres = {}, Counter()
    for s in slots:
        st = area_stage.get(s['area'])
        if st is None:
            continue
        for tok in s['reqs']:
            v = req_stage(tok)
            if v is None:
                unres[tok] += 1
            else:
                st = max(st, v)
        base = st
        for kind, num, mat in s['src']:
            st = max(base, key_stage.get(norm(mat), base)) if mat else base   # 这一行要换的材料也算条件
            items = []
            if kind == 'shop' and num in SHOP.rows:
                items = [(sg(SHOP.rows[num], 'equipType'), sg(SHOP.rows[num], 'equipId'))]
            elif kind == 'lot':
                for P in lots:
                    if num in P.rows:
                        items += [(LOT_CAT.get(c), i) for _k, c, i, pt in erlib.lot_slots(P.rows[num]) if i > 0 and c in LOT_CAT]
            for t, i in items:
                if t not in KEEP_TYPES:
                    continue
                if t == 0:
                    i = i // 10000 * 10000                 # 武器按本体（去掉强化、质变）
                key = '%d:%d' % (t, i)
                best[key] = min(best.get(key, st), st)
    out = {'_说明': '暗黑商店分阶段解锁（dev\\item_system\\build_shop_regions.py 生成，别手改）：stages 按解锁顺序，'
                    'items「商店 equipType:编号」→ 原版最早能拿到它的阶段（武器按本体编号）',
           'stages': [{'key': k, 'zh': zh, 'boss': b, 'flag': f, 'regions': names} for k, zh, b, f, names in STAGES],
           'items': dict(sorted(best.items(), key=lambda kv: (int(kv[0].split(':')[0]), int(kv[0].split(':')[1]))))}
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    os.replace(tmp, OUT)
    c = Counter(v for v in best.values())
    print('写好 %s：%d 件；各阶段 %s' % (OUT, len(best), '，'.join('%s %d' % (STAGES[k][0], c[k]) for k in range(len(STAGES)))))
    print('条件里认不出的词（格子数，前 15）：%s' % dict(unres.most_common(15)))


if __name__ == '__main__':
    main()
