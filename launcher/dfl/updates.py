# -*- coding: utf-8 -*-
"""离线 / 在线更新（launcher.ps1 的 Invoke-Update / Invoke-UpdatePy）：都交给 launcher\\update.py，输出逐行转出来"""
import os

from .core import write_err
from .pytool import find_python, run_stream


def invoke_update(ctx, Zips):
    """导入离线更新包：几个包用 | 隔开"""
    a = []
    for z in (Zips or '').split('|'):
        if z.strip():
            a += ['--zip', z.strip()]
    if not a:
        write_err('没有选更新包')
        return False
    return invoke_update_py(ctx, a)


def invoke_update_py(ctx, Extra):
    """在线检查（--check）/ 下载并应用（--fetch）/ 离线（--zip …）"""
    py = find_python(ctx)
    if not py:
        write_err('找不到 Python（整合包里的 launcher\\python 不见了？），没法更新')
        return False
    a = ['-X', 'utf8', os.path.join(ctx.LauncherDir, 'update.py'), '--root', os.path.dirname(ctx.LauncherDir)] + list(Extra)
    if os.environ.get('DARKFORGE_UPDATE_MANIFEST'):
        a += ['--manifest', os.environ['DARKFORGE_UPDATE_MANIFEST']]       # 测试用（本机模拟服务器）
    return run_stream(py, a) == 0
