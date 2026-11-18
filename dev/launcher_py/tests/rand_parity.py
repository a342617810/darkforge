# -*- coding: utf-8 -*-
"""随机器自动操作的实跑对照（迁移第 2 步）：在第二套安装（默认 Game\\dark_reforged_coop）上，旧的 PowerShell（Invoke-RandomizeHiWorld）和
新的 Python（randomizer.invoke_randomize_hi_world）各生成一次死亡以上世界：同一个种子（最新 spoiler 日志的）、同一份精英指定，
随机器的输出应该逐字节一样（联机随机码就是靠这个）。会真的打开随机器窗口并自动点它。

不碰的：平常那一套随机结果（randomizer\\ 下的输出；函数自己先挪到 .dr_lo、跑完搬回来，这里再核对一遍）；
原来的 randomizer_hi 先改名放一边，测完放回来；随机器的设置（%LOCALAPPDATA%\\EldenRingRandomizer.Avalo，整个文件夹）测前复制一份、测完还原；
两次的输出（randomizer_hi.ps_out / .py_out）比完删掉。不能在 Claude 的命令沙盒里跑（建不了窗口），要在普通终端里跑。
用法：rand_parity.py [整合包根目录]"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
MAIN = os.path.join(GAME, 'dark_reforged')
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(GAME, 'dark_reforged_coop')
PY = os.path.join(MAIN, 'launcher', 'python', 'python.exe')
GAME_EXE = os.path.join(GAME, 'eldenring.exe')
RD = os.path.join(ROOT, 'randomizer')
HI = os.path.join(ROOT, 'randomizer_hi')
SETTINGS = os.path.join(os.environ['LOCALAPPDATA'], 'EldenRingRandomizer.Avalo')
LO_ITEMS = ['map', 'event', 'msg', 'script', 'sfx', 'regulation.bin', 'config_eldenringrandomizer.toml']


def say(s):
    print(time.strftime('%H:%M:%S ') + s, flush=True)


def hashes(top):
    out = {}
    for d, _, files in os.walk(top):
        for n in files:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, top).replace('\\', '/')
            rel = re.sub(r'\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}', '<时间>', rel)
            if n == 'regulation.bin':                    # 每次写都用新的随机 IV 加密：比解开以后的内容
                sys.path.insert(0, os.path.join(MAIN, 'launcher', 'reroll'))
                import erlib
                erlib.DLL_DIRS = [GAME]
                out[rel] = '解开后 ' + hashlib.sha256(erlib.read_regulation(p)).hexdigest()[:16]
                continue
            if n.endswith('.txt') and 'spoiler_logs' in rel:
                out[rel] = open(p, encoding='utf-8', errors='replace').read()
                continue
            if n == 'hi_source.json':
                j = json.load(open(p, encoding='utf-8-sig'))
                j.pop('time', None)
                j['hi_log'] = re.sub(r'\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}', '<时间>', j.get('hi_log', ''))
                out[rel] = json.dumps(j, sort_keys=True)
                continue
            h = hashlib.sha256()
            with open(p, 'rb') as f:
                for b in iter(lambda: f.read(1 << 20), b''):
                    h.update(b)
            out[rel] = h.hexdigest()[:16]
    return out


def lo_state():
    """平常那一套：输出文件的大小 + 修改时间（够看出有没有被换掉），日志列表"""
    s = {}
    for n in LO_ITEMS:
        p = os.path.join(RD, n)
        if os.path.isfile(p):
            st = os.stat(p)
            s[n] = (st.st_size, st.st_mtime_ns)
        elif os.path.isdir(p):
            tot = 0
            cnt = 0
            for d, _, fs in os.walk(p):
                for f in fs:
                    tot += os.path.getsize(os.path.join(d, f))
                    cnt += 1
            s[n] = (cnt, tot)
    s['logs'] = sorted(os.listdir(os.path.join(RD, 'spoiler_logs')))
    return s


PS_RUN = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
. '%s' *> $null
$r = Invoke-RandomizeHiWorld '%s'
Write-Host ('@@RESULT@@ ' + ($r | ConvertTo-Json -Compress))
'''
PY_RUN = r'''
import json, os, sys
sys.path.insert(0, %r)
from dfl import core, randomizer
core.setup_console()
ctx = core.Ctx(Action='randhi')
r = randomizer.invoke_randomize_hi_world(ctx, %r)
print('@@RESULT@@ ' + json.dumps(dict(r), ensure_ascii=False))
'''


def run(cmd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=e, stdin=subprocess.DEVNULL)
    lines = []
    for raw in iter(p.stdout.readline, b''):
        l = raw.decode('utf-8', 'replace').rstrip('\r\n')
        lines.append(l)
        print('    | ' + l, flush=True)
    p.wait()
    res = [l for l in lines if l.startswith('@@RESULT@@ ')]
    return json.loads(res[-1][11:]) if res else None, lines


def main():
    if subprocess.run(['tasklist', '/FI', 'IMAGENAME eq EldenRingRandomizer.exe'], capture_output=True).stdout.find(b'EldenRingRandomizer') >= 0:
        sys.exit('随机器开着，先关掉')
    tmp = tempfile.mkdtemp(prefix='dfrand_')
    say('备份随机器设置 → ' + tmp)
    shutil.copytree(SETTINGS, os.path.join(tmp, 'settings'))
    shutil.copytree(os.path.join(RD, 'presets'), os.path.join(tmp, 'presets'))
    keep_hi = HI + '.bak_parity'
    if os.path.exists(HI):
        os.rename(HI, keep_hi)
    lo0 = lo_state()
    results = {}
    try:
        say('==== PowerShell：Invoke-RandomizeHiWorld')
        ps_file = os.path.join(tmp, 'run.ps1')
        with open(ps_file, 'w', encoding='utf-8-sig') as f:
            f.write(PS_RUN % (os.path.join(ROOT, 'launcher', 'launcher.ps1').replace("'", "''"), GAME_EXE.replace("'", "''")))
        t = time.time()
        results['ps'] = run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File', ps_file])
        say('PowerShell 用了 %.0f 秒，结果 %s' % (time.time() - t, results['ps'][0]))
        if os.path.exists(HI):
            os.rename(HI, HI + '.ps_out')
        say('平常那一套没被动：%s' % (lo_state() == lo0))
        say('==== Python：randomizer.invoke_randomize_hi_world')
        t = time.time()
        results['py'] = run([PY, '-X', 'utf8', '-c', PY_RUN % (os.path.join(MAIN, 'launcher'), GAME_EXE)], {'DARKFORGE_ROOT': ROOT})
        say('Python 用了 %.0f 秒，结果 %s' % (time.time() - t, results['py'][0]))
        if os.path.exists(HI):
            os.rename(HI, HI + '.py_out')
        say('平常那一套没被动：%s' % (lo_state() == lo0))
        a = hashes(HI + '.ps_out') if os.path.exists(HI + '.ps_out') else {}
        b = hashes(HI + '.py_out') if os.path.exists(HI + '.py_out') else {}
        diff = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
        say('输出：PowerShell %d 个文件，Python %d 个文件，不同 %d 个 %s' % (len(a), len(b), len(diff), diff[:20]))
        for k in diff[:5]:
            x, y = a.get(k) or '', b.get(k) or ''
            if len(x) > 100 or len(y) > 100:                 # 日志：列出不同的行
                import difflib
                d = [l for l in difflib.unified_diff(x.splitlines(), y.splitlines(), 'PS', 'PY', lineterm='', n=0) if not l.startswith('@@')]
                say('   %s：不同的行 %d 行' % (k, len(d)))
                for l in d[:16]:
                    say('      ' + l[:200])
            else:
                say('   %s：PS %s / PY %s' % (k, x, y))
    finally:
        say('还原：随机器设置、预设、原来的 randomizer_hi；删掉两次的输出')
        for d in (HI + '.ps_out', HI + '.py_out'):
            if os.path.exists(d):
                shutil.rmtree(d)
        if os.path.exists(HI):
            shutil.rmtree(HI)
        if os.path.exists(keep_hi):
            os.rename(keep_hi, HI)
        shutil.rmtree(SETTINGS)
        shutil.copytree(os.path.join(tmp, 'settings'), SETTINGS)
        pr = os.path.join(RD, 'presets')
        shutil.rmtree(pr)
        shutil.copytree(os.path.join(tmp, 'presets'), pr)
        # 这两次随机化的日志（.hi_failed 之类）不留
        for n in os.listdir(os.path.join(RD, 'spoiler_logs')):
            if n not in lo0['logs']:
                os.remove(os.path.join(RD, 'spoiler_logs', n))
                say('  删掉测试留下的日志 ' + n)
        say('平常那一套还是原样：%s；randomizer_hi 放回去了：%s' % (lo_state() == lo0, os.path.exists(os.path.join(HI, 'hi_source.json'))))
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
