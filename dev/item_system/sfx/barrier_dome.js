// 死亡以上难度错配屏障的特效 990050（用户 2026-11-05「屏障缩小到10m吧 同时要加上特效标识屏障存在不能只是隐形空气墙」）。
// 生成：fxrlab.html?build=barrier_dome.js（见 ..\自制特效.md）；要先有 vanilla\f000806700.fxr（make_sfx.vanilla_fxr 从本机 Data0 取）。
// dark_core 的 barrier.rs 在圆心放一颗不动的子弹挂它（子弹行 99806700，rr/bossmods.py 的 barrier）。三层：
//   1. 原版封印监牢的圆顶 806700（模型 s83081，半径 30 米）整体缩到 SCALE（半径 RADIUS 米）。原版是挂在封印监牢物件上的，
//      第一次当子弹放在游戏里没看到（2026-11-05），所以再加下面两层一定看得见的；
//   2. 光幕：圆周上不停往上飘的蓝白光点（原版光点贴图 10011，叠加混合、发光、面朝镜头），人在圈里任何方向都看得到边界；
//   3. 地上一圈：同样的光点贴在圆周上不动、慢慢淡出，画出地面的边线。
// 外层状态照原版那份（ext(0) < 1 一直在；收掉时 3 秒内消失）。
const ID = 990050, SRC = 806700
export const RADIUS = 10                         // 和 dark_core barrier.rs 的 RADIUS 一样
const SCALE = RADIUS / 30                        // 原版圆顶模型半径 30 米
const COLOR = [0.55, 0.78, 1.0]                  // 封印监牢那种蓝白
const CURTAIN = { life: 2.2, rise: 1.4, interval: 0.05, per: 10, w: 0.45, h: 1.1, mult: 2.6, alpha: 0.9 }
const GROUND = { life: 1.4, interval: 0.05, per: 8, size: 1.1, mult: 2.0, alpha: 0.6 }
const SIZE_KEYS = /^(sizeX|sizeY|sizeZ|width|height|size|radius|offsetX|offsetY|offsetZ)$/

function scaleValue(v, f) {
  if (typeof v === 'number') return v * f
  if (Array.isArray(v)) return v.map(x => scaleValue(x, f))
  if (v && typeof v === 'object') {
    let out = { ...v }
    // Hermite 曲线的切线（t1 / t2）也是「值 / 时间」，跟着缩，不然开头长大时会先冲过头
    if (Array.isArray(v.keyframes)) out.keyframes = v.keyframes.map(k => ({ ...k, value: scaleValue(k.value, f),
      ...(typeof k.t1 === 'number' ? { t1: k.t1 * f } : {}), ...(typeof k.t2 === 'number' ? { t2: k.t2 * f } : {}) }))
    if ('value' in v) out.value = scaleValue(v.value, f)
    return out
  }
  return v
}

/** 原版圆顶的节点：外观的大小乘 SCALE */
function shrink(nodes) {
  return nodes.map(n => ({
    ...n,
    configs: (n.configs || []).map(c => c.appearance
      ? { ...c, appearance: Object.fromEntries(Object.entries(c.appearance).map(([k, v]) => [k, SIZE_KEYS.test(k) ? scaleValue(v, SCALE) : v])) }
      : c),
    nodes: shrink(n.nodes || []),
  }))
}

export async function build(FX) {
  const { FXR, BasicNode, PeriodicEmitter, CylinderEmitterShape, InitialDirection, ParticleAttributes, ParticleSpeed, BillboardEx,
          BlendMode, OrientationMode, LightingMode, AttachMode, LinearProperty, Keyframe, Game } = FX
  const name = 'f' + String(SRC).padStart(9, '0') + '.fxr'
  const res = await fetch('./vanilla/' + name)
  if (!res.ok) throw new Error('缺原版特效 vanilla/' + name + '：先跑 make_sfx.vanilla_fxr(' + SRC + ')')
  const base = FXR.read(await res.arrayBuffer(), Game.EldenRing).toJSON()
  base.root.nodes = shrink(base.root.nodes)
  base.id = ID
  const fxr = FXR.fromJSON(base)
  const look = { texture: 10011, blendMode: BlendMode.Add, orientation: OrientationMode.CameraPlane, lighting: LightingMode.Unlit,
                 bloom: true, bloomColor: [...COLOR, 0.5], shadowDarkness: 0 }
  const ring = (c) => new CylinderEmitterShape({ radius: RADIUS, height: 0.1, direction: InitialDirection.Up, emitInside: false, yAxis: true })
  const fade = (life, alpha) => new LinearProperty(false, [new Keyframe(0, [1, 1, 1, 0]), new Keyframe(Math.min(0.3, life / 4), [1, 1, 1, alpha]),
                                                          new Keyframe(life, [1, 1, 1, 0])])
  fxr.root.nodes.push(
    new BasicNode([
      new PeriodicEmitter({ interval: CURTAIN.interval, perEmission: CURTAIN.per, totalEmissions: -1, maxConcurrent: 600 }),
      ring(),
      new ParticleAttributes({ duration: CURTAIN.life, attachment: AttachMode.None }),
      new ParticleSpeed({ speed: CURTAIN.rise }),
      new BillboardEx({ ...look, width: CURTAIN.w, height: CURTAIN.h, color1: [...COLOR, 1], color2: fade(CURTAIN.life, CURTAIN.alpha),
                        rgbMultiplier: CURTAIN.mult }),
    ]),
    new BasicNode([
      new PeriodicEmitter({ interval: GROUND.interval, perEmission: GROUND.per, totalEmissions: -1, maxConcurrent: 400 }),
      ring(),
      new ParticleAttributes({ duration: GROUND.life, attachment: AttachMode.None }),
      new BillboardEx({ ...look, width: GROUND.size, height: GROUND.size, color1: [...COLOR, 1], color2: fade(GROUND.life, GROUND.alpha),
                        rgbMultiplier: GROUND.mult }),
    ]),
  )
  console.log('barrier_dome：圆顶缩到 ' + SCALE.toFixed(3) + '，加光幕、地面圈，半径 ' + RADIUS + ' 米')
  return { ['f' + String(ID).padStart(9, '0') + '.fxr']: fxr.toArrayBuffer(Game.EldenRing) }
}
