# -*- coding: utf-8 -*-
"""移植补查：FINALIZE 前 13 字节；TEXT_LABEL 的候选（按 +0x4B0 的规律核对）；箭袋 cmp 指令（按数据段平移找）；
各挂钩点被搬走的那几个字节新旧是否一样（挂钩只搬这几个字节，必须是完整指令、不含 RIP 相对）"""
import struct, sys
sys.argv = ['x']
g = {}
exec(open(__file__.replace('port_rvas2.py', 'port_rvas.py'), encoding='utf-8').read().split('FUNCS = {')[0], g)
old, new, masked, find, md, X = g['old'], g['new'], g['masked'], g['find'], g['md'], g['X']

pat, mask = masked(old, 0x7617c0, 40)
hits = find(new, pat, mask)
print('TEXT_LABEL 候选', [hex(h) for h in hits], '；按规律 0x761c70 在里面：', 0x761c70 in hits)
for n in (60, 90, 120):
    pat, mask = masked(old, 0x7617c0, n, stop_at_ret=False)
    hits = find(new, pat, mask)
    print('   %d 条指令（不在 ret 停）：' % n, [hex(h) for h in hits])
print('TEXT_LABEL 新旧开头 16 字节', old.data[0x7617c0:0x7617d0].hex(), new.data[0x761c70:0x761c80].hex())

# 挂钩点：被搬走的字节数（dark_lock 的 detour）
steal = {'FINALIZE': (0x78e780, 0x78ec30, 13), 'POPUP': (0x8fc570, 0x8fca20, 13), 'OPEN_FILE': (0xd6d280, 0xd6e970, 16),
         'BIND': (0x900940, 0x900df0, 12), 'REFRESH': (0x900610, 0x900ac0, 13)}
for k, (o, n, s) in steal.items():
    ins = [(i.address - n, i.size, i.mnemonic, i.op_str) for i in md.disasm(new.data[n:n + 32], n)]
    cut = [a + sz for a, sz, _, _ in ins]
    print('%-10s 搬走 %d 字节：新旧一样 %s，正好在指令边界 %s，新指令 %s' % (
        k, s, old.data[o:o + s] == new.data[n:n + s], s in cut, ' | '.join('%s %s' % (m, op) for a, sz, m, op in ins if a < s)))

# 箭袋：旧标记 0x3d6a216，数据段平移 +0x3000 → 新 0x3d6d216？在新代码里找 cmp byte [rip+x], 0 指向它的指令
ta, text = new.sec('.text')
for want in (0x3d6d216, 0x3d6a216 + (0x3b18000 - 0x3b15000)):
    hits = []
    i = text.find(b'\x80\x3d')
    while i != -1:
        if i + 7 <= len(text) and text[i + 6] == 0:
            disp = struct.unpack_from('<i', text, i + 2)[0]
            if ta + i + 7 + disp == want:
                hits.append(ta + i)
        i = text.find(b'\x80\x3d', i + 1)
    print('新代码里 cmp byte [rip+x],0 指向 %#x 的：' % want, [hex(h) for h in hits])
# 旧代码里指向旧标记的同类指令有几处（对照）
oa, otext = old.sec('.text')
ohits = []
i = otext.find(b'\x80\x3d')
while i != -1:
    if i + 7 <= len(otext) and otext[i + 6] == 0 and oa + i + 7 + struct.unpack_from('<i', otext, i + 2)[0] == 0x3d6a216:
        ohits.append(oa + i)
    i = otext.find(b'\x80\x3d', i + 1)
print('旧代码里指向 0x3d6a216 的：', [hex(h) for h in ohits])
