//! 幻化插件（ertransmogrify）赐福菜单那一项加图标（用户 2026-11-10「给幻化装备的赐福菜单也加上图标吧」）。
//! 那一项不是我们赐福脚本加的：插件运行时改赐福对话脚本插进去，文字也不在文本表里——它挂钩游戏取文字的函数
//! MsgRepositoryImp 查条目（特征码 8B DA 44 8B CA 33 D2 48 8B F9 44 8D 42 6F 后面那条 call 的目标，和插件找的一样），
//! 对话文字（文本类别 33）69000000 直接返回它自己的字符串（反汇编插件 ertransmogrify.dll 0x21980 的分派表看的）。
//! 所以只能同样挂这个函数：插件挂完以后（开头是 jmp）我们接在它前面，先照常往下走拿到它的字符串，
//! 是 69000000 就在前面加上图标（和 launcher\reroll\sc\gracelook.py 的 ICON 一样的写法，图标用图集 SB_DR_Grace 里的
//! 「获得英雄的防具」方图），别的原样返回。插件没装 / 没挂上就什么都不做。
//! 拼好的字符串按插件返回的地址缓存（插件的字符串是常驻的，换语言地址才变），不会每次都重新分配。

use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use windows::Win32::System::Diagnostics::Debug::FlushInstructionCache;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Memory::{PAGE_EXECUTE_READWRITE, PAGE_PROTECTION_FLAGS, VirtualProtect};
use windows::Win32::System::Threading::GetCurrentProcess;
use windows::core::w;

use crate::log;
use crate::pickup::{alloc_near, write_abs_jmp};

/// 插件的「幻化防具」（赐福菜单那一项）
const TALK_BND: u32 = 33;
const TRANSMOG_TEXT: i32 = 69_000_000;
/// 和 gracelook.py 的 ICON % ours('MENU_FL_Armor_40171') 一样
const PREFIX: &str = "<img src='img://MENU_DR_FL_Armor_40171.png' height='36' width='36' vspace='-18'/> ";
/// 特征码后面第 14 字节是 call rel32（插件的 relative_offsets {1, 5}）
const AOB: [Option<u8>; 14] = [
    Some(0x8B), Some(0xDA), Some(0x44), Some(0x8B), Some(0xCA), Some(0x33), Some(0xD2), Some(0x48), Some(0x8B), Some(0xF9), Some(0x44),
    Some(0x8D), Some(0x42), Some(0x6F),
];

type LookupFn = unsafe extern "C" fn(usize, u32, u32, i32) -> *const u16;
static NEXT: AtomicUsize = AtomicUsize::new(0);
/// 插件返回的地址 → 加了图标的副本（结尾带 0）
static CACHE: Mutex<Vec<(usize, Box<[u16]>)>> = Mutex::new(Vec::new());

unsafe extern "C" fn detour(repo: usize, unk: u32, bnd: u32, id: i32) -> *const u16 {
    let next: LookupFn = unsafe { std::mem::transmute(NEXT.load(Ordering::Relaxed)) };
    let p = unsafe { next(repo, unk, bnd, id) };
    if bnd != TALK_BND || id != TRANSMOG_TEXT || p.is_null() {
        return p;
    }
    let Ok(mut c) = CACHE.try_lock() else { return p };
    if let Some((_, s)) = c.iter().find(|(k, _)| *k == p as usize) {
        return s.as_ptr();
    }
    let mut n = 0;
    while n < 512 && unsafe { *p.add(n) } != 0 {
        n += 1;
    }
    let orig = unsafe { std::slice::from_raw_parts(p, n) };
    let mut s: Vec<u16> = PREFIX.encode_utf16().collect();
    s.extend_from_slice(orig);
    s.push(0);
    c.push((p as usize, s.into_boxed_slice()));
    c.last().map(|(_, s)| s.as_ptr()).unwrap_or(p)
}

/// 特征码在游戏里有两处（exe+0xd11d4a / +0xd11dca，2.7.2.0 离线看的），都 call 同一个函数：所有命中的目标一致才用
fn target() -> Result<usize, String> {
    let base = unsafe { GetModuleHandleW(None) }.map_err(|e| format!("取模块基址：{e}"))?.0 as usize;
    let mut found: Option<usize> = None;
    unsafe {
        let pe = base + *((base + 0x3C) as *const u32) as usize;
        let nsec = *((pe + 6) as *const u16) as usize;
        let opt = *((pe + 20) as *const u16) as usize;
        for k in 0..nsec {
            let sh = pe + 24 + opt + 40 * k;
            if *((sh + 36) as *const u32) & 0x2000_0000 == 0 {
                continue;
            }
            let va = base + *((sh + 12) as *const u32) as usize;
            let size = *((sh + 8) as *const u32) as usize;
            let mem = std::slice::from_raw_parts(va as *const u8, size);
            for i in 0..size.saturating_sub(AOB.len() + 5) {
                if !AOB.iter().enumerate().all(|(j, p)| p.is_none_or(|b| mem[i + j] == b)) {
                    continue;
                }
                let at = i + AOB.len();
                if mem[at] != 0xE8 {
                    return Err(format!("特征码后面不是 call（{:#x}）", mem[at]));
                }
                let rel = i32::from_le_bytes([mem[at + 1], mem[at + 2], mem[at + 3], mem[at + 4]]);
                let t = (va + at + 5).wrapping_add_signed(rel as isize);
                match found {
                    Some(f) if f != t => return Err("几处命中 call 的函数不一样".into()),
                    _ => found = Some(t),
                }
            }
        }
    }
    found.ok_or_else(|| "没找到".into())
}

fn install(t: usize) -> Result<(), String> {
    let head = unsafe { (t as *const u64).read() }.to_le_bytes();
    // 只接在插件的 jmp 前面（插件没挂上不动手：原函数开头不搬）
    if head[0] != 0xE9 {
        return Err("取文字的函数还没被挂".into());
    }
    let block = alloc_near(t).ok_or("函数附近申请不到内存")?;
    let rel = i32::from_le_bytes([head[1], head[2], head[3], head[4]]);
    unsafe {
        write_abs_jmp(block, detour as *const () as usize);
        let tramp = block + 16;
        write_abs_jmp(tramp, (t + 5).wrapping_add_signed(rel as isize));
        NEXT.store(tramp, Ordering::SeqCst);
        let rel = (block as isize - (t as isize + 5)) as i32;
        let mut new = head;
        new[1..5].copy_from_slice(&rel.to_le_bytes());
        let mut old = PAGE_PROTECTION_FLAGS(0);
        VirtualProtect(t as *const _, 8, PAGE_EXECUTE_READWRITE, &mut old).map_err(|e| format!("改内存属性：{e}"))?;
        std::sync::atomic::AtomicU64::from_ptr(t as *mut u64).store(u64::from_le_bytes(new), Ordering::SeqCst);
        let _ = VirtualProtect(t as *const _, 8, old, &mut old);
        let _ = FlushInstructionCache(GetCurrentProcess(), Some(t as *const _), 8);
    }
    Ok(())
}

/// 后台线程：dark_core 比插件先加载（2026-11-10 日志：早 0.8 秒），先等插件加载、再等它挂好（最多 10 分钟，每 2 秒看一次）
pub fn start() {
    std::thread::spawn(|| {
        let mut t = None;
        let mut last = String::from("幻化插件没有加载");
        for _ in 0..300 {
            if unsafe { GetModuleHandleW(w!("ertransmogrify.dll")) }.is_ok() {
                if t.is_none() {
                    match target() {
                        Ok(a) => t = Some(a),
                        Err(e) => {
                            log(&format!("幻化菜单图标：找不到取文字的函数（{e}），不加"));
                            return;
                        }
                    }
                }
                match install(t.unwrap_or_default()) {
                    Ok(()) => {
                        log("幻化菜单图标：已接上");
                        return;
                    }
                    Err(e) => last = e,
                }
            }
            std::thread::sleep(Duration::from_secs(2));
        }
        log(&format!("幻化菜单图标：没接上（{last}），不加"));
    });
}
