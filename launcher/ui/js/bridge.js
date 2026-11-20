/* 和宿主（launcher\dfl\gui\app.py）的通信：页面 → 宿主 {action, ...}；宿主 → 页面 {type, ...}（state / changelog / toast）。
   不在 WebView2 里（直接用浏览器打开预览）时，发出的消息只打到控制台，并且自己造一份演示状态，方便调样式。 */
(function () {
  'use strict';
  var wv = window.chrome && window.chrome.webview;
  var handlers = [];

  function emit(msg) {
    handlers.forEach(function (h) { try { h(msg); } catch (e) { console.error(e); } });
  }

  var bridge = {
    live: !!wv,
    post: function (action, payload) {
      var msg = Object.assign({ action: action }, payload || {});
      if (wv) wv.postMessage(msg);
      else { console.log('[bridge]', msg); demoReply(msg); }
    },
    on: function (h) { handlers.push(h); },
  };

  if (wv) {
    wv.addEventListener('message', function (e) { emit(e.data); });
  }

  /* ---------------- 演示（浏览器预览） ---------------- */
  var demo = {
    type: 'state', version: '0.10.1', busy: false, hasHard: true, randomizerOk: true, mode: 'rand', backupMin: 10, backupMins: [5, 10, 15, 30, 60], backupKeep: 5,
    cards: {
      path: { value: 'E:\\SteamLibrary\\steamapps\\common\\ELDEN RING', accent: 'gold', tip: '' },
      rand: { value: '2026-11-07 17:07', accent: 'ok', tip: '随机器输出：2026-11-07 17:07（敌人随机）' },
      last: { value: '2026-11-10 23:49:00', accent: 'gold', tip: '' },
    },
    subs: { launchV: '无敌人随机', launchR: '敌人随机', randEnemy: '换一个新种子，不启动游戏', randItems: '骨灰、开局装备，下次启动重抽' },
    run: { title: '', player: true, lines: ['选择上面的按钮开始。'], pct: null, error: false },
  };
  var demoDlg = 0;
  var lv = function (n, s, d) { return { name: n, sub: s, desc: d }; };
  var DEMO_DLG = {
    '备份存档': { kind: 'msg', title: '暗黑重铸', icon: 'info', text: '已备份到：\nE:\\Darkforge\\存档备份\\2026-11-11_21-30-05\n\n要换回来时点「恢复存档」，选这份。', buttons: ['确定'], def: 0, cancel: 0 },
    '一键重随物品': { kind: 'msg', title: '一键重随物品', icon: 'question', text: '骨灰的位置、职业的开局装备、开局遗物只在第一次启动时抽一次，之后一直固定。\n\n确定后，下次启动时会重新抽一次，之后再固定下来。\n（开局装备、遗物和骨灰只对之后新建的角色生效。）', buttons: ['确定', '取消'], def: 0, cancel: 1 },
    '导出诊断包': { kind: 'msg', title: '暗黑重铸 · 游戏还在运行', icon: 'warn', text: '检测到 eldenring.exe 还在运行：\n\n  进程号 1234，启动于 11-11 21:30:05，没有窗口（后台），无响应\n\n如果游戏其实已经关了，点「是」强制结束这个进程再继续。', buttons: ['是', '否'], def: 1, cancel: 1 },
    '恢复存档': { kind: 'pick', title: '恢复存档：手动选择备份', icon: '', text: '定时 = 游戏开着时自动存的（「退出游戏后」那份就是退出时的样子）；启动前 / 恢复前 = 以前的版本自动存的（定时备份攒满 5 份后自动删掉）；存档备份 = 点「备份存档」存的。\n存档和角色记录一起换回去，那之后的游戏进度会丢失。',
                  items: ['2026-11-11 22:40:12   定时 · 退出游戏后   （存档 1 个 + 角色记录 3 个）', '2026-11-11 22:30:05   定时 · 游戏中   （存档 1 个 + 角色记录 3 个）', '2026-11-11 21:30:05   启动前 · 敌人随机   （存档 1 个 + 角色记录 3 个）', '2026-11-10 23:49:00   启动前 · 无敌人随机   （存档 1 个 + 角色记录 3 个）', '2026-11-09 18:02:11   存档备份   （存档 1 个）'],
                  sel: 0, buttons: ['恢复选中的这份', '取消'], def: 0, cancel: 1 },
    '敌人设置': { kind: 'enemy', title: '暗黑重铸 · 敌人设置', icon: '',
                  elite: { title: '精英怪比例', desc: '敌人随机时，普通敌人里有多少换成精英怪（越往后的地区越多）。', sel: 2, orig: '普通敌人里精英怪的比例：前期 2.5%，……',
                           levels: [lv('最少', '不额外放', '不额外放精英。'), lv('少', '× 0.5', '× 0.5'), lv('默认', '× 1', '× 1'), lv('较多', '× 1.5', '× 1.5'), lv('多', '× 2', '× 2'), lv('很多', '× 3', '× 3')] },
                  boss: { title: '头目出现在普通敌人位置', desc: '开启后，敌人随机时有一部分普通敌人会换成随机头目。', sel: 0, orig: '关闭：普通敌人的位置只会出现普通敌人和精英怪。',
                          levels: [lv('关闭', '不出现', '关闭'), lv('很少', '约 1%', '约 1%'), lv('少量', '约 3%', '约 3%'), lv('较多', '约 6%', '约 6%'), lv('很多', '约 10%', '约 10%')] },
                  note: '这两项只影响敌人随机：保存后要点「一键重随敌人」才会生效。', buttons: ['保存并重随敌人', '只保存', '取消'], def: 0, cancel: 2 },
    '常见问题': { kind: 'msg', wide: true, title: '常见问题', icon: '', text: '问：我想重新随机敌人怎么办？\n1. 点「一键重随敌人」。\n2. 点「一键启动（敌人随机）」开始玩。',
                  ops: [{ op: 'bk', label: '打开自动备份文件夹' }, { op: 'save', label: '打开存档文件夹' }], buttons: ['关闭'], def: 0, cancel: 0 },
  };
  function demoReply(msg) {
    if (msg.action === 'ready') {
      setTimeout(function () { emit(demo); }, 50);
      setTimeout(function () {
        emit({ type: 'changelog', text: 'v0.10.1（未发布）\n----\n【新增】\n- 卢恩银行：存取身上的卢恩。\n- 更新包：启动器新增「导入更新包」。\n\n【调整】\n- 说明书整理了一遍。\n\nv0.10.0（2026-11-10）\n----\n【新增】\n- 骨灰稀有度。\n  - 带 1~2 条词条。\n' });
      }, 80);
    } else if (msg.action === 'checkupdate') {
      setTimeout(function () {
        demo.update = { status: 'available', cur: demo.version, latest: '0.10.2', size: 3670016, checked: '2026-11-11 21:30:05', error: '',
                        notes: 'v0.10.2（2026-11-12）\n【修正】\n- 演示用的更新内容。' };
        emit(JSON.parse(JSON.stringify(demo)));
      }, 600);
    } else if (msg.action === 'tool' && DEMO_DLG[msg.name]) {
      setTimeout(function () { emit(Object.assign({ type: 'dialog', id: ++demoDlg }, DEMO_DLG[msg.name])); }, 30);
    } else if (msg.action === 'launch' || msg.action === 'randenemy') {
      var s = JSON.parse(JSON.stringify(demo));
      s.busy = true; s.run = { title: '一键启动', player: true, lines: ['正在准备启动（敌人随机）……', '正在生成这一局的游戏数据……'], pct: 0, error: false };
      emit(s);
      var p = 0;
      var t = setInterval(function () {
        p += 9; s.run.pct = Math.min(100, p);
        if (p >= 100) { clearInterval(t); s.busy = false; s.run.lines.push('游戏已启动。'); s.run.pct = null; }
        emit(JSON.parse(JSON.stringify(s)));
      }, 300);
    }
  }

  window.bridge = bridge;
})();
