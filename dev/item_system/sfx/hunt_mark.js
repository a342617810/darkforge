// 猎印的准星特效 990001 / 990002 / 990003（1~3 层，浅绿 → 深绿；用户 2026-10-28）
// 第二版（用户 2026-10-28）：不要描边，透明度不均匀，隐隐有气流缠绕在上面。
// 第三版（用户 2026-10-28）：参考大卢恩图标（贴图见 ..\make_sfx.py），线条粗很多；发光照原版 4160：普通混合 + 亮度倍数 > 1 + 泛光。
// 用 @cccode/fxr（https://github.com/EvenTorset/fxr，按 Elden Ring 的格式写）在浏览器里生成：
//   python fxrlab.py（本目录）起本地服务器，内置浏览器打开 http://127.0.0.1:8765/fxrlab.html?build=hunt_mark.js，
//   页面 import 本文件和库，调用 build(库)，把 { 文件名: ArrayBuffer } 写回本目录。生成完跑 ..\make_sfx.py 打包。详见 ..\自制特效.md
// 写法照原版敌人身上的持续光效（4160，桂奥尔的咆哮挂给敌人的降攻）：状态「ext(0) < 1」（光效行结束时游戏把它置 1，特效收掉）。
// 两个节点，每个只放一个一直在的粒子（时长 -1）；效果结束时整份在 END_FADE 秒内淡出（FadeTermination）。
// （以前照原版每 0.1 秒换一个粒子、活 0.13 秒，新旧叠在一起那一下变亮，一秒闪 10 下；气流每 1.5 秒换一个、交接时淡入淡出叠加，
//  用户 2026-11-03：印记会闪烁 → 改成常驻粒子）
//   准星：贴图 99001（make_sfx.py 画的：白色、没有描边、透明度不均匀）乘上每层的颜色，透明度随粒子年龄轻微呼吸（color2 循环）。
//   气流：贴图 99002（三股螺旋细流，三重对称），比准星大一圈，更淡的同色，开头 WISP_FADE 秒淡入，之后一直慢慢转（粒子角速度）。
// 都面朝镜头、跟着挂点走、不受场景光照，往镜头方向提前画 3 米（depthOffset），挂点在身体中间时不被身体挡住
// （2026-10-28 游戏里看得到的测试版用的就是 3 米）。
export const TEXTURE = 99001
export const WISP_TEXTURE = 99002
export const LAYERS = [
  { id: 990001, rgb: [0.62, 1.0, 0.62] },   // 1 层：浅绿
  { id: 990002, rgb: [0.2, 0.82, 0.2] },    // 2 层：绿
  { id: 990003, rgb: [0.0, 0.42, 0.06] },   // 3 层：深绿
]
export const SIZE = 0.55                     // 准星边长（米）
export const WISP_SIZE = 0.85                // 气流边长（米）
export const WISP_MIX = 0.45                 // 气流颜色 = 层色往白色混这么多（make_sfx.py 的预览用同样的值）
export const WISP_ALPHA = 0.35               // 隐隐能看到
export const RET_MULT = 2.2                  // 亮度倍数：> 1 就发光（超过 1 的部分走泛光）；深绿乘上去是饱和的亮绿
export const WISP_MULT = 1.2
export const WISP_LIFE = 1.5                 // 一个气流粒子转 120 度用的秒数（= 每秒 80 度）
export const WISP_FADE = 0.15             // 气流开头淡入的秒数
export const END_FADE = 0.25              // 效果结束时整份淡出的秒数

export function build(FX) {
  const { FXR, BasicNode, ParticleAttributes, BillboardEx, BlendMode, OrientationMode, LightingMode, AttachMode,
          LinearProperty, Keyframe, FadeTermination, Game } = FX
  const look = { blendMode: BlendMode.Normal, orientation: OrientationMode.CameraPlane, depthOffset: 3.0, depthBlend: false,
                 lighting: LightingMode.Unlit, shadowDarkness: 0 }
  const out = {}
  for (const { id, rgb } of LAYERS) {
    const wc = rgb.map(v => v * (1 - WISP_MIX) + WISP_MIX)
    const fxr = new FXR(id, true)
    fxr.root.nodes = [
      new BasicNode([
        new ParticleAttributes({ duration: -1, attachment: AttachMode.Parent }),
        new BillboardEx({
          ...look,
          texture: TEXTURE,
          width: SIZE,
          height: SIZE,
          color1: [...rgb, 1],
          rgbMultiplier: RET_MULT,
          bloom: true,
          bloomColor: [...rgb, 0.35],
          // 呼吸：按粒子年龄循环，2.4 秒一轮，透明度 1 → 0.75 → 1
          color2: new LinearProperty(true, [new Keyframe(0, [1, 1, 1, 1]), new Keyframe(1.2, [1, 1, 1, 0.75]), new Keyframe(2.4, [1, 1, 1, 1])]),
        }),
      ]),
      new BasicNode([
        new ParticleAttributes({ duration: -1, attachment: AttachMode.Parent }),
        new BillboardEx({
          ...look,
          texture: WISP_TEXTURE,
          width: WISP_SIZE,
          height: WISP_SIZE,
          color1: new LinearProperty(false, [new Keyframe(0, [...wc, 0]), new Keyframe(WISP_FADE, [...wc, WISP_ALPHA])]),
          rgbMultiplier: WISP_MULT,
          bloom: false,
          angularSpeedZ: 120 / WISP_LIFE,
        }),
      ]),
    ]
    fxr.root.termination = new FadeTermination(END_FADE)
    out['f' + String(id).padStart(9, '0') + '.fxr'] = fxr.toArrayBuffer(Game.EldenRing)
  }
  return out
}
