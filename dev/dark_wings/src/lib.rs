//! RNG Lands 飞行：战灰「熔炉百相之羽」（技艺 256，动画 a856_040000 / 双头剑 a856_042400）按住战技键 → 持续飞行。
//!
//! 原版这招：0.333 秒起关掉重力、长出翅膀升空（TAE 事件 0 动作 27，到 1.567 秒），约 1.7 秒俯冲斩（攻击判定 1.7~2.167 秒）。这里：
//!   - 动画放到 hover_time（默认 1.0 秒，正悬在空中）时还按着战技键、有蓝 → 飞行：动画接着放到 pose_time（默认 1.68 秒，
//!     俯冲斩往前戳、攻击判定之前）定住，当飞行姿势（翅膀特效一直在）；
//!     每帧按摇杆 / WASD 移动（相对镜头；前后跟着镜头俯仰，抬头往前飞就是往上飞；auto_forward：一直往前飞，前后输入不起作用）、
//!     跳跃键上升、蹲下键下降、冲刺键加速，
//!     人物朝向慢慢转向移动方向（游戏的朝向约定固定：人物正面是 -Z，见 yaw_for），往上 / 下飞时抬头 / 低头（body_pitch：
//!     飞行时关掉物理模块的「按世界竖直扶正」，四元数里加俯仰，结束时扶正）；
//!     飞行默认不耗蓝（fp_per_sec / boost_fp_per_sec 大于 0 时每秒扣人物数据模块的蓝）。
//!   - 松开战技键：放开动画，接原版的俯冲斩（hold_to_fly = 0 时改成再按一次战技键）。
//!   - 动画被打断（受击等）、开了耗蓝且蓝用完：滑翔——不扣蓝，慢慢下降、可以转向，落地后结束。
//!   - 飞行 / 滑翔中每帧清坠落计时；攻击、跳跃、翻滚、移动这些动作暂时关掉（这些键只给飞行用），结束时恢复。
//! 移动方式（move_mode）：直接改位置（havok 角色代理按新位置重放）。光这样会穿墙：瞬移进墙里再被挤出去，一帧走得远就挤到墙另一边
//!   （日志里偶尔一段「实际走了 40 多米」）。所以改位置前先沿移动方向打射线（wall_check，见 clip_move：膝盖 / 胸口 / 头顶三条，
//!   用玩家移动的碰撞过滤），前面有墙就停在墙前，斜着撞就沿墙滑、擦着地面 / 斜坡往上滑。
//!   试过写本帧位移（root_motion，ELDEN VINS 的飞盘滑行、喷射杖那样交给角色控制器走）：动画一定住游戏就不按它走了，只留作 root_motion 选项。
//!   都关重力。
//! 位移、转向按游戏这一帧更新人物用的帧时间（ChrIns.chr_update_delta_time）算，和镜头、动画同步，不按真实时间（会一顿一顿）。
//! 落地：命令往下走、读到的位置被地面顶回去（物理模块的「站在地上」标记在空中也是 true，不能用）。
//! 输入：按键（跳跃 / 蹲下 / 冲刺 / 战技）用游戏自己的输入；移动方向在关掉人物移动后游戏读不到，改读手柄左摇杆（XInput）/ 键盘 WASD。
//! 参数在 DLL 旁边的 dark_wings.ini（没有就用默认值；每次起飞重新读，游戏开着改也行）；日志 dark_wings.log（debug=1 时多记输入、位置，调参用）。
//! 认 eldenring.exe 2.7.1.0 / 2.7.2.0（地址表在 ../vendor 的 fromsoftware-rs 副本里），别的版本不工作。

use std::f32::consts::PI;
use std::fs;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{
    CSCamExt, CSCamera, CSHavokMan, CSTaskGroupIndex, CSTaskImp, ChrInsModuleContainer, GameDataMan, PlayerIns, UserInputKey, WorldChrMan,
};
use eldenring::fd4::{FD4PadManager, FD4TaskData};
use eldenring::position::{HavokPosition, PositionDelta};
use eldenring::rotation::Quaternion;
use fromsoftware_shared::{F32Vector4, FromStatic, SharedTaskImpExt};
use windows::Win32::Foundation::HMODULE;
use windows::Win32::System::LibraryLoader::GetModuleFileNameW;
use windows::Win32::System::Threading::GetCurrentProcessId;
use windows::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState;
use windows::Win32::UI::Input::XboxController::{XINPUT_STATE, XInputGetState};
use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};

static DIR: OnceLock<PathBuf> = OnceLock::new();
static CFG: Mutex<Option<Arc<Cfg>>> = Mutex::new(None);
static ST: Mutex<St> = Mutex::new(St::new());
/// 动画定住了没有（行为更新前的任务每帧把播放速度写成 0）
static FROZEN: AtomicBool = AtomicBool::new(false);
/// 人物结构自检：0 还没查、1 通过、2 对不上（停用飞行）
static LAYOUT: std::sync::atomic::AtomicU8 = std::sync::atomic::AtomicU8::new(0);

fn dir() -> PathBuf {
    DIR.get().cloned().unwrap_or_else(|| PathBuf::from("."))
}

fn log(msg: &str) {
    use std::io::Write;
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(dir().join("dark_wings.log")) {
        let t = local_time();
        let _ = writeln!(f, "{:02}:{:02}:{:02}.{:03} {msg}", t.hour, t.min, t.sec, t.ms);
    }
}

/// 本地时间：日志每行开头写时:分:秒.毫秒，加载时写一行日期（直接调 kernel32，不用给 windows crate 加特性）
#[repr(C)]
#[derive(Default)]
struct LocalTime {
    year: u16,
    month: u16,
    _weekday: u16,
    day: u16,
    hour: u16,
    min: u16,
    sec: u16,
    ms: u16,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetLocalTime(t: *mut LocalTime);
}

fn local_time() -> LocalTime {
    let mut t = LocalTime::default();
    unsafe { GetLocalTime(&mut t) };
    t
}

fn module_dir(h: u64) -> PathBuf {
    let mut buf = [0u16; 1024];
    let n = unsafe { GetModuleFileNameW(Some(HMODULE(h as *mut _)), &mut buf) } as usize;
    let p = PathBuf::from(String::from_utf16_lossy(&buf[..n]));
    p.parent().map(|d| d.to_path_buf()).unwrap_or_else(|| PathBuf::from("."))
}

/// 版本不对时库里查地址表会 panic：在这里接住
fn version_ok() -> bool {
    catch_unwind(|| {
        let _ = unsafe { GameDataMan::instance() };
    })
    .is_ok()
}

// ---- 参数（dark_wings.ini：一行「名字 = 值」，# 或 ; 后面是注释）
#[derive(Clone, Debug, PartialEq)]
struct Cfg {
    enabled: bool,
    /// 动画放到第几秒时进入飞行（要在关重力的 0.333~1.567 秒之间）
    hover_time: f32,
    /// true：那一刻还按着战技键才飞（轻按 = 原版俯冲斩），飞行中松开战技键结束；false：每次都飞，再按战技键结束
    hold_to_fly: bool,
    /// 飞行时定住的姿势：动画第几秒（起飞后动画接着放到这一秒再定住；1.7 秒起是俯冲斩的攻击判定，定在那之后飞过敌人会打到）
    pose_time: f32,
    /// 蓝少于这个数不起飞
    min_fp: u32,
    speed: f32,
    boost_speed: f32,
    vertical_speed: f32,
    fp_per_sec: f32,
    boost_fp_per_sec: f32,
    glide_speed: f32,
    glide_fall: f32,
    max_glide_secs: f32,
    /// 人物转向速度（度 / 秒）
    turn_rate: f32,
    /// 人物跟着飞行方向抬头 / 低头（关掉「按世界竖直扶正」，四元数里加俯仰；游戏会不会照着歪要实测）
    body_pitch: bool,
    /// 最大俯仰角（度）
    max_pitch: f32,
    /// 俯仰反了（往上飞低头）时改成 true
    flip_pitch: bool,
    /// 跳跃键上升、蹲下键下降
    vertical_keys: bool,
    /// 一直往前飞，前后输入不起作用（不能刹车、悬停；左右照常）；false = 摇杆控制前后，不推就悬停
    auto_forward: bool,
    /// 前后移动跟着镜头俯仰
    pitch_follow: bool,
    /// 俯仰死区（度）：镜头平时就从后上方往下看 15~25°，这个角度以内往前推是平飞，超出的部分才升降
    pitch_deadzone: f32,
    /// 左右反了时改成 true
    flip_lr: bool,
    /// 人物朝向反了（背对飞行方向）时改成 true
    flip_face: bool,
    /// 认作「熔炉百相之羽」的动画编号（逗号分隔；默认 856040000, 856042400）
    anim_ids: Vec<i32>,
    move_mode: MoveMode,
    /// 改位置前沿移动方向打射线（膝盖 / 胸口 / 头顶），前面有墙就停在墙前或沿墙滑，不穿墙
    wall_check: bool,
    debug: bool,
}

/// 怎么移动人物
#[derive(Clone, Copy, Debug, PartialEq)]
enum MoveMode {
    /// 改位置（同 Warp）。2026-10-25 试过默认写本帧位移：动画一定住（播放速度 0）游戏就不按它走了，飞不动
    Auto,
    /// 改位置 + 让角色代理按新位置重放；wall_check 开着时先打射线防穿墙
    Warp,
    /// 只写本帧位移（行为模块和物理模块的 root_motion；自动判断世界 / 本地坐标）。动画定住后不生效，只留着排查用
    RootMotion,
}

/// 实际用的移动办法（这次进游戏判断出来以后一直用）
#[derive(Clone, Copy, Debug, PartialEq)]
enum Via {
    /// 写本帧位移，按世界坐标写
    RootWorld,
    /// 写本帧位移，按人物本地坐标写（世界位移乘朝向的逆）
    RootLocal,
    /// 改位置
    Warp,
}

/// 写本帧位移时判断坐标系（只看水平）：一段时间里按世界算的命令位移、假如游戏按本地坐标解释会走到哪、实际走的、时长；
/// 连续几段几乎不动的次数
struct Det {
    cw: V3,
    cl: V3,
    act: V3,
    t: f32,
    stuck: u32,
}

const DET0: Det = Det { cw: (0.0, 0.0, 0.0), cl: (0.0, 0.0, 0.0), act: (0.0, 0.0, 0.0), t: 0.0, stuck: 0 };

impl Default for Cfg {
    fn default() -> Self {
        Cfg {
            enabled: true,
            hover_time: 1.0,
            hold_to_fly: true,
            pose_time: 1.68,
            min_fp: 0,
            speed: 12.0,
            boost_speed: 22.0,
            vertical_speed: 7.0,
            fp_per_sec: 0.0,
            boost_fp_per_sec: 0.0,
            glide_speed: 8.0,
            glide_fall: 4.0,
            max_glide_secs: 60.0,
            turn_rate: 540.0,
            body_pitch: true,
            max_pitch: 80.0,
            flip_pitch: false,
            vertical_keys: true,
            auto_forward: true,
            pitch_follow: true,
            pitch_deadzone: 25.0,
            flip_lr: false,
            flip_face: false,
            anim_ids: vec![856040000, 856042400],
            move_mode: MoveMode::Auto,
            wall_check: true,
            debug: false,
        }
    }
}

fn parse_cfg(text: &str) -> (Cfg, Vec<String>) {
    let mut c = Cfg::default();
    let mut bad = Vec::new();
    for raw in text.lines() {
        let line = raw.split(['#', ';']).next().unwrap_or("").trim().trim_start_matches('\u{feff}');
        let Some((k, v)) = line.split_once('=') else { continue };
        let (k, v) = (k.trim().to_ascii_lowercase(), v.trim());
        let f = || v.parse::<f32>().ok().filter(|x| x.is_finite() && *x >= 0.0);
        let b = || match v.to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => Some(true),
            "0" | "false" | "no" | "off" => Some(false),
            _ => None,
        };
        let ok = match k.as_str() {
            "enabled" => b().map(|x| c.enabled = x),
            "hover_time" => f().map(|x| c.hover_time = x),
            "hold_to_fly" => b().map(|x| c.hold_to_fly = x),
            "pose_time" => f().map(|x| c.pose_time = x),
            "min_fp" => v.parse::<u32>().ok().map(|x| c.min_fp = x),
            "speed" => f().map(|x| c.speed = x),
            "boost_speed" => f().map(|x| c.boost_speed = x),
            "vertical_speed" => f().map(|x| c.vertical_speed = x),
            "fp_per_sec" => f().map(|x| c.fp_per_sec = x),
            "boost_fp_per_sec" => f().map(|x| c.boost_fp_per_sec = x),
            "glide_speed" => f().map(|x| c.glide_speed = x),
            "glide_fall" => f().map(|x| c.glide_fall = x),
            "max_glide_secs" => f().map(|x| c.max_glide_secs = x),
            "turn_rate" => f().map(|x| c.turn_rate = x),
            "body_pitch" => b().map(|x| c.body_pitch = x),
            "max_pitch" => f().filter(|x| *x <= 89.0).map(|x| c.max_pitch = x),
            "flip_pitch" => b().map(|x| c.flip_pitch = x),
            "vertical_keys" => b().map(|x| c.vertical_keys = x),
            "auto_forward" => b().map(|x| c.auto_forward = x),
            "pitch_follow" => b().map(|x| c.pitch_follow = x),
            "pitch_deadzone" => f().filter(|x| *x < 89.0).map(|x| c.pitch_deadzone = x),
            "flip_lr" => b().map(|x| c.flip_lr = x),
            "flip_face" => b().map(|x| c.flip_face = x),
            "move_mode" => match v.to_ascii_lowercase().as_str() {
                "auto" => Some(MoveMode::Auto),
                "warp" => Some(MoveMode::Warp),
                "root_motion" => Some(MoveMode::RootMotion),
                _ => None,
            }
            .map(|x| c.move_mode = x),
            "anim_ids" => {
                let ids: Option<Vec<i32>> = v.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).map(|s| s.parse().ok()).collect();
                ids.filter(|x| !x.is_empty()).map(|x| c.anim_ids = x)
            }
            "wall_check" => b().map(|x| c.wall_check = x),
            "debug" => b().map(|x| c.debug = x),
            _ => None,
        };
        if ok.is_none() {
            bad.push(line.to_string());
        }
    }
    (c, bad)
}

fn load_cfg() -> Cfg {
    match fs::read_to_string(dir().join("dark_wings.ini")) {
        Ok(t) => {
            let (c, bad) = parse_cfg(&t);
            if !bad.is_empty() {
                log(&format!("dark_wings.ini 里这几行没认出来（用默认值）：{}", bad.join(" | ")));
            }
            c
        }
        Err(_) => Cfg::default(),
    }
}

fn cfg() -> Arc<Cfg> {
    let mut g = CFG.lock().unwrap_or_else(|e| e.into_inner());
    g.get_or_insert_with(|| Arc::new(load_cfg())).clone()
}

/// 每次起飞重新读一遍 dark_wings.ini：游戏开着改参数（速度、姿势等）下次起飞就生效
fn reload_cfg() -> Arc<Cfg> {
    let new = Arc::new(load_cfg());
    let mut g = CFG.lock().unwrap_or_else(|e| e.into_inner());
    if g.as_ref().is_some_and(|old| **old != *new) {
        log(&format!("dark_wings.ini 改过，用新参数：{new:?}"));
    }
    *g = Some(new.clone());
    new
}

// ---- 状态
#[derive(Clone, Copy, PartialEq, Debug)]
enum Mode {
    Idle,
    Fly,
    Glide,
}

struct St {
    mode: Mode,
    /// 这一次「熔炉百相之羽」动画已经处理过（没按住 / 已放开），动画结束前不再进入
    used: bool,
    fp_acc: f32,
    yaw: f32,
    saved_anim_speed: f32,
    saved_hks_speed: f32,
    /// 起飞前的「关掉动作 / 关掉移动」调试开关
    saved_flags: (bool, bool),
    skill_was: bool,
    /// 松开战技键多久了（去抖：松开 0.1 秒才结束）
    release_t: f32,
    /// 起飞了、动画还在往 pose_time 放，到了再定住
    pose_pending: bool,
    t_mode: f32,
    ground_t: f32,
    dbg_t: f32,
    last: Option<Instant>,
    last_pos: Option<(f32, f32, f32)>,
    /// 上一帧写进去的位置和竖直位移（判断落地：往下走被地面挡住）
    cmd: Option<(V3, f32)>,
    last_anim: i32,
    seen_wings: bool,
    /// 实际用的移动办法、判断好了没有（这次进游戏一直用）；判断坐标系的统计、上一帧写的位移（按世界 / 假如按本地）
    via: Via,
    via_decided: bool,
    via_cfg: MoveMode,
    det: Det,
    det_prev: Option<(V3, V3)>,
    /// 这 0.5 秒里被射线挡住（停在墙前 / 沿墙滑）的帧数（调试日志）
    clips: u32,
    /// 这 0.5 秒里最后一次被挡时三条射线的样子、上次记「飞行被挡」的时间（日志）
    block_note: Option<String>,
    stuck_log: Option<Instant>,
    /// 移动效果统计（0.5 秒一段）：命令的路程、实际的路程、时长、上一帧读到的位置
    win: (f32, f32, f32),
    prev_read: Option<V3>,
    /// 认准的手柄位、上次找手柄的时间
    xi: (Option<u32>, Option<Instant>),
    /// 帧时间统计（0.5 秒一段，调试用）：帧数、游戏帧时间最小 / 最大、真实间隔最小 / 最大
    dts: (u32, f32, f32, f32, f32),
    /// 飞行中游戏帧时间连续是 0 的时长；改用真实时间了没有
    zero_t: f32,
    wall_time: bool,
    /// 当前俯仰角（弧度，抬头为正）；起飞前「按世界竖直扶正」开关的值
    pitch: f32,
    saved_align: bool,
}

impl St {
    const fn new() -> Self {
        St {
            mode: Mode::Idle,
            used: false,
            fp_acc: 0.0,
            yaw: 0.0,
            saved_anim_speed: 1.0,
            saved_hks_speed: 1.0,
            saved_flags: (false, false),
            skill_was: false,
            release_t: 0.0,
            pose_pending: false,
            t_mode: 0.0,
            ground_t: 0.0,
            dbg_t: 0.0,
            last: None,
            last_pos: None,
            cmd: None,
            last_anim: -1,
            seen_wings: false,
            via: Via::Warp,
            via_decided: false,
            via_cfg: MoveMode::Auto,
            det: DET0,
            det_prev: None,
            clips: 0,
            block_note: None,
            stuck_log: None,
            win: (0.0, 0.0, 0.0),
            prev_read: None,
            xi: (None, None),
            dts: DTS0,
            zero_t: 0.0,
            wall_time: false,
            pitch: 0.0,
            saved_align: true,
        }
    }
}

/// 朝向 + 俯仰的四元数：先绕本地 X 轴转俯仰，再绕 Y 轴转朝向（Hamilton 积，XYZW）。
/// 绕 X 转 φ 时本地 +Z 往下（(0, -sin φ, cos φ)）、本地 -Z 往上：人物正面是 -Z，抬头 = +φ
fn orient_quat(yaw: f32, pitch: f32, flip: bool) -> Quaternion {
    let phi = pitch * if flip { -1.0 } else { 1.0 };
    let (sy, cy) = (yaw / 2.0).sin_cos();
    let (sp, cp) = (phi / 2.0).sin_cos();
    Quaternion(cy * sp, sy * cp, -sy * sp, cy * cp)
}

/// 想让人物面向水平方向角 a（atan2(x, z)），四元数里的朝向角该是多少：人物正面是 -Z，差 180°。
/// 以前靠平时跑动自动校准，40 多次启动都是这个结果；只要样本被干扰（跑动时朝向和移动方向不一致）就可能定错，
/// 那次运行的飞行朝向全错（2026-11-05 校准成「镜像 75°」，用户「人物在空中的朝向会转动」），所以改成固定的
fn yaw_for(a: f32) -> f32 {
    wrap(a - PI)
}

const DTS0: (u32, f32, f32, f32, f32) = (0, f32::MAX, 0.0, f32::MAX, 0.0);

fn st() -> MutexGuard<'static, St> {
    ST.lock().unwrap_or_else(|e| e.into_inner())
}

fn is_wings(c: &Cfg, id: i32) -> bool {
    c.anim_ids.contains(&id)
}

// ---- 向量
type V3 = (f32, f32, f32);

fn len(v: V3) -> f32 {
    (v.0 * v.0 + v.1 * v.1 + v.2 * v.2).sqrt()
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

/// 绕 Y 轴转 yaw：+Z 转到 (sin yaw, 0, cos yaw)
fn yaw_quat(yaw: f32) -> Quaternion {
    Quaternion(0.0, (yaw / 2.0).sin(), 0.0, (yaw / 2.0).cos())
}

/// 用四元数（XYZW）转一个向量（q v q*）
fn rotate(q: &Quaternion, v: V3) -> V3 {
    let (x, y, z, w) = (q.0, q.1, q.2, q.3);
    let t = (2.0 * (y * v.2 - z * v.1), 2.0 * (z * v.0 - x * v.2), 2.0 * (x * v.1 - y * v.0));
    (v.0 + w * t.0 + (y * t.2 - z * t.1), v.1 + w * t.1 + (z * t.0 - x * t.2), v.2 + w * t.2 + (x * t.1 - y * t.0))
}

/// 反着转（共轭四元数）
fn rotate_inv(q: &Quaternion, v: V3) -> V3 {
    rotate(&Quaternion(-q.0, -q.1, -q.2, q.3), v)
}

/// 水平长度、两个向量水平方向的夹角（弧度）
fn hlen(v: V3) -> f32 {
    (v.0 * v.0 + v.2 * v.2).sqrt()
}

fn hangle(a: V3, b: V3) -> f32 {
    wrap(a.0.atan2(a.2) - b.0.atan2(b.2)).abs()
}

// ---- 防穿墙：改位置前沿移动方向打射线（CSPhysWorld::cast_ray，1.17.1 / 1.17.2 地址都有）
/// 玩家移动用的碰撞过滤（er-mario 的 PLAYER_MOVE_FILTER：玩家实际会撞上的地形和物件；0x08 只有地面）
const RAY_FILTER: u32 = 0x1704;
/// 停在离墙这么远（人物胶囊半径左右）
const BODY_R: f32 = 0.45;
/// 从脚底往上打射线的高度：膝盖、胸口、头顶
const RAY_H: [f32; 3] = [0.3, 1.0, 1.6];

/// 只有地面 / 地形的过滤（er-mario）：被挡时胸口那条用它重打一次，看挡住的是地形本身还是别的（日志，2026-11-10 用户「前面没东西」）
const GROUND_FILTER: u32 = 0x08;

/// 从 o 沿 d 打射线（用玩家的碰撞过滤、不撞自己），撞到返回撞点
fn ray_hit(o: V3, d: V3, me: &PlayerIns) -> Option<V3> {
    ray_hit_f(RAY_FILTER, o, d, me)
}

fn ray_hit_f(filter: u32, o: V3, d: V3, me: &PlayerIns) -> Option<V3> {
    let hm = unsafe { CSHavokMan::instance() }.ok()?;
    let h = hm.phys_world.cast_ray(filter, &HavokPosition(o.0, o.1, o.2, 0.0), PositionDelta(d.0, d.1, d.2), me)?;
    Some((h.0, h.1, h.2))
}

/// 被挡时胸口那条换「只有地面」的过滤重打：（撞没撞上, 距离）的说明
fn ground_note(pos: V3, d: V3, me: &PlayerIns) -> String {
    let Some(u) = norm(d) else { return String::new() };
    let o = (pos.0, pos.1 + RAY_H[1], pos.2);
    match ray_hit_f(GROUND_FILTER, o, mul(u, len(d) + BODY_R + 1.0), me) {
        Some(h) => format!("只看地形也撞上（{:.2} 米）", len(add(h, mul(o, -1.0)))),
        None => "只看地形撞不上（挡住的不是地形本身）".into(),
    }
}

/// 撞点离起点不到 NEAR 米 = 起点可能在模型里面（射线从里往外打出去）。往回退 BACK 米重打一次：重打在原起点附近或之前就撞上 =
/// 真贴着墙，照样当墙；穿过原起点才撞上（或没撞上）= 原来那下是从模型里面打出去的，按重打的结果算。
/// 三条里只能有一条这样放过（两条以上都贴着起点 = 真嵌在东西里，都当墙）。用户 2026-11-10「明明没有空气墙的地方也会无法前进」
const NEAR: f32 = 0.05;
const BACK: f32 = 0.3;

/// 一条射线的结果：沿方向离撞点多远（None = 没撞到）、是不是「起点在模型里」重打后放过的
#[derive(Clone, Copy, Debug, Default, PartialEq)]
struct RayInfo {
    dist: Option<f32>,
    inside: bool,
}

/// 三个高度（膝盖、胸口、头顶）各沿 d 打一条（长度 |d| + BODY_R）。ray(起点, 位移) → 撞点
fn ray_dists(pos: V3, d: V3, ray: &dyn Fn(V3, V3) -> Option<V3>) -> [RayInfo; 3] {
    let mut out = [RayInfo::default(); 3];
    let Some(u) = norm(d) else { return out };
    let reach = len(d) + BODY_R;
    for (k, h) in RAY_H.iter().enumerate() {
        let o = (pos.0, pos.1 + h, pos.2);
        let Some(hit) = ray(o, mul(u, reach)) else { continue };
        let dist = len(add(hit, mul(o, -1.0)));
        if dist >= NEAR {
            out[k].dist = Some(dist);
            continue;
        }
        let ob = add(o, mul(u, -BACK));
        out[k] = match ray(ob, mul(u, reach + BACK)) {
            Some(h2) if len(add(h2, mul(ob, -1.0))) < BACK + NEAR => RayInfo { dist: Some(dist), inside: false },
            Some(h2) => RayInfo { dist: Some(len(add(h2, mul(ob, -1.0))) - BACK), inside: true },
            None => RayInfo { dist: None, inside: true },
        };
    }
    if out.iter().filter(|r| r.inside).count() > 1 {
        for r in out.iter_mut().filter(|r| r.inside) {
            *r = RayInfo { dist: Some(0.0), inside: false };
        }
    }
    out
}

/// 沿 d 最多能走多远：三条里最近的撞点再退 BODY_R
fn free_of(d: V3, rays: &[RayInfo; 3]) -> f32 {
    rays.iter().filter_map(|r| r.dist).map(|x| (x - BODY_R).max(0.0)).fold(len(d), f32::min)
}

fn free_len(pos: V3, d: V3, ray: &dyn Fn(V3, V3) -> Option<V3>) -> f32 {
    free_of(d, &ray_dists(pos, d, ray))
}

/// 这一帧实际走的位移、往下走是不是被挡住了（落地判断用）、被挡时直着走那三条射线的结果（日志用）。直着走得通就照走；
/// 撞了就在几个方向里挑走得最远的（每个方向都重新打三条射线检查）：直着走到墙前、只走水平（擦着地面 / 天花板）、只走竖直、
/// 沿墙面滑（胸口高度往左右各偏 25° 打两条，两个撞点连线是墙面方向）、往上偏（膝盖碰到矮东西 / 斜坡时从上面过去）、
/// 往下偏（头顶碰到树枝 / 屋檐时从下面钻过去；2026-11-10 加）
fn clip_move(pos: V3, d: V3, ray: &dyn Fn(V3, V3) -> Option<V3>) -> (V3, bool, Option<[RayInfo; 3]>) {
    let l = len(d);
    if l < 1e-4 {
        return (d, false, None);
    }
    let rays = ray_dists(pos, d, ray);
    let f = free_of(d, &rays);
    if f >= l - 1e-3 {
        return (d, false, None);
    }
    let (dh, lh) = ((d.0, 0.0, d.2), hlen(d));
    let mut cands = vec![dh, (0.0, d.1, 0.0)];
    if lh > 1e-3 {
        let o = (pos.0, pos.1 + 1.0, pos.2);
        let (a, reach) = (d.0.atan2(d.2), lh + BODY_R + 1.5);
        let hits: Vec<V3> = [-0.44f32, 0.44]
            .iter()
            .filter_map(|da| ray(o, ((a + da).sin() * reach, 0.0, (a + da).cos() * reach)))
            .collect();
        if let [h0, h1] = hits[..] {
            if let Some(t) = norm((h0.0 - h1.0, 0.0, h0.2 - h1.2)) {
                cands.push(mul(t, dh.0 * t.0 + dh.2 * t.2));
            }
        }
        if let Some(u) = norm((d.0, d.1.max(0.0) + lh * 0.8, d.2)) {
            cands.push(mul(u, l));
        }
        if let Some(u) = norm((d.0, d.1.min(0.0) - lh * 0.8, d.2)) {
            cands.push(mul(u, l));
        }
    }
    let mut best = mul(d, f / l);
    for c in cands {
        let lc = len(c);
        if lc < 1e-4 {
            continue;
        }
        let mv = mul(c, free_len(pos, c, ray).min(lc) / lc);
        if len(mv) > len(best) + 1e-4 {
            best = mv;
        }
    }
    (best, d.1 < -1e-3 && best.1 > 0.5 * d.1, Some(rays))
}

/// 被挡时三条射线的样子（日志）：「膝 0.12 米 胸 通 头 通（膝：起点在模型里，重打后放过）」
fn rays_note(r: &[RayInfo; 3]) -> String {
    let names = ["膝", "胸", "头"];
    let mut s = String::new();
    for (k, x) in r.iter().enumerate() {
        s += &match x.dist {
            Some(v) => format!("{} {v:.2} 米 ", names[k]),
            None => format!("{} 通 ", names[k]),
        };
    }
    let ins: Vec<&str> = (0..3).filter(|&k| r[k].inside).map(|k| names[k]).collect();
    if !ins.is_empty() {
        s += &format!("（{}：起点在模型里，重打后放过）", ins.join("、"));
    }
    s.trim_end().to_string()
}

/// 四元数（XYZW）把 +Z 转到哪个方向，取水平朝向角
fn quat_yaw(q: &Quaternion) -> f32 {
    let (x, y, z, w) = (q.0, q.1, q.2, q.3);
    let fx = 2.0 * (x * z + w * y);
    let fz = 1.0 - 2.0 * (x * x + y * y);
    fx.atan2(fz)
}

fn wrap(a: f32) -> f32 {
    let mut a = a % (2.0 * PI);
    if a > PI {
        a -= 2.0 * PI;
    } else if a < -PI {
        a += 2.0 * PI;
    }
    a
}

/// 镜头方向：（前方（含俯仰）, 水平前方, 水平右方）。前方用「镜头 → 人物胸口」的方向（第三人称镜头就在人物后上方），
/// 镜头离人物太远 / 太近（不在同一个坐标系等）时退回镜头矩阵的前方；右方的正负按镜头矩阵的右方对齐
fn camera_basis(c: &Cfg, pos: V3, dbg: &mut String) -> Option<(V3, V3, V3)> {
    let cam = unsafe { CSCamera::instance() }.ok()?;
    let pc = &cam.pers_cam_1;
    let cp = pc.position();
    let to_chr = (pos.0 - cp.0, pos.1 + 1.4 - cp.1, pos.2 - cp.2);
    let mf = pc.forward();
    let mr = pc.right();
    let d = len(to_chr);
    let fwd3 = if (0.5..40.0).contains(&d) { norm(to_chr)? } else { norm((mf.0, mf.1, mf.2))? };
    let fwd_h = norm((fwd3.0, 0.0, fwd3.2))?;
    let mut right = (fwd_h.2, 0.0, -fwd_h.0);
    if right.0 * mr.0 + right.2 * mr.2 < 0.0 {
        right = mul(right, -1.0);
    }
    if c.flip_lr {
        right = mul(right, -1.0);
    }
    if c.debug {
        *dbg = format!(
            "镜头 {:.1},{:.1},{:.1} 距离 {d:.1} 前 {:.2},{:.2},{:.2} 矩阵前 {:.2},{:.2},{:.2} 矩阵右 {:.2},{:.2},{:.2} 右 {:.2},{:.2}",
            cp.0, cp.1, cp.2, fwd3.0, fwd3.1, fwd3.2, mf.0, mf.1, mf.2, mr.0, mr.1, mr.2, right.0, right.2
        );
    }
    Some((fwd3, fwd_h, right))
}

/// 输入：（前后, 左右, 上下, 加速, 战技键）。摇杆用模拟量，键盘（WASD）按下 = 1
struct Input {
    fwd: f32,
    side: f32,
    up: f32,
    boost: bool,
    skill: bool,
    /// 移动方向从哪读到的（调试用）
    src: &'static str,
}

/// 游戏窗口在前台（键盘只在这时读，免得在别的程序里打字也会飞）
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

/// 手柄左摇杆（XInput）/ 键盘 WASD 的原始移动输入：（前后, 左右, 来源）。
/// 飞行时关掉了人物的移动，游戏的移动键查询会读到 0（第二次实测），所以直接读设备。
/// 没接的手柄位查起来慢：认准一个接着的手柄，没有时每秒才重新找一次
fn raw_move(xi: &mut (Option<u32>, Option<Instant>)) -> (f32, f32, &'static str) {
    if !game_focused() {
        return (0.0, 0.0, "窗口不在前台");
    }
    let read = |i: u32| {
        let mut s = XINPUT_STATE::default();
        (unsafe { XInputGetState(i, &mut s) } == 0).then_some(s)
    };
    if xi.0.is_none() && xi.1.is_none_or(|t| t.elapsed().as_secs_f32() > 1.0) {
        xi.1 = Some(Instant::now());
        xi.0 = (0..4).find(|&i| read(i).is_some());
    }
    if let Some(i) = xi.0 {
        match read(i) {
            Some(s) => {
                let (x, y) = (s.Gamepad.sThumbLX as f32 / 32767.0, s.Gamepad.sThumbLY as f32 / 32767.0);
                let mag = (x * x + y * y).sqrt();
                if mag > 0.24 {
                    let k = ((mag - 0.24) / 0.76).min(1.0) / mag;
                    return (y * k, x * k, "手柄摇杆");
                }
            }
            None => xi.0 = None,
        }
    }
    let k = |vk: i32| (unsafe { GetAsyncKeyState(vk) } as u16 & 0x8000 != 0) as i32 as f32;
    let (fwd, side) = (k(0x57) - k(0x53), k(0x44) - k(0x41)); // W / S，D / A
    (fwd, side, if fwd != 0.0 || side != 0.0 { "键盘 WASD" } else { "无" })
}

/// 游戏自己的输入（按键设置改过也认得）；移动方向在飞行时由 tick 用 raw_move 补
fn read_input() -> Input {
    let none = Input { fwd: 0.0, side: 0.0, up: 0.0, boost: false, skill: false, src: "无" };
    let Some(pad) = unsafe { FD4PadManager::instance() }.ok().and_then(|m| m.get_in_game_pad()) else { return none };
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
    let key = |k: UserInputKey| pad.poll_digital_input(k);
    let (fwd, side) = (axis(UserInputKey::MoveForwards) - axis(UserInputKey::MoveBackwards), axis(UserInputKey::MoveRight) - axis(UserInputKey::MoveLeft));
    Input {
        fwd,
        side,
        up: (key(UserInputKey::Jump) as i32 - key(UserInputKey::Crouch) as i32) as f32, // vertical_keys 关掉时 tick 里清 0
        boost: key(UserInputKey::Backstep),
        skill: key(UserInputKey::Skill),
        src: if fwd != 0.0 || side != 0.0 { "游戏输入" } else { "无" },
    }
}

// ---- 每帧
/// 行为更新前：定住动画（播放速度 0）
fn pre_behavior() {
    if !FROZEN.load(Ordering::Relaxed) {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else { return };
    let m: &mut ChrInsModuleContainer = &mut p.chr_ins.modules;
    m.behavior.animation_speed = 0.0;
    m.behavior_data.hks_animation_speed_multiplier = 0.0;
}

/// 起飞前核对人物结构：飞行要写的几个模块（物理、行为、行为数据、坠落、数据、动画）的「所属角色」都指回这个人物，
/// 动画速度、血、蓝在合理范围。地址表是按版本选的，但结构布局只有 2.7.1.0 实测过；游戏更新后结构挪了位置时
/// 这里对不上就停用飞行（只写一行日志），免得往错的位置写东西把游戏写崩
fn layout_check(p: &PlayerIns) -> Result<(), String> {
    let me = &p.chr_ins as *const _ as usize;
    let m = &p.chr_ins.modules;
    for (n, o) in [
        ("物理", m.physics.owner.as_ptr() as usize),
        ("行为", m.behavior.owner.as_ptr() as usize),
        ("行为数据", m.behavior_data.owner.as_ptr() as usize),
        ("坠落", m.fall.owner.as_ptr() as usize),
        ("数据", m.data.owner.as_ptr() as usize),
        ("动画", m.time_act.owner.as_ptr() as usize),
    ] {
        if o != me {
            return Err(format!("{n}模块的所属角色对不上（{o:#x} / {me:#x}）"));
        }
    }
    let (sp, hs) = (m.behavior.animation_speed, m.behavior_data.hks_animation_speed_multiplier);
    if !(0.0..=10.0).contains(&sp) || !(0.0..=10.0).contains(&hs) {
        return Err(format!("动画速度 {sp} / {hs} 不合理"));
    }
    let d = &m.data;
    if d.hp <= 0 || d.hp > d.max_hp || d.fp < 0 || d.fp > d.max_fp {
        return Err(format!("血 {} / {}、蓝 {} / {} 不合理", d.hp, d.max_hp, d.fp, d.max_fp));
    }
    Ok(())
}

/// 放开定住的动画：播放速度写回起飞前的值（不写回的话游戏不一定会自己改回来，人物会一直卡住）
fn unfreeze(st: &St, m: &mut ChrInsModuleContainer) {
    if FROZEN.swap(false, Ordering::Relaxed) {
        m.behavior.animation_speed = st.saved_anim_speed;
        m.behavior_data.hks_animation_speed_multiplier = st.saved_hks_speed;
    }
}

/// 结束飞行 / 滑翔：放开动画（还是这招的话接着放原版的俯冲斩）、恢复动作
fn finish(st: &mut St, p: &mut PlayerIns, why: &str) {
    unfreeze(st, &mut p.chr_ins.modules);
    // 扶正：去掉俯仰、恢复「按世界竖直扶正」
    let ph = &mut p.chr_ins.modules.physics;
    let q = yaw_quat(st.yaw);
    ph.orientation = q;
    ph.interpolated_orientation = q;
    ph.use_world_y_alignment_logic = st.saved_align;
    st.pitch = 0.0;
    p.chr_ins.debug_flags.set_disabled_secondary_actions(st.saved_flags.0);
    p.chr_ins.debug_flags.set_disabled_movement(st.saved_flags.1);
    log(&format!("{}结束：{why}（用时 {:.1} 秒）", if st.mode == Mode::Fly { "飞行" } else { "滑翔" }, st.t_mode));
    st.mode = Mode::Idle;
    st.used = true;
    st.pose_pending = false;
}

fn set_mode(st: &mut St, mode: Mode, why: &str) {
    log(&format!("{:?} → {:?}：{why}", st.mode, mode));
    st.mode = mode;
    st.t_mode = 0.0;
    st.ground_t = 0.0;
    st.cmd = None;
    st.prev_read = None;
    st.det = DET0;
    st.det_prev = None;
    st.win = (0.0, 0.0, 0.0);
    st.dts = DTS0;
    st.zero_t = 0.0;
}

/// 物理更新前：状态机、扣蓝、移动、朝向
fn tick() {
    let mut c = cfg();
    let mut st = st();
    let now = Instant::now();
    let wall_dt = st.last.map(|t| now.duration_since(t).as_secs_f32()).unwrap_or(0.0).min(0.1);
    st.last = Some(now);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        if st.mode != Mode::Idle {
            log("玩家角色没了（读盘 / 回标题），飞行状态清掉");
            FROZEN.store(false, Ordering::Relaxed);
            st.mode = Mode::Idle;
        }
        st.last_pos = None;
        return;
    };
    let p: &mut PlayerIns = p;
    // 帧时间：用游戏这一帧更新这个人物用的（和镜头、动画同步）。以前按两次调用之间的真实时间算，
    // 游戏帧间隔不均匀时人物这帧走多、下帧走少，镜头又是平滑跟着的，看着一顿一顿（用户反馈飞行卡顿）。
    // 读到的不合理（负数、NaN、超过 0.1 秒）时退回真实时间；0 = 这一帧游戏没更新人物（暂停等），不动
    // 保险：飞行中游戏帧时间连续 1 秒都是 0（这个字段不是我们以为的意思）就改回真实时间，这次进游戏一直用
    let gdt = p.chr_ins.chr_update_delta_time;
    if st.mode != Mode::Idle && !st.wall_time {
        st.zero_t = if gdt == 0.0 { st.zero_t + wall_dt } else { 0.0 };
        if st.zero_t > 1.0 {
            st.wall_time = true;
            log("飞行中游戏帧时间一直是 0：改回按真实时间算位移");
        }
    }
    let dt = if !st.wall_time && gdt.is_finite() && (0.0..=0.1).contains(&gdt) { gdt } else { wall_dt };
    if st.mode != Mode::Idle {
        let w = &mut st.dts;
        *w = (w.0 + 1, w.1.min(gdt), w.2.max(gdt), w.3.min(wall_dt), w.4.max(wall_dt));
    }
    let (anim, play_time) = {
        let ta = &p.chr_ins.modules.time_act;
        let a = &ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()];
        (a.anim_id, a.play_time)
    };
    let wings = is_wings(&c, anim);
    if c.debug && anim != st.last_anim {
        log(&format!("动画 {} → {anim}", st.last_anim));
    }
    st.last_anim = anim;
    if wings && !st.seen_wings {
        st.seen_wings = true;
        log(&format!("认出「熔炉百相之羽」动画 {anim}"));
    }
    // 血、蓝用人物数据模块里的（存档数据里的 current_fp 每帧被这里覆盖，改那边扣不掉蓝：第三次实测）
    let (hp, fp) = {
        let d = &p.chr_ins.modules.data;
        (d.hp, d.fp)
    };
    let pos = {
        let x = &p.chr_ins.modules.physics.position;
        (x.0, x.1, x.2)
    };
    let warped = st.last_pos.is_some_and(|q| len((pos.0 - q.0, pos.1 - q.1, pos.2 - q.2)) > 60.0);
    st.last_pos = Some(pos);
    let mut inp = read_input();
    if !c.vertical_keys {
        inp.up = 0.0;
    }
    let skill_edge = inp.skill && !st.skill_was;
    st.skill_was = inp.skill;

    if st.mode == Mode::Idle {
        if !wings {
            st.used = false;
            return;
        }
        if st.used || !c.enabled || play_time < c.hover_time {
            return;
        }
        st.used = true;
        if c.hold_to_fly && !inp.skill {
            if c.debug {
                log("没按住战技键：原版俯冲斩");
            }
            return;
        }
        c = reload_cfg();
        if !c.enabled {
            return;
        }
        // 移动办法：第一次起飞、ini 里改了 move_mode 时重新定（只有 root_motion 要判断坐标系）
        if c.move_mode != st.via_cfg || (st.via == Via::Warp) != (c.move_mode != MoveMode::RootMotion) {
            st.via_cfg = c.move_mode;
            let root = c.move_mode == MoveMode::RootMotion;
            st.via = if root { Via::RootWorld } else { Via::Warp };
            st.via_decided = !root;
        }
        match LAYOUT.load(Ordering::Relaxed) {
            2 => return,
            0 => match layout_check(p) {
                Ok(()) => {
                    LAYOUT.store(1, Ordering::Relaxed);
                    log("人物结构自检通过");
                }
                Err(e) => {
                    LAYOUT.store(2, Ordering::Relaxed);
                    log(&format!("人物结构自检没通过（游戏版本的结构变了？）：{e}；这次进游戏不再飞行"));
                    return;
                }
            },
            _ => {}
        }
        if fp < c.min_fp as i32 {
            log(&format!("蓝不够（{fp}）：不起飞"));
            return;
        }
        let m: &mut ChrInsModuleContainer = &mut p.chr_ins.modules;
        st.saved_anim_speed = if m.behavior.animation_speed > 0.0 { m.behavior.animation_speed } else { 1.0 };
        st.saved_hks_speed = if m.behavior_data.hks_animation_speed_multiplier > 0.0 { m.behavior_data.hks_animation_speed_multiplier } else { 1.0 };
        st.yaw = quat_yaw(&m.physics.orientation);
        st.pitch = 0.0;
        st.saved_align = m.physics.use_world_y_alignment_logic;
        if c.body_pitch {
            m.physics.use_world_y_alignment_logic = false;
        }
        st.fp_acc = 0.0;
        // 攻击 / 跳跃 / 翻滚 / 移动这些动作暂时关掉：飞行时这些键由这里读（直接读手柄，不受这两个开关影响）
        let f = &mut p.chr_ins.debug_flags;
        st.saved_flags = (f.disabled_secondary_actions(), f.disabled_movement());
        f.set_disabled_secondary_actions(true);
        f.set_disabled_movement(true);
        // 姿势：动画接着放到 pose_time 再定住（已经过了就马上定住）
        st.pose_pending = play_time < c.pose_time;
        FROZEN.store(!st.pose_pending, Ordering::Relaxed);
        let why = format!(
            "动画 {anim} 第 {play_time:.2} 秒起飞，姿势定在第 {:.2} 秒，蓝 {fp}，动画速度 {:.2} / {:.2}，移动 {:?}{}",
            c.pose_time.max(play_time),
            st.saved_anim_speed,
            st.saved_hks_speed,
            st.via,
            if st.via == Via::Warp {
                if c.wall_check { "（射线防穿墙）" } else { "（没开防穿墙）" }
            } else if st.via_decided {
                ""
            } else {
                "（还在判断坐标系）"
            }
        );
        set_mode(&mut st, Mode::Fly, &why);
        st.skill_was = true;
        st.release_t = 0.0;
        return;
    }

    st.t_mode += dt;
    // 结束条件
    if hp <= 0 {
        return finish(&mut st, p, "人物死亡");
    }
    if warped {
        return finish(&mut st, p, "位置跳变（传送 / 读盘）");
    }
    if st.mode == Mode::Fly {
        if c.hold_to_fly {
            // 松开战技键（0.1 秒，去掉偶尔一帧读不到）：结束，接原版俯冲斩
            st.release_t = if inp.skill { 0.0 } else { st.release_t + dt };
            if st.release_t > 0.1 {
                return finish(&mut st, p, "松开战技键：俯冲斩");
            }
        } else if skill_edge {
            return finish(&mut st, p, "再按战技键：俯冲斩");
        }
    }
    if st.mode == Mode::Fly && !wings {
        st.pose_pending = false;
        unfreeze(&st, &mut p.chr_ins.modules);
        set_mode(&mut st, Mode::Glide, &format!("动画被打断（现在是 {anim}）"));
    }
    if st.pose_pending && wings && play_time >= c.pose_time {
        st.pose_pending = false;
        FROZEN.store(true, Ordering::Relaxed);
        if c.debug {
            log(&format!("姿势定在动画第 {play_time:.2} 秒"));
        }
    }
    if st.mode == Mode::Glide && st.t_mode > c.max_glide_secs {
        return finish(&mut st, p, "滑翔超时");
    }

    // 扣蓝（默认不扣：用户要求飞行不耗蓝；两个数都是 0 时蓝空了也照样飞）
    let rate = if inp.boost { c.boost_fp_per_sec } else { c.fp_per_sec };
    if st.mode == Mode::Fly && (c.fp_per_sec > 0.0 || c.boost_fp_per_sec > 0.0) {
        st.fp_acc += rate * dt;
        let n = st.fp_acc.floor();
        let d = &mut p.chr_ins.modules.data;
        if n >= 1.0 {
            st.fp_acc -= n;
            d.fp = (d.fp - n as i32).max(0);
        }
        if d.fp <= 0 {
            set_mode(&mut st, Mode::Glide, "蓝用完");
        }
    }

    // 速度（游戏的移动输入读不到时直接读摇杆 / WASD）
    if inp.fwd == 0.0 && inp.side == 0.0 {
        (inp.fwd, inp.side, inp.src) = raw_move(&mut st.xi);
    }
    let mut dbg = String::new();
    let Some((fwd3, fwd_h, right)) = camera_basis(&c, pos, &mut dbg) else { return };
    let v = if st.mode == Mode::Fly {
        // 前方：水平前方按镜头俯仰抬起 / 压低，俯仰先减掉死区（第四次实测：平时视角往前推一直在往下飞，贴地就被当成落地）
        let fwd = if c.pitch_follow {
            let pitch = fwd3.1.clamp(-1.0, 1.0).asin();
            let eff = pitch.signum() * (pitch.abs() - c.pitch_deadzone.to_radians()).max(0.0);
            (fwd_h.0 * eff.cos(), eff.sin(), fwd_h.2 * eff.cos())
        } else {
            fwd_h
        };
        // 自动向前：一直全速往前，前后输入不起作用（不能刹车、不能悬停），只剩左右和镜头的方向 / 俯仰
        let f_in = if c.auto_forward { 1.0 } else { inp.fwd };
        let dir = add(mul(fwd, f_in), mul(right, inp.side));
        let l = len(dir);
        let dir = if l > 1.0 { mul(dir, 1.0 / l) } else { dir };
        let spd = if inp.boost { c.boost_speed } else { c.speed };
        add(mul(dir, spd), (0.0, inp.up * c.vertical_speed, 0.0))
    } else {
        let dir = add(mul(fwd_h, inp.fwd), mul(right, inp.side));
        let l = len(dir);
        let dir = if l > 1.0 { mul(dir, 1.0 / l) } else { dir };
        add(mul(dir, c.glide_speed), (0.0, -c.glide_fall, 0.0))
    };

    // 这一帧要走的位移；改位置时先打射线防穿墙（往下走被地面挡住也算落地）
    let dw = mul(v, dt);
    let (mv, down_hit, rays) = if st.via == Via::Warp && c.wall_check { clip_move(pos, dw, &|o, d| ray_hit(o, d, p)) } else { (dw, false, None) };
    if len(mv) + 1e-3 < len(dw) {
        st.clips += 1;
        if let Some(r) = rays {
            st.block_note = Some(format!("{}，{}；地图块 {} 位置 {:.1},{:.1},{:.1} 方向 {:.2},{:.2},{:.2}", rays_note(&r), ground_note(pos, dw, p),
                                         p.current_block_id, pos.0, pos.1, pos.2, dw.0 / len(dw), dw.1 / len(dw), dw.2 / len(dw)));
        }
    }

    let m: &mut ChrInsModuleContainer = &mut p.chr_ins.modules;
    // 落地：上一帧命令往下走，这一帧读到的位置却被顶回去一半以上（地面挡住），或者这一帧往下打射线就碰到地面。物理模块里的
    // 「站在地上 / 碰到地面」在空中也是 true（实测：起飞 0.5 秒就被当成落地），不能用。飞行时只认按住蹲下键往下降（低头往前飞擦到地面不结束）
    let blocked = down_hit || st.cmd.is_some_and(|(q, dy)| dy < -1e-3 && pos.1 - q.1 > -0.5 * dy);
    let landing = if st.mode == Mode::Fly { inp.up < 0.0 } else { v.1 < 0.0 };
    if blocked && landing {
        st.ground_t += dt;
        if st.ground_t > 0.15 {
            return finish(&mut st, p, "落地");
        }
    } else {
        st.ground_t = 0.0;
    }
    let flags = (m.physics.standing_on_solid_ground, m.physics.touching_solid_ground, m.physics.is_falling, m.physics.is_touching_ground);

    // 写本帧位移时判断坐标系：上一帧写的位移这一帧才体现在位置上。0.3 秒一段（命令水平走了 0.5 米以上才算）：
    // 实际方向和「按世界」对上 → 世界坐标；和「按本地」对上 → 改成按本地坐标写；两个都对上（人物正好朝 +Z）不算；
    // 几乎不动连续两段、而且是刚起飞（还没碰到墙的时候）→ 自动模式退回改位置
    if let (Some(q0), Some((dw, dl))) = (st.prev_read, st.det_prev) {
        if !st.via_decided && st.via != Via::Warp {
            let d = &mut st.det;
            d.cw = add(d.cw, dw);
            d.cl = add(d.cl, dl);
            d.act = add(d.act, (pos.0 - q0.0, pos.1 - q0.1, pos.2 - q0.2));
            d.t += dt;
            if d.t >= 0.3 && hlen(d.cw) > 0.5 {
                let (r, aw, al) = (hlen(d.act) / hlen(d.cw), hangle(d.act, d.cw).to_degrees(), hangle(d.act, d.cl).to_degrees());
                let msg = format!("命令 {:.2} 米、实际 {:.2} 米，和按世界差 {aw:.0}°、和按本地差 {al:.0}°", hlen(d.cw), hlen(d.act));
                let mut stuck = 0;
                if r > 0.3 && aw < 25.0 && al >= 25.0 {
                    st.via_decided = true;
                    log(&format!("写本帧位移：游戏按世界坐标算（{msg}）"));
                } else if r > 0.3 && al < 25.0 && aw >= 25.0 {
                    st.via = Via::RootLocal;
                    st.via_decided = true;
                    log(&format!("写本帧位移：游戏按人物本地坐标算（{msg}），以后按本地坐标写"));
                } else if r < 0.15 {
                    stuck = d.stuck + 1;
                    if stuck == 2 {
                        log(&format!("写本帧位移几乎不动（{msg}；动画定住后游戏不按它走，move_mode 改回 auto）"));
                    }
                } else if c.debug {
                    log(&format!("写本帧位移：坐标系还看不出来（{msg}）"));
                }
                st.det = Det { stuck, ..DET0 };
            }
        }
    }

    // 移动效果：实际走了多少 / 命令走了多少（调试日志）
    if let Some(q) = st.prev_read {
        st.win.1 += len((pos.0 - q.0, pos.1 - q.1, pos.2 - q.2));
    }
    st.prev_read = Some(pos);
    st.win.0 += len(v) * dt;
    st.win.2 += dt;
    if st.win.2 >= 0.5 {
        let (cmd, act, _) = st.win;
        if c.debug {
            let w = st.dts;
            log(&format!(
                "0.5 秒：命令走 {cmd:.2} 米，实际 {act:.2} 米（{:?}{}，挡住 {} 帧）；{} 帧，游戏帧时间 {:.1}~{:.1} 毫秒，真实间隔 {:.1}~{:.1} 毫秒{}",
                st.via, if st.via == Via::Warp || st.via_decided { "" } else { "，还在判断" }, st.clips,
                w.0, w.1 * 1000.0, w.2 * 1000.0, w.3 * 1000.0, w.4 * 1000.0, if st.wall_time { "（用真实时间）" } else { "" }
            ));
        }
        // 被挡得走不动（不开 debug 也记，最多 3 秒一行）：这 0.5 秒命令走 2 米以上、实际不到 4 成、一半以上的帧被挡
        if !c.debug && cmd > 2.0 && act < 0.4 * cmd && st.clips >= st.dts.0.max(1) / 2 && st.stuck_log.is_none_or(|t| t.elapsed().as_secs_f32() > 3.0) {
            st.stuck_log = Some(Instant::now());
            log(&format!("飞行被挡：0.5 秒命令走 {cmd:.1} 米，实际 {act:.1} 米，挡住 {} 帧；最后一次 {}", st.clips, st.block_note.as_deref().unwrap_or("（没记到）")));
        } else if c.debug {
            if let Some(n) = &st.block_note {
                log(&format!("  最后一次被挡：{n}"));
            }
        }
        st.block_note = None;
        st.clips = 0;
        st.win = (0.0, 0.0, 0.0);
        st.dts = DTS0;
    }

    // 朝向：水平移动时慢慢转向移动方向（先算出这一帧的朝向，按本地坐标写位移要用）
    let hv = (v.0, 0.0, v.2);
    if len(hv) > 0.5 {
        let mut target = yaw_for(hv.0.atan2(hv.2));
        if c.flip_face {
            target = wrap(target + PI);
        }
        let step = c.turn_rate.to_radians() * dt;
        st.yaw = wrap(st.yaw + wrap(target - st.yaw).clamp(-step, step));
    }
    // 俯仰：跟着速度方向抬头 / 低头（只往上下飞时按最大俯仰角），悬停时回正；速度是转向速度的一半
    let target_pitch = if c.body_pitch && len(v) > 0.5 {
        let mp = c.max_pitch.to_radians();
        v.1.atan2(len(hv)).clamp(-mp, mp)
    } else {
        0.0
    };
    let pstep = c.turn_rate.to_radians() * 0.5 * dt;
    st.pitch += (target_pitch - st.pitch).clamp(-pstep, pstep);
    let q = orient_quat(st.yaw, st.pitch, c.flip_pitch != c.flip_face);

    // 移动；关重力、清坠落计时
    let np = match st.via {
        Via::RootWorld | Via::RootLocal => {
            // 写本帧位移：游戏的角色控制器按它走，撞墙停下 / 沿墙滑
            let d = if st.via == Via::RootLocal { rotate_inv(&q, dw) } else { dw };
            let d4 = F32Vector4(d.0, d.1, d.2, 0.0);
            m.behavior.root_motion = d4;
            m.physics.root_motion = d4;
            st.det_prev = Some((dw, rotate(&q, dw)));
            add(pos, dw)
        }
        Via::Warp => {
            // 改位置 + 让角色代理按新位置重放；清掉这一帧的动画位移。高度从上一帧命令的高度接着算（读到的比命令的低时最多补 0.3 米）：
            // 姿势定在关重力的 TAE 事件（到 1.567 秒）之后，万一重力没关住也不会一点点往下沉；被地面顶高时照读到的
            let base_y = match st.cmd {
                Some((q, _)) if pos.1 < q.1 => q.1.min(pos.1 + 0.3),
                _ => pos.1,
            };
            let np = (pos.0 + mv.0, base_y + mv.1, pos.2 + mv.2);
            let w = m.physics.position.3;
            m.physics.position = HavokPosition(np.0, np.1, np.2, w);
            m.physics.chr_proxy_pos_update_requested = true;
            m.behavior.root_motion = F32Vector4(0.0, 0.0, 0.0, 0.0);
            m.physics.root_motion = F32Vector4(0.0, 0.0, 0.0, 0.0);
            st.det_prev = None;
            np
        }
    };
    m.physics.gravity_disabled = true;
    m.fall.fall_timer = 0.0;
    st.last_pos = Some(np);
    st.cmd = Some((np, mv.1));

    m.physics.orientation = q;
    m.physics.interpolated_orientation = q;
    if c.body_pitch {
        m.physics.use_world_y_alignment_logic = false;
    }

    if c.debug {
        st.dbg_t += dt;
        if st.dbg_t >= 0.5 {
            st.dbg_t = 0.0;
            let ta = &m.time_act;
            let a = &ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()];
            log(&format!(
                "{:?} {:.1}s 读到 {:.2},{:.2},{:.2} 命令 {:.2},{:.2},{:.2} 速度 {:.1},{:.1},{:.1} 输入 前{:.2} 右{:.2}（{}）上{} 加速{} 朝向角 {:.0}° 移动方向角 {:.0}° 俯仰 {:.0}° 扶正 {} 蓝 {} 动画 {} {:.2}/{:.2} 速度 {:.2} 地面标记 {:?} 挡住 {blocked} {}",
                st.mode, st.t_mode, pos.0, pos.1, pos.2, np.0, np.1, np.2, v.0, v.1, v.2, inp.fwd, inp.side, inp.src, inp.up, inp.boost,
                st.yaw.to_degrees(), v.0.atan2(v.2).to_degrees(), st.pitch.to_degrees(), m.physics.use_world_y_alignment_logic,
                m.data.fp, a.anim_id, a.play_time, a.anim_length,
                m.behavior.animation_speed, flags, dbg
            ));
        }
    }
}

/// 给 dark_core 查：现在是不是正定住主角的动画（飞行中，pre_behavior 每帧写 0）。是的话 dark_core 这一帧不写主角的动画速度
/// （用户 2026-11-12：飞行时裙子不自然地循环扩张——两边同时写，dark_core 写战灰加速 1.25、这里写 0）。飞完 unfreeze 写回起飞前的值
#[unsafe(no_mangle)]
pub extern "C" fn dark_wings_frozen() -> u8 {
    FROZEN.load(Ordering::Relaxed) as u8
}

/// # Safety
/// 由加载器（YAFSML / me3）调用，不要自己调用。
#[unsafe(no_mangle)]
pub unsafe extern "system" fn DllMain(hmodule: u64, reason: u32, _reserved: *mut std::ffi::c_void) -> i32 {
    if reason != 1 {
        return 1;
    }
    let _ = DIR.set(module_dir(hmodule));
    std::panic::set_hook(Box::new(|info| log(&format!("panic：{info}"))));
    let t = local_time();
    log(&format!("==== {}-{:02}-{:02} 加载（进程 {}）", t.year, t.month, t.day, std::process::id()));
    std::thread::spawn(|| {
        if !version_ok() {
            log("游戏版本不是 2.7.1.0（1.17.1）/ 2.7.2.0（1.17.2），dark_wings 不工作");
            return;
        }
        let c = cfg();
        if !c.enabled {
            log("dark_wings.ini 里 enabled = 0：不工作");
            return;
        }
        // 加载器注入得很早：任务调度器可能还没建好，每秒重试（最多 10 分钟）
        let mut task = None;
        for _ in 0..600 {
            if let Ok(t) = CSTaskImp::wait_for_instance(Duration::from_secs(1)) {
                task = Some(t);
                break;
            }
            std::thread::sleep(Duration::from_secs(1));
        }
        let Some(task) = task else {
            log("10 分钟内等不到 CSTaskImp，dark_wings 不工作");
            return;
        };
        log(&format!("dark_wings 已加载：战灰「熔炉百相之羽」按住战技键持续飞行；参数 {c:?}"));
        task.run_recurring(
            |_: &FD4TaskData| {
                if catch_unwind(AssertUnwindSafe(pre_behavior)).is_err() {
                    FROZEN.store(false, Ordering::Relaxed);
                }
            },
            CSTaskGroupIndex::ChrIns_PreBehavior,
        );
        let mut errs = 0u32;
        task.run_recurring(
            move |_: &FD4TaskData| {
                if catch_unwind(AssertUnwindSafe(tick)).is_err() {
                    FROZEN.store(false, Ordering::Relaxed);
                    st().mode = Mode::Idle;
                    errs += 1;
                    if errs <= 3 {
                        log("飞行：读写人物时出错（已停下）");
                    }
                }
            },
            CSTaskGroupIndex::ChrIns_PrePhysics,
        );
    });
    1
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 假地形：竖直的墙 z = wz（x 不限、y 在 y0..y1 之间，两面都挡）
    fn wall(wz: f32, y0: f32, y1: f32) -> impl Fn(V3, V3) -> Option<V3> {
        move |o: V3, d: V3| {
            if d.2.abs() < 1e-6 {
                return None;
            }
            let t = (wz - o.2) / d.2;
            if !(0.0..=1.0).contains(&t) {
                return None;
            }
            let h = add(o, mul(d, t));
            (h.1 >= y0 && h.1 <= y1).then_some(h)
        }
    }

    #[test]
    fn clear_and_wall() {
        let w = wall(5.0, -10.0, 10.0);
        let (mv, _, r) = clip_move((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), &w);
        assert_eq!((mv, r), ((0.0, 0.0, 0.3), None));
        // 墙前 0.5 米的整面墙：可能斜着往上 / 下滑，但不会走到墙跟前
        let (mv, _, r) = clip_move((0.0, 0.0, 4.5), (0.0, 0.0, 0.3), &w);
        assert!(4.5 + mv.2 < 5.0 - 0.3, "{mv:?}");
        assert!(r.is_some());
    }

    #[test]
    fn low_obstacle_goes_over() {
        // 只到膝盖高的矮东西（0~0.5 米）：往上偏着过去，不停在它前面
        let w = wall(1.0, -10.0, 0.5);
        let (mv, _, _) = clip_move((0.0, 0.0, 0.6), (0.0, 0.0, 0.3), &w);
        assert!(mv.1 > 0.1 && len(mv) > 0.25, "{mv:?}");
    }

    #[test]
    fn low_ceiling_goes_under() {
        // 只挡头顶的东西（1.4 米以上，越不过去）：往下偏着钻过去
        let w = wall(1.0, 1.4, 30.0);
        let (mv, _, _) = clip_move((0.0, 0.0, 0.6), (0.0, 0.0, 0.3), &w);
        assert!(mv.1 < -0.1 && len(mv) > 0.25, "{mv:?}");
    }

    #[test]
    fn inside_start_is_retried() {
        // 胸口那条从模型里面往外打：贴着起点就撞上，往回退重打没撞到 → 放过
        let ray = |o: V3, d: V3| -> Option<V3> {
            if (o.1 - 1.0).abs() < 1e-3 && o.2.abs() < 1e-3 && d.2 > 0.0 { Some((o.0, o.1, o.2 + 0.01)) } else { None }
        };
        let r = ray_dists((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), &ray);
        assert_eq!(r[1], RayInfo { dist: None, inside: true });
        assert_eq!(clip_move((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), &ray).0, (0.0, 0.0, 0.3));
        // 真贴着墙（墙就在起点上）：往回退重打在原起点就撞上 → 照样当墙
        let w = wall(0.02, -10.0, 10.0);
        let r = ray_dists((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), &w);
        assert!(r.iter().all(|x| !x.inside && x.dist.is_some()), "{r:?}");
        assert!(len(clip_move((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), &w).0) < 0.01);
    }

    #[test]
    fn two_inside_still_block() {
        // 两条以上都贴着起点 = 真嵌在东西里，都当墙
        let ray = |o: V3, d: V3| -> Option<V3> { (o.1 < 1.5 && o.2.abs() < 1e-3 && d.2 > 0.0).then_some((o.0, o.1, o.2 + 0.01)) };
        let r = ray_dists((0.0, 0.0, 0.0), (0.0, 0.0, 0.3), &ray);
        assert_eq!(r[0], RayInfo { dist: Some(0.0), inside: false });
        assert_eq!(r[1], RayInfo { dist: Some(0.0), inside: false });
    }

    #[test]
    fn cfg_lines() {
        let (c, bad) = parse_cfg("\u{feff}# 注释\nspeed = 15 ; 行尾注释\nhold_to_fly=0\nanim_ids = 1, 2\nflip_lr = yes\nturn_rate=-3\nxx=1\n\n");
        assert_eq!(c.speed, 15.0);
        assert!(!c.hold_to_fly);
        assert!(c.flip_lr);
        assert_eq!(c.anim_ids, vec![1, 2]);
        assert_eq!(c.turn_rate, Cfg::default().turn_rate);
        assert_eq!(bad, vec!["turn_rate=-3".to_string(), "xx=1".to_string()]);
        assert_eq!(parse_cfg("").0, Cfg::default());
    }

    #[test]
    fn shipped_ini_is_default() {
        // 包里带的 dark_wings.ini 每一行都认得出来，数值和代码里的默认值一致（改默认值时两边一起改）；
        // debug 测试时可以开着，打包脚本会拦住 debug = 1
        let (c, bad) = parse_cfg(include_str!("../../../dll/dark_wings/dark_wings.ini"));
        assert!(bad.is_empty(), "{bad:?}");
        assert_eq!(Cfg { debug: false, ..c }, Cfg::default());
    }

    /// 朝向约定固定：移动方向角 = 朝向角 + 180°
    #[test]
    fn facing_fixed() {
        for a in [-2.0f32, 0.0, 1.0, 3.0] {
            assert!(wrap(yaw_for(a) + PI - a).abs() < 1e-4, "{a}");
        }
    }

    /// 俯仰：按 Hamilton 约定把人物正面（-Z）转到「朝向 a、抬头 θ」的方向
    #[test]
    fn pitch_quat() {
        let rot = |q: &Quaternion, v: V3| {
            let (x, y, z, w) = (q.0, q.1, q.2, q.3);
            let t = (2.0 * (y * v.2 - z * v.1), 2.0 * (z * v.0 - x * v.2), 2.0 * (x * v.1 - y * v.0));
            (v.0 + w * t.0 + (y * t.2 - z * t.1), v.1 + w * t.1 + (z * t.0 - x * t.2), v.2 + w * t.2 + (x * t.1 - y * t.0))
        };
        for (a, th) in [(0.3f32, 0.5f32), (-2.0, -0.7), (2.8, 1.2), (1.0, 0.0)] {
            let d = rot(&orient_quat(yaw_for(a), th, false), (0.0, 0.0, -1.0));
            let want = (th.cos() * a.sin(), th.sin(), th.cos() * a.cos());
            assert!(len((d.0 - want.0, d.1 - want.1, d.2 - want.2)) < 1e-4, "{a} {th}: {d:?} vs {want:?}");
        }
        // 俯仰 0 时就是只有朝向的四元数
        let (q0, q1) = (orient_quat(0.7, 0.0, false), yaw_quat(0.7));
        assert!((q0.0 - q1.0).abs() + (q0.1 - q1.1).abs() + (q0.2 - q1.2).abs() + (q0.3 - q1.3).abs() < 1e-6);
    }

    #[test]
    fn yaw_round_trip() {
        for d in [-170.0f32, -90.0, 0.0, 45.0, 135.0, 179.0] {
            let y = d.to_radians();
            assert!((wrap(quat_yaw(&yaw_quat(y)) - y)).abs() < 1e-4, "{d}");
        }
        assert!((wrap(3.0 * PI) - PI).abs() < 1e-4 || (wrap(3.0 * PI) + PI).abs() < 1e-4);
        assert!((wrap(-0.5) + 0.5).abs() < 1e-6);
    }

    /// 四元数转向量：朝向四元数把 +Z 转到 (sin yaw, 0, cos yaw)；反着转回来是原向量（含俯仰）；
    /// 按本地坐标写的位移 rotate_inv(q, d) 经游戏按 q 转回世界正好是 d
    #[test]
    fn rotate_vectors() {
        let y = 0.9f32;
        let r = rotate(&yaw_quat(y), (0.0, 0.0, 1.0));
        assert!((r.0 - y.sin()).abs() < 1e-5 && r.1.abs() < 1e-5 && (r.2 - y.cos()).abs() < 1e-5);
        let q = orient_quat(-2.1, 0.6, false);
        let d = (1.5, -0.4, 2.0);
        let back = rotate(&q, rotate_inv(&q, d));
        assert!(len((back.0 - d.0, back.1 - d.1, back.2 - d.2)) < 1e-5);
        assert!((len(rotate(&q, d)) - len(d)).abs() < 1e-5);
        // 水平夹角
        assert!((hangle((1.0, 5.0, 0.0), (0.0, -3.0, 1.0)).to_degrees() - 90.0).abs() < 1e-3);
        assert!((hlen((3.0, 9.0, 4.0)) - 5.0).abs() < 1e-6);
    }
}
