# -*- coding: utf-8 -*-
"""移植补查 2：
1) 函数逐条比：新旧指令一样，call / jmp 的目标都差同一个平移量（TEXT_LABEL 候选 0x761c70，顺带核对已找到的几个）
2) 箭袋：.pdata 找出旧指令 0x65a758 所在函数，移植函数开头，在新函数里找同一位置的 cmp byte [rip+x], 0，读出新标记"""
import struct, sys
sys.argv = ['x']
g = {}
exec(open(__file__.replace('port_rvas3.py', 'port_rvas.py'), encoding='utf-8').read().split('FUNCS = {')[0], g)
old, new, masked, find, md, X = g['old'], g['new'], g['masked'], g['find'], g['md'], g['X']


def ins_list(img, rva, n=80):
    out = []
    for i in md.disasm(img.data[rva:rva + 16 * n], rva):
        tgt = None
        if (i.group(X.X86_GRP_JUMP) or i.group(X.X86_GRP_CALL)) and i.operands and i.operands[0].type == X.X86_OP_IMM:
            tgt = i.operands[0].imm
        rip = None
        for op in i.operands:
            if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP:
                rip = i.address + i.size + op.mem.disp
        out.append((i.mnemonic, tgt, rip, i.address - rva))
        if i.mnemonic in ('ret', 'int3') and len(out) > 3:
            break
    return out


def compare(o, n):
    a, b = ins_list(old, o), ins_list(new, n)
    if [x[0] for x in a] != [x[0] for x in b]:
        return '指令序列不同'
    shifts = set()
    for (m1, t1, r1, _), (m2, t2, r2, _) in zip(a, b):
        if t1 is not None and t1 not in range(o, o + 0x2000):
            shifts.add(('call/jmp', t2 - t1))
        if r1 is not None:
            shifts.add(('rip', r2 - r1))
    return '%d 条指令一样；目标平移 %s' % (len(a), sorted(shifts))


for name, o, n in (('TEXT_LABEL', 0x7617c0, 0x761c70), ('TEXT_HELP', 0x7615e0, 0x761a90), ('POPUP', 0x8fc570, 0x8fca20),
                   ('RESULT2', 0x7a80d0, 0x7a8580), ('SETVIS', 0x734190, 0x734640), ('OPEN_FILE', 0xd6d280, 0xd6e970)):
    print('%-10s %s' % (name, compare(o, n)))
# TEXT_LABEL 的其他候选：不是它的应该对不上
for n in (0x761b70, 0x761bd0, 0x7619a0):
    print('  候选 %#x：%s' % (n, compare(0x7617c0, n)))

# 箭袋：.pdata 找函数
pd = old.data[0x4867000:0x4867000 + 0x2b3200]
fn = None
for k in range(0, len(pd) - 12, 12):
    b, e, u = struct.unpack_from('<III', pd, k)
    if b <= 0x65a758 < e:
        fn = (b, e)
        break
print('箭袋指令所在函数（旧）%#x ~ %#x，指令在 +%#x' % (fn[0], fn[1], 0x65a758 - fn[0]))
for nn in (40, 60, 24, 90):
    pat, mask = masked(old, fn[0], nn)
    hits = find(new, pat, mask)
    print('   移植函数开头（%d 条）：' % nn, [hex(h) for h in hits])
    if len(hits) == 1:
        nf = hits[0]
        off = 0x65a758 - fn[0]
        i = next(md.disasm(new.data[nf + off:nf + off + 16], nf + off))
        print('   新函数 %#x + %#x：%s %s（字节 %s）' % (nf, off, i.mnemonic, i.op_str, new.data[nf + off:nf + off + 7].hex()))
        if i.mnemonic == 'cmp' and new.data[nf + off:nf + off + 2] == b'\x80\x3d':
            print('   → 新箭袋指令 %#x，新标记 %#x' % (nf + off, nf + off + 7 + struct.unpack_from('<i', new.data, nf + off + 2)[0]))
        print('   整个函数比：', compare(fn[0], nf))
        break
