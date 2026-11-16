# -*- coding: utf-8 -*-
"""用事件脚本放的音效（用户 2026-11-04「相杀的音效还没做」→ 光效行只能放 sfx 类、试了原版刀被弹开那声不响 →「剑心和ga是怎么做的」）：
光效行（SpEffectVfx）的音效按 sfx（s）类找，人物类（c）的放不出来；相杀用原版防御反击那一声 c 999999984（各类武器 XX030700 / XX032700
= 防御反击动作的第 0 帧，剑心修罗也把它加进了自己的弹刀动作；用户 2026-11-04 试听「第一个是原版防御反击的声音不是很搭」→「先这样吧
就用原版防御反击的声音吧」）。原版精准防御（偏折泪滴）动作第 0 帧的 s 111111111 / 111111122 光效行、事件脚本放都不响（要动作事件给的
武器参数），不用。所以用事件脚本的「播放音效」（EMEVD 2010:2 PlaySE，锚在玩家 10000 身上，类别随便选；用户试过能响）：
  - 每个音效一个标记（FLAGS，93645 起：以前商店版装备继承用过的空段，dev\\event_flags\\说明.md），公共事件（sc/sounds.py）每帧看一遍，
    亮着的放它的音效、熄灭；dark_core 要放就点亮（相杀：clash.rs 看到防御火花出现时）。晚一两帧，挡刀听不出来。
  - SOUNDS 第一个 = 相杀用的；后面几个是开发工具「相杀音效试听」的候选（点了 dark_core 点亮那个标记）。
定义：dll\\dark_core\\clash.txt 的 sound <标记>（相杀）、usound <标记>（装备工坊）、stest <标记> <类> <编号> <说明>（试听，dark_dev 照着出按钮）；
features.json 的 sounds（[[标记, 类别编号, 音效编号], ...]，sc 建事件）。
装备工坊（用户 2026-11-10「继承重铸和超限时加一个原版强化武器的音效」）：继承（含提取成护符）、重铸、超限、防具词条升级成功时
dark_core 点亮 usound 标记。强化武器那一声是菜单音效（f 类），编号写在程序里、菜单文件里没有：常驻音效库 cs_main 里存在的 f 类编号
（枚举 Play_f<9 位> 对事件表）中 50000~50700 这 9 个最像「菜单操作完成」那一组，还没听过确认 → 编号放 settings.json 的 workshop_sound
（默认 f50100，猜的），9 个都放进试听（F9「相杀火花测试」里的「事件脚本放音效」按钮），听好了改设置。
用户试听后「都不太好 能自己做或者搜索铁砧敲击的声音吗」（2026-11-10）→ 改成 dark_ui 放自己合成的铁砧声（dll\\dark_ui\\anvil.wav，
dev\\dark_ui\\sounds\\make_anvil.py）；workshop_sound 默认空 = 不用游戏音效（没有 usound 行），候选也拿掉了。
要换回游戏音效就在 settings.json 填 "f50100" 这样的编号（那时两种会一起响，把 dll\\dark_ui\\anvil.wav 删掉）。"""
from .common import *  # noqa: F401,F403

FLAGS = list(range(93645, 93657))        # 12 个（dev\event_flags\说明.md：93645~93673 空着）
TYPES = {'a': 0, 'c': 1, 'f': 2, 'o': 3, 'p': 4, 's': 5, 'm': 6, 'v': 7, 'x': 8, 'b': 9, 'g': 10}   # EMEVD 的 SoundType
# (键, 类, 编号, 说明)：都在常驻音效库 cs_main 里（解开 sd.bhd 对过事件名 Play_<类><9 位编号>）
SOUNDS = [
    ('clash', 'c', 999999984, '原版防御反击'),
    ('test', 's', 440550, '对照：黄金格挡'),
]
# 见切成立时的音效（用户 2026-11-12「见切成功时播放防御反击的音效 和相杀一样」→「有没有更合适一点的音效」）：单独一个标记（msound），
# 编号在 settings.json 的 mikiri_sound（"s440700" 这样写：类 + 编号）。试听过闪避 / 格挡类战技动作里放的、在常驻音效库里的几个
# （a756 猎犬步法 s440310、a757 潜雾猛禽 s440700、a755 碎步 s440060、a697 黄金格挡第二声 s440551；分段 = 600 + swordArtsTypeNew），
# 用户选了潜雾猛禽（被打中化成羽毛那一声），候选拿掉了；要再试听就把它们加回 MIKIRI_TRY
MIKIRI_DEFAULT = ('s', 440700)
MIKIRI_TRY = []
# 见切成立时的画面（用户 2026-11-13「见切触发时加个视觉特效 给我几个提案」→「用A吧」：羽毛四散）：潜雾猛禽化成羽毛那一下的原版特效
# （a757 动画 40010 第 0.17 秒，440700 + 440701 挂在 220 点，和音效 s440700 同一刻；都在常驻的 sfxbnd_commoneffects），
# 做成挂给自己的短效果（SpEffect + 两行 SpEffectVfx，底子同发狂特效 rr/ailments.py），dark_core 放见切音效的同一帧挂上（clash.txt 的 mvfx 行）。
# 特效放在「持续特效」（midst）那格、效果只持续 MIKIRI_VFX_SECS 秒：原版是动作事件放的（440700 放 0.20 秒、440701 放 0.26 秒），
# 事件一结束特效就收尾；第一版放在「起手特效」（init）那格，放出去就没人收，羽毛特效里循环的光晕一直留在身上
# （用户 2026-11-13「dev工具里挂了特效但是特效在人物身上的光晕没有正确结束」）。持续特效跟着效果走，效果结束就收
MIKIRI_VFX_SP = 7299130          # 特效行 7299130、7299131（7299100~7299129 是发狂 / 咒死的）
MIKIRI_VFX = [(440700, 220), (440701, 220)]
MIKIRI_VFX_SECS = 0.25
# 加速期间的光晕（用户 2026-11-13「影步持续时间内保留这个光晕特效」「其他加速也挂这个特效」）：潜雾猛禽羽毛特效里的 440701，
# 放在「持续特效」格，加进所有动作加快的状态效果（词条库里带 haste / act_speed 的规则挂的 effect / fx：处刑、转念；影步见下面 LATE_GLOW_SP），
# 效果在多久光晕就在多久，摘掉就收。F9「效果调试」有两个 3 秒的对比效果（DEV_GLOW_SP：440700 / 440701 各一个）。
# 以前用 440700（带通用光晕贴图 s10011）：它长在身体里面，穿着铠甲看不见；用户 2026-11-14 用 F9 对比只看得见 B = 440701，改用它
HASTE_GLOW_VFX = 7299132         # 第一个加速词条的光晕特效行（DEV_GLOW_SP 对比用的还是原版 440700 / 440701）
HASTE_GLOW = (440701, 220)
# 每个加速词条一行光晕（按词条键排序分）：(特效行, 特效)。特效是 440701 的原样副本（dev\item_system\make_sfx.py HASTE_GLOW_FXR）。
# 用户 2026-11-14「影步的持续光晕没有生效」：同一个特效同时挂在同一个挂点上，游戏只放一份——影步在见切那一刻挂上，
# 见切的羽毛特效（440700 + 440701，0.25 秒）收掉时连影步的光晕一起收了；影步和处刑同时在时也会这样。所以光晕不用原版编号，每个词条各用一份
HASTE_GLOWS = ((7299132, 990091), (7299136, 990092), (7299137, 990093))
# 见切触发的加速（影步）的光晕不放进加速效果里，单独建一个效果（从这个编号起，按词条键排序），dark_core 等翻滚完再挂、加速结束就摘
# （clash.txt 的 hglow 行；用户 2026-11-14「特效虽然能正常在调试工具中播放 但是实际触发时没有这个特效」）
LATE_GLOW_SP = 7299138
DEV_GLOW_SP = {7299133: (440700, 220), 7299134: (440701, 220)}     # 只给开发工具对比用：各挂 3 秒
DEV_GLOW_SECS = 3.0
# 只给开发工具试放用、直接指现成光效行的效果（用户 2026-11-13 词条特效）：效果编号 → 光效行；挂 DEV_GLOW_SECS 秒。
# 碎骨 / 千钧满蓄力出招期间的光（原版岩棘裂纹露滴 5805）在词条里是引擎管的状态效果，手动挂上会被引擎当场摘掉，所以另建一个 3 秒的
DEV_VFX_SP = {7299135: 5805}


def mikiri_sound(S):
    v = str((S or {}).get('mikiri_sound') or '').strip().lower()
    if v and v[0] in TYPES and v[1:].isdigit():
        return v[0], int(v[1:])
    return MIKIRI_DEFAULT


# 装备工坊成功时用游戏音效（settings.json 的 workshop_sound，"f50100" 这样写：类 + 编号；空 = 不用，dark_ui 放自己的铁砧声）


def workshop_sound(S):
    v = str((S or {}).get('workshop_sound') or '').strip().lower()
    if v and v[0] in TYPES and v[1:].isdigit():
        return v[0], int(v[1:])
    if v.isdigit():
        return 'f', int(v)
    return None


# 雷电羊球按住连滚（用户 2026-11-11）：循环段的原版音效静音了（rr/skillgems.py，加速后每秒响十来次），dark_core 每 gap_ms 毫秒
# 轮流点亮这两个标记放原版的滚动声（都在常驻音效库 cs_main，a713 40010 里原来就有：s440463 两次、s440462 一次）
RAM_SOUNDS = [('ram', 's', 440463, '雷电羊球滚动'), ('ram', 's', 440462, '雷电羊球滚动 2')]
RAM_GAP_MS = 450


def ram_cfg(S):
    c = (S or {}).get('ram_sound') or {}
    return bool(c.get('enabled', True)), int(c.get('gap_ms', RAM_GAP_MS) or RAM_GAP_MS)


def sound_list(S=None):
    """全部事件音效（按顺序配标记）：相杀、对照、见切、见切的试听候选、装备工坊（设了游戏音效才有）、雷电羊球（开着才有）"""
    w = workshop_sound(S)
    m = mikiri_sound(S)
    return list(SOUNDS) + [('mikiri', m[0], m[1], '见切（现在用的）')] + MIKIRI_TRY + \
        ([('workshop', w[0], w[1], '装备工坊')] if w else []) + (RAM_SOUNDS if ram_cfg(S)[0] else [])


def build(ctx):
    """features.json 的 sounds（新装备系统没开也建：只是几个空等的标记）"""
    lst = sound_list(ctx.S)
    if len(lst) > len(FLAGS):
        raise RuntimeError('事件音效：%d 个、标记只有 %d 个' % (len(lst), len(FLAGS)))
    ctx.features['sounds'] = {'list': [[FLAGS[k], TYPES[t], i] for k, (_key, t, i, _d) in enumerate(lst)]}
    mikiri_vfx(ctx)
    haste_glow(ctx)


def _vfx_row(ctx, VP, VL, vid, sfx, dmy):
    """一行只有持续特效的 SpEffectVfx（底子同发狂特效）"""
    from . import ailments
    if vid in VP.rows:
        raise RuntimeError('特效行 %d 已经有人用了' % vid)
    v = bytearray(VP.rows[ailments.VFX_TEMPLATE])
    for f in ('midstSfxId', 'initSfxId', 'finishSfxId', 'midstDmyId', 'initDmyId', 'finishDmyId'):
        ailments._put(VL, v, f, -1)
    ailments._put(VL, v, 'wetAspectType', 0)
    ailments._put(VL, v, 'footEffectOffset', 0)
    ailments._put(VL, v, 'midstSfxId', sfx)
    ailments._put(VL, v, 'midstDmyId', dmy)
    VP.add_row(vid, v)


def haste_glow(ctx):
    """加速期间的光晕：建光晕特效行，加进动作加快的状态效果空着的特效格；再建两个开发工具对比用的 3 秒效果"""
    import json
    from . import ailments
    S = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    VP = erlib.Param(ctx.bnd.get('SpEffectVfxParam.param'))
    L, VL = ailments._lay(ctx, 'SpEffect'), ailments._lay(ctx, 'SpEffectVfx')
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    by_key = {}                                    # 加速词条 → 它的效果行
    late = {}                                      # 见切触发的加速词条 → 加速秒数（光晕单独挂）
    for key, f in lib['gear'].items():
        for rule in (f.get('runtime') or {}).get('rules') or []:
            if any(x and x > 0 for x in (rule.get('haste') or []) + (rule.get('act_speed') or [])):
                if rule.get('event') == 'mikiri' and rule.get('haste_secs'):
                    late[key] = float(rule['haste_secs'])
                ids = by_key.setdefault(key, set())
                ids.update(x for x in rule.get('effect') or [] if x and x > 0)
                ids.update(x for grp in rule.get('fx') or [] for x in grp if x and x > 0)
    glow_vids = {vid for vid, _sfx in HASTE_GLOWS}
    slots = ['vfxId'] + ['vfxId%d' % k for k in range(1, 8)]
    done, full, used = [], [], []
    ctx.late_glows = []
    for i, key in enumerate(sorted(by_key)):
        vid, sfx = HASTE_GLOWS[min(i, len(HASTE_GLOWS) - 1)]   # 加速词条比光晕多时，多出来的共用最后一份
        if vid not in VP.rows:
            _vfx_row(ctx, VP, VL, vid, sfx, HASTE_GLOW[1])
        used.append('%s %d' % (key, sfx))
        if key in late:
            # 单独的光晕效果：持续时间同加速（dark_core 晚挂、到点摘；万一没摘也自己到期）
            sp = LATE_GLOW_SP + len(ctx.late_glows)
            if sp in S.rows:
                raise RuntimeError('特殊效果 %d 已经有人用了（见切加速的光晕）' % sp)
            r = bytearray(S.rows[ailments.VFX_SP_TEMPLATE])
            ailments._putbit(L, r, 'disableCurse', False)
            ailments._put(L, r, 'effectEndurance', late[key])
            ailments._put(L, r, 'vfxId', vid)
            S.add_row(sp, r)
            ctx.late_glows.append((key, sp))
            continue
        for sp in sorted(by_key[key]):
            if sp not in S.rows:
                continue
            r = bytearray(S.rows[sp])
            have = [ailments._get(L, r, f) for f in slots]
            if glow_vids & set(have):
                continue
            free = next((f for f, v in zip(slots, have) if v <= 0), None)
            if free is None:
                full.append(sp)
                continue
            ailments._put(L, r, free, vid)
            S.rows[sp] = r
            done.append(sp)
    # 词条库自己的行改了：登记进 patched_rows，最后的校验（affixes.verify）按改过的比（同 rr/ailments.py、rr/procs.py）
    ctx.patched_rows = getattr(ctx, 'patched_rows', {})
    ctx.patched_rows.update({('SpEffectParam', sp): bytes(S.rows[sp]) for sp in done})
    for sp, (sfx, dmy) in DEV_GLOW_SP.items():
        if sp in S.rows:
            raise RuntimeError('特殊效果 %d 已经有人用了（加速光晕对比）' % sp)
        r = bytearray(S.rows[ailments.VFX_SP_TEMPLATE])
        ailments._putbit(L, r, 'disableCurse', False)
        ailments._put(L, r, 'effectEndurance', DEV_GLOW_SECS)
        _vfx_row(ctx, VP, VL, sp, sfx, dmy)
        ailments._put(L, r, 'vfxId', sp)
        S.add_row(sp, r)
    for sp, vid in DEV_VFX_SP.items():
        if sp in S.rows:
            raise RuntimeError('特殊效果 %d 已经有人用了（开发工具试放词条特效）' % sp)
        if vid not in VP.rows:
            raise RuntimeError('开发工具试放词条特效：没有光效行 %d' % vid)
        r = bytearray(S.rows[ailments.VFX_SP_TEMPLATE])
        ailments._putbit(L, r, 'disableCurse', False)
        ailments._put(L, r, 'effectEndurance', DEV_GLOW_SECS)
        ailments._put(L, r, 'vfxId', vid)
        S.add_row(sp, r)
    ctx.bnd.put('SpEffectParam.param', S.serialize())
    ctx.bnd.put('SpEffectVfxParam.param', VP.serialize())
    ctx.report.append('加速光晕（原版 %d 的副本，每个词条一份：%s）：加进 %d 个动作加快的效果 %s%s；见切触发的单独挂（翻滚完再挂）：%s' % (
        HASTE_GLOW[0], '、'.join(used), len(done), done, '；特效格满了没加：%s' % full if full else '',
        '、'.join('%s 效果 %d' % kv for kv in ctx.late_glows) or '没有'))


def mikiri_vfx(ctx):
    """见切的羽毛特效：SpEffect MIKIRI_VFX_SP（挂给自己、MIKIRI_VFX_SECS 秒）+ 每个特效一行 SpEffectVfx（只有持续特效，效果结束就收）"""
    from . import ailments
    S = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    VP = erlib.Param(ctx.bnd.get('SpEffectVfxParam.param'))
    L, VL = ailments._lay(ctx, 'SpEffect'), ailments._lay(ctx, 'SpEffectVfx')
    if MIKIRI_VFX_SP in S.rows:
        raise RuntimeError('特殊效果 %d 已经有人用了（见切特效）' % MIKIRI_VFX_SP)
    r = bytearray(S.rows[ailments.VFX_SP_TEMPLATE])
    ailments._putbit(L, r, 'disableCurse', False)
    ailments._put(L, r, 'effectEndurance', MIKIRI_VFX_SECS)
    for k, (sfx, dmy) in enumerate(MIKIRI_VFX):
        vid = MIKIRI_VFX_SP + k
        if vid in VP.rows:
            raise RuntimeError('特效行 %d 已经有人用了（见切特效）' % vid)
        v = bytearray(VP.rows[ailments.VFX_TEMPLATE])
        for f in ('midstSfxId', 'initSfxId', 'finishSfxId', 'midstDmyId', 'initDmyId', 'finishDmyId'):
            ailments._put(VL, v, f, -1)
        ailments._put(VL, v, 'wetAspectType', 0)
        ailments._put(VL, v, 'footEffectOffset', 0)
        ailments._put(VL, v, 'midstSfxId', sfx)
        ailments._put(VL, v, 'midstDmyId', dmy)
        VP.add_row(vid, v)
        ailments._put(L, r, 'vfxId' if k == 0 else 'vfxId%d' % k, vid)
    S.add_row(MIKIRI_VFX_SP, r)
    ctx.bnd.put('SpEffectParam.param', S.serialize())
    ctx.bnd.put('SpEffectVfxParam.param', VP.serialize())
    ctx.mikiri_vfx = MIKIRI_VFX_SP


def vfx_lines(ctx):
    """clash.txt 的 mvfx 行：见切成立时挂给自己的特效效果（这次重随建了才有）"""
    sp = getattr(ctx, 'mikiri_vfx', None)
    return (['mvfx %d' % sp] if sp else []) + ['hglow %s %d' % kv for kv in getattr(ctx, 'late_glows', [])]


def clash_lines(S=None):
    """clash.txt 里的音效行（rr/affixes.py clash_lines 接在后面）"""
    out, ram = [], []
    for k, (key, t, i, desc) in enumerate(sound_list(S)):
        if key == 'clash':
            out.append('sound %d' % FLAGS[k])
        if key == 'workshop':
            out.append('usound %d' % FLAGS[k])
        if key == 'mikiri':
            out.append('msound %d' % FLAGS[k])
        if key == 'ram':
            ram.append(FLAGS[k])
        out.append('stest %d %s %d %s' % (FLAGS[k], t, i, desc))
    if ram:
        out.append('ramsound %d %s' % (ram_cfg(S)[1], ','.join(map(str, ram))))
    return out
