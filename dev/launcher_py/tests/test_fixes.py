# -*- coding: utf-8 -*-
"""移植时修的老毛病里，只能单独测 Python 版的（PowerShell 版就是错的，没法对照）：
- 把 DR3 联机码误拿去「按联机随机码重随」（coopimport）：报「不是联机随机码」时日志里不能出现联机密码（以前打印前 80 个字，pw= 原样露出来）"""
import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H  # noqa: E402

from dfl import coop, randomizer  # noqa: E402
from dfl.core import Rec  # noqa: E402

RESULTS = []


def ok(name, cond, info=''):
    RESULTS.append(bool(cond))
    print(('OK   ' if cond else 'DIFF ') + name + ('' if cond else '：' + str(info)[:600]))


with tempfile.TemporaryDirectory() as tmp:
    env = H.fake_env(tmp)
    pw = 'Secr3tPassw0rdXY'
    code = 'DR3|v=0.10.14|m=rand|pw=' + base64.b64encode(pw.encode()).decode() + '|w=low|sc=allow_summons=1'
    old = randomizer.get_randomizer_status
    randomizer.get_randomizer_status = lambda ctx: Rec(Ok=True, Msg='')
    try:
        r, out = H.py_call(lambda ctx: coop.invoke_coop_import(ctx, code), env)
    finally:
        randomizer.get_randomizer_status = old
    text = '\n'.join(out)
    b64 = base64.b64encode(pw.encode()).decode()
    ok('coopimport 给 DR3 码：返回失败', r is False, r)
    ok('coopimport 给 DR3 码：说了不是联机随机码', '不是联机随机码' in text, text)
    ok('coopimport 给 DR3 码：日志里没有密码（明文和 base64 都没有）', pw not in text and b64 not in text, text)
    ok('coopimport 给 DR3 码：密码换成「去掉了」', 'pw=（去掉了）' in text, text)

# ---- 随机化完成的判断（wait_rand_result）：日志第 3 行的说明里就有「Basic placements」，不能当成完成；
#      要有「-- Basic placements」一节、而且日志不再变了；没看到「随机中」时一直等到超时（以前 30 秒后就判失败）
class Clock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s
        if self.on_tick:
            self.on_tick(self.t)


class FakeProc:
    pid = 1

    def poll(self):
        return None


class FakeBtn:
    def __init__(self):
        self.name = '随机化敌人'


HEAD = 'Options and seed: enemy seed:1\n\nCtrl+F \'Boss placements\' or \'Miniboss placements\' or \'Basic placements\' to see enemy placements.\n'


def run_wait(steps, seen_busy=False):
    """steps：[(到第几秒, 日志全文 or None, 按钮文字)]；返回 wait_rand_result 的结果和用了几秒"""
    with tempfile.TemporaryDirectory() as tmp:
        env = H.fake_env(tmp)
        root = os.path.join(tmp, 'root')
        logd = os.path.join(root, 'randomizer', 'spoiler_logs')
        os.makedirs(logd)
        os.makedirs(os.path.join(root, 'launcher'))
        clock = Clock()
        btn = FakeBtn()
        logp = os.path.join(logd, '2026-11-18_10.00.00_log_1_81236.txt')

        def tick(t):
            for at, txt, name in steps:
                if t - 1000 >= at:
                    if txt is not None and (not os.path.exists(logp) or open(logp, encoding='utf-8').read() != txt):
                        with open(logp, 'w', encoding='utf-8') as f:
                            f.write(txt)
                    if name is not None:
                        btn.name = name
        clock.on_tick = tick
        real = randomizer.time
        randomizer.time = clock
        try:
            r, _ = H.py_call(lambda ctx: randomizer.wait_rand_result(ctx, FakeProc(), btn, clock.time() - 1), env, root=root)
        finally:
            randomizer.time = real
        return r, clock.t - 1000


# 没看到「随机中」：40 秒时日志只有开头（说明里有那几个字），200 秒时写完了
r, t = run_wait([(40, HEAD, None), (200, HEAD + '-- Basic placements\nx\n', None)])
ok('完成判断：只有日志开头的说明 → 不算完成，等到真的写完（以前 30 多秒就判）', r == 'ok' and t >= 200, (r, t))
# 看到过「随机中」：变回来以后日志写完、不再变 → 完成
r, t = run_wait([(2, None, '随机中...'), (60, HEAD + '-- Basic placements\n', '随机化敌人')])
ok('完成判断：「随机中」→ 变回来 → 日志有那一节、不再变 → 完成', r == 'ok', (r, t))
# 日志里是报错 → 失败
r, t = run_wait([(2, None, '随机中...'), (20, HEAD + '   at RandomizerCommon.Foo()\n', '随机化敌人')])
ok('完成判断：日志里有报错 → 失败（换种子重试）', r == 'fail', (r, t))
# 一直没写完 → 超时
r, t = run_wait([(40, HEAD, None)])
ok('完成判断：一直没写完 → 15 分钟超时', r == 'timeout' and t >= 900, (r, t))

print('%d 项，%d 项不同' % (len(RESULTS), RESULTS.count(False)))
sys.exit(0 if all(RESULTS) else 1)
