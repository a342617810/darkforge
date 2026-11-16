// 夺取魇火时玩家身上的特效 990006 / 990007（用户 2026-11-03：用原版亵渎圣剑战技「夺取者的火焰」打中回血时的特效，改成紫色）。
// 生成：fxrlab.html?build=drain.js（见 ..\自制特效.md）。要先有原版的 vanilla\f000450344.fxr、f000440322.fxr（make_sfx.py 会从本机 Data0 取）。
// 原版效果行 1565 → 光效行 8535（挂点 220）→ 特效 450344，它只是个壳：里面一个引用节点（type 2001）放 440322，画面都在 440322 里。
// 这里两份都复制：440322 → CORE，450344 → DRAIN（引用改成 CORE）；所有颜色（属性、字段、关键帧）用库自带的 recolor 换色：
// 转成 HSV，色相换成 HUE、饱和度至少 MIN_SAT，亮度（含超过 1 的 HDR 亮度）和透明度不变——原版的红变紫、白色乘数变淡紫。
// 光效行、效果行由 launcher\reroll\rr\nightmare.py 建（DRAIN_SP，光效行指 DRAIN）。
export const DRAIN = 990006
export const CORE = 990007
export const SRC = 450344
export const SRC_CORE = 440322
export const HUE = 280 / 360
export const MIN_SAT = 0.35

/** 一个颜色换成紫色：保留亮度（最大分量，可以超过 1）、透明度 */
function purple([r, g, b, a]) {
  const v = Math.max(r, g, b)
  if (!(v > 0)) return [r, g, b, a]
  const s = Math.max((v - Math.min(r, g, b)) / v, MIN_SAT)
  const h = HUE * 6
  const i = Math.floor(h) % 6
  const f = h - Math.floor(h)
  const p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f))
  const rgb = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i]
  return [rgb[0], rgb[1], rgb[2], a]
}

/** JSON 里引用 from 的节点改成引用 to，返回改了几个 */
function retarget(node, from, to) {
  let n = 0
  if (node && typeof node === 'object') {
    if (node.type === 2001 && node.sfx === from) {
      node.sfx = to
      n++
    }
    for (const v of Object.values(node)) n += retarget(v, from, to)
  }
  return n
}

const fname = id => 'f' + String(id).padStart(9, '0') + '.fxr'

export async function build(FX) {
  const { FXR, Game } = FX
  const read = async id => {
    const res = await fetch('./vanilla/' + fname(id))
    if (!res.ok) throw new Error('缺原版特效 vanilla/' + fname(id) + '：先跑一次 make_sfx.py')
    return FXR.read(await res.arrayBuffer(), Game.EldenRing)
  }
  const core = await read(SRC_CORE)
  core.id = CORE
  core.root.recolor(purple)
  const shell = (await read(SRC)).toJSON()
  shell.id = DRAIN
  if (retarget(shell.root, SRC_CORE, CORE) !== 1) throw new Error(SRC + ' 里引用 ' + SRC_CORE + ' 的节点不是正好一个')
  const top = FXR.fromJSON(shell)
  top.root.recolor(purple)
  return { [fname(DRAIN)]: top.toArrayBuffer(Game.EldenRing), [fname(CORE)]: core.toArrayBuffer(Game.EldenRing) }
}
