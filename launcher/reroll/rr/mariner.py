# -*- coding: utf-8 -*-
"""战灰「唤声船」（settings 的 mariner_boat）：乘上提比亚唤声船的灵船在地面上滑行。
  - 战灰 GEM（照原版「幻影共击」22500 复制）：所有武器类型都能装（canMountWep_* 全开，含法杖、圣印记、盾、弓），属性 13 种都能选；
    原版不能换战灰的法杖 / 圣印记（gemMountType 0、战技是「无战技」）改成能换（原版没有别的战灰能装到法杖 / 圣印记上，所以只多出这一个）；
    带专属战技的武器不动（用户 2026-10-29 定的）。
  - 技艺 ARTS：技艺类型 ARTS_TYPE（原版没有的编号，没有动画）。玩家脚本（sc/hks.py）认这个类型：按战技键不放动作，
    挂上请求标记 REQ_SP；dll\\dark_core 的 boat 模块看到就扣蓝、上船（移动、瞬移、下船都在 DLL 里，参数在 dll\\dark_core\\boat.ini）。
  - 船：BOAT_SP 挂着时显示灵船（自制特效 BOAT_FXR，模型是从唤声船 c4950 取出的船身、用原版的幽灵材质，dev\\item_system\\boat_model.py；
    WOOD_SP 是普通材质的木头船，boat.ini 的 look 选）和唤声船原版的船底雾气（MIST_FXR），挂点 900（脚底、跟着人物朝向）；
    上船 / 下船 / 瞬移落点挂 BLINK_SP（唤声船消失 / 出现的雾 BLINK_FXR）。
  - 坐姿（用户 2026-10-29：坐在王座上，参考唤声船 Boss）：玩家用不了唤声船的动作（骨架不同），用手势 sit_gesture（默认 91 盘腿坐）：
    船的效果挂着时玩家脚本放这个手势（坐下 → 一直坐着），DLL 挂 STAND_SP 时放起身、挂 JUMP_SP 时起跳（下船的过渡）。
  - 获取（用户 2026-11-09 改）：道具「唤声船的碎片」FRAG（关键道具，最多 1 个）。DLL 看原版唤声船所在三处 Boss 战的击败标记 BOSS_FLAGS
    （敌人随机后看位置，不看敌人是谁）：打赢第一处发碎片、点亮 FLAG_FRAG；第二处收走碎片、发战灰、点亮 FLAG_GEM；以后不再发。
    发货走新装备系统的发货表（dark_core gear）。
DLL 用的编号写在 dll\\dark_core\\boat.txt（reroll.py 的 write_dll_defs）。要在 affixes.build 之前（词条库的武器本体要带上改过的 gemMountType）"""
from .common import *  # noqa: F401,F403

GEM, GEM_TEMPLATE, GEM_ICON, GEM_SORT = 29500, 22500, 8351, 352095
ARTS, ARTS_TEMPLATE, ARTS_TYPE = 2900, 225, 990
FRAG, FRAG_TEMPLATE, FRAG_ICON, FRAG_SORT = 9170, 8105, 6099, 203195     # 碎片：照迪可达斯符节（关键道具），图标借「提比亚的唤声」
REQ_SP, BOAT_SP, BLINK_SP = 369400, 369401, 369402
JUMP_SP, STAND_SP, WOOD_SP = 369403, 369404, 369405       # 跳船标记、起身标记（DLL 下船时挂，玩家脚本照着起跳 / 站起来）、木头船（boat.ini 的 look = wood）
BOAT_VFX, MIST_VFX, BLINK_VFX, WOOD_VFX = 990021, 990023, 990022, 990024
BOAT_FXR, MIST_FXR, BLINK_FXR, WOOD_FXR = 990021, 649501, 649502, 990024
SIT_GESTURE = 91                                          # 坐姿：手势编号（动作 80000 + 编号 × 10），91 = 盘腿坐
BOAT_DMY, BLINK_DMY = 900, 900                                            # 900：脚底，跟着人物位置和朝向（c0000「SFX発生用_固定」）
FLAG_FRAG, FLAG_GEM = 93614, 93615
# 水唤村、壶村、亚坛高原的遗迹（m60_38_52）：击败标记（randomizer enemy.txt 的 DefeatFlag，第三处实体是 1038520340，标记不同号）
BOSS_FLAGS = (1045390800, 1039440800, 1038520800)
MARKER_TEMPLATE, VFX_TEMPLATE = 360400, 1709000
STAFF_TYPES, NO_SKILL = (57, 61), 10
BOAT_SECS = 16.0                                                          # 船的效果最长挂多久（DLL 下船时摘掉；DLL 不工作时自己消失）

TEXT = {
    'zh': dict(
        gem='战灰：唤声船',
        gem_info='能赋予武器属性、战技',
        gem_cap='能赋予武器属性、战技的战灰。\n属性为“标准”，战技如下：\n\n　战技：唤声船\n%s\n\n能在所有的武器使用。\n（含法杖、圣印记）',
        arts='唤声船',
        arts_cap='战技：唤声船\n\n%s',
        body='提比亚唤声船的灵船所化的战技。\n乘上灵船，在地面上高速滑行一段时间，\n移动速度是灵马的1.5倍，但无法跳跃。\n乘船时再次发动，能不消耗专注值，\n瞬间移动到前方。按下跳跃会离开灵船。',
        frag='唤声船的碎片',
        frag_info='在唤声船出没之地取胜后得到的碎片',
        frag_cap='提比亚的唤声船所留下的，\n灵船的碎片。\n\n水唤村、壶村与亚坛高原的遗迹，\n曾有唤声船出没。\n击败其中另一处的头目，\n碎片会化为战灰「唤声船」。'),
    'en': dict(
        gem="Ash of War: Mariner's Boat",
        gem_info='Grants affinities and skills to an armament',
        gem_cap='This Ash of War grants an armament the Standard affinity and the following skill:\n\n"Mariner\'s Boat: %s"\n\nUsable on all armaments, including staves and sacred seals.',
        arts="Mariner's Boat",
        arts_cap="Skill: Mariner's Boat\n\n%s",
        body="Skill born of the spectral boat of a Tibia Mariner. Ride the boat and glide across the land for a time "
             "at 1.5 times the speed of Torrent, but unable to jump. Using the skill again while aboard warps you ahead at no FP cost. "
             "Jump to leave the boat.",
        frag="Mariner's Boat Shard",
        frag_info='Shard found where a Tibia Mariner once sailed',
        frag_cap="A shard of the spectral boat left behind by a Tibia Mariner.\n\nMariners once haunted Summonwater Village, Jarburg and the "
                 "ruins of the Altus Plateau. Defeat the boss of another of these places, and the shard will become the Ash of War: Mariner's Boat."),
}


def cfg(S):
    c = S.get('mariner_boat') or {}
    if not c.get('enabled', True):
        return None
    return dict(fp=max(0, min(999, int(c.get('fp_cost', 20)))), sit=int(c.get('sit_gesture', SIT_GESTURE)))


def build(ctx):
    c = cfg(ctx.S)
    if not c:
        return
    lay = lambda xml: {n: (fc, o, bp, nb) for n, fc, o, bp, nb, _ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, xml)))[0]}
    Lg, Ls, Lw, Lo, Lsp, Lv = (lay(x) for x in ('EquipParamGem.xml', 'SwordArtsParam.xml', 'EquipParamWeapon.xml', 'EquipParamGoods.xml',
                                                  'SpEffect.xml', 'SpEffectVfx.xml'))

    def get(L, r, f):
        fc, o, bp, nb = L[f]
        return (r[o] >> bp) & ((1 << nb) - 1) if nb else struct.unpack_from('<' + fc, r, o)[0]

    def put(L, r, f, v):
        fc, o, bp, nb = L[f]
        if nb:
            r[o] = (r[o] & ~(((1 << nb) - 1) << bp)) | ((int(v) & ((1 << nb) - 1)) << bp)
        else:
            struct.pack_into('<' + fc, r, o, v)

    names = ('EquipParamGem', 'SwordArtsParam', 'EquipParamWeapon', 'EquipParamGoods', 'SpEffectParam', 'SpEffectVfxParam')
    G, A, W, O, SP, V = (erlib.Param(ctx.bnd.get(n + '.param')) for n in names)
    miss = [(n, i) for n, P, i in (('战灰', G, GEM_TEMPLATE), ('技艺', A, ARTS_TEMPLATE), ('道具', O, FRAG_TEMPLATE),
                                   ('效果', SP, MARKER_TEMPLATE), ('光效', V, VFX_TEMPLATE)) if i not in P.rows]
    used = [(n, i) for n, P, ids in (('战灰', G, [GEM]), ('技艺', A, [ARTS]), ('道具', O, [FRAG]),
                                     ('效果', SP, [REQ_SP, BOAT_SP, BLINK_SP, JUMP_SP, STAND_SP, WOOD_SP]),
                                     ('光效', V, [BOAT_VFX, MIST_VFX, BLINK_VFX, WOOD_VFX])) for i in ids if i in P.rows]
    if miss or used:
        raise RuntimeError('唤声船：缺少模板 %s / 编号已被占用 %s' % (miss, used))
    if any(get(Ls, r, 'swordArtsTypeNew') == ARTS_TYPE for r in A.rows.values()):
        raise RuntimeError('唤声船：技艺类型 %d 已经有人用了' % ARTS_TYPE)

    # 战灰：所有武器类型都能装，13 种属性都能选，默认标准
    g = bytearray(G.rows[GEM_TEMPLATE])
    for f in Lg:
        if f.startswith('canMountWep_'):
            put(Lg, g, f, 1)
        elif f.startswith('configurableWepAttr'):
            put(Lg, g, f, 1 if int(f[-2:]) <= 12 else 0)
    m0 = Lg['canMountWep_Dagger'][1]
    for bit in range(36, 44):           # DLC 的武器类型（格斗术 ~ 兽爪）在字段表里没有名字，是第 36~43 位（2026-11-04 补上）
        g[m0 + bit // 8] |= 1 << (bit % 8)
    for f, v in (('swordArtsParamId', ARTS), ('iconId', GEM_ICON), ('sortId', GEM_SORT), ('defaultWepAttr', 0), ('mountWepTextId', -1),
                 ('spEffectId0', -1), ('spEffectId1', -1), ('spEffectId2', -1)):
        put(Lg, g, f, v)
    G.add_row(GEM, bytes(g))
    # 技艺：没有动画的新类型，按战技键由玩家脚本转给 DLL；蓝耗写在四个按键上（面板显示、蓝不够时变灰）
    a = bytearray(A.rows[ARTS_TEMPLATE])
    for f, v in (('swordArtsTypeNew', ARTS_TYPE), ('textId', ARTS), ('aiUsageId', -1), ('useMagicPoint_L1', c['fp']), ('useMagicPoint_L2', c['fp']),
                 ('useMagicPoint_R1', c['fp']), ('useMagicPoint_R2', c['fp'])):
        put(Ls, a, f, v)
    A.add_row(ARTS, bytes(a))
    # 法杖 / 圣印记：原版不能换战灰、战技是「无战技」的改成能换（带专属战技的不动）
    n_staff = 0
    for i, r in W.rows.items():
        if get(Lw, r, 'wepType') in STAFF_TYPES and get(Lw, r, 'gemMountType') == 0 and get(Lw, r, 'swordArtsParamId') == NO_SKILL:
            put(Lw, r, 'gemMountType', 2)
            n_staff += 1
    # 碎片：关键道具，最多 1 个
    o = bytearray(O.rows[FRAG_TEMPLATE])
    for f, v in (('iconId', FRAG_ICON), ('sortId', FRAG_SORT), ('maxNum', 1), ('maxRepositoryNum', 1), ('isRemoveItem_forGameClear', 0)):
        put(Lo, o, f, v)
    O.add_row(FRAG, bytes(o))
    # 效果：请求标记（玩家脚本挂、DLL 看到就上船）、船（光效：灵船 + 船底雾气）、瞬移落点的雾
    def marker(secs, vfx=()):
        r = bytearray(SP.rows[MARKER_TEMPLATE])
        for f, v in (('iconId', -1), ('fallDamageRate', 1.0), ('spCategory', 0), ('effectEndurance', secs)):
            put(Lsp, r, f, v)
        for k, vid in enumerate(vfx):
            put(Lsp, r, 'vfxId' if k == 0 else 'vfxId%d' % k, vid)
        return bytes(r)
    SP.add_row(REQ_SP, marker(0.5))
    SP.add_row(BOAT_SP, marker(BOAT_SECS, (BOAT_VFX, MIST_VFX)))
    SP.add_row(WOOD_SP, marker(BOAT_SECS, (WOOD_VFX, MIST_VFX)))
    SP.add_row(BLINK_SP, marker(0.8, (BLINK_VFX,)))
    SP.add_row(JUMP_SP, marker(0.4))
    SP.add_row(STAND_SP, marker(1.0))
    for vid, (fxr, dmy) in ((BOAT_VFX, (BOAT_FXR, BOAT_DMY)), (MIST_VFX, (MIST_FXR, BOAT_DMY)), (BLINK_VFX, (BLINK_FXR, BLINK_DMY)),
                            (WOOD_VFX, (WOOD_FXR, BOAT_DMY))):
        r = bytearray(V.rows[VFX_TEMPLATE])
        put(Lv, r, 'midstSfxId', fxr)
        put(Lv, r, 'midstDmyId', dmy)
        put(Lv, r, 'isMidstFullbody', 0)
        V.add_row(vid, bytes(r))
    for n, P in zip(names, (G, A, W, O, SP, V)):
        ctx.bnd.put(n + '.param', P.serialize())

    # 文字
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        T = TEXT[lang]
        body = T['body'] if lang == 'en' else '\n'.join('　' + l for l in T['body'].split('\n'))
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for fmg, iid, txt in (('GemName.fmg', GEM, T['gem']), ('GemInfo.fmg', GEM, T['gem_info']), ('GemCaption.fmg', GEM, T['gem_cap'] % body),
                              ('ArtsName.fmg', ARTS, T['arts']), ('ArtsCaption.fmg', ARTS, T['arts_cap'] % T['body']),
                              ('GoodsName.fmg', FRAG, T['frag']), ('GoodsInfo.fmg', FRAG, T['frag_info']), ('GoodsCaption.fmg', FRAG, T['frag_cap'])):
            if fmg not in mb.entries:
                raise RuntimeError('唤声船：文字包里没有 %s' % fmg)
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            d[iid] = txt
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.features['mariner_boat'] = {'arts_type': ARTS_TYPE, 'req_sp': REQ_SP, 'boat_sps': [BOAT_SP, WOOD_SP], 'jump_sp': JUMP_SP,
                                    'stand_sp': STAND_SP, 'sit_gesture': c['sit']}
    ctx.report.append('战灰「唤声船」%d（技艺 %d，类型 %d，蓝 %d）：所有武器能装，%d 把法杖 / 圣印记改成能换战灰；碎片 %d；'
                      '打赢原版唤声船位置的 Boss（击败标记 %s）给碎片 / 战灰（标记 %d / %d）；骑船、瞬移、发货要 dll\\dark_core' % (
                          GEM, ARTS, ARTS_TYPE, c['fp'], n_staff, FRAG, BOSS_FLAGS, FLAG_FRAG, FLAG_GEM))


def def_lines(S):
    """dll\\dark_core\\boat.txt：一行一个「键<TAB>值」"""
    c = cfg(S)
    if not c:
        return []
    return ['gem\t%d' % GEM, 'frag\t%d' % FRAG, 'req_sp\t%d' % REQ_SP, 'boat_sp\t%d' % BOAT_SP, 'blink_sp\t%d' % BLINK_SP,
            'fp\t%d' % c['fp'], 'flag_frag\t%d' % FLAG_FRAG, 'flag_gem\t%d' % FLAG_GEM,
            'wood_sp\t%d' % WOOD_SP, 'jump_sp\t%d' % JUMP_SP, 'stand_sp\t%d' % STAND_SP] + ['boss_flag\t%d' % f for f in BOSS_FLAGS]
