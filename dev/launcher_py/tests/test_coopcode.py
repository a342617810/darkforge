# -*- coding: utf-8 -*-
"""coopcode.ps1 → dfl/coopcode.py 对照测试。
- 压缩：同一批输入两边压出来的码逐字一样（.NET DeflateStream = zlib 第 6 级）；
- 解压：两边对同一批码（含折行 / 空格 / 截断 / 坏码）结果一样；
- 互通：PowerShell 压的 Python 解得开，Python 压的 PowerShell 解得开（玩家之间版本不同也能用）。"""
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
from dfl import coopcode  # noqa: E402

RESULTS = []


def check(name, ps, py):
    RESULTS.append(harness.same(name, ps, py))


REAL_RAND = ('DR3|v=0.10.13|m=rand|pw=YWJjZGVmZ2g=|w=high|sc=allow_summons=1,boss_damage_scaling=100,boss_health_scaling=100,'
             'boss_posture_scaling=100,death_debuffs=1,enemy_damage_scaling=100,enemy_health_scaling=100,enemy_posture_scaling=100'
             '|em=1.5|bp=10|ps=123456789|nat=0.05=1,0.1|o=allmaps bossbgm changestats crashfix customenemy dlcblessing dlckeysilo '
             'earlylegacy editnames enemy item markareas mats norandom_health norandom_scadu phasehp raceloc_health raceloc_scadu scale '
             'spellshops weaponprogression bias:30 seed:1234567890 dlc v16')
REAL_PLAIN = 'DR3|v=0.10.13|m=plain|pw=MTIzNDU2|w=low|sc=allow_summons=1,death_debuffs=0'


def compress_inputs():
    rnd = random.Random(20261118)
    xs = [REAL_RAND, REAL_PLAIN, 'DR3|', 'DR3|' + '|'.join(coopcode.CoopCodeWords), 'DR3|norandom_upgradesnorandom',
          'DR3|pw=中文', 'DR3|a\tb', 'DR3|xK', 'DR3|xİ', 'DR3|xı', 'DR3|xſ', 'DR3|café', 'DR3|del\x7f',
          'DR2|123|0.5', 'dr3|v=1', '', ' DR3|v=1', 'DR3|~ !"#$%&\'()*+,-./:;<=>?@[\\]^_`{}',
          'DR3|' + 'x' * 40000]                                            # 很长：deflate 分好几块，也要逐字一样
    for _ in range(150):
        n = rnd.randint(0, 60)
        parts = [rnd.choice(coopcode.CoopCodeWords) if rnd.random() < 0.4 else ''.join(chr(rnd.randint(0x20, 0x7e)) for _ in range(rnd.randint(1, 8)))
                 for _ in range(n)]
        xs.append('DR3|' + ''.join(parts))
    big = ''.join(chr(rnd.randint(0x20, 0x7e)) for _ in range(70000))     # 不好压的长文本
    xs.append('DR3|' + big)
    return xs


def ps_list(fn, items, env, tmp):
    """PowerShell 里对每个输入调一次 fn，结果按顺序放进数组（输入经 JSON 文件传，免得转义出问题）"""
    p = os.path.join(tmp, 'in_%s.json' % fn)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)
    snippet = ("$in = Get-Content -LiteralPath '%s' -Raw -Encoding UTF8 | ConvertFrom-Json\n"
               "$__r = @(foreach ($x in $in) { [string](%s ([string]$x)) })\n") % (p.replace("'", "''"), fn)
    r, _ = harness.ps_call(snippet, env)
    return r


def main():
    with tempfile.TemporaryDirectory() as tmp:
        env = harness.fake_env(tmp)
        xs = compress_inputs()

        # ---- 压缩：逐字一样
        ps_z = ps_list('Compress-CoopCode', xs, env, tmp)
        py_z, out = harness.py_call(lambda ctx: [coopcode.compress_coop_code(x) for x in xs], env)
        for i, x in enumerate(xs):
            check('compress #%d %s' % (i, json.dumps(x[:40], ensure_ascii=False)), ps_z[i], py_z[i])
        check('compress 没有输出', [], out)
        check('compress None 当空串', '', coopcode.compress_coop_code(None))
        z_real = py_z[0]
        print('   真码 %d 字 → %d 字' % (len(REAL_RAND), len(z_real)))

        # ---- 解压的输入：两边压出来的、加空白的、截断的、坏的
        ys = list(ps_z) + list(py_z)
        ys += [z_real[:40] + '\r\n' + z_real[40:80] + '  ' + z_real[80:], ' \t' + z_real + '\n', z_real[:30] + '　' + z_real[30:],
               z_real[:30] + ' ' + z_real[30:], z_real[:30] + '\x1c' + z_real[30:], z_real[:30] + '​' + z_real[30:],
               'DR4y' + z_real[4:], 'DR4', 'DR4z', 'DR4z!!!!', 'DR4zQ', 'DR4zQQ', 'DR4zQQ==A', z_real + '=', z_real + 'AAAA',
               'hello', ' DR3|v=1 ', '', 'dr4z' + z_real[4:], z_real.replace('-', '+'), z_real[:4] + z_real[4:].lower()]
        ys += [z_real[:n] for n in range(4, len(z_real))]                     # 每个截断长度（没复制完整）
        # 解出来的字节超出词表 / 不是 DR3| 开头
        import base64
        import zlib

        def raw_code(b):
            c = zlib.compressobj(6, zlib.DEFLATED, -15)
            return 'DR4z' + base64.urlsafe_b64encode(c.compress(b) + c.flush()).decode().rstrip('=')
        ys += [raw_code(b'DR3|\xff'), raw_code(b'DR3|' + bytes([0x80 + len(coopcode.CoopCodeWords)])), raw_code(b'XX3|v=1'),
               raw_code(b'\x80|v=1'), raw_code(b''), raw_code('DR3|中'.encode('utf-8'))]
        ps_x = ps_list('Expand-CoopCode', ys, env, tmp)
        py_x, out = harness.py_call(lambda ctx: [coopcode.expand_coop_code(y) for y in ys], env)
        for i, y in enumerate(ys):
            check('expand #%d %s' % (i, json.dumps(y[:40], ensure_ascii=False)), ps_x[i], py_x[i])
        check('expand 没有输出', [], out)
        check('expand None 当空串', '', coopcode.expand_coop_code(None))

        # ---- 互通：各自压的、对方解（只看 DR3 的输入：别的照原样返回）
        # 开尔文符号 K、带点的 İ 在 PowerShell 版里本来就会变成 ? / I（见 coopcode._LOWER_ASCII），两边一样地「有损」
        n = len(xs)
        for i, x in enumerate(xs):
            if py_z[i].startswith('DR4z'):
                want = x.replace('K', '?').replace('İ', 'I')
                check('Python 压 → PowerShell 解 #%d' % i, want, ps_x[n + i])
                check('PowerShell 压 → Python 解 #%d' % i, want, py_x[i])
        check('真码解开就是原文', REAL_RAND, coopcode.expand_coop_code(coopcode.compress_coop_code(REAL_RAND)))

    bad = RESULTS.count(False)
    print('%d 项，%d 项不同' % (len(RESULTS), bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
