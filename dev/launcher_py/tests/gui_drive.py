# -*- coding: utf-8 -*-
"""开 Python 版的启动器窗口（在 gui_env.py 搭的副本上），按步骤点页面、截图，记下宿主和页面之间的消息。要在普通终端里跑（WebView2 在沙箱里起不来）。

  gui_drive.py <root> <appdata> <local> <输出文件夹> <步骤.json>

步骤.json：[{"note": 说明, "js": 页面里执行的脚本, "wait": 执行后等多少毫秒, "shot": 截图文件名}, ...]，按顺序做，做完关窗口。
js 里可以用 clickBtn(文字) 点页面上文字对得上的按钮（弹窗最上面那层优先）、dlgAnswer(第几个按钮)、post(action, 参数)。
结果写进 <输出文件夹>\\drive.json：页面发来的消息、宿主发出的消息（状态只记 busy / cards / run）、每步时的状态。"""
import json
import os
import sys
import threading
import time

root, appdata, local, outdir, steps_file = sys.argv[1:6]
os.environ['APPDATA'] = appdata
os.environ['LOCALAPPDATA'] = local
for k in ('DARKFORGE_WEBUI_SHOT', 'DARKFORGE_ROOT'):
    os.environ.pop(k, None)
# 副本里的 Python 代码换成现在的（副本是先搭好的，之后改的代码要同步过去）
import shutil  # noqa: E402
REAL_L = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'launcher'))
shutil.copytree(os.path.join(REAL_L, 'dfl'), os.path.join(root, 'launcher', 'dfl'), dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
for _n in ('df.py', 'dfgui.py'):
    shutil.copy2(os.path.join(REAL_L, _n), os.path.join(root, 'launcher', _n))
sys.path.insert(0, os.path.join(root, 'launcher'))
from dfl.gui import app as A  # noqa: E402

with open(steps_file, encoding='utf-8') as f:
    STEPS = json.load(f)
os.makedirs(outdir, exist_ok=True)
LOG = []
T0 = time.time()
HELPERS = r"""
window.clickBtn = function (text) {
  var scopes = [];
  var d = document.querySelectorAll('.dlg-mask');
  if (d.length) scopes.push(d[d.length - 1]);
  scopes.push(document);
  for (var s = 0; s < scopes.length; s++) {
    var bs = scopes[s].querySelectorAll('button');
    for (var i = 0; i < bs.length; i++) {
      var t = (bs[i].innerText || '').replace(/\s+/g, '');
      if (t === text.replace(/\s+/g, '') || t.indexOf(text.replace(/\s+/g, '')) === 0) { bs[i].click(); return true; }
    }
  }
  return false;
};
window.dlgAnswer = function (i) {
  var d = document.querySelectorAll('.dlg-mask');
  if (!d.length) return false;
  var b = d[d.length - 1].querySelector('[data-b="' + i + '"]');
  if (b) b.click();
  return !!b;
};
window.post = function (a, p) { window.chrome.webview.postMessage(Object.assign({ action: a }, p || {})); };
"""


def stamp():
    return round(time.time() - T0, 2)


class Drive(A.App):
    def send(self, obj):
        LOG.append([stamp(), 'host', obj])
        super().send(obj)

    def on_message(self, text):
        try:
            LOG.append([stamp(), 'page', json.loads(text)])
        except ValueError:
            pass
        super().on_message(text)

    def handle(self, m):
        if m.get('action') == 'ready' and not getattr(self, '_driving', False):
            self._driving = True                    # 先排上步骤：ready 里打开时的检查可能弹窗一直等着
            self.win.invoke(self.next_step)
        super().handle(m)

    def next_step(self):
        i = getattr(self, '_step', 0)
        if i == 0:
            self.win.execute_script(HELPERS)
        if i >= len(STEPS):
            self.finish()
            return
        self._step = i + 1
        s = STEPS[i]
        LOG.append([stamp(), 'step', s.get('note', ''), s.get('js', '') or s.get('py', '')])
        if s.get('py'):                             # 在驱动这边执行的 Python（模拟后台进程要弹窗之类）；结果放进 R
            try:
                exec(s['py'], {'os': os, 'json': json, 'app': self, 'R': R, 'LOG': LOG, 'close_dialogs': close_dialogs})
            except Exception as e:
                LOG.append([stamp(), 'py-error', repr(e)])
        if s.get('js'):
            self.win.execute_script(s['js'])

        def after():
            self.win.kill_timer(t[0])
            st = self.build_state()
            LOG.append([stamp(), 'state', {k: st[k] for k in ('busy', 'cards', 'subs', 'run', 'hasHard', 'update')}])
            if s.get('shot'):
                self.win.capture_png(os.path.join(outdir, s['shot']), lambda ok: self.next_step())
            else:
                self.next_step()
        t = [self.win.set_timer(int(s.get('wait', 800)), after)]

    def start_run(self, title, steps, after=None):
        """GUI_DRIVE_FAKE_RUN=1：只记下要跑什么（测启动 / 重随前的那些问答，不真的启动游戏）"""
        if os.environ.get('GUI_DRIVE_FAKE_RUN'):
            LOG.append([stamp(), 'run', title, steps, bool(after)])
            self.log('=== ' + title + ' ===（测试：没有真的跑）')
            return
        super().start_run(title, steps, after)

    def finish(self):
        self.closing = True
        self.win.destroy()


R = {}


def close_dialogs():
    """把这个进程开着的系统对话框（文件夹 / 文件选择框，类名 #32770）都点「取消」；返回关了几个"""
    import ctypes
    from dfl import win as W
    n = 0
    for h in W.windows_of(os.getpid(), visible=True, top_owner=False):
        buf = ctypes.create_unicode_buffer(64)
        ctypes.windll.user32.GetClassNameW(ctypes.c_void_p(h), buf, 64)
        if buf.value == '#32770':
            R.setdefault('dialogs', []).append(W.window_text(h))
            ctypes.windll.user32.PostMessageW(ctypes.c_void_p(h), 0x0111, 2, 0)     # WM_COMMAND IDCANCEL
            n += 1
    return n
# 不真的开资源管理器 / 记事本 / 浏览器，记下要开什么
A._explorer = lambda p: LOG.append([stamp(), 'explorer', p])
A._notepad = lambda p: LOG.append([stamp(), 'notepad', p])
A._open_url = lambda u: LOG.append([stamp(), 'open_url', u])
app = Drive()


def guard():
    time.sleep(float(os.environ.get('GUI_DRIVE_TIMEOUT') or 180))
    LOG.append([stamp(), 'timeout'])
    app.closing = True
    if app.win:
        app.win.destroy()


threading.Thread(target=guard, daemon=True).start()
rc = 1
try:
    rc = app.run()
finally:
    LOG.append([stamp(), 'exit', rc, app.errors, R])
    with open(os.path.join(outdir, 'drive.json'), 'w', encoding='utf-8') as f:
        json.dump(LOG, f, ensure_ascii=False, indent=1, default=str)
