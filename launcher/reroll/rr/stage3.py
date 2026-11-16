# -*- coding: utf-8 -*-
"""开了敌人随机时：被挪到别处的敌人按新位置的档次掉落（复制敌人参数 + 修补地图）。"""
from .common import *  # noqa: F401,F403


def diste(rand_dir, *p):
    """随机器自带的数据（diste）。高难度世界（randomizer_hi，dev\\boss_mods\\README.md）里没有：E: 这种 exFAT 盘建不了目录联接，
    就用旁边平常的随机器目录里的那份"""
    d = os.path.join(rand_dir, 'diste')
    if not os.path.isdir(d):
        alt = os.path.join(os.path.dirname(os.path.abspath(rand_dir)), 'randomizer', 'diste')
        if os.path.isdir(alt):
            d = alt
    return os.path.join(d, *p)

def known_enemies(rand_dir):
    """随机器 enemy.txt 里所有原版敌人的编号（随机器输出地图里的实体编号和它一致；不在里面的是随机器为 Boss 随从新加的）"""
    import re
    t = open(diste(rand_dir, 'Base', 'enemy.txt'), encoding='utf-8').read()
    return {int(x) for x in re.findall(r'^- ID: (\d+)$', t, re.M)}


def enemy_positions(rand_dir):
    """随机器 enemy.txt：{敌人编号: (原版地图, 部件名)}。原版里实体编号是 0 的敌人，随机器也给了编号，只能按部件名对回原版。
    大图块（m60_12_13_02 这类 _02）上的部件名本身就是「小图块-部件名」（m60_48_55_00-c4300_9004），原样用：
    以前拆成（小图块, 部件名）去找，全都对不上（193 个，雪原商队马车的护卫这些没吃到血量补正，用户 2026-11-04 发现）"""
    import re
    t = open(diste(rand_dir, 'Base', 'enemy.txt'), encoding='utf-8').read()
    return {int(i): (mp, nm) for i, mp, nm in re.findall(r'^- ID: (\d+)\n  Map: (\S+)\n  Name: (\S+)$', t, re.M)}


# 不开敌人随机时要的原版敌人数据（原版地图上的敌人、入侵 NPC、多阶段 Boss），随整合包发：dev\tools\make_vanilla_enemies.py
# 用随机器自带的 diste 算好写进去。没装随机器（正式发布不带，dev\release\第三方分离.md）时读这份，结果和装了一样
SHIPPED = os.path.join(HERE, 'data', 'vanilla_enemies.json')
_shipped_cache = []


def shipped():
    if not _shipped_cache:
        try:
            _shipped_cache.append(json.load(open(SHIPPED, encoding='utf-8')))
        except (OSError, ValueError):
            _shipped_cache.append({})
    return _shipped_cache[0]


def hostile_npcs(rand_dir):
    """随机器 enemy.txt 里 Class: HostileNPC 的敌人编号：入侵的 NPC（褪色者、血指、蕾妲一伙……，原版 54 个）；没装随机器读 SHIPPED"""
    import re
    try:
        t = open(diste(rand_dir, 'Base', 'enemy.txt'), encoding='utf-8').read()
    except OSError:
        return set(shipped().get('hostile', []))
    return {int(i) for i in re.findall(r'^- ID: (\d+)\n  Map: \S+\n  Name: \S+\n  Class: HostileNPC$', t, re.M)}


def next_phases(rand_dir):
    """多阶段 Boss：随机器 enemy.txt 的 NextPhase [(实体, 下一阶段)]；没装随机器读 SHIPPED"""
    import re
    try:
        t = open(diste(rand_dir, 'Base', 'enemy.txt'), encoding='utf-8').read()
    except OSError:
        return [tuple(x) for x in shipped().get('next_phase', [])]
    return [(int(a), int(b)) for a, b in re.findall(r'^- ID: (\d+)\n(?:  [^\n]*\n)*?  NextPhase: (\d+)', t, re.M)]


def boss_tiers(rand_dir, data_dir):
    """Boss 位置的流程等级：data/boss_lots.json（整合包按地区整理的，和 tier_bands 的地区名对得上）；
    多阶段 Boss 的另一个阶段跟着它（随机器 enemy.txt 的 NextPhase）。{实体: 流程等级}"""
    import re
    bt = {b['entity']: b['tier'] for b in json.load(open(os.path.join(data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses']}
    for a, b in next_phases(rand_dir):
        if a in bt and b not in bt:
            bt[b] = bt[a]
        elif b in bt and a not in bt:
            bt[a] = bt[b]
    return bt


def boss_rule_mults(rules, bt, rem_ents):
    """enemy_hp_band.boss_rules（用户 2026-11-02：利耶尼亚除追忆外 Boss 血量 ×0.8）→ {Boss 位置的实体: 倍数}，几条规则都管到的相乘。
    一条规则 {"tiers": [流程等级], "include": [实体], "exclude": [实体], "mult": 倍数, "except_remembrance": true}：
    bt（boss_tiers）里等级在 tiers 的位置 + include − exclude，except_remembrance 时去掉追忆 Boss 的位置（rem_ents）"""
    out = {}
    for r in rules or ():
        k = float(r.get('mult', 1.0))
        tiers = {int(t) for t in r.get('tiers') or ()}
        ents = {e for e, t in bt.items() if t in tiers} | {int(e) for e in r.get('include') or ()}
        ents -= {int(e) for e in r.get('exclude') or ()}
        if r.get('except_remembrance', True):
            ents -= rem_ents
        for e in ents:
            out[e] = out.get(e, 1.0) * k
    return out


def vanilla_parts(rand_dir, cache_dir):
    """原版地图（随机器自带的 diste\\Vanilla）里的敌人：{地图文件: [[实体, 敌人参数]]}；没装随机器读 SHIPPED"""
    vfiles = sorted(glob.glob(diste(rand_dir, 'Vanilla', '*.msb.dcx')))
    if not vfiles:
        return shipped().get('parts', {})
    os.makedirs(cache_dir, exist_ok=True)
    return _cached(os.path.join(cache_dir, 'stage3_vanilla.json'), _files_sig(vfiles),
                   lambda: dict(zip(map(os.path.basename, vfiles), erlib.pmap(_job_parts_en, vfiles, chunksize=8))))


def boss_npc_tiers(rand_dir, cache_dir, bt):
    """没开敌人随机时：原版地图上 Boss 位置放的敌人参数 → 那个位置的流程等级（同一行参数放在几处时取最低的）"""
    out = {}
    for plist in vanilla_parts(rand_dir, cache_dir).values():
        for e, n in plist:
            if e in bt:
                out[n] = min(out.get(n, 99), bt[e])
    return out


def msb_parts_named(raw):
    """MSB 里的敌人部件：[[部件名, 实体编号, 敌人参数]]（erlib.msb_enemy_parts 不带名字）"""
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
                out.append([name, struct.unpack_from('<I', raw, o + ptrs[2])[0], struct.unpack_from('<i', raw, o + ptrs[3] + 12)[0]])
            return out
        pos = nxt
    return out


def _job_parts(f):
    return erlib.msb_enemy_parts(erlib.dcx_decompress(open(f, 'rb').read()))


def _job_parts_en(f):
    return [[e, n] for e, n, _ in _job_parts(f)]


def _job_parts_named(f):
    return msb_parts_named(erlib.dcx_decompress(open(f, 'rb').read()))


def _job_scale_calls(f):
    """一个事件文件里所有「挂特殊效果」的调用（2000, 6）：[(公共事件, 实体, 效果)]"""
    import emevd
    out = []
    for ev in emevd.read(erlib.dcx_decompress(open(f, 'rb').read()))['events']:
        for i in ev['ins']:
            if (i['bank'], i['id']) == (2000, 6) and len(i['args']) >= 16:
                _slot, eid, ent, sp = struct.unpack_from('<iiii', i['args'], 0)
                out.append((eid, ent, sp))
    return out


def _job_patch_map(job):
    """修补一张地图里敌人的参数引用，按游戏的方式读回自检后写出"""
    src, dst, edits, n_parts = job
    raw = bytearray(erlib.dcx_decompress(open(src, 'rb').read()))
    for off, old, new in edits:
        if struct.unpack_from('<i', raw, off)[0] != old:
            raise RuntimeError('地图 %s 偏移 %d 的内容和缓存不符' % (os.path.basename(src), off))
        struct.pack_into('<i', raw, off, new)
    data = erlib.dcx_compress_dflt(bytes(raw), level=6)
    if len(erlib.msb_enemy_parts(erlib.dcx_check_strict(data))) != n_parts:
        raise RuntimeError('地图 %s 写回后自检失败' % os.path.basename(src))
    tmp = dst + '.tmp'
    open(tmp, 'wb').write(data)
    os.replace(tmp, dst)
    return os.path.basename(dst)


def scale_calls(efiles):
    """所有事件文件里的挂效果调用（并行读）"""
    return [c for lst in erlib.pmap(_job_scale_calls, efiles) for c in lst]


ADDED = range(4000000, 5000000)             # 随机器为 Boss 随从新加进地图的敌人用的实体编号段
# 原版第一次兰斯克斯遭遇（m60_37_51_00）是“打到 60% 后逃跑”的特殊实例，死亡事件不发奖。
# 随机器把它换成可击杀 Boss 时，必须给这个位置复制独立 NPC 参数，不能改共享的 45102030。
FORCE_COPY_IF_REPLACED = {1037510800: 45102030}
# 部件实体数据块里 8 个分组编号（EntityGroupIDs）的位置：+0x1C（SoulsFormats MSBE ReadEntityData；原版 m14_00 蕾娜菈战的部件核对过）。
# 2026-11-10 以前写成 0x14：随从没编进分组，反而把 +0x14~0x17 的几个渲染布尔位写成了分组编号（SoulsFormats 读这些图报
# 「ReadBoolean encountered non-boolean value」，斗技场试炼改王城灰城地图时查出来的）
GROUP_AT = 0x1C


def _job_helper_groups(job):
    """漏编组的 Boss 随从：随机器把 Boss 连随从搬进别的场地时，给随从新编了一个分组（Boss 被打倒时「强制死亡」、
    读图时 Boss 已死就「禁用」都按这个分组做），但有的随从没编进去（比如蕾娜菈的 c0100 假人），Boss 死后它一直留在场地里；
    它是敌对的，旁边的赐福就坐下又起身、不能休息。
    认法：随机器新加的、没有任何分组的敌人 E；地图事件 0 里有初始化调用同时带 E 和地图上的实体 B（Boss），
    B 又和某个随从分组 G 出现在同一个调用里，而且 G 是事件里「强制死亡」的对象 → 把 E 编进 G。
    返回 [[分组位置的偏移, G, E]]"""
    import emevd
    msb_p, ev_p = job
    raw = erlib.dcx_decompress(open(msb_p, 'rb').read())
    ents, added = set(), {}
    pos = 0x10
    while pos:
        cnt = struct.unpack_from('<i', raw, pos + 4)[0]
        noff = struct.unpack_from('<q', raw, pos + 8)[0]
        offs = struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16)
        nxt = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
        if erlib._u16str(raw, noff) == 'PARTS_PARAM_ST':
            for o in offs:
                at = o + struct.unpack_from('<11q', raw, o + 0x50)[2]
                ent = struct.unpack_from('<I', raw, at)[0]
                ents.add(ent)
                if struct.unpack_from('<i', raw, o + 12)[0] == 2 and ent in ADDED:
                    added[ent] = (at, struct.unpack_from('<8I', raw, at + GROUP_AT))
            break
        pos = nxt
    groups = {g for _at, gs in added.values() for g in gs if g}
    lonely = [e for e, (_at, gs) in sorted(added.items()) if not any(gs)]
    if not lonely or not groups:
        return []
    killed, calls = set(), []
    for ev in emevd.read(erlib.dcx_decompress(open(ev_p, 'rb').read()))['events']:
        for i in ev['ins']:
            a = bytes(i['args'])
            if (i['bank'], i['id']) == (2004, 4):                     # 强制死亡
                killed.add(struct.unpack_from('<I', a, 0)[0])
            elif ev['id'] == 0 and (i['bank'], i['id']) in ((2000, 0), (2000, 6)):
                calls.append({struct.unpack_from('<I', a, o)[0] for o in range(8, len(a) - len(a) % 4, 4)})
    out = []
    for e in lonely:
        bosses = {v for c in calls if e in c for v in c if v != e and v in ents}
        gs = sorted({g for c in calls if bosses & c for g in c if g in groups and g in killed})
        at, slots = added[e]
        free = [k for k in range(8) if not slots[k]]
        out += [[at + GROUP_AT + 4 * k, g, e] for k, g in zip(free, gs)]
    return out


NPC_HP = 36
NPC_SCALE = 88                              # spEffectID3：区域强度（7000 + 10 × 流程等级；DLC 20007000 + …）
NPC_SPEFFECTS = tuple(range(76, 108, 4)) + tuple(range(376, 408, 4)) + tuple(range(488, 552, 4))
SCALE_EVENT = 9005890                       # 随机器给每个敌人挂缩放效果用的公共事件（实体, 效果）：等敌人加载进场景再挂
# 随机器给 Boss、事件里才出现的敌人挂缩放效果用的公共事件（实体, 效果）：一开始就挂、每秒重挂。这些敌人多半先被事件禁用、
# 遭遇时才启用，禁用期间挂上的血量上限倍率不会按比例补当前血量 → 放大的敌人出场不满血（比如落叶丹恩的位置约 70%）
SCALE_EVENT_NOW = 9005891


def _cached(path, sig, build):
    try:
        c = json.load(open(path, encoding='utf-8'))
        if c.get('sig') == sig:
            return c['data']
    except Exception:
        pass
    data = build()
    open(path, 'w', encoding='utf-8').write(json.dumps({'sig': sig, 'data': data}))
    return data


def _files_sig(files):
    return '%d|%d|%d' % (len(files), sum(os.path.getsize(f) for f in files), int(max(os.path.getmtime(f) for f in files))) if files else '0'


def scale_now_effects(rand_dir, maps_out, P_sp):
    """随机器用 SCALE_EVENT_NOW 挂的缩放效果里会改血量上限的：{实体: (效果, ...)}（按随机器的事件文件缓存）"""
    efiles = sorted(glob.glob(os.path.join(rand_dir, 'event', '*.emevd.dcx')))

    def build():
        out = defaultdict(list)
        for eid, ent, sp in scale_calls(efiles):
            if eid == SCALE_EVENT_NOW and sp > 0 and sp not in out[str(ent)]:
                out[str(ent)].append(sp)
        return out
    raw = _cached(os.path.join(maps_out, 'stage3_scale_now.json'), _files_sig(efiles), build)
    hp_sp = {sp for v in raw.values() for sp in v
             if sp in P_sp.rows and abs(struct.unpack_from('<f', P_sp.rows[sp], 16)[0] - 1.0) > 1e-6}
    return {int(e): tuple(sp for sp in v if sp in hp_sp) for e, v in raw.items() if any(sp in hp_sp for sp in v)}


def boss_targets(rows, boss_mult, blend, base_hp, mult, items_out=None):
    """敌人随机后 Boss 位置的血量（enemy_hp_band.boss + boss_blend）。
    原来直接按「原版这个位置的 Boss 血量 × 档倍数」定：脆皮 Boss 换到血牛的位置（或反过来）就很抽象——
    菲雅的勇士们放到溃烂树灵的位置每个 2.2 万血，乳腐龙放到腐败化身的位置只有 1.1 万。现在加权：
      肉度 T = 实际血量 ÷ 这一档原版 Boss 位置血量的中位数（> 1 血牛、< 1 脆皮）；
      目标 = 档中位数 × T自身^own × T位置^(1-own) × 档倍数，T自身夹在 [min, max]（巨龙之类的血牛别翻太多倍）；
      neutral_entities（拉卡德两个阶段：血量是按弑神者之剑的特攻定的）的肉度当 1；
      normalize：每档放进来的 Boss 目标血量总和缩放到「档中位数 × T位置 × 档倍数」的总和，地区整体血量和以前一样。
    放进来的 Boss 原版不在任何 Boss 位置（对不上自身肉度）时照旧按位置定。
    rows = [(地图, 偏移, 实体, 原版 Boss, 放进来的 Boss, 档, 总倍率)]；返回（{地图: {偏移: ('=', 参数血量)}}, 报告文字）；
    items_out = [] 时填上 [(实体, 原版 Boss, 放进来的 Boss, 档, 定下来的实际血量)]（高难度血量补正 rr/hpunify.py 用）"""
    import statistics
    if not boss_mult or not rows:
        return {}, ''
    w = min(1.0, max(0.0, float(blend.get('own', 0.7))))
    lo, hi = float(blend.get('min', 0.25)), float(blend.get('max', 3.0))
    neutral_ent = set(blend.get('neutral_entities') or ())
    neutral = {nv for _n, _o, ent, nv, _p, _b, _m in rows if ent in neutral_ent}
    actual = lambda nid: base_hp(nid) * mult(nid)
    by_b = defaultdict(list)
    for _n, _o, ent, nv, _p, b, _m in rows:
        if nv not in neutral:
            by_b[b].append(actual(nv))
    med = {b: statistics.median(v) for b, v in by_b.items()}
    own_band = {}
    for _n, _o, _e, nv, _p, b, _m in rows:
        own_band[nv] = min(own_band.get(nv, 99), b)

    def tness(nid, band):
        return 1.0 if nid in neutral else actual(nid) / med[band]

    items, n_keep = [], 0
    for row in rows:
        name, off, ent, nv, npc, b, mr = row
        m = float(boss_mult[min(b, len(boss_mult) - 1)])
        if b not in med:
            base = tgt = actual(nv) * m
        else:
            base = med[b] * tness(nv, b) * m
            ob = own_band.get(npc)
            if ob is None or ob not in med or w <= 0:
                tgt = base
                n_keep += 1
            else:
                t_own = min(hi, max(lo, tness(npc, ob)))
                tgt = med[b] * t_own ** w * tness(nv, b) ** (1 - w) * m
        items.append([row, base, tgt])
    if blend.get('normalize', True):
        tot = defaultdict(lambda: [0.0, 0.0])
        for row, base, tgt in items:
            tot[row[5]][0] += base
            tot[row[5]][1] += tgt
        for it in items:
            s = tot[it[0][5]]
            it[2] *= s[0] / s[1] if s[1] > 0 else 1.0
    # 极值：最后夹在「档中位数 × 档倍数」的 cap_min ~ cap_max 倍之间（档倍数、肉度加权都不动，只管两头离群的：
    # 血牛 Boss 换到血牛位置 2.7 倍、脆皮换到脆皮位置 0.1 倍这种）
    cap_lo, cap_hi = float(blend.get('cap_min', 0) or 0), float(blend.get('cap_max', 0) or 0)
    n_cap = Counter()
    for it in items:
        b = it[0][5]
        if b not in med:
            continue
        ref = med[b] * float(boss_mult[min(b, len(boss_mult) - 1)])
        if cap_hi > 0 and it[2] > cap_hi * ref:
            it[2] = cap_hi * ref
            n_cap['hi'] += 1
        elif cap_lo > 0 and it[2] < cap_lo * ref:
            it[2] = cap_lo * ref
            n_cap['lo'] += 1
    # 按位置夹（pos_min ~ pos_max，用户 2026-11-01：混合肉度的极端值）：再夹在「这个位置原版 Boss 的血量 × 档倍数」（base，
    # 完全照位置的血量）的这么多倍之间，「现在 ÷ 原版」不会离档倍数太远（菲雅的勇士位置放铃珠猎人 ×12、葛瑞克位置放蕾娜菈一阶段 ×0.46 这种）
    pos_lo, pos_hi = float(blend.get('pos_min', 0) or 0), float(blend.get('pos_max', 0) or 0)
    for it in items:
        if pos_hi > 0 and it[2] > pos_hi * it[1]:
            it[2] = pos_hi * it[1]
            n_cap['pos_hi'] += 1
        elif pos_lo > 0 and it[2] < pos_lo * it[1]:
            it[2] = pos_lo * it[1]
            n_cap['pos_lo'] += 1
    # 按位置再乘（pos_mult：{位置的实体编号: 倍数}，用户 2026-11-02：葛瑞克位置 ×2，前期档中位数低，上面的夹限把这里压到 3000~4000）
    pos_mult = {int(k): float(v) for k, v in (blend.get('pos_mult') or {}).items()}
    n_pm = 0
    for it in items:
        k = pos_mult.get(it[0][2])
        if k:
            it[2] *= k
            n_pm += 1
    out, n = {}, Counter()
    for (name, off, ent, nv, npc, b, mr), base, tgt in items:
        new = max(1, int(round(tgt / max(mr, 1e-6))))
        out.setdefault(name, {})[off] = ('=', new)
        if items_out is not None:
            items_out.append((ent, nv, npc, b, new * mr))
        n['down' if new < base_hp(npc) else 'up' if new > base_hp(npc) else 'same'] += 1
    msg = ('；Boss 位置 %d 处：档中位数 × 自身肉度^%g × 位置肉度^%g × %s（自身肉度夹在 %g~%g%s%s%s%s；调低 %d、调高 %d%s）' % (
        len(items), w, 1 - w, ' / '.join('%g' % float(x) for x in boss_mult), lo, hi,
        '，每档总量归一' if blend.get('normalize', True) else '', '，%d 个阶段肉度按 1' % len(neutral) if neutral else '',
        '，最后夹在档中位数 × 档倍数的 %g~%g 倍（压低 %d、抬高 %d）' % (cap_lo, cap_hi, n_cap['hi'], n_cap['lo']) if cap_lo or cap_hi else '',
        '，再夹在这个位置原版血量 × 档倍数的 %g~%g 倍（压低 %d、抬高 %d）' % (pos_lo, pos_hi, n_cap['pos_hi'], n_cap['pos_lo'])
        if pos_lo or pos_hi else '',
        n['down'], n['up'], ('，%d 处对不上原来的位置照旧按位置定' % n_keep if n_keep else '') +
        ('，%d 处按位置再乘（%s）' % (n_pm, '、'.join('%d ×%g' % kv for kv in sorted(pos_mult.items()))) if pos_mult else '')))
    return out, msg


# 不在 Boss 分档表、地图也不在流程等级表里的 Boss 位置：{实体: 流程等级（随机器日志没有这个位置的强度时用）}。放进来的敌人参数可能被归成普通敌人，也照 Boss 算（用户 2026-11-09：祖灵）
FORCE_BOSS_POS = {12080800: 6}
HUMAN_ROW_MIN = 500000000                       # 人形 NPC（c0000）的敌人参数：九位数 5 开头，NpcParam.hp 不起作用，血量看 CharaInitParam 的生命力和身上的效果
HP_RATE_BASE, HP_RATE_ZERO, HP_RATE_STEP = 7307100, 200, 1.03   # 按需建的血量上限效果：编号 = 基数 + 零点 + 档，倍率 = 步长 ^ 档


def player_hp(v):
    """玩家的血量公式（人形 NPC 的基础血量；日志核对过：生命力 2 → 304，28 → 911）"""
    if v < 25:
        return 300 + 500 * ((v - 1) / 24) ** 1.5
    if v < 40:
        return 800 + 650 * ((v - 25) / 15) ** 1.1
    if v < 60:
        return 1450 + 450 * (1 - (1 - (v - 40) / 20) ** 1.2)
    return 1900 + 200 * (1 - (1 - (v - 60) / 39) ** 1.2)


def hp_rate_rows(P_sp, data_dir):
    """返回 get(倍率) → 血量上限效果的编号（最接近的一档，用到才建）"""
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(data_dir, 'SpEffect.xml')))[0]}
    put = lambda row, f, v: struct.unpack_from and struct.pack_into('<' + lay[f][1], row, lay[f][2], v)
    made = set()

    def get(k):
        i = max(-HP_RATE_ZERO, min(HP_RATE_ZERO, int(round(math.log(max(k, 1e-6)) / math.log(HP_RATE_STEP)))))
        rid = HP_RATE_BASE + HP_RATE_ZERO + i
        if rid not in made:
            if rid in P_sp.rows:
                raise RuntimeError('血量上限效果的编号 %d 已经有人用了' % rid)
            row = bytearray(P_sp.rows[INV_SP_TEMPLATE])
            o, bit = lay['disableCurse'][2], lay['disableCurse'][3]
            row[o] &= ~(1 << bit)
            put(row, 'iconId', -1)
            put(row, 'effectEndurance', -1.0)
            put(row, 'maxHpRate', HP_RATE_STEP ** i)
            put(row, 'spCategory', 0)
            P_sp.add_row(rid, bytes(row))
            made.add(rid)
        return rid
    return get


def link_main(mains, groups, e):
    """同一张图有几个 Boss 时，这个搭档 / 血条代理是谁的：分组有交集的，没有就取地图位置最近的（60 米内）；对不上返回 None"""
    if e not in groups:
        return None
    gs, pos = groups[e]
    hit = next((r for r in mains if r[2] in groups and gs & groups[r[2]][0]), None)
    if hit is not None:
        return hit
    near = [(sum((a - b) ** 2 for a, b in zip(pos, groups[r[2]][1])), r[1], r) for r in mains if r[2] in groups]
    near = [x for x in near if x[0] <= 3600]
    return min(near)[2] if near else None


def _bar_tmpl(e):
    """{事件: [(指令里写的实体, 实体从第几个字节的初始化参数来；写死的是 None)]}：只看「显示 Boss 血条」"""
    out = {}
    for ev in e['events']:
        for k, i in enumerate(ev['ins']):
            a = bytes(i['args'])
            if (i['bank'], i['id']) == (2003, 11) and a[0] == 1:
                src = [p[2] for p in ev.get('params') or () if p[0] == k and p[1] == 4]
                out.setdefault(ev['id'], []).append((struct.unpack_from('<I', a, 4)[0], src[0] if src else None))
    return out


def _job_bars(job):
    """一张图的事件里显示血条的、随机器新加的实体（双 Boss 的搭档、共用的血条代理）"""
    import emevd
    f, common = job
    e = emevd.read(erlib.dcx_decompress(open(f, 'rb').read()))
    local = _bar_tmpl(e)
    out = {lit for lst in local.values() for lit, src in lst if src is None}
    for ev in e['events']:
        for i in ev['ins']:
            if (i['bank'], i['id']) in ((2000, 0), (2000, 6)):
                a = bytes(i['args'])
                eid = struct.unpack_from('<I', a, 4)[0]
                for _lit, src in local.get(eid, []) + list(common.get(eid, [])):
                    if src is not None and 12 + src <= len(a):
                        out.add(struct.unpack_from('<I', a, 8 + src)[0])
    return sorted(x for x in out if x in ADDED)


def _msb_groups(path):
    """{实体: (它的分组集合, 地图位置)}"""
    raw = erlib.dcx_decompress(open(path, 'rb').read())
    pos, out = 0x10, {}
    while pos:
        cnt = struct.unpack_from('<i', raw, pos + 4)[0]
        noff = struct.unpack_from('<q', raw, pos + 8)[0]
        offs = struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16)
        nxt = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
        if erlib._u16str(raw, noff) == 'PARTS_PARAM_ST':
            for o in offs:
                if struct.unpack_from('<i', raw, o + 12)[0] == 2:
                    at = o + struct.unpack_from('<11q', raw, o + 0x50)[2]
                    out[struct.unpack_from('<I', raw, at)[0]] = ({g for g in struct.unpack_from('<8I', raw, at + GROUP_AT) if g}, struct.unpack_from('<3f', raw, o + 0x20))
            break
        pos = nxt
    return out


# 幽影树化身的敌人参数（编号 ÷ 100）：第三阶段本体；三个血条代理；一、二阶段的身体
AVATAR_MAIN, AVATAR_BARS, AVATAR_BODIES = 523003, (523001, 523004, 523005), (523000, 523002)


def hp_align_factors(rand_dir, maps_out, parts, P_npc, hp, tgt=None, now_sp=None):
    """按地区给敌人随机后的血量加固定值（enemy_hp_align）：同一批位置（原版地图里放普通敌人的位置）上统计实际血量的中位数，
    以第一个地区（前期）为基准：前期比值 r0 = 随机后中位 ÷ 原版中位；后面每个地区的目标 = 原版中位 × r0，
    补正 = 目标 − 随机后中位（只加不减，前期不动）。加固定值而不是乘倍数：低基础血量的敌人被放到后期地区也能被拉上去。
    实际血量 = 敌人参数 hp × 各特殊效果格的血量倍率 ×（随机后）随机器运行时挂的缩放效果，所以每个位置加到参数 hp 上的是
    补正 ÷ 这个位置的总倍率（取整到 step）。返回（{地图文件: {偏移: 加到 hp 上的值}}, 报告文字）"""
    opts = hp.get('opts') or {}
    P_sp, cls, map_tiers, band_idx, bands = hp['P_sp'], hp['cls'], hp['map_tiers'], hp['band_idx'], hp['bands']
    import statistics
    vdir = diste(rand_dir, 'Vanilla')
    vfiles = sorted(glob.glob(os.path.join(vdir, '*.msb.dcx')))
    van = _cached(os.path.join(maps_out, 'stage3_vanilla.json'), _files_sig(vfiles),
                  lambda: dict(zip(map(os.path.basename, vfiles), erlib.pmap(_job_parts_en, vfiles, chunksize=8))))
    # 原版实体编号是 0 的位置：随机器给的编号 → enemy.txt 的（地图, 部件名）→ 原版那个部件放的敌人
    vnamed = _cached(os.path.join(maps_out, 'stage3_vanilla_named.json'), _files_sig(vfiles),
                     lambda: dict(zip(map(os.path.basename, vfiles), erlib.pmap(_job_parts_named, vfiles, chunksize=8))))
    by_name = {(fn[:-len('.msb.dcx')], pn): n for fn, lst in vnamed.items() for pn, _e, n in lst}
    eid_pos = enemy_positions(rand_dir)
    efiles = sorted(glob.glob(os.path.join(rand_dir, 'event', '*.emevd.dcx')))

    def build_scale():
        # 一个实体可能挂好几个缩放效果（比如真正的缩放 + 两个 ×1 的 90000 / 90010），全记下来，倍率连乘
        out = defaultdict(list)
        for eid, ent, sp in scale_calls(efiles):
            if eid == SCALE_EVENT and sp > 0 and sp not in out[str(ent)]:
                out[str(ent)].append(sp)
        return out
    scale = _cached(os.path.join(maps_out, 'stage3_scale_all.json'), _files_sig(efiles), build_scale)

    def rate(sid):
        r = P_sp.rows.get(sid)
        return (struct.unpack_from('<f', r, 16)[0] or 1.0) if r is not None else 1.0

    def scale_rate(ent):
        m = 1.0
        for sid in scale.get(str(ent), ()):
            m *= rate(sid)
        return m

    def now_only(ent, npc):
        """随机器出场就挂的缩放（now_sp，stage3_retier 会写进这个位置复制出来的参数）里，参数行自己没有、「全部缩放」（scale）里也没记的：
        这些也算在实际血量里，不算的话加血量要除的倍率偏小、加多了（用户 2026-11-13 查出：随机器新加的 Boss 随从全靠它缩放，加了约 10 倍；
        原版普通敌人的位置也有 42 个，平均多了约 4 成）。Boss 那边（boss_rows）一直有算"""
        have = {struct.unpack_from('<i', P_npc.rows[npc], o)[0] for o in NPC_SPEFFECTS}
        sc = set(scale.get(str(ent), ()))
        return tuple(sp for sp in (now_sp or {}).get(ent, ()) if sp not in have and sp not in sc)

    def pos_rate(ent, npc):
        """这个位置的总倍率：参数行的效果 × 运行时缩放 × 出场就挂、别处没记的缩放"""
        m = mult(npc) * scale_rate(ent)
        for sp in now_only(ent, npc):
            m *= rate(sp)
        return m

    def npc_info(ent, npc):
        """hpunify 要的（参数, 缩放效果）：缩放连同出场就挂、别处没记的"""
        return (npc, tuple(scale.get(str(ent), ())) + now_only(ent, npc))

    def area_tier(ent, nv, m):
        """这个位置的强度：随机器日志里的目标强度（scaling a->b 的 b）> 原版放在这里的敌人的区域强度 > 地图的流程等级。
        同一个地图文件里可能有不同强度的区域（关卡前方的求学洞窟是 1，同一张图里的边境英雄墓是 6）"""
        t = (tgt or {}).get(ent)
        if t is None:
            s = struct.unpack_from('<i', P_npc.rows[nv], NPC_SCALE)[0]
            if 7000 <= s <= 7200 and s % 10 == 0:
                t = max(1, (s - 7000) // 10)
            elif 20007000 <= s < 20007400 and s % 10 == 0:
                t = min(33, 21 + ((s - 20007000) % 200) // 10)
        return t if t is not None else map_tiers[m]

    def area_band(ent, nv, m):
        return band_idx(area_tier(ent, nv, m))

    def mult(nid):
        row = P_npc.rows.get(nid)
        if row is None:
            return None
        m = 1.0
        for o in NPC_SPEFFECTS:
            sid = struct.unpack_from('<i', row, o)[0]
            if sid > 0:
                m *= rate(sid)
        return m

    def base_hp(nid):
        return struct.unpack_from('<I', P_npc.rows[nid], NPC_HP)[0]

    hv_b, hr_b = defaultdict(list), defaultdict(list)
    pos = defaultdict(list)                  # 地区 -> [(地图, 偏移, 这个位置的总倍率)]
    hr_t, pos_t = defaultdict(list), defaultdict(list)   # 按强度（enemy_hp_band.curve）：随机后的实际血量、位置
    # Boss 位置（enemy_hp_band.boss）：放在这里的 Boss 实际血量直接定（可加可减），见下面 boss_rows 之后。
    # 倍率算上随机器运行时挂的缩放和写进参数的出场缩放
    boss_mult = hp.get('boss_mult') or []
    boss_rows = []                           # [(地图, 偏移, 实体, 原版 Boss, 放进来的 Boss, 档, 总倍率)]
    n_small = 0                              # 原版小动物的位置放了普通敌人（只加血，不进中位数统计）
    # 入侵的 NPC（随机器的 HostileNPC 位置）：实际血量 × 这个位置那一档 Boss 的倍数（enemy_hp_band.invader_as_boss，用户 2026-11-01）。
    # 人形 NPC 的血量按 CharaInitParam 的生命力算，NpcParam.hp 不起作用（2026-11-09 查出来的），所以挂血量上限效果（invader_sp_rows）
    inv_mult = hp.get('invader_mult') or []
    inv_sp = hp.get('invader_sp') or []
    hostile = hostile_npcs(rand_dir) if inv_mult else set()
    inv_pos, inv_by = {}, defaultdict(int)   # {(地图, 偏移): 效果}（stage3_retier 写进复制出来的参数行）、档 → 处数
    hp['inv_pos'] = inv_pos
    # 高难度血量补正（rr/hpunify.py）要的：hp['unify'] = {'mobs': [('e', 实体, 强度)], 'bosses': [...], 'final': {强度: 中位数}}
    uni = hp.get('unify')
    # 不在流程等级表里、普通敌人 / 小动物位置被跳过的地图（报告里列出来；用户 2026-11-13「dlc里比如指头遗迹附近的小怪血量补正也有遗漏」：
    # 47 张地图、四百多个位置不在 data\map_tiers.json，按随机器日志的强度补上了。以后再有新的漏掉，看报告这一句）
    untiered = Counter()
    n_added = 0                              # 随机器新加的 Boss 随从（普通敌人）照档加血的个数
    for name, plist in parts.items():
        m = name[:-len('.msb.dcx')]
        # 地图不在流程等级表里（星星之子、指之母、铃珠猎人、孤牢骑士这些 Boss 所在的小地图）：普通敌人跳过；
        # Boss 有整合包的 Boss 分档照样处理（以前整张地图跳过，这些 Boss 血量没调、档倍数也没乘）
        in_tiers = m in map_tiers
        # 随机器的原版地图目录里没有的（m60_44_37_10 这类 _10 图块、DLC 的 m61_*_10，31 张）只能按部件名对回原版
        # （以前整张跳过：689 个普通敌人位置、8 个 Boss 位置没补，用户 2026-11-01 发现）
        vmap = {e: n for e, n in van.get(name, ()) if e}
        for ent, npc, off in plist:
            nv = vmap.get(ent)
            if nv is None and ent in eid_pos:
                nv = by_name.get(eid_pos[ent])
            # 随机器为 Boss 随从新加进地图的敌人（4000000 段，对不上原版、日志里也没有强度）：放的是普通敌人就按这张地图的档照同档小怪加血
            # （用户 2026-11-13「都修」：以前跳过，DLC 的 Boss 房里随从只有 1k 血左右，同档小怪 8~12k；同一场里原版随从的位置是补了的）。
            # 不进中位数统计；记进 helpers，不魇化（rr/nightmare.py）
            if nv is None and ent in ADDED and npc in P_npc.rows and cls(npc) == 'basic' and ent not in hostile:
                if not in_tiers:
                    untiered[m] += 1
                    continue
                t = map_tiers[m]
                mr = pos_rate(ent, npc)
                pos[band_idx(t)].append((name, off, mr))
                pos_t[t].append((name, off, mr))
                n_added += 1
                if uni is not None:
                    uni['mobs'].append(('e', ent, t))
                    uni.setdefault('helpers', set()).add(ent)
                    uni.setdefault('npc', {})[ent] = npc_info(ent, npc)
                continue
            if nv is None or nv not in P_npc.rows or npc not in P_npc.rows:
                continue
            if ent in hostile:
                # 多挂一个血量上限效果：身上的倍率和运行时缩放不变，实际血量正好 × 倍数
                if (tgt or {}).get(ent) is not None or in_tiers:
                    b = area_band(ent, nv, m)
                    if uni is not None:
                        uni['mobs'].append(('e', ent, area_tier(ent, nv, m)))
                        uni.setdefault('inv', set()).add(ent)      # 入侵 NPC：血量跟着小怪乘，但不魇化（rr/nightmare.py）
                        uni.setdefault('npc', {})[ent] = npc_info(ent, npc)
                    sp = inv_sp[min(b, len(inv_sp) - 1)]
                    if sp is not None:
                        inv_pos[(name, off)] = sp
                        inv_by[b] += 1
                continue
            if boss_mult and cls(nv) == 'boss' and (cls(npc) == 'boss' or ent in FORCE_BOSS_POS):
                bt = (tgt or {}).get(ent, FORCE_BOSS_POS[ent]) if ent in FORCE_BOSS_POS else (hp.get('boss_tier') or {}).get(ent)       # 整合包的 Boss 分档优先（随机器的强度和地区名不总对得上，比如葛瑞克）
                if bt is None and not in_tiers:
                    continue
                b = band_idx(bt) if bt is not None else area_band(ent, nv, m)
                have = {struct.unpack_from('<i', P_npc.rows[npc], o)[0] for o in NPC_SPEFFECTS}
                mr = mult(npc) * scale_rate(ent)
                for sp in (now_sp or {}).get(ent, ()):
                    if sp not in have:
                        mr *= rate(sp)
                boss_rows.append((name, off, ent, nv, npc, b, mr))
                continue
            if not in_tiers:
                if cls(nv) in ('basic', 'small_animal'):
                    untiered[m] += 1
                continue
            if cls(nv) == 'small_animal' and cls(npc) == 'basic':
                # 随机器把狼、老鼠、野犬这些位置也当普通敌人位置，会放普通敌人进来：照这一档一样加血（雪原的狼群，用户 2026-11-01）
                t = area_tier(ent, nv, m)
                mr = pos_rate(ent, npc)
                pos[band_idx(t)].append((name, off, mr))
                pos_t[t].append((name, off, mr))
                n_small += 1
                if uni is not None:
                    uni['mobs'].append(('e', ent, t))
                    uni.setdefault('npc', {})[ent] = npc_info(ent, npc)
                continue
            if cls(nv) != 'basic':
                continue
            t = area_tier(ent, nv, m)
            b = band_idx(t)
            mv, mr = mult(nv), pos_rate(ent, npc)
            hv_b[b].append(base_hp(nv) * mv)
            hr_b[b].append(base_hp(npc) * mr)
            pos[b].append((name, off, mr))
            hr_t[t].append(base_hp(npc) * mr)
            pos_t[t].append((name, off, mr))
            if uni is not None:
                uni['mobs'].append(('e', ent, t))
                uni.setdefault('npc', {})[ent] = npc_info(ent, npc)
    boss_set, boss_msg = boss_targets(boss_rows, boss_mult, hp.get('boss_blend') or {}, base_hp, mult,
                                      items_out=uni['bosses'] if uni is not None else None)
    def full_rate(e, n):                           # 同 boss_rows 的总倍率：随机器后挂的缩放（now_sp）也会写进复制出来的行
        have = {struct.unpack_from('<i', P_npc.rows[n], o)[0] for o in NPC_SPEFFECTS}
        m = mult(n) * scale_rate(e)
        for sp in (now_sp or {}).get(e, ()):
            if sp not in have:
                m *= rate(sp)
        return m

    # 幽影树化身（敌人参数 c5230）：三个阶段的血量看三个血条代理，击败也由第三阶段的代理决定，上面只改了第三阶段本体那一行，
    # 整场实际只有约 4 万（用户 2026-11-09）。把本体的目标血量按原来的比例分给代理；身体同倍率（身体打到 1 血以后代理一死就过阶段，不能比代理薄）
    target = {(r[0], r[1]): r[4] for r in boss_rows if r[4] // 100 == AVATAR_MAIN}
    for name, plist in parts.items():
        main = next(((e, n, o) for e, n, o in plist if (name, o) in target and isinstance(boss_set.get(name, {}).get(o), tuple)), None)
        if main is None:
            continue
        linked = [(e, n, o) for e, n, o in plist if n // 100 in AVATAR_BARS + AVATAR_BODIES and n in P_npc.rows]
        bars = [(e, n) for e, n, _o in linked if n // 100 in AVATAR_BARS]
        if len(bars) != len(AVATAR_BARS):
            continue
        mr = next(r[6] for r in boss_rows if (r[0], r[1]) == (name, main[2]))
        k = boss_set[name][main[2]][1] * mr / sum(base_hp(n) * full_rate(e, n) for e, n in bars)
        for _e, n, o in linked:
            boss_set.setdefault(name, {})[o] = ('=', max(1, int(round(base_hp(n) * k))))
        hp.setdefault('avatar_maps', []).append(name[:-len('.msb.dcx')])
        if uni is not None:
            uni.setdefault('linked', {})[main[0]] = [e for e, _n, _o in linked]
        boss_msg += '；幽影树化身（%s）的目标血量按比例分给三个血条代理和身体（× %.2f）' % (name[:-len('.msb.dcx')], k)
    step = max(1, int(opts.get('step', 10)))
    if n_added:
        boss_msg += '；随机器新加的 Boss 随从（普通敌人）%d 个照所在地图的档加血' % n_added
    if untiered:
        boss_msg += '；不在流程等级表（data\\map_tiers.json）里、普通敌人没补血量的地图 %d 张 %d 处：%s' % (
            len(untiered), sum(untiered.values()), '、'.join('%s %d' % kv for kv in sorted(untiered.items())))
    if inv_mult:
        boss_msg += '；入侵 NPC %d 处挂血量上限效果，按 Boss 的倍数 × %s（%s）' % (
            len(inv_pos), ' / '.join('%g' % float(x) for x in inv_mult),
            '，'.join('%s %d' % (bands[b]['name'].split('（')[0], n) for b, n in sorted(inv_by.items())) or '都不用乘')
    # 四类 Boss 血量上面改不到（用户 2026-11-09「祖灵的血量补正也没生效 看看是否还有类似的」，FORCE_BOSS_POS 是其中的祖灵位置）：
    # 人形 Boss 的 hp 不起作用：按生命力算现在的实际血量，用血量上限效果拉到目标；双 Boss 的搭档、共用的血条代理（随机器新加的 4000000 段）跟主 Boss 同倍率。
    n_part, n_human, n_nolink, n_noinit = 0, 0, 0, 0
    P_init = hp.get('P_init')
    if P_init is not None and boss_mult:
        vit_lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(hp['data_dir'], 'CharaInitParam.xml')))[0]}['baseVit']
        hp_rate = hp_rate_rows(P_sp, hp['data_dir'])
        raws = {}

        def human_base(name, off):
            """人形：地图部件的 CharaInit 编号 → 生命力 → 玩家血量公式；找不到返回 None"""
            raw = raws.get(name)
            if raw is None:
                raw = raws[name] = erlib.dcx_decompress(open(os.path.join(rand_dir, 'map', 'mapstudio', name), 'rb').read())
            ids = struct.unpack_from('<8i', raw, off + 4)
            row = next((P_init.rows[x] for x in ids if x in P_init.rows), None)
            return player_hp(struct.unpack_from('<' + vit_lay[1], row, vit_lay[2])[0]) if row is not None else None

        def actual(name, e, n, o):
            base = human_base(name, o) if n >= HUMAN_ROW_MIN else base_hp(n)
            return base * full_rate(e, n) if base else None
        avatar = {(n, o) for n, plist in parts.items() for _e, npc, o in plist if npc // 100 in (AVATAR_MAIN,) + AVATAR_BARS + AVATAR_BODIES
                  and n[:-len('.msb.dcx')] in (hp.get('avatar_maps') or ())}
        k_of = {}
        for r in boss_rows:
            v = boss_set.get(r[0], {}).get(r[1])
            if isinstance(v, tuple) and (r[0], r[1]) not in avatar:
                a0 = actual(r[0], r[2], r[4], r[1])
                if a0:
                    k_of[(r[0], r[1])] = v[1] * r[6] / a0
                else:
                    n_noinit += 1
        added = {r[0] for r in boss_rows if any(e in ADDED for e, _n, _o in parts[r[0]])}

        def build_bars():
            import emevd
            common = {}
            for n in ('common', 'common_func'):
                p = os.path.join(rand_dir, 'event', n + '.emevd.dcx')
                if os.path.isfile(p):
                    common.update(_bar_tmpl(emevd.read(erlib.dcx_decompress(open(p, 'rb').read()))))
            jobs = [(f, common) for f in efiles if os.path.basename(f)[:-len('.emevd.dcx')] + '.msb.dcx' in added]
            return {os.path.basename(j[0])[:-len('.emevd.dcx')] + '.msb.dcx': r for j, r in zip(jobs, erlib.pmap(_job_bars, jobs, chunksize=8))}
        bar_ents = _cached(os.path.join(maps_out, 'stage3_bars.json'), _files_sig(efiles) + '|%d' % len(added), build_bars)
        for name, ents in sorted(bar_ents.items()):
            mains = [r for r in boss_rows if r[0] == name and (name, r[1]) in k_of]
            if not mains or not ents:
                continue
            groups = _msb_groups(os.path.join(rand_dir, 'map', 'mapstudio', name)) if len(mains) > 1 else {}
            want = set(ents)
            for e, n, o in parts[name]:
                if e not in want or n not in P_npc.rows or (name, o) in avatar or isinstance(boss_set.get(name, {}).get(o), tuple):
                    continue
                main = mains[0] if len(mains) == 1 else link_main(mains, groups, e)
                if main is None:
                    n_nolink += 1
                    continue
                k = k_of[(name, main[1])]
                if n >= HUMAN_ROW_MIN:
                    inv_pos[(name, o)] = hp_rate(k)
                else:
                    boss_set.setdefault(name, {})[o] = ('=', max(1, int(round(base_hp(n) * k))))
                n_part += 1
                if uni is not None:
                    uni.setdefault('linked', {}).setdefault(main[2], []).append(e)
        for r in boss_rows:
            if r[4] >= HUMAN_ROW_MIN and (r[0], r[1]) in k_of:
                boss_set[r[0]].pop(r[1])                # hp 字段没用，不用改它
                inv_pos[(r[0], r[1])] = hp_rate(k_of[(r[0], r[1])])
                n_human += 1
        boss_msg += '；人形 Boss %d 处用血量上限效果拉到目标%s；双 Boss 的搭档 / 共用血条 %d 处跟主 Boss 同倍率%s' % (
            n_human, '（%d 处找不到生命力，没改）' % n_noinit if n_noinit else '', n_part, '（%d 处对不上主 Boss，没改）' % n_nolink if n_nolink else '')
    n_min = int(opts.get('min_samples', 30))
    if len(hv_b.get(0, [])) < n_min:
        return boss_set, '敌人血量按地区补正：前期统计到的普通敌人位置太少，普通敌人跳过' + boss_msg
    med_v = {b: statistics.median(v) for b, v in hv_b.items() if len(v) >= n_min}
    med_r = {b: statistics.median(hr_b[b]) for b in med_v}
    r0 = med_r[0] / med_v[0]
    cap = float(opts.get('max_add', 5000))
    align = hp.get('align', True)
    bm = hp.get('band_mult') or []
    out = defaultdict(dict)
    for name, d in boss_set.items():
        out[name].update(d)
    msg = []
    curve = hp.get('curve')
    add_b = {}
    for b in sorted(med_v):
        base = med_v[b] * r0 if align else med_r[b]          # 对齐后的中位数
        a1 = min(cap, max(0.0, base - med_r[b])) if align and b > 0 else 0.0
        # enemy_hp_band：中位数再 × 地区倍数，也是加固定值（基础血量低的相对加得多），前期也加
        m = float(bm[min(b, len(bm) - 1)]) if bm else 1.0
        a2 = max(0.0, m - 1.0) * base
        add = add_b[b] = a1 + a2
        if add < 1 or curve:
            continue
        for name, off, mr in pos[b]:
            v = int(round(add / max(mr, 1e-6) / step)) * step
            if v > 0:
                out[name][off] = v
        msg.append('%s +%d%s' % (bands[b]['name'].split('（')[0], round(add), '（×%g）' % m if bm else ''))
    if curve:
        # 按强度平滑：两个锚点强度用上面按档算出来的加法，定出每级倍率，再把每一级的目标中位数外推出来（见 curve_adds）
        adds, cmsg = curve_adds(hr_t, set(pos_t), lambda t: add_b.get(band_idx(t), 0.0), curve, n_min,
                                final=uni['final'] if uni is not None else None)
        if uni is not None:
            uni['adds'] = dict(adds)                 # 每一级加的实际血量（斗技场试炼的精英照这个加，rr/arena.py）
        for t, add in adds.items():
            for name, off, mr in pos_t[t]:
                v = int(round(add / max(mr, 1e-6) / step)) * step
                if v > 0:
                    out[name][off] = v
        msg.append(cmsg)
    head = '敌人血量按地区补正（%s实际血量加%s%s）' % (
        '以前期为基准：前期随机后中位 ÷ 原版中位 = %.2f；' % r0 if align else '',
        '；中位数再按地区 ×' + ' / '.join('%g' % float(x) for x in bm) if bm else '',
        '；原版小动物位置放进来的普通敌人 %d 处也加' % n_small if n_small else '')
    return out, head + '：%s' % ('，'.join(msg) or '都不用加') + boss_msg


def curve_adds(hr_t, tiers, anchor_add, cfg, n_min, final=None):
    """按强度平滑（enemy_hp_band.curve，用户 2026-11-01：山顶和王城同档血量偏低、到雪原又翻倍，「按宁姆格福到湖区的增幅外推，让小怪血量平滑」）。
    两个锚点强度（默认 1 宁姆格福、6 湖区）按档的做法加完以后的中位数 T1、T2 → 每级倍率 k = (T2 / T1)^(1 / 两者差几级)；
    设了 end_tier / end_hp（用户同日：「最后才是 1 万一只小怪」）就改成从 T1 到「强度 end_tier 的中位数 = end_hp」定每级倍率；
    强度 t 的目标中位数 = T1 × k^(等效级 − 锚点 1)。DLC（强度 dlc_from 起）单独一段：等效级 = dlc_after + (t − dlc_from + 1) / dlc_merge，
    接在本体强度 dlc_after 后面（DLC 第一级比它高 1 / dlc_merge 级）、几个序号算一级（不然从 21 一路乘到 33，末尾近 9 万）。每级加 目标 − 这一级随机后的中位数（只加不减，加固定值）。
    hr_t = {强度: [这一级普通敌人位置加血前的实际血量]}；tiers = 要算的强度；anchor_add(t) = 按档的做法在强度 t 加多少。
    样本不够 n_min 的强度，中位数连同最近的几级一起算。返回（{强度: 加多少}, 报告文字）；
    final = {} 时填上每一级加完以后的中位数（目标和原来的中位数取大的，高难度血量补正 rr/hpunify.py 用）"""
    import statistics
    lo, hi = (int(x) for x in cfg.get('anchors', (1, 6)))
    dlc_from, dlc_after, merge = int(cfg.get('dlc_from', 21)), float(cfg.get('dlc_after', 20)), float(cfg.get('dlc_merge', 3))

    def med_near(t):
        pool = []
        for tt in sorted(hr_t, key=lambda x: (abs(x - t), x)):
            pool += hr_t[tt]
            if len(pool) >= n_min:
                break
        return statistics.median(pool) if pool else 0.0

    def eff(t):
        return t if t < dlc_from else dlc_after + (t - dlc_from + 1) / merge

    t1, t2 = med_near(lo) + anchor_add(lo), med_near(hi) + anchor_add(hi)
    end_t, end_hp = cfg.get('end_tier'), cfg.get('end_hp')
    if end_t and end_hp:
        hi, t2 = int(end_t), float(end_hp)
    k = (t2 / t1) ** (1.0 / (eff(hi) - eff(lo))) if t1 > 0 and t2 > 0 and hi != lo else 1.0
    # DLC 前中期对齐本体某一强度（用户 2026-11-03：「dlc 前中期的敌人血量改到圣树一档 后期跟着改」）：
    # 强度 dlc_from ~ dlc_flat_until 都用本体强度 dlc_base_tier 的目标，再往后从它起每 dlc_merge 个序号涨一级（每级倍率 k 不变，
    # end_tier / end_hp 只用来定 k，DLC 末尾不再是 end_hp）
    base_t = cfg.get('dlc_base_tier')
    flat = int(cfg.get('dlc_flat_until', dlc_from - 1))

    def level(t):
        if base_t is None or t < dlc_from:
            return eff(t)
        return eff(int(base_t)) + max(0, t - flat) / merge
    adds, shown = {}, []
    for t in sorted(tiers):
        target = t1 * k ** (level(t) - eff(lo))
        adds[t] = max(0.0, target - med_near(t))
        if final is not None:
            final[t] = max(target, med_near(t))
        shown.append('%d:%d' % (t, round(target)))
    dlc = ('DLC 强度 %d~%d 对齐本体强度 %d、之后每 %g 个序号涨一级' % (dlc_from, flat, int(base_t), merge) if base_t is not None
           else 'DLC 从强度 %d 起接在 %g 后面、%g 个序号算一级' % (dlc_from, dlc_after, merge))
    return adds, '按强度平滑（强度 %d → %d%s 每级 ×%.3f，%s；各强度目标中位数 %s）' % (
        lo, hi, '（%d）' % round(t2) if end_t and end_hp else '', k, dlc, ' '.join(shown))


def band_hp_plain(rand_dir, cache_dir, P_npc, P_sp, band_rows, cls, map_tiers, band_idx, bands, mult, step=10, min_samples=30,
                  tier_of=None, curve=None, final=None):
    """没开敌人随机时的 enemy_hp_band：按原版地图上普通敌人的位置统计每档实际血量中位数，
    这一档每个普通敌人参数（band_rows = {档: [敌人参数]}）的实际血量都加 中位数 × (倍数 − 1)（换算到基础血量时除以它身上的倍率）。
    curve（enemy_hp_band.curve）：改成按强度平滑（tier_of = {敌人参数: 强度}，见 curve_adds），锚点强度按上面按档的加法定。
    原版地图读随机器自带的 diste\\Vanilla（没装读 SHIPPED，见 vanilla_parts）；都没有就按参数行（不按位置）统计中位数。返回报告文字"""
    import statistics

    def rate(sid):
        r = P_sp.rows.get(sid)
        return (struct.unpack_from('<f', r, 16)[0] or 1.0) if r is not None else 1.0

    def actual(nid):
        row = P_npc.rows[nid]
        m = 1.0
        for o in NPC_SPEFFECTS:
            sid = struct.unpack_from('<i', row, o)[0]
            if sid > 0:
                m *= rate(sid)
        return struct.unpack_from('<I', row, NPC_HP)[0] * m, m

    own = {nid: b for b, lst in band_rows.items() for nid in lst}
    hv, hv_t = defaultdict(list), defaultdict(list)
    tier_of = tier_of or {}
    van = vanilla_parts(rand_dir, cache_dir)
    if van:
        for name, plist in van.items():
            if name[:-len('.msb.dcx')] not in map_tiers:
                continue
            for _e, n in plist:
                if n in own and cls(n) == 'basic':
                    hv[own[n]].append(actual(n)[0])      # 按敌人自己的区域强度定档（同一张图里可能有不同强度的区域）
                    if n in tier_of:
                        hv_t[tier_of[n]].append(actual(n)[0])
        how = '原版地图上的普通敌人位置'
    if not any(len(v) >= min_samples for v in hv.values()):
        hv, hv_t = defaultdict(list), defaultdict(list)
        for nid, b in own.items():
            hv[b].append(actual(nid)[0])
            if nid in tier_of:
                hv_t[tier_of[nid]].append(actual(nid)[0])
        how = '普通敌人参数行（没找到原版地图）'
    msg, n = [], 0
    add_b, plan = {}, []                     # 档 → 加多少；[(敌人参数, 实际血量要加多少)]
    for b, lst in sorted(band_rows.items()):
        if len(hv.get(b, [])) < min_samples:
            continue
        mb = float(mult[min(b, len(mult) - 1)])
        add = add_b[b] = max(0.0, mb - 1.0) * statistics.median(hv[b])
        if add < 1 or curve:
            continue
        plan += [(nid, add) for nid in lst]
        msg.append('%s +%d（×%g）' % (bands[b]['name'].split('（')[0], round(add), mb))
    if curve:
        rows_t = defaultdict(list)
        for nid, t in tier_of.items():
            if nid in own:
                rows_t[t].append(nid)
        adds, cmsg = curve_adds(hv_t, set(rows_t), lambda t: add_b.get(band_idx(t), 0.0), curve, min_samples, final=final)
        plan += [(nid, adds[t]) for t, lst in rows_t.items() for nid in lst]
        msg.append(cmsg)
    for nid, add in plan:
        _h, m = actual(nid)
        v = int(round(add / max(m, 1e-6) / step)) * step
        if v > 0:
            row = P_npc.rows[nid]
            struct.pack_into('<I', row, NPC_HP, min(0x7FFFFFFF, struct.unpack_from('<I', row, NPC_HP)[0] + v))
            n += 1
    return '敌人血量按地区加（%d 个普通敌人参数；按%s的实际血量中位数加固定值，基础血量低的相对加得多）：%s' % (n, how, '，'.join(msg) or '都不用加')


INV_SP_BASE, INV_SP_TEMPLATE = 7307000, 90030   # 入侵 NPC 的血量上限效果：每档一行；底子同 rr/hpunify.py（去掉「咒死无效」那一位）


def invader_sp_rows(P_sp, data_dir, mult):
    """enemy_hp_band.invader_as_boss 的效果行：血量上限 × 那一档的倍数。人形 NPC（c0000）的最大血量 = 玩家的血量公式（CharaInitParam 的生命力）
    × 身上的血量上限效果，NpcParam.hp 只是占位（1551、931），改了没用（用户 2026-11-09 发现修正没生效；日志核对：生命力 2 → 304 × 4.383 = 1332，
    生命力 28 → 911 × 1.61 = 1465）。返回 [每档的效果编号，倍数不大于 1 的是 None]"""
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(data_dir, 'SpEffect.xml')))[0]}
    put = lambda row, f, v: struct.pack_into('<' + lay[f][1], row, lay[f][2], v)
    out = []
    for b, k in enumerate(float(x) for x in mult):
        if k <= 1:
            out.append(None)
            continue
        rid = INV_SP_BASE + b
        if rid in P_sp.rows:
            raise RuntimeError('入侵 NPC 血量效果的编号 %d 已经有人用了' % rid)
        row = bytearray(P_sp.rows[INV_SP_TEMPLATE])
        o, bit = lay['disableCurse'][2], lay['disableCurse'][3]
        row[o] &= ~(1 << bit)
        put(row, 'iconId', -1)
        put(row, 'effectEndurance', -1.0)
        put(row, 'maxHpRate', k)
        put(row, 'spCategory', 0)
        P_sp.add_row(rid, bytes(row))
        out.append(rid)
    return out


def invader_hp_plain(rand_dir, cache_dir, P_npc, npc_tier, map_tiers, band_idx, bands, mult, sp_ids):
    """没开敌人随机时的 enemy_hp_band.invader_as_boss：入侵的 NPC（随机器 enemy.txt 的 HostileNPC）按原版地图找到敌人参数，
    参数行挂上所在地区那一档的血量上限效果（sp_ids，见 invader_sp_rows；档按参数自己的强度，没有就按地图的流程等级；一行用在几处取最高的档）。
    这一行也被别的（不是入侵的）位置用的不动。返回报告文字"""
    hostile = hostile_npcs(rand_dir)
    van = vanilla_parts(rand_dir, cache_dir)
    if not hostile or not van:
        return '入侵 NPC 血量：找不到原版敌人数据（随机器的敌人表 / 原版地图，或者整合包带的 data\\vanilla_enemies.json），跳过'
    band, other = {}, set()
    for name, plist in van.items():
        m = name[:-len('.msb.dcx')]
        for e, n in plist:
            if e not in hostile:
                other.add(n)
                continue
            if n not in P_npc.rows:
                continue
            t = npc_tier(P_npc.rows[n])
            if t is None:
                t = map_tiers.get(m)
            if t is not None:
                band[n] = max(band.get(n, 0), band_idx(t))
    n_ok, shared, by = 0, [], defaultdict(int)
    for n, b in sorted(band.items()):
        if n in other:
            shared.append(n)
            continue
        sp = sp_ids[min(b, len(sp_ids) - 1)]
        if sp is None:
            continue
        row = P_npc.rows[n]
        slot = next((o for o in NPC_SPEFFECTS if struct.unpack_from('<i', row, o)[0] <= 0), None)
        if slot is None:
            raise RuntimeError('入侵 NPC 的敌人参数 %d 没有空的效果格' % n)
        struct.pack_into('<i', row, slot, sp)
        n_ok += 1
        by[b] += 1
    return '入侵 NPC 血量按 Boss 的倍数（挂血量上限效果）：%d 个敌人参数 × %s（%s）%s' % (
        n_ok, ' / '.join('%g' % float(x) for x in mult),
        '，'.join('%s %d' % (bands[b]['name'].split('（')[0], c) for b, c in sorted(by.items())) or '都不用乘',
        '；%d 行也被别的位置用，没动：%s' % (len(shared), shared) if shared else '')


def stage3_retier(rand_dir, maps_out, P_npc, member_band, band_idx, table_base, npc_lot_off, elite=frozenset(),
                  extra=None, hooked=None, helpers=frozenset(), hp_align=None, P_sp=None, placed=None):
    """开了敌人随机时：被挪到别处的敌人仍带着原来的敌人参数（也就带着原来档次的掉落表）。
    这里按随机器日志里每个被替换位置的目标强度（scaling a->b 的 b）重新定档：给“原参数 × 新档次”复制一行敌人参数，
    指向新档次的大表，再把随机器输出地图里那个位置引用的参数编号改成复制出来的那行。
    extra = {实体: 掉落表}：击杀事件不发奖励的 Boss 位置（data\\boss_extra.json），不管放的是什么敌人，
    都复制一行参数指向给它准备的传说掉落表；挂上的实体记进 hooked。
    helpers = 原版 Boss 随从的位置（data\\boss_summons.json）：这些位置、以及随机器为随从新加进地图的敌人（编号不在 enemy.txt 里），
    放的敌人要是会掉东西，复制一行参数改成不掉（掉落表 -1），免得打 Boss 时刷随从。
    hp_align：按地区补正血量（见 hp_align_factors），补正的位置也复制一行参数（hp 加上补正值），和掉落的复制合在一起。
    P_sp：随机器用 SCALE_EVENT_NOW 挂的、会改血量上限的缩放效果，直接写进这个位置复制出来的参数（出场就带着，血量按缩放后的上限初始化；
    事件之后再挂同一个效果只是刷新），修正这些敌人出场不满血。
    placed：传一个 dict 进来，填成「实体 → 地图里最终引用的敌人参数」（复制过的是复制出来的那行）。之后再按位置改敌人参数
    （Boss 自身掉落的龙心脏、锻造石）要改这一行，改随机器原来的那行没用。
    改过的地图写到 maps_out\\map\\mapstudio（覆盖包），只有随机器输出或档次设置变了才重写。"""
    extra = extra or {}
    import hashlib
    mdir = os.path.join(rand_dir, 'map', 'mapstudio')
    files = sorted(glob.glob(os.path.join(mdir, '*.msb.dcx')))
    if not files:
        return ['敌人随机档次修正：找不到随机器输出的地图，跳过']
    sig = '%d|%d|%d' % (len(files), sum(os.path.getsize(f) for f in files), int(max(os.path.getmtime(f) for f in files)))
    os.makedirs(maps_out, exist_ok=True)
    cache_p = os.path.join(maps_out, 'stage3_parts.json')
    parts = None
    try:
        c = json.load(open(cache_p, encoding='utf-8'))
        if c.get('sig') == sig:
            parts = c['parts']
    except Exception:
        pass
    if parts is None:
        log('    读取随机器输出的地图（只在重新随机化后做一次）...')
        parts = dict(zip(map(os.path.basename, files), erlib.pmap(_job_parts, files, chunksize=8)))
        open(cache_p, 'w', encoding='utf-8').write(json.dumps({'sig': sig, 'parts': parts}))

    tgt = {}
    logs = sorted(glob.glob(os.path.join(rand_dir, 'spoiler_logs', '*_log_*.txt')), key=os.path.getmtime, reverse=True)
    used_log = ''
    for lp in logs:
        t = open(lp, encoding='utf-8', errors='replace').read()
        if 'Basic placements' not in t:
            continue                      # 失败的随机化没有摆放记录
        for m in re.finditer(r'^Replacing .*?\(#(\d+)\) in .*?\(scaling (\d+)->(\d+)\)', t, re.M):
            tgt[int(m.group(1))] = int(m.group(3))
        used_log = os.path.basename(lp)
        break
    if not tgt:
        return ['敌人随机档次修正：没有找到成功的随机化日志，跳过']

    now_sp = scale_now_effects(rand_dir, maps_out, P_sp) if P_sp is not None else {}
    hp_pos, hp_msg = (hp_align_factors(rand_dir, maps_out, parts, P_npc, hp_align, tgt, now_sp) if hp_align else ({}, ''))
    inv_pos = (hp_align or {}).get('inv_pos') or {}
    inv_ids = set(inv_pos.values())
    changes = defaultdict(list)
    need = {}
    known = known_enemies(rand_dir) if helpers is not None else set()
    n_helper = n_hp = n_now = 0
    final = {}                                    # 实体 → 原参数 / (原参数, 改法)；复制完再换成复制出来的编号
    for name, plist in parts.items():
        hpm = hp_pos.get(name, {})
        for ent, npc, off in plist:
            final.setdefault(ent, npc)
            if npc not in P_npc.rows:
                continue
            tb = None                             # 掉落：None 不改 / ('lot', 表) / 档次
            force_copy = ent in FORCE_COPY_IF_REPLACED and npc != FORCE_COPY_IF_REPLACED[ent]
            if (ent in helpers or (known and ent not in known)) and ent not in extra \
                    and struct.unpack_from('<i', P_npc.rows[npc], npc_lot_off)[0] > 0:
                tb = ('lot', -1)                  # Boss 随从：不掉东西
                n_helper += 1
            elif ent in extra:
                tb = ('lot', extra[ent])
                if hooked is not None:
                    hooked.add(ent)
            elif ent in tgt and npc in member_band:
                b = band_idx(tgt[ent]) + (1 if npc in elite else 0)    # 精英怪按新位置的下一档
                if b != member_band[npc]:
                    tb = b
            f = hpm.get(off)
            have = {struct.unpack_from('<i', P_npc.rows[npc], o)[0] for o in NPC_SPEFFECTS}
            sps = tuple(sp for sp in now_sp.get(ent, ()) if sp not in have) or None
            n_now += sps is not None
            if (name, off) in inv_pos:            # 入侵 NPC 的血量上限效果
                sps = (sps or ()) + (inv_pos[(name, off)],)
            if tb is None and f is None and sps is None and not force_copy:
                continue
            n_hp += f is not None
            key = (tb, f, sps, force_copy)
            changes[name].append((off, npc, key))
            need[(npc, key)] = None
            if final[ent] == npc:
                final[ent] = (npc, key)
    taken = set(P_npc.rows)
    for (npc, tb) in sorted(need, key=str):
        blk = npc // 10000 * 10000
        found = None
        for k in range(1, 10000):          # 在同一个 10000 段里找空编号，保持和原参数同一类
            c = blk + ((npc - blk + k) % 10000)
            if c not in taken:
                found = c
                break
        if found is None:
            raise RuntimeError('敌人参数 %d 所在编号段已满，无法复制' % npc)
        taken.add(found)
        need[(npc, tb)] = found
        lot, f, sps, _force_copy = tb
        row = bytearray(P_npc.rows[npc])
        for sp in sps or ():
            slot = next((o for o in NPC_SPEFFECTS if struct.unpack_from('<i', row, o)[0] <= 0), None)
            if slot is not None:
                struct.pack_into('<i', row, slot, sp)
            elif sp in inv_ids:
                raise RuntimeError('入侵 NPC 的敌人参数 %d 没有空的效果格' % npc)
        if lot is not None:
            if isinstance(lot, tuple):
                v = lot[1]
            elif callable(table_base):                # 按（原参数, 档）给掉落表（未鉴定物品的复制表，见 rr/unidentified.py）
                v = table_base(npc, lot)
            else:
                v = table_base + lot * 10000
            struct.pack_into('<i', row, npc_lot_off, v)
        if isinstance(f, tuple):
            struct.pack_into('<I', row, NPC_HP, min(0x7FFFFFFF, f[1]))
        elif f is not None:
            struct.pack_into('<I', row, NPC_HP, min(0x7FFFFFFF, struct.unpack_from('<I', row, NPC_HP)[0] + f))
        P_npc.add_row(found, row)
    if placed is not None:
        placed.update({e: need[v] if isinstance(v, tuple) else v for e, v in final.items()})

    # 漏编组的 Boss 随从补进 Boss 的随从分组（见 _job_helper_groups）：只看有随机器新加敌人的地图，按随机器输出缓存
    edir = os.path.join(rand_dir, 'event')
    hjobs = [(os.path.join(mdir, n), os.path.join(edir, n.replace('.msb.dcx', '.emevd.dcx'))) for n, pl in sorted(parts.items())
             if any(e in ADDED for e, _n, _o in pl) and os.path.isfile(os.path.join(edir, n.replace('.msb.dcx', '.emevd.dcx')))]
    grp = _cached(os.path.join(maps_out, 'stage3_helpers.json'), sig + '|grp%x|' % GROUP_AT + _files_sig([j[1] for j in hjobs]),
                  lambda: {os.path.basename(m): r for (m, _e), r in zip(hjobs, erlib.pmap(_job_helper_groups, hjobs)) if r})

    plan = sorted([name, off, need[(npc, tb)]] for name, lst in changes.items() for off, npc, tb in lst)
    maps = sorted(set(changes) | set(grp))
    outdir = os.path.join(maps_out, 'map', 'mapstudio')
    plan_p = os.path.join(maps_out, 'stage3_plan.json')
    # 每张地图一个指纹（来源 + 这张的改法），只重写变了的（用户 2026-11-05「只重做需要的部分」；以前一处变了 470 多张全部重写）
    edits = {name: [(off, npc, need[(npc, tb)]) for off, npc, tb in changes.get(name, [])] + [(off, 0, g) for off, g, _e in grp.get(name, [])] for name in maps}
    per = {name: hashlib.sha1(json.dumps([sig, edits[name]]).encode()).hexdigest() for name in maps}
    try:
        old = json.load(open(plan_p, encoding='utf-8')).get('per') or {}
    except Exception:
        old = {}
    todo = [name for name in maps if old.get(name) != per[name] or not os.path.isfile(os.path.join(outdir, name))]
    stale = [f for f in glob.glob(os.path.join(outdir, '*.msb.dcx')) if os.path.basename(f) not in per]
    reuse = not todo and not stale
    if not reuse:
        if todo:
            log('    修补 %d 张地图里被挪动敌人的参数引用（共 %d 张，其余没变）...' % (len(todo), len(maps)))
        os.makedirs(outdir, exist_ok=True)
        for f in stale:
            os.remove(f)
        if os.path.exists(plan_p):
            os.remove(plan_p)                     # 写到一半失败的话下次全部重写
        jobs = [(os.path.join(mdir, name), os.path.join(outdir, name), edits[name], len(parts[name])) for name in todo]
        erlib.pmap(_job_patch_map, sorted(jobs, key=lambda j: -os.path.getsize(j[0])), chunksize=4)   # 按游戏的固定偏移方式读回自检
        json.dump({'per': per, 'log': used_log, 'maps': maps}, open(plan_p, 'w', encoding='utf-8'))
    n_moved = sum(1 for v in changes.values() for x in v if isinstance(x[2][0], int))
    n_grp = len({(name, e) for name, lst in grp.items() for _off, _g, e in lst})
    return ['敌人随机档次修正：%d 处被挪动的敌人改按新位置的档次掉落（复制敌人参数 %d 行，地图 %d 张%s；日志 %s）' % (
        n_moved, len(need), len(maps), '，沿用上次修补的地图' if reuse else '，已重新修补', used_log),
            '敌人随机的 Boss 随从：%d 处（原版随从的位置、随机器为随从新加的敌人）放的敌人改成不掉东西' % n_helper,
            '敌人随机的 Boss 随从：%d 个没编进随从分组的（比如蕾娜菈的假人）补进 Boss 的随从分组，Boss 死后跟着消失，旁边的赐福能正常休息' % n_grp,
            'Boss / 事件里才出现的敌人：%d 处随机器后挂的血量缩放改成写进敌人参数（出场就是满血）' % n_now] + \
        ([hp_msg + '（%d 处）' % n_hp] if hp_msg else [])
