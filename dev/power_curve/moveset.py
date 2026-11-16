# -*- coding: utf-8 -*-
"""招式表：从玩家动作包（Data3 的 c0000.anibnd，TAE）和 regulation 读每一招的时长、判定时刻、动作值、攻击类别（用户 2026-11-05「现在应该方便读取动作文件算输出频率了」）。

攻击行为（TAE 类型 1）/ 子弹行为（类型 2）的判定号 = 前缀 × 1000 + 判定；行为编号 = max(前缀, 1) 亿位 + 行为变体 × 1000 + 判定（BehaviorParam_PC），
行为 refType 0 → AtkParam_Pc、1 → Bullet（Bullet.atkId_Bullet → AtkParam_Pc）。AtkParam_Pc：atk*Correction = 动作值 %（乘武器攻击力），atk* = 固定攻击力，subCategory1~4 = 攻击类别
（100 蓄力、102 跳跃、103 防御反击、104 连段最后一下、106 战技、121 翻滚 / 后撤步后、122 冲刺）。
时长 = 动作开始到最早能出下一招（跳转表 115 / 116 / 4，同 attack_rate.py），是一直尽早接招的上限。
动作段：武器 a<wepmotionCategory>；施法 a<400 + Magic.refType>（c0000.hks IsMagicAnimExists）；战技 a<600 + 战技类型>。"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
RR = os.path.join(PALY, 'launcher', 'reroll')
GAME = os.path.dirname(PALY)
sys.path.insert(0, RR)
import erlib  # noqa: E402
import paramdef_min as pdm  # noqa: E402

erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), GAME]
KEY = os.path.join(RR, 'data', 'menu', 'data3_key.pem')
CHAIN_JT = (115, 116, 4)
CHARGE_SP = 100280
ATK_C = ('atkPhysCorrection', 'atkMagCorrection', 'atkFireCorrection', 'atkThunCorrection', 'atkDarkCorrection')
ATK_F = ('atkPhys', 'atkMag', 'atkFire', 'atkThun', 'atkDark')
SUBS = ('subCategory1', 'subCategory2', 'subCategory3', 'subCategory4')


def _lay(x):
    return pdm.layout(pdm.load(os.path.join(RR, 'data', x + '.xml')))[0]


class Hit:
    """一个判定：t 判定开始（秒）；motion 五种动作值（%）；flat 五种固定攻击力；subs 攻击类别；bullet 是子弹"""
    __slots__ = ('t', 'motion', 'flat', 'subs', 'bullet', 'atk')

    def __init__(self, t, motion, flat, subs, bullet, atk):
        self.t, self.motion, self.flat, self.subs, self.bullet, self.atk = t, motion, flat, subs, bullet, atk

    def __repr__(self):
        return 'Hit(%.2f m=%s f=%s sub=%s)' % (self.t, self.motion[0], sum(self.flat), self.subs)


class Move:
    """一招：dur 到下一招的秒数；hits 判定；charge 蓄力段秒数（含在 dur 里）；tags 这招的种类（light / heavy / charged / jump / roll / dash / counter / skill / cast / shot）"""
    __slots__ = ('name', 'dur', 'hits', 'charge', 'tags', 'fp')

    def __init__(self, name, dur, hits, tags=(), charge=0.0, fp=0):
        self.name, self.dur, self.hits, self.tags, self.charge, self.fp = name, dur, hits, set(tags), charge, fp

    def __repr__(self):
        return '%s %.2fs %s' % (self.name, self.dur, self.hits)


class Moves:
    def __init__(self, reg_path=None):
        arc = erlib.GameArchive(os.path.join(GAME, 'Data3.bhd'), open(KEY, encoding='ascii').read())
        self.bnd = erlib.Bnd4(erlib.dcx_decompress(arc.read('/chr/c0000.anibnd.dcx')))
        self.names = {e.replace('\\', '/').split('/')[-1]: e for e in self.bnd.entries}
        self._sec = {}
        reg = erlib.Bnd4(erlib.read_regulation(reg_path or os.path.join(GAME, 'regulation.bin')))
        self.P = {n: erlib.Param(reg.get(n + '.param')) for n in ('EquipParamWeapon', 'BehaviorParam_PC', 'AtkParam_Pc', 'Bullet', 'Magic', 'SwordArtsParam', 'EquipParamGem')}
        self.Lw, self.Lb, self.La, self.Lbu, self.Lm, self.Lsa = _lay('EquipParamWeapon'), _lay('BehaviorParam'), _lay('AtkParam'), _lay('BulletParam'), _lay('MagicParam'), _lay('SwordArtsParam')
        self._u = {}

    def u(self, pname, lay, i):
        k = (pname, i)
        if k not in self._u:
            r = self.P[pname].rows.get(i)
            self._u[k] = pdm.unpack(lay, bytes(r)) if r is not None else None
        return self._u[k]

    def section(self, sec):
        """{动画: (事件 [(类型, 开始, 结束, 参数偏移)], 事件数, 导入的动画), 'b': 文件}"""
        if sec in self._sec:
            return self._sec[sec]
        n = next((x for x in ('a%02d.tae' % sec, 'a%03d.tae' % sec, 'a%d.tae' % sec) if x in self.names), None)
        out = {}
        if n:
            b = self.bnd.get(self.names[n])
            q = lambda o: struct.unpack_from('<q', b, o)[0]
            i32 = lambda o: struct.unpack_from('<i', b, o)[0]
            f32 = lambda o: struct.unpack_from('<f', b, o)[0]
            for k in range(i32(0x54)):
                base = q(0x58) + k * 16
                aid, aoff = q(base), q(base + 8)
                ev_off, n_ev = q(aoff), i32(aoff + 32)
                mini = q(aoff + 24)
                imp = i32(mini + 0x18) if i32(mini) == 1 else None
                evs = []
                for j in range(n_ev):
                    h = ev_off + j * 24
                    dat = q(h + 16)
                    typ = i32(dat)
                    if typ in (0, 1, 2, 67):
                        par = q(dat + 8)
                        evs.append((typ, f32(q(h)), f32(q(h + 8)), i32(par), i32(par + 8)))
                out[aid] = (evs, n_ev, imp)
        self._sec[sec] = out
        return out

    def events(self, sec, aid, depth=0):
        v = self.section(sec).get(aid)
        if v is None or depth > 8:
            return None
        evs, n_ev, imp = v
        if n_ev == 0 and imp:
            return self.events(imp // 1000000, imp % 1000000, depth + 1)
        return evs

    def atk(self, judge, var):
        """判定号 + 行为变体 → (AtkParam_Pc 行, 子弹?)；找不到 None"""
        pre, ju = judge // 1000, judge % 1000
        for bid in ((pre or 1) * 100000000 + var * 1000 + ju, (pre or 1) * 100000000 + ju):
            ub = self.u('BehaviorParam_PC', self.Lb, bid)
            if ub is None:
                continue
            if ub['refType'] == 0:
                return ub['refId'], False
            if ub['refType'] == 1:
                bu = self.u('Bullet', self.Lbu, ub['refId'])
                if bu and bu.get('atkId_Bullet', 0) > 0:
                    return bu['atkId_Bullet'], True
            return None
        return None

    def hit_from_atk(self, t, atk_id, bullet):
        a = self.u('AtkParam_Pc', self.La, atk_id)
        if a is None:
            return None
        h = Hit(t, [float(a[f]) for f in ATK_C], [float(a[f]) for f in ATK_F], {int(a[s]) for s in SUBS} - {0}, bullet, atk_id)
        return h if sum(h.motion) + sum(h.flat) > 0 else None

    def hits(self, sec, aid, var, after=None):
        """这个动画的判定（同一时间段的算一下；after = 只要这个时间之后的）"""
        out, seen = [], set()
        for typ, t0, t1, _p0, judge in self.events(sec, aid) or []:
            if typ not in (1, 2) or (after is not None and t0 < after - 1e-4):
                continue
            key = (round(t0, 2), judge)
            if key in seen:
                continue
            seen.add(key)
            r = self.atk(judge, var)
            if r is None:
                continue
            h = self.hit_from_atk(t0, r[0], r[1])
            if h is not None:
                out.append(h)
        return sorted(out, key=lambda x: x.t)

    def chain(self, sec, aid, after=0.0):
        t = [t0 for typ, t0, _t1, p0, _ in self.events(sec, aid) or [] if typ == 0 and p0 in CHAIN_JT and t0 > after + 1e-4]
        return min(t) if t else None

    def charge(self, sec, aid):
        c = [(t0, t1) for typ, t0, t1, p0, _ in self.events(sec, aid) or [] if typ == 67 and p0 == CHARGE_SP]
        return c[0] if c else None

    def weapon(self, wid):
        u = self.u('EquipParamWeapon', self.Lw, wid)
        return u['wepmotionCategory'], u['behaviorVariationId']

    # ---------------------------------------------------------- 武器的招式
    def light_chain(self, sec, var, two=False):
        base, out = (32000 if two else 30000), []
        for k in range(10):
            a = base + 10 * k
            h, c = self.hits(sec, a, var), self.chain(sec, a)
            if not h or c is None:
                break
            out.append(Move('轻击%d' % (k + 1), c, [x for x in h if x.t < c], ('light', 'grip2' if two else 'grip1')))
        return out

    def heavy_tap(self, sec, var, two=False):
        base, out = (32500 if two else 30500), []
        for k in (0, 10):
            s, e = base + k, base + k + 5
            ch, h, c = self.charge(sec, s), self.hits(sec, e, var), self.chain(sec, e)
            if not h or c is None:
                continue
            lead = ch[0] if ch else 0.0
            for x in h:
                x.t += lead
            out.append(Move('点按重击%d' % (k // 10 + 1), lead + c, [x for x in h if x.t < lead + c], ('heavy', 'grip2' if two else 'grip1')))
        return out

    def heavy_charged(self, sec, var, two=False):
        base, out = (32500 if two else 30500), []
        for k in (0, 10):
            s = base + k
            ch, h = self.charge(sec, s), self.hits(sec, s, var)
            if ch is None or not h:
                continue
            c = self.chain(sec, s, ch[1])
            if c is None:
                continue
            out.append(Move('满蓄力重击%d' % (k // 10 + 1), c, [x for x in h if ch[1] - 1e-4 <= x.t < c], ('heavy', 'charged', 'grip2' if two else 'grip1'), charge=ch[1] - ch[0]))
        return out

    def _single(self, sec, var, aids, name, tags, lead=0.0, two=False):
        """跳跃 / 翻滚 / 冲刺 / 防御反击：lead = 出招前要多花的秒数（起跳、翻滚本身）"""
        base = 2000 if two else 0
        for a in aids:
            a += base
            h, c = self.hits(sec, a, var), self.chain(sec, a)
            if h and c is not None:
                hs = [x for x in h if x.t < c]
                for x in hs:
                    x.t += lead
                return Move(name, lead + c, hs, set(tags) | {'grip2' if two else 'grip1'})
        return None

    def moves(self, wid, two=False):
        """这把武器的招式：{种类: [Move]}"""
        sec, var = self.weapon(wid)
        d = {'light': self.light_chain(sec, var, two), 'tap': self.heavy_tap(sec, var, two), 'charged': self.heavy_charged(sec, var, two)}
        d['jump_light'] = self._single(sec, var, (31070,), '跳跃轻击', ('jump', 'jatk'), lead=0.75, two=two)
        d['jump_heavy'] = self._single(sec, var, (31270,), '跳跃重击', ('jump', 'jatk'), lead=0.75, two=two)
        d['roll'] = self._single(sec, var, (30300,), '翻滚攻击', ('roll',), lead=0.55, two=two)
        d['dash'] = self._single(sec, var, (30200,), '冲刺攻击', ('dash',), two=two)
        d['counter'] = self._single(sec, var, (30700,), '防御反击', ('counter',), two=two)
        return d

    # ---------------------------------------------------------- 法术
    def bullet_hit(self, bid, t):
        """子弹 → 第一个有伤害的攻击行（顺着命中后 / 持续生成的子弹找）"""
        seen, todo = set(), [bid]
        while todo:
            b = todo.pop(0)
            if b in seen or b <= 0:
                continue
            seen.add(b)
            bu = self.u('Bullet', self.Lbu, b)
            if bu is None:
                continue
            if bu.get('atkId_Bullet', 0) > 0:
                h = self.hit_from_atk(t, bu['atkId_Bullet'], True)
                if h is not None:
                    return h, bu
            todo += [bu.get(k, -1) for k in ('HitBulletID', 'intervalCreateBulletId') if bu.get(k, -1) and bu.get(k, -1) > 0]
        return None, None

    def spell(self, mid):
        """(Move, mp, 需求 (智, 信, 感)) 或 None：动作段 a<400 + refType>，45010（右手起手）/ 45020（接着放）的跳转时间；子弹 Magic.refId1 的攻击行，一发按打中一下"""
        m = self.u('Magic', self.Lm, mid)
        if m is None or m['refCategory1'] != 1 or m['refId1'] <= 0:
            return None
        sec = 400 + m['refType']
        durs = [c for c in (self.chain(sec, a) for a in (45010, 45020)) if c]
        if not durs:
            return None
        hit, bu = self.bullet_hit(m['refId1'], 0.3)
        if hit is None:
            return None
        return Move('法术%d' % mid, sum(durs) / len(durs), [hit], ('cast',), fp=m['mp']), m['mp'], (m['requirementIntellect'], m['requirementFaith'], m['requirementLuck'])

    # ---------------------------------------------------------- 战技
    def skill(self, gem_or_art, var):
        """战技类型 art 的出招：动作段 a<600 + art>，30000~39999 / 40000+ 里判定最多的那段第一招。[(动画, Move)]"""
        sec = 600 + gem_or_art
        out = []
        for a in sorted(self.section(sec)):
            h = self.hits(sec, a, var)
            c = self.chain(sec, a)
            if h and c:
                out.append((a, Move('战技%d' % a, c, [x for x in h if x.t < c], ('skill',))))
        return out


if __name__ == '__main__':
    M = Moves()
    for wid, nm in ((2000000, '长剑'), (1000000, '短剑'), (3000000, '大剑'), (4000000, '特大剑'), (9000000, '刀'), (12000000, '大槌')):
        if wid not in M.P['EquipParamWeapon'].rows:
            continue
        d = M.moves(wid)
        d2 = M.moves(wid, two=True)
        def rate(ms):
            ms = [m for m in (ms if isinstance(ms, list) else [ms]) if m]
            t = sum(m.dur for m in ms)
            return '%.2f 秒/招 %3.0f%%/秒' % (t / max(1, len(ms)), sum(sum(h.motion[:1]) for m in ms for h in m.hits) / max(t, 1e-6)) if ms else '-'
        print(nm, '轻击', rate(d['light']), '| 双手轻击', rate(d2['light']), '| 点按', rate(d['tap']), '| 蓄力', rate(d['charged']), '| 双手蓄力', rate(d2['charged']), '| 跳重', rate(d['jump_heavy']), '| 翻滚', rate(d['roll']))
    for mid in (4000, 4100, 6400, 6420):
        print(mid, M.spell(mid))
    for art in (10, 100, 230):
        print(art, [(a, round(m.dur, 2), len(m.hits), m.hits[0].motion[0], m.hits[0].subs) for a, m in M.skill(art, 200)][:4])
