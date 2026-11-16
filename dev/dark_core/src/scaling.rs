//! 武器补正显示具体数值（settings 的 weapon_scaling_numbers，重随写 scaling.txt 才开）。
//! 游戏把数值印成文字的函数按格式码分支，格式码 0x64 那一支是补正：按 141 / 101 / 81 / 51 / 21 / 1 的门槛
//! 挑 Ｓ~Ｅ（GR_MenuText 11321~11326），不到 1 显示「-」。这一支改成和格式码 1 一样按「%.0f」印数字（不到 1 照旧「-」）：
//! 特征码现找（2.7.1.0 / 2.7.2.0 都离线核对过），就地改写这一支开头的 LEN 字节（这一支原来有 130 字节），跳回各分支共用的出口。
//! 超限（用户 2026-11-03：「超过原本上限之后变成金色」）：印字不直接调游戏的印字函数，先过 print_hook——数值是 GOLD 里的
//! （gear 每半秒算一次：背包里超限过的生成武器、补正超过原上限的那几项在面板上的数，见 workshop.rs 的 gold_tick），
//! 格式换成带金色 <font> 的「%.0f」，别的照原样。面板的文字框没开 HTML 位，但游戏设文字时照样认 <font>（物品名字的稀有度颜色就是这么显示的）。

use std::ffi::c_void;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Mutex, OnceLock};

use windows::Win32::System::Diagnostics::Debug::FlushInstructionCache;
use windows::Win32::System::Memory::{PAGE_EXECUTE_READWRITE, PAGE_PROTECTION_FLAGS, VirtualProtect};
use windows::Win32::System::Threading::GetCurrentProcess;

use crate::dir;
use crate::gear::aob_scan_unique;

const fn b(x: u8) -> Option<u8> {
    Some(x)
}
const W: Option<u8> = None;

/// cmp ax,0x64；jne 下一种格式；comiss xmm6,[Ｓ门槛]；jb 下一档；mov edx,11321（Ｓ）；call 造文字；jmp 出口
const GRADE: [Option<u8>; 31] = [
    b(0x66), b(0x83), b(0xF8), b(0x64), b(0x0F), b(0x85), W, W, W, W, b(0x0F), b(0x2F), b(0x35), W, W, W, W, b(0x72), b(0x0C),
    b(0xBA), b(0x39), b(0x2C), b(0x00), b(0x00), b(0xE8), W, W, W, W, b(0xEB), W,
];
/// 最后一档：comiss xmm6,[1.0]；jb 「-」
const LAST: [Option<u8>; 9] = [b(0x0F), b(0x2F), b(0x35), W, W, W, W, b(0x0F), b(0x82)];
/// 格式码 1 印整数那段：lea rdx,[「%.0f」]；call 印字；jmp 出口；cmp ax,2（下一种格式）
const FMT0: [Option<u8>; 21] =
    [b(0x48), b(0x8D), b(0x15), W, W, W, W, b(0xE8), W, W, W, W, b(0xE9), W, W, W, W, b(0x66), b(0x83), b(0xF8), b(0x02)];
const LEN: usize = 46;
/// 超过原上限的补正的颜色（同装备工坊「超限」页）
const GOLD_FMT_TEXT: &str = "<font color=\"#F0C850\">%.0f</font>";

/// 游戏的印字函数（out, 格式, 数值…，可变参数）
static PRINT: AtomicUsize = AtomicUsize::new(0);
static GOLD_FMT: OnceLock<Vec<u16>> = OnceLock::new();
/// 要印成金色的数（面板上的补正，未取整）
static GOLD: Mutex<Vec<f32>> = Mutex::new(Vec::new());

/// gear 每半秒更新一次（没有超限武器时是空的）
pub fn set_gold(v: Vec<f32>) {
    if let Ok(mut g) = GOLD.lock() {
        if *g != v {
            *g = v;
        }
    }
}

fn is_gold(v: f32) -> bool {
    GOLD.try_lock().is_ok_and(|g| g.iter().any(|&x| (x - v).abs() < 0.01))
}

/// 补正那一支印数字时调这里（参数和游戏的印字函数一样：数值是 double，可变参数在 xmm2 / r8 各一份，这里按 xmm2 收）
unsafe extern "C" fn print_hook(out: *mut c_void, fmt: *const u16, v: f64) -> usize {
    let f = match GOLD_FMT.get() {
        Some(g) if is_gold(v as f32) => g.as_ptr(),
        _ => fmt,
    };
    let print: unsafe extern "C" fn(*mut c_void, *const u16, ...) -> usize = unsafe { std::mem::transmute(PRINT.load(Ordering::Relaxed)) };
    unsafe { print(out, f, v) }
}

fn matches(at: usize, pat: &[Option<u8>]) -> bool {
    pat.iter().enumerate().all(|(j, p)| p.is_none_or(|x| unsafe { *((at + j) as *const u8) } == x))
}

/// at 处 4 字节相对位移、指令在 end 结束：目标地址
fn target(at: usize, end: usize) -> usize {
    (end as isize + unsafe { (at as *const i32).read_unaligned() } as isize) as usize
}

fn patch() -> Result<usize, String> {
    let g = aob_scan_unique(&GRADE).map_err(|e| format!("找补正分支：{e}"))?;
    let p = g + 10;
    let next = target(g + 6, g + 10);
    let end = (g as isize + 31 + unsafe { *((g + 30) as *const i8) } as isize) as usize;
    let last = (p..p + 0xA0).find(|&a| matches(a, &LAST)).ok_or("找不到最后一档")?;
    let (one, dash) = (target(last + 3, last + 7), target(last + 9, last + 13));
    let f = (g - 0x400..g).rev().find(|&a| matches(a, &FMT0)).ok_or("找不到印整数的那段")?;
    let (fmt, print) = (target(f + 3, f + 7), target(f + 8, f + 12));
    let s: Vec<u16> = (0..5).map(|k| unsafe { *((fmt + 2 * k) as *const u16) }).collect();
    if s != "%.0f\0".encode_utf16().collect::<Vec<_>>() || p + LEN > next || unsafe { *(one as *const f32) } != 1.0 {
        return Err("地址核对不上".into());
    }
    let r = |dst: usize, end: usize| ((dst as isize - end as isize) as i32).to_le_bytes();
    let mut code = Vec::with_capacity(LEN);
    code.extend([0x0F, 0x2F, 0x35]);
    code.extend(r(one, p + 7)); // comiss xmm6,[1.0]
    code.extend([0x0F, 0x82]);
    code.extend(r(dash, p + 13)); // jb 「-」
    code.extend([0xF3, 0x0F, 0x5A, 0xD6, 0x66, 0x49, 0x0F, 0x7E, 0xD0]); // cvtss2sd xmm2,xmm6；movq r8,xmm2
    code.extend([0x48, 0x8D, 0x15]);
    code.extend(r(fmt, p + 29)); // lea rdx,[「%.0f」]
    code.extend([0x48, 0xB8]);
    code.extend((print_hook as unsafe extern "C" fn(*mut c_void, *const u16, f64) -> usize as usize as u64).to_le_bytes()); // mov rax,print_hook
    code.extend([0xFF, 0xD0]); // call rax（同一个位置调，栈对齐、影子空间照旧）
    code.push(0xE9);
    code.extend(r(end, p + 46)); // jmp 出口
    debug_assert_eq!(code.len(), LEN);
    PRINT.store(print, Ordering::Relaxed);
    let _ = GOLD_FMT.set(GOLD_FMT_TEXT.encode_utf16().chain([0]).collect());
    unsafe {
        let mut old = PAGE_PROTECTION_FLAGS(0);
        VirtualProtect(p as *const _, LEN, PAGE_EXECUTE_READWRITE, &mut old).map_err(|e| format!("改内存属性：{e}"))?;
        std::ptr::copy_nonoverlapping(code.as_ptr(), p as *mut u8, LEN);
        let _ = VirtualProtect(p as *const _, LEN, old, &mut old);
        let _ = FlushInstructionCache(GetCurrentProcess(), Some(p as *const _), LEN);
    }
    Ok(p)
}

/// 启动时调一次；返回给加载日志的说明
pub fn install() -> String {
    if !dir().join("scaling.txt").exists() {
        return "补正显示数值（没开）".into();
    }
    let base = unsafe { windows::Win32::System::LibraryLoader::GetModuleHandleW(None) }.map(|h| h.0 as usize).unwrap_or(0);
    match patch() {
        Ok(p) => format!("补正显示数值（已改 eldenring.exe+{:#x}）", p - base),
        Err(e) => format!("补正显示数值（没改：{e}）"),
    }
}
