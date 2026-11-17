# -*- coding: utf-8 -*-
"""斗技场试炼的地图、事件、雕像对话（重随 rr/arena.py 在 features.json 的 arena 写了才做；执行在 dll\\dark_core 的 arena.rs；
提案 dev\\item_system\\斗技场试炼提案.md）。
- 竞技场地图 m45_0X（加载的包里最后一份 / 随机器带的原版）：msbtool batch 照抄敌人部件进来（Boss 在中间偏后、精英在前方一排 5 个位置，
  地面碰撞 h001000 的显示分组），玩家部件照抄一个当传送落点（F + 3980）。按来源地图和清单的内容缓存在 cache\\arena。
- 竞技场的事件脚本：每个部件一个事件（读图时禁用 → 等出场标记 → 启用、Boss 挂血条 → 死了点亮死亡标记）；问继续（2007[10]，是 / 否 / 取消
  点亮 F + 2601~2603）；离开（传回进来的那个雕像旁）；竞技场里的提示（同 sc/notes.py 的做法，标记是本图的 F + 2630 起 5 位）。
  初始化加在事件 0 的最前面：原版事件 0 不在竞技场对战里就提前结束了。
- 雕像旁的传送落点（离开时传到这里）：王城两张图照抄本图的玩家部件，野外小格子从 m60_40_52_00 照抄。
- 公共事件：dark_core 点亮传送请求（93673）、场次位改成竞技场编号 + 1 以后，对应的事件把玩家传进竞技场。
- 雕像对话：原版「解锁 / 联机检查」那一步换成我们的菜单（三种场次、竞技场（联机）= 原版流程、离开）；选了场次先看星光碎片够不够、确认，
  点亮场次位和请求（93670~93672），dark_core 扣碎片、点传送请求。联机会话里只有房主能开始（确认框写明队友一起进），队员只看提示。
- 联机（联机计划 13.13）：竞技场里加的事件都关掉网络同步；敌人出场先读进来、AI 关着，各台电脑都就绪了 dark_core 再点亮开打（map_events）。
做不成的竞技场整个不改（日志说一句），其他照常。"""
import hashlib
import math
import os
import re
import shutil
import subprocess

import emevd
import erlib
import esd as esdlib

from . import extragrace
from .common import REROLL, last_with, vanilla
from .esdutil import ALWAYS, CONFIRM_NO, CONFIRM_YES, flag_is_on, i32, menu_pick, wait_menu, write_check

CACHE_DIR = os.path.join(REROLL, 'cache', 'arena')
TALK_TEXT0 = 80099000        # EventTextForTalk：+r 三种场次，+3 竞技场（联机），+4 队员不能开始，+20+r 碎片不够，+30+10X+r 确认框，+60+10X+r 房主的确认框
ASK_TEXT = 80099100          # EventTextForMap：继续下一波？
LEAVE_TEXT = 20000009        # 原版「离开」
# 联机（联机计划 13.13）：会话里只有房主能在雕像开始，队员跟着房主进（dark_core arena.rs）。COOP_SESSION / COOP_HOST 和 dark_core coop.rs 的
# SESSION_FLAG / HOST_FLAG 一样（两边一起改）
COOP_SESSION, COOP_HOST, COOP_TEXT, HOST_TEXT0 = 92570, 92571, TALK_TEXT0 + 4, TALK_TEXT0 + 60
CONFIRM_GID, DIALOG_GID, MENU_GID = 2147399100, 2147399101, 2147399102   # 加进雕像脚本的状态机
WARP_EVENT0 = 1040490872     # 公共事件：传进竞技场 X = 1040490872~874（不存档的块；870 / 871 原版提示、880 音效、881~959 / 961~999 Boss 奖励，dev\event_flags\说明.md）
EV_ASK, EV_NOTE, EV_LEAVE0, EV_RESPAWN0, EV_BANNER, EV_PART0 = 2700, 2701, 2702, 2704, 2706, 2800      # 竞技场地图里的事件编号（F + …；离开、复活点按雕像序号 +v）
EV_READY0, EV_ENGAGE0, MAX_PARTS = 2850, 2900, 50        # 部件 k 的就绪、开打事件（F + … + k）
# 联机时每台电脑各管各的（同 scripts.py 的 NO_SYNC，原版很多事件第一条就是它）：竞技场里我们加的事件都关掉网络同步
NO_SYNC = emevd.ins(2000, 2, ('u8', 0))
FLOOR = 'h001000'            # 竞技场地面的碰撞部件（三张图都有）
Y = 0.3
PLAYER_AT, PLAYER_YAW = (0.0, 15.0), 180.0
BOSS_AT = (0.0, -8.0)
# 精英站位 0~4；5、6 是红 / 蓝粪金龟（rr/arena.py SCARAB_SPOTS），在精英那排前面一点
ELITE_AT = [(-8.0, -6.0), (-4.0, -9.0), (0.0, -10.0), (4.0, -9.0), (8.0, -6.0), (-5.0, -2.0), (5.0, -2.0)]
ENEMY_YAW = 0.0
SHOW_SECS = 3.0
# 打完最后一波的大字幕：借竞技场结算的字幕（2007[2] 类型 32；原版 98005120 / 98005121 竞技场结算用 31~34）。
# 类型 32 显示的是 GR_MenuText 331315（STALEMATE，中文版写 DRAW；2026-11-10 用户游戏里看到的，以前以为是 VICTORY 331314）。
# 只有联机竞技场打平会用到它，那里也会显示成 TRIAL COMPLETE
BANNER_TYPE, BANNER_TEXT = 32, 331315
# 各竞技场的敌人强度（确认框里写，用户 2026-11-10）：0 王城、1 盖利德、2 宁姆格福
STRENGTH = {0: ('幽影之地后期', 'late Realm of Shadow'), 1: ('王城', 'Leyndell, Royal Capital'), 2: ('利耶尼亚', 'Liurnia of the Lakes')}
RUN_ZH = '斗技场试炼：%d 波（%d 个星光碎片）'
RUN_EN = 'Colosseum Trial: %d waves (%d Starlight Shard%s)'


def feat(cx):
    return cx.feat.get('arena')


def rel_map(m):
    return os.path.join('map', 'mapstudio', m + '.msb.dcx')


def rel_event(m):
    return os.path.join('event', m + '.emevd.dcx')


def rel_talk(m):
    return os.path.join('script', 'talk', m + '.talkesdbnd.dcx')


def talk_of(statue_map):
    """雕像所在地图 → 对话包（野外都在 m60_00_00_00 里）"""
    return 'm60_00_00_00' if statue_map.startswith('m60') else statue_map


def src_file(cx, rel, tmp=None):
    """先看这次已经写进覆盖包的（别的功能改过的），再按加载顺序找，最后用原版"""
    if tmp and os.path.isfile(os.path.join(tmp, rel)):
        return os.path.join(tmp, rel)
    return last_with(cx.sources, rel) or vanilla(rel)


def sources(cx):
    f = feat(cx)
    if not f:
        return []
    out = []
    for co in f['colos']:
        out += [src_file(cx, rel_map(co['map'])), src_file(cx, rel_event(co['map']))]
        out += [vanilla(rel_map(p['src_map'])) for p in co['parts']]
        for s in co['statues']:
            out += [src_file(cx, rel_map(s['map'])), src_file(cx, rel_talk(talk_of(s['map'])))]
            if s['src'][0] == 'player':
                out.append(vanilla(rel_map(s['src'][1])))
            if s.get('rsrc') and s['rsrc'][0] != '-':
                out.append(vanilla(rel_map(s['rsrc'][0])))
    out.append(os.path.join(REROLL, 'data', 'msbtool', 'msbtool.dll'))
    return sorted({p for p in out if p})


# ------------------------------------------------------------------ 地图（msbtool batch）
def run_batch(name, src, spec):
    """在 src（地图文件）上跑一份清单，返回新地图的字节；按来源内容 + 清单 + msbtool 缓存。失败抛 RuntimeError"""
    raw = open(src, 'rb').read()
    tool_dll = os.path.join(REROLL, 'data', 'msbtool', 'msbtool.dll')
    h = hashlib.sha1(raw + spec.encode('utf-8') + open(tool_dll, 'rb').read()).hexdigest()[:20]
    cached = os.path.join(CACHE_DIR, '%s_%s.msb.dcx' % (name, h))
    if os.path.isfile(cached):
        return open(cached, 'rb').read()
    d, why = extragrace.tool()
    if not d:
        raise RuntimeError(why)
    fin, fout, fspec = (os.path.join(d, 'arena_%s.%s' % (name, x)) for x in ('in.msb.dcx', 'out.msb.dcx', 'spec.txt'))
    open(fin, 'wb').write(raw)
    open(fspec, 'w', encoding='utf-8', newline='\n').write(spec)
    r = subprocess.run([extragrace.DOTNET, 'msbtool.dll', 'batch', fin, fout, fspec], cwd=d, capture_output=True, text=True,
                       timeout=600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0 or not r.stdout.strip().endswith('ok') or not os.path.isfile(fout):
        raise RuntimeError('msbtool batch %s 失败：%s' % (name, (r.stdout + r.stderr).strip()[-300:]))
    out = open(fout, 'rb').read()
    for p in (fin, fout, fspec):
        os.remove(p)
    os.makedirs(CACHE_DIR, exist_ok=True)
    for old in os.listdir(CACHE_DIR):
        if old.startswith(name + '_'):
            os.remove(os.path.join(CACHE_DIR, old))
    open(cached, 'wb').write(out)
    return out


def line(*f):
    return '\t'.join(repr(x) if isinstance(x, float) else str(x) for x in f)


def arena_spec(co):
    F = co['flag']
    L = ['# 斗技场试炼：%s（sc/arena.py 生成）' % co['map'], line('drawfrom', FLOOR),
         line('clone', 'c0000_0000', 'c0000_9980', co['warp'], PLAYER_AT[0], Y, PLAYER_AT[1], PLAYER_YAW)]
    for p in co['parts']:
        x, z = BOSS_AT if p['kind'] == 'b' else ELITE_AT[p['spot'] % len(ELITE_AT)]
        src = vanilla(rel_map(p['src_map']))
        if not src:
            raise RuntimeError('找不到来源地图 %s' % p['src_map'])
        L.append(line('import', src, p['part'], '%s_%d' % (p['model'], 9500 + p['k']), p['ent'], float(x), Y, float(z), ENEMY_YAW,
                      p['npc'], -1, FLOOR, 0))
    if F + 3000 + len(co['parts']) > co['warp']:
        raise RuntimeError('部件实体和传送落点撞号')
    return '\n'.join(L) + '\n'


def statue_spec(s):
    x, y, z = s['pos']
    sx, _sy, sz = s['statue']
    yaw = math.degrees(math.atan2(sx - x, sz - z))            # 面朝雕像
    if s['src'][0] == 'clone':
        out = line('clone', s['src'][1], 'c0000_9980', s['ent'], float(x), float(y), float(z), round(yaw, 2)) + '\n'
    else:
        src = vanilla(rel_map(s['src'][1]))
        if not src:
            raise RuntimeError('找不到玩家部件的来源地图 %s' % s['src'][1])
        out = line('player', src, s['src'][2], 'c0000_9980', s['ent'], float(x), float(y), float(z), round(yaw, 2)) + '\n'
    # 复活点（SpawnPoint 区域，试炼中死了在这里复活）：同一处
    rmap, rent = s['rsrc']
    rsrc = '-' if rmap == '-' else vanilla(rel_map(rmap))
    if not rsrc:
        raise RuntimeError('找不到复活点区域的来源地图 %s' % rmap)
    return out + line('region', rsrc, rent, 'DR 斗技场试炼 复活点', s['resp'], float(x), float(y), float(z), round(yaw, 2)) + '\n'


# ------------------------------------------------------------------ 事件
def wait_flag(flag, on=1):
    return emevd.ins(3, 0, ('s8', 0), ('u8', on), ('u8', 0), ('u32', flag))


def set_flag(flag, on):
    return emevd.ins(2003, 66, ('u8', 0), ('u32', flag), ('u8', on))


def skip_if(lines, state, flag):
    """标记是 state 就跳过下面 lines 行"""
    return emevd.ins(1003, 1, ('u8', lines), ('u8', state), ('u8', 0), ('u32', flag))


RESTART = emevd.ins(1000, 4, ('u8', 1))


def wait_s(t):
    return emevd.ins(1001, 0, ('f32', t))


def init(eid):
    return emevd.ins(2000, 0, ('s32', 0), ('u32', eid), ('u32', 0))


def note_body(bits, t0, n):
    """竞技场里的提示（照 sc/notes.py）：几位标记里写着编号 → 显示 EventTextForMap t0 + 编号、等几秒、全灭"""
    nb = len(bits)
    clear = emevd.ins(2003, 22, ('u32', bits[0]), ('u32', bits[-1]), ('u8', 0))
    body = [skip_if(nb - 1 - i + 2, 1, b) for i, b in enumerate(bits)]
    body += [wait_s(0.25), RESTART]
    for v in range(1, n + 1):
        body += [skip_if(nb - 1 - i + 4, 0 if (v >> i) & 1 else 1, b) for i, b in enumerate(bits)]
        body += [emevd.ins(2007, 4, ('s32', t0 + v)), wait_s(SHOW_SECS), clear, RESTART]
    body += [clear, RESTART]
    return body


def map_events(raw, co, f):
    """竞技场地图的事件脚本加我们的事件；返回新的（解压后）。
    联机（联机计划 13.13，照黄金树爬塔的做法，没抄代码）：我们加的事件都关掉网络同步（每台电脑点亮自己的出场标记、启用自己那份敌人）；
    读图时除了禁用还去掉预读（2004[29]），出场时恢复预读再启用（爬塔两台电脑实测：不这样房主那边敌人一直没读进来）；
    出场时 AI 关着、无敌，读进来了点亮就绪标记，dark_core 等各台电脑都就绪了再点亮开打标记（开打事件打开 AI、关掉无敌）。
    就绪、开打各是一个事件：就绪那条指令（4[7]）万一一直等不到，dark_core 照样会开打，敌人不会一直站着不动"""
    e = emevd.read(raw)
    F = co['flag']
    ready, engage, mydead = f.get('ready', 0), f.get('engage', 0), f.get('mydead', 0)
    if len(co['parts']) > MAX_PARTS or any(p['k'] >= MAX_PARTS for p in co['parts']):
        raise RuntimeError('%s 的部件超过 %d 个' % (co['map'], MAX_PARTS))
    ids = {F + x for x in (EV_ASK, EV_NOTE, EV_BANNER)} | {F + EV_LEAVE0 + s['v'] for s in co['statues']} | \
          {F + EV_RESPAWN0 + s['v'] for s in co['statues']} | {F + b + p['k'] for p in co['parts'] for b in (EV_PART0, EV_READY0, EV_ENGAGE0)}
    clash = sorted(ev['id'] for ev in e['events'] if ev['id'] in ids)
    if clash:
        raise RuntimeError('%s 的事件脚本里已经有 %s' % (co['map'], clash[:5]))
    ev0 = next(ev for ev in e['events'] if ev['id'] == 0)
    new = []
    for p in co['parts']:
        ent, boss, k = p['ent'], p['kind'] == 'b', p['k']
        bar = lambda on: emevd.ins(2003, 11, ('s8', on), ('u32', ent), ('s16', 0), ('s32', p['name']))
        body = []
        if engage:
            body += [emevd.ins(2004, 1, ('u32', ent), ('u8', 0)),       # AI 关、无敌：等开打
                     emevd.ins(2004, 15, ('u32', ent), ('u8', 1))]
        body += [emevd.ins(2004, 5, ('u32', ent), ('u8', 0)),            # 读图时禁用、去掉预读
                 emevd.ins(2004, 29, ('u32', ent), ('u8', 1)),
                 wait_flag(F + f['spawn'] + k),                           # 等 dark_core 点亮出场
                 emevd.ins(2004, 35, ('u32', ent), ('u8', 1)),
                 emevd.ins(2004, 29, ('u32', ent), ('u8', 0)),
                 emevd.ins(2004, 5, ('u32', ent), ('u8', 1))]
        if boss and p['name'] > 0:
            body.append(bar(1))
        body += [emevd.ins(4, 0, ('s8', 0), ('u32', ent), ('u8', 1), ('u8', 0), ('f32', 1.0)),   # 等它死
                 set_flag(F + f['dead'] + k, 1)]
        if boss and p['name'] > 0:
            body.append(bar(0))
        new.append({'id': F + EV_PART0 + k, 'rest': 0, 'ins': body, 'params': []})
        if ready:
            new.append({'id': F + EV_READY0 + k, 'rest': 0, 'params': [], 'ins': [
                wait_flag(F + f['spawn'] + k),
                emevd.ins(4, 7, ('s8', 0), ('u32', ent), ('u8', 1), ('s8', 0), ('f32', 1.0)),    # 等它读进来
                set_flag(F + ready + k, 1)]})
        if engage:
            new.append({'id': F + EV_ENGAGE0 + k, 'rest': 0, 'params': [], 'ins': [
                wait_flag(F + f['spawn'] + k), wait_flag(F + engage),
                emevd.ins(2004, 1, ('u32', ent), ('u8', 1)),
                emevd.ins(2004, 15, ('u32', ent), ('u8', 0))]})
    a = F + f['ask']
    # 问继续：照剑心修罗在同一张竞技场图里的写法（实测能用）——对话框实体 0、距离 5，结果标记不用竞技场本图的标记
    # （2026-11-10 两次测试：结果设在本图的 4500X2601~2603、实体填玩家，选了「是」标记都没亮，第二波一直不出），
    # 先清结果标记、弹框、OR 组等任意一个亮了，再转写成本图的 a + 1（是）/ a + 2（否）给 dark_core 读、清掉结果标记、重新开始。
    # 结果标记借雕像请求的场次两位（len0 / len0 + 1）：传进竞技场时公共事件已经清了，试炼中不会有别的地方用
    # 取消算「否」（用户 2026-11-10「取消可以算否」）。第三次测试刚发奖励就问，对话框被获得提示顶掉、以取消结束直接传了出去：
    # dark_core 现在等奖励发完、提示播完才点亮问话；问了 1.5 秒内就回「否」的当成被顶掉，再点亮一次（这里选了才熄灭 a）。距离照原版 4852 用 100
    r_yes, r_no = f['len0'], f['len0'] + 1
    or1 = lambda flag: emevd.ins(3, 0, ('s8', -1), ('u8', 1), ('u8', 0), ('u32', flag))
    clear_r = emevd.ins(2003, 22, ('u32', r_yes), ('u32', r_no), ('u8', 0))
    new.append({'id': F + EV_ASK, 'rest': 0, 'params': [], 'ins': [
        wait_flag(a), clear_r,
        emevd.ins(2007, 10, ('s32', ASK_TEXT), ('s16', 0), ('s16', 2), ('u32', 0), ('f32', 100.0), ('u32', r_yes), ('u32', r_no), ('u32', r_no)),
        or1(r_yes), or1(r_no), emevd.ins(0, 0, ('s8', 0), ('u8', 1), ('s8', -1)),
        skip_if(1, 0, r_yes), set_flag(a + 1, 1),
        skip_if(1, 0, r_no), set_flag(a + 2, 1),
        set_flag(a, 0), clear_r, wait_s(0.5), RESTART]})
    if f.get('banner'):
        bf = F + f['banner']
        new.append({'id': F + EV_BANNER, 'rest': 0, 'params': [], 'ins': [
            wait_flag(bf), set_flag(bf, 0), emevd.ins(2007, 2, ('u8', BANNER_TYPE)), wait_s(1.0), RESTART]})
    bits = [F + f['note_bits'] + i for i in range(f['note_n'])]
    new.append({'id': F + EV_NOTE, 'rest': 0, 'params': [], 'ins': note_body(bits, f['note_text0'], len(f['notes']))})
    for s in co['statues']:
        lf = F + f['leave'] + s['v']
        new.append({'id': F + EV_LEAVE0 + s['v'], 'rest': 0, 'params': [], 'ins': [
            wait_flag(lf), set_flag(lf, 0),
            emevd.ins(2003, 14, *[('u8', b) for b in s['block']], ('u32', s['ent']), ('s32', 0)),
            wait_s(1.0), RESTART]})
        # 试炼中死了：复活点设到进来的那个雕像旁（2003[23]，原版也有跨地图设的；直到下次在赐福休息都按它）。
        # 联机时客机事件里的 10000 可能是房主（黄金树爬塔的玩家日志）：再加 dark_core 点亮的「本机死了」，哪个先到都算
        died = [emevd.ins(4, 0, ('s8', 0), ('u32', 10000), ('u8', 1), ('u8', 0), ('f32', 1.0))]
        if mydead:
            died = [emevd.ins(4, 0, ('s8', -1), ('u32', 10000), ('u8', 1), ('u8', 0), ('f32', 1.0)), or1(F + mydead),
                    emevd.ins(0, 0, ('s8', 0), ('u8', 1), ('s8', -1))]
        new.append({'id': F + EV_RESPAWN0 + s['v'], 'rest': 0, 'params': [], 'ins': [
            wait_flag(F + f['run'] + s['v'])] + died + [
            emevd.ins(2003, 23, ('u32', s['resp']))]})
    for ev in new:
        ev['ins'].insert(0, dict(NO_SYNC))
    e['events'] += new
    ev0['ins'][0:0] = [init(ev['id']) for ev in new]                     # 原版事件 0 不在对战里就提前结束：加在最前面
    return emevd.write(e)


def events(cx, e, ev0):
    """公共事件：传进竞技场；顺便把能做成的竞技场先做出来（地图、事件，cx.arena_ok）"""
    f = feat(cx)
    if not f or any(ev['id'] == WARP_EVENT0 for ev in e['events']):
        return
    prepare(cx)
    for co in f['colos']:
        x = co['x']
        if x not in cx.arena_ok:
            continue
        code = x + 1
        b0, b1 = code & 1, (code >> 1) & 1
        body = [wait_flag(f['warp']),
                skip_if(2, b0, f['len0']), wait_s(0.5), RESTART,
                skip_if(2, b1, f['len0'] + 1), wait_s(0.5), RESTART,
                set_flag(f['warp'], 0), set_flag(f['len0'], 0), set_flag(f['len0'] + 1, 0),
                emevd.ins(2003, 14, ('u8', 45), ('u8', x), ('u8', 0), ('u8', 0), ('u32', co['warp']), ('s32', 0)),
                wait_s(1.0), RESTART]
        e['events'].append({'id': WARP_EVENT0 + x, 'rest': 0, 'ins': body, 'params': []})
        ev0['ins'].append(init(WARP_EVENT0 + x))


def prepare(cx):
    """竞技场地图 + 事件 + 雕像旁落点（来源是加载的包 / 原版；files 里雕像地图如果被别的功能改过会重做）：cx.arena_out {x: {rel: 字节}}"""
    if hasattr(cx, 'arena_ok'):
        return
    cx.arena_ok, cx.arena_out = set(), {}
    f = feat(cx)
    for co in f['colos']:
        x, m = co['x'], co['map']
        try:
            out = {}
            src = src_file(cx, rel_map(m))
            if not src:
                raise RuntimeError('找不到 %s' % m)
            out[rel_map(m)] = run_batch(m, src, arena_spec(co))
            ev_src = src_file(cx, rel_event(m))
            if not ev_src:
                raise RuntimeError('找不到 %s 的事件脚本' % m)
            out[rel_event(m)] = erlib.dcx_compress_dflt(map_events(erlib.dcx_decompress(open(ev_src, 'rb').read()), co, f), level=6)
            for s in co['statues']:
                ssrc = src_file(cx, rel_map(s['map']))
                if not ssrc:
                    raise RuntimeError('找不到雕像地图 %s' % s['map'])
                out[rel_map(s['map'])] = run_batch(s['map'], ssrc, statue_spec(s))
        except Exception as ex:
            cx.notes.append('斗技场试炼：%s 没做成（%s: %s）' % (m, type(ex).__name__, ex))
            continue
        cx.arena_ok.add(x)
        cx.arena_out[x] = out


# ------------------------------------------------------------------ 雕像对话
def _st(entry, conds):
    return {'entry': entry, 'exit': [], 'while': [], 'conds': conds}


def _go(t, ev=ALWAYS):
    return {'target': t, 'eval': ev, 'pass': [], 'sub': []}


def _ret(v):
    return {'target': None, 'eval': ALWAYS, 'pass': [{'bank': 7, 'id': -1, 'args': [bytes([0x40 + v, 0xA1])]}], 'sub': []}


def _cmd(b, i, *a):
    return {'bank': b, 'id': i, 'args': list(a)}


DIALOG_WAIT = bytes.fromhex('7a4085a64095a1')                # 提示框关掉了


def confirm_group():
    """通用确认框（照抄原版赐福脚本 t000001000 的 2147483647）：参数 = 文字编号；选「是」返回 0，否则 1"""
    return {0: _st([], [_go(1)]),
            1: _st([_cmd(1, 17, bytes.fromhex('48a1'), bytes.fromhex('40b8a1'), bytes.fromhex('43a1'), bytes.fromhex('44a1'), bytes.fromhex('42a1'))],
                   [_go(2, DIALOG_WAIT)]),
            2: _st([], [_go(3, bytes.fromhex('5684a64195a1')), _go(4)]),
            3: _st([], [_ret(0)]),
            4: _st([], [_ret(1)])}


def dialog_group():
    """只有「确定」的提示框（照抄原版雕像脚本 t621006000 的 2147483645）：参数 = 文字编号"""
    return {0: _st([], [_go(1)]),
            1: _st([_cmd(1, 17, bytes.fromhex('47a1'), bytes.fromhex('40b8a1'), bytes.fromhex('41a1'), bytes.fromhex('40a1'), bytes.fromhex('41a1'))],
                   [_go(2, DIALOG_WAIT)]),
            2: _st([], [_ret(0)])}


def has_shards(goods, n):
    """eval：ComparePlayerInventoryNumber(道具, goods, >, n − 1) == 1（写法同原版赐福菜单的「有灵药圣杯瓶」）"""
    return (bytes([0x6F]) + b''.join(i32(v)[:-1] for v in (3, goods, 2, n - 1, 0)) + bytes([0x89]) + i32(1)[:-1] + bytes([0x95, 0xA1]))


def menu_group(f, x):
    """我们的菜单：返回 0 = 走原版流程（竞技场联机），1 = 结束这次对话"""
    g = {0: _st([], [_go(1)]),
         1: _st([_cmd(1, 20)], [_go(2)]),
         2: _st([_cmd(1, 19, i32(r + 1), i32(TALK_TEXT0 + r), i32(-1)) for r in range(len(f['waves']))]
                + [_cmd(1, 19, i32(9), i32(TALK_TEXT0 + 3), i32(-1)), _cmd(1, 19, i32(99), i32(LEAVE_TEXT), i32(-1))], [_go(3)]),
         3: _st([_cmd(1, 10, i32(1))], [_go(4, wait_menu(1))]),
         4: _st([], [_go(10 * (r + 1), menu_pick(r + 1)) for r in range(len(f['waves']))] + [_go(90, menu_pick(9)), _go(99)]),
         90: _st([], [_ret(0)]),
         99: _st([], [_ret(1)])}
    for r, cost in enumerate(f['cost']):
        s = 10 * (r + 1)
        code = r + 1
        shards = has_shards(int(f['shard']), int(cost))
        # 会话里：房主照常（确认框写明队员会一起进），队员只看提示（由房主开始）
        g[s] = _st([], [_go(s + 7, flag_is_on(COOP_HOST)), _go(s + 6, flag_is_on(COOP_SESSION)), _go(s + 1, shards), _go(s + 5)])
        g[s + 6] = _st([_cmd(6, DIALOG_GID, i32(COOP_TEXT))], [_go(1, CONFIRM_NO)])
        g[s + 7] = _st([], [_go(s + 8, shards), _go(s + 5)])
        g[s + 8] = _st([_cmd(6, CONFIRM_GID, i32(HOST_TEXT0 + 10 * x + r))], [_go(s + 2, CONFIRM_YES), _go(1, CONFIRM_NO)])
        g[s + 1] = _st([_cmd(6, CONFIRM_GID, i32(TALK_TEXT0 + 30 + 10 * x + r))], [_go(s + 2, CONFIRM_YES), _go(1, CONFIRM_NO)])
        g[s + 2] = _st([_cmd(1, 11, i32(f['len0']), i32(code & 1)), _cmd(1, 11, i32(f['len0'] + 1), i32((code >> 1) & 1)),
                        _cmd(1, 11, i32(f['req']), i32(1))], [_go(99)])
        g[s + 5] = _st([_cmd(6, DIALOG_GID, i32(TALK_TEXT0 + 20 + r))], [_go(1, CONFIRM_NO)])
    return g


def patch_statue(e, f, x):
    """原版：说话 → 「解锁 / 联机检查」状态机（结果 0 打开竞技场菜单 1:151，1 没解锁，2 离线提示）。
    把调用它的那个状态换成调用我们的菜单：返回 0 → 原样走原版那一步，返回 1 → 回到等说话"""
    groups = e['groups']
    if MENU_GID in groups:
        raise RuntimeError('已经改过')
    hit = [(gid, sid) for gid, g in groups.items() for sid, st in g.items() if any((c['bank'], c['id']) == (1, 151) for c in st['entry'])]
    if len(hit) != 1:
        raise RuntimeError('找不到打开竞技场菜单（1:151）的状态：%s' % hit)
    gid, s151 = hit[0]
    g = groups[gid]
    calls = [sid for sid, st in g.items() if len(st['entry']) == 1 and st['entry'][0]['bank'] == 6
             and any(sc['target'] == s151 for c in st['conds'] for sc in c['sub'])]
    if len(calls) != 1:
        raise RuntimeError('找不到调用「解锁 / 联机检查」的状态：%s' % calls)
    s5 = calls[0]
    back = g[0]['conds'][0]['target']                                   # 等说话的状态（状态 0 第一步就去那里）
    sv = max(g) + 1
    g[sv] = g[s5]
    g[s5] = _st([_cmd(6, MENU_GID)], [{'target': None, 'eval': CONFIRM_YES, 'pass': [], 'sub': [_go(sv)]},
                                       {'target': None, 'eval': CONFIRM_NO, 'pass': [], 'sub': [_go(back)]}])
    groups[CONFIRM_GID] = confirm_group()
    groups[DIALOG_GID] = dialog_group()
    groups[MENU_GID] = menu_group(f, x)


def files(cx, tmp):
    f = feat(cx)
    if not f:
        return
    prepare(cx)
    by_talk = {}
    for co in f['colos']:
        x = co['x']
        if x not in cx.arena_ok:
            continue
        out = dict(cx.arena_out[x])
        try:
            for s in co['statues']:                                     # 雕像地图这次被别的功能写过：在它的基础上重做
                rel = rel_map(s['map'])
                if os.path.isfile(os.path.join(tmp, rel)):
                    out[rel] = run_batch(s['map'] + '_tmp', os.path.join(tmp, rel), statue_spec(s))
        except Exception as ex:
            cx.notes.append('斗技场试炼：%s 的雕像地图没做成（%s）' % (co['map'], ex))
            continue
        for rel, blob in out.items():
            os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
            open(os.path.join(tmp, rel), 'wb').write(blob)
        for s in co['statues']:
            by_talk.setdefault(talk_of(s['map']), []).append((s['esd'], x))
    n = 0
    for tm, scripts in sorted(by_talk.items()):
        rel = rel_talk(tm)
        src = src_file(cx, rel, tmp)
        try:
            if not src:
                raise RuntimeError('找不到对话包')
            bnd = erlib.Bnd4(erlib.dcx_decompress(open(src, 'rb').read()))
            for sc, cx_x in scripts:
                name = next((nm for nm in bnd.entries if re.split(r'[\\/]', nm)[-1].lower() == sc + '.esd'), None)
                if name is None:
                    raise RuntimeError('对话包里没有 %s' % sc)
                e = esdlib.read(bytes(bnd.get(name)))
                patch_statue(e, f, cx_x)
                bnd.put(name, write_check(e))
                n += 1
        except Exception as ex:
            cx.notes.append('斗技场试炼：%s 的雕像对话没改成（%s）' % (tm, ex))
            continue
        os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
        erlib.write_dcx_file(os.path.join(tmp, rel), bytes(bnd.data))
    cx.arena_statues = n


def texts(cx, key):
    f = feat(cx)
    if not f:
        return {}
    zh = key == 'zh'
    talk, mp = {}, {}
    for r, (w, cost) in enumerate(zip(f['waves'], f['cost'])):
        talk[TALK_TEXT0 + r] = RUN_ZH % (w, cost) if zh else RUN_EN % (w, cost, '' if cost == 1 else 's')
        for co in f['colos']:                         # 确认框：按竞技场写明敌人强度（TALK_TEXT0 + 30 + 10 × 竞技场 + 场次）
            sz, se = STRENGTH.get(co['x'], ('', ''))
            talk[TALK_TEXT0 + 30 + 10 * co['x'] + r] = (
                ('消耗 %d 个星光碎片，挑战 %d 波斗技场试炼？\n敌人强度：%s\n魇化精英与 Boss 轮流出场，每打完一波奖励直接放进背包，之后可以选择继续或离开；'
                 '途中死亡会收回这次试炼得到的全部奖励。') % (cost, w, sz) if zh else
                ('Spend %d Starlight Shard%s to take on a %d-wave Colosseum Trial?\nEnemy strength: %s\nNightmare elites and bosses take turns. '
                 'Each cleared wave puts its rewards in your inventory; then continue or leave. '
                 'Dying takes back everything this trial gave you.') % (cost, '' if cost == 1 else 's', w, se))
            # 联机时房主的确认框（HOST_TEXT0 + 10 × 竞技场 + 场次）
            talk[HOST_TEXT0 + 10 * co['x'] + r] = (
                ('消耗 %d 个星光碎片，和队友一起挑战 %d 波斗技场试炼？\n敌人强度：%s\n队友会一起被传进竞技场，各自消耗自己的星光碎片，不够的只能帮忙、不拿奖励。'
                 '每打完一波由你选择继续或离开；倒下的人会收回自己这次得到的奖励，所有人都倒下才算失败。') % (cost, w, sz) if zh else
                ('Spend %d Starlight Shard%s to take on a %d-wave Colosseum Trial with your party?\nEnemy strength: %s\n'
                 'Your teammates are brought in too and spend their own shards; anyone without enough can help but gets no rewards. '
                 'You choose to continue or leave after each wave. Whoever falls loses the rewards this trial gave them; '
                 'the trial fails only if everyone falls.') % (cost, '' if cost == 1 else 's', w, se))
        talk[TALK_TEXT0 + 20 + r] = ('需要 %d 个星光碎片' % cost) if zh else ('Requires %d Starlight Shard%s' % (cost, '' if cost == 1 else 's'))
    talk[TALK_TEXT0 + 3] = '竞技场（联机对战）' if zh else 'Colosseum (online)'
    talk[COOP_TEXT] = ('联机时由房主在雕像开始斗技场试炼，你会和房主一起被传进竞技场。' if zh else
                       'During co-op the host starts Colosseum Trials at a statue, and you are brought in with them.')
    mp[ASK_TEXT] = ('继续挑战下一波吗？\n选择「否」离开斗技场，已经得到的奖励保留' if zh else
                    'Continue to the next wave?\nChoose "No" to leave the colosseum and keep the rewards you have')
    for v, (_k, z, en) in enumerate(f['notes']):
        mp[f['note_text0'] + v + 1] = z if zh else en
    out = {'EventTextForTalk': talk, 'EventTextForMap': mp}
    if f.get('banner'):
        out['GR_MenuText'] = {BANNER_TEXT: 'TRIAL COMPLETE'}      # 原版大字幕中文版也是英文（用户 2026-11-10：用「试炼完成」的英文）
    return out
