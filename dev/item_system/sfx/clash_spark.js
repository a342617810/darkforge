// 相杀的防御火花加大加亮（用户 2026-11-04「改一下火花特效 现在太不明显了」）：原版金属武器防御火花 201001 → 我们的 990040。
// 生成：fxrlab.html?build=clash_spark.js（见 ..\自制特效.md）；要先有 vanilla\f000201001.fxr（make_sfx.vanilla_fxr 从本机 Data0 取）。
// 原版 201001：0.1 秒点光源（半径 1 米）+ 一下闪光（0.25 米）+ 最多 3 道光条 + 9 道火花线 + 15 颗小火星，1 秒内落完。
// 改法（同 aoe_scale.js，在 JSON 上改，颜色不动）：
//   - 大小 ×SIZE：width / height / size / sizeX~Z / radius / length / offset…（点光源半径跟着变大，照得更开）；
//   - 运动 ×MOTION：speed / acceleration / gravity（同样时间飞得更远，轨迹形状不变）；
//   - 数量 ×COUNT：会连续发射的发射器（totalEmissions -1）每次发几颗、最多同时几颗；只发一次的闪光不动；
//   - 亮度 ×BRIGHT：rgbMultiplier。
const ID = 990040, SRC = 201001
// 第一版游戏里「非常不明显」：原因是光效行进了身体光效的演出类别（4）被别的光效压掉（extract_affixes.custom_vfx 改成类别 0），
// 不是大小不够，所以大小保持第一版（中间试过再 ×3，用户 2026-11-04「按理说应该很明显了」后退回）
const SIZE = 2.5, MOTION = 1.6, COUNT = 3, BRIGHT = 1.5
const LEN = /^(width|height|size|sizeX|sizeY|sizeZ|radius|length|offsetX|offsetY|offsetZ|offset)$/
const VEL = /^(speed|speedX|speedY|speedZ|acceleration|accelerationX|accelerationY|accelerationZ|gravity)$/

function scaleValue(v, f) {
  if (typeof v === 'number') return v * f
  if (Array.isArray(v)) return v.map(x => scaleValue(x, f))
  if (v && typeof v === 'object') {
    let out = { ...v }
    if (Array.isArray(v.keyframes)) out.keyframes = v.keyframes.map(k => ({ ...k, value: scaleValue(k.value, f) }))
    if ('value' in v) out.value = scaleValue(v.value, f)
    if (Array.isArray(v.modifiers)) {
      out.modifiers = v.modifiers.map(m => {
        if (m.type === 'RandomRange' || m.type === 'RandomDelta') {
          const mm = { ...m }
          for (const k of Object.keys(m)) if (k !== 'type' && k !== 'seed' && (typeof m[k] === 'number' || Array.isArray(m[k]))) mm[k] = scaleValue(m[k], f)
          return mm
        }
        return m
      })
    }
    return out
  }
  return v
}

let stats = { len: 0, vel: 0, emit: 0, bright: 0 }
function walk(o) {
  if (Array.isArray(o)) return o.map(walk)
  if (!o || typeof o !== 'object') return o
  const out = {}
  for (const [k, v] of Object.entries(o)) {
    if (k === 'sfx' && o.type === 2001) throw new Error('201001 引用了子特效 ' + v + '，要一起复制')
    if (LEN.test(k)) { out[k] = scaleValue(v, SIZE); stats.len++ }
    else if (VEL.test(k)) { out[k] = scaleValue(v, MOTION); stats.vel++ }
    else if (k === 'rgbMultiplier') { out[k] = scaleValue(v, BRIGHT); stats.bright++ }
    else out[k] = walk(v)
  }
  // 连续发射的发射器：每次发几颗、最多同时几颗 ×COUNT
  if (o.type === 300 && o.totalEmissions === -1 && typeof o.perEmission === 'number') {
    out.perEmission = Math.round(o.perEmission * COUNT)
    out.maxConcurrent = Math.round(o.maxConcurrent * COUNT)
    stats.emit++
  }
  return out
}

export async function build(FX) {
  const { FXR, Game } = FX
  const name = 'f' + String(SRC).padStart(9, '0') + '.fxr'
  const res = await fetch('./vanilla/' + name)
  if (!res.ok) throw new Error('缺原版特效 vanilla/' + name + '：先跑 make_sfx.vanilla_fxr(' + SRC + ')')
  const json = FXR.read(await res.arrayBuffer(), Game.EldenRing).toJSON()
  stats = { len: 0, vel: 0, emit: 0, bright: 0 }
  const big = walk(json)
  big.id = ID
  console.log('clash_spark：改了大小 ' + stats.len + ' 处、运动 ' + stats.vel + ' 处、发射器 ' + stats.emit + ' 个、亮度 ' + stats.bright + ' 处')
  return { ['f' + String(ID).padStart(9, '0') + '.fxr']: FXR.fromJSON(big).toArrayBuffer(Game.EldenRing) }
}
