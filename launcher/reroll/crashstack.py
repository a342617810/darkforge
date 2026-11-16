# -*- coding: utf-8 -*-
"""诊断包用：从游戏的崩溃转储（%LOCALAPPDATA%\\CrashDumps\\eldenring.exe.<进程号>.dmp，约 55 MB）里取出排查要的那一小部分，
写成文本放进诊断包，不用再单独发转储：
  - 异常：异常码、位置（模块+偏移）、访问错误时读 / 写的地址；
  - 出错线程的寄存器（指到模块里的标出模块+偏移）；
  - 调用栈：按各模块文件里的 .pdata 展开（x64 的展开信息）；展开断了（钩子跳板、没有 .pdata 的代码）还有下面的扫描；
  - 栈上像返回地址的值：从 rsp 往上扫，落在模块代码里、前面紧挨着一条 call 的；
  - 模块清单（基址、大小、时间戳、版本、路径）和其他线程当前停在哪。
模块的 .pdata 和代码字节从本机磁盘上的模块文件读（时间戳对不上就不用）。只读转储和模块文件，不改任何东西。
退出游戏时那种没影响的崩溃只记一行；完整写出的最多 MAX_FULL 份（按给的顺序）。
用法：python crashstack.py 输出.txt 转储1 [转储2 ...]"""
import bisect
import datetime
import mmap
import os
import struct
import sys

EXC_NAMES = {
    0xC0000005: '内存访问错误', 0x80000003: '断点（int3，多是程序自己的断言）', 0xC0000409: '栈缓冲区溢出 / 快速失败',
    0xC00000FD: '栈溢出', 0xC000001D: '非法指令', 0xC0000094: '整数除以零', 0xC0000374: '堆损坏', 0xE06D7363: 'C++ 异常',
}
REGS = ['rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']
MAX_FRAMES = 40
MAX_SCAN = 60
SCAN_BYTES = 0x10000
MAX_FULL = 3              # 完整写出的转储最多几份
EXIT_CRASH = {0x1ebb809: '2.7.1.0', 0x1ebcef9: '2.7.2.0'}   # 退出时必崩的位置（DL_PANIC，存档已写完），只记一行


class Dump:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        if self.m[:4] != b'MDMP':
            raise ValueError('不是 minidump')
        n, rva = struct.unpack_from('<II', self.m, 8)
        self.time = struct.unpack_from('<I', self.m, 20)[0]
        self.streams = {}
        for i in range(n):
            t, size, at = struct.unpack_from('<III', self.m, rva + i * 12)
            self.streams.setdefault(t, (at, size))
        self.ranges = []   # (起始地址, 长度, 文件偏移)
        if 5 in self.streams:
            at = self.streams[5][0]
            for i in range(struct.unpack_from('<I', self.m, at)[0]):
                start, size, off = struct.unpack_from('<QII', self.m, at + 4 + i * 16)
                self.ranges.append((start, size, off))
        if 9 in self.streams:
            at = self.streams[9][0]
            cnt, off = struct.unpack_from('<QQ', self.m, at)
            for i in range(cnt):
                start, size = struct.unpack_from('<QQ', self.m, at + 16 + i * 16)
                self.ranges.append((start, size, off))
                off += size
        self.ranges.sort()
        self.starts = [r[0] for r in self.ranges]
        self.modules = self._modules()
        self.mod_bases = [m['base'] for m in self.modules]

    def text(self, rva):
        n = struct.unpack_from('<I', self.m, rva)[0]
        return self.m[rva + 4:rva + 4 + n].decode('utf-16-le', 'replace')

    def read(self, addr, n):
        i = bisect.bisect_right(self.starts, addr) - 1
        if i < 0:
            return None
        start, size, off = self.ranges[i]
        if addr + n > start + size:
            return None
        return self.m[off + addr - start:off + addr - start + n]

    def q(self, addr):
        b = self.read(addr, 8)
        return struct.unpack('<Q', b)[0] if b else None

    def _modules(self):
        out = []
        if 4 not in self.streams:
            return out
        at = self.streams[4][0]
        for i in range(struct.unpack_from('<I', self.m, at)[0]):
            e = at + 4 + i * 108
            base, size, _, ts, name = struct.unpack_from('<QIIII', self.m, e)
            ms, ls = struct.unpack_from('<II', self.m, e + 24 + 8)
            path = self.text(name)
            out.append({'base': base, 'size': size, 'ts': ts, 'path': path, 'name': os.path.basename(path),
                        'ver': f'{ms >> 16}.{ms & 0xffff}.{ls >> 16}.{ls & 0xffff}', 'pe': None})
        out.sort(key=lambda m: m['base'])
        return out

    def module(self, addr):
        i = bisect.bisect_right(self.mod_bases, addr) - 1
        if i >= 0 and addr < self.modules[i]['base'] + self.modules[i]['size']:
            return self.modules[i]
        return None

    def where(self, addr):
        m = self.module(addr)
        return f'{m["name"]}+{addr - m["base"]:#x}' if m else f'{addr:#x}'

    def threads(self):
        out = []
        if 3 not in self.streams:
            return out
        at = self.streams[3][0]
        for i in range(struct.unpack_from('<I', self.m, at)[0]):
            tid, _, _, _, teb, stk, stk_size, stk_rva, ctx_size, ctx_rva = struct.unpack_from('<IIIIQQIIII', self.m, at + 4 + i * 48)
            out.append({'tid': tid, 'stack': (stk, stk_size), 'ctx': self.context(ctx_rva, ctx_size)})
        return out

    def context(self, rva, size):
        if size < 0x100:
            return None
        regs = dict(zip(REGS, struct.unpack_from('<16Q', self.m, rva + 0x78)))
        regs['rip'] = struct.unpack_from('<Q', self.m, rva + 0xF8)[0]
        return regs

    def exception(self):
        if 6 not in self.streams:
            return None
        at = self.streams[6][0]
        tid = struct.unpack_from('<I', self.m, at)[0]
        code, flags, _, addr, nparams = struct.unpack_from('<IIQQI', self.m, at + 8)
        params = struct.unpack_from('<15Q', self.m, at + 8 + 32)[:nparams]
        ctx_size, ctx_rva = struct.unpack_from('<II', self.m, at + 8 + 152)
        return {'tid': tid, 'code': code, 'addr': addr, 'params': params, 'ctx': self.context(ctx_rva, ctx_size)}


class PE:
    """磁盘上的模块文件：节表、.pdata、按 RVA 读字节"""
    def __init__(self, path, ts):
        self.ok = False
        try:
            self.f = open(path, 'rb')
            h = self.f.read(0x1000)
            pe = struct.unpack_from('<I', h, 0x3c)[0]
            if h[pe:pe + 4] != b'PE\0\0' or struct.unpack_from('<I', h, pe + 8)[0] != ts:
                return
            nsec, = struct.unpack_from('<H', h, pe + 6)
            opt_size, = struct.unpack_from('<H', h, pe + 20)
            opt = pe + 24
            exc_rva, exc_size = struct.unpack_from('<II', h, opt + 112 + 3 * 8)
            self.secs = []
            for i in range(nsec):
                s = opt + opt_size + i * 40
                vsize, va, rsize, roff = struct.unpack_from('<IIII', h, s + 8)
                chars, = struct.unpack_from('<I', h, s + 36)
                self.secs.append((va, max(vsize, rsize), roff, rsize, bool(chars & 0x20000000)))
            raw = self.read(exc_rva, exc_size) or b''
            self.funcs = [struct.unpack_from('<III', raw, i) for i in range(0, len(raw) - 11, 12)]
            self.funcs.sort()
            self.begins = [fn[0] for fn in self.funcs]
            self.ok = True
        except OSError:
            pass

    def read(self, rva, n):
        for va, size, roff, rsize, _ in self.secs:
            if va <= rva and rva + n <= va + min(size, rsize):
                self.f.seek(roff + rva - va)
                return self.f.read(n)
        return None

    def is_code(self, rva):
        return any(va <= rva < va + size and x for va, size, _, _, x in self.secs)

    def func(self, rva):
        i = bisect.bisect_right(self.begins, rva) - 1
        if i >= 0 and rva < self.funcs[i][1]:
            return self.funcs[i]
        return None


def pe_of(m):
    if m['pe'] is None:
        m['pe'] = PE(m['path'], m['ts'])
    return m['pe'] if m['pe'].ok else None


def after_call(pe, rva):
    """rva 前面紧挨着一条 call（返回地址的样子）"""
    b = pe.read(rva - 7, 7) if rva >= 7 else None
    if not b:
        return False
    return (b[2] == 0xE8                                                   # call rel32
            or (b[1] == 0xFF and (b[2] == 0x15 or 0x90 <= b[2] <= 0x97))   # call [rip+d32] / [r+d32]
            or (b[0] == 0xFF and b[1] == 0x94)                             # call [r+r*s+d32]
            or (b[3] == 0xFF and b[4] == 0x54)                             # call [r+r*s+d8]
            or (b[4] == 0xFF and (0x50 <= b[5] <= 0x57 or b[5] == 0x14))   # call [r+d8] / [r+r*s]
            or (b[5] == 0xFF and (0xD0 <= b[6] <= 0xD7 or 0x10 <= b[6] <= 0x17)))   # call r / [r]


def unwind(d, regs):
    """按 .pdata 展开一帧：返回新的寄存器（rip/rsp 等），展开不了返回 None"""
    rip, rsp = regs['rip'], regs['rsp']
    m = d.module(rip)
    pe = pe_of(m) if m else None
    if not pe:
        return None
    rva = rip - m['base']
    fn = pe.func(rva)
    regs = dict(regs)
    if fn:
        first = True
        while fn:
            info = pe.read(fn[2], 4)
            if not info:
                return None
            flags, prolog, count, fr = info[0] >> 3, info[1], info[2], info[3]
            codes = pe.read(fn[2] + 4, count * 2) or b''
            pos = rva - fn[0]
            in_prolog = first and pos < prolog
            # 帧寄存器已经设好（不在序言里，或序言里 SET_FPREG 已经执行）：栈帧基址按它算
            fp_set = fr & 0xF and (not in_prolog or any(codes[j * 2 + 1] & 0xF == 3 and codes[j * 2] <= pos for j in range(count)))
            if fp_set:
                regs['rsp'] = regs[REGS[fr & 0xF]] - (fr >> 4) * 16
            base = regs['rsp']
            i = 0
            while i < count:
                off, op, inf = codes[i * 2], codes[i * 2 + 1] & 0xF, codes[i * 2 + 1] >> 4
                slots = {1: 2 if inf == 0 else 3, 4: 2, 5: 3, 6: 2, 7: 3, 8: 2, 9: 3}.get(op, 1)
                if in_prolog and off > pos:
                    i += slots
                    continue
                if op == 0:
                    v = d.q(regs['rsp'])
                    if v is None:
                        return None
                    regs[REGS[inf]] = v
                    regs['rsp'] += 8
                elif op == 1:
                    regs['rsp'] += (struct.unpack_from('<H', codes, i * 2 + 2)[0] * 8 if inf == 0
                                    else struct.unpack_from('<I', codes, i * 2 + 2)[0])
                elif op == 2:
                    regs['rsp'] += inf * 8 + 8
                elif op in (4, 5):
                    o = struct.unpack_from('<H', codes, i * 2 + 2)[0] * 8 if op == 4 else struct.unpack_from('<I', codes, i * 2 + 2)[0]
                    v = d.q(base + o)
                    if v is not None:
                        regs[REGS[inf]] = v
                elif op == 10:
                    sp = regs['rsp'] + (8 if inf else 0)
                    rip2, rsp2 = d.q(sp), d.q(sp + 24)
                    if rip2 is None or rsp2 is None:
                        return None
                    regs['rip'], regs['rsp'] = rip2, rsp2
                    return regs
                i += slots
            if flags & 4:   # 接着处理链上的展开信息
                n = (count + 1) & ~1
                ch = pe.read(fn[2] + 4 + n * 2, 12)
                fn = struct.unpack('<III', ch) if ch else None
                first = False
            else:
                fn = None
    ret = d.q(regs['rsp'])
    if ret is None:
        return None
    regs['rip'] = ret
    regs['rsp'] += 8
    return regs


SYSTEM = {'ntdll.dll', 'kernelbase.dll', 'kernel32.dll', 'win32u.dll', 'user32.dll'}


def owner(d, regs):
    """线程停的位置，和往上第一处不在系统 DLL 里的调用者"""
    leaf, r = d.where(regs['rip']), regs
    for _ in range(12):
        m = d.module(r['rip'])
        if not m or m['name'].lower() not in SYSTEM:
            return leaf, d.where(r['rip'])
        r = unwind(d, r)
        if not r or r['rip'] == 0:
            break
    return leaf, None


def report(path):
    d = Dump(path)
    st = os.stat(path)
    out = [f'==== 崩溃转储 {os.path.basename(path)}（{datetime.datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}，{st.st_size / 1048576:.1f} MB）']
    exc = d.exception()
    threads = d.threads()
    if not exc:
        out.append('转储里没有异常记录。')
        return out
    exe = next((m for m in d.modules if m['name'].lower() == 'eldenring.exe'), None)
    if exe and exc['addr'] - exe['base'] in EXIT_CRASH:
        return None
    code = exc['code']
    line = f'异常：{code:#010x} {EXC_NAMES.get(code, "")}'
    if code == 0xC0000005 and len(exc['params']) >= 2:
        kind = {0: '读', 1: '写', 8: '执行'}.get(exc['params'][0], f'类型 {exc["params"][0]}')
        line += f'（{kind}地址 {exc["params"][1]:#x}）'
    out.append(line)
    out.append(f'位置：{d.where(exc["addr"])}　线程 {exc["tid"]}')
    regs = exc['ctx'] or next((t['ctx'] for t in threads if t['tid'] == exc['tid']), None)
    if not regs:
        out.append('出错线程没有寄存器记录。')
        return out
    out.append('')
    out.append('寄存器：')
    for k in REGS + ['rip']:
        v = regs[k]
        out.append(f'  {k:<4}{v:016x}' + (f'  {d.where(v)}' if d.module(v) else ''))
    out.append('')
    out.append('调用栈（按模块的 .pdata 展开）：')
    r = regs
    for i in range(MAX_FRAMES):
        m = d.module(r['rip'])
        out.append(f'  #{i:<2} {d.where(r["rip"]):<36} rsp={r["rsp"]:#x}')
        nxt = unwind(d, r)
        if nxt is None:
            why = '不在任何模块里' if not m else '模块文件读不到或时间戳不同' if not pe_of(m) else '栈读不到'
            out.append(f'  （展开到这里断了：{why}，接着看下面的扫描）')
            break
        if nxt['rip'] == 0:
            out.append('  （到底了）')
            break
        if nxt['rsp'] <= r['rsp']:
            out.append('  （展开信息对不上，后面不可信，接着看下面的扫描）')
            break
        r = nxt
    out.append('')
    out.append(f'栈上像返回地址的值（从 rsp 往上 {SCAN_BYTES // 1024} KB，落在模块代码里、前面是 call 的，最多 {MAX_SCAN} 个）：')
    rsp = regs['rsp']
    stack = next((t['stack'] for t in threads if t['tid'] == exc['tid']), None)
    end = rsp + SCAN_BYTES
    if stack and stack[0] <= rsp < stack[0] + stack[1]:
        end = min(end, stack[0] + stack[1])
    n = 0
    for a in range(rsp, end, 8):
        v = d.q(a)
        if v is None:
            break
        m = d.module(v)
        pe = pe_of(m) if m else None
        if pe and pe.is_code(v - m['base']) and after_call(pe, v - m['base']):
            out.append(f'  rsp+{a - rsp:#06x}  {d.where(v)}')
            n += 1
            if n >= MAX_SCAN:
                break
    if n == 0:
        out.append('  （没有）')
    out.append('')
    out.append('其他线程当前位置（停在系统 DLL 里的，往上找第一处不是系统 DLL 的调用者；相同的合并计数）：')
    groups = {}
    for t in threads:
        if t['ctx'] and t['tid'] != exc['tid']:
            key = owner(d, t['ctx'])
            groups[key] = groups.get(key, 0) + 1
    for (leaf, own), n in sorted(groups.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f'  ×{n:<3} {leaf}' + (f'  ← {own}' if own and own != leaf else ''))
    out.append('')
    out.append('模块：')
    for m in d.modules:
        out.append(f'  {m["base"]:016x} {m["size"]:#010x} {m["ts"]:08x} {m["ver"]:<16} {m["path"]}')
    return out


def main():
    lines, full, skipped = [], 0, []
    for p in sys.argv[2:]:
        if full >= MAX_FULL:
            break
        try:
            r = report(p)
        except Exception as e:   # 一个转储坏了不影响别的
            r = [f'==== {os.path.basename(p)}：读不了（{type(e).__name__}: {e}）']
        if r is None:
            skipped.append(os.path.basename(p))
            continue
        lines += r + ['']
        full += 1
    if skipped:
        lines.append(f'退出游戏时的崩溃（DL_PANIC，没影响）{len(skipped)} 份，略：' + '、'.join(skipped))
    if not lines:
        lines.append('没有转储。')
    with open(sys.argv[1], 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write('\n'.join(lines))


if __name__ == '__main__':
    main()
