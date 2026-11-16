// 环绕法球（凝聚）的特效 990011 / 990012 / 990013 / 990014：1~4 颗辉石魔砾绕着人物转（用户 2026-10-29：参考原版辉石魔砾，有几个法球就有几颗）。
// 生成：fxrlab.html?build=orbs.js（见 ..\自制特效.md）。要先有原版魔砾的飞行特效 vanilla\f000523002.fxr（make_sfx.py 会从本机 Data0 取）。
// 写法：原版魔砾子弹（10400000）的飞行特效 523002 复制 N 份，各放在半径 RADIUS 的圆上、朝着切线方向（魔砾的模型沿 Z 轴），
// 套在一个绕竖轴自转的节点下（NodeSpeedSpin，每秒 SPIN 度），整圈再往前倾 TILT 度。
// 对原版那份的改动（在 JSON 上改，再 FXR.fromJSON 读回来）：
//   - 去掉只在发射那一下播的闪光（有限时长的节点）；
//   - 去掉留在世界里的拖尾火花（粒子 attachment 0）：人物跑起来会被甩在身后拉成一长条（用户 2026-10-29：移动时转得很怪）；
//   - 尺寸统一乘 SCALE（用户 2026-10-29：缩小）；
//   - 尾迹（Tracer）的发射点留在法球上：原版有一条尾迹的节点 0.2 秒内沿 -Z 退 0.5 米（NodeTranslation），子弹直线飞时退在正后方；
//     环绕时 Z 是切线，退出去就离开了圆周，尾迹画在半径 √(RADIUS² + 0.5²) ≈ 0.78 米的大圆上、还落后法球四十度
//     （用户 2026-11-11「法球尾迹没有直接跟在子弹后面而是离玩家身体半径更大的圆上」）→ 去掉这段平移；
//   - 魔砾模型（RichModel）原版往前偏 0.25 米，同理偏出圆周 → 放回节点原点，和尾迹的发射点重合（不管转的方向，尾迹都从法球身上拖出来）；
//     模型 s84016 的原点在头尖上、身子沿 -Z 往后长 PEBBLE_LEN（包围盒 Z −0.928 ~ 0），放在原点时尾迹从头尖起、盖住整颗魔砾
//     （用户 2026-11-12「法球的尾迹可以改到魔砾的中部么 衔接更自然」）→ 往前（+Z）挪半个身长，尾迹的发射点落在身子中间；
//     这样魔砾也是在中点和圆相切，两头偏出圆周一样少（以前尾巴偏出约 16 厘米）。
// 整圈挂成「只跟着挂点移动、不跟着挂点转」（DummyPolyTranslation）：胸口骨骼跑动时的摆动、倾斜不带着整圈歪，始终在水平面上转。
// 外层状态照原版持续光效：ext(0) < 1（光效行结束时收掉）。
// 5~7 颗：盈满（原名鹰眼视觉）按稀有度多 1~4 颗，凝聚传说 3 颗 → 最多 7 颗（2026-11-04）
export const ORBIT = [990011, 990012, 990013, 990014, 990015, 990016, 990017]   // 第 n 颗 = ORBIT[n - 1]
export const PEBBLE_FXR = 523002
export const RADIUS = 0.6                 // 半径（米）
export const SPIN = 120                   // 每秒转几度（3 秒一圈）
export const TILT = 10                    // 整圈前倾（度）
export const SCALE = 0.5                  // 魔砾大小（原版的倍数）
export const PEBBLE_LEN = 0.928           // 魔砾模型 s84016 的身长（模型单位 = sizeZ 为 1 时的米数；原点在头尖，身子沿 -Z）

// 动作编号（@cccode/fxr 的 ActionType）：节点平移（关键帧）、魔砾模型
const NODE_TRANSLATION = 15
const RICH_MODEL = 10015

// 外观动作里按尺寸算的字段（宽高、大小、半径、偏移）；别的（颜色、贴图坐标、比例开关……）不动
const SIZE_KEYS = /^(width|height|size|sizeX|sizeY|sizeZ|radius|offsetX|offsetY|offsetZ)$/

function scaleValue(v, f) {
  if (typeof v === 'number') return v * f
  if (Array.isArray(v)) return v.map(x => scaleValue(x, f))
  if (v && typeof v === 'object') {
    if (Array.isArray(v.keyframes)) return { ...v, keyframes: v.keyframes.map(k => ({ ...k, value: scaleValue(k.value, f) })) }
    if ('value' in v) {
      const mods = (v.modifiers || []).map(m => (m.type === 'RandomRange' ? { ...m, min: m.min * f, max: m.max * f } : m))
      return { ...v, value: scaleValue(v.value, f), modifiers: mods }
    }
  }
  return v
}

/** 属性最后稳定下来的值：数字直接用，关键帧取最后一帧，带随机的取中间值 */
function lastValue(v) {
  if (typeof v === 'number') return v
  if (v && Array.isArray(v.keyframes)) return lastValue(v.keyframes[v.keyframes.length - 1].value)
  if (v && 'value' in v) return lastValue(v.value)
  throw new Error('认不出的属性值：' + JSON.stringify(v))
}

const isFinitePositive = d => {
  const v = typeof d === 'number' ? d : Number(d)
  return Number.isFinite(v) && v > 0
}

/** 原版魔砾的节点（JSON）：去掉发射闪光、世界里的拖尾，尺寸乘 SCALE */
function prepare(nodes) {
  return nodes
    .filter(n => {
      const c = n.configs?.[0]
      if (isFinitePositive(c?.nodeAttributes?.duration)) return false                    // 发射那一下的闪光
      if (c?.appearance && c?.particleAttributes?.attachment === 0) return false        // 留在世界里的拖尾火花
      return true
    })
    .map(n => ({
      ...n,
      configs: (n.configs || []).map(c => {
        const out = { ...c }
        if (c.appearance) {
          out.appearance = Object.fromEntries(Object.entries(c.appearance).map(([k, v]) => [k, SIZE_KEYS.test(k) ? scaleValue(v, SCALE) : v]))
        }
        if (c.nodeTransform?.offset) out.nodeTransform = { ...c.nodeTransform, offset: scaleValue(c.nodeTransform.offset, SCALE) }
        if (c.nodeMovement?.type === NODE_TRANSLATION) out.nodeMovement = null                       // 尾迹发射点往后退的那段
        // 魔砾往前挪半个身长（按出场 0.2 秒后稳定下来的 sizeZ，已乘 SCALE），尾迹的发射点在身子中间
        if (c.appearance?.type === RICH_MODEL && c.nodeTransform?.offset) out.nodeTransform = { ...c.nodeTransform, offset: [0, 0, PEBBLE_LEN * lastValue(out.appearance.sizeZ) / 2] }
        return out
      }),
      nodes: prepare(n.nodes || []),
    }))
}

export async function build(FX) {
  const { FXR, BasicNode, NodeAttributes, NodeTransform, NodeSpeedSpin, AttachMode, Game } = FX
  const res = await fetch('./vanilla/f' + String(PEBBLE_FXR).padStart(9, '0') + '.fxr')
  if (!res.ok) throw new Error('缺原版魔砾特效 vanilla/f000523002.fxr：先跑一次 make_sfx.py')
  const base = FXR.read(await res.arrayBuffer(), Game.EldenRing).toJSON()
  const nodesJSON = JSON.stringify(prepare(base.root.nodes))
  // 每颗都从 JSON 重新建一份节点（节点对象不能共用）
  const pebble = () => FXR.fromJSON({ ...base, root: { ...base.root, nodes: JSON.parse(nodesJSON) } }).root.nodes
  const out = {}
  ORBIT.forEach((id, i) => {
    const count = i + 1
    const ring = []
    for (let k = 0; k < count; k++) {
      const th = 360 * k / count
      const rad = th * Math.PI / 180
      // 魔砾的头朝 +Z（原版子弹沿 +Z 飞）。NodeSpeedSpin 正转在游戏里是往切线的 -Z 那边走（以前写 th + 90，
      // 尾迹画在走过的路上，看着是从魔砾头部拖出来的；用户 2026-11-12「法球的尾迹应该是魔砾的尾部而不是头部」）→ 掉个头，th - 90
      ring.push(new BasicNode([new NodeTransform({ offset: [RADIUS * Math.sin(rad), 0, RADIUS * Math.cos(rad)], rotation: [0, th - 90, 0] })], pebble()))
    }
    const spin = new BasicNode([new NodeSpeedSpin({ angularSpeedY: SPIN })], ring)
    const fxr = new FXR(id, true)
    fxr.root.nodes = [new BasicNode([
      new NodeAttributes({ duration: -1, attachment: AttachMode.DummyPolyTranslation }),
      new NodeTransform({ rotation: [TILT, 0, 0] }),
    ], [spin])]
    out['f' + String(id).padStart(9, '0') + '.fxr'] = fxr.toArrayBuffer(Game.EldenRing)
  })
  return out
}
