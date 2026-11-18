# -*- coding: utf-8 -*-
"""导出诊断包（launcher.ps1 的 Invoke-Diag / Copy-LogTail / Save-DiagContent）：把日志、配置、游戏版本、Windows 崩溃记录打成一个 zip，不含存档。

和 PowerShell 版有意的不同：
- 事件日志用 evtlog（wevtapi），硬件用 WMI（_wmi）+ 注册表（winreg），不再开 PowerShell；
- zip 用 zipfile：路径分隔符是 /（PowerShell 5.1 的 Compress-Archive 写的是 \\，别的系统上解不开）；
- system.txt 里「PowerShell：版本」换成「启动器：Python 版本」；launcher_logs 多带一份 gui_trace.txt（新界面自己的出错堆栈）。"""
import datetime
import hashlib
import os
import platform
import re
import shutil
import subprocess
import traceback
import zipfile

from . import core, win
from .backup import RngCoopSave, _gci, copy_rng_record, get_rng_record_files, get_rng_save_files
from .core import write_err, write_head, write_ok, write_warn
from .pytool import CREATE_NO_WINDOW, find_python

MB = 1024 * 1024
GB = 1024 * MB
HOOKERS = ['RTSS', 'RTSSHooksLoader64', 'MSIAfterburner', 'Discord', 'NVIDIA Overlay', 'nvsphelper64', 'NVIDIA Share', 'GameBar',
           'Overwolf', 'obs64', 'bdcam', 'fraps', 'Action_x64', 'Medal', 'LosslessScaling', 'SKIF', 'FPSMonitor', 'CapFrameX',
           'GameOverlayUI', 'AMDRSServ', 'RadeonSoftware', 'ReShade']


# ---------------------------------------------------------------- 小工具
def fmt_num(v):
    """PowerShell 里 double 转文字：整数不带小数点（[Math]::Round(x, 1) 的结果拼进字符串）"""
    if v == int(v):
        return str(int(v))
    return repr(float(v))


def round1(x):
    """[Math]::Round(x, 1)（.NET 的四舍六入五成双）"""
    return round(x, 1)


def _now():
    return datetime.datetime.now()


def _t(dt, f='%Y-%m-%d %H:%M:%S'):
    return dt.strftime(f)


def _write_bom(path, text):
    """[IO.File]::WriteAllText(..., UTF8Encoding($true))"""
    core.write_text(path, text, bom=True)


def _write_lines_bom(path, lines):
    """[IO.File]::WriteAllLines(..., UTF8Encoding($true))：每行后面 \\r\\n"""
    core.write_lines(path, lines, bom=True)


def cim_time(s):
    """WMI 的时间（20261112023343.475012-300：本地时间 + 和 UTC 差几分钟）→ 这台电脑的本地时间；认不出返回 None"""
    m = re.match(r'^(\d{14})\.(\d{6})([+-])(\d{3})$', s or '')
    if not m:
        return None
    t = datetime.datetime.strptime(m.group(1), '%Y%m%d%H%M%S').replace(microsecond=int(m.group(2)))
    off = int(m.group(4)) * (1 if m.group(3) == '+' else -1)
    t = t.replace(tzinfo=datetime.timezone(datetime.timedelta(minutes=off)))
    return t.astimezone().replace(tzinfo=None)


def _copy_item(src, dst):
    """Copy-Item -Force：带修改时间"""
    shutil.copy2(src, dst)


def _hidden(path):
    try:
        return bool(getattr(os.stat(path), 'st_file_attributes', 0) & 0x2)
    except OSError:
        return False


def _explorer_select(path):
    try:
        subprocess.Popen('explorer.exe /select,"' + path + '"', close_fds=True)
    except OSError:
        pass


# ---------------------------------------------------------------- 入口
def invoke_diag(ctx, OutDir='', Reason='', DumpPath=''):
    """Invoke-Diag：返回 zip 的路径，失败返回 None"""
    ts = _now().strftime('%Y%m%d_%H%M%S')
    tmp = os.path.join(os.environ.get('TEMP') or ctx.Paly, 'darkforge_diag_' + ts)
    os.makedirs(tmp, exist_ok=True)
    write_head('导出诊断包')
    if Reason:
        _write_bom(os.path.join(tmp, 'crash.txt'), Reason)
    # 收集到一半出错也照样把已经收集到的打包（诊断包就是出问题时用的），错误写进 diag_error.txt
    try:
        save_diag_content(ctx, tmp, DumpPath)
    except Exception as e:
        err = '收集到一半出错，后面的内容没收集到：' + str(e) + '\r\n' + ''.join(traceback.format_tb(e.__traceback__)[-3:]).replace('\n', '\r\n')
        _write_bom(os.path.join(tmp, 'diag_error.txt'), err)
        write_warn('收集时出错，诊断包里会缺一部分：' + str(e))
    d = OutDir
    if not d:
        d = win.known_folder('Desktop')
        if not d or not os.path.exists(d):
            d = ctx.Paly
    os.makedirs(d, exist_ok=True)
    zp = os.path.join(d, ('Darkforge_崩溃诊断_' if Reason else 'Darkforge_诊断_') + ts + '.zip')
    from .coop import remove_coop_secret
    remove_coop_secret(ctx, tmp)
    try:
        compress_dir(tmp, zp)
    except OSError as e:
        write_warn('打包失败：' + str(e))
    shutil.rmtree(tmp, ignore_errors=True)
    if os.path.exists(zp):
        write_ok('诊断包已导出：' + zp)
        core.host('  把这个 zip 发给帮你排查的人即可（不含存档）。')
        if not ctx.NoLaunch and not Reason:
            _explorer_select(zp)
        return zp
    write_err('诊断包导出失败。')
    return None


def compress_dir(src, zp):
    """Compress-Archive -Path <src>\\* -DestinationPath <zp> -Force：src 下面的东西放在 zip 的根上（空文件夹也留一项）"""
    tmpzip = zp + '.part'
    with zipfile.ZipFile(tmpzip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for d, dirs, files in os.walk(src):
            rel = os.path.relpath(d, src)
            if rel != '.' and not dirs and not files:
                z.write(d, rel.replace('\\', '/') + '/')
            for n in files:
                p = os.path.join(d, n)
                z.write(p, os.path.relpath(p, src).replace('\\', '/'))
    os.replace(tmpzip, zp)


def copy_log_tail(Src, Dst, Max=MB):
    """Copy-LogTail：不存在（或隐藏）就跳过；超过 Max 只取最后 Max（从下一个换行开始，免得切开半个字），开头写一行说明"""
    try:
        if not os.path.isfile(Src) or _hidden(Src):
            return
        n = os.path.getsize(Src)
        os.makedirs(os.path.dirname(Dst), exist_ok=True)
        if n <= Max:
            _copy_item(Src, Dst)
            return
        with open(Src, 'rb') as f:
            f.seek(-Max, 2)
            buf = f.read(Max)
        start = buf.find(b'\n') + 1
        head = ('（原文件 ' + fmt_num(round1(n / MB)) + ' MB，这里只取了最后 ' + fmt_num(round1(Max / MB)) + ' MB）' + '\r\n').encode('utf-8')
        with open(Dst, 'wb') as f:
            f.write(head)
            f.write(buf[start:])
    except OSError:
        pass


# ---------------------------------------------------------------- 内容
def save_diag_content(ctx, tmp, DumpPath):
    """Save-DiagContent：都写进 tmp"""
    j = os.path.join
    L = ctx.LauncherDir
    # 日志超过 1 MB 的只取最后 1 MB（最近几次启动），开头写一行说明
    copy = [
        (ctx.RandomLog, 'YAFSML.log'), (ctx.YafIni, 'YAFSML.ini'),
        (j(ctx.RerollPack, 'reroll_report.txt'), 'reroll_report.txt'), (j(ctx.RerollPack, 'features.json'), 'reroll_features.json'),
        (ctx.GamePathFile, 'game_path.txt'),
        (j(L, 'reroll', 'settings.json'), 'reroll_settings.json'),
        (j(ctx.RandomDir, 'config_eldenringrandomizer.toml'), 'randomizer_config.toml'),
        (j(ctx.RandomDir, 'dll', 'RandomizerCrashFix_log.txt'), 'RandomizerCrashFix_log.txt'),
        (ctx.UserIniPath, 'YAFSML自定义.ini'),
    ]
    for s, d in copy:
        copy_log_tail(s, j(tmp, d))
    # 启动器：最近 10 次运行日志，每局游戏怎么结束的（game_sessions.txt），退出时崩溃的记录，图形界面自己出的错
    log_dir = j(L, 'logs')
    if os.path.exists(log_dir):
        dst = j(tmp, 'launcher_logs')
        os.makedirs(dst, exist_ok=True)
        logs = [f for f in _gci(log_dir, dirs=False, pattern='*.log')]
        for f in win.ps_sort_key(logs, lambda f: f.LastWriteTimeUtcTicks, True)[:10]:
            _copy_item(f.FullName, j(dst, f.Name))
        for n in ('game_sessions.txt', 'exit_crashes.txt', 'gui_errors.txt', 'gui_trace.txt', 'save_ops.txt'):
            copy_log_tail(j(log_dir, n), j(dst, n))
    # 角色记录（DLL 记的装备配方、锁定名单等，一次性重随的 once.json）放 player_records\，联机的在 player_records\联机\
    for f in get_rng_record_files(ctx):
        copy_rng_record(f, j(tmp, 'player_records'))
    # 联机：Seamless Co-op 的配置（联机密码去掉）
    from .coop import find_ersc
    ersc = find_ersc(ctx)
    if ersc:
        try:
            t = _read_net_text(j(ersc.DirectoryName, 'ersc_settings.ini'))
            t = re.sub(r'(?im)^([ \t]*cooppassword[ \t]*=)[^\r\n]*', '\\g<1> （诊断包里去掉了）', t)
            _write_bom(j(tmp, 'ersc_settings.ini'), '; 位置：' + ersc.FullName + '\r\n' + t)
        except OSError:
            pass
    # dll\ 下各 DLL 自己的日志、难度档位表、庆典油脂参数、飞行参数、锁定名单，按原来的子文件夹放；日志只要最近 7 天写过的
    if os.path.exists(ctx.UserDllDir):
        week = _now() - datetime.timedelta(days=7)
        names = ('lock_items.txt', 'difficulty_tiers.txt', 'festive.txt', 'dark_wings.ini')
        for f in _gci(ctx.UserDllDir, dirs=False, recurse=True):
            if (core.ieq(f.Extension, '.log') and f.LastWriteTime > week) or any(core.ieq(f.Name, n) for n in names):
                copy_log_tail(f.FullName, j(tmp, 'dll_logs', f.FullName[len(ctx.UserDllDir):].lstrip('\\')))
    if os.path.exists(ctx.RunLogDir):
        dst = j(tmp, 'dll_logs_prev')
        os.makedirs(dst, exist_ok=True)
        runs = _gci(ctx.RunLogDir, dirs=False)
        for f in win.culture_sorted(runs, key=lambda f: f.Name, reverse=True)[:20]:
            _copy_item(f.FullName, j(dst, f.Name))
    from .randomizer import get_latest_random, get_randomizer_status
    latest = get_latest_random(ctx)
    if latest:
        try:
            head = core.read_text(latest.Log, 'replace').splitlines()[:80]
            _write_lines_bom(j(tmp, 'randomizer_log_head.txt'), head)
        except OSError:
            pass
    _write_lines_bom(j(tmp, 'system.txt'), system_info(ctx, tmp, DumpPath, latest, ersc, get_randomizer_status(ctx)))
    _write_bom(j(tmp, 'windows_crash_events.txt'), crash_events_text())
    _write_lines_bom(j(tmp, 'gpu_events.txt'), gpu_events_lines())


def _read_net_text(path):
    """[IO.File]::ReadAllText：有 BOM 按 BOM，没有按 UTF-8"""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw[3:].decode('utf-8', 'replace')
    if raw.startswith(b'\xff\xfe'):
        return raw[2:].decode('utf-16-le', 'replace')
    return raw.decode('utf-8', 'replace')


def get_ersc_dumps(ctx, From, To):
    """Get-ErscDumps：Seamless Co-op 自己接管崩溃（crashpad），转储写在 SeamlessCoop\\crashdumps\\reports\\（游戏目录的、整合包 dll\\ 里的都看）。
    返回这段时间里写的 .dmp（FileItem，新的在前）"""
    from .coop import find_ersc
    from .gamepath import resolve_game_root
    dirs = []
    gr = resolve_game_root(ctx)
    if gr:
        dirs.append(os.path.join(gr, 'Game\\SeamlessCoop\\crashdumps\\reports'))
    ersc = find_ersc(ctx)
    if ersc:
        dirs.append(os.path.join(ersc.DirectoryName, 'crashdumps\\reports'))
    seen, out = set(), []
    for d in dirs:
        if d in seen:
            continue
        seen.add(d)
        out += [f for f in _gci(d, dirs=False, pattern='*.dmp') if From <= f.LastWriteTime <= To]
    return win.ps_sort_key(out, lambda f: f.LastWriteTimeUtcTicks, True)


def _wmi1(q):
    r = win.wmi_query(q)
    return r[0] if r else {}


def _uint32(s):
    try:
        v = int(s)
    except (TypeError, ValueError):
        return 0
    return v + (1 << 32) if v < 0 else v


def _reg_vram():
    """显卡驱动注册表项里的显存大小 {显卡名: 字节}（Win32_VideoController 的 AdapterRAM 最多到 4 GB）"""
    import winreg
    out = {}
    base = 'SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}'
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return out
    with k:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(k, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(k, sub) as s:
                    desc = winreg.QueryValueEx(s, 'DriverDesc')[0]
                    mem = winreg.QueryValueEx(s, 'HardwareInformation.qwMemorySize')[0]
            except OSError:
                continue
            if desc and isinstance(mem, int) and mem:
                out[str(desc)] = float(mem)
    return out


def _gpu_pref():
    import winreg
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\DirectX\\UserGpuPreferences')
    except OSError:
        return '没指定'
    hits = []
    with k:
        i = 0
        while True:
            try:
                n, v, _ = winreg.EnumValue(k, i)
            except OSError:
                break
            i += 1
            if re.search(r'(eldenring|YAFSML)\.exe$', n, re.I):
                hits.append(n + ' = ' + str(v))
    return ('；'.join(hits) + '（GpuPreference=1 省电显卡，2 高性能显卡）') if hits else '没指定'


def _hags():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 'SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers') as k:
            v = winreg.QueryValueEx(k, 'HwSchMode')[0]
    except OSError:
        return '默认（没设置）'
    return '开' if v == 2 else '关' if v == 1 else '默认（没设置）'


def _steam_language(gr):
    p = os.path.dirname(os.path.dirname(gr.rstrip('\\'))) if gr else ''
    acf = os.path.join(p, 'appmanifest_1245620.acf') if p else None
    if not acf or not os.path.exists(acf):
        return '找不到 Steam 的 appmanifest（不是 Steam 版？）'
    try:
        for l in core.read_text(acf, 'replace').splitlines():
            m = re.search(r'"language"\s+"([^"]*)"', l, re.I)
            if m:
                return m.group(1)
    except OSError:
        pass
    return 'acf 里没写'


def _sha16(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:16]


def system_info(ctx, tmp, DumpPath, latest, ersc, rs):
    """system.txt 的每一行：系统 / 游戏 / 整合包 / 硬件"""
    from .gamepath import resolve_game_root
    from .launch import get_enemy_info_choice, get_reroll_last_text
    from .usermods import get_user_mod_summary
    j = os.path.join
    info = ['导出时间：' + _t(_now())]
    os_ = _wmi1('SELECT Caption, Version, LastBootUpTime FROM Win32_OperatingSystem')
    if os_:
        info.append('系统：' + os_.get('Caption', '') + ' ' + os_.get('Version', ''))
    info.append('启动器：Python ' + platform.python_version())
    info.append('整合包目录：' + ctx.Paly)
    gr = resolve_game_root(ctx)
    if gr:
        exe = j(gr, 'Game', 'eldenring.exe')
        info.append('游戏目录：' + gr)
        if os.path.exists(exe):
            info.append('eldenring.exe 版本：' + win.file_version_text(exe))
        # 游戏语言：Steam 版看 steamapps\appmanifest_1245620.acf（菜单文字只做了简体中文 / 英文）。游戏装在盘符下一级时没有上两级
        info.append('游戏语言（Steam）：' + _steam_language(gr))
    else:
        info.append('游戏目录：未设置 / 找不到')
    py = find_python(ctx)
    if py:
        try:
            r = subprocess.run([py, '--version'], capture_output=True, stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=60)
            ver = ' '.join((r.stdout + r.stderr).decode('utf-8', 'replace').split())
        except (OSError, subprocess.SubprocessError):
            ver = ''
        info.append('Python：' + py + '  ' + ver)
    else:
        info.append('Python：找不到')
    cache = _gci(j(ctx.YafDir, 'cache'), dirs=False, pattern='*.bhd.zz')
    info.append('YAFSML 缓存文件：' + str(len(cache)) + ' 个')
    try:
        info += list(get_user_mod_summary(ctx))
    except Exception:
        pass
    if not rs.Ok:
        rtxt = '没装 / 用不了：' + rs.Msg.split('\r\n')[0]
    elif rs.Tested:
        rtxt = rs.Version
    else:
        rtxt = '版本没测过，程序 SHA-256 ' + ctx.RandExeHash.Hash
    info.append('随机器：' + rtxt)
    if latest:
        info.append('随机器输出：' + _t(latest.Time) + '，敌人随机=' + str(bool(latest.HasEnemy)) + '，物品随机=' + str(bool(latest.HasItem)))
    else:
        info.append('随机器输出：无')
    once = j(ctx.RngRecordDir, 'once.json')
    info.append('一次性重随记录：' + (_t(datetime.datetime.fromtimestamp(os.path.getmtime(once))) if os.path.exists(once) else '无'))
    info.append('上次重随：' + get_reroll_last_text(ctx))
    saves = get_rng_save_files(ctx)
    for name, label in (('ER0000.rng', '单机'), (RngCoopSave, '联机')):
        s = [f for f in saves if core.ieq(f.Name, name)]
        newest = win.ps_sort_key(s, lambda f: f.LastWriteTimeUtcTicks, True)[0] if s else None
        info.append('暗黑重铸' + label + '存档（' + name + '）：' + str(len(s)) + ' 个' + ('，最后修改 ' + _t(newest.LastWriteTime) if newest else ''))
    # 改名以前的联机存档（ER0000.rng.co2，还有以前套出来的 ER0000.rng.rng.co2 这类）
    old = []
    for d in _gci(ctx.RngSaveRoot, files=False):
        old += [f for f in _gci(d.FullName, dirs=False) if re.match(r'^ER0000(\.rng)+\.co2$', f.Name, re.I)]
    if old:
        info.append('旧名字的联机存档：' + '、'.join(f.Name + '（' + _t(f.LastWriteTime, '%m-%d %H:%M') + '）' for f in old))
    info.append('Seamless Co-op：' + (ersc.FullName + '，版本 ' + win.file_version_text(ersc.FullName) if ersc else '没放'))
    info.append('联机一次性重随记录：' + str(len(_gci(j(ctx.RngRecordDir, '联机'), dirs=False, pattern='once_*.json'))) + ' 份')
    gps = win.find_pids('eldenring')
    info.append('游戏正在运行：' + str(bool(gps)))
    for pid in gps:
        with win.Proc(pid) as p:
            st = p.start_time()
            pp = p.path()
        hw = win.main_window(pid)
        try:
            import ctypes
            resp = str(not ctypes.windll.user32.IsHungAppWindow(ctypes.c_void_p(hw))) if hw else 'True'
        except Exception:
            resp = '未知'
        info.append('  进程号 ' + str(pid) + '，启动于 ' + (_t(st) if st else '未知') + '，窗口=' + str(bool(hw)) + '，响应=' + resp + '，路径=' + (pp or ''))
    boot = cim_time(os_.get('LastBootUpTime')) if os_ else None
    if boot:
        info.append('电脑开机时间：' + _t(boot))
    dumps = _gci(j(os.environ.get('LOCALAPPDATA') or '', 'CrashDumps'), dirs=False, pattern='eldenring*') if os.environ.get('LOCALAPPDATA') else []
    info.append('崩溃转储（%LOCALAPPDATA%\\CrashDumps，未打包）：' + '；'.join(f.Name + ' ' + _t(f.LastWriteTime, '%m-%d %H:%M') for f in dumps))
    # 崩溃调用栈（crash_stack.txt）：reroll\crashstack.py 从转储里取异常、寄存器、调用栈、模块清单，转储本身不打包。
    # 崩溃看守传进来的那份排第一，再按时间从新到旧给最近 7 天的（联机时 Seamless Co-op 的也算），最多 10 份
    week = _now() - datetime.timedelta(days=7)
    picks = []
    if DumpPath and os.path.exists(DumpPath):
        picks.append(os.path.abspath(DumpPath))
    ed = get_ersc_dumps(ctx, week, _now())
    if ed:
        info.append('Seamless Co-op 的崩溃转储（未打包）：' + '；'.join(f.Name + ' ' + _t(f.LastWriteTime, '%m-%d %H:%M') for f in ed))
    more = [f for f in dumps if core.ieq(f.Extension, '.dmp') and f.LastWriteTime > week] + ed
    picks += [f.FullName for f in win.ps_sort_key(more, lambda f: f.LastWriteTimeUtcTicks, True)]
    uniq = []
    for p in picks:
        if p not in uniq:
            uniq.append(p)
    picks = uniq[:10]
    stack_out = j(tmp, 'crash_stack.txt')
    if picks and py:
        try:
            subprocess.run([py, j(ctx.LauncherDir, 'reroll', 'crashstack.py'), stack_out] + picks, capture_output=True,
                           stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=600)
        except (OSError, subprocess.SubprocessError):
            pass
    info.append('崩溃调用栈：' + ('crash_stack.txt' if os.path.exists(stack_out) else '最近 7 天没有崩溃转储' if not picks
                                 else '没生成（找不到 Python）' if not py else '没生成（解析出错）'))
    # 硬件：CPU / 内存 / 显卡（型号、驱动版本和日期、显存、当前分辨率）；游戏在 Windows 图形设置里指定的显卡；硬件加速 GPU 计划
    cpu = _wmi1('SELECT Name, NumberOfLogicalProcessors FROM Win32_Processor')
    cs = _wmi1('SELECT TotalPhysicalMemory FROM Win32_ComputerSystem')
    if cpu and cs:
        info.append('CPU：' + cpu.get('Name', '').strip() + '（' + cpu.get('NumberOfLogicalProcessors', '') + ' 线程）；内存：' +
                    fmt_num(round1(float(cs.get('TotalPhysicalMemory') or 0) / GB)) + ' GB')
    vram = _reg_vram()
    gpus = win.wmi_query('SELECT Name, AdapterRAM, DriverVersion, DriverDate, CurrentHorizontalResolution, CurrentVerticalResolution, '
                         'CurrentRefreshRate FROM Win32_VideoController')
    if not gpus:
        info.append('显卡：读不到（WMI 没有结果）')
    for g in gpus:
        name = g.get('Name', '')
        mem = vram[name] if name in vram else float(_uint32(g.get('AdapterRAM')))
        dd = cim_time(g.get('DriverDate'))
        dd = dd.strftime('%Y-%m-%d') if dd else '日期不明'
        hres = g.get('CurrentHorizontalResolution')
        res = ('，当前 ' + hres + '×' + g.get('CurrentVerticalResolution', '') + ' ' + g.get('CurrentRefreshRate', '') + 'Hz') if hres and hres != '0' else '，没接显示器'
        info.append('显卡：' + name + '（驱动 ' + g.get('DriverVersion', '') + '，' + dd + '，显存约 ' + fmt_num(round1(mem / GB)) + ' GB' + res + '）')
    info.append('Windows 图形设置里给游戏指定的显卡：' + _gpu_pref())
    if os.path.exists(j(ctx.UserDllDir, 'souls_vision.dll')):
        ch = get_enemy_info_choice(ctx)
        info.append('敌人信息 mod：' + ('玩家关掉了，不加载' if ch and ch.casefold() == 'off' else '加载') +
                    ('（双显卡）' if len(win.get_gpu_names()) >= 2 else '（单显卡）'))
    info.append('硬件加速 GPU 计划：' + _hags())
    # 正在运行、会往游戏里注入画面层 / 钩子的常见程序（和整合包自己的两个画面层 dark_ui、souls_vision 叠在一起时可能冲突）
    names = []
    hk = [h.casefold() for h in HOOKERS]
    for _, _, exe in win.processes():
        n = exe[:-4] if exe.lower().endswith('.exe') else exe
        if (n.casefold() in hk or re.search('overlay|hook', n, re.I)) and n not in names:
            names.append(n)
    names = win.culture_sorted(names)
    info.append('正在运行的画面层 / 注入类程序：' + ('、'.join(names) if names else '没有'))
    info.append('')
    info.append('---- 整合包目录 ----')
    for d in _gci(ctx.Paly, force=True):
        info.append('  ' + d.Name)
    # 游戏目录 Game\ 顶层：别的 mod 加载器、ReShade 之类放的 dinput8.dll / dxgi.dll 会和整合包一起被游戏加载
    if gr:
        info.append('')
        info.append('---- 游戏目录 Game\\ 顶层 ----')
        for f in win.culture_sorted(_gci(j(gr, 'Game'), force=True), key=lambda f: f.Name):
            if f.PSIsContainer:
                info.append('  [' + f.Name + ']')
            else:
                info.append('  ' + f.Name + '  ' + str(f.Length) + ' 字节  ' + _t(f.LastWriteTime, '%Y-%m-%d %H:%M'))
    # dll 文件夹（和随机器自带的 dll）：DLL 被杀毒软件删掉 / 改名停用时这里能看出来；.dll 带 SHA256 前 16 位，和发布的版本对照看文件坏没坏
    for label, d in (('dll 文件夹', ctx.UserDllDir), ('randomizer\\dll', j(ctx.RandomDir, 'dll'))):
        info.append('')
        info.append('---- ' + label + ' ----')
        for f in win.culture_sorted(_gci(d, dirs=False, force=True, recurse=True), key=lambda f: f.FullName):
            h = ''
            if core.ieq(f.Extension, '.dll'):
                try:
                    h = '  SHA256 ' + _sha16(f.FullName)
                except OSError as e:
                    h = '  SHA256 读不了（' + str(e) + '）'
            info.append('  ' + f.FullName[len(d):].lstrip('\\') + '  ' + str(f.Length) + ' 字节  ' + _t(f.LastWriteTime, '%Y-%m-%d %H:%M') + h)
    return info


# ---------------------------------------------------------------- Windows 事件日志
def crash_events_text():
    """windows_crash_events.txt：最近 7 天游戏相关的崩溃 / 卡住记录"""
    from . import evtlog
    since = _now() - datetime.timedelta(days=7)
    try:
        ev = evtlog.query('Application', providers=['Application Error', 'Windows Error Reporting', 'Application Hang'], since=since,
                          match='eldenring|YAFSML')
    except OSError:
        ev = []
    if not ev:
        return '最近 7 天没有游戏相关的崩溃记录。'
    return '\r\n'.join('==== ' + _t(e.Time) + '  ' + e.Provider + ' ' + str(e.Id) + '\r\n' + e.Message + '\r\n' for e in ev)


def gpu_events_lines():
    """gpu_events.txt：显卡驱动超时被重置（Display 4101）、显卡驱动 / 图形内核自己记的错误、硬件错误（WHEA-Logger），
    以及显卡出错时 Windows 生成的内核报告（LiveKernelEvent 141、117 等），最近 7 天"""
    from . import evtlog
    since = _now() - datetime.timedelta(days=7)
    gx = ['---- 系统日志：显卡驱动 / 图形内核 / 硬件错误（最近 7 天，最多 40 条） ----']
    try:
        evs = evtlog.query('System', since=since, levels=[1, 2, 3], limit=40,
                           where=lambda e: re.search(r'^Display$|WHEA|nvlddmkm|amdkmdag|amdwddmg|igfx|DxgKrnl', e.Provider, re.I))
        for x in evs:
            gx.append('==== ' + _t(x.Time) + '  ' + x.Provider + ' ' + str(x.Id))
            ls = [l for l in re.split(r'\r?\n', x.Message or '') if l.strip()][:6]
            gx += ['  ' + l.strip() for l in ls]
        if not evs:
            gx.append('  没有')
    except OSError as e:
        gx.append('  没有 / 读不到（' + str(e) + '）')
    gx.append('')
    gx.append('---- 显卡内核报告 LiveKernelEvent（最近 7 天，最多 20 条） ----')
    try:
        evs = evtlog.query('Application', providers=['Windows Error Reporting'], ids=[1001], since=since, limit=20, match='LiveKernelEvent')
        for x in evs:
            gx.append('==== ' + _t(x.Time))
            gx += ['  ' + l.strip() for l in re.split(r'\r?\n', x.Message or '') if re.search(r'^(P1|P2|P3|P4):|事件名称|Event Name', l, re.I)]
        if not evs:
            gx.append('  没有')
    except OSError as e:
        gx.append('  没有 / 读不到（' + str(e) + '）')
    return gx
