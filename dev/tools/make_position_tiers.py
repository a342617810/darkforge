# -*- coding: utf-8 -*-
"""合成 launcher\\reroll\\data\\position_tiers.json：每个敌人位置的强度等级（随机器 spoiler 日志里 "scaling a->b" 的 b），
给 enemypreset.py 按地区控制精英比例用。

等级只和位置有关、和放了什么无关（2026-11-02 核对 37 份日志，同一位置没有两个值），但每份日志只列出这一次被换掉的位置，
覆盖的位置每次差约 2000 个。以前 enemypreset.py 读最近一次的日志，同一个种子生成的预设会跟着上一次的随机结果变，
联机随机码就对不上（dev\\coop\\联机计划.md 3.3）。所以把能找到的日志合成一张固定表随整合包发。

  python make_position_tiers.py [另外的 spoiler_logs 文件夹 ...]
默认读整合包 randomizer\\spoiler_logs；同一位置出现两个不同的等级就报错不写。"""
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'launcher', 'reroll', 'data', 'position_tiers.json')


def main():
    dirs = [os.path.join(ROOT, 'randomizer', 'spoiler_logs')] + sys.argv[1:]
    tiers, seen, n_logs = {}, {}, 0
    for d in dirs:
        for lp in sorted(glob.glob(os.path.join(d, '*_log_*.txt'))):
            t = open(lp, encoding='utf-8', errors='replace').read()
            if 'Basic placements' not in t:
                continue
            n_logs += 1
            for m in re.finditer(r'^Replacing .*?\(#(\d+)\) in .*?\(scaling \d+->(\d+)\)', t, re.M):
                e, b = int(m.group(1)), int(m.group(2))
                if tiers.setdefault(e, b) != b:
                    sys.exit('位置 %d 的等级不一致：%d（%s）和 %d（%s）' % (e, tiers[e], seen[e], b, os.path.basename(lp)))
                seen.setdefault(e, os.path.basename(lp))
    if not tiers:
        sys.exit('没找到带敌人放置的 spoiler 日志')
    out = {'_说明': '每个敌人位置的强度等级（随机器日志 scaling a->b 的 b），dev\\tools\\make_position_tiers.py 从 %d 份 spoiler 日志合成' % n_logs,
           'tiers': {str(e): tiers[e] for e in sorted(tiers)}}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print('%d 份日志，%d 个位置 → %s' % (n_logs, len(tiers), OUT))


if __name__ == '__main__':
    main()
