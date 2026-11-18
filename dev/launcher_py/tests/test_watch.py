# -*- coding: utf-8 -*-
"""崩溃看守新旧对照（第 4 步）。不制造真的游戏崩溃（会在真的 CrashDumps 和事件日志里留下假的 eldenring 崩溃），
用改名成 eldenring.exe 的小程序当「游戏」：

  test_watch.py <gui_env 的测试文件夹> <假游戏文件夹>

假游戏文件夹（scratchpad\\fakegame）：eldenring.exe = ping.exe 的复制（正常退出、没有窗口）；
py\\eldenring.exe = 包里 Python 的复制（ExitProcess(0xC0000005)：退出码是异常码、Windows 没有崩溃记录）。

1. 实跑对照：两种结束方式，PowerShell 的 Invoke-CrashWatch 和 Python 的 watch.invoke_crash_watch 各看一个进程，
   比 game_sessions.txt 新加的那行、弹窗的文字、崩溃诊断包里的 crash.txt（时间、进程号、分钟数换成占位）。
2. 只测 Python：把查事件日志换成这台电脑上真的事件（退出时的崩溃、游戏里的崩溃、卡住），看走的分支和记的内容。"""
import datetime
import json
import os
import re
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import ps_call, py_call  # noqa: E402

T = os.path.abspath(sys.argv[1])
FAKE = os.path.abspath(sys.argv[2])
ROOT = os.path.join(T, 'root')
ENV = {'APPDATA': os.path.join(T, 'appdata'), 'LOCALAPPDATA': os.path.join(T, 'local')}
SESS = os.path.join(ROOT, 'launcher', 'logs', 'game_sessions.txt')
CRASH = os.path.join(ROOT, '崩溃诊断')
DLG = os.path.join(T, 'watch_dialogs.jsonl')
FAILS = []
NO_WIN = 0x08000000


def check(name, ok, detail=''):
    print(('OK   ' if ok else 'DIFF ') + name)
    if not ok:
        FAILS.append(name)
        if detail:
            print('   ' + detail.replace('\n', '\n   '))


def sessions():
    try:
        with open(SESS, encoding='utf-8-sig') as f:
            return f.read().splitlines()
    except OSError:
        return []


def dialogs():
    try:
        with open(DLG, encoding='utf-8') as f:
            return [json.loads(l) for l in f if l.strip()]
    except OSError:
        return []


def newest_zip():
    zs = [os.path.join(CRASH, n) for n in os.listdir(CRASH) if n.endswith('.zip')] if os.path.isdir(CRASH) else []
    return max(zs, key=os.path.getmtime) if zs else None


def crash_txt(zp):
    with zipfile.ZipFile(zp) as z:
        n = next(i for i in z.namelist() if i.replace('\\', '/') == 'crash.txt')
        return z.read(n).decode('utf-8-sig')


def mask(s):
    s = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '<时间>', s)
    s = re.sub(r' ~ \d{2}:\d{2}:\d{2}', ' ~ <时间>', s)
    s = re.sub(r'（[\d.]+ 分钟）', '（<n> 分钟）', s)
    s = re.sub(r'启动后[：]?\s*[\d.]+ 分钟', '启动后 <n> 分钟', s)
    s = re.sub(r'进程号：\d+', '进程号：<pid>', s)
    s = re.sub(r'eldenring\.exe\.\d+\.dmp', 'eldenring.exe.<pid>.dmp', s)
    s = re.sub(r'Darkforge_崩溃诊断_\d{8}_\d{6}\.zip', 'Darkforge_崩溃诊断_<时间>.zip', s)
    return s


def fake_game(kind, secs=6):
    if kind == 'normal':
        return subprocess.Popen([os.path.join(FAKE, 'eldenring.exe'), '-n', str(secs), '127.0.0.1'], stdout=subprocess.DEVNULL,
                                creationflags=NO_WIN)
    code = ('import time, ctypes; time.sleep(%d); k = ctypes.windll.kernel32; k.ExitProcess.argtypes = [ctypes.c_uint]; '
            'k.ExitProcess(0xC0000005)' % secs)
    return subprocess.Popen([os.path.join(FAKE, 'py', 'eldenring.exe'), '-c', code], creationflags=NO_WIN)


def env_dlg():
    e = dict(ENV)
    e['DARKFORGE_TEST_DIALOG'] = '1'                # 「游戏出错」弹窗点「关闭」
    e['DARKFORGE_TEST_DIALOG_LOG'] = DLG
    return e


def run_ps(kind):
    p = fake_game(kind)
    time.sleep(0.5)
    ps_call('Invoke-CrashWatch %d' % p.pid, env_dlg(), root=ROOT, timeout=900)
    p.wait()
    return p.pid


def run_py(kind, settle=8.0, patch=None):
    p = fake_game(kind)
    time.sleep(0.5)

    def fn(ctx):
        from dfl import watch
        old = {}
        for k, v in (patch or {}).items():
            old[k] = getattr(watch, k)
            setattr(watch, k, v)
        try:
            watch.invoke_crash_watch(ctx, p.pid, settle=settle)
        finally:
            for k, v in old.items():
                setattr(watch, k, v)
    py_call(fn, env_dlg(), root=ROOT)
    p.wait()
    return p.pid


def part1():
    for kind, name in (('normal', '正常退出、没有窗口'), ('code', '退出码 0xC0000005、Windows 没有记录')):
        s0, d0, z0 = len(sessions()), len(dialogs()), newest_zip()
        run_ps(kind)
        s1, d1, z1 = sessions(), dialogs(), newest_zip()
        run_py(kind)
        s2, d2, z2 = sessions(), dialogs(), newest_zip()
        a, b = s1[s0:], s2[len(s1):]
        check(name + '：game_sessions 的行', len(a) == 1 and len(b) == 1 and mask(a[0]) == mask(b[0]), 'PS: %r\nPY: %r' % (a, b))
        da, db = d1[d0:], d2[len(d1):]
        dj = lambda x: mask(json.dumps(x, ensure_ascii=False, sort_keys=True))       # 两边记的字段顺序不一样
        check(name + '：弹窗', [dj(x) for x in da] == [dj(x) for x in db],
              'PS: %r\nPY: %r' % (da, db))
        if kind == 'code':
            ok = z1 and z2 and z1 != z0 and z2 != z1
            check(name + '：导出了两个崩溃诊断包', bool(ok), '%s / %s / %s' % (z0, z1, z2))
            if ok:
                ca, cb = crash_txt(z1), crash_txt(z2)
                check(name + '：crash.txt', mask(ca) == mask(cb), 'PS: %r\nPY: %r' % (ca, cb))
        print('   ', b[0] if b else '')


def ev(when, data, provider='Application Error', eid=1000, msg='（说明文字）'):
    from dfl.core import Rec
    return Rec(Provider=provider, Id=eid, Level=2, Time=when, Data=data, Message=msg)


def part2():
    now = datetime.datetime.now()
    base = ['eldenring.exe', '2.7.1.0', '6a96b418', 'eldenring.exe', '2.7.1.0', '6a96b418', 'c0000005']
    cases = [
        ('退出时的崩溃（eldenring.exe+1ebb809）', {'_app_error': lambda s, pid: ev(now, base + ['0000000001ebb809', hex(pid)])},
         r'^退出时崩溃（没影响）：eldenring\.exe 0000000001ebb809$', False),
        ('游戏里的崩溃（eldenring.exe+11a6b79）', {'_app_error': lambda s, pid: ev(now, base + ['00000000011a6b79', hex(pid)])},
         r'^崩溃：eldenring\.exe 00000000011a6b79（退出码 0x00000000）$', True),
        ('卡住后被关掉', {'_app_error': lambda s, pid: None, '_app_hang': lambda s: ev(now, ['eldenring.exe', '2.7.1.0', '0x1'], 'Application Hang', 1002)},
         r'^无响应（卡住）后被关掉$', True),
    ]
    for name, patch, want, diag in cases:
        z0, d0 = newest_zip(), len(dialogs())
        s0 = len(sessions())
        run_py('normal', settle=0, patch=patch)
        new = sessions()[s0:]
        res = new[0].split('  ', 1)[1] if new and '  ' in new[0] else ''
        ok = len(new) == 1 and re.match(want, res)
        if diag:
            ok = ok and newest_zip() != z0 and len(dialogs()) == d0 + 1
        else:
            ok = ok and newest_zip() == z0 and len(dialogs()) == d0
        check('只测 Python：' + name, bool(ok), '%r' % new)
    # Seamless Co-op 的转储：真的 crashpad 转储认不认得出退出时的崩溃（DL_PANIC）
    from dfl import diag as D

    def fn(ctx):
        from dfl import watch
        ds = D.get_ersc_dumps(ctx, now - datetime.timedelta(days=30), now)
        return [(d.Name, watch.test_exit_crash_dump(ctx, d.FullName)) for d in ds[:3]]
    r, _ = py_call(fn, ENV, root=ROOT)
    print('    Seamless Co-op 的转储（是不是退出时的崩溃）：', r)


part1()
part2()
print()
print('共 %d 项不同' % len(FAILS) if FAILS else '全部一样（有意的不同之外）')
sys.exit(1 if FAILS else 0)
