# -*- coding: utf-8 -*-
"""dark_slot（第五个护符槽）在 2.7.1.0 / 2.7.2.0 两个 exe 上离线核对，照 DLL 里 lib.rs 的逻辑走一遍：
  装备筛选 hook：调用点特征码（第一个 .text 唯一命中）→ call 目标 = 版本表里的 hook RVA，开头 16 字节对得上
  槽位可用函数表：跳转特征码唯一命中 → 表 + 24*8 = 版本表里的 entry；第 23 项是 mov al,1/ret，第 24 项是 xor al,al/ret
  数据：版本表里的 data = FLT_MAX（0x7f7fffff），data+8 = 0
  定时检查：每个起点都试（同 pelite 扫描器），[4-132] 取最短；必须 181 处、互不相同、都是 0x72
另外和 Golden Age 带的 eldenring_covenant_slot 0.1.2 写死的 2.7.1.0 地址对一遍。
用法：launcher\\python\\python.exe -X utf8 dev\\vendor\\port_tools\\verify_slot.py [2.7.1.0 exe] [2.7.2.0 exe]"""
import struct
import sys

EXES = sys.argv[1:] or [r'E:\SteamLibrary\steamapps\common\ELDEN RING\Game\eldenring.exe', r'C:\Users\dxphh\ER_new\Game\eldenring.exe']
W = None
# 和 lib.rs 的 VERSIONS 一致
VERSIONS = [
    ('2.7.1.0', 0x8505C0, 0x3B39020, 0x3B35008),
    ('2.7.2.0', 0x850A70, 0x3B3C030, 0x3B38008),
]
HOOK_SITE = [0x4D, 0x8D, 0x4B, 0xB8, 0x8D, 0x51, 0x28, 0x44, 0x8D, 0x41, 0x15, 0x48, 0x8B, 0xCB, 0xE8]
HOOK_HEAD = bytes([0x4C, 0x8B, 0xDC, 0x4D, 0x89, 0x4B, 0x20, 0x49, 0x89, 0x4B, 0x08, 0x55, 0x56, 0x57, 0x48, 0x81])
DISPATCH = [0x48, 0x0F, 0xBE, 0x01, 0x48, 0x8D, 0x0D, W, W, W, W, 0x48, 0xFF, 0x24, 0xC1]
BRANCHES = 181
# Golden Age 的 DLL：2.7.1.0 写死的地址（它的 .rdata 0x30390 起、0x5cbe 起）
GA_271 = {'hook_site': 0x858119, 'hook': 0x8505C0, 'src': 0x3B35008, 'dst': 0x3B35010, 'entry': 0x3B39020, 'true': 0x765C40, 'false': 0x765C50}


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
            self.secs.append((name, va, vsize, raw, rsize))

    def rd(self, rva, n):
        for _n, va, vs, raw, rs in self.secs:
            if va <= rva and rva + n <= va + rs:
                return self.d[raw + rva - va:raw + rva - va + n]
        raise ValueError('读不到 %#x' % rva)

    def q(self, rva):
        return struct.unpack('<Q', self.rd(rva, 8))[0]

    def text(self):
        """第一个 .text（exe 里有两个，DLL 只扫第一个）"""
        name, va, vs, raw, rs = next(s for s in self.secs if s[0] == '.text')
        return va, self.d[raw:raw + min(vs, rs)]


def find_all(t, pat):
    first = pat[0]
    out, i = [], t.find(bytes([first]))
    while i != -1 and i + len(pat) <= len(t):
        if all(p is None or t[i + j] == p for j, p in enumerate(pat)):
            out.append(i)
        i = t.find(bytes([first]), i + 1)
    return out


def branches(t):
    """b9 ???? e8 ???? f3 0f 11 05 [4-132] ' 72 ? 48 8d：每个起点都试，跳过的字节取最短（和 lib.rs 一样也认已改成 eb 的）"""
    out, i = [], t.find(b'\xb9')
    while i != -1 and i + 150 <= len(t):
        if t[i + 5] == 0xE8 and t[i + 10:i + 14] == b'\xf3\x0f\x11\x05':
            for j in range(i + 18, i + 147):
                if t[j] in (0x72, 0xEB) and t[j + 2] == 0x48 and t[j + 3] == 0x8D:
                    out.append(j)
                    break
        i = t.find(b'\xb9', i + 1)
    return out


def check(path):
    p = Pe(path)
    va, t = p.text()
    ok, got = [], {}
    hs = find_all(t, HOOK_SITE)
    ok.append(('hook 调用点唯一', len(hs) == 1, len(hs)))
    site = va + hs[0]
    hook = site + 19 + struct.unpack('<i', p.rd(site + 15, 4))[0]
    got.update(hook_site=site, hook=hook)
    ok.append(('hook 开头 16 字节', p.rd(hook, 16) == HOOK_HEAD, p.rd(hook, 16).hex(' ')))
    ds = find_all(t, DISPATCH)
    ok.append(('函数表跳转唯一', len(ds) == 1, len(ds)))
    d = va + ds[0]
    table = d + 11 + struct.unpack('<i', p.rd(d + 7, 4))[0]
    entry = table + 24 * 8
    tru, cur = p.q(table + 23 * 8) - p.base, p.q(entry) - p.base
    got.update(entry=entry, true=tru, false=cur)
    ok.append(('第 23 项 mov al,1/ret', p.rd(tru, 3) == b'\xb0\x01\xc3', '%#x' % tru))
    ok.append(('第 24 项 xor al,al/ret', p.rd(cur, 3) == b'\x32\xc0\xc3', '%#x' % cur))
    ver = next((v for v in VERSIONS if v[1] == hook), None)
    ok.append(('版本表认得出', ver is not None and ver[2] == entry, ver[0] if ver else '-'))
    if ver:
        src = ver[3]
        got.update(src=src, dst=src + 8)
        ok.append(('数据 FLT_MAX / 0', p.q(src) == 0x7F7FFFFF and p.q(src + 8) == 0, '%#x %#x' % (p.q(src), p.q(src + 8))))
    br = [va + j for j in branches(t)]
    codes = {p.rd(b, 1)[0] for b in br}
    ok.append(('定时检查 181 处、互不相同、都是 jb', len(br) == BRANCHES and len(set(br)) == len(br) and codes == {0x72},
               '%d 处，%s' % (len(br), sorted(hex(c) for c in codes))))
    return ok, got, br


def main():
    allok = True
    for path in EXES:
        ok, got, br = check(path)
        print('==', path)
        for name, good, info in ok:
            allok &= good
            print('  %s %s：%s' % ('OK ' if good else '不符', name, info))
        print('  地址：' + '，'.join('%s=%#x' % kv for kv in got.items()) + '，第一处跳转=%#x' % br[0])
        if got.get('hook') == GA_271['hook']:
            same = all(got.get(k) == v for k, v in GA_271.items())
            allok &= same
            print('  %s 和 Golden Age 的 2.7.1.0 写死地址一致' % ('OK ' if same else '不符'))
    print('全部符合' if allok else '有不符的项')
    return 0 if allok else 1


if __name__ == '__main__':
    sys.exit(main())
