# -*- coding: utf-8 -*-
"""训练木桩 + 整备点（rr/dummy.py 在重随版 regulation 里建木桩的敌人参数，features.json 的 training_dummy）：圆桌厅堂能战斗的区域。
圆桌里的赐福是游戏写死的（加第二个也会被当成大赐福），所以旁边放的是能对话的「整备点」：更换战灰、记忆法术、调配灵药、重新诞生、恢复。
地图和对话包都是预先做好的固定文件（data/dummy，说明见那里），启动时纯 Python 处理，不需要 .NET：
  地图：把随机器对这张图的改动（替换入侵的阿尔贝里奇等）按字节同步到固定地图上；
  对话包：来源包里的各个脚本原样换进来，再写整备点的脚本（照抄双子老妪的，只换菜单）；
  事件脚本：加「恢复」事件（对话里点亮请求标记，事件看到就像在赐福休息一样恢复，不刷新敌人）"""
import os
import struct

import emevd
import erlib
import esd as esdlib

from .common import DATA, last_with, vanilla
from .esdutil import DIALOG_WAIT, GRACE_WAIT, STATE_TIME_OVER_1, i32, wait_menu, write_check

DUMMY_MAP = os.path.join(DATA, 'dummy', 'm11_10_00_00.msb.dcx')
DUMMY_TALK = os.path.join(DATA, 'dummy', 'm11_10_00_00.talkesdbnd.dcx')
MAP_REL = os.path.join('map', 'mapstudio', 'm11_10_00_00.msb.dcx')
EVENT_REL = os.path.join('event', 'm11_10_00_00.emevd.dcx')
TALK_REL = os.path.join('script', 'talk', 'm11_10_00_00.talkesdbnd.dcx')
STATION_ESD, STATION_TEMPLATE, STATION_MENU = 't699001110.esd', 't600001110.esd', 2147483644    # 双子老妪的脚本、它的菜单状态机
STATION_FLAG, STATION_EVENT = 11109990, 11102990
STATION_TEXT = {k: 80090100 + k for k in range(4)}          # 0 更换战灰 / 1 记忆法术 / 2 恢复 / 3 已恢复
STATION_TEXTS = {'en': ['Ashes of War', 'Memorize spell', 'Restore (HP, FP, flasks)', 'HP, FP and flasks restored'],
                 'zh': ['更换战灰', '记忆法术', '恢复（血量、专注值、圣杯瓶）', '血量、专注值、圣杯瓶已恢复']}
STATION_RESTORE_SP = 30100      # 恢复时一起挂的原版效果（照抄法魂 mod 的恢复事件）
# 整备点的「调配灵药」「重新诞生」：照搬赐福脚本（t000001000）里的写法，菜单文字用原版的 EventTextForTalk
#   调配灵药：有灵药圣杯瓶（物品 250 / 空瓶 251）才显示（AddTalkListDataIf，条件字节照抄原版赐福菜单），1:130 打开，等界面 21 关掉
#   重新诞生：1:113 打开重新诞生界面 + 1:35，等 1 秒、等界面 19 关掉（不消耗泪滴幼体）
PHYSICK_TEXT, REBIRTH_TEXT = 15000510, 22000000
PHYSICK_COND = bytes.fromhex('6f820300000082fa000000820200000082000000008200000000898201000000956f820300000082fb000000'
                             '8202000000820000000082000000008982010000009599a1')
PART_MODEL = 0x14        # 部件里的模型序号（i32，指模型表；各文件的模型表顺序可能不同，按名字比）


def plan(cx):
    """要用的来源 {map, vanilla, event, talk}；不加木桩返回 None"""
    if getattr(cx, '_plan', False) is not False:
        return cx._plan
    cx._plan = None
    d = cx.S.get('training_dummy')
    if not cx.feat.get('training_dummy') or not isinstance(d, dict) or not d.get('enabled', True):
        return None
    # 原版文件走 vanilla()（装了随机器用它带的，没装从游戏 Data0 取）；原版地图在 Data1~3 拿不到，只有开敌人随机（随机器在）时才要
    p = {'map': last_with(cx.sources, MAP_REL),                  # 随机器 / 档次修正改过的这张图（没有就是原版）
         'vanilla': vanilla(MAP_REL),
         'event': last_with(cx.sources, EVENT_REL) or vanilla(EVENT_REL),
         'talk': last_with(cx.sources, TALK_REL) or vanilla(TALK_REL)}
    if not os.path.isfile(DUMMY_MAP) or not os.path.isfile(DUMMY_TALK) or not p['event'] or not p['talk'] \
            or (p['map'] and not p['vanilla']):
        return None
    cx._plan = p
    return p


def msb_lists(raw):
    """解压后的 MSBE：{表名: [各条目的偏移]}，外加每张表的结束位置 {表名: 下一张表的偏移}"""
    out, ends = {}, {}
    pos = 0x10
    while pos:
        cnt = struct.unpack_from('<i', raw, pos + 4)[0]
        noff = struct.unpack_from('<q', raw, pos + 8)[0]
        name = erlib._u16str(raw, noff)
        out[name] = list(struct.unpack_from('<%dq' % (cnt - 1), raw, pos + 16))
        pos = struct.unpack_from('<q', raw, pos + 16 + 8 * (cnt - 1))[0]
        ends[name] = pos or len(raw)
    return out, ends


def msb_parts(raw):
    """{部件名: (起点, 终点)}（PARTS_PARAM_ST 里每个部件的字节范围）"""
    lists, ends = msb_lists(raw)
    offs = lists['PARTS_PARAM_ST']
    return {erlib._u16str(raw, o + struct.unpack_from('<q', raw, o)[0]): (o, e)
            for o, e in zip(offs, offs[1:] + [ends['PARTS_PARAM_ST']])}


def msb_models(raw):
    return [erlib._u16str(raw, o + struct.unpack_from('<q', raw, o)[0]) for o in msb_lists(raw)[0]['MODEL_PARAM_ST']]


def sync_map(fixed, vanilla, rand):
    """把随机器（rand）相对原版（vanilla）改过的地方抄到固定地图（fixed）的同名部件上。
    模型序号按模型名比（随机器重写地图时模型表顺序会变，序号不同不代表换了模型）；换了模型而固定地图里没有那个模型的不抄。
    其余只抄改过的字节：固定地图里加了部件 / 模型，其他部件里的编号会变，那些字节不能整段覆盖；
    随机器改的字节在固定地图里也被动过（冲突）、长度不一样、随机器新加 / 删掉部件的，记下来不抄。返回 (新的固定地图, 抄了几个部件, 没抄的说明)"""
    F, V, R = bytearray(fixed), vanilla, rand
    pf, pv, pr = msb_parts(F), msb_parts(V), msb_parts(R)
    mf, mv, mr = msb_models(F), msb_models(V), msb_models(R)
    model = lambda raw, names, o: names[struct.unpack_from('<i', raw, o + PART_MODEL)[0]]
    M = range(PART_MODEL, PART_MODEL + 4)
    done, skip = 0, []
    for name, (rs, re_) in pr.items():
        if name not in pv:
            skip.append('随机器新加的 ' + name)
            continue
        vs, ve = pv[name]
        fs, fe = pf.get(name, (0, 0))
        new_model = model(R, mr, rs)
        model_changed = new_model != model(V, mv, vs)
        diff = [i for i in range(min(re_ - rs, ve - vs)) if i not in M and R[rs + i] != V[vs + i]]
        if not diff and not model_changed and re_ - rs == ve - vs:
            continue
        if name not in pf or not (re_ - rs == ve - vs == fe - fs):
            skip.append(name)
            continue
        if model_changed and new_model not in mf:
            skip.append('%s（换成的模型 %s 固定地图里没有）' % (name, new_model))
            continue
        if any(F[fs + i] != V[vs + i] for i in diff):
            skip.append(name + '（冲突）')
            continue
        for i in diff:
            F[fs + i] = R[rs + i]
        if model_changed:
            struct.pack_into('<i', F, fs + PART_MODEL, mf.index(new_model))
        done += 1
    skip += ['随机器删掉的 ' + n for n in pv if n not in pr]
    return bytes(F), done, skip


def station_esd(template):
    """整备点的对话脚本：照抄双子老妪的（靠近出提示、按键对话那一套），菜单状态机整个换掉"""
    E = esdlib.read(template)
    old = E['groups'][STATION_MENU]
    cmd = lambda b, i, *a: {'bank': b, 'id': i, 'args': list(a)}
    go = lambda t, ev=bytes([0x41, 0xA1]): {'target': t, 'eval': ev, 'pass': [], 'sub': []}
    pick = lambda k: bytes([0x57, 0x84]) + i32(k)[:-1] + bytes([0x95, 0xA1])   # 菜单选了第 k 项（直接比较选择结果，不用寄存器）
    st = lambda entry, conds: {'entry': entry, 'exit': [], 'while': [], 'conds': conds}
    clear_sel = old[8]['entry']                                     # ClearPreviousMenuSelection（照抄）
    E['groups'][STATION_MENU] = {
        0: st([], [go(8)]),
        8: st(clear_sel, [go(1)]),
        1: st([cmd(1, 20)], [go(2)]),                               # ClearTalkListData
        2: st([cmd(1, 19, i32(1), i32(STATION_TEXT[0]), i32(-1)), cmd(1, 19, i32(2), i32(STATION_TEXT[1]), i32(-1)),
               cmd(5, 19, PHYSICK_COND, i32(4), i32(PHYSICK_TEXT), i32(-1)), cmd(1, 19, i32(5), i32(REBIRTH_TEXT), i32(-1)),
               cmd(1, 19, i32(3), i32(STATION_TEXT[2]), i32(-1)), cmd(1, 19, i32(99), i32(20000009), i32(-1))], [go(3)]),
        3: st([cmd(1, 10, i32(1))], [go(4, wait_menu(1))]),          # ShowShopMessage，等菜单关掉
        4: st([], [go(10, pick(1)), go(11, pick(2)), go(12, pick(3)), go(13, pick(4)), go(14, pick(5)), go(9)]),
        10: st([cmd(1, 48)], [go(8, wait_menu(7))]),                 # OpenEquipmentChangeOfPurposeShop（更换战灰）
        11: st([cmd(1, 28, i32(-1), i32(-1))], [go(8, wait_menu(11))]),  # OpenMagicEquip（记忆法术）
        12: st([cmd(1, 11, i32(STATION_FLAG), i32(1)),               # 点亮恢复请求（事件里恢复），弹一句提示
                cmd(1, 17, i32(7), i32(STATION_TEXT[3]), i32(1), i32(0), i32(1))], [go(8, DIALOG_WAIT)]),
        13: st([cmd(1, 130)], [go(8, GRACE_WAIT(21))]),              # 调配灵药
        14: st([cmd(1, 113), cmd(1, 35)], [go(15, STATE_TIME_OVER_1)]),  # 重新诞生
        15: st([], [go(8, GRACE_WAIT(19))]),
        9: st([], [go(None)]),
    }
    return write_check(E)


def build(tmp, p):
    """写固定地图（同步随机器的改动）、整备点的事件脚本和对话包；返回说明"""
    fixed = erlib.dcx_decompress(open(DUMMY_MAP, 'rb').read())
    note = ''
    if p['map']:
        fixed, n, skip = sync_map(fixed, erlib.dcx_decompress(open(p['vanilla'], 'rb').read()),
                                  erlib.dcx_decompress(open(p['map'], 'rb').read()))
        note = '同步随机器改动 %d 处' % n + ('（%d 处没同步：%s）' % (len(skip), '、'.join(skip[:5])) if skip else '')
    os.makedirs(os.path.join(tmp, os.path.dirname(MAP_REL)), exist_ok=True)
    data = erlib.dcx_compress_dflt(fixed, level=6)
    if erlib.dcx_check_strict(data) != fixed:
        raise RuntimeError('圆桌地图写回后自检失败')
    open(os.path.join(tmp, MAP_REL), 'wb').write(data)
    # 事件脚本：整备点的「恢复」——对话里点亮 STATION_FLAG，这个事件看到就像在赐福休息一样恢复（2004[47]，不刷新敌人），再熄灭
    e = emevd.read(erlib.dcx_decompress(open(p['event'], 'rb').read()))
    if not any(ev['id'] == STATION_EVENT for ev in e['events']):
        body = [emevd.ins(1003, 1, ('u8', 3), ('u8', 0), ('u8', 0), ('u32', STATION_FLAG)),        # 没请求就跳过下面三行
                emevd.ins(2004, 47),
                emevd.ins(2004, 8, ('u32', 10000), ('s32', STATION_RESTORE_SP)),
                emevd.ins(2003, 66, ('u8', 0), ('u32', STATION_FLAG), ('u8', 0)),
                emevd.ins(1001, 0, ('f32', 0.3)), emevd.ins(1000, 4, ('u8', 1))]                       # 等 0.3 秒，重新开始
        e['events'].append({'id': STATION_EVENT, 'rest': 0, 'ins': body, 'params': []})
        next(ev for ev in e['events'] if ev['id'] == 0)['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', STATION_EVENT), ('u32', 0)))
    os.makedirs(os.path.join(tmp, os.path.dirname(EVENT_REL)), exist_ok=True)
    open(os.path.join(tmp, EVENT_REL), 'wb').write(erlib.dcx_compress_dflt(emevd.write(e), level=6))
    # 对话包：固定包（多了整备点的脚本）里换上来源包的各个脚本，再写整备点的脚本
    fb = erlib.Bnd4(erlib.dcx_decompress(open(DUMMY_TALK, 'rb').read()))
    sb = erlib.Bnd4(erlib.dcx_decompress(open(p['talk'], 'rb').read()))
    for name in sb.entries:
        if name in fb.entries and name != STATION_ESD:
            fb.put(name, sb.get(name))
    fb.put(STATION_ESD, station_esd(sb.get(STATION_TEMPLATE)))
    os.makedirs(os.path.join(tmp, os.path.dirname(TALK_REL)), exist_ok=True)
    erlib.write_dcx_file(os.path.join(tmp, TALK_REL), bytes(fb.data))
    return note


def files(cx, tmp):
    p = plan(cx)
    if not p:
        return
    try:
        note = build(tmp, p)
        if '没同步' in note:
            cx.notes.append('训练场：' + note)
    except Exception as e:                      # 木桩加不上不影响其他功能（没写完的文件删掉）
        for rel in (MAP_REL, EVENT_REL, TALK_REL):
            if os.path.isfile(os.path.join(tmp, rel)):
                os.remove(os.path.join(tmp, rel))
        cx.notes.append('训练木桩没加上（%s: %s）' % (type(e).__name__, e))
        cx.sig_extra = '-nodummy'


def texts(cx, key):
    if not plan(cx):
        return {}
    return {'EventTextForTalk': {STATION_TEXT[k]: t for k, t in enumerate(STATION_TEXTS[key])}}


def sources(cx):
    p = plan(cx)
    return [DUMMY_MAP, DUMMY_TALK] + [x for x in (p['map'], p['vanilla'], p['event'], p['talk']) if x] if p else []
