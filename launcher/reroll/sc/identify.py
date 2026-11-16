# -*- coding: utf-8 -*-
"""赐福「一键鉴定」+ 发货事件（新装备系统阶段 1；重随的 rr/containers.py 建了容器才有，features.json 的 identify）。
赐福「暗黑重铸」子菜单里的「一键鉴定」（sc/forge.py；以前在赐福主菜单）：先弹确认框，框里「背包里有几件未鉴定物品、容器还剩多少」是固定长度的占位
「〔#I0 …〕」（英文用 [ ]），dll\\dark_core 进游戏后按背包现状改写（长度不变，空位补空格；没装 DLL 就显示占位里的提示）。
选「是」点亮请求标记 identify_flag、弹一句提示；dark_core 看到标记（还要人物正坐在赐福点）就熄灭标记，逐件鉴定：
选空容器、按词条库生成、改写参数行和文字，把这批容器写进发货表、点亮 deliver_flag。
提示框关掉时请求标记还亮着 = DLL 没加载：熄灭标记、改弹「没有加载 dark_core」。
发货事件 DELIVER_EVENT（公共事件）每 0.5 秒看一次 deliver_flag：亮着就发发货表那一串（deliver_lot 起，每 LOT_CHAIN 行发一次），再熄灭标记。
事件编号在不存档的 1040490 块（见 dev\\event_flags\\说明.md），标记在 93000 块。
用户 2026-11-03：「暗黑重铸」里这一项改成「鉴定」子菜单——「一键鉴定」（上面那套）和各武器类型的「定向鉴定：<类型>」并列；
定向鉴定选了类型再选稀有度（普通 / 稀有 / 史诗 / 传说 / 传说（幽影之地）/ 全部，用户 2026-11-03），弹这一类型、这一稀有度的确认框
（占位 #I7：各稀有度的未鉴定武器件数、卢恩够鉴定几件），选「是」把类型序号、稀有度写进 features identify.dir 的标记再点亮请求；
dark_core（gear.rs directed_batch）熄灭请求，一件都鉴定不了先点亮「没鉴定」标记：请求熄了看它，亮着提示没鉴定，否则提示开始鉴定；
1 秒还没熄 = DLL 没加载。每件扣 cost 卢恩（只鉴定付得起的件数），本体从这一类型里挑（偏向加点），稀有度不变。做完都回到「鉴定」列表。
用户 2026-11-09：「鉴定」列表改成 一键鉴定 / 武器鉴定 / 防具鉴定 / 护符鉴定，武器类型收进「武器鉴定」；防具鉴定选部位（头 / 身 / 手 / 腿），
护符鉴定选流派（词条库的流派），之后同样选稀有度、确认。种类写进 features identify.dir 的 kind 标记（0 武器 / 1 防具 / 2 护符），
序号写进类型那几位；护符每件的价是 tcost（武器、防具的 10 倍）。确认框占位：武器 #I7、防具 #I9、护符 #IA。做完回到这一类的列表。"""
import emevd

from .esdutil import ALWAYS, DIALOG_WAIT, MENU_WAIT, STATE_TIME_OVER_1, flag_is_off, flag_is_on, register, i32, menu_parts, menu_pick, option_of

OPTION, TEXT, DONE_TEXT, MISSING_TEXT, DESC_TEXT = 35, 80090160, 80090161, 80090162, 80090163
# 「鉴定」子菜单里的文字（EventTextForTalk）：一键鉴定、定向鉴定开始 / 没鉴定、稀有度选项 +r、类型选项 +j、确认框 + 10j + r
ALL_TEXT, DIR_DONE, DIR_NONE, RAR_TEXT, TYPE_TEXT, DIR_DESC = 80096000, 80096001, 80096002, 80096010, 80096100, 80097000
RAR_NAMES = {'zh': ('普通', '稀有', '史诗', '传说', '传说（幽影之地）', '全部稀有度'),
             'en': ('Common', 'Rare', 'Epic', 'Legendary', 'Legendary (Shadow)', 'All rarities')}
RAR_COLOR = ('#DADADA', '#A0B4F3', '#BB2DC2', '#D4A900', '#D4A900', None)     # 同装备名字的颜色（sc/gracelook.py RARITY）
DELIVER_EVENT = 1040490960
LOT_CHAIN = 10                                     # 发一张掉落表，游戏最多连着发这么多行（之后的行要另发）
FIELD_LEN = {'zh': 44, 'en': 72}                   # 含两端括号的字符数（DLL 连括号整段改写；「背包里 199 件待鉴定；还能再生成 武器 2693 防具 589 护符 812」要 40 个字）


def on(cx):
    return bool(cx.feat.get('identify'))


KIND_CH = '0123456789A'                            # 确认框占位的种类字（dark_core gear.rs 的 kind_char）
KIND_TEXT = 80096003                               # +k：武器鉴定 / 防具鉴定 / 护符鉴定
KIND_NONE = (DIR_NONE, 80096006, 80096007)         # 没鉴定的提示（武器沿用以前的编号）
ENTRY_TEXT = (TYPE_TEXT, 80096200, 80096300)       # 各类的条目 +j：武器类型 / 部位 / 流派
DESC0 = (DIR_DESC, 80097500, 80097600)             # 确认框 +10j+r
FIELD_KIND = (7, 9, 10)                            # 确认框占位的种类（dark_core confirm_tick：各稀有度的未鉴定武器 / 防具 / 护符件数）
KIND_NAMES = {'zh': ('武器鉴定', '防具鉴定', '护符鉴定'), 'en': ('Identify Armaments', 'Identify Armor', 'Identify Talismans')}


def field(lang, kind=0):
    """确认框里 dark_core 改写的占位（种类 kind：0 一键鉴定、7 / 9 / 10 武器 / 防具 / 护符鉴定）"""
    ch = KIND_CH[kind]
    if lang == 'zh':
        body = '#I%s 正在清点背包……' % ch
        return '〔' + body + ' ' * (FIELD_LEN['zh'] - 2 - len(body)) + '〕'
    body = '#I%s counting...' % ch
    return '[' + body + ' ' * (FIELD_LEN['en'] - 2 - len(body)) + ']'


def dir_cfg(cx):
    return (cx.feat.get('identify') or {}).get('dir')


def entries(di, k):
    """这一类的条目 [(中文, 英文)]：武器类型 / 防具部位 / 护符流派（旧的设置没有防具、护符）"""
    if k == 0:
        return [(t[1], t[2]) for t in di['types']]
    if not di.get('kind0'):
        return []
    return [(x[1], x[2]) for x in di.get('slots') or []] if k == 1 else [(x[0], x[1]) for x in di.get('archs') or []]


def kinds_of(di):
    return [k for k in range(3) if di and entries(di, k)]


def sel_state(k, j):
    """选了第 k 类的第 j 项：写种类、序号，列稀有度；+1 按稀有度分；+10+r 写稀有度、确认框"""
    return 10000 * (k + 1) + 100 * j


def req_state(k):
    """第 k 类点亮请求：+5 熄了看「没鉴定」，+10 没鉴定，+20 开始，+30 DLL 没加载"""
    return 5000 + 100 * k


def esd(cx, groups):
    if not on(cx):
        return
    from .esdutil import MENU_GROUP
    if any(option_of(c) == OPTION for s in groups[MENU_GROUP].values() for c in s['entry']):
        raise RuntimeError('赐福菜单的选项编号 %d 已被占用（一键鉴定）' % OPTION)
    flag = int(cx.feat['identify']['identify_flag'])
    p = menu_parts(groups, cx.root)
    add_cmd, conf_call, yes_eval, no_eval, ret, gid = (p[k] for k in ('add_cmd', 'conf_call', 'yes_eval', 'no_eval', 'ret', 'gid'))
    setf = lambda f, v: {'bank': 1, 'id': 11, 'args': [i32(f), i32(v)]}
    say = lambda text: {'bank': 1, 'id': 17, 'args': [i32(7), i32(text), i32(1), i32(0), i32(1)]}
    add = lambda k, text: dict(add_cmd, args=[i32(k), i32(text), i32(-1)])
    to = lambda target, ev: {'target': target, 'eval': ev, 'pass': [], 'sub': []}
    state = lambda entry, conds: {'entry': entry, 'exit': [], 'while': [], 'conds': conds}
    show = lambda items: [{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}] + items + \
        [add(99, 26000004), {'bank': 1, 'id': 10, 'args': [i32(1)]}]
    di = dir_cfg(cx)
    kinds = kinds_of(di)
    # 0 列表（一键鉴定 + 武器 / 防具 / 护符鉴定）→ 1 按选项分；100~103 一键鉴定（同以前，做完回列表）；20 + 2k 第 k 类的列表
    st = {
        0: state(show([add(1, ALL_TEXT)] + [add(2 + k, KIND_TEXT + k) for k in kinds]), [to(1, MENU_WAIT)]),
        1: state([], [to(100, menu_pick(1))] + [to(20 + 2 * k, menu_pick(2 + k)) for k in kinds] + [to(9, ALWAYS)]),
        100: state([dict(conf_call, args=[i32(DESC_TEXT)])], [to(101, yes_eval), to(0, no_eval)]),
        101: state([setf(flag, 1), say(DONE_TEXT)], [to(102, DIALOG_WAIT)]),
        102: state([], [to(103, flag_is_on(flag)), to(0, ALWAYS)]),
        103: state([setf(flag, 0), say(MISSING_TEXT)], [to(0, DIALOG_WAIT)]),
        9: state([], [ret]),
    }
    if di:
        req, none = int(di['flag']), int(di['none'])
        bits = lambda first, n, v: [setf(first + i, (v >> i) & 1) for i in range(n)]
        kind_bits = (lambda k: bits(int(di['kind0']), int(di['kind_bits']), k)) if di.get('kind0') else (lambda k: [])
        for k in kinds:
            ents, lst, rq = entries(di, k), 20 + 2 * k, req_state(k)
            st[lst] = state(show([add(1 + j, ENTRY_TEXT[k] + j) for j in range(len(ents))]), [to(lst + 1, MENU_WAIT)])
            st[lst + 1] = state([], [to(sel_state(k, j), menu_pick(1 + j)) for j in range(len(ents))] + [to(0, ALWAYS)])
            for j in range(len(ents)):
                s0 = sel_state(k, j)
                st[s0] = state(kind_bits(k) + bits(int(di['type0']), int(di['type_bits']), j) + show([add(1 + r, RAR_TEXT + r) for r in range(6)]),
                               [to(s0 + 1, MENU_WAIT)])
                st[s0 + 1] = state([], [to(s0 + 10 + r, menu_pick(1 + r)) for r in range(6)] + [to(lst, ALWAYS)])
                for r in range(6):
                    st[s0 + 10 + r] = state(bits(int(di['rar0']), int(di['rar_bits']), r) + [dict(conf_call, args=[i32(DESC0[k] + 10 * j + r)])],
                                            [to(rq, yes_eval), to(s0, no_eval)])
            # 点亮请求 → 熄了看「没鉴定」（+10 提示没鉴定 / +20 提示开始，都回这一类的列表）；1 秒没熄 = DLL 没加载（+30）
            st[rq] = state([setf(none, 0), setf(req, 1)], [to(rq + 5, flag_is_off(req)), to(rq + 30, STATE_TIME_OVER_1)])
            st[rq + 5] = state([], [to(rq + 10, flag_is_on(none)), to(rq + 20, ALWAYS)])
            st[rq + 10] = state([setf(none, 0), say(KIND_NONE[k])], [to(lst, DIALOG_WAIT)])
            st[rq + 20] = state([say(DIR_DONE)], [to(lst, DIALOG_WAIT)])
            st[rq + 30] = state([setf(req, 0), say(MISSING_TEXT)], [to(0, DIALOG_WAIT)])
    groups[gid] = st
    register(cx, 'identify', TEXT, gid)          # 收进赐福最上面的「暗黑重铸」（sc/forge.py）


def desc(key, k, name, r, cost, names):
    """第 k 类第 name 项、稀有度 r 的确认框（没折行）。用户 2026-11-12「武器鉴定里的文本也要修订一下」→ 认可的修订稿：
    标题「武器鉴定：大剑 · 普通」（以前括号套括号）；一句一行（以前一整段自动折行，会断在词中间）；写明武器本体优先挑适合加点的
    （gear.rs 的 gen_weapon_for_typed）、全部稀有度时卢恩不够先鉴定便宜的"""
    zh = key == 'zh'
    title = KIND_NAMES[key][k]
    if zh:
        what = ('武器', '防具', '护符')[k]
        into = (name, '%s防具' % name, '「%s」流派的护符' % name)[k]
        whom = '所有未鉴定%s' % what if r == 5 else '%s的未鉴定%s' % (names[r], what)
        how = ('稀有度不变，本体优先挑适合你加点的，词条照常随机。', '稀有度不变，词条照常随机。', '稀有度不变，词条从这个流派里抽。')[k]
        price = ('每件消耗 %d 卢恩，卢恩不够时只鉴定付得起的件数。' % cost[r] if r < 5 else
                 '每件按稀有度消耗 %s 卢恩，\n卢恩不够时先鉴定便宜的。' % ' / '.join(map(str, cost)))
        return '%s：%s · %s\n背包里%s都鉴定成%s。\n%s\n%s\n%s\n\n确定鉴定吗？' % (title, name, names[r], whom, into, how, price, field('zh', FIELD_KIND[k]))
    what = ('armament', 'armor piece', 'talisman')[k]
    into = ('a %s' % name, '%s armor' % name.lower(), 'a talisman with a %s affix' % name.lower())[k]
    whom = 'every unidentified %s' % what if r == 5 else 'every %s unidentified %s' % (names[r], what)
    how = ('Rarity stays the same; the base weapon is picked to suit your stats, and affixes are rolled as usual.',
           'Rarity stays the same; affixes are rolled as usual.', 'Rarity stays the same; affixes are drawn from this style.')[k]
    price = ('%d runes each; if you run short, only as many as you can afford.' % cost[r] if r < 5 else
             '%s runes each by rarity;\nif you run short, the cheapest go first.' % ' / '.join(map(str, cost)))
    return '%s: %s · %s\nIdentify %s in your inventory as %s.\n%s\n%s\n%s\n\nIdentify them?' % (
        title, name, names[r], whom, into, how, price, field('en', FIELD_KIND[k]))


def wrap_box(text, key, wrap):
    """确认框折行：dark_core 按背包改写的占位那一行（〔#I… 〕/ [#I… ]，定长，见 field）原样留着不折——
    英文一行最多 64 个字母，占位 72 个，以前会被折成两行、去掉尾部空格，长度对不上（2026-11-12 修订文字时发现）"""
    out = []
    for par in text.split('\n'):
        out += [par] if par.startswith(('〔#I', '[#I')) else wrap(par, key)
    return out


def texts(cx, key):
    if not on(cx):
        return {}
    zh = key == 'zh'
    if zh:
        out = {TEXT: '鉴定', ALL_TEXT: '一键鉴定', DONE_TEXT: '开始鉴定，装备会放进背包',
               MISSING_TEXT: '现在无法鉴定：暗黑重铸的组件没有加载，请用启动器重新启动游戏。',
               DESC_TEXT: '鉴定背包里所有的未鉴定物品，各自变成一件随机的装备。\n%s\n\n确定鉴定吗？' % field('zh')}
    else:
        out = {TEXT: 'Identify', ALL_TEXT: 'Identify All', DONE_TEXT: 'Identifying. The gear will be put in your inventory.',
               MISSING_TEXT: "Can't identify right now: a Darkforge component didn't load. Please restart the game from the launcher.",
               DESC_TEXT: 'Identify every unidentified item in your inventory; each becomes a random piece of gear.\n%s\n\nIdentify them?'
                          % field('en')}
    di = dir_cfg(cx)
    if di:
        names = RAR_NAMES[key]
        paint = lambda r: names[r] if RAR_COLOR[r] is None else '<font color="%s">%s</font>' % (RAR_COLOR[r], names[r])
        out[DIR_DONE] = '开始鉴定，装备会放进背包' if zh else 'Identification started. The gear will be put in your inventory.'
        for r in range(6):
            out[RAR_TEXT + r] = paint(r)
        none_zh = ('没有鉴定：没有这种未鉴定武器，或卢恩不够', '没有鉴定：没有这种未鉴定防具，或卢恩不够', '没有鉴定：没有这种未鉴定护符，或卢恩不够')
        none_en = ('Nothing identified: no such armaments, or not enough runes.', 'Nothing identified: no such armor, or not enough runes.',
                   'Nothing identified: no such talismans, or not enough runes.')
        from .guide import wrap           # 确认框的高度按换行数定：长句手动折行（同说明页）
        for k in kinds_of(di):
            cost = [int(x) for x in (di['tcost'] if k == 2 else di['cost'])]
            out[KIND_TEXT + k] = KIND_NAMES[key][k]
            out[KIND_NONE[k]] = (none_zh if zh else none_en)[k]
            for j, (ezh, een) in enumerate(entries(di, k)):
                name = ezh if zh else een
                out[ENTRY_TEXT[k] + j] = name
                for r in range(6):
                    out[DESC0[k] + 10 * j + r] = '\n'.join(wrap_box(desc(key, k, name, r, cost, names), key, wrap))
    return {'EventTextForTalk': out}


def events(cx, e, ev0):
    """发货：每 0.5 秒看一次发货标记，亮着就发发货表那一串、熄灭标记（DLL 改好发货表后才点亮）"""
    if not on(cx) or any(ev['id'] == DELIVER_EVENT for ev in e['events']):
        return
    d = cx.feat['identify']
    lot, flag, rows = int(d['deliver_lot']), int(d['deliver_flag']), int(d.get('deliver_rows') or 32)
    # 游戏发一张掉落表最多连着发 LOT_CHAIN 行：按这么多行一段，每段开头发一次（以前只发第一段，每批只到 10 件，2026-11-01 查日志）
    awards = [emevd.ins(2003, 4, ('s32', lot + k)) for k in range(0, rows, LOT_CHAIN)]
    body = [emevd.ins(1003, 1, ('u8', len(awards) + 1), ('u8', 0), ('u8', 0), ('u32', flag)),   # 标记没亮：跳过下面几行
            *awards,
            emevd.ins(2003, 66, ('u8', 0), ('u32', flag), ('u8', 0)),
            emevd.ins(1001, 0, ('f32', 0.5)), emevd.ins(1000, 4, ('u8', 1))]           # 等 0.5 秒，重新开始
    e['events'].append({'id': DELIVER_EVENT, 'rest': 0, 'ins': body, 'params': []})
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', DELIVER_EVENT), ('u32', 0)))
