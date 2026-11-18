# -*- coding: utf-8 -*-
"""窗口宿主的冒烟测试：打开真的启动器页面（launcher\\ui），记下页面发来的消息，回一份演示状态，截图，然后自己关掉。
不碰启动器的状态；WebView2 的用户数据放临时文件夹（不动真的 %LOCALAPPDATA%\\Darkforge\\WebView2）。要在普通终端里跑。
用法：webview_probe.py <截图 png> <结果 json>"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
L = os.path.abspath(os.path.join(HERE, '..', '..', '..', 'launcher'))
sys.path.insert(0, L)
from dfl.gui import webview  # noqa: E402

png, out = sys.argv[1], sys.argv[2]
log = []
webview.set_dpi_aware()
webview.set_app_id('Darkforge.Launcher.Test')
udf = tempfile.mkdtemp(prefix='dfwv_')
w = webview.WebViewWindow('暗黑重铸 启动器（测试）', os.path.join(L, 'webview2'), udf, 'darkforge.local', os.path.join(L, 'ui'),
                          'https://darkforge.local/index.html', icon_path=os.path.join(L, 'darkforge.ico'))
log.append(['runtime', webview.runtime_version(os.path.join(L, 'webview2'))])
STATE = {'type': 'state', 'version': '9.9.9', 'busy': False, 'hasHard': False, 'randomizerOk': True, 'mode': 'rand',
         'cards': {'path': {'value': 'E:\\测试\\ELDEN RING', 'accent': 'gold', 'tip': ''},
                   'rand': {'value': '2026-11-18 14:30', 'accent': 'ok', 'tip': ''},
                   'last': {'value': '还没启动过', 'accent': 'muted', 'tip': ''}},
         'subs': {'launchV': '无敌人随机', 'launchR': '敌人随机', 'randEnemy': '换一个新种子，不启动游戏', 'randItems': '骨灰、开局装备重抽，新角色生效'},
         'run': {'player': False, 'lines': ['Python 版宿主：页面收到了这份状态'], 'pct': None, 'error': False},
         'tools': [{'name': '游戏路径', 'tip': 'x'}], 'coop': False, 'update': None, 'enemyInfo': ''}


def on_message(text):
    m = json.loads(text)
    log.append(['page', m])
    if m.get('action') == 'ready':
        w.post_json(json.dumps(STATE, ensure_ascii=False))
        w.post_json(json.dumps({'type': 'toast', 'text': '来自 Python 宿主的提示'}, ensure_ascii=False))

        def shot():
            w.kill_timer(t[0])
            w.capture_png(png, lambda ok: (log.append(['capture', ok]), w.destroy()))
        t = [w.set_timer(2500, shot)]


w.on_message = on_message
w.on_navigated = lambda ok, st: log.append(['nav', ok, st])
w.on_failed = lambda why: (log.append(['failed', why]), w.destroy())
guard = []
w.run_started = None


def safety():
    log.append(['timeout'])
    w.destroy()


orig_create = w._create_window


def create_and_guard():
    orig_create()
    w.set_timer(30000, safety)


w._create_window = create_and_guard
w.run()
with open(out, 'w', encoding='utf-8') as f:
    json.dump(log, f, ensure_ascii=False, indent=1)
