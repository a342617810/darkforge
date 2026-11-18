# -*- coding: utf-8 -*-
"""给启动器画进度条（用户 2026-11-05「正在生成这一局的游戏数据……这一句后面加个简易进度条」）。

启动器（dfl\launch.py 的 invoke_reroll_generate）设环境变量 DR_PROGRESS=1 时才打印「§% <0~100>」这种行，图形界面（dfl\gui\app.py 的 on_run_line）
把它画成「正在生成这一局的游戏数据……」那一行后面的进度条；别人跑重随（测试、命令行）什么都不打印。
重随这边只走到 TOP（92%），剩下的是启动器之后合并游戏脚本、菜单（dfl\launch.py 的 write_ini_file 接着打 97、100）。

怎么算：重随分三段（load / run_steps / write_and_check），每段里一句一句执行。后台线程每 0.1 秒看一眼主线程正在这段函数的哪一句
（sys._current_frames，不拖慢主线程），按上次完整重随时每一句的用时加权（记在 cache\\progress.json，按那一句的代码认；
没记过的按平均算，一条记录都没有时每句 0.5 秒），一句里面按已经用掉的时间往前挪一点（最多到这一句的九成）。三段各占多少也按上次的用时分。"""
import ast
import bisect
import contextlib
import inspect
import json
import os
import sys
import textwrap
import threading
import time

ON = os.environ.get('DR_PROGRESS') == '1'
TOP = 92                  # 重随这边最多到这里（之后是启动器的游戏脚本、菜单）
STEP = 2                  # 每涨这么多才打印一行（运行日志里不会刷满屏）
DEFAULT_SECS = 0.5        # 没有记录的一句当它用这么久


def _statements(fn):
    """函数体里每一句：[(开始的行号, 认它的代码)]（行号是文件里的绝对行号，代码去掉注释和空白）"""
    src, start = inspect.getsourcelines(fn)
    tree = ast.parse(textwrap.dedent(''.join(src)))
    body = tree.body[0].body
    out = []
    for st in body:
        if isinstance(st, ast.Expr) and isinstance(getattr(st, 'value', None), ast.Constant) and isinstance(st.value.value, str):
            continue                                              # 文档字符串
        text = src[st.lineno - 1].split('#', 1)[0].strip()
        out.append((start + st.lineno - 1, '%s:%s' % (fn.__name__, text)))
    return out


class Bar:
    def __init__(self, here):
        self.path = os.path.join(here, 'cache', 'progress.json')
        try:
            self.hist = json.load(open(self.path, encoding='utf-8'))
        except Exception:
            self.hist = {}
        self.new = {}
        self.last = -STEP
        self.lock = threading.Lock()

    def mark(self, pct):
        if not ON:
            return
        pct = int(max(0, min(100, pct)))
        with self.lock:
            if pct < self.last + STEP and not (pct == TOP and pct > self.last):
                return
            self.last = pct
            sys.stdout.write('§%% %d\n' % pct)                    # 一次写完一整行，不和主线程的输出混在一行里
            sys.stdout.flush()

    def ranges(self, names):
        """三段各占 0~TOP 的哪一截：按上次各段的用时（没有记录按 10 : 70 : 20）"""
        dflt = {'load': 10.0, 'run_steps': 70.0, 'write_and_check': 20.0}
        w = [max(0.1, float(self.hist.get('@' + n, dflt.get(n, 10.0)))) for n in names]
        if not all('@' + n in self.hist for n in names):
            w = [dflt.get(n, 10.0) for n in names]
        tot, acc, out = sum(w), 0.0, {}
        for n, x in zip(names, w):
            out[n] = (TOP * acc / tot, TOP * (acc + x) / tot)
            acc += x
        return out

    @contextlib.contextmanager
    def track(self, fn, lo, hi):
        """主线程在 fn 里跑的时候，进度从 lo 走到 hi"""
        t_start = time.time()
        if not ON:
            yield
            return
        try:
            sts = _statements(fn)
        except Exception:
            sts = []
        if not sts:
            self.mark(lo)
            yield
            self.mark(hi)
            return
        lines = [ln for ln, _k in sts]
        keys = [k for _ln, k in sts]
        known = [float(self.hist[k]) for k in keys if k in self.hist]
        avg = sum(known) / len(known) if known else DEFAULT_SECS
        w = [max(0.01, float(self.hist.get(k, avg))) for k in keys]
        before = [sum(w[:i]) for i in range(len(w))]
        total = sum(w)
        code = fn.__code__
        main = threading.get_ident()
        stop = threading.Event()
        cur = {'i': None, 't': None}

        def where():
            f = sys._current_frames().get(main)
            while f is not None and f.f_code is not code:
                f = f.f_back
            return None if f is None else f.f_lineno

        def close(now):
            if cur['i'] is not None:
                k = keys[cur['i']]
                self.new[k] = self.new.get(k, 0.0) + (now - cur['t'])

        def run():
            while not stop.wait(0.1):
                ln = where()
                if ln is None:
                    continue
                i = max(0, bisect.bisect_right(lines, ln) - 1)
                now = time.time()
                if i != cur['i']:
                    close(now)
                    cur['i'], cur['t'] = i, now
                done = before[i] + min(now - cur['t'], 0.9 * w[i])
                self.mark(lo + (hi - lo) * done / total)

        self.mark(lo)
        th = threading.Thread(target=run, daemon=True)
        th.start()
        try:
            yield
        finally:
            stop.set()
            th.join()
            close(time.time())
            self.new['@' + fn.__name__] = time.time() - t_start
            self.mark(hi)

    def save(self):
        """完整重随跑完：这次记到的用时写回去（没跑到的句子留着上次的）"""
        if not ON or not self.new:
            return
        h = dict(self.hist)
        h.update({k: round(v, 3) for k, v in self.new.items()})
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            open(tmp, 'w', encoding='utf-8').write(json.dumps(h, ensure_ascii=False, indent=1, sort_keys=True))
            os.replace(tmp, self.path)
        except Exception:
            pass
