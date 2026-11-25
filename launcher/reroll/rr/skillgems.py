# -*- coding: utf-8 -*-
"""专属战技的判定换到共享层 + 专属战技战灰（settings 的 skill_gems）。数据在 data\\skill_gems.json（dev\\item_system\\skill_gems.py 生成，说明见那边）：
  - 换号（skill_gems.renumber，用户 2026-11-03「修复做了吧」）：所有原版武器带的专属战技（不在战灰里的；共用一套动作的欧赫剑舞两个除外）
    的判定换到共享层，在哪把武器上都找得到。生成武器配了别家的专属战技不用再换行为变体（以前换成原武器的，本体的普攻判定跟着变，双持轻击没伤害）：
    ctx.free_skills 给 affixes 写 skillinfo（当成战灰：dark_core 生成和读档重建时都用本体自己的变体）、跳过 skill_vars；
  - 战灰（skill_gems.enabled，用户 2026-11-03：「都做成战灰 冲突的就先不管了 然后范围依旧是8」，2026-11-04：「把单体的专属战技也做成战灰
    然后开放战技 并且说明按照原版风格」）：所有换过号的专属战技（145 个）做成战灰，在暗黑商店的战灰商店卖（darkshop.ash_shop 接在原版战灰后面）；
    按原武器归类开放：近战的能装在所有近战武器上、盾的所有盾、弓的所有弓（大弓只装原武器是大弓的，GREATBOW_BIT；原版「能在所有的…使用」那几条的武器类型位和文字），
    弩、法杖、火把、调香瓶的只能装在原类型；图标借原武器的；和原版战灰 / 别的专属战技同名的在名字后面加原武器类型（照原版「箭步（上砍）」）；
  - 原版专属战技的判定在原武器自己的行为变体下（3VVVJJJ），别的武器找不到 → 动作里的判定号换成没人用过的号，判定行复制到共享层（变体 0）；
    动作包 chr\\c0000.anibnd.dcx 启动时从本机 Data3 取出来改好判定号（只改这几个战技的 TAE），regulation 写好后放进重随输出
    （place_anim）跟着 DR_Reroll 挂载，做一次缓存在 cache\\anim（游戏更新 / 数据变了重做）。原行不动，原武器照样能用；
  - 动作包改不了（读不了 Data3、游戏更新后对不上）的战技：不复制、不做战灰（原版判定号对原武器照旧有效）。动作包每次重随前先删掉
    （reroll.load），这一步做成了才放回去，免得旧动作包配上没有新行的参数（那样原武器的战技也没伤害）；
  - 范围放大到 8 米在 rr/aoe.py（aoe_skills.json 里这些战技的行为，在这一步之前改好，复制的行带上新指向）；动作里直接放的特效
    （aoe_skills.json 的 tae_sfx，用户 2026-11-03「全部都做」）在这里一起换成放大的副本（编号照 aoe_skills.json 的 fxr，特效在我们的 sfxbnd_c0000）。
要在 aoe.aoe_radius 之后、affixes.build 之前（skillinfo / skill_vars 要用 free_skills）、darkshop.build 之前。"""
import hashlib
import shutil

from .common import *  # noqa: F401,F403
import tae

DATA = 'skill_gems.json'
GEM_TEMPLATE = 22500                    # 战灰：幻影共击（唤声船也照它复制）
GEM_SORT = 364000                       # 排在原版所有战灰后面（原版最大 363080）
GEM_RARITY = 3
ANIBND = '/chr/c0000.anibnd.dcx'
KEY = os.path.join('menu', 'data3_key.pem')
ANIM_VERSION = 3                        # 改了打补丁的办法就加一（缓存重做）；2：加了换特效；3：雷电羊球接着滚的动作静音
# 雷电羊球按住一直滚（动作 ×10）时接着滚的动作每秒重放约 10 次，音效跟着响，只留按下第一下的（用户 2026-11-09「只留第一下」）。
# 音效编号改成不存在的：游戏找不到音效就不响（敌人随机把敌人放到没加载它音效的地图时也是这样，只是没声音）
MUTE_TAE, MUTE_ANIMS, NO_SOUND = 'a713.tae', (40010, 40015), 999999999
OWN_GEMS = (29500, 29999)               # 我们自己的战灰（唤声船 29500、专属战技战灰 29600 起）：放开原版战灰时不动
# 大弓的位不往上加（用户 2026-11-24「大弓不能装小弓和中弓的战技」）：弓类战灰照旧放开到小弓、长弓，大弓只装本来就能装在大弓上的
# （原版贯穿射击、箭雨、埃贡的猎龙，专属战技里大弓的拉塔恩的骤雨）。放开后没有大弓的用原版「能在小弓、长弓类武器使用」那条（63033）。
# skill_gems.json 的弓组照旧写三种弓（dev\item_system\skill_gems.py），这里按原武器去掉
GREATBOW_BIT, GREATBOW_TYPE = 26, 53
BOW_NO_GREAT = (63033, '能在小弓、长弓类武器使用', 'Usable on light bows and longbows')
P = 100000000
TEXT = {
    'zh': dict(gem='战灰：%s', info='能赋予武器属性、战技',
               cap='能赋予武器属性、战技的战灰。\n属性为“标准”，战技如下：\n\n　战技：%s\n%s\n\n%s'),
    'en': dict(gem='Ash of War: %s', info='Grants affinities and skills to an armament',
               cap='This Ash of War grants an armament the Standard affinity and the following skill:\n\n"%s: %s"\n\n%s'),
}


def cfg(S):
    """(做不做战灰, 换不换号)"""
    c = S.get('skill_gems') or {}
    return bool(c.get('enabled', True)), bool(c.get('renumber', True))


def open_vanilla(ctx, d):
    """原版战灰也按开放分组放开（skill_gems.open_vanilla，用户 2026-11-04「原版也直接放开」）：原来能装的武器类型碰到哪组（近战 / 盾 / 弓），
    就开放到整组（skill_gems.json 的 open：原版「能在所有的…使用」那几条的类型位），原来另外能装的（法杖、火把…）留着；只能装调香瓶的不动；大弓那一位不往上加（GREATBOW_BIT）。
    说明（GemCaption）最后一段换成原版那条文字，碰到几组 / 留着别的类型的照这个写法拼（「能在所有的近战武器、盾类武器使用。」），
    mountWepTextId 换成第一组那条。只改说明最后一段是「能在…」的（原版正式的战灰；测试用的那些没有说明）。返回 [(编号, 中文那句)]"""
    op = d.get('open') or {}
    if not op:
        return []
    names = {int(k): v for k, v in (d.get('type_names') or {}).items()}
    L = {n: (fc, o) for n, fc, o, bp, nb, _ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGem.xml')))[0]}
    G = erlib.Param(ctx.bnd.get('EquipParamGem.param'))
    m0 = L['canMountWep_Dagger'][1]
    bits_of = {g: set(v['bits']) for g, v in op.items()}
    every = set().union(*bits_of.values())
    # 只属于这一组的位才算碰到这一组（突刺盾 38 原版「所有的近战」「所有的盾」都带着）
    detect = {g: b - set().union(*(bits_of[h] for h in bits_of if h != g)) for g, b in bits_of.items()}
    order = [g for g in ('melee', 'shield', 'bow') if g in op]
    words = {'melee': ('近战武器', 'melee armaments'), 'shield': ('盾类武器', 'shields'), 'bow': ('弓类武器', 'bows')}
    plural = lambda t: t.lower() + ('es' if t.lower().endswith(('ch', 's')) else 's')
    # 原版战灰的说明在哪个 FMG（GemCaption / _dlc01 / _dlc02）
    msgs = {}
    for code in ('zhocn', 'engus'):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if erlib.dcx_exists(mp):
            mb = erlib.Bnd4(erlib.read_dcx(mp))
            msgs[code] = (mp, mb, {n: erlib.read_fmg_full(mb.get(n)) for n in mb.entries if n.startswith('GemCaption')})
    if 'zhocn' not in msgs:
        return []
    caps = {code: {i: (n, t) for n, (_h, ents) in fm.items() for i, t in ents if t} for code, (_p, _b, fm) in msgs.items()}
    done = []
    for i, row in G.rows.items():
        cz = caps['zhocn'].get(i)
        if OWN_GEMS[0] <= i <= OWN_GEMS[1] or not cz or not cz[1].split('\n\n')[-1].startswith('能在'):
            continue                                # 我们自己的战灰（唤声船、专属战技战灰）不动
        b = {k for k in range(48) if row[m0 + k // 8] >> (k % 8) & 1}
        groups = [g for g in order if b & detect[g]]
        new = b.union(*(bits_of[g] for g in groups)) if groups else b
        if GREATBOW_BIT not in b:                   # 大弓只装本来就能装在大弓上的
            new.discard(GREATBOW_BIT)
        if new == b:
            continue
        for k in new:
            row[m0 + k // 8] |= 1 << (k % 8)
        extra = sorted(b - every - ({37} if 'melee' in groups else set()))     # 调香瓶算在近战里（原版「所有的近战武器」那条带着它）
        no_great = 'bow' in groups and GREATBOW_BIT not in new
        text = BOW_NO_GREAT[0] if no_great and groups[0] == 'bow' else op[groups[0]]['text']
        if len(groups) == 1 and not extra:
            zh, en = (BOW_NO_GREAT[1], BOW_NO_GREAT[2]) if no_great else (op[groups[0]]['zh'], op[groups[0]]['en'])
        else:
            w = dict(words, bow=('小弓、长弓类武器', 'light bows and longbows')) if no_great else words
            zh = '能在所有的%s使用' % '、'.join([w[g][0] for g in groups] + ['%s类武器' % names[k][0] for k in extra if k in names])
            en = 'Usable on all %s' % ' and '.join([w[g][1] for g in groups] + [plural(names[k][1]) for k in extra if k in names])
        struct.pack_into('<' + L['mountWepTextId'][0], row, L['mountWepTextId'][1], text)
        for code, line in (('zhocn', zh + '。'), ('engus', ' '.join(en.split('\n')) + '.')):
            hit = caps.get(code, {}).get(i)
            if hit:
                fmg, t = hit
                hdr, ents = msgs[code][2][fmg]
                msgs[code][2][fmg] = (hdr, [(k, (t.rsplit('\n\n', 1)[0] + '\n\n' + line) if k == i else v) for k, v in ents])
        done.append((i, zh))
    ctx.bnd.put('EquipParamGem.param', G.serialize())
    for code, (mp, mb, fm) in msgs.items():
        for n, (hdr, ents) in fm.items():
            mb.put(n, erlib.write_fmg(hdr, ents))
        erlib.write_dcx_file(mp, bytes(mb.data))
    return done


ANY_WEAPON_GEMS = (50400, 200100, 29500)    # 雷电羊球、熔炉百相之羽、唤声船
ANY_WEAPON_ARTS = (1026,)                   # 按技艺找的（专属战技的宝石编号看排序）：雷云化身
MOUNT_BITS = 44                             # 武器类型的位：字段表只有前 36 个的名字（canMountWep_*），36~43 是 DLC 的武器类型


def any_weapon(ctx):
    """这几个战灰能装在任意武器上（用户 2026-11-09）：武器类型的位全开；生成武器都能换战灰（dark_core build_row），法杖、圣印记 rr/mariner.py 开过了。
    原版那条「能在所有的…使用」的文字没有「所有武器」这一条，和唤声船一样不用（-1），说明最后一段改成能装在所有武器上"""
    L = {n: (fc, o) for n, fc, o, bp, nb, _ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamGem.xml')))[0]}
    G = erlib.Param(ctx.bnd.get('EquipParamGem.param'))
    m0 = L['canMountWep_Dagger'][1]
    art = L['swordArtsParamId']
    gems = [g for g in ANY_WEAPON_GEMS if g in G.rows] + [g for g, r in sorted(G.rows.items()) if struct.unpack_from('<' + art[0], r, art[1])[0] in ANY_WEAPON_ARTS]
    for g in gems:
        row = G.rows[g]
        for k in range(MOUNT_BITS):
            row[m0 + k // 8] |= 1 << (k % 8)
        struct.pack_into('<' + L['mountWepTextId'][0], row, L['mountWepTextId'][1], -1)
    ctx.bnd.put('EquipParamGem.param', G.serialize())
    lines = {'zhocn': '能在所有的武器使用。\n（含法杖、圣印记）', 'engus': 'Usable on all armaments, including staves and sacred seals.'}
    n_text = 0
    for code, line in lines.items():
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for n in [x for x in mb.entries if x.startswith('GemCaption')]:
            hdr, ents = erlib.read_fmg_full(mb.get(n))
            new = [(k, t.rsplit('\n\n', 1)[0] + '\n\n' + line if k in gems and t and '\n\n' in t else t) for k, t in ents]
            if new != ents:
                n_text += sum(1 for a, b in zip(new, ents) if a != b)
                mb.put(n, erlib.write_fmg(hdr, new))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.report.append('任意武器的战灰：%s（说明改了 %d 条）' % (gems, n_text))


def chr_out(a):
    return os.path.join(a.out, 'chr')


def anim(ctx, d):
    """改好判定号（和放大的特效编号）的动作包放进重随输出（chr\\c0000.anibnd.dcx）。返回 (改好的战技集合, 说明)；有缓存直接拷"""
    import vanilla as vsrc
    todo = [s for s in d['skills'] if s['judges'] or s.get('fx')]
    if not todo:
        return set(), ''
    g = vsrc.game_dir()
    key = os.path.join(ctx.data_dir, KEY)
    if not g or not os.path.isfile(os.path.join(g, 'Data3.bhd')) or not os.path.isfile(key):
        return set(), '找不到游戏的 Data3 或钥匙'
    bhd = os.path.join(g, 'Data3.bhd')
    spec = json.dumps([[s['sid'], s['tae'], s['judges'], s['events'], s.get('fx', {})] for s in todo], sort_keys=True)
    st = [os.stat(p) for p in (bhd, bhd[:-4] + '.bdt')]
    stamp = hashlib.sha1(repr([(x.st_size, x.st_mtime_ns) for x in st] + [ANIM_VERSION, spec]).encode('utf-8')).hexdigest()[:16]
    cache = os.path.join(HERE, 'cache', 'anim')
    path = os.path.join(cache, 'c0000_%s.anibnd.dcx' % stamp)
    okf = path[:-len('.anibnd.dcx')] + '.ok.json'
    t0 = time.time()
    done = json.load(open(okf, encoding='utf-8')) if os.path.isfile(okf) else None
    ok, n_fx, n_mute = (set(done['ok']), done['fx'], done.get('mute', 0)) if done else (None, 0, 0)
    if ok is not None and (os.path.isfile(path) or not ok):
        how = '沿用缓存'
    else:
        arc = erlib.GameArchive(bhd, open(key, encoding='ascii').read())
        bnd = erlib.Bnd4(erlib.dcx_decompress(arc.read(ANIBND)))
        ok, bad, n_fx = set(), [], 0
        for s in todo:
            if s['tae'] not in bnd.entries:
                bad.append('%s（没有 %s）' % (s['zh'], s['tae']))
                continue
            e = bnd.entries[s['tae']]
            hits = [(j, o) for j, o in tae.judges(bnd.get(s['tae'])) if str(j) in s['judges']]
            if len(hits) != s['events']:           # 游戏更新改了动作：对不上就不改这个战技
                bad.append('%s（%d / %d 个事件）' % (s['zh'], len(hits), s['events']))
                continue
            for j, o in hits:
                struct.pack_into('<i', bnd.data, e['off'] + o, s['judges'][str(j)])
            for v, o in tae.effects(bnd.get(s['tae'])):     # 放特效的事件：换成放大的副本
                if str(v) in s.get('fx', {}):
                    struct.pack_into('<i', bnd.data, e['off'] + o, s['fx'][str(v)])
                    n_fx += 1
            ok.add(s['sid'])
        if bad:
            log('    专属战技战灰：动作对不上，不做 %s' % '、'.join(bad))
        if MUTE_TAE in bnd.entries:
            e = bnd.entries[MUTE_TAE]
            for _v, o in tae.sounds(bnd.get(MUTE_TAE), MUTE_ANIMS):
                struct.pack_into('<i', bnd.data, e['off'] + o, NO_SOUND)
                n_mute += 1
        if not n_mute:
            log('    雷电羊球：动作里没找到音效事件，接着滚还会响')
        os.makedirs(cache, exist_ok=True)
        for f in os.listdir(cache):             # 旧的缓存
            os.remove(os.path.join(cache, f))
        if ok:
            tmp = path + '.tmp'
            open(tmp, 'wb').write(erlib.dcx_compress_dflt(bytes(bnd.data)))
            os.replace(tmp, path)
        json.dump({'ok': sorted(ok), 'fx': n_fx, 'mute': n_mute}, open(okf, 'w', encoding='utf-8'))
        how = '从 Data3 重做（%.1f 秒）' % (time.time() - t0)
    ctx.anim_src = path if ok else None
    n_judged = sum(1 for s in todo if s['judges'] and s['sid'] in ok)
    return ok, '动作包%s，改了 %d 个战技的判定号、%d 处特效换成放大的、雷电羊球接着滚的 %d 个音效去掉' % (how, n_judged, n_fx, n_mute)


def place_anim(ctx):
    """regulation 写好以后再把动作包放进输出（中途失败就没有动作包，原版判定号对原武器照旧有效）"""
    src = getattr(ctx, 'anim_src', None)
    if src:
        os.makedirs(chr_out(ctx.a), exist_ok=True)
        tmp = os.path.join(chr_out(ctx.a), 'c0000.anibnd.dcx.tmp')
        shutil.copyfile(src, tmp)
        os.replace(tmp, os.path.join(chr_out(ctx.a), 'c0000.anibnd.dcx'))


def build(ctx):
    ctx.free_skills = set()
    gems_on, renum_on = cfg(ctx.S)
    if not gems_on and not renum_on:
        return
    path = os.path.join(ctx.data_dir, DATA)
    if not os.path.exists(path):
        ctx.report.append('专属战技：缺 data\\%s，判定没换、战灰没做' % DATA)
        return
    d = json.load(open(path, encoding='utf-8'))
    if not renum_on:                            # 不换号：只留不用换号的（DLC 本来就在共享层的）
        d['skills'] = [s for s in d['skills'] if not s['rows']]
        for s in d['skills']:
            s['judges'] = {}
    # 动作里直接放的特效：范围放大开着（aoe_skill_radius）、这个战技放大了，就换成 aoe_skills.json 里分好编号的放大副本
    ac = ctx.S.get('aoe_skill_radius') or {}
    ap = os.path.join(ctx.data_dir, 'aoe_skills.json')
    ad = json.load(open(ap, encoding='utf-8')) if ac.get('enabled', True) and os.path.exists(ap) else {}
    for s in d['skills']:
        sk, m = ad.get('skills', {}).get(str(s['sid'])) or {}, ad.get('fxr', {}).get(str(s['sid'])) or {}
        s['fx'] = {str(v): m[str(v)] for v in sk.get('tae_sfx', []) if str(v) in m} if sk.get('scale') else {}
    try:
        ok, anim_msg = anim(ctx, d)
    except Exception as e:                      # 动作包做不了：要换判定号的战技不做，其他照做
        ok, anim_msg = set(), '动作包没做成（%s: %s）' % (type(e).__name__, e)
    skills = [s for s in d['skills'] if not s['rows'] or s['sid'] in ok]       # 只换成空号的（DLC 里的残留判定）不改也照常能用
    skipped = [s['zh'] for s in d['skills'] if s not in skills]
    ctx.free_skills = {s['sid'] for s in skills if s['free']}

    lay = lambda xml: {n: (fc, o, bp, nb) for n, fc, o, bp, nb, _ in pdm.layout(pdm.load(os.path.join(ctx.data_dir, xml)))[0]}
    Lg, Lb, Ls = lay('EquipParamGem.xml'), lay('BehaviorParam.xml'), lay('SwordArtsParam.xml')

    def get(L, r, f):
        fc, o, bp, nb = L[f]
        return (r[o] >> bp) & ((1 << nb) - 1) if nb else struct.unpack_from('<' + fc, r, o)[0]

    def put(L, r, f, v):
        fc, o, bp, nb = L[f]
        if nb:
            r[o] = (r[o] & ~(((1 << nb) - 1) << bp)) | ((int(v) & ((1 << nb) - 1)) << bp)
        else:
            struct.pack_into('<' + fc, r, o, v)
    G, B, A = (erlib.Param(ctx.bnd.get(n + '.param')) for n in ('EquipParamGem', 'BehaviorParam_PC', 'SwordArtsParam'))
    if GEM_TEMPLATE not in G.rows:
        raise RuntimeError('专属战技战灰：缺模板战灰 %d' % GEM_TEMPLATE)
    # 判定行复制到共享层：新号在这个前缀下谁都没用过（开发时按原版挑的；这里再核对一遍，免得和后来加的行撞上）
    used = defaultdict(set)
    for i in B.rows:
        used[i // P].add(i % 1000)
    n_rows = 0
    for s in skills:
        for src, new in s['rows'].items():
            src, new = int(src), int(new)
            if src not in B.rows or new % 1000 in used[new // P]:
                raise RuntimeError('专属战技战灰：%s 的判定行 %d → %d 复制不了（原行不在 / 新号被占）' % (s['zh'], src, new))
        for src, new in s['rows'].items():
            row = bytearray(B.rows[int(src)])
            put(Lb, row, 'variationId', 0)
            put(Lb, row, 'behaviorJudgeId', int(new) % 1000)
            B.add_row(int(new), bytes(row))
            used[int(new) // P].add(int(new) % 1000)
            n_rows += 1
    # 战灰：能装的武器类型照 skill_gems.json 的 mount_bits（开放分组），属性只有标准。
    # 动作包没做成的（skipped）战灰行和文字也照建、只是不上架（崩溃风险审查 2026-11-19 第 4 条）：以前拿到的还在存档里，缺了行读档会出问题；
    # 装在原武器以外的武器上判定找不到（打不出伤害），但不会崩
    mount0 = Lg['canMountWep_Dagger'][1]
    gem_skills = [s for s in d['skills'] if s['gem'] and gems_on]
    for s in gem_skills:                            # 弓组：原武器不是大弓的不能装在大弓上（GREATBOW_BIT），说明跟着换
        if s.get('group') == 'bow' and GREATBOW_TYPE not in s['types'] and GREATBOW_BIT in s['mount_bits']:
            s['mount_bits'] = [b for b in s['mount_bits'] if b != GREATBOW_BIT]
            s['mount_text'], zh, en = BOW_NO_GREAT
            s['usable_zh'], s['usable_en'] = zh + '。', en + '.'
    gems = []
    for k, s in enumerate(gem_skills):
        if s['gem'] in G.rows or s['sid'] not in A.rows:
            raise RuntimeError('专属战技战灰：战灰编号 %d 被占 / 战技 %d 不在' % (s['gem'], s['sid']))
        g = bytearray(G.rows[GEM_TEMPLATE])
        for f in Lg:
            if f.startswith('configurableWepAttr'):
                put(Lg, g, f, 1 if f == 'configurableWepAttr00' else 0)
        for o in range(mount0, mount0 + 6):         # 武器类型的位（含 DLC 类型的 36~43 位）
            g[o] = 0
        for bit in s['mount_bits']:
            g[mount0 + bit // 8] |= 1 << (bit % 8)
        for f, v in (('swordArtsParamId', s['sid']), ('iconId', s['icon']), ('sortId', GEM_SORT + k * 10), ('defaultWepAttr', 0),
                     ('mountWepTextId', s['mount_text']), ('rarity', GEM_RARITY), ('spEffectId0', -1), ('spEffectId1', -1), ('spEffectId2', -1)):
            put(Lg, g, f, v)
        G.add_row(s['gem'], bytes(g))
        if s in skills:
            gems.append(s['gem'])
    for n, Pm in (('EquipParamGem', G), ('BehaviorParam_PC', B)):
        ctx.bnd.put(n + '.param', Pm.serialize())

    # 文字：名字、说明（战技说明照原版的专用战技说明，去掉第一行「专用战技：…」）
    for code, lang in (('zhocn', 'zh'), ('engus', 'en')):
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        T = TEXT[lang]
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        arts = {}
        for n in mb.entries:
            if n.replace('.fmg', '').split('_dlc')[0] in ('ArtsName', 'ArtsCaption'):
                kind = n.replace('.fmg', '').split('_dlc')[0]
                arts.setdefault(kind, {}).update((i, t) for i, t in erlib.read_fmg_full(mb.get(n))[1] if t)
        add = {'GemName.fmg': {}, 'GemInfo.fmg': {}, 'GemCaption.fmg': {}}
        for s in gem_skills:
            tid = get(Ls, A.rows[s['sid']], 'textId')
            name = arts.get('ArtsName', {}).get(tid) or s[lang]
            body = (arts.get('ArtsCaption', {}).get(tid) or '').split('\n\n', 1)[-1].strip()
            # 最后一段「能在…使用」照原版战灰的写法（skill_gems.json 的 usable_*：原版「能在所有的近战武器使用」这几条，或原类型）
            if lang == 'zh':
                body = '\n'.join('　' + l for l in body.split('\n') if l)
                cap = T['cap'] % (name, body, s['usable_zh'])
            else:
                cap = T['cap'] % (name, ' '.join(body.split('\n')), s['usable_en'])
            add['GemName.fmg'][s['gem']] = T['gem'] % (name + s['suffix_' + lang])
            add['GemInfo.fmg'][s['gem']] = T['info']
            add['GemCaption.fmg'][s['gem']] = cap
        for fmg, ents in add.items():
            if fmg not in mb.entries:
                raise RuntimeError('专属战技战灰：文字包里没有 %s' % fmg)
            hdr, old = erlib.read_fmg_full(mb.get(fmg))
            dd = dict(old)
            dd.update(ents)
            mb.put(fmg, erlib.write_fmg(hdr, sorted(dd.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    ctx.skill_gems = gems                       # 上架的（darkshop.ash_shop）：没做成的不在里面
    ctx.skill_gem_info = [{'gem': s['gem'], 'weapons': list(s['weapons'])} for s in gem_skills if s in skills]   # 暗黑商店分阶段解锁：跟着武器本体的区域（rr/darkshop.py）
    ctx.features['skill_gems'] = {'gems': gems, 'free': sorted(ctx.free_skills)}
    if gems_on and (ctx.S.get('skill_gems') or {}).get('open_vanilla', True):
        opened = open_vanilla(ctx, d)
        kinds = Counter(z for _i, z in opened)
        ctx.report.append('原版战灰放开 %d 个：%s' % (len(opened), '、'.join('%s %d 个' % (z, n) for z, n in kinds.most_common())))
    unsold = [s['zh'] for s in gem_skills if s not in skills]
    ctx.report.append('专属战技：%d 个的判定在共享层（换号的判定行复制 %d 行；%s），生成武器配别家的专属战技不再换行为变体；'
                      '战灰 %d 个（%d~%d，按原武器开放到所有近战 / 盾 / 弓，战灰商店卖）：%s%s%s' % (
                          len(ctx.free_skills), n_rows, anim_msg, len(gems), min(gems, default=0), max(gems, default=0),
                          '、'.join(s['zh'] for s in gem_skills if s in skills), '；没做：%s' % '、'.join(skipped) if skipped else '',
                          '（其中 %d 个战灰照建、不上架，以前拿到的还在）' % len(unsold) if unsold else ''))
