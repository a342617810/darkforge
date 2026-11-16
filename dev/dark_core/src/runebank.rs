//! 卢恩银行（菜单 launcher\reroll\sc\runebank.py，用户 2026-11-10「可以存取身上的卢恩 然后要显示银行当前卢恩 同时注意存档问题」）：
//! - 余额 = 事件标记 BANK0 起 32 位（92600~92631，92000 块会存档）。和身上的卢恩都在存档里：游戏什么时候存、回档、崩溃，两边一起，
//!   不会出现「卢恩扣了余额没加」或者复制。改动都在这一帧的任务里做完（先算好新值，再一次写余额、写身上的卢恩）。
//! - 菜单把操作序号写进 OP0 起 3 位、点亮请求 REQ；这里处理完熄灭 REQ。没有可存取的点亮 NONE，一点都放不下点亮 FULL（放得下一部分就照放）。
//! - 余额行的占位 #IB：gear.rs confirm_tick 调 confirm_text。
//! 编号和 sc/runebank.py 一样（两边一起改；dev\event_flags\说明.md 登记了）。

use eldenring::cs::{GameDataMan, PlayerGameData};
use fromsoftware_shared::FromStatic;

use crate::gear::{flag_get, flag_set};
use crate::log;

const BANK0: u32 = 92600;
const BANK_BITS: u32 = 32;
const REQ: u32 = 92632;
const OP0: u32 = 92633;
const OP_BITS: u32 = 3;
const NONE: u32 = 92636;
const FULL: u32 = 92637;
/// 身上能带的上限（原版）
const HELD_MAX: u32 = 999_999_999;
/// 银行上限（32 位里留点余量）
const BANK_MAX: u32 = 4_000_000_000;

/// 读余额；有一位读不到（标记系统还没好）就是 None
fn balance() -> Option<u32> {
    let mut v = 0u32;
    for i in 0..BANK_BITS {
        if flag_get(BANK0 + i)? {
            v |= 1 << i;
        }
    }
    Some(v.min(BANK_MAX))
}

fn set_balance(v: u32) -> bool {
    (0..BANK_BITS).all(|i| flag_set(BANK0 + i, (v >> i) & 1 == 1))
}

/// 余额行的文字（中文, 英文）
pub(crate) fn confirm_text(pgd: &PlayerGameData) -> Option<(String, String)> {
    let b = balance()?;
    Some((format!("银行 {} / 身上 {}", group(b), group(pgd.rune_count)), format!("Bank {} / carried {}", group(b), group(pgd.rune_count))))
}

/// 千位分隔
fn group(v: u32) -> String {
    let s = v.to_string();
    let mut out = String::new();
    for (i, c) in s.chars().enumerate() {
        if i > 0 && (s.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    out
}

#[derive(Debug, PartialEq)]
enum Outcome {
    /// (新的身上卢恩, 新余额)
    Moved(u32, u32),
    Nothing,
    Full,
}

/// 操作 op 之后的（身上, 银行）：0 存全部、1 存一半、2 取全部、3 取一半、4 取 1 万、5 取 10 万
fn plan(op: u32, held: u32, bank: u32) -> Outcome {
    let held = held.min(HELD_MAX);
    let (deposit, want) = match op {
        0 => (true, held),
        1 => (true, held / 2),
        2 => (false, bank),
        3 => (false, bank / 2),
        4 => (false, 10_000.min(bank)),
        5 => (false, 100_000.min(bank)),
        _ => return Outcome::Nothing,
    };
    if want == 0 {
        return Outcome::Nothing;
    }
    let room = if deposit { BANK_MAX - bank.min(BANK_MAX) } else { HELD_MAX - held };
    let n = want.min(room);
    if n == 0 {
        return Outcome::Full;
    }
    if deposit { Outcome::Moved(held - n, bank + n) } else { Outcome::Moved(held + n, bank - n) }
}

/// 每帧看请求（同 wishstone.rs：菜单等回应的时间很短，不能节流）
pub fn tick() {
    if flag_get(REQ) != Some(true) {
        return;
    }
    let Ok(gdm) = (unsafe { GameDataMan::instance_mut() }) else { return };
    let p: &mut PlayerGameData = &mut gdm.main_player_game_data;
    if p.level == 0 {
        return; // 还在主菜单
    }
    let Some(bank) = balance() else { return };
    let op = (0..OP_BITS).filter(|&i| flag_get(OP0 + i) == Some(true)).fold(0u32, |v, i| v | (1 << i));
    match plan(op, p.rune_count, bank) {
        Outcome::Moved(held, nb) => {
            if set_balance(nb) {
                let old = p.rune_count;
                p.rune_count = held;
                log(&format!("卢恩银行：操作 {op}，身上 {old} → {held}，银行 {bank} → {nb}"));
            } else {
                // 写到一半失败：写回原值，卢恩不动
                set_balance(bank);
                flag_set(NONE, true);
                log("卢恩银行：写余额失败，没动卢恩");
            }
        }
        Outcome::Nothing => {
            flag_set(NONE, true);
        }
        Outcome::Full => {
            flag_set(FULL, true);
        }
    }
    flag_set(REQ, false);
}

pub fn describe() -> String {
    format!("卢恩银行（余额标记 {BANK0}~{}，请求 {REQ}）", BANK0 + BANK_BITS - 1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plans() {
        assert_eq!(plan(0, 500, 100), Outcome::Moved(0, 600));
        assert_eq!(plan(1, 501, 0), Outcome::Moved(251, 250));
        assert_eq!(plan(2, 10, 90), Outcome::Moved(100, 0));
        assert_eq!(plan(3, 0, 7), Outcome::Moved(3, 4));
        assert_eq!(plan(4, 0, 5_000), Outcome::Moved(5_000, 0));
        assert_eq!(plan(5, 0, 1_000_000), Outcome::Moved(100_000, 900_000));
        assert_eq!(plan(0, 0, 5), Outcome::Nothing);
        assert_eq!(plan(2, 5, 0), Outcome::Nothing);
        assert_eq!(plan(7, 5, 5), Outcome::Nothing);
        // 身上快满：只取放得下的
        assert_eq!(plan(2, HELD_MAX - 10, 100), Outcome::Moved(HELD_MAX, 90));
        assert_eq!(plan(2, HELD_MAX, 100), Outcome::Full);
        assert_eq!(plan(0, 100, BANK_MAX), Outcome::Full);
        assert_eq!(plan(0, 100, BANK_MAX - 30), Outcome::Moved(70, BANK_MAX));
    }

    #[test]
    fn grouping() {
        assert_eq!(group(0), "0");
        assert_eq!(group(999), "999");
        assert_eq!(group(1000), "1,000");
        assert_eq!(group(999_999_999), "999,999,999");
    }
}
