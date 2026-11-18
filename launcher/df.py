# -*- coding: utf-8 -*-
"""暗黑重铸启动器的命令行入口（代替 launcher.ps1）：python launcher\\df.py <动作> [参数]；不带参数看用法。
包里的 Python 不会自动把脚本所在的文件夹加进搜索路径（python312._pth），这里自己加。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 用 pythonw 跑（崩溃看守）时没有控制台：sys.stdout / sys.stderr 是 None，输出扔掉
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

from dfl.cli import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
