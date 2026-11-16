# -*- coding: utf-8 -*-
"""各步骤共用的导入、常量和小工具。步骤模块用 `from .common import *`。"""
import glob
import json
import math
import os
import random
import re
import struct
import time
from collections import Counter, defaultdict

import erlib
import paramdef_min as pdm

__all__ = ['glob', 'json', 'math', 'os', 'random', 're', 'struct', 'time', 'Counter', 'defaultdict', 'erlib', 'pdm',
           'HERE', 'RAR', 'RAR_ZH', 'CAT_W', 'CAT_P', 'CAT_A', 'CAT_ZH', 'SMITHING_STONES', 'log', 'elite_families', 'Ctx', 'tal_weight']

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # launcher\reroll

RAR = ('Common', 'Rare', 'Epic', 'Legendary')


def tal_weight(f, r):
    """词条族在稀有度 r 的护符权重（词条库按稀有度的 weight_r；旧词条库只有一个 weight）"""
    wr = f.get('weight_r', {}).get('talisman')
    return wr[RAR.index(r)] if wr else f.get('weight', {}).get('talisman', 0)
RAR_ZH = {'Common': '普通', 'Rare': '稀有', 'Epic': '史诗', 'Legendary': '传说'}
CAT_W, CAT_P, CAT_A = 2, 3, 4            # 掉落表的物品类别：武器、防具、护符（道具是 1）
CAT_ZH = {CAT_W: '武器', CAT_P: '防具', CAT_A: '护符'}
# 锻造石【1-8】、古龙岩锻造石、失色锻造石【1-9】、古龙岩失色锻造石（道具编号）
SMITHING_STONES = set(range(10100, 10108)) | {10140} | set(range(10160, 10169)) | {10200}


def log(msg):
    print(msg, flush=True)


def elite_families(data_dir):
    """精英敌人的族（敌人参数编号 // 10000）：data\\elite_families.json（本体）+ data\\elite_dlc.json（DLC，键不以 _ 开头的各组）"""
    fams = set(json.load(open(os.path.join(data_dir, 'elite_families.json'), encoding='utf-8'))['families'])
    try:
        ed = json.load(open(os.path.join(data_dir, 'elite_dlc.json'), encoding='utf-8'))
        fams |= {int(f) for k, v in ed.items() if not k.startswith('_') and isinstance(v, dict) for f in v}
    except Exception:
        pass
    return fams


class Ctx:
    """一次重随的全部共享状态。主流程（reroll.py）先填好基础字段，各步骤读写它。

    a 命令行参数；S 设置；rng 随机数；bnd 解开的 regulation；P_en / P_mp 敌人 / 地图掉落表；report 报告行；
    msg_out 重随包的文字包目录；features 给游戏脚本覆盖包（scripts.py）看的「这次建了什么」，写成 features.json；
    ent_npc_final 敌人随机时每个位置最终引用的敌人参数（stage3 填）；item_rand 随机器开了物品随机（reroll.load 填）。"""

    def __init__(self, **kw):
        self.report = []
        self.features = {}
        self.ent_npc_final = {}
        self.item_rand = False
        self.__dict__.update(kw)

    # ---- 难度分档（settings.json 的 tier_bands）
    @property
    def bands(self):
        return self.S.get('tier_bands', [])

    def band_idx(self, tier):
        bands = self.bands
        for k, b in enumerate(bands):
            if tier <= b['max_tier']:
                return k
        return len(bands) - 1

    def band_for(self, tier):
        bands = self.bands
        for b in bands:
            if tier <= b['max_tier']:
                return b
        return bands[-1]

    # ---- 地图掉落表的一条链（连续编号）
    def chain(self, start):
        out, r = [], start
        while r in self.P_mp.rows:
            out.append(r)
            r += 1
        return out
