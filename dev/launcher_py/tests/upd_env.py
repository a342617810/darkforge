# -*- coding: utf-8 -*-
"""第 5 步：验证「旧的 PowerShell 启动器在线更新到 Python 启动器，再自动重开」。

  upd_env.py <测试文件夹> <旧版本 launcher 的快照文件夹> [端口]

旧包 = 快照（git 里 v0.10.13 提交的 launcher + 启动.bat），新包 = 现在的工作区；都只取 launcher（不含 python / dotnet / webview2 / reroll / logs）
和 启动.bat，按 make_package 的排除规则过滤，新包的版本号写成 0.10.99。用 make_delta 比出真的更新包，
<测试文件夹>\\serve 里放更新包和 latest.json（本机 http://127.0.0.1:<端口>/），<测试文件夹>\\root 是装着旧版本的整合包副本
（python / webview2 用目录联接，reroll 只放界面要读的几个文件），appdata / local 是假的。
打印 JSON：{root, appdata, local, manifest}"""
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import zipfile
import _winapi

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, os.path.join(PALY, 'dev', 'tools'))
import make_delta  # noqa: E402
import make_package  # noqa: E402

SKIP = ('launcher/python/', 'launcher/dotnet/', 'launcher/webview2/', 'launcher/reroll/', 'launcher/logs/')
NEW_VER = '0.10.99'


def pick(src):
    """src 下要进包的文件 [(完整路径, 相对路径)]"""
    out = []
    for d, dirs, fs in os.walk(src):
        dirs[:] = sorted(x for x in dirs if x != '__pycache__')
        for n in sorted(fs):
            full = os.path.join(d, n)
            rel = os.path.relpath(full, src).replace(os.sep, '/')
            if not (rel.startswith('launcher/') or rel == '启动.bat') or rel.startswith(SKIP):
                continue
            if rel in make_package.KEEP or not any(fnmatch.fnmatch(rel, p) for p in make_package.EXCL):
                out.append((full, rel))
    return out


def make_zip(src, out, version=None):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for full, rel in pick(src):
            if rel == 'launcher/version.txt' and version:
                z.writestr('darkforge/' + rel, version + '\r\n')
            else:
                z.write(full, 'darkforge/' + rel)


def main(t, old_src, port):
    t = os.path.abspath(t)
    if os.path.exists(t):
        for n in ('python', 'webview2'):
            j = os.path.join(t, 'root', 'launcher', n)
            if os.path.isjunction(j):
                os.rmdir(j)
        shutil.rmtree(t)
    serve, root = os.path.join(t, 'serve'), os.path.join(t, 'root')
    os.makedirs(serve)
    old_zip, new_zip = os.path.join(t, 'old.zip'), os.path.join(t, 'new.zip')
    make_zip(old_src, old_zip)
    make_zip(PALY, new_zip, NEW_VER)
    delta = os.path.join(serve, 'Darkforge_v0.10.13_to_v%s_update.zip' % NEW_VER)
    make_delta.build(old_zip, new_zip, delta)
    data = open(delta, 'rb').read()
    man = {'format': 1, 'name': 'Darkforge', 'latest': NEW_VER, 'date': '2026-11-18', 'notes': '测试：启动器换成 Python',
           'updates': [{'from': '0.10.13', 'to': NEW_VER, 'date': '2026-11-18', 'notes': '测试：启动器换成 Python',
                        'file': os.path.basename(delta), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        'url': 'http://127.0.0.1:%d/%s' % (port, os.path.basename(delta))}]}
    with open(os.path.join(serve, 'latest.json'), 'w', encoding='utf-8') as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    # 装着旧版本的整合包副本
    with zipfile.ZipFile(old_zip) as z:
        for i in z.infolist():
            if i.is_dir():
                continue
            p = os.path.join(root, *i.filename[len('darkforge/'):].split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(z.read(i))
    L = os.path.join(PALY, 'launcher')
    for n in ('python', 'webview2'):
        _winapi.CreateJunction(os.path.join(L, n), os.path.join(root, 'launcher', n))
    for n in ('settings.json', 'erlib.py', 'savediff.py', 'state'):
        s, d = os.path.join(L, 'reroll', n), os.path.join(root, 'launcher', 'reroll', n)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
    shutil.copy2(os.path.join(L, 'game_path.txt'), os.path.join(root, 'launcher', 'game_path.txt'))
    for n in ('dll', 'yafsml', 'randomizer'):
        os.makedirs(os.path.join(root, n), exist_ok=True)
    env = {'root': root, 'appdata': os.path.join(t, 'appdata'), 'local': os.path.join(t, 'local'),
           'manifest': 'http://127.0.0.1:%d/latest.json' % port, 'delta': delta}
    for k in ('appdata', 'local'):
        os.makedirs(env[k])
    m = json.load(zipfile.ZipFile(delta).open('update.json'))
    env['delta_files'] = len(m['files'])
    env['delta_delete'] = [x['path'] for x in m.get('delete', [])]
    print(json.dumps(env, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8765)
