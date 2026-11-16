//! 仿身泪滴复制召唤者（用户 2026-11-10「仿身泪滴的装备没正确继承」→「原版的没问题」）：
//! 游戏写死了「这一组召唤参数里有 20700000 那一行（原版仿身泪滴的银色泪滴）」才复制召唤者的装备和属性——
//! eldenring.exe 里两处 `cmp dword [..], 0x13bdb60`（2.7.x 都一样，按特征码找）：
//!   A：生成召唤物时扫这一组召唤参数（[rax+0x50] 是行号），有这一行就打开「复制召唤者」；
//!   B：查某个召唤物所在的组（[rcx+0x1c] 是行号），是不是这一行（大概是左边血条不显示银色泪滴这些）。
//! 骨灰容器的召唤参数是自己的行号，所以容器里的仿身穿的是默认装备、血量也是模板的。
//! 这里把两处的「cmp + je」（9 字节）换成跳到旁边申请的一小段：原来的比较照做，再逐个比每个专用容器的第一行
//! （银色泪滴那一行：专用容器那一段 [lo, hi) 里每 PER 行的第一行，ashes.txt 的 mimic 行，rr/ashcont.py），然后跳回原来的两个去处。
//! 只认第一行、不认整段（2026-11-10 第一版整段都认：仿身本体在「查召唤物」那处也被当成银色泪滴，左边血条不对）。
//! 进存档时改一次，之后不再动。

use std::sync::atomic::{AtomicU8, Ordering};

use windows::Win32::System::Diagnostics::Debug::FlushInstructionCache;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Memory::{PAGE_EXECUTE_READWRITE, PAGE_PROTECTION_FLAGS, VirtualProtect};
use windows::Win32::System::Threading::GetCurrentProcess;

use crate::log;
use crate::pickup::alloc_near;

/// 0 没改、1 改好了、2 改不了（特征码对不上之类）
static STATE: AtomicU8 = AtomicU8::new(0);

/// 原版仿身泪滴银色泪滴那一行的召唤参数编号
const MIMIC_ROW: u32 = 20_700_000;

/// 一处判断：特征码、cmp 在特征码里的位置、比较的那个字段（cmp 指令里 0x81 后面的 ModRM + 位移）
struct Site {
    name: &'static str,
    sig: &'static [u8],
    at: usize,
    /// 81 <modrm> <disp8>：A = 78 50（[rax+0x50]），B = 79 1c（[rcx+0x1c]）
    modrm: [u8; 2],
}
/// 最多认几个专用容器（中转一段 0x100 字节，每个比较 13 字节）
const MAX_ROWS: usize = 15;

const SITES: [Site; 2] = [
    Site {
        name: "生成召唤物",
        sig: &[0x81, 0x78, 0x50, 0x60, 0xdb, 0x3b, 0x01, 0x74, 0x0a, 0x48, 0x8b, 0x00, 0x49, 0x3b, 0xc6, 0x75, 0xef, 0xeb, 0x04],
        at: 0,
        modrm: [0x78, 0x50],
    },
    Site {
        name: "查召唤物",
        sig: &[0x4c, 0x39, 0x41, 0x10, 0x75, 0x09, 0x81, 0x79, 0x1c, 0x60, 0xdb, 0x3b, 0x01, 0x74, 0x58, 0x48, 0x8b, 0x09, 0x48, 0x3b, 0xca, 0x75, 0xe9],
        at: 6,
        modrm: [0x79, 0x1c],
    },
];

/// 主程序代码段（.text）的起止
fn text_range() -> Option<(usize, usize)> {
    let base = unsafe { GetModuleHandleW(None) }.ok()?.0 as usize;
    unsafe {
        let pe = base + (*((base + 0x3c) as *const u32)) as usize;
        let nsec = *((pe + 6) as *const u16) as usize;
        let opt = *((pe + 20) as *const u16) as usize;
        for i in 0..nsec {
            let s = pe + 24 + opt + 40 * i;
            let name = std::slice::from_raw_parts(s as *const u8, 8);
            if name.starts_with(b".text") {
                let vsz = *((s + 8) as *const u32) as usize;
                let va = *((s + 12) as *const u32) as usize;
                return Some((base + va, base + va + vsz));
            }
        }
    }
    None
}

fn find(sig: &[u8], (lo, hi): (usize, usize)) -> Vec<usize> {
    let text = unsafe { std::slice::from_raw_parts(lo as *const u8, hi - lo) };
    text.windows(sig.len()).enumerate().filter(|(_, w)| *w == sig).map(|(i, _)| lo + i).collect()
}

/// 一处的中转代码：原来那一行和每个专用容器的第一行逐个比（cmp dword [字段], 行号; je 命中），都不是就跳回 miss
fn cave(s: &Site, ids: &[u32], hit: usize, miss: usize) -> Vec<u8> {
    let mut c = Vec::new();
    let mut jes = Vec::new();
    for id in std::iter::once(MIMIC_ROW).chain(ids.iter().copied()) {
        c.extend([0x81, s.modrm[0], s.modrm[1]]);
        c.extend(id.to_le_bytes());
        c.extend([0x0f, 0x84, 0, 0, 0, 0]);
        jes.push(c.len());
    }
    c.extend([0xff, 0x25, 0, 0, 0, 0]);
    c.extend((miss as u64).to_le_bytes());
    let hit_at = c.len();
    c.extend([0xff, 0x25, 0, 0, 0, 0]);
    c.extend((hit as u64).to_le_bytes());
    for j in jes {
        c[j - 4..j].copy_from_slice(&((hit_at - j) as i32).to_le_bytes());
    }
    c
}

/// 改好了没有（没改好时仿身泪滴不换成容器，免得穿默认装备）
pub(super) fn ok() -> bool {
    STATE.load(Ordering::Relaxed) == 1
}

/// 进存档时调（只改一次）：rows = 仿身泪滴专用容器的召唤参数 [lo, hi)，per = 每个容器几行（第一行是银色泪滴）
pub(super) fn install(rows: (u32, u32), per: u32) {
    if STATE.load(Ordering::Relaxed) != 0 {
        return;
    }
    let r = (|| -> Result<String, String> {
        let text = text_range().ok_or("找不到主程序的代码段")?;
        let mut at = Vec::new();
        for s in &SITES {
            let hits = find(s.sig, text);
            if hits.len() != 1 {
                return Err(format!("「{}」那处特征码找到 {} 处（应该 1 处；游戏版本不对或者被别的 mod 改过）", s.name, hits.len()));
            }
            at.push(hits[0] + s.at);
        }
        let block = alloc_near(at[0]).ok_or("附近申请不到内存")?;
        let ids: Vec<u32> = (rows.0..rows.1).step_by(per.max(1) as usize).take(MAX_ROWS).collect();
        let base = unsafe { GetModuleHandleW(None) }.map(|h| h.0 as usize).unwrap_or(0);
        let mut done = Vec::new();
        for (k, (s, &p)) in SITES.iter().zip(&at).enumerate() {
            // cmp（7）+ je rel8（2）：命中去 p + 9 + rel8，没命中接着 p + 9
            let rel8 = unsafe { *((p + 8) as *const i8) } as isize;
            let (hit, miss) = ((p + 9).wrapping_add_signed(rel8), p + 9);
            let code = cave(s, &ids, hit, miss);
            let c = block + 0x100 * k;
            let rel = c as isize - (p as isize + 5);
            if i32::try_from(rel).is_err() {
                return Err("申请到的内存离得太远".into());
            }
            let mut patch = [0x90u8; 9];
            patch[0] = 0xe9;
            patch[1..5].copy_from_slice(&(rel as i32).to_le_bytes());
            unsafe {
                std::ptr::copy_nonoverlapping(code.as_ptr(), c as *mut u8, code.len());
                let mut old = PAGE_PROTECTION_FLAGS(0);
                VirtualProtect(p as *const _, 9, PAGE_EXECUTE_READWRITE, &mut old).map_err(|e| format!("改内存属性：{e}"))?;
                std::ptr::copy_nonoverlapping(patch.as_ptr(), p as *mut u8, 9);
                let _ = VirtualProtect(p as *const _, 9, old, &mut old);
                let _ = FlushInstructionCache(GetCurrentProcess(), Some(p as *const _), 9);
            }
            done.push(format!("{} exe+{:#x}", s.name, p - base));
        }
        Ok(done.join("、"))
    })();
    match r {
        Ok(at) => {
            STATE.store(1, Ordering::Relaxed);
            let ids: Vec<u32> = (rows.0..rows.1).step_by(per.max(1) as usize).take(MAX_ROWS).collect();
            log(&format!("骨灰：仿身泪滴判断改好了（{at}）：召唤参数 {MIMIC_ROW} 和专用容器的银色泪滴那一行 {ids:?} 都算（复制召唤者的装备和属性）"));
        }
        Err(e) => {
            STATE.store(2, Ordering::Relaxed);
            log(&format!("骨灰：仿身泪滴的判断没改成：{e}；仿身泪滴先不换成容器（换了会穿默认装备）"));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 中转代码：原来那一行 + 每个专用容器的第一行逐个比，je 都跳到命中那一段；没命中跳回原来的下一条
    #[test]
    fn cave_layout() {
        let c = cave(&SITES[0], &[39900876, 39900882], 0x1111_2222_3333, 0x4444_5555_6666);
        assert_eq!(c.len(), 3 * 13 + 28);
        for (k, id) in [20_700_000u32, 39900876, 39900882].into_iter().enumerate() {
            let at = 13 * k;
            assert_eq!(&c[at..at + 3], &[0x81, 0x78, 0x50]);
            assert_eq!(u32::from_le_bytes(c[at + 3..at + 7].try_into().unwrap()), id);
            assert_eq!(&c[at + 7..at + 9], &[0x0f, 0x84]);
            let to = at + 13 + i32::from_le_bytes(c[at + 9..at + 13].try_into().unwrap()) as usize;
            assert_eq!(to, c.len() - 14, "je 跳到命中");
        }
        assert_eq!(u64::from_le_bytes(c[c.len() - 8..].try_into().unwrap()), 0x1111_2222_3333);
        assert_eq!(u64::from_le_bytes(c[c.len() - 22..c.len() - 14].try_into().unwrap()), 0x4444_5555_6666, "没命中跳回");
        let b = cave(&SITES[1], &[1], 3, 4);
        assert_eq!(&b[..3], &[0x81, 0x79, 0x1c]);
        assert!(13 * (MAX_ROWS + 1) + 28 <= 0x100, "一段放得下");
    }
}
