# -*- coding: utf-8 -*-
"""补挂被顶掉的「命中时触发」（用户 2026-11-06「结冰油脂没生效」）。

玩家身上带 stateInfo 152 + atkOccurrenceSpEffectId 的效果，游戏只认一个（实测：结冰油脂 3140 挂满 60 秒，
戴着猎印、巨人杀手时 9 下命中冻伤一点不动；摘掉这些装备就好了）。听命中的词条标记（land）走的也是这条路，
所以戴着它们时，原版油脂、附魔祷告、蛇弓的命中效果都被顶掉了。

做法：这一下敌人身上真的出现了 land，就说明别的都被顶掉了，dll\\dark_core（rules.rs 的 atkfwd）把它们挂到这个敌人身上；
没出现 land（原版的那个排在前面，游戏自己挂了）就不补，不会算两次。

游戏不让 DLL 直接挂只有「命中时挂给对方」位的行（见 extract_affixes.py allow_direct），所以每个目标行建一份带「挂给自己」位的副本。
要放在所有改效果行的步骤之后（副本要带上霜铠的接线、发狂 / 咒死的改动）。
runtime.txt 的 atkfwd 行：atkfwd <玩家身上的效果> <补挂的副本> <wepParamChange：1 右手 / 2 左手 / 0 不分手>"""
from .common import *  # noqa: F401,F403

BASE, LIMIT = 7308000, 200              # 副本的编号段（不存进存档，每次重随重建）
HIT_STATE = 152                         # 同 extract_affixes.py ATK_OCCUR_STATE
# 同 extract_affixes.py DIRECT_TARGET_BITS，再加 effectTargetFriendlyTarget：和 buildup 那些已经在用的累积行一样
DIRECT_BITS = ('effectTargetSelf', 'effectTargetSelfTarget', 'effectTargetAI', 'effectTargetLive', 'effectTargetFriendlyTarget')


def build(ctx):
    ctx.atkfwd = []
    if not getattr(ctx, 'containers', None):
        return
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    land = lib['runtime']['marks'].get('land')
    if not land:
        return
    L = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}

    def get(row, f):
        v = struct.unpack_from('<' + L[f][1], row, L[f][2])[0]
        return (v >> L[f][3]) & ((1 << L[f][4]) - 1) if L[f][4] else v

    S = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    taken = [i for i in S.rows if BASE <= i < BASE + LIMIT]
    if taken:
        raise RuntimeError('命中效果副本：编号段 %d 起已经有人用了：%s' % (BASE, taken[:8]))
    direct = {}
    for buff in sorted(S.rows):
        row = S.rows[buff]
        if get(row, 'stateInfo') != HIT_STATE:
            continue
        target = get(row, 'atkOccurrenceSpEffectId')
        if target <= 0 or target == land or target not in S.rows or not get(S.rows[target], 'effectTargetEnemy'):
            continue
        if target not in direct:
            if len(direct) >= LIMIT:
                raise RuntimeError('命中效果副本：超过 %d 行' % LIMIT)
            copy = bytearray(S.rows[target])
            for n in DIRECT_BITS:
                copy[L[n][2]] |= 1 << L[n][3]
            direct[target] = BASE + len(direct)
            S.add_row(direct[target], bytes(copy))
        ctx.atkfwd.append('atkfwd\t%d\t%d\t%d' % (buff, direct[target], get(row, 'wepParamChange')))
    ctx.bnd.put('SpEffectParam.param', S.serialize())
    ctx.report.append('命中效果补挂：%d 个带命中时触发的效果（油脂、附魔祷告、蛇弓……）被命中标记 %d 顶掉时由 dark_core 补挂，副本 %d 行（%d 起）' % (
        len(ctx.atkfwd), land, len(direct), BASE))
