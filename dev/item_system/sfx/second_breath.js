// 换气（双手共持时切换武器、精力回满）的特效 990075
// 第三版（用户 2026-11-13「换气这特效不太行 用上你最好技术 贴合原版风格设计一个特效」）：全部用原版的特效拼，不再自己画。
// 生成：fxrlab.html?build=second_breath.js（见 ..\自制特效.md）。要先有 vanilla\f000301002.fxr、f000301202.fxr（make_sfx.py 会从本机 Data0 取）。
//
// 原版的「回复」一套：红露滴圣杯瓶喝下去的回血光 301002、蓝露滴的回专注光 301052 —— 蓝的就是红的那份只换了颜色
// （结构、时序、贴图、点光源全一样，比对过：只有颜色、随机种子和音效编号不同）。换色的规则也看得出来：
//   · 每个粒子颜色的开头（暖白 [1, 0.94, 0.62]）两份一样，不动；
//   · 结尾换成这一种资源的颜色（红 [1, 0.53, 0.37] / 蓝 [0.5, 0.75, 1]）；
//   · 中间那一帧 = 开头往结尾走同样的比例 t（红的 t 由红的那帧算出来，蓝的照用）；
//   · 泛光颜色、点光源颜色整个换成这种颜色。
// 精力在原版是绿（腌制龟颈肉、涌绿结晶露滴的那层光 301202：[0.44, 0.88, 0.47] → [0.22, 0.88, 0.27]，泛光 [0.5, 1, 0.5]）。
// 所以换气 = 「回复」一套里的第三个：照同样的规则把 301002 换成精力绿 —— 红回血、蓝回专注、绿回精力。
//   1. 主体：301002 的画面（节点 1：一团往外散的光、点光源把周围照绿一下、上升的光粒），换色；音效节点（节点 0，放喝红瓶的声音）去掉
//   2. 余韵：301202（腌制龟颈肉的持续光）里两个发射节点（往上飘的小光点、淡淡的光雾）照原版颜色，只发射 TAIL 秒（照 301002 里节点
//      「发射节点短命、粒子自己放完」的写法：外层节点活得比粒子长），之后自己散掉 —— 精力回满后身上还留一下精力的绿
// 光效行（extract_affixes.CUSTOM_VFX）放开头特效格、挂点 220（原版 5030 / 5352 挂这两个特效都用 220）：原版喝圣杯瓶也是一次放完、没人收，
// 所有节点都有限时长，不会留在身上。第一版自己画的在胸口提前 3 米、第二版挂腰间，都不像原版（用户「不太行」）。
export const ID = 990075
export const SRC = 301002            // 红露滴圣杯瓶的回血光
export const SRC_TAIL = 301202       // 腌制龟颈肉的精力光（持续）
export const KF0 = [1, 0.94, 0.62]   // 原版回复光每个粒子开头的暖白（红 / 蓝两份都是它）
export const GREEN = [0.45, 1.0, 0.5]        // 结尾色：精力绿（照蓝的 [0.5, 0.75, 1] 的亮度 / 饱和度，色相取 301202 的绿）
export const BLOOM = [0.35, 1.0, 0.4]        // 泛光（蓝的 [0.25, 0.5, 1]）
export const LIGHT = [0.6, 0.9, 0.62]        // 点光源（蓝的 [0.56, 0.73, 0.9]）
export const TAIL = 0.6                      // 余韵的发射秒数
export const TAIL_HOLD = 1.6                 // 余韵外层节点活多久（> 发射 + 粒子寿命 1 秒）

const fname = id => 'f' + String(id).padStart(9, '0') + '.fxr'
const isColor = v => Array.isArray(v) && v.length === 4 && v.every(x => typeof x === 'number')
const lerp = (a, b, t) => a.map((x, i) => x + (b[i] - x) * t)

/** 一个粒子颜色（color1）按原版红 → 蓝的规则换成绿：开头不动，结尾换色（透明度不变），中间按原来走到哪换算 */
function regreen(prop) {
  const ks = prop && prop.keyframes
  if (!Array.isArray(ks) || ks.length < 2 || !ks.every(k => isColor(k.value))) return 0
  const first = ks[0].value, last = ks[ks.length - 1].value
  for (let i = 1; i < ks.length; i++) {
    const v = ks[i].value
    if (i === ks.length - 1) {
      ks[i].value = [...GREEN, v[3]]
      continue
    }
    // t：这一帧在「开头 → 结尾」上走到哪（按变化大的通道平均）
    const ts = [0, 1, 2].filter(c => Math.abs(last[c] - first[c]) > 0.05).map(c => (v[c] - first[c]) / (last[c] - first[c]))
    const t = ts.length ? Math.min(1, Math.max(0, ts.reduce((a, b) => a + b, 0) / ts.length)) : 0
    ks[i].value = [...lerp(first.slice(0, 3), GREEN, t), v[3]]
  }
  return 1
}

/** 主体（301002 的节点 1）里所有暖色换成精力绿，返回换了几处 */
function recolor(node) {
  let n = 0
  if (!node || typeof node !== 'object') return 0
  const app = node.appearance
  if (app && typeof app === 'object') {
    n += regreen(app.color1)
    if (isColor(app.bloomColor) && app.bloomColor[0] > app.bloomColor[2] + 0.1) {
      app.bloomColor = [...BLOOM, app.bloomColor[3]]
      n++
    }
    for (const k of ['diffuseColor', 'specularColor']) {
      if (isColor(app[k])) {
        app[k] = [...LIGHT, app[k][3]]
        n++
      }
    }
  }
  for (const [k, v] of Object.entries(node)) if (k !== 'appearance') n += recolor(v)
  return n
}

/** 余韵：节点的寿命改成 dur（发射的节点）/ hold（外层），粒子寿命为负（一直在）的外层也改成 hold */
function limit(node, hold) {
  const cfgs = node.configs || []
  for (const c of cfgs) {
    const emits = c.emitter && c.emitter.type !== 399          // 399 = 只放一个（外层壳）；300 = 每隔多久放
    const dur = emits ? TAIL : hold
    if (c.nodeAttributes) c.nodeAttributes.duration = dur
    if (!emits && c.particleAttributes && typeof c.particleAttributes.duration === 'number' && c.particleAttributes.duration < 0) {
      c.particleAttributes.duration = hold
    }
  }
  for (const ch of node.nodes || []) limit(ch, hold)
}

export async function build(FX) {
  const { FXR, Game } = FX
  const read = async id => {
    const res = await fetch('./vanilla/' + fname(id))
    if (!res.ok) throw new Error('缺原版特效 vanilla/' + fname(id) + '：先跑 make_sfx.py（vanilla_fxr）')
    return FXR.read(await res.arrayBuffer(), Game.EldenRing).toJSON()
  }
  const main = await read(SRC)
  const tail = await read(SRC_TAIL)
  // 主体：去掉音效节点（只有 nodeAudio、没有画面的那个），剩下的换色
  const body = main.root.nodes.filter(n => !(n.configs || []).every(c => c.nodeAudio && !c.appearance && !(n.nodes || []).length))
  if (body.length !== main.root.nodes.length - 1) throw new Error('301002 的结构和预想的不一样（音效节点）')
  const changed = body.reduce((a, n) => a + recolor(n), 0)
  // 余韵：301202 根下第一个（细节层级节点 2002）里的第一条链（外壳 → 偏移 → 两个发射节点），整条拿来、限时
  const lod = tail.root.nodes[0]
  const chain = lod && lod.nodes && lod.nodes[0]
  if (!chain || !(chain.nodes || []).length) throw new Error('301202 的结构和预想的不一样（发射节点）')
  limit(chain, TAIL_HOLD)
  main.id = ID
  main.root.nodes = [...body, chain]
  const fxr = FXR.fromJSON(main)
  console.log('second_breath：主体换色 ' + changed + ' 处，余韵发射 ' + TAIL + ' 秒')
  return { [fname(ID)]: fxr.toArrayBuffer(Game.EldenRing) }
}
