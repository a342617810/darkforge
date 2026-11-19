# -*- coding: utf-8 -*-
"""斗技场试炼（用户 2026-11-10；提案 dev\\item_system\\斗技场试炼提案.md）：原版三个竞技场的雕像对话里选「斗技场试炼」，
花 1 / 2 / 3 个星光碎片打 2 / 4 / 8 波（一波魇化精英、一波 Boss 轮流），中间每波问要不要继续；奖励（未鉴定物品、骨灰）
每打完一波就放进背包，途中死了收回这次给的（用户 2026-11-10）。只在开了敌人随机时做（精英从随机器的精英池里抽，强度用随机器的缩放效果）。
这里（重随）：
- 每个竞技场一份敌人池（按这一局的种子定，once.rng_for）：Boss bosses 个（不同模型；排除追忆 Boss、多阶段、两人共用击败标记的、
  随机器标了不能放 / 不死 / 友方的、体型 3），精英 elite_kinds 种 × elite_copies 个（随机器的精英池：普通敌人里属于精英族的，
  同 enemypreset.py 的 late_elite）。DLC 的只进王城（而且随机器开了 DLC）。
- 红 / 蓝粪金龟（打死回一次红露滴 / 蓝露滴的那种，原版野外的；用户 2026-11-15「副本里的精英有20%的概率是红蓝粪金龟」）：
  每种 scarab_copies 个，dark_core 排出场时精英波每个精英位 scarab_pct% 换成它（红蓝各半，一波里至少留一个真精英）。
  血量照原版 + 随机器的缩放（不加精英的地区血量），不魇化；会逃跑钻地，不算进「这一波打完」。
- 每个敌人复制一行敌人参数（ARENA_NPC0 起）：不掉原版东西；空的特殊效果格挂随机器的缩放效果（来源位置的强度 → 这个竞技场的强度，
  精英用普通版、Boss 用 Boss 版），魇化在 dark_core 挂。
- features.json 的 arena：地图要放的部件（sc/arena.py 用 msbtool 导进 m45 地图、写事件和雕像对话）；
  dll\\dark_core\\arena.txt：波次、奖励、标记（执行在 dark_core 的 arena.rs）。
- 按波次挂的效果（用户 2026-11-17「给任意指定波数敌人挂自定义效果」）：settings 的 wave_fx 每条规则 = 哪个竞技场、哪种场次、第几波、
  哪种敌人、几率、挂哪些效果包（rr/foefx.py 的通用敌人效果包；规则里也能直接写 fx，做成包 arena_rule<第几条>）→ arena.txt 的 wfx 行，
  dark_core 出场时按规则挂（foefx.rs）。每波血量加成也走同一个模块。
竞技场：0 王城（m45_00，DLC 后期强度）、1 盖利德（m45_01，王城）、2 宁姆格福（m45_02，利耶尼亚）。
（2026-11-10 以前把 m45_01 当成宁姆格福、m45_02 当成盖利德，用户游戏里从宁姆格福的雕像进去是盖利德的竞技场）"""
from .common import *  # noqa: F401,F403
from . import once

COLOS = ('m45_00_00_00', 'm45_01_00_00', 'm45_02_00_00')
COLO_ZH = ('王城竞技场', '盖利德竞技场', '宁姆格福竞技场')
FLAG_BASE = 45000000                  # 竞技场 X 的地图标记 / 实体 F = 45000000 + X × 10000（后四位 ≥ 2000 的标记死亡、读档、传送就清零）
PART_ENT, WARP_ENT = 3000, 3980       # 部件实体 F + 3000 + k，玩家传送落点 F + 3980
SPAWN, DEAD, ASK, LEAVE, NOTE_BITS = 2400, 2500, 2600, 2610, 2630   # 出场 / 死了 / 问继续（+1 是 +2 否 +3 取消）/ 离开（+雕像序号）/ 提示位
NOTE_N = 5                            # 竞技场里的提示：5 位，编号 1~31（sc/arena.py 的事件显示 EventTextForMap NOTE_TEXT0 + 编号）
REQ, LEN0, WARP = 93670, 93671, 93673   # 雕像对话的请求、场次 2 位（93671~93672）、传送请求（dev\event_flags\说明.md）
SHARD = 1290                          # 星光碎片
ARENA_NPC0 = 99300000                 # 敌人参数副本：ARENA_NPC0 + X × 100 + k
SCALE0 = 7800001                      # 随机器的缩放效果：7800001 + 4 × ((a − 1) × 33 + b 的序号) + 变体（0 普通、3 Boss）
NOTE_TEXT0 = 80099200                 # 竞技场里的提示（EventTextForMap）
HPW_SP0, HPW_N = 7319970, 4           # 血量随波次的效果行：第 j 档（1 起）= HPW_SP0 + j − 1，最大血量 ×(1 + hp_step × j)（dark_core 出场时挂）
HPW_TEMPLATE = 90030                  # 效果行的底子（同 rr/hpunify.py：去掉「咒死无效」那一位）
CLASSES_BOSS = ('Boss', 'MinorBoss', 'Miniboss', 'NightMiniboss', 'Evergaol')
BAD_BOSS_TAGS = {'noplace', 'norandom', 'immortal', 'friendly', 'uniquearena', 'scalephase', 'npcpart', 'size:3', 'excludemultiphase'}
DLC_MAP_PREFIX = ('m20', 'm21', 'm22', 'm25', 'm28', 'm40', 'm41', 'm42', 'm43', 'm61')
# 精英池里不要龙（用户 2026-11-10）：敌人参数族 = 模型号。飞龙 / 辉石龙 c450x、古龙 c451x、龙王 c4520、熔岩土龙 c4910 / c5920、尖峰飞龙 c5580
# （龙人士兵 c4650、龙树守卫 c3250 不是龙，照常）
DRAGON_FAMILIES = {4500, 4501, 4502, 4503, 4510, 4511, 4520, 4910, 5580, 5920}
# 精英站位（sc/arena.py 按竞技场的玩家出生点摆）：Boss 在中间偏后，精英在前方一排 5 个位置
ELITE_SPOTS = 5
# 红 / 蓝粪金龟的站位（sc/arena.py ELITE_AT 的第 6、7 个，在精英那排前面）：同一波里红的、蓝的最多各一只
SCARAB_SPOTS = (5, 6)
# 各竞技场的雕像（进场的对话、离开时传回来的地方）：(雕像所在地图, 地图块, 传送落点实体, 对话脚本, 落点部件从哪来, 落点坐标, 雕像坐标)
# 落点：王城两张图照抄本图的玩家部件；野外小格子里没有玩家部件，从 m60_40_52_00 照抄（msbtool batch 的 player）。
# 坐标：王城是原版「復帰ポイント 篝火 闘技受付」区域 11002957 的位置（灰城同一处）；宁姆格福是雕像旁「闘技場チュートリアル」区域；
# 盖利德是雕像南边赐福的传送落点（c0000_9000，1047420980）——那边的教程区域在入口平台底下，2026-11-10 用户传回去掉到了地下
# 后两项：同一处的复活点区域（试炼中死了在这里复活，用户 2026-11-10「传送回进入竞技场时的位置」）和照抄哪个 SpawnPoint 区域
# （原版设复活点 2003[23] 用的都是 SpawnPoint 区域，玩家部件不行；- = 本图，野外照抄 m60_34_50_00 的「復帰ポイント ラニ前」）
STATUES = {
    0: [('m11_00_00_00', (11, 0, 0, 0), 11000990, 't620001100', ('clone', 'c0000_9000'), (-348.0, 28.6, -424.8), (-349.5, 29.6, -435.7), 11002990, ('-', 11002697)),
        ('m11_05_00_00', (11, 5, 0, 0), 11050990, 't620001105', ('clone', 'c0000_9000'), (-348.0, 28.6, -424.8), (-349.5, 29.6, -435.7), 11052990, ('-', 11052680))],
    1: [('m60_47_42_00', (60, 47, 42, 0), 1047420990, 't622006000', ('player', 'm60_40_52_00', 'c0000_9000'), (-5.1, 147.6, -92.3), (-4.6, 148.1, -85.6),
         1047422990, ('m60_34_50_00', 1034502610))],
    2: [('m60_42_40_00', (60, 42, 40, 0), 1042400990, 't621006000', ('player', 'm60_40_52_00', 'c0000_9000'), (-42.8, 205.2, -113.8), (-39.9, 206.5, -106.2),
         1042402990, ('m60_34_50_00', 1034502610))],
}
BANNER = 2604                         # 竞技场里的标记：F + 2604 = 放「TRIAL COMPLETE」大字幕（最后一波打完，sc/arena.py 的事件放）
RUN = 2620                            # 竞技场里的标记：F + 2620 + 雕像序号 = 试炼进行中（dark_core 进场后点亮；这时死了把复活点设到那个雕像旁）
# 联机（联机计划 13.13）：F + 2605 开打（dark_core 等各台电脑都就绪了点亮，事件打开 AI、关掉无敌）、F + 2606 本机死了（dark_core 点亮，
# 复活点照设，不靠事件里的 10000）、F + 2640 + k 部件 k 读进来了（事件点亮，dark_core 看）
ENGAGE, MYDEAD, READY = 2605, 2606, 2640
# 无尽模式的生成器实验（用户 2026-11-17「开始之前无尽模式的生成器实验吧」；settings 的 generator_test 写竞技场名字才做，默认不做）：
# 前五轮在那个竞技场照抄一个精英部件当模板（F + 3910），配一个生成器（F + 3900）；出生点区域从原版学院 m14 照抄（学院的
# 「レナラの子供たち_ジェネレートポイントA01」14002900）。开发工具 F9 按钮经 dark_core 点亮请求标记，竞技场的事件听着去叫生成器；
# dark_core 的 arena.rs 记下这些敌人出现 / 倒下 / 又活了 / 消失（实体编号、地址、位置）。
# 出生点区域照抄学院 m14 的；生成器第五轮起照抄湖底 m12_08 的 12083260（类型 3：间隔 0、开场不生，原版靠事件 2003[54] 叫，
# 湖底 m12_01、地下墓地 m30_03 都这样用，m30_03 关着的也叫）。前四轮照抄学院 14003814（类型 1：只会死后按间隔复活，2003[54] 叫不动）
GEN_SRC_MAP, GEN_SRC_GEN, GEN_SRC_REGION = 'm12_08_00_00', 12083260, 14002900
GEN_REGION_MAP = 'm14_00_00_00'
# 第三轮（类型 1，间隔 3~5 秒）实测：生成器不复制，而是模板死了以后把它本身在出生点复活（地址、实体编号不变，满血）。
# 第四轮（类型 1，间隔 600 秒）：死了 27 秒后点「刷一只」不复活，类型 1 叫不动。
# 第五轮（类型 3，同时 1 只、总数不限、一次 1 只、间隔 0、开场不生，照湖底 m12_08 的；2026-11-19 实测）：死了不会自己回来（开着也不会），
# 「刷一只」0.5 秒后在出生点满血复活，还是那只（地址、实体编号不变）；活着时叫一下会挪到出生点；出生点按 1 → 2 → 3 换。
# 第六轮：不要模板了，给这个竞技场池子里每个敌人各配一个这样的生成器（管那个部件本身），出生点 6 个（F + 3901~3906），
# 生成器 k 的出生点从第 k 个开始排（几只一起叫不挤在一处）。生成器实体 F + 3700 + k、请求标记 F + 2700 + k、事件 F + 2950 + k。
# 2026-11-19 实测：开场不生（initial 0）的话，生成器没叫过的敌人事件启用了也不出来（第 1 波两只都没出、一只没排到的 Boss 自己被放了出来）。
# 第七轮（现在）：开场就生 1 只（第三轮的模板就是这样，读图时是站在原位的普通敌人），出场照旧走事件，只有复活用生成器叫
GEN_ENT0, GEN_REG0, GEN_REQ0, GEN_EV0 = 3700, 3901, 2700, 2950
GEN_AT = [(-6.0, -12.0), (6.0, -12.0), (0.0, -14.0), (-10.0, -3.0), (10.0, -3.0), (0.0, -5.0)]   # 出生点（同 sc/arena.py 的坐标系：竞技场中心、玩家出生点朝 −z）
GEN_PARAMS = dict(max_num=1, limit=-1, min_gen=1, max_gen=1, min_iv=0.0, max_iv=0.0, initial=1)
DEFAULT = dict(enabled=True, tiers=[31, 13, 8], bosses=8, elite_kinds=4, elite_copies=4, elite_per_wave=2, scarab_pct=20, scarab_copies=4,
               cost=[1, 2, 3], waves=[2, 4, 8],
               items_elite=2, items_boss=1, ash_boss=1, clear_bonus=[1, 2, 4], refund=[0, 1, 2], elite_two=[0, 0, 10, 15, 20, 30, 40, 50],
               reward_tiers=[[4, 4], [3, 4], [2, 3]], reward_scale=[2, 1, 1], hp_every=2, hp_step=0.1, wave_fx=[], generator_test='',
               ash_weights=[[0, 30, 40, 30], [0, 70, 20, 10], [50, 35, 10, 5]],
               difficulty_mult=[[1.6, 1.2, 0.7, 0.4], [1.3, 1.1, 0.85, 0.6], [1, 1, 1, 1], [0.85, 1, 1.15, 1.3],
                                [0.7, 0.95, 1.3, 1.7], [0.55, 0.9, 1.45, 2.2], [0.4, 0.8, 1.6, 2.8], [0.3, 0.7, 1.7, 3.5]])


def cfg(S):
    c = S.get('arena') or {}
    if not c.get('enabled', True):
        return None
    out = dict(DEFAULT)
    out.update({k: v for k, v in c.items() if k in DEFAULT})
    return out


def flag_base(x):
    return FLAG_BASE + 10000 * x


def scale_sp(a, b, boss):
    """随机器「scaling a->b」的效果行（同一档没有，返回 None）"""
    if a == b:
        return None
    return SCALE0 + 4 * ((a - 1) * 33 + (b - 1 if b < a else b - 2)) + (3 if boss else 0)


def read_enemy_txt(path):
    """enemy.txt 的 Enemies：{实体: dict(map, src_map, part, cls, tags, defeat, next, npcname)}；
    大地图格子里的敌人 Name 写成「m60_48_55_00-c3150_9000」（部件在前面那个小格子的地图里）"""
    t = open(path, encoding='utf-8').read()
    t = t[t.index('\nEnemies:'):]
    t = t[:t.index('\nPassiveAdjustments:')] if '\nPassiveAdjustments:' in t else t
    out = {}
    for blk in re.split(r'\n(?=- ID: )', t):
        m = re.match(r'- ID: (\d+)\n  Map: (\S+)\n  Name: (\S+)\n  Class: (\S+)', blk)
        if not m:
            continue
        name = m.group(3)
        src_map, part = (name.split('-', 1) if '-' in name else (m.group(2), name))
        g = lambda k: (re.search(r'^  %s: (.*)$' % k, blk, re.M) or [None, None])[1]
        nn = re.search(r'^    NpcName: (\d+)$', blk, re.M)
        out[int(m.group(1))] = dict(map=m.group(2), src_map=src_map, part=part, cls=m.group(4),
                                    tags=set((g('Tags') or '').split()), defeat=g('DefeatFlag'), next=g('NextPhase'),
                                    npcname=int(nn.group(1)) if nn else 0)
    return out


def rand_options(rd):
    """随机器最近一次成功的随机化用的选项（同 reroll.py 的 rand_options）"""
    for lp in sorted(glob.glob(os.path.join(rd, 'spoiler_logs', '*_log_*.txt')), key=os.path.getmtime, reverse=True):
        t = open(lp, encoding='utf-8', errors='replace').read()
        if 'Exception' in t or not t.startswith('Options and seed:'):
            continue
        return set(t.split('\n', 1)[0].split(':', 1)[1].split())
    return set()


_NAMES = {}


def part_names(vdir, m):
    """原版地图里的部件名集合（缓存）。enemy.txt 里中格子（m60_xx_yy_01）的条目写的部件名有的和小格子地图里的对不上
    （m60_45_52_00-c4660_9002，图里实际是 c4660_9001，2026-11-10 msbtool 导不进），抽池时要先核对"""
    if m not in _NAMES:
        out = set()
        try:
            raw = erlib.dcx_decompress(open(os.path.join(vdir, m + '.msb.dcx'), 'rb').read())
            pos = 0x10
            while pos:
                cnt = struct.unpack_from('<i', raw, pos + 4)[0]
                noff = struct.unpack_from('<q', raw, pos + 8)[0]
                offs = struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16)
                nxt = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
                if erlib._u16str(raw, noff) == 'PARTS_PARAM_ST':
                    out = {erlib._u16str(raw, o + struct.unpack_from('<q', raw, o)[0]) for o in offs}
                    break
                pos = nxt
        except (OSError, struct.error, ValueError):
            pass
        _NAMES[m] = out
    return _NAMES[m]


def is_dlc(e):
    return e['src_map'].startswith(DLC_MAP_PREFIX) or e['map'].startswith(DLC_MAP_PREFIX) or e['part'][:2] == 'c5'


def build(ctx):
    """敌人池 + 敌人参数副本；ctx.arena = def_lines 用的数据（没做就 None）"""
    ctx.arena = None
    c = cfg(ctx.S)
    rd = getattr(ctx.a, 'randomizer_dir', '') or ''
    if not c or not rd:
        return
    import enemypreset as ep
    from .stage3 import diste                 # 高难度世界 randomizer_hi 没有 diste，用平常的随机器目录里的（2026-11-10：死亡以上斗技场试炼整个跳过，雕像还是原版「要联机」）
    enemy_txt = diste(rd, 'Base', 'enemy.txt')
    vdir = diste(rd, 'Vanilla')
    if not os.path.isfile(enemy_txt) or not os.path.isdir(vdir):
        ctx.report.append('斗技场试炼：找不到随机器的 enemy.txt / 原版地图，跳过')
        return
    S_sp = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    if SCALE0 not in S_sp.rows:
        ctx.report.append('斗技场试炼：regulation 里没有随机器的缩放效果（%d），跳过' % SCALE0)
        return
    dlc_on = 'dlc' in rand_options(rd)
    ents = read_enemy_txt(enemy_txt)
    npc = ep.vanilla_npc(rd, os.path.join(HERE, 'cache'))
    fams = elite_families(ctx.data_dir)
    tiers = ep.target_tiers()
    rem = json.load(open(os.path.join(ctx.data_dir, 'remembrance_bosses.json'), encoding='utf-8'))
    rem_ids = {int(k) for g in ('base', 'dlc', 'dlc_extra') for k in rem.get(g, {})}
    N = erlib.Param(ctx.bnd.get('NpcParam.param'))
    LN = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'NpcParam.xml')))[0]}
    get = lambda row, f: struct.unpack_from('<' + LN[f][1], row, LN[f][2])[0]
    sp_slots = sorted((f for f in LN if re.fullmatch(r'spEffectID\d+', f)), key=lambda f: int(f[len('spEffectID'):]))
    have_map = lambda e: os.path.isfile(os.path.join(vdir, e['src_map'] + '.msb.dcx'))

    def tier_of(ent):
        t = tiers.get(ent)
        if t is None:
            row = N.rows.get(npc.get(ent))
            s = get(row, 'spEffectID3') if row is not None and 'spEffectID3' in LN else 0
            if 7000 <= s <= 7200 and s % 10 == 0:
                t = max(1, (s - 7000) // 10)
            elif 20007000 <= s < 20007400 and s % 10 == 0:
                t = min(33, 21 + ((s - 20007000) % 200) // 10)
        if t is None:
            t = ctx.map_tiers.get(ents[ent]['map'])
        return max(1, min(34, int(t))) if t else None

    # Boss 池：两人共用击败标记的（双人组）、有下一阶段的（多阶段第一段）和被当成下一阶段的都不要
    from collections import Counter as _C
    df_n = _C(e['defeat'] for e in ents.values() if e['defeat'])
    phase2 = {int(e['next']) for e in ents.values() if e['next']}
    boss_all = [k for k, e in ents.items()
                if e['cls'] in CLASSES_BOSS and k not in rem_ids and not (e['tags'] & BAD_BOSS_TAGS) and not e['next'] and k not in phase2
                and (not e['defeat'] or df_n[e['defeat']] == 1) and k in npc and npc[k] in N.rows and have_map(e)]
    elite_all = [k for k, e in ents.items()
                 if e['cls'] == 'Basic' and k in npc and npc[k] in N.rows and npc[k] // 10000 in fams and npc[k] // 10000 not in DRAGON_FAMILIES
                 and not (e['tags'] & ep.BAD_SOURCE) and have_map(e)]
    if not boss_all or not elite_all:
        ctx.report.append('斗技场试炼：Boss 池 %d、精英池 %d，跳过' % (len(boss_all), len(elite_all)))
        return

    def flask(k):
        """回红露滴的粪金龟 0、回蓝露滴的 1（敌人参数的 estusFlaskRecoveryParamId + hp / mpEstusFlaskLotPoint），别的 None"""
        row = N.rows.get(npc.get(k))
        if row is None or get(row, 'estusFlaskRecoveryParamId') <= 0:
            return None
        hp, mp = get(row, 'hpEstusFlaskLotPoint'), get(row, 'mpEstusFlaskLotPoint')
        return 0 if hp > 0 and mp <= 0 else 1 if mp > 0 and hp <= 0 else None
    scarab_all = ([], [])
    for k in sorted(ents):
        e = ents[k]
        if e['cls'] == 'Scarab' and not is_dlc(e) and not (e['tags'] & ep.BAD_SOURCE) and have_map(e) and flask(k) is not None:
            scarab_all[flask(k)].append(k)
    for x in range(3):
        if ARENA_NPC0 + 100 * x in N.rows:
            raise RuntimeError('斗技场试炼：敌人参数 %d 已经有人用了' % (ARENA_NPC0 + 100 * x))
    colos = []
    added = 0
    for x, m in enumerate(COLOS):
        rng = once.rng_for(ctx, 'arena', x)
        tgt = int(c['tiers'][x])
        dlc_ok = dlc_on and x == 0
        F = flag_base(x)
        pick_b = [k for k in sorted(boss_all) if dlc_ok or not is_dlc(ents[k])]
        rng.shuffle(pick_b)
        bosses, models = [], set()
        for k in pick_b:
            mdl = ents[k]['part'].split('_')[0]
            if mdl in models or tier_of(k) is None or ents[k]['part'] not in part_names(vdir, ents[k]['src_map']):
                continue
            models.add(mdl)
            bosses.append(k)
            if len(bosses) >= int(c['bosses']):
                break
        pick_e = [k for k in sorted(elite_all) if dlc_ok or not is_dlc(ents[k])]
        rng.shuffle(pick_e)
        kinds, efam = [], set()
        for k in pick_e:
            f = npc[k] // 10000
            if f in efam or tier_of(k) is None or ents[k]['part'] not in part_names(vdir, ents[k]['src_map']):
                continue
            efam.add(f)
            kinds.append(k)
            if len(kinds) >= int(c['elite_kinds']):
                break
        scarabs = []                          # [(0 红 / 1 蓝, 来源)]：每种挑一只，复制 scarab_copies 个
        if float(c['scarab_pct']) > 0:
            for col, pool in enumerate(scarab_all):
                cand = [k for k in pool if tier_of(k) is not None and ents[k]['part'] in part_names(vdir, ents[k]['src_map'])]
                if cand:
                    scarabs += [(col, rng.choice(cand))] * max(0, int(c['scarab_copies']))
        parts = []
        for kind, srcs in (('b', bosses), ('e', [k for k in kinds for _ in range(int(c['elite_copies']))]), ('s', [k for _c, k in scarabs])):
            for j, src in enumerate(srcs):
                k = len(parts)
                if k >= 100:
                    raise RuntimeError('斗技场试炼：%s 的敌人超过 100 个' % m)
                nid = ARENA_NPC0 + 100 * x + k
                row = bytearray(N.rows[npc[src]])
                for f in ('itemLotId_enemy', 'itemLotId_map'):
                    if f in LN:
                        struct.pack_into('<' + LN[f][1], row, LN[f][2], -1)
                a = tier_of(src)
                sp = scale_sp(a, tgt, kind == 'b')
                if sp is not None:
                    if sp not in S_sp.rows:
                        raise RuntimeError('斗技场试炼：随机器没有缩放效果 %d（%d → %d）' % (sp, a, tgt))
                    slot = next((f for f in sp_slots if get(row, f) <= 0), None)
                    if slot is None:
                        raise RuntimeError('斗技场试炼：敌人参数 %d 没有空的特殊效果格' % npc[src])
                    struct.pack_into('<i', row, LN[slot][2], sp)
                N.add_row(nid, bytes(row))
                added += 1
                e = ents[src]
                name = e['npcname'] or (get(row, 'nameId') if 'nameId' in LN else 0)
                parts.append(dict(k=k, kind=kind, src=src, src_map=e['src_map'], part=e['part'], model=e['part'].split('_')[0],
                                  ent=F + PART_ENT + k, npc=nid, name=int(name or 0), tier=a, spot=(j // int(c['elite_copies'])) % ELITE_SPOTS if kind == 'e' else SCARAB_SPOTS[scarabs[j][0]] if kind == 's' else -1))
        colos.append(dict(x=x, map=m, tier=tgt, flag=F, parts=parts, warp=F + WARP_ENT))
    hp_msg = align_hp(ctx, colos, N, S_sp, npc)
    ctx.bnd.put('NpcParam.param', N.serialize())
    # 每 hp_every 波敌人血量 +hp_step（用户 2026-11-10「每两波 敌人血量提升10%」）：效果行，dark_core 出场时挂
    LS = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}
    put = lambda row, f, v: struct.pack_into('<' + LS[f][1], row, LS[f][2], v)
    for j in range(1, HPW_N + 1):
        rid = HPW_SP0 + j - 1
        if rid in S_sp.rows:
            raise RuntimeError('斗技场试炼：血量加成的效果编号 %d 已经有人用了' % rid)
        row = bytearray(S_sp.rows[HPW_TEMPLATE])
        o, bit = LS['disableCurse'][2], LS['disableCurse'][3]
        row[o] &= ~(1 << bit)
        put(row, 'iconId', -1)
        put(row, 'effectEndurance', -1.0)
        put(row, 'maxHpRate', 1.0 + float(c['hp_step']) * j)
        put(row, 'spCategory', 0)
        S_sp.add_row(rid, bytes(row))
    ctx.bnd.put('SpEffectParam.param', S_sp.serialize())
    band = lambda t: next((i for i, b in enumerate(ctx.S.get('tier_bands') or []) if t <= b.get('max_tier', 99)), len(ctx.S.get('tier_bands') or []) - 1)
    gen = gen_test(ctx, c, colos)
    ctx.arena = dict(cfg=c, colos=colos, band=[band(co['tier']) for co in colos], gen=gen)
    ctx.features['arena'] = dict(colos=[dict(x=co['x'], map=co['map'], flag=co['flag'], warp=co['warp'], gen=gen if gen and gen['x'] == co['x'] else None,
                                             parts=[{k: p[k] for k in ('k', 'kind', 'src_map', 'part', 'model', 'ent', 'npc', 'name', 'spot')} for p in co['parts']],
                                             statues=[dict(v=v, map=s[0], block=list(s[1]), ent=s[2], esd=s[3], src=list(s[4]), pos=list(s[5]), statue=list(s[6]),
                                                           resp=s[7], rsrc=list(s[8]))
                                                      for v, s in enumerate(STATUES[co['x']])])
                                        for co in colos],
                                 req=REQ, len0=LEN0, warp=WARP, shard=SHARD, cost=c['cost'], waves=c['waves'],
                                 spawn=SPAWN, dead=DEAD, ask=ASK, leave=LEAVE, run=RUN, banner=BANNER, note_bits=NOTE_BITS, note_n=NOTE_N, note_text0=NOTE_TEXT0,
                                 ready=READY, engage=ENGAGE, mydead=MYDEAD,
                                 notes=note_rows(c))
    ctx.report.append('斗技场试炼：' + '；'.join('%s（强度 %d）Boss %d 个、精英 %d 种 × %d、粪金龟 %d 只' % (
        COLO_ZH[co['x']], co['tier'], sum(p['kind'] == 'b' for p in co['parts']), len({p['src'] for p in co['parts'] if p['kind'] == 'e'}),
        int(c['elite_copies']), sum(p['kind'] == 's' for p in co['parts'])) for co in colos) +
        '（敌人参数副本 %d 行，%d 起；Boss 池 %d、精英池 %d、红 / 蓝粪金龟 %d / %d；精英位 %g%% 换成粪金龟）' % (
            added, ARENA_NPC0, len(boss_all), len(elite_all), len(scarab_all[0]), len(scarab_all[1]), float(c['scarab_pct'])))
    for co in colos:
        seen = set()
        ctx.report.append('  %s：%s' % (COLO_ZH[co['x']], '、'.join('%s%s(%d→%d)' % ({'b': 'B', 's': 'S'}.get(p['kind'], 'E'), p['part'], p['tier'], co['tier'])
                                                                   for p in co['parts'] if not ((p['kind'], p['src']) in seen or seen.add((p['kind'], p['src']))))))
    ctx.report.append('  血量：' + hp_msg)
    inline_packs(ctx, c)


def gen_test(ctx, c, colos):
    """生成器实验（GEN_*）：generator_test 写了竞技场名字（王城 / 盖利德 / 宁姆格福，或 0~2）才做；返回 sc/arena.py 和 arena.txt 要的"""
    v = str(c.get('generator_test') or '').strip()
    if not v:
        return None
    x = COLO_KEYS.get(v, int(v) if v.isdigit() else None)
    co = next((co for co in colos if co['x'] == x), None)
    if not co or not co['parts']:
        ctx.report.append('生成器实验：generator_test「%s」不对（写 王城 / 盖利德 / 宁姆格福），或者那个竞技场没有敌人，跳过' % v)
        return None
    F = co['flag']
    if F + GEN_ENT0 + max(p['k'] for p in co['parts']) >= F + GEN_REG0:
        raise RuntimeError('生成器实验：部件太多，生成器实体和出生点撞号')
    g = dict(x=x, regs=[F + GEN_REG0 + i for i in range(len(GEN_AT))], at=[list(a) for a in GEN_AT],
             req0=F + GEN_REQ0, gen0=F + GEN_ENT0, ev0=F + GEN_EV0,
             gens=[dict(k=p['k'], part='%s_%d' % (p['model'], 9500 + p['k']), ent=F + GEN_ENT0 + p['k']) for p in co['parts']],
             src_map=GEN_SRC_MAP, src_gen=GEN_SRC_GEN, region_map=GEN_REGION_MAP, src_region=GEN_SRC_REGION, **GEN_PARAMS)
    ctx.report.append('生成器实验：%s，%d 个敌人各配一个生成器（实体 %d 起，照抄 %s 的 %d），F9「斗技场试炼测试」里叫' % (
        COLO_ZH[x], len(g['gens']), g['gen0'], GEN_SRC_MAP, GEN_SRC_GEN))
    return g


def inline_packs(ctx, c):
    """wave_fx 规则里直接写的效果（fx）：交给通用敌人效果包做成行（rr/foefx.py 在斗技场之后跑），包名 arena_rule<第几条>"""
    more = {rule_pack(i): r['fx'] for i, r in enumerate(c.get('wave_fx') or []) if isinstance(r, dict) and isinstance(r.get('fx'), dict)}
    if more:
        ctx.foefx_more = dict(getattr(ctx, 'foefx_more', None) or {}, **more)


COLO_KEYS = {'王城': 0, '盖利德': 1, '宁姆格福': 2}
WHO_KEYS = {'boss': 'b', '精英': 'e', 'elite': 'e', '粪金龟': 's', 'scarab': 's'}
WAVES_RE = re.compile(r'^\d+(-\d+|\+)?$')


def rule_pack(i):
    """wave_fx 第 i 条（0 起）里直接写的 fx 做成的效果包名"""
    return 'arena_rule%d' % (i + 1)


def wave_fx_lines(ctx, c):
    """settings 的 arena.wave_fx → arena.txt 的 wfx 行：wfx 竞技场 场次的波数 哪种敌人 第几波 几率% 效果包（格式见 arena.rs；- = 不限）。
    一条规则：waves「3」「3-6」「5+」逗号分开（默认 1+）；colos 王城 / 盖利德 / 宁姆格福（或 0 / 1 / 2，默认全部）；
    runs 场次的总波数 2 / 4 / 8（默认全部）；who boss / elite / scarab（精英 / 粪金龟，all = 全部，默认 boss,elite）；
    chance 每个敌人挂上的几率 %（默认 100）；packs 效果包名（enemy_fx.packs）；fx 直接写一包（格式同 enemy_fx.packs 的一项）"""
    packs = getattr(ctx, 'foefx', None) or {}
    out, bad = [], []
    for i, r in enumerate(c.get('wave_fx') or []):
        try:
            if not isinstance(r, dict):
                raise ValueError('要写成 {waves / who / packs …}')
            if r.get('enabled', True) is False:
                continue
            ws = r.get('waves', '1+')
            toks = [str(t).strip() for t in (ws if isinstance(ws, list) else str(ws).split(','))]
            if not toks or not all(WAVES_RE.match(t) for t in toks):
                raise ValueError('waves 写成 3 / 3-6 / 5+，逗号分开')
            for t in toks:
                a, _, b = t.rstrip('+').partition('-')
                if int(a) < 1 or (b and int(b) < int(a)):
                    raise ValueError('waves 的「%s」不对（从 1 数起）' % t)
            cl = r.get('colos')
            cl = [cl] if isinstance(cl, (str, int)) and cl != 'all' else [] if cl in (None, 'all') else cl
            xs = sorted({COLO_KEYS.get(v, v) for v in cl})
            if any(isinstance(x, bool) or x not in (0, 1, 2) for x in xs):
                raise ValueError('colos 写王城 / 盖利德 / 宁姆格福')
            rn = r.get('runs')
            rn = [rn] if isinstance(rn, int) else rn or []
            if any(isinstance(x, bool) or not isinstance(x, int) or x < 1 for x in rn):
                raise ValueError('runs 写场次的总波数（2 / 4 / 8）')
            who = r.get('who', 'boss,elite')
            who = [w.strip() for w in (who.split(',') if isinstance(who, str) else who)]
            kinds = {'b', 'e', 's'} if any(w in ('all', '全部') for w in who) else {WHO_KEYS.get(w.lower() if w.isascii() else w) for w in who}
            if not kinds or None in kinds:
                raise ValueError('who 写 boss / elite / scarab / all')
            chance = float(r.get('chance', 100))
            if not 0.0 < chance <= 100.0:
                raise ValueError('chance 要在 0~100')
            names = r.get('packs') or []
            names = [names] if isinstance(names, str) else list(names)
            if isinstance(r.get('fx'), dict):
                names.append(rule_pack(i))
            if not names:
                raise ValueError('没写 packs 也没写 fx')
            miss = [n for n in names if n not in packs]
            if miss:
                raise ValueError('效果包 %s 没有（或者不对，见「敌人效果包」那行报告）' % '、'.join(map(str, miss)))
        except (TypeError, ValueError, AttributeError) as e:
            bad.append('第 %d 条（%s）' % (i + 1, e))
            continue
        out.append('wfx\t%s\t%s\t%s\t%s\t%g\t%s' % (','.join(map(str, xs)) or '-', ','.join(map(str, sorted(set(rn)))) or '-',
                                                    ','.join(sorted(kinds)), ','.join(toks), chance, ','.join(names)))
    if out or bad:
        ctx.report.append('斗技场试炼按波次挂的效果：%d 条规则%s' % (len(out), '；这些规则不对，跳过：' + '；'.join(bad) if bad else ''))
    return out


def align_hp(ctx, colos, N, S_sp, npc_of):
    """敌人血量照野外同一强度的规则（用户 2026-11-10「boss和小怪的血量加成也不对」：副本照抄原版参数，只有随机器的缩放，
    整合包按地区的加血一点没吃到，比野外同档的脆得多）：
    - 精英：+ 这一强度的小怪固定加血（rr/stage3.py curve_adds 每一级加的实际血量，随机模式下 stage3 记进 hpu_src 的 adds）；
    - Boss：同 stage3.boss_targets —— 目标 = 这一档原版 Boss 位置血量的中位数 × 自身肉度^own × 档倍数（enemy_hp_band.boss），
      肉度 = 原版实际血量 ÷ 它原来那一档的中位数（夹在 boss_blend 的 min~max），最后夹在 cap_min~cap_max；
    - 死亡 / 不可能：照 rr/hpunify.py 给这些敌人参数挂高难度血量 / 攻击倍率（hpunify.txt 的 n / an 行）。
    改的是副本参数的血量（实际血量 ÷ 身上的总倍率）。返回报告文字"""
    import statistics
    from .hpunify import NPC_HP, NPC_SPEFFECTS
    src = getattr(ctx, 'hpu_src', None)
    if not src:
        return '没有野外血量的统计，照原版参数'
    U, hp0 = src['U'], src['hp0']
    hb = ctx.S.get('enemy_hp_band') or {}
    bm = [float(x) for x in hb.get('boss') or [1.0]]
    blend = hb.get('boss_blend') or {}
    w = min(1.0, max(0.0, float(blend.get('own', 0.7))))
    lo, hi = float(blend.get('min', 0.25)), float(blend.get('max', 3.0))
    cap_lo, cap_hi = float(blend.get('cap_min', 0) or 0), float(blend.get('cap_max', 0) or 0)
    neutral_ent = {int(e) for e in blend.get('neutral_entities') or ()}

    def rate(sid):
        r = S_sp.rows.get(sid)
        return (struct.unpack_from('<f', r, 16)[0] or 1.0) if r is not None else 1.0

    def mult(row):
        m = 1.0
        for o in NPC_SPEFFECTS:
            sid = struct.unpack_from('<i', row, o)[0]
            if sid > 0:
                m *= rate(sid)
        return m

    van = lambda nid: hp0.get(nid, 0) * mult(N.rows[nid]) if nid in N.rows else 0.0
    rows = U.get('bosses') or []
    neutral = {nv for e, nv, _p, _b, _c in rows if e in neutral_ent}
    by_b, own_band = defaultdict(list), {}
    for e, nv, _p, b, _c in rows:
        if nv not in neutral:
            by_b[b].append(van(nv))
        own_band[nv] = min(own_band.get(nv, 99), b)
    med = {b: statistics.median(v) for b, v in by_b.items() if v}
    adds = U.get('adds') or {}
    calc = getattr(ctx, 'hpu_calc', None) if getattr(ctx, 'hpu_lines', None) else None
    extra, msg = [], []
    for co in colos:
        T = co['tier']
        b = ctx.band_idx(T)
        near = [t for t in adds if (t >= 21) == (T >= 21)] or list(adds)
        add = adds.get(T, adds[min(near, key=lambda t: (abs(t - T), t))] if near else 0.0)
        mm = bm[min(b, len(bm) - 1)]
        got = {'e': [], 'b': []}
        for p in co['parts']:
            if p['kind'] == 's':                   # 粪金龟：照原版血量（只有随机器的缩放），打死回露滴的奖励怪
                continue
            row = bytearray(N.rows[p['npc']])
            m = mult(row)
            cur = struct.unpack_from('<I', row, NPC_HP)[0] * m
            vn = npc_of[p['src']]
            t_own = 1.0
            if p['kind'] == 'e':
                tgt = cur + add
            else:
                ob = own_band.get(vn)
                if ob is None or ob not in med:
                    ob = ctx.band_idx(p['tier'])
                if vn not in neutral and ob in med and med[ob] > 0:
                    t_own = min(hi, max(lo, van(vn) / med[ob]))
                if b in med:
                    tgt = med[b] * t_own ** w * mm
                    base = med[b] * mm
                    if cap_lo > 0:
                        tgt = max(tgt, cap_lo * base)
                    if cap_hi > 0:
                        tgt = min(tgt, cap_hi * base)
                else:
                    tgt = cur * mm
            struct.pack_into('<I', row, NPC_HP, max(1, min(0x7FFFFFFF, int(round(tgt / max(m, 1e-6))))))
            N.rows[p['npc']] = bytes(row)
            got[p['kind']].append(tgt)
            if calc:                               # 死亡 / 不可能：同 hpunify 的小怪 / Boss 算法
                if p['kind'] == 'e':
                    k = calc['k_mob'](T)
                else:
                    g = calc['goal_b'].get(b >= calc['dlc_b'])
                    k = g * min(calc['hi'], max(calc['lo'], t_own)) / tgt if g and tgt > 0 else None
                sp = calc['sp_of'](k) if k else None
                if sp is not None:
                    extra.append('n %d %d' % (p['npc'], sp))
                if 'asp_of' in calc:
                    asp = calc['asp_of'](calc['k_atk'](T))
                    if asp is not None:
                        extra.append('an %d %d' % (p['npc'], asp))
        msg.append('%s 精英加 %d（中位 %d）、Boss 中位 %d（档 %d × %g）' % (
            COLO_ZH[co['x']], round(add), statistics.median(got['e']) if got['e'] else 0, statistics.median(got['b']) if got['b'] else 0, b, mm))
    if extra:
        ctx.hpu_lines.extend(extra)
        msg.append('高难度倍率 %d 行' % len(extra))
    return '；'.join(msg)


def note_rows(c):
    """竞技场里的提示：[(键, 中文, 英文)]，下标 + 1 = 编号（键是 dark_core arena.rs 里的写法）"""
    rows = []
    for m in c['waves']:
        for n in range(1, int(m) + 1):
            kind = ('魇化精英', 'Nightmare elites') if n % 2 else ('Boss', 'Boss')
            rows.append(('wave %d %d' % (m, n), '斗技场试炼　第 %d / %d 波：%s' % (n, m, kind[0]), 'Colosseum Trial  wave %d / %d: %s' % (n, m, kind[1])))
    rows.append(('clear', '斗技场试炼完成！', 'Colosseum Trial complete!'))
    rows.append(('cleared', '本波已肃清，奖励已放进背包（途中死亡会收回）', 'Wave cleared. Rewards added to your inventory (taken back if you die)'))
    if len(rows) >= 1 << NOTE_N:
        raise RuntimeError('斗技场试炼：提示 %d 条，%d 位放不下' % (len(rows), NOTE_N))
    return rows


def def_lines(ctx):
    """dll\\dark_core\\arena.txt（格式见 dark_core 的 arena.rs）"""
    a = getattr(ctx, 'arena', None)
    if not a:
        return []
    c = a['cfg']
    from . import difficulty as dif
    from .unidentified import GOODS0
    _, ts = dif.tiers(ctx.S)
    cat = ctx.S.get('gear_category_share') or {'weapon': 30, 'armor': 60, 'talisman': 10}
    out = ['req\t%d\t%d\t%d\t%d' % (REQ, LEN0, LEN0 + 1, WARP), 'shard\t%d' % SHARD, 'goods0\t%d' % GOODS0,
           'local\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d' % (SPAWN, DEAD, ASK, LEAVE, NOTE_BITS, NOTE_N, RUN, BANNER, READY, ENGAGE, MYDEAD),
           'per\t%d' % int(c['elite_per_wave']), 'scarab\t%g' % max(0.0, min(100.0, float(c['scarab_pct']))), 'items\t%d\t%d\t%d' % (int(c['items_elite']), int(c['items_boss']), int(c['ash_boss'])),
           'cat\t%d\t%d\t%d' % (int(cat.get('weapon', 30)), int(cat.get('armor', 60)), int(cat.get('talisman', 10)))]
    if ctx.features.get('difficulty') and ts:
        from .hpunify import CUR0
        out.append('diff\t%d\t%d\t%d' % (CUR0, len(ts), dif.normal_index(ts)))
    for d, mm in enumerate(c['difficulty_mult']):
        out.append('dmult\t%d\t%s' % (d, '\t'.join('%g' % v for v in mm)))
    for d, v in enumerate(c['elite_two']):
        out.append('two\t%d\t%g' % (d, v))
    if float(c['hp_step']) > 0:
        out.append('hpwave\t%d\t%d\t%d' % (max(1, int(c['hp_every'])), HPW_SP0, HPW_N))
    out += wave_fx_lines(ctx, c)
    g = a.get('gen')
    if g:
        # gentest <竞技场> <部件 k 的请求标记起点（+ k，竞技场的事件听，叫部件 k 的生成器）> <部件 k 的生成器实体起点（+ k）>
        out.append('gentest\t%d\t%d\t%d' % (g['x'], g['req0'], g['gen0']))
    for i, (w, cost) in enumerate(zip(c['waves'], c['cost'])):
        # run <场次> <波数> <碎片> <全部打完多给几件> <全部打完退还几个碎片>
        back = int(c['refund'][i]) if i < len(c.get('refund') or []) else 0
        out.append('run\t%d\t%d\t%d\t%d\t%d' % (i + 1, int(w), int(cost), int(c['clear_bonus'][i]) if i < len(c['clear_bonus']) else 0,
                                                 max(0, min(back, int(cost)))))
    for co in a['colos']:
        x = co['x']
        out.append('colo\t%d\t%d\t%d' % (x, co['flag'], co['warp']))
        for v, s in enumerate(STATUES[x]):
            out.append('statue\t%d\t%d\t%s' % (x, v, '\t'.join(map(str, s[1]))))
        et, bt = c['reward_tiers'][x]
        out.append('rew\t%d\t%d\t%d\t%d' % (x, int(et), int(bt), int(c['reward_scale'][x])))
        out.append('ashrar\t%d\t%s' % (x, '\t'.join(str(int(v)) for v in c['ash_weights'][x])))
        for p in co['parts']:
            out.append('part\t%d\t%d\t%s\t%d\t%d\t%d\t%s' % (x, p['k'], p['kind'], p['ent'], p['npc'], p['spot'], p['part']))
    out += ['note\t%s\t%d' % (k, v + 1) for v, (k, _z, _e) in enumerate(note_rows(c))]
    return out
