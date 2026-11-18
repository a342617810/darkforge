# -*- coding: utf-8 -*-
"""崩溃看守（launcher.ps1 的 Invoke-CrashWatch 一组）：启动游戏后在后台等游戏退出，
查 Windows 有没有记录这个进程号的崩溃（Application Error 1000）或卡住后被关掉（Application Hang 1002），
有就自动导出诊断包到 崩溃诊断\\（留最近 10 个）并弹窗提示；每局怎么结束的都记一行到 launcher\\logs\\game_sessions.txt。

由 launch.start_crash_watch 用包里的 pythonw.exe 跑 `df.py watch --game-pid <进程号>`（没有窗口、不写运行日志）。"""
import datetime
import os
import re
import subprocess
import tempfile
import time

from . import core, win
from .diag import _explorer_select, fmt_num, get_ersc_dumps, invoke_diag, round1
from .pytool import CREATE_NO_WINDOW, find_python

EXIT_OFFSETS = r'^(0x)?0*(1ebb809|1ebcef9|1ebb799)$'      # 带 mod 退出游戏时几乎每次都在这里出错（2.7.1.0 / 2.7.2.0 / 不支持的 2.7.0.0，同一处 DL_PANIC）


def _minutes(a, b):
    return fmt_num(round1((b - a).total_seconds() / 60.0))


def add_game_session(ctx, Start, End, Result):
    """Add-GameSession：每局游戏一行（只留最近 300 行，诊断包会带上）：什么时候开始 / 结束、玩了多久、怎么结束的"""
    try:
        f = os.path.join(ctx.LauncherDir, 'logs', 'game_sessions.txt')
        os.makedirs(os.path.dirname(f), exist_ok=True)
        line = Start.strftime('%Y-%m-%d %H:%M:%S') + ' ~ ' + End.strftime('%H:%M:%S') + '（' + _minutes(Start, End) + ' 分钟）  ' + Result
        old = core.read_lines(f, 'replace') if os.path.exists(f) else []
        core.write_lines(f, old[-299:] + [line], bom=True)
    except OSError:
        pass


def add_exit_crash_line(ctx, What):
    """Add-ExitCrashLine：退出时的崩溃（没影响）记一行到 launcher\\logs\\exit_crashes.txt（Add-Content -Encoding UTF8：新文件带 BOM）"""
    try:
        f = os.path.join(ctx.LauncherDir, 'logs', 'exit_crashes.txt')
        os.makedirs(os.path.dirname(f), exist_ok=True)
        new = not os.path.exists(f)
        with open(f, 'ab') as fh:
            if new:
                fh.write(b'\xef\xbb\xbf')
            fh.write((datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' 退出时崩溃（已忽略）：' + What + '\r\n').encode('utf-8'))
    except OSError:
        pass


def test_exit_crash_dump(ctx, Dump):
    """Test-ExitCrashDump：一份转储是不是退出游戏时那种没影响的崩溃（reroll\\crashstack.py 认 DL_PANIC 的位置）"""
    py = find_python(ctx)
    if not py:
        return False
    fd, out = tempfile.mkstemp(suffix='.txt')
    os.close(fd)
    try:
        subprocess.run([py, '-X', 'utf8', os.path.join(ctx.LauncherDir, 'reroll', 'crashstack.py'), out, Dump], capture_output=True,
                       stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=600)
        return '退出游戏时的崩溃' in core.read_text(out, 'replace')
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def export_crash_diag(ctx, Reason, Dump, What):
    """Export-CrashDiag：崩溃 / 卡住：导出诊断包到 崩溃诊断\\（留最近 10 个）并弹窗"""
    from .backup import _gci
    from .dialog import show_dr_dialog
    zp = invoke_diag(ctx, ctx.CrashDir, Reason, Dump)
    zips = win.ps_sort_key(_gci(ctx.CrashDir, dirs=False, pattern='*.zip'), lambda f: f.LastWriteTimeUtcTicks, True)
    for f in zips[10:]:
        try:
            os.remove(f.FullName)
        except OSError:
            pass
    if zp:
        r = show_dr_dialog('游戏刚才' + What + '。\r\n\r\n已自动导出诊断包：\r\n' + zp + '\r\n\r\n需要别人帮忙排查时，把这个 zip 发给对方。',
                           '暗黑重铸 · 游戏出错', ['打开所在文件夹', '关闭'], 0, 1, 'warn')
        if r == 0:
            _explorer_select(zp)


def ask_enemy_info_off_after_crash(ctx):
    """Ask-EnemyInfoOffAfterCrash：双显卡电脑上加载着敌人信息 mod 时游戏崩溃了，问要不要改成不加载"""
    from .launch import get_enemy_info_choice, set_enemy_info_choice, show_top_yes_no
    ch = get_enemy_info_choice(ctx)
    if len(win.get_gpu_names()) < 2 or (ch and ch.casefold() == 'off') or not os.path.exists(os.path.join(ctx.UserDllDir, 'souls_vision.dll')):
        return
    try:
        off = show_top_yes_no('这台电脑有两块显卡，这次游戏加载了敌人信息 mod（敌人头上的血条、状态条）。' +
                              '它在有的双显卡电脑上会让游戏读档时闪退。\r\n\r\n' +
                              '要改成不加载吗？（游戏里就没有敌人血条和状态条了，以后想再用：启动器「工具与设置」→「游戏」）', '暗黑重铸 · 敌人信息 mod')
        if off is True:
            set_enemy_info_choice(ctx, 'off')
    except Exception:
        pass


def _app_error(started, pid):
    """这个进程号的 Application Error 1000（[0] 程序名 [3] 崩溃模块 [6] 异常码 [7] 偏移 [8] 进程号；按字段认，说明文字随系统语言变）"""
    from . import evtlog
    try:
        r = evtlog.query('Application', providers=['Application Error'], ids=[1000], since=started, limit=1,
                         where=lambda e: len(e.Data) > 8 and e.Data[0].casefold() == 'eldenring.exe' and evtlog.to_int(e.Data[8]) == pid)
    except OSError:
        return None
    return r[0] if r else None


def _app_hang(started):
    from . import evtlog
    try:
        r = evtlog.query('Application', providers=['Application Hang'], ids=[1002], since=started, limit=1,
                         where=lambda e: len(e.Data) > 0 and e.Data[0].casefold() == 'eldenring.exe')
    except OSError:
        return None
    return r[0] if r else None


def invoke_crash_watch(ctx, ProcId, settle=8.0):
    """Invoke-CrashWatch：等这个进程（要是 eldenring.exe）退出，看它怎么结束的"""
    pid = int(ProcId or 0)
    if pid <= 0 or pid not in win.find_pids('eldenring'):
        return
    p = win.Proc(pid)                      # 先拿住进程句柄，退出后才读得到退出码
    try:
        started = p.start_time() or datetime.datetime.now()
        # 边等边记游戏窗口最后一次还在的时间：正常退出时窗口先关、进程后结束；游戏中崩溃时窗口会留到进程结束
        win_seen = False
        last_win = datetime.datetime.now()
        if p:
            while not p.wait(0):
                if win.main_window(pid):
                    win_seen = True
                    last_win = datetime.datetime.now()
                p.wait(500)
        else:
            while win.pid_alive(pid):
                time.sleep(5)
        ended = datetime.datetime.now()
        window_closed_first = win_seen and (ended - last_win).total_seconds() >= 1.5
        code = p.exit_code()
        exit_code = ('0x%08X' % (code & 0xFFFFFFFF)) if code is not None else '读不到'
    finally:
        p.close()
    time.sleep(settle)                     # 等 Windows 写完崩溃记录
    local = os.environ.get('LOCALAPPDATA') or ''
    ev = _app_error(started, pid)
    if not ev:
        # 联机（Seamless Co-op）时崩溃由它的 crashpad 接管、Windows 没有记录：看它写的转储（退出时写，看守又等了 8 秒）
        eds = get_ersc_dumps(ctx, started, ended + datetime.timedelta(seconds=15))
        ed = eds[0] if eds else None
        if ed:
            if test_exit_crash_dump(ctx, ed.FullName):
                add_game_session(ctx, started, ended, '退出时崩溃（没影响）：DL_PANIC（Seamless Co-op 的转储 ' + ed.Name + '）')
                add_exit_crash_line(ctx, 'DL_PANIC（Seamless Co-op 的转储 ' + ed.FullName + '） 进程 ' + str(pid))
                return
            play = _minutes(started, ended)
            add_game_session(ctx, started, ended, '崩溃（Seamless Co-op 的转储 ' + ed.Name + '，退出码 ' + exit_code + '）')
            reason = ('游戏崩溃（联机：Seamless Co-op 接管了崩溃，Windows 没有记录，转储是它写的）\r\n退出时间：' + ended.strftime('%Y-%m-%d %H:%M:%S') +
                      '\r\n游戏启动后：' + play + ' 分钟\r\n退出码：' + exit_code + '\r\n进程号：' + str(pid) + '\r\n转储文件：' + ed.FullName)
            export_crash_diag(ctx, reason, ed.FullName, '崩溃了（游戏启动后 ' + play + ' 分钟，退出码 ' + exit_code + '）')
            ask_enemy_info_off_after_crash(ctx)
            return
        # 卡住（无响应）后被玩家关掉：Windows 记一条 Application Hang 1002，[0] 是程序名。同一时间只有一个游戏，按时间认
        hang = _app_hang(started)
        # Windows 没记崩溃事件（有的电脑关掉了错误报告），但退出码是异常码（0xC…）、窗口也不是先关的：一样算崩溃
        if not hang and re.match(r'^0xC', exit_code, re.I) and not window_closed_first:
            play = _minutes(started, ended)
            add_game_session(ctx, started, ended, '崩溃（Windows 没有崩溃记录，退出码 ' + exit_code + '）')
            dump = os.path.join(local, 'CrashDumps', 'eldenring.exe.' + str(pid) + '.dmp')
            reason = ('游戏崩溃（Windows 没有记录这次崩溃，可能关掉了错误报告，所以不知道崩在哪个模块）\r\n退出时间：' + ended.strftime('%Y-%m-%d %H:%M:%S') +
                      '\r\n游戏启动后：' + play + ' 分钟\r\n退出码：' + exit_code + '\r\n进程号：' + str(pid) + '\r\n' +
                      '转储文件：' + (dump if os.path.exists(dump) else '无'))
            export_crash_diag(ctx, reason, dump, '崩溃了（游戏启动后 ' + play + ' 分钟，退出码 ' + exit_code + '）')
            ask_enemy_info_off_after_crash(ctx)
            return
        if not hang:
            add_game_session(ctx, started, ended, '正常退出（退出码 ' + exit_code + '）' + ('' if win_seen else '，没出现过游戏窗口'))
            return
        play = _minutes(started, hang.Time)
        add_game_session(ctx, started, ended, '无响应（卡住）后被关掉')
        reason = ('游戏无响应（卡住）后被关掉\r\n时间：' + hang.Time.strftime('%Y-%m-%d %H:%M:%S') + '\r\n游戏启动后：' + play + ' 分钟\r\n' +
                  '进程号：' + str(pid) + '\r\n\r\n' + hang.Message)
        export_crash_diag(ctx, reason, '', '卡住后被关掉了（游戏启动后 ' + play + ' 分钟）')
        return
    module = ev.Data[3]
    offset = ev.Data[7]
    # 退出时的崩溃不算（存档已经写完，没有影响），或者窗口已经先关了：只记一行到日志，不弹窗、不导出诊断包
    exit_crash = (module.casefold() == 'eldenring.exe' and re.match(EXIT_OFFSETS, offset, re.I)) or window_closed_first
    if exit_crash:
        add_game_session(ctx, started, ended, '退出时崩溃（没影响）：' + module + ' ' + offset)
        add_exit_crash_line(ctx, module + ' ' + offset + ' 进程 ' + str(pid) + ' 窗口先关闭=' + str(bool(window_closed_first)))
        return
    play = _minutes(started, ev.Time)
    add_game_session(ctx, started, ended, '崩溃：' + module + ' ' + offset + '（退出码 ' + exit_code + '）')
    dump = os.path.join(local, 'CrashDumps', 'eldenring.exe.' + str(pid) + '.dmp')
    reason = ('游戏崩溃\r\n时间：' + ev.Time.strftime('%Y-%m-%d %H:%M:%S') + '\r\n游戏启动后：' + play + ' 分钟\r\n' +
              '崩溃模块：' + module + '\r\n位置：' + offset + '\r\n进程号：' + str(pid) + '\r\n' +
              '转储文件（约 55 MB，未打包；调用栈已经取到 crash_stack.txt 里，一般不用再发）：' + (dump if os.path.exists(dump) else '无') + '\r\n\r\n' + ev.Message)
    export_crash_diag(ctx, reason, dump, '崩溃了（崩溃模块：' + module + '，游戏启动后 ' + play + ' 分钟）')
    ask_enemy_info_off_after_crash(ctx)


def invoke_crash_watch_safe(ctx, ProcId):
    """-Action watch：看守在后台跑、不写运行日志；自己出错时记一行到 game_sessions.txt"""
    try:
        invoke_crash_watch(ctx, ProcId)
    except Exception as e:
        t = datetime.datetime.now()
        add_game_session(ctx, t, t, '崩溃看守自己出错（这一局怎么结束的没记下来）：' + str(e))
