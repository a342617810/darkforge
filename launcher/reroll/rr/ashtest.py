# -*- coding: utf-8 -*-
"""骨灰词条的测试骨灰（用户 2026-11-09，提案见 dev\\item_system\\骨灰词条提案.md）：确认召唤物身上挂「命中时触发」效果能不能让它的攻击附带异常。
原版没有敌人 / 召唤物这么做（敌人的异常写在各自的攻击参数里），所以先做一个测试骨灰，在开发工具（F9）「骨灰词条测试」里发放：
  - 道具 GOODS：照「离群野狼的骨灰」（BASE，召唤 3 只狼）复制，召唤效果换成自己的 GOODS（照原版那一行复制），不能强化；
  - 召唤行：照原版那 3 行复制（BUDDY0 起），敌人参数换成复制出来的 NPC；
  - NPC：照原版野狼的敌人参数复制，空着的第一个特殊效果格挂 CARRIER；
  - CARRIER：照原版出血油脂的效果 3190（状态 152 + 命中时触发）复制，一直挂着、不放武器上的光效，命中时给目标挂 BUILDUP；
  - BUILDUP：照 3191（出血累积）复制，出血累积 BLOOD（提案里传说档的值）。
不生效就改走 dark_core：判定「召唤物打中」再给敌人挂累积。settings 的 ash_affix_test = false 不建。"""
from .common import *  # noqa: F401,F403

BASE = 232000                   # 离群野狼的骨灰（召唤 3 只）
GOODS = 299900                  # 测试骨灰的道具编号，也是它的召唤效果编号（原版骨灰都是道具编号 = 召唤效果编号）；dark_dev 的 ASH_TEST 同这个
BUDDY0 = 29990000
# 召唤物没有模型字段，模型从敌人参数编号推：1 + 四位模型号 + 四位（离群野狼 140700000 = 模型 4070）。2026-11-09 第一次用 199990000（模型 9999 不存在），
# 召唤登记了、血条出来了，但角色没生成。复制的那只要留在原来的模型段里
NPC = 140709900
CARRIER, BUILDUP = 7310000, 7310001
GREASE_CARRIER, GREASE_BUILDUP = 3190, 3191     # 原版出血油脂：载体（状态 152，命中时触发 3191）、出血累积 30
BLOOD = 40
# 道具的名字、简介、说明、召唤物名字（GoodsInfo2：左边骨灰血条上显示的名字，原版「离群野狼」；第一次没写，血条没名字）
TEXT = {'zh': ('测试骨灰：出血的离群野狼', '开发测试：召唤的野狼攻击附带出血累积',
               '开发工具发放的测试骨灰（骨灰词条的测试）。\n召唤 3 只离群野狼，每只身上带「攻击附带出血累积（%d）」的效果。\n'
               '用来确认召唤物身上挂「命中时触发」的效果能不能让它的攻击附带异常。' % BLOOD, '离群野狼（出血）'),
        'en': ('Test Ash: Bleeding Lone Wolves', 'Dev test: the summoned wolves inflict blood loss',
               'A test spirit ash from the dev tool (spirit ash affix test).\nSummons 3 lone wolves, each carrying "attacks build up blood loss (%d)".\n'
               'Checks whether an on-hit effect on a summon makes its attacks inflict a status.' % BLOOD, 'Lone Wolf (Bleed)')}


def _lay(ctx, xml):
    path = os.path.join(ctx.data_dir, xml + '.xml')
    if not os.path.exists(path):
        path = os.path.join(ctx.a.randomizer_dir or '', 'diste', 'Defs', xml + '.xml')
    return {n: (o, fc, bp, bits) for n, fc, o, bp, bits, _ in pdm.layout(pdm.load(path))[0]}


def _put(L, row, f, v):
    o, fc, bp, bits = L[f]
    if bits:
        raise RuntimeError('测试骨灰：%s 是位字段' % f)
    struct.pack_into('<' + fc, row, o, v)


def _get(L, row, f):
    o, fc, bp, bits = L[f]
    return struct.unpack_from('<' + fc, row, o)[0]


def _none(L, f):
    """「没有」的值：有符号字段 -1，无符号 0"""
    return 0 if L[f][1] in 'BHIQ' else -1


def build(ctx):
    if not ctx.S.get('ash_affix_test', True):
        return
    # BuddyParam 的字段表随整合包带在 data 里（2026-11-10：高难度世界 randomizer_hi 没有 diste，不开敌人随机时也没有随机器目录）
    bxml = os.path.join(ctx.data_dir, 'BuddyParam.xml')
    if not os.path.exists(bxml):
        ctx.report.append('测试骨灰：没有 BuddyParam 的字段表（%s），没做' % bxml)
        return
    LG, LS, LN = _lay(ctx, 'EquipParamGoods'), _lay(ctx, 'SpEffect'), _lay(ctx, 'NpcParam')
    LB = {n: (o, fc, bp, bits) for n, fc, o, bp, bits, _ in pdm.layout(pdm.load(bxml))[0]}
    G, S, B, N = (erlib.Param(ctx.bnd.get(x)) for x in ('EquipParamGoods.param', 'SpEffectParam.param', 'BuddyParam.param', 'NpcParam.param'))
    for name, P, ids in (('道具', G, [GOODS]), ('特殊效果', S, [GOODS, CARRIER, BUILDUP]), ('召唤', B, [BUDDY0 + k for k in range(8)]), ('敌人参数', N, [NPC])):
        taken = [i for i in ids if i in P.rows]
        if taken:
            raise RuntimeError('测试骨灰：%s编号 %s 已被占用' % (name, taken))
    rows = sorted((i, r) for i, r in B.rows.items() if _get(LB, r, 'triggerSpEffectId') == BASE)
    need = [(G, BASE), (S, BASE), (S, GREASE_CARRIER), (S, GREASE_BUILDUP)]
    if not rows or any(k not in P.rows for P, k in need):
        ctx.report.append('测试骨灰：原版的离群野狼骨灰 / 出血油脂效果不在，没做')
        return
    # 道具：同原版，召唤效果换成自己的，不能强化
    g = bytearray(G.rows[BASE])
    _put(LG, g, 'refId_default', GOODS)
    for f in ('reinforceGoodsId', 'reinforceMaterialId'):
        _put(LG, g, f, _none(LG, f))
    G.add_row(GOODS, bytes(g))
    # 召唤效果、命中时触发的载体、出血累积
    S.add_row(GOODS, bytes(S.rows[BASE]))
    c = bytearray(S.rows[GREASE_CARRIER])
    _put(LS, c, 'effectEndurance', -1.0)
    _put(LS, c, 'atkOccurrenceSpEffectId', BUILDUP)
    _put(LS, c, 'iconId', -1)
    for f in [f for f in LS if f.startswith('vfxId')]:
        _put(LS, c, f, -1)
    S.add_row(CARRIER, bytes(c))
    u = bytearray(S.rows[GREASE_BUILDUP])
    _put(LS, u, 'bloodAttackPower', BLOOD)
    S.add_row(BUILDUP, bytes(u))
    # 敌人参数：照原版那只复制，空着的第一个特殊效果格挂载体
    npc0 = _get(LB, rows[0][1], 'npcParamId')
    n = bytearray(N.rows[npc0])
    slot = next((f for f in sorted((f for f in LN if f.startswith('spEffectID')), key=lambda x: int(x[len('spEffectID'):])) if _get(LN, n, f) <= 0), None)
    if slot is None:
        raise RuntimeError('测试骨灰：敌人参数 %d 的特殊效果格都满了' % npc0)
    _put(LN, n, slot, CARRIER)
    N.add_row(NPC, bytes(n))
    for k, (_i, r) in enumerate(rows):
        b = bytearray(r)
        _put(LB, b, 'triggerSpEffectId', GOODS)
        if _get(LB, b, 'npcParamId') == npc0:
            _put(LB, b, 'npcParamId', NPC)
        B.add_row(BUDDY0 + k, bytes(b))
    for P, name in ((G, 'EquipParamGoods'), (S, 'SpEffectParam'), (B, 'BuddyParam'), (N, 'NpcParam')):
        ctx.bnd.put(name + '.param', P.serialize())
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for j, fmg in enumerate(('GoodsName.fmg', 'GoodsInfo.fmg', 'GoodsCaption.fmg', 'GoodsInfo2.fmg')):
            if fmg not in mb.entries:
                continue
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            d[GOODS] = TEXT[lang][j]
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.report.append('测试骨灰：道具 %d（照离群野狼的骨灰 %d），召唤 %d 行（%d 起），敌人参数 %d 的 %s 挂 %d（命中时给目标挂出血累积 %d 的 %d）；F9「骨灰词条测试」发放'
                      % (GOODS, BASE, len(rows), BUDDY0, NPC, slot, CARRIER, BLOOD, BUILDUP))
