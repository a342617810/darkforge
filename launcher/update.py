# -*- coding: utf-8 -*-
"""离线增量更新（用户 2026-11-10「先做离线增量包」）：把 dev\\tools\\make_delta.py 做的更新包应用到整合包目录。

用法（启动器「导入更新包」→ launcher.ps1 -Action update 调用）：
  python update.py --root <整合包目录> --zip <更新包.zip> [--zip <下一个.zip> ...] [--dry]
几个更新包按「从哪个版本到哪个版本」自动排好顺序，一个接一个应用（比如 0.10.0→0.10.1、0.10.1→0.10.2）。

更新包（zip 根目录）：
  update.json   {"format": 1, "name": "Darkforge", "from": 版本, "to": 版本,
                 "files": [{"path", "sha256", "size", "old_sha256"}],   # 新增 / 改了的文件；old_sha256 = 旧版本里这个文件（没有是 null）
                 "delete": [{"path", "old_sha256"}],                    # 新版本里没有了的文件
                 "merge_json": [路径]}                                  # 玩家能改的 JSON（settings.json）：按键合并，不整个覆盖
  files/<路径>  新版本的文件
  base/<路径>   merge_json 里的文件在旧版本的样子（判断玩家改过哪些键）

做法：核对版本 → 游戏没在运行 → 逐个文件核对 SHA-256 → 先把要改 / 要删的文件备份到「更新备份\\<旧>_到_<新>_<时间>」→
写临时文件再整体替换（version.txt 最后写）→ 任何一步失败就按备份全部还原。
玩家改过的文件（和旧版本不一样）：JSON 按键合并（玩家改过的键保留，其余用新版本的）；别的文件照样换成新版本，原来的留在备份里并列出来。
不能换 launcher\\python（更新程序自己在用），这种更新只能下完整包。
输出：给玩家看的行以「§ 」开头，出错的行带「[错误]」；结果写 launcher\\logs\\update_result.txt（ok <版本> / latest / full / fail）和 update_ops.txt（追加）

在线更新（用户 2026-11-11「通过 gitee 实现自动更新」）：
  python update.py --root <整合包目录> --check          只检查，结果写 launcher\\logs\\update_check.json
  python update.py --root <整合包目录> --fetch [--dry]  检查 → 下载要用的更新包（launcher\\updates，断点续传、核对 SHA-256）→ 按上面的做法应用
  --manifest <网址>  测试用：换掉 launcher\\update_source.json 里的清单地址
来源（用户 2026-11-11「两边一起试」）：update_source.json 的 sources 里有 Gitee（国内快）和 GitHub（国外快），
检查时同时读两边的清单，先读到的那边说了算（另一边在 RACE_GRACE 秒内也读到、而且版本更新的话用版本新的）；
下载先用选中那边的地址，下不了换另一边同一个文件（SHA-256 一样）的地址，没下完的部分接着用。
版本清单 latest.json（dev\\tools\\publish_update.py 发布到 Gitee 和 GitHub）：
  {"format": 1, "name": "Darkforge", "latest": 版本, "date": 日期, "notes": 最新版本的更新内容,
   "full": {"version", "url", "note"},                                          # 完整整合包的下载页（更新包接不上时打开它）
   "updates": [{"from", "to", "date", "notes", "file", "size", "sha256", "url"}]}  # 新的在前，只留最近几个
从现在的版本到 latest 找一条更新包最少（一样多时下载量最小）的链；找不到就提示下载完整整合包。
下载地址只认 update_source.json 的 hosts 里的网站（https；本机 127.0.0.1 测试时可以 http）。"""
import argparse
import base64
import hashlib
import http.client
import json
import os
import queue
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

FORMAT = 1
NAME = 'Darkforge'
VERSION_FILE = 'launcher/version.txt'
BLOCKED = ('launcher/python/',)
BACKUP_DIR = '更新备份'
KEEP_BACKUPS = 3                       # 更新备份只留最近几次
SOURCE_FILE = 'launcher/update_source.json'
CHECK_FILE = 'launcher/logs/update_check.json'
DOWNLOAD_DIR = 'launcher/updates'
USER_AGENT = 'Darkforge-Updater/1'
MAX_MANIFEST = 4 << 20
MAX_PACK = 500 << 20                   # 清单里写的更新包再大就不下（Gitee 附件本来也只能 100 MB 左右）
RACE_GRACE = 2.0                       # 第一个来源读到清单后，再等别的来源几秒（版本更新的优先）


def say(msg):
    print('§ ' + msg, flush=True)


def err(msg):
    print('[错误] ' + msg, flush=True)


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def read_version(root):
    p = os.path.join(root, *VERSION_FILE.split('/'))
    try:
        return open(p, encoding='utf-8-sig').read().strip()
    except OSError:
        return None


def vkey(v):
    return tuple(int(x) if x.isdigit() else x for x in str(v).replace('-', '.').split('.'))


def game_running():
    """tasklist 按系统代码页（中文是 GBK）输出，不能按文本解码（UTF-8 模式下会解码失败、误判成没在运行）：直接在字节里找进程名"""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq eldenring.exe', '/NH'], capture_output=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        return b'eldenring.exe' in out.lower()
    except Exception:
        return False


def safe_rel(rel):
    """更新包里的路径只能落在整合包目录里（不许绝对路径、..）"""
    r = rel.replace('\\', '/')
    if not r or r.startswith('/') or ':' in r or any(part in ('', '.', '..') for part in r.split('/')):
        raise ValueError('更新包里有不安全的路径：%s' % rel)
    return r


# ---------------------------------------------------------------- 玩家能改的 JSON：按键合并、保留新版本的排版
def merge_value(base, user, new):
    """玩家没动过的（和旧版本一样）用新版本的；玩家改过的保留玩家的；对象逐键合并；_ 开头的说明一律用新版本的"""
    if isinstance(new, dict) and isinstance(user, dict):
        b = base if isinstance(base, dict) else {}
        out = {}
        for k, nv in new.items():
            if k.startswith('_') or k not in user:
                out[k] = nv
            elif k in b:
                out[k] = merge_value(b[k], user[k], nv)
            else:
                out[k] = user[k]           # 新版本加的键、玩家也有（少见）：保留玩家的
        for k, uv in user.items():          # 玩家自己加的键（旧版本、新版本都没有）
            if k not in out and k not in b:
                out[k] = uv
        return out
    return new if user == base else user


def top_level_spans(text):
    """顶层对象每个键的值在文本里的位置 {键: (起, 止)}，和最后的 } 的位置"""
    dec = json.JSONDecoder()
    i = text.index('{') + 1
    spans = {}
    n = len(text)
    while True:
        while i < n and text[i] in ' \t\r\n,':
            i += 1
        if text[i] == '}':
            return spans, i
        key, i = dec.raw_decode(text, i)
        while text[i] in ' \t\r\n':
            i += 1
        assert text[i] == ':'
        i += 1
        while text[i] in ' \t\r\n':
            i += 1
        _v, j = dec.raw_decode(text, i)
        spans[key] = (i, j)
        i = j


def merge_json_text(base_text, user_text, new_text):
    """返回（合并后的文本, 保留了玩家改动的顶层键）：以新版本的文本为底，只替换值和合并结果不同的顶层键，其余排版不变"""
    base, user, new = json.loads(base_text), json.loads(user_text), json.loads(new_text)
    merged = merge_value(base, user, new)
    spans, end = top_level_spans(new_text)
    out = new_text
    kept = []
    for k in sorted(spans, key=lambda k: -spans[k][0]):
        if merged.get(k) != new[k]:
            a, b = spans[k]
            out = out[:a] + json.dumps(merged[k], ensure_ascii=False) + out[b:]
            kept.append(k)
    extra = [k for k in merged if k not in new]
    if extra:
        _s, end = top_level_spans(out)
        head = out[:end].rstrip()
        add = ''.join(',\n  %s: %s' % (json.dumps(k, ensure_ascii=False), json.dumps(merged[k], ensure_ascii=False)) for k in extra)
        out = head + add + '\n' + out[end:]
        kept += extra
    json.loads(out)
    return out, sorted(kept)


# ---------------------------------------------------------------- 读更新包
class Pack:
    def __init__(self, path):
        self.path = path
        self.z = zipfile.ZipFile(path)
        try:
            self.m = json.loads(self.z.read('update.json').decode('utf-8'))
        except KeyError:
            raise ValueError('不是暗黑重铸的更新包（里面没有 update.json）：%s' % os.path.basename(path))
        if self.m.get('name') != NAME or int(self.m.get('format', 0)) != FORMAT:
            raise ValueError('更新包的格式不认识（%s）：%s' % (self.m.get('format'), os.path.basename(path)))
        self.src, self.dst = str(self.m['from']), str(self.m['to'])
        for f in self.m['files']:
            f['path'] = safe_rel(f['path'])
        for f in self.m.get('delete', []):
            f['path'] = safe_rel(f['path'])
        self.merge = {safe_rel(p) for p in self.m.get('merge_json', [])}

    def data(self, rel):
        return self.z.read('files/' + rel)

    def base(self, rel):
        try:
            return self.z.read('base/' + rel)
        except KeyError:
            return None


def order(packs, cur):
    """从当前版本起接成一条链；接不上的返回在第二个里"""
    chain, left = [], list(packs)
    v = cur
    while True:
        nxt = [p for p in left if p.src == v]
        if not nxt:
            break
        p = max(nxt, key=lambda p: vkey(p.dst))
        chain.append(p)
        left.remove(p)
        v = p.dst
    return chain, left


# ---------------------------------------------------------------- 应用一个更新包
def apply(root, pk, dry=False):
    say('正在核对更新包 v%s → v%s ……' % (pk.src, pk.dst))
    bad = [f['path'] for f in pk.m['files'] + pk.m.get('delete', []) if f['path'].startswith(BLOCKED)]
    if bad:
        raise RuntimeError('这个更新包要换启动器自带的 Python（%s），只能下载完整的整合包' % bad[0])
    for f in pk.m['files']:
        if sha256_bytes(pk.data(f['path'])) != f['sha256']:
            raise RuntimeError('更新包损坏：%s 校验不对，请重新下载更新包' % f['path'])
    full = lambda rel: os.path.join(root, *rel.split('/'))
    # 计划：要写的、要删的；玩家改过的
    writes, deletes, user_changed, merged_keys = [], [], [], {}
    for f in pk.m['files']:
        rel, p = f['path'], full(f['path'])
        new = pk.data(rel)
        cur = sha256_file(p) if os.path.isfile(p) else None
        if cur == f['sha256']:
            continue                                   # 已经是新版本的
        if rel in pk.merge and cur and cur != f.get('old_sha256') and pk.base(rel) is not None:
            text, kept = merge_json_text(pk.base(rel).decode('utf-8-sig'), open(p, 'rb').read().decode('utf-8-sig'), new.decode('utf-8-sig'))
            bom = new.startswith(b'\xef\xbb\xbf')
            new = (b'\xef\xbb\xbf' if bom else b'') + text.encode('utf-8')
            if kept:
                merged_keys[rel] = kept
        elif cur and f.get('old_sha256') and cur != f['old_sha256']:
            user_changed.append(rel)
        writes.append((rel, new))
    for f in pk.m.get('delete', []):
        p = full(f['path'])
        if os.path.isfile(p):
            if f.get('old_sha256') and sha256_file(p) != f['old_sha256']:
                user_changed.append(f['path'])
            deletes.append(f['path'])
    writes.sort(key=lambda w: w[0] == VERSION_FILE)    # version.txt 最后写：中途失败版本号还是旧的
    say('要更新 %d 个文件、删除 %d 个文件' % (len(writes), len(deletes)))
    if dry:
        for rel, _ in writes:
            print('  写 ' + rel)
        for rel in deletes:
            print('  删 ' + rel)
        return {'user_changed': user_changed, 'merged': merged_keys, 'backup': None}
    # 备份
    stamp = time.strftime('%Y%m%d_%H%M%S')
    bdir = os.path.join(root, BACKUP_DIR, '%s_到_%s_%s' % (pk.src, pk.dst, stamp))
    backed, created = [], []
    for rel in [w[0] for w in writes] + deletes:
        p = full(rel)
        if os.path.isfile(p):
            q = os.path.join(bdir, 'files', *rel.split('/'))
            os.makedirs(os.path.dirname(q), exist_ok=True)
            shutil.copy2(p, q)
            backed.append(rel)
        else:
            created.append(rel)
    os.makedirs(bdir, exist_ok=True)
    json.dump({'from': pk.src, 'to': pk.dst, 'backed': backed, 'created': created, 'deleted': deletes},
              open(os.path.join(bdir, 'restore.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    say('已备份要改动的文件：%s' % os.path.relpath(bdir, root))
    # 应用（失败就还原）
    done = []
    try:
        for i, (rel, data) in enumerate(writes):
            p = full(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + '.dfupd'
            with open(tmp, 'wb') as fh:
                fh.write(data)
            replace(tmp, p)
            done.append(rel)
            if len(writes) > 20 and i % max(1, len(writes) // 20) == 0:
                print('§%% %d' % (100 * (i + 1) // len(writes)), flush=True)
        for rel in deletes:
            remove(full(rel))
            done.append(rel)
    except Exception as e:
        err('更新到一半失败（%s），正在还原……' % e)
        restore(root, bdir, [r for r in backed if r in done], [r for r in created if r in done])   # 只还原已经动过的
        raise RuntimeError('更新没有完成，已经还原成 v%s；可能是有文件被占用（关掉游戏和打开着的整合包文件后再试）' % pk.src)
    print('§% 100', flush=True)
    prune_backups(root)
    return {'user_changed': user_changed, 'merged': merged_keys, 'backup': bdir}


def prune_backups(root, keep=KEEP_BACKUPS):
    """更新备份只留最近几次（按文件夹的修改时间）"""
    d = os.path.join(root, BACKUP_DIR)
    try:
        subs = sorted((os.path.join(d, x) for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))), key=os.path.getmtime, reverse=True)
    except OSError:
        return
    for old in subs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def replace(tmp, p, tries=10):
    for k in range(tries):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if k == tries - 1:
                os.remove(tmp)
                raise
            time.sleep(0.3)


def remove(p, tries=10):
    for k in range(tries):
        try:
            os.remove(p)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if k == tries - 1:
                raise
            time.sleep(0.3)


def restore(root, bdir, backed, created):
    for rel in backed:
        src = os.path.join(bdir, 'files', *rel.split('/'))
        dst = os.path.join(root, *rel.split('/'))
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        except Exception as e:
            err('还原 %s 失败：%s（备份在 %s）' % (rel, e, src))
    for rel in created:
        try:
            os.remove(os.path.join(root, *rel.split('/')))
        except OSError:
            pass


# ---------------------------------------------------------------- 在线更新：版本清单、下载
def load_sources(root, manifest=None):
    """更新来源 [{name, manifest: [清单地址…], hosts: [允许的网站…]}]；--manifest 给了就只用它（测试）"""
    if manifest:
        return [{'name': 'test', 'manifest': [manifest], 'hosts': [(urllib.parse.urlsplit(manifest).hostname or '').lower()]}]
    try:
        s = json.load(open(os.path.join(root, *SOURCE_FILE.split('/')), encoding='utf-8-sig'))
    except (OSError, ValueError):
        s = {}
    raw = s.get('sources') if isinstance(s.get('sources'), list) else [dict(s, name='default')]   # 旧格式：只有一个来源
    out = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        urls = [u for u in (x.get('manifest') or []) if isinstance(u, str)]
        hosts = [h.lower() for h in (x.get('hosts') or []) if isinstance(h, str)]
        if urls:
            out.append({'name': str(x.get('name') or 'source%d' % len(out)), 'manifest': urls, 'hosts': hosts})
    return out


def url_ok(url, hosts):
    if not isinstance(url, str):
        return False
    u = urllib.parse.urlsplit(url)
    h = (u.hostname or '').lower()
    if not h or not any(h == x or h.endswith('.' + x) for x in hosts if x):
        return False
    return u.scheme == 'https' or (u.scheme == 'http' and h in ('127.0.0.1', 'localhost'))


def net_reason(e):
    """网络错误 → 给玩家看的一句话"""
    if isinstance(e, urllib.error.HTTPError):
        return {404: '服务器上没有这个文件（404）', 403: '服务器拒绝访问（403）'}.get(e.code, '服务器返回 HTTP %d' % e.code)
    r = getattr(e, 'reason', e)
    if isinstance(r, ConnectFailed):
        return '连接服务器超时（握手没完成，可能是网络不稳定）'
    if isinstance(r, (socket.timeout, TimeoutError)):
        return '连接超时'
    if isinstance(r, ssl.SSLError):
        return '安全连接失败（%s）' % (getattr(r, 'reason', None) or r)
    if isinstance(r, socket.gaierror):
        return '找不到服务器（网络没连上？）'
    if isinstance(r, ConnectionRefusedError):
        return '服务器没有响应（连接被拒绝）'
    if isinstance(r, ConnectionError):
        return '连接被断开'
    return str(r) or type(r).__name__


CONNECT_TIMEOUT = 10                   # 连接 + 握手的时限（正常 2~3 秒）


class ConnectFailed(OSError):
    """连接 / 握手没完成（请求还没发出去，换个连接重试是安全的）"""


class _QuickConn(http.client.HTTPSConnection):
    """Gitee 的握手时好时坏（2026-11-11 实测一半以上一直卡到超时，成功的 2~3 秒）：握手只等 CONNECT_TIMEOUT，
    卡住就放弃、换新连接重试；连上以后读写再用正常的时限"""
    io_timeout = 30

    def connect(self):
        try:
            super().connect()
        except OSError as e:
            raise ConnectFailed('连接 %s 超时（%s）' % (self.host, e)) from e
        self.sock.settimeout(self.io_timeout)


class _QuickHttps(urllib.request.HTTPSHandler):
    def __init__(self, io_timeout):
        super().__init__()
        self.io_timeout = io_timeout

    def https_open(self, req):
        io = self.io_timeout

        def conn(host, **kw):
            c = _QuickConn(host, **kw)
            c.io_timeout = io
            return c
        return self.do_open(conn, req, context=self._context)


class Redirects(urllib.request.HTTPRedirectHandler):
    """记下跳到的最后一个地址：Gitee 附件下载要跳两次（gitee.com → gitee.com → foruda.gitee.com），每跳都要握手；
    重试时直接连最后那个地址，少握手两次"""
    def __init__(self):
        super().__init__()
        self.last = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.last = newurl
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_open(url, headers=None, timeout=20, redirects=None):
    h = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
    h.update(headers or {})
    opener = urllib.request.build_opener(_QuickHttps(timeout), *([redirects] if redirects else []))
    return opener.open(urllib.request.Request(url, headers=h), timeout=min(CONNECT_TIMEOUT, timeout))


def http_get(url, tries=6, timeout=20, limit=MAX_MANIFEST):
    """Gitee 经常握手超时：失败重试几次（404 / 403 不重试）"""
    last = None
    for k in range(tries):
        try:
            with http_open(url, timeout=timeout) as r:
                data = r.read(limit + 1)
            if len(data) > limit:
                raise ValueError('返回的内容太大')
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 404):
                break
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            last = e
        if k < tries - 1:
            time.sleep(min(1 + k, 3))
    raise last


def parse_manifest(raw):
    j = json.loads(raw.decode('utf-8-sig'))
    if isinstance(j, dict) and 'content' in j and j.get('encoding') == 'base64':     # Gitee 接口 contents/latest.json 的返回
        j = json.loads(base64.b64decode(j['content']).decode('utf-8-sig'))
    if not isinstance(j, dict) or j.get('name') != NAME or int(j.get('format', 0)) != FORMAT:
        raise ValueError('版本清单的格式不认识')
    return j


def newer(a, b):
    try:
        return vkey(a) > vkey(b)
    except TypeError:
        return str(a) != str(b)


def plan_chain(updates, cur, target):
    """从 cur 到 target 的更新包链：包最少，一样多时下载量最小；接不上返回 None"""
    if cur == target:
        return []
    best = {cur: (0, 0, [])}
    frontier = [cur]
    while frontier:
        nxt = []
        for v in frontier:
            hops, size, path = best[v]
            for u in updates:
                if str(u.get('from')) != v or not newer(str(u.get('to')), v):
                    continue
                t = str(u.get('to'))
                cand = (hops + 1, size + int(u.get('size') or 0), path + [u])
                if t not in best:
                    nxt.append(t)
                    best[t] = cand
                elif cand[:2] < best[t][:2]:
                    best[t] = cand
        frontier = nxt
    return best[target][2] if target in best else None


def read_source(src):
    """读一个来源的清单（地址按顺序试）：（清单, 出错原因）"""
    why = []
    for u in src['manifest']:
        if not url_ok(u, src['hosts']):
            why.append('地址不在允许的网站里')
            continue
        try:
            return parse_manifest(http_get(u, tries=4)), None
        except Exception as e:
            why.append(net_reason(e))
    return None, '；'.join(dict.fromkeys(why))


def race(srcs, grace=RACE_GRACE):
    """同时读各来源的清单：第一个读到的来了以后再等 grace 秒，返回 [(来源, 清单, 出错原因, 用时)]（按到的先后）；
    慢的那边不等（后台线程，进程结束就没了）"""
    q = queue.Queue()
    t0 = time.time()

    def run(src):
        m, why = read_source(src)
        q.put((src, m, why, time.time() - t0))
    for src in srcs:
        threading.Thread(target=run, args=(src,), daemon=True).start()
    got, first = [], None
    while len(got) < len(srcs):
        try:
            item = q.get(timeout=None if first is None else max(0.0, first + grace - time.time()))
        except queue.Empty:
            break
        got.append(item)
        if item[1] is not None and first is None:
            first = time.time()
    return got


def check(root, manifest=None):
    """检查更新，结果写 CHECK_FILE 并返回：status = latest / available / full / error"""
    cur = read_version(root)
    res = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'cur': cur, 'status': 'error'}
    try:
        if not cur:
            raise RuntimeError('找不到整合包的版本号（%s）' % VERSION_FILE)
        srcs = load_sources(root, manifest)
        if not srcs:
            raise RuntimeError('没有设置更新地址（%s）' % SOURCE_FILE)
        got = race(srcs)
        res['sources'] = {s['name']: ('%.1f 秒' % dt if m is not None else '失败：' + why) for s, m, why, dt in got}
        for s in srcs:
            res['sources'].setdefault(s['name'], '没等到')
        oks = [(s, m) for s, m, why, dt in got if m is not None]
        if not oks:
            raise RuntimeError('没能读到版本清单（%s）' % '；'.join(dict.fromkeys(why for s, m, why, dt in got if why)))
        best = oks[0]
        for s, m in oks[1:]:                   # 先到的优先；晚到一点但版本更新的（另一边刚发布完）换成它
            if newer(str(m.get('latest') or '0'), str(best[1].get('latest') or '0')):
                best = (s, m)
        src, m = best
        hosts = src['hosts']
        res['source'] = src['name']
        latest = str(m.get('latest') or '')
        res.update(latest=latest, date=str(m.get('date') or ''))
        full = m.get('full') if isinstance(m.get('full'), dict) else {}
        if isinstance(full.get('url'), str) and full['url'].startswith('https://'):
            res.update(full_url=full['url'], full_version=str(full.get('version') or ''), full_note=str(full.get('note') or ''))
        if not latest or not newer(latest, cur):
            res['status'] = 'latest'
        else:
            ups = [u for u in (m.get('updates') or []) if isinstance(u, dict)]
            chain = plan_chain(ups, cur, latest)
            ok = chain and all(url_ok(u.get('url'), hosts) and isinstance(u.get('sha256'), str)
                               and 0 < int(u.get('size') or 0) <= MAX_PACK for u in chain)
            if ok:
                res['status'] = 'available'
                res['chain'] = [{k: u.get(k) for k in ('from', 'to', 'file', 'size', 'sha256', 'url')} for u in chain]
                for c in res['chain']:            # 另一边同一个文件（SHA-256 一样）的地址：这边下不了时换过去
                    c['alt'] = [u['url'] for s2, m2 in oks if s2 is not src for u in (m2.get('updates') or [])
                                if isinstance(u, dict) and u.get('sha256') == c['sha256'] and url_ok(u.get('url'), s2['hosts'])]
                res['size'] = sum(int(u['size']) for u in chain)
                res['notes'] = [{'version': str(u.get('to')), 'date': str(u.get('date') or ''), 'text': str(u.get('notes') or '')} for u in chain]
            else:
                res['status'] = 'full'
                res['notes'] = [{'version': latest, 'date': res['date'], 'text': str(m.get('notes') or '')}]
    except Exception as e:
        res['error'] = str(e)
    p = os.path.join(root, *CHECK_FILE.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = '%s.%d.tmp' % (p, os.getpid())             # 启动器后台检查和手动检查可能同时在跑
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    try:
        replace(tmp, p)
    except OSError:
        pass
    return res


def say_check(res):
    if res.get('sources'):                   # 不带 § 的行只进日志（排查用：哪边快、哪边连不上）
        print('更新来源：%s；用 %s' % ('，'.join('%s %s' % kv for kv in res['sources'].items()), res.get('source', '无')), flush=True)
    s = res['status']
    if s == 'latest':
        say('已经是最新版本 v%s' % res['cur'])
    elif s == 'available':
        say('有新版本 v%s%s：要下载 %d 个更新包，共 %.1f MB' % (res['latest'], '（%s）' % res['date'] if res.get('date') else '',
                                                     len(res['chain']), res['size'] / 1048576))
    elif s == 'full':
        say('有新版本 v%s，但没有能从 v%s 直接更新的更新包，请下载完整的整合包%s' % (
            res['latest'], res['cur'], '：' + res['full_url'] if res.get('full_url') else ''))
    else:
        err('检查更新失败：%s' % res.get('error', ''))


def pack_name(u):
    n = os.path.basename(str(u.get('file') or '').replace('\\', '/'))
    if not n.lower().endswith('.zip') or any(c in n for c in ':*?"<>|') or n.startswith('.'):
        n = 'Darkforge_v%s_to_v%s_update.zip' % (u['from'], u['to'])
    return n


class BadPack(RuntimeError):
    """下下来的文件不对（已经删掉，下次从头下）"""


def download(url, dst, size, sha, on_bytes, tries=8):
    """下到 dst.part（断了从断开的地方接着下），大小和 SHA-256 都对了才改名成 dst"""
    part = dst + '.part'
    last = None
    target = url                  # 跳转后的最终地址（带时限）：重试直接连它；过期了（403 / 404）再从原地址跳
    for k in range(tries):
        have = os.path.getsize(part) if os.path.isfile(part) else 0
        if have > size:
            os.remove(part)
            have = 0
        if have == size:
            break
        rd = Redirects()
        try:
            with http_open(target, {'Range': 'bytes=%d-' % have} if have else None, timeout=30, redirects=rd) as r:
                if have and r.status != 206:           # 服务器不支持续传：从头下
                    have = 0
                got = have
                with open(part, 'ab' if have else 'wb') as f:
                    while True:
                        blk = r.read(1 << 16)
                        if not blk:
                            break
                        got += len(blk)
                        if got > size:
                            raise ValueError('下载的文件比版本清单里写的大')
                        f.write(blk)
                        on_bytes(got)
            if got == size:
                break
            last = OSError('下载中断（%d / %d 字节）' % (got, size))
        except urllib.error.HTTPError as e:
            last = e
            rd.last = None
            if e.code == 416:                          # 续传的位置不对：从头下
                os.remove(part)
            elif e.code in (401, 403, 404, 410) and target != url:
                target = url                           # 跳转后的地址过期了
            elif e.code in (401, 403, 404):
                break
        except ValueError as e:
            os.remove(part)
            raise BadPack(str(e))
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            last = e
        if rd.last:
            target = rd.last
        if k < tries - 1:
            time.sleep(min(1 + k, 4))
    if not os.path.isfile(part) or os.path.getsize(part) != size:
        raise RuntimeError('下载失败：%s' % (net_reason(last) if last else '不完整'))
    if sha256_file(part) != sha:
        os.remove(part)
        raise BadPack('下载的更新包校验不对（文件损坏），请再试一次')
    os.replace(part, dst)


def fetch(root, res):
    """把 res['chain'] 里的更新包下到 DOWNLOAD_DIR，返回本地路径（已经下好、校验对的直接用）"""
    ddir = os.path.join(root, *DOWNLOAD_DIR.split('/'))
    os.makedirs(ddir, exist_ok=True)
    total = res['size']
    base = 0
    shown = [-1]

    def progress(got):
        pct = int(100 * (base + got) / max(1, total))
        if pct != shown[0]:
            shown[0] = pct
            print('§%% %d' % pct, flush=True)

    out = []
    for i, u in enumerate(res['chain']):
        p = os.path.join(ddir, pack_name(u))
        size = int(u['size'])
        if not (os.path.isfile(p) and os.path.getsize(p) == size and sha256_file(p) == u['sha256']):
            say('正在下载更新包 %d/%d：v%s → v%s（%.1f MB）……' % (i + 1, len(res['chain']), u['from'], u['to'], size / 1048576))
            links = [u['url']] + [x for x in (u.get('alt') or []) if x != u['url']]
            for j, link in enumerate(links):
                try:
                    download(link, p, size, u['sha256'], progress, tries=8 if j == len(links) - 1 else 5)
                    break
                except RuntimeError as e:            # 包括校验不对（BadPack）：换另一边的服务器
                    if j == len(links) - 1:
                        raise
                    say('这个服务器下载不了（%s），换另一个服务器……' % e)
        base += size
        progress(0)
        out.append(p)
    return out


def clean_downloads(root, keep=()):
    """更新成功后删掉下好的更新包（和没下完的 .part）"""
    ddir = os.path.join(root, *DOWNLOAD_DIR.split('/'))
    try:
        names = os.listdir(ddir)
    except OSError:
        return
    for n in names:
        p = os.path.join(ddir, n)
        if os.path.isfile(p) and p not in keep and (n.endswith('.zip') or n.endswith('.part')):
            try:
                os.remove(p)
            except OSError:
                pass


def log_line(root, text):
    d = os.path.join(root, 'launcher', 'logs')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'update_ops.txt'), 'a', encoding='utf-8') as f:
        f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text))


def write_result(root, text):
    d = os.path.join(root, 'launcher', 'logs')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'update_result.txt'), 'w', encoding='utf-8') as f:
        f.write(text + '\n')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--zip', action='append')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--fetch', action='store_true')
    ap.add_argument('--manifest')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    if a.check:
        res = check(root, a.manifest)
        say_check(res)
        return 1 if res['status'] == 'error' else 0
    if not a.dry:
        write_result(root, 'fail')
    if a.fetch:
        return main_fetch(root, a)
    if not a.zip:
        err('没有选更新包')
        return 1
    return apply_zips(root, a.zip, a.dry)


def main_fetch(root, a):
    if not a.dry and game_running():
        err('游戏还在运行，请先退出游戏再更新')
        return 1
    say('正在检查更新……')
    res = check(root, a.manifest)
    say_check(res)
    if res['status'] in ('latest', 'full'):
        if not a.dry:
            write_result(root, res['status'])
        return 0 if res['status'] == 'latest' else 1
    if res['status'] != 'available':
        return 1
    try:
        zips = fetch(root, res)
    except Exception as e:
        err(str(e))
        ddir = os.path.join(root, *DOWNLOAD_DIR.split('/'))
        if not isinstance(e, BadPack) and any(n.endswith('.part') for n in os.listdir(ddir)):
            say('没下完，过一会儿再点更新就行')
        log_line(root, '在线更新 v%s → v%s 下载失败：%s' % (res['cur'], res['latest'], e))
        return 1
    say('更新包下载好了，正在应用……')
    code = apply_zips(root, zips, a.dry)
    if code == 0 and not a.dry:
        clean_downloads(root)
    return code


def apply_zips(root, zips, dry=False):
    cur = read_version(root)
    if not cur:
        err('找不到整合包的版本号（%s）' % VERSION_FILE)
        return 1
    packs = []
    try:
        for z in zips:
            packs.append(Pack(z))
    except Exception as e:
        err(str(e))
        return 1
    try:
        return apply_packs(root, cur, packs, dry)
    finally:
        for p in packs:                 # 关掉 zip：在线更新成功后要删掉下好的更新包
            p.z.close()


def apply_packs(root, cur, packs, dry):
    a = argparse.Namespace(dry=dry)
    chain, left = order(packs, cur)
    if not chain:
        have = '、'.join('v%s → v%s' % (p.src, p.dst) for p in packs)
        err('这些更新包都不能用在现在的版本 v%s 上（%s）。更新包要从你现在的版本开始，按顺序导入' % (cur, have))
        return 1
    if not a.dry and game_running():
        err('游戏还在运行，请先退出游戏再更新')
        return 1
    notes = []
    for pk in chain:
        try:
            r = apply(root, pk, a.dry)
        except Exception as e:
            err(str(e))
            log_line(root, 'v%s → v%s 失败：%s' % (pk.src, pk.dst, e))
            return 1
        if r['merged']:
            for rel, keys in r['merged'].items():
                notes.append('%s 里你改过的设置保留了：%s' % (rel, '、'.join(keys)))
        if r['user_changed']:
            notes.append('这些文件你改过，已换成新版本（原来的留在备份里）：%s' % '、'.join(r['user_changed']))
        if not a.dry:
            log_line(root, 'v%s → v%s 完成，备份 %s%s' % (pk.src, pk.dst, os.path.relpath(r['backup'], root),
                                                     '；' + '；'.join(notes) if notes else ''))
            say('已更新到 v%s' % pk.dst)
    for n in dict.fromkeys(notes):        # 连着几个包都保留了同一项设置时只说一次
        say(n)
    if left:
        say('没用上的更新包（版本接不上）：%s' % '、'.join('v%s → v%s' % (p.src, p.dst) for p in left))
    if not a.dry:
        write_result(root, 'ok ' + chain[-1].dst)
        say('更新完成，启动器会重新打开')
    return 0


if __name__ == '__main__':
    sys.exit(main())
