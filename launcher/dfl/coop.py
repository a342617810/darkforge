# -*- coding: utf-8 -*-
"""联机（Seamless Co-op；launcher.ps1 的「联机」一节，dev\\coop\\联机计划.md 阶段一）。

- ersc.dll 玩家自己放（不打包）：整合包 dll\\ 下（dll\\SeamlessCoop\\ersc.dll，连同它的 ersc_settings.ini、locale 文件夹），
  没有就用游戏目录 Game\\SeamlessCoop\\ 里的。平常启动不加载它，联机启动才加载，放 [dll] 最前面、early（launch.join_dll_lines）。
- 存档：Seamless Co-op 把存档扩展名换成 co2，YAFSML 再换成 ER0000.rngcoop（和单机的 ER0000.rng 分开）。
- 两个人的游戏数据必须一样：重随用联机种子（敌人随机 = 随机器的种子，无敌人随机 = 固定的 CoopVanillaSeed），
  一次性重随记录用 角色记录\\联机\\once_<种子>.json；敌人随机靠联机码对齐（get_coop_code3）。
- 玩家流程（2026-11-16 起）：房主「开房」（invoke_coop_host），队友「加入」（invoke_coop_join），一个联机码 DR3 带上密码、Seamless 规则、
  敌人设置、世界和启动方式。联机核对码（reroll\\coopfp.py）写进兼容档案，进会话后联机通道自动比对。

和 PowerShell 版逐字节一样的几处细节（别「顺手」改）：
- ersc_settings.ini 保持原来有没有 BOM（按字节看），按 .NET 的 ReadAllText 读（认 BOM，坏字节换成 U+FFFD）；
- .Trim()、-replace '\\s+'、-split '\\s+' 用 .NET 的空白（不含 \\x1c~\\x1f，和 Python 的 str.strip 不一样）；
- ToString('0.###')：先取 15 位有效数字再四舍五入（远离零），1.0 → "1"；字符串拼 double 是 15 位有效数字的 G 格式；
- ConvertFrom-Json 读出的数字拼进字符串时照原来的写法（1.50 还是 "1.50"，1e2 是 "100"）；
- -eq / -match / -in / 哈希表的键不分大小写，.StartsWith / -cne 分大小写。"""
import base64
import datetime
import json
import os
import re
import secrets
import shutil
import stat
import struct
import subprocess
from decimal import ROUND_HALF_UP, Decimal, localcontext

from . import win
from .core import Rec, host, write_err, write_head, write_ok, write_player, write_warn

# ---------------------------------------------------------------- 常量（launcher.ps1 里的名字照抄）
CoopVanillaSeed = 20261102
# Seamless Co-op 的版本（联机计划 13.9 B）：ersc.dll 的 PE 时间戳 + 镜像大小；认得的写版本号（特征照黄金树爬塔记的），认不出写原始数值
ErscKnown = {'6ae0ad1a:d65000': '2.0.2', '6af4b20a:d67000': '2.0.3'}
# PowerShell 的 [CultureInfo]::InvariantCulture：Python 的数字格式本来就不看区域，留着名字对照
CoopInv = 'InvariantCulture'
# 联机码和兼容档案里带的 Seamless 规则（不含密码）
CoopRuleKeys = ['allow_summons', 'boss_damage_scaling', 'boss_health_scaling', 'boss_posture_scaling', 'death_debuffs',
                'enemy_damage_scaling', 'enemy_health_scaling', 'enemy_posture_scaling']

# ---------------------------------------------------------------- .NET 语义的小工具（只给这个模块用）
# .NET 的空白（Char.IsWhiteSpace = 正则的 \s）：\t~\r、空格、\x85、\xa0 和 Unicode 的 Zs / Zl / Zp
_NET_WS = '\t\n\x0b\x0c\r \x85\xa0                　'
_S = '[\\t\\n\\x0b\\x0c\\r \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]'
_S_RUN = re.compile(_S + '+')


def _trim(s):
    """.Trim()"""
    return (s or '').strip(_NET_WS)


def _trim_end(s):
    """.TrimEnd()"""
    return (s or '').rstrip(_NET_WS)


def _squash(s):
    """([string]$Text -replace '\\s+', ' ').Trim()：聊天软件折了行、加了空格的码连回一行"""
    return _trim(_S_RUN.sub(' ', s or ''))


def _ieq(a, b):
    """-eq（字符串不分大小写；$null 只等于 $null）"""
    if a is None or b is None:
        return a is None and b is None
    return str(a).casefold() == str(b).casefold()


def _iin(a, items):
    """-in / -contains（不分大小写）"""
    return any(_ieq(a, x) for x in items)


def _count(x):
    """@(...).Count"""
    if x is None:
        return 0
    if isinstance(x, (list, tuple)):
        return len(x)
    return 1


def _decode_net(raw):
    """[IO.File]::ReadAllText 不给编码：认 BOM（UTF-8 / UTF-16 / UTF-32），没有按 UTF-8，坏字节换成 U+FFFD"""
    if raw[:4] == b'\xff\xfe\x00\x00':
        return raw[4:].decode('utf-32-le', 'replace')
    if raw[:3] == b'\xef\xbb\xbf':
        return raw[3:].decode('utf-8', 'replace')
    if raw[:2] == b'\xff\xfe':
        return raw[2:].decode('utf-16-le', 'replace')
    if raw[:2] == b'\xfe\xff':
        return raw[2:].decode('utf-16-be', 'replace')
    if raw[:4] == b'\x00\x00\xfe\xff':
        return raw[4:].decode('utf-32-be', 'replace')
    return raw.decode('utf-8', 'replace')


def _read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def _read_all_text(path):
    return _decode_net(_read_bytes(path))


def _has_bom(raw):
    return raw[:3] == b'\xef\xbb\xbf'


def _write_all_text(path, text, bom=False):
    """[IO.File]::WriteAllText(path, text, UTF8Encoding($bom))：换行原样"""
    with open(path, 'wb') as f:
        f.write((b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8'))


def _stamp():
    """Get-Date -Format 'yyyyMMdd_HHmmss'（备份文件名；测试时换成固定的）"""
    return datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


def _copy_force(src, dst):
    """Copy-Item -LiteralPath src -Destination dst -Force（目标只读也覆盖）"""
    try:
        shutil.copy2(src, dst)
    except PermissionError:
        if os.path.isfile(dst):
            os.chmod(dst, stat.S_IWRITE)
            shutil.copy2(src, dst)
        else:
            raise


def _backup_once(path, tag):
    """改 ini 之前备份成 <ini>.<tag>_<时间>。同一秒里已经备份过（上一项刚改完）就不再盖：留下的是改之前最原始的那份。
    以前（PowerShell 版）每改一项都覆盖一次，同一秒改两三项时，备份里已经是改过一项的设置（2026-11-18 移植时修）"""
    dst = path + '.' + tag + '_' + _stamp()
    if not os.path.exists(dst):
        _copy_force(path, dst)


def _msg(e):
    """$_.Exception.Message 的替身（.NET 和 Python 的报错文字本来就不一样）"""
    return str(e) or e.__class__.__name__


def _fmt3(x):
    """$x.ToString('0.###', InvariantCulture)：.NET Framework 先取 15 位有效数字，再按小数第 4 位四舍五入（远离零）；
    整数不带小数点（1.0 → "1"），舍成 0 的负数不带负号"""
    x = float(x)
    with localcontext() as c:
        c.prec = 400
        d = Decimal(format(abs(x), '.14e')).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        if d == 0:
            return '0'
        s = format(d, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return ('-' if x < 0 else '') + s


def _g15(x):
    """[string]$double（PowerShell 5.1 = .NET Framework 的 ToString()：15 位有效数字的 G 格式）；-0 写成 0"""
    s = format(float(x), '.15G')
    return '0' if s == '-0' else s


class _JNum(str):
    """ConvertFrom-Json（PowerShell 5.1 的 JavaScriptSerializer）读出的数字：记下原来的写法，拼进字符串时照 .NET 的类型转"""


def _jnum_str(lit):
    """没有指数：Int32 / Int64 / decimal，写出来就是原来的写法（decimal 保留小数位，1.50 → "1.50"；负零不带负号）；
    有指数（或者超出 decimal）：double，15 位有效数字"""
    if 'e' not in lit.lower():
        neg = lit.startswith('-')
        body = lit[1:] if neg else lit
        if '.' not in body:
            v = int(body)
            if v == 0:
                return '0'
            if v < 79228162514264337593543950336:     # decimal 的上限
                return ('-' if neg else '') + str(v)
        else:
            ip, _, fp = body.partition('.')
            if len((ip + fp).lstrip('0')) <= 28:
                if not (ip + fp).strip('0'):
                    return body
                return ('-' if neg else '') + body
    return _g15(float(lit))


def _json_pairs(pairs):
    """键不分大小写：只差大小写的两个键 PowerShell 5.1 报错；完全一样的后面的算数"""
    out = {}
    seen = {}
    for k, v in pairs:
        f = k.casefold()
        if f in seen and seen[f] != k:
            raise ValueError('duplicated keys ' + seen[f] + ' / ' + k)
        seen[f] = k
        out[k] = v
    return out


def _ps_json(text):
    """$text | ConvertFrom-Json：空的 / 只有空白返回 None；不合法抛异常"""
    if not _trim(text):
        return None
    return json.loads(text, parse_int=_JNum, parse_float=_JNum, object_pairs_hook=_json_pairs)


def _prop(obj, name):
    """$obj.name（不分大小写；不是对象 / 没有这个属性 = $null）"""
    if not isinstance(obj, dict):
        return None
    for k, v in obj.items():
        if k.casefold() == name.casefold():
            return v
    return None


def _ps_str(v):
    """字符串拼接时的转换（'a' + $v）"""
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, _JNum):
        return _jnum_str(str(v))
    if isinstance(v, float):
        return _g15(v)
    if isinstance(v, list):
        return 'System.Object[]'
    return str(v)


def _u16_head(s, n):
    """.Substring(0, n)（按 UTF-16 算长度；切在代理对中间时那半个字输出成 U+FFFD）"""
    b = s.encode('utf-16-le', 'surrogatepass')
    if len(b) <= 2 * n:
        return s
    t = b[:2 * n].decode('utf-16-le', 'surrogatepass')
    if t and 0xD800 <= ord(t[-1]) <= 0xDBFF:
        t = t[:-1] + '�'
    return t


def _u16_len(s):
    return len(s.encode('utf-16-le', 'surrogatepass')) // 2


def _is_hidden(entry):
    try:
        return bool(entry.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
    except (OSError, AttributeError):
        return False


def _ls(d, dirs):
    """Get-ChildItem -LiteralPath d -File / -Directory（不带 -Force：隐藏的不算；顺序就是文件系统给的顺序）；目录不在返回 []"""
    out = []
    try:
        it = os.scandir(d)
    except OSError:
        return out
    with it:
        for e in it:
            try:
                if e.is_dir() != dirs:
                    continue
            except OSError:
                continue
            if _is_hidden(e):
                continue
            out.append(e)
    return out


def _ext(name):
    """FileInfo.Extension（最后一个点起；没有点是空的）"""
    i = name.rfind('.')
    return name[i:] if i >= 0 else ''


def _file_rec(path):
    """Get-Item / Get-ChildItem 得到的 FileInfo 的替身：FullName、DirectoryName、Name、Length"""
    full = os.path.abspath(path)
    try:
        n = os.path.getsize(full)
    except OSError:
        n = None
    return Rec(FullName=full, DirectoryName=os.path.dirname(full), Name=os.path.basename(full), Length=n)


def _from_b64(s):
    """[Convert]::FromBase64String（.NET Framework：中间的空格、Tab、换行不管；长度要是 4 的倍数，= 只能在最后、最多两个）"""
    t = re.sub(r'[ \t\r\n]', '', s)
    if len(t) % 4 or not re.fullmatch(r'[A-Za-z0-9+/]*={0,2}', t):
        raise ValueError('Base-64 格式不对')
    return base64.b64decode(t)


# ---------------------------------------------------------------- 找 Seamless Co-op
def find_ersc(ctx):
    """Find-Ersc：整合包 dll\\ 和下一层文件夹（_ 开头的不算），再看游戏目录 Game\\SeamlessCoop\\；返回 ersc.dll 的文件记录（_file_rec），没有返回 None"""
    from .gamepath import resolve_game_root
    cands = []
    if os.path.exists(ctx.UserDllDir):
        cands += [_file_rec(e.path) for e in _ls(ctx.UserDllDir, False) if e.name.casefold() == 'ersc.dll']
        for d in win.culture_sorted(_ls(ctx.UserDllDir, True), key=lambda e: e.name):
            if d.name.startswith('_'):
                continue
            cands += [_file_rec(e.path) for e in _ls(d.path, False) if e.name.casefold() == 'ersc.dll']
    gr = resolve_game_root(ctx)
    if gr:
        g = os.path.join(gr, 'Game\\SeamlessCoop\\ersc.dll')
        if os.path.exists(g):
            cands.append(_file_rec(g))
    return cands[0] if cands else None


def get_ini_match(Text, Key):
    """Get-IniMatch：ini 里某一项（key = value，分号后是注释）：返回正则匹配（group(1) 是值），没有返回 None"""
    return re.search(r'(?im)^[ \t]*' + re.escape(Key) + r'[ \t]*=[ \t]*([^\r\n;]*)', Text or '')


def _splice(text, m, value):
    """$txt.Substring(0, g.Index) + value + $txt.Substring(g.Index + g.Length)"""
    return text[:m.start(1)] + value + text[m.end(1):]


def test_ersc_settings(ctx, Ersc):
    """Test-ErscSettings：Seamless Co-op 的配置（ersc.dll 旁边的 ersc_settings.ini）：
      save_file_extension 必须是 co2（YAFSML 再换成 .rngcoop）→ 不是就改（原 ini 备份）；
      随人数加强（血量、架势、伤害，以主机的为准）会叠在整合包的敌人血量上 → 打印出来提醒；
      联机密码（cooppassword）空的不让启动：Seamless Co-op 2.0.1 会弹「Please enter a session password」然后整个游戏退出（2026-11-02 实测）。
      入侵（allow_invaders）关掉、死后一直观战（always_spectate_on_death）打开（斗技场试炼联机，联机计划 13.13）。
    返回能不能联机启动。
    每改一项备份一次；同一秒里改好几项时只留第一次的备份（_backup_once）"""
    ini = os.path.join(Ersc.DirectoryName, 'ersc_settings.ini')
    if not os.path.exists(ini):
        write_err('Seamless Co-op 缺少 ersc_settings.ini（应该和 ersc.dll 放在一起）：' + Ersc.DirectoryName)
        return False
    try:
        raw = _read_bytes(ini)
        bom = _has_bom(raw)
        txt = _decode_net(raw)
        m = get_ini_match(txt, 'save_file_extension')
        ext = _trim(m.group(1)) if m else ''
        if not _ieq(ext, 'co2'):
            if ctx.DryRun:
                write_warn('Seamless Co-op 的存档扩展名是「' + ext + '」，真的启动时会改成 co2：' + ini)
            else:
                _backup_once(ini, 'bak')
                if m:
                    txt = _splice(txt, m, 'co2')
                else:
                    txt = _trim_end(txt) + '\r\n\r\n[SAVE]\r\nsave_file_extension = co2\r\n'
                _write_all_text(ini, txt, bom)
                write_warn('Seamless Co-op 的存档扩展名是「' + ext + '」，已改成 co2（联机存档是 ER0000.rngcoop，和单机存档分开；原 ini 已备份）：' + ini)
        # 入侵关掉（联机计划 13.2 G7）：入侵者的游戏数据和我们对不上，Seamless 的反作弊按什么限制匹配也看不到
        inv = get_ini_match(txt, 'allow_invaders')
        if inv and not _ieq(_trim(inv.group(1)), '0'):
            if ctx.DryRun:
                write_warn('Seamless Co-op 开着入侵（allow_invaders），真的启动时会关掉：' + ini)
            else:
                _backup_once(ini, 'bak')
                txt = _splice(txt, inv, '0')
                _write_all_text(ini, txt, bom)
                write_player('联机时不开放入侵：已把 Seamless Co-op 设置里的入侵关掉（整合包的数据和别的玩家对不上，入侵会出问题）。')
        # 死后一直观战（联机计划 13.13，照黄金树爬塔）：斗技场试炼倒下的队员留在竞技场里观战，队友接着打
        spec = get_ini_match(txt, 'always_spectate_on_death')
        if spec and not _ieq(_trim(spec.group(1)), '1'):
            if ctx.DryRun:
                write_warn('Seamless Co-op 的死后观战（always_spectate_on_death）不是 1，真的启动时会改成 1：' + ini)
            else:
                _backup_once(ini, 'bak')
                txt = _splice(txt, spec, '1')
                _write_all_text(ini, txt, bom)
                write_player('联机时倒下了会观战队友，直到所有人都倒下或者有人在赐福休息：已把 Seamless Co-op 设置里的死后观战打开。')
        # 中文（用户 2026-11-17「先把无缝联机的汉化做了」）：launcher\ersc_locale\*.json 复制进 Seamless Co-op 的 locale 文件夹（不一样才复制）。
        # Steam 语言是简体中文、mod_language_override 空着时再填上 schinese 保险
        if not ctx.DryRun:
            install_ersc_locale(ctx, Ersc)
            lo = get_ini_match(txt, 'mod_language_override')
            if lo and not _trim(lo.group(1)):
                from .gamepath import get_steam_game_language
                if _ieq(get_steam_game_language(ctx), 'schinese') and os.path.exists(os.path.join(Ersc.DirectoryName, 'locale\\schinese.json')):
                    txt = _splice(txt, lo, 'schinese')
                    _write_all_text(ini, txt, bom)
                    host('  Seamless Co-op 的语言设成简体中文（mod_language_override = schinese）')
        sc = []
        for k, label in (('enemy_health_scaling', '小怪血量'), ('boss_health_scaling', 'Boss 血量'), ('enemy_posture_scaling', '小怪架势'),
                         ('boss_posture_scaling', 'Boss 架势'), ('enemy_damage_scaling', '小怪伤害'), ('boss_damage_scaling', 'Boss 伤害')):
            v = get_ini_match(txt, k)
            if v:
                sc.append(label + ' +' + _trim(v.group(1)) + '%')
        if sc:
            host('  Seamless Co-op 随人数加强（以主机的设置为准，每多一个玩家）：' + '，'.join(sc))
            host('  整合包的敌人血量已经比原版高很多，再叠这里的加血会很肉；主机觉得太肉可以把 ersc_settings.ini 里的 boss_health_scaling、enemy_health_scaling 调低。')
        pw = get_ini_match(txt, 'cooppassword')
        if not pw or not _trim(pw.group(1)):
            msg = ('ersc_settings.ini 里的联机密码（cooppassword）是空的，Seamless Co-op 会报错并让游戏退出。在启动器「联机」里点「开房」会自动生成一个；'
                   '或者在 cooppassword = 后面自己填一个（两个人填一样的）：' + ini)
            if ctx.DryRun:
                write_warn(msg)
            else:
                write_err(msg)
                return False
        return True
    except Exception as e:
        write_err('检查 Seamless Co-op 的配置失败，没有启动：' + _msg(e))
        return False


def install_ersc_locale(ctx, Ersc):
    """Install-ErscLocale：launcher\\ersc_locale 里的语言文件（schinese.json）复制进 Seamless 的 locale 文件夹，内容不一样才复制"""
    try:
        dst = os.path.join(Ersc.DirectoryName, 'locale')
        for f in [e for e in _ls(ctx.ErscLocaleDir, False) if e.name.casefold().endswith('.json')]:
            to = os.path.join(dst, f.name)
            if os.path.exists(to) and _read_bytes(to) == _read_bytes(f.path):      # Get-FileHash 一样
                continue
            os.makedirs(dst, exist_ok=True)
            _copy_force(f.path, to)
            host('  Seamless Co-op 中文：' + f.name + ' 已放进 ' + dst)
    except Exception as e:
        write_warn('Seamless Co-op 的中文没放进去：' + _msg(e))


def get_ersc_version(ctx, Ersc):
    """Get-ErscVersion：ersc.dll 的 PE 时间戳 + 镜像大小 → 认得的写「2.0.2（6ae0ad1a:d65000）」，认不出写原始数值和文件大小；读不了返回 ''。
    和 .NET 一样读前 4096 字节（文件短的后面当 0），位置越界才算读不了"""
    try:
        with open(Ersc.FullName, 'rb') as f:
            b = f.read(4096)
        b = b.ljust(4096, b'\0')
        pe = struct.unpack_from('<i', b, 0x3C)[0]
        if pe + 8 < 0 or pe + 80 > 4092:                   # BitConverter.ToUInt32 越界
            return ''
        ts = struct.unpack_from('<I', b, pe + 8)[0]
        soi = struct.unpack_from('<I', b, pe + 24 + 56)[0]
        key = '%08x:%x' % (ts, soi)
        for k, v in ErscKnown.items():
            if _ieq(k, key):
                return v + '（' + key + '）'
        return '未知（' + key + '，' + _ps_str(Ersc.Length) + ' 字节）'
    except Exception:
        return ''


def write_coop_profile(ctx, Ersc, Fp, Rand):
    """Write-CoopProfile：联机兼容档案（联机计划 13.4）：联机启动时写给 dark_core，联机通道（dev\\dark_core\\src\\link.rs）握手时发给队友逐项比对。
    一行「键<Tab>值」：整合包版本、联机核对码、世界、Seamless 的随人数加强和规则（不含密码）、敌人设置。改了键名要和 link.rs 的 LABELS 一起改。
    UTF-8 无 BOM、LF"""
    try:
        ver = get_coop_pack_version(ctx)
        rules = list(get_ersc_rules(ctx, Ersc))
        enemy = ''
        try:
            s = _ps_json(_read_all_text(os.path.join(ctx.LauncherDir, 'reroll\\settings.json')))
            enemy = 'elite_share_mult=' + _ps_str(_prop(s, 'elite_share_mult')) + ',boss_in_basic_pct=' + _ps_str(_prop(s, 'boss_in_basic_pct'))
        except Exception:
            pass
        lines = ['# 联机兼容档案：启动器联机启动时写，dark_core 的联机通道握手时发给队友比对（不含联机密码）',
                 'version\t' + ver, 'fingerprint\t' + (Fp or ''), 'world\t' + (getattr(ctx, 'WorldSuffix', '') or ''),
                 'scaling\t' + ','.join(rules), 'enemy\t' + enemy, 'seamless\t' + get_ersc_version(ctx, Ersc),
                 # 自己加的 mod（崩溃风险审查 2026-11-19 第 12 条）：名字 + 文件清单，两边不一样时联机通道的日志里写是哪几个
                 'mods\t' + (', '.join(m.Label + '#' + m.Hash for m in get_player_mod_list(ctx)) or '无')]
        # 联机码（不算比对的一项；DR3 带着联机密码，只发给会话里的队员）：队友和房主对不上时，联机通道把房主的存到队友的
        # dll\dark_core\coop_host_code.txt，队友退出后点「加入」剪贴板里没有码也能用它
        try:
            cc = get_coop_code3(ctx, Rand, Ersc)
            if cc.Ok:
                lines.append('code\t' + cc.Code)
        except Exception:
            pass
        _write_all_text(ctx.CoopProfile, '\n'.join(lines) + '\n')
        host('  联机兼容档案：' + ctx.CoopProfile)
    except Exception as e:
        write_warn('写不了联机兼容档案（联机通道握手时不比对）：' + _msg(e))


def get_coop_seed(ctx, Rand):
    """Get-CoopSeed：敌人随机 = 随机器的种子（两人用联机码对齐了敌人随机，种子就一样），无敌人随机 = 固定的 CoopVanillaSeed；读不到返回 None"""
    if not Rand:
        return CoopVanillaSeed
    from .randomizer import get_random_info
    ri = get_random_info(ctx, ctx.RandomDir)
    if not ri or not ri.Seed:
        write_err('读不到随机器的种子（spoiler 日志的文件名里没有），定不了联机种子。先一键重随敌人一次。')
        return None
    return int(ri.Seed)


def _run_stdout(py, args):
    """& $py @args 2>$null：只要标准输出的行（错误输出不要），不开窗口"""
    from .pytool import CREATE_NO_WINDOW, child_env
    try:
        r = subprocess.run([py] + list(args), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           creationflags=CREATE_NO_WINDOW, env=child_env())
    except OSError:
        return []
    return re.split(r'\r\n|\r|\n', r.stdout.decode('utf-8', 'replace'))


def get_coop_fingerprint(ctx, Rand, WithReroll):
    """Get-CoopFingerprint：联机核对码（reroll\\coopfp.py）：Rand = 带上随机器输出的指纹，WithReroll = 带上这次重随包的指纹；失败返回 ''"""
    from .gamepath import resolve_game_root
    from .pytool import find_python
    tool = os.path.join(ctx.LauncherDir, 'reroll\\coopfp.py')
    py = find_python(ctx)
    if not py or not os.path.exists(tool):
        return ''
    a = ['-X', 'utf8', tool]
    if Rand:
        a += ['--rand', ctx.RandomDir]
    if WithReroll:
        a += ['--reroll', ctx.RerollPack]
    a += ['--dll-dir', ctx.RandomDir]
    gr = resolve_game_root(ctx)
    if gr:
        a += ['--dll-dir', os.path.join(gr, 'Game')]
    out = [l for l in _run_stdout(py, a) if _trim(l)]
    fp = _trim(out[-1]) if out else ''
    # 联机启动时（WithReroll）再带上自己加的 mod：名字 + 文件清单（崩溃风险审查 2026-11-19 第 12 条）。
    # 以前只看 regulation 和随机器输出，两人 mods 文件夹 / YAFSML自定义.ini 的 [mod] [mod_after] 不一样时核对码也一样
    mods = get_player_mod_list(ctx) if WithReroll else []
    if fp and mods:
        import hashlib
        fp += ' / m' + hashlib.sha256('\n'.join(m.Label + '#' + m.Hash for m in mods).encode('utf-8')).hexdigest()[:8]
    return fp


def _file_list_hash(root):
    """一个 mod 文件夹的文件清单：每个文件相对路径（不分大小写）+ 大小，SHA-256 前 8 位。不看修改时间（两台电脑各自解压的时间不一样），
    不读内容（外观 mod 动辄几个 GB）"""
    import hashlib
    items = []
    for dp, dns, fns in os.walk(root):
        dns.sort()
        for f in fns:
            full = os.path.join(dp, f)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            items.append((os.path.relpath(full, root).replace('\\', '/').casefold(), size))
    h = hashlib.sha256()
    for rel, size in sorted(items):
        h.update(('%s|%d\n' % (rel, size)).encode('utf-8'))
    return h.hexdigest()[:8]


def get_player_mod_list(ctx):
    """这次实际挂载的、自己加的 mod（usermods.get_user_load_lines 给的 [mod] 行：mods\\ 文件夹、YAFSML自定义.ini 的 [mod] / [mod_after]），
    按加载顺序：[Rec(Label = 「mods\\名字」/「[mod]名字」/「[mod_after]名字」, Path, After = 排在整合包后面, Hash = 文件清单)]。
    联机核对码、兼容档案用；读不了当没有（get_player_load 那边也就一个都不加载）。一次启动只算一次"""
    if getattr(ctx, 'CoopModList', None) is not None:
        return ctx.CoopModList
    from .usermods import get_user_load_lines
    out = []
    try:
        pl = get_user_load_lines(ctx)
    except Exception:
        pl = None
    for after, text in ((False, pl.Before if pl else ''), (True, pl.After if pl else '')):
        for line in re.split(r'\r?\n', text or ''):
            m = re.match(r'^\s*([^;=\s][^=]*)=(.+)$', line)
            if not m:
                continue
            key, path = m.group(1).strip(), m.group(2).strip()
            tag = '[mod_after]' if after else ('mods\\' if key.casefold().startswith('user_mod_') else '[mod]')
            out.append(Rec(Label=tag + os.path.basename(path.rstrip('\\/')), Path=path, After=after, Hash=_file_list_hash(path)))
    ctx.CoopModList = out
    return out


def test_coop_player_mods(ctx):
    """联机启动前：YAFSML自定义.ini 的 [mod_after] 排在整合包后面，里面带数值文件（regulation.bin）、地图（map）、事件（event）的话会盖过整合包的，
    两人的游戏数据对不上（崩溃风险审查 2026-11-19 第 12 条）：不让联机启动。-DryRun 只提示。返回能不能启动"""
    bad = []
    for m in get_player_mod_list(ctx):
        if not m.After:
            continue
        has = [what for n, what in (('regulation.bin', '数值文件 regulation.bin'), ('map', '地图（map 文件夹）'), ('event', '事件（event 文件夹）'))
               if os.path.exists(os.path.join(m.Path, n))]
        if has:
            bad.append('「' + m.Label[len('[mod_after]'):] + '」（' + m.Path + '）带着' + '、'.join(has))
    if not bad:
        return True
    msg = ('联机启动不了：YAFSML自定义.ini 的 [mod_after] 里' + '；'.join(bad) +
           '。[mod_after] 排在整合包后面，会盖过整合包的数值、地图和事件，两个人的游戏数据就对不上，联机时容易掉线或闪退。'
           '联机前在 YAFSML自定义.ini 里这一行的行首加 ; 停用它（或者挪到 [mod] 段），再联机启动。')
    if ctx.DryRun:
        write_warn(msg)
        return True
    write_err(msg)
    return False


# ---------------------------------------------------------------- 联机随机码 DR1 / DR2（settings.json 的敌人设置按文字改，不动排版）
def _num_re(Name):
    return re.compile(r'(?m)^' + _S + r'*"' + re.escape(Name) + r'"' + _S + r'*:' + _S + r'*(-?[0-9]+(?:\.[0-9]+)?)')


def get_coop_setting_num(Text, Name, Default):
    """Get-CoopSettingNum：settings.json 文字里 "Name": 数字（键分大小写）；没有返回 Default"""
    m = _num_re(Name).search(Text or '')
    if not m:
        return Default
    return float(m.group(1))


def set_coop_setting_num(Text, Name, Value):
    """Set-CoopSettingNum：只换已有键的数字（两个键在发布的 settings.json 里都有）；没有这个键返回 None"""
    m = _num_re(Name).search(Text or '')
    if not m:
        return None
    return Text[:m.start(1)] + _fmt3(Value) + Text[m.end(1):]


def get_coop_code(ctx):
    """Get-CoopCode：联机随机码第二版 DR2|预设种子|自然精英比例|精英倍数|普通位置出头目|世界|随机器的选项和种子。
    返回 Rec(Ok, Msg) / Rec(Ok, Code, Info, World)"""
    from .launch import get_boss_mods
    from .randomizer import get_random_info
    ri = get_random_info(ctx, ctx.RandomDir)
    if not ri:
        return Rec(Ok=False, Msg='还没有敌人随机结果。先一键重随敌人一次。')
    if ri.Merged:
        return Rec(Ok=False, Msg='现在的敌人随机结果是旧版本合并别的包做的。先一键重随敌人一次。')
    if not ri.PresetSeed or not ri.PresetNat:
        return Rec(Ok=False, Msg='现在的敌人随机结果没记下敌人预设的种子（加联机功能以前做的，或者是自己开随机器做的）。先一键重随敌人一次再复制。')
    if not re.search(r'(?:^|' + _S + r')seed:\d+', str(ri.Options or ''), re.I):
        return Rec(Ok=False, Msg='spoiler 日志第一行里没有种子，生成不了联机随机码。先一键重随敌人一次。')
    try:
        txt = _read_all_text(os.path.join(ctx.LauncherDir, 'reroll\\settings.json'))
    except Exception:
        txt = ''
    em = _fmt3(get_coop_setting_num(txt, 'elite_share_mult', 1.0))
    bp = _fmt3(get_coop_setting_num(txt, 'boss_in_basic_pct', 0.0))
    world = 'high' if _count((get_boss_mods(ctx, True) or Rec()).Keys) else 'low'
    return Rec(Ok=True, Code='DR2|' + _ps_str(ri.PresetSeed) + '|' + _ps_str(ri.PresetNat) + '|' + em + '|' + bp + '|' + world + '|' + _ps_str(ri.Options),
               Info=ri, World=world)


def get_option_key(Options):
    """Get-OptionKey：随机器选项按空白分开再用一个空格连起来（比较用）"""
    return ' '.join(x for x in _S_RUN.split(Options or '') if x)


def invoke_coop_import(ctx, Text=''):
    """Invoke-CoopImport：按联机随机码（DR2 / DR1）重随敌人：Text 不给就读剪贴板。现在的敌人随机已经是这个码的就不重随"""
    from .randomizer import get_randomizer_status
    write_head('按联机随机码重随敌人')
    rs = get_randomizer_status(ctx)
    if not rs.Ok:
        write_err(rs.Msg)
        return False
    frm = '给的' if Text else '剪贴板里的'
    if not Text:
        try:
            Text = win.clipboard_get() or ''
        except Exception:
            Text = ''
    t = _squash(Text)
    em = None
    bp = None
    world = ''
    m2 = re.match(r'^DR2\|(\d+)\|([-0-9=.,]+)\|([0-9.]+)\|([0-9.]+)\|(high|low)\|(.*(?:^|' + _S + r')seed:\d+.*)$', t, re.I)
    m1 = None if m2 else re.match(r'^DR1\|(\d+)\|([-0-9=.,]+)\|(.*(?:^|' + _S + r')seed:\d+.*)$', t, re.I)
    if m2:
        fixed = Rec(PresetSeed=m2.group(1), Nat=m2.group(2), Options=get_option_key(m2.group(6)))
        em = float(m2.group(3))
        bp = float(m2.group(4))
        world = m2.group(5)
    elif m1:
        fixed = Rec(PresetSeed=m1.group(1), Nat=m1.group(2), Options=get_option_key(m1.group(3)))
        write_warn('这是旧版的联机随机码（DR1）：不带敌人设置和世界，两人的「敌人设置」要自己对一样。')
    else:
        # 先去掉联机密码再显示（以前把 DR3 码误拿来这里时，日志里会露出联机密码；2026-11-18 移植时修）
        t = hide_coop_secret(t)
        show = (_u16_head(t, 80) + '…') if _u16_len(t) > 80 else (t if t else '（空的）')
        write_err(frm + '不是联机随机码（应该是 DR2| 开头的一行，对方在启动器里点「联机」→「复制随机码」得到）：' + show)
        return False
    if not import_coop_enemy(ctx, fixed, em, bp, world):
        return False
    fp = get_coop_fingerprint(ctx, True, False)
    if fp:
        host('  敌人随机核对码：' + fp + '（和对方复制随机码时看到的应该一样）')
    host('  现在两人都用「联机」→「联机 · 敌人随机」启动。')
    return True


def import_coop_enemy(ctx, fixed, em, bp, world):
    """Import-CoopEnemy：照房主的改敌人设置、世界，敌人随机和码不一样才重随（DR1 / DR2 导入和 DR3「加入」共用）。em / bp 是 None = 码里没带敌人设置"""
    from .gamepath import resolve_game_root
    from .randomizer import get_random_info, invoke_randomize_enemies
    # 敌人设置照房主的（不一样才改；原设置备份）。要在重随敌人之前改：敌人预设按它写
    if em is not None:
        sp = os.path.join(ctx.LauncherDir, 'reroll\\settings.json')
        txt = _read_all_text(sp)
        my_em = get_coop_setting_num(txt, 'elite_share_mult', 1.0)
        my_bp = get_coop_setting_num(txt, 'boss_in_basic_pct', 0.0)
        if my_em != em or my_bp != bp:
            if ctx.DryRun:
                host('  [-DryRun] 敌人设置会改成房主的：精英倍数 ' + _ps_str(em) + '，普通位置出头目 ' + _ps_str(bp) + '%')
            else:
                new = set_coop_setting_num(txt, 'elite_share_mult', em)
                if new is not None:
                    new = set_coop_setting_num(new, 'boss_in_basic_pct', bp)
                if new is None:
                    write_err('改不了敌人设置（settings.json 里没有 elite_share_mult / boss_in_basic_pct）：' + sp)
                    return False
                _ps_json(new)                       # [void]($new | ConvertFrom-Json)：改坏了就抛异常，不写
                _backup_once(sp, 'bak_coop')
                _write_all_text(sp, new)
                write_player('敌人设置改成了房主的：精英倍数 ' + _fmt3(em) + '，普通位置出头目 ' + _fmt3(bp) + '%（原设置已备份）')
    set_coop_world(ctx, world)
    m = re.search(r'(?:^|' + _S + r')seed:(\d+)', str(fixed.Options or ''), re.I)
    sd = m.group(1) if m else ''
    host('  联机随机码：种子 ' + sd + '，敌人预设种子 ' + _ps_str(fixed.PresetSeed))
    cur = get_random_info(ctx, ctx.RandomDir)
    if cur and not cur.Merged and _ieq(cur.PresetSeed, fixed.PresetSeed) and _ieq(cur.PresetNat, fixed.Nat) and \
            _ieq(get_option_key(cur.Options), fixed.Options):
        write_player('敌人随机已经和房主的一样，不用重随。')
    else:
        if win.find_pids('eldenring'):
            write_err('游戏还在运行，先退出游戏再重随敌人。')
            return False
        er_root = resolve_game_root(ctx)
        if not er_root:
            write_err('还没有设置游戏路径（随机器要读游戏文件）。先点「游戏路径」选一下。')
            return False
        if ctx.DryRun:
            host('  [-DryRun] 不重随。选项：' + _ps_str(fixed.Options))
            return True
        write_player('敌人随机和房主的不一样，先照房主的重随（随机器窗口会自动打开、自动关闭，约 1~5 分钟，期间不要点它）……')
        r = invoke_randomize_enemies(ctx, os.path.join(er_root, 'Game\\eldenring.exe'), fixed)
        if not r.Ok:
            write_err('按联机码重随失败：' + _ps_str(r.Msg))
            return False
        write_ok(_ps_str(r.Msg))
    return True


def set_coop_world(ctx, world):
    """Set-CoopWorld：联机世界照房主的（high = 死亡以上的改版 Boss 世界）：之后联机启动按它加载（launch.get_boss_mods）；空 = 不改。
    coop_world.txt：UTF-8 无 BOM，「世界\\n」"""
    if not world:
        return
    if not ctx.DryRun:
        _write_all_text(ctx.CoopWorldFile, world + '\n')
    write_player('联机世界：' + ('死亡以上（改版 Boss）' if _ieq(world, 'high') else '普通') + '，和房主一样')


# ---------------------------------------------------------------- 联机码第三版（用户 2026-11-16「参考爬塔mod简化一下联机流程」→「联机流程改」）
# DR3|v=整合包版本|m=rand / plain|pw=联机密码（UTF-8 的 base64）|w=high / low|sc=Seamless 的规则（键=值,…）
#    敌人随机的再加 |em=精英倍数|bp=普通位置出头目|ps=敌人预设种子|nat=自然精英比例|o=随机器的选项和种子（最后一项，里面有空格）
# 码里有联机密码：只发给队友；启动器日志里只打出去掉密码的（hide_coop_secret），诊断包里也去掉（remove_coop_secret）。DR2 / DR1 照收（不带密码）
def get_coop_pack_version(ctx):
    """Get-CoopPackVersion：本包的版本（字符串；不能和 randomizer.get_pack_version 混，那个读指定整合包的、返回版本号）"""
    vp = os.path.join(ctx.LauncherDir, 'version.txt')
    if os.path.exists(vp):
        return _trim(_read_all_text(vp))
    return ''


def read_ersc_ini(ctx, Ersc):
    """Read-ErscIni：ersc_settings.ini 的 Rec(Path, Bom, Text)；读不了抛异常"""
    ini = os.path.join(Ersc.DirectoryName, 'ersc_settings.ini')
    raw = _read_bytes(ini)
    return Rec(Path=ini, Bom=_has_bom(raw), Text=_decode_net(raw))


def set_ini_value(Text, Key, Value, Section):
    """Set-IniValue：ini 里这一项改成 Value（值后面、分号注释前的空格留着）；没有就加在 [Section] 下面（没有这一节就加在最后）"""
    m = get_ini_match(Text, Key)
    if m:
        old = m.group(1)
        keep = old[len(_trim_end(old)):]
        return Text[:m.start(1)] + Value + keep + Text[m.end(1):]
    sm = re.search(r'(?im)^[ \t]*\[' + re.escape(Section) + r'\][ \t]*(?=\r?$)', Text)
    if sm:
        at = sm.end()
        return Text[:at] + '\r\n' + Key + ' = ' + Value + Text[at:]
    return _trim_end(Text) + '\r\n\r\n[' + Section + ']\r\n' + Key + ' = ' + Value + '\r\n'


def get_ersc_rules(ctx, Ersc):
    """Get-ErscRules：Seamless 的规则（不含密码）：「键=值」列表，兼容档案和联机码共用；读不了返回 []"""
    rules = []
    try:
        txt = read_ersc_ini(ctx, Ersc).Text
    except Exception:
        return rules
    for k in CoopRuleKeys:
        m = get_ini_match(txt, k)
        if m:
            rules.append(k + '=' + _trim(m.group(1)))
    return rules


def get_ersc_password(ctx, Ersc):
    """Get-ErscPassword：ersc_settings.ini 的 cooppassword；没有 / 读不了返回 ''"""
    try:
        m = get_ini_match(read_ersc_ini(ctx, Ersc).Text, 'cooppassword')
        if m:
            return _trim(m.group(1))
    except Exception:
        pass
    return ''


def new_coop_password():
    """New-CoopPassword：16 位随机密码（去掉了容易看错的 0 O 1 l I）；和 PowerShell 一样每个字节对字符数取余"""
    chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(chars[b % len(chars)] for b in secrets.token_bytes(16))


def initialize_coop_password(ctx, Ersc):
    """Initialize-CoopPassword：房主：联机密码空着就生成一个写进去（原 ini 备份）；返回密码，失败返回 ''"""
    try:
        pw = get_ersc_password(ctx, Ersc)
        if pw:
            return pw
        pw = new_coop_password()
        if ctx.DryRun:
            host('  [-DryRun] 联机密码是空的，真的开房时会自动生成一个')
            return pw
        f = read_ersc_ini(ctx, Ersc)
        _backup_once(f.Path, 'bak')
        _write_all_text(f.Path, set_ini_value(f.Text, 'cooppassword', pw, 'PASSWORD'), f.Bom)
        write_player('联机密码是空的，自动生成了一个（联机码里带着，队友加入时自动填上；原设置已备份）。')
        return pw
    except Exception as e:
        write_err('写不了联机密码：' + _msg(e))
        return ''


def hide_coop_secret(Text):
    """Hide-CoopSecret：联机码里的密码换成「去掉了」（日志、诊断包用）；压缩过的 DR4z 解开就是带密码的原文，整个去掉"""
    t = re.sub(r'(DR3\|[^\r\n]*?\|pw=)[A-Za-z0-9+/=]*', '\\g<1>（去掉了）', Text or '')
    return re.sub(r'DR4z[A-Za-z0-9_\-]{8,}', 'DR4z（去掉了）', t)


def remove_coop_secret(ctx, Dir):
    """Remove-CoopSecret：诊断包：文字文件（.log .txt .ini .json）里的联机码去掉密码，原来有没有 BOM 照旧（隐藏的文件 / 文件夹不管，和 Get-ChildItem 一样）"""
    def walk(d):
        for e in _ls(d, False):
            yield e
        for e in _ls(d, True):
            yield from walk(e.path)
    for f in [e for e in walk(Dir) if _iin(_ext(e.name), ('.log', '.txt', '.ini', '.json'))]:
        try:
            raw = _read_bytes(f.path)
            t = _decode_net(raw)
            n = hide_coop_secret(t)
            if not _ieq(n, t):
                _write_all_text(f.path, n, _has_bom(raw))
        except Exception:
            pass


def get_coop_code3(ctx, Rand, Ersc):
    """Get-CoopCode3：生成联机码（Rand = 敌人随机）：Rec(Ok, Code, World, Info) / Rec(Ok, Msg)"""
    from .launch import get_boss_mods
    pw = get_ersc_password(ctx, Ersc)
    if not pw:
        return Rec(Ok=False, Msg='联机密码是空的：点「开房」会自动生成一个。')
    world = 'high' if _count((get_boss_mods(ctx, True) or Rec()).Keys) else 'low'
    f = ['DR3', 'v=' + get_coop_pack_version(ctx), 'm=' + ('rand' if Rand else 'plain'),
         'pw=' + base64.b64encode(pw.encode('utf-8')).decode('ascii'), 'w=' + world, 'sc=' + ','.join(get_ersc_rules(ctx, Ersc))]
    info = None
    if Rand:
        c2 = get_coop_code(ctx)
        if not c2.Ok:
            return c2
        p = c2.Code.split('|')      # DR2|预设种子|自然精英比例|精英倍数|普通位置出头目|世界|选项（选项里不会有 |）
        f += ['em=' + p[3], 'bp=' + p[4], 'ps=' + p[1], 'nat=' + p[2], 'o=' + '|'.join(p[6:])]
        info = c2.Info
    return Rec(Ok=True, Code='|'.join(f), World=world, Info=info)


def read_coop_code3(Text):
    """Read-CoopCode3：读联机码第三版：Rec(Ok, Msg, Version, Rand, Password, World, Rules, Em, Bp, Fixed) / Rec(Ok, Msg)。
    em / bp 是 [0-9.]+ 但不是数字（「1.2.3」）时和 PowerShell 一样抛异常"""
    t = _squash(Text)
    if not t.startswith('DR3|'):
        return Rec(Ok=False, Msg='不是 DR3| 开头')
    parts = t.split('|')
    h = {}                                     # 哈希表的键不分大小写
    for i in range(1, len(parts)):
        kv = parts[i]
        eq = kv.find('=')
        if eq < 1:
            continue
        k = kv[:eq]
        v = kv[eq + 1:]
        if _ieq(k, 'o'):
            if i < len(parts) - 1:
                v = '|'.join([v] + parts[i + 1:])
            h[k.lower()] = v
            break
        h[k.lower()] = v
    if not _iin(h.get('m'), ('rand', 'plain')):
        return Rec(Ok=False, Msg='启动方式看不懂（m=）')
    if not _iin(h.get('w'), ('high', 'low')):
        return Rec(Ok=False, Msg='世界看不懂（w=）')
    pw = ''
    try:
        pw = _from_b64(h.get('pw') or '').decode('utf-8', 'replace')
    except Exception:
        pass
    if not pw or re.search(r'[\r\n;]', pw):
        return Rec(Ok=False, Msg='联机密码看不懂（pw=），码可能没复制完整')
    rules = [x for x in (h.get('sc') or '').split(',') if re.search(r'^[a-z_]+=-?[0-9]+$', x, re.I)]
    r = Rec(Ok=True, Msg='', Version=h.get('v') or '', Rand=_ieq(h.get('m'), 'rand'), Password=pw, World=h.get('w'), Rules=rules,
            Em=None, Bp=None, Fixed=None)
    if r.Rand:
        if not re.search(r'^\d+$', h.get('ps') or '') or not re.search(r'^[-0-9=.,]+$', h.get('nat') or '') or \
                not re.search(r'^[0-9.]+$', h.get('em') or '') or not re.search(r'^[0-9.]+$', h.get('bp') or '') or \
                not re.search(r'(?:^|' + _S + r')seed:\d+', h.get('o') or '', re.I):
            return Rec(Ok=False, Msg='敌人随机的部分不完整，码可能没复制完整')
        r.Em = float(h['em'])
        r.Bp = float(h['bp'])
        r.Fixed = Rec(PresetSeed=h['ps'], Nat=h['nat'], Options=get_option_key(h['o']))
    return r


def set_ersc_from_code(ctx, Ersc, C):
    """Set-ErscFromCode：队友：Seamless 的联机密码和规则照房主的（不一样才改；原 ini 备份成 .bak_coop_<时间>）"""
    try:
        f = read_ersc_ini(ctx, Ersc)
        t = f.Text
        what = []
        if get_ersc_password(ctx, Ersc) != C.Password:          # -cne：分大小写
            t = set_ini_value(t, 'cooppassword', C.Password, 'PASSWORD')
            what.append('联机密码')
        rule_changed = False
        for rule in C.Rules or []:
            eq = rule.find('=')
            k = rule[:eq]
            v = rule[eq + 1:]
            if not _iin(k, CoopRuleKeys):
                continue
            m = get_ini_match(t, k)
            if not m or not _ieq(_trim(m.group(1)), v):
                t = set_ini_value(t, k, v, 'GAMEPLAY' if _iin(k, ('allow_summons', 'death_debuffs')) else 'SCALING')
                rule_changed = True
        if rule_changed:
            what.append('随人数加强等规则')
        if not what:
            host('  Seamless Co-op 设置已经和房主一样')
            return True
        if ctx.DryRun:
            host('  [-DryRun] Seamless Co-op 设置会照房主的改：' + '、'.join(what))
            return True
        _backup_once(f.Path, 'bak_coop')
        _write_all_text(f.Path, t, f.Bom)
        write_player('Seamless Co-op 设置照房主的改了：' + '、'.join(what) + '（原设置已备份）')
        return True
    except Exception as e:
        write_err('改不了 Seamless Co-op 的设置：' + _msg(e))
        return False


def copy_coop_code(ctx, C):
    """Copy-CoopCode：联机码（压缩成 DR4z）复制到剪贴板，告诉房主发给队友（日志里只打去掉密码的；复制失败才把完整的打出来让玩家手动复制）"""
    from .coopcode import compress_coop_code
    ok = True
    short = compress_coop_code(C.Code)
    try:
        if win.clipboard_set(short) is False:
            ok = False
    except Exception:
        ok = False
    about = '（' + (('敌人随机，做于 ' + C.Info.Time.strftime('%Y-%m-%d %H:%M')) if C.Info is not None else '无敌人随机') + '；世界：' + \
            ('死亡以上' if _ieq(C.World, 'high') else '普通') + '）'
    if ok:
        write_player('联机码已复制到剪贴板' + about + '：发给队友，队友复制后在启动器「联机」里点「加入」。码里有联机密码，只发给队友。')
        host('  ' + hide_coop_secret(C.Code))
    else:
        write_player('复制到剪贴板失败，手动复制下面这一行发给队友' + about + '（里面有联机密码，只发给队友）：')
        write_player(short)


_NO_ERSC = '没找到 Seamless Co-op。把它压缩包里的 SeamlessCoop 文件夹整个放进 '


def invoke_coop_code_action(ctx):
    """Invoke-CoopCodeAction：复制联机码（不启动）：按上次开房的方式（没开过房按敌人随机）"""
    from .randomizer import get_randomizer_status
    write_head('复制联机码')
    ersc = find_ersc(ctx)
    if not ersc:
        write_err(_NO_ERSC + ctx.UserDllDir + '（变成 dll\\SeamlessCoop\\ersc.dll）。')
        return False
    rand = True
    if os.path.exists(ctx.CoopHostModeFile):
        rand = not _ieq(_trim(_read_all_text(ctx.CoopHostModeFile)), 'plain')
    if rand:
        rs = get_randomizer_status(ctx)
        if not rs.Ok:
            write_err(rs.Msg)
            return False
    if not initialize_coop_password(ctx, ersc):
        return False
    c = get_coop_code3(ctx, rand, ersc)
    if not c.Ok:
        write_err(c.Msg)
        return False
    copy_coop_code(ctx, c)
    return True


def invoke_coop_host(ctx, Rand):
    """Invoke-CoopHost：联机开房：没密码就生成、联机码复制到剪贴板、联机启动"""
    from .launch import invoke_launch
    from .randomizer import get_randomizer_status
    write_head('联机开房 · ' + ('敌人随机' if Rand else '无敌人随机'))
    ctx.CoopRole = 'host'
    ersc = find_ersc(ctx)
    if not ersc:
        write_err(_NO_ERSC + ctx.UserDllDir + '（变成 dll\\SeamlessCoop\\ersc.dll；整合包不带 Seamless Co-op，要自己下载）。')
        return False
    if Rand:
        rs = get_randomizer_status(ctx)
        if not rs.Ok:
            write_err(rs.Msg)
            return False
    # 世界：开房时选了（图形界面问的，-BossWorld high|low）就记下来，联机启动、联机码、标题封面都按它；
    # 没选（Boss 改版没开）就按自己上次玩的联机角色，以前当队友加入时照别人的码记下的去掉
    if _iin(ctx.BossWorld, ('high', 'low')):
        if not ctx.DryRun:
            _write_all_text(ctx.CoopWorldFile, ctx.BossWorld + '\n')
        write_player('联机世界：' + ('死亡以上（改版 Boss）' if _ieq(ctx.BossWorld, 'high') else '普通') + '（开房时选的，队友加入时照联机码用同一个）')
    elif os.path.exists(ctx.CoopWorldFile):
        if not ctx.DryRun:
            try:
                os.remove(ctx.CoopWorldFile)
            except OSError:
                pass
        host('  以前加入队友时记下的联机世界去掉了：开房按自己上次玩的联机角色定')
    if not initialize_coop_password(ctx, ersc):
        return False
    c = get_coop_code3(ctx, Rand, ersc)
    if not c.Ok:
        write_err(c.Msg)
        return False
    if not ctx.DryRun:
        try:
            _write_all_text(ctx.CoopHostModeFile, 'rand' if Rand else 'plain')      # 无 BOM、不带换行
        except Exception:
            pass
    copy_coop_code(ctx, c)
    invoke_launch(ctx, Rand, True)
    return True


def invoke_coop_join(ctx, Text=''):
    """Invoke-CoopJoin：加入队友：找联机码（给的 / 剪贴板 → 联机时联机通道存下的房主的码、上次加入用的码，新的先），照着改好再联机启动"""
    from .coopcode import expand_coop_code
    from .launch import invoke_launch
    from .randomizer import get_randomizer_status
    write_head('加入队友的联机')
    ctx.CoopRole = 'guest'
    ersc = find_ersc(ctx)
    if not ersc:
        write_err(_NO_ERSC + ctx.UserDllDir + '（变成 dll\\SeamlessCoop\\ersc.dll；整合包不带 Seamless Co-op，要自己下载）。')
        return False
    cands = []
    if Text:
        cands.append(('给的', Text))
    else:
        try:
            cands.append(('剪贴板里的', win.clipboard_get() or ''))
        except Exception:
            pass
    files = [(ctx.CoopHostCodeFile, '上次联机时房主发来的'), (ctx.CoopJoinCodeFile, '上次加入时用的')]
    files = sorted([f for f in files if os.path.exists(f[0])], key=lambda f: os.stat(f[0]).st_mtime_ns, reverse=True)
    for p, n in files:
        cands.append((n, _read_all_text(p)))
    code = ''
    frm = ''
    for n, s in cands:
        t = _squash(s)
        if re.match(r'^DR(?:[123]\||4)', t, re.I):
            code = t
            frm = n
            break
    if not code:
        write_err('没找到联机码：先复制房主发来的那一串（DR4 开头），再点「加入」。')
        return False
    # 前缀不分大小写（以前 .StartsWith 分大小写：「dr4z…」「dr3|…」先被认成联机码、又被当旧版的码拒掉；2026-11-18 移植时修）。
    # DR4 后面的模式字母是小写的（z），base64 那段本身分大小写、不能动
    if code[:3].upper() == 'DR4':
        code = 'DR4' + code[3:4].lower() + code[4:]
    elif code[:4].upper() == 'DR3|':
        code = 'DR3|' + code[4:]
    if code.startswith('DR4'):
        plain = expand_coop_code(code)
        if not plain:
            write_err(frm + '联机码解不开（多半没复制完整）：让房主重新点「复制联机码」发一次。')
            return False
        code = plain
    if not code.startswith('DR3|'):
        # 旧版的码（DR2 / DR1）：不带联机密码和启动方式，按敌人随机
        write_warn('这是旧版的联机随机码（不带联机密码）：两人的联机密码要自己填一样的（「工具与设置」→「联机设置」）。')
        if not test_ersc_settings(ctx, ersc):
            return False
        if not invoke_coop_import(ctx, code):
            return False
        invoke_launch(ctx, True, True)
        return True
    c = read_coop_code3(code)
    if not c.Ok:
        write_err(frm + '联机码不对：' + c.Msg + '。让房主重新点「复制联机码」发一次。')
        return False
    mine = get_coop_pack_version(ctx)
    if c.Version and mine and not _ieq(c.Version, mine):
        write_err('房主的整合包是 ' + c.Version + '，你的是 ' + mine + '：两人先更新成同一个版本再联机。')
        return False
    write_player('按' + frm + '联机码加入：' + ('敌人随机' if c.Rand else '无敌人随机') + '，世界：' + ('死亡以上' if _ieq(c.World, 'high') else '普通'))
    if not set_ersc_from_code(ctx, ersc, c):
        return False
    if c.Rand:
        rs = get_randomizer_status(ctx)
        if not rs.Ok:
            write_err(rs.Msg)
            return False
        if not import_coop_enemy(ctx, c.Fixed, c.Em, c.Bp, c.World):
            return False
    else:
        set_coop_world(ctx, c.World)
    if not ctx.DryRun:
        try:
            _write_all_text(ctx.CoopJoinCodeFile, code + '\n')
        except Exception:
            pass
    invoke_launch(ctx, c.Rand, True)
    return True
