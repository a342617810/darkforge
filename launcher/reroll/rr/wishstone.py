# -*- coding: utf-8 -*-
"""许愿石（settings.json 的 wish_stone；用户 2026-11-04「在高难给boss添加许愿石的掉落 效果是提高1级等级 每个boss固定掉落1个 追忆boss掉落3个」）：
  - 道具 GOODS：强化材料类（照锻造石【1】，不能使用、不能卖）。图标先借泪滴幼虫的，菜单包里有 make_frames.py 画的自制图标
    （frames.txt 的 custom wish_stone 行）时 dark_core 换上。
  - 掉落：只在 difficulty 里标了 lock 的档（死亡 / 不可能）。每场 Boss 战给 boss 个、追忆 Boss 战给 remembrance 个，
    和死亡以上的融锻之心一起由 dark_core 的 fusion 模块发（bosses.fusion_lines 的 wish 行、boss 行第 4 个数），共用「死亡以上给过」标记：
    两档合起来每场只给一次。
  - 使用：赐福「暗黑重铸」→「许愿石升级」（sc/wishstone.py，只在高难度档列出来）选一项能力值、确认；菜单把能力值序号写进 ATTR0 起的 3 个标记，
    点亮请求 REQ。dark_core（wishstone.rs）熄灭请求前：没有许愿石点亮 NONE、这项已经 99 点亮 MAX；否则扣 1 个许愿石，这项能力值 +1、等级 +1
    （直接改人物数据，游戏 1 秒内自己重算最大血量等；用户 2026-11-04 游戏里试过）。
  - 定义 dll\\dark_core\\wishstone.txt（def_lines）。
要有新装备系统的容器（dark_core 发货表）和 lock 档。"""
from .common import *  # noqa: F401,F403

GOODS = 9244                             # 道具编号（超限锻造石 9242 / 9243 后面，原版没用）
TEMPLATE = 10100                         # 锻造石【1】：强化材料（goodsType 14）、不能使用
ICON_FROM = 8185                         # 泪滴幼虫的图标（自制图标在菜单包里时 dark_core 换上）
SORT = 160104                            # 排在超限锻造石（160102 / 160103）后面
REQ, ATTR0, ATTR_BITS, NONE, MAX = 93012, 93013, 3, 93016, 93017   # 赐福菜单的请求 / 能力值序号 / 没有许愿石 / 已经 99（dev\event_flags\说明.md）
DEFAULT = dict(boss=1, remembrance=3)
NAMES = {'zh': ('生命力', '集中力', '耐力', '力气', '灵巧', '智力', '信仰', '感应'),
         'en': ('Vigor', 'Mind', 'Endurance', 'Strength', 'Dexterity', 'Intelligence', 'Faith', 'Arcane')}


def cfg(S):
    c = S.get('wish_stone') or {}
    if not c.get('enabled', True):
        return None
    out = dict(DEFAULT)
    out.update({k: max(0, int(c[k])) for k in DEFAULT if k in c})
    return out


def texts(c):
    """（名字, 简介, 说明）：中文、英文"""
    zh = ('许愿石', '赐福「许愿石升级」消耗的道具',
          '在最艰难的试炼中击败强敌时凝成的小石。握着它许下的愿望，会化作力量。\n\n'
          '在黄金树时代，夜空的命运受到律法束缚。据说仍有人握着这种小石，向星星许愿。\n\n'
          '在赐福「暗黑重铸」→「许愿石升级」里选一项能力值，每次消耗 1 个：这项能力值提升 1 点，等级随之提升 1 级，不花卢恩。\n\n'
          '只在「死亡」「不可能」难度里获得：每个 Boss 给 %d 个，追忆 Boss 给 %d 个；每场 Boss 战只给一次。' % (c['boss'], c['remembrance']))
    en = ('Wish Stone', 'Used by "Wish Stone Level Up" at a site of grace',
          'A small stone that forms when a mighty foe falls in the harshest trials. A wish made while holding it turns into strength.\n\n'
          'In the age of the Erdtree, the fate held in the night sky was bound by the Golden Order. Some, it is said, still held stones like this and wished upon the stars.\n\n'
          'At a site of grace, "Darkforge" -> "Wish Stone Level Up": pick an attribute and use one stone to raise it by 1. '
          'Your level rises by 1 as well, at no rune cost.\n\n'
          'Obtained only on the Death and Impossible difficulties: every boss gives %d, bosses that hold a remembrance give %d. '
          'Each boss fight gives them only once.' % (c['boss'], c['remembrance']))
    return {'zh': zh, 'en': en}


def build(ctx):
    from .hpunify import flags as lock_flags
    ctx.wishstone = None
    c = cfg(ctx.S)
    tiers = lock_flags(ctx.S)
    if not c or not tiers or not getattr(ctx, 'containers', None):
        return
    gl, gsz = pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGoods.xml')))
    go = {n: (o, fc, bp, bits) for n, fc, o, bp, bits, _ in gl}
    G = erlib.Param(ctx.bnd.get('EquipParamGoods.param'))
    if gsz != G.row_size or TEMPLATE not in G.rows or ICON_FROM not in G.rows:
        raise RuntimeError('许愿石：EquipParamGoods 行大小不对，或缺少锻造石【1】%d / 泪滴幼虫 %d' % (TEMPLATE, ICON_FROM))
    if GOODS in G.rows:
        raise RuntimeError('许愿石：道具编号 %d 已被占用' % GOODS)
    icon = struct.unpack_from('<' + go['iconId'][1], G.rows[ICON_FROM], go['iconId'][0])[0]
    row = bytearray(G.rows[TEMPLATE])
    for f, v in (('iconId', icon), ('sortId', SORT), ('rarity', 3), ('sellValue', -1), ('maxNum', 999), ('maxRepositoryNum', 999)):
        o, fc, bp, bits = go[f]
        if bits:
            raise RuntimeError('许愿石：%s 是位字段' % f)
        struct.pack_into('<' + fc, row, o, v)
    G.add_row(GOODS, bytes(row))
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
            d[GOODS] = tx[lang][j]
            mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.wishstone = c
    ctx.features['wishstone'] = {'goods': GOODS, 'req': REQ, 'attr0': ATTR0, 'attr_bits': ATTR_BITS, 'none': NONE, 'max': MAX,
                                 'tiers': tiers}          # tiers：入口只在这几档列出来
    ctx.report.append('许愿石：道具 %d，死亡以上每场 Boss 战 %d 个、追忆 Boss %d 个（dark_core 的 fusion 模块发，和融锻之心共用给过标记）；'
                      '赐福「许愿石升级」请求 %d、能力值序号 %d~%d、没有 %d、已满 %d（dark_core 的 wishstone 模块）' % (
                          GOODS, c['boss'], c['remembrance'], REQ, ATTR0, ATTR0 + ATTR_BITS - 1, NONE, MAX))


def def_lines(ctx):
    """dll\\dark_core\\wishstone.txt（格式见 dark_core 的 wishstone.rs）；没开就没有"""
    if not getattr(ctx, 'wishstone', None):
        return []
    return ['goods %d' % GOODS, 'req %d' % REQ, 'attr %d %d' % (ATTR0, ATTR_BITS), 'none %d' % NONE, 'max %d' % MAX]
