# -*- coding: utf-8 -*-
"""launch 模块（launcher.ps1 的「生成 ini」「启动游戏」「Boss 模组」「动作：启动」「状态显示」、Start-CrashWatch）的对照测试。

每组用例在两份一样的整合包副本上跑（PowerShell 一份、Python 一份：tmp\\<组>\\ps、tmp\\<组>\\py，路径一样长），各自一套假的 APPDATA；
比返回值、输出的行、写出的文件（路径换成 <T>，个别组把时间换成 <TS> / <TIME>）。
- 包里的 Python 工具（reroll\\scripts.py、menu.py、vanilla.py、reroll.py）换成假的：按 <根>\\fake_ctl.json 输出、退出，
  把收到的参数和 DR_PROGRESS / PYTHONIOENCODING 记进 <根>\\fake_calls.jsonl。Find-Python 两边都固定成包里的 python.exe
  （副本里没有 launcher\\python；PowerShell 那边覆盖 Find-Python，Python 那边设 ctx.PythonExe）。
- 不启动、不结束真的进程：Stop-EldenRing / Start-YafGame / Start-CrashWatch 在 PowerShell 那边覆盖 Get-Process / Start-Process / Start-Sleep，
  Python 那边换掉 win.find_pids / win.kill_pid / win.Proc / launch._sleep / launch._start，比调用的顺序和拼出来的命令行。
- 有意的不同：Start-CrashWatch 找不到 pythonw / spawn.py 时 PowerShell 退回隐藏窗口的 powershell，Python 只提示一句不看守（单独断言）；
  exception 的说明文字（.NET 和 Python 写法不同）只比前缀。
运行：launcher\\python\\python.exe -X utf8 dev\\launcher_py\\tests\\test_launch.py"""
import base64
import contextlib
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import PALY, copy_root, fake_env, ps_call, py_call, same  # noqa: E402
from dfl import launch, pytool, win  # noqa: E402
from dfl.core import Rec  # noqa: E402

PYEXE = os.path.join(PALY, 'launcher', 'python', 'python.exe')
GAME = os.path.dirname(os.path.dirname(PALY))
GAME_EXE = os.path.join(GAME, 'Game', 'eldenring.exe')
BOSSMODS = os.path.join(PALY, 'launcher', 'reroll', 'data', 'bossmods')
BOSS_KEYS = [k for k in os.listdir(BOSSMODS) if os.path.isfile(os.path.join(BOSSMODS, k, 'mod.json'))]
ITEMS = tuple('launcher\\' + n for n in ('launcher.ps1', 'backup.ps1', 'randomize.ps1', 'ui.ps1', 'coopcode.ps1', 'usermods.ps1',
                                         'YAFSML.ini.tpl', 'spawn.py', 'df.py', 'version.txt', 'game_path.txt', 'ersc_locale'))
EXTRA = ('launcher\\reroll\\settings.json',) + tuple('launcher\\reroll\\data\\bossmods\\%s\\mod.json' % k for k in BOSS_KEYS)
STEAM_ID = '76561190000000000'
FAILS = []
COUNT = [0]

FAKE_TOOL = r'''# -*- coding: utf-8 -*-
import json, os, sys, time
name = os.path.splitext(os.path.basename(__file__))[0]
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    ctl = json.load(open(os.path.join(root, 'fake_ctl.json'), encoding='utf-8')).get(name, {})
except Exception:
    ctl = {}
with open(os.path.join(root, 'fake_calls.jsonl'), 'a', encoding='utf-8') as f:
    f.write(json.dumps({'tool': name, 'argv': sys.argv[1:], 'progress': os.environ.get('DR_PROGRESS'),
                        'enc': os.environ.get('PYTHONIOENCODING')}, ensure_ascii=False) + '\n')
for l in ctl.get('out', []):
    print(l, flush=True)
if ctl.get('err'):
    time.sleep(0.3)
    for l in ctl['err']:
        sys.stderr.write(l + '\n')
    sys.stderr.flush()
    time.sleep(0.3)
for l in ctl.get('out2', []):
    print(l, flush=True)
if 'json' in ctl:
    print(json.dumps(ctl['json'], ensure_ascii=False), flush=True)
sys.exit(ctl.get('code', 0))
'''


# ---------------------------------------------------------------- 小工具
def first_diffs(a, b, path='', out=None):
    """两个结构里不一样的地方（路径、两边的值），最多 8 处"""
    out = [] if out is None else out
    if len(out) >= 8:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            if a.get(k, '<没有>') != b.get(k, '<没有>'):
                first_diffs(a.get(k, '<没有>'), b.get(k, '<没有>'), path + '/' + str(k), out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                first_diffs(x, y, path + '[%d]' % i, out)
    elif isinstance(a, str) and isinstance(b, str) and '\n' in a + b:
        la, lb = a.split('\n'), b.split('\n')
        for i in range(max(len(la), len(lb))):
            x = la[i] if i < len(la) else '<没有>'
            y = lb[i] if i < len(lb) else '<没有>'
            if x != y:
                out.append((path + ' 第 %d 行' % (i + 1), x, y))
                if len(out) >= 8:
                    break
    else:
        out.append((path, a, b))
    return out


def check(name, a, b):
    COUNT[0] += 1
    if a == b:
        print('OK   ' + name)
        return
    print('DIFF ' + name)
    for p_, x, y in first_diffs(a, b):
        print('   %s\n      PS: %s\n      PY: %s' % (p_, json.dumps(x, ensure_ascii=False)[:600], json.dumps(y, ensure_ascii=False)[:600]))
    FAILS.append(name)


def j(x):
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def q(s):
    """PowerShell \u5b57\u7b26\u4e32\u5b57\u9762\u91cf\u3002\u6709\u6362\u884c\u7684\u5199\u6210\u53cc\u5f15\u53f7\u52a0 `r`n\uff08\u6d4b\u8bd5\u6846\u67b6\u6309\u6587\u672c\u65b9\u5f0f\u5199 .ps1\uff0c\u539f\u6837\u7684 \\r\\n \u4f1a\u53d8\u6210 \\r\\r\\n\uff09"""
    if s is None:
        return '$null'
    if '\r' in s or '\n' in s:
        for a, b in (('`', '``'), ('"', '`"'), ('$', '`$'), ('\u201c', '`\u201c'), ('\u201d', '`\u201d'), ('\u201e', '`\u201e'),
                     ('\r', '`r'), ('\n', '`n')):
            s = s.replace(a, b)
        return '"' + s + '"'
    for ch in "'\u2018\u2019\u201a\u201b":
        s = s.replace(ch, ch + ch)
    return "'" + s + "'"


def qa(xs):
    return '@(' + ','.join(q(x) for x in xs) + ')'


def touch(p, data=b''):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))


def rm(p):
    if os.path.isdir(p):
        shutil.rmtree(p)
    elif os.path.exists(p):
        os.remove(p)


def set_mtime(p, dt):
    t = time.mktime(dt.timetuple())
    os.utime(p, (t, t))


def hide(p):
    import ctypes
    ctypes.windll.kernel32.SetFileAttributesW(p, 0x2)


def fdesc(fp):
    if os.path.basename(fp) == 'dlg.txt':            # 假弹窗的记录：两边各写各的 JSON 格式，解析了比
        with open(fp, encoding='utf-8') as f:
            return [json.loads(l) for l in f if l.strip()]
    raw = open(fp, 'rb').read()
    if len(raw) > 65536:
        return 'SIZE:%d' % len(raw)
    return ('BOM:' if raw.startswith(b'\xef\xbb\xbf') else '') + raw.decode('utf-8', 'replace')


def snap(base, rels):
    out = {}
    for rel in rels:
        p = os.path.join(base, rel)
        if os.path.isdir(p):
            for d, _, files in os.walk(p):
                for n in files:
                    fp = os.path.join(d, n)
                    out[os.path.relpath(fp, base).replace('\\', '/')] = fdesc(fp)
        elif os.path.isfile(p):
            out[rel.replace('\\', '/')] = fdesc(p)
        else:
            out[rel.replace('\\', '/')] = None
    return out


def normalize(x, subs, times=False):
    if isinstance(x, str):
        for a, b in subs:
            x = x.replace(a, b)
        if times:
            x = re.sub(r'\d{8}_\d{6}', '<TS>', x)
            x = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '<TIME>', x)
            x = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', '<TIME>', x)
        return x
    if isinstance(x, list):
        return [normalize(v, subs, times) for v in x]
    if isinstance(x, dict):
        return {normalize(k, subs, times): normalize(v, subs, times) for k, v in x.items()}
    return x


@contextlib.contextmanager
def patched(obj, **kw):
    old = {k: getattr(obj, k, None) for k in kw}
    for k, v in kw.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(obj, k, v)


PS_FINDPY = 'function Find-Python { return %s }\n' % q(PYEXE)


def wrap(fn, pre=None):
    def w(ctx):
        ctx.PythonExe = PYEXE
        if pre:
            pre(ctx)
        return fn(ctx)
    return w


class Pair:
    """两份一样的副本：tmp\\<名字>\\ps、tmp\\<名字>\\py"""

    def __init__(self, tmp, name, setup=None):
        self.base, self.root, self.env = {}, {}, {}
        for s in ('ps', 'py'):
            b = os.path.join(tmp, name, s)
            os.makedirs(b)
            self.base[s] = b
            self.root[s] = copy_root(b, items=ITEMS, extra=EXTRA)
            for k in BOSS_KEYS:
                os.makedirs(os.path.join(self.root[s], 'launcher', 'reroll', 'data', 'bossmods', k, 'files'), exist_ok=True)
                if os.path.isdir(os.path.join(BOSSMODS, k, 'arena')):
                    os.makedirs(os.path.join(self.root[s], 'launcher', 'reroll', 'data', 'bossmods', k, 'arena'), exist_ok=True)
            for t in ('scripts', 'menu', 'vanilla', 'reroll'):
                touch(os.path.join(self.root[s], 'launcher', 'reroll', t + '.py'), FAKE_TOOL)
            e = fake_env(b)
            e['DARKFORGE_TEST_DIALOG'] = '0'
            e['DARKFORGE_TEST_DIALOG_LOG'] = os.path.join(b, 'dlg.txt')
            self.env[s] = e
            if setup:
                setup(self.root[s], e, b)

    def subs(self, s):
        b = self.base[s]
        return [(b.replace('\\', '\\\\'), '<T>'), (b, '<T>')]

    def ctl(self, d):
        for s in ('ps', 'py'):
            touch(os.path.join(self.root[s], 'fake_ctl.json'), json.dumps(d, ensure_ascii=False))

    def each(self, fn):
        for s in ('ps', 'py'):
            fn(self.root[s], self.env[s], self.base[s])

    def run(self, name, ps, py, files=(), ctx_args=None, times=False, extra_ps=None, extra_py=None):
        for s in ('ps', 'py'):
            rm(os.path.join(self.root[s], 'fake_calls.jsonl'))
            rm(os.path.join(self.base[s], 'dlg.txt'))
        a, oa = ps_call(PS_FINDPY + ps, self.env['ps'], root=self.root['ps'])
        b, ob = py_call(py, self.env['py'], root=self.root['py'], **(ctx_args or {}))
        fa = snap(self.base['ps'], ('root\\fake_calls.jsonl', 'dlg.txt') + tuple(files))
        fb = snap(self.base['py'], ('root\\fake_calls.jsonl', 'dlg.txt') + tuple(files))
        A = normalize([a, oa, fa] + ([extra_ps()] if extra_ps else []), self.subs('ps'), times)
        B = normalize([j(b), ob, fb] + ([extra_py()] if extra_py else []), self.subs('py'), times)
        check(name, A, B)
        return A, B


def ps_write(path, data):
    """PowerShell 里写 / 删一个文件（批量用例用）"""
    if data is None:
        return 'if (Test-Path -LiteralPath %s) { Remove-Item -LiteralPath %s -Force -Recurse }\n' % (q(path), q(path))
    b = data if isinstance(data, bytes) else data.encode('utf-8')
    return '[IO.File]::WriteAllBytes(%s, [Convert]::FromBase64String(%s))\n' % (q(path), q(base64.b64encode(b).decode()))


def py_write(path, data):
    if data is None:
        rm(path)
    else:
        touch(path, data)


# ---------------------------------------------------------------- 各组
def g_user_dll(tmp):
    """Get-UserDllLines / Test-UserDllSafe / Join-DllLines"""
    def setup(root, env, b):
        d = os.path.join(root, 'dll')
        for n in ('a.dll', 'B.dll', '_off.dll', 'ersc.dll', 'x.dllx', 'my-mod.dll', 'my_mod.dll', 'my mod.dll', 'a-b.dll', 'ab.dll', 'a_b.dll',
                  'Zeta.dll', 'é.dll', '.dll', 'readme.txt', 'sub\\c.dll', 'sub\\_d.dll', 'sub\\readme.txt', '_offdir\\e.dll', 'sub2\\nested\\f.dll',
                  'hidden.dll', 'hiddendir\\h.dll', 'ErdTools\\ErdTools.dll', 'alt\\eldenring_alt_saves.dll', 'souls_vision.dll',
                  'SeamlessCoop\\ersc.dll', 'ErdTools2\\erd_tools_x.dll'):
            touch(os.path.join(d, n), b'MZ')
        hide(os.path.join(d, 'hidden.dll'))
        hide(os.path.join(d, 'hiddendir'))
    p = Pair(tmp, 'userdll', setup)
    real_ini = open(os.path.join(PALY, 'dll', 'ErdTools', 'erd_tools.ini'), 'rb').read()
    inis = [
        ('没有 ini', None, 'rng', False, None),
        ('sl2 + 有 [PARAM]', b'[SAVE]\r\nsave_extension = sl2\r\n\r\n[PARAM]\r\nfoo = 1\r\n', 'rng', False, b'off\r\n'),
        ('已经对了', b'\xef\xbb\xbf[SAVE]\r\nsave_extension = rng\r\n[PARAM]\r\npersistent_lantern = 0\r\n', 'rng', False, b'on\r\n'),
        ('联机切单机', b'[save]\nSave_Extension=co2 ; c\n', 'rng', False, b'OFF'),
        ('没有两节', b'[DEBUG]\r\nx = 1\r\n\r\n\r\n', 'co2', False, None),
        ('-DryRun', b'[SAVE]\r\nsave_extension = sl2\r\npersistent_lantern = 1 ; x\r\n', 'rng', True, None),
        ('只改提灯', b'[PARAM]\r\npersistent_lantern = 1\r\nsave_extension = rng', 'rng', False, None),
        ('没有 ini + -DryRun', None, 'co2', True, b' off \r\n'),
        ('真的 erd_tools.ini（副本）联机', real_ini, 'co2', False, None),
        ('空的扩展名', b'save_extension =\r\n[PARAM]\n', 'rng', False, None),
    ]
    for name, ini, ext, dry, choice in inis:
        def prep(root, env, b, ini=ini, choice=choice):
            for k in ('ErdTools', 'ErdTools2'):
                for f in os.listdir(os.path.join(root, 'dll', k)):
                    if f.lower().startswith('erd_tools.ini'):
                        os.remove(os.path.join(root, 'dll', k, f))
                if ini is not None:
                    touch(os.path.join(root, 'dll', k, 'erd_tools.ini'), ini)
            py_write(os.path.join(root, 'launcher', 'reroll', 'state', 'enemy_info_mod.txt'), choice)
        p.each(prep)
        ps = '$script:ErdSaveExt = %s; %s$__r = Get-UserDllLines' % (q(ext), '$DryRun = $true; ' if dry else '')

        def py(ctx, ext=ext):
            ctx.ErdSaveExt = ext
            return sv_delay(launch.get_user_dll_lines(ctx))
        p.run('Get-UserDllLines ' + name, ps, wrap(py), files=('root\\dll',), ctx_args={'DryRun': dry}, times=True)
    # Join-DllLines：联机的 ersc.dll、YAFSML自定义.ini 的 [dll]
    for name, coop, pl in (('平常', '', None), ('联机', '..\\dll\\SeamlessCoop\\ersc.dll', None),
                           ('自定义 [dll]', '', '; YAFSML自定义.ini 的 [dll]\r\ncustom_a=C:\\a.dll'), ('都有', 'C:\\x\\ersc.dll', 'x=y')):
        ps = '$script:CoopDll = %s; %s$__r = Join-DllLines "; 无敌人随机：不需要额外 DLL"' % (
            q(coop), ('$script:PlayerLoad = @{ Dll = %s }; ' % q(pl)) if pl else '')

        def py(ctx, coop=coop, pl=pl):
            ctx.CoopDll = coop
            if pl:
                ctx.PlayerLoad = Rec(Dll=pl)
            return sv_delay(launch.join_dll_lines(ctx, '; 无敌人随机：不需要额外 DLL'))
        p.run('Join-DllLines ' + name, ps, wrap(py), files=('root\\dll',), times=True)


def sv_delay(s):
    """有意的不同（崩溃风险审查 2026-11-19 第 14 条）：敌人信息 mod（souls_vision）那一行 Python 加了 |delay,3000。
    加载了它就断言带着，再去掉和 PowerShell 比"""
    if isinstance(s, str) and 'user_souls_vision=' in s:
        COUNT[0] += 1
        if 'souls_vision.dll|delay,3000' not in s:
            FAILS.append('souls_vision 没带 |delay,3000')
            sys.__stdout__.write('DIFF 敌人信息 mod 那一行没带 |delay,3000（有意的不同）：' + s + '\n')
        return s.replace('souls_vision.dll|delay,3000', 'souls_vision.dll')
    return s


def g_enemy_info(tmp):
    """Get-/Set-EnemyInfoChoice、Test-EnemyInfoMod、Show-TopYesNo"""
    p = Pair(tmp, 'enemyinfo')
    for name, data in (('没有', None), ('on', b'on\r\n'), ('OFF', b'OFF'), ('BOM off', b'\xef\xbb\xbfoff\r\n'), ('空格', b' off \r\n'),
                       ('第一行空', b'\r\noff'), ('别的', b'maybe\r\n'), ('CR', b'off\rx'), ('GBK', b'\xb9\xd8\r\n')):
        p.each(lambda r, e, b, data=data: py_write(os.path.join(r, 'launcher', 'reroll', 'state', 'enemy_info_mod.txt'), data))
        p.run('Get-EnemyInfoChoice ' + name, '$__r = @{ c = Get-EnemyInfoChoice; t = Test-EnemyInfoMod }',
              wrap(lambda c: {'c': launch.get_enemy_info_choice(c), 't': launch.test_enemy_info_mod(c)}))
    for v in ('on', 'off', ''):
        p.each(lambda r, e, b: rm(os.path.join(r, 'launcher', 'reroll', 'state')))
        p.run('Set-EnemyInfoChoice %r' % v, 'Set-EnemyInfoChoice %s' % q(v), wrap(lambda c, v=v: launch.set_enemy_info_choice(c, v)),
              files=('root\\launcher\\reroll\\state',))
    for ans in ('0', '1', '-1', '2'):
        for dn in (False, True):
            for s in ('ps', 'py'):
                p.env[s]['DARKFORGE_TEST_DIALOG'] = ans
            p.run('Show-TopYesNo 回答=%s DefaultNo=%s' % (ans, dn), '$__r = Show-TopYesNo "正文`r`n第二行" "标题" %s' % ('$true' if dn else '$false'),
                  wrap(lambda c, dn=dn: launch.show_top_yes_no('正文\r\n第二行', '标题', dn)))
    for s in ('ps', 'py'):
        p.env[s]['DARKFORGE_TEST_DIALOG'] = '0'


MODLINES = 'DR_Reroll=C:\\a\r\n; comment=x\r\n\r\n  DR_X = C:\\b  \n=bad\nnoeq\nk=v=w\r\n\tDR_Tab=\tC:\\t'


def g_scripts_menu(tmp):
    """Get-ScriptsLine / Get-MenuLine（假的 scripts.py / menu.py）"""
    p = Pair(tmp, 'scripts')
    for name, ctl in (('合并好了有提示', {'json': {'ok': True, 'warn': True, 'msg': '有提示'}}),
                      ('合并好了', {'out': ['进度 1', '{not json'], 'json': {'ok': True, 'msg': '合并了 3 个'}}),
                      ('失败', {'json': {'ok': False, 'msg': '坏了'}, 'err': ['Traceback (most recent call last):', '  File "x"', 'Error: y']}),
                      ('没有 JSON', {'out': ['没有结果'], 'err': ['e1'], 'code': 1}),
                      ('键是大写', {'json': {'OK': True, 'MSG': '大写', 'Warn': 0}}),
                      ('数字', {'json': {'ok': 1, 'msg': 5, 'warn': ''}}),
                      ('最后一个 JSON 算', {'out': ['{"ok": false, "msg": "前面的"}'], 'json': {'ok': True, 'msg': '后面的'}})):
        p.ctl({'scripts': ctl, 'menu': ctl})
        p.run('Get-ScriptsLine ' + name, '$__r = Get-ScriptsLine %s' % q(MODLINES), wrap(lambda c: launch.get_scripts_line(c, MODLINES)))
    p.ctl({'scripts': {'json': {'ok': True, 'msg': 'x'}}})
    p.run('Get-ScriptsLine 空的 [mod]', "$__r = Get-ScriptsLine ''", wrap(lambda c: launch.get_scripts_line(c, '')))
    with patched(pytool, find_python=lambda ctx: None):
        p.run('Get-ScriptsLine 找不到 Python', 'function Find-Python { return $null }\n$__r = Get-ScriptsLine "a=b"', lambda c: launch.get_scripts_line(c, 'a=b'))
        p.run('Get-MenuLine 找不到 Python', 'function Find-Python { return $null }\n$__r = Get-MenuLine', lambda c: launch.get_menu_line(c))
    title = {'normal': 'C:\\t\\normal', 'hard': 'C:\\t\\hard'}
    for name, ctl, cover in (('有封面 普通', {'json': {'ok': True, 'msg': '好了', 'title': title}}, None),
                             ('有封面 hard', {'json': {'ok': True, 'msg': '好了', 'title': title}}, 'hard'),
                             ('有封面 HARD', {'json': {'ok': True, 'msg': '好了', 'title': title}}, 'HARD'),
                             ('有封面 normal', {'json': {'ok': True, 'msg': '好了', 'title': title}}, 'normal'),
                             ('封面键大写', {'json': {'ok': True, 'msg': '好了', 'title': {'Normal': 'C:\\N'}}}, None),
                             ('没有这张封面', {'json': {'ok': True, 'msg': '好了', 'title': {'normal': 'C:\\N'}}}, 'hard'),
                             ('封面是空的', {'json': {'ok': True, 'msg': '好了', 'title': {}}}, None),
                             ('封面是字符串', {'json': {'ok': True, 'msg': '好了', 'title': 'x'}}, None),
                             ('没有封面', {'json': {'ok': True, 'msg': '好了'}}, None),
                             ('失败', {'json': {'ok': False, 'msg': '坏'}, 'err': ['boom']}, None),
                             ('没有输出', {}, None)):
        p.ctl({'menu': ctl})
        ps = ('$script:TitleCover = %s; ' % q(cover) if cover else '') + '$__r = Get-MenuLine'
        p.run('Get-MenuLine ' + name, ps, wrap(lambda c: launch.get_menu_line(c), lambda c, cover=cover: setattr(c, 'TitleCover', cover)))
    for t in ('scripts', 'menu'):
        p.each(lambda r, e, b, t=t: rm(os.path.join(r, 'launcher', 'reroll', t + '.py')))
    p.run('Get-ScriptsLine / Get-MenuLine 没有工具', '$__r = @((Get-ScriptsLine "a=b"), (Get-MenuLine))',
          wrap(lambda c: [launch.get_scripts_line(c, 'a=b'), launch.get_menu_line(c)]))


def setup_mods(root, env, b):
    touch(os.path.join(root, 'mods', 'look', 'parts', 'x.partsbnd.dcx'), b'x')
    touch(os.path.join(root, 'mods', 'nested', 'inner', 'chr', 'c.dcx'), b'x')
    os.makedirs(os.path.join(root, 'mods', '_off', 'parts'))
    os.makedirs(os.path.join(root, 'mods', 'empty'))
    touch(os.path.join(root, 'extra.dll'), b'MZ')
    touch(os.path.join(root, 'aftermod', 'sfx', 'a'), b'x')
    touch(os.path.join(root, 'YAFSML自定义.ini'), ('\ufeff[patch]\r\nskip_intro=0\r\nenable_ime=1\r\n[tweak]\r\nnew_key=5\r\n[log]\r\nlog_level=debug\r\n'
                                                   '[Extra]\r\nfoo=bar\r\npatch_mem=0\r\n[mod]\r\nmissing=D:\\nope\r\n[mod_after]\r\nlate=aftermod\r\n'
                                                   '[dll]\r\nmine=extra.dll|early\r\nsc=dll\\SeamlessCoop\\ersc.dll\r\n').encode('utf-8'))
    touch(os.path.join(root, 'dll', 'SeamlessCoop', 'ersc.dll'), b'MZ')
    touch(os.path.join(root, 'dll', 'a.dll'), b'MZ')


def g_ini(tmp):
    """Get-PlayerLoad / Write-IniFile / Show-IniDry"""
    def base_setup(root, env, b):
        os.makedirs(os.path.join(root, 'yafsml'))
        touch(os.path.join(root, 'dll', 'a.dll'), b'MZ')
        os.makedirs(os.path.join(root, 'out', 'reroll'))
    for nm, setup in (('没有自己的 mod', base_setup), ('有 mods 和自定义 ini', lambda r, e, b: (base_setup(r, e, b), setup_mods(r, e, b)))):
        p = Pair(tmp, 'ini_' + str(len(nm)), setup)
        p.run('Get-PlayerLoad ' + nm, '$__r = Get-PlayerLoad', wrap(launch.get_player_load), files=('root\\YAFSML自定义.ini',))
        p.ctl({'scripts': {'json': {'ok': True, 'msg': '合并了'}}, 'menu': {'json': {'ok': True, 'msg': '菜单', 'title': {'normal': 'C:\\T'}}}})
        modl = 'DR_Reroll=' + os.path.join('X', 'out', 'reroll')
        p.run('Write-IniFile ' + nm, 'Write-IniFile %s "; 无敌人随机：不需要额外 DLL"' % q(modl),
              wrap(lambda c: launch.write_ini_file(c, modl, '; 无敌人随机：不需要额外 DLL')), files=('root\\yafsml',))
        p.ctl({'scripts': {'json': {'ok': False, 'msg': '坏'}}, 'menu': {'code': 1}})
        p.run('Write-IniFile 覆盖包都失败 ' + nm, '$script:CoopDll = "..\\dll\\SeamlessCoop\\ersc.dll"; Write-IniFile "DR_A=C:\\a`nDR_B=C:\\b" "x=1"',
              wrap(lambda c: launch.write_ini_file(c, 'DR_A=C:\\a\nDR_B=C:\\b', 'x=1'), lambda c: setattr(c, 'CoopDll', '..\\dll\\SeamlessCoop\\ersc.dll')),
              files=('root\\yafsml',))

        def dry_ps(root):
            return 'Show-IniDry %s "; 无敌人随机：不需要额外 DLL"' % q(dry_mod(root))

        def dry_mod(root):
            return ('DR_Boss_godrick=' + os.path.join(root, 'launcher', 'reroll', 'data', 'bossmods', 'godrick', 'files') + '\r\n' +
                    'DR_Reroll=' + os.path.join(root, 'out', 'reroll') + '\r\nDR_Nope = C:\\nope  \r\n; DR_C=x\r\nother=1')
        p.run('Show-IniDry ' + nm, dry_ps(p.root['ps']), wrap(lambda c: launch.show_ini_dry(c, dry_mod(p.root['py']), '; 无敌人随机：不需要额外 DLL')))
    p = Pair(tmp, 'ini_notpl', base_setup)
    p.each(lambda r, e, b: os.remove(os.path.join(r, 'launcher', 'YAFSML.ini.tpl')))
    p.ctl({'scripts': {'json': {'ok': True, 'msg': 'x'}}, 'menu': {'json': {'ok': True, 'msg': 'y'}}})

    def py(c):
        try:
            launch.write_ini_file(c, 'a=b', 'c=d')
        except RuntimeError as e:
            return 'EXC:' + str(e)
    p.run('Write-IniFile 缺少模板', 'try { Write-IniFile "a=b" "c=d" } catch { $__r = "EXC:" + $_.Exception.Message }', wrap(py), files=('root\\yafsml',))


# ---------------------------------------------------------------- 进程（假的）
PS_PROC = r'''
$script:__seq = @(%s); $script:__gi = 0; $script:__killed = @(); $script:__sl = @(); $script:__sp = @()
function Get-Process { [CmdletBinding()] param([string]$Name)
    $i = $script:__gi; $script:__gi++
    $on = if ($i -lt $script:__seq.Count) { $script:__seq[$i] } else { $script:__seq[-1] }
    if ($on) {
        $a = [pscustomobject]@{ Id = 100; StartTime = [datetime]'2026-01-01 10:00:00' }
        $b = [pscustomobject]@{ Id = 200; StartTime = [datetime]'2026-01-01 11:00:00' }
        foreach ($o in @($a, $b)) { $o | Add-Member -MemberType ScriptMethod -Name Kill -Value { $script:__killed += @($this.Id) } }
        $a; $b
    }
}
function Start-Sleep { [CmdletBinding()] param([int]$Seconds = 0, [int]$Milliseconds = 0) $script:__sl += @([string]$Seconds + '/' + [string]$Milliseconds) }
function Start-Process { [CmdletBinding()] param([string]$FilePath, [string[]]$ArgumentList, [string]$WorkingDirectory, [string]$WindowStyle)
    $script:__sp += @('"' + $FilePath + '" ' + ($ArgumentList -join ' ') + ' |cwd=' + $WorkingDirectory + ' |ws=' + $WindowStyle) }
'''


class FakeProc:
    starts = {100: datetime.datetime(2026, 1, 1, 10), 200: datetime.datetime(2026, 1, 1, 11)}

    def __init__(self, pid):
        self.pid = pid

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def start_time(self):
        return FakeProc.starts.get(self.pid)


def proc_fakes(seq):
    st = {'gi': 0, 'killed': [], 'sl': [], 'sp': []}

    def find_pids(name):
        i = st['gi']
        st['gi'] += 1
        on = seq[i] if i < len(seq) else seq[-1]
        return [100, 200] if on else []

    def kill_pid(pid):
        st['killed'].append(pid)
        return True

    def sleep(x):
        st['sl'].append('%d/%d' % ((int(x), 0) if x >= 1 else (0, round(x * 1000))))

    def start(args, **kw):
        si = kw.get('startupinfo')
        ws = 'Minimized' if si is not None and si.wShowWindow == 2 else ''
        st['sp'].append(args + ' |cwd=' + kw.get('cwd', '') + ' |ws=' + ws)
    return st, find_pids, kill_pid, sleep, start


def run_proc(p, name, seq, ps_call_expr, py_fn, ctx_args=None, files=(), ps_pre='', times=True, py_pre=None):
    st, fp, kp, sl, stt = proc_fakes(seq)
    ps = (PS_PROC % ','.join('$true' if x else '$false' for x in seq)) + ps_pre + \
        ('$x = %s; if ($null -eq $x) { $x = $null }; $__r = @{ r = $x; gi = $script:__gi; killed = $script:__killed; sl = $script:__sl; sp = $script:__sp }'
         % ps_call_expr)

    def py(ctx):
        with patched(win, find_pids=fp, kill_pid=kp, Proc=FakeProc), patched(launch, _sleep=sl, _start=stt):
            x = py_fn(ctx)
        # 有意的不同（第 4 步）：崩溃看守 PowerShell 是 spawn.py → launcher.ps1 -Action watch，Python 是 df.py watch；比之前换成同一种写法
        sp = [re.sub(r'-I "([^"]*)\\df\.py" watch --game-pid (\d+)', lambda m: '-I "%s\\spawn.py" launcher.ps1 -Action watch -GamePid %s'
                     % (m.group(1), m.group(2)), s) for s in st['sp']]
        return {'r': x, 'gi': st['gi'], 'killed': st['killed'], 'sl': st['sl'], 'sp': sp}
    return p.run(name, ps, wrap(py, py_pre), ctx_args=ctx_args, files=files, times=times)


def g_processes(tmp):
    """Stop-EldenRing / Save-RunLogs / Start-YafGame / Start-CrashWatch"""
    p = Pair(tmp, 'stop')
    for name, seq in (('没在运行', [False]), ('结束后马上没了', [True, False]), ('等了几次', [True, True, True, True, False]), ('一直关不掉', [True])):
        run_proc(p, 'Stop-EldenRing ' + name, seq, '(Stop-EldenRing)', lambda c: launch.stop_elden_ring(c))

    # Save-RunLogs
    now = datetime.datetime.now()

    def logs_setup(root, env, b):
        d = os.path.join(root, 'dll')
        touch(os.path.join(d, 'dark_core', 'dark_core.log'), b'\0' * (2 * 1024 * 1024 + 1))
        touch(os.path.join(d, 'dark_lock', 'dark_lock.log'), b'small')
        touch(os.path.join(d, 'dark_sell', 'dark_sell.log'), b'\1' * (3 * 1024 * 1024))
        touch(os.path.join(d, 'dark_sell', 'dark_sell.log.old'), b'older')
        touch(os.path.join(d, 'dark_wings', 'dark_wings.log'), b'\2' * (2 * 1024 * 1024))
        touch(os.path.join(d, 'dark_slot', 'dark_slot.log'), b'\3' * (2 * 1024 * 1024 + 5))
        hide(os.path.join(d, 'dark_slot', 'dark_slot.log'))
        touch(os.path.join(root, 'yafsml', 'log', 'YAFSML.log'), b'old\r\n')
        touch(os.path.join(root, 'randomizer', 'dll', 'RandomizerCrashFix_log.txt'), b'\4' * (2 * 1024 * 1024 + 9))
        for n, days, hid in (('ertransmogrify_2026-10-01.log', 20, False), ('ertransmogrify_new.log', 0, False), ('ertransmogrify_h.log', 30, True),
                             ('other.log', 40, False), ('ertransmogrify_x.log.bak', 40, False)):
            f = os.path.join(d, 'logs', n)
            touch(f, b'x')
            set_mtime(f, now - datetime.timedelta(days=days))
            if hid:
                hide(f)
        touch(os.path.join(d, 'dark_ui', 'dark_ui.log'), b'ui log')
        set_mtime(os.path.join(d, 'dark_ui', 'dark_ui.log'), datetime.datetime(2026, 11, 10, 8, 30, 15))
        touch(os.path.join(d, 'souls_vision.log'), b'')
        for i in range(12):
            touch(os.path.join(root, 'launcher', 'logs', 'dll_runs', '202611%02d_120000_dark_ui.log' % (i + 1)), b'r')
        touch(os.path.join(root, 'launcher', 'logs', 'dll_runs', '20261101_120000_souls_vision.log'), b'sv')
    p = Pair(tmp, 'runlogs', logs_setup)
    p.run('Save-RunLogs', "Save-RunLogs '无敌人随机'", wrap(lambda c: launch.save_run_logs(c, '无敌人随机')),
          files=('root\\dll', 'root\\yafsml', 'root\\randomizer', 'root\\launcher\\logs'), times=True)
    p = Pair(tmp, 'runlogs2')
    p.run('Save-RunLogs 什么都没有', "Save-RunLogs ''", wrap(lambda c: launch.save_run_logs(c, '')),
          files=('root\\dll', 'root\\yafsml', 'root\\launcher\\logs'), times=True)

    # Start-YafGame
    def yaf_setup(root, env, b):
        touch(os.path.join(root, 'yafsml', 'YAFSML.exe'), b'MZ')
        touch(os.path.join(root, 'launcher', 'python', 'pythonw.exe'), b'MZ')
    p = Pair(tmp, 'yaf', yaf_setup)
    files = ('root\\yafsml', 'root\\launcher\\logs')
    run_proc(p, 'Start-YafGame -NoLaunch', [False], "(Start-YafGame '无敌人随机')", lambda c: launch.start_yaf_game(c, '无敌人随机'),
             ctx_args={'NoLaunch': True}, files=files, ps_pre='$NoLaunch = $true\n')
    run_proc(p, 'Start-YafGame -NoLaunch 版本核对过了', [False], "(Start-YafGame '无敌人随机')", lambda c: launch.start_yaf_game(c, '无敌人随机'),
             ctx_args={'NoLaunch': True}, files=files, ps_pre='$NoLaunch = $true; $script:GameVerOk = %s\n' % q(GAME_EXE.upper()),
             py_pre=lambda c: setattr(c, 'GameVerOk', GAME_EXE.upper()))
    run_proc(p, 'Start-YafGame 启动、第 3 秒看到游戏', [False, False, False, True], "(Start-YafGame '敌人随机')",
             lambda c: launch.start_yaf_game(c, '敌人随机'), files=files)
    run_proc(p, 'Start-YafGame 60 秒没看到', [False], "(Start-YafGame '敌人随机')", lambda c: launch.start_yaf_game(c, '敌人随机'), files=files)
    # 有意的不同（崩溃风险审查 2026-11-19 第 15 条）：游戏已在运行时 PowerShell 先结束它再启动，Python 报错、不结束也不启动。
    # 只跑 Python 这边（PowerShell 那边会写 YAFSML.log，两份副本就对不齐了）
    st, fp, kp, sl, stt = proc_fakes([True, True, False, True])

    def py_running(c):
        c.PythonExe = PYEXE
        with patched(win, find_pids=fp, kill_pid=kp, Proc=FakeProc), patched(launch, _sleep=sl, _start=stt):
            return launch.start_yaf_game(c, 'x')
    b, ob = py_call(py_running, p.env['py'], root=p.root['py'])
    COUNT[0] += 1
    ok = (b is False and not st['killed'] and not st['sp'] and not st['sl']
          and any(l.startswith('  [错误] 游戏还在运行') and '任务管理器' in l for l in ob))
    print(('OK   ' if ok else 'DIFF ') + 'Start-YafGame 游戏已在运行（有意的不同：Python 不结束游戏，报错不启动）')
    if not ok:
        print('   PY:', b, st, ob)
        FAILS.append('Start-YafGame 游戏已在运行')
    p.each(lambda r, e, b: touch(os.path.join(r, 'launcher', 'game_path.txt'), 'Q:\\nope\r\n'))
    run_proc(p, 'Start-YafGame 记下的游戏路径不对（自动检测）', [False], "(Start-YafGame 'x')", lambda c: launch.start_yaf_game(c, 'x'),
             ctx_args={'NoLaunch': True}, files=files + ('root\\launcher\\game_path.txt',), ps_pre='$NoLaunch = $true\n')
    p.each(lambda r, e, b: os.remove(os.path.join(r, 'yafsml', 'YAFSML.exe')))
    run_proc(p, 'Start-YafGame 没有 YAFSML', [False], "(Start-YafGame 'x')", lambda c: launch.start_yaf_game(c, 'x'), files=files)

    # Start-CrashWatch
    for pid in (0, -5):
        run_proc(p, 'Start-CrashWatch %d' % pid, [False], '(Start-CrashWatch %d)' % pid,
                 lambda c, pid=pid: (launch.start_crash_watch(c, pid), None)[1])
    # 有意的不同（第 4 步）：看守本身换成 Python 的。PowerShell 跑 spawn.py → launcher.ps1 -Action watch，Python 直接 pythonw df.py watch
    st, fp, kp, sl, stt = proc_fakes([False])
    a, _ = ps_call(PS_PROC % '$false' + '$x = Start-CrashWatch 4242; $__r = @($script:__sp)', p.env['ps'], root=p.root['ps'])

    def py_w(c):
        with patched(launch, _start=stt):
            return [launch.start_crash_watch(c, 4242), st['sp']]
    b, ob = py_call(py_w, p.env['py'], root=p.root['py'])
    COUNT[0] += 1
    sp = b[1][0] if b and len(b[1]) == 1 else ''
    sp = sp if isinstance(sp, str) else ' '.join(map(str, sp))
    ok = (len(a) == 1 and 'spawn.py' in str(a[0]) and '-Action watch -GamePid 4242' in str(a[0]) and b[0] is True
          and 'pythonw.exe" -I "' in sp and 'df.py" watch --game-pid 4242' in sp and not ob)
    print(('OK   ' if ok else 'DIFF ') + 'Start-CrashWatch 4242（有意的不同：看守换成 df.py watch）')
    if not ok:
        print('   PS:', a)
        print('   PY:', b, ob)
        FAILS.append('Start-CrashWatch 4242')
    # 有意的不同：没有 pythonw.exe。PowerShell 退回隐藏窗口的 powershell，Python 只提示、不看守
    p.each(lambda r, e, b: os.remove(os.path.join(r, 'launcher', 'python', 'pythonw.exe')))
    st, fp, kp, sl, stt = proc_fakes([False])
    a, _ = ps_call(PS_PROC % '$false' + '$x = Start-CrashWatch 4242; $__r = @($script:__sp)', p.env['ps'], root=p.root['ps'])

    def py(c):
        with patched(launch, _start=stt):
            return [launch.start_crash_watch(c, 4242), st['sp']]
    b, ob = py_call(py, p.env['py'], root=p.root['py'])
    COUNT[0] += 1
    ok = (len(a) == 1 and 'powershell.exe' in a[0] and '-Action watch -GamePid 4242' in a[0] and b == [False, []] and len(ob) == 1
          and ob[0].startswith('  [提示] 找不到 ') and '这次不开崩溃看守' in ob[0])
    print(('OK   ' if ok else 'DIFF ') + 'Start-CrashWatch 没有 pythonw（有意的不同：Python 不退回 powershell）')
    if not ok:
        print('   PS:', a)
        print('   PY:', b, ob)
        FAILS.append('Start-CrashWatch 没有 pythonw')


def g_vanilla_reroll(tmp):
    """Get-VanillaSource / Invoke-RerollGenerate"""
    p = Pair(tmp, 'vanilla')
    vok = {'json': {'ok': True, 'reg': 'C:\\v\\regulation.bin', 'msg': 'C:\\v\\msg', 'from': 'game', 'check': '是原版', 'vanilla': True}}
    for name, ctl in (('从游戏取', vok),
                      # check 是数字：用整数（小数经过 pytool.invoke_py_json 的 json.loads 成了 float，[string] 写不回 PowerShell 的「1.0」，见汇报）
                      ('vanilla 是字符串 false', {'json': {'ok': True, 'reg': 'r', 'msg': 'm', 'from': 'randomizer', 'check': 1, 'vanilla': 'false'}}),
                      ('vanilla 是 0', {'json': {'ok': True, 'reg': 'r', 'msg': 'm', 'from': None, 'vanilla': 0}}),
                      ('失败', {'json': {'ok': False, 'msg_err': '读不了 Data0'}, 'err': ['Traceback', 'Boom']}),
                      ('失败没说原因', {'json': {'ok': False}}),
                      ('没有输出', {'err': ['crash'], 'code': 2})):
        p.ctl({'vanilla': ctl})
        ps = ('$a = Get-VanillaSource %s; $b = Get-VanillaSource %s; $__r = @{ a = $a; b = $b; err = $script:VanillaErr }' % (q(PYEXE), q(PYEXE)))

        def py(c):
            a = launch.get_vanilla_source(c, PYEXE)
            b = launch.get_vanilla_source(c, PYEXE)
            return {'a': a, 'b': b, 'err': getattr(c, 'VanillaErr', None)}
        p.run('Get-VanillaSource ' + name, ps, wrap(py))
    rer = {'out': ['重随开始', '§% 50', '中文 ✓'], 'err': ['警告 1', '警告 2'], 'out2': ['完成']}
    cases = [('无敌人随机', False, None, '', [], [], None, 0),
             ('敌人随机 全部参数', True, 20261118123456, 'C:\\s\\once_1.json', ['godrick', 'malenia'], ['godrick'], 'C:\\hi', 0),
             ('无敌人随机 带 Boss（场地不传）', False, 123, '', ['godrick'], ['godrick'], None, 0),
             ('敌人随机 默认世界', True, None, '', [], [], None, 0),
             ('重随失败', False, None, '', [], [], None, 3)]
    for name, rand, seed, state, keys, arena, world, code in cases:
        r2 = dict(rer, code=code)
        p.ctl({'vanilla': vok, 'reroll': r2})
        ps = ('$script:BossKeys = %s; $script:BossArena = %s; %s$__r = Invoke-RerollGenerate %s %s %s %s' % (
            qa(keys), qa(arena), ('$script:RandWorld = %s; ' % q(world)) if world else '', q(PYEXE), '$true' if rand else '$false',
            '$null' if seed is None else str(seed), q(state)))

        def py(c, rand=rand, seed=seed, state=state, keys=keys, arena=arena, world=world):
            c.BossKeys, c.BossArena = list(keys), list(arena)
            if world:
                c.RandWorld = world
            return launch.invoke_reroll_generate(c, PYEXE, rand, seed, state)
        p.run('Invoke-RerollGenerate ' + name, ps, wrap(py))
    p.ctl({'vanilla': {'json': {'ok': False, 'msg_err': '没有原版'}}, 'reroll': rer})
    p.run('Invoke-RerollGenerate 拿不到原版文件', '$script:BossKeys = @(); $__r = Invoke-RerollGenerate %s $false' % q(PYEXE),
          wrap(lambda c: (setattr(c, 'BossKeys', []), launch.invoke_reroll_generate(c, PYEXE, False))[1]))


def g_seed_rel(tmp):
    """Get-NewGameSeed / Get-YafRelPath"""
    save = os.path.join('AppData', 'Roaming', 'EldenRing', STEAM_ID)
    for name, rand, files in (('无敌人随机', False, {}), ('有存档', True, {save + '\\ER0000.rng': b'x'}),
                              ('存档名大小写不同', True, {save + '\\er0000.RNG': b'x'}), ('只有联机存档', True, {save + '\\ER0000.rngcoop': b'x'}),
                              ('新开局（有 once.json）', True, {'AppData\\Roaming\\EldenRing\\DarkReforged\\角色记录\\once.json': b'{}'}),
                              ('新开局（什么都没有）', True, {})):
        def setup(root, env, b, files=files):
            for k, v in files.items():
                touch(os.path.join(b, k), v)
        p = Pair(tmp, 'seed_%d' % len(os.listdir(tmp)), setup)

        def py(c, rand=rand):
            s = launch.get_new_game_seed(c, rand)
            return None if s is None else ('SEED14' if re.fullmatch(r'\d{14}', str(s)) else s)
        p.run('Get-NewGameSeed ' + name,
              '$s = Get-NewGameSeed %s; $__r = if ($null -eq $s) { $null } elseif ([string]$s -match "^\\d{14}$" -and $s -is [long]) { "SEED14" } else { $s }' % (
                  '$true' if rand else '$false'), wrap(py), files=('AppData', 'root\\launcher\\logs'), times=True)
    p = Pair(tmp, 'relpath')
    r = p.root['ps']
    rp = p.root['py']
    tests = lambda root: [root + '\\dll\\SeamlessCoop\\ersc.dll', root.upper() + '\\DLL\\x.dll', root + 'x\\dll\\a.dll', root, root + '\\',
                          'D:\\other\\ersc.dll', '']
    a, _ = ps_call('$__r = @(foreach ($f in %s) { Get-YafRelPath $f })' % qa(tests(r)), p.env['ps'], root=r)
    b, _ = py_call(lambda c: [launch.get_yaf_rel_path(c, f) for f in tests(rp)], p.env['py'], root=rp)
    check('Get-YafRelPath', normalize(a, p.subs('ps')), normalize(b, p.subs('py')))


def g_boss(tmp):
    """Get-BossMods / Get-TitleCover / Get-BossModMeta / Get-BossModName / Write-BossModeDef（批量：一个 PowerShell 进程里跑完一组）"""
    # Get-BossMods 只读 boss_mods：变体用小的 settings.json；'real' = 副本里原样的那份（不重写，所以 real 的用例排在前面）
    def settings(bm, bom=False):
        d = {'version': 1} if bm == 'DEL' else {'version': 1, 'boss_mods': bm}
        t = json.dumps(d, ensure_ascii=False, indent=1)
        return (b'\xef\xbb\xbf' if bom else b'') + t.encode('utf-8')
    allmods = {k: True for k in BOSS_KEYS}
    S = {
        'real': 'KEEP', 'on': settings({'mode': 'on', 'mods': allmods}), 'OFF': settings({'mode': 'OFF', 'mods': allmods}),
        'nobm': settings('DEL'), 'emptybm': settings({}), 'bad': b'{ not json', 'falsebm': settings(False), 'strbm': settings('x'),
        'mixed': settings({'mode': 'auto', 'mods': {'godrick': 1, 'malenia': 'true', 'mohg': 0, 'rykard': '1', 'midra': 2, 'radahn': None,
                                                    'rennala': [True], 'consort': {'a': 1}, '_godfrey': True, 'nokey': True, 'messmer': 'TRUE',
                                                    'placidusax': 1.0, 'rellana': [0, 1]}}),
        'nomode': settings({'mods': allmods}), 'bom': settings({'mode': 'Auto', 'mods': {'godrick': True}}, bom=True),
        'listmods': settings({'mode': 'on', 'mods': [True]}), 'modenum': settings({'mode': 1, 'mods': allmods}),
        'modefloat': settings({'mode': 2.0, 'mods': allmods}), 'modebool': settings({'mode': True, 'mods': allmods}),
    }
    BM = {None: None, 'hi': 'name\tA\r\nhigh\t1\r\n', 'HI': 'NAME\tB\nHIGH\t1', 'lo': 'name\tC\nhigh\t0', 'hix': 'high\t1x',
          'bad': '\tbad\nname\tD\nhigh', 'dup': 'name\tE\nhigh\t1\nHigh\t0', 'bom': '\ufeffname\tF\r\nhigh\t1'}
    CW = {None: None, 'high': 'high\n', 'LOW': ' LOW \r\n', 'x': 'x'}
    cases = []
    for bw in ('', 'high', 'low'):
        for coop in (False, True):
            for cw in CW:
                for bmk in BM:
                    if cw is not None and not coop and bmk not in (None, 'hi'):
                        continue
                    cases.append(('real', bw, coop, cw, bmk, bmk if coop else None))
    for sk in S:
        if sk != 'real':
            cases.append((sk, '', False, None, 'hi', None))
            cases.append((sk, 'high', True, 'LOW', None, 'hi'))
    p = Pair(tmp, 'boss')

    def files_for(root, b, sk, cw, bmk, bmk_coop):
        rec = os.path.join(b, 'AppData', 'Roaming', 'EldenRing', 'DarkReforged', '角色记录')
        out = [(os.path.join(root, 'launcher', 'reroll', 'state', 'coop_world.txt'), CW[cw]),
               (os.path.join(rec, 'boss_mode.txt'), BM[bmk]), (os.path.join(rec, '联机', 'boss_mode.txt'), BM[bmk_coop])]
        if S[sk] != 'KEEP':
            out.append((os.path.join(root, 'launcher', 'reroll', 'settings.json'), S[sk]))
        return out
    p.each(lambda r, e, b: (os.makedirs(os.path.join(r, 'launcher', 'reroll', 'state')),
                            os.makedirs(os.path.join(b, 'AppData', 'Roaming', 'EldenRing', 'DarkReforged', '角色记录', '联机'))))
    ps = '$__r = @()\n'
    last = {}
    for sk, bw, coop, cw, bmk, bmkc in cases:
        for path, data in files_for(p.root['ps'], p.base['ps'], sk, cw, bmk, bmkc):
            if last.get(path, 'none') != data:
                ps += ps_write(path, data)
                last[path] = data
        ps += '$BossWorld = %s\n$__r += ,@{ bm = (Get-BossMods %s); tc = (Get-TitleCover %s) }\n' % (q(bw), '$true' if coop else '$false', '$true' if coop else '$false')
    a, _ = ps_call(ps, p.env['ps'], root=p.root['ps'])

    def py(c):
        out = []
        for sk, bw, coop, cw, bmk, bmkc in cases:
            for path, data in files_for(p.root['py'], p.base['py'], sk, cw, bmk, bmkc):
                py_write(path, data)
            c.BossWorld = bw
            out.append({'bm': launch.get_boss_mods(c, coop), 'tc': launch.get_title_cover(c, coop)})
        return out
    b, _ = py_call(py, p.env['py'], root=p.root['py'])
    b = j(b)
    for i, case in enumerate(cases):
        check('Get-BossMods / Get-TitleCover %r' % (case,), a[i], b[i])
    # Get-BossModMeta / Get-BossModName
    p.each(lambda r, e, b: (touch(os.path.join(r, 'launcher', 'reroll', 'data', 'bossmods', 'fakemod', 'mod.json'), '{"boss": {"en": "x"}, "fixed": 5}'),
                            touch(os.path.join(r, 'launcher', 'reroll', 'data', 'bossmods', 'badmod', 'mod.json'), '{x'),
                            touch(os.path.join(r, 'launcher', 'reroll', 'data', 'bossmods', 'nozh', 'mod.json'), '{"boss": "x", "arena": {}}')))
    keys = BOSS_KEYS + ['GODRICK', 'nokey', '', 'fakemod', 'badmod', 'nozh']
    a, _ = ps_call('$__r = @(foreach ($k in %s) { $m = Get-BossModMeta $k; @{ name = (Get-BossModName $k); m = $(if ($m) { @{ fixed = @($m.fixed); arena = [bool]$m.arena } } else { $null }) } })' % qa(keys),
                   p.env['ps'], root=p.root['ps'])

    def meta(c):
        out = []
        for k in keys:
            m = launch.get_boss_mod_meta(c, k)
            fx = m.get('fixed') if isinstance(m, dict) else None          # 和上面 PowerShell 的 @($m.fixed) 一样：没有是一个 $null
            out.append({'name': launch.get_boss_mod_name(c, k),
                        'm': {'fixed': [None] if fx is None else launch._list(fx), 'arena': launch._true(m.get('arena'))} if launch._true(m) else None})
        return out
    b, _ = py_call(meta, p.env['py'], root=p.root['py'])
    for i, k in enumerate(keys):
        check('Get-BossModMeta / Get-BossModName %r' % k, a[i], j(b)[i])
    # Write-BossModeDef
    bms = [('关着', 'off', ['a'], ['a'], ''), ('一个都没开', 'auto', [], [], ''), ('auto 加载了', 'auto', ['godrick', 'malenia'], ['godrick', 'malenia'], ''),
           ('auto 没加载 房主', 'auto', [], ['godrick'], 'host'), ('on 队友', 'on', ['x'], ['x'], 'guest'), ('OFF 大写', 'OFF', ['x'], ['x'], ''),
           ('AUTO 大写', 'AUTO', ['x'], ['x'], '')]
    for name, mode, keys_, want, role in bms:
        for dark_core in (True, False):
            def prep(r, e, b, dark_core=dark_core):
                rm(os.path.join(r, 'dll'))
                if dark_core:
                    touch(os.path.join(r, 'dll', 'dark_core', 'bossmods.txt'), 'old')
            p.each(prep)
            ps = '$script:CoopRole = %s; Write-BossModeDef ([pscustomobject]@{ Mode = %s; Keys = %s; Want = %s; Why = "" })' % (q(role), q(mode), qa(keys_), qa(want))

            def py(c, mode=mode, keys_=keys_, want=want, role=role):
                c.CoopRole = role
                launch.write_boss_mode_def(c, Rec(Mode=mode, Keys=list(keys_), Want=list(want), Why=''))
            A, B = None, None
            if dark_core:
                p.run('Write-BossModeDef ' + name, ps, py, files=('root\\dll',))
            else:
                a, oa = ps_call(ps, p.env['ps'], root=p.root['ps'])
                b, ob = py_call(py, p.env['py'], root=p.root['py'])
                cut = lambda o: [l.split('：')[0] for l in o]          # 异常的说明文字两边不一样，只比到「：」
                check('Write-BossModeDef 没有 dll\\dark_core ' + name, normalize(cut(oa), p.subs('ps')), normalize(cut(ob), p.subs('py')))


# ---------------------------------------------------------------- Invoke-Launch / Show-Status / Get-RerollLastText
def setup_rand(root, env, b, item=False, merged=False):
    rd = os.path.join(root, 'randomizer')
    touch(os.path.join(rd, 'EldenRingRandomizer.exe'), b'MZ fake randomizer')
    touch(os.path.join(rd, 'diste', 'Base', 'enemy.txt'), b'x')
    touch(os.path.join(rd, 'regulation.bin'), b'reg')
    os.makedirs(os.path.join(rd, 'msg'), exist_ok=True)
    log = os.path.join(rd, 'spoiler_logs', '2026-11-01_log_12345_abc.txt')
    touch(log, ('Checking other mod directory C:\\x\r\n' if merged else '') + 'Options and seed: enemy customenemy%s seed:12345\r\nmore\r\n' % (' item' if item else ''))
    touch(log[:-4] + '.preset', '777\n0.25\n')
    set_mtime(log, datetime.datetime(2026, 11, 1, 9, 8, 7))
    ids = []
    for k in BOSS_KEYS:
        ids += json.load(open(os.path.join(BOSSMODS, k, 'mod.json'), encoding='utf-8-sig')).get('fixed') or []
    touch(os.path.join(root, 'randomizer_hi', 'hi_source.json'),
          json.dumps({'lo_log': os.path.basename(log), 'hi_log': 'h.txt', 'seed': '12345', 'fixed': ids + [2044450800], 'time': '2026-11-01 10:00:00'}))
    touch(os.path.join(root, 'randomizer_hi', 'regulation.bin'), b'hi')


ERSC_INI = ('[GAMEPLAY]\r\nallow_invaders = 0\r\ndeath_debuffs = 1\r\nallow_summons = 1\r\nalways_spectate_on_death = 1\r\n[SCALING]\r\n'
            'enemy_health_scaling = 35\r\nboss_health_scaling = 100\r\n[PASSWORD]\r\ncooppassword = abc\r\n[SAVE]\r\nsave_file_extension = co2\r\n'
            '[LANGUAGE]\r\nmod_language_override = \r\n')


def setup_launch(root, env, b, rand=False, coop=False, item=False):
    touch(os.path.join(root, 'yafsml', 'YAFSML.exe'), b'MZ')
    os.makedirs(os.path.join(root, 'out'))
    touch(os.path.join(root, 'dll', 'dark_core', 'bossmods.txt'), 'old')
    touch(os.path.join(root, 'dll', 'dark_core', 'coop_profile.txt'), 'old')
    touch(os.path.join(root, 'dll', 'a.dll'), b'MZ')
    save = os.path.join(b, 'AppData', 'Roaming', 'EldenRing', STEAM_ID, 'ER0000.rng')
    touch(save, b'\0' * 64)
    set_mtime(save, datetime.datetime(2026, 11, 2, 3, 4, 5))       # 备份签名里有修改时间：两边一样
    if rand:
        setup_rand(root, env, b, item=item)
    if coop:
        touch(os.path.join(root, 'dll', 'SeamlessCoop', 'ersc.dll'), b'MZ' + b'\0' * 100)
        touch(os.path.join(root, 'dll', 'SeamlessCoop', 'ersc_settings.ini'), ERSC_INI)


LAUNCH_CTL = {'vanilla': {'json': {'ok': True, 'reg': 'C:\\v\\regulation.bin', 'msg': 'C:\\v\\msg', 'from': 'game', 'check': '和原版一样', 'vanilla': False}},
              'reroll': {'out': ['重随中', '§% 90']},
              'scripts': {'json': {'ok': True, 'msg': '合并了'}}, 'menu': {'json': {'ok': True, 'msg': '菜单', 'title': {'normal': 'C:\\N', 'hard': 'C:\\H'}}}}
LAUNCH_FILES = ('root\\yafsml', 'root\\out', 'root\\dll', 'root\\YAFSML自定义.ini', 'AppData', 'root\\launcher\\logs')


def g_launch(tmp):
    """Invoke-Launch（-DryRun、-NoLaunch：不启动 YAFSML；重随、游戏脚本、菜单都是假的工具）"""
    rec = os.path.join('AppData', 'Roaming', 'EldenRing', 'DarkReforged', '角色记录')
    cases = [
        # 名字, 敌人随机, 联机, -DryRun, -BossWorld, 准备, 额外的文件
        ('-DryRun 无敌人随机', False, False, True, '', {}, {}),
        ('-DryRun 无敌人随机 high', False, False, True, 'high', {}, {}),
        ('-DryRun 无敌人随机 low', False, False, True, 'low', {}, {}),
        ('-DryRun 无敌人随机 上次是死亡以上的角色', False, False, True, '', {}, {rec + '\\boss_mode.txt': 'name\t褪色者\r\nhigh\t1\r\n'}),
        ('-DryRun 敌人随机（没装随机器）', True, False, True, '', {}, {}),
        ('-DryRun 敌人随机 high（高难度世界）', True, False, True, 'high', {'rand': True}, {}),
        ('-DryRun 敌人随机 low 带物品随机', True, False, True, 'low', {'rand': True, 'item': True}, {}),
        ('-DryRun 联机 无敌人随机', False, True, True, '', {'coop': True}, {}),
        ('-DryRun 联机 敌人随机（联机世界 high）', True, True, True, '', {'coop': True, 'rand': True}, {'root\\launcher\\reroll\\state\\coop_world.txt': 'high\n'}),
        ('-DryRun 联机 没有 Seamless', False, True, True, '', {}, {}),
        ('-NoLaunch 无敌人随机', False, False, False, '', {}, {}),
        ('-NoLaunch 敌人随机 high', True, False, False, 'high', {'rand': True}, {}),
        ('-NoLaunch 联机 无敌人随机', False, True, False, '', {'coop': True}, {}),
        ('-NoLaunch 重随失败', False, False, False, '', {}, {}),
    ]
    for name, rand, coop, dry, bw, opts, extra in cases:
        def setup(root, env, b, opts=opts, extra=extra):
            setup_launch(root, env, b, **opts)
            for k, v in extra.items():
                touch(os.path.join(b, k), v)
        p = Pair(tmp, 'launch_%d' % len(os.listdir(tmp)), setup)
        ctl = json.loads(json.dumps(LAUNCH_CTL))
        if name == '-NoLaunch 重随失败':
            ctl['reroll'] = {'err': ['崩了'], 'code': 1}
        p.ctl(ctl)
        ps = ('$DryRun = $true; ' if dry else '$NoLaunch = $true; ') + '$BossWorld = %s; Invoke-Launch %s %s; $__r = @{ suffix = $script:WorldSuffix; ext = $script:ErdSaveExt; coopdll = $script:CoopDll }' % (
            q(bw), '$true' if rand else '$false', '$true' if coop else '$false')

        def py(c, rand=rand, coop=coop):
            launch.invoke_launch(c, rand, coop)
            prof_mods(c)
            return {'suffix': c.WorldSuffix, 'ext': c.ErdSaveExt, 'coopdll': c.CoopDll}
        p.run('Invoke-Launch ' + name, ps, wrap(py), ctx_args={'DryRun': dry, 'NoLaunch': not dry, 'BossWorld': bw},
              files=LAUNCH_FILES, times=True)
    p = Pair(tmp, 'launch_notool', setup_launch)
    p.each(lambda r, e, b: os.remove(os.path.join(r, 'launcher', 'reroll', 'scripts.py')))
    p.run('Invoke-Launch 缺少脚本', 'Invoke-Launch $false', wrap(lambda c: launch.invoke_launch(c, False)), files=LAUNCH_FILES, times=True)


def prof_mods(c):
    """有意的不同（崩溃风险审查 2026-11-19 第 12 条）：联机兼容档案多了一行「mods<Tab>自己加的 mod」（副本里没有，是「无」）。
    写了档案就断言有这一行，再从文件里去掉和 PowerShell 比"""
    if not os.path.isfile(c.CoopProfile):
        return
    lines = open(c.CoopProfile, encoding='utf-8', newline='').read().split('\n')
    if not any(l.startswith('fingerprint\t') for l in lines):      # 这次没写（副本里原来就有的那份）
        return
    COUNT[0] += 1
    if 'mods\t无' not in lines:
        FAILS.append('联机兼容档案没有 mods 一行')
        sys.__stdout__.write('DIFF 联机兼容档案没有「mods\t无」一行（有意的不同）：%r\n' % lines)
    with open(c.CoopProfile, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(l for l in lines if not l.startswith('mods\t')))


def g_status(tmp):
    """Get-RerollLastText / Show-Status"""
    p = Pair(tmp, 'lasttext')
    for name, data in (('没有', None), ('正常', '时间：2026-11-18 10:00\r\n种子：123\r\n其他\r\n'), ('只有一行', '时间：x'), ('空的', ''),
                       ('第四行才有种子', '时间：t\r\na\r\nb\r\n种子：9\r\n'), ('BOM', '\ufeff种子：5\n时间：  t2 \n'), ('重复', '时间：1\n时间：2\n')):
        p.each(lambda r, e, b, data=data: py_write(os.path.join(r, 'out', 'reroll', 'reroll_report.txt'), data))
        # 照调用的地方那样拼进字符串比：没有「时间：」行时 PowerShell 返回的是数组（拼进字符串时用空格连起来），Python 直接返回连好的字符串
        p.run('Get-RerollLastText ' + name, "$__r = '' + (Get-RerollLastText)", wrap(launch.get_reroll_last_text))
    for name, setup in (('什么都没装', None),
                        ('装了随机器和 Seamless', lambda r, e, b: (setup_rand(r, e, b, item=True), setup_launch(r, e, b, coop=True),
                                                                touch(os.path.join(r, 'out', 'reroll', 'reroll_report.txt'), '时间：t\r\n种子：1\r\n'))),
                        ('合并别的包做的', lambda r, e, b: setup_rand(r, e, b, merged=True)),
                        ('没记游戏路径', lambda r, e, b: os.remove(os.path.join(r, 'launcher', 'game_path.txt')))):
        p = Pair(tmp, 'status_%d' % len(os.listdir(tmp)), setup)
        p.run('Show-Status ' + name, 'Show-Status', wrap(launch.show_status), files=('root\\launcher\\game_path.txt',))


def main():
    os.chdir(PALY)
    groups = [g_user_dll, g_enemy_info, g_scripts_menu, g_ini, g_processes, g_vanilla_reroll, g_seed_rel, g_boss, g_launch, g_status]
    only = sys.argv[1:]
    with tempfile.TemporaryDirectory() as tmp:
        for g in groups:
            if only and g.__name__ not in only:
                continue
            print('==== ' + g.__name__ + '：' + (g.__doc__ or '').strip().splitlines()[0])
            d = os.path.join(tmp, g.__name__)
            os.makedirs(d)
            g(d)
    print('launch：%d 项，%d 项不同' % (COUNT[0], len(FAILS)))
    for f in FAILS:
        print('  DIFF', f)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
