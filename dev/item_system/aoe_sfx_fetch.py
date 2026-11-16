# -*- coding: utf-8 -*-
"""范围战灰放大：把 aoe_skills.json 里各战灰子弹用的原版特效（和它们里面引用的子特效）从本机 Data0 的公共特效包取到 sfx\\vanilla\\（只读），
再给每个（战灰, 原版特效）分配我们的编号（990100 起），写 sfx\\aoe_scale.json 给 sfx\\aoe_scale.js 用、aoe_skills.json 的 fxr 给重随用。
子特效：FXR 里的「引用别的特效」节点（类型 2001，ER 的 FXR 里以编号出现），按 fxrlab 读出来的列表补（aoe_scale.js 会报缺哪个）。
用法：python aoe_sfx_fetch.py [额外的原版特效编号…]"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402

erlib.DLL_DIRS[:] = [os.path.join(PALY, 'randomizer'), os.path.dirname(PALY)]
SFX = os.path.join(HERE, 'sfx')
VAN = os.path.join(SFX, 'vanilla')
DATA = os.path.join(RR, 'data', 'aoe_skills.json')
FIRST = 990100
PACKS = ('/sfx/sfxbnd_commoneffects.ffxbnd.dcx', '/sfx/sfxbnd_commoneffects_dlc02.ffxbnd.dcx',
         # 狩猎大蛇（大蛇狩猎矛）的特效在拉卡德的特效包 c4710 里：原版只有拉卡德那场战斗载入，别处看不见；
         # 我们的副本放在常驻的 sfxbnd_c0000，贴图都在公共特效包，只有模型 s88830 要一起拷（MODELS）
         '/sfx/sfxbnd_c4710.ffxbnd.dcx')
COMMON = PACKS[:2]
MODELS = os.path.join(SFX, 'aoe_models.json')      # 不在公共特效包里、要一起放进我们特效包的模型（make_sfx.py 读）
# 原版特效里引用的子特效（类型 2001 的节点；aoe_scale.js 遇到没列的引用会报错）：跟着父特效按同一个倍数各复制一份
CHILDREN = {440181: [440182], 449990: [440182], 440681: [440683], 440682: [440683],
            # 专属战技战灰（2026-11-03）
            450581: [450582], 451073: [451075], 451212: [451211], 451325: [451326], 451450: [451451], 523877: [523879], 451326: [440182],
            # 动作里直接放的特效（2026-11-03「全部都做」）
            220521: [220501], 450250: [201001], 450335: [523391], 450523: [620100], 450650: [450676], 450658: [450653],
            450721: [440182], 450726: [690000], 451214: [220102, 451211], 451215: [220712], 451464: [451460], 220501: [220101],
            # 信仰喷发（2026-11-04 做成战灰时一起放大）
            450402: [431]}


def main():
    d = json.load(open(DATA, encoding='utf-8'))
    want = set(int(x) for x in sys.argv[1:])
    for sk in d['skills'].values():
        want.update(sk['bullet_sfx'])
        want.update(sk.get('tae_sfx', []))           # 专属战技动作里直接放的特效（2026-11-03）
    want.update(c for cs in CHILDREN.values() for c in cs)
    os.makedirs(VAN, exist_ok=True)
    missing = [f for f in sorted(want) if not os.path.isfile(os.path.join(VAN, 'f%09d.fxr' % f))]
    models = json.load(open(MODELS, encoding='utf-8')) if os.path.isfile(MODELS) else {}
    if missing:
        key = open(os.path.join(RR, 'data', 'menu', 'data0_key.pem'), encoding='ascii').read()
        arc = erlib.GameArchive(os.path.join(os.path.dirname(PALY), 'Data0.bhd'), key)
        for pack in PACKS:
            if not missing:
                break
            try:
                bnd = erlib.Bnd4(erlib.dcx_decompress(arc.read(pack)))
            except Exception as e:
                print('读不了', pack, e)
                continue
            names = {n.replace('/', '\\').split('\\')[-1].lower(): n for n in bnd.entries}
            for f in list(missing):
                fx, rl = 'f%09d.fxr' % f, 'f%09d.ffxreslist' % f
                if fx in names:
                    open(os.path.join(VAN, fx), 'wb').write(bnd.get(names[fx]))
                    open(os.path.join(VAN, rl), 'wb').write(bnd.get(names[rl]) if rl in names else b'')
                    missing.remove(f)
                    print('取了', fx, '（%s）' % pack.split('/')[-1])
                    if pack in COMMON:
                        continue
                    # 不是公共特效包里的：资源清单里的模型（.sib → 同一个包里的 .flver）也拷出来，一起放进我们的特效包
                    res = bnd.get(names[rl]).decode('ascii', 'replace').split() if rl in names else []
                    for r in res:
                        flv = r.lower().replace('.sib', '.flver')
                        if r.lower().endswith('.sib') and flv in names and flv not in models:
                            os.makedirs(os.path.join(VAN, 'model'), exist_ok=True)
                            open(os.path.join(VAN, 'model', flv), 'wb').write(bnd.get(names[flv]))
                            models[flv] = 'model\\' + flv
                            print('   取了模型', flv)
        if missing:
            print('特效包里没有（动作事件 134 / 138 的编号不是这种特效，正常）：', missing)
    open(MODELS, 'w', encoding='utf-8', newline='\n').write(json.dumps(models, ensure_ascii=False, indent=1) + '\n')
    # 分配编号：已有的对照不变，新的往后排
    fxr = d.get('fxr', {})
    used = {v for m in fxr.values() for v in m.values()}
    nxt = max(used | {FIRST - 1}) + 1
    jobs = []
    for sid, sk in d['skills'].items():
        m = fxr.setdefault(sid, {})
        srcs = list(sk['bullet_sfx']) + [v for v in sk.get('tae_sfx', []) if v not in sk['bullet_sfx']]
        for src in srcs:
            if not os.path.isfile(os.path.join(VAN, 'f%09d.fxr' % src)):
                continue                            # 公共特效包里没有的（角色自己的特效包里的）：不做副本，照原版
            if str(src) not in m:
                m[str(src)] = nxt
                nxt += 1
            jobs.append(dict(skill=sid, zh=sk['zh'], src=src, id=m[str(src)], scale=sk['scale'], refs={}))
    # 子特效：每个父特效一份（编号接着往后排，只在我们的特效包里用，重随不用知道）
    nxt = max([j['id'] for j in jobs] + [FIRST - 1]) + 1
    for j in jobs:              # 列表边走边加：子特效自己引用的子特效也各复制一份
        for c in CHILDREN.get(j['src'], []):
            j['refs'][str(c)] = nxt
            jobs.append(dict(skill=j['skill'], zh=j['zh'] + '（子特效）', src=c, id=nxt, scale=j['scale'], refs={}))
            nxt += 1
    d['fxr'] = {k: v for k, v in fxr.items() if v}
    open(DATA, 'w', encoding='utf-8', newline='\n').write(json.dumps(d, ensure_ascii=False, indent=1) + '\n')
    open(os.path.join(SFX, 'aoe_scale.json'), 'w', encoding='utf-8', newline='\n').write(json.dumps(jobs, ensure_ascii=False, indent=1) + '\n')
    print('特效副本 %d 个：%s' % (len(jobs), ', '.join('%s %d→%d ×%.2f' % (j['zh'], j['src'], j['id'], j['scale']) for j in jobs)))


if __name__ == '__main__':
    main()
