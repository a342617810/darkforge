//! 存档标记护栏（联机计划 13.2 G6 / 13.3 C7）：Seamless Co-op 的 FAQ 说会话里切换过的事件标记可能留在客机存档里，Seamless 自己也有
//! 一套标记管理（YKEventFlagMan）。我们有几样按角色存在存档标记里的数据，要是被房主那边的值盖掉，客机就会凭空多出 / 少掉卢恩、魇火等。
//! 做法：
//! - 不在会话里（大厅状态 0）、人物在场时每 SAMPLE 读一遍这些标记，连续 STABLE 次一样才算可靠的快照；
//! - 大厅状态一变（建会话 / 加入中 / 主机 / 客机……，Seamless 同步标记可能就在加入的时候）就把快照冻住：会话里人物在场时
//!   每 SAMPLE 对一遍，和快照不一样、又不是本机写的 → 改回快照的值（记日志）；
//! - 本机写的：dark_core 写标记都走 gear::flag_set，它调 own() 同时更新快照（卢恩银行存取、夺得魇火、咒痕碎片……照常）；
//!   难度档位（9950~9959）和高难度锁（93910）是赐福菜单的对话脚本 / dark_sell 写的：同时亮着难度请求标记（9960~9969，
//!   菜单选档时和档位一起点亮、公共事件处理完熄灭）或者 REQ_GRACE 内亮过，算本机在改，接受；
//! - 冻住时快照还不可靠（刚读档就进了会话）：这次不护，记一行；
//! - 离开会话（大厅状态回到 0）：最后再对一遍、改回，之后照常读快照。
//! 只管 dark_core 自己的这几段；免费许愿次数（93020~）dark_sell 另外记着，不管。

use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::log;

const SAMPLE: Duration = Duration::from_millis(500);
const STABLE: u8 = 2;
/// 难度请求熄灭后这么久之内档位变了，也算本机在改
const REQ_GRACE: Duration = Duration::from_secs(3);
/// 前这么多次改回逐个写日志，之后每次会话结束记个总数
const LOG_EACH: u32 = 20;

/// 护着的段：（第一个, 最后一个, 名字）
const RANGES: [(u32, u32, &str); 9] = [
    (92600, 92631, "卢恩银行余额"),
    (93616, 93633, "魇火"),
    (93911, 93992, "魇印次数 / 刻印位"),
    (93492, 93499, "魇印刻印位"),
    (93993, 93999, "咒痕碎片"),
    (92582, 92595, "咒痕碎片"),
    (93910, 93910, "高难度锁定"),
    (9950, 9959, "局内难度档位"),
    (93488, 93488, "馈赠用过"),
];
/// 也护着、但只是提示过没有（单独列，免得撑大上面的表）
const SINGLES: [(u32, &str); 2] = [(93677, "Boss 取回力量提示过"), (93686, "开场提示过")];
const DIFF: std::ops::RangeInclusive<u32> = 9950..=9959;
const LOCK: u32 = 93910;
const DIFF_REQ: std::ops::RangeInclusive<u32> = 9960..=9969;

pub fn guarded(f: u32) -> bool {
    RANGES.iter().any(|&(a, b, _)| (a..=b).contains(&f)) || SINGLES.iter().any(|&(x, _)| x == f)
}

fn name_of(f: u32) -> &'static str {
    RANGES.iter().find(|&&(a, b, _)| (a..=b).contains(&f)).map(|r| r.2).or_else(|| SINGLES.iter().find(|s| s.0 == f).map(|s| s.1)).unwrap_or("?")
}

fn all_flags() -> Vec<u32> {
    let mut v: Vec<u32> = RANGES.iter().flat_map(|&(a, b, _)| a..=b).chain(SINGLES.iter().map(|s| s.0)).collect();
    v.sort();
    v.dedup();
    v
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Mode {
    /// 不在会话里：读快照
    Offline,
    /// 会话里，护着
    Guard,
    /// 会话里，但进会话时快照不可靠，不护
    Off,
}

/// 判断逻辑（不碰游戏，单元测试用假的标记表）
pub struct Core {
    flags: Vec<u32>,
    snap: Vec<Option<bool>>,
    stable: u8,
    mode: Mode,
    req_seen: Option<Instant>,
    pub reverted: u32,
    logged: u32,
}

impl Core {
    pub fn new() -> Self {
        let flags = all_flags();
        let n = flags.len();
        Core { flags, snap: vec![None; n], stable: 0, mode: Mode::Offline, req_seen: None, reverted: 0, logged: 0 }
    }

    fn idx(&self, f: u32) -> Option<usize> {
        self.flags.binary_search(&f).ok()
    }

    /// 本机写了一个标记（gear::flag_set 调）：护着的就更新快照
    pub fn own(&mut self, f: u32, on: bool) {
        if let Some(i) = self.idx(f) {
            self.snap[i] = Some(on);
        }
    }

    /// 每 SAMPLE 一次。lobby = 大厅状态原始值（读不到 None 当 0）；in_world = 人物在场；get / set 读写游戏标记；
    /// 返回要写进日志的话
    pub fn step(&mut self, lobby: u32, in_world: bool, now: Instant, get: &dyn Fn(u32) -> Option<bool>,
                set: &mut dyn FnMut(u32, bool)) -> Vec<String> {
        let mut out = Vec::new();
        if lobby == 0 {
            if self.mode != Mode::Offline {
                if self.mode == Mode::Guard && in_world {
                    self.check(now, get, set, &mut out);
                }
                out.push(format!("存档标记护栏：离开会话{}", if self.mode == Mode::Guard {
                    format!("，这次会话改回了 {} 处外来改动", self.reverted)
                } else {
                    String::new()
                }));
                self.mode = Mode::Offline;
                self.stable = 0;
            }
            if !in_world {
                self.stable = 0;
                return out;
            }
            let cur: Vec<Option<bool>> = self.flags.iter().map(|&f| get(f)).collect();
            if cur.iter().any(|c| c.is_none()) {
                self.stable = 0;
                return out;
            }
            self.stable = if cur == self.snap { self.stable.saturating_add(1) } else { 0 };
            self.snap = cur;
            return out;
        }
        if self.mode == Mode::Offline {
            if self.stable >= STABLE {
                self.mode = Mode::Guard;
                self.reverted = 0;
                out.push(format!("存档标记护栏：进入会话（大厅状态 {lobby}），护着 {} 个标记", self.flags.len()));
            } else {
                self.mode = Mode::Off;
                out.push("存档标记护栏：进入会话时还没有可靠的快照（刚读档？），这次会话不护".into());
            }
        }
        if self.mode == Mode::Guard && in_world {
            self.check(now, get, set, &mut out);
        }
        out
    }

    fn check(&mut self, now: Instant, get: &dyn Fn(u32) -> Option<bool>, set: &mut dyn FnMut(u32, bool), out: &mut Vec<String>) {
        if DIFF_REQ.clone().any(|f| get(f) == Some(true)) {
            self.req_seen = Some(now);
        }
        let diff_ok = self.req_seen.is_some_and(|t| now.duration_since(t) <= REQ_GRACE);
        for i in 0..self.flags.len() {
            let f = self.flags[i];
            let (Some(cur), Some(want)) = (get(f), self.snap[i]) else { continue };
            if cur == want {
                continue;
            }
            if diff_ok && (DIFF.contains(&f) || f == LOCK) {
                self.snap[i] = Some(cur); // 本机在赐福菜单里换难度
                continue;
            }
            set(f, want);
            self.reverted += 1;
            if self.logged < LOG_EACH {
                self.logged += 1;
                out.push(format!("存档标记护栏：{}（标记 {f}）被改成了 {}，不是本机改的，改回 {}", name_of(f), cur as u8, want as u8));
            }
        }
    }
}

static CORE: Mutex<Option<Core>> = Mutex::new(None);
static NEXT: Mutex<Option<Instant>> = Mutex::new(None);

/// gear::flag_set 调：本机写的
pub fn own(f: u32, on: bool) {
    if !guarded(f) {
        return;
    }
    if let Some(c) = CORE.lock().unwrap_or_else(|e| e.into_inner()).as_mut() {
        c.own(f, on);
    }
}

pub fn tick() {
    let now = Instant::now();
    {
        let mut n = NEXT.lock().unwrap_or_else(|e| e.into_inner());
        if n.is_some_and(|t| now < t) {
            return;
        }
        *n = Some(now + SAMPLE);
    }
    let lobby = crate::coop::lobby().unwrap_or(0);
    let in_world = crate::coop::in_world();
    let get = |f: u32| crate::gear::flag_get(f);
    // 改回时直接写游戏（不走 gear::flag_set：那是「本机写的」）
    let mut set = |f: u32, on: bool| {
        crate::gear::flag_set_raw(f, on);
    };
    let lines = {
        let mut g = CORE.lock().unwrap_or_else(|e| e.into_inner());
        g.get_or_insert_with(Core::new).step(lobby, in_world, now, &get, &mut set)
    };
    for l in lines {
        log(&l);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::collections::HashMap;

    struct World(RefCell<HashMap<u32, bool>>);

    impl World {
        fn new() -> Self {
            World(RefCell::new(all_flags().into_iter().chain(DIFF_REQ).map(|f| (f, false)).collect()))
        }
        fn get(&self, f: u32) -> Option<bool> {
            self.0.borrow().get(&f).copied()
        }
        fn put(&self, f: u32, on: bool) {
            self.0.borrow_mut().insert(f, on);
        }
    }

    fn step(c: &mut Core, w: &World, lobby: u32, t: Instant) -> Vec<String> {
        let get = |f: u32| w.get(f);
        let mut set = |f: u32, on: bool| w.put(f, on);
        c.step(lobby, true, t, &get, &mut set)
    }

    #[test]
    fn foreign_change_in_session_is_reverted() {
        let (mut c, w, t) = (Core::new(), World::new(), Instant::now());
        w.put(92600, true); // 银行有一点余额
        step(&mut c, &w, 0, t);
        step(&mut c, &w, 0, t);
        step(&mut c, &w, 0, t);
        assert!(step(&mut c, &w, 6, t)[0].contains("护着"));
        w.put(92600, false); // 房主那边的值同步过来
        w.put(93616, true);
        let out = step(&mut c, &w, 6, t);
        assert_eq!(w.get(92600), Some(true));
        assert_eq!(w.get(93616), Some(false));
        assert_eq!(c.reverted, 2);
        assert!(out[0].contains("卢恩银行余额"));
    }

    #[test]
    fn own_writes_are_kept() {
        let (mut c, w, t) = (Core::new(), World::new(), Instant::now());
        for _ in 0..3 {
            step(&mut c, &w, 0, t);
        }
        step(&mut c, &w, 3, t);
        w.put(92601, true); // 卢恩银行存了钱（runebank.rs 经 gear::flag_set）
        c.own(92601, true);
        step(&mut c, &w, 3, t);
        assert_eq!(w.get(92601), Some(true));
        assert_eq!(c.reverted, 0);
    }

    #[test]
    fn difficulty_change_from_menu_is_kept() {
        let (mut c, w, t) = (Core::new(), World::new(), Instant::now());
        w.put(9950, true);
        for _ in 0..3 {
            step(&mut c, &w, 0, t);
        }
        step(&mut c, &w, 6, t);
        // 菜单换档：档位和请求一起亮
        w.put(9950, false);
        w.put(9952, true);
        w.put(9962, true);
        step(&mut c, &w, 6, t);
        w.put(9962, false); // 公共事件处理完熄灭请求
        step(&mut c, &w, 6, t + Duration::from_millis(500));
        assert_eq!((w.get(9950), w.get(9952)), (Some(false), Some(true)));
        // 没有请求的档位变化（房主的值）改回
        w.put(9952, false);
        w.put(9953, true);
        step(&mut c, &w, 6, t + Duration::from_secs(10));
        assert_eq!((w.get(9952), w.get(9953)), (Some(true), Some(false)));
    }

    #[test]
    fn no_reliable_snapshot_means_no_guard() {
        let (mut c, w, t) = (Core::new(), World::new(), Instant::now());
        step(&mut c, &w, 0, t); // 只读了一次
        assert!(step(&mut c, &w, 4, t)[0].contains("不护"));
        w.put(92600, true);
        step(&mut c, &w, 6, t);
        assert_eq!(w.get(92600), Some(true), "不护的会话里什么都不改");
    }

    #[test]
    fn leaving_session_checks_once_more_then_samples() {
        let (mut c, w, t) = (Core::new(), World::new(), Instant::now());
        for _ in 0..3 {
            step(&mut c, &w, 0, t);
        }
        step(&mut c, &w, 6, t);
        w.put(93910, true); // 离开会话的那一刻被同步了高难度锁
        let out = step(&mut c, &w, 0, t);
        assert_eq!(w.get(93910), Some(false));
        assert!(out.iter().any(|l| l.contains("离开会话")));
        // 之后本机自己点亮（离线）就是新的快照
        w.put(93910, true);
        step(&mut c, &w, 0, t);
        step(&mut c, &w, 0, t);
        step(&mut c, &w, 0, t);
        step(&mut c, &w, 6, t);
        step(&mut c, &w, 6, t);
        assert_eq!(w.get(93910), Some(true));
    }

    #[test]
    fn ranges_cover_expected() {
        assert!(guarded(92631) && guarded(93633) && guarded(93686) && guarded(9959) && guarded(93492));
        assert!(!guarded(92632) && !guarded(93020) && !guarded(9960) && !guarded(93501));
    }
}
