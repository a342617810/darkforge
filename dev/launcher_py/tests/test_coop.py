# -*- coding: utf-8 -*-
"""coop 模块（launcher.ps1 的「联机」一节）的对照测试：同样的输入交给旧的 PowerShell 函数和新的 dfl\\coop.py，比返回值、输出的行、写出的文件（逐字节）。

- 整合包目录用 copy_root 的副本；Seamless Co-op 是假的（dll\\SeamlessCoop\\ersc.dll 带一个假的 PE 头 + ersc_settings.ini），游戏目录是副本里的 game\\。
- 别的模块的函数两边都换成一样的替身：Resolve-GameRoot、Get-SteamGameLanguage、Get-RandomizerStatus、Get-RandomInfo、Get-BossMods、
  Invoke-RandomizeEnemies、Invoke-Launch、Find-Python、剪贴板（不碰真的剪贴板）、Get-Date（备份文件名固定）、New-CoopPassword（开房生成的密码固定）。
  Python 这边替身挂在 dfl.gamepath / dfl.randomizer / dfl.launch / dfl.pytool / dfl.win 上（模块还没写好就放一个假的）。
- 联机核对码（Get-CoopFingerprint）只读，在真的整合包上跑真的 coopfp.py。
- 用到联机码压缩（dfl\\coopcode.py，另一个人在写）的用例：coopcode.py 还没有就跳过并打印 SKIP。

有意的不同（单独说明，不算 DIFF）：
- 出错时的报错文字（$_.Exception.Message）：.NET 和 Python 的说法不一样，这几处用 norm 只比到「：」为止。"""
import base64
import ctypes
import datetime
import importlib
import json
import os
import shutil
import stat
import struct
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

import dfl  # noqa: E402
from dfl import coop, core, win  # noqa: E402
from dfl.core import Rec  # noqa: E402

REAL_PY = os.path.join(H.LAUNCHER, 'python', 'python.exe')
STAMP = '20990101_000000'
PW_FIXED = 'Tst2pw3456789abc'
ORIG_NEW_PW = coop.new_coop_password
RESULTS = {'ok': 0, 'diff': 0, 'skip': 0}

try:
    from dfl import coopcode  # noqa: F401
    HAVE_COOPCODE = True
except Exception:
    HAVE_COOPCODE = False


# ---------------------------------------------------------------- PowerShell 字面量
def ps_lit(v):
    if v is None:
        return '$null'
    if v is True:
        return '$true'
    if v is False:
        return '$false'
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, datetime.datetime):
        return "[datetime]'%s'" % v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, (list, tuple)):
        return '@(' + ', '.join(ps_lit(x) for x in v) + ')'
    if isinstance(v, dict):
        return '[pscustomobject]@{ ' + '; '.join('%s = %s' % (k, ps_lit(x)) for k, x in v.items()) + ' }'
    s = str(v)
    parts, buf = [], ''
    for ch in s:
        o = ord(ch)
        if o < 0x20 or o in (0x7f, 0x85, 0x2028, 0x2029, 0xfeff) or ch in '\u2018\u2019\u201a\u201b':
            if buf:
                parts.append("'" + buf.replace("'", "''") + "'")
                buf = ''
            parts.append('([string][char]0x%04x)' % o)
        else:
            buf += ch
    if buf or not parts:
        parts.append("'" + buf.replace("'", "''") + "'")
    return '(' + ' + '.join(parts) + ')'


# ---------------------------------------------------------------- 替身
RI = dict(Time=datetime.datetime(2026, 11, 10, 12, 34, 56), Seed='843925562', Merged=False,
          Options='allmaps bossbgm customenemy dlc enemy v16 bias:20 seed:843925562', PresetSeed='197861029',
          PresetNat='1=0.0113,2=0.0137,3=0.0056')
DEFAULT_CFG = dict(gr=None, lang='schinese', rs=dict(Ok=True, Msg=''), ri=RI, boss=False, clip_in=None, clip_fail=False,
                   rand_res=dict(Ok=True, Msg='重随好了'), py=None)
CFG = {}
CLIP = {}


def ps_stubs(cfg):
    ri = cfg['ri']
    return '\n'.join([
        "function Get-Date { param([string]$Format) if ($Format) { return '%s' } return [datetime]'2099-01-01' }" % STAMP,
        "function Set-Clipboard { param($Value) if ($global:__clipFail) { throw 'clip fail' }; $global:__clip = $Value }",
        "function Get-Clipboard { param([switch]$Raw) return $global:__clipIn }",
        "function Resolve-GameRoot { param([switch]$Refresh) return $global:__gr }",
        "function Get-SteamGameLanguage { return $global:__lang }",
        "function Get-RandomizerStatus { return $global:__rs }",
        "function Get-RandomInfo { param([string]$RandDir) Write-Host 'STUB ri'; return $global:__ri }",
        "function Get-BossMods { param([bool]$Coop = $false) Write-Host ('STUB boss ' + $Coop); return [pscustomobject]@{ Keys = $global:__bossKeys } }",
        "function Invoke-RandomizeEnemies { param([string]$GameExe, $Fixed = $null) "
        "Write-Host ('STUB rand ' + $GameExe + ' | ' + $Fixed.PresetSeed + ' | ' + $Fixed.Nat + ' | ' + $Fixed.Options); return $global:__randRes }",
        "function Invoke-Launch { param([bool]$Rand, [bool]$Coop = $false) Write-Host ('STUB Invoke-Launch ' + $Rand + ' ' + $Coop) }",
        "function Find-Python { return $global:__py }",
        "function New-CoopPassword { return '%s' }" % PW_FIXED,
        '$global:__clip = $null',
        '$global:__clipFail = ' + ps_lit(cfg['clip_fail']),
        '$global:__clipIn = ' + ps_lit(cfg['clip_in']),
        '$global:__gr = ' + ps_lit(cfg['gr']),
        '$global:__lang = ' + ps_lit(cfg['lang']),
        '$global:__rs = @{ Ok = %s; Msg = %s }' % (ps_lit(cfg['rs']['Ok']), ps_lit(cfg['rs']['Msg'])),
        '$global:__ri = ' + ps_lit(ri),
        '$global:__bossKeys = ' + ("@('k1')" if cfg['boss'] else '@()'),
        '$global:__randRes = @{ Ok = %s; Msg = %s }' % (ps_lit(cfg['rand_res']['Ok']), ps_lit(cfg['rand_res']['Msg'])),
        '$global:__py = ' + ps_lit(cfg['py']),
    ]) + '\n'


def _fake_module(name):
    full = 'dfl.' + name
    try:
        return importlib.import_module(full)
    except Exception:
        m = types.ModuleType(full)
        sys.modules[full] = m
        setattr(dfl, name, m)
        return m


def install_fakes():
    gp = _fake_module('gamepath')
    gp.resolve_game_root = lambda ctx, Refresh=False: CFG['gr']
    gp.get_steam_game_language = lambda ctx: CFG['lang']
    rz = _fake_module('randomizer')
    rz.get_randomizer_status = lambda ctx: Rec(**CFG['rs'])

    def get_random_info(ctx, RandDir):
        core.host('STUB ri')
        return Rec(**CFG['ri']) if CFG['ri'] is not None else None
    rz.get_random_info = get_random_info

    def invoke_randomize_enemies(ctx, GameExe, Fixed=None):
        core.host('STUB rand ' + GameExe + ' | ' + str(Fixed.PresetSeed) + ' | ' + str(Fixed.Nat) + ' | ' + str(Fixed.Options))
        return Rec(**CFG['rand_res'])
    rz.invoke_randomize_enemies = invoke_randomize_enemies
    la = _fake_module('launch')

    def get_boss_mods(ctx, Coop=False):
        core.host('STUB boss ' + str(bool(Coop)))
        return Rec(Keys=['k1'] if CFG['boss'] else [])
    la.get_boss_mods = get_boss_mods
    la.invoke_launch = lambda ctx, Rand, Coop=False: core.host('STUB Invoke-Launch %s %s' % (bool(Rand), bool(Coop)))
    from dfl import pytool
    pytool.find_python = lambda ctx: CFG['py']

    def clip_set(t):
        if CFG['clip_fail']:
            raise OSError('clip fail')
        CLIP['out'] = t
        return True
    win.clipboard_set = clip_set
    win.clipboard_get = lambda: CFG['clip_in'] or ''
    coop._stamp = lambda: STAMP
    coop.new_coop_password = lambda: PW_FIXED


# ---------------------------------------------------------------- 假的整合包副本
TMP = tempfile.mkdtemp(prefix='dftest_coop_')
ENV = H.fake_env(TMP)
ROOT = H.copy_root(TMP)
PRISTINE = os.path.join(TMP, 'pristine')
os.makedirs(PRISTINE)
shutil.copy2(os.path.join(H.LAUNCHER, 'reroll', 'settings.json'), os.path.join(PRISTINE, 'settings.json'))
shutil.copy2(os.path.join(H.LAUNCHER, 'version.txt'), os.path.join(PRISTINE, 'version.txt'))
shutil.copytree(os.path.join(H.LAUNCHER, 'ersc_locale'), os.path.join(PRISTINE, 'ersc_locale'), ignore=shutil.ignore_patterns('__pycache__'))
VERSION = core.read_text(os.path.join(PRISTINE, 'version.txt')).strip()
MUT = ['dll', 'game', 'out', 'randomizer', 'diag', 'launcher\\reroll', 'launcher\\ersc_locale', 'launcher\\version.txt']
GAME = os.path.join(ROOT, 'game')


def _rm(p):
    def onerr(fn, path, exc):
        os.chmod(path, stat.S_IWRITE)
        fn(path)
    if os.path.isdir(p):
        shutil.rmtree(p, onerror=onerr)
    elif os.path.exists(p):
        os.chmod(p, stat.S_IWRITE)
        os.remove(p)


def reset():
    for rel in MUT:
        _rm(os.path.join(ROOT, rel))
    os.makedirs(os.path.join(ROOT, 'launcher', 'reroll', 'state'))
    shutil.copy2(os.path.join(PRISTINE, 'settings.json'), os.path.join(ROOT, 'launcher', 'reroll', 'settings.json'))
    shutil.copy2(os.path.join(PRISTINE, 'version.txt'), os.path.join(ROOT, 'launcher', 'version.txt'))
    shutil.copytree(os.path.join(PRISTINE, 'ersc_locale'), os.path.join(ROOT, 'launcher', 'ersc_locale'))
    os.makedirs(os.path.join(ROOT, 'dll', 'dark_core'))
    os.makedirs(os.path.join(GAME, 'Game'))


def snap():
    out = {}
    for rel in MUT:
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p):
            out[rel.replace('\\', '/')] = open(p, 'rb').read()
        elif os.path.isdir(p):
            for k, v in H.tree(p).items():
                out[rel.replace('\\', '/') + '/' + k] = v
    return out


def wfile(rel, data, mtime=None, hidden=False):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data.encode('utf-8') if isinstance(data, str) else data)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    if hidden:
        ctypes.windll.kernel32.SetFileAttributesW(p, 2)
    return p


def hide(rel):
    ctypes.windll.kernel32.SetFileAttributesW(os.path.join(ROOT, rel), 2)


def fake_pe(ts=0x6ae0ad1a, soi=0xd65000, pe=0x80, size=1024):
    b = bytearray(size)
    b[0:2] = b'MZ'
    struct.pack_into('<i', b, 0x3C, pe)
    if 0 <= pe and pe + 4 <= size:
        b[pe:pe + 4] = b'PE\0\0'
    for off, v in ((pe + 8, ts), (pe + 80, soi)):
        if 0 <= off and off + 4 <= size:
            struct.pack_into('<I', b, off, v)
    return bytes(b)


INI = ('; Seamless Co-op 设置\r\n[GAMEPLAY]\r\nallow_invaders = 1 ; 入侵\r\ndeath_debuffs = 1\r\nallow_summons = 1\r\n'
       'overhead_player_display = 0\r\nskip_splash_screens = 0\r\ndefault_boot_master_volume = 5\r\nalways_spectate_on_death = 0\r\n\r\n'
       '[SCALING]\r\nenemy_health_scaling = 35\r\nenemy_damage_scaling = 0\r\nenemy_posture_scaling = 15\r\nboss_health_scaling = 100\r\n'
       'boss_damage_scaling = 0\r\nboss_posture_scaling = 20\r\n\r\n[PASSWORD]\r\ncooppassword = \r\n\r\n[SAVE]\r\nsave_file_extension = co2\r\n\r\n'
       '[LANGUAGE]\r\nmod_language_override = \r\n')
INI_OK = (INI.replace('allow_invaders = 1 ; 入侵', 'allow_invaders = 0 ; 入侵').replace('always_spectate_on_death = 0', 'always_spectate_on_death = 1')
          .replace('cooppassword = \r\n', 'cooppassword = abc123\r\n').replace('mod_language_override = \r\n', 'mod_language_override = english\r\n'))
ERSC_DIR = 'dll\\SeamlessCoop'


def mk_ersc(ini=INI, sub=ERSC_DIR, bom=False, raw=None, pe=None, dll_name='ersc.dll'):
    wfile(sub + '\\' + dll_name, pe if pe is not None else fake_pe())
    if raw is not None:
        wfile(sub + '\\ersc_settings.ini', raw)
    elif ini is not None:
        wfile(sub + '\\ersc_settings.ini', (b'\xef\xbb\xbf' if bom else b'') + ini.encode('utf-8'))


def b64(s):
    return base64.b64encode(s.encode('utf-8')).decode('ascii')


def dr3(m='plain', pw='abc123', w='low', sc='allow_summons=1,boss_health_scaling=100', v=None, extra=''):
    return 'DR3|v=%s|m=%s|pw=%s|w=%s|sc=%s%s' % (VERSION if v is None else v, m, b64(pw) if pw is not None else '', w, sc, extra)


RAND_EXTRA = '|em=1|bp=0|ps=197861029|nat=1=0.0113,2=0.0137,3=0.0056|o=allmaps bossbgm customenemy dlc enemy v16 bias:20 seed:843925562'


# ---------------------------------------------------------------- 对照
def jsonable(v):
    return json.loads(json.dumps(v, ensure_ascii=False, default=str))


def cut_after(marker):
    """出错时的报错文字两边不一样（.NET / Python）：带 marker 的行只比到 marker 为止"""
    def f(lines):
        return [l[:l.index(marker) + len(marker)] if marker in l else l for l in lines]
    return f


def case(name, ps, py, setup=None, cfg=None, dry=False, bossworld='', norm=None, need_coopcode=False):
    if need_coopcode and not HAVE_COOPCODE:
        print('SKIP ' + name + '（还没有 dfl\\coopcode.py）')
        RESULTS['skip'] += 1
        return
    c = dict(DEFAULT_CFG)
    c['gr'] = GAME
    c.update(cfg or {})
    reset()
    if setup:
        setup()
    snippet = ps_stubs(c)
    if dry:
        snippet += '$DryRun = $true\n'
    if bossworld:
        snippet += '$BossWorld = %s\n' % ps_lit(bossworld)
    snippet += 'try {\n' + ps + '\n} catch { $__x = \'EXC\' }\n$__r = @{ r = $__x; clip = $global:__clip }\n'
    r_ps, out_ps = H.ps_call(snippet, ENV, root=ROOT)
    t_ps = snap()
    reset()
    if setup:
        setup()
    CFG.clear()
    CFG.update(c)
    CLIP.clear()

    def run(ctx):
        try:
            x = py(ctx)
        except Exception:
            x = 'EXC'
        return {'r': x, 'clip': CLIP.get('out')}
    t0 = snap()                                   # 跑之前（备份文件该和这时的原文件一样）
    r_py, out_py = H.py_call(run, ENV, root=ROOT, DryRun=dry, BossWorld=bossworld)
    r_py = jsonable(r_py)
    t_py = snap()
    if norm:
        out_ps, out_py = norm(out_ps), norm(out_py)
    ok = H.same(name + ' · 结果', r_ps, r_py)
    ok = H.same(name + ' · 输出', out_ps, out_py) and ok
    d = H.diff_tree(t_py, t_ps)
    # 有意的不同（2026-11-18 修）：改 ini 前的备份 .bak_<时间>，同一秒里改好几项时 Python 版只留第一次的、就是改之前的原文件；
    # PowerShell 版每改一项都覆盖一次，留下的已经是改过一项的
    kept = []
    for k, why in d:
        base = k.split('.bak_')[0]
        if '.bak_' in k and k in t_py and k in t_ps and t_py[k] == t0.get(base):
            print('OK   ' + name + ' · 备份 ' + k + ' 是改之前的原文件（有意修了：PowerShell 版是改过一项的）')
        else:
            kept.append((k, why))
    d = kept
    if d:
        print('DIFF ' + name + ' · 文件：' + json.dumps(d, ensure_ascii=False))
        for k, _ in d:
            if k in t_ps and k in t_py:
                print('   PS:', t_ps[k][:300])
                print('   PY:', t_py[k][:300])
        ok = False
    else:
        print('OK   ' + name + ' · 文件（%d 个）' % len(t_ps))
    RESULTS['ok' if ok else 'diff'] += 1


def pure(name, ps, py):
    """不碰文件的函数：一次 PowerShell 跑一批输入"""
    r_ps, out_ps = H.ps_call(ps, ENV)
    r_py = jsonable(py())
    ok = H.same(name, r_ps, r_py)
    RESULTS['ok' if ok else 'diff'] += 1


def batch_ps(func_body, inputs):
    """$__r = 每个输入跑 func_body（$a 是这一个输入的数组）的结果列表"""
    # 两个以上的数组用二元的逗号连起来就是「数组的数组」；只有一个时要一元的逗号包一层
    items = [ps_lit(list(i)) for i in inputs]
    return ('$__in = @(' + (', '.join(items) if len(items) > 1 else ',' + items[0]) + ')\n'
            '$__l = New-Object System.Collections.ArrayList\n'
            'foreach ($a in $__in) { $__v = $null; try { ' + func_body + ' } catch { $__v = \'EXC\' }; [void]$__l.Add($__v) }\n'
            '$__r = $__l\n')


def try_py(f, *a):
    try:
        return f(*a)
    except Exception:
        return 'EXC'


def u16(s, i):
    return len(s[:i].encode('utf-16-le', 'surrogatepass')) // 2


# ================================================================ 纯函数
def test_pure():
    texts = [('a = 1\r\nkey = val ; c\r\n', 'key'), ('KEY=  x  \n', 'key'), ('  cooppassword =\r\n', 'cooppassword'), ('nokey\n', 'key'),
             ('; key = 1\nkey=2', 'key'), ('中文 = 1\r\nk.e+y = 某值 ;注\r\n', 'k.e+y'), ('\U0001F600x\nkey = v', 'key'), ('', 'k'),
             ('[A]\r\n\tkey\t=\tv\tv \r\n', 'key')]
    pure('Get-IniMatch', batch_ps('$m = Get-IniMatch $a[0] $a[1]; if ($m) { $__v = @($m.Groups[1].Value, $m.Groups[1].Index, $m.Groups[1].Length) }', texts),
         lambda: [(lambda m, t: [m.group(1), u16(t, m.start(1)), u16(t, m.end(1)) - u16(t, m.start(1))] if m else None)(coop.get_ini_match(t, k), t)
                  for t, k in texts])

    siv = [('a = 1\r\ncooppassword = old   ; c\r\n', 'cooppassword', 'new', 'PASSWORD'),
           ('[PASSWORD]\r\nx = 1\r\n', 'cooppassword', 'pw', 'PASSWORD'),
           ('[password]  \nx = 1\n', 'cooppassword', 'pw', 'PASSWORD'),
           ('[GAMEPLAY]\r\n', 'allow_summons', '1', 'GAMEPLAY'),
           ('x = 1\r\n\r\n  \t', 'cooppassword', 'pw', 'PASSWORD'),
           ('', 'k', 'v', 'S'),
           ('COOPPASSWORD=abc\r\n', 'cooppassword', 'xyz', 'PASSWORD'),
           ('k = v\u3000\r\n', 'k', 'w', 'S'),
           ('k = v\x1c\r\n', 'k', 'w', 'S'),
           (' [PASSWORD] x\r\n[PASSWORD]', 'cooppassword', 'pw', 'PASSWORD')]
    pure('Set-IniValue', batch_ps('$__v = Set-IniValue $a[0] $a[1] $a[2] $a[3]', siv), lambda: [coop.set_ini_value(*a) for a in siv])

    sj = core.read_text(os.path.join(PRISTINE, 'settings.json'))
    gsn = [(sj, 'elite_share_mult', 1.0), (sj, 'boss_in_basic_pct', 0.0), (sj, 'nope', 2.5), ('{\n  "elite_share_mult": -1.25,\n}', 'elite_share_mult', 1.0),
           ('{"Elite_Share_Mult": 3}', 'elite_share_mult', 1.0), ('{\n\n   "x":007.50', 'x', 0.0), ('\u3000"x" :\t12', 'x', 0.0), ('\x1c"x": 1', 'x', 0.0)]
    pure('Get-CoopSettingNum', batch_ps('$__v = Get-CoopSettingNum $a[0] $a[1] $a[2]', gsn), lambda: [coop.get_coop_setting_num(*a) for a in gsn])
    vals = [1.0, 1.5, 0.0005, 1.0005, 2.5, 10.0, 0.333333, 1e-7, 123456.7895, 0.0015, 2.0004999, 1234.5675, 1e20, 3.0, -0.0001, 0.1 + 0.2]
    ssn = [(sj, 'elite_share_mult', v) for v in vals] + [(sj, 'missing', 1.0), ('{"boss_in_basic_pct":5.5}', 'boss_in_basic_pct', 6.25)]
    pure('Set-CoopSettingNum', batch_ps('$__v = Set-CoopSettingNum $a[0] $a[1] $a[2]; if ($__v) { $__v = $__v.Substring(0, [Math]::Min(2000, $__v.Length)) }', ssn),
         lambda: [(lambda r: r[:2000] if r else r)(coop.set_coop_setting_num(*a)) for a in ssn])
    # 字符串拼 double（Import-CoopEnemy 的 [-DryRun] 行）
    pure('[string]double', batch_ps('$__v = \'\' + [double]$a[0]', [(v,) for v in vals]), lambda: [coop._g15(v) for v in vals])

    opts = [('  a   b\tc  ',), ('a\u3000b\x1cc',), ('',), ('\r\nseed:1\r\n',), ('x  y   z',)]
    pure('Get-OptionKey', batch_ps('$__v = Get-OptionKey $a[0]', opts), lambda: [coop.get_option_key(a[0]) for a in opts])

    hides = [(dr3(),), ('前文 ' + dr3(m='rand', extra=RAND_EXTRA) + '\r\n后文 DR3|v=1|pw=xx==|w=low',), ('dr3|v=1|pw=abc',), ('DR4zAbCdEfGh_-12 和 DR4zshort',),
             ('DR3|pw=abc\nDR3|x|pw=def',), ('',)]
    pure('Hide-CoopSecret', batch_ps('$__v = Hide-CoopSecret $a[0]', hides), lambda: [coop.hide_coop_secret(a[0]) for a in hides])

    codes = [dr3(), dr3(m='rand', extra=RAND_EXTRA), dr3(m='RAND', w='HIGH', extra=RAND_EXTRA.replace('|o=', '|O=')),
             'dr3|' + dr3()[4:], '  DR3|v=1|m=plain|pw=' + b64('abc') + '|w=low\r\n', dr3(pw=None), dr3(pw='a;b'), dr3(m='xx'), dr3(w='mid'),
             dr3(m='rand'), dr3(m='rand', extra=RAND_EXTRA.replace('seed:', 'sd:')), dr3(m='rand', extra=RAND_EXTRA.replace('em=1', 'em=1.2.3')),
             dr3(m='rand', extra=RAND_EXTRA + '|x|y=1'), 'DR3|v=1|m=plain|PW=' + b64('pw') + '|w=low|=x|noeq|v=2',
             'DR3|v=1|m=plain|pw=YWJj ZGVm|w=low', 'DR3|v=1|m=plain|pw=YWJ|w=low', 'DR3|m=plain|pw=' + b64('中文密码') + '|w=low|sc=A_B=1,c=x,d=-2,=1',
             'DR3|m=plain|pw=/w==|w=low', dr3(m='rand', extra=RAND_EXTRA.replace('|o=', '|o=  a\t b  ')), '', 'DR4z']
    body = ('$c = Read-CoopCode3 $a[0]; $__v = @{ Ok = $c.Ok; Msg = $c.Msg; Version = $c.Version; Rand = $c.Rand; Password = $c.Password; World = $c.World; '
            'Rules = $(if ($null -eq $c.Rules) { $null } else { ,@($c.Rules) }); Em = $c.Em; Bp = $c.Bp; F = $(if ($c.Fixed) { @($c.Fixed.PresetSeed, $c.Fixed.Nat, $c.Fixed.Options) } else { $null }) }')

    def py_codes():
        out = []
        for t in codes:
            c = try_py(coop.read_coop_code3, t)
            if c == 'EXC':
                out.append(c)
                continue
            out.append(dict(Ok=c.Ok, Msg=c.Msg, Version=c.Version, Rand=c.Rand, Password=c.Password, World=c.World,
                            Rules=list(c.Rules) if c.Rules is not None else None,
                            Em=c.Em, Bp=c.Bp, F=[c.Fixed.PresetSeed, c.Fixed.Nat, c.Fixed.Options] if c.Fixed else None))
        return out
    pure('Read-CoopCode3', batch_ps(body, [(t,) for t in codes]), py_codes)

    # New-CoopPassword：随机的，只比格式和字符集
    r_ps, _ = H.ps_call('$__r = @(1..5 | ForEach-Object { New-CoopPassword })', ENV)
    chars = set('abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789')
    good = lambda p: len(p) == 16 and set(p) <= chars  # noqa: E731
    pys = [ORIG_NEW_PW() for _ in range(200)]
    ok = all(good(p) for p in r_ps) and all(good(p) for p in pys) and len(set(pys)) == 200 and set(''.join(pys)) == chars
    print(('OK   ' if ok else 'DIFF ') + 'New-CoopPassword（16 位、字符集一样、200 个不重复且用到全部字符）')
    RESULTS['ok' if ok else 'diff'] += 1


# ================================================================ 找 Seamless Co-op / 检查配置
def E(py_fn):
    """Python 这边：fn(ctx, find_ersc(ctx))"""
    return lambda ctx: py_fn(ctx, coop.find_ersc(ctx))


def test_find_ersc():
    ps = '$__x = (Find-Ersc).FullName'
    py = lambda ctx: (coop.find_ersc(ctx) or Rec()).FullName  # noqa: E731
    case('Find-Ersc 没有', ps, py)
    case('Find-Ersc 没有游戏路径', ps, py, cfg=dict(gr=None))
    case('Find-Ersc dll\\SeamlessCoop', ps, py, setup=lambda: mk_ersc())
    case('Find-Ersc dll 根 + 子文件夹', ps, py, setup=lambda: (mk_ersc(), wfile('dll\\ersc.dll', fake_pe())))
    case('Find-Ersc _ 开头不算 → 游戏目录', ps, py, setup=lambda: (mk_ersc(sub='dll\\_old'), wfile('game\\Game\\SeamlessCoop\\ersc.dll', fake_pe())))
    case('Find-Ersc 子文件夹排序不分大小写', ps, py, setup=lambda: (mk_ersc(sub='dll\\b'), mk_ersc(sub='dll\\A', dll_name='ERSC.DLL')))
    case('Find-Ersc 隐藏的文件夹 / 文件不算', ps, py,
         setup=lambda: (mk_ersc(sub='dll\\h'), hide('dll\\h'), wfile('dll\\ersc.dll', fake_pe(), hidden=True), mk_ersc(sub='dll\\z')))


def test_ersc_settings():
    ps = '$__x = Test-ErscSettings (Find-Ersc)'
    py = E(coop.test_ersc_settings)
    case('Test-ErscSettings 全要改、密码空', ps, py, setup=lambda: mk_ersc())
    case('Test-ErscSettings 带 BOM', ps, py, setup=lambda: mk_ersc(bom=True))
    case('Test-ErscSettings -DryRun', ps, py, setup=lambda: mk_ersc(), dry=True)
    case('Test-ErscSettings 都好（中文已放好）', ps, py,
         setup=lambda: (mk_ersc(INI_OK), shutil.copytree(os.path.join(PRISTINE, 'ersc_locale'), os.path.join(ROOT, ERSC_DIR, 'locale'))))
    case('Test-ErscSettings 没有存档扩展名这一项', ps, py, setup=lambda: mk_ersc(INI_OK.replace('save_file_extension = co2\r\n', '') + '\r\n\r\n  '))
    case('Test-ErscSettings 扩展名 sl2', ps, py, setup=lambda: mk_ersc(INI_OK.replace('= co2', '=\tsl2 ;x')))
    case('Test-ErscSettings 扩展名 CO2 不改', ps, py, setup=lambda: mk_ersc(INI_OK.replace('= co2', '= CO2').replace('allow_invaders = 0', 'allow_invaders =  0 ')))
    case('Test-ErscSettings 没有 ini', ps, py, setup=lambda: mk_ersc(ini=None))
    case('Test-ErscSettings 语言英文不填 schinese', ps, py, setup=lambda: mk_ersc(), cfg=dict(lang='english'))
    case('Test-ErscSettings 坏的 UTF-8 字节', ps, py, setup=lambda: mk_ersc(raw=b'; \xd6\xd0\xce\xc4\r\n' + INI.encode('utf-8')))
    case('Test-ErscSettings UTF-16 的 ini', ps, py, setup=lambda: mk_ersc(raw=b'\xff\xfe' + INI.encode('utf-16-le')))
    case('Test-ErscSettings 没有 ersc_locale', ps, py, setup=lambda: (mk_ersc(), _rm(os.path.join(ROOT, 'launcher', 'ersc_locale'))))
    case('Test-ErscSettings 中文文件不一样就覆盖', ps, py, setup=lambda: (mk_ersc(INI_OK), wfile(ERSC_DIR + '\\locale\\schinese.json', '{}')))
    case('Test-ErscSettings 没有随人数加强、有密码', ps, py,
         setup=lambda: mk_ersc('[SAVE]\nsave_file_extension=co2\n[PASSWORD]\ncooppassword=x y\n'))
    case('Test-ErscSettings ini 是文件夹', ps, py, setup=lambda: (mk_ersc(ini=None), os.makedirs(os.path.join(ROOT, ERSC_DIR, 'ersc_settings.ini'))),
         norm=cut_after('没有启动：'))
    case('Install-ErscLocale 新放', 'Install-ErscLocale (Find-Ersc); $__x = $true', lambda ctx: (coop.install_ersc_locale(ctx, coop.find_ersc(ctx)), True)[1],
         setup=lambda: mk_ersc())
    case('Install-ErscLocale locale 是文件', 'Install-ErscLocale (Find-Ersc); $__x = $true',
         lambda ctx: (coop.install_ersc_locale(ctx, coop.find_ersc(ctx)), True)[1], setup=lambda: (mk_ersc(), wfile(ERSC_DIR + '\\locale', 'x')),
         norm=cut_after('没放进去：'))


def test_ersc_version():
    ps = '$__x = Get-ErscVersion (Find-Ersc)'
    py = E(coop.get_ersc_version)
    case('Get-ErscVersion 2.0.2', ps, py, setup=lambda: mk_ersc())
    case('Get-ErscVersion 2.0.3', ps, py, setup=lambda: mk_ersc(pe=fake_pe(0x6af4b20a, 0xd67000)))
    case('Get-ErscVersion 认不出', ps, py, setup=lambda: mk_ersc(pe=fake_pe(0x12345678, 0xabc000, size=5000)))
    case('Get-ErscVersion 文件短（后面当 0）', ps, py, setup=lambda: mk_ersc(pe=fake_pe(0x11, 0x22, pe=0x40, size=0x50)))
    case('Get-ErscVersion PE 位置越界', ps, py, setup=lambda: mk_ersc(pe=fake_pe(pe=4013)))
    case('Get-ErscVersion PE 位置 4012', ps, py, setup=lambda: mk_ersc(pe=fake_pe(1, 2, pe=4012, size=4200)))
    case('Get-ErscVersion PE 位置是负的', ps, py, setup=lambda: mk_ersc(pe=fake_pe(pe=-4)))
    case('Get-ErscVersion PE 位置 -9', ps, py, setup=lambda: mk_ersc(pe=fake_pe(pe=-9)))
    case('Get-ErscVersion 没有 ersc', ps, py)


# ================================================================ 兼容档案 / 种子 / 核对码
def test_profile_seed():
    ps = "Set-WorldPacks '_coop'; Write-CoopProfile (Find-Ersc) 'fp123' %s; $__x = $true"

    def py(rand):
        def f(ctx):
            core.set_world_packs(ctx, '_coop')
            coop.write_coop_profile(ctx, coop.find_ersc(ctx), 'fp123', rand)
            # 有意的不同（崩溃风险审查 2026-11-19 第 12 条）：档案多了一行「mods<Tab>自己加的 mod」（副本里没有，是「无」）。
            # 断言有这一行，再从文件里去掉和 PowerShell 比
            if os.path.isfile(ctx.CoopProfile):
                lines = open(ctx.CoopProfile, encoding='utf-8', newline='').read().split('\n')
                if 'mods\t无' not in lines:
                    return 'mods 一行不对：%r' % [l for l in lines if l.startswith('mods')]
                with open(ctx.CoopProfile, 'w', encoding='utf-8', newline='') as fh:
                    fh.write('\n'.join(l for l in lines if not l.startswith('mods\t')))
            return True
        return f
    case('Write-CoopProfile 敌人随机', ps % '$true', py(True), setup=lambda: mk_ersc(INI_OK), cfg=dict(boss=True))
    case('Write-CoopProfile 无敌人随机', ps % '$false', py(False), setup=lambda: mk_ersc(INI_OK))
    case('Write-CoopProfile 设置里的数字照原样', ps % '$false', py(False),
         setup=lambda: (mk_ersc(INI_OK), wfile('launcher\\reroll\\settings.json', '{"elite_share_mult": 1.50, "boss_in_basic_pct": 1e1}')))
    case('Write-CoopProfile 键名大小写不同', ps % '$false', py(False),
         setup=lambda: (mk_ersc(INI_OK), wfile('launcher\\reroll\\settings.json', '\ufeff{"Elite_Share_Mult": -0.0, "boss_in_basic_pct": true}')))
    case('Write-CoopProfile settings.json 空的', ps % '$false', py(False), setup=lambda: (mk_ersc(INI_OK), wfile('launcher\\reroll\\settings.json', '')))
    case('Write-CoopProfile 没有 settings.json', ps % '$false', py(False), setup=lambda: (mk_ersc(INI_OK), _rm(os.path.join(ROOT, 'launcher', 'reroll', 'settings.json'))))
    case('Write-CoopProfile 没有随机结果', ps % '$true', py(True), setup=lambda: mk_ersc(INI_OK), cfg=dict(ri=None))
    case('Write-CoopProfile 密码空', ps % '$false', py(False), setup=lambda: mk_ersc())
    case('Write-CoopProfile 没有 dark_core', ps % '$false', py(False), setup=lambda: (mk_ersc(INI_OK), _rm(os.path.join(ROOT, 'dll', 'dark_core'))),
         norm=cut_after('不比对）：'))

    case('Get-CoopSeed 无敌人随机', '$__x = Get-CoopSeed $false', lambda ctx: coop.get_coop_seed(ctx, False))
    case('Get-CoopSeed 敌人随机', '$__x = Get-CoopSeed $true', lambda ctx: coop.get_coop_seed(ctx, True))
    case('Get-CoopSeed 没有随机结果', '$__x = Get-CoopSeed $true', lambda ctx: coop.get_coop_seed(ctx, True), cfg=dict(ri=None))
    case('Get-CoopSeed 种子空', '$__x = Get-CoopSeed $true', lambda ctx: coop.get_coop_seed(ctx, True), cfg=dict(ri=dict(RI, Seed='')))

    fp = '$__x = Get-CoopFingerprint %s %s'
    case('Get-CoopFingerprint 没有 coopfp.py', fp % ('$true', '$true'), lambda ctx: coop.get_coop_fingerprint(ctx, True, True), cfg=dict(py=REAL_PY))
    case('Get-CoopFingerprint 没有 Python', fp % ('$true', '$true'), lambda ctx: coop.get_coop_fingerprint(ctx, True, True),
         setup=lambda: wfile('launcher\\reroll\\coopfp.py', 'print(1)'))
    case('Get-CoopFingerprint 输出最后一行', fp % ('$true', '$false'), lambda ctx: coop.get_coop_fingerprint(ctx, True, False), cfg=dict(py=REAL_PY),
         setup=lambda: wfile('launcher\\reroll\\coopfp.py', 'import sys\nprint("a")\nprint(" fp-1 / x \\r")\nprint("   ")\nsys.stderr.write("err\\n")\n'))
    # 真的整合包、真的 coopfp.py（只读）
    real_gr = core.read_text(os.path.join(H.LAUNCHER, 'game_path.txt')).strip()
    for rand, rr in ((False, True), (True, False), (False, False)):
        snippet = ps_stubs(dict(DEFAULT_CFG, gr=real_gr, py=REAL_PY)) + '$__r = Get-CoopFingerprint %s %s' % (ps_lit(rand), ps_lit(rr))
        r_ps, _ = H.ps_call(snippet, ENV)
        CFG.clear()
        CFG.update(DEFAULT_CFG, gr=real_gr, py=REAL_PY)
        r_py, _ = H.py_call(lambda ctx: coop.get_coop_fingerprint(ctx, rand, rr), ENV)
        # 有意的不同：coopfp.py 什么都没打出来时，PowerShell 的 [string]$out 是 $null（AutomationNull），.Trim() 报「null-valued expression」
        # （ErrorActionPreference = Continue：错误写进日志，函数返回 $null）；Python 返回 ''。调用的地方都只看真假，一样
        if r_ps is None and rand is False and rr is False:
            print('     （PowerShell 返回 $null 并在日志里报错，Python 返回 ""：有意的不同）')
            r_ps = ''
        ok = H.same('Get-CoopFingerprint 真的整合包 rand=%s reroll=%s（%s）' % (rand, rr, r_ps), r_ps, r_py)
        RESULTS['ok' if ok else 'diff'] += 1


# ================================================================ DR1 / DR2
def test_code2_import():
    ps = '$c = Get-CoopCode; $__x = @{ Ok = $c.Ok; Msg = $c.Msg; Code = $c.Code; World = $c.World; Info = ($null -ne $c.Info) }'

    def py(ctx):
        c = coop.get_coop_code(ctx)
        return dict(Ok=c.Ok, Msg=c.Msg, Code=c.Code, World=c.World, Info=c.Info is not None)
    case('Get-CoopCode 没有随机结果', ps, py, cfg=dict(ri=None))
    case('Get-CoopCode 合并过', ps, py, cfg=dict(ri=dict(RI, Merged=True)))
    case('Get-CoopCode 没有预设种子', ps, py, cfg=dict(ri=dict(RI, PresetSeed='')))
    case('Get-CoopCode 选项里没有种子', ps, py, cfg=dict(ri=dict(RI, Options='enemy dlc')))
    case('Get-CoopCode 正常、高难度', ps, py, cfg=dict(boss=True))
    case('Get-CoopCode SEED 大写、没有 settings.json', ps, py, cfg=dict(ri=dict(RI, Options='enemy\u3000SEED:12')),
         setup=lambda: _rm(os.path.join(ROOT, 'launcher', 'reroll', 'settings.json')))
    case('Get-CoopCode 设置 1.0005 / 2.5', ps, py, setup=lambda: wfile('launcher\\reroll\\settings.json', '{\n "elite_share_mult": 1.0005,\n "boss_in_basic_pct": 2.5\n}'))

    imp = '$__x = Invoke-CoopImport %s'

    def py_imp(text):
        return lambda ctx: coop.invoke_coop_import(ctx, text)
    dr2 = 'DR2|197861029|1=0.0113,2=0.0137,3=0.0056|1.5|3|high|allmaps bossbgm customenemy dlc enemy v16 bias:20 seed:843925562'
    dr2same = dr2.replace('|1.5|3|', '|1|0|')
    dr1 = 'DR1|197861029|1=0.0113,2=0.0137,3=0.0056|allmaps  bossbgm customenemy dlc enemy v16 bias:20 seed:843925562'
    case('Invoke-CoopImport 随机器不能用', imp % ps_lit(dr2), py_imp(dr2), cfg=dict(rs=dict(Ok=False, Msg='没装随机器')))
    case('Invoke-CoopImport 剪贴板空的', imp % "''", py_imp(''))
    long_junk = 'x' * 79 + '\U0001F600' + 'y' * 30
    case('Invoke-CoopImport 剪贴板里不是码（长、切在表情中间）', imp % "''", py_imp(''), cfg=dict(clip_in=long_junk))
    case('Invoke-CoopImport 给的不是码（81 个字）', imp % ps_lit('z' * 81), py_imp('z' * 81))
    case('Invoke-CoopImport DR2 改设置、随机已一样', imp % ps_lit(dr2), py_imp(dr2))
    case('Invoke-CoopImport dr2 小写、HIGH', imp % ps_lit(dr2.replace('DR2', 'dr2').replace('high', 'HIGH')),
         py_imp(dr2.replace('DR2', 'dr2').replace('high', 'HIGH')))
    case('Invoke-CoopImport DR1', imp % ps_lit(dr1), py_imp(dr1))
    case('Invoke-CoopImport -DryRun', imp % ps_lit(dr2), py_imp(dr2), dry=True)
    case('Invoke-CoopImport 精英倍数 1.2.3', imp % ps_lit(dr2.replace('|1.5|', '|1.2.3|')), py_imp(dr2.replace('|1.5|', '|1.2.3|')))
    wrapped = dr2same[:40] + '\r\n  ' + dr2same[40:90] + '\n\t' + dr2same[90:]
    case('Invoke-CoopImport 剪贴板里折了行的、要重随', imp % "''", py_imp(''), cfg=dict(clip_in=wrapped, ri=dict(RI, PresetSeed='1')))
    case('Invoke-CoopImport 重随失败', imp % ps_lit(dr2same), py_imp(dr2same), cfg=dict(ri=dict(RI, Options='enemy seed:1'), rand_res=dict(Ok=False, Msg='随机器崩了')))
    case('Invoke-CoopImport 要重随、-DryRun', imp % ps_lit(dr2same), py_imp(dr2same), cfg=dict(ri=None), dry=True)
    case('Invoke-CoopImport 没有游戏路径', imp % ps_lit(dr2same), py_imp(dr2same), cfg=dict(ri=dict(RI, Merged=True), gr=None))
    case('Invoke-CoopImport settings.json 没有这两个键', imp % ps_lit(dr2), py_imp(dr2), setup=lambda: wfile('launcher\\reroll\\settings.json', '{"a": 1}'))
    case('Invoke-CoopImport 没有 settings.json', imp % ps_lit(dr2), py_imp(dr2), setup=lambda: _rm(os.path.join(ROOT, 'launcher', 'reroll', 'settings.json')))
    case('Invoke-CoopImport 没有 state 文件夹', imp % ps_lit(dr2), py_imp(dr2), setup=lambda: _rm(os.path.join(ROOT, 'launcher', 'reroll', 'state')))

    sw = 'Set-CoopWorld %s; $__x = $true'
    for w, dry in (('high', False), ('LOW', False), ('', False), ('low', True)):
        case('Set-CoopWorld %r%s' % (w, ' -DryRun' if dry else ''), sw % ps_lit(w), lambda ctx, w=w: (coop.set_coop_world(ctx, w), True)[1], dry=dry)


# ================================================================ ini / 密码 / DR3
def test_ini_code3():
    ver = '$__x = Get-CoopPackVersion'
    case('Get-CoopPackVersion', ver, coop.get_coop_pack_version)
    case('Get-CoopPackVersion BOM + 空白', ver, coop.get_coop_pack_version, setup=lambda: wfile('launcher\\version.txt', '\ufeff  0.10.14 \r\n'))
    case('Get-CoopPackVersion 没有', ver, coop.get_coop_pack_version, setup=lambda: _rm(os.path.join(ROOT, 'launcher', 'version.txt')))

    rd = '$f = Read-ErscIni (Find-Ersc); $__x = @{ Path = $f.Path; Bom = $f.Bom; Text = $f.Text }'

    def py_rd(ctx):
        f = coop.read_ersc_ini(ctx, coop.find_ersc(ctx))
        return dict(Path=f.Path, Bom=f.Bom, Text=f.Text)
    case('Read-ErscIni', rd, py_rd, setup=lambda: mk_ersc())
    case('Read-ErscIni BOM', rd, py_rd, setup=lambda: mk_ersc(bom=True))
    case('Read-ErscIni UTF-16 BE', rd, py_rd, setup=lambda: mk_ersc(raw=b'\xfe\xff' + INI.encode('utf-16-be')))
    case('Read-ErscIni 没有', rd, py_rd, setup=lambda: mk_ersc(ini=None))

    rules = '$__x = @(Get-ErscRules (Find-Ersc))'
    case('Get-ErscRules', rules, E(coop.get_ersc_rules), setup=lambda: mk_ersc())
    case('Get-ErscRules 大写的键', rules, E(coop.get_ersc_rules), setup=lambda: mk_ersc('BOSS_HEALTH_SCALING =  50 \r\nDeath_Debuffs=0;x\r\n'))
    case('Get-ErscRules 没有 ini', rules, E(coop.get_ersc_rules), setup=lambda: mk_ersc(ini=None))

    pw = '$__x = Get-ErscPassword (Find-Ersc)'
    case('Get-ErscPassword', pw, E(coop.get_ersc_password), setup=lambda: mk_ersc(INI_OK))
    case('Get-ErscPassword 带空格和注释', pw, E(coop.get_ersc_password), setup=lambda: mk_ersc('cooppassword =  pw x ; 注释\r\n'))
    case('Get-ErscPassword 没有 ini', pw, E(coop.get_ersc_password), setup=lambda: mk_ersc(ini=None))
    case('Get-ErscPassword 没有这一项', pw, E(coop.get_ersc_password), setup=lambda: mk_ersc('[PASSWORD]\r\n'))
    case('Get-ErscPassword 没有 ersc', pw, E(coop.get_ersc_password))

    ini = '$__x = Initialize-CoopPassword (Find-Ersc)'
    case('Initialize-CoopPassword 已有', ini, E(coop.initialize_coop_password), setup=lambda: mk_ersc(INI_OK))
    case('Initialize-CoopPassword 空的', ini, E(coop.initialize_coop_password), setup=lambda: mk_ersc(bom=True))
    case('Initialize-CoopPassword 有节没有键（LF）', ini, E(coop.initialize_coop_password), setup=lambda: mk_ersc('[GAMEPLAY]\nx=1\n[PASSWORD]\n\n[SAVE]\n'))
    case('Initialize-CoopPassword 没有节', ini, E(coop.initialize_coop_password), setup=lambda: mk_ersc('[GAMEPLAY]\r\nx=1\r\n\r\n'))
    case('Initialize-CoopPassword -DryRun', ini, E(coop.initialize_coop_password), setup=lambda: mk_ersc(), dry=True)
    case('Initialize-CoopPassword 没有 ini', ini, E(coop.initialize_coop_password), setup=lambda: mk_ersc(ini=None), norm=cut_after('写不了联机密码：'))

    def mk_diag():
        wfile('diag\\a.log', 'line ' + dr3() + '\r\nend')
        wfile('diag\\b.txt', '\ufeff' + dr3(m='rand', extra=RAND_EXTRA))
        wfile('diag\\c.ini', b'\xff\xfe' + ('x=' + dr3()).encode('utf-16-le'))
        wfile('diag\\d.json', '{"a": 1}')
        wfile('diag\\e.dat', dr3())
        wfile('diag\\sub\\f.TXT', 'code DR4zAbCdEfGhIjKl')
        wfile('diag\\h.txt', dr3(), hidden=True)
        wfile('diag\\hd\\g.txt', dr3())
        hide('diag\\hd')
        wfile('diag\\.txt', dr3())
        wfile('diag\\i.log', b'\xd6\xd0 ' + dr3().encode('ascii'))
        wfile('diag\\j.log', b'\xd6\xd0 no code')
    case('Remove-CoopSecret', "Remove-CoopSecret (Join-Path $Paly 'diag'); $__x = $true",
         lambda ctx: (coop.remove_coop_secret(ctx, os.path.join(ctx.Paly, 'diag')), True)[1], setup=mk_diag)
    case('Remove-CoopSecret 文件夹不在', "Remove-CoopSecret (Join-Path $Paly 'nodir'); $__x = $true",
         lambda ctx: (coop.remove_coop_secret(ctx, os.path.join(ctx.Paly, 'nodir')), True)[1])

    c3 = '$c = Get-CoopCode3 %s (Find-Ersc); $__x = @{ Ok = $c.Ok; Msg = $c.Msg; Code = $c.Code; World = $c.World; Info = ($null -ne $c.Info) }'

    def py_c3(rand):
        def f(ctx):
            c = coop.get_coop_code3(ctx, rand, coop.find_ersc(ctx))
            return dict(Ok=c.Ok, Msg=c.Msg, Code=c.Code, World=c.World, Info=c.Info is not None)
        return f
    case('Get-CoopCode3 密码空', c3 % '$true', py_c3(True), setup=lambda: mk_ersc())
    case('Get-CoopCode3 无敌人随机', c3 % '$false', py_c3(False), setup=lambda: mk_ersc(INI_OK))
    case('Get-CoopCode3 敌人随机、高难度', c3 % '$true', py_c3(True), setup=lambda: mk_ersc(INI_OK.replace('abc123', '中文 密码')), cfg=dict(boss=True))
    case('Get-CoopCode3 敌人随机没有结果', c3 % '$true', py_c3(True), setup=lambda: mk_ersc(INI_OK), cfg=dict(ri=None))

    se = '$c = Read-CoopCode3 %s; $__x = Set-ErscFromCode (Find-Ersc) $c'

    def py_se(code):
        return lambda ctx: coop.set_ersc_from_code(ctx, coop.find_ersc(ctx), coop.read_coop_code3(code))
    same_code = dr3(sc='allow_summons=1,boss_health_scaling=100,death_debuffs=1')
    case('Set-ErscFromCode 已经一样', se % ps_lit(same_code), py_se(same_code), setup=lambda: mk_ersc(INI_OK))
    c_case = dr3(pw='ABC123')
    case('Set-ErscFromCode 密码只差大小写', se % ps_lit(c_case), py_se(c_case), setup=lambda: mk_ersc(INI_OK, bom=True))
    rules_code = dr3(sc='ALLOW_SUMMONS=0,boss_health_scaling=50,unknown_rule=3,enemy_health_scaling=35')
    case('Set-ErscFromCode 规则不同、键缺', se % ps_lit(rules_code), py_se(rules_code),
         setup=lambda: mk_ersc('[SCALING]\r\nboss_health_scaling = 100   ; 注\r\n[PASSWORD]\r\ncooppassword=abc123\r\n'))
    case('Set-ErscFromCode 没有节', se % ps_lit(rules_code), py_se(rules_code), setup=lambda: mk_ersc('cooppassword=abc123\n'))
    case('Set-ErscFromCode -DryRun', se % ps_lit(rules_code), py_se(rules_code), setup=lambda: mk_ersc(INI_OK), dry=True)
    case('Set-ErscFromCode 没有 ini', se % ps_lit(rules_code), py_se(rules_code), setup=lambda: mk_ersc(ini=None), norm=cut_after('设置：'))


# ================================================================ 复制联机码 / 开房 / 加入
def test_flows():
    cc = "$c = @{ Code = %s; Info = %s; World = %s }; Copy-CoopCode $c; $__x = $true"

    def py_cc(code, info, world):
        return lambda ctx: (coop.copy_coop_code(ctx, Rec(Code=code, Info=Rec(Time=info) if info else None, World=world)), True)[1]
    t = datetime.datetime(2026, 11, 10, 9, 5, 0)
    full = dr3(m='rand', extra=RAND_EXTRA)
    case('Copy-CoopCode 敌人随机、死亡以上', cc % (ps_lit(full), "[pscustomobject]@{ Time = [datetime]'2026-11-10 09:05:00' }", "'HIGH'"),
         py_cc(full, t, 'HIGH'), need_coopcode=True)
    case('Copy-CoopCode 无敌人随机', cc % (ps_lit(dr3()), '$null', "'low'"), py_cc(dr3(), None, 'low'), need_coopcode=True)
    case('Copy-CoopCode 剪贴板失败', cc % (ps_lit(dr3()), '$null', "'low'"), py_cc(dr3(), None, 'low'), cfg=dict(clip_fail=True), need_coopcode=True)

    act = '$__x = Invoke-CoopCodeAction'
    case('Invoke-CoopCodeAction 没有 Seamless', act, coop.invoke_coop_code_action)
    case('Invoke-CoopCodeAction 上次开房是 PLAIN', act, coop.invoke_coop_code_action,
         setup=lambda: (mk_ersc(), wfile('launcher\\reroll\\state\\coop_host_mode.txt', ' PLAIN\n')), cfg=dict(rs=dict(Ok=False, Msg='x')), need_coopcode=True)
    case('Invoke-CoopCodeAction 随机器不能用', act, coop.invoke_coop_code_action, setup=lambda: mk_ersc(), cfg=dict(rs=dict(Ok=False, Msg='没装随机器')))
    case('Invoke-CoopCodeAction 没有 ini', act, coop.invoke_coop_code_action, setup=lambda: mk_ersc(ini=None), norm=cut_after('写不了联机密码：'))
    case('Invoke-CoopCodeAction 没有随机结果', act, coop.invoke_coop_code_action, setup=lambda: mk_ersc(INI_OK), cfg=dict(ri=None))
    case('Invoke-CoopCodeAction 正常', act, coop.invoke_coop_code_action, setup=lambda: mk_ersc(INI_OK), need_coopcode=True)

    host_ = '$__x = Invoke-CoopHost %s'
    case('Invoke-CoopHost 没有 Seamless', host_ % '$true', lambda ctx: coop.invoke_coop_host(ctx, True))
    case('Invoke-CoopHost 随机器不能用', host_ % '$true', lambda ctx: coop.invoke_coop_host(ctx, True), setup=lambda: mk_ersc(),
         cfg=dict(rs=dict(Ok=False, Msg='没装随机器')))
    case('Invoke-CoopHost 敌人随机、选了 high', host_ % '$true', lambda ctx: coop.invoke_coop_host(ctx, True), setup=lambda: mk_ersc(), bossworld='high',
         cfg=dict(boss=True), need_coopcode=True)
    case('Invoke-CoopHost 无敌人随机、去掉旧的世界', host_ % '$false', lambda ctx: coop.invoke_coop_host(ctx, False),
         setup=lambda: (mk_ersc(INI_OK), wfile('launcher\\reroll\\state\\coop_world.txt', 'high\n')), need_coopcode=True)
    case('Invoke-CoopHost -DryRun LOW', host_ % '$false', lambda ctx: coop.invoke_coop_host(ctx, False),
         setup=lambda: (mk_ersc(), wfile('launcher\\reroll\\state\\coop_world.txt', 'high\n')), dry=True, bossworld='LOW', need_coopcode=True)
    case('Invoke-CoopHost 没有随机结果', host_ % '$true', lambda ctx: coop.invoke_coop_host(ctx, True), setup=lambda: mk_ersc(INI_OK), cfg=dict(ri=None))
    case('Invoke-CoopHost 写不了密码', host_ % '$false', lambda ctx: coop.invoke_coop_host(ctx, False), setup=lambda: mk_ersc(ini=None),
         norm=cut_after('写不了联机密码：'))

    join = '$__x = Invoke-CoopJoin %s'

    def py_join(text):
        return lambda ctx: coop.invoke_coop_join(ctx, text)
    plain = dr3(sc='allow_summons=0,boss_health_scaling=50')
    rand = dr3(m='rand', w='high', extra=RAND_EXTRA)
    case('Invoke-CoopJoin 没有 Seamless', join % ps_lit(plain), py_join(plain))
    case('Invoke-CoopJoin 哪里都没有码', join % "''", py_join(''), setup=lambda: mk_ersc(INI_OK), cfg=dict(clip_in='随便什么'))
    case('Invoke-CoopJoin DR3 无敌人随机', join % ps_lit(plain), py_join(plain), setup=lambda: mk_ersc(INI_OK, bom=True))
    case('Invoke-CoopJoin DR3 敌人随机、已一样', join % ps_lit(rand), py_join(rand), setup=lambda: mk_ersc(INI_OK))
    case('Invoke-CoopJoin DR3 敌人随机、要重随', join % ps_lit(rand), py_join(rand), setup=lambda: mk_ersc(INI_OK), cfg=dict(ri=dict(RI, PresetNat='9')))
    case('Invoke-CoopJoin DR3 随机器不能用', join % ps_lit(rand), py_join(rand), setup=lambda: mk_ersc(INI_OK), cfg=dict(rs=dict(Ok=False, Msg='没装')))
    case('Invoke-CoopJoin -DryRun', join % ps_lit(rand), py_join(rand), setup=lambda: mk_ersc(INI_OK), cfg=dict(ri=None), dry=True)
    case('Invoke-CoopJoin 版本不同', join % ps_lit(dr3(v='0.0.1')), py_join(dr3(v='0.0.1')), setup=lambda: mk_ersc(INI_OK))
    case('Invoke-CoopJoin 码不对（m=）', join % ps_lit(dr3(m='xx')), py_join(dr3(m='xx')), setup=lambda: mk_ersc(INI_OK))
    case('Invoke-CoopJoin 码里 em 不是数字', join % ps_lit(dr3(m='rand', extra=RAND_EXTRA.replace('em=1', 'em=1..'))),
         py_join(dr3(m='rand', extra=RAND_EXTRA.replace('em=1', 'em=1..'))), setup=lambda: mk_ersc(INI_OK))
    # 有意的不同（2026-11-18 修）：小写开头的码 Python 版当成 DR3 码（PowerShell 版当旧码拒掉）：和 PowerShell 处理大写的码比
    case('Invoke-CoopJoin dr3 小写 → 和 DR3 一样（有意修了）', join % ps_lit(plain), py_join('dr3|' + plain[4:]), setup=lambda: mk_ersc(INI_OK))
    old = 'DR2|197861029|1=0.0113,2=0.0137,3=0.0056|1|0|low|allmaps bossbgm customenemy dlc enemy v16 bias:20 seed:843925562'
    case('Invoke-CoopJoin 旧码 DR2', join % ps_lit(old), py_join(old), setup=lambda: mk_ersc(INI_OK))
    case('Invoke-CoopJoin 旧码 DR2、ini 要改', join % ps_lit(old), py_join(old), setup=lambda: mk_ersc(INI_OK.replace('allow_invaders = 0', 'allow_invaders = 1')))
    case('Invoke-CoopJoin 旧码、密码空', join % ps_lit(old), py_join(old), setup=lambda: mk_ersc())
    case('Invoke-CoopJoin DR4z 解不开', join % ps_lit('DR4zgarbage!!'), py_join('DR4zgarbage!!'), setup=lambda: mk_ersc(INI_OK), need_coopcode=True)
    case('Invoke-CoopJoin 剪贴板 DR4 不是 z', join % "''", py_join(''), setup=lambda: mk_ersc(INI_OK), cfg=dict(clip_in='DR4yabc'), need_coopcode=True)
    case('Invoke-CoopJoin 房主的码比上次加入的新', join % "''", py_join(''), cfg=dict(clip_in='不是码'),
         setup=lambda: (mk_ersc(INI_OK), wfile('dll\\dark_core\\coop_host_code.txt', 'code ' + plain, mtime=2000000000),
                        wfile('launcher\\reroll\\state\\coop_join_code.txt', rand + '\n', mtime=1900000000)))
    case('Invoke-CoopJoin 上次加入的更新', join % "''", py_join(''),
         setup=lambda: (mk_ersc(INI_OK), wfile('dll\\dark_core\\coop_host_code.txt', plain, mtime=1900000000),
                        wfile('launcher\\reroll\\state\\coop_join_code.txt', '\ufeff' + rand + '\n', mtime=2000000000)))
    if HAVE_COOPCODE:
        from dfl.coopcode import compress_coop_code
        z_plain = compress_coop_code(plain)
        z_rand = compress_coop_code(rand)
        case('Invoke-CoopJoin 剪贴板 DR4z', join % "''", py_join(''), setup=lambda: mk_ersc(INI_OK), cfg=dict(clip_in=z_plain))
        broken = '  ' + z_rand[:30] + '\r\n' + z_rand[30:60] + ' \t ' + z_rand[60:] + '\n'
        case('Invoke-CoopJoin 折了行的 DR4z', join % ps_lit(broken), py_join(broken), setup=lambda: mk_ersc(INI_OK))
        case('Invoke-CoopJoin dr4z 小写 → 和 DR4z 一样（有意修了）', join % ps_lit(z_plain), py_join('dr4z' + z_plain[4:]), setup=lambda: mk_ersc(INI_OK))
        case('Invoke-CoopJoin DR4z 没复制完整', join % ps_lit(z_rand[:40]), py_join(z_rand[:40]), setup=lambda: mk_ersc(INI_OK))
    else:
        for n in ('剪贴板 DR4z', '折了行的 DR4z', 'dr4z 小写', 'DR4z 没复制完整'):
            print('SKIP Invoke-CoopJoin ' + n + '（还没有 dfl\\coopcode.py）')
            RESULTS['skip'] += 1


if __name__ == '__main__':
    install_fakes()
    try:
        only = sys.argv[1:]
        for fn in (test_pure, test_find_ersc, test_ersc_settings, test_ersc_version, test_profile_seed, test_code2_import, test_ini_code3, test_flows):
            if not only or fn.__name__ in only:
                fn()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print('\n共 %d 组：OK %d，DIFF %d，SKIP %d' % (sum(RESULTS.values()), RESULTS['ok'], RESULTS['diff'], RESULTS['skip']))
    sys.exit(1 if RESULTS['diff'] else 0)
