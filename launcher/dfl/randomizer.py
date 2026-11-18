# -*- coding: utf-8 -*-
"""随机器（randomize.ps1，以及 launcher.ps1 里随机器的几个动作：Get-LatestRandom、一键重随敌人、补做高难度世界、沿用旧版本的随机结果、打开随机器）。

随机器（thefifthmatt 的 EldenRingRandomizer.exe，Avalonia 版）没有命令行模式：一键重随敌人要用 UI 自动化点它的窗口。
那一部分（Initialize-Uia … Invoke-RandomizeHiWorld 十个函数，文件末尾）是迁移第 2 步：Avalonia 的按钮没有窗口句柄，走 UIA（dfl\\uia.py）。

和 PowerShell 版的约定（dev\\launcher_py\\移植约定.md）：
- 所有公开函数第一个参数都是 ctx（纯函数也带，调用的地方不用记哪个带哪个不带）；参数名、默认值照抄 PowerShell。
- PowerShell 引入 randomize.ps1 时把 $env:DOTNET_ROOT / DOTNET_ROOT_X64 改成自带的 launcher\\dotnet（整个进程都变了）；
  这里不改自己的环境变量，只在启动随机器时给子进程（_rand_env）。Test-DotNet8 照样先看自带的。
- 随机器的设置文件 user.config：PowerShell 用 XmlDocument 读、XmlWriter（缩进、UTF-8 无 BOM、CRLF）整份重写。
  这里用 expat 读成节点树，再照 .NET XmlWriter（Indent）的规则写回，写出的字节和 PowerShell 一样（对照测试里比过），
  ExtraDlls 里的 xmlns:xsi / xmlns:xsd 原样保留。
- Copy-RandItems 以前用 robocopy，这里用 shutil.copytree + copy2（保留修改时间，沿用后按 spoiler 日志的时间核对）。"""
import ctypes
import datetime
import fnmatch
import hashlib
import json
import os
import random
import re
import shutil
import stat
import subprocess
import time
import xml.parsers.expat

from . import core, win
from .core import Rec, host, ieq, write_err, write_head, write_ok, write_player, write_player_warn, write_warn

CREATE_NO_WINDOW = 0x08000000

# ---------------------------------------------------------------- 常量（randomize.ps1 / launcher.ps1 的模块变量，名字照抄）
# 整合包的默认设置：只开敌人随机，其余是随机器推荐项。物品随机玩家可以在随机器里自己开（重随认得出来，dev\item_rand\物品随机兼容.md）
RandDefaultOptions = ('allmaps bossbgm changestats crashfix dlc dlcblessing dlckeysilo earlylegacy editnames enemy markareas mats norandom '
                      'norandom_health norandom_scadu norandom_upgrades phasehp raceloc_health raceloc_scadu scale spellshops v16 '
                      'weaponprogression bias:20')
DotNet8Url = 'https://dotnet.microsoft.com/download/dotnet/8.0'
# 随机器的许可不许转发，玩家自己下载；版本按程序的 SHA-256 认（文件版本号里没有）：测过的才算，别的版本照样能用，只提示没测过
RandomizerUrl = 'https://www.nexusmods.com/eldenring/mods/428'
RandomizerTested = {'8eb132f8e47a21dfffb3d0016c1117de2bb6c86b643ad9f8fba99079ab1c6cf4': 'v0.12.2'}
# 高难度世界（randomizer_hi）要搬的随机器输出、记录文件
RandHiItems = ['map', 'event', 'msg', 'script', 'sfx', 'regulation.bin', 'config_eldenringrandomizer.toml']
RandHiSource = 'hi_source.json'
# 随机器生成的东西（打包时排除的那些）；spoiler_logs 放最后：复制到一半中断时不会被当成完整的结果
RandOutputItems = ['map', 'event', 'msg', 'script', 'sfx', 'regulation.bin', 'config_eldenringrandomizer.toml', 'spoiler_logs']


class _Ver(tuple):
    """[version]：按段比较（'0.7' < '0.7.0'，和 .NET 的 -1 段一样），转字符串是 0.10.13 这样"""

    def __str__(self):
        return '.'.join(str(x) for x in self)

    def __repr__(self):
        return "_Ver('%s')" % self


def _ver(s):
    v = core.ps_version(s)
    return _Ver(v) if v is not None else None


# 只沿用整合包版本不低于它的（v0.7 起随机器不再合并别的包）
RandCarryMinVersion = _ver('0.7')


class _Thrown(Exception):
    """PowerShell 的 throw '文字'：$_.Exception.Message 就是这段文字"""


def _exc_message(e):
    """$_.Exception.Message 的近似（系统错误的措辞和 .NET 不一样，没法逐字一样）"""
    if isinstance(e, OSError) and e.strerror:
        return e.strerror + ('：' + str(e.filename) if e.filename else '')
    return str(e)


# ---------------------------------------------------------------- 文件小工具（Get-ChildItem / Get-Content / ReadAllText 的语义）
_HIDDEN = 0x2
_DIRECTORY = 0x10
_TICKS_1970 = 621355968000000000


def _ticks(mtime_ns):
    """LastWriteTimeUtc.Ticks"""
    return mtime_ns // 100 + _TICKS_1970


def _local_dt(mtime_ns):
    """LastWriteTime（本地时间，精确到微秒）"""
    return datetime.datetime.fromtimestamp(mtime_ns // 10 ** 9) + datetime.timedelta(microseconds=(mtime_ns // 1000) % 10 ** 6)


class _Item:
    """Get-ChildItem 列出来的一项"""
    __slots__ = ('FullName', 'Name', 'IsDir', 'Length', 'MtimeNs')

    def __init__(self, path, name, isdir, st):
        self.FullName = path
        self.Name = name
        self.IsDir = isdir
        self.Length = 0 if isdir else st.st_size
        self.MtimeNs = st.st_mtime_ns

    @property
    def DirectoryName(self):
        return os.path.dirname(self.FullName)

    @property
    def LastWriteTime(self):
        return _local_dt(self.MtimeNs)


def _wild(pattern):
    """-Filter 的通配符（Win32：* 和 ?，不分大小写；「X.*」也匹配没有扩展名的 X）"""
    tail = ''
    if pattern.endswith('.*'):
        pattern, tail = pattern[:-2], r'(?:\..*)?'
    rx = ''.join('.*' if c == '*' else '.' if c == '?' else re.escape(c) for c in pattern)
    return re.compile('^' + rx + tail + '$', re.I | re.S)


def _gci(path, Filter=None, File=False, Directory=False, Recurse=False, Depth=None):
    """Get-ChildItem -LiteralPath path [-Filter] [-File / -Directory] [-Recurse [-Depth]] -ErrorAction SilentlyContinue：
    顺序是文件系统给的顺序；没有 -Force 时隐藏的文件 / 文件夹不列、也不进去；递归时先列完这一层，再按顺序进每个子文件夹"""
    out = []
    rx = _wild(Filter) if Filter else None

    def walk(d, level):
        try:
            ents = list(os.scandir(d))
        except OSError:
            return
        subs = []
        for e in ents:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            attrs = getattr(st, 'st_file_attributes', 0)
            if attrs & _HIDDEN:
                continue
            isdir = bool(attrs & _DIRECTORY)
            if isdir:
                subs.append(e.path)
            if (File and isdir) or (Directory and not isdir):
                continue
            if rx is not None and not rx.match(e.name):
                continue
            out.append(_Item(e.path, e.name, isdir, st))
        if Recurse and (Depth is None or level < Depth):
            for s in subs:
                walk(s, level + 1)
    walk(path, 0)
    return out


def _ps_sort(items, key, Descending=False):
    """Sort-Object <属性> [-Descending]（PowerShell 5.1 的不稳定排序，一样新的两个文件挑出来的才和以前是同一个）：见 win.ps_sort_key"""
    return win.ps_sort_key(items, key, Descending)


def _newest(items):
    """Sort-Object LastWriteTime -Descending | Select-Object -First 1"""
    if not items:
        return None
    return _ps_sort(items, lambda i: i.MtimeNs // 100, Descending=True)[0]


def _newest_log(log_dir):
    return _newest(_gci(log_dir, '*_log_*.txt', File=True))


def _decode(raw):
    """StreamReader / ReadAllText：认 BOM（UTF-8 / UTF-16 / UTF-32），默认 UTF-8；坏字节换成 U+FFFD，不报错。
    文件末尾不完整的半个字符 .NET 直接丢掉（解码器最后没 flush），这里也丢（final=False）"""
    import codecs
    enc, skip = 'utf-8', 0
    if raw.startswith(b'\xef\xbb\xbf'):
        skip = 3
    elif raw.startswith(b'\xff\xfe\x00\x00'):
        enc, skip = 'utf-32-le', 4
    elif raw.startswith(b'\xff\xfe'):
        enc, skip = 'utf-16-le', 2
    elif raw.startswith(b'\xfe\xff'):
        enc, skip = 'utf-16-be', 2
    return codecs.getincrementaldecoder(enc)('replace').decode(raw[skip:], final=False)


def _read_all_text(path):
    """[IO.File]::ReadAllText（文件不在 / 读不了抛 OSError）"""
    with open(path, 'rb') as f:
        return _decode(f.read())


_NL = re.compile(r'\r\n|\r|\n')


def _split_lines(text):
    """Get-Content / StreamReader.ReadLine 的分行：只认 \\r\\n、\\r、\\n；最后的换行后面不多出空行"""
    if not text:
        return []
    parts = _NL.split(text)
    if parts[-1] == '':
        parts.pop()
    return parts


def _gc_lines(path, TotalCount=None):
    """Get-Content -LiteralPath path [-TotalCount N] -Encoding UTF8：按行；文件不在抛 OSError。
    只要前几行时只读够用的部分（spoiler 日志有好几 MB）。随机器可能还开着日志，Python 的 open 允许别人同时读写"""
    with open(path, 'rb') as f:
        if TotalCount is None:
            return _split_lines(_decode(f.read()))
        raw = b''
        while True:
            chunk = f.read(65536)
            raw += chunk
            if not chunk:
                return _split_lines(_decode(raw))[:TotalCount]
            parts = _NL.split(_decode(raw))
            if len(parts) - 1 >= TotalCount:          # 前 N 行都已经完整（最后一段可能不完整，不要）
                return parts[:TotalCount]


def _try_lines(path, TotalCount=None):
    """同上，-ErrorAction SilentlyContinue：读不了就是空的"""
    try:
        return _gc_lines(path, TotalCount)
    except OSError:
        return []


def _net_dirname(p):
    """[IO.Path]::GetDirectoryName：根目录（E:\\、E:）返回 None"""
    if not p:
        return None
    d = os.path.dirname(p)
    if not d or d == p:
        return None
    return d


def _jp(a, b):
    """Join-Path：「E:」这种只有盘符的也接成「E:\\…」（os.path.join 会接成相对路径）"""
    if len(a) == 2 and a[1] == ':':
        a += '\\'
    return os.path.join(a, b)


def _full_path(p):
    """[IO.Path]::GetFullPath：空的抛异常（os.path.abspath 会返回当前目录）"""
    if not p or not str(p).strip():
        raise ValueError('路径的形式不合法。')
    return os.path.abspath(p)


def _oic(a, b):
    """String.Equals(…, OrdinalIgnoreCase)：逐个字符转大写比"""
    def up(s):
        return ''.join(c.upper() if len(c.upper()) == 1 else c for c in s)
    return up(a) == up(b)


def _icontains(seq, x):
    """-contains / -notcontains（字符串不分大小写）"""
    return any(ieq(s, x) for s in seq)


def _ps_str(v):
    """[string]$v"""
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _to_long(v):
    """[long]$v：$null = 0；小数按银行家舍入；转不了抛 ValueError（PowerShell 也是报错）"""
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    s = str(v).strip()
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        pass
    if s.lower().startswith('0x'):
        return int(s, 16)
    return int(round(float(s)))


def _ps_array(v):
    """@($v)：$null 是一个 $null 元素，数组原样，别的包成一个元素"""
    if v is None:
        return [None]
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _to_rec(v):
    """ConvertFrom-Json 的对象：dict → Rec（属性访问 h.seed、h.time），里面的也转"""
    if isinstance(v, dict):
        return Rec((k, _to_rec(x)) for k, x in v.items())
    if isinstance(v, list):
        return [_to_rec(x) for x in v]
    return v


def _read_json(path):
    import json
    return json.loads(_read_all_text(path))


def _make_writable(p):
    try:
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _remove_item(path):
    """Remove-Item -LiteralPath path -Recurse -Force：只读的也删；目录联接 / 符号链接只删链接本身，不进去删"""
    if os.path.isjunction(path) or os.path.islink(path):
        try:
            os.rmdir(path)
        except OSError:
            os.unlink(path)
        return
    if os.path.isdir(path):
        def onexc(func, p, exc):
            _make_writable(p)
            func(p)
        shutil.rmtree(path, onexc=onexc)
        return
    try:
        os.remove(path)
    except PermissionError:
        _make_writable(path)
        os.remove(path)


_ATTR_KEEP = 0x1 | 0x2 | 0x4 | 0x20         # 只读、隐藏、系统、存档：robocopy / Copy-Item（CopyFile）都照搬
_k32 = ctypes.WinDLL('kernel32', use_last_error=True)     # 自己的一份（不改 win.kernel32 上函数的 argtypes）
_GetFileAttributesW = _k32.GetFileAttributesW
_GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
_GetFileAttributesW.restype = ctypes.c_uint32
_SetFileAttributesW = _k32.SetFileAttributesW
_SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]


def _copy_force(src, dst):
    """copy2（内容 + 修改时间）；目标是只读的也覆盖（Copy-Item -Force / robocopy）；文件属性（隐藏、只读……）照搬"""
    if os.path.isfile(dst) and not os.access(dst, os.W_OK):
        _make_writable(dst)
    r = shutil.copy2(src, dst)
    a = _GetFileAttributesW(src)
    if a != 0xFFFFFFFF and a & _ATTR_KEEP:
        _SetFileAttributesW(r, a & _ATTR_KEEP)
    return r


def _copy_tree_file(src, dst):
    """copytree 里复制一个文件：目标那里是个文件夹时报错（copy2 会悄悄复制进那个文件夹里；robocopy 是跳过、照样算成功，结果不完整）"""
    if os.path.isdir(dst):
        raise IsADirectoryError(21, '目标是个文件夹', dst)
    return _copy_force(src, dst)


# ---------------------------------------------------------------- 时间（.dr_manual.preset 第一行：.NET 的 ToString('o')）
def _now_o():
    """(Get-Date).ToString('o')：本地时间、7 位小数、带时区，如 2026-11-18T08:50:37.4090254-05:00"""
    ns = time.time_ns()
    dt = datetime.datetime.fromtimestamp(ns // 10 ** 9).astimezone()
    off = int(dt.utcoffset().total_seconds())
    sign = '+' if off >= 0 else '-'
    off = abs(off)
    return dt.strftime('%Y-%m-%dT%H:%M:%S') + '.%07d' % ((ns // 100) % 10 ** 7) + '%s%02d:%02d' % (sign, off // 3600, off % 3600 // 60)


_DT_RX = re.compile(r'^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?\s*(Z|[+-]\d{2}(?::?\d{2})?)?\s*$', re.I)


def _parse_dt_ticks(s):
    """[datetime]::TryParse 的近似（只认 ISO 8601：'o' 格式、带不带时区、带不带小数）→ UTC 的 Ticks；认不出返回 None。
    比较用 UTC：PowerShell 比的是本地时间，夏令时切换那一小时里会差一点，这里更准"""
    m = _DT_RX.match(str(s or ''))
    if not m:
        return None
    y, mo, d, h, mi, sec, frac, tz = m.groups()
    try:
        dt = datetime.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(sec or 0))
    except ValueError:
        return None
    sub = int((frac or '0')[:7].ljust(7, '0'))          # 100 纳秒为单位
    if tz is None:
        try:
            dt = dt.astimezone()                        # 没写时区 = 本地时间
        except (OverflowError, OSError, ValueError):
            return None
        utc = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    elif tz.upper() == 'Z':
        utc = dt
    else:
        t = tz.replace(':', '')
        off = int(t[1:3]) * 60 + (int(t[3:5]) if len(t) > 3 else 0)
        utc = dt - datetime.timedelta(minutes=off if t[0] == '+' else -off)
    epoch = datetime.datetime(1970, 1, 1)
    delta = utc - epoch
    return (delta.days * 86400 + delta.seconds) * 10 ** 7 + delta.microseconds * 10 + sub + _TICKS_1970


# ---------------------------------------------------------------- .NET 8 运行时
def _has_dotnet8(root):
    return bool(root) and bool(_gci(os.path.join(root, 'shared', 'Microsoft.NETCore.App'), '8.*', Directory=True))


def _dotnet_root(ctx):
    """引入 randomize.ps1 后 $env:DOTNET_ROOT 的值：自带的 launcher\\dotnet 里有 8.x 就是它，否则是继承来的"""
    if _has_dotnet8(ctx.BundledDotNet):
        return ctx.BundledDotNet
    return os.environ.get('DOTNET_ROOT') or ''


def _rand_env(ctx):
    """启动随机器用的环境变量：自带的 .NET 8 在就让随机器用它（新电脑不用装），只给子进程，不改自己的"""
    env = dict(os.environ)
    if _has_dotnet8(ctx.BundledDotNet):
        env['DOTNET_ROOT'] = ctx.BundledDotNet
        env['DOTNET_ROOT_X64'] = ctx.BundledDotNet
    return env


def _start_randomizer(ctx, Exe=None):
    """Start-Process 随机器（工作目录 = 它所在的文件夹）。不等它；句柄不继承（图形界面读我们的输出管道，不能被随机器占着）。
    返回 Popen（第 2 步的 New-RandSettingsFile / Invoke-RandomizeEnemies 要用 -PassThru 的进程）"""
    exe = Exe or ctx.RandomExe
    return subprocess.Popen([exe], cwd=os.path.dirname(exe), env=_rand_env(ctx), close_fds=True)


def test_dot_net8(ctx):
    """Test-DotNet8：$env:DOTNET_ROOT（见 _dotnet_root）或 Program Files\\dotnet 里有 Microsoft.NETCore.App 8.x"""
    roots = []
    dr = _dotnet_root(ctx)
    if dr:
        roots.append(dr)
    pf = os.environ.get('ProgramFiles')
    if pf:
        roots.append(os.path.join(pf, 'dotnet'))
    for r in roots:
        if _has_dotnet8(r):
            return True
    return False


def get_dot_net8_msg(ctx):
    return ('找不到 .NET 8 运行时（整合包自带的 launcher\\dotnet 不见了，系统里也没装），随机器打不开。' + '\r\n' +
            '重新解压整合包可以恢复自带的；或者' + '\r\n' +
            '请到 ' + DotNet8Url + ' 下载「.NET 桌面运行时 8.0」的 Windows x64 安装包，装好后再试。' + '\r\n' +
            '（不玩敌人随机的话不用装：无敌人随机照常能玩。）')


# ---------------------------------------------------------------- 随机器装了没有
def get_randomizer_how_to(ctx):
    return ('敌人随机要用 thefifthmatt 的随机器（Elden Ring Item and Enemy Randomizer）。整合包不带它（它的许可不许转发），要自己下载：' + '\r\n\r\n' +
            '1. 打开 ' + RandomizerUrl + '，在 Files 里下载 v0.12.2（整合包测过的版本，在 Old files 里）；' + '\r\n' +
            '2. 把压缩包里的东西全部解压到整合包的 randomizer 文件夹（和 launcher 文件夹并排；图形界面里点「打开 randomizer 文件夹」能直接打开）。' + '\r\n' +
            '    解压好后 randomizer 文件夹里直接就是 EldenRingRandomizer.exe，中间不要多一层文件夹；' + '\r\n' +
            '3. 重新打开启动器。' + '\r\n\r\n' +
            '不装随机器也能玩「无敌人随机」，联机也能用「联机 · 无敌人随机」。')


def get_randomizer_status(ctx):
    """随机器的状态 Rec(Ok, Msg, Version, Tested)：每次现查（玩家可能开着启动器时装上），只有程序的哈希按大小和修改时间缓存在 ctx.RandExeHash"""
    exe = os.path.join(ctx.RandomDir, 'EldenRingRandomizer.exe')
    if not os.path.exists(exe):
        nested = _gci(ctx.RandomDir, 'EldenRingRandomizer.exe', File=True, Recurse=True, Depth=2)
        if nested:
            sub = nested[0].DirectoryName[len(ctx.RandomDir):].lstrip('\\')
            return Rec(Ok=False, Msg=('随机器解压多了一层文件夹（randomizer\\' + sub + '）。' + '\r\n\r\n' +
                                      '把这个文件夹里的东西全部挪到 randomizer 文件夹下面（EldenRingRandomizer.exe 要直接在 randomizer 文件夹里），再重新打开启动器。'))
        return Rec(Ok=False, Msg=get_randomizer_how_to(ctx))
    if not os.path.exists(os.path.join(ctx.RandomDir, 'diste', 'Base', 'enemy.txt')):
        return Rec(Ok=False, Msg='随机器文件夹不完整（缺 diste 文件夹）。重新下载随机器，把压缩包里的东西全部解压到整合包的 randomizer 文件夹。')
    st = os.stat(exe)
    # 文件夹没有 Length，PowerShell 给的是「标量的 .Length」= 1
    key = ('1' if os.path.isdir(exe) else str(st.st_size)) + '|' + str(_ticks(st.st_mtime_ns))
    cache = getattr(ctx, 'RandExeHash', None)
    if not cache or cache.Key != key:
        try:
            h = hashlib.sha256()
            with open(exe, 'rb') as f:
                for chunk in iter(lambda: f.read(1 << 20), b''):
                    h.update(chunk)
            hx = h.hexdigest()
        except OSError:
            hx = ''
        ctx.RandExeHash = Rec(Key=key, Hash=hx)
    v = RandomizerTested.get(ctx.RandExeHash.Hash)
    return Rec(Ok=True, Msg='', Version=v, Tested=bool(v))


def get_randomizer_untested_msg(ctx):
    return ('这个版本的随机器整合包没测过（测过的是 v0.12.2），可能有问题：比如敌人预设、按位置修正对不上。出问题时换回 v0.12.2（' + RandomizerUrl + ' 的 Old files）。')


# ---------------------------------------------------------------- 随机器的设置文件（user.config）在哪
# 记录（launcher\randomizer_settings_path.txt）两行：设置文件、它属于的随机器 exe。exe 对不上就不用（整合包文件夹挪过 / 复制过，
# 用了会把游戏路径、选项写进别的随机器的设置，用户 2026-11-17「联机的时候随机器没有默认加载保存的游戏路径」）。
# 只有一行的旧记录认不准：设置里写着这份随机器的 dll 目录才算数，否则记作 ctx.RandSettingsGuess（实在认不出来时才退回去用它）
def get_rand_exe_path(ctx):
    return os.path.abspath(os.path.join(ctx.RandomDir, 'EldenRingRandomizer.exe'))


def save_rand_settings_map(ctx, File):
    """两行，UTF-8 无 BOM、CRLF"""
    core.write_text(ctx.RandSettingsMap, (File or '') + '\r\n' + get_rand_exe_path(ctx) + '\r\n')


def _user_configs(ctx):
    """随机器所有的设置文件，新的在前"""
    items = _gci(ctx.RandSettingsRoot, 'user.config', File=True, Recurse=True)
    return [i.FullName for i in _ps_sort(items, lambda i: i.MtimeNs // 100, Descending=True)]


def find_rand_settings_file(ctx):
    """这份随机器对应的设置文件；还没有或认不准返回 None（要用时 resolve_rand_settings_file 打开一次随机器来认）"""
    ctx.RandSettingsGuess = None
    dll_dir = os.path.join(ctx.RandomDir, 'dll').lower()
    if os.path.exists(ctx.RandSettingsMap):
        lines = _gc_lines(ctx.RandSettingsMap, 2)
        p = lines[0].strip() if len(lines) >= 1 else ''
        who = lines[1].strip() if len(lines) >= 2 else ''
        if p and os.path.exists(p):
            if who:
                if _oic(who, get_rand_exe_path(ctx)):
                    return p
            elif dll_dir in _read_all_text(p).lower():
                save_rand_settings_map(ctx, p)
                return p
            else:
                ctx.RandSettingsGuess = p
    for f in _user_configs(ctx):
        # 随机器开了崩溃修复时，额外 DLL 里是它自己 dll 目录的完整路径：能认出是哪一份
        if dll_dir in _read_all_text(f).lower():
            save_rand_settings_map(ctx, f)
            return f
    return None


def resolve_rand_settings_file(ctx, Exe):
    """一定要拿到这份随机器的设置文件时用：认不出来就打开一次随机器（第 2 步的 new_rand_settings_file）；
    打开了还认不出来，有只有一行的旧记录就照旧用它。返回设置文件或 None。
    """
    f = find_rand_settings_file(ctx)
    if f:
        return f
    guess = getattr(ctx, 'RandSettingsGuess', None)
    if guess:
        host('  先打开一次随机器，认一下这份随机器用的是哪个设置文件（会自动关掉，不要点它）...')
    else:
        host('  第一次用这份随机器：先打开一次让它生成设置文件（会自动关掉，不要点它）...')
    try:
        f = new_rand_settings_file(ctx, Exe)
    except NotImplementedError:
        raise
    except Exception:
        f = None
    if f:
        return f
    return guess


# ---------------------------------------------------------------- user.config 的读写（[xml] + XmlWriter）
class _XNode:
    __slots__ = ('kind', 'name', 'attrs', 'children', 'empty', 'text')

    def __init__(self, kind, name='', text=''):
        self.kind = kind            # doc / elem / text / cdata / comment / pi
        self.name = name
        self.attrs = []             # [(名字, 值)]，文档里的顺序（xmlns:xsi 这种也在里面）
        self.children = []
        self.empty = False          # 原文是 <x /> 这种（.NET 的 IsEmpty）：没有子节点时写回 <x />，否则写 <x></x>
        self.text = text


def _tag_is_empty(data, i):
    """data[i] 是一个开始标签的 <：这个标签是不是以 /> 结尾（属性值里的 > 跳过）"""
    j, q, n = i + 1, 0, len(data)
    while j < n:
        c = data[j]
        if q:
            if c == q:
                q = 0
        elif c in (0x22, 0x27):
            q = c
        elif c == 0x3e:
            return data[j - 1] == 0x2f
        j += 1
    return False


def _xml_load(text):
    """[xml]$text：XmlDocument（不保留空白：只有空白的文字节点丢掉）。不是合法的 XML 抛 ValueError；有 DOCTYPE 的也不认"""
    data = text.encode('utf-8')
    p = xml.parsers.expat.ParserCreate(encoding='utf-8')     # 按 UTF-8 读，不管声明里写的编码（读的是已经解码的文字）
    p.ordered_attributes = True
    doc = _XNode('doc')
    doc.attrs = [('standalone', -1)]
    stack = [doc]
    pend = []
    cdata = []
    st = {'in_cdata': False}

    def flush():
        if pend:
            t = ''.join(pend)
            pend.clear()
            if t.strip(' \t\r\n'):
                stack[-1].children.append(_XNode('text', text=t))

    def start(name, attrs):
        flush()
        n = _XNode('elem', name)
        n.attrs = list(zip(attrs[0::2], attrs[1::2]))
        n.empty = _tag_is_empty(data, p.CurrentByteIndex)
        stack[-1].children.append(n)
        stack.append(n)

    def end(name):
        flush()
        stack.pop()

    def chars(t):
        (cdata if st['in_cdata'] else pend).append(t)

    def cdata_start():
        flush()
        st['in_cdata'] = True
        cdata.clear()

    def cdata_end():
        st['in_cdata'] = False
        stack[-1].children.append(_XNode('cdata', text=''.join(cdata)))

    def comment(t):
        flush()
        stack[-1].children.append(_XNode('comment', text=t))

    def pi(target, d):
        flush()
        stack[-1].children.append(_XNode('pi', target, d))

    def decl(version, encoding, standalone):
        doc.attrs = [('standalone', standalone)]

    def doctype(*a):
        raise ValueError('DOCTYPE')

    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chars
    p.StartCdataSectionHandler = cdata_start
    p.EndCdataSectionHandler = cdata_end
    p.CommentHandler = comment
    p.ProcessingInstructionHandler = pi
    p.XmlDeclHandler = decl
    p.StartDoctypeDeclHandler = doctype
    try:
        p.Parse(data, True)
    except xml.parsers.expat.ExpatError as e:
        raise ValueError(str(e))
    return doc


def _xml_elems(n):
    """文档顺序的所有元素（// 的范围）"""
    for c in n.children:
        if c.kind == 'elem':
            yield c
            yield from _xml_elems(c)


def _xml_attr(n, name):
    for k, v in n.attrs:
        if k == name:
            return v
    return None


def _xml_find_value(doc, Name):
    """SelectSingleNode("//setting[@name='Name']/value")"""
    for s in _xml_elems(doc):
        if s.name == 'setting' and _xml_attr(s, 'name') == Name:
            for c in s.children:
                if c.kind == 'elem' and c.name == 'value':
                    return c
    return None


def _xml_section(doc):
    """SelectSingleNode('//userSettings/*')"""
    for u in _xml_elems(doc):
        if u.name == 'userSettings':
            for c in u.children:
                if c.kind == 'elem':
                    return c
    return None


def _xml_inner_text(n):
    """InnerText：所有文字（含 CDATA）连起来"""
    if n.kind in ('text', 'cdata'):
        return n.text
    if n.kind == 'elem' or n.kind == 'doc':
        return ''.join(_xml_inner_text(c) for c in n.children)
    return ''


_XML_BAD = re.compile('[^\t\n\r\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]')


def _xml_check(s):
    """XmlWriter（CheckCharacters）遇到 XML 里不许有的字符会报错"""
    m = _XML_BAD.search(s)
    if m:
        raise ValueError("'%s'，十六进制值 0x%02X，是无效的字符。" % (m.group(0), ord(m.group(0))))
    return s


def _esc_text(s):
    s = _xml_check(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return s.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')       # NewLineHandling.Replace


def _esc_attr(s):
    return (_xml_check(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            .replace('\t', '&#x9;').replace('\n', '&#xA;').replace('\r', '&#xD;'))


class _XmlWriter:
    """XmlDocument.Save(XmlWriter.Create(…, Indent = $true))：照 .NET 的 XmlEncodedRawTextWriterIndent 写——
    两个空格缩进、\\r\\n 换行；元素里一出现文字（哪怕是空的）就不再给后面的子节点缩进；没有子节点的空元素写 <x />；
    开头的声明总是 <?xml version="1.0" encoding="utf-8"?>（编码名按写的编码），最后没有换行"""

    def __init__(self):
        self.buf = []
        self.pos = 0
        self.text_pos = 0
        self.content_pos = 0
        self.mixed = False
        self.stack = []
        self.level = 0

    def w(self, s):
        self.buf.append(s)
        self.pos += len(s)

    def indent_if(self):
        if not self.mixed and self.text_pos != self.pos:
            self.w('\r\n' + '  ' * self.level)

    def node(self, n):
        k = n.kind
        if k == 'elem':
            self.indent_if()
            self.level += 1
            self.stack.append(self.mixed)
            self.w('<' + n.name)
            for a, v in n.attrs:
                self.w(' ' + a + '="' + _esc_attr(v) + '"')
            # StartElementContent：根元素不继承 mixed
            self.mixed = False if self.level == 1 else self.stack[-1]
            self.w('>')
            self.content_pos = self.pos
            if n.empty and not n.children:
                self.level -= 1
                self.mixed = self.stack.pop()
                self.buf.pop()                     # 去掉刚写的 >，写成 " />"
                self.pos -= 1
                self.w(' />')
            else:
                for c in n.children:
                    self.node(c)
                self.level -= 1
                if not self.mixed and self.content_pos != self.pos and self.text_pos != self.pos:
                    self.w('\r\n' + '  ' * self.level)
                self.mixed = self.stack.pop()
                self.w('</' + n.name + '>')
        elif k == 'text':
            self.mixed = True
            self.w(_esc_text(n.text))
            self.text_pos = self.pos
        elif k == 'cdata':
            self.mixed = True
            self.w('<![CDATA[' + _xml_check(n.text).replace(']]>', ']]]]><![CDATA[>') + ']]>')
            self.text_pos = self.pos
        elif k == 'comment':
            self.indent_if()
            self.w('<!--' + _xml_check(n.text) + '-->')
        elif k == 'pi':
            self.indent_if()
            self.w('<?' + n.name + (' ' + _xml_check(n.text) if n.text else '') + '?>')

    def document(self, doc):
        sa = doc.attrs[0][1] if doc.attrs else -1
        self.w('<?xml version="1.0" encoding="utf-8"' + {1: ' standalone="yes"', 0: ' standalone="no"'}.get(sa, '') + '?>')
        for c in doc.children:
            self.node(c)
        return ''.join(self.buf)


# Set-RandSettings 按 PowerShell 哈希表的枚举顺序处理键：缺的设置按这个顺序加在最后。哈希表的顺序取决于 .NET 的哈希值，
# 没法一般地算，这里照实测（PowerShell 5.1）写死用得到的几组；别的组合按传进来的顺序
_PS_KEY_ORDER = {
    frozenset(['exe', 'mod', 'options']): ['exe', 'mod', 'options'],
    frozenset(['exe', 'mod']): ['mod', 'exe'],
    frozenset(['mod', 'options']): ['mod', 'options'],
    frozenset(['exe', 'options']): ['exe', 'options'],
}


def _ps_key_order(keys):
    keys = list(keys)
    order = _PS_KEY_ORDER.get(frozenset(k.lower() for k in keys))
    if not order or len(order) != len(keys):
        return keys
    return sorted(keys, key=lambda k: order.index(k.lower()))


def get_rand_setting(ctx, File, Name):
    """设置文件里一项的值；没有 / 读不了返回 None"""
    if not File or not os.path.exists(File):
        return None
    try:
        doc = _xml_load(_read_all_text(File))
    except (OSError, ValueError):
        return None
    n = _xml_find_value(doc, Name)
    if n is not None:
        return _xml_inner_text(n)
    return None


def set_rand_settings(ctx, File, Values):
    """Set-RandSettings：Values = {设置名: 值}；没有的设置加在 userSettings 下第一节的最后。整份按 XmlWriter 的格式重写
    （UTF-8 无 BOM、两空格缩进、CRLF）。读不了 / 不是 XML / 没有 userSettings 抛异常。
    和 PowerShell 有一处不同：值里有 XML 不许的字符时先报错、文件不动（PowerShell 是写到一半报错，文件剩半截）"""
    doc = _xml_load(_read_all_text(File))
    sec = _xml_section(doc)
    for k in _ps_key_order(Values.keys()):
        v = _xml_find_value(doc, k)
        if v is None:
            if sec is None:
                raise ValueError('不能对 Null 值表达式调用方法。')
            s = _XNode('elem', 'setting')
            s.attrs = [('name', k), ('serializeAs', 'String')]
            v = _XNode('elem', 'value')
            v.empty = True
            s.children.append(v)
            sec.children.append(s)
        x = Values[k]
        v.children = [_XNode('text', text=_ps_str(x))]
        v.empty = False
    out = _XmlWriter().document(doc).encode('utf-8')
    with open(File, 'wb') as f:
        f.write(out)


# ---------------------------------------------------------------- 这次用的选项
_RX_V = re.compile(r'\bv\d+\b', re.I)


def _split_ws(s):
    """-split '\\s+' 再去掉空的"""
    return [t for t in re.split(r'\s+', s or '') if t]


def get_randomize_options(ctx):
    """Rec(Options = 不含种子的选项, From = 说明, HasItem = 是否开着物品随机)"""
    sf = find_rand_settings_file(ctx)
    if not sf:
        sf = getattr(ctx, 'RandSettingsGuess', None)     # 认不准的旧记录：先照它（真正随机化前 resolve_rand_settings_file 会认准）
    opt = get_rand_setting(ctx, sf, 'Options')
    frm = '上一次在随机器里用的设置'
    if not opt or not _RX_V.search(opt):
        # 这个文件夹的随机器还没用过（多半是刚更新到新版本）：沿用旧版本随机器里的设置
        opt = None
        for p in get_other_packs(ctx):
            o2 = get_rand_setting(ctx, find_rand_settings_file_for(ctx, os.path.join(p, 'randomizer')), 'Options')
            if o2 and _RX_V.search(o2):
                opt = o2
                frm = '旧版本随机器里的设置（' + p + '）'
                break
    if not opt or not _RX_V.search(opt):
        opt = RandDefaultOptions
        frm = '整合包默认设置（只开敌人随机）'
    tok = [t for t in _split_ws(opt) if not re.match(r'^seed2?:', t, re.I)]
    if not _icontains(tok, 'enemy'):
        tok.append('enemy')                          # 一键重随的就是敌人
    return Rec(Options=' '.join(tok), From=frm, HasItem=_icontains(tok, 'item'))


def reset_rand_mod(ctx, GameExe):
    """自己打开随机器之前：把「合并其它MOD」清空、游戏 exe 填好；写好整合包的自定义敌人预设、勾上 customenemy。
    种子不动（玩家自己勾「重roll种子」，用户 2026-11-04）。随机器开着时不改（它关掉时会把自己的设置写回去）。
    返回给玩家看的一句话（空 = 没什么要说的）"""
    if win.find_pids('EldenRingRandomizer'):
        return ''
    file = find_rand_settings_file(ctx)
    note = ''
    if not file:
        exe = os.path.join(ctx.RandomDir, 'EldenRingRandomizer.exe')
        if not os.path.exists(exe):
            return ''
        why = ''
        try:
            initialize_uia(ctx)
            file = resolve_rand_settings_file(ctx, exe)
        except NotImplementedError:
            raise
        except Exception as e:
            # 以前什么异常都悄悄接住，第一次打开随机器失败时看不到原因（2026-11-18 移植时修）：说一声，照常打开随机器
            file = None
            why = _exc_message(e)
        if not file:
            return ('没找到随机器的设置文件（' + why + '），这次没帮你改设置：打开后请自己确认「合并其它MOD」是空的、游戏路径对。') if why else ''
    v = {'Mod': ''}
    if GameExe and os.path.exists(GameExe):
        v['Exe'] = GameExe
    if update_manual_preset(ctx):
        opt = get_rand_setting(ctx, file, 'Options')
        tok = _split_ws(opt)
        if not (opt and _RX_V.search(opt)):
            tok = _split_ws(get_randomize_options(ctx).Options)     # 设置里还是随机器自己的默认值
        if not _icontains(tok, 'customenemy'):
            tok.append('customenemy')
        v['Options'] = ' '.join(tok)
        note = '已写好整合包的自定义敌人预设，随机器里「自定义敌人」已经勾上（追忆 Boss 只在追忆之间换、按地区控制精英比例），不要取消它。'
    try:
        set_rand_settings(ctx, file, v)
    except Exception as e:
        note = '改随机器的设置时出错（' + _exc_message(e) + '），这次没帮你改：打开后请自己确认「合并其它MOD」是空的、游戏路径对。'
    return note


# ---------------------------------------------------------------- 自定义敌人预设的种子记录（presets\.dr_manual.preset）
def save_preset_record(ctx, RandDir, Seed, Nat):
    """时间（ToString('o')）、种子、自然精英比例三行，UTF-8 无 BOM、LF；写不了就算了"""
    f = os.path.join(RandDir, 'presets', '.dr_manual.preset')
    try:
        core.write_text(f, _now_o() + '\n' + str(int(Seed)) + '\n' + _ps_str(Nat) + '\n')
    except OSError:
        pass


def update_manual_preset(ctx):
    """重写自定义敌人预设（reroll\\enemypreset.py，新的预设种子；选项照 get_randomize_options），写好了记下种子返回 True；不限制 / 失败返回 False"""
    py = os.path.join(ctx.LauncherDir, 'python', 'python.exe')
    if not os.path.exists(py):
        return False
    o = get_randomize_options(ctx)
    seed = random.randint(1, 2147483646)
    from .pytool import child_env
    try:
        r = subprocess.run([py, '-X', 'utf8', os.path.join(ctx.LauncherDir, 'reroll', 'enemypreset.py'), '--randomizer-dir', ctx.RandomDir,
                            '--dll-dir', ctx.RandomDir, '--options', o.Options, '--seed', str(seed)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           creationflags=CREATE_NO_WINDOW, env=child_env())
        code = r.returncode
        out = _split_lines(r.stdout.decode('utf-8', 'replace'))
    except OSError:
        code = -1
        out = []
    if code != 0:
        return False
    nat = ''
    for l in out:
        m = re.match(r'^NAT:(.*)$', l, re.I)
        if m:
            nat = m.group(1).strip()
    save_preset_record(ctx, ctx.RandomDir, seed, nat)
    return True


# ---------------------------------------------------------------- 读随机器的日志
def read_shared_text(ctx, Path):
    """读随机器正在写 / 刚写完的日志（它一直开着这个文件；Python 的 open 本来就允许别人同时读写）；读不了返回 ''"""
    try:
        return _read_all_text(Path)
    except OSError:
        return ''


def get_latest_random(ctx):
    """launcher.ps1 的 Get-LatestRandom：最新 spoiler 日志 Rec(Log, Time, HasEnemy, HasItem, Merged)；没有返回 None。
    Merged = 以前的版本让随机器合并了可玩包（日志开头有 Checking other mod directory），要重新随机化"""
    log_dir = os.path.join(ctx.RandomDir, 'spoiler_logs')
    if not os.path.exists(log_dir):
        return None
    log = _newest_log(log_dir)
    if not log:
        return None
    head = _try_lines(log.FullName, 40)
    opt = next((l for l in head if re.match(r'^Options and seed:', l, re.I)), None)
    mod = next((l for l in head if re.match(r'^Checking other mod directory \S', l, re.I)), None)
    return Rec(Log=log.FullName, Time=log.LastWriteTime,
               HasEnemy=bool(opt and re.search(r'(^|\s)enemy(\s|$)', opt, re.I)),
               HasItem=bool(opt and re.search(r'(^|\s)item(\s|$)', opt, re.I)),
               Merged=bool(mod))


# ---------------------------------------------------------------- 高难度世界（Boss 模组）
def get_boss_fixed_ids(ctx):
    """settings.json 的 boss_mods 里开着、数据也在的模组要固定的 Boss 实体（mod.json 的 fixed），从小到大不重复；关着（mode off）就是 []"""
    ids = []
    try:
        s = _read_json(os.path.join(ctx.LauncherDir, 'reroll', 'settings.json'))
    except (OSError, ValueError):
        return ids
    bm = s.get('boss_mods') if isinstance(s, dict) else None
    if not bm or not isinstance(bm, dict) or ieq(_ps_str(bm.get('mode')), 'off') or not bm.get('mods') or not isinstance(bm.get('mods'), dict):
        return ids
    for name, val in bm['mods'].items():
        if name.startswith('_') or not _ps_eq_true(val):
            continue
        mj = os.path.join(ctx.LauncherDir, 'reroll', 'data', 'bossmods', name, 'mod.json')
        try:
            m = _read_json(mj)
        except (OSError, ValueError):
            continue
        fx = m.get('fixed') if isinstance(m, dict) else None
        for e in _ps_array(fx):
            if _ps_bool_scalar(e):
                ids.append(_to_long(e))
    # 有高难度世界时，「花蕾圣女」萝蜜娜也固定在原位（用户 2026-11-13「只在高难不随机」）
    if ids:
        ids.append(2044450800)
    return sorted(set(ids))


def _ps_eq_true(v):
    """$v -eq $true（右边按左边的类型转）：字符串不分大小写比 'True'，数字比 1，数组要每个都相等（空数组也算）"""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return ieq(v, 'True')
    if isinstance(v, (int, float)):
        return v == 1
    if isinstance(v, list):
        return all(_ps_eq_true(x) for x in v)
    return False


def _ps_bool_scalar(v):
    """if ($e)：$null、''、0、$false 为假"""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0
    if isinstance(v, str):
        return v != ''
    if isinstance(v, list):
        return core.ps_bool(v) and (len(v) > 1 or _ps_bool_scalar(v[0]))
    return True


def remove_rand_hi_dir(ctx):
    """删掉高难度世界：diste 要是目录联接，先单独删联接（不递归，不会碰 randomizer\\diste 里的东西），再删其余"""
    if not os.path.lexists(ctx.RandomHiDir):
        return
    j = os.path.join(ctx.RandomHiDir, 'diste')
    if os.path.lexists(j):
        os.rmdir(j)                 # Directory.Delete(j, $false)：联接 / 空目录删掉，有东西的真目录报错
    _remove_item(ctx.RandomHiDir)


def get_rand_hi_world(ctx, Need, HiDir=None, LoDir=None):
    """能用的高难度世界（hi_source.json 的内容，Rec）：None = 没有 / 过期（不是跟着现在这次随机化做的、或者固定的 Boss 不全）。
    Need = 这次要固定的实体（照 PowerShell：None 当作一个 0）；HiDir / LoDir 不给就是这个整合包的 randomizer_hi / randomizer"""
    HiDir = ctx.RandomHiDir if HiDir is None else HiDir
    LoDir = ctx.RandomDir if LoDir is None else LoDir
    f = os.path.join(HiDir, RandHiSource)
    if not os.path.exists(f) or not os.path.exists(os.path.join(HiDir, 'regulation.bin')):
        return None
    try:
        h = _read_json(f)
    except (OSError, ValueError):
        return None
    lo = _newest_log(os.path.join(LoDir, 'spoiler_logs'))
    lo_log = h.get('lo_log') if isinstance(h, dict) else None
    if not lo or not ieq(lo.Name, _ps_str(lo_log)):
        return None
    fx = h.get('fixed')
    have = [_to_long(x) for x in ([None] if fx is None else _ps_array(fx))]
    for e in _ps_array(Need):
        if _to_long(e) not in have:
            return None
    return _to_rec(h)


# ---------------------------------------------------------------- 更新后沿用旧版本的敌人随机结果
def get_pack_version(ctx, Pack):
    """整合包的版本（launcher\\version.txt 第一行，_Ver）；读不到 / 不是版本号返回 None"""
    try:
        lines = _gc_lines(os.path.join(Pack, 'launcher', 'version.txt'), 1)
    except OSError:
        return None
    return _ver((lines[0] if lines else '').strip())


def get_random_info(ctx, RandDir):
    """一个随机器文件夹里的随机结果 Rec(Time, Seed, HasEnemy, HasItem, Merged, Options, PresetSeed, PresetNat, Log)；
    没有 regulation.bin 或日志返回 None。日志旁边没有 .preset、选项带 customenemy（玩家自己开随机器随机化的）时，
    照 presets\\.dr_manual.preset（比日志旧的才算）补写 .preset"""
    if not os.path.exists(os.path.join(RandDir, 'regulation.bin')):
        return None
    log = _newest_log(os.path.join(RandDir, 'spoiler_logs'))
    if not log:
        return None
    head = _try_lines(log.FullName, 40)
    opt = next((l for l in head if re.match(r'^Options and seed:', l, re.I)), '')
    pf = re.sub(r'\.txt$', '.preset', log.FullName, flags=re.I)
    if not os.path.exists(pf) and re.search(r'(^|\s)customenemy(\s|$)', opt, re.I):
        mf = os.path.join(RandDir, 'presets', '.dr_manual.preset')
        m = _try_lines(mf, 3) if os.path.exists(mf) else []
        if len(m) >= 3:
            t = _parse_dt_ticks(m[0])
            if t is not None and _ticks(log.MtimeNs) >= t and m[1].strip():
                try:
                    core.write_text(pf, m[1].strip() + '\n' + m[2].strip() + '\n')
                except OSError:
                    pass
    pre = _try_lines(pf, 2) if os.path.exists(pf) else []
    sm = re.search(r'_log_(\d+)_', log.Name, re.I)
    return Rec(
        Time=log.LastWriteTime,
        Seed=sm.group(1) if sm else '',
        HasEnemy=bool(re.search(r'(^|\s)enemy(\s|$)', opt, re.I)),
        HasItem=bool(re.search(r'(^|\s)item(\s|$)', opt, re.I)),
        Merged=any(re.match(r'^Checking other mod directory \S', l, re.I) for l in head),
        Options=re.sub(r'^Options and seed:\s*', '', opt, count=1, flags=re.I).strip(),
        PresetSeed=pre[0].strip() if len(pre) >= 1 else '',
        PresetNat=pre[1].strip() if len(pre) >= 2 else '',
        Log=log.FullName,
    )


def save_pack_path(ctx):
    """启动游戏时把这个整合包的位置记进 packs.txt（最近 10 个，新的在前；UTF-8 无 BOM、CRLF）；出错就算了"""
    try:
        cur = os.path.abspath(ctx.Paly).rstrip('\\')
        old = _gc_lines(ctx.RandPacksFile) if os.path.exists(ctx.RandPacksFile) else []
        lst = [cur] + [x for x in (l.strip().rstrip('\\') for l in old) if x and not ieq(x, cur)]
        os.makedirs(ctx.RngDataDir, exist_ok=True)
        core.write_lines(ctx.RandPacksFile, lst[:10])
    except Exception:
        pass


def _is_pack(p):
    """整合包文件夹：有 launcher\\df.py（Python 的启动器，v0.10.14 起）或 launcher\\launcher.ps1（以前的版本）"""
    return os.path.exists(_jp(p, 'launcher\\df.py')) or os.path.exists(_jp(p, 'launcher\\launcher.ps1'))


def get_other_packs(ctx):
    """别的整合包文件夹（_is_pack）：先是 packs.txt 记的（最近用过的在前），再往下两层找：
    这个整合包上一级、上两级目录，桌面、下载、文档，游戏目录和它的 Game 文件夹"""
    cur = os.path.abspath(ctx.Paly).rstrip('\\')
    seen = set()
    out = []

    def add(p):
        k = p.lower()
        if p and not ieq(p, cur) and k not in seen and _is_pack(p):
            seen.add(k)
            out.append(p)
    for p in (_gc_lines(ctx.RandPacksFile) if os.path.exists(ctx.RandPacksFile) else []):
        if p and p.strip():
            add(p.strip().rstrip('\\'))
    up1 = _net_dirname(cur)
    up2 = _net_dirname(up1) if up1 else None
    prof = os.environ.get('USERPROFILE')
    bases = [up1, up2, win.known_folder('Desktop'), os.path.join(prof, 'Downloads') if prof else None, win.known_folder('MyDocuments')]
    # game_path.txt：PowerShell 这里没给编码（按 ANSI 读，中文路径会读错、这一处就找不到）；这里按 UTF-8 读，和写它的 Save-GameRoot 一致
    try:
        gl = _gc_lines(ctx.GamePathFile, 1)
        gr = (gl[0] if gl else '').strip()
        if gr:
            bases += [gr, os.path.join(gr, 'Game')]
    except OSError:
        pass
    done = set()
    for base in bases:
        if not base or not os.path.exists(base):
            continue
        bk = base.rstrip('\\').lower()
        if bk in done:
            continue
        done.add(bk)
        for d1 in _gci(base, Directory=True):
            add(d1.FullName)
            for d2 in _gci(d1.FullName, Directory=True):
                add(d2.FullName)
    return out


def get_old_random(ctx, Pack):
    """一个整合包文件夹里的随机结果能不能沿用：能就返回 Rec(Pack, Version, Time, Seed)，不能返回原因（字符串）"""
    if not _is_pack(Pack):
        return '这里不是暗黑重铸整合包的文件夹（里面没有 launcher 文件夹里的启动器）。'
    info = get_random_info(ctx, os.path.join(Pack, 'randomizer'))
    if not info:
        return '这个整合包里没有敌人随机结果（randomizer 文件夹里没有 regulation.bin 或 spoiler_logs）。'
    if info.Merged:
        return '这份随机结果是旧版本合并别的包做的，不能沿用。'
    if not (info.HasEnemy or info.HasItem):
        return '这份随机结果没开敌人随机。'
    ver = get_pack_version(ctx, Pack)
    if not ver or ver < RandCarryMinVersion:
        return '这个整合包版本太旧（' + ('v' + str(ver) if ver else '读不到版本') + '），要 v' + str(RandCarryMinVersion) + ' 以上。'
    return Rec(Pack=Pack, Version=ver, Time=info.Time, Seed=info.Seed)


def resolve_pack_dir(ctx, Dir):
    """玩家选的文件夹 → 整合包文件夹：可以是整合包本身、它里面的随便哪一层，或者包着它的那一层（往下两层里挑能沿用的、随机化最晚的）"""
    d = _full_path(Dir).rstrip('\\')
    p = d
    while p:
        if _is_pack(p):
            return p
        p = _net_dirname(p)
    cur = os.path.abspath(ctx.Paly).rstrip('\\')
    packs = []
    for c1 in _gci(d, Directory=True):
        for c in [c1] + _gci(c1.FullName, Directory=True):
            if not ieq(c.FullName, cur) and _is_pack(c.FullName):
                packs.append(c.FullName)
    best = _ps_sort([r for r in (get_old_random(ctx, x) for x in packs) if not isinstance(r, str)], lambda r: r.Time, Descending=True)
    if best:
        return best[0].Pack
    if packs:
        return packs[0]
    return d


def find_old_randoms(ctx):
    """旧版本整合包里能沿用的随机结果，随机化时间新的在前"""
    out = [get_old_random(ctx, p) for p in get_other_packs(ctx)]
    return _ps_sort([r for r in out if not isinstance(r, str)], lambda r: r.Time, Descending=True)


def test_need_old_random(ctx):
    """这个整合包需不需要沿用：还没有随机结果，或者现在的是合并别的包做的"""
    cur = get_random_info(ctx, ctx.RandomDir)
    return (not cur) or bool(cur.Merged)


def find_rand_settings_file_for(ctx, RandDir):
    """某个随机器文件夹对应的随机器设置文件（设置里额外 DLL 写的是它自己 dll 目录的完整路径）"""
    dll_dir = os.path.join(RandDir, 'dll').lower()
    for f in _user_configs(ctx):
        if dll_dir in _read_all_text(f).lower():
            return f
    return None


# ---------------------------------------------------------------- launcher.ps1 的动作
def invoke_rand_enemy_action(ctx):
    """一键重随敌人：用上次 / 默认的随机器设置、换新种子随机化一次，不启动游戏；返回成功与否"""
    write_head('一键重随敌人')
    rs = get_randomizer_status(ctx)
    if not rs.Ok:
        write_err(rs.Msg)
        return False
    if not rs.Tested:
        write_warn(get_randomizer_untested_msg(ctx))
    if win.find_pids('eldenring'):
        write_err('游戏还在运行，先退出游戏再重随敌人。')
        return False
    from .gamepath import resolve_game_root
    er_root = resolve_game_root(ctx)
    if not er_root:
        write_err('还没有设置游戏路径（随机器要读游戏文件）。先点「游戏路径」选一下。')
        return False
    if ctx.DryRun:
        o = get_randomize_options(ctx)
        host('  ' + o.From + '：' + o.Options)
        return True
    write_player('正在随机化敌人（约 1~5 分钟）：随机器窗口会自动操作、完成后自动关闭，这期间不要点它，也不要关掉它……')
    r = invoke_randomize_enemies(ctx, os.path.join(er_root, 'Game', 'eldenring.exe'))
    if r.Ok:
        write_ok(r.Msg)
        write_player('敌人随机化完成。')
        # 高难度世界（Boss 模组：整合了改版的 Boss 在「死亡」以上留在原位；没开 Boss 模组时什么都不做）
        if get_boss_fixed_ids(ctx):
            write_player('正在生成死亡以上难度的世界（随机器再跑一遍，约 1~5 分钟）……')
        h = invoke_randomize_hi_world(ctx, os.path.join(er_root, 'Game', 'eldenring.exe'))
        if h.Ok and h.Msg:
            write_ok(h.Msg)
            write_player('死亡以上难度的世界也生成好了。')
        elif not h.Ok:
            write_player_warn('死亡以上难度的世界没生成成功（正常的敌人随机不受影响；死亡以上难度时部分追忆 Boss 不在原位）：' + _ps_str(h.Msg))
        host('  现在点「一键启动 · 敌人随机」就能玩新的敌人配置。')
    else:
        write_err('一键重随敌人失败：' + _ps_str(r.Msg))
    return bool(r.Ok)


def invoke_rand_hi_action(ctx):
    """只补做高难度世界：按现在这次敌人随机的种子再跑一遍随机器，平常的世界不动"""
    write_head('补做高难度世界')
    rs = get_randomizer_status(ctx)
    if not rs.Ok:
        write_err(rs.Msg)
        return False
    if win.find_pids('eldenring'):
        write_err('游戏还在运行，先退出游戏。')
        return False
    from .gamepath import resolve_game_root
    er_root = resolve_game_root(ctx)
    if not er_root:
        write_err('还没有设置游戏路径。先点「游戏路径」选一下。')
        return False
    if not get_boss_fixed_ids(ctx):
        write_ok('没有开着的 Boss 模组，不用做高难度世界。')
        return True
    if ctx.DryRun:
        host('  [-DryRun] 不跑随机器。')
        return True
    write_player('正在生成死亡以上难度的世界（约 1~5 分钟）：随机器窗口会自动操作、完成后自动关闭，这期间不要点它，也不要关掉它……')
    h = invoke_randomize_hi_world(ctx, os.path.join(er_root, 'Game', 'eldenring.exe'))
    if h.Ok:
        write_ok(_ps_str(h.Msg))
        write_player('死亡以上难度的世界生成好了。')
    else:
        write_err('死亡以上难度的世界没生成成功：' + _ps_str(h.Msg))
    return bool(h.Ok)


def copy_rand_items(ctx, Src, Dst, Items):
    """把一个文件夹里随机器生成的东西复制到另一个文件夹（保留修改时间：沿用后按 spoiler 日志的时间核对）。出错返回原因，都成功返回 ''。
    以前用 robocopy（多线程、失败时说返回码）；这里用 copytree，失败的原因换成系统的错误说明"""
    for n in Items:
        s = os.path.join(Src, n)
        if not os.path.exists(s):
            continue
        if os.path.isdir(s):
            mb = round(sum(i.Length for i in _gci(s, File=True, Recurse=True)) / 1048576)
            host('  复制 ' + n + '（' + str(int(mb)) + ' MB）...')
            try:
                shutil.copytree(s, os.path.join(Dst, n), copy_function=_copy_tree_file, dirs_exist_ok=True)
            except shutil.Error as e:
                errs = e.args[0] if e.args and isinstance(e.args[0], list) else []
                why = errs[0][2] if errs and len(errs[0]) >= 3 else str(e)
                return '复制 ' + n + ' 失败（' + str(why) + '）'
            except OSError as e:
                return '复制 ' + n + ' 失败（' + _exc_message(e) + '）'
        else:
            _copy_force(s, os.path.join(Dst, os.path.basename(s)) if os.path.isdir(Dst) else Dst)
    return ''


def copy_old_rand_hi_world(ctx, Pack):
    """死亡以上难度的世界（randomizer_hi）跟着普通世界一起沿用；旧整合包里没有 / 不配套就不带。这里失败不影响已经沿用好的普通世界"""
    src = os.path.join(Pack, 'randomizer_hi')
    if get_rand_hi_world(ctx, [], src, os.path.join(Pack, 'randomizer')) is None:
        host('  旧版本没有配套的死亡以上难度世界，这部分不用沿用。')
        return
    try:
        remove_rand_hi_dir(ctx)
        os.makedirs(ctx.RandomHiDir, exist_ok=True)
        err = copy_rand_items(ctx, src, ctx.RandomHiDir, RandHiItems + ['spoiler_logs'])
        if not err:
            err = copy_rand_items(ctx, src, ctx.RandomHiDir, [RandHiSource])     # 记录文件最后复制：复制到一半中断时不会被当成完整的
        if err:
            raise _Thrown(err)
        if get_rand_hi_world(ctx, []) is None:
            raise _Thrown('复制完了却读不到这个世界')
        write_ok('死亡以上难度的世界也沿用过来了。')
    except Exception as e:
        write_warn('死亡以上难度的世界没沿用成（普通世界不受影响，选死亡以上难度启动时会问要不要重新生成）：' + _exc_message(e))
        try:
            remove_rand_hi_dir(ctx)
        except Exception:
            pass


def invoke_carry_random(ctx, From):
    """沿用旧版本的敌人随机结果：把旧整合包 randomizer\\ 里随机器生成的东西复制过来，旧文件夹不动。
    From 不给就用找到的最新一份；这个整合包已经有能用的随机结果就不覆盖。返回成功与否（图形界面靠退出码决定接不接着启动）"""
    write_head('沿用旧版本的敌人随机结果')
    rs = get_randomizer_status(ctx)
    if not rs.Ok:
        write_err(rs.Msg)
        return False
    if not test_need_old_random(ctx):
        cur = get_random_info(ctx, ctx.RandomDir)
        write_ok('这个整合包已经有敌人随机结果了（随机化于 ' + cur.Time.strftime('%Y-%m-%d %H:%M') + '），不用沿用。')
        return True
    if From:
        # 指定了文件夹（图形界面里自动找到的，或者玩家自己选的）：直接看那个文件夹
        pack = resolve_pack_dir(ctx, From)
        if ieq(pack, os.path.abspath(ctx.Paly).rstrip('\\')):
            write_err('选的是现在这个整合包自己：' + pack)
            return False
        c = get_old_random(ctx, pack)
        if isinstance(c, str):
            write_err('不能沿用 ' + pack + '：' + c)
            return False
    else:
        olds = find_old_randoms(ctx)
        c = olds[0] if olds else None
        if not c:
            write_err('没找到能沿用的旧版本随机结果（记下的整合包、旁边的文件夹、桌面 / 下载 / 文档、游戏目录、各盘根目录往下两层里都没有）')
            return False
    src = os.path.join(c.Pack, 'randomizer')
    host('  来源：' + c.Pack + '（整合包 ' + str(c.Version) + '，随机化于 ' + c.Time.strftime('%Y-%m-%d %H:%M:%S') +
         ('，种子 ' + c.Seed if c.Seed else '') + '）')
    # 先删掉这里残缺的 / 合并别的包做的结果（spoiler_logs 先删）
    for n in ['spoiler_logs'] + RandOutputItems:
        t = os.path.join(ctx.RandomDir, n)
        if os.path.lexists(t):
            _remove_item(t)
    t0 = time.monotonic()
    err = copy_rand_items(ctx, src, ctx.RandomDir, RandOutputItems)
    if err:
        write_err(err)
        return False
    now = get_random_info(ctx, ctx.RandomDir)
    if not now or now.Time != c.Time:
        write_err('复制完了却读不到随机结果（spoiler 日志或 regulation.bin 不对），这次没沿用成。')
        return False
    write_ok('已沿用旧版本的敌人随机结果（用时 ' + str(int(round(time.monotonic() - t0))) + ' 秒）：敌人和之前一样。')
    copy_old_rand_hi_world(ctx, c.Pack)
    return True


def invoke_randomizer(ctx):
    """打开随机器（玩家自己在随机器里随机化）：先写好它的设置（reset_rand_mod），再启动它，不等它"""
    rs = get_randomizer_status(ctx)
    if not rs.Ok:
        write_err(rs.Msg)
        return
    if not test_dot_net8(ctx):
        write_err(get_dot_net8_msg(ctx))
        return
    if win.find_pids('EldenRingRandomizer'):
        write_warn('随机器已经开着。')
        return
    write_head('打开随机器')
    host('  在随机器窗口里按下面做：')
    host('    1) 点「选择游戏exe启动文件」选好 eldenring.exe（第一次需要）')
    host('    2) 「合并其它MOD」留空（整合包直接用原版，不合并别的包；以前填过的已经自动清掉）')
    host('    3) 勾选「敌人随机」；「物品随机」可开可不开（开了会打乱法术祷告、道具、材料的位置和商人货架，原版装备整合包照样换掉）')
    host('       「自定义敌人」启动器已经勾好，不要取消（追忆 Boss 只在追忆之间换、按地区控制精英比例都靠它）')
    host('    4) 点「随机化敌人」（开了物品随机是「随机化物品与敌人」）；想要新的随机结果，点之前先勾上「重roll种子」（不勾会沿用上次的种子，敌人和上次一模一样）')
    host('       完成后关掉随机器（不要点它的「启动游戏」），回启动器点「一键启动（敌人随机）」')
    if ctx.DryRun:
        write_warn('[-DryRun] 不启动随机器。')
        return
    from .gamepath import resolve_game_root
    gr = resolve_game_root(ctx)
    note = reset_rand_mod(ctx, os.path.join(gr, 'Game', 'eldenring.exe') if gr else '')
    if note:
        host('  ' + note)
    _start_randomizer(ctx)


# ---------------------------------------------------------------- 操作随机器窗口（UI 自动化；迁移第 2 步，2026-11-18）
# 随机器是 Avalonia 程序，按钮、勾选框没有自己的窗口句柄，只能走 UIA（dfl\uia.py，ctypes 直接调 COM）。
# 用到的只有：按进程号找顶层窗口、按控件类型找子孙、读名字、点按钮、勾「重roll种子」、关窗口——和 randomize.ps1 一样。
def initialize_uia(ctx):
    """Initialize-Uia：建好 UI 自动化（一次运行建一次，放在 ctx.Uia）"""
    if getattr(ctx, 'Uia', None) is None:
        from .uia import Automation
        ctx.Uia = Automation()
    return ctx.Uia


def wait_rand_window(ctx, ProcId, Seconds=90):
    """等随机器的窗口出来：按进程号找顶层窗口，主按钮（随机化）也出来了才算加载完；等不到返回 None"""
    from . import uia
    a = initialize_uia(ctx)
    cond = a.process_cond(ProcId)
    for _ in range(Seconds * 2):
        try:
            w = a.root().find_first(uia.TreeScope_Children, cond)
            if w and find_rand_button(ctx, w):
                return w
        except OSError:
            pass
        time.sleep(0.5)
    return None


def find_rand_control(ctx, Win, Type, NamePattern):
    """窗口里第一个控件类型是 Type、名字匹配 NamePattern（不分大小写，-match）的控件；没有返回 None"""
    from . import uia
    a = initialize_uia(ctx)
    for e in Win.find_all(uia.TreeScope_Descendants, a.control_type_cond(Type)):
        if re.search(NamePattern, e.name, re.I):
            return e
    return None


def get_rand_button_names(ctx):
    """随机器主按钮的所有写法：它自己的界面文字（diste\\Messages\\*.json 里 EldenForm_randomize* 那几条的 text / english_text）。
    按钮文字随选项变（「随机化敌人」「以设定种子运行随机」……，界面语言不同也不同）；两个页面都没勾时的「???」（EldenForm_randomizeNothing）不算"""
    names = getattr(ctx, 'RandButtonNames', None)
    if names is not None:
        return names
    seen = {}
    for f in _gci(os.path.join(ctx.RandomDir, 'diste', 'Messages'), '*.json', File=True):
        try:
            j = json.loads(_read_all_text(f.FullName))
        except (OSError, ValueError):
            continue
        msgs = j.get('messages') if isinstance(j, dict) else None
        for m in msgs if isinstance(msgs, list) else ([msgs] if msgs else []):
            if not isinstance(m, dict):
                continue
            n = _ps_str(m.get('name'))
            if fnmatch.fnmatch(n.casefold(), 'eldenform_randomize*') and not ieq(n, 'EldenForm_randomizeNothing'):
                for t in (_ps_str(m.get('text')), _ps_str(m.get('english_text'))):
                    if t.strip():
                        seen[t.strip().casefold()] = t.strip()
    ctx.RandButtonNames = list(seen.values())
    return ctx.RandButtonNames


def find_rand_button(ctx, Win):
    """主按钮（随机化）：名字是上面任一种写法（不分大小写），或者老规则「随机化 / Randomize」开头"""
    from . import uia
    a = initialize_uia(ctx)
    names = {n.casefold() for n in get_rand_button_names(ctx)}
    for e in Win.find_all(uia.TreeScope_Descendants, a.control_type_cond('Button')):
        n = e.name.strip()
        if n and (n.casefold() in names or re.match(r'^(随机化|Randomize)', n, re.I)):
            return e
    return None


def close_rand_window(ctx, Proc):
    """正常关掉随机器（像点了 ×：它会把设置写回文件）；15 秒还没退出就强制结束"""
    from . import uia
    try:
        a = initialize_uia(ctx)
        for w in a.root().find_all(uia.TreeScope_Children, a.process_cond(Proc.pid)):
            try:
                w.close_window()
            except OSError:
                pass
    except OSError:
        pass
    try:
        Proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            Proc.kill()
        except OSError:
            pass


def new_rand_settings_file(ctx, Exe):
    """打开一次随机器再正常关掉，让它生成自己的设置文件（第一次用这份随机器时）；返回设置文件或 None"""
    t0 = time.time()
    p = _start_randomizer(ctx, Exe)
    w = wait_rand_window(ctx, p.pid)
    close_rand_window(ctx, p)
    if not w:
        return None
    found = []
    for d, _, files in os.walk(ctx.RandSettingsRoot):
        for n in files:
            if n.casefold() == 'user.config':
                f = os.path.join(d, n)
                try:
                    mt = os.stat(f).st_mtime
                except OSError:
                    continue
                if mt >= t0 - 2:
                    found.append((mt, f))
    if not found:
        return None
    f = max(found)[1]
    save_rand_settings_map(ctx, f)
    return f


_BUSY = re.compile(r'(中\.\.\.|中…|ing\.\.\.)$')


def wait_rand_result(ctx, Proc, Btn, Since, Minutes=15):
    """一次随机化的结果：'ok' / 'fail'（随机器报错，可换种子重试）/ 'timeout' / 'closed'。
    随机化时按钮文字变成「随机中...」，完成或出错后变回来；之后日志才写完。
    和以前的不同（2026-11-18 修）：以前日志里有「Basic placements」就算成功，可日志第 3 行的说明里就有这几个字，
    没看到「随机中」的那条路径会在随机器还在跑时提前判成功。现在要有「-- Basic placements」这一节、而且日志不再变了；
    没看到「随机中」时一直等到超时（以前只等 30 秒，随机器还在跑就当失败、换种子又点一次）"""
    log_dir = os.path.join(ctx.RandomDir, 'spoiler_logs')
    deadline = time.time() + Minutes * 60
    seen = False
    while time.time() < deadline:
        if Proc.poll() is not None:
            return 'closed'
        try:
            name = Btn.name
        except OSError:
            name = ''
        if _BUSY.search(name):
            seen = True
        elif seen or time.time() > Since + 30:          # 30 秒都没进入「随机中」也去看日志
            break
        time.sleep(2)
    if time.time() >= deadline:
        return 'timeout'
    tries = 15 if seen else None                         # 看到过「随机中」：日志最多再等 30 秒；没看到：等到超时
    last = None
    while tries is None or tries > 0:
        if tries is not None:
            tries -= 1
        elif time.time() >= deadline:
            return 'timeout'
        if Proc.poll() is not None and not seen:
            return 'closed'
        logs = [l for l in _gci(log_dir, '*_log_*.txt', File=True) if l.MtimeNs / 1e9 >= Since - 2]
        log = _newest(logs)
        if log:
            txt = read_shared_text(ctx, log.FullName)
            if re.search(r'(?m)^\s+at RandomizerCommon\.', txt):
                return 'fail'
            if re.search(r'(?m)^-- Basic placements', txt):
                try:
                    busy = bool(_BUSY.search(Btn.name))
                except OSError:
                    busy = False
                cur = (log.FullName, len(txt))
                if cur == last and not busy:              # 两次读到的一样：写完了
                    return 'ok'
                last = cur
        time.sleep(2)
    return 'fail'


def invoke_randomize_enemies(ctx, GameExe, Fixed=None):
    """一键重随敌人的整个流程（GameExe = eldenring.exe）。返回 Rec(Ok, Msg[, Options])。
    Fixed（联机随机码 / 高难度世界）：Rec(Options = 随机器的选项和种子（带 seed:N）, PresetSeed = 敌人预设的种子, Nat = 随机器自然精英比例
    [, From, FixedBosses])。给了就照它重随（不勾「重roll种子」，只试一次），和对方的结果一模一样；不给就是平常的一键重随（随机器自己换新种子）。
    敌人预设的种子和自然精英比例记在新 spoiler 日志旁边的 <日志名>.preset（两行）"""
    exe = os.path.join(ctx.RandomDir, 'EldenRingRandomizer.exe')
    if not os.path.exists(exe):
        return Rec(Ok=False, Msg='找不到随机器：' + exe)
    if win.find_pids('EldenRingRandomizer'):
        return Rec(Ok=False, Msg='随机器已经开着，先把它关掉再点一键重随敌人。')
    if not test_dot_net8(ctx):
        return Rec(Ok=False, Msg=get_dot_net8_msg(ctx))
    initialize_uia(ctx)
    # 先认准这份随机器的设置文件（认不出来就打开一次随机器），选项才是从这份随机器上次的设置里读的
    file = resolve_rand_settings_file(ctx, exe)
    if not file:
        return Rec(Ok=False, Msg='随机器没有生成设置文件（窗口没有正常打开？）。请先手动打开随机器一次再试。')
    if Fixed:
        tok = _split_ws(Fixed.Options)
        o = Rec(Options=' '.join(tok), From=Fixed.From or '联机随机码', HasItem=_icontains(tok, 'item'))
    else:
        o = get_randomize_options(ctx)
    seed = int(Fixed.PresetSeed) if Fixed else random.randint(1, 2147483646)
    nat = ''
    m = re.search(r'(?:^|\s)seed:(\d+)', o.Options, re.I) if Fixed else None
    want_seed = m.group(1) if m else ''
    # 前期位置少放精英：往随机器的自定义敌人预设里写指定（launcher\reroll\enemypreset.py），写好了就开「自定义敌人」
    py = os.path.join(ctx.LauncherDir, 'python', 'python.exe')
    if os.path.exists(py):
        pa = ['--randomizer-dir', ctx.RandomDir, '--dll-dir', ctx.RandomDir, '--options', o.Options, '--seed', str(seed)]
        # PowerShell 5.1 传空字符串参数时会把它丢掉（--nat 后面空着，enemypreset.py 报参数错、这次不写预设）；这里空的就不传 --nat
        if Fixed and Fixed.Nat:
            pa += ['--nat', str(Fixed.Nat)]
        if Fixed and Fixed.FixedBosses:
            pa += ['--fixed-bosses', str(Fixed.FixedBosses)]       # 高难度世界（invoke_randomize_hi_world）
        from .pytool import child_env
        try:
            r = subprocess.run([py, '-X', 'utf8', os.path.join(ctx.LauncherDir, 'reroll', 'enemypreset.py')] + pa,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               creationflags=CREATE_NO_WINDOW, env=child_env())
            code, out = r.returncode, _split_lines(r.stdout.decode('utf-8', 'replace'))
        except OSError as e:
            code, out = -1, [str(e)]
        # NAT: 那行是这次用的随机器自然精英比例，记进 .preset，不显示
        for l in out:
            mm = re.match(r'^NAT:(.*)$', l, re.I)
            if mm:
                nat = mm.group(1).strip()
            else:
                host(l)
        tok = _split_ws(o.Options)
        if code == 0:
            if not _icontains(tok, 'customenemy'):
                tok.append('customenemy')
            save_preset_record(ctx, ctx.RandomDir, seed, nat)
        o.Options = ' '.join(tok)
    _copy_force(file, file + '.dr.bak')
    # 种子交给随机器：勾「重roll种子」，它每次自己换新种子（设置里不写种子）；不合并别的包。联机随机码：选项里带着 seed:N，不勾，随机器就用这个种子
    set_rand_settings(ctx, file, {'Options': o.Options, 'Mod': '', 'Exe': GameExe})
    host('  设置：' + _ps_str(o.From) + (('（固定种子 ' + want_seed + '，敌人预设种子 ' + str(seed) + '）') if Fixed else '（勾「重roll种子」，每次换新种子）'))
    host('  选项：' + o.Options)
    if o.HasItem:
        host('  开着物品随机：法术祷告、道具、材料、锻造石的位置和商人货架也会打乱（原版武器防具护符整合包照样换成未鉴定物品）。')
    host('  [提示] 随机器窗口马上会打开并自动操作：这期间不要点随机器窗口，也不要关掉它，完成后会自动关闭。')
    p = _start_randomizer(ctx, exe)
    try:
        w = wait_rand_window(ctx, p.pid)
        if not w:
            return Rec(Ok=False, Msg='随机器窗口没有在 90 秒内打开。')
        for n_try in range(1, (1 if Fixed else 3) + 1):
            btn = find_rand_button(ctx, w)
            cb = find_rand_control(ctx, w, 'CheckBox', '(重roll种子|Reroll seed)')
            if cb:                                       # 平常每次（含失败重试）都勾「重roll种子」：随机器自己换新种子；联机随机码不勾（用码里的种子）
                want = 'Off' if Fixed else 'On'
                if cb.toggle_state() != want:
                    cb.toggle()
            elif Fixed:
                return Rec(Ok=False, Msg='在随机器窗口里找不到「重roll种子」，没法确认用的是联机随机码里的种子，这次没有重随。')
            else:
                host('  [提示] 在随机器窗口里找不到「重roll种子」，这次用随机器自己的种子设置。')
            if not btn:
                return Rec(Ok=False, Msg='在随机器窗口里找不到「随机化」按钮。')
            host('  第 %d 次：点「%s」，随机化大约要 2~5 分钟...' % (n_try, btn.name))
            t0 = time.time()
            btn.invoke()
            r = wait_rand_result(ctx, p, btn, t0)
            if r == 'ok':
                log = _newest_log(os.path.join(ctx.RandomDir, 'spoiler_logs'))
                mm = re.search(r'_log_(\d+)_', log.Name) if log else None
                used_seed = mm.group(1) if mm else ''
                if log:
                    try:
                        core.write_text(re.sub(r'\.txt$', '.preset', log.FullName, flags=re.I), str(seed) + '\n' + nat + '\n')
                    except OSError:
                        pass
                if Fixed and used_seed != want_seed:
                    return Rec(Ok=False, Msg='随机器用的种子（' + used_seed + '）和联机随机码里的（' + want_seed + '）不一样，随机结果和对方对不上。')
                used = ('，种子 ' + used_seed) if used_seed else ''
                return Rec(Ok=True, Msg='敌人已重新随机化（' + _ps_str(o.From) + used + '）', Options=o.Options)
            if r != 'fail':
                return Rec(Ok=False, Msg='随机化超过 15 分钟没有完成。' if r == 'timeout' else '随机器窗口被关掉了。')
            if Fixed:
                return Rec(Ok=False, Msg='随机器用联机随机码里的种子失败了（日志里是报错）。确认两边的整合包版本一样。')
            host('  [提示] 这个种子随机器自己失败了（日志里是报错），换个种子再试...')
        return Rec(Ok=False, Msg='换了 3 个种子都失败了，请点「打开随机器」手动看看是哪个选项有问题。')
    finally:
        close_rand_window(ctx, p)


def _move_item(src, dst):
    """Move-Item：目标已经有了就出错（shutil.move 会挪进已有的文件夹里）"""
    if os.path.lexists(dst):
        raise FileExistsError('无法创建「' + dst + '」，因为它已经存在。')
    os.rename(src, dst)


def invoke_randomize_hi_world(ctx, GameExe):
    """一键重随敌人成功之后：同一个种子再跑一遍高难度世界（整合了改版的 Boss 固定在原位，输出搬到 randomizer_hi\\）。
    返回 Rec(Ok, Msg)（没开 Boss 模组时 Ok、Msg 空）。搬之前先把正常那一套挪到 randomizer\\.dr_lo，跑完不管成没成功都搬回来；
    随机器的设置、自定义敌人预设也还原成正常那一遍的"""
    fixed = get_boss_fixed_ids(ctx)
    remove_rand_hi_dir(ctx)                               # 旧的高难度世界跟着旧的随机化，作废
    if not fixed:
        return Rec(Ok=True, Msg='')
    log_dir = os.path.join(ctx.RandomDir, 'spoiler_logs')
    log = _newest_log(log_dir)
    m = re.search(r'_log_(\d+)_', log.Name) if log else None
    if not m:
        return Rec(Ok=False, Msg='找不到刚才随机化的日志')
    seed = m.group(1)
    opt_line = next((l for l in _try_lines(log.FullName, 5) if re.match(r'^Options and seed:', l, re.I)), None)
    if not opt_line:
        return Rec(Ok=False, Msg='刚才随机化的日志里没有选项')
    opt = ' '.join(t for t in _split_ws(re.sub(r'^Options and seed:\s*', '', opt_line, flags=re.I)) if not re.match(r'^seed2?:', t, re.I))
    pf = re.sub(r'\.txt$', '.preset', log.FullName, flags=re.I)
    pl = _try_lines(pf, None) if os.path.exists(pf) else []
    if not pl or not pl[0]:
        return Rec(Ok=False, Msg='刚才随机化没有记下敌人预设的种子')
    file = find_rand_settings_file(ctx)
    preset = os.path.join(ctx.RandomDir, 'presets', 'CustomEnemy.txt')
    lo = os.path.join(ctx.RandomDir, '.dr_lo')
    host('')
    host('  高难度世界：同一个种子（' + seed + '）再随机化一遍，这一遍 ' + str(len(fixed)) + ' 个 Boss 留在原位（整合了改版的、萝蜜娜；只在「死亡」以上用）...')
    if file:
        _copy_force(file, file + '.hi.bak')
    if os.path.exists(preset):
        _copy_force(preset, preset + '.hi.bak')
    ok = False
    try:
        if os.path.exists(lo):
            _remove_item(lo)
        os.makedirs(lo)
        for n in RandHiItems:
            p = os.path.join(ctx.RandomDir, n)
            if os.path.exists(p):
                _move_item(p, os.path.join(lo, n))
        fx = Rec(Options=opt + ' seed:' + seed, PresetSeed=pl[0], Nat=pl[1] if len(pl) > 1 else '',
                 From='高难度世界（同一个种子）', FixedBosses=','.join(str(x) for x in fixed))
        r = invoke_randomize_enemies(ctx, GameExe, fx)
        if not r.Ok:
            return Rec(Ok=False, Msg=r.Msg)
        hi_log = _newest_log(log_dir)
        os.makedirs(os.path.join(ctx.RandomHiDir, 'spoiler_logs'), exist_ok=True)
        for n in RandHiItems:
            p = os.path.join(ctx.RandomDir, n)
            if os.path.exists(p):
                _move_item(p, os.path.join(ctx.RandomHiDir, n))
        for p in (hi_log.FullName, re.sub(r'\.txt$', '.preset', hi_log.FullName, flags=re.I)):
            if os.path.exists(p):
                _move_item(p, os.path.join(ctx.RandomHiDir, 'spoiler_logs', os.path.basename(p)))
        info = {'lo_log': log.Name, 'hi_log': hi_log.Name, 'seed': seed, 'fixed': fixed, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        core.write_text(os.path.join(ctx.RandomHiDir, RandHiSource), json.dumps(info, ensure_ascii=False, indent=4).replace('\n', '\r\n'))
        ok = True
        return Rec(Ok=True, Msg='高难度世界也随机化好了（' + str(len(fixed)) + ' 个 Boss 留在原位）')
    finally:
        if not ok:
            # 没成功：随机器这一遍的半截输出清掉，它的日志改名（免得被当成最近一次随机化），高难度世界不要
            for n in RandHiItems:
                p = os.path.join(ctx.RandomDir, n)
                if os.path.exists(p) and os.path.exists(os.path.join(lo, n)):
                    _remove_item(p)
            for l in _gci(log_dir, '*_log_*.txt', File=True):
                if l.MtimeNs > log.MtimeNs:
                    try:
                        os.rename(l.FullName, l.FullName + '.hi_failed')
                    except OSError:
                        pass
            if os.path.exists(ctx.RandomHiDir):
                try:
                    remove_rand_hi_dir(ctx)
                except OSError:
                    pass
        for n in RandHiItems:
            src = os.path.join(lo, n)
            if os.path.exists(src):
                _move_item(src, os.path.join(ctx.RandomDir, n))
        if os.path.isdir(lo) and not os.listdir(lo):
            os.rmdir(lo)
        if file and os.path.exists(file + '.hi.bak'):
            os.replace(file + '.hi.bak', file)
        if os.path.exists(preset + '.hi.bak'):
            os.replace(preset + '.hi.bak', preset)
