# -*- coding: utf-8 -*-
"""地图 MSB：模组 vs 原版，按名字比较部件（敌人 / 物件 / 玩家点）和区域：新增 / 删除 / 改了模型、实体编号、位置的。
用旧会话编好的 msbdump.dll（SoulsFormats，只读）把整张图列出来（半径给很大）"""
import os, sys, subprocess, re, tempfile, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import van

DUMP = os.path.join(van.HERE, 'msbdump', 'msbdump.dll')     # 只读的 SoulsFormats 小工具（源码 msbdump.cs），要 .NET 8
TMP = os.path.join(van.HERE, 'msb_tmp')
os.makedirs(TMP, exist_ok=True)


def dump(path):
    out = subprocess.run(['dotnet', DUMP, path, '0', '0', '0', '1e9'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if out.returncode:
        raise RuntimeError(out.stderr[:500])
    items = {}
    for ln in out.stdout.splitlines():
        m = re.match(r'(REGION|PART) (\w+) (\S+) (.*)', ln)
        if m:
            kind, typ, name, rest = m.groups()
            items[(kind, name)] = (typ, rest)
    return items


def pos_of(rest):
    m = re.search(r'pos=<([^>]*)>', rest)
    return tuple(round(float(x), 2) for x in m.group(1).split(',')) if m else None


for m in sorted(van.ROOTS):
    md = os.path.join(van.root(m), 'map', 'MapStudio')
    if not os.path.isdir(md):
        md = os.path.join(van.root(m), 'map', 'mapstudio')
    if not os.path.isdir(md):
        continue
    for f in sorted(os.listdir(md)):
        if not f.endswith('.msb.dcx'):
            continue
        v = van.vread('/map/mapstudio/' + f)
        if v is None:
            print('\n== %s %s：原版没有这张图' % (m, f))
            continue
        vp = os.path.join(TMP, 'v_' + f[:-4])
        open(vp, 'wb').write(van.unz(v))
        mp = os.path.join(TMP, m + '_' + f[:-4])
        open(mp, 'wb').write(van.unz(open(os.path.join(md, f), 'rb').read()))
        V, M = dump(vp), dump(mp)
        add = [k for k in M if k not in V]
        rem = [k for k in V if k not in M]
        chg = []
        for k in M:
            if k in V and M[k] != V[k]:
                a, b = V[k][1], M[k][1]
                what = []
                if pos_of(a) != pos_of(b):
                    what.append('位置')
                ra, rb = re.sub(r'pos=<[^>]*>|rot=<[^>]*>', '', a), re.sub(r'pos=<[^>]*>|rot=<[^>]*>', '', b)
                if ra != rb:
                    what.append('属性')
                if what:
                    chg.append((k, what, a, b))
        print('\n== %s %s %s   新增 %d / 删除 %d / 改 %d' % (m, van.NAMES[m], f, len(add), len(rem), len(chg)))
        cnt = collections.Counter((k[0], M[k][0]) for k in add)
        print('  新增类型:', dict(cnt))
        for k in add:
            if k[0] == 'PART' and M[k][0] in ('Enemy', 'DummyEnemy', 'Player') or k[0] == 'REGION' and len(add) < 40:
                print('   + %s %s %s %s' % (k[0], M[k][0], k[1], M[k][1][:170]))
        for k in rem[:15]:
            print('   - %s %s %s' % (k[0], V[k][0], k[1]))
        for k, what, a, b in chg[:40]:
            if k[0] == 'PART' and M[k][0] not in ('Enemy', 'DummyEnemy', 'Player', 'Asset') and what == ['属性']:
                continue
            print('   ~ %s %s %s %s\n       原: %s\n       模: %s' % (k[0], M[k][0], k[1], '/'.join(what), a[:170], b[:170]))
