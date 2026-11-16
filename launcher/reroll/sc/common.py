# -*- coding: utf-8 -*-
"""各功能共用：路径、上下文、按加载顺序找文件、日志"""
import json
import os
import sys

REROLL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # launcher\reroll
PALY = os.path.dirname(os.path.dirname(REROLL))                         # 项目根目录
DATA = os.path.join(REROLL, 'data')
SETTINGS = os.path.join(REROLL, 'settings.json')
TALK = os.path.join('script', 'talk', 'm00_00_00_00.talkesdbnd.dcx')
COMMON_EVENT = os.path.join('event', 'common.emevd.dcx')
LANGS = (('engus', 'en'), ('zhocn', 'zh'))
FEATURES_FILE = 'features.json'                                       # 重随写的：这次 regulation 里建了什么（见 rr/common.py）


def log(s):
    print(s, file=sys.stderr)


def last_with(sources, rel):
    """按 YAFSML [mod] 的加载顺序，最后一个有这个文件的目录里的那份"""
    for d in reversed(sources):
        p = os.path.join(d, rel)
        if os.path.isfile(p):
            return p
    return None


def vanilla(rel):
    """原版文件（没有别的来源时用）：装了随机器用它带的 diste\\Vanilla，没装从游戏 Data0 取（launcher\\reroll\\vanilla.py）；拿不到返回 None"""
    import vanilla as vsrc
    return vsrc.path(rel)


class Ctx:
    """sources：YAFSML [mod] 的目录（按加载顺序）；S：settings.json；feat：重随写的 features.json（没有重随包时是 {}）；
    root：「更多选项」状态机（合并赐福菜单后填）；notes：启动日志里要写的句子"""

    def __init__(self, sources):
        self.sources = sources
        try:
            self.S = json.load(open(SETTINGS, encoding='utf-8'))
        except Exception:
            self.S = {}
        fp = last_with(sources, FEATURES_FILE)
        self.feat = json.load(open(fp, encoding='utf-8')) if fp else {}
        self.features_file = fp
        self.reroll = fp is not None
        self.common = last_with(sources, COMMON_EVENT) or vanilla(COMMON_EVENT)
        self.root = None
        self.notes = []
