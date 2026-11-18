# -*- coding: utf-8 -*-
"""把主文件夹（dark_reforged，main 分支）里 git 不管的运行库和数据复制到另一个工作目录（git worktree，比如联机分支的 dark_reforged_coop），
让那边也能跑重随、启动器和编译好的 DLL。E 盘是 exFAT，不能做目录链接，只能复制。
  python dev/tools/sync_worktree.py <主文件夹> <工作目录> [--dry]
只复制下面列的（大小和修改时间一样的跳过）；不删工作目录里多出来的文件；dll\\ 只在工作目录还没有时整份复制
（之后那边部署自己分支编译的 DLL，不能被主文件夹盖掉）。"""
import os
import shutil
import sys

# 每次都同步（只读使用的运行库和数据）
ALWAYS = ['launcher/python', 'launcher/dotnet', 'launcher/webview2', 'randomizer', 'randomizer_hi',
          'launcher/reroll/data/menu', 'launcher/reroll/data/bossmods']
# 只在工作目录还没有时复制一次（之后那边自己写）
# launcher/randomizer_settings_path.txt 不复制：它记的是主文件夹那份随机器的设置文件，复制过去以后工作目录的启动器把游戏路径、
# 选项写进了主文件夹随机器的设置，工作目录的随机器打开时读不到（用户 2026-11-17「联机的时候随机器没有默认加载保存的游戏路径」）
ONCE = ['dll', 'yafsml', 'launcher/reroll/cache', 'launcher/reroll/state',
        'launcher/game_path.txt']
SKIP_PARTS = {'__pycache__', '.git'}


def same(a, b):
    try:
        sa, sb = os.stat(a), os.stat(b)
    except OSError:
        return False
    return sa.st_size == sb.st_size and int(sa.st_mtime) == int(sb.st_mtime)


def copy_tree(src, dst, dry, stats):
    if os.path.isfile(src):
        items = [(src, dst)]
    else:
        items = []
        for dp, dn, fn in os.walk(src):
            dn[:] = [d for d in dn if d not in SKIP_PARTS]
            for f in fn:
                s = os.path.join(dp, f)
                items.append((s, os.path.join(dst, os.path.relpath(s, src))))
    for s, d in items:
        if same(s, d):
            stats['same'] += 1
            continue
        stats['copy'] += 1
        stats['bytes'] += os.path.getsize(s)
        if not dry:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry' in sys.argv
    if len(args) != 2:
        sys.exit(__doc__)
    main_dir, wt = (os.path.abspath(a) for a in args)
    if os.path.normcase(main_dir) == os.path.normcase(wt):
        sys.exit('主文件夹和工作目录不能是同一个')
    for name in ALWAYS + ONCE:
        src, dst = os.path.join(main_dir, name), os.path.join(wt, name)
        if not os.path.exists(src):
            print('  没有，跳过：' + name)
            continue
        if name in ONCE and os.path.exists(dst):
            print('  已经有，不覆盖：' + name)
            continue
        st = {'same': 0, 'copy': 0, 'bytes': 0}
        copy_tree(src, dst, dry, st)
        print('  %s：复制 %d 个（%.1f MB），一样的 %d 个%s' % (name, st['copy'], st['bytes'] / 1e6, st['same'], '（--dry，没写）' if dry else ''))


if __name__ == '__main__':
    main()
