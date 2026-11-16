//! 能施法的近战武器在面板上显示「魔法加成 / 祷告加成」（用户 2026-11-13「卡利亚魔法剑的魔法加成 … 可以改为显示到面板上吗」→「改 DLL 只动这把」）。
//! 游戏挑面板布局（MenuPropertyLayoutParam 的块）按「面板类型」：近战武器 19（块 2000，攻击力下面那一格是空的）、法杖 21（块 2300，
//! 那一格是「魔法加成」）、圣印记 22（块 2500，「祷告加成」）。算面板类型的函数（2.7.1.0 exe+0x847480，2.7.2.0 +0x4B0）对武器读
//! weaponCategory（参数 +0xE6）：类别 8（法杖 / 圣印记）再看能不能施魔法（+0x105 第 7 位）/ 祷告（+0x106 第 1 位）分 21 / 22，
//! 别的类别给 19。这里把「给 19」那一支（mov eax,0x13；jmp 出口）改成跳到我们的几条指令：武器能施魔法给 21、能施祷告给 22，
//! 否则照旧 19。原版里类别不是 8 又能施法的只有卡利亚魔法剑（2530000），新装备系统生成的同本体武器照样认。
//! 这个函数只有三处调用：两处只看结果是不是 15~18（法术），一处是建面板；道具栏的页签不用它，卡利亚魔法剑还在「近战武器」那一页。
//! 特征码：类别判断到各分支结尾这一段（145 字节，rel32 / 位移掩掉），2.7.1.0 / 2.7.2.0 离线核对过都只命中一处。

use windows::Win32::System::Diagnostics::Debug::FlushInstructionCache;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Memory::{PAGE_EXECUTE_READWRITE, PAGE_PROTECTION_FLAGS, VirtualProtect};
use windows::Win32::System::Threading::GetCurrentProcess;

use crate::gear::aob_scan_unique;
use crate::log;
use crate::pickup::{alloc_near, write_abs_jmp};

/// mov rcx,[rbp-28h]（武器参数行）；test；读 weaponCategory；减 8；超过 6 走默认；跳表；三个分支；类别 8 那段；mov eax,14h / 13h 两支
const PAT: &str = "48 8b 4d d8 48 85 c9 74 07 0f b6 99 e6 00 00 00 0f b6 c3 83 c0 f8 83 f8 06 77 ?? 48 98 48 8d 15 ?? ?? ?? ?? \
                   8b 84 82 ?? ?? ?? ?? 48 03 c2 ff e0 b8 17 00 00 00 e9 ?? ?? ?? ?? b8 1c 00 00 00 e9 ?? ?? ?? ?? b8 1d 00 00 00 \
                   e9 ?? ?? ?? ?? 48 85 c9 74 20 80 b9 05 01 00 00 80 73 17 0f b6 81 06 01 00 00 d0 e8 24 01 74 0a b8 16 00 00 00 \
                   e9 ?? ?? ?? ?? b8 15 00 00 00 e9 ?? ?? ?? ?? b8 14 00 00 00 e9 ?? ?? ?? ?? b8 13 00 00 00 e9 ?? ?? ?? ??";
/// 「mov eax,0x13（近战武器）；jmp 出口」在特征码里的位置
const DEFAULT_OFF: usize = 135;

fn parse(pat: &str) -> Vec<Option<u8>> {
    pat.split_whitespace().map(|t| if t == "??" { None } else { u8::from_str_radix(t, 16).ok() }).collect()
}

/// 跳过来时 rcx = 武器参数行（可能是空）。能施魔法 → 21（法杖布局），能施祷告 → 22（圣印记布局），否则 19；然后跳回原来的出口
fn cave(exit: usize) -> Vec<u8> {
    let mut c = vec![
        0x48, 0x85, 0xC9, // test rcx, rcx
        0x74, 0x20, // jz 默认
        0x80, 0xB9, 0x05, 0x01, 0x00, 0x00, 0x80, // cmp byte [rcx+0x105], 0x80（第 7 位 = 能施魔法）
        0x72, 0x07, // jb 看祷告
        0xB8, 0x15, 0x00, 0x00, 0x00, // mov eax, 21
        0xEB, 0x15, // jmp 出口
        0xF6, 0x81, 0x06, 0x01, 0x00, 0x00, 0x02, // test byte [rcx+0x106], 2（第 1 位 = 能施祷告）
        0x74, 0x07, // jz 默认
        0xB8, 0x16, 0x00, 0x00, 0x00, // mov eax, 22
        0xEB, 0x05, // jmp 出口
        0xB8, 0x13, 0x00, 0x00, 0x00, // 默认：mov eax, 19
        0xFF, 0x25, 0x00, 0x00, 0x00, 0x00, // 出口：jmp [rip+0]
    ];
    c.extend_from_slice(&(exit as u64).to_le_bytes());
    c
}

pub fn install() {
    match try_install() {
        Ok(msg) => log(&format!("能施法的近战武器显示魔法加成：{msg}")),
        Err(e) => log(&format!("能施法的近战武器显示魔法加成：没改（{e}）")),
    }
}

fn try_install() -> Result<String, String> {
    let hit = aob_scan_unique(&parse(PAT)).map_err(|e| format!("找面板类型的代码：{e}"))?;
    let target = hit + DEFAULT_OFF;
    let orig = unsafe { std::slice::from_raw_parts(target as *const u8, 10) };
    if orig[..6] != [0xB8, 0x13, 0x00, 0x00, 0x00, 0xE9] {
        return Err("那一支不是原样（被别的 mod 改过？）".into());
    }
    let rel = i32::from_le_bytes([orig[6], orig[7], orig[8], orig[9]]);
    let exit = (target + 10).wrapping_add_signed(rel as isize);
    let block = alloc_near(target).ok_or("附近申请不到内存")?;
    let code = cave(exit);
    unsafe {
        // 中转代码写好（最后的绝对跳转用 pickup 的写法再写一遍，确保格式一致）
        std::ptr::copy_nonoverlapping(code.as_ptr(), block as *mut u8, code.len());
        write_abs_jmp(block + code.len() - 14, exit);
        let mut old = PAGE_PROTECTION_FLAGS(0);
        VirtualProtect(target as *const _, 5, PAGE_EXECUTE_READWRITE, &mut old).map_err(|e| format!("改内存属性：{e}"))?;
        let jmp = (block as isize - (target as isize + 5)) as i32;
        let mut new = [0xE9u8, 0, 0, 0, 0];
        new[1..].copy_from_slice(&jmp.to_le_bytes());
        std::ptr::copy_nonoverlapping(new.as_ptr(), target as *mut u8, 5);
        let _ = VirtualProtect(target as *const _, 5, old, &mut old);
        let _ = FlushInstructionCache(GetCurrentProcess(), Some(target as *const _), 5);
    }
    let base = unsafe { GetModuleHandleW(None) }.map(|h| h.0 as usize).unwrap_or(0);
    Ok(format!("已改 eldenring.exe+{:#x}", target - base))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pattern_shape() {
        let p = parse(PAT);
        assert_eq!(p.len(), 145);
        assert_eq!(&p[DEFAULT_OFF..DEFAULT_OFF + 6], &[Some(0xB8), Some(0x13), Some(0), Some(0), Some(0), Some(0xE9)]);
    }

    /// 各个短跳转落在对的地方：jz 默认 → 默认段；jb → 看祷告；两个 jmp → 出口
    #[test]
    fn cave_jumps() {
        let c = cave(0x1122_3344_5566_7788);
        assert_eq!(c.len(), 56);
        let land = |at: usize| at + 2 + c[at + 1] as usize;
        let (default, chk, out) = (37, 21, 42);
        assert_eq!(&c[default..default + 5], &[0xB8, 0x13, 0, 0, 0]);
        assert_eq!(&c[chk..chk + 2], &[0xF6, 0x81]);
        assert_eq!(&c[out..out + 2], &[0xFF, 0x25]);
        assert_eq!(land(3), default, "武器参数是空");
        assert_eq!(land(12), chk, "不能施魔法 → 看祷告");
        assert_eq!(land(19), out);
        assert_eq!(land(28), default, "也不能施祷告");
        assert_eq!(land(35), out);
        assert_eq!(&c[14..19], &[0xB8, 0x15, 0, 0, 0], "法杖布局 21");
        assert_eq!(&c[30..35], &[0xB8, 0x16, 0, 0, 0], "圣印记布局 22");
        assert_eq!(u64::from_le_bytes(c[48..56].try_into().unwrap()), 0x1122_3344_5566_7788);
    }
}
