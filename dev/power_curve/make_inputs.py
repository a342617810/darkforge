# -*- coding: utf-8 -*-
"""数值模型的输入：在副本上各跑一次重随（不随机敌人 / 随机敌人），再用 dark_core 的生成代码导出装备样本。
全部写在 inputs\\ 下（不碰 out\\、dll\\、真实的 %APPDATA%）：
  inputs\\plain\\           不随机敌人的重随输出（regulation.bin 等）；core\\、sell\\ 是这次写的 DLL 定义
  inputs\\rand\\            随机敌人的重随输出；maps\\ 是修补后的地图
  inputs\\pool.tsv         装备样本（dr_pool.py 导出：每类每档 --n 件，配方 + 生成后的参数行）
  inputs\\appdata\\         假的 APPDATA（一次性重随的记录 once.json 也在这里，两种情况共用一份）
用法：python -X utf8 make_inputs.py [--seed 7] [--n 400] [--only plain|rand|pool]
（敌人随机用的是 randomizer\\ 里最近一次的随机器输出；改了词条库、settings.json 或代码后重跑这个，再跑 model.py）"""
import argparse, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
RD = os.path.join(PALY, 'randomizer')
VAN = os.path.join(RD, 'diste', 'Vanilla')
GAME = os.path.normpath(os.path.join(PALY, '..'))
PY = os.path.join(PALY, 'launcher', 'python', 'python.exe')
INPUTS = os.path.join(HERE, 'inputs')


def run_reroll():
    """子进程里：DLL 定义改写到输入目录下（reroll.CORE_DIR / SELL_DIR），再调 reroll.main()"""
    out = sys.argv[sys.argv.index('--out') + 1]
    sys.path.insert(0, RR)
    import reroll
    reroll.CORE_DIR = os.path.join(out, 'core')
    reroll.SELL_DIR = os.path.join(out, 'sell')
    for d in (reroll.CORE_DIR, reroll.SELL_DIR):
        os.makedirs(d, exist_ok=True)
    sys.argv = ['reroll.py'] + sys.argv[2:]
    reroll.main()


def reroll(mode, seed, rd=RD, name=None):
    """mode = plain / rand；rd = 用哪份随机器输出（rand_seeds.ps1 在副本上换种子跑的也行）；name = 输出到 inputs\\ 下哪个目录（默认 = mode）"""
    out = os.path.join(INPUTS, name or mode)
    shutil.rmtree(out, ignore_errors=True)
    app = os.path.join(INPUTS, 'appdata')
    os.makedirs(app, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', APPDATA=app)
    rand = mode == 'rand'
    args = [PY, '-X', 'utf8', __file__, '--reroll', '--base-reg', os.path.join(rd if rand else VAN, 'regulation.bin'), '--out', out,
            '--dll-dir', RD, '--dll-dir', GAME, '--label', mode, '--seed', str(seed), '--state', os.path.join(app, 'once.json')]
    if rand:
        args += ['--msg-src', os.path.join(rd, 'msg'), '--randomizer-dir', rd, '--maps-out', os.path.join(out, 'maps')]
    args += ['--msg-src', os.path.join(VAN, 'msg')]
    t = time.time()
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', env=env)
    ok = r.returncode == 0 and '[错误]' not in r.stdout and os.path.isfile(os.path.join(out, 'regulation.bin'))
    print('重随（%s）：%s，%.0f 秒' % (mode, '好了' if ok else '失败', time.time() - t), flush=True)
    if not ok:
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--n', type=int, default=400, help='装备样本：每类每档几件')
    ap.add_argument('--only', choices=('plain', 'rand', 'pool'), default=None)
    ap.add_argument('--randomizer-dir', default=RD, help='随机敌人用哪份随机器输出（默认 randomizer\\；rand_seeds.ps1 换种子跑的副本在 rz\\seed_<k>）')
    ap.add_argument('--rand-name', default='rand', help='随机敌人的重随输出放在 inputs\\ 下哪个目录（多个随机器种子时各用一个名字，model.py --rand-name 选）')
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(a.randomizer_dir, 'regulation.bin')) and a.only in (None, 'rand'):
        sys.exit('%s 里还没有随机器输出（先在启动器里随机化一次敌人）' % a.randomizer_dir)
    for mode in ('plain', 'rand'):
        if a.only in (None, mode):
            reroll(mode, a.seed, a.randomizer_dir if mode == 'rand' else RD, a.rand_name if mode == 'rand' else None)
    if a.only in (None, 'pool'):
        import dr_pool
        dr_pool.build(os.path.join(INPUTS, 'rand'), os.path.join(INPUTS, 'pool.tsv'), a.n)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--reroll':
        run_reroll()
    else:
        main()
