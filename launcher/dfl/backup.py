# -*- coding: utf-8 -*-
"""启动前自动备份 / 恢复（backup.ps1，外加 launcher.ps1 的 Invoke-LaunchBackup、Invoke-OnceReset）。
我们自己的东西都在存档文件夹 %APPDATA%\\EldenRing 下的 DarkReforged\\ 里（游戏自己的 <SteamID>\\ER0000.rng、GraphicsConfig.xml 不动）：
  DarkReforged\\角色记录\\     DLL 记的装备配方（items_<格子>.txt）、锁定名单、免费许愿次数，一次性重随的结果（once.json）
      角色记录\\联机\\            联机（Seamless Co-op）存档 ER0000.rngcoop（以前叫 ER0000.rng.co2）的角色的同样这些
  DarkReforged\\启动前备份\\   每次启动游戏前存一份：<时间>_启动前\\<SteamID>\\ER0000.rng、<时间>_启动前\\角色记录\\…、backup_info.json
  DarkReforged\\旧文件\\       不再使用的：RNG Lands 时代的 RNGLands_*、重置前的一次性重随记录等
  DarkReforged\\version.txt   上次用的整合包版本（更新提醒）
2026-10-29 以前这些都散在 EldenRing 根目录（DarkReforged_*.txt、DarkReforged_启动前备份\\ 等）：move_rng_legacy_files 搬进来。
和上一份内容完全相同（存档、记录都没变）就不重复存；启动前备份只留最近 RngBackupKeep 份（一份约 30 MB）。

和 PowerShell 版的不同：backup.ps1 被 dot-source 时会顺手跑一次 Move-RngLegacyFiles；这里 import 时什么都不做，
要整理旧文件的地方自己调 move_rng_legacy_files(ctx)（invoke_launch_backup、restore_rng_backup、invoke_once_reset 本来就调）。

文件对象：Get-ChildItem / Get-Item 返回的 FileInfo 在这里是 FileItem，属性名照抄（FullName、Name、Directory.Name、DirectoryName、
Length、LastWriteTime、LastWriteTimeUtc、Extension、PSIsContainer），调用的地方（诊断包、图形界面）照原样用。"""
import ctypes
import datetime
import decimal
import json
import os
import re
import shutil
import stat
from ctypes import wintypes as W

from . import win
from .core import Rec, host, ieq, write_head, write_ok, write_warn, write_lines

RngBackupKeep = 10
# 现在的 Dark Reforged 存档：<SteamID>\ER0000.rng，联机的 <SteamID>\ER0000.rngcoop（.bak 是游戏自己留的上一份，不备份）。
# 联机存档以前叫 ER0000.rng.co2（2026-11-17 改名）：旧备份里的照样认，恢复时换成新名字
RngCoopSave = 'ER0000.rngcoop'
RngCoopSaveOld = 'ER0000.rng.co2'
RngSaveNames = ['ER0000.rng', RngCoopSave]


def _now():
    """Get-Date（测试时换成固定的时间，两边的备份文件夹名、记录行才对得上）"""
    return datetime.datetime.now()


# ---------------------------------------------------------------- PowerShell 文件操作的替身（私有）
_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_TICKS_1970 = 621355968000000000

_k32 = ctypes.WinDLL('kernel32', use_last_error=True)
_k32.CopyFileW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.BOOL]
_k32.CopyFileW.restype = W.BOOL


def _local_dt(ns):
    """st_mtime_ns → 本地时间（LastWriteTime；整数秒换算，微秒单独补上，不经过浮点）"""
    return datetime.datetime.fromtimestamp(ns // 10 ** 9) + datetime.timedelta(microseconds=(ns // 1000) % 10 ** 6)


def _ext(name):
    """[IO.Path]::GetExtension：最后一个点起；没有点、或者点在最后，是空的（和 os.path.splitext 不一样：'a.' → ''，'.txt' → '.txt'）"""
    i = name.rfind('.')
    if i < 0 or i == len(name) - 1:
        return ''
    return name[i:]


class FileItem:
    """FileInfo / DirectoryInfo 的替身：建的时候读一次属性（和 Get-ChildItem 给的一样是快照）"""

    def __init__(self, path, st=None):
        self.FullName = path
        self.Name = os.path.basename(path)
        if st is None:
            st = os.lstat(path)
        self._attrs = getattr(st, 'st_file_attributes', 0)
        self.PSIsContainer = bool(self._attrs & _FILE_ATTRIBUTE_DIRECTORY) if self._attrs else stat.S_ISDIR(st.st_mode)
        self.Length = 0 if self.PSIsContainer else st.st_size
        self._mtime_ns = st.st_mtime_ns
        self.LastWriteTime = _local_dt(st.st_mtime_ns)
        self.LastWriteTimeUtcTicks = st.st_mtime_ns // 100 + _TICKS_1970
        self.LastWriteTimeUtc = datetime.datetime(1970, 1, 1) + datetime.timedelta(microseconds=st.st_mtime_ns // 1000)
        self.Extension = _ext(self.Name)
        self.DirectoryName = os.path.dirname(path)
        self.Directory = Rec(Name=os.path.basename(self.DirectoryName), FullName=self.DirectoryName)

    @property
    def Hidden(self):
        return bool(self._attrs & _FILE_ATTRIBUTE_HIDDEN)

    def __repr__(self):
        return 'FileItem(%r)' % self.FullName


def _get_item(path):
    """Get-Item -LiteralPath：隐藏的文件不给 -Force 是「找不到项」（launcher.ps1 里 $ErrorActionPreference = 'Stop'，就是异常）"""
    it = FileItem(os.path.abspath(path))
    if it.Hidden:
        raise FileNotFoundError('找不到项 ' + path + '。')
    return it


def _wild(pattern):
    """-Filter 的通配符（* ?，不分大小写）→ 正则"""
    return re.compile(''.join('.*' if c == '*' else '.' if c == '?' else re.escape(c) for c in pattern) + r'\Z', re.I | re.S)


def _gci(path, files=True, dirs=True, force=False, pattern=None, recurse=False, depth=None):
    """Get-ChildItem -LiteralPath <path> -ErrorAction SilentlyContinue。
    顺序和 PowerShell 一样：每个文件夹里先列子文件夹、再列文件（各自按文件系统给的顺序），-Recurse 时列完这一层再按顺序进子文件夹；
    不给 force 不列隐藏的（系统属性的照列），也不进隐藏的子文件夹；不进链接 / 联接点。depth = -Depth（0 = 只看这一层）"""
    rx = _wild(pattern) if pattern else None
    out = []

    def walk(d, lvl):
        try:
            with os.scandir(d) as it:
                ents = list(it)
        except OSError:
            return
        ds, fs = [], []
        for e in ents:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            a = getattr(st, 'st_file_attributes', 0)
            if not force and a & _FILE_ATTRIBUTE_HIDDEN:
                continue
            item = FileItem(os.path.join(d, e.name), st)
            (ds if item.PSIsContainer else fs).append(item)
        for it in ds:
            if dirs and (rx is None or rx.match(it.Name)):
                out.append(it)
        for it in fs:
            if files and (rx is None or rx.match(it.Name)):
                out.append(it)
        if recurse and (depth is None or lvl < depth):
            for it in ds:
                if it._attrs & _FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                walk(it.FullName, lvl + 1)
    if path:
        walk(os.path.abspath(path), 0)                 # FullName 和 .NET 一样是规范化过的完整路径
    return out


def _clear_readonly(path):
    try:
        st = os.lstat(path)
        if getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_READONLY:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _copy_item(src, dst, force=False):
    """Copy-Item -LiteralPath <文件> -Destination <dst>：dst 是已有的文件夹就复制进去；已有的文件照样覆盖（只读的要 -Force）。
    用 CopyFileW（和 .NET 的 File.Copy 一样：修改时间、属性跟着复制）"""
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    if _k32.CopyFileW(src, dst, False):
        return
    err = ctypes.get_last_error()
    if force and err == 5 and os.path.isfile(dst):           # ERROR_ACCESS_DENIED：只读的目标，-Force 先去掉只读
        _clear_readonly(dst)
        if _k32.CopyFileW(src, dst, False):
            return
        err = ctypes.get_last_error()
    raise OSError(0, ctypes.FormatError(err).strip(), dst, err)


def _move_item(src, dst, force=False):
    """Move-Item -LiteralPath <src> -Destination <dst>：dst 是已有的文件夹 → 挪进去（dst\\<名字>）；
    目标已经有了 → 出错（文件给了 -Force 就覆盖）。和 shutil.move 不一样的地方都照 PowerShell"""
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    if os.path.lexists(dst):
        if force and not os.path.isdir(dst) and not os.path.isdir(src):
            _clear_readonly(dst)
            os.remove(dst)
        else:
            raise FileExistsError(183, 'Cannot create a file when that file already exists.', dst)
    try:
        os.rename(src, dst)
    except OSError as e:
        if getattr(e, 'winerror', None) != 17:               # ERROR_NOT_SAME_DEVICE：跨盘才复制再删
            raise
        shutil.move(src, dst)


def _remove_file(path):
    """Remove-Item -LiteralPath <文件> -Force（只读的也删）"""
    _clear_readonly(path)
    os.remove(path)


def _remove_tree_quiet(path):
    """Remove-Item -Recurse -Force -ErrorAction SilentlyContinue：只读的也删，删不掉的跳过接着删别的"""
    def onexc(func, p, exc):
        if isinstance(exc, PermissionError):
            try:
                os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
                func(p)
            except OSError:
                pass
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, onexc=onexc)
        else:
            _remove_file(path)
    except OSError:
        pass


def _rmdir_quiet(path):
    """Remove-Item -LiteralPath <空文件夹> -Force -ErrorAction SilentlyContinue"""
    try:
        _clear_readonly(path)
        os.rmdir(path)
    except OSError:
        pass


def _net_read_lines(path):
    """[IO.File]::ReadAllLines(path, UTF8)：认 BOM（UTF-8 / UTF-16 / UTF-32），坏字节换成 U+FFFD 不报错；只按 \\r\\n、\\r、\\n 分行"""
    with open(path, 'rb') as f:
        raw = f.read()
    return _net_split_lines(_net_decode(raw))


def _net_decode(raw):
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw[3:].decode('utf-8', 'replace')
    if raw.startswith(b'\xff\xfe\x00\x00'):
        return raw[4:].decode('utf-32-le', 'replace')
    if raw.startswith(b'\xff\xfe'):
        return raw[2:].decode('utf-16-le', 'replace')
    if raw.startswith(b'\xfe\xff'):
        return raw[2:].decode('utf-16-be', 'replace')
    if raw.startswith(b'\x00\x00\xfe\xff'):
        return raw[4:].decode('utf-32-be', 'replace')
    return raw.decode('utf-8', 'replace')


def _net_split_lines(text):
    if not text:
        return []
    parts = re.split(r'\r\n|\r|\n', text)
    if text.endswith(('\r', '\n')):
        parts.pop()
    return parts


def _json_str(s):
    """ConvertTo-Json（PowerShell 5.1）怎么转义字符串：\\ " 控制字符，还有 < > ' & 写成 \\u003c 这类；中文原样"""
    out = []
    for c in s:
        o = ord(c)
        if c == '"':
            out.append('\\"')
        elif c == '\\':
            out.append('\\\\')
        elif c == '\b':
            out.append('\\b')
        elif c == '\f':
            out.append('\\f')
        elif c == '\n':
            out.append('\\n')
        elif c == '\r':
            out.append('\\r')
        elif c == '\t':
            out.append('\\t')
        elif o < 0x20 or c in '<>\'&':
            out.append('\\u%04x' % o)
        else:
            out.append(c)
    return '"' + ''.join(out) + '"'


def _ps_json_flat(d):
    """[ordered]@{ 键 = 字符串 } | ConvertTo-Json 的原样排版（CRLF、缩进 4 格、冒号后两个空格），备份信息文件逐字节和以前一样"""
    body = ',\r\n'.join('    ' + _json_str(k) + ':  ' + _json_str(v) for k, v in d.items())
    return '{\r\n' + body + '\r\n}'


_DT_ISO = re.compile(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d{1,7}))?)?)?(Z|[+-]\d{2}:\d{2})?')
_DT_US = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})(?: (\d{1,2}):(\d{2})(?::(\d{2}))?)?')
_JSON_WS = ' \t\r\n'


def _ps_datetime(v):
    """[datetime]$info.time：PowerShell 按固定区域（InvariantCulture）解析（带 Z / +08:00 的换成本地时间）；数字 = Ticks；
    $null、空串、认不出来都是异常"""
    if isinstance(v, int) and not isinstance(v, bool):
        return datetime.datetime(1, 1, 1) + datetime.timedelta(microseconds=v // 10)
    s = v if isinstance(v, str) else None
    if s is not None:
        s = s.strip()
        try:
            m = _DT_ISO.fullmatch(s)
            if m:
                y, mo, d, h, mi, se, fr, tz = m.groups()
                t = datetime.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(se or 0), int((fr or '0').ljust(7, '0')[:6]))
                if tz:
                    off = datetime.timedelta(0) if tz == 'Z' else (1 if tz[0] == '+' else -1) * datetime.timedelta(hours=int(tz[1:3]), minutes=int(tz[4:6]))
                    t = t.replace(tzinfo=datetime.timezone(off)).astimezone().replace(tzinfo=None)
                return t
            m = _DT_US.fullmatch(s)
            if m:
                mo, d, y, h, mi, se = m.groups()
                return datetime.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(se or 0))
        except (ValueError, OverflowError):
            pass
    raise ValueError('无法将值“%s”转换为类型“System.DateTime”。错误:“该字符串未被识别为有效的 DateTime。”' % ('' if v is None else v))


def _ps_str(v):
    """[string]$x：$null → ''，真假 → True / False，数组用空格连起来，对象是 @{a=1; b=2}"""
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, list):
        return ' '.join(_ps_str(x) for x in v)
    if isinstance(v, dict):
        return '@{' + '; '.join(k + '=' + _ps_str(x) for k, x in v.items()) + '}'
    if isinstance(v, decimal.Decimal):
        return format(v, 'f')              # ConvertFrom-Json 把带小数点的数读成 decimal：1.0 还是 "1.0"
    return str(v)


def _json_obj(pairs):
    """ConvertFrom-Json：同一个对象里只差大小写的两个键是错误（PowerShell 的属性不分大小写）；完全一样的键后面的算"""
    seen = {}
    for k, _ in pairs:
        f = k.casefold()
        if f in seen and seen[f] != k:
            raise ValueError('无法转换 JSON 字符串，因为从该字符串转换的字典包含重复的键“%s”和“%s”。' % (seen[f], k))
        seen[f] = k
    return dict(pairs)


def _jget(obj, key):
    """$info.tag：属性名不分大小写；不是对象读出来是 $null"""
    if not isinstance(obj, dict):
        return None
    if key in obj:
        return obj[key]
    for k, v in obj.items():
        if k.casefold() == key.casefold():
            return v
    return None


def _net_sort(items, cmp):
    """PowerShell 5.1 Sort-Object 的排序法（不稳定，相等的谁在前也照它）：见 win.ps_sort"""
    return win.ps_sort(items, cmp)


def _ps_sort_by(items, key):
    """Sort-Object <属性>（字符串，按区域规则、不分大小写；排序法和 PowerShell 5.1 一样，相等的谁在前也一样）"""
    return _net_sort(items, lambda x, y: win.culture_cmp(key(x), key(y)))


# ---------------------------------------------------------------- 存档操作记录
def add_rng_ops_log(ctx, Text):
    """存档操作记录 launcher\\logs\\save_ops.txt（留最近 300 行，诊断包会带上）：每次备份 / 恢复 / 删旧备份 / 整理旧文件记一行。
    图形界面（备份、恢复按钮）和启动器（启动前备份）都会写；玩家说「恢复以后进度没了」之类的时候看这个"""
    try:
        os.makedirs(os.path.dirname(ctx.RngOpsLog), exist_ok=True)
        old = _net_read_lines(ctx.RngOpsLog) if os.path.exists(ctx.RngOpsLog) else []
        line = _now().strftime('%Y-%m-%d %H:%M:%S') + '  ' + Text
        write_lines(ctx.RngOpsLog, old[-299:] + [line], bom=True)
    except Exception:
        pass


# ---------------------------------------------------------------- 存档、角色记录
def test_rng_coop_save_name(Name):
    return any(ieq(Name, n) for n in (RngCoopSave, RngCoopSaveOld))


def move_coop_save_name(ctx):
    """联机存档换名字（联机启动前调）：每个 SteamID 文件夹里还没有 ER0000.rngcoop、却有旧的 ER0000.rng.co2（或以前套出来的
    ER0000.rng.rng.co2 这类）时，挑修改时间最新的那份（真正在玩的；套出来的是复制的，修改时间和原来的一样）复制成 ER0000.rngcoop，
    它的 .bak 也一起。旧文件都不删。返回复制了几个"""
    n = 0
    rx = re.compile(r'^ER0000(\.rng)+\.co2$', re.I)
    for d in _gci(ctx.RngSaveRoot, files=False):
        new = os.path.join(d.FullName, RngCoopSave)
        if os.path.exists(new):
            continue
        old = [f for f in _gci(d.FullName, dirs=False) if rx.search(f.Name)]
        old = _net_sort(old, lambda x, y: -((x._mtime_ns > y._mtime_ns) - (x._mtime_ns < y._mtime_ns)))   # Sort-Object LastWriteTime -Descending
        if not old:
            continue
        src = old[0]
        try:
            _copy_item(src.FullName, new)
            if os.path.exists(src.FullName + '.bak'):
                try:
                    _copy_item(src.FullName + '.bak', new + '.bak')
                except OSError:
                    pass
            n += 1
            add_rng_ops_log(ctx, '联机存档改名：' + d.Name + '\\' + src.Name + '（' + src.LastWriteTime.strftime('%Y-%m-%d %H:%M') + '）复制成 ' + RngCoopSave +
                            ('；同一文件夹里另有 ' + str(len(old) - 1) + ' 个旧联机存档（' + '、'.join(f.Name for f in old[1:]) + '），没动' if len(old) > 1 else ''))
            host('  联机存档：' + d.Name + '\\' + src.Name + ' 复制成 ' + RngCoopSave + '（联机存档换了名字，旧文件留着没删）')
        except Exception as e:
            host('  联机存档换名字失败：' + src.FullName + ' → ' + new + '：' + _msg(e))
    return n


def _msg(e):
    """异常的说明（$_.Exception.Message 的近似：.NET 的原话这里没有，用 Windows / Python 给的）"""
    if isinstance(e, OSError) and e.strerror:
        return e.strerror
    return str(e)


def get_rng_save_files(ctx):
    """现在的存档：每个 SteamID 文件夹里的 ER0000.rng、ER0000.rngcoop。
    隐藏的存档也算（Get-Item -Force 的意思）：以前 Get-Item 不带 -Force，存档文件被设成隐藏时直接出错，启动前备份跟着失败
    （2026-11-18 移植时修）"""
    out = []
    for d in _gci(ctx.RngSaveRoot, files=False):
        for n in RngSaveNames:
            f = os.path.join(d.FullName, n)
            if os.path.exists(f):
                out.append(FileItem(os.path.abspath(f)))
    return out


def get_rng_saves_in(ctx, Dir):
    """一份备份（或任意文件夹）里的存档文件：单机的、联机的都算（含旧名字 ER0000.rng.co2）"""
    names = RngSaveNames + [RngCoopSaveOld]
    return [f for f in _gci(Dir, dirs=False, recurse=True) if any(ieq(f.Name, n) for n in names)]


def get_rng_record_files(ctx, Backup=''):
    """角色记录：不给 Backup 是现在的（角色记录\\ 和 角色记录\\联机\\ 下的 .txt / .json；写到一半的 .tmp 不算）；
    给一份备份的目录：新的在 <备份>\\角色记录\\（联机的在里面的 联机\\），2026-10-29 以前的直接在备份里（DarkReforged_*.txt，版本记录不算；DarkReforged_once.json）"""
    d0 = os.path.join(Backup, '角色记录') if Backup else ctx.RngRecordDir
    if Backup and not os.path.exists(d0):
        return [f for f in _gci(Backup, dirs=False, pattern='DarkReforged_*')
                if (ieq(f.Extension, '.txt') and not ieq(f.Name, 'DarkReforged_version.txt')) or ieq(f.Name, 'DarkReforged_once.json')]
    out = []
    for d in (d0, os.path.join(d0, '联机')):
        out += [f for f in _gci(d, dirs=False) if ieq(f.Extension, '.txt') or ieq(f.Extension, '.json')]
    return out


def get_rng_record_name(File):
    """记录在 角色记录\\ 里的相对路径（联机的是 联机\\<名字>；以前的备份里带 DarkReforged_ 前缀）"""
    n = re.sub(r'^DarkReforged_', '', File.Name, flags=re.I)
    if ieq(File.Directory.Name, '联机'):
        return '联机\\' + n
    return n


def copy_rng_record(File, Dir):
    """把记录复制到 <Dir>\\<相对路径>（联机的要先建 联机\\）"""
    to = os.path.join(Dir, get_rng_record_name(File))
    os.makedirs(os.path.dirname(to), exist_ok=True)
    _copy_item(File.FullName, to, force=True)


def get_rng_file_sig(Files):
    """文件的指纹（大小 + 修改时间）：判断和上一份备份是不是一样。格式一字不差（FullName|Length|LastWriteTimeUtc.Ticks，; 连起来），
    不然以前版本存的备份全被当成不一样的"""
    return ';'.join(f.FullName + '|' + str(f.Length) + '|' + str(f.LastWriteTimeUtcTicks)
                    for f in _ps_sort_by(list(Files), lambda f: f.FullName))


def move_rng_item(ctx, Item, To):
    """把 Item（文件或文件夹）挪到 To；To 已经有了：文件留修改时间新的那份，另一份放旧文件\\（名字后面加时间）；文件夹挪进旧文件\\"""
    os.makedirs(os.path.dirname(To), exist_ok=True)
    if not os.path.exists(To):
        _move_item(Item.FullName, To)
        return
    stamp = _now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(ctx.RngOldDir, exist_ok=True)
    cur = _get_item(To)
    if not Item.PSIsContainer and Item.LastWriteTimeUtcTicks > cur.LastWriteTimeUtcTicks:
        _move_item(cur.FullName, os.path.join(ctx.RngOldDir, cur.Name + '.' + stamp))
        _move_item(Item.FullName, To)
    else:
        _move_item(Item.FullName, os.path.join(ctx.RngOldDir, Item.Name + '.' + stamp))


def move_rng_legacy_files(ctx):
    """旧版散在 EldenRing 根目录的东西搬进 DarkReforged\\。游戏开着时不搬（DLL 可能正在写）；搬不动的（被占用）跳过，下次再搬。返回搬了几项。
    PowerShell 版在 dot-source backup.ps1 时自动跑一次；这里不自动跑，调用的地方自己调"""
    if win.find_pids('eldenring'):
        return 0
    if not os.path.exists(ctx.RngSaveRoot):
        return 0
    n = 0
    # DarkReforged_<名字>：版本记录 → version.txt；.txt / .json → 角色记录\<名字>；别的（.before_reset、.tmp……）→ 旧文件\
    for f in _gci(ctx.RngSaveRoot, dirs=False, pattern='DarkReforged_*'):
        name = get_rng_record_name(f)
        to = os.path.join(ctx.RngOldDir, name)
        if ieq(name, 'version.txt'):
            to = ctx.RngVersionFile
        elif ieq(f.Extension, '.txt') or ieq(f.Extension, '.json'):
            to = os.path.join(ctx.RngRecordDir, name)
        try:
            move_rng_item(ctx, f, to)
            n += 1
        except Exception:
            pass
    # 启动前备份：每一份挪进 启动前备份\，挪空了删掉旧文件夹
    old_bk = os.path.join(ctx.RngSaveRoot, 'DarkReforged_启动前备份')
    if os.path.exists(old_bk):
        for d in _gci(old_bk, force=True):
            try:
                move_rng_item(ctx, d, os.path.join(ctx.RngBackupDir, d.Name))
                n += 1
            except Exception:
                pass
        if len(_gci(old_bk, force=True)) == 0:
            _rmdir_quiet(old_bk)
    # RNG Lands 时代的（RNGLands_*，现在不用）：原样挪进 旧文件\RNG Lands\
    for x in _gci(ctx.RngSaveRoot, pattern='RNGLands_*', force=True):
        try:
            move_rng_item(ctx, x, os.path.join(ctx.RngOldDir, 'RNG Lands', x.Name))
            n += 1
        except Exception:
            pass
    if n:
        add_rng_ops_log(ctx, '整理旧版的存档文件：搬进 ' + ctx.RngDataDir + ' ' + str(n) + ' 项')
    return n


# ---------------------------------------------------------------- 备份 / 恢复
def new_rng_backup(ctx, Tag, Mode=''):
    """Tag：启动前 / 恢复前；返回备份目录（没有可备份的返回 None，和上一份相同时返回上一份）"""
    what = Tag + ('，' + Mode if Mode else '')
    saves = get_rng_save_files(ctx)
    records = get_rng_record_files(ctx)
    if len(saves) + len(records) == 0:
        add_rng_ops_log(ctx, '备份（' + what + '）：没有存档和角色记录，不用存')
        return None
    sig = get_rng_file_sig(saves + records)
    last = next((b for b in get_rng_backups(ctx) if ieq(b.Tag, Tag)), None)
    if last and ieq(last.Sig, sig):
        add_rng_ops_log(ctx, '备份（' + what + '）：和上一份一样，没再存（' + os.path.basename(last.Dir) + '）')
        return last.Dir
    stamp = _now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(ctx.RngBackupDir, stamp + '_' + Tag)
    k = 2
    while os.path.exists(dst):                                        # 同一秒里存了两份
        dst = os.path.join(ctx.RngBackupDir, stamp + '_' + Tag + '_' + str(k))
        k += 1
    os.makedirs(dst, exist_ok=True)
    for f in saves:
        to = os.path.join(dst, f.Directory.Name)
        os.makedirs(to, exist_ok=True)
        _copy_item(f.FullName, to, force=True)
    if records:
        to = os.path.join(dst, '角色记录')
        os.makedirs(to, exist_ok=True)
        for f in records:
            copy_rng_record(f, to)
    info = {'tag': Tag, 'time': _now().strftime('%Y-%m-%d %H:%M:%S'), 'mode': Mode, 'sig': sig}
    with open(os.path.join(dst, 'backup_info.json'), 'wb') as fh:              # UTF-8 无 BOM，排版和 ConvertTo-Json 一样
        fh.write(_ps_json_flat(info).encode('utf-8'))
    add_rng_ops_log(ctx, '备份（' + what + '）：存档 ' + str(len(saves)) + ' 个、角色记录 ' + str(len(records)) + ' 个 → ' + os.path.basename(dst))
    # 每种只留最近几份（恢复前的备份不会把启动前的挤掉）
    keep = RngBackupKeep if ieq(Tag, '启动前') else 5
    for old in [b for b in get_rng_backups(ctx) if ieq(b.Tag, Tag)][keep:]:
        _remove_tree_quiet(old.Dir)
        add_rng_ops_log(ctx, '删掉旧备份（每种只留最近 ' + str(keep) + ' 份）：' + os.path.basename(old.Dir))
    return dst


def _backup_cmp(a, b):
    """Sort-Object Time, Dir：先比时间，再按区域规则比路径"""
    if a.Time != b.Time:
        return -1 if a.Time < b.Time else 1
    return win.culture_cmp(a.Dir, b.Dir)


def get_rng_backups(ctx, ManualDir=''):
    """启动前备份 + 恢复前备份 + 「存档备份」按钮存的（ManualDir），新的在前：
    [Rec(Dir, Tag, Time（datetime）, Mode, Sig, Records（几个记录）, Saves（几个存档）)]"""
    lst = []
    for d in _gci(ctx.RngBackupDir, files=False):
        info_file = os.path.join(d.FullName, 'backup_info.json')
        if not os.path.exists(info_file):                                  # 没写完的
            continue
        try:
            with open(info_file, 'rb') as fh:
                text = _net_decode(fh.read())
            info = json.loads(text, object_pairs_hook=_json_obj, parse_float=decimal.Decimal) if text.strip(_JSON_WS) else None
            # 有意的不同：PowerShell 版读到空的 / 只有 null 的 backup_info.json 不出错（ConvertFrom-Json 给 $null），
            # 往下 [datetime]$null 才抛，整个列表（连带启动前备份、恢复）都失败；时间认不出来也一样。这里当没写完的跳过
            t = _ps_datetime(_jget(info, 'time'))
        except (OSError, ValueError):
            continue
        lst.append(Rec(Dir=d.FullName, Tag=_ps_str(_jget(info, 'tag')), Time=t,
                       Mode=_ps_str(_jget(info, 'mode')), Sig=_ps_str(_jget(info, 'sig')),
                       Records=len(get_rng_record_files(ctx, d.FullName)), Saves=len(get_rng_saves_in(ctx, d.FullName))))
    if ManualDir:
        for d in _gci(ManualDir, files=False):
            rc = len(get_rng_record_files(ctx, d.FullName))
            sv = len(get_rng_saves_in(ctx, d.FullName))
            if sv == 0:
                continue
            lst.append(Rec(Dir=d.FullName, Tag='存档备份', Time=d.LastWriteTime, Mode='', Sig='', Records=rc, Saves=sv))
    return _net_sort(lst, lambda a, b: -_backup_cmp(a, b))                 # Sort-Object Time, Dir -Descending


def restore_rng_backup(ctx, Backup):
    """恢复一份备份（get_rng_backups 给的一项）：先把现在的存档和记录存成「恢复前」备份（恢复错了还能换回来），再复制回去。
    角色记录整套换成备份里的：备份之后才有的记录删掉（已经存进「恢复前」），免得和换回去的存档对不上。
    备份里没有联机存档、也没有联机记录（加联机以前的备份）时，现在的联机存档和 联机\\ 记录不动（不然联机角色的装备记录会被删光）。
    返回恢复了什么（给玩家看的几段文字）"""
    move_rng_legacy_files(ctx)
    pre = new_rng_backup(ctx, '恢复前')
    done = []
    saves = get_rng_saves_in(ctx, Backup.Dir)
    for f in saves:
        name = f.Name
        if ieq(name, RngCoopSaveOld):
            # 改名以前的备份：联机存档换成新名字；同一份备份里已经有新名字的就不用旧的
            if os.path.exists(os.path.join(f.DirectoryName, RngCoopSave)):
                continue
            name = RngCoopSave
        to = os.path.join(ctx.RngSaveRoot, f.Directory.Name)
        os.makedirs(to, exist_ok=True)
        _copy_item(f.FullName, os.path.join(to, name), force=True)
        done.append(('联机存档 ' if test_rng_coop_save_name(f.Name) else '存档 ') + f.Directory.Name)
    coop = any(test_rng_coop_save_name(s.Name) for s in saves) or os.path.exists(os.path.join(Backup.Dir, '角色记录\\联机'))
    keep = {}                                                             # 和 PowerShell 的 @{} 一样不分大小写
    os.makedirs(ctx.RngRecordDir, exist_ok=True)
    for f in get_rng_record_files(ctx, Backup.Dir):
        copy_rng_record(f, ctx.RngRecordDir)
        keep[get_rng_record_name(f).casefold()] = True
    for f in get_rng_record_files(ctx):
        name = get_rng_record_name(f)
        if name.casefold().startswith('联机\\'.casefold()) and not coop:
            continue
        if name.casefold() not in keep:
            _remove_file(f.FullName)
    done.append('角色记录 ' + str(len(keep)) + ' 个')
    add_rng_ops_log(ctx, '恢复：' + '、'.join(done) + '，来自 ' + Backup.Dir + '（' + Backup.Tag + ' ' + Backup.Time.strftime('%Y-%m-%d %H:%M:%S') + '）；' +
                    '恢复前的存档和记录存在 ' + (os.path.basename(pre) if pre else '（没有，原来就是空的）'))
    return done


# ---------------------------------------------------------------- launcher.ps1 里的两个
def invoke_launch_backup(ctx, Mode):
    """启动游戏前自动备份存档 + 角色记录；图形界面「恢复存档」默认恢复最近一份"""
    try:
        n = move_rng_legacy_files(ctx)
        if n:
            host('  整理存档文件夹：' + str(n) + ' 项搬进 ' + ctx.RngDataDir)
    except Exception as e:
        write_warn('整理存档文件夹失败（下次启动再试）：' + _msg(e))
    try:
        d = new_rng_backup(ctx, '启动前', Mode)
        if d:
            host('  启动前备份：' + d)
    except Exception as e:
        write_warn('启动前备份失败（不影响游戏，但出问题时没法恢复到这次启动前）：' + _msg(e))


def invoke_once_reset(ctx):
    """一次性重随：骨灰的位置、开局装备和遗物只在第一次启动时抽一次，记在 角色记录\\once.json；
    删掉这个文件，下次启动就会重新抽一次（之后又固定）。原文件挪进 DarkReforged\\旧文件（once_<时间>.json.before_reset）留着"""
    write_head('一键重随物品')
    move_rng_legacy_files(ctx)
    state = os.path.join(ctx.RngRecordDir, 'once.json')
    if not os.path.exists(state):
        write_ok('还没有记录，下次启动时本来就会抽。')
        return
    os.makedirs(ctx.RngOldDir, exist_ok=True)
    kept = os.path.join(ctx.RngOldDir, 'once_' + _now().strftime('%Y%m%d_%H%M%S') + '.json.before_reset')
    _move_item(state, kept, force=True)
    write_ok('记录已清除。下次启动时骨灰的位置、开局装备和遗物会重新抽一次，之后再固定下来；只对之后新建的角色生效（已有角色的装备和还没捡到的骨灰不变）。')
    host('  原来的记录：' + kept)
