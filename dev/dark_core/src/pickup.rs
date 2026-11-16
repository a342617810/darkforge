//! 拾遗（护符，用户 2026-10-29）：戴着时自动拾取周围的地上物品和敌人掉落，不播拾取动作。
//! 参考 ErdTools（Nordgaren/Erd-Tools-CPP，GPL-3.0；我们包里也带着它，开着材料和遗失卢恩的自动拾取）的自动拾取：
//!   游戏判断「这个交互这一帧要不要执行」的函数 ExecuteActionButtonParam(交互管理器, 交互编号, …)，返回 true 就执行（= 按了交互键）。
//!   只有玩家进了这个交互的范围（ActionButtonParam 的半径 / 高度）才会走到这里。
//! 这里：
//!   - 挂钩：戴着时交互编号是物品类（ITEM_AB：地上物品、敌人掉落，编号表照 ErdTools）就直接返回 true，别的照原样往下走；
//!   - 范围：戴着时把这些交互的半径改成词条的米数、高度（和底面偏移）× HEIGHT_MULT，摘下还原；
//!   - 动作：戴着时 PlayerCommonParam 第 0 行「捡地上物品」的动作改成 NO_ANIM（不播；原版采集材料就是这个值），摘下还原。
//! 挂钩只改函数开头 5 字节（jmp 到旁边申请的中转），开头已经被别的 mod 用同样的方式挂过（ErdTools 用 MinHook）就接在它前面；
//! 我们先挂的话，之后 MinHook 也能把我们的 jmp 搬进它的跳板。第一次戴上时才挂（那时别的 mod 早就挂完了，不会同时改同一处）。
//! 函数有浮点参数（XMM0~2），判断前后用一小段汇编保存 / 还原（ErdTools 也是这么包的）。

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Mutex;

use eldenring::cs::{ActionButtonParam, PlayerCommonParam, SoloParamRepository};
use fromsoftware_shared::FromStatic;
use windows::Win32::System::Diagnostics::Debug::FlushInstructionCache;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Memory::{MEM_COMMIT, MEM_RESERVE, PAGE_EXECUTE_READWRITE, PAGE_PROTECTION_FLAGS, VirtualAlloc, VirtualProtect};
use windows::Win32::System::Threading::GetCurrentProcess;

use crate::log;

/// 物品类交互（ActionButtonParam 编号）：地上物品 + 尸体 / 敌人掉落 4100（照 ErdTools 的 ABParam_list_items / corpse_loot）
const ITEM_AB: [i32; 17] = [4000, 4100, 4110, 4200, 4201, 4202, 4250, 4251, 4252, 4253, 4260, 4270, 4280, 4300, 4350, 6361, 9532];
/// 高度、底面偏移放大倍数（坡上 / 台阶下的东西也够得着）
const HEIGHT_MULT: f32 = 2.0;
/// 不播拾取动作（原版 PlayerCommonParam 里采集材料的值）
const NO_ANIM: i32 = 999_999;
/// 两个游戏版本（2.7.1.0 / 2.7.2.0）里 ExecuteActionButtonParam 的位置：ErdTools 特征码的第一处命中（第二处是另一个函数，相隔 0xE0）
const RVAS: [usize; 2] = [0xa6_6f10, 0xa6_73d0];
/// 函数开头（ErdTools 的特征码，None = 通配）；开头 5 字节可能已被别的 mod 改成 jmp，从第 5 字节起核对
const SIG: [Option<u8>; 41] = [
    Some(0x48), Some(0x89), Some(0x5C), Some(0x24), Some(0x08), Some(0x57), Some(0x48), Some(0x81), Some(0xEC), Some(0x90),
    Some(0x00), Some(0x00), Some(0x00), Some(0x48), Some(0x8B), Some(0x84), Some(0x24), Some(0xE0), Some(0x00), Some(0x00),
    Some(0x00), Some(0x41), Some(0x0F), Some(0xB6), Some(0xD9), Some(0x48), Some(0x8B), Some(0x0D), None, None,
    None, None, Some(0x8B), Some(0xFA), Some(0x0F), Some(0x29), Some(0xB4), Some(0x24), Some(0x80), Some(0x00),
    Some(0x00),
];

/// 戴着拾遗（钩子看它）
static ON: AtomicBool = AtomicBool::new(false);
/// 钩子不管时往下走的地址（中转里的跳板：原来开头 5 字节 + 跳回，或者接着跳到先挂的 mod）
static NEXT: AtomicUsize = AtomicUsize::new(0);

// 钩子入口：保存参数寄存器和 XMM0~2，问 filter；-1 照原样往下走，否则直接返回它（1 = 执行）
std::arch::global_asm!(
    ".globl dr_pickup_hook",
    "dr_pickup_hook:",
    "push rcx",
    "push rdx",
    "push r8",
    "push r9",
    "sub rsp, 0x58",
    "movaps [rsp+0x20], xmm0",
    "movaps [rsp+0x30], xmm1",
    "movaps [rsp+0x40], xmm2",
    "mov ecx, edx",
    "call {filter}",
    "movaps xmm0, [rsp+0x20]",
    "movaps xmm1, [rsp+0x30]",
    "movaps xmm2, [rsp+0x40]",
    "add rsp, 0x58",
    "pop r9",
    "pop r8",
    "pop rdx",
    "pop rcx",
    "cmp eax, -1",
    "je 2f",
    "ret",
    "2:",
    "jmp qword ptr [rip + {next}]",
    filter = sym filter,
    next = sym NEXT,
);

unsafe extern "C" {
    fn dr_pickup_hook();
}

extern "C" fn filter(entry: i32) -> i32 {
    if ON.load(Ordering::Relaxed) && ITEM_AB.contains(&entry) { 1 } else { -1 }
}

#[derive(Default)]
struct St {
    /// 挂钩：None = 还没试过，Some(Ok) = 挂上了，Some(Err) = 挂不上（只写一次日志）
    hooked: Option<Result<(), String>>,
    /// 现在生效的半径（None = 没戴）
    radius: Option<f32>,
    /// 改之前的原值：交互编号 → (半径, 高度, 底面偏移)；拾取动作
    orig: HashMap<i32, (f32, f32, f32)>,
    orig_anim: Option<i32>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 函数开头（从第 5 字节起）对得上的那个版本的地址
fn find_target() -> Result<usize, String> {
    let base = unsafe { GetModuleHandleW(None) }.map(|h| h.0 as usize).map_err(|e| format!("取模块基址：{e}"))?;
    for rva in RVAS {
        let p = base + rva;
        let bytes = unsafe { std::slice::from_raw_parts(p as *const u8, SIG.len()) };
        let tail = bytes[5..].iter().zip(&SIG[5..]).all(|(b, s)| s.is_none_or(|s| s == *b));
        let head = bytes[..5].iter().zip(&SIG[..5]).all(|(b, s)| s.is_none_or(|s| s == *b)) || bytes[0] == 0xE9;
        if tail && head {
            return Ok(p);
        }
    }
    Err("两个版本的位置都对不上（游戏版本不对或者被别的 mod 改得更多）".into())
}

/// 在 target 前后 ±2GB 内申请一页可执行内存（5 字节 jmp 够得着）
pub(crate) fn alloc_near(target: usize) -> Option<usize> {
    let base = target & !0xFFFF;
    for k in 1..0x7000usize {
        for a in [base.wrapping_sub(k * 0x10000), base.wrapping_add(k * 0x10000)] {
            let p = unsafe { VirtualAlloc(Some(a as *const _), 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE) };
            if !p.is_null() {
                return Some(p as usize);
            }
        }
    }
    None
}

/// 绝对跳转 jmp [rip+0] + 地址（14 字节）
pub(crate) unsafe fn write_abs_jmp(at: usize, to: usize) {
    unsafe {
        std::ptr::copy_nonoverlapping([0xFF, 0x25, 0, 0, 0, 0].as_ptr(), at as *mut u8, 6);
        ((at + 6) as *mut usize).write_unaligned(to);
    }
}

fn install() -> Result<(), String> {
    let target = find_target()?;
    let block = alloc_near(target).ok_or("函数附近申请不到内存")?;
    let orig8 = unsafe { (target as *const u64).read() };
    let head = orig8.to_le_bytes();
    unsafe {
        // [0..14) 中转：跳到我们的钩子；[16..) 跳板：钩子不管时往下走
        write_abs_jmp(block, dr_pickup_hook as *const () as usize);
        let tramp = block + 16;
        if head[0] == 0xE9 {
            // 已经被别的 mod 挂过（5 字节 jmp）：跳板直接跳到它原来的去处
            let rel = i32::from_le_bytes([head[1], head[2], head[3], head[4]]);
            write_abs_jmp(tramp, (target + 5).wrapping_add_signed(rel as isize));
        } else {
            // 原样：跳板 = 原来开头 5 字节（mov [rsp+8], rbx，没有 rip 相对寻址）+ 跳回 target + 5
            std::ptr::copy_nonoverlapping(head.as_ptr(), tramp as *mut u8, 5);
            write_abs_jmp(tramp + 5, target + 5);
        }
        NEXT.store(tramp, Ordering::SeqCst);
        let rel = (block as isize - (target as isize + 5)) as i32;
        let mut new = head;
        new[0] = 0xE9;
        new[1..5].copy_from_slice(&rel.to_le_bytes());
        let mut old = PAGE_PROTECTION_FLAGS(0);
        VirtualProtect(target as *const _, 8, PAGE_EXECUTE_READWRITE, &mut old).map_err(|e| format!("改内存属性：{e}"))?;
        // 8 字节对齐的地址一次写完（别的线程不会看到写到一半的指令）
        std::sync::atomic::AtomicU64::from_ptr(target as *mut u64).store(u64::from_le_bytes(new), Ordering::SeqCst);
        let _ = VirtualProtect(target as *const _, 8, old, &mut old);
        let _ = FlushInstructionCache(GetCurrentProcess(), Some(target as *const _), 8);
    }
    let base = unsafe { GetModuleHandleW(None) }.map(|h| h.0 as usize).unwrap_or(0);
    log(&format!("拾遗：已挂上拾取判断（eldenring.exe+{:#x}，{}）", target - base, if head[0] == 0xE9 { "接在别的 mod 前面" } else { "原样" }));
    Ok(())
}

/// 改 / 还原交互范围和拾取动作；radius = None 是还原
fn apply_params(st: &mut St, radius: Option<f32>) -> Result<(), String> {
    let repo = unsafe { SoloParamRepository::instance_mut() }.map_err(|_| "参数还没载入".to_string())?;
    for id in ITEM_AB {
        let Some(row) = repo.get_mut::<ActionButtonParam>(id as u32) else { continue };
        let o = *st.orig.entry(id).or_insert((row.radius(), row.height(), row.base_height_offset()));
        match radius {
            Some(r) => {
                row.set_radius(r.max(o.0));
                row.set_height(o.1 * HEIGHT_MULT);
                row.set_base_height_offset(o.2 * HEIGHT_MULT);
            }
            None => {
                row.set_radius(o.0);
                row.set_height(o.1);
                row.set_base_height_offset(o.2);
            }
        }
    }
    if let Some(pc) = repo.get_mut::<PlayerCommonParam>(0) {
        let o = *st.orig_anim.get_or_insert(pc.anime_id_drop_item_pick());
        pc.set_anime_id_drop_item_pick(if radius.is_some() { NO_ANIM } else { o });
    }
    Ok(())
}

/// 每帧（runtime::tick）：radius = 戴着的拾遗的半径（米），没戴是 None。只在变了的时候动手
pub fn update(radius: Option<f32>) {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    if st.radius == radius {
        return;
    }
    if radius.is_some() && st.hooked.is_none() {
        let r = std::panic::catch_unwind(install).unwrap_or_else(|_| Err("挂钩时出错".into()));
        if let Err(e) = &r {
            log(&format!("拾遗：挂不上拾取判断，这个词条不起作用：{e}"));
        }
        st.hooked = Some(r);
    }
    if radius.is_some() && !st.hooked.as_ref().is_some_and(|r| r.is_ok()) {
        st.radius = radius;
        return;
    }
    match apply_params(st, radius) {
        Ok(()) => {
            ON.store(radius.is_some(), Ordering::Relaxed);
            log(&match radius {
                Some(r) => format!("拾遗：生效，半径 {r} 米（地上物品、敌人掉落，不播拾取动作）"),
                None => "拾遗：摘下，范围和拾取动作还原".to_string(),
            });
            st.radius = radius;
        }
        Err(e) => log(&format!("拾遗：改参数失败（下一帧再试）：{e}")),
    }
}
