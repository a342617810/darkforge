# -*- coding: utf-8 -*-
"""对照测试的公共部分：同一个输入分别交给旧的 PowerShell 函数和新的 Python 函数，比结果、比输出、比写出的文件。

- ps_call(snippet, env)：在一个新的 powershell 里设好环境变量、dot-source <根目录>\\launcher\\launcher.ps1（它会顺带加载 backup / randomize /
  ui / coopcode / usermods），把 Show-DrDialog 换成按 DARKFORGE_TEST_DIALOG 回答、记进 DARKFORGE_TEST_DIALOG_LOG 的假弹窗，再跑 snippet。
  snippet 里把要比的结果放进 $__r；返回 (结果, 输出的行)。结果按 ConvertTo-Json -Depth 8 转成 Python 的值。
- py_call(fn, env)：同样的环境变量下建 Ctx 跑 fn(ctx)，返回 (结果, 输出的行)。
- fake_env(tmp)：一套假的 APPDATA / LOCALAPPDATA（不碰真的存档和随机器设置）。
- tree(path)：目录里所有文件 {相对路径: 字节}，比写出的文件用。

只在副本 / 假目录上跑：env 里一定要有 APPDATA、LOCALAPPDATA（fake_env 给的）；写整合包目录的函数要给 root（复制出来的根目录）。"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
LAUNCHER = os.path.join(PALY, 'launcher')
sys.path.insert(0, LAUNCHER)

MARK = '@@DF_RESULT@@'
PS_PRE = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
. '%(launcher)s' *> $null
function Show-DrDialog {
    param([string]$Text, [string]$Title = '暗黑重铸', [string[]]$Buttons = @('确定'), [int]$Default = 0, [int]$Cancel = -1, [string]$Icon = 'info', $Owner = $null)
    $log = $env:DARKFORGE_TEST_DIALOG_LOG
    if ($log) { [IO.File]::AppendAllText($log, ((@{ title = $Title; text = $Text; buttons = [string[]]$Buttons } | ConvertTo-Json -Compress) + "`n"), (New-Object Text.UTF8Encoding($false))) }
    $ans = @(([string]$env:DARKFORGE_TEST_DIALOG).Split(',') | Where-Object { $_.Trim() })
    if (-not $ans.Count) { return 0 }
    if ($ans.Count -gt 1) { $env:DARKFORGE_TEST_DIALOG = ($ans[1..($ans.Count - 1)] -join ',') }
    return [int]$ans[0]
}
$__r = $null
'''
PS_POST = r'''
Write-Host '%(mark)s'
if ($null -eq $__r) { Write-Host 'null' } else { Write-Host (ConvertTo-Json -InputObject $__r -Depth 8 -Compress) }
'''


def fake_env(tmp):
    """假的 APPDATA / LOCALAPPDATA（建好空目录）"""
    env = {'APPDATA': os.path.join(tmp, 'AppData', 'Roaming'), 'LOCALAPPDATA': os.path.join(tmp, 'AppData', 'Local')}
    for v in env.values():
        os.makedirs(v, exist_ok=True)
    return env


def _check_env(env):
    for k in ('APPDATA', 'LOCALAPPDATA'):
        v = (env or {}).get(k)
        if not v or os.path.normcase(os.path.abspath(v)) == os.path.normcase(os.path.abspath(os.environ.get(k, ''))):
            raise RuntimeError('测试必须给假的 %s（fake_env）' % k)


PS_OLD = os.path.join(PALY, 'dev', 'launcher_py', 'ps_old')      # 第 5 步起旧的 PowerShell 脚本放在这里（整合包里没有了）


def put_old_ps(launcher_dir):
    """把旧的 .ps1 放进一个副本的 launcher 文件夹（对照测试要 dot-source 它们）"""
    for n in os.listdir(PS_OLD):
        if n.lower().endswith('.ps1') and not os.path.exists(os.path.join(launcher_dir, n)):
            shutil.copy2(os.path.join(PS_OLD, n), os.path.join(launcher_dir, n))


def ps_call(snippet, env, root=None, timeout=300):
    """返回 (结果, 输出的行)"""
    _check_env(env)
    launcher = os.path.join(root or PALY, 'launcher', 'launcher.ps1')
    if not os.path.exists(launcher):
        raise RuntimeError('没有 ' + launcher + '：旧的 PowerShell 脚本第 5 步挪到了 dev\\launcher_py\\ps_old，' +
                           '对照测试要在副本上跑（copy_root / gui_env.py 会放回去），不往真的整合包里放')
    body = PS_PRE % {'launcher': launcher.replace("'", "''")} + snippet + PS_POST % {'mark': MARK}
    fd, path = tempfile.mkstemp(suffix='.ps1', dir=os.environ.get('TEMP'))
    os.close(fd)
    with open(path, 'w', encoding='utf-8-sig') as f:
        f.write(body)
    e = dict(os.environ)
    e.update(env)
    try:
        r = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path], capture_output=True, env=e,
                           timeout=timeout, stdin=subprocess.DEVNULL)
    finally:
        os.remove(path)
    out = r.stdout.decode('utf-8', 'replace').replace('\r\n', '\n').split('\n')
    if MARK not in out:
        raise RuntimeError('PowerShell 没跑完：\n' + r.stdout.decode('utf-8', 'replace')[-3000:] + r.stderr.decode('utf-8', 'replace')[-3000:])
    i = out.index(MARK)
    res = json.loads(out[i + 1]) if out[i + 1] != 'null' else None
    return res, [l for l in out[:i]]


class _Env:
    def __init__(self, env):
        self.env = env

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update({k: str(v) for k, v in self.env.items()})

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def py_call(fn, env, root=None, **ctx_args):
    """返回 (结果, 输出的行)：fn(ctx) 在同样的环境变量下跑"""
    _check_env(env)
    from dfl import core
    e = dict(env)
    if root:
        e['DARKFORGE_ROOT'] = root
    buf = io.StringIO()
    old = sys.stdout
    with _Env(e):
        sys.stdout = buf
        try:
            ctx = core.Ctx(**ctx_args)
            res = fn(ctx)
        finally:
            sys.stdout = old
    return res, buf.getvalue().split('\n')[:-1] if buf.getvalue() else []


def copy_root(tmp, items=('launcher',), extra=()):
    """把整合包根目录的一部分复制到 tmp\\root（写整合包目录的函数在副本上测）；launcher 下的 python / dotnet / webview2 / logs 不复制"""
    dst = os.path.join(tmp, 'root')
    big = {'python', 'dotnet', 'webview2', 'logs', 'reroll'}       # launcher 下太大的 / 运行时的；要用 reroll 里的文件就放进 extra

    def ignore(d, names):
        top = os.path.normcase(os.path.abspath(d)) == os.path.normcase(LAUNCHER)
        return [n for n in names if n == '__pycache__' or (top and n in big)]
    for it in items:
        s = os.path.join(PALY, it)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst, it), ignore=ignore)
        elif os.path.isfile(s):
            os.makedirs(os.path.dirname(os.path.join(dst, it)), exist_ok=True)
            shutil.copy2(s, os.path.join(dst, it))
    for rel in extra:
        s = os.path.join(PALY, rel)
        d = os.path.join(dst, rel)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
        elif os.path.isfile(s):
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
    if any(it == 'launcher' or (it.startswith('launcher\\') and it.lower().endswith('.ps1')) for it in items):
        os.makedirs(os.path.join(dst, 'launcher'), exist_ok=True)
        put_old_ps(os.path.join(dst, 'launcher'))
    return dst


def tree(path):
    """目录里所有文件 {相对路径（/ 分隔）: 字节}"""
    out = {}
    for d, _, files in os.walk(path):
        for n in files:
            p = os.path.join(d, n)
            out[os.path.relpath(p, path).replace('\\', '/')] = open(p, 'rb').read()
    return out


def diff_tree(a, b):
    """两个 tree() 的差别：[(相对路径, 说明)]"""
    out = []
    for k in sorted(set(a) | set(b)):
        if k not in a:
            out.append((k, '只有 Python 版写了'))
        elif k not in b:
            out.append((k, '只有 PowerShell 版写了'))
        elif a[k] != b[k]:
            out.append((k, '内容不同（%d / %d 字节）' % (len(a[k]), len(b[k]))))
    return out


def same(name, ps, py):
    """打印一行比较结果，返回是否一样"""
    ok = ps == py
    print(('OK   ' if ok else 'DIFF ') + name)
    if not ok:
        print('   PS:', json.dumps(ps, ensure_ascii=False)[:2000])
        print('   PY:', json.dumps(py, ensure_ascii=False)[:2000])
    return ok
