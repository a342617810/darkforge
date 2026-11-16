# -*- coding: utf-8 -*-
"""重随用的最小工具库：regulation.bin 解密/解压/写回、BND4、PARAM、FMG、存档读取。

只用 Python 标准库；AES 用 Windows 自带的 bcrypt.dll（CNG），KRAK 压缩靠游戏自带的 oo2core_6_win64.dll，ZSTD 靠 libzstd.dll（整合包自带，在 bin 文件夹里）。
写回一律用 DFLT（zlib），RNG Lands 原包就是 DFLT，游戏可以读。
"""
import ctypes
import os
import struct
import zlib

_PENDING = None            # 延迟写出的 DCX：{规范化路径: (路径, 解压后的数据, 压缩等级)}；None = 直接写
JOBS = 1                   # pmap 默认的进程数（reroll / scripts 启动时按负载设）


def cpu_idle_cores(sample=0.3):
    """这一刻空闲的逻辑核数（GetSystemTimes 采样 sample 秒）；拿不到就 None"""
    try:
        import time
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32

        def times():
            ft = [wintypes.FILETIME() for _ in range(3)]
            if not k32.GetSystemTimes(*(ctypes.byref(x) for x in ft)):
                raise OSError('GetSystemTimes')
            return [(x.dwHighDateTime << 32) | x.dwLowDateTime for x in ft]
        i0, k0, u0 = times()
        time.sleep(sample)
        i1, k1, u1 = times()
        total = (k1 - k0) + (u1 - u0)             # 内核时间里含空闲时间
        frac = (i1 - i0) / float(total) if total > 0 else 1.0
        return max(0.0, min(1.0, frac)) * (os.cpu_count() or 1)
    except Exception:
        return None


def free_mb():
    """可用物理内存（MB）；拿不到就 None"""
    try:
        class MS(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong)] + \
                       [(n, ctypes.c_ulonglong) for n in ('total', 'avail', 'tpf', 'apf', 'tv', 'av', 'aev')]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        return m.avail / 2 ** 20 if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None
    except Exception:
        return None


def auto_jobs(want=0, mem_per_job=250):
    """并行进程数：want > 0 就用它（1 = 不并行）；0 = 自动 = 这一刻空闲的核数（四舍五入），
    再按可用内存（每个进程约 mem_per_job MB，留 1 GB 给系统和游戏）封顶；至少 1，最多 逻辑核数 - 1（Windows 进程池上限 61）。
    返回 (进程数, 说明)"""
    cpu = os.cpu_count() or 1
    if want and int(want) > 0:
        n, why = int(want), '设置指定'
    else:
        idle = cpu_idle_cores()
        n = int(idle + 0.5) if idle is not None else cpu // 2
        why = '空闲约 %.1f / %d 核' % (idle, cpu) if idle is not None else '读不到负载，按一半核数'
    fm = free_mb()
    if fm is not None:
        n = min(n, int((fm - 1024) // mem_per_job))
        why += '，可用内存 %.0f MB' % fm
    return max(1, min(n, max(1, cpu - 1), 61)), why


def _worker_init(dll_dirs):
    """子进程：外部 dll 的搜索目录跟主进程一样（解压 KRAK 要 oo2core）"""
    DLL_DIRS[:] = dll_dirs


def pmap(fn, items, jobs=None, while_waiting=None, chunksize=1):
    """并行 map：fn 要是模块里的顶层函数（子进程按名字导入）；结果顺序同 items。
    jobs 默认用 JOBS；只有 1 个进程或 1 件事就在本进程里做；进程池起不来 / 中途崩了就退回单进程整批重做（各任务要可重复做）。
    while_waiting：任务交出去之后在主进程里顺便做的事"""
    items = list(items)
    jobs = JOBS if jobs is None else jobs
    if jobs > 1 and len(items) > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=min(jobs, len(items)), initializer=_worker_init, initargs=(list(DLL_DIRS),)) as ex:
                futs = ex.map(fn, items, chunksize=chunksize)
                if while_waiting is not None:
                    while_waiting()
                    while_waiting = None
                return list(futs)
        except Exception as e:
            from concurrent.futures.process import BrokenProcessPool
            if not isinstance(e, (BrokenProcessPool, OSError, PermissionError)):
                raise                                  # 任务本身出错：照常报错
            print('  [提示] 并行处理没成功（%s: %s），改成单进程' % (type(e).__name__, e), flush=True)
    out = [fn(x) for x in items]
    if while_waiting is not None:
        while_waiting()
    return out


ER_REG_KEY = bytes.fromhex('99BFFC366A6BC8C6F5827D093602D676C42892A01C207FB024D3AF4E493FEF99')

# 外部 dll 的搜索目录（由调用方设置）
DLL_DIRS = []


# 整合包自带的 dll（libzstd.dll）：DLL_DIRS 里都没有时再找这里（以前借随机器文件夹里的那份，正式发布不带随机器）
BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')


def _find_dll(name):
    for d in DLL_DIRS + [BIN_DIR]:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError('找不到 %s（搜索过：%s）' % (name, '; '.join(DLL_DIRS + [BIN_DIR])))


_oodle = None
_zstd = None


def _oodle_dec(src, rawlen):
    global _oodle
    if _oodle is None:
        _oodle = ctypes.WinDLL(_find_dll('oo2core_6_win64.dll'))
        _oodle.OodleLZ_Decompress.restype = ctypes.c_ssize_t
    out = ctypes.create_string_buffer(rawlen)
    n = _oodle.OodleLZ_Decompress(src, ctypes.c_ssize_t(len(src)), out, ctypes.c_ssize_t(rawlen),
                                  1, 0, 0, None, 0, None, None, None, 0, 3)
    if n != rawlen:
        raise RuntimeError('Oodle 解压失败（%d）' % n)
    return out.raw


def _zstd_dec(src, rawlen):
    global _zstd
    if _zstd is None:
        _zstd = ctypes.CDLL(_find_dll('libzstd.dll'))
        _zstd.ZSTD_decompress.restype = ctypes.c_size_t
    out = ctypes.create_string_buffer(rawlen)
    n = _zstd.ZSTD_decompress(out, ctypes.c_size_t(rawlen), src, ctypes.c_size_t(len(src)))
    if n != rawlen:
        raise RuntimeError('ZSTD 解压失败（%d）' % n)
    return out.raw


# ---------------------------------------------------------------- DCX
def dcx_decompress(b):
    # 有的工具写出的头部不规范（缺 DCX/DCA 段），按标记定位
    dcs = b.index(b'DCS\0')
    usize, csize = struct.unpack('>II', b[dcs + 4:dcs + 12])
    dcp = b.index(b'DCP\0')
    fmt = b[dcp + 4:dcp + 8]
    dca = b.find(b'DCA\0', 0, 0x100)
    start = dca + struct.unpack('>I', b[dca + 4:dca + 8])[0] if dca >= 0 else dcs + 12
    data = b[start:start + csize]
    if fmt == b'DFLT':
        return zlib.decompressobj().decompress(data)
    if fmt == b'KRAK':
        return _oodle_dec(data, usize)
    if fmt == b'ZSTD':
        return _zstd_dec(data, usize)
    raise ValueError('不支持的 DCX 压缩格式：%r' % fmt)


def dcx_compress_dflt(raw, level=6):
    comp = zlib.compress(raw, level)
    head = (b'DCX\0' + struct.pack('>IIIII', 0x11000, 0x18, 0x24, 0x44, 0x4C)
            + b'DCS\0' + struct.pack('>II', len(raw), len(comp))
            + b'DCP\0' + b'DFLT' + struct.pack('>I', 0x20) + bytes([9, 0, 0, 0])
            + struct.pack('>IIII', 0, 0, 0, 0x00010100)
            + b'DCA\0' + struct.pack('>I', 8))
    assert len(head) == 0x4C, len(head)  # 游戏按固定偏移读：DCA 在 0x44，数据从 0x4C 开始
    return head + comp


def dcx_check_strict(b):
    """按游戏的方式（固定偏移）检查并解压标准 DCX_DFLT 头，不靠搜索标记。"""
    if b[:4] != b'DCX\0' or struct.unpack('>5I', b[4:24]) != (0x11000, 0x18, 0x24, 0x44, 0x4C):
        raise ValueError('DCX 头不标准')
    if b[0x18:0x1C] != b'DCS\0' or b[0x24:0x28] != b'DCP\0' or b[0x44:0x48] != b'DCA\0':
        raise ValueError('DCX 段标记不在固定位置')
    usize, csize = struct.unpack('>II', b[0x1C:0x24])
    raw = zlib.decompress(b[0x4C:0x4C + csize])
    if len(raw) != usize:
        raise ValueError('DCX 解压大小不符')
    return raw


# ---------------------------------------------------------------- regulation
def _aes_cbc(key, iv, data, encrypt, chain='ChainingModeCBC'):
    """AES-CBC（不带填充；chain='ChainingModeECB' 时是 ECB，iv 给 None），走 Windows CNG，省掉 pycryptodome 依赖。"""
    from ctypes import byref, c_ulong, c_void_p, c_wchar_p, create_string_buffer
    bc = ctypes.WinDLL('bcrypt')
    for fn in (bc.BCryptOpenAlgorithmProvider, bc.BCryptSetProperty, bc.BCryptGenerateSymmetricKey,
               bc.BCryptEncrypt, bc.BCryptDecrypt, bc.BCryptDestroyKey, bc.BCryptCloseAlgorithmProvider):
        fn.restype = ctypes.c_long
    bc.BCryptOpenAlgorithmProvider.argtypes = [ctypes.POINTER(c_void_p), c_wchar_p, c_wchar_p, c_ulong]
    bc.BCryptSetProperty.argtypes = [c_void_p, c_wchar_p, c_void_p, c_ulong, c_ulong]
    bc.BCryptGenerateSymmetricKey.argtypes = [c_void_p, ctypes.POINTER(c_void_p), c_void_p, c_ulong,
                                              c_void_p, c_ulong, c_ulong]
    crypt_args = [c_void_p, c_void_p, c_ulong, c_void_p, c_void_p, c_ulong, c_void_p, c_ulong,
                  ctypes.POINTER(c_ulong), c_ulong]
    bc.BCryptEncrypt.argtypes = crypt_args
    bc.BCryptDecrypt.argtypes = crypt_args
    bc.BCryptDestroyKey.argtypes = [c_void_p]
    bc.BCryptCloseAlgorithmProvider.argtypes = [c_void_p, c_ulong]

    def ok(st, what):
        if st != 0:
            raise OSError('bcrypt %s 失败：0x%08X' % (what, st & 0xFFFFFFFF))
    if len(data) % 16:
        raise ValueError('AES 数据长度不是 16 的倍数')
    alg, hkey = c_void_p(), c_void_p()
    ok(bc.BCryptOpenAlgorithmProvider(byref(alg), 'AES', None, 0), 'OpenAlgorithmProvider')
    try:
        mode = ctypes.create_unicode_buffer(chain)
        ok(bc.BCryptSetProperty(alg, 'ChainingMode', mode, ctypes.sizeof(mode), 0), 'SetProperty')
        kbuf = create_string_buffer(key, len(key))
        ok(bc.BCryptGenerateSymmetricKey(alg, byref(hkey), None, 0, kbuf, len(key), 0), 'GenerateSymmetricKey')
        try:
            src = create_string_buffer(bytes(data), len(data))
            ivb = create_string_buffer(iv, 16) if iv is not None else None
            out = create_string_buffer(len(data))
            n = c_ulong()
            fn = bc.BCryptEncrypt if encrypt else bc.BCryptDecrypt
            ok(fn(hkey, src, len(data), None, ivb, 16 if iv is not None else 0, out, len(data), byref(n), 0),
               'Encrypt' if encrypt else 'Decrypt')
            return out.raw[:n.value]
        finally:
            bc.BCryptDestroyKey(hkey)
    finally:
        bc.BCryptCloseAlgorithmProvider(alg, 0)


def read_regulation(path, strict=False):
    raw = open(path, 'rb').read()
    body = raw[16:len(raw) - (len(raw) - 16) % 16]
    dec = _aes_cbc(ER_REG_KEY, raw[:16], body, False)
    return dcx_check_strict(dec) if strict else dcx_decompress(dec)


def write_regulation(path, bnd, level=6):
    data = dcx_compress_dflt(bnd, level)
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    iv = os.urandom(16)
    enc = iv + _aes_cbc(ER_REG_KEY, iv, data, True)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(enc)
    os.replace(tmp, path)


# ---------------------------------------------------------------- BND4
def _rev8(x):
    return int('{:08b}'.format(x)[::-1], 2)


class Bnd4:
    """只读解析 + “追加并改指向”的方式替换单个文件（不移动其他文件）。"""

    def __init__(self, data):
        self.data = bytearray(data)
        b = self.data
        if b[:4] != b'BND4':
            raise ValueError('不是 BND4')
        bit_big = not b[0x0A]
        self.count = struct.unpack_from('<i', b, 0x0C)[0]
        self.hdr_size = struct.unpack_from('<q', b, 0x20)[0]
        self.unicode = b[0x30]
        fmt = b[0x31]
        if not bit_big:
            fmt = _rev8(fmt)
        self.has_ids, self.has_names = fmt & 2, fmt & 0x0C
        self.long_off, self.compr = fmt & 0x10, fmt & 0x20
        self.entries = {}
        pos = 0x40
        for _ in range(self.count):
            p = pos + 8
            csize_at = p
            csize = struct.unpack_from('<q', b, p)[0]
            p += 8
            usize_at = None
            if self.compr:
                usize_at = p
                p += 8
            off_at = p
            if self.long_off:
                off = struct.unpack_from('<q', b, p)[0]
                p += 8
            else:
                off = struct.unpack_from('<I', b, p)[0]
                p += 4
            if self.has_ids:
                p += 4
            name = None
            if self.has_names:
                noff = struct.unpack_from('<I', b, p)[0]
                if self.unicode:
                    e = noff
                    while b[e:e + 2] != b'\0\0':
                        e += 2
                    name = b[noff:e].decode('utf-16le')
                else:
                    name = bytes(b[noff:b.index(b'\0', noff)]).decode('shift_jis')
            short = os.path.basename(name.replace('\\', '/')) if name else str(len(self.entries))
            self.entries[short] = dict(off=off, size=csize, csize_at=csize_at, usize_at=usize_at, off_at=off_at, first=off)
            pos += self.hdr_size

    def get(self, short):
        e = self.entries[short]
        return bytes(self.data[e['off']:e['off'] + e['size']])

    def put(self, short, new):
        e = self.entries[short]
        if len(new) <= e['size']:
            self.data[e['off']:e['off'] + len(new)] = new
        else:
            while len(self.data) % 16:
                self.data.append(0)
            off = len(self.data)
            self.data += new
            if self.long_off:
                struct.pack_into('<q', self.data, e['off_at'], off)
            else:
                if off > 0xFFFFFFFF:
                    raise ValueError('BND4 太大')
                struct.pack_into('<I', self.data, e['off_at'], off)
            e['off'] = off
        struct.pack_into('<q', self.data, e['csize_at'], len(new))
        if e['usize_at'] is not None:
            struct.pack_into('<q', self.data, e['usize_at'], len(new))
        e['size'] = len(new)

    def compact(self):
        """put 换大文件是追加到末尾、旧数据留在原处：改得多了包里大半是没人指向的旧数据（2026-11-10 高难 regulation 解压 906 MB，
        有用的只有 93 MB，开机黑屏长了半分钟）。写出前按原来的顺序把每个文件紧挨着重排（16 字节对齐），文件头区原样保留"""
        es = sorted(self.entries.values(), key=lambda e: e['first'])
        start = min(e['first'] for e in es)
        out = bytearray(self.data[:start])
        for e in es:
            while len(out) % 16:
                out.append(0)
            off = len(out)
            out += self.data[e['off']:e['off'] + e['size']]
            if self.long_off:
                struct.pack_into('<q', out, e['off_at'], off)
            else:
                struct.pack_into('<I', out, e['off_at'], off)
            e['off'] = off
        self.data = out


# ---------------------------------------------------------------- BND4 整个重写（0x74 格式：Unicode 名字、编号、带路径哈希表；
# 原版特效包、菜单布局包都是这种。Bnd4 只能就地换文件，要加文件时用这里的读 / 写）
def path_hash(name):
    s = name.strip().replace('\\', '/').lower()
    if not s.startswith('/'):
        s = '/' + s
    h = 0
    for ch in s:
        h = (h * 37 + ord(ch)) & 0xFFFFFFFF
    return h


def is_prime(p):
    if p < 2:
        return False
    if p % 2 == 0:
        return p == 2
    return all(p % i for i in range(3, int(p ** 0.5) + 1, 2))


def write_bnd4(files, head=b'BND4\0\0\0\0\0\0\x01\0', version=b'07D7R6\0\0'):
    """files：[(编号, 完整名字, 数据)] → BND4 字节（文件头 36 字节：标记 0x40、未压缩大小、32 位偏移、编号、名字偏移）"""
    n = len(files)
    out = bytearray(head + struct.pack('<iq', n, 0x40) + version + struct.pack('<qq', 36, 0) + bytes([1, 0x74, 4, 0]) + bytes(4) + bytes(8))
    hdr = []
    for fid, name, data in files:
        hdr.append(len(out))
        out += struct.pack('<B3xiqqIiI', 0x40, -1, len(data), len(data), 0, fid, 0)
    for at, (fid, name, data) in zip(hdr, files):
        struct.pack_into('<I', out, at + 32, len(out))
        out += name.encode('utf-16le') + b'\0\0'
    while len(out) % 8:
        out.append(0)
    struct.pack_into('<q', out, 0x38, len(out))     # 哈希表
    groups = next(p for p in range(n // 7, 100001) if is_prime(p))
    lists = [[] for _ in range(groups)]
    for i, (_, name, _) in enumerate(files):
        h = path_hash(name)
        lists[h % groups].append((h, i))
    at = len(out)
    out += struct.pack('<qIBBBB', 0, groups, 16, 8, 8, 0)
    k = 0
    for lst in lists:
        lst.sort()
        out += struct.pack('<ii', len(lst), k)
        k += len(lst)
    struct.pack_into('<q', out, at, len(out))
    for lst in lists:
        for h, i in lst:
            out += struct.pack('<Ii', h, i)
    struct.pack_into('<q', out, 0x28, len(out))     # 文件头部分结束
    for at, (fid, name, data) in zip(hdr, files):
        while data and len(out) % 16:               # 空文件不对齐（原版写法）
            out.append(0)
        struct.pack_into('<I', out, at + 24, len(out))
        out += data
    return bytes(out)


def read_bnd4_full(raw):
    """→ [(编号, 完整名字, 数据)]（按文件头顺序；本工具的写法只认 0x74 格式）"""
    b = Bnd4(raw)
    if raw[0x31] != 0x74 or b.hdr_size != 36:
        raise ValueError('不是 0x74 格式的 BND4')
    files = []
    for k in range(b.count):
        at = 0x40 + 36 * k
        size, off, fid, noff = struct.unpack_from('<qxxxxxxxxIiI', raw, at + 8)
        e = noff
        while raw[e:e + 2] != b'\0\0':
            e += 2
        files.append((fid, raw[noff:e].decode('utf-16le'), raw[off:off + size]))
    return files


# ---------------------------------------------------------------- 游戏打包数据（Data*.bhd / .bdt，只读）
def _pem_rsa(pem):
    """PEM 的 RSA 公钥（PKCS#1：SEQUENCE { n, e }）→ (n, e)"""
    import base64
    der = base64.b64decode(''.join(l for l in pem.splitlines() if l and not l.startswith('-----')))

    def read(b, p):
        ln, p = b[p + 1], p + 2
        if ln & 0x80:
            k = ln & 0x7F
            ln, p = int.from_bytes(b[p:p + k], 'big'), p + k
        return b[p:p + ln], p + ln
    seq, _ = read(der, 0)
    n, p = read(seq, 0)
    e, _ = read(seq, p)
    return int.from_bytes(n, 'big'), int.from_bytes(e, 'big')


def er_path_hash(path):
    """ER 打包数据的文件名哈希（64 位，小写、正斜杠，质数 0x85）"""
    h = 0
    for ch in path.lower().replace('\\', '/'):
        h = (h * 0x85 + ord(ch)) & 0xFFFFFFFFFFFFFFFF
    return h


class GameArchive:
    """一个 Data*.bhd / .bdt：.bhd 用 RSA 公钥逐块解开（每 256 字节解出 255 字节），按 BHD5 的哈希桶找文件；
    文件内容里列出的段用 AES-128-ECB 解。只读，不改游戏文件"""

    def __init__(self, bhd_path, pem):
        n, e = _pem_rsa(pem)
        size = (n.bit_length() + 7) // 8
        enc = open(bhd_path, 'rb').read()
        out = bytearray()
        for k in range(0, len(enc), size):
            out += pow(int.from_bytes(enc[k:k + size], 'big'), e, n).to_bytes(size, 'big')[1:]
        if out[:4] != b'BHD5':
            raise ValueError('%s 解不开（公钥不对？）' % bhd_path)
        self.bhd, self.bdt = bytes(out), bhd_path[:-4] + '.bdt'

    def entry(self, path):
        b, want = self.bhd, er_path_hash(path)
        buckets, at = struct.unpack_from('<ii', b, 0x10)
        count, hdr = struct.unpack_from('<ii', b, at + 8 * (want % buckets))
        for k in range(count):
            h, padded, unpadded, off, _sha, aes = struct.unpack_from('<Qiiqqq', b, hdr + 40 * k)
            if h == want:
                key, ranges = None, []
                if aes:
                    key = b[aes:aes + 16]
                    n = struct.unpack_from('<i', b, aes + 16)[0]
                    ranges = [struct.unpack_from('<qq', b, aes + 20 + 16 * r) for r in range(n)]
                return dict(size=unpadded or padded, padded=padded, off=off, key=key, ranges=ranges)
        return None

    def read(self, path):
        e = self.entry(path)
        if e is None:
            raise FileNotFoundError('打包数据里没有 %s' % path)
        with open(self.bdt, 'rb') as f:
            f.seek(e['off'])
            data = bytearray(f.read(e['padded']))
        for s, t in e['ranges']:
            if 0 <= s < t:
                data[s:t] = _aes_cbc(e['key'], None, bytes(data[s:t]), False, chain='ChainingModeECB')
        return bytes(data[:e['size']])


# ---------------------------------------------------------------- TPF（PC 平台的贴图包）
def read_tpf(raw):
    """→ dict(flag2, enc, tex=[dict(name, fmt, type, mips, flags1, flags2, data=DDS 文件)])"""
    if raw[:4] != b'TPF\0' or raw[12] != 0:
        raise ValueError('不是 PC 平台的 TPF')
    count, flag2, enc = struct.unpack_from('<i', raw, 8)[0], raw[13], raw[14]
    tex = []
    for k in range(count):
        off, size, fmt, typ, mips, fl1, noff, fl2 = struct.unpack_from('<IiBBBBIi', raw, 16 + 20 * k)
        if enc == 1:
            e = noff
            while raw[e:e + 2] != b'\0\0':
                e += 2
            name = raw[noff:e].decode('utf-16le')
        else:
            name = raw[noff:raw.index(b'\0', noff)].decode('shift_jis')
        tex.append(dict(name=name, fmt=fmt, type=typ, mips=mips, flags1=fl1, flags2=fl2, data=raw[off:off + size]))
    return dict(flag2=flag2, enc=enc, tex=tex)


def write_tpf(t):
    count = len(t['tex'])
    names, offs = bytearray(), []
    for x in t['tex']:
        offs.append(16 + 20 * count + len(names))
        names += x['name'].encode('utf-16le') + b'\0\0' if t['enc'] == 1 else x['name'].encode('shift_jis') + b'\0'
    pos = (16 + 20 * count + len(names) + 15) // 16 * 16
    entries, body = bytearray(), bytearray()
    for x, no in zip(t['tex'], offs):
        entries += struct.pack('<IiBBBBIi', pos + len(body), len(x['data']), x['fmt'], x['type'], x['mips'], x['flags1'], no, x['flags2'])
        body += x['data']                       # 原版各贴图紧挨着放，只有第一张对齐 16
    head = b'TPF\0' + struct.pack('<ii', sum(len(x['data']) for x in t['tex']), count) + bytes([0, t['flag2'], t['enc'], 0])
    out = bytearray(head + entries + names)
    out += bytes(pos - len(out))
    return bytes(out + body)


# ---------------------------------------------------------------- PARAM（ER，长偏移格式）
class Param:
    def __init__(self, data):
        b = bytes(data)
        self.head = bytearray(b[:0x40])
        f2d = b[0x2D]
        if not (f2d & 0x04) or not (f2d & 0x80):
            raise ValueError('只支持 ER 的长偏移 PARAM（Format2D=0x%02X）' % f2d)
        n = struct.unpack_from('<H', b, 0x0A)[0]
        pto = struct.unpack_from('<q', b, 0x10)[0]
        self.param_type = b[pto:b.index(b'\0', pto)]
        self.unicode_names = bool(b[0x2E] & 1)
        rows = []
        for i in range(n):
            rid, _pad, doff, noff = struct.unpack_from('<iiqq', b, 0x40 + 24 * i)
            rows.append((rid, doff, noff))
        if n > 1:
            self.row_size = rows[1][1] - rows[0][1]
        else:
            self.row_size = pto - rows[0][1] if n else 0
        self.ids = []
        self.rows = {}
        self.names = {}
        for rid, doff, noff in rows:
            self.ids.append(rid)
            self.rows[rid] = bytearray(b[doff:doff + self.row_size])
            self.names[rid] = self._read_name(b, noff)

    def _read_name(self, b, noff):
        if noff <= 0 or noff >= len(b):
            return b''
        if self.unicode_names:
            e = noff
            while b[e:e + 2] != b'\0\0':
                e += 2
            return b[noff:e]
        return b[noff:b.index(b'\0', noff)]

    def add_row(self, rid, data, name=b''):
        if rid in self.rows:
            raise KeyError('行 %d 已存在' % rid)
        if len(data) != self.row_size:
            raise ValueError('行大小不对')
        self.rows[rid] = bytearray(data)
        self.names[rid] = name
        self.ids.append(rid)

    def del_row(self, rid):
        del self.rows[rid]
        self.names.pop(rid, None)
        self.ids.remove(rid)

    def serialize(self):
        ids = sorted(self.ids)
        n = len(ids)
        if n > 0xFFFF:
            raise ValueError('行数超过 65535')
        data_start = 0x40 + 24 * n
        strings = data_start + n * self.row_size
        out = bytearray(self.head)
        struct.pack_into('<I', out, 0x00, strings)
        struct.pack_into('<H', out, 0x0A, n)
        struct.pack_into('<q', out, 0x10, strings)
        struct.pack_into('<q', out, 0x30, data_start)
        # 名字区：先写 param type，再按首次出现顺序写去重后的名字
        name_blob = bytearray(self.param_type + b'\0')
        term = b'\0\0' if self.unicode_names else b'\0'
        name_off = {}
        for rid in ids:
            nm = self.names.get(rid, b'')
            if nm not in name_off:
                name_off[nm] = strings + len(name_blob)
                name_blob += nm + term
        hdrs = bytearray()
        for i, rid in enumerate(ids):
            hdrs += struct.pack('<iiqq', rid, 0, data_start + i * self.row_size, name_off[self.names.get(rid, b'')])
        body = bytearray()
        for rid in ids:
            body += self.rows[rid]
        # 原文件末尾多 2 个 0 字节，照抄以便逐字节往返一致
        return bytes(out + hdrs + body + name_blob + b'\0\0')


# ---------------------------------------------------------------- ItemLotParam 字段（ER 1.17，行 152 字节）
LOT_ID = 0          # s32 × 8
LOT_CAT = 32        # s32 × 8
LOT_PT = 64         # u16 × 8
LOT_SLOTFLAG = 96   # u32 × 8
LOT_FLAG = 128      # u32
LOT_NUM = 138       # u8 × 8
LOT_LUCK = 146      # u16 位域：低 8 位 = enableLuck01..08


def lot_slots(row):
    """返回 [(i, category, itemId, point)]（point>0 或 itemId!=0 的格子）。"""
    out = []
    for i in range(8):
        iid = struct.unpack_from('<i', row, LOT_ID + 4 * i)[0]
        cat = struct.unpack_from('<i', row, LOT_CAT + 4 * i)[0]
        pt = struct.unpack_from('<H', row, LOT_PT + 2 * i)[0]
        if iid or pt:
            out.append((i, cat, iid, pt))
    return out


def lot_set_slot(row, i, cat, iid, pt, num=1, luck=None, slotflag=None):
    struct.pack_into('<i', row, LOT_ID + 4 * i, iid)
    struct.pack_into('<i', row, LOT_CAT + 4 * i, cat)
    struct.pack_into('<H', row, LOT_PT + 2 * i, pt)
    row[LOT_NUM + i] = num
    if slotflag is not None:
        struct.pack_into('<I', row, LOT_SLOTFLAG + 4 * i, slotflag)
    if luck is not None:
        v = struct.unpack_from('<H', row, LOT_LUCK)[0]
        v = (v | (1 << i)) if luck else (v & ~(1 << i))
        struct.pack_into('<H', row, LOT_LUCK, v)


def lot_clear_slot(row, i):
    lot_set_slot(row, i, 0, 0, 0, num=0, luck=False, slotflag=0)


def lot_flag(row):
    return struct.unpack_from('<I', row, LOT_FLAG)[0]


# ---------------------------------------------------------------- FMG / msgbnd
def _u16end(b, so):
    """从 so 开始的 UTF-16 字符串结尾（双零字节、且和 so 同奇偶对齐）"""
    e = b.find(b'\0\0', so)
    while e >= 0 and (e - so) % 2:
        e = b.find(b'\0\0', e + 1)
    return e if e >= 0 else len(b)


def read_fmg(b):
    count_groups = struct.unpack_from('<i', b, 0x0C)[0]
    str_off_off = struct.unpack_from('<q', b, 0x18)[0]
    out = {}
    p = 0x28
    for _ in range(count_groups):
        off_idx, first, last, _pad = struct.unpack_from('<iiii', b, p)
        p += 16
        for k, tid in enumerate(range(first, last + 1)):
            so = struct.unpack_from('<q', b, str_off_off + (off_idx + k) * 8)[0]
            if so:
                out[tid] = b[so:_u16end(b, so)].decode('utf-16le')
    return out


def read_fmg_full(b):
    """读 FMG，保留表头，返回 (header0x28, [(id, text 或 None)])，顺序同原文件。"""
    count_groups = struct.unpack_from('<i', b, 0x0C)[0]
    str_off_off = struct.unpack_from('<q', b, 0x18)[0]
    out = []
    p = 0x28
    for _ in range(count_groups):
        off_idx, first, last, _pad = struct.unpack_from('<iiii', b, p)
        p += 16
        for k, tid in enumerate(range(first, last + 1)):
            so = struct.unpack_from('<q', b, str_off_off + (off_idx + k) * 8)[0]
            if so:
                out.append((tid, b[so:_u16end(b, so)].decode('utf-16le')))
            else:
                out.append((tid, None))
    return bytes(b[:0x28]), out


def write_fmg(header, entries):
    """按 ER 的 FMG v2 格式写回：连续的 ID 合成一组，字符串按 ID 顺序 UTF-16 存放。
    一模一样的 #DRC 占位（dark_core 改写的，骨灰容器各级共用一个）只存一份、几个 ID 指同一处；原版文字不合并。"""
    entries = sorted(entries, key=lambda kv: kv[0])
    groups = []
    for k, (tid, _) in enumerate(entries):
        if groups and tid == groups[-1][2] + 1:
            groups[-1][2] = tid
        else:
            groups.append([k, tid, tid])
    n = len(entries)
    str_off_off = 0x28 + 16 * len(groups)
    pos = str_off_off + 8 * n
    offs, blob, shared = [], bytearray(), {}
    for tid, text in entries:
        if text is None:
            offs.append(0)
        elif text.startswith('#DRC') and text in shared:
            offs.append(shared[text])
        else:
            offs.append(pos + len(blob))
            if text.startswith('#DRC'):
                shared[text] = offs[-1]
            blob += text.encode('utf-16le') + b'\0\0'
    out = bytearray(header)
    struct.pack_into('<i', out, 0x04, pos + len(blob))
    struct.pack_into('<i', out, 0x0C, len(groups))
    struct.pack_into('<i', out, 0x10, n)
    struct.pack_into('<q', out, 0x18, str_off_off)
    for k, first, last in groups:
        out += struct.pack('<iiii', k, first, last, 0)
    for o in offs:
        out += struct.pack('<q', o)
    out += blob
    return bytes(out)


def _shrink_bnd(raw):
    """BND4 里 put 追加留下的旧数据超过 1 MB 就整理掉（文字包被二十来个步骤依次改，2026-11-10 中文 item_dlc02 解压 147 MB、有用 38 MB）"""
    if raw[:4] != b'BND4':
        return raw
    try:
        b = Bnd4(raw)
        used = sum(e['size'] for e in b.entries.values())
        if len(raw) - used < (1 << 20) or len(b.entries) != b.count:
            return raw
        b.compact()
        return bytes(b.data)
    except Exception:
        return raw


def _write_dcx_now(path, raw, level=6):
    data = dcx_compress_dflt(_shrink_bnd(raw), level)
    dcx_check_strict(data)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def write_dcx_file(path, raw, level=6):
    """写 DCX 文件。defer_writes() 打开时先放内存（后面的步骤用 read_dcx / dcx_exists 读到的就是它），
    flush_writes() 时再一起并行压缩写盘：同一个文字包被好几个步骤改来改去时，只压缩最后那一版"""
    if _PENDING is not None:
        _PENDING[os.path.normcase(os.path.abspath(path))] = (path, bytes(raw), level)
        return
    _write_dcx_now(path, raw, level)


def read_dcx(path):
    """读 DCX 文件（解压后）；延迟写出里有这个路径就直接用内存里的"""
    if _PENDING is not None:
        hit = _PENDING.get(os.path.normcase(os.path.abspath(path)))
        if hit is not None:
            return hit[1]
    return dcx_decompress(open(path, 'rb').read())


def dcx_exists(path):
    return (_PENDING is not None and os.path.normcase(os.path.abspath(path)) in _PENDING) or os.path.isfile(path)


def pending_under(folder):
    pre = os.path.join(os.path.normcase(os.path.abspath(folder)), '')
    return _PENDING is not None and any(k.startswith(pre) for k in _PENDING)


def discard_writes(folder):
    """丢掉 folder 下还没写出的文件（那个目录要整个删掉时）"""
    pre = os.path.join(os.path.normcase(os.path.abspath(folder)), '')
    if _PENDING is not None:
        for k in [k for k in _PENDING if k.startswith(pre)]:
            del _PENDING[k]


def defer_writes(on=True):
    global _PENDING
    _PENDING = {} if on else None


def _dcx_job(args):
    path, raw, level = args
    _write_dcx_now(path, raw, level)
    return path


def flush_writes(jobs=None, while_waiting=None):
    """把延迟写出的文件并行压缩写盘（大的先做）；while_waiting 在主进程里同时做（比如写 regulation）。返回写了几个"""
    global _PENDING
    todo = sorted((_PENDING or {}).values(), key=lambda x: -len(x[1]))
    _PENDING = None
    pmap(_dcx_job, todo, jobs, while_waiting=while_waiting)
    return len(todo)


def read_msgbnd(path, wanted=None):
    bnd = Bnd4(read_dcx(path))
    res = {}
    for short in bnd.entries:
        key = short.replace('.fmg', '')
        if wanted is None or key in wanted:
            res[key] = read_fmg(bnd.get(short))
    return res


# ---------------------------------------------------------------- MSB（地图）：敌人摆放
def _u16str(b, o):
    e = o
    while b[e:e + 2] != b'\0\0':
        e += 2
    return bytes(b[o:e]).decode('utf-16le')


def msb_enemy_parts(raw):
    """解压后的 MSBE：返回 [(实体ID, NpcParamID, NpcParamID 字段在文件里的绝对偏移)]（只看 Enemy 类型的 part）。"""
    if raw[:4] != b'MSB ':
        raise ValueError('不是 MSB')
    out = []
    pos = 0x10
    while pos:
        cnt = struct.unpack_from('<i', raw, pos + 4)[0]
        noff = struct.unpack_from('<q', raw, pos + 8)[0]
        offs = struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16)
        nxt = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
        if _u16str(raw, noff) == 'PARTS_PARAM_ST':
            for o in offs:
                typ = struct.unpack_from('<i', raw, o + 12)[0]
                if typ != 2:
                    continue
                ptrs = struct.unpack_from('<11q', raw, o + 0x50)
                ent = struct.unpack_from('<I', raw, o + ptrs[2])[0]
                at = o + ptrs[3] + 12
                out.append((ent, struct.unpack_from('<i', raw, at)[0], at))
            return out
        pos = nxt
    return out


# ---------------------------------------------------------------- 存档：找出拥有的装备
def owned_items(save_path, weapon_ids, armor_ids, talisman_ids):
    """只读解析 .sl2/.cnv/.rng：所有角色合起来拥有的武器 / 防具 / 护符。返回三个集合。"""
    ws, ps, ts = set(), set(), set()
    for _slot, w, p, t in owned_items_by_slot(save_path, weapon_ids, armor_ids, talisman_ids):
        ws |= w
        ps |= p
        ts |= t
    return ws, ps, ts


def save_profiles(save_path):
    """存档里各角色格（0-9）的名字和等级（USER_DATA010 的角色摘要）。返回 {格号: (名字, 等级)}，只含在用的格子。"""
    raw = open(save_path, 'rb').read()
    e = Bnd4(raw).entries.get('USER_DATA010')
    if not e:
        return {}
    body = raw[e['off'] + 16:e['off'] + e['size']]
    out = {}
    for k in range(10):
        if not body[0x1954 + k]:
            continue
        o = 0x195E + k * 0x24C
        name = body[o:o + 0x22].decode('utf-16le', 'replace').split('\x00')[0]
        out[k] = (name, struct.unpack_from('<I', body, o + 0x22)[0])
    return out


def save_stats(save_path):
    """各角色格的属性：{格号: {'name', 'level', 'stats': (生命, 集中, 耐力, 力气, 灵巧, 智力, 信仰, 感应), 'data': 这一格的原始数据}}。
    属性是角色名字（UTF-16）前 0x60 处的 8 个 u32，再往后 0x2C 是等级：名字可能在格子里出现好几次，等级对得上的才算。"""
    raw = open(save_path, 'rb').read()
    b = Bnd4(raw)
    out = {}
    for k, (name, lvl) in save_profiles(save_path).items():
        e = b.entries.get('USER_DATA%03d' % k)
        if not e or not name:
            continue
        body = raw[e['off'] + 16:e['off'] + e['size']]
        nb = name.encode('utf-16le') + b'\0\0'
        i = body.find(nb)
        while i != -1:
            if i >= 0x60:
                vals = struct.unpack_from('<8I', body, i - 0x60)
                if all(1 <= v <= 99 for v in vals) and struct.unpack_from('<I', body, i - 0x60 + 0x2C)[0] == lvl:
                    out[k] = {'name': name, 'level': lvl, 'stats': vals, 'data': body}
                    break
            i = body.find(nb, i + 1)
    return out


def owned_items_by_slot(save_path, weapon_ids, armor_ids, talisman_ids):
    """按角色格（0-9，对应 USER_DATA000-009）分别读：物品实例表（武器/防具）+ 背包里的护符。
    返回 [(格号, 武器集合, 防具集合, 护符集合)]，空格子跳过。"""
    raw = open(save_path, 'rb').read()
    bnd = Bnd4(raw)
    out = []
    for short, e in sorted(bnd.entries.items()):
        if not short.startswith('USER_DATA0') or short in ('USER_DATA010', 'USER_DATA011'):
            continue
        body = raw[e['off'] + 16:e['off'] + e['size']]
        if not any(body[:0x40]):
            continue
        ws, ps, ts = set(), set(), set()
        ver = struct.unpack_from('<I', body, 0)[0]
        n = 0x1400 if ver > 81 else 0x13FE
        off = 0x20
        for _ in range(n):
            h, iid = struct.unpack_from('<II', body, off)
            t = h & 0xF0000000
            if h and t == 0x80000000:
                base = iid - iid % 10000
                if base in weapon_ids:
                    ws.add(base)
                off += 21
            elif h and t == 0x90000000:
                if (iid ^ 0x10000000) in armor_ids:
                    ps.add(iid ^ 0x10000000)
                off += 16
            else:
                off += 8
        # 背包紧接在物品实例表后面，按表尾的实际位置对齐（武器条目 21 字节，表尾通常不是 4 的倍数，
        # 不能再对齐到 4 的倍数，否则整段错开、护符一件都读不到）
        end = off
        for o in range(end, len(body) - 8, 4):
            v, q = struct.unpack_from('<II', body, o)
            if v >> 28 == 0xA and q == 1 and (v & 0x0FFFFFFF) in talisman_ids:
                ts.add(v & 0x0FFFFFFF)
        out.append((int(short[-3:]), ws, ps, ts))
    return out
