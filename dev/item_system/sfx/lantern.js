// 提灯（携带照明灯，道具 2070）照得更亮（用户 2026-11-10「改一下油灯的亮度 参考 golden age 不需要改灯光颜色和位置」）：
// 原版提灯的光源特效 302421（光效行 5401，挂点 160 腰间）→ 我们的 990060，重随 rr/tweaks.py lantern_light 把光效行 5401 指过来。
// 生成：fxrlab.html?build=lantern.js（见 ..\自制特效.md）；要先有 vanilla\f000302421.fxr（make_sfx.vanilla_fxr 从本机 Data0 取）。
// Golden Age 的「幽魂提灯」（GA 加的道具 2071，挂在手上，用原版特效 402030）和原版提灯的点光源（类型 609）对比：
//   半径都是 16、亮度曲线（diffuse / specularMultiplier）都是 0 → 7.5、闪烁一样，只差颜色（GA 偏蓝）和 unk_ds3_p2_0：原版 1.25、GA 2。
//   unk_ds3_p2_0 管衰减（@cccode/fxr 的说明：1 = 正常；大于 1 衰减变弱，照到半径边上才很快暗下去，越大半径里越接近全亮）。
// 改法：只把点光源的 unk_ds3_p2_0 改成 GA 的 2；颜色、半径、亮度曲线、闪烁、挂点都不动（灯的模型和火苗 302420 / 光效行 5400 也不动）。
const ID = 990060, SRC = 302421
const FALLOFF = 2

let changed = 0
function walk(o) {
  if (Array.isArray(o)) return o.map(walk)
  if (!o || typeof o !== 'object') return o
  const out = {}
  for (const [k, v] of Object.entries(o)) out[k] = walk(v)
  if (o.type === 609) {
    out.unk_ds3_p2_0 = FALLOFF
    changed++
  }
  return out
}

export async function build(FX) {
  const { FXR, Game } = FX
  const name = 'f' + String(SRC).padStart(9, '0') + '.fxr'
  const res = await fetch('./vanilla/' + name)
  if (!res.ok) throw new Error('缺原版特效 vanilla/' + name + '：先跑 make_sfx.vanilla_fxr(' + SRC + ')')
  const json = FXR.read(await res.arrayBuffer(), Game.EldenRing).toJSON()
  changed = 0
  const lit = walk(json)
  if (changed !== 1) throw new Error('lantern：点光源应该正好 1 个，找到 ' + changed + ' 个')
  lit.id = ID
  console.log('lantern：点光源衰减 unk_ds3_p2_0 → ' + FALLOFF)
  return { ['f' + String(ID).padStart(9, '0') + '.fxr']: FXR.fromJSON(lit).toArrayBuffer(Game.EldenRing) }
}
