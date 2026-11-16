# -*- coding: utf-8 -*-
"""按难度渐进推图的战斗力曲线（只读，不改任何游戏文件）。

每个地区档位（settings.json 的 tier_bands：前期 → 利耶尼亚/盖利德/亚坛 → … → DLC 后期）算玩家「打到这一档一半时」的状态，
对这一档的普通敌人（原版地图里放普通敌人的那批位置，和 enemy_hp_align 用的同一批）算两个数：
  砍几刀（h2k）= 敌人实际血量 ÷ 玩家一刀的伤害；能挨几下（h2d）= 玩家血量 ÷ 敌人一下的伤害；
  战斗力指数 = 能挨几下 ÷ 砍几刀（越大越轻松），每档取这一档所有位置的中位数。
三种情况：原版（游戏自带 regulation + 原版地图，玩家用原版长剑按常见进度强化）/ DR 不随机敌人 / DR 随机敌人；
DR 两种按 8 档局内难度各算一遍（卢恩、发现力加成影响等级和掉落；敌人血量 / 伤害倍率直接乘在结果上）。
DR 的掉落运气用蒙特卡洛：每次模拟按这一档的真实掉落表（普通敌人按击杀数、宝箱 / 拾取 / Boss 奖励按概率，含发现力）
抽未鉴定物品（武器 / 防具 / 护符 × 稀有度）和锻造石，鉴定时从装备样本（dr_pool.py：dark_core 自己的生成代码出的，
和游戏里鉴定是同一套；武器照游戏按加点偏向挑）里抽一件；开局装备、免费许愿也算。取 10% / 50% / 90% 分位。
词条：常驻特效本身带数值的直接读参数，靠 HKS / dark_core 规则生效的按 affix_power.json 的折算（powertab.py），
折算能给固定伤害（flat）、按敌人血量的伤害（pct）、回血（regen），这三样只有 DR 有。

敌人：实际血量 = 参数血量 × 参数自带特效的血量倍率 × 随机器运行时挂的缩放效果（和 rr/stage3.py 一样）；
      攻击 = 这种敌人所有攻击动作（BehaviorParam 2亿 + 行为组 ×1000 + n → AtkParam_Npc）里总攻击力的中位那一招 × 攻击倍率；
      防御 = 参数防御 × 防御倍率，减伤 = 特效的减伤倍率连乘。
玩家：卢恩 → 等级（原版升级公式），按加点方案分配；攻击力按原版公式（强化倍率、补正曲线、属性对应关系）算，单手；
      能用 = 双手持（力气 ×1.5）够需求；只用近战武器；伤害按原版防御公式（攻击 / 防御比值的分段曲线）。
护符：原版按掉落表里的原版护符（宝箱 / 尸体 / 地上拾取 / Boss 奖励 / 敌人掉落，任务奖励、商店不算），DR 按未鉴定护符，
      按各档的护符栏数挑最好的几件；效果从护符的特效参数读（攻击、受到伤害、血量、属性），条件效果按覆盖率折算。
防具词条：防具的常驻特效和护符同样读法（同一个特效防具 + 护符只生效一次），挑防具时一起比较。
异常：玩家武器的出血 / 冻伤 / 毒 / 腐败 / 发狂和敌人攻击带的异常都逐击模拟（敌人抗性、发作后抗性上涨、玩家的基础抗性 + 防具抗性）；
      原版长剑在 13 种质变里挑。难度倍率只乘在攻击伤害上，异常不受难度影响（整合包就是这么做的），所以每档难度分开算。
主要假设（ASSUME，改这里就行）见下面；所有假设对三种情况一视同仁，所以曲线适合横向比较，不适合当绝对难度。
用法：先 python make_inputs.py（副本上跑两次重随 + 导出装备样本，写在 inputs\\），再 python model.py [--runs 300] [--jobs 10]，
最后 python report.py。（用带 numpy 的 Python；整合包自带的 Python 没有 numpy。任务分给 --jobs 个进程并行，种子固定，结果和单进程一样）"""
import argparse, glob, json, math, os, random, struct, sys
from collections import Counter, defaultdict

import numpy as np

import dr_pool
import powertab

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
RD = os.environ.get('DR_RANDOMIZER_DIR') or os.path.join(PALY, 'randomizer')     # 随机敌人用的随机器输出（--randomizer-dir 设环境变量，子进程也认）
GAME = os.path.normpath(os.path.join(PALY, '..'))
sys.path.insert(0, RR)
import erlib, emevd, paramdef_min as pdm  # noqa: E402
erlib.DLL_DIRS += [RD, GAME]

ASSUME = {
    'kill_ratio': 1.0,                # 小怪清除率：推图时每个普通敌人杀几次（1 = 都杀一遍，2 = 刷了一倍；不算黄金卢恩）
    'boss_ratio': 1.0,                # Boss 清除率：杀几成 Boss（卢恩、Boss 奖励按这个比例拿；打 Boss 的评估照旧按这一档所有 Boss）
    'treasure_ratio': None,           # 宝箱 / 尸体 / 地上拾取拿几成（None = 跟小怪清除率走，最多 1：清图清得少的人宝箱也拿得少）
    'player_def': (45.0, 0.62),       # 玩家各属性的基础防御 ≈ a + b × (等级 - 1)
    'vanilla_upgrade': [6, 12, 18, 23, 25, 25],     # 原版玩家各档打到一半时的武器强化等级（+25 制）
    'vanilla_armor_pct': 0.75,        # 原版玩家各部位穿「负重放得下的防具里减伤排 75% 分位」的那件
    'dlc_blessing': [0, 0, 0, 0, 8, 16],            # 各档幽影树庇佑等级（只有 DLC 两档）
    'blessing_dealt': 0.04, 'blessing_taken': 0.025,  # 每级庇佑：造成伤害 +4%，受到伤害 ÷(1 + 2.5%×等级)
    'arcane_discovery': True,         # 发现力 = 100 + 感应（+ 难度加成 × 100）
    'load_ratio': 0.69,               # 中负重
    'slot_share': {'head': 0.2, 'body': 0.42, 'arm': 0.15, 'leg': 0.23},
    'talisman_slots': [1, 2, 3, 4, 4, 4],         # 原版各档打到一半时的护符栏数（护符皮带：大树守卫 / 恩雅 / 葛弗雷金色幻影）；DR 有第五个护符槽（dll\dark_slot）就 +1
    'talisman_uptime': {                          # 条件效果的覆盖率（效果 = 1 + 覆盖率 ×（倍率 - 1））；表里没有的条件（只对法术 / 弓箭 / 骑马、轻负重、灵体死亡等）按 0
        'motion': 0.25,          # 只对某类动作：蓄力、跳劈、防御反击、连段最后一击、战技、双手、翻滚后、冲刺、致命一击
        'full_hp': 0.5, 'low_hp': 0.1,            # 满血时 / 低血时
        'on_hit': 0.5, 'on_kill': 0.5,            # 连续命中叠起来的 / 击杀后的限时加成
        'nearby_status': 0.25,   # 附近发生出血 / 腐败 / 冻伤 / 发狂 / 睡眠时
    },
    # 异常状态：逐击模拟（累积 → 发作 → 敌人抗性按 ResistCorrectParam 上涨），持续扣血按时间折算
    'hit_interval': 1.0,         # 玩家每一下隔几秒（中毒 / 腐败这种持续扣血每一下折多少）
    'enemy_hit_interval': 4.0,   # 敌人打中你一下隔几秒（你身上的持续扣血每挨一下折多少）
    'status_sim_hits': 60,       # 逐击模拟最多算多少下，之后按最后 20 下的平均伤害外推
    'vanilla_affinity': True,    # 原版长剑在 13 种质变里挑（含出血 / 冻伤 / 毒），False = 用 BUILDS 里写死的质变
    # DR（新装备系统）
    'free_wishes': {0: 30},      # 免费许愿在哪一档用掉几次（每个角色送 30 次，按前期一次用完算；付费许愿和暗黑商店不算，卢恩都拿去升级）
    'start_armor_tiers': [0, 1, 2],      # 开局防具每个部位的稀有度在这几档里平均抽（rr/startgear.py：普通 ~ 史诗，2026-11-02 起不出传说）
    'start_weapon_tier': 0,      # 开局武器：普通（2026-11-02 起，以前稀有），按职业加点偏向
    'target_ratio': [1.0, 1.5],  # 目标：DR 普通难度的战斗力指数是原版的几倍（报告按这个算各档敌人血量该怎么调）
    # Boss：和打普通敌人同一身装备；能挨几下算上圣杯瓶
    'boss_flasks': [3, 5, 7, 9, 10, 10],   # 各档打 Boss 时带几瓶红露滴（原版常见进度：黄金种子 + 一半分给蓝露滴）
    'flask_heal': 0.5,           # 每瓶回血量上限的几成（原版红露滴 +0 约 250、+12 约 1000，和同期血量的比例差不多一半）
    'boss_target_ratio': [1.0, 1.5],   # 目标：DR 普通难度打 Boss 的指数是原版的几倍（对应 settings 的 enemy_hp_band.boss）
}
UNID0 = 9200                     # 未鉴定物品：9200 + 类别（0 武器 / 1 防具 / 2 护符）× 10 + 档（0~4，4 = 传说（幽影之地））
POOL_W0, POOL_P0 = 1900000000, 1950000000    # 装备样本插进 regulation 时用的编号（武器 / 防具）
BUILDS = {   # 职业（CharaInitParam）+ 加点权重（每升一级加给「已加点 ÷ 权重」最小的属性）+ 上限 + 原版对照用的长剑质变
    '力敏': {'cls': 3000, 'w': {'vit': .35, 'end': .15, 'str': .25, 'dex': .25}, 'cap': {'vit': 60, 'end': 40, 'str': 80, 'dex': 80}, 'van': 2000000},
    '智力': {'cls': 3004, 'w': {'vit': .35, 'wil': .1, 'end': .05, 'mag': .4, 'dex': .1}, 'cap': {'vit': 60, 'wil': 35, 'end': 25, 'mag': 80, 'dex': 40}, 'van': 2000800},
    '信仰': {'cls': 3005, 'w': {'vit': .35, 'wil': .1, 'end': .05, 'fai': .4, 'str': .1}, 'cap': {'vit': 60, 'wil': 35, 'end': 25, 'fai': 80, 'str': 40}, 'van': 2000700},
}
STATS = ('vit', 'wil', 'end', 'str', 'dex', 'mag', 'fai', 'luc')
TYPES = ('phys', 'mag', 'fire', 'thun', 'dark')
SCALE_EVENT, SCALE_EVENT_NOW = 9005890, 9005891
# 每个稀有度 +1 ~ +5 要的锻造石（settings.json 的 weapon_upgrade.stones，rr/upgrade.py）
_UPG = (json.load(open(os.path.join(RR, 'settings.json'), encoding='utf-8')).get('weapon_upgrade') or {}).get('stones') or {}
UPGRADE_STONES = {k: _UPG.get(r) or d for k, (r, d) in enumerate((
    ('Common', [10100, 10101, 10102, 10103, 10104]), ('Rare', [10160, 10161, 10162, 10163, 10164]),
    ('Epic', [10104, 10105, 10106, 10107, 10140]), ('Legendary', [10165, 10166, 10167, 10200, 10168])))}
MELEE = {1, 3, 5, 7, 9, 11, 13, 14, 15, 16, 17, 19, 21, 23, 24, 25, 28, 29, 31, 35, 37, 39, 41, 88, 92, 93, 94, 95}


# ---------------------------------------------------------------- 参数读取
_LAYS = {}


def lay(name):
    if name not in _LAYS:
        p = os.path.join(RR, 'data', name + '.xml')
        if not os.path.isfile(p):
            p = os.path.join(HERE, 'defs', name + '.xml')
        _LAYS[name] = {n: (o, fc, bp, bits) for n, fc, o, bp, bits, _ in pdm.layout(pdm.load(p))[0]}
    return _LAYS[name]


def gv(L, row, f):
    o, fc, bp, bits = L[f]
    v = struct.unpack_from('<' + fc, row, o)[0]
    return (v >> bp) & ((1 << bits) - 1) if bits else v


class Reg:
    def __init__(self, path):
        self.path = path
        self.bnd = erlib.Bnd4(erlib.read_regulation(path))
        self._p = {}

    def p(self, name):
        if name not in self._p:
            self._p[name] = erlib.Param(self.bnd.get(name + '.param'))
        return self._p[name]


def defense_mult(ratio):
    """原版的攻防比曲线（攻击 / 防御 → 伤害倍率）"""
    r = np.asarray(ratio, dtype=float)
    return np.where(r > 8, 0.9, np.where(r > 2.5, 0.9 - 0.2 * ((8 - r) / 5.5) ** 2, np.where(
        r > 1, 0.7 - 0.3 * ((2.5 - r) / 1.5) ** 2, np.where(r > 0.125, 0.1 + 0.3 * ((r - 0.125) / 0.875) ** 2, 0.1))))


# ---------------------------------------------------------------- 敌人
SP_HP = 'maxHpRate'
SP_ATK = ('physicsAttackPowerRate', 'magicAttackPowerRate', 'fireAttackPowerRate', 'thunderAttackPowerRate', 'darkAttackPowerRate')
SP_DEF = ('physicsDiffenceRate', 'magicDiffenceRate', 'fireDiffenceRate', 'thunderDiffenceRate', 'darkDiffenceRate')
SP_CUT = ('neutralDamageCutRate', 'magicDamageCutRate', 'fireDamageCutRate', 'thunderDamageCutRate', 'darkDamageCutRate')
NPC_DEF = ('def_phys', 'def_mag', 'def_fire', 'def_thunder', 'def_dark')
ATK_F = ('atkPhys', 'atkMag', 'atkFire', 'atkThun', 'atkDark')
# 异常状态：中毒 / 腐败 / 出血 / 冻伤 / 睡眠 / 发狂（咒死不算）
ST_NAME = ('中毒', '腐败', '出血', '冻伤', '睡眠', '发狂')
ST_ATK = ('poizonAttackPower', 'diseaseAttackPower', 'bloodAttackPower', 'freezeAttackPower', 'sleepAttackPower', 'madnessAttackPower')
ST_NPC_RES = ('resist_poison', 'resist_desease', 'resist_blood', 'resist_freeze', 'resist_sleep', 'resist_madness')
ST_NPC_RC = ('resistCorrectId_poison', 'resistCorrectId_disease', 'resistCorrectId_blood', 'resistCorrectId_freeze',
             'resistCorrectId_sleep', 'resistCorrectId_madness')
ST_REGIST = ('registPoizonChangeRate', 'registDiseaseChangeRate', 'registBloodChangeRate', 'registFreezeChangeRate',
             'registSleepChangeRate', 'registMadnessChangeRate')
ST_DEFDMG = ('poisonDefDamageRate', 'diseaseDefDamageRate', 'bloodDefDamageRate', 'freezeDefDamageRate', 'sleepDefDamageRate', 'madnessDefDamageRate')
ST_ARMOR = ('resistPoison', 'resistDisease', 'resistBlood', 'resistFreeze', 'resistSleep', 'resistMadness')
ST_ADDRES = ('changePoisonResistPoint', 'changeDiseaseResistPoint', 'changeBloodResistPoint', 'changeFreezeResistPoint',
             'changeSleepResistPoint', 'changeMadnessResistPoint')
ST_STAT = ('vit', 'vit', 'end', 'end', 'wil', 'wil')     # 玩家抗性：免疫（生命力）/ 健壮（耐力）/ 理智（精神）
ST_CORR = ('correctType_Poison', None, 'correctType_Blood', None, 'correctType_Sleep', 'correctType_Madness')   # 随感应涨的
IMMUNE = 999


def proc_vec(Ls, r):
    """一个异常特效发作时的效果：[每跳扣血 % 最大血量, 每跳扣血点数, 是否持续扣血, 间隔秒, 持续秒, 受到伤害倍率]"""
    g = lambda f: gv(Ls, r, f)
    dur, itv = max(0.0, g('effectEndurance')), g('motionInterval')
    mult = g('neutralDamageCutRate')
    return [max(0.0, g('changeHpRate')), max(0, g('changeHpPoint')), 1.0 if itv > 0 and dur > itv else 0.0,
            itv if itv > 0 else 1.0, dur, mult if mult > 0 else 1.0]


def wmedian(v, w):
    """带权中位数（每种敌人按它在这一档放了几个加权）"""
    o = np.argsort(v, kind='stable')
    c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, c[-1] / 2.0)])


def scale_effects():
    """随机器运行时挂的缩放效果：{实体: [效果...]}"""
    cp = os.path.join(HERE, 'cache', 'scale.json')
    files = sorted(glob.glob(os.path.join(RD, 'event', '*.emevd.dcx')))
    sig = '%d|%d' % (len(files), int(max(os.path.getmtime(f) for f in files))) if files else '0'
    try:
        c = json.load(open(cp, encoding='utf-8'))
        if c['sig'] == sig:
            return {int(k): v for k, v in c['data'].items()}
    except Exception:
        pass
    out = defaultdict(list)
    for f in files:
        for ev in emevd.read(erlib.dcx_decompress(open(f, 'rb').read()))['events']:
            for i in ev['ins']:
                if (i['bank'], i['id']) == (2000, 6) and len(i['args']) >= 16:
                    _s, eid, ent, sp = struct.unpack_from('<iiii', i['args'], 0)
                    if eid in (SCALE_EVENT, SCALE_EVENT_NOW) and sp > 0 and sp not in out[ent]:
                        out[ent].append(sp)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    json.dump({'sig': sig, 'data': out}, open(cp, 'w', encoding='utf-8'))
    return out


def _parts(raw):
    """MSB 里的敌人部件：[(部件名, 实体编号, 敌人参数)]（部件名用来对原版里没有实体编号的敌人）"""
    out = []
    pos = 0x10
    while pos:
        cnt = struct.unpack_from('<i', raw, pos + 4)[0]
        noff = struct.unpack_from('<q', raw, pos + 8)[0]
        offs = struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16)
        nxt = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
        if erlib._u16str(raw, noff) == 'PARTS_PARAM_ST':
            for o in offs:
                if struct.unpack_from('<i', raw, o + 12)[0] != 2:
                    continue
                name = erlib._u16str(raw, o + struct.unpack_from('<q', raw, o)[0])
                ptrs = struct.unpack_from('<11q', raw, o + 0x50)
                ent = struct.unpack_from('<I', raw, o + ptrs[2])[0]
                out.append((name, ent, struct.unpack_from('<i', raw, o + ptrs[3] + 12)[0]))
            return out
        pos = nxt
    return out


def map_parts(path):
    import hashlib
    cp = os.path.join(HERE, 'cache', 'msb_' + hashlib.md5(os.path.normcase(path).encode('utf-8')).hexdigest()[:16] + '.json')
    sig = '%d|%d' % (os.path.getsize(path), int(os.path.getmtime(path)))
    try:
        c = json.load(open(cp, encoding='utf-8'))
        if c['sig'] == sig and c.get('v') == 2:
            return c['data']
    except Exception:
        pass
    data = [list(x) for x in _parts(erlib.dcx_decompress(open(path, 'rb').read()))]
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    json.dump({'sig': sig, 'v': 2, 'data': data}, open(cp, 'w', encoding='utf-8'))
    return data


def enemy_ids():
    """随机器 enemy.txt：（地图, 部件名）→ 它给这个敌人的编号（随机后地图里的实体编号就是它）"""
    import re
    t = open(os.path.join(RD, 'diste', 'Base', 'enemy.txt'), encoding='utf-8').read()
    out = {}
    for i, mp, nm in re.findall(r'^- ID: (\d+)\n  Map: (\S+)\n  Name: (\S+)$', t, re.M):
        if '-' in nm:
            mp, nm = nm.split('-', 1)
        out[(mp, nm)] = int(i)
    return out


class World:
    """一种情况（原版 / DR 不随机 / DR 随机）的敌人：每档的普通敌人数组、卢恩、掉落"""

    def __init__(self, name, reg, map_dirs, scaled, map_tiers, band_of):
        self.name, self.reg = name, reg
        N, S, B, A = reg.p('NpcParam'), reg.p('SpEffectParam'), reg.p('BehaviorParam'), reg.p('AtkParam_Npc')
        Ln, Ls, Lb, La = lay('NpcParam'), lay('SpEffect'), lay('BehaviorParam'), lay('AtkParam')
        ec = json.load(open(os.path.join(RR, 'data', 'enemy_classes.json'), encoding='utf-8'))
        cls = lambda nid: ec['by_npc_param'].get(str(nid)) or ec['by_family'].get(str(nid // 10000)) or 'other'
        scale = scale_effects() if scaled else {}
        sp_slots = [f for f in Ln if f.startswith('spEffectID')]
        attacks = defaultdict(list)                     # 行为组 -> [攻击向量]
        st_hits = defaultdict(lambda: [0, np.zeros(6), [Counter() for _ in range(6)]])   # 行为组 -> [攻击数, 各异常累积合计, 各异常用的特效]
        for bid, br in B.rows.items():
            if 200000000 <= bid < 300000000 and gv(Lb, br, 'refType') == 0:
                ar = A.rows.get(gv(Lb, br, 'refId'))
                if ar is not None:
                    vec = [max(0, gv(La, ar, f)) for f in ATK_F]
                    if sum(vec) > 0:
                        var = (bid - 200000000) // 1000
                        attacks[var].append(vec)
                        h = st_hits[var]
                        h[0] += 1
                        for k in range(5):
                            r = S.rows.get(gv(La, ar, 'spEffectId%d' % k))
                            if r is not None:
                                for t, f in enumerate(ST_ATK):
                                    v = gv(Ls, r, f)
                                    if v > 0:
                                        h[1][t] += v
                                        h[2][t][gv(La, ar, 'spEffectId%d' % k)] += 1
        med_atk = {}
        for var, lst in attacks.items():
            lst.sort(key=sum)
            med_atk[var] = lst[len(lst) // 2]
        # 敌人每一下平均叠多少异常（所有攻击动作的平均）+ 发作效果（这种异常最常用的那个特效）
        e_status = {}
        for var, (n_att, tot, cnt) in st_hits.items():
            proc = np.zeros((6, 6))
            for t in range(6):
                if cnt[t]:
                    proc[t] = proc_vec(Ls, S.rows[cnt[t].most_common(1)[0][0]])
            e_status[var] = (tot / max(1, n_att), proc)
        RC, Lrc = reg.p('ResistCorrectParam'), lay('ResistCorrectParam')
        rc_cache = {}

        def rc(cid):
            """发作后抗性怎么涨：第 k 次之后阈值 = 原阈值 × 倍率_k + 加点_k"""
            if cid not in rc_cache:
                r = RC.rows.get(cid)
                rc_cache[cid] = (np.zeros(5), np.ones(5)) if r is None else \
                    (np.array([gv(Lrc, r, 'addPoint%d' % k) for k in range(1, 6)]), np.array([gv(Lrc, r, 'addRate%d' % k) for k in range(1, 6)]))
            return rc_cache[cid]
        sp_cache = {}

        def sp(sid):
            if sid not in sp_cache:
                r = S.rows.get(sid)
                sp_cache[sid] = None if r is None else (gv(Ls, r, SP_HP), [gv(Ls, r, f) for f in SP_ATK], [gv(Ls, r, f) for f in SP_DEF],
                                                        [gv(Ls, r, f) for f in SP_CUT], gv(Ls, r, 'soulRate') * gv(Ls, r, 'haveSoulRate'),
                                                        [gv(Ls, r, f) for f in ST_REGIST], [gv(Ls, r, f) for f in ST_DEFDMG])
            return sp_cache[sid]

        def stats(nid, ent):
            r = N.rows.get(nid)
            if r is None:
                return None
            hp, atk, dfn, cut, soul = float(gv(Ln, r, 'hp')), np.ones(5), np.ones(5), np.ones(5), float(gv(Ln, r, 'getSoul'))
            reg_r, sdef = np.ones(6), np.ones(6)
            # 同一个特效只算一次（游戏里同编号的特效不叠加）：重随把随机器给 Boss「出场就挂」的缩放（SCALE_EVENT_NOW）写进了复制的敌人参数的特效格，
            # 随机器的事件里还挂着同一个，以前这里乘了两次（前期 Boss 是缩小的，血量算成 0.1~0.3 倍；DLC 放大的又算多了）
            for sid in dict.fromkeys([gv(Ln, r, f) for f in sp_slots] + scale.get(ent, [])):
                e = sp(sid) if sid > 0 else None
                if e:
                    hp *= e[0]
                    atk *= e[1]
                    dfn *= e[2]
                    cut *= e[3]
                    soul *= e[4]
                    reg_r *= e[5]
                    sdef *= e[6]
            var = gv(Ln, r, 'behaviorVariationId')
            base_atk = med_atk.get(var)
            if hp <= 0 or base_atk is None:
                return None
            d = np.array([max(1.0, gv(Ln, r, f)) for f in NPC_DEF]) * dfn
            res0 = np.array([gv(Ln, r, f) for f in ST_NPC_RES], float)
            res = np.where(res0 >= IMMUNE, np.inf, res0 * reg_r)
            rcs = [rc(gv(Ln, r, f)) for f in ST_NPC_RC]
            ebu, eproc = e_status.get(var, (np.zeros(6), np.zeros((6, 6))))
            return (hp, np.array(base_atk, float) * atk, d, cut, soul, res, np.array([x[0] for x in rcs]), np.array([x[1] for x in rcs]),
                    sdef, ebu, eproc)

        # 位置 = 原版地图里每个敌人部件（按原版放的敌人分类）；随机后按随机器给的编号去最终地图里找实际放的敌人
        van_dir = os.path.join(RD, 'diste', 'Vanilla')
        ids = enemy_ids() if scaled else {}
        rows = defaultdict(list)                       # 档 -> [(stats…, npc, 去重键)]
        brows = defaultdict(list)                      # Boss（原版放 Boss 的位置；随机敌人时是随机后实际放的 Boss）
        boss_soul = defaultdict(float)
        self.lost = Counter()
        for vf in sorted(glob.glob(os.path.join(van_dir, '*.msb.dcx'))):
            name = os.path.basename(vf)
            m = name[:-len('.msb.dcx')]
            if m not in map_tiers:
                continue
            b = band_of(map_tiers[m])
            final = None
            if scaled:
                fp = next((os.path.join(d, name) for d in map_dirs if os.path.isfile(os.path.join(d, name))), None)
                final = {e: n for _nm, e, n in map_parts(fp)} if fp else {}
            for pname, e, vn in map_parts(vf):
                c = cls(vn)
                if c not in ('basic', 'boss'):
                    continue
                if scaled:
                    e = ids.get((m, pname)) or e
                    n = final.get(e)
                    if n is None:
                        self.lost[b] += c == 'basic'
                        continue
                else:
                    n = vn
                st = stats(n, e)
                if st is None:
                    self.lost[b] += c == 'basic'
                    continue
                if c == 'basic':
                    rows[b].append(st + (n, (n, tuple(scale.get(e, ())))))
                else:
                    boss_soul[b] += st[4]
                    brows[b].append(st + (n, (n, tuple(scale.get(e, ())))))
        self.nbands = max(rows) + 1

        def group(lst):
            """同一种敌人（参数 + 缩放效果相同）只算一次，按个数加权：逐击模拟异常时快很多，中位数不变"""
            uniq, w = {}, []
            for x in lst:
                if x[-1] not in uniq:
                    uniq[x[-1]] = len(uniq)
                    w.append(0)
                w[uniq[x[-1]]] += 1
            u = [None] * len(uniq)
            for x in lst:
                u[uniq[x[-1]]] = x
            col = lambda k: np.array([x[k] for x in u])
            return {'hp': col(0), 'atk': col(1), 'def': col(2), 'cut': col(3), 'res': col(5), 'rcpt': col(6), 'rcrt': col(7),
                    'sdef': col(8), 'ebu': col(9), 'eproc': col(10), 'w': np.array(w, float), 'npc': [x[11] for x in lst]}
        self.enemies = {b: group(lst) for b, lst in rows.items()}
        # Boss：每个放 Boss 的位置一个（两段的 Boss 两段各算一个），按档分
        self.bosses = {b: group(lst) for b, lst in brows.items() if lst}
        self.boss_count = {b: len(lst) for b, lst in brows.items()}
        # 参考敌人（这一档的中位防御 / 减伤 / 攻击 / 血量 / 异常抗性）：挑武器、防具、护符时用
        self.ref = {}
        for b, e in self.enemies.items():
            rep = lambda a: np.repeat(a, e['w'].astype(int), axis=0)
            # 攻击：总攻击取中位数，按这一档所有敌人（按个数加权）的属性占比分（逐属性取中位数的话元素全是 0，元素减伤词条就一点不算）
            wa = (e['atk'] * e['w'][:, None]).sum(0)
            atk = float(np.median(rep(e['atk'].sum(1)))) * wa / max(wa.sum(), 1e-9)
            self.ref[b] = (np.median(rep(e['def']), axis=0), np.median(rep(e['cut']), axis=0), atk,
                           float(np.median(rep(e['hp']))), np.median(rep(e['res']), axis=0))
        self.soul = {b: float(sum(x[4] for x in rows[b])) for b in rows}
        self.boss_soul = dict(boss_soul)
        self.count = {b: len(rows[b]) for b in rows}
        self._drops = {}

    def map_drops(self, D, map_tiers, band_of, extra=()):
        """宝箱 / 尸体 / 地上拾取（data/treasures.json，按所在地图分档）和 Boss 奖励（data/boss_lots.json，按 Boss 的档）：
        {档: [(类别 'w' / 'a' / 's' / 't', 编号, 概率, 来源 'm' 宝箱拾取 / 'b' Boss)]}，每个掉落表行算一次（拿几成见 drop_ratio）。
        extra = [(档, 掉落表行)]：treasures.json 里没有、但原版在地图上放了护符的那些行（talisman_lots），只取里面的护符"""
        key = ('map', D)
        if key in self._drops:
            return self._drops[key]
        L = self.reg.p('ItemLotParam_map')
        tre = json.load(open(os.path.join(RR, 'data', 'treasures.json'), encoding='utf-8'))['treasures']
        boss = json.load(open(os.path.join(RR, 'data', 'boss_lots.json'), encoding='utf-8'))['bosses']
        starts = [(band_of(map_tiers[t['map']]), t['lot'], 10, 'm') for t in tre if t['map'] in map_tiers] + \
                 [(band_of(bs['tier']), lot, 10, 'b') for bs in boss for lot in bs['lots']] + [(b, lot, 1, 'm') for b, lot in extra]
        seen, out = set(), defaultdict(list)
        for b, lot, depth, src in starts:
            k = 0
            while lot > 0 and (lot + k) in L.rows and k < depth:
                rid = lot + k
                k += 1
                if rid in seen:
                    continue
                seen.add(rid)
                row = L.rows[rid]
                luck = struct.unpack_from('<H', row, erlib.LOT_LUCK)[0]
                pts, items = [], []
                for i in range(8):
                    pt = struct.unpack_from('<H', row, erlib.LOT_PT + 2 * i)[0]
                    iid = struct.unpack_from('<i', row, erlib.LOT_ID + 4 * i)[0]
                    cat = struct.unpack_from('<i', row, erlib.LOT_CAT + 4 * i)[0]
                    pts.append(pt * (D / 100.0 if (luck >> i) & 1 and iid > 0 else 1.0))
                    items.append((cat, iid))
                tot = sum(pts)
                for eff, (cat, iid) in zip(pts, items):
                    kk = {2: 'w', 3: 'a', 4: 't'}.get(cat) or ('s' if cat == 1 and 10100 <= iid <= 10210 else None) or \
                        ('u' if cat == 1 and UNID0 <= iid < UNID0 + 25 else None)   # 武器 / 防具 / 护符 / 锻造石 / 未鉴定物品
                    if depth == 1 and kk != 't':
                        continue
                    if kk and iid > 0 and eff > 0 and tot > 0:
                        out[b].append((kk, iid, min(1.0, eff / tot), src))
        self._drops[key] = out
        return out

    def drops(self, D):
        """发现力 D 时这一档每杀一个普通敌人的期望掉落：{档: {'w': {武器: 个数}, 'a': {防具: 个数}, 's': {道具: 个数}}}"""
        if D in self._drops:
            return self._drops[D]
        N, L = self.reg.p('NpcParam'), self.reg.p('ItemLotParam_enemy')
        Ln = lay('NpcParam')
        per_npc = {}

        def npc_drop(nid):
            if nid in per_npc:
                return per_npc[nid]
            out = defaultdict(float)
            r = N.rows.get(nid)
            lot = gv(Ln, r, 'itemLotId_enemy') if r is not None else -1
            k = 0
            while lot > 0 and (lot + k) in L.rows and k < 12:
                row = L.rows[lot + k]
                luck = struct.unpack_from('<H', row, erlib.LOT_LUCK)[0]
                pts, items = [], []
                for i in range(8):
                    pt = struct.unpack_from('<H', row, erlib.LOT_PT + 2 * i)[0]
                    iid = struct.unpack_from('<i', row, erlib.LOT_ID + 4 * i)[0]
                    cat = struct.unpack_from('<i', row, erlib.LOT_CAT + 4 * i)[0]
                    eff = pt * (D / 100.0 if (luck >> i) & 1 and iid > 0 else 1.0)
                    pts.append(eff)
                    items.append((cat, iid, row[erlib.LOT_NUM + i] or 1))
                tot = sum(pts)
                if tot > 0:
                    for eff, (cat, iid, num) in zip(pts, items):
                        if iid > 0 and eff > 0:
                            key = {2: 'w', 3: 'a', 1: 's', 4: 't'}.get(cat)
                            if key:
                                out[(key, iid)] += eff / tot * num
                k += 1
            per_npc[nid] = out
            return out

        res = {}
        for b, e in self.enemies.items():
            agg = defaultdict(float)
            for nid in e['npc']:
                for k2, v in npc_drop(nid).items():
                    agg[k2] += v
            n = len(e['npc'])
            res[b] = {k3: {i: v / n for (kk, i), v in agg.items() if kk == k3} for k3 in ('w', 'a', 's', 't')}
        self._drops[D] = res
        return res


# ---------------------------------------------------------------- 玩家
def rune_cost(L):
    x = max(((L + 81) - 92) * 0.02, 0.0)
    return math.floor((x + 0.1) * (L + 81) ** 2 + 1)


def level_from_runes(start_lv, runes):
    L = start_lv
    while L < 713 and runes >= rune_cost(L):
        runes -= rune_cost(L)
        L += 1
    return L


def hp_from_vigor(v):
    if v <= 25:
        return 300 + 500 * ((v - 1) / 24) ** 1.5
    if v <= 40:
        return 800 + 650 * ((v - 25) / 15) ** 1.1
    if v <= 60:
        return 1450 + 450 * (1 - (1 - (v - 40) / 20) ** 1.2)
    return 1900 + 200 * (1 - (1 - min(v - 60, 39) / 39) ** 1.2)


def allocate(base, start_lv, lv, build):
    s = dict(base)
    w, cap = build['w'], build['cap']
    added = Counter()
    for _ in range(max(0, lv - start_lv)):
        cand = [k for k in w if s[k] < cap[k]] or list(w)
        k = min(cand, key=lambda x: (added[x] + 1) / w[x])
        s[k] += 1
        added[k] += 1
    return s


class Arms:
    """一份 regulation 里武器攻击力、防具的计算（带缓存）"""

    def __init__(self, reg):
        self.reg = reg
        self.W, self.RF, self.G, self.AE = reg.p('EquipParamWeapon'), reg.p('ReinforceParamWeapon'), reg.p('CalcCorrectGraph'), reg.p('AttackElementCorrectParam')
        self.P, self.S = reg.p('EquipParamProtector'), reg.p('SpEffectParam')
        self.Lw, self.Lr, self.Lg, self.La, self.Lp = lay('EquipParamWeapon'), lay('ReinforceParamWeapon'), lay('CalcCorrectGraph'), lay('AttackElementCorrectParam'), lay('EquipParamProtector')
        self.Ls = lay('SpEffect')
        self._ar, self._graph, self._st, self._info, self._armor = {}, {}, {}, {}, {}
        self.armor_scale = 1.0          # 情景：每件防具的减伤 × 这个数（要在第一次 armor() 之前设）

    def graph(self, gid, stat):
        key = (gid, stat)
        if key not in self._graph:
            r = self.G.rows.get(gid)
            if r is None:
                self._graph[key] = 0.0
            else:
                st = [gv(self.Lg, r, 'stageMaxVal%d' % k) for k in range(5)]
                gr = [gv(self.Lg, r, 'stageMaxGrowVal%d' % k) for k in range(5)]
                ad = [gv(self.Lg, r, 'adjPt_maxGrowVal%d' % k) for k in range(5)]
                val = gr[4]
                for k in range(4):
                    if stat <= st[k + 1]:
                        t = (stat - st[k]) / (st[k + 1] - st[k]) if st[k + 1] > st[k] else 1.0
                        t = max(0.0, min(1.0, t))
                        t = t ** ad[k] if ad[k] > 0 else 1 - (1 - t) ** (-ad[k])
                        val = gr[k] + (gr[k + 1] - gr[k]) * t
                        break
                self._graph[key] = val / 100.0
        return self._graph[key]

    def info(self, wid):
        if wid in self._info:
            return self._info[wid]
        r = self.W.rows.get(wid)
        if r is None:
            return None
        L = self.Lw
        self._info[wid] = {'type': gv(L, r, 'wepType'), 'rar': gv(L, r, 'rarity'), 'rt': gv(L, r, 'reinforceTypeId'), 'w': gv(L, r, 'weight'),
                'req': [gv(L, r, f) for f in ('properStrength', 'properAgility', 'properMagic', 'properFaith', 'properLuck')]}
        return self._info[wid]

    def usable(self, wid, s):
        i = self.info(wid)
        if i is None or i['type'] not in MELEE:
            return False
        have = (int(s['str'] * 1.5), s['dex'], s['mag'], s['fai'], s['luc'])
        return all(n <= h for n, h in zip(i['req'], have))

    def max_level(self, wid):
        i = self.info(wid)
        k = 0
        while i and (i['rt'] + k + 1) in self.RF.rows:
            k += 1
        return k

    def resident(self, wid):
        """武器的常驻特效（DR：流派加成 / 异常抗性、特效、传说光效）"""
        r = self.W.rows[wid]
        return tuple(sorted({gv(self.Lw, r, f) for f in ('residentSpEffectId', 'residentSpEffectId1', 'residentSpEffectId2')} - {0, -1}))

    def ar(self, wid, lv, s):
        key = (wid, lv, tuple(s[k] for k in ('str', 'dex', 'mag', 'fai', 'luc')))
        if key in self._ar:
            return self._ar[key]
        r = self.W.rows[wid]
        L, Lr = self.Lw, self.Lr
        rf = self.RF.rows.get(gv(L, r, 'reinforceTypeId') + lv) or self.RF.rows.get(gv(L, r, 'reinforceTypeId'))
        rate = [gv(Lr, rf, f) for f in ('physicsAtkRate', 'magicAtkRate', 'fireAtkRate', 'thunderAtkRate', 'darkAtkRate')]
        crate = [gv(Lr, rf, f) for f in ('correctStrengthRate', 'correctAgilityRate', 'correctMagicRate', 'correctFaithRate', 'correctLuckRate')]
        base = [gv(L, r, f) for f in ('attackBasePhysics', 'attackBaseMagic', 'attackBaseFire', 'attackBaseThunder', 'attackBaseDark')]
        corr = [gv(L, r, f) for f in ('correctStrength', 'correctAgility', 'correctMagic', 'correctFaith', 'correctLuck')]
        ctype = [gv(L, r, f) for f in ('correctType_Physics', 'correctType_Magic', 'correctType_Fire', 'correctType_Thunder', 'correctType_Dark')]
        ae = self.AE.rows.get(gv(L, r, 'attackElementCorrectId'))
        stat = [s['str'], s['dex'], s['mag'], s['fai'], s['luc']]
        sname = ('Strength', 'Dexterity', 'Magic', 'Faith', 'Luck')
        tname = ('Physics', 'Magic', 'Fire', 'Thunder', 'Dark')
        out = []
        for t in range(5):
            b = base[t] * rate[t]
            if b <= 0:
                out.append(0.0)
                continue
            bonus = 0.0
            for k in range(5):
                if ae is None or not gv(self.La, ae, 'is%sCorrect_by%s' % (sname[k], tname[t])):
                    continue
                bonus += b * corr[k] * crate[k] / 100.0 * self.graph(ctype[t], stat[k])
            out.append(b + bonus)
        self._ar[key] = np.array(out)
        return self._ar[key]

    def status(self, wid, lv, s):
        """武器每一下叠的异常 (6,) 和发作效果 (6, 6)：自带异常特效（按强化等级偏移），出血 / 毒 / 睡眠 / 发狂随感应涨"""
        key = (wid, lv, s['luc'])
        if key in self._st:
            return self._st[key]
        r = self.W.rows[wid]
        L = self.Lw
        rf = self.RF.rows.get(gv(L, r, 'reinforceTypeId') + lv) or self.RF.rows.get(gv(L, r, 'reinforceTypeId'))
        bu, proc = np.zeros(6), np.zeros((6, 6))
        for k in range(3):
            sid = gv(L, r, 'spEffectBehaviorId%d' % k)
            if sid <= 0:
                continue
            sr = self.S.rows.get(sid + (gv(self.Lr, rf, 'spEffectId%d' % (k + 1)) if rf is not None else 0)) or self.S.rows.get(sid)
            if sr is None:
                continue
            for t, f in enumerate(ST_ATK):
                v = gv(self.Ls, sr, f)
                if v <= 0:
                    continue
                luck = gv(L, r, 'correctLuck') * (gv(self.Lr, rf, 'correctLuckRate') if rf is not None else 1.0)
                if ST_CORR[t] and luck > 0 and gv(self.Ls, sr, 'isUseStatusAilmentAtkPowerCorrect'):
                    v *= 1 + luck / 100.0 * self.graph(gv(L, r, ST_CORR[t]), s['luc'])
                bu[t] += v
                proc[t] = proc_vec(self.Ls, sr)
        self._st[key] = (bu, proc)
        return self._st[key]

    def armor(self, pid):
        if pid in self._armor:
            return self._armor[pid]
        r = self.P.rows.get(pid)
        if r is None:
            return None
        L = self.Lp
        slot = next((sl for sl, f in (('head', 'headEquip'), ('body', 'bodyEquip'), ('arm', 'armEquip'), ('leg', 'legEquip')) if gv(L, r, f)), None)
        sp = tuple(sorted({gv(L, r, f) for f in ('residentSpEffectId', 'residentSpEffectId2', 'residentSpEffectId3')} - {0, -1}))
        self._armor[pid] = {'slot': slot, 'w': gv(L, r, 'weight'), 'cut': 1 - (1 - np.array([gv(L, r, f) for f in SP_CUT])) * self.armor_scale,
                            'res': np.array([gv(L, r, f) for f in ST_ARMOR], float), 'sp': sp, 'id': pid}
        return self._armor[pid]


# ---------------------------------------------------------------- 护符
SP_DEALT = (('atkEnemyDmgCorrectRate_Physics', 'physicsAttackRate'), ('atkEnemyDmgCorrectRate_Magic', 'magicAttackRate'),
            ('atkEnemyDmgCorrectRate_Fire', 'fireAttackRate'), ('atkEnemyDmgCorrectRate_Thunder', 'thunderAttackRate'),
            ('atkEnemyDmgCorrectRate_Dark', 'darkAttackRate'))          # 对敌人造成的伤害（atkPlayer… 是对玩家的，不算）
SP_TAKEN = (('defEnemyDmgCorrectRate_Physics', 'neutralDamageCutRate'), ('defEnemyDmgCorrectRate_Magic', 'magicDamageCutRate'),
            ('defEnemyDmgCorrectRate_Fire', 'fireDamageCutRate'), ('defEnemyDmgCorrectRate_Thunder', 'thunderDamageCutRate'),
            ('defEnemyDmgCorrectRate_Dark', 'darkDamageCutRate'))       # 受到敌人的伤害
TAL_STAT = ('addLifeForceStatus', 'addWillpowerStatus', 'addEndureStatus', 'addStrengthStatus',
            'addDexterityStatus', 'addMagicStatus', 'addFaithStatus', 'addLuckStatus')   # 和 STATS 同顺序
MELEE_SUB = {100, 102, 103, 104, 110, 111, 112, 120, 121, 122, 123, 124, 127}   # 近战能吃到的动作类别（magicSubCategoryChange）


def tal_neutral():
    """乘到玩家身上的倍率；flat / pct / pcap / regen / regen_pct 只有 DR 的折算词条会有（见 powertab.py）"""
    return powertab.neutral()


def tal_add(a, b):
    return {'dealt': a['dealt'] * b['dealt'], 'pow': a['pow'] * b['pow'], 'taken': a['taken'] * b['taken'],
            'defr': a['defr'] * b['defr'], 'hp': a['hp'] * b['hp'], 'st': a['st'] + b['st'], 'res': a['res'] + b['res'],
            'flat': a['flat'] + b['flat'], 'pct': a['pct'] + b['pct'], 'pcap': min(a['pcap'], b['pcap']),
            'regen': a['regen'] + b['regen'], 'regen_pct': a['regen_pct'] + b['regen_pct']}


FLAT_EFF = powertab.ASSUME['flat_eff']      # 词条的固定伤害（法术、冲击波）打到敌人身上剩几成（防御、减伤的粗略折算）


def extra_out(ar_sum, cut_mean, hp, flat, pct, pcap):
    """词条额外的每下伤害：固定伤害 × 折算 × 敌人平均减伤 + 敌人最大血量 × 比例（每下最多自己攻击力的 pcap 倍）"""
    return flat * FLAT_EFF * cut_mean + np.minimum(pct * hp, pcap * ar_sum)


REGEN_CAP = 0.5     # 回血最多抵掉敌人每下伤害的一半（不封顶的话，前期「命中回血」类词条能把敌人的伤害整个抵掉，能挨几下变成几十倍）


def regen_in(d_in, regen):
    """回血抵掉一部分敌人每下的伤害（敌人两下之间回的血），最多抵 REGEN_CAP"""
    return np.maximum(d_in - regen * ASSUME['enemy_hit_interval'], (1 - REGEN_CAP) * d_in)


class Tals:
    """一份 regulation 里护符 / 防具词条的效果（带缓存）：特效 → 乘到玩家身上的倍率。
    读护符的 refId 和两个常驻特效（防具是三个常驻特效），顺着连锁（cycleOccurrence / 连续命中 accumuOverFire / 击杀 applyIdOnGetSoul）往下找；
    条件效果按 ASSUME['talisman_uptime'] 的覆盖率折算"""

    def __init__(self, reg):
        self.A, self.S = reg.p('EquipParamAccessory'), reg.p('SpEffectParam')
        self.La, self.Ls = lay('EquipParamAccessory'), lay('SpEffect')
        self._e, self._sp = {}, {}

    def _cond(self, r):
        U = ASSUME['talisman_uptime']
        g = lambda f: gv(self.Ls, r, f)
        if g('conditionHp') > 0:
            return U['low_hp']
        if g('conditionHpRate') > 0:
            return U['full_hp']
        subs = [x for x in (g('magicSubCategoryChange1'), g('magicSubCategoryChange2'), g('magicSubCategoryChange3')) if x]
        if subs:
            return U['motion'] if any(x in MELEE_SUB for x in subs) else 0.0
        si = g('stateInfo')
        if si in (197, 367) or g('throwAttackParamChange'):       # 反击 / 致命一击
            return U['motion']
        if si in (315, 335) or g('wepParamChange') in (2, 3):     # 轻负重 / 被致命一击 / 只对法术
            return 0.0
        if any(g('invocationConditionsStateChange%d' % k) for k in (1, 2, 3)):
            return U['nearby_status']
        return 1.0

    def _collect(self, sid, u, acc, seen):
        if sid <= 0 or sid in seen or u <= 0:
            return
        seen.add(sid)
        m = powertab.MANUAL.get(sid)
        if m is not None:                          # DR 靠规则生效的词条：标记特效本身没数值，按折算表
            if m[0] is not None:
                powertab.apply(acc, m[0], u * m[1])
            return
        r = self.S.rows.get(sid)
        if r is None:
            return
        g = lambda f: gv(self.Ls, r, f)
        uu = u * self._cond(r)
        if uu <= 0:
            return
        f = lambda m: 1.0 + uu * (m - 1.0)
        acc['dealt'] *= [f(g(a) * g(b)) for a, b in SP_DEALT]
        acc['pow'] *= [f(g(x)) for x in SP_ATK]
        acc['taken'] *= [f(g(a) * g(b)) for a, b in SP_TAKEN]
        acc['defr'] *= [f(g(x)) for x in SP_DEF]
        acc['hp'] *= f(g(SP_HP))
        acc['st'] += [uu * g(x) for x in TAL_STAT]
        acc['res'] += [uu * g(x) for x in ST_ADDRES]
        U = ASSUME['talisman_uptime']
        self._collect(g('cycleOccurrenceSpEffectId'), uu, acc, seen)
        self._collect(g('accumuOverFireId'), uu * U['on_hit'], acc, seen)
        self._collect(g('applyIdOnGetSoul'), uu * U['on_kill'], acc, seen)

    def sp_effect(self, sids):
        """一组特效（同一个特效只生效一次）合起来的倍率；对战斗力没影响就 None"""
        if sids in self._sp:                        # 防具 / 护符的特效组本来就是排好序的元组，直接命中
            return self._sp[sids]
        sids = tuple(sorted(set(sids)))
        if sids not in self._sp:
            acc, seen = tal_neutral(), set()
            for sid in sids:
                self._collect(sid, 1.0, acc, seen)
            rel = any(not np.allclose(acc[k], 1.0) for k in ('dealt', 'pow', 'taken', 'defr')) or abs(acc['hp'] - 1) > 1e-9 or \
                acc['st'].any() or acc['res'].any() or any(abs(acc[k]) > 1e-12 for k in ('flat', 'pct', 'regen', 'regen_pct'))
            self._sp[sids] = acc if rel else None
        return self._sp[sids]

    def effect(self, aid):
        """(效果键, 护符组, 倍率) 或 None（对战斗力没影响）；效果键相同的只能生效一个，护符组相同的只能戴一个"""
        if aid in self._e:
            return self._e[aid]
        r = self.A.rows.get(aid)
        out = None
        if r is not None:
            sids = tuple(sorted({gv(self.La, r, f) for f in ('refId', 'residentSpEffectId1', 'residentSpEffectId2')} - {0, -1}))
            acc = self.sp_effect(sids)
            if acc is not None:
                out = (sids, gv(self.La, r, 'accessoryGroup'), acc)
        self._e[aid] = out
        return out


def ref_scores(arms, wid, lv, s, pdef, CUT, effs, ref, ar_cache=None):
    """参考敌人上的战斗力（能挨几下 ÷ 砍几刀，不含异常），一次算一批：CUT (K,5) 防具减伤，effs = K 个倍率"""
    ref_def, ref_cut, ref_atk = ref[:3]
    ar_cache = {} if ar_cache is None else ar_cache
    st = np.array([s[k] for k in STATS], float)[None, :] + np.array([e['st'] for e in effs])
    ar = []
    for row in st:
        k = (wid, lv) + tuple(np.round(row[3:], 3))
        if k not in ar_cache:
            ar_cache[k] = arms.ar(wid, lv, dict(zip(STATS[3:], k[2:])))
        ar.append(ar_cache[k])
    ar = np.array(ar) * np.array([e['pow'] for e in effs])
    col = lambda k: np.array([e[k] for e in effs], float)
    d_out = (ar * defense_mult(ar / ref_def) * ref_cut * np.array([e['dealt'] for e in effs])).sum(1) + \
        extra_out(ar.sum(1), float(np.mean(ref_cut)), ref[3], col('flat'), col('pct'), col('pcap'))
    d_in = (ref_atk * defense_mult(ref_atk / (pdef * np.array([e['defr'] for e in effs]))) * CUT * np.array([e['taken'] for e in effs])).sum(1)
    hp = np.array([hp_from_vigor(v) for v in st[:, 0]]) * col('hp')
    d_in = regen_in(d_in, col('regen') + col('regen_pct') * hp)
    return hp / np.maximum(d_in, 1e-6) * d_out


def ref_score(arms, wid, lv, s, pdef, pcut, eff, ref, ar_cache=None):
    return float(ref_scores(arms, wid, lv, s, pdef, np.asarray(pcut)[None, :], [eff], ref, ar_cache)[0])


def combine_sids(tals, sids, cache=None):
    """几个特效合起来的倍率（逐个特效相加；同一个特效只算一次）"""
    key = frozenset(sids)
    if cache is not None and key in cache:
        return cache[key]
    eff = tal_neutral()
    for sid in sorted(key):
        e1 = tals.sp_effect((sid,))
        if e1 is not None:
            eff = tal_add(eff, e1)
    if cache is not None:
        cache[key] = eff
    return eff


def armor_effect(tals, pieces):
    """几件防具合起来：(减伤连乘, 词条倍率, 用到的特效, 异常抗性合计)；同一个词条特效两件都有也只生效一次"""
    cut, res, sids = np.ones(5), np.zeros(6), set()
    for a in pieces:
        cut = cut * a['cut']
        res = res + a['res']
        sids.update(a['sp'])
    return cut, combine_sids(tals, sids), frozenset(sids), res


def pick_armor(arms, tals, owned, budget, wid, lv, s, pdef, ref):
    """每个部位挑负重放得下的（中负重按比例分到各部位）：先挑减伤最高的，再逐个部位换成让参考战斗力最高的那件（算上词条），来回两遍"""
    cand = {}
    for slot, share in ASSUME['slot_share'].items():
        lst = [a for a in owned.get(slot, []) if a['w'] <= budget * share] or sorted(owned.get(slot, []), key=lambda a: a['w'])[:1]
        if not lst:
            continue
        # 没有词条的只留物理减伤最高的 3 件；有词条的同一组词条只留减伤最高的那件
        plain = sorted((a for a in lst if tals.sp_effect(a['sp']) is None), key=lambda a: a['cut'][0])[:3]
        best_sp = {}
        for a in lst:
            if tals.sp_effect(a['sp']) is not None and (a['sp'] not in best_sp or a['cut'][0] < best_sp[a['sp']]['cut'][0]):
                best_sp[a['sp']] = a
        cand[slot] = plain + list(best_sp.values())
    pick = {slot: min(lst, key=lambda a: a['cut'][0]) for slot, lst in cand.items()}
    ar_cache, eff_cache = {}, {}
    for _ in range(2):
        moved = False
        for slot, lst in cand.items():
            if len(lst) < 2:
                continue
            others = [a for k, a in pick.items() if k != slot]
            cut_o, sids_o = np.ones(5), set()
            for a in others:
                cut_o = cut_o * a['cut']
                sids_o.update(a['sp'])
            CUT = cut_o[None, :] * np.array([a['cut'] for a in lst])
            eff_o = combine_sids(tals, sids_o, eff_cache)
            effs = [eff_o if not set(a['sp']) - sids_o else tal_add(eff_o, combine_sids(tals, set(a['sp']) - sids_o, eff_cache)) for a in lst]
            sc = ref_scores(arms, wid, lv, s, pdef, CUT, effs, ref, ar_cache)
            j, cur = int(np.argmax(sc)), next(i for i, a in enumerate(lst) if a is pick[slot])
            if j != cur and sc[j] > sc[cur] * (1 + 1e-9):
                pick[slot] = lst[j]
                moved = True
        if not moved:
            break
    return pick


def pick_talismans(tals, owned, slots, arms, wid, lv, s, pdef, pcut, ref, base=None, skip_sids=frozenset()):
    """从拥有的护符里贪心挑 slots 件（同护符组 / 同效果只戴一件，和防具词条同一个特效的不算）：
    每步加上让参考敌人战斗力指数涨得最多的那件，不涨就不戴。base = 防具词条已经给的倍率。
    返回 (合并后的倍率（含 base）, 戴的护符编号, 护符让参考指数乘了多少)"""
    cur = base if base is not None else tal_neutral()
    cands, aids, keys = [], [], set()
    for t in sorted(owned):
        e = tals.effect(t)
        if e is not None and e[0] not in keys and not (set(e[0]) & skip_sids):
            keys.add(e[0])
            cands.append(e)
            aids.append(t)
    if not cands or slots <= 0:
        return cur, [], 1.0
    ref_def, ref_cut, ref_atk = ref[:3]
    D = np.array([e[2]['dealt'] for e in cands])
    P = np.array([e[2]['pow'] for e in cands])
    T = np.array([e[2]['taken'] for e in cands])
    R = np.array([e[2]['defr'] for e in cands])
    H = np.array([e[2]['hp'] for e in cands])
    ST = np.array([e[2]['st'] for e in cands])
    X = {k: np.array([e[2][k] for e in cands], float) for k in ('flat', 'pct', 'pcap', 'regen', 'regen_pct')}
    base_st = np.array([s[k] for k in STATS], float)
    ar_cache = {}

    one = (np.ones((1, 5)), np.ones((1, 5)), np.ones((1, 5)), np.ones((1, 5)), np.ones(1), np.zeros((1, 8)))
    X1 = {'flat': np.zeros(1), 'pct': np.zeros(1), 'pcap': np.full(1, math.inf), 'regen': np.zeros(1), 'regen_pct': np.zeros(1)}

    def scores(c, with_cands=True):
        d_, p_, t_, r_, h_, st_ = (D, P, T, R, H, ST) if with_cands else one
        x_ = X if with_cands else X1
        st = base_st + c['st'] + st_
        ar = []
        for row in st:
            k = tuple(np.round(row[3:], 3))
            if k not in ar_cache:
                ar_cache[k] = arms.ar(wid, lv, dict(zip(STATS[3:], k)))
            ar.append(ar_cache[k])
        ar = np.array(ar) * c['pow'] * p_
        d_out = (ar * defense_mult(ar / ref_def) * ref_cut * c['dealt'] * d_).sum(1) + \
            extra_out(ar.sum(1), float(np.mean(ref_cut)), ref[3], c['flat'] + x_['flat'], c['pct'] + x_['pct'], np.minimum(c['pcap'], x_['pcap']))
        d_in = (ref_atk * defense_mult(ref_atk / (pdef * c['defr'] * r_)) * pcut * c['taken'] * t_).sum(1)
        hp = np.array([hp_from_vigor(v) for v in st[:, 0]]) * c['hp'] * h_
        d_in = regen_in(d_in, c['regen'] + x_['regen'] + (c['regen_pct'] + x_['regen_pct']) * hp)
        return hp / np.maximum(d_in, 1e-6) * d_out

    s0 = float(scores(cur, False)[0])
    now, chosen, picked = s0, [], []
    for _ in range(slots):
        sc = scores(cur)
        for j, e in enumerate(cands):
            if any(e[0] == c[0] or (e[1] >= 0 and e[1] == c[1]) for c in chosen):
                sc[j] = -1
        j = int(np.argmax(sc))
        if sc[j] <= now * (1 + 1e-9):
            break
        chosen.append(cands[j])
        picked.append(aids[j])
        cur = tal_add(cur, cands[j][2])
        now = float(sc[j])
    return cur, picked, now / s0 if s0 > 0 else 1.0


def talisman_lots(vreg, map_tiers, band_of):
    """原版在地图上放了护符、但 treasures.json / boss_lots.json 没覆盖到的掉落表行：[(档, 行)]。
    地图从掉落表编号推（大地图 10AABBxxxx → m60_AA_BB_00，DLC 20AABBxxxx → m61，传承地 XXYYxxxx → mXX_YY）；
    推不出地图的（任务奖励、NPC 给的）不算"""
    L = vreg.p('ItemLotParam_map')
    tre = json.load(open(os.path.join(RR, 'data', 'treasures.json'), encoding='utf-8'))['treasures']
    boss = json.load(open(os.path.join(RR, 'data', 'boss_lots.json'), encoding='utf-8'))['bosses']
    covered = set()
    for lot in [t['lot'] for t in tre] + [x for bs in boss for x in bs['lots']]:
        k = 0
        while lot > 0 and (lot + k) in L.rows and k < 10:
            covered.add(lot + k)
            k += 1
    out = []
    for rid, row in L.rows.items():
        if rid in covered or not any(struct.unpack_from('<i', row, erlib.LOT_CAT + 4 * i)[0] == 4 and
                                     struct.unpack_from('<i', row, erlib.LOT_ID + 4 * i)[0] > 0 for i in range(8)):
            continue
        s = str(rid)
        if len(s) == 10 and s[0] in '12':
            m = 'm%s_%s_%s_00' % ('60' if s[0] == '1' else '61', s[2:4], s[4:6])
            m = m if m in map_tiers else None
        elif len(s) == 8:
            m = next((k for k in sorted(map_tiers) if k.startswith('m%s_%s_' % (s[:2], s[2:4]))), None)
        else:
            m = None
        if m:
            out.append((band_of(map_tiers[m]), rid))
    return out


def max_load(reg, end):
    L = lay('CalcCorrectGraph')
    r = reg.p('CalcCorrectGraph').rows[220]
    st = [gv(L, r, 'stageMaxVal%d' % k) for k in range(5)]
    gr = [gv(L, r, 'stageMaxGrowVal%d' % k) for k in range(5)]
    ad = [gv(L, r, 'adjPt_maxGrowVal%d' % k) for k in range(5)]
    for k in range(4):
        if end <= st[k + 1]:
            t = max(0.0, min(1.0, (end - st[k]) / (st[k + 1] - st[k]) if st[k + 1] > st[k] else 1.0))
            t = t ** ad[k] if ad[k] > 0 else 1 - (1 - t) ** (-ad[k])
            return gr[k] + (gr[k + 1] - gr[k]) * t
    return gr[4]


def class_start(reg, cid):
    L = lay('CharaInitParam')
    r = reg.p('CharaInitParam').rows[cid]
    keys = {'vit': 'baseVit', 'wil': 'baseWil', 'end': 'baseEnd', 'str': 'baseStr', 'dex': 'baseDex', 'mag': 'baseMag', 'fai': 'baseFai', 'luc': 'baseLuc'}
    base = {k: gv(L, r, f) for k, f in keys.items()}
    weps = [v - v % 10000 for f in L if f.startswith(('equip_Wep', 'equip_Subwep')) for v in [gv(L, r, f)] if v > 0]
    arm = [v for f in ('equip_Helm', 'equip_Armer', 'equip_Gaunt', 'equip_Leg') for v in [gv(L, r, f)] if v > 0]
    return base, gv(L, r, 'soulLv'), weps, arm


# ---------------------------------------------------------------- 评估
def resist_base(L, stat):
    """玩家的基础异常抗性 = 等级部分 + 对应属性部分（Fextralife 整理的公式；免疫看生命力、健壮看耐力、理智看精神）"""
    x = L + 79
    if L <= 71:
        lv = 75 + 30 * (x - 1) / 149
    elif L <= 111:
        lv = 105 + 40 * (x - 150) / 40
    elif L <= 161:
        lv = 145 + 15 * (x - 190) / 50
    else:
        lv = 160 + 20 * (x - 240) / 552
    if stat <= 30:
        st = 0
    elif stat <= 40:
        st = 30 * (stat - 30) / 10
    elif stat <= 60:
        st = 30 + 10 * (stat - 40) / 20
    else:
        st = 40 + 10 * (min(stat, 99) - 60) / 39
    return lv + st


def player_resist(L, s, armor_res, eff_res):
    return np.array([resist_base(L, s[k]) for k in ST_STAT]) + armor_res + eff_res


def sim_hits(H, D, bu, thr0, proc, sdef, dt, rcpt=None, rcrt=None):
    """逐击模拟带异常的「几下打死」（带小数，最少 1）。
    H (u,) 目标血量；D (T, u) 每一下的基础伤害（T = 难度档数）；bu 每一下叠的异常 (u,6)/(6,)；thr0 抗性阈值 (u,6)/(6,)（inf = 免疫）；
    proc 发作效果 (u,6,6)/(6,6)（见 proc_vec）；sdef 目标的异常伤害倍率；dt 两下之间几秒（持续扣血按时间折算）；
    rcpt / rcrt (u,6,5)：第 k 次发作后阈值 = 原阈值 × rcrt_k + rcpt_k。
    发作效果持续期间（冻伤 30 秒、中毒 90 秒等）这种异常不再累积；出血、发狂是一次性的，马上能接着叠"""
    T, u = D.shape
    out = H[None, :] / np.maximum(D, 1e-6)
    bu = np.broadcast_to(bu, (u, 6))
    thr0 = np.broadcast_to(thr0, (u, 6))
    proc = np.broadcast_to(proc, (u, 6, 6))
    tick = (proc[:, :, 0] / 100.0 * H[:, None] + proc[:, :, 1]) * np.broadcast_to(sdef, (u, 6))
    act = (bu > 0) & np.isfinite(thr0) & ((tick > 0) | (proc[:, :, 5] != 1.0))
    rows = np.nonzero(act.any(1))[0]
    if len(rows):
        cols = np.nonzero(act.any(0))[0]
        n = len(rows)
        sel = lambda a: np.tile(a[rows][:, cols], (T, 1))
        Hr, Dr = np.tile(H[rows], T), D[:, rows].reshape(-1)
        bu_r, thr0_r, tick_r, act_r = sel(bu), sel(thr0), sel(tick), sel(act)
        isdot, itv, dur, mult = sel(proc[:, :, 2]) > 0, sel(proc[:, :, 3]), sel(proc[:, :, 4]), sel(proc[:, :, 5])
        dot = np.where(isdot, tick_r / np.where(itv > 0, itv, 1.0) * dt, 0.0)
        if rcpt is not None:
            rp, rr = np.tile(rcpt[rows][:, cols], (T, 1, 1)), np.tile(rcrt[rows][:, cols], (T, 1, 1))
        thr, meter, until = thr0_r.copy(), np.zeros_like(bu_r), np.full(bu_r.shape, -1.0)
        k = np.zeros(bu_r.shape, int)
        left, res, alive, last = Hr.copy(), np.full(Hr.shape, np.nan), np.ones(Hr.shape, bool), np.zeros(Hr.shape)
        cap = ASSUME['status_sim_hits']
        for i in range(1, cap + 1):
            t = i * dt
            on = until > t
            dmg = Dr * np.where(on, mult, 1.0).prod(1) + np.where(on, dot, 0.0).sum(1)
            free = act_r & ~on
            meter = meter + np.where(free, bu_r, 0.0)
            pr = free & (meter >= thr)
            if pr.any():
                dmg = dmg + np.where(pr & ~isdot, tick_r, 0.0).sum(1)
                until = np.where(pr, t + dur, until)
                meter = np.where(pr, 0.0, meter)
                if rcpt is not None:
                    k = np.minimum(k + pr, 5)
                    kk = np.maximum(k - 1, 0)[..., None]
                    thr = np.where(pr, thr0_r * np.take_along_axis(rr, kk, 2)[..., 0] + np.take_along_axis(rp, kk, 2)[..., 0], thr)
            new = left - dmg
            died = alive & (new <= 0)
            if died.any():
                res[died] = i - 1 + left[died] / dmg[died]
                alive &= ~died
            left = new
            if i > cap - 20:
                last += dmg
            if not alive.any():
                break
        if alive.any():                                # 模拟上限之后按最后 20 下的平均伤害外推
            res[alive] = cap + left[alive] / np.maximum(last[alive] / 20.0, 1e-6)
        out[:, rows] = res.reshape(T, n)
    return np.maximum(out, 1.0)


def evaluate(world, b, ar_vec, php, pdef, pcut, dealt, taken, wst, pres, tiers, flat=0.0, pct=0.0, pcap=math.inf, regen=0.0, boss=False):
    """这一档所有普通敌人：每档难度 (hp 倍率, 伤害倍率) 一组 (砍几刀, 能挨几下, 战斗力指数, 不算异常时的指数)（按个数加权的中位数）。
    难度和整合包一样做成玩家造成伤害 ÷ hp 倍率、受到伤害 × 伤害倍率，异常的累积和发作伤害不受难度影响。
    wst = 武器的 (每下异常累积, 发作效果)；pres = 玩家的异常抗性 (6,)；flat / pct / pcap / regen = DR 折算词条的固定伤害、按敌人血量的伤害、每秒回血。
    boss = True：对这一档的 Boss（没有 Boss 的档返回 None），能挨几下算上圣杯瓶（ASSUME 的 boss_flasks 瓶，每瓶回 flask_heal 的血量上限）"""
    if boss:
        if b not in world.bosses:
            return None
        e = world.bosses[b]
        php = php * (1 + ASSUME['boss_flasks'][min(b, len(ASSUME['boss_flasks']) - 1)] * ASSUME['flask_heal'])
    else:
        e = world.enemies[b]
    d_out = (ar_vec[None, :] * defense_mult(ar_vec[None, :] / e['def']) * e['cut'] * dealt).sum(1) + \
        extra_out(float(ar_vec.sum()), e['cut'].mean(1), e['hp'], flat, pct, pcap)
    d_in = regen_in((e['atk'] * defense_mult(e['atk'] / pdef) * pcut[None, :] * taken).sum(1), regen)
    hm = np.array([t[0] for t in tiers], float)[:, None]
    dm = np.array([t[1] for t in tiers], float)[:, None]
    D_out, D_in = d_out[None, :] / hm, d_in[None, :] * dm
    h2k = sim_hits(e['hp'], D_out, wst[0], e['res'], wst[1], e['sdef'], ASSUME['hit_interval'], e['rcpt'], e['rcrt'])
    h2d = sim_hits(np.full(len(e['hp']), float(php)), D_in, e['ebu'], pres, e['eproc'], 1.0, ASSUME['enemy_hit_interval'])
    k0 = np.maximum(1.0, e['hp'][None, :] / np.maximum(D_out, 1e-6))
    d0 = np.maximum(1.0, php / np.maximum(D_in, 1e-6))
    w = e['w']
    return [(wmedian(h2k[j], w), wmedian(h2d[j], w), wmedian(h2d[j] / h2k[j], w), wmedian(d0[j] / k0[j], w)) for j in range(len(tiers))]


def weapon_value(arms, wid, lv, s, ref):
    """参考敌人身上平均每一下的伤害（异常按「叠满 → 发作 → 效果期间」一个周期折算），挑主力武器用"""
    ref_def, ref_cut, _atk, ref_hp, ref_res = ref
    a = arms.ar(wid, lv, s)
    d = float((a * defense_mult(a / ref_def) * ref_cut).sum())
    bu, proc = arms.status(wid, lv, s)
    dt, extra = ASSUME['hit_interval'], 0.0
    for t in np.nonzero(bu > 0)[0]:
        if not np.isfinite(ref_res[t]):
            continue
        rate, pt, isdot, itv, dur, mult = proc[t]
        tick = rate / 100.0 * ref_hp + pt
        win = dur / dt if (isdot or mult != 1.0) else 0.0
        cyc = math.ceil(ref_res[t] / bu[t]) + win
        extra += (tick / itv * dur if isdot else tick) / cyc + d * (mult - 1.0) * win / cyc
    return d + extra


def tal_eval(world, b, arms, tals, owned_t, slots, wid, lv, s, L, pdef, pcut, a_eff, a_sids, a_res, dealt, taken, tiers):
    """在防具词条之上挑护符，再算这一档：返回 (每档难度的 evaluate 结果, 戴了几件护符, 护符让参考指数乘了多少)"""
    eff, picked, gain = pick_talismans(tals, owned_t, slots, arms, wid, lv, s, pdef, pcut, world.ref[b], a_eff, a_sids)
    s2 = {k: s[k] + v for k, v in zip(STATS, eff['st'])}
    a = arms.ar(wid, lv, s2) * eff['pow']
    php = hp_from_vigor(s2['vit']) * eff['hp']
    pres = player_resist(L, s2, a_res, eff['res'])
    args = (a, php, pdef * eff['defr'], pcut * eff['taken'], dealt * eff['dealt'], taken, arms.status(wid, lv, s2), pres, tiers,
            eff['flat'] * dealt, eff['pct'], eff['pcap'], eff['regen'] + eff['regen_pct'] * php)
    ev = evaluate(world, b, *args)
    evb = evaluate(world, b, *args, boss=True)          # 同一身装备打这一档的 Boss
    return ev, len(picked), gain, evb


def armor_gain(arms, wid, lv, s, pdef, pcut, a_eff, ref):
    """防具词条让参考指数乘了多少（同样的防具减伤，有词条 vs 没词条）"""
    return ref_score(arms, wid, lv, s, pdef, pcut, a_eff, ref) / max(ref_score(arms, wid, lv, s, pdef, pcut, tal_neutral(), ref), 1e-9)


SMITH = [10100 + k for k in range(8)]       # 锻造石 1~8
SOMBER = [10160 + k for k in range(9)]      # 失色锻造石 1~9


def stone_tier(world, sid, b):
    """情景：锻造石分层（world.stone_tiers[档] = (最低, 最高) 等级），掉到的石头换成这一档允许的最近等级；古龙不动"""
    tiers = getattr(world, 'stone_tiers', None)
    if not tiers or b >= len(tiers):
        return sid
    lo, hi = tiers[b]
    for seq in (SMITH, SOMBER):
        if sid in seq:
            lv = min(max(seq.index(sid) + 1, lo), hi, len(seq))
            return seq[lv - 1]
    return sid


def pool_insert(arms, pool):
    """装备样本插进这份 regulation（武器 / 防具各一段新编号），给每件记上编号；返回 {'w': {档: [武器编号]}, 'p': {档: [(防具编号, 部位)]}, 'a': {档: [护符编号]}}"""
    ids = {'w': {}, 'p': {}, 'a': {}}
    k = 0
    for t, lst in sorted(pool['w'].items()):
        for it in lst:
            it['id'] = POOL_W0 + 100 * k
            k += 1
            arms.W.rows[it['id']] = it['row']
            ids['w'].setdefault(t, []).append(it)
    k = 0
    for t, lst in sorted(pool['p'].items()):
        for it in lst:
            it['id'] = POOL_P0 + 100 * k
            k += 1
            arms.P.rows[it['id']] = it['row']
            a = arms.armor(it['id'])
            ids['p'].setdefault(t, []).append((it['id'], a['slot'] if a else None))
    for t, lst in sorted(pool['a'].items()):
        ids['a'][t] = [it['tal'] for it in lst]
    return ids


def wish_tiers(bands_cfg, b):
    """这一档许愿 / 光点的稀有度分布 [(档, 权重)]：tier_bands 的 weights，DLC 两档的传说是传说（幽影之地）"""
    w = bands_cfg[min(b, len(bands_cfg) - 1)]['weights']
    dlc = b >= 4
    return [(k if not (dlc and k == 3) else 4, w.get(r, 0)) for k, r in enumerate(powertab.RAR) if w.get(r, 0) > 0]


def run_dr(world, arms, tals, build, bands, D, runes_by_band, kills_by_band, runs, seed, blessing, mdrops, slots, tiers, pool, ids, bands_cfg):
    """DR 蒙特卡洛：每次从头推一遍，返回每档 (每档难度的 evaluate 结果, ar总和, 强化等级, 稀有度, 血量, 物理减伤, 护符件数, 护符倍数,
    防具和武器词条倍数, 主力武器带不带异常)。
    装备：开局（稀有武器按职业加点偏向 + 每个部位一件防具）→ 免费许愿 → 每档的未鉴定物品（普通敌人按击杀数，宝箱 / 拾取 / Boss 奖励按概率，
    打到一半时拿到一半），每件从装备样本里抽（武器照游戏：先抽 bias 把候选，按当前加点的权重挑一把）"""
    base, start_lv, _w, _a = class_start(world.reg, build['cls'])
    drops = world.drops(D)
    share = json.load(open(os.path.join(RR, 'settings.json'), encoding='utf-8')).get('gear_category_share') or {'weapon': 30, 'armor': 60, 'talisman': 10}
    cat_w = [share.get('weapon', 30), share.get('armor', 60), share.get('talisman', 10)]
    u_rate = {b: {i - UNID0: p for i, p in drops[b]['s'].items() if UNID0 <= i < UNID0 + 25} for b in range(bands)}   # 每杀一个普通敌人：类别 × 10 + 档 → 件数
    out = []
    rng_np = np.random.default_rng(seed)
    rng = random.Random(seed)
    levels = [level_from_runes(start_lv, runes_by_band[b]) for b in range(bands)]
    stats = [allocate(base, start_lv, levels[b], build) for b in range(bands)]
    s5 = lambda s: [s['str'], s['dex'], s['mag'], s['fai'], s['luc']]
    weff_cache = {}

    def weapon_eff(wid):
        sids = arms.resident(wid)
        if sids not in weff_cache:
            weff_cache[sids] = tals.sp_effect(sids) or tal_neutral()
        return weff_cache[sids]

    def draw(code, s, owned_w, owned_a, owned_t):
        """拿到一件未鉴定物品（code = 类别 × 10 + 档），鉴定成装备"""
        cat, t = divmod(code, 10)
        if cat == 0:
            lst = ids['w'].get(t) or []
            if not lst:
                return
            cands = [lst[rng.randrange(len(lst))] for _ in range(max(1, pool['bias']))]
            ws = [dr_pool.build_weight(c, s5(s)) * 10000 + 1 for c in cands] if len(cands) > 1 else [1]
            owned_w.add(rng.choices(cands, weights=ws)[0]['id'])
        elif cat == 1:
            lst = ids['p'].get(t) or []
            if lst:
                pid, slot = lst[rng.randrange(len(lst))]
                if slot:
                    owned_a[slot].append(arms.armor(pid))
        else:
            lst = ids['a'].get(t) or []
            if lst:
                owned_t.add(lst[rng.randrange(len(lst))])

    for _ in range(runs):
        owned_w, owned_t, owned_a = set(), set(), defaultdict(list)
        s0 = stats[0]
        # 开局：稀有武器（偏向职业加点，近战能用的）+ 每个部位一件防具
        for _k in range(20):
            tmp = set()
            draw(ASSUME['start_weapon_tier'], s0, tmp, owned_a, owned_t)
            if tmp and arms.usable(next(iter(tmp)), s0):
                owned_w |= tmp
                break
        for slot in ASSUME['slot_share']:
            t = rng.choice(ASSUME['start_armor_tiers'])
            lst = [x for x in ids['p'].get(t, []) if x[1] == slot]
            if lst:
                owned_a[slot].append(arms.armor(lst[rng.randrange(len(lst))][0]))
        stones = Counter()
        res = []
        for b in range(bands):
            half = kills_by_band[b] / 2.0
            mitems = mdrops.get(b, [])
            mp = np.array([p * drop_ratio(src) for _k, _i, p, src in mitems])
            first_half = rng_np.random(len(mitems)) < 0.5        # 这一档的宝箱 / Boss 哪一半在前半段拿到
            got = rng_np.random(len(mitems)) < mp
            for step in (0, 1):
                s = stats[b]
                if step == 0 and b in ASSUME['free_wishes']:
                    tw = wish_tiers(bands_cfg, b)
                    for _k in range(ASSUME['free_wishes'][b]):
                        cat = rng.choices((0, 1, 2), weights=cat_w)[0]
                        t = rng.choices([x[0] for x in tw], weights=[x[1] for x in tw])[0]
                        draw(cat * 10 + t, s, owned_w, owned_a, owned_t)
                for j in np.nonzero(got & (first_half if step == 0 else ~first_half))[0]:
                    kk, iid, _p, _src = mitems[j]
                    if kk == 's':
                        stones[stone_tier(world, iid, b)] += 1
                    elif kk == 'u':
                        draw(iid - UNID0, s, owned_w, owned_a, owned_t)
                for code, p in u_rate[b].items():
                    n = rng_np.poisson(half * p)
                    for _k in range(int(n)):
                        draw(code, s, owned_w, owned_a, owned_t)
                for sid, p in drops[b]['s'].items():
                    if 10100 <= sid <= 10210:
                        stones[stone_tier(world, sid, b)] += rng_np.poisson(half * p)
                if step == 0:
                    best, best_v = None, -1
                    ref = world.ref[b]
                    for w in sorted(owned_w):
                        if not arms.usable(w, s):
                            continue
                        i = arms.info(w)
                        lv = 0
                        for st in UPGRADE_STONES.get(i['rar'], [])[:arms.max_level(w)]:
                            if stones[st] <= 0:
                                break
                            lv += 1
                        we = weapon_eff(w)
                        a_ = arms.ar(w, lv, s)
                        v = weapon_value(arms, w, lv, s, ref) * float(np.mean(we['dealt'] * we['pow'])) + \
                            float(extra_out(float(a_.sum()), float(np.mean(ref[1])), ref[3], we['flat'], we['pct'], we['pcap']))
                        if v > best_v:
                            best, best_v = (w, lv, a_, i['rar'], i['w']), v
                    if best is None:
                        res.append(None)
                        continue
                    load = max(0.0, max_load(world.reg, s['end']) * ASSUME['load_ratio'] - best[4])
                    pdef = ASSUME['player_def'][0] + ASSUME['player_def'][1] * (levels[b] - 1)
                    pick = pick_armor(arms, tals, owned_a, load, best[0], best[1], s, pdef, ref)
                    pcut, a_eff, a_sids, a_res = armor_effect(tals, pick.values())
                    w_sids = arms.resident(best[0])
                    a_eff = tal_add(a_eff, combine_sids(tals, set(w_sids) - set(a_sids)))      # 武器的特效、流派加成和防具词条一起算
                    a_sids = frozenset(a_sids | set(w_sids))
                    php = hp_from_vigor(s['vit'])
                    dealt = 1 + ASSUME['blessing_dealt'] * blessing[b]
                    taken = 1 / (1 + ASSUME['blessing_taken'] * blessing[b])
                    ev, nt, gain, evb = tal_eval(world, b, arms, tals, owned_t, slots[b], best[0], best[1], s, levels[b], pdef, pcut,
                                                 a_eff, a_sids, a_res, dealt, taken, tiers)
                    res.append((ev, float(best[2].sum()), best[1], best[3], php, 1 - float(pcut[0]), nt, gain,
                                armor_gain(arms, best[0], best[1], s, pdef, pcut, a_eff, ref),
                                float(arms.status(best[0], best[1], s)[0].any()), evb))
        out.append(res)
    return out, levels


def vanilla_line(world, arms, tals, build, bands, runes_by_band, blessing, D, kills_by_band, mdrops, slots, runs, seed):
    """原版：长剑按各档常见强化等级，质变在 13 种里挑参考敌人身上每下伤害最高的（含出血 / 冻伤 / 毒）；
    防具每个部位在负重放得下的里按「单件的参考战斗力」（减伤 + 词条）取 75% 分位；
    护符按真实掉落蒙特卡洛（宝箱 / Boss 奖励 / 敌人掉落），各项取中位数"""
    base, start_lv, _w, _a = class_start(world.reg, build['cls'])
    wbase = build['van'] - build['van'] % 10000
    pieces = defaultdict(list)
    for pid in arms.P.rows:
        a = arms.armor(pid)
        if a and a['slot'] and a['w'] > 0 and pid >= 100000:
            pieces[a['slot']].append(a)
    fixed, levels = [], []
    for b in range(bands):
        L = level_from_runes(start_lv, runes_by_band[b])
        s = allocate(base, start_lv, L, build)
        lv = min(ASSUME['vanilla_upgrade'][b], arms.max_level(build['van']))
        cands = [wbase + 100 * k for k in range(13) if wbase + 100 * k in arms.W.rows and arms.usable(wbase + 100 * k, s)] \
            if ASSUME['vanilla_affinity'] else [build['van']]
        wid = max(cands or [build['van']], key=lambda w: weapon_value(arms, w, lv, s, world.ref[b]))
        a = arms.ar(wid, lv, s)
        load = max_load(world.reg, s['end']) * ASSUME['load_ratio'] - arms.info(wid)['w']
        pdef = ASSUME['player_def'][0] + ASSUME['player_def'][1] * (L - 1)
        cache, chosen = {}, []
        for slot, share in ASSUME['slot_share'].items():
            fit = [p for p in pieces[slot] if p['w'] <= load * share]
            if fit:
                # 打分取整到 1e-9 再排：几乎一样的两件不因为末位误差换位置（Rust 版同样）
                fit.sort(key=lambda p: round(ref_score(arms, wid, lv, s, pdef, p['cut'], tals.sp_effect(p['sp']) or tal_neutral(), world.ref[b], cache) * 1e9))
                chosen.append(fit[int(len(fit) * ASSUME['vanilla_armor_pct'])])
        pcut, a_eff, a_sids, a_res = armor_effect(tals, chosen)
        php = hp_from_vigor(s['vit'])
        dealt = 1 + ASSUME['blessing_dealt'] * blessing[b]
        taken = 1 / (1 + ASSUME['blessing_taken'] * blessing[b])
        fixed.append((s, lv, a, pcut, a_eff, a_sids, a_res, php, pdef, dealt, taken, wid, L))
        levels.append(L)
    drops = world.drops(D)
    tl = {b: (list(drops[b]['t']), np.array(list(drops[b]['t'].values()))) for b in range(bands)}
    mt = {b: [(i, p * drop_ratio(src)) for k, i, p, src in mdrops.get(b, []) if k == 't'] for b in range(bands)}
    rng_np = np.random.default_rng(seed)
    rng = random.Random(seed)
    sims = []
    for _ in range(runs):
        owned_t, res = set(), []
        for b in range(bands):
            first = rng_np.random(len(mt[b])) < 0.5
            got = rng_np.random(len(mt[b])) < np.array([p for _i, p in mt[b]])
            for step in (0, 1):
                for j in np.nonzero(got & (first if step == 0 else ~first))[0]:
                    owned_t.add(mt[b][j][0])
                ids, p = tl[b]
                if ids:
                    n = rng_np.poisson(kills_by_band[b] / 2.0 * p.sum())
                    owned_t.update(rng.choices(ids, weights=p, k=int(n)) if n else ())
                if step == 0:
                    s, lv, a, pcut, a_eff, a_sids, a_res, php, pdef, dealt, taken, wid, L = fixed[b]
                    ev, nt, gain, evb = tal_eval(world, b, arms, tals, owned_t, slots[b], wid, lv, s, L, pdef, pcut, a_eff, a_sids, a_res,
                                                 dealt, taken, [(1.0, 1.0)])
                    res.append(ev[0] + (nt, gain) + (tuple(evb[0][:3]) if evb else (None, None, None)))
        sims.append(res)
    out = []
    for b in range(bands):
        s, lv, a, pcut, a_eff, a_sids, a_res, php, pdef, dealt, taken, wid, L = fixed[b]
        med = [pct([r[b][k] for r in sims], 0.5) for k in range(9)]
        out.append({'h2k': med[0], 'h2d': med[1], 'idx': med[2], 'stx': med[2] / med[3], 'tal': med[4], 'talx': med[5],
                    'bh2k': med[6], 'bh2d': med[7], 'bidx': med[8],
                    'ar': float(a.sum()), 'upgrade': lv, 'hp': php, 'neg': 1 - float(pcut[0]),
                    'armx': armor_gain(arms, wid, lv, s, pdef, pcut, a_eff, world.ref[b]), 'stw': float(arms.status(wid, lv, s)[0].any()),
                    'wid': wid})
    return out, levels


def cumulative(world, bands, c, bonus):
    """每档打到一半时累计的卢恩（普通敌人按比例 c 杀、Boss 按 boss_ratio 杀）× (1 + 卢恩加成)"""
    out, acc, bc = [], 0.0, ASSUME['boss_ratio']
    for b in range(bands):
        mid = acc + (c * world.soul.get(b, 0) + bc * world.boss_soul.get(b, 0)) / 2
        out.append(mid * (1 + bonus))
        acc += c * world.soul.get(b, 0) + bc * world.boss_soul.get(b, 0)
    return out


def treasure_ratio():
    t = ASSUME['treasure_ratio']
    return min(1.0, ASSUME['kill_ratio']) if t is None else t


def drop_ratio(src):
    """宝箱 / Boss 奖励拿几成（map_drops 的来源 'm' / 'b'）"""
    return ASSUME['boss_ratio'] if src == 'b' else treasure_ratio()


def pct(vals, q):
    v = sorted(x for x in vals if x is not None and math.isfinite(x))
    if not v:
        return None
    k = (len(v) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


# ---------------------------------------------------------------- 并行：每个任务（一套加点 × 一种情况 × 一组卢恩/发现力）互相独立，
# 分给多个进程跑；每个进程只留最近用的那一种情况的数据（任务按情况排好序，换得少，内存不会翻几倍）。种子固定，结果和单进程一样
MODES = ('原版', 'DR 不随机敌人', 'DR 随机敌人')
_CFG, _W = {}, {}


def _init(cfg):
    _CFG.update(cfg)
    ASSUME.update(cfg.get('assume_over') or {})        # 命令行改的假设（--kill-ratio 等），子进程也要


def band_of(t):
    bands_cfg = _CFG['bands_cfg']
    return next((i for i, b in enumerate(bands_cfg) if t <= b.get('max_tier', 99)), len(bands_cfg) - 1)


def _ctx(mode):
    """这个进程里某种情况的 (World, Arms, Tals, 装备样本的编号)，懒加载；DR 的两种把装备样本插进自己的 regulation"""
    if mode not in _W:
        _W.clear()
        import gc
        gc.collect()
        van_maps = [os.path.join(RD, 'diste', 'Vanilla')]
        inp = _CFG['inputs']
        if mode == '原版':
            w = World(mode, Reg(os.path.join(GAME, 'regulation.bin')), van_maps, False, _CFG['map_tiers'], band_of)
        elif mode == 'DR 不随机敌人':
            w = World(mode, Reg(os.path.join(inp, 'plain', 'regulation.bin')), van_maps, False, _CFG['map_tiers'], band_of)
        else:
            rn = _CFG.get('rand_name', 'rand')
            maps = [os.path.join(inp, rn, 'maps', 'map', 'mapstudio'), os.path.join(RD, 'map', 'mapstudio')]
            w = World(mode, Reg(os.path.join(inp, rn, 'regulation.bin')), maps, True, _CFG['map_tiers'], band_of)
        arms, ids = Arms(w.reg), None
        if mode != '原版':                          # 情景（--scn-*）只改 DR
            arms.armor_scale = _CFG.get('scn_armor', 1.0)
            w.stone_tiers = _CFG.get('scn_stones')
            hpm = _CFG.get('scn_hp')
            if hpm:
                for b, e in w.enemies.items():
                    m = hpm[min(b, len(hpm) - 1)]
                    e['hp'] = e['hp'] * m
                    d, c, a, h, r = w.ref[b]
                    w.ref[b] = (d, c, a, h * m, r)
            w.pool = dr_pool.load(os.path.join(inp, 'pool.tsv'))
            ids = pool_insert(arms, w.pool)
        _W[mode] = (w, arms, Tals(w.reg), ids)
    return _W[mode]


def job_meta(mode):
    w = _ctx(mode)[0]
    nb = w.nbands
    out = {'nbands': nb, 'count': [w.count.get(b, 0) for b in range(nb)], 'lost': [w.lost.get(b, 0) for b in range(nb)],
           'hp_median': [wmedian(w.enemies[b]['hp'], w.enemies[b]['w']) for b in range(nb)],
           'atk_median': [wmedian(w.enemies[b]['atk'].sum(1), w.enemies[b]['w']) for b in range(nb)],
           'kinds': [len(w.enemies[b]['w']) for b in range(nb)], 'boss_count': [w.boss_count.get(b, 0) for b in range(nb)],
           'boss_hp_median': [wmedian(w.bosses[b]['hp'], w.bosses[b]['w']) if b in w.bosses else None for b in range(nb)]}
    if mode == '原版':
        out['extra'] = talisman_lots(w.reg, _CFG['map_tiers'], band_of)
    return out


def job_van(bname, bands, extra, slots):
    w, arms, tals, _ids = _ctx('原版')
    build, c = BUILDS[bname], ASSUME['kill_ratio']
    vbase = class_start(w.reg, build['cls'])[0]
    Dv = 100 + (vbase['luc'] if ASSUME['arcane_discovery'] else 0)
    line, levels = vanilla_line(w, arms, tals, build, bands, cumulative(w, bands, c, 0.0), ASSUME['dlc_blessing'], Dv,
                                [c * w.count.get(b, 0) for b in range(bands)], w.map_drops(Dv, _CFG['map_tiers'], band_of, extra),
                                slots, _CFG['runs'], _CFG['seed'])
    ser = {'mode': '原版', 'build': bname, 'difficulty': '普通', 'level': levels}
    for k in ('h2k', 'h2d', 'idx', 'stx', 'ar', 'upgrade', 'hp', 'neg', 'tal', 'talx', 'armx', 'stw', 'wid', 'bh2k', 'bh2d', 'bidx'):
        ser[k] = [x[k] for x in line]
    return [ser]


def job_dr(bname, mode, rbonus, dbonus, ts, bands, extra, slots):
    w, arms, tals, ids = _ctx(mode)
    build, c = BUILDS[bname], ASSUME['kill_ratio']
    base = class_start(w.reg, build['cls'])[0]
    D = 100 + (base['luc'] if ASSUME['arcane_discovery'] else 0) + 100 * dbonus
    tiers = [(float(t.get('enemy_hp', 1.0)), float(t.get('enemy_damage', 1.0))) for t in ts]
    sims, levels = run_dr(w, arms, tals, build, bands, D, cumulative(w, bands, c, rbonus), [c * w.count.get(b, 0) for b in range(bands)],
                          _CFG['runs'], _CFG['seed'], ASSUME['dlc_blessing'], w.map_drops(D, _CFG['map_tiers'], band_of, extra), slots, tiers,
                          w.pool, ids, _CFG['bands_cfg'])
    out = []
    for j, t in enumerate(ts):
        ser = {'mode': mode, 'build': bname, 'difficulty': t['name'], 'level': levels}
        get = {'h2k': lambda x: x[0][j][0], 'h2d': lambda x: x[0][j][1], 'idx': lambda x: x[0][j][2], 'stx': lambda x: x[0][j][2] / x[0][j][3],
               'ar': lambda x: x[1], 'upgrade': lambda x: x[2], 'rarity': lambda x: x[3], 'hp': lambda x: x[4], 'neg': lambda x: x[5],
               'tal': lambda x: x[6], 'talx': lambda x: x[7], 'armx': lambda x: x[8],
               'bh2k': lambda x: x[10][j][0] if x[10] else None, 'bh2d': lambda x: x[10][j][1] if x[10] else None,
               'bidx': lambda x: x[10][j][2] if x[10] else None}
        for key, f in get.items():
            for q, qn in ((0.1, '_p10'), (0.5, ''), (0.9, '_p90')):
                ser[key + qn] = [pct([f(r[b]) for r in sims if r[b] is not None], q) for b in range(bands)]
        ser['stw'] = [float(np.mean([r[b][9] for r in sims if r[b] is not None])) for b in range(bands)]   # 主力武器带异常的比例
        out.append(ser)
    return out


REF_CUT = 0.6       # 词条排行的参考玩家：防具合起来受到伤害 × 0.6（减伤 40%）


def job_affix(bands):
    """词条强度排行：每个词条（和武器特效）在各稀有度下，让参考玩家对参考敌人的战斗力指数（能挨几下 ÷ 砍几刀）乘多少。
    参考玩家 = 力敏加点、原版长剑按原版常见进度强化、防具减伤 40%，放在这个稀有度占比最高的那一档；参考敌人 = 那一档的中位敌人"""
    w, arms, tals, _ids = _ctx('DR 不随机敌人')
    build, c = BUILDS['力敏'], ASSUME['kill_ratio']
    base, start_lv, _w, _a = class_start(w.reg, build['cls'])
    runes = cumulative(w, bands, c, 0.0)
    cfg = _CFG['bands_cfg'][:bands]
    at = []
    for r in powertab.RAR:
        share = [b['weights'].get(r, 0) / max(1, sum(b['weights'].values())) for b in cfg]
        at.append(int(np.argmax(share)))
    ctxs = []
    for b in at:
        L = level_from_runes(start_lv, runes[b])
        s = allocate(base, start_lv, L, build)
        wid = build['van']
        lv = min(ASSUME['vanilla_upgrade'][b], arms.max_level(wid))
        pdef = ASSUME['player_def'][0] + ASSUME['player_def'][1] * (L - 1)
        pcut = np.full(5, REF_CUT)
        ctxs.append((wid, lv, s, pdef, pcut, w.ref[b], ref_score(arms, wid, lv, s, pdef, pcut, tal_neutral(), w.ref[b])))

    def gains(sp_by_r):
        out = []
        for k, sp in enumerate(sp_by_r):
            if not sp:
                out.append(None)
                continue
            wid, lv, s, pdef, pcut, ref, s0 = ctxs[k]
            e = tals.sp_effect((int(sp),))
            out.append(1.0 if e is None else ref_score(arms, wid, lv, s, pdef, pcut, e, ref) / max(s0, 1e-9))
        return out
    rows = []
    for key, fam in powertab.LIB['gear'].items():
        kind, note = powertab.INFO.get(key, ('?', ''))
        wr = fam.get('weight_r') or {}
        if not any(x > 0 for x in wr.get('armor', []) + wr.get('talisman', [])):
            continue                                  # 停用的（权重全 0）
        rows.append({'key': key, 'name': (fam.get('suffix') or ['', key])[1], 'group': fam.get('group', ''), 'kind': kind, 'note': note,
                     'where': '防具 / 护符', 'gain': gains([(fam.get('sp') or {}).get(r) for r in powertab.RAR])})
    for x in powertab.LIB['weapon']['special']['pool']:
        kind, note = powertab.INFO.get(x['key'], ('?', ''))
        rows.append({'key': x['key'], 'name': x['name'][0], 'group': '武器特效', 'kind': kind, 'note': note, 'where': '武器',
                     'gain': gains([x['sp']] * 4)})
    return {'bands_at': at, 'rows': rows}


WORKER_MB = 450          # 每个进程大概要的内存（一种情况的 regulation + 地图 + 缓存，含峰值余量）


def free_mb():
    """可用物理内存（MB）；拿不到就 None"""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong)] + \
                       [(n, ctypes.c_ulonglong) for n in ('total', 'avail', 'tpf', 'apf', 'tv', 'av', 'aev')]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        return m.avail / 2 ** 20 if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None
    except Exception:
        return None


def main():
    import time
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    ap = argparse.ArgumentParser()
    ap.add_argument('--inputs', default=os.path.join(HERE, 'inputs'), help='make_inputs.py 写的输入目录（plain\\、rand\\、pool.tsv）')
    ap.add_argument('--runs', type=int, default=200)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--jobs', type=int, default=min(10, os.cpu_count() or 1),
                    help='并行进程数（默认 10；可用内存不够时自动减少，进程崩了自动减半接着跑没做完的）')
    ap.add_argument('--out', default=os.path.join(HERE, 'result.json'))
    ap.add_argument('--scn-armor', type=float, default=1.0, help='情景：DR 防具每件的减伤 × 这个数（0.6 = 20%% 减伤变 12%%）')
    ap.add_argument('--scn-hp', default='', help='情景：DR 敌人血量按档位乘，逗号分隔，如 2,3,3,3,3,3（不够的档用最后一个）')
    ap.add_argument('--scn-stones', default='', help='情景：锻造石 / 失色锻造石按档位分层，如 1-3,4-6,7-9（同样的数量换成这一档允许的等级，没写的档不变）')
    ap.add_argument('--engine', choices=('rust', 'py'), default='rust',
                    help='模拟用哪个：rust（dev\\power_sim，快得多，默认）/ py（这个文件里的 Python 版，对照用）')
    ap.add_argument('--rand-name', default='rand', help='随机敌人用 inputs\\ 下哪个重随输出（make_inputs.py --rand-name 做的）')
    ap.add_argument('--randomizer-dir', default='', help='随机敌人对应的随机器输出（默认 randomizer\\；换种子的副本在 rz\\seed_<k>）')
    ap.add_argument('--kill-ratio', type=float, help='小怪清除率（ASSUME kill_ratio，默认 1）')
    ap.add_argument('--boss-ratio', type=float, help='Boss 清除率（ASSUME boss_ratio，默认 1）')
    ap.add_argument('--treasure-ratio', type=float, help='宝箱 / 拾取拿几成（默认跟小怪清除率走，最多 1）')
    a = ap.parse_args()
    over = {k: v for k, v in (('kill_ratio', a.kill_ratio), ('boss_ratio', a.boss_ratio), ('treasure_ratio', a.treasure_ratio)) if v is not None}
    ASSUME.update(over)
    t0 = time.time()
    if a.randomizer_dir:                         # 子进程 import 时读环境变量；这个进程直接改
        global RD
        os.environ['DR_RANDOMIZER_DIR'] = RD = a.randomizer_dir
    if powertab.MISSING:
        sys.exit('affix_power.json 里没写这些词条的强度折算：' + '、'.join(powertab.MISSING))
    need = [os.path.join(a.inputs, x) for x in ('plain\\regulation.bin', a.rand_name + '\\regulation.bin', 'pool.tsv')]
    if not all(os.path.isfile(p) for p in need):
        sys.exit('输入不全（%s），先跑 make_inputs.py' % '、'.join(p for p in need if not os.path.isfile(p)))
    S = json.load(open(os.path.join(RR, 'settings.json'), encoding='utf-8'))
    tiers = S['difficulty']['tiers']
    cfg = {'bands_cfg': S['tier_bands'], 'map_tiers': json.load(open(os.path.join(RR, 'data', 'map_tiers.json'), encoding='utf-8')),
           'inputs': a.inputs, 'runs': a.runs, 'seed': a.seed, 'rand_name': a.rand_name, 'assume_over': over,
           'scn_armor': a.scn_armor, 'scn_hp': [float(x) for x in a.scn_hp.split(',') if x.strip()],
           'scn_stones': [tuple(int(y) for y in x.split('-')) for x in a.scn_stones.split(',') if x.strip()]}
    scn = []
    if a.scn_armor != 1.0:
        scn.append('DR 防具减伤 ×%g' % a.scn_armor)
    if cfg['scn_hp']:
        scn.append('DR 敌人血量 ×' + ' / '.join('%g' % x for x in cfg['scn_hp']))
    if cfg['scn_stones']:
        scn.append('锻造石分层 ' + ' / '.join('%d-%d' % x for x in cfg['scn_stones']))
    groups = {}
    for t in tiers:
        groups.setdefault((t.get('rune_bonus', 0.0), t.get('discovery_bonus', 0.0)), []).append(t)
    if a.engine == 'rust':
        return main_rust(a, S, cfg, scn, groups, t0)
    jobs, fm = max(1, a.jobs), free_mb()
    if fm is not None and jobs > 1 and fm - 1000 < jobs * WORKER_MB:
        n = max(1, int((fm - 1000) // WORKER_MB))
        print('可用内存 %.0f MB，进程数 %d → %d' % (fm, jobs, n), flush=True)
        jobs = n
    meta, done = None, {}
    while True:
        try:
            with ProcessPoolExecutor(max_workers=jobs, initializer=_init, initargs=(cfg,)) as pool:
                if meta is None:
                    print('读取原版 / DR 不随机敌人 / DR 随机敌人（%d 个进程）…' % jobs, flush=True)
                    meta = dict(zip(MODES, pool.map(job_meta, MODES)))
                    bands = min(m['nbands'] for m in meta.values())
                    extra = meta['原版']['extra']
                    slots_v = ASSUME['talisman_slots'][:bands]
                    slots_r = [n + 1 for n in slots_v]          # 第五个护符槽（誓约槽）不占护符皮带的 4 个
                    print('  护符：treasures.json 之外原版地图上的护符掉落表 %d 行；护符栏 原版 %s / DR %s' % (len(extra), slots_v, slots_r), flush=True)
                    for n, m in meta.items():
                        print('  %s：每档普通敌人位置 %s（%s 种），没对上的 %s' % (n, m['count'][:bands], m['kinds'][:bands], m['lost'][:bands]), flush=True)
                # 按情况分批提交（同一进程尽量连着做同一种情况），结果最后按原来的顺序拼；崩了重来时只交没做完的
                futs = [((bname,), pool.submit(job_van, bname, bands, extra, slots_v)) for bname in BUILDS if (bname,) not in done]
                if ('affix',) not in done:
                    futs.append((('affix',), pool.submit(job_affix, bands)))
                for mode in MODES[1:]:
                    for bname in BUILDS:
                        for (rb, db), ts in groups.items():
                            if (bname, mode, rb, db) not in done:
                                futs.append(((bname, mode, rb, db), pool.submit(job_dr, bname, mode, rb, db, ts, bands, extra, slots_r)))
                total = len(done) + len(futs)
                for key, f in futs:
                    done[key] = f.result()
                    what = ('词条排行' if key == ('affix',) else '%s · 原版' % key) if len(key) == 1 else \
                        '%s · %s · 卢恩 %+.0f%% 发现力 %+.0f' % (key[0], key[1], key[2] * 100, key[3] * 100)
                    print('  [%d/%d %4.0f 秒] %s' % (len(done), total, time.time() - t0, what), flush=True)
            break
        except (BrokenProcessPool, MemoryError) as e:
            if jobs <= 1:
                raise
            jobs = max(1, jobs // 2)
            print('有进程崩了（%s），改成 %d 个进程接着跑没做完的' % (type(e).__name__, jobs), flush=True)
    result = {'bands': [b['name'] for b in S['tier_bands'][:bands]], 'assume': ASSUME, 'kill_ratio': ASSUME['kill_ratio'],
              'power_assume': powertab.ASSUME, 'enemy_hp_band': S.get('enemy_hp_band'), 'target_ratio': ASSUME['target_ratio'],
              'boss_target_ratio': ASSUME['boss_target_ratio'],
              'enemies': {n: {k: m[k][:bands] for k in ('count', 'lost', 'kinds', 'hp_median', 'atk_median', 'boss_count', 'boss_hp_median')}
                          for n, m in meta.items()},
              'talisman_slots': {'原版': slots_v, 'DR': slots_r}, 'runs': a.runs, 'scenario': '；'.join(scn),
              'affix_rank': done[('affix',)], 'series': []}
    for bname in BUILDS:                                    # 和以前一样的顺序：每套加点 原版 → 不随机 → 随机
        result['series'] += done[(bname,)]
        for mode in MODES[1:]:
            for rb, db in groups:
                result['series'] += done[(bname, mode, rb, db)]
    json.dump(result, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=lambda o: None if o == math.inf else str(o))
    print('写好了：', a.out, '（%.0f 秒）' % (time.time() - t0))


SIM_DIR = os.path.normpath(os.path.join(HERE, '..', 'power_sim'))
SIM_EXE = os.path.join(SIM_DIR, 'target', 'release', 'power_sim.exe')


def job_bundle(mode, cfg, out):
    import bundle
    return bundle.export(mode, cfg, out)


def main_rust(a, S, cfg, scn, groups, t0):
    """Rust 版：三种情况各导出一个数据包（bundle.py，并行），再交给 dev\\power_sim 做蒙特卡洛和评估，结果拼成和 Python 版一样的 result.json"""
    import subprocess, time
    from concurrent.futures import ProcessPoolExecutor
    cfg = dict(cfg, tiers=S['difficulty']['tiers'])
    r = subprocess.run([os.path.join(os.path.expanduser('~'), '.cargo', 'bin', 'cargo.exe'), 'build', '--release'], cwd=SIM_DIR,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        sys.exit('编译 dev\\power_sim 失败：\n' + r.stderr[-3000:])
    paths = [os.path.join(a.inputs, 'bundle_%d%s.json' % (k, '_' + a.rand_name if k == 2 else '')) for k in range(len(MODES))]
    print('导出数据包（%d 种情况并行）…' % len(MODES), flush=True)
    with ProcessPoolExecutor(max_workers=len(MODES)) as pool:
        meta = dict(zip(MODES, pool.map(job_bundle, MODES, [cfg] * len(MODES), paths)))
    bands = min(m['nbands'] for m in meta.values())
    slots_v = ASSUME['talisman_slots'][:bands]
    slots_r = [n + 1 for n in slots_v]
    print('  数据包好了（%.0f 秒）；护符栏 原版 %s / DR %s' % (time.time() - t0, slots_v, slots_r), flush=True)
    for n, m in meta.items():
        print('  %s：每档普通敌人位置 %s（%s 种），没对上的 %s；Boss %s' % (n, m['count'][:bands], m['kinds'][:bands], m['lost'][:bands], m['boss_count'][:bands]), flush=True)
    share = S.get('gear_category_share') or {}
    A = ASSUME
    sim_cfg = {
        'bundles': paths, 'out': os.path.join(a.inputs, 'sim_out.json'), 'runs': a.runs, 'seed': a.seed, 'threads': max(1, a.jobs), 'bands': bands,
        'assume': {'kill_ratio': A['kill_ratio'], 'boss_ratio': A['boss_ratio'], 'treasure_ratio': treasure_ratio(), 'player_def': list(A['player_def']), 'vanilla_upgrade': A['vanilla_upgrade'], 'dlc_blessing': A['dlc_blessing'],
                   'blessing_dealt': A['blessing_dealt'], 'blessing_taken': A['blessing_taken'], 'arcane_discovery': A['arcane_discovery'],
                   'load_ratio': A['load_ratio'], 'slot_share': [[k, v] for k, v in A['slot_share'].items()], 'hit_interval': A['hit_interval'],
                   'enemy_hit_interval': A['enemy_hit_interval'], 'status_sim_hits': A['status_sim_hits'], 'vanilla_armor_pct': A['vanilla_armor_pct'],
                   'free_wishes': [[int(k), int(v)] for k, v in A['free_wishes'].items()], 'start_armor_tiers': A['start_armor_tiers'],
                   'start_weapon_tier': A['start_weapon_tier'], 'boss_flasks': [float(x) for x in A['boss_flasks']], 'flask_heal': A['flask_heal'],
                   'regen_cap': REGEN_CAP, 'flat_eff': FLAT_EFF},
        'groups': [{'rb': rb, 'db': db, 'tiers': [{'name': t['name'], 'enemy_hp': float(t.get('enemy_hp', 1.0)), 'enemy_damage': float(t.get('enemy_damage', 1.0))}
                                                   for t in ts]} for (rb, db), ts in groups.items()],
        'build_order': list(BUILDS), 'slots_v': slots_v, 'slots_r': slots_r,
        'band_weights': [[float(b['weights'].get(r, 0)) for r in powertab.RAR] for b in S['tier_bands']],
        'cat_w': [float(share.get('weapon', 30)), float(share.get('armor', 60)), float(share.get('talisman', 10))],
        'upgrade_stones': {str(k): v for k, v in UPGRADE_STONES.items()},
    }
    cp = os.path.join(a.inputs, 'sim_config.json')
    json.dump(sim_cfg, open(cp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    p = subprocess.Popen([SIM_EXE, cp], stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    for line in p.stdout:
        print(line.rstrip(), flush=True)
    if p.wait():
        sys.exit('dev\\power_sim 出错（退出码 %d）' % p.returncode)
    sim = json.load(open(sim_cfg['out'], encoding='utf-8'))
    result = {'bands': [b['name'] for b in S['tier_bands'][:bands]], 'assume': ASSUME, 'kill_ratio': ASSUME['kill_ratio'],
              'power_assume': powertab.ASSUME, 'enemy_hp_band': S.get('enemy_hp_band'), 'target_ratio': ASSUME['target_ratio'],
              'boss_target_ratio': ASSUME['boss_target_ratio'], 'engine': 'rust',
              'enemies': {n: {k: m[k][:bands] for k in ('count', 'lost', 'kinds', 'hp_median', 'atk_median', 'boss_count', 'boss_hp_median')}
                          for n, m in meta.items()},
              'talisman_slots': {'原版': slots_v, 'DR': slots_r}, 'runs': a.runs, 'scenario': '；'.join(scn),
              'affix_rank': sim['affix_rank'], 'series': sim['series']}
    json.dump(result, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('写好了：', a.out, '（%.0f 秒）' % (time.time() - t0))


if __name__ == '__main__':
    main()
