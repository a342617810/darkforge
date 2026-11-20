# -*- coding: utf-8 -*-
"""启动（launcher.ps1 的「生成 ini」「启动游戏」「Boss 模组」「动作：启动」「状态显示」几节，和崩溃看守的启动）：
用户 DLL（dll\\ 文件夹）、敌人信息 mod 开关、游戏脚本 / 菜单覆盖包（reroll\\scripts.py、menu.py）、写 yafsml\\YAFSML.ini、原版文件来源（vanilla.py）、
重随（reroll.py）、Boss 模组、开 YAFSML、启动后的崩溃看守。

每次启动前都重新生成两个覆盖包（YAFSML 按 [mod] 的顺序加载，后面的覆盖前面的）：
  out\\reroll    reroll\\reroll.py：在原版（randomizer\\diste\\Vanilla）或随机器输出的 regulation 上改
                （敌人血量分档、Boss 奖励、开局物品、局内难度、训练木桩……），只写到这里，不改原文件
  out\\scripts   reroll\\scripts.py：赐福菜单、公共事件、玩家动作脚本等，在前面各包最后生效的那份上合并
敌人随机时前面再加随机器输出（randomizer）和按新位置修补过的地图（out\\reroll_maps）。

别的模块（backup / randomizer / usermods / coop）在函数里面才 import：它们也 import 这里（coop 用 get_boss_mods、invoke_launch），免得循环引用。"""
import datetime
import decimal
import inspect
import json
import os
import re
import shutil
import subprocess
import time

from . import core, gamepath, win
from .core import Rec, host, write_err, write_head, write_ok, write_player, write_player_warn, write_progress_bar, write_warn
from .gamepath import ls, ps_lines, read_all_text, read_lines_utf8

# 一直往后追加的日志（各 DLL 的；YAFSML、随机器的 CrashFix 另算）：超过 2 MB 就挪成 <文件名>.old（Save-RunLogs）
AppendLogs = ('dark_core\\dark_core.log', 'dark_lock\\dark_lock.log', 'dark_sell\\dark_sell.log', 'dark_slot\\dark_slot.log', 'dark_wings\\dark_wings.log')
# 联机 · 无敌人随机固定用的重随种子（两个人的游戏数据要一样；敌人随机用随机器的种子。coop.get_coop_seed 用）
CoopVanillaSeed = 20261102

_sleep = time.sleep          # 测试时换掉（Stop-EldenRing / Start-YafGame 的等待）


def _start(args, **kw):
    """直接启动别的程序（不经过 shell；测试时换掉）"""
    return subprocess.Popen(args, **kw)


# ---------------------------------------------------------------- PowerShell 语义的小工具
def _g(o, k, default=None):
    """$o.Key：字典 / Rec 按键找（不分大小写，和 PowerShell 读 [pscustomobject] / 哈希表一样），别的对象按属性；没有返回 None"""
    if o is None:
        return default
    if isinstance(o, dict):
        if k in o:
            return o[k]
        kl = k.casefold()
        for kk, v in o.items():
            if isinstance(kk, str) and kk.casefold() == kl:
                return v
        return default
    return getattr(o, k, default)


def _json(text):
    """ConvertFrom-Json：带小数点的数字留成 Decimal（PowerShell 5.1 也是 Decimal，[string] 出来是「1.0」不是「1」）"""
    return json.loads(text, parse_float=decimal.Decimal)


def _true(v):
    """PowerShell 的真假：$null、''、0、空数组为假；只有一个元素的数组看那个元素；对象（哪怕是空的 {}）为真"""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, decimal.Decimal)):
        return v != 0
    if isinstance(v, str):
        return len(v) > 0
    if isinstance(v, (list, tuple)):
        if not v:
            return False
        return _true(v[0]) if len(v) == 1 else True
    return True


def _eq_true(v):
    """$x -eq $true：左边是什么类型就按什么比（1 -eq $true、'true' -eq $true 也是真；数组是筛出等于 $true 的）"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, decimal.Decimal)):
        return v == 1
    if isinstance(v, str):
        return v.casefold() == 'true'
    if isinstance(v, (list, tuple)):
        return any(_eq_true(x) for x in v)
    return False


def _s(v):
    """[string]$x / 字符串拼接：$null 是 ''，布尔是 True / False，整数的小数不带 .0，数组用空格连起来"""
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    if isinstance(v, decimal.Decimal):
        return format(v, 'f')
    if isinstance(v, (list, tuple)):
        return ' '.join(_s(x) for x in v)
    return str(v)


def _list(v):
    """@($x)：$null 是空数组，单个值包成一个元素的数组"""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _full(f):
    """文件对象的完整路径（别的模块给的可能是路径字符串，也可能是带 FullName 的对象）"""
    if f is None:
        return ''
    if isinstance(f, (str, os.PathLike)):
        return os.fspath(f)
    return _s(_g(f, 'FullName'))


def _name(f):
    if isinstance(f, (str, os.PathLike)):
        return os.path.basename(os.fspath(f))
    n = _g(f, 'Name')
    return _s(n) if n is not None else os.path.basename(_full(f))


def _hostm(text):
    """Write-Host 一段多行的文字：按行分开写（标准输出和运行日志里换行都是一个 \\r\\n，和 PowerShell 一样）"""
    for line in re.split(r'\r?\n', _s(text)):
        host(line)


def _multi(fn, text):
    """Write-Err / Write-Warn 一段可能有换行的文字（别的模块给的说明）：前缀只在第一行，后面的行原样（和 PowerShell 的 Write-Host 一样）"""
    lines = re.split(r'\r?\n', _s(text))
    fn(lines[0])
    for line in lines[1:]:
        host(line)


def _jp(a, b):
    """Join-Path a b：中间只留一个 \\（b 以 \\ 开头也是接在 a 后面，不像 os.path.join 那样当成根目录）"""
    return a.rstrip('\\/') + '\\' + b.lstrip('\\/')


def _xcall(fn, ctx, *args):
    """调别的模块的函数：它第一个参数叫 ctx 就带上 ctx（纯函数可以不带 ctx，见移植约定「命名」）"""
    try:
        params = list(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        params = []
    if params and params[0] == 'ctx':
        return fn(ctx, *args)
    return fn(*args)


def _remove_file(p):
    """Remove-Item -Force -ErrorAction SilentlyContinue（只读的也删）"""
    try:
        os.remove(p)
    except PermissionError:
        try:
            os.chmod(p, 0o666)
            os.remove(p)
        except OSError:
            pass
    except OSError:
        pass


def _mtime(p):
    """LastWriteTime（本地时间）"""
    return datetime.datetime.fromtimestamp(os.stat(p).st_mtime)


def _eldenring_running():
    return bool(win.find_pids('eldenring'))


def _get_item_size(p):
    """Get-Item -LiteralPath p 的 Length：是文件才有；不存在、是文件夹、或者是隐藏的（Get-Item 不给 -Force 拿不到）返回 None"""
    try:
        st = os.stat(p)
    except OSError:
        return None
    if getattr(st, 'st_file_attributes', 0) & 0x12:          # FILE_ATTRIBUTE_HIDDEN | DIRECTORY
        return None
    return st.st_size


# ---------------------------------------------------------------- 生成 ini：用户 DLL
# 用户自己加的 DLL mod：整合包根目录的 dll\ 文件夹，每次生成配置时自动扫描（所有启动方式都加载）。
#   dll\xxx.dll           直接放
#   dll\某个mod\xxx.dll    mod 带配置文件 / 资源时整个文件夹放进来（只看这一层的 .dll）
#   文件名或文件夹名以 _ 开头 = 停用；按路径字母顺序加载（Sort-Object：区域规则、不分大小写）
#   Seamless Co-op（ersc.dll）不在这里加载：只有联机启动才加载（见 coop 模块，Join-DllLines 放最前面）
def get_user_dll_lines(ctx):
    """Get-UserDllLines：dll\\ 里要加载的 DLL 写成 [dll] 的行；一个都没有返回 ''"""
    import fnmatch
    if not os.path.exists(ctx.UserDllDir):
        return ''
    files = ls(ctx.UserDllDir, '*.dll', 'file')
    for name, full in ls(ctx.UserDllDir, '*', 'dir'):
        if name.startswith('_'):
            continue
        files += ls(full, '*.dll', 'file')
    lines = []
    used = set()
    for name, full in win.culture_sorted([f for f in files if not f[0].startswith('_')], key=lambda f: f[1]):
        if name.casefold() == 'ersc.dll':
            continue
        if not test_user_dll_safe(ctx, full):
            continue
        rel = full[len(ctx.UserDllDir):].lstrip('\\')
        base = name[:name.rfind('.')] if '.' in name else name          # BaseName（扩展名一定是 .dll）
        key = 'user_' + re.sub(r'[^A-Za-z0-9_]', '_', base, flags=re.I)
        k = key
        n = 2
        while k.casefold() in used:                                     # 哈希表的键不分大小写
            k = key + '_' + str(n)
            n += 1
        used.add(k.casefold())
        # 敌人信息 mod 晚 3 秒再加载（YAFSML 自带的示例也是 delay）：启动头几秒 dark_ui、ErdTools、幻化插件都在装钩子，
        # 装钩子时会把进程里别的线程都停一下，错开免得撞在一起（崩溃风险审查 2026-11-19 第 14 条）
        cond = '|delay,3000' if fnmatch.fnmatchcase(name.lower(), 'souls_vision*.dll') else ''
        lines.append(k + '=..\\dll\\' + rel + cond)
    if not lines:
        return ''
    return '; 用户 DLL（整合包根目录 dll\\ 文件夹，自动扫描）\r\n' + '\r\n'.join(lines)


# 会改存档文件名的 DLL：不处理的话会读写原版（.sl2）或法魂（.cnv）的存档
#   Erd Tools：把 ini 里的 save_extension 写进游戏内存（缺省 sl2；没有 ini 时扩展名会变成空的）→ 保证同目录有 ini，
#             单机为 rng、联机为 co2（ctx.ErdSaveExt；和 Seamless Co-op 一致，YAFSML 再换成 .rngcoop，免得联机读写单机存档）；
#             persistent_lantern 一律设成 0：它在游戏加载参数时自己扫参数仓库找 SpEffectParam，有的电脑上仓库还没加载完就崩
#             （玩家崩溃诊断包 2026-11-18，ErdTools.dll+0x13D43）；提灯传送后保留改由重随写进参数（rr/tweaks.py lantern_persist）
#   独立存档类 dll（alt_saves）：存档已由 YAFSML 的 replace_save_filename 隔离，再叠一个会改成别的文件 → 不加载
ERD_INI_NEW = ('[SAVE]\r\n; Dark Reforged：单机 rng、联机 co2，启动器每次启动按启动方式改（和 YAFSML 的 replace_save_filename 一致）\r\n'
               'save_extension = %s\r\n\r\n[PARAM]\r\n; Dark Reforged：提灯传送后保留由整合包自己做，这一项一直是 0\r\npersistent_lantern = 0\r\n')


def test_user_dll_safe(ctx, File):
    """Test-UserDllSafe：这个 DLL 能不能加载（File = 完整路径）；Erd Tools 顺带把 erd_tools.ini 改对（UTF-8 带 BOM）"""
    import fnmatch
    full = _full(File)
    fname = os.path.basename(full)
    n = fname.lower()
    if fnmatch.fnmatchcase(n, '*alt_saves*') or fnmatch.fnmatchcase(n, '*altsaves*'):
        write_warn('不加载 ' + fname + '：它会另外改存档文件名，和整合包的独立存档（ER0000.rng）冲突。')
        return False
    if fnmatch.fnmatchcase(n, 'souls_vision*.dll'):
        return test_enemy_info_mod(ctx)
    if fnmatch.fnmatchcase(n, 'erdtools*.dll') or fnmatch.fnmatchcase(n, 'erd_tools*.dll'):
        ini = os.path.join(os.path.dirname(full), 'erd_tools.ini')
        ext = _s(getattr(ctx, 'ErdSaveExt', 'rng'))
        try:
            if not os.path.exists(ini):
                # -DryRun 时也照样新建（和 PowerShell 一样）
                core.write_text(ini, ERD_INI_NEW % ext, bom=True)
                write_warn('Erd Tools 缺少 erd_tools.ini，已新建一个（只设了存档扩展名 ' + ext + '，其他用默认）：' + ini)
                return True
            txt = read_all_text(ini)
            orig = txt
            m = re.search(r'^[ \t]*save_extension[ \t]*=[ \t]*([^\r\n;]*)', txt, re.I | re.M)
            cur = m.group(1).strip() if m else ''
            ext_change = cur.casefold() != ext.casefold()
            if ext_change:
                if m:
                    txt = txt[:m.start(1)] + ext + txt[m.end(1):]
                else:
                    txt = txt.rstrip() + '\r\n\r\n[SAVE]\r\nsave_extension = ' + ext + '\r\n'
            # 提灯传送后保留：ErdTools 那一项关掉（见上面的说明），有 [PARAM] 段没这一项的加进去，没有 [PARAM] 段的补一段
            lm = re.search(r'^[ \t]*persistent_lantern[ \t]*=[ \t]*([^\r\n;]*)', txt, re.I | re.M)
            lantern_fix = False
            if lm:
                if lm.group(1).strip() != '0':
                    txt = txt[:lm.start(1)] + '0' + txt[lm.end(1):]
                    lantern_fix = True
            else:
                pm = re.search(r'^[ \t]*\[PARAM\][ \t]*\r?\n', txt, re.I | re.M)
                if pm:
                    txt = txt[:pm.end()] + 'persistent_lantern = 0\r\n' + txt[pm.end():]
                else:
                    txt = txt.rstrip() + '\r\n\r\n[PARAM]\r\npersistent_lantern = 0\r\n'
                lantern_fix = True
            if txt == orig:
                return True
            if ctx.DryRun:
                if ext_change:
                    host('  [-DryRun] Erd Tools 的存档扩展名现在是「' + cur + '」，真的启动时会改成 ' + ext)
                if lantern_fix:
                    host('  [-DryRun] 真的启动时会把 Erd Tools 的 persistent_lantern 设成 0')
                return True
            flip = cur.casefold() in ('rng', 'co2')      # 单机 / 联机之间切换：平常事，不备份
            if ext_change and not flip:
                shutil.copy2(ini, ini + '.bak_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
            core.write_text(ini, txt, bom=True)
            if ext_change:
                if flip:
                    host('  Erd Tools 的存档扩展名换成 ' + ext + ('（联机）' if ext.casefold() == 'co2' else '（单机）'))
                else:
                    write_warn('Erd Tools 的存档扩展名不是 ' + ext + '（会读写别的存档），已改成 ' + ext + '（原 ini 已备份）：' + ini)
            if lantern_fix:
                host('  Erd Tools 的 persistent_lantern 设成 0（提灯传送后保留改由整合包自己做）')
            return True
        except (OSError, ValueError) as e:
            write_err('检查 Erd Tools 配置失败，这次不加载它：' + str(e))
            return False
    return True


# ---------------------------------------------------------------- 敌人信息 mod
# 敌人信息 mod（dll\souls_vision.dll：敌人头上的血条、状态条）在有的双显卡电脑（核显 + 独显，笔记本常见）上会让游戏读档时崩溃：
# 它启用悬浮层时自己建一个 DX12 设备，游戏的显卡设备随即丢失，读档时游戏锁显存缓冲区拿到空地址（2026-11-01 玩家 RTX 5070 笔记本 + Radeon 610M 核显，
# 两次诊断都是它启用后 1~2 秒设备丢失，关掉就好了）。不是每台双显卡电脑都会。以前检测到双显卡时让玩家自己选（用户 2026-11-01），
# 2026-11-16 改成不问、默认加载（用户「只是说明可能导致游戏无法启动并给出关闭的路径 不需要让玩家一开始就选是否加载」）：
# 第一次打开启动器时说明一次，开关在「工具与设置」→「游戏」，记在 launcher\reroll\state\enemy_info_mod.txt（on / off）；
# 双显卡加载着它崩溃了，崩溃看守会问要不要改成不加载。给玩家看的文字一律叫「敌人信息 mod」，不用 mod 原名（用户 2026-11-01）。
def get_enemy_info_choice(ctx):
    """Get-EnemyInfoChoice：玩家的选择 on / off（大小写照文件里的）；还没选返回 None。
    PowerShell 用 Get-Content 不给编码读（5.1 按 ANSI 代码页）：这里也按 ANSI 读（值只会是英文）"""
    try:
        with open(ctx.EnemyInfoChoice, 'rb') as f:
            raw = f.read()
    except OSError:
        return None
    if raw.startswith(b'\xef\xbb\xbf'):
        text = raw[3:].decode('utf-8', 'replace')
    else:
        try:
            text = raw.decode('mbcs', 'replace')
        except LookupError:
            text = raw.decode('latin-1')
    lines = ps_lines(text)
    v = (lines[0] if lines else '').strip()
    if v.casefold() in ('on', 'off'):
        return v
    return None


def set_enemy_info_choice(ctx, Value):
    """Set-EnemyInfoChoice：写 on / off（UTF-8 无 BOM、CRLF）；写不了不管"""
    try:
        os.makedirs(os.path.dirname(ctx.EnemyInfoChoice), exist_ok=True)
        core.write_text(ctx.EnemyInfoChoice, _s(Value) + '\r\n')
    except OSError:
        pass


def show_top_yes_no(Text, Title, DefaultNo=False):
    """Show-TopYesNo：置顶的是 / 否对话框（dialog.show_dr_dialog）；DefaultNo = 默认按钮是「否」。
    返回 True（是）/ False（否）/ None（关掉了，没选）"""
    from .dialog import show_dr_dialog
    r = show_dr_dialog(Text, Title, ['是', '否'], 1 if DefaultNo else 0, -1, 'question')
    if r < 0:
        return None
    return r == 0


def test_enemy_info_mod(ctx):
    """Test-EnemyInfoMod：加不加载敌人信息 mod：玩家在启动器「工具与设置」→「游戏」里关掉了就不加载
    （所有电脑都能关，2026-11-11 应 Souls Vision 作者的要求），否则加载（不问）"""
    ch = get_enemy_info_choice(ctx)
    if ch is not None and ch.casefold() == 'off':
        host('  敌人信息 mod：按你的设置没加载（想打开：启动器「工具与设置」→「游戏」）。')
        return False
    gpus = list(win.get_gpu_names() or [])
    if len(gpus) >= 2:
        host('  敌人信息 mod：加载（这台电脑有两块显卡：' + '、'.join(gpus) + '；游戏启动不了或读档闪退的话，在启动器「工具与设置」→「游戏」里关掉它）')
    return True


def join_dll_lines(ctx, DllLines):
    """Join-DllLines：[dll] 的内容 = 启动方式自带的 + 用户 DLL + YAFSML自定义.ini 的 [dll]；联机启动时 Seamless Co-op 放最前面、加 early
    （游戏入口之前加载，和 ModEngine2 加载它的时机一样）。以前和法魂一样放最后（SteamAPI_Init 之后、我们 9 个 DLL 之后才初始化）：
    它初始化时要接管游戏自带的改动检测，在有的电脑上时好时坏，失败就弹「Cheat detection spider has failed」中止游戏
    （玩家诊断包 2026-11-17 / 11-18：两台电脑都只偶尔成功；用户 2026-11-18「把无缝加载优先级拉到最高吧」）"""
    DllLines = _s(DllLines)
    u = get_user_dll_lines(ctx)
    if u:
        DllLines = DllLines + '\r\n' + u
    pl = getattr(ctx, 'PlayerLoad', None)
    if _true(pl) and _true(_g(pl, 'Dll')):
        DllLines = DllLines + '\r\n' + _s(_g(pl, 'Dll'))
    if getattr(ctx, 'CoopDll', ''):
        DllLines = '; 联机启动：Seamless Co-op 最先加载（early）\r\nseamlesscoop=' + ctx.CoopDll + '|early\r\n' + DllLines
    return DllLines


# ---------------------------------------------------------------- 游戏脚本 / 菜单覆盖包
def get_scripts_line(ctx, ModLines):
    """Get-ScriptsLine：游戏脚本覆盖包（reroll\\scripts.py）：赐福脚本、公共事件、玩家动作脚本随机器输出也会改，不能直接用固定文件覆盖，
    按 [mod] 的加载顺序取最后生效的那份，把我们的功能合并进去，写到 out\\scripts；返回要追加的 [mod] 行（失败返回空，照常启动）"""
    from .pytool import find_python, invoke_py_json, write_py_errors
    if not os.path.exists(ctx.ScriptsTool):
        return ''
    py = find_python(ctx)
    if not py:
        write_warn('找不到 Python，这次不加载游戏脚本覆盖包。')
        return ''
    dirs = []
    for line in re.split(r'\r?\n', _s(ModLines)):
        m = re.search(r'^\s*[^;=\s][^=]*=(.+)$', line, re.I)
        if m:
            dirs.append(m.group(1).strip())
    a = ['-X', 'utf8', ctx.ScriptsTool, '--out', ctx.ScriptsPack, '--dll-dir', ctx.RandomDir]
    gr = gamepath.resolve_game_root(ctx)
    if gr:
        a += ['--dll-dir', os.path.join(gr, 'Game')]
    a += ['--sources'] + dirs
    r = invoke_py_json(ctx, py, a)
    if _true(r) and _true(_g(r, 'ok')) and _true(_g(r, 'warn')):
        write_warn('游戏脚本：' + _s(_g(r, 'msg')))
        return '\r\nDR_Scripts=' + ctx.ScriptsPack
    if _true(r) and _true(_g(r, 'ok')):
        write_ok('游戏脚本：' + _s(_g(r, 'msg')))
        return '\r\nDR_Scripts=' + ctx.ScriptsPack
    write_warn('游戏脚本覆盖包合并失败，这次不加载（赐福「更多选项」、局内难度、一键出售、不受坠落伤害、蹬墙跳、训练木桩这次都没有）：' +
               (_s(_g(r, 'msg')) if _true(r) else '没有输出'))
    write_py_errors(ctx)
    return ''


def set_lock_text_marker(ctx, Loaded):
    """物品菜单「锁定 / 送给」的文字（4190~4196）只在游戏脚本覆盖包里（sc/lock.py 写进 menu_dlc02）：这次没挂覆盖包就在 dll\\dark_lock\\
    放一个标记（no_menu_text.txt），dark_lock 看到就不加这两种选项，免得游戏建选项时拿到空文字（崩溃风险审查 2026-11-19 第 17 条）；挂上了就删掉。
    dll\\dark_lock 不在（没装 / 停用了）就不管"""
    d = os.path.join(ctx.UserDllDir, 'dark_lock')
    if not os.path.isdir(d):
        return
    p = os.path.join(d, 'no_menu_text.txt')
    if Loaded:
        _remove_file(p)
        return
    try:
        core.write_text(p, '这次启动游戏脚本覆盖包没有加载（启动器写的，下次加载上了会删掉）：物品菜单里不加「锁定 / 送给」\r\n')
    except OSError as e:
        host('  写不了 ' + p + '：' + str(e))


def get_menu_line(ctx):
    """Get-MenuLine：菜单覆盖包（reroll\\menu.py）：自制状态图标（buff 图标）、生成装备的稀有度边框图标。从本机游戏 Data0 里的原版菜单文件合成到 out\\menu
    （只读游戏文件，没变就沿用上次的）；返回要追加的 [mod] 行（失败返回空，照常启动，只是没有自制图标）"""
    from .pytool import find_python, invoke_py_json, write_py_errors
    if not os.path.exists(ctx.MenuTool):
        return ''
    py = find_python(ctx)
    gr = gamepath.resolve_game_root(ctx)
    if not py or not gr:
        write_warn('找不到 Python 或游戏目录，这次不加载自制状态图标。')
        return ''
    game = os.path.join(gr, 'Game')
    r = invoke_py_json(ctx, py, ['-X', 'utf8', ctx.MenuTool, '--out', ctx.MenuPack, '--game', game, '--dll-dir', ctx.RandomDir, '--dll-dir', game])
    if _true(r) and _true(_g(r, 'ok')):
        write_ok('菜单：' + _s(_g(r, 'msg')))
        line = '\r\nDR_Menu=' + ctx.MenuPack
        # 标题封面（menu.py 做的两个小包，普通 / 死亡以上）：标题画面一启动就读进来，进了存档换不了，所以按启动时定的难度挂（ctx.TitleCover，invoke_launch 里定）
        cover = getattr(ctx, 'TitleCover', None) or 'normal'
        title = _g(r, 'title')
        tp = _g(title, cover) if _true(title) and isinstance(title, dict) else None
        if _true(tp):
            line += '\r\nDR_Title=' + _s(tp)
            host('  标题封面   : ' + ('死亡以上（魇火、咒痕）' if core.ieq(cover, 'hard') else '普通（熔炉）'))
        return line
    write_warn('菜单覆盖包合成失败，这次不加载（词条的叠层图标显示成原版的样子或不显示，生成装备照原版图标、没有稀有度边框）：' +
               (_s(_g(r, 'msg')) if _true(r) else '没有输出'))
    write_py_errors(ctx)
    return ''


# ---------------------------------------------------------------- 玩家自己加的 mod、写 YAFSML.ini
def get_player_load(ctx):
    """Get-PlayerLoad：玩家自己加的（usermods）：mods\\ 文件夹里的 mod、YAFSML自定义.ini 的 [mod] / [mod_after] / [dll]；出错不耽误启动。
    记在 ctx.PlayerLoad（join_dll_lines 读），给玩家看加载了哪些、有什么问题"""
    from .usermods import get_user_load_lines, new_user_ini
    ctx.PlayerLoad = Rec(Before='', After='', Dll='', Mods=[], Notes=[])
    try:
        new_user_ini(ctx)
        ctx.PlayerLoad = get_user_load_lines(ctx)
    except Exception as e:
        write_player_warn('读 mods 文件夹 / YAFSML自定义.ini 出错，这次不加载自己加的 mod：' + str(e))
        return ctx.PlayerLoad
    mods = [_s(x) for x in _list(_g(ctx.PlayerLoad, 'Mods'))]
    if mods:
        write_player('自己加的 mod：' + '、'.join(mods))
    for n in _list(_g(ctx.PlayerLoad, 'Notes')):
        write_player_warn(_s(n))
    return ctx.PlayerLoad


def write_ini_file(ctx, ModLines, DllLines):
    """Write-IniFile：按模板写 yafsml\\YAFSML.ini（UTF-8 无 BOM，换行统一成 CRLF；YAFSML 的 DLL 读它）"""
    from .usermods import merge_user_ini_settings
    if not os.path.exists(ctx.TplPath):
        raise RuntimeError('缺少模板：' + ctx.TplPath)
    ModLines = _s(ModLines)
    # 玩家的 mod 排在整合包前面（同名文件以整合包为准）；也给游戏脚本合并当来源（按加载顺序取最后生效的那份，和 YAFSML 一样）
    pl = get_player_load(ctx)
    if _true(_g(pl, 'Before')):
        ModLines = _s(_g(pl, 'Before')) + '\r\n' + ModLines
    sl = get_scripts_line(ctx, ModLines)
    set_lock_text_marker(ctx, bool(sl))
    write_progress_bar(97)
    ml = get_menu_line(ctx)
    write_progress_bar(100)
    ModLines = ModLines + sl + ml
    if _true(_g(pl, 'After')):
        ModLines = ModLines + '\r\n' + _s(_g(pl, 'After'))      # YAFSML自定义.ini 的 [mod_after]：最后加载，同名文件以它为准
    DllLines = join_dll_lines(ctx, DllLines)
    tpl = read_all_text(ctx.TplPath)
    out = tpl.replace('@MOD_LINES@', ModLines).replace('@DLL_LINES@', DllLines)
    # YAFSML自定义.ini 的 [patch] [tweak] [log] 等：替换模板里同名的设置（存档 / 内存相关的不让改）
    try:
        mg = merge_user_ini_settings(ctx, out)
        out = _s(_g(mg, 'Text'))
        for a in _list(_g(mg, 'Applied')):
            host('  自定义设置：' + _s(a))
        for n in _list(_g(mg, 'Notes')):
            write_player_warn(_s(n))
    except Exception as e:
        write_player_warn('YAFSML自定义.ini 的设置没用上（读的时候出错）：' + str(e))
    out = re.sub(r'\r?\n', '\r\n', out)
    core.write_text(ctx.YafIni, out)
    write_ok('已生成配置：' + ctx.YafIni)


def show_ini_dry(ctx, ModLines, DllLines):
    """Show-IniDry：-DryRun 时只打印要写进 YAFSML.ini 的 [mod] / [dll]，再看看各个包在不在"""
    ModLines = _s(ModLines)
    write_head('DRY-RUN：即将写入 yafsml\\YAFSML.ini 的 [mod] / [dll]')
    pl = get_player_load(ctx)
    host('[mod]')
    if _true(_g(pl, 'Before')):
        _hostm(_g(pl, 'Before'))
    _hostm(ModLines)
    host('DR_Scripts=' + ctx.ScriptsPack + '   （启动时合并生成）')
    host('DR_Menu=' + ctx.MenuPack + '   （启动时从原版菜单文件合成）')
    if _true(_g(pl, 'After')):
        _hostm(_g(pl, 'After'))
    host('[dll]')
    _hostm(join_dll_lines(ctx, DllLines))
    host('')
    host('路径检查：')
    for line in re.split(r'\r?\n', ModLines):
        m = re.search(r'^\s*(DR_\w+)\s*=\s*(.+)$', line, re.I)
        if m:
            k = m.group(1)
            v = m.group(2).strip()
            host('  ' + k + ' -> ' + v + '  (存在=' + ('True' if os.path.exists(v) else 'False') + ')')


# ---------------------------------------------------------------- 启动游戏
# 以前 YAFSML 第一次启动（yafsml\cache 为空，或游戏更新后）会先「预热」一次：先启动一次只建 BootBoost 缓存再关掉，
# 因为那时候缓存现场建的那一局读档会崩在 YAFSML.dll 里。2026-10-30 用 YAFSML 0.10.4 测过缓存全空直接启动：
# 7 个缓存当场建好、文字包和 regulation 都覆盖上了、读档进地图不闪退，所以去掉了预热。
# 游戏在跑时不启动（不替玩家结束游戏：可能正在存档）。上次崩溃 / 退出时卡住、窗口没了进程还在的，让玩家自己在任务管理器里结束
GameRunningMsg = ('游戏还在运行。先在游戏里正常退出（系统 → 退出游戏），等游戏完全关闭后再启动。'
                  '如果游戏已经关了还这样提示（上次没退干净，后台还留着），打开任务管理器结束 eldenring.exe 再启动。')


def stop_elden_ring(ctx=None):
    """Stop-EldenRing：结束 eldenring.exe，最多等 10 秒（每 0.5 秒看一次）"""
    pids = win.find_pids('eldenring')
    if not pids:
        return
    for pid in pids:
        try:
            win.kill_pid(pid)
        except OSError:
            pass
    for _ in range(20):
        _sleep(0.5)
        if not win.find_pids('eldenring'):
            break


def save_run_logs(ctx, Mode):
    """Save-RunLogs：启动前整理日志：
    - 每次启动都重写的日志（dark_ui、souls_vision）上一次的就没了：先复制一份到 launcher\\logs\\dll_runs
      （文件名前面是那份日志最后写入的时间，每种留最近 10 份），诊断包会带上；
    - 一直往后追加的日志（各 DLL、YAFSML、随机器的 CrashFix）超过 2 MB 就挪成 <文件名>.old（只留一份），免得越积越大；
    - 幻化插件每天一个日志，只留最近 14 天；
    - YAFSML.log 自己不写时间：先追加一行分隔（时间 + 启动方式），分得清哪几行是哪次启动的"""
    grow = [os.path.join(ctx.UserDllDir, x) for x in AppendLogs] + [ctx.RandomLog, os.path.join(ctx.RandomDir, 'dll\\RandomizerCrashFix_log.txt')]
    for f in grow:
        try:
            n = _get_item_size(f)
            if n is not None and n > 2 * 1024 * 1024:
                os.replace(f, f + '.old')
        except OSError:
            pass
    old = datetime.datetime.now() - datetime.timedelta(days=14)
    for _n, full in ls(os.path.join(ctx.UserDllDir, 'logs'), 'ertransmogrify_*.log', 'file'):
        try:
            if _mtime(full) < old:
                _remove_file(full)
        except OSError:
            pass
    try:
        os.makedirs(os.path.dirname(ctx.RandomLog), exist_ok=True)
        with open(ctx.RandomLog, 'ab') as fh:
            fh.write(('==== ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' 暗黑重铸 启动（' + _s(Mode) + '）====' + '\r\n').encode('utf-8'))
    except OSError:
        pass
    for f in (os.path.join(ctx.UserDllDir, 'dark_ui\\dark_ui.log'), os.path.join(ctx.UserDllDir, 'souls_vision.log')):
        try:
            n = _get_item_size(f)
            if not n:
                continue
            name = os.path.basename(f)
            os.makedirs(ctx.RunLogDir, exist_ok=True)
            shutil.copy2(f, os.path.join(ctx.RunLogDir, _mtime(f).strftime('%Y%m%d_%H%M%S') + '_' + name))
            keep = win.culture_sorted(ls(ctx.RunLogDir, '*_' + name, 'file'), key=lambda x: x[0], reverse=True)
            for _n, full in keep[10:]:
                _remove_file(full)
        except OSError:
            pass


# 游戏目录 Game\ 顶层的这些文件会被游戏当成系统 DLL 先加载（别的 mod 加载器、ReShade、补帧 / 超分类 mod 常用的「代理」文件名）：
# 和整合包一起就是同一个游戏里再加载一套 mod（再来一份 Seamless Co-op 或 ErdTools 必出事）。原版游戏、整合包、YAFSML、Seamless Co-op
# 都不往 Game\ 放这些（2026-11-19 核对：原版 Game\ 顶层只有 amd_ags_x64 / bink2w64 / eossdk / oo2core / steam_api64）
ProxyDllNames = ('dinput8.dll', 'dxgi.dll', 'd3d11.dll', 'd3d12.dll', 'winmm.dll', 'version.dll', 'dsound.dll', 'winhttp.dll',
                 'xinput1_3.dll', 'xinput1_4.dll')
# 画面类（ReShade、补帧 / 超分）常用的名字：很多玩家长期开着，联机也只提示不拦；拦的是 mod 加载器常用的其余几个名字
GraphicsProxyNames = ('dxgi.dll', 'd3d11.dll', 'd3d12.dll')


def find_proxy_dlls(game_dir):
    """Game\\ 顶层的代理 DLL（实际的文件名）；读不了目录返回 []"""
    try:
        names = os.listdir(game_dir)
    except OSError:
        return []
    want = {n.casefold() for n in ProxyDllNames}
    return sorted((n for n in names if n.casefold() in want and os.path.isfile(os.path.join(game_dir, n))), key=str.casefold)


def test_game_dir_proxies(ctx, er_root, Coop):
    """启动前看 Game\\ 顶层有没有别的 mod 留下的代理 DLL（崩溃风险审查 2026-11-19 第 16 条）：单机提示一句照常启动；联机不启动。
    同一个游戏目录一次启动只看一次。返回能不能启动"""
    game_dir = os.path.join(er_root, 'Game')
    if getattr(ctx, 'ProxyChecked', '') == game_dir:
        return True
    ctx.ProxyChecked = game_dir
    found = find_proxy_dlls(game_dir)
    if not found:
        return True
    names = '、'.join(found)
    host('  游戏目录 ' + game_dir + ' 顶层有代理 DLL：' + names)
    gfx = {n.casefold() for n in GraphicsProxyNames}
    if Coop and all(n.casefold() in gfx for n in found):
        write_player_warn('游戏的 Game 文件夹里有画面类 mod 的文件（' + names + '）。联机时如果闪退或掉线，先把它们从 Game 文件夹挪走' +
                          '（例如放进一个新建的文件夹）再试：' + game_dir)
        return True
    if Coop:
        write_err('联机启动不了：游戏的 Game 文件夹里有别的 mod 留下的文件（' + names + '），游戏会额外加载一套别的 mod，' +
                  '联机时容易掉线或闪退。把这些文件从 Game 文件夹挪走（例如放进一个新建的文件夹）再联机启动：' + game_dir)
        return False
    write_player_warn('游戏的 Game 文件夹里有别的 mod 留下的文件（' + names + '），游戏会额外加载一套别的 mod，可能闪退或者功能出错。' +
                      '不用的话把它们从 Game 文件夹挪走（例如放进一个新建的文件夹）：' + game_dir)
    return True


def _newest_pid(pids):
    """Sort-Object StartTime -Descending | Select-Object -First 1（读不到启动时间的排最后）"""
    def start(pid):
        try:
            with win.Proc(pid) as p:
                return p.start_time() or datetime.datetime.min
        except OSError:
            return datetime.datetime.min
    return sorted(pids, key=start, reverse=True)[0] if pids else None


def start_yaf_game(ctx, Mode=''):
    """Start-YafGame：核对游戏路径和版本，开 YAFSML（最小化、不等它），再等 eldenring.exe 出现（最多 60 秒）；看到了就开崩溃看守。返回游戏起来了没有"""
    if not os.path.exists(ctx.YafExe):
        write_err('找不到 YAFSML：' + ctx.YafExe)
        return False
    er_root = gamepath.resolve_game_root(ctx)
    if not er_root:
        write_warn('还没有可用的游戏路径（未设置，或自动检测到多个候选）。先选一下游戏目录：')
        if not gamepath.set_game_root_interactive(ctx):
            write_err('未选择游戏路径，取消启动。')
            return False
        er_root = gamepath.resolve_game_root(ctx, Refresh=True)
    game_exe = os.path.join(er_root, 'Game\\eldenring.exe')
    if not os.path.exists(game_exe):
        write_err('游戏路径无效（找不到 Game\\eldenring.exe）：' + er_root)
        return False
    host('  游戏：' + game_exe)
    ok_ver = getattr(ctx, 'GameVerOk', None)
    if not (ok_ver is not None and core.ieq(ok_ver, game_exe)) and not gamepath.test_game_version(ctx, game_exe):
        return False
    if not test_game_dir_proxies(ctx, er_root, bool(getattr(ctx, 'CoopDll', ''))):
        return False
    if ctx.NoLaunch:
        write_warn('[-NoLaunch] 只写配置，不启动 YAFSML。')
        return True
    # 游戏已经在跑：不再结束它（崩溃风险审查 2026-11-19 第 15 条：以前直接结束，赶上另一个启动器刚启动的游戏、或者正在存档就坏档）。
    # 以前要结束多半是为了上次没退干净的进程；invoke_launch 生成之前已经查过一次，走到这里说明是生成的这一会儿里有人又启动了游戏
    if _eldenring_running():
        write_err(GameRunningMsg)
        return False
    save_run_logs(ctx, Mode)
    # Start-Process -WindowStyle Minimized：直接启动（不经过 shell），最小化，不继承句柄，不等它。命令行照 PowerShell 拼（路径总带引号）
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 2                                  # SW_SHOWMINIMIZED
    _start('"%s" --game-path "%s"' % (ctx.YafExe, er_root), cwd=ctx.YafDir, startupinfo=si, close_fds=True)
    host('')
    host('  已启动 YAFSML，等待 eldenring.exe（最多 60 秒）...')
    write_player('正在启动游戏……')
    ok = False
    for _ in range(60):
        _sleep(1)
        if _eldenring_running():
            ok = True
            break
    if ok:
        write_ok('游戏已启动。')
        write_player('游戏已启动。')
        # 后台看守：游戏崩溃时自动导出诊断包（正常退出什么都不做）
        gp = _newest_pid(win.find_pids('eldenring'))
        if gp and start_crash_watch(ctx, gp):
            host('  如果游戏崩溃，会自动导出诊断包到「崩溃诊断」文件夹。')
    else:
        write_player_warn('60 秒内没看到游戏启动，看日志：' + ctx.RandomLog)
    host('  日志：' + ctx.RandomLog)
    return ok


# ---------------------------------------------------------------- 原版文件、重随
def get_vanilla_source(ctx, Py):
    """Get-VanillaSource：原版文件的来源（reroll\\vanilla.py）：装了随机器用它带的 diste\\Vanilla；没装（正式发布不带随机器）从玩家的游戏取：
    regulation 用 Game\\regulation.bin 并核对是不是原版，文字包从 Data0 解出来缓存。返回 Rec(Reg, Msg, From, Check, Vanilla)，
    拿不到返回 None，原因在 ctx.VanillaErr"""
    from .pytool import invoke_py_json, write_py_errors
    if getattr(ctx, 'VanillaSrc', None):
        return ctx.VanillaSrc
    a = ['-X', 'utf8', ctx.VanillaTool, 'prepare']
    gr = gamepath.resolve_game_root(ctx)
    if gr:
        a += ['--dll-dir', os.path.join(gr, 'Game')]
    r = invoke_py_json(ctx, Py, a)
    if not _true(r) or not _true(_g(r, 'ok')):
        ctx.VanillaErr = _s(_g(r, 'msg_err')) if _true(r) else '没有输出'
        write_py_errors(ctx)
        return None
    ctx.VanillaSrc = Rec(Reg=_s(_g(r, 'reg')), Msg=_s(_g(r, 'msg')), From=_s(_g(r, 'from')), Check=_s(_g(r, 'check')), Vanilla=_true(_g(r, 'vanilla')))
    return ctx.VanillaSrc


def invoke_reroll_generate(ctx, Py, Rand, Seed=None, State=''):
    """Invoke-RerollGenerate：生成重随包：基础 = 原版 / 随机器输出；文字包按语言先找随机器输出，没有就用原版；Seed 给了就用它当重随的种子
    （否则重随自己随机取）；State 给了就用它当一次性重随的记录（联机用 角色记录\\联机\\once_<种子>.json），不给是 reroll.py 默认的 角色记录\\once.json。
    重随的输出逐行转出来（打印「§% 百分比」行，图形界面画成进度条：DR_PROGRESS=1 只给它）"""
    from .pytool import run_stream
    vs = get_vanilla_source(ctx, Py)
    if not vs:
        write_err('拿不到原版文件：' + _s(getattr(ctx, 'VanillaErr', '')))
        return False
    world = getattr(ctx, 'RandWorld', None) or ctx.RandomDir         # 敌人随机：平常的世界或高难度世界（Boss 模组）
    base = os.path.join(world, 'regulation.bin') if Rand else _s(_g(vs, 'Reg'))
    a = ['-X', 'utf8', ctx.RerollTool, '--base-reg', base, '--out', ctx.RerollPack, '--dll-dir', ctx.RandomDir,
         '--label', 'rand' if Rand else 'vanilla']
    if Rand:
        a += ['--msg-src', os.path.join(world, 'msg'), '--randomizer-dir', world, '--maps-out', ctx.RerollMapsPack]
    a += ['--msg-src', _s(_g(vs, 'Msg'))]
    if Seed is not None:
        a += ['--seed', _s(Seed)]
    if State:
        a += ['--state', State]
    keys = _list(getattr(ctx, 'BossKeys', None))
    if keys:
        a += ['--boss-mods', ','.join(_s(k) for k in keys)]
    arena = _list(getattr(ctx, 'BossArena', None))
    if Rand and arena:
        a += ['--boss-arena', ','.join(_s(k) for k in arena)]
    gr = gamepath.resolve_game_root(ctx)
    if gr:
        a += ['--dll-dir', os.path.join(gr, 'Game')]
    code = run_stream(Py, a, env={'DR_PROGRESS': '1'})
    if code == 0:
        write_progress_bar(92)
    return code == 0


def get_new_game_seed(ctx, Rand):
    """Get-NewGameSeed：新开局（存档文件夹里还没有 Dark Reforged 存档）用敌人随机启动：先自动做一次一次性重随（骨灰位置、开局装备和遗物重新抽），
    种子用这台电脑现在的时间（yyyyMMddHHmmss，用户 2026-10-29）。返回要传给重随的种子；不是新开局、或者是无敌人随机，返回 None。
    只看单机存档 ER0000.rng（联机存档不算；联机启动不走这里，用联机种子）"""
    from .backup import get_rng_save_files, invoke_once_reset
    if not Rand or any(_name(f).casefold() == 'er0000.rng' for f in _list(get_rng_save_files(ctx))):
        return None
    host('  没找到暗黑重铸存档（新开局）：先重随一次物品（同「一键重随物品」），种子用当前时间。')
    invoke_once_reset(ctx)
    return int(datetime.datetime.now().strftime('%Y%m%d%H%M%S'))


def get_yaf_rel_path(ctx, Full):
    """Get-YafRelPath：文件在整合包里就写成相对 yafsml\\ 的路径（..\\dll\\...，和用户 DLL 一样），不在就写完整路径"""
    Full = _s(Full)
    if gamepath.ordinal_starts_ci(Full, ctx.Paly + '\\'):
        return '..\\' + Full[len(ctx.Paly) + 1:]
    return Full


# ---------------------------------------------------------------- Boss 模组（只在高难度加载，dev\boss_mods\README.md）
# settings.json 的 boss_mods：mode = auto（按角色难度：图形界面启动时，存档里有「死亡」以上的角色就问这次用哪种难度的世界，-BossWorld high|low；
# 没给（命令行、联机）按上次玩的角色，dark_core 记在 角色记录\boss_mode.txt，「死亡」以上才加载）/ on（一直加载）/ off（不加载，
# 和整合前完全一样）；mods = 要整合哪些（键 = launcher\reroll\data\bossmods 下的文件夹）。
# 加载 = 角色层文件（data\bossmods\<键>\files：动作 / 行为 / 模型 / AI / 音频）挂成 YAFSML 最底层（别的包都盖在它上面）+ 重随带 --boss-mods 写参数和台词。
# 游戏里换不了：Boss 的动作和 AI 是读图时从硬盘读的，只能启动时定。每次启动把这次的决定写给 dark_core（dll\dark_core\bossmods.txt），
# 读进来的角色和这次对不上时它用原版提示说要重启；off 或者一个都没开时删掉这个文件，dark_core 什么都不做。
def _boss_mode_kv(path):
    """boss_mode.txt：一行「键<Tab>值」；键不分大小写（PowerShell 的哈希表），后面的盖前面的"""
    kv = {}
    for l in read_lines_utf8(path) or []:
        i = l.find('\t')
        if i > 0:
            kv[l[:i].casefold()] = l[i + 1:]
    return kv


def get_boss_mods(ctx, Coop=False):
    """Get-BossMods：这次加载哪些 Boss 模组：Rec(Keys = 这次加载的, Want = 设置里开着的, Mode, Why = 为什么)"""
    r = Rec(Keys=[], Want=[], Mode='off', Why='')
    sp = os.path.join(ctx.LauncherDir, 'reroll', 'settings.json')
    try:
        s = _json(read_all_text(sp))
    except (OSError, ValueError):
        r.Why = '读不了设置'
        return r
    bm = _g(s, 'boss_mods') if isinstance(s, dict) else None
    if not _true(bm):
        return r
    r.Mode = _s(_g(bm, 'mode')) if isinstance(bm, dict) else ''
    want = []
    mods = _g(bm, 'mods') if isinstance(bm, dict) else None
    if _true(mods) and isinstance(mods, dict):
        for name, val in mods.items():
            if not name.startswith('_') and _eq_true(val) and os.path.exists(_jp(ctx.BossModsDir, name + '\\files')):
                want.append(name)
    r.Want = want
    if not want or core.ieq(r.Mode, 'off'):
        r.Why = '设置里关着'
        return r
    if core.ieq(r.Mode, 'on'):
        r.Keys = want
        r.Why = '设置成一直加载'
        return r
    if not Coop and core.ieq(ctx.BossWorld, 'high'):
        r.Keys = want
        r.Why = '启动时选了死亡以上难度'
        return r
    if not Coop and core.ieq(ctx.BossWorld, 'low'):
        r.Why = '启动时选了普通难度'
        return r
    # 联机：开房时选的世界，或者加入时照房主的联机码记下的（联机计划 13.3 C9、13.8）
    if Coop and os.path.exists(ctx.CoopWorldFile):
        w = read_all_text(ctx.CoopWorldFile).strip()
        if core.ieq(w, 'high'):
            r.Keys = want
            r.Why = '联机世界（开房时选的 / 照房主的联机码）：死亡以上'
            return r
        if core.ieq(w, 'low'):
            r.Why = '联机世界（开房时选的 / 照房主的联机码）：普通'
            return r
    d = os.path.join(ctx.RngRecordDir, '联机') if Coop else ctx.RngRecordDir
    rec = os.path.join(d, 'boss_mode.txt')
    if not os.path.exists(rec):
        r.Why = '还不知道角色难度（进一次游戏读档后就记下了）'
        return r
    kv = _boss_mode_kv(rec)
    who = '上次玩的角色「' + kv.get('name', '') + '」'
    if kv.get('high') == '1':
        r.Keys = want
        r.Why = who + '是「死亡」以上'
    else:
        r.Why = who + '不是「死亡」以上'
    return r


def get_title_cover(ctx, Coop=False):
    """Get-TitleCover：标题封面用哪张：这次是死亡以上的世界就是 hard。判断同 Boss 模组（启动时选的 -BossWorld，没给就看上次玩的角色），
    但不看 boss_mods 的设置：关了 Boss 模组也一样换"""
    if not Coop and core.ieq(ctx.BossWorld, 'high'):
        return 'hard'
    if not Coop and core.ieq(ctx.BossWorld, 'low'):
        return 'normal'
    if Coop and os.path.exists(ctx.CoopWorldFile):
        w = read_all_text(ctx.CoopWorldFile).strip()
        if core.ieq(w, 'high'):
            return 'hard'
        if core.ieq(w, 'low'):
            return 'normal'
    d = os.path.join(ctx.RngRecordDir, '联机') if Coop else ctx.RngRecordDir
    rec = os.path.join(d, 'boss_mode.txt')
    if not os.path.exists(rec):
        return 'normal'
    for l in read_lines_utf8(rec) or []:
        if re.match(r'high\t1', l, re.I):
            return 'hard'
    return 'normal'


def get_boss_mod_meta(ctx, Key):
    """Get-BossModMeta：bossmods\\<键>\\mod.json（解析好的 dict）；读不了返回 None"""
    try:
        return json.loads(read_all_text(_jp(ctx.BossModsDir, _s(Key) + '\\mod.json')))
    except (OSError, ValueError):
        return None


def get_boss_mod_name(ctx, Key):
    """Get-BossModName：mod.json 里 Boss 的中文名；没有用键"""
    m = get_boss_mod_meta(ctx, Key)
    zh = _g(_g(m, 'boss'), 'zh') if isinstance(m, dict) and isinstance(_g(m, 'boss'), dict) else None
    if _true(zh):
        return _s(zh)
    return Key


def write_boss_mode_def(ctx, Bm):
    """Write-BossModeDef：这次的 Boss 模组决定写给 dark_core（dll\\dark_core\\bossmods.txt，UTF-8 无 BOM、LF）；off 或一个都没开就删掉"""
    if core.ieq(_s(_g(Bm, 'Mode')), 'off') or not _list(_g(Bm, 'Want')):
        _remove_file(ctx.BossModeDef)
        return
    role = getattr(ctx, 'CoopRole', '')
    t = ('# 启动器每次启动写（dark_core 的 bossmode.rs 读）：auto = 按角色难度自动加载；loaded = 这次加载了没有；keys = 设置里开着的；' +
         'role = 联机开房 host / 加入 guest（guest 在死亡以上的世界里用普通角色也不提示重启）' + '\n' +
         'auto ' + ('1' if core.ieq(_s(_g(Bm, 'Mode')), 'auto') else '0') + '\n' + 'loaded ' + ('1' if _list(_g(Bm, 'Keys')) else '0') + '\n' +
         'keys ' + ' '.join(_s(x) for x in _list(_g(Bm, 'Want'))) + '\n' + ('role ' + role + '\n' if role else ''))
    try:
        core.write_text(ctx.BossModeDef, t)
    except OSError as e:
        write_warn('写不了 ' + ctx.BossModeDef + '：' + str(e))


# ---------------------------------------------------------------- 动作：启动
def invoke_launch(ctx, Rand, Coop=False):
    """Invoke-Launch：启动（Rand = 敌人随机，在最近一次随机器输出上做；否则在原版上做）。
    Coop = 联机启动（Seamless Co-op）：加载 ersc.dll、Erd Tools 存档扩展名换成 co2、重随用联机种子和联机专用的一次性记录（见 coop 模块）"""
    from .backup import invoke_launch_backup, move_coop_save_name
    from .pytool import find_python
    from . import randomizer
    for t in (ctx.RerollTool, ctx.ScriptsTool):
        if not os.path.exists(t):
            write_err('缺少脚本：' + t)
            return
    mode_text = ('联机 · ' if Coop else '') + ('敌人随机' if Rand else '无敌人随机')
    write_head('启动 · ' + mode_text)
    write_player('正在准备启动（' + mode_text + '）……')
    randomizer.save_pack_path(ctx)     # 记下这个整合包的位置：更新到新版本后从这里沿用敌人随机结果
    ctx.ErdSaveExt = 'co2' if Coop else 'rng'
    ctx.CoopDll = ''
    ersc = None
    if Coop:
        from .coop import find_ersc, get_ersc_version, test_ersc_settings
        ersc = find_ersc(ctx)
        if not ersc:
            write_err('没找到 Seamless Co-op。把它压缩包里的 SeamlessCoop 文件夹整个放进 ' + ctx.UserDllDir +
                      '（变成 dll\\SeamlessCoop\\ersc.dll；整合包不带 Seamless Co-op，要自己下载）。')
            return
        host('  Seamless Co-op：' + _full(ersc) + '（版本 ' + _s(get_ersc_version(ctx, ersc)) + '）')
        if not test_ersc_settings(ctx, ersc):
            return
        # 自己加的 mod 排在整合包后面、改了数值 / 地图 / 事件的不让联机（两人的游戏数据会对不上）
        from .coop import test_coop_player_mods
        if not test_coop_player_mods(ctx):
            return
        # 联机存档 2026-11-17 起叫 ER0000.rngcoop（YAFSML.ini.tpl）：还没有就从旧的 ER0000.rng.co2 复制，免得 YAFSML 从原版联机存档 ER0000.co2 复制一份新的
        if not ctx.DryRun:
            move_coop_save_name(ctx)
        ctx.CoopDll = get_yaf_rel_path(ctx, _full(ersc))
    # Boss 模组：按上次玩的角色的难度定这次加不加载（加载的挂在最前面 = 最底层）
    bm = get_boss_mods(ctx, Coop)
    keys = _list(bm.Keys)
    # 这次的世界用哪一份输出（各存各的，见 core.set_world_packs）
    core.set_world_packs(ctx, ('_coop' if Coop else '') + ('' if Rand else '_van') + ('_hi' if keys else ''))
    if Rand:
        # 敌人随机要随机器（正式发布不带，玩家自己装；重随按位置修正要读它的数据）
        rs = randomizer.get_randomizer_status(ctx)
        if not _true(_g(rs, 'Ok')):
            _multi(write_err, _g(rs, 'Msg'))
            return
        if not _true(_g(rs, 'Tested')):
            _multi(write_warn, _xcall(randomizer.get_randomizer_untested_msg, ctx))
        latest = randomizer.get_latest_random(ctx)
        if not _true(latest) or not os.path.exists(os.path.join(ctx.RandomDir, 'regulation.bin')):
            if _list(randomizer.find_old_randoms(ctx)):
                write_err('还没有随机器输出。旧版本里有敌人随机结果：在「常见问题」里点「沿用旧版本的敌人随机」（敌人和之前一样），或者「一键重随敌人」重新随机化一次。')
            else:
                write_err('还没有随机器输出。先「一键重随敌人」随机化一次。')
            return
        if _true(_g(latest, 'Merged')):
            write_err('现在的随机器输出是旧版本合并别的包做的，带着那个包的参数。先「一键重随敌人」重新随机化一次。')
            return
        # 写明沿用的是哪一次（2026-11-04 用户反馈：覆盖更新后看到重随包的「种子」，以为敌人被重新随机化了）
        ri = randomizer.get_random_info(ctx, ctx.RandomDir)
        lt = _g(latest, 'Time')
        host('  敌人随机   : 沿用 ' + lt.strftime('%Y-%m-%d %H:%M:%S') + ' 随机化的结果' +
             ('（随机器种子 ' + _s(_g(ri, 'Seed')) + '）' if _true(ri) and _true(_g(ri, 'Seed')) else '') +
             '，这次没有重新随机化；要换一批敌人点「一键重随敌人」')
        write_player('敌人随机：沿用 ' + lt.strftime('%Y-%m-%d %H:%M') + ' 随机化的结果（要换一批敌人点「一键重随敌人」）')
        if not _true(_g(latest, 'HasEnemy')) and not _true(_g(latest, 'HasItem')):
            write_warn('最近一次随机化的选项里没有 enemy（敌人随机），这样启动和无敌人随机差不多。')
        if _true(_g(latest, 'HasItem')):
            host('  物品随机   : 开着（重随认出来了：商店重抽、骨灰打乱跳过，见 dev\\item_rand\\物品随机兼容.md）')
        mod_lines = 'DR_Randomizer=' + ctx.RandomDir + '\r\n' + 'DR_RerollMaps=' + ctx.RerollMapsPack + '\r\n' + 'DR_Reroll=' + ctx.RerollPack
        dll_lines = 'randomizer_crashfix=..\\randomizer\\dll\\RandomizerCrashFix.dll|early'
    else:
        mod_lines = 'DR_Reroll=' + ctx.RerollPack
        dll_lines = '; 无敌人随机：不需要额外 DLL'
    ctx.BossKeys = list(keys)
    ctx.TitleCover = get_title_cover(ctx, Coop)
    want = _list(bm.Want)
    if want:
        names = '、'.join(_s(get_boss_mod_name(ctx, k)) for k in want)
        host('  高难度 Boss : ' + ('加载改版（' + names + '）' if keys else '不加载（' + names + ' 用原版）') + '——' + _s(bm.Why))
        if core.ieq(_s(bm.Mode), 'auto'):
            write_player('难度：' + ('死亡以上难度' if keys else '普通难度'))
    # 敌人随机：用高难度世界（一键重随敌人时随机器多跑的一遍，这些 Boss 留在原位；randomizer 的 invoke_randomize_hi_world），
    # 场地在重随 / 游戏脚本里移植上去（--boss-arena）。没有或过期（不是跟着最近这次随机化做的）就用平常的世界，Boss 不固定、只换新动作
    ctx.RandWorld = ctx.RandomDir
    ctx.BossArena = []
    if Rand and keys:
        need = []
        arena_keys = []
        for k in keys:
            m = get_boss_mod_meta(ctx, k)
            if _true(m):
                fx = _g(m, 'fixed') if isinstance(m, dict) else None
                need += [None] if fx is None else _list(fx)      # @($m.fixed)：没有 fixed 是一个 $null（get_rand_hi_world 当 0 看，和 PowerShell 一样）
                if isinstance(m, dict) and _true(_g(m, 'arena')):
                    arena_keys.append(k)
        hi = None if Coop else randomizer.get_rand_hi_world(ctx, need)
        if _true(hi):
            ctx.RandWorld = ctx.RandomHiDir
            ctx.BossArena = arena_keys
            mod_lines = mod_lines.replace('DR_Randomizer=' + ctx.RandomDir, 'DR_Randomizer=' + ctx.RandomHiDir)
            host('  敌人随机   : 用高难度世界（' + _s(_g(hi, 'time')) + ' 和平常的一起随机化的，种子 ' + _s(_g(hi, 'seed')) + '；整合了改版的 Boss 在原场地）')
        elif Coop:
            write_warn('联机先不用高难度世界：整合了改版的 Boss 不固定在原位（只换新动作）。')
        else:
            write_player_warn('还没有死亡以上难度的敌人随机世界（自己打开随机器随机化的、或者之后才开了新的 Boss 模组）：部分追忆 Boss 这次不在原位。' +
                              '点「一键重随敌人」重新随机化一次就有了。')
    if keys:
        boss_lines = ['DR_Boss_' + _s(k) + '=' + _jp(ctx.BossModsDir, _s(k) + '\\files') for k in keys]
        # 场地（新阶段的事件、新加的随从 / 物件，移植到原版地图上的成品）：只在 Boss 在原位时挂 = 不开敌人随机
        if not Rand:
            boss_lines += ['DR_BossArena_' + _s(k) + '=' + _jp(ctx.BossModsDir, _s(k) + '\\arena') for k in keys
                           if os.path.exists(_jp(ctx.BossModsDir, _s(k) + '\\arena'))]
        mod_lines = '\r\n'.join(boss_lines) + '\r\n' + mod_lines
    seed = None
    state = ''
    if Coop:
        from .coop import get_coop_seed
        seed = get_coop_seed(ctx, Rand)
        if seed is None:
            return
        state = os.path.join(os.path.join(ctx.RngRecordDir, '联机'), 'once_' + _s(seed) + '.json')
        host('  联机种子 : ' + _s(seed) + ('（= 随机器的种子：两人的敌人随机一样，种子就一样）' if Rand else '（无敌人随机固定用这个）'))
        host('  一次性重随记录（联机专用）: ' + state)
    if ctx.DryRun:
        show_ini_dry(ctx, mod_lines, dll_lines)
        write_warn('[-DryRun] 不生成覆盖包、不启动。')
        return
    # 要覆盖游戏正在用的 out\reroll 等文件
    if _eldenring_running():
        write_err(GameRunningMsg)
        return
    # 游戏版本不对：大半功能不工作，生成之前先说（游戏路径还没选好的，到 start_yaf_game 选完再核对）
    ctx.GameVerOk = ''
    gr = gamepath.resolve_game_root(ctx)
    if gr and os.path.exists(os.path.join(gr, 'Game\\eldenring.exe')):
        if not gamepath.test_game_version(ctx, os.path.join(gr, 'Game\\eldenring.exe')):
            return
        ctx.GameVerOk = os.path.join(gr, 'Game\\eldenring.exe')
        # Game\ 顶层别的 mod 留下的代理 DLL：联机在生成之前就不启动（游戏路径还没选好的，到 start_yaf_game 选完再看）
        if not test_game_dir_proxies(ctx, gr, Coop):
            return
    py = find_python(ctx)
    if not py:
        write_err('找不到 Python 3：包里自带的 ' + os.path.join(ctx.LauncherDir, 'python') + ' 不完整，系统里也没装（python.org 装 3.8 以上即可）')
        return
    # 原版文件：没装随机器时从游戏取，先核对游戏目录的 regulation.bin 是不是原版
    vs = get_vanilla_source(ctx, py)
    if not vs:
        write_err('拿不到原版文件，没有启动：' + _s(getattr(ctx, 'VanillaErr', '')))
        return
    if core.ieq(_s(_g(vs, 'From')), 'game'):
        host('  原版文件 : 从游戏取（没装随机器）；regulation.bin ' + _s(_g(vs, 'Check')))
        if not _true(_g(vs, 'Vanilla')):
            write_player_warn('游戏目录的 regulation.bin 不是整合包认识的原版：游戏更新了，或者被别的 mod 改过。被改过的话，在 Steam 里对游戏「验证游戏文件的完整性」再启动。')
    invoke_launch_backup(ctx, mode_text)
    if not Coop:
        seed = get_new_game_seed(ctx, Rand)
        if seed is not None:
            host('  这次重随的种子：' + _s(seed))
    host('')
    # 设置、整合包、随机器输出、一次性重随记录都没变时重随沿用上次的结果（launcher\reroll\rr\reuse.py），几秒就好
    if Rand:
        host('  正在生成重随包（没变就沿用上次的；要重做约 20 秒，刚重新随机化过约 25 秒）...')
    else:
        host('  正在生成重随包（没变就沿用上次的；要重做约 5 秒）...')
    write_player('正在生成这一局的游戏数据（没变化时几秒就好，要重做约 ' + ('20' if Rand else '5') + ' 秒）……')
    if not invoke_reroll_generate(ctx, py, Rand, seed, state):
        write_err('重随失败，没有启动游戏。')
        return
    core.write_text(ctx.WorldFile, ctx.WorldSuffix)     # 状态显示、诊断包读这一份
    if Coop:
        from .coop import get_coop_fingerprint, write_coop_profile
        fp = get_coop_fingerprint(ctx, Rand, True)
        if fp:
            host('  联机核对码：' + _s(fp) + '（进会话后自动和队友比对，对不上时日志里写是哪一项）')
        write_coop_profile(ctx, ersc, fp, Rand)
    else:
        _remove_file(ctx.CoopProfile)
    write_boss_mode_def(ctx, bm)
    write_ini_file(ctx, mod_lines, dll_lines)
    start_yaf_game(ctx, mode_text)


# ---------------------------------------------------------------- 状态显示
def get_reroll_last_text(ctx):
    """Get-RerollLastText：上次重随的时间和种子（重随报告的开头几行）"""
    rep = os.path.join(ctx.RerollPack, 'reroll_report.txt')
    if not os.path.exists(rep):
        return '（还没有）'
    lines = read_lines_utf8(rep, 3) or []
    t = next((l for l in lines if l.casefold().startswith('时间：')), None)
    s = next((l for l in lines if l.casefold().startswith('种子：')), None)
    s = re.sub(r'^种子：', '', s, flags=re.I) if s is not None else None
    if t is None:
        # PowerShell 里没有「时间：」那一行时 $t 是空数组，拼出来的是数组 @('（种子 ', 种子, '）')，调用的地方拼进字符串时用空格连起来：照那样返回
        return ' '.join(['（种子 '] + ([s] if s is not None else []) + ['）'])
    return re.sub(r'^时间：', '', t, flags=re.I) + '（种子 ' + (s or '') + '）'


def show_status(ctx):
    """Show-Status：状态（-Action list）：游戏路径、随机器输出、上次重随、随机器版本、联机"""
    from . import randomizer
    from .coop import find_ersc
    game_root = gamepath.resolve_game_root(ctx)
    if game_root:
        host('  游戏路径   : ' + game_root)
    else:
        host('  游戏路径   : （未设置 / 有多个候选，在图形界面点「游戏路径」选择）')
    latest = randomizer.get_latest_random(ctx)
    if _true(latest):
        if _true(_g(latest, 'Merged')):
            tag = '旧版本合并别的包做的，要重新随机化'
        elif _true(_g(latest, 'HasEnemy')):
            tag = '有敌人随机'
        elif _true(_g(latest, 'HasItem')):
            tag = '只有物品随机'
        else:
            tag = '未勾选敌人随机'
        if _true(_g(latest, 'HasItem')) and _true(_g(latest, 'HasEnemy')):
            tag += '，含物品随机'
        host('  随机器输出 : ' + _g(latest, 'Time').strftime('%Y-%m-%d %H:%M:%S') + '（' + tag + '）')
    else:
        host('  随机器输出 : （还没有）')
    host('  上次重随   : ' + get_reroll_last_text(ctx))
    rs = randomizer.get_randomizer_status(ctx)
    if not _true(_g(rs, 'Ok')):
        rt = '没装（敌人随机要自己下载，见 ' + randomizer.RandomizerUrl + '）'
    elif _true(_g(rs, 'Tested')):
        rt = _s(_g(rs, 'Version'))
    else:
        rt = '版本没测过（测过的是 v0.12.2）'
    host('  随机器     : ' + rt)
    ersc = find_ersc(ctx)
    host('  联机       : ' + ('Seamless Co-op ' + _full(ersc) if _true(ersc) else '没放 Seamless Co-op（放进 dll\\SeamlessCoop\\ 才能联机启动）'))


# ---------------------------------------------------------------- 崩溃看守
def start_crash_watch(ctx, ProcId):
    """Start-CrashWatch：游戏启动后在后台看守（游戏崩溃时自动导出诊断包）：包里的 pythonw 跑 `df.py watch --game-pid N`
    （第 4 步起看守也是 Python 的，以前是 spawn.py → launcher.ps1 -Action watch）。pythonw 本身没有窗口；不继承句柄，
    图形界面读的输出管道不会被一直开着的看守占住。以前没有 pythonw 时退回隐藏窗口的 powershell：去掉了，没有就说一声、不看守。开起来了返回 True"""
    try:
        pid = int(ProcId or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    pyw = os.path.join(ctx.LauncherDir, 'python', 'pythonw.exe')
    df = os.path.join(ctx.LauncherDir, 'df.py')
    if not (os.path.exists(pyw) and os.path.exists(df)):
        write_warn('找不到 ' + pyw + ' 或 ' + df + '，这次不开崩溃看守（游戏崩溃时不会自动导出诊断包）。')
        return False
    try:
        _start('"%s" -I "%s" watch --game-pid %d' % (pyw, df, pid), cwd=ctx.LauncherDir, close_fds=True,
               creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        return True
    except OSError:
        return False
