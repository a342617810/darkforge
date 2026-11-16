# -*- coding: utf-8 -*-
"""各大类武器的出招速度（用户 2026-11-04「顺便记一下这个每秒刀数 用于数值模型估计使用」）→ attack_rate.json。
数据全是原版的：游戏目录 Data3 的玩家动作包 chr\\c0000.anibnd.dcx（TAE）+ 游戏目录的 regulation.bin（EquipParamWeapon 的武器类型、动作类别）。
  - 一次出招的时长 = 从动作开始到最早能出下一招（TAE 跳转表 115 / 116 / 4 最早开始的时间；115 用日志核对过：连击时下一刀就在那一刻切进来）。
    是「一直按着出招、每招都尽早接」的上限，实际打比这慢（等时机、走位、收招）；
  - 轻击连击：单手 0300x0 / 双手 0320x0 一串（有几刀算几刀，取平均）；
  - 点按重击：起手动作（0305x0 / 0325x0）挂上蓄力效果 100280 后就能松手 → 这一小段 + 出招动作（0305x5 / 0325x5）到下一招；
  - 满蓄力重击：起手动作里蓄力效果 100280 从开始到结束是蓄力段，松手后到下一招是出招段；
  - 每招几下：攻击判定（TAE 类型 1，没有就用子弹类型 2）按时间段合并后的段数（双头剑轻击一刀两下这种；同一时间的几个判定框算一下）；
  - 相杀覆盖率：相杀窗口（判定开始前 PRE 秒 ~ 判定结束后 POST 秒，同 extract_affixes.py 的 dr_clash）落在出招时长里的比例（满蓄力只算松手后）；
  - 第 1、2 下重击平均；每类 = 原版这类武器（本体，没质变）各自的动作段（wepmotionCategory，TAE 文件 aXX.tae）平均。
自己一个事件都没有的动画（mini 头「导入别的动画」）顺着导入的找（同 dev\\item_system\\build_hit_windows.py）。
用法：python -X utf8 attack_rate.py（只读游戏文件，几秒）。游戏更新改了动作要重跑"""
import json
import os
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402
import paramdef_min as pdm  # noqa: E402

GAME = os.path.dirname(PALY)
erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), GAME]
OUT = os.path.join(HERE, 'attack_rate.json')
KEY = os.path.join(RR, 'data', 'menu', 'data3_key.pem')
PRE, POST = 0.2, 0.15                   # 相杀窗口（extract_affixes.py dr_clash 的 hit）
CHAIN_JT = (115, 116, 4)                # 能出下一招的跳转表
CHARGE_SP = 100280                      # 重击蓄力中的效果（TAE 类型 67 挂的）
NAMES = {1: '短剑', 3: '直剑', 5: '大剑', 7: '特大剑', 9: '曲剑', 11: '大曲剑', 13: '刀', 14: '双头剑', 15: '刺剑', 16: '重刺剑',
         17: '斧', 19: '大斧', 21: '槌', 23: '大槌', 24: '连枷', 25: '矛', 28: '大矛', 29: '戟', 31: '镰刀', 35: '拳头', 37: '钩爪',
         39: '鞭子', 41: '特大武器', 87: '火把', 88: '格斗术', 89: '调香瓶', 90: '穿刺盾', 91: '投掷刃', 92: '反手剑', 93: '轻型大剑',
         94: '大太刀', 95: '兽爪', 65: '小盾', 67: '中盾', 69: '大盾'}


def read_tae(b, sec, out):
    """普通攻击编号段（030000~039999）每个动画：(事件 [(类型, 开始, 结束, 第一个参数)], 事件数, 导入的动画)"""
    q = lambda o: struct.unpack_from('<q', b, o)[0]
    i32 = lambda o: struct.unpack_from('<i', b, o)[0]
    f32 = lambda o: struct.unpack_from('<f', b, o)[0]
    n_anim, anims_off = i32(0x54), q(0x58)
    for k in range(n_anim):
        aid, aoff = q(anims_off + k * 16), q(anims_off + k * 16 + 8)
        if not 30000 <= aid <= 39999:
            continue
        ev_off, n_ev = q(aoff), i32(aoff + 32)
        mini = q(aoff + 24)
        imp = i32(mini + 0x18) if i32(mini) == 1 else None
        evs = []
        for j in range(n_ev):
            h = ev_off + j * 24
            dat = q(h + 16)
            typ = i32(dat)
            if typ in (0, 1, 2, 67):
                evs.append((typ, f32(q(h)), f32(q(h + 8)), i32(q(dat + 8))))
        out[sec * 1000000 + aid] = (evs, n_ev, imp)


class Anims:
    def __init__(self):
        arc = erlib.GameArchive(os.path.join(GAME, 'Data3.bhd'), open(KEY, encoding='ascii').read())
        bnd = erlib.Bnd4(erlib.dcx_decompress(arc.read('/chr/c0000.anibnd.dcx')))
        self.ev = {}
        for e in bnd.entries:
            n = e.replace('\\', '/').split('/')[-1]
            if n.startswith('a') and n.endswith('.tae') and n[1:-4].isdigit():
                read_tae(bnd.get(e), int(n[1:-4]), self.ev)

    def events(self, a, depth=0):
        v = self.ev.get(a)
        if v is None or depth > 8:
            return None
        evs, n_ev, imp = v
        return self.events(imp, depth + 1) if n_ev == 0 and imp else evs

    def hits(self, a):
        """判定时间段（合并重叠的）：[(开始, 结束)]；没有攻击行为就用子弹行为"""
        ev = self.events(a) or []
        for t in (1, 2):
            spans = sorted((t0, t1) for typ, t0, t1, _ in ev if typ == t and t1 > t0)
            if spans:
                merged = [list(spans[0])]
                for t0, t1 in spans[1:]:
                    if t0 <= merged[-1][1] + 1e-4:
                        merged[-1][1] = max(merged[-1][1], t1)
                    else:
                        merged.append([t0, t1])
                return [tuple(x) for x in merged]
        return []

    def chain(self, a, after=0.0):
        t = [t0 for typ, t0, _, p in self.events(a) or [] if typ == 0 and p in CHAIN_JT and t0 > after + 1e-4]
        return min(t) if t else None

    def charge(self, a):
        c = [(t0, t1) for typ, t0, t1, p in self.events(a) or [] if typ == 67 and p == CHARGE_SP]
        return c[0] if c else None


def overlap(w, lo, hi):
    return max(0.0, min(w[1], hi) - max(w[0], lo))


def window(h):
    return (max(0.0, h[0][0] - PRE), h[-1][1] + POST) if h else None


def light(A, sec, base):
    """一串轻击：[(时长, 几下, 相杀覆盖秒数)]"""
    out = []
    for k in range(10):
        a = sec * 1000000 + base + 10 * k
        h, c = A.hits(a), A.chain(a)
        if not h or c is None:
            break
        out.append((c, len([x for x in h if x[0] < c]), overlap(window(h), 0.0, c)))
    return out


def tap(A, sec, base):
    out = []
    for k in (0, 10):
        s, e = sec * 1000000 + base + k, sec * 1000000 + base + k + 5
        ch, h, c = A.charge(s), A.hits(e), A.chain(e)
        if not h or c is None:
            continue
        lead = ch[0] if ch else 0.0
        out.append((lead + c, len([x for x in h if x[0] < c]), overlap(window(h), 0.0, c)))
    return out


def charged(A, sec, base):
    """[(蓄力秒数, 松手后到下一招秒数, 几下, 相杀覆盖秒数)]"""
    out = []
    for k in (0, 10):
        s = sec * 1000000 + base + k
        ch, h = A.charge(s), A.hits(s)
        if ch is None or not h:
            continue
        c = A.chain(s, ch[1])
        if c is None:
            continue
        after = [x for x in h if ch[1] - 1e-4 <= x[0] < c]
        out.append((ch[1] - ch[0], c - ch[1], len(after), overlap(window(h), ch[1], c)))
    return out


def summarize(per_weapon, kind):
    """几把武器的样本 → 平均（每把武器先自己平均，再在武器间平均）"""
    rows = [x for x in per_weapon if x]
    if not rows:
        return None
    mean = lambda xs: sum(xs) / len(xs)
    if kind == 'charged':
        hold = mean([mean([s[0] for s in x]) for x in rows])
        after = mean([mean([s[1] for s in x]) for x in rows])
        hits = mean([mean([s[2] for s in x]) for x in rows])
        clash = mean([sum(s[3] for s in x) / sum(s[1] for s in x) for x in rows])
        return {'蓄力秒': round(hold, 3), '松手后秒': round(after, 3), '每招秒': round(hold + after, 3),
                '每秒招数': round(1 / (hold + after), 3), '每招几下': round(hits, 2), '每秒几下': round(hits / (hold + after), 3),
                '相杀覆盖': round(clash, 3)}
    sec = mean([mean([s[0] for s in x]) for x in rows])
    hits = mean([mean([s[1] for s in x]) for x in rows])
    clash = mean([sum(s[2] for s in x) / sum(s[0] for s in x) for x in rows])
    d = {'每招秒': round(sec, 3), '每秒招数': round(1 / sec, 3), '每招几下': round(hits, 2), '每秒几下': round(hits / sec, 3), '相杀覆盖': round(clash, 3)}
    if kind == 'light':
        d['连击刀数'] = round(mean([len(x) for x in rows]), 1)
    return d


def main():
    A = Anims()
    bnd = erlib.Bnd4(erlib.read_regulation(os.path.join(GAME, 'regulation.bin')))
    P = erlib.Param(bnd.get('EquipParamWeapon.param'))
    L = pdm.layout(pdm.load(os.path.join(RR, 'data', 'EquipParamWeapon.xml')))[0]
    weps = defaultdict(list)
    for wid, row in P.rows.items():
        if wid % 10000 or wid < 1000000:
            continue
        u = pdm.unpack(L, bytes(row))
        if u['wepType'] in NAMES:
            weps[u['wepType']].append(u['wepmotionCategory'])
    types = {}
    for t, zh in NAMES.items():
        secs = weps.get(t)
        if not secs:
            continue
        types[str(t)] = {
            '名字': zh, '原版武器': len(secs), '动作段': sorted(set(secs)),
            '单手轻击': summarize([light(A, s, 30000) for s in secs], 'light'),
            '双手轻击': summarize([light(A, s, 32000) for s in secs], 'light'),
            '单手点按重击': summarize([tap(A, s, 30500) for s in secs], 'tap'),
            '双手点按重击': summarize([tap(A, s, 32500) for s in secs], 'tap'),
            '单手满蓄力': summarize([charged(A, s, 30500) for s in secs], 'charged'),
            '双手满蓄力': summarize([charged(A, s, 32500) for s in secs], 'charged'),
        }
    doc = {
        '_说明': '各大类武器的出招速度（attack_rate.py 从原版 TAE 生成，说明见该文件开头和 说明.md）。键 = EquipParamWeapon 的 wepType。'
                 '每招秒 = 从动作开始到最早能出下一招（一直尽早接招的上限，实际更慢）；每招几下 = 攻击判定按时间合并后的段数（对单个敌人最多打中几下）；'
                 '满蓄力的每招秒含蓄力；相杀覆盖 = 相杀窗口（判定前 %g 秒 ~ 判定后 %g 秒）占出招时长的比例（满蓄力只算松手后）' % (PRE, POST),
        '相杀窗口': [PRE, POST],
        'types': types,
    }
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print('写了', OUT)
    for t, d in types.items():
        l1, th, fc = d['单手轻击'] or {}, d['单手点按重击'] or {}, d['单手满蓄力'] or {}
        print('%-5s 轻击 %.2f 招/秒（%.2f 下/秒） 点按重击 %.2f 招/秒 满蓄力 %.2f 招/秒（蓄力 %.2f 秒）' % (
            d['名字'], l1.get('每秒招数', 0), l1.get('每秒几下', 0), th.get('每秒招数', 0), fc.get('每秒招数', 0), fc.get('蓄力秒', 0)))


if __name__ == '__main__':
    main()
