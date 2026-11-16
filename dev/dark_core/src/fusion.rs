//! 融锻之心的 Boss 掉落（参数侧 rr/bosses.py fusion_lines；用户 2026-11-04「追忆boss按照难度从5个开始 依次+5掉落 其余boss不掉落融锻之心
//! 然后进入死亡难度以上才是按照现在的boss掉落」）。以前放在 Boss 的掉落表里，掉落表管不了难度，改成这里看击败标记发：
//! - 平时（lock 档的当前档标记都灭着）：只有追忆 Boss 战给（rem 行，按难度第 k 名给 5k 个）；
//! - 「死亡」「不可能」（lock 档有一个亮着）：所有 Boss 战都给（boss 行，数量同龙心脏）。
//! 击败标记从灭变亮、这一种的「给过」标记还没亮，就发货（gear 的 gift_n，游戏里弹「获得物品」）并点亮它：平时、死亡以上各一次（两档合起来一次）。
//! 进存档、换了平时 / 死亡以上以后 SETTLE 之后才开始记击败标记（读档时标记会变），已经打过的不补发。
//! 许愿石（rr/wishstone.py，用户 2026-11-04「在高难给boss添加许愿石的掉落 … 每个boss固定掉落1个 追忆boss掉落3个」）也在这里发：
//! 死亡以上的 boss 行第 4 个数，和融锻之心一起发、共用给过标记（没开装备工坊时融锻之心的 goods 是 0，只发许愿石）。
//! 高难度 Boss 卢恩保底（rr/bosses.py，settings 的 hard_boss_runes，用户 2026-11-04「补正一下高难度下boss的卢恩获取 20w起步」）：
//! 死亡以上第一次打过一场 Boss 战时补 runefloor − 这场原版的击败奖励（boss 行第 5 个数）个卢恩，和融锻之心、许愿石同一次发（共用给过标记）；
//! 原版奖励游戏照常乘难度的卢恩加成，所以合起来每场至少 runefloor。
//! 定义 fusion.txt：goods 融锻之心（0 = 不给）；wish 许愿石；runefloor 卢恩保底；lock 当前档标记…；rem 击败标记 数量 给过标记；
//! boss 击败标记 数量 给过标记 [许愿石数量 [原版击败奖励]]

use std::collections::HashMap;
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{GameDataMan, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::gear::{flag_get, flag_set, gift_n};
use crate::{dir, log};

const SCAN: Duration = Duration::from_millis(250);
/// 进存档 / 换了平时、死亡以上多久以后才开始记击败标记（读档时标记会变）
const SETTLE: Duration = Duration::from_secs(3);

#[derive(Debug, Default, PartialEq)]
struct Def {
    goods: i32,
    /// 「死亡」「不可能」的当前档标记：亮着一个就算死亡以上
    lock: Vec<u32>,
    /// (击败标记, 数量, 给过标记)：平时的（追忆 Boss 战）
    rem: Vec<(u32, u32, u32)>,
    /// 同上：死亡以上的（所有 Boss 战）
    boss: Vec<(u32, u32, u32)>,
    /// 许愿石道具（0 = 没开）
    wish: i32,
    /// 死亡以上各场 Boss 战给几个许愿石（击败标记 → 个数）
    wish_n: HashMap<u32, u32>,
    /// 死亡以上每场 Boss 战的卢恩保底（0 = 不补）、各场原版的击败奖励（击败标记 → 卢恩）
    floor: u32,
    award: HashMap<u32, u32>,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    for l in text.lines() {
        let f: Vec<&str> = l.trim_start_matches('\u{feff}').split_whitespace().collect();
        let nums: Vec<u32> = f.iter().skip(1).filter_map(|x| x.parse().ok()).collect();
        match f.first().copied() {
            Some("goods") if f.len() >= 2 => d.goods = f[1].parse().ok()?,
            Some("lock") => d.lock.extend(nums),
            Some("rem") if nums.len() == 3 => d.rem.push((nums[0], nums[1], nums[2])),
            Some("wish") if f.len() >= 2 => d.wish = f[1].parse().ok()?,
            Some("runefloor") if f.len() >= 2 => d.floor = f[1].parse().ok()?,
            Some("boss") if (3..=5).contains(&nums.len()) => {
                d.boss.push((nums[0], nums[1], nums[2]));
                if let Some(&w) = nums.get(3).filter(|&&w| w > 0) {
                    d.wish_n.insert(nums[0], w);
                }
                if let Some(&a) = nums.get(4) {
                    d.award.insert(nums[0], a);
                }
            }
            _ => {}
        }
    }
    ((d.goods > 0 || d.wish > 0 || d.floor > 0) && !(d.rem.is_empty() && d.boss.is_empty())).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("fusion.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!(
            "融锻之心掉落（{}平时追忆 Boss {} 场，死亡以上 Boss {} 场{}）",
            if d.goods > 0 { "" } else { "不给融锻之心，" },
            d.rem.len(),
            d.boss.len(),
            if d.wish > 0 { format!("；许愿石 {} 场", d.wish_n.len()) } else { String::new() }
        ) + &if d.floor > 0 {
            format!("；死亡以上 Boss 卢恩保底 {}（{} 场要补）", d.floor, d.boss.iter().filter(|b| runes_for(d, true, b.0) > 0).count())
        } else {
            String::new()
        },
        None => "融锻之心掉落（没有 fusion.txt，不管）".into(),
    }
}

struct St {
    next: Instant,
    /// 现在是不是死亡以上、从什么时候起
    mode: Option<(bool, Instant)>,
    /// 击败标记上一次看到的状态（SETTLE 之后才记）
    seen: HashMap<u32, bool>,
    /// 这次进游戏发了几个（融锻之心, 许愿石）
    given: (u32, u32),
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 这一场给几个（融锻之心, 许愿石）：没开融锻之心（goods 0）就不给它；许愿石只在死亡以上
fn gives(d: &Def, death: bool, defeat: u32, n: u32) -> (u32, u32) {
    let heart = if d.goods > 0 { n } else { 0 };
    let wish = if death && d.wish > 0 { d.wish_n.get(&defeat).copied().unwrap_or(0) } else { 0 };
    (heart, wish)
}

/// 这一场补多少卢恩：只在死亡以上，保底 − 原版的击败奖励（没有记录的当 0）
fn runes_for(d: &Def, death: bool, defeat: u32) -> u32 {
    if !death || d.floor == 0 {
        return 0;
    }
    d.floor.saturating_sub(d.award.get(&defeat).copied().unwrap_or(0))
}

/// 加卢恩（直接加在身上的卢恩数上）；读不到人物数据就是没加上
fn add_runes(n: u32) -> bool {
    let Ok(gdm) = (unsafe { GameDataMan::instance_mut() }) else { return false };
    let pgd = &mut gdm.main_player_game_data;
    pgd.rune_count = pgd.rune_count.saturating_add(n);
    true
}

/// 这一种（平时 / 死亡以上）里，击败标记 defeat 从灭变亮、给过标记还没亮：该发
fn due(was: Option<bool>, on: bool, got: Option<bool>) -> bool {
    on && was == Some(false) && got == Some(false)
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St { next: now, mode: None, seen: HashMap::new(), given: (0, 0) });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    if wcm.main_player.is_none() {
        st.mode = None;
        st.seen.clear();
        return;
    }
    let death = d.lock.iter().any(|&f| flag_get(f) == Some(true));
    if st.mode.map(|m| m.0) != Some(death) {
        st.mode = Some((death, now));
        st.seen.clear();
        log(&format!("融锻之心掉落：现在是{}，开始看 Boss 击败标记", if death { "「死亡」以上（所有 Boss）" } else { "平时（只有追忆 Boss）" }));
    }
    let Some((_, since)) = st.mode else { return };
    if now - since < SETTLE {
        return;
    }
    for &(defeat, n, got) in if death { &d.boss } else { &d.rem } {
        let Some(on) = flag_get(defeat) else { continue };
        let was = st.seen.insert(defeat, on);
        if due(was, on, flag_get(got)) {
            let (heart, wish) = gives(d, death, defeat, n);
            let runes = runes_for(d, death, defeat);
            if heart == 0 && wish == 0 && runes == 0 {
                continue;
            }
            if (heart > 0 && !gift_n(1, d.goods, heart)) || (wish > 0 && !gift_n(1, d.wish, wish)) {
                log("融锻之心掉落：没有发货表，没发");
                continue;
            }
            let runes_ok = runes == 0 || add_runes(runes);
            flag_set(got, true);
            st.given.0 += heart;
            st.given.1 += wish;
            log(&format!(
                "融锻之心掉落：Boss 战 {defeat} 被击败（{}）→ 融锻之心 {heart} 个、许愿石 {wish} 个{}（这次进游戏累计 {} / {} 个）",
                if death { "死亡以上" } else { "平时" },
                if runes > 0 {
                    format!("、卢恩保底补 {runes}（原版奖励 {}，保底 {}）{}", d.award.get(&defeat).copied().unwrap_or(0), d.floor,
                            if runes_ok { "" } else { "，人物数据读不到，没补上" })
                } else {
                    String::new()
                },
                st.given.0,
                st.given.1
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 定义：道具、死亡以上的档标记、平时 / 死亡以上的 Boss 战；不像样的行丢掉，没有 Boss 战就不工作
    #[test]
    fn parse_def() {
        let d = parse("# x\ngoods 9241\nlock 9956 9957\nrem 10000800 5 10007989\nboss 10000800 3 10007988\nboss 10000850 1 10007987\nrem 1 2\n").unwrap();
        assert_eq!(d.goods, 9241);
        assert_eq!(d.lock, vec![9956, 9957]);
        assert_eq!(d.rem, vec![(10000800, 5, 10007989)]);
        assert_eq!(d.boss, vec![(10000800, 3, 10007988), (10000850, 1, 10007987)]);
        assert!(parse("goods 9241\nlock 9956\n").is_none());
        assert!(parse("rem 10000800 5 10007989\n").is_none());
        assert_eq!(d.wish, 0);
        assert!(d.wish_n.is_empty());
    }

    /// 许愿石：wish 行 + boss 行第 4 个数；没开融锻之心（goods 0）时只发许愿石；平时不发许愿石
    #[test]
    fn wish_stone() {
        let d = parse("goods 0\nwish 9244\nlock 9956\nboss 10000800 0 10007988 3\nboss 10000850 0 10007987 1\nboss 10000860 0 10007986 0\n").unwrap();
        assert_eq!(d.wish, 9244);
        assert_eq!(d.wish_n.get(&10000800), Some(&3));
        assert_eq!(d.wish_n.get(&10000860), None);
        assert_eq!(gives(&d, true, 10000800, 0), (0, 3));
        assert_eq!(gives(&d, true, 10000860, 0), (0, 0));
        assert_eq!(gives(&d, false, 10000800, 5), (0, 0));
        let both = parse("goods 9241\nwish 9244\nboss 10000800 4 10007988 3\nrem 10000800 5 10007989\n").unwrap();
        assert_eq!(gives(&both, true, 10000800, 4), (4, 3));
        assert_eq!(gives(&both, false, 10000800, 5), (5, 0));
        assert!(parse("goods 0\nboss 10000800 0 10007988 3\n").is_none());
    }

    /// 高难度 Boss 卢恩保底（用户 2026-11-04「20w起步」）：runefloor + boss 行第 5 个数（原版奖励）；只在死亡以上补，原版本来就够的不补；
    /// 只开保底（没开融锻之心、许愿石）也工作
    #[test]
    fn rune_floor() {
        let d = parse("goods 0\nrunefloor 200000\nlock 9956\nboss 10000800 0 10007988 0 20000\nboss 10000850 0 10007987 0 500000\nboss 10000860 0 10007986\n").unwrap();
        assert_eq!(d.floor, 200000);
        assert_eq!(runes_for(&d, true, 10000800), 180000);
        assert_eq!(runes_for(&d, true, 10000850), 0, "原版奖励就 ≥ 保底");
        assert_eq!(runes_for(&d, true, 10000860), 200000, "没有原版奖励的记录当 0");
        assert_eq!(runes_for(&d, false, 10000800), 0, "平时不补");
        let off = parse("goods 9241\nboss 10000800 3 10007988 0 20000\n").unwrap();
        assert_eq!(runes_for(&off, true, 10000800), 0, "没有 runefloor 行就不补");
    }

    /// 只在这一种里第一次看到击败标记从灭变亮、还没给过时发；读档后第一次看到就亮着的（打过的）不补发
    #[test]
    fn due_only_on_new_defeat() {
        assert!(due(Some(false), true, Some(false)));
        assert!(!due(None, true, Some(false))); // 刚开始记就亮着：以前打过的
        assert!(!due(Some(false), true, Some(true))); // 给过了（复活后再打）
        assert!(!due(Some(true), true, Some(false)));
        assert!(!due(Some(false), false, Some(false)));
        assert!(!due(Some(false), true, None)); // 读不到标记
    }
}
