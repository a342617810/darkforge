# -*- coding: utf-8 -*-
"""范围战灰放大到 8 米（用户 2026-11-03）的数据：哪些行为是这几个战灰的（按 Smithbox 的行名认，只在开发时跑），写到
launcher\\reroll\\data\\aoe_skills.json，重随的 rr/aoe.py 按它改参数（游戏里没有行名，重随时认不出是哪个战灰）。
  - 行为：共享的 3000JJJ 和武器大类的 3VVVJJJ（行名里是同一个战灰），不算专属武器的；
  - 用户定：等比放大（这个战灰最大那圈到 8 米，其余同一个倍数）；飞行类（幻影共击、落雷、野兽咆哮、冻霜踏地）不改；主教冲锋不改；
  - 每个战灰的子弹特效（sfxId_Bullet / Hit / Flick）列出来，make_aoe_sfx 做放大的副本（编号 990100 起，fxr 里写好）。
  - 专属战技战灰（skill_gems.py，用户 2026-11-03「范围依旧是8」「大于8的就不管了」）：行为照 skill_gems.json 的 aoe_behaviors（原武器变体下的
    原行，重随复制到共享层时带上改过的指向），会飞的子弹（初速 / 最大速度 > 0）不算最大半径也不放大（still_only），原本 8 米以上的不动。
用法：python aoe_skills.py（要 Smithbox 的行名表和本机 Data0 的 regulation；输出覆盖 aoe_skills.json 里的 skills，保留 fxr 对照）"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib, paramdef_min as pdm  # noqa: E402

erlib.DLL_DIRS[:] = [os.path.join(PALY, 'randomizer'), os.path.dirname(PALY)]
NAMES = r'C:\Users\dxphh\Downloads\Smithbox_2_2_6_2026_09_20_b\Assets\PARAM\ER\Param Row Names\English'
OUT = os.path.join(RR, 'data', 'aoe_skills.json')
GEMS = os.path.join(RR, 'data', 'skill_gems.json')
# 战技编号 → 中文名（SwordArtsParam；英文名按 Smithbox 的 SwordArtsParam 行名）
SKILLS = {507: '黄金坠落震击', 506: '坠落震击', 653: '山妖咆哮', 509: '荷莱·露的撼地', 212: '撼地', 123: '唤起风暴', 213: '黄金大地',
          508: '黑暗波动', 221: '黑焰漩涡', 209: '重力', 217: '雷击斩', 502: '风暴足', 122: '风暴袭击', 207: '熔岩火浆'}
RADIUS = 8.0
MIN_R = 0.9        # 半径不到这个的是挥武器的判定 / 定位用的小子弹，不放大
CATS = ('', 'Shared', 'Dagger', 'Straight Sword', 'Greatsword', 'Colossal Sword', 'Curved Sword', 'Curved Greatsword', 'Katana', 'Twinblade',
        'Thrusting Sword', 'Heavy Thrusting Sword', 'Axe', 'Greataxe', 'Hammer', 'Great Hammer', 'Warhammer', 'Flail', 'Spear', 'Great Spear',
        'Halberd', 'Scythe', 'Whip', 'Fist', 'Claw', 'Colossal Weapon', 'Lance', 'Torch', 'Small Shield', 'Medium Shield', 'Greatshield')


def names(p):
    js = json.load(open(os.path.join(NAMES, p + '.json'), encoding='utf-8'))['Entries']
    return {e['ID']: (e['Entries'][0] if e['Entries'] else '') for e in js}


def main():
    import vanilla as vsrc
    bnd = erlib.Bnd4(erlib.read_regulation(vsrc.path('regulation.bin')))

    def param(name, xml):
        f = next(n for n in bnd.entries if n.replace('/', '\\').split('\\')[-1] == name + '.param')
        lay, _ = pdm.layout(pdm.load(os.path.join(RR, 'data', xml + '.xml')))
        return {i: pdm.unpack(lay, r) for i, r in erlib.Param(bnd.get(f)).rows.items()}
    BH, BL, AT = param('BehaviorParam_PC', 'BehaviorParam'), param('Bullet', 'BulletParam'), param('AtkParam_Pc', 'AtkParam')
    nb, nsa = names('BehaviorParam_PC'), names('SwordArtsParam')
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    out = {'_说明': __doc__.split('\n')[0], 'radius': RADIUS, 'min_radius': MIN_R, 'skills': {}, 'fxr': old.get('fxr', {})}
    # 最大半径：有伤害的判定（倍率或固定伤害 > 0、半径 MIN_R 以上）里最大的那个；倍数 = 8 / 它（没伤害的辅助子弹也按这个倍数放大）
    EL = ('Phys', 'Mag', 'Fire', 'Thun', 'Dark')
    dmg = lambda a: any(a['atk%sCorrection' % e] for e in EL) or any(a['atk%s' % e] for e in EL)
    arad = lambda a: max(a['hit%d_Radius' % k] for k in range(16))

    def measure(behs, still_only=False):
        """(最大半径, 要放大的子弹的特效)；still_only：会飞的子弹不算、不放大（它的子子弹照样往下找）"""
        rmax, sfx = 0.0, set()
        for i in behs:
            b = BH[i]
            if b['refType'] == 0 and b['refId'] in AT:
                a = AT[b['refId']]
                if dmg(a) and arad(a) >= MIN_R:
                    rmax = max(rmax, arad(a))
            elif b['refType'] == 1:
                todo, seen = [b['refId']], set()
                while todo:
                    bb = todo.pop()
                    if bb in seen or bb not in BL:
                        continue
                    seen.add(bb)
                    r = BL[bb]
                    rr_ = max(r['hitRadius'], r['hitRadiusMax'])
                    moving = still_only and max(r['initVellocity'], r['maxVellocity']) > 0
                    if rr_ >= MIN_R and not moving:
                        sfx.update(v for v in (r['sfxId_Bullet'], r['sfxId_Hit'], r['sfxId_Flick']) if v > 0)
                        if r['atkId_Bullet'] in AT and dmg(AT[r['atkId_Bullet']]):
                            rmax = max(rmax, rr_)
                    elif moving and r['HitBulletID'] > 0 and r['sfxId_Hit'] > 0:
                        sfx.add(r['sfxId_Hit'])         # 会飞的子弹落地生成原地子弹：命中特效就是那一下爆炸的光效（火焰唾球），跟着放大
                    todo += [v for v in (r['HitBulletID'], r['intervalCreateBulletId']) if v > 0]
        return rmax, sfx

    def add(sid, zh, en, behs, rmax, sfx, **extra):
        out['skills'][str(sid)] = dict(zh=zh, en=en, behaviors=sorted(behs), max_radius=round(rmax, 3),
                                       scale=round(RADIUS / rmax, 4) if rmax else None, bullet_sfx=sorted(sfx), **extra)
        print('%s（%d）：行为 %d 条，最大半径 %.2f → ×%.3f，子弹特效 %s' % (zh, sid, len(behs), rmax, RADIUS / rmax if rmax else 0, sorted(sfx)))
    for sid, zh in SKILLS.items():
        en = nsa[sid].lower()
        behs = []
        for i, n in nb.items():
            m = re.match(r'^(.*?)\s*-?\s*\[AOW\]\s*(.+)$', n or '')
            if not m or i not in BH:
                continue
            cat = m.group(1).replace('Shared', '').replace(' Category', '').strip(' -')
            if m.group(2).strip().lower() != en or cat not in CATS:
                continue
            behs.append(i)
        rmax, sfx = measure(behs)
        add(sid, zh, nsa[sid], behs, rmax, sfx)
    # 专属战技战灰：原本就 RADIUS 以上 / 没有范围判定的不动
    for s in json.load(open(GEMS, encoding='utf-8'))['skills'] if os.path.exists(GEMS) else []:
        behs = [i for i in s['aoe_behaviors'] if i in BH]
        rmax, sfx = measure(behs, True)
        if not rmax or rmax >= RADIUS:
            print('%s（%d）：最大半径 %.2f，不放大' % (s['zh'], s['sid'], rmax))
            continue
        # 动作里直接放的特效也换成放大的副本（用户 2026-11-03「全部都做」；重随的 rr/skillgems.py 改动作包里的特效编号）
        add(s['sid'], s['zh'], s['en'], behs, rmax, sfx, still_only=True, tae_sfx=s.get('tae_fx', []))
    open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    print('写好', OUT)


if __name__ == '__main__':
    main()
