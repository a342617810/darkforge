# -*- coding: utf-8 -*-
"""恢复存档前算差别（用户 2026-11-06：玩家点「恢复存档」丢了一整次启动的进度，确认框只写「进度会丢失」，看不出丢多少）：
只读，比较现在的存档和一份备份里每个角色的等级、游戏时间。图形界面的恢复确认框调用（launcher\\gui.ps1 Get-RestoreDiffLines）。
用法：python savediff.py <备份目录> <存档根目录>；输出一行 JSON（字符串数组，ASCII 转义，PowerShell 不用管编码）；读不了退出码 1、不输出。
没变化的角色不列；一个角色都没变时输出一句「都一样」。"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erlib  # noqa: E402

SAVE_NAMES = ('ER0000.rng', 'ER0000.rng.co2')
MAX_LINES = 8
SUMMARY0, SUMMARY_SIZE, SECS_OFF = 0x195E, 0x24C, 0x26    # USER_DATA010 的角色摘要（同 erlib.save_profiles）：名字、等级之后是游戏时间（秒）


def chars(path):
    """{格号: (名字, 等级, 游戏时间秒)}"""
    raw = open(path, 'rb').read()
    e = erlib.Bnd4(raw).entries.get('USER_DATA010')
    if not e:
        return {}
    body = raw[e['off'] + 16:e['off'] + e['size']]
    return {k: (name, level, struct.unpack_from('<I', body, SUMMARY0 + k * SUMMARY_SIZE + SECS_OFF)[0])
            for k, (name, level) in erlib.save_profiles(path).items()}


def span(secs):
    h, m = secs // 3600, secs % 3600 // 60
    return '%d 小时 %d 分' % (h, m) if h else '%d 分' % m


def state(c):
    return 'Lv.%d、%s' % (c[1], span(c[2]))


def compare(cur, bak):
    """一个存档文件里变了的角色，一行一个（现在 → 恢复后）"""
    out = []
    for k in sorted(set(cur) | set(bak)):
        a, b = cur.get(k), bak.get(k)
        slot = '第 %d 格' % (k + 1)
        if a and not b:
            out.append('「%s」（%s）：恢复后没有这个角色（现在 %s）' % (a[0], slot, state(a)))
        elif b and not a:
            out.append('「%s」（%s）：恢复后多出这个角色（%s）' % (b[0], slot, state(b)))
        elif a[0] != b[0]:
            out.append('%s：现在是「%s」（%s），恢复后换成「%s」（%s）' % (slot, a[0], state(a), b[0], state(b)))
        elif a[1:] != b[1:]:
            d = b[2] - a[2]
            tail = '，少 %s' % span(-d) if d < 0 else '，多 %s' % span(d) if d > 0 else ''
            out.append('「%s」（%s）：现在 %s → 恢复后 %s%s' % (a[0], slot, state(a), state(b), tail))
    return out


def diff_lines(backup, root):
    pairs = []
    for d, _sub, files in os.walk(backup):
        for n in files:
            if n in SAVE_NAMES:
                pairs.append((os.path.basename(d), n, os.path.join(d, n)))
    found = []
    for acc, name, path in sorted(pairs):
        cur = os.path.join(root, acc, name)
        lines = compare(chars(cur) if os.path.isfile(cur) else {}, chars(path))
        if lines:
            found.append((acc, name, lines))
    accounts = {x[0] for x in found}
    out = []
    for acc, name, lines in found:
        tag = ('联机 · ' if name.endswith('.co2') else '') + ('账号尾号 %s · ' % acc[-4:] if len(accounts) > 1 else '')
        out += [tag + l for l in lines]
    if not out:
        return ['所有角色的等级和游戏时间都和现在一样。']
    if len(out) > MAX_LINES:
        return out[:MAX_LINES] + ['……还有 %d 个角色有变化' % (len(out) - MAX_LINES)]
    return out


if __name__ == '__main__':
    print(json.dumps(diff_lines(sys.argv[1], sys.argv[2])))
