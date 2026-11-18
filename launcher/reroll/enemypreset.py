# -*- coding: utf-8 -*-
"""敌人随机前生成随机器的自定义敌人预设（randomizer\\presets\\CustomEnemy.txt 里的 Enemies 一节），按地区控制精英比例：
settings.json 的 elite_share_by_band = 各掉落档（tier_bands）普通敌人位置里精英的目标比例（百分比，越往后越多；2026-10-31 起减半，最高 15）。
  - 前期（流程等级 <= early_elite_max_tier，默认 3 = 宁姆格福 / 半岛 / 史东薇尔）的普通敌人位置全部指定：
    按目标比例指定精英，其余指定非精英；early_ban_models（默认古龙 c4500 / c4510）前期一律不放；
  - 后面的地区：随机器自己抽时精英约占 4%（按上次随机化日志里没被我们指定的位置统计，每档单独算），
    只额外指定 (目标 - 自然比例) / (1 - 自然比例) 的位置放精英，其余照常交给随机器。
  没有 elite_share_by_band 时用旧规则（只管前期：early_elite_keep 的位置从全部普通敌人里抽）。
精英名单 = data\\elite_families.json 加上 data\\elite_dlc.json 里的名单。
启动器「敌人设置」（用户 2026-11-10）：elite_share_mult = 精英比例倍数（各档目标 × 它，每档最多 ELITE_CAP %）；
boss_in_basic_pct = 头目出现在普通敌人位置：预设 Classes 里 Basic（普通敌人）的来源组改成同类 (100 - p)% + 全部 Boss（AllBosses）p%
（随机器 enemy.txt 的分类名，随机器界面的说明：想让 10% 变成任意 Boss，就用 90%「同类」+ 10%「All Bosses」）；0 = 还原（只还原我们改过的）。

追忆 Boss（settings.json 的 remembrance_boss_shuffle，名单 data\\remembrance_bosses.json）：只在追忆 Boss 之间一对一打乱，
本体和本体换、DLC 和 DLC 换（没开 DLC 时只管本体）；同时写 RemoveSource，追忆 Boss 不再出现在其他位置。
名单的 dlc_extra（狂龙贝勒，用户 2026-11-02）不掉追忆，但也并进 DLC 组一起换。
指定的位置随机器不检查，这里照它对 Boss 的规则检查（canPlace）：目标的 exclude 标签、体型 size 不超过场地 arena、
不同模型、同一个多阶段 Boss 的两段不互换、excludemultiphase 的不放进多阶段的位置。

随机器只认它自己的预设格式：Enemies 的键是目标位置的实体编号，值是来源（这里也是一个实体编号）。
指定的位置随机器不再检查放置限制，所以这里照它的规则挑来源：目标的 exclude 标签、敏感目标不放嗅觉灵敏的敌人等。

  python enemypreset.py --randomizer-dir <randomizer> --settings <settings.json> --options "<随机器选项>"
退出码 0 = 已写好；10 = 不限制（已清掉自动生成的一节）；其他 = 失败（启动器就不开自定义预设）。"""
import argparse
import glob
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import erlib  # noqa: E402

MARK = '# Dark Reforged：按地区控制精英比例（enemypreset.py 自动生成，每次一键重随敌人前重写，手动改了也会被覆盖）'
MARK_RS = '# Dark Reforged：追忆 Boss 只在追忆 Boss 之间随机（enemypreset.py 自动生成，下一行每次重写）原有：'
OUR_LINE = ('# Dark Reforged：', '# RNG Lands：')       # 我们写的说明行开头（含改名前写的）
MARK_RS_ALL = (MARK_RS, '# RNG Lands：追忆 Boss 只在追忆 Boss 之间随机（enemypreset.py 自动生成，下一行每次重写）原有：')
# 高难度世界（dev\boss_mods\README.md：只在「死亡」以上加载的 Boss 改版，用户 2026-11-05「只在高难度固定」）：
# 整合了改版的 Boss 不随机、留在原场地（DontRandomize），也不放到别处（RemoveSource）。正常那一遍生成时还原
MARK_DR = '# Dark Reforged：高难度世界把整合了改版的 Boss 固定在原位（enemypreset.py 自动生成，下一行每次重写）原有：'
# 幽影之地的地图（随机器没开 DLC 时，这些地图的敌人不能当来源、位置也不指定；和 rr/arena.py 的 DLC_MAP_PREFIX 一样）。
# 以前漏了地下墓地、洞窟这类小地图 m40～m43：不开 DLC 时预设里还有它们，随机器每次都报错，一键重随敌人换 3 个种子都失败
# （玩家诊断包 2026-11-18，用户「补上」）
DLC_MAPS = ('m20', 'm21', 'm22', 'm25', 'm28', 'm40', 'm41', 'm42', 'm43', 'm61')
ELITE_CAP = 60              # 精英比例乘了倍数以后每档最多 60%
# Basic 来源组前面的说明行（缩进在 Basic 里面，strip_block 不动它；随机器界面另存预设会丢掉注释，所以「只有 default + AllBosses 两组」也算我们改的）
MARK_BP = '    # Dark Reforged：头目出现在普通敌人位置（启动器「敌人设置」，enemypreset.py 每次重写）'


def elite_shares(S):
    """各档精英目标比例 = elite_share_by_band × elite_share_mult（启动器「敌人设置」，默认 1；0 = 不额外放精英）"""
    sh = S.get('elite_share_by_band')
    if sh is None:
        return None
    m = S.get('elite_share_mult', 1.0)
    m = max(0.0, float(1.0 if m is None else m))
    return [min(float(ELITE_CAP), float(x) * m) for x in sh]


def boss_pct(S):
    """头目出现在普通敌人位置的比例 %（0~50）"""
    try:
        return max(0.0, min(50.0, float(S.get('boss_in_basic_pct', 0) or 0)))
    except (TypeError, ValueError):
        return 0.0


def basic_pools(body, pct):
    """预设 Classes 里 Basic（普通敌人）的来源组：pct > 0 → 同类 (1000 - w) + AllBosses w（权重按 1000 算）；
    pct = 0 → 是我们改的（有说明行，或者正好是 default + AllBosses 两组）才还原成 100% 同类，用户在随机器里自己配的不动"""
    lines = body.split('\n')
    try:
        ci = lines.index('Classes:')
    except ValueError:
        return body
    bi = None
    for i in range(ci + 1, len(lines)):
        l = lines[i]
        if l and not l.startswith(' '):
            break
        if l == '  Basic:':
            bi = i
            break
    if bi is None:
        return body
    end = bi + 1
    while end < len(lines) and (lines[end].startswith('   ') or not lines[end].strip()):
        end += 1
    blk = lines[bi + 1:end]
    ours = MARK_BP in blk
    pi = next((k for k, l in enumerate(blk) if l == '    Pools:'), None)
    if pi is not None:
        pe = pi + 1
        while pe < len(blk) and blk[pe].startswith(('    - ', '      ')):
            pe += 1
        pools = [l.split(':', 1)[1].strip() for l in blk[pi + 1:pe] if l.strip().startswith(('Pool:', '- Pool:'))]
        ours = ours or pools == ['default', 'AllBosses']
    else:
        pe = None
    w = int(round(pct * 10))
    if w <= 0 and not ours:
        return body
    new = [MARK_BP] if w > 0 else []
    new += ['    Pools:', '    - Weight: %d' % (1000 - w), '      Pool: default']
    if w > 0:
        new += ['    - Weight: %d' % w, '      Pool: AllBosses']
    rest = [l for k, l in enumerate(blk) if l != MARK_BP and not (pi is not None and pi <= k < pe)]
    at = 0 if pi is None else len([l for l in blk[:pi] if l != MARK_BP])
    rest[at:at] = new
    return '\n'.join(lines[:bi + 1] + rest + lines[end:])

BAD_SOURCE = {'noplace', 'norandom', 'unique', 'frames', 'invader', 'friendly', 'generated', 'immortal'}


def read_enemies(path):
    """randomizer\\diste\\Base\\enemy.txt 的 Enemies 一节：{实体: (地图, 类别, 标签集合)}"""
    t = open(path, encoding='utf-8').read()
    t = t[t.index('\nEnemies:'):]
    t = t[:t.index('\nPassiveAdjustments:')] if '\nPassiveAdjustments:' in t else t
    out = {}
    for blk in re.split(r'\n(?=- ID: )', t):
        m = re.match(r'- ID: (\d+)\n  Map: (\S+)\n  Name: \S+\n  Class: (\S+)', blk)
        if not m:
            continue
        tags = re.search(r'^  Tags: (.*)$', blk, re.M)
        out[int(m.group(1))] = (m.group(2), m.group(3), set(tags.group(1).split()) if tags else set())
    return out


def read_models(path):
    """{实体: 模型名（c4510 等）}"""
    t = open(path, encoding='utf-8').read()
    return {int(a): b.split('_')[0] for a, b in re.findall(r'^- ID: (\d+)\n  Map: \S+\n  Name: (\S+)$', t, re.M)}


def vanilla_npc(rand_dir, cache_dir):
    """原版地图里每个敌人实体的敌人参数编号（随机器自带的 diste\\Vanilla，读一次后缓存）"""
    d = os.path.join(rand_dir, 'diste')
    if not os.path.isdir(d):                  # 高难度世界 randomizer_hi 没有 diste：用旁边平常的随机器目录里的（同 rr/stage3.py 的 diste）
        d = os.path.join(os.path.dirname(os.path.abspath(rand_dir)), 'randomizer', 'diste')
    files = sorted(glob.glob(os.path.join(d, 'Vanilla', '*.msb.dcx')))
    sig = '%d|%d' % (len(files), sum(os.path.getsize(f) for f in files))
    cp = os.path.join(cache_dir, 'vanilla_enemy_npc.json')
    try:
        c = json.load(open(cp, encoding='utf-8'))
        if c.get('sig') == sig:
            return {int(k): v for k, v in c['npc'].items()}
    except Exception:
        pass
    print('  读取原版地图里的敌人（只在第一次做，约 1 分钟）...', flush=True)
    npc = {}
    for f in files:
        for e, n, _ in erlib.msb_enemy_parts(erlib.dcx_decompress(open(f, 'rb').read())):
            npc[e] = n
    os.makedirs(cache_dir, exist_ok=True)
    json.dump({'sig': sig, 'npc': npc}, open(cp, 'w', encoding='utf-8'))
    return npc


def target_tiers():
    """每个位置的强度等级（随机器日志里 scaling a->b 的 b，只和位置有关、和放了什么无关）：用随整合包发的固定表 data\\position_tiers.json
    （dev\\tools\\make_position_tiers.py 从历次 spoiler 日志合成）。以前读最近一次的日志，但每份日志只列出这一次被换掉的位置，
    覆盖的位置每次差约 2000 个，同一个种子生成的预设会跟着上一次的随机结果变，联机随机码对不上（dev\\coop\\联机计划.md 3.3）"""
    try:
        return {int(k): v for k, v in json.load(open(os.path.join(HERE, 'data', 'position_tiers.json'), encoding='utf-8'))['tiers'].items()}
    except (OSError, ValueError, KeyError):
        return {}


def forced_targets(text):
    """预设里上次自动生成的指定：{目标: 来源}"""
    out, on = {}, False
    for line in text.splitlines():
        if line.startswith(OUR_LINE) and 'enemypreset.py' in line and not line.startswith(MARK_RS_ALL):
            on = True                           # 精英指定的说明行（含旧版本的写法），后面紧跟 Enemies
            continue
        if not on or line.startswith('Enemies:'):
            continue
        m = re.match(r"\s+'(\d+)': '(\d+)'", line)
        if not m:
            break
        out[int(m.group(1))] = int(m.group(2))
    return out


def natural_share(rand_dir, ents, npc, fams, band_of, skip):
    """上次随机化里随机器自己抽的（不算 skip 里我们指定的位置）普通敌人位置，每档精英占多少：{档: 比例}（样本太少的档没有）。
    比例取 4 位小数：会打印出来记进联机随机码（nat_text），导入的一方用 --nat 原样传回来，不读自己的上一次结果"""
    logs = sorted(glob.glob(os.path.join(rand_dir, 'spoiler_logs', '*_log_*.txt')), key=os.path.getmtime, reverse=True)
    for lp in logs:
        t = open(lp, encoding='utf-8', errors='replace').read()
        if 'Basic placements' not in t:
            continue
        cnt = {}
        for m in re.finditer(r'^Replacing .*?\(#(\d+)\) in .*?: .*?\(#(\d+)\) from .*?\(scaling \d+->(\d+)\)', t, re.M):
            tgt, src, tier = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if tgt in skip or tgt not in ents or ents[tgt][1] != 'Basic':
                continue
            c = cnt.setdefault(band_of(tier), [0, 0])
            c[1] += 1
            c[0] += src in npc and npc[src] // 10000 in fams
        return {b: round(e / n, 4) for b, (e, n) in cnt.items() if n >= 50}
    return {}


def nat_text(nat):
    """{档: 比例} ↔ 「0=0.0412,1=0.0103」（没有是「-」）"""
    return ','.join('%d=%s' % (b, nat[b]) for b in sorted(nat)) or '-'


def parse_nat(text):
    return {int(k): float(v) for k, v in (x.split('=') for x in text.split(',') if '=' in x)}


def elite_families():
    from rr.common import elite_families as load      # 和重随的未鉴定物品掉落（精英往上一档）用同一份名单
    return load(os.path.join(HERE, 'data'))


def read_bosses(path):
    """enemy.txt 里的 Boss：{实体: (模型, 标签集合, 下一阶段)}"""
    t = open(path, encoding='utf-8').read()
    t = t[t.index('\nEnemies:'):]
    out = {}
    for blk in re.split(r'\n(?=- ID: )', t):
        m = re.match(r'- ID: (\d+)\n  Map: \S+\n  Name: (\S+)\n  Class: Boss\n', blk)
        if not m:
            continue
        tags = re.search(r'^  Tags: (.*)$', blk, re.M)
        nxt = re.search(r'^  NextPhase: (\d+)$', blk, re.M)
        out[int(m.group(1))] = (m.group(2).split('-')[-1].split('_')[0], set(tags.group(1).split()) if tags else set(),
                                int(nxt.group(1)) if nxt else 0)
    return out


def remembrance_force(bosses, groups, options, rng):
    """追忆 Boss 一对一打乱：{目标: 来源}（每组内部换），换不出来的组返回 None"""
    final = {}                                  # 多阶段 Boss 的两段 → 最后一段（随机器的 multiPhase）
    for e, (_m, _t, nxt) in bosses.items():
        if nxt:
            final[e] = final[nxt] = nxt
    ignoresize = 'ignoresize' in options

    def named(tags, key):
        v = [x.split(':', 1)[1] for x in tags if x.startswith(key + ':')]
        return int(v[0]) if v and v[0].isdigit() else None

    def ok(src, tgt):
        (sm, st, _), (tm, tt, _) = bosses[src], bosses[tgt]
        if src == tgt or sm == tm or 'noplace' in st:
            return False
        for x in tt:
            if x.startswith('exclude:') and (x[8:] == str(src) or x[8:] in st):
                return False
        if 'sensitive' in tt and 'perceptive' in st:
            return False
        if not ignoresize or src == 2054390800:
            arena, size = named(tt, 'arena'), named(st, 'size')
            if (size or 0) > (arena if arena is not None else 2):
                return False
        if tgt in final and (final.get(src) == final[tgt] or 'excludemultiphase' in st):
            return False
        return True

    out = {}
    for ids in groups:
        ids = [e for e in ids if e in bosses]
        got = None
        for _ in range(3000):
            order, left, cur = ids[:], set(ids), {}
            rng.shuffle(order)
            order.sort(key=lambda t: sum(ok(s, t) for s in ids))   # 能放的来源少的位置先挑
            for t in order:
                cand = [s for s in sorted(left) if ok(s, t)]
                if not cand:
                    break
                s = cand[rng.randrange(len(cand))]
                cur[t] = s
                left.discard(s)
            if len(cur) == len(ids):
                got = cur
                break
        if got is None:
            return None
        out.update(got)
    return out


def strip_block(text):
    """去掉预设里原有的 Enemies 一节（连同我们的说明行），我们写的 RemoveSource 还原成原有的"""
    out, skip, rs, dr = [], False, None, None
    for line in text.splitlines():
        m = next((p for p in MARK_RS_ALL if line.startswith(p)), None)
        if m:
            rs = line[len(m):].strip()
            continue
        if line.startswith(MARK_DR):
            dr = line[len(MARK_DR):].strip()
            continue
        if dr is not None and line.startswith('DontRandomize:'):
            if dr:
                out.append('DontRandomize: ' + dr)
            dr = None
            continue
        if line.startswith(OUR_LINE) and 'enemypreset.py' in line:   # 我们的说明行（含旧版本写的）
            continue
        if rs is not None and line.startswith('RemoveSource:'):
            if rs:
                out.append('RemoveSource: ' + rs)
            rs = None
            continue
        if re.match(r'^Enemies:', line):
            skip = True
            continue
        if skip and (line.startswith((' ', '-')) or not line.strip()):
            continue
        skip = False
        out.append(line)
    return '\n'.join(out).rstrip('\n') + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--randomizer-dir', required=True)
    ap.add_argument('--settings', default=os.path.join(HERE, 'settings.json'))
    ap.add_argument('--options', default='')
    ap.add_argument('--dll-dir', action='append', default=[])
    ap.add_argument('--seed', type=int)
    ap.add_argument('--nat', help='联机随机码：随机器自然精英比例用这个（nat_text 的格式），不按上一次的随机结果算')
    ap.add_argument('--off', action='store_true', help='只清掉自动生成的 Enemies 一节')
    ap.add_argument('--preset', help='排查用：写到别的预设文件')
    ap.add_argument('--fixed-bosses', default='', help='高难度世界：这些 Boss（实体编号，逗号隔开；多阶段的每段都给）留在原位、不当来源')
    a = ap.parse_args()
    erlib.DLL_DIRS = [d for d in a.dll_dir if d] or [a.randomizer_dir]
    preset = a.preset or os.path.join(a.randomizer_dir, 'presets', 'CustomEnemy.txt')
    S = json.load(open(a.settings, encoding='utf-8'))
    keep = float(S.get('early_elite_keep', 1.0))
    max_tier = int(S.get('early_elite_max_tier', 3))
    shares = elite_shares(S)
    bands = S.get('tier_bands') or []
    bpct = boss_pct(S)
    base = open(preset, encoding='utf-8-sig').read() if os.path.isfile(preset) else ''
    if not base.strip():
        print('  找不到随机器的自定义预设 %s（先在随机器里打开一次自定义敌人）' % preset)
        return 2
    elite_on = not ((shares is None and keep >= 1.0) or (shares is not None and not bands))
    rem_on = bool(S.get('remembrance_boss_shuffle', True))
    fixed = sorted({int(x) for x in a.fixed_bosses.replace(';', ',').split(',') if x.strip()})
    if a.off or not (elite_on or rem_on or fixed):
        open(preset, 'w', encoding='utf-8').write(basic_pools(strip_block(base), 0 if a.off else bpct))
        print('  精英比例：不限制；追忆 Boss：不单独随机')
        if bpct > 0 and not a.off:
            print('  头目出现在普通敌人位置：约 %g%%' % bpct)
            return 0
        return 10

    rng = random.Random(a.seed if a.seed is not None else int.from_bytes(os.urandom(4), 'little'))
    dlc_on = 'dlc' in a.options.split()
    boss = {}
    if rem_on:
        rb = json.load(open(os.path.join(HERE, 'data', 'remembrance_bosses.json'), encoding='utf-8'))
        groups = [[int(k) for k in rb['base']]] + ([[int(k) for k in {**rb['dlc'], **rb.get('dlc_extra', {})}]] if dlc_on else [])
        groups = [[e for e in g if e not in fixed] for g in groups]          # 高难度世界：固定的不参加打乱
        boss = remembrance_force(read_bosses(os.path.join(a.randomizer_dir, 'diste', 'Base', 'enemy.txt')), groups, a.options.split(), rng)
        if boss is None:
            print('  追忆 Boss：在随机器的放置限制下排不出一对一的打乱，这次不单独随机')
            boss = {}
    elite = elite_force(a, S, base, rng, dlc_on) if elite_on else ({}, None)
    if elite is None and not boss and not fixed and bpct <= 0:
        return 3
    force, msg = elite or ({}, None)
    body = strip_block(base)
    if boss:                                    # 追忆 Boss 从所有来源池里拿掉（指定的不受影响）；原有的 RemoveSource 记在说明行里，下次还原
        m = re.search(r'^RemoveSource: *(.*)$', body, re.M)
        orig = m.group(1).strip() if m else ''
        if m:
            body = body[:m.start()] + body[m.end() + 1:]
        keep_rs = [orig] if orig and orig.lower() != 'none' else []
        body += MARK_RS + orig + '\nRemoveSource: ' + '; '.join(keep_rs + ['%d' % e for e in sorted(set(boss.values()) | set(fixed))]) + '\n'
    elif fixed:
        m = re.search(r'^RemoveSource: *(.*)$', body, re.M)
        orig = m.group(1).strip() if m else ''
        if m:
            body = body[:m.start()] + body[m.end() + 1:]
        keep_rs = [orig] if orig and orig.lower() != 'none' else []
        body += MARK_RS + orig + '\nRemoveSource: ' + '; '.join(keep_rs + ['%d' % e for e in fixed]) + '\n'
    if fixed:                                   # 高难度世界：固定的 Boss 不随机（原有的 DontRandomize 记在说明行里，下次还原）
        m = re.search(r'^DontRandomize: *(.*)$', body, re.M)
        orig = m.group(1).strip() if m else ''
        if m:
            body = body[:m.start()] + body[m.end() + 1:]
        keep_dr = [orig] if orig and orig.lower() != 'none' else []
        body += MARK_DR + orig + '\nDontRandomize: ' + '; '.join(keep_dr + ['%d' % e for e in fixed]) + '\n'
    force = {**force, **boss}
    body += MARK + '\nEnemies:\n' + ''.join("  '%d': '%d'\n" % kv for kv in sorted(force.items()))
    body = basic_pools(body, bpct)
    tmp = preset + '.tmp'
    open(tmp, 'w', encoding='utf-8').write(body)
    os.replace(tmp, preset)
    if msg:
        print(msg)
    if boss:
        print('  追忆 Boss：%s，只在追忆 Boss 之间一对一打乱（%d 个位置），不再出现在其他位置' % (
            '本体和本体换、DLC 和 DLC 换' if dlc_on else '本体之间换（没开 DLC）', len(boss)))
    if fixed:
        print('  高难度世界：%d 个 Boss 位置固定在原位（%s）' % (len(fixed), ' '.join(map(str, fixed))))
    if bpct > 0:
        print('  头目出现在普通敌人位置：约 %g%%（追忆头目除外）' % bpct)
    return 0


def elite_force(a, S, base, rng, dlc_on):
    """按地区控制精英比例的指定：({目标: 来源}, 报告一行)；找不到位置或来源返回 None"""
    keep = float(S.get('early_elite_keep', 1.0))
    max_tier = int(S.get('early_elite_max_tier', 3))
    shares = elite_shares(S)
    bands = S.get('tier_bands') or []
    ents = read_enemies(os.path.join(a.randomizer_dir, 'diste', 'Base', 'enemy.txt'))
    models = read_models(os.path.join(a.randomizer_dir, 'diste', 'Base', 'enemy.txt'))
    banned = set(S.get('early_ban_models', ['c4500', 'c4510']))
    npc = vanilla_npc(a.randomizer_dir, os.path.join(HERE, 'cache'))
    fams = elite_families()
    tiers = target_tiers()
    map_tiers = json.load(open(os.path.join(HERE, 'data', 'map_tiers.json'), encoding='utf-8'))

    def tier(e):
        return tiers.get(e) if e in tiers else map_tiers.get(ents[e][0])

    def band_of(t):
        return next((i for i, b in enumerate(bands) if t <= b.get('max_tier', 99)), len(bands) - 1)

    def is_elite(e):
        return npc[e] // 10000 in fams

    all_sources = [e for e, (mp, cls, tags) in ents.items()
                   if cls == 'Basic' and e in npc and not (tags & BAD_SOURCE) and (dlc_on or not mp.startswith(DLC_MAPS))]
    any_sources = [e for e in all_sources if models.get(e) not in banned]
    sources = [e for e in any_sources if not is_elite(e)]               # 前期的非精英
    early_elite = [e for e in any_sources if is_elite(e)]               # 前期的精英（不含禁用模型）
    late_elite = [e for e in all_sources if is_elite(e)]
    targets = [e for e, (mp, cls, tags) in ents.items()
               if cls == 'Basic' and not (tags & {'norandom', 'noplace'}) and (dlc_on or not mp.startswith(DLC_MAPS))]
    if shares is None:                                                  # 旧规则：只管前期
        targets = [e for e in targets if (tier(e) or 99) <= max_tier]
    if not sources or not targets or (shares is not None and not late_elite):
        print('  精英比例：没找到可用的位置或来源（%d / %d），跳过' % (len(targets), len(sources)))
        return None
    if shares is None:
        nat = {}
    elif a.nat:
        nat = parse_nat(a.nat)
    else:
        nat = natural_share(a.randomizer_dir, ents, npc, fams, band_of, set(forced_targets(base)))
    print('NAT:' + nat_text(nat))                 # randomize.ps1 收走记进 .preset（不显示）

    def ok(src, tgt):
        stags, ttags = ents[src][2], ents[tgt][2]
        for x in ttags:
            if x.startswith('exclude:') and (x[8:] == str(src) or x[8:] in stags):
                return False
        if 'sensitive' in ttags and 'perceptive' in stags:
            return False
        return src != tgt

    force = {}
    stat = {}                                   # 档 -> [位置数, 指定数, 指定精英数]
    for t in sorted(targets):
        ti = tier(t) or 99
        b = band_of(ti)
        st = stat.setdefault(b, [0, 0, 0])
        st[0] += 1
        if shares is None:
            pool = any_sources if rng.random() < keep else sources
        else:
            p = float(shares[min(b, len(shares) - 1)]) / 100.0
            if ti <= max_tier:
                pool = (early_elite or sources) if rng.random() < p else sources
            else:
                s0 = nat.get(b, 0.04)
                if rng.random() >= max(0.0, (p - s0) / (1.0 - s0)):
                    continue
                pool = late_elite
        for _ in range(30):
            src = pool[rng.randrange(len(pool))]
            if ok(src, t):
                force[t] = src
                st[1] += 1
                st[2] += is_elite(src)
                break
    if shares is None:
        msg = ('  前期精英：流程等级 <= %d 的 %d 个普通敌人位置全部指定（保留 %.0f%% 的精英机会，精英 %d 类）' % (max_tier, len(force), keep * 100, len(fams)))
    else:
        msg = ('  精英比例（精英 %d 类）：' % len(fams) + '；'.join(
            '%s 目标 %s%%（随机器自然 %.0f%%）：%d 个位置里指定 %d 个、其中精英 %d' % (
                bands[b].get('name', b) if b < len(bands) else b, shares[min(b, len(shares) - 1)], nat.get(b, 0.04) * 100, n, k, ke)
            for b, (n, k, ke) in sorted(stat.items())))
    return force, msg


if __name__ == '__main__':
    sys.exit(main())
