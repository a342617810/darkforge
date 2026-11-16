# -*- coding: utf-8 -*-
"""生成特效文件（.fxr）用的本地小服务器：本机没有 node，@cccode/fxr 在 Claude 内置浏览器（或任何浏览器）里跑。
用法：python fxrlab.py，浏览器打开 http://127.0.0.1:8765/fxrlab.html?build=hunt_mark.js
  页面从 CDN 载入库、import 本目录的生成脚本、调用它的 build(库)，把得到的 f*.fxr PUT 回来，写进本目录
  （?out=debug 写进 debug\\，排查用的变体放那里，见 ..\\自制特效.md）。只收 f<9 位数字>.fxr，别的名字一律拒绝。
写完跑 ..\\make_sfx.py 打包（排查变体：make_sfx.py --debug）。"""
import http.server
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = re.compile(r'^f\d{9}\.fxr$')


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def do_PUT(self):
        parts = self.path.split('?')[0].strip('/').split('/')
        if parts[0] != 'out' or not NAME.match(parts[-1]) or len(parts) not in (2, 3) or (len(parts) == 3 and parts[1] != 'debug'):
            self.send_error(400, 'only /out/f#########.fxr or /out/debug/f#########.fxr')
            return
        folder = os.path.join(HERE, *parts[1:-1])
        os.makedirs(folder, exist_ok=True)
        data = self.rfile.read(int(self.headers['Content-Length']))
        open(os.path.join(folder, parts[-1]), 'wb').write(data)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


if __name__ == '__main__':
    print('http://127.0.0.1:8765/fxrlab.html?build=hunt_mark.js', flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1', 8765), H).serve_forever()
