# -*- coding: utf-8 -*-
"""UIA 槽位的实测：桌面根元素的名字、顶层窗口（按进程号找）、窗口里的按钮。只读，不点任何东西。
用法：uia_probe.py [进程名，默认 explorer]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'launcher'))
from dfl import uia, win  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else 'explorer'
a = uia.Automation()
root = a.root()
print('根元素：', repr(root.name), '进程', root.process_id)
pids = win.find_pids(name)
print(name, '进程：', pids[:5])
for pid in pids[:3]:
    ws = root.find_all(uia.TreeScope_Children, a.process_cond(pid))
    print('  进程 %d 的顶层窗口 %d 个：%s' % (pid, len(ws), [w.name for w in ws][:5]))
    for w in ws[:2]:
        bs = w.find_all(uia.TreeScope_Descendants, a.control_type_cond('Button'))
        print('    「%s」里的按钮 %d 个：%s' % (w.name, len(bs), [b.name for b in bs][:8]))
        f = w.find_first(uia.TreeScope_Descendants, a.control_type_cond('Button'))
        print('    第一个按钮：', f.name if f else None)
