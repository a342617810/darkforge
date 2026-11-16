# -*- coding: utf-8 -*-
"""重随沿用（用户 2026-11-04「改成沿用」）：输入都没变就不重做，直接用上次的重随包（--out）和修补过的地图（--maps-out）。

输入（parts）：
  code 重随真正用到的代码（rr\\*.py 和它们 import 到的 reroll 下的模块，按内容；menu.py、scripts.py、sc\\ 这些改了不用重做重随）；
  data data\\ 下重随读的文件（菜单、标题封面的贴图、只有游戏脚本用的不算；Boss 模组只算这次加载的）；settings settings.json（按内容）；
  base 基础 regulation；msg 文字包来源；game 游戏版本（Data0 / Data3 / eldenring.exe）；
  rand 随机器的输出和 diste 里读的那几样（没开敌人随机也读 diste：Boss 的多阶段、原版地图）；args 命令行参数；
  state 一次性重随记录（--state，按内容；重随会往里记，所以记的是跑完以后的内容）。
  种子不算：结果由一次性重随记录和这一局的种子（once.world_seed，也记在里面）定，--seed 只在第一次抽、还没有记录时用。
文件按大小 + 修改时间算（settings、一次性记录按内容）。
沿用还要输出没被动过：重随包和修补地图里的文件（大小、修改时间）和上次跑完时一样（reroll_report.txt 不算，沿用时只改它的时间行）。
dll\\dark_core / dark_sell 旁边的定义文件不在输出目录里，可能被另一种模式的重随改过：上次写的内容记在指纹文件里，沿用时对不上就写回去。
跑完整重随前先删掉指纹文件：中途失败不会留下「对得上」的旧指纹。"""
from .common import *  # noqa: F401,F403
import hashlib
import re
import time

SIG_FILE = 'reroll_source.json'
VERSION = 'reuse1'
REPORT = 'reroll_report.txt'
# data\\ 下重随不读的（菜单 / 标题封面的贴图：menu 里只读 Data3 的密钥；后面几个只有 scripts.py 用）：改它们不用重做重随
DATA_SKIP = ('menu', 'bossmods', 'gracemenu', 'guide.json', 'torrent', 'msbtool')
MENU_KEY = os.path.join('menu', 'data3_key.pem')
NAMES = {'ver': '格式', 'code': '重随代码', 'data': '重随数据', 'settings': '设置', 'base': '基础 regulation', 'msg': '文字包',
         'game': '游戏版本', 'rand': '随机器输出', 'args': '启动参数', 'state': '一次性重随记录', 'out': '重随包里的文件', 'maps': '修补过的地图'}


def _h(*items):
    h = hashlib.sha1()
    for x in items:
        h.update((x if isinstance(x, str) else repr(x)).encode('utf-8', 'replace'))
        h.update(b'\0')
    return h.hexdigest()


def _stat(p):
    try:
        st = os.stat(p)
        return '%s|%d|%d' % (os.path.abspath(p), st.st_size, st.st_mtime_ns)
    except OSError:
        return '%s|-' % os.path.abspath(p)


def _tree(d, skip=()):
    """目录下所有文件（含子目录）：[(相对路径, 大小, 修改时间)]，按路径排；目录不在返回 []"""
    out = []
    if not d or not os.path.isdir(d):
        return out
    for root, dirs, files in os.walk(d):
        dirs[:] = sorted(x for x in dirs if x != '__pycache__')
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, d).replace('\\', '/')
            if rel in skip:
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((rel, st.st_size, st.st_mtime_ns))
    return out


def _content(p):
    try:
        return hashlib.sha1(open(p, 'rb').read()).hexdigest()
    except OSError:
        return '-'


def state_part(a):
    """一次性重随记录（按内容）：--state 没有时看老位置（once._legacy，重随读它）"""
    from . import once
    p = a.state if os.path.isfile(a.state) else (once._legacy(a.state) or a.state)
    return _h(os.path.abspath(a.state), _content(p))


def code_files(here):
    """重随真正用到的代码：reroll.py、rr\\*.py，加上它们 import 到的 reroll 目录下的模块（往下一层层找）"""
    scan = [os.path.join(here, 'reroll.py')] + sorted(glob.glob(os.path.join(here, 'rr', '*.py')))
    seen = set()
    while scan:
        p = scan.pop()
        if p in seen:
            continue
        seen.add(p)
        t = open(p, encoding='utf-8-sig').read()
        mods = [x.strip().split()[0] for m in re.findall(r'^\s*import\s+(.+)$', t, re.M) for x in m.split(',') if x.strip()]
        mods += re.findall(r'^\s*from\s+([A-Za-z_]\w*)\S*\s+import\b', t, re.M)
        scan += [f for f in (os.path.join(here, m.split('.')[0] + '.py') for m in mods) if os.path.isfile(f)]
    return sorted(seen)


def data_part(here, boss_mods):
    """data\\ 下重随读的文件（见 DATA_SKIP）的指纹；Boss 模组只算这次加载的"""
    d = os.path.join(here, 'data')
    items = [(e, _tree(os.path.join(d, e)) if os.path.isdir(os.path.join(d, e)) else _stat(os.path.join(d, e)))
             for e in sorted(os.listdir(d)) if e not in DATA_SKIP]
    items.append(_stat(os.path.join(d, MENU_KEY)))
    items += [(k, _tree(os.path.join(d, 'bossmods', k))) for k in sorted(x for x in (boss_mods or '').split(',') if x)]
    return _h(*items)


def inputs(a, here, langs):
    """跑重随之前算：除了一次性重随记录以外的输入，{名字: 指纹}"""
    import vanilla as vsrc
    P = {'ver': VERSION}
    P['code'] = _h(*[(os.path.relpath(p, here), _content(p)) for p in code_files(here)])
    P['data'] = data_part(here, getattr(a, 'boss_mods', ''))
    P['settings'] = _content(a.settings)
    P['base'] = _stat(a.base_reg)
    msg = []
    for lang in langs:
        src = next((p for p in (os.path.join(d, lang, 'item_dlc02.msgbnd.dcx') for d in a.msg_src) if os.path.isfile(p)), None)
        msg.append(_stat(src) if src else lang + '|-')
    P['msg'] = _h(*msg)
    g = vsrc.game_dir()
    P['game'] = _h(*[_stat(os.path.join(g, f)) for f in ('Data0.bhd', 'Data3.bhd', 'Data3.bdt', 'eldenring.exe')]) if g else '-'
    rd = a.randomizer_dir or os.path.normpath(os.path.join(here, '..', '..', 'randomizer'))
    from .stage3 import diste            # 高难度世界里没有 diste，用旁边随机器目录的
    rp = [_stat(os.path.join(rd, 'EldenRingRandomizer.exe')), _stat(diste(rd, 'Base', 'enemy.txt'))] + \
        [_stat(p) for p in sorted(glob.glob(diste(rd, 'Vanilla', '*.msb.dcx')))]
    if a.randomizer_dir:
        rp += [_tree(os.path.join(rd, sub)) for sub in ('map', 'event', 'spoiler_logs')]
    P['rand'] = _h(*rp)
    P['args'] = _h(os.path.abspath(a.out), os.path.abspath(a.base_reg), [os.path.abspath(d) for d in a.msg_src], a.label, a.noop,
                   os.path.abspath(a.settings), a.randomizer_dir and os.path.abspath(a.randomizer_dir), a.maps_out and os.path.abspath(a.maps_out))
    if getattr(a, 'boss_mods', ''):        # 加载了 Boss 模组才算进去（不加载时和整合前的记录对得上，照样沿用）
        P['args'] = _h(P['args'], 'boss_mods', a.boss_mods, getattr(a, 'boss_arena', ''))
    return P


def _outputs(a):
    return {'out': _h(_tree(a.out, skip=(SIG_FILE, REPORT))), 'maps': _h(_tree(a.maps_out)) if a.maps_out else '-'}


def _key(path, dirs):
    """定义文件 → 记录里的键（dirs 的名字 / 文件名；safe_reroll 改了目录也对得上）"""
    for k, d in dirs.items():
        if os.path.normcase(os.path.abspath(os.path.dirname(path))) == os.path.normcase(os.path.abspath(d)):
            return k + '/' + os.path.basename(path)
    return None


def check(a, pre, dirs):
    """沿用得上返回上次的记录；对不上返回 None，并在日志里说哪样变了（第一次没有记录不说）"""
    p = os.path.join(a.out, SIG_FILE)
    try:
        rec = json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return None
    now = dict(pre, state=state_part(a), **_outputs(a))
    old = rec.get('parts') or {}
    diff = [k for k in now if old.get(k) != now[k]]
    if diff:
        log('  重随：%s变了，重新做' % '、'.join(NAMES.get(k, k) for k in diff))
        return None
    return rec


def restore_defs(rec, dirs):
    """DLL 旁边的定义文件写回上次的内容（被别的重随改过才写）；返回写了几个"""
    n = 0
    for key, text in (rec.get('defs') or {}).items():
        d = dirs.get(key.split('/', 1)[0])
        if not d or not os.path.isdir(d):
            continue
        path = os.path.join(d, key.split('/', 1)[1])
        cur = open(path, encoding='utf-8', newline='').read() if os.path.isfile(path) else None
        if cur == text:
            continue
        if text is None:
            os.remove(path)
        else:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8', newline='') as f:
                f.write(text)
            os.replace(tmp, path)
        n += 1
    return n


def touch_report(a, rec):
    """报告的时间行换成这次（启动器「上次启动」看它），下面记一行沿用的哪一次"""
    p = os.path.join(a.out, REPORT)
    try:
        lines = open(p, encoding='utf-8').read().split('\n')
    except OSError:
        return
    lines = [l for l in lines if not l.startswith('沿用：')]
    for i, l in enumerate(lines):
        if l.startswith('时间：'):
            lines[i] = '时间：%s' % time.strftime('%Y-%m-%d %H:%M:%S')
            lines.insert(i + 1, '沿用：输入没变，结果是 %s 那次重随的（当时用时 %.1f 秒）' % (rec.get('time', '?'), rec.get('secs', 0)))
            break
    open(p, 'w', encoding='utf-8').write('\n'.join(lines))


def clear(a):
    p = os.path.join(a.out, SIG_FILE)
    if os.path.isfile(p):
        os.remove(p)


def save(a, pre, dirs, def_paths, seed, secs):
    """完整重随跑完：记下输入、输出的指纹和这次写的定义文件"""
    defs = {}
    for path in def_paths:
        k = _key(path, dirs)
        if k and os.path.isdir(os.path.dirname(path)):
            defs[k] = open(path, encoding='utf-8', newline='').read() if os.path.isfile(path) else None
    rec = {'parts': dict(pre, state=state_part(a), **_outputs(a)), 'defs': defs, 'seed': seed, 'secs': round(secs, 1),
           'time': time.strftime('%Y-%m-%d %H:%M:%S')}
    tmp = os.path.join(a.out, SIG_FILE + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(a.out, SIG_FILE))
