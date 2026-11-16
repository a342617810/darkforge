# -*- coding: utf-8 -*-
"""原版文件从哪来（正式发布不带随机器，dev\\release\\第三方分离.md 第 3 节）：
  - 装了随机器：用它带的 randomizer\\diste\\Vanilla（地图、事件、对话平放在一层，文字包在 msg\\<语言>\\）；
  - 没装：regulation.bin 用玩家游戏目录 Game\\ 下那份（check_regulation 核对是不是原版），其余从游戏 Data0 解出来，
    放 cache\\vanilla\\<Data0 指纹>\\<原路径>，同一个游戏版本只解一次。Data0 里没有的（地图在 Data1~3）拿不到，
    只有开敌人随机时才要原版地图，那时随机器一定在。
环境变量 DR_VANILLA_FROM_GAME=1：装了随机器也从游戏取（测试用）。
游戏目录从 erlib.DLL_DIRS 里找（有 Data0.bhd 的那个），调用方照常传 --dll-dir <游戏 Game 目录>。

命令行（启动器的 Get-VanillaSource 用）：
  python vanilla.py prepare --dll-dir <游戏 Game 目录>
  → 一行 JSON：{ok, from: "randomizer" / "game", reg: regulation 路径, msg: 文字包目录（下面是 <语言>\\item_dlc02…）, check: 核对结果, msg_err}
  python vanilla.py fingerprint <regulation.bin> [名字]   重新生成 data\\vanilla_regulation.json 里的一条（开发用）"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import erlib  # noqa: E402

PALY = os.path.dirname(os.path.dirname(HERE))
DISTE = os.path.join(PALY, 'randomizer', 'diste', 'Vanilla')
CACHE = os.path.join(HERE, 'cache', 'vanilla')
PEM = os.path.join(HERE, 'data', 'menu', 'data0_key.pem')
FINGERPRINTS = os.path.join(HERE, 'data', 'vanilla_regulation.json')
MSG_FILES = [os.path.join('msg', lang, 'item_dlc02.msgbnd.dcx') for lang in ('engus', 'zhocn')]


def from_game():
    """这次原版文件从游戏取（没装随机器，或者设了 DR_VANILLA_FROM_GAME）"""
    return bool(os.environ.get('DR_VANILLA_FROM_GAME')) or not os.path.isfile(os.path.join(DISTE, 'regulation.bin'))


def game_dir():
    for d in erlib.DLL_DIRS:
        if d and os.path.isfile(os.path.join(d, 'Data0.bhd')):
            return d
    return None


def _diste_path(rel):
    parts = rel.replace('/', os.sep).split(os.sep)
    p = os.path.join(DISTE, *parts) if parts[0] == 'msg' else os.path.join(DISTE, parts[-1])
    return p if os.path.isfile(p) else None


def cache_dir(g):
    """这个游戏版本的缓存目录：按 Data0.bhd 的大小和修改时间分（游戏更新了就换一个）"""
    st = os.stat(os.path.join(g, 'Data0.bhd'))
    return os.path.join(CACHE, '%x_%x' % (st.st_size, int(st.st_mtime)))


_arc = {}


def _archive(g):
    if g not in _arc:
        _arc[g] = erlib.GameArchive(os.path.join(g, 'Data0.bhd'), open(PEM, encoding='ascii').read())
    return _arc[g]


def path(rel):
    """原版文件 rel（相对游戏根，比如 event\\common.emevd.dcx）的本地路径；拿不到返回 None"""
    if not from_game():
        return _diste_path(rel)
    g = game_dir()
    if not g:
        return None
    out = os.path.join(cache_dir(g), rel.replace('/', os.sep))
    if os.path.isfile(out):
        return out
    try:
        data = _archive(g).read('/' + rel.replace(os.sep, '/'))
    except FileNotFoundError:
        return None
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, out)
    return out


def _digest(raw):
    b = erlib.Bnd4(raw)
    return hashlib.sha256(raw).hexdigest(), {n: hashlib.sha1(b.get(n)).hexdigest() for n in sorted(b.entries)}


def check_regulation(reg_path):
    """(是不是原版, 说明)：和 data\\vanilla_regulation.json 里认识的原版比（解密后的内容）"""
    try:
        known = json.load(open(FINGERPRINTS, encoding='utf-8'))['versions']
    except (OSError, ValueError, KeyError):
        return False, '没有原版指纹表，没核对'
    full, params = _digest(erlib.read_regulation(reg_path))
    for v in known:
        if v['sha256'] == full:
            return True, '和原版一样（%s）' % v['name']
    best = min(known, key=lambda v: sum(params.get(n) != h for n, h in v['params'].items()) + len(set(params) - set(v['params'])))
    diff = sorted(n for n in set(params) | set(best['params']) if params.get(n) != best['params'].get(n))
    return False, '和整合包认识的原版（%s）有 %d 个参数表不一样：%s%s' % (
        best['name'], len(diff), '、'.join(x.replace('.param', '') for x in diff[:6]), ' …' if len(diff) > 6 else '')


def prepare():
    if not from_game():
        return {'ok': True, 'from': 'randomizer', 'reg': os.path.join(DISTE, 'regulation.bin'), 'msg': os.path.join(DISTE, 'msg'),
                'check': '随机器带的原版'}
    g = game_dir()
    if not g:
        return {'ok': False, 'msg_err': '找不到游戏目录（没有 Data0.bhd）'}
    reg = os.path.join(g, 'regulation.bin')
    if not os.path.isfile(reg):
        return {'ok': False, 'msg_err': '游戏目录里没有 regulation.bin：%s' % g}
    miss = [rel for rel in MSG_FILES if not path(rel)]
    if miss:
        return {'ok': False, 'msg_err': '从游戏的 Data0 里解不出：%s' % '、'.join(miss)}
    same, note = check_regulation(reg)
    return {'ok': True, 'from': 'game', 'reg': reg, 'msg': os.path.join(cache_dir(g), 'msg'), 'check': note, 'vanilla': same}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('prepare', 'fingerprint'))
    ap.add_argument('args', nargs='*')
    ap.add_argument('--dll-dir', action='append', default=[])
    a = ap.parse_args()
    erlib.DLL_DIRS = [d for d in a.dll_dir if d]
    if a.cmd == 'prepare':
        try:
            r = prepare()
        except Exception as e:      # 启动器按 ok 判断，原因写进 msg_err
            r = {'ok': False, 'msg_err': '%s: %s' % (type(e).__name__, e)}
        print(json.dumps(r, ensure_ascii=False))
        return
    reg, name = a.args[0], (a.args[1] if len(a.args) > 1 else os.path.basename(a.args[0]))
    full, params = _digest(erlib.read_regulation(reg))
    try:
        d = json.load(open(FINGERPRINTS, encoding='utf-8'))
    except (OSError, ValueError):
        d = {'_说明': '认识的原版 regulation.bin（解密、解压后的内容）：整个的 SHA-256 和每个参数表的 SHA-1。vanilla.py fingerprint 生成', 'versions': []}
    d['versions'] = [v for v in d['versions'] if v['sha256'] != full] + [{'name': name, 'sha256': full, 'params': params}]
    with open(FINGERPRINTS, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=0)
    print('%s：%d 个参数表，共 %d 个版本' % (name, len(params), len(d['versions'])))


if __name__ == '__main__':
    main()
