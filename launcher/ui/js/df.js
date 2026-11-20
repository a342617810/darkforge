/* 暗黑重铸启动器网页界面：只管显示和把点击转给宿主；所有逻辑都在 launcher\dfl\gui\app.py（后台步骤交给 df.py） */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var app = $('#app');
  var S = null;                 // 宿主最近一次推来的状态
  var wasBusy = false;
  var hideRunTimer = null;
  var changelogText = '';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function store(k, v) {
    try { if (v === undefined) return localStorage.getItem('df.' + k); localStorage.setItem('df.' + k, v); } catch (e) { return null; }
  }

  /* ---------------- 画布缩放：1280×720 按窗口等比缩放、居中 ---------------- */
  function fit() {
    var w = window.innerWidth, h = window.innerHeight;
    var k = Math.min(w / 1280, h / 720);
    app.style.transform = 'scale(' + k + ')';
    app.style.left = Math.round((w - 1280 * k) / 2) + 'px';
    app.style.top = Math.round((h - 720 * k) / 2) + 'px';
  }
  window.addEventListener('resize', fit);
  fit();

  /* ---------------- 键盘焦点轮廓只在按 Tab 时显示 ---------------- */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Tab') document.documentElement.classList.add('kb');
    if (e.key === 'Escape' && !topDlg()) closeModal();
  });
  document.addEventListener('mousedown', function () { document.documentElement.classList.remove('kb'); });

  /* ---------------- 提示气泡（data-tip） ---------------- */
  var tip = $('#tip'), tipTimer = null;
  document.addEventListener('mouseover', function (e) {
    var el = e.target.closest('[data-tip]');
    clearTimeout(tipTimer);
    if (!el || !el.getAttribute('data-tip')) { tip.classList.add('hide'); return; }
    tipTimer = setTimeout(function () {
      tip.textContent = el.getAttribute('data-tip');
      tip.classList.remove('hide');
      var r = el.getBoundingClientRect(), a = app.getBoundingClientRect(), k = a.width / 1280;
      var tw = tip.offsetWidth, th = tip.offsetHeight;
      var x = (r.left - a.left) / k + (r.width / k - tw) / 2;
      var below = el.getAttribute('data-tip-place') === 'bottom';
      var y = below ? (r.bottom - a.top) / k + 8 : (r.top - a.top) / k - th - 8;
      if (y < 4) y = (r.bottom - a.top) / k + 8;
      tip.style.left = Math.max(8, Math.min(1280 - tw - 8, x)) + 'px';
      tip.style.top = y + 'px';
    }, 280);
  });
  document.addEventListener('mouseout', function (e) {
    if (e.target.closest('[data-tip]')) { clearTimeout(tipTimer); tip.classList.add('hide'); }
  });

  /* ---------------- 窗口：拖动、最小化、关闭 ---------------- */
  document.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;
    if (e.target.closest('button, a, input, select, .log, .news')) return;
    if (e.target.closest('[data-drag]')) bridge.post('win', { op: 'drag' });
  });
  $$('[data-win]').forEach(function (b) {
    b.addEventListener('click', function () { bridge.post('win', { op: b.getAttribute('data-win') }); });
  });

  /* ---------------- 提示条 ---------------- */
  function toast(text, err, ms) {
    var box = $('#toasts');
    var t = document.createElement('div');
    t.className = 'toast' + (err ? ' err' : '');
    t.textContent = text;
    box.appendChild(t);
    while (box.children.length > 3) box.removeChild(box.firstChild);
    setTimeout(function () { t.remove(); }, ms || 3600);
  }

  /* ---------------- 左下面板：页签 ---------------- */
  function showTab(name) {
    $$('.tab').forEach(function (t) { t.classList.toggle('on', t.getAttribute('data-tab') === name); });
    $$('.tab-body').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-body') === name); });
    if (name === 'news' && !changelogText) bridge.post('changelog');
    if (name === 'log') scrollLog();
  }
  $$('.tab').forEach(function (t) {
    t.addEventListener('click', function () { showTab(t.getAttribute('data-tab')); });
  });

  /* ---------------- 启动模式 ---------------- */
  function mode() { return store('mode') || (S && S.mode) || 'rand'; }
  function renderMode() {
    var m = mode();
    $$('.seg').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-mode') === m); });
    if (S) $('#launchSub').textContent = m === 'rand' ? S.subs.launchR : S.subs.launchV;
  }
  $$('.seg').forEach(function (b) {
    b.addEventListener('click', function () { store('mode', b.getAttribute('data-mode')); renderMode(); });
  });
  $('#btnLaunch').addEventListener('click', function () { bridge.post('launch', { mode: mode() }); });
  $('#btnRandEnemy').addEventListener('click', function () { bridge.post('randenemy'); });
  // 一键重随物品 = 以前工具里的「一次性重随」，和「打开随机器」对调了位置（用户 2026-11-12）
  $('#btnRandItems').addEventListener('click', function () { bridge.post('tool', { name: '一键重随物品' }); });
  $('#btnTools').addEventListener('click', function () { openModal(); });
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-tool]');
    if (!t || t.disabled) return;
    var n = t.getAttribute('data-tool');
    if (n === '打开随机器') bridge.post('randomizer');        // 宿主的大按钮，不在工具按钮里
    else bridge.post('tool', { name: n });
  });

  /* ---------------- 状态 ---------------- */
  function setStat(id, c) {
    var el = $(id);
    el.className = 'stat ' + (c.accent || 'muted');
    el.querySelector('.v').textContent = c.value || '';
    el.querySelector('.v').setAttribute('data-tip', c.tip || c.value || '');
  }
  /* ---------------- 背景：没有死亡以上难度的角色用普通那张；有了默认用魇火那张，设置里可以手动换回普通（用户 2026-11-10） ---------------- */
  var curWorld = null;
  function bgWorld() {
    if (!S || !S.hasHard) return 'normal';
    return store('bg') === 'normal' ? 'normal' : 'hard';
  }
  function applyWorld() {
    var w = bgWorld();
    if (w === curWorld) return;
    curWorld = w;
    app.classList.toggle('world-hard', w === 'hard');
    app.classList.toggle('world-normal', w !== 'hard');
    $('#bgArt').setAttribute('src', 'img/bg_' + w + '.jpg');
    var top = $('#bgTop'), m = ((window.DF_LAYERS || {})[w] || {}).top;
    top.setAttribute('src', 'img/top_' + w + '.png');
    if (m) {                                      // layers.js 是 1920×1080 的坐标，画布 1280×720
      var k = 1280 / 1920;
      top.style.left = m[0] * k + 'px'; top.style.top = m[1] * k + 'px';
      top.style.width = m[2] * k + 'px'; top.style.height = m[3] * k + 'px';
    }
    if (window.DFSmoke) window.DFSmoke.set(w);
  }
  if (window.DFSmoke) window.DFSmoke.enable(store('anim') !== 'off');
  applyWorld();

  function render(s) {
    S = s;
    applyWorld();
    var badge = $('#badge');
    badge.textContent = s.busy ? '运行中' : (s.version ? 'v' + s.version : '');
    badge.classList.toggle('busy', !!s.busy);
    setStat('#stPath', s.cards.path);
    setStat('#stRand', s.cards.rand);
    setStat('#stLast', s.cards.last);
    $('#stTip').textContent = s.randomizerOk ? '' : '敌人随机要先装随机器（整合包不带）。点「一键启动」选敌人随机时会说明怎么装；不装也能玩无敌人随机。';
    $('#subRandEnemy').textContent = s.subs.randEnemy;
    $('#subRandItems').textContent = s.subs.randItems || '';
    renderMode();
    ['#btnLaunch', '#btnRandEnemy', '#btnRandItems', '#btnDiag'].forEach(function (id) { $(id).disabled = !!s.busy; });
    $('#btnDiag').classList.toggle('hot', !!(s.run && s.run.error));        // 这次运行出过错：标签栏的「导出诊断包」变成提醒色
    $$('#rows [data-tool]').forEach(function (b) { b.disabled = !!s.busy; });
    renderRun(s);
    renderUpdate(s);
    if (s.tools && !toolTips) { toolTips = {}; s.tools.forEach(function (t) { toolTips[t.name] = t.tip; }); }
  }

  function renderRun(s) {
    var r = s.run || {};
    var lines = r.lines || [];
    var pre = $('#log');
    pre.innerHTML = lines.map(function (l) {
      var cls = /\[错误\]/.test(l) ? 'err' : (/^\s*[■□]+/.test(l) ? 'pbar' : '');
      return cls ? '<span class="' + cls + '">' + esc(l) + '</span>' : esc(l);
    }).join('\n');
    var box = $('#run');
    if (s.busy) {
      clearTimeout(hideRunTimer); hideRunTimer = null;
      box.classList.remove('hide');
      if (!wasBusy) showTab('log');
      var last = '';
      for (var i = lines.length - 1; i >= 0; i--) {
        if (lines[i] && !/^\s*[■□]+/.test(lines[i]) && !/^===/.test(lines[i])) { last = lines[i].trim(); break; }
      }
      $('#runText').textContent = last || (r.title ? r.title + '……' : '运行中……');
      var bar = $('.bar');
      if (typeof r.pct === 'number') {
        bar.classList.remove('indet');
        $('#runBar').style.width = Math.max(0, Math.min(100, r.pct)) + '%';
        $('#runPct').textContent = r.pct + '%';
      } else {
        bar.classList.add('indet');
        $('#runPct').textContent = '';
      }
    } else if (wasBusy) {
      $('#runText').textContent = r.error ? '出了问题，详细看「运行日志」' : '完成';
      $('#runPct').textContent = '';
      $('.bar').classList.remove('indet');
      $('#runBar').style.width = r.error ? '0%' : '100%';
      if (r.error) toast('运行中出了问题，详细看「运行日志」', true);
      hideRunTimer = setTimeout(function () { box.classList.add('hide'); }, r.error ? 8000 : 3000);
    }
    wasBusy = !!s.busy;
    scrollLog();
  }
  /* ---------------- 有新版本（宿主后台检查更新，state.update；用户 2026-11-11「通过 gitee 实现自动更新」） ---------------- */
  function hasUpdate(s) { var u = s && s.update; return !!(u && (u.status === 'available' || u.status === 'full')); }
  function mb(n) { return (Number(n || 0) / 1048576).toFixed(1) + ' MB'; }
  function renderUpdate(s) {
    var u = s.update, has = hasUpdate(s);
    $('#toolsDot').classList.toggle('hide', !has);
    var pill = $('#updPill');
    pill.classList.toggle('hide', !has);
    if (!has) return;
    $('#updText').textContent = '有新版本 v' + u.latest + (u.status === 'available' ? ' · ' + mb(u.size) : '');
    // 用户 2026-11-13「启动器左边新版本那里改为点击查看并更新」
    $('#updAct').textContent = u.status === 'available' ? '点击查看并更新' : '点击下载完整整合包';
    pill.disabled = !!s.busy;
    pill.setAttribute('data-tip', u.notes || '');
  }
  $('#updPill').addEventListener('click', function () { bridge.post('autoupdate'); });
  function updateStatusText(s) {
    var u = s && s.update;
    if (!u) return '';
    var when = u.checked ? '上次检查：' + u.checked.slice(5, 16) + '，' : '';
    if (u.status === 'latest') return when + '已经是最新版本。';
    if (u.status === 'available') return when + '有新版本 v' + u.latest + '（' + mb(u.size) + '）。';
    if (u.status === 'full') return when + '有新版本 v' + u.latest + '，要下载完整的整合包。';
    return when + '没连上（' + (u.error || '网络问题') + '）。';
  }
  var autoChecked = false;
  // 打开时查一次，之后启动器开着就每 5 分钟查一次（用户 2026-11-12「启动器是每30s 而不是只检查一次」→「那间隔改为5分钟吧」）。
  // 设置里关了、启动器正在忙（启动游戏、更新）、已经查到有新版本时这一次不查
  var AUTO_RECHECK_MS = 5 * 60 * 1000;
  function autoCheck() {
    if (autoChecked) return;
    autoChecked = true;
    if (store('autocheck') !== 'off') bridge.post('checkupdate');
    setInterval(function () {
      var st = S && S.update && S.update.status;
      if (store('autocheck') !== 'off' && !(S && S.busy) && st !== 'available' && st !== 'full') bridge.post('checkupdate');
    }, AUTO_RECHECK_MS);
  }

  function scrollLog() { var p = $('#log'); p.scrollTop = p.scrollHeight; }

  /* ---------------- 更新日志（宿主把 更新日志.txt 的前几个版本发过来） ---------------- */
  function renderNews(text) {
    changelogText = text || '';
    var parts = changelogText.split(/\r?\n(?=v\d[^\n]*\r?\n-{3,})/);
    var out = [];
    parts.forEach(function (p) {
      var m = p.match(/^(v\d[^\n（(]*)[（(]?([^）)\n]*)[）)]?\s*\r?\n-{3,}/);
      if (!m) return;
      if (out.length >= 3) return;
      var html = '<h4>' + esc(m[1].trim()) + '<small>' + esc(m[2]) + '</small></h4>';
      var body = p.slice(m[0].length).split(/\r?\n/);
      var inList = false, inSub = false;
      body.forEach(function (l) {
        var sec = l.match(/^【(.+)】/);
        if (sec) {
          if (inSub) { html += '</ul></li>'; inSub = false; }
          if (inList) { html += '</ul>'; inList = false; }
          html += '<h5>' + esc(sec[1]) + '</h5>';
          return;
        }
        var sub = l.match(/^\s{2,}- (.*)/);
        var top = l.match(/^- (.*)/);
        if (top) {
          if (inSub) { html += '</ul></li>'; inSub = false; }
          if (!inList) { html += '<ul>'; inList = true; }
          html += '<li>' + esc(top[1]);
          html += '</li>';
        } else if (sub && inList) {
          if (!inSub) { html = html.replace(/<\/li>$/, ''); html += '<ul>'; inSub = true; }
          html += '<li>' + esc(sub[1]) + '</li>';
        }
      });
      if (inSub) html += '</ul></li>';
      if (inList) html += '</ul>';
      out.push(html);
    });
    $('#news').innerHTML = (out.join('') || '<p class="muted">没有读到更新日志。</p>') +
      '<button class="link more" data-tool="更新日志">用记事本打开完整的更新日志</button>';
  }

  /* ---------------- 工具与设置 ---------------- */
  var toolTips = null;
  var CATS = [
    { key: 'game', name: '游戏', tools: ['游戏路径'] },
    { key: 'save', name: '存档', tools: ['备份存档', '恢复存档'] },
    { key: 'rand', name: '敌人随机', tools: ['敌人设置', '打开随机器', '重随设置'] },
    { key: 'coop', name: '联机', tools: ['联机', '联机设置'] },     // Seamless Co-op（联机分支 coop，联机计划 13.3 C11；dfl\gui\app.py 的 COOP_TOOLS）
    { key: 'update', name: '更新', tools: ['检查更新', '导入更新包', '更新日志'] },
    { key: 'mods', name: '模组', tools: ['mods 文件夹', 'DLL 文件夹', '自定义配置'] },     // 玩家自己加 mod（用户 2026-11-16，launcher\dfl\usermods.py）
    { key: 'help', name: '帮助与排查', tools: ['常见问题', '报告 / 日志', '导出诊断包'] },
    { key: 'ui', name: '界面', tools: [] },
    { key: 'about', name: '关于', tools: [] },
  ];
  // 「关于」里的署名（用户 2026-11-12「把署名挪到启动器的关于里」：v0.10.3 起整合包不带说明文件，以前写在各处说明.txt 里的出处挪到这里；
  // 作者和许可照 2026-10-29 / 11-11 查的各模组页面）。一组：[标题, [[名字, 说明], …]]
  var CREDITS_LIST = [
    ['整合包带着的模组和工具', [
      ['Elden Ring Item and Enemy Randomizer', 'thefifthmatt（Nexus 428）：敌人随机、物品随机'],
      ['Souls Vision', 'sparrowsj（Nexus 6968）：敌人信息'],
      ['Transmogrify Armor', 'Tom Clark（Nexus 3596）：防具幻化'],
      ['Erd-Tools-CPP', 'Nordgaren（GPL-3.0）：ErdTools'],
      ['YAFSML', 'soarqin（MIT）：模组加载器'],
    ]],
    ['死亡以上难度的头目改版', [
      ['Inner Consort、Inner Serpent、Ancient Elden Lord', 'thebluehood35'],
      ['Inner Godfrey', 'TheInterloper1'],
      ['Mohg 2.00 Complete', 'DDMMDD09'],
      ['Midra Overhaul、Rellana Twin Moon Knight Overhaul', 'mrsakana23'],
      ['Godrick overhaul、Rennala overhaul', 'Lwingr'],
      ['Rykard Overhaul', 'Lwingr、thebluehood35'],
      ['Unalloyed Malenia、Vanilla Plus Radahn', '作者的账号已注销'],
    ]],
    ['参考或沿用了做法', [
      ['RNG Lands', 'Ecril（Nexus 3229）：暗黑重铸的前身'],
      ['黄金时代（Golden Age）3.6.8', '第五个护符栏的做法（eldenring_covenant_slot）、大书库门前赐福的位置、解封后花蕾教堂的头目战'],
      ['ELDEN VINS', 'mayk（Nexus 4709）：赐福菜单、训练木桩的位置、防摔和商店距离的参数'],
      ['Modular Wall Jump', 'Vulgyren（Nexus 8500）：蹬墙跳'],
      ['法魂（The Convergence）', '发狂、咒死的重做，整备点恢复的做法'],
      ['EldenRingHKS', 'soulsmods：玩家动作脚本'],
    ]],
    ['程序库和素材', [
      ['fromsoftware-rs', 'vswarte（MIT / Apache-2.0）'],
      ['hudhook、Dear ImGui', 'MIT：装备工坊的界面'],
      ['SoulsFormats', 'soulsmods：读写游戏文件'],
      ['Python、.NET 8、zstd', 'PSF、MIT、BSD 许可：启动器和数据处理'],
      ['Kenney「Impact Sounds」', 'CC0：装备工坊的铁砧声'],
      ['龙藏体（Long Cang）', 'SIL OFL 1.1：标题画面的中文副标题'],
    ]],
  ];
  var CREDITS = '<p class="cr-note">感谢下面这些作者。各组件的许可文件在它们自己的文件夹里（比如 randomizer\\LICENSE.txt）。</p>' +
    CREDITS_LIST.map(function (g) {
      return '<div class="cr"><h4>' + esc(g[0]) + '</h4>' + g[1].map(function (x) {
        return '<div class="cr-item"><b>' + esc(x[0]) + '</b>　' + esc(x[1]) + '</div>';
      }).join('') + '</div>';
    }).join('');
  var curCat = 'game';
  function openModal(cat) {
    curCat = cat || curCat;
    $('#mask').classList.remove('hide');
    renderCats();
  }
  function closeModal() { $('#mask').classList.add('hide'); }
  $('#modalClose').addEventListener('click', closeModal);
  $('#mask').addEventListener('mousedown', function (e) { if (e.target === this) closeModal(); });
  function renderCats() {
    // 联机一类只在测试开关开着时显示（状态里的 coop；launcher\coop_test.txt）
    var cats = CATS.filter(function (x) { return x.key !== 'coop' || (S && S.coop); });
    if (!cats.some(function (x) { return x.key === curCat; })) curCat = cats[0].key;
    $('#cats').innerHTML = cats.map(function (c) {
      return '<button class="cat' + (c.key === curCat ? ' on' : '') + '" data-cat="' + c.key + '">' + esc(c.name) +
        (c.key === 'update' && hasUpdate(S) ? '<i class="nd"></i>' : '') + '</button>';
    }).join('');
    $$('.cat').forEach(function (b) {
      b.addEventListener('click', function () { curCat = b.getAttribute('data-cat'); renderCats(); });
    });
    var c = CATS.filter(function (x) { return x.key === curCat; })[0];
    var busy = S && S.busy;
    var html = '';
    if (c.key === 'about') {
      html = '<div class="about"><h3>DARKFORGE</h3><div>暗黑重铸 · 艾尔登法环整合包</div>' +
        '<p class="ver">整合包版本 ' + esc(S ? 'v' + S.version : '') + '</p>' +
        '<p>启动器界面基于开源项目 hyp-launcher-ui（tamikip，MIT 许可，launcher\\ui\\LICENSE-launcher-ui-shell.txt）：<br>' +
        '<button class="link url" data-url="https://github.com/tamikip/hyp-launcher-ui">github.com/tamikip/hyp-launcher-ui</button></p>' +
        '<p>网页显示用微软 WebView2（launcher\\webview2\\LICENSE.txt）。</p>' + CREDITS + '</div>';
    } else if (c.key === 'ui') {
      var hard = S && S.hasHard, w = bgWorld(), anim = store('anim') !== 'off';
      html = row('背景', hard ? '存档里有死亡以上难度的角色时默认用魇火那张，也可以换回普通的。'
                              : '现在用普通的那张。存档里有了死亡以上难度的角色后，会换成魇火那张，也可以在这里换回来。',
          '<div class="pick"><button class="pick-b' + (w === 'normal' ? ' on' : '') + '" data-bg="normal">普通</button>' +
          '<button class="pick-b' + (w === 'hard' ? ' on' : '') + '" data-bg="hard"' + (hard ? '' : ' disabled') + '>死亡以上</button></div>') +
        row('背景动画', '背景里飘动的烟雾。电脑比较卡时可以关掉。',
          '<div class="pick"><button class="pick-b' + (anim ? ' on' : '') + '" data-anim="on">开</button>' +
          '<button class="pick-b' + (anim ? '' : ' on') + '" data-anim="off">关</button></div>');
    } else {
      html = c.tools.map(function (n) {
        var d = (toolTips && toolTips[n]) || '';
        if (n === '检查更新' && updateStatusText(S)) d += '\n' + updateStatusText(S);
        return row(n, d, '<button class="btn-ghost" data-tool="' + esc(n) + '"' + (busy ? ' disabled' : '') + '>' + esc(btnText(n)) + '</button>');
      }).join('');
      if (c.key === 'game') {          // 敌人信息 mod（Souls Vision）：所有电脑都能关（2026-11-11 应作者要求）
        var ei = S && S.enemyInfo === 'off' ? 'off' : 'on';
        html += row('敌人信息 mod', '敌人头上的血条和状态条（Souls Vision），默认打开。少数电脑（多见于有两块显卡的）可能因为它无法启动游戏或读档时闪退，遇到的话在这里关掉。下次启动游戏时生效。',
          '<div class="pick"><button class="pick-b' + (ei === 'on' ? ' on' : '') + '" data-enemyinfo="on">开</button>' +
          '<button class="pick-b' + (ei === 'off' ? ' on' : '') + '" data-enemyinfo="off">关</button></div>');
      }
      if (c.key === 'save') {          // 定时备份（用户 2026-11-19：代替启动前 / 恢复前备份，默认 10 分钟，设置里能改；dfl\backup.py）
        var bm = (S && S.backupMin) || 10, mins = (S && S.backupMins) || [5, 10, 15, 30, 60], keep = (S && S.backupKeep) || 5;
        html += row('定时备份间隔（分钟）', '游戏开着时定时把存档和角色记录存成压缩包（没变就不存），退出游戏后再存一份，只留最近 ' + keep +
            ' 份。改了马上生效。',
          '<div class="pick">' + mins.map(function (m) {
            return '<button class="pick-b' + (m === bm ? ' on' : '') + '" data-bkmin="' + m + '" title="每 ' + m + ' 分钟">' + m + '</button>';
          }).join('') + '</div>');
      }
      if (c.key === 'update') {
        var ac = store('autocheck') !== 'off';
        html += row('自动检查更新', '启动器开着时，每 5 分钟在后台联网看一下有没有新版本（打开时先看一次），有的话右上角的齿轮按钮上出红点，左下角也会提示。不会自己下载，要你点了才更新。',
          '<div class="pick"><button class="pick-b' + (ac ? ' on' : '') + '" data-autocheck="on">开</button>' +
          '<button class="pick-b' + (ac ? '' : ' on') + '" data-autocheck="off">关</button></div>');
      }
    }
    $('#rows').innerHTML = html;
    $$('#rows [data-url]').forEach(function (b) {       // 用系统浏览器打开（宿主只认写死的几个网址）
      b.addEventListener('click', function () { bridge.post('openurl', { url: b.getAttribute('data-url') }); });
    });
    $$('#rows [data-bg]').forEach(function (b) {
      b.addEventListener('click', function () { store('bg', b.getAttribute('data-bg')); applyWorld(); renderCats(); });
    });
    $$('#rows [data-enemyinfo]').forEach(function (b) {
      b.addEventListener('click', function () {
        var v = b.getAttribute('data-enemyinfo');
        if (S) S.enemyInfo = v;
        bridge.post('enemyinfo', { value: v });
        renderCats();
      });
    });
    $$('#rows [data-bkmin]').forEach(function (b) {
      b.addEventListener('click', function () {
        var v = +b.getAttribute('data-bkmin');
        if (S) S.backupMin = v;
        bridge.post('backupint', { value: v });
        renderCats();
      });
    });
    $$('#rows [data-autocheck]').forEach(function (b) {
      b.addEventListener('click', function () { store('autocheck', b.getAttribute('data-autocheck')); renderCats(); });
    });
    $$('#rows [data-anim]').forEach(function (b) {
      b.addEventListener('click', function () {
        store('anim', b.getAttribute('data-anim'));
        if (window.DFSmoke) window.DFSmoke.enable(b.getAttribute('data-anim') !== 'off');
        renderCats();
      });
    });
  }
  function btnText(n) {
    return { '游戏路径': '修改', '备份存档': '备份', '恢复存档': '恢复…', '敌人设置': '设置…', '打开随机器': '打开…', '重随设置': '打开',
             '检查更新': '检查', '导入更新包': '选择更新包…', '更新日志': '打开', '常见问题': '查看', '报告 / 日志': '打开文件夹', '导出诊断包': '导出',
             'mods 文件夹': '打开', 'DLL 文件夹': '打开', '自定义配置': '编辑', '联机': '打开…', '联机设置': '编辑' }[n] || '打开';
  }
  function row(t, d, btn) {
    return '<div class="row"><div class="txt"><div class="t">' + esc(t) + '</div><div class="d">' + esc(d) + '</div></div>' + btn + '</div>';
  }

  /* ---------------- 弹窗（宿主的提示 / 确认框等，dfl\gui\app.py 的 modal；用户 2026-11-11「把目前的弹窗都接入新的ui」） ----------------
     宿主发 {type:'dialog', id, kind:'msg'|'pick'|'enemy', title, text, icon, buttons, def, cancel, ops, wide, items, sel, elite, boss, note}：
       buttons 从左到右，def 是金色的（回车），cancel 是 Esc / 右上角 × 算点了哪个（-1：Esc 不关，× 关掉算「没选」）；
       ops 是左下角点了不关窗口的按钮（回 {action:'dialogop', id, op}）。
     点了按钮回 {action:'dialog', id, result: 第几个（-1 = × 关掉没选）, pick: 列表选了第几行, e / b: 敌人设置点了哪档（没点 -1）}。
     可以叠好几层（常见问题里再弹提示），键盘只给最上面那层 */
  var ICONS = {
    info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.2"/><path d="M12 10.8v5.8M12 7.5v.1"/></svg>',
    question: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.2"/><path d="M9.5 9.4a2.6 2.6 0 1 1 3.7 2.4c-.8.4-1.2.9-1.2 1.8v.5M12 16.8v.1"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 3.6 21.4 19.8H2.6Z"/><path d="M12 9.6v4.8M12 17v.1"/></svg>',
    error: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9.2"/><path d="m9 9 6 6M15 9l-6 6"/></svg>'
  };
  var XSVG = '<svg viewBox="0 0 12 12"><path d="M2 2.8 2.8 2 6 5.2 9.2 2l.8.8L6.8 6 10 9.2l-.8.8L6 6.8 2.8 10 2 9.2 5.2 6Z"/></svg>';
  var dlgs = [];
  function topDlg() { return dlgs.length ? dlgs[dlgs.length - 1] : null; }

  function enemySec(key, s) {
    s = s || { levels: [] };
    return '<div class="en-sec" data-sec="' + key + '"><div class="en-t">' + esc(s.title) + '</div><div class="en-d">' + esc(s.desc) + '</div>' +
      '<div class="en-seg">' + (s.levels || []).map(function (l, i) {
        return '<button class="en-b' + (i === s.sel ? ' on' : '') + '" data-l="' + i + '"><b>' + esc(l.name) + '</b><small>' + esc(l.sub) + '</small></button>';
      }).join('') + '</div><div class="en-info">' + esc(s.orig) + '</div></div>';
  }

  function openDialog(m) {
    tip.classList.add('hide');
    var kind = m.kind || 'msg';
    var btns = m.buttons || ['确定'];
    var d = { id: m.id, m: m, pick: typeof m.sel === 'number' ? m.sel : 0, e: -1, b: -1, done: false };
    // 按钮有 5 个以上（联机菜单）放宽，免得最后一个挤到第二行
    var w = kind === 'enemy' ? 700 : kind === 'pick' ? 660 : m.wide ? 880 : (m.buttons || []).length >= 5 ? 760 : ((m.text || '').length > 400 ? 640 : 540);
    var icon = ICONS[m.icon] || '';
    var html = '<div class="dlg ' + kind + '" style="width:' + w + 'px" role="dialog" aria-modal="true">' +
      '<div class="dlg-head" data-drag><span data-drag>' + esc(m.title || '暗黑重铸') + '</span><button class="win-btn" data-x data-tip="关闭">' + XSVG + '</button></div>' +
      '<div class="dlg-body">' + (icon ? '<div class="dlg-ic ' + esc(m.icon) + '">' + icon + '</div>' : '') + '<div class="dlg-main">';
    if (m.text) html += '<div class="dlg-text' + (m.wide ? ' tall' : '') + (kind === 'pick' ? ' help' : '') + '">' + esc(m.text) + '</div>';
    if (kind === 'pick') {
      html += '<div class="dlg-list">' + (m.items || []).map(function (t, i) {
        return '<button class="dlg-item' + (i === d.pick ? ' on' : '') + '" data-i="' + i + '">' + esc(t) + '</button>';
      }).join('') + '</div>';
    }
    if (kind === 'enemy') html += enemySec('elite', m.elite) + enemySec('boss', m.boss) + (m.note ? '<div class="en-note">' + esc(m.note) + '</div>' : '');
    html += '</div></div><div class="dlg-foot"><div class="dlg-ops">' + (m.ops || []).map(function (o) {
      return '<button class="btn-ghost sm" data-op="' + esc(o.op) + '"' + (o.once ? ' data-once' : '') + '>' + esc(o.label) + '</button>';
    }).join('') + '</div><div class="dlg-btns">' + btns.map(function (t, i) {
      return '<button class="' + (i === m.def ? 'btn-gold' : 'btn-ghost') + '" data-b="' + i + '">' + esc(t) + '</button>';
    }).join('') + '</div></div></div>';
    var el = document.createElement('div');
    el.className = 'dlg-mask';
    el.innerHTML = html;
    app.appendChild(el);
    d.el = el;
    dlgs.push(d);

    el.querySelectorAll('[data-b]').forEach(function (b) {
      b.addEventListener('click', function () { answer(d, +b.getAttribute('data-b')); });
    });
    el.querySelector('[data-x]').addEventListener('click', function () { answer(d, m.cancel >= 0 ? m.cancel : -1); });
    el.querySelectorAll('[data-op]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (b.hasAttribute('data-once')) b.disabled = true;
        bridge.post('dialogop', { id: d.id, op: b.getAttribute('data-op') });
      });
    });
    el.querySelectorAll('.dlg-item').forEach(function (b) {
      b.addEventListener('click', function () { setPick(d, +b.getAttribute('data-i')); });
      b.addEventListener('dblclick', function () { setPick(d, +b.getAttribute('data-i')); answer(d, m.def); });
    });
    el.querySelectorAll('.en-sec').forEach(function (sec) {
      var key = sec.getAttribute('data-sec'), conf = m[key] || { levels: [] };
      sec.querySelectorAll('.en-b').forEach(function (b) {
        b.addEventListener('click', function () {
          var i = +b.getAttribute('data-l');
          sec.querySelectorAll('.en-b').forEach(function (x) { x.classList.toggle('on', x === b); });
          sec.querySelector('.en-info').textContent = (conf.levels[i] || {}).desc || '';
          if (key === 'elite') d.e = i; else d.b = i;
        });
      });
    });
    focusDlg(d);
  }
  function setPick(d, i) {
    d.pick = i;
    d.el.querySelectorAll('.dlg-item').forEach(function (x) { x.classList.toggle('on', +x.getAttribute('data-i') === i); });
    var on = d.el.querySelector('.dlg-item.on');
    if (on) on.scrollIntoView({ block: 'nearest' });
  }
  function focusDlg(d) {
    var b = d.el.querySelector('[data-b="' + d.m.def + '"]') || d.el.querySelector('[data-b]');
    if (b) b.focus();
  }
  function removeDlg(d) {
    d.done = true;
    d.el.remove();
    dlgs.splice(dlgs.indexOf(d), 1);
    var t = topDlg();
    if (t) focusDlg(t);
  }
  function answer(d, i) {
    if (d.done) return;
    removeDlg(d);
    bridge.post('dialog', { id: d.id, result: i, pick: d.pick, e: d.e, b: d.b });
  }
  function closeDialog(id) {
    dlgs.filter(function (d) { return d.id === id; }).forEach(removeDlg);
  }
  document.addEventListener('keydown', function (e) {
    var d = topDlg();
    if (!d) return;
    var m = d.m, a = document.activeElement;
    if (e.key === 'Escape') {
      e.preventDefault();
      if (m.cancel >= 0) answer(d, m.cancel);
    } else if (e.key === 'Enter') {
      if (a && a.classList && a.classList.contains('dlg-item')) { e.preventDefault(); answer(d, m.def); }
      else if (!a || !d.el.contains(a) || a.tagName !== 'BUTTON') { e.preventDefault(); answer(d, m.def); }
    } else if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && m.kind === 'pick') {
      e.preventDefault();
      var n = (m.items || []).length;
      if (n) setPick(d, Math.max(0, Math.min(n - 1, d.pick + (e.key === 'ArrowDown' ? 1 : -1))));
    } else if (e.key === 'Tab') {                 // 焦点留在最上面这层
      var f = Array.prototype.slice.call(d.el.querySelectorAll('button:not(:disabled)'));
      if (!f.length) return;
      var k = f.indexOf(a);
      e.preventDefault();
      f[(k < 0 ? 0 : k + (e.shiftKey ? f.length - 1 : 1)) % f.length].focus();
    }
  });

  /* ---------------- 宿主消息 ---------------- */
  bridge.on(function (m) {
    if (!m || !m.type) return;
    if (m.type === 'state') {
      render(m);
      autoCheck();
      if (!$('#mask').classList.contains('hide')) renderCats();
    } else if (m.type === 'changelog') renderNews(m.text);
    else if (m.type === 'toast') toast(m.text, m.error, m.ms);
    else if (m.type === 'tab') showTab(m.tab);
    else if (m.type === 'closeModal') closeModal();
    else if (m.type === 'dialog') openDialog(m);
    else if (m.type === 'dialogclose') closeDialog(m.id);
  });
  window.__df = { render: render, showTab: showTab, openModal: openModal, dialog: openDialog, dialogs: function () { return dlgs; },
                  state: function () { return S; } };   // 测试截图用
  bridge.post('ready');
})();
