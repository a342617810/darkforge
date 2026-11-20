# -*- coding: utf-8 -*-
"""打包暗黑重铸（Darkforge）：python dev\\tools\\make_package.py <输出.zip>（例：..\\Darkforge_v0.9.4.zip）
   --dry：只数会打进去多少文件、检查测试开关，不写 zip。
不打包：本机生成的东西（out\\、日志、缓存、随机器输出、启动时生成的 DLL 定义文件）、dev\\。
测试用的开关开着时拒绝打包：dll\\dark_wings\\dark_wings.ini 的 debug。"""
import fnmatch
import os
import re
import sys
import time
import zipfile

SRC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # dev\tools\ 往上两层
TOP = 'darkforge'
EXCL = ['launcher/game_path.txt', 'launcher/randomizer_settings_path.txt', 'launcher/logs/*',
        'randomizer/presets/.dr_manual.preset',   # 本机点「打开随机器」时记的预设（本地状态，2026-11-13 打包时发现混进来了）
        'launcher/classic_ui.txt',     # 玩家选了「换回经典界面」时写的（launcher\webui.ps1），本机的选择
        'launcher/updates/*',          # 在线更新下载的更新包（launcher\update.py --fetch），更新完就删
        'hyp-launcher-ui-master.zip',  # 新界面参考的框架原包（只在本机留着参考，用到的部分已经在 launcher\ui）
        'mods/*', 'YAFSML自定义.ini',   # 玩家自己加的 mod 和加载器设置（launcher\usermods.ps1，用户 2026-11-16）：本机的，不发；更新也不碰
        'launcher/reroll/state/*', 'launcher/reroll/cache/*', 'launcher/reroll/backup_affix_zh/*', '*/__pycache__/*',
        'yafsml/YAFSML.ini', 'yafsml/YAFSML.ini.bak*', 'yafsml/log/*', 'yafsml/cache/*',
        'out/*', 'dev/*', 'packs/*', '存档备份/*', '崩溃诊断/*', '更新备份/*',     # 更新备份：导入离线更新包前备份的旧文件（launcher\update.py）      # packs：RNG Lands 原包，只在本地留着做参考（词条库已经提取）
        'randomizer/dll/*_log.txt', 'randomizer/dll/*.old','randomizer/map/*', 'randomizer/event/*', 'randomizer/msg/*', 'randomizer/script/*', 'randomizer/sfx/*',
        'randomizer/regulation.bin', 'randomizer/config_eldenringrandomizer.toml', 'randomizer/spoiler_logs/*',
        'dll/logs/*', 'dll/*/logs/*', 'dll/*.log', 'dll/*/*.log', 'dll/*/*.old', 'dll/*/*.old2',
        'dll/dark_lock/no_menu_text.txt',   # 游戏脚本包这次没挂上时启动器写的标记（崩溃风险审查 2026-11-19 第 17 条），本机状态
        # 启动时（重随）生成、按本机内容写的 DLL 定义 / 记录
        'dll/dark_sell/inventory.txt', 'dll/dark_sell/difficulty.txt', 'dll/dark_sell/difficulty_tiers.txt', 'dll/dark_sell/ash_dup.txt',
        'dll/dark_sell/sell_items.txt', 'dll/dark_lock/lock_items.txt', 'dll/dark_core/festive.txt', 'dll/dark_core/container.txt',
        'dll/dark_core/items.txt', 'dll/dark_core/affixes.txt', 'dll/dark_core/scaling.txt', 'dll/dark_core/runtime.txt', 'dll/dark_core/devgive.txt',
        'dll/dark_core/procs.txt',
        'dll/dark_core/bossmods.txt',      # Boss 模组：启动器每次启动写（这次加没加载）
        # Boss 模组的数据（launcher\reroll\data\bossmods）打包进去：还在内测（用户 2026-11-05「现在需要打包进去 还在内测所以没有关系」）；
        # 正式发布前要按各作者的许可重新定（dev\boss_mods\README.md「打包」）
        'boss/*',      # Boss 模组的原始压缩包：只给 dev\boss_mods\build.py 抽取数据用，运行时用的是 data\bossmods
        'randomizer_hi/*',      # 高难度世界（一键重随敌人时随机器多跑一遍的输出，按本机生成）
        'dll/dark_core/hpunify.txt', 'dll/dark_core/ovldrop.txt', 'dll/dark_core/ashes.txt', 'dll/dark_core/nightmare.txt', 'dll/dark_core/arena.txt', 'dll/dark_core/notes.txt', 'dll/dark_core/curses.txt',
        'dll/dark_core/fusion.txt', 'dll/dark_core/plague.txt', 'dll/dark_core/unseen.txt', 'dll/dark_core/wishstone.txt', 'dll/dark_core/shopstage.txt', 'dll/dark_core/clash.txt', 'dll/dark_core/hitwin.txt', 'dll/dark_core/foewin.txt', 'dll/dark_core/foefx.txt',
        'dll/dark_core/*_req.txt', 'dll/dark_core/arena_run.txt', 'dll/dark_core/arena_pick.txt',      # 开发工具写的请求（dark_core 看到就删，残留的不发）；斗技场试炼进行中的记录
        'dll/dark_core/coop_profile.txt', 'dll/dark_core/coop_host_code.txt',      # 联机兼容档案：联机启动时按本机写（联机分支 coop，联机计划 13.4）
        'dll/dark_core/frames.txt',      # 稀有度边框图标的对照表：启动时 menu.py 合成菜单包成功才写
        'dll/dark_core/boat.txt', 'dll/dark_core/boat_req.txt', 'dll/dark_core/devsp_req.txt', 'dll/dark_core/devgive_req.txt', 'dll/dark_core/devsp.txt', 'dll/dark_dev/*',      # 开发工具（游戏里 F9 的悬浮窗口），只在本机测试用
        'dll/sv_config.toml',     # SoulsVision 的配置按本机分辨率生成（位置是绝对像素），让它在别的电脑上重新生成
        'dll/SeamlessCoop/*',     # Seamless Co-op 不随整合包发（玩家自己下载放进来，联机时启动器才加载）
        # 联机还在测试（用户 2026-11-17：联机稳定了再公开）：联机测试包的使用说明、网页界面显示「联机」一类的测试开关不发
        '联机使用说明.txt', 'launcher/coop_test.txt', 'launcher/ersc_locale/*',      # ersc_locale：Seamless Co-op 的汉化（联机启动时才放进去）
        # Alt Saves：存档已由 YAFSML 的 replace_save_filename 隔离，启动器也不加载它（launcher.ps1 跳过 *alt_saves*），作者不许转载（记忆 nexus-publish-permissions）→ 不发（用户 2026-11-12「拿掉」）
        'yafsml/dll/eldenring_alt_saves.dll',
        # 说明文件都不发（用户 2026-11-11「以后打包时说明不要打包进去了」→「全部说明都不带」）：根目录「说明」文件夹、各处的 说明.txt
        '说明/*', '说明.txt', '*/说明.txt',
        '*.tmp', '*.prev', '*.prev.*', '*.bak', '*.bak_*', '*.packinfo.tmp', '*.rnglands.bak',
        # 源码仓库（用户 2026-11-16 传到 GitHub xp271/darkforge）：git 自己的文件不发
        '.git/*', '.git', '.gitignore', '.gitattributes']     # .git：git 工作目录（worktree，比如联机分支的文件夹）里它是指向主仓库的一个文件
# 上面排除了但要发的（用户 2026-11-16「带个说明文件进去」：mods 文件夹本身不发，里面这份怎么加 mod 的说明要发；说明文件不发的规矩对它例外）
KEEP = ['mods/使用说明.txt']
EMPTY_DIRS = ('yafsml/log/', 'yafsml/cache/', 'randomizer/spoiler_logs/')


def guards():
    bad = []
    wi = os.path.join(SRC, 'dll', 'dark_wings', 'dark_wings.ini')
    if os.path.exists(wi) and re.search(r'(?m)^\s*debug\s*=\s*(1|true|yes|on)\b', open(wi, encoding='utf-8-sig').read(), re.I):
        bad.append('dll/dark_wings/dark_wings.ini 里 debug 还开着（测试用），改回 0 再打包')
    bi = os.path.join(SRC, 'dll', 'dark_core', 'boat.ini')
    if os.path.exists(bi) and re.search(r'(?m)^\s*debug\s*=\s*(1|true|yes|on)\b', open(bi, encoding='utf-8-sig').read(), re.I):
        bad.append('dll/dark_core/boat.ini 里 debug 还开着（测试用），改回 0 再打包')
    # 无尽模式的生成器实验（开发用，rr/arena.py 的 GEN_*）：开着会在竞技场里多一个生成器和模板敌人
    try:
        import json
        st = json.load(open(os.path.join(SRC, 'launcher', 'reroll', 'settings.json'), encoding='utf-8'))
        if str((st.get('arena') or {}).get('generator_test') or '').strip():
            bad.append('launcher/reroll/settings.json 的 arena.generator_test 还开着（生成器实验），改回 "" 再打包')
    except Exception as e:
        bad.append('读不了 settings.json：%s' % e)
    # 启动器换成 Python 以后（v0.10.14）包里不能再有 PowerShell 脚本：杀毒软件把以前的 .ps1 当成后门（用户 2026-11-18，火绒报 Meterpreter）
    ps = [rel for _, rel in files() if rel.lower().endswith(('.ps1', '.psm1', '.psd1'))]
    if ps:
        bad.append('包里还有 PowerShell 脚本（启动器已经换成 Python，不能再发 .ps1）：' + '、'.join(ps[:10]))
    return bad


def files():
    for root, dirs, names in os.walk(SRC):
        dirs[:] = sorted(d for d in dirs if d != '.git')       # git 仓库的内部文件不走（很多、不打包）
        for f in sorted(names):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, SRC).replace(os.sep, '/')
            if rel in KEEP or not any(fnmatch.fnmatch(rel, p) for p in EXCL):
                yield full, rel


def main():
    dry = '--dry' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    bad = guards()
    if bad and not dry:
        sys.exit('\n'.join(bad))
    if dry:
        n = size = 0
        tops = {}
        for full, rel in files():
            n += 1
            size += os.path.getsize(full)
            tops[rel.split('/')[0]] = tops.get(rel.split('/')[0], 0) + 1
        print('会打包 %d 个文件，%.1f MB；按顶层：%s' % (n, size / 1048576, tops))
        for b in bad:
            print('！', b)
        return
    if len(args) != 1:
        sys.exit(__doc__)
    out = args[0]
    if os.path.exists(out):
        sys.exit('%s 已存在，不覆盖旧包' % out)
    n = size = 0
    t = time.time()
    with zipfile.ZipFile(out + '.part', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for full, rel in files():
            z.write(full, TOP + '/' + rel)
            n += 1
            size += os.path.getsize(full)
        for d in EMPTY_DIRS:
            z.writestr(TOP + '/' + d, b'')
    os.replace(out + '.part', out)
    print('files', n, 'raw %.1f MB' % (size / 1048576), 'zip %.1f MB' % (os.path.getsize(out) / 1048576), '%.0fs' % (time.time() - t))


if __name__ == '__main__':
    main()
