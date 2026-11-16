# -*- coding: utf-8 -*-
"""Boss 模组（只在高难度加载；评估和做法见 dev\\boss_mods\\Boss模组整合评估.md、dev\\boss_mods\\README.md）。

启动器启动时按「上次玩的角色」是不是「死亡」以上决定加不加载（settings.json 的 boss_mods），要加载就带 --boss-mods 键,键 来跑重随；
没带（低难度、没开、或者整个功能关掉）这里什么都不做，重随结果和整合前一模一样。

带了的话：
- data\\bossmods\\<键>\\params.json 的参数补丁在所有步骤之前写进 regulation：「patch」只动模组改过的位（别的保持现在的原版），
  「add」是模组新加的行。后面的血量 / 掉落 / 难度都叠在它上面，复制敌人参数时挑的新编号也会自动避开这些行。
- 台词交给 scripts.py：features.json 的 boss_mods.texts → sc/bossmods.py 写进 menu_dlc02 的 TalkMsg。
- 角色层文件（data\\bossmods\\<键>\\files\\：动作 / 行为 / 模型 / AI / 音频…）由启动器挂成 YAFSML 的最底层，不经过这里。

要在所有步骤之前（reroll.py 的 run_steps 第一步）。

另外 auto 模式（按角色难度加载）不管这次加不加载，都加「死亡以上难度错配屏障」的圆顶子弹（barrier）：dark_core 的 barrier.rs 在
这次加载的世界和角色难度对不上时，直接在圆心生成这颗子弹（以前让公共事件发，实测发不出来，2026-11-05 去掉了）。"""
from .common import *  # noqa: F401,F403
from . import hpunify
import struct

BARRIER_ID = 99806700          # 圆顶子弹（Bullet）编号，原版和随机器都没有（dark_core barrier.rs 的 BULLET）
BARRIER_BASE = 100920          # 照着抄的原版子弹行：m60 的事件从玩家身上发的不动子弹
BARRIER_FX = 990050            # 我们的屏障特效（data\sfx 的 sfxbnd_c0000，dev\item_system\sfx\barrier_dome.js）：封印监牢圆顶缩到半径 10 米 + 光幕 + 地面圈，
                               # 和 dark_core 推回的半径一致（用户 2026-11-05「屏障缩小到10m … 要加上特效标识」；原版 806700 直接放没看到）
BARRIER_LIFE = 100000.0        # 秒：一直在，直到读图 / 回标题


def keys(ctx):
    return [k for k in (getattr(ctx.a, 'boss_mods', '') or '').split(',') if k.strip()]


def arena_port(ctx):
    """敌人随机的高难度世界（randomizer_hi：这些 Boss 留在原位）里要把场地移植上去的键（启动器带 --boss-arena）；
    不开敌人随机时场地是做好的成品，启动器直接挂，不用移植"""
    return [k for k in (getattr(ctx.a, 'boss_arena', '') or '').split(',') if k.strip() and k in keys(ctx)]


def arena_on(ctx, k):
    """这个键的场地这次有没有（不开敌人随机 = 成品直接挂；敌人随机 = 高难度世界里移植）"""
    return not ctx.a.randomizer_dir or k in arena_port(ctx)


def auto_on(ctx):
    """settings 的 boss_mods 是 auto（按角色难度加载）而且开着至少一个数据也在的模组（发布的整合包不带模组数据，dev\\tools\\make_package.py；
    同启动器的 Get-BossMods：那时启动器删掉 bossmods.txt，dark_core 什么都不做）"""
    bm = ctx.S.get('boss_mods') or {}
    return bm.get('mode', 'off') == 'auto' and any(
        v and os.path.isdir(os.path.join(ctx.data_dir, 'bossmods', k, 'files')) for k, v in (bm.get('mods') or {}).items() if not k.startswith('_'))


def barrier(ctx):
    """错配屏障的圆顶子弹：抄原版 100920（不动），去掉攻击、特效换成我们的屏障特效、穿过角色 / 物件 / 地形、存活很久"""
    if not auto_on(ctx):
        return
    def lay(n):
        return {f: (o, fc, bp, bits) for f, fc, o, bp, bits, dflt in pdm.layout(pdm.load(os.path.join(ctx.data_dir, n + '.xml')))[0]}

    def put(L, row, n, v):
        o, fc, bp, bits = L[n]
        if bits:
            m = ((1 << bits) - 1) << bp
            row[o] = (row[o] & ~m & 0xFF) | ((int(v) << bp) & m)
        else:
            struct.pack_into('<' + fc, row, o, v)
    LU = lay('BulletParam')
    U = erlib.Param(ctx.bnd.get('Bullet.param'))
    if BARRIER_BASE not in U.rows:
        ctx.report.append('死亡以上难度错配屏障：没有原版子弹 %d 行，圆顶没加（推回和禁止传送照样有）' % BARRIER_BASE)
        return
    bul = bytearray(U.rows[BARRIER_BASE])
    for n, v in (('atkId_Bullet', -1), ('sfxId_Bullet', BARRIER_FX), ('sfxId_Hit', -1), ('sfxId_Flick', -1), ('life', BARRIER_LIFE),
                 ('hitRadius', -1.0), ('hitRadiusMax', -1.0), ('HitBulletID', -1), ('intervalCreateBulletId', -1), ('spEffectIDForShooter', -1),
                 ('spEffectId0', -1), ('isPenetrateChr', 1), ('isPenetrateObj', 1), ('isPenetrateMap', 1)):
        put(LU, bul, n, v)
    if BARRIER_ID in U.rows:
        U.rows[BARRIER_ID][:] = bul
    else:
        U.add_row(BARRIER_ID, bytes(bul))
    ctx.bnd.put('Bullet.param', U.serialize())
    ctx.report.append('死亡以上难度错配屏障：圆顶子弹 %d（特效 %d，dark_core 的 barrier.rs 在圆心直接生成）' % (BARRIER_ID, BARRIER_FX))


def build(ctx):
    barrier(ctx)
    ks = keys(ctx)
    if not ks:
        return
    texts = {'en': {}, 'zh': {}}
    menu_fmg = {}                                   # 别的菜单文字（menu_dlc02）：{FMG: {语言: {编号: 文字}}}，给游戏脚本
    done = []
    for k in ks:
        d = os.path.join(ctx.data_dir, 'bossmods', k)
        if not os.path.isfile(os.path.join(d, 'params.json')):
            raise RuntimeError('Boss 模组「%s」：没有 %s' % (k, d))
        meta = json.load(open(os.path.join(d, 'mod.json'), encoding='utf-8'))
        rows = json.load(open(os.path.join(d, 'params.json'), encoding='utf-8'))['rows']
        params = {}
        n_add = n_patch = 0
        notes = []
        for r in rows:
            name = r['param'] + '.param'
            if name not in params:
                params[name] = erlib.Param(ctx.bnd.get(name))
            P, rid = params[name], int(r['id'])
            if r['kind'] == 'add':
                data = bytes.fromhex(r['data'])
                if len(data) != P.row_size:
                    raise RuntimeError('Boss 模组「%s」：%s %d 行大小 %d，现在是 %d（游戏版本变了？重新跑 dev\\boss_mods\\build.py）' % (
                        k, r['param'], rid, len(data), P.row_size))
                if rid in P.rows:
                    notes.append('%s %d 已经有了（用模组的盖上）' % (r['param'], rid))
                    P.rows[rid][:] = data
                else:
                    P.add_row(rid, data)
                n_add += 1
            else:
                row = P.rows.get(rid)
                if row is None:
                    notes.append('%s %d 没有这一行（跳过）' % (r['param'], rid))
                    continue
                for off, mask, val in r['bits']:
                    row[off] = (row[off] & (~mask & 0xFF)) | val
                n_patch += 1
        for name, P in params.items():
            ctx.bnd.put(name, P.serialize())
        for lang in texts:
            texts[lang].update(meta.get('texts', {}).get(lang, {}))
        for fmg, t in (meta.get('fmg_texts') or {}).items():
            if t['dest'] == 'menu':
                for lang in ('en', 'zh'):
                    menu_fmg.setdefault(fmg, {}).setdefault(lang, {}).update(t[lang])
            else:
                add_item_text(ctx, fmg, t)
        n_fx = add_fx(ctx, d, meta, notes)
        done.append(k)
        arena = '；场地（%s：事件 %d 个、地图部件 %d 个）%s' % (
            meta['arena']['map'], len(meta['arena']['events']), len(meta['arena']['parts']),
            '启动器挂上' if not ctx.a.randomizer_dir else ('移植到高难度世界的地图上（游戏脚本覆盖包）' if k in arena_port(ctx)
                                                          else '这次不用（敌人随机，Boss 不在原位）')) if meta.get('arena') else ''
        log('  Boss 模组「%s」（%s %s）：参数新加 %d 行、改 %d 行%s%s%s' % (
            meta.get('boss', {}).get('zh', k), meta.get('name', k), meta.get('version', ''), n_add, n_patch,
            '，特效 %d 个' % n_fx if n_fx else '', arena, '；' + '；'.join(notes) if notes else ''))
        ctx.report.append('Boss 模组 %s：参数新加 %d 行、改 %d 行，台词 %d 条，特效 %d 个%s%s' % (
            k, n_add, n_patch, len(meta.get('texts', {}).get('zh', {})), n_fx, arena, '；' + '；'.join(notes) if notes else ''))
    ctx.features['boss_mods'] = {'keys': done, 'texts': texts, 'menu_fmg': menu_fmg, 'arena_port': arena_port(ctx)}


def add_item_text(ctx, fmg, t):
    """物品类文字（地名等，item_dlc02）：写进重随包的文字包（中文用我们翻的，别的语言用英文）"""
    for code in sorted(os.listdir(ctx.msg_out)):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        hdr, ents = erlib.read_fmg_full(mb.get(fmg + '.fmg'))
        d = dict(ents)
        d.update({int(k): v for k, v in t['zh' if code == 'zhocn' else 'en'].items()})
        mb.put(fmg + '.fmg', erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))


SFX_ROOT = 'N:\\GR\\data\\INTERROOT_win64\\sfx\\'
RES_SUB = {'.tpf': ('tex', 100000), '.flver': ('model', 200000), '.anibnd': ('hkx', 300000)}
FX_DIR = 'N:\\GR\\data\\INTERROOT_win64\\sfx\\effect\\'
RES_DIR = 'N:\\GR\\data\\INTERROOT_win64\\sfx\\ResourceList\\'


def add_fx(ctx, d, meta, notes):
    """模组塞进原版常驻特效包的新特效（data\\bossmods\\<键>\\fx）→ 并进重随包里我们自己的 sfxbnd_c0000（常驻，跟着 DR_Reroll 挂，
    不碰原版公共包）。编号照我们这个包的规矩：特效 0 起、资源表 400000 + 同一个号"""
    ids = meta.get('fx') or []
    res_files = meta.get('fx_res') or []
    if not ids and not res_files:
        return 0
    p = os.path.join(ctx.a.out, 'sfx', 'sfxbnd_c0000.ffxbnd.dcx')
    raw = erlib.read_dcx(p)        # 写出是延迟的（defer_writes）：直接读盘的话每个模组都拿到没改过的包，最后一个把前面的全盖掉
    files = erlib.read_bnd4_full(raw)
    have = {n.lower() for _f, n, _d in files}
    nxt = max([f for f, n, _d in files if n.lower().endswith('.fxr')] or [-1]) + 1
    n = 0
    for fid in ids:
        fx, res = 'f%09d.fxr' % fid, 'f%09d.ffxreslist' % fid
        if (FX_DIR + fx).lower() in have:
            # 别的模组已经带了同一个特效（Inner 系列共用的那批）：资源表取并集（有的模组那份是空的）
            k = next(i for i, (_f, n2, _d) in enumerate(files) if n2.lower() == (RES_DIR + res).lower())
            old = files[k][2].decode('ascii', 'replace').split()
            add = [x for x in open(os.path.join(d, 'fx', res), 'rb').read().decode('ascii', 'replace').split() if x not in old]
            if add:
                files[k] = (files[k][0], files[k][1], ''.join(x + '\r\n' for x in old + add).encode('ascii'))
            continue
        files.append((nxt, FX_DIR + fx, open(os.path.join(d, 'fx', fx), 'rb').read()))
        files.append((400000 + nxt, RES_DIR + res, open(os.path.join(d, 'fx', res), 'rb').read()))
        nxt += 1
        n += 1
    # 特效用到的贴图 / 模型 / 动画（模组新加进公共包的）：编号照原版包的段（贴图 100000 起、模型 200000、动画 300000）
    have = {n.lower() for _f, n, _d in files}
    for name in res_files:
        sub, base = RES_SUB[os.path.splitext(name)[1].lower()]
        path = SFX_ROOT + sub + '\\' + name
        if path.lower() in have:
            continue
        used = [f for f, _n, _d in files if base <= f < base + 100000]
        files.append((max(used) + 1 if used else base, path, open(os.path.join(d, 'fx', name), 'rb').read()))
        have.add(path.lower())
    files.sort(key=lambda t: t[0])
    erlib.write_dcx_file(p, erlib.write_bnd4(files, head=raw[:12], version=raw[0x18:0x20]))
    return n


def hp_boost(ctx, lines, k, meta):
    """settings 的 boss_mods.hp_mult（键 → 倍率，用户 2026-11-06）：这个模组的 Boss 本体形态（mod.json 的 boss_forms，没有就是 fixed）
    在算好的高难度补正上再乘。只改 hpunify.txt 里这些实体挂哪一档血量效果（效果档位 step^i，所以实际倍率差一点点）；随从不动。
    只在 Boss 在原位时调用（after_hpunify 的 arena_on / in_place），不然这些实体位置上是别的敌人"""
    mult = float(((ctx.S.get('boss_mods') or {}).get('hp_mult') or {}).get(k, 1.0))
    c = hpunify.cfg(ctx.S)
    if mult == 1.0 or not c:
        return
    step, kmin, kmax, base = float(c['step']), float(c['k_min']), float(c['k_max']), int(c['sp_base'])
    imin = math.floor(math.log(kmin) / math.log(step))
    cur = {int(l.split()[1]): int(l.split()[2]) for l in lines if l.split()[:1] == ['e']}
    forms = [int(e) for e in (meta.get('boss_forms') or meta.get('fixed') or [])]
    new, seen = {}, []
    for e in forms:
        r = step ** (cur[e] - base + imin) if e in cur else 1.0
        new[e] = base + round(math.log(min(kmax, max(kmin, r * mult))) / math.log(step)) - imin
        seen.append('%d ×%.2f→×%.2f' % (e, r, step ** (new[e] - base + imin)))
    lines[:] = [l for l in lines if not (l.split()[:1] == ['e'] and int(l.split()[1]) in new)]
    lines.extend('e %d %d' % kv for kv in sorted(new.items()))
    ctx.report.append('Boss 模组 %s：血量倍率 ×%g，%d 个实体（%s）' % (k, mult, len(new), '、'.join(seen[:3]) + ('…' if len(seen) > 3 else '')))


def in_place(ctx, meta):
    """没有场地的模组（葛孚雷）：这次 fixed 的位置上放的还是这个模组的 Boss 吗。
    高难度世界里它们留在原位；没做高难度世界时 Boss 不固定，可能被随机到别处，这些位置上是别的敌人"""
    if not ctx.a.randomizer_dir:
        return True
    chrs = {int(c) for c in meta.get('chrs') or []}
    placed = {r[0]: r[2] for r in ((getattr(ctx, 'hpu_src', None) or {}).get('U') or {}).get('bosses') or []}
    fixed = [int(e) for e in meta.get('fixed') or []]
    return bool(fixed) and all(placed.get(e, 0) // 10000 in chrs for e in fixed)


def after_hpunify(ctx):
    """高难度血量 / 攻击力补正（rr/hpunify.py 的 hpu_lines）：模组场地里新加的随从（mod.json 的 helpers：随从实体 → Boss 实体）
    跟着 Boss 乘同一档，保持模组设计的比例（实体优先于敌人参数，见 dark_core 的 hpunify.rs）。只在场地挂上时（arena_on）"""
    ks = keys(ctx)
    lines = getattr(ctx, 'hpu_lines', None)
    if not ks or not lines:
        return
    n = 0
    U = (getattr(ctx, 'hpu_src', None) or {}).get('U') or {}
    for k in ks:
        meta = json.load(open(os.path.join(ctx.data_dir, 'bossmods', k, 'mod.json'), encoding='utf-8'))
        if not meta.get('arena'):
            if in_place(ctx, meta):
                hp_boost(ctx, lines, k, meta)
            continue
        if not arena_on(ctx, k):
            continue
        # 模组新加的敌人参数行只给场地里新加的随从用：不算小怪（不按小怪统一、不会被挑成魇化精英）
        rows = json.load(open(os.path.join(ctx.data_dir, 'bossmods', k, 'params.json'), encoding='utf-8'))['rows']
        added = {int(r['id']) for r in rows if r['param'] == 'NpcParam' and r['kind'] == 'add'}
        if added and U.get('mobs') is not None:
            kept = [m for m in U['mobs'] if not (m[0] == 'n' and m[1] in added)]
            U['mobs'] = type(U['mobs'])(kept)
            lines[:] = [l for l in lines if not (l.split()[0] in ('n', 'an', 'rn') and int(l.split()[1]) in added)]
        for helper, boss in (meta.get('helpers') or {}).items():
            for pre in ('e', 'ae'):
                src = [l.split()[2] for l in lines if l.split()[:2] == [pre, str(boss)]]
                lines[:] = [l for l in lines if l.split()[:2] != [pre, str(helper)]]
                for sp in src:
                    lines.append('%s %s %s' % (pre, helper, sp))
                    n += 1
        hp_boost(ctx, lines, k, meta)
    if n:
        ctx.report.append('Boss 模组：场地新加的随从跟着 Boss 乘高难度补正 %d 条' % n)
