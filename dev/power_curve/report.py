# -*- coding: utf-8 -*-
"""把 model.py 的 result.json 画成一个自包含的交互式网页（report.html）：主图 = 各档的战斗力指数 / 砍几刀 / 能挨几下，
原版一条灰线作基准，DR 各难度一条线 + 10%~90% 运气区间；下面是玩家成长（等级、血量、攻击力、减伤、主力武器稀有度、护符 / 防具词条 / 异常的影响）和数据表。
下面还有「目标和调整建议」（DR 普通难度 ÷ 原版，和目标区间比，算敌人血量该怎么调）和「词条强度排行」（每个词条让战斗力指数乘多少）。
用法：python report.py [result.json] [report.html]"""
import html as H, json, math, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'result.json')
dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'report.html')
r = json.load(open(src, encoding='utf-8'))
SHORT = ['前期', '利耶尼亚/盖利德', '王城/山顶', '雪原/圣树', 'DLC 前中期', 'DLC 后期']
keep = ('h2k', 'h2d', 'idx', 'ar', 'upgrade', 'rarity', 'hp', 'neg', 'level', 'tal', 'talx', 'armx', 'stx', 'stw', 'bh2k', 'bh2d', 'bidx')
series = []
for s in r['series']:
    # 旧的 result*.json 里普通档叫「普通（原版）」
    d = {'mode': s['mode'], 'build': s['build'], 'diff': '普通' if s['difficulty'] == '普通（原版）' else s['difficulty']}
    for k in keep:
        for q in ('', '_p10', '_p90'):
            if k + q in s:
                d[k + q] = [None if v is None else round(v, 4) for v in s[k + q]]
    series.append(d)


def med(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def target_table(metric='idx', ratio_key='target_ratio', hp_key='normal', who='敌人'):
    """各档：原版、DR 普通难度的指数（三套加点的中位数），DR ÷ 原版，和目标区间比；血量 ×k 让比值回到目标中间。
    metric = idx（普通敌人）/ bidx（Boss，对应 enemy_hp_band.boss）"""
    lo, hi = r.get(ratio_key) or (1.0, 1.5)
    mid = (lo + hi) / 2
    cur = ((r.get('enemy_hp_band') or {}).get(hp_key) or [])
    head = ['档', '原版', 'DR 不随机', 'DR 随机', 'DR ÷ 原版（不随机 / 随机）', '判断', who + '血量该 ×', 'enemy_hp_band.%s 现在 → 建议' % hp_key]
    rows = []
    for b, name in enumerate(SHORT[:len(r['bands'])]):
        van = med([(s.get(metric) or [None] * 9)[b] for s in r['series'] if s['mode'] == '原版'])
        dr = [med([(s.get(metric) or [None] * 9)[b] for s in r['series'] if s['mode'] == m and s['difficulty'] == '普通'])
              for m in ('DR 不随机敌人', 'DR 随机敌人')]
        ratio = [x / van if x and van else None for x in dr]
        rr_ = med(ratio)
        if rr_ is None:
            rows.append([name, '–', '–', '–', '–', '–', '–', '–'])
            continue
        verdict = '偏易' if rr_ > hi else '偏难' if rr_ < lo else '合适'
        k = rr_ / mid
        c = cur[b] if b < len(cur) else None
        rows.append([name, '%.2f' % van] + ['%.2f' % x if x else '–' for x in dr] + [' / '.join('%.2f' % x if x else '–' for x in ratio), verdict,
                     '×%.2f' % k if verdict != '合适' else '不用调', '%g → %.1f' % (c, c * k) if c is not None and verdict != '合适' else ('%g' % c if c is not None else '–')])
    if metric == 'bidx':
        return {'head': head, 'rows': [[H.escape(str(x)) for x in row] for row in rows],
                'sub': ('Boss：和打普通敌人同一身装备，能挨几下算上圣杯瓶（各档 %s 瓶，每瓶回血量上限的 %g）。目标：DR 普通难度是原版的 %g～%g 倍；'
                        'enemy_hp_band.boss 是按 Boss 自己的位置乘的倍率，建议值同样只是大致。模型不算躲招，所以 Boss 指数只适合比较「容错」，不是能不能打过。'
                        % (' / '.join(str(x) for x in r['assume'].get('boss_flasks', [])), r['assume'].get('flask_heal', 0.5), lo, hi))}
    sub = ('目标：DR 普通难度的战斗力指数是原版的 %g～%g 倍。战斗力指数和敌人血量成反比（砍几刀跟着血量走），所以偏离目标时，敌人血量乘「比值 ÷ 目标中间值」就回到中间；'
           'enemy_hp_band 是按地区中位数加的，建议值只是大致，改完重跑 make_inputs.py → model.py 再看。也可以改目标：model.py 的 ASSUME[\'target_ratio\']。' % (lo, hi))
    return {'head': head, 'rows': [[H.escape(str(x)) for x in row] for row in rows], 'sub': sub}


def affix_table():
    a = r.get('affix_rank') or {'rows': [], 'bands_at': []}
    RN = ['普通', '稀有', '史诗', '传说']
    KIND = {'auto': '读参数', 'manual': '折算', 'none': '不算'}
    inc = [[(x['gain'][k] - 1) for x in a['rows'] if x['kind'] != 'none' and x['gain'][k] and x['gain'][k] > 1.0001] for k in range(4)]
    medi = [statistics.median(v) if v else 0.0 for v in inc]
    out = []
    for x in sorted(a['rows'], key=lambda x: -max([g for g in x['gain'] if g] or [1.0])):
        g = x['gain']
        flag = []
        if x['kind'] == 'none':
            flag.append('不算')
        else:
            if any(g[k] and g[k] - 1 > 3 * medi[k] > 0 for k in range(4)):
                flag.append('偏强')
            if any(g[k] and g[k] < 0.999 for k in range(4)):
                flag.append('有负面')
            if all(not g[k] or abs(g[k] - 1) < 1e-4 for k in range(4)):
                flag.append('参考玩家吃不到')
        out.append([x['name'], x['where'], x['group'], KIND.get(x['kind'], x['kind'])] + ['×%.3f' % v if v else '–' for v in g] +
                   ['、'.join(flag), x.get('note', '')])
    head = ['词条', '出在', '组', '怎么算'] + RN + ['标记', '说明']
    at = a.get('bands_at') or []
    sub = ('每个词条单独加到参考玩家身上，战斗力指数乘多少（×1.10 = 强 10%%）。参考玩家：力敏加点、原版长剑按原版常见进度强化、防具减伤 40%%，'
           '普通 / 稀有 / 史诗 / 传说分别放在 %s（这个稀有度掉得最多的那档），对那一档的中位敌人。'
           '「偏强」= 比同稀有度词条的中位提升高 3 倍以上；「读参数」直接按游戏参数算，「折算」按 dev/power_curve/affix_power.json 的估计，'
           '「不算」是对单挑普通敌人没影响的（移动、弓箭、法术、专注值等）；「参考玩家吃不到」是力敏近战用不上的（智力、信仰加点，只加魔力伤害、只在防御时生效等）。') % ' / '.join(SHORT[b] for b in at)
    return {'head': head, 'rows': [[H.escape(str(c)) for c in row] for row in out], 'sub': sub, 'median': ['%.3f' % (1 + m) for m in medi]}


def seeds_table():
    """seeds.py 的 seeds_summary.json（和 result.json 放一起）：换几个敌人随机种子，DR 随机敌人普通难度 ÷ 原版；没有就 None"""
    p = os.path.join(os.path.dirname(os.path.abspath(src)), 'seeds_summary.json')
    if not os.path.isfile(p):
        return None
    s = json.load(open(p, encoding='utf-8'))
    nb = len(r['bands'])
    rows = []
    for m, who in (('idx', '普通敌人'), ('bidx', 'Boss')):
        for x in s['rows']:
            rows.append([who, x['label']] + ['×%.2f' % v if v else '–' for v in x[m][:nb]])
        vals = [[x[m][b] for x in s['rows'] if x[m][b]] for b in range(nb)]
        rows.append([who, '范围'] + ['%.2f～%.2f' % (min(v), max(v)) if v else '–' for v in vals])
    sub = ('DR 随机敌人（普通难度）÷ 原版的战斗力指数（三套加点的中位数），每行一份随机器输出：不同的敌人随机种子，各自重随一次装备、模拟 %d 次。'
           '普通敌人一档有几百个位置，换种子变化小；Boss 一档只有十几到几十个位置，换到哪个 Boss 差别很大，看 Boss 要看「范围」那行。'
           '重跑：dev/power_curve/rand_seeds.ps1 出种子，seeds.py 跑模型和汇总。' % s.get('runs', 0))
    return {'head': ['', '敌人随机'] + SHORT[:nb], 'rows': [[H.escape(str(c)) for c in row] for row in rows], 'sub': sub}


data = {'bands': r['bands'], 'short': SHORT[:len(r['bands'])], 'series': series, 'assume': r['assume'], 'seeds': seeds_table(),
        'enemies': r['enemies'], 'kill_ratio': r['kill_ratio'], 'slots': r['talisman_slots'], 'scenario': r.get('scenario', ''),
        'target': target_table(), 'btarget': target_table('bidx', 'boss_target_ratio', 'boss', 'Boss '), 'affix': affix_table(), 'power': r.get('power_assume') or {}}

HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>战斗力曲线</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --ink-1: #0b0b0b; --ink-2: #52514e; --ink-muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --ring: rgba(11,11,11,0.10); --van: #898781;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4; --s6: #008300; --s7: #6250d6; --s8: #e34948;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --ink-1: #f0efec; --ink-2: #c3c2b7; --ink-muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10); --van: #a8a7a0;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #008300; --s7: #9085e9; --s8: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface-1: #1a1a19; --ink-1: #f0efec; --ink-2: #c3c2b7; --ink-muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10); --van: #a8a7a0;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #008300; --s7: #9085e9; --s8: #e66767;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink-1); font: 15px/1.6 system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 28px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; font-weight: 650; }
h2 { font-size: 18px; margin: 36px 0 10px; font-weight: 650; }
.lede { color: var(--ink-2); margin: 0 0 20px; max-width: 760px; }
.scn { margin: -8px 0 18px; padding: 8px 12px; border: 1px solid var(--ring); border-radius: 8px; background: var(--surface-1); color: var(--ink-1); font-size: 14px; max-width: 760px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
.tile { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 10px; padding: 14px 16px; }
.tile .v { font-size: 24px; font-weight: 650; line-height: 1.25; }
.tile .k { color: var(--ink-2); font-size: 13px; margin-top: 4px; }
.filters { position: sticky; top: 0; z-index: 5; background: var(--page); padding: 12px 0; display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; border-bottom: 1px solid var(--grid); margin-top: 24px; }
@media (max-width: 720px) { .filters { position: static; } }
.group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.group > span { color: var(--ink-muted); font-size: 13px; margin-right: 2px; }
.seg { display: inline-flex; border: 1px solid var(--ring); border-radius: 8px; overflow: hidden; }
.seg button { border: 0; background: var(--surface-1); color: var(--ink-2); padding: 5px 11px; font: inherit; font-size: 13px; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--ring); }
.seg button[aria-pressed="true"] { background: var(--ink-1); color: var(--page); }
.chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--ring); border-radius: 999px; padding: 3px 10px; font-size: 13px; cursor: pointer; background: var(--surface-1); color: var(--ink-2); user-select: none; }
.chip input { margin: 0; accent-color: var(--ink-1); }
.sw { width: 10px; height: 10px; border-radius: 3px; display: inline-block; flex: none; }
.card { background: var(--surface-1); border: 1px solid var(--ring); border-radius: 12px; padding: 16px 16px 8px; margin-top: 12px; position: relative; }
.card h3 { margin: 0 0 2px; font-size: 15px; font-weight: 650; }
.card .sub { color: var(--ink-2); font-size: 13px; margin: 0 0 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 13px; color: var(--ink-2); margin: 4px 0 6px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.chart { width: 100%; }
.chart svg { display: block; width: 100%; overflow: visible; }
.chart svg:focus { outline: none; }
.chart svg:focus-visible { outline: 2px solid var(--axis); outline-offset: 4px; border-radius: 4px; }
.grid4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.tip { position: absolute; pointer-events: none; background: var(--surface-1); border: 1px solid var(--ring); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.12); padding: 8px 10px; font-size: 12.5px; color: var(--ink-1); min-width: 180px; display: none; z-index: 4; }
.tip .t { font-weight: 650; margin-bottom: 4px; }
.tip .row { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.tip .row b { font-weight: 600; margin-left: auto; padding-left: 12px; font-variant-numeric: tabular-nums; }
.tip .row i { color: var(--ink-muted); font-style: normal; font-variant-numeric: tabular-nums; }
details { margin-top: 14px; }
summary { cursor: pointer; color: var(--ink-2); font-size: 14px; }
.tablewrap { overflow-x: auto; }
table { border-collapse: collapse; font-size: 13px; margin-top: 8px; min-width: 560px; }
th, td { border-bottom: 1px solid var(--grid); padding: 6px 10px; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
th { color: var(--ink-2); font-weight: 600; }
ul.notes { color: var(--ink-2); padding-left: 20px; margin: 6px 0; }
ul.notes li { margin: 4px 0; }
code { font-size: 12.5px; background: var(--surface-1); border: 1px solid var(--ring); border-radius: 4px; padding: 1px 5px; }
</style>
</head>
<body>
<main>
<h1>战斗力曲线</h1>
<p class="lede">按地区档位推图时，玩家打到每一档一半的状态，对这一档的普通敌人算：<b>砍几刀</b>能杀掉一个、<b>能挨几下</b>才会死；
<b>战斗力指数</b> = 能挨几下 ÷ 砍几刀，越高越轻松。灰线是原版游戏，彩色线是 Dark Reforged 的各档局内难度，浅色带是掉落运气的 10%～90% 区间（__RUNS__ 次模拟）。
适合横向比较（原版 vs DR、难度 vs 难度），不是绝对难度——假设见页面最后。</p>

<p class="scn" id="scn" hidden></p>
<div class="tiles" id="tiles"></div>

<div class="filters" role="group" aria-label="筛选">
  <div class="group"><span>加点</span><div class="seg" id="f-build"></div></div>
  <div class="group"><span>敌人</span><div class="seg" id="f-mode"></div></div>
  <div class="group"><span>指标</span><div class="seg" id="f-metric"></div></div>
  <div class="group" id="f-diff"><span>难度</span></div>
</div>

<div class="card">
  <h3 id="main-title"></h3>
  <p class="sub" id="main-sub"></p>
  <div class="legend" id="main-legend"></div>
  <div class="chart" id="main-chart"></div>
  <div class="tip" id="main-tip" role="status"></div>
</div>

<h2>玩家成长（DR 普通难度 vs 原版）</h2>
<div class="grid4" id="growth"></div>

<details>
  <summary>数据表（当前筛选：中位数，括号里是 10%～90% 区间）</summary>
  <div class="tablewrap"><table id="table"></table></div>
</details>

<h2>目标和调整建议</h2>
<p class="lede" id="target-sub"></p>
<div class="tablewrap"><table id="target"></table></div>

<h3>Boss</h3>
<p class="lede" id="btarget-sub"></p>
<div class="tablewrap"><table id="btarget"></table></div>

<div id="seeds-wrap" hidden>
<h3>换几个敌人随机种子</h3>
<p class="lede" id="seeds-sub"></p>
<div class="tablewrap"><table id="seeds"></table></div>
</div>

<h2>词条强度排行</h2>
<p class="lede" id="affix-sub"></p>
<details open>
  <summary>全部词条（按最高一档的提升排序）</summary>
  <div class="tablewrap"><table id="affix"></table></div>
</details>

<h2>怎么算的、有哪些假设</h2>
<ul class="notes" id="notes"></ul>
</main>
<script>
const DATA = __DATA__;
const TIER_SLOT = {'普通': 1, '大师': 2, '死亡': 3, '不可能': 4, '困难': 5, '进阶': 6, '休闲': 7, '轻松': 8};
const TIER_ORDER = ['轻松', '休闲', '普通', '进阶', '困难', '大师', '死亡', '不可能'];
const METRICS = {
  idx: {name: '战斗力指数', sub: '能挨几下 ÷ 砍几刀（对数刻度，越高越轻松）', log: true, fmt: v => v.toFixed(v < 10 ? 2 : 1)},
  h2k: {name: '砍几刀', sub: '杀一个这一档的普通敌人要几刀（单手轻攻击，最少 1 刀；越低越轻松）', log: false, fmt: v => v.toFixed(1) + ' 刀'},
  h2d: {name: '能挨几下', sub: '这一档的普通敌人打几下能打死你（越高越轻松）', log: false, fmt: v => v.toFixed(1) + ' 下'},
  bidx: {name: 'Boss 指数', sub: '打这一档的 Boss：能挨几下（含圣杯瓶）÷ 砍几刀（对数刻度，越高越轻松；不算躲招，只比容错）', log: true, fmt: v => v.toFixed(v < 10 ? 2 : 1)},
  bh2k: {name: 'Boss 砍几刀', sub: '打死这一档的 Boss 要几刀（中位数，越低越轻松）', log: true, fmt: v => v.toFixed(0) + ' 刀'},
  bh2d: {name: 'Boss 能挨几下', sub: '这一档的 Boss 打几下能打死你，算上圣杯瓶（越高越轻松）', log: false, fmt: v => v.toFixed(1) + ' 下'},
};
const RAR = ['普通', '稀有', '史诗', '传说'];
const state = {build: '力敏', mode: 'DR 随机敌人', metric: 'idx', diffs: new Set(['普通', '大师', '死亡', '不可能'])};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const color = d => d === '原版' ? css('--van') : css('--s' + TIER_SLOT[d]);
const label = d => d;
const find = (mode, build, diff) => DATA.series.find(s => s.mode === mode && s.build === build && (mode === '原版' || s.diff === diff));
const esc = s => String(s).replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));

function seg(id, opts, key) {
  const el = document.getElementById(id);
  el.innerHTML = '';
  for (const [v, t] of opts) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = t; b.setAttribute('aria-pressed', state[key] === v);
    b.onclick = () => { state[key] = v; render(); };
    el.appendChild(b);
  }
}

function tiles() {
  const out = [];
  const van = find('原版', state.build);
  const nor = find(state.mode, state.build, '普通');
  const ratio = nor.idx.map((v, i) => v / van.idx[i]);
  const arR = nor.ar.map((v, i) => v / van.ar[i]);
  const best = DATA.bands.map((_, i) => {
    let bt = null, bd = 1e9;
    for (const t of TIER_ORDER) { const s = find(state.mode, state.build, t); const d = Math.abs(Math.log(s.idx[i] / van.idx[i])); if (d < bd) { bd = d; bt = t; } }
    return label(bt);
  });
  const cnt = {}; best.forEach(b => cnt[b] = (cnt[b] || 0) + 1);
  const top = Object.entries(cnt).sort((a, b) => b[1] - a[1]);
  const vanIdx = van.idx;
  const hard = vanIdx.indexOf(Math.min(...vanIdx));
  const mm = a => Math.min(...a).toFixed(1) + '～' + Math.max(...a).toFixed(1);
  out.push(['比原版轻松 ' + mm(ratio) + ' 倍', 'DR 普通难度的战斗力指数 ÷ 原版（各档）']);
  out.push(['和原版一样难：' + top[0][0], '每档最接近原版的难度：' + best.join(' · ')]);
  out.push(['攻击力 ' + mm(arR) + ' 倍', '武器攻击力是原版的几倍；物理减伤 ' + Math.round(Math.min(...nor.neg) * 100) + '%～' + Math.round(Math.max(...nor.neg) * 100) + '%（原版约 ' + Math.round(van.neg[2] * 100) + '%）；防具词条 ×' + mm(nor.armx) + '、护符 ×' + mm(nor.talx) + '（原版 ×' + mm(van.talx) + '）']);
  out.push(['最难的一段：' + DATA.short[hard], '原版和 DR 都是这一档最吃力（敌人血量比上一档高 2 倍多）']);
  document.getElementById('tiles').innerHTML = out.map(([v, k]) => '<div class="tile"><div class="v">' + esc(v) + '</div><div class="k">' + esc(k) + '</div></div>').join('');
}

function niceTicks(lo, hi, n) {
  const span = hi - lo, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
  const t = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) t.push(+v.toFixed(6)); return t;
}

function lineChart(host, tip, opt) {
  const W = Math.max(320, host.clientWidth), H = opt.height || 300, m = {l: 46, r: opt.labels ? 76 : 14, t: 12, b: 46};
  const n = DATA.bands.length, iw = W - m.l - m.r, ih = H - m.t - m.b;
  const vals = [];
  for (const s of opt.series) for (const k of ['v', 'lo', 'hi']) (s[k] || []).forEach(v => { if (v != null && isFinite(v)) vals.push(v); });
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (opt.min != null) lo = Math.min(lo, opt.min);
  if (opt.max != null) hi = Math.max(hi, opt.max);
  let yf, ticks;
  if (opt.log) {
    lo = Math.max(0.05, lo * 0.85); hi = hi * 1.15;
    const L0 = Math.log(lo), L1 = Math.log(hi);
    yf = v => m.t + ih - (Math.log(Math.max(v, lo)) - L0) / (L1 - L0) * ih;
    ticks = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200].filter(t => t >= lo && t <= hi);
  } else {
    const pad = (hi - lo) * 0.08 || 1; lo = opt.min != null ? opt.min : Math.max(0, lo - pad); hi = hi + pad;
    yf = v => m.t + ih - (v - lo) / (hi - lo) * ih;
    ticks = opt.ticks || niceTicks(lo, hi, 5);
  }
  const xf = i => m.l + (n === 1 ? iw / 2 : i * iw / (n - 1));
  const surf = css('--surface-1');
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" height="' + H + '" tabindex="0" role="img" aria-label="' + esc(opt.title || '') + '">';
  for (const t of ticks) s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + yf(t) + '" y2="' + yf(t) + '" stroke="' + css('--grid') + '" stroke-width="1"/>' +
    '<text x="' + (m.l - 8) + '" y="' + (yf(t) + 4) + '" text-anchor="end" font-size="11.5" fill="' + css('--ink-muted') + '" style="font-variant-numeric:tabular-nums">' + esc(opt.tickFmt ? opt.tickFmt(t) : t) + '</text>';
  s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + (m.t + ih) + '" y2="' + (m.t + ih) + '" stroke="' + css('--axis') + '"/>';
  const fs = iw / (n - 1) < 70 ? 11 : 12;          // 窄图：地区名一律两行、字小一点
  DATA.short.forEach((b, i) => {
    const parts = b.includes('/') ? [b.slice(0, b.indexOf('/') + 1), b.slice(b.indexOf('/') + 1)] : b.includes(' ') ? b.split(' ') : [b];
    s += '<text x="' + xf(i) + '" y="' + (m.t + ih + 18) + '" text-anchor="middle" font-size="' + fs + '" fill="' + css('--ink-2') + '">' +
      parts.map((p, k) => '<tspan x="' + xf(i) + '" dy="' + (k ? fs + 2 : 0) + '">' + esc(p) + '</tspan>').join('') + '</text>';
  });
  for (const se of opt.series) if (se.lo && se.hi) {
    const top = se.hi.map((v, i) => v == null ? null : [xf(i), yf(v)]).filter(Boolean);
    const bot = se.lo.map((v, i) => v == null ? null : [xf(i), yf(v)]).filter(Boolean).reverse();
    if (top.length > 1) s += '<path d="M' + top.concat(bot).map(p => p.join(',')).join('L') + 'Z" fill="' + se.color + '" opacity="0.14"/>';
  }
  for (const se of opt.series) {
    const pts = se.v.map((v, i) => v == null ? null : [xf(i), yf(v)]);
    const d = pts.filter(Boolean).map((p, k) => (k ? 'L' : 'M') + p.join(',')).join('');
    s += '<path d="' + d + '" fill="none" stroke="' + se.color + '" stroke-width="' + (se.base ? 2.5 : 2) + '" stroke-linejoin="round" stroke-linecap="round"/>';
    for (const p of pts) if (p) s += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="4" fill="' + se.color + '" stroke="' + surf + '" stroke-width="2"/>';
  }
  if (opt.labels) {
    const ends = opt.series.map(se => { const i = se.v.length - 1; return {y: yf(se.v[i]), t: se.name}; }).sort((a, b) => a.y - b.y);
    for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 15) ends[k].y = ends[k - 1].y + 15;
    for (const e of ends) s += '<text x="' + (xf(n - 1) + 10) + '" y="' + (e.y + 4) + '" font-size="12" fill="' + css('--ink-2') + '">' + esc(e.t) + '</text>';
  }
  s += '<line class="xh" x1="0" x2="0" y1="' + m.t + '" y2="' + (m.t + ih) + '" stroke="' + css('--axis') + '" stroke-width="1" visibility="hidden"/>';
  s += '<rect class="hit" x="' + m.l + '" y="' + m.t + '" width="' + iw + '" height="' + ih + '" fill="transparent"/></svg>';
  host.innerHTML = s;
  const svg = host.querySelector('svg'), xh = svg.querySelector('.xh');
  let cur = -1;
  const show = i => {
    cur = i;
    const x = xf(i);
    xh.setAttribute('x1', x); xh.setAttribute('x2', x); xh.setAttribute('visibility', 'visible');
    const rows = opt.series.map(se => '<div class="row"><span class="sw" style="background:' + se.color + '"></span>' + esc(se.name) +
      '<b>' + (se.v[i] == null ? '—' : esc(opt.fmt(se.v[i]))) + '</b>' + (se.lo && se.lo[i] != null ? ' <i>（' + esc(opt.fmt(se.lo[i])) + '～' + esc(opt.fmt(se.hi[i])) + '）</i>' : '') + '</div>').join('');
    tip.innerHTML = '<div class="t">' + esc(DATA.bands[i]) + '</div>' + rows;
    tip.style.display = 'block';
    const box = host.getBoundingClientRect(), card = tip.parentElement.getBoundingClientRect();
    const px = box.left - card.left + x * box.width / W, py = box.top - card.top + m.t;
    const left = px + 14 + tip.offsetWidth > card.width ? px - 14 - tip.offsetWidth : px + 14;
    tip.style.left = Math.max(4, left) + 'px'; tip.style.top = py + 'px';
  };
  const hide = () => { cur = -1; xh.setAttribute('visibility', 'hidden'); tip.style.display = 'none'; };
  svg.addEventListener('mousemove', ev => {
    const pt = svg.getBoundingClientRect(), x = (ev.clientX - pt.left) * W / pt.width;
    if (x < m.l - 20 || x > W - m.r + 20) return hide();
    show(Math.max(0, Math.min(n - 1, Math.round((x - m.l) / (iw / (n - 1))))));
  });
  svg.addEventListener('mouseleave', hide);
  svg.addEventListener('focus', () => show(cur < 0 ? 0 : cur));
  svg.addEventListener('blur', hide);
  svg.addEventListener('keydown', ev => {
    if (ev.key === 'ArrowRight') { show(Math.min(n - 1, cur + 1)); ev.preventDefault(); }
    if (ev.key === 'ArrowLeft') { show(Math.max(0, cur - 1)); ev.preventDefault(); }
    if (ev.key === 'Escape') hide();
  });
}

function legend(el, series) {
  el.innerHTML = series.length < 2 ? '' : series.map(s => '<span><span class="sw" style="background:' + s.color + '"></span>' + esc(s.name) + '</span>').join('');
}

function render() {
  seg('f-build', Object.keys({'力敏': 1, '智力': 1, '信仰': 1}).map(b => [b, b]), 'build');
  seg('f-mode', [['DR 不随机敌人', '不随机'], ['DR 随机敌人', '随机']], 'mode');
  seg('f-metric', Object.entries(METRICS).map(([k, v]) => [k, v.name]), 'metric');
  const fd = document.getElementById('f-diff');
  fd.querySelectorAll('label').forEach(x => x.remove());
  for (const t of TIER_ORDER) {
    const lb = document.createElement('label'); lb.className = 'chip';
    lb.innerHTML = '<input type="checkbox"' + (state.diffs.has(t) ? ' checked' : '') + '><span class="sw" style="background:' + color(t) + '"></span>' + esc(label(t));
    lb.querySelector('input').onchange = e => { e.target.checked ? state.diffs.add(t) : state.diffs.delete(t); render(); };
    fd.appendChild(lb);
  }
  tiles();
  const M = METRICS[state.metric];
  const van = find('原版', state.build);
  const ser = [{name: '原版', color: color('原版'), v: van[state.metric], base: true}];
  for (const t of TIER_ORDER) if (state.diffs.has(t)) {
    const s = find(state.mode, state.build, t);
    ser.push({name: label(t), color: color(t), v: s[state.metric], lo: s[state.metric + '_p10'], hi: s[state.metric + '_p90']});
  }
  document.getElementById('main-title').textContent = M.name + ' · ' + state.build + ' · ' + (state.mode === 'DR 随机敌人' ? '随机敌人' : '不随机敌人');
  document.getElementById('main-sub').textContent = M.sub;
  legend(document.getElementById('main-legend'), ser);
  lineChart(document.getElementById('main-chart'), document.getElementById('main-tip'),
            {series: ser, log: M.log, fmt: M.fmt, labels: ser.length <= 5, title: M.name, height: 330, min: M.log ? null : 0});
  // 成长
  const nor = find(state.mode, state.build, '普通');
  const G = [
    ['等级', '打到这一档一半时（每个普通敌人杀一次 + Boss 全杀，卢恩按难度加成）', 'level', v => Math.round(v) + ' 级', null, false],
    ['血量', '生命力加点换算的血量上限（不含护符）', 'hp', v => Math.round(v), null, false],
    ['武器攻击力', '主力武器的攻击力（各属性合计，单手，不含护符）', 'ar', v => Math.round(v), null, true],
    ['物理减伤', '四件防具合计（越高受到的伤害越少）', 'neg', v => Math.round(v * 100) + '%', t => Math.round(t * 100) + '%', true],
    ['主力武器稀有度', '原版对照用长剑，不算稀有度', 'rarity', v => RAR[Math.round(v)] || '—', t => RAR[t] || '', true],
    ['护符加成', '戴上挑出来的护符后，战斗力指数乘多少（护符栏 原版 ' + DATA.slots['原版'].join('/') + '，DR ' + DATA.slots['DR'].join('/') + '）', 'talx', v => '×' + v.toFixed(2), t => '×' + t, true],
    ['防具词条加成', '同样的防具减伤，算上词条后战斗力指数乘多少（原版防具基本没有相关词条）', 'armx', v => '×' + v.toFixed(2), t => '×' + t, true],
    ['异常的影响', '算上双方的异常（你给敌人叠的 + 敌人给你叠的）后战斗力指数乘多少，低于 ×1 = 敌人的异常更伤', 'stx', v => '×' + v.toFixed(2), t => '×' + t, true],
  ];
  const gw = document.getElementById('growth'); gw.innerHTML = '';
  const cards = G.map(([title, sub]) => {                // 先把卡片都放进网格，排好版再量宽度画图
    const card = document.createElement('div'); card.className = 'card';
    card.innerHTML = '<h3>' + esc(title) + '</h3><p class="sub">' + esc(sub) + '</p><div class="legend"></div><div class="chart"></div><div class="tip"></div>';
    gw.appendChild(card);
    return card;
  });
  G.forEach(([title, sub, key, fmt, tf, band], gi) => {
    const card = cards[gi];
    const ss = [];
    if (van[key]) ss.push({name: '原版', color: color('原版'), v: van[key], base: true});
    ss.push({name: 'DR 普通', color: color('普通'), v: nor[key], lo: band ? nor[key + '_p10'] : null, hi: band ? nor[key + '_p90'] : null});
    legend(card.querySelector('.legend'), ss);
    lineChart(card.querySelector('.chart'), card.querySelector('.tip'),
              {series: ss, fmt, tickFmt: tf, height: 230, min: key === 'talx' || key === 'armx' ? 1 : (key === 'stx' ? null : 0), max: key === 'rarity' ? 3 : (key === 'neg' ? 0.8 : null),
               ticks: key === 'rarity' ? [0, 1, 2, 3] : (key === 'neg' ? [0, 0.2, 0.4, 0.6, 0.8] : null), title});
  });
  // 表
  const th = '<tr><th>档位</th>' + ser.map(s => '<th>' + esc(s.name) + '</th>').join('') + '</tr>';
  const rows = DATA.bands.map((b, i) => '<tr><td>' + esc(b) + '</td>' + ser.map(s => '<td>' + (s.v[i] == null ? '—' : esc(M.fmt(s.v[i])) +
    (s.lo && s.lo[i] != null ? ' （' + esc(M.fmt(s.lo[i])) + '～' + esc(M.fmt(s.hi[i])) + '）' : '')) + '</td>').join('') + '</tr>').join('');
  document.getElementById('table').innerHTML = th + rows;
}

if (DATA.scenario) { const el = document.getElementById('scn'); el.hidden = false; el.innerHTML = '<b>情景</b>：' + esc(DATA.scenario) + '（只改 DR，原版不变）'; }
const A = DATA.assume;
function table(id, t) {
  document.getElementById(id).innerHTML = '<tr>' + t.head.map(h => '<th>' + esc(h) + '</th>').join('') + '</tr>' +
    t.rows.map(row => '<tr>' + row.map(c => '<td>' + c + '</td>').join('') + '</tr>').join('');
}
document.getElementById('target-sub').textContent = DATA.target.sub;
table('target', DATA.target);
document.getElementById('btarget-sub').textContent = DATA.btarget.sub;
table('btarget', DATA.btarget);
if (DATA.seeds) {
  document.getElementById('seeds-wrap').hidden = false;
  document.getElementById('seeds-sub').textContent = DATA.seeds.sub;
  table('seeds', DATA.seeds);
}
document.getElementById('affix-sub').textContent = DATA.affix.sub + ' 各稀有度有效果的词条中位：' + DATA.affix.median.map(x => '×' + x).join(' / ') + '。';
table('affix', DATA.affix);
document.getElementById('notes').innerHTML = [
  '<b>敌人</b>：每档 = 原版地图里放普通敌人的那批位置（和重随的「敌人血量按地区补正」同一批），随机敌人时看随机后实际放的敌人。血量 = 参数血量 × 自带特效 × 随机器缩放（含整合包的血量补正）；一下的伤害取这种敌人所有攻击动作里中位的那一招。每档取所有位置的中位数。',
  '<b>等级</b>：小怪清除率 ' + A.kill_ratio + '（每个普通敌人杀几次）、Boss 清除率 ' + (A.boss_ratio ?? 1) + '，宝箱 / 拾取拿 ' + (A.treasure_ratio ?? Math.min(1, A.kill_ratio)) + ' 成，不算黄金卢恩（按肝度分开看：<code>profiles.py</code>）；卢恩按难度加成。按原版升级公式换算等级，三套加点：力敏（流浪骑士）、智力（占星师）、信仰（预言者）。',
  '<b>DR 装备</b>：开局（稀有武器按职业加点偏向 + 每个部位一件防具）+ 免费许愿 ' + JSON.stringify(A.free_wishes) + ' 次（档 → 次数）+ 这一档的未鉴定物品：普通敌人按击杀数（真实掉落表，发现力 = 100 + 感应 + 难度加成）、宝箱 / 拾取 / Boss 奖励按概率（打到一半时拿到一半）；每件从装备样本里抽（<code>make_inputs.py</code> 用 dark_core 自己的生成代码导出的，和游戏里鉴定是同一套；武器照游戏先抽几把候选、按当前加点挑一把）。付费许愿和暗黑商店不算（卢恩都拿去升级）。只用近战武器、双手持够属性需求；强化按掉到的锻造石（每级 1 块，最高 +5），挑对这一档敌人伤害最高的（武器的特效、流派加成也算）；防具每个部位在负重放得下的里挑让战斗力最高的（减伤 + 词条）。',
  '<b>护符</b>：原版按掉落表里的原版护符（宝箱 / 尸体 / 地上拾取 / Boss 奖励 / 敌人掉落，任务奖励、NPC 给的、商店卖的不算）；DR 按未鉴定护符（同上）。护符栏 原版 ' + DATA.slots['原版'].join(' / ') + '（护符皮带的常见进度），DR ' + DATA.slots['DR'].join(' / ') + '（第五个护符槽多一个）。每档从拥有的护符里贪心挑让战斗力最高的。',
  '<b>原版对照</b>：同样的等级算法，武器用长剑，各档强化 ' + A.vanilla_upgrade.map(v => '+' + v).join(' / ') + '，质变在 13 种里挑这一档每下伤害最高的（含出血 / 冻伤 / 毒，不管磨刀石什么时候拿到）；防具每个部位在负重放得下的里，按单件放到身上的战斗力（减伤 + 词条）取 75% 分位的那件。',
  '<b>词条</b>：常驻特效本身带数值的（攻击、受到伤害、血量、属性、异常抗性，条件效果按覆盖率折算）直接读游戏参数；靠 HKS / dark_core 规则生效的（触发法术、回血、新流派词条、武器特效）按 <code>dev/power_curve/affix_power.json</code> 的折算：命中时触发的按游戏参数算触发周期（常驻标记的累积阈值 ÷ 每下累积 ' + (DATA.power.hit_accum || 1) + ' × 每下 ' + (DATA.power.H || 1) + ' 秒，不短于效果持续时间），其它按每 ' + DATA.power.P + ' 秒触发一次；固定伤害打到敌人身上剩 ' + DATA.power.flat_eff + '，回血最多抵掉敌人每下伤害的一半，圣杯瓶按有效血量的 ' + DATA.power.F + '。同一个特效防具和护符都有只生效一次。',
  '<b>异常</b>：双方都逐击模拟——你的武器每下叠的出血 / 冻伤 / 毒 / 腐败 / 发狂（出血、毒、睡眠、发狂随感应涨）对敌人的抗性，叠满发作（出血、发狂 15% 血 + 100，冻伤 10% + 30 且 30 秒内受伤 +20%，毒 / 腐败持续扣血），敌人抗性按 ResistCorrectParam 发作一次涨一次；敌人每一下平均叠的异常（它所有攻击动作的平均）对你的抗性（等级 + 生命力 / 耐力 / 精神 + 防具 + 词条）。持续扣血按你每 ' + A.hit_interval + ' 秒砍一下、敌人每 ' + A.enemy_hit_interval + ' 秒打中你一下折算。难度只乘在攻击伤害上（整合包就是这么做的），异常不受难度影响，所以每档难度分开模拟。',
  '<b>伤害</b>：攻击力按原版公式（强化倍率、补正曲线、属性对应关系），对敌人按原版的攻防比曲线算；玩家的基础防御 ≈ ' + A.player_def[0] + ' + ' + A.player_def[1] + ' × (等级 − 1)。DLC 两档假设幽影树庇佑 ' + A.dlc_blessing.slice(4).join(' / ') + ' 级（每级造成伤害 +' + Math.round(A.blessing_dealt * 100) + '%、受到伤害 ÷(1 + ' + (A.blessing_taken * 100) + '% × 等级)），三种情况一样。',
  '<b>难度</b>：照整合包的做法，玩家造成的攻击伤害 ÷ 敌人血量倍率、受到的攻击伤害 × 敌人伤害倍率；异常的累积和发作扣血不受难度影响，所以高难度下异常相对更值钱。卢恩和发现力加成影响等级和掉落。',
  '<b>重跑</b>：<code>dev/power_curve/model.py</code>（要带 numpy 的 Python）算 <code>result.json</code>，再 <code>report.py</code> 出这个网页；假设都在 model.py 开头的 ASSUME 里。',
].map(x => '<li>' + x + '</li>').join('');
render();
let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(render, 120); });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', render);
</script>
</body>
</html>
'''
html = HTML.replace('__DATA__', json.dumps(data, ensure_ascii=False)).replace('__RUNS__', str(r.get('runs', 300)))
open(dst, 'w', encoding='utf-8').write(html)
print('写好了：', dst, '%.0f KB' % (len(html.encode('utf-8')) / 1024))
