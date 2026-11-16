# -*- coding: utf-8 -*-
"""dark_core 的特征码在 2.7.1.0 / 2.7.2.0 两个 exe 上离线核对（照 DLL 里 aob_scan_unique 的逻辑：所有可执行节、要求唯一命中），
连同命中后 DLL 做的附加核对：
  移除物品（gear.rs REMOVE_ITEM_AOB，函数开头 = 命中 - 16）
  补正显示数值（scaling.rs GRADE / LAST / FMT0：「%.0f」字符串、1.0 门槛、改写长度不越过下一种格式）
  本体战斗判断（runtime.rs COMBAT_AOB：call 前面是 mov rcx,[rip+x]）
  拾遗的拾取判断（pickup.rs RVAS + SIG：每个版本的地址有一个对得上整段特征码，同一特征码别处还有命中也列出来）
用法：launcher\\python\\python.exe -X utf8 dev\\vendor\\port_tools\\verify_core.py [旧 exe] [新 exe]"""
import struct
import sys

EXES = sys.argv[1:] or [r'E:\SteamLibrary\steamapps\common\ELDEN RING\Game\eldenring.exe', r'C:\Users\dxphh\ER_new\Game\eldenring.exe']
W = None


def b(x):
    return x


REMOVE_ITEM = [W, 0x83, 0xEC, W, 0x8B, 0xF2, W, 0x8B, 0xE9, W, 0x85, 0xC0, 0x74]
GRADE = [0x66, 0x83, 0xF8, 0x64, 0x0F, 0x85, W, W, W, W, 0x0F, 0x2F, 0x35, W, W, W, W, 0x72, 0x0C,
         0xBA, 0x39, 0x2C, 0x00, 0x00, 0xE8, W, W, W, W, 0xEB, W]
LAST = [0x0F, 0x2F, 0x35, W, W, W, W, 0x0F, 0x82]
FMT0 = [0x48, 0x8D, 0x15, W, W, W, W, 0xE8, W, W, W, W, 0xE9, W, W, W, W, 0x66, 0x83, 0xF8, 0x02]
COMBAT = [0xE8, W, W, W, W, 0x84, 0xC0, 0x75, W, 0x38, 0x83, W, W, W, W, 0x75, W, 0x83, 0xE6, 0xFE]
PICKUP_RVAS = [0xa66f10, 0xa673d0]
PICKUP = [0x48, 0x89, 0x5C, 0x24, 0x08, 0x57, 0x48, 0x81, 0xEC, 0x90, 0x00, 0x00, 0x00, 0x48, 0x8B, 0x84, 0x24, 0xE0, 0x00, 0x00,
          0x00, 0x41, 0x0F, 0xB6, 0xD9, 0x48, 0x8B, 0x0D, W, W, W, W, 0x8B, 0xFA, 0x0F, 0x29, 0xB4, 0x24, 0x80, 0x00, 0x00]
LEN = 39


class Pe:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        pe = struct.unpack_from('<I', self.d, 0x3C)[0]
        nsec, = struct.unpack_from('<H', self.d, pe + 6)
        opt, = struct.unpack_from('<H', self.d, pe + 20)
        self.base, = struct.unpack_from('<Q', self.d, pe + 24 + 24)
        self.secs = []
        for s in range(nsec):
            sh = pe + 24 + opt + 40 * s
            name = self.d[sh:sh + 8].rstrip(b'\0').decode('latin1')
            vsize, va, rsize, raw = struct.unpack_from('<IIII', self.d, sh + 8)
            ch, = struct.unpack_from('<I', self.d, sh + 36)
            self.secs.append((name, va, vsize, raw, rsize, ch))

    def off(self, rva):
        for _n, va, vs, raw, rs, _c in self.secs:
            if va <= rva < va + max(vs, rs):
                return raw + rva - va if rva - va < rs else None
        return None

    def byte(self, rva, n=1):
        o = self.off(rva)
        return None if o is None else self.d[o:o + n]

    def i32(self, rva):
        return struct.unpack('<i', self.byte(rva, 4))[0]

    def match(self, rva, pat):
        bs = self.byte(rva, len(pat))
        return bs is not None and len(bs) == len(pat) and all(p is None or bs[j] == p for j, p in enumerate(pat))

    def scan_unique(self, pat):
        """所有可执行节里找，返回 (rva 列表)；pat 的第一个非通配字节用来加速"""
        k = next(j for j, p in enumerate(pat) if p is not None)
        first = bytes([pat[k]])
        hits = []
        for _n, va, vs, raw, rs, ch in self.secs:
            if not ch & 0x2000_0000:
                continue
            data = self.d[raw:raw + min(vs, rs)]
            i = data.find(first, k)
            while i != -1:
                s = i - k
                if s + len(pat) <= len(data) and all(p is None or data[s + j] == p for j, p in enumerate(pat)):
                    hits.append(va + s)
                    if len(hits) > 1:
                        return hits
                i = data.find(first, i + 1)
        return hits


def target(pe, at, end):
    return end + pe.i32(at)


def check(path):
    pe = Pe(path)
    out = []
    # 移除物品
    h = pe.scan_unique(REMOVE_ITEM)
    out.append(('移除物品', 'OK 函数 %#x' % (h[0] - 16) if len(h) == 1 else '命中 %d 处' % len(h)))
    # 补正显示数值
    h = pe.scan_unique(GRADE)
    if len(h) != 1:
        out.append(('补正数值', '命中 %d 处' % len(h)))
    else:
        g = h[0]
        p = g + 10
        nxt = target(pe, g + 6, g + 10)
        last = next((a for a in range(p, p + 0xA0) if pe.match(a, LAST)), None)
        f = next((a for a in range(g - 1, g - 0x400, -1) if pe.match(a, FMT0)), None)
        if last is None or f is None:
            out.append(('补正数值', '找不到最后一档 / 印整数那段'))
        else:
            one = target(pe, last + 3, last + 7)
            fmt = target(pe, f + 3, f + 7)
            s = pe.byte(fmt, 10)
            onev = struct.unpack('<f', pe.byte(one, 4))[0]
            ok = s == '%.0f\0'.encode('utf-16-le') and p + LEN <= nxt and onev == 1.0
            out.append(('补正数值', ('OK' if ok else '核对不上') + ' 分支 %#x 最后一档 %#x 印整数 %#x' % (g, last, f)))
    # 本体战斗判断
    h = pe.scan_unique(COMBAT)
    if len(h) != 1:
        out.append(('战斗判断', '命中 %d 处' % len(h)))
    else:
        m = h[0]
        mov = pe.byte(m - 7, 3)
        f = target(pe, m + 1, m + 5)
        g = target(pe, m - 4, m)
        ok = mov == b'\x48\x8b\x0d'
        out.append(('战斗判断', ('OK' if ok else 'call 前面不是 mov rcx,[rip+x]') + ' call %#x 函数 %#x 单例指针 %#x' % (m, f, g)))
    # 拾遗的拾取判断（DLL 按版本地址核对，不扫；别处同一特征码的命中只是列出来）
    good = [r for r in PICKUP_RVAS if pe.match(r, PICKUP)]
    out.append(('拾取判断', ('OK %#x' % good[0]) if len(good) == 1 else '版本地址对得上 %d 个' % len(good)))
    return out


for path in EXES:
    print('==', path)
    for name, r in check(path):
        print('  %s：%s' % (name, r))
