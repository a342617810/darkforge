# -*- coding: utf-8 -*-
"""旧版本启动器（PowerShell 的，v0.10.13 以前）留下的入口：它们用包里的 pythonw.exe 跑这个文件来开窗口 / 开崩溃看守。
启动器换成 Python 以后（迁移第 5 步）这里只做转接，转到新的入口，不再启动 powershell：

  pythonw -I spawn.py gui.ps1                                   → pythonw -I dfgui.py（旧版本在线更新完重开启动器时这样调）
  pythonw -I spawn.py launcher.ps1 -Action watch -GamePid 1234  → pythonw -I df.py watch --game-pid 1234（更新前就开着的游戏的崩溃看守）

别的参数一概不跑。新启动器自己不用这个文件（直接跑 dfgui.py / df.py）。
- 不开窗口：pythonw 本身没有窗口；
- 不继承句柄（close_fds）：启动器运行步骤时的输出管道不会被一直开着的崩溃看守占住。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def pythonw():
    p = os.path.join(HERE, 'python', 'pythonw.exe')
    return p if os.path.isfile(p) else sys.executable


def command(argv):
    """要跑的命令行（列表）；参数不对返回 None"""
    if not argv:
        return None
    if argv[0] == 'gui.ps1' and len(argv) == 1:
        return [pythonw(), '-I', os.path.join(HERE, 'dfgui.py')]
    if argv[0] == 'launcher.ps1' and len(argv) == 5 and argv[1] == '-Action' and argv[2] == 'watch' and argv[3] == '-GamePid':
        try:
            pid = int(argv[4])
        except ValueError:
            return None
        return [pythonw(), '-I', os.path.join(HERE, 'df.py'), 'watch', '--game-pid', str(pid)]
    return None


def main(argv):
    cmd = command(argv)
    if not cmd or not os.path.isfile(cmd[2]):
        return 2
    subprocess.Popen(cmd, cwd=os.path.dirname(HERE), close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
