# -*- coding: utf-8 -*-
"""公共部分：路径和状态（Ctx，原来 launcher.ps1 / backup.ps1 / randomize.ps1 / usermods.ps1 开头的全局变量）、输出约定（Write-*）、运行日志（Start-Transcript）、
读写文本的小工具。

命名：PowerShell 的变量 $Xxx / $script:Xxx 在这里都是 ctx.Xxx（名字照抄，免得各模块对不上）；函数 Verb-Noun → verb_noun(ctx, ...)。
测试：环境变量 DARKFORGE_ROOT 指向别的整合包根目录（副本），APPDATA / LOCALAPPDATA 指向假的目录，就不碰真的文件。"""
import datetime
import os
import platform
import re
import sys
import traceback

LAUNCHER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_dir(name):
    return os.environ.get(name) or ''


class Ctx:
    """一次运行的路径、参数和状态（PowerShell 的脚本级变量）"""

    def __init__(self, Action='help', GamePid=0, GamePath='', FromPack='', Code='', UpdateZip='', BossWorld='', DryRun=False, NoLaunch=False):
        # ---- 参数（launcher.ps1 的 param）
        self.Action = Action
        self.GamePid = int(GamePid or 0)
        self.GamePath = GamePath or ''
        self.FromPack = FromPack or ''
        self.Code = Code or ''
        self.UpdateZip = UpdateZip or ''
        self.BossWorld = BossWorld or ''
        self.DryRun = bool(DryRun)
        self.NoLaunch = bool(NoLaunch)

        # ---- 路径（launcher.ps1 开头）
        root = os.environ.get('DARKFORGE_ROOT')
        self.LauncherDir = os.path.join(os.path.abspath(root), 'launcher') if root else LAUNCHER_DIR
        self.Paly = os.path.dirname(self.LauncherDir)
        j = os.path.join
        self.YafDir = j(self.Paly, 'yafsml')
        self.YafExe = j(self.YafDir, 'YAFSML.exe')
        self.YafIni = j(self.YafDir, 'YAFSML.ini')
        self.TplPath = j(self.LauncherDir, 'YAFSML.ini.tpl')
        self.RandomDir = j(self.Paly, 'randomizer')
        self.RandomExe = j(self.RandomDir, 'EldenRingRandomizer.exe')
        self.VanillaTool = j(self.LauncherDir, 'reroll', 'vanilla.py')
        self.RandomLog = j(self.YafDir, 'log', 'YAFSML.log')
        self.GamePathFile = j(self.LauncherDir, 'game_path.txt')
        self.RerollTool = j(self.LauncherDir, 'reroll', 'reroll.py')
        self.ScriptsTool = j(self.LauncherDir, 'reroll', 'scripts.py')
        self.WorldFile = j(self.Paly, 'out', 'current_world.txt')
        self.MenuTool = j(self.LauncherDir, 'reroll', 'menu.py')
        self.MenuPack = j(self.Paly, 'out', 'menu')
        self.UserDllDir = j(self.Paly, 'dll')
        self.EnemyInfoChoice = j(self.LauncherDir, 'reroll', 'state', 'enemy_info_mod.txt')
        self.BackupIntervalFile = j(self.LauncherDir, 'reroll', 'state', 'backup_interval.txt')    # 定时备份间隔（分钟，backup.py）
        self.RunLogDir = j(self.LauncherDir, 'logs', 'dll_runs')
        self.ErscLocaleDir = j(self.LauncherDir, 'ersc_locale')
        self.CoopProfile = j(self.Paly, 'dll', 'dark_core', 'coop_profile.txt')
        self.CoopWorldFile = j(self.LauncherDir, 'reroll', 'state', 'coop_world.txt')
        self.CoopHostModeFile = j(self.LauncherDir, 'reroll', 'state', 'coop_host_mode.txt')
        self.CoopJoinCodeFile = j(self.LauncherDir, 'reroll', 'state', 'coop_join_code.txt')
        self.CoopHostCodeFile = j(self.Paly, 'dll', 'dark_core', 'coop_host_code.txt')
        self.BossModsDir = j(self.LauncherDir, 'reroll', 'data', 'bossmods')
        self.BossModeDef = j(self.Paly, 'dll', 'dark_core', 'bossmods.txt')
        self.CrashDir = j(self.Paly, '崩溃诊断')
        self.LogDir = j(self.LauncherDir, 'logs')

        # ---- 存档和记录（launcher.ps1 的 $SaveRootDir、backup.ps1 开头）
        self.SaveRootDir = j(_env_dir('APPDATA'), 'EldenRing')
        self.RngSaveRoot = self.SaveRootDir
        self.RngDataDir = j(self.RngSaveRoot, 'DarkReforged')
        self.RngRecordDir = j(self.RngDataDir, '角色记录')
        self.RngBackupDir = j(self.RngDataDir, '启动前备份')
        self.RngOldDir = j(self.RngDataDir, '旧文件')
        self.RngVersionFile = j(self.RngDataDir, 'version.txt')
        self.RngOpsLog = j(self.LauncherDir, 'logs', 'save_ops.txt')

        # ---- 随机器（randomize.ps1 开头）
        self.RandSettingsRoot = j(_env_dir('LOCALAPPDATA'), 'EldenRingRandomizer.Avalo')
        self.RandSettingsMap = j(self.LauncherDir, 'randomizer_settings_path.txt')
        self.BundledDotNet = j(self.LauncherDir, 'dotnet')
        self.RandomHiDir = j(self.Paly, 'randomizer_hi')
        self.RandPacksFile = j(self.RngDataDir, 'packs.txt')

        # ---- 玩家 mod（usermods.ps1 开头）
        self.UserModDir = j(self.Paly, 'mods')
        self.UserIniPath = j(self.Paly, 'YAFSML自定义.ini')

        # ---- 运行中的状态（$script:...；各模块用到时再设）
        self.CacheGameRoot = None
        self.CoopDll = ''
        self.CoopRole = ''
        self.ErdSaveExt = 'rng'
        self.PyErr = []
        self.ExitCode = None
        self.LogPath = None
        self.LogStart = None

        # 上次启动的世界（out\current_world.txt）：状态显示、诊断包读它，Invoke-Launch 再按这次的世界换
        last = ''
        try:
            last = read_text(self.WorldFile).strip()
        except OSError:
            pass
        set_world_packs(self, last if re.fullmatch(r'[a-z_]*', last) else '')


def set_world_packs(ctx, Suffix):
    """Set-WorldPacks：重随包、修补过的地图、游戏脚本覆盖包按「世界」各存一份（后缀 _van _hi _coop …）"""
    ctx.WorldSuffix = Suffix
    ctx.RerollPack = os.path.join(ctx.Paly, 'out', 'reroll' + Suffix)
    ctx.RerollMapsPack = os.path.join(ctx.Paly, 'out', 'reroll_maps' + Suffix)
    ctx.ScriptsPack = os.path.join(ctx.Paly, 'out', 'scripts' + Suffix)


# ---------------------------------------------------------------- 文本文件
def read_text(path, errors='strict'):
    """读 UTF-8 文本（有 BOM 就去掉，和 PowerShell 的 ReadAllText / Get-Content -Encoding UTF8 一样）；换行原样保留"""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(b'\xef\xbb\xbf'):
        raw = raw[3:]
    return raw.decode('utf-8', errors)


def read_lines(path, errors='strict'):
    """按行读（去掉行尾的 \\r\\n / \\n，和 Get-Content 一样）"""
    return read_text(path, errors).splitlines()


def write_text(path, text, bom=False, crlf=False):
    """写 UTF-8 文本。crlf=True 先把换行统一成 \\r\\n（\\n 和 \\r\\n 混着的也行）；不改别的字节"""
    if crlf:
        text = text.replace('\r\n', '\n').replace('\n', '\r\n')
    data = (b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)


def write_lines(path, lines, bom=False):
    """[IO.File]::WriteAllLines：每行后面都加 \\r\\n（最后一行也加）"""
    write_text(path, ''.join(l + '\r\n' for l in lines), bom=bom)


# ---------------------------------------------------------------- 输出（Write-*）
class _Out:
    """所有输出都走这里：写到标准输出（图形界面读它），运行日志开着时也写一份"""
    log = None

    @classmethod
    def line(cls, text=''):
        s = str(text).replace('\r\n', '\n')          # 整段带 `r`n 的文字：标准输出是文本模式，\n 自己会变成 \r\n，不能再带 \r
        try:
            sys.stdout.write(s + '\n')
            sys.stdout.flush()
        except (OSError, ValueError):
            pass
        if cls.log is not None:
            try:
                cls.log.write(s.replace('\n', '\r\n') + '\r\n')
                cls.log.flush()
            except (OSError, ValueError):
                pass


def host(text=''):
    """Write-Host：原样一行"""
    _Out.line(text)


def write_head(Text):
    _Out.line('')
    _Out.line('=== ' + Text + ' ===')


def write_ok(Text):
    _Out.line('  [OK] ' + Text)


def write_warn(Text):
    _Out.line('  [提示] ' + Text)


def write_err(Text):
    _Out.line('  [错误] ' + Text)


def write_player(Text):
    """给玩家看的进度（图形界面只显示 § 开头的行和 [错误]）"""
    _Out.line('§ ' + Text)


def write_player_warn(Text):
    _Out.line('§ [提示] ' + Text)


def write_progress_bar(Pct):
    """进度条：「§% 百分比」，图形界面画在上一行给玩家看的进度后面"""
    _Out.line('§% ' + str(int(Pct)))


def setup_console():
    """标准输出 / 错误输出用 UTF-8（图形界面按 UTF-8 读；和 launcher.ps1 开头设 Console.OutputEncoding 一样）"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------- 运行日志（Start-Transcript + Compress-TranscriptLog）
LOG_KEEP = 30
NO_LOG_ACTIONS = ('help', 'list', 'diag', 'watch')


def start_run_log(ctx):
    """每次运行的完整输出存到 launcher\\logs\\<时间>_<动作>.log，只留最近 30 份（help / list / diag / watch 不记）"""
    if ctx.Action in NO_LOG_ACTIONS:
        return
    try:
        os.makedirs(ctx.LogDir, exist_ok=True)
        logs = [os.path.join(ctx.LogDir, n) for n in os.listdir(ctx.LogDir) if n.lower().endswith('.log')]
        logs = [p for p in logs if os.path.isfile(p)]
        logs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in logs[LOG_KEEP - 1:]:
            try:
                os.remove(p)
            except OSError:
                pass
        ctx.LogStart = datetime.datetime.now()
        ctx.LogPath = os.path.join(ctx.LogDir, ctx.LogStart.strftime('%Y%m%d_%H%M%S_') + '%03d' % (ctx.LogStart.microsecond // 1000) + '_' + ctx.Action + '.log')
        _Out.log = open(ctx.LogPath, 'w', encoding='utf-8', newline='')
    except OSError:
        _Out.log = None


def finish_run_log(ctx):
    """结束时把日志开头换成一行：动作、开始 / 结束时间、Python 和 Windows 版本（UTF-8 带 BOM，和以前的日志一样）"""
    if _Out.log is None:
        return
    try:
        _Out.log.close()
    except OSError:
        pass
    _Out.log = None
    try:
        body = read_text(ctx.LogPath).split('\r\n')
        if body and body[-1] == '':
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        head = '# %s · %s ~ %s · Python %s · Windows %s' % (
            ctx.Action, ctx.LogStart.strftime('%Y-%m-%d %H:%M:%S'), datetime.datetime.now().strftime('%H:%M:%S'),
            platform.python_version(), platform.version())
        write_lines(ctx.LogPath, [head] + body, bom=True)
    except (OSError, ValueError):
        pass


def report_crash(exc):
    """没接住的异常：和 launcher.ps1 一样写「运行出错」和位置（最后一层调用）"""
    write_err('运行出错：' + str(exc))
    tb = traceback.extract_tb(exc.__traceback__)
    if tb:
        f = tb[-1]
        host('  位置：%s 第 %d 行（%s）' % (os.path.basename(f.filename), f.lineno, f.name))


# ---------------------------------------------------------------- PowerShell 语义的小工具
class Rec(dict):
    """[pscustomobject] / @{} 的替身：属性和下标都能读写（r.Log、r['Log']），属性名照抄 PowerShell 的；没有的属性读出来是 None（和 PowerShell 一样）"""

    def __getattr__(self, k):
        if k.startswith('__'):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v



def ieq(a, b):
    """-eq / -ieq：字符串不分大小写"""
    return str(a).casefold() == str(b).casefold()


def ps_bool(v):
    """PowerShell 的真假：$null、''、0、空数组为假"""
    if v is None:
        return False
    if isinstance(v, (list, tuple, dict, set, str)):
        return len(v) > 0
    return bool(v)


def ps_version(s):
    """[version]'1.2.3'：两到四段数字，转不了返回 None（PowerShell 里转不了是异常 / $null）"""
    s = str(s or '').strip()
    if not re.fullmatch(r'\d+(\.\d+){1,3}', s):
        return None
    return tuple(int(x) for x in s.split('.'))
