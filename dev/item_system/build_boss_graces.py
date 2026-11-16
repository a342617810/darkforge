# -*- coding: utf-8 -*-
"""Boss 房里的赐福（用户 2026-11-12「进入高难度后要熄灭所有boss房里的赐福点亮标记」）→ launcher\\reroll\\data\\boss_graces.json。
认法：地图事件脚本里调公共事件 9005810（Boss 击败后在房间里出现赐福）的地方，参数是（击败标记、赐福自己的点亮标记、赐福角色、赐福物件、距离），
赐福物件的编号 = BonfireWarpParam.bonfireEntityId → 这一行的 eventflagId 就是赐福的传送标记（flag，亮着才能传送过去）。
第 2 个参数是 RegisterBonfire 用的点亮标记（lit，用户 2026-11-15）：只熄传送标记的话，重新打败 Boss 后赐福出现时还算「已点亮」，
摸了不会再点亮，传送标记也就不会再亮，地图上传送不过去。
进「死亡」以上难度复活 Boss 时两个都熄灭（sc/difficulty.py revive_flags）：Boss 复活后房间里的赐福不出现，标记却还亮着就能直接传送进 Boss 房。
NOT_BOSS 里的不是 Boss 房（出现条件是支线标记）。
用法：python -X utf8 dev\\item_system\\build_boss_graces.py（读随机器目录的 event\\ 和游戏目录的 regulation.bin；地图、赐福编号不随随机化变）"""
import glob
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402
import emevd  # noqa: E402
import paramdef_min as pdm  # noqa: E402

GAME = os.path.dirname(PALY)
erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), GAME]
OUT = os.path.join(RR, 'data', 'boss_graces.json')
BOSS_GRACE_EVENT = 9005810
NOT_BOSS = {76247: '菈妮的房间：出现条件 1034500703 是菈妮支线的标记，不是 Boss'}


def main():
    calls = []
    for p in sorted(glob.glob(os.path.join(PALY, 'randomizer', 'event', 'm*.emevd.dcx'))):
        e = emevd.read(erlib.dcx_decompress(open(p, 'rb').read()))
        m = os.path.basename(p).split('.')[0]
        for ev in e['events']:
            for ins in ev['ins']:
                if (ins['bank'], ins['id']) == (2000, 6) and len(ins['args']) >= 16:
                    v = struct.unpack_from('<%di' % (len(ins['args']) // 4), ins['args'], 0)
                    if v[1] == BOSS_GRACE_EVENT:
                        calls.append((m, v[2], v[3:]))
    reg = erlib.Bnd4(erlib.read_regulation(os.path.join(GAME, 'regulation.bin')))
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(RR, 'data', 'BonfireWarpParam.xml')))[0]}
    B = erlib.Param(reg.get('BonfireWarpParam.param'))
    g = lambda r, f: struct.unpack_from('<' + lay[f][1], r, lay[f][2])[0]
    by_ent = {g(r, 'bonfireEntityId'): (rid, g(r, 'eventflagId'), g(r, 'textId1')) for rid, r in B.rows.items()}
    names = {}
    for f in ('item.msgbnd.dcx', 'item_dlc02.msgbnd.dcx', 'menu.msgbnd.dcx', 'menu_dlc02.msgbnd.dcx'):
        pth = os.path.join(PALY, 'randomizer', 'diste', 'Vanilla', 'msg', 'zhocn', f)
        if os.path.isfile(pth):
            b = erlib.Bnd4(erlib.dcx_decompress(open(pth, 'rb').read()))
            for n in b.entries:
                if 'PlaceName' in n:
                    names.update({k: v for k, v in erlib.read_fmg(b.get(n)).items() if v})
    out, seen, miss = [], set(), []
    for m, defeat, args in calls:
        ent = next((x for x in args if x in by_ent), None)
        if ent is None:
            miss.append((m, defeat))
            continue
        rid, flag, tid = by_ent[ent]
        if flag in seen or flag in NOT_BOSS:
            continue
        seen.add(flag)
        out.append({'flag': flag, 'lit': args[0], 'name': names.get(tid, ''), 'map': m, 'defeat': defeat, 'bonfire_row': rid})
    if miss:
        raise RuntimeError('对不上赐福参数的调用：%s' % miss)
    out.sort(key=lambda x: x['flag'])
    head = {'_说明': 'Boss 房里的赐福（Boss 击败后才出现）：flag 是传送标记、lit 是赐福自己的点亮标记，进「死亡」以上难度复活 Boss 时'
                    '两个都熄灭；读档时传送标记灭着、点亮标记却亮着的也把点亮标记熄掉（sc/difficulty.py）。'
                    'dev\\item_system\\build_boss_graces.py 生成，不要手改',
            'graces': out}
    open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(head, ensure_ascii=False, indent=1) + '\n')
    print('写好 %s：%d 个 Boss 房赐福（9005810 调用 %d 处，跳过不是 Boss 的 %d 个）' % (OUT, len(out), len(calls), len(NOT_BOSS)))


if __name__ == '__main__':
    main()
