# -*- coding: utf-8 -*-
"""合成 launcher\\reroll\\data\\vanilla_enemies.json：不开敌人随机时 Boss 定档、入侵 NPC 加血、普通敌人按位置算血量要的原版敌人数据，
用随机器自带的 diste 算（rr/stage3.py 的 vanilla_parts / hostile_npcs / next_phases）。正式发布不带随机器，没装随机器时重随读这份。
  - parts：原版地图上的敌人 {地图文件: [[实体, 敌人参数]]}（来自 diste\\Vanilla\\*.msb.dcx）；
  - hostile：入侵的 NPC 的实体编号（随机器 enemy.txt 的 Class: HostileNPC）；
  - next_phase：多阶段 Boss [[实体, 下一阶段]]（enemy.txt 的 NextPhase）。
游戏更新改了地图、或者换了随机器版本时重新跑一次：python make_vanilla_enemies.py"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RR = os.path.join(ROOT, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402
from rr import stage3  # noqa: E402

RD = os.path.join(ROOT, 'randomizer')


def main():
    erlib.DLL_DIRS[:] = [RD]
    if not os.path.isfile(os.path.join(RD, 'diste', 'Base', 'enemy.txt')):
        sys.exit('要随机器的 randomizer\\diste（只在开发时用）')
    stage3.SHIPPED = os.path.join(RR, 'data', '__none__.json')     # 只从随机器算，不读旧的那份
    parts = stage3.vanilla_parts(RD, os.path.join(RR, 'cache'))
    out = {'_说明': '原版敌人数据（dev\\tools\\make_vanilla_enemies.py 用随机器 v0.12.2 的 diste 算的）：parts 原版地图上的敌人 {地图: [[实体, 敌人参数]]}，'
                   'hostile 入侵 NPC 的实体，next_phase 多阶段 Boss [[实体, 下一阶段]]。没装随机器时 rr/stage3.py 读这份',
           'parts': parts, 'hostile': sorted(stage3.hostile_npcs(RD)), 'next_phase': sorted(stage3.next_phases(RD))}
    p = os.path.join(RR, 'data', 'vanilla_enemies.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print('%d 张地图、%d 个敌人位置，入侵 NPC %d 个，多阶段 Boss %d 对 → %s' % (
        len(parts), sum(len(v) for v in parts.values()), len(out['hostile']), len(out['next_phase']), p))


if __name__ == '__main__':
    main()
