# -*- coding: utf-8 -*-
"""按存档算伤害成长（方案 D）：读一批存档快照（启动前备份 / 存档的副本），每个角色在每个快照的等级、属性、所在地图、
装备着的武器，用角色记录（items_<格子>.txt）里的配方还原生成武器的参数行（dark_core 的 export_records 测试，和游戏里同一套 build_row），
按原版公式算攻击力，和所在地区强度的普通敌人（重随报告里的「各强度目标中位数」血量 + 模型输入里这一档的中位防御）比：一刀多少伤害、砍几刀。
再和数值模型（result.json，DR 随机敌人 普通难度）在同一档的预测比。只读：存档、记录只读，不碰 APPDATA 以外的东西也不写游戏文件。

用法（带 numpy 的 Python）：python -X utf8 save_curve.py <快照目录>... [--out save_curve.json]
快照目录 = 有 ER0000.rng（或 ER0000.sl2，或下一层 <steamid>\\ 里有）的目录，角色记录在同目录的 rec\\ 或 角色记录\\。
局限：只算武器本身的攻击力（单手、不算护符 / 防具词条 / 战灰 / 法术 / 异常 / 增益），敌人按普通难度、按所在地图的强度；
同一个快照里不同角色进度不同，能当横截面看，同一个角色多个快照能看成长。"""
import argparse, glob, json, math, os, re, subprocess, sys
from collections import defaultdict

import numpy as np

import dr_pool
import model
import savefile

HERE = model.HERE
PALY = model.PALY
OUT_REG = os.path.join(PALY, 'out', 'reroll', 'regulation.bin')
REPORT = os.path.join(PALY, 'out', 'reroll', 'reroll_report.txt')
DEFS = os.path.join(PALY, 'dll', 'dark_core')
SYN0 = 1800000000           # 还原出来的武器插进 regulation 用的编号（每个不同的配方一个）
# 容器 / 开局装备的编号段（items.txt 的 container w、startids）：段里的编号不在记录里就是不知道配方，不能按原版行算
CONT_RANGES = ((240000000, 270000000), (200000000, 202000000), (230000000, 240000000))
# 没有敌人的地图：开局的礼拜堂（按强度 1 算，刚建的角色）、圆桌厅堂（不比）
HUB = {'m10_01_00_00': ('开局礼拜堂', 1), 'm11_10_00_00': ('圆桌厅堂', None)}


def snapshots(dirs):
    """[(标签, 存档路径, 记录目录 或 None)]"""
    out = []
    for d in dirs:
        cands = [os.path.join(d, n) for n in ('ER0000.rng', 'ER0000.sl2')] + \
            sorted(glob.glob(os.path.join(d, '*', 'ER0000.rng'))) + sorted(glob.glob(os.path.join(d, '*', 'ER0000.sl2')))
        save = next((p for p in cands if os.path.isfile(p)), None)
        if save is None:
            print('跳过（没有存档）：', d)
            continue
        rec = next((os.path.join(d, n) for n in ('rec', '角色记录') if os.path.isdir(os.path.join(d, n))), None)
        out.append((os.path.basename(os.path.normpath(d)), save, rec))
    return out


def records(rec_dir, slot):
    """这个格子的记录里的武器配方（回购、商店的不算）：[配方行]"""
    p = rec_dir and os.path.join(rec_dir, 'items_%d.txt' % slot)
    if not p or not os.path.isfile(p):
        return None
    return [l.rstrip('\r\n') for l in open(p, encoding='utf-8') if l.startswith('w\t')]


def export_rows(lines, reg):
    """配方行 → (容器编号, 生成后的整行)：跑 dark_core 的 export_records 测试；
    另外返回开局武器 {编号: (配方行, 整行)}（按现在的 items.txt 种子生成，不在角色记录里的开局武器用）"""
    W = reg.p('EquipParamWeapon')
    tmp = os.path.join(HERE, 'cache', 'save_curve')
    os.makedirs(tmp, exist_ok=True)
    base, rin, rout = (os.path.join(tmp, n) for n in ('base.txt', 'rec_in.txt', 'rec_out.txt'))
    with open(base, 'w', encoding='utf-8', newline='\n') as f:
        for i in sorted(dr_pool.base_ids(DEFS)[0]):
            if i in W.rows:
                f.write('w\t%d\t%s\n' % (i, bytes(W.rows[i]).hex()))
    with open(rin, 'w', encoding='utf-8', newline='\n') as f:
        for k, l in enumerate(lines):
            f.write('%d\t%s\n' % (k, l))
    env = dict(os.environ, DR_DEFS_DIR=DEFS, DR_POOL_BASE=base, DR_REC_IN=rin, DR_REC_OUT=rout)
    r = subprocess.run([dr_pool.CARGO, 'test', '--release', '--lib', 'export_records', '--', '--ignored', '--nocapture'],
                       cwd=dr_pool.CORE_SRC, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode or not os.path.isfile(rout):
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit('还原武器参数行失败（dark_core 的 export_records 测试）')
    print(next((l.strip() for l in r.stdout.splitlines() if '记录里的装备' in l), '记录里的装备：好了'), flush=True)
    out, start = {}, {}
    for l in open(rout, encoding='utf-8'):
        k, cid, hx = l.rstrip('\n').split('\t')
        if k == 'start':
            start[int(cid)] = bytes.fromhex(hx)
        else:
            out[lines[int(k)]] = (int(cid), bytes.fromhex(hx))
    return out, start


def tile_tier(map_tiers, mp):
    """地图的强度；开放世界的小地图块（m60 / m61）不在表里时取同一层最近的块（最多隔 2 块）"""
    if mp in map_tiers:
        return map_tiers[mp]
    m = re.match(r'm(6[01])_(\d\d)_(\d\d)_(\d\d)$', mp)
    if not m:
        return None
    a, x, y, lod = m.groups()
    best = None
    for k, t in map_tiers.items():
        n = re.match(r'm(6[01])_(\d\d)_(\d\d)_(\d\d)$', k)
        if n and n.group(1) == a and n.group(4) == lod:
            d = max(abs(int(n.group(2)) - int(x)), abs(int(n.group(3)) - int(y)))
            if d <= 2 and (best is None or d < best[0]):
                best = (d, t)
    return best and best[1]


def tier_hp():
    """重随报告里普通敌人「各强度目标中位数」{强度: 血量}（开了血量曲线时才有）"""
    t = open(REPORT, encoding='utf-8').read()
    m = re.search(r'各强度目标中位数 ([0-9: ]+)', t)
    if not m:
        sys.exit('重随报告里没有「各强度目标中位数」（血量曲线没开？）')
    return {int(a): float(b) for a, b in (x.split(':') for x in m.group(1).split())}


def hp_at(hp, t):
    """强度 t 的目标中位数：报告里没有的强度按相邻两级几何插值"""
    if t in hp:
        return hp[t]
    ks = sorted(hp)
    lo = max((k for k in ks if k < t), default=ks[0])
    hi = min((k for k in ks if k > t), default=ks[-1])
    if lo == hi:
        return hp[lo]
    return hp[lo] * (hp[hi] / hp[lo]) ** ((t - lo) / (hi - lo))


def ar_req(arms, w, lv, s):
    """攻击力（arms.ar），能力需求不够时照原版扣：不够的那项属性补正到的伤害类型，补正全没了、还扣基础的 40%（力气按双手 ×1.5 比需求）"""
    v = arms.ar(w, lv, s).copy()
    i = arms.info(w)
    have = (int(s['str'] * 1.5), s['dex'], s['mag'], s['fai'], s['luc'])
    short = [k for k in range(5) if i['req'][k] > have[k]]
    if not short:
        return v
    r = arms.W.rows[w]
    L = arms.Lw
    rf = arms.RF.rows.get(model.gv(L, r, 'reinforceTypeId') + lv) or arms.RF.rows.get(model.gv(L, r, 'reinforceTypeId'))
    rate = [model.gv(arms.Lr, rf, f) for f in ('physicsAtkRate', 'magicAtkRate', 'fireAtkRate', 'thunderAtkRate', 'darkAtkRate')]
    base = [model.gv(L, r, f) for f in ('attackBasePhysics', 'attackBaseMagic', 'attackBaseFire', 'attackBaseThunder', 'attackBaseDark')]
    ae = arms.AE.rows.get(model.gv(L, r, 'attackElementCorrectId'))
    sname = ('Strength', 'Dexterity', 'Magic', 'Faith', 'Luck')
    tname = ('Physics', 'Magic', 'Fire', 'Thunder', 'Dark')
    for t in range(5):
        if ae is not None and any(model.gv(arms.La, ae, 'is%sCorrect_by%s' % (sname[k], tname[t])) for k in short):
            v[t] = base[t] * rate[t] * 0.6
    return v


def build_of(s):
    """和模型的三种加点比：力敏 / 智力 / 信仰（感应流按信仰）"""
    phys, mag, fai = max(s['str'], s['dex']), s['mag'], max(s['fai'], s['luc'])
    return '智力' if mag > max(phys, fai) else '信仰' if fai > phys else '力敏'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dirs', nargs='+')
    ap.add_argument('--out', default=os.path.join(HERE, 'save_curve.json'))
    a = ap.parse_args()
    S = json.load(open(os.path.join(model.RR, 'settings.json'), encoding='utf-8'))
    model._init({'bands_cfg': S['tier_bands']})
    map_tiers = json.load(open(os.path.join(model.RR, 'data', 'map_tiers.json'), encoding='utf-8'))
    ref = json.load(open(os.path.join(HERE, 'inputs', 'bundle_2_rand.json'), encoding='utf-8'))['ref']
    series = json.load(open(os.path.join(HERE, 'result.json'), encoding='utf-8'))['series']
    pred = {x['build']: x for x in series if x['mode'] == 'DR 随机敌人' and x['difficulty'] == '普通'}
    van = {x['build']: x for x in series if x['mode'] == '原版'}
    hp = tier_hp()

    snaps = []
    for label, save, rec in snapshots(a.dirs):
        chars = savefile.parse(save)
        for slot, c in chars.items():
            c['recs'] = records(rec, slot)
        snaps.append((label, chars))
    lines = sorted({l for _, chars in snaps for c in chars.values() for l in (c.get('recs') or [])})
    reg = model.Reg(OUT_REG)
    rows, start = export_rows(lines, reg)
    arms = model.Arms(reg)
    syn, syn_start = {}, {}
    for k, l in enumerate(sorted(rows)):
        syn[l] = SYN0 + 100 * k
        arms.W.rows[syn[l]] = rows[l][1]
    for k, (cid, row) in enumerate(sorted(start.items())):
        syn_start[cid] = SYN0 + 100 * (len(syn) + k)
        arms.W.rows[syn_start[cid]] = row

    def resolve(c, wid):
        """存档里的武器编号 → (算攻击力用的编号, 强化等级, 来源)；不知道配方的返回 None"""
        if wid in (0, savefile.EMPTY, 110000):
            return None
        lv = wid % 100
        cont = wid - wid % 10000
        if c['_map'] is not None and cont in c['_map']:
            return c['_map'][cont], lv, '生成'
        if cont in syn_start:
            return syn_start[cont], lv, '开局'
        if any(lo <= wid < hi for lo, hi in CONT_RANGES):
            return None
        base = wid - lv
        return (base, lv, '原版') if base in arms.W.rows else None

    out = []
    for label, chars in snaps:
        for slot, c in sorted(chars.items()):
            if 'error' in c:
                continue
            c['_map'] = None if c['recs'] is None else {rows[l][0]: syn[l] for l in c['recs'] if l in rows}
            s = c['stats']
            mp = c['map']
            hub = HUB.get(mp)
            t = hub[1] if hub else tile_tier(map_tiers, mp)
            b = model.band_of(t) if t is not None else None
            e_hp = hp_at(hp, t) if t is not None else None
            e_def = np.array(ref[b]['def']) if b is not None else None
            e_cut = np.array(ref[b]['cut']) if b is not None else None

            def dmg(v):
                return float((v * model.defense_mult(v / e_def) * e_cut).sum()) if e_def is not None else None

            def one(wid):
                r = resolve(c, wid)
                if r is None:
                    return None
                w, lv, src = r
                info = arms.info(w)
                v = ar_req(arms, w, lv, s)
                return {'id': wid, 'src': src, 'lv': lv, 'type': info['type'], 'melee': info['type'] in model.MELEE,
                        'usable': arms.usable(w, s), 'ar': float(v.sum()), 'ar5': [round(x, 1) for x in v], 'dmg': dmg(v)}
            right = c['equip']['right']
            act = right[c['active']['right']] if c['active']['right'] < 3 else right[0]
            cur = one(act)
            unknown = sum(1 for w in c['weapons'] if resolve(c, w) is None and w != 110000)
            gen = sum(1 for w in c['weapons'] if any(lo <= w < hi for lo, hi in CONT_RANGES))
            # 算不算进曲线：属性被改过的测试角色、没有角色记录的（别的 mod / 别的模式的老角色）、生成武器一半以上没配方的（当时记录丢了）不算
            why = None if c['stats_ok'] else '属性改过'
            if why is None and c['recs'] is None:
                why = '没有角色记录'
            if why is None and gen and unknown * 2 > gen:
                why = '记录缺（%d/%d 把生成武器没配方）' % (unknown, gen)
            best = None
            for w in c['weapons']:
                x = one(w)
                if x and x['melee'] and x['usable'] and (best is None or (x['dmg'] or x['ar']) > (best['dmg'] or best['ar'])):
                    best = x
            bd = build_of(s)
            pr, pv = pred.get(bd), van.get(bd)
            row = {'snap': label, 'slot': slot, 'level': c['level'], 'stats_ok': c['stats_ok'], 'skip': why, 'stats': s, 'map': mp,
                   'place': hub[0] if hub else None, 'tier': t, 'band': b, 'enemy_hp': e_hp, 'has_rec': c['recs'] is not None,
                   'current': cur, 'best': best, 'unknown_weapons': unknown, 'owned': len(c['weapons']), 'build': bd,
                   'model': None if pr is None or b is None else {'level': pr['level'][b], 'ar': pr['ar'][b], 'ar_p10': pr['ar_p10'][b],
                                                                    'ar_p90': pr['ar_p90'][b], 'h2k_old': pr['h2k'][b],
                                                                    'van_h2k': pv['h2k'][b] if pv else None}}
            for k in ('current', 'best'):
                x = row[k]
                if x and e_hp and x['dmg']:
                    x['h2k'] = e_hp / x['dmg']
            m = row['model']
            if m and e_hp:
                # 模型同档的攻击力按全物理、换成现在的敌人血量算砍几刀（模型的 h2k 用的是做输入时的血量）
                m['h2k_now'] = e_hp / dmg(np.array([m['ar'], 0, 0, 0, 0]))
            out.append(row)
    json.dump(out, open(a.out, 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=1)

    # 同一个角色（格子 + 名字）按快照时间列；同样的等级 + 地图 + 当前武器只列第一次
    seen = set()
    print('\n快照            格 Lv  地图(强度/档)          加点 当前右手                    攻击力  一刀 砍几刀 | 持有里最强 攻击力 砍几刀 | 模型同档 攻击力(10~90%) 等级')
    skipped = defaultdict(set)
    for r in sorted(out, key=lambda r: (r['slot'], r['snap'])):
        if r['skip']:
            skipped[r['skip'].split('（')[0]].add('%d 号格 Lv%d' % (r['slot'], r['level']))
            continue
        cur, best = r['current'], r['best']
        key = (r['slot'], r['level'], r['map'], cur and cur['id'], best and best['id'])
        if key in seen:
            continue
        seen.add(key)
        f = lambda x, k, fmt: (fmt % x[k]) if x and x.get(k) is not None else '-'
        place = r['place'] or r['map']
        tier = '%s/%s' % (r['tier'], r['band']) if r['tier'] is not None else '-'
        cw = ('%d%s+%d' % (cur['id'] - cur['lv'], {'生成': '', '开局': '开', '原版': '原'}[cur['src']], cur['lv'])) if cur else '-'
        if cur and not cur['melee']:
            cw += '(非近战)'
        elif cur and not cur['usable']:
            cw += '(需求不够)'
        m = r['model']
        print('%-15s %d %3d %-22s %-4s %-27s %6s %5s %5s | %6s %6s | %s' % (
            'now' if r['snap'] == 'current' else r['snap'][:15], r['slot'], r['level'], '%s(%s)' % (place, tier), r['build'], cw,
            f(cur, 'ar', '%.0f'), f(cur, 'dmg', '%.0f'), f(cur, 'h2k', '%.1f'), f(best, 'ar', '%.0f'), f(best, 'h2k', '%.1f'),
            '%.0f (%.0f~%.0f) Lv%d 砍%.1f（现血量）原版%.1f' % (m['ar'], m['ar_p10'], m['ar_p90'], m['level'], m.get('h2k_now', 0), m['van_h2k'] or 0)
            if m else '-'))
    for why, who in skipped.items():
        print('不算（%s）：%s' % (why, '、'.join(sorted(who))))
    print('\n→', a.out)


if __name__ == '__main__':
    main()
