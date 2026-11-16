# -*- coding: utf-8 -*-
"""装备样本：用 dark_core 自己的生成代码（generate + build_row，和游戏里鉴定是同一套）批量生成装备，给数值模型用。
build：从重随输出的 regulation 抽本体行（affixes.txt 的 wbase / pbase）→ 跑 dark_core 的 export_pool 测试 → pool.tsv；
load：读回来，{'bias': 偏向加点的候选数, 'w' / 'p' / 'a': {档: [件]}}。
武器、防具带生成后的整行参数（模型插进 regulation 当新的一行来算攻击力、减伤、常驻词条）；护符是模板护符 + 词条效果"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(HERE, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402

CORE_SRC = os.path.join(PALY, 'dev', 'dark_core')
CARGO = os.path.join(os.path.expanduser('~'), '.cargo', 'bin', 'cargo.exe')


def base_ids(defs):
    """affixes.txt 里能当本体的武器（wbase 类型 编号 …）和防具（pbase 部位 编号 …）"""
    w, p = set(), set()
    for line in open(os.path.join(defs, 'affixes.txt'), encoding='utf-8'):
        f = line.rstrip('\r\n').split('\t')
        if f[0] == 'wbase' and len(f) >= 3:
            w.add(int(f[2]))
        elif f[0] == 'pbase' and len(f) >= 3:
            p.add(int(f[2]))
    return w, p


def build(mode_dir, out, n):
    defs = os.path.join(mode_dir, 'core')
    bnd = erlib.Bnd4(erlib.read_regulation(os.path.join(mode_dir, 'regulation.bin')))
    W, P = erlib.Param(bnd.get('EquipParamWeapon.param')), erlib.Param(bnd.get('EquipParamProtector.param'))
    wids, pids = base_ids(defs)
    base = out + '.base'
    with open(base, 'w', encoding='utf-8', newline='\n') as f:
        for c, ids, tab in (('w', wids, W), ('p', pids, P)):
            for i in sorted(ids):
                if i in tab.rows:
                    f.write('%s\t%d\t%s\n' % (c, i, bytes(tab.rows[i]).hex()))
    env = dict(os.environ, DR_DEFS_DIR=defs, DR_POOL_BASE=base, DR_POOL_OUT=out, DR_POOL_N=str(n))
    r = subprocess.run([CARGO, 'test', '--release', '--lib', 'export_pool', '--', '--ignored', '--nocapture'],
                       cwd=CORE_SRC, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode or not os.path.isfile(out):
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit('装备样本导出失败（dark_core 的 export_pool 测试）')
    print(next((l.strip() for l in r.stdout.splitlines() if '装备样本' in l), '装备样本：好了'), flush=True)
    os.remove(base)


def nums(s, conv=float):
    return [conv(x) for x in s.split(',') if x != '']


def load(path):
    pool = {'bias': 1, 'w': {}, 'p': {}, 'a': {}}
    for line in open(path, encoding='utf-8'):
        f = line.rstrip('\r\n').split('\t')
        if f[0] == 'bias':
            pool['bias'] = int(f[1])
            continue
        cat, tier = f[0], int(f[2])
        if cat == 'w':
            it = {'base': int(f[3]), 'skill': int(f[5]), 'cor': nums(f[6]), 'req': nums(f[7], int), 'st': nums(f[9], int),
                  'res': nums(f[10], int), 'spec': int(f[12]), 'atk': int(f[13]), 'row': bytes.fromhex(f[14])}
        elif cat == 'p':
            it = {'base': int(f[3]), 'sps': [(int(x.split(':')[0]), x.split(':', 1)[1]) for x in f[4].split(',') if x],
                  'row': bytes.fromhex(f[5])}
        else:
            it = {'tal': int(f[3]), 'sp': int(f[4]), 'key': f[5]}
        it['tier'] = tier
        pool[cat].setdefault(tier, []).append(it)
    return pool


def build_weight(it, s):
    """和 dark_core 的 build_weight 一样：鉴定偏向加点时每把候选的权重（s = 力气、灵巧、智力、信仰、感应，力气按单手）"""
    cor, req = it['cor'], it['req']
    gap = sum(max(0, req[k] - s[k]) for k in range(5))
    put = [max(0, x - 10) for x in s]
    top = max(put)
    sc = sum(max(0.0, c) for c in cor)
    fit = sum(max(0.0, cor[k]) * put[k] for k in range(5)) / (sc * top) if sc > 0 and top > 0 else 0.5
    return 0.5 ** (gap / 4.0) * (0.1 + fit) ** 2
