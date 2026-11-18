# -*- coding: utf-8 -*-
"""给图形界面测试搭一个整合包副本 + 假的 APPDATA / LOCALAPPDATA（第 3 步：PowerShell 版和 Python 版的窗口都在副本上开，按钮写的东西都落在副本里）。

  gui_env.py <测试文件夹>        建好 <测试文件夹>\\root（整合包）、appdata、local，打印 JSON {root, appdata, local}

- launcher 复制（python / webview2 用目录联接，只读着用；dotnet、logs 不要）；reroll 只复制界面要读的几个文件；
- randomizer 只复制状态要看的几样（程序本身算哈希、diste\\Base\\enemy.txt、regulation.bin、最新的随机器日志），别的按钮写进去也只写副本；
- out 只复制 current_world.txt 和各个重随包的 reroll_report.txt；
- APPDATA：存档、版本记录、角色记录、最近两份启动前备份复制过来（只读真的）。"""
import _winapi
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
L = os.path.join(PALY, 'launcher')


def cp(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    elif os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def main(t):
    t = os.path.abspath(t)
    if os.path.exists(t):
        for n in ('python', 'webview2'):            # 先拆联接（只删联接本身），免得删副本时顺着删到真的文件夹
            j = os.path.join(t, 'root', 'launcher', n)
            if os.path.isjunction(j) if hasattr(os.path, 'isjunction') else os.path.exists(j):
                os.rmdir(j)
        shutil.rmtree(t)
    root, appdata, local = os.path.join(t, 'root'), os.path.join(t, 'appdata'), os.path.join(t, 'local')
    rl = os.path.join(root, 'launcher')
    big = {'python', 'dotnet', 'webview2', 'logs', 'reroll', '__pycache__'}
    os.makedirs(rl)
    for n in os.listdir(L):
        if n not in big:
            cp(os.path.join(L, n), os.path.join(rl, n))
    for n in ('python', 'webview2'):
        _winapi.CreateJunction(os.path.join(L, n), os.path.join(rl, n))
    old = os.path.join(PALY, 'dev', 'launcher_py', 'ps_old')       # 旧的 PowerShell 脚本（第 5 步挪出了整合包）：副本里放回去，新旧对照要用
    for n in os.listdir(old):
        if n.lower().endswith('.ps1'):
            shutil.copy2(os.path.join(old, n), os.path.join(rl, n))
    rr = os.path.join(L, 'reroll')
    for n in ('settings.json', 'erlib.py', 'savediff.py', 'state'):
        cp(os.path.join(rr, n), os.path.join(rl, 'reroll', n))
    bm = os.path.join(rr, 'data', 'bossmods')
    if os.path.isdir(bm):
        for n in os.listdir(bm):
            if os.path.isdir(os.path.join(bm, n, 'files')):
                os.makedirs(os.path.join(rl, 'reroll', 'data', 'bossmods', n, 'files'))
    rd = os.path.join(PALY, 'randomizer')
    for n in ('EldenRingRandomizer.exe', os.path.join('diste', 'Base', 'enemy.txt'), 'regulation.bin', 'config_eldenringrandomizer.toml'):
        cp(os.path.join(rd, n), os.path.join(root, 'randomizer', n))
    sl = os.path.join(rd, 'spoiler_logs')
    if os.path.isdir(sl):
        logs = sorted((e for e in os.scandir(sl) if e.is_file()), key=lambda e: e.stat().st_mtime_ns)
        for e in logs[-2:]:
            cp(e.path, os.path.join(root, 'randomizer', 'spoiler_logs', e.name))
    out = os.path.join(PALY, 'out')
    cp(os.path.join(out, 'current_world.txt'), os.path.join(root, 'out', 'current_world.txt'))
    for n in os.listdir(out):
        cp(os.path.join(out, n, 'reroll_report.txt'), os.path.join(root, 'out', n, 'reroll_report.txt'))
    for n in ('更新日志.txt', '启动.bat'):
        cp(os.path.join(PALY, n), os.path.join(root, n))
    os.makedirs(os.path.join(root, 'dll'))
    # APPDATA
    er = os.path.join(os.environ['APPDATA'], 'EldenRing')
    ter = os.path.join(appdata, 'EldenRing')
    for e in os.scandir(er):
        if e.is_dir() and e.name.isdigit():
            for n in ('ER0000.rng', 'ER0000.rngcoop'):
                cp(os.path.join(e.path, n), os.path.join(ter, e.name, n))
    dr = os.path.join(er, 'DarkReforged')
    for n in ('version.txt', 'packs.txt', '角色记录'):
        cp(os.path.join(dr, n), os.path.join(ter, 'DarkReforged', n))
    bk = os.path.join(dr, '启动前备份')
    if os.path.isdir(bk):
        ds = sorted((e for e in os.scandir(bk) if e.is_dir()), key=lambda e: e.name)
        for e in ds[-2:]:
            cp(e.path, os.path.join(ter, 'DarkReforged', '启动前备份', e.name))
    os.makedirs(local)
    print(json.dumps({'root': root, 'appdata': appdata, 'local': local}, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1])
