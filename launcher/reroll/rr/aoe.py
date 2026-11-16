# -*- coding: utf-8 -*-
"""范围战灰放大（aoe_skill_radius，用户 2026-11-03）：除主教冲锋、飞行类以外的 14 个范围战灰，判定半径等比放大到 8 米
（这个战灰有伤害的判定里最大那圈到 8 米，其余攻击 / 子弹按同一个倍数；挥武器的小判定、定位用的小子弹不动）。
哪些行为是哪个战灰的、倍数，在 data\\aoe_skills.json（dev\\item_system\\aoe_skills.py 按行名生成，游戏里没有行名）。
  - 改的是这些行为能到的攻击（AtkParam_Pc 的 16 个命中球半径）和子弹（hitRadius / hitRadiusMax，顺着命中后 / 间隔生成的子弹往下）；
  - 只有这个战灰用的行才原地改；别的行为（敌人、法术、别的战技）也用的复制一份新编号再改，只把这个战灰的指向换过去；
  - 子弹特效换成放大的副本（aoe_skills.json 的 fxr：原版编号 → 我们 sfxbnd_c0000 里的编号，dev\\item_system\\sfx\\aoe_scale.js 做）；
  - 要在战技固定伤害 ×1.3 之后（复制的行带上改过的伤害），词条库之前（专属战技借变体整套复制行为时带上这里的指向）。
专属战技战灰（rr/skillgems.py，用户 2026-11-03）也在这里放大：aoe_skills.json 里 still_only 的那些，会飞的子弹（初速 / 最大速度 > 0）
不放大（它命中后 / 飞行中生成的原地子弹照放大），原本 8 米以上的（授血仪式、白王引力波）不在表里；要在 skillgems.build 之前（复制到共享层的行带上新指向）。"""
from .common import *  # noqa: F401,F403

DATA = 'aoe_skills.json'
NEW_BASE = 980000000          # 复制的攻击 / 子弹从这里往上找空号


def aoe_radius(ctx):
    cfg = ctx.S.get('aoe_skill_radius') or {}
    if not cfg.get('enabled', True):
        return
    path = os.path.join(ctx.data_dir, DATA)
    if not os.path.exists(path):
        ctx.report.append('范围战灰放大：缺 data\\%s，没改' % DATA)
        return
    d = json.load(open(path, encoding='utf-8'))
    radius = float(cfg.get('radius', d.get('radius', 8.0)))
    min_r = float(d.get('min_radius', 0.9))
    lay = lambda n: {f: (o, fc) for f, fc, o, bp, bits, dflt in pdm.layout(pdm.load(os.path.join(ctx.data_dir, n + '.xml')))[0] if not bits}
    bl, ul, al = lay('BehaviorParam'), lay('BulletParam'), lay('AtkParam')
    get = lambda o, row, n: struct.unpack_from('<' + o[n][1], row, o[n][0])[0]

    def put(o, row, n, v):
        struct.pack_into('<' + o[n][1], row, o[n][0], v)
    BP, BU, AT = (erlib.Param(ctx.bnd.get(n + '.param')) for n in ('BehaviorParam_PC', 'Bullet', 'AtkParam_Pc'))
    NPC = erlib.Param(ctx.bnd.get('BehaviorParam.param'))
    BCH = ('HitBulletID', 'intervalCreateBulletId')

    def reach(rt, ref):
        """行为能到的 (类别, 编号)：('a', 攻击) / ('b', 子弹)"""
        out, todo = set(), []
        if rt == 0 and ref in AT.rows:
            out.add(('a', ref))
        elif rt == 1:
            todo.append(ref)
        while todo:
            b = todo.pop()
            if ('b', b) in out or b not in BU.rows:
                continue
            out.add(('b', b))
            a = get(ul, BU.rows[b], 'atkId_Bullet')
            if a in AT.rows:
                out.add(('a', a))
            todo += [v for v in (get(ul, BU.rows[b], f) for f in BCH) if v > 0]
        return out
    # 每个攻击 / 子弹被哪些行为用到（玩家 + 敌人的行为）
    users = defaultdict(set)
    beh_ref = {}
    for src, P in (('pc', BP), ('npc', NPC)):
        for i, row in P.rows.items():
            k = (src, i)
            beh_ref[k] = (get(bl, row, 'refType'), get(bl, row, 'refId'))
            for x in reach(*beh_ref[k]):
                users[x].add(k)
    nid = {'a': NEW_BASE, 'b': NEW_BASE}

    def new_id(kind):
        P = AT if kind == 'a' else BU
        while nid[kind] in P.rows:
            nid[kind] += 1
        nid[kind] += 1
        return nid[kind] - 1
    rmax_of = lambda r: max(get(al, r, 'hit%d_Radius' % k) for k in range(16))
    total = Counter()
    lines = []
    for sid, sk in sorted(d['skills'].items(), key=lambda kv: int(kv[0])):
        scale = sk.get('scale')
        if not scale:
            continue
        scale = scale * radius / float(d.get('radius', 8.0))
        listed = {('pc', i) for i in sk['behaviors'] if i in BP.rows}
        refs = {beh_ref[k] for k in listed}
        still = bool(sk.get('still_only'))      # 专属战技战灰：会飞的子弹不放大；只认列出的行为（原武器变体下的原行 / DLC 的共享行）
        mine = listed if still else listed | {k for k, r in beh_ref.items() if k[0] == 'pc' and r in refs and 300000000 <= k[1] < 500000000}    # 同一个指向的复制行为也算
        fxr = {int(k): v for k, v in d.get('fxr', {}).get(sid, {}).items()}
        own_cache = {}
        n_scaled = n_copy = n_sfx = 0

        def own(kind, i):
            """这个战灰自己的一份：只有它用的原地改，别人也用的复制一份（同一个原行只复制一次）"""
            nonlocal n_copy
            if all(u in mine for u in users[(kind, i)]):
                return i
            if (kind, i) not in own_cache:
                P = AT if kind == 'a' else BU
                j = new_id(kind)
                P.add_row(j, bytes(P.rows[i]))
                own_cache[(kind, i)] = j
                n_copy += 1
            return own_cache[(kind, i)]
        done = set()

        def walk_bullet(b):
            nonlocal n_scaled, n_sfx
            if b in done or b not in BU.rows:
                return
            done.add(b)
            row = BU.rows[b]
            r = max(get(ul, row, 'hitRadius'), get(ul, row, 'hitRadiusMax'))
            moving = still and max(get(ul, row, 'initVellocity'), get(ul, row, 'maxVellocity')) > 0
            if r >= min_r and not moving:
                for f in ('hitRadius', 'hitRadiusMax'):
                    v = get(ul, row, f)
                    if v > 0:
                        put(ul, row, f, v * scale)
                for f in ('sfxId_Bullet', 'sfxId_Hit', 'sfxId_Flick'):
                    v = get(ul, row, f)
                    if v in fxr:
                        put(ul, row, f, fxr[v])
                        n_sfx += 1
                n_scaled += 1
                a = get(ul, row, 'atkId_Bullet')
                if a in AT.rows and rmax_of(AT.rows[a]) >= min_r:
                    a2 = own('a', a)
                    put(ul, row, 'atkId_Bullet', a2)
                    scale_atk(a2)
            elif moving and get(ul, row, 'HitBulletID') > 0 and get(ul, row, 'sfxId_Hit') in fxr:
                put(ul, row, 'sfxId_Hit', fxr[get(ul, row, 'sfxId_Hit')])     # 落地爆炸的光效（火焰唾球），子弹本身不放大
                n_sfx += 1
            for f in BCH:
                c = get(ul, row, f)
                if c > 0 and c in BU.rows:
                    c2 = own('b', c)
                    put(ul, row, f, c2)
                    walk_bullet(c2)
        done_a = set()

        def scale_atk(a):
            nonlocal n_scaled
            if a in done_a:
                return
            done_a.add(a)
            row = AT.rows[a]
            if rmax_of(row) < min_r:
                return
            for k in range(16):
                f = 'hit%d_Radius' % k
                v = get(al, row, f)
                if v > 0:
                    put(al, row, f, v * scale)
            n_scaled += 1
        for _src, i in sorted(mine):
            row = BP.rows[i]
            rt, ref = get(bl, row, 'refType'), get(bl, row, 'refId')
            if rt == 0 and ref in AT.rows and rmax_of(AT.rows[ref]) >= min_r:
                a2 = own('a', ref)
                put(bl, row, 'refId', a2)
                scale_atk(a2)
            elif rt == 1 and ref in BU.rows:
                b2 = own('b', ref)
                put(bl, row, 'refId', b2)
                walk_bullet(b2)
        total.update(scaled=n_scaled, copies=n_copy, sfx=n_sfx)
        lines.append('%s ×%.2f（%d 行%s%s）' % (sk['zh'], scale, n_scaled, '，复制 %d' % n_copy if n_copy else '', '，特效 %d' % n_sfx if n_sfx else ''))
    for n, P in (('BehaviorParam_PC', BP), ('Bullet', BU), ('AtkParam_Pc', AT)):
        ctx.bnd.put(n + '.param', P.serialize())
    ctx.report.append('范围战灰放大到 %g 米：%s；共改 %d 行，复制 %d 行，换特效 %d 处' % (
        radius, '、'.join(lines), total['scaled'], total['copies'], total['sfx']))
