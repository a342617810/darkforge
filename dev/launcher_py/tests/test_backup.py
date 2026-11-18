# -*- coding: utf-8 -*-
"""backup.ps1（+ launcher.ps1 的 Invoke-LaunchBackup / Invoke-OnceReset）→ dfl/backup.py 对照测试。
- 假的 APPDATA（路径里特意带 ' 和 &：备份信息里的签名要照 ConvertTo-Json 的样子转义）；存档操作记录写在 copy_root 的副本里。
- 每个用例：清空 → 按同样的步骤建好存档 / 记录 / 旧文件（修改时间都是定死的）→ 跑 PowerShell 版 → 记下结果、输出、
  存档文件夹（每个文件的字节、修改时间、只读 / 隐藏）和 save_ops.txt → 清空重建 → 跑 Python 版 → 逐项比。
- 时间：两边的 Get-Date 都换成同一个固定时间（PowerShell 里定义同名函数盖住，Python 换 backup._now），备份文件夹名、记录行逐字一样。
- PowerShell 那边 dot-source 时会自己跑一次 Move-RngLegacyFiles：建好的 EldenRing 文件夹先挪开，snippet 开头再挪回来，免得被它先搬了。"""
import ctypes
import datetime
import os
import re
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from dfl import backup  # noqa: E402

RESULTS = []
NOW = datetime.datetime(2026, 11, 18, 10, 20, 30)
NEW_MTIME = datetime.datetime(2026, 11, 1).timestamp() * 1e9       # 这之后的修改时间 = 测试时新写的文件，不比


def norm(v):
    """异常的说法 .NET / Python 不一样：只比「出错了」"""
    if isinstance(v, str) and v.startswith('ERR:'):
        return 'ERR'
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    return v


def norm_lines(lines):
    """输出里异常的说法（「：」后面是 .NET / Python 给的原话）只比前半句"""
    out = []
    for l in lines:
        m = re.match(r'^(  \[提示\] (?:整理存档文件夹失败|启动前备份失败)[^：]*：)', l)
        out.append(m.group(1) + '<异常说明>' if m else l)
    return out


def check(name, ps, py):
    RESULTS.append(harness.same(name, ps, py))


def ns(day, sec=0, frac=0):
    """2026-10-<day> 的某个时间（本地时间）→ 纳秒；frac 是不足一秒的 100ns 数（测 Ticks）"""
    return int(datetime.datetime(2026, 10, day, 8, 0, 0).timestamp()) * 10 ** 9 + sec * 10 ** 9 + frac * 100


def put(path, data=b'x', mt=None, hidden=False, readonly=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode('utf-8'))
    if mt is not None:
        os.utime(path, ns=(mt, mt))
    if hidden:
        ctypes.windll.kernel32.SetFileAttributesW(path, 0x2)
    if readonly:
        os.chmod(path, stat.S_IREAD)


def setdir_mtime(path, mt):
    os.utime(path, ns=(mt, mt))


def info_json(tag, time, mode='', sig=''):
    return backup._ps_json_flat({'tag': tag, 'time': time, 'mode': mode, 'sig': sig})


def clear_attrs(p):
    for d, sub, fs in os.walk(p):
        for n in sub + fs:
            ctypes.windll.kernel32.SetFileAttributesW(os.path.join(d, n), 0x80)


class Case:
    def __init__(self, root, env, tmp):
        self.root, self.env, self.tmp = root, env, tmp
        self.er = os.path.join(env['APPDATA'], 'EldenRing')
        self.stage = os.path.join(env['APPDATA'], '_stage_EldenRing')
        self.data = os.path.join(self.er, 'DarkReforged')
        self.rec = os.path.join(self.data, '角色记录')
        self.bk = os.path.join(self.data, '启动前备份')
        self.old = os.path.join(self.data, '旧文件')
        self.logs = os.path.join(root, 'launcher', 'logs')
        self.ops = os.path.join(self.logs, 'save_ops.txt')
        self.man = os.path.join(tmp, '存档备份')

    def reset(self):
        for p in (self.er, self.stage, self.logs, self.man):
            if os.path.isdir(p):
                clear_attrs(p)
                shutil.rmtree(p)

    def snap(self):
        out = {}
        for top, tag in ((self.er, 'ER'), (self.man, 'MAN')):
            if not os.path.isdir(top):
                continue
            for d, sub, fs in os.walk(top):
                rel = os.path.relpath(d, top)
                out[tag + '/' + rel + '/'] = 'dir'
                for n in fs:
                    p = os.path.join(d, n)
                    st = os.lstat(p)
                    a = st.st_file_attributes
                    out[tag + '/' + os.path.join(rel, n)] = (open(p, 'rb').read(), st.st_mtime_ns if st.st_mtime_ns < NEW_MTIME else 'new',
                                                           bool(a & 1), bool(a & 2))
        if os.path.exists(self.ops):
            out['ops'] = open(self.ops, 'rb').read()
        return out

    def run(self, name, setup, snippet, fn, now=NOW):
        ps, ps_out, ps_tree, py, py_out, py_tree = self.run_both(setup, snippet, fn, now)
        check(name + '：结果', norm(ps), norm(py))
        check(name + '：输出', norm_lines(ps_out), norm_lines(py_out))
        check(name + '：写出的文件', [], tree_diff(ps_tree, py_tree))

    def run_fixed(self, name, setup, snippet, fn, expect, now=NOW):
        """有意和 PowerShell 版不同（2026-11-18 修的老毛病）：PowerShell 那边照跑（确认它确实是老毛病），Python 这边断言新的行为。
        expect(ps, ps_out, py, py_out, py_tree) -> bool"""
        ps, ps_out, ps_tree, py, py_out, py_tree = self.run_both(setup, snippet, fn, now)
        ok = bool(expect(ps, ps_out, py, py_out, py_tree))
        print(('OK   ' if ok else 'DIFF ') + name + '（有意的不同，断言新的行为）')
        if not ok:
            print('   PS:', repr(ps)[:800], ps_out[-5:])
            print('   PY:', repr(py)[:800], py_out[-5:])
        RESULTS.append(ok)

    def run_both(self, setup, snippet, fn, now=NOW):
        # PowerShell：建好 → 挪开（躲过 dot-source 时的自动整理）→ snippet 开头挪回来、盖住 Get-Date
        self.reset()
        setup(self)
        staged = os.path.isdir(self.er)
        if staged:
            os.rename(self.er, self.stage)
        pre = ''
        if staged:
            pre += "[IO.Directory]::Move('%s', '%s')\n" % (self.stage.replace("'", "''"), self.er.replace("'", "''"))
        pre += ("function Get-Date { param([string]$Format) $d = New-Object DateTime %d, %d, %d, %d, %d, %d; if ($Format) { return $d.ToString($Format) }; return $d }\n"
                % (now.year, now.month, now.day, now.hour, now.minute, now.second))
        ps, ps_out = harness.ps_call(pre + snippet, self.env, root=self.root)
        ps_tree = self.snap()
        self.reset()
        setup(self)

        def wrapped(ctx):
            old = backup._now
            backup._now = lambda: now
            try:
                return fn(ctx)
            finally:
                backup._now = old
        py, py_out = harness.py_call(wrapped, self.env, root=self.root)
        py_tree = self.snap()
        self.reset()
        return ps, ps_out, ps_tree, py, py_out, py_tree


def tree_diff(ps_tree, py_tree):
    diff = []
    for k in sorted(set(ps_tree) | set(py_tree)):
        a, b = ps_tree.get(k), py_tree.get(k)
        if a == b:
            continue
        if a is None or b is None:
            diff.append((k, 'PS 没有' if a is None else 'PY 没有'))
        elif k == 'ops':
            diff.append((k, 'PS: ' + a.decode('utf-8', 'replace')[-600:] + ' | PY: ' + b.decode('utf-8', 'replace')[-600:]))
        elif a == 'dir' or b == 'dir' or a[0] == b[0]:
            diff.append((k, 'PS %r / PY %r' % (a if a == 'dir' else a[1:], b if b == 'dir' else b[1:])))
        else:
            diff.append((k, '内容不同'))
    return diff


# ---------------------------------------------------------------- 存档文件夹的几种样子
S1, S2, S3 = '76561198000000001', '76561198000000002', '76561198000000003'


def st_none(c):
    pass


def st_empty(c):
    os.makedirs(c.er)


def st_saves(c):
    """两个 SteamID：单机 + 联机存档、.bak、游戏自己的文件；角色记录（单机 / 联机 / .tmp / 子文件夹）"""
    put(os.path.join(c.er, S1, 'ER0000.rng'), b'save1' * 100, ns(10))
    put(os.path.join(c.er, S1, 'ER0000.rng.bak'), b'bak1', ns(9))
    put(os.path.join(c.er, S1, 'ER0000.rngcoop'), b'coop1' * 50, ns(11, 5, 1234567))
    put(os.path.join(c.er, S1, 'ER0000.sl2'), b'vanilla', ns(5))
    put(os.path.join(c.er, S2, 'ER0000.rng'), b'save2', ns(12, 0, 1))
    put(os.path.join(c.er, 'GraphicsConfig.xml'), b'<x/>', ns(1))
    put(os.path.join(c.rec, 'items_0.txt'), '配方 0', ns(10, 1))
    put(os.path.join(c.rec, 'Lock.TXT'), 'lock', ns(10, 2))
    put(os.path.join(c.rec, 'once.json'), '{"a":1}', ns(10, 3))
    put(os.path.join(c.rec, 'half.tmp'), 'tmp', ns(10, 4))
    put(os.path.join(c.rec, 'sub', 'deep.txt'), 'deep', ns(10, 5))
    put(os.path.join(c.rec, 'hidden.txt'), 'h', ns(10, 6), hidden=True)
    put(os.path.join(c.rec, '联机', 'items_0.txt'), '联机配方', ns(11, 1))
    put(os.path.join(c.rec, '联机', 'wish.json'), '{}', ns(11, 2), readonly=True)
    put(os.path.join(c.data, 'version.txt'), '0.10.13', ns(3))


def st_records_only(c):
    put(os.path.join(c.rec, 'items_3.txt'), 'only records', ns(14))


def st_hidden_save(c):
    st_saves(c)
    ctypes.windll.kernel32.SetFileAttributesW(os.path.join(c.er, S2, 'ER0000.rng'), 0x2)


def st_coop_names(c):
    """联机存档改名的各种情况"""
    put(os.path.join(c.er, S1, 'ER0000.rng.co2'), b'old coop', ns(10))
    put(os.path.join(c.er, S1, 'ER0000.rng.co2.bak'), b'old coop bak', ns(9))
    put(os.path.join(c.er, S2, 'ER0000.rngcoop'), b'new coop', ns(12))
    put(os.path.join(c.er, S2, 'ER0000.rng.co2'), b'old coop 2', ns(10))
    # 三份：两份旧的修改时间一样、一份新的——.NET 的排序不稳定，两份旧的在记录里谁先写要和它一样
    put(os.path.join(c.er, S3, 'ER0000.rng.co2'), b'a', ns(10))
    put(os.path.join(c.er, S3, 'ER0000.rng.rng.co2'), b'b', ns(10))
    put(os.path.join(c.er, S3, 'ER0000.rng.rng.rng.co2'), b'c', ns(15))
    put(os.path.join(c.er, '76561198000000004', 'er0000.RNG.CO2'), b'upper', ns(10))
    put(os.path.join(c.er, '76561198000000005', 'ER0000.co2'), b'seamless own', ns(10))
    put(os.path.join(c.er, '76561198000000006', 'ER0000.rng.co2'), b'hidden', ns(10), hidden=True)
    put(os.path.join(c.er, '76561198000000007', 'ER0000.rng.co2'), b'same time 1', ns(10))
    put(os.path.join(c.er, '76561198000000007', 'ER0000.rng.rng.co2'), b'same time 2', ns(10))
    put(os.path.join(c.er, '76561198000000008', 'ER0000.rng.co2'), b'ro', ns(10))
    put(os.path.join(c.er, '76561198000000008', 'ER0000.rngcoop.bak'), b'ro bak', ns(8), readonly=True)
    put(os.path.join(c.er, '76561198000000008', 'ER0000.rng.co2.bak'), b'src bak', ns(9))
    put(os.path.join(c.er, 'loose.co2'), b'file at root', ns(10))


def st_legacy(c):
    """2026-10-29 以前散在 EldenRing 根目录的东西"""
    er = c.er
    put(os.path.join(er, S1, 'ER0000.rng'), b'save', ns(10))
    put(os.path.join(er, 'DarkReforged_items_0.txt'), 'legacy items 0', ns(5))
    put(os.path.join(er, 'DarkReforged_once.json'), '{"once":1}', ns(5, 1))
    put(os.path.join(er, 'DarkReforged_version.txt'), '0.9.0', ns(5, 2))
    put(os.path.join(er, 'DarkReforged_once.json.before_reset'), 'reset', ns(5, 3))
    put(os.path.join(er, 'DarkReforged_x.tmp'), 'tmp', ns(5, 4))
    put(os.path.join(er, 'darkreforged_lower.TXT'), 'lower', ns(5, 5))
    put(os.path.join(er, 'DarkReforged_hidden.txt'), 'hidden', ns(5, 6), hidden=True)
    put(os.path.join(er, 'DarkReforged_ro.txt'), 'readonly legacy', ns(5, 7), readonly=True)
    # 冲突：现在的比旧的新 → 旧的进 旧文件\；现在的比旧的旧 → 现在的进 旧文件\、旧的搬进来
    put(os.path.join(er, 'DarkReforged_items_1.txt'), 'legacy older', ns(5))
    put(os.path.join(c.rec, 'items_1.txt'), 'current newer', ns(20))
    put(os.path.join(er, 'DarkReforged_items_2.txt'), 'legacy newer', ns(25))
    put(os.path.join(c.rec, 'items_2.txt'), 'current older', ns(6))
    # 冲突、而且 旧文件\ 里同一秒的名字已经有了：挪不动，跳过（不算数）
    put(os.path.join(er, 'DarkReforged_items_3.txt'), 'legacy blocked', ns(5))
    put(os.path.join(c.rec, 'items_3.txt'), 'current 3', ns(21))
    put(os.path.join(c.old, 'DarkReforged_items_3.txt.' + NOW.strftime('%Y%m%d_%H%M%S')), 'occupied', ns(4))
    # 版本记录冲突
    put(os.path.join(c.data, 'version.txt'), '0.10.13', ns(26))
    # 旧的启动前备份文件夹
    ob = os.path.join(er, 'DarkReforged_启动前备份')
    put(os.path.join(ob, '20261001_100000_启动前', S1, 'ER0000.rng'), b'bk1', ns(1))
    put(os.path.join(ob, '20261001_100000_启动前', 'DarkReforged_items_0.txt'), 'bk1 rec', ns(1))
    put(os.path.join(ob, '20261001_100000_启动前', 'backup_info.json'), info_json('启动前', '2026-10-01 10:00:00'), ns(1))
    put(os.path.join(ob, '20261002_100000_启动前', S1, 'ER0000.rng'), b'bk2', ns(2))
    put(os.path.join(ob, '20261002_100000_启动前', 'backup_info.json'), info_json('启动前', '2026-10-02 10:00:00'), ns(2))
    put(os.path.join(c.bk, '20261002_100000_启动前', 'backup_info.json'), info_json('启动前', '2026-10-02 10:00:00'), ns(2))   # 同名的已经有了
    put(os.path.join(ob, 'stray_hidden.txt'), 'h', ns(3), hidden=True)
    # RNG Lands 时代的
    put(os.path.join(er, 'RNGLands_state.txt'), 'rng lands', ns(2))
    put(os.path.join(er, 'RNGLands_dir', 'a.txt'), 'rng lands dir', ns(2))
    put(os.path.join(er, 'RNGLands_hidden.txt'), 'rng hidden', ns(2), hidden=True)


def st_legacy_partial(c):
    """旧的启动前备份文件夹挪不空（里面的旧文件\\ 同名已有）：旧文件夹留着"""
    st_legacy(c)
    os.makedirs(os.path.join(c.old, '20261002_100000_启动前.' + NOW.strftime('%Y%m%d_%H%M%S'), '20261002_100000_启动前'))


def st_backups(c):
    """现在的存档 + 一堆旧备份（启动前 12 份、恢复前 6 份、没写完的、坏的），还有「存档备份」按钮存的"""
    st_saves(c)
    for i in range(12):
        d = os.path.join(c.bk, '202610%02d_090000_启动前' % (i + 1))
        put(os.path.join(d, S1, 'ER0000.rng'), b'old%d' % i, ns(i + 1))
        put(os.path.join(d, '角色记录', 'items_0.txt'), 'old rec %d' % i, ns(i + 1), readonly=(i == 0))
        put(os.path.join(d, 'backup_info.json'), info_json('启动前', '2026-10-%02d 09:00:00' % (i + 1), 'rand', 'sig%d' % i), ns(i + 1))
    for i in range(6):
        d = os.path.join(c.bk, '202610%02d_120000_恢复前' % (i + 1))
        put(os.path.join(d, S1, 'ER0000.rng'), b'pre%d' % i, ns(i + 1))
        put(os.path.join(d, 'backup_info.json'), info_json('恢复前', '2026-10-%02d 12:00:00' % (i + 1)), ns(i + 1))
    put(os.path.join(c.bk, '20261020_000000_启动前', S1, 'ER0000.rng'), b'unfinished', ns(20))      # 没写完的（没有 backup_info.json）
    put(os.path.join(c.bk, '20261021_000000_坏的', 'backup_info.json'), b'{not json', ns(21))
    put(os.path.join(c.bk, 'trail', 'backup_info.json'), b'{"tag":"x","time":"2026-10-15",}', ns(21))
    put(os.path.join(c.bk, 'dup', 'backup_info.json'), b'{"tag":"x","Tag":"y","time":"2026-10-15"}', ns(21))
    put(os.path.join(c.bk, 'iso', 'backup_info.json'), b'\xef\xbb\xbf{"Tag":"\xe5\x90\xaf\xe5\x8a\xa8\xe5\x89\x8d","TIME":"2026-10-15T08:30:00","mode":5,"sig":null}', ns(15))
    put(os.path.join(c.bk, 'slash', 'backup_info.json'), '{"tag":"手动","time":"2026/10/16 07:05"}', ns(16))
    put(os.path.join(c.bk, 'us', 'backup_info.json'), '{"tag":"手动","time":"10/17/2026 06:00:00","sig":"x"}', ns(17))
    put(os.path.join(c.bk, 'frac', 'backup_info.json'), '{"tag":"手动","time":"2026-10-18 06:00:00.1234567"}', ns(17))
    put(os.path.join(c.bk, 'zulu', 'backup_info.json'), '{"tag":"手动","time":"2026-10-19T08:30:00Z"}', ns(17))
    put(os.path.join(c.bk, 'offset', 'backup_info.json'), '{"tag":"手动","time":"2026-10-19T08:30:00+08:00","mode":1.0}', ns(17))
    put(os.path.join(c.bk, 'ticks', 'backup_info.json'), '{"tag":true,"time":5,"mode":false}', ns(17))
    put(os.path.join(c.bk, 'nested', 'backup_info.json'), '{"tag":{"a":1},"time":" 2026-10-14 ","sig":["a","b"],"tag2":1}', ns(17))
    put(os.path.join(c.bk, 'same', 'backup_info.json'), '{"tag":"x","tag":"手动","time":"2026-10-13"}', ns(17))
    put(os.path.join(c.bk, 'hid', 'backup_info.json'), '{"tag":"启动前","time":"2026-10-30 06:00:00"}', ns(17))
    ctypes.windll.kernel32.SetFileAttributesW(os.path.join(c.bk, 'hid'), 0x12)
    put(os.path.join(c.bk, 'file.json'), '{}', ns(1))
    # 「存档备份」按钮的
    put(os.path.join(c.man, '备份A', S1, 'ER0000.rng'), b'manA', ns(13))
    put(os.path.join(c.man, '备份A', '角色记录', 'items_0.txt'), 'manA rec', ns(13))
    put(os.path.join(c.man, '备份A', '角色记录', '联机', 'items_0.txt'), 'manA coop rec', ns(13))
    put(os.path.join(c.man, '备份B', 'x', 'y', S1, 'ER0000.RNG'), b'manB nested', ns(14))
    put(os.path.join(c.man, '备份B', 'DarkReforged_items_0.txt'), 'manB legacy rec', ns(14))
    put(os.path.join(c.man, '备份C_没存档', 'readme.txt'), 'nothing', ns(14))
    put(os.path.join(c.man, 'loose.txt'), 'file', ns(14))
    setdir_mtime(os.path.join(c.man, '备份A'), ns(13, 0, 7654321))
    setdir_mtime(os.path.join(c.man, '备份B'), ns(14, 1, 9999999))
    setdir_mtime(os.path.join(c.man, '备份C_没存档'), ns(14))


def st_bad_info(kind):
    """有意的不同用：一份正常的备份 + 一份 backup_info.json 坏掉的（PowerShell 版整个列表出错，Python 版跳过坏的）"""
    data = {'bad_time': '{"tag":"启动前","time":"18.11.2026"}', 'no_time': '{"tag":"启动前"}', 'empty': b'', 'bom_only': b'\xef\xbb\xbf',
            'spaces': b'  \r\n ', 'null': b'null', 'array': b'[1,2]'}[kind]

    def f(c):
        st_saves(c)
        put(os.path.join(c.bk, '20261001_090000_启动前', S1, 'ER0000.rng'), b'good', ns(1))
        put(os.path.join(c.bk, '20261001_090000_启动前', 'backup_info.json'), info_json('启动前', '2026-10-01 09:00:00'), ns(1))
        put(os.path.join(c.bk, '20261002_090000_启动前', 'backup_info.json'), data, ns(2))
    return f


def st_restore(c):
    """恢复用：现在的存档 + 记录（有备份里没有的）；三种备份：新的（带联机）、加联机以前的、2026-10-29 以前的平铺式（带 .co2）"""
    st_saves(c)
    put(os.path.join(c.rec, 'extra_after_backup.txt'), 'newer record', ns(15))
    put(os.path.join(c.rec, '联机', 'extra_coop.txt'), 'newer coop record', ns(15))
    put(os.path.join(c.rec, 'ro_record.txt'), 'read only', ns(15), readonly=True)
    put(os.path.join(c.rec, 'items_9.txt'), 'lower case current', ns(15))
    put(os.path.join(c.er, 'DarkReforged_legacy_at_restore.txt'), 'legacy', ns(2))
    b = os.path.join(c.bk, '20261005_090000_启动前')
    put(os.path.join(b, S1, 'ER0000.rng'), b'bk save', ns(5))
    put(os.path.join(b, S1, 'ER0000.rngcoop'), b'bk coop', ns(5))
    put(os.path.join(b, S3, 'ER0000.rng'), b'bk new steam id', ns(5))
    put(os.path.join(b, '角色记录', 'items_0.txt'), 'bk rec 0', ns(5))
    put(os.path.join(b, '角色记录', 'ITEMS_9.TXT'), 'bk upper', ns(5))
    put(os.path.join(b, '角色记录', '联机', 'items_0.txt'), 'bk coop rec', ns(5))
    put(os.path.join(b, 'backup_info.json'), info_json('启动前', '2026-10-05 09:00:00', 'coop', 'x'), ns(5))
    b = os.path.join(c.bk, '20261004_090000_启动前')                          # 加联机以前：没有联机存档、没有 联机\ 记录
    put(os.path.join(b, S1, 'ER0000.rng'), b'pre-coop save', ns(4))
    put(os.path.join(b, '角色记录', 'items_0.txt'), 'pre-coop rec', ns(4))
    put(os.path.join(b, 'backup_info.json'), info_json('启动前', '2026-10-04 09:00:00'), ns(4))
    b = os.path.join(c.bk, '20261003_090000_启动前')                          # 平铺式（记录带 DarkReforged_ 前缀），联机存档旧名字
    put(os.path.join(b, S1, 'ER0000.rng'), b'flat save', ns(3))
    put(os.path.join(b, S1, 'ER0000.rng.co2'), b'flat coop old name', ns(3))
    put(os.path.join(b, S2, 'ER0000.rng.co2'), b'flat coop old 2', ns(3))
    put(os.path.join(b, S2, 'ER0000.rngcoop'), b'flat coop new 2', ns(3))
    put(os.path.join(b, 'DarkReforged_items_0.txt'), 'flat rec', ns(3))
    put(os.path.join(b, 'DarkReforged_version.txt'), '0.8', ns(3))
    put(os.path.join(b, 'DarkReforged_once.json'), '{"flat":1}', ns(3))
    put(os.path.join(b, 'DarkReforged_skip.json'), '{}', ns(3))
    put(os.path.join(b, 'backup_info.json'), info_json('启动前', '2026-10-03 09:00:00'), ns(3))
    put(os.path.join(c.man, '手动1', S1, 'ER0000.rng'), b'manual', ns(2))
    put(os.path.join(c.man, '手动1', '角色记录', 'items_0.txt'), 'manual rec', ns(2))
    setdir_mtime(os.path.join(c.man, '手动1'), ns(2))


def st_restore_empty_now(c):
    """现在什么都没有（新电脑），从「存档备份」恢复"""
    put(os.path.join(c.man, '手动1', S1, 'ER0000.rng'), b'manual', ns(2))
    put(os.path.join(c.man, '手动1', '角色记录', '联机', 'a.txt'), 'manual coop rec', ns(2))
    setdir_mtime(os.path.join(c.man, '手动1'), ns(2))


def st_once(c):
    st_saves(c)


def st_once_legacy(c):
    put(os.path.join(c.er, 'DarkReforged_once.json'), '{"legacy once":1}', ns(5))
    put(os.path.join(c.old, 'once_' + NOW.strftime('%Y%m%d_%H%M%S') + '.json.before_reset'), 'occupied', ns(4))


def st_ops_log(lines_bytes):
    def f(c):
        st_saves(c)
        os.makedirs(c.logs, exist_ok=True)
        with open(c.ops, 'wb') as fh:
            fh.write(lines_bytes)
    return f


# ---------------------------------------------------------------- 两边的调用
PS_FILES = "function Conv-Files($l) { ,@($l | ForEach-Object { $_.FullName + '|' + $_.Length + '|' + $_.LastWriteTimeUtc.Ticks + '|' + $_.Name + '|' + $_.Directory.Name }) }\n"
PS_BK = ("function Conv-Bk($l) { ,@($l | ForEach-Object { @{ Dir = $_.Dir; Tag = $_.Tag; Time = $_.Time.ToString('yyyy-MM-dd HH:mm:ss.ffffff');"
         " Mode = $_.Mode; Sig = $_.Sig; Records = $_.Records; Saves = $_.Saves } }) }\n")


def py_files(l):
    return [f.FullName + '|' + str(f.Length) + '|' + str(f.LastWriteTimeUtcTicks) + '|' + f.Name + '|' + f.Directory.Name for f in l]


def py_bk(l):
    return [{'Dir': b.Dir, 'Tag': b.Tag, 'Time': b.Time.strftime('%Y-%m-%d %H:%M:%S.%f'), 'Mode': b.Mode, 'Sig': b.Sig, 'Records': b.Records, 'Saves': b.Saves}
            for b in l]


def ps_try(body):
    return 'try {\n' + body + '\n} catch { $__r = "ERR:" + $_.Exception.Message }\n'


def py_try(fn):
    def f(ctx):
        try:
            return fn(ctx)
        except Exception as e:
            return 'ERR:' + str(e)
    return f


def pick_ps(leaf, man=True):
    return "$b = @(Get-RngBackups %s | Where-Object { (Split-Path $_.Dir -Leaf) -eq '%s' })[0]\n" % ("$env:DF_MAN" if man else "''", leaf)


def pick_py(ctx, leaf, man):
    return [b for b in backup.get_rng_backups(ctx, man) if os.path.basename(b.Dir) == leaf][0]


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "U'ser & Co")
        env = {'APPDATA': os.path.join(base, 'Roaming'), 'LOCALAPPDATA': os.path.join(base, 'Local')}
        for v in env.values():
            os.makedirs(v)
        root = harness.copy_root(tmp)
        c = Case(root, env, tmp)
        env['DF_MAN'] = c.man
        man = c.man

        # ---- Add-RngOpsLog：没有记录、超过 300 行、各种编码 / 换行
        c.run('Add-RngOpsLog（没有记录）', st_none, "Add-RngOpsLog '第一行 & 记录'", lambda ctx: backup.add_rng_ops_log(ctx, '第一行 & 记录'))
        many = ''.join('2026-10-01 00:00:00  第 %d 行\r\n' % i for i in range(305)).encode('utf-8')
        for n, data in [('305 行带 BOM', b'\xef\xbb\xbf' + many), ('305 行无 BOM', many), ('LF', many.replace(b'\r\n', b'\n')),
                        ('只有 CR', many.replace(b'\r\n', b'\r')), ('结尾空行', b'a\r\n\r\n\r\n'), ('没有结尾换行', b'a\r\nb'),
                        ('GBK', '旧记录 中文\r\n'.encode('gbk')), ('UTF-16', b'\xff\xfe' + 'utf16 行\r\n'.encode('utf-16-le')),
                        ('空文件', b''), ('只有 BOM', b'\xef\xbb\xbf'), ('U+2028', 'a b\x0bc\x0cd\x85e\r\n'.encode('utf-8'))]:
            c.run('Add-RngOpsLog（%s）' % n, st_ops_log(data), "Add-RngOpsLog '新的一行'", lambda ctx: backup.add_rng_ops_log(ctx, '新的一行'))

        # ---- Test-RngCoopSaveName
        names = ['ER0000.rngcoop', 'er0000.RNGCOOP', 'ER0000.rng.co2', 'ER0000.RNG.CO2', 'ER0000.rng', '', 'ER0000.rng.rng.co2', 'ER0000.co2']
        c.run('Test-RngCoopSaveName', st_none, '$__r = @(%s)' % ', '.join("(Test-RngCoopSaveName '%s')" % n for n in names),
              lambda ctx: [backup.test_rng_coop_save_name(n) for n in names])

        # ---- Move-CoopSaveName
        for n, s in [('没有存档文件夹', st_none), ('空的', st_empty), ('各种旧名字', st_coop_names)]:
            c.run('Move-CoopSaveName（%s）' % n, s, '$__r = Move-CoopSaveName', lambda ctx: backup.move_coop_save_name(ctx))
        c.run('Move-CoopSaveName（跑两次）', st_coop_names, '$a = Move-CoopSaveName; $__r = @($a, (Move-CoopSaveName))',
              lambda ctx: [backup.move_coop_save_name(ctx), backup.move_coop_save_name(ctx)])

        # ---- Get-RngSaveFiles / Get-RngSavesIn / Get-RngRecordFiles / Get-RngRecordName / Get-RngFileSig
        for n, s in [('没有', st_none), ('空的', st_empty), ('存档和记录', st_saves), ('只有记录', st_records_only), ('联机旧名字', st_coop_names)]:
            c.run('Get-RngSaveFiles（%s）' % n, s, PS_FILES + '$__r = Conv-Files @(Get-RngSaveFiles)', lambda ctx: py_files(backup.get_rng_save_files(ctx)))
            c.run('Get-RngRecordFiles（%s）' % n, s, PS_FILES + '$__r = Conv-Files @(Get-RngRecordFiles)', lambda ctx: py_files(backup.get_rng_record_files(ctx)))
            c.run('Get-RngFileSig（%s）' % n, s, '$__r = Get-RngFileSig (@(Get-RngSaveFiles) + @(Get-RngRecordFiles))',
                  lambda ctx: backup.get_rng_file_sig(backup.get_rng_save_files(ctx) + backup.get_rng_record_files(ctx)))
        # 有意的不同（2026-11-18 修）：存档文件是隐藏的时，PowerShell 版 Get-Item（不带 -Force）出错、启动前备份跟着失败；Python 版照样认这份存档
        c.run_fixed('Get-RngSaveFiles（隐藏的存档）', st_hidden_save, ps_try(PS_FILES + '$__r = Conv-Files @(Get-RngSaveFiles)'),
                    py_try(lambda ctx: py_files(backup.get_rng_save_files(ctx))),
                    lambda ps, ps_out, py, py_out, t: str(ps).startswith('ERR') and isinstance(py, list)
                    and any('\\' + S2 + '\\ER0000.rng|' in x for x in py))
        c.run('Get-RngFileSig（空）', st_none, "$__r = Get-RngFileSig @()", lambda ctx: backup.get_rng_file_sig([]))
        bdirs = ['20261005_090000_启动前', '20261004_090000_启动前', '20261003_090000_启动前', 'nope']
        snip = PS_FILES + '$__r = @(foreach ($n in @(%s)) { $d = Join-Path $RngBackupDir $n; ,@((Conv-Files @(Get-RngSavesIn $d)), (Conv-Files @(Get-RngRecordFiles $d)), @(Get-RngRecordFiles $d | ForEach-Object { Get-RngRecordName $_ })) })' % ', '.join("'%s'" % b for b in bdirs)
        c.run('Get-RngSavesIn / Get-RngRecordFiles / Get-RngRecordName（备份里）', st_restore, snip,
              lambda ctx: [[py_files(backup.get_rng_saves_in(ctx, os.path.join(ctx.RngBackupDir, b))),
                            py_files(backup.get_rng_record_files(ctx, os.path.join(ctx.RngBackupDir, b))),
                            [backup.get_rng_record_name(f) for f in backup.get_rng_record_files(ctx, os.path.join(ctx.RngBackupDir, b))]] for b in bdirs])
        c.run('Get-RngSavesIn / Get-RngRecordFiles（存档备份）', st_backups,
              PS_FILES + '$__r = @(foreach ($d in @(Get-ChildItem -LiteralPath $env:DF_MAN -Directory)) { ,@((Conv-Files @(Get-RngSavesIn $d.FullName)), (Conv-Files @(Get-RngRecordFiles $d.FullName))) })',
              lambda ctx: [[py_files(backup.get_rng_saves_in(ctx, d.FullName)), py_files(backup.get_rng_record_files(ctx, d.FullName))]
                           for d in backup._gci(man, files=False)])

        # ---- Copy-RngRecord：联机的、带前缀的、复制到已有的只读文件上
        def st_copy(cc):
            st_restore(cc)
            put(os.path.join(cc.data, 'copydst', '联机', 'items_0.txt'), 'old ro', ns(1), readonly=True)
        c.run('Copy-RngRecord', st_copy,
              "$d = Join-Path $RngDataDir 'copydst'\nforeach ($n in @('20261005_090000_启动前', '20261003_090000_启动前')) { foreach ($f in @(Get-RngRecordFiles (Join-Path $RngBackupDir $n))) { Copy-RngRecord $f $d } }",
              lambda ctx: [backup.copy_rng_record(f, os.path.join(ctx.RngDataDir, 'copydst'))
                           for n in ('20261005_090000_启动前', '20261003_090000_启动前') for f in backup.get_rng_record_files(ctx, os.path.join(ctx.RngBackupDir, n))] and None)

        # ---- Move-RngItem（直接调）
        def st_item(cc):
            put(os.path.join(cc.er, 'a.txt'), 'a new', ns(20))
            put(os.path.join(cc.er, 'dst', 'a.txt'), 'a old', ns(10))
            put(os.path.join(cc.er, 'b.txt'), 'b old', ns(10))
            put(os.path.join(cc.er, 'dst', 'b.txt'), 'b new', ns(20))
            put(os.path.join(cc.er, 'dd', 'x.txt'), 'dir', ns(10))
            put(os.path.join(cc.er, 'dst', 'dd', 'y.txt'), 'dir dst', ns(10))
            put(os.path.join(cc.er, 'free.txt'), 'free', ns(10))
        snip = ("foreach ($p in @(@('a.txt', 'dst\\a.txt'), @('b.txt', 'dst\\b.txt'), @('dd', 'dst\\dd'), @('free.txt', 'new\\sub\\free.txt'))) {"
                " Move-RngItem (Get-Item -LiteralPath (Join-Path $RngSaveRoot $p[0])) (Join-Path $RngSaveRoot $p[1]) }")
        c.run('Move-RngItem', st_item, snip,
              lambda ctx: [backup.move_rng_item(ctx, backup.FileItem(os.path.join(ctx.RngSaveRoot, a)), os.path.join(ctx.RngSaveRoot, b))
                           for a, b in (('a.txt', 'dst\\a.txt'), ('b.txt', 'dst\\b.txt'), ('dd', 'dst\\dd'), ('free.txt', 'new\\sub\\free.txt'))] and None)

        # ---- Move-RngLegacyFiles
        for n, s in [('没有存档文件夹', st_none), ('空的', st_empty), ('没有旧文件', st_saves), ('旧版的文件', st_legacy), ('旧备份挪不空', st_legacy_partial)]:
            c.run('Move-RngLegacyFiles（%s）' % n, s, '$__r = Move-RngLegacyFiles', lambda ctx: backup.move_rng_legacy_files(ctx))
        c.run('Move-RngLegacyFiles（跑两次）', st_legacy, '$a = Move-RngLegacyFiles; $__r = @($a, (Move-RngLegacyFiles))',
              lambda ctx: [backup.move_rng_legacy_files(ctx), backup.move_rng_legacy_files(ctx)])

        # ---- Get-RngBackups
        c.run('Get-RngBackups（没有）', st_none, PS_BK + '$__r = Conv-Bk @(Get-RngBackups)', lambda ctx: py_bk(backup.get_rng_backups(ctx)))
        c.run('Get-RngBackups（一堆）', st_backups, PS_BK + '$__r = Conv-Bk @(Get-RngBackups)', lambda ctx: py_bk(backup.get_rng_backups(ctx)))
        c.run('Get-RngBackups（一堆 + 存档备份）', st_backups, PS_BK + '$__r = Conv-Bk @(Get-RngBackups $env:DF_MAN)',
              lambda ctx: py_bk(backup.get_rng_backups(ctx, man)))
        c.run('Get-RngBackups（存档备份文件夹不在）', st_backups, PS_BK + "$__r = Conv-Bk @(Get-RngBackups (Join-Path $env:DF_MAN 'nope'))",
              lambda ctx: py_bk(backup.get_rng_backups(ctx, os.path.join(man, 'nope'))))
        # 有意的不同：backup_info.json 坏了（空的 / 只有 null / 时间认不出来 / 没有时间）——PowerShell 版整个 Get-RngBackups 抛异常
        # （启动前备份、恢复列表都跟着失败）；Python 版跳过那一份，别的照常
        for kind in ('bad_time', 'no_time', 'empty', 'bom_only', 'spaces', 'null', 'array'):
            ps, _, _, py, _, _ = c.run_both(st_bad_info(kind), ps_try(PS_BK + '$__r = Conv-Bk @(Get-RngBackups)'),
                                            py_try(lambda ctx: py_bk(backup.get_rng_backups(ctx))))
            check('Get-RngBackups（坏的信息文件 %s）：PowerShell 版出错' % kind, 'ERR', norm(ps))
            check('Get-RngBackups（坏的信息文件 %s）：Python 版跳过坏的' % kind, ['20261001_090000_启动前'],
                  [os.path.basename(b['Dir']) for b in py] if isinstance(py, list) else py)
            ps, ps_out, _, py, py_out, py_tree = c.run_both(st_bad_info(kind), "Invoke-LaunchBackup 'rand'", lambda ctx: backup.invoke_launch_backup(ctx, 'rand'))
            check('Invoke-LaunchBackup（坏的信息文件 %s）：PowerShell 版备份失败' % kind, True, any('启动前备份失败' in l for l in ps_out))
            check('Invoke-LaunchBackup（坏的信息文件 %s）：Python 版照常备份' % kind,
                  ['  启动前备份：' + os.path.join(c.bk, NOW.strftime('%Y%m%d_%H%M%S') + '_启动前')], py_out)

        # ---- New-RngBackup
        for n, s in [('什么都没有', st_none), ('存档和记录', st_saves), ('只有记录', st_records_only)]:
            c.run('New-RngBackup（%s）' % n, s, "$__r = New-RngBackup '启动前' 'rand'", lambda ctx: backup.new_rng_backup(ctx, '启动前', 'rand'))
        c.run('New-RngBackup（没变：不重复存；换了 Tag 要存；同一秒改了文件 → _2）', st_saves,
              "$a = New-RngBackup '启动前' 'rand'; $b = New-RngBackup '启动前' '联机，coop'; $c = New-RngBackup '恢复前'\n"
              "Set-Content -LiteralPath (Join-Path $RngRecordDir 'items_0.txt') -Value 'changed' -Encoding UTF8\n"
              "(Get-Item -LiteralPath (Join-Path $RngRecordDir 'items_0.txt')).LastWriteTimeUtc = [datetime]::FromFileTimeUtc(%d)\n"
              "$d = New-RngBackup '启动前'; $e = New-RngBackup '启动前'\n$__r = @($a, $b, $c, $d, $e)" % ((ns(28) // 100) + 116444736000000000),
              lambda ctx: _py_multi(ctx))
        c.run('New-RngBackup（启动前只留 10 份、恢复前不动）', st_backups, "$__r = New-RngBackup '启动前' 'rand'", lambda ctx: backup.new_rng_backup(ctx, '启动前', 'rand'))
        c.run('New-RngBackup（恢复前只留 5 份）', st_backups, "$__r = New-RngBackup '恢复前'", lambda ctx: backup.new_rng_backup(ctx, '恢复前'))
        c.run_fixed('New-RngBackup（隐藏的存档：照样备份）', st_hidden_save, ps_try("$__r = New-RngBackup '启动前'"), py_try(lambda ctx: backup.new_rng_backup(ctx, '启动前')),
                    lambda ps, ps_out, py, py_out, t: str(ps).startswith('ERR') and str(py).endswith('_启动前')
                    and any(k.endswith(os.path.join(S2, 'ER0000.rng')) and '启动前备份' in k for k in t))

        # ---- Restore-RngBackup
        for leaf, n in [('20261005_090000_启动前', '新的（带联机）'), ('20261004_090000_启动前', '加联机以前的'), ('20261003_090000_启动前', '平铺式 + 旧联机名'),
                        ('手动1', '存档备份')]:
            c.run('Restore-RngBackup（%s）' % n, st_restore, PS_BK + pick_ps(leaf) + '$r = @(Restore-RngBackup $b)\n$__r = @{ done = $r; after = (Conv-Bk @(Get-RngBackups)) }',
                  lambda ctx, leaf=leaf: (lambda r: {'done': r, 'after': py_bk(backup.get_rng_backups(ctx))})(backup.restore_rng_backup(ctx, pick_py(ctx, leaf, man))))
        c.run('Restore-RngBackup（现在什么都没有）', st_restore_empty_now, PS_BK + pick_ps('手动1') + '$__r = @(Restore-RngBackup $b)',
              lambda ctx: backup.restore_rng_backup(ctx, pick_py(ctx, '手动1', man)))

        # ---- Invoke-LaunchBackup
        for n, s in [('什么都没有', st_none), ('存档和记录', st_saves), ('旧版的文件', st_legacy)]:
            c.run('Invoke-LaunchBackup（%s）' % n, s, "Invoke-LaunchBackup 'rand'", lambda ctx: backup.invoke_launch_backup(ctx, 'rand'))
        c.run_fixed('Invoke-LaunchBackup（隐藏的存档：照样备份）', st_hidden_save, "Invoke-LaunchBackup 'rand'", lambda ctx: backup.invoke_launch_backup(ctx, 'rand'),
                    lambda ps, ps_out, py, py_out, t: any('启动前备份失败' in l for l in ps_out) and any(l.startswith('  启动前备份：') for l in py_out))
        c.run('Invoke-LaunchBackup（两次）', st_saves, "Invoke-LaunchBackup ''; Invoke-LaunchBackup '联机'",
              lambda ctx: (backup.invoke_launch_backup(ctx, ''), backup.invoke_launch_backup(ctx, '联机')) and None)

        # ---- Invoke-OnceReset
        for n, s in [('没有记录', st_none), ('有 once.json', st_once), ('旧位置的 once + 同一秒的已有', st_once_legacy)]:
            c.run('Invoke-OnceReset（%s）' % n, s, 'Invoke-OnceReset', lambda ctx: backup.invoke_once_reset(ctx))

        # ---- 不经过 PowerShell 的：import 时不整理旧文件（PowerShell 版 dot-source 时会）
        c.reset()
        st_legacy(c)
        import importlib
        harness.py_call(lambda ctx: importlib.reload(backup), c.env, root=root)
        check('import 时不搬旧文件', True, os.path.exists(os.path.join(c.er, 'DarkReforged_items_0.txt')))
        c.reset()
        # PowerShell 5.1 Sort-Object 的排序（.NET 4.0 的 DepthLimitedQuickSort）：修改时间一样的两份旧联机存档 + 一份新的、两份一样的
        desc = lambda p, q: -((p[1] > q[1]) - (p[1] < q[1]))           # noqa: E731
        check('_net_sort 相等的谁在前（三个）和 PowerShell 一样', ['z', 'x', 'y'], [n for n, _ in backup._net_sort([('x', 1), ('y', 1), ('z', 2)], desc)])
        check('_net_sort 相等的谁在前（两个）和 PowerShell 一样', ['y', 'x'], [n for n, _ in backup._net_sort([('x', 1), ('y', 1)], desc)])
        import random
        rnd = random.Random(1)
        for k in (0, 1, 2, 5, 16, 17, 40, 300):
            xs = [rnd.randint(0, 9) for _ in range(k)]
            check('_net_sort 排得对（%d 个）' % k, sorted(xs), backup._net_sort(xs, lambda p, q: (p > q) - (p < q)))

    bad = RESULTS.count(False)
    print('%d 项，%d 项不同' % (len(RESULTS), bad))
    sys.exit(1 if bad else 0)


def _py_multi(ctx):
    a = backup.new_rng_backup(ctx, '启动前', 'rand')
    b = backup.new_rng_backup(ctx, '启动前', '联机，coop')
    cc = backup.new_rng_backup(ctx, '恢复前')
    p = os.path.join(ctx.RngRecordDir, 'items_0.txt')
    with open(p, 'wb') as f:
        f.write(b'\xef\xbb\xbfchanged\r\n')                  # Set-Content -Encoding UTF8（带 BOM、CRLF）
    t = ns(28)
    os.utime(p, ns=(t, t))
    d = backup.new_rng_backup(ctx, '启动前')
    e = backup.new_rng_backup(ctx, '启动前')
    return [a, b, cc, d, e]


if __name__ == '__main__':
    main()
