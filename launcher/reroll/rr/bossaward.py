# -*- coding: utf-8 -*-
"""Boss 奖励放不下击杀奖励表时，改成事件发放（用户 2026-11-08「能把现在 boss 在地上的光点掉落都改为事件发放吗」）。
以前放不下的龙心脏、星光碎片、保底锻造石、未鉴定传说走 Boss 自身掉落，是地上的光点，还要看这个位置实际放的是哪个敌人。
现在收集起来放进地图掉落表的单独一段（LOT0 起，每 10 行一张：一次发放最多发 10 行），features.json 的 boss_award = [[击败标记, 掉落表], …]，
sc/bossaward.py 的公共事件等击败标记从灭变亮时发。每行照旧带自己的获取标记（编号沿用以前自身掉落的），每件只给一次，Boss 复活再打也不重复。
Boss 原本自带的掉落不动，照旧在地上。

击败标记：data\\fusion_drop.json 的 fights（键是标记，entities 是这场的位置；boss_lots.json 的 196 个 Boss 都对得上）。
击杀不发奖励的小 Boss（boss_extra.json）的击败标记就是实体号（事件脚本里 SetEventFlag 点亮，头目复活清单也有）；
GROUND_ONLY 这两个的事件脚本里没有点亮实体号的指令，发放时机没把握，照旧地上掉落。"""
from .common import *  # noqa: F401,F403

LOT0, STEP, CHUNK = 1908500000, 20, 10
GROUND_ONLY = {2049440710, 1037510800}      # 落叶丹恩、逃跑位的兰斯桑克斯


def _flags(ctx):
    if not hasattr(ctx, 'boss_defeat'):
        fi = json.load(open(os.path.join(ctx.data_dir, 'fusion_drop.json'), encoding='utf-8'))['fights']
        ctx.boss_defeat = {int(e): int(k) for k, v in fi.items() for e in v.get('entities', [])}
        ctx.boss_defeat.update({int(k): int(k) for k in fi})
    return ctx.boss_defeat


def has_flag(ctx, entity):
    return entity in _flags(ctx)


def extra_by_event(ctx, b):
    """boss_extra.json 的这个小 Boss 走事件发放吗"""
    if b['entity'] in GROUND_ONLY or b.get('replaced_only'):
        return False
    return not (b.get('randomizer_only') and not ctx.a.randomizer_dir)


def rows_of(ctx, entity):
    """这个 Boss 已经收集的行"""
    x = getattr(ctx, 'boss_award', {}).get(entity)
    return x[1] if x else []


def add(ctx, entity, rows, flag=None):
    """收集这个 Boss 要发的行；找不到击败标记返回 False（调用的地方照旧走自身掉落）。flag：小 Boss 直接给实体号"""
    flag = flag if flag else _flags(ctx).get(entity)
    if not flag:
        return False
    if not hasattr(ctx, 'boss_award'):
        ctx.boss_award = {}
    ctx.boss_award.setdefault(entity, (flag, []))[1].extend(bytes(r) for r in rows)
    return True


def build(ctx):
    """收集完了（在 Boss 奖励的几步之后）：放进地图掉落表，写 features"""
    award = getattr(ctx, 'boss_award', None) or {}
    P, lot, out, n_rows = ctx.P_mp, LOT0, [], 0
    for ent, (flag, rows) in sorted(award.items()):
        for i in range(0, len(rows), CHUNK):
            part = rows[i:i + CHUNK]
            while any((lot + k) in P.rows for k in range(len(part) + 1)):
                lot += STEP
            for k, r in enumerate(part):
                if len(r) != P.row_size:
                    raise RuntimeError('Boss 奖励：掉落表行大小不符（%d / %d）' % (len(r), P.row_size))
                P.add_row(lot + k, r)
            out.append([flag, lot])
            n_rows += len(part)
            lot += STEP
    ctx.features['boss_award'] = out
    ctx.report.append('Boss 奖励事件发放：%d 个 Boss、%d 张表、%d 行（击败标记亮起时发，放不下击杀奖励表的龙心脏、星光碎片、锻造石、传说）；照旧地上掉落的小 Boss：%s' % (
        len(award), len(out), n_rows, sorted(GROUND_ONLY)))
