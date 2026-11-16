// 战灰「唤声船」的灵船特效（用户 2026-10-29：唤声船同款座驾）。
// 生成：fxrlab.html?build=boat.js（见 ..\自制特效.md）。模型由 ..\boat_model.py 从唤声船 c4950 取出船身（make_sfx.py 打包）：
//   990021 → 模型 99003：原版唤声船的幽灵材质（boat.ini 的 look = ghost，默认）
//   990024 → 模型 99004：普通特效材质的木头船（look = wood，第一版的样子，幽灵材质显示不对时用）
// 模型在 boat_model.py 里已经转好方向、王座座面挪到原点（第一次实测：船头反了、人物要坐在王座上），这里不用再偏移 / 转。
// 挂法：光效行挂点 900（玩家脚底「SFX発生用_固定」，跟着人物位置和朝向）；船底雾气另外挂唤声船原版的 649501。
// 写法：每 INTERVAL 秒放一个模型粒子、粒子活 LIFE 秒，跟着挂点走（Parent）；外层状态照原版持续光效 ext(0) < 1（效果摘掉时收掉，
// 最多再显示 LIFE 秒）。模型朝向用默认的「粒子方向」（第一次实测：跟着人物转，模型 +Z 朝人物前方）。
// 第三版（用户 2026-10-29：幽灵船显示有问题）：
//   - 幽灵船换成 RichModel 动作：幽灵船的模型是蒙皮网格（照原版材质的要求），库的说明里 Model 动作对有的模型会拉伸变形，RichModel 正常；
//   - 前后两个粒子交接的那一段（FADE 秒）一个淡出、一个淡入：以前两份同时画 0.05 秒，半透明的幽灵材质每 0.5 秒闪一下。
// 还要调时改：SCALE（大小；改了要同时改 boat.ini 的 seat_h = 0.96 × SCALE）、ROT_Y、LIFT、SHIFT_Z。
export const BOATS = [
  { id: 990021, model: 99003, rich: true },
  { id: 990024, model: 99004, rich: false },
]
export const SCALE = 1.0              // 原版唤声船的船约 6.8 米长
export const LIFT = 0.0
export const SHIFT_Z = 0.0
export const ROT_Y = 0
export const LIFE = 0.6
export const FADE = 0.1
export const INTERVAL = LIFE - FADE

export function build(FX) {
  const { FXR, BasicNode, PeriodicEmitter, ParticleAttributes, Model, RichModel, NodeTransform, BlendMode, AttachMode,
          LinearProperty, Keyframe, Game } = FX
  const fade = () => new LinearProperty(false, [
    new Keyframe(0, [1, 1, 1, 0]),
    new Keyframe(FADE, [1, 1, 1, 1]),
    new Keyframe(LIFE - FADE, [1, 1, 1, 1]),
    new Keyframe(LIFE, [1, 1, 1, 0]),
  ])
  const out = {}
  for (const { id, model, rich } of BOATS) {
    const look = rich
      ? new RichModel({ model, sizeX: SCALE, uniformScale: true, color1: fade() })
      : new Model({ model, sizeX: SCALE, uniformScale: true, blendMode: BlendMode.Normal, color1: fade() })
    const fxr = new FXR(id, true)
    fxr.root.nodes = [
      new BasicNode([
        new NodeTransform({ offset: [0, LIFT, SHIFT_Z], rotation: [0, ROT_Y, 0] }),
        new PeriodicEmitter({ interval: INTERVAL, perEmission: 1 }),
        new ParticleAttributes({ duration: LIFE, attachment: AttachMode.Parent }),
        look,
      ]),
    ]
    out['f' + String(id).padStart(9, '0') + '.fxr'] = fxr.toArrayBuffer(Game.EldenRing)
  }
  return out
}
