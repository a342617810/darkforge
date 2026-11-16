# -*- coding: utf-8 -*-
"""超限锻造石的 Boss 掉落标记（用户 2026-11-03，设计稿 超限锻造石与高难度.md §2.2）：每场 Boss 战在每个高难度档只掉一次，
「这场在这一档掉过没有」记在会存档的事件标记里（读旧档、恢复备份时跟着回去）。
- 一场 Boss 战 = 一个击败标记：data\\boss_selfdrop.json 的 191 个 Boss 位置，击败标记一般就是实体编号（赐福「头目复活」熄灭的就是它）；
  不是的（多阶段的前一阶段：蕾娜菈一阶段、拉达冈）按随机器 enemy.txt 的 NextPhase 归到下一阶段，同一场只算一次。
- 每场两个标记（死亡、不可能），放在击败标记所在地图块（编号 ÷ 10000）的后四位 7995 往下（龙心脏、星光碎片用的是 7999~7996），
  跳过事件 / 对话 / 参数里引用过的（scratchpad 的 scan_79xx.py 全量扫的 used_79xx.json，含批量设标记的区间）和掉落表的获取标记
  （lot_flags：扫描里没有，2026-11-04 换掉了第一版里撞上的 16 个）。
- 写 launcher\\reroll\\data\\boss_overlimit_flags.json。生成后不能改：改了已经掉过的会再掉一次；新加的 Boss 接着分配。
用法：launcher\\python\\python.exe -X utf8 build_overlimit_flags.py <used_79xx.json>"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402
from rr.stage3 import next_phases  # noqa: E402
from sc import difficulty, revivefix  # noqa: E402

OUT = os.path.join(RR, 'data', 'boss_overlimit_flags.json')
TIERS = ('死亡', '不可能')
LOW_HI, LOW_LO = 7995, 7900


def lot_flags():
    """掉落表的获取标记（原版、随机器、上次重随输出的 ItemLotParam_map / enemy）：used_79xx.json 的扫描里没有它们，
    2026-11-04 发现第一版分的标记有 16 个和原版地图道具的获取标记撞了（掉过超限锻造石，那件道具就当成捡过了）"""
    import vanilla as vsrc
    out = set()
    for p in (vsrc.path('regulation.bin'), os.path.join(PALY, 'randomizer', 'regulation.bin'), os.path.join(PALY, 'out', 'reroll', 'regulation.bin')):
        if p and os.path.isfile(p):
            b = erlib.Bnd4(erlib.read_regulation(p))
            for name in ('ItemLotParam_map', 'ItemLotParam_enemy'):
                out |= {erlib.lot_flag(r) for r in erlib.Param(b.get(name + '.param')).rows.values()}
    return out - {0}


def main():
    erlib.DLL_DIRS += [os.path.join(PALY, 'randomizer'), os.path.dirname(PALY)]
    scan = json.load(open(sys.argv[1]))
    lots = lot_flags()
    used = set(scan['used']) | lots
    # 批量设标记的区间；跨几百万号的那条是 RNG Lands 公共事件 9941（只在官方调试标记 9993 / 9991 亮着时跑，起止还写反了），不算
    spans = [tuple(x) for x in scan['spans'] if x[1] - x[0] <= 100000]
    sd = json.load(open(os.path.join(RR, 'data', 'boss_selfdrop.json'), encoding='utf-8'))['bosses']
    used |= {f for v in sd.values() for f in v['flags']}
    fd = os.path.join(RR, 'data', 'fusion_drop.json')            # 融锻之心的给过标记（build_fusion_flags.py）也在这一段
    if os.path.exists(fd):
        used |= {v[k] for v in json.load(open(fd, encoding='utf-8'))['fights'].values() for k in ('death', 'normal') if v.get(k)}
    old = {}
    if os.path.exists(OUT):
        old = json.load(open(OUT, encoding='utf-8'))['bosses']
        used |= {f for v in old.values() for f in v['flags']}
    revive = set(difficulty.revive_flags())
    nxt = {}
    for a, b in next_phases(os.path.join(PALY, 'randomizer')):     # 双向：随机器写的方向不一定是「前 → 后」
        nxt.setdefault(a, b)
        nxt.setdefault(b, a)
    fights = {}
    for e, v in sorted(sd.items(), key=lambda kv: int(kv[0])):
        e = int(e)
        f = e if e in revive or nxt.get(e) not in revive else nxt[e]
        f = revivefix.DEFEAT_FIX.get(f, f)                         # 实体编号不是击败标记的（2026-11-09）
        fights.setdefault(f, {'entities': [], 'names': []})
        fights[f]['entities'].append(e)
        fights[f]['names'].append(v['name'])
    out = dict(old)
    new = fixed = 0

    def alloc(f, n, what):
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
        raise SystemExit('地图块 %d 的 %d~%d 里没有空号了（%s）' % (base, LOW_LO, LOW_HI, what))
    # 以前分的和掉落表获取标记撞了的：只换撞了的那几个（2026-11-04）
    for k, v in out.items():
        for i, fl in enumerate(v['flags']):
            if fl in lots:
                v['flags'][i] = alloc(int(k), 1, v['name'])[0]
                fixed += 1
    for f, v in sorted(fights.items()):
        if str(f) in out:
            continue
        out[str(f)] = {'flags': alloc(f, len(TIERS), v['names']), 'entities': v['entities'], 'name': ' / '.join(dict.fromkeys(v['names']))}
        new += 1
    doc = {'_说明': '超限锻造石的 Boss 掉落标记（dev\\item_system\\build_overlimit_flags.py 生成）：击败标记 → 这场在「死亡」「不可能」各掉过没有'
                    '（flags 两个，各在击败标记所在地图块的 xxxx79xx）、这场包含的 Boss 位置实体。生成后不能改：改了已经掉过的会再掉一次；新加的接着分配',
           'tiers': list(TIERS), 'bosses': {k: out[k] for k in sorted(out, key=int)}}
    open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    print('Boss 战 %d 场（新分配 %d 场，换掉和掉落表撞的标记 %d 个），标记 %d 个；写好 %s' % (
        len(out), new, fixed, sum(len(v['flags']) for v in out.values()), OUT))


if __name__ == '__main__':
    main()
