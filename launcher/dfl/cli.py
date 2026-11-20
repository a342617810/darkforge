# -*- coding: utf-8 -*-
"""命令行入口（launcher.ps1 结尾的 param + switch）：python launcher\\df.py <动作> [参数]，动作名和以前的 -Action 一样。
输出：§ 开头的行是给玩家看的进度，图形界面只显示这几行和 [错误]；完整的在 launcher\\logs\\<时间>_<动作>.log。
退出码：几个要给图形界面看结果的动作（重随、联机、更新……）成功 0、失败 1；启动类的动作和以前一样总是 0。"""
import argparse
import sys

from . import core
from .core import Ctx, host, write_err, write_head

ACTIONS = ('list', 'vanilla', 'rand', 'randomizer', 'help', 'setgame', 'diag', 'watch', 'oncereset', 'randenemy', 'randhi', 'carryrand',
           'coop', 'coopvanilla', 'coopcode', 'coopimport', 'coophost', 'coophostvanilla', 'coopjoin', 'update', 'checkupdate', 'autoupdate')


def show_help():
    host('用法：双击整合包里的「启动.bat」打开图形界面。')
    host('')
    host('命令行（调试用，python launcher\\df.py <动作> [参数]）：')
    host('  list                               （状态）')
    host('  vanilla --dry-run                  （只打印将写入的配置）')
    host('  rand --dry-run')
    host('  vanilla --no-launch                （生成覆盖包、写配置，不启动）')
    host('  setgame --game-path "D:\\ELDEN RING\\Game"   （设置/修改游戏路径）')
    host('  randenemy                          （一键重随敌人）')
    host('  oncereset                          （一次性重随）')
    host('  update --update-zip "a.zip"        （导入离线更新包）')
    host('  checkupdate / autoupdate           （在线检查更新 / 下载并应用更新）')
    host('  coop / coopvanilla                 （联机启动 · 敌人随机 / 无敌人随机，要先放 Seamless Co-op）')
    host('  coopcode                           （复制联机码）')
    host('  coophost / coophostvanilla         （联机开房 · 敌人随机 / 无敌人随机）')
    host('  coopjoin [--code "DR4..."]         （加入队友：不给 --code 用上次联机 / 加入时的码）')
    host('  coopimport [--code "DR1|..."]      （按联机随机码重随敌人，不给 --code 读剪贴板）')


def parse(argv):
    p = argparse.ArgumentParser(prog='df.py', add_help=False)
    p.add_argument('action', nargs='?', default='help', choices=ACTIONS)
    p.add_argument('--game-pid', type=int, default=0)
    p.add_argument('--game-path', default='')
    p.add_argument('--from-pack', default='')
    p.add_argument('--code', default='')
    p.add_argument('--update-zip', default='')
    p.add_argument('--boss-world', default='', choices=('', 'high', 'low'))
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--no-launch', action='store_true')
    return p.parse_args(argv)


def code(ok):
    return 0 if ok else 1


def dispatch(ctx):
    a = ctx.Action
    if a == 'list':
        from .launch import show_status
        write_head('暗黑重铸 状态')
        show_status(ctx)
    elif a == 'setgame':
        from .gamepath import save_game_root, set_game_root_interactive, test_normalize_game_root
        if ctx.GamePath:
            root = test_normalize_game_root(ctx.GamePath)
            if not root:
                write_err('路径无效（需要包含 Game\\eldenring.exe）：' + ctx.GamePath)
                ctx.ExitCode = 1
                return
            save_game_root(ctx, root)
        else:
            set_game_root_interactive(ctx)
    elif a in ('vanilla', 'rand', 'coop', 'coopvanilla'):
        from .launch import invoke_launch
        invoke_launch(ctx, a in ('rand', 'coop'), a in ('coop', 'coopvanilla'))
    elif a == 'coopcode':
        from .coop import invoke_coop_code_action
        ctx.ExitCode = code(invoke_coop_code_action(ctx))
    elif a == 'coopimport':
        from .coop import invoke_coop_import
        ctx.ExitCode = code(invoke_coop_import(ctx, ctx.Code))
    elif a in ('coophost', 'coophostvanilla'):
        from .coop import invoke_coop_host
        ctx.ExitCode = code(invoke_coop_host(ctx, a == 'coophost'))
    elif a == 'coopjoin':
        from .coop import invoke_coop_join
        ctx.ExitCode = code(invoke_coop_join(ctx, ctx.Code))
    elif a == 'randenemy':
        from .randomizer import invoke_rand_enemy_action
        ctx.ExitCode = code(invoke_rand_enemy_action(ctx))
    elif a == 'randhi':
        from .randomizer import invoke_rand_hi_action
        ctx.ExitCode = code(invoke_rand_hi_action(ctx))
    elif a == 'carryrand':
        from .randomizer import invoke_carry_random
        ctx.ExitCode = code(invoke_carry_random(ctx, ctx.FromPack))
    elif a == 'randomizer':
        from .randomizer import invoke_randomizer
        invoke_randomizer(ctx)
    elif a == 'diag':
        from .diag import invoke_diag
        invoke_diag(ctx)
    elif a == 'watch':
        from .watch import invoke_crash_watch_safe
        invoke_crash_watch_safe(ctx, ctx.GamePid)
    elif a == 'oncereset':
        from .backup import invoke_once_reset
        invoke_once_reset(ctx)
    elif a == 'update':
        from .updates import invoke_update
        ctx.ExitCode = code(invoke_update(ctx, ctx.UpdateZip))
    elif a == 'checkupdate':
        from .updates import invoke_update_py
        ctx.ExitCode = code(invoke_update_py(ctx, ['--check']))
    elif a == 'autoupdate':
        from .updates import invoke_update_py
        ctx.ExitCode = code(invoke_update_py(ctx, ['--fetch']))
    else:
        show_help()


def main(argv=None):
    core.setup_console()
    o = parse(sys.argv[1:] if argv is None else argv)
    ctx = Ctx(Action=o.action, GamePid=o.game_pid, GamePath=o.game_path, FromPack=o.from_pack, Code=o.code, UpdateZip=o.update_zip,
              BossWorld=o.boss_world, DryRun=o.dry_run, NoLaunch=o.no_launch)
    core.start_run_log(ctx)
    try:
        dispatch(ctx)
    except SystemExit:
        raise
    except BaseException as e:            # 和 launcher.ps1 一样：写一行「运行出错」+ 位置，退出码 1
        core.report_crash(e)
        core.finish_run_log(ctx)
        return 1
    core.finish_run_log(ctx)
    return ctx.ExitCode if ctx.ExitCode is not None else 0
