# -*- coding: utf-8 -*-
"""「一键重随敌人」的实跑（迁移第 2 步）：在第二套安装（默认 Game\\dark_reforged_coop）上用新的 df.py randenemy 跑一遍完整流程：
随机器换新种子随机化 + 死亡以上世界第二遍。种子是随机的，没法和 PowerShell 版逐字节比，只看流程走完、该有的东西都有：
退出码 0、新的 spoiler 日志和 .preset、随机器输出齐全、randomizer_hi\\hi_source.json 指向这次的日志、随机器设置里勾了 customenemy。
随机器设置文件的记录（launcher\\randomizer_settings_path.txt）先弄成「认不出来」，顺便测「第一次用：打开一次让它生成设置文件」那一步。

测之前：平常那一套输出、randomizer_hi 改名放一边，随机器设置（%LOCALAPPDATA%\\EldenRingRandomizer.Avalo）、预设、设置记录复制一份；
测完全部还原，这次生成的删掉。会真的打开随机器窗口并自动点它；要在普通终端里跑。用法：randenemy_smoke.py [整合包根目录]"""
import json
import os
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
RD = os.path.join(ROOT, 'randomizer')
HI = os.path.join(ROOT, 'randomizer_hi')
MAP = os.path.join(ROOT, 'launcher', 'randomizer_settings_path.txt')
SETTINGS = os.path.join(os.environ['LOCALAPPDATA'], 'EldenRingRandomizer.Avalo')
OUT_ITEMS = ['map', 'event', 'msg', 'script', 'sfx', 'regulation.bin', 'config_eldenringrandomizer.toml']
SUFFIX = '.bak_smoke'


def say(s):
    print(time.strftime('%H:%M:%S ') + s, flush=True)


def check(name, cond, info=''):
    say(('OK   ' if cond else 'FAIL ') + name + ('' if cond else '：' + str(info)[:500]))
    return bool(cond)


def main():
    if subprocess.run(['tasklist', '/FI', 'IMAGENAME eq EldenRingRandomizer.exe'], capture_output=True).stdout.find(b'EldenRingRandomizer') >= 0:
        sys.exit('随机器开着，先关掉')
    tmp = tempfile.mkdtemp(prefix='dfsmoke_')
    say('备份 → ' + tmp)
    shutil.copytree(SETTINGS, os.path.join(tmp, 'settings'))
    shutil.copytree(os.path.join(RD, 'presets'), os.path.join(tmp, 'presets'))
    shutil.copy2(MAP, os.path.join(tmp, 'map.txt'))
    logs0 = set(os.listdir(os.path.join(RD, 'spoiler_logs')))
    for n in OUT_ITEMS:
        p = os.path.join(RD, n)
        if os.path.exists(p):
            os.rename(p, p + SUFFIX)
    if os.path.exists(HI):
        os.rename(HI, HI + SUFFIX)
    # 设置记录弄成认不出来：测「第一次用这份随机器」
    with open(MAP, 'w', encoding='utf-8', newline='') as f:
        f.write(os.path.join(tmp, 'nope', 'user.config') + '\r\n' + os.path.join(RD, 'EldenRingRandomizer.exe') + '\r\n')
    ok = True
    try:
        fake = os.path.join(tmp, 'Roaming')
        os.makedirs(fake)
        e = dict(os.environ, DARKFORGE_ROOT=ROOT, APPDATA=fake)
        say('==== df.py randenemy')
        t = time.time()
        p = subprocess.Popen([PY, '-X', 'utf8', os.path.join(MAIN, 'launcher', 'df.py'), 'randenemy'], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=e, stdin=subprocess.DEVNULL)
        lines = []
        for raw in iter(p.stdout.readline, b''):
            l = raw.decode('utf-8', 'replace').rstrip('\r\n')
            lines.append(l)
            print('    | ' + l[:300], flush=True)
        code = p.wait()
        say('用了 %.0f 秒，退出码 %d' % (time.time() - t, code))
        new_logs = sorted(set(os.listdir(os.path.join(RD, 'spoiler_logs'))) - logs0)
        ok &= check('退出码 0', code == 0, code)
        ok &= check('打开过一次随机器生成设置文件', any('先打开一次让它生成设置文件' in l for l in lines), '')
        lo_log = [n for n in new_logs if n.endswith('.txt')]
        ok &= check('平常那一套：新的 spoiler 日志 1 份', len(lo_log) == 1, new_logs)
        ok &= check('平常那一套：日志旁边有 .preset', any(n.endswith('.preset') for n in new_logs), new_logs)
        ok &= check('平常那一套：输出齐全', all(os.path.exists(os.path.join(RD, n)) for n in OUT_ITEMS), [n for n in OUT_ITEMS if not os.path.exists(os.path.join(RD, n))])
        if lo_log:
            txt = open(os.path.join(RD, 'spoiler_logs', lo_log[0]), encoding='utf-8', errors='replace').read()
            ok &= check('平常那一套：日志写完了（有「-- Basic placements」一节）', '\n-- Basic placements' in txt)
            ok &= check('平常那一套：用了自定义敌人预设', 'customenemy' in txt.splitlines()[0])
        hs = os.path.join(HI, 'hi_source.json')
        if os.path.exists(hs):
            j = json.load(open(hs, encoding='utf-8-sig'))
            ok &= check('死亡以上世界：hi_source.json 指向这次的日志', lo_log and j.get('lo_log') == lo_log[0], j)
            ok &= check('死亡以上世界：输出齐全', all(os.path.exists(os.path.join(HI, n)) for n in OUT_ITEMS))
        else:
            ok &= check('死亡以上世界：有 hi_source.json（没开 Boss 模组时不做）', False, os.listdir(ROOT))
        mp = open(MAP, encoding='utf-8-sig').read().splitlines()
        ok &= check('设置记录换成了新生成的设置文件', mp and os.path.exists(mp[0]) and 'nope' not in mp[0], mp)
    finally:
        say('还原')
        for n in OUT_ITEMS:
            p = os.path.join(RD, n)
            if os.path.exists(p + SUFFIX):
                if os.path.isdir(p):
                    shutil.rmtree(p)
                elif os.path.exists(p):
                    os.remove(p)
                os.rename(p + SUFFIX, p)
        if os.path.exists(HI + SUFFIX):
            if os.path.exists(HI):
                shutil.rmtree(HI)
            os.rename(HI + SUFFIX, HI)
        for n in set(os.listdir(os.path.join(RD, 'spoiler_logs'))) - logs0:
            os.remove(os.path.join(RD, 'spoiler_logs', n))
        shutil.rmtree(SETTINGS)
        shutil.copytree(os.path.join(tmp, 'settings'), SETTINGS)
        pr = os.path.join(RD, 'presets')
        shutil.rmtree(pr)
        shutil.copytree(os.path.join(tmp, 'presets'), pr)
        shutil.copy2(os.path.join(tmp, 'map.txt'), MAP)
        say('还原完：日志列表和原来一样 %s；randomizer_hi 在 %s' % (set(os.listdir(os.path.join(RD, 'spoiler_logs'))) == logs0, os.path.exists(os.path.join(HI, 'hi_source.json'))))
        shutil.rmtree(tmp, ignore_errors=True)
    say('全部通过' if ok else '有没通过的')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
