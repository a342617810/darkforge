# -*- coding: utf-8 -*-
"""融锻之心的 Boss 掉落（用户 2026-11-04：「追忆boss按照难度从5个开始 依次+5掉落 其余boss不掉落融锻之心 然后进入死亡难度以上才是
按照现在的boss掉落」）的数据：每场 Boss 战（击败标记）给过没有的标记、追忆 Boss 战按难度的名次。写 launcher\\reroll\\data\\fusion_drop.json，
重随的 rr/bosses.py fusion_lines 照它写 dll\\dark_core\\fusion.txt，dark_core 的 fusion 模块看击败标记发。
- Boss 战：超限锻造石那 191 场（boss_overlimit_flags.json，击败标记 → 包含的 Boss 位置），加上 boss_lots.json 里有、那边没有的
  （碎星拉塔恩、火焰巨人、死龙弗尔桑克斯、祖灵之王……）：击败标记照赐福「头目复活」列表，实体编号或野外 Boss 的 12 开头全局标记。
- 追忆 Boss 战：包含 remembrance_bosses.json 里的实体（多阶段的任一阶段，或击败标记就是它）。难度 = 所在地图的流程等级（boss_lots 的 tier，
  取这场里最大的），同一级按原版血量从低到高；名次 1 起（平时第 k 名给 5k 个，倍数在 settings 的 fusion_drop.step）。
- 标记：每场一个 death（「死亡」「不可能」里给过，两档合起来一次），追忆 Boss 战再一个 normal（平时给过）；放在击败标记所在地图块的
  后四位 7995 往下（和超限锻造石的一样挑法，跳过扫描到的引用、掉落表的获取标记、龙心脏 / 星光碎片 / 超限锻造石用过的）。生成后不能改：改了给过的会再给一次；
  新加的接着分配。
用法：python build_fusion_flags.py <used_79xx.json>（scan_79xx.py 扫的 7000~7999 段引用）"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
sys.path.insert(0, HERE)
import erlib, paramdef_min as pdm  # noqa: E402
from sc import difficulty  # noqa: E402

D = os.path.join(RR, 'data')
OUT = os.path.join(D, 'fusion_drop.json')
LOW_HI, LOW_LO = 7995, 7900


def main():
    erlib.DLL_DIRS += [os.path.join(PALY, 'randomizer'), os.path.dirname(PALY)]
    import vanilla as vsrc
    load = lambda n: json.load(open(os.path.join(D, n), encoding='utf-8'))
    from build_overlimit_flags import lot_flags
    scan = json.load(open(sys.argv[1]))
    lots = lot_flags()                     # 掉落表的获取标记（扫描里没有）
    used = set(scan['used']) | lots
    spans = [tuple(x) for x in scan['spans'] if x[1] - x[0] <= 100000]
    sd, ov, bl, rb = load('boss_selfdrop.json')['bosses'], load('boss_overlimit_flags.json')['bosses'], load('boss_lots.json')['bosses'], \
        load('remembrance_bosses.json')
    used |= {f for v in sd.values() for f in v['flags']} | {f for v in ov.values() for f in v['flags']}
    old = load('fusion_drop.json')['fights'] if os.path.exists(OUT) else {}
    taken_other = {f for v in sd.values() for f in v['flags']} | {f for v in ov.values() for f in v['flags']}
    for v in old.values():                 # 和掉落表获取标记、龙心脏 / 超限锻造石的标记撞了的不沿用，重新分
        for k in ('death', 'normal'):
            if v.get(k) in lots or v.get(k) in taken_other:
                v[k] = None
    used |= {v[k] for v in old.values() for k in ('death', 'normal') if v.get(k)}
    revive = set(difficulty.revive_flags())
    # Boss 战：击败标记 → 位置实体
    fights = {int(k): list(v['entities']) for k, v in ov.items()}
    names = {int(k): v['name'] for k, v in ov.items()}
    covered = {e for es in fights.values() for e in es} | set(fights)
    lots = {b['entity']: b for b in bl}
    extra, miss = [], []
    for e, b in sorted(lots.items()):
        if e in covered:
            continue
        f = e if e in revive else e + 200000000 if e + 200000000 in revive else None     # 野外 Boss：1052380800 → 1252380800
        if f is None:
            miss.append(b['name'])
            continue
        fights.setdefault(f, []).append(e)
        names.setdefault(f, b['name'])
        extra.append(b['name'])
    # 原版血量（同一级里排先后）
    reg = erlib.Bnd4(erlib.read_regulation(vsrc.path('regulation.bin')))
    lay, _ = pdm.layout(pdm.load(os.path.join(D, 'NpcParam.xml')))
    npc_p = erlib.Param(reg.get('NpcParam.param'))
    ent_npc = {e: n for parts in load('vanilla_enemies.json')['parts'].values() for e, n in parts if e}
    hp = lambda e: pdm.unpack(lay, npc_p.rows[ent_npc[e]])['hp'] if ent_npc.get(e) in npc_p.rows else 0
    rem_ents = {int(e) for part in ('base', 'dlc') for e in rb[part]}
    rem = []
    for f, es in fights.items():
        if f in rem_ents or set(es) & rem_ents:
            tier = max([lots[e]['tier'] for e in es if e in lots] + [0])
            rem.append((tier, sum(hp(e) for e in set(es) | ({f} & rem_ents)), f))
    rank = {f: k + 1 for k, (_t, _h, f) in enumerate(sorted(rem))}

    def alloc(f, n):
        base = f // 10000 * 10000
        got = []
        for low in range(LOW_HI, LOW_LO - 1, -1):
            c = base + low
            if c in used or any(a <= c <= b for a, b in spans):
                continue
            got.append(c)
            used.add(c)
            if len(got) == n:
                return got
        raise SystemExit('地图块 %d 的 %d~%d 里没有空号了（%s）' % (base, LOW_LO, LOW_HI, names.get(f)))
    out, new = {}, 0
    for f in sorted(fights):
        o = old.get(str(f), {})
        death = o.get('death') or alloc(f, 1)[0]
        normal = (o.get('normal') or alloc(f, 1)[0]) if f in rank else None
        new += (not o.get('death')) + (f in rank and not o.get('normal'))
        tier = max([lots[e]['tier'] for e in fights[f] if e in lots] + [o.get('tier', 0)])    # boss_lots 里没有的（2026-11-09 手补的 10 场）留着原来的
        out[str(f)] = dict(death=death, normal=normal, rank=rank.get(f, 0), tier=tier, entities=sorted(set(fights[f])), name=names.get(f, ''))
    doc = {'_说明': __doc__.split('\n')[0], 'fights': out}
    open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    print('Boss 战 %d 场（补了 boss_lots 里有、超限那边没有的 %d 场：%s；找不到击败标记的 %d 个：%s），追忆 %d 场，新分配标记 %d 个' % (
        len(out), len(extra), '、'.join(extra), len(miss), '、'.join(miss), len(rank), new))
    for f, k in sorted(rank.items(), key=lambda kv: kv[1]):
        print('  %2d. %s（等级 %d）' % (k, out[str(f)]['name'], out[str(f)]['tier']))
    print('写好', OUT)


if __name__ == '__main__':
    main()
