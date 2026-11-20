# -*- coding: utf-8 -*-
"""静态核对双版本 DLL：从源码里读出 dark_lock 的 VERSIONS / checks() 和 dark_sell 的 NO_ARROW，
在 2.7.1.0（本机）和 2.7.2.0（ER_new）两个 exe 上照 DLL 的逻辑走一遍：每个 exe 应该正好认出自己那一组；
再照 fromsoftware-rs 的 detect 读版本资源（产品版本、语言、产品名）"""
import os, re, struct, sys
import pefile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # 仓库的 dev
EXES = {'2.7.1.0': os.path.normpath(os.path.join(ROOT, '..', '..', 'eldenring.exe')),   # 本机游戏的 exe
        '2.7.2.0': os.environ.get('ER_NEW_EXE') or os.path.expanduser(r'~\ER_new\Game\eldenring.exe')}   # 另一版（环境变量 ER_NEW_EXE 可换）

lock = open(ROOT + r'\dark_lock\src\lib.rs', encoding='utf-8').read()
sell = open(ROOT + r'\dark_sell\src\lib.rs', encoding='utf-8').read()


def num(s):
    return int(s.replace('_', ''), 0)


def bytes_of(s):
    return bytes(num(x) for x in re.findall(r'0x[0-9a-fA-F]+', s))


# dark_lock：VERSIONS 里每一组
vers = []
body = lock.split('static VERSIONS')[1].split('\n];')[0]
for blk in re.findall(r'Rvas \{(.*?)\n    \}', body, re.S):
    v = {}
    for k, val in re.findall(r'(\w+): (0x[0-9a-fA-F]+|"[^"]*"|\[[^\]]*\])', blk):
        v[k] = val.strip('"') if val.startswith('"') else bytes_of(val) if val.startswith('[') else num(val)
    vers.append(v)
# checks()：（字段, 开头字节）
chk = []
cbody = lock.split('fn checks(&self)')[1].split('\n    }\n}')[0]
for f, arr in re.findall(r'\(self\.(\w+), &(\[[^\]]*\]|self\.\w+)\)', cbody):
    chk.append((f, arr))
assert len(chk) == 13, chk
# 箭袋护符 2026-10-29 删掉了（NO_ARROW 不在了），没有就不核对
arrow = [(num(a), num(b)) for a, b in re.findall(r'\((0x[0-9A-Fa-f]+), (0x[0-9A-Fa-f]+)\)', sell.split('const NO_ARROW:')[1].split('=', 1)[1].split(';')[0])] \
    if 'const NO_ARROW:' in sell else []
assert len(arrow) in (0, 2), arrow
print('dark_lock 版本组：', [v['version'] for v in vers], '；dark_sell 箭袋组：', [(hex(a), hex(b)) for a, b in arrow])

ok = True
for exe_ver, path in EXES.items():
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
    img = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    # 版本资源（照 detect：dwProductVersion、第一个翻译的语言、ProductName）
    fi = pe.VS_FIXEDFILEINFO[0]
    pv = '%d.%d.%d.%d' % (fi.ProductVersionMS >> 16, fi.ProductVersionMS & 0xffff, fi.ProductVersionLS >> 16, fi.ProductVersionLS & 0xffff)
    lang, name = None, None
    for fi2 in pe.FileInfo[0]:
        if getattr(fi2, 'Key', b'') == b'VarFileInfo':
            for var in fi2.Var:
                tr = var.entry.get(b'Translation') or var.entry.get('Translation')
                if tr:
                    lang = int(tr.split()[0], 16) & 0x3ff
        if getattr(fi2, 'Key', b'') == b'StringFileInfo':
            for st in fi2.StringTable:
                name = st.entries.get(b'ProductName', name)
    print('\n== %s：产品版本 %s 语言 %#x 产品名 %r' % (path, pv, lang or -1, name))
    if pv != exe_ver:
        ok = False
        print('   ！产品版本和预期不同')
    # dark_lock：照 install() 的顺序找第一组对得上的
    hit = None
    for v in vers:
        bad = None
        for f, arr in chk:
            want = v[arr[5:]] if arr.startswith('self.') else bytes_of(arr)
            got = img[v[f]:v[f] + len(want)]
            if got != want:
                bad = '%s exe+%#x 字节 %s' % (f, v[f], got.hex())
                break
        if not bad:
            vt0 = struct.unpack_from('<Q', img, v['memfile_vt'])[0] - base
            if vt0 != v['memfile_vt0']:
                bad = '虚表 %#x' % vt0
        print('   dark_lock 按 %s：%s' % (v['version'], '对得上' if not bad else '对不上（%s）' % bad))
        if not bad and hit is None:
            hit = v['version']
    print('   → dark_lock 选中', hit)
    if not hit or not hit.startswith(exe_ver):
        ok = False
    # dark_sell 箭袋
    hit = None
    for check, flag in arrow:
        b = img[check:check + 7]
        tgt = check + 7 + struct.unpack_from('<i', b, 2)[0]
        good = b[0] == 0x80 and b[1] == 0x3d and b[6] == 0 and tgt == flag
        print('   箭袋 (%#x, %#x)：%s（%s → %#x）' % (check, flag, '对得上' if good else '对不上', b.hex(), tgt))
        if good and hit is None:
            hit = (check, flag)
    if arrow and hit is None:
        ok = False
print('\n全部符合预期' if ok else '\n！有不符合预期的')
