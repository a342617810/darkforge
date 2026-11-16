# -*- coding: utf-8 -*-
"""原版的闪烁提示（屏幕中间一行字、几秒后淡出；EMEVD 2007:4，文字在 EventTextForMap）：夺得魇火、魇印解锁 / 升级、开新刻印位、
咒痕碎片 / 反转的提示（用户 2026-11-03：夺取魇火的提示用原版提示框，不用 dark_ui 自己画的）。
dark_core（notes.rs）把要显示的编号（1~127）按位写进 BITS 这 7 个标记；公共事件（sc/notes.py）每 0.25 秒看一次，有编号就显示
TEXT0 + 编号那条文字、3 秒后熄灭这 7 个标记，dark_core 等它们全灭了再写下一条（排队，一条接一条）。
编号在这里按顺序分：dll\\dark_core\\notes.txt（bits、note <键> <编号>，键是 dark_core 里的写法）、features.json 的 notes（sc 建事件、写文字）。
暗黑商店分阶段解锁（rr/darkshop.py，用户 2026-11-04「每次解锁时提示“暗黑商店已经可以购买新物品” 用魇火那个提示」）：键 shop，放最后。
要在 nightmare.build、curses.build 之后。"""
from .common import *  # noqa: F401,F403
from . import curses as cs, darkshop, nightmare as nm

BITS = list(range(93093, 93100))         # 7 位，编号 1~127（dev\event_flags\说明.md；sc/notes.py 要求连号）
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
    if not rows:
        return
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
