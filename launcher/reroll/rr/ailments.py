# -*- coding: utf-8 -*-
"""发狂、咒死重做（ailment_rework，用户 2026-10-29，参考法魂，全局：敌人对玩家的也一样）。

- 所有敌人都会中发狂、咒死（resist）：敌人参数里发狂 / 咒死抗性是 999（免疫）的，改成这个敌人自己的冻伤抗性 × resist_mult
  （冻伤免疫就依次看出血、中毒、腐败、睡眠；原版这几项一般一样大），发作后的抗性成长表也照那一项；
  五项都免疫的（多半不是活物）照旧免疫（同法魂）。原来就不是 999 的不动。要在复制敌人参数的步骤之前做，复制出来的跟着改。
  咒死 / 发狂抗性不是 999 的敌人，参数里挂的效果 90030 / 90060 去掉（那一格改成 -1，同法魂）：这两个效果只有「咒死无效」/「发狂无效」
  一位，原版挂在九成敌人身上，挂着它怎么打都不累积（用户 2026-10-30 报 Souls Vision 里咒死条打了也不涨；抗性模块里咒死一直是满的）。
- 发狂发作（effects）：累积效果自己带发作的数值（原版扣最大生命 15% + 100、专注 10% + 30），改成只扣最大生命 madness_hp_pct%；
  硬直同出血（用户 2026-11-09，sc/hks.py 的 MADNESS_FLINCH：c0000.hks 里发狂不再放 W_DamageMad 整段动作，和出血、冻伤一样升级成小硬直；
  玩家和用 c0000 脚本的人形角色生效，别的模型的敌人硬直写在它们自己的脚本里）。连带效果 102370 → 502 → 弹体 1020 → 503（状态 495）不是硬直，
  是给周围角色的「附近发狂」通知（出血同样 500 → 1000 → 501，状态 379），照旧。另外 dll\\dark_core 看到敌人身上新出现发狂类的效果（发作时挂 1 秒），
  把它的架势扣掉上限的 madness_poise_pct%（runtime.txt 的 madpoise 行；最低压到 1，下一下打崩，同千钧）。
- 咒死发作（effects）：累积效果发作时换成效果 70（即死，状态 117 由引擎处理）；改成换成新效果 DOOM_SP（照 70 复制、去掉状态 117）：
  death_secs 秒内毒、腐败、出血、冻伤、睡眠、发狂六种异常的抗性 × (1 - death_resist_cut%)（咒死自己不降，同法魂），
  再发作刷新时间、不叠加。效果 70 本身不动（没人再换成它）。
  咒死累积效果的持续时间原版是 0，照法魂改成 0.1 秒（用户 2026-10-29 报 Souls Vision 看不到敌人的咒死累积；
  法魂让敌人能中咒死，这几行都是 0.1，原版只有玩家挨咒死、没有打敌人的情况）。
- 敌人强度缩放类的效果（原版各地区 7000 起、随机器的缩放、幽影之地的……：六种异常抗性同一个倍率、咒死是 1）咒死也乘这个倍率
  （effects）：原版咒死不在缩放里，敌人身上咒死上限只有别的异常的一半左右；用户要和其他异常一样。
- 发狂 / 咒死发作的特效（effects，用户 2026-10-30「即死和发狂的特效也补一下」）：用原版玩家发狂硬直、咒死死亡动作
  （a000_017170 / 017160 的 TAE）里的特效，都在常驻特效包里：发狂 4210（头 907，爆一下）+ 4220（原版在两眼 845/846，
  敌人没有这两个点，改在头 907）；咒死 4230（身体 905）+ 4231（脚下 900）。做成两个 VFX_SECS 秒的效果：
  咒死的由 DOOM_SP 开头触发一次（cycleOccurrence，间隔比持续时间长），玩家、敌人都有（玩家不再即死、没有死亡动作了）；
  发狂的由 dll\\dark_core 在敌人发狂发作时挂（runtime.txt 的 madvfx 行）；玩家和人形角色由 c0000.hks 在发作时挂（整段动作去掉了，动作里的特效也没了）。
effects 要在所有会加带异常的效果行的步骤之后（词条库、开局装备、追忆、许愿……）。
"""
from .common import *  # noqa: F401,F403

DOOM_SP = 7299100
MADNESS_STATE, CURSE_STATE = 437, 116
VANILLA_DOOM = 70
IMMUNE_SP = {'resist_curse': 90030, 'resist_madness': 90060}   # 敌人参数挂的「咒死无效」「发狂无效」效果（disableCurse / disableMadness）
CURSE_ENDURANCE = 0.1                    # 咒死累积效果的持续时间：原版 0 改成法魂的 0.1 秒
MAD_VFX_SP, DOOM_VFX_SP = 7299110, 7299120   # 发狂 / 咒死发作的特效效果（SpEffectParam）
VFX_ROWS = {MAD_VFX_SP: [((4210, 907), (4220, 907))], DOOM_VFX_SP: [(None, (4230, 905)), (None, (4231, 900))]}  # 特效行：(发动时, 持续中) 的 (特效, 点位)
VFX_TEMPLATE = 260                       # 特效行的底子：原版冻伤发作的（大型敌人也显示、死了也显示）
VFX_SP_TEMPLATE = 90030                  # 特效效果的底子：原版只有「咒死无效」一位的效果（对谁都生效），去掉那一位
VFX_SECS = 3.0
DEFAULT = dict(madness_hp_pct=5.0, madness_poise_pct=30.0, death_resist_cut=30.0, death_secs=60.0, resist_mult=1.0)
BASES = ('resist_freeze', 'resist_blood', 'resist_poison', 'resist_desease', 'resist_sleep')
CORRECT = {'resist_freeze': 'resistCorrectId_freeze', 'resist_blood': 'resistCorrectId_blood', 'resist_poison': 'resistCorrectId_poison',
           'resist_desease': 'resistCorrectId_disease', 'resist_sleep': 'resistCorrectId_sleep'}
LOWERED = ('registPoizonChangeRate', 'registDiseaseChangeRate', 'registBloodChangeRate', 'registFreezeChangeRate',
           'registSleepChangeRate', 'registMadnessChangeRate')


def cfg(S):
    c = S.get('ailment_rework') or {}
    if not c.get('enabled', True):
        return None
    return {k: float(c.get(k, v)) for k, v in DEFAULT.items()}


def _lay(ctx, xml):
    return {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, xml + '.xml')))[0]}


def _get(L, row, f):
    return struct.unpack_from('<' + L[f][1], row, L[f][2])[0]


def _put(L, row, f, v):
    struct.pack_into('<' + L[f][1], row, L[f][2], v)


def resist(ctx):
    c = cfg(ctx.S)
    if c is None:
        return
    L = _lay(ctx, 'NpcParam')
    N = erlib.Param(ctx.bnd.get('NpcParam.param'))
    changed, still = Counter(), Counter()
    slots = [f for f in L if f.startswith('spEffectID')]
    for row in N.rows.values():
        base = next((f for f in BASES if _get(L, row, f) not in (999, 0)), None)
        for f, rc in (('resist_madness', 'resistCorrectId_madness'), ('resist_curse', 'resistCorrectId_curse')):
            if _get(L, row, f) != 999:
                continue
            if base is None:
                still[f] += 1
                continue
            _put(L, row, f, min(998, max(1, int(round(_get(L, row, base) * c['resist_mult'])))))
            _put(L, row, rc, _get(L, row, CORRECT[base]))
            changed[f] += 1
        for f, sp in IMMUNE_SP.items():
            if _get(L, row, f) != 999:
                for s in slots:
                    if _get(L, row, s) == sp:
                        _put(L, row, s, -1)
                        changed[sp] += 1
    ctx.bnd.put('NpcParam.param', N.serialize())
    ctx.report.append('发狂 / 咒死抗性：原来免疫的敌人参数改成照冻伤（或出血 / 中毒 / 腐败 / 睡眠）抗性 ×%g：发狂 %d 行、咒死 %d 行；'
                      '去掉「咒死无效」效果 %d 的 %d 行、「发狂无效」效果 %d 的 %d 行；'
                      '五项都免疫的照旧免疫：发狂 %d 行、咒死 %d 行' % (c['resist_mult'], changed['resist_madness'], changed['resist_curse'],
                                                         IMMUNE_SP['resist_curse'], changed[IMMUNE_SP['resist_curse']],
                                                         IMMUNE_SP['resist_madness'], changed[IMMUNE_SP['resist_madness']],
                                                         still['resist_madness'], still['resist_curse']))


def effects(ctx):
    c = cfg(ctx.S)
    if c is None:
        return
    L = _lay(ctx, 'SpEffect')
    S = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    if DOOM_SP in S.rows:
        raise RuntimeError('特殊效果 %d 已经有人用了（咒死的新效果）' % DOOM_SP)
    n_mad = n_cur = 0
    touched = []
    for rid, row in S.rows.items():
        if _get(L, row, 'madnessAttackPower') > 0 and _get(L, row, 'stateInfo') == MADNESS_STATE:
            _put(L, row, 'changeHpRate', c['madness_hp_pct'])
            for f in ('changeHpPoint', 'changeMpPoint'):
                _put(L, row, f, 0)
            _put(L, row, 'changeMpRate', 0.0)
            touched.append(rid)
            n_mad += 1
        elif _get(L, row, 'curseAttackPower') > 0 and _get(L, row, 'replaceSpEffectId') == VANILLA_DOOM:
            _put(L, row, 'replaceSpEffectId', DOOM_SP)
            if _get(L, row, 'effectEndurance') == 0:
                _put(L, row, 'effectEndurance', CURSE_ENDURANCE)
            touched.append(rid)
            n_cur += 1
    # 强度缩放：六种异常抗性倍率都一样、咒死是 1 的，咒死也照这个倍率
    n_scale = 0
    for rid, row in S.rows.items():
        v = [_get(L, row, f) for f in LOWERED]
        if abs(_get(L, row, 'registCurseChangeRate') - 1) < 1e-6 and abs(v[0] - 1) > 1e-6 and max(v) - min(v) < 1e-6:
            _put(L, row, 'registCurseChangeRate', v[0])
            touched.append(rid)
            n_scale += 1
    vfx(ctx, S, L)
    doom = bytearray(S.rows[VANILLA_DOOM])
    # 发作时触发一次咒死特效（间隔比持续时间长：只在开头）
    _put(L, doom, 'cycleOccurrenceSpEffectId', DOOM_VFX_SP)
    _put(L, doom, 'motionInterval', c['death_secs'] + 1.0)
    _put(L, doom, 'stateInfo', 0)
    _put(L, doom, 'effectEndurance', c['death_secs'])
    for f in LOWERED:
        _put(L, doom, f, 1.0 - c['death_resist_cut'] / 100.0)
    S.add_row(DOOM_SP, doom)
    ctx.bnd.put('SpEffectParam.param', S.serialize())
    # 词条库自带的发狂 / 咒死效果行也改了：写出去后的核对（affixes.verify）按改后的比
    ctx.patched_rows = getattr(ctx, 'patched_rows', {})
    ctx.patched_rows.update({('SpEffectParam', rid): bytes(S.rows[rid]) for rid in touched})
    ctx.report.append('发狂发作：%d 行改成扣最大生命 %g%%、不扣专注（硬直同出血，见 sc/hks.py；架势扣上限 %g%% 由 dark_core 做）；'
                      '咒死发作：%d 行从即死改成效果 %d（%g 秒内六种异常抗性 -%g%%）；强度缩放效果 %d 行的咒死抗性倍率跟别的异常一样' % (
                          n_mad, c['madness_hp_pct'], c['madness_poise_pct'], n_cur, DOOM_SP, c['death_secs'], c['death_resist_cut'], n_scale))


def runtime_lines(ctx):
    """runtime.txt：madpoise <架势扣上限的 %>、madvfx <敌人发狂发作时挂的特效效果>"""
    c = cfg(ctx.S)
    if not c:
        return []
    out = ['madpoise\t%g' % c['madness_poise_pct']] if c['madness_poise_pct'] > 0 else []
    if getattr(ctx, 'ailment_vfx', False):
        out.append('madvfx\t%d' % MAD_VFX_SP)
    return out


def _putbit(L, row, f, on):
    o, bit = L[f][2], L[f][3]
    row[o] = (row[o] | (1 << bit)) if on else (row[o] & ~(1 << bit))


def vfx(ctx, S, L):
    """发狂 / 咒死发作的特效行（SpEffectVfxParam）和特效效果（SpEffectParam）"""
    VP = erlib.Param(ctx.bnd.get('SpEffectVfxParam.param'))
    VL = _lay(ctx, 'SpEffectVfx')
    for sp, rows in VFX_ROWS.items():
        if sp in S.rows:
            raise RuntimeError('特殊效果 %d 已经有人用了（发作特效）' % sp)
        r = bytearray(S.rows[VFX_SP_TEMPLATE])
        _putbit(L, r, 'disableCurse', False)
        _put(L, r, 'effectEndurance', VFX_SECS)
        for k, (init, midst) in enumerate(rows):
            vid = sp + k
            if vid in VP.rows:
                raise RuntimeError('特效行 %d 已经有人用了' % vid)
            v = bytearray(VP.rows[VFX_TEMPLATE])
            for f in ('midstSfxId', 'initSfxId', 'finishSfxId', 'midstDmyId', 'initDmyId', 'finishDmyId'):
                _put(VL, v, f, -1)
            _put(VL, v, 'wetAspectType', 0)       # 冻伤模板带的（湿的样子、脚步特效）不要
            _put(VL, v, 'footEffectOffset', 0)
            for pair, (fs, fd) in ((init, ('initSfxId', 'initDmyId')), (midst, ('midstSfxId', 'midstDmyId'))):
                if pair is not None:
                    _put(VL, v, fs, pair[0])
                    _put(VL, v, fd, pair[1])
            VP.add_row(vid, v)
            _put(L, r, 'vfxId' if k == 0 else 'vfxId%d' % k, vid)
        S.add_row(sp, r)
    ctx.bnd.put('SpEffectVfxParam.param', VP.serialize())
    ctx.ailment_vfx = True
