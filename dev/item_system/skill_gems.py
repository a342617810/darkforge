# -*- coding: utf-8 -*-
"""专属战技的判定换到共享层 + 做成战灰的数据。只在开发时跑，写 launcher\\reroll\\data\\skill_gems.json；重随的 rr/skillgems.py
照它复制判定行、改动作包里的判定号、建战灰和文字。
  - 战灰（用户 2026-11-03：「都做成战灰 冲突的就先不管了 然后范围依旧是8」「大于8的就不管了」）：GEMS 里的 33 个。
  - 换号（用户 2026-11-03「修复做了吧」）：所有原版武器带的专属战技（不在任何战灰里）都换。换过的战技在哪把武器上都找得到自己的判定，
    生成武器配了别家的专属战技也不用再把行为变体换成原武器的（以前换了，本体的普攻判定跟着变，双持轻击没伤害），skillinfo 写成战灰一样（free）。
  - 战技动作：swordArtsTypeNew ≥ 170 的战技只有一套动作 TAE a(600 + 类型)，在 c0000.anibnd（Data3），不分武器。攻击 / 子弹行为事件
    （类型 1 / 2）参数 +8 是判定号：≥ 1000 的 = 前缀 × 1000 + 判定（3 战技，5 / 6 / 7 也是战技用的），< 1000 的是前缀 1（普攻）；
    行为编号 = 前缀亿位 + 武器的行为变体 × 1000 + 判定，找不到退到大类（变体 // 100 × 100），再退到共享层（变体 0）。
  - 原版专属战技的判定在原武器自己的变体下（3VVVJJJ），别的武器找不到。改法：动作里的判定号换成这个前缀下全游戏都没用过的号，
    判定行复制到共享层（新号），所有武器都找得到；原行不动。各前缀的规则：
      前缀 1（架式战技里的轻重击）：只有原武器自己有的换号（不换的话别的本体没有这一行）；原武器的覆盖了大类 / 共享的照旧（本体用自己的那套）；
      前缀 3：原武器 / 大类层的换号（大类的也换：别的大类的本体找到的是别的行）；共享层的是通用战灰那套，不动；原武器上找不到的换成「空号」
        （永远没行；原版就不起作用，比如血怪授血里授血仪式留下的 3935，但别的本体可能找到别家的行）；
      前缀 5 / 6 / 7：原武器 / 大类层的换号；共享层的只有同类武器里有变体自己带同号行（会用错行）才换。
  - 一套动作好几个战技用（欧赫剑舞的大剑版、直剑版：判定行不一样）：不换，这几个照旧（生成时行为变体换成原武器的）。
  - 战灰能装的武器类型 = 原武器的类型；图标借原武器的；范围放大在 aoe_skills.py（读战灰那些的 aoe_behaviors、tae_fx：动作里直接放的特效，
    放大时一起换成放大的副本）。
用法：python skill_gems.py（要本机游戏的 Data0 / Data3；新号沿用上次 skill_gems.json 的分配）"""
import collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
GAME = os.path.dirname(PALY)
sys.path.insert(0, RR)
import erlib, paramdef_min as pdm, tae  # noqa: E402

erlib.DLL_DIRS[:] = [os.path.join(PALY, 'randomizer'), GAME]
OUT = os.path.join(RR, 'data', 'skill_gems.json')
# 最先做成战灰的 33 个（SwordArtsParam 编号，战灰编号 29600 起照这个顺序）：原版失色武器的范围战技 + DLC 专属战技。
# 其余专属战技（单体的，用户 2026-11-04「把单体的专属战技也做成战灰」）接在后面，按战技编号排
GEMS = [1030, 1029, 1041, 1022, 1038, 1193, 1025, 1048, 1028, 1031, 1168, 1198, 1001, 1186, 1005, 1033, 1050, 1185, 1188, 1190, 1034, 1040,
        5180, 5220, 5450, 5540, 5170, 5190, 5260, 5280, 5300, 5560, 5160]
GEM_FIRST = 29600            # 战灰编号（唤声船是 29500）
GEM_SKIP = {5461}            # 没有名字的（原版没用上的）
# 范围战技（放大到 8 米，aoe_skills.py）：上面 33 个里除了割草（自己的判定都是挥刀的小判定），再加原先因为冲突没做的唤星、吞世、信仰喷发
# （原本 8 米以上的唤星、吞世 aoe_skills.py 会跳过）
AOE = (set(GEMS) - {5450}) | {1000, 1032, 1183}
# 开放（用户 2026-11-04「开放战技 并且说明按照原版风格 不要只是标注可用武器类型」）：按原武器归类，用原版的「能在所有的近战 / 盾类 / 弓类武器
# 使用」（mountWepTextId）和原版这几种战灰最常见的武器类型位；弩、弩炮、法杖、圣印记、火把、调香瓶的战技离不开那种武器，只能装在原类型上。
# 弓组这里照旧三种弓；重随时 rr/skillgems.py 把原武器不是大弓的去掉大弓那一位（用户 2026-11-24「大弓不能装小弓和中弓的战技」）
OPEN = {'melee': (63042, list(range(0, 16)) + list(range(17, 24)) + [36] + list(range(38, 44))),
        'shield': (63041, [32, 33, 34, 38]), 'bow': (63034, [24, 25, 26])}
SHIELD_TYPES, BOW_TYPES, OWN_TYPES = {65, 67, 69, 90}, {50, 51, 53}, {55, 56, 57, 61, 87, 89}
# 武器类型 → canMountWep 的位（EquipParamGem 第 56 字节第 0 位起；extract_affixes.py MOUNT_BIT）、类型名的文字编号（GR_MenuText）
MOUNT_BIT = {1: 0, 3: 1, 5: 2, 7: 3, 9: 4, 11: 5, 13: 6, 14: 7, 15: 8, 16: 9, 17: 10, 19: 11, 21: 12, 23: 13, 24: 14, 25: 15, 28: 17,
             29: 18, 31: 19, 35: 20, 37: 21, 39: 22, 41: 23, 50: 24, 51: 25, 53: 26, 55: 27, 56: 28, 57: 29, 61: 31, 65: 32, 67: 33,
             69: 34, 87: 35, 88: 36, 89: 37, 90: 38, 91: 39, 92: 40, 93: 41, 94: 42, 95: 43}
TYPE_TEXT = {1: 60010, 3: 60015, 5: 60020, 7: 60025, 9: 60030, 11: 60035, 13: 60040, 14: 60043, 15: 60045, 16: 60046, 17: 60050, 19: 60055,
             21: 60060, 23: 60065, 24: 60067, 25: 60070, 28: 60077, 29: 60080, 31: 60085, 35: 60090, 37: 60100, 39: 60155, 41: 60102,
             50: 60104, 51: 60105, 53: 60110, 55: 60115, 56: 60117, 57: 60120, 61: 60130, 65: 60140, 67: 60145, 69: 60150, 87: 60175,
             88: 60180, 89: 60181, 90: 60182, 91: 60183, 92: 60184, 93: 60185, 94: 60186, 95: 60187}
# 原版有「能在 X 类武器使用」这句单独一条的类型（mountWepTextId；没有的写 -1，说明里自己写）
MOUNT_TEXT = {13: 63008, 3: 63009, 88: 63051, 89: 63052, 90: 63053, 91: 63054, 92: 63055, 93: 63056, 94: 63057, 95: 63058}
P = 100000000


def split(j):
    """TAE 判定号 → (前缀, 判定)；< 1000 的是前缀 1"""
    return (1, j) if j < 1000 else (j // 1000, j % 1000)


def main():
    import vanilla as vsrc
    reg = erlib.Bnd4(erlib.read_regulation(vsrc.path('regulation.bin')))

    def param(name, xml):
        f = next(n for n in reg.entries if os.path.basename(n.replace('\\', '/')) == name + '.param')
        lay, _ = pdm.layout(pdm.load(os.path.join(RR, 'data', xml + '.xml')))
        return {i: pdm.unpack(lay, r) for i, r in erlib.Param(reg.get(f)).rows.items()}
    BH, SA, WP, GE = (param('BehaviorParam_PC', 'BehaviorParam'), param('SwordArtsParam', 'SwordArtsParam'),
                      param('EquipParamWeapon', 'EquipParamWeapon'), param('EquipParamGem', 'EquipParamGem'))
    W = {i: r for i, r in WP.items() if i < P and i % 10000 == 0}
    gem_arts = {r['swordArtsParamId'] for r in GE.values()}
    owners = collections.defaultdict(list)
    for w, r in sorted(W.items()):
        if r['swordArtsParamId'] > 0:
            owners[r['swordArtsParamId']].append(w)
    in_use = set(owners) | gem_arts
    art_users = collections.defaultdict(set)
    for s, r in SA.items():
        if s in in_use:
            art_users[r['swordArtsTypeNew']].add(s)
    # 用过的判定（前缀 → 判定）：原版 + 词条库自己加的行为行（rows.json）
    used = collections.defaultdict(set)
    extra = json.load(open(os.path.join(RR, 'data', 'affixes', 'rows.json'), encoding='utf-8')).get('BehaviorParam_PC', {})
    for i in list(BH) + [int(k) for k in extra]:
        used[i // P].add(i % 1000)
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    old_new = {(s['sid'], int(k)): v for s in old.get('skills', []) for k, v in s.get('judges', {}).items()}
    taken = set(old_new.values())
    void = {}

    def void_of(p):
        if p not in void:
            j = next(j for j in range(999, -1, -1) if j not in used[p])
            used[p].add(j)
            void[p] = p * 1000 + j
        return void[p]
    for p in (3, 5, 6, 7):          # 先占空号（最大的空判定），新号从小往上排
        void_of(p)

    def fresh(sid, judge):
        """这个战技这个判定的新号：上次分过的照旧（还空着的话），不然取最小的空判定。前缀 1 的（< 1000）照旧 < 1000；
        前缀 3 的空号不够（专属战技全换要 500 多个，空的不到 500），接着用前缀 7、6、5 的（DLC 的战技自己就是前缀 3 满了才往 6 / 7 放的，
        前缀只是编号段）"""
        p, _ = split(judge)
        pres = (3, 7, 6, 5) if p == 3 else (p,)
        v = old_new.get((sid, judge))
        if v is not None and split(v)[0] in pres and split(v)[1] not in used[split(v)[0]] and v not in void.values():
            used[split(v)[0]].add(split(v)[1])
            return v
        for q in pres:
            j = next((j for j in range(1000) if j not in used[q] and (j if judge < 1000 else q * 1000 + j) not in taken), None)
            if j is not None:
                used[q].add(j)
                return j if judge < 1000 else q * 1000 + j
        raise SystemExit('前缀 %s 的空判定用完了' % (pres,))

    # 动作包（Data3）
    key = open(os.path.join(RR, 'data', 'menu', 'data3_key.pem'), encoding='ascii').read()
    anib = erlib.Bnd4(erlib.dcx_decompress(erlib.GameArchive(os.path.join(GAME, 'Data3.bhd'), key).read('/chr/c0000.anibnd.dcx')))
    # 文字：战技名（item），武器类型名（menu）
    key0 = open(os.path.join(RR, 'data', 'menu', 'data0_key.pem'), encoding='ascii').read()
    arc0 = erlib.GameArchive(os.path.join(GAME, 'Data0.bhd'), key0)
    txt = {}
    for lang, code in (('zh', 'zhocn'), ('en', 'engus')):
        for mb in ('item_dlc02', 'menu_dlc02'):
            b = erlib.Bnd4(erlib.dcx_decompress(arc0.read('/msg/%s/%s.msgbnd.dcx' % (code, mb))))
            for n in b.entries:
                base = n.replace('.fmg', '').split('_dlc')[0]
                if base in ('ArtsName', 'GR_MenuText', 'GemName'):
                    d = txt.setdefault((lang, base), {})
                    d.update((i, t) for i, t in erlib.read_fmg_full(b.get(n))[1] if t)

    def resolve(p, var, jj):
        """行为变体 var 上判定 (p, jj) 找到的行：(层, 行号) 或 None"""
        cls = var // 100 * 100
        for lv, v in (('本体', var), ('大类', cls), ('共享', 0)):
            if (lv == '本体' and var == cls) or (lv == '大类' and cls == 0):
                continue
            i = p * P + v * 1000 + jj
            if i in BH:
                return lv, i
        return None
    out = {'_说明': __doc__.split('\n')[0], 'gem_first': GEM_FIRST, 'void': {str(p): v for p, v in sorted(void.items())}, 'skills': [],
           # 开放分组（原版战灰也照它放开，用户 2026-11-04「原版也直接放开」，rr/skillgems.py open_vanilla）：武器类型位 + 原版那条文字
           'open': {g: dict(text=t, bits=b, zh=txt[('zh', 'GR_MenuText')][t], en=txt[('en', 'GR_MenuText')][t]) for g, (t, b) in OPEN.items()},
           # 武器类型位 → 类型名（拼「能在所有的近战武器、手杖类武器使用」这种）
           'type_names': {str(MOUNT_BIT[t]): [txt[('zh', 'GR_MenuText')][n], txt[('en', 'GR_MenuText')][n]] for t, n in sorted(TYPE_TEXT.items())
                          if t in MOUNT_BIT}}
    uniq = sorted(s for s in owners if s not in gem_arts and s in SA)
    order = GEMS + [s for s in uniq if s not in GEMS]
    totals, skipped, gems = collections.Counter(), [], []
    for sid in order:
        art = SA[sid]['swordArtsTypeNew']
        name = 'a%d.tae' % (600 + art)
        if name not in anib.entries:
            if sid in GEMS:
                raise SystemExit('%d：动作包里没有 %s' % (sid, name))
            skipped.append('%d（没有 %s）' % (sid, name))
            continue
        if len(art_users[art]) > 1:
            if sid in GEMS:
                raise SystemExit('%d：动作 %s 还有别的战技在用 %s' % (sid, name, sorted(art_users[art])))
            skipped.append('%d（动作和 %s 共用）' % (sid, sorted(art_users[art] - {sid})))
            continue
        js = tae.judges(anib.get(name))
        natives = owners[sid]
        types = sorted({W[w]['wepType'] for w in natives})
        vars_ = list(dict.fromkeys(W[w]['behaviorVariationId'] for w in natives))
        peers = {W[w]['behaviorVariationId'] for w in W if W[w]['wepType'] in types}       # 同类武器的变体
        judges, rows, notes, aoe = {}, {}, collections.Counter(), []
        for j in sorted({j for j, _ in js if j >= 0}):
            p, jj = split(j)
            hit = next((h for h in (resolve(p, v, jj) for v in vars_) if h), None)
            if hit is None:
                if p == 3:
                    judges[str(j)] = void_of(p)
                    notes['空号'] += 1
                else:
                    notes['找不到'] += 1
                continue
            lv, src = hit
            if p == 1:
                # 普攻前缀：只有原武器自己有（大类、共享都没有）的换号
                cls = vars_[0] // 100 * 100
                if lv != '本体' or p * P + cls * 1000 + jj in BH or p * P + jj in BH:
                    notes['普攻照旧'] += 1
                    continue
            elif lv == '共享' and (p == 3 or not any(resolve(p, v, jj)[0] != '共享' for v in peers if resolve(p, v, jj))):
                notes['共享照旧'] += 1
                aoe.append(src)
                continue
            new = fresh(sid, j)
            judges[str(j)] = new
            rows[str(src)] = split(new)[0] * P + split(new)[1]
            aoe.append(src)
            notes['换号'] += 1
        n_ev = sum(1 for j, _ in js if str(j) in judges)
        zh = txt[('zh', 'ArtsName')].get(SA[sid]['textId'], '')
        en = txt[('en', 'ArtsName')].get(SA[sid]['textId'], '')
        rec = dict(sid=sid, zh=zh, en=en, art=art, tae=name, weapons=natives, types=types, judges=judges, events=n_ev, rows=rows, free=True)
        if zh and sid not in GEM_SKIP:
            gems.append(sid)
            tn = {lang: [txt[(lang, 'GR_MenuText')][TYPE_TEXT[t]] for t in types] for lang in ('zh', 'en')}
            group = 'shield' if set(types) <= SHIELD_TYPES else 'bow' if set(types) <= BOW_TYPES else \
                None if set(types) & OWN_TYPES else 'melee'
            if group:
                mount_text, bits = OPEN[group]
                usable = {lang: txt[(lang, 'GR_MenuText')][mount_text] for lang in ('zh', 'en')}
            else:
                mount_text, bits = MOUNT_TEXT.get(types[0], -1) if len(types) == 1 else -1, [MOUNT_BIT[t] for t in types]
                usable = {'zh': '能在%s类武器使用' % '、'.join(tn['zh']),
                          'en': 'Usable on %s' % ' and '.join(t.lower() + ('es' if t.lower().endswith(('ch', 's')) else 's') for t in tn['en'])}
            # GemCaption 最后一段照原版：第一行加句号，括号里的那行另起；英文是一句
            lines = usable['zh'].split('\n')
            rec.update(group=group or 'own', mount_bits=bits, mount_text=mount_text, type_zh=tn['zh'], type_en=tn['en'],
                       usable_zh=lines[0] + '。' + ''.join('\n' + l for l in lines[1:]), usable_en=' '.join(usable['en'].split('\n')) + '.',
                       icon=WP[natives[0]]['iconId'], gem=None)
        else:
            rec.update(gem=None)
        rec.update(aoe_behaviors=sorted(set(aoe)) if sid in AOE else [],
                   # 动作里直接放的特效（范围放大时换成放大的副本，用户 2026-11-03「全部都做」）：编号 < 1000 的是通用的发动闪光，不算
                   tae_fx=sorted({v for v, _ in tae.effects(anib.get(name)) if v >= 1000}) if sid in AOE else [])
        out['skills'].append(rec)
        totals.update(notes)
        totals['事件'] += n_ev
    # 战灰编号照 gems 的顺序（最先那 33 个编号不变）。名字和原版战灰 / 别的专属战技撞了的，照原版「战灰：箭步（上砍）」的写法在后面加原武器类型
    recs = {r['sid']: r for r in out['skills']}
    taken_names = {lang: collections.Counter([t.split('：', 1)[-1].split(': ', 1)[-1] for t in txt[(lang, 'GemName')].values()] +
                                             [recs[s][lang] for s in gems]) for lang in ('zh', 'en')}
    for k, sid in enumerate(gems):
        r = recs[sid]
        r['gem'] = GEM_FIRST + k
        dup = any(taken_names[lang][r[lang]] > 1 for lang in ('zh', 'en'))
        r['suffix_zh'] = '（%s）' % '、'.join(r['type_zh']) if dup else ''
        r['suffix_en'] = ' (%s)' % '/'.join(r['type_en']) if dup else ''
    full = collections.Counter(recs[s]['zh'] + recs[s]['suffix_zh'] for s in gems)
    if any(n > 1 for n in full.values()):
        raise SystemExit('加了武器类型还是同名：%s' % [k for k, n in full.items() if n > 1])
    open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    print('战技 %d 个（战灰 %d：%s）；%s；不换：%s' % (len(out['skills']), len(gems), dict(collections.Counter(recs[s]['group'] for s in gems)),
                                              dict(totals), '、'.join(skipped)))
    print('加了武器类型的：%s' % '、'.join(recs[s]['zh'] + recs[s]['suffix_zh'] for s in gems if recs[s]['suffix_zh']))
    print('只能装在原类型的：%s' % '、'.join('%s（%s）' % (recs[s]['zh'], '、'.join(recs[s]['type_zh'])) for s in gems if recs[s]['group'] == 'own'))
    print('空号 %s；写好 %s' % (out['void'], OUT))


if __name__ == '__main__':
    main()
