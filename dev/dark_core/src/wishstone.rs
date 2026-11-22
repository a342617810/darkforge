//! 许愿石升级（参数侧 rr/wishstone.py，菜单 sc/wishstone.py；用户 2026-11-04「效果是提高1级等级」，游戏里试过直接改人物数据可行）：
//! 赐福「暗黑重铸」→「许愿石升级」选一项能力值、确认：菜单把能力值序号（0 生命力 … 7 感应）写进 attr 起的几个标记、点亮请求 req。
//! 这里看到请求就处理、最后熄灭请求（菜单等它熄了再看结果）：
//! - 背包里没有许愿石：点亮 none；这项能力值已经 99：点亮 max（菜单提示后熄灭）；
//! - 否则扣 1 个许愿石，这项能力值 +1、等级 +1（游戏 1 秒内自己重算最大血量 / 专注值 / 精力、负重等）。
//! 确认框里的「现有许愿石几个、等级」：gear.rs 的 #I8 占位调 confirm_text。
//! 一次用 10 个（用户 2026-11-21「许愿石做一个一次使用10个的入口 注意校验加点后不要超过上限」）：菜单另外点亮 ten；这里用
//! min(10, 现有许愿石, 到 99 还差几点) 个，这项能力值、等级各加这么多，不会超过 99；结果（加了几点、为什么不足 10）写进
//! 占位 #IH（msghook），菜单的结果框显示它。
//! 定义 wishstone.txt：goods 道具；req 请求标记；attr 起点 位数；none 没有许愿石；max 已经 99；ten 一次用 10 个（没有这行就只能一个一个用）

use std::fs;
use std::sync::OnceLock;

use eldenring::cs::{GameDataMan, PlayerGameData};
use fromsoftware_shared::FromStatic;

use crate::gear::{count_goods, flag_get, flag_set, remove_goods};
use crate::levelup::{attr, NAMES};
use crate::{dir, log};

/// 能力值上限
const ATTR_MAX: u32 = 99;
/// 「一次使用 10 个」一次最多用几个
const TEN: u32 = 10;
/// 结果文字的占位种类（#IH，msghook 的 marker_at：A~Z = 10~35；gear.rs confirm_tick 用到 #IG = 16）
const RESULT_KIND: u8 = 17;

#[derive(Debug, Default, PartialEq)]
struct Def {
    goods: u32,
    req: u32,
    attr0: u32,
    bits: u32,
    none: u32,
    max: u32,
    /// 一次用 10 个的标记；0 = 没有
    ten: u32,
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
            (Some("ten"), [x, ..]) => d.ten = *x,
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
    /// 提升了（能力值序号, 原来的值, 新值）
    Done(usize, u32, u32),
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

/// 这次用几个：最多 want 个，不超过现有的，加完不超过 99（check 过了才调：stones ≥ 1、cur < 99）
fn how_many(want: u32, stones: u32, cur: u32) -> u32 {
    want.min(stones).min(ATTR_MAX.saturating_sub(cur)).max(1)
}

fn apply(d: &Def, p: &mut PlayerGameData, k: usize, want: u32) -> Outcome {
    let stones = count_goods(p, d.goods);
    let cur = attr(p, k).map(|a| *a);
    if let Some(o) = check(stones, cur) {
        return o;
    }
    let old = cur.unwrap_or(0);
    let n = how_many(want, stones, old);
    let got = remove_goods(p, d.goods, n);
    if got == 0 {
        log("许愿石升级：扣不掉许愿石，没升级");
        return Outcome::NoStone;
    }
    let Some(a) = attr(p, k) else { return Outcome::Bad };
    // 扣掉几个加几点（扣少了也不多加）；再夹一次上限
    *a = (*a + got).min(ATTR_MAX);
    let new = *a;
    p.level += new - old;
    Outcome::Done(k, old, new)
}

/// 一次用 10 个的结果文字（中文, 英文），两行：加了几点、等级；用了几个、不足 10 的原因、还剩几个
fn result_text(k: usize, old: u32, new: u32, level: u32, left: u32) -> (String, String) {
    let n = new - old;
    let name = NAMES.get(k).copied().unwrap_or("?");
    let name_en = NAMES_EN.get(k).copied().unwrap_or("?");
    let (zh2, en2) = if n >= TEN {
        (format!("用了 {n} 个许愿石，还剩 {left} 个"), format!("Used {n} Wish Stones, {left} left"))
    } else if new >= ATTR_MAX {
        (format!("到 {ATTR_MAX} 为止，只用了 {n} 个许愿石，还剩 {left} 个"), format!("Stopped at {ATTR_MAX}: used only {n}, {left} left"))
    } else {
        (format!("许愿石只有 {n} 个，都用掉了"), format!("You had only {n} Wish Stones; all used"))
    };
    (
        format!("{name}提升了 {n} 点（{old} → {new}），等级 {level}\n{zh2}"),
        format!("{name_en} +{n} ({old} -> {new}), level {level}\n{en2}"),
    )
}

/// 结果文字里的英文名（同 sc/wishstone.py 的 NAMES['en']）
const NAMES_EN: [&str; 8] = ["Vigor", "Mind", "Endurance", "Strength", "Dexterity", "Intelligence", "Faith", "Arcane"];

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
    let ten = d.ten > 0 && flag_get(d.ten) == Some(true);
    match apply(d, p, k, if ten { TEN } else { 1 }) {
        Outcome::Done(k, old, v) => {
            let left = count_goods(p, d.goods);
            log(&format!("许愿石升级{}：{} {old} → {v}，等级 → {}（还剩 {left} 个许愿石）", if ten { "（一次 10 个）" } else { "" }, NAMES[k], p.level));
            if ten {
                let (zh, en) = result_text(k, old, v, p.level, left);
                crate::msghook::set_confirm(b'I', RESULT_KIND, &zh.encode_utf16().collect::<Vec<u16>>(), &en.encode_utf16().collect::<Vec<u16>>());
            }
        }
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
    if d.ten > 0 {
        flag_set(d.ten, false);
    }
    flag_set(d.req, false);
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 一次 10 个：不超过现有的、加完不超过 99；一个一个用照旧是 1
    #[test]
    fn ten_at_once() {
        assert_eq!(how_many(10, 30, 50), 10);
        assert_eq!(how_many(10, 4, 50), 4, "只有 4 个");
        assert_eq!(how_many(10, 30, 95), 4, "95 → 99 只差 4 点");
        assert_eq!(how_many(10, 2, 98), 1);
        assert_eq!(how_many(1, 30, 50), 1);
        let (zh, en) = result_text(0, 95, 99, 120, 26);
        assert_eq!(zh, "生命力提升了 4 点（95 → 99），等级 120\n到 99 为止，只用了 4 个许愿石，还剩 26 个");
        assert_eq!(en, "Vigor +4 (95 -> 99), level 120\nStopped at 99: used only 4, 26 left");
        assert!(result_text(3, 40, 44, 80, 0).0.ends_with("许愿石只有 4 个，都用掉了"));
        assert!(result_text(7, 40, 50, 80, 5).0.ends_with("用了 10 个许愿石，还剩 5 个"), "用满 10 个不写原因");
    }

    #[test]
    fn parse_def() {
        let d = parse("# x\ngoods 9244\nreq 93012\nattr 93013 3\nnone 93016\nmax 93017\nten 92770\n").unwrap();
        assert_eq!(d, Def { goods: 9244, req: 93012, attr0: 93013, bits: 3, none: 93016, max: 93017, ten: 92770 });
        assert_eq!(parse("goods 9244\nreq 93012\nattr 93013 3\nnone 93016\nmax 93017\n").map(|d| d.ten), Some(0), "老的定义：只能一个一个用");
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
