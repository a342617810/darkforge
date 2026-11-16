# -*- coding: utf-8 -*-
"""Dark Reforged 重随的各个步骤（由 reroll.py 按顺序调用），基础是原版（或随机器输出）的 regulation。

  common     公共导入、常量、上下文 Ctx（分档、掉落表链、给游戏脚本覆盖包的 features）
  enemies    敌人分档、血量按地区、Boss 战随从不掉东西；粪金龟血量统一
  stage3     敌人随机后按新位置修正（复制敌人参数、修补地图）
  bosses     Boss 龙心脏 + 星光碎片、保底锻造石
  world      随处传送、开局召魂铃、不受坠落伤害
  tweaks     赐福记忆不丢卢恩、双子老妪卖卢恩弯弧、战技固定伤害倍数
  ashes      骨灰获取处一次性打乱（once 记录）
  difficulty 局内难度：每档一个玩家特殊效果
  festive    庆典油脂：卢恩越多伤害越高
  dummy      训练木桩的敌人参数
  atkfwd     被命中标记顶掉的命中时触发（油脂等）：补挂用的副本
  unseen     词条无形：箭、法术、道具的子弹清单（dark_core 戴着时让 AI 不反应）
RNG Lands 时期的模块（装备重组、配方、商店重抽…）在 dev\\legacy_rnglands\\reroll，只留作参考。
"""
