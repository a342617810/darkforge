# -*- coding: utf-8 -*-
"""词条「无形」dr_unseen（用户 2026-11-06「能不能加个词条实现黑夜魔法的效果 不会被读指令」，同日「只管远程箭和法术道具 近战不屏蔽」「喝药灵药也不拦截」）。

敌人的「读指令」这里管两路，近战普攻、跳劈、战灰、喝药、灵药、起跳都不管：
- 玩家脚本主动通知 AI（施法、蓄力施法）：sc/hks.py 的 AFFIX_UNSEEN 戴着时不发；
- 子弹：游戏决定要不要让 AI 知道这颗子弹时（2.7.1.0 的 0x49e610），子弹参数 isDisableAiProjectileDodge 开着就不通知；
  否则有攻击力就通知，没攻击力再看 isAiInterruptShootNoDamageBullet。原版黑夜魔法的根子弹攻击力是 0、不带特效，
  走的是后面这条；这里不用改子弹结构，dll\\dark_core 的 unseen 模块在戴着时把清单里子弹的这一位打开，摘下还原。

这里只写子弹清单 unseen.txt：箭和弩箭（同 affixes.ranged_hits）、法术、道具放的子弹，加上法球（迸发、星群直接发射），
再顺着 HitBulletID / intervalCreateBulletId 找子子弹。战灰、触发词条的子弹不算。
人形 NPC 可能和玩家共用一部分子弹行，它们的子弹在戴着时也不会被骨灰躲，影响很小，不单独区分。
"""
from .affixes import AMMO_TYPES
from .common import *  # noqa: F401,F403

KEY = 'dr_unseen'
PER_LINE = 200


def bullets(ctx, extra):
    lay = lambda n: {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, n + '.xml')))[0]}
    get = lambda L, row, f: struct.unpack_from('<' + L[f][1], row, L[f][2])[0]
    LB, LM, LG, LU, LW = lay('BehaviorParam'), lay('MagicParam'), lay('EquipParamGoods'), lay('BulletParam'), lay('EquipParamWeapon')
    U = erlib.Param(ctx.bnd.get('Bullet.param'))
    todo = list(extra)
    by_var = defaultdict(list)                  # 箭的行为：100000000 + 变体 × 1000（同 affixes.ranged_hits）
    for i, r in erlib.Param(ctx.bnd.get('BehaviorParam_PC.param')).rows.items():
        if get(LB, r, 'refType') == 1:
            by_var[i // 1000].append(get(LB, r, 'refId'))
    for i, r in erlib.Param(ctx.bnd.get('EquipParamWeapon.param')).rows.items():
        if get(LW, r, 'wepType') in AMMO_TYPES and i % 100 == 0 and get(LW, r, 'behaviorVariationId') > 0:
            todo += by_var.get(100000 + get(LW, r, 'behaviorVariationId'), [])
    for r in erlib.Param(ctx.bnd.get('Magic.param')).rows.values():
        todo += [get(LM, r, 'refId%d' % k) for k in range(1, 11) if get(LM, r, 'refCategory%d' % k) == 1]
    todo += [get(LG, r, 'refId_default') for r in erlib.Param(ctx.bnd.get('EquipParamGoods.param')).rows.values() if get(LG, r, 'refCategory') == 1]
    seen = set()
    while todo:
        b = todo.pop()
        if b in seen or b not in U.rows:
            continue
        seen.add(b)
        todo += [c for c in (get(LU, U.rows[b], 'HitBulletID'), get(LU, U.rows[b], 'intervalCreateBulletId')) if c > 0]
    return sorted(seen)


def def_lines(ctx):
    """unseen.txt：mark 词条标记；talisman 护符（开发工具用）；b 子弹编号…"""
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    f = lib['gear'].get(KEY)
    if not f:
        return []
    orbs = [t[2] for tiers in (lib.get('runtime', {}).get('bursts') or {}).values() for t in tiers if len(t) > 2]
    ids = bullets(ctx, orbs)
    log('  无形：箭、法术、道具的子弹 %d 行' % len(ids))
    out = ['mark ' + ' '.join(str(f['sp'][r]) for r in RAR if r in f['sp']),
           'talisman ' + ' '.join(str(f['tal'][r]) for r in RAR if r in f['tal'])]
    out += ['b ' + ' '.join(map(str, ids[i:i + PER_LINE])) for i in range(0, len(ids), PER_LINE)]
    return out
