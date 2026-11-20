# -*- coding: utf-8 -*-
"""启动器的图形界面（迁移第 3 步；以前是 gui.ps1 + webui.ps1）。页面 launcher\\ui\\ 不动，消息和以前一样：
页面 → 宿主 {action, ...}，宿主 → 页面 {type: state / changelog / toast / tab / dialog / dialogclose}。

线程：
- 窗口线程（webview.WebViewWindow.run）：WebView2、定时器（每 300 毫秒推一次状态、看后台进程要不要弹窗）。
- 操作线程（一个）：页面的点击按顺序一件一件做（和以前 webui.ps1 的队列一样，一件在等弹窗时别的排队）；弹窗在这里等页面回答。
- 运行线程：「一键启动」这类长步骤交给 launcher\\df.py 子进程（以前是 powershell launcher.ps1），逐行读输出，
  给玩家看的只留 § 开头的行、进度条（§%）和 [错误]，和以前一样。
- 后台进程弹窗（df.py 子进程、崩溃看守的 dialog.request_host_dialog）：logs\\dlg\\<id>.req.json 认领后在页面里弹，回答写进 .ans.json。
经典界面不迁（用户规则：经典界面不维护）；电脑上没有 WebView2 运行库时弹系统对话框给下载链接。"""
import datetime
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

from .. import backup, core, randomizer, win
from ..core import Rec
from ..pytool import CREATE_NO_WINDOW, child_env
from . import webview

WEBVIEW2_DOWNLOAD = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
WEB_LINKS = ['https://github.com/tamikip/hyp-launcher-ui']           # 页面能让宿主用浏览器打开的网址（别的一律不开）
PLAYER_ACTIONS = ('vanilla', 'randenemy', 'rand', 'coopvanilla', 'coop', 'update', 'checkupdate', 'autoupdate')

# 工具（名字, 说明）：顺序和以前的 $small 一样
SMALL = [
    ('游戏路径', '设置 / 修改游戏目录（包含 Game\\eldenring.exe 的那一层）'),
    ('备份存档', '把暗黑重铸存档（ER0000.rng）和角色记录（存档文件夹里的 DarkReforged\\角色记录）复制到「存档备份」文件夹'),
    ('恢复存档', '从自动备份里挑一份换回去，之后玩的进度会丢失（确认前会显示差多少）。游戏开着时会定时自动备份，间隔在下面的「定时备份」里改。只是遇到问题的话，先点「导出诊断包」'),
    ('重随设置', '用记事本打开重随规则 settings.json（敌人血量、Boss 奖励、局内难度等）'),
    ('一键重随物品', '骨灰的位置、开局装备、开局遗物只在第一次启动时抽一次，之后固定。点这里后，下次启动会重新抽一次（之后再固定）；只对之后新建的角色生效'),
    ('敌人设置', '调整敌人随机：精英怪的多少、头目会不会出现在普通敌人的位置。改完点「一键重随敌人」生效'),
    ('报告 / 日志', '打开上次重随报告和 YAFSML 日志所在位置'),
    ('导出诊断包', '出问题时点这里：把日志、配置、游戏版本和 Windows 崩溃记录打成一个 zip 放到桌面，发给帮你排查的人（不含存档）'),
    ('常见问题', '怎么重新随机敌人、怎么回退整合包版本、自动备份的存档在哪'),
    ('更新日志', '打开整合包的「更新日志.txt」：每个版本改了什么'),
    ('导入更新包', '选下载好的更新包（Darkforge_v旧_to_v新_update.zip，不用解压），只替换改了的文件；改动前自动备份，失败自动还原，你改过的设置会保留'),
    ('检查更新', '联网看看有没有新版本；有的话下载更新包并更新（只替换改了的文件，改动前自动备份，失败自动还原，你改过的设置会保留）'),
]
RANDOMIZER_TIP = '会先显示操作步骤（敌人随机要开，物品随机可开可不开）。在这里改过的设置，以后「一键重随敌人」也会沿用。'
MOD_TOOLS = [
    ('mods 文件夹', '放外观、模型、特效这类 mod（解压后带 parts、chr、sfx 等文件夹的）：一个 mod 一个文件夹，下次启动游戏自动加载，排在整合包前面（同名文件以整合包为准）。文件夹名前加 _ 就停用。整合包更新不会动它'),
    ('DLL 文件夹', '放 DLL 类的 mod（.dll；带配置文件的整个文件夹放进来）：下次启动游戏自动加载，文件名前加 _ 就停用'),
    ('自定义配置', '用记事本打开 YAFSML自定义.ini：改模组加载器的设置（比如游戏里用输入法）、按路径加 mod 或 DLL。整合包更新不会动它；改完下次启动游戏生效'),
]
COOP_TOOLS = [
    ('联机', '和朋友用 Seamless Co-op 联机（要自己下载放进整合包的 dll\\ 文件夹）：房主点「开房」，把联机码发给队友，队友点「加入」'),
    ('联机设置', '用记事本打开 Seamless Co-op 的设置文件（ersc_settings.ini）：随人数加强的血量和伤害等。联机密码开房时自动生成、队友加入时自动填，一般不用改'),
]

# 敌人设置（用户 2026-11-10）：settings.json 的 elite_share_mult / boss_in_basic_pct
ELITE_LEVELS = [('最少', 0.0, '不额外放'), ('少', 0.5, '× 0.5'), ('默认', 1.0, '× 1'), ('较多', 1.5, '× 1.5'), ('多', 2.0, '× 2'), ('很多', 3.0, '× 3')]
BOSS_LEVELS = [('关闭', 0.0, '不出现'), ('很少', 1.0, '约 1%'), ('少量', 3.0, '约 3%'), ('较多', 6.0, '约 6%'), ('很多', 10.0, '约 10%')]
ELITE_BAND_NAMES = ['前期', '利耶尼亚 / 盖利德', '王城 / 山顶', '雪原 / 圣树', 'DLC 前中期', 'DLC 后期']

GAME_PICK_HINT = '请选中游戏的 Game 文件夹（里面有 eldenring.exe）' + '\r\n' + '例如 …\\steamapps\\common\\ELDEN RING\\Game'
GAME_PICK_WRONG = ('要选的是游戏的 Game 文件夹（里面有 eldenring.exe），Steam 版一般在：' + '\r\n' +
                   '    C:\\Program Files (x86)\\Steam\\steamapps\\common\\ELDEN RING\\Game' + '\r\n' +
                   '    D:\\SteamLibrary\\steamapps\\common\\ELDEN RING\\Game（游戏装在别的盘时）' + '\r\n\r\n' +
                   '不知道装在哪：在 Steam 库里右键艾尔登法环 →「管理」→「浏览本地文件」，打开的文件夹里的 Game 就是。')
BACKUP_PICK_HELP = ('定时 = 游戏开着时自动存的（「退出游戏后」那份就是退出时的样子）；启动前 / 恢复前 = 以前的版本自动存的（定时备份攒满 5 份后自动删掉）；'
                    '存档备份 = 点「备份存档」存的。\r\n'
                    '存档和角色记录一起换回去，那之后的游戏进度会丢失。')
FAQ_TEXT = (
    "问：我想重新随机敌人怎么办？\r\n"
    "1. 点「一键重随敌人」，等它跑完（2~5 分钟，期间不要碰随机器窗口）。\r\n"
    "2. 点「一键启动（敌人随机）」开始玩。\r\n"
    "\r\n"
    "问：更新到新版本后，敌人会全部换掉吗？\r\n"
    "不会，只要旧版本的文件夹还在：第一次打开新版本时会问你要不要沿用旧版本的敌人随机结果，选「是」敌人就和之前一样。\r\n"
    "当时选了「否」又想沿用：点下面的「沿用旧版本的敌人随机」（要在重新随机化之前；已经重新随机化过就没有这个按钮）。\r\n"
    "没自动找到旧版本（比如解压到了别的地方）：点「一键启动（敌人随机）」时会让你自己选旧版本的文件夹；也可以点下面的「沿用旧版本的敌人随机」去选。\r\n"
    "\r\n"
    "问：游戏里怎么没有敌人血条？\r\n"
    "敌人头上的血条、状态条来自整合包里的敌人信息 mod，默认加载。在「工具与设置」→「游戏」里关掉过的话，打开就有了。\r\n"
    "它在少数电脑上（多见于有两块显卡的，笔记本常见：核显 + 独显）可能导致游戏无法启动或读档时闪退：遇到的话在同一个地方把它关掉。\r\n"
    "\r\n"
    "问：怎么更新到新版本？\r\n"
    "能联网的话点「检查更新」：有新版本会显示改了什么，点「现在更新」自动下载更新包并更新。\r\n"
    "自己下载的更新包：\r\n"
    "1. 下载更新包（Darkforge_v旧版本_to_v新版本_update.zip，比完整的整合包小得多），不用解压。\r\n"
    "2. 退出游戏，点「导入更新包」选它；跨了几个版本就把几个更新包一起选上，会按顺序导入。\r\n"
    "3. 更新包要从你现在的版本开始（启动器右上角写着版本号）。接不上时请下载完整的整合包。\r\n"
    "只替换改了的文件，敌人随机结果、存档和角色记录都不受影响；你改过的重随设置会保留。改动前的文件备份在整合包文件夹里的「更新备份」。\r\n"
    "\r\n"
    "问：回退版本怎么办？\r\n"
    "1. 把旧版本的压缩包解压到另一个文件夹。\r\n"
    "2. 在现在的启动器里点「恢复存档」，选一份更新之前的备份，点恢复（旧版本的启动器认不得新的定时备份，所以在这里恢复）。\r\n"
    "3. 打开旧版本的启动器，用它启动。\r\n"
    "\r\n"
    "问：精英怪太多 / 太少，或者想在普通敌人的位置遇到头目？\r\n"
    "点「敌人设置」：精英怪比例有六档；「头目出现在普通敌人位置」可以选关闭或四档多少（追忆头目不会出现在这些位置）。\r\n"
    "改完点「一键重随敌人」才会生效，已经随机好的敌人不会变。\r\n"
    "\r\n"
    "问：自动备份的存档在哪？\r\n"
    "点下面的「打开自动备份文件夹」。游戏开着时每隔一段时间（默认 10 分钟，在「工具与设置」→「存档」里改）自动存一份，"
    "退出游戏后再存一份，存档没变就不存；每份是一个压缩包，名字就是时间，只留最近 5 份。\r\n"
    "以前的版本每次启动游戏前存的备份（名字是时间的文件夹）在定时备份攒满 5 份后自动删掉，在那之前也能恢复。\r\n"
    "自己点「备份存档」存的，在整合包文件夹里的「存档备份」。\r\n"
    "\r\n"
    "手动恢复：\r\n"
    "1. 关掉游戏。\r\n"
    "2. 打开一份备份（压缩包直接双击打开），把里面的 ER0000.rng 复制到「打开存档文件夹」里那个数字文件夹中，覆盖。\r\n"
    "3. 把备份里「角色记录」文件夹中的文件复制到「打开存档文件夹」里的 DarkReforged\\角色记录，覆盖。\r\n"
    "   联机存档 ER0000.rngcoop 同样放进数字文件夹；备份的「角色记录」里的「联机」文件夹整个复制过去。\r\n"
    "   （2026-10-29 以前的备份里是 DarkReforged_*.txt、DarkReforged_once.json：去掉文件名开头的 DarkReforged_ 再放进去。）")


def _fmt_num(v, pattern='0.###'):
    """.NET 的 ToString('0.###' / '0.#', Invariant)：小数位数按格式，四舍五入（远离零），去掉多余的 0"""
    from decimal import ROUND_HALF_UP, Decimal
    places = len(pattern.split('.')[1]) if '.' in pattern else 0
    d = Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    s = format(d, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def _explorer(path):
    """explorer.exe "<文件夹>"（直接启动，不经过 shell）"""
    try:
        subprocess.Popen('explorer.exe "' + path + '"', close_fds=True)
    except OSError:
        pass


def _notepad(path):
    try:
        subprocess.Popen(['notepad.exe', path], close_fds=True)
    except OSError:
        pass


def _open_url(url):
    """系统默认浏览器打开（只给写死的 https 网址用）"""
    if str(url).startswith('https://'):
        try:
            os.startfile(url)
        except OSError:
            pass


class App:
    def __init__(self):
        self.ctx = core.Ctx(Action='gui')
        c = self.ctx
        self.L, self.P = c.LauncherDir, c.Paly
        j = os.path.join
        self.settings = j(self.L, 'reroll', 'settings.json')
        self.version_file = j(self.L, 'version.txt')
        self.last_ver_file = c.RngVersionFile
        self.old_ver_file = j(c.RngSaveRoot, 'DarkReforged_version.txt')
        self.update_result = j(self.L, 'logs', 'update_result.txt')
        self.update_check = j(self.L, 'logs', 'update_check.json')
        self.carry_declined = j(self.L, 'reroll', 'state', 'carry_declined.txt')
        self.enemy_info_choice = j(self.L, 'reroll', 'state', 'enemy_info_mod.txt')
        self.enemy_info_noted = j(self.L, 'reroll', 'state', 'enemy_info_noted.txt')
        self.dlg_dir = j(self.L, 'logs', 'dlg')
        self.gui_err_log = j(self.L, 'logs', 'gui_errors.txt')
        self.run_log = j(os.environ.get('TEMP') or self.L, 'darkforge_gui_run.log')
        self.coop_on = os.path.exists(j(self.L, 'coop_test.txt'))
        self.pack_version = ''
        try:
            self.pack_version = core.read_lines(self.version_file)[0].strip()
        except (OSError, IndexError):
            pass
        self.lock = threading.RLock()
        self.running = False
        self.player_view = False
        self.saw_error = False
        self.log_lines = []
        self.view_lines = []
        self.bar_line = -1
        self.cards = {k: {'value': '', 'accent': 'muted', 'tip': ''} for k in ('path', 'rand', 'last')}
        self.subs = {'launchV': '无敌人随机', 'launchR': '敌人随机', 'randEnemy': '换一个新种子，不启动游戏', 'randomizer': '自己配置敌人 / 物品随机'}
        self.has_hard = False
        self.update = None
        self.was_busy = False
        self.web_last = ''
        self.page_ready = False
        self.closing = False
        self.updated_note = None
        self.startup_done = False
        self.errors = []
        self.actions = queue.Queue()
        self.dialogs = {}
        self.dlg_seq = 0
        self.host_dlg_busy = False
        self.upd_proc = None
        self.win = None

    # ================================================================ 记错误（以前 gui_errors.txt 记 PowerShell 的 $Error）
    def record_error(self, e):
        self.errors.append('- ' + ''.join(traceback.format_exception_only(type(e), e)).strip() + '\r\n  ' +
                           ''.join(traceback.format_tb(e.__traceback__)[-2:]).strip().replace('\n', '\r\n  '))

    def save_errors(self):
        if not self.errors:
            return
        try:
            os.makedirs(os.path.dirname(self.gui_err_log), exist_ok=True)
            lines = ['==== ' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' 关闭启动器窗口时记下的错误（共 ' + str(len(self.errors)) +
                     ' 条，这里是最近 30 条，有的已经处理过、不影响使用）'] + self.errors[-30:]
            core.write_lines(self.gui_err_log, lines, bom=True)
        except OSError:
            pass

    # ================================================================ 读状态
    def get_game_root(self):
        """game_path.txt 第一行，Game\\eldenring.exe 在才算"""
        try:
            p = core.read_lines(self.ctx.GamePathFile)[0].strip()
        except (OSError, IndexError, UnicodeDecodeError):
            return None
        if p and os.path.isfile(os.path.join(p, 'Game', 'eldenring.exe')):
            return p
        return None

    def get_latest_random(self):
        """最近一次随机器输出（gui.ps1 自己的 Get-LatestRandom：要有 regulation.bin；看日志前 5 行）"""
        rd = self.ctx.RandomDir
        if not os.path.exists(os.path.join(rd, 'regulation.bin')):
            return None
        logs = []
        try:
            for e in os.scandir(os.path.join(rd, 'spoiler_logs')):
                if e.is_file() and re.fullmatch(r'.*_log_.*\.txt', e.name, re.I):
                    logs.append((e.stat().st_mtime_ns, e.path))
        except OSError:
            return None
        if not logs:
            return None
        mt, p = win.ps_sort_key(logs, lambda x: x[0], True)[0]
        try:
            head = core.read_text(p, 'replace').splitlines()[:5]
        except OSError:
            head = []
        opt = next((l for l in head if re.match(r'^Options and seed:', l, re.I)), None)
        merged = any(re.match(r'^Checking other mod directory \S', l, re.I) for l in head)
        return Rec(Time=datetime.datetime.fromtimestamp(mt / 1e9), HasEnemy=bool(opt and re.search(r'(^|\s)enemy(\s|$)', opt, re.I)),
                   HasItem=bool(opt and re.search(r'(^|\s)item(\s|$)', opt, re.I)), Merged=merged)

    def reroll_pack(self):
        w = ''
        try:
            w = core.read_text(self.ctx.WorldFile).strip()
        except OSError:
            pass
        return os.path.join(self.P, 'out', 'reroll' + (w if re.fullmatch(r'[a-z_]*', w) else ''))

    def update_status(self):
        """卡片（游戏路径 / 敌人随机 / 上次启动）和按钮副标题"""
        latest = self.get_latest_random()
        root = self.get_game_root()
        cards = {}
        if root:
            cards['path'] = {'value': root, 'accent': 'gold', 'tip': root}
        else:
            cards['path'] = {'value': '未设置', 'accent': 'warn', 'tip': '未设置（第一次启动时会自动检测，找不到会让你选）'}
        rs = randomizer.get_randomizer_status(self.ctx)
        subs = {'launchV': '无敌人随机', 'launchR': '敌人随机' if rs.Ok else '敌人随机 · 要先装随机器',
                'randEnemy': '换一个新种子，不启动游戏' if rs.Ok else '要先装随机器',
                'randomizer': '自己配置敌人 / 物品随机' if rs.Ok else '要先装随机器'}
        if not rs.Ok:
            cards['rand'] = {'value': '没装随机器', 'accent': 'muted',
                             'tip': '敌人随机要先装随机器（整合包不带），点「一键启动（敌人随机）」看怎么装。不装也能玩无敌人随机。'}
        elif latest and latest.Merged:
            t = latest.Time.strftime('%Y-%m-%d %H:%M')
            cards['rand'] = {'value': t + ' · 要重新随机化', 'accent': 'warn', 'tip': '随机器输出：' + t + '（旧版本合并别的包做的，玩敌人随机前会先重新随机化一次）'}
        elif latest and not latest.HasEnemy and not latest.HasItem:
            t = latest.Time.strftime('%Y-%m-%d %H:%M')
            cards['rand'] = {'value': t + ' · 没勾敌人随机', 'accent': 'warn', 'tip': '随机器输出：' + t + '（没有勾敌人随机！）'}
        elif latest:
            t = latest.Time.strftime('%Y-%m-%d %H:%M')
            what = ' + '.join(x for x in ('敌人随机' if latest.HasEnemy else '', '物品随机' if latest.HasItem else '') if x)
            cards['rand'] = {'value': t + (' · 含物品' if latest.HasItem else ''), 'accent': 'ok', 'tip': '随机器输出：' + t + '（' + what + '）'}
        else:
            cards['rand'] = {'value': '还没有', 'accent': 'muted', 'tip': '还没有随机器输出（点「一键启动（敌人随机）」会先自动随机化一次）'}
        rep = os.path.join(self.reroll_pack(), 'reroll_report.txt')
        if os.path.exists(rep):
            when = ''
            try:
                for l in core.read_text(rep, 'replace').splitlines()[:3]:
                    if l.startswith('时间：'):
                        when = l[3:]
                        break
            except OSError:
                pass
            cards['last'] = {'value': when, 'accent': 'gold', 'tip': '上次启动：' + when}
        else:
            cards['last'] = {'value': '还没启动过', 'accent': 'muted', 'tip': '还没有启动过'}
        with self.lock:
            self.cards, self.subs = cards, subs

    # ================================================================ 运行日志（页面「运行日志」）
    def log(self, text):
        """Add-Log"""
        with self.lock:
            (self.view_lines if self.player_view else self.log_lines).append(text)

    @staticmethod
    def bar_text(pct):
        p = max(0, min(100, pct))
        n = int(round(p / 10.0))
        return '■' * n + '□' * (10 - n) + ' ' + str(p) + '%'

    def on_run_line(self, l):
        with self.lock:
            if self.player_view:
                m = re.match(r'^§% (\d+)\s*$', l)
                if m:
                    if self.bar_line < 0:
                        self.view_lines.append('')
                        self.bar_line = len(self.view_lines) - 1
                    self.view_lines[self.bar_line] = '    ' + self.bar_text(int(m.group(1)))
                elif l.startswith('§ '):
                    self.view_lines.append(l[2:])
                elif '[错误]' in l:
                    self.saw_error = True
                    self.view_lines.append(l.strip())
            else:
                self.log_lines.append(l)

    # ================================================================ 状态 → 页面
    def get_update_info(self):
        c = self.read_update_check()
        if not c or str(c.get('cur')) != str(self.pack_version):
            return None
        try:
            size = float(c.get('size') or 0)
        except (TypeError, ValueError):
            size = 0.0
        return {'status': str(c.get('status') or ''), 'cur': str(c.get('cur') or ''), 'latest': str(c.get('latest') or ''), 'size': size,
                'checked': str(c.get('time') or ''), 'error': str(c.get('error') or ''), 'notes': self.update_notes_text(c, 360)}

    def get_enemy_info(self):
        try:
            if os.path.exists(self.enemy_info_choice):
                return core.read_text(self.enemy_info_choice).strip()
        except OSError:
            pass
        return ''

    def build_state(self):
        with self.lock:
            lines = list(self.view_lines if self.player_view else self.log_lines)[-300:]
            while lines and not lines[-1]:
                lines.pop()
            pct = None
            if self.player_view and 0 <= self.bar_line < len(self.view_lines):
                m = re.search(r'(\d+)%\s*$', self.view_lines[self.bar_line])
                if m:
                    pct = int(m.group(1))
            cards, subs, busy, player, err = dict(self.cards), dict(self.subs), self.running, self.player_view, self.saw_error
        rs = randomizer.get_randomizer_status(self.ctx)
        tools = ([{'name': n, 'tip': t} for n, t in SMALL] + [{'name': '打开随机器', 'tip': subs['randomizer'] + '。' + RANDOMIZER_TIP}] +
                 [{'name': n, 'tip': t} for n, t in MOD_TOOLS] + ([{'name': n, 'tip': t} for n, t in COOP_TOOLS] if self.coop_on else []))
        return {'type': 'state', 'version': self.pack_version, 'busy': busy, 'hasHard': self.has_hard,
                'randomizerOk': bool(rs.Ok), 'mode': 'rand' if rs.Ok else 'vanilla',
                'cards': cards,
                'subs': {'launchV': subs['launchV'], 'launchR': subs['launchR'], 'randEnemy': subs['randEnemy'], 'randItems': '骨灰、开局装备重抽，新角色生效'},
                'run': {'player': player, 'lines': lines, 'pct': pct, 'error': err},
                'tools': tools, 'coop': self.coop_on, 'update': self.update, 'enemyInfo': self.get_enemy_info(),
                'backupMin': backup.get_backup_interval(self.ctx), 'backupMins': list(backup.RngTimedIntervals), 'backupKeep': backup.RngTimedKeep}

    def send(self, obj):
        if self.win:
            self.win.post_json(json.dumps(obj, ensure_ascii=False, separators=(',', ':')))

    def toast(self, text, error=False, ms=None):
        m = {'type': 'toast', 'text': text}
        if error:
            m['error'] = True
        if ms:
            m['ms'] = ms
        self.send(m)

    def push_state(self, force=False):
        """每 300 毫秒（窗口线程）：变了才发；刚跑完一次重算有没有死亡以上的角色、读一次更新检查的结果"""
        if not self.win or not self.win.wv:
            return
        if self.was_busy and not self.running:
            self.refresh_has_hard()
            self.update = self.get_update_info()
        self.was_busy = self.running
        if self.upd_proc is not None and self.upd_proc.poll() is not None:
            self.upd_proc = None
            self.update = self.get_update_info()
        try:
            j = json.dumps(self.build_state(), ensure_ascii=False, separators=(',', ':'))
        except Exception as e:
            self.record_error(e)
            return
        if force or j != self.web_last:
            self.web_last = j
            self.win.post_json(j)

    def refresh_has_hard(self, then_push=True):
        """存档里有没有死亡以上难度的角色（要跑一次 Python 读存档）：放到后台线程，算完再推状态"""
        def run():
            try:
                hh = bool(self.get_high_chars())
            except Exception:
                hh = False
            if hh != self.has_hard:
                self.has_hard = hh
                if then_push and self.win:
                    self.win.invoke(self.push_state)
        threading.Thread(target=run, daemon=True).start()

    # ================================================================ 弹窗（页面里的弹层；操作线程 / 后台弹窗线程调，等页面回答）
    def dialog_ok(self):
        return bool(self.page_ready and not self.closing and self.win and self.win.wv)

    def modal(self, spec, on_op=None):
        """在页面里弹一层，等回答 {id, result（第几个按钮，-1 = 点 × 关掉）, pick, e, b}；
        on_op(op)：弹层里不关窗口的按钮点了时调，返回 'close' 就关掉这层（返回 {result: -2}）。页面没了 / 窗口在关返回 None"""
        if not self.dialog_ok():
            return None
        with self.lock:
            self.dlg_seq += 1
            did = self.dlg_seq
            q = queue.Queue()
            self.dialogs[did] = q
        spec = dict(spec, type='dialog', id=did)
        self.send(spec)
        try:
            while True:
                try:
                    kind, v = q.get(timeout=0.2)
                except queue.Empty:
                    if not self.dialog_ok():
                        return None
                    continue
                if kind == 'answer':
                    return v
                r = on_op(v) if on_op else None
                if r == 'close':
                    self.send({'type': 'dialogclose', 'id': did})
                    return {'result': -2}
        finally:
            with self.lock:
                self.dialogs.pop(did, None)

    def show_dr_dialog(self, Text, Title='暗黑重铸', Buttons=('确定',), Default=0, Cancel=-1, Icon='info'):
        """提示 / 确认框：页面能用就在页面里弹，不能用退回系统对话框"""
        if self.dialog_ok():
            a = self.modal({'kind': 'msg', 'title': Title, 'text': Text, 'buttons': list(Buttons), 'def': Default, 'cancel': Cancel, 'icon': Icon})
            if a is None:
                return Cancel
            try:
                return int(a.get('result'))
            except (TypeError, ValueError):
                return Cancel
        from .. import dialog
        return dialog.show_dr_dialog(Text, Title, Buttons, Default, Cancel, Icon)

    def show_info(self, Text, Title='暗黑重铸'):
        self.show_dr_dialog(Text, Title, ['确定'], 0, 0, 'info')

    def confirm_box(self, Text, Title):
        return self.show_dr_dialog(Text, Title, ['确定', '取消'], 0, 1, 'question') == 0

    def watch_host_dialogs(self):
        """后台进程的弹窗请求（窗口线程，每 300 毫秒）：<id>.req.json 改名成 .busy.json 认领，弹完把选了第几个写进 <id>.ans.json"""
        if self.host_dlg_busy or not os.path.isdir(self.dlg_dir):
            return
        try:
            reqs = [n for n in os.listdir(self.dlg_dir) if n.lower().endswith('.req.json')]
        except OSError:
            return
        if not reqs:
            return
        f = os.path.join(self.dlg_dir, reqs[0])
        busy = f[:-9] + '.busy.json'
        ans = f[:-9] + '.ans.json'
        try:
            os.rename(f, busy)                          # 后台进程等不及已经自己弹了
        except OSError:
            return
        self.host_dlg_busy = True

        def run():
            try:
                q = json.loads(core.read_text(busy))
                os.remove(busy)
                self.win.invoke(self.win.bring_front)
                r = self.show_dr_dialog(str(q.get('text') or ''), str(q.get('title') or ''), [str(x) for x in (q.get('buttons') or [])],
                                        int(q.get('def') or 0), int(q.get('cancel') if q.get('cancel') is not None else -1), str(q.get('icon') or 'info'))
                with open(ans + '.tmp', 'w', encoding='utf-8', newline='') as fh:
                    fh.write(str(int(r)))
                os.rename(ans + '.tmp', ans)
            except Exception as e:
                self.record_error(e)
                try:
                    os.remove(busy)
                except OSError:
                    pass
            finally:
                self.host_dlg_busy = False
        threading.Thread(target=run, daemon=True).start()

    # ================================================================ 后台跑 df.py（以前 Start-LauncherRun 跑 powershell launcher.ps1）
    def python_exe(self):
        p = os.path.join(self.L, 'python', 'python.exe')
        return p if os.path.isfile(p) else sys.executable

    def set_busy(self, busy):
        self.running = busy
        if not busy:
            self.update_status()

    def start_run(self, title, steps, after=None):
        """steps：[(失败了就不做后面的?, [动作, 参数…])]；after：跑完后（在操作线程上）要做的事"""
        if self.running:
            return
        with self.lock:
            self.log_lines, self.view_lines, self.bar_line = [], [], -1
            self.player_view = any(a and a[0] in PLAYER_ACTIONS for _, a in steps)
            self.saw_error = False
        self.log('=== ' + title + ' ===')
        self.set_busy(True)
        threading.Thread(target=self._run_steps, args=(steps, after), daemon=True).start()

    def _run_steps(self, steps, after):
        env = child_env({'DARKFORGE_DLG_DIR': self.dlg_dir, 'DARKFORGE_GUI_PID': str(os.getpid())})
        try:
            logf = open(self.run_log, 'w', encoding='utf-8', newline='')
        except OSError:
            logf = None
        try:
            for stop, args in steps:
                cmd = [self.python_exe(), '-X', 'utf8', os.path.join(self.L, 'df.py')] + list(args)
                try:
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=self.L,
                                         env=env, creationflags=CREATE_NO_WINDOW)
                except OSError as e:
                    self.on_run_line('  [错误] 启动不了：' + str(e))
                    break
                for raw in iter(p.stdout.readline, b''):
                    l = raw.decode('utf-8', 'replace').rstrip('\r\n')
                    if logf:
                        try:
                            logf.write(l + '\n')
                            logf.flush()
                        except OSError:
                            pass
                    self.on_run_line(l)
                code = p.wait()
                if stop and code != 0:
                    break
        finally:
            if logf:
                logf.close()
            if self.player_view and self.saw_error:
                self.log('（完整的运行输出在「报告 / 日志」打开的 logs 文件夹里，出问题时点「导出诊断包」发过来）')
            self.log('=== 完成 ===')
            self.set_busy(False)
            if after:
                self.actions.put(('_call', after))
            if self.win:
                self.win.invoke(self.push_state)

    # ================================================================ 游戏进程
    def get_game_proc_text(self):
        boot = None
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.GetTickCount64.restype = ctypes.c_ulonglong
            boot = datetime.datetime.now() - datetime.timedelta(milliseconds=k.GetTickCount64())
        except Exception:
            pass
        lines = []
        for pid in win.find_pids('eldenring'):
            with win.Proc(pid) as p:
                start = p.start_time()
                path = p.path()
            hw = win.main_window(pid)
            resp = '有响应'
            if hw:
                try:
                    import ctypes
                    resp = '无响应' if ctypes.windll.user32.IsHungAppWindow(ctypes.c_void_p(hw)) else '有响应'
                except Exception:
                    resp = '未知'
            lines.append('  进程号 ' + str(pid) + '，启动于 ' + (start.strftime('%m-%d %H:%M:%S') if start else '未知') + '，' +
                         ('有窗口' if hw else '没有窗口（后台）') + '，' + resp + '\r\n  路径：' + (path if path else '读不到（可能是管理员权限启动的）'))
        if boot:
            lines.append('  （电脑本次开机时间：' + boot.strftime('%m-%d %H:%M:%S') + '）')
        return '\r\n'.join(lines)

    def confirm_game_closed(self, Why):
        """游戏没在运行（或已按玩家确认强制结束）返回 True"""
        if not win.find_pids('eldenring'):
            return True
        msg = ('检测到 eldenring.exe 还在运行：\r\n\r\n' + self.get_game_proc_text() + '\r\n\r\n' + Why + '\r\n\r\n' +
               '如果游戏其实已经关了（崩溃后残留在后台、看不到窗口等），点「是」强制结束这个进程再继续；\r\n' +
               '正在玩的话点「否」，先在游戏里正常退出（系统 → 退出游戏）。强制结束正在玩的游戏，没存档的进度会丢。')
        if self.show_dr_dialog(msg, '暗黑重铸 · 游戏还在运行', ['是', '否'], 1, 1, 'warn') != 0:
            return False
        self.log('强制结束 eldenring.exe：' + ', '.join(str(p) for p in win.find_pids('eldenring')))
        for pid in win.find_pids('eldenring'):
            win.kill_pid(pid)
        for _ in range(20):
            if not win.find_pids('eldenring'):
                return True
            time.sleep(0.5)
        self.show_info('没能结束 eldenring.exe（可能是以管理员身份启动的）。\r\n\r\n' +
                       '请打开任务管理器（Ctrl+Shift+Esc）→「详细信息」，找到 eldenring.exe 右键「结束任务」；还不行就重启电脑。')
        return False

    # ================================================================ 版本
    def get_ver(self, path):
        try:
            return core.ps_version(core.read_lines(path)[0].strip())
        except (OSError, IndexError):
            return None

    @staticmethod
    def ver_str(v):
        return '.'.join(str(x) for x in v)

    def get_version_state(self):
        cur = self.get_ver(self.version_file)
        if not cur:
            return Rec(Kind='same')
        last = self.get_ver(self.last_ver_file) or self.get_ver(self.old_ver_file)
        if last and last == cur:
            return Rec(Kind='same', Cur=cur)
        if last and last > cur:
            return Rec(Kind='downgrade', Cur=cur, Last=last)
        if not last:
            return Rec(Kind='fresh', Cur=cur)
        return Rec(Kind='upgrade', Cur=cur, Last=last)

    def downgrade_text(self, v):
        return ('这台电脑上已经用过更新的整合包 ' + self.ver_str(v.Last) + '，现在打开的是旧版本 ' + self.ver_str(v.Cur) + '。\r\n\r\n' +
                '旧版本可能看不懂新版本记下的角色记录（装备、锁定、难度等），用它启动可能出错。\r\n\r\n' +
                '强烈建议关掉这个窗口，改用新版本的整合包启动。')

    def show_version_notice(self):
        v = self.get_version_state()
        if v.Kind in ('fresh', 'upgrade'):
            os.makedirs(self.ctx.RngDataDir, exist_ok=True)
        if v.Kind == 'fresh':
            core.write_text(self.last_ver_file, self.ver_str(v.Cur) + '\r\n')
        elif v.Kind == 'upgrade':
            core.write_text(self.last_ver_file, self.ver_str(v.Cur) + '\r\n')
            self.updated_note = '已更新到 v' + self.ver_str(v.Cur) + '（原来是 v' + self.ver_str(v.Last) + '），改了什么见「更新日志」'
            self.log(self.updated_note)
        elif v.Kind == 'downgrade':
            self.show_dr_dialog(self.downgrade_text(v), '版本比这台电脑上用过的旧', ['我已了解'], 0, 0, 'warn')

    def test_version_change(self):
        v = self.get_version_state()
        if v.Kind == 'downgrade':
            return self.show_dr_dialog(self.downgrade_text(v) + '\r\n仍然要用旧版本启动吗？', '版本比这台电脑上用过的旧', ['是', '否'], 1, 1, 'warn') == 0
        if v.Kind in ('upgrade', 'fresh'):
            self.show_version_notice()
        return True

    # ================================================================ 游戏路径
    def ensure_game_root(self):
        """先自动检测（只有一个候选时会记住），还没有就弹选择框"""
        if self.get_game_root():
            return True
        from .. import gamepath
        try:
            gamepath.resolve_game_root(self.ctx, True)
        except Exception as e:
            self.record_error(e)
        if self.get_game_root():
            return True
        return self.select_game_root('没有自动找到游戏，请手动选一下。')

    def game_pick_start(self):
        cur = self.get_game_root()
        if cur:
            return os.path.join(cur, 'Game')
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Valve\\Steam') as k:
                sp = winreg.QueryValueEx(k, 'SteamPath')[0]
            c = os.path.abspath(os.path.join(sp, 'steamapps', 'common'))
            if os.path.isdir(c):
                return c
        except OSError:
            pass
        return None

    def select_game_root(self, Why=''):
        """手动选：选中 Game 文件夹就记它的上一层；选成 ELDEN RING 那一层也认。选错了说明一下再让选，取消才算没选"""
        while True:
            start = self.game_pick_start()
            path = win.pick_folder((Why + '\r\n' if Why else '') + GAME_PICK_HINT, start if start and os.path.isdir(start) else None,
                                   self.win.hwnd if self.win else None)
            if not path:
                return False
            path = path.rstrip('\\')
            root = None
            if os.path.exists(os.path.join(path, 'eldenring.exe')):
                root = os.path.dirname(path)
            elif os.path.exists(os.path.join(path, 'Game', 'eldenring.exe')):
                root = path
            if root:
                core.write_text(self.ctx.GamePathFile, root + '\r\n')
                self.ctx.CacheGameRoot = root
                self.log('游戏路径已设为：' + root)
                self.update_status()
                return True
            self.show_info('这个文件夹里没有 eldenring.exe：' + '\r\n' + path + '\r\n\r\n' + GAME_PICK_WRONG, '游戏路径')

    def before_launch(self):
        if not self.confirm_game_closed('启动前要重新生成重随包，游戏开着时不能覆盖它正在用的文件。'):
            return False
        if not self.ensure_game_root():
            return False
        return self.test_version_change()

    # ================================================================ 死亡以上难度
    def test_boss_auto(self):
        try:
            bm = json.loads(core.read_text(self.settings)).get('boss_mods')
        except (OSError, ValueError, AttributeError):
            return False
        if not isinstance(bm, dict) or str(bm.get('mode')) != 'auto' or not bm.get('mods'):
            return False
        for name, val in (bm.get('mods') or {}).items():
            if not name.startswith('_') and val is True and os.path.exists(os.path.join(self.L, 'reroll', 'data', 'bossmods', name, 'files')):
                return True
        return False

    def get_save_slot_names(self, File='ER0000.rng'):
        """存档（最近改过的那份）里各格的角色名 {格子: 名字}；读不了返回 None（不核对）"""
        saves = [f for f in backup.get_rng_save_files(self.ctx) if f.Name == File]
        if not saves:
            return {}
        save = max(saves, key=lambda f: os.stat(f.FullName).st_mtime_ns)
        code = ('import sys, json; sys.path.insert(0, sys.argv[1]); import erlib; '
                'print(json.dumps({str(k): v[0] for k, v in erlib.save_profiles(sys.argv[2]).items()}))')
        try:
            r = subprocess.run([self.python_exe(), '-X', 'utf8', '-c', code, os.path.join(self.L, 'reroll'), save.FullName], capture_output=True,
                               stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, env=child_env(), timeout=60)
            out = [l for l in r.stdout.decode('utf-8', 'replace').splitlines() if l.strip()]
            return {int(k): str(v) for k, v in json.loads(out[-1]).items()}
        except Exception:
            return None

    def get_high_chars(self, Coop=False):
        rows = []
        d = os.path.join(self.ctx.RngRecordDir, '联机') if Coop else self.ctx.RngRecordDir
        slots, rec = os.path.join(d, 'boss_slots.txt'), os.path.join(d, 'boss_mode.txt')
        try:
            if os.path.exists(slots):
                for l in core.read_lines(slots, 'replace'):
                    f = l.split('\t')
                    if not l.startswith('#') and len(f) >= 4 and f[1] == '1':
                        rows.append(Rec(Slot=int(f[0]), Name=f[3]))
            elif os.path.exists(rec):
                kv = {}
                for l in core.read_lines(rec, 'replace'):
                    i = l.find('\t')
                    if i > 0:
                        kv[l[:i]] = l[i + 1:]
                if kv.get('high') == '1' and kv.get('name'):
                    rows.append(Rec(Slot=int(kv.get('slot') or 0), Name=kv['name']))
        except (OSError, ValueError):
            return []
        names = self.get_save_slot_names(backup.RngCoopSave if Coop else 'ER0000.rng')
        if names is None:
            return rows
        out = []
        for r in rows:
            if r.Slot in names and names[r.Slot] == r.Name:
                out.append(r)
                continue
            k = next((k for k in names if names[k] == r.Name), None)
            if k is not None:
                out.append(Rec(Slot=int(k), Name=r.Name))
        uniq = {}
        for r in sorted(out, key=lambda x: x.Slot):
            uniq.setdefault(r.Slot, r)
        return list(uniq.values())

    @staticmethod
    def who_text(hi):
        return '、'.join('「' + r.Name + '」（第 ' + str(r.Slot + 1) + ' 格）' for r in hi)

    def ask_boss_world(self):
        """'' = 功能没开（不传）、'high' / 'low'、None = 取消启动"""
        if not self.test_boss_auto():
            return ''
        hi = self.get_high_chars()
        if not hi:
            return 'low'
        who = self.who_text(hi)
        msg = ('存档里有死亡以上难度的角色：' + who + '\r\n\r\n要以死亡以上难度启动吗？\r\n\r\n' +
               '· 玩上面这些角色：选「死亡以上难度」。\r\n' +
               '· 玩别的角色：选「普通难度」。\r\n\r\n' +
               '进游戏后读取的角色和这里选的难度对不上时，角色周围会出现屏障、不能传送，要重启游戏重新选择。')
        r = self.show_dr_dialog(msg, '暗黑重铸 · 选择难度', ['死亡以上难度', '普通难度', '取消'], 0, 2, 'question')
        if r == 0:
            self.show_info('进入游戏后，请读取死亡以上难度的角色：' + who + '。', '暗黑重铸 · 死亡以上难度')
            return 'high'
        if r == 1:
            return 'low'
        return None

    @staticmethod
    def boss_arg(bw):
        return ['--boss-world', bw] if bw else []

    def ask_coop_world(self):
        if not self.test_boss_auto():
            return ''
        hi = self.get_high_chars(True)
        if not hi:
            msg = ('联机存档里还没有死亡以上难度的角色，这次只能以普通难度开房。\r\n\r\n' +
                   '要开死亡以上难度的房间，房主要先有一个死亡以上难度的联机角色（队友不需要）。')
            return 'low' if self.show_dr_dialog(msg, '暗黑重铸 · 联机难度', ['普通难度开房', '取消'], 0, 1, 'info') == 0 else None
        high = False
        try:
            rec = os.path.join(self.ctx.RngRecordDir, '联机', 'boss_mode.txt')
            if os.path.exists(rec):
                high = any(re.match(r'^high\t1', l, re.I) for l in core.read_lines(rec, 'replace'))
        except OSError:
            pass
        msg = ('这次联机用哪种难度的世界？\r\n\r\n' +
               '· 死亡以上难度：加载 Boss 改版。进游戏后房主请读取死亡以上难度的联机角色：' + self.who_text(hi) + '。队友用什么角色都可以。\r\n' +
               '· 普通难度：原版 Boss。\r\n\r\n' +
               '选的世界写进联机码，队友点「加入」时自动用同一个。')
        r = self.show_dr_dialog(msg, '暗黑重铸 · 联机难度', ['死亡以上难度', '普通难度', '取消'], 0 if high else 1, 2, 'question')
        return {0: 'high', 1: 'low'}.get(r)

    def ask_missing_hi_world(self, Pack=''):
        """死亡以上难度缺配套的世界：返回启动前要先做的步骤 'randhi' / 'randenemy'、'' = 已经有了、None = 取消"""
        lo = os.path.join(Pack, 'randomizer') if Pack else self.ctx.RandomDir
        hi = os.path.join(Pack, 'randomizer_hi') if Pack else self.ctx.RandomHiDir
        if randomizer.get_rand_hi_world(self.ctx, randomizer.get_boss_fixed_ids(self.ctx), hi, lo):
            return ''
        info = randomizer.get_random_info(self.ctx, lo)
        keep = bool(info and info.PresetSeed)
        if keep:
            how = '「现在生成」：约 1~5 分钟，完成后直接启动，普通难度的敌人不变。'
        else:
            how = ('这份敌人随机结果是旧版本做的，没法单独补做。「重新随机化」：约 2~10 分钟，完成后直接启动，两种难度的敌人都会换一批' +
                   ('，道具位置和商人货架也会重新打乱。' if info and info.HasItem else '。'))
        msg = ('死亡以上难度要用单独生成的一份敌人世界，现在还没有（从旧版本更新、沿用了旧的敌人随机结果时常见）。\r\n\r\n' +
               '没有它，部分追忆 Boss 不在原来的位置，改版 Boss 的场地内容也不会生效，所以要先生成才能启动。\r\n\r\n' + how + '\r\n\r\n' +
               '⚠ 随机器窗口会自动打开、自动操作、完成后自动关闭：这期间不要点随机器窗口，也不要关掉它。')
        if self.show_dr_dialog(msg, '暗黑重铸 · 死亡以上难度', ['现在生成' if keep else '重新随机化', '取消'], 0, 1, 'question') != 0:
            return None
        if win.find_pids('EldenRingRandomizer'):
            self.show_info('随机器已经开着，先把它关掉。')
            return None
        return 'randhi' if keep else 'randenemy'

    # ================================================================ 随机器 / 沿用旧版本
    def confirm_randomizer(self):
        rs = randomizer.get_randomizer_status(self.ctx)
        if rs.Ok:
            return True
        r = self.show_dr_dialog(rs.Msg, '暗黑重铸 · 要先装随机器', ['打开下载页', '打开 randomizer 文件夹', '关闭'], 0, 2, 'info')
        if r == 0:
            _open_url(randomizer.RandomizerUrl)
        if r == 1:
            os.makedirs(self.ctx.RandomDir, exist_ok=True)
            _explorer(self.ctx.RandomDir)
        return False

    def save_carry_declined(self, What):
        try:
            os.makedirs(os.path.dirname(self.carry_declined), exist_ok=True)
            core.write_text(self.carry_declined, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' 不沿用 ' + What + '\r\n')
        except OSError:
            pass

    def select_old_pack(self):
        start = os.path.dirname(os.path.abspath(self.P).rstrip('\\'))
        d = win.pick_folder('选择旧版本的整合包文件夹（里面有 launcher、randomizer 的那一层；选包着它的那一层也行）', start, self.win.hwnd if self.win else None)
        if not d:
            return None
        pack = randomizer.resolve_pack_dir(self.ctx, d)
        if core.ieq(pack, os.path.abspath(self.P).rstrip('\\')):
            self.show_info('选的是现在这个整合包自己（' + pack + '）。要选的是旧版本解压出来的那个文件夹。')
            return None
        c = randomizer.get_old_random(self.ctx, pack)
        if isinstance(c, str):
            self.show_info('不能沿用这个文件夹里的敌人随机结果：' + '\r\n  ' + pack + '\r\n\r\n' + c)
            return None
        return c

    def ask_pick_old_random(self):
        msg = ('这个整合包里还没有敌人随机结果，自动也没找到旧版本的（记下的整合包、旁边的文件夹、桌面 / 下载 / 文档、游戏目录、各盘根目录往下两层都找过）。\r\n\r\n' +
               '你已经有暗黑重铸存档：如果是从旧版本更新过来接着玩，重新随机化后敌人会全部换掉。\r\n\r\n' +
               '旧版本的文件夹还在的话，点「选择旧版本文件夹」选它，复制过来后敌人和之前一模一样。\r\n' +
               '确定不要沿用（新开一局、或者就想换一批敌人），点「重新随机化」，之后不再问。')
        while True:
            r = self.show_dr_dialog(msg, '沿用旧版本的敌人随机结果', ['选择旧版本文件夹', '重新随机化', '取消'], 0, 2, 'question')
            if r == 1:
                self.save_carry_declined('（没找到旧版本，玩家选重新随机化）')
                return None
            if r != 0:
                return 'cancel'
            c = self.select_old_pack()
            if c:
                return c

    def ask_old_random(self, Launching=False):
        if not randomizer.get_randomizer_status(self.ctx).Ok:
            return None
        if os.path.exists(self.carry_declined) or not randomizer.test_need_old_random(self.ctx):
            return None
        found = randomizer.find_old_randoms(self.ctx)
        c = found[0] if found else None
        if not c:
            if Launching and backup.get_rng_save_files(self.ctx):
                return self.ask_pick_old_random()
            return None
        msg = ('在旧版本的整合包里找到了敌人随机结果：\r\n' +
               '  文件夹：' + c.Pack + '（v' + str(c.Version) + '）\r\n' +
               '  随机化于：' + c.Time.strftime('%Y-%m-%d %H:%M') + ('，种子 ' + str(c.Seed) if c.Seed else '') + '\r\n\r\n' +
               '要沿用吗？\r\n\r\n' +
               '是：复制过来（约 100 MB，几秒钟），敌人和之前一模一样，接着玩不受影响。\r\n\r\n' +
               '否：第一次用「一键启动（敌人随机）」时会重新随机化一次，敌人会全部换掉。之后不再问（想沿用可以在「常见问题」里点「沿用旧版本的敌人随机」）。')
        r = self.show_dr_dialog(msg, '沿用旧版本的敌人随机结果', ['是', '否'], 0, -1, 'question')
        if r == 0:
            return c
        if r != 1:
            return 'cancel' if Launching else None
        self.save_carry_declined(c.Pack)
        return None

    @staticmethod
    def carry_call(c):
        return ['carryrand', '--from-pack', c.Pack]

    def confirm_first_randomize(self, Merged):
        o = randomizer.get_randomize_options(self.ctx)
        why = ('现在的敌人随机结果是旧版本合并别的包做的，带着那个包的参数，' if Merged else
               '这个文件夹里还没有敌人随机的结果（randomizer 文件夹里没有 regulation.bin 或随机器日志），')
        msg = (why + '这次会先自动随机化一次敌人（约 1~5 分钟），完成后直接启动游戏。\r\n\r\n' +
               '⚠ 随机器窗口会自动打开、自动操作、完成后自动关闭：这期间不要点随机器窗口，也不要关掉它。\r\n\r\n' +
               '随机器设置：' + str(o.From) + '\r\n' +
               ('\r\n这份设置开着物品随机：法术祷告、道具、材料、锻造石的位置和商人货架也会打乱（原版武器防具护符整合包照样换成未鉴定物品）。\r\n' if o.HasItem else '') +
               '\r\n现在开始吗？')
        return self.confirm_box(msg, '第一次玩敌人随机')

    # ================================================================ 按钮：启动 / 重随 / 打开随机器
    def on_launch_vanilla(self):
        if not self.before_launch():
            return
        bw = self.ask_boss_world()
        if bw is None:
            return
        self.start_run('启动 · 无敌人随机', [(False, ['vanilla'] + self.boss_arg(bw))])

    def on_launch_rand(self):
        if not self.confirm_randomizer():
            return
        latest = self.get_latest_random()
        if not latest or latest.Merged:
            if win.find_pids('EldenRingRandomizer'):
                self.show_info('随机器已经开着，先把它关掉。')
                return
            if not self.before_launch():
                return
            c = self.ask_old_random(True)
            if isinstance(c, str):
                return
            bw = self.ask_boss_world()
            if bw is None:
                return
            if c:
                step = self.ask_missing_hi_world(c.Pack) if bw == 'high' else ''
                if step is None:
                    return
                if step == 'randenemy':                  # 重新随机化就不用先沿用了
                    self.start_run('重随敌人 + 启动 · 敌人随机', [(True, ['randenemy']), (False, ['rand'] + self.boss_arg(bw))])
                    return
                steps = [(True, self.carry_call(c))] + ([(True, [step])] if step else []) + [(False, ['rand'] + self.boss_arg(bw))]
                self.start_run('沿用旧版本的敌人随机结果 + 启动 · 敌人随机', steps)
                return
            if not self.confirm_first_randomize(bool(latest)):
                return
            self.start_run('重随敌人 + 启动 · 敌人随机', [(True, ['randenemy']), (False, ['rand'] + self.boss_arg(bw))])
            return
        if not latest.HasEnemy and not latest.HasItem:
            if not self.confirm_box('最近一次随机化没有勾选敌人随机，这样启动和“无敌人随机”差不多。仍然启动吗？', '提示'):
                return
        if not self.before_launch():
            return
        bw = self.ask_boss_world()
        if bw is None:
            return
        step = self.ask_missing_hi_world() if bw == 'high' else ''
        if step is None:
            return
        if step:
            self.start_run('生成死亡以上难度的世界 + 启动 · 敌人随机', [(True, [step]), (False, ['rand'] + self.boss_arg(bw))])
            return
        self.start_run('启动 · 敌人随机', [(False, ['rand'] + self.boss_arg(bw))])

    def on_rand_enemy(self):
        if not self.confirm_randomizer():
            return
        if not self.confirm_game_closed('重随敌人要在游戏关闭后做。'):
            return
        if win.find_pids('EldenRingRandomizer'):
            self.show_info('随机器已经开着，先把它关掉再点一键重随敌人。')
            return
        if not self.get_game_root() and not self.select_game_root('随机器要读游戏文件，先选一下游戏路径。'):
            return
        o = randomizer.get_randomize_options(self.ctx)
        warn = ''
        if o.HasItem:
            warn += '\r\n这份设置开着物品随机：法术祷告、道具、材料、锻造石的位置和商人货架也会打乱（原版武器防具护符整合包照样换成未鉴定物品）。\r\n'
        msg = ('⚠ 随机器窗口会自动打开、自动点「随机化敌人」、完成后自动关闭。\r\n' +
               '    这期间不要点随机器窗口里的任何东西，也不要关掉它（大约 1~5 分钟）。\r\n\r\n' +
               '换一个新种子重新随机化敌人，不启动游戏。\r\n' +
               '随机器设置：' + str(o.From) + '\r\n' + warn + '\r\n' +
               '· 想改随机器设置（难度、DLC、Boss 是否混合等）：点「打开随机器，自己配置」改好；以后一键重随都按你上一次的设置。\r\n' +
               '· 完成后点「一键启动（敌人随机）」玩。旧的随机结果会被覆盖。\r\n\r\n' +
               '现在开始吗？')
        if not self.confirm_box(msg, '一键重随敌人'):
            return
        self.start_run('一键重随敌人', [(False, ['randenemy'])])

    def on_randomizer(self):
        if not self.confirm_randomizer():
            return
        if not randomizer.test_dot_net8(self.ctx):
            self.show_info(randomizer.get_dot_net8_msg(self.ctx))
            _open_url(randomizer.DotNet8Url)
            return
        if win.find_pids('EldenRingRandomizer'):
            self.show_info('随机器已经开着。')
            return
        msg = ('在随机器窗口里这样做：\r\n' +
               '1. 第一次使用：点右下的「选择游戏exe启动文件」，选游戏的 eldenring.exe。\r\n' +
               '2. 「合并其它MOD」留空（整合包直接用原版，不合并别的包；以前填过的已经自动清掉）。\r\n' +
               '3. 顶部的「敌人随机」：勾选，点进去按喜好调整；「DLC设置」「杂项设置」也可以按喜好改。\r\n' +
               '    「自定义敌人」启动器已经勾好，不要取消（追忆 Boss 只在追忆之间换、按地区控制精英比例都靠它）。\r\n' +
               '4. 顶部的「物品随机」：可开可不开。开了会打乱法术祷告、道具、材料、锻造石的位置和商人货架；\r\n' +
               '    原版武器、防具、护符整合包照样换成未鉴定物品，Boss 奖励、未鉴定掉落、暗黑商店不受影响。\r\n' +
               '    关键道具（钥匙、大卢恩等）要不要打乱，看「物品随机」里关键道具那一项。\r\n' +
               '5. 点右下的「随机化敌人」（开了物品随机时按钮写的是「随机化物品与敌人」），\r\n' +
               '    想要新的随机结果，点之前先勾上「重roll种子」（不勾会沿用上次的种子，敌人和上次一模一样）；\r\n' +
               '    等提示完成后关掉随机器。不要点随机器里的「启动游戏」。\r\n' +
               '6. 回到这里，点「一键启动（敌人随机）」。\r\n\r\n' +
               '点「确定」打开随机器。')
        if not self.confirm_box(msg, '打开随机器'):
            return
        root = self.get_game_root()
        note = randomizer.reset_rand_mod(self.ctx, os.path.join(root, 'Game', 'eldenring.exe') if root else '')
        try:
            randomizer._start_randomizer(self.ctx)
        except OSError as e:
            self.show_info('打不开随机器：' + str(e))
            return
        self.log('已打开随机器。')
        if note:
            self.log(note)

    # ================================================================ 工具
    def on_backup(self):
        saves = backup.get_rng_save_files(self.ctx)
        if not saves:
            self.show_info('没有找到暗黑重铸存档（' + self.ctx.RngSaveRoot + '\\<SteamID>\\ER0000.rng，联机的是 ER0000.rngcoop）。')
            return
        records = backup.get_rng_record_files(self.ctx)
        dst = os.path.join(self.P, '存档备份', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        for s in saves:
            d = os.path.join(dst, s.Directory.Name)
            os.makedirs(d, exist_ok=True)
            shutil.copy2(s.FullName, d)
        if records:
            rd = os.path.join(dst, '角色记录')
            os.makedirs(rd, exist_ok=True)
            for f in records:
                backup.copy_rng_record(f, rd)
        self.log('存档已备份到：' + dst + '（' + str(len(saves)) + ' 个存档 + ' + str(len(records)) + ' 个角色记录）')
        backup.add_rng_ops_log(self.ctx, '手动备份（「备份存档」按钮）：存档 ' + str(len(saves)) + ' 个、角色记录 ' + str(len(records)) + ' 个 → ' + dst)
        self.show_info('已备份到：\r\n' + dst + '\r\n\r\n要换回来时点「恢复存档」，选这份。')
        _explorer(dst)

    @staticmethod
    def backup_text(b):
        what = []
        if b.Saves and b.Saves > 0:
            what.append('存档 ' + str(b.Saves) + ' 个')
        if b.Records and b.Records > 0:
            what.append('角色记录 ' + str(b.Records) + ' 个')
        return '%s   %s%s   （%s）' % (b.Time.strftime('%Y-%m-%d %H:%M:%S'), b.Tag, (' · ' + b.Mode) if b.Mode else '', ' + '.join(what))

    def restore_diff_lines(self, b):
        try:
            with backup.backup_as_dir(b) as d:          # 定时备份是压缩包：先解到临时文件夹再比
                r = subprocess.run([self.python_exe(), '-X', 'utf8', os.path.join(self.L, 'reroll', 'savediff.py'), d, self.ctx.RngSaveRoot],
                                   capture_output=True, stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, env=child_env(), timeout=120)
            if r.returncode != 0:
                return []
            out = [l for l in r.stdout.decode('utf-8', 'replace').splitlines() if l.strip()]
            return [str(x) for x in json.loads(out[-1])]
        except Exception:
            return []

    def restore_warn_text(self, b):
        diff = self.restore_diff_lines(b)
        what = ('和现在相比：\r\n' + '\r\n'.join('    ' + x for x in diff)) if diff else '（读不出这份备份和现在差多少）'
        return ('存档和角色记录都会换成这份备份，备份之后玩的进度会丢失：\r\n\r\n    ' + self.backup_text(b) + '\r\n\r\n' + what + '\r\n\r\n' +
                '现在的样子不会另外备份：恢复错了想换回来，选最新的那份「定时 · 退出游戏后」备份（就是上次退出游戏时的样子）。'
                '只是遇到问题的话，先点「导出诊断包」，不用恢复。')

    def invoke_restore(self, pick):
        done = backup.restore_rng_backup(self.ctx, pick) or []
        self.log('已恢复（' + '、'.join(done) + '）：' + self.backup_text(pick))
        self.show_info('已恢复：' + '、'.join(done) + '\r\n' + self.backup_text(pick))

    def show_backup_pick(self, items):
        a = self.modal({'kind': 'pick', 'title': '恢复存档：手动选择备份', 'icon': '', 'text': BACKUP_PICK_HELP,
                        'items': [self.backup_text(b) for b in items], 'sel': 0, 'buttons': ['恢复选中的这份', '取消'], 'def': 0, 'cancel': 1})
        if not a or a.get('result') != 0 or a.get('pick') is None:
            return -1
        i = int(a['pick'])
        return i if 0 <= i < len(items) else -1

    def on_restore(self):
        if not self.confirm_game_closed('恢复存档要在游戏关闭后做。'):
            return
        items = [b for b in backup.get_rng_backups(self.ctx, os.path.join(self.P, '存档备份')) if b.Saves and b.Saves > 0]
        if not items:
            self.show_info('没有找到可以恢复的备份。' + '\r\n' + '（游戏开着时会定时自动备份到 ' + self.ctx.RngBackupDir + '）')
            return
        # 以前先问「恢复到上次启动前」：2026-11-19 起没有启动前备份了（定时备份），直接列出来挑
        i = self.show_backup_pick(items)
        if i < 0:
            return
        pick = items[i]
        if self.show_dr_dialog(self.restore_warn_text(pick), '确认恢复存档', ['确认恢复', '取消'], 1, 1, 'warn') != 0:
            return
        self.invoke_restore(pick)

    def on_report(self):
        rep = os.path.join(self.reroll_pack(), 'reroll_report.txt')
        if os.path.exists(rep):
            _notepad(rep)
        _explorer(os.path.join(self.ctx.YafDir, 'log'))
        ld = os.path.join(self.L, 'logs')
        if os.path.exists(ld):
            _explorer(ld)

    def on_once_reset(self):
        msg = ('骨灰的位置、职业的开局装备、开局遗物只在第一次启动时抽一次，之后一直固定。\r\n\r\n' +
               '确定后，下次启动时会重新抽一次，之后再固定下来。\r\n' +
               '（同一台电脑的所有角色共用这一套。开局装备、遗物和骨灰只对之后新建的角色生效：已有角色身上的装备和还没捡到的骨灰都按这个角色自己的记录，不会变。）')
        if self.confirm_box(msg, '一键重随物品'):
            self.start_run('一键重随物品', [(False, ['oncereset'])])

    # ---------------------------------------------------------------- 敌人设置
    @staticmethod
    def get_setting_num(Text, Name, Default):
        m = re.search(r'(?m)^\s*"' + re.escape(Name) + r'"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)', Text)
        return float(m.group(1)) if m else Default

    @staticmethod
    def set_setting_num(Text, Name, Value, Before):
        v = _fmt_num(Value)
        m = re.search(r'(?m)^\s*"' + re.escape(Name) + r'"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)', Text)
        if m:
            return Text[:m.start(1)] + v + Text[m.end(1):]
        nl = '\r\n' if '\r\n' in Text else '\n'
        b = re.search(r'(?m)^[ \t]*"' + re.escape(Before) + r'"\s*:', Text)
        at = b.start() if b else Text.index('{') + 1 + len(nl)
        return Text[:at] + '  "' + Name + '": ' + v + ',' + nl + Text[at:]

    @staticmethod
    def nearest_level(levels, value):
        best = 0
        for i in range(1, len(levels)):
            if abs(levels[i][1] - value) < abs(levels[best][1] - value):
                best = i
        return best

    @staticmethod
    def elite_desc(mult, base):
        if mult <= 0:
            return '不额外放精英：前期没有精英怪，其他地区只有随机器自己随机到的少量精英怪。'
        parts = []
        for i, b in enumerate(base):
            nm = ELITE_BAND_NAMES[i] if i < len(ELITE_BAND_NAMES) else '第 ' + str(i + 1) + ' 档'
            parts.append(nm + ' ' + _fmt_num(min(60.0, b * mult), '0.#') + '%')
        return '普通敌人里精英怪的比例：' + '，'.join(parts) + '。'

    @staticmethod
    def boss_desc(pct):
        if pct <= 0:
            return '关闭：普通敌人的位置只会出现普通敌人和精英怪。'
        n = round(100 / pct)
        return '约 ' + _fmt_num(pct, '0.#') + '% 的普通敌人会换成随机头目（大约每 ' + str(int(n)) + ' 个里 1 个）。追忆头目不会出现在这些位置。'

    def on_enemy_settings(self):
        try:
            txt = core.read_text(self.settings)
        except OSError:
            self.show_info('读不了重随设置：' + self.settings)
            return
        base = [2.5, 5, 7.5, 10, 12.5, 15]
        bm = re.search(r'"elite_share_by_band"\s*:\s*\[([^\]]*)\]', txt)
        if bm:
            try:
                base = [float(x.strip()) for x in bm.group(1).split(',')]
            except ValueError:
                pass
        em = self.get_setting_num(txt, 'elite_share_mult', 1.0)
        bp = self.get_setting_num(txt, 'boss_in_basic_pct', 0.0)
        st = Rec(E=self.nearest_level(ELITE_LEVELS, em), B=self.nearest_level(BOSS_LEVELS, bp), EV=em, BV=bp, ED=False, BD=False, Go='')
        el = [{'name': n, 'sub': s, 'desc': self.elite_desc(v, base)} for n, v, s in ELITE_LEVELS]
        blv = [{'name': n, 'sub': s, 'desc': self.boss_desc(v)} for n, v, s in BOSS_LEVELS]
        a = self.modal({'kind': 'enemy', 'title': '暗黑重铸 · 敌人设置', 'icon': '',
                        'elite': {'title': '精英怪比例', 'desc': '敌人随机时，普通敌人里有多少换成精英怪（越往后的地区越多）。', 'levels': el, 'sel': st.E,
                                  'orig': self.elite_desc(st.EV, base)},
                        'boss': {'title': '头目出现在普通敌人位置', 'desc': '开启后，敌人随机时有一部分普通敌人会换成随机头目，路上可能突然遇到头目。', 'levels': blv,
                                 'sel': st.B, 'orig': self.boss_desc(st.BV)},
                        'note': '这两项只影响敌人随机：保存后要点「一键重随敌人」才会生效，已经随机好的敌人不会变。没开敌人随机（一键启动 · 无敌人随机）时不起作用。',
                        'buttons': ['保存并重随敌人', '只保存', '取消'], 'def': 0, 'cancel': 2})
        if a is None:
            return
        r = a.get('result')
        if r not in (0, 1):
            return
        e = a.get('e') if a.get('e') is not None else -1
        b = a.get('b') if a.get('b') is not None else -1
        if 0 <= int(e) < len(ELITE_LEVELS):
            st.E, st.ED = int(e), True
        if 0 <= int(b) < len(BOSS_LEVELS):
            st.B, st.BD = int(b), True
        st.Go = 'rand' if r == 0 else 'save'
        ev = ELITE_LEVELS[st.E][1] if st.ED else st.EV
        bv = BOSS_LEVELS[st.B][1] if st.BD else st.BV
        try:
            new = self.set_setting_num(txt, 'elite_share_mult', ev, 'elite_share_by_band')
            new = self.set_setting_num(new, 'boss_in_basic_pct', bv, 'elite_share_by_band')
            json.loads(new)                                # 改完还得是合法的 JSON，不是就不写
            if new != txt:
                with open(self.settings, 'wb') as f:
                    f.write(new.encode('utf-8'))
        except Exception as ex:
            self.show_dr_dialog('保存失败：' + str(ex) + '\r\n\r\n设置文件：' + self.settings, '暗黑重铸 · 敌人设置', ['确定'], 0, 0, 'error')
            return
        s = '精英怪比例：' + ELITE_LEVELS[self.nearest_level(ELITE_LEVELS, ev)][0] + '；头目出现在普通敌人位置：' + BOSS_LEVELS[self.nearest_level(BOSS_LEVELS, bv)][0]
        self.log('敌人设置已保存（' + s + '）')
        if st.Go == 'rand':
            self.on_rand_enemy()
            return
        self.show_info('已保存（' + s + '）。' + '\r\n\r\n' + '下次点「一键重随敌人」时生效。')

    # ---------------------------------------------------------------- 常见问题
    def on_faq(self):
        ops = [{'op': 'bk', 'label': '打开自动备份文件夹'}, {'op': 'save', 'label': '打开存档文件夹'}]
        need = randomizer.get_randomizer_status(self.ctx).Ok and randomizer.test_need_old_random(self.ctx)
        found = randomizer.find_old_randoms(self.ctx) if need else []
        st = {'carry': found[0] if found else None, 'go': None}
        if need:
            ops.append({'op': 'carry', 'label': '沿用旧版本的敌人随机'})

        def on_op(op):
            c = self.ctx
            if op == 'bk':
                d = c.RngBackupDir if os.path.exists(c.RngBackupDir) else c.RngSaveRoot
                if not os.path.exists(d):
                    self.show_info('还没有备份（' + c.RngBackupDir + '）：用启动器启动游戏、玩过一会儿后才会有。')
                    return None
                _explorer(d)
            elif op == 'save':
                if not os.path.exists(c.RngSaveRoot):
                    self.show_info('没有找到存档文件夹：' + c.RngSaveRoot)
                    return None
                _explorer(c.RngSaveRoot)
            elif op == 'carry':
                if not st['carry']:
                    st['carry'] = self.select_old_pack()
                    if not st['carry']:
                        return None
                x = st['carry']
                msg = ('把旧版本整合包里的敌人随机结果复制过来（约 100 MB，几秒钟），敌人和之前一模一样：\r\n' +
                       '  文件夹：' + x.Pack + '（v' + str(x.Version) + '）\r\n' +
                       '  随机化于：' + x.Time.strftime('%Y-%m-%d %H:%M') + ('，种子 ' + str(x.Seed) if x.Seed else '') + '\r\n\r\n现在复制吗？')
                if not self.confirm_box(msg, '沿用旧版本的敌人随机结果'):
                    return None
                st['go'] = x
                return 'close'
            return None
        self.modal({'kind': 'msg', 'wide': True, 'title': '常见问题', 'icon': '', 'text': FAQ_TEXT, 'ops': ops,
                    'buttons': ['关闭'], 'def': 0, 'cancel': 0}, on_op)
        if st['go']:
            self.start_run('沿用旧版本的敌人随机结果', [(False, self.carry_call(st['go']))])

    # ---------------------------------------------------------------- 更新
    def read_update_check(self):
        try:
            v = json.loads(core.read_text(self.update_check))
            return v if isinstance(v, dict) else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def update_notes_text(c, Max=2400):
        t = ''
        for n in c.get('notes') or []:
            if not n:
                continue
            t += 'v' + str(n.get('version')) + ('（' + str(n.get('date')) + '）' if n.get('date') else '') + '\r\n'
            body = str(n.get('text') or '').strip()
            t += (re.sub(r'\r?\n', '\r\n', body) if body else '（没有写更新内容）') + '\r\n\r\n'
        if len(t) > Max:
            t = t[:Max] + '……\r\n（完整的更新内容更新后见「更新日志」）'
        return t.rstrip()

    def show_update_offer(self, c):
        mb = '%.1f' % (float(c.get('size') or 0) / 1048576.0)
        head = ('现在是 v' + str(c.get('cur')) + '，可以更新到 v' + str(c.get('latest')) + '：要下载 ' + str(len(c.get('chain') or [])) + ' 个更新包，共 ' + mb + ' MB。\r\n' +
                '只替换改了的文件，敌人随机结果、存档和角色记录都不受影响；改动前自动备份，失败自动还原。更新前要先退出游戏。\r\n\r\n')
        return self.show_dr_dialog(head + self.update_notes_text(c), '暗黑重铸 · 有新版本 v' + str(c.get('latest')), ['现在更新', '以后再说'], 0, 1, 'info') == 0

    def show_full_package(self, c):
        if not c:
            self.show_info('没有能直接更新的更新包，请下载完整的整合包。')
            return
        why = ('有新版本 v' + str(c.get('latest')) + '，但没有能从你现在的 v' + str(c.get('cur')) +
               ' 直接更新的更新包（跨的版本太多，或者这一版改动太大），请下载完整的整合包。')
        if c.get('full_note'):
            why += '\r\n\r\n' + str(c['full_note'])
        if not c.get('full_url'):
            self.show_info(why)
            return
        r = self.show_dr_dialog(why + '\r\n\r\n下载页：' + str(c['full_url']), '暗黑重铸 · 需要完整的整合包', ['打开下载页', '关闭'], 0, 1, 'info')
        if r == 0:
            _open_url(str(c['full_url']))

    def start_gui_again(self):
        """更新完重开启动器（新版本的）：包里的 pythonw 直接跑 launcher\\dfgui.py"""
        pyw = os.path.join(self.L, 'python', 'pythonw.exe')
        try:
            subprocess.Popen([pyw if os.path.isfile(pyw) else sys.executable, '-I', os.path.join(self.L, 'dfgui.py')], cwd=self.P, close_fds=True)
        except OSError:
            pass

    def update_done(self):
        res = ''
        try:
            res = core.read_lines(self.update_result)[0].strip()
        except (OSError, IndexError):
            pass
        if re.match(r'^ok (.+)$', res):
            self.start_gui_again()
            if self.win:
                self.win.invoke(self.win.destroy)
        elif res == 'latest':
            self.show_info('已经是最新版本，不用更新。')
        elif res == 'full':
            self.show_full_package(self.read_update_check())

    def start_online_update(self):
        if self.running or not self.confirm_game_closed('更新整合包之前要先退出游戏。'):
            return
        try:
            os.remove(self.update_result)
        except OSError:
            pass
        self.start_run('在线更新', [(True, ['autoupdate'])], self.update_done)

    def update_checked(self):
        c = self.read_update_check()
        if not c:
            self.show_info('检查更新没有完成，详细看运行日志。')
            return
        s = str(c.get('status'))
        if s == 'latest':
            self.show_info('已经是最新版本 v' + str(c.get('cur')) + '。')
        elif s == 'available':
            if self.show_update_offer(c):
                self.start_online_update()
        elif s == 'full':
            self.show_full_package(c)
        else:
            self.show_info('检查更新失败：' + str(c.get('error')) + '\r\n\r\n网络不好时过一会儿再试；也可以自己下载更新包，用「导入更新包」导入。')

    def on_check_update(self):
        if self.running:
            return
        try:
            os.remove(self.update_check)
        except OSError:
            pass
        self.start_run('检查更新', [(False, ['checkupdate'])], self.update_checked)

    def on_import_update(self):
        if self.running or not self.confirm_game_closed('更新整合包之前要先退出游戏。'):
            return
        zips = win.pick_file('选择暗黑重铸的更新包（可以一次选好几个，会按版本顺序导入）', '暗黑重铸更新包 (*.zip)|*.zip', None, True,
                             self.win.hwnd if self.win else None)
        if not zips:
            return
        try:
            os.remove(self.update_result)
        except OSError:
            pass
        self.start_run('导入更新包', [(True, ['update', '--update-zip', '|'.join(zips)])], self.update_done)

    def start_update_check(self):
        """页面「自动检查更新」：后台跑 update.py --check，不进运行日志"""
        if self.upd_proc is not None and self.upd_proc.poll() is None:
            return
        py = os.path.join(self.L, 'python', 'python.exe')
        if not os.path.exists(py):
            return
        a = [py, '-X', 'utf8', os.path.join(self.L, 'update.py'), '--root', self.P, '--check']
        if os.environ.get('DARKFORGE_UPDATE_MANIFEST'):
            a += ['--manifest', os.environ['DARKFORGE_UPDATE_MANIFEST']]
        try:
            self.upd_proc = subprocess.Popen(a, cwd=self.L, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                             creationflags=CREATE_NO_WINDOW, env=child_env())
        except OSError:
            self.upd_proc = None

    # ---------------------------------------------------------------- 联机（有 launcher\coop_test.txt 才显示）
    def find_ersc_path(self):
        ud = os.path.join(self.P, 'dll')
        cands = []
        if os.path.isdir(ud):
            if os.path.isfile(os.path.join(ud, 'ersc.dll')):
                cands.append(os.path.join(ud, 'ersc.dll'))
            for d in win.culture_sorted([e for e in os.scandir(ud) if e.is_dir()], key=lambda e: e.name):
                if not d.name.startswith('_') and os.path.isfile(os.path.join(d.path, 'ersc.dll')):
                    cands.append(os.path.join(d.path, 'ersc.dll'))
        root = self.get_game_root()
        if root and os.path.exists(os.path.join(root, 'Game', 'SeamlessCoop', 'ersc.dll')):
            cands.append(os.path.join(root, 'Game', 'SeamlessCoop', 'ersc.dll'))
        return cands[0] if cands else None

    def show_coop_menu(self):
        from .. import coopcode
        ersc = self.find_ersc_path()
        need = '没找到 Seamless Co-op。它要自己下载：把压缩包里的 SeamlessCoop 文件夹整个放进整合包的 dll\\ 文件夹（变成 dll\\SeamlessCoop\\ersc.dll）。'
        msg = ('联机用 Seamless Co-op 模组（整合包不带，要自己下载：把压缩包里的 SeamlessCoop 文件夹整个放进整合包的 dll\\；压缩包里的 ersc_launcher.exe 不用，联机也从这里启动）。\r\n' +
               ('已找到：' + ersc if ersc else '⚠ 还没找到 Seamless Co-op。') + '\r\n\r\n' +
               '怎么联机（两人用同一个版本的整合包）：\r\n' +
               '1. 房主点「开房 · 敌人随机」或「开房 · 无敌人随机」：联机码自动复制到剪贴板，游戏同时启动。把联机码发给队友（码里有联机密码，只发给队友）。\r\n' +
               '2. 队友复制这一行，点「加入」：联机密码、Seamless Co-op 设置、敌人设置和世界照房主的改好；敌人随机和房主不一样时先重随（约 1~5 分钟），然后启动。\r\n' +
               '3. 进游戏后房主用 Seamless Co-op 的开房道具，队友用加入的道具。两边的游戏数据对不对得上，进同一个会话后自动核对。\r\n' +
               '下次还是同一队人：房主照样点「开房」，队友点「加入」（剪贴板里没有码时用上次的）。\r\n\r\n' +
               '联机时：以房主的世界为准；斗技场试炼由房主在雕像开始、队友一起进，头目复活只有房主能用；倒下了会观战队友，直到所有人都倒下或者有人在赐福休息；Seamless Co-op 的入侵会自动关掉；直接改敌人的词条效果由房主那边改。\r\n' +
               '联机存档是 ER0000.rngcoop（以前叫 ER0000.rng.co2，联机启动时会自动换过来），和单机存档分开；联机角色的新装备、锁定等记录也单独存，互不影响。\r\n' +
               '联机还在测试：队友身上的新装备在你这边样子和名字不对；新装备可以在背包里点它「送给」队友。出问题时点「导出诊断包」发过来。')
        r = self.show_dr_dialog(msg, '暗黑重铸 · 联机（Seamless Co-op）', ['开房 · 敌人随机', '开房 · 无敌人随机', '加入', '复制联机码', '关闭'], 0, 4, 'question')
        if r in (0, 1, 2, 3) and not ersc:
            self.show_info(need)
            return
        if r == 0:
            if not self.confirm_randomizer():
                return
            latest = self.get_latest_random()
            if not latest or latest.Merged:
                self.show_info('还没有能用的敌人随机结果：先「一键重随敌人」，或者点「开房 · 无敌人随机」。')
                return
            if not self.before_launch():
                return
            bw = self.ask_coop_world()
            if bw is None:
                return
            self.start_run('联机开房 · 敌人随机', [(False, ['coophost'] + self.boss_arg(bw))])
        elif r == 1:
            if not self.before_launch():
                return
            bw = self.ask_coop_world()
            if bw is None:
                return
            self.start_run('联机开房 · 无敌人随机', [(False, ['coophostvanilla'] + self.boss_arg(bw))])
        elif r == 2:
            code = re.sub(r'\s+', ' ', win.clipboard_get() or '').strip()
            if not re.match(r'^DR(?:[123]\||4)', code, re.I):
                code = ''
                files = [f for f in (os.path.join(self.P, 'dll', 'dark_core', 'coop_host_code.txt'),
                                     os.path.join(self.L, 'reroll', 'state', 'coop_join_code.txt')) if os.path.exists(f)]
                for f in sorted(files, key=lambda f: os.stat(f).st_mtime_ns, reverse=True):
                    t = re.sub(r'\s+', ' ', core.read_text(f, 'replace')).strip()
                    if re.match(r'^DR(?:[123]\||4)', t, re.I):
                        code = t
                        break
            if not code:
                self.show_info('剪贴板里没有联机码。先复制房主发来的那一串（DR4 开头），再点「加入」。')
                return
            plain = coopcode.expand_coop_code('DR4' + code[3:4].lower() + code[4:] if code[:3].upper() == 'DR4' else code)
            if not plain:
                self.show_info('这个联机码解不开（多半没复制完整）。让房主重新点「复制联机码」发一次。')
                return
            rand = not re.match(r'^DR3\|', plain, re.I) or re.search(r'\|m=rand(\||$)', plain, re.I)
            if rand:
                if not self.confirm_randomizer():
                    return
                if win.find_pids('EldenRingRandomizer'):
                    self.show_info('随机器已经开着，先把它关掉。')
                    return
            if not self.before_launch():
                return
            if rand:
                msg2 = ('加入房主的联机：联机密码、Seamless Co-op 设置、敌人设置和世界照房主的改好再启动。\r\n\r\n' +
                        '敌人随机和房主不一样时会先重随敌人：随机器窗口会自动打开、自动操作、完成后自动关闭，这期间不要点它，也不要关掉它（约 1~5 分钟）。\r\n\r\n现在开始吗？')
                if not self.confirm_box(msg2, '加入联机'):
                    return
            self.start_run('加入队友的联机', [(False, ['coopjoin', '--code', code])])
        elif r == 3:
            self.start_run('复制联机码', [(False, ['coopcode'])])

    def on_coop_tool(self, name):
        if name == '联机':
            self.show_coop_menu()
        elif name == '联机设置':
            e = self.find_ersc_path()
            if not e:
                self.show_info('没找到 Seamless Co-op。它要自己下载：把压缩包里的 SeamlessCoop 文件夹整个放进整合包的 dll\\ 文件夹（变成 dll\\SeamlessCoop\\ersc.dll）。')
                return
            ini = os.path.join(os.path.dirname(e), 'ersc_settings.ini')
            if not os.path.exists(ini):
                self.show_info('Seamless Co-op 旁边没有设置文件：' + ini + '\r\n\r\n' + '重新解压一次 Seamless Co-op 的压缩包。')
                return
            _notepad(ini)

    def on_mod_tool(self, name):
        from .. import usermods
        if name == 'mods 文件夹':
            os.makedirs(self.ctx.UserModDir, exist_ok=True)
            _explorer(self.ctx.UserModDir)
        elif name == 'DLL 文件夹':
            _explorer(os.path.join(self.P, 'dll'))
        elif name == '自定义配置':
            _notepad(usermods.new_user_ini(self.ctx))

    # ================================================================ 打开时
    def show_enemy_info_first(self):
        """第一次打开启动器时说明一次敌人信息 mod（不问，默认加载；动过开关或看过就不再显示）"""
        if os.path.exists(self.enemy_info_choice) or os.path.exists(self.enemy_info_noted):
            return
        gpus = win.get_gpu_names()
        text = ('整合包带有敌人信息 mod：在敌人头上显示血条和异常状态条，默认加载。\r\n\r\n' +
                '在少数电脑上（多见于有两块显卡的，比如核显 + 独显的笔记本），它可能导致游戏无法启动或读档时闪退。' +
                ('这台电脑有两块显卡（' + '、'.join(gpus) + '），遇到的可能性大一些。' if len(gpus) >= 2 else '') +
                'N 卡开启插帧（帧生成）时，它也会导致游戏崩溃。\r\n\r\n' +
                '遇到的话，在启动器「工具与设置」→「游戏」里把「敌人信息 mod」关掉，下次启动游戏生效。关掉后游戏里没有敌人头上的血条和状态条，别的功能都不受影响。')
        self.show_dr_dialog(text, '暗黑重铸 · 敌人信息 mod', ['知道了'], 0, 0, 'info')
        try:
            os.makedirs(os.path.dirname(self.enemy_info_noted), exist_ok=True)
            core.write_text(self.enemy_info_noted, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\r\n')
        except OSError:
            pass

    def startup(self):
        """打开时：记下版本（降级要警告）；确定游戏路径；敌人信息 mod 的说明；记下整合包位置；问要不要沿用旧版本的敌人随机"""
        if self.startup_done or not self.page_ready:
            return
        self.startup_done = True
        self.show_version_notice()
        if not self.get_game_root():
            self.log('正在搜索游戏路径...')
            if self.ensure_game_root():
                self.log('游戏路径：' + str(self.get_game_root()))
            else:
                self.log('还没有设置游戏路径：启动游戏和一键重随敌人前都需要，点「游戏路径」选一下。')
            self.update_status()
        self.show_enemy_info_first()
        try:
            randomizer.save_pack_path(self.ctx)
        except Exception as e:
            self.record_error(e)
        c = self.ask_old_random()
        if c:
            self.start_run('沿用旧版本的敌人随机结果', [(False, self.carry_call(c))])
        self.send_updated_note()

    def send_updated_note(self):
        if not self.updated_note or not self.win or not self.win.wv:
            return
        self.toast(self.updated_note, ms=6000)
        self.send({'type': 'tab', 'tab': 'news'})
        self.updated_note = None

    def send_changelog(self):
        text = ''
        try:
            allt = core.read_text(os.path.join(self.P, '更新日志.txt'), 'replace')
            idx = [m.start() for m in re.finditer(r'(?m)^v\d[^\r\n]*\r?\n-{3,}', allt)]
            end = idx[3] if len(idx) > 3 else len(allt)
            text = allt[:end]
        except OSError:
            pass
        self.send({'type': 'changelog', 'text': text})

    # ================================================================ 页面消息
    def on_message(self, text):
        """窗口线程：弹层的回答、拖动 / 最小化马上处理；别的交给操作线程按顺序做"""
        try:
            m = json.loads(text)
        except ValueError:
            return
        if not isinstance(m, dict):
            return
        a = str(m.get('action') or '')
        if a in ('dialog', 'dialogop'):
            try:
                q = self.dialogs.get(int(m.get('id')))
            except (TypeError, ValueError):
                q = None
            if q:
                q.put(('answer', m) if a == 'dialog' else ('op', str(m.get('op') or '')))
            return
        if a == 'win' and m.get('op') != 'close':
            if m.get('op') == 'drag':
                self.win.drag()
            elif m.get('op') == 'minimize':
                self.win.minimize()
            return
        self.actions.put(m)

    def worker(self):
        while True:
            m = self.actions.get()
            if m is None:
                return
            try:
                if isinstance(m, tuple) and m[0] == '_call':
                    m[1]()
                else:
                    self.handle(m)
            except Exception as e:
                self.record_error(e)
                self.log('界面操作出错：' + str(e))
            if self.win:
                self.win.invoke(self.push_state)

    def handle(self, m):
        a = str(m.get('action') or '')
        if a == 'ready':
            self.page_ready = True
            self.update_status()
            self.refresh_has_hard()
            self.win.invoke(lambda: self.push_state(True))
            self.send_updated_note()
            if os.environ.get('DARKFORGE_WEBUI_SHOT'):
                self.win.invoke(self.start_shot)
            self.startup()
        elif a == '_startup':
            self.startup()
        elif a == 'changelog':
            self.send_changelog()
        elif a == 'launch':
            if self.running:
                return
            self.on_launch_vanilla() if m.get('mode') == 'vanilla' else self.on_launch_rand()
        elif a == 'randenemy':
            if not self.running:
                self.on_rand_enemy()
        elif a == 'randomizer':
            if not self.running:
                self.on_randomizer()
        elif a == 'checkupdate':
            self.start_update_check()
        elif a == 'backupint':                          # 定时备份间隔（工具与设置 → 存档；看守每分钟读一次，马上生效）
            try:
                v = backup.set_backup_interval(self.ctx, m.get('value'))
                self.toast('定时备份改成每 ' + str(v) + ' 分钟一次')
            except OSError as e:
                self.toast('没能保存设置：' + str(e), error=True)
        elif a == 'enemyinfo':
            v = 'off' if m.get('value') == 'off' else 'on'
            try:
                os.makedirs(os.path.dirname(self.enemy_info_choice), exist_ok=True)
                core.write_text(self.enemy_info_choice, v + '\r\n')
                self.toast('已关掉敌人信息 mod，下次启动游戏时生效' if v == 'off' else '已打开敌人信息 mod，下次启动游戏时生效')
            except OSError as e:
                self.toast('没能保存设置：' + str(e), error=True)
        elif a == 'autoupdate':
            if self.running:
                return
            c = self.read_update_check()
            if c and str(c.get('cur')) == str(self.pack_version) and c.get('status') == 'available':
                if self.show_update_offer(c):
                    self.start_online_update()
            elif c and str(c.get('cur')) == str(self.pack_version) and c.get('status') == 'full':
                self.show_full_package(c)
            else:
                self.on_check_update()
        elif a == 'tool':
            if self.running:
                return
            self.on_tool(str(m.get('name') or ''))
        elif a == 'openurl':
            if str(m.get('url')) in WEB_LINKS:
                _open_url(str(m.get('url')))
        elif a == 'win' and m.get('op') == 'close':
            if self.running:
                r = self.show_dr_dialog('启动器还在运行（生成掉落或等待游戏启动）。关掉窗口不会影响已经启动的游戏，确定关闭吗？', '暗黑重铸', ['关闭', '取消'], 0, 1, 'question')
                if r != 0:
                    return
            self.closing = True
            self.win.invoke(self.win.destroy)

    def on_tool(self, n):
        handlers = {
            '游戏路径': lambda: self.select_game_root(),
            '备份存档': self.on_backup,
            '恢复存档': self.on_restore,
            '重随设置': lambda: _notepad(self.settings),
            '一键重随物品': self.on_once_reset,
            '敌人设置': self.on_enemy_settings,
            '报告 / 日志': self.on_report,
            '导出诊断包': lambda: self.start_run('导出诊断包', [(False, ['diag'])]),
            '常见问题': self.on_faq,
            '更新日志': self.on_changelog_file,
            '导入更新包': self.on_import_update,
            '检查更新': self.on_check_update,
        }
        if n in handlers:
            handlers[n]()
        elif n in [x[0] for x in MOD_TOOLS]:
            try:
                self.on_mod_tool(n)
            except OSError as e:
                self.toast('没能打开：' + str(e), error=True)
        elif self.coop_on and n in [x[0] for x in COOP_TOOLS]:
            try:
                self.on_coop_tool(n)
            except OSError as e:
                self.toast('没能打开：' + str(e), error=True)

    def on_changelog_file(self):
        cl = os.path.join(self.P, '更新日志.txt')
        if os.path.exists(cl):
            _notepad(cl)
        else:
            self.show_info('找不到更新日志：' + cl)

    # ================================================================ 测试用截图（DARKFORGE_WEBUI_SHOT=<png>：页面就绪后截一张，然后关窗口）
    def start_shot(self):
        delay = int(os.environ.get('DARKFORGE_WEBUI_SHOT_DELAY') or 1500)
        after = int(os.environ.get('DARKFORGE_WEBUI_SHOT_AFTER') or 800)
        st = {'step': 0}

        def tick():
            st['step'] += 1
            if st['step'] == 1:
                js = os.environ.get('DARKFORGE_WEBUI_SHOT_JS')
                if js:
                    self.win.execute_script(js)
                self.win.kill_timer(st['t'])
                st['t'] = self.win.set_timer(after, tick)
            elif st['step'] == 2:
                self.win.kill_timer(st['t'])
                self.win.capture_png(os.environ['DARKFORGE_WEBUI_SHOT'], lambda ok: self.win.destroy())
        st['t'] = self.win.set_timer(delay, tick)

    # ================================================================ 跑起来
    def on_navigated(self, ok, status):
        if ok:
            self.win.ready = True
            self.push_state(True)
            self.send_updated_note()
            self.actions.put({'action': '_startup'})
        else:
            self.fallback('页面打不开（%d）' % status)

    def fallback(self, why):
        """网页界面用不了（没装 WebView2 运行库之类）：经典界面已经去掉，弹系统对话框给下载链接"""
        self.closing = True
        text = ('启动器的界面要用 Windows 自带的 WebView2 运行库（' + why + '）。\r\n\r\n' +
                '大多数电脑已经装好了；这台电脑上用不了的话，从微软官网装一下「Microsoft Edge WebView2 运行库」（免费，几十 MB），再打开启动器。\r\n\r\n' +
                '现在打开下载页吗？')
        if win.message_box(text, '暗黑重铸 启动器', 0x30 | 0x4) == 6:
            _open_url(WEBVIEW2_DOWNLOAD)
        if self.win:
            self.win.destroy()

    def run(self):
        webview.set_dpi_aware()
        webview.set_app_id('Darkforge.Launcher')
        loader = os.path.join(self.L, 'webview2')
        ui = os.path.join(self.L, 'ui')
        if not os.path.exists(os.path.join(ui, 'index.html')) or not os.path.exists(os.path.join(loader, 'WebView2Loader.dll')):
            win.message_box('启动器的文件不全（launcher\\ui 或 launcher\\webview2 不见了）。请重新解压整合包。', '暗黑重铸 启动器', 0x10)
            return 1
        if not webview.runtime_version(loader):
            self.fallback('这台电脑上没有找到')
            return 1
        os.makedirs(self.dlg_dir, exist_ok=True)
        os.environ['DARKFORGE_DLG_DIR'] = self.dlg_dir
        os.environ['DARKFORGE_GUI_PID'] = str(os.getpid())
        self.update_status()
        self.log('选择上面的按钮开始。')
        udf = os.path.join(os.environ.get('LOCALAPPDATA') or self.L, 'Darkforge', 'WebView2')
        self.win = webview.WebViewWindow('暗黑重铸 启动器', loader, udf, 'darkforge.local', ui, 'https://darkforge.local/index.html',
                                         icon_path=os.path.join(self.L, 'darkforge.ico'), browser_args='--disable-features=msSmartScreenProtection',
                                         devtools=bool(os.environ.get('DARKFORGE_WEBUI_DEVTOOLS')))
        self.win.on_message = self.on_message
        self.win.on_navigated = self.on_navigated
        self.win.on_failed = lambda why: self.fallback(why)
        self.win.on_close = self.on_window_close
        threading.Thread(target=self.worker, daemon=True).start()
        orig = self.win._create_window

        def created():
            orig()
            self.win.set_timer(300, lambda: (self.push_state(), self.watch_host_dialogs()))
        self.win._create_window = created
        try:
            self.win.run()
        finally:
            self.closing = True
            self.actions.put(None)
            self.save_errors()
        return 0

    def on_window_close(self):
        """点了 ×（任务栏右键关闭之类）：在跑的时候先问（交给操作线程，问完它自己关）"""
        if self.closing or not self.running:
            self.closing = True
            return True
        self.actions.put({'action': 'win', 'op': 'close'})
        return False


def main():
    app = App()
    try:
        return app.run()
    except Exception as e:
        app.record_error(e)
        app.save_errors()
        raise
