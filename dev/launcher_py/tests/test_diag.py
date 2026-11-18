# -*- coding: utf-8 -*-
"""诊断包新旧对照（第 4 步）：在 gui_env.py 搭的副本（整合包副本 + 假 APPDATA / LOCALAPPDATA）上，
PowerShell 的 Invoke-Diag 和 Python 的 diag.invoke_diag 各导出一个 zip，解开逐个文件比。

  test_diag.py <gui_env 的测试文件夹>

准备：副本的 dll\\ 换成真的 dll 文件夹的一份复制，假 LOCALAPPDATA\\CrashDumps 里放两份真的游戏转储（都只读真的）。
有意的不同（只看这些行 / 文件的形状，不比内容）：
- system.txt：「导出时间」差几秒；「PowerShell：」换成「启动器：Python」；
- windows_crash_events.txt / gpu_events.txt：事件说明的语言跟着进程的界面语言（PowerShell 在这里给英文），只比每条的标题行；
- zip 里的路径分隔符：PowerShell 5.1 写 \\，Python 写 /（解开后一样）；
- launcher_logs 里多一份 gui_trace.txt（新界面自己的出错堆栈）。"""
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import LAUNCHER, PALY, ps_call, py_call  # noqa: E402

T = os.path.abspath(sys.argv[1])
ROOT = os.path.join(T, 'root')
ENV = {'APPDATA': os.path.join(T, 'appdata'), 'LOCALAPPDATA': os.path.join(T, 'local')}
OUT = os.path.join(T, 'diag_out')
FAILS = []


def prepare():
    shutil.copytree(os.path.join(LAUNCHER, 'dfl'), os.path.join(ROOT, 'launcher', 'dfl'), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    for n in ('df.py', 'dfgui.py'):
        shutil.copy2(os.path.join(LAUNCHER, n), os.path.join(ROOT, 'launcher', n))
    os.makedirs(os.path.join(ROOT, 'launcher', 'reroll'), exist_ok=True)
    shutil.copy2(os.path.join(LAUNCHER, 'reroll', 'crashstack.py'), os.path.join(ROOT, 'launcher', 'reroll', 'crashstack.py'))
    d = os.path.join(ROOT, 'dll')
    if not os.listdir(d):
        shutil.copytree(os.path.join(PALY, 'dll'), d, dirs_exist_ok=True)
    cd = os.path.join(ENV['LOCALAPPDATA'], 'CrashDumps')
    os.makedirs(cd, exist_ok=True)
    real = os.path.join(os.environ['LOCALAPPDATA'], 'CrashDumps')
    dumps = sorted((e for e in os.scandir(real) if e.name.lower().startswith('eldenring')), key=lambda e: e.stat().st_mtime)[-2:]
    for e in dumps:
        if not os.path.exists(os.path.join(cd, e.name)):
            shutil.copy2(e.path, os.path.join(cd, e.name))
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for s in ('ps', 'py'):
        os.makedirs(os.path.join(OUT, s))


def unzip(zp, dst):
    with zipfile.ZipFile(zp) as z:
        for i in z.infolist():
            name = i.filename.replace('\\', '/')
            p = os.path.join(dst, *name.split('/'))
            if name.endswith('/'):
                os.makedirs(p, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(z.read(i))
    out = {}
    for d, _, fs in os.walk(dst):
        for n in fs:
            p = os.path.join(d, n)
            out[os.path.relpath(p, dst).replace('\\', '/')] = open(p, 'rb').read()
    return out


def check(name, ok, detail=''):
    print(('OK   ' if ok else 'DIFF ') + name)
    if not ok:
        FAILS.append(name)
        if detail:
            print('   ' + detail.replace('\n', '\n   '))


def lines(b):
    return b.decode('utf-8-sig', 'replace').split('\r\n')


def main():
    prepare()
    pz, pout = ps_call("$NoLaunch = $true; $__r = Invoke-Diag '%s'" % os.path.join(OUT, 'ps').replace("'", "''"), ENV, root=ROOT, timeout=900)

    def run(ctx):
        from dfl import diag
        return diag.invoke_diag(ctx, OutDir=os.path.join(OUT, 'py'))
    yz, yout = py_call(run, ENV, root=ROOT, NoLaunch=True)
    check('两边都导出了 zip', bool(pz) and bool(yz), 'PS: %s\nPY: %s' % (pz, yz))
    if not (pz and yz):
        return
    norm = lambda ls: [re.sub(r'\\(ps|py)\\Darkforge_诊断_\d{8}_\d{6}\.zip', r'\\<输出>\\Darkforge_诊断_<时间>.zip', l) for l in ls if l.strip()]
    check('输出的行', norm(pout) == norm(yout), 'PS: %r\nPY: %r' % (norm(pout), norm(yout)))
    a = unzip(pz, os.path.join(OUT, 'ps_x'))
    b = unzip(yz, os.path.join(OUT, 'py_x'))
    only_ps = sorted(set(a) - set(b))
    only_py = sorted(set(b) - set(a) - {'launcher_logs/gui_trace.txt'})      # 有意的不同：新界面自己的出错堆栈，PowerShell 版没有这个文件
    check('zip 里的文件', not only_ps and not only_py, '只有 PS 有：%s\n只有 PY 有：%s' % (only_ps, only_py))
    for k in sorted(set(a) & set(b)):
        if k == 'system.txt':
            la, lb = lines(a[k]), lines(b[k])
            mask = lambda l: re.sub(r'^导出时间：.*', '导出时间：<时间>', re.sub(r'^(PowerShell|启动器)：.*', '<运行环境>', l))
            ma, mb = [mask(l) for l in la], [mask(l) for l in lb]
            diff = [(i, x, y) for i, (x, y) in enumerate(zip(ma, mb)) if x != y]
            check('system.txt（%d 行）' % len(la), not diff and len(ma) == len(mb) and a[k][:3] == b[k][:3],
                  '\n'.join('%d\n  PS: %s\n  PY: %s' % d for d in diff[:20]) + ('\n行数 %d / %d' % (len(ma), len(mb)) if len(ma) != len(mb) else ''))
        elif k in ('windows_crash_events.txt', 'gpu_events.txt'):
            pick = lambda b_: [l for l in lines(b_) if l.startswith('==== ') or l.startswith('---- ') or l.strip() in ('没有',)]
            check(k + '（标题行）', pick(a[k]) == pick(b[k]), 'PS: %r\nPY: %r' % (pick(a[k])[:10], pick(b[k])[:10]))
        else:
            check(k, a[k] == b[k], 'PS %d 字节 / PY %d 字节' % (len(a[k]), len(b[k])))
    print()
    print('共 %d 项不同' % len(FAILS) if FAILS else '全部一样（有意的不同之外）')


main()
sys.exit(1 if FAILS else 0)
