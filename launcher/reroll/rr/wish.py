# -*- coding: utf-8 -*-
"""向星辰许愿（settings 的 wish；v0.4 的「许愿按地区」+「开局免费许愿」，迁移后改成直接抽成品装备）。
赐福主菜单「向星辰许愿」→ 许愿 1 次 / 10 次，确认框里显示这个地区的价格和剩余免费次数（dll\\dark_core 改写占位）。
选「是」点亮请求标记 WISH1_FLAG / WISH10_FLAG，dark_core 按人物所在地图的档位（data\\map_tiers.json + tier_bands）：
  - 先用免费次数（每个角色 free 次，标记 FREE_FLAG0 起依次点亮，存档里记着；dll\\dark_sell 另外记在 DarkReforged\\角色记录\\free_wishes.txt），
    用完扣卢恩：cost_base + cost_step × 档位，DLC 的档（流程等级 20 以上）按顺序用 cost_dlc；
  - 每次随机一件成品装备：类别按 gear_category_share，稀有度按这一档的 weights（DLC 档的传说是传说（幽影之地）），
    武器偏向角色的加点（同鉴定）；和鉴定一样生成、放进背包。容器满了那件不抽、不扣钱，卢恩不够就到此为止。
这里只算数据（ctx.wish，containers.write_def 写进 items.txt），赐福菜单在 sc/wish.py"""
from .common import *  # noqa: F401,F403
from . import unidentified

WISH1_FLAG, WISH10_FLAG = 93503, 93504
POOR_FLAG = 93909                         # dark_core 的应答：一次都付不起（没有免费次数、卢恩不够），赐福菜单提示「星辰没有收到你的诚意」
FREE_FLAG0, FREE_MAX = 93020, 30          # 和 dll\dark_sell 的 FREE_FLAG0 / FREE_MAX 一致
CATS = ('weapon', 'armor', 'talisman')


def build(ctx):
    ctx.wish = None
    c = ctx.S.get('wish') or {}
    if not c.get('enabled', True) or not getattr(ctx, 'containers', None):
        return
    U = unidentified.cfg(ctx.S) or {}
    share = U.get('share') or {'weapon': 30, 'armor': 60, 'talisman': 10}
    base, step = int(c.get('cost_base', 3000)), int(c.get('cost_step', 2000))
    dlc_cost = c.get('cost_dlc') or [30000, 50000]
    dlc_cost = [int(x) for x in (dlc_cost if isinstance(dlc_cost, list) else [dlc_cost])]
    bands, j = [], 0
    for k, bd in enumerate(ctx.bands):
        dlc = unidentified.is_dlc(bd)
        cost = dlc_cost[min(j, len(dlc_cost) - 1)] if dlc else base + step * k
        j += dlc
        w = bd.get('weights') or {}
        bands.append({'cost': cost, 'dlc': dlc, 'w': [int(w.get(r, 0)) for r in RAR], 'name': bd.get('name', '')})
    maps = []
    for m, t in sorted(ctx.map_tiers.items()):
        g = re.match(r'^m(\d\d)_(\d\d)_(\d\d)_(\d\d)$', m)
        if g:
            maps.append(tuple(int(x) for x in g.groups()) + (ctx.band_idx(int(t)),))
    ctx.wish = {'flags': (WISH1_FLAG, WISH10_FLAG), 'free': (FREE_FLAG0, min(FREE_MAX, int(c.get('free', 30)))),
                'share': [int(share.get(k, 0)) for k in CATS], 'bands': bands, 'maps': maps}
    ctx.features['wish'] = {'flag1': WISH1_FLAG, 'flag10': WISH10_FLAG, 'poor': POOR_FLAG}
    ctx.report.append('向星辰许愿：直接抽成品装备，每个角色免费 %d 次，之后按地区 %s 卢恩（%d 张地图有档位；要 dll\\dark_core）' % (
        ctx.wish['free'][1], ' / '.join(str(b['cost']) for b in bands), len(maps)))


def lines(ctx):
    """items.txt 的许愿行"""
    w = getattr(ctx, 'wish', None)
    if not w:
        return []
    out = ['# wish <1 次请求标记> <10 次请求标记> <免费许愿第一个标记> <免费次数> <类别权重 武器 防具 护符> <诚意不够的应答标记>；'
           'wband <档> <每次卢恩> <DLC 档 1/0> <稀有度权重 普通 稀有 史诗 传说>；wmap <区域> <块> <行> <列/层> <档>（rr/wish.py）',
           'wish\t%d\t%d\t%d\t%d\t%s\t%d' % (w['flags'] + w['free'] + ('\t'.join(map(str, w['share'])), POOR_FLAG))]
    out += ['wband\t%d\t%d\t%d\t%s' % (k, b['cost'], 1 if b['dlc'] else 0, '\t'.join(map(str, b['w']))) for k, b in enumerate(w['bands'])]
    out += ['wmap\t%d\t%d\t%d\t%d\t%d' % m for m in w['maps']]
    return out
