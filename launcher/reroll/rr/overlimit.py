# -*- coding: utf-8 -*-
"""超限锻造石（settings.json 的 overlimit；用户 2026-11-03，设计稿 dev\\item_system\\超限锻造石与高难度.md §1）：
  - 两个道具：武器 GOODS_W、防具 GOODS_A，强化材料类（照锻造石【1】，不能使用）。图标先借古龙岩锻造石 / 古龙岩失色锻造石的，
    菜单包里有 make_frames.py 画的自制图标（frames.txt 的 custom overlimit_w / overlimit_a 行）时 dark_core 换上。
  - 只在赐福「暗黑重铸」→「装备工坊」的「超限」页用（界面 dll\\dark_ui，执行 dll\\dark_core）：
    武器：这把所有有补正的项每颗各加一个步长，到这个稀有度（和补正项数）原上限 × weapon_cap 为止；
    防具：减伤倍率每颗加一个步长，到原上限 × armor_cap 为止。步长 = （超限上限 − 中位）÷ stones，按稀有度固定。
    超限过的武器不能再重铸；超限是装备本身的属性，所有难度都生效。
  - 掉落（drop_lines → dll\\dark_core\\ovldrop.txt，dark_core 的 ovldrop 模块）：只在 difficulty 里标了 lock 的档（死亡 / 不可能）；
    每场 Boss 战每档第一次击败给 boss_stones 颗（1 = 随机一种，2 = 各一颗；掉落追忆的头目给 remembrance_stones 颗，用户 2026-11-09），「掉过」记在 data\\boss_overlimit_flags.json 分好的标记里
    （dev\\item_system\\build_overlimit_flags.py 生成，不能改）；附近 range 米内的敌对角色死了按 mob_pct% 给 1 颗，Boss 位置、召唤物、训练木桩不算。
DLL 用的：items.txt 的 overlimit 行（lines，containers.write_def 调）；各稀有度的中位、原上限、超限上限在 affixes.txt 的 ovlw / ovlp 行
（affixes.write_def 按 weapon_scaling / armor_negation 的区间写，caps）。"""
from .common import *  # noqa: F401,F403

GOODS_W, GOODS_A = 9242, 9243            # 道具编号（重铸石 9240、融锻之心 9241 后面；原版没用）
TEMPLATE = 10100                         # 锻造石【1】：强化材料（goodsType 14）、不能使用
ICON_FROM = {GOODS_W: 10140, GOODS_A: 10200}   # 古龙岩锻造石 / 古龙岩失色锻造石的图标（自制图标在菜单包里时 dark_core 换上）
SORT = {GOODS_W: 160102, GOODS_A: 160103}      # 排在武器重铸石（160101）后面
DUMMY_NPC = 56009900                     # 训练木桩的敌人参数（rr/dummy.py 的 NPC_ID），死了不掉
# armor_stones：防具从中位到超限上限几颗（用户 2026-11-04「减少防具超限满所需个数 当前数量/2」：50 → 25；武器照旧 stones）
DEFAULT = dict(weapon_cap=1.1, armor_cap=1.2, stones=50, armor_stones=25)
# 按 lock 档的顺序：死亡、不可能（用户 2026-11-03）；boss_stones 2026-11-04「超限锻造石boss掉落数量翻5倍」1 / 2 → 5 / 10（武器 / 防具轮流给，第一颗随机）
# remembrance_stones：掉落追忆的头目（data\\remembrance_bosses.json 的 base / dlc 位置，不算 dlc_extra）的颗数（用户 2026-11-09「死亡追忆boss掉10个两种碎片吧 不可能20个」）
DROP_DEFAULT = dict(mob_pct=[10, 20], boss_stones=[5, 10], remembrance_stones=[10, 20], range=0)


def cfg(S):
    c = S.get('overlimit') or {}
    if not c.get('enabled', True):
        return None
    out = dict(DEFAULT)
    out.update({k: c[k] for k in DEFAULT if k in c})
    out['stones'] = max(1, int(out['stones']))
    out['armor_stones'] = max(1, int(out['armor_stones']))
    out['drops'] = dict(DROP_DEFAULT, **(c.get('drops') or {}))
    return out


def caps(S, lo, hi, which):
    """(中位, 原上限, 超限上限)：中位 = 区间中点（截断正态的均值），超限上限 = 原上限 × weapon_cap / armor_cap"""
    c = cfg(S)
    k = float(c['weapon_cap' if which == 'w' else 'armor_cap']) if c else 1.0
    return (lo + hi) / 2, hi, hi * k


def texts(c):
    """（名字, 简介, 说明）× 武器 / 防具：中文、英文"""
    wp, ap, n, na = round((c['weapon_cap'] - 1) * 100), round((c['armor_cap'] - 1) * 100), c['stones'], c['armor_stones']
    drop_zh = '在「死亡」「不可能」难度里击败敌人时有几率获得；每个头目在每个难度第一次被击败时必定获得数颗，掉落追忆的头目给得更多。'
    drop_en = 'Dropped by enemies on the Death and Impossible difficulties; every boss gives several the first time it falls on each of those difficulties, remembrance bosses more.'
    zh = {
        GOODS_W: ('超限锻造石（武器）', '装备工坊「超限」消耗的材料（武器）',
                  '命定之死的封印解开后才出现的锻造石，带有些微死亡的气息。能将武器强化至超过原本的上限。\n\n'
                  '圆桌厅堂的铁匠修古向玛莉卡女王立下誓言，要锻造弒神武器。无论锻造出多少把，他都只说一句：\n　这种东西哪能杀害神祇？\n\n'
                  '在赐福「暗黑重铸」→「装备工坊」的「超限」里，选背包里的一把新武器：每颗让它所有有补正的能力各提高一点，'
                  '最多到这个稀有度原上限再高 %d%%（一般约 %d 颗到顶）。超过原上限的部分显示为金色。\n\n'
                  '超限过的武器不能再重铸。超限是武器本身的属性，任何难度都有效。\n\n%s' % (wp, n, drop_zh)),
        GOODS_A: ('超限锻造石（防具）', '装备工坊「超限」消耗的材料（防具）',
                  '命定之死的封印解开后才出现的锻造石，带有些微死亡的气息。能将防具的减伤率强化至超过原本的上限。\n\n'
                  '在交界地，防具向来不在锻造之列。据说最先这么做的，是步入死亡次数最多的褪色者。\n\n'
                  '在赐福「暗黑重铸」→「装备工坊」的「超限」里，选背包里的一件新防具：每颗让它的减伤倍率（八种减伤一起）提高一点，'
                  '最多到这个稀有度原上限再高 %d%%（一般约 %d 颗到顶）。超过原上限的部分显示为金色。\n\n'
                  '超限是防具本身的属性，任何难度都有效；继承词条不会带走它。\n\n%s' % (ap, na, drop_zh)),
    }
    en = {
        GOODS_W: ('Overlimit Smithing Stone (Armament)', 'Material used by Overlimit in the Gear Workshop (armaments)',
                  'A smithing stone that appears only once the seal on Destined Death is broken, bearing a faint air of death. Reinforces an armament beyond its original limit.\n\n'
                  'Hewg, blacksmith of the Roundtable Hold, swore to Queen Marika that he would forge a godslaying armament. However many he forged, he said only this:\n  This\'ll never kill a god.\n\n'
                  'At a site of grace, "Darkforge" -> "Gear Workshop" -> "Overlimit": each stone raises every attribute scaling '
                  'of a new armament in your inventory by one step, up to %d%% above the original cap for its rarity '
                  '(usually about %d stones to max out). Values beyond the original cap are shown in gold.\n\n'
                  'An overlimited armament can no longer be reforged. Overlimit is part of the armament and works on every difficulty.\n\n%s'
                  % (wp, n, drop_en)),
        GOODS_A: ('Overlimit Smithing Stone (Armor)', 'Material used by Overlimit in the Gear Workshop (armor)',
                  'A smithing stone that appears only once the seal on Destined Death is broken, bearing a faint air of death. Reinforces the damage negation of armor beyond its original limit.\n\n'
                  'In the Lands Between, armor was never counted among the things to be smithed. It is said the first to try were the Tarnished who had died the most.\n\n'
                  'At a site of grace, "Darkforge" -> "Gear Workshop" -> "Overlimit": each stone raises the damage negation '
                  'multiplier (all eight types) of a new armor piece in your inventory by one step, up to %d%% above the original '
                  'cap for its rarity (usually about %d stones to max out). Values beyond the original cap are shown in gold.\n\n'
                  'Overlimit is part of the armor and works on every difficulty; inheriting affixes does not move it.\n\n%s'
                  % (ap, na, drop_en)),
    }
    return {'zh': zh, 'en': en}


def build(ctx):
    ctx.overlimit = None
    c = cfg(ctx.S)
    if not c or not getattr(ctx, 'containers', None):
        return
    gl, gsz = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))
    go = {n: (o, fc, bp, bits) for n, fc, o, bp, bits, _ in gl}
    G = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    if gsz != G.row_size or TEMPLATE not in G.rows or any(i not in G.rows for i in ICON_FROM.values()):
        raise RuntimeError('超限锻造石：EquipParamGoods 行大小不对，或缺少锻造石【1】%d / 古龙岩锻造石 %s' % (TEMPLATE, list(ICON_FROM.values())))
    for gid in (GOODS_W, GOODS_A):
        if gid in G.rows:
            raise RuntimeError('超限锻造石：道具编号 %d 已被占用' % gid)
        icon = struct.unpack_from('<' + go['iconId'][1], G.rows[ICON_FROM[gid]], go['iconId'][0])[0]
        row = bytearray(G.rows[TEMPLATE])
        for f, v in (('iconId', icon), ('sortId', SORT[gid]), ('rarity', 3), ('sellValue', 100), ('maxNum', 999), ('maxRepositoryNum', 999)):
            o, fc, bp, bits = go[f]
            if bits:
                raise RuntimeError('超限锻造石：%s 是位字段' % f)
            struct.pack_into('<' + fc, row, o, v)
        G.add_row(gid, bytes(row))
    ctx.bnd.put('EquipParamGoods.param', G.serialize())

    tx = texts(c)
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for j, fmg in enumerate(('GoodsName.fmg', 'GoodsInfo.fmg', 'GoodsCaption.fmg')):
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            for gid in (GOODS_W, GOODS_A):
                d[gid] = tx[lang][gid][j]
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.overlimit = c
    ctx.features['overlimit'] = {'goods': [GOODS_W, GOODS_A]}
    dr = c['drops']
    ctx.report.append('超限锻造石：道具 %d（武器）/ %d（防具），装备工坊「超限」消耗；武器补正到原上限 ×%g、防具减伤倍率到原上限 ×%g，'
                      '从中位 %d 颗到顶（dll\\dark_core 执行）；掉落只在标了 lock 的难度档：小怪 %s%%、Boss 每档第一次 %s 颗（%g 米内）' % (
                          GOODS_W, GOODS_A, c['weapon_cap'], c['armor_cap'], c['stones'],
                          ' / '.join('%g' % float(x) for x in dr['mob_pct']), ' / '.join(str(x) for x in dr['boss_stones']) + '（追忆 %s）' % ' / '.join(str(x) for x in dr['remembrance_stones']), float(dr['range'])))


def drop_lines(ctx):
    """dll\\dark_core\\ovldrop.txt（格式见 dark_core 的 ovldrop.rs）；没开超限、没有 lock 档就没有"""
    from .hpunify import flags as lock_flags
    c = getattr(ctx, 'overlimit', None)
    fl = lock_flags(ctx.S)
    if not c or not fl:
        return []
    dr = c['drops']
    pct, bs, rs = list(dr['mob_pct']), list(dr['boss_stones']), list(dr['remembrance_stones'])
    pick = lambda v, k: v[min(k, len(v) - 1)]
    out = ['tier %d %d %g %d' % (f, int(pick(bs, k)), float(pick(pct, k)), int(pick(rs, k))) for k, f in enumerate(fl)]
    out += ['goods %d %d' % (GOODS_W, GOODS_A), 'range %g' % float(dr['range'])]
    bf = json.load(open(os.path.join(ctx.data_dir, 'boss_overlimit_flags.json'), encoding='utf-8'))['bosses']
    try:
        rb = json.load(open(os.path.join(ctx.data_dir, 'remembrance_bosses.json'), encoding='utf-8'))
        rem_ents = {int(e) for part in ('base', 'dlc') for e in rb.get(part, {})}
    except (OSError, ValueError):
        rem_ents = set()
    rem = sorted(int(k) for k, v in bf.items() if rem_ents & set(v['entities']) or int(k) in rem_ents)
    out += ['rem ' + ' '.join(map(str, rem[i:i + 20])) for i in range(0, len(rem), 20)]
    ents = set()
    for k, v in sorted(bf.items(), key=lambda kv: int(kv[0])):
        fs = v['flags'][:len(fl)]
        if len(fs) == len(fl):
            out.append('boss %s %s' % (k, ' '.join(map(str, fs))))
        ents.update(v['entities'])
        ents.add(int(k))
    try:
        ents.update(b['entity'] for b in json.load(open(os.path.join(ctx.data_dir, 'boss_lots.json'), encoding='utf-8'))['bosses'])
    except (OSError, ValueError, KeyError):
        pass
    ents = sorted(ents)
    out += ['bossent ' + ' '.join(map(str, ents[i:i + 20])) for i in range(0, len(ents), 20)]
    nodrop = sorted(set(getattr(ctx, 'summon_npcs', ()) or ()) | {DUMMY_NPC})
    out += ['nodrop ' + ' '.join(map(str, nodrop[i:i + 20])) for i in range(0, len(nodrop), 20)]
    # 骨灰掉落（rr/ashcont.py 的 boss_drop）：ash 各档个数；ashes 随机挑的原版骨灰（+0），进背包后 dark_core 照常换成带稀有度的容器
    a = getattr(ctx, 'ashcont', None)
    bd = list((a or {}).get('c', {}).get('boss_drop') or [])
    if a and bd and any(int(x) > 0 for x in bd):
        out.append('ash ' + ' '.join(str(int(pick(bd, k))) for k in range(len(fl))))
        ks = [k[0] for k in a['kinds']]
        out += ['ashes ' + ' '.join(map(str, ks[i:i + 20])) for i in range(0, len(ks), 20)]
    return out


def lines(ctx):
    """items.txt 的超限行"""
    c = getattr(ctx, 'overlimit', None)
    if not c:
        return []
    return ['# overlimit <武器石> <防具石> <武器从中位到超限上限几颗> <防具几颗>（rr/overlimit.py；各稀有度的上限在 affixes.txt 的 ovlw / ovlp 行）',
            'overlimit\t%d\t%d\t%d\t%d' % (GOODS_W, GOODS_A, c['stones'], c['armor_stones'])]
