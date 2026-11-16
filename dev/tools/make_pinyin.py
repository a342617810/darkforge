# -*- coding: utf-8 -*-
"""生成 dev/dark_ui/src/ui/pinyin_table.bin（装备工坊拼音搜索的数据，用户 2026-11-09「用拼音搜索吧」）。
数据用 Windows 自带的 ICU（icu.dll 的 Han-Latin 转写，Win10 1903 起系统自带，不用下载）：基本汉字区 U+4E00~U+9FFF 每个字一个读音，去掉声调，ü 写成 v。
只有生成表的时候用，表进 dark_ui.dll，玩家机器上不跑这个。
文件格式：<音节个数 u16><音节表：空格分开的 ASCII，长度 u16 + 内容><每个字一个 u16（音节序号 + 1，0 = 没有读音），从 U+4E00 到 U+9FFF>，都是小端
一字多音的另外一些读音写在 dark_ui 的 ui/pinyin.rs 的 EXTRA 里（这里只有最常见的读音）。
用法：python -X utf8 dev/tools/make_pinyin.py [检查用的文字文件 …]（报告这些文件里的汉字有没有读音）"""
import ctypes as C
import os
import struct
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'dark_ui', 'src', 'ui', 'pinyin_table.bin')
FIRST, LAST = 0x4E00, 0x9FFF

icu = C.WinDLL('icu.dll')
icu.utrans_openU.restype = C.c_void_p
icu.utrans_openU.argtypes = [C.c_wchar_p, C.c_int32, C.c_int, C.c_void_p, C.c_int32, C.c_void_p, C.POINTER(C.c_int)]
icu.utrans_transUChars.restype = None
icu.utrans_transUChars.argtypes = [C.c_void_p, C.c_wchar_p, C.POINTER(C.c_int32), C.c_int32, C.c_int32, C.POINTER(C.c_int32), C.POINTER(C.c_int)]
st = C.c_int(0)
trans = icu.utrans_openU('Han-Latin', -1, 0, None, 0, None, C.byref(st))
if st.value > 0 or not trans:
    sys.exit('icu.dll 打不开 Han-Latin 转写（错误 %d）' % st.value)


def latin(ch):
    buf = C.create_unicode_buffer(ch, 64)
    n = C.c_int32(len(ch))
    limit = C.c_int32(len(ch))
    err = C.c_int(0)
    icu.utrans_transUChars(trans, buf, C.byref(n), 64, 0, C.byref(limit), C.byref(err))
    if err.value > 0:
        raise RuntimeError('转写失败 %04X：%d' % (ord(ch), err.value))
    return buf.value[:n.value]


def plain(s):
    """去声调，ü → v，只留小写字母；转不出来（还是汉字）返回空"""
    out = []
    for c in unicodedata.normalize('NFD', s.strip().lower()):
        if c == '̈' and out and out[-1] == 'u':
            out[-1] = 'v'
        elif 'a' <= c <= 'z':
            out.append(c)
        elif unicodedata.category(c) != 'Mn':
            return ''
    return ''.join(out)


table, syl = [], {}
for cp in range(FIRST, LAST + 1):
    p = plain(latin(chr(cp)))
    table.append(syl.setdefault(p, len(syl)) + 1 if p else 0)
names = sorted(syl, key=syl.get)
text = ' '.join(names).encode('ascii')
with open(OUT, 'wb') as f:
    f.write(struct.pack('<HH', len(names), len(text)) + text)
    f.write(struct.pack('<%dH' % len(table), *table))
print('音节 %d 个，有读音的字 %d / %d，写了 %d 字节：%s' % (len(names), sum(1 for x in table if x), len(table), os.path.getsize(OUT), os.path.normpath(OUT)))
for ch in '法术重击血传说凝聚头部驴绿':
    print(ch, names[table[ord(ch) - FIRST] - 1] if table[ord(ch) - FIRST] else '（无）', end='  ')
print()
for path in sys.argv[1:]:
    t = open(path, encoding='utf-8').read()
    han = sorted({c for c in t if FIRST <= ord(c) <= LAST})
    miss = [c for c in han if not table[ord(c) - FIRST]]
    out_of = sorted({c for c in t if unicodedata.category(c) == 'Lo' and not FIRST <= ord(c) <= LAST and ord(c) > 0x2E80 and not 0x3040 <= ord(c) <= 0x30FF})
    print(os.path.basename(path), '汉字 %d 种，没读音 %d：%s；基本区以外 %s' % (len(han), len(miss), ''.join(miss[:40]), ''.join(out_of[:20])))
