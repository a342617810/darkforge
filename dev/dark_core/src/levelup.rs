//! 开发工具「能力值调整」（最早是直接升一级的可行性测试，用户 2026-11-04 游戏里试过可行，许愿石升级 wishstone.rs 照这个做；原话：高难 Boss 掉的许愿石「提高1级等级」，「先看看能不能实现直接提升一级 不行就回退给卢恩」）：
//! 开发工具（dll\dark_dev「许愿石测试」）写 levelup_req.txt：「属性 <0~7> <+1|-1>」直接改人物这项属性（生命力、集中力、耐力、力气、灵巧、
//! 智力、信仰、感应）和等级（-1 用来撤销），「记录」只记一次。改之前、改后 1 秒、5 秒各记一次属性、等级、当前 / 最大 / 基础的血量、专注值、精力，
//! 看游戏自己会不会重算最大值（不会的话再看休息、读档以后）。日志开头「直接升级测试」。没有请求文件时什么都不做。

use std::fs;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::{GameDataMan, PlayerGameData};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

const REQ_FILE: &str = "levelup_req.txt";
const SCAN: Duration = Duration::from_millis(250);
/// 能力值的名字（同游戏升级界面；许愿石升级 wishstone.rs 也用）
pub(crate) const NAMES: [&str; 8] = ["生命力", "集中力", "耐力", "力气", "灵巧", "智力", "信仰", "感应"];

struct St {
    next: Instant,
    /// 改了以后要再记的时刻和原因
    later: Vec<(Instant, String)>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 第 k 项能力值（0 生命力 … 7 感应）
pub(crate) fn attr(p: &mut PlayerGameData, k: usize) -> Option<&mut u32> {
    Some(match k {
        0 => &mut p.vigor,
        1 => &mut p.mind,
        2 => &mut p.endurance,
        3 => &mut p.strength,
        4 => &mut p.dexterity,
        5 => &mut p.intelligence,
        6 => &mut p.faith,
        7 => &mut p.arcane,
        _ => return None,
    })
}

fn snap(p: &PlayerGameData) -> String {
    format!(
        "等级 {}，属性 生{} 集{} 耐{} 力{} 灵{} 智{} 信{} 感{}；血量 {}/{}（基础 {}），专注值 {}/{}（基础 {}），精力 {}/{}（基础 {}）",
        p.level, p.vigor, p.mind, p.endurance, p.strength, p.dexterity, p.intelligence, p.faith, p.arcane,
        p.current_hp, p.current_max_hp, p.base_max_hp, p.current_fp, p.current_max_fp, p.base_max_fp,
        p.current_stamina, p.current_max_stamina, p.base_max_stamina
    )
}

/// 一行请求 → 改了哪项（序号, 增减），看不懂返回 None
fn parse_req(line: &str) -> Option<(usize, i32)> {
    let f: Vec<&str> = line.split_whitespace().collect();
    match f.as_slice() {
        ["属性", k, d] => {
            let k: usize = k.parse().ok().filter(|&k| k < NAMES.len())?;
            let d: i32 = d.parse().ok().filter(|&d: &i32| d == 1 || d == -1)?;
            Some((k, d))
        }
        _ => None,
    }
}

pub fn tick() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St { next: now, later: Vec::new() });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let path = dir().join(REQ_FILE);
    let req = fs::read_to_string(&path).ok();
    if req.is_none() && st.later.is_empty() {
        return;
    }
    let Ok(gdm) = (unsafe { GameDataMan::instance_mut() }) else { return };
    let p: &mut PlayerGameData = &mut gdm.main_player_game_data;
    if p.level == 0 {
        return; // 还在主菜单
    }
    if let Some(text) = req {
        let _ = fs::remove_file(&path);
        for line in text.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')) {
            if line == "记录" {
                log(&format!("直接升级测试：现在 {}", snap(p)));
                continue;
            }
            let Some((k, d)) = parse_req(line) else {
                log(&format!("直接升级测试：看不懂「{line}」"));
                continue;
            };
            let before = snap(p);
            let Some(a) = attr(p, k) else { continue };
            let new = (*a as i32 + d).clamp(1, 99) as u32;
            if new == *a {
                log(&format!("直接升级测试：{} 已经是 {}，没改", NAMES[k], new));
                continue;
            }
            *a = new;
            p.level = (p.level as i32 + d).max(1) as u32;
            log(&format!("直接升级测试：{} {:+}（等级 {:+}）\n  改之前 {before}\n  刚改完 {}", NAMES[k], d, d, snap(p)));
            let why = format!("{} {:+}", NAMES[k], d);
            st.later.push((now + Duration::from_secs(1), format!("{why} 之后 1 秒")));
            st.later.push((now + Duration::from_secs(5), format!("{why} 之后 5 秒")));
        }
    }
    let due: Vec<String> = st.later.iter().filter(|(t, _)| *t <= now).map(|(_, w)| w.clone()).collect();
    st.later.retain(|(t, _)| *t > now);
    for w in due {
        log(&format!("直接升级测试：{w} {}", snap(p)));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_requests() {
        assert_eq!(parse_req("属性 0 1"), Some((0, 1)));
        assert_eq!(parse_req("属性 7 -1"), Some((7, -1)));
        assert_eq!(parse_req("属性 8 1"), None);
        assert_eq!(parse_req("属性 0 2"), None);
        assert_eq!(parse_req("记录"), None);
    }
}
