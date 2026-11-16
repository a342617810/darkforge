# -*- coding: utf-8 -*-
"""把 dark_lock / dark_sell 在 2.7.1.0 里写死的地址移植到 2.7.2.0：
函数开头反汇编若干条指令，rel32 / RIP 相对位移当通配符做特征码，在新 exe 的代码段里找唯一命中；
函数内的指令（POPUP 里调 FINALIZE 的 call、箭袋的 cmp）按周围指令找；MemoryFile 虚表按它的函数指针在只读数据里找。
输出新旧地址、开头字节（给 DLL 的版本核对用），以及每个移植的核对结果"""
import sys, struct, json
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone import x86_const as X

OLD = r'E:\SteamLibrary\steamapps\common\ELDEN RING\Game\eldenring.exe'
NEW = r'C:\Users\dxphh\ER_new\Game\eldenring.exe'


class Img:
    def __init__(self, path):
        self.pe = pefile.PE(path, fast_load=True)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.data = self.pe.get_memory_mapped_image()
        self.secs = {}
        for s in self.pe.sections:              # 有两个 .text（后一个是保护壳的）：同名的只记第一个（主代码段）
            self.secs.setdefault(s.Name.rstrip(b'\0').decode(), (s.VirtualAddress, s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData)))

    def sec(self, name):
        a, b = self.secs[name]
        return a, self.data[a:b]


old, new = Img(OLD), Img(NEW)
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True


def masked(img, rva, n_ins=40, stop_at_ret=True):
    """从 rva 开始反汇编 n_ins 条，返回（字节, 掩码）——rel32 立即数 / 分支偏移 / RIP 相对位移的字节掩掉"""
    code = img.data[rva:rva + 16 * n_ins]
    bs, mask = bytearray(), bytearray()
    for k, ins in enumerate(md.disasm(code, rva)):
        if k >= n_ins:
            break
        b = bytearray(ins.bytes)
        m = bytearray(b'\xff' * len(b))
        x = ins.x86 if hasattr(ins, 'x86') else None
        # 分支 / 调用的相对偏移
        if ins.group(X.X86_GRP_JUMP) or ins.group(X.X86_GRP_CALL):
            for op in ins.operands:
                if op.type == X.X86_OP_IMM and ins.imm_size:
                    for i in range(ins.imm_offset, ins.imm_offset + ins.imm_size):
                        m[i] = 0
        for op in ins.operands:
            if op.type == X.X86_OP_MEM and op.mem.base == X.X86_REG_RIP and ins.disp_size:
                for i in range(ins.disp_offset, ins.disp_offset + ins.disp_size):
                    m[i] = 0
        bs += b
        mask += m
        if stop_at_ret and ins.mnemonic in ('ret', 'int3') and k >= 3:
            break
    return bytes(bs), bytes(mask)


def find(img, pat, mask, sec='.text'):
    a, data = img.sec(sec)
    # 找一段最长的不掩码的字节先粗查
    best, cur, cs = (0, 0), 0, 0
    for i, m in enumerate(mask + b'\0'):
        if m:
            if cur == 0:
                cs = i
            cur += 1
        else:
            if cur > best[1]:
                best = (cs, cur)
            cur = 0
    s, ln = best
    anchor = pat[s:s + ln]
    hits = []
    i = data.find(anchor)
    while i != -1:
        st = i - s
        if st >= 0 and st + len(pat) <= len(data):
            ok = all((data[st + j] == pat[j]) for j in range(len(pat)) if mask[j])
            if ok:
                hits.append(a + st)
        i = data.find(anchor, i + 1)
    return hits


def port_fn(name, rva, n_ins=40):
    for n in (n_ins, 60, 90, 24, 16):
        pat, mask = masked(old, rva, n)
        if sum(mask) < 12:
            continue
        hits = find(new, pat, mask)
        if len(hits) == 1:
            return hits[0], n, len(pat)
    return None, None, None


FUNCS = {'POPUP': 0x8fc570, 'FINALIZE': 0x78e780, 'ADD_ITEM': 0x745600, 'TEXT_LABEL': 0x7617c0, 'TEXT_HELP': 0x7615e0,
         'TEXT_DTOR': 0x743ae0, 'RESULT2': 0x7a80d0, 'OPEN_FILE': 0xd6d280, 'BIND': 0x900940, 'REFRESH': 0x900610,
         'RESOLVE': 0x74b140, 'SETVIS': 0x734190, 'MEMFILE_VT0': 0xce9730}
res = {}
for name, rva in FUNCS.items():
    nr, n, ln = port_fn(name, rva)
    res[name] = nr
    same16 = nr is not None and old.data[rva:rva + 16] == new.data[nr:nr + 16]
    print('%-12s 旧 %#09x → 新 %s（%s 条指令 %s 字节）开头 16 字节%s' % (
        name, rva, '%#09x' % nr if nr else '没找到 / 不唯一', n, ln, '一样' if same16 else '不一样'))


def rel_target(img, rva):
    ins = next(md.disasm(img.data[rva:rva + 16], rva))
    return ins, (ins.operands[0].imm if ins.operands and ins.operands[0].type == X.X86_OP_IMM else None)


# POPUP 里调 FINALIZE 的 call：在新 POPUP 里找调用新 FINALIZE 的 call
CALL_FIN_OLD = 0x8fd02d
ins, tgt = rel_target(old, CALL_FIN_OLD)
print('旧 CALL_FIN', ins.mnemonic, ins.op_str, '目标 %#x（= FINALIZE %s）' % (tgt, tgt == FUNCS['FINALIZE']), '在 POPUP + %#x' % (CALL_FIN_OLD - FUNCS['POPUP']))
calls = []
if res['POPUP'] and res['FINALIZE']:
    code = new.data[res['POPUP']:res['POPUP'] + 0x2000]
    for i in md.disasm(code, res['POPUP']):
        if i.mnemonic == 'call' and i.operands and i.operands[0].type == X.X86_OP_IMM and i.operands[0].imm == res['FINALIZE']:
            calls.append(i.address)
        if i.mnemonic == 'int3':
            break
print('新 POPUP 里调用新 FINALIZE 的 call：', ['%#x（POPUP + %#x）' % (c, c - res['POPUP']) for c in calls])
res['CALL_FIN'] = calls[0] if len(calls) == 1 else None

# MemoryFile 虚表：旧虚表各项 → 新函数，然后在新的 .rdata 里找第一项指针、后面几项也对得上
VT_OLD = 0x2ba7d70
old_entries = [struct.unpack_from('<Q', old.data, VT_OLD + 8 * k)[0] - old.base for k in range(6)]
print('旧虚表前 6 项', ['%#x' % e for e in old_entries])
new_entries = []
for e in old_entries:
    nr, _, _ = port_fn('vt', e, 24)
    new_entries.append(nr)
print('对应新函数', ['%#x' % e if e else None for e in new_entries])
ra, rdata = new.sec('.rdata')
cand = []
p0 = struct.pack('<Q', new.base + new_entries[0]) if new_entries[0] else None
i = rdata.find(p0) if p0 else -1
while i != -1:
    ok = sum(1 for k, e in enumerate(new_entries) if e and struct.unpack_from('<Q', rdata, i + 8 * k)[0] == new.base + e)
    cand.append((ra + i, ok))
    i = rdata.find(p0, i + 1)
print('新 .rdata 里的候选虚表（地址, 对上几项）', [('%#x' % a, k) for a, k in cand])
best = [a for a, k in cand if k == sum(1 for e in new_entries if e)]
res['MEMFILE_VT'] = best[0] if len(best) == 1 else None

# 箭袋：读「所有箭矢不消耗」开关的 cmp byte [rip+x], 0
CHK_OLD, FLAG_OLD = 0x65A758, 0x3D6A216
ins, _ = rel_target(old, CHK_OLD)
print('旧箭袋指令', ins.mnemonic, ins.op_str, '目标 %#x' % (CHK_OLD + ins.size + ins.disp))
# 用这条指令前后的指令做特征码：从前面 12 条开始
code = old.data[CHK_OLD - 0x80:CHK_OLD + 0x80]
starts = [i.address for i in md.disasm(code, CHK_OLD - 0x80)]
k = next((j for j, a in enumerate(starts) if a == CHK_OLD), None)
found = None
for back in (8, 12, 6, 16, 4):
    if k is None or k - back < 0:
        continue
    st = starts[k - back]
    pat, mask = masked(old, st, back + 12, stop_at_ret=False)
    hits = find(new, pat, mask)
    if len(hits) == 1:
        found = hits[0] + (CHK_OLD - st)
        break
if found:
    ins2, _ = rel_target(new, found)
    tgt2 = found + ins2.size + ins2.disp
    print('新箭袋指令 %#x：' % found, ins2.mnemonic, ins2.op_str, '目标 %#x' % tgt2, '字节', new.data[found:found + 7].hex())
    res['NO_ARROW_CHECK'], res['NO_ARROW_FLAG'] = found, tgt2
else:
    print('新箭袋指令没找到 / 不唯一')
# 一键出售「移除物品」的特征码（运行时搜）：新 exe 里是否唯一
aob = [None, 0x83, 0xEC, None, 0x8B, 0xF2, None, 0x8B, 0xE9, None, 0x85, 0xC0, 0x74]
pat = bytes(b if b is not None else 0 for b in aob)
mask = bytes(0xff if b is not None else 0 for b in aob)
print('移除物品特征码：旧 %d 处、新 %d 处' % (len(find(old, pat, mask)), len(find(new, pat, mask))))
out = {k: v for k, v in res.items()}
out['_first16'] = {k: new.data[v:v + 16].hex() for k, v in res.items() if v and k not in ('MEMFILE_VT', 'NO_ARROW_FLAG')}
out['_vt0'] = new_entries[0]
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else 'port_rvas.json', 'w'), indent=1)
print(json.dumps({k: (hex(v) if isinstance(v, int) else v) for k, v in res.items()}, ensure_ascii=False))
