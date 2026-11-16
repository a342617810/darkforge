// 猎印被引爆 / 近身清除时的碎裂特效 990070 / 990071 / 990072（消耗掉 1~3 层，颜色同猎印准星每层的浅绿 / 绿 / 深绿；用户 2026-11-13）
// 生成：fxrlab.html?build=hunt_burst.js（见 ..\自制特效.md）。光效行 extract_affixes.FLASH_VFX（挂点 220，演出类别 0），
// 效果行 0.5 秒，dark_core rules.rs 的 take_fx（tfx0~3：按消耗的层数挑）消耗猎印时挂给那个敌人。
// 一次性的：所有粒子在开头一起放出，0.4 秒内自己放完；效果结束（ext(0) 置 1）时还剩的在 END_FADE 秒内淡出。三部分：
//   1. 准星（猎印的贴图 99001）一下子撑大、转一点、淡掉 —— 看着是那个准星炸开；层数越多撑得越大
//   2. 中心一下白绿闪光（原版光点贴图 10011，常驻）
//   3. 碎片：一圈光点往外飞、减速、变小淡掉；层数越多碎片越多、飞得越快
// 都面朝镜头、跟着挂点走、不受场景光照、往镜头方向提前画 3 米（同猎印准星，不被身体挡住）。
export const TEXTURE = 99001
export const DOT = 10011
export const LAYERS = [
  { id: 990070, rgb: [0.62, 1.0, 0.62], grow: 2.0, shards: 8, speed: 4.5 },    // 1 层：浅绿
  { id: 990071, rgb: [0.2, 0.82, 0.2], grow: 2.4, shards: 12, speed: 5.5 },    // 2 层：绿
  { id: 990072, rgb: [0.0, 0.42, 0.06], grow: 2.8, shards: 16, speed: 6.5 },   // 3 层：深绿
]
export const SIZE = 0.55          // 准星原本的边长（米，同 hunt_mark.js）
export const LIFE = 0.36          // 准星撑大、淡掉的秒数
export const FLASH_LIFE = 0.18
export const SHARD_LIFE = 0.42
export const SHARD_SIZE = 0.16
export const MULT = 2.2           // 亮度倍数（同准星：> 1 发光、走泛光）
export const END_FADE = 0.15

export function build(FX) {
  const { FXR, BasicNode, PeriodicEmitter, SphereEmitterShape, ParticleAttributes, ParticleSpeed, BillboardEx, BlendMode, OrientationMode,
          LightingMode, AttachMode, LinearProperty, Keyframe, FadeTermination, Game } = FX
  const look = { blendMode: BlendMode.Normal, orientation: OrientationMode.CameraPlane, depthOffset: 3.0, depthBlend: false,
                 lighting: LightingMode.Unlit, shadowDarkness: 0, bloom: true }
  const curve = (keys) => new LinearProperty(false, keys.map(([t, v]) => new Keyframe(t, v)))
  const out = {}
  for (const { id, rgb, grow, shards, speed } of LAYERS) {
    const pale = rgb.map(v => v * 0.45 + 0.55)
    const big = SIZE * grow
    const fxr = new FXR(id, true)
    fxr.root.nodes = [
      // 1. 准星撑大淡掉（先快后慢）
      new BasicNode([
        new ParticleAttributes({ duration: LIFE, attachment: AttachMode.Parent }),
        new BillboardEx({
          ...look,
          texture: TEXTURE,
          width: curve([[0, SIZE], [LIFE * 0.35, SIZE + (big - SIZE) * 0.7], [LIFE, big]]),
          height: curve([[0, SIZE], [LIFE * 0.35, SIZE + (big - SIZE) * 0.7], [LIFE, big]]),
          color1: curve([[0, [...rgb, 1]], [LIFE * 0.25, [...rgb, 0.9]], [LIFE, [...rgb, 0]]]),
          rgbMultiplier: MULT,
          bloomColor: [...rgb, 0.4],
          angularSpeedZ: 240,
        }),
      ]),
      // 2. 中心闪光
      new BasicNode([
        new ParticleAttributes({ duration: FLASH_LIFE, attachment: AttachMode.Parent }),
        new BillboardEx({
          ...look,
          texture: DOT,
          width: curve([[0, 0.5], [FLASH_LIFE, 1.2]]),
          height: curve([[0, 0.5], [FLASH_LIFE, 1.2]]),
          color1: curve([[0, [...pale, 1]], [FLASH_LIFE, [...pale, 0]]]),
          rgbMultiplier: 3.0,
          bloomColor: [...pale, 0.5],
        }),
      ]),
      // 3. 碎片：开头一次放 shards 个，从中心附近往外飞、减速
      new BasicNode([
        new PeriodicEmitter({ interval: 1, perEmission: shards, totalEmissions: 1, maxConcurrent: shards }),
        new SphereEmitterShape({ radius: 0.12, emitInside: false }),
        new ParticleAttributes({ duration: SHARD_LIFE, attachment: AttachMode.Parent }),
        new ParticleSpeed({ speed: curve([[0, speed], [SHARD_LIFE * 0.5, speed * 0.25], [SHARD_LIFE, speed * 0.05]]) }),
        new BillboardEx({
          ...look,
          texture: DOT,
          width: curve([[0, SHARD_SIZE], [SHARD_LIFE, SHARD_SIZE * 0.4]]),
          height: curve([[0, SHARD_SIZE], [SHARD_LIFE, SHARD_SIZE * 0.4]]),
          color1: curve([[0, [...pale, 1]], [SHARD_LIFE * 0.4, [...rgb, 0.9]], [SHARD_LIFE, [...rgb, 0]]]),
          rgbMultiplier: 2.6,
          bloomColor: [...rgb, 0.4],
        }),
      ]),
    ]
    fxr.root.termination = new FadeTermination(END_FADE)
    out['f' + String(id).padStart(9, '0') + '.fxr'] = fxr.toArrayBuffer(Game.EldenRing)
  }
  return out
}
