# -*- coding: utf-8 -*-
"""词条库要用的参数行：插进这次的 regulation。

词条库在 data\\affixes\\（dev\\item_system\\extract_affixes.py 从 RNG Lands 原包提取，不要手改）：
  affixes.json  词条定义和生成用的分布，鉴定时 DLL 照它抽
  rows.json     原版里没有、词条要用的整行参数：RNG Lands 加的效果（SpEffectParam）连同它们引用的行为 / 子弹 / 攻击，
                合并出来的新效果（魔法 / 祷告伤害、盾牌抗性、咒死 / 发狂的新强度）、传说光效、护符模板（EquipParamAccessory 9000 起）
编号已经有了、内容又不一样（比如随机器自己加了同编号的行）就报错，不悄悄覆盖。"""
from .common import *  # noqa: F401,F403

ROWS = os.path.join('affixes', 'rows.json')


def build(ctx):
    data = json.load(open(os.path.join(ctx.data_dir, ROWS), encoding='utf-8'))
    sizes = data.pop('_row_size')
    added, same = Counter(), Counter()
    for p, rows in sorted(data.items()):
        P = erlib.Param(ctx.bnd.get(p + '.param'))
        if P.row_size != sizes[p]:
            raise RuntimeError('%s 行大小 %d 和词条库的 %d 不一样（游戏版本不对？）' % (p, P.row_size, sizes[p]))
        clash = []
        for k, hx in rows.items():
            i, b = int(k), bytes.fromhex(hx)
            if i in P.rows:
                if bytes(P.rows[i]) == b:
                    same[p] += 1
                else:
                    clash.append(i)
                continue
            P.add_row(i, b)
            added[p] += 1
        if clash:
            raise RuntimeError('%s 里词条库要用的 %d 个编号已经被别的内容占了：%s' % (p, len(clash), clash[:10]))
        ctx.bnd.put(p + '.param', P.serialize())
    ctx.report.append('词条库：插入 %s%s' % ('、'.join('%s %d 行' % kv for kv in sorted(added.items())),
                                         '（已经有一样的 %s）' % dict(same) if same else ''))
    hooks(ctx)
    attr_copies(ctx)
    val_pool(ctx)
    skill_mults(ctx)
    cast_bases(ctx)
    from . import procs
    procs.build(ctx)                      # 触发词条的属性补正：原版共用的伤害行复制成词条专用（说明文字要它的结果）
    template_texts(ctx)
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    ranged_hits(ctx, (lib.get('runtime') or {}).get('marks') or {})
    boss_npcs(ctx)
    skill_vars(ctx, lib)
    hks, _dll = runtime_parts(lib)
    # 疾风叠加：各稀有度标记的副本（每档 ATTR_COPIES 个，按稀有度排成一列；没建副本的这一档写 0，玩家脚本数到 0 就停）
    if 'gale' in hks:
        cp = {r_i: c for k, r_i, _sp, c in getattr(ctx, 'attr_dup', []) if k == 'dr_gale'}
        if cp:
            hks['gale_cp'] = [x for r_i in range(len(RAR)) for x in (list(cp.get(r_i, [])) + [0] * ATTR_COPIES)[:ATTR_COPIES]]
            hks['gale_n'] = [ATTR_COPIES]
    if hks:
        ctx.features['affix_hks'] = hks


# 远程与道具（bd设计.md 3.11）：箭 / 弩箭（武器类型 81 / 83 / 85 / 86）和投掷道具（道具的使用动作：2 / 3 / 17 / 20 / 42 投掷壶、附绳壶、
# 大投掷壶、飞刀、投矛，57 / 58 / 59 崩裂辉石、重力石）的子弹，在命中时挂给被打一方的效果位（spEffectId0~4 里第一个空的）挂标记，
# dark_core 扫敌人时看谁身上刚出现这个标记，就分得清是箭（shot_hit）还是道具（item_hit）打中的、打中的是谁，和飞行时间无关。
# 以前用的 spEffectIDForShooter 是「发射时」挂给射手的（2026-10-28 游戏里量到比命中早 0.35~0.56 秒 = 飞行时间），射空也算、射远了对不上，改掉了。
# 五个位都占满的子弹不动（报告里数）。
# 箭的行为编号 = 100000000 + 箭的行为变体 × 1000 + 判定（行为再指向子弹）；道具的 refId_default（refCategory 1）直接是子弹编号。子弹命中再生成的子弹（HitBulletID /
# intervalCreateBulletId）一起加（投掷壶多半是落地炸开那一颗打中人）。返还（回收、无尽箭袋）要数的弹药写进 runtime.txt 的 ammo 行
AMMO_TYPES = (81, 83, 85, 86)
THROW_ANIMS = (2, 3, 13, 17, 20, 42, 57, 58, 59, 67)   # 13 龙飨鱼叉、67 大投掷壶（2026-11-05 补，以前打中算成近战）


def skill_vars(ctx, lib):
    """专属战技的「只有战技判定」变体（用户 2026-10-31：碎星大剑配了遗迹大剑的战技，轻击没伤害）。
    dark_core 把专属战技配到同一大类的别的本体上时，行为变体改成战技原武器的（战技判定在 BehaviorParam_PC 3VVVJJJ）；
    原武器自己有覆盖这一大类通用判定（1GGGJJJ，GGG = 变体 // 100 × 100）的普攻判定（1VVVJJJ）的，本体的轻重击也跟着用上原武器的，
    判定点在原武器模型上（遗迹大剑是 100~120 号点），模型对不上就打不中。所以给这种战技在同一大类里找个空号（从 99 往下）建新变体：
    整套复制这一大类的通用判定（1GGG / 3GGG），再叠战技判定（3VVVJJJ）和原武器独有的普攻判定（通用里没有的判定号：有的专属战技的
    判定放在 1VVV 里，比如月光剑），覆盖通用的那些不要，本体的轻重击照通用判定（和原版碎星大剑这种自己没有普攻判定的一样）。
    写进 affixes.txt 的 skillvar 行，DLL 生成和读档重建时用它。
    判定已经换到共享层的专属战技（rr/skillgems.py 的 free_skills，用户 2026-11-03）不用换变体，也不建这种变体"""
    ctx.skill_vars = {}
    B = erlib.Param(ctx.bnd.get('BehaviorParam_PC.param'))
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    _n, fc, off, *_ = next(t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamWeapon.xml')))[0] if t[0] == 'behaviorVariationId')
    by = defaultdict(lambda: defaultdict(list))         # 变体 → 前缀（1 普攻 / 3 战技 …）→ 行号（行号 = 前缀亿位 + 变体 × 1000 + 判定）
    for i in B.rows:
        by[(i % 100000000) // 1000][i // 100000000].append(i)
    used = set(by) | {struct.unpack_from('<' + fc, row, off)[0] for row in W.rows.values()}
    full, n_rows = [], 0
    for s, x in sorted(lib['weapon']['skill_info'].items(), key=lambda kv: int(kv[0])):
        v = x.get('native_var')
        if x.get('gem') or v is None or v < 0 or int(s) in getattr(ctx, 'free_skills', ()):
            continue
        g = v // 100 * 100
        generic = {i % 1000 for i in by[g].get(1, [])}
        if v == g or not {i % 1000 for i in by[v].get(1, [])} & generic:
            continue                                     # 原武器没有覆盖通用的普攻判定：直接用原武器的变体没问题
        new = next((c for c in range(g + 99, g, -1) if c not in used), None)
        if new is None:
            full.append(int(s))
            continue
        used.add(new)
        # 新变体自成一套，不靠退回（用户 2026-10-31 实测：碎星大剑配遗迹大剑战技，单持轻击正常、双持没伤害；原版碎星大剑 405 自己一行
        # 普攻判定都没有，双持却正常——双持找判定时不像单持那样从新变体退回 400）：先整套复制这一大类的通用判定（1GGG / 3GGG），
        # 再叠原武器独有的普攻判定和它的战技判定
        src = {}
        for p in (1, 3):
            for i in by[g].get(p, []):
                src[(p, i % 1000)] = i
        for i in by[v].get(1, []):
            if i % 1000 not in generic:
                src[(1, i % 1000)] = i
        for i in by[v].get(3, []):
            src[(3, i % 1000)] = i
        for (p, j), i in sorted(src.items()):
            row = bytearray(B.rows[i])
            struct.pack_into('<i', row, 0, new)      # variationId
            B.add_row(p * 100000000 + new * 1000 + j, bytes(row))
            n_rows += 1
        ctx.skill_vars[int(s)] = (v, new)
    ctx.bnd.put('BehaviorParam_PC.param', B.serialize())
    ctx.report.append('专属战技的新行为变体（通用判定整套 + 战技判定，不带覆盖通用的普攻判定）：%d 个、复制 %d 行（原武器有覆盖通用的普攻判定的战技，配到别的本体上时普攻用这一大类的通用判定）%s' % (
        len(ctx.skill_vars), n_rows, '；大类里没空号、照旧用原武器变体的：%s' % full if full else ''))


def boss_npcs(ctx):
    """千钧要分 Boss（满蓄力只扣强韧度上限的一部分）：NpcParam 的 isSoulGetByBoss（卢恩按 Boss 方式给）是 1 的；写进 runtime.txt 的 boss 行"""
    L = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'NpcParam.xml')))[0]}
    _n, _fc, off, bp, bits, _d = L['isSoulGetByBoss']
    P = erlib.Param(ctx.bnd.get('NpcParam.param'))
    ctx.boss_npcs = sorted(i for i, row in P.rows.items() if (row[off] >> bp) & ((1 << max(bits, 1)) - 1))
    ctx.report.append('千钧认的 Boss：NpcParam 里 isSoulGetByBoss 的 %d 行' % len(ctx.boss_npcs))


def ranged_hits(ctx, marks):
    ctx.ammo = []
    shot, item, cast = marks.get('shot_hit'), marks.get('item_hit'), marks.get('cast_hit')
    if not (shot or item or cast):
        return
    lay = lambda n: {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, n + '.xml')))[0]}
    get = lambda L, row, f: struct.unpack_from('<' + L[f][1], row, L[f][2])[0]
    LW, LG, LB, LU = lay('EquipParamWeapon'), lay('EquipParamGoods'), lay('BehaviorParam'), lay('BulletParam')
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    G = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    B = erlib.Param(ctx.bnd.get('BehaviorParam_PC.param'))
    U = erlib.Param(ctx.bnd.get('Bullet.param'))
    by_var = defaultdict(list)
    for i, row in B.rows.items():
        if get(LB, row, 'refType') == 1:
            by_var[i // 1000].append(get(LB, row, 'refId'))
    arrows = sorted(i for i, row in W.rows.items() if get(LW, row, 'wepType') in AMMO_TYPES and i % 100 == 0)
    goods = sorted(i for i, row in G.rows.items() if get(LG, row, 'refCategory') == 1 and get(LG, row, 'goodsUseAnim') in THROW_ANIMS
                   and get(LG, row, 'refId_default') > 0)
    roots = {'shot': set(), 'item': set(), 'cast': set()}
    for i in arrows:                                    # 行为变体 0 的是没名字的占位箭（47000000 等），不然会把 1000000xx 的通用行为拉进来
        var = get(LW, W.rows[i], 'behaviorVariationId')
        if var > 0:
            roots['shot'].update(by_var.get(100000 + var, []))
    for i in goods:                                     # 道具的 refCategory 1：refId_default 直接就是子弹编号
        roots['item'].add(get(LG, G.rows[i], 'refId_default'))
    # 法术（refCategory 1 的 refId 是子弹编号）、调香等别的道具放的子弹：cast_hit，不算近战（用户 2026-11-05「查一下远程或者法术的判定」）
    LM = lay('MagicParam')
    for row in erlib.Param(ctx.bnd.get('Magic.param')).rows.values():
        roots['cast'].update(get(LM, row, 'refId%d' % k) for k in range(1, 11) if get(LM, row, 'refCategory%d' % k) == 1 and get(LM, row, 'refId%d' % k) > 0)
    roots['cast'].update(get(LG, row, 'refId_default') for row in G.rows.values() if get(LG, row, 'refCategory') == 1
                         and get(LG, row, 'goodsUseAnim') not in THROW_ANIMS and get(LG, row, 'refId_default') > 0)
    slots = ['spEffectId%d' % k for k in range(5)]
    n = Counter()
    marked = set()
    for kind, sp in (('shot', shot), ('item', item), ('cast', cast)):
        if not sp:
            continue
        todo, seen = [b for b in roots[kind] if b in U.rows], set()
        while todo:
            b = todo.pop()
            if b in seen or b not in U.rows:
                continue
            seen.add(b)
            row = U.rows[b]
            todo += [c for c in (get(LU, row, 'HitBulletID'), get(LU, row, 'intervalCreateBulletId')) if c > 0]
            if kind == 'cast' and b in marked:     # 和箭 / 投掷道具共用的子弹：照那边算
                continue
            marked.add(b)
            free = next((s for s in slots if get(LU, row, s) in (-1, 0)), None)
            if free:
                struct.pack_into('<' + LU[free][1], row, LU[free][2], sp)
                n[kind] += 1
            else:
                n[kind + '_full'] += 1
    ctx.bnd.put('Bullet.param', U.serialize())
    ctx.ammo = [('w', i) for i in arrows] + [('g', i) for i in goods]
    ctx.report.append('法术、调香等的命中标记：子弹 %d 颗挂 cast_hit（%d 颗五个效果位满了，没动，这些打中时算近战）' % (n['cast'], n['cast_full']))
    ctx.report.append('远程命中标记（命中时挂给被打的一方）：箭 / 弩箭 %d 种的子弹 %d 颗挂 shot_hit（%d 颗五个效果位都满了，没动），'
                      '投掷道具 %d 种的子弹 %d 颗挂 item_hit（%d 颗没动）' % (len(arrows), n['shot'], n['shot_full'], len(goods), n['item'], n['item_full']))


# 新词条（extract_affixes.py 的 CUSTOM，词条库里带 runtime）谁来做：玩家脚本（sc/hks.py，features.json 的 affix_hks）或 dll\dark_core（runtime.txt）
HKS_RUNS = ('gale', 'wolf', 'leap', 'overlord')
DLL_RUNS = {'elegance': (1.0, 20.0),               # 优雅：姿势做满几秒记一层、一层持续几秒（用户 2026-10-27 定）
            'cocktail': (10.0,),                   # 鸡尾酒：间隔秒
            'timeslip': (8.0,),                    # 时隙：半径（米，照授血仪式的范围）；「效果编号」那列写加速百分比
            'deft': (1.0,),                        # 巧手：「效果编号」那列写加速百分比（秒数那列不用）
            'crush': (1.0,),                       # 碾压：「效果编号」那列写右手武器攻击力的百分比（秒数那列不用）
            'magnet': (1.0,),                      # 拾遗：「效果编号」那列写吸取半径（米；秒数那列不用）
            'quickcharge': (1.0,),                 # 寸劲（原沉稳，2026-11-05 改）：「效果编号」那列写蓄力时间减少的百分比
            'loadspeed': (1.0,)}                   # 致命舞（2026-11-06 改）：「效果编号」那列写空载时动作加快的百分比
# chaos 混沌：积木规则（on land + target_fx，2026-11-06 起，见 extract_affixes.py CUSTOM）；run 这里什么都不用做
# 事件总线（sc/hks.py DR_Event）：旧词条（run）听的事件；血狂（武器特效的标记）听 light_new / hit；积木词条按规则里用到的事件
LEGACY_LISTEN = {'roll': ('crush',), 'reload': ('deft',), 'charging': ('quickcharge',), 'sync': ('loadspeed',)}
# 法球（迸发 / 星群）从拿法器那只手的武器点位直接射出（用户 2026-11-05「改成从原版法杖的发射点位发射 看着好些」；dark_core orbshot.rs）：
# (右手武器的点位, 左手的)，dark_core 加上 10000 / 20000；None = 照旧挂效果（子弹从身体中间出来）。
# 用户 2026-11-05 开发工具「法球发射点测试」试过「100号点合适」（左右手都是武器的 100 号点 = 法杖 / 圣印记的发射点）
ORB_SHOT = (100, 100)


def rule_events(rule):
    """积木规则用到的事件（条件 / 排除条件 / 触发 / 加层 / 清零 / 消耗）；rally 还要受击事件 hit（掉血要和它对上才算受伤），
    quiet（泡盾）要受击事件 hit（重新计时），见切 mikiri 是 dark_core 在翻滚 / 后撤步中判断的，要翻滚、后撤步事件 roll / backstep"""
    evs = [e for k in ('cond', 'unless', 'event', 'prog_from') if k in rule for e in (rule[k] if isinstance(rule[k], list) else [rule[k]])] + \
        [e for k in ('add', 'clear', 'consume') for e in rule.get(k, [])]
    # 在地上 / 在空中（ground / air）：玩家脚本在空中时每帧发 air，用到其中一个的词条都要听 air（dark_core 没收到 air 就算在地上）
    # 无尽箭袋 free：射击 / 投掷的状态 shot / throw 和新的一次 shot_new / throw_new（玩家脚本 DR_StateFrame / AFFIX_NEW_WRAP 发）
    return evs + (['hit'] if rule['type'] in ('rally', 'quiet') else []) + (['roll', 'backstep'] if 'mikiri' in evs else []) + \
        (['shot', 'shot_new', 'throw', 'throw_new'] if rule['type'] == 'free' else []) + \
        (['air'] if {'ground', 'air'} & set(evs) else []) + \
        (['sync'] if 'haste' in rule or 'act_speed' in rule or 'layer_speed' in rule else [])   # 改动作速度的（处刑、转念）：处决、被抓时不变速


def rule_line(key, rule):
    """runtime.txt 的 rule 行：rule <词条键> <类型> <参数=值>…；按稀有度的值逗号分隔，叠层每层的效果是 fx0~fx3（各稀有度）"""
    num = lambda x: '%g' % x if isinstance(x, float) else str(x)
    cols = ['rule', key, rule['type']]
    for k, v in rule.items():
        if k == 'type':
            continue
        if k in ('fx', 'mfx', 'tfx'):               # 叠层每层一行（fx0~fx3）/ 目标身上的标记每层一行（mfx0~mfx3）/ 消耗标记时按层数挑的特效（tfx0~tfx3）
            cols += ['%s%d=%s' % (k, i, ','.join(map(str, x))) for i, x in enumerate(v)]
        elif isinstance(v, list):
            cols.append('%s=%s' % (k, ','.join(map(num, v))))
        else:
            cols.append('%s=%s' % (k, num(v)))
    return '\t'.join(cols)


def runtime_parts(lib):
    """(玩家脚本用的 {名字: [普通 ~ 传说]}, runtime.txt 的行)"""
    hks, dll = {}, []
    listen = defaultdict(set)                       # 事件 → 在听的词条的标记
    for key, f in lib['gear'].items():
        rt = f.get('runtime')
        if not rt:
            continue
        if 'rules' in rt:                           # 积木规则：aff <键> <标记 普通 ~ 传说（不出的稀有度 -1）>，再一条条 rule
            markers = [f['sp'].get(r, -1) for r in RAR]
            dll.append('aff\t%s\t%s' % (key, ','.join(map(str, markers))))
            hks.setdefault(key, markers)            # 玩家脚本 DR_Has(键)
            for rule in rt['rules']:
                dll.append(rule_line(key, rule))
                for ev in rule_events(rule):
                    listen[ev].update(m for m in markers if m > 0)
            if rt.get('iframes'):                   # 身上有就无敌的效果（dark_core 的 pre_physics 设无敌位）
                dll.append('iframe\t%s' % ','.join(map(str, rt['iframes'])))
            hks.update(rt.get('hks') or {})         # 导出给玩家脚本的效果（DR_AnyOn）
        if 'run' not in rt:                         # 纯积木词条；老词条（run）也可以带积木规则（霸王的图标、光效），接着走下面
            continue
        run, markers = rt['run'], [f['sp'][r] for r in RAR]
        for ev, runs in LEGACY_LISTEN.items():
            if run in runs:
                listen[ev].update(markers)
        if run in HKS_RUNS:
            hks[run] = markers
            if run in ('gale', 'wolf'):
                hks[run + '_v'] = rt['vals']
            else:
                hks[run + '_sp'] = [rt['sp'][r][0] for r in RAR]
            # DLL 看戴没戴（狼魂写日志）、飞鸿的计时标记：hks <名字> <标记, 普通 ~ 传说> <数值> [<脚本挂的效果, 普通 ~ 传说>]
            cols = ['hks', run, ','.join(map(str, markers)), ','.join('%g' % v for v in rt['vals'])]
            if run + '_sp' in hks:
                cols.append(','.join(map(str, hks[run + '_sp'])))
            dll.append('\t'.join(cols))
        elif run in DLL_RUNS:
            dll += ['%s\t%d\t%d\t%s\t%s' % (run, k, markers[k], ','.join(map(str, rt['sp'][r] or [rt['vals'][k]])),
                                            '\t'.join('%g' % x for x in DLL_RUNS[run]))
                    for k, r in enumerate(RAR)]
            if run in ('deft', 'crush'):               # 玩家脚本只在戴着这个词条时挂脉冲标记
                hks[run] = markers
    # 新词条共用（extract_affixes.py custom_shared）：脉冲标记、碾压冲击波各档、血狂、积木武器特效的规则
    sh = lib.get('runtime') or {}
    for key, x in (sh.get('special_rules') or {}).items():
        dll.append('weapon\t%s' % key)              # 武器上的特效：只在带这个标记的武器出招时生效
        dll.append('aff\t%s\t%s' % (key, ','.join(map(str, x['markers']))))
        hks.setdefault(key, x['markers'])
        for rule in x['rules']:
            dll.append(rule_line(key, rule))
            for ev in rule_events(rule):
                listen[ev].update(x['markers'][:1])
        # 左右手攻击提示：HKS 的 DR_ClashFrame 会在普通攻击 / 跳跃攻击中发这些事件；
        # 即使没有相杀词条，只要武器特效在听，DR_Event 也会把它们挂出来。
        for ev in ('clash_l_l', 'clash_l_r', 'clash_h_l', 'clash_h_r', 'clash_hc_l', 'clash_hc_r'):
            listen[ev].update(x['markers'][:1])
    b = sh.get('bloodrage')
    if b:
        hks['bloodrage'] = [b['marker']] * 4
        dll.append('bloodrage\t%d\t%s\t%g\t%g' % (b['marker'], ','.join(map(str, b['stacks'])), b['hp'], b['reset']))
        for ev in ('light_new', 'hit', 'clash_l_l', 'clash_l_r', 'clash_h_l', 'clash_h_r', 'clash_hc_l', 'clash_hc_r'):
            listen[ev].add(b['marker'])
    # 七咒（rr/curses.py）：诅咒监听标记挂在玩家身上时也发这些事件（没开七咒时这个标记不会出现，多一个判断而已）
    from .curses import CURSE_EVENTS, LISTEN as CURSE_LISTEN
    for ev in CURSE_EVENTS:
        if ev in (sh.get('marks') or {}):
            listen[ev].add(CURSE_LISTEN)
    for name, sp in sorted((sh.get('marks') or {}).items()):
        hks[name + '_mark'] = [sp]
        dll.append('mark\t%s\t%d' % (name, sp))
        if listen.get(name):                        # 事件总线：ev_<事件> = {脉冲标记, 在听的词条标记…}
            hks['ev_' + name] = [sp] + sorted(listen[name])
    missing = sorted(set(listen) - set(sh.get('marks') or {}))
    if missing:
        raise RuntimeError('词条用到的事件没有脉冲标记：%s（extract_affixes.py custom_shared 的 marks）' % missing)
    dll += ['crushtier\t%d\t%d' % (dmg, sp) for dmg, sp in sh.get('crush') or []]
    dll += ['crushlive\t%d\t%d' % (sp, atk) for sp, atk in sh.get('crush_live') or []]   # 碾压的实时伤害（dark_core 放之前写攻击行）
    dll += ['shocklive\t%d\t%d' % (sp, atk) for sp, atk in sh.get('shock_live') or []]   # 反震 / 坠星的实时伤害（积木引擎）
    # 碾压的削韧 = 右手武器的重击削韧（用户 2026-11-12）：武器动作类别 + 行为变体 → 重击的削韧倍率％（data\\heavy_poise.txt，
    # dev\\item_system\\build_heavy_poise.py 生成；变体 -1 = 这个类别的默认）
    hpath = os.path.join(HERE, 'data', 'heavy_poise.txt')
    if (sh.get('crush_live') or sh.get('shock_live')) and os.path.isfile(hpath):
        dll += ['heavypoise\t%s\t%s\t%s' % tuple(l.split()[:3]) for l in open(hpath, encoding='utf-8') if l.strip() and not l.startswith('#')]
    # 法球那套带子弹编号（第 5 项）：dark_core 可以不挂效果、直接从法器点位射出（ORB_SHOT 打开，见 dark_core 的 orbshot.rs）
    dll += ['bursttier\t%s\t%d\t%d%s' % (k, t[0], t[1], '\t%d' % t[2] if len(t) > 2 else '')
            for k, tiers in sorted((sh.get('bursts') or {}).items()) for t in tiers]
    if sh.get('hp_pool'):                       # 精确扣血的专用行（dark_core 的 rules.rs foe_hp_exact）
        dll.append('hppool\t%s' % ','.join(map(str, sh['hp_pool'])))
    if ORB_SHOT:
        dll.append('orbshot\t%d\t%d' % ORB_SHOT)
    dll += ['buildup\t%s\t%d\t%d' % (k, n, sp) for k, lst in sorted((sh.get('buildups') or {}).items()) for n, sp in lst]   # 异常累积（目标层）
    return hks, dll


HOOK_XML = {'SpEffectParam': 'SpEffect.xml'}


# 原版类型数值词条同稀有度叠加（用户 2026-11-01 属性加点；2026-11-03 扩到「原版类型数值词条都能任意稀有度叠加」，「触发型的先不处理」）：
# 每个效果的副本份数（防具 4 件 + 护符 5 格 = 最多 9 件同一个效果，第一件装备自己给）、副本编号从这里起
ATTR_COPIES = 8
# 2026-11-15 从 7300000 挪过来：7300000 往后 2000 个号就到了别的行（7302000 起），关掉词条数值随机时副本 1300 多个、再加疾风就挤了；
# 74~77 整段空着（随机器在 78）
ATTR_COPY_BASE = 7400000
# 词条数值随机的占位行（dark_core gear/valfx.rs：身上每件装备的每条随机词条一组 VAL_BLOCK 行，运行时整行照这一档的效果链抄过来、写进精确数值再挂）：
# 防具 4 件 × 3 条 + 护符 4 格 + 第五护符槽 = 17 条，留到 24 组
VAL_POOL_BASE, VAL_POOL_N, VAL_BLOCK = 7490000, 96, 4
# 不放开的：附近触发、命中时触发（机制类，各有自己的叠加规则）、新词条（dark_core / 玩家脚本做，只认最高稀有度）；
# 触发型（效果行会再挂别的效果：蛋白石盾、悲伤、远征、黄金蹲姿、臭气嘲讽）和狂怒突刺（致命一击后才生效，说明写着同稀有度仅生效一次）先不处理
STACK_SKIP_GROUPS = ('附近触发', '命中时触发', '新词条')
# 新词条里也放开叠加的（用户 2026-11-15「疾风改为四个部位都可出现并且可以叠加」）：标记效果照样建副本，dark_core attrstack 按件数挂，
# 玩家脚本（sc/hks.py DR_MoveMult）数每个稀有度的标记和副本挂了几份、数值相加（features.json 的 affix_hks：gale_cp / gale_n）
STACK_NEW_KEYS = ('dr_gale',)
STACK_SKIP_KEYS = ('increase_attack_by_pct_for_seconds_after_critica', 'increase_damage_with_lower_equip_load_damage_inc')
# 会再挂别的效果、但也放开叠加的（用户 2026-11-05「翔空箭词条改为可以叠加」）：加伤在效果行本身，射程在 cycleOccurrenceSpEffectId 周期挂的那行，
# 那行也跟着每份副本复制一份（编号一样的话射程还是只算一次）。说明里的不叠加在 extract_affixes.py 的 STACK_FREE 去掉
STACK_CHAIN_KEYS = ('increase_range_of_bows_by_pct_and_raise_attack_p',)
SP_REF_FIELDS = ('replaceSpEffectId', 'cycleOccurrenceSpEffectId', 'atkOccurrenceSpEffectId', 'accumuOverFireId', 'accumuUnderFireId',
                 'applyIdOnGetSoul', 'spiritDeathSpEffectId')


def value_random(ctx):
    """词条数值随机（用户 2026-11-15；extract_affixes.py value_ranges 算好的取值定义，词条库 vrand）：
    settings 的 affix_value_random = false 不写取值定义、不建占位行（dark_core 照旧每档固定数值，随机的词条照旧建叠加副本）"""
    return bool(ctx.S.get('affix_value_random', True))


def val_pool(ctx):
    """词条数值随机的占位行：VAL_POOL_BASE 起 VAL_POOL_N 行，先照第一条随机词条的效果行抄（dark_core 用之前整行重写，不会原样挂）"""
    ctx.val_pool = []
    if not value_random(ctx):
        return
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    src = next((x['rows'][0] for f in lib['gear'].values() for x in (f.get('vrand') or {}).get('r', {}).values()), None)
    if src is None:
        return
    P = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    if src not in P.rows:
        raise RuntimeError('词条数值随机：占位行要抄的效果 %d 不在 regulation 里' % src)
    for i in range(VAL_POOL_BASE, VAL_POOL_BASE + VAL_POOL_N):
        if i in P.rows:
            raise RuntimeError('词条数值随机的占位行 %d 已经有人用了' % i)
        P.add_row(i, bytes(P.rows[src]), b'')
        ctx.val_pool.append(i)
    ctx.bnd.put('SpEffectParam.param', P.serialize())
    ctx.report.append('词条数值随机：占位行 %d~%d（%d 行，每条词条 %d 行）' % (VAL_POOL_BASE, VAL_POOL_BASE + VAL_POOL_N - 1, VAL_POOL_N, VAL_BLOCK))


def val_lines(ctx, k, f, key):
    """一条随机词条的取值定义（dark_core gear.rs 读）：
    famnum <序号> <数的位置> <显示精度> <1 = 主数> <各档的数 普通,稀有,史诗,传说（没有的档 ->）>；
    famval <序号> <r> <下限> <上限> <μ> <σ>（主数的范围、截断正态）；famtpl / famspan <序号> <r> <中文> <英文>（说明模板 {位置}、词条百科的范围）；
    famrow <序号> <r> <效果链的行，第 0 个是链头>（一期才有）；famref <序号> <r> <行> <字段偏移> <指向第几行>；famfld <序号> <r> <行> <字段偏移> <类型> <a> <b> <数的位置>（字段 = a + b × 数）"""
    v = f.get('vrand')
    if not v or not value_random(ctx):
        return []
    out = []
    for j, x in sorted(v['nums'].items(), key=lambda kv: int(kv[0])):
        out.append('famnum\t%d\t%s\t%g\t%d\t%s' % (
            k, j, x['prec'], 1 if int(j) == v['main'] else 0, ','.join('%g' % x['c'][r] if r in x['c'] else '-' for r in RAR)))
    for r_i, r in enumerate(RAR):
        x = v['r'].get(r)
        if not x:
            continue
        out.append('famval\t%d\t%d\t%g\t%g\t%g\t%g' % (k, r_i, x['lo'], x['hi'], x['mu'], x['sigma']))
        # 说明和 famr 一样补「伤害随…提升」（rr/procs.py）
        from . import procs
        ann = lambda t, lang: esc(procs.annotate(ctx, key, lang, t))
        out.append('famtpl\t%d\t%d\t%s\t%s' % (k, r_i, ann(x['tpl'][0], 'zh'), ann(x['tpl'][1], 'en')))
        out.append('famspan\t%d\t%d\t%s\t%s' % (k, r_i, ann(x['span'][0], 'zh'), ann(x['span'][1], 'en')))
        if x.get('rows'):
            out.append('famrow\t%d\t%d\t%s' % (k, r_i, ','.join(map(str, x['rows']))))
        # 二期：famrnum <序号> <r> <第几条规则> <字段> <a> <b> <数的位置>（积木引擎改规则里这一档的数）；
        # famslot <序号> <r> <效果编号> <偏移:类型:a:b:数的位置;…>（规则挂的这一档的效果行，dark_core 原地改写成精确数值）；
        # famrun <序号> <r> <模块> <模块数值的位置> <a> <b> <数的位置>（专用模块按位置取数）
        out += ['famrnum\t%d\t%d\t%d\t%s\t%g\t%g\t%d' % (k, r_i, nth, fld, ca, cb, j) for nth, fld, ca, cb, j in v.get('rnum') or []]
        out += ['famslot\t%d\t%d\t%d\t%s' % (k, r_i, sid, ';'.join('%d:%s:%g:%g:%d' % tuple(w) for w in ws))
                for _nth, _fld, _lay, sid, ws in x.get('slots') or []]
        out += ['famrun\t%d\t%d\t%s\t%d\t%g\t%g\t%d' % (k, r_i, run, vi, ca, cb, j) for run, vi, ca, cb, j in v.get('run') or []]
        out += ['famref\t%d\t%d\t%d\t%d\t%d' % (k, r_i, a, o, t) for a, o, t in x.get('refs') or []]
        out += ['famfld\t%d\t%d\t%d\t%d\t%s\t%g\t%g\t%d' % (k, r_i, a, o, fc, ca, cb, j) for a, o, fc, ca, cb, j in x.get('fields') or []]
    return out


def attr_copies(ctx):
    """原版类型的数值词条每个稀有度只有一个效果编号，两件同稀有度的装备挂的是同一个效果，游戏里只算一次。
    每个效果复制 ATTR_COPIES 份（数值一样、编号不同），dll\\dark_core（attrstack.rs）按身上出现的件数挂副本。
    只做效果行本身带数值的（不引用别的效果，STACK_CHAIN_KEYS 除外）；写进 runtime.txt 的 attrdup 行（write_def）；
    settings 的 numeric_affix_stack = false 不做（旧的 attr_affix_stack 也认）"""
    ctx.attr_dup = []
    if not ctx.S.get('numeric_affix_stack', ctx.S.get('attr_affix_stack', True)):
        return
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    P = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}
    get = lambda row, f: struct.unpack_from('<' + lay[f][1], row, lay[f][2])[0]
    nid = ATTR_COPY_BASE
    skipped = []
    for key, f in lib['gear'].items():
        if (f.get('group') in STACK_SKIP_GROUPS and key not in STACK_NEW_KEYS) or f.get('retired') or key in STACK_SKIP_KEYS:
            continue
        # 词条数值随机的词条：dark_core 给每件装备的每条词条各挂一份占位行，本来就各算各的，不建副本
        if f.get('vrand') and value_random(ctx):
            continue
        if f.get('stack') == 'top':                 # 同名只认最高的（famtop）：不叠加，不建副本
            continue
        sps = [(r_i, f['sp'].get(r)) for r_i, r in enumerate(RAR) if f['sp'].get(r) in P.rows]
        chain = key in STACK_CHAIN_KEYS
        refs = [x for x in SP_REF_FIELDS if not (chain and x == 'cycleOccurrenceSpEffectId')]
        if any(get(P.rows[sp], x) not in (0, -1) for _r, sp in sps for x in refs):
            skipped.append((f.get('suffix') or ['', key])[1])
            continue
        for r_i, sp in sps:
            copies = []
            for _ in range(ATTR_COPIES):
                if nid in P.rows:
                    raise RuntimeError('数值词条副本的效果编号 %d 已经有人用了' % nid)
                row = bytearray(P.rows[sp])
                copy_id, nid = nid, nid + 1
                cycle = get(row, 'cycleOccurrenceSpEffectId') if chain else 0
                if cycle > 0:
                    if nid in P.rows:
                        raise RuntimeError('数值词条副本的效果编号 %d 已经有人用了' % nid)
                    P.add_row(nid, bytes(P.rows[cycle]), P.names.get(cycle, b''))
                    struct.pack_into('<' + lay['cycleOccurrenceSpEffectId'][1], row, lay['cycleOccurrenceSpEffectId'][2], nid)
                    nid += 1
                P.add_row(copy_id, bytes(row), P.names.get(sp, b''))
                copies.append(copy_id)
            ctx.attr_dup.append((key, r_i, sp, copies))
    ctx.bnd.put('SpEffectParam.param', P.serialize())
    ctx.report.append('数值词条同稀有度叠加：%d 种词条、%d 个效果各复制 %d 份（%d~%d），dark_core 按身上件数挂；触发型不做：%s' % (
        len({k for k, *_ in ctx.attr_dup}), len(ctx.attr_dup), ATTR_COPIES, ATTR_COPY_BASE, nid - 1, '、'.join(skipped) or '无'))


# 战技伤害按稀有度（用户 2026-11-08：普通 0.7、稀有 0.8、史诗 0.9、传说 1.0，整个战技伤害都算）：
# 照「亚历山大的碎片」的效果（312310：五种攻击力倍率 + 只管攻击子类别 112 / 111 = 战技）复制，倍率改成各稀有度的数，
# dll\\dark_core（skillmult.rs）按放战技的那把生成武器的稀有度挂一个。1.0 的稀有度不建。settings 的 skill_damage_by_rarity 可以改
SKILL_MULT = {'Common': 0.7, 'Rare': 0.8, 'Epic': 0.9, 'Legendary': 1.0}
SKILL_TEMPLATE = 312310
SKILL_SP_BASE = 7296900
SKILL_RATES = ('physicsAttackRate', 'magicAttackRate', 'fireAttackRate', 'thunderAttackRate', 'darkAttackRate')


def skill_mults(ctx):
    """建各稀有度的战技伤害倍率效果，记进 ctx.skill_mult = [(稀有度 0~3, 效果编号, 倍率)]，write_def 写成 runtime.txt 的 skillmult 行"""
    ctx.skill_mult = []
    cfg = ctx.S.get('skill_damage_by_rarity') or {}
    if not cfg.get('enabled', True):
        return
    P = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    if SKILL_TEMPLATE not in P.rows:
        ctx.report.append('战技伤害按稀有度：没有模板效果 %d，没做' % SKILL_TEMPLATE)
        return
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}
    put = lambda row, f, v: struct.pack_into('<' + lay[f][1], row, lay[f][2], v)
    mult = cfg.get('mult') or {}
    for r_i, r in enumerate(RAR):
        m = float(mult.get(r, SKILL_MULT[r]))
        if m == 1.0:
            continue
        sp = SKILL_SP_BASE + r_i
        if sp in P.rows:
            raise RuntimeError('战技伤害倍率的效果编号 %d 已经有人用了' % sp)
        row = bytearray(P.rows[SKILL_TEMPLATE])
        put(row, 'iconId', -1)
        put(row, 'effectEndurance', -1.0)
        for f in SKILL_RATES:
            put(row, f, m)
        P.add_row(sp, bytes(row))
        ctx.skill_mult.append((r_i, sp, m))
    ctx.bnd.put('SpEffectParam.param', P.serialize())
    ctx.report.append('战技伤害按稀有度：%s（效果 %s，dark_core 按放战技的那把生成武器挂）' % (
        '、'.join('%s ×%g' % (RAR_ZH[r], float(mult.get(r, SKILL_MULT[r]))) for r in RAR),
        '、'.join(str(sp) for _r, sp, _m in ctx.skill_mult) or '无'))


# 法器倍率（用户 2026-11-03：「补正基数按稀有度也正态分布 普通和原版一样 稀有则是120 史诗160 传说200」「祷告同理」，
# 又「那改补正值的分布不就好了 这样也能显示在面板上」）：原版法术补正 = 100 × (1 + Σ 补正值 × 补正倍率 × 曲线)，100 是游戏写死的；
# 改成生成法器的五项补正值 × 倍率（dark_core build_row 改参数行，面板上的补正、法术补正都跟着变，配方里存的不乘，重铸 / 超限照配方）。
# 每件的倍率由 dark_core 按记录在稀有度区间（百分数）里抽截断正态（同防具减伤：均值 = 中点，区间 = ±2σ）；法球（迸发、星群）也乘它（spellbase.rs）。
# 能施法的法器本体（weaponCategory 8 里 enableMagic / enableMiracle 的：法杖、圣印记）写进 affixes.txt 的 wcast 行。settings 的 catalyst_base 可以改。
# 能施法的近战武器（卡利亚魔法剑 2530000，类别 2）不算（用户 2026-11-20「修一下卡利亚魔法剑吃到法杖专用的补正增强的问题」）：
# 倍率乘的是五项补正值，近战武器的攻击力也按这几项补正，以前跟着法杖一起放大到 0.7~2.5 倍
# 弓（weaponCategory 10：短弓、长弓、大弓，含幽影之地的）也乘（用户 2026-11-21「弓不再走超限额外波动了 弩和弩炮不动 弓走法杖的补正」）：
# 一起写进 wcast（能施法写 0 0），dark_core 按 wcast 乘法器倍率、超限上限不随机（gear/overlimit.rs cap_mult）；弩、弩炮（类别 11）照旧
CATALYST_CATEGORY = 8
BOW_CATEGORY = 10
CAST_BASE = {'Common': (70, 130), 'Rare': (90, 150), 'Epic': (110, 210), 'Legendary': (150, 250)}   # 普通 / 稀有 ±30、史诗 / 传说 ±50（用户 2026-11-03）


def cast_bases(ctx):
    """记下法器倍率的区间 ctx.cast_range 和乘它的本体 ctx.cast_ids = [(本体, 魔法, 祷告)]（法杖、圣印记，再加上弓，弓写 0 0），
    write_def 写成 affixes.txt 的 cbase / wcast 行"""
    ctx.cast_range, ctx.cast_ids = None, []
    cfg = ctx.S.get('catalyst_base') or {}
    if not cfg.get('enabled', True):
        return
    rg = {r: tuple(map(float, (cfg.get('range') or {}).get(r) or CAST_BASE[r])) for r in RAR}
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    wl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamWeapon.xml')))[0]}
    bit = lambda row, f: (row[wl[f][2]] >> wl[f][3]) & 1 if wl[f][4] else row[wl[f][2]]
    melee, bows = [], []
    for i, row in sorted(W.rows.items()):
        if i >= 100000000 or i % 10000:
            continue
        if bit(row, 'enableMagic') or bit(row, 'enableMiracle'):
            if bit(row, 'weaponCategory') != CATALYST_CATEGORY:
                melee.append(i)
                continue
            ctx.cast_ids.append((i, bit(row, 'enableMagic'), bit(row, 'enableMiracle')))
        elif bit(row, 'weaponCategory') == BOW_CATEGORY:
            bows.append(i)
    ctx.cast_ids += [(i, 0, 0) for i in bows]
    ctx.cast_range = rg
    ctx.report.append('法器倍率：%s（补正值 × 倍率 ÷ 100，法器本体 %d 种 + 弓 %d 种，dark_core 改参数行时乘；能施法的近战武器 %s 不乘）' % (
        '、'.join('%s %g~%g' % (RAR_ZH[r], *rg[r]) for r in RAR), len(ctx.cast_ids) - len(bows), len(bows), ' '.join(map(str, melee)) or '没有'))


def hooks(ctx):
    """affixes.json 的 hooks：原版行上要接的字段（比如冻伤发作接霜铠的附近判定），只改这个字段还空着（empty 里的值）的行"""
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    for h in lib.get('hooks', []):
        P = erlib.Param(ctx.bnd.get(h['param'] + '.param'))
        lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, HOOK_XML[h['param']])))[0]}
        get = lambda row, f: struct.unpack_from('<' + lay[f][1], row, lay[f][2])[0]
        n, busy = 0, []
        for i, row in P.rows.items():
            if all(get(row, f) == v for f, v in h['where'].items()):
                if get(row, h['field']) in h['empty']:
                    row = bytearray(row)
                    struct.pack_into('<' + lay[h['field']][1], row, lay[h['field']][2], h['value'])
                    P.rows[i] = row
                    n += 1
                elif get(row, h['field']) != h['value']:
                    busy.append(i)
        ctx.bnd.put(h['param'] + '.param', P.serialize())
        ctx.report.append('词条库：%s %d 行%s' % (h['what'], n, '（%d 行这个字段已经有别的用途，没接：%s）' % (len(busy), busy[:8]) if busy else ''))


INFO_CAP = 160          # 护符简介：说明的第一行，超过这么多字就写「效果：后缀（详见说明）」（同 dark_core 生成护符的写法）


def paint(tag, text):
    """词条说明上稀有度的颜色：用稀有度名字带的 <font color="#…">，每行各包一层（同 dark_core 的 paint）"""
    m = re.match(r'<font[^>]*>', tag)
    if not m:
        return text
    return '\n'.join(m.group(0) + l + '</font>' if l else l for l in text.split('\n'))


def template_texts(ctx):
    """护符模板（暗黑商店卖的、开局遗物）的名字 / 简介 / 说明写进文字包，写法同 dark_core 生成的护符"""
    from . import procs
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    for lang, code in (('zh', 'zhocn'), ('en', 'engus')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        add = {'Name': {}, 'Info': {}, 'Caption': {}}
        for key, f in lib['gear'].items():
            s = f['suffix'][1] if lang == 'zh' else f['suffix'][0]
            for r, t in f['tal'].items():
                tag = lib['rarity_tag'][r][lang]
                sent = procs.annotate(ctx, key, lang, f['text'][r][lang])
                first = sent.split('\n')[0]
                add['Name'][t] = '%s %s护符' % (tag, s) if lang == 'zh' else '%s Amulet of %s' % (tag, s)
                if len(first) <= INFO_CAP:
                    add['Info'][t] = first
                else:
                    add['Info'][t] = '效果：%s（详见说明）' % s if lang == 'zh' else 'Effect: %s (see description)' % s
                add['Caption'][t] = paint(lib['rarity_tag'][r]['zh'], sent)
        for fld, d in add.items():
            fmg = 'Accessory%s.fmg' % fld
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            e = dict(ents)
            e.update(d)
            mb.put(fmg, erlib.write_fmg(hdr, sorted(e.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))


# ---------------------------------------------------------------- 给 dark_core 的词条库（鉴定时照它抽）
STATS = ('Strength', 'Agility', 'Magic', 'Faith', 'Luck')
STAT_TAG = {'zh': ('力气', '灵巧', '智力', '信仰', '感应'), 'en': ('Str', 'Dex', 'Int', 'Fai', 'Arc')}
CURVES = ('Physics', 'Magic', 'Fire', 'Thunder', 'Dark', 'Poison', 'Blood', 'Sleep', 'Madness')
STATUS_KINDS = ('bleed', 'poison', 'rot', 'frost', 'sleep', 'death', 'madness')
# 面板「附加效果」显示的文字（WeaponEffect：累积出血量表（<?bleedATKpwr?>）等，数值游戏自己填）；武器的 spEffectMsgId 跟着异常写
STATUS_MSG = {'bleed': 6501, 'poison': 6401, 'rot': 6451, 'frost': 6601, 'sleep': 6651, 'death': 6551, 'madness': 6701}
RES_CATS = ('staff', 'seal', 'shield')
GLOW_ELEM = ('magic', 'fire', 'thunder', 'holy')             # 本体属性 1~4（物理 0 不加光效）
# 盾牌随机的六项（顺序同 dark_core gear.rs 的 GUARD_F；说明见下面 SHIELD_TYPES）
GUARD_F = ('physGuardCutRate', 'magGuardCutRate', 'fireGuardCutRate', 'thunGuardCutRate', 'darkGuardCutRate', 'staminaGuardDef')
W_FIELDS = ['correct' + s for s in STATS] + ['proper' + s for s in STATS] + ['correctType_' + c for c in CURVES] + \
    ['attackElementCorrectId', 'spEffectBehaviorId0', 'spEffectBehaviorId1', 'spEffectBehaviorId2', 'residentSpEffectId',
     'residentSpEffectId1', 'residentSpEffectId2', 'swordArtsParamId', 'behaviorVariationId', 'wepType', 'sellValue', 'rarity',
     'spEffectMsgId0', 'spEffectMsgId1', 'spEffectMsgId2',
     'disableGemAttr', 'gemMountType', 'isEnhance', 'reinforceTypeId', 'materialSetId', 'iconId',
     'attackBasePhysics', 'attackBaseMagic', 'attackBaseFire', 'attackBaseThunder', 'attackBaseDark'] + list(GUARD_F) + \
    ['throwAtkRate']            # 致命一击按稀有度乘（wcrit，2026-11-10）
# 盾牌随机（shield_guard_random，用户 2026-11-01）：小盾、中盾、大盾、突刺盾的五种属性防御时减伤和防御强度，各自在原版同类盾的值里
# 按稀有度的分位区间抽（越稀有越偏强）；顺序和 dark_core gear.rs 的 GUARD_F 一样。settings 的 shield_guard_random 可以改
SHIELD_TYPES = (65, 67, 69, 90)
GUARD_Q = {'Common': (0.0, 0.5), 'Rare': (0.15, 0.7), 'Epic': (0.3, 0.85), 'Legendary': (0.5, 1.0)}
# 强攻（武器本体层，不占特效位，用户 2026-10-28 要的）：各稀有度出的几率（%）、基础攻击力加成（%）；settings 的 weapon_assault 可以改
ASSAULT_CHANCE, ASSAULT_PCT = (10, 15, 20, 25), (5, 10, 15, 20)
# 重武器的基础攻击力倍率（用户 2026-10-31，先 1.5，知道能力加成也跟着乘后改 1.3）：大剑、特大剑、大曲剑、大刺剑、大斧、大锤、大枪、戟、
# 特大武器、大刀（DLC）；settings 的 heavy_weapon_atk 可以改
HEAVY_TYPES, HEAVY_MULT = (5, 7, 11, 16, 19, 23, 28, 29, 41, 94), 1.3
# 轻武器的基础攻击力倍率（用户 2026-11-08）：近战类型里除重武器和火把 / 调香瓶 / 投掷剑之外的类别，
# 即短剑、直剑、曲剑、刀、双头剑、刺剑、斧、槌、连枷、矛、镰刀、拳、爪、鞭，以及 DLC 的格斗术、反手剑、轻大剑、兽爪；
# settings 的 light_weapon_atk 可以改。弓、弩、法杖、圣印记、盾牌不加。
LIGHT_TYPES, LIGHT_MULT = (1, 3, 9, 13, 14, 15, 17, 21, 24, 25, 31, 35, 37, 39, 88, 92, 93, 95), 1.2
# 武器属性随机（用户 2026-11-10）：拆分时元素占比区间 %、拆分补偿系数、纯元素倍率、不抽的武器类型
# （57 法杖、61 圣印记、50 / 51 / 53 / 55 / 56 弓弩、87 火把、89 调香瓶）
WELEM_SHARE, WELEM_COEF, WELEM_PURE = (30, 60), 0.3, 1.08
WELEM_SKIP = (57, 61, 50, 51, 53, 55, 56, 87, 89)
# 防具减伤倍率（用户 2026-10-29；同一天又整体 +0.2）：各稀有度在原版减伤上乘的倍率区间，DLL 按截断正态抽（均值 = 中点，区间 = ±2σ）；settings 的 armor_negation 可以改
ARMOR_NEG = {'Common': (1.2, 1.4), 'Rare': (1.3, 1.5), 'Epic': (1.5, 1.7), 'Legendary': (1.6, 1.8)}
# 武器补正值（用户 2026-11-02「改成正态分布」，同一天又「可以有交叠 不用分层这么明显」把区间放宽一倍，又「下三档中位再提高10 20 20」；以前照原包各稀有度生成武器的补正值统计，
# 跨度大，普通 ~ 史诗拉不开）：每项补正在区间里
# 按截断正态抽（同防具减伤：均值 = 中点，区间 = ±2σ），1 / 2 / 3 项一样；全能（5 项）的区间乘原包里全能和两项的中位数之比。
# 写成 wscal_v 的「值:权重」，DLL 不用改，开局 / 追忆 / 商人取前百分之几照旧。settings 的 weapon_scaling 可以改，enabled = false 照原包的统计
WEAPON_SCAL = {'Common': (40, 80), 'Rare': (60, 100), 'Epic': (70, 110), 'Legendary': (100, 150)}
# 装备名字的前后缀（用户 2026-10-28）：机制类词条（触发、规则改变）做前缀，数值类（加减数值，最多带一个持握 / 血量之类的简单条件）做后缀。
# 这两组和「新词条」算机制类，新词条里下面这些只是加减数值，算数值类
MECH_GROUPS = ('附近触发', '命中时触发', '新词条')
NUMERIC_NEW = ('dr_gale', 'dr_deft', 'dr_calm', 'dr_rage', 'dr_blood_surge', 'dr_desperate', 'dr_orb_flow', 'dr_crack', 'dr_alternate')
# 词条位置（用户 2026-10-28 定的数）：每个档（普通 / 稀有 / 史诗 / 传说 / 传说（幽影））每个位置有词条的几率（%）。
# 防具：前缀位抽机制类、两个后缀位抽数值类；武器只有前缀位（特效）；位置上抽哪条在能出的里面每条一样（词条库的权重）
SLOT_DEFAULT = {'armor_prefix': (10, 15, 20, 25, 40), 'armor_suffix1': (100, 100, 100, 100, 100),
                'armor_suffix2': (10, 20, 30, 40, 65), 'weapon_prefix': (30, 35, 40, 45, 60)}   # 武器前缀 2026-10-30 起（以前 0 / 3 / 6 / 10 / 10）


def is_mech(key, f):
    return f.get('group') in MECH_GROUPS and key not in NUMERIC_NEW


SLOT_W_MIN, SLOT_W_RATIO = 100, 1000   # 部位补偿后的权重：最小的是 100，最大不超过它的 1000 倍
# 生成的防具四个部位（头 / 身 / 手 / 腿）一样多（用户 2026-10-31；以前照原包的件数，头、身约三成多，手、腿不到两成，
# 手甲、腿甲专属的前缀词条再怎么补偿也只有平均的六七成）
SLOT_EVEN = True


def slot_balanced(fams, p_slot, iters=600):
    """防具一个位置（机制类 / 数值类分开算）的权重按部位补偿（用户 2026-10-31：只能出在某些部位的词条补偿到整体一样）：
    fams = [(键, 词条库权重, 能出的部位位：头 1 / 身 2 / 手 4 / 腿 8, 单位：变体组的键，单条就是自己的键)]，
    p_slot = {部位 0~3: 抽到这个部位的几率}。DLL 先按 p_slot 抽部位，再在这个部位能出的里面按权重抽，所以一条词条在所有防具上的
    出现几率 = Σ 部位几率 × 自己的权重 / 这个部位能出的总权重。变体组加起来算一条（用户 2026-10-31）：组员的权重比例照词条库（平分），
    整组乘同一个系数；反复按（平均 / 自己）调各单位的系数，让各单位（组或单条）一样多。
    做不到完全一样时（手部专属的词条多、手甲又少），这几条在自己的部位上占满（系数顶到 SLOT_W_RATIO 倍），别的照样补齐。
    返回（{键: 整数权重}, 补偿后单位最少 / 最多是平均的几成）"""
    act = [(k, w, m, u) for k, w, m, u in fams if w > 0 and any(m >> s & 1 for s in p_slot)]
    if not act:
        return {}, (1.0, 1.0)
    mul = {u: 1.0 for *_, u in act}

    def freq():
        wt = {k: mul[u] * w for k, w, m, u in act}
        tot = {s: sum(wt[k] for k, w, m, u in act if m >> s & 1) for s in p_slot}
        out = defaultdict(float)
        for k, w, m, u in act:
            out[u] += sum(p * wt[k] / tot[s] for s, p in p_slot.items() if m >> s & 1)
        return out, wt
    for _ in range(iters):
        f, _ = freq()
        mean = sum(f.values()) / len(f)
        for u in mul:
            mul[u] *= (mean / f[u]) ** 0.5
        lo = min(mul.values())
        mul = {u: min(v / lo, SLOT_W_RATIO) for u, v in mul.items()}
    f, wt = freq()
    mean = sum(f.values()) / len(f)
    lo = min(wt.values())
    return {k: max(1, round(SLOT_W_MIN * v / lo)) for k, v in wt.items()}, (min(f.values()) / mean, max(f.values()) / mean)


P_FIELDS = ['residentSpEffectId', 'residentSpEffectId2', 'residentSpEffectId3', 'protectorCategory', 'sellValue', 'rarity', 'iconIdM', 'iconIdF',
            'neutralDamageCutRate', 'slashDamageCutRate', 'blowDamageCutRate', 'thrustDamageCutRate',
            'magicDamageCutRate', 'fireDamageCutRate', 'thunderDamageCutRate', 'darkDamageCutRate']
A_FIELDS = ['refId', 'sellValue', 'rarity', 'iconId']
SLOTS = ('head', 'body', 'arm', 'leg')


def esc(s):
    return (s or '').replace('\\', '\\\\').replace('\t', '\\t').replace('\r', '').replace('\n', '\\n')


# 武器类型权重 × weapon_type_boost 的几类（用户 2026-11-10「给法杖和圣印记和弓弩系列一些补正」，同日「盾牌不用动」）：法杖、圣印记、
# 小弓、长弓、大弓、弩、弩炮
SUPPORT_TYPES = {57, 61, 50, 51, 53, 55, 56}


def pairs(h, scale=1):
    """{值: 件数} → 「值:权重 …」（Tab 分隔）"""
    return '\t'.join('%s:%d' % (k, max(1, round(v * scale))) for k, v in sorted(h.items(), key=lambda kv: float(kv[0])) if v > 0)


def median(h):
    """{值: 件数} 的中位数"""
    xs = sorted((float(k), v) for k, v in h.items() if v > 0)
    tot, acc = sum(v for _k, v in xs), 0
    for k, v in xs:
        acc += v
        if acc * 2 >= tot:
            return k
    return 0.0


def normal_hist(lo, hi, total=10000):
    """区间 [lo, hi] 的截断正态（均值 = 中点，σ = 区间宽 / 4）离散到整数：{值: 权重}，权重合计约 total"""
    mu, sd = (lo + hi) / 2, max((hi - lo) / 4, 1e-6)
    w = {float(x): math.exp(-0.5 * ((x - mu) / sd) ** 2) for x in range(math.ceil(lo), math.floor(hi) + 1)}
    s = sum(w.values()) or 1.0
    return {x: v * total / s for x, v in w.items()}


def weapon_scaling(ctx, wt):
    """各稀有度各项数的补正值分布 {稀有度: {项数: {值: 权重}}}：settings 的 weapon_scaling 开着就是截断正态（见 WEAPON_SCAL），否则照原包。
    返回（分布，报告用的说明）"""
    src = wt['scaling']['value']
    ws = ctx.S.get('weapon_scaling') or {}
    if not ws.get('enabled', True):
        return src, '照原包的统计'
    rg, out, note = ws.get('range') or {}, {}, []
    for r in RAR:
        lo, hi = map(float, rg.get(r) or WEAPON_SCAL[r])
        two = median(src[r].get('2') or {}) or 1.0
        out[r] = {}
        for n, h in src[r].items():
            k = median(h) / two if n == '5' else 1.0          # 全能：照原包全能和两项的中位数之比
            out[r][n] = normal_hist(lo * k, hi * k)
            if n == '5':
                note.append('%s %g~%g（全能 ×%.2f）' % (RAR_ZH[r], lo, hi, k))
        if '5' not in src[r]:
            note.append('%s %g~%g' % (RAR_ZH[r], lo, hi))
    return out, '截断正态 ' + '、'.join(note)


def bases(ctx, lib):
    """能当本体的原版武器 / 防具（这次 regulation 里编号 < 1 亿、整万的武器 / 4 万 ~ 1000 万的防具；有名字；武器类型在原包出现过）。
    返回（武器 [{type, id, var, elem, weight, zh, en}], 防具 [{slot, id, weight, zh, en}], 取名字的函数 nm(语言, FMG, 编号)）"""
    names = {}
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        m = erlib.read_msgbnd(mp) if erlib.dcx_exists(mp) else {}
        for fmg in ('WeaponName', 'ProtectorName', 'ArtsName'):
            d = {}
            for k, v in m.items():
                if k == fmg or k.startswith(fmg + '_dlc'):
                    d.update(v)
            names[(lang, fmg)] = d
    nm = lambda lang, fmg, i: re.sub(r'<[^>]+>', '', names[(lang, fmg)].get(i) or '').strip()
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    wl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamWeapon.xml')))[0]}
    g = lambda lay, row, f: struct.unpack_from('<' + lay[f][1], row, lay[f][2])[0]
    types = {int(t) for r in RAR for t in lib['weapon']['types'][r]}
    wb = []
    for i, row in sorted(W.rows.items()):
        if i >= 100000000 or i % 10000:
            continue
        t = g(wl, row, 'wepType')
        zh, en = nm('zh', 'WeaponName', i), nm('en', 'WeaponName', i)
        if t not in types or not zh or not en or 'ERROR' in en:
            continue
        atk = [g(wl, row, f) for f in ('attackBaseMagic', 'attackBaseFire', 'attackBaseThunder', 'attackBaseDark')]
        elem = next((4 - k for k, a in enumerate(reversed(atk)) if a > 0), 0)    # 圣 > 雷 > 火 > 魔力（同旧版的光效优先级）
        wb.append({'type': t, 'id': i, 'var': g(wl, row, 'behaviorVariationId'), 'elem': elem, 'weight': g(wl, row, 'weight'), 'zh': zh, 'en': en})
    Pp = erlib.Param(ctx.bnd.get('EquipParamProtector.param'))
    pl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamProtector.xml')))[0]}
    pb = []
    for i, row in sorted(Pp.rows.items()):
        if i >= 10000000 or i < 40000:            # 4 万以下是光着的占位（头部 / 身体…）；1000 万起是我们的容器
            continue
        s = g(pl, row, 'protectorCategory')
        zh, en = nm('zh', 'ProtectorName', i), nm('en', 'ProtectorName', i)
        if s > 3 or not zh or not en or 'ERROR' in en:
            continue
        pb.append({'slot': s, 'id': i, 'weight': g(pl, row, 'weight'), 'zh': zh, 'en': en})
    return wb, pb, nm


def clash_lines(ctx):
    """dll\\dark_core\\clash.txt（格式见 dark_core 的 clash.rs）：相杀（dr_clash）挂的效果行 → 哪只手、固定受到伤害倍率 0.4（减伤 60%）。
    不再区分轻重击、武器或左右手。没有新装备系统、词条库里没有相杀就没有"""
    if not getattr(ctx, 'containers', None):
        return []
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    f = lib['gear'].get('dr_clash')
    if not f:
        return []
    rt = f.get('runtime') or {}
    out, seen = [], set()
    for rule in rt.get('rules') or []:
        m = re.fullmatch(r'clash_(l|h|hc)_(r|l)', str(rule.get('cond', '')))
        if not m:
            continue
        for sp in rule.get('effect') or []:
            if sp > 0 and sp not in seen:
                seen.add(sp)
                out.append('row %d %s 0.4' % (sp, m.group(2)))
    # 防御火花（玩家脚本在相杀时挨打才放）：dll 看到它出现就记一行「挡下一次攻击」
    for k in ('clash_spark_r', 'clash_spark_l'):
        for sp in (rt.get('hks') or {}).get(k) or []:
            if sp > 0 and sp not in seen:
                seen.add(sp)
                out.append('spark %d' % sp)
    # 挡下时的那一声（人物类音效，光效行放不了 → 事件脚本放：dll 看到火花出现就点亮 sound 标记，rr/sounds.py；用户 2026-11-04）
    from . import sounds
    return out + sounds.clash_lines(ctx.S) + sounds.vfx_lines(ctx)     # 见切成立时的羽毛特效（mvfx）也写在这里，和见切音效同一帧


def hitwin_lines(ctx):
    """dll\\dark_core\\hitwin.txt：玩家普通攻击动作的攻击判定时间（data\\hit_windows.txt，dev\\item_system\\build_hit_windows.py 生成）→
    hitwin <动作编号> <判定开始> <判定结束>，积木引擎 while 的 hit 用（相杀按判定开窗口，用户 2026-11-04）。没有规则用 hit 就没有"""
    if not getattr(ctx, 'containers', None):
        return []
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    if not any('hit' in rule for f in lib['gear'].values() for rule in (f.get('runtime') or {}).get('rules') or []):
        return []
    src = os.path.join(ctx.data_dir, 'hit_windows.txt')
    if not os.path.isfile(src):
        return []
    out = []
    for l in open(src, encoding='utf-8'):
        f = l.split()
        if len(f) == 3 and not l.startswith('#'):
            out.append('hitwin\t%s\t%s\t%s' % tuple(f))
    return out


def foewin_lines(ctx):
    """dll\\dark_core\\foewin.txt：敌人攻击动作的攻击判定时间段（data\\foe_windows.txt，dev\\item_system\\build_foe_windows.py 生成）→
    foewin <模型号> <动作编号> <开始,结束[;开始,结束…]>，积木引擎的见切用（用户 2026-11-11「用出招判定帧」：翻滚无敌时敌人的判定正好在才算）。
    没有规则听见切（event=mikiri）就没有"""
    if not getattr(ctx, 'containers', None):
        return []
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    rules = [rule for f in lib['gear'].values() for rule in (f.get('runtime') or {}).get('rules') or []]
    if not any(r.get('event') == 'mikiri' or 'mikiri' in str(r.get('add', '')) for r in rules if isinstance(r, dict)):
        return []
    src = os.path.join(ctx.data_dir, 'foe_windows.txt')
    if not os.path.isfile(src):
        return []

    def read(path):
        """{模型号: [(动作编号, 时间段)]}（保持文件里的顺序）"""
        blocks, model = {}, None
        for l in open(path, encoding='utf-8'):
            f = l.split()
            if not f or l.startswith('#'):
                continue
            if f[0] == 'm' and len(f) == 2:
                model = f[1]
                blocks.setdefault(model, [])
            elif model is not None and len(f) == 2:
                blocks[model].append((f[0], f[1]))
        return blocks
    blocks = read(src)
    # Boss 模组（用户 2026-11-12「这是我们整合进来的boss出招 这个也要加进来」）：这次加载的模组带了动作包的模型，整块换成模组的
    # （data\\bossmods\\<键>\\foe_windows.txt，dev\\item_system\\build_foe_windows.py 生成）；没加载的照原版
    from . import bossmods
    swapped = []
    for k in bossmods.keys(ctx):
        mp = os.path.join(ctx.data_dir, 'bossmods', k, 'foe_windows.txt')
        if os.path.isfile(mp):
            mod = read(mp)
            blocks.update(mod)
            swapped += ['c%04d' % int(m) for m in mod]
    if swapped:
        ctx.report.append('见切的敌人攻击判定：Boss 模组的动作换上了 %d 个模型（%s）' % (len(swapped), '、'.join(swapped)))
    return ['foewin\t%s\t%s\t%s' % (m, a, w) for m, rows in blocks.items() for a, w in rows]


def codex_lines(ctx, lib):
    """词条百科（dark_ui 的 ui/codex.rs）在 fam / famr / wspec 之外多要的两样：
    wspecarch <键> <流派>：武器特效的流派；famlink <键> <键,…>：规则里互相用到的词条（往同一个键上叠层、拿别的词条的层数、看别的词条的标记……），
    从积木规则自动算、双向，新词条不用另外登记；
    famicon <键> <图标 普通,稀有,史诗,传说>：没加边框的原图标（0 = 这一档没有；界面查 dr_frames.txt 换成带框的）。
    优先 data\\codex_icons.json（换图标只改那个文件），其次这个词条这一档的护符现在的图标（护符换图标这里跟着变）"""
    pool = ((lib.get('weapon') or {}).get('special') or {}).get('pool') or []
    rules = {k: (f.get('runtime') or {}).get('rules') or [] for k, f in lib['gear'].items()}
    rules.update({k: x['rules'] for k, x in ((lib.get('runtime') or {}).get('special_rules') or {}).items()})
    links = defaultdict(set)
    for k, rs in rules.items():
        for rule in rs:
            for field in ('stack', 'take', 'target_take', 'target_mark', 'max_boost_key', 'freeze_key', 'requires'):
                o = rule.get(field)
                if o != k and o in rules:
                    links[k].add(o)
                    links[o].add(k)
    p = os.path.join(ctx.data_dir, 'codex_icons.json')
    over = json.load(open(p, encoding='utf-8')) if os.path.isfile(p) else {}
    A = erlib.Param(ctx.bnd.get('EquipParamAccessory.param'))
    ic = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamAccessory.xml')))[0]}['iconId']
    tal_icon = lambda i: max(struct.unpack_from('<' + ic[1], A.rows[i], ic[2])[0], 0) if i in A.rows else 0
    icons, none = [], []
    for key, f in list(lib['gear'].items()) + [(x['key'], {}) for x in pool]:
        v = [over[key]] * len(RAR) if over.get(key) else [tal_icon((f.get('tal') or {}).get(r, -1)) for r in RAR]
        if any(v):
            icons.append('famicon\t%s\t%s' % (key, ','.join(map(str, v))))
        elif not f.get('retired'):
            none.append(key)
    if none:
        ctx.report.append('词条百科：%d 条词条没有图标（在 data\\codex_icons.json 补上）：%s' % (len(none), '、'.join(none)))
    return ['wspecarch\t%s\t%s' % (x['key'], x.get('archetype') or '其他') for x in pool] + \
        ['famlink\t%s\t%s' % (k, ','.join(sorted(v))) for k, v in sorted(links.items())] + icons


def write_def(ctx, path):
    """dll\\dark_core\\affixes.txt：词条库 + 这次 regulation 里能当本体的原版武器 / 防具（名字取这次的文字包）+ 要改的字段偏移。
    一行一项、Tab 分隔，文字里的换行 / Tab / 反斜杠转义成 \\n \\t \\\\。没有容器（没开未鉴定物品）就删掉"""
    from . import overlimit, procs
    if not os.path.isdir(os.path.dirname(path)):
        return
    if not getattr(ctx, 'containers', None):
        for x in (path, os.path.join(os.path.dirname(path), 'runtime.txt')):
            if os.path.exists(x):
                os.remove(x)
        return
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    L = ['# 词条库（dark_core 鉴定用，重随的 rr/affixes.py write_def 写；来源 launcher\\reroll\\data\\affixes\\affixes.json）。每次重随自动生成，不要手改',
         '# 稀有度 r：0 普通 / 1 稀有 / 2 史诗 / 3 传说；档 t 多一个 4 = 传说（幽影之地），武器、护符按传说算；「值:权重」是原包里的件数'
         '（wscal_v 补正值除外：settings 的 weapon_scaling 开着时是截断正态）']
    for k, r in enumerate(RAR):
        L.append('rar\t%d\t%s\t%s' % (k, esc(lib['rarity_tag'][r]['zh']), esc(lib['rarity_tag'][r]['en'])))
    for c, key in (('w', 'weapon'), ('p', 'armor'), ('a', 'talisman')):
        L.append('sell\t%s\t%s' % (c, '\t'.join(str(lib['sell'][key][r]) for r in RAR)))
    for z, en in zip(STAT_TAG['zh'], STAT_TAG['en']):
        L.append('stat\t%s\t%s' % (z, en))
    # 字段偏移：field <类> <名字> <偏移> <格式 f/B/i/H/h> <位（-1 = 整个字段）>
    for c, xml, names in (('w', 'EquipParamWeapon.xml', W_FIELDS), ('p', 'EquipParamProtector.xml', P_FIELDS), ('a', 'EquipParamAccessory.xml', A_FIELDS)):
        lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, xml)))[0]}
        for n in names:
            _nm, fc, off, bp, bits, _d = lay[n]
            L.append('field\t%s\t%s\t%d\t%s\t%d' % (c, n, off, fc, bp if bits else -1))
    wb, pb, nm = bases(ctx, lib)
    wt = lib['weapon']
    n_w, n_p = Counter(), Counter()
    for b in wb:
        L.append('wbase\t%d\t%d\t%d\t%d\t%s\t%s' % (b['type'], b['id'], b['var'], b['elem'], esc(b['zh']), esc(b['en'])))
        n_w[b['type']] += 1
    for b in pb:
        L.append('pbase\t%d\t%d\t%s\t%s' % (b['slot'], b['id'], esc(b['zh']), esc(b['en'])))
        n_p[b['slot']] += 1
    # 武器
    scal, scal_note = weapon_scaling(ctx, wt)
    ctx.report.append('武器补正值：%s' % scal_note)
    # 武器类型：用户 2026-11-10「改成均匀」——这个稀有度里有本体的类型都一样多（以前照原装备包的件数，火把 0.6%、大剑 4%）；
    # settings 的 weapon_type_uniform 设 false 回到按件数
    # 同日「给法杖和圣印记和弓弩系列一些补正」（盾牌不动）：这几类（SUPPORT_TYPES）权重 × weapon_type_boost（默认 2）
    uniform = ctx.S.get('weapon_type_uniform', True)
    boost = float(ctx.S.get('weapon_type_boost', 2))
    for r_i, r in enumerate(RAR):
        L.append('wtype\t%d\t%s' % (r_i, pairs({t: ((10 * boost if int(t) in SUPPORT_TYPES else 10) if uniform else v)
                                                 for t, v in wt['types'][r].items() if n_w.get(int(t))})))
        L.append('wscal_n\t%d\t%s' % (r_i, pairs(wt['scaling']['count'][r])))
        for n, h in scal[r].items():
            L.append('wscal_v\t%d\t%s\t%s' % (r_i, n, pairs(h)))
            # 超限锻造石（rr/overlimit.py）：ovlw <r> <项数> <中位> <原上限> <超限上限>（按这个分布的中位数、最大值）
            if overlimit.cfg(ctx.S):
                vals = [float(v) for v, w in h.items() if float(w) > 0]
                if vals:
                    L.append('ovlw\t%d\t%s\t%g\t%g\t%g' % ((r_i, n) + overlimit.caps(ctx.S, 2 * median(h) - max(vals), max(vals), 'w')))
        for k, s in enumerate(STATS):
            L.append('wreq\t%d\t%d\t%s' % (r_i, k, pairs(wt['scaling']['require'][r][s])))
        for k, c in enumerate(CURVES):
            L.append('wcurve\t%d\t%d\t%s' % (r_i, k, pairs(wt['scaling']['curve'][r][c])))
        L.append('wstat_n\t%d\t%s' % (r_i, pairs(wt['status']['count'][r])))
        for k, kind in enumerate(STATUS_KINDS):
            L.append('wstat_pow\t%d\t%d\t%s' % (k, r_i, pairs(wt['status']['power'][kind][r])))
    for k, kind in enumerate(STATUS_KINDS):
        L.append('wstat_sp\t%d\t%s' % (k, '\t'.join('%s:%d' % kv for kv in sorted(wt['status']['sp'][kind].items(), key=lambda kv: int(kv[0])))))
        L.append('wstat_msg\t%d\t%d' % (k, STATUS_MSG[kind]))
    # 需求规则：same_order = 各项需求和补正排序相同（补正最高的那项需求也最高）；min_level = 各稀有度最低等级
    # （从全 10 起只加需要的属性，力气按单手），不够的按补正比例补；全能（五项补正）不带异常
    wr = ctx.S.get('weapon_requirements') or {}
    L.append('wreq_rule\t%d\t%s' % (1 if wr.get('same_order', True) else 0,
                                    '\t'.join(str(int((wr.get('min_level') or {}).get(r, 0))) for r in RAR)))
    L.append('wfull_nostatus\t1')
    # 鉴定偏向加点：每件武器先生成几把候选，按「需求够不够得着、补正和加点吻合度」挑一把（1 = 不偏向）
    bb = ctx.S.get('identify_build_bias') or {}
    L.append('bias\t%d' % (int(bb.get('candidates', 3)) if bb.get('enabled', True) else 1))
    L.append('element_table\t%d' % wt['scaling']['element_table'])
    for k, e in enumerate(GLOW_ELEM):
        L.append('glow\t%d\t%d' % (k + 1, wt['glow'][e]))
    for c in RES_CATS:
        rc = wt['resident'][c]
        L.append('wres_types\t%s\t%s' % (c, ','.join(map(str, rc['types']))))
        for r_i, r in enumerate(RAR):
            L.append('wres_n\t%s\t%d\t%s' % (c, r_i, pairs(rc['count'][r])))
        for x in rc['pool']:
            if x['zh'] and x['en']:
                L.append('wres\t%s\t%d\t%d\t%s\t%s' % (c, x['sp'], x['weight'], esc(x['zh']), esc(x['en'])))
    # 武器的特殊效果词条位：wspec_n <r> <出几个的分布>；wspec <键> <效果> <权重> <武器类型,…（空 = 全部）> <短名中文> <短名英文> <说明中文> <说明英文>
    #   <能出的稀有度（位：普通 1 / 稀有 2 / 史诗 4 / 传说 8）>
    spec = wt.get('special') or {}
    if spec.get('pool'):
        for r_i, r in enumerate(RAR):
            L.append('wspec_n\t%d\t%s' % (r_i, pairs(spec['count'][r])))
        for x in spec['pool']:
            L.append('wspec\t%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%d' % (x['key'], x['sp'], x['weight'], ','.join(map(str, x.get('types') or [])),
                                                              esc(x['name'][0]), esc(x['name'][1]), esc(x['zh']), esc(x['en']),
                                                              sum(1 << RAR.index(r) for r in x.get('rarities') or RAR)))
    # 词条位置：pslot_p <档 0~4> <前缀（机制类）%> <后缀 1（数值类）%> <后缀 2（数值类）%>；wspec_p <档> <武器前缀（特效）%>。
    # 有这两种行 DLL 就按位置抽；没有（settings 关掉）照旧用 pcount / wspec_n（原包的分布）
    sl = ctx.S.get('affix_slots') or {}
    if sl.get('enabled', True):
        p = {k: [int(x) for x in (sl.get(k) or d)] for k, d in SLOT_DEFAULT.items()}
        for t in range(len(RAR) + 1):
            L.append('pslot_p\t%d\t%d\t%d\t%d' % (t, p['armor_prefix'][t], p['armor_suffix1'][t], p['armor_suffix2'][t]))
            L.append('wspec_p\t%d\t%d' % (t, p['weapon_prefix'][t]))
    # 强攻：wassault <r> <几率 %> <基础攻击力 +%>
    wa = ctx.S.get('weapon_assault') or {}
    if wa.get('enabled', True):
        chance, pct = wa.get('chance') or ASSAULT_CHANCE, wa.get('pct') or ASSAULT_PCT
        for r_i in range(len(RAR)):
            L.append('wassault\t%d\t%d\t%d' % (r_i, int(chance[r_i]), int(pct[r_i])))
    # 致命一击按稀有度乘：wcrit <r> <倍率>（面板的致命一击 = 100 + throwAtkRate，整个乘；用户 2026-11-10）
    cr = ctx.S.get('crit_by_rarity') or {}
    if cr.get('enabled', True):
        for r_i, r in enumerate(RAR):
            m = float((cr.get('mult') or {}).get(r, 1.0))
            if m != 1.0:
                L.append('wcrit\t%d\t%g' % (r_i, m))
    # 轻 / 重武器：wheavy <倍率> <武器类型,…>（五项基础攻击力再乘，和强攻相乘）。
    # DLL 只关心“类型 → 倍率”，这里把两套独立配置合并；同一类型不能同时出现在两边。
    atk_by_type = {}
    for key, default_types, default_mult in (
            ('light_weapon_atk', LIGHT_TYPES, LIGHT_MULT),
            ('heavy_weapon_atk', HEAVY_TYPES, HEAVY_MULT)):
        cfg = ctx.S.get(key) or {}
        mult = float(cfg.get('mult', default_mult))
        if not cfg.get('enabled', True) or mult == 1.0:
            continue
        for t in cfg.get('types') or default_types:
            t = int(t)
            prev = atk_by_type.get(t)
            if prev and prev[0] != key:
                raise RuntimeError('%s 和 %s 都包含武器类型 %d，请让轻 / 重武器类型互斥' % (prev[0], key, t))
            atk_by_type[t] = (key, mult)
    by_mult = {}
    for t, (_, mult) in atk_by_type.items():
        by_mult.setdefault(mult, []).append(t)
    for mult, types in sorted(by_mult.items()):
        L.append('wheavy\t%g\t%s' % (mult, ','.join(str(t) for t in sorted(types))))
    # 属性随机：welem <拆分元素占比下限 %> <上限 %> <拆分补偿系数> <纯元素倍率> <不抽的武器类型,…>（没有这一行 DLL 就不抽）
    we = ctx.S.get('weapon_element') or {}
    if we.get('enabled', True):
        lo, hi = we.get('split_share') or WELEM_SHARE
        L.append('welem\t%d\t%d\t%g\t%g\t%s' % (int(lo), int(hi), float(we.get('split_coef', WELEM_COEF)), float(we.get('pure_mult', WELEM_PURE)),
                                               ','.join(str(int(x)) for x in (we.get('skip_types') or WELEM_SKIP))))
    # 防具减伤倍率：pdef <r> <下限> <上限>（乘在本体八种减伤的百分比上）
    an = ctx.S.get('armor_negation') or {}
    if an.get('enabled', True):
        rg = an.get('range') or {}
        for r_i, r in enumerate(RAR):
            lo, hi = map(float, rg.get(r) or ARMOR_NEG[r])
            L.append('pdef\t%d\t%g\t%g' % (r_i, lo, hi))
            if overlimit.cfg(ctx.S):
                L.append('ovlp\t%d\t%g\t%g\t%g' % ((r_i,) + overlimit.caps(ctx.S, lo, hi, 'p')))
    # 法器倍率：cbase <r> <下限> <上限>（百分数，补正值 × 倍率 ÷ 100）；能施法的本体：wcast <本体> <魔法 0/1> <祷告 0/1>（cast_bases）
    if getattr(ctx, 'cast_range', None):
        for r_i, r in enumerate(RAR):
            L.append('cbase\t%d\t%g\t%g' % (r_i, *ctx.cast_range[r]))
        L += ['wcast\t%d\t%d\t%d' % x for x in ctx.cast_ids]
    # 盾牌随机：wguard <武器类型> <GUARD_F 序号> <原版同类盾的值,…>；wguard_q <r> <下分位> <上分位>
    sg = ctx.S.get('shield_guard_random') or {}
    if sg.get('enabled', True):
        W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
        wl = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamWeapon.xml')))[0]}
        g = lambda row, f: struct.unpack_from('<' + wl[f][1], row, wl[f][2])[0]
        sh = [int(t) for t in (sg.get('types') or SHIELD_TYPES)]
        vals = {t: [[] for _ in GUARD_F] for t in sh}
        for i, row in W.rows.items():
            t = g(row, 'wepType')
            if i < 100000000 and i % 10000 == 0 and t in vals:     # 原版本体（不算质变、我们的容器）
                for k, f in enumerate(GUARD_F):
                    vals[t][k].append(g(row, f))
        for t, vs in sorted(vals.items()):
            for k, v in enumerate(vs):
                if v:
                    L.append('wguard\t%d\t%d\t%s' % (t, k, ','.join('%g' % x for x in sorted(v))))
        q = sg.get('quantile') or {}
        for r_i, r in enumerate(RAR):
            lo, hi = map(float, q.get(r) or GUARD_Q[r])
            L.append('wguard_q\t%d\t%g\t%g' % (r_i, lo, hi))
        ctx.report.append('盾牌随机：%s 的五种属性减伤和防御强度在原版同类盾里按稀有度抽（分位 %s）' % (
            '、'.join('%d（%d 把）' % (t, len(vals[t][0])) for t in sh), ' / '.join('%g~%g' % tuple(q.get(r) or GUARD_Q[r]) for r in RAR)))
    for t, h in wt['skills'].items():
        h = {s: v for s, v in h.items() if s in wt['skill_info']}
        if h and n_w.get(int(t)):
            L.append('skill\t%s\t%s' % (t, pairs(h)))
    for t, h in wt['skill_default'].items():
        if n_w.get(int(t)):
            L.append('skill_def\t%s\t%s' % (t, pairs(h)))
    # 判定在共享层的专属战技（skillgems.free_skills）当成战灰写：DLL 不换行为变体，以前存的配方读档重建时也改回本体自己的
    free = getattr(ctx, 'free_skills', None) or set()
    for s, x in wt['skill_info'].items():
        zh, en = nm('zh', 'ArtsName', x['text_id']) or x['zh'], nm('en', 'ArtsName', x['text_id'])
        L.append('skillinfo\t%s\t%d\t%d\t%s\t%s' % (s, 1 if x['gem'] or int(s) in free else 0, x['native_var'] if x['native_var'] is not None else -1,
                                                     esc(zh), esc(en or zh)))
    # 专属战技：skillvar <战技> <原武器的行为变体> <只有战技判定的变体>（skill_vars）
    for s, (v, new) in sorted((getattr(ctx, 'skill_vars', None) or {}).items()):
        L.append('skillvar\t%d\t%d\t%d' % (s, v, new))
    # 防具：pslot <档> <部位:权重 …>（DLL 先按这个抽部位）
    def slot_odds(r):
        """各部位（有本体的）的权重：SLOT_EVEN 时一样多，不然照原包的件数"""
        h = {SLOTS.index(s): v for s, v in lib['armor']['slots'][r].items() if n_p.get(SLOTS.index(s))}
        return {s: 1000 for s in h} if SLOT_EVEN else h
    for r_i, r in enumerate(RAR):
        L.append('pslot\t%d\t%s' % (r_i, pairs(slot_odds(r))))
    cnt = lib['armor']['count']
    for r_i, r in enumerate(RAR):
        L.append('pcount\t%d\t%s' % (r_i, pairs(cnt[r])))
    share3 = float(lib['armor']['dlc_three_share'])                   # 传说（幽影之地）：三词条占这么多，其余照传说的一二词条比例
    leg = {k: v for k, v in cnt['Legendary'].items() if k != '3'}
    tot = float(sum(leg.values())) or 1.0
    L.append('pcount\t4\t%s' % pairs(dict({k: 10000 * (1 - share3) * v / tot for k, v in leg.items()}, **{'3': 10000 * share3})))
    # 防具词条按部位补偿（slot_balanced）：famw 的防具权重用补偿后的（部位几率同上面的 pslot 行）；词条库的权重只决定能不能出
    armor_w = defaultdict(lambda: [0] * len(RAR))
    spread = {True: [], False: []}
    for r_i, r in enumerate(RAR):
        ps = slot_odds(r)
        tot = float(sum(ps.values())) or 1.0
        ps = {s: v / tot for s, v in ps.items()}
        for mech in (True, False):
            ws, sp = slot_balanced([(key, f['weight_r']['armor'][r_i], f.get('slots', 15), (f.get('merge_group') or [key])[0])
                                    for key, f in lib['gear'].items() if 'weight_r' in f and is_mech(key, f) == mech], ps)
            for key, v in ws.items():
                armor_w[key][r_i] = v
            spread[mech].append(sp)
    ctx.report.append('防具词条按部位补偿（每条在所有防具上出现得一样多，变体组加起来算一条）：前缀位（机制类）各档最少 / 最多是平均的 %s；后缀位（数值类）%s' % tuple(
        '、'.join('%.2f / %.2f' % x for x in spread[m]) for m in (True, False)))
    # 护符 / 防具词条：fam <序号> <防具权重> <护符权重> <后缀中文> <后缀英文> <键> <能出的防具部位：头 1 / 身 2 / 手 4 / 腿 8> <1 = 机制类（名字里做前缀）>
    #   <合并组（变体组的键，- = 没有；同一件防具不出同组的两个）> <流派（extract_affixes.py ARCHETYPES 的分类，开发工具一键发放流派用）>；
    # famr <序号> <r> <效果> <护符模板> <说明中文> <说明英文>；famw <序号> <防具权重 普通,稀有,史诗,传说> <护符权重 …>；famtop <序号>（原版类型的数值词条里同名只认最好的那件）；
    # 词条数值随机的取值定义（val_lines）：famnum / famval / famtpl / famspan / famrow / famref / famfld；占位行 valpool <编号,…>
    # （护符：能出的每条一样、变体组算一条，见 extract_affixes.py merge_and_balance；防具：上面按部位补偿的；停用的词条族四档都是 0，留着给已有装备的记录查说明）
    for k, (key, f) in enumerate(lib['gear'].items()):
        L.append('fam\t%d\t%d\t%d\t%s\t%s\t%s\t%d\t%d\t%s\t%s' % (k, f['weight']['armor'], f['weight']['talisman'], esc(f['suffix'][1]), esc(f['suffix'][0]), key,
                                                                 f.get('slots', 15), 1 if is_mech(key, f) else 0, (f.get('merge_group') or ['-'])[0],
                                                                 esc(f.get('archetype') or '其他')))
        if 'weight_r' in f:
            L.append('famw\t%d\t%s\t%s' % (k, ','.join(map(str, armor_w[key])), ','.join(map(str, f['weight_r']['talisman']))))
        if f.get('stack') == 'top':                 # 同名只认最好的那件（extract_affixes.py STACK_TOP_NATIVE；dark_core gear/valfx.rs）
            L.append('famtop\t%d' % k)
        for r_i, r in enumerate(RAR):
            if r in f['sp']:
                # 触发词条的说明加一行「伤害随…提升」（rr/procs.py）
                L.append('famr\t%d\t%d\t%d\t%d\t%s\t%s' % (k, r_i, f['sp'][r], f['tal'].get(r, -1), esc(procs.annotate(ctx, key, 'zh', f['text'][r]['zh'])),
                                                          esc(procs.annotate(ctx, key, 'en', f['text'][r]['en']))))
        L += val_lines(ctx, k, f, key)
    if getattr(ctx, 'val_pool', None):
        L.append('valpool' + '\t' + ','.join(map(str, ctx.val_pool)))
    L += codex_lines(ctx, lib)
    # 强化（rr/upgrade.py）：rmax 最高等级、rmat 各稀有度的材料组、reinf <原版强化类型> <稀有度> <全能> <换成的强化类型>
    from . import upgrade
    L += upgrade.def_lines(ctx)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write('\n'.join(L) + '\n')
    os.replace(tmp, path)
    # 新词条里 DLL 做的（优雅、鸡尾酒）：runtime.txt，每行 <种类> <稀有度> <标记效果> <效果编号,…> <秒…>
    _hks, rt = runtime_parts(lib)
    # 返还（回收、无尽箭袋）要数的弹药：ammo <w 箭 / 弩箭 | g 投掷道具> <编号>
    rt += ['ammo\t%s\t%d' % x for x in getattr(ctx, 'ammo', [])]
    # 千钧认的 Boss：boss <NpcParam 编号>
    rt += ['boss\t%d' % i for i in getattr(ctx, 'boss_npcs', [])]
    # 发狂发作扣架势：madpoise <扣上限的 %>（rr/ailments.py）
    from . import ailments
    rt += ailments.runtime_lines(ctx)
    # 属性词条同稀有度叠加：attrdup <词条键> <稀有度 0~3> <效果编号> <副本编号,…>（attr_copies，dark_core attrstack.rs）
    rt += ['attrdup\t%s\t%d\t%d\t%s' % (k, r, sp, ','.join(map(str, c))) for k, r, sp, c in getattr(ctx, 'attr_dup', [])]
    # 战技伤害按稀有度：skillmult <稀有度 0~3> <效果编号> <倍率>（skill_mults，dark_core skillmult.rs）
    rt += ['skillmult\t%d\t%d\t%g' % x for x in getattr(ctx, 'skill_mult', [])]
    # 被命中标记顶掉的命中时触发：atkfwd <玩家身上的效果> <补挂的副本> <wepParamChange>（rr/atkfwd.py，dark_core rules.rs）
    rt += getattr(ctx, 'atkfwd', [])
    with open(os.path.join(os.path.dirname(path), 'runtime.txt'), 'w', encoding='utf-8', newline='\n') as fp:
        fp.write('# 新词条里 dll\\dark_core 做的（rr/affixes.py write_def 写，每次重随自动生成，不要手改）：'
                 '种类、稀有度 0~3、标记效果、效果编号（逗号分隔）、秒数（优雅：满几秒、持续几秒；鸡尾酒：间隔）\n' + '\n'.join(rt) + '\n')
    ctx.report.append('词条库给 dark_core：本体武器 %d 把（%d 种类型）、防具 %d 件；护符 / 防具词条 %d 种 → %s' % (
        sum(n_w.values()), len(n_w), sum(n_p.values()), len(lib['gear']), os.path.basename(path)))


def verify(bnd, patched=None):
    """写出去的 regulation 读回来后核对：词条库的行都在、内容一样。
    patched：后面的步骤有意改过的词条库行 {(参数表, 编号): 改后的内容}（发狂 / 咒死重做 rr/ailments.py），按改后的比"""
    patched = patched or {}
    data = json.load(open(os.path.join(HERE, 'data', ROWS), encoding='utf-8'))
    data.pop('_row_size')
    for p, rows in data.items():
        P = erlib.Param(bnd.get(p + '.param'))
        bad = [k for k, hx in rows.items() if bytes(P.rows.get(int(k), b'')) != patched.get((p, int(k)), bytes.fromhex(hx))]
        if bad:
            raise RuntimeError('校验失败：%s 里词条库的 %d 行没写进去或不一样（%s）' % (p, len(bad), bad[:5]))
