# -*- coding: utf-8 -*-
"""开局装备和开局遗物（一次性重随：第一次抽了记进 --state 的 start / gifts，以后照旧；点「一次性重随」才重抽）。

开局装备（settings 的 start_gear）：每个职业的每件开局武器 / 防具换成新装备系统生成的装备。
  每件占一个专用编号（武器 START_W0 起每个 1 万号、防具 START_P0 起每个 100 号），参数行先照本体复制、文字和容器一样是占位；
  dll\\dark_core 一启动（还在主菜单）就按 items.txt 的 start 行（本体、档、种子、能力需求上限）生成词条、改写参数行和文字，
  同一次抽的所有新角色都一样；角色进存档时 DLL 把身上的开局装备记进这个角色的记录，以后点「一次性重随」只影响新角色。
  武器：普通（用户 2026-11-02，以前稀有）；近战武器换成任意近战类型（各职业尽量不同，同一职业的同一把原武器换成同一类型），盾、法杖、圣印记、弓、火把同类型；
        本体在这类型里随机；能力需求不超过职业的初始属性（DLL 按上限截）。
  防具：同部位随机本体，稀有度按原包防具的件数比例（普通 ~ 史诗，不出传说：用户 2026-11-02）。
  武器档和防具最高档在发 start 行时按现在的规则套，一次性重随存下的旧抽签（本体、种子）照旧用。
  负重：武器 + 防具不超过最大负重的 69%（中负重）：武器占到 75% 以上就换成不比原武器重的本体，防具按部位分剩下的。
开局遗物（start_keepsakes）：9 个遗物换成「命中时触发、会放法术」的护符（每种一个、稀有，开局直接装备），从这些词条里随机挑 9 种。
  角色创建界面的名字 / 说明放在 features.json 的 keepsakes，游戏脚本（sc/start.py）写进 menu 文字包"""
from .common import *  # noqa: F401,F403
from . import affixes, containers, once

START_W0, START_P0 = 230000000, 29000000
MELEE_TYPES = {1, 3, 5, 7, 9, 11, 13, 14, 15, 16, 17, 19, 21, 23, 24, 25, 28, 29, 31, 35, 37, 39, 41,
               88, 92, 93, 94, 95}     # 近战武器类型（含 DLC 的拳脚 / 反手剑 / 轻型大剑 / 大太刀 / 兽爪；不含香水瓶、投掷刀、刺盾）
# 开局时不带命中异常的武器类型（用户 2026-10-29：只有武器要带异常）：弓、弩、大弓、弩炮、法杖、圣印记、小盾、中盾、大盾、突刺盾
NO_STATUS_TYPES = {50, 51, 53, 55, 56, 57, 61, 65, 67, 69, 90}
WEAPON_FIELDS = ('equip_Wep_Right', 'equip_Subwep_Right', 'equip_Subwep_Right3', 'equip_Wep_Left', 'equip_Subwep_Left', 'equip_Subwep_Left3')
ARMOR_FIELDS = ('equip_Helm', 'equip_Armer', 'equip_Gaunt', 'equip_Leg')     # 顺序同 protectorCategory 0~3
SLOT_SHARE = {'equip_Helm': 0.2, 'equip_Armer': 0.42, 'equip_Gaunt': 0.15, 'equip_Leg': 0.23}
START_LOAD = 0.69                       # 中负重：装备重量 < 最大负重的 70%
WEAPON_TIER = 0                         # 普通（用户 2026-11-02，以前稀有）
ARMOR_MAX_TIER = 2                      # 开局防具最高史诗，不出传说（用户 2026-11-02）
STAT_FIELDS = ('baseStr', 'baseDex', 'baseMag', 'baseFai', 'baseLuc')
KEEPSAKES = 9
KEEPSAKE_MENU0 = 100300                 # CharMakeMenuListItemParam：遗物 k 的 captionId（GR_MenuText 名字 / GR_LineHelp 说明）
KEEPSAKE_INIT0 = 2400                   # CharaInitParam：2400 = 无（空模板），2401~2409 = 9 个遗物
CLASS_MENU = range(100200, 100230)      # CharMakeMenuListItemParam：职业菜单，value + 3000 = CharaInitParam 职业行


def lay(ctx, xml):
    return pdm.layout(pdm.load(os.path.join(ctx.data_dir, xml)))[0]


def build(ctx):
    """要在 affixes.build 之后（护符模板）、containers.build 之后（开局装备的文字占位和 items.txt）"""
    ctx.start_items = []
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    il, ml = lay(ctx, 'CharaInitParam.xml'), lay(ctx, 'CharMakeMenuListItemParam.xml')
    P_init = erlib.Param(ctx.bnd.get('CharaInitParam.param'))
    P_menu = erlib.Param(ctx.bnd.get('CharMakeMenuListItemParam.param'))
    if ctx.S.get('start_keepsakes', True):
        keepsakes(ctx, lib, il, ml, P_init, P_menu)
    sg = ctx.S.get('start_gear') or {}
    if sg.get('enabled', True) and getattr(ctx, 'containers', None):
        start_gear(ctx, lib, il, ml, P_init, P_menu, sg)
    ctx.bnd.put('CharaInitParam.param', P_init.serialize())


# ---------------------------------------------------------------- 开局遗物
def keepsakes(ctx, lib, il, ml, P_init, P_menu):
    fams = [k for k, f in lib['gear'].items() if f['group'] == '命中时触发' and 'Rare' in f['tal'] and tal_weight(f, 'Rare') > 0
            and not f['zh'].startswith('近战武器命中敌人累积到一定次数时，恢复')]          # 恢复血量 / 专注值那两种不放法术
    if len(fams) < KEEPSAKES or any(KEEPSAKE_INIT0 + k not in P_init.rows for k in range(KEEPSAKES + 1)) \
            or any(KEEPSAKE_MENU0 + k not in P_menu.rows for k in range(1, KEEPSAKES + 1)):
        ctx.report.append('开局遗物：没换（护符词条或角色创建参数不全）')
        return
    key = once.sig(*[bytes(P_init.rows[KEEPSAKE_INIT0 + k]) for k in range(KEEPSAKES + 1)], sorted(fams))
    plan = once.get(ctx, 'gifts', key)
    fresh = not (plan and len(plan) == KEEPSAKES and all(k in fams for k in plan))
    if fresh:
        with once.own_rng(ctx, 'gifts'):
            plan = ctx.rng.sample(fams, KEEPSAKES)
        once.put(ctx, 'gifts', key, plan)
    io = {nm: (off, fc) for nm, fc, off, bp, bits, d in il if not bits}
    off, fc = io['equip_Accessory01']
    empty = bytes(P_init.rows[KEEPSAKE_INIT0])
    texts = {'zh': {}, 'en': {}}
    for k, fk in enumerate(plan, 1):
        f = lib['gear'][fk]
        row = bytearray(empty)
        struct.pack_into('<' + fc, row, off, f['tal']['Rare'])
        P_init.rows[KEEPSAKE_INIT0 + k][:] = row
        cid = pdm.unpack(ml, bytes(P_menu.rows[KEEPSAKE_MENU0 + k]))['captionId']
        for lang, hint in (('zh', '开局直接装备'), ('en', 'Starts equipped')):
            tag = re.sub(r'<[^>]+>', '', lib['rarity_tag']['Rare'][lang])
            s = f['suffix'][1] if lang == 'zh' else f['suffix'][0]
            name = '%s %s护符' % (tag, s) if lang == 'zh' else '%s Amulet of %s' % (tag, s)
            texts[lang][cid] = [name, f['text']['Rare'][lang].split('\n')[0] + '\n' + hint]
    ctx.features['keepsakes'] = texts
    ctx.report.append('开局遗物（%s）：%s' % ('新抽的' if fresh else '沿用第一次抽的', '、'.join(v[0] for v in texts['zh'].values())))


# ---------------------------------------------------------------- 开局装备
def max_load(ctx, end):
    """耐力 → 最大负重（CalcCorrectGraph 220）"""
    g = pdm.unpack(lay(ctx, 'CalcCorrectGraph.xml'), bytes(erlib.Param(ctx.bnd.get('CalcCorrectGraph.param')).rows[220]))
    st = [g['stageMaxVal%d' % k] for k in range(5)]
    gr = [g['stageMaxGrowVal%d' % k] for k in range(5)]
    ad = [g['adjPt_maxGrowVal%d' % k] for k in range(5)]
    for k in range(4):
        if end <= st[k + 1]:
            t = (end - st[k]) / (st[k + 1] - st[k]) if st[k + 1] > st[k] else 1.0
            t = max(0.0, min(1.0, t))
            t = t ** ad[k] if ad[k] > 0 else 1 - (1 - t) ** (-ad[k])
            return gr[k] + (gr[k + 1] - gr[k]) * t
    return gr[4]


def classes(ml, P_init, P_menu):
    out = []
    for k in CLASS_MENU:
        if k in P_menu.rows:
            c = 3000 + pdm.unpack(ml, bytes(P_menu.rows[k]))['value']
            if c in P_init.rows and c not in out:
                out.append(c)
    return out


def armor_tier_weights(lib):
    """防具稀有度权重：原包每个稀有度的防具件数（超过 ARMOR_MAX_TIER 的档是 0）"""
    return [sum(lib['armor']['count'][r].values()) if k <= ARMOR_MAX_TIER else 0 for k, r in enumerate(RAR)]


def draw(ctx, lib, il, ml, P_init, P_menu, wb, pb, W, any_melee):
    """抽一份开局装备：[{cls, field, cat, base, tier, seed, maxreq, lvl}]"""
    rng = ctx.rng
    wl = {t[0]: t for t in lay(ctx, 'EquipParamWeapon.xml')}
    gw = lambda i, f: struct.unpack_from('<' + wl[f][1], W.rows[i], wl[f][2])[0]
    by_type, by_slot = defaultdict(list), defaultdict(list)
    for b in wb:
        by_type[b['type']].append(b)
    for b in pb:
        by_slot[b['slot']].append(b)
    tw = armor_tier_weights(lib)
    used = Counter()
    plan = []
    for cls in classes(ml, P_init, P_menu):
        ci = pdm.unpack(il, bytes(P_init.rows[cls]))
        stats = [int(ci[f]) for f in STAT_FIELDS]
        avail = max_load(ctx, ci['baseEnd']) * START_LOAD
        weapons, same = [], {}
        for f in WEAPON_FIELDS:
            v = ci.get(f, 0)
            w = v - v % 10000 if v > 0 else 0
            if w <= 0 or w not in W.rows:
                continue
            t = gw(w, 'wepType')
            if w in same:
                t = same[w]
            elif any_melee and t in MELEE_TYPES:
                cand = [x for x in sorted(MELEE_TYPES) if by_type.get(x)]
                if cand:
                    low = min(used[x] for x in cand)
                    t = rng.choice([x for x in cand if used[x] == low])
                    used[t] += 1
            same[w] = t
            if by_type.get(t):
                weapons.append({'field': f, 'orig': w, 'type': t, 'lvl': v % 10000, 'base': rng.choice(by_type[t])})
        wsum = sum(x['base']['weight'] for x in weapons)
        if wsum > avail * 0.75:          # 太重：换成不比原武器重的本体（这类型都比它重就挑最轻的）
            for x in weapons:
                cap = gw(x['orig'], 'weight')
                light = [b for b in by_type[x['type']] if b['weight'] <= cap]
                x['base'] = rng.choice(light) if light else min(by_type[x['type']], key=lambda b: b['weight'])
            wsum = sum(x['base']['weight'] for x in weapons)
        for x in weapons:
            plan.append({'cls': cls, 'field': x['field'], 'cat': 0, 'base': x['base']['id'], 'tier': WEAPON_TIER,
                         'seed': rng.getrandbits(62), 'maxreq': stats, 'lvl': x['lvl']})
        budget = max(0.0, avail - wsum)
        worn = [f for f in ARMOR_FIELDS if ci.get(f, 0) > 0]
        tot = sum(SLOT_SHARE[f] for f in worn) or 1.0
        for f in worn:
            slot = ARMOR_FIELDS.index(f)
            if not by_slot.get(slot):
                continue
            cap = budget * SLOT_SHARE[f] / tot
            light = [b for b in by_slot[slot] if b['weight'] <= cap]
            b = rng.choice(light) if light else min(by_slot[slot], key=lambda b: b['weight'])
            tier = rng.choices(range(len(RAR)), weights=tw)[0]
            plan.append({'cls': cls, 'field': f, 'cat': 1, 'base': b['id'], 'tier': tier, 'seed': rng.getrandbits(62),
                         'maxreq': stats, 'lvl': 0})
    return plan


def main_stat(stats, wtype, seed):
    """开局武器的主补正（最高的那项）放在职业最高的属性上（用户 2026-10-30）：力、技、智、信、感的序号。
    并列时法杖优先智力、圣印记优先信仰，否则按种子挑一个（落魄者全是 10）"""
    hi = max(stats)
    tied = [k for k, v in enumerate(stats) if v == hi]
    pref = {57: 2, 61: 3}.get(wtype)                  # wepType：法杖 57、圣印记 61
    return pref if pref in tied else tied[seed % len(tied)]


def start_gear(ctx, lib, il, ml, P_init, P_menu, sg):
    ctx.start_ids = (START_W0, 10000, START_P0, 100)       # 写进 items.txt 的 startids：DLL 按编号把开局装备记进角色记录
    wb, pb, nm = affixes.bases(ctx, lib)
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    Pp = erlib.Param(ctx.bnd.get('EquipParamProtector.param'))
    cls_ids = classes(ml, P_init, P_menu)
    key = once.sig(*[bytes(P_init.rows[c]) for c in cls_ids])
    plan = once.get(ctx, 'start', key)
    ok_w, ok_p = {b['id'] for b in wb}, {b['id'] for b in pb}
    fresh = not (plan and all((e['base'] in ok_w) if e['cat'] == 0 else (e['base'] in ok_p) for e in plan))
    if fresh:
        with once.own_rng(ctx, 'start'):
            plan = draw(ctx, lib, il, ml, P_init, P_menu, wb, pb, W, bool(sg.get('any_melee', True)))
        once.put(ctx, 'start', key, plan)
    wf = json.load(open(os.path.join(ctx.data_dir, 'weapon_fields.json'), encoding='utf-8'))
    origin = [(o, sz) for f, o, sz in wf['own'] if f.startswith('originEquipWep')]
    io = {nm_: (off, fc) for nm_, fc, off, bp, bits, d in il if not bits}
    used = [i for i in W.rows if START_W0 <= i < START_W0 + 500 * 10000] + [i for i in Pp.rows if START_P0 <= i < START_P0 + 1000 * 100]
    if used:
        raise RuntimeError('开局装备的编号 %s 已被占用' % used[:5])
    orig = {c: pdm.unpack(il, bytes(P_init.rows[c])) for c in cls_ids}
    wtype = {b['id']: b['type'] for b in wb}
    ids = {0: [], 1: []}
    tw = armor_tier_weights(lib)
    for e in plan:
        # 旧抽签也按现在的档：武器一律 WEAPON_TIER；超过 ARMOR_MAX_TIER 的防具按种子在允许的档里重定（不全挤到史诗）
        if e['cat'] == 0:
            e['tier'] = WEAPON_TIER
        elif e['tier'] > ARMOR_MAX_TIER:
            e['tier'] = random.Random(e['seed']).choices(range(len(RAR)), weights=tw)[0]
        cat = e['cat']
        if cat == 0:
            i = START_W0 + len(ids[0]) * 10000
            copy_weapon(W, origin, e['base'], i)
        else:
            i = START_P0 + len(ids[1]) * 100
            Pp.add_row(i, bytes(Pp.rows[e['base']]))
        ids[cat].append(i)
        off, fc = io[e['field']]
        struct.pack_into('<' + fc, P_init.rows[e['cls']], off, i + e['lvl'])
        w = cat == 0                         # 武器：补正只从分布最高的 scaling_top_pct% 里抽、至少 min_status 种异常（DLL 生成时管）
        nost = w and wtype.get(e['base']) in NO_STATUS_TYPES     # 法杖、圣印记、弓、盾：-1 = 一个异常都不带
        ctx.start_items.append({'cat': cat, 'id': i, 'tier': e['tier'], 'base': e['base'], 'seed': e['seed'], 'maxreq': e['maxreq'],
                                'top': int(sg.get('scaling_top_pct', 20)) if w else 100, 'min_status': -1 if nost else int(sg.get('min_status', 1)) if w else 0,
                                'main': main_stat(e['maxreq'], wtype.get(e['base']), e['seed']) if w else -1})
    ctx.bnd.put('EquipParamWeapon.param', W.serialize())
    ctx.bnd.put('EquipParamProtector.param', Pp.serialize())
    placeholders(ctx, ids[0], ids[1])
    # 报告：各职业的武器本体和负重（换过的按本体重量，没换的按原来的）
    wl = {t[0]: t for t in lay(ctx, 'EquipParamWeapon.xml')}
    pl = {t[0]: t for t in lay(ctx, 'EquipParamProtector.xml')}
    weight = lambda P, L, i: struct.unpack_from('<' + L['weight'][1], P.rows[i], L['weight'][2])[0] if i in P.rows else 0.0
    loads, parts = [], []
    for c in cls_ids:
        ci = pdm.unpack(il, bytes(P_init.rows[c]))
        tot = sum(weight(W, wl, ci[f] - ci[f] % 10000) for f in WEAPON_FIELDS if ci.get(f, 0) > 0)
        tot += sum(weight(Pp, pl, ci[f]) for f in ARMOR_FIELDS if ci.get(f, 0) > 0)
        loads.append(tot / max_load(ctx, ci['baseEnd']))
        parts.append('/'.join(nm('zh', 'WeaponName', e['base']) for e in plan if e['cls'] == c and e['cat'] == 0))
    n_cls = class_texts(ctx, ml, P_menu, orig, plan, nm)
    tiers = Counter(RAR_ZH[RAR[e['tier']]] for e in plan if e['cat'] == 1)
    ctx.report.append('开局装备（%s）：%d 个职业，武器 %d 把（%s，本体 %s）、防具 %d 件（%s）；最重的职业占最大负重 %.0f%%；'
                      '职业介绍里的武器名换了 %d 个职业；生成词条要 dll\\dark_core' % (
                          '新抽的' if fresh else '沿用第一次抽的', len(cls_ids), len(ids[0]), RAR_ZH[RAR[WEAPON_TIER]], '；'.join(parts), len(ids[1]),
                          '、'.join('%s %d' % kv for kv in sorted(tiers.items())), max(loads) * 100 if loads else 0, n_cls))


def copy_weapon(W, origin, base, i):
    """本体的参数行复制到编号 i（originEquipWep 指着本体的改成指自己）"""
    row = bytearray(W.rows[base])
    for o, _sz in origin:
        if struct.unpack_from('<i', row, o)[0] == base:
            struct.pack_into('<i', row, o, i)
    W.add_row(i, bytes(row))


def placeholders(ctx, w_ids, p_ids):
    """开局装备 / 追忆武器的文字占位（同容器；DLL 生成后改写）"""
    for lang, code in containers.LANGS:
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for cat, lst in (('w', w_ids), ('p', p_ids)):
            if not lst:
                continue
            for fld, fn in containers.FIELD.items():
                fmg = containers.FMG[cat] + fn + '.fmg'
                hdr, ents = erlib.read_fmg_full(mb.get(fmg))
                d = dict(ents)
                d.update({i: containers.placeholder(i, fld, lang) for i in lst})
                mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))


CLASS_TEXT_WIDTH = {'zh': 19, 'en': 50}   # 职业介绍一行最多几个字（照随机器的换行）


def wrap(toks, sep, width):
    """「名字，名字，…」按名字换行，一行不超过 width 个字（单个名字更长就独占一行）；行尾留逗号，同随机器"""
    lines, cur = [], ''
    for k, t in enumerate(toks):
        piece = t + (sep.strip() if k < len(toks) - 1 else '')
        add = piece if not cur else (cur + (' ' if sep.endswith(' ') else '') + piece)
        if cur and len(add) > width:
            lines.append(cur)
            cur = piece
        else:
            cur = add
    lines.append(cur)
    return '\n'.join(lines)


def class_texts(ctx, ml, P_menu, orig, plan, nm):
    """随机器把各职业的开局装备名字写进了职业介绍（GR_LineHelp，「名字，名字，…」）：里面原武器的名字换成新本体的名字
    （生成的武器名字里带着本体名）。原版的介绍是背景文字，对不上名字就不动。结果放 features.json 的 class_text，sc/start.py 写。
    返回改了几个职业"""
    cap = {}
    for k in CLASS_MENU:
        if k in P_menu.rows:
            u = pdm.unpack(ml, bytes(P_menu.rows[k]))
            cap.setdefault(3000 + u['value'], u['captionId'])
    out = {}
    for lang, code in (('zh', 'zhocn'), ('en', 'engus')):
        src = next((p for p in (os.path.join(d, code, 'menu_dlc02.msgbnd.dcx') for d in ctx.a.msg_src) if os.path.isfile(p)), None)
        if not src:
            continue
        helps = erlib.read_msgbnd(src).get('GR_LineHelp', {})
        sep = '，' if lang == 'zh' else ', '
        for c, cid in cap.items():
            text = helps.get(cid)
            if not text or c not in orig:
                continue
            # 随机器手动换行（有时断在名字中间、逗号后面）：先压成一行再按逗号切
            toks = [t.strip() for t in re.sub(r'\s+', ' ', text).split(sep.strip())]
            done = set()
            for e in plan:
                if e['cls'] != c or e['cat'] != 0:
                    continue
                v = orig[c][e['field']]
                old, new = nm(lang, 'WeaponName', v - v % 10000), nm(lang, 'WeaponName', e['base'])
                k = next((j for j, t in enumerate(toks) if t == old and j not in done), None)
                if k is not None and new:
                    toks[k] = new
                    done.add(k)
            if done:
                out.setdefault(lang, {})[cid] = wrap(toks, sep, CLASS_TEXT_WIDTH[lang])
    ctx.features['class_text'] = out
    return len(out.get('zh', {}))
