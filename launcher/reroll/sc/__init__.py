# -*- coding: utf-8 -*-
"""游戏脚本覆盖包（out\\scripts，YAFSML 最后加载）：赐福对话脚本、菜单文字、公共事件、玩家 / 灵马脚本、商人对话、圆桌地图。
入口是 launcher\\reroll\\scripts.py；每个功能一个模块，按需要提供这几个函数（builder 按 FEATURES 的顺序逐个调用）：
  esd(cx, groups)        改赐福对话脚本 t000001000 的状态机（cx.root = 「更多选项」状态机）
  texts(cx, key)         菜单文字：{FMG 名字结尾: {文字编号: 文字}}（key = 'en' / 'zh'）
  restyle(cx, key, add, base)  各功能的文字合好之后再改（add 同上、合在一起；base(编号) = 包里原有的对话文字），赐福菜单美化用
  events(cx, e, ev0)     改公共事件脚本 common.emevd（e = emevd.read 的结果，ev0 = 事件 0）
  files(cx, tmp)         写别的文件到覆盖包目录 tmp
  sources(cx)            会影响结果的额外输入文件（算「来源没变就不重写」的签名）
  note(cx)               启动日志里的一句（没做成的才写）
功能开关在 settings.json；要靠重随包里的参数的（难度效果、木桩、开局物品的掉落表…）看重随写的 features.json（cx.feat）。"""
