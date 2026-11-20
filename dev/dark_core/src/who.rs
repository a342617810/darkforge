//! 角色身份（用户 2026-11-19「收拢」，dev\存档与角色记录.md 第 4 节）：「现在是哪个角色、认准了没有、是不是刚建的」只在这里判断，
//! 新装备（gear.rs）、骨灰（gear/ashes.rs）、Boss 难度（bossmode.rs）照这里的；dark_lock 的锁定名单经导出的 dr_who_fresh 知道。
//! - 身份 = (存档格子 GameMan.save_slot, 角色名)。标题画面（等级 0）没有身份；格子号是负的、名字还没读进来的那几帧照旧（不算换人）。
//! - 认准：人物在世界里（WorldChrMan.main_player）、身份连续 CONFIRM_FRAMES 帧没变。建新角色时游戏报的格子号还是上一个角色的
//!   （那时人物还没生成），认准之前谁都不写角色记录。
//! - 刚建的：认准那一刻这个角色的游戏时间不到 FRESH_MS（用户选「按游戏时间认」）。刚建的角色不接格子里原来的记录（不管同不同名，
//!   原来那份挪进 旧记录）：以前删掉「D」又建「D」、或者新角色被放进以前某个「D」用过的格子，会接着用旧「D」的配方，
//!   建角色界面看到的开局装备和进游戏后的对不上（2026-11-19 16:40，13 件里 6 件是旧的）。只用来认刚建的：崩溃回档不会把玩过的
//!   角色退回 3 分钟以内；会被当成刚建的老角色只有玩了不到 3 分钟就退出的，开局装备按现在抽的重记一次。

use std::sync::Mutex;

use eldenring::cs::{GameDataMan, GameMan, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::log;

/// 人物在场多少帧、身份没变才算认准（约 1 秒）
pub const CONFIRM_FRAMES: u32 = 60;
/// 认准时游戏时间不到这么久（毫秒）算刚建的
pub const FRESH_MS: u32 = 180_000;

/// 这一帧读到的
#[derive(Clone, Debug, Default, PartialEq)]
struct Input {
    /// 等级 0 = 标题画面
    level: u32,
    slot: i32,
    name: String,
    in_world: bool,
    play_ms: u32,
}

#[derive(Debug, PartialEq)]
enum Ev {
    None,
    /// 换了身份（含回到标题：None）
    Changed,
    /// 认准了：是不是刚建的、游戏时间
    Confirmed { fresh: bool, play_ms: u32 },
}

#[derive(Default)]
struct Tracker {
    cur: Option<(i32, String)>,
    frames: u32,
    confirmed: bool,
    fresh: bool,
    play_ms: u32,
    /// 换一次身份加一
    id_gen: u64,
    /// 认准过几个刚建的角色、最后一个的格子（dr_who_fresh）
    fresh_seq: u32,
    fresh_slot: i32,
}

impl Tracker {
    fn step(&mut self, i: &Input) -> Ev {
        if i.level == 0 {
            if self.cur.take().is_some() {
                self.reset();
                return Ev::Changed;
            }
            return Ev::None;
        }
        if i.slot < 0 || i.name.is_empty() {
            return Ev::None; // 读图时格子号、名字还没好：照旧，不数帧
        }
        let who = (i.slot, i.name.clone());
        if self.cur.as_ref() != Some(&who) {
            self.cur = Some(who);
            self.reset();
            return Ev::Changed;
        }
        if !i.in_world {
            return Ev::None;
        }
        self.frames = self.frames.saturating_add(1);
        if self.confirmed || self.frames < CONFIRM_FRAMES {
            return Ev::None;
        }
        self.confirmed = true;
        self.play_ms = i.play_ms;
        self.fresh = i.play_ms < FRESH_MS;
        if self.fresh {
            self.fresh_seq = self.fresh_seq.wrapping_add(1).max(1);
            self.fresh_slot = i.slot;
        }
        Ev::Confirmed { fresh: self.fresh, play_ms: i.play_ms }
    }

    fn reset(&mut self) {
        self.frames = 0;
        self.confirmed = false;
        self.fresh = false;
        self.play_ms = 0;
        self.id_gen = self.id_gen.wrapping_add(1);
    }
}

static T: Mutex<Option<Tracker>> = Mutex::new(None);

fn with<R>(f: impl FnOnce(&mut Tracker) -> R) -> R {
    f(T.lock().unwrap_or_else(|e| e.into_inner()).get_or_insert_with(Tracker::default))
}

fn read() -> Option<Input> {
    let gdm = unsafe { GameDataMan::instance() }.ok()?;
    let pgd = &gdm.main_player_game_data;
    let slot = unsafe { GameMan::instance() }.ok().map_or(-1, |g| g.save_slot);
    let len = pgd.character_name.iter().position(|&c| c == 0).unwrap_or(pgd.character_name.len());
    Some(Input {
        level: pgd.level,
        slot,
        name: String::from_utf16_lossy(&pgd.character_name[..len]),
        in_world: unsafe { WorldChrMan::instance() }.ok().is_some_and(|w| w.main_player.is_some()),
        play_ms: gdm.play_time,
    })
}

fn mmss(ms: u32) -> String {
    let s = ms / 1000;
    format!("{} 分 {} 秒", s / 60, s % 60)
}

/// 每帧最先调（lib.rs，在新装备系统前面）
pub fn tick() {
    let Some(i) = read() else { return };
    let ev = with(|t| t.step(&i));
    if let Ev::Confirmed { fresh, play_ms } = ev {
        log(&format!(
            "角色身份：认准格子 {}「{}」（游戏时间 {}）{}",
            i.slot,
            i.name,
            mmss(play_ms),
            if fresh { "，是刚建的角色：不接格子里原来的记录" } else { "" }
        ));
    }
}

/// 现在的身份（格子, 角色名）；标题画面是 None
pub fn current() -> Option<(i32, String)> {
    with(|t| t.cur.clone())
}

/// 认准了的身份（人物在世界里、稳定 CONFIRM_FRAMES 帧）
pub fn confirmed() -> Option<(i32, String)> {
    with(|t| t.cur.clone().filter(|_| t.confirmed))
}

/// 这个身份认准了没有
pub fn is_confirmed(who: &(i32, String)) -> bool {
    with(|t| t.confirmed && t.cur.as_ref() == Some(who))
}

/// 认准了、是刚建的角色 → 这个身份的编号（换一次身份变一次；各模块记下处理过的编号，同一个身份只处理一次）
pub fn fresh(who: &(i32, String)) -> Option<u64> {
    with(|t| (t.confirmed && t.fresh && t.cur.as_ref() == Some(who)).then_some(t.id_gen))
}

/// dark_lock 用：认准过的刚建角色的序号（0 = 还没有）和它的格子。序号变了就清掉那个格子的锁定名单
///
/// # Safety
/// slot 要能写一个 i32（可以是空指针，就不写）。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn dr_who_fresh(slot: *mut i32) -> u32 {
    let (seq, s) = with(|t| (t.fresh_seq, t.fresh_slot));
    if !slot.is_null() {
        unsafe { *slot = s };
    }
    seq
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inp(level: u32, slot: i32, name: &str, in_world: bool, play_ms: u32) -> Input {
        Input { level, slot, name: name.into(), in_world, play_ms }
    }

    fn run(t: &mut Tracker, i: &Input, n: u32) -> Vec<Ev> {
        (0..n).map(|_| t.step(i)).filter(|e| *e != Ev::None).collect()
    }

    /// 读老角色：人物在场满 60 帧认准，游戏时间长，不是刚建的；人物不在场的帧不数
    #[test]
    fn load_existing() {
        let mut t = Tracker::default();
        assert_eq!(t.step(&inp(30, 4, "D", false, 9_000_000)), Ev::Changed);
        assert!(run(&mut t, &inp(30, 4, "D", false, 9_000_000), 500).is_empty(), "人物还没生成：不数");
        assert!(run(&mut t, &inp(30, 4, "D", true, 9_000_000), CONFIRM_FRAMES - 1).is_empty());
        assert_eq!(t.step(&inp(30, 4, "D", true, 9_000_000)), Ev::Confirmed { fresh: false, play_ms: 9_000_000 });
        assert!(run(&mut t, &inp(30, 4, "D", true, 9_000_100), 100).is_empty(), "只认准一次");
        assert_eq!(t.fresh_seq, 0);
    }

    /// 建新角色：建角色时报的是上一个角色的格子（临时身份，人物没生成，认不准）；真正的格子出来、人物出现后认准，游戏时间短 → 刚建的
    #[test]
    fn create_new_after_playing() {
        let mut t = Tracker::default();
        run(&mut t, &inp(40, 1, "hghh", true, 17_000_000), 100);
        assert_eq!(t.step(&inp(0, 1, "hghh", false, 17_000_000)), Ev::Changed, "回到标题");
        assert_eq!(t.cur, None);
        assert_eq!(t.step(&inp(9, 1, "rrr", false, 0)), Ev::Changed, "建角色时的临时身份");
        assert!(run(&mut t, &inp(9, 1, "rrr", false, 0), 2000).is_empty(), "人物没生成：一直认不准");
        assert_eq!(t.step(&inp(9, 2, "rrr", false, 0)), Ev::Changed, "真正的格子");
        let g = t.id_gen;
        let evs = run(&mut t, &inp(9, 2, "rrr", true, 40_000), CONFIRM_FRAMES);
        assert_eq!(evs, vec![Ev::Confirmed { fresh: true, play_ms: 40_000 }]);
        assert_eq!((t.fresh_seq, t.fresh_slot, t.id_gen), (1, 2, g));
    }

    /// 读档时格子号、名字没好的帧不算换人；3 分钟整不算刚建的
    #[test]
    fn edges() {
        let mut t = Tracker::default();
        t.step(&inp(20, 3, "A", true, 0));
        let g = t.id_gen;
        assert_eq!(t.step(&inp(20, -1, "A", true, 0)), Ev::None);
        assert_eq!(t.step(&inp(20, 3, "", true, 0)), Ev::None);
        assert_eq!(t.id_gen, g);
        let evs = run(&mut t, &inp(20, 3, "A", true, FRESH_MS), CONFIRM_FRAMES);
        assert_eq!(evs, vec![Ev::Confirmed { fresh: false, play_ms: FRESH_MS }]);
    }
}
