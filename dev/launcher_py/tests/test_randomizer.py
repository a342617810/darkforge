# -*- coding: utf-8 -*-
"""randomizer.py 的对照测试：同样的假随机器文件夹、假的 APPDATA / LOCALAPPDATA，分别跑 randomize.ps1 / launcher.ps1 里的旧函数和 dfl.randomizer 的新函数，
比返回值、输出的行、写出的文件（逐字节）。

做法：整合包根目录复制一份（harness.copy_root，放在 <临时>\\w\\x\\root，往上两级都在临时目录里，找「别的整合包」时不会扫到别处），
每个用例先按固定的内容和修改时间搭好现场 → 跑 PowerShell → 记下结果和文件 → 原样重搭 → 跑 Python → 比。
随机器只用假的 exe（不是真的程序，打不开）；真的 randomizer\\EldenRingRandomizer.exe 只读着算一次哈希。
不启动随机器、游戏、图形界面；第 2 步（UI 自动化）要真的打开随机器，在 rand_parity.py / randenemy_smoke.py 里实跑（普通终端）。

有意的不同（汇报里也写了）：
- Copy-RandItems 出错时的原因：以前是「robocopy 返回 N」，现在是系统的错误说明（只比开头）。
- Set-RandSettings 的值里有 XML 不许的字符：PowerShell 写到一半报错、文件剩半截；Python 先报错、文件不动（单独断言）。
- Get-OtherPacks 读 game_path.txt：PowerShell 按 ANSI 读（中文路径读错），Python 按 UTF-8（这里只用英文路径比）。
运行：launcher\\python\\python.exe -X utf8 dev\\launcher_py\\tests\\test_randomizer.py"""
import ctypes
import datetime
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from dfl import randomizer as R  # noqa: E402

RESULTS = []
T0 = 1762000000 * 10 ** 9 + 123456700          # 2025-11-01 前后，带不到一秒的部分（.NET 的 100 纳秒精度）
HOUR = 3600 * 10 ** 9


def check(name, ps, py):
    ok = harness.same(name, ps, py)
    RESULTS.append((name, ok))
    return ok


def check_true(name, cond, info=''):
    print(('OK   ' if cond else 'DIFF ') + name + ('' if cond else '   ' + str(info)[:2000]))
    RESULTS.append((name, bool(cond)))
    return cond


def psq(s):
    return "'" + str(s).replace("'", "''") + "'"


# ---------------------------------------------------------------- 现场
TMP = tempfile.mkdtemp(prefix='dfrand_')
BASE = os.path.join(TMP, 'w', 'x')
os.makedirs(BASE)
print('复制整合包到', BASE)
ROOT = harness.copy_root(BASE)
L = os.path.join(ROOT, 'launcher')
RD = os.path.join(ROOT, 'randomizer')
HD = os.path.join(ROOT, 'randomizer_hi')
GAME = os.path.join(TMP, 'game', 'ELDEN RING')
PACKS = os.path.join(TMP, 'w', 'packs')
FAR = os.path.join(TMP, 'far')
USER = os.path.join(TMP, 'user')
PF = os.path.join(TMP, 'pf')
DNR = os.path.join(TMP, 'dotnetroot')
XMLD = os.path.join(TMP, 'xml')
ENV = harness.fake_env(TMP)
ENV.update({'USERPROFILE': USER, 'ProgramFiles': PF, 'DOTNET_ROOT': ''})
APPD = ENV['APPDATA']
LAD = ENV['LOCALAPPDATA']
AVALO = os.path.join(LAD, 'EldenRingRandomizer.Avalo')
DRD = os.path.join(APPD, 'EldenRing', 'DarkReforged')
PY_ON = os.path.join(L, 'python')
PY_OFF = os.path.join(TMP, 'python_off')

# 游戏（假的：Test-NormalizeGameRoot 只看 Game\eldenring.exe 在不在）
os.makedirs(os.path.join(GAME, 'Game'))
open(os.path.join(GAME, 'Game', 'eldenring.exe'), 'wb').close()
with open(os.path.join(L, 'game_path.txt'), 'wb') as f:
    f.write((GAME + '\r\n').encode('utf-8'))

# 包里的 Python（Update-ManualPreset 用 launcher\python\python.exe 跑 reroll\enemypreset.py）：只复制跑得起来的几个文件
os.makedirs(PY_OFF)
for n in ('python.exe', 'python3.dll', 'python312.dll', 'python312.zip', 'python312._pth', 'vcruntime140.dll', 'vcruntime140_1.dll'):
    shutil.copy2(os.path.join(harness.LAUNCHER, 'python', n), os.path.join(PY_OFF, n))

FAKE_PRESET = r'''# -*- coding: utf-8 -*-
# 假的 enemypreset.py：把参数记进 fake_args.json，按 fake_mode.txt（第一行退出码，其余原样输出）输出、退出
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
mode = ['0']
p = os.path.join(here, 'fake_mode.txt')
if os.path.exists(p):
    mode = open(p, encoding='utf-8').read().split('\n')
with open(os.path.join(here, 'fake_args.json'), 'w', encoding='utf-8') as f:
    json.dump(sys.argv[1:], f, ensure_ascii=False)
for l in mode[1:]:
    if l:
        print(l)
sys.exit(int(mode[0]))
'''

K32 = ctypes.WinDLL('kernel32', use_last_error=True)
K32.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
K32.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
K32.GetFileAttributesW.restype = ctypes.c_uint32


def set_attr(p, add):
    a = K32.GetFileAttributesW(p)
    K32.SetFileAttributesW(p, (a & ~0x80) | add)


def rm(p):
    if not os.path.lexists(p):
        return
    if os.path.isjunction(p) or os.path.islink(p):
        os.rmdir(p)
        return
    if os.path.isdir(p):
        def onexc(func, q, exc):
            try:
                K32.SetFileAttributesW(q, 0x80)
                os.chmod(q, stat.S_IWRITE)
            except OSError:
                pass
            func(q)
        shutil.rmtree(p, onexc=onexc)
    else:
        K32.SetFileAttributesW(p, 0x80)
        os.remove(p)


def mk(path, data=b'', mtime=None, hidden=False, readonly=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(data, str):
        data = data.encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)
    if mtime is not None:
        os.utime(path, ns=(mtime, mtime))
    if hidden:
        set_attr(path, 0x2)
    if readonly:
        set_attr(path, 0x1)
    return path


def mkdir(p, hidden=False):
    os.makedirs(p, exist_ok=True)
    if hidden:
        set_attr(p, 0x2)
    return p


def reset(python=False):
    """清掉所有用例会动的地方"""
    for p in (RD, HD, os.path.join(L, 'randomizer_settings_path.txt'), os.path.join(L, 'reroll'), os.path.join(L, 'dotnet'),
              os.path.join(APPD, 'EldenRing'), AVALO, PACKS, FAR, USER, PF, DNR, XMLD,
              os.path.join(BASE, 'old4'), os.path.join(BASE, 'old5'), os.path.join(GAME, 'Game', 'gpack'), os.path.join(TMP, 'w', 'empty'),
              os.path.join(TMP, 'nope'), os.path.join(TMP, 'csrc'), os.path.join(TMP, 'cdst'), os.path.join(TMP, 'jtarget')):
        rm(p)
    os.makedirs(os.path.join(USER, 'Downloads'))
    os.makedirs(PF)
    mk(os.path.join(L, 'reroll', 'enemypreset.py'), FAKE_PRESET)
    if python and os.path.isdir(PY_OFF):
        os.rename(PY_OFF, PY_ON)
    elif not python and os.path.isdir(PY_ON):
        os.rename(PY_ON, PY_OFF)


def log_text(opts, merged=False, pad=0, opt_prefix='Options and seed: '):
    lines = [opt_prefix + opts, '']
    if merged:
        lines += ['Extracted 1682 game files', 'Checking other mod directory F:\\game\\RNG Lands\\recommended']
    lines += ['x'] * pad
    lines += ["Ctrl+F 'Boss placements' or 'Miniboss placements' or 'Basic placements' to see enemy placements.", 'Version: v0.12.2', '',
              '-- Enemy preset', 'Classes:', '  Basic:', '中文 ok']
    return ('\r\n'.join(lines) + '\r\n').encode('utf-8')


OPT_E = 'allmaps bossbgm changestats crashfix customenemy dlc enemy markareas phasehp scale v16 bias:20 seed:1271204388'


def rand_install(d=RD, exe=True, diste=True):
    """随机器本身（假的 exe）"""
    if exe:
        mk(os.path.join(d, 'EldenRingRandomizer.exe'), b'not a real exe\r\n', T0)
    if diste:
        mk(os.path.join(d, 'diste', 'Base', 'enemy.txt'), 'enemy', T0)
    mk(os.path.join(d, 'dll', 'RandomizerCrashFix.dll'), b'dll', T0)
    mkdir(os.path.join(d, 'presets'))


def rand_output(d=RD, logs=(), regulation=True, big=0):
    """随机器的输出：logs = [(文件名, 内容, 修改时间)]"""
    mk(os.path.join(d, 'map', 'mapstudio', 'm10_00_00_00.msb.dcx'), b'msb' * 100, T0 + 1)
    mk(os.path.join(d, 'map', 'mapstudio', 'ro.msb.dcx'), b'readonly', T0 + 2, readonly=True)
    mk(os.path.join(d, 'map', 'hid.bin'), b'hidden', T0 + 3, hidden=True)
    mk(os.path.join(d, 'event', 'common.emevd.dcx'), b'ev', T0 + 4)
    mk(os.path.join(d, 'msg', 'zhocn', 'item.msgbnd.dcx'), '中文'.encode('utf-8'), T0 + 5)
    mkdir(os.path.join(d, 'script', 'empty'))
    mk(os.path.join(d, 'sfx', 'big.ffxbnd.dcx'), b'\0' * big, T0 + 6)
    if regulation:
        mk(os.path.join(d, 'regulation.bin'), b'REG', T0 + 7)
    mk(os.path.join(d, 'config_eldenringrandomizer.toml'), b'[x]\r\n', T0 + 8)
    for name, text, mt in logs:
        mk(os.path.join(d, 'spoiler_logs', name), text, mt)


def new_pack(p, ver='0.10.12', logs=(), regulation=True, hi=None):
    mk(os.path.join(p, 'launcher', 'launcher.ps1'), '# fake')
    if ver is not None:
        mk(os.path.join(p, 'launcher', 'version.txt'), ver)
    if logs or regulation:
        rand_output(os.path.join(p, 'randomizer'), logs, regulation)
    return p


CFG4 = '''<?xml version="1.0" encoding="utf-8"?>
<configuration>
    <configSections>
        <sectionGroup name="userSettings" type="System.Configuration.UserSettingsGroup, System.Configuration.ConfigurationManager, Version=9.0.0.0, Culture=neutral, PublicKeyToken=cc7b13ffcd2ddd51" >
            <section name="RandomizerCommon.Properties.Settings" type="System.Configuration.ClientSettingsSection, System.Configuration.ConfigurationManager, Version=9.0.0.0, Culture=neutral, PublicKeyToken=cc7b13ffcd2ddd51" allowExeDefinition="MachineToLocalUser" requirePermission="false" />
        </sectionGroup>
    </configSections>
    <userSettings>
        <RandomizerCommon.Properties.Settings>
            <setting name="Options" serializeAs="String">
                <value>{opt}</value>
            </setting>
            <setting name="ExtraDlls" serializeAs="Xml">
                <value>
                    <ArrayOfString xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                        xmlns:xsd="http://www.w3.org/2001/XMLSchema">
                        <string>{dll}\\RandomizerCrashFix.dll</string>
                    </ArrayOfString>
                </value>
            </setting>
            <setting name="Exe" serializeAs="String">
                <value>{exe}</value>
            </setting>
            <setting name="Mod" serializeAs="String">
                <value />
            </setting>
            <setting name="WindowPosition" serializeAs="String">
                <value>358, 142, 1160, 718</value>
            </setting>
        </RandomizerCommon.Properties.Settings>
    </userSettings>
</configuration>'''.replace('\n', '\r\n')

CFG2 = '''<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <configSections>
    <sectionGroup name="userSettings" type="System.Configuration.UserSettingsGroup, System.Configuration.ConfigurationManager, Version=9.0.0.0, Culture=neutral, PublicKeyToken=cc7b13ffcd2ddd51">
      <section name="RandomizerCommon.Properties.Settings" type="System.Configuration.ClientSettingsSection, System.Configuration.ConfigurationManager, Version=9.0.0.0, Culture=neutral, PublicKeyToken=cc7b13ffcd2ddd51" allowExeDefinition="MachineToLocalUser" requirePermission="false" />
    </sectionGroup>
  </configSections>
  <userSettings>
    <RandomizerCommon.Properties.Settings>
      <setting name="Options" serializeAs="String">
        <value>{opt}</value>
      </setting>
      <setting name="ExtraDlls" serializeAs="Xml">
        <value>
          <ArrayOfString xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:xsd="http://www.w3.org/2001/XMLSchema">
            <string>{dll}\\RandomizerCrashFix.dll</string>
          </ArrayOfString>
        </value>
      </setting>
      <setting name="Mod" serializeAs="String">
        <value>E:\\old\\mod &amp; more</value>
      </setting>
      <setting name="WindowPosition" serializeAs="String">
        <value>208, 208, 1160, 718</value>
      </setting>
    </RandomizerCommon.Properties.Settings>
  </userSettings>
</configuration>'''.replace('\n', '\r\n')

# 没开崩溃修复（没有 ExtraDlls）：认不出是哪一份随机器的
CFGN = '''<?xml version="1.0" encoding="utf-8"?>
<configuration>
    <userSettings>
        <RandomizerCommon.Properties.Settings>
            <setting name="Options" serializeAs="String">
                <value>{opt}</value>
            </setting>
            <setting name="Exe" serializeAs="String">
                <value>{exe}</value>
            </setting>
        </RandomizerCommon.Properties.Settings>
    </userSettings>
</configuration>'''.replace('\n', '\r\n')


def cfg(name, tpl, mtime, opt=OPT_E, dll=None, exe='E:\\Games\\ELDEN RING\\Game\\eldenring.exe', bom=False):
    p = os.path.join(AVALO, 'EldenRingRandomizer.Avalo_Path_' + name, '1.0.0.0', 'user.config')
    t = tpl.replace('{opt}', opt).replace('{dll}', dll or os.path.join(RD, 'dll')).replace('{exe}', exe)
    mk(p, (b'\xef\xbb\xbf' if bom else b'') + t.encode('utf-8'), mtime)
    return p


def write_map(lines, bom=False, crlf=True, final=True):
    nl = '\r\n' if crlf else '\n'
    t = nl.join(lines) + (nl if final else '')
    mk(os.path.join(L, 'randomizer_settings_path.txt'), (b'\xef\xbb\xbf' if bom else b'') + t.encode('utf-8'))


# ---------------------------------------------------------------- 比较
def snap(paths, mtimes=()):
    """{相对 TMP 的路径: 字节}；mtimes 里的前缀下的文件再带上修改时间（复制的结果要保留修改时间）"""
    out = {}
    for base in paths:
        if os.path.isfile(base):
            items = [base]
        else:
            items = []
            for d, dirs, files in os.walk(base):
                for n in dirs:
                    full = os.path.join(d, n)
                    if not os.listdir(full):
                        out[os.path.relpath(full, TMP) + '\\'] = 'dir'
                items += [os.path.join(d, n) for n in files]
        for p in items:
            rel = os.path.relpath(p, TMP)
            with open(p, 'rb') as f:
                v = f.read()
            if any(rel.startswith(m) for m in mtimes):
                v = (v, os.stat(p).st_mtime_ns // 100, K32.GetFileAttributesW(p) & 0x3)      # 修改时间、只读 / 隐藏
            out[rel] = v
    return out


def norm_preset(tree):
    """.dr_manual.preset 第一行是现在的时间、第二行是随机的种子：格式对就换成占位再比"""
    for k, v in list(tree.items()):
        if k.endswith('.dr_manual.preset') and isinstance(v, bytes):
            t = v.decode('utf-8').split('\n')
            ok = (len(t) == 4 and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}[+-]\d\d:\d\d', t[0]) and re.fullmatch(r'\d+', t[1]))
            tree[k] = ('<time ok>' if ok else t[0], '<seed>' if ok else t[1], t[2:])
        if k.endswith('fake_args.json') and isinstance(v, bytes):
            a = json.loads(v.decode('utf-8'))
            i = a.index('--seed') if '--seed' in a else -1
            if i >= 0:
                a[i + 1] = '<seed>' if a[i + 1].isdigit() else a[i + 1]
            tree[k] = a
    return tree


def dt_ms(dt):
    aware = dt.astimezone()
    return (aware - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)) // datetime.timedelta(milliseconds=1)


def norm(v):
    """两边的结果变成一样的形状：PowerShell 的日期（/Date(ms)/）、[version]（Major…）；Python 的 datetime、_Ver"""
    if isinstance(v, R._Ver):
        return str(v)
    if isinstance(v, datetime.datetime):
        return dt_ms(v)
    if isinstance(v, dict):
        if set(v) >= {'Major', 'Minor', 'Build', 'Revision'}:
            return '.'.join(str(v[k]) for k in ('Major', 'Minor', 'Build', 'Revision') if v[k] >= 0)
        if set(v) == {'value', 'DisplayHint', 'DateTime'}:
            return norm(v['value'])
        return {k: norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, str):
        m = re.fullmatch(r'/Date\((-?\d+)\)/', v)
        if m:
            return int(m.group(1))
    return v


def norm_out(lines, seconds=False):
    """输出的行：Python 这边消息里的 \\r\\n 会多出 \\r（图形界面按行读时一样），去掉；可选把「用时 N 秒」换掉"""
    out = '\n'.join(lines).replace('\r\n', '\n').replace('\r', '').split('\n') if lines else []
    if seconds:
        out = [re.sub(r'用时 \d+ 秒', '用时 N 秒', l) for l in out]
    return out


def case(name, setup, snippet, fn, watch=(), mtimes=(), ctx_args=None, seconds=False, ps_pre='', py_pre=None, env=None, root=ROOT, expect=None):
    """搭现场 → PowerShell → 记下 → 重搭 → Python → 比返回值、输出、文件"""
    e = dict(ENV)
    e.update(env or {})
    setup()
    if ps_pre:
        snippet = ps_pre + '\n' + snippet
    # Windows 给每个新的 64 位进程重新设 ProgramFiles（传进去的不算），只能在 PowerShell 里面再设成假的
    snippet = '$env:ProgramFiles = %s\n' % psq(e['ProgramFiles']) + snippet
    pr, po = harness.ps_call(snippet, e, root=root)
    pt = norm_preset(snap(watch, mtimes))
    setup()
    if py_pre:
        py_pre()
    try:
        yr, yo = harness.py_call(fn, e, root=root, **(ctx_args or {}))
    except Exception as e:                  # 测试里出错也要看得到是哪个用例
        yr, yo = {'py_exception': repr(e)}, []
    yt = norm_preset(snap(watch, mtimes))
    if os.environ.get('DFTEST_VERBOSE'):              # 看看两边实际给了什么（不是两边都空着才一样）
        print('   [PS 返回]', json.dumps(norm(pr), ensure_ascii=False, default=str)[:600])
        print('   [PS 输出]', ' | '.join(norm_out(po, seconds))[:600])
        print('   [写出的文件]', len(pt), '个', sorted(k for k in pt if not k.startswith('w\\x\\root\\randomizer\\diste'))[:8])
    if expect:                                        # 有意的不同（修过的老毛病）：返回值改成断言新的行为
        a = check_true(name + ' · 返回值（有意的不同，断言新的行为）', bool(expect(norm(pr), norm(yr))), (norm(pr), norm(yr)))
    else:
        a = check(name + ' · 返回值', norm(pr), norm(yr))
    b = check(name + ' · 输出', norm_out(po, seconds), norm_out(yo, seconds))
    diff = [k for k in sorted(set(pt) | set(yt)) if pt.get(k) != yt.get(k)]
    c = check_true(name + ' · 文件', not diff, [(k, str(pt.get(k))[:300], str(yt.get(k))[:300]) for k in diff[:6]])
    return a and b and c


def py_only(name, fn, setup=None, ctx_args=None):
    if setup:
        setup()
    try:
        r, o = harness.py_call(fn, ENV, root=ROOT, **(ctx_args or {}))
        return r, norm_out(o)
    except Exception as e:
        return e, []


# ================================================================ 1. user.config 的写法（Set-RandSettings）
def xml_cases():
    """[(名字, 原文字节, [(键, 值)])]"""
    dll = 'E:\\Pack\\randomizer\\dll'
    full3 = [('Options', 'allmaps enemy v16 customenemy'), ('Mod', ''), ('Exe', 'D:\\游戏\\ELDEN RING\\Game\\eldenring.exe')]
    c4 = CFG4.replace('{opt}', 'enemy v16 seed:5').replace('{dll}', dll).replace('{exe}', 'E:\\old.exe')
    c2 = CFG2.replace('{opt}', 'enemy v16').replace('{dll}', dll)
    cn = CFGN.replace('{opt}', 'enemy').replace('{exe}', 'x')
    strip_dll = c4.replace('<string>E:\\Pack\\randomizer\\dll\\RandomizerCrashFix.dll</string>', '')
    out = [
        ('cfg4_full', c4.encode(), full3),
        ('cfg2_missing_exe', c2.encode(), full3),
        ('cfg2_mod_exe', c2.encode(), [('Mod', ''), ('Exe', 'C:\\a b\\eldenring.exe')]),
        ('cfg2_mod_only', c2.encode(), [('Mod', '')]),
        ('cfg2_mod_options', c2.encode(), [('Mod', ''), ('Options', 'a b')]),
        ('cfgN_missing_many', cn.encode(), full3),
        ('cfgN_exe_options', cn.encode(), [('Exe', 'E:\\x'), ('Options', 'o')]),
        ('cfgN_mod_exe', cn.encode(), [('Mod', ''), ('Exe', 'E:\\y')]),
        ('bom_input', b'\xef\xbb\xbf' + c4.encode(), [('Mod', '')]),
        ('lf_input', c4.replace('\r\n', '\n').encode(), [('Mod', 'm')]),
        ('no_decl', c4.split('\r\n', 1)[1].encode(), [('Mod', '')]),
        ('standalone', c4.replace('encoding="utf-8"?>', 'encoding="utf-8" standalone="yes"?>', 1).encode(), [('Mod', '')]),
        ('decl_utf16_name', c4.replace('encoding="utf-8"', 'encoding="utf-16"', 1).encode(), [('Mod', '')]),
        ('special_chars', c4.encode(), [('Options', 'a & b < c > d " e \' f 中文 \t tab'), ('Mod', 'x&y'), ('Exe', '')]),
        ('empty_value_tag', c4.replace('<value>E:\\old.exe</value>', '<value></value>').encode(), [('Mod', '')]),
        ('ws_value', c4.replace('<value>E:\\old.exe</value>', '<value>   </value>').encode(), [('Mod', '')]),
        ('spaces_kept', c4.replace('<value>E:\\old.exe</value>', '<value>  sp  </value>').encode(), [('Mod', '')]),
        ('comment', c4.replace('<userSettings>', '<!-- 注释 -->\r\n    <userSettings>', 1).encode(), [('Mod', '')]),
        ('comment_top', c4.replace('<configuration>', '<!--top--><configuration>', 1).encode() + b'\r\n<!--tail-->', [('Mod', '')]),
        ('cdata', c4.replace('<value>358, 142, 1160, 718</value>', '<value><![CDATA[a<b]]></value>').encode(), [('Mod', '')]),
        ('mixed', c4.replace('<value>358, 142, 1160, 718</value>', '<value>t<b>x</b>u<c /></value>').encode(), [('Mod', '')]),
        ('nested_after_text', c4.replace('<value>358, 142, 1160, 718</value>', '<value><a><b /></a>txt<d><e /></d></value>').encode(), [('Mod', '')]),
        ('entities_attr', c4.replace('name="WindowPosition"', 'name="Win&amp;Pos" extra="a&#10;b&#9;c&quot;&lt;"').encode(), [('Mod', '')]),
        ('selfclose_array', strip_dll.encode(), [('Mod', '')]),
        ('array_selfclose', re.sub(r'<ArrayOfString[^>]*>\s*</ArrayOfString>', '<ArrayOfString xmlns:xsi="x" xmlns:xsd="y" />', strip_dll).encode(),
         [('Mod', '')]),
        ('pi_inside', c4.replace('<userSettings>', '<?my-pi some data?><userSettings>', 1).encode(), [('Mod', '')]),
        ('gt_in_attr', c4.replace('serializeAs="Xml"', 'serializeAs="a>b/"').encode(), [('Mod', '')]),
        ('value_newline_text', c4.replace('<value>358, 142, 1160, 718</value>', '<value>l1\r\nl2\rl3\nl4</value>').encode(), [('Mod', '')]),
        ('set_newline', c4.encode(), [('Options', 'a\r\nb\nc')]),
        ('dup_setting', c4.replace('<setting name="Exe"', '<setting name="Mod" serializeAs="String"><other /></setting>\r\n<setting name="Exe"', 1).encode(),
         [('Mod', 'z')]),
        ('no_usersettings_missing', b'<?xml version="1.0"?><configuration><a /></configuration>', [('Mod', '')]),
        ('no_usersettings_present', b'<configuration><setting name="Mod"><value>q</value></setting></configuration>', [('Mod', '')]),
        ('broken', c4[:-20].encode(), [('Mod', '')]),
        ('not_xml', b'hello', [('Mod', '')]),
        ('empty_file', b'', [('Mod', '')]),
        ('usersettings_empty_first', b'<c><userSettings></userSettings><userSettings><S><setting name="A"><value>1</value></setting></S></userSettings></c>',
         [('Mod', 'n')]),
        ('single_quote_attr', b"<c a='1'><userSettings><S><setting name='Mod'><value>v</value></setting></S></userSettings></c>", [('Mod', '')]),
        ('real_like_4vk', CFG2.replace('{opt}', 'x v16').replace('{dll}', dll).encode(), [('Options', 'y v16 customenemy'), ('Mod', '')]),
    ]
    return out


def t_xml():
    reset()
    cases = xml_cases()
    for side in ('ps', 'py'):
        for n, data, vals in cases:
            mk(os.path.join(XMLD, side, n + '.config'), data)
            with open(os.path.join(XMLD, side, n + '.json'), 'w', encoding='utf-8') as f:
                json.dump(vals, f, ensure_ascii=False)
    snippet = r'''
$res = @{}
foreach ($c in @(Get-ChildItem -LiteralPath %s -Filter '*.config')) {
    $j = [IO.File]::ReadAllText(($c.FullName -replace '\.config$', '.json'), [Text.Encoding]::UTF8) | ConvertFrom-Json
    $h = @{}
    foreach ($kv in @($j)) { $h[[string]$kv[0]] = [string]$kv[1] }
    try { Set-RandSettings $c.FullName $h; $res[$c.BaseName] = 'ok' } catch { $res[$c.BaseName] = 'err' }
}
$__r = $res
''' % psq(os.path.join(XMLD, 'ps'))
    pr, po = harness.ps_call(snippet, ENV, root=ROOT)

    def run(ctx):
        res = {}
        for n, data, vals in cases:
            p = os.path.join(XMLD, 'py', n + '.config')
            try:
                R.set_rand_settings(ctx, p, dict(vals))
                res[n] = 'ok'
            except Exception:
                res[n] = 'err'
        return res
    yr, yo = harness.py_call(run, ENV, root=ROOT)
    check('Set-RandSettings 成功 / 报错', pr, yr)
    first = open(os.path.join(XMLD, 'py', 'cfg4_full.config'), 'rb').read()
    check_true('Set-RandSettings 真的重写了（四空格 → 两空格、属性并成一行）', first != cases[0][1] and b'\r\n  <configSections>' in first and
               b'<ArrayOfString xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">' in first, first[:400])
    for n, data, vals in cases:
        a = open(os.path.join(XMLD, 'ps', n + '.config'), 'rb').read()
        b = open(os.path.join(XMLD, 'py', n + '.config'), 'rb').read()
        check_true('Set-RandSettings 写出的字节 · ' + n, a == b, (a[:1500], b[:1500]))
    # 有意的不同：XML 不许的字符，Python 先报错、文件不动
    p = mk(os.path.join(XMLD, 'bad.config'), cases[0][1])
    try:
        R.set_rand_settings(None, p, {'Mod': 'a\x01b'})
        bad = 'no error'
    except ValueError:
        bad = 'ValueError'
    check_true('Set-RandSettings 不许的字符：先报错、文件不动（有意的不同）', bad == 'ValueError' and open(p, 'rb').read() == cases[0][1], bad)


# ================================================================ 2. 常量、说明文字、Sort-Object 的顺序
def t_sort():
    """PowerShell 5.1 的 Sort-Object 不稳定（老的快速排序）：一样大的几项的顺序要和它一样，挑「最新的一份」才对得上"""
    seqs = [[1] * 6, [1] * 20, [2, 1, 2, 1, 2], [3, 3, 1, 2, 2, 3, 1, 1, 2, 3, 3, 3, 2, 1, 5, 5, 5, 0, 0, 0, 0, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7],
            list(range(40, 0, -1)), [5], []]
    sn = []
    for s in seqs:
        arr = '@(' + ','.join('[pscustomobject]@{K=%d;N=%d}' % (k, i) for i, k in enumerate(s)) + ')'
        sn.append('@(@(%s | Sort-Object K -Descending | ForEach-Object { $_.N }), @(%s | Sort-Object K | ForEach-Object { $_.N }))' % (arr, arr))
    snippet = '$__r = @(' + ', '.join(sn) + ')'

    def fn(ctx):
        out = []
        for s in seqs:
            items = list(enumerate(s))
            out.append([[i for i, k in R._ps_sort(items, lambda t: t[1], Descending=True)], [i for i, k in R._ps_sort(items, lambda t: t[1])]])
        return out
    case('Sort-Object 的顺序（一样大的打乱方式）', reset, snippet, fn)


def t_consts():
    snippet = r'''
$__r = @{
  RandDefaultOptions = $RandDefaultOptions; DotNet8Url = $DotNet8Url; RandomizerUrl = $RandomizerUrl; RandomizerTested = $RandomizerTested
  RandHiItems = $RandHiItems; RandHiSource = $RandHiSource; RandCarryMinVersion = $RandCarryMinVersion.ToString(); RandOutputItems = $RandOutputItems
  RandSettingsRoot = $RandSettingsRoot; RandSettingsMap = $RandSettingsMap; BundledDotNet = $BundledDotNet; RandomHiDir = $RandomHiDir
  RandPacksFile = $RandPacksFile; RandomDir = $RandomDir; RandomExe = $RandomExe
  DotNet8Msg = (Get-DotNet8Msg); HowTo = (Get-RandomizerHowTo); Untested = (Get-RandomizerUntestedMsg); ExePath = (Get-RandExePath)
}'''

    def fn(ctx):
        return dict(RandDefaultOptions=R.RandDefaultOptions, DotNet8Url=R.DotNet8Url, RandomizerUrl=R.RandomizerUrl, RandomizerTested=R.RandomizerTested,
                    RandHiItems=R.RandHiItems, RandHiSource=R.RandHiSource, RandCarryMinVersion=str(R.RandCarryMinVersion), RandOutputItems=R.RandOutputItems,
                    RandSettingsRoot=ctx.RandSettingsRoot, RandSettingsMap=ctx.RandSettingsMap, BundledDotNet=ctx.BundledDotNet, RandomHiDir=ctx.RandomHiDir,
                    RandPacksFile=ctx.RandPacksFile, RandomDir=ctx.RandomDir, RandomExe=ctx.RandomExe,
                    DotNet8Msg=R.get_dot_net8_msg(ctx), HowTo=R.get_randomizer_how_to(ctx), Untested=R.get_randomizer_untested_msg(ctx),
                    ExePath=R.get_rand_exe_path(ctx))
    case('常量和说明文字', reset, snippet, fn)


# ================================================================ 3. .NET 8（Test-DotNet8、DOTNET_ROOT 只给子进程）
def t_dotnet():
    nc = ('shared', 'Microsoft.NETCore.App')
    snippet = '$__r = @{ t = (Test-DotNet8); root = [string]$env:DOTNET_ROOT; root64 = [string]$env:DOTNET_ROOT_X64 }'

    def fn(ctx):
        e = R._rand_env(ctx)
        before = os.environ.get('DOTNET_ROOT')
        r = {'t': R.test_dot_net8(ctx), 'root': e.get('DOTNET_ROOT') or '', 'root64': e.get('DOTNET_ROOT_X64') or ''}
        assert os.environ.get('DOTNET_ROOT') == before        # 自己的环境变量不动
        return r

    def s(*dirs, hidden=False, files=()):
        def f():
            reset()
            for d in dirs:
                mkdir(os.path.join(*d), hidden=hidden)
            for p in files:
                mk(os.path.join(*p), b'x')
        return f
    case('Test-DotNet8 · 都没有', s(), snippet, fn)
    case('Test-DotNet8 · Program Files 里有 8.0.5', s((PF, 'dotnet') + nc + ('8.0.5',)), snippet, fn)
    case('Test-DotNet8 · 只有 7.x / 9.x', s((PF, 'dotnet') + nc + ('7.0.1',), (PF, 'dotnet') + nc + ('9.0.0',)), snippet, fn)
    case('Test-DotNet8 · 自带的 8.0.22（DOTNET_ROOT 指过去）', s((L, 'dotnet') + nc + ('8.0.22',)), snippet, fn)
    case('Test-DotNet8 · 自带的只有 7.x，继承的 DOTNET_ROOT 有 8.x', s((L, 'dotnet') + nc + ('7.0.0',), (DNR,) + nc + ('8.0.1',)), snippet, fn,
         env={'DOTNET_ROOT': DNR})
    case('Test-DotNet8 · 继承的 DOTNET_ROOT 没有 8.x', s((DNR,) + nc + ('6.0.1',)), snippet, fn, env={'DOTNET_ROOT': DNR})
    case('Test-DotNet8 · 隐藏的 8.0.1', s((PF, 'dotnet') + nc + ('8.0.1',), hidden=True), snippet, fn)
    case('Test-DotNet8 · 文件夹名就是「8」', s((PF, 'dotnet') + nc + ('8',)), snippet, fn)
    case('Test-DotNet8 · 8.0.1 是文件不是文件夹', s(files=[(PF, 'dotnet') + nc + ('8.0.1',)]), snippet, fn)


# ================================================================ 4. 随机器装了没有（Get-RandomizerStatus）
def t_status():
    snippet = '$s = Get-RandomizerStatus; $__r = @{ s = $s; h = $script:RandExeHash }'

    def fn(ctx):
        s = R.get_randomizer_status(ctx)
        return {'s': s, 'h': getattr(ctx, 'RandExeHash', None)}

    def s_none():
        reset()

    def s_nested(*parts, hidden=False):
        def f():
            reset()
            mkdir(RD)
            for p in parts:
                if hidden:
                    mkdir(os.path.join(RD, p.split('\\')[0]), hidden=True)
                mk(os.path.join(RD, p, 'EldenRingRandomizer.exe'), b'x')
        return f
    case('Get-RandomizerStatus · 没有 randomizer 文件夹', s_none, snippet, fn)
    case('Get-RandomizerStatus · 多了一层文件夹', s_nested('EldenRingRandomizer_v0.12.2'), snippet, fn)
    case('Get-RandomizerStatus · 多了两层', s_nested('a\\b'), snippet, fn)
    case('Get-RandomizerStatus · 多了三层（找不到）', s_nested('a\\b\\c'), snippet, fn)
    case('Get-RandomizerStatus · 两个都多一层（取文件系统顺序第一个）', s_nested('b1', 'a1'), snippet, fn)
    case('Get-RandomizerStatus · 在隐藏文件夹里（不算）', s_nested('hid', hidden=True), snippet, fn)

    def s_exe(diste=True, exe_dir=False):
        def f():
            reset()
            rand_install(RD, exe=not exe_dir, diste=diste)
            if exe_dir:
                d = mkdir(os.path.join(RD, 'EldenRingRandomizer.exe'))
                os.utime(d, ns=(T0, T0))
        return f
    case('Get-RandomizerStatus · 缺 diste', s_exe(diste=False), snippet, fn)
    case('Get-RandomizerStatus · 没测过的版本（假 exe）', s_exe(), snippet, fn)
    case('Get-RandomizerStatus · exe 是个文件夹', s_exe(exe_dir=True), snippet, fn)
    # 真的随机器（只读，算一次 45 MB 的哈希）
    case('Get-RandomizerStatus · 真的 randomizer（v0.12.2）', lambda: None, snippet, fn, root=None)

    # 缓存：大小和修改时间不变就不重算
    def fn2(ctx):
        reset()
        rand_install(RD)
        a = R.get_randomizer_status(ctx)
        ctx.RandExeHash.Hash = '8eb132f8e47a21dfffb3d0016c1117de2bb6c86b643ad9f8fba99079ab1c6cf4'    # 假装算过：没变就直接用缓存
        b = R.get_randomizer_status(ctx)
        os.utime(os.path.join(RD, 'EldenRingRandomizer.exe'), ns=(T0 + HOUR, T0 + HOUR))
        c = R.get_randomizer_status(ctx)
        return a.Tested, b.Tested, b.Version, c.Tested
    r, _ = py_only('缓存', fn2)
    check_true('Get-RandomizerStatus · 哈希按大小 + 修改时间缓存', r == (False, True, 'v0.12.2', False), r)


# ================================================================ 5. 设置文件在哪（Find-RandSettingsFile 等）、读设置
OTHER = os.path.join(FAR, 'old3')


def base_cfgs(a=True, b=True, c=True):
    rand_install(RD)
    out = {}
    if c:
        out['C'] = cfg('cccc', CFGN, T0 + 1 * HOUR, opt='v16 guess')
    if a:
        out['A'] = cfg('aaaa', CFG4, T0 + 2 * HOUR)
    if b:
        out['B'] = cfg('bbbb', CFG2, T0 + 3 * HOUR, opt='x v16 seed:1 item', dll=os.path.join(OTHER, 'randomizer', 'dll'))
    return out


def cpath(n):
    return os.path.join(AVALO, 'EldenRingRandomizer.Avalo_Path_' + n, '1.0.0.0', 'user.config')


def t_find():
    snippet = '$f = Find-RandSettingsFile; $__r = @{ f = $f; g = $script:RandSettingsGuess }'

    def fn(ctx):
        f = R.find_rand_settings_file(ctx)
        return {'f': f, 'g': getattr(ctx, 'RandSettingsGuess', None)}
    exe = os.path.join(RD, 'EldenRingRandomizer.exe')
    watch = [os.path.join(L, 'randomizer_settings_path.txt'), AVALO]

    def s(map_lines=None, **kw):
        a = kw.pop('a', True)
        extra = kw.pop('extra', None)

        def f():
            reset()
            base_cfgs(a=a, **kw)
            if map_lines is not None:
                write_map(*map_lines) if isinstance(map_lines, tuple) else write_map(map_lines)
            if extra:
                extra()
        return f
    case('Find-RandSettingsFile · 没有记录：按 dll 目录认出来、记下', s(), snippet, fn, watch)
    case('Find-RandSettingsFile · 两行记录、exe 对得上（大小写、空格不同）', s([cpath('cccc'), '  ' + exe.upper() + '  ']), snippet, fn, watch)
    case('Find-RandSettingsFile · 两行记录、exe 对不上', s([cpath('cccc'), 'D:\\other\\randomizer\\EldenRingRandomizer.exe']), snippet, fn, watch)
    case('Find-RandSettingsFile · 一行的旧记录（认得出）', s(([cpath('aaaa')], False, True, False)), snippet, fn, watch)
    case('Find-RandSettingsFile · 一行的旧记录（认不出 → 记作猜测）', s([cpath('cccc')]), snippet, fn, watch)
    case('Find-RandSettingsFile · 一行的旧记录、别的都认不出', s([cpath('cccc')], a=False), snippet, fn, watch)
    case('Find-RandSettingsFile · 记录里的文件不在了', s([os.path.join(TMP, 'nope.config'), exe]), snippet, fn, watch)
    case('Find-RandSettingsFile · 空的记录', s([]), snippet, fn, watch)
    case('Find-RandSettingsFile · 带 BOM、LF 的两行记录', s(([cpath('cccc'), exe], True, False, True)), snippet, fn, watch)
    case('Find-RandSettingsFile · 三行记录（只看两行）', s([cpath('cccc'), exe, 'junk']), snippet, fn, watch)
    case('Find-RandSettingsFile · 一个设置文件都没有', lambda: (reset(), rand_install(RD)), snippet, fn, watch)

    def same_time():
        cfg('aaab', CFG4, T0 + 2 * HOUR)
    case('Find-RandSettingsFile · 两份一样新（取文件系统顺序第一个）', s(extra=same_time), snippet, fn, watch)

    def hide_a():
        set_attr(cpath('aaaa'), 0x2)
        cfg('dddd', CFG4, T0)
        mk(cpath('aaaa') + '.dr.bak', CFG4.replace('{dll}', os.path.join(RD, 'dll')), T0 + 9 * HOUR)
        mk(os.path.join(AVALO, 'deep', 'x', 'y', 'user.config'), CFG4.replace('{dll}', os.path.join(RD, 'dll')).replace('{opt}', 'deep').replace('{exe}', ''),
           T0 + 8 * HOUR)
    case('Find-RandSettingsFile · 隐藏的不算、.dr.bak 不算、深层的也找', s(extra=hide_a), snippet, fn, watch)

    # Get-RandSetting
    def s_get():
        reset()
        base_cfgs()
        mk(os.path.join(XMLD, 'broken.config'), CFG4[:-30])
        mkdir(os.path.join(XMLD, 'adir.config'))
    names = ['Options', 'ExtraDlls', 'Exe', 'Mod', 'WindowPosition', 'Missing', 'options']
    files = [cpath('aaaa'), cpath('bbbb'), os.path.join(XMLD, 'broken.config'), os.path.join(XMLD, 'nope.config'), os.path.join(XMLD, 'adir.config'), '']
    snippet2 = '$__r = @(' + ', '.join('@(' + ', '.join('(Get-RandSetting %s %s)' % (psq(f), psq(n)) for n in names) + ')' for f in files) + ')'

    def fn2(ctx):
        return [[R.get_rand_setting(ctx, f, n) for n in names] for f in files]
    case('Get-RandSetting · 各种设置、文件不在 / 坏的 / 文件夹 / 空', s_get, snippet2, fn2)

    # Resolve-RandSettingsFile：认得出来就直接用（认不出来要打开随机器，PowerShell 那边不跑；Python 那边见第 14 组）
    case('Resolve-RandSettingsFile · 认得出来（不打开随机器）', s([cpath('cccc')]), '$__r = Resolve-RandSettingsFile %s' % psq(exe),
         lambda ctx: R.resolve_rand_settings_file(ctx, exe), watch)

    # Find-RandSettingsFileFor
    dirs = [RD, os.path.join(OTHER, 'randomizer'), os.path.join(OTHER, 'RANDOMIZER'), os.path.join(TMP, 'nowhere', 'randomizer')]
    snippet3 = '$__r = @(' + ', '.join('(Find-RandSettingsFileFor %s)' % psq(d) for d in dirs) + ')'
    case('Find-RandSettingsFileFor', s(), snippet3, lambda ctx: [R.find_rand_settings_file_for(ctx, d) for d in dirs], watch)


# ================================================================ 6. 这次用的选项（Get-RandomizeOptions）
def t_options():
    snippet = '$__r = Get-RandomizeOptions'
    fn = R.get_randomize_options
    watch = [os.path.join(L, 'randomizer_settings_path.txt')]

    def s(opt_a=OPT_E, packs=True, a=True, map_line=None, other_opt='x v16 seed:1 item'):
        def f():
            reset()
            rand_install(RD)
            cfg('cccc', CFGN, T0 + 1 * HOUR, opt='v16 guess  from\tC')
            if a:
                cfg('aaaa', CFG4, T0 + 2 * HOUR, opt=opt_a)
            cfg('bbbb', CFG2, T0 + 3 * HOUR, opt=other_opt, dll=os.path.join(OTHER, 'randomizer', 'dll'))
            if packs:
                new_pack(OTHER, regulation=False)
                mk(os.path.join(DRD, 'packs.txt'), (OTHER + '\r\n').encode())
            if map_line:
                write_map([map_line])
        return f
    case('Get-RandomizeOptions · 上次的设置（去掉种子）', s(), snippet, fn, watch)
    case('Get-RandomizeOptions · 这份没用过 → 旧版本随机器里的', s(opt_a='allmaps dlc'), snippet, fn, watch)
    case('Get-RandomizeOptions · 都没有 → 默认', s(opt_a='allmaps', packs=False), snippet, fn, watch)
    case('Get-RandomizeOptions · 旧版本的也没 v 号 → 默认', s(opt_a='allmaps', other_opt='nothing'), snippet, fn, watch)
    case('Get-RandomizeOptions · 大小写（ENEMY V16 Seed: seed2: ITEM）', s(opt_a='  ENEMY\tV16 Seed:12 seed2:99 ITEM dlc  '), snippet, fn, watch)
    case('Get-RandomizeOptions · 没 enemy 就补上', s(opt_a='v16 item'), snippet, fn, watch)
    case('Get-RandomizeOptions · 只有认不准的旧记录 → 照它', s(a=False, packs=False, map_line=cpath('cccc')), snippet, fn, watch)


# ================================================================ 7. Reset-RandMod / Update-ManualPreset / Save-PresetRecord
def t_reset():
    watch = [AVALO, os.path.join(RD, 'presets'), os.path.join(L, 'reroll', 'fake_args.json')]
    gexe = os.path.join(GAME, 'Game', 'eldenring.exe')

    def s(python=False, mode=None, opt=OPT_E, exe=True, have_cfg=True, broken=False):
        def f():
            reset(python=python)
            rand_install(RD, exe=exe)
            if have_cfg:
                cfg('aaaa', CFG4, T0 + 2 * HOUR, opt=opt)
            if broken:
                mk(cpath('aaaa'), ('<configuration><userSettings>' + os.path.join(RD, 'dll') + '\\x').encode(), T0)
            if mode is not None:
                mk(os.path.join(L, 'reroll', 'fake_mode.txt'), mode)
        return f

    def run(g):
        return ('$__r = Reset-RandMod %s' % psq(g)), (lambda ctx: R.reset_rand_mod(ctx, g))
    sn, fn = run(gexe)
    case('Reset-RandMod · 没有 Python：清合并、填游戏', s(), sn, fn, watch)
    sn0, fn0 = run('')
    case('Reset-RandMod · 没给游戏 exe', s(), sn0, fn0, watch)
    snx, fnx = run(os.path.join(TMP, 'nope', 'eldenring.exe'))
    case('Reset-RandMod · 游戏 exe 不在', s(), snx, fnx, watch)
    case('Reset-RandMod · 预设写好了（NAT 行）', s(python=True, mode='0\nsome output\nNAT: 1=0.01,2=0.02 \n'), sn, fn, watch)
    case('Reset-RandMod · 预设不限制（退出码 10）', s(python=True, mode='10\nNAT:x'), sn, fn, watch)
    case('Reset-RandMod · 设置是随机器默认值（没 v 号）→ 用整合包的选项', s(python=True, mode='0\nNAT:a\nnat: last ', opt='allmaps dlc'), sn, fn, watch)
    case('Reset-RandMod · 已经有 customenemy 不重复', s(python=True, mode='0', opt='v16 CustomEnemy enemy'), sn, fn, watch)
    case('Reset-RandMod · 没设置文件、也没随机器', s(have_cfg=False, exe=False), sn, fn, watch)
    # 有意的不同（2026-11-18 修）：PowerShell 版什么异常都接住、悄悄返回空（第一次打开随机器失败时看不到原因）；Python 版说出原因
    case('Reset-RandMod · 设置文件坏了（写不进去，说出原因）', s(python=True, mode='0\nNAT:1', have_cfg=False, broken=True), sn, fn, watch,
         expect=lambda ps, py: ps == '' and str(py).startswith('改随机器的设置时出错（'))

    case('Update-ManualPreset · 没有 Python', s(), '$__r = Update-ManualPreset', R.update_manual_preset, watch)
    case('Update-ManualPreset · 成功', s(python=True, mode='0\nNAT:9=0.5'), '$__r = Update-ManualPreset', R.update_manual_preset, watch)
    case('Update-ManualPreset · 失败（退出码 3）', s(python=True, mode='3\nNAT:9'), '$__r = Update-ManualPreset', R.update_manual_preset, watch)

    # fake_args.json 里的参数（除了种子）两边一样已经比过；这里再核对种子 = .dr_manual.preset 第二行
    def fn_seed(ctx):
        R.update_manual_preset(ctx)
        a = json.load(open(os.path.join(L, 'reroll', 'fake_args.json'), encoding='utf-8'))
        rec = open(os.path.join(RD, 'presets', '.dr_manual.preset'), encoding='utf-8').read().split('\n')
        return a[a.index('--seed') + 1] == rec[1] and 1 <= int(rec[1]) <= 2147483646, rec
    r, _ = py_only('seed', fn_seed, s(python=True, mode='0\nNAT:z'))
    check_true('Update-ManualPreset · 记下的种子就是传给 enemypreset 的', r[0] is True, r)

    pdir = os.path.join(RD, 'presets')
    for nm, d, seed, nat in (('正常', RD, 123, '1=0.1'), ('NAT 空', RD, '42', ''), ('presets 不在', os.path.join(TMP, 'nope'), 5, 'x')):
        case('Save-PresetRecord · ' + nm, lambda: (reset(), mkdir(pdir)), '$__r = Save-PresetRecord %s %s %s' % (psq(d), psq(seed), psq(nat)),
             lambda ctx, d=d, seed=seed, nat=nat: R.save_preset_record(ctx, d, seed, nat), [pdir])

    def fn_time(ctx):
        reset()
        mkdir(pdir)
        R.save_preset_record(ctx, RD, 1, '')
        t = open(os.path.join(pdir, '.dr_manual.preset'), encoding='utf-8').read().split('\n')[0]
        ticks = R._parse_dt_ticks(t)
        now = time.time_ns() // 100 + 621355968000000000
        return t, abs(now - ticks) < 10 ** 8
    r, _ = py_only('time', fn_time)
    check_true('Save-PresetRecord · 时间能读回来、就是现在（带时区）', r[1], r)


# ================================================================ 8. 日志（Read-SharedText、Get-LatestRandom、Get-RandomInfo）
def t_logs():
    fs = {'bom': b'\xef\xbb\xbfOptions \xe4\xb8\xad\r\nx', 'u16': '\ufeffhi 中'.encode('utf-16-le'), 'bad': b'ok \xff\xfe bad \xe4\xb8',
          'plain': 'Basic placements\nlast'.encode(), 'empty': b''}

    def s_shared():
        reset()
        for k, v in fs.items():
            mk(os.path.join(XMLD, k + '.txt'), v)
    names = list(fs) + ['missing']
    snippet = '$__r = @(' + ', '.join('(Read-SharedText %s)' % psq(os.path.join(XMLD, n + '.txt')) for n in names) + ')'
    case('Read-SharedText · BOM / UTF-16 / 坏字节 / 空 / 不在', s_shared, snippet, lambda ctx: [R.read_shared_text(ctx, os.path.join(XMLD, n + '.txt')) for n in names])
    # 随机器还开着日志（写入、不许删）时也读得到
    held = {}

    def unhold():
        if held.get('f'):
            held.pop('f').close()

    def s_held():
        unhold()
        s_shared()
        held['f'] = open(os.path.join(XMLD, 'plain.txt'), 'ab')
    sn = '$__r = Read-SharedText %s' % psq(os.path.join(XMLD, 'plain.txt'))
    try:
        case('Read-SharedText · 别的进程正开着写', s_held, sn, lambda ctx: R.read_shared_text(ctx, os.path.join(XMLD, 'plain.txt')))
    finally:
        unhold()

    sd = os.path.join(RD, 'spoiler_logs')

    def s(logs, regulation=True, extra=None, dr_manual=None, preset_dirs=True):
        def f():
            reset()
            rand_install(RD)
            rand_output(RD, logs, regulation)
            if dr_manual is not None:
                mk(os.path.join(RD, 'presets', '.dr_manual.preset'), dr_manual)
            if extra:
                extra()
        return f
    n1 = '2026-11-05_19.30.05_log_843925562_81236.txt'
    n2 = '2026-11-07_17.06.42_log_1271204388_81236.txt'
    base = [(n1, log_text('enemy v16 seed:843925562'), T0), (n2, log_text(OPT_E), T0 + HOUR)]
    sl = '$__r = Get-LatestRandom'
    si = '$__r = Get-RandomInfo %s' % psq(RD)
    fl = R.get_latest_random
    fi = (lambda ctx: R.get_random_info(ctx, RD))
    watch = [sd]
    case('Get-LatestRandom · 没有 spoiler_logs', lambda: (reset(), rand_install(RD)), sl, fl)
    case('Get-LatestRandom · spoiler_logs 是空的', lambda: (reset(), mkdir(sd)), sl, fl)
    case('Get-LatestRandom · 最新的一份', s(base), sl, fl)
    case('Get-LatestRandom · 物品随机', s(base + [('a_log_5_1.txt', log_text('item v16'), T0 + 2 * HOUR)]), sl, fl)
    case('Get-LatestRandom · 合并别的包做的', s([(n2, log_text('enemy', merged=True), T0)]), sl, fl)
    case('Get-LatestRandom · 选项行在 40 行以后（读不到）', s([(n2, log_text('enemy', pad=45), T0)]), sl, fl)
    case('Get-LatestRandom · 大小写（OPTIONS AND SEED: / ENEMY）', s([(n2, log_text('ENEMY Item', opt_prefix='OPTIONS AND SEED:'), T0)]), sl, fl)

    def junk():
        mk(os.path.join(sd, 'z_log_9_1.txt.hi_failed'), log_text('item'), T0 + 9 * HOUR)
        mk(os.path.join(sd, 'z_log_9_1.preset'), b'1\n', T0 + 9 * HOUR)
        mk(os.path.join(sd, 'zz_log_8_1.txt'), log_text('item'), T0 + 9 * HOUR, hidden=True)
        mk(os.path.join(sd, 'notalog.txt'), log_text('item'), T0 + 9 * HOUR)
        mk(os.path.join(sd, 'UP_LOG_7_1.TXT'), log_text('enemy UPPER'), T0 + 5 * HOUR)
    case('Get-LatestRandom · 不是日志的、隐藏的不算，大写扩展名算', s(base, extra=junk), sl, fl)
    case('Get-LatestRandom · 一样新的两份（取文件系统顺序第一个）', s([('b_log_2_1.txt', log_text('item'), T0), ('a_log_1_1.txt', log_text('enemy'), T0)]), sl, fl)
    case('Get-LatestRandom · 空的日志', s([(n2, b'', T0)]), sl, fl)

    case('Get-RandomInfo · 没有 regulation.bin', s(base, regulation=False), si, fi, watch)
    case('Get-RandomInfo · 没有日志', s([]), si, fi, watch)
    pre2 = n2.replace('.txt', '.preset')
    case('Get-RandomInfo · 有 .preset', s(base, extra=lambda: mk(os.path.join(sd, pre2), b' 197861029 \n1=0.0113,2=0.0137\n')), si, fi, watch)
    case('Get-RandomInfo · .preset 只有一行', s(base, extra=lambda: mk(os.path.join(sd, pre2), b'5')), si, fi, watch)
    old_o = '2025-11-01T00:00:00.0000000+00:00'     # 比日志（T0 前后）早
    case('Get-RandomInfo · 自己开随机器做的：照 .dr_manual.preset 补写 .preset', s(base, dr_manual=old_o + '\n 1468470570 \n 1=0.0127,2=0.0091 \n'), si, fi, watch)
    case('Get-RandomInfo · .dr_manual.preset 比日志新（不补）', s(base, dr_manual='2030-01-01T00:00:00.0000000-05:00\n1\n2\n'), si, fi, watch)
    # 日志时间 T0 = 1762000000.1234567 秒 = 2025-11-01T12:26:40.1234567Z：前后各差 100 纳秒、换时区写
    lt = datetime.datetime(2025, 11, 1, 12, 26, 40) + datetime.timedelta(hours=1)        # n2 的时间
    for nm, t in (('同一刻（-05:00 写的）', (lt - datetime.timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M:%S') + '.1234567-05:00'),
                  ('晚 100 纳秒', lt.strftime('%Y-%m-%dT%H:%M:%S') + '.1234568+00:00'),
                  ('早 100 纳秒（+08:00）', (lt + datetime.timedelta(hours=8)).strftime('%Y-%m-%dT%H:%M:%S') + '.1234566+08:00'),
                  ('Z 结尾', lt.strftime('%Y-%m-%dT%H:%M:%S') + '.1234567Z'),
                  ('没写时区（本地时间，早一天）', (datetime.datetime.fromtimestamp((T0 + HOUR) // 10 ** 9) - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')),
                  ('读不出的时间', 'not a time'),
                  ('种子空', old_o + '\n   \nnat')):
        body = t if '\n' in t else t + '\n7\n8\n'
        case('Get-RandomInfo · .dr_manual.preset ' + nm, s(base, dr_manual=body), si, fi, watch)
    case('Get-RandomInfo · .dr_manual.preset 只有两行', s(base, dr_manual=old_o + '\n7\n'), si, fi, watch)
    case('Get-RandomInfo · 选项里没 customenemy（不补）', s([(n2, log_text('enemy v16'), T0)], dr_manual=old_o + '\n7\n8\n'), si, fi, watch)
    case('Get-RandomInfo · 文件名里没有种子', s([('x_log_abc.txt', log_text('enemy'), T0)]), si, fi, watch)
    case('Get-RandomInfo · 合并的、选项行大小写', s([(n2, log_text('Enemy ITEM', merged=True, opt_prefix='options and seed:'), T0)]), si, fi, watch)
    case('Get-RandomInfo · 大写 .TXT（.preset 也照改）', s([('A_LOG_3_1.TXT', log_text('customenemy enemy'), T0)], dr_manual=old_o + '\n3\n4\n'), si, fi, watch)


def rel(p):
    return os.path.relpath(p, TMP)


N1 = '2026-11-05_19.30.05_log_843925562_81236.txt'
N2 = '2026-11-07_17.06.42_log_1271204388_81236.txt'


# ================================================================ 9. Get-BossFixedIds
def t_boss():
    sn = '$__r = @(Get-BossFixedIds)'
    fn = R.get_boss_fixed_ids

    def s(settings=None, mods=None, bom=False):
        def f():
            reset()
            if settings is not None:
                data = settings if isinstance(settings, bytes) else json.dumps(settings, ensure_ascii=False).encode('utf-8')
                mk(os.path.join(L, 'reroll', 'settings.json'), (b'\xef\xbb\xbf' if bom else b'') + data)
            for name, mj in (mods or {}).items():
                mk(os.path.join(L, 'reroll', 'data', 'bossmods', name, 'mod.json'),
                   mj if isinstance(mj, bytes) else json.dumps(mj, ensure_ascii=False).encode('utf-8'))
        return f
    full_mods = {'a': True, 'b': False, 'c': 'TRUE', 'd': 1, 'e': 2, '_x': True, 'f': True, 'g': True, 'h': True, 'i': True, 'j': 'yes',
                 'k': [True], 'l': [], 'm': None, 'n': 1.0}
    mj = {'a': {'fixed': [10000800, 11050800]}, 'b': {'fixed': [1]}, 'c': {'fixed': [1052380800]},
          'd': {'fixed': ['123', 2.5, 3.5, 0, '', None, '0', ' 7 ', True]}, 'e': {'fixed': [2]}, '_x': {'fixed': [3]},
          'g': b'{not json', 'h': {'arena': {}}, 'i': {'fixed': [11050800, 10000800]}, 'j': {'fixed': [4]},
          'k': {'fixed': 5}, 'l': {'fixed': [6, 6]}, 'm': {'fixed': [7]}, 'n': {'fixed': [8]}}
    case('Get-BossFixedIds · 没有 settings.json', s(), sn, fn)
    case('Get-BossFixedIds · settings.json 坏了', s(b'{x'), sn, fn)
    case('Get-BossFixedIds · 没有 boss_mods', s({'x': 1}), sn, fn)
    case('Get-BossFixedIds · mode off', s({'boss_mods': {'mode': 'off', 'mods': {'a': True}}}, mj), sn, fn)
    case('Get-BossFixedIds · mode OFF（不分大小写）', s({'boss_mods': {'mode': 'OFF', 'mods': {'a': True}}}, mj), sn, fn)
    case('Get-BossFixedIds · mods 是空的', s({'boss_mods': {'mode': 'auto', 'mods': {}}}, mj), sn, fn)
    case('Get-BossFixedIds · 各种开关 / 各种 fixed（带 BOM）', s({'boss_mods': {'mode': 'auto', 'mods': full_mods}}, mj, bom=True), sn, fn)
    case('Get-BossFixedIds · 都关着（不加萝蜜娜）', s({'boss_mods': {'mods': {'a': False, 'b': 0}}}, mj), sn, fn)
    case('Get-BossFixedIds · 开着的都没有 fixed', s({'boss_mods': {'mods': {'h': True, 'f': True}}}, mj), sn, fn)


# ================================================================ 10. 高难度世界：Remove-RandHiDir、Get-RandHiWorld
def hi_source(lo_log, fixed=(10000800, 2044450800), extra=None):
    d = {'lo_log': lo_log, 'hi_log': '2026-11-13_19.11.18_log_1271204388_81236.txt', 'seed': '1271204388', 'fixed': list(fixed or ()),
         'time': '2026-11-13 19:12:38'}
    if fixed is None:
        d.pop('fixed')
    d.update(extra or {})
    return json.dumps(d, indent=4).replace('\n', '\r\n').encode('utf-8')


def hi_world(d=HD, lo_log=N2, fixed=(10000800, 2044450800), regulation=True, raw=None):
    for n in R.RandHiItems:
        if n == 'regulation.bin':
            if regulation:
                mk(os.path.join(d, n), b'HIREG', T0 + 20)
        elif n.endswith('.toml'):
            mk(os.path.join(d, n), b'[hi]', T0 + 21)
        else:
            mk(os.path.join(d, n, 'f_' + n + '.bin'), n.encode(), T0 + 22, readonly=(n == 'map'))
    mk(os.path.join(d, 'spoiler_logs', '2026-11-13_19.11.18_log_1271204388_81236.txt'), log_text(OPT_E), T0 + 23)
    mk(os.path.join(d, 'spoiler_logs', '2026-11-13_19.11.18_log_1271204388_81236.preset'), b'1\n2\n', T0 + 24)
    mk(os.path.join(d, R.RandHiSource), raw if raw is not None else hi_source(lo_log, fixed), T0 + 25)


def t_hi():
    jt = os.path.join(TMP, 'jtarget')
    watch = [HD, jt]

    def s(kind):
        def f():
            reset()
            rm(jt)
            if kind == 'none':
                return
            if kind == 'file':
                mk(HD, b'i am a file')
                return
            hi_world()
            mk(os.path.join(HD, 'map', 'sub', 'deep.bin'), b'deep', readonly=True)
            if kind == 'junction':
                mk(os.path.join(jt, 'keep.txt'), b'keep me')
                import _winapi
                _winapi.CreateJunction(jt, os.path.join(HD, 'diste'))
            elif kind == 'diste_full':
                mk(os.path.join(HD, 'diste', 'Base', 'enemy.txt'), b'x')
            elif kind == 'diste_empty':
                mkdir(os.path.join(HD, 'diste'))
            elif kind == 'diste_file':
                mk(os.path.join(HD, 'diste'), b'x')
        return f
    sn = "try { Remove-RandHiDir; $__r = 'ok' } catch { $__r = 'err' }"

    def fn(ctx):
        try:
            R.remove_rand_hi_dir(ctx)
            return 'ok'
        except Exception:
            return 'err'
    for k, nm in (('none', '不在'), ('plain', '普通（只读文件也删）'), ('junction', 'diste 是联接（目标不动）'), ('diste_full', 'diste 是有东西的真文件夹（报错、都不删）'),
                  ('diste_empty', 'diste 是空文件夹'), ('diste_file', 'diste 是文件（报错）'), ('file', 'randomizer_hi 是个文件')):
        case('Remove-RandHiDir · ' + nm, s(k), sn, fn, watch)

    other_hi = os.path.join(PACKS, 'oh', 'randomizer_hi')
    other_lo = os.path.join(PACKS, 'oh', 'randomizer')

    def s2(**kw):
        lo_logs = kw.pop('lo_logs', [(N1, log_text('enemy'), T0), (N2, log_text(OPT_E), T0 + HOUR)])

        def f():
            reset()
            rand_install(RD)
            rand_output(RD, lo_logs)
            hi_world(**kw)
            rand_output(other_lo, [(N1, log_text('enemy'), T0 + 5 * HOUR)])
            hi_world(other_hi, lo_log=N1, fixed=(1, 2))
        return f
    sn2 = ('$__r = @{ a = (Get-RandHiWorld @()); b = (Get-RandHiWorld @(10000800)); c = (Get-RandHiWorld @(10000800, 5)); d = (Get-RandHiWorld $null); '
           "e = (Get-RandHiWorld @('10000800')); f = (Get-RandHiWorld 2044450800); g = (Get-RandHiWorld @(0)); "
           'h = (Get-RandHiWorld @(1) %s %s); i = (Get-RandHiWorld @(1, 3) %s %s); j = (Get-RandHiWorld @() %s) }'
           % (psq(other_hi), psq(other_lo), psq(other_hi), psq(other_lo), psq(other_hi)))

    def fn2(ctx):
        g = R.get_rand_hi_world
        return {'a': g(ctx, []), 'b': g(ctx, [10000800]), 'c': g(ctx, [10000800, 5]), 'd': g(ctx, None), 'e': g(ctx, ['10000800']), 'f': g(ctx, 2044450800),
                'g': g(ctx, [0]), 'h': g(ctx, [1], other_hi, other_lo), 'i': g(ctx, [1, 3], other_hi, other_lo), 'j': g(ctx, [], other_hi)}
    case('Get-RandHiWorld · 配套的', s2(), sn2, fn2)
    case('Get-RandHiWorld · lo_log 大小写不同也算', s2(lo_log=N2.upper()), sn2, fn2)
    case('Get-RandHiWorld · 不是跟着最近这次做的', s2(lo_log=N1), sn2, fn2)
    case('Get-RandHiWorld · 没有 regulation.bin', s2(regulation=False), sn2, fn2)
    case('Get-RandHiWorld · hi_source.json 坏了', s2(raw=b'{oops'), sn2, fn2)
    case('Get-RandHiWorld · 没有 fixed（当作一个 0）', s2(fixed=None), sn2, fn2)
    case('Get-RandHiWorld · fixed 是空的', s2(fixed=()), sn2, fn2)
    case('Get-RandHiWorld · 普通世界没有日志', s2(lo_logs=[]), sn2, fn2)
    case('Get-RandHiWorld · hi_source.json 是 null / 数组', s2(raw=b'[1,2]'), sn2, fn2)


# ================================================================ 11. 别的整合包：版本、packs.txt、找旧版本
OLD1 = os.path.join(PACKS, 'old1')
OLD2 = os.path.join(PACKS, 'old2')
OLD3 = os.path.join(FAR, 'old3')
OLD4 = os.path.join(BASE, 'old4')
OLD5 = os.path.join(BASE, 'old5')
OLD6 = os.path.join(PACKS, 'old6')
OLD7 = os.path.join(USER, 'Downloads', 'dl', 'old7')
GPACK = os.path.join(GAME, 'Game', 'gpack')
HIDP = os.path.join(PACKS, 'hidpack')


def s_packs(packs_txt=True, root_out=None, hi3=False):
    def f():
        reset()
        rand_install(RD)
        if root_out == 'valid':
            rand_output(RD, [(N2, log_text(OPT_E), T0 + 11 * HOUR)])
        elif root_out == 'merged':
            rand_output(RD, [(N2, log_text('enemy', merged=True), T0 + 11 * HOUR)])
        new_pack(OLD1, '0.10.12', [(N1, log_text('enemy v16 customenemy'), T0 + 5 * HOUR)])
        new_pack(OLD2, '0.6.5', [(N1, log_text('enemy'), T0 + 8 * HOUR)])
        new_pack(OLD3, '0.9.0', [(N2, log_text(OPT_E), T0 + 9 * HOUR)])
        new_pack(OLD4, '0.10.0', [(N1, log_text('enemy', merged=True), T0 + 10 * HOUR)])
        new_pack(OLD5, '0.10.0', regulation=False)
        new_pack(OLD6, '0.10.0', [(N1, log_text('dlc v16'), T0 + 10 * HOUR)])
        new_pack(OLD7, '0.10.0', [(N1, log_text('item v16'), T0 + 6 * HOUR)])
        new_pack(GPACK, '0.8.0', [(N1, log_text('enemy'), T0 + 6 * HOUR)])          # 和 old7 一样新：看 Sort-Object 怎么排
        new_pack(os.path.join(PACKS, 'nover'), None, [(N1, log_text('enemy'), T0)])
        new_pack(HIDP, '0.10.0', [(N1, log_text('enemy'), T0 + 12 * HOUR)])        # 最新的一份（隐藏的文件夹，只记在 packs.txt 里）
        if hi3:
            hi_world(os.path.join(HIDP, 'randomizer_hi'), lo_log=N1)
        set_attr(HIDP, 0x2)
        mkdir(os.path.join(FAR, 'notpack'))
        if packs_txt:
            lines = [OLD3, OLD1.upper() + '\\', ROOT, '', '   ', 'D:\\nowhere\\pack', os.path.join(FAR, 'notpack'), HIDP + '\\\\', OLD3]
            mk(os.path.join(DRD, 'packs.txt'), '\r\n'.join(lines) + '\r\n')
    return f


def t_packs():
    # Get-PackVersion
    vers = {'a': '0.10.13', 'b': '0.7', 'c': ' 0.8.5 \r\nsecond', 'd': 'abc', 'e': '', 'g': '\ufeff1.2.3.4', 'h': '1.2.3.4.5', 'i': '1', 'j': 'v0.9',
            'k': '1.-2', 'l': '0010.07'}

    def s_ver():
        reset()
        for k, v in vers.items():
            mk(os.path.join(PACKS, k, 'launcher', 'version.txt'), v)
    dirs = [os.path.join(PACKS, k) for k in list(vers) + ['missing']]
    sn = '$__r = @(foreach ($p in @(%s)) { $v = Get-PackVersion $p; if ($v) { $v.ToString() } else { \'null\' } })' % ', '.join(psq(d) for d in dirs)
    case('Get-PackVersion', s_ver, sn, lambda ctx: [str(R.get_pack_version(ctx, d) or 'null') for d in dirs])
    check_true('Get-PackVersion · 和 0.7 比（[version] 的比法）', R._ver('0.7') < R._ver('0.7.0') < R._ver('0.10') and not R._ver('0.7') < R._ver('0.7'))

    # Save-PackPath
    pf = os.path.join(DRD, 'packs.txt')

    def s_sp(lines=None, bom=False):
        def f():
            reset()
            if lines is not None:
                mk(pf, (b'\xef\xbb\xbf' if bom else b'') + ('\r\n'.join(lines) + '\r\n').encode('utf-8'))
        return f
    case('Save-PackPath · 第一次（建文件夹）', s_sp(), 'Save-PackPath', R.save_pack_path, [os.path.join(APPD, 'EldenRing')])
    many = ['E:\\p%d' % i for i in range(12)]
    case('Save-PackPath · 去重、去空行、最多 10 个（带 BOM）', s_sp([many[0], ROOT.upper() + '\\', '', '  ', many[1] + '\\\\', many[0]] + many[2:], bom=True),
         'Save-PackPath', R.save_pack_path, [os.path.join(APPD, 'EldenRing')])
    case('Save-PackPath · 中文路径', s_sp(['D:\\游戏\\暗黑重铸 v0.9', 'E:\\x']), 'Save-PackPath', R.save_pack_path, [os.path.join(APPD, 'EldenRing')])

    watch = [PACKS, FAR, BASE + '\\old4', OLD7, GPACK]
    case('Get-OtherPacks', s_packs(), '$__r = @(Get-OtherPacks)', R.get_other_packs, watch)
    case('Get-OtherPacks · 没有 packs.txt', s_packs(packs_txt=False), '$__r = @(Get-OtherPacks)', R.get_other_packs, watch)
    case('Get-OldRandom · 找到的每一个', s_packs(), '$__r = @(foreach ($p in (Get-OtherPacks)) { Get-OldRandom $p })',
         lambda ctx: [R.get_old_random(ctx, p) for p in R.get_other_packs(ctx)], watch)
    extra = [os.path.join(FAR, 'notpack'), os.path.join(PACKS, 'nover'), OLD5, OLD6, os.path.join(TMP, 'nope')]
    case('Get-OldRandom · 不是整合包 / 读不到版本 / 没结果 / 没开敌人随机', s_packs(), '$__r = @(%s)' % ', '.join('(Get-OldRandom %s)' % psq(p) for p in extra),
         lambda ctx: [R.get_old_random(ctx, p) for p in extra], watch)
    case('Find-OldRandoms（一样新的两份看 Sort-Object 的顺序）', s_packs(), '$__r = @(Find-OldRandoms)', R.find_old_randoms, watch)
    case('Find-OldRandoms · 没有 packs.txt', s_packs(packs_txt=False), '$__r = @(Find-OldRandoms)', R.find_old_randoms, watch)

    rdirs = [os.path.join(OLD1, 'randomizer', 'spoiler_logs'), PACKS, PACKS + '\\', BASE, ROOT, os.path.join(TMP, 'w', 'empty'), os.path.join(TMP, 'nope', 'x'),
             os.path.join(USER, 'Downloads'), os.path.join(FAR, 'notpack'), '']

    def s_res():
        s_packs()()
        mkdir(os.path.join(TMP, 'w', 'empty'))
    sn = '$__r = @(foreach ($d in @(%s)) { try { Resolve-PackDir $d } catch { \'err\' } })' % ', '.join(psq(d) for d in rdirs)

    def fn(ctx):
        out = []
        for d in rdirs:
            try:
                out.append(R.resolve_pack_dir(ctx, d))
            except Exception:
                out.append('err')
        return out
    case('Resolve-PackDir', s_res, sn, fn, watch)
    for nm, ro in (('还没有随机结果', None), ('有了', 'valid'), ('合并别的包做的', 'merged')):
        case('Test-NeedOldRandom · ' + nm, s_packs(root_out=ro), '$__r = Test-NeedOldRandom', R.test_need_old_random)


# ================================================================ 12. 复制、沿用
def t_carry():
    src = os.path.join(TMP, 'csrc')
    dst = os.path.join(TMP, 'cdst')
    mb = 1048576

    def s_copy(conflict=False):
        def f():
            reset()
            rm(src)
            rm(dst)
            rand_output(src, [(N2, log_text(OPT_E), T0 + HOUR)], big=int(2.5 * mb))
            mk(os.path.join(src, 'event', 'x1.bin'), b'\0' * int(0.6 * mb), T0)
            mk(os.path.join(dst, 'map', 'mapstudio', 'ro.msb.dcx'), b'old readonly', T0 - HOUR, readonly=True)
            mk(os.path.join(dst, 'map', 'extra.bin'), b'dst only', T0 - HOUR)
            mk(os.path.join(dst, 'regulation.bin'), b'OLD', T0 - HOUR, readonly=True)
            if conflict:
                mkdir(os.path.join(dst, 'map', 'mapstudio', 'm10_00_00_00.msb.dcx'))
        return f
    items = R.RandOutputItems + ['missing_item']
    sn = '$__r = Copy-RandItems %s %s @(%s)' % (psq(src), psq(dst), ', '.join(psq(i) for i in items))
    case('Copy-RandItems · 目录、文件、只读的、隐藏的、修改时间', s_copy(), sn, lambda ctx: R.copy_rand_items(ctx, src, dst, items), [dst], mtimes=[rel(dst)])
    # 出错时：以前是「robocopy 返回 N」，现在是系统的错误说明，只比开头（有意的不同）。源文件被别的程序独占着打不开：
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    locked = os.path.join(src, 'map', 'mapstudio', 'm10_00_00_00.msb.dcx')
    res = []
    for side in ('ps', 'py'):
        s_copy()()
        h = k.CreateFileW(locked, 0x80000000, 0, None, 3, 0, None)          # GENERIC_READ，不共享
        try:
            if side == 'ps':
                res.append(harness.ps_call(sn, ENV, root=ROOT))
            else:
                res.append(harness.py_call(lambda ctx: R.copy_rand_items(ctx, src, dst, items), ENV, root=ROOT))
        finally:
            k.CloseHandle(h)
    (pr, po), (yr, yo) = res
    check_true('Copy-RandItems · 源文件打不开：返回「复制 map 失败（…）」（原因的写法不同，有意的）',
               str(pr).startswith('复制 map 失败（robocopy 返回 ') and str(yr).startswith('复制 map 失败（') and norm_out(po) == norm_out(yo), (pr, yr, po, yo))
    # 目标那里是个文件夹：robocopy 跳过它、照样返回成功（结果不完整）；Python 报失败（有意的不同；沿用时目标都先删掉了，碰不到）
    s_copy(conflict=True)()
    pr, po = harness.ps_call(sn, ENV, root=ROOT)
    s_copy(conflict=True)()
    yr, yo = harness.py_call(lambda ctx: R.copy_rand_items(ctx, src, dst, items), ENV, root=ROOT)
    check_true('Copy-RandItems · 目标是文件夹：PowerShell 当成功、Python 报失败（有意的不同）',
               pr == '' and str(yr).startswith('复制 map 失败（') and norm_out(po)[:1] == norm_out(yo), (pr, yr, po, yo))

    # Copy-OldRandHiWorld
    oldh = os.path.join(PACKS, 'oldh')

    def s_hi(kind):
        def f():
            reset()
            rand_install(RD)
            rand_output(RD, [(N1 if kind == 'mismatch' else N2, log_text(OPT_E), T0 + HOUR)])
            new_pack(oldh, '0.10.12', [(N2, log_text(OPT_E), T0 + HOUR)])
            if kind != 'nohi':
                hi_world(os.path.join(oldh, 'randomizer_hi'), lo_log=N2)
            if kind == 'existing':
                mk(os.path.join(HD, 'stale', 'old.bin'), b'stale', readonly=True)
        return f
    sn = '$__r = Copy-OldRandHiWorld %s' % psq(oldh)
    for k, nm in (('nohi', '旧版本没有'), ('ok', '配套的'), ('mismatch', '复制完对不上（不要）'), ('existing', '先删掉原来的')):
        case('Copy-OldRandHiWorld · ' + nm, s_hi(k), sn, lambda ctx: R.copy_old_rand_hi_world(ctx, oldh), [HD], mtimes=[rel(HD)])

    # Invoke-CarryRandom
    watch = [RD, HD, PACKS, FAR]
    mt = [rel(RD), rel(HD)]

    def run(frm):
        return '$__r = Invoke-CarryRandom %s' % psq(frm), (lambda ctx: R.invoke_carry_random(ctx, frm))

    def s_noexe():
        s_packs()()
        rm(os.path.join(RD, 'EldenRingRandomizer.exe'))
    sn, fn = run(OLD1)
    case('Invoke-CarryRandom · 随机器没装', s_noexe, sn, fn, watch, mt, seconds=True)
    case('Invoke-CarryRandom · 已经有了（不用沿用）', s_packs(root_out='valid'), sn, fn, watch, mt, seconds=True)
    case('Invoke-CarryRandom · 指定旧版本', s_packs(), sn, fn, watch, mt, seconds=True)
    case('Invoke-CarryRandom · 指定旧版本里面的一层', s_packs(), *run(os.path.join(OLD1, 'randomizer')), watch, mt, seconds=True)
    case('Invoke-CarryRandom · 指定的是自己', s_packs(), *run(os.path.join(ROOT, 'launcher')), watch, mt, seconds=True)
    case('Invoke-CarryRandom · 指定的太旧', s_packs(), *run(OLD2), watch, mt, seconds=True)
    case('Invoke-CarryRandom · 指定的不是整合包', s_packs(), *run(os.path.join(TMP, 'nope')), watch, mt, seconds=True)
    case('Invoke-CarryRandom · 自动找最新的（带死亡以上世界）', s_packs(hi3=True), *run(''), watch, mt, seconds=True)
    case('Invoke-CarryRandom · 合并的结果换掉', s_packs(root_out='merged'), sn, fn, watch, mt, seconds=True)

    def s_nothing():
        reset()
        rand_install(RD)
    case('Invoke-CarryRandom · 哪里都没有', s_nothing, *run(''), watch, mt, seconds=True)


# ================================================================ 13. 动作：一键重随敌人、补做高难度世界、打开随机器
def t_actions():
    nc = ('shared', 'Microsoft.NETCore.App')

    def s(install=True, cfgs=True, boss=False, dotnet=True):
        def f():
            reset()
            if install:
                rand_install(RD)
            if cfgs:
                cfg('aaaa', CFG4, T0 + 2 * HOUR)
            if boss:
                mk(os.path.join(L, 'reroll', 'settings.json'), json.dumps({'boss_mods': {'mode': 'auto', 'mods': {'a': True}}}))
                mk(os.path.join(L, 'reroll', 'data', 'bossmods', 'a', 'mod.json'), json.dumps({'fixed': [10000800]}))
            if dotnet:
                mkdir(os.path.join(L, 'dotnet', *nc, '8.0.22'))
        return f
    watch = [AVALO, RD, os.path.join(L, 'randomizer_settings_path.txt')]
    dry = {'DryRun': True}
    case('Invoke-RandEnemyAction · 随机器没装', s(install=False), '$__r = Invoke-RandEnemyAction', R.invoke_rand_enemy_action, watch)
    case('Invoke-RandEnemyAction · -DryRun', s(), '$DryRun = $true; $__r = Invoke-RandEnemyAction', R.invoke_rand_enemy_action, watch, ctx_args=dry)
    case('Invoke-RandHiAction · 随机器没装', s(install=False), '$__r = Invoke-RandHiAction', R.invoke_rand_hi_action, watch)
    case('Invoke-RandHiAction · 没开 Boss 模组', s(), '$__r = Invoke-RandHiAction', R.invoke_rand_hi_action, watch)
    case('Invoke-RandHiAction · Boss 模组 + -DryRun', s(boss=True), '$DryRun = $true; $__r = Invoke-RandHiAction', R.invoke_rand_hi_action, watch, ctx_args=dry)
    case('Invoke-Randomizer · 随机器没装', s(install=False), '$__r = Invoke-Randomizer', R.invoke_randomizer, watch)
    case('Invoke-Randomizer · 没有 .NET 8', s(dotnet=False), '$__r = Invoke-Randomizer', R.invoke_randomizer, watch)
    case('Invoke-Randomizer · -DryRun', s(), '$DryRun = $true; $__r = Invoke-Randomizer', R.invoke_randomizer, watch, ctx_args=dry)

    # 真的往下走：写好设置以后启动「随机器」——这里的 exe 是假的（文本），两边都启动不了，到此为止
    def fn(ctx):
        try:
            R.invoke_randomizer(ctx)
            return 'started'
        except OSError:
            return 'start failed'
    case('Invoke-Randomizer · 写设置，启动（假 exe 启动失败）', s(), "try { Invoke-Randomizer; $__r = 'started' } catch { $__r = 'start failed' }", fn, watch)


# ================================================================ 14. 第 2 步（UI 自动化）：真的打开随机器的部分在 rand_parity.py（和 PowerShell 版
#    各生成一次死亡以上世界、逐字节比）/ randenemy_smoke.py（一键重随敌人走一遍）实跑；这里只比不开窗口的：主按钮的各种写法
def t_stubs():
    real_rd = os.path.join(harness.PALY, 'randomizer')          # 只读：随机器自己的界面文字 diste\Messages\*.json
    if not os.path.isdir(os.path.join(real_rd, 'diste', 'Messages')):
        print('SKIP 主按钮的写法（没装随机器）')
        return
    pr, _ = harness.ps_call('$RandomDir = %s\n$__r = @(Get-RandButtonNames)' % psq(real_rd), ENV)

    def fn(ctx):
        ctx.RandomDir = real_rd
        return R.get_rand_button_names(ctx)
    yr, _ = harness.py_call(fn, ENV)
    check_true('Get-RandButtonNames · 随机器主按钮的各种写法（集合一样，不分大小写）',
               sorted(x.casefold() for x in pr or []) == sorted(x.casefold() for x in yr or []) and len(yr) > 3, (pr, yr))

    # 启动随机器的环境变量只给子进程
    def fn(ctx):
        before = dict(os.environ)
        e = R._rand_env(ctx)
        return e.get('DOTNET_ROOT') == ctx.BundledDotNet and e.get('DOTNET_ROOT_X64') == ctx.BundledDotNet and dict(os.environ) == before
    r, _ = py_only('env', fn, lambda: (reset(), mkdir(os.path.join(L, 'dotnet', 'shared', 'Microsoft.NETCore.App', '8.0.22'))))
    check_true('_rand_env · 自带的 .NET 只给随机器子进程', r is True, r)


GROUPS = [('xml', t_xml), ('sort', t_sort), ('consts', t_consts), ('dotnet', t_dotnet), ('status', t_status), ('find', t_find), ('options', t_options),
          ('reset', t_reset), ('logs', t_logs), ('boss', t_boss), ('hi', t_hi), ('packs', t_packs), ('carry', t_carry), ('actions', t_actions),
          ('stubs', t_stubs)]


def main():
    want = sys.argv[1:]
    try:
        for name, fn in GROUPS:
            if not want or name in want:
                print('\n######## ' + name)
                fn()
    finally:
        reset()
        if os.path.isdir(PY_ON):
            os.rename(PY_ON, PY_OFF)
        rm(TMP)
    bad = [n for n, ok in RESULTS if not ok]
    print('\n共 %d 项，OK %d，DIFF %d' % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
    for n in bad:
        print('  DIFF ' + n)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
