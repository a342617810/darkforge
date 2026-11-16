# -*- coding: utf-8 -*-
"""Elden Ring 对话脚本 ESD（talkesdbnd 里的 *.esd，长格式 fsSL）的读写。

结构（偏移都相对 0x6C 处的数据区）：
  状态机表 [id, 状态表偏移, 状态数, 状态表偏移]
  状态 0x48：id, 条件偏移表的偏移+数量, 进入 / 退出 / 持续命令（偏移+数量）
  条件 0x38：目标状态（状态结构的偏移，-1 = 无）, 通过时命令, 子条件偏移表, 判断字节码
  命令 0x18：bank, id, 参数表；参数 0x10：字节码偏移+长度
读出来的结构：{'groups': {机器id: {状态id: State}}, 'unk': [4 个 int], 'ds': 3}
State = {'conds': [Cond], 'entry': [Cmd], 'exit': [Cmd], 'while': [Cmd]}
Cond = {'target': 状态id 或 None, 'eval': bytes, 'pass': [Cmd], 'sub': [Cond]}
Cmd = {'bank': int, 'id': int, 'args': [bytes]}
写出的顺序和 SoulsFormats 一样（用它逐字节核对过）。"""
import struct

HDR = 0x6C


def read(b):
    b = bytes(b)
    if b[:4] != b'fsSL':
        raise ValueError('不是长格式 ESD（fsSL）')
    h = struct.unpack_from('<26i', b, 4)
    ds = h[1]
    D = HDR
    q = lambda o: struct.unpack_from('<q', b, D + o)[0]
    unk = list(struct.unpack_from('<4i', b, D + 4))
    goff, gcnt = q(0x18), q(0x20)
    state_at = {}            # 状态结构偏移 → (机器, 状态id)
    groups = {}
    raw = []
    for k in range(gcnt):
        gid, soff, scnt, _ = struct.unpack_from('<4q', b, D + goff + 32 * k)
        raw.append((gid, soff, scnt))
        for j in range(scnt):
            o = soff + 0x48 * j
            state_at[o] = (gid, q(o))

    def cmds(off, n):
        out = []
        for j in range(n):
            bank, cid, aoff, acnt = struct.unpack_from('<iiqq', b, D + off + 0x18 * j)
            args = []
            for t in range(acnt):
                bo, bl = struct.unpack_from('<qq', b, D + aoff + 0x10 * t)
                args.append(b[D + bo:D + bo + bl])
            out.append({'bank': bank, 'id': cid, 'args': args})
        return out

    def conds(off, n):
        out = []
        for j in range(n):
            co = q(off + 8 * j)
            tgt, poff, pcnt, soff, scnt, eoff, elen = struct.unpack_from('<7q', b, D + co)
            out.append({'target': None if tgt == -1 else state_at[tgt][1], 'pass': cmds(poff, pcnt),
                        'sub': conds(soff, scnt), 'eval': b[D + eoff:D + eoff + elen]})
        return out

    for gid, soff, scnt in raw:
        st = {}
        for j in range(scnt):
            o = soff + 0x48 * j
            sid, coff, ccnt, a, an, x, xn, w, wn = struct.unpack_from('<9q', b, D + o)
            st[sid] = {'conds': conds(coff, ccnt), 'entry': cmds(a, an), 'exit': cmds(x, xn), 'while': cmds(w, wn)}
        groups[gid] = st
    name = None
    noff, nlen = q(0x28), q(0x30)
    if noff >= 0 and nlen > 0:                      # 原版文件末尾有名字（如 t000001100），UTF-16
        name = b[D + noff:D + noff + 2 * nlen].decode('utf-16le')
    return {'groups': groups, 'unk': unk, 'ds': ds, 'name': name}


def write(esd):
    G = list(esd['groups'].items())
    # 状态记录：每个机器的状态依次排，多于一个状态的机器末尾再放一份第一个状态的副本（原文件就是这样）
    slots = []
    for gid, st in G:
        items = list(st.items())
        for sid, s in items:
            slots.append((gid, sid, s))
        if len(items) > 1:
            slots.append((gid, items[0][0], None))
    states = [x for x in slots if x[2] is not None]
    cond_list, cond_gid, cmd_list, arg_list, coff_list = [], [], [], [], []
    sub_start = {}

    def add_conds(cs, gid):            # 一组条件在偏移表里连续；子条件排在后面
        start = len(coff_list)
        ids = []
        for c in cs:
            ids.append(len(cond_list))
            cond_list.append(c)
            cond_gid.append(gid)
        coff_list.extend(ids)
        for k, c in zip(ids, cs):
            sub_start[k] = add_conds(c['sub'], gid) if c['sub'] else None
        return start

    cond_start, cond_range = {}, {}
    for gid, sid, s in states:
        k0 = len(cond_list)
        cond_start[(gid, sid)] = add_conds(s['conds'], gid)     # 没有条件也指向当前位置（原文件如此）
        cond_range[(gid, sid)] = range(k0, len(cond_list))

    def add_cmds(cs):
        start = len(cmd_list)
        cmd_list.extend(cs)
        return start

    cmd_state, cmd_cond = {}, {}
    for gid, st in G:                   # 按机器排：各状态的进入 / 退出 / 持续命令，再是这个机器各条件的通过命令
        for sid, s in st.items():
            cmd_state[(gid, sid)] = (add_cmds(s['entry']), add_cmds(s['exit']), add_cmds(s['while']))
        for sid in st:
            for k in cond_range[(gid, sid)]:
                cmd_cond[k] = add_cmds(cond_list[k]['pass'])
    arg_start = []
    for c in cmd_list:
        arg_start.append(len(arg_list))
        arg_list.extend(c['args'])

    off_groups = 0x48
    off_states = off_groups + 32 * len(G)
    off_conds = off_states + 0x48 * len(slots)
    off_cmds = off_conds + 0x38 * len(cond_list)
    off_args = off_cmds + 0x18 * len(cmd_list)
    off_coffs = off_args + 0x10 * len(arg_list)
    bpos = off_coffs + 8 * len(coff_list)
    eval_off = []
    for c in cond_list:                 # 字节码：先条件的判断式，再命令参数
        eval_off.append(bpos)
        bpos += len(c['eval'])
    arg_off = []
    for a in arg_list:
        arg_off.append(bpos)
        bpos += len(a)
    name = (esd.get('name') or '').encode('utf-16le')
    name_off = bpos
    end = bpos + len(name)

    state_off = {}
    for n, (gid, sid, s) in enumerate(slots):
        if s is not None:
            state_off[(gid, sid)] = off_states + 0x48 * n
    out = bytearray(end)

    def p(fmt, o, *v):
        struct.pack_into(fmt, out, o, *v)
    p('<i', 0, 1)
    p('<4i', 4, *esd['unk'])
    p('<qq', 0x18, off_groups, len(G))
    p('<qqqq', 0x28, name_off if name else -1, len(name) // 2, -1, -1)
    out[name_off:end] = name
    for k, (gid, st) in enumerate(G):
        o = state_off[(gid, next(iter(st)))]
        p('<4q', off_groups + 32 * k, gid, o, len(st), o)
    for n, (gid, sid, s) in enumerate(slots):
        s = esd['groups'][gid][sid]
        cs = cond_start[(gid, sid)]
        e, x, w = cmd_state[(gid, sid)]
        p('<9q', off_states + 0x48 * n, sid,
          off_coffs + 8 * cs, len(s['conds']),
          -1 if not s['entry'] else off_cmds + 0x18 * e, len(s['entry']),
          -1 if not s['exit'] else off_cmds + 0x18 * x, len(s['exit']),
          -1 if not s['while'] else off_cmds + 0x18 * w, len(s['while']))
    for k, c in enumerate(cond_list):
        sub = sub_start[k]
        p('<7q', off_conds + 0x38 * k,
          -1 if c['target'] is None else state_off[(cond_gid[k], c['target'])],
          -1 if not c['pass'] else off_cmds + 0x18 * cmd_cond[k], len(c['pass']),
          -1 if sub is None else off_coffs + 8 * sub, len(c['sub']),
          eval_off[k], len(c['eval']))
        out[eval_off[k]:eval_off[k] + len(c['eval'])] = c['eval']
    for j, c in enumerate(cmd_list):
        p('<iiqq', off_cmds + 0x18 * j, c['bank'], c['id'],
          off_args + 0x10 * arg_start[j], len(c['args']))      # 没有参数也指向当前位置
    for j, a in enumerate(arg_list):
        p('<qq', off_args + 0x10 * j, arg_off[j], len(a))
        out[arg_off[j]:arg_off[j] + len(a)] = a
    for j, k in enumerate(coff_list):
        p('<q', off_coffs + 8 * j, off_conds + 0x38 * k)
    hdr = struct.pack('<4s26i', b'fsSL', 1, esd['ds'], esd['ds'], 0x54, end, 6, 0x48, 1, 0x20, len(G), 0x48, len(slots),
                      0x38, len(cond_list), 0x18, len(cmd_list), 0x10, len(arg_list), off_coffs, len(coff_list),
                      name_off if name else end, len(name) // 2, end, 0, end, 0)
    return hdr + bytes(out)
