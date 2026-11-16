//! 许愿石升级（参数侧 rr/wishstone.py，菜单 sc/wishstone.py；用户 2026-11-04「效果是提高1级等级」，游戏里试过直接改人物数据可行）：
//! 赐福「暗黑重铸」→「许愿石升级」选一项能力值、确认：菜单把能力值序号（0 生命力 … 7 感应）写进 attr 起的几个标记、点亮请求 req。
//! 这里看到请求就处理、最后熄灭请求（菜单等它熄了再看结果）：
//! - 背包里没有许愿石：点亮 none；这项能力值已经 99：点亮 max（菜单提示后熄灭）；
//! - 否则扣 1 个许愿石，这项能力值 +1、等级 +1（游戏 1 秒内自己重算最大血量 / 专注值 / 精力、负重等）。
//! 确认框里的「现有许愿石几个、等级」：gear.rs 的 #I8 占位调 confirm_text。
//! 定义 wishstone.txt：goods 道具；req 请求标记；attr 起点 位数；none 没有许愿石；max 已经 99

use std::fs;
use std::sync::OnceLock;

use eldenring::cs::{GameDataMan, PlayerGameData};
use fromsoftware_shared::FromStatic;

use crate::gear::{count_goods, flag_get, flag_set, remove_goods};
use crate::levelup::{attr, NAMES};
use crate::{dir, log};

/// 能力值上限
const ATTR_MAX: u32 = 99;

#[derive(Debug, Default, PartialEq)]
struct Def {
    goods: u32,
    req: u32,
    attr0: u32,
    bits: u32,
    none: u32,
    max: u32,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    for l in text.lines() {
        let f: Vec<&str> = l.trim_start_matches('\u{feff}').split_whitespace().collect();
        let nums: Vec<u32> = f.iter().skip(1).filter_map(|x| x.parse().ok()).collect();
        match (f.first().copied(), nums.as_slice()) {
            (Some("goods"), [g, ..]) => d.goods = *g,
            (Some("req"), [x, ..]) => d.req = *x,
            (Some("attr"), [a, b, ..]) => (d.attr0, d.bits) = (*a, *b),
            (Some("none"), [x, ..]) => d.none = *x,
            (Some("max"), [x, ..]) => d.max = *x,
            _ => {}
        }
    }
    (d.goods > 0 && d.req > 0 && d.attr0 > 0 && (1..=4).contains(&d.bits) && d.none > 0 && d.max > 0).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("wishstone.txt")).unwrap_or_default())).as_ref()
}

/// 许愿石的道具编号（换自制图标用）；没开就没有
pub(crate) fn goods() -> Option<u32> {
    def().map(|d| d.goods)
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("许愿石升级（道具 {}，请求标记 {}）", d.goods, d.req),
        None => "许愿石升级（没有 wishstone.txt，不管）".into(),
    }
}

/// 确认框占位 #I8 的文字（中文, 英文）：现有许愿石个数、等级
pub(crate) fn confirm_text(pgd: &PlayerGameData) -> Option<(String, String)> {
    let d = def()?;
    let n = count_goods(pgd, d.goods);
    Some((format!("现有许愿石 {n} 个，等级 {}", pgd.level), format!("Wish Stones: {n}, level {}", pgd.level)))
}

/// 一次请求的结果
#[derive(Debug, PartialEq)]
enum Outcome {
    /// 提升了（能力值序号, 新值）
    Done(usize, u32),
    NoStone,
    Maxed,
    /// 序号不对（菜单写坏了）
    Bad,
}

/// 能不能提升（cur = 这项能力值现在的值，序号不对是 None）：有没有石头、到没到上限（不改东西）
fn check(stones: u32, cur: Option<u32>) -> Option<Outcome> {
    let Some(cur) = cur else { return Some(Outcome::Bad) };
    if stones < 1 {
        return Some(Outcome::NoStone);
    }
    if cur >= ATTR_MAX {
        return Some(Outcome::Maxed);
    }
    None
}

fn apply(d: &Def, p: &mut PlayerGameData, k: usize) -> Outcome {
    let stones = count_goods(p, d.goods);
    let cur = attr(p, k).map(|a| *a);
    if let Some(o) = check(stones, cur) {
        return o;
    }
    if remove_goods(p, d.goods, 1) != 1 {
        log("许愿石升级：扣不掉许愿石，没升级");
        return Outcome::NoStone;
    }
    let Some(a) = attr(p, k) else { return Outcome::Bad };
    *a += 1;
    let new = *a;
    p.level += 1;
    Outcome::Done(k, new)
}

/// 每帧看请求，不能节流：赐福菜单等回应的时间很短（2026-11-05 以前每 250 毫秒看一次，菜单先超时、熄了请求，
/// 这里根本看不到，就提示「没有加载 dark_core」）
pub fn tick() {
    let Some(d) = def() else { return };
    if flag_get(d.req) != Some(true) {
        return;
    }
    let Ok(gdm) = (unsafe { GameDataMan::instance_mut() }) else { return };
    let p: &mut PlayerGameData = &mut gdm.main_player_game_data;
    if p.level == 0 {
        return; // 还在主菜单
    }
    let k = (0..d.bits).filter(|&i| flag_get(d.attr0 + i) == Some(true)).fold(0usize, |v, i| v | (1 << i));
    match apply(d, p, k) {
        Outcome::Done(k, v) => log(&format!("许愿石升级：{} → {v}，等级 → {}（还剩 {} 个许愿石）", NAMES[k], p.level, count_goods(p, d.goods))),
        Outcome::NoStone => {
            flag_set(d.none, true);
            log("许愿石升级：背包里没有许愿石");
        }
        Outcome::Maxed => {
            flag_set(d.max, true);
            log(&format!("许愿石升级：{} 已经是 {ATTR_MAX}", NAMES[k]));
        }
        Outcome::Bad => {
            flag_set(d.none, true);
            log(&format!("许愿石升级：能力值序号 {k} 不对，没升级"));
        }
    }
    flag_set(d.req, false);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_def() {
        let d = parse("# x\ngoods 9244\nreq 93012\nattr 93013 3\nnone 93016\nmax 93017\n").unwrap();
        assert_eq!(d, Def { goods: 9244, req: 93012, attr0: 93013, bits: 3, none: 93016, max: 93017 });
        assert!(parse("goods 9244\nreq 93012\nattr 93013 3\nnone 93016\n").is_none());
        assert!(parse("goods 9244\nreq 93012\nattr 93013 9\nnone 93016\nmax 93017\n").is_none());
    }

    #[test]
    fn checks() {
        assert_eq!(check(0, Some(10)), Some(Outcome::NoStone));
        assert_eq!(check(3, Some(99)), Some(Outcome::Maxed));
        assert_eq!(check(0, Some(99)), Some(Outcome::NoStone));
        assert_eq!(check(3, None), Some(Outcome::Bad));
        assert_eq!(check(1, Some(98)), None);
    }
}
