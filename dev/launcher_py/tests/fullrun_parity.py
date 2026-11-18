# -*- coding: utf-8 -*-
"""整条启动流程的对照（第 1 步收尾用）：在第二套安装（默认 Game\\dark_reforged_coop）上，分别用旧的 launcher.ps1 和新的 df.py
跑「生成但不启动」（-NoLaunch / --no-launch），比写出的 YAFSML.ini、bossmods.txt、当前世界、覆盖包里的文件、假 APPDATA 里的备份，
以及给玩家看的输出行。
重随有「没变就沿用」：PowerShell 先跑两遍（第二遍沿用），Python 再跑（也沿用），比第二遍和 Python 那遍的输出。
APPDATA / LOCALAPPDATA 用假的（放一个假的 ER0000.rng，不算新开局）；不启动游戏。
用法：fullrun_parity.py [整合包根目录] [动作,...]（默认 vanilla,rand,rand:high）"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
MAIN = os.path.join(GAME, 'dark_reforged')
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(GAME, 'dark_reforged_coop')
CASES = (sys.argv[2] if len(sys.argv) > 2 else 'vanilla,rand,rand:high').split(',')
PY = os.path.join(MAIN, 'launcher', 'python', 'python.exe')
STEAM_ID = '76561190000000000'


def fake_appdata(tmp):
    env = {'APPDATA': os.path.join(tmp, 'Roaming'), 'LOCALAPPDATA': os.path.join(tmp, 'Local')}
    save = os.path.join(env['APPDATA'], 'EldenRing', STEAM_ID)
    os.makedirs(save, exist_ok=True)
    with open(os.path.join(save, 'ER0000.rng'), 'wb') as f:
        f.write(b'\0' * 64)
    os.makedirs(env['LOCALAPPDATA'], exist_ok=True)
    # 随机器设置在 LOCALAPPDATA：用真的那份的副本（只读真的），找不到也行
    real = os.path.join(os.environ['LOCALAPPDATA'], 'EldenRingRandomizer.Avalo')
    if os.path.isdir(real):
        shutil.copytree(real, os.path.join(env['LOCALAPPDATA'], 'EldenRingRandomizer.Avalo'))
    return env


def run(cmd, env, extra=None):
    e = dict(os.environ)
    e.update(env)
    e.update(extra or {})
    r = subprocess.run(cmd, capture_output=True, env=e, stdin=subprocess.DEVNULL, timeout=1800)
    return r.returncode, r.stdout.decode('utf-8', 'replace').replace('\r\n', '\n').split('\n')


def sha(p):
    h = hashlib.sha256()
    if os.path.basename(p) == 'reroll_report.txt':        # 沿用时只改它的「时间：」「沿用：」两行（rr/reuse.py touch_report），两边跑的时刻不同
        txt = open(p, 'rb').read().decode('utf-8', 'replace')
        h.update('\n'.join(l for l in txt.splitlines() if not l.startswith(('时间：', '沿用：'))).encode('utf-8'))
        return h.hexdigest()[:16]
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()[:16]


def snapshot(appdata):
    s = {}
    for rel in ('yafsml/YAFSML.ini', 'dll/dark_core/bossmods.txt', 'out/current_world.txt'):
        p = os.path.join(ROOT, rel)
        s[rel] = open(p, 'rb').read() if os.path.isfile(p) else None
    out = os.path.join(ROOT, 'out')
    for d, _, files in os.walk(out):
        for n in files:
            p = os.path.join(d, n)
            s[os.path.relpath(p, ROOT).replace('\\', '/')] = sha(p)
    for d, _, files in os.walk(appdata):
        for n in files:
            p = os.path.join(d, n)
            rel = re.sub(r'\d{8}_\d{6}', '<时间>', os.path.relpath(p, appdata).replace('\\', '/'))
            s['APPDATA/' + rel] = 'file'
    return s


NOISE = [(re.compile(r'\d+(\.\d+)? ?秒'), '<秒>'), (re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?'), '<时间>'),
         (re.compile(r'\d{8}_\d{6}(_\d+)?'), '<时间>'), (re.compile(r'并行：\d+ 个进程.*'), '并行：<略>')]


def norm(lines):
    out = []
    for l in lines:
        for rx, rep in NOISE:
            l = rx.sub(rep, l)
        out.append(l.rstrip())
    while out and not out[-1]:
        out.pop()
    return out


def main():
    bad = 0
    for case in CASES:
        action, _, world = case.partition(':')
        print('==== %s %s' % (action, world or ''))
        with tempfile.TemporaryDirectory() as tmp:
            ps_env = fake_appdata(os.path.join(tmp, 'ps'))
            ps_cmd = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(ROOT, 'launcher', 'launcher.ps1'),
                      '-Action', action, '-NoLaunch'] + (['-BossWorld', world] if world else [])
            py_cmd = [PY, '-X', 'utf8', os.path.join(MAIN, 'launcher', 'df.py'), action, '--no-launch'] + (['--boss-world', world] if world else [])
            # 两边用同一个假存档目录、从同一个状态开始：一次性重随的记录 once.json 在第一遍里抽，各抽各的重随包当然不一样；
            # 路径也要一样（重随「没变就沿用」的签名里有它）。PowerShell 第一遍以后存一份，Python 跑之前还原回去
            run(ps_cmd, ps_env)                                    # 第一遍：该重做的重做
            keep = os.path.join(tmp, 'after_first')
            for k in ('APPDATA', 'LOCALAPPDATA'):
                shutil.copytree(ps_env[k], os.path.join(keep, k))
            c1, ps_out = run(ps_cmd, ps_env)                       # 第二遍：没变就沿用
            ps_snap = snapshot(ps_env['APPDATA'])
            for k in ('APPDATA', 'LOCALAPPDATA'):
                shutil.rmtree(ps_env[k])
                shutil.copytree(os.path.join(keep, k), ps_env[k])
            c2, py_out = run(py_cmd, ps_env, {'DARKFORGE_ROOT': ROOT})
            py_snap = snapshot(ps_env['APPDATA'])
            print('退出码 PS %d / PY %d' % (c1, c2))
            for k in sorted(set(ps_snap) | set(py_snap)):
                if ps_snap.get(k) != py_snap.get(k):
                    bad += 1
                    print('  文件不同：%s' % k)
            a, b = norm(ps_out), norm(py_out)
            if a != b:
                bad += 1
                import difflib
                print('  输出不同：')
                for l in list(difflib.unified_diff(a, b, 'PowerShell', 'Python', lineterm='', n=1))[:80]:
                    print('    ' + l)
            else:
                print('  输出一样（%d 行）' % len(a))
    print('不同的地方：%d' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
