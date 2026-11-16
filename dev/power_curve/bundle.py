# -*- coding: utf-8 -*-
"""给 Rust 模拟（dev\\power_sim）的数据包：一种情况（原版 / DR 不随机敌人 / DR 随机敌人）一份 JSON。
读数据还是 model.py 的 World / Arms / Tals（regulation、地图、掉落表、词条效果），这里只把模拟要用的东西摊平：
敌人和 Boss 的数组、各档参考敌人、卢恩、各发现力下的掉落、武器（攻击力公式要的字段 + 各强化等级的倍率和异常）、
防具、每个特效的效果、护符、装备样本、职业、难度。无穷大写成 1e30（JSON 没有 inf）"""
import json, math, os

import numpy as np

import model as M
import powertab

BIG = 1e30


def dkey(D):
    """发现力当键（Rust 那边同样格式化：整数不带小数点）"""
    return '%g' % D


def fin(x):
    """数 / 数组 → 能写进 JSON 的（inf → 1e30）"""
    if isinstance(x, np.ndarray):
        return [fin(v) for v in x.tolist()]
    if isinstance(x, (list, tuple)):
        return [fin(v) for v in x]
    if isinstance(x, (float, np.floating)):
        x = float(x)
        return BIG if math.isinf(x) and x > 0 else -BIG if math.isinf(x) else x
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def eff_json(e):
    if e is None:
        return None
    return {k: fin(e[k]) for k in ('dealt', 'pow', 'taken', 'defr', 'hp', 'st', 'res', 'flat', 'pct', 'pcap', 'regen', 'regen_pct')}


def group_json(e):
    return {k: fin(e[k]) for k in ('hp', 'atk', 'def', 'cut', 'res', 'rcpt', 'rcrt', 'sdef', 'ebu', 'eproc', 'w')}


ST_FIELDS = ('correctType_Poison', None, 'correctType_Blood', None, 'correctType_Sleep', 'correctType_Madness')


def weapon_json(arms, wid, graphs, rts):
    """攻击力 / 异常要的字段；各强化等级的倍率、异常特效（按等级偏移后的行）"""
    r = arms.W.rows[wid]
    L, Lr, Ls = arms.Lw, arms.Lr, arms.Ls
    g = lambda f: M.gv(L, r, f)
    sname = ('Strength', 'Dexterity', 'Magic', 'Faith', 'Luck')
    tname = ('Physics', 'Magic', 'Fire', 'Thunder', 'Dark')
    ae = arms.AE.rows.get(g('attackElementCorrectId'))
    flags = [[bool(ae is not None and M.gv(arms.La, ae, 'is%sCorrect_by%s' % (sname[k], tname[t]))) for k in range(5)] for t in range(5)]
    ctype = [g(f) for f in ('correctType_Physics', 'correctType_Magic', 'correctType_Fire', 'correctType_Thunder', 'correctType_Dark')]
    stc = [g(f) if f else -1 for f in ST_FIELDS]
    graphs.update(x for x in ctype + stc if x >= 0)
    rt = g('reinforceTypeId')
    nl = arms.max_level(wid)
    levels = []
    for lv in range(nl + 1):
        rf = arms.RF.rows.get(rt + lv) or arms.RF.rows.get(rt)
        rts.add(rt + lv)
        rate = [M.gv(Lr, rf, f) for f in ('physicsAtkRate', 'magicAtkRate', 'fireAtkRate', 'thunderAtkRate', 'darkAtkRate')]
        crate = [M.gv(Lr, rf, f) for f in ('correctStrengthRate', 'correctAgilityRate', 'correctMagicRate', 'correctFaithRate', 'correctLuckRate')]
        st = []
        for k in range(3):
            sid = g('spEffectBehaviorId%d' % k)
            if sid <= 0:
                continue
            sr = arms.S.rows.get(sid + (M.gv(Lr, rf, 'spEffectId%d' % (k + 1)) if rf is not None else 0)) or arms.S.rows.get(sid)
            if sr is None:
                continue
            st.append({'bu': [float(M.gv(Ls, sr, f)) for f in M.ST_ATK], 'proc': fin(M.proc_vec(Ls, sr)),
                       'corr': bool(M.gv(Ls, sr, 'isUseStatusAilmentAtkPowerCorrect'))})
        levels.append({'rate': fin(rate), 'crate': fin(crate), 'luck': float(g('correctLuck')) * (crate[4] if rf is not None else 1.0), 'st': st})
    i = arms.info(wid)
    return {'type': i['type'], 'rar': i['rar'], 'w': float(i['w']), 'req': i['req'], 'melee': i['type'] in M.MELEE,
            'base': [float(g(f)) for f in ('attackBasePhysics', 'attackBaseMagic', 'attackBaseFire', 'attackBaseThunder', 'attackBaseDark')],
            'corr': [float(g(f)) for f in ('correctStrength', 'correctAgility', 'correctMagic', 'correctFaith', 'correctLuck')],
            'ctype': ctype, 'stc': stc, 'flags': flags, 'res': list(arms.resident(wid)), 'levels': levels}


def graph_json(arms, gid):
    r = arms.G.rows.get(gid)
    if r is None:
        return None
    G = lambda f: float(M.gv(arms.Lg, r, f))
    return {'st': [G('stageMaxVal%d' % k) for k in range(5)], 'gr': [G('stageMaxGrowVal%d' % k) for k in range(5)],
            'ad': [G('adjPt_maxGrowVal%d' % k) for k in range(5)]}


def armor_json(arms, tals, pid):
    a = arms.armor(pid)
    return {'slot': a['slot'], 'w': float(a['w']), 'cut': fin(a['cut']), 'res': fin(a['res']), 'sp': list(a['sp']),
            'has': tals.sp_effect(a['sp']) is not None}


def export(mode, cfg, out):
    """mode 的数据包写到 out，返回这种情况的敌人统计（报告用）。
    要用到的发现力：原版 = 100 + 职业感应；DR = 再加各档难度的发现力加成 × 100（和 model.py 的 job_van / job_dr 一样）"""
    M._init(cfg)
    w, arms, tals, ids = M._ctx(mode)
    nb = w.nbands
    extra = M.talisman_lots(w.reg if mode == '原版' else M.Reg(os.path.join(M.GAME, 'regulation.bin')), cfg['map_tiers'], M.band_of)
    groups = sorted({float(t.get('discovery_bonus', 0.0)) for t in cfg['tiers']})
    ds = []
    for b in M.BUILDS.values():
        luc = M.class_start(w.reg, b['cls'])[0]['luc'] if M.ASSUME['arcane_discovery'] else 0
        ds += [100 + luc] if mode == '原版' else [100 + luc + 100 * db for db in groups]
    wids, pids, aids = set(), set(), set()
    builds = {}
    for bn, b in M.BUILDS.items():
        base, start_lv, _w, _a = M.class_start(w.reg, b['cls'])
        wb = b['van'] - b['van'] % 10000
        cands = [wb + 100 * k for k in range(13) if wb + 100 * k in arms.W.rows] if M.ASSUME['vanilla_affinity'] else [b['van']]
        wids.update(cands + [b['van']])
        builds[bn] = {'w': [[k, v] for k, v in b['w'].items()], 'cap': b['cap'],   # 加点权重保持顺序（一样时先加前面的）
                      'van': b['van'], 'van_cands': cands, 'base': base, 'start_lv': start_lv}
    pool = None
    if ids is not None:
        pool = {'bias': w.pool['bias'],
                'w': {str(t): [{'id': it['id'], 'cor': it['cor'], 'req': it['req']} for it in lst] for t, lst in ids['w'].items()},
                'p': {str(t): [[pid, slot] for pid, slot in lst if slot] for t, lst in ids['p'].items()},
                'a': {str(t): lst for t, lst in ids['a'].items()}}
        for lst in ids['w'].values():
            wids.update(it['id'] for it in lst)
        for lst in ids['p'].values():
            pids.update(pid for pid, slot in lst if slot)
        for lst in ids['a'].values():
            aids.update(lst)
    van_pieces = {}
    if mode == '原版':
        for pid in arms.P.rows:
            a = arms.armor(pid)
            if a and a['slot'] and a['w'] > 0 and pid >= 100000:
                van_pieces.setdefault(a['slot'], []).append(pid)
                pids.add(pid)
    drops, mdrops = {}, {}
    for D in sorted(set(ds)):
        dd = w.drops(D)
        drops[dkey(D)] = [{'t': {str(k): v for k, v in dd[b]['t'].items()}, 's': {str(k): v for k, v in dd[b]['s'].items()}} for b in range(nb)]
        md = w.map_drops(D, cfg['map_tiers'], M.band_of, extra)
        mdrops[dkey(D)] = [[[k, i, p, src] for k, i, p, src in md.get(b, []) if k in ('t', 's', 'u')] for b in range(nb)]
        for b in range(nb):
            aids.update(dd[b]['t'])
            aids.update(i for k, i, p, _src in md.get(b, []) if k == 't')
    graphs, rts = set(), set()
    weapons = {str(i): weapon_json(arms, i, graphs, rts) for i in sorted(wids) if i in arms.W.rows}
    armors = {str(i): armor_json(arms, tals, i) for i in sorted(pids) if arms.armor(i)}
    sids = set()
    for a in armors.values():
        sids.update(a['sp'])
    for x in weapons.values():
        sids.update(x['res'])
    affix = None
    if mode == 'DR 不随机敌人':
        affix = []
        for key, fam in powertab.LIB['gear'].items():
            wr = fam.get('weight_r') or {}
            if not any(x > 0 for x in wr.get('armor', []) + wr.get('talisman', [])):
                continue
            kind, note = powertab.INFO.get(key, ('?', ''))
            sps = [(fam.get('sp') or {}).get(r) or 0 for r in powertab.RAR]
            affix.append({'key': key, 'name': (fam.get('suffix') or ['', key])[1], 'group': fam.get('group', ''), 'kind': kind, 'note': note,
                          'where': '防具 / 护符', 'sps': sps})
        for x in powertab.LIB['weapon']['special']['pool']:
            kind, note = powertab.INFO.get(x['key'], ('?', ''))
            affix.append({'key': x['key'], 'name': x['name'][0], 'group': '武器特效', 'kind': kind, 'note': note, 'where': '武器', 'sps': [x['sp']] * 4})
        for a in affix:
            sids.update(s for s in a['sps'] if s)
    effects = {str(s): eff_json(tals.sp_effect((s,))) for s in sorted(sids) if s > 0}
    tal = {}
    for t in sorted(aids):
        e = tals.effect(t)
        if e is not None:
            tal[str(t)] = {'key': list(e[0]), 'group': int(e[1]), 'eff': eff_json(e[2])}
    gl = M.lay('CalcCorrectGraph')
    g220 = w.reg.p('CalcCorrectGraph').rows[220]
    load = {k: [float(M.gv(gl, g220, '%s%d' % (f, j))) for j in range(5)] for k, f in (('st', 'stageMaxVal'), ('gr', 'stageMaxGrowVal'), ('ad', 'adjPt_maxGrowVal'))}
    data = {
        'mode': mode, 'nbands': nb,
        'enemies': [group_json(w.enemies[b]) for b in range(nb)],
        'bosses': [group_json(w.bosses[b]) if b in w.bosses else None for b in range(nb)],
        'ref': [{'def': fin(w.ref[b][0]), 'cut': fin(w.ref[b][1]), 'atk': fin(w.ref[b][2]), 'hp': float(w.ref[b][3]), 'res': fin(w.ref[b][4])}
                for b in range(nb)],
        'soul': [w.soul.get(b, 0.0) for b in range(nb)], 'boss_soul': [w.boss_soul.get(b, 0.0) for b in range(nb)],
        'count': [w.count.get(b, 0) for b in range(nb)],
        'stone_tiers': getattr(w, 'stone_tiers', None) or [],
        'drops': drops, 'mdrops': mdrops,
        'weapons': weapons, 'armors': armors, 'effects': effects, 'talismans': tal,
        'graphs': {str(i): graph_json(arms, i) for i in sorted(graphs)}, 'load_graph': load,
        'builds': builds, 'van_pieces': van_pieces, 'pool': pool, 'affix': affix, 'extra_lots': len(extra),
    }
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    return {'nbands': nb, 'count': [w.count.get(b, 0) for b in range(nb)], 'lost': [w.lost.get(b, 0) for b in range(nb)],
            'hp_median': [M.wmedian(w.enemies[b]['hp'], w.enemies[b]['w']) for b in range(nb)],
            'atk_median': [M.wmedian(w.enemies[b]['atk'].sum(1), w.enemies[b]['w']) for b in range(nb)],
            'kinds': [len(w.enemies[b]['w']) for b in range(nb)], 'boss_count': [w.boss_count.get(b, 0) for b in range(nb)],
            'boss_hp_median': [M.wmedian(w.bosses[b]['hp'], w.bosses[b]['w']) if b in w.bosses else None for b in range(nb)]}
