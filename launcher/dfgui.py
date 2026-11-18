# -*- coding: utf-8 -*-
"""打开启动器窗口（以前是 gui.ps1）。用包里自带的 pythonw.exe 跑（没有黑框）：
  launcher\\python\\pythonw.exe -I launcher\\dfgui.py
界面在 dfl\\gui\\app.py；后台步骤（启动游戏、重随敌人……）照样交给 launcher\\df.py 子进程。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)            # 自带的 Python 有 ._pth，不会自己把脚本所在的文件夹加进来

# pythonw 没有控制台：sys.stdout / sys.stderr 是 None，print 和 traceback 会出错。输出扔掉，出错的堆栈记进 logs\gui_trace.txt
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    try:
        os.makedirs(os.path.join(HERE, 'logs'), exist_ok=True)
        sys.stderr = open(os.path.join(HERE, 'logs', 'gui_trace.txt'), 'w', encoding='utf-8', buffering=1)
    except OSError:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')

from dfl.gui import app  # noqa: E402

if __name__ == '__main__':
    sys.exit(app.main())
