# -*- coding: utf-8 -*-
"""暗黑重铸启动器（Python 版，从 launcher\\*.ps1 迁移过来；用户 2026-11-18：杀毒软件把 PowerShell 脚本当后门报，「直接整体迁移」）。
方案和进度：dev\\launcher_py\\迁移方案.md；移植约定（PowerShell 函数 → 哪个模块、怎么对照测试）：dev\\launcher_py\\移植约定.md。
入口：launcher\\df.py（命令行，动作名和以前 launcher.ps1 -Action 一样）。"""
