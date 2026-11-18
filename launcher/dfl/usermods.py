# -*- coding: utf-8 -*-
"""玩家自己加的东西（usermods.ps1；用户 2026-11-16「怎么能方便玩家可以自己手动编辑yafsml」→「两层都做」）：
  mods\\                 整合包根目录，放游戏文件类的 mod（外观、模型、特效……解压后带 parts / chr / sfx 这些文件夹的）。
                        一个 mod 一个文件夹，每次启动自动扫描，加进 YAFSML 的 [mod]，排在整合包自己的包前面（同名文件以整合包为准）；
                        文件夹名以 _ 开头 = 停用；按名字顺序。解压多套了一两层文件夹的自己往里找；直接把 parts 之类放进 mods\\ 的，把 mods\\ 整个当一个 mod。
  YAFSML自定义.ini      整合包根目录，玩家改加载器设置的地方（yafsml\\YAFSML.ini 每次启动按模板重写，改了会被覆盖）：
                        [patch] [tweak] [log] 等里写的项替换模板里同名的（存档、内存相关的几项不让改，见 UserIniLocked）；
                        [mod] 的行排在整合包前面，[mod_after] 的排在最后（同名文件以它为准），[dll] 的加在 DLL 最后（联机的 ersc.dll 在最前面）。
                        路径可以写完整的，也可以写相对整合包根目录的。没有这个文件时启动器第一次启动写一份带说明的。
两样都不在发布包里（dev\\tools\\make_package.py 的 EXCL），整合包更新不会动。路径是 ctx.UserModDir / ctx.UserIniPath。

和 PowerShell 一样的细节：mod 的加载顺序是 Sort-Object Name（区域规则、不分大小写，backup._ps_sort_by）；ini 的段名、键名不分大小写
（同一段里大小写不同的键算一个：留第一次出现的位置、最后一次的写法和值，和 [ordered]@{} 一样）；
玩家可能把 YAFSML自定义.ini 存成 GBK / UTF-16：读的时候认 BOM，坏字节换成 U+FFFD，不报错。"""
import os
import re

from .backup import _gci, _net_read_lines, _ps_sort_by
from .core import Rec, ieq

# 不让玩家改的：存档文件名（改了会读写原版 / 法魂的存档）、防止往存档写「已修改」、内存分配器（关掉进游戏就崩）、游戏
UserIniLocked = ['game', 'replace_save_filename', 'replace_seamless_coop_save_filename', 'prevent_regulation_save_write', 'patch_mem']
# 游戏数据的顶层文件夹 / 文件（mod 文件夹里有这些才算找到了 mod 的根）
GameDataNames = ['action', 'asset', 'chr', 'cutscene', 'event', 'expression', 'facegen', 'font', 'map', 'material', 'menu', 'movie',
                 'msg', 'other', 'param', 'parts', 'script', 'sd', 'sfx', 'shader', 'sound', 'regulation.bin']

# .NET 的空白（String.Trim、正则 \s）：和 Python 的 str.strip / \s 差在 \x1c-\x1f（Python 算空白，.NET 不算）
_NET_WS = '\t\n\x0b\x0c\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
_WS_CLASS = '[' + re.escape(_NET_WS) + ']'


def _trim(s):
    return s.strip(_NET_WS)


class _IDict(dict):
    """[ordered]@{}：按加入的顺序、键不分大小写。已有的键再赋值：位置不变，键的写法和值换成新的（OrderedDictionary 就是这样）"""

    def __init__(self):
        super().__init__()
        self._k = {}                       # 小写 → 现在的写法

    def __setitem__(self, k, v):
        f = k.casefold()
        old = self._k.get(f)
        if old is None:
            self._k[f] = k
            super().__setitem__(k, v)
            return
        if old != k:                       # 换键的写法，位置不变
            items = [(k if x == old else x, y) for x, y in super().items()]
            super().clear()
            for x, y in items:
                super().__setitem__(x, y)
            self._k[f] = k
        super().__setitem__(k, v)

    def __getitem__(self, k):
        return super().__getitem__(self._k.get(k.casefold(), k))

    def __contains__(self, k):
        return isinstance(k, str) and k.casefold() in self._k

    def get(self, k, d=None):
        return self[k] if k in self else d


def test_game_data_root(Dir):
    for n in GameDataNames:
        if os.path.exists(os.path.join(Dir, n)):
            return True
    return False


def _sorted_dirs(path):
    """Get-ChildItem -Directory | Sort-Object Name（按区域规则比的名字相等时——比如只差一个软连字符——谁在前也和 PowerShell 5.1 一样）"""
    return _ps_sort_by(_gci(path, files=False), lambda d: d.Name)


def find_mod_roots(Dir, Depth=2):
    """一个 mod 文件夹里真正的根（带 parts / chr … 的那一层）：自己就是，或者往里找两层（压缩包解压常多套一层）；
    找到不止一个（几个版本让玩家挑的那种）返回全部，交给调用的报错"""
    if test_game_data_root(Dir):
        return [Dir]
    if Depth <= 0:
        return []
    found = []
    for d in _sorted_dirs(Dir):
        if d.Name.startswith('_'):
            continue
        found += find_mod_roots(d.FullName, Depth - 1)
    return found


def get_user_mod_info(ctx):
    """mods\\ 里的每个 mod：[Rec(Name, Path（根，没找到是 None）, Off（_ 开头停用）, Issues（给玩家看的问题）)]"""
    out = []
    if not os.path.exists(ctx.UserModDir):
        return out
    if test_game_data_root(ctx.UserModDir):
        # 直接把 parts 之类放进了 mods\：整个 mods\ 当一个 mod（里面别的子文件夹不会被当成游戏文件，不碍事）
        out.append(Rec(Name='mods', Path=ctx.UserModDir, Off=False, Issues=[]))
    for d in _sorted_dirs(ctx.UserModDir):
        if any(ieq(d.Name, n) for n in GameDataNames):          # 上面整个 mods\ 已经算了
            continue
        if d.Name.startswith('_'):
            out.append(Rec(Name=d.Name, Path=None, Off=True, Issues=[]))
            continue
        roots = find_mod_roots(d.FullName)
        m = Rec(Name=d.Name, Path=None, Off=False, Issues=[])
        if len(roots) == 0:
            m.Issues.append('里面没找到游戏文件（parts、chr、sfx 这类文件夹），没有加载')
            if _gci(d.FullName, dirs=False, pattern='*.dll', recurse=True, depth=2):
                m.Issues.append('里面是 DLL：DLL 类的 mod 要放进整合包的 dll 文件夹')
        elif len(roots) > 1:
            m.Issues.append('里面有 ' + str(len(roots)) + ' 套文件（' + '、'.join(os.path.basename(r) for r in roots) +
                            '），没有加载：留下要用的那套，别的删掉或在文件夹名前加 _')
        else:
            m.Path = roots[0]
        out.append(m)
    for m in out:
        if not m.Path:
            continue
        if os.path.exists(os.path.join(m.Path, 'regulation.bin')):
            m.Issues.append('带了 regulation.bin：里面的数值改动不会生效（整合包自己的优先），外观之类的照常加载')
        if _gci(m.Path, dirs=False, pattern='*.dll'):
            m.Issues.append('里面的 DLL 不会加载：要放进整合包的 dll 文件夹')
    return out


_BAD_PATH_CHARS = re.compile('["<>|\x00-\x1f]')


def resolve_user_path(ctx, P):
    """路径：完整路径照用；相对路径按整合包根目录算。
    .NET 的 IsPathRooted / GetFullPath 遇到非法字符会抛异常（调用的地方接住，玩家看到的就是这句话），这里照样抛、说法一样"""
    P = _trim(P or '').strip('"')
    if not P:
        return ''
    if _BAD_PATH_CHARS.search(P):
        raise ValueError('使用“1”个参数调用“IsPathRooted”时发生异常:“路径中具有非法字符。”')
    if P[0] in '\\/' or (len(P) >= 2 and P[1] == ':'):                # [IO.Path]::IsPathRooted
        return P
    full = os.path.join(ctx.Paly, P)
    if '*' in full or '?' in full:
        raise ValueError('使用“1”个参数调用“GetFullPath”时发生异常:“路径中具有非法字符。”')
    if ':' in full[2:]:
        raise ValueError('使用“1”个参数调用“GetFullPath”时发生异常:“不支持给定路径的格式。”')
    return _get_full_path(full)


def _get_full_path(p):
    """[IO.Path]::GetFullPath：和 os.path.abspath 不同，结尾的 \\ 保留（都是 Windows 的 GetFullPathNameW）"""
    import nt
    return nt._getfullpathname(p)


def read_user_ini(ctx):
    """YAFSML自定义.ini → Rec(Sections = { 段名小写: { 键: 值 } }（都按出现的顺序、不分大小写）, Names = { 段名小写: 原样的段名 })；没有文件 = 空的"""
    sec = _IDict()
    names = _IDict()
    if not os.path.exists(ctx.UserIniPath):
        return Rec(Sections=sec, Names=names)
    cur = None
    for raw in _net_read_lines(ctx.UserIniPath):
        l = _trim(raw)
        if not l or l.startswith(';') or l.startswith('#'):
            continue
        m = re.match(r'^\[([^\]]+)\]$', l)
        if m:
            cur = _trim(m.group(1)).lower()
            names[cur] = _trim(m.group(1))
            if cur not in sec:
                sec[cur] = _IDict()
            continue
        m = re.match(r'^([^=]+?)' + _WS_CLASS + '*=' + _WS_CLASS + '*(.*)$', l)
        if cur is None or not m:
            continue
        sec[cur][_trim(m.group(1))] = _trim(m.group(2))
    return Rec(Sections=sec, Names=names)


_INI_TEMPLATE = [
    '; 暗黑重铸 · YAFSML 自定义配置（自己改这个文件；整合包更新不会动它）',
    '; 启动器每次启动都会重新生成 yafsml\\YAFSML.ini，直接改那个会被覆盖，所以改这里。改完下次启动游戏生效。',
    ';',
    '; [patch] [tweak] [log]：写在这里的设置替换整合包里同名的设置（下面的例子去掉行首的分号就生效）。',
    ';     存档和内存相关的几项（replace_save_filename、replace_seamless_coop_save_filename、prevent_regulation_save_write、patch_mem）不能改，写了也不生效。',
    '; [mod]：额外加载的 mod，一行一个「名字=文件夹」，文件夹里是 parts、chr、sfx 这些。排在整合包前面，同名文件以整合包为准。',
    ';     更省事的办法：把 mod 文件夹直接放进整合包根目录的 mods 文件夹，不用写这里。',
    '; [mod_after]：排在整合包后面，同名文件以这个 mod 为准（可能让整合包的功能失效，确定需要再用）。',
    '; [dll]：额外加载的 DLL，一行一个「名字=dll 路径」（也可以直接放进整合包的 dll 文件夹）。',
    '; 路径可以写完整路径，也可以写相对整合包根目录的路径。',
    '',
    '[patch]',
    '; 跳过开场动画（整合包默认就是 1）',
    ';skip_intro=1',
    '; 游戏里能用输入法打中文（整合包默认 0）',
    ';enable_ime=1',
    '',
    '[tweak]',
    ';cpu_affinity=0',
    '',
    '[mod]',
    ';look=D:\\ERMods\\look',
    '',
    '[mod_after]',
    '',
    '[dll]',
    '',
]


def new_user_ini(ctx):
    """没有 YAFSML自定义.ini 就写一份带说明的（UTF-8 带 BOM：老系统的记事本也认得中文；CRLF）；返回路径"""
    if os.path.exists(ctx.UserIniPath):
        return ctx.UserIniPath
    with open(ctx.UserIniPath, 'wb') as f:
        f.write(b'\xef\xbb\xbf' + '\r\n'.join(_INI_TEMPLATE).encode('utf-8'))
    return ctx.UserIniPath


def get_user_load_lines(ctx):
    """要加进 YAFSML.ini 的玩家内容：Rec(Before = [mod] 前面的行, After = [mod] 最后的行, Dll = [dll] 的行, Mods = mods\\ 里加载了的名字, Notes = 给玩家看的提示)"""
    r = Rec(Before='', After='', Dll='', Mods=[], Notes=[])
    before, after, dll = [], [], []
    used = set()                                                   # 和 PowerShell 的 @{} 一样不分大小写

    def key(prefix, name):
        k = prefix + re.sub(r'[^A-Za-z0-9_]', '_', name)
        k2 = k
        n = 2
        while k2.casefold() in used:
            k2 = k + '_' + str(n)
            n += 1
        used.add(k2.casefold())
        return k2
    for m in get_user_mod_info(ctx):
        for i in m.Issues:
            r.Notes.append('mods\\' + m.Name + '：' + i)
        if m.Off or not m.Path:
            continue
        before.append(key('user_mod_', m.Name) + '=' + m.Path)
        r.Mods.append(m.Name)
    if before:
        before = ['; 玩家的 mod（整合包根目录 mods\\，自动扫描；排在整合包前面，同名文件以整合包为准）'] + before
    ini = read_user_ini(ctx)
    for s in ('mod', 'mod_after', 'dll'):
        if s not in ini.Sections:
            continue
        for k in list(ini.Sections[s].keys()):
            v = str(ini.Sections[s][k])
            cond = ''
            if s == 'dll' and '|' in v:
                i = v.index('|')
                cond = v[i:]
                v = v[:i]
            # 路径里有 " < > | * ? : 这类字符：只跳过这一项（以前整个函数出错，自己加的 mod 一个都不加载；2026-11-18 移植时修）
            try:
                p = resolve_user_path(ctx, v)
            except ValueError:
                r.Notes.append('YAFSML自定义.ini [' + s + '] 的 ' + k + '：路径里有不能用的字符（" < > | * ? 之类）：' + v + '，没有加载')
                continue
            if not p or not os.path.exists(p):
                r.Notes.append('YAFSML自定义.ini [' + s + '] 的 ' + k + '：找不到 ' + v + '，没有加载')
                continue
            # Seamless Co-op 只能走联机启动（联机计划 13.2 G9）：那里会查联机密码（空的会让游戏退出）、把联机存档和单机分开
            if s == 'dll' and ieq(re.split(r'[\\/:]', p)[-1], 'ersc.dll'):
                r.Notes.append('YAFSML自定义.ini [dll] 的 ' + k + '：Seamless Co-op（ersc.dll）不在这里加载，联机请用启动器的「联机」启动')
                continue
            line = key('custom_', k) + '=' + p + cond
            if s == 'mod':
                before.append(line)
            elif s == 'mod_after':
                after.append(line)
            else:
                dll.append(line)
    if before:
        r.Before = '\r\n'.join(before)
    if after:
        r.After = '; YAFSML自定义.ini 的 [mod_after]（排在整合包后面）\r\n' + '\r\n'.join(after)
    if dll:
        r.Dll = '; YAFSML自定义.ini 的 [dll]\r\n' + '\r\n'.join(dll)
    return r


def merge_user_ini_settings(ctx, Text):
    """生成的 YAFSML.ini 文字里，按 YAFSML自定义.ini 替换 / 加上设置（[mod] [mod_after] [dll] 以外的段）；返回 Rec(Text, Applied = 改了哪些, Notes = 提示)"""
    Text = Text or ''
    res = Rec(Text=Text, Applied=[], Notes=[])
    ini = read_user_ini(ctx)
    lines = re.split(r'\r?\n', Text)
    for s in list(ini.Sections.keys()):
        if s.casefold() in ('mod', 'mod_after', 'dll'):
            continue
        for k in list(ini.Sections[s].keys()):
            v = str(ini.Sections[s][k])
            if k.lower() in UserIniLocked:
                res.Notes.append('YAFSML自定义.ini 的 ' + k + ' 不能改（存档 / 内存相关），用整合包的设置')
                continue
            # 找这一段：[段名] 到下一个 [ 之间
            hrx = re.compile(r'^\[' + re.escape(s) + r'\]$', re.I)
            h = -1
            for i in range(len(lines)):
                if hrx.search(_trim(lines[i])):
                    h = i
                    break
            if h < 0:
                lines += ['', '[' + ini.Names[s] + ']', k + '=' + v]
                res.Applied.append('[' + ini.Names[s] + '] ' + k + '=' + v)
                continue
            end = len(lines)
            for i in range(h + 1, len(lines)):
                if _trim(lines[i]).startswith('['):
                    end = i
                    break
            krx = re.compile('^' + re.escape(k) + _WS_CLASS + '*=', re.I)
            hit = -1
            last = h
            for i in range(h + 1, end):
                t = _trim(lines[i])
                if t and not t.startswith(';'):
                    last = i
                if krx.search(t):
                    hit = i
            if hit >= 0:
                lines[hit] = k + '=' + v
            else:
                lines.insert(last + 1, k + '=' + v)
            res.Applied.append('[' + ini.Names[s] + '] ' + k + '=' + v)
    res.Text = '\r\n'.join(lines)
    return res


def get_user_mod_summary(ctx):
    """诊断包用：mods\\ 和 YAFSML自定义.ini 的情况（几行文字）"""
    out = []
    mods = get_user_mod_info(ctx)
    if mods:
        parts = []
        for m in mods:
            if m.Off:
                suf = '（停用）'
            elif not m.Path:
                suf = '（没加载）'
            elif ieq(m.Path, ctx.UserModDir):
                suf = '（直接放在 mods 里的）'
            elif not ieq(m.Path, os.path.join(ctx.UserModDir, m.Name)):
                suf = '（根：' + m.Path[len(ctx.UserModDir):].lstrip('\\') + '）'
            else:
                suf = ''
            parts.append(m.Name + suf)
        out.append('mods 文件夹：' + '、'.join(parts))
    else:
        out.append('mods 文件夹：没有')
    out.append('YAFSML自定义.ini：' + ('有（诊断包里附了一份）' if os.path.exists(ctx.UserIniPath) else '没有'))
    return out
