//! Dark Reforged 第五个护符槽（dark_slot）：把游戏里没用上的「誓约」装备槽打开，当第五个护符槽用。
//! 做法照 Golden Age 3.6.8 带的 eldenring_covenant_slot 0.1.2 逆向出来的四处改动（它按 exe 的 SHA-256 只认 2.7.0.0 / 2.7.1.0，
//! 2.7.2.0 上拒绝加载，所以重写一个两版都认的）：
//!   - 槽位可用：一个按槽位类型（对象第 0 字节）跳转的函数表，第 24 项（誓约槽）原来指向「xor al,al；ret」，
//!     改成第 23 项那个「mov al,1；ret」；
//!   - 数据：exe .data 里三组 {…, FLT_MAX, 0}，最后一组的 0 改成 FLT_MAX（照抄原 mod，含义没深究）；
//!   - 装备筛选（选装备时列哪些物品）：函数开头 hook，第 2 个参数 0x28（誓约槽）换成 0x27（第 4 个护符槽）；
//!   - 181 处定时检查（mov ecx,编号；call 取随机间隔；…；jb 跳过这次检查）的 jb 改成 jmp，检查就不跑了
//!     （检查函数在 exe 的第二个加密 .text 里，照抄原 mod）。
//! hook 点、函数表、181 处跳转按特征码现找；数据位置按版本写死，版本由 hook 点的 RVA 认。
//! 加载 5 秒后（同原 mod）全部核对，有一项对不上就一项都不改，只写 dark_slot.log。
//! 认 eldenring.exe 2.7.1.0 / 2.7.2.0：dev\vendor\port_tools\verify_slot.py 照这里的逻辑在两个 exe 上离线核对过。

use std::fs;
use std::panic::catch_unwind;
use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::Duration;

use windows::Win32::Foundation::HMODULE;
use windows::Win32::System::Diagnostics::Debug::FlushInstructionCache;
use windows::Win32::System::LibraryLoader::{GetModuleFileNameW, GetModuleHandleW};
use windows::Win32::System::Memory::{
    MEM_COMMIT, MEM_RESERVE, PAGE_EXECUTE_READWRITE, PAGE_PROTECTION_FLAGS, VirtualAlloc, VirtualProtect,
};
use windows::Win32::System::Threading::GetCurrentProcess;

static DIR: OnceLock<PathBuf> = OnceLock::new();

fn log(msg: &str) {
    use std::io::Write;
    let dir = DIR.get().cloned().unwrap_or_else(|| PathBuf::from("."));
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(dir.join("dark_slot.log")) {
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

struct Version {
    name: &'static str,
    hook: usize,  // 装备筛选函数
    entry: usize, // 函数表第 24 项（核对特征码找到的表）
    data: usize,  // FLT_MAX 那项；+8 是要改的 0
}

const VERSIONS: [Version; 2] = [
    Version { name: "2.7.1.0（1.17.1）", hook: 0x8505C0, entry: 0x3B39020, data: 0x3B35008 },
    Version { name: "2.7.2.0（1.17.2）", hook: 0x850A70, entry: 0x3B3C030, data: 0x3B38008 },
];

const W: Option<u8> = None;
const fn b(x: u8) -> Option<u8> {
    Some(x)
}

/// 调筛选函数的地方：lea r9,[r11-48]；lea edx,[rcx+28]；lea r8d,[rcx+15]；mov rcx,rbx；call 筛选
const HOOK_SITE: [Option<u8>; 15] = [
    b(0x4D), b(0x8D), b(0x4B), b(0xB8), b(0x8D), b(0x51), b(0x28), b(0x44), b(0x8D), b(0x41), b(0x15), b(0x48), b(0x8B), b(0xCB), b(0xE8),
];
/// 筛选函数开头：mov r11,rsp；mov [r11+20],r9；mov [r11+8],rcx；push rbp/rsi/rdi；sub rsp,…（前 12 字节搬进跳板）
const HOOK_HEAD: [u8; 16] = [0x4C, 0x8B, 0xDC, 0x4D, 0x89, 0x4B, 0x20, 0x49, 0x89, 0x4B, 0x08, 0x55, 0x56, 0x57, 0x48, 0x81];
const STOLEN: usize = 12;
/// 槽位可用：movsx rax,byte [rcx]；lea rcx,[表]；jmp [rcx+rax*8]
const DISPATCH: [Option<u8>; 15] = [b(0x48), b(0x0F), b(0xBE), b(0x01), b(0x48), b(0x8D), b(0x0D), W, W, W, W, b(0x48), b(0xFF), b(0x24), b(0xC1)];
const SLOT: usize = 24;
const RET_TRUE: [u8; 3] = [0xB0, 0x01, 0xC3];
const RET_FALSE: [u8; 3] = [0x32, 0xC0, 0xC3];
const FLT_MAX: u64 = 0x7F7F_FFFF;
const BRANCHES: usize = 181;
const JB: u8 = 0x72;
const JMP: u8 = 0xEB;

/// exe 第一个 .text（exe 有两个，第二个是加密段）
unsafe fn text(base: usize) -> Result<&'static [u8], String> {
    unsafe {
        let pe = base + *((base + 0x3C) as *const u32) as usize;
        let nsec = *((pe + 6) as *const u16) as usize;
        let sec0 = pe + 24 + *((pe + 20) as *const u16) as usize;
        for s in 0..nsec {
            let sh = sec0 + 40 * s;
            if std::slice::from_raw_parts(sh as *const u8, 8) == b".text\0\0\0" {
                let va = base + *((sh + 12) as *const u32) as usize;
                let size = *((sh + 8) as *const u32) as usize;
                return Ok(std::slice::from_raw_parts(va as *const u8, size));
            }
        }
        Err("找不到 .text".into())
    }
}

fn find_unique(t: &[u8], pat: &[Option<u8>]) -> Result<usize, String> {
    let mut hits = (0..t.len().saturating_sub(pat.len())).filter(|&i| pat.iter().enumerate().all(|(j, p)| p.is_none_or(|x| t[i + j] == x)));
    let first = hits.next().ok_or("没找到")?;
    if hits.next().is_some() {
        return Err("命中不止一处".into());
    }
    Ok(first)
}

/// b9 ???? e8 ???? f3 0f 11 05 [4-132] 72 ? 48 8d：每个起点都试，中间跳过的字节取最短（同原 mod 用的 pelite 扫描）；
/// 已经是 eb（被别的东西改过）的也认，免得往后错找到下一段的 jb
fn branches(t: &[u8]) -> Vec<usize> {
    let mut out = Vec::new();
    for i in 0..t.len().saturating_sub(150) {
        if t[i] != 0xB9 || t[i + 5] != 0xE8 || t[i + 10..i + 14] != [0xF3, 0x0F, 0x11, 0x05] {
            continue;
        }
        if let Some(j) = (i + 18..=i + 146).find(|&j| (t[j] == JB || t[j] == JMP) && t[j + 2] == 0x48 && t[j + 3] == 0x8D) {
            out.push(j);
        }
    }
    out
}

fn rel32(at: usize, end: usize) -> usize {
    (end as isize + unsafe { (at as *const i32).read_unaligned() } as isize) as usize
}

unsafe fn bytes(at: usize, n: usize) -> &'static [u8] {
    unsafe { std::slice::from_raw_parts(at as *const u8, n) }
}

unsafe fn write_code(at: usize, code: &[u8]) -> Result<(), String> {
    unsafe {
        let mut old = PAGE_PROTECTION_FLAGS(0);
        VirtualProtect(at as *const _, code.len(), PAGE_EXECUTE_READWRITE, &mut old).map_err(|e| format!("改内存属性：{e}"))?;
        std::ptr::copy_nonoverlapping(code.as_ptr(), at as *mut u8, code.len());
        let _ = VirtualProtect(at as *const _, code.len(), old, &mut old);
        let _ = FlushInstructionCache(GetCurrentProcess(), Some(at as *const _), code.len());
    }
    Ok(())
}

/// .data 里对齐的 8 字节：一条 mov 写完，游戏同时读也读不到一半
unsafe fn write_u64(at: usize, v: u64) -> Result<(), String> {
    unsafe {
        let mut old = PAGE_PROTECTION_FLAGS(0);
        VirtualProtect(at as *const _, 8, PAGE_EXECUTE_READWRITE, &mut old).map_err(|e| format!("改内存属性：{e}"))?;
        (at as *mut u64).write_volatile(v);
        let _ = VirtualProtect(at as *const _, 8, old, &mut old);
    }
    Ok(())
}

/// 跳板：cmp edx,0x28；jne +5；mov edx,0x27；原来开头 12 字节；jmp [rip] → 筛选函数 +12
fn stub(hook: usize) -> Result<usize, String> {
    let mut code = vec![0x83, 0xFA, 0x28, 0x75, 0x05, 0xBA, 0x27, 0x00, 0x00, 0x00];
    code.extend_from_slice(&HOOK_HEAD[..STOLEN]);
    code.extend_from_slice(&[0xFF, 0x25, 0, 0, 0, 0]);
    code.extend_from_slice(&(hook + STOLEN).to_le_bytes());
    let p = unsafe { VirtualAlloc(None, code.len(), MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE) } as *mut u8;
    if p.is_null() {
        return Err("VirtualAlloc 失败".into());
    }
    unsafe { std::ptr::copy_nonoverlapping(code.as_ptr(), p, code.len()) };
    Ok(p as usize)
}

fn install() -> Result<String, String> {
    let base = unsafe { GetModuleHandleW(None) }.map_err(|e| format!("GetModuleHandle：{e}"))?.0 as usize;
    install_at(base)
}

/// base = 内存里 eldenring.exe 的基址（测试时是按原基址映射的 exe 文件）
fn install_at(base: usize) -> Result<String, String> {
    let t = unsafe { text(base)? };
    let tva = t.as_ptr() as usize;

    // 全部先核对
    let site = tva + find_unique(t, &HOOK_SITE).map_err(|e| format!("装备筛选调用点特征码{e}"))?;
    let hook = rel32(site + 15, site + 19);
    let Some(v) = VERSIONS.iter().find(|v| base + v.hook == hook) else {
        return Err(format!("游戏版本不是 2.7.1.0 / 2.7.2.0（装备筛选在 exe+{:#x}）", hook - base));
    };
    let head = unsafe { bytes(hook, HOOK_HEAD.len()) };
    if head != HOOK_HEAD {
        return Err(format!("装备筛选函数开头对不上（{head:02x?}），可能已经装了别的第五护符槽 mod（比如 Golden Age 的 eldenring_covenant_slot）"));
    }
    let d = tva + find_unique(t, &DISPATCH).map_err(|e| format!("槽位可用函数表特征码{e}"))?;
    let table = rel32(d + 7, d + 11);
    let entry = table + SLOT * 8;
    if entry != base + v.entry {
        return Err(format!("槽位可用函数表位置对不上（exe+{:#x}）", entry - base));
    }
    let on = unsafe { *((entry - 8) as *const usize) };
    let cur = unsafe { *(entry as *const usize) };
    if unsafe { bytes(on, 3) } != RET_TRUE {
        return Err("函数表第 23 项不是「返回 true」".into());
    }
    let slot_done = cur == on;
    if !slot_done && unsafe { bytes(cur, 3) } != RET_FALSE {
        return Err(format!("函数表第 24 项既不是原来的「返回 false」也不是改好的（exe+{:#x}）", cur.wrapping_sub(base)));
    }
    let src = base + v.data;
    let dst = src + 8;
    let (sv, dv) = unsafe { (*(src as *const u64), *(dst as *const u64)) };
    if sv != FLT_MAX || (dv != 0 && dv != FLT_MAX) {
        return Err(format!("数据对不上（exe+{:#x} = {sv:#x}，+8 = {dv:#x}）", v.data));
    }
    let br = branches(t);
    let mut uniq = br.clone();
    uniq.sort_unstable();
    uniq.dedup();
    if br.len() != BRANCHES || uniq.len() != br.len() {
        return Err(format!("定时检查找到 {} 处（应为 {BRANCHES} 处、互不相同）", br.len()));
    }
    let todo: Vec<usize> = br.iter().copied().filter(|&o| t[o] == JB).collect();

    // 再改：先建跳板（唯一可能失败的分配），最后挂 hook
    let s = stub(hook)?;
    unsafe {
        if dv == 0 {
            write_u64(dst, FLT_MAX)?;
        }
        if !slot_done {
            write_u64(entry, on as u64)?;
        }
        for &o in &todo {
            write_code(tva + o, &[JMP])?;
        }
        let mut patch = [0u8; STOLEN];
        patch[0] = 0x48;
        patch[1] = 0xB8;
        patch[2..10].copy_from_slice(&s.to_le_bytes());
        patch[10] = 0xFF;
        patch[11] = 0xE0;
        write_code(hook, &patch)?;
    }
    let mut already = Vec::new();
    if dv != 0 {
        already.push("数据");
    }
    if slot_done {
        already.push("槽位可用");
    }
    if todo.len() < BRANCHES {
        already.push("部分定时检查");
    }
    let note = if already.is_empty() { String::new() } else { format!("；原来就改过的：{}", already.join("、")) };
    Ok(format!(
        "eldenring.exe {}：第五个护符槽已打开（装备筛选 exe+{:#x}，槽位可用 exe+{:#x}，数据 exe+{:#x}，定时检查改了 {}/{BRANCHES} 处{note}）",
        v.name,
        hook - base,
        entry - base,
        v.data + 8,
        todo.len()
    ))
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
        std::thread::sleep(Duration::from_secs(5));
        match catch_unwind(install) {
            Ok(Ok(msg)) => log(&format!("dark_slot 已加载：{msg}")),
            Ok(Err(e)) => log(&format!("dark_slot 不工作（什么都没改）：{e}")),
            Err(_) => log("dark_slot 不工作：核对时出错"),
        }
    });
    1
}

/// 离线测试：把 exe 文件按原基址（0x140000000）映射进测试进程，在映射上跑 install_at，再核对改了的字节。
/// 默认两个 exe 都测（本机 2.7.1.0 + ER_new 的 2.7.2.0），可用环境变量 DARK_SLOT_EXES（分号隔开）换。
/// cargo test --release --offline -- --nocapture --test-threads=1
#[cfg(test)]
mod tests {
    use super::*;
    use windows::Win32::System::Memory::{MEM_RELEASE, PAGE_READWRITE, VirtualFree};

    const EXES: &str = r"E:\SteamLibrary\steamapps\common\ELDEN RING\Game\eldenring.exe;C:\Users\dxphh\ER_new\Game\eldenring.exe";

    fn u16_at(d: &[u8], o: usize) -> usize {
        u16::from_le_bytes([d[o], d[o + 1]]) as usize
    }
    fn u32_at(d: &[u8], o: usize) -> usize {
        u32::from_le_bytes(d[o..o + 4].try_into().unwrap()) as usize
    }

    /// 按节表把文件铺到 ImageBase（不做重定位：表里的函数指针是按 0x140000000 写死的）
    unsafe fn map(path: &str) -> usize {
        let d = fs::read(path).unwrap();
        let pe = u32_at(&d, 0x3C);
        let opt = pe + 24;
        let image_base = u64::from_le_bytes(d[opt + 24..opt + 32].try_into().unwrap()) as usize;
        let size = u32_at(&d, opt + 56);
        let p = unsafe { VirtualAlloc(Some(image_base as *const _), size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE) } as usize;
        assert_eq!(p, image_base, "映射不到 {image_base:#x}");
        unsafe { std::ptr::copy_nonoverlapping(d.as_ptr(), p as *mut u8, u32_at(&d, opt + 60)) };
        let sec0 = opt + u16_at(&d, pe + 20);
        for s in 0..u16_at(&d, pe + 6) {
            let sh = sec0 + 40 * s;
            let (vs, va, rs, raw) = (u32_at(&d, sh + 8), u32_at(&d, sh + 12), u32_at(&d, sh + 16), u32_at(&d, sh + 20));
            let n = rs.min(vs.max(rs));
            unsafe { std::ptr::copy_nonoverlapping(d.as_ptr().add(raw), (p + va) as *mut u8, n) };
        }
        p
    }

    #[test]
    fn both_versions() {
        let exes = std::env::var("DARK_SLOT_EXES").unwrap_or_else(|_| EXES.into());
        for path in exes.split(';').filter(|p| !p.is_empty()) {
            let base = unsafe { map(path) };
            let t = unsafe { text(base) }.unwrap();
            let before = branches(t);
            let msg = install_at(base).unwrap_or_else(|e| panic!("{path}：{e}"));
            println!("{path}\n  {msg}");
            let v = VERSIONS.iter().find(|v| msg.contains(v.name)).unwrap();
            unsafe {
                // hook：mov rax,跳板；jmp rax，跳板 = cmp/jne/mov + 原来 12 字节 + jmp [rip] 回 +12
                let hook = base + v.hook;
                assert_eq!(bytes(hook, 2), [0x48, 0xB8]);
                assert_eq!(bytes(hook + 10, 2), [0xFF, 0xE0]);
                let s = *((hook + 2) as *const usize);
                assert_eq!(bytes(s, 10), [0x83, 0xFA, 0x28, 0x75, 0x05, 0xBA, 0x27, 0x00, 0x00, 0x00]);
                assert_eq!(bytes(s + 10, STOLEN), &HOOK_HEAD[..STOLEN]);
                assert_eq!(bytes(s + 22, 6), [0xFF, 0x25, 0, 0, 0, 0]);
                assert_eq!(*((s + 28) as *const usize), hook + STOLEN);
                assert_eq!(bytes(hook + STOLEN, 4), &HOOK_HEAD[STOLEN..]);
                // 函数表第 24 项 = 第 23 项（返回 true）
                let e = base + v.entry;
                assert_eq!(*(e as *const usize), *((e - 8) as *const usize));
                assert_eq!(bytes(*(e as *const usize), 3), RET_TRUE);
                // 数据
                assert_eq!(*((base + v.data + 8) as *const u64), FLT_MAX);
                assert_eq!(*((base + v.data) as *const u64), FLT_MAX);
                // 181 处 jb → jmp，偏移不变
                let after = branches(text(base).unwrap());
                assert_eq!(before, after);
                assert!(after.iter().all(|&o| t[o] == JMP));
            }
            // 再装一次：开头已经是我们的 hook → 拒绝、什么都不改
            let again = install_at(base).unwrap_err();
            println!("  再装一次：{again}");
            assert!(again.contains("开头对不上"));
            unsafe { VirtualFree(base as *mut _, 0, MEM_RELEASE).unwrap() };
        }
    }
}
