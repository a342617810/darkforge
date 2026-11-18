# -*- coding: utf-8 -*-
"""后台进程（命令行动作、崩溃看守）要弹窗时（ui.ps1 的 Request-HostDialog / Show-DrDialog）：
图形界面开着就交给它显示在页面里——请求写进 $env:DARKFORGE_DLG_DIR\\<id>.req.json，等 <id>.ans.json（选了第几个）；
图形界面 5 秒内没接、或者已经关了，自己弹系统对话框。文件协议和以前一样，迁移期间旧的 PowerShell 图形界面也认得。

测试：环境变量 DARKFORGE_TEST_DIALOG = 「按顺序的回答」（逗号分开，如 "1,0"），不弹窗；DARKFORGE_TEST_DIALOG_LOG = 文件，
每次弹窗追加一行 JSON（标题、正文、按钮），对照测试比两边弹了什么。"""
import json
import os
import time

from . import win


def request_host_dialog(Text, Title, Buttons, Default, Cancel, Icon):
    """交给图形界面显示：返回选了第几个；图形界面没接 / 不在了返回 None"""
    d = os.environ.get('DARKFORGE_DLG_DIR')
    try:
        gp = int(os.environ.get('DARKFORGE_GUI_PID') or '')
    except ValueError:
        return None
    if not d or gp == os.getpid():
        return None
    try:
        if not win.pid_alive(gp):
            return None
        os.makedirs(d, exist_ok=True)
        rid = '%d_%d' % (os.getpid(), time.time_ns() // 100 + 621355968000000000)   # 和以前一样：进程号_Ticks
        req = os.path.join(d, rid + '.req.json')
        ans = os.path.join(d, rid + '.ans.json')
        j = json.dumps({'text': Text, 'title': Title, 'buttons': list(Buttons), 'def': Default, 'cancel': Cancel, 'icon': Icon},
                       ensure_ascii=False, separators=(',', ':'))
        with open(req + '.tmp', 'w', encoding='utf-8', newline='') as f:
            f.write(j)
        os.rename(req + '.tmp', req)
        t0 = time.time()
        while True:
            if os.path.isfile(ans):
                try:
                    with open(ans, encoding='utf-8-sig') as f:
                        s = f.read().strip()
                except OSError:
                    s = ''
                try:
                    os.remove(ans)
                except OSError:
                    pass
                try:
                    return int(s)
                except ValueError:
                    return None
            if not win.pid_alive(gp):
                try:
                    os.remove(req)
                except OSError:
                    pass
                return None
            if time.time() - t0 > 5 and os.path.isfile(req):
                try:
                    os.rename(req, req + '.x')        # 改名成功 = 图形界面还没接，收回来自己弹
                except OSError:
                    pass
                else:
                    try:
                        os.remove(req + '.x')
                    except OSError:
                        pass
                    return None
            time.sleep(0.15)
    except OSError:
        return None


def _test_answer(Text, Title, Buttons):
    spec = os.environ.get('DARKFORGE_TEST_DIALOG')
    if spec is None:
        return None
    logp = os.environ.get('DARKFORGE_TEST_DIALOG_LOG')
    if logp:
        with open(logp, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'title': Title, 'text': Text, 'buttons': list(Buttons)}, ensure_ascii=False) + '\n')
    answers = [x for x in spec.split(',') if x.strip()]
    if not answers:
        return 0
    a = int(answers[0])
    os.environ['DARKFORGE_TEST_DIALOG'] = ','.join(answers[1:]) if len(answers) > 1 else answers[0]   # 最后一个一直用
    return a


def show_dr_dialog(Text, Title='暗黑重铸', Buttons=('确定',), Default=0, Cancel=-1, Icon='info'):
    """统一的弹窗：返回点了第几个按钮（0 起）；关掉窗口没选返回 Cancel。
    后台进程用：先交给图形界面，没接就弹系统对话框（一个按钮 = 确定；两个 = 是 / 否；三个 = 是 / 否 / 取消，按钮文字写进正文里）"""
    Buttons = list(Buttons)
    t = _test_answer(Text, Title, Buttons)
    if t is not None:
        return t
    r = request_host_dialog(Text, Title, Buttons, Default, Cancel, Icon)
    if r is not None:
        return r
    icon = win.MB_ICONS.get(Icon, 0x40)
    if len(Buttons) <= 1:
        win.message_box(Text, Title, icon)
        return 0
    hint = '\r\n\r\n' + '　'.join('「%s」= %s' % (b, k) for b, k in zip(Buttons, ('是', '否', '取消')))
    if len(Buttons) == 2:
        r = win.message_box(Text + hint, Title, icon | 0x4 | (0x100 if Default == 1 else 0))     # MB_YESNO
        return 0 if r == 6 else 1
    r = win.message_box(Text + hint, Title, icon | 0x3 | (0x100 * min(Default, 2)))              # MB_YESNOCANCEL
    return {6: 0, 7: 1, 2: 2}.get(r, Cancel)
