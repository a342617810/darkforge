// 范围战灰放大（用户 2026-11-03）：原版子弹特效按战灰的倍数整体放大成我们的编号（列表在 aoe_scale.json，..\aoe_sfx_fetch.py 生成）。
// 生成：fxrlab.html?build=aoe_scale.js（见 ..\自制特效.md）。要先有 vanilla\f<原版>.fxr（aoe_sfx_fetch.py 从本机 Data0 取）。
// 放大的办法（库没有整体缩放，在 JSON 上改）：
//   - 长度类的字段乘倍数：外观大小（width / height / size / sizeX~Z / radius）、发射形状（radius / height / width / sizeX~Z）、
//     偏移（offsetX~Z / offset）。关键帧的 position 是时间，不动；
//   - 运动类的字段也乘倍数（speed / speedX~Z / acceleration / accelerationX~Z / gravity）：同样的时间里飞出去、扩散开的距离跟着变大；
//   - 不动：比例、倍率类（scaleX~Z、speedMultiplier…）、贴图滚动（speedU / V…）、角速度、颜色、时间、可见距离；
//   - 引用的子特效（类型 2001 的节点）换成同一份列表里放大过的副本（没列的就报错，免得漏了）。
const LEN = /^(width|height|size|sizeX|sizeY|sizeZ|radius|offsetX|offsetY|offsetZ|offset)$/
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

let missing = []
function walk(o, f, refs) {
  if (Array.isArray(o)) return o.map(x => walk(x, f, refs))
  if (!o || typeof o !== 'object') return o
  const out = {}
  for (const [k, v] of Object.entries(o)) {
    if (k === 'sfx' && o.type === 2001) {
      const r = refs[String(v)]
      if (r === undefined) missing.push(v)
      out[k] = r === undefined ? v : r
    } else if (LEN.test(k) || VEL.test(k)) {
      out[k] = scaleValue(v, f)
    } else {
      out[k] = walk(v, f, refs)
    }
  }
  return out
}

export async function build(FX) {
  const { FXR, Game } = FX
  const jobs = await (await fetch('./aoe_scale.json?t=' + Date.now())).json()
  const files = {}
  const lacks = {}            // 原版特效 → 没列的子特效（全部列完再报，一次补齐）
  for (const j of jobs) {
    const res = await fetch('./vanilla/f' + String(j.src).padStart(9, '0') + '.fxr')
    if (!res.ok) throw new Error('缺原版特效 vanilla/f' + String(j.src).padStart(9, '0') + '.fxr：先跑 ..\\aoe_sfx_fetch.py')
    const json = FXR.read(await res.arrayBuffer(), Game.EldenRing).toJSON()
    missing = []
    const scaled = walk(json, j.scale, j.refs)
    if (missing.length) { lacks[j.src] = [...new Set(missing)]; continue }
    scaled.id = j.id
    files['f' + String(j.id).padStart(9, '0') + '.fxr'] = FXR.fromJSON(scaled).toArrayBuffer(Game.EldenRing)
  }
  if (Object.keys(lacks).length) throw new Error('引用了没列的子特效（加进 aoe_sfx_fetch.py 的 CHILDREN）：' + JSON.stringify(lacks))
  return files
}
