# -*- coding: utf-8 -*-
"""各流派在不同时间点的单体输出（用户 2026-11-05「算一下现在各流派的伤害」「可以给出不同时间点的」「词条折算需要找个算法计算」）。

不用 affix_power.json 里写死的覆盖率，改成事件模拟，词条的折算是模拟跑出来的：
  - 招式：moveset.py（TAE 的时长、判定时刻；AtkParam 的动作值、固定攻击力、攻击类别、削韧）；
  - 武器：make_inputs.py 导出的 pool（和 dark_core 同一套生成），Arms.ar 算攻击力；
  - 词条：数值读当前参数（效果行的倍率、攻击类别、血量条件、法术 / 武器开关）和 runtime.txt 的规则（while / stack / on / foe_*）；
    条件增伤只算到它覆盖的那几下，命中触发按真实的命中次数累积，限时效果按触发时刻开窗，异常逐下累积、发作、抗性上涨，架势打崩了才有处决；
  - 敌人：model 这一档的中位防御 / 减伤 / 血量 / 异常抗性（普通敌人和 Boss），不算难度和随机敌人的差别。
词条怎么选：每个时间点用贪心，每次加最能提升「小怪和 Boss 输出的几何平均」的一条，直到词条位用完（依赖别的词条的连同依赖一起试）。
只算对单个敌人的伤害：多目标、闪避、防御和生存词条的价值都不在里面；「连续出招」是上限（一直尽早接招，不算走位和精力）。
用法：python -X utf8 archetype_dps.py [--out archetype_dps.json] [--only 姿态,法术]（先跑 make_inputs.py）"""
import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model  # noqa: E402
import moveset  # noqa: E402
import powertab  # noqa: E402

RR = model.RR
S = json.load(open(os.path.join(RR, 'settings.json'), encoding='utf-8'))
LIB = powertab.LIB
RAR = powertab.RAR
INPUTS = os.path.join(HERE, 'inputs')
MODE = 'DR 不随机敌人'

# 时间点：等级、武器档和强化取 result.json 这一档的中位数；护符栏含第五格；防具词条位 = 4 件 × affix_slots 的平均词条数（取整）；词条稀有度是估的
TP = [
    dict(b=0, name='前期', level=28, wt=1, up=3, tal=2, arm=3, ar=1),
    dict(b=1, name='利耶尼亚', level=61, wt=1, up=5, tal=3, arm=4, ar=1),
    dict(b=2, name='王城', level=93, wt=2, up=5, tal=4, arm=6, ar=2),
    dict(b=3, name='圣树', level=120, wt=3, up=5, tal=5, arm=6, ar=2),
    dict(b=4, name='DLC 前中', level=159, wt=4, up=5, tal=5, arm=8, ar=3),
    dict(b=5, name='DLC 后', level=187, wt=4, up=5, tal=5, arm=8, ar=3),
]
BUILD = dict(model.BUILDS)
BUILD['力量'] = {'cls': 3001, 'w': {'vit': .35, 'end': .15, 'str': .5}, 'cap': {'vit': 60, 'end': 40, 'str': 80}}
BUILD['灵巧'] = {'cls': 3000, 'w': {'vit': .35, 'end': .15, 'dex': .5}, 'cap': {'vit': 60, 'end': 40, 'dex': 80}}
BUILD['感应'] = {'cls': 3000, 'w': {'vit': .35, 'end': .1, 'luc': .4, 'dex': .15}, 'cap': {'vit': 60, 'end': 30, 'luc': 80, 'dex': 40}}

# ---- 假设（动作包和参数里读不到的）
ENEMY_HIT_EVERY = 8.0                  # 敌人打中你一下隔几秒（清心流、掉乘势层数、血狂消退）
ENEMY_ATK_EVERY = 4.0                  # 敌人出招隔几秒（防御反击、见切的机会）
HP_FRAC = 0.7                          # 打的时候平均还剩几成血
HP_LOW = 0.45                          # 带了背水 / 血涌 / 血契这种词条时，平均还剩几成血
STANCE = {'mob': 50.0, 'boss': 130.0}  # 架势（原版小怪 / 大 Boss 的常见值）
CRIT_MOTION, CRIT_TIME = 300.0, 3.0    # 打崩架势后的处决：动作值 × 武器的致命一击补正；占 3 秒（动作 + 敌人起身）
FP_FIGHT = 60.0                        # 专注预算按一场 60 秒算：专注上限 + 蓝瓶
BLUE_FLASKS = [3, 4, 5, 6, 6, 6]       # 各档一场喝几瓶蓝
FP_PER_FLASK = [80, 130, 170, 200, 220, 240]
BOW_DRAW = {50: 0.35, 51: 0.55, 53: 1.6, 55: 1.1, 56: 2.4}   # 拉弦 / 装填（动作包里只有放箭那段，这几个是估的）
ARROW_AR = [20, 40, 60, 80, 90, 100]   # 箭矢本身的物理攻击（各档常见箭）
T_SIM = 40.0
WEAPON_PCT = 0.9                       # 这一档和上一档的样本放一起取 90% 分位：这类武器里手上较好的一把
SKILL_RANK = 4                         # 战技流用第 5 强的战灰：最前面的往往是这里算不准的（按住持续耗专注的只读到每跳几点）
SPELLS = {'sorc': [4000, 4001, 4400, 4010, 4020, 4021, 4360], 'inc': [6000, 6001, 6110, 6300, 6100, 6940, 6810, 6410]}   # 常用的、放出来一发打中一下的法术

ST = {'poison': 0, 'rot': 1, 'bleed': 2, 'frost': 3, 'sleep': 4, 'madness': 5}
ELEM_WORDS = (('物理', 0), ('魔力', 1), ('火', 2), ('雷', 3), ('圣', 4))
# 周围发生什么异常才生效（ST_NAME 顺序：中毒 腐败 出血 冻伤 睡眠 发狂）
VIC_BUFF = {'when_poisoning_or_rot_occurs_in_vicinity_increas': (0, 1), 'when_blood_loss_occur_nearby_increase_damage_by': (2,),
            'when_madness_occurs_in_vicinity_increase_damage': (5,), 'sleep_in_vicinity_increases_attack_power_by_pct': (4,)}
VIC_SHOT = {'when_poisoning_or_rot_occurs_in_vicinity_relase': (0, 1), 'when_poisoning_or_rot_occurs_in_vicinity_release': (0, 1),
            'bleed_in_vicinity_activate_weak_but_sharp_windy': (2,), 'when_poisoning_or_rot_occurs_in_vicinity_call_da': (2,),
            'when_bleeding_occurs_in_vicinity_call_wind_strik': (2,)}
DEPS = {'dr_orb_flow': 'dr_orb', 'dr_orb_burst': 'dr_orb', 'dr_orb_swarm': 'dr_orb', 'dr_hawk': 'dr_orb', 'dr_recoil': 'dr_bulwark'}
SKIP_RULE = {'dr_execute', 'dr_alternate'}     # 致命一击的冲击只打身边的其他敌人；交替要穿插投掷道具，循环里没有
LOW_HP_KEYS = {'dr_blood_surge', 'dr_desperate', 'dr_blood_pact'}
Ls = None


def elem_of(zh):
    m = zh.split('伤害：', 1)
    s = m[1] if len(m) > 1 else zh
    return min(((s.find(w), e) for w, e in ELEM_WORDS if w in s), default=(0, 1))[1]


def fam_vals(key, r):
    return [float(x) for x in (LIB['gear'][key].get('vals') or {}).get(RAR[r]) or []]


def four(s, r, cast=float):
    """规则里「a,b,c,d」按稀有度取（一个数 = 都一样）"""
    v = str(s).split(',')
    return cast(v[r] if len(v) > r else v[-1])


class Row:
    """一个效果行里和输出有关的数"""
    __slots__ = ('sid', 'dealt', 'pow', 'st', 'foe', 'sa', 'subs', 'wep', 'mag', 'mir', 'state', 'throw', 'hp_le', 'hp_ge', 'dur')

    def __init__(self, sid, r):
        g = lambda f: model.gv(Ls, r, f)
        self.sid = sid
        self.dealt = np.array([g(a) * g(b) for a, b in model.SP_DEALT])
        self.pow = np.array([g(x) for x in model.SP_ATK])
        self.st = np.array([g(x) for x in model.TAL_STAT], float)
        self.foe = np.array([g(x) for x in model.SP_CUT])
        self.sa = g('saAttackPowerRate')
        self.subs = {x for x in (g('magicSubCategoryChange1'), g('magicSubCategoryChange2'), g('magicSubCategoryChange3')) if x}
        self.wep, self.mag, self.mir = g('wepParamChange'), g('magParamChange'), g('miracleParamChange')
        self.state, self.throw = g('stateInfo'), g('throwAttackParamChange')
        self.hp_le, self.hp_ge = g('conditionHp'), g('conditionHpRate')
        self.dur = g('effectEndurance')

    def applies(self, hit, tags, hp):
        if self.subs and not (self.subs & hit.subs):
            return False
        if 'cast' in tags:                     # 魔法 / 祷告只吃开了对应开关的行；wepParamChange 2 / 3 的行不加武器
            if 'sorc' in tags and not self.mag:
                return False
            if 'inc' in tags and not self.mir:
                return False
        elif self.wep in (2, 3):
            return False
        if (self.throw or self.state == 367) and 'crit' not in tags:
            return False
        if self.state == 197:                  # 突刺反击（打中正在出招的敌人）没模拟
            return False
        if self.hp_le > 0 and hp * 100 > self.hp_le:
            return False
        if self.hp_ge > 0 and hp * 100 < self.hp_ge:
            return False
        return True


class Data:
    """这一次运行的固定数据"""

    def __init__(self):
        global Ls
        cfg = {'bands_cfg': S['tier_bands'], 'map_tiers': json.load(open(os.path.join(RR, 'data', 'map_tiers.json'), encoding='utf-8')),
               'inputs': INPUTS, 'runs': 1, 'seed': 1, 'rand_name': 'rand', 'assume_over': {}, 'scn_armor': 1.0, 'scn_hp': [], 'scn_stones': []}
        model._init(cfg)
        # 模型的 400 件样本分到每种武器每档只有 10 件上下，挑出来的忽高忽低：这里用同一套生成多导一份（每档 2000 件）
        big, small = os.path.join(INPUTS, 'pool_big.tsv'), os.path.join(INPUTS, 'pool.tsv')
        if not os.path.exists(big) or os.path.getmtime(big) < os.path.getmtime(small):
            model.dr_pool.build(os.path.join(INPUTS, 'rand'), big, 2000)
        load = model.dr_pool.load
        model.dr_pool.load = lambda _p: load(big)
        self.w, self.arms, self.tals, self.ids = model._ctx(MODE)
        model.dr_pool.load = load
        Ls = model.lay('SpEffect')
        self.Sp = self.w.reg.p('SpEffectParam')
        self.M = moveset.Moves(os.path.join(INPUTS, 'plain', 'regulation.bin'))
        self._rows = {}
        self.rules = defaultdict(list)
        self.lines = defaultdict(dict)
        self.bloodrage = None
        self.tier_max = defaultdict(float)     # 规则放的伤害是按档位挂特效的，最高那档就是上限（rules.rs Data::tier）
        for line in open(os.path.join(INPUTS, 'plain', 'core', 'runtime.txt'), encoding='utf-8'):
            f = line.rstrip('\r\n').split('\t')
            if f[0] == 'rule':
                self.rules[f[1]].append((f[2], dict(x.split('=', 1) for x in f[3:] if '=' in x)))
            elif f[0] in ('quickcharge', 'crush', 'timeslip', 'deft'):
                self.lines[f[0]][int(f[1])] = float(f[3])
            elif f[0] == 'bloodrage':
                self.bloodrage = ([int(x) for x in f[2].split(',')], float(f[4]))
            elif f[0] == 'bursttier':
                self.tier_max[f[1]] = max(self.tier_max[f[1]], float(f[2]))
            elif f[0] == 'crushtier':
                self.tier_max['phys'] = max(self.tier_max['phys'], float(f[1]))
        self.items = defaultdict(list)
        for tier, lst in self.ids['w'].items():
            for it in lst:
                i = self.arms.info(it['id'])
                if i:
                    self.items[(tier, i['type'])].append(it)
        self.enemy = {}
        for b in range(6):
            ref = self.w.ref[b]
            e = self.w.enemies[b]
            rep = lambda a, ee=e: np.repeat(a, ee['w'].astype(int), axis=0)
            self.enemy[('mob', b)] = dict(defn=np.array(ref[0], float), cut=np.array(ref[1], float), hp=float(ref[3]), res=np.array(ref[4], float),
                                          rcpt=np.median(rep(e['rcpt']), axis=0), rcrt=np.median(rep(e['rcrt']), axis=0), sdef=np.median(rep(e['sdef']), axis=0))
            eb = self.w.bosses[b]
            repb = lambda a, ee=eb: np.repeat(a, ee['w'].astype(int), axis=0)
            self.enemy[('boss', b)] = dict(defn=np.median(repb(eb['def']), axis=0), cut=np.median(repb(eb['cut']), axis=0), hp=float(np.median(repb(eb['hp']))),
                                           res=np.median(repb(eb['res']), axis=0), rcpt=np.median(repb(eb['rcpt']), axis=0), rcrt=np.median(repb(eb['rcrt']), axis=0), sdef=np.median(repb(eb['sdef']), axis=0))
        self._poise = {}
        self._nm = None
        self.native = {}
        Lw = self.M.Lw
        for wid, r in self.M.P['EquipParamWeapon'].rows.items():
            if wid < 100000000:
                u = moveset.pdm.unpack(Lw, bytes(r))
                self.native.setdefault(u.get('swordArtsParamId'), u.get('behaviorVariationId'))

    def _names(self):
        if self._nm is None:
            self._nm = {}
            try:
                v = os.path.join(model.PALY, 'randomizer', 'diste', 'Vanilla', 'msg', 'zhocn', 'item_dlc02.msgbnd.dcx')
                for k, fm in moveset.erlib.read_msgbnd(v).items():
                    tab = k.split('_')[0]
                    if tab in ('ArtsName', 'GoodsName'):
                        self._nm.setdefault(tab, {}).update(fm if isinstance(fm, dict) else dict(fm))
            except Exception:
                pass
        return self._nm

    def art_name(self, sa):
        return self._names().get('ArtsName', {}).get(sa) or '战技 %d' % sa

    def magic_name(self, mid):
        return self._names().get('GoodsName', {}).get(mid) or '法术 %d' % mid

    def row(self, sid):
        sid = int(sid)
        if sid not in self._rows:
            r = self.Sp.rows.get(sid)
            self._rows[sid] = Row(sid, r) if r is not None else None
        return self._rows[sid]

    def poise(self, atk):
        if atk not in self._poise:
            a = self.M.u('AtkParam_Pc', self.M.La, atk) or {}
            self._poise[atk] = (float(a.get('atkSuperArmorCorrection', 100.0)), float(a.get('atkSuperArmor', 0.0)))
        return self._poise[atk]

    def stat_mult(self, elem, s):
        """触发词条的属性补正（rr/procs.py）：物理按力气灵巧高的、魔力智力、火圣信仰、雷灵巧；80 点 ×3"""
        stat = {0: max(s['str'], s['dex']), 1: s['mag'], 2: s['fai'], 3: s['dex'], 4: s['fai']}[elem]
        return 1 + 2.0 * self.arms.graph(0, stat) / max(self.arms.graph(0, 80), 1e-6)


def spell_scale(D, wid, lv, s, elem):
    """法器的法术补正（基数 100）：补正 × 强化系数 × 曲线（这种元素的补正曲线）"""
    a = D.arms
    r = a.W.rows[wid]
    L = a.Lw
    rf = a.RF.rows.get(model.gv(L, r, 'reinforceTypeId') + lv) or a.RF.rows.get(model.gv(L, r, 'reinforceTypeId'))
    corr = [model.gv(L, r, f) for f in ('correctStrength', 'correctAgility', 'correctMagic', 'correctFaith', 'correctLuck')]
    crate = [model.gv(a.Lr, rf, f) for f in ('correctStrengthRate', 'correctAgilityRate', 'correctMagicRate', 'correctFaithRate', 'correctLuckRate')]
    ctype = model.gv(L, r, ('correctType_Physics', 'correctType_Magic', 'correctType_Fire', 'correctType_Thunder', 'correctType_Dark')[elem])
    stat = [s['str'], s['dex'], s['mag'], s['fai'], s['luc']]
    ae = a.AE.rows.get(model.gv(L, r, 'attackElementCorrectId'))
    sname, tname = ('Strength', 'Dexterity', 'Magic', 'Faith', 'Luck'), ('Physics', 'Magic', 'Fire', 'Thunder', 'Dark')
    bonus = 0.0
    for k in range(5):
        if ae is None or not model.gv(a.La, ae, 'is%sCorrect_by%s' % (sname[k], tname[elem])):
            continue
        bonus += corr[k] * crate[k] * a.graph(ctype, stat[k])      # graph 已经是 0~1
    return 100.0 + bonus


def fp_max(s):
    """专注上限（原版曲线的近似）"""
    w = s['wil']
    return 50 + 2.4 * min(w, 20) + 7.0 * max(0, min(w, 35) - 20) + 6.0 * max(0, w - 35)


def fp_use(rate, fpmax, tp):
    """想要每秒 rate 点专注：(能放的时间比例, 喝蓝瓶之外能打的时间比例)；每瓶占 1.5 秒"""
    per, n = FP_PER_FLASK[tp['b']], BLUE_FLASKS[tp['b']]
    budget = (fpmax + n * per) / FP_FIGHT
    u = min(1.0, budget / max(rate, 1e-6))
    flasks = min(n, max(0.0, (u * rate * FP_FIGHT - fpmax) / per))
    return u, 1 - flasks * 1.5 / FP_FIGHT


def stat_view(s):
    return {k: int(round(s[k])) for k in ('str', 'dex', 'mag', 'fai', 'luc')}


# ---------------------------------------------------------------- 配置
class Built:
    """一个时间点、一种打法的固定部分：武器、招式、加点（词条再往上加）"""
    __slots__ = ('tp', 'arch', 'opt', 'item', 'wid', 'lv', 's', 'rot', 'two', 'rname', 'crit', 'sa', 'spec', 'fp', 'skill', 'lights', 'label', 'wtype')


def pick_weapon(D, tp, wtype, s, two, status, key=None):
    """这种武器：属性够得着的样本里，攻击力（法器按法术补正）WEAPON_PCT 分位那把；异常流只看带这种异常的"""
    its = [it for t in (tp['wt'], tp['wt'] - 1) for it in D.items.get((t, wtype)) or []]     # 这一档和上一档一起挑（样本少，玩家也会留着好的）
    if not its:
        return None
    st = stat_view(s)
    if two:
        st['str'] = int(st['str'] * 1.5)
    have = (st['str'], st['dex'], st['mag'], st['fai'], st['luc'])
    ok = [it for it in its if all(n <= h for n, h in zip(D.arms.info(it['id'])['req'], have))] or its
    if status:
        nst = lambda it: int((D.arms.status(it['id'], tp['up'], st)[0][list(status)] > 0).sum())
        best = max(nst(it) for it in ok)
        if best > 0:
            ok = [it for it in ok if nst(it) == best]
    if key is None:
        key = lambda it: float(D.arms.ar(it['id'], min(tp['up'], D.arms.max_level(it['id'])), st).sum())
    ok = sorted(ok, key=key)
    return ok[int(len(ok) * WEAPON_PCT)] if len(ok) > 1 else ok[0]


def melee_rot(D, b):
    mv = D.M.moves(b.wid, b.two)
    name = b.rname
    tog = lambda: moveset.Move('切换握法', 0.5, [], ('style',))
    if name == 'light':
        return mv['light']
    if name == 'charged':
        return mv['charged'] or mv['tap'] or mv['light']
    if name == 'tap':
        return mv['tap'] or mv['light']
    if name == 'style':
        return mv['light'][:3] + [tog(), tog()] if mv['light'] else None
    if name == 'jump':
        return [mv['jump_heavy']] if mv['jump_heavy'] else None
    if name == 'roll':
        return [mv['roll']] + mv['light'][:2] if mv['roll'] and mv['light'] else None
    if name == 'dash':
        return [mv['dash']] + mv['light'][:2] if mv['dash'] and mv['light'] else None
    if name == 'crouch':
        return [moveset.Move('蹲下', 0.4, [], ('crouch',))] + mv['light'][:2] if mv['light'] else None
    if name == 'guard':
        if not mv['counter'] or not mv['light']:
            return None
        rot, t = [], 0.4 + mv['counter'].dur            # 敌人一招一次防住 + 防御反击，其余时间轻击
        for k in range(8):
            m = mv['light'][k % len(mv['light'])]
            if t + m.dur > ENEMY_ATK_EVERY and rot:
                break
            rot.append(m)
            t += m.dur
        return rot + [moveset.Move('防住', 0.4, [], ('guarded',)), mv['counter']]
    raise ValueError(name)


def find_skill(D, b, st):
    """按（每秒伤害 × 专注够放的比例）给所有战灰排名，取第 SKILL_RANK + 1 强的：行为变体先用武器的，没有就用这个战技原来那把武器的"""
    M = D.M
    _sec, var = M.weapon(b.wid)
    ar = D.arms.ar(b.wid, b.lv, st)
    budget = (fp_max(b.s) + BLUE_FLASKS[b.tp['b']] * FP_PER_FLASK[b.tp['b']]) / FP_FIGHT
    Lg = moveset._lay('EquipParamGem')
    seen, best = set(), {}
    for _gid, gr in M.P['EquipParamGem'].rows.items():
        ug = moveset.pdm.unpack(Lg, bytes(gr))
        sa = ug.get('swordArtsParamId', -1)
        if sa is None or sa <= 0 or sa in seen:
            continue
        seen.add(sa)
        usa = M.u('SwordArtsParam', M.Lsa, sa)
        if usa is None:
            continue
        art = usa['swordArtsTypeNew']
        fp = max(usa['useMagicPoint_R2'], usa['useMagicPoint_R1'], usa['useMagicPoint_L2'], usa['useMagicPoint_L1'], 0) or 10
        real = lambda ms: [x for x in ms if x[0] >= 40000 and x[1].dur >= 0.8 and any(h.subs & {111, 112} for h in x[1].hits)]
        cand = real(M.skill(art, var))
        if not cand and D.native.get(sa) is not None:
            cand = real(M.skill(art, D.native[sa]))
        rate = lambda m: (sum(float((ar * np.array(h.motion) / 100.0).sum()) + sum(h.flat) for h in m.hits), m.dur)
        groups = defaultdict(list)
        for a, m in cand:
            groups[a // 10].append(m)
        pick = {g: max(ms, key=lambda m: rate(m)[0] / rate(m)[1]) for g, ms in groups.items()}
        cycles = [[pick[g] for g in (4000, 4001, 4002) if g in pick]] if 4000 in pick else []     # 按第一段起手，接后面的段
        cycles += [[pick[g]] for g in pick if g not in (4000, 4001, 4002) and g % 10 not in (1, 2)]
        for cyc in cycles:
            if not cyc:
                continue
            dmg = sum(rate(m)[0] for m in cyc)
            d = sum(m.dur for m in cyc)
            if d < 1.0:
                continue
            up = min(1.0, budget / max(fp * len(cyc) / d, 1e-6))
            if sa not in best or dmg / d * up > best[sa][0]:
                best[sa] = (dmg / d * up, cyc, fp * len(cyc), sa)
    ranked = sorted(best.values(), key=lambda x: -x[0])
    return ranked[min(SKILL_RANK, len(ranked) - 1)] if ranked else None


def setup(D, tp, arch, opt):
    wtype, bname, rname, two, status, spec = opt
    base = model.class_start(D.w.reg, BUILD[bname]['cls'])
    s = model.allocate(base[0], base[1], tp['level'], BUILD[bname])
    st = stat_view(s)
    key = None
    if rname in SPELLS:
        el = 1 if rname == 'sorc' else 2
        key = lambda it: spell_scale(D, it['id'], min(tp['up'], D.arms.max_level(it['id'])), st, el)
    item = pick_weapon(D, tp, wtype, s, two, status, key)
    if item is None:
        return None
    b = Built()
    b.tp, b.arch, b.opt, b.item, b.wid, b.s, b.two, b.rname, b.spec, b.wtype = tp, arch, opt, item, item['id'], s, two, rname, spec, wtype
    b.lv = min(tp['up'], D.arms.max_level(b.wid))
    b.fp, b.skill, b.lights, b.rot = 0, None, None, None
    D.M.P['EquipParamWeapon'].rows[b.wid] = D.arms.W.rows[b.wid]
    D.M._u.pop(('EquipParamWeapon', b.wid), None)
    b.crit = float(model.gv(D.arms.Lw, D.arms.W.rows[b.wid], 'throwAtkRate')) + 100.0
    b.sa = float(model.gv(D.arms.Lw, D.arms.W.rows[b.wid], 'saWeaponDamage'))
    b.label = ''
    if rname in SPELLS:
        best, score_ = None, -1
        budget = (fp_max(s) + BLUE_FLASKS[tp['b']] * FP_PER_FLASK[tp['b']]) / FP_FIGHT
        scales = [spell_scale(D, b.wid, b.lv, st, e) for e in range(5)]
        for mid in SPELLS[rname]:
            r = D.M.spell(mid)
            if r is None:
                continue
            mv, mp, req = r
            if req[0] > s['mag'] or req[1] > s['fai'] or req[2] > s['luc']:
                continue
            up = min(1.0, budget / max(mp / mv.dur, 1e-6))
            sc = sum(mv.hits[0].flat[k] * scales[k] for k in range(5)) / mv.dur * up
            if sc > score_:
                best, score_ = (mv, mp, mid), sc
        if best is None:
            return None
        best[0].tags |= {rname}
        b.rot, b.fp = [best[0]], best[1]
        b.label = D.magic_name(best[2])
        return b
    if rname == 'bow':
        sec, _var = D.M.weapon(b.wid)
        c = D.M.chain(sec, 36000) or {55: 0.5, 56: 1.0}.get(wtype, 0.67)
        draw = BOW_DRAW.get(wtype, 0.6)
        b.rot = [moveset.Move('射箭', draw + c, [moveset.Hit(draw, [100.0] * 5, [0.0] * 5, {105}, True, 0)], ('shot',), charge=draw)]
        return b
    if rname == 'skill':
        st2 = dict(st)
        if two:
            st2['str'] = int(st2['str'] * 1.5)
        found = find_skill(D, b, st2)
        if found is None:
            return None
        _sc, cyc, fp, sa = found
        for m in cyc:
            m.tags |= {'grip2' if two else 'grip1'}
        b.skill, b.fp = cyc, fp
        b.lights = D.M.moves(b.wid, two)['light']
        b.label = D.art_name(sa)
        return b
    b.rot = melee_rot(D, b)
    return b if b.rot else None


def fp_terms(fams, cast):
    """词条对专注的影响：(消耗倍率, 上限倍率, 不耗专注)"""
    cost, cap, free = 1.0, 1.0, False
    for k, r in fams:
        v = fam_vals(k, r)
        if k == 'decrease_cost_of_spells_and_incantations_and_dec' and cast:
            cost *= 1 - v[0] / 100.0
        elif k == 'decrease_cost_of_ashes_of_war_and_decrease_max_s' and not cast:
            cost *= 1 - v[0] / 100.0
        elif k == 'dr_orb' and cast:
            cost *= 1 - v[1] / 100.0 * v[0] * 0.5       # 平均半满
        elif k == 'max_fp_pct':
            cap *= 1 + v[0] / 100.0
        elif k == 'dr_blood_pact':
            free = True
    return cost, cap, free


# ---------------------------------------------------------------- 模拟
CRIT_HIT = moveset.Hit(0.0, [0.0] * 5, [0.0] * 5, set(), False, 0)


class Sim:
    def __init__(self, D, b, who, fams, T=T_SIM):
        self.D, self.b, self.tp, self.who, self.fams, self.T = D, b, b.tp, who, fams, T
        self.e = D.enemy[(who, b.tp['b'])]
        st = np.zeros(8)
        self.always, self.rules, self.procs, self.vic_buff, self.vic_shot = [], [], [], [], []
        self.speed, self.q_charge, self.deft, self.roll_burst = 1.0, 0.0, 0.0, 0.0
        self.dealt_all, self.buildup_mult = 1.0, 1.0
        self.kill_buff = self.crit_buff = (0.0, 1.0)
        self.src = defaultdict(float)
        for k, r in fams:
            self._compile(k, r, st)
        if b.spec in D.rules:
            for kind, kv in D.rules[b.spec]:
                self.rules.append((b.spec, 3, kind, kv))
        fs = {k: b.s[k] + st[i] for i, k in enumerate(model.STATS)}
        self.final = dict(fs)
        if b.two:
            fs['str'] = int(fs['str'] * 1.5)
        self.fs = fs
        sv = stat_view(fs)
        self.ar = D.arms.ar(b.wid, b.lv, sv)
        self.ar_sum = float(self.ar.sum())
        self.bu, self.proc = D.arms.status(b.wid, b.lv, sv)
        self.bu = self.bu * self.buildup_mult
        self.spell_base = 0.5                       # 法球乘的法器面板 ÷ 200（dark_core spellbase.rs），施法的流派下面算
        self.hp = 0.4 if b.spec == 'bloodrage' else HP_FRAC
        if any(k in LOW_HP_KEYS for k, _ in fams):
            self.hp = min(self.hp, HP_LOW)
        # 招式循环和专注
        cast = b.rname in SPELLS
        cost, cap, free = fp_terms(fams, cast)
        self.up = 1.0
        self.scales = None
        if cast:
            self.scales = np.array([spell_scale(D, b.wid, b.lv, sv, e) for e in range(5)])
            self.spell_base = float(max(self.scales[1], self.scales[4])) / 200.0   # 法杖按魔力、圣印记按圣属性的面板
            self.rot = b.rot
            if not free:
                u, live = fp_use(b.fp * cost / b.rot[0].dur, fp_max(fs) * cap, b.tp)
                self.up = u * live
        elif b.rname == 'skill':
            d = sum(m.dur for m in b.skill)
            u, live = (1.0, 1.0) if free else fp_use(b.fp * cost / d, fp_max(fs) * cap, b.tp)
            self.up = live
            ld = sum(m.dur for m in b.lights) / max(len(b.lights), 1)
            n = int(round(d * (1 - u) / max(u, 0.05) / max(ld, 0.3)))
            self.rot = b.skill + (b.lights * (n // max(len(b.lights), 1) + 1))[:n]
        else:
            self.rot = b.rot

    def _compile(self, key, r, st):
        D = self.D
        fam = LIB['gear'][key]
        v = fam_vals(key, r)
        sid = (fam.get('sp') or {}).get(RAR[r])
        spec = powertab.TABLE.get(key)
        if key in D.rules and key not in SKIP_RULE:
            for kind, kv in D.rules[key]:
                self.rules.append((key, r, kind, kv))
        if key == 'dr_steady':
            self.q_charge = D.lines['quickcharge'][r] / 100.0
        elif key == 'dr_timeslip':
            self.speed *= 1 + D.lines['timeslip'][r] / 100.0
        elif key == 'dr_crush':
            self.roll_burst = D.lines['crush'][r] / 100.0
        elif key == 'dr_deft':
            self.deft = D.lines['deft'][r] / 100.0
        elif key == 'dr_chaos':
            self.buildup_mult *= 1 + v[1] / 100.0
        elif key == 'dr_elegance':
            self.dealt_all *= (1 + v[2] / 100.0) * (1 - v[0] / v[1])        # 每 v1 秒花 v0 秒做动作
        elif key == 'this_item_was_used_during_workout_sessions_by_ra':
            self.dealt_all *= 1 + v[1] / 100.0
        elif key == 'increase_damage_with_lower_equip_load_damage_inc':
            self.dealt_all *= 1 + v[0] / 100.0                              # 流派按轻负重打
        elif key == 'after_killing_enemy_increase_damage_by_pct_for_s':
            self.kill_buff = (v[0], 1 + v[1] / 100.0)
        elif key == 'increase_attack_by_pct_for_seconds_after_critica':
            self.crit_buff = (v[0], 1 + v[1] / 100.0)
        elif key in VIC_BUFF:
            self.vic_buff.append((VIC_BUFF[key], v[0], 1 + v[1] / 100.0))
        elif key in VIC_SHOT:
            self.vic_shot.append([VIC_SHOT[key], v[1], v[0], v[2], elem_of(fam['zh']), -1e9])
        elif isinstance(spec, dict) and 'proc' in spec and 'flat' in spec:
            n, e = spec['proc']
            amount = powertab._ev(spec['flat'], v, r, 1.0) * float((S.get('trigger_damage_mult') or {}).get(key, 1.0))
            self.procs.append(dict(key=key, n=n / max(powertab.ASSUME.get('hit_accum', 1), 1), e=e, amount=amount, elem=elem_of(fam['zh'])))
        elif sid and key not in D.rules:
            row = D.row(sid)
            if row is not None:
                st += row.st
                self.always.append(row)
                c = model.gv(Ls, D.Sp.rows[int(sid)], 'cycleOccurrenceSpEffectId')
                if c > 0 and D.row(c) is not None:
                    st += D.row(c).st
                    self.always.append(D.row(c))

    def flat_damage(self, a, elem):
        """词条放出的攻击：过一遍防御和减伤"""
        e = self.e
        return float(a * model.defense_mult(a / e['defn'][elem]) * e['cut'][elem])

    def hit_damage(self, hit, tags, rows, foes, mult):
        pw, dl, sa = np.ones(5), np.ones(5), 1.0
        for row in self.always:
            if row.applies(hit, tags, self.hp):
                pw = pw * row.pow
                dl = dl * row.dealt
                sa *= row.sa
        for row in rows:
            if row is not None and row.applies(hit, tags, self.hp):
                pw = pw * row.pow
                dl = dl * row.dealt
                sa *= row.sa
        for row in foes:
            if row is not None:
                dl = dl * row.foe
        if 'cast' in tags:
            atk = np.array(hit.flat, float) * self.scales / 100.0
        elif 'crit' in tags:
            atk = self.ar * self.b.crit / 100.0 * CRIT_MOTION / 100.0
        else:
            atk = self.ar * np.array(hit.motion) / 100.0 + np.array(hit.flat)
            if 'shot' in tags:
                atk = atk.copy()
                atk[0] += ARROW_AR[self.tp['b']] * hit.motion[0] / 100.0
        atk = atk * pw
        e = self.e
        d = atk * model.defense_mult(atk / e['defn']) * e['cut'] * dl
        return float(d.sum()) * mult, sa

    def run(self):
        D, e, T, rules = self.D, self.e, self.T, self.rules
        hp_max = e['hp']
        S_ = dict(t=0.0, total=0.0, left=hp_max, kills=0, hits=0)
        stacks, stack_t = defaultdict(int), {}
        marks, marks_t = 0, -1e9
        nth, nth_t = 0, -1e9
        stack_max = {}
        for key, r, kind, kv in rules:
            if kind == 'stack' and key not in stack_max:
                m = four(kv.get('max', '1'), r, int)
                if 'max_boost_key' in kv:
                    br = next((rr for kk, rr in self.fams if kk == kv['max_boost_key']), None)
                    if br is not None:
                        m += four(kv.get('max_boost', '0'), br, int)
                stack_max[key] = m
        next_hit = ENEMY_HIT_EVERY
        every_next = {}
        thr0 = np.array(e['res'], float)
        thr = thr0.copy()
        meter, until, k_proc = np.zeros(6), np.full(6, -1.0), np.zeros(6, int)
        status_at = np.full(6, -1e9)
        vp = self.proc
        tick = (vp[:, 0] / 100.0 * hp_max + vp[:, 1]) * e['sdef']
        isdot = vp[:, 2] > 0
        itv = np.where(vp[:, 3] > 0, vp[:, 3], 1.0)
        dur, pmult = vp[:, 4], vp[:, 5]
        stance, last_hit = 0.0, -1e9
        foe_row, foe_until = None, -1e9
        timed = {}
        kill_until = crit_until = -1e9
        rr_buildup = 0
        rage, rage_t = 0, -1e9
        proc_st = [dict(acc=0, ready=0.0) for _ in self.procs]
        last_mikiri = -1e9

        def deal(x, src):
            S_['total'] += x
            S_['left'] -= x
            self.src[src] += x

        def add_buildup(amount, kinds):
            nonlocal rr_buildup
            ks = [ST[k] for k in kinds.split(',')]
            ks = [k for k in ks if np.isfinite(thr[k]) and thr[k] > 0] or ks
            meter[ks[rr_buildup % len(ks)]] += amount
            rr_buildup += 1

        def emit(ev, tags, now):
            """规则的事件：叠层、消耗层、放冲击波、挂易伤"""
            nonlocal marks, marks_t, nth, nth_t, foe_row, foe_until
            for key, r, kind, kv in rules:
                if kind == 'stack':
                    if ev in kv.get('add', '').split(',') and (not kv.get('cond') or kv['cond'] in tags):
                        stacks[key] = min(stack_max.get(key, 1), stacks[key] + 1)
                        stack_t[key] = now
                    if ev in kv.get('clear', '').split(',') or ev == kv.get('consume'):
                        stacks[key] = 0
                elif kind == 'on' and kv.get('event') == ev:
                    if kv.get('when') == 'end' and 'end' not in tags:
                        continue
                    if kv.get('cond') and kv['cond'] not in tags:
                        continue
                    if kv.get('unless') and any(x in tags for x in kv['unless'].split(',')):
                        continue
                    if 'target_take' in kv and marks <= 0:
                        continue
                    n = 1
                    if 'take' in kv:
                        tk = kv['take']
                        have = stacks[tk]
                        if have <= 0 or (kv.get('take_full') and have < stack_max.get(tk, 1)):
                            continue
                        n = have if not kv.get('take_max') else min(have, int(kv['take_max']))
                        stacks[tk] -= n
                    if 'target_has' in kv:
                        ks = [ST[x] for x in kv['target_has'].split(',')]
                        act = [x for x in ks if until[x] > now]
                        if not act:
                            continue
                        if 'target_settle' in kv:
                            for x in act:
                                if isdot[x]:
                                    deal(min(tick[x] / itv[x] * (until[x] - now) * four(kv['target_settle'], r) / 100.0, D.tier_max['hp']), '异常结算')
                        if kv.get('target_remove'):
                            for x in act:
                                until[x] = now
                    if 'target_buildup' in kv:
                        add_buildup(four(kv['target_buildup'], r), kv.get('buildup_kinds', 'poison,rot,bleed,frost'))
                    if 'burst' in kv:
                        deal(self.flat_damage(min(self.ar_sum * four(kv['burst'], r) / 100.0, D.tier_max['phys']), 0) * n, '冲击波')
                    if 'burst_flat' in kv:
                        per = four(kv['burst_flat'], r) * D.stat_mult(1, self.fs) * (self.spell_base if kv.get('burst_spell') else 1.0)
                        per *= 1 + four(kv.get('burst_grow', '0'), r) / 100.0 * n
                        deal(self.flat_damage(min(per, D.tier_max['pebble']), 1) * n, '法球')
                    if 'target_mark' in kv:
                        marks, marks_t = min(int(kv.get('mark_max', 3)), marks + 1), now
                    if 'take_pct' in kv:
                        deal(self.flat_damage(min(self.ar_sum * four(kv['take_pct'], r) / 100.0, D.tier_max['phys']), 0) * marks, '猎印')
                        marks = 0
                    if 'target_hp_pct' in kv:
                        if now - nth_t > float(kv.get('target_reset', 5)):
                            nth = 0
                        nth += 1
                        nth_t = now
                        pct = four(kv['target_hp_pct'], r)
                        if nth % int(kv.get('target_nth', 3)) == 0:
                            pct += four(kv.get('target_nth_pct', '0'), r)
                        cap = self.ar_sum * four(kv['target_cap'], r) / 100.0 if 'target_cap' in kv else float('inf')
                        deal(min(pct / 100.0 * hp_max, cap, D.tier_max['hp']), '比例伤害')
                    if 'target_fx' in kv and four(kv['target_fx'], r, int) > 0:
                        foe_row = D.row(four(kv['target_fx'], r, int))
                        foe_until = now + (foe_row.dur if foe_row else 0)
                    if 'effect' in kv and four(kv['effect'], r, int) > 0:
                        row = D.row(four(kv['effect'], r, int))
                        if row is not None:
                            timed[key] = (row, now + max(row.dur, 0))

        def advance(now, tags):
            """到 now 为止的定时事情：敌人打中你、自动射出的法球"""
            nonlocal next_hit, rage
            while next_hit <= now:
                emit('hit', tags, next_hit)
                rage = 0
                next_hit += ENEMY_HIT_EVERY
            for key, r, kind, kv in rules:
                if kind == 'on' and 'every' in kv:
                    ev = float(kv['every'])
                    tk = kv['take']
                    n0 = every_next.setdefault(key, ev)
                    while n0 <= now:
                        if stacks[tk] > 0:
                            stacks[tk] -= 1
                            per = four(kv['burst_flat'], r) * D.stat_mult(1, self.fs) * (self.spell_base if kv.get('burst_spell') else 1.0)
                            deal(self.flat_damage(min(per, D.tier_max['pebble']), 1), '法球')
                        n0 += ev
                    every_next[key] = n0

        def check_kill(now):
            nonlocal kill_until, stance, thr
            if S_['left'] <= 0:
                S_['kills'] += 1
                S_['left'] = hp_max
                kill_until = now + self.kill_buff[0]
                meter[:] = 0
                until[:] = -1
                thr = thr0.copy()
                k_proc[:] = 0
                stance = 0.0

        skill_mult = float(S['skill_damage_by_rarity']['mult'][RAR[min(self.tp['wt'], 3)]])
        i = 0
        while S_['t'] < T:
            mv = self.rot[i % len(self.rot)]
            i += 1
            t = S_['t']
            tags = set(mv.tags)
            spd = self.speed
            shift = 0.0
            if 'charged' in tags:
                shift = mv.charge * self.q_charge
            elif 'shot' in tags:
                draw_speed = 1 + self.deft + sum(four(kv['reload_speed'], r) / 100.0 * stacks[key] for key, r, kind, kv in rules if kind == 'stack' and 'reload_speed' in kv)
                shift = mv.charge - mv.charge / draw_speed
            dur_mv = (mv.dur - shift) / spd
            if 'cast' in tags:
                emit('cast_new', tags, t)
            for ev in ('style', 'jump', 'crouch'):
                if ev in tags:
                    emit(ev, tags, t)
            if 'roll' in tags:
                emit('roll', tags, t)
                if self.roll_burst:
                    deal(self.flat_damage(min(self.ar_sum * self.roll_burst, D.tier_max['phys']), 0), '冲撞')
                if t - last_mikiri >= ENEMY_ATK_EVERY:          # 敌人一招一次见切
                    last_mikiri = t
                    emit('mikiri', tags, t)
            if 'guarded' in tags:
                emit('guard_hit', tags, t)
            if 'counter' in tags:
                emit('guard_counter', tags, t)
            if mv.hits and self.b.spec == 'bloodrage':
                if t - rage_t > D.bloodrage[1]:
                    rage = 0
                rage, rage_t = min(rage + 1, len(D.bloodrage[0])), t
            crit_time = 0.0
            for h in mv.hits:
                now = t + crit_time + max(h.t - shift, 0.0) / spd
                advance(now, tags)
                htags = set(tags)
                if 100 in h.subs:
                    htags.add('charged')
                if 'skill' in tags or (h.subs & {111, 112}):
                    htags.add('skill')
                if 'shot' in tags:
                    htags.add('shot_hit')
                melee = not (htags & {'cast', 'shot'})
                if melee and 'skill' not in htags:
                    htags.add('swing')
                htags.add('air' if 'jump' in tags else 'ground')
                rows, foes = [], []
                for key, r, kind, kv in rules:
                    if kind == 'while':
                        if kv.get('cond') and kv['cond'] not in htags:
                            continue
                        if kv.get('unless') and any(x in htags for x in kv['unless'].split(',')):
                            continue
                        if 'hp_below' in kv and self.hp * 100 >= float(kv['hp_below']):
                            continue
                        if 'hp_above' in kv and self.hp * 100 < float(kv['hp_above']):
                            continue
                        if 'stack' in kv and stacks[kv['stack']] < int(kv.get('min', 1)):
                            continue
                        if 'effect' in kv and four(kv['effect'], r, int) > 0:
                            rows.append(D.row(four(kv['effect'], r, int)))
                    elif kind == 'stack' and stacks[key] > 0:
                        ids = [x for x in kv.get('fx%d' % r, '').split(',') if x]
                        if ids:
                            rows.append(D.row(ids[min(stacks[key], len(ids)) - 1]))
                    elif kind == 'foe_aura':
                        nact = int((until > now).sum())
                        ids = [x for x in kv.get('fx%d' % r, '').split(',') if x]
                        if nact and ids:
                            foes.append(D.row(ids[min(nact, len(ids)) - 1]))
                    elif kind == 'on' and 'target_mark' in kv and marks > 0 and now - marks_t < float(kv.get('mark_secs', 10)):
                        ids = [x for x in kv.get('mfx%d' % r, '').split(',') if x]
                        if ids:
                            foes.append(D.row(ids[min(marks, len(ids)) - 1]))
                if now < foe_until:
                    foes.append(foe_row)
                for row, end in timed.values():
                    if now < end:
                        rows.append(row)
                mult = self.dealt_all
                for vs, secs, m in self.vic_buff:
                    if any(now - status_at[x] < secs for x in vs):
                        mult *= m
                if now < kill_until:
                    mult *= self.kill_buff[1]
                if now < crit_until:
                    mult *= self.crit_buff[1]
                for x in range(6):
                    if until[x] > now:
                        mult *= pmult[x]
                if 'skill' in htags:
                    mult *= skill_mult
                if self.b.spec == 'bloodrage' and rage > 0:
                    rows.append(D.row(D.bloodrage[0][rage - 1]))
                d, sa_mult = self.hit_damage(h, htags, rows, foes, mult)
                deal(d, '招式')
                S_['hits'] += 1
                # 命中触发：按真实的命中次数累积
                if melee:
                    for p, ps in zip(self.procs, proc_st):
                        ps['acc'] += 1
                        if ps['acc'] >= p['n'] and now >= ps['ready']:
                            ps['acc'] = 0
                            ps['ready'] = now + p['e']
                            deal(self.flat_damage(p['amount'] * D.stat_mult(p['elem'], self.fs), p['elem']), '命中触发')
                # 规则的命中事件（可能带异常累积）
                emit('land', htags, now)
                if 'shot' in tags:
                    emit('shot_hit', htags, now)
                # 异常累积
                if melee:
                    meter += np.where(until <= now, self.bu, 0.0)
                    for x in np.nonzero((until <= now) & np.isfinite(thr) & (meter >= thr) & (thr > 0))[0]:
                        meter[x] = 0.0
                        until[x] = now + dur[x]
                        status_at[x] = now
                        k = min(k_proc[x], e['rcrt'].shape[-1] - 1)
                        thr[x] = thr0[x] * e['rcrt'][x][k] + e['rcpt'][x][k]
                        k_proc[x] += 1
                        if not isdot[x]:
                            deal(tick[x], '异常发作')
                        for key, r, kind, kv in rules:      # 碎冰
                            if kind == 'foe_react' and x == ST[kv['when']] and until[ST[kv['need']]] > now:
                                deal(min(tick[x] * four(kv['pct'], r) / 100.0, D.tier_max['hp']), '异常结算')
                                if kv.get('remove'):
                                    until[ST[kv['need']]] = now
                # 周围异常放的东西
                for vs_ in self.vic_shot:
                    vs, secs, every, am, el, last = vs_
                    if any(now - status_at[x] < secs for x in vs) and now - last >= every:
                        n = 1 if last < -1e8 else int((now - last) // every)
                        vs_[5] = now
                        deal(self.flat_damage(am * D.stat_mult(el, self.fs), el) * n, '命中触发')
                # 架势：打崩了处决
                if melee:
                    c, f = D.poise(h.atk)
                    poise = (self.b.sa * c / 100.0 + f) * sa_mult
                    if now - last_hit > 30:
                        stance = 0.0
                    last_hit = now
                    stance += poise
                    cap = STANCE['boss' if self.who == 'boss' else 'mob']
                    if 'charged' in htags and any(x[0] == 'dr_thousand' for x in rules):
                        stance += cap if self.who != 'boss' else cap * 0.3
                    if stance >= cap:
                        stance = 0.0
                        emit('break', htags, now)
                        cd, _ = self.hit_damage(CRIT_HIT, {'crit', 'swing'}, [], [foe_row] if now < foe_until else [], self.dealt_all * (self.crit_buff[1] if now < crit_until else 1.0))
                        deal(cd, '处决')
                        crit_time += CRIT_TIME
                        next_hit += CRIT_TIME
                        now += CRIT_TIME
                        crit_until = now + self.crit_buff[0]
                        emit('crit', htags, now)
                check_kill(now)
            # 这招结束：持续扣血按时间走完
            t_end = t + crit_time + dur_mv
            advance(t_end, tags)
            for x in np.nonzero(isdot)[0]:
                if until[x] > t:
                    deal(tick[x] / itv[x] * min(t_end - t, until[x] - t), '异常持续')
            check_kill(t_end)
            if mv.hits:
                emit('attack', tags, t_end)
            for key, r, kind, kv in rules:
                if kind == 'stack' and 'timeout' in kv and stacks[key] > 0 and t_end - stack_t.get(key, t_end) > float(kv['timeout']):
                    stacks[key] = 0
            if 'jump' in tags:
                emit('jland', tags | {'jatk'}, t_end)
            if 'skill' in tags:
                emit('skill', tags | {'end'}, t_end)
            S_['t'] = t_end
        t = max(S_['t'], 1e-6)
        self.src_rate = {k: v / t * self.up for k, v in self.src.items() if v > 0}
        return S_['total'] / t * self.up, S_['hits'] / t * self.up, S_['kills']


def sim_pair(D, b, fams):
    out = {}
    for who in ('mob', 'boss'):
        s = Sim(D, b, who, fams)
        dps, hps, _k = s.run()
        out[who] = dps
        out['hps'] = hps
        out['src_' + who] = {k: round(v, 1) for k, v in s.src_rate.items()}
    out['ar'] = s.ar_sum
    out['stats'] = stat_view(s.final)
    out['up'] = s.up
    out['spell'] = float(s.scales.max()) if s.scales is not None else None
    return out


# ---------------------------------------------------------------- 流派
# (武器类型, 加点, 招式循环, 双手, 优先带的异常, 武器特效)；武器取 dark_dev 的 KIT_WEAPONS
POI, ROT, BLD, FRO, SLP = 0, 1, 2, 3, 4
ARCH = {
    '属性（基准）': [(3, '力敏', 'light', False, None, None), (5, '力敏', 'light', True, None, None), (7, '力量', 'light', True, None, None), (13, '灵巧', 'light', True, None, None)],
    '姿态': [(5, '力敏', 'light', True, None, None), (5, '力敏', 'style', True, None, None), (7, '力量', 'light', True, None, None), (7, '力量', 'style', True, None, None), (13, '灵巧', 'light', True, None, None), (13, '灵巧', 'style', True, None, None)],
    '防御': [(3, '力敏', 'guard', False, None, None), (3, '力敏', 'guard', False, None, 'dr_poise_guard')],
    '反击回血': [(3, '力敏', 'light', False, None, 'bloodrage'), (9, '灵巧', 'light', False, (BLD,), 'dr_thirst')],
    '法术': [(57, '智力', 'sorc', False, None, None), (61, '信仰', 'inc', False, None, None)],
    '异常': [(13, '感应', 'light', False, (BLD, FRO), 'dr_shatter'), (1, '感应', 'light', False, (POI, ROT), 'dr_plague'), (15, '感应', 'light', False, (SLP,), 'dr_awaken'), (9, '感应', 'crouch', False, (BLD,), 'dr_charge'), (9, '感应', 'light', False, (BLD,), None)],
    '机动空战': [(7, '力量', 'jump', True, None, None), (41, '力量', 'jump', True, None, None), (23, '力量', 'jump', True, None, None), (5, '力敏', 'jump', True, None, None), (3, '力敏', 'dash', False, None, None)],
    '闪避': [(1, '灵巧', 'roll', False, None, None), (13, '灵巧', 'roll', False, None, None), (9, '灵巧', 'roll', False, None, None)],
    '战技': [(3, '力敏', 'skill', False, None, None), (5, '力敏', 'skill', True, None, None), (13, '灵巧', 'skill', True, None, None)],
    '命中连击': [(1, '灵巧', 'light', False, None, 'dr_giant'), (14, '力敏', 'light', False, None, None), (37, '灵巧', 'light', False, None, None), (35, '力敏', 'light', False, None, None), (1, '灵巧', 'light', False, None, None)],
    '重击处决': [(7, '力量', 'charged', True, None, None), (7, '力量', 'tap', True, None, None), (41, '力量', 'charged', True, None, None), (23, '力量', 'charged', True, None, None), (19, '力量', 'charged', True, None, None)],
    '远程': [(50, '灵巧', 'bow', False, None, None), (51, '灵巧', 'bow', False, None, None), (53, '力量', 'bow', False, None, None), (55, '力敏', 'bow', False, None, None), (56, '力量', 'bow', False, None, None)],
}


def arch_fams(arch):
    """这个流派能用的词条：流派自己的 + 属性类（谁都能带），停用的不算"""
    want = {'属性（基准）': ('属性',)}.get(arch, (arch, '属性'))
    return [k for k, f in LIB['gear'].items() if (f.get('archetype') or '其他') in want and any(x > 0 for x in (f.get('weight_r') or {}).get('armor', []) + (f.get('weight_r') or {}).get('talisman', []))]


def place(k, r):
    wr = LIB['gear'][k].get('weight_r') or {}
    return (wr.get('talisman', [0] * 4)[r] > 0, wr.get('armor', [0] * 4)[r] > 0)


def is_proc(k):
    s = powertab.TABLE.get(k)
    return isinstance(s, dict) and 'proc' in s


def score(x):
    return math.sqrt(max(x['mob'], 1e-6) * max(x['boss'], 1e-6))


def greedy(D, b):
    """这个时间点这一身：护符栏 + 防具词条位。每次加最能提升输出的一条；命中触发同稀有度只有一条生效，低一档的可以再带"""
    tp = b.tp
    r0 = tp['ar']
    cands = []
    for k in arch_fams(b.arch):
        sp = LIB['gear'][k].get('sp') or {}
        rs = [r for r in range(r0, -1, -1) if sp.get(RAR[r])]
        if not rs:
            continue
        cands += [(k, r) for r in rs] if is_proc(k) else [(k, rs[0])]
    tal, arm = tp['tal'], tp['arm']
    chosen, cur = [], sim_pair(D, b, [])
    base = cur

    def fits(ks):
        t, a = tal, arm
        for k, r in ks:
            ct, ca = place(k, r)
            if ca and a > 0:
                a -= 1
            elif ct and t > 0:
                t -= 1
            else:
                return None
        return t, a

    while tal + arm > 0:
        best = None
        have = {k for k, _ in chosen}
        pr = {r for k, r in chosen if is_proc(k)}
        for k, r in cands:
            if k in have or (is_proc(k) and r in pr):
                continue
            add = [(k, r)]
            dep = DEPS.get(k)
            if dep and dep not in have:
                dep_rs = [x for x in cands if x[0] == dep]
                if not dep_rs:
                    continue
                add = [dep_rs[0], (k, r)]
            if fits(add) is None:
                continue
            x = sim_pair(D, b, chosen + add)
            g = (score(x) / max(score(cur), 1e-6)) ** (1.0 / len(add))
            if best is None or g > best[0]:
                best = (g, add, x)
        if best is None or best[0] < 1.002:
            break
        tal, arm = fits(best[1])
        chosen += best[1]
        cur = best[2]
    return chosen, base, cur


def fam_name(k):
    s = LIB['gear'][k].get('suffix') or ['', k]
    return s[1] if len(s) > 1 else k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'archetype_dps.json'))
    ap.add_argument('--only', default='')
    ap.add_argument('--flasks', type=float, default=1.0, help='蓝瓶数量倍率（看法术、战技对专注预算有多敏感）')
    a = ap.parse_args()
    BLUE_FLASKS[:] = [x * a.flasks for x in BLUE_FLASKS]
    t0 = time.time()
    D = Data()
    print('数据读好了 %.0f 秒' % (time.time() - t0), flush=True)
    res = {}
    for arch, opts in ARCH.items():
        if a.only and not any(x in arch for x in a.only.split(',')):
            continue
        res[arch] = []
        for tp in TP:
            rows = []
            for opt in opts:
                b = setup(D, tp, arch, opt)
                if b is None:
                    continue
                chosen, base, cur = greedy(D, b)
                rows.append(dict(wtype=opt[0], build=opt[1], rot=opt[2], two=opt[3], spec=opt[5], label=b.label, base_mob=base['mob'], base_boss=base['boss'], mob=cur['mob'], boss=cur['boss'], hps=cur['hps'],
                                 ar=cur['ar'], spell=cur['spell'], up=cur['up'], stats=cur['stats'], src_mob=cur['src_mob'], src_boss=cur['src_boss'],
                                 fams=[('%s%s' % (fam_name(k), '' if r == tp['ar'] else '(%s)' % RAR[r][0])) for k, r in chosen]))
            rows.sort(key=lambda x: -score(x))
            e, eb = D.enemy[('mob', tp['b'])], D.enemy[('boss', tp['b'])]
            res[arch].append(dict(tp=tp['name'], level=tp['level'], mob_hp=e['hp'], boss_hp=eb['hp'], rows=rows))
            if rows:
                x = rows[0]
                print('%-8s %-8s %2d %-7s 小怪 %6.0f Boss %6.0f（裸 %6.0f / %6.0f）%.2f 下/秒 AR %.0f %s| %s' % (
                    arch, tp['name'], x['wtype'], x['rot'], x['mob'], x['boss'], x['base_mob'], x['base_boss'], x['hps'], x['ar'], x['label'], '、'.join(x['fams'])), flush=True)
    json.dump(res, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('用时 %.0f 秒，写了 %s' % (time.time() - t0, a.out))


if __name__ == '__main__':
    main()
