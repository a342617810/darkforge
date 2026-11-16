//! Boss 模组只在「死亡」以上难度加载（dev\boss_mods\README.md）。加不加载是启动时定的：Boss 的动作 / 行为 / AI 是读图时从硬盘读的，
//! 进了游戏换不了。启动器（界面）在存档里有「死亡」以上的角色时问玩家这次以哪种难度的世界启动（命令行启动按上次玩的角色）。这里：
//! 1. 进存档稳定几秒后，记下这个角色是不是「死亡」以上：
//!    - 角色记录\boss_slots.txt：每个存档格子一行（格子 / 是不是 / 时间 / 角色名），启动器弹框用（对过存档里的角色名才算）；
//!    - 角色记录\boss_mode.txt：最后玩的那个（slot / name / high / time），命令行启动用。联机时都在 角色记录\联机\。
//! 2. 启动器写的 bossmods.txt（auto 1、loaded 1/0、keys …）说这次是按难度定的，而读进来的角色对不上（「死亡」以上却是普通世界 /
//!    不是「死亡」以上却是改版世界）时：
//!    - 闪烁提示重启（notes 的「boss on」「boss off」）：一直对不上就一条接一条不停地提示（用户 2026-11-05「闪烁提示不要停」）；
//!    - 不是联机时在人物周围围上屏障、禁止传送（barrier.rs；联机的世界由房主定，只提示）。
//! 3. 对上了、又是「死亡」以上的改版世界：第一次（这个角色的标记 POWER_SEEN 没亮）提示「部分追忆Boss已经取回真正的力量」（notes 的
//!    「boss power」），之后不再提示（用户 2026-11-05「boss取回力量只在第一次时提示」）。
//! 「死亡」以上 = fusion.txt 的 lock 标记（「死亡」「不可能」的当前档）有一个亮着，和融锻之心掉落同一个判断。
//! 没有 bossmods.txt（功能关着 / 一个模组都没开）就什么都不做。
use std::fs;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use eldenring::cs::{GameDataMan, GameMan, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::gear::{flag_get, flag_set};
use crate::{barrier, dir, log};

/// 多久看一次（只读几个标记和角色名，很便宜；用户 2026-11-05「进入游戏到屏障放置还是隔了好多秒」：原来 2 秒）
const SCAN: Duration = Duration::from_millis(250);
/// 人物生成后等多久再看难度标记：难度的当前档标记跟着存档一起读进来，人物生成时已经是这个角色的了
/// （难度初始化事件只在一档都没亮时才补点亮「普通」）。原来保守地等 5 秒，进游戏 10 秒左右才围上屏障
const SETTLE: Duration = Duration::from_millis(500);
const REC: &str = "boss_mode.txt";
const SLOTS: &str = "boss_slots.txt";
/// 错配时的重启提示（notes 的键）：对上了、回到标题时把还在排队的删掉
const RESTART_NOTES: [&str; 2] = ["boss on", "boss off"];
/// 「部分追忆Boss已经取回真正的力量」提示过（会存档，每个角色自己的；dev\event_flags\说明.md）
const POWER_SEEN: u32 = 93677;

#[derive(Debug, Default, PartialEq)]
struct Def {
    auto: bool,
    loaded: bool,
    keys: Vec<String>,
    lock: Vec<u32>,
}

fn parse(launch: &str, fusion: &str) -> Option<Def> {
    let mut d = Def::default();
    let mut seen = false;
    for l in launch.lines() {
        let l = l.trim_start_matches('\u{feff}').trim();
        let mut it = l.split_whitespace();
        match it.next() {
            Some("auto") => d.auto = it.next() == Some("1"),
            Some("loaded") => d.loaded = it.next() == Some("1"),
            Some("keys") => {
                d.keys = it.map(String::from).collect();
                seen = true;
            }
            _ => {}
        }
    }
    for l in fusion.lines() {
        if let Some(rest) = l.trim_start_matches('\u{feff}').strip_prefix("lock ") {
            d.lock = rest.split_whitespace().filter_map(|x| x.parse().ok()).collect();
        }
    }
    (seen && !d.keys.is_empty() && !d.lock.is_empty()).then_some(d)
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| {
        let launch = fs::read_to_string(dir().join("bossmods.txt")).ok()?;
        parse(&launch, &fs::read_to_string(dir().join("fusion.txt")).unwrap_or_default())
    })
    .as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("高难度 Boss 改版（{}，这次{}加载：{}）", if d.auto { "按角色难度自动" } else { "固定" }, if d.loaded { "" } else { "没" }, d.keys.join("、")),
        None => "高难度 Boss 改版（没开）".into(),
    }
}

/// 角色记录的文件夹（同 gear.rs 的 data_dir：联机时是里面的 联机\）
fn rec_dir() -> PathBuf {
    let base = std::env::var_os("APPDATA").map(|a| PathBuf::from(a).join("EldenRing").join("DarkReforged").join("角色记录")).unwrap_or_else(dir);
    if crate::coop::ersc_loaded() { base.join("联机") } else { base }
}

fn rec_text(slot: i32, name: &str, high: bool, unix: u64) -> String {
    format!("slot\t{slot}\nname\t{name}\nhigh\t{}\ntime\t{unix}\n", u8::from(high))
}

/// boss_slots.txt：每个格子一行「格子<TAB>是不是死亡以上<TAB>时间<TAB>角色名」，按格子排；这个格子原来的那行换掉
fn slots_text(old: &str, slot: i32, name: &str, high: bool, unix: u64) -> String {
    let mut rows: Vec<(i32, String)> = old
        .lines()
        .map(|l| l.trim_start_matches('\u{feff}'))
        .filter(|l| !l.starts_with('#'))
        .filter_map(|l| l.split('\t').next().and_then(|s| s.parse::<i32>().ok()).map(|s| (s, l.to_string())))
        .filter(|(s, _)| *s != slot)
        .collect();
    rows.push((slot, format!("{slot}\t{}\t{unix}\t{name}", u8::from(high))));
    rows.sort_by_key(|r| r.0);
    let mut out = String::from("# 存档格子\t死亡以上（1 是）\t记下的时间（Unix 秒）\t角色名（dark_core 的 bossmode.rs 写，启动器对过存档里的角色名才用）\n");
    for (_, l) in rows {
        out.push_str(&l);
        out.push('\n');
    }
    out
}

/// 这次启动加载的和这个角色对不上时该提示哪一条
fn mismatch(d: &Def, high: bool) -> Option<&'static str> {
    if !d.auto || high == d.loaded {
        return None;
    }
    Some(if high { "boss on" } else { "boss off" })
}

#[derive(Default)]
struct St {
    next: Option<Instant>,
    /// 现在读进来的角色 + 从什么时候开始
    who: Option<((i32, String), Instant)>,
    written: Option<(i32, String, bool)>,
    /// 对不上、已经记过日志的角色（提示本身不停）
    told: Option<((i32, String, bool), Instant)>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 开了 Boss 改版（有 bossmods.txt）：咒痕的开场提示等这里认定世界对上了才放
pub fn active() -> bool {
    def().is_some()
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    let now = Instant::now();
    if st.next.is_some_and(|t| now < t) {
        return;
    }
    st.next = Some(now + SCAN);
    let in_world = unsafe { WorldChrMan::instance() }.ok().is_some_and(|w| w.main_player.is_some());
    if !in_world {
        st.who = None;
        barrier::set_wanted(false);
        crate::notes::forget(&RESTART_NOTES);
        return;
    }
    let Some(slot) = unsafe { GameMan::instance() }.ok().map(|g| g.save_slot).filter(|s| *s >= 0) else { return };
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return };
    let cn = &gdm.main_player_game_data.character_name;
    let len = cn.iter().position(|&c| c == 0).unwrap_or(cn.len());
    let name = String::from_utf16_lossy(&cn[..len]);
    if name.is_empty() {
        return;
    }
    let who = (slot, name);
    match &st.who {
        Some((w, _)) if *w == who => {}
        _ => {
            st.who = Some((who, now));
            barrier::set_wanted(false);
            return;
        }
    }
    let Some(((slot, name), since)) = st.who.clone() else { return };
    if now - since < SETTLE {
        return;
    }
    let high = d.lock.iter().any(|&f| flag_get(f) == Some(true));
    let key = (slot, name.clone(), high);
    if st.written.as_ref() != Some(&key) {
        let unix = SystemTime::now().duration_since(UNIX_EPOCH).map(|t| t.as_secs()).unwrap_or(0);
        let dirp = rec_dir();
        let old = fs::read_to_string(dirp.join(SLOTS)).unwrap_or_default();
        let ok = fs::create_dir_all(&dirp)
            .and_then(|_| fs::write(dirp.join(REC), rec_text(slot, &name, high, unix)))
            .and_then(|_| fs::write(dirp.join(SLOTS), slots_text(&old, slot, &name, high, unix)))
            .is_ok();
        log(&format!("高难度 Boss 改版：角色「{name}」（格子 {slot}）{}，{}", if high { "是「死亡」以上" } else { "不是「死亡」以上" },
                     if ok { "记下了（启动器下次启动时看）" } else { "记录写不进去" }));
        st.written = Some(key.clone());
    }
    let coop = crate::coop::ersc_loaded();
    match mismatch(d, high) {
        Some(note) => {
            barrier::set_wanted(!coop);
            if st.told.as_ref().is_none_or(|(k, _)| *k != key) {
                log(&format!("高难度 Boss 改版：这次启动{}加载，和角色「{name}」对不上，一直提示重启{}", if d.loaded { "" } else { "没" },
                             if coop { "（联机：不围屏障）" } else { "，围上屏障、禁止传送" }));
                st.told = Some((key, now));
            }
            // 不停地提示（用户 2026-11-05「错配时重启游戏的闪烁提示不要停」）：排队的都显示完了就再排一条，一条接一条
            if crate::notes::idle() {
                crate::notes::push(note);
            }
        }
        None => {
            barrier::set_wanted(false);
            st.told = None;
            crate::notes::forget(&RESTART_NOTES);
            if high {
                crate::curses::opening();
            }
            if high && d.loaded && flag_get(POWER_SEEN) == Some(false) && crate::notes::push("boss power") {
                flag_set(POWER_SEEN, true);
                log(&format!("高难度 Boss 改版：角色「{name}」第一次在改版世界里，提示追忆 Boss 取回了力量"));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_launch_and_lock() {
        let d = parse("# x\nauto 1\nloaded 0\nkeys godfrey messmer\n", "goods 9241\nlock 9956 9957\n").unwrap();
        assert_eq!(d, Def { auto: true, loaded: false, keys: vec!["godfrey".into(), "messmer".into()], lock: vec![9956, 9957] });
        // 没有开着的模组、没有档标记：不工作
        assert!(parse("auto 1\nloaded 0\nkeys\n", "lock 9956\n").is_none());
        assert!(parse("auto 1\nloaded 0\nkeys godfrey\n", "goods 1\n").is_none());
        assert!(parse("", "lock 9956\n").is_none());
    }

    #[test]
    fn mismatch_only_in_auto() {
        let mut d = Def { auto: true, loaded: false, keys: vec!["godfrey".into()], lock: vec![9956] };
        assert_eq!(mismatch(&d, true), Some("boss on"));
        assert_eq!(mismatch(&d, false), None);
        d.loaded = true;
        assert_eq!(mismatch(&d, false), Some("boss off"));
        assert_eq!(mismatch(&d, true), None);
        d.auto = false;
        assert_eq!(mismatch(&d, false), None);
    }

    #[test]
    fn record_format() {
        assert_eq!(rec_text(3, "褪色者", true, 7), "slot\t3\nname\t褪色者\nhigh\t1\ntime\t7\n");
    }

    #[test]
    fn slots_replace_and_sort() {
        let a = slots_text("", 3, "褪色者", true, 7);
        assert!(a.ends_with("3\t1\t7\t褪色者\n"));
        let b = slots_text(&a, 0, "甲", false, 9);
        let c = slots_text(&b, 3, "乙", false, 10);
        let rows: Vec<&str> = c.lines().filter(|l| !l.starts_with('#')).collect();
        assert_eq!(rows, vec!["0\t0\t9\t甲", "3\t0\t10\t乙"]);
    }
}
