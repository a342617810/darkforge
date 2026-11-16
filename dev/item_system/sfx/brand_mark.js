// 咒痕（原名七咒）「烙印」的血月印记 990004（诅咒，血红）/ 990005（反转后，金色）（用户 2026-11-03：不用准星，另外做特效）
// 生成方法同 hunt_mark.js：python fxrlab.py，内置浏览器打开 http://127.0.0.1:8765/fxrlab.html?build=brand_mark.js，再跑 ..\make_sfx.py 打包。
// 贴图（..\make_sfx.py 画的，白色，颜色在这里染）：
//   99005 月面：圆盘、暗斑，右上一道亮的月牙（左下被蚀），边上一圈发亮的颗粒、外圈柔光
//   99006 月牙环：六个相同的小月牙围一圈 + 断续的细环（六重对称：转 60° 和原样一样）
// 两个节点，都悬在挂点（敌人的锁定点，光效行 midstDmyId 220）上方 OFFSET_Y 米、面朝镜头、不受场景光照、往镜头方向提前画（depthOffset），
// 每个只放一个一直在的粒子（时长 -1），效果结束时整份在 END_FADE 秒内淡出（FadeTermination）：
//   月面：亮度倍数 > 1 发光 + 泛光，透明度随粒子年龄慢慢呼吸；
//   月牙环：开头 RING_FADE 秒淡入，之后一直慢慢转（粒子角速度，RING_LIFE 秒转 60 度）。
// （以前照猎印每 0.1 秒换一个月面粒子、每 2 秒换一个月牙环，新旧交接时叠在一起变亮——用户 2026-11-03：印记会闪烁 → 改成常驻粒子）
// 状态照原版敌人身上的持续光效：「ext(0) < 1」（光效行结束时游戏把它置 1，特效收掉）——同 hunt_mark.js 的写法
// 近大远小（用户 2026-11-03：离敌人近了印记过大）：大小 ≈ 镜头到印记的距离 / REF_DIST（最小 MIN_SCALE，最大 1 = 原来的大小）。
// 特效里没有靠得住的「按镜头距离连续缩放」（外部值 SFXDistance 换算不明、不一定生效），所以按 STEP 倍一档细分（每档一套月面 + 月牙环），
// 用粒子自带的距离淡入淡出（minDistance / minFadeDistance / maxFadeDistance / maxDistance）只在自己那一段显示；
// 交界处两档一个淡出一个淡入（透明度加起来是 1），淡入淡出的宽度占到每档的 FADE_SHARE，相邻两档只差 STEP 倍，看着是连续缩放
// （第一版 5 档、每档差 1.4 倍，用户 2026-11-03：换挡时大小突变）。
export const MOON_TEXTURE = 99005
export const RING_TEXTURE = 99006
export const MARKS = [
  { id: 990004, rgb: [0.85, 0.06, 0.03] },   // 诅咒：血红
  { id: 990005, rgb: [1.0, 0.76, 0.22] },    // 反转后：金色
]
export const OFFSET_Y = 0.85                 // 锁定点上方（米）：大多数敌人在头顶附近
export const MOON_SIZE = 0.5
export const RING_SIZE = 0.95
export const MOON_MULT = 1.8
export const RING_MULT = 1.3
export const RING_ALPHA = 0.55
export const RING_LIFE = 2.0
export const RING_FADE = 0.2                 // 月牙环开头淡入的秒数
export const END_FADE = 0.25                 // 效果结束时整份淡出的秒数
export const REF_DIST = 10                   // 这么远（米）以外是原来的大小
export const MIN_SCALE = 0.3                 // 贴脸时最小缩到这么多（再近也不更小）
export const STEP = 1.08                     // 相邻两档的大小比
export const FADE_SHARE = 0.45               // 交界两边各拿出相邻那档宽度的这么多来交叉淡入淡出

/** 各档：{ scale, lo, hi, wlo, whi }——这一档在 [lo, hi) 米，两头各 wlo / whi 米的淡入淡出（-1 = 这一头不限） */
export function bands() {
  const scales = []
  for (let k = MIN_SCALE; k < 1 - 1e-6; k *= STEP) scales.push(k)
  scales.push(1)
  const edges = scales.slice(1).map((k, i) => REF_DIST * Math.sqrt(scales[i] * k))   // 第 i 档和第 i+1 档的交界：大小的几何平均处
  const width = j => Math.min(j > 0 ? edges[j] - edges[j - 1] : Infinity, j + 1 < edges.length ? edges[j + 1] - edges[j] : Infinity)
  const w = edges.map((_e, j) => FADE_SHARE * width(j))
  return scales.map((scale, i) => ({
    scale,
    lo: i > 0 ? edges[i - 1] : -1, wlo: i > 0 ? w[i - 1] : 0,
    hi: i < edges.length ? edges[i] : -1, whi: i < edges.length ? w[i] : 0,
  }))
}

export function build(FX) {
  const { FXR, BasicNode, NodeTransform, ParticleAttributes, BillboardEx, BlendMode, OrientationMode, LightingMode, AttachMode,
          LinearProperty, Keyframe, FadeTermination, Game } = FX
  const look = { blendMode: BlendMode.Normal, orientation: OrientationMode.CameraPlane, depthOffset: 3.0, depthBlend: false,
                 lighting: LightingMode.Unlit, shadowDarkness: 0 }
  const up = () => new NodeTransform({ offset: [0, OFFSET_Y, 0] })
  // 一档的距离淡入淡出：头一档近处不限、最后一档远处不限
  const fade = b => ({
    minDistance: b.lo > 0 ? b.lo - b.wlo : -1, minFadeDistance: b.lo > 0 ? b.lo + b.wlo : -1,
    maxFadeDistance: b.hi > 0 ? b.hi - b.whi : -1, maxDistance: b.hi > 0 ? b.hi + b.whi : -1,
  })
  const list = bands()
  const out = {}
  for (const { id, rgb } of MARKS) {
    const rc = rgb.map(v => v * 0.7 + 0.3)
    const fxr = new FXR(id, true)
    fxr.root.nodes = list.flatMap(b => [
      new BasicNode([
        up(),
        new ParticleAttributes({ duration: -1, attachment: AttachMode.Parent }),
        new BillboardEx({
          ...look,
          ...fade(b),
          texture: MOON_TEXTURE,
          width: MOON_SIZE * b.scale,
          height: MOON_SIZE * b.scale,
          color1: [...rgb, 1],
          rgbMultiplier: MOON_MULT,
          bloom: true,
          bloomColor: [...rgb, 0.4],
          // 呼吸：3 秒一轮，透明度 1 → 0.8 → 1
          color2: new LinearProperty(true, [new Keyframe(0, [1, 1, 1, 1]), new Keyframe(1.5, [1, 1, 1, 0.8]), new Keyframe(3.0, [1, 1, 1, 1])]),
        }),
      ]),
      new BasicNode([
        up(),
        new ParticleAttributes({ duration: -1, attachment: AttachMode.Parent }),
        new BillboardEx({
          ...look,
          ...fade(b),
          texture: RING_TEXTURE,
          width: RING_SIZE * b.scale,
          height: RING_SIZE * b.scale,
          color1: new LinearProperty(false, [new Keyframe(0, [...rc, 0]), new Keyframe(RING_FADE, [...rc, RING_ALPHA])]),
          rgbMultiplier: RING_MULT,
          bloom: false,
          angularSpeedZ: 60 / RING_LIFE,
        }),
      ]),
    ])
    fxr.root.termination = new FadeTermination(END_FADE)
    out['f' + String(id).padStart(9, '0') + '.fxr'] = fxr.toArrayBuffer(Game.EldenRing)
  }
  return out
}
