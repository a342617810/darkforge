// 排查「特效看不到」用的变体（2026-10-28 用过）：编号和正式的一样（990001~3），这样不用改 regulation，
// 猎印 1 / 2 / 3 层（F9 开发工具「效果调试」的按钮）分别挂出 A / B / C。生成：fxrlab.html?build=debug_variants.js&out=debug，
// 打包：make_sfx.py --debug（只写进 launcher\reroll\data\sfx，下次启动生效；排查完一定再跑一次 make_sfx.py 换回正式的）。
//   A 990001：我们的准星贴图，放大到 1.2 米、挂点往上 1 米（头顶上方，不可能和模型重合）、往镜头提前 3 米、亮绿 —— 看我们的贴图 / 特效能不能显示
//   B 990002：原版贴图 10011（原版 4160 用的光点），叠加混合、亮绿，同样在头顶上方 —— 排除我们的贴图
//   C 990003：原版 4160 原样只改编号（要先把原版的 f000004160.fxr 放进 debug\vanilla\，见 自制特效.md）—— 排除「我们包里的特效根本不加载」；
//             4160 本身很淡，2026-10-28 游戏里没看出来，参考价值不大
export async function build(FX) {
  const { FXR, BasicNode, NodeTransform, PeriodicEmitter, ParticleAttributes, BillboardEx, BlendMode, OrientationMode, LightingMode, AttachMode, Game } = FX
  const card = (id, tex, blend, mult) => {
    const fxr = new FXR(id, true)
    fxr.root.nodes = [
      new BasicNode([
        new NodeTransform({ offset: [0, 1.0, 0] }),
        new PeriodicEmitter({ interval: 0.1, perEmission: 1 }),
        new ParticleAttributes({ duration: 0.13, attachment: AttachMode.Parent }),
        new BillboardEx({
          texture: tex, blendMode: blend, orientation: OrientationMode.CameraPlane,
          width: 1.2, height: 1.2, color1: [0.3, 1, 0.3, 1], rgbMultiplier: mult,
          depthOffset: 3.0, depthBlend: false, lighting: LightingMode.Unlit, shadowDarkness: 0, bloom: false,
        }),
      ]),
    ]
    return fxr.toArrayBuffer(Game.EldenRing)
  }
  const out = {
    'f000990001.fxr': card(990001, 99001, BlendMode.Normal, 1),
    'f000990002.fxr': card(990002, 10011, BlendMode.Add, 4),
  }
  const v = await fetch('./debug/vanilla/f000004160.fxr')
  if (v.ok) {
    const fxr = FXR.read(await v.arrayBuffer(), Game.EldenRing)
    fxr.id = 990003
    out['f000990003.fxr'] = fxr.toArrayBuffer(Game.EldenRing)
  }
  return out
}
