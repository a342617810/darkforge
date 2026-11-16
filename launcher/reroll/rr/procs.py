# -*- coding: utf-8 -*-
"""触发词条的属性补正（用户 2026-10-31：「可以让目前这些触发性词条拥有补正吗 基础伤害为当前伤害 包括词条里的猎印和法球」）。

触发词条（命中、附近发生异常、下蹲时放出的爆炸 / 子弹 / 治疗波）原来是固定数值。dll\\dark_core 的 procs 模块按人物属性
把这些攻击行的五种攻击力、治疗效果的回复量乘一个倍率，属性变了就重写：
  物理按力气、灵巧里高的，魔力按智力，火、圣按信仰，雷按灵巧，治疗按信仰；一个词条有两种属性的各算各的（用户定「按伤害属性」）。
  倍率 = 1 + K × 补正曲线 SCALE_GRAPH(属性)%，K 让 SCALE_AT 点时正好 SCALE_MULT 倍（用户定「80 点约 ×3」）。
法球（迸发 / 星群）是积木规则（dark_core 的 rules 自己算伤害），乘同一套倍率，按智力、信仰里高的（RULE_ELEMS 的 ORB；用户 2026-11-15，以前只按智力）。引爆 2026-11-05 改成按武器面板，不再乘。

这里做的（词条库插进 regulation 之后，affixes.build 调）：
  - 从每个词条族各稀有度的效果顺着 效果 → 行为（BehaviorParam_PC）→ 子弹 → 攻击（AtkParam_Pc）走（REFS），
    要改的是打伤害的攻击行和回血的效果行（changeHpPoint < 0；入口效果本身不算）；
  - 有的稀有度直接用原版法术 / 祷告的子弹链（辉石魔砾、兽爪、黄金树的恩惠…），改它会连玩家自己放的原版法术一起改：
    原版行（不是词条库 rows.json 插的）、往下走得到要改的原版行的，复制成词条专用的新行（NEW_BASE 起找空号），
    父节点（词条库的行或复制出来的行）指到复制的；用不到的原版行照旧共用；
  - 写 dll\\dark_core\\procs.txt（def_lines），说明文字里加一行「伤害随…提升」（annotate，护符模板和 dark_core 生成的装备都用）；
  - 词条库自己的攻击行和复制出来的攻击行都开 disableHitSpEffect（NO_HIT_EFFECT）：词条放出的攻击不算武器打中。"""
from .common import *  # noqa: F401,F403

SCALE_GRAPH, SCALE_AT, SCALE_MULT = 0, 80, 3.0  # 补正曲线 0（原版武器最常用的那条）；80 点 ×3
ELEMS = ('atkPhys', 'atkMag', 'atkFire', 'atkThun', 'atkDark')
HEAL = 5                                         # 词条族属性集合里「回血」的序号（0~4 是五种攻击力）
ORB = 6                                          # 法球：魔力伤害，按智力、信仰里高的（rules.rs kind_scale）
RULE_ELEMS = {'dr_orb_burst': {ORB}, 'dr_orb_swarm': {ORB}}
# 表：(参数名, 定义文件)；找空号的起点
TABLES = {'sp': ('SpEffectParam', 'SpEffect'), 'bh': ('BehaviorParam_PC', 'BehaviorParam'), 'bu': ('Bullet', 'BulletParam'), 'at': ('AtkParam_Pc', 'AtkParam')}
NEW_BASE = {'sp': 7298000, 'bh': 600009000, 'bu': 94000000, 'at': 308000000}
SP_REFS = ('replaceSpEffectId', 'cycleOccurrenceSpEffectId', 'atkOccurrenceSpEffectId', 'accumuOverFireId', 'accumuUnderFireId')
REFS = {'sp': [(f, 'sp') for f in SP_REFS] + [('behaviorId', 'bh')],
        'bu': [('atkId_Bullet', 'at'), ('HitBulletID', 'bu'), ('intervalCreateBulletId', 'bu'), ('spEffectIDForShooter', 'sp')] +
              [('spEffectId%d' % k, 'sp') for k in range(5)],
        'at': [('spEffectId%d' % k, 'sp') for k in range(5)]}
BH_REF = {0: 'at', 1: 'bu', 2: 'sp'}            # 行为的 refType → 指向哪张表
NO_HIT_EFFECT = 'disableHitSpEffect'             # 攻击参数的原版开关：这一下打中不触发攻击者「攻击命中时」的效果
HINT = {'zh': dict(elem=('物理', '魔力', '火', '雷', '圣'), stat=('力气或灵巧（较高者）', '智力', '信仰', '灵巧', '信仰'), orb='智力或信仰（较高者）',
                   one='伤害随%s提升', many='%s伤害随%s提升', join='，', heal='回复量随信仰提升', head=('伤害：', '回复血量：'), mark=('伤害',)),
        'en': dict(elem=('Physical', 'Magic', 'Fire', 'Lightning', 'Holy'),
                   stat=('Strength or Dexterity (higher)', 'Intelligence', 'Faith', 'Dexterity', 'Faith'), orb='Intelligence or Faith (higher)',
                   one='Damage scales with %s', many='%s damage scales with %s', join='; ', heal='Healing scales with Faith',
                   head=('Damage:', 'HP restored:'), mark=('damage', 'Damage'))}


class Table:
    def __init__(self, ctx, kind):
        self.name, xml = TABLES[kind]
        self.P = erlib.Param(ctx.bnd.get(self.name + '.param'))
        self.L = {n: (fc, off) for n, fc, off, *_ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, xml + '.xml')))[0]}
        self.next = NEW_BASE[kind]

    def get(self, row, f):
        fc, off = self.L[f]
        return struct.unpack_from('<' + fc, row, off)[0]

    def put(self, row, f, v):
        fc, off = self.L[f]
        struct.pack_into('<' + fc, row, off, v)

    def new_id(self):
        while self.next in self.P.rows:
            self.next += 1
        self.next += 1
        return self.next - 1


def build(ctx):
    ctx.procs = None
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))['gear']
    own_rows = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'rows.json'), encoding='utf-8'))
    T = {k: Table(ctx, k) for k in TABLES}
    own = {k: {int(i) for i in own_rows.get(T[k].name, {})} for k in TABLES}
    entries = {(key, r): s for key, f in lib.items() for r, s in (f.get('sp') or {}).items() if isinstance(s, int) and s > 0}
    entry_ids = set(entries.values())

    def row(kind, i):
        return T[kind].P.rows.get(i) if i is not None and i > 0 else None

    def children(kind, i):
        """(字段, 子节点的表, 编号)：指向存在的行的引用"""
        r = row(kind, i)
        if r is None:
            return []
        if kind == 'bh':
            ck = BH_REF.get(T['bh'].get(r, 'refType'))
            refs = [('refId', ck)] if ck else []
        else:
            refs = REFS[kind]
        out = []
        for f, ck in refs:
            c = T[kind].get(r, f)
            if c > 0 and c in T[ck].P.rows:
                out.append((f, ck, c))
        return out

    def target(kind, i):
        """要按属性改的行：打伤害的攻击行（五种攻击力的值）/ 回血的效果行（回复量）"""
        r = row(kind, i)
        if kind == 'at':
            v = [T['at'].get(r, f) for f in ELEMS]
            return v if any(v) else None
        if kind == 'sp' and i not in entry_ids:
            v = T['sp'].get(r, 'changeHpPoint')
            return v if v < 0 else None
        return None

    def walk(s):
        """从入口效果走到的所有节点 {(表, 编号)}"""
        seen, todo = set(), [('sp', s)]
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            todo += [(ck, c) for _f, ck, c in children(*n)]
        return seen

    # 哪些原版节点要复制：自己是要改的行，或者往下（只走原版节点）走得到要改的原版行
    need_memo = {}

    def need(kind, i):
        key = (kind, i)
        if key in need_memo:
            return need_memo[key]
        need_memo[key] = False                      # 环：先当不需要
        if i in own[kind]:
            return False
        v = target(kind, i) is not None or any(need(ck, c) for _f, ck, c in children(kind, i))
        need_memo[key] = v
        return v

    clones, patched = {}, set()

    def clone(kind, i):
        if (kind, i) in clones:
            return clones[(kind, i)]
        t = T[kind]
        nid = t.new_id()
        clones[(kind, i)] = nid
        r = bytearray(t.P.rows[i])
        t.P.add_row(nid, bytes(r), t.P.names.get(i, b''))
        nr = t.P.rows[nid]
        for f, ck, c in children(kind, i):
            if need(ck, c):
                t.put(nr, f, clone(ck, c))
        return nid

    bad = []
    for (key, r), s in entries.items():
        if need('sp', s):
            bad.append('%s/%s' % (key, r))           # 入口效果本身是原版行又要改：物品引用的是它，换不了
            continue
        for kind, i in walk(s):
            if i not in own[kind]:
                continue
            for f, ck, c in children(kind, i):
                if need(ck, c):
                    T[kind].put(T[kind].P.rows[i], f, clone(ck, c))
                    patched.add((kind, i))
    if bad:
        raise RuntimeError('触发词条补正：这些词条的入口效果是原版行、下面有要改的伤害，复制不了：%s' % bad[:10])

    # 复制完重新走一遍：要改的行都应该是词条专用的了
    atk, heal, fam = {}, {}, defaultdict(set)
    cloned = {(k, n) for (k, _o), n in clones.items()}
    for (key, r), s in entries.items():
        for kind, i in walk(s):
            v = target(kind, i)
            if v is None:
                continue
            if i not in own[kind] and (kind, i) not in cloned:
                raise RuntimeError('触发词条补正：%s/%s 走到的 %s %d 还是原版行' % (key, r, T[kind].name, i))
            if kind == 'at':
                atk[i] = v
                fam[key] |= {k for k, x in enumerate(v) if x}
            else:
                heal[i] = v
                fam[key].add(HEAL)
    for key, es in RULE_ELEMS.items():
        if key in lib:
            fam[key] |= es
    # 个别词条的基础伤害另外乘一个倍率（settings 的 trigger_damage_mult；用户 2026-11-01：辉石碎片 × 0.5）：攻击行的五种攻击力直接改，
    # 给 DLL 的基础值（procs.txt）也是改过的，说明里「伤害：」那行的数字 annotate 跟着改。同一攻击行被倍率不同的词条共用就报错（改一个会连另一个一起改）
    mult = damage_mults(ctx)
    users = defaultdict(set)
    for (key, r), s in entries.items():
        for kind, i in walk(s):
            if kind == 'at' and i in atk:
                users[i].add(key)
    scaled = Counter()
    for i, keys in sorted(users.items()):
        ms = {mult.get(k, 1.0) for k in keys}
        if len(ms) > 1:
            raise RuntimeError('触发词条补正：攻击行 %d 被基础伤害倍率不同的词条共用（%s），没法只改一个' % (i, '、'.join(sorted(keys))))
        m = ms.pop()
        if m == 1.0:
            continue
        atk[i] = [scale_num(x, m) for x in atk[i]]
        for f, x in zip(ELEMS, atk[i]):
            T['at'].put(T['at'].P.rows[i], f, x)
        patched.add(('at', i))                       # 词条库自己的行改了：登记进 patched_rows，最后的校验按改过的比
        for k in keys:
            scaled[k] += 1
    # 词条放出的攻击（触发词条的子弹 / 爆炸、碾压 / 坠星 / 反震的冲击波、法球、引爆……：词条库自己的攻击行 + 上面复制成词条专用的）
    # 开原版的 disableHitSpEffect：打中敌人不触发「攻击命中时」的效果，不算武器打中（用户 2026-11-01：巨人杀手、凌空不该跟着触发；
    # 原版剑骸大剑战技的冲击波等也开着它）。和原版共用、没复制的行不动
    _n, _fc, off, bp, *_ = next(t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'AtkParam.xml')))[0] if t[0] == NO_HIT_EFFECT)
    n_quiet = 0
    for i in sorted(own['at'] | {n for (k, _o), n in clones.items() if k == 'at'}):
        r = T['at'].P.rows.get(i)
        if r is None or r[off] >> bp & 1:
            continue
        r[off] |= 1 << bp
        n_quiet += 1
        if i in own['at']:
            patched.add(('at', i))
    for kind in TABLES:
        ctx.bnd.put(T[kind].name + '.param', T[kind].P.serialize())
    ctx.patched_rows = getattr(ctx, 'patched_rows', {})
    ctx.patched_rows.update({(T[k].name, i): bytes(T[k].P.rows[i]) for k, i in patched})
    ctx.procs = {'atk': atk, 'heal': heal, 'fam': dict(fam)}
    n_cl = Counter(T[k].name for k, _i in clones)
    ctx.report.append('触发词条补正：%d 个词条（含法球、引爆）、攻击行 %d、治疗效果 %d 按属性改（80 点 ×%g）；原版共用的复制成词条专用 %s%s' % (
        len(fam), len(atk), len(heal), SCALE_MULT, '、'.join('%s %d 行' % kv for kv in sorted(n_cl.items())) or '无',
        '；基础伤害另乘倍率：%s' % '、'.join('%s ×%g（%d 行）' % (k, mult[k], n) for k, n in sorted(scaled.items())) if scaled else ''))
    ctx.report.append('词条放出的攻击：%d 行攻击参数开 %s（打中不触发「攻击命中时」的效果，不算武器打中）' % (n_quiet, NO_HIT_EFFECT))


def damage_mults(ctx):
    """settings 的 trigger_damage_mult：{词条族: 基础伤害倍率}（_ 开头的键是说明）"""
    return {k: float(v) for k, v in (ctx.S.get('trigger_damage_mult') or {}).items() if not k.startswith('_')}


def scale_num(x, m):
    """乘倍率后四舍五入（不用 round 的银行家舍入：253 × 0.5 → 127）"""
    return int(math.floor(x * m + 0.5))


def def_lines(ctx):
    """dll\\dark_core\\procs.txt：scale <补正曲线> <属性> <倍率>；atk <攻击行> <物理> <魔力> <火> <雷> <圣>；heal <效果> <changeHpPoint>"""
    p = getattr(ctx, 'procs', None)
    if not p:
        return []
    return (['scale\t%d\t%d\t%g' % (SCALE_GRAPH, SCALE_AT, SCALE_MULT)] +
            ['atk\t%d\t%s' % (i, '\t'.join(map(str, v))) for i, v in sorted(p['atk'].items())] +
            ['heal\t%d\t%d' % kv for kv in sorted(p['heal'].items())])


def hint(ctx, key, lang):
    """说明里加的那一行：伤害随哪项属性提升（多种属性分开说）、回复量随信仰提升；不是触发词条就是空的"""
    p = getattr(ctx, 'procs', None)
    es = (p or {}).get('fam', {}).get(key)
    if not es:
        return ''
    h = HINT[lang]
    dmg = sorted(e for e in es if e != HEAL)
    stat = lambda e: h['orb'] if e == ORB else h['stat'][e]
    elem = lambda e: h['elem'][1] if e == ORB else h['elem'][e]
    parts = []
    if len(dmg) == 1:
        parts.append(h['one'] % stat(dmg[0]))
    elif dmg:
        parts += [h['many'] % (elem(e), stat(e)) for e in dmg]
        if lang == 'en':
            parts = [parts[0]] + [x[0].lower() + x[1:] for x in parts[1:]]
    if HEAL in es:
        parts.append(h['heal'])
    return h['join'].join(parts)


def annotate(ctx, key, lang, text):
    """说明文字加上 hint：插在「伤害：… / 回复血量：…」那行后面；没有这种行就插在第一行提到伤害的后面，再没有就接在第一段末尾。
    基础伤害另乘了倍率的词条（trigger_damage_mult），「伤害：」那行的数字跟着乘"""
    h = HINT[lang]
    m = damage_mults(ctx).get(key, 1.0)
    if m != 1.0:
        text = '\n'.join(re.sub(r'\d+(?:\.\d+)?', lambda mo: str(scale_num(float(mo.group()), m)), l) if l.startswith(h['head'][0]) else l
                         for l in text.split('\n'))
    add = hint(ctx, key, lang)
    if not add:
        return text
    lines = text.split('\n')
    at = next((k for k, l in enumerate(lines) if l.startswith(h['head'])), None)
    if at is None:
        at = next((k for k, l in enumerate(lines) if any(m in l for m in h['mark'])), None)
    if at is None:
        at = next((k - 1 for k, l in enumerate(lines) if not l.strip()), len(lines) - 1)
    return '\n'.join(lines[:at + 1] + [add] + lines[at + 1:])
