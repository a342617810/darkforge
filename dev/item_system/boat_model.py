# -*- coding: utf-8 -*-
"""战灰「唤声船」的灵船：把提比亚唤声船（c4950）的船身做成特效模型，给 make_sfx.py 打进我们自己的 sfxbnd_c0000。
来源（只读，第一次从本机游戏里取出来放在 sfx\\vanilla\\，不改任何原版文件）：
  - c4950.chrbnd.dcx（Data3）里 c4950.flver 的网格 0：材质 C[c4950]_boat，船身、王座、灯柱、小雕像都在里面，全绑在骨骼 Boat 上；
    约 6.8 米长，船头朝 -Z，原点在船尾王座前面，甲板比原点高 0.43 米，王座座面在原点后 0.42 米、高 0.96 米（唤声船坐的地方），
    船底比原点低 0.34 米，灯柱高 3.5 米；
  - c4950_h.texbnd.dcx 的 c4950_Boat_a（BC1 sRGB 1024²）、c4950_Boat_n（BC7 512²）：DDS 原样拷进去，不重新压缩；
  - s84005.flver（公共特效包里的一个特效模型，Data0）：特效模型的写法照它（头部、贴图项后面那段、木头版的材质 / GX 列表 / 顶点格式）。
顶点在这里先摆好（用户 2026-10-29 第一次实测：船头朝向反了、人物要坐在王座上）：
  - 绕竖轴转 180°（x、z 取反，法线 / 切线一起转），再平移，让王座座面中心落在原点：特效挂在玩家脚底，人物坐上去就在座面上；
    dll\\dark_core 骑船时把人物抬高 SEAT[1] 米（boat.ini 的 seat_h），船底就回到地面。
两种外观（boat.ini 的 look 选）：
  - ghost（模型 99003）：直接用唤声船原版的材质 C[c4950]_boat（着色器 C[c4950]_Ghost，半透明的幽灵船）。材质表是全局的，
    贴图项照原版 15 个，反照率 / 法线换成我们包里的 s99003_a / _n，别的留空（用材质的默认）。顶点照原版 40 字节蒙皮格式，
    骨骼编号全改成 0（只有一根单位骨骼），网格标成动态（原版就是蒙皮网格，着色器按这个来）；GX 列表照原版材质的。
  - wood（模型 99004）：普通特效材质 S[AMSN]（不透明的木头船，第一版就是这个），静态顶点 28 字节，金属度借公共特效包的 s00003_m。
只取最精细那一档（LOD0）的三角形。
用法：make_sfx.py 里调用 files()；python boat_model.py 只生成、读回检查（不打包）。"""
import os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(PALY, 'launcher', 'reroll'))
import erlib  # noqa: E402

erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), os.path.dirname(PALY)]
VAN = os.path.join(HERE, 'sfx', 'vanilla')
SRC_CHR, SRC_TEX, TEMPLATE = 'c4950.chrbnd.dcx', 'c4950_h.texbnd.dcx', 's84005.flver'
SRC_MESH = 0
SRC_ALBEDO, SRC_NORMAL = 'c4950_Boat_a', 'c4950_Boat_n'
GHOST_MODEL, WOOD_MODEL, TEX_ID = 99003, 99004, 99003
# 王座座面中心（原模型坐标）：摆到原点
SEAT = (0.0, 0.964, 0.42)
METALLIC = 'N:\\GR\\data\\Sfx\\Tex\\s00003_m.tif'
WOOD_MTD = 'N:\\GR\\data\\Material\\mtd\\sfx\\matxml\\S[AMSN].matxml'
WOOD_TEX_TYPES = ('M_AMSN__snp_Texture2D_0_AlbedoMap_0', 'M_AMSN__snp_Texture2D_2_MetallicMap_0', 'M_AMSN__snp_Texture2D_1_NormalMap_0')
WOOD_VSIZE = 28                                 # 静态顶点：位置 12、法线 4、切线 4、顶点色 4、UV 4
NORMAL_FMT = 106                                # 原版特效模型的法线贴图（BC7）在贴图包里记的格式
SRC_LAYOUT = [(0, 0x2, 0), (12, 0x11, 3), (16, 0x11, 6), (20, 0x11, 2), (24, 0x13, 1), (28, 0x13, 10), (32, 0x16, 5)]


def _rs(b, off):
    e = off
    while b[e:e + 2] != b'\0\0':
        e += 2
    return b[off:e].decode('utf-16le')


def _gx(b, at):
    q = at
    while True:
        gid, _unk, ln = struct.unpack_from('<iii', b, q)
        q += ln
        if gid in (0x7FFFFFFF, -1):
            return b[at:q]


def _source():
    """唤声船网格：dict(raw=顶点 [n, 40], idx=LOD0 索引, mat=材质 8 个整数, mtd, gx, tex=[(类型, 0x20 原始字节)], members=布局成员原始字节)"""
    b = erlib.Bnd4(erlib.dcx_decompress(open(os.path.join(VAN, SRC_CHR), 'rb').read())).get('c4950.flver')
    ver, doff, _dlen, ndum, nmat, nbone, nmesh, nvb = struct.unpack_from('<IIIiiiii', b, 8)
    nfs, nlay, _ntex = struct.unpack_from('<iii', b, 0x50)
    p_mat = 0x80 + ndum * 0x40
    p_mesh = p_mat + nmat * 0x20 + nbone * 0x80
    p_fs = p_mesh + nmesh * 0x30
    p_vb = p_fs + nfs * 0x20
    p_lay = p_vb + nvb * 0x20
    p_tex = p_lay + nlay * 0x10
    m = struct.unpack_from('<B3x11i', b, p_mesh + SRC_MESH * 0x30)
    mi, fsc, fso, vbc, vbo = m[1], m[8], m[9], m[10], m[11]
    lod0 = None
    for k in range(fsc):
        fi = struct.unpack_from('<i', b, fso + 4 * k)[0]
        flags, strip, _cull, _u6, _u7, ic, io, _il, _, isz = struct.unpack_from('<IBBBBiiiii', b, p_fs + fi * 0x20)
        if flags == 0:
            if strip or isz != 16:
                raise RuntimeError('唤声船网格的面不是 16 位三角形列表')
            lod0 = np.frombuffer(b, dtype='<u2', count=ic, offset=doff + io).copy()
    if lod0 is None or vbc != 1:
        raise RuntimeError('唤声船网格没有 LOD0 面组，或者不止一个顶点缓冲')
    vi = struct.unpack_from('<i', b, vbo)[0]
    _bi, li, vs, vc, _, _, _bl, bo = struct.unpack_from('<8i', b, p_vb + vi * 0x20)
    mc, _, _, mo = struct.unpack_from('<4i', b, p_lay + li * 0x10)
    members = [struct.unpack_from('<5i', b, mo + 20 * k)[1:4] for k in range(mc)]
    if vs != 40 or members != SRC_LAYOUT:
        raise RuntimeError('唤声船网格的顶点格式和预想的不一样：%d 字节 %s' % (vs, members))
    mat = struct.unpack_from('<8i', b, p_mat + mi * 0x20)
    tex = [(_rs(b, struct.unpack_from('<i', b, p_tex + 0x20 * k + 4)[0]), b[p_tex + 0x20 * k:p_tex + 0x20 * (k + 1)])
           for k in range(mat[3], mat[3] + mat[2])]
    raw = np.frombuffer(b, dtype=np.uint8, count=vs * vc, offset=doff + bo).reshape(vc, vs).copy()
    return dict(raw=raw, idx=lod0, mat=mat, mtd=_rs(b, mat[1]), gx=_gx(b, mat[5]), tex=tex, members=b[mo:mo + 20 * mc])


def _template():
    t = open(os.path.join(VAN, TEMPLATE), 'rb').read()
    ndum, nmat, nbone, nmesh, nvb = struct.unpack_from('<iiiii', t, 0x14)
    nfs, nlay, ntex = struct.unpack_from('<iii', t, 0x50)
    p_mat = 0x80 + ndum * 0x40
    mat = struct.unpack_from('<8i', t, p_mat)
    p_bone = p_mat + nmat * 0x20
    p_mesh = p_bone + nbone * 0x80
    p_fs = p_mesh + nmesh * 0x30
    p_vb = p_fs + nfs * 0x20
    p_lay = p_vb + nvb * 0x20
    p_tex = p_lay + nlay * 0x10
    p_unk = p_tex + ntex * 0x20
    lay0 = struct.unpack_from('<4i', t, p_lay)
    return dict(head=t[:0x80], mat=mat, gx=_gx(t, mat[5]), bone=t[p_bone:p_bone + 0x80], fs=t[p_fs:p_fs + 0x20],
                members=t[lay0[3]:lay0[3] + 20 * lay0[0]], tex=[t[p_tex + 0x20 * k:p_tex + 0x20 * (k + 1)] for k in range(ntex)],
                unk=t[p_unk:p_unk + 0x40], vsize=struct.unpack_from('<i', t, p_vb + 8)[0])


def _placed(raw):
    """绕竖轴转 180°、王座座面中心挪到原点：位置、法线、切线一起改（字节法线 (b-127)/127，取反 = 254-b）"""
    out = raw.copy()
    n = len(raw)
    pos = raw[:, 0:12].copy().view('<f4').reshape(n, 3)
    p = np.stack([-(pos[:, 0] - SEAT[0]), pos[:, 1] - SEAT[1], -(pos[:, 2] - SEAT[2])], 1).astype('<f4')
    out[:, 0:12] = p.view(np.uint8).reshape(n, 12)
    for o in (12, 16):                          # 法线、切线的 x、z
        for k in (0, 2):
            out[:, o + k] = 254 - raw[:, o + k].astype(np.int32).clip(0, 254)
    return out, p


def _write(T, name, mtd, mat_flags, mat_unk18, gx, tex, members, dynamic, verts, vsize, idx, pos):
    """拼一个 flver：tex = [(贴图路径, 原始 0x20 字节的贴图项)]（路径空就不改原来的偏移，写空字符串）"""
    n = len(verts)
    lo, hi = pos.min(0), pos.max(0)
    used = np.unique(idx)
    if used.max() >= n:
        raise RuntimeError('索引超出顶点数')
    strings = bytearray()

    def s(text):
        at = len(strings)
        strings.extend(text.encode('utf-16le') + b'\0\0')
        return at
    at_name, at_mtd = s(name), s(mtd)
    tex_str = [(s(p), s(ty)) for p, ty, _raw in tex]
    at_bone = s(name)
    ntex = len(tex)
    o_mat, o_bone, o_mesh, o_fs, o_vb, o_lay, o_tex = 0x80, 0xA0, 0x120, 0x150, 0x170, 0x190, 0x1A0
    o_unk = o_tex + ntex * 0x20
    o_mem = o_unk + 0x40
    o_bb = (o_mem + len(members) + 15) // 16 * 16
    o_fsi = o_bb + 0x30
    o_vbi = o_fsi + 0x10
    o_gx = o_vbi + 0x10
    o_str = o_gx + len(gx)
    o_data = (o_str + len(strings) + 15) // 16 * 16
    ibytes = idx.astype('<u2').tobytes()
    vb_off = (len(ibytes) + 15) // 16 * 16
    data = ibytes + bytes(vb_off - len(ibytes)) + verts.tobytes()
    out = bytearray(o_data + len(data))
    head = bytearray(T['head'])
    tris = len(idx) // 3
    struct.pack_into('<IIiiiii6fii', head, 0x0C, o_data, len(data), 0, 1, 1, 1, 1, *lo, *hi, tris, tris)
    struct.pack_into('<iii', head, 0x50, 1, 1, ntex)
    out[0:0x80] = head
    struct.pack_into('<8i', out, o_mat, o_str + at_name, o_str + at_mtd, ntex, 0, mat_flags, o_gx, mat_unk18, 0)
    bone = bytearray(0x80)
    struct.pack_into('<3fi3fhh3fhh3fi3f', bone, 0, 0, 0, 0, o_str + at_bone, 0, 0, 0, -1, -1, 1, 1, 1, -1, -1,
                     *lo, struct.unpack_from('<i', T['bone'], 0x3C)[0], *hi)
    out[o_bone:o_bone + 0x80] = bone
    struct.pack_into('<B3x11i', out, o_mesh, 1 if dynamic else 0, 0, 0, 0, 0, 0, o_bb, o_fsi, 1, o_fsi, 1, o_vbi)
    fs = bytearray(T['fs'])
    struct.pack_into('<iii', fs, 8, len(idx), 0, len(ibytes))
    out[o_fs:o_fs + 0x20] = fs
    struct.pack_into('<8i', out, o_vb, 0, 0, vsize, n, 0, 0, n * vsize, vb_off)
    struct.pack_into('<4i', out, o_lay, len(members) // 20, 0, 0, o_mem)
    for k, ((_p, _ty, raw), (ap, at)) in enumerate(zip(tex, tex_str)):
        t = bytearray(raw)
        struct.pack_into('<ii', t, 0, o_str + ap, o_str + at)
        out[o_tex + 0x20 * k:o_tex + 0x20 * (k + 1)] = t
    unk = bytearray(T['unk'])                     # 照模板：两个计数 + 两个成员表偏移，成员各 0x10
    struct.pack_into('<ii', unk, 4, o_unk + 0x20, o_unk + 0x30)
    out[o_unk:o_unk + 0x40] = unk
    out[o_mem:o_mem + len(members)] = members
    struct.pack_into('<9f', out, o_bb, *lo, *hi, *pos[used].mean(0))
    out[o_gx:o_gx + len(gx)] = gx
    out[o_str:o_str + len(strings)] = strings
    out[o_data:] = data
    return bytes(out), (lo, hi)


def tex_path(suffix):
    return 'N:\\GR\\data\\Sfx\\Tex\\s%05d_%s.tif' % (TEX_ID, suffix)


def build_flver(look):
    """→ (flver 字节, 顶点数, 三角形数, 包围盒)。look：ghost（原版幽灵材质）/ wood（普通特效材质）"""
    src = _source()
    T = _template()
    raw, p = _placed(src['raw'])
    idx = src['idx']
    if look == 'ghost':
        raw[:, 20:24] = 0                         # 骨骼编号：都是第 0 根（权重原来就是 255,0,0,0）
        tex = []
        for ty, r in src['tex']:
            path = tex_path('a') if ty.endswith('_7_AlbedoMap') else tex_path('n') if ty.endswith('_0_NormalMap') else ''
            tex.append((path, ty, r))
        m = src['mat']
        fl, box = _write(T, 's%05d' % GHOST_MODEL, src['mtd'], m[4], m[6], src['gx'], tex, src['members'], True, raw, 40, idx, p)
    else:
        if T['vsize'] != WOOD_VSIZE:
            raise RuntimeError('特效模型模板的顶点大小不是 %d' % WOOD_VSIZE)
        v = np.zeros((len(raw), WOOD_VSIZE), np.uint8)
        v[:, 0:12] = raw[:, 0:12]                 # 位置
        v[:, 12:15] = raw[:, 12:15]               # 法线（第 4 位 = 静态网格的骨骼编号 0）
        v[:, 16:20] = raw[:, 16:20]               # 切线
        v[:, 20:24] = raw[:, 28:32]               # 顶点色
        v[:, 24:28] = raw[:, 32:36]               # UV（只要第一组）
        tex = [(path, ty, r) for path, ty, r in zip((tex_path('a'), METALLIC, tex_path('n')), WOOD_TEX_TYPES, T['tex'])]
        m = T['mat']
        fl, box = _write(T, 's%05d' % WOOD_MODEL, WOOD_MTD, m[4], m[6], T['gx'], tex, T['members'], False, v, WOOD_VSIZE, idx, p)
    return fl, len(raw), len(idx) // 3, box


def textures():
    """→ [(贴图名, tpf 字节)]：船的反照率、法线，DDS 原样"""
    b = erlib.Bnd4(erlib.dcx_decompress(open(os.path.join(VAN, SRC_TEX), 'rb').read()))
    t = erlib.read_tpf(b.get('c4950_h.tpf'))
    got = {x['name']: x for x in t['tex']}
    out = []
    for src, suf, fmt in ((SRC_ALBEDO, 'a', None), (SRC_NORMAL, 'n', NORMAL_FMT)):
        x = dict(got[src])
        x['name'] = 's%05d_%s' % (TEX_ID, suf)
        if fmt is not None:
            x['fmt'] = fmt
        out.append((x['name'], erlib.write_tpf(dict(flag2=t['flag2'], enc=t['enc'], tex=[x]))))
    return out


def files():
    """make_sfx.py 打包用：（[(包里的相对名字, 数据)]，{模型编号: 资源清单里要列的名字}，说明）"""
    out, res, info = [], {}, []
    for look, mid in (('ghost', GHOST_MODEL), ('wood', WOOD_MODEL)):
        fl, n, tris, (lo, hi) = build_flver(look)
        out.append(('model\\s%05d.flver' % mid, fl))
        res[mid] = ['s%05d_a.tif' % TEX_ID, 's%05d_n.tif' % TEX_ID] + (['s00003_m.tif'] if look == 'wood' else []) + ['s%05d.sib' % mid]
        info.append('%s s%05d：%d 个顶点、%d 个三角形，%.2f×%.2f×%.2f 米（座面在原点）' % (look, mid, n, tris, *(hi - lo)))
    out += [('tex\\%s.tpf' % name, data) for name, data in textures()]
    return out, res, '灵船模型：' + '；'.join(info)


def check(fl):
    """读回检查：各段偏移、字符串、索引和顶点都在文件里"""
    ver, doff, dlen, ndum, nmat, nbone, nmesh, nvb = struct.unpack_from('<IIIiiiii', fl, 8)
    assert doff + dlen == len(fl), '数据区长度不对'
    mat = struct.unpack_from('<8i', fl, 0x80)
    fs = struct.unpack_from('<IBBBBiiiii', fl, 0x150)
    vb = struct.unpack_from('<8i', fl, 0x170)
    idx = np.frombuffer(fl, dtype='<u2', count=fs[5], offset=doff + fs[6])
    assert idx.max() < vb[3], '索引超出'
    assert doff + vb[7] + vb[6] == len(fl), '顶点区不在最后'
    tex = [(_rs(fl, struct.unpack_from('<i', fl, 0x1A0 + 0x20 * k)[0]), _rs(fl, struct.unpack_from('<i', fl, 0x1A0 + 0x20 * k + 4)[0]))
           for k in range(mat[2])]
    return dict(mtd=_rs(fl, mat[1]), dynamic=fl[0x120], vb=vb, tex=[t for t in tex if t[0]], ntex=len(tex))


if __name__ == '__main__':
    for look in ('ghost', 'wood'):
        fl, n, tris, (lo, hi) = build_flver(look)
        print(look, '%d 字节，顶点 %d，三角形 %d，包围盒 %s ~ %s' % (len(fl), n, tris, lo.round(2), hi.round(2)))
        print('  ', check(fl))
    for name, data in textures():
        print(name, len(data))
