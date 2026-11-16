//! 输入：窗口开着（BLOCK）时游戏收不到键鼠（DirectInput8 的 GetDeviceState / GetDeviceData，游戏不走窗口消息读键鼠）、
//! 手柄（游戏用 xinput1_4.dll 的 XInputGetState，按序号导入）和窗口消息（hudhook 的 MessageFilter，在 lib.rs）；光标放开
//! （SetCursorPos / ClipCursor 拦掉）。界面自己读手柄用原来的 XInputGetState（read_pad）。
//! 键鼠、光标这部分照 dll\dark_dev（已经在游戏里验证过）；手柄是新加的
use std::ffi::c_void;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicIsize, AtomicUsize, Ordering};

use hudhook::mh::{MH_EnableHook, MhHook};
use hudhook::windows::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, RECT, WPARAM};
use hudhook::windows::Win32::Graphics::Gdi::ScreenToClient;
use hudhook::windows::Win32::UI::WindowsAndMessaging::{CallWindowProcW, DefWindowProcW, GWLP_WNDPROC, GetCursorPos, SetWindowLongPtrW, WM_CHAR, WNDPROC};
use hudhook::windows::Win32::System::LibraryLoader::{GetModuleHandleA, GetProcAddress};
use hudhook::windows::core::{BOOL, s};

/// 拦不拦游戏的输入（窗口开着，或者刚关、手柄 / 键还没松开）
pub static BLOCK: AtomicBool = AtomicBool::new(false);

// ------------------------------------------------------------------ 光标
static SET_CURSOR_POS: AtomicUsize = AtomicUsize::new(0);
static CLIP_CURSOR: AtomicUsize = AtomicUsize::new(0);

unsafe extern "system" fn set_cursor_pos(x: i32, y: i32) -> BOOL {
    if BLOCK.load(Ordering::Relaxed) {
        return BOOL(1);
    }
    let f: unsafe extern "system" fn(i32, i32) -> BOOL = unsafe { std::mem::transmute(SET_CURSOR_POS.load(Ordering::Relaxed)) };
    unsafe { f(x, y) }
}

unsafe extern "system" fn clip_cursor(rect: *const RECT) -> BOOL {
    if BLOCK.load(Ordering::Relaxed) && !rect.is_null() {
        return BOOL(1);
    }
    let f: unsafe extern "system" fn(*const RECT) -> BOOL = unsafe { std::mem::transmute(CLIP_CURSOR.load(Ordering::Relaxed)) };
    unsafe { f(rect) }
}

fn hook(addr: *mut c_void, detour: *mut c_void, slot: &AtomicUsize) -> bool {
    match unsafe { MhHook::new(addr, detour) } {
        Ok(h) => {
            slot.store(h.trampoline() as usize, Ordering::Relaxed);
            unsafe { MH_EnableHook(addr) }.ok().is_ok()
        }
        Err(_) => false,
    }
}

fn hook_cursor() -> usize {
    let Ok(user32) = (unsafe { GetModuleHandleA(s!("user32.dll")) }) else { return 0 };
    let mut n = 0;
    for (name, detour, slot) in [
        (s!("SetCursorPos"), set_cursor_pos as *mut c_void, &SET_CURSOR_POS),
        (s!("ClipCursor"), clip_cursor as *mut c_void, &CLIP_CURSOR),
    ] {
        if let Some(addr) = unsafe { GetProcAddress(user32, name) } {
            n += hook(addr as *mut c_void, detour, slot) as usize;
        }
    }
    n
}

/// 游戏窗口（窗口消息带来的）
static GAME_WND: AtomicUsize = AtomicUsize::new(0);

pub fn set_window(h: HWND) {
    GAME_WND.store(h.0 as usize, Ordering::Relaxed);
}

/// 指针在游戏窗口里的位置（窗口坐标）。hudhook 把原始输入的相对位移和 WM_MOUSEMOVE 的绝对位置混着加，指针会飘，窗口开着时每帧用系统的位置校正
pub fn cursor_client() -> Option<[f32; 2]> {
    let h = GAME_WND.load(Ordering::Relaxed);
    if h == 0 {
        return None;
    }
    let mut p = POINT::default();
    unsafe {
        GetCursorPos(&mut p).ok()?;
        ScreenToClient(HWND(h as _), &mut p).as_bool().then_some([p.x as f32, p.y as f32])
    }
}

// ------------------------------------------------------------------ 输入框：打字时关掉输入法
#[link(name = "imm32", kind = "raw-dylib")]
unsafe extern "system" {
    fn ImmAssociateContext(h: HWND, c: isize) -> isize;
}

/// 正在往输入框里打字；窗口过程接管了没有；输入法现在关着、关之前的输入法上下文
static TYPING: AtomicBool = AtomicBool::new(false);
static OLD_PROC: AtomicUsize = AtomicUsize::new(0);
static IME_OFF: AtomicBool = AtomicBool::new(false);
static IME_PREV: AtomicIsize = AtomicIsize::new(0);

/// 接在窗口过程最前面（用户 2026-11-09「用拼音搜索」）：打字时把窗口的输入法摘掉，玩家开着中文输入法字母也直接进搜索框，打完还原。
/// 输入法的调用要在窗口所在的线程，所以放在这里。半个字符（emoji）不往下传（hudhook 处理 WM_CHAR 时会 panic）
unsafe extern "system" fn ime_proc(h: HWND, msg: u32, w: WPARAM, l: LPARAM) -> LRESULT {
    let typing = TYPING.load(Ordering::Relaxed);
    if typing != IME_OFF.load(Ordering::Relaxed) {
        IME_OFF.store(typing, Ordering::Relaxed);
        if typing {
            IME_PREV.store(unsafe { ImmAssociateContext(h, 0) }, Ordering::Relaxed);
        } else {
            unsafe { ImmAssociateContext(h, IME_PREV.load(Ordering::Relaxed)) };
        }
    }
    if typing && msg == WM_CHAR && (0xD800..0xE000).contains(&w.0) {
        return LRESULT(0);
    }
    let old = OLD_PROC.load(Ordering::Relaxed);
    if old == 0 {
        return unsafe { DefWindowProcW(h, msg, w, l) };
    }
    let old: WNDPROC = unsafe { std::mem::transmute(old) };
    unsafe { CallWindowProcW(old, h, msg, w, l) }
}

/// 每帧告诉这里在不在打字；第一次打字时才接管窗口过程（不用搜索的人完全不受影响）
pub fn set_typing(on: bool) {
    TYPING.store(on, Ordering::Relaxed);
    let h = GAME_WND.load(Ordering::Relaxed);
    if on && h != 0 && OLD_PROC.load(Ordering::Relaxed) == 0 {
        let old = unsafe { SetWindowLongPtrW(HWND(h as _), GWLP_WNDPROC, ime_proc as *const () as isize) };
        OLD_PROC.store(old as usize, Ordering::Relaxed);
    }
}

/// 窗口开着：解除光标限制（用原来的 ClipCursor，不经过钩子）
pub fn free_cursor() {
    let p = CLIP_CURSOR.load(Ordering::Relaxed);
    if p != 0 {
        let f: unsafe extern "system" fn(*const RECT) -> BOOL = unsafe { std::mem::transmute(p) };
        let _ = unsafe { f(std::ptr::null()) };
    }
}

// ------------------------------------------------------------------ 键鼠（DirectInput8）
static DEV_STATE: [AtomicUsize; 2] = [AtomicUsize::new(0), AtomicUsize::new(0)];
static DEV_DATA: [AtomicUsize; 2] = [AtomicUsize::new(0), AtomicUsize::new(0)];
static DEV_TYPES: Mutex<Vec<(usize, u8)>> = Mutex::new(Vec::new());
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
    BLOCK.load(Ordering::Relaxed) && matches!(dev_type(this), DI8DEVTYPE_MOUSE | DI8DEVTYPE_KEYBOARD)
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

/// 挂 DirectInput 设备的两个读取函数：自己建一个鼠标设备拿函数地址（A / W 两套接口各一次，地址一样的只挂一次）
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
    for (k, iid) in [IID_W, IID_A].iter().enumerate() {
        let mut di: *mut c_void = std::ptr::null_mut();
        if unsafe { create(hinst, 0x0800, iid, &mut di, std::ptr::null_mut()) } < 0 || di.is_null() {
            continue;
        }
        let mut dev: *mut c_void = std::ptr::null_mut();
        let cd: unsafe extern "system" fn(*mut c_void, *const GUID, *mut *mut c_void, *mut c_void) -> i32 = unsafe { std::mem::transmute(vfn(di, VT_CREATE_DEVICE)) };
        if unsafe { cd(di, &SYS_MOUSE, &mut dev, std::ptr::null_mut()) } >= 0 && !dev.is_null() {
            let targets: [(usize, *mut c_void, &AtomicUsize); 2] = [
                (unsafe { vfn(dev, VT_GET_STATE) }, if k == 0 { get_device_state::<0> as *mut c_void } else { get_device_state::<1> as *mut c_void }, &DEV_STATE[k]),
                (unsafe { vfn(dev, VT_GET_DATA) }, if k == 0 { get_device_data::<0> as *mut c_void } else { get_device_data::<1> as *mut c_void }, &DEV_DATA[k]),
            ];
            for (addr, detour, slot) in targets {
                if !done.contains(&addr) && hook(addr as *mut c_void, detour, slot) {
                    done.push(addr);
                }
            }
            let rel: unsafe extern "system" fn(*mut c_void) -> u32 = unsafe { std::mem::transmute(vfn(dev, VT_RELEASE)) };
            unsafe { rel(dev) };
        }
        let rel: unsafe extern "system" fn(*mut c_void) -> u32 = unsafe { std::mem::transmute(vfn(di, VT_RELEASE)) };
        unsafe { rel(di) };
    }
    done.len()
}

// ------------------------------------------------------------------ 手柄（XInput）
/// XINPUT_STATE
#[repr(C)]
#[derive(Debug, Default, Clone, Copy)]
pub struct XState {
    pub packet: u32,
    pub buttons: u16,
    pub lt: u8,
    pub rt: u8,
    pub lx: i16,
    pub ly: i16,
    pub rx: i16,
    pub ry: i16,
}

/// 原来的 XInputGetState（挂上了是跳板，没挂上就是它本身）
static XGET: AtomicUsize = AtomicUsize::new(0);

unsafe extern "system" fn xinput_get_state(user: u32, st: *mut XState) -> u32 {
    let f: unsafe extern "system" fn(u32, *mut XState) -> u32 = unsafe { std::mem::transmute(XGET.load(Ordering::Relaxed)) };
    let r = unsafe { f(user, st) };
    if r == 0 && !st.is_null() && BLOCK.load(Ordering::Relaxed) {
        let packet = unsafe { (*st).packet };
        unsafe { *st = XState { packet, ..XState::default() } };
    }
    r
}

/// 挂 xinput1_4.dll 的 XInputGetState；返回挂上没有（没挂上也记下原函数，界面照样能读手柄，只是挡不住游戏）
fn hook_xinput() -> bool {
    let Ok(x) = (unsafe { GetModuleHandleA(s!("xinput1_4.dll")) }) else { return false };
    let Some(addr) = (unsafe { GetProcAddress(x, s!("XInputGetState")) }) else { return false };
    XGET.store(addr as usize, Ordering::Relaxed);
    hook(addr as *mut c_void, xinput_get_state as *mut c_void, &XGET)
}

/// 界面自己读手柄：第一个连着的
pub fn read_pad() -> Option<XState> {
    let p = XGET.load(Ordering::Relaxed);
    if p == 0 {
        return None;
    }
    let f: unsafe extern "system" fn(u32, *mut XState) -> u32 = unsafe { std::mem::transmute(p) };
    (0..4).find_map(|u| {
        let mut st = XState::default();
        (unsafe { f(u, &mut st) } == 0).then_some(st)
    })
}

/// 挂所有钩子：(光标, 键鼠, 手柄)
pub fn install() -> (usize, usize, bool) {
    (hook_cursor(), hook_dinput(), hook_xinput())
}
