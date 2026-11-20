# -*- coding: utf-8 -*-
"""联机核对码（dfl\coop.py 的 get_coop_fingerprint 调，dev\\coop\\联机计划.md 1.5）：两人各自看一下，一样就说明游戏数据一样。
  --rand <randomizer 文件夹>   敌人随机的结果：regulation 的指纹 - 地图个数 - 事件个数
  --reroll <out\\reroll>        这次启动生成的重随包：regulation 的指纹
指纹 = 解密、解压后的 regulation 内容的 SHA-256 前 12 位（加密时的随机初始向量不影响）。几项之间用 / 隔开，一行输出。
联机启动时 dfl\\coop.py 再在后面接一项「m + 自己加的 mod 的名字和文件清单」（get_player_mod_list；没加 mod 就没有这一项）。
  python coopfp.py [--rand <dir>] [--reroll <dir>] [--dll-dir <找解压 DLL 的文件夹> ...]"""
import argparse
import glob
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erlib  # noqa: E402


def reg_fp(d):
    return hashlib.sha256(erlib.read_regulation(os.path.join(d, 'regulation.bin'))).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rand', default='')
    ap.add_argument('--reroll', default='')
    ap.add_argument('--dll-dir', action='append', default=[])
    a = ap.parse_args()
    erlib.DLL_DIRS = [d for d in a.dll_dir if d] or [d for d in (a.rand, a.reroll) if d]
    parts = []
    if a.rand:
        n_map = len(glob.glob(os.path.join(a.rand, 'map', 'mapstudio', '*.msb.dcx')))
        n_ev = len(glob.glob(os.path.join(a.rand, 'event', '*.emevd.dcx')))
        parts.append('%s-%d-%d' % (reg_fp(a.rand), n_map, n_ev))
    if a.reroll:
        parts.append(reg_fp(a.reroll))
    print(' / '.join(parts))


if __name__ == '__main__':
    main()
