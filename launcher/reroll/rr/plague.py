# -*- coding: utf-8 -*-
"""词条「疫病」dr_pestilence 的敌人一侧（用户 2026-11-04「增加一个护符 让所有敌人都能中毒和腐败 实现可以参考法魂」，
同日「改为不免疫所有异常 同时增加所有异常的抗性 传说无负面」；2026-11-06「疫病也应该是词条啊 以后也没有固定护符」改成词条）：
戴着时所有敌人都会陷入七种异常（中毒、腐败、出血、冻伤、睡眠、发狂、咒死，原来免疫的也会），摘下恢复；
所有敌人的七种异常抗性 × (1 + 数值%)，普通 / 稀有 / 史诗 / 传说 100 / 83 / 67 / 50（原来免疫、降下来的也再乘这个；
2026-11-13 用户加强，以前 30 / 20 / 10 / 0）。

词条本身（标记、护符模板、文字、掉落权重、暗黑商店）和别的词条一样在词条库（extract_affixes.py），这里不管。
以前的固定护符 4141~4144 和标记 7305000~7305003 锁定给了这条词条（id_lock.json），老存档里的护符就是它的模板，照常生效。

法魂（Convergence）的「封印者宝石」（护符 9230）：戴着时敌人身上有个标记，敌人的 HKS（Status.hks 的 StripImmunity）看到就摘掉
「中毒无效」「腐败无效」效果（90000 / 90010），再挂一个降抗性的效果（抗性 × 10%~90%），把 999 降到比它别的异常抗性的最高值高一点；
标记没了就挂回免疫效果。我们不改敌人的 HKS，由 dll\\dark_core 的 plague 模块做（每 0.5 秒扫一遍在场的敌人，只在戴着时扫）：
- 抗性倍率的效果：每种异常 STEPS 行，第 k 行（1~STEPS）这项抗性 × k%（registPoizonChangeRate 等）。dark_core 给每个敌人挂一行：
  原来免疫的挂「降到的比例 × (1 + 数值%)」，不免疫的挂「100 + 数值」（传说不加，不免疫的就什么都不挂）；
  第 100 行不变，只当记号（参数里抗性本来就不是 999、只挂着免疫效果的敌人）。
  摘下护符时 dark_core 按这组效果找回改过的敌人：摘掉它、挂回免疫效果（参数里本来就挂着的才挂）。
- 每个敌人参数降到多少（plague.txt 的 n 行）：抗性是 999 的，目标 = 这个敌人自己的冻伤抗性（冻伤免疫就依次看出血、另一种（腐败 / 中毒）、
  睡眠，同发狂 / 咒死的 rr/ailments.py）× resist_mult，几项都免疫的按 fallback；k = 目标 / 999。
  地区、随机器、周目的强度缩放六种异常同一个倍率，挂上去比例不变。
- 只摘纯粹的免疫效果 90000 / 90010 等（参数里只有那一位，同法魂）；别的带「中毒无效」「腐败无效」的（91000 全免疫、290 / 9642 /
  14500 / 14506、8200 / 8201 这些多半是剧情、特殊状态）不动，挂着它们的敌人参数不写（照旧免疫）。
n 行在写定义文件时按最终的敌人参数算。"""
from .common import *  # noqa: F401,F403

KEY = 'dr_pestilence'
POISON0, ROT0, STEPS = 7305100, 7305300, 200      # 第 k 行 = 抗性 × k%；最高 +100% 要到 200 行（各种异常的编号段正好隔 200）
BLOOD0, FROST0, SLEEP0, MAD0, CURSE0 = 7305500, 7305700, 7305900, 7306100, 7306300   # 2026-11-04 扩到七种异常
ENEMY_TEMPLATE = 90030              # 敌人身上的（同 rr/hpunify.py：去掉「咒死无效」那一位）
# (敌人参数的抗性, 原版的「XX无效」效果（只有那一位的：睡眠是 90300，挂在 5000 多行敌人参数上）, 效果里的免疫位, 抗性倍率起点, 效果里的倍率字段)
# 顺序就是 plague.txt 的 status / n 行的顺序（dark_core plague.rs 的 ZH 照这个）
STATUS = (('resist_poison', 90000, 'disablePoison', POISON0, 'registPoizonChangeRate'),
          ('resist_desease', 90010, 'disableDisease', ROT0, 'registDiseaseChangeRate'),
          ('resist_blood', 90020, 'disableBlood', BLOOD0, 'registBloodChangeRate'),
          ('resist_freeze', 90040, 'disableFreeze', FROST0, 'registFreezeChangeRate'),
          ('resist_sleep', 90300, 'disableSleep', SLEEP0, 'registSleepChangeRate'),
          ('resist_madness', 90060, 'disableMadness', MAD0, 'registMadnessChangeRate'),
          ('resist_curse', 90030, 'disableCurse', CURSE0, 'registCurseChangeRate'))
BASES = ('resist_freeze', 'resist_blood', 'resist_poison', 'resist_desease', 'resist_sleep')
DEFAULT = dict(resist_mult=1.0, fallback=400)
ZH = ('中毒', '腐败', '出血', '冻伤', '睡眠', '发狂', '咒死')


def cfg(S):
    return dict(DEFAULT, **(S.get('plague_talisman') or {}))


def family(ctx):
    """词条库里的这条词条（标记 sp、数值 runtime.vals）"""
    f = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))['gear'].get(KEY)
    if not f:
        raise RuntimeError('词条库里没有 %s（重跑 dev\\item_system\\extract_affixes.py）' % KEY)
    return f


def _lay(ctx, xml):
    return {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, xml + '.xml')))[0]}


def _get(L, row, f):
    v = struct.unpack_from('<' + L[f][1], row, L[f][2])[0]
    return (v >> L[f][3]) & ((1 << L[f][4]) - 1) if L[f][4] else v


def _put(L, row, f, v):
    if L[f][4]:
        o, b = L[f][2], L[f][3]
        row[o] = (row[o] | (1 << b)) if v else (row[o] & ~(1 << b))
    else:
        struct.pack_into('<' + L[f][1], row, L[f][2], v)


def build(ctx):
    bnd = ctx.bnd
    L = _lay(ctx, 'SpEffect')
    S = erlib.Param(bnd.get('SpEffectParam.param'))
    for rid in [b + k for _f, _i, _d, b, _r in STATUS for k in range(STEPS)]:
        if rid in S.rows:
            raise RuntimeError('词条疫病：效果编号 %d 已经有人用了' % rid)
    for _f, imm, _d, base, rate in STATUS:
        for k in range(1, STEPS + 1):
            row = bytearray(S.rows[ENEMY_TEMPLATE])
            _put(L, row, 'disableCurse', 0)
            _put(L, row, 'iconId', -1)
            _put(L, row, 'effectEndurance', -1.0)
            _put(L, row, 'spCategory', 0)
            _put(L, row, rate, k / 100.0)
            S.add_row(base + k - 1, bytes(row))
    bnd.put('SpEffectParam.param', S.serialize())
    ctx.plague = cfg(ctx.S)
    ctx.report.append('词条疫病：抗性倍率效果 %s 起各 %d 行（dark_core 挂）' % (
        ' / '.join('%s %d' % (z, b) for z, (_f, _i, _d, b, _r) in zip(ZH, STATUS)), STEPS))


def def_lines(ctx):
    """plague.txt：mark 各稀有度的标记效果；raise 各稀有度敌人抗性加多少 %；
    status 序号 免疫效果（-1 = 没有）抗性倍率效果起点 行数（STATUS 的顺序）；n 敌人参数 各异常第几行（STATUS 的顺序）位（第 j 位 = 参数里挂着第 j 种的免疫效果）
    第几行 0 = 不免疫（或挂着别的免疫效果），只按稀有度加抗性"""
    c = getattr(ctx, 'plague', None)
    if not c:
        return []
    f = family(ctx)
    L = _lay(ctx, 'NpcParam')
    SL = _lay(ctx, 'SpEffect')
    N = erlib.Param(ctx.bnd.get('NpcParam.param'))
    S = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    others = {d: {r for r, row in S.rows.items() if _get(SL, row, d)} - {imm} for _f, imm, d, _b, _r in STATUS}
    slots = [s for s in L if s.startswith('spEffectID')]
    lines = ['mark ' + ' '.join(str(f['sp'][r]) for r in RAR), 'raise ' + ' '.join(map(str, f['runtime']['vals']))] + \
        ['status %d %d %d %d' % (j, imm, base, STEPS) for j, (_f, imm, _d, base, _r) in enumerate(STATUS)]
    n = Counter()
    for nid in sorted(N.rows):
        row = N.rows[nid]
        sps = {_get(L, row, s) for s in slots}
        ks, bits = [], 0
        for j, (fld, imm, d, _b, _r) in enumerate(STATUS):
            v = _get(L, row, fld)
            has = imm > 0 and imm in sps                # 睡眠没有免疫效果（-1；空的效果栏也是 -1）
            if sps & others[d] or not (has or v >= 999):
                ks.append(0)
                n['skip' if sps & others[d] else 'ok', j] += 1
                continue
            if v >= 999:
                base = next((b for b in BASES if b != fld and _get(L, row, b) not in (999, 0)), None)
                tgt = _get(L, row, base) * float(c['resist_mult']) if base else float(c['fallback'])
                n['fallback' if base is None else 'cut', j] += 1
                ks.append(max(1, min(99, int(round(tgt / 999.0 * 100)))))
            else:
                n['strip', j] += 1
                ks.append(100)
            bits |= (1 << j) if has else 0
        if any(ks):
            lines.append('n %d %s %d' % (nid, ' '.join(map(str, ks)), bits))
    ctx.report.append('词条疫病：敌人参数 %d 行要摘免疫（各异常：抗性 999 照别的异常降 / 都免疫按 %d / 只摘免疫效果 / 挂着别的免疫效果不动）%s' % (
        sum(l.startswith('n ') for l in lines), int(c['fallback']),
        '；'.join('%s %d / %d / %d / %d' % (z, n['cut', j], n['fallback', j], n['strip', j], n['skip', j]) for j, z in enumerate(ZH))))
    return lines
