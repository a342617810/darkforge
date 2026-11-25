# -*- coding: utf-8 -*-
"""原版的闪烁提示（屏幕中间一行字、几秒后淡出；EMEVD 2007:4，文字在 EventTextForMap）：夺得魇火、魇印解锁 / 升级、开新刻印位、
咒痕碎片 / 反转的提示（用户 2026-11-03：夺取魇火的提示用原版提示框，不用 dark_ui 自己画的）。
dark_core（notes.rs）把要显示的编号（1~127）按位写进 BITS 这 7 个标记；公共事件（sc/notes.py）每 0.25 秒看一次，有编号就显示
TEXT0 + 编号那条文字、3 秒后熄灭这 7 个标记，dark_core 等它们全灭了再写下一条（排队，一条接一条）。
编号在这里按顺序分：dll\\dark_core\\notes.txt（bits、note <键> <编号>，键是 dark_core 里的写法）、features.json 的 notes（sc 建事件、写文字）。
暗黑商店分阶段解锁（rr/darkshop.py，用户 2026-11-04「每次解锁时提示“暗黑商店已经可以购买新物品” 用魇火那个提示」）：键 shop，放最后。
要在 nightmare.build、curses.build 之后。"""
from .common import *  # noqa: F401,F403
from . import containers, curses as cs, darkshop, nightmare as nm

# 8 位，编号 1~255（dev\event_flags\说明.md；sc/notes.py 要求连号）。原来是 93093~93099 七位（最多 127 条），
# 2026-11-16 加联机赠送的三条后放不下，挪到扫过没人用的 92560~92567（只在显示时临时点亮，挪了不影响存档）
BITS = list(range(92560, 92568))
TEXT0 = 80095000                         # EventTextForMap：TEXT0 + 编号
ROMAN = ('', 'I', 'II', 'III', 'IV')     # 游戏字体里没有 Ⅰ~Ⅳ


def build(ctx):
    """[(键, 中文, 英文)]，下标 + 1 就是编号"""
    ctx.notes = None
    rows = []
    if getattr(ctx, 'nightmare', None):
        lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))['gear']
        names = [(lib[key]['suffix'][1], lib[key]['suffix'][0][:1].upper() + lib[key]['suffix'][0][1:]) for key, _b in nm.FAMILIES]   # 英文名首字母大写
        for k, (zh, en) in enumerate(names):
            rows.append(('seize %d' % k, '夺得魇火：%s' % zh, 'Nightmare Ember seized: %s' % en))
        for k, (zh, en) in enumerate(names):
            for lv in range(1, len(ctx.nightmare['levels']) + 1):
                rows.append(('level %d %d' % (k, lv),
                             '魇印「%s」已解锁' % zh if lv == 1 else '魇印「%s」升至 %s' % (zh, ROMAN[lv]),
                             'Seal unlocked: %s' % en if lv == 1 else 'Seal upgraded: %s %s' % (en, ROMAN[lv])))
        for n in range(1, nm.NSLOT + 1):
            rows.append(('slot %d' % n, '第 %d 个刻印位已开启' % n, 'Seal slot %d opened' % n))
    if getattr(ctx, 'curses', None):
        tx = cs.texts(ctx.curses)
        need = int(ctx.curses['shards'])
        for r, (_rz, _re, key) in enumerate(cs.REGIONS):
            zh, en = tx[key][0], tx[key][1]
            for n in range(1, need):
                rows.append(('shard %d %d' % (r, n), '获得咒痕碎片：%s %d / %d' % (zh, n, need), 'Cursemark shard: %s %d / %d' % (en, n, need)))
            rows.append(('rev %d' % r, '咒痕「%s」已反转为祝福' % zh, 'Cursemark reversed into a blessing: %s' % en))
        if ctx.curses.get('revive'):                # 复活的那一下（dark_core 的 curses.rs）
            rows.append(('revive', cs.GIFT[0], cs.GIFT[1]))
    if darkshop.staged_cfg(ctx.S):
        rows.append(('shop', '暗黑商店新增了交易项目。', 'New items have been added to the Dark Shop.'))
    # Boss 模组按角色难度自动加载（rr/bossmods.py、dark_core 的 bossmode.rs）：这次启动加载的世界和读进来的角色对不上时提示重启
    # （同时围屏障、禁止传送，barrier.rs）；对上了第一次进改版世界时提示 Boss 取回力量（一直加载的 on 模式也有）。放最后，不动前面的编号
    bm = ctx.S.get('boss_mods') or {}
    if bm.get('mode', 'off') in ('auto', 'on') and any(v for k, v in (bm.get('mods') or {}).items() if not k.startswith('_')):
        if bm.get('mode') == 'auto':
            rows.append(('boss on', '死亡以上难度的角色：请重启游戏，启动时选「死亡以上难度」',
                         'Death+ difficulty character: restart the game and choose Death+ difficulty at launch'))
            rows.append(('boss off', '不是死亡以上难度的角色：请重启游戏，启动时选「普通难度」',
                         'Not a Death+ difficulty character: restart the game and choose Normal difficulty at launch'))
        rows.append(('boss power', '部分追忆Boss已经取回真正的力量', 'Some remembrance bosses have regained their true power'))
    # 叙事提示（dev\\narrative\\叙事方案.md）：进入死亡以上的开场、每道咒痕反转后接一句、七道全部反转。放最后，不动前面的编号
    if getattr(ctx, 'curses', None):
        rows += [('open %d' % (i + 1), z, e) for i, (z, e) in enumerate(cs.OPEN_NOTES)]
        rows += [('revline %d' % r, cs.REV_NOTES[key][0], cs.REV_NOTES[key][1]) for r, (_rz, _re, key) in enumerate(cs.REGIONS)]
        rows.append(('all', cs.ALL_NOTE[0], cs.ALL_NOTE[1]))
    # 斗技场试炼死在里面（复活在赐福，竞技场里的提示看不到了）：放最后，不动前面的编号（竞技场里的提示走本图自己的标记，sc/arena.py）
    if getattr(ctx, 'arena', None):
        rows.append(('arena fail', '斗技场试炼失败，这次得到的奖励已经收回', 'Colosseum Trial failed. The rewards it gave were taken back'))
    # 联机装备赠送（联机计划 13.7，dark_core 的 gear/gift.rs）：放最后，不动前面的编号
    rows.append(('gift sent', '队友收下了你送的新装备', 'Your teammate received the gear you gave'))
    rows.append(('gift fail', '新装备没送出去，还在你这里', "The gear wasn't given and is still yours"))
    rows.append(('gift got', '收到队友送的新装备', 'You received gear from a teammate'))
    # 联机斗技场试炼（联机计划 13.13，dark_core 的 arena.rs）：队员这边的提示。放最后，不动前面的编号
    if getattr(ctx, 'arena', None):
        rows.append(('arena coop join', '房主开始了斗技场试炼，你也会被传进竞技场', 'The host started a Colosseum Trial. You are being brought in'))
        rows.append(('arena coop helper', '星光碎片不够：这次试炼你只能帮忙，不拿奖励', 'Not enough Starlight Shards: you can help in this trial but get no rewards'))
        rows.append(('arena coop down', '你倒下了：这次试炼给你的奖励会收回', 'You fell. The rewards this trial gave you will be taken back'))
        rows.append(('arena coop lost', '和房主断开了：斗技场试炼结束，奖励保留', 'Lost the host. The Colosseum Trial is over and you keep your rewards'))
    # 死亡惩罚（用户 2026-11-19，dark_core 的 gear/deathloss.rs）：复活后提示。放最后，不动前面的编号
    # 同一天用户「可以随着卢恩取回好了」：遗失的跟着血迹，取回卢恩时发回来（death back），没取回又死了永久没了（death gone）
    if getattr(ctx, 'containers', None) and containers.death_pct(ctx.S) > 0:
        rows.append(('death loss', '死亡时遗失了部分未鉴定物品，取回卢恩时一起取回', 'Some unidentified items were lost upon death. Recover your runes to get them back'))
        rows.append(('death back', '取回了死亡时遗失的未鉴定物品', 'Recovered the unidentified items lost upon death'))
        rows.append(('death gone', '没有取回的未鉴定物品永久遗失了', 'The unidentified items you did not recover are lost for good'))
    # 无尽试炼每波的奖励直接放进背包、不弹框（用户 2026-11-22「直接给+闪烁提示奖励已发放」，dark_core 的 gear/deathloss.rs direct_drain）：
    # 发完闪一下。放最后，不动前面的编号
    if getattr(ctx, 'arena', None):
        rows.append(('endless reward', '奖励已发放', 'Rewards delivered'))
    if len(rows) >= 1 << len(BITS):
        raise RuntimeError('原版提示：%d 条，%d 个标记放不下' % (len(rows), len(BITS)))
    ctx.notes = rows
    ctx.features['notes'] = {'bits': BITS, 'text0': TEXT0, 'zh': [z for _k, z, _e in rows], 'en': [e for _k, _z, e in rows]}
    ctx.report.append('原版闪烁提示：%d 条（文字 EventTextForMap %d 起，编号写进标记 %d~%d，公共事件见 sc/notes.py）' % (
        len(rows), TEXT0 + 1, BITS[0], BITS[-1]))


def def_lines(ctx):
    """dll\\dark_core\\notes.txt（格式见 dark_core 的 notes.rs）"""
    rows = getattr(ctx, 'notes', None)
    if not rows:
        return []
    return ['bits ' + ' '.join(map(str, BITS))] + ['note\t%s\t%d' % (key, v + 1) for v, (key, _z, _e) in enumerate(rows)]
