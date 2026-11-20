# -*- coding: utf-8 -*-
"""从 reg_diff.json 里去掉“版本差”（同一游戏版本的几个模组都一样的行 = 那个版本原版的值），
剩下每个模组自己的改动；逐行解出改了哪些字段，并看 VINS 有没有原样收进去。
输出 rows_<m>.txt + rows_summary.json"""
import os, sys, json, collections, glob
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van
from van import erlib
import paramdef_min as pdm

# Smithbox 的 paramdef：环境变量 SMITHBOX_DIR 指 Smithbox 解压目录，不设就找 ~\Downloads 下的 2.2.6
SB = os.path.join(os.environ.get('SMITHBOX_DIR') or os.path.expanduser(r'~\Downloads\Smithbox_2_2_6_2026_09_20_b'), 'Assets', 'PARAM', 'ER', 'Defs')
H = van.HERE
D = json.load(open(os.path.join(H, 'reg_diff.json')))
MODS = sorted(van.ROOTS)

# ---------- 版本差
groups = collections.defaultdict(list)
for m in MODS:
    groups[D[m]['ver']].append(m)
drift = {}   # ver -> set((param,row,hash))
for ver, ms in groups.items():
    cnt = collections.Counter()
    for m in ms:
        for p, v in D[m]['params'].items():
            for r, h in v.get('hash', {}).items():
                cnt[(p, r, h)] += 1
    drift[ver] = {k for k, n in cnt.items() if n >= 2}
# 1.16.1 组改过的行（不论值），给只有一个模组的旧版本（Mohg 1.13）参考
drift_rows_161 = {(p, r) for p, r, h in drift.get('11601000', set())}

# ---------- 参数定义
defs = {}
for f in glob.glob(os.path.join(SB, '*.xml')):
    try:
        t = ET.parse(f).getroot().findtext('ParamType')
    except Exception:
        continue
    if t:
        defs[t.strip()] = f
_lay = {}


def lay(ptype):
    if ptype not in _lay:
        f = defs.get(ptype)
        _lay[ptype] = pdm.layout(pdm.load(f))[0] if f else None
    return _lay[ptype]


def load_params(path):
    raw = erlib.read_regulation(path)
    b = erlib.Bnd4(raw)
    return {n[:-6]: erlib.Param(b.get(n)) for n in b.entries if n.endswith('.param')}


VP = load_params(os.path.join(van.ER, 'regulation.bin'))
VINS = load_params(os.path.join(van.VINS, 'regulation.bin'))


def fdiff(pt, a, b):
    L = lay(pt.decode())
    if L is None:
        return ['(无定义)']
    da, db = pdm.unpack(L, a) if a is not None else {}, pdm.unpack(L, b)
    out = []
    for k, v in db.items():
        if a is None:
            continue
        if da.get(k) != v:
            out.append('%s:%s→%s' % (k, _f(da.get(k)), _f(v)))
    return out


def _f(v):
    return ('%.4g' % v) if isinstance(v, float) else str(v)


KEYS = {'NpcParam': ['hp', 'getSoul', 'itemLotId_enemy', 'itemLotId_map', 'behaviorVariationId', 'nameId', 'spEffectID0', 'spEffectID1',
                     'spEffectID2', 'spEffectID3', 'teamType', 'stamina', 'superArmorDurability'],
        'NpcThinkParam': ['logicId', 'battleGoalID', 'eye_dist', 'ear_dist'],
        }

summary = {}
for m in MODS:
    ver = D[m]['ver']
    dr = drift.get(ver, set())
    MP = load_params(os.path.join(van.root(m), 'regulation.bin'))
    lines = ['# %s  (%s, regulation %s)' % (van.NAMES[m], m, ver)]
    sm = {}
    for p, v in sorted(D[m]['params'].items()):
        if 'hash' not in v:
            continue
        own = []
        for r in v['add'] + v['chg']:
            h = v['hash'][str(r)]
            if (p, str(r), h) in dr:
                continue
            if ver == '11320031' and (p, str(r)) in drift_rows_161 and r not in v['add']:
                continue      # Mohg 1.13：1.16.1 组也改过的行多半是版本差
            own.append(r)
        if not own:
            continue
        mp, vp, vi = MP[p], VP[p], VINS.get(p)
        same_vins = sum(1 for r in own if vi is not None and r in vi.rows and bytes(vi.rows[r]) == bytes(mp.rows[r]))
        sm[p] = {'add': [r for r in own if r in v['add']], 'chg': [r for r in own if r in v['chg']], 'vins_same': same_vins}
        lines.append('\n## %s  新增 %d / 修改 %d   （VINS 里一模一样的 %d 行）' % (p, len(sm[p]['add']), len(sm[p]['chg']), same_vins))
        for r in own:
            nm = mp.names.get(r, b'')
            try:
                nm = nm.decode('utf-16le' if mp.unicode_names else 'shift_jis', 'replace')
            except Exception:
                nm = ''
            vi_tag = ''
            if vi is not None and r in vi.rows:
                vi_tag = ' [VINS=同]' if bytes(vi.rows[r]) == bytes(mp.rows[r]) else ' [VINS=不同]'
            else:
                vi_tag = ' [VINS无]'
            if r in vp.rows:
                fd = fdiff(mp.param_type, bytes(vp.rows[r]), bytes(mp.rows[r]))
                lines.append('  ~%d %s%s: %s' % (r, nm, vi_tag, '; '.join(fd[:25]) + (' …(+%d)' % (len(fd) - 25) if len(fd) > 25 else '')))
            else:
                extra = ''
                L = lay(mp.param_type.decode())
                if L and p in KEYS:
                    d = pdm.unpack(L, bytes(mp.rows[r]))
                    extra = ' ' + ', '.join('%s=%s' % (k, _f(d[k])) for k in KEYS[p] if k in d)
                lines.append('  +%d %s%s%s' % (r, nm, vi_tag, extra))
    summary[m] = sm
    open(os.path.join(H, 'rows_%s.txt' % m), 'w', encoding='utf-8').write('\n'.join(lines))
    print(m, van.NAMES[m], ver, {p: '+%d~%d vins%d' % (len(x['add']), len(x['chg']), x['vins_same']) for p, x in sm.items()})
json.dump(summary, open(os.path.join(H, 'rows_summary.json'), 'w'))
