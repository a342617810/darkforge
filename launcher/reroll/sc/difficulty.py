# -*- coding: utf-8 -*-
"""局内难度（rr/difficulty.py 在重随版 regulation 里建每档的玩家特殊效果）：「暗黑重铸」子菜单里加「难度调整」
（原来在「更多选项」里的选项 33，用户 2026-11-03 挪进来：用 esdutil.register 登记，sc/forge.py 收进去），
子菜单只列各档的名字；选中先弹确认框写清楚这一档的效果，选「是」才切换再弹一句提示，选「否」回到档位列表。
切换：对话脚本点亮请求标记 REQ0 + 档位，公共事件 EVENT 看到后先清掉所有档的效果、再挂上这一档、熄灭标记
（不能靠同类别自动顶替：游戏不认自定义的类别，旧档的效果会一直叠着；对话脚本也没有移除效果的命令）。
当前档位（照 ELDEN RING Reforged 的做法）：选档时对话脚本点亮 CUR0 + 这一档、熄灭其他档。CUR0 / REQ0 在会存档的全局标记块 99xx
（ERR 用 9900~9919 存难度；原版、随机器的事件 / 对话 / 参数里都没用 9950~9969），重启游戏也在。
难度效果本身不存档：读档（包括死后复活）时公共事件都会重新跑——EVENT 每 0.5 秒看一次，当前档的标记亮着、身上却没有这一档的
效果就重新挂上；INIT_EVENT 读档后跑一次，一个当前档标记都没亮时：身上有某档效果就点亮那一档，否则点亮「普通」。
打开难度菜单时按这些标记选哪一档用「当前」文字 CUR_TEXT + 档位：前面嵌原版背包里「装备中」的图标（01_common 的 MENU_EquMark）。

高难度单程票（用户 2026-11-03，dev\\item_system\\超限锻造石与高难度.md §4）：settings 里标了 lock 的档（死亡、不可能）一旦进去，
这个角色就再也不能切回没标 lock 的档。锁记在会存档的标记 LOCK（93910，确认进入时才点亮；更新前就在这两档的老存档没有它，还能切走一次）。
- LOCK 没亮时选 lock 档：确认框只显示前 3 行（用户 2026-11-06），分 3 个框：效果（DESC_FIRST_TEXT）、敌人变化 + 建议（CONFIRM_MID_TEXT）、
  不可逆警告 + 最后确认（CONFIRM2_TEXT），三次都选「是」才点亮 LOCK、切档、熄灭头目复活列表里所有 Boss 的击败标记（复活），最后提示（LOCK_DONE）；任何一次「否」回到列表。
- 门槛（用户 2026-11-13）：LOCK 没亮时选 lock 档，「黑剑」玛利喀斯的击败标记 RELEASE_FLAG 没亮就只提示「命定之死尚未被释放」（GATE_NOTE），回到列表。
  存档解锁（用户 2026-11-20）：同一个存档里有角色七道咒痕都反转了，不看黑剑——dark_core saveunlock.rs 读存档后点亮 features 里咒痕的 unlock 标记。
- LOCK 亮着时：列表里没标 lock 的档变灰、后面写「（已锁定）」，选了只提示一句（LOCKED_NOTE）；lock 档之间照旧只弹效果说明，不复活，也不看门槛。
复活列表照头目复活（data\\gracemenu\\grace_more.esd，Vawser 的 Boss Resurrection - Lite）：它的几个「复活一个 Boss」子状态机把除最后一个参数
（传送用）外的参数都设成 0，这里把所有调用的这些参数收齐，一次熄灭（每个状态 REVIVE_CHUNK 条，串起来）。
Boss 房里的赐福（用户 2026-11-12「进入高难度后要熄灭所有boss房里的赐福点亮标记」）：点亮标记也一起熄灭（data\\boss_graces.json，
dev\\item_system\\build_boss_graces.py 生成；头目复活列表本来就熄灭其中 22 个）。Boss 复活后房间里的赐福不出现，标记亮着就能直接传送进 Boss 房。
熄的是两个标记（用户 2026-11-15）：传送标记（flag）和赐福自己的点亮标记（lit，9005810 的第 2 个参数，RegisterBonfire 用）。只熄传送标记的话，
重新打败 Boss 后赐福出现时还算「已点亮」，摸了不会再点亮，传送标记也不会再亮。
读档修复（GRACE_FIX_EVENT）：传送标记灭着、点亮标记却亮着的 Boss 房赐福，把点亮标记熄掉。修的是更新前进过「死亡」的角色，
还有赐福菜单「头目复活」（它对其中 17 个只熄传送标记）。同一个事件接着熄掉复活后残留的 Boss 标记（revivefix.STALE_WHEN_ALIVE：
艾尔登之兽打倒后看完过场才点亮的 19000804，亮着的话位置的结算事件一开始就结束，用户 2026-11-18）。"""
import json
import os

import emevd
import esd as esdlib

from .common import DATA
from .esdutil import ALWAYS, DIALOG_WAIT, MENU_WAIT, calls, esd_int, flag_is_off, flag_is_on, i32, menu_parts, menu_pick, register
from . import revivefix

OPTION, TEXT, TIER_TEXT, DONE_TEXT, DESC_TEXT = 33, 80090020, 80090021, 80090041, 80090080
EVENT, REQ0 = 1040490710, 9960
MAX = 10                                                     # 最多 10 档：当前 9950~9959、请求 9960~9969
CUR0, CUR_TEXT = 9950, 80090140
INIT_EVENT = 1040490712
GRACE_FIX_EVENT = 1040490714                                  # 读档后修 Boss 房赐福：传送标记灭、点亮标记亮 → 熄点亮标记；再熄复活后残留的 Boss 标记
MARK_IMG = "<img src='img://MENU_EquMark.png' height='32' width='32' vspace='-16'/>"
# 高难度单程票：锁定标记（93000 块，dev\event_flags\说明.md）、文字编号
LOCK = 93910
DESC_FIRST_TEXT, CONFIRM2_TEXT, TIER_LOCKED_TEXT, LOCKED_NOTE, LOCK_DONE = 80090300, 80090310, 80090320, 80090330, 80090331
CONFIRM_MID_TEXT, DONE_FIRST_TEXT = 80090340, 80090350      # 第二个框；第一次进入后的提示（说明已经在第二个框看过，不重复）
# 门槛（用户 2026-11-13「死亡难度以上改为只有击败黑剑才能进入 没击败时提示命定之死尚未被释放」）：LOCK 没亮时选 lock 档，先看「黑剑」玛利喀斯
# （逐渐崩毁的法姆·亚兹拉）的击败标记，没亮就提示 GATE_NOTE、回到列表。开启敌人随机时就是那个位置的头目（随机器保留位置的标记）。
# LOCK 亮了以后不看：进入时所有头目复活（玛利喀斯的击败标记也在复活列表里），死亡、不可能之间照旧能切
RELEASE_FLAG, GATE_NOTE = 13000800, 80090332
GATE0, GATE_SAY = 50, 110                                    # 状态：50+k 看标记、110 提示
LOCKED_COLOR = '#7F7F7F'
REVIVE_CHUNK = 100
REVIVE_ESD = os.path.join(DATA, 'gracemenu', 'grace_more.esd')
BOSS_GRACES = os.path.join(DATA, 'boss_graces.json')
# 状态编号：0 分派、1 / 2 列表等选择（没锁 / 锁了）、9 返回、10+k 效果说明、10+n+k 切档、30+k 锁定提示、40+k / 60+k 建列表（没锁 / 锁了）、
# 70+k 第一个框（带建议）、80+k 第二个框（不可逆）、90+k 进入（点亮 LOCK、切档）、200+ 复活、REVIVE_DONE 最后提示
REVIVE0, REVIVE_DONE = 200, 199
# 每档的来历（dev\\narrative\\叙事方案.md；按 settings 里的中文名对，对不上就不写这一句）
LORE = {
    '轻松': ('受到赐福浓厚庇佑的道路。敌人的刀刃变得迟钝，能得到的卢恩也随之减少。',
           'A path under the thick protection of grace. Enemy blades grow dull, and the runes to be gained diminish with them.'),
    '休闲': ('赐福的指引清晰可见的道路。敌人的攻势较为缓和，能得到的卢恩也略微减少。',
           'A path where the guidance of grace is plain to see. Enemies press less fiercely, and the runes to be gained diminish slightly.'),
    '普通': ('褪色者原本走的道路。引导之路的前头，有无数敌人在等待。',
           'The path the Tarnished were meant to walk. Countless foes wait ahead on the road of guidance.'),
    '进阶': ('习武之人走的道路。敌人更为坚韧，难以轻易撼动。',
           'The path of those who train in arms. Enemies are sturdier and not easily shaken.'),
    '困难': ('老练的战士走的道路。跟随拉塔恩将军的士兵，走的便是这样的路。',
           'The path of seasoned warriors. The soldiers who followed General Radahn walked one like it.'),
    '大师': ('英雄走的道路。在破碎战争之前，蒙受黄金树赐福的战士们走过这样的路。',
           'The path of heroes. Before the Shattering, warriors who bore the blessing of the Erdtree walked one like it.'),
    # 用户 2026-11-13「应该是褪色者主动踏上 而不是被找上」（以前第二句是「黄金律法去除的死亡，会在这里重新找上褪色者」）
    '死亡': ('命定之死回归的道路。褪色者在这里迎向黄金律法去除的死亡。',
           'The path where Destined Death returns. Here the Tarnished go forth to meet the death the Golden Order removed.'),
    '不可能': ('挑战半神、杀戮神祇的道路。圆桌厅堂的铁匠修古，等的就是走上这条路的人。',
            'The path of those who challenge demigods and slay gods. Hewg, blacksmith of the Roundtable Hold, has been waiting for those who walk it.'),
}


def locked_tiers(ts):
    """标了 lock 的档（死亡、不可能）的序号"""
    return [k for k, t in enumerate(ts) if t.get('lock')]


def revive_flags():
    """头目复活列表里所有 Boss 要熄灭的标记（击败标记、对应的全局 Boss 标记等），加上 Boss 房里赐福的点亮标记，排好序"""
    groups = revivefix.apply(esdlib.read(open(REVIVE_ESD, 'rb').read())['groups'])
    workers = {}
    for g, st in groups.items():
        cleared = {i for s in st.values() for c in s['entry'] if (c['bank'], c['id']) == (1, 11) and len(c['args']) == 2
                   and esd_int(c['args'][1]) == 0 for i in range(10) if bytes(c['args'][0]) == bytes([0x40 + i, 0xB8, 0xA1])}
        if cleared:
            workers[g] = cleared
    flags = set(revivefix.EXTRA_FLAGS)           # 只熄击败标记不够的 Boss 另外要熄的（火焰巨人的真击败标记、蒙葛特的入口雾门）
    for st in groups.values():
        for s in st.values():
            for c in calls(s):
                w = workers.get(c['id'] & 0xFFFFFFFF) if c['bank'] == 6 else None
                if w:
                    for i in w:
                        v = esd_int(c['args'][i]) if i < len(c['args']) else None
                        if v and v > 0:
                            flags.add(v)
    flags |= set(boss_grace_flags())
    return sorted(flags)


def boss_graces():
    """Boss 房里的赐福（data\\boss_graces.json；没有这个文件就是空的）：[(传送标记, 点亮标记)]"""
    if not os.path.isfile(BOSS_GRACES):
        return []
    return [(int(g['flag']), int(g['lit'])) for g in json.load(open(BOSS_GRACES, encoding='utf-8'))['graces']]


def boss_grace_flags():
    """Boss 房里赐福要熄灭的标记：传送标记 + 赐福自己的点亮标记（有几个是同一个）"""
    return sorted({f for pair in boss_graces() for f in pair})


def sources(cx):
    """复活列表、Boss 房赐福表改了也要重做游戏脚本"""
    return [REVIVE_ESD, BOSS_GRACES]


def skip_flag(lines, on, f):
    """标记是 on 就跳过后面 lines 条"""
    return emevd.ins(1003, 1, ('u8', lines), ('u8', int(on)), ('u8', 0), ('u32', f))


def flag_off(f):
    return emevd.ins(2003, 66, ('u8', 0), ('u32', f), ('u8', 0))


def grace_fix_event():
    """读档后跑一次：每个 Boss 房赐福，传送标记亮着就跳过，点亮标记灭着也跳过，否则熄灭点亮标记"""
    body = []
    for warp, lit in boss_graces():
        if lit != warp:
            body += [skip_flag(2, True, warp), skip_flag(1, False, lit), flag_off(lit)]
    return body


def stale_fix():
    """同一个读档事件里接着跑：复活过的 Boss（击败标记灭着）留下的「打倒后」标记熄掉（revivefix.STALE_WHEN_ALIVE，艾尔登之兽 19000804）"""
    body = []
    for defeat, stale in sorted(revivefix.STALE_WHEN_ALIVE.items()):
        body += [skip_flag(len(stale), True, defeat)] + [flag_off(f) for f in stale]
    return body


def both(a, b):
    """eval：a && b"""
    return a[:-1] + b[:-1] + bytes([0x98, 0xA1])


def tiers(cx):
    """要做难度就返回各档设置（settings.json 的 difficulty.tiers），否则 []；效果行要重随包里建过（features.json 的 difficulty）"""
    d = cx.S.get('difficulty') or {}
    if not cx.feat.get('difficulty') or not d.get('enabled', True):
        return []
    return d.get('tiers') or []


def base_id(cx):
    return int((cx.S.get('difficulty') or {}).get('base_id', 369000))


def normal(ts):
    """「普通」那一档：敌人血量、伤害都是 ×1 的第一档（和 rr/difficulty.py 的 normal_index 一样认）"""
    return next((k for k, t in enumerate(ts) if float(t.get('enemy_hp', 1)) == 1 and float(t.get('enemy_damage', 1)) == 1), 0)


def esd(cx, groups):
    ts = tiers(cx)
    if not ts:
        return
    p = menu_parts(groups, cx.root)
    add_cmd, conf_call, yes_eval, no_eval, ret, gid = (p[k] for k in ('add_cmd', 'conf_call', 'yes_eval', 'no_eval', 'ret', 'gid'))
    n = len(ts)
    nm = normal(ts)
    lk = locked_tiers(ts)
    lock_on = flag_is_on(LOCK)
    to = lambda target, ev: {'target': target, 'eval': ev, 'pass': [], 'sub': []}
    state = lambda entry, conds: {'entry': entry, 'exit': [], 'while': [], 'conds': conds}
    dialog = lambda text: {'bank': 1, 'id': 17, 'args': [i32(7), i32(text), i32(1), i32(0), i32(1)]}
    set_flag = lambda f, on: {'bank': 1, 'id': 11, 'args': [i32(f), i32(int(on))]}
    # 切档：点亮请求、当前档标记只留这一档
    switch = lambda k: [set_flag(REQ0 + k, 1)] + [set_flag(CUR0 + j, j == k) for j in range(n)]
    # 状态 0：按当前档位标记跳到对应的「建列表」状态（那一档用带图标的文字）；锁了的用 60 + 档位那套
    conds0 = []
    if lk:
        conds0 += [to(60 + k, both(flag_is_on(CUR0 + k), lock_on)) for k in range(n)] + [to(60 + lk[0], lock_on)]
    conds0 += [to(40 + k, flag_is_on(CUR0 + k)) for k in range(n)] + [to(40 + nm, ALWAYS)]
    st = {0: state([], conds0),
          # 1：没锁的列表等选择：lock 档先过门槛（GATE0 + 档位：击败过黑剑才走三个确认框 70 + 档位），别的照旧（10 + 档位）
          1: state([], [to((GATE0 if k in lk else 10) + k, menu_pick(k + 1)) for k in range(n)] + [to(9, ALWAYS)]),
          9: state([], [ret])}

    def build(cur, locked):
        """建列表：当前档带图标；锁了的话没标 lock 的档变灰、写「（已锁定）」"""
        cmds = [{'bank': 1, 'id': 12, 'args': []}, {'bank': 1, 'id': 20, 'args': []}]
        for k in range(n):
            text = TIER_LOCKED_TEXT + k if locked and k not in lk else (CUR_TEXT if k == cur else TIER_TEXT) + k
            cmds.append(dict(add_cmd, args=[i32(k + 1), i32(text), i32(-1)]))
        cmds += [dict(add_cmd, args=[i32(99), i32(26000004), i32(-1)]), {'bank': 1, 'id': 10, 'args': [i32(1)]}]
        return state(cmds, [to(2 if locked else 1, MENU_WAIT)])
    for cur in range(n):
        st[40 + cur] = build(cur, False)
    for k in range(n):
        st[10 + k] = state([dict(conf_call, args=[i32(DESC_TEXT + k)])], [to(10 + n + k, yes_eval), to(0, no_eval)])
        st[10 + n + k] = state(switch(k) + [dialog(DONE_TEXT + k)], [to(9, DIALOG_WAIT)])
    if lk:
        # 门槛：黑剑没击败、存档也没解锁（同一个存档里有角色七道咒痕都反转了，dark_core saveunlock.rs 点亮；没有咒痕就只看黑剑）才拦下
        unlock = (cx.feat.get('curses') or {}).get('unlock')
        gate = both(flag_is_off(RELEASE_FLAG), flag_is_off(unlock)) if unlock else flag_is_off(RELEASE_FLAG)
        # 2：锁了的列表等选择：lock 档之间照旧（10 + 档位，只弹效果说明、不复活），别的提示已锁定（30 + 档位）
        st[2] = state([], [to((10 if k in lk else 30) + k, menu_pick(k + 1)) for k in range(n)] + [to(9, ALWAYS)])
        for cur in range(n):
            st[60 + cur] = build(cur, True)
        for k in range(n):
            if k not in lk:
                st[30 + k] = state([dialog(LOCKED_NOTE)], [to(0, DIALOG_WAIT)])
                continue
            st[GATE0 + k] = state([], [to(GATE_SAY, gate), to(70 + k, ALWAYS)])
            st[70 + k] = state([dict(conf_call, args=[i32(DESC_FIRST_TEXT + k)])], [to(100 + k, yes_eval), to(0, no_eval)])
            st[100 + k] = state([dict(conf_call, args=[i32(CONFIRM_MID_TEXT + k)])], [to(80 + k, yes_eval), to(0, no_eval)])
            st[80 + k] = state([dict(conf_call, args=[i32(CONFIRM2_TEXT + k)])], [to(90 + k, yes_eval), to(0, no_eval)])
            st[90 + k] = state(switch(k) + [set_flag(LOCK, 1), dialog(DONE_FIRST_TEXT + k)], [to(REVIVE0, DIALOG_WAIT)])
        # 复活：头目复活列表里的标记全部熄灭，每个状态 REVIVE_CHUNK 条
        flags = revive_flags()
        chunks = [flags[i:i + REVIVE_CHUNK] for i in range(0, len(flags), REVIVE_CHUNK)] or [[]]
        for j, ch in enumerate(chunks):
            st[REVIVE0 + j] = state([set_flag(f, 0) for f in ch], [to(REVIVE0 + j + 1 if j + 1 < len(chunks) else REVIVE_DONE, ALWAYS)])
        st[REVIVE_DONE] = state([dialog(LOCK_DONE)], [to(9, DIALOG_WAIT)])
        st[GATE_SAY] = state([dialog(GATE_NOTE)], [to(0, DIALOG_WAIT)])
        cx.notes.append('难度：%s 要先击败黑剑（标记 %d%s）才能进入，进入后锁定（标记 %d），进入时复活 %d 个标记（含 Boss 房赐福 %d 个的传送 / 点亮标记 %d 个）' % (
            '、'.join(ts[k]['name'] for k in lk), RELEASE_FLAG, '；存档解锁标记 %d 亮着不用' % unlock if unlock else '', LOCK, len(flags),
            len(boss_graces()), len(boss_grace_flags())))
    groups[gid] = st
    register(cx, 'difficulty', TEXT, gid)          # 收进赐福最上面的「暗黑重铸」（sc/forge.py）


def texts(cx, key):
    ts = tiers(cx)
    if not ts:
        return {}
    out = {TEXT: 'Difficulty' if key == 'en' else '难度调整'}
    hpu = set((cx.feat.get('hp_unify') or {}).get('flags') or ())     # 高难度血量补正生效的档（rr/hpunify.py）
    extras = {}                                                        # 死亡、不可能的说明（放第二个框，确认框只显示前 3 行）
    ovl = bool(cx.feat.get('overlimit'))                               # 超限锻造石（rr/overlimit.py）：标了 lock 的档里掉
    for k, t in enumerate(ts):
        h, d = t.get('enemy_hp', 1), round(float(t.get('enemy_damage', 1)), 2)     # 受到的伤害 2.2222222 → 2.22
        rb, db = float(t.get('rune_bonus', 0)) * 100, float(t.get('discovery_bonus', 0)) * 100
        name = t.get('name_en', t['name']) if key == 'en' else t['name']
        dealt = round(1.0 / float(h), 2)                 # enemy_hp 的做法是你造成的伤害 ÷ 它（rr/difficulty.py），这里照实写
        sr = round(float(t.get('status_resist', 1)), 2) if CUR0 + k in hpu else 1    # 敌人的异常抗性（rr/hpunify.py）
        lore = LORE.get(t['name'], ('', ''))[1 if key == 'en' else 0]
        out[TIER_TEXT + k] = name
        out[CUR_TEXT + k] = '%s %s' % (MARK_IMG, name)
        if key == 'en':
            pe = ', poise damage you deal x%g' % t['poise_dealt'] if 'poise_dealt' in t else ''
            rune = 'Runes %+d%%, discovery %+d' % (rb, db) if rb or db else 'Runes and discovery unchanged'
            extra = ', and '.join(x for x in ('enemies and bosses gain much more HP and attack' if CUR0 + k in hpu else '',
                                              'enemies may drop Overlimit Smithing Stones' if ovl and t.get('lock') else '') if x)
            # 确认框实测只显示前 3 行（用户 2026-11-06 截图），后面的直接切掉：不写难度名和「只影响自身」，卢恩才排得进第 3 行
            lines = ([lore] if lore else []) + ['Damage you deal x%g, damage you take x%g%s' % (dealt, d, pe)]
            lines += [rune]
            extras[k] = extra[:1].upper() + extra[1:] + '.' if extra else ''
            if sr != 1:
                extras[k] += ('\n' if extras[k] else '') + 'Enemy status resistance x%g.' % sr
            out[DESC_TEXT + k] = '\n'.join(lines) + '\n\nSwitch to this difficulty?'
            out[DONE_TEXT + k] = 'You now walk the path of %s.' % name + ('\n' + extras[k] if extras[k] else '')
        else:
            pz = '，造成的削韧 ×%g' % t['poise_dealt'] if 'poise_dealt' in t else ''
            rune = '卢恩 %+d%%，观察力 %+d' % (rb, db) if rb or db else '卢恩、观察力不变'
            extra = '，'.join(x for x in ('敌人与头目的血量、攻击力大幅提升' if CUR0 + k in hpu else '',
                                         '有几率掉落超限锻造石' if ovl and t.get('lock') else '') if x)
            # 确认框实测只显示前 3 行（用户 2026-11-06 截图），后面的直接切掉：不写难度名和「只影响自身」，卢恩才排得进第 3 行
            lines = ([lore] if lore else []) + ['造成的伤害 ×%g，受到的伤害 ×%g%s' % (dealt, d, pz)]
            lines += [rune]
            extras[k] = extra + '。' if extra else ''
            if sr != 1:
                extras[k] += ('\n' if extras[k] else '') + '敌人的异常抗性 ×%g。' % sr
            out[DESC_TEXT + k] = '\n'.join(lines) + '\n\n切换到这个难度吗？'
            out[DONE_TEXT + k] = '已走上「%s」的道路。' % name + ('\n' + extras[k] if extras[k] else '')
    # 高难度单程票的文字：第一个框（效果说明 + 建议）、第二个框（不可逆 + 最后确认）、灰掉的档、提示
    lk = locked_tiers(ts)
    if lk:
        en = key == 'en'
        below = [t for k, t in enumerate(ts) if k < lk[0]]
        top = (below[-1].get('name_en', below[-1]['name']) if en else below[-1]['name']) if below else ''
        for k in lk:
            t = ts[k]
            name = t.get('name_en', t['name']) if en else t['name']
            body = out[DESC_TEXT + k].rsplit('\n\n', 1)[0]
            if en:
                out[DESC_FIRST_TEXT + k] = body + '\n\nSwitch to this difficulty?'
                out[CONFIRM_MID_TEXT + k] = '\n'.join(x for x in (extras[k], 'Recommended only after defeating Promised Consort Radahn in the Realm of Shadow.', 'Continue?') if x)
                out[CONFIRM2_TEXT + k] = 'This character can never return to %s or below.\nAll bosses will be revived, and graces inside boss arenas must be lit again.\nFinal confirmation: enter %s?' % (top, name)
                out[DONE_FIRST_TEXT + k] = 'You now walk the path of %s.' % name
            else:
                out[DESC_FIRST_TEXT + k] = body + '\n\n切换到这个难度吗？'
                out[CONFIRM_MID_TEXT + k] = '\n'.join(x for x in (extras[k], '建议先在幽影之地击败「约定之王」拉塔恩，再踏上这条路。', '继续吗？') if x)
                out[CONFIRM2_TEXT + k] = '这个角色再也不能切回「%s」及以下的难度。\n所有头目都会复活，头目房间里的赐福要重新点亮。\n最后确认：确定进入「%s」吗？' % (top, name)
                out[DONE_FIRST_TEXT + k] = '已走上「%s」的道路。' % name
        for k, t in enumerate(ts):
            if k not in lk:
                name = t.get('name_en', t['name']) if en else t['name']
                out[TIER_LOCKED_TEXT + k] = "<font color='%s'>%s%s</font>" % (LOCKED_COLOR, name, ' (locked)' if en else '（已锁定）')
        # 命定之死由黑剑玛利喀斯封印，击败他才释放（门槛）；进入是褪色者自己踏上这条路（用户「应该是褪色者主动踏上 而不是被找上」），回不了头
        if en:
            out[GATE_NOTE] = 'Destined Death has yet to be released.'
            out[LOCKED_NOTE] = 'You have set foot on the path where Destined Death returns. There is no turning back.'
            out[LOCK_DONE] = 'All bosses have been revived; they reappear after you rest or re-enter the area.\nGraces inside boss arenas must be lit again.\nThis character can no longer return to %s or below.' % top
        else:
            out[GATE_NOTE] = '命定之死尚未被释放。'
            out[LOCKED_NOTE] = '你已踏上命定之死回归的道路，不能再回头。'
            out[LOCK_DONE] = '所有头目已复活，休息或重新进入区域后出现。\n头目房间里的赐福要重新点亮。\n这个角色从此不能再切回「%s」及以下的难度。' % top
    return {'EventTextForTalk': out}


def events(cx, e, ev0):
    ts = tiers(cx)
    if not ts:
        return
    if not cx.common:
        raise RuntimeError('加载的包里没有公共事件脚本，难度切换做不了')
    if any(ev['id'] in (EVENT, INIT_EVENT, GRACE_FIX_EVENT) for ev in e['events']):
        raise RuntimeError('公共事件 %d / %d / %d 已存在' % (EVENT, INIT_EVENT, GRACE_FIX_EVENT))
    if len(ts) > MAX:
        raise RuntimeError('难度最多 %d 档（settings.json 的 difficulty.tiers 有 %d 档）：再多标记会和一键出售撞上' % (MAX, len(ts)))
    n, nm, b0 = len(ts), normal(ts), base_id(cx)
    flag = lambda f, on: emevd.ins(2003, 66, ('u8', 0), ('u32', f), ('u8', int(on)))
    skip_flag = lambda lines, on, f: emevd.ins(1003, 1, ('u8', lines), ('u8', int(on)), ('u8', 0), ('u32', f))     # 标记是 on 就跳过
    skip_has = lambda lines, has, sp: emevd.ins(1004, 0, ('u8', lines), ('u32', 10000), ('s32', sp), ('u8', int(has)), ('s8', 0), ('s32', 1))

    # 每档的效果：主效果 + 卢恩 / 发现力加成的单独效果（rr/difficulty.py 建，带圣甲虫图标；features.json 的 difficulty_extra）
    extra = cx.feat.get('difficulty_extra') or {}
    sps = [[b0 + j] + [int(x) for x in extra.get(str(j), [])] for j in range(n)]

    def put(k):
        """清掉各档的效果，挂上第 k 档（主效果 + 加成效果）"""
        return [emevd.ins(2004, 21, ('u32', 10000), ('s32', s)) for j in range(n) for s in sps[j]] + \
            [emevd.ins(2004, 8, ('u32', 10000), ('s32', s)) for s in sps[k]]
    body = []
    for k in range(n):                       # 选档：请求标记亮了就换成这一档、熄灭请求
        act = put(k) + [flag(REQ0 + k, False)]
        body += [skip_flag(len(act), False, REQ0 + k)] + act
    for k in range(n):                       # 补挂：当前档的标记亮着、身上却没有这一档的效果（读档、死后、被别的东西清掉）就重新挂上
        act = put(k)
        body += [skip_flag(1 + len(act), False, CUR0 + k), skip_has(len(act), True, b0 + k)] + act
    body += [emevd.ins(1001, 0, ('f32', 0.5)), emevd.ins(1000, 4, ('u8', 1))]                            # 等 0.5 秒，重新开始
    e['events'].append({'id': EVENT, 'rest': 0, 'ins': body, 'params': []})
    # 读档后跑一次：一个当前档标记都没亮（新角色）时，身上有某一档的效果就点亮那一档，否则点亮「普通」
    init = [emevd.ins(1001, 0, ('f32', 2.0))]
    tail = 3 * n + 1                         # 后面「按身上的效果认」每档 3 行 + 最后点亮「普通」1 行
    for k in range(n):
        init.append(skip_flag((n - 1 - k) + tail, True, CUR0 + k))          # 有一档亮着：什么都不做
    for k in range(n):
        init += [skip_has(2, False, b0 + k), flag(CUR0 + k, True), emevd.ins(1000, 3, ('u8', 3 * (n - 1 - k) + 1))]
    init.append(flag(CUR0 + nm, True))
    e['events'].append({'id': INIT_EVENT, 'rest': 0, 'ins': init, 'params': []})
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', EVENT), ('u32', 0)))
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', INIT_EVENT), ('u32', 0)))
    graces, stale = grace_fix_event(), stale_fix()
    fix = graces + stale
    if fix:
        e['events'].append({'id': GRACE_FIX_EVENT, 'rest': 0, 'ins': fix, 'params': []})
        ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', GRACE_FIX_EVENT), ('u32', 0)))
    cx.notes.append('局内难度 %d 档（读档修 Boss 房赐福点亮标记 %d 个、复活后残留的 Boss 标记 %d 个）' % (
        n, len(graces) // 3, len(revivefix.STALE_WHEN_ALIVE)))
