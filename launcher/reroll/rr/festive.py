# -*- coding: utf-8 -*-
"""庆典油脂改成「卢恩越多伤害越高」（settings.json 的 festive_grease）：
  - 油脂本身的两个效果（右手 / 左手武器各一个，GREASE_SP）：去掉圣属性 +100 和命中得卢恩（cycleOccurrenceSpEffectId），
    持续 duration 秒；武器上的特效、和其他油脂互相顶替都照旧；
  - 加 max_bonus_pct 个加伤效果 BASE_SP + k（k = 1~max_bonus_pct，造成的伤害 +k%：五种属性的 AttackRate 都是 1 + k/100，
    和「造成的伤害 +X%」类护符同一套字段），没图标；
  - dll\\dark_core 每秒看玩家身上有没有油脂效果：有就扣当前卢恩的 drain_pct_per_sec%，按扣完的卢恩换加伤档位
    （max_bonus_pct × min(卢恩, full_runes) ÷ full_runes，取整到 1%），油脂没了就摘掉。
    DLL 用的定义写在 dll\\dark_core\\festive.txt（reroll.py 的 write_festive_def）。"""
from .common import *  # noqa: F401,F403

GREASE = 2001600                              # 庆典油脂（DLC 道具）
GREASE_SP = (20501620, 20501622)              # 涂在右手 / 左手武器上的效果
BASE_SP = 369200                              # 加伤档位：BASE_SP + k = 伤害 +k%
TEMPLATE_SP = 360400                          # 长尾猫护符的效果：简单的常驻效果，拿来当底子（同 difficulty.py）
TIER_SECS = 5.0                               # 加伤档位的持续时间：DLL 每秒摘了重挂，DLL 不工作时几秒后自己消失
RATES = ('physicsAttackRate', 'magicAttackRate', 'fireAttackRate', 'thunderAttackRate', 'darkAttackRate')


def cfg(S):
    c = S.get('festive_grease') or {}
    if not c or not c.get('enabled', True):
        return None
    return dict(max_pct=max(1, min(100, int(round(float(c.get('max_bonus_pct', 50)))))), full=max(1, int(c.get('full_runes', 200000))),
                drain=max(0.0, float(c.get('drain_pct_per_sec', 1))), secs=max(1.0, float(c.get('duration', 60))))


def wan(n):
    return '%d万' % (n // 10000) if n % 10000 == 0 else '{:,}'.format(n)


def texts(c):
    """（道具简介, 说明里讲效果的那一段）：中文、英文"""
    zh_effect = '能涂在武器上，执行庆典祷告，\n持有的卢恩越多，造成的伤害越高\n（%s卢恩时提升%d%%），\n但每秒会消耗当前持有卢恩的%g%%。\n%g秒后，效果会消失。' % (
        wan(c['full']), c['max_pct'], c['drain'], c['secs'])
    en_effect = ('Coats armament, imparting a festive incantation: the more runes the wielder holds, the more damage they deal '
                 '(+%d%% at {:,} runes), but %g%% of held runes is consumed every second. The effect lasts %g seconds.'.format(c['full'])
                 % (c['max_pct'], c['drain'], c['secs']))
    return {'zh': ('能涂在武器上，持有的卢恩越多，造成的伤害越高，但会持续消耗卢恩', zh_effect),
            'en': ('Coats armament. The more runes held, the more damage dealt, but runes are steadily consumed', en_effect)}


def build(ctx):
    c = cfg(ctx.S)
    if not c:
        return
    import paramdef_min as pdm
    P = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    lay, _ = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))
    off = {n: (o, fc) for n, fc, o, *_ in lay}
    put = lambda row, n, v: struct.pack_into('<' + off[n][1], row, off[n][0], v)
    miss = [i for i in GREASE_SP + (TEMPLATE_SP,) if i not in P.rows]
    used = [BASE_SP + k for k in range(1, c['max_pct'] + 1) if BASE_SP + k in P.rows]
    if miss or used:
        raise RuntimeError('庆典油脂：缺少效果 %s / 效果编号 %s 已被占用' % (miss, used))
    for sid in GREASE_SP:
        row = P.rows[sid]
        for f, v in (('darkAttackPower', 0), ('cycleOccurrenceSpEffectId', -1), ('effectEndurance', c['secs'])):
            put(row, f, v)
    for k in range(1, c['max_pct'] + 1):
        row = bytearray(P.rows[TEMPLATE_SP])
        for f, v in (('iconId', -1), ('effectEndurance', TIER_SECS), ('fallDamageRate', 1.0)):
            put(row, f, v)
        for f in RATES:
            put(row, f, 1.0 + k / 100.0)
        P.add_row(BASE_SP + k, row)
    ctx.bnd.put('SpEffectParam.param', P.serialize())
    # 文字：简介整句换掉；说明换掉讲效果的那一段（第二段），制作材料和传说那两段不动
    for code, key in (('engus', 'en'), ('zhocn', 'zh')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        info, effect = texts(c)[key]
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for fmg in ('GoodsInfo_dlc01.fmg', 'GoodsCaption_dlc01.fmg'):
            if fmg not in mb.entries:
                continue
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            if fmg.startswith('GoodsInfo'):
                d[GREASE] = info
            elif d.get(GREASE):
                parts = d[GREASE].split('\n\n')
                d[GREASE] = '\n\n'.join(parts[:1] + [effect] + parts[2:]) if len(parts) >= 3 else d[GREASE] + '\n\n' + effect
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.report.append('庆典油脂：%g 秒内卢恩越多伤害越高（%s 卢恩时 +%d%%，加伤效果 %d~%d），每秒扣当前卢恩的 %g%%；去掉了圣 +100 和命中得卢恩；'
                      '扣卢恩、换档要 dll\\dark_core' % (c['secs'], wan(c['full']), c['max_pct'], BASE_SP + 1, BASE_SP + c['max_pct'], c['drain']))
