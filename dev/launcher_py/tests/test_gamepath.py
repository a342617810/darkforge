# -*- coding: utf-8 -*-
"""gamepath 模块（launcher.ps1「游戏路径」一节、Get-SteamGameLanguage、游戏版本）的对照测试。

都在假的 APPDATA / LOCALAPPDATA、整合包副本上跑；Steam 注册表、各盘扫描、真的游戏目录只读。
不能对照的（写在汇报里）：
- 选择框（Pick-FolderDialog / Pick-ExeDialog）本身弹不了：PowerShell 那边换成假的函数（照原来的先 Resolve-GameRoot 再返回准备好的回答），
  Python 那边换掉 win.pick_folder / win.pick_file，比菜单的流程；另外单独看 Python 版传给 win.pick_* 的参数。
- Read-Host：两边都换成从准备好的回答里取（读到 <EOF> = 标准输入关了），比菜单逻辑，不比提示符的写法；Clear-Host 换成什么都不做。
运行：launcher\\python\\python.exe -X utf8 dev\\launcher_py\\tests\\test_gamepath.py"""
import ctypes
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from harness import PALY, copy_root, fake_env, ps_call, py_call, same, tree, diff_tree  # noqa: E402
from dfl import gamepath, win  # noqa: E402

GAME = os.path.dirname(os.path.dirname(PALY))          # ...\ELDEN RING（整合包放在 Game\dark_reforged）
GAME_EXE = os.path.join(GAME, 'Game', 'eldenring.exe')
HAVE_GAME = os.path.isfile(GAME_EXE)
FAILS = []
COUNT = [0]


def check(name, a, b):
    COUNT[0] += 1
    if not same(name, a, b):
        FAILS.append(name)


def j(x):
    """Python 的结果按 JSON 走一遍（和 PowerShell 那边 ConvertTo-Json 回来的比）"""
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def q(s):
    """PowerShell 单引号字符串"""
    if s is None:
        return '$null'
    for ch in "'\u2018\u2019\u201a\u201b":
        s = s.replace(ch, ch + ch)
    return "'" + s + "'"


def qa(xs):
    return '@(' + ','.join(q(x) for x in xs) + ')'


def touch(p, data=b''):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data)


def hide(p):
    ctypes.windll.kernel32.SetFileAttributesW(p, 0x2)


def make_game(d):
    """假的游戏目录：d\\Game\\eldenring.exe（空文件）"""
    touch(os.path.join(d, 'Game', 'eldenring.exe'))
    return d


def nn(v):
    return '<null>' if v is None else v


def main():
    os.chdir(PALY)          # 相对路径（'.'、'..'）两边按同一个当前目录算
    with tempfile.TemporaryDirectory() as tmp:
        env = fake_env(tmp)
        env['DARKFORGE_TEST_DIALOG'] = '0'
        root = copy_root(os.path.join(tmp, 'c1'))
        gp_file = os.path.join(root, 'launcher', 'game_path.txt')
        fake = make_game(os.path.join(tmp, 'fake', 'ELDEN RING'))
        os.makedirs(os.path.join(tmp, 'fake2', 'Game', 'eldenring.exe'))          # 叫 eldenring.exe 的文件夹
        touch(os.path.join(tmp, 'shallow', 'eldenring.exe'))
        touch(os.path.join(tmp, 'fake3', 'ELDENRING.EXE'))                          # 大写的 exe，直接放在游戏目录（没有 Game 这层）

        # ---------------------------------------------------------------- Test-NormalizeGameRoot
        paths = ['', '   ', '""', '" "', 'Q:\\nope', 'Q:\\nope\\Game\\eldenring.exe', 'E:\\a<b>', 'E:\\a|b', 'E:\\x:y', '.', '..', '..\\..',
                 'C:\\', 'C:', fake, fake + '\\', fake + '\\Game', fake + '\\Game\\eldenring.exe', '"' + fake + '"', '  "' + fake + '\\Game\\"  ',
                 fake.replace('\\', '/'), fake.upper() + '\\GAME\\ELDENRING.EXE', os.path.join(tmp, 'fake2', 'Game', 'eldenring.exe'),
                 os.path.join(tmp, 'fake2'), os.path.join(tmp, 'shallow', 'eldenring.exe'), os.path.join(tmp, 'fake3'),
                 os.path.join(tmp, 'fake3', 'ELDENRING.EXE'), fake + '\\Game\\.', fake + '\\Game\\..\\Game', fake + '\\Game\\eldenring.exe\\',
                 fake + '\\Game\\eldenring.exe.', fake + '\\Game\\eldenring.exe ', '\t' + fake + '\t', '\\\\?\\' + fake, fake + '\\\\Game']
        if HAVE_GAME:
            paths += [GAME, GAME + '\\Game', GAME_EXE, GAME.lower()]
        r_ps, _ = ps_call('$__r = @(foreach ($p in %s) { $r = Test-NormalizeGameRoot $p; if ($null -eq $r) { "<null>" } else { $r } })' % qa(paths), env, root=root)
        r_py = [nn(gamepath.test_normalize_game_root(p)) for p in paths]
        for p, a, b in zip(paths, r_ps, r_py):
            check('Test-NormalizeGameRoot %r' % p, a, b)
        check('Test-NormalizeGameRoot $null', ps_call('$__r = Test-NormalizeGameRoot $null', env, root=root)[0],
              gamepath.test_normalize_game_root(None))

        # ---------------------------------------------------------------- Get-SavedGameRoot
        g = (GAME if HAVE_GAME else fake).encode('utf-8')
        variants = [('没有文件', None), ('空文件', b''), ('只有换行', b'\r\n'), ('正常', g + b'\r\n'), ('带 BOM', b'\xef\xbb\xbf' + g + b'\r\n'),
                    ('引号、LF', b'"' + g + b'"\n'), ('第一行空', b'\n' + g + b'\r\n'), ('CR 分行', g + b'\rjunk'), ('前后空格', b'  ' + g + b'  \r\n'),
                    ('不存在的盘', b'Q:\\nope\r\n'), ('GBK 字节', b'\xc4\xe3\xba\xc3\r\n'), ('exe 路径', g + b'\\Game\\eldenring.exe'),
                    ('Game 文件夹', g + b'\\Game\r\n'), ('只有空格', b'   \r\n' + g)]
        for name, data in variants:
            if data is None:
                if os.path.exists(gp_file):
                    os.remove(gp_file)
            else:
                touch(gp_file, data)
            a, oa = ps_call('$__r = Get-SavedGameRoot', env, root=root)
            b, ob = py_call(gamepath.get_saved_game_root, env, root=root)
            check('Get-SavedGameRoot ' + name, [a, oa], [b, ob])

        # ---------------------------------------------------------------- Save-GameRoot
        for rt in ('D:\\测试\\ELDEN RING', fake):
            touch(gp_file, b'x')
            a, oa = ps_call('Save-GameRoot %s; $__r = @{ cache = $script:CacheGameRoot }' % q(rt), env, root=root)
            fa = open(gp_file, 'rb').read()
            touch(gp_file, b'x')

            def f(ctx, rt=rt):
                gamepath.save_game_root(ctx, rt)
                return {'cache': ctx.CacheGameRoot}
            b, ob = py_call(f, env, root=root)
            fb = open(gp_file, 'rb').read()
            check('Save-GameRoot ' + rt, [a, oa, fa.hex()], [b, ob, fb.hex()])

        # ---------------------------------------------------------------- Get-UniquePaths
        lists = [['a', 'A', 'a\\', '', None, 'b', 'B\\\\', 'ß', 'SS', 'ss', 'c:/x', 'C:/X\\', 'C:\\x'], [], ['\\'], ['x', 'x', 'X\\']]
        for ls_ in lists:
            a, _ = ps_call('$__r = @(Get-UniquePaths %s)' % qa(ls_), env, root=root)
            check('Get-UniquePaths %r' % ls_, a, gamepath.get_unique_paths(ls_))
        a, _ = ps_call("$__r = @(Get-UniquePaths 'one\\')", env, root=root)
        check('Get-UniquePaths 单个字符串', a, gamepath.get_unique_paths('one\\'))

        # ---------------------------------------------------------------- 注册表 / 各盘（只读）
        a, _ = ps_call('$__r = @(Find-SteamGameRoots)', env, root=root)
        check('Find-SteamGameRoots（本机注册表）', a, gamepath.find_steam_game_roots())
        a, _ = ps_call('$__r = @(Get-FixedDriveRoots)', env, root=root)
        check('Get-FixedDriveRoots', a, gamepath.get_fixed_drive_roots())
        a, _ = ps_call('$__r = @(Find-CommonGameRoots)', env, root=root)
        check('Find-CommonGameRoots（本机各盘）', a, gamepath.find_common_game_roots())

        # ---------------------------------------------------------------- 整合包附近：真的整合包（只读）+ 两种假的摆法
        a, _ = ps_call('$__r = @(Find-NearbyGameRoots)', env)
        check('Find-NearbyGameRoots（真的整合包，只读）', a, py_call(gamepath.find_nearby_game_roots, env)[0])
        # A：整合包解压在游戏的 Game 文件夹里
        ga = make_game(os.path.join(tmp, 'A', 'ELDEN RING'))
        root_a = copy_root(os.path.join(ga, 'Game'))
        # B：整合包旁边放着几个游戏目录；45 个名字像的（只看前 40 个）；里面 45 层子文件夹的（也只看前 40 个）；隐藏的不算
        scan = os.path.join(tmp, 'B', 'scan')
        root_b = copy_root(os.path.join(scan, 'packs'))
        make_game(os.path.join(scan, 'ELDEN RING 1'))
        for i in range(45):
            os.makedirs(os.path.join(scan, 'MyEldenStuff', 'sub%02d' % i))
        make_game(os.path.join(scan, 'MyEldenStuff', 'sub44'))
        make_game(os.path.join(scan, 'MyEldenStuff', 'sub03'))
        make_game(os.path.join(scan, 'packs', 'Ring of Fire'))
        make_game(os.path.join(scan, 'ELDEN RING hidden'))
        hide(os.path.join(scan, 'ELDEN RING hidden'))
        for i in range(45):
            make_game(os.path.join(scan, 'packs', 'elden_%02d' % i))
        for nm, rr in (('A', root_a), ('B', root_b), ('副本', root)):
            a, _ = ps_call('$__r = @(Find-NearbyGameRoots)', env, root=rr)
            check('Find-NearbyGameRoots 摆法 ' + nm, a, py_call(gamepath.find_nearby_game_roots, env, root=rr)[0])
            a, _ = ps_call('$__r = @(Get-GameCandidates)', env, root=rr)
            check('Get-GameCandidates 摆法 ' + nm, a, py_call(gamepath.get_game_candidates, env, root=rr)[0])
            a, _ = ps_call('$__r = Select-GameCandidate', env, root=rr)
            check('Select-GameCandidate 摆法 ' + nm, a, py_call(gamepath.select_game_candidate, env, root=rr)[0])

        # ---------------------------------------------------------------- Resolve-GameRoot
        def rgr_case(name, data, pre_ps='', pre_py=None, refresh=False, rr=root):
            gpf = os.path.join(rr, 'launcher', 'game_path.txt')

            def setup():
                if data is None:
                    if os.path.exists(gpf):
                        os.remove(gpf)
                else:
                    touch(gpf, data)
            setup()
            a, oa = ps_call(pre_ps + '$x = Resolve-GameRoot%s; $__r = @{ r = $x; cache = $script:CacheGameRoot }' % (' -Refresh' if refresh else ''), env, root=rr)
            fa = open(gpf, 'rb').read().hex() if os.path.exists(gpf) else None
            setup()

            def f(ctx):
                if pre_py:
                    pre_py(ctx)
                x = gamepath.resolve_game_root(ctx, Refresh=refresh)
                return {'r': x, 'cache': ctx.CacheGameRoot}
            b, ob = py_call(f, env, root=rr)
            fb = open(gpf, 'rb').read().hex() if os.path.exists(gpf) else None
            check('Resolve-GameRoot ' + name, [a, oa, fa], [j(b), ob, fb])

        rgr_case('记下的', fake.encode('utf-8') + b'\r\n')
        rgr_case('没记下：自动检测（副本）', None)
        rgr_case('没记下：自动检测（摆法 A，整合包在游戏里面）', None, rr=root_a)
        rgr_case('没记下：自动检测（摆法 B，好几个候选）', None, rr=root_b)
        rgr_case('记下的不对：自动检测', b'Q:\\nope\r\n')
        rgr_case('有缓存', fake.encode('utf-8') + b'\r\n', "$script:CacheGameRoot = 'X:\\cached'; ", lambda c: setattr(c, 'CacheGameRoot', 'X:\\cached'))
        rgr_case('有缓存 -Refresh', fake.encode('utf-8') + b'\r\n', "$script:CacheGameRoot = 'X:\\cached'; ", lambda c: setattr(c, 'CacheGameRoot', 'X:\\cached'),
                 refresh=True)

        # ---------------------------------------------------------------- 选择框（只看 Python 版传给 win.pick_* 的参数）
        calls = []
        old_pf, old_pe = getattr(win, 'pick_folder', None), getattr(win, 'pick_file', None)
        win.pick_folder = lambda *a, **k: calls.append(('folder', a, k)) or 'D:\\picked'
        win.pick_file = lambda *a, **k: calls.append(('file', a, k)) or None
        touch(gp_file, fake.encode('utf-8') + b'\r\n')
        r1, _ = py_call(lambda c: gamepath.pick_folder_dialog(c, '标题'), env, root=root)
        r2, _ = py_call(lambda c: gamepath.pick_exe_dialog(c, '选 exe'), env, root=root)
        check('Pick-FolderDialog 参数（只有 Python）', [r1, r2, calls],
              ['D:\\picked', None, [('folder', ('标题', fake), {}), ('file', ('选 exe', 'eldenring.exe|eldenring.exe|所有文件|*.*', fake + '\\Game'), {})]])
        win.pick_folder = lambda *a, **k: (_ for _ in ()).throw(OSError('x'))
        check('Pick-FolderDialog 出错返回 None（只有 Python）', py_call(lambda c: gamepath.pick_folder_dialog(c, 't'), env, root=root)[0], None)

        # ---------------------------------------------------------------- Set-GameRootInteractive（回答按顺序；<EOF> = 标准输入关了）
        exe_in_fake = fake + '\\Game\\eldenring.exe'
        scripts = [
            ('Q', ['Q'], []), ('EOF', ['<EOF>'], []), ('空行再 q', ['', '  ', 'q'], []), ('序号 1', ['1'], []), ('序号 +1', ['+1'], []),
            ('序号 01', [' 01 '], []), ('全角数字', ['１', '<EOF>', '<EOF>'], []), ('序号太大', ['99', '', 'q'], []), ('A 再 q', ['A', 'q'], []),
            ('F 选对了', ['F'], [fake + '\\Game']), ('F 取消', ['f', 'q'], ['']), ('F 选错', ['F', '', 'Q'], [tmp]),
            ('E 选对了', ['E'], [exe_in_fake]), ('E 选错', ['e', '<EOF>', 'q'], [os.path.join(tmp, 'shallow', 'eldenring.exe')]),
            ('粘贴路径', ['"' + fake + '\\Game"'], []), ('乱写', ['zzz', '', '<EOF>'], []),
        ]
        old_rh = gamepath._read_host
        for name, ans, picks in scripts:
            for data in (fake.encode('utf-8') + b'\r\n', None):
                tag = name + ('（有记下的）' if data else '（没记下的）')
                ps = ('function Clear-Host {}\n$script:__ans = %s; $script:__ai = 0\n$script:__picks = %s; $script:__pi = 0\n'
                      'function Read-Host([string]$Prompt) { Write-Host ($Prompt + ": "); $a = $script:__ans[$script:__ai]; $script:__ai++; '
                      'if ($null -eq $a -or $a -eq "<EOF>") { return $null }; return $a }\n'
                      'function Pick-FolderDialog([string]$Title) { $null = Resolve-GameRoot; Write-Host ("PICK-FOLDER:" + $Title.Replace("`r`n", "|")); '
                      '$a = $script:__picks[$script:__pi]; $script:__pi++; if (-not $a) { return $null }; return $a }\n'
                      'function Pick-ExeDialog([string]$Title) { $null = Resolve-GameRoot; Write-Host ("PICK-EXE:" + $Title); '
                      '$a = $script:__picks[$script:__pi]; $script:__pi++; if (-not $a) { return $null }; return $a }\n'
                      '$ok = Set-GameRootInteractive; $__r = @{ ok = $ok; cache = $script:CacheGameRoot }') % (qa(ans + ['<EOF>']), qa(picks + ['']))
                if data is None:
                    if os.path.exists(gp_file):
                        os.remove(gp_file)
                else:
                    touch(gp_file, data)
                a, oa = ps_call(ps, env, root=root)
                fa = open(gp_file, 'rb').read().hex() if os.path.exists(gp_file) else None
                if data is None:
                    if os.path.exists(gp_file):
                        os.remove(gp_file)
                else:
                    touch(gp_file, data)
                st = {'a': list(ans) + ['<EOF>'], 'p': list(picks) + ['']}

                def rh(prompt, st=st):
                    harness_host(prompt + ': ')
                    x = st['a'].pop(0) if st['a'] else '<EOF>'
                    return None if x == '<EOF>' else x

                def pick(kind, st=st):
                    def fn(title, *a, **k):
                        harness_host(('PICK-FOLDER:' if kind == 'f' else 'PICK-EXE:') + title.replace('\r\n', '|'))
                        x = st['p'].pop(0) if st['p'] else ''
                        return x or None
                    return fn
                gamepath._read_host = rh
                win.pick_folder = pick('f')
                win.pick_file = pick('e')

                def f(ctx):
                    ok = gamepath.set_game_root_interactive(ctx)
                    return {'ok': ok, 'cache': ctx.CacheGameRoot}
                b, ob = py_call(f, env, root=root)
                fb = open(gp_file, 'rb').read().hex() if os.path.exists(gp_file) else None
                check('Set-GameRootInteractive ' + tag, [a, oa, fa], [j(b), ob, fb])
        gamepath._read_host = old_rh
        win.pick_folder, win.pick_file = old_pf, old_pe

        # ---------------------------------------------------------------- Get-SteamGameLanguage
        lib = os.path.join(tmp, 'lib')
        lg = make_game(os.path.join(lib, 'steamapps', 'common', 'ELDEN RING'))
        acf = os.path.join(lib, 'steamapps', 'appmanifest_1245620.acf')
        cases = [('真的游戏（只读）', (GAME if HAVE_GAME else fake), None),
                 ('假的 schinese', lg, b'"AppState"\n{\n\t"language"\t\t"schinese"\n}\n'),
                 ('大写键', lg, b'\xef\xbb\xbf"AppState"\r\n{\r\n  "LANGUAGE"   "english"\r\n  "language" "x"\r\n}'),
                 ('没写语言', lg, b'"AppState"\n{\n}\n'), ('空的语言', lg, b'"language"  ""\n'), ('没有 acf', lg, 'del'),
                 ('记下的不对：先自动检测', os.path.join(tmp, 'fake'), None)]
        for name, groot, acf_data in cases:
            touch(gp_file, groot.encode('utf-8') + b'\r\n')
            if acf_data == 'del':
                if os.path.exists(acf):
                    os.remove(acf)
            elif acf_data is not None:
                touch(acf, acf_data)
            a, oa = ps_call('$__r = Get-SteamGameLanguage', env, root=root)
            touch(gp_file, groot.encode('utf-8') + b'\r\n')
            b, ob = py_call(gamepath.get_steam_game_language, env, root=root)
            check('Get-SteamGameLanguage ' + name, [a, oa], [b, ob])

        # ---------------------------------------------------------------- 游戏版本
        sysdir = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32')
        exes = [os.path.join(sysdir, 'notepad.exe'), os.path.join(sysdir, 'edit.exe'), os.path.join(PALY, 'yafsml', 'YAFSML.exe'),
                os.path.join(sysdir, 'GameInputSvc.exe'), os.path.join(root, 'launcher', 'launcher.ps1'), os.path.join(tmp, 'nope.exe'), '',
                os.path.join(tmp, 'fake'), exe_in_fake]
        if HAVE_GAME:
            exes.append(GAME_EXE)
        a, _ = ps_call('$__r = @(foreach ($e in %s) { Get-GameExeVersion $e })' % qa(exes), env, root=root)
        check('Get-GameExeVersion', a, [gamepath.get_game_exe_version(e) for e in exes])
        for e in exes:
            if not e:
                continue
            for nl in (True, False):
                for ans in ('0', '1', '-1'):
                    if nl and ans != '0':
                        continue
                    e2 = dict(env)
                    e2['DARKFORGE_TEST_DIALOG'] = ans
                    e2['DARKFORGE_TEST_DIALOG_LOG'] = os.path.join(tmp, 'dlg_ps.txt')
                    for p_ in (e2['DARKFORGE_TEST_DIALOG_LOG'], os.path.join(tmp, 'dlg_py.txt')):
                        if os.path.exists(p_):
                            os.remove(p_)
                    a, oa = ps_call(('$NoLaunch = $true; ' if nl else '') + '$__r = Test-GameVersion %s' % q(e), e2, root=root)
                    e2['DARKFORGE_TEST_DIALOG'] = ans
                    e2['DARKFORGE_TEST_DIALOG_LOG'] = os.path.join(tmp, 'dlg_py.txt')
                    b, ob = py_call(lambda c, e=e: gamepath.test_game_version(c, e), e2, root=root, NoLaunch=nl)
                    da = read_dlg(os.path.join(tmp, 'dlg_ps.txt'))
                    db = read_dlg(os.path.join(tmp, 'dlg_py.txt'))
                    check('Test-GameVersion %s NoLaunch=%s 回答=%s' % (os.path.basename(e), nl, ans), [a, oa, da], [b, ob, db])
    print('gamepath：%d 项，%d 项不同' % (COUNT[0], len(FAILS)))
    for f in FAILS:
        print('  DIFF', f)
    return 1 if FAILS else 0


def harness_host(text):
    from dfl.core import host
    host(text)


def read_dlg(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


if __name__ == '__main__':
    sys.exit(main())
