# -*- coding: utf-8 -*-
"""联机测试包：python dev\\tools\\make_coop_pack.py <输出.zip> [--ref <正式包.zip>]
                python dev\\tools\\make_coop_pack.py --dry <正式包.zip>     只和正式包比对，不写 zip

从主文件夹（main）打，和 make_package.py 同一套规则（用户 2026-11-18：联机文件夹以后不用同步了，直接在 main 上开发，联机包也从这里打）。另外：
- 开放联机入口：包里放 launcher/coop_test.txt（启动器看到它才在「工具与设置」里显示「联机」一类）
- 带 Seamless Co-op（dll/SeamlessCoop：ersc.dll、设置、locale、crashpad_handler；联机密码清空，开房时自动生成），备份文件和崩溃转储不带
- 带 Seamless 的汉化（launcher/ersc_locale）和 联机使用说明.txt
- dll/ErdTools/erd_tools.ini 的 save_extension 照正式包放 rng（本机联机启动过会是 co2；启动器每次启动按启动方式重写）
- settings.json 的 arena.generator_test 本机开着（生成器实验）时，包里放 git HEAD 里的那份（HEAD 里得是关着的）
- --ref：randomizer/presets/CustomEnemy.txt 用正式包里的那份（本机点「打开随机器」/ 一键重随敌人时会改写它）
只给联机测试用，不发布、不做更新包（Seamless 不许随包发）。"""
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_package as mp  # noqa: E402

OPEN = ('dll/SeamlessCoop/*', '联机使用说明.txt', 'launcher/ersc_locale/*', 'launcher/coop_test.txt')
SEAMLESS_OK = ('dll/SeamlessCoop/ersc.dll', 'dll/SeamlessCoop/ersc_settings.ini',
               'dll/SeamlessCoop/crashpad/crashpad_handler.exe', 'dll/SeamlessCoop/locale/*.json')
COOP_TEST = ('联机测试包：有这个文件，启动器的「工具与设置」里才显示「联机」一类。\r\n'
             '正式包不带它（联机稳定了再公开）。\r\n').encode('utf-8')
SETTINGS = 'launcher/reroll/settings.json'
PRESET = 'randomizer/presets/CustomEnemy.txt'
GEN_MSG = 'arena.generator_test'

mp.EXCL = [p for p in mp.EXCL if p not in OPEN]


def _ini_set(full, key, value, what):
    raw = open(full, 'rb').read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    txt = raw.decode('utf-8-sig')
    txt2, k = re.subn(r'(?im)^([ \t]*%s[ \t]*=)[ \t]*[^\r\n;]*' % key, r'\g<1>' + value, txt)
    assert k == 1, what + ' 行没找到'
    return (b'\xef\xbb\xbf' if bom else b'') + txt2.encode('utf-8')


def _gen_on(raw):
    st = json.loads(raw.decode('utf-8-sig'))
    return bool(str((st.get('arena') or {}).get('generator_test') or '').strip())


def head_settings():
    """本机 settings.json 开着生成器实验时，返回 git HEAD 里的那份（必须是关着的）；否则 None"""
    full = os.path.join(mp.SRC, *SETTINGS.split('/'))
    if not _gen_on(open(full, 'rb').read()):
        return None
    raw = subprocess.run(['git', '-c', 'safe.directory=*', '-C', mp.SRC, 'show', 'HEAD:' + SETTINGS],
                         capture_output=True, check=True).stdout
    if _gen_on(raw):
        sys.exit('git HEAD 里的 settings.json 也开着 arena.generator_test，不打')
    return raw


def entries(ref=None):
    """(包里的相对路径, 替换的内容或 None, 源文件)"""
    settings = head_settings()
    preset = None
    if ref:
        with zipfile.ZipFile(ref) as z:
            preset = z.read(mp.TOP + '/' + PRESET)
    for full, rel in mp.files():
        if rel == 'launcher/coop_test.txt':
            continue        # 下面统一写
        if rel.startswith('dll/SeamlessCoop/'):
            if not any(fnmatch.fnmatch(rel, pat) for pat in SEAMLESS_OK):
                continue
            if rel == 'dll/SeamlessCoop/ersc_settings.ini':
                yield rel, _ini_set(full, 'cooppassword', ' ', 'cooppassword'), full
                continue
        if rel == 'dll/ErdTools/erd_tools.ini':
            yield rel, _ini_set(full, 'save_extension', ' rng', 'save_extension'), full
            continue
        if rel == SETTINGS and settings is not None:
            yield rel, settings, full
            continue
        if rel == PRESET and preset is not None:
            yield rel, preset, full
            continue
        yield rel, None, full
    yield 'launcher/coop_test.txt', COOP_TEST, None


def guards():
    bad = [b for b in mp.guards() if GEN_MSG not in b]      # 生成器实验：entries() 换成 HEAD 的那份
    seen = {rel for rel, _, _ in entries()}
    need = ['launcher/coop_test.txt', '联机使用说明.txt', 'launcher/ersc_locale/schinese.json',
            'dll/SeamlessCoop/ersc.dll', 'dll/SeamlessCoop/ersc_settings.ini', 'dll/dark_core/dark_core.dll',
            'dll/dark_lock/dark_lock.dll', 'dll/dark_slot/dark_slot.dll', 'launcher/dfgui.py', 'launcher/df.py',
            'launcher/reroll/data/msbtool/msbtool.dll']
    bad += ['包里少了 ' + x for x in need if x not in seen]
    return bad


def sha(b):
    return hashlib.sha256(b).hexdigest()


def dry(ref):
    z = zipfile.ZipFile(ref)
    top = mp.TOP + '/'
    rel_names = {n[len(top):]: n for n in z.namelist() if n.startswith(top) and not n.endswith('/')}
    mine = {rel: (data if data is not None else full) for rel, data, full in entries(ref)}
    add = sorted(set(mine) - set(rel_names))
    gone = sorted(set(rel_names) - set(mine))
    changed = []
    for rel in sorted(set(mine) & set(rel_names)):
        v = mine[rel]
        a = v if isinstance(v, bytes) else open(v, 'rb').read()
        if sha(a) != sha(z.read(rel_names[rel])):
            changed.append(rel)
    print('包里 %d 个文件；正式包 %d 个' % (len(mine), len(rel_names)))
    print('多出来的 %d：' % len(add)); [print('  +', x) for x in add]
    print('少了的 %d：' % len(gone)); [print('  -', x) for x in gone]
    print('内容不同的 %d：' % len(changed)); [print('  *', x) for x in changed]


def build(out, ref=None):
    if os.path.exists(out):
        sys.exit(out + ' 已存在，不覆盖')
    n = size = 0
    t = time.time()
    with zipfile.ZipFile(out + '.part', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel, data, full in entries(ref):
            if data is not None:
                z.writestr(mp.TOP + '/' + rel, data)
                size += len(data)
            else:
                z.write(full, mp.TOP + '/' + rel)
                size += os.path.getsize(full)
            n += 1
        for d in mp.EMPTY_DIRS:
            z.writestr(mp.TOP + '/' + d, b'')
    os.replace(out + '.part', out)
    print('files', n, 'raw %.1f MB' % (size / 1048576), 'zip %.1f MB' % (os.path.getsize(out) / 1048576), '%.0fs' % (time.time() - t))


def main():
    a = sys.argv[1:]
    ref = None
    if '--ref' in a:
        i = a.index('--ref')
        ref = a[i + 1]
        del a[i:i + 2]
    bad = guards()
    if bad:
        sys.exit('\n'.join(bad))
    if a and a[0] == '--dry':
        dry(a[1])
    elif len(a) == 1:
        build(a[0], ref)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
