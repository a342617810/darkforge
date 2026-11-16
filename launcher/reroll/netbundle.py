# -*- coding: utf-8 -*-
"""从 .NET 单文件程序（随机器 EldenRingRandomizer.exe）里取出打包的文件（SoulsFormats.dll 等），只读。
格式（.NET 6+ 的单文件包）：程序里有一段 32 字节的标记（「.net core bundle」的 SHA-256），标记前 8 字节 = 包头偏移；
包头：主版本 u32、次版本 u32、文件数 i32、包 ID（7 位变长长度 + UTF-8），主版本 >= 2 时再跟 deps.json / runtimeconfig.json 的偏移和长度、标志 u64；
每个文件：偏移 i64、长度 i64、（主版本 >= 6）压缩后长度 i64（0 = 没压缩，否则是 Deflate）、类型 u8、相对路径（同上的字符串）。"""
import struct
import zlib

MARKER = bytes.fromhex('8b1202b96a612038727b930214d7a03213f5b9e6efae3318ee3b2dce24b36aae')


def _str(raw, o):
    n, shift = 0, 0
    while True:
        b = raw[o]
        o += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if b < 0x80:
            break
    return raw[o:o + n].decode('utf-8'), o + n


def entries(raw):
    """{相对路径: (偏移, 长度, 压缩后长度)}"""
    k = raw.find(MARKER)
    if k < 8:
        raise ValueError('不是 .NET 单文件程序（没找到包标记）')
    o = struct.unpack_from('<q', raw, k - 8)[0]
    major, _minor, n = struct.unpack_from('<IIi', raw, o)
    _bid, o = _str(raw, o + 12)
    if major >= 2:
        o += 8 * 5
    out = {}
    for _ in range(n):
        off, size = struct.unpack_from('<qq', raw, o)
        o += 16
        csize = 0
        if major >= 6:
            csize = struct.unpack_from('<q', raw, o)[0]
            o += 8
        o += 1                                   # 类型
        path, o = _str(raw, o)
        out[path.replace('\\', '/')] = (off, size, csize)
    return out


def extract(raw, name):
    """取出一个文件（按文件名，不分目录）的内容；没有就 None"""
    for path, (off, size, csize) in entries(raw).items():
        if path.rsplit('/', 1)[-1].lower() == name.lower():
            data = raw[off:off + (csize or size)]
            return zlib.decompress(data, -15) if csize else bytes(data)
    return None
