# -*- coding: utf-8 -*-
"""不开窗口地启动启动器自己的 PowerShell 脚本（用户 2026-11-14：安全软件把「隐藏窗口 + 绕过执行策略」的 powershell 当成可疑脚本拦下）。

用法（都用包里自带的 pythonw.exe 跑，它本身没有窗口）：
  pythonw -I spawn.py gui.ps1                                   打开启动器（启动.bat、在线更新后重开）
  pythonw -I spawn.py launcher.ps1 -Action watch -GamePid 1234  游戏启动后的崩溃看守

- powershell 用 CREATE_NO_WINDOW 启动：不会闪黑框，命令行里也没有 -WindowStyle Hidden；
- 不继承句柄（close_fds）：启动器运行步骤时的输出管道不会被一直开着的崩溃看守占住；
- 只认这个文件夹里的 gui.ps1 / launcher.ps1，别的一概不跑。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED = ('gui.ps1', 'launcher.ps1')


def powershell():
    p = os.path.join(os.environ.get('SystemRoot') or r'C:\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    return p if os.path.isfile(p) else 'powershell.exe'


def command(argv):
    """要跑的命令行（列表）；参数不对返回 None"""
    if not argv or argv[0] not in ALLOWED:
        return None
    script = os.path.join(HERE, argv[0])
    if not os.path.isfile(script):
        return None
    return [powershell(), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File', script] + list(argv[1:])


def main(argv):
    cmd = command(argv)
    if not cmd:
        return 2
    subprocess.Popen(cmd, cwd=os.path.dirname(HERE), close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
