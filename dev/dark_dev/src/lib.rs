//! Dark Reforged 开发工具（dark_dev，测试用，不打包）：游戏里按 F9 开关一个悬浮窗口，选好类别 / 档 / 本体 / 补正 / 异常 / 战技 / 词条，
//! 点「发放」就把这一件写成 dll\dark_core\devgive_req.txt（格式同 devgive.txt 的一行），dark_core 看到就生成、走鉴定的发货表放进背包、
//! 删掉这个请求文件（生成和发货都在 dark_core 的 gear\devgive.rs，这里只是界面）。
//! 列表（武器 / 防具本体、词条、战技）读 dll\dark_core\affixes.txt（重随生成）；窗口下面显示 dark_core.log 里最近的「开发工具」行。
//! 悬浮层用 hudhook（Dear ImGui，DirectX 12）；窗口开着时挡住游戏的键鼠输入。中文字体用系统的微软雅黑。
//! 「效果调试」区：给自己 / 15 米内最近的敌人挂效果（写 devsp_req.txt，dark_core 的 rules.rs 执行），叠标记的词条（猎印）每层一个按钮。
//! 「相杀火花测试」区：火花的光效行换成几种写法（我们的 / 原版火花、挂武器 / 身上、持续 / 起手，加两个看得见的对照）马上给自己挂上，
//! 找火花不显示的原因（写 clashfx_req.txt，dark_core 的 clash.rs 处理；用户 2026-11-04「确实还是一点没播放出来 开发工具加按钮吧」）。
//! 「一键发放流派」区：一个流派（affixes.txt fam 行的流派，重随写）的每条词条一件护符 + 能上防具的塞进防具 + KIT_WEAPONS 里的武器，
//! 一行一件排队，dark_core 取走一批（请求文件删掉）再写下一批（每批不超过发货表的行数，items.txt 的 deliver）。
//! 「高难度测试」区：发超限锻造石（devgive_req.txt 的「道具 编号 个数」行，编号读 items.txt 的 overlimit 行）、查看最近的敌人血量（核对血量补正）。
//! 「魇化测试」区：让最近的敌人魇化、夺取一次（随机 / 指定词条）、夺取次数一键设成 0 / 1 / 5 / 15 / 30、清空魇火
//! （写 nightmare_req.txt，dark_core 的 nightmare.rs 处理；词条读 nightmare.txt 的 fam 行，名字对 affixes.txt）。
//! 「七咒测试」区：按区域把碎片设成 0 / 4 / 5（5 = 反转）、全部清零 / 全部反转、马上换烙印的目标、试放叙事提示（写 curses_req.txt，dark_core 的 curses.rs 处理）。
//! 「传说光效测试」区：换武器后光效落到手上时马上重挂一次、查看拿着的武器和身上的光效（写 glow_req.txt，dark_core 的 glow.rs 处理）。
//! 「高难度锁定」区：解除 / 恢复这个角色的高难度锁定标记（录素材用，写 curses_req.txt 的「标记」行）。
//! 「死亡以上难度屏障测试」区：不管难度强制围起来 / 取消、在这里重新围、半径、查看状态、试三条提示（写 barrier_req.txt，dark_core 的 barrier.rs 处理）。
//! 「帧耗时统计」区：dark_core 各模块每帧花多久、游戏一帧多长（直接调 dark_core 的导出，不写请求文件；停止时结果写进 dark_core.log）。
//! 测试用的东西都做进这个窗口（用户 2026-11-03：不再让人手写 devgive.txt）。

use std::ffi::c_void;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::{Duration, Instant};

use hudhook::hooks::dx12::ImguiDx12Hooks;
use hudhook::imgui::{self, Condition, FontConfig, FontGlyphRanges, FontSource, Key, Ui};
use hudhook::mh::{MH_EnableHook, MhHook};
use hudhook::windows::Win32::Foundation::RECT;
use hudhook::windows::Win32::System::LibraryLoader::{GetModuleHandleA, GetProcAddress};
use hudhook::windows::core::{BOOL, s};
use hudhook::{ImguiRenderLoop, MessageFilter, RenderContext};

// ------------------------------------------------------------------ 光标
// 游戏里光标被锁住（每帧拉回中央 / 限制在窗口里），窗口开着时鼠标动不了：开着的时候把 SetCursorPos / ClipCursor 拦掉（直接返回成功），
// 每帧再解除一次限制；关上就照常交给游戏
/// 见切成立时挂的羽毛特效（同 launcher\reroll\rr\sounds.py 的 MIKIRI_VFX_SP，两边一起改）
const MIKIRI_VFX_SP: i32 = 7299130;
/// 高难度单程票的锁定标记（同 launcher\reroll\sc\difficulty.py 的 LOCK，两边一起改）
const DIFF_LOCK_FLAG: u32 = 93910;
/// 碎骨 / 千钧满蓄力出招期间的光，试放用的 3 秒效果（同 rr/sounds.py 的 DEV_VFX_SP，两边一起改）
const POISE_GLOW_DEV_SP: i32 = 7299135;
/// 效果调试里列试放按钮的词条（触发时一闪的特效，用户 2026-11-13）：换气、回光、余裕、交替、引爆、近身
const FLASH_KEYS: [&str; 6] = ["dr_second_breath", "dr_last_light", "dr_composure", "dr_alternate", "dr_detonate", "dr_close"];
static OPEN: AtomicBool = AtomicBool::new(false);
static SET_CURSOR_POS: AtomicUsize = AtomicUsize::new(0);
static CLIP_CURSOR: AtomicUsize = AtomicUsize::new(0);

unsafe extern "system" fn set_cursor_pos(x: i32, y: i32) -> BOOL {
    if OPEN.load(Ordering::Relaxed) {
        return BOOL(1);
    }
    let f: unsafe extern "system" fn(i32, i32) -> BOOL = unsafe { std::mem::transmute(SET_CURSOR_POS.load(Ordering::Relaxed)) };
    unsafe { f(x, y) }
}

unsafe extern "system" fn clip_cursor(rect: *const RECT) -> BOOL {
    if OPEN.load(Ordering::Relaxed) && !rect.is_null() {
        return BOOL(1);
    }
    let f: unsafe extern "system" fn(*const RECT) -> BOOL = unsafe { std::mem::transmute(CLIP_CURSOR.load(Ordering::Relaxed)) };
    unsafe { f(rect) }
}

/// 挂上两个光标函数的钩子（hudhook 已经初始化过 MinHook）；返回挂上了几个
fn hook_cursor() -> usize {
    let Ok(user32) = (unsafe { GetModuleHandleA(s!("user32.dll")) }) else { return 0 };
    let mut n = 0;
    for (name, detour, slot) in [
        (s!("SetCursorPos"), set_cursor_pos as *mut c_void, &SET_CURSOR_POS),
        (s!("ClipCursor"), clip_cursor as *mut c_void, &CLIP_CURSOR),
    ] {
        let Some(addr) = (unsafe { GetProcAddress(user32, name) }) else { continue };
        let addr = addr as *mut c_void;
        if let Ok(h) = unsafe { MhHook::new(addr, detour) } {
            slot.store(h.trampoline() as usize, Ordering::Relaxed);
            if unsafe { MH_EnableHook(addr) }.ok().is_ok() {
                n += 1;
            }
        }
    }
    n
}

// ------------------------------------------------------------------ 游戏的键鼠输入
// 游戏用 DirectInput8 读键鼠（不走窗口消息，hudhook 的消息过滤拦不住）：挂 IDirectInputDevice8 的 GetDeviceState / GetDeviceData，
// 窗口开着时鼠标读到的全是空（键盘只在搜索框里打字时清空）。设备类型用 GetCapabilities 问一次、按设备指针记住
static WANT_KB: AtomicBool = AtomicBool::new(false);
static DEV_STATE: [AtomicUsize; 2] = [AtomicUsize::new(0), AtomicUsize::new(0)];
static DEV_DATA: [AtomicUsize; 2] = [AtomicUsize::new(0), AtomicUsize::new(0)];
static DEV_TYPES: std::sync::Mutex<Vec<(usize, u8)>> = std::sync::Mutex::new(Vec::new());
const DI8DEVTYPE_MOUSE: u8 = 0x12;
const DI8DEVTYPE_KEYBOARD: u8 = 0x13;
const VT_RELEASE: usize = 2;
const VT_CREATE_DEVICE: usize = 3;
const VT_GET_CAPS: usize = 3;
const VT_GET_STATE: usize = 9;
const VT_GET_DATA: usize = 10;

unsafe fn vfn(obj: *mut c_void, k: usize) -> usize {
    unsafe { *(*(obj as *const *const usize)).add(k) }
}

/// 设备类型（DIDEVCAPS.dwDevType 的低字节），按设备指针记住
fn dev_type(this: *mut c_void) -> u8 {
    let mut g = DEV_TYPES.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(&(_, t)) = g.iter().find(|x| x.0 == this as usize) {
        return t;
    }
    let mut caps = [0u32; 11];
    caps[0] = 44;
    let f: unsafe extern "system" fn(*mut c_void, *mut u32) -> i32 = unsafe { std::mem::transmute(vfn(this, VT_GET_CAPS)) };
    let t = if unsafe { f(this, caps.as_mut_ptr()) } >= 0 { (caps[2] & 0xff) as u8 } else { 0 };
    if g.len() > 64 {
        g.clear();
    }
    g.push((this as usize, t));
    t
}

fn blocked(this: *mut c_void) -> bool {
    if !OPEN.load(Ordering::Relaxed) {
        return false;
    }
    match dev_type(this) {
        DI8DEVTYPE_MOUSE => true,
        DI8DEVTYPE_KEYBOARD => WANT_KB.load(Ordering::Relaxed),
        _ => false,
    }
}

unsafe extern "system" fn get_device_state<const K: usize>(this: *mut c_void, cb: u32, data: *mut c_void) -> i32 {
    let f: unsafe extern "system" fn(*mut c_void, u32, *mut c_void) -> i32 = unsafe { std::mem::transmute(DEV_STATE[K].load(Ordering::Relaxed)) };
    let hr = unsafe { f(this, cb, data) };
    if hr >= 0 && !data.is_null() && blocked(this) {
        unsafe { std::ptr::write_bytes(data as *mut u8, 0, cb as usize) };
    }
    hr
}

unsafe extern "system" fn get_device_data<const K: usize>(this: *mut c_void, cb: u32, rgdod: *mut c_void, inout: *mut u32, flags: u32) -> i32 {
    let f: unsafe extern "system" fn(*mut c_void, u32, *mut c_void, *mut u32, u32) -> i32 =
        unsafe { std::mem::transmute(DEV_DATA[K].load(Ordering::Relaxed)) };
    let hr = unsafe { f(this, cb, rgdod, inout, flags) };
    if hr >= 0 && !inout.is_null() && blocked(this) {
        unsafe { *inout = 0 }; // 事件照常从缓冲里取走（关窗口后不会一下子涌进来），只是告诉游戏「没有」
    }
    hr
}

/// 挂 DirectInput 设备的两个读取函数：自己建一个鼠标设备拿函数地址（A / W 两套接口各一次，地址一样的只挂一次）；返回挂上了几个
fn hook_dinput() -> usize {
    use hudhook::windows::core::GUID;
    const IID_W: GUID = GUID::from_u128(0xBF798031_483A_4DA2_AA99_5D64ED369700);
    const IID_A: GUID = GUID::from_u128(0xBF798030_483A_4DA2_AA99_5D64ED369700);
    const SYS_MOUSE: GUID = GUID::from_u128(0x6F1D2B60_D5A0_11CF_BFC7_444553540000);
    let Ok(dinput) = (unsafe { GetModuleHandleA(s!("dinput8.dll")) }) else { return 0 };
    let Some(create) = (unsafe { GetProcAddress(dinput, s!("DirectInput8Create")) }) else { return 0 };
    let create: unsafe extern "system" fn(*mut c_void, u32, *const GUID, *mut *mut c_void, *mut c_void) -> i32 = unsafe { std::mem::transmute(create) };
    let hinst = unsafe { GetModuleHandleA(None) }.map(|h| h.0).unwrap_or(std::ptr::null_mut());
    let mut done: Vec<usize> = Vec::new();
    let mut n = 0;
    for (k, iid) in [IID_W, IID_A].iter().enumerate() {
        let mut di: *mut c_void = std::ptr::null_mut();
        if unsafe { create(hinst, 0x0800, iid, &mut di, std::ptr::null_mut()) } < 0 || di.is_null() {
            continue;
        }
        let mut dev: *mut c_void = std::ptr::null_mut();
        let cd: unsafe extern "system" fn(*mut c_void, *const GUID, *mut *mut c_void, *mut c_void) -> i32 =
            unsafe { std::mem::transmute(vfn(di, VT_CREATE_DEVICE)) };
        if unsafe { cd(di, &SYS_MOUSE, &mut dev, std::ptr::null_mut()) } >= 0 && !dev.is_null() {
            let targets: [(usize, *mut c_void, &AtomicUsize); 2] = [
                (unsafe { vfn(dev, VT_GET_STATE) }, if k == 0 { get_device_state::<0> as *mut c_void } else { get_device_state::<1> as *mut c_void }, &DEV_STATE[k]),
                (unsafe { vfn(dev, VT_GET_DATA) }, if k == 0 { get_device_data::<0> as *mut c_void } else { get_device_data::<1> as *mut c_void }, &DEV_DATA[k]),
            ];
            for (addr, detour, slot) in targets {
                if done.contains(&addr) {
                    continue;
                }
                if let Ok(h) = unsafe { MhHook::new(addr as *mut c_void, detour) } {
                    slot.store(h.trampoline() as usize, Ordering::Relaxed);
                    if unsafe { MH_EnableHook(addr as *mut c_void) }.ok().is_ok() {
                        done.push(addr);
                        n += 1;
                    }
                }
            }
            let rel: unsafe extern "system" fn(*mut c_void) -> u32 = unsafe { std::mem::transmute(vfn(dev, VT_RELEASE)) };
            unsafe { rel(dev) };
        }
        let rel: unsafe extern "system" fn(*mut c_void) -> u32 = unsafe { std::mem::transmute(vfn(di, VT_RELEASE)) };
        unsafe { rel(di) };
    }
    n
}

/// 窗口开着：解除光标限制（用原来的 ClipCursor，不经过钩子）
fn free_cursor() {
    let p = CLIP_CURSOR.load(Ordering::Relaxed);
    if p != 0 {
        let f: unsafe extern "system" fn(*const RECT) -> BOOL = unsafe { std::mem::transmute(p) };
        let _ = unsafe { f(std::ptr::null()) };
    }
}

const RAR: [&str; 5] = ["普通", "稀有", "史诗", "传说", "传说（幽影之地）"];
const STATS: [&str; 5] = ["力气", "灵巧", "智力", "信仰", "感应"];
const STATUS: [&str; 7] = ["出血", "中毒", "腐败", "冻伤", "睡眠", "咒死", "发狂"];
/// 武器属性（devgive 的 属性=…；第一个 = 随机，不写）
const ELEMS: [&str; 11] = ["随机", "原版", "物理", "魔力", "火", "雷", "圣", "纯魔力", "纯火", "纯雷", "纯圣"];
const SLOTS: [&str; 4] = ["头", "身", "手", "腿"];
/// 发放窗口的类别（devgive 那一行开头的词）
const CATS: [&str; 4] = ["武器", "防具", "护符", "骨灰"];
const LIST_MAX: usize = 300;

struct WBase {
    id: u32,
    typ: u16,
    name: String,
}

struct PBase {
    id: u32,
    slot: u8,
    name: String,
}

struct Fam {
    key: String,
    name: String,
    armor: bool,
    slots: u8,
    /// 各稀有度有没有护符模板
    tal: [bool; 4],
    /// 传说那档的说明第一行
    text: String,
    /// 流派（fam 行第 10 个字段；旧的 affixes.txt 没有就是空的）
    arch: String,
    /// 变体组（同一件防具不放同组的两条）
    group: String,
    /// famw：[防具, 护符] × 各稀有度的权重（0 = 这个稀有度不出，停用的词条全是 0）
    w: [[u32; 4]; 2],
}

#[derive(Default)]
struct Data {
    wbase: Vec<WBase>,
    pbase: Vec<PBase>,
    fams: Vec<Fam>,
    skills: Vec<(i32, String)>,
    /// 武器常驻效果：(效果编号, 类：staff / seal / shield, 名字)
    wres: Vec<(i32, String, String)>,
    /// 武器的特殊效果词条位：(效果编号, 短名 / 说明)
    wspec: Vec<(i32, String)>,
    /// 叠标记的词条（runtime.txt 里带 target_mark 的规则）：(名字, 传说档每层挂给敌人的效果)
    marks: Vec<(String, Vec<i32>)>,
    /// 词条触发时一闪的特效（runtime.txt 里 FLASH_KEYS 那几个词条的规则，传说档）：(名字, 挂给敌人, 效果；多个 = 按消耗的层数)
    flashes: Vec<(String, bool, Vec<i32>)>,
    /// 流派（ARCH_ORDER 的顺序，后面是表里没有的）：(名字, 能出的词条数)
    archs: Vec<(String, usize)>,
    /// 一批最多发几件（items.txt 的 deliver 行，dark_core 一次请求最多放这么多进发货表）
    deliver: usize,
    /// 超限锻造石（武器, 防具）的道具编号（items.txt 的 overlimit 行；没开就没有）
    ovl_goods: Option<[u32; 2]>,
    /// 魇化的词条：(序号, 名字)（nightmare.txt 的 fam 行；没开就没有）
    nm_fams: Vec<(usize, String)>,
    /// 七咒：(区域序号, 诅咒名, 区域名)（curses.txt 的 region / text 行；没开就没有）
    curses: Vec<(usize, String, String)>,
    /// 无形的护符编号（unseen.txt 的 talisman 行）
    unseen_tal: Vec<i32>,
    /// 许愿石的道具编号（wishstone.txt 的 goods 行；没开就没有）
    ws_goods: Option<u32>,
    /// 事件脚本放的音效试听：(标记, 说明)（clash.txt 的 stest 行，rr/sounds.py；相杀用的那个带「相杀用」）
    stests: Vec<(u32, String)>,
    /// 骨灰（ashes.txt，rr/ashcont.py；没开骨灰稀有度就没有）：种类 (原版本体编号, 名字, 能强化到几级 + 1)、
    /// 机制前缀 (键, 名字, 说明)、数值词条 (键, 名字, 说明)
    ash_kinds: Vec<(u32, String, u32)>,
    ash_pres: Vec<(String, String, String)>,
    ash_affs: Vec<(String, String, String)>,
}

/// 流派列表的顺序（extract_affixes.py ARCHETYPES 的分类）
const ARCH_ORDER: [&str; 15] =
    ["姿态", "防御", "反击回血", "法术", "异常", "机动空战", "闪避", "战技", "命中连击", "重击处决", "远程", "属性", "生存", "杂项", "其他"];
/// 一键发放流派带的武器：每项是 devgive 一行「武器 档=N」后面的参数（一项一把）；类型编号见 affixes.txt 的 wbase 行
/// （1 匕首、3 直剑、5 大剑、7 特大剑、9 曲剑、13 武士刀、14 双头剑、15 刺剑、16 重刺剑、19 大斧、23 大槌、25 矛、35 拳、37 爪、41 特大武器、
///  50 短弓、51 长弓、53 大弓、55 弩、56 弩炮、57 法杖、61 圣印记、65 / 67 / 69 小 / 中 / 大盾、89 调香瓶、90 刺盾、91 投掷刀、92 反手剑、
///  93 轻大剑、94 大太刀、95 兽爪）；特效写 wspec 的键。表里没有的流派（属性、生存、杂项）给 KIT_WEAPONS_OTHER
const KIT_WEAPONS: [(&str, &[&str]); 11] = [
    ("姿态", &["类型=5", "类型=7", "类型=13", "类型=94", "类型=93"]),
    ("防御", &["类型=65", "类型=67", "类型=69", "类型=90", "类型=3 特效=dr_poise_guard"]),
    ("反击回血", &["类型=3 特效=bloodrage", "类型=9 特效=dr_thirst 异常=出血"]),
    ("法术", &["类型=57", "类型=57", "类型=61", "类型=61"]),
    ("异常", &["类型=13 异常=出血,冻伤 特效=dr_shatter", "类型=1 异常=中毒,腐败 特效=dr_plague", "类型=15 异常=睡眠 特效=dr_awaken", "类型=9 特效=dr_charge"]),
    ("机动空战", &["类型=7", "类型=41", "类型=23", "类型=25"]),
    ("闪避", &["类型=1", "类型=13", "类型=92", "类型=9"]),
    ("战技", &["类型=3", "类型=5", "类型=13"]),
    ("命中连击", &["类型=1 特效=dr_giant", "类型=14 强攻=20", "类型=37", "类型=35", "类型=95"]),
    ("重击处决", &["类型=7", "类型=41", "类型=23", "类型=19", "类型=16"]),
    ("远程", &["类型=50", "类型=51", "类型=53", "类型=55", "类型=56", "类型=89", "类型=91"]),
];
const KIT_WEAPONS_OTHER: &[&str] = &["类型=3", "类型=5"];

/// 一个流派的整套（一行一件）和说明
struct Kit {
    lines: Vec<String>,
    summary: String,
}

/// 这个档能出的、这个流派的词条：每条一件护符（有护符模板的）；能上防具的按部位塞进防具（能放的部位少的先放，每件最多 3 条、
/// 同一变体组不放一起，放不下就新开一件，开在能放的部位里件数最少的）；再加 KIT_WEAPONS 的武器（词条库里没有这种武器就跳过）
fn kit(d: &Data, arch: &str, tier: usize) -> Kit {
    let r = tier.min(3);
    let fams: Vec<usize> = (0..d.fams.len()).filter(|&k| d.fams[k].arch == arch && (d.fams[k].w[0][r] > 0 || d.fams[k].w[1][r] > 0)).collect();
    let mut lines = Vec::new();
    let mut n_tal = 0;
    for &k in &fams {
        let f = &d.fams[k];
        if f.tal[r] && f.w[1][r] > 0 {
            lines.push(format!("护符 档={tier} 词条={}", f.key));
            n_tal += 1;
        }
    }
    let mut armor: Vec<usize> = fams.iter().copied().filter(|&k| d.fams[k].w[0][r] > 0 && d.fams[k].slots & 15 != 0).collect();
    armor.sort_by_key(|&k| (d.fams[k].slots & 15).count_ones());
    let mut pieces: Vec<(usize, Vec<usize>)> = Vec::new();
    for &k in &armor {
        let f = &d.fams[k];
        let fits = |p: &(usize, Vec<usize>)| {
            f.slots & (1 << p.0) != 0 && p.1.len() < 3 && (f.group.is_empty() || p.1.iter().all(|&j| d.fams[j].group != f.group))
        };
        if let Some(p) = pieces.iter_mut().find(|p| fits(p)) {
            p.1.push(k);
            continue;
        }
        let slot = (0..4).filter(|s| f.slots & (1 << s) != 0).min_by_key(|&s| pieces.iter().filter(|p| p.0 == s).count()).unwrap_or(0);
        pieces.push((slot, vec![k]));
    }
    for (s, ks) in &pieces {
        let keys: Vec<&str> = ks.iter().map(|&k| d.fams[k].key.as_str()).collect();
        lines.push(format!("防具 档={tier} 部位={} 词条={}", SLOTS[*s], keys.join(",")));
    }
    let specs = KIT_WEAPONS.iter().find(|(a, _)| *a == arch).map_or(KIT_WEAPONS_OTHER, |x| x.1);
    let (mut n_w, mut skip) = (0, Vec::new());
    for s in specs {
        let typ = s.split_whitespace().find_map(|x| x.strip_prefix("类型=")).and_then(|x| x.parse::<u16>().ok());
        if typ.is_some_and(|t| !d.wbase.iter().any(|b| b.typ == t)) {
            skip.push(*s);
            continue;
        }
        lines.push(format!("武器 档={tier} {s}"));
        n_w += 1;
    }
    let names: Vec<&str> = fams.iter().map(|&k| d.fams[k].name.split(" / ").next().unwrap_or("")).collect();
    let batches = lines.len().div_ceil(d.deliver.max(1));
    let summary = format!(
        "{} 条词条：{}\n护符 {n_tal} 件、防具 {} 件（{} 条能上防具的都放进去了）、武器 {n_w} 件；共 {} 件，分 {batches} 批发{}",
        fams.len(),
        names.join("、"),
        pieces.len(),
        armor.len(),
        lines.len(),
        if skip.is_empty() { String::new() } else { format!("\n（词条库里没有这些武器，跳过：{}）", skip.join("；")) }
    );
    Kit { lines, summary }
}

fn unesc(s: &str) -> String {
    s.replace("\\n", " ").replace("\\t", " ").replace("\\\\", "\\")
}

/// 测试骨灰的道具编号（同重随 rr/ashtest.py 的 GOODS）
const ASH_TEST: i32 = 299900;
/// 骨灰稀有度测试发的原版骨灰：离群野狼（3 只）、“黑刀”狄希（1 只）、仿身泪滴（集结多一个仿身）、亚人集团（原版 5 只，集结变 6 只）、咒剑士米拉（DLC）
const ASH_SAMPLES: [(&str, i32); 5] = [("离群野狼", 232000), ("狄希", 200000), ("仿身泪滴", 207000), ("亚人集团", 234000), ("米拉（DLC）", 2200000)];
const ASH_MORE: [i32; 5] = [201000, 202000, 203000, 2201000, 2205000];

fn core_dir() -> PathBuf {
    hudhook::util::get_dll_path()
        .and_then(|p| p.parent().and_then(|d| d.parent()).map(|d| d.join("dark_core")))
        .unwrap_or_else(|| PathBuf::from("dark_core"))
}

fn load() -> Result<Data, String> {
    load_from(&core_dir())
}

/// 读 dir 里的 affixes.txt、items.txt、runtime.txt（dark_core 的定义文件，重随生成）
fn load_from(dir: &Path) -> Result<Data, String> {
    let path = dir.join("affixes.txt");
    let text = fs::read_to_string(&path).map_err(|e| format!("读不了 {}：{e}（先启动一次让重随生成）", path.display()))?;
    let mut d = Data::default();
    for line in text.lines() {
        let f: Vec<&str> = line.split('\t').collect();
        let n = f.len();
        match f[0] {
            "wbase" if n >= 7 => d.wbase.push(WBase {
                id: f[2].parse().unwrap_or(0),
                typ: f[1].parse().unwrap_or(0),
                name: format!("{} / {}", unesc(f[5]), unesc(f[6])),
            }),
            "pbase" if n >= 5 => d.pbase.push(PBase { id: f[2].parse().unwrap_or(0), slot: f[1].parse().unwrap_or(0), name: format!("{} / {}", unesc(f[3]), unesc(f[4])) }),
            "fam" if n >= 7 => d.fams.push(Fam {
                key: f[6].to_string(),
                name: format!("{} / {}", unesc(f[4]), unesc(f[5])),
                armor: f[2].parse::<u32>().unwrap_or(0) > 0,
                slots: f.get(7).and_then(|x| x.parse().ok()).unwrap_or(15),
                tal: [false; 4],
                text: String::new(),
                arch: f.get(10).map_or(String::new(), |x| unesc(x)),
                group: f.get(9).filter(|x| **x != "-").map_or(String::new(), |x| x.to_string()),
                w: [[0; 4]; 2],
            }),
            "famw" if n >= 4 => {
                if let Some(fam) = f[1].parse::<usize>().ok().and_then(|k| d.fams.get_mut(k)) {
                    for (p, list) in [f[2], f[3]].iter().enumerate() {
                        for (r, x) in list.split(',').take(4).enumerate() {
                            fam.w[p][r] = x.parse().unwrap_or(0);
                        }
                    }
                }
            }
            "famr" if n >= 7 => {
                if let (Ok(k), Ok(r)) = (f[1].parse::<usize>(), f[2].parse::<usize>()) {
                    if let Some(fam) = d.fams.get_mut(k).filter(|_| r < 4) {
                        fam.tal[r] = f[4].parse::<i32>().unwrap_or(-1) >= 0;
                        if r == 3 || fam.text.is_empty() {
                            fam.text = unesc(f[5]).chars().take(60).collect();
                        }
                    }
                }
            }
            "skillinfo" if n >= 6 => d.skills.push((f[1].parse().unwrap_or(0), format!("{} / {}", unesc(f[4]), unesc(f[5])))),
            "wres" if n >= 6 => d.wres.push((f[2].parse().unwrap_or(0), f[1].to_string(), unesc(f[4]))),
            "wspec" if n >= 9 => d.wspec.push((f[2].parse().unwrap_or(0), format!("{}  {}", unesc(f[5]), unesc(f[7])))),
            _ => {}
        }
    }
    if d.wbase.is_empty() || d.fams.is_empty() {
        return Err(format!("{} 里没有本体 / 词条", path.display()));
    }
    d.skills.sort_by(|a, b| a.1.cmp(&b.1));
    // 流派：能出的词条（哪个稀有度有权重就算）按流派数
    let mut archs: Vec<(String, usize)> = Vec::new();
    for f in d.fams.iter().filter(|f| !f.arch.is_empty() && f.w.iter().flatten().any(|&x| x > 0)) {
        match archs.iter_mut().find(|a| a.0 == f.arch) {
            Some(a) => a.1 += 1,
            None => archs.push((f.arch.clone(), 1)),
        }
    }
    archs.sort_by_key(|a| ARCH_ORDER.iter().position(|x| *x == a.0).unwrap_or(ARCH_ORDER.len()));
    d.archs = archs;
    d.deliver = fs::read_to_string(dir.join("items.txt"))
        .unwrap_or_default()
        .lines()
        .find_map(|l| l.strip_prefix("deliver\t").and_then(|x| x.split('\t').nth(1)).and_then(|x| x.parse().ok()))
        .unwrap_or(32);
    d.ovl_goods = fs::read_to_string(dir.join("items.txt")).unwrap_or_default().lines().find_map(|l| {
        let f: Vec<&str> = l.split('\t').collect();
        (f.len() >= 3 && f[0] == "overlimit").then(|| Some([f[1].parse().ok()?, f[2].parse().ok()?])).flatten()
    });
    d.ws_goods = fs::read_to_string(dir.join("wishstone.txt")).unwrap_or_default().lines()
        .find_map(|l| l.trim().strip_prefix("goods ").and_then(|x| x.trim().parse().ok()));
    {
        let text = fs::read_to_string(dir.join("clash.txt")).unwrap_or_default();
        let sound = text.lines().find_map(|l| l.trim().strip_prefix("sound ").and_then(|x| x.trim().parse::<u32>().ok()));
        let usound = text.lines().find_map(|l| l.trim().strip_prefix("usound ").and_then(|x| x.trim().parse::<u32>().ok()));
        for line in text.lines() {
            let f: Vec<&str> = line.split_whitespace().collect();
            if f.len() >= 4 && f[0] == "stest" {
                if let Ok(flag) = f[1].parse::<u32>() {
                    let tag = if Some(flag) == sound { "（相杀用）" } else if Some(flag) == usound { "（工坊现在用的）" } else { "" };
                    d.stests.push((flag, format!("{} {}{} {}", f[2], f[3], tag, f[4..].join(" "))));
                }
            }
        }
    }
    d.unseen_tal = fs::read_to_string(dir.join("unseen.txt")).unwrap_or_default().lines()
        .find_map(|l| l.trim().strip_prefix("talisman ").map(|x| x.split_whitespace().filter_map(|t| t.parse().ok()).collect()))
        .unwrap_or_default();
    // 骨灰：kind / pre / aff 行；数值词条的名字在词条百科的 ashcx 行（键 ash_<键>）
    {
        let text = fs::read_to_string(dir.join("ashes.txt")).unwrap_or_default();
        let rows: Vec<Vec<&str>> = text.lines().map(|l| l.split('\t').collect()).collect();
        let cx = |key: &str| rows.iter().find(|f| f.len() >= 4 && f[0] == "ashcx" && f[1] == format!("ash_{key}")).map(|f| unesc(f[2]));
        for f in &rows {
            match f[0] {
                "kind" if f.len() >= 6 => d.ash_kinds.push((f[1].parse().unwrap_or(0), unesc(f[5]), f[2].parse().unwrap_or(1))),
                "pre" if f.len() >= 10 => d.ash_pres.push((f[1].to_string(), unesc(f[6]), unesc(f[8]))),
                "aff" if f.len() >= 6 => d.ash_affs.push((f[1].to_string(), cx(f[1]).unwrap_or_else(|| f[1].to_string()), unesc(f[4]))),
                _ => {}
            }
        }
    }
    for line in fs::read_to_string(dir.join("nightmare.txt")).unwrap_or_default().lines() {
        let f: Vec<&str> = line.split_whitespace().collect();
        if f.len() >= 4 && f[0] == "fam" {
            if let Ok(k) = f[1].parse::<usize>() {
                let name = d.fams.iter().find(|m| m.key == f[2]).map_or(f[2].to_string(), |m| m.name.clone());
                d.nm_fams.push((k, name));
            }
        }
    }
    let ct = fs::read_to_string(dir.join("curses.txt")).unwrap_or_default();
    let names: std::collections::HashMap<&str, &str> = ct.lines().filter_map(|l| {
        let f: Vec<&str> = l.split('\t').collect();
        (f.len() >= 3 && f[0] == "text").then(|| (f[1], f[2]))
    }).collect();
    for l in ct.lines() {
        let f: Vec<&str> = l.split('\t').collect();
        if f.len() >= 5 && f[0] == "region" {
            if let Ok(k) = f[1].parse::<usize>() {
                d.curses.push((k, names.get(f[2]).unwrap_or(&f[2]).to_string(), f[4].to_string()));
            }
        }
    }
    // 效果调试：叠标记的词条每层的效果（runtime.txt，重随生成；读不到就不显示这几个按钮）
    for line in fs::read_to_string(dir.join("runtime.txt")).unwrap_or_default().lines() {
        let f: Vec<&str> = line.split('\t').collect();
        if f.len() < 4 || f[0] != "rule" || !f.iter().any(|x| x.starts_with("target_mark=")) {
            continue;
        }
        let Some(ids) = f.iter().find_map(|x| x.strip_prefix("mfx3=")) else { continue };
        let name = d.fams.iter().find(|m| m.key == f[1]).map_or(f[1].to_string(), |m| m.name.clone());
        d.marks.push((name, ids.split(',').filter_map(|x| x.parse().ok()).collect()));
    }
    // 词条触发时一闪的特效（用户 2026-11-13）：传说档的效果行 —— on 规则的 effect（最后一档）、叠层的 fx3、消耗猎印的 tfx3（挂给敌人，按层数）
    for line in fs::read_to_string(dir.join("runtime.txt")).unwrap_or_default().lines() {
        let f: Vec<&str> = line.split('\t').collect();
        if f.len() < 4 || f[0] != "rule" || !FLASH_KEYS.contains(&f[1]) {
            continue;
        }
        let ids = |p: &str| -> Vec<i32> {
            f.iter().find_map(|x| x.strip_prefix(p)).map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.parse().ok()).filter(|&x: &i32| x > 0).collect())
        };
        let name = d.fams.iter().find(|m| m.key == f[1]).map_or(f[1].to_string(), |m| m.name.clone());
        let (enemy, got) = match (ids("tfx3="), ids("fx3="), ids("effect=")) {
            (t, _, _) if !t.is_empty() => (true, t),
            (_, x, _) if !x.is_empty() => (false, x),
            (_, _, e) => (false, e.last().copied().into_iter().collect()),
        };
        // 交替两条规则：投掷 / 调香后（箭增伤）、射箭命中后（道具增伤）
        let how = match f.iter().find_map(|x| x.strip_prefix("add=")) {
            Some(a) if a.contains("shot_hit") => "（射箭命中后）",
            Some(_) => "（投掷 / 调香后）",
            None => "",
        };
        if !got.is_empty() {
            d.flashes.push((format!("{name}{how}"), enemy, got));
        }
    }
    Ok(d)
}

/// 帧耗时统计：dark_core 的导出（dll\\dark_core 的 prof.rs）；没加载、版本太老就 None
#[derive(Clone, Copy)]
struct ProfApi {
    set: unsafe extern "C" fn(u32),
    get: unsafe extern "C" fn(*mut u8, usize) -> usize,
}

fn prof_api() -> Option<ProfApi> {
    let m = unsafe { GetModuleHandleA(s!("dark_core.dll")) }.ok()?;
    unsafe {
        Some(ProfApi {
            set: std::mem::transmute(GetProcAddress(m, s!("dr_prof_set"))?),
            get: std::mem::transmute(GetProcAddress(m, s!("dr_prof_get"))?),
        })
    }
}

struct App {
    prof_on: bool,
    prof_text: String,
    prof_at: Option<Instant>,
    open: bool,
    data: Option<Data>,
    err: String,
    cat: usize,
    tier: usize,
    count: i32,
    // 武器
    wfilter: String,
    wbase: Option<usize>,
    scal_mode: usize,
    n_idx: usize,
    cor_on: [bool; 5],
    cor: [i32; 5],
    status_mode: usize,
    status: [bool; 7],
    sfilter: String,
    skill: Option<i32>,
    /// 常驻效果：0 随机 / 1 不带 / 2 指定（最多 2 个）
    res_mode: usize,
    res: Vec<i32>,
    rfilter: String,
    /// 特效：0 随机 / 1 不带 / 2 指定
    spec_mode: usize,
    spec: Option<i32>,
    /// 属性：ELEMS 的序号（0 随机）；物理＋元素时的元素占比（0 = 随机）
    elem: usize,
    elem_pct: i32,
    // 防具 / 护符
    pfilter: String,
    pbase: Option<usize>,
    slot: usize,
    ffilter: String,
    pfams: Vec<usize>,
    tfam: Option<usize>,
    // 骨灰（发放窗口的第四类）：本体、强化等级、前缀（随机 / 不带 / 指定）、数值词条、集结（随机 / 带 / 不带）
    abase: Option<usize>,
    afilter: String,
    alv: i32,
    apre_mode: usize,
    apre: Option<usize>,
    aaffs: Vec<usize>,
    arally: usize,
    // 效果调试
    sp_id: i32,
    /// 相杀音效试听：自己填的音效编号、放在持续特效那格（否则起手那格）
    se_id: i32,
    se_midst: bool,
    // 一键发放流派：选的流派（archs 的下标）、排队的行（一行一件）、上次看请求文件的时间
    kit_arch: usize,
    queue: Vec<String>,
    queue_at: Instant,
    // 结果
    last: String,
    log_tail: Vec<String>,
    log_at: Instant,
    /// 光标钩子挂上了几个（2 = 都挂上了）
    cursor_hooks: usize,
    /// DirectInput 读取函数的钩子挂上了几个（至少 2 个）
    input_hooks: usize,
}

impl App {
    fn new() -> Self {
        App {
            prof_on: false,
            prof_text: String::new(),
            prof_at: None,
            open: false,
            data: None,
            err: String::new(),
            cat: 0,
            tier: 3,
            count: 1,
            wfilter: String::new(),
            wbase: None,
            scal_mode: 0,
            n_idx: 1,
            cor_on: [true, true, false, false, false],
            cor: [120, 80, 100, 100, 100],
            status_mode: 0,
            status: [false; 7],
            sfilter: String::new(),
            skill: None,
            res_mode: 0,
            res: Vec::new(),
            rfilter: String::new(),
            spec_mode: 0,
            spec: None,
            elem: 0,
            elem_pct: 0,
            pfilter: String::new(),
            pbase: None,
            slot: 0,
            ffilter: String::new(),
            pfams: Vec::new(),
            tfam: None,
            abase: None,
            afilter: String::new(),
            alv: 0,
            apre_mode: 0,
            apre: None,
            aaffs: Vec::new(),
            arally: 0,
            sp_id: 1709000,
            se_id: 440550,
            se_midst: true,
            kit_arch: 0,
            queue: Vec::new(),
            queue_at: Instant::now(),
            last: String::new(),
            log_tail: Vec::new(),
            log_at: Instant::now(),
            cursor_hooks: 0,
            input_hooks: 0,
        }
    }

    /// 这一件写成 devgive 的一行
    fn line(&self, d: &Data) -> String {
        let mut s = format!("{} 档={} 件数={}", CATS[self.cat.min(3)], self.tier, self.count.clamp(1, 32));
        match self.cat {
            0 => {
                if let Some(i) = self.wbase {
                    s += &format!(" 本体={}", d.wbase[i].id);
                }
                match self.scal_mode {
                    1 => s += &format!(" 项数={}", [1, 2, 3, 5][self.n_idx]),
                    2 => {
                        let parts: Vec<String> = (0..5).filter(|&k| self.cor_on[k]).map(|k| format!("{}:{}", STATS[k], self.cor[k])).collect();
                        if !parts.is_empty() {
                            s += &format!(" 补正={}", parts.join(","));
                        }
                    }
                    _ => {}
                }
                match self.status_mode {
                    1 => s += " 异常=无",
                    2 => {
                        let v: Vec<&str> = (0..7).filter(|&k| self.status[k]).map(|k| STATUS[k]).take(3).collect();
                        s += &format!(" 异常={}", if v.is_empty() { "无".to_string() } else { v.join(",") });
                    }
                    _ => {}
                }
                if let Some(id) = self.skill {
                    s += &format!(" 战技={id}");
                }
                match self.res_mode {
                    1 => s += " 常驻=无",
                    2 if !self.res.is_empty() => {
                        s += &format!(" 常驻={}", self.res.iter().map(|x| x.to_string()).collect::<Vec<_>>().join(","))
                    }
                    _ => {}
                }
                match (self.spec_mode, self.spec) {
                    (1, _) => s += " 特效=无",
                    (2, Some(sp)) => s += &format!(" 特效={sp}"),
                    _ => {}
                }
                match self.elem {
                    0 => {}
                    3..=6 if self.elem_pct > 0 => s += &format!(" 属性={}:{}", ELEMS[self.elem], self.elem_pct),
                    k => s += &format!(" 属性={}", ELEMS[k]),
                }
            }
            1 => {
                match (self.pbase, self.slot) {
                    (Some(i), _) => s += &format!(" 本体={}", d.pbase[i].id),
                    (None, k) if k > 0 => s += &format!(" 部位={}", SLOTS[k - 1]),
                    _ => {}
                }
                if !self.pfams.is_empty() {
                    s += &format!(" 词条={}", self.pfams.iter().map(|&k| d.fams[k].key.as_str()).collect::<Vec<_>>().join(","));
                }
            }
            2 => {
                if let Some(k) = self.tfam {
                    s += &format!(" 词条={}", d.fams[k].key);
                }
            }
            _ => {
                if let Some(i) = self.abase {
                    s += &format!(" 本体={}", d.ash_kinds[i].0);
                }
                s += &format!(" 等级={}", self.alv.clamp(0, 10));
                match (self.apre_mode, self.apre) {
                    (1, _) => s += " 前缀=无",
                    (2, Some(i)) => s += &format!(" 前缀={}", d.ash_pres[i].0),
                    _ => {}
                }
                if !self.aaffs.is_empty() {
                    s += &format!(" 词条={}", self.aaffs.iter().map(|&k| d.ash_affs[k].0.as_str()).collect::<Vec<_>>().join(","));
                }
                match self.arally {
                    1 => s += " 集结=有",
                    2 => s += " 集结=无",
                    _ => {}
                }
            }
        }
        s
    }

    fn send(&mut self, line: String) {
        let path = core_dir().join("devgive_req.txt");
        let text = format!("# dark_dev 悬浮窗口写的请求，dark_core 发完会删掉\n{line}\n");
        self.last = match fs::write(&path, text) {
            Ok(()) => format!("已发出请求：{line}"),
            Err(e) => format!("写不了 {}：{e}", path.display()),
        };
    }

    /// 效果调试：写 devsp_req.txt（一行「我 / 敌 + 效果编号」），dark_core 看到就挂、删掉
    fn send_sp(&mut self, who: &str, sp: i32) {
        self.send_line(&format!("{who} {sp}"));
    }

    fn send_line(&mut self, line: &str) {
        let path = core_dir().join("devsp_req.txt");
        self.last = match fs::write(&path, format!("{line}\n")) {
            Ok(()) => format!("已发出请求：{line}"),
            Err(e) => format!("写不了 {}：{e}", path.display()),
        };
    }

    /// 唤声船：写 boat_req.txt（一行一个：战灰 / 碎片 / 击杀 / 重置），dark_core 的 boat 模块看到就做、删掉
    fn send_boat(&mut self, line: &str) {
        let path = core_dir().join("boat_req.txt");
        self.last = match fs::write(&path, format!("{line}\n")) {
            Ok(()) => format!("已发出请求：唤声船 {line}"),
            Err(e) => format!("写不了 {}：{e}", path.display()),
        };
    }

    /// 相杀火花测试：写 clashfx_req.txt（一行「fx 特效 挂点 类型 持续|起手」或「fx 恢复」）
    fn clashfx_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("相杀火花测试（换几种写法马上挂给自己）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        // (按钮, 请求)：特效 990040 = 我们放大的防御火花，201001 = 原版防御火花；挂点 10300 = 右手武器刀根（护手），220 = 身体中间
        // 2026-11-04 实测：挂在武器上（类型 1 / 2）的都不显示，挂在身上的都正常 → 火花改挂人物的点位 1（右手）/ 2（左手）
        const FX: [(&str, &str); 7] = [
            ("1 现在的设定：我们的火花，右手（点位 1）", "fx 990040 1 0 持续"),
            ("2 我们的火花，左手（点位 2）", "fx 990040 2 0 持续"),
            ("3 我们的火花，身体中间（点位 220）", "fx 990040 220 0 持续"),
            ("4 原版防御火花 201001，右手（点位 1）", "fx 201001 1 0 持续"),
            ("5 我们的火花，右手（起手特效）", "fx 990040 1 0 起手"),
            ("6 对照：猎印准星 990001，身体中间", "fx 990001 220 0 持续"),
            ("恢复原来的设定", "fx 恢复"),
        ];
        for (name, line) in FX {
            if ui.button(name) {
                let path = core_dir().join("clashfx_req.txt");
                self.last = match fs::write(&path, format!("{line}\n")) {
                    Ok(()) => format!("已发出请求：相杀火花测试 {line}"),
                    Err(e) => format!("写不了 {}：{e}", path.display()),
                };
            }
        }
        ui.text_wrapped(concat!("每点一个就把火花效果的光效行改成那样（只在内存里，重开游戏恢复）、马上给自己挂上 1.2 秒，看手上 / 身上有没有出特效。",
                                "6 是对照：它要是也看不到，就是测试的挂法本身有问题。结果写进 dark_core.log，搜「相杀火花测试」。"));
        // 音效试听（用户 2026-11-04「相杀的音效还没做」）：音效放进火花特效的那一格（第一版放在没有特效的起手那格，一个都不响）
        ui.text("相杀音效试听（音效和火花一起放）");
        // 都是 sfx 类、在常驻音效库 cs_main 里确定存在的编号（解开游戏的 sd.bhd 对过），取自这些原版战技动作里放的音效
        const SE: [(&str, i32); 8] = [
            ("A 440550 黄金格挡", 440550),
            ("B 440551 黄金格挡（第二声）", 440551),
            ("C 440210 盾牌冲击 / 突进冲击", 440210),
            ("D 440001 铁壁盾防 / 决心", 440001),
            ("E 440510 托普斯的力场", 440510),
            ("F 450440 黄金式奉还", 450440),
            ("G 440470 坠落震击", 440470),
            ("H 440110 忍耐", 440110),
        ];
        let mut send = None;
        for (k, (name, id)) in SE.iter().enumerate() {
            if k % 2 == 1 {
                ui.same_line();
            }
            if ui.button(name) {
                send = Some(*id);
            }
        }
        ui.set_next_item_width(160.0);
        ui.input_int("音效编号##clashse", &mut self.se_id).build();
        ui.same_line();
        if ui.button("试听这个编号") {
            send = Some(self.se_id);
        }
        ui.same_line();
        if ui.button("去掉音效") {
            send = Some(-1);
        }
        ui.radio_button("放在持续特效那格", &mut self.se_midst, true);
        ui.same_line();
        ui.radio_button("放在起手特效那格（多放一份火花）", &mut self.se_midst, false);
        if let Some(id) = send {
            let line = format!("se {id} {}", if self.se_midst { "持续" } else { "起手" });
            let path = core_dir().join("clashfx_req.txt");
            self.last = match fs::write(&path, format!("{line}\n")) {
                Ok(()) => format!("已发出请求：相杀音效试听 {line}"),
                Err(e) => format!("写不了 {}：{e}", path.display()),
            };
        }
        // 对照：原版忍耐的效果（光效行 8570 = 持续特效 440111 + 持续音效 440111，同一格），听得到它就说明光效行的音效这条路是通的
        if ui.button("对照：给自己挂原版「忍耐」的效果 1650（光效自带音效）") {
            self.send_sp("我", 1650);
        }
        ui.text_wrapped(concat!("先点「对照」：听得到声音，再一个个试 A~H（每点一下火花和音效一起放一次）；两种放法都试试。",
                                "「恢复原来的设定」也会把音效改回去。挑好了告诉我字母或编号。"));
        // 事件脚本放的音效（人物类也能放，rr/sounds.py；用户 2026-11-04：原版防御反击那一声是人物类，光效行放不了）
        ui.text("事件脚本放音效（人物类也能放；只有声音，没有火花）");
        if d.stests.is_empty() {
            ui.text_wrapped("clash.txt 里没有试听候选（还没重随，或者没开新装备系统）");
        }
        for (k, (flag, desc)) in d.stests.iter().enumerate() {
            if k % 2 == 1 {
                ui.same_line();
            }
            if ui.button(format!("{desc}##snd{flag}")) {
                let line = format!("snd {flag}");
                let path = core_dir().join("clashfx_req.txt");
                self.last = match fs::write(&path, format!("{line}\n")) {
                    Ok(()) => format!("已发出请求：相杀音效试听 {line}（{desc}）"),
                    Err(e) => format!("写不了 {}：{e}", path.display()),
                };
            }
        }
        ui.separator();
    }

    /// 法球发射点测试（用户 2026-11-05「改成从原版法杖的发射点位发射」）：dark_core orbshot.rs 直接调游戏生成子弹的函数，
    /// 从给的点位射一颗最低档的法球，看从哪里出来（右手拿法杖时 101xx = 右手武器上的点位）
    fn orbshot_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("法球发射点测试（从法杖哪个点位射出）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        const DMY: [(&str, i32); 9] = [
            ("10100 右手武器 100 号点（原版辉剑圆阵等战技从这出）", 10100),
            ("10110 右手武器 110 号点", 10110),
            ("10130 右手武器 130 号点", 10130),
            ("10101 右手武器 101 号点", 10101),
            ("10300 右手武器 300 号点（刀根）", 10300),
            ("20100 左手武器 100 号点", 20100),
            ("1 右手", 1),
            ("220 身体中间", 220),
            ("-1 不指定点位", -1),
        ];
        for (name, dmy) in DMY {
            if ui.button(format!("{name}##orbshot{dmy}")) {
                let path = core_dir().join("orbshot_req.txt");
                self.last = match fs::write(&path, format!("shot {dmy}\n")) {
                    Ok(()) => format!("已发出请求：法球发射点测试 shot {dmy}"),
                    Err(e) => format!("写不了 {}：{e}", path.display()),
                };
            }
        }
        ui.text_wrapped(concat!("右手拿法杖（或圣印记）站着点一个，看那颗法球从哪里飞出来（最低一档的伤害，会追最近的敌人）。",
                                "游戏直接生成子弹，第一次点之前先存好档。结果写进 dark_core.log，搜「法球发射点」。"));
        ui.separator();
    }

    fn boat_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("战灰「唤声船」", imgui::TreeNodeFlags::empty()) {
            return;
        }
        if ui.button("直接拿战灰") {
            self.send_boat("战灰");
        }
        ui.same_line();
        if ui.button("直接拿碎片") {
            self.send_boat("碎片");
        }
        if ui.button("当作击败了一只唤声船") {
            self.send_boat("击杀");
        }
        ui.same_line();
        if ui.button("重置获取进度（熄灭标记、收走碎片）") {
            self.send_boat("重置");
        }
        ui.separator();
    }

    /// 高难度测试区：发超限锻造石、查看最近的敌人血量（血量补正挂没挂上、上限对不对）
    fn hard_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("高难度测试（超限锻造石、许愿石、血量补正）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        match d.ovl_goods {
            Some([w, a]) => {
                for (name, g) in [("超限锻造石（武器）", w), ("超限锻造石（防具）", a)] {
                    ui.text(name);
                    for n in [1, 10, 50] {
                        ui.same_line();
                        if ui.button(format!("×{n}##ovl{g}_{n}")) {
                            self.send(format!("道具 {g} {n}"));
                        }
                    }
                }
            }
            None => ui.text_wrapped("items.txt 里没有 overlimit 行（没开超限锻造石，或者还没重随）"),
        }
        match d.ws_goods {
            Some(g) => {
                ui.text("许愿石");
                for n in [1, 10, 50] {
                    ui.same_line();
                    if ui.button(format!("×{n}##ws{n}")) {
                        self.send(format!("道具 {g} {n}"));
                    }
                }
                ui.same_line();
                ui.text("（赐福「暗黑重铸」→「许愿石升级」，只在死亡 / 不可能列出来）");
            }
            None => ui.text_wrapped("没有 wishstone.txt（没开许愿石、没有高难度档，或者还没重随）"),
        }
        if ui.button("查看最近的敌人（血量、上限、身上的效果，写进日志）##hard") {
            self.send_line("查 敌");
        }
        ui.text_wrapped("血量补正只在难度「死亡」「不可能」里挂（效果 7302000 起）；dark_core.log 里搜「高难度血量补正」「超限锻造石掉落」。");
        ui.separator();
    }

    /// 魇化测试：写 nightmare_req.txt（一行一条），dark_core 的 nightmare 模块看到就做、删掉
    fn send_nm(&mut self, line: &str) {
        let path = core_dir().join("nightmare_req.txt");
        self.last = match fs::write(&path, format!("{line}\n")) {
            Ok(()) => format!("已发出请求：魇化 {line}"),
            Err(e) => format!("写不了 {}：{e}", path.display()),
        };
    }

    fn nightmare_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("魇化测试（精英、魇火、魇印）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        if d.nm_fams.is_empty() {
            ui.text_wrapped("nightmare.txt 里没有词条（没开魇化，或者还没重随）");
            ui.separator();
            return;
        }
        if ui.button("让 15 米内最近的敌人魇化") {
            self.send_nm("魇化最近");
        }
        ui.same_line();
        if ui.button("清空魇火") {
            self.send_nm("清空魇火");
        }
        if ui.button("夺取一次（随机词条）") {
            self.send_nm("夺取 随机");
        }
        ui.text("夺取一次：");
        for (i, (k, name)) in d.nm_fams.iter().enumerate() {
            if i % 5 != 0 {
                ui.same_line();
            }
            if ui.button(format!("{name}##nm{k}")) {
                self.send_nm(&format!("夺取 {k}"));
            }
        }
        ui.text("全部词条的夺取次数设成：");
        for n in [0, 1, 5, 15, 30] {
            ui.same_line();
            if ui.button(format!("{n}##nmc{n}")) {
                self.send_nm(&format!("次数 全部 {n}"));
            }
        }
        ui.text_wrapped("魇火这一档的稀有度（死亡稀有、不可能史诗；不在这两档按稀有）；结果看 dark_core.log 里「魇化」开头的行，刻印在赐福「暗黑重铸」→「魇印」。");
        ui.separator();
    }

    /// 斗技场试炼测试：写 arena_req.txt（一行一条），dark_core 的 arena 模块看到就做、删掉
    fn send_arena(&mut self, line: &str) {
        let path = core_dir().join("arena_req.txt");
        self.last = match fs::write(&path, format!("{line}\n")) {
            Ok(()) => format!("已发出请求：斗技场 {line}"),
            Err(e) => format!("写不了 {}：{e}", path.display()),
        };
    }

    fn arena_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("斗技场试炼测试", imgui::TreeNodeFlags::empty()) {
            return;
        }
        if !core_dir().join("arena.txt").is_file() {
            ui.text_wrapped("没有 arena.txt（没开敌人随机，或者还没重随）");
            ui.separator();
            return;
        }
        ui.text_wrapped("直接进竞技场（不扣星光碎片、不用站在雕像旁；离开时传到这个竞技场的雕像旁，王城是没变灰的那张图）：");
        for (x, name) in [(2, "宁姆格福"), (1, "盖利德"), (0, "王城")] {
            ui.text(format!("{name}："));
            for (code, waves) in [(1, 2), (2, 4), (3, 8)] {
                ui.same_line();
                if ui.button(format!("{waves} 波##ar{x}_{code}")) {
                    self.send_arena(&format!("进 {x} {code}"));
                }
            }
        }
        if ui.button("清场（这一波的敌人血量设 0）") {
            self.send_arena("清场");
        }
        ui.same_line();
        if ui.button("直接离开（奖励保留）") {
            self.send_arena("结算");
        }
        ui.same_line();
        if ui.button("放弃（当死亡，收回奖励）") {
            self.send_arena("放弃");
        }
        if ui.button("发 3 个星光碎片") {
            self.send_arena("碎片 3");
        }
        ui.same_line();
        if ui.button("状态写进日志##arena") {
            self.send_arena("状态");
        }
        ui.text_wrapped("正常流程：三个竞技场门口的雕像对话里选「斗技场试炼」。结果看 dark_core.log 里「竞技场：」开头的行。");
        // 无尽模式的生成器实验（settings 的 arena.generator_test 写了竞技场名字、重随过才有 gentest 行）
        let gen_line = fs::read_to_string(core_dir().join("arena.txt")).ok().and_then(|t| t.lines().find(|l| l.starts_with("gentest\t")).map(str::to_string));
        if let Some(line) = gen_line {
            let x = line.split('\t').nth(1).unwrap_or("?").to_string();
            let name = match x.as_str() { "0" => "王城", "1" => "盖利德", "2" => "宁姆格福", _ => "?" };
            ui.separator();
            ui.text_wrapped(format!("生成器实验（{name}竞技场，每个敌人一个生成器；先用上面的按钮进那个竞技场的试炼）："));
            for (label, cmd) in [("复活这一波倒下的", "复活这一波"), ("叫一只没出场的精英", "叫精英"), ("叫一只没出场的 Boss", "叫Boss")] {
                if ui.button(format!("{label}##gen{cmd}")) {
                    self.send_arena(&format!("生成器 {cmd}"));
                }
                ui.same_line();
            }
            ui.new_line();
            if ui.button("记录这个竞技场的敌人##gen记录") {
                self.send_arena("生成器 记录");
            }
            ui.text_wrapped("结果看 dark_core.log 里「生成器实验：」开头的行（倒下 / 又活了、复活前后身上的效果、被挪到出生点、卢恩多了多少）。");
        }
        ui.separator();
    }

    /// 高难度锁定（用户 2026-11-14「给开发工具加一个解除高难度锁定的按钮 我要录素材」）：熄灭 / 点亮锁定标记
    /// （写 curses_req.txt 的「标记 编号 亮 / 灭」，dark_core 的 curses 模块改）
    fn lock_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("高难度锁定（录素材用：解除后能切回普通等难度）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        if ui.button("解除高难度锁定##lock") {
            self.send_curse(&format!("标记 {DIFF_LOCK_FLAG} 灭"));
        }
        ui.same_line();
        if ui.button("恢复锁定##lock") {
            self.send_curse(&format!("标记 {DIFF_LOCK_FLAG} 亮"));
        }
        ui.text_wrapped(concat!("只改这个角色的锁定标记（会存档）。解除后在赐福「暗黑重铸」→「难度」里普通等难度能选了；",
                                "这时再选死亡 / 不可能，会照第一次进入那样：要先击败过黑剑，走三个确认框，所有头目复活。",
                                "录完想保持原样就点「恢复锁定」。结果看 dark_core.log 里「咒痕：开发工具：标记」那一行（要在游戏里、人物在场时才处理）。"));
        ui.separator();
    }

    /// 七咒测试：写 curses_req.txt（一行一条），dark_core 的 curses 模块看到就做、删掉
    fn send_curse(&mut self, line: &str) {
        let path = core_dir().join("curses_req.txt");
        self.last = match fs::write(&path, format!("{line}\n")) {
            Ok(()) => format!("已发出请求：咒痕 {line}"),
            Err(e) => format!("写不了 {}：{e}", path.display()),
        };
    }

    /// 能力值调整（用户 2026-11-04 先用它试了直接升一级可行，许愿石升级照这个做）：写 levelup_req.txt，dark_core 的 levelup 模块直接改能力值和等级、记日志
    fn send_levelup(&mut self, line: &str) {
        let path = core_dir().join("levelup_req.txt");
        self.last = match fs::write(&path, format!("{line}\n")) {
            Ok(()) => format!("已发出请求：能力值调整 {line}"),
            Err(e) => format!("写不了 {}：{e}", path.display()),
        };
    }

    fn levelup_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("能力值调整（直接 ±1，等级跟着变）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        for (k, name) in ["生命力", "集中力", "耐力", "力气", "灵巧", "智力", "信仰", "感应"].iter().enumerate() {
            if ui.button(format!("{name} +1##lv{k}")) {
                self.send_levelup(&format!("属性 {k} 1"));
            }
            ui.same_line();
            if ui.button(format!("-1（撤销）##lvm{k}")) {
                self.send_levelup(&format!("属性 {k} -1"));
            }
            if k % 2 == 0 {
                ui.same_line();
                ui.text("   ");
                ui.same_line();
            }
        }
        if ui.button("记录现在的能力值") {
            self.send_levelup("记录");
        }
        ui.text_wrapped("直接改能力值和等级（不花卢恩、不扣许愿石），游戏 1 秒内自己重算最大血量等。\
                         dark_core.log 里「直接升级测试」开头的行记了改之前、改后 1 秒和 5 秒的数值。用「-1（撤销）」改回去。");
        ui.separator();
    }

    fn curses_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("咒痕测试（碎片、反转、烙印）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        if d.curses.is_empty() {
            ui.text_wrapped("curses.txt 里没有区域（没开咒痕，或者还没重随）");
            ui.separator();
            return;
        }
        for (k, name, region) in &d.curses {
            ui.text(format!("{name}（{region}）碎片："));
            for n in [0, 4, 5] {
                ui.same_line();
                if ui.button(format!("{n}##cur{k}_{n}")) {
                    self.send_curse(&format!("碎片 {k} {n}"));
                }
            }
        }
        if ui.button("全部清零（都是诅咒）") {
            self.send_curse("碎片 全部 0");
        }
        ui.same_line();
        if ui.button("全部反转（都是祝福）") {
            self.send_curse("碎片 全部 5");
        }
        if ui.button("马上换烙印的目标") {
            self.send_curse("烙印 换");
        }
        if ui.button("战斗复活：重置成这次休息后没用过") {
            self.send_curse("复活 重置");
        }
        ui.text("叙事提示：");
        ui.same_line();
        if ui.button("开场两行##story") {
            self.send_curse("开场 试放");
        }
        ui.same_line();
        if ui.button("重置开场（在这两档里约 3 秒后真放一次）##story") {
            self.send_curse("开场 重置");
        }
        ui.same_line();
        if ui.button("七道全反转##story") {
            self.send_curse("全反转提示");
        }
        for k in 0..7 {
            if k > 0 {
                ui.same_line();
            }
            if ui.button(format!("反转 {}##revline{k}", k + 1)) {
                self.send_curse(&format!("反转提示 {k}"));
            }
        }
        ui.text_wrapped("只在「死亡」「不可能」里生效；结果看 dark_core.log 里「咒痕」开头的行，状态在赐福「暗黑重铸」→「咒痕」（这两档里才列出来）。");
        ui.separator();
    }

    /// 无形测试：直接拿护符（传说，掉落很少），日志里看开关
    fn unseen_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("无形测试（敌人不读箭、法术、道具）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        match d.unseen_tal.first() {
            Some(t) => {
                if ui.button(format!("直接拿无形护符##unseen{t}")) {
                    self.send(format!("护符编号 {t}"));
                }
            }
            None => ui.text_wrapped("unseen.txt 里没有护符（还没重随）"),
        }
        ui.text_wrapped(concat!("戴上后 0.5 秒内 dark_core.log 写「无形：…子弹」，摘下 1 秒后还原。",
                                "对比方法：同一种敌人，戴和不戴时分别施法、射箭、扔投掷道具，看它还会不会提前闪避；近战出招、喝药不受影响。"));
        ui.separator();
    }

    /// 疫病测试：查最近的敌人（身上的效果 + 异常抗性，看免疫摘没摘）。护符本身是词条，在下面的护符页发
    fn plague_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("疫病测试（所有敌人都会陷入所有异常）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        ui.text_wrapped("护符在下面的「护符」页搜「疫病」发放。");
        if ui.button("查看最近的敌人（身上的效果、异常抗性，写进日志）##plague") {
            self.send_line("查 敌");
        }
        ui.text_wrapped(concat!("戴上后 0.5 秒内在场的敌人摘掉七种异常的免疫（90000 中毒 / 90010 腐败 / 90020 出血 / 90040 冻伤 / 90300 睡眠 / 90060 发狂 / 90030 咒死）、",
                                "挂上抗性倍率（7305100 起每种 200 号，低稀有度所有敌人再加 30 / 20 / 10%）；摘下 1 秒后恢复。",
                                "dark_core.log 里搜「疫病护符」；查看敌人那行最后是七种异常的「还差多少 / 上限」。"));
        ui.separator();
    }

    /// 骨灰词条测试（用户 2026-11-09，提案 dev\item_system\骨灰词条提案.md）：发测试骨灰（重随的 rr/ashtest.py 建，编号同那边的 GOODS）；
    /// 骨灰稀有度（2026-11-10）：发原版骨灰，进背包后 dark_core（gear\ashes.rs）换成带稀有度、词条的容器骨灰
    fn ash_test_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("骨灰测试（稀有度、词条、召唤物日志）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        ui.text("发原版骨灰（进背包后自动换成带稀有度的）：");
        for (name, id) in ASH_SAMPLES {
            ui.same_line();
            if ui.button(format!("{name}##ashs{id}")) {
                self.send(format!("道具 {id} 1"));
            }
        }
        if ui.button("随机原版骨灰（同死亡 / 不可能 Boss 掉的）##ashrand") {
            if !d.ash_kinds.is_empty() {
                let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |x| x.subsec_nanos() as usize);
                let id = d.ash_kinds[t % d.ash_kinds.len()].0;
                self.send(format!("道具 {id} 1"));
            }
        }
        ui.same_line();
        if ui.button("一次发上面这几种 + 另外 5 种##ashall") {
            let lines: Vec<String> = ASH_SAMPLES.iter().map(|x| x.1).chain(ASH_MORE).map(|id| format!("道具 {id} 1")).collect();
            self.send(lines.join("\n"));
        }
        ui.text_wrapped("指定种类、稀有度、前缀、词条：用最下面发放窗口的「骨灰」类别（同武器 / 护符）。");
        if ui.button("暂停转换（原版骨灰先不换，拿来对照）##ashoff") {
            self.send("骨灰转换 关".into());
        }
        ui.same_line();
        if ui.button("恢复转换##ashon") {
            self.send("骨灰转换 开".into());
        }
        if ui.button("骨灰状态写进日志##ashst") {
            self.send_line("骨灰状态");
        }
        ui.text_wrapped(concat!("dark_core.log 里搜「骨灰：」看换成了哪个容器（稀有度 0 普通 ~ 3 传说、前缀、词条、集结）；",
                                "搜「骨灰召唤：」看召唤：召唤的是哪个容器、专注消耗和原版比，每只召唤物的血量上限和预期比（看稀有度、坚韧有没有生效），",
                                "召唤 3 秒后的只数（集结那一只出没出来），前缀每次触发，召唤物倒下 / 消失，召唤物都没了时的小结。"));
        ui.text_wrapped(concat!("用玩家形象的（仿身泪滴、傀儡）召唤 1 秒后，日志记它和你每一格装备的参数编号，不一样的列出来；",
                                "对照原版：先「暂停转换」，再发原版骨灰召唤，测完点「恢复转换」。"));
        ui.text_wrapped(concat!("测前缀：爆裂、殉道让召唤物被打倒（找强一点的敌人）；激昂看召唤物血量掉到 30% 以下那行；",
                                "庇护、共鸣召唤出来就会记「召唤者挂上效果」，再对比受到 / 造成的伤害；战意在召唤者 20 米内打死敌人。"));
        ui.separator();
        if ui.button("发放测试骨灰：出血的离群野狼##ashtest") {
            self.send(format!("道具 {ASH_TEST} 1"));
        }
        ui.same_line();
        if ui.button("查看最近的敌人（异常抗性写进日志）##ashtest") {
            self.send_line("查 敌");
        }
        ui.text_wrapped(concat!("召唤 3 只离群野狼，每只身上挂一个「命中时触发」效果（照出血油脂，出血累积 40）。让狼咬敌人：",
                                "敌人头上出现出血条、发作，就说明这条路能用；没反应就改走 dark_core。",
                                "测的时候别用带出血的武器、别涂出血油脂，免得分不清是谁打的。"));
        ui.text_wrapped(concat!("dark_core.log 里搜「骨灰诊断」（只看测试狼）：测试狼出现时那行列出它身上所有效果，看测试载体 7310000 在不在；",
                                "测试狼在场时 30 米内的敌人出血「还差多少 / 上限」一变就记一行，敌人身上出现出血累积效果 7310001 也记",
                                "（出现了 = 命中时触发生效了）；召唤物都消失时有一行小结。"));
        ui.separator();
    }

    /// 帧耗时统计（用户 2026-11-05「高难下有点卡顿」）：开了以后每秒取一次最近 2 秒的结果，停止时开始以来的结果写进 dark_core.log
    fn prof_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("帧耗时统计（各模块每帧花多久）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        let Some(api) = prof_api() else {
            ui.text_wrapped("dark_core 没加载，或者版本太老（没有统计的导出）");
            ui.separator();
            return;
        };
        if ui.button(if self.prof_on { "停止（结果写进 dark_core.log）##prof" } else { "开始统计##prof" }) {
            self.prof_on = !self.prof_on;
            unsafe { (api.set)(self.prof_on as u32) };
            self.prof_at = None;
            if !self.prof_on {
                self.last = "帧耗时统计：结果写进 dark_core.log 了".to_string();
            }
        }
        if self.prof_on {
            if self.prof_at.is_none_or(|t| t.elapsed() >= Duration::from_secs(1)) {
                self.prof_at = Some(Instant::now());
                let mut buf = vec![0u8; 8192];
                let n = unsafe { (api.get)(buf.as_mut_ptr(), buf.len()) };
                self.prof_text = String::from_utf8_lossy(&buf[..n]).into_owned();
            }
            ui.text_wrapped(&self.prof_text);
        } else {
            ui.text_wrapped("在卡的地方开始，打一会儿再停止；可以和普通难度同一个地方比。F9 窗口本身也要画，开着窗口时帧长会偏高一点。");
        }
        ui.separator();
    }

    /// 传说光效测试：写 glow_req.txt（「重挂」/「查」），dark_core 的 glow 模块看到就做、删掉
    fn glow_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("传说光效测试（换武器后光效挂在手上）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        for (name, line) in [("马上重挂光效##glow", "重挂"), ("查看光效状态（写进日志）##glow", "查")] {
            if ui.button(name) {
                let path = core_dir().join("glow_req.txt");
                self.last = match fs::write(&path, format!("{line}\n")) {
                    Ok(()) => format!("已发出请求：传说光效 {line}"),
                    Err(e) => format!("写不了 {}：{e}", path.display()),
                };
            }
            ui.same_line();
        }
        ui.new_line();
        ui.text_wrapped(concat!("拿着传说武器换一次武器，看光效在武器上还是手上；换武器 1 秒后 dark_core 会自动摘掉光效让游戏重挂。",
                                "要是还在手上，点「马上重挂光效」再看；「查看」把拿着的武器、身上的光效写进日志。dark_core.log 里搜「传说光效」。"));
        ui.separator();
    }

    /// 死亡以上难度屏障测试：写 barrier_req.txt，dark_core 的 barrier 模块看到就做、删掉
    fn barrier_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("死亡以上难度屏障测试（错配时的圆顶 / 推回 / 禁止传送）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        let rows: [&[(&str, &str)]; 3] = [
            &[("强制围起来（不管难度）##bar", "开"), ("取消强制##bar", "关"), ("在这里重新围、放圆顶##bar", "圆顶"), ("查看状态（写进日志）##bar", "查")],
            &[("半径 5 米##bar", "半径 5"), ("半径 10 米（特效那么大）##bar", "半径 10"), ("半径 15 米##bar", "半径 15")],
            &[("提示：要重启（死亡以上）##bar", "提示 boss on"), ("提示：要重启（普通）##bar", "提示 boss off"), ("提示：Boss 取回力量##bar", "提示 boss power")],
        ];
        for row in rows {
            for (name, line) in row {
                if ui.button(name) {
                    let path = core_dir().join("barrier_req.txt");
                    self.last = match fs::write(&path, format!("{line}
")) {
                        Ok(()) => format!("已发出请求：难度屏障 {line}"),
                        Err(e) => format!("写不了 {}：{e}", path.display()),
                    };
                }
                ui.same_line();
            }
            ui.new_line();
        }
        ui.text_wrapped(concat!("「强制围起来」在现在的位置放原版封印监牢的圆顶、走到半径外推回来（骑马时推灵马）、地图上不能传送；",
                                "「取消强制」后只剩难度真的对不上时的屏障。特效（缩小的封印监牢圆顶 + 光幕 + 地面圈）固定 10 米，半径只改推回的距离；围起来 1 秒后 dark_core 在圆心放圆顶（日志里写着放没放成）。",
                                "提示按钮马上闪一条原版提示看文字（这次不是按难度自动加载启动的就没有这几条）。dark_core.log 里搜「难度屏障」。"));
        ui.separator();
    }

    /// 联机通道测试（联机计划 13.4）：写 coopnet_req.txt，dark_core 的 link.rs 看到就做、删掉
    fn coopnet_ui(&mut self, ui: &Ui) {
        if !ui.collapsing_header("联机通道测试（整合包自己的 Steam 消息）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        for (name, line) in [("查看状态（写进日志）##cn", "状态"), ("自测：发给自己##cn", "自测"), ("给连上的队员发测试消息##cn", "测试 你好")] {
            if ui.button(name) {
                let path = core_dir().join("coopnet_req.txt");
                self.last = match fs::write(&path, format!("{line}\n")) {
                    Ok(()) => format!("已发出请求：联机通道 {line}"),
                    Err(e) => format!("写不了 {}：{e}", path.display()),
                };
            }
            ui.same_line();
        }
        ui.new_line();
        ui.text_wrapped(concat!("「查看状态」把会话里的队员、连上没有、往返时间、兼容档案一不一致写进日志；",
                                "「自测」不用联机也能点：给自己发一条，看 Steam 会不会送回来（送不回来不代表坏了，要两台电脑实测）；",
                                "「发测试消息」发给所有已经连上的队员，对方日志里会记「发来测试消息」。dark_core.log 里搜「联机通道」。"));
        ui.separator();
    }

    /// 效果调试区：给自己 / 15 米内最近的敌人挂效果
    fn speffect_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("效果调试（给自己 / 15 米内最近的敌人挂效果）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        ui.input_int("效果编号", &mut self.sp_id).build();
        if ui.button("挂给自己") {
            self.send_sp("我", self.sp_id);
        }
        ui.same_line();
        if ui.button("挂给最近的敌人") {
            self.send_sp("敌", self.sp_id);
        }
        // 原版对照：很显眼的黄金誓约（金色光环）。只有带「挂给自己」位的效果行才能直接挂（原版命中时挂给对方的那种，比如 1709000，挂不上）
        if ui.button("原版对照：黄金誓约（1730，挂给自己）") {
            self.send_sp("我", 1730);
        }
        ui.same_line();
        if ui.button("原版对照：黄金誓约（1730，挂给敌人）") {
            self.send_sp("敌", 1730);
        }
        // 见切成立时挂的羽毛特效（launcher\reroll\rr\sounds.py 的 MIKIRI_VFX_SP，dark_core 在见切音效同一帧挂；用户 2026-11-13「用A吧」）：
        // 不用真的见切也能反复看。重随没建它（旧的重随包）就挂不上
        if ui.button("试放见切特效：潜雾猛禽的羽毛（7299130，挂给自己）") {
            self.send_sp("我", MIKIRI_VFX_SP);
        }
        // 加速光晕（影步 / 处刑 / 转念的状态效果里挂的那个，rr/sounds.py HASTE_GLOW；用户 2026-11-13「其他加速也挂这个特效」）：
        // 羽毛特效里两个候选各挂 3 秒对比（用户 2026-11-14：A 长在身体里、穿铠甲看不见，现在用 B）
        if ui.button("加速光晕对比 A：440700（3 秒）") {
            self.send_sp("我", 7299133);
        }
        ui.same_line();
        if ui.button("B：440701（3 秒，现在用的）") {
            self.send_sp("我", 7299134);
        }
        if ui.button("查看最近的敌人（血量、上限、身上的效果，写进日志）") {
            self.send_line("查 敌");
        }
        for (name, ids) in &d.marks {
            ui.text(format!("{name}（传说档，挂给敌人）："));
            for (k, &id) in ids.iter().enumerate() {
                ui.same_line();
                if ui.button(format!("{} 层##mark{id}", k + 1)) {
                    self.send_sp("敌", id);
                }
            }
        }
        // 词条触发时的特效（用户 2026-11-13）：不用真的触发也能反复看；读不到 runtime.txt / 旧的重随包就只有第一个按钮
        ui.text("词条触发时的特效（传说档）：");
        if ui.button("碎骨 / 千钧：满蓄力出招期间的削韧光（3 秒，挂给自己）") {
            self.send_sp("我", POISE_GLOW_DEV_SP);
        }
        for (name, enemy, ids) in &d.flashes {
            ui.text(format!("{name}（{}）：", if *enemy { "挂给敌人，按消耗的层数" } else { "挂给自己" }));
            for (k, &id) in ids.iter().enumerate() {
                ui.same_line();
                let label = if ids.len() > 1 { format!("{} 层##flash{id}", k + 1) } else { format!("试放##flash{id}") };
                if ui.button(label) {
                    self.send_sp(if *enemy { "敌" } else { "我" }, id);
                }
            }
        }
        ui.separator();
    }

    /// 一键发放流派：选流派和档，看会发什么，点按钮排队
    fn kit_ui(&mut self, ui: &Ui, d: &Data) {
        if !ui.collapsing_header("一键发放流派（每条词条一件护符 + 塞满词条的防具 + 适合的武器）", imgui::TreeNodeFlags::empty()) {
            return;
        }
        if d.archs.is_empty() {
            ui.text_wrapped("affixes.txt 里没有流派（是更新前的重随写的）：重新启动一次游戏让重随写出来，再点「重新读取 affixes.txt」。");
            ui.separator();
            return;
        }
        self.kit_arch = self.kit_arch.min(d.archs.len() - 1);
        let names: Vec<String> = d.archs.iter().map(|(a, n)| format!("{a}（{n} 条词条）")).collect();
        ui.combo_simple_string("流派", &mut self.kit_arch, &names);
        ui.combo_simple_string("档##kit", &mut self.tier, &RAR);
        let k = kit(d, &d.archs[self.kit_arch].0, self.tier);
        ui.text_wrapped(&k.summary);
        if ui.button("发放这一流派") {
            self.queue.extend(k.lines);
            self.queue_at = Instant::now() - Duration::from_secs(2);
            self.last = format!("一键发放流派：{} 排队 {} 件", d.archs[self.kit_arch].0, self.queue.len());
        }
        if !self.queue.is_empty() {
            ui.same_line();
            ui.text(format!("排队中：还剩 {} 件", self.queue.len()));
            ui.same_line();
            if ui.button("取消排队") {
                self.queue.clear();
                self.last = "一键发放流派：取消了排队（已经发出去的那批照发）".into();
            }
        }
        ui.separator();
    }

    /// 排队的请求：上一批被 dark_core 取走（请求文件删掉了）就写下一批，每批不超过发货表的行数；窗口关着也照样发（每秒看一次）
    fn pump(&mut self) {
        if self.queue.is_empty() || self.queue_at.elapsed() < Duration::from_secs(1) {
            return;
        }
        self.queue_at = Instant::now();
        let path = core_dir().join("devgive_req.txt");
        if path.exists() {
            return;
        }
        let n = self.queue.len().min(self.data.as_ref().map_or(32, |d| d.deliver).max(1));
        let batch: Vec<String> = self.queue.drain(..n).collect();
        let text = format!("# dark_dev 一键发放流派（这一批 {n} 件，还剩 {} 件排队），dark_core 发完会删掉\n{}\n", self.queue.len(), batch.join("\n"));
        self.last = match fs::write(&path, text) {
            Ok(()) => format!("一键发放流派：发出 {n} 件，还剩 {} 件排队", self.queue.len()),
            Err(e) => {
                self.queue.clear();
                format!("写不了 {}：{e}（排队的都取消了）", path.display())
            }
        };
    }

    fn refresh_log(&mut self) {
        if self.log_at.elapsed() < Duration::from_secs(1) {
            return;
        }
        self.log_at = Instant::now();
        let Ok(bytes) = fs::read(core_dir().join("dark_core.log")) else { return };
        let tail = &bytes[bytes.len().saturating_sub(16384)..];
        let text = String::from_utf8_lossy(tail);
        self.log_tail = text.lines().filter(|l| l.contains("开发工具") || l.contains("敌人血量（诊断）") || l.starts_with("唤声船") || l.contains("相杀火花")).map(|l| l.to_string()).collect();
        let n = self.log_tail.len();
        self.log_tail.drain(..n.saturating_sub(8));
    }
}

/// 带搜索框的单选列表；None = 随机
fn pick_list(ui: &Ui, id: &str, filter: &mut String, sel: &mut Option<usize>, items: &[(usize, String)], random_label: &str) {
    ui.input_text(format!("搜索##{id}"), filter).build();
    let f = filter.to_lowercase();
    ui.child_window(format!("##list{id}")).size([0.0, 150.0]).border(true).horizontal_scrollbar(true).build(|| {
        if ui.selectable_config(random_label).selected(sel.is_none()).build() {
            *sel = None;
        }
        let mut shown = 0;
        for (i, name) in items {
            if !f.is_empty() && !name.to_lowercase().contains(&f) {
                continue;
            }
            shown += 1;
            if shown > LIST_MAX {
                ui.text_disabled("……（太多了，再输几个字）");
                break;
            }
            if ui.selectable_config(format!("{name}##{id}{i}")).selected(*sel == Some(*i)).build() {
                *sel = Some(*i);
            }
        }
    });
}

impl ImguiRenderLoop for App {
    fn initialize<'a>(&'a mut self, ctx: &mut imgui::Context, _render_context: &'a mut dyn RenderContext) {
        let fonts = ["C:\\Windows\\Fonts\\msyh.ttc", "C:\\Windows\\Fonts\\msyh.ttf", "C:\\Windows\\Fonts\\simhei.ttf", "C:\\Windows\\Fonts\\simsun.ttc"];
        if let Some(bytes) = fonts.iter().find_map(|p| fs::read(p).ok()) {
            let data: &'static [u8] = Box::leak(bytes.into_boxed_slice());
            ctx.fonts().add_font(&[FontSource::TtfData {
                data,
                size_pixels: 18.0,
                config: Some(FontConfig { glyph_ranges: FontGlyphRanges::chinese_full(), ..FontConfig::default() }),
            }]);
        }
        ctx.set_ini_filename(None::<PathBuf>);
        self.cursor_hooks = hook_cursor();
        self.input_hooks = hook_dinput();
        match load() {
            Ok(d) => self.data = Some(d),
            Err(e) => self.err = e,
        }
    }

    fn before_render<'a>(&'a mut self, ctx: &mut imgui::Context, _render_context: &'a mut dyn RenderContext) {
        ctx.io_mut().mouse_draw_cursor = self.open;
        OPEN.store(self.open, Ordering::Relaxed);
        WANT_KB.store(self.open && ctx.io().want_text_input, Ordering::Relaxed);
        if self.open {
            free_cursor();
        }
    }

    fn render(&mut self, ui: &mut Ui) {
        if ui.is_key_pressed_no_repeat(Key::F9) {
            self.open = !self.open;
            if self.open && self.data.is_none() {
                match load() {
                    Ok(d) => {
                        self.data = Some(d);
                        self.err.clear();
                    }
                    Err(e) => self.err = e,
                }
            }
        }
        self.pump();
        if !self.open {
            return;
        }
        self.refresh_log();
        let mut open = self.open;
        ui.window("Dark Reforged 开发工具（F9 开关）")
            .size([560.0, 720.0], Condition::FirstUseEver)
            .position([60.0, 60.0], Condition::FirstUseEver)
            .opened(&mut open)
            .build(|| {
                let Some(d) = self.data.take() else {
                    ui.text_wrapped(&self.err);
                    if ui.button("重新读取 affixes.txt") {
                        match load() {
                            Ok(d) => {
                                self.data = Some(d);
                                self.err.clear();
                            }
                            Err(e) => self.err = e,
                        }
                    }
                    return;
                };
                self.speffect_ui(ui, &d);
                self.hard_ui(ui, &d);
                self.lock_ui(ui);
                self.nightmare_ui(ui, &d);
                self.arena_ui(ui);
                self.curses_ui(ui, &d);
                self.plague_ui(ui);
                self.ash_test_ui(ui, &d);
                self.unseen_ui(ui, &d);
                self.prof_ui(ui);
                self.glow_ui(ui);
                self.barrier_ui(ui);
                self.coopnet_ui(ui);
                self.levelup_ui(ui);
                self.clashfx_ui(ui, &d);
                self.orbshot_ui(ui);
                self.boat_ui(ui);
                self.kit_ui(ui, &d);
                for (k, name) in CATS.iter().enumerate() {
                    if k > 0 {
                        ui.same_line();
                    }
                    if ui.radio_button_bool(*name, self.cat == k) {
                        self.cat = k;
                    }
                }
                ui.combo_simple_string("档", &mut self.tier, &RAR);
                ui.input_int("件数", &mut self.count).build();
                ui.separator();
                match self.cat {
                    0 => self.weapon_ui(ui, &d),
                    1 => self.armor_ui(ui, &d),
                    2 => self.talisman_ui(ui, &d),
                    _ => self.ash_ui(ui, &d),
                }
                ui.separator();
                let line = self.line(&d);
                ui.text_wrapped(format!("请求：{line}"));
                if ui.button("发放") {
                    self.send(line);
                }
                ui.same_line();
                if ui.button("重新读取 affixes.txt") {
                    match load() {
                        Ok(nd) => {
                            self.data = Some(nd);
                            self.wbase = None;
                            self.pbase = None;
                            self.pfams.clear();
                            self.tfam = None;
                            self.skill = None;
                            self.abase = None;
                            self.apre = None;
                            self.aaffs.clear();
                            return;
                        }
                        Err(e) => self.err = e,
                    }
                }
                if !self.last.is_empty() {
                    ui.text_wrapped(&self.last);
                }
                ui.separator();
                if self.cursor_hooks < 2 {
                    ui.text_wrapped(format!("（光标钩子只挂上了 {} / 2 个，鼠标可能还是动不了）", self.cursor_hooks));
                }
                if self.input_hooks < 2 {
                    ui.text_wrapped(format!("（输入钩子只挂上了 {} 个，游戏可能还会收到鼠标）", self.input_hooks));
                }
                ui.text("dark_core.log 里最近的「开发工具」：");
                for l in &self.log_tail {
                    ui.text_wrapped(l);
                }
                self.data = Some(d);
            });
        self.open = open;
    }

    fn message_filter(&self, _io: &imgui::Io) -> MessageFilter {
        if self.open { MessageFilter::InputAll } else { MessageFilter::empty() }
    }
}

impl App {
    fn weapon_ui(&mut self, ui: &Ui, d: &Data) {
        ui.text("本体（不选 = 随机）");
        let items: Vec<(usize, String)> = d.wbase.iter().enumerate().map(|(i, b)| (i, format!("{}  [{}] 类型 {}", b.name, b.id, b.typ))).collect();
        pick_list(ui, "w", &mut self.wfilter, &mut self.wbase, &items, "（随机本体）");
        ui.text("补正");
        for (k, name) in ["随机", "指定项数", "指定数值"].iter().enumerate() {
            if k > 0 {
                ui.same_line();
            }
            if ui.radio_button_bool(format!("{name}##scal"), self.scal_mode == k) {
                self.scal_mode = k;
            }
        }
        match self.scal_mode {
            1 => {
                ui.combo_simple_string("项数", &mut self.n_idx, &["1", "2", "3", "5（全能）"]);
            }
            2 => {
                for k in 0..5 {
                    ui.checkbox(format!("##on{k}"), &mut self.cor_on[k]);
                    ui.same_line();
                    ui.slider(STATS[k], 1, 250, &mut self.cor[k]);
                }
            }
            _ => {}
        }
        ui.text("附加异常（最多 3 种）");
        for (k, name) in ["随机", "不带", "指定"].iter().enumerate() {
            if k > 0 {
                ui.same_line();
            }
            if ui.radio_button_bool(format!("{name}##st"), self.status_mode == k) {
                self.status_mode = k;
            }
        }
        if self.status_mode == 2 {
            for k in 0..7 {
                if k % 4 != 0 {
                    ui.same_line();
                }
                ui.checkbox(STATUS[k], &mut self.status[k]);
            }
        }
        ui.text("战技（不选 = 随机）");
        let items: Vec<(usize, String)> = d.skills.iter().enumerate().map(|(i, (id, n))| (i, format!("{n}  [{id}]"))).collect();
        let mut sel = self.skill.and_then(|id| d.skills.iter().position(|s| s.0 == id));
        pick_list(ui, "s", &mut self.sfilter, &mut sel, &items, "（随机战技）");
        self.skill = sel.map(|i| d.skills[i].0);
        ui.text("属性（物理＋元素 / 纯元素；法杖、圣印记、弓弩、火把、调香瓶不抽）");
        for (k, name) in ELEMS.iter().enumerate() {
            if k > 0 && k != 3 && k != 7 {
                ui.same_line();
            }
            if ui.radio_button_bool(format!("{name}##el"), self.elem == k) {
                self.elem = k;
            }
        }
        if (3..=6).contains(&self.elem) {
            ui.slider("元素占比 %（0 = 随机）##elp", 0, 99, &mut self.elem_pct);
        }
        ui.text("特效（武器的特殊效果词条位）");
        for (k, name) in ["随机", "不带", "指定"].iter().enumerate() {
            if k > 0 {
                ui.same_line();
            }
            if ui.radio_button_bool(format!("{name}##spec"), self.spec_mode == k) {
                self.spec_mode = k;
            }
        }
        if self.spec_mode == 2 {
            for (i, (sp, name)) in d.wspec.iter().enumerate() {
                if ui.radio_button_bool(format!("{name}##sp{i}"), self.spec == Some(*sp)) {
                    self.spec = Some(*sp);
                }
            }
        }
        ui.text("常驻效果（法杖 / 圣印记的流派加成、盾牌抗性，最多 2 个）");
        for (k, name) in ["随机", "不带", "指定"].iter().enumerate() {
            if k > 0 {
                ui.same_line();
            }
            if ui.radio_button_bool(format!("{name}##res"), self.res_mode == k) {
                self.res_mode = k;
            }
        }
        if self.res_mode == 2 {
            ui.input_text("搜索##rf", &mut self.rfilter).build();
            let f = self.rfilter.to_lowercase();
            ui.child_window("##wres").size([0.0, 140.0]).border(true).horizontal_scrollbar(true).build(|| {
                for (i, (sp, cat, name)) in d.wres.iter().enumerate() {
                    if !f.is_empty() && !name.to_lowercase().contains(&f) && !cat.contains(&f) {
                        continue;
                    }
                    let mut on = self.res.contains(sp);
                    if ui.checkbox(format!("[{cat}] {name}##wr{i}"), &mut on) {
                        if on && self.res.len() < 2 {
                            self.res.push(*sp);
                        } else if !on {
                            self.res.retain(|x| x != sp);
                        }
                    }
                }
            });
        }
    }

    fn armor_ui(&mut self, ui: &Ui, d: &Data) {
        ui.combo_simple_string("部位", &mut self.slot, &["随机", "头", "身", "手", "腿"]);
        ui.text("本体（选了就不看部位；不选 = 这个部位随机）");
        let items: Vec<(usize, String)> = d
            .pbase
            .iter()
            .enumerate()
            .filter(|(_, b)| self.slot == 0 || b.slot as usize == self.slot - 1)
            .map(|(i, b)| (i, format!("{}  [{}] {}", b.name, b.id, SLOTS[b.slot.min(3) as usize])))
            .collect();
        pick_list(ui, "p", &mut self.pfilter, &mut self.pbase, &items, "（随机本体）");
        let slot = self.pbase.map(|i| d.pbase[i].slot as usize + 1).unwrap_or(self.slot);
        ui.text(format!("词条（最多 3 个，已选 {}；不选 = 随机）", self.pfams.len()));
        ui.same_line();
        if ui.button("一键清除##pf") {
            self.pfams.clear();
        }
        ui.input_text("搜索##pf", &mut self.ffilter).build();
        let f = self.ffilter.to_lowercase();
        ui.child_window("##pfams").size([0.0, 200.0]).border(true).horizontal_scrollbar(true).build(|| {
            for (i, fam) in d.fams.iter().enumerate() {
                if !fam.armor || (slot > 0 && fam.slots & (1 << (slot - 1)) == 0) {
                    continue;
                }
                if !f.is_empty() && !fam.name.to_lowercase().contains(&f) && !fam.key.contains(&f) && !fam.text.contains(&self.ffilter) {
                    continue;
                }
                let mut on = self.pfams.contains(&i);
                if ui.checkbox(format!("{}  {}##pf{i}", fam.name, fam.text), &mut on) {
                    if on && self.pfams.len() < 3 {
                        self.pfams.push(i);
                    } else if !on {
                        self.pfams.retain(|&x| x != i);
                    }
                }
            }
        });
    }

    fn talisman_ui(&mut self, ui: &Ui, d: &Data) {
        let r = self.tier.min(3);
        ui.text("词条（不选 = 随机；灰色的这个稀有度没有护符）");
        ui.input_text("搜索##tf", &mut self.ffilter).build();
        let f = self.ffilter.to_lowercase();
        ui.child_window("##tfams").size([0.0, 320.0]).border(true).horizontal_scrollbar(true).build(|| {
            if ui.selectable_config("（随机词条）").selected(self.tfam.is_none()).build() {
                self.tfam = None;
            }
            for (i, fam) in d.fams.iter().enumerate() {
                if !f.is_empty() && !fam.name.to_lowercase().contains(&f) && !fam.key.contains(&f) && !fam.text.contains(&self.ffilter) {
                    continue;
                }
                let ok = fam.tal[r];
                if ui.selectable_config(format!("{}  {}##tf{i}", fam.name, fam.text)).selected(self.tfam == Some(i)).disabled(!ok).build() {
                    self.tfam = Some(i);
                }
            }
        });
    }

    /// 骨灰（dark_core 的 gear\ashes.rs dev_give：直接生成骨灰容器，不用先拿原版的）；档 = 稀有度（幽影之地的传说同传说）
    fn ash_ui(&mut self, ui: &Ui, d: &Data) {
        if d.ash_kinds.is_empty() {
            ui.text_wrapped("没有骨灰的定义（ashes.txt）：骨灰稀有度没开，或者还没启动过一次");
            return;
        }
        ui.text("本体（不选 = 随机）");
        let items: Vec<(usize, String)> =
            d.ash_kinds.iter().enumerate().map(|(i, k)| (i, format!("{}  [{}]", if k.1.is_empty() { "（没有名字）" } else { k.1.as_str() }, k.0))).collect();
        pick_list(ui, "a", &mut self.afilter, &mut self.abase, &items, "（随机本体）");
        let top = self.abase.map_or(10, |i| d.ash_kinds[i].2.saturating_sub(1) as i32);
        self.alv = self.alv.clamp(0, top.max(0));
        ui.slider(format!("强化等级（这种最高 +{top}）"), 0, top.max(0), &mut self.alv);
        ui.text("机制前缀（随机 = 照这个稀有度的几率）");
        for (k, name) in ["随机", "不带", "指定"].iter().enumerate() {
            if k > 0 {
                ui.same_line();
            }
            if ui.radio_button_bool(format!("{name}##apm"), self.apre_mode == k) {
                self.apre_mode = k;
            }
        }
        if self.apre_mode == 2 {
            for (i, (_, name, text)) in d.ash_pres.iter().enumerate() {
                if ui.radio_button_bool(format!("{name}  {text}##apre{i}"), self.apre == Some(i)) {
                    self.apre = Some(i);
                }
            }
        }
        ui.text(format!("数值词条（已选 {}；不选 = 照稀有度随机抽）", self.aaffs.len()));
        ui.same_line();
        if ui.button("一键清除##aaf") {
            self.aaffs.clear();
        }
        for (i, (_, name, text)) in d.ash_affs.iter().enumerate() {
            let mut on = self.aaffs.contains(&i);
            if ui.checkbox(format!("{name}  {text}##aaf{i}"), &mut on) {
                if on {
                    self.aaffs.push(i);
                } else {
                    self.aaffs.retain(|&x| x != i);
                }
            }
        }
        ui.text("集结（召唤数量 +1；仿身泪滴是多一个仿身，原版 5 只的变 6 只）");
        for (k, name) in ["照规则（传说带）", "带", "不带"].iter().enumerate() {
            if k > 0 {
                ui.same_line();
            }
            if ui.radio_button_bool(format!("{name}##arl"), self.arally == k) {
                self.arally = k;
            }
        }
    }
}

/// 和 dll\dark_ui 排队挂 DirectX 12 钩子（同名互斥量，最多等 30 秒）：hudhook 在 with() 时抄目标函数开头、apply() 才写跳转，
/// 两个 DLL 交错时先写的那个被绕过、不报错（2026-10-31 装备工坊两局一帧都没画，见 dark_ui 的 HookLock）
struct HookLock(*mut c_void);

#[link(name = "kernel32")]
unsafe extern "system" {
    fn CreateMutexW(attr: *const c_void, initial: i32, name: *const u16) -> *mut c_void;
    fn WaitForSingleObject(h: *mut c_void, ms: u32) -> u32;
    fn ReleaseMutex(h: *mut c_void) -> i32;
    fn CloseHandle(h: *mut c_void) -> i32;
}

impl HookLock {
    fn take() -> Option<Self> {
        let name: Vec<u16> = "Local\\DarkReforged.D3D12Hooks".encode_utf16().chain([0]).collect();
        let h = unsafe { CreateMutexW(std::ptr::null(), 0, name.as_ptr()) };
        if h.is_null() {
            return None;
        }
        match unsafe { WaitForSingleObject(h, 30_000) } {
            0 | 0x80 => Some(Self(h)),
            _ => {
                unsafe { CloseHandle(h) };
                None
            }
        }
    }
}

impl Drop for HookLock {
    fn drop(&mut self) {
        unsafe {
            ReleaseMutex(self.0);
            CloseHandle(self.0);
        }
    }
}

/// 入口：和 hudhook::hudhook! 宏做的一样（开线程挂 DirectX 12 的钩子，挂不上就 eject），但明确返回 TRUE。
/// hudhook 0.9.3 的宏生成的 DllMain 没有返回值，RAX 里剩下什么算什么：偶尔是 0，加载器当成失败把 DLL 卸掉，
/// 可挂钩子的线程已经开了，游戏就崩在「dark_dev.dll_unloaded」（2026-10-29 20:57 的崩溃，YAFSML 日志 cannot load external DLL user_dark_dev）
#[unsafe(no_mangle)]
pub unsafe extern "system" fn DllMain(hmodule: hudhook::windows::Win32::Foundation::HINSTANCE, reason: u32, _: *mut c_void) -> BOOL {
    if reason == hudhook::windows::Win32::System::SystemServices::DLL_PROCESS_ATTACH {
        let raw = hmodule.0 as usize;
        std::thread::spawn(move || {
            let hmodule = hudhook::windows::Win32::Foundation::HINSTANCE(raw as _);
            let lock = HookLock::take();
            let r = hudhook::Hudhook::builder().with::<ImguiDx12Hooks>(App::new()).with_hmodule(hmodule).build().apply();
            drop(lock);
            if let Err(e) = r {
                hudhook::tracing::error!("Couldn't apply hooks: {e:?}");
                hudhook::eject();
            }
        });
    }
    BOOL(1)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 重随写的定义文件（环境变量 DR_CORE_DIR，没设就跳过）：每个流派、每个档的整套里，能出的词条都在护符或防具上，
    /// 防具每件不超过 3 条、部位能放、同一变体组不在一起；设了 DR_KIT_OUT 就把所有行写进去（dark_core 的 kit_lines_generate 逐行生成）
    #[test]
    fn kits_from_real_library() {
        let Some(dir) = std::env::var_os("DR_CORE_DIR") else {
            eprintln!("没设 DR_CORE_DIR，跳过");
            return;
        };
        let d = load_from(Path::new(&dir)).unwrap();
        assert!(!d.archs.is_empty(), "affixes.txt 里没有流派（重随要先写第 10 个字段）");
        let by_key = |k: &str| d.fams.iter().find(|f| f.key == k).unwrap_or_else(|| panic!("没有词条 {k}"));
        let mut all = Vec::new();
        for (a, _) in &d.archs {
            for tier in 0..5 {
                let r = tier.min(3);
                let k = kit(&d, a, tier);
                let mut seen = std::collections::HashSet::new();
                for l in &k.lines {
                    let Some(keys) = l.split_whitespace().find_map(|x| x.strip_prefix("词条=")) else { continue };
                    let keys: Vec<&str> = keys.split(',').collect();
                    if l.starts_with("防具") {
                        assert!(keys.len() <= 3, "{l}");
                        let slot = SLOTS.iter().position(|s| l.contains(&format!("部位={s}"))).unwrap();
                        for (i, x) in keys.iter().enumerate() {
                            let f = by_key(x);
                            assert!(f.slots & (1 << slot) != 0 && f.w[0][r] > 0, "{x} 不能上这个部位 / 这个档的防具：{l}");
                            assert!(f.group.is_empty() || keys[..i].iter().all(|y| by_key(y).group != f.group), "同组两条：{l}");
                        }
                    }
                    seen.extend(keys.iter().map(|x| x.to_string()));
                }
                for f in d.fams.iter().filter(|f| f.arch == *a && (f.w[0][r] > 0 || f.w[1][r] > 0)) {
                    assert!(seen.contains(&f.key), "{a} 档 {tier}：词条 {} 没发", f.key);
                }
                assert!(k.lines.iter().any(|l| l.starts_with("武器")), "{a} 没有武器");
                all.extend(k.lines);
            }
            eprintln!("{a}（传说）：{}", kit(&d, a, 3).summary.replace('\n', " | "));
        }
        if let Some(out) = std::env::var_os("DR_KIT_OUT") {
            fs::write(out, all.join("\n") + "\n").unwrap();
        }
    }
}
