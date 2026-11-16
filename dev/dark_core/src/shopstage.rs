//! 暗黑商店分阶段解锁的提示（参数侧 rr/darkshop.py stage_lines → shopstage.txt；用户 2026-11-04「每次解锁时提示“暗黑商店已经可以购买新物品”
//! 用魇火那个提示」）：商店行的上架标记就是各区域追忆 Boss 的击败标记，游戏自己上架；这里只看这些标记从灭变亮（打败了），
//! 弹原版闪烁提示（notes.rs 的 note 键）。进存档 / 换角色后 SETTLE 之后才开始记（读档时标记会变），以前打过的不补提示。
//! 定义 shopstage.txt：note <提示的键>；gate <击败标记> <区域键>（只列有东西上架的区域）

use std::collections::HashMap;
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::WorldChrMan;
use fromsoftware_shared::FromStatic;

use crate::gear::flag_get;
use crate::{dir, log};

const SCAN: Duration = Duration::from_millis(250);
/// 进存档多久以后才开始记击败标记（读档时标记会变）
const SETTLE: Duration = Duration::from_secs(3);

#[derive(Debug, Default, PartialEq)]
struct Def {
    note: String,
    /// (击败标记, 区域键)
    gates: Vec<(u32, String)>,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    for l in text.lines() {
        let f: Vec<&str> = l.trim_start_matches('\u{feff}').split_whitespace().collect();
        match f.as_slice() {
            ["note", key] => d.note = key.to_string(),
            ["gate", flag, key, ..] => {
                if let Ok(flag) = flag.parse() {
                    d.gates.push((flag, key.to_string()));
                }
            }
            _ => {}
        }
    }
    (!d.note.is_empty() && !d.gates.is_empty()).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("shopstage.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("暗黑商店分阶段解锁提示（{} 个区域）", d.gates.len()),
        None => "暗黑商店分阶段解锁提示（没有 shopstage.txt，不管）".into(),
    }
}

struct St {
    next: Instant,
    /// 进存档的时刻（SETTLE 之后才记）
    since: Option<Instant>,
    /// 击败标记上一次看到的状态
    seen: HashMap<u32, bool>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 上一次看到灭、这一次亮：刚打败
fn fresh(was: Option<bool>, on: bool) -> bool {
    on && was == Some(false)
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St { next: now, since: None, seen: HashMap::new() });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    if wcm.main_player.is_none() {
        st.since = None;
        st.seen.clear();
        return;
    }
    let since = *st.since.get_or_insert(now);
    if now - since < SETTLE {
        return;
    }
    for (flag, key) in &d.gates {
        let Some(on) = flag_get(*flag) else { continue };
        let was = st.seen.insert(*flag, on);
        if fresh(was, on) {
            log(&format!("暗黑商店分阶段解锁：{key} 的追忆 Boss（标记 {flag}）被击败，提示新物品上架"));
            crate::notes::push(&d.note);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_def() {
        let d = parse("# x\nnote shop\ngate 10000800 limgrave\ngate 14000800 liurnia\ngate x y\n").unwrap();
        assert_eq!(d.note, "shop");
        assert_eq!(d.gates, vec![(10000800, "limgrave".to_string()), (14000800, "liurnia".to_string())]);
        assert!(parse("gate 10000800 limgrave\n").is_none());
        assert!(parse("note shop\n").is_none());
    }

    #[test]
    fn only_fresh_defeats() {
        assert!(fresh(Some(false), true));
        assert!(!fresh(None, true)); // 刚开始记就亮着：以前打过的
        assert!(!fresh(Some(true), true));
        assert!(!fresh(Some(false), false));
    }
}
