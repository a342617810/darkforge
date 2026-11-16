# -*- coding: utf-8 -*-
"""一次性重随的记录：第一次重随时抽一次，记进 --state（%APPDATA%\\EldenRing\\DarkReforged\\角色记录\\once.json），以后启动原样还原；
删掉这个文件（或里面那一项）才重抽。每份记录按「原来的内容」算指纹：原版 / 随机器输出变了就是另一份。现在用它的：骨灰（ashes）"""
from .common import *  # noqa: F401,F403
import contextlib
import hashlib


def sig(*blobs):
    h = hashlib.sha1(b'once1')
    for x in blobs:
        h.update(x if isinstance(x, (bytes, bytearray)) else repr(x).encode())
    return h.hexdigest()[:16]


def _legacy(path):
    """2026-10-29 以前的位置：%APPDATA%\\EldenRing\\DarkReforged_once.json（启动器会搬进 DarkReforged\\角色记录，这里兜底；写总是写新位置）"""
    d = os.path.dirname(os.path.abspath(path))
    if os.path.basename(path) == 'once.json' and os.path.basename(d) == '角色记录':
        return os.path.join(os.path.dirname(os.path.dirname(d)), 'DarkReforged_once.json')
    return None


def _load(path):
    for p in (path, _legacy(path)):
        try:
            return json.load(open(p, encoding='utf-8')) if p else {}
        except FileNotFoundError:
            continue
    return {}


@contextlib.contextmanager
def own_rng(ctx, kind):
    """第一次抽的时候 ctx.rng 临时换成这一项自己的随机数（按重随种子和种类定），抽完换回来：
    不消耗全局的随机数，有没有记录，后面各步骤抽到的都一样（同一个联机种子，第一次联机启动的人和启动过的人对得上，dev\\coop\\联机计划.md 1.4）"""
    keep = ctx.rng
    ctx.rng = random.Random('once:%s:%s' % (ctx.seed, kind))
    try:
        yield
    finally:
        ctx.rng = keep


def get(ctx, kind, key):
    return (_load(ctx.a.state).get(kind) or {}).get(key)


def last(ctx, kind):
    """这一项最近记下的那份（不管指纹）：格子集合变了时，还在的格子沿用以前抽的（rr/shops.py gear_to_ash）"""
    d = _load(ctx.a.state).get(kind) or {}
    return list(d.values())[-1] if d else None


def put(ctx, kind, key, value):
    if ctx.a.noop:
        return
    st = _load(ctx.a.state)
    st.setdefault(kind, {})[key] = value
    os.makedirs(os.path.dirname(os.path.abspath(ctx.a.state)), exist_ok=True)
    tmp = ctx.a.state + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, ctx.a.state)


def world_seed(ctx):
    """这一局固定的种子（第一次抽了记下，新开局重置一次性重随时换）：不单独记录的小随机（黄金卢恩换成哪类未鉴定物品、
    宝箱里的原版装备换成什么、大蛇狩猎矛的种子）都按它定，每次启动结果一样（重随才能「输入没变就沿用上次的」，rr/reuse.py）"""
    v = getattr(ctx, 'world_seed', None)
    if v is None:
        v = get(ctx, 'world', 'seed')
        if v is None:
            v = random.Random('once:%s:world' % ctx.seed).getrandbits(62)
            put(ctx, 'world', 'seed', v)
        ctx.world_seed = v
    return v


def rng_for(ctx, *key):
    """按这一局的种子和 key 定的随机数（同一个 key 每次启动抽到的一样）"""
    return random.Random('%s:%s' % (world_seed(ctx), ':'.join(map(str, key))))
