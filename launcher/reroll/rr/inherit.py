# -*- coding: utf-8 -*-
"""赐福「装备工坊」（settings.json 的 equipment_inherit；用户 2026-10-31）：现在只有「继承」一页——
  把背包里一件生成防具（来源，没穿着、没锁定）的一条词条转到另一件生成防具上（机制类进前缀位、数值类进后缀位，
  有空位就补上，满了选替换哪一条），或者提取成这条词条的护符；来源销毁，另外消耗 1 个融锻之心；词条保留来源的稀有度。
界面是 dll\\dark_ui（自己画的悬浮窗口，单独一个 DLL），规则、数据和执行在 dll\\dark_core（gear.rs 的「装备继承」、gear\\workshop.rs）。
赐福菜单（sc/inherit.py）点亮打开请求 OPEN，dark_core 应答 ACK（界面在）或点亮 NOUI（界面没加载）；窗口关了 dark_core 熄灭 OPEN / ACK，
菜单回到赐福。这里分标记、建道具「融锻之心」、写 items.txt 的 inherit 行和 features.json 的 inherit。
融锻之心（用户 2026-10-31，代替原来消耗的武器重铸石）：强化材料类道具（照锻造石【1】，背包普通格；龙心脏是关键道具，在另一张表里，
dark_core 不数）；Boss 掉落，数量和龙心脏一样（rr/bosses.py heart_shard，enabled 决定加不加）。图标先写龙心脏的，
菜单包里有 make_frames.py 画的自制图标（frames.txt 的 custom fusion_heart 行）时 dark_core 换上。
（2026-10-31 先试过用商店界面选来源：商店一件都不显示，原因没查明，改成自己画界面；当时用的标记 93614~93673、93677~93717 空出来了）
没有新装备系统的容器就不开。"""
from .common import *  # noqa: F401,F403

OPEN, ACK, NOUI = 93674, 93675, 93676    # 打开请求（菜单点亮）/ 应答（dark_core 点亮）/ 没有界面（dark_core 点亮）（dev\event_flags\说明.md）
TALK0 = 80092000                         # EventTextForTalk：菜单项「装备工坊」+0、没加载 dark_core +1、没加载 dark_ui +3
GOODS = 9241                             # 融锻之心（武器重铸石 9240 后面，原版没用）
TEMPLATE = 10100                         # 锻造石【1】：强化材料（goodsType 14）、不能使用
ICON = 3230                              # 龙心脏的图标（菜单包没有自制图标时就用它）
SORT = 160100                            # 排在未鉴定物品（160000 起）后面


def cfg(S):
    c = S.get('equipment_inherit') or {}
    return c if c.get('enabled', True) else None


def enabled(ctx):
    """这次开不开装备工坊（Boss 掉不掉融锻之心也看它）：要新装备系统的容器（containers.build 之后才准）"""
    return cfg(ctx.S) is not None and bool(getattr(ctx, 'containers', None))


def texts(S=None):
    """（名字, 简介, 说明）：中文、英文。平时追忆 Boss 给的个数按 fusion_drop 的 step / max 写（用户 2026-11-04：3、6、9、12 封顶）"""
    c = (S or {}).get('fusion_drop') or {}
    step, top = int(c.get('step', 3)), int(c.get('max', 12))
    if step > 0 and top >= step:
        seq = [step * k for k in range(1, top // step + 1)]
        rem_zh = '打倒追忆 Boss 获得：按难度从低到高依次给 %s 个，之后每个给 %d 个。\n' % ('、'.join(map(str, seq[:-1])) or str(seq[0]), seq[-1])
        rem_en = 'Obtained by defeating bosses that hold a remembrance: %s in order of difficulty, then %d each.\n' % (
            ', '.join(map(str, seq[:-1])) or str(seq[0]), seq[-1])
    else:
        rem_zh, rem_en = '打倒追忆 Boss 获得，越往后的追忆 Boss 给得越多。\n', 'Obtained by defeating bosses that hold a remembrance; later ones give more.\n'
    zh = ('融锻之心', '装备工坊「继承」消耗的材料',
          '强敌体内凝结的炽热心核，混杂着熔化的钢铁，仍传出脉动。能将一件防具的流纹文字熔进另一件。\n\n'
          '献上心核、熔化文字──这种做法要称为锻造，也过于野蛮。\n\n'
          '在赐福「暗黑重铸」→「装备工坊」的「继承」里，把一件新防具的一条词条转到另一件新防具上，或者提取成护符，每次消耗 1 个。\n\n'
          + rem_zh +
          '难度在「死亡」「不可能」时，所有 Boss 都会给，数量和龙心脏一样。每场 Boss 战在平时、在「死亡」以上各只给一次。')
    en = ('Fusion Heart', 'Material used by Inherit in the Gear Workshop',
          'A searing core congealed within a mighty foe, mixed with molten steel and still pulsing. Melts the smithscript of one piece of armor into another.\n\n'
          'Offering up a heart and melting down the script: this is too savage to be called smithing.\n\n'
          'At a site of grace, "Darkforge" -> "Gear Workshop" -> "Inherit" uses one each time you move an affix from one new armor piece '
          'onto another, or extract it as a talisman.\n\n'
          + rem_en +
          'On the Death and Impossible difficulties, every boss gives them, as many as Dragon Hearts. Each boss fight gives them only once below Death, and once more on Death or Impossible.')
    return {'zh': zh, 'en': en}


def make_goods(ctx):
    """道具行（照锻造石【1】：强化材料、不能使用、不能卖）+ 文字"""
    gl, gsz = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))
    go = {n: (o, fc, bp, bits) for n, fc, o, bp, bits, _ in gl}
    G = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    if gsz != G.row_size or TEMPLATE not in G.rows:
        raise RuntimeError('融锻之心：EquipParamGoods 行大小不对，或缺少锻造石【1】%d' % TEMPLATE)
    if GOODS in G.rows:
        raise RuntimeError('融锻之心：道具编号 %d 已被占用' % GOODS)
    row = bytearray(G.rows[TEMPLATE])
    for f, v in (('iconId', ICON), ('sortId', SORT), ('rarity', 2), ('sellValue', -1), ('maxNum', 999), ('maxRepositoryNum', 999)):
        o, fc, bp, bits = go[f]
        if bits:
            raise RuntimeError('融锻之心：%s 是位字段' % f)
        struct.pack_into('<' + fc, row, o, v)
    G.add_row(GOODS, bytes(row))
    ctx.bnd.put('EquipParamGoods.param', G.serialize())
    tx = texts(ctx.S)
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for j, fmg in enumerate(('GoodsName.fmg', 'GoodsInfo.fmg', 'GoodsCaption.fmg')):
            hdr, ents = erlib.read_fmg_full(mb.get(fmg))
            d = dict(ents)
            d[GOODS] = tx[lang][j]
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))


def build(ctx):
    ctx.inherit = None
    if not enabled(ctx):
        return
    make_goods(ctx)
    ctx.inherit = True
    ctx.features['inherit'] = {'open': OPEN, 'ack': ACK, 'noui': NOUI, 'talk0': TALK0, 'goods': GOODS}
    ctx.report.append('装备工坊（继承）：打开请求 / 应答 / 没有界面 标记 %d / %d / %d（界面 dll\\dark_ui，执行 dll\\dark_core），'
                      '消耗来源 + 1 个融锻之心（道具 %d，追忆 Boss 掉落、死亡以上所有 Boss，见 bosses.fusion_lines）' % (OPEN, ACK, NOUI, GOODS))


def lines(ctx):
    """items.txt 的 inherit 行"""
    if not getattr(ctx, 'inherit', None):
        return []
    pages = [int((ctx.features.get(k) or {}).get('open') or 0) for k in ('nightmare', 'curses')]
    return ['# inherit <打开请求标记> <应答标记> <没有界面标记> <继承消耗的道具（融锻之心）> <「魇印」的打开请求> <「七咒」的打开请求>：'
            '赐福「装备工坊」（rr/inherit.py、sc/inherit.py，界面 dll\\dark_ui）；「魇印」「七咒」是「暗黑重铸」里单独的两项（sc/wspages.py，0 = 没有）',
            'inherit\t%d\t%d\t%d\t%d\t%d\t%d' % (OPEN, ACK, NOUI, GOODS, pages[0], pages[1])]
