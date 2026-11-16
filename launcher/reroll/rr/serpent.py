# -*- coding: utf-8 -*-
"""大蛇狩猎矛换成 DR 版本（serpent_hunter_dr，用户 2026-10-30「大蛇狩猎矛也改成 dr 的大蛇狩猎矛 读取拾取时人物加点 根据加点最高给补正和需求」）。
火山官邸那个光点（打拉卡德要用，删原版装备时留下的唯一一把）改成给开局装备编号段里第 SERPENT_OFF 个专用编号：
本体就是原来那把（战技、常驻效果照本体，keep），传说。dll\\dark_core 在人物拿到它、角色记录里还没有时按那时的属性生成：
主补正（最高的那项）放在最高的属性上，能力需求不超过那时的属性（拿到就能用），然后记进这个角色的记录（items.txt start 行最后一列 pick = 1）。
拿到之前显示的是一启动按种子生成的那一份。要在 remembrance.build 之后（开局装备的编号段、start_items）"""
from .common import *  # noqa: F401,F403
from . import once, startgear

SERPENT = 17030000               # 大蛇狩猎矛
SERPENT_OFF = 800                # 开局装备编号段里的位置（开局装备 0~499，追忆武器 500~699，支线武器 700~799）
LEGENDARY = 3


def build(ctx):
    c = ctx.S.get('serpent_hunter_dr') or {}
    if not c.get('enabled', True) or not getattr(ctx, 'containers', None):
        return
    W = erlib.Param(ctx.bnd.get('EquipParamWeapon.param'))
    if SERPENT not in W.rows:
        ctx.report.append('大蛇狩猎矛：武器参数里没有 %d，没换' % SERPENT)
        return
    if not hasattr(ctx, 'start_ids'):
        ctx.start_ids = (startgear.START_W0, 10000, startgear.START_P0, 100)
    if not hasattr(ctx, 'start_items'):
        ctx.start_items = []
    i = ctx.start_ids[0] + SERPENT_OFF * ctx.start_ids[1]
    if i in W.rows:
        raise RuntimeError('大蛇狩猎矛的编号 %d 已被占用' % i)
    lots = [r for r, row in sorted(ctx.P_mp.rows.items()) if any(cat == CAT_W and iid == SERPENT for _, cat, iid, _ in erlib.lot_slots(row))]
    if not lots:
        ctx.report.append('大蛇狩猎矛：地图掉落里没找到，没换')
        return
    wf = json.load(open(os.path.join(ctx.data_dir, 'weapon_fields.json'), encoding='utf-8'))
    origin = [(o, sz) for f, o, sz in wf['own'] if f.startswith('originEquipWep')]
    startgear.copy_weapon(W, origin, SERPENT, i)
    for r in lots:
        row = ctx.P_mp.rows[r]
        for k, cat, iid, _ in erlib.lot_slots(row):
            if cat == CAT_W and iid == SERPENT:
                struct.pack_into('<i', row, erlib.LOT_ID + 4 * k, i)
    # 种子按这一局的种子定（每次启动一样；不从 ctx.rng 取，不打乱后面步骤的随机数）
    seed = once.rng_for(ctx, 'serpent').getrandbits(62)
    ctx.start_items.append({'cat': 0, 'id': i, 'tier': LEGENDARY, 'base': SERPENT, 'seed': seed, 'maxreq': [99] * 5,
                            'top': int(c.get('scaling_top_pct', 30)), 'min_status': 0, 'keep': True, 'pick': True})
    ctx.bnd.put('EquipParamWeapon.param', W.serialize())
    startgear.placeholders(ctx, [i], [])
    ctx.report.append('大蛇狩猎矛：火山官邸的掉落（%s）换成 DR 版本 %d（传说，本体和战技照原来那把；拿到时按人物属性生成补正和能力需求，要 dll\\dark_core）' % (
        '、'.join(map(str, lots)), i))
