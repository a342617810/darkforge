/* 背景烟雾：和游戏标题封面同一套规则（dev\title_menu\make_anim.py 的 gen_puffs）：
   64 团柔和的烟从屏幕下沿附近出来，顺同一个风向往上飘、微微荡一点，慢慢放大、淡出，16 秒一个循环（每团各自错开）。
   贴图是 make_launcher_bg.py 导出的 puff_<封面>_<k>.png（黑底亮度），在半分辨率画布上加法叠好，画布再以「加亮」混合叠到底图上。
   只平移和等比放大（用户 2026-11-05：摆动「像果冻」不要），不要火星（用户：「火星也是重复」）。 */
(function () {
  'use strict';
  var SMOKE_L = 480, FPS = 30, N = 64, PUFF = 256, STAGE_W = 1920;
  var BRIGHT = 1.8;                          // 比游戏标题画面亮一些（用户 2026-11-10「背景和烟雾整体都再亮一点」）
  var canvas = document.getElementById('smoke');
  if (!canvas || !canvas.getContext) { window.DFSmoke = { set: function () {}, enable: function () {} }; return; }
  var ctx = canvas.getContext('2d');
  var world = null, puffs = [], tex = [], on = true, raf = 0, last = 0;

  function rng(seed) {                       // mulberry32：每次启动同一组粒子
    return function () {
      seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gauss(r) { return Math.sqrt(-2 * Math.log(1 - r())) * Math.cos(2 * Math.PI * r()); }

  function gen(seed, peakMul) {
    var r = rng(seed), out = [], slots = [], k;
    for (k = 0; k < N; k++) slots.push(k);
    for (k = N - 1; k > 0; k--) { var j = Math.floor(r() * (k + 1)), t = slots[k]; slots[k] = slots[j]; slots[j] = t; }
    for (k = 0; k < N; k++) {                // 横向分格、出生时间按黄金分割撒开：不扎堆、亮度不忽明忽暗
      out.push({
        life: 240 + Math.floor(r() * 180),
        a: ((k * 0.618034) % 1) * SMOKE_L,
        x0: -300 + (slots[k] + r()) * 2520 / N,
        y0: 960 + r() * 320,
        vy: 0.25 + r() * 0.35,
        vx: 0.20 + gauss(r) * 0.10,          // 风：大家朝一边走
        amp: 6 + r() * 16, per: 180 + r() * 240, ph: r() * 6.28,
        s0: 1.5 + r() * 1.4,
        peak: (0.10 + r() * 0.10) * peakMul * BRIGHT,
        tex: Math.floor(r() * 6), rot: r() * 6.28,
      });
    }
    return out;
  }

  function draw(now) {
    raf = requestAnimationFrame(draw);
    if (now - last < 1000 / FPS - 2) return;            // 30 帧就够（烟飘得慢），省 CPU
    last = now;
    var k = canvas.width / STAGE_W;
    var frame = now / 1000 * FPS;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < puffs.length; i++) {
      var p = puffs[i];
      var t = ((frame - p.a) % SMOKE_L + SMOKE_L) % SMOKE_L;
      if (t >= p.life) continue;
      var img = tex[p.tex];
      if (!img || !img.complete || !img.naturalWidth) continue;
      var u = t / p.life;
      var x = p.x0 + p.vx * t + p.amp * Math.sin(2 * Math.PI * t / p.per + p.ph);
      var y = p.y0 - p.vy * t;
      var s = p.s0 * (1 + 0.32 * u) * k;
      var al = p.peak * Math.pow(Math.sin(Math.PI * u), 1.2);
      if (al <= 0.002) continue;
      var c = Math.cos(p.rot) * s, sn = Math.sin(p.rot) * s;
      ctx.globalAlpha = Math.min(1, al);
      ctx.setTransform(c, sn, -sn, c, x * k, y * k);
      ctx.drawImage(img, -PUFF / 2, -PUFF / 2);
    }
  }

  function start() {
    if (raf || !on || !world) return;
    last = 0;
    raf = requestAnimationFrame(draw);
  }
  function stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  window.DFSmoke = {
    /* 换封面：normal / hard */
    set: function (name) {
      if (name === world) return;
      world = name;
      var meta = (window.DF_LAYERS || {})[name] || { peak: 1, seed: 31 };
      puffs = gen(meta.seed, meta.peak);
      tex = [];
      for (var k = 0; k < 6; k++) { var im = new Image(); im.src = 'img/puff_' + name + '_' + k + '.png'; tex.push(im); }
      start();
    },
    /* 背景动画开关（设置里，存在页面自己的 localStorage） */
    enable: function (v) {
      on = !!v;
      canvas.style.display = on ? '' : 'none';
      if (on) start(); else stop();
    },
  };
  document.addEventListener('visibilitychange', function () { if (document.hidden) stop(); else start(); });
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) on = false;
})();
