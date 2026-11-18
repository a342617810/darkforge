# -*- coding: utf-8 -*-
"""usermods.ps1 → dfl/usermods.py 对照测试（整合包目录用 copy_root 的副本：mods\\、YAFSML自定义.ini 都写在副本里）。
每个用例：清掉副本里的 mods\\ / ini / ext\\ → 按同样的步骤建好 → 跑 PowerShell 版 → 记下结果、输出、写出的文件 → 再清掉重建 → 跑 Python 版 → 逐项比。"""
import ctypes
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from dfl import usermods  # noqa: E402

RESULTS = []


def norm_err(v):
    """.NET 异常的说法跟着控制台代码页变（同一台机器上有时英文、有时中文），Python 版固定用中文的那句：
    比的是「哪个检查抛的、哪一类」（有意的不同，见汇报）"""
    if isinstance(v, str) and v.startswith('ERR:'):
        m = re.search(r'(IsPathRooted|GetFullPath)', v)
        kind = 'illegal' if ('Illegal characters' in v or '非法字符' in v) else 'format' if ('format' in v or '格式' in v) else v
        return 'ERR:%s:%s' % (m.group(1) if m else '?', kind)
    if isinstance(v, list):
        return [norm_err(x) for x in v]
    return v


def check(name, ps, py):
    RESULTS.append(harness.same(name, norm_err(ps), norm_err(py)))


def put(path, data=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))


def mkdir(path):
    os.makedirs(path, exist_ok=True)


def hide(path):
    ctypes.windll.kernel32.SetFileAttributesW(path, 0x2 | (0x10 if os.path.isdir(path) else 0))


class Case:
    def __init__(self, root, ext, env, tmp):
        self.root, self.ext, self.env, self.tmp = root, ext, env, tmp
        self.mods = os.path.join(root, 'mods')
        self.ini = os.path.join(root, 'YAFSML自定义.ini')

    def reset(self):
        for p in (self.mods, self.ext, os.path.join(self.root, 'extra_rel')):
            if os.path.isdir(p):
                for d, sub, fs in os.walk(p):
                    for n in sub + fs:
                        ctypes.windll.kernel32.SetFileAttributesW(os.path.join(d, n), 0x80)
                shutil.rmtree(p)
        if os.path.exists(self.ini):
            os.remove(self.ini)

    def snap(self):
        t = {('mods/' + k): v for k, v in harness.tree(self.mods).items()} if os.path.isdir(self.mods) else {}
        if os.path.exists(self.ini):
            t['ini'] = open(self.ini, 'rb').read()
        return t

    def run(self, name, setup, snippet, fn, expect=None):
        """expect(ps, py) -> bool：有意和 PowerShell 版不同的地方，不比结果、改成断言新的行为"""
        self.reset()
        setup(self)
        ps, ps_out = harness.ps_call(snippet, self.env, root=self.root)
        ps_tree = self.snap()
        self.reset()
        setup(self)
        py, py_out = harness.py_call(fn, self.env, root=self.root)
        py_tree = self.snap()
        if expect:
            ok = bool(expect(ps, py))
            print(('OK   ' if ok else 'DIFF ') + name + '：结果（有意的不同，断言新的行为）')
            if not ok:
                print('   PS:', json.dumps(ps, ensure_ascii=False)[:1500])
                print('   PY:', json.dumps(py, ensure_ascii=False)[:1500])
            RESULTS.append(ok)
        else:
            check(name + '：结果', ps, py)
        check(name + '：输出', ps_out, py_out)
        d = harness.diff_tree(ps_tree, py_tree)
        check(name + '：写出的文件', [], d)


# ---------------------------------------------------------------- 搭 mods\ 和 ini 的几种情况
def mods_none(c):
    pass


def mods_empty(c):
    mkdir(c.mods)


def mods_many(c):
    m = c.mods
    mkdir(os.path.join(m, 'Look', 'parts'))
    put(os.path.join(m, 'nested', 'inner', 'chr', 'c0000.chrbnd.dcx'))
    mkdir(os.path.join(m, 'deep2', 'a', 'b', 'sfx'))
    mkdir(os.path.join(m, 'deep3', 'a', 'b', 'c', 'sfx'))
    mkdir(os.path.join(m, '_off', 'parts'))
    mkdir(os.path.join(m, 'multi', 'v1', 'parts'))
    mkdir(os.path.join(m, 'multi', 'v2', 'menu'))
    mkdir(os.path.join(m, 'multi_skip', 'v1', 'parts'))
    mkdir(os.path.join(m, 'multi_skip', '_v2', 'parts'))
    put(os.path.join(m, 'dllmod', 'x.dll'))
    put(os.path.join(m, 'dllmod2', 'a', 'b', 'x.DLL'))
    put(os.path.join(m, 'dllmod3', 'a', 'b', 'c', 'x.dll'))
    put(os.path.join(m, 'empty_txt', 'readme.txt'))
    mkdir(os.path.join(m, 'withreg', 'parts'))
    put(os.path.join(m, 'withreg', 'regulation.bin'))
    mkdir(os.path.join(m, 'withdll', 'sfx'))
    put(os.path.join(m, 'withdll', 'y.dll'))
    put(os.path.join(m, 'withdll', 'sub', 'z.dll'))
    mkdir(os.path.join(m, 'regonly'))
    put(os.path.join(m, 'regonly', 'Regulation.BIN'))
    # a­b（带软连字符）按区域规则和 ab 相等：Sort-Object 不稳定，两个谁在前要和 PowerShell 5.1 一样
    for n in ('b', 'A', 'a-b', 'ab', '中文mod', '10', '9', 'Ä', 'a b', 'a_b', 'A_B!', 'z.z', 'a­b', 'x­', 'x'):
        mkdir(os.path.join(m, n, 'parts'))
    mkdir(os.path.join(m, 'hid', 'parts'))
    hide(os.path.join(m, 'hid'))
    mkdir(os.path.join(m, 'hidsub', 'inner', 'parts'))
    hide(os.path.join(m, 'hidsub', 'inner'))
    put(os.path.join(m, 'loose.txt'))


def mods_top_root(c):
    """直接把 chr 之类放进了 mods\\：整个 mods\\ 当一个 mod，chr 文件夹本身跳过"""
    m = c.mods
    mkdir(os.path.join(m, 'chr'))
    mkdir(os.path.join(m, 'PARTS'))
    mkdir(os.path.join(m, 'other_mod', 'sfx'))
    put(os.path.join(m, 'top.dll'))
    put(os.path.join(m, 'regulation.bin'))


def ext_dirs(c):
    e = c.ext
    mkdir(os.path.join(e, 'm1', 'parts'))
    mkdir(os.path.join(e, 'm2'))
    put(os.path.join(e, 'ersc', 'ersc.dll'))
    put(os.path.join(e, 'ersc', 'ERSC.DLL2'))
    put(os.path.join(e, 'tool', 'tool.dll'))
    put(os.path.join(e, 'tool', 'Ersc.Dll.bak'))
    mkdir(os.path.join(c.root, 'extra_rel', 'm3', 'chr'))


def ini_text(c):
    return ('; 注释\r\n# 井号注释\r\nkey_before_section=1\r\n'
            '[patch]\r\nskip_intro = 0\r\nENABLE_IME=1\r\nenable_ime = 2\r\nreplace_save_filename=.sl2\r\nPatch_Mem=0\r\nnew_key=a=b\r\n'
            'novalue=\r\nnoequals\r\n  spaced   =   v  v  \r\n'
            '[Tweak]\r\ncpu_affinity=3\r\n'
            '[ log ]\r\nlog_level=debug\r\n'
            '[NewSec]\r\nfoo=bar\r\n'
            '[patch]\r\nboot_boost=0\r\n'
            '[mod]\r\nm1=' + c.ext + '\\m1\r\nM1=' + c.ext + '\\m1\\\r\nrel=extra_rel\\m3\r\nrel2=.\\extra_rel\\..\\extra_rel\\m3\r\n'
            'quoted="' + c.ext + '\\m2"\r\nmissing=D:\\不存在\\外观\r\nempty=\r\nfwd=' + c.ext.replace('\\', '/') + '/m1\r\n'
            '中文名=' + c.ext + '\\m1\r\n'
            '[mod_after]\r\nafter1=' + c.ext + '\\m2\r\nafter-2=extra_rel\\m3\r\n'
            '[dll]\r\ntool=' + c.ext + '\\tool\\tool.dll|delay,500\r\ncoop=' + c.ext + '\\ersc\\ersc.dll\r\ncoop2=' + c.ext + '\\ersc\\ERSC.DLL|early\r\n'
            'nf=' + c.ext + '\\tool\\none.dll|early\r\nbak=' + c.ext + '\\tool\\Ersc.Dll.bak\r\n'
            '[MOD]\r\nlate=' + c.ext + '\\m1\r\n')


def ini_utf8_bom(c):
    ext_dirs(c)
    put(c.ini, b'\xef\xbb\xbf' + ini_text(c).encode('utf-8'))


def ini_utf8_nobom_lf(c):
    ext_dirs(c)
    put(c.ini, ini_text(c).replace('\r\n', '\n').encode('utf-8'))


def ini_cr_only(c):
    ext_dirs(c)
    put(c.ini, b'\xef\xbb\xbf' + ini_text(c).replace('\r\n', '\r').encode('utf-8'))


def ini_utf16(c):
    ext_dirs(c)
    put(c.ini, b'\xff\xfe' + ini_text(c).encode('utf-16-le'))


def ini_gbk(c):
    """玩家用记事本存成了 GBK（ANSI）：中文变成乱码也不能报错"""
    ext_dirs(c)
    t = ('; 中文注释：跳过开场\r\n[patch]\r\nskip_intro=0\r\ntitle=暗黑重铸\r\n[mod]\r\n外观=' + c.ext + '\\m1\r\nlook=D:\\不存在\\外观\r\n'
         'ok=' + c.ext + '\\m1\r\n[dll]\r\n工具=' + c.ext + '\\tool\\tool.dll\r\n')
    put(c.ini, t.encode('gbk'))


def ini_garbage(c):
    """随便什么字节（截断的 UTF-8、单独的 \\r、NUL）"""
    put(c.ini, b'[patch]\r\nk1=\xe4\xb8\r\nk2=\xff\xfe\xfd\r\n\x00k3=\x00\r\nk4=a\rk5=b\n\n[mod]\r\nbad=\xe6\x96\x87\xe4\r\n')


def ini_empty(c):
    put(c.ini, b'')


def ini_bom_only(c):
    put(c.ini, b'\xef\xbb\xbf')


def ini_bad_path(c):
    """[mod] 里的路径带非法字符：.NET 抛异常，整个 Get-UserLoadLines 出错（启动器接住、这次不加载自己加的 mod）"""
    ext_dirs(c)
    put(c.ini, ('[mod]\r\nok=' + c.ext + '\\m1\r\nbad=D:\\a|b\r\n').encode('utf-8'))


def ini_bad_wild(c):
    put(c.ini, '[mod]\r\nbad=mods\\a*b\r\n'.encode('utf-8'))


def ini_bad_colon(c):
    put(c.ini, '[mod_after]\r\nbad=ab:c\r\n'.encode('utf-8'))


def ini_dll_pipe_only(c):
    put(c.ini, '[dll]\r\nonlycond=|early\r\nemptyv=\r\n'.encode('utf-8'))


def both(*fs):
    def f(c):
        for x in fs:
            x(c)
    return f


# ---------------------------------------------------------------- 两边怎么调
PS_INI_FLAT = r'''
$ini = Read-UserIni
$__r = @{
  S = @(foreach ($s in @($ini.Sections.Keys)) { '#' + $s; foreach ($k in @($ini.Sections[$s].Keys)) { $s + "`t" + $k + "`t" + $ini.Sections[$s][$k] } })
  N = @(@(foreach ($k in @($ini.Names.Keys)) { $k + "`t" + $ini.Names[$k] }) | Sort-Object)
}
'''


def py_ini_flat(ctx):
    ini = usermods.read_user_ini(ctx)
    s = []
    for sec in ini.Sections.keys():
        s.append('#' + sec)
        for k in ini.Sections[sec].keys():
            s.append(sec + '\t' + k + '\t' + ini.Sections[sec][k])
    from dfl import win
    return {'S': s, 'N': win.culture_sorted([k + '\t' + ini.Names[k] for k in ini.Names.keys()])}


def ps_try(expr):
    return '$__r = $null\ntry { $__r = ' + expr + ' } catch { $__r = "ERR:" + $_.Exception.Message }\n'


def py_try(fn):
    def f(ctx):
        try:
            return fn(ctx)
        except Exception as e:
            return 'ERR:' + str(e)
    return f


def main():
    with tempfile.TemporaryDirectory() as tmp:
        env = harness.fake_env(tmp)
        root = harness.copy_root(tmp)
        ext = os.path.join(tmp, 'ext')
        c = Case(root, ext, env, tmp)
        tpl = os.path.join(root, 'launcher', 'YAFSML.ini.tpl')
        tpl_ps = tpl.replace("'", "''")

        mod_setups = [('没有 mods', mods_none), ('空的 mods', mods_empty), ('各种 mod 文件夹', mods_many), ('直接放进 mods', mods_top_root)]
        ini_setups = [('没有 ini', mods_none), ('UTF-8 带 BOM', ini_utf8_bom), ('UTF-8 无 BOM、LF', ini_utf8_nobom_lf), ('只有 CR', ini_cr_only),
                      ('UTF-16', ini_utf16), ('GBK', ini_gbk), ('乱字节', ini_garbage), ('空文件', ini_empty), ('只有 BOM', ini_bom_only),
                      ('dll 只有条件', ini_dll_pipe_only)]

        # ---- Get-UserModInfo / Get-UserModSummary：各种 mods\ 结构
        for n, s in mod_setups:
            c.run('Get-UserModInfo（%s）' % n, s, '$__r = @(Get-UserModInfo)', lambda ctx: usermods.get_user_mod_info(ctx))
            c.run('Get-UserModSummary（%s）' % n, s, '$__r = @(Get-UserModSummary)', lambda ctx: usermods.get_user_mod_summary(ctx))

        # ---- Test-GameDataRoot / Find-ModRoots：直接对文件夹调
        def dirs_of(cc):
            m = cc.mods
            return [m, os.path.join(m, 'Look'), os.path.join(m, 'nested'), os.path.join(m, 'deep2'), os.path.join(m, 'deep3'),
                    os.path.join(m, 'multi'), os.path.join(m, 'multi_skip'), os.path.join(m, 'regonly'), os.path.join(m, 'hidsub'),
                    os.path.join(m, 'nope'), os.path.join(m, 'loose.txt')]
        ds = dirs_of(c)
        jp = os.path.join(tmp, 'dirs.json')
        with open(jp, 'w', encoding='utf-8') as f:
            json.dump(ds, f, ensure_ascii=False)
        snip = ("$in = Get-Content -LiteralPath '%s' -Raw -Encoding UTF8 | ConvertFrom-Json\n"
                "$__r = @(foreach ($d in $in) { ,@([string](Test-GameDataRoot $d), (@(Find-ModRoots $d 0) -join '|'), (@(Find-ModRoots $d 1) -join '|'),"
                " (@(Find-ModRoots $d) -join '|'), (@(Find-ModRoots $d 3) -join '|')) })\n") % jp.replace("'", "''")
        c.run('Test-GameDataRoot / Find-ModRoots', mods_many, snip,
              lambda ctx: [[str(usermods.test_game_data_root(d)), '|'.join(usermods.find_mod_roots(d, 0)), '|'.join(usermods.find_mod_roots(d, 1)),
                            '|'.join(usermods.find_mod_roots(d)), '|'.join(usermods.find_mod_roots(d, 3))] for d in ds])

        # ---- Read-UserIni：各种编码、写法
        for n, s in ini_setups:
            c.run('Read-UserIni（%s）' % n, s, PS_INI_FLAT, py_ini_flat)

        # ---- New-UserIni：没有就写（带 BOM、CRLF），有就不动
        c.run('New-UserIni（没有）', mods_none, '$__r = New-UserIni', lambda ctx: usermods.new_user_ini(ctx))
        c.run('New-UserIni（已经有）', ini_gbk, '$__r = New-UserIni', lambda ctx: usermods.new_user_ini(ctx))
        c.run('New-UserIni 写的再读', mods_none, '[void](New-UserIni)\n' + PS_INI_FLAT, lambda ctx: (usermods.new_user_ini(ctx), py_ini_flat(ctx))[1])

        # ---- Get-UserLoadLines：mods\ × ini
        for mn, ms in mod_setups[2:]:
            for n, s in ini_setups:
                c.run('Get-UserLoadLines（%s + %s）' % (mn, n), both(ms, s), ps_try('Get-UserLoadLines'), py_try(lambda ctx: usermods.get_user_load_lines(ctx)))
            # 有意的不同（2026-11-18 修）：路径里有不能用的字符时，PowerShell 版整个出错（自己加的 mod 一个都不加载），
            # Python 版只跳过那一项、提示一句，别的照常加载
            for n, s in [('非法字符 |', ini_bad_path), ('通配符', ini_bad_wild), ('冒号', ini_bad_colon)]:
                c.run('Get-UserLoadLines（%s + %s）' % (mn, n), both(ms, s), ps_try('Get-UserLoadLines'), py_try(lambda ctx: usermods.get_user_load_lines(ctx)),
                      expect=lambda ps, py: str(ps).startswith('ERR') and isinstance(py, dict)
                      and any('路径里有不能用的字符' in x for x in py.get('Notes') or []))
        c.run('Get-UserLoadLines（什么都没有）', mods_none, ps_try('Get-UserLoadLines'), py_try(lambda ctx: usermods.get_user_load_lines(ctx)))

        # ---- Merge-UserIniSettings：拿真的模板（填过的和没填的）、LF 的、空的
        for n, s in ini_setups + [('UTF-8 带 BOM（再来）', ini_utf8_bom)]:
            c.run('Merge-UserIniSettings（模板 + %s）' % n, s,
                  "$t = [IO.File]::ReadAllText('%s')\n" % tpl_ps + ps_try('Merge-UserIniSettings $t'),
                  py_try(lambda ctx: usermods.merge_user_ini_settings(ctx, open(tpl, encoding='utf-8-sig').read())))
        c.run('Merge-UserIniSettings（LF 模板）', ini_utf8_bom,
              "$t = [IO.File]::ReadAllText('%s') -replace \"`r`n\", \"`n\"\n" % tpl_ps + ps_try('Merge-UserIniSettings $t'),
              py_try(lambda ctx: usermods.merge_user_ini_settings(ctx, open(tpl, encoding='utf-8-sig').read().replace('\r\n', '\n'))))
        c.run('Merge-UserIniSettings（空文字）', ini_utf8_bom, ps_try("Merge-UserIniSettings ''"),
              py_try(lambda ctx: usermods.merge_user_ini_settings(ctx, '')))
        c.run('Merge-UserIniSettings（$null）', ini_utf8_bom, ps_try('Merge-UserIniSettings $null'),
              py_try(lambda ctx: usermods.merge_user_ini_settings(ctx, None)))
        dup = '[patch]\r\nskip_intro=1\r\n;skip_intro=9\r\nSKIP_INTRO = 2\r\n\r\n; 注释\r\n[tweak]\r\n\r\n[log]\r\nx=1\r\n'
        dp = os.path.join(tmp, 'dup.txt')
        with open(dp, 'w', encoding='utf-8', newline='') as f:
            f.write(dup)
        c.run('Merge-UserIniSettings（同名键两次、空段）', ini_utf8_bom,
              "$t = [IO.File]::ReadAllText('%s')\n" % dp.replace("'", "''") + ps_try('Merge-UserIniSettings $t'),
              py_try(lambda ctx: usermods.merge_user_ini_settings(ctx, dup)))

        # ---- Resolve-UserPath：一批写法
        ins = ['', '   ', '""', '"C:\\a b"', ' "mods\\x" ', 'mods\\x\\', '..\\x', 'a/b', 'C:foo', '\\foo', '/foo', 'D:\\x\\y\\', 'a|b', 'a<b',
               'a"b', 'a\tb', 'a*b', 'a?b', 'ab:c', 'C:\\x:y', '\u3000mods\u3000', '\x1cmods', '中文\\路径', 'x. ', 'x ', '.', '..',
               'mods\\..\\..', 'C:', '\\\\server\\share\\x', '\u00a0x\u00a0', '"', '" "', 'x\x00y']
        jp = os.path.join(tmp, 'paths.json')
        with open(jp, 'w', encoding='utf-8') as f:
            json.dump(ins, f, ensure_ascii=False)
        snip = ("$in = Get-Content -LiteralPath '%s' -Raw -Encoding UTF8 | ConvertFrom-Json\n"
                "$__r = @(foreach ($x in $in) { try { [string](Resolve-UserPath ([string]$x)) } catch { 'ERR:' + $_.Exception.Message } })\n") % jp.replace("'", "''")

        def py_res(ctx):
            out = []
            for x in ins:
                try:
                    out.append(usermods.resolve_user_path(ctx, x))
                except Exception as e:
                    out.append('ERR:' + str(e))
            return out
        r_ps, _ = harness.ps_call(snip, env, root=root)
        r_py, _ = harness.py_call(py_res, env, root=root)
        for i, x in enumerate(ins):
            check('Resolve-UserPath %s' % json.dumps(x, ensure_ascii=False), r_ps[i], r_py[i])
        # Python 版异常的说法：和中文系统上 PowerShell 版给玩家看到的一样
        try:
            harness.py_call(lambda ctx: usermods.resolve_user_path(ctx, 'a|b'), env, root=root)
            msg = ''
        except ValueError as e:
            msg = str(e)
        check('Python 版的异常说法', '使用“1”个参数调用“IsPathRooted”时发生异常:“路径中具有非法字符。”', msg)

        c.reset()

    bad = RESULTS.count(False)
    print('%d 项，%d 项不同' % (len(RESULTS), bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
