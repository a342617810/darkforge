# -*- coding: utf-8 -*-
"""把更新包发布到 Gitee 和 GitHub（用户 2026-11-11「通过 gitee 实现自动更新」「在国内就用 gitee 在国外就用 github」→「两边一起试」），
玩家启动器的「检查更新」同时读两边，先读到的那边说了算（launcher\\update.py、launcher\\update_source.json）。
两边仓库都叫 xp271/darkforge_update（公开，不开源，README 写明保留所有权利），内容一样：
  latest.json        版本清单（格式见 launcher\\update.py），下载地址写各自平台的
  发行版 v<版本>      附件 = 更新包（make_delta.py 做的 Darkforge_v旧_to_v新_update.zip），两边是同一个文件
令牌（自己放，别发给别人；dev\\ 不打包）：
  Gitee   「设置 → 私人令牌」，勾 projects            → dev\\tools\\gitee_token.txt  或环境变量 GITEE_TOKEN
  GitHub  「Settings → Developer settings → Fine-grained tokens」，只选这个仓库，Contents 读写 → dev\\tools\\github_token.txt  或 GITHUB_TOKEN
脚本不打印令牌，出错信息里也会遮掉。

Gitee 由 GitHub 转发（用户 2026-11-11「GitHub 自动转发」：开发者那边往 Gitee 传更新包只有几 KB/秒，传不上去）：
  默认只发 GitHub；GitHub 的 latest.json 一改，仓库里的 GitHub Actions（.github/workflows/sync-gitee.yml + .github/sync_gitee.py，
  原件在 dev\\tools\\gitee_relay\\）就把更新包和清单转发到 Gitee。发完这里会等转发跑完，告诉你 Gitee 那边成没成。
  转发要：GitHub 仓库的 Secret GITEE_TOKEN；装转发时 GitHub 令牌还要有 Workflows 读写。
  --only gitee 还是能从这里直接发 Gitee（网络好的时候），--only github 只发 GitHub、不等转发。

用法：
  python dev\\tools\\publish_update.py <更新包.zip> [<更新包2.zip> ...] [--full-url 网址] [--full-note 说明] [--dry] [--yes] [--allow-third-party]
      几个更新包要到同一个版本（比如 0.10.0→0.10.1 和 0.9.10→0.10.1 一起发）。先列出要做的事，输入 yes 才真的发（--yes 不问）。
      --full-url：完整整合包的下载页（更新包接不上时启动器打开它），不给就沿用清单里原来的。
      每边的顺序：建发行版 → 传附件 → 不登录下载核对 → 最后才改 latest.json（中途失败玩家那边看不到半成品）。
      一边失败不影响另一边；失败的那边修好网络后用 --only 再发一次（已经传好的附件不重传）。
  python dev\\tools\\publish_update.py --status          看两边的清单和发行版
  python dev\\tools\\publish_update.py --test [--yes]    试一遍：建测试发行版 test、传一个小 zip、不登录下载核对、再删掉；不动 latest.json
  python dev\\tools\\publish_update.py --prune [--yes]   删掉清单里已经不用的发行版
  python dev\\tools\\publish_update.py --install-relay    把 dev\\tools\\gitee_relay 里的转发任务装到 GitHub 仓库（改了也用它更新），装上就会跑一次
空仓库第一次发布（或 --test）时先建 README.md，默认分支才有。
国外连 Gitee 很慢（2026-11-11 实测一半握手卡住）：在终端里跑、加 python -u 看进度；每行带时间。"""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(SRC, 'launcher'))
import make_delta  # noqa: E402
from update import CONNECT_TIMEOUT, ConnectFailed, _QuickHttps  # noqa: E402  握手只等 10 秒、卡住换连接重试（和启动器同一套）

OWNER, REPO = 'xp271', 'darkforge_update'
MANIFEST = 'latest.json'
KEEP = 100                               # 清单里最多留几个更新包（= 最多能跨几个版本；用户 2026-11-11 从 12 调到 100）
FULL_NOTES = 10                          # 最新几个更新包带完整的更新内容；更早的只留开头 OLD_NOTES 字（清单小一点：启动器每次打开都要读）
OLD_NOTES = 200
UA = 'Darkforge-Publisher/1'
TOKENS = []                              # 所有令牌（出错信息里遮掉）

README = """# 暗黑重铸 / Darkforge 更新源

这个仓库只放暗黑重铸整合包的更新包和版本清单（latest.json），给整合包启动器的「检查更新」用。
Gitee 和 GitHub 上各有一份，内容一样：启动器两边一起试，哪边快用哪边。

- 玩家不用来这里下载：打开启动器 → 工具 →「检查更新」。
- 也可以在「发行版 / Releases」里手动下载更新包，用启动器的「导入更新包」导入。

## 版权

© Darkforge 作者，保留所有权利（All rights reserved）。本仓库不是开源项目，未经许可不得转载、修改后再发布或用于商业用途。

整合包里用到的第三方组件（YAFSML、Erd-Tools-CPP、fromsoftware-rs、CPython、zstd、WebView2、hyp-launcher-ui 等）
按它们各自的许可使用，许可文本随整合包一起提供。作者不许转载的组件不放在这里。
"""


def say(*a):
    """进度：每行带时间、马上输出"""
    print(time.strftime('[%H:%M:%S]'), *a, flush=True)


def mask(s):
    s = str(s)
    for t in TOKENS:
        if t:
            s = s.replace(t, '***')
    return s


class ApiError(Exception):
    def __init__(self, who, code, text):
        super().__init__('%s 接口返回 %s：%s' % (who, code, mask(text)[:400]))
        self.code = code


# ---------------------------------------------------------------- 两个平台共用的部分
class Target:
    key = label = web = branch = token_file = token_env = token_help = ''
    max_attach = 0
    can_delete_tag = False

    def __init__(self):
        self.token = ''

    def load_token(self, optional=False):
        t = os.environ.get(self.token_env, '').strip()
        p = os.path.join(HERE, self.token_file)
        if not t and os.path.isfile(p):
            lines = [l.strip() for l in open(p, encoding='utf-8-sig').read().splitlines() if l.strip() and not l.startswith('#')]
            t = lines[0] if lines else ''
        if not t and not optional:
            raise SystemExit('没有 %s 令牌：%s，自己放进 %s（一行，别发给别人）' % (self.label, self.token_help, p))
        self.token = t
        TOKENS.append(t)

    def say(self, msg):
        say('[%s] %s' % (self.label, msg))

    def request(self, method, url, data=None, headers=None, timeout=60, tries=8, show=None):
        """发请求，返回解析好的 JSON（空的返回 None）。握手没完成（请求还没发出去）怎么都能重试；
        发出去以后出错的，POST（建发行版、传附件）不重试（免得重复）"""
        h = {'User-Agent': UA}
        h.update(headers or {})
        opener = urllib.request.build_opener(_QuickHttps(timeout))
        self.say('  … %s %s%s' % (method, show or urllib.parse.urlsplit(url).path, '（%.1f MB）' % (len(data) / 1048576) if data and len(data) > 100000 else ''))
        last = None
        for k in range(tries):
            try:
                with opener.open(urllib.request.Request(url, data=data, headers=h, method=method), timeout=CONNECT_TIMEOUT) as r:
                    body = r.read()
                return json.loads(body.decode('utf-8')) if body.strip() else None
            except urllib.error.HTTPError as e:
                raise ApiError(self.label, e.code, e.read().decode('utf-8', 'replace'))
            except (urllib.error.URLError, OSError) as e:
                last = e
                stuck = isinstance(getattr(e, 'reason', e), ConnectFailed)
                if not stuck and method == 'POST':
                    break
                if k < tries - 1:
                    self.say('    %s，换连接重试（第 %d 次）' % ('握手卡住' if stuck else '出错', k + 1))
                    time.sleep(min(1 + k, 4))
        raise RuntimeError('连不上 %s（试了 %d 次）：%s' % (self.label, k + 1, mask(getattr(last, 'reason', last))))

    def download_url(self, tag, name):
        return '%s/releases/download/%s/%s' % (self.web, tag, name)

    def upload(self, rid, name, data, timeout=900, tries=4):
        """传附件：中途断开就先看服务器收到没有，没收到再传，不会传重复。返回附件信息（含下载地址）"""
        for k in range(tries):
            try:
                return self.upload_raw(rid, name, data, timeout)
            except RuntimeError as e:
                self.say('    上传中断（%s），看一下服务器收到没有……' % mask(e))
                for x in self.attachments(rid):
                    if x.get('name') != name:
                        continue
                    if not x.get('size') or int(x['size']) == len(data):
                        self.say('    服务器已经收到了')
                        return x
                    self.delete_attachment(rid, x['id'])        # 收了一半的：删掉重传
                if k == tries - 1:
                    raise
                self.say('    重新上传（第 %d 次）' % (k + 1))

    def ensure_init(self):
        """空仓库：先建 README.md（第一次提交才有默认分支，发行版要挂在提交上）。建了返回 True"""
        if self.branches():
            return False
        self.put_file('README.md', README.encode('utf-8'), '初始化：说明与版权', empty=True)
        for _ in range(10):
            if self.branches():
                self.say('已建 README.md')
                return True
            time.sleep(2)
        raise RuntimeError('建好 README 之后还是看不到 %s 分支' % self.branch)

    def raw_url(self, path):
        raise NotImplementedError


class Gitee(Target):
    key, label = 'gitee', 'Gitee'
    api = 'https://gitee.com/api/v5'
    web = 'https://gitee.com/%s/%s' % (OWNER, REPO)
    branch = 'master'
    max_attach = 100 << 20               # 单个附件约 100 MB
    token_file, token_env = 'gitee_token.txt', 'GITEE_TOKEN'
    token_help = '在 Gitee「设置 → 私人令牌」生成一个（勾选 projects）'

    def call(self, method, parts, fields=None, query=None, files=None, timeout=60, tries=8):
        q, f = dict(query or {}), dict(fields or {})
        if self.token:
            (q if method in ('GET', 'DELETE') else f)['access_token'] = self.token
        path = '/repos/%s/%s/' % (OWNER, REPO) + '/'.join(urllib.parse.quote(str(p), safe='') for p in parts)
        url = self.api + path + ('?' + urllib.parse.urlencode(q) if q else '')
        h, data = {'Accept': 'application/json'}, None
        if files:
            data, h['Content-Type'] = multipart(f, files)
        elif method in ('POST', 'PUT', 'PATCH'):
            data = urllib.parse.urlencode(f).encode('utf-8')
            h['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8'
        return self.request(method, url, data, h, timeout, tries, show='/' + '/'.join(map(str, parts)))

    def call404(self, *a, **k):
        try:
            return self.call(*a, **k)
        except ApiError as e:
            if e.code == 404:
                return None
            raise

    def branches(self):
        return self.call404('GET', ['branches']) or []

    def get_file(self, path):
        j = self.call404('GET', ['contents'] + path.split('/'), query={'ref': self.branch})
        if not j or isinstance(j, list) or 'content' not in j:
            return None, None
        return base64.b64decode(j['content']), j['sha']

    def put_file(self, path, data, message, sha=None, empty=False):
        f = {'content': base64.b64encode(data).decode('ascii'), 'message': message}
        if not empty:
            f['branch'] = self.branch
        if sha:
            f['sha'] = sha
            return self.call('PUT', ['contents'] + path.split('/'), f)
        return self.call('POST', ['contents'] + path.split('/'), f)

    def get_release(self, tag):
        j = self.call404('GET', ['releases', 'tags', tag])
        return j if isinstance(j, dict) and j.get('id') else None

    def create_release(self, tag, name, body, pre=False):
        return self.call('POST', ['releases'], {'tag_name': tag, 'name': name, 'body': body or name,
                                                'prerelease': 'true' if pre else 'false', 'target_commitish': self.branch})

    def delete_release(self, rid):
        self.call('DELETE', ['releases', rid])

    def delete_tag(self, tag):
        pass                              # Gitee 接口删不了标签（DELETE tags 是 404）

    def releases(self):
        out, page = [], 1
        while True:
            j = self.call('GET', ['releases'], query={'per_page': 100, 'page': page, 'direction': 'desc'}) or []
            out += j
            if len(j) < 100:
                return out
            page += 1

    def attachments(self, rid):
        return self.call404('GET', ['releases', rid, 'attach_files'], query={'per_page': 100}) or []

    def delete_attachment(self, rid, aid):
        self.call('DELETE', ['releases', rid, 'attach_files', aid])

    def upload_raw(self, rid, name, data, timeout):
        return self.call('POST', ['releases', rid, 'attach_files'], files={'file': (name, data)}, timeout=timeout)

    def raw_url(self, path):
        return '%s/raw/%s/%s' % (self.web, self.branch, path)


class GitHub(Target):
    key, label = 'github', 'GitHub'
    api = 'https://api.github.com'
    uploads = 'https://uploads.github.com'
    web = 'https://github.com/%s/%s' % (OWNER, REPO)
    branch = 'main'
    max_attach = 2000 << 20              # 单个附件 2 GB
    can_delete_tag = True
    token_file, token_env = 'github_token.txt', 'GITHUB_TOKEN'
    token_help = '在 GitHub「Settings → Developer settings → Fine-grained tokens」生成一个，只选 xp271/darkforge_update，Contents 读写'

    def call(self, method, parts, body=None, query=None, raw=None, base=None, timeout=60, tries=8):
        path = '/repos/%s/%s/' % (OWNER, REPO) + '/'.join(urllib.parse.quote(str(p), safe='') for p in parts)
        url = (base or self.api) + path + ('?' + urllib.parse.urlencode(query) if query else '')
        h = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
        if self.token:
            h['Authorization'] = 'Bearer ' + self.token
        data = None
        if raw is not None:
            data, h['Content-Type'] = raw, 'application/zip'
        elif body is not None:
            data, h['Content-Type'] = json.dumps(body, ensure_ascii=False).encode('utf-8'), 'application/json'
        return self.request(method, url, data, h, timeout, tries, show='/' + '/'.join(map(str, parts)))

    def call404(self, *a, **k):
        try:
            return self.call(*a, **k)
        except ApiError as e:
            if e.code in (404, 409):         # 409：仓库是空的
                return None
            raise

    def branches(self):
        return self.call404('GET', ['branches']) or []

    def get_file(self, path):
        j = self.call404('GET', ['contents'] + path.split('/'), query={'ref': self.branch})
        if not j or isinstance(j, list) or 'content' not in j:
            return None, None
        return base64.b64decode(j['content']), j['sha']

    def put_file(self, path, data, message, sha=None, empty=False):
        b = {'message': message, 'content': base64.b64encode(data).decode('ascii')}
        if not empty:
            b['branch'] = self.branch
        if sha:
            b['sha'] = sha
        return self.call('PUT', ['contents'] + path.split('/'), b)

    def get_release(self, tag):
        j = self.call404('GET', ['releases', 'tags', tag])
        return j if isinstance(j, dict) and j.get('id') else None

    def create_release(self, tag, name, body, pre=False):
        return self.call('POST', ['releases'], {'tag_name': tag, 'name': name, 'body': body or name,
                                                'prerelease': bool(pre), 'target_commitish': self.branch})

    def delete_release(self, rid):
        self.call('DELETE', ['releases', rid])

    def delete_tag(self, tag):
        try:
            self.call('DELETE', ['git', 'refs', 'tags', tag])
        except ApiError as e:
            if e.code not in (404, 422):
                raise

    def releases(self):
        out, page = [], 1
        while True:
            j = self.call404('GET', ['releases'], query={'per_page': 100, 'page': page}) or []
            out += j
            if len(j) < 100:
                return out
            page += 1

    def attachments(self, rid):
        return self.call404('GET', ['releases', rid, 'assets'], query={'per_page': 100}) or []

    def delete_attachment(self, rid, aid):
        self.call('DELETE', ['releases', 'assets', aid])

    def upload_raw(self, rid, name, data, timeout):
        return self.call('POST', ['releases', rid, 'assets'], query={'name': name}, raw=data, base=self.uploads, timeout=timeout)

    def raw_url(self, path):
        return 'https://raw.githubusercontent.com/%s/%s/%s/%s' % (OWNER, REPO, self.branch, path)


TARGETS = {'github': GitHub, 'gitee': Gitee}      # GitHub 在前：从国外发几秒就好；Gitee 慢，放后面


def multipart(fields, files):
    b = '----Darkforge' + os.urandom(12).hex()
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n' % (b, k)).encode('utf-8'))
        out.write(str(v).encode('utf-8') + b'\r\n')
    for k, (name, data) in files.items():
        out.write(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: application/zip\r\n\r\n'
                   % (b, k, name)).encode('utf-8'))
        out.write(data + b'\r\n')
    out.write(('--%s--\r\n' % b).encode('utf-8'))
    return out.getvalue(), 'multipart/form-data; boundary=' + b


# ---------------------------------------------------------------- 不登录下载核对（玩家那边就是这样下）
class _LogRedirect(urllib.request.HTTPRedirectHandler):
    """下载地址会跳到存附件的服务器：每一跳打一行，记下最后一个地址（重试直接连它）"""
    last = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        say('    跳转 %d → %s' % (code, urllib.parse.urlsplit(newurl).hostname))
        self.last = newurl
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def anon_get(url, rng=None, timeout=60, tries=15):
    h = {'User-Agent': 'Darkforge-Updater/1'}
    if rng:
        h['Range'] = rng
    rd = _LogRedirect()
    opener = urllib.request.build_opener(_QuickHttps(timeout), rd)
    target = url
    for k in range(tries):
        try:
            with opener.open(urllib.request.Request(target, headers=h), timeout=CONNECT_TIMEOUT) as r:
                return r.status, r.geturl(), r.read()
        except urllib.error.URLError as e:
            if isinstance(e, urllib.error.HTTPError) and target != url and e.code in (401, 403, 404, 410):
                target = url          # 跳转后的地址过期了：从原地址重新跳
                continue
            if not isinstance(e.reason, ConnectFailed) or k == tries - 1:
                raise
            if rd.last:
                target = rd.last
            say('    %s，换连接重试（第 %d 次）' % (e.reason, k + 1))
            time.sleep(min(1 + k, 4))


def verify_download(url, data):
    """整个下下来比对；再试一次续传（Range）。返回 (对不对, 说明)"""
    try:
        st, final, got = anon_get(url, timeout=300)
    except Exception as e:
        return False, '下载失败：%s' % mask(e)
    if got != data:
        head = got[:120].decode('utf-8', 'replace').replace('\n', ' ')
        return False, '下到的内容不对（%d 字节，开头：%s）' % (len(got), head)
    note = '整个下载一致（%d 字节，最后落在 %s）' % (len(got), urllib.parse.urlsplit(final).hostname)
    try:
        st2, _f, part = anon_get(url, 'bytes=%d-' % (len(data) // 2))
        note += '；续传 %s' % ('支持（206）' if st2 == 206 and part == data[len(data) // 2:] else '不支持（%d），断线后会从头下' % st2)
    except Exception as e:
        note += '；续传请求失败：%s' % mask(e)
    return True, note


# ---------------------------------------------------------------- 更新包、更新内容
class Pack:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.data = open(path, 'rb').read()
        self.size = len(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()
        z = zipfile.ZipFile(io.BytesIO(self.data))
        self.m = json.loads(z.read('update.json').decode('utf-8'))
        if self.m.get('name') != 'Darkforge' or int(self.m.get('format', 0)) != 1:
            raise SystemExit('%s 不是暗黑重铸的更新包' % self.name)
        self.src, self.dst = str(self.m['from']), str(self.m['to'])
        self.paths = [f['path'] for f in self.m['files']] + [f['path'] for f in self.m.get('delete', [])]
        try:
            self.changelog = z.read('files/更新日志.txt').decode('utf-8-sig')
        except KeyError:
            self.changelog = None


def changelog_notes(text, ver):
    """更新日志里这个版本的那一节：（正文, 日期）"""
    text = text.replace('\r\n', '\n')
    heads = list(re.finditer(r'(?m)^v(\d[\w.\-]*)\s*[（(]([^）)\n]*)[）)][^\n]*\n-{3,}\n', text))
    for i, m in enumerate(heads):
        if m.group(1) == ver:
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            return text[m.end():end].strip(), m.group(2).strip()
    return '', ''


def newer(a, b):
    k = lambda v: tuple(int(x) if x.isdigit() else 0 for x in re.split(r'[.\-]', v))
    return k(a) > k(b)


def build_manifest(old, packs, to, date, notes, urls, full_url, full_note):
    ups = [{'from': p.src, 'to': to, 'date': date, 'notes': notes, 'file': p.name, 'size': p.size,
            'sha256': p.sha, 'url': urls[p.name]} for p in packs]
    have = {(u['from'], u['to']) for u in ups}
    for u in (old or {}).get('updates', []):
        if isinstance(u, dict) and (str(u.get('from')), str(u.get('to'))) not in have:
            ups.append(u)
    full = dict((old or {}).get('full') or {})
    if full_url:
        full = {'version': to, 'url': full_url, 'note': full_note if full_note is not None else full.get('note', '')}
    elif full_note is not None:
        full['note'] = full_note
    ups = ups[:KEEP]
    for u in ups[FULL_NOTES:]:
        n = str(u.get('notes') or '')
        if len(n) > OLD_NOTES:
            u['notes'] = n[:OLD_NOTES].rstrip() + '……'
    return {'format': 1, 'name': 'Darkforge', 'latest': to, 'date': date, 'notes': notes, 'full': full, 'updates': ups}


def confirm(a, what):
    if a.yes:
        return True
    try:
        return input('%s\n输入 yes 继续：' % what).strip().lower() == 'yes'
    except EOFError:
        return False


# ---------------------------------------------------------------- 发布
def publish(a, targets):
    packs = [Pack(p) for p in a.zips]
    tos = {p.dst for p in packs}
    if len(tos) != 1:
        raise SystemExit('这几个更新包不是到同一个版本：%s' % '、'.join(sorted(tos)))
    to = tos.pop()
    if len({p.src for p in packs}) != len(packs):
        raise SystemExit('有两个更新包是从同一个版本开始的')
    for p in packs:
        deny, ask = make_delta.public_check(p.paths)
        if deny:
            raise SystemExit('%s 里有作者不许转载的文件，不能公开发布：%s' % (p.name, '、'.join(deny[:8])))
        if ask and not a.allow_third_party:
            raise SystemExit('%s 里有还没确认许可的第三方文件：%s\n确定可以公开后加 --allow-third-party' % (p.name, '、'.join(ask[:8])))
    cl = next((p.changelog for p in packs if p.changelog), None) or open(os.path.join(SRC, '更新日志.txt'), encoding='utf-8-sig').read()
    notes, date = changelog_notes(cl, to)
    if not notes:
        raise SystemExit('更新日志里找不到 v%s 那一节' % to)
    if not re.match(r'\d{4}-\d\d-\d\d$', date):
        if not a.dry:
            raise SystemExit('更新日志里 v%s 的日期是「%s」：先写上发布日期再打包、做更新包' % (to, date))
        date = time.strftime('%Y-%m-%d')
    notes = notes[:3000]                     # 更新弹窗最多显示 2400 字；清单小一点
    tag = 'v' + to

    plans, failed = [], []
    for t in targets:
        t.load_token(optional=a.dry)          # 只看（--dry）时没有令牌也行：公开仓库能匿名读
        try:                                  # 一边连不上不影响另一边（2026-11-11：Gitee 连着 8 次握手卡住，两边都没发成）
            too_big = [p.name for p in packs if p.size > t.max_attach]
            raw, msha = t.get_file(MANIFEST)
            old = json.loads(raw.decode('utf-8-sig')) if raw else None
            if old and newer(str(old.get('latest', '0')), to):
                raise SystemExit('%s 的清单里已经是更新的 v%s，不能发更旧的 v%s' % (t.label, old['latest'], to))
            plan = {'t': t, 'old': old, 'msha': msha, 'rel': t.get_release(tag), 'empty': not t.branches(), 'too_big': too_big,
                    'urls': {p.name: t.download_url(tag, p.name) for p in packs}}
            plans.append(plan)
        except (ApiError, RuntimeError) as e:
            t.say('[错误] 读不到现在的情况，这边先不发：%s' % mask(e))
            failed.append(t)
    if not plans:
        say('[错误] 哪边都连不上，没有发布')
        return 1

    say('发布 v%s 的更新包：' % to)
    for p in packs:
        say('  %s  %.2f MB  v%s → v%s  sha256 %s…' % (p.name, p.size / 1048576, p.src, p.dst, p.sha[:16]))
    for pl in plans:
        t, old = pl['t'], pl['old']
        new = build_manifest(old, packs, to, date, notes, pl['urls'], a.full_url, a.full_note)
        say('  %s（%s）：%s发行版 %s（%s）；latest.json %s → v%s，更新包 %d 个；完整包 %s%s' % (
            t.label, t.web, '先建 README.md，' if pl['empty'] else '', tag, '已有，补传附件' if pl['rel'] else '新建',
            'v' + old['latest'] if old else '新建', to, len(new['updates']), new['full'].get('url') or '没有',
            '；超过附件上限，这边发不了：' + '、'.join(pl['too_big']) if pl['too_big'] else ''))
    say('  更新内容（%s）：\n    %s' % (date, '\n    '.join(notes.splitlines()[:12]) + ('\n    ……' if len(notes.splitlines()) > 12 else '')))
    if a.dry:
        say('（--dry：只看，不发）')
        return 0
    if not confirm(a, '以上内容会公开到 %s。' % '、'.join(pl['t'].label for pl in plans)):
        say('没有发布')
        return 1
    relay = None
    for pl in plans:
        try:
            r = publish_one(pl, packs, to, tag, date, notes, a)
            if pl['t'].key == 'github' and RELAY and a.only != 'github':
                relay = ((r or {}).get('commit') or {}).get('sha')
        except Exception as e:
            pl['t'].say('[错误] %s' % mask(e))
            failed.append(pl['t'])
    if relay and not wait_relay(relay):
        if not failed:
            say('GitHub 发好了；Gitee 转发没成功，看上面的日志链接，修好后在 GitHub 仓库的 Actions 页点「Run workflow」重跑')
            return 1
        failed.append(Gitee())
    if failed:
        say('没发完：%s。网络好一点后再跑一次，加 --only %s（已经传好的附件不会重传）' % (
            '、'.join(t.label for t in failed), failed[0].key if len(failed) == 1 else '…'))
        return 1
    say('两边都发好了' if len(plans) > 1 or relay else '%s 发好了' % plans[0]['t'].label)
    return 0


def publish_one(pl, packs, to, tag, date, notes, a):
    t = pl['t']
    if pl['too_big']:
        raise RuntimeError('附件超过 %s 的上限：%s' % (t.label, '、'.join(pl['too_big'])))
    t.ensure_init()
    rel = pl['rel'] or t.get_release(tag)
    if not rel:
        rel = t.create_release(tag, '暗黑重铸 ' + tag, notes)
        t.say('已建发行版 %s' % tag)
    rid = rel['id']
    have = {x.get('name'): x for x in t.attachments(rid)}
    urls = dict(pl['urls'])
    # 清单里记的同名文件的 SHA-256：一样才算「已经传过」（同一版本重新打包的更新包可能大小一样、内容不同）
    old_sha = {u.get('file'): u.get('sha256') for u in (pl['old'] or {}).get('updates', []) if isinstance(u, dict)}
    for p in packs:
        x = have.get(p.name)
        if x and int(x.get('size') or 0) == p.size and old_sha.get(p.name) == p.sha:
            t.say('附件 %s 已经在了' % p.name)
        else:
            if x:
                t.delete_attachment(rid, x['id'])
            j = t.upload(rid, p.name, p.data)
            t.say('已上传 %s' % p.name)
            x = j or {}
        if x.get('browser_download_url'):
            urls[p.name] = x['browser_download_url']
    for p in packs:
        t.say('不登录下载核对 %s ……' % p.name)
        ok, note = verify_download(urls[p.name], p.data)
        t.say('  %s' % note)
        if not ok:
            raise RuntimeError('附件没法正常下载：latest.json 没有改，这边的玩家不受影响。看一下 %s/releases' % t.web)
    new = build_manifest(pl['old'], packs, to, date, notes, urls, a.full_url, a.full_note)
    r = t.put_file(MANIFEST, (json.dumps(new, ensure_ascii=False, indent=1) + '\n').encode('utf-8'), '发布 ' + tag, sha=pl['msha'])
    t.say('已更新 latest.json → v%s' % to)
    try:
        st, _f, got = anon_get(t.raw_url(MANIFEST))
        t.say('  不登录读 latest.json：v%s' % json.loads(got.decode('utf-8-sig'))['latest'])
    except Exception as e:
        t.say('  不登录读 latest.json 失败（可能有缓存或网络问题，启动器会改读接口地址）：%s' % mask(e))
    return r


# ---------------------------------------------------------------- Gitee 转发（GitHub Actions）
RELAY = True                             # 默认 Gitee 由 GitHub 转发
RELAY_DIR = os.path.join(HERE, 'gitee_relay')
RELAY_FILES = {'.github/sync_gitee.py': 'sync_gitee.py', '.github/workflows/sync-gitee.yml': 'sync-gitee.yml'}


def wait_relay(sha, timeout=1200):
    """等 GitHub 上这次提交触发的转发任务跑完：成功返回 True"""
    gh = GitHub()
    gh.load_token(optional=True)
    say('[Gitee] 等 GitHub 转发（Actions）……')
    t0, seen, url = time.time(), None, ''
    while time.time() - t0 < timeout:
        try:
            j = gh.call('GET', ['actions', 'runs'], query={'head_sha': sha, 'per_page': 10}, tries=3) or {}
        except ApiError as e:
            if e.code == 403 and gh.token:
                gh.token = ''                 # 令牌没有 Actions 权限：不登录查
                continue
            say('[Gitee]   查不到转发任务的状态：%s' % mask(e))
            j = {}
        except RuntimeError as e:
            say('[Gitee]   查不到转发任务的状态：%s' % mask(e))
            j = {}
        runs = [r for r in j.get('workflow_runs') or [] if 'sync-gitee' in str(r.get('path') or r.get('name'))]
        if runs:
            r = runs[0]
            url = r.get('html_url') or url
            st = '%s/%s' % (r.get('status'), r.get('conclusion'))
            if st != seen:
                say('[Gitee]   转发任务：%s %s' % ({'queued': '排队中', 'in_progress': '运行中', 'completed': '跑完了'}.get(r.get('status'), r.get('status')),
                                                  {'success': '（成功）', 'failure': '（失败）', 'cancelled': '（取消）'}.get(r.get('conclusion'), '')))
                seen = st
            if r.get('status') == 'completed':
                if r.get('conclusion') == 'success':
                    say('[Gitee] 转发好了')
                    return True
                say('[Gitee] [错误] 转发没成功，日志：%s（修好后可以在 Actions 页点 Run workflow 重跑）' % url)
                return False
        elif time.time() - t0 > 180:
            say('[Gitee] [错误] 3 分钟了还没看到转发任务：转发装了没有（--install-relay）？Actions 是不是被关了？')
            return False
        time.sleep(10 if gh.token else 30)
    say('[Gitee] [错误] 转发跑了 %d 分钟还没完：%s' % (timeout // 60, url))
    return False


def install_relay(a):
    gh = GitHub()
    gh.load_token()
    say('把 Gitee 转发装到 %s：%s' % (gh.web, '、'.join(RELAY_FILES)))
    if not confirm(a, '会往 GitHub 仓库提交这两个文件。'):
        return 1
    last = None
    for path, local in RELAY_FILES.items():
        data = open(os.path.join(RELAY_DIR, local), 'rb').read()
        old, sha = gh.get_file(path)
        if old == data:
            gh.say('%s 没变' % path)
            continue
        try:
            last = gh.put_file(path, data, '安装 / 更新 Gitee 转发：' + path, sha=sha)
        except ApiError as e:
            if e.code in (403, 404) and 'workflows' in path:
                raise SystemExit('GitHub 不让令牌改 %s：令牌要加 Workflows 权限（Fine-grained token → Edit → + Add permissions → Workflows → Read and write）' % path)
            raise
        gh.say('已提交 %s' % path)
    if last and not a.no_wait:
        sha = ((last or {}).get('commit') or {}).get('sha')
        return 0 if wait_relay(sha) else 1
    return 0


# ---------------------------------------------------------------- 其他
def status(a, targets):
    for t in targets:
        t.load_token(optional=True)
        raw, _sha = t.get_file(MANIFEST)
        if raw:
            m = json.loads(raw.decode('utf-8-sig'))
            t.say('latest.json：v%s（%s），更新包 %d 个，完整包 %s' % (m.get('latest'), m.get('date'), len(m.get('updates', [])),
                                                         (m.get('full') or {}).get('url') or '没有'))
            for u in m.get('updates', []):
                t.say('  %s → %s  %.2f MB  %s' % (u['from'], u['to'], u['size'] / 1048576, u['url']))
        else:
            t.say('还没有 latest.json%s' % ('（仓库是空的）' if not t.branches() else ''))
        total = 0
        for r in t.releases():
            att = t.attachments(r['id'])
            size = sum(int(x.get('size') or 0) for x in att)
            total += size
            t.say('发行版 %s：%d 个附件，%.1f MB' % (r.get('tag_name'), len(att), size / 1048576))
        t.say('附件共 %.1f MB' % (total / 1048576))
    return 0


def prune(a, targets):
    for t in targets:
        t.load_token()
        raw, _sha = t.get_file(MANIFEST)
        used = set()
        if raw:
            for u in json.loads(raw.decode('utf-8-sig')).get('updates', []):
                m = re.search(r'/releases/download/([^/]+)/', str(u.get('url')))
                if m:
                    used.add(urllib.parse.unquote(m.group(1)))
        drop = [r for r in t.releases() if r.get('tag_name') not in used]
        if not drop:
            t.say('没有不用的发行版')
            continue
        t.say('清单里不用的发行版：%s' % '、'.join(r['tag_name'] for r in drop))
        if not confirm(a, '会删掉 %s 上这些发行版和它们的附件（不能恢复）。' % t.label):
            continue
        for r in drop:
            t.delete_release(r['id'])
            t.delete_tag(r['tag_name'])
            t.say('已删 %s' % r['tag_name'])
    return 0


def test(a, targets):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('test.bin', os.urandom(200000))
    data = buf.getvalue()
    tag = 'test'          # Gitee 删不了标签：固定用一个名字，最多留这一个标签
    say('测试 %s：各建一个预发行版 test，传 darkforge_test.zip（%d 字节），不登录下载核对，再删掉；不动 latest.json'
        % ('、'.join(t.label for t in targets), len(data)))
    for t in targets:
        t.load_token()
    if not confirm(a, '会在 %s 上公开建测试发行版（几分钟内删掉）。' % '、'.join(t.label for t in targets)):
        return 1
    result = {}
    for t in targets:
        try:
            result[t.label] = test_one(t, tag, data)
        except Exception as e:
            t.say('[错误] %s' % mask(e))
            result[t.label] = False
    say('测试结果：%s' % '，'.join('%s %s' % (k, '通过' if v else '没通过') for k, v in result.items()))
    return 0 if all(result.values()) else 1


def test_one(t, tag, data):
    if not t.ensure_init():
        old = [r for r in t.releases() if str(r.get('tag_name', '')).startswith('test')]
        for r in old:
            t.delete_release(r['id'])
            t.delete_tag(r['tag_name'])
            t.say('已删之前留下的测试发行版 %s' % r['tag_name'])
    t.say('不登录读 README.md ……')
    try:
        st, _f, got = anon_get(t.raw_url('README.md'))
        t.say('不登录读 raw 文件：%s' % ('正常' if got.decode('utf-8-sig').startswith('# 暗黑重铸') else '内容不对：' + got[:80].decode('utf-8', 'replace')))
    except Exception as e:
        t.say('不登录读 raw 文件失败：%s' % mask(e))
    rel = t.create_release(tag, '测试（马上删）', '启动器在线更新的测试，马上删掉', pre=True)
    rid = rel['id']
    t.say('已建测试发行版 %s，开始传附件' % tag)
    ok = False
    try:
        j = t.upload(rid, 'darkforge_test.zip', data, timeout=300)
        url = (j or {}).get('browser_download_url')
        guess = t.download_url(tag, 'darkforge_test.zip')
        t.say('附件地址：%s（%s）' % (url, '和约定的格式一样' if url == guess else '约定格式是 ' + guess))
        t.say('不登录下载核对 ……')
        ok, note = verify_download(url or guess, data)
        t.say('不登录下载：%s' % note)
    finally:
        t.delete_release(rid)
        t.delete_tag(tag)
        t.say('已删测试发行版%s' % ('和标签' if t.can_delete_tag else '（标签 test 留着，下次测试接着用）'))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('zips', nargs='*')
    ap.add_argument('--only', choices=sorted(TARGETS))
    ap.add_argument('--full-url')
    ap.add_argument('--full-note')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--allow-third-party', action='store_true')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--test', action='store_true')
    ap.add_argument('--prune', action='store_true')
    ap.add_argument('--install-relay', action='store_true')
    ap.add_argument('--no-wait', action='store_true', help='不等 Gitee 转发跑完')
    a = ap.parse_args(argv)
    if a.full_url and not a.full_url.startswith('https://'):
        raise SystemExit('--full-url 要是 https:// 开头的网址')
    if a.install_relay:
        return install_relay(a)
    if a.status or a.test or a.prune:
        targets = [TARGETS[a.only]()] if a.only else [cls() for cls in TARGETS.values()]
    else:                                 # 发布：默认只发 GitHub，Gitee 由 GitHub 转发
        targets = [TARGETS[a.only]()] if a.only else [GitHub()]
    if a.no_wait:
        global RELAY
        RELAY = False
    try:
        if a.status:
            return status(a, targets)
        if a.test:
            return test(a, targets)
        if a.prune:
            return prune(a, targets)
        if not a.zips:
            raise SystemExit(__doc__)
        return publish(a, targets)
    except (ApiError, RuntimeError) as e:
        say('[错误] %s' % mask(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
