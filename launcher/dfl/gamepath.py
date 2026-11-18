# -*- coding: utf-8 -*-
"""游戏路径（launcher.ps1「游戏路径」一节）：game_path.txt、自动检测（Steam 注册表 + libraryfolders.vdf、整合包附近、各盘的常见位置）、
选择框、命令行菜单；还有游戏的 Steam 语言（Get-SteamGameLanguage）和游戏版本核对（Get-GameExeVersion / Test-GameVersion）。

游戏路径不写死：优先读 launcher\\game_path.txt（用户选择 / 自动检测后保存），其次自动检测，仍找不到就让玩家选。
注册表只读（winreg，KEY_READ）。

几个和 PowerShell 一样的小工具也放在这里（launch.py 也用）：
- ls：Get-ChildItem -LiteralPath [-Filter] [-File / -Directory]，-Filter 交给系统的 FindFirstFile 匹配（和 PowerShell 一样带 8.3 短名的老规矩），
  不带 -Force 不列隐藏的；顺序是文件系统给的。
- read_all_text：[IO.File]::ReadAllText（认 BOM，坏字节换成 U+FFFD）。
- ps_lines：Get-Content 的分行（\\r\\n、\\n、\\r 都算换行，最后的空行不算）。"""
import ctypes
import os
import re
import sys
from ctypes import wintypes as W

from . import core, win
from .core import host, write_err, write_ok, write_player_warn, write_warn

# 整合包认得的游戏版本（eldenring.exe 的文件版本 → 游戏里的版本号）。整合包的功能模块按版本找游戏里的位置，别的版本上大半不工作：
# 2026-11-17 玩家诊断包是非 Steam 版 2.7.0.0（比 2.7.1.0 早一版），装备、商店、飞行、物品锁的模块都没工作，玩家只看到东西不对、老崩溃。
# 支持了新版本在这里加（键 = 文件版本）
SupportedGameVersions = {'2.7.1.0': '1.17.1', '2.7.2.0': '1.17.2'}

# ---------------------------------------------------------------- 和 PowerShell 一样的小工具
_k32 = ctypes.WinDLL('kernel32', use_last_error=True)
_k32.FindFirstFileExW.restype = W.HANDLE
_k32.FindFirstFileExW.argtypes = [W.LPCWSTR, ctypes.c_int, ctypes.POINTER(W.WIN32_FIND_DATAW), ctypes.c_int, ctypes.c_void_p, W.DWORD]
_k32.FindNextFileW.argtypes = [W.HANDLE, ctypes.POINTER(W.WIN32_FIND_DATAW)]
_k32.FindClose.argtypes = [W.HANDLE]
_k32.GetLogicalDrives.restype = W.DWORD
_k32.GetDriveTypeW.argtypes = [W.LPCWSTR]
_k32.GetDriveTypeW.restype = W.UINT
_k32.SetThreadErrorMode.argtypes = [W.DWORD, ctypes.POINTER(W.DWORD)]
_INVALID = ctypes.c_void_p(-1).value
_HIDDEN = 0x2
_DIRECTORY = 0x10


def ls(path, pattern='*', kind=None, force=False):
    """Get-ChildItem -LiteralPath path [-Filter pattern] [-File（kind='file'）/ -Directory（kind='dir'）] [-Force] -ErrorAction SilentlyContinue：
    [(名字, 完整路径)]。列不了（不存在、没权限）返回 []"""
    out = []
    if not path:
        return out
    base = path if path.endswith(('\\', '/')) else path + '\\'
    data = W.WIN32_FIND_DATAW()
    try:
        h = _k32.FindFirstFileExW(base + pattern, 0, ctypes.byref(data), 0, None, 0)     # FindExInfoStandard, FindExSearchNameMatch
    except (ValueError, TypeError):
        return out
    if not h or h == _INVALID:
        return out
    try:
        while True:
            name = data.cFileName
            a = data.dwFileAttributes
            if name not in ('.', '..') and (force or not a & _HIDDEN):
                is_dir = bool(a & _DIRECTORY)
                if kind is None or (kind == 'dir') == is_dir:
                    out.append((name, base + name))
            if not _k32.FindNextFileW(h, ctypes.byref(data)):
                break
    finally:
        _k32.FindClose(h)
    return out


def read_all_text(path):
    """[IO.File]::ReadAllText：UTF-8（带不带 BOM 都行），也认 UTF-16 / UTF-32 的 BOM；坏字节换成 U+FFFD，不报错"""
    with open(path, 'rb') as f:
        raw = f.read()
    for bom, enc in ((b'\xef\xbb\xbf', 'utf-8'), (b'\xff\xfe\x00\x00', 'utf-32-le'), (b'\x00\x00\xfe\xff', 'utf-32-be'),
                     (b'\xff\xfe', 'utf-16-le'), (b'\xfe\xff', 'utf-16-be')):
        if raw.startswith(bom):
            return raw[len(bom):].decode(enc, 'replace')
    return raw.decode('utf-8', 'replace')


def ps_lines(text):
    """Get-Content 的分行：\\r\\n、\\n、\\r 都算换行；文件最后的换行后面不算一行"""
    if not text:
        return []
    parts = re.split(r'\r\n|\r|\n', text)
    if parts and parts[-1] == '':
        parts.pop()
    return parts


def read_lines_utf8(path, count=None):
    """Get-Content -LiteralPath path [-TotalCount count] -Encoding UTF8：读不了返回 None（-ErrorAction SilentlyContinue 时什么都没有）"""
    try:
        lines = ps_lines(read_all_text(path))
    except OSError:
        return None
    return lines[:count] if count is not None else lines


def net_dirname(p):
    """[IO.Path]::GetDirectoryName：根目录（C:\\、C:、\\\\server\\share）返回 None"""
    if p is None:
        return None
    d = os.path.dirname(p)
    return None if d == p else d


def split_parent(p):
    """Split-Path -Parent：根目录的上一级是空串"""
    if not p:
        return ''
    d = os.path.dirname(p)
    return '' if d == p else d


def _upper_key(s):
    """StringComparer.OrdinalIgnoreCase 的键：逐个字符转大写（变长的不转，和 .NET 一样不会把 ß 当成 SS）"""
    return ''.join(c.upper() if len(c.upper()) == 1 else c for c in s)


def ordinal_starts_ci(s, prefix):
    """.StartsWith(prefix, [StringComparison]::OrdinalIgnoreCase)"""
    return len(s) >= len(prefix) and _upper_key(s[:len(prefix)]) == _upper_key(prefix)


# ---------------------------------------------------------------- 游戏路径
def test_normalize_game_root(Path):
    """Test-NormalizeGameRoot：给的是游戏目录（ELDEN RING）、它的 Game 文件夹或 eldenring.exe 都行，返回游戏目录（ELDEN RING 那一层）；不像返回 None。
    PowerShell 里全用 .NET 判断（5.1 的 Join-Path / Split-Path 遇到不存在的盘符会抛异常）；这里出错一律当不像"""
    if not Path:
        return None
    p = str(Path).strip()
    p = p.strip('"').strip()
    if not p:
        return None
    try:
        p = os.path.abspath(p).rstrip('\\')
        if os.path.basename(p).casefold() == 'eldenring.exe':
            if not os.path.isfile(p):
                return None
            p = net_dirname(net_dirname(p))
            if p is None:
                return None
        if os.path.isfile(os.path.join(p, 'eldenring.exe')):
            return net_dirname(p)
        if os.path.isfile(os.path.join(p, 'Game\\eldenring.exe')):
            return p
    except (OSError, ValueError, TypeError):
        pass
    return None


def get_saved_game_root(ctx):
    """Get-SavedGameRoot：launcher\\game_path.txt 第一行（再核对一遍）；没有 / 不对返回 None"""
    if not os.path.exists(ctx.GamePathFile):
        return None
    lines = read_lines_utf8(ctx.GamePathFile, 1)
    if not lines or not lines[0]:
        return None
    return test_normalize_game_root(lines[0])


def save_game_root(ctx, Root):
    """Save-GameRoot：写 game_path.txt（UTF-8 无 BOM、CRLF）"""
    core.write_text(ctx.GamePathFile, Root + '\r\n')
    ctx.CacheGameRoot = Root
    write_ok('已保存游戏路径：' + Root)


def get_unique_paths(Paths):
    """Get-UniquePaths：路径去重，不分大小写，留第一次出现的写法（去掉结尾的 \\）。注册表里的 SteamPath 是小写加正斜杠（c:/program files (x86)/steam），
    游戏库列表和按盘扫到的是 C:\\Program Files (x86)\\Steam：以前分大小写去重，同一个游戏算成两个候选，「只有一个候选才自动记住」就不成立，
    游戏装在 C 盘 Steam 默认位置的玩家每次都要手选（2026-11-16 查出来）"""
    seen = set()
    out = []
    if isinstance(Paths, str):
        Paths = [Paths]
    for p in list(Paths or []):
        if not p:
            continue
        k = str(p).rstrip('\\')
        u = _upper_key(k)
        if u not in seen:
            seen.add(u)
            out.append(k)
    return out


def _reg_value(root, sub, name):
    """Get-ItemProperty -Path <键> -Name <名字>：读不到返回 None（只读）"""
    import winreg
    try:
        with winreg.OpenKey(root, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            v, t = winreg.QueryValueEx(k, name)
    except OSError:
        return None
    if t == winreg.REG_EXPAND_SZ and isinstance(v, str):
        v = winreg.ExpandEnvironmentStrings(v)
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v) if v else None
    return v if isinstance(v, str) else None


def get_steam_path():
    """Steam 装在哪：HKCU\\Software\\Valve\\Steam 的 SteamPath，没有再看 HKLM\\SOFTWARE\\WOW6432Node\\Valve\\Steam 的 InstallPath"""
    import winreg
    p = _reg_value(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath')
    if not p:
        p = _reg_value(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')
    return p or None


def find_steam_game_roots(ctx=None):
    """Find-SteamGameRoots：Steam 的游戏库（libraryfolders.vdf 的 path）和 Steam 自己的目录里找 ELDEN RING"""
    roots = []
    steam = get_steam_path()
    libs = []
    if steam:
        vdf = os.path.join(steam, 'steamapps\\libraryfolders.vdf')
        if os.path.exists(vdf):
            try:
                txt = read_all_text(vdf)
                for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
                    libs.append(m.group(1).replace('\\\\', '\\'))
            except OSError:
                pass
        libs.append(steam)                     # 放在库列表后面：库列表里的写法大小写正常，去重时留它
    for lib in libs:
        for sub in ('steamapps\\common\\ELDEN RING', 'steamapps\\common\\ELDEN RING\\Game'):
            r = test_normalize_game_root(os.path.join(lib, sub))
            if r:
                roots.append(r)
    return get_unique_paths(roots)


def find_nearby_game_roots(ctx):
    """Find-NearbyGameRoots：整合包直接解压在游戏文件夹里（Game 或 ELDEN RING 那一层，2026-11-16 有两个玩家这样放）：整合包目录自己和往上几层；
    再从 launcher 往上 4 层，每层找名字像游戏的文件夹（和它下一层）"""
    roots = []
    up = ctx.Paly
    i = 0
    while i < 3 and up:
        r = test_normalize_game_root(up)
        if r:
            roots.append(r)
        up = net_dirname(up)
        i += 1
    d = ctx.LauncherDir
    for _ in range(4):
        if not d:
            break
        for pat in ('ELDEN RING*', '*ELDEN*', '*elden*', '*Ring*'):
            for _n, full in ls(d, pat, 'dir')[:40]:
                r = test_normalize_game_root(full)
                if r:
                    roots.append(r)
                for _n2, full2 in ls(full, '*', 'dir')[:40]:
                    r2 = test_normalize_game_root(full2)
                    if r2:
                        roots.append(r2)
        d = split_parent(d)
    return get_unique_paths(roots)


def _drive_ready(root):
    """DriveInfo.IsReady（.NET Framework 就是看根目录在不在；没放盘的光驱、读卡器不弹「没有磁盘」）"""
    old = W.DWORD()
    try:
        _k32.SetThreadErrorMode(0x0001, ctypes.byref(old))           # SEM_FAILCRITICALERRORS
    except (AttributeError, OSError):
        pass
    try:
        return os.path.isdir(root)
    finally:
        try:
            _k32.SetThreadErrorMode(old.value, None)
        except (AttributeError, OSError):
            pass


def get_fixed_drive_roots(ctx=None):
    """Get-FixedDriveRoots：要扫的盘：本机硬盘、移动硬盘、网络盘（光驱这类没放盘的跳过），C:\\ 这样的写法"""
    out = []
    try:
        mask = _k32.GetLogicalDrives()
        for i in range(26):
            if not mask & (1 << i):
                continue
            root = chr(65 + i) + ':\\'
            if _k32.GetDriveTypeW(root) not in (2, 3, 4):                # DRIVE_REMOVABLE / FIXED / REMOTE
                continue
            if _drive_ready(root):
                out.append(root)
    except OSError:
        pass
    return out


COMMON_RELS = (
    'Program Files (x86)\\Steam\\steamapps\\common\\ELDEN RING',
    'Program Files\\Steam\\steamapps\\common\\ELDEN RING',
    'SteamLibrary\\steamapps\\common\\ELDEN RING',
    'Steam\\steamapps\\common\\ELDEN RING',
    'Steam Library\\steamapps\\common\\ELDEN RING',
    'SteamLibrary2\\steamapps\\common\\ELDEN RING',
    'SteamGames\\steamapps\\common\\ELDEN RING',
    'Games\\Steam\\steamapps\\common\\ELDEN RING',
    'Games\\SteamLibrary\\steamapps\\common\\ELDEN RING',
    'Games\\ELDEN RING',
    'Game\\ELDEN RING',
)
COMMON_SKIP = ('Windows', 'System Volume Information', '$Recycle.Bin', '$WinREAgent', 'Recovery', 'PerfLogs', 'ProgramData')


def find_common_game_roots(ctx=None):
    """Find-CommonGameRoots：每个盘里 Steam 正版的默认位置（用户 2026-11-16「自动扫描所有盘下 steam 正版默认的路径」）：Steam 装在默认位置、
    在别的盘建的游戏库（Steam 默认叫 SteamLibrary），再加上盘根下每个文件夹当游戏库看一遍（X:\\随便什么名字\\steamapps\\common\\ELDEN RING，
    比如 E:\\SteamGames）和 X:\\随便什么名字\\Steam\\…。只看固定的几层，不整盘搜"""
    roots = []
    skip = {s.casefold() for s in COMMON_SKIP}
    for d in get_fixed_drive_roots():
        for rel in COMMON_RELS:
            r = test_normalize_game_root(os.path.join(d, rel))
            if r:
                roots.append(r)
        tops = [full for _n, full in ls(d, '*', 'dir', force=True)][:300]      # [IO.Directory]::GetDirectories：隐藏的也算
        for t in tops:
            if os.path.basename(t).casefold() in skip:
                continue
            for sub in ('steamapps\\common\\ELDEN RING', 'Steam\\steamapps\\common\\ELDEN RING'):
                r = test_normalize_game_root(os.path.join(t, sub))
                if r:
                    roots.append(r)
    return get_unique_paths(roots)


def get_game_candidates(ctx):
    """Get-GameCandidates"""
    return get_unique_paths(find_steam_game_roots() + find_nearby_game_roots(ctx) + find_common_game_roots())


def select_game_candidate(ctx):
    """Select-GameCandidate：自动检测到的游戏里挑一个：只有一个就是它；有好几个时，整合包解压在其中一个里面的用那个，
    否则 Steam 游戏库里登记的只有一个就用它；还分不出来返回 None（让玩家在「游戏路径」里自己选）"""
    cands = get_game_candidates(ctx)
    if len(cands) <= 1:
        return cands[0] if cands else None
    me = ctx.Paly.rstrip('\\') + '\\'
    inside = [c for c in cands if ordinal_starts_ci(me, c + '\\')]
    if len(inside) == 1:
        return inside[0]
    steam = find_steam_game_roots()
    if len(steam) == 1:
        return steam[0]
    return None


def resolve_game_root(ctx, Refresh=False):
    """Resolve-GameRoot：记下的 → 自动检测（挑得出来就记住）；都没有返回 None。结果缓存在 ctx.CacheGameRoot"""
    if not Refresh and getattr(ctx, 'CacheGameRoot', None):
        return ctx.CacheGameRoot
    saved = get_saved_game_root(ctx)
    if saved:
        ctx.CacheGameRoot = saved
        return saved
    pick = select_game_candidate(ctx)
    if pick:
        ctx.CacheGameRoot = pick
        try:
            core.write_text(ctx.GamePathFile, pick + '\r\n')
        except OSError:
            pass
        write_ok('自动检测到游戏路径并已记住：' + pick)
        return pick
    return None


def pick_folder_dialog(ctx, Title):
    """Pick-FolderDialog：文件夹选择框（win.pick_folder），默认选在现在的游戏目录；取消 / 出错返回 None"""
    try:
        cur = resolve_game_root(ctx)
        r = win.pick_folder(Title, cur or None)
        return r or None
    except Exception:
        return None


def pick_exe_dialog(ctx, Title):
    """Pick-ExeDialog：选 eldenring.exe（win.pick_file），默认打开现在的游戏的 Game 文件夹；取消 / 出错返回 None"""
    try:
        cur = resolve_game_root(ctx)
        r = win.pick_file(Title, 'eldenring.exe|eldenring.exe|所有文件|*.*', os.path.join(cur, 'Game') if cur else None)
        return r or None
    except Exception:
        return None


def _read_host(prompt):
    """Read-Host：提示后面加「: 」，读一行；读到结尾（标准输入关了 / 没有）返回 None"""
    try:
        sys.stdout.write(prompt + ': ')
        sys.stdout.flush()
    except (OSError, ValueError, AttributeError):
        pass
    try:
        line = sys.stdin.readline() if sys.stdin else ''
    except (OSError, ValueError):
        line = ''
    if not line:
        return None
    return line.rstrip('\r\n')


def _try_int32(s):
    """[int]::TryParse：只认 ASCII 数字（可带正负号），超出 Int32 返回 None"""
    if not re.fullmatch(r'[+-]?[0-9]+', s):
        return None
    v = int(s)
    return v if -2 ** 31 <= v < 2 ** 31 else None


def set_game_root_interactive(ctx):
    """Set-GameRootInteractive：命令行菜单（从标准输入读，读到结尾当取消）。选好返回 True，取消返回 False。
    PowerShell 先 Clear-Host 清屏：这里不清（输出给图形界面 / 日志，清屏没有意义）"""
    while True:
        cur = get_saved_game_root(ctx)
        cands = get_game_candidates(ctx)
        host('==============================================================')
        host('   设置 Elden Ring 游戏路径（只需选一次，会记住）')
        host('==============================================================')
        if cur:
            host('  当前：' + cur)
        else:
            resolved = resolve_game_root(ctx)
            if resolved:
                host('  当前：' + resolved)
            else:
                host('  当前：未设置')
        host('')
        if cands:
            host('  自动检测到的候选：')
            for i, c in enumerate(cands):
                host('   [%d] %s' % (i + 1, c))
        else:
            host('  自动检测：没有找到（可手动浏览）')
        host('')
        host('   输入序号 = 使用该候选')
        host('   [F] 浏览文件夹（选游戏的 Game 文件夹，例如 C:\\Program Files (x86)\\Steam\\steamapps\\common\\ELDEN RING\\Game）')
        host('   [E] 直接选择 eldenring.exe')
        host('   [A] 重新自动检测')
        host('   [Q] 取消')
        host('==============================================================')
        sel = _read_host('请选择')
        if sel is None:
            return False
        sel = sel.strip()
        if sel == '':
            continue
        if sel in ('q', 'Q'):
            return False
        if sel in ('a', 'A'):
            ctx.CacheGameRoot = None
            continue
        if sel in ('f', 'F'):
            picked = pick_folder_dialog(ctx, '请选中游戏的 Game 文件夹（里面有 eldenring.exe）' + '\r\n' + '例如 …\\steamapps\\common\\ELDEN RING\\Game')
            if not picked:
                continue
            root = test_normalize_game_root(picked)
            if root:
                save_game_root(ctx, root)
                return True
            write_err('这个目录里没找到 Game\\eldenring.exe：' + picked)
            _read_host('按回车重试')
            continue
        if sel in ('e', 'E'):
            picked = pick_exe_dialog(ctx, '选择 eldenring.exe')
            if not picked:
                continue
            root = test_normalize_game_root(picked)
            if root:
                save_game_root(ctx, root)
                return True
            write_err('这个 exe 的位置不像 Elden Ring 安装：' + picked)
            _read_host('按回车重试')
            continue
        n = _try_int32(sel)
        if n is not None and 1 <= n <= len(cands):
            save_game_root(ctx, cands[n - 1])
            return True
        root = test_normalize_game_root(sel)
        if root:
            save_game_root(ctx, root)
            return True
        write_err('无法识别（可输入序号、[F]/[E]/[A]/[Q]，或粘贴路径）：' + sel)
        _read_host('按回车重试')


# ---------------------------------------------------------------- 游戏的 Steam 语言
def get_steam_game_language(ctx):
    """Get-SteamGameLanguage：steamapps\\appmanifest_1245620.acf 的 language（比如 schinese / english）；不是 Steam 版、读不到返回 ''"""
    try:
        gr = resolve_game_root(ctx)
        if not gr:
            return ''
        steamapps = net_dirname(net_dirname(gr.rstrip('\\')))
        if not steamapps:
            return ''
        acf = os.path.join(steamapps, 'appmanifest_1245620.acf')
        if not os.path.exists(acf):
            return ''
        # Select-String：一行一行找，不分大小写
        for line in ps_lines(read_all_text(acf)):
            m = re.search(r'"language"\s+"([^"]*)"', line, re.I)
            if m:
                return m.group(1)
    except (OSError, ValueError):
        pass
    return ''


# ---------------------------------------------------------------- 游戏版本
def get_game_exe_version(GameExe):
    """Get-GameExeVersion：eldenring.exe 的文件版本（「2.7.1.0」）；读不到（或主、次版本都是 0）返回 ''"""
    try:
        if not GameExe or not os.path.exists(GameExe):
            return ''
        v = win.file_version(GameExe)
    except (OSError, ValueError):
        return ''
    if v and (v[0] or v[1]):
        return '%d.%d.%d.%d' % v
    return ''


def test_game_version(ctx, GameExe):
    """Test-GameVersion：启动前核对游戏版本：认得的（或读不到版本的）返回 True；认不得的弹窗说明，玩家点「仍然启动」返回 True，否则 False。
    -NoLaunch（只生成不启动，测试用）不弹窗，只写一行提示"""
    from .dialog import show_dr_dialog
    v = get_game_exe_version(GameExe)
    if not v:
        write_warn('读不到游戏版本（' + GameExe + '），照常启动。')
        return True
    if v in SupportedGameVersions:
        host('  游戏版本 : ' + SupportedGameVersions[v] + '（' + v + '）')
        return True
    names = '和 '.join(SupportedGameVersions[k] + '（' + k + '）' for k in SupportedGameVersions)
    newest = sorted(core.ps_version(k) for k in SupportedGameVersions)[-1]
    if core.ps_version(v) > newest:
        why = '游戏更新到了 ' + v + '，整合包还没跟上这个版本。'
        support = '整合包现在只支持 ' + names + '。'
        fix = '等整合包出新版本（打开启动器时会自动检查更新）。'
    else:
        why = '这个游戏的版本是 ' + v + '，比整合包支持的旧。'
        support = '整合包只支持 ' + names + '。'
        fix = 'Steam 版：在 Steam 里把游戏更新到最新。\r\n不是 Steam 版：换成 ' + ' 或 '.join(SupportedGameVersions.values()) + ' 的游戏文件。'
    lost = '在这个版本上，新装备的属性和词条、鉴定、商店等大部分功能都不会工作。'
    if ctx.NoLaunch:
        write_player_warn(why + support + lost)
        return True
    r = show_dr_dialog(why + '\r\n' + support + '\r\n\r\n' + lost + '\r\n\r\n' + fix + '\r\n\r\n还是要启动吗？', '暗黑重铸 · 游戏版本不支持',
                       ['不启动', '仍然启动'], 0, 0, 'warn')
    if r == 1:
        write_player_warn('游戏版本 ' + v + ' 不支持，按你的选择照常启动：大部分功能不会工作。')
        return True
    write_err('游戏版本 ' + v + ' 不支持，没有启动。' + fix.replace('\r\n', ' '))
    return False
