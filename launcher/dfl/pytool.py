# -*- coding: utf-8 -*-
"""调用包里的 Python 工具（reroll.py、scripts.py、menu.py、vanilla.py、update.py……；launcher.ps1 的 Find-Python / Invoke-PyJson / Write-PyErrors，
以及「输出逐行转给玩家看」的那几处）。子进程不开窗口；环境变量只给子进程，不留在自己身上。"""
import json
import os
import subprocess

from .core import host

CREATE_NO_WINDOW = 0x08000000


def find_python(ctx):
    """Find-Python：优先用包里自带的 launcher\\python\\python.exe，其次系统里装的 python / py（3.8+）；找不到返回 None"""
    if getattr(ctx, 'PythonExe', None):
        return ctx.PythonExe
    cands = [os.path.join(ctx.LauncherDir, 'python', 'python.exe')]
    import shutil
    for cmd in ('python', 'py'):
        c = shutil.which(cmd)
        if c:
            cands.append(c)
    for p in cands:
        if not os.path.isfile(p):
            continue
        try:
            r = subprocess.run([p, '-c', 'import sys, ctypes, zlib; sys.exit(0 if sys.version_info >= (3, 8) else 1)'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                               creationflags=CREATE_NO_WINDOW, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0:
            ctx.PythonExe = p
            return p
    return None


def child_env(extra=None):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    for k, v in (extra or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return env


def invoke_py_json(ctx, Py, PyArgs, env=None):
    """Invoke-PyJson：跑一个最后输出一行 JSON 结果的工具，返回解析好的结果（dict；没有返回 None）。
    错误输出留在 ctx.PyErr，失败时 write_py_errors 写最后几行"""
    try:
        r = subprocess.run([Py] + list(PyArgs), stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                           creationflags=CREATE_NO_WINDOW, env=child_env(env))
    except OSError as e:
        ctx.PyErr = [str(e)]
        return None
    out = r.stdout.decode('utf-8', 'replace').splitlines()
    ctx.PyErr = r.stderr.decode('utf-8', 'replace').splitlines()
    js = [l for l in out if l.lstrip().startswith('{')]
    if not js:
        return None
    try:
        v = json.loads(js[-1])
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def write_py_errors(ctx):
    """Write-PyErrors：Python 错误输出的最后 15 行写进运行日志"""
    lines = [l for l in ctx.PyErr if l and l.strip()][-15:]
    if not lines:
        return
    host('  Python 的错误输出（最后几行）：')
    for l in lines:
        host('    ' + l)


def run_stream(Py, PyArgs, env=None, on_line=None):
    """跑工具，标准输出逐行原样转出来（运行日志、图形界面都看得到），错误输出逐行前面加两个空格；返回退出码。
    两路输出合在一起按到达顺序转（和 PowerShell 的 2>&1 | ForEach-Object 一样，错误行认得出来是因为前缀）"""
    import threading
    try:
        p = subprocess.Popen([Py] + list(PyArgs), stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW, env=child_env(env))
    except OSError as e:
        host('  ' + str(e))
        return -1
    emit = on_line or host
    lock = threading.Lock()

    def pump(stream, prefix):
        for raw in iter(stream.readline, b''):
            s = raw.decode('utf-8', 'replace').rstrip('\r\n')
            with lock:
                emit(prefix + s)
        stream.close()
    t = threading.Thread(target=pump, args=(p.stderr, '  '), daemon=True)
    t.start()
    pump(p.stdout, '')
    t.join()
    return p.wait()
