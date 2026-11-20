//! 战灰「唤声船」（参数侧 rr/mariner.py，玩家脚本侧 sc/hks.py；用户 2026-10-29：唤声船同款座驾）。
//!   - 上船：按战技键时玩家脚本不放动作，挂请求标记 req_sp（这个技艺类型没有动画）；这里看到它新挂上，蓝够就扣蓝（fp），挂上船的效果
//!     （boat_sp = 原版幽灵材质的灵船 / wood_sp = 木头船，boat.ini 的 look 选；都带唤声船的船底雾气）和唤声船出现的雾 blink_sp。
//!     持续 dur_min ~ dur_max 秒：按放战技那只手的武器强化等级（+0 最短，满级最长；满级看强化表连着有几级：原版 +25 / 失色 +10，生成武器 +5）。
//!   - 坐在王座上（用户 2026-10-29，第一次实测后）：船的效果挂着时玩家脚本放坐姿手势；灵船模型的王座座面在挂点（脚底）上，
//!     所以骑船时把人物抬高 seat_h 米，船底回到地面。上船的过渡：board_t 秒内人物从地面升到座位高度（船从地里浮上来）、坐下，
//!     后半段才开始走；下船（时间到）：挂起身标记 stand_sp + 雾，unboard_t 秒内降回地面（船沉下去）、站起来，再放开操作。
//!   - 骑船：人物自己的移动、攻击这些暂时关掉（调试开关，同 dark_wings）；每帧按镜头和摇杆 / WASD 推着走
//!     （speed，按住冲刺键 boost_speed），改位置前沿移动方向打射线（离地面膝盖以上三条），前面有墙就停在墙前或沿墙滑；
//!     往下打射线贴地（矮于 step_up 的台阶直接上去），脚下没有地面就往下落（不会飞）；人物慢慢转向移动方向。
//!   - 骑船时再按战技键：不耗蓝，朝摇杆方向（没推就朝人物前方）瞬移 blink_dist 米（撞墙停在墙前），落地，落点挂 blink_sp
//!     （唤声船消失 / 出现的雾）；两次至少隔 blink_cd 秒。
//!   - 下船：跳跃键（挂跳船标记 jump_sp，玩家脚本从座位上起跳）、时间到（上面的起身过渡）、被打（exit_on_hit，一帧掉血够多才算，
//!     见 is_hit：中毒、腐败、词条扣血不算）、死亡、位置跳变（传送 / 读盘）；被打 / 死亡时直接放回地面，没有受击动作的话玩家脚本让人站起来。
//!   - 原版唤声船所在的三处 Boss 位置（boss_flag，击败标记；用户 2026-11-09：碎片改为原版唤声船位置的 Boss 掉落，敌人随机后看位置不看敌人）
//!     打赢一处发碎片 frag；有碎片了再打赢一处就收走碎片、发战灰 gem；发过战灰就不再发（标记 flag_frag / flag_gem 存档）。
//!     发货借新装备系统的发货表（gear::gift）。
//! 定义 boat.txt（重随写，没有就不工作）；参数 boat.ini（手改，每次上船重新读；debug = 1 时多记位置、输入，不骑船时记最快水平速度，
//! 骑灵马跑一段就知道灵马多快）；开发工具（dll\dark_dev 的 F9 窗口）写 boat_req.txt：战灰 / 碎片 / 击杀 / 重置。日志开头「唤声船」。
//! 移动、射线、输入的写法照 dark_wings（飞行）：改位置 + 角色代理按新位置重放、CSPhysWorld::cast_ray、游戏的按键 + 直接读摇杆 / WASD。

use std::collections::{HashMap, HashSet};
use std::f32::consts::PI;
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

use eldenring::cs::{
    CSCamExt, CSCamera, CSHavokMan, ChrAsmHand, ChrInsExt, EquipParamWeapon, GameDataMan, PlayerIns, ReinforceParamWeapon, SoloParamRepository,
    UserInputKey, WorldChrMan,
};
use eldenring::fd4::FD4PadManager;
use eldenring::position::{HavokPosition, PositionDelta};
use eldenring::rotation::Quaternion;
use fromsoftware_shared::{F32Vector4, FromStatic};
use windows::Win32::System::Threading::GetCurrentProcessId;
use windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState;
use windows::Win32::UI::Input::XboxController::{XINPUT_GAMEPAD_A, XINPUT_STATE, XInputGetState};
use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};

use crate::{dir, gear, log};

const DEF_FILE: &str = "boat.txt";
const CFG_FILE: &str = "boat.ini";
const REQ_FILE: &str = "boat_req.txt";
/// 掉落表类别：道具、战灰
const LOT_GOODS: i32 = 1;
const LOT_GEM: i32 = 5;
/// 背包里道具的类别
const INV_GOODS: u8 = 4;

// ------------------------------------------------------------------ 定义（重随写）
#[derive(Debug, Default, PartialEq)]
struct Defs {
    gem: i32,
    frag: u32,
    req_sp: i32,
    boat_sp: i32,
    blink_sp: i32,
    fp: i32,
    /// 原版唤声船所在位置的 Boss 战击败标记
    boss_flags: Vec<u32>,
    flag_frag: u32,
    flag_gem: u32,
    wood_sp: i32,
    jump_sp: i32,
    stand_sp: i32,
}

fn parse_defs(text: &str) -> Option<Defs> {
    let mut d = Defs::default();
    let mut n = 0;
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}').trim();
        if l.is_empty() || l.starts_with('#') {
            continue;
        }
        let (k, v) = l.split_once('\t')?;
        let v: i64 = v.trim().parse().ok()?;
        match k {
            "gem" => d.gem = v as i32,
            "frag" => d.frag = v as u32,
            "req_sp" => d.req_sp = v as i32,
            "boat_sp" => d.boat_sp = v as i32,
            "blink_sp" => d.blink_sp = v as i32,
            "fp" => d.fp = v as i32,
            "boss_flag" => {
                d.boss_flags.push(v as u32);
                continue;
            }
            "flag_frag" => d.flag_frag = v as u32,
            "flag_gem" => d.flag_gem = v as u32,
            "wood_sp" => d.wood_sp = v as i32,
            "jump_sp" => d.jump_sp = v as i32,
            "stand_sp" => d.stand_sp = v as i32,
            _ => continue,
        }
        n += 1;
    }
    (n == 11 && !d.boss_flags.is_empty()).then_some(d)
}

static DEFS: OnceLock<Option<Defs>> = OnceLock::new();

fn defs() -> Option<&'static Defs> {
    DEFS.get_or_init(|| fs::read_to_string(dir().join(DEF_FILE)).ok().and_then(|t| parse_defs(&t))).as_ref()
}

pub fn describe() -> String {
    match defs() {
        Some(d) => {
            let nr = new_reinf();
            format!("唤声船（战灰 {}，蓝 {}；重随的强化类型 {} 种，满级 +{}）", d.gem, d.fp, nr.1.len(), nr.0)
        }
        None => "唤声船（没有 boat.txt，不工作）".into(),
    }
}

// ------------------------------------------------------------------ 参数（boat.ini，手改）
#[derive(Debug, Clone, PartialEq)]
struct Cfg {
    enabled: bool,
    dur_min: f32,
    dur_max: f32,
    speed: f32,
    boost_speed: f32,
    turn_rate: f32,
    blink_dist: f32,
    blink_cd: f32,
    exit_on_hit: bool,
    step_up: f32,
    snap_down: f32,
    fall_speed: f32,
    /// 外观：false = 原版幽灵材质（look = ghost），true = 木头船（look = wood）
    wood: bool,
    /// 座位高度（米，= 模型里王座座面比船底原点高多少）、上船 / 下船过渡的秒数
    seat_h: f32,
    board_t: f32,
    unboard_t: f32,
    debug: bool,
}

/// 起身标记（stand_sp）挂 1 秒：下船过渡不能比它长，不然玩家脚本会在船还在时重新坐下
const UNBOARD_MAX: f32 = 0.9;

const CFG0: Cfg = Cfg {
    enabled: true,
    dur_min: 10.0,
    dur_max: 15.0,
    speed: 16.0,
    boost_speed: 22.0,
    turn_rate: 540.0,
    blink_dist: 15.0,
    blink_cd: 1.0,
    exit_on_hit: true,
    step_up: 0.7,
    snap_down: 2.5,
    fall_speed: 15.0,
    wood: false,
    seat_h: 0.96,
    board_t: 0.6,
    unboard_t: 0.5,
    debug: false,
};

fn parse_cfg(text: &str) -> (Cfg, Vec<String>) {
    let mut c = CFG0;
    let mut bad = Vec::new();
    for raw in text.lines() {
        let l = raw.trim_start_matches('\u{feff}');
        let l = l.split(['#', ';']).next().unwrap_or("").trim();
        if l.is_empty() {
            continue;
        }
        let Some((k, v)) = l.split_once('=') else {
            bad.push(l.to_string());
            continue;
        };
        let (k, v) = (k.trim(), v.trim());
        let f = v.parse::<f32>().ok().filter(|x| x.is_finite() && *x >= 0.0);
        let b = matches!(v, "1" | "true" | "yes" | "on");
        let ok = match k {
            "enabled" => {
                c.enabled = b;
                true
            }
            "exit_on_hit" => {
                c.exit_on_hit = b;
                true
            }
            "debug" => {
                c.debug = b;
                true
            }
            "look" => match v {
                "ghost" => {
                    c.wood = false;
                    true
                }
                "wood" => {
                    c.wood = true;
                    true
                }
                _ => false,
            },
            _ => {
                let Some(s) = slot(&mut c, k) else {
                    bad.push(l.to_string());
                    continue;
                };
                match f {
                    Some(x) => {
                        *s = x;
                        true
                    }
                    None => false,
                }
            }
        };
        if !ok {
            bad.push(l.to_string());
        }
    }
    if c.dur_max < c.dur_min {
        c.dur_max = c.dur_min;
    }
    c.unboard_t = c.unboard_t.min(UNBOARD_MAX);
    (c, bad)
}

/// boat.ini 数值的合理范围（崩溃风险审查第 24 条：以前没有上限，速度 / 瞬移距离填 1e6 会把人写到物理世界外面）
const LIMITS: [(&str, f32); 13] = [
    ("dur_min", 300.0),
    ("dur_max", 300.0),
    ("speed", 60.0),
    ("boost_speed", 60.0),
    ("turn_rate", 3600.0),
    ("blink_dist", 50.0),
    ("blink_cd", 60.0),
    ("step_up", 3.0),
    ("snap_down", 20.0),
    ("fall_speed", 100.0),
    ("seat_h", 3.0),
    ("board_t", 5.0),
    ("unboard_t", UNBOARD_MAX),
];

fn slot<'a>(c: &'a mut Cfg, k: &str) -> Option<&'a mut f32> {
    Some(match k {
        "dur_min" => &mut c.dur_min,
        "dur_max" => &mut c.dur_max,
        "speed" => &mut c.speed,
        "boost_speed" => &mut c.boost_speed,
        "turn_rate" => &mut c.turn_rate,
        "blink_dist" => &mut c.blink_dist,
        "blink_cd" => &mut c.blink_cd,
        "step_up" => &mut c.step_up,
        "snap_down" => &mut c.snap_down,
        "fall_speed" => &mut c.fall_speed,
        "seat_h" => &mut c.seat_h,
        "board_t" => &mut c.board_t,
        "unboard_t" => &mut c.unboard_t,
        _ => return None,
    })
}

/// 超出范围的夹到边上（parse_cfg 已经挡掉负数、NaN、无穷大），返回改了哪些
fn clamp_cfg(c: &mut Cfg) -> Vec<String> {
    let mut out = Vec::new();
    for (k, hi) in LIMITS {
        if let Some(v) = slot(c, k) {
            if *v > hi {
                out.push(format!("{k} = {} → {hi}", *v));
                *v = hi;
            }
        }
    }
    if c.dur_max < c.dur_min {
        c.dur_max = c.dur_min;
    }
    out
}

fn load_cfg() -> Cfg {
    let (mut c, bad) = parse_cfg(&fs::read_to_string(dir().join(CFG_FILE)).unwrap_or_default());
    if !bad.is_empty() {
        log(&format!("唤声船：boat.ini 里看不懂的行（用默认值）：{}", bad.join(" | ")));
    }
    let clamped = clamp_cfg(&mut c);
    if !clamped.is_empty() {
        log(&format!("唤声船：boat.ini 里超出范围的值（按上限算）：{}", clamped.join(" | ")));
    }
    c
}

// ------------------------------------------------------------------ 向量
type V3 = (f32, f32, f32);

fn len(v: V3) -> f32 {
    (v.0 * v.0 + v.1 * v.1 + v.2 * v.2).sqrt()
}

fn hlen(v: V3) -> f32 {
    (v.0 * v.0 + v.2 * v.2).sqrt()
}

fn norm(v: V3) -> Option<V3> {
    let l = len(v);
    (l > 1e-4).then(|| (v.0 / l, v.1 / l, v.2 / l))
}

fn add(a: V3, b: V3) -> V3 {
    (a.0 + b.0, a.1 + b.1, a.2 + b.2)
}

fn mul(a: V3, k: f32) -> V3 {
    (a.0 * k, a.1 * k, a.2 * k)
}

pub(crate) fn wrap(a: f32) -> f32 {
    let mut a = a % (2.0 * PI);
    if a > PI {
        a -= 2.0 * PI;
    } else if a < -PI {
        a += 2.0 * PI;
    }
    a
}

/// 绕 Y 轴转 yaw：+Z 转到 (sin yaw, 0, cos yaw)
pub(crate) fn yaw_quat(yaw: f32) -> Quaternion {
    Quaternion(0.0, (yaw / 2.0).sin(), 0.0, (yaw / 2.0).cos())
}

pub(crate) fn quat_yaw(q: &Quaternion) -> f32 {
    let (x, y, z, w) = (q.0, q.1, q.2, q.3);
    (2.0 * (x * z + w * y)).atan2(1.0 - 2.0 * (x * x + y * y))
}

/// 人物正面是本地 -Z（dark_wings 朝向校准「同向、偏移 180°」）：面向水平方向角 a 时四元数里的朝向角，和反过来
fn yaw_for(a: f32) -> f32 {
    wrap(a - PI)
}

fn facing(yaw: f32) -> V3 {
    let a = yaw + PI;
    (a.sin(), 0.0, a.cos())
}

// ------------------------------------------------------------------ 射线（玩家移动的碰撞过滤，同 dark_wings）
const RAY_FILTER: u32 = 0x1704;
const BODY_R: f32 = 0.45;
/// 往前打射线的高度：膝盖以上（更矮的台阶由贴地直接上去）
const RAY_H: [f32; 3] = [0.8, 1.3, 1.8];

fn ray_hit(o: V3, d: V3, me: &PlayerIns) -> Option<V3> {
    let hm = unsafe { CSHavokMan::instance() }.ok()?;
    let h = hm.phys_world.cast_ray(RAY_FILTER, &HavokPosition(o.0, o.1, o.2, 0.0), PositionDelta(d.0, d.1, d.2), me)?;
    Some((h.0, h.1, h.2))
}

/// 沿水平方向 d 最多能走多远
fn free_len(pos: V3, d: V3, me: &PlayerIns) -> f32 {
    let l = hlen(d);
    let Some(u) = norm((d.0, 0.0, d.2)) else { return 0.0 };
    let mut best = l;
    for h in RAY_H {
        let o = (pos.0, pos.1 + h, pos.2);
        if let Some(hit) = ray_hit(o, mul(u, l + BODY_R), me) {
            best = best.min((hlen((hit.0 - o.0, 0.0, hit.2 - o.2)) - BODY_R).max(0.0));
        }
    }
    best
}

/// 这一帧水平走多少：直着走得通就照走；撞了就在「直着走到墙前」和「沿墙滑」（左右偏 25° 两条射线的撞点连线是墙面）里挑走得远的
fn clip_h(pos: V3, d: V3, me: &PlayerIns) -> V3 {
    let l = hlen(d);
    if l < 1e-4 {
        return d;
    }
    let f = free_len(pos, d, me);
    if f >= l - 1e-3 {
        return d;
    }
    let mut best = mul(d, f / l);
    let o = (pos.0, pos.1 + RAY_H[1], pos.2);
    let (a, reach) = (d.0.atan2(d.2), l + BODY_R + 1.5);
    let hits: Vec<V3> = [-0.44f32, 0.44].iter().filter_map(|da| ray_hit(o, ((a + da).sin() * reach, 0.0, (a + da).cos() * reach), me)).collect();
    if let [h0, h1] = hits[..] {
        if let Some(t) = norm((h0.0 - h1.0, 0.0, h0.2 - h1.2)) {
            let c = mul(t, d.0 * t.0 + d.2 * t.2);
            let lc = hlen(c);
            if lc > 1e-4 {
                let mv = mul(c, free_len(pos, c, me).min(lc) / lc);
                if hlen(mv) > hlen(best) + 1e-4 {
                    best = mv;
                }
            }
        }
    }
    best
}

/// 在 (x, y + up, z) 往下打 up + down 米：碰到的地面高度
fn ground_y(p: V3, up: f32, down: f32, me: &PlayerIns) -> Option<f32> {
    ray_hit((p.0, p.1 + up, p.2), (0.0, -(up + down), 0.0), me).map(|h| h.1)
}

// ------------------------------------------------------------------ 输入（同 dark_wings）
fn game_focused() -> bool {
    unsafe {
        let w = GetForegroundWindow();
        if w.0.is_null() {
            return false;
        }
        let mut pid = 0u32;
        GetWindowThreadProcessId(w, Some(&mut pid));
        pid == GetCurrentProcessId()
    }
}

fn xinput(xi: &mut (Option<u32>, Option<Instant>)) -> Option<XINPUT_STATE> {
    let read = |i: u32| {
        let mut s = XINPUT_STATE::default();
        (unsafe { XInputGetState(i, &mut s) } == 0).then_some(s)
    };
    if xi.0.is_none() && xi.1.is_none_or(|t| t.elapsed().as_secs_f32() > 1.0) {
        xi.1 = Some(Instant::now());
        xi.0 = (0..4).find(|&i| read(i).is_some());
    }
    let s = read(xi.0?);
    if s.is_none() {
        xi.0 = None;
    }
    s
}

/// 这次骑船的移动输入来自哪里（位，下船时写日志）
const SRC_PAD: u8 = 1;
const SRC_KEY: u8 = 2;
const SRC_GAME: u8 = 4;

/// 游戏自己的移动键（改过按键、不走 XInput 的手柄靠这个；dark_wings 飞行时实测读到过 0，所以只在直接读设备读不到时才看）
fn game_move() -> (f32, f32) {
    let Some(pad) = unsafe { FD4PadManager::instance() }.ok().and_then(|m| m.get_in_game_pad()) else { return (0.0, 0.0) };
    let axis = |k: UserInputKey| {
        let a = pad.poll_analog_input(k).abs().min(1.0);
        if a > 0.0 {
            a
        } else if pad.poll_digital_input(k) {
            1.0
        } else {
            0.0
        }
    };
    (axis(UserInputKey::MoveForwards) - axis(UserInputKey::MoveBackwards), axis(UserInputKey::MoveRight) - axis(UserInputKey::MoveLeft))
}

/// 移动方向（前后, 左右, 来源）：关掉人物移动后游戏的移动键查询可能读到 0，先直接读手柄左摇杆 / 键盘 WASD（只在游戏窗口在前台时），
/// 都没有再看游戏自己的移动键
fn raw_move(xi: &mut (Option<u32>, Option<Instant>)) -> (f32, f32, u8) {
    if !game_focused() {
        return (0.0, 0.0, 0);
    }
    if let Some(s) = xinput(xi) {
        let (x, y) = (s.Gamepad.sThumbLX as f32 / 32767.0, s.Gamepad.sThumbLY as f32 / 32767.0);
        let mag = (x * x + y * y).sqrt();
        if mag > 0.24 {
            let k = ((mag - 0.24) / 0.76).min(1.0) / mag;
            return (y * k, x * k, SRC_PAD);
        }
    }
    let k = |vk: i32| (unsafe { GetAsyncKeyState(vk) } as u16 & 0x8000 != 0) as i32 as f32;
    let (f, s) = (k(0x57) - k(0x53), k(0x44) - k(0x41));
    if f != 0.0 || s != 0.0 {
        return (f, s, SRC_KEY);
    }
    let (f, s) = game_move();
    (f, s, if f != 0.0 || s != 0.0 { SRC_GAME } else { 0 })
}

/// 按键（游戏自己的输入，改过按键设置也认得）：（跳跃, 冲刺, 战技）。跳跃读不到时再看手柄 A 键
fn read_keys(xi: &mut (Option<u32>, Option<Instant>)) -> (bool, bool, bool) {
    let Some(pad) = unsafe { FD4PadManager::instance() }.ok().and_then(|m| m.get_in_game_pad()) else { return (false, false, false) };
    let key = |k: UserInputKey| pad.poll_digital_input(k);
    let mut jump = key(UserInputKey::Jump);
    if !jump && game_focused() {
        jump = xinput(xi).is_some_and(|s| s.Gamepad.wButtons.0 & XINPUT_GAMEPAD_A.0 != 0);
    }
    (jump, key(UserInputKey::Backstep), key(UserInputKey::Skill))
}

/// 镜头的水平前方、右方（前方用「镜头 → 人物」的方向，太远 / 太近时用镜头矩阵的前方）
fn camera_basis(pos: V3) -> Option<(V3, V3)> {
    let cam = unsafe { CSCamera::instance() }.ok()?;
    let pc = &cam.pers_cam_1;
    let cp = pc.position();
    let to_chr = (pos.0 - cp.0, pos.1 + 1.4 - cp.1, pos.2 - cp.2);
    let mf = pc.forward();
    let mr = pc.right();
    let d = len(to_chr);
    let f3 = if (0.5..40.0).contains(&d) { to_chr } else { (mf.0, mf.1, mf.2) };
    let fwd = norm((f3.0, 0.0, f3.2))?;
    let mut right = (fwd.2, 0.0, -fwd.0);
    if right.0 * mr.0 + right.2 * mr.2 < 0.0 {
        right = mul(right, -1.0);
    }
    Some((fwd, right))
}

// ------------------------------------------------------------------ 状态
#[derive(Clone, Copy, PartialEq, Debug)]
enum Mode {
    Idle,
    /// 骑船（前 board_t 秒是上船过渡）
    Ride,
    /// 下船过渡（时间到）：降回地面、站起来
    Unboard,
}

struct St {
    mode: Mode,
    cfg: Cfg,
    t: f32,
    dur: f32,
    /// 下船过渡已经过了几秒
    un_t: f32,
    /// 人物现在被抬高了多少（米）；挂着的是哪个船的效果
    lift: f32,
    sp: i32,
    yaw: f32,
    vy: f32,
    hp0: i32,
    blink_t: f32,
    saved_flags: (bool, bool),
    req_was: bool,
    skill_was: bool,
    jump_was: bool,
    last: Option<Instant>,
    last_pos: Option<V3>,
    xi: (Option<u32>, Option<Instant>),
    dbg_t: f32,
    /// 测速（debug，不骑船时）：这段时间里最快的水平速度、时长
    spd: (f32, f32),
    frames: u32,
    /// Boss 战击败标记上一次看到的状态（进存档 BOSS_SETTLE 之后才记）、进存档的时刻
    boss_seen: HashMap<u32, bool>,
    boss_since: Option<Instant>,
    /// 这次骑船走了多少米、移动输入来自哪里（SRC_*）
    moved: f32,
    src: u8,
    /// 骑船的声音（sound.rs，用户 2026-11-11）：上船声什么时候开始放、它多长、循环开始放了没有；None = 没在放
    snd: Option<(Instant, f32, bool)>,
    /// 物理更新前排下的效果（效果编号, true 挂 / false 摘），下一帧的 FrameBegin（frame）照顺序做
    fx: Vec<(i32, bool)>,
    /// 人物结构还没核对好时不上船，这条日志只记一次
    layout_told: bool,
}

impl St {
    fn new() -> Self {
        St {
            mode: Mode::Idle,
            cfg: load_cfg(),
            t: 0.0,
            dur: 0.0,
            un_t: 0.0,
            lift: 0.0,
            sp: 0,
            yaw: 0.0,
            vy: 0.0,
            hp0: 0,
            blink_t: 0.0,
            saved_flags: (false, false),
            req_was: false,
            skill_was: false,
            jump_was: false,
            last: None,
            last_pos: None,
            xi: (None, None),
            dbg_t: 0.0,
            spd: (0.0, 0.0),
            frames: 0,
            boss_seen: HashMap::new(),
            boss_since: None,
            moved: 0.0,
            src: 0,
            snd: None,
            fx: Vec::new(),
            layout_told: false,
        }
    }
}

/// 挂 / 摘效果排到下一帧的 FrameBegin（同一帧里同样的只排一次）
fn fx(st: &mut St, sp: i32, on: bool) {
    if !st.fx.contains(&(sp, on)) {
        st.fx.push((sp, on));
    }
}

/// 骑船的声音：dll\dark_core\sounds\ 的 boat_start.wav（上船：摇铃两下 + 嗡鸣渐入）放完接 boat_loop.wav 一直循环，下船停
/// （dev\dark_core\sounds\make_boat.py 合成的；唤声者自己的声音在它的音效库里，平时放不出来）
const SND_START: &str = "boat_start.wav";
const SND_LOOP: &str = "boat_loop.wav";

fn snd_path(name: &str) -> std::path::PathBuf {
    crate::dir().join("sounds").join(name)
}

fn snd_begin(st: &mut St, now: Instant) {
    let p = snd_path(SND_START);
    st.snd = if crate::sound::play(&p, false) {
        Some((now, crate::sound::wav_secs(&p).unwrap_or(0.0), false))
    } else if crate::sound::play(&snd_path(SND_LOOP), true) {
        Some((now, 0.0, true))
    } else {
        None
    };
}

/// 上船声放完了就接上循环（骑船时每帧看一次）
fn snd_tick(st: &mut St, now: Instant) {
    if let Some((t0, len, false)) = st.snd {
        if now.duration_since(t0).as_secs_f32() >= len {
            let ok = crate::sound::play(&snd_path(SND_LOOP), true);
            st.snd = Some((t0, len, true));
            if !ok {
                st.snd = None;
            }
        }
    }
}

fn snd_end(st: &mut St) {
    if st.snd.take().is_some() {
        crate::sound::stop();
    }
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 重随建的强化类型（affixes.txt 的 reinf 行第 4 列，rr/upgrade.py）和它们的最高等级（rmax 行）。这些类型的强化行一直建到 +25
/// （+rmax 以上照 +rmax 那行，崩溃风险审查第 10 条），数「连着有几级」会数成 25，生成武器 +5 时唤声船的时长只剩两成。
/// 新装备系统（gear.rs）的定义是私有的，这里自己读这两种行（启动时 describe 读一次，骑船时不读文件）
static NEW_REINF: OnceLock<(u32, HashSet<u32>)> = OnceLock::new();

fn parse_reinf(text: &str) -> (u32, HashSet<u32>) {
    let (mut rmax, mut types) = (0u32, HashSet::new());
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}').trim_end_matches('\r');
        let f: Vec<&str> = l.split('\t').collect();
        match f.as_slice() {
            ["rmax", n, ..] => rmax = n.parse::<u32>().map_or(0, |v| v.min(25)),
            ["reinf", _, _, _, t, ..] => {
                if let Ok(t) = t.parse::<u32>() {
                    types.insert(t);
                }
            }
            _ => {}
        }
    }
    (rmax, types)
}

fn new_reinf() -> &'static (u32, HashSet<u32>) {
    NEW_REINF.get_or_init(|| parse_reinf(&fs::read_to_string(dir().join("affixes.txt")).unwrap_or_default()))
}

/// 满级：重随建的强化类型照 rmax；原版类型数连着有几级强化行（原版 +25 / 失色 +10）
fn level_max(rt: u32, rows: u32, nr: &(u32, HashSet<u32>)) -> u32 {
    if nr.0 > 0 && nr.1.contains(&rt) { nr.0 } else { rows }
}

/// 放战技那只手的武器：（武器编号, 强化等级, 满级）。双手持握时是握着的那把，单手时是右手（这个战技不是盾牌战技，游戏也用右手的）
fn weapon_level() -> Option<(i32, u32, u32)> {
    let gdm = unsafe { GameDataMan::instance() }.ok()?;
    let asm = &gdm.main_player_game_data.equipment.chr_asm;
    let slot = asm.equipment.active_weapon_slot(ChrAsmHand::Right);
    let id = *asm.equipment_param_ids.get(slot as usize)?;
    if id <= 0 {
        return None;
    }
    let repo = unsafe { SoloParamRepository::instance() }.ok()?;
    let w = repo.get::<EquipParamWeapon>((id / 100 * 100) as u32)?;
    let rt = w.reinforce_type_id().max(0) as u32;
    let rows = (1..=25).take_while(|k| repo.get::<ReinforceParamWeapon>(rt + k).is_some()).count() as u32;
    let max = level_max(rt, rows, new_reinf());
    Some((id, ((id % 100) as u32).min(max), max))
}

/// 背包里有几个这个道具
fn goods_count(goods: u32) -> u32 {
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return 0 };
    gdm.main_player_game_data
        .equipment
        .equip_inventory_data
        .items_data
        .items()
        .filter(|it| it.item_id.category() as u8 == INV_GOODS && it.item_id.param_id() == goods)
        .map(|it| it.quantity)
        .sum()
}

/// 打赢了一处：没给过碎片就给碎片；给过（或背包里有）就收走碎片、给战灰；给过战灰就不再给
fn reward(d: &Defs, why: &str) {
    if gear::flag_get(d.flag_gem) == Some(true) {
        log(&format!("唤声船：{why}；战灰已经给过，不再发"));
        return;
    }
    let have = goods_count(d.frag);
    if gear::flag_get(d.flag_frag) == Some(true) || have > 0 {
        let removed = match unsafe { GameDataMan::instance_mut() } {
            Ok(gdm) if have > 0 => gear::remove_goods(&mut gdm.main_player_game_data, d.frag, have),
            _ => 0,
        };
        if gear::gift(LOT_GEM, d.gem) {
            gear::flag_set(d.flag_gem, true);
            log(&format!("唤声船：{why}；第二处：收走碎片 {removed} 个，发战灰 {}", d.gem));
        } else {
            log(&format!("唤声船：{why}；该发战灰了，但没有发货表（这次不是用重随的模式启动的？）"));
        }
    } else if gear::gift(LOT_GOODS, d.frag as i32) {
        gear::flag_set(d.flag_frag, true);
        log(&format!("唤声船：{why}；第一处：发碎片 {}", d.frag));
    } else {
        log(&format!("唤声船：{why}；该发碎片了，但没有发货表（这次不是用重随的模式启动的？）"));
    }
}

/// 开发工具（dark_dev 写的 boat_req.txt）：战灰 / 碎片（直接发）、击杀（当作击败了一只唤声船）、重置（熄灭两个标记、收走碎片）
fn dev_tick(d: &Defs) {
    let req = dir().join(REQ_FILE);
    let Ok(t) = fs::read_to_string(&req) else { return };
    let _ = fs::remove_file(&req);
    for l in t.lines().map(|l| l.trim_start_matches('\u{feff}').trim()).filter(|l| !l.is_empty()) {
        match l {
            "战灰" => log(&format!("唤声船（开发工具）：发战灰 {}：{}", d.gem, if gear::gift(LOT_GEM, d.gem) { "已排队" } else { "没有发货表" })),
            "碎片" => log(&format!("唤声船（开发工具）：发碎片 {}：{}", d.frag, if gear::gift(LOT_GOODS, d.frag as i32) { "已排队" } else { "没有发货表" })),
            "击杀" => reward(d, "开发工具：当作打赢了一处唤声船位置的 Boss"),
            "重置" => {
                gear::flag_set(d.flag_frag, false);
                gear::flag_set(d.flag_gem, false);
                let have = goods_count(d.frag);
                let removed = match unsafe { GameDataMan::instance_mut() } {
                    Ok(gdm) if have > 0 => gear::remove_goods(&mut gdm.main_player_game_data, d.frag, have),
                    _ => 0,
                };
                log(&format!("唤声船（开发工具）：重置——两个标记熄灭，收走碎片 {removed} 个（战灰留着）"));
            }
            _ => log(&format!("唤声船（开发工具）：看不懂「{l}」（战灰 / 碎片 / 击杀 / 重置）")),
        }
    }
}

/// 进存档多久以后才开始记击败标记（读档时标记会变，同 fusion.rs）；以前打过的不补发
const BOSS_SETTLE: f32 = 3.0;

/// 击败标记从灭变亮（读档后第一次看到就亮着的是以前打过的）
fn newly_on(was: Option<bool>, on: bool) -> bool {
    on && was == Some(false)
}

/// 三处 Boss 战里这次新打赢的（击败标记）
fn scan_bosses(d: &Defs, st: &mut St, now: Instant) -> Vec<u32> {
    let since = *st.boss_since.get_or_insert(now);
    if now.duration_since(since).as_secs_f32() < BOSS_SETTLE {
        return Vec::new();
    }
    let mut won = Vec::new();
    for &f in &d.boss_flags {
        let Some(on) = gear::flag_get(f) else { continue };
        if newly_on(st.boss_seen.insert(f, on), on) {
            won.push(f);
        }
    }
    won
}

/// 这一帧掉的血算不算被打：一帧掉最大血量的 2%（至少 10 点）才算。中毒、腐败、词条扣血每帧都很少，不算（以前一掉血就下船，人还留在坐姿里）
fn is_hit(prev: i32, now: i32, max: i32) -> bool {
    prev - now >= (max / 50).max(10)
}

fn ease(x: f32) -> f32 {
    let x = x.clamp(0.0, 1.0);
    x * x * (3.0 - 2.0 * x)
}

/// 放开：恢复动作 / 移动、开重力、摘掉船的效果；to_ground = 先放回地面（被打 / 时间到；跳船时留在座位高度起跳）
fn release(st: &mut St, p: &mut PlayerIns, to_ground: bool) {
    let f = &mut p.chr_ins.debug_flags;
    f.set_disabled_secondary_actions(st.saved_flags.0);
    f.set_disabled_movement(st.saved_flags.1);
    p.chr_ins.modules.physics.gravity_disabled = false;
    if to_ground && st.lift > 0.0 {
        let x = &p.chr_ins.modules.physics.position;
        let pos = (x.0, x.1 - st.lift, x.2);
        warp(p, pos);
        st.last_pos = Some(pos);
    }
    st.lift = 0.0;
    let sp = st.sp;
    fx(st, sp, false);
    st.mode = Mode::Idle;
    snd_end(st);
    let src: Vec<&str> = [(SRC_PAD, "XInput 手柄"), (SRC_KEY, "键盘 WASD"), (SRC_GAME, "游戏的移动键")].iter().filter(|x| st.src & x.0 != 0).map(|x| x.1).collect();
    log(&format!("唤声船：这次走了 {:.1} 米，移动输入：{}", st.moved, if src.is_empty() { "一次都没读到（手柄不是 XInput，或键盘改过按键）".to_string() } else { src.join("、") }));
}

/// 直接下船（死亡、被打、传送）：放回地面，照受击动作走
fn finish(st: &mut St, p: &mut PlayerIns, why: &str) {
    release(st, p, true);
    log(&format!("唤声船：下船（{why}，骑了 {:.1} 秒）", st.t));
}

/// 跳船：挂跳船标记（玩家脚本从座位上起跳）和雾，留在座位高度放开
fn jump_off(st: &mut St, d: &Defs, p: &mut PlayerIns) {
    fx(st, d.jump_sp, true);
    fx(st, d.blink_sp, true);
    release(st, p, false);
    log(&format!("唤声船：跳下船（骑了 {:.1} 秒）", st.t));
}

fn warp(p: &mut PlayerIns, np: V3) {
    let m = &mut p.chr_ins.modules;
    let w = m.physics.position.3;
    m.physics.position = HavokPosition(np.0, np.1, np.2, w);
    m.physics.chr_proxy_pos_update_requested = true;
    m.behavior.root_motion = F32Vector4(0.0, 0.0, 0.0, 0.0);
    m.physics.root_motion = F32Vector4(0.0, 0.0, 0.0, 0.0);
}

/// 脚下地面的高度（foot = 船底原点，也就是人物位置减去抬高的部分）；没有地面就按落速往下落
fn settle_y(st: &mut St, c: &Cfg, foot: V3, np: V3, dt: f32, p: &PlayerIns) -> f32 {
    match ground_y(np, c.step_up, c.snap_down, p) {
        Some(gy) => {
            st.vy = 0.0;
            gy
        }
        None => {
            st.vy = (st.vy - 20.0 * dt).max(-c.fall_speed);
            let y = foot.1 + st.vy * dt;
            match ground_y(np, 0.1, foot.1 - y + 0.1, p) {
                Some(gy) => {
                    st.vy = 0.0;
                    gy.max(y)
                }
                None => y,
            }
        }
    }
}

/// 每帧都要做的：关重力、清坠落计时、朝向
fn hold(st: &St, p: &mut PlayerIns) {
    let m = &mut p.chr_ins.modules;
    m.physics.gravity_disabled = true;
    m.fall.fall_timer = 0.0;
    let q = yaw_quat(st.yaw);
    m.physics.orientation = q;
    m.physics.interpolated_orientation = q;
}

/// 帧开头（FrameBegin）：tick 在物理更新前排下的效果照顺序挂上 / 摘掉；唤声船位置的 Boss 击败（发碎片 / 战灰）、开发工具请求。
/// 崩溃风险审查第 21 条：物理更新前那个组（ChrIns_PrePhysics）不带 Safe，挂效果、改背包、发货挪到这里，那边只改位置、朝向、重力和动作开关。
/// 效果晚到下一帧的帧开头才挂，玩家脚本在同一帧的行为更新里看到，和以前一样
pub fn frame() {
    let Some(d) = defs() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::new);
    let now = Instant::now();
    st.frames = st.frames.wrapping_add(1);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        st.fx.clear();
        st.boss_seen.clear();
        st.boss_since = None;
        return;
    };
    for (sp, on) in std::mem::take(&mut st.fx) {
        if on {
            p.apply_speffect(sp, false);
        } else {
            p.remove_speffect(sp);
        }
    }
    // 战灰发过了就不再看（用户 2026-11-01：每帧的活要挂在用得着的时候）
    if st.frames % 15 == 0 && gear::flag_get(d.flag_gem) != Some(true) {
        for f in scan_bosses(d, st, now) {
            reward(d, &format!("打赢了唤声船位置的 Boss（击败标记 {f}）"));
        }
    }
    if st.frames % 30 == 0 {
        dev_tick(d);
    }
}

/// 物理更新前（ChrIns_PrePhysics）：上船 / 骑船 / 瞬移 / 下船（挂 / 摘效果排给 frame）
pub fn tick() {
    let Some(d) = defs() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::new);
    let now = Instant::now();
    let wall_dt = st.last.map(|t| now.duration_since(t).as_secs_f32()).unwrap_or(0.0).min(0.1);
    st.last = Some(now);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    if wcm.main_player.is_none() {
        if st.mode != Mode::Idle {
            log("唤声船：玩家角色没了（读盘 / 回标题），下船");
            st.mode = Mode::Idle;
            st.lift = 0.0;
        }
        snd_end(st);
        st.last_pos = None;
        return;
    }
    let Some(p) = wcm.main_player.as_mut() else { return };
    let p: &mut PlayerIns = p;
    let gdt = p.chr_ins.chr_update_delta_time;
    let dt = if gdt.is_finite() && gdt > 0.0 && gdt <= 0.1 { gdt } else { wall_dt };
    let (hp, fp, max_hp) = (p.chr_ins.modules.data.hp, p.chr_ins.modules.data.fp, p.chr_ins.modules.data.max_hp);
    let pos = {
        let x = &p.chr_ins.modules.physics.position;
        (x.0, x.1, x.2)
    };
    let jumped = st.last_pos.is_some_and(|q| len((pos.0 - q.0, pos.1 - q.1, pos.2 - q.2)) > 60.0);
    let prev = st.last_pos.replace(pos);
    let req = p.chr_ins.special_effect.entries().any(|e| e.param_id == d.req_sp);
    let req_edge = req && !st.req_was;
    st.req_was = req;
    let (jump, boost, skill) = read_keys(&mut st.xi);
    let (skill_edge, jump_edge) = (skill && !st.skill_was, jump && !st.jump_was);
    (st.skill_was, st.jump_was) = (skill, jump);

    if st.mode == Mode::Idle {
        // 测速（debug）：2 秒一段，最快的水平速度超过 6 米 / 秒才记（骑灵马跑一段就知道灵马多快）
        if st.cfg.debug && dt > 0.005 {
            if let Some(q) = prev {
                st.spd.0 = st.spd.0.max(hlen((pos.0 - q.0, 0.0, pos.2 - q.2)) / dt);
            }
            st.spd.1 += dt;
            if st.spd.1 >= 2.0 {
                if st.spd.0 > 6.0 && st.spd.0 < 60.0 {
                    log(&format!("唤声船（测速）：最近 2 秒水平最快 {:.1} 米 / 秒", st.spd.0));
                }
                st.spd = (0.0, 0.0);
            }
        }
        if !req_edge {
            return;
        }
        st.cfg = load_cfg();
        let c = st.cfg.clone();
        if !c.enabled {
            log("唤声船：boat.ini 里 enabled = 0，不上船");
            return;
        }
        if hp <= 0 {
            return;
        }
        // 要写的物理 / 坠落 / 动作开关的位置先核对（崩溃风险审查第 22 条，chrs.rs）；对不上就不上船
        if !crate::chrs::player_layout_ok(p) {
            if !st.layout_told {
                st.layout_told = true;
                log("唤声船：人物结构没核对通过（或者还没读完图），这次不上船");
            }
            return;
        }
        if fp < d.fp {
            log(&format!("唤声船：蓝不够（{fp} / {}），不上船", d.fp));
            return;
        }
        p.chr_ins.modules.data.fp = fp - d.fp;
        let wl = weapon_level();
        let k = wl.map(|(_, lv, max)| lv as f32 / max.max(1) as f32).unwrap_or(0.0);
        st.dur = c.dur_min + (c.dur_max - c.dur_min) * k;
        let f = &mut p.chr_ins.debug_flags;
        st.saved_flags = (f.disabled_secondary_actions(), f.disabled_movement());
        f.set_disabled_secondary_actions(true);
        f.set_disabled_movement(true);
        st.sp = if c.wood { d.wood_sp } else { d.boat_sp };
        let sp = st.sp;
        fx(st, sp, true);
        fx(st, d.blink_sp, true);
        st.mode = Mode::Ride;
        (st.t, st.vy, st.blink_t, st.dbg_t, st.lift, st.moved, st.src) = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0);
        snd_begin(st, now);
        st.hp0 = hp;
        st.yaw = quat_yaw(&p.chr_ins.modules.physics.orientation);
        st.skill_was = true;
        log(&format!(
            "唤声船：上船（{}，{:.1} 秒，蓝 {fp} → {}；{}，速度 {} / 冲刺 {}，瞬移 {} 米，座位高 {} 米）",
            match wl {
                Some((id, lv, max)) => format!("武器 {} +{lv} / +{max}", id / 100 * 100),
                None => "读不到武器，按 +0 算".into(),
            },
            st.dur,
            fp - d.fp,
            if c.wood { "木头船" } else { "幽灵船" },
            c.speed,
            c.boost_speed,
            c.blink_dist,
            c.seat_h
        ));
        return;
    }

    let c = st.cfg.clone();
    if hp <= 0 {
        return finish(st, p, "死亡");
    }
    if jumped {
        return finish(st, p, "位置跳变（传送 / 读盘）");
    }
    if c.exit_on_hit && is_hit(st.hp0, hp, max_hp) {
        return finish(st, p, &format!("受到伤害（血 {} → {hp}）", st.hp0));
    }
    st.hp0 = hp;
    let foot = (pos.0, pos.1 - st.lift, pos.2);

    // ---- 下船过渡（时间到）：原地降回地面、站起来（起身标记挂上时玩家脚本放起身动作），完了再放开
    if st.mode == Mode::Unboard {
        st.un_t += dt;
        let k = if c.unboard_t > 0.0 { st.un_t / c.unboard_t } else { 1.0 };
        if k >= 1.0 {
            release(st, p, true);
            log(&format!("唤声船：下船（时间到，骑了 {:.1} 秒）", st.t));
            return;
        }
        let gy = settle_y(st, &c, foot, foot, dt, p);
        st.lift = c.seat_h * (1.0 - ease(k));
        let np = (foot.0, gy + st.lift, foot.2);
        warp(p, np);
        st.last_pos = Some(np);
        return hold(st, p);
    }

    // ---- 骑船（前 board_t 秒是上船过渡：从地面升到座位高度、坐下，后半段才开始走）
    snd_tick(st, now);
    st.t += dt;
    st.blink_t = (st.blink_t - dt).max(0.0);
    let board = if c.board_t > 0.0 { st.t / c.board_t } else { 1.0 };
    if st.t >= st.dur {
        fx(st, d.stand_sp, true);
        fx(st, d.blink_sp, true);
        st.mode = Mode::Unboard;
        st.un_t = 0.0;
        return hold(st, p);
    }
    if jump_edge && board >= 1.0 {
        return jump_off(st, d, p);
    }
    if !p.chr_ins.special_effect.entries().any(|e| e.param_id == st.sp) {
        let sp = st.sp;
        fx(st, sp, true);
    }

    let (mf, ms, src) = raw_move(&mut st.xi);
    st.src |= src;
    let Some((fwd, right)) = camera_basis(pos) else { return };
    let mut dir = add(mul(fwd, mf), mul(right, ms));
    if hlen(dir) > 1.0 {
        dir = mul(dir, 1.0 / hlen(dir));
    }

    // 再按战技键：瞬移（座位高度不变）
    if skill_edge && board >= 1.0 && st.blink_t <= 0.0 {
        let u = if hlen(dir) > 0.2 { norm(dir).unwrap_or(facing(st.yaw)) } else { facing(st.yaw) };
        let want = mul(u, c.blink_dist);
        let go = free_len(foot, want, p).min(c.blink_dist);
        let t = add(foot, mul(u, go));
        let ty = ground_y(t, 3.0, 12.0, p).unwrap_or(foot.1);
        let np = (t.0, ty + st.lift, t.2);
        warp(p, np);
        fx(st, d.blink_sp, true);
        st.blink_t = c.blink_cd;
        st.vy = 0.0;
        st.last_pos = Some(np);
        log(&format!("唤声船：瞬移 {go:.1} 米（想走 {} 米）", c.blink_dist));
        return hold(st, p);
    }

    // 移动：水平先防穿墙，再贴地 / 往下落；上船过渡的后半段慢慢加速
    let spd = (if boost { c.boost_speed } else { c.speed }) * ease(board * 2.0 - 1.0);
    let mv = clip_h(foot, mul(dir, spd * dt), p);
    st.moved += hlen(mv);
    let nf = (foot.0 + mv.0, foot.1, foot.2 + mv.2);
    let gy = settle_y(st, &c, foot, nf, dt, p);
    st.lift = c.seat_h * ease(board);
    let np = (nf.0, gy + st.lift, nf.2);
    warp(p, np);
    st.last_pos = Some(np);
    if hlen(dir) > 0.1 && spd > 0.0 {
        let target = yaw_for(dir.0.atan2(dir.2));
        let step = c.turn_rate.to_radians() * dt;
        st.yaw = wrap(st.yaw + wrap(target - st.yaw).clamp(-step, step));
    }
    hold(st, p);

    if c.debug {
        st.dbg_t += dt;
        if st.dbg_t >= 0.5 {
            st.dbg_t = 0.0;
            let ta = &p.chr_ins.modules.time_act;
            let anim = ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].anim_id;
            log(&format!(
                "唤声船 {:.1}/{:.1}s 位置 {:.1},{:.1},{:.1} 抬高 {:.2} 输入 前{mf:.2} 右{ms:.2} 冲刺{boost} 走 {:.2} 米（想走 {:.2}）落速 {:.1} 朝向 {:.0}° 动画 {anim}",
                st.t,
                st.dur,
                np.0,
                np.1,
                np.2,
                st.lift,
                hlen(mv),
                spd * dt * hlen(dir),
                st.vy,
                st.yaw.to_degrees()
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defs_lines() {
        let t = "# 注释\ngem\t29500\nfrag\t9170\nreq_sp\t369400\nboat_sp\t369401\nblink_sp\t369402\nfp\t20\nboss_flag\t1045390800\nboss_flag\t1038520800\nflag_frag\t93614\nflag_gem\t93615\nwood_sp\t369405\njump_sp\t369403\nstand_sp\t369404\n";
        let d = parse_defs(t).unwrap();
        assert_eq!((d.gem, d.frag, d.req_sp, d.fp, d.flag_gem), (29500, 9170, 369400, 20, 93615));
        assert_eq!(d.boss_flags, vec![1045390800, 1038520800]);
        assert!(parse_defs("gem\t1\n").is_none());
    }

    /// 只有读档后看到过灭着、现在亮了才算新打赢
    #[test]
    fn boss_flag_edge() {
        assert!(newly_on(Some(false), true));
        assert!(!newly_on(None, true), "读档后第一次看到就亮着：以前打过的");
        assert!(!newly_on(Some(true), true));
        assert!(!newly_on(Some(false), false));
    }

    /// 持续掉血不算被打，一帧掉得多才算；小血量角色至少 10 点
    #[test]
    fn hit_threshold() {
        assert!(!is_hit(1000, 995, 2000), "中毒一跳");
        assert!(is_hit(1000, 960, 2000));
        assert!(!is_hit(100, 91, 200));
        assert!(is_hit(100, 90, 200));
        assert!(!is_hit(100, 120, 200), "回血");
    }

    #[test]
    fn cfg_lines() {
        let (c, bad) = parse_cfg("\u{feff}# x\nspeed = 18 ; 注释\ndebug=1\nexit_on_hit = 0\ndur_min = 12\ndur_max = 8\nxx = 1\nblink_dist = -3\n");
        assert_eq!(c.speed, 18.0);
        assert!(c.debug && !c.exit_on_hit);
        assert_eq!((c.dur_min, c.dur_max), (12.0, 12.0));
        assert_eq!(c.blink_dist, CFG0.blink_dist);
        assert_eq!(bad.len(), 2);
    }

    /// 满级：重随建的强化类型（行一直建到 +25）照 rmax；原版类型数行；没有 rmax 行时都数行
    #[test]
    fn reinforce_max() {
        let nr = parse_reinf("\u{feff}# x\nrmax\t5\nrmat\t1\t2\t3\t4\nreinf\t0\t0\t0\t10000\nreinf\t1300\t3\t1\t11500\r\nreinfx\t1\t2\t3\t4\n");
        assert_eq!(nr.0, 5);
        assert_eq!(nr.1, [10000u32, 11500].into_iter().collect::<HashSet<u32>>());
        assert_eq!(level_max(10000, 25, &nr), 5, "新类型：行建到 +25 也按 +5 满级");
        assert_eq!(level_max(11500, 25, &nr), 5);
        assert_eq!(level_max(0, 25, &nr), 25, "原版普通");
        assert_eq!(level_max(2200, 10, &nr), 10, "原版失色");
        assert_eq!(level_max(10000, 25, &parse_reinf("")), 25, "不是重随的模式：照数行");
        // 随包的 affixes.txt（重随写的）：有的话每种新类型都认得出来，满级不超过 +25
        let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("dll").join("dark_core").join("affixes.txt");
        if let Ok(t) = fs::read_to_string(p) {
            let nr = parse_reinf(&t);
            assert!(nr.0 <= 25);
            assert!(nr.1.iter().all(|t| t % 100 == 0), "{:?}", nr.1);
        }
    }

    /// 超出范围的夹到上限（1e6 的速度 / 瞬移距离不会把人写出物理世界）；默认值不用夹；每个数值键都有上限
    #[test]
    fn cfg_clamped() {
        let (mut c, bad) = parse_cfg("speed = 1e6\nblink_dist = 999\nseat_h = 50\nunboard_t = 0.3\ndur_min = 1000\n");
        assert!(bad.is_empty());
        let out = clamp_cfg(&mut c);
        assert_eq!((c.speed, c.blink_dist, c.seat_h, c.unboard_t, c.dur_min, c.dur_max), (60.0, 50.0, 3.0, 0.3, 300.0, 300.0));
        assert_eq!(out.len(), 5, "{out:?}"); // speed、blink_dist、seat_h、dur_min、dur_max（parse 时跟着 dur_min 成了 1000）
        let mut d = CFG0;
        assert!(clamp_cfg(&mut d).is_empty());
        assert_eq!(d, CFG0);
        for (k, _) in LIMITS {
            assert!(slot(&mut d, k).is_some(), "{k}");
        }
    }

    /// dll\dark_core\boat.ini（随包带的）和代码里的默认值一致
    #[test]
    fn shipped_ini_is_default() {
        let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("dll").join("dark_core").join(CFG_FILE);
        let (c, bad) = parse_cfg(&fs::read_to_string(p).expect("boat.ini"));
        assert!(bad.is_empty(), "{bad:?}");
        assert_eq!(c, CFG0);
    }

    #[test]
    fn facing_matches_yaw_for() {
        for a in [-3.0f32, -1.0, 0.0, 0.7, 2.5] {
            let f = facing(yaw_for(a));
            assert!((f.0 - a.sin()).abs() < 1e-4 && (f.2 - a.cos()).abs() < 1e-4);
        }
    }
}
