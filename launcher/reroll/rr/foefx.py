# -*- coding: utf-8 -*-
"""敌人效果包（通用模块；用户 2026-11-17「和斗技场结合 实现可以给任意指定波数敌人挂自定义效果」「可以抽象成一个通用模块」）。
settings.json 的 enemy_fx.packs：{包名: {sp: [现成的效果行…], rows: [{from: 底子行（可选）, 字段: 值…}…], speed: 动作速度倍数}}
- rows：每一项做成一行新的效果行（编号 SP0 起，按包名排好依次分）。不写 from 用 90030 当底子（同 rr/hpunify.py：去掉「咒死无效」
  那一位、不显示图标、永久、类别 0）；写了 from 就照抄那一行（带它的特效、持续时间）再改字段。字段名照 data\\SpEffect.xml，位字段写 0 / 1。
- sp：直接挂现成的效果行（原版的、别的模块做的都行；写定义时核对存在，不存在的去掉、写进报告）。
- speed：动作速度倍数（dark_core 交给 speed.rs，和时隙、减速、魇化相乘；1 = 不改，0~3）。
字段写错、底子行不存在、数值不对的这一包整包不要，写进报告（启动日志能看到）。
别的模块也能在这一步之前往 ctx.foefx_more 里放包（同样的格式；斗技场规则里直接写的 fx 就是这样）。
dll\\dark_core\\foefx.txt（def_lines，格式见 dark_core 的 foefx.rs）：pack <包名> <动作速度> <效果,效果…|->。
谁、什么时候挂由用的地方定：斗技场试炼按波次（settings 的 arena.wave_fx，rr/arena.py 写进 arena.txt 的 wfx 行）。"""
from .common import *  # noqa: F401,F403

# 自定义效果行（2026-11-17 扫过普通 / 死亡以上两个世界的 regulation：7310001 之后到 7319920 之前都空着）
SP0, SP_N = 7311000, 1000
TEMPLATE = 90030
NAME_RE = re.compile(r'^[^\s,]+$')        # 包名不能有空白和逗号（定义文件按 tab、逗号分）
MAX_SPEED = 3.0                           # 同 dark_core speed.rs 的上限


def packs_of(S, more=None):
    """{包名: 定义}：settings 的 enemy_fx.packs（关掉就没有），加上别的模块放的"""
    c = S.get('enemy_fx') or {}
    out = {} if not c.get('enabled', True) else {k: v for k, v in (c.get('packs') or {}).items() if not k.startswith('_')}
    for k, v in (more or {}).items():
        if k in out:
            raise RuntimeError('敌人效果包：包名「%s」重复了' % k)
        out[k] = v
    return out


def set_field(lay, row, f, v):
    """按 paramdef 的布局写一个字段（位字段只改那几位）"""
    _nm, fc, off, bp, bits, _d = lay[f]
    if isinstance(v, bool):
        v = int(v)
    if not isinstance(v, (int, float)):
        raise ValueError('%s 要写数字，写的是 %r' % (f, v))
    if bits:
        if v not in (0, 1) and bits == 1:
            raise ValueError('%s 是开关，写 0 或 1' % f)
        cur = struct.unpack_from('<' + fc, row, off)[0]
        mask = ((1 << bits) - 1) << bp
        struct.pack_into('<' + fc, row, off, (cur & ~mask) | ((int(v) << bp) & mask))
    elif fc in 'fd':
        struct.pack_into('<' + fc, row, off, float(v))
    else:
        if v != int(v):
            raise ValueError('%s 要写整数，写的是 %r' % (f, v))
        struct.pack_into('<' + fc, row, off, int(v))


def make_rows(p, rows_have, lay):
    """一包的自定义行：[(底子, 改好的行)]；不对就 ValueError（说明原因）"""
    out = []
    rows = p.get('rows') or []
    if isinstance(rows, dict):
        rows = [rows]
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError('rows 里每一项要写成 {字段: 值}')
        base = r.get('from', TEMPLATE)
        if isinstance(base, bool) or not isinstance(base, int) or base not in rows_have:
            raise ValueError('底子行 %r 不存在' % (base,))
        row = bytearray(rows_have[base])
        if 'from' not in r:                       # 90030 底子：去掉「咒死无效」、无图标、永久、类别 0
            set_field(lay, row, 'disableCurse', 0)
            set_field(lay, row, 'iconId', -1)
            set_field(lay, row, 'effectEndurance', -1.0)
            set_field(lay, row, 'spCategory', 0)
        for f, v in r.items():
            if f == 'from' or f.startswith('_'):
                continue
            if f not in lay:
                raise ValueError('效果行没有字段 %s' % f)
            set_field(lay, row, f, v)
        out.append(bytes(row))
    return out


def build(ctx):
    """做自定义效果行；ctx.foefx = {包名: dict(sp=[效果…], speed=倍数, made=自己做的行数)}"""
    ctx.foefx = {}
    packs = packs_of(ctx.S, getattr(ctx, 'foefx_more', None))
    if not packs:
        return
    S_sp = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}
    nxt, bad, out = SP0, [], {}
    for name in sorted(packs):
        p = packs[name]
        try:
            if not NAME_RE.match(name):
                raise ValueError('包名不能有空格或逗号')
            if not isinstance(p, dict):
                raise ValueError('要写成 {sp / rows / speed}')
            speed = float(p.get('speed', 1.0))
            if not 0.0 <= speed <= MAX_SPEED:
                raise ValueError('动作速度要在 0~%g' % MAX_SPEED)
            sps = p.get('sp') or []
            sps = [sps] if isinstance(sps, int) else sps
            if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in sps):
                raise ValueError('sp 要写效果行编号')
            rows = make_rows(p, S_sp.rows, lay)
        except (TypeError, ValueError, struct.error) as e:
            bad.append('%s（%s）' % (name, e))
            continue
        if not rows and not sps and speed == 1.0:
            bad.append('%s（什么都没改）' % name)
            continue
        if nxt + len(rows) > SP0 + SP_N:
            raise RuntimeError('敌人效果包：自定义效果行超过 %d 行' % SP_N)
        ids = []
        for row in rows:
            if nxt in S_sp.rows:
                raise RuntimeError('敌人效果包：效果编号 %d 已经有人用了' % nxt)
            S_sp.add_row(nxt, row)
            ids.append(nxt)
            nxt += 1
        out[name] = dict(sp=ids + [x for x in sps if x not in ids], speed=speed, made=len(ids))
    if nxt > SP0:
        ctx.bnd.put('SpEffectParam.param', S_sp.serialize())
    ctx.foefx = out
    ctx.report.append('敌人效果包：%d 个（%s），自定义效果行 %d 行（%d 起，执行在 dll\\dark_core 的 foefx.rs）%s' % (
        len(out), '、'.join('%s：%s%s' % (k, '+'.join(map(str, v['sp'])) or '-', '，速度 ×%g' % v['speed'] if v['speed'] != 1.0 else '')
                           for k, v in sorted(out.items())) or '-',
        nxt - SP0, SP0, '；这些包不对，跳过：' + '；'.join(bad) if bad else ''))


def def_lines(ctx):
    """dll\\dark_core\\foefx.txt；现成的效果行在这时（参数都做完了）核对存在"""
    packs = getattr(ctx, 'foefx', None) or {}
    if not packs:
        return []
    need = {sp for p in packs.values() for sp in p['sp'][p['made']:]}
    missing = set()
    if need:
        rows = erlib.Param(ctx.bnd.get('SpEffectParam.param')).rows
        missing = {sp for sp in need if sp not in rows}
        if missing:
            ctx.report.append('敌人效果包：效果行 %s 不存在，跳过（没挂）' % '、'.join(map(str, sorted(missing))))
    out = []
    for name, p in sorted(packs.items()):
        sps = [sp for sp in p['sp'] if sp not in missing]
        out.append('pack\t%s\t%g\t%s' % (name, p['speed'], ','.join(map(str, sps)) or '-'))
    return out
