//! 死亡惩罚（用户 2026-11-19「加一下死亡惩罚 死亡时永久遗失身上25%的未鉴定装备」；比例是 items.txt 的 deathloss 行，
//! 重随 settings 的 death_penalty）：
//! - 认真死了没有（Watch）：血量 0 停了 HOLD 身上一直没有馈赠复活的「刚复活」效果；或者血量 0 停了 MIN_ZERO 以上又回来了、
//!   没见过「刚复活」（联机观战时血量会回来，同 arena.rs 的 death_tick）；或者血量 0 停够 MIN_ZERO 后人物没了（死亡画面后读图）。
//!   血量 0 的时间只数人物在场的时候。血量到 0 时在斗技场（m45：斗技场试炼、原版对战）的不算，试炼有自己的收回。
//! - 扣：背包（不含仓库）里的未鉴定道具一共 N 件，扣 N × 比例（不是整数时余下的部分按几率多扣一件），每件被挑中的机会一样。
//!   新装备正在发货（鉴定、许愿、赠送）时先欠着，发完再扣：发货核对还要扣掉换掉的未鉴定道具。回主菜单、换角色时欠着的作废。
//! - 扣掉了：血量回来、人物在场后原版闪烁提示 death loss（rr/notes.py）。
//! - 跟着卢恩取回（用户 2026-11-19「死亡惩罚那里也改一下 可以随着卢恩取回好了」）：扣掉的这批记下来，等死后新出现的那摊血迹
//!   （GameDataMan 的 has_bloodstain / bloodstain：所在地图、位置、卢恩数）。认出来以后：血迹没了（摸到了、卢恩取回了）就把这批发回来；
//!   血迹变成了另一摊（没取回又死了）就永久没了，同卢恩。死后 NO_STAIN 一直没有新血迹（献祭细枝、身上没有卢恩）就直接还回来。
//!   记在角色记录 遗失的未鉴定物品_<格子>.txt，退出游戏再进来照样认。
//! - 联机：只动自己的背包，各台电脑各算各的，不用房主定（联机计划 13.2 的 G 规则管的是敌人身上的效果和抽签）。
//! - 发回来不弹框（用户 2026-11-21「捡回死亡掉落的卢恩和物品时不要弹确认框 用闪烁提示」）：发货表（gift_n）走游戏的「获得物品」框，
//!   这里改成 items.txt 的 deathback 行那套：每轮按种类点亮计数标记（每种 per 个，亮一个 = 1 件）、再点亮请求，公共事件
//!   （sc/identify.py DEATHBACK_EVENT）用 2003:43 直接放进背包、熄灭标记；请求熄了数背包 + 仓库核对，少了的走发货表补上，
//!   再发下一轮；全部发完提示 death back（闪烁提示）。还没发完的记在记录的 b 行，退出再进来接着发。
//!   请求 ROUND_WAIT 一直亮着（游戏脚本包没挂上，事件没跑）：熄掉标记，剩下的走发货表。没有 deathback 行（老的重随包）也走发货表。
use std::time::{Duration, Instant};

use super::*;

/// 死后（人物在场、活着）这么久还没有新血迹：这次没掉卢恩（献祭细枝、身上没有卢恩），遗失的直接还回来
const NO_STAIN: Duration = Duration::from_secs(60);
/// 角色记录里的文件名：遗失的未鉴定物品_<格子>.txt
const LOST_PREFIX: &str = "遗失的未鉴定物品_";
/// 一轮请求亮着最多等这么久（公共事件每 0.5 秒看一次）；还亮着 = 事件没跑
const ROUND_WAIT: Duration = Duration::from_secs(10);
/// 复活后在场活着这么久才发「死亡时遗失了部分未鉴定物品」提示（读图刚完那几帧提示会被清掉）
const NOTE_DELAY: Duration = Duration::from_secs(3);

/// 可以发遗失提示了：这次在场活着满 NOTE_DELAY
fn note_ready(alive_since: Option<Instant>, now: Instant) -> bool {
    alive_since.is_some_and(|t| now.duration_since(t) >= NOTE_DELAY)
}

/// 直接放回背包的那套（items.txt 的 deathback 行：请求标记、第一个计数标记、每种几个、道具编号）
#[derive(Debug, Clone, PartialEq)]
pub(super) struct Back {
    req: u32,
    bit0: u32,
    per: u32,
    goods: Vec<u32>,
}

impl Back {
    pub(super) fn parse(f: &[&str]) -> Option<Back> {
        let num = |i: usize| f.get(i)?.parse::<u32>().ok();
        let goods: Vec<u32> = f.get(4)?.split(',').map(|x| x.parse().ok()).collect::<Option<_>>()?;
        let b = Back { req: num(1)?, bit0: num(2)?, per: num(3)?, goods };
        (b.per > 0 && !b.goods.is_empty() && b.req > 0 && b.bit0 > 0).then_some(b)
    }

    /// 第 i 种的第 j 个计数标记
    fn bit(&self, i: usize, j: u32) -> u32 {
        self.bit0 + self.per * i as u32 + j
    }

    fn clear_bits(&self) {
        for i in 0..self.goods.len() {
            for j in 0..self.per {
                flag_set(self.bit(i, j), false);
            }
        }
    }
}

/// 正在发的一轮：点亮请求的时间、这轮每种发几件、发之前背包 + 仓库里各有几件
#[derive(Debug)]
struct Round {
    t0: Instant,
    sent: Vec<(u32, u32)>,
    before: Vec<u32>,
}

/// 这一轮发哪些：back 里每种最多 per 件（不在 goods 里的不发，留给发货表）
fn round_plan(back: &[(u32, u32)], b: &Back) -> Vec<(usize, u32, u32)> {
    back.iter().filter_map(|&(g, n)| Some((b.goods.iter().position(|&x| x == g)?, g, n.min(b.per)))).filter(|x| x.2 > 0).collect()
}

/// 从 v 里减掉 g 的 n 件（减到 0 就去掉）
fn take_out(v: &mut Vec<(u32, u32)>, g: u32, n: u32) {
    if let Some(x) = v.iter_mut().find(|x| x.0 == g) {
        x.1 = x.1.saturating_sub(n);
    }
    v.retain(|x| x.1 > 0);
}

fn add_to(v: &mut Vec<(u32, u32)>, items: &[(u32, u32)]) {
    for &(g, n) in items {
        match v.iter_mut().find(|x| x.0 == g) {
            Some(x) => x.1 += n,
            None => v.push((g, n)),
        }
    }
}

/// 一摊血迹（认是不是同一摊：所在地图、位置取到 0.1 米、卢恩数）
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Stain {
    block: i32,
    pos: [i32; 3],
    runes: i32,
}

/// 现在的血迹；没有血迹（取回了、还没死过）是 None
fn stain_now() -> Option<Stain> {
    let g = unsafe { GameDataMan::instance() }.ok()?;
    if !g.has_bloodstain {
        return None;
    }
    let b: &eldenring::cs::BloodstainData = &g.bloodstain;
    let p = &b.msb_pos;
    let q = |v: f32| if v.is_finite() { (v * 10.0).round() as i32 } else { 0 };
    Some(Stain { block: i32::from(b.block_id), pos: [q(p.0), q(p.1), q(p.2)], runes: b.rune_count })
}

/// 遗失的这批现在该怎么办
#[derive(Debug, PartialEq)]
enum Lost {
    /// 接着等
    Wait,
    /// 死后新出现了血迹：这批跟着它
    Link,
    /// 死后一直没有新血迹：直接还回来
    NoStain,
    /// 跟着的那摊血迹没了：卢恩取回了，这批也发回来
    Back,
    /// 跟着的那摊血迹换成了别的（没取回又死了）：永久没了
    Gone,
}

/// 刚扣掉、还没认出血迹的这批：cur 现在的血迹、before 死之前的血迹、waited 死后在场活着等了多久
fn judge_fresh(cur: Option<Stain>, before: Option<Stain>, waited: Duration) -> Lost {
    match cur {
        Some(c) if Some(c) != before => Lost::Link,
        _ if waited >= NO_STAIN => Lost::NoStain,
        _ => Lost::Wait,
    }
}

/// 已经跟着血迹 stain 的这批
fn judge_linked(cur: Option<Stain>, stain: Stain) -> Lost {
    match cur {
        None => Lost::Back,
        Some(c) if c != stain => Lost::Gone,
        _ => Lost::Wait,
    }
}

fn lost_path(slot: i32) -> PathBuf {
    data_dir().join(format!("{LOST_PREFIX}{slot}.txt"))
}

fn fmt_list(v: &[(u32, u32)]) -> String {
    v.iter().map(|(g, n)| format!("{g}×{n}")).collect::<Vec<_>>().join("、")
}

fn total(v: &[(u32, u32)]) -> u32 {
    v.iter().map(|x| x.1).sum()
}

/// 写这个角色的记录（两批都空了就删掉文件）
fn save_lost(ds: &DeathSt) {
    let Some((slot, name)) = &ds.who else { return };
    let p = lost_path(*slot);
    if ds.lost.is_empty() && ds.fresh.is_empty() && ds.back.is_empty() {
        if p.is_file() {
            let _ = std::fs::remove_file(&p);
        }
        return;
    }
    let mut s = format!("# 死亡惩罚遗失的未鉴定物品（dark_core gear/deathloss.rs）：取回卢恩时一起发回来\nname\t{name}\n");
    let line = |tag: &str, t: Stain| format!("{tag}\t{}\t{}\t{}\t{}\t{}\n", t.block, t.pos[0], t.pos[1], t.pos[2], t.runes);
    if let Some(t) = ds.stain {
        s += &line("stain", t);
    }
    if let Some(t) = ds.before {
        s += &line("before", t);
    }
    for (g, n) in &ds.lost {
        s += &format!("g\t{g}\t{n}\n");
    }
    for (g, n) in &ds.fresh {
        s += &format!("f\t{g}\t{n}\n");
    }
    for (g, n) in &ds.back {
        s += &format!("b\t{g}\t{n}\n");
    }
    let _ = std::fs::create_dir_all(data_dir());
    let tmp = p.with_extension("tmp");
    if std::fs::write(&tmp, s).and_then(|_| std::fs::rename(&tmp, &p)).is_err() {
        log(&format!("死亡惩罚：遗失的未鉴定物品记不下来（{}）", p.display()));
    }
}

/// 读出来的记录
type Rec = (Vec<(u32, u32)>, Option<Stain>, Vec<(u32, u32)>, Option<Stain>, Vec<(u32, u32)>);

/// 读记录（名字对不上的不认）：(跟着血迹的那批, 血迹, 还没认出血迹的那批, 死之前的血迹, 还没发完的)
fn parse_lost(text: &str, name: &str) -> Option<Rec> {
    if rec_text_name(text).as_deref() != Some(name) {
        return None;
    }
    let (mut lost, mut stain, mut fresh, mut before, mut back) = (Vec::new(), None, Vec::new(), None, Vec::new());
    for l in text.lines().map(|l| l.trim_end_matches('\r')) {
        let f: Vec<&str> = l.split('\t').collect();
        let num = |i: usize| f.get(i).and_then(|v| v.parse::<i64>().ok());
        match f[0] {
            "stain" | "before" => {
                if let (Some(b), Some(x), Some(y), Some(z), Some(r)) = (num(1), num(2), num(3), num(4), num(5)) {
                    let t = Some(Stain { block: b as i32, pos: [x as i32, y as i32, z as i32], runes: r as i32 });
                    if f[0] == "stain" { stain = t } else { before = t }
                }
            }
            "g" | "f" | "b" => {
                if let (Some(g), Some(n)) = (num(1), num(2)) {
                    if g > 0 && n > 0 && g <= u32::MAX as i64 && n <= u32::MAX as i64 {
                        let v = match f[0] {
                            "g" => &mut lost,
                            "f" => &mut fresh,
                            _ => &mut back,
                        };
                        v.push((g as u32, n as u32));
                    }
                }
            }
            _ => {}
        }
    }
    Some((lost, stain, fresh, before, back))
}

/// 排进发货队列（会弹「获得物品」框）；发不了（没有发货表）返回 false
fn gift_back(v: &[(u32, u32)]) -> bool {
    v.iter().all(|&(g, n)| gift_n(1, g as i32, n))
}

/// 发回来：有 deathback 行就排进 back（直接放回背包、不弹框，back_tick 发，发完提示）；没有就走发货表（note = 这就提示 death back）。
/// 发不了返回 false
fn give_back(d: &Defs, ds: &mut DeathSt, v: &[(u32, u32)], note: bool) -> bool {
    let Some(b) = d.items.deathback.as_ref() else {
        let ok = gift_back(v);
        if ok && note {
            let _ = crate::notes::push("death back");
        }
        return ok;
    };
    let (direct, other): (Vec<(u32, u32)>, Vec<(u32, u32)>) = v.iter().copied().partition(|x| b.goods.contains(&x.0));
    add_to(&mut ds.back, &direct);
    ds.back_note |= note;
    other.is_empty() || gift_back(&other)
}

/// 血量 0 停这么久还没被馈赠复活顶掉就算死了（同 arena.rs DEATH_HOLD）
const HOLD: Duration = Duration::from_millis(2500);
/// 血量 0 不到这么久就回来了 / 人物没了：读图时的一两帧，不算
const MIN_ZERO: Duration = Duration::from_millis(500);
/// 斗技场的地图区号（m45_00 / m45_01 / m45_02）
const COLOS_AREA: u8 = 45;
const TIER_ZH: [&str; 5] = ["普通", "稀有", "史诗", "传说", "传说（幽影之地）"];

#[derive(Default)]
pub(super) struct DeathSt {
    w: Watch,
    /// 认定死了、还没扣（等发货发完、人物在场）
    owe: bool,
    /// 扣掉了、复活后要提示
    note: bool,
    /// 这次在场活着从什么时候起（复活后等 NOTE_DELAY 再提示）
    alive_since: Option<Instant>,
    /// 上一批没取回、永久没了，要提示 death gone（和 note 一样等 NOTE_DELAY）
    gone_note: bool,
    /// 这个记录是哪个角色的（格子, 名字）；换了角色 DeathSt 整个清掉，认准了再读
    who: Option<(i32, String)>,
    /// 跟着血迹 stain 的那批（道具编号, 件数）
    lost: Vec<(u32, u32)>,
    stain: Option<Stain>,
    /// 刚扣掉、还没认出血迹的那批；死之前的血迹 before；死后在场活着开始等的时间
    fresh: Vec<(u32, u32)>,
    before: Option<Stain>,
    wait_from: Option<Instant>,
    /// 活着时最后看到的血迹（死的时候记成 before）
    alive_stain: Option<Stain>,
    /// 要直接放回背包、还没发完的（道具编号, 件数）：每轮发完才减（记录的 b 行）
    back: Vec<(u32, u32)>,
    /// 正在发的一轮
    round: Option<Round>,
    /// 全部发完后提示 death back
    back_note: bool,
}

#[derive(Debug, Default)]
struct Watch {
    /// 这次血量到 0 的时间、最后一次在场还是 0 的时间
    zero_at: Option<Instant>,
    zero_seen: Option<Instant>,
    /// 这次血量 0 期间见过「刚复活」
    revived: bool,
    /// 血量到 0 时在斗技场里
    colos: bool,
    /// 这次已经判过了（等血量回来再重新看）
    done: bool,
}

#[derive(Debug, PartialEq)]
enum Ev {
    None,
    /// 真死了：血量 0 停了多久
    Died(Duration),
    /// 血量到 0 但不算：原因
    Skip(&'static str),
}

impl Watch {
    /// 每帧：present 人物在场；hp、just（身上有「刚复活」）、colos（在斗技场）只在在场时有意义
    fn step(&mut self, present: bool, hp: i32, just: bool, colos: bool, now: Instant) -> Ev {
        if present && hp <= 0 {
            if self.zero_at.is_none() {
                *self = Watch { zero_at: Some(now), zero_seen: Some(now), revived: just, colos, done: false };
            }
            self.zero_seen = Some(now);
            self.revived |= just;
            let held = now - self.zero_at.unwrap_or(now);
            if !self.done && held >= HOLD {
                self.done = true;
                return self.judge(held);
            }
            return Ev::None;
        }
        let (Some(t0), Some(t1)) = (self.zero_at, self.zero_seen) else { return Ev::None };
        let held = t1 - t0;
        if present {
            // 血量回来了：这次结束（还没判过、0 停够了就按这时候判）
            self.revived |= just;
            let ev = if self.done || held < MIN_ZERO { Ev::None } else { self.judge(held) };
            *self = Watch::default();
            return ev;
        }
        // 人物没了（读图）：血量 0 停够了就当死了；只判一次，回来血量满了再清
        if !self.done && held >= MIN_ZERO {
            self.done = true;
            return self.judge(held);
        }
        Ev::None
    }

    fn judge(&self, held: Duration) -> Ev {
        if self.revived {
            Ev::Skip("被馈赠复活顶掉了")
        } else if self.colos {
            Ev::Skip("在斗技场里")
        } else {
            Ev::Died(held)
        }
    }
}

/// 扣几件：total × pct%，不是整数时余下的部分按几率（roll 是 0~1 的随机数）多扣一件
fn how_many(total: u32, pct: f64, roll: f64) -> u32 {
    let x = total as f64 * pct.clamp(0.0, 100.0) / 100.0;
    let base = x.floor();
    (base as u32 + u32::from(roll < x - base)).min(total)
}

/// 0~1 的随机数
fn unit(rng: &mut Rng) -> f64 {
    (rng.next() >> 11) as f64 / (1u64 << 53) as f64
}

/// 从 have（道具编号, 件数）里不放回地挑 k 件（每件机会一样），返回（道具编号, 扣几件）
fn pick(have: &[(u32, u32)], k: u32, rng: &mut Rng) -> Vec<(u32, u32)> {
    let mut left: Vec<u64> = have.iter().map(|x| x.1 as u64).collect();
    let mut total: u64 = left.iter().sum();
    let mut out = vec![0u32; have.len()];
    for _ in 0..(k as u64).min(total) {
        let mut r = rng.below(total);
        for (i, l) in left.iter_mut().enumerate() {
            if r < *l {
                *l -= 1;
                out[i] += 1;
                break;
            }
            r -= *l;
        }
        total -= 1;
    }
    have.iter().zip(out).filter(|(_, n)| *n > 0).map(|(h, n)| (h.0, n)).collect()
}

/// 扣掉背包里的未鉴定道具，返回实际扣掉的（道具编号, 件数）
fn apply(d: &Defs, pgd: &mut PlayerGameData, pct: f64, rng: &mut Rng) -> Vec<(u32, u32)> {
    let have = unidentified(d, pgd);
    let total: u32 = have.iter().map(|x| x.1).sum();
    if total == 0 {
        log("死亡惩罚：背包里没有未鉴定物品，不扣");
        return Vec::new();
    }
    let k = how_many(total, pct, unit(rng));
    if k == 0 {
        log(&format!("死亡惩罚：背包里未鉴定物品 {total} 件，按 {pct}% 这次没扣到"));
        return Vec::new();
    }
    let mut gone = Vec::new();
    let mut parts = Vec::new();
    for (g, n) in pick(&have, k, rng) {
        let got = remove_goods(pgd, g, n);
        if got > 0 {
            gone.push((g, got));
        }
        let name = d.items.goods.get(&g).map_or_else(|| format!("道具 {g}"), |&(c, t)| format!("{}（{}）", DIR_CAT_ZH.get(c).unwrap_or(&"?"), TIER_ZH.get(t).unwrap_or(&"?")));
        parts.push(if got == n { format!("{name}×{n}") } else { format!("{name}×{n}（只扣掉 {got}）") });
    }
    log(&format!("死亡惩罚：背包里未鉴定物品 {total} 件，按 {pct}% 扣 {k} 件：{}；实际扣掉 {} 件，取回卢恩时一起发回来",
                 parts.join("、"), gone.iter().map(|x| x.1).sum::<u32>()));
    gone
}

/// 遗失的两批：换了角色读记录，活着时看血迹，该还的还、该丢的丢
fn lost_tick(d: &Defs, st: &mut St, present_alive: bool, now: Instant) {
    let ds = &mut st.death;
    if ds.who.is_none() {
        let Some(w) = st.who.clone().filter(|w| crate::who::is_confirmed(w)) else { return };
        if let Some((lost, stain, fresh, before, back)) = std::fs::read_to_string(lost_path(w.0)).ok().and_then(|t| parse_lost(&t, &w.1)) {
            if !lost.is_empty() || !fresh.is_empty() || !back.is_empty() {
                log(&format!("死亡惩罚：格子 {}「{}」有遗失还没取回的未鉴定物品：跟着血迹的 {} 件、刚遗失的 {} 件、取回了还没发完的 {} 件",
                             w.0, w.1, total(&lost), total(&fresh), total(&back)));
            }
            (ds.lost, ds.stain, ds.fresh, ds.before, ds.back) = (lost, stain, fresh, before, back);
            ds.back_note = !ds.back.is_empty();
        }
        // 上次没发完的一轮（退出时请求、计数标记还亮着，会跟着存档）：熄掉，照记录重新发
        if let Some(b) = d.items.deathback.as_ref() {
            flag_set(b.req, false);
            b.clear_bits();
        }
        ds.round = None;
        ds.who = Some(w);
    }
    if !present_alive {
        return;
    }
    let cur = stain_now();
    ds.alive_stain = cur;
    if !ds.fresh.is_empty() {
        let waited = now - *ds.wait_from.get_or_insert(now);
        match judge_fresh(cur, ds.before, waited) {
            Lost::Link => {
                if !ds.lost.is_empty() {
                    log(&format!("死亡惩罚：上次遗失的未鉴定物品 {} 件没取回又死了，永久失去：{}", total(&ds.lost), fmt_list(&ds.lost)));
                    ds.gone_note = true;
                }
                ds.lost = std::mem::take(&mut ds.fresh);
                ds.stain = cur;
                ds.before = None;
                ds.wait_from = None;
                log(&format!("死亡惩罚：遗失的 {} 件跟着这次的血迹（卢恩 {}），取回卢恩时一起发回来", total(&ds.lost), cur.map_or(0, |c| c.runes)));
                save_lost(ds);
            }
            Lost::NoStain => {
                let fresh = std::mem::take(&mut ds.fresh);
                let ok = give_back(d, ds, &fresh, false);
                ds.fresh = fresh;
                log(&format!("死亡惩罚：死后 {} 秒没有新血迹（献祭细枝、或者身上没有卢恩），遗失的 {} 件{}", NO_STAIN.as_secs(), total(&ds.fresh),
                             if ok { "直接发回来" } else { "要发回来，但没有发货表，发不了" }));
                ds.fresh.clear();
                ds.before = None;
                ds.wait_from = None;
                save_lost(ds);
            }
            _ => {}
        }
        return;
    }
    let Some(stain) = ds.stain.filter(|_| !ds.lost.is_empty()) else { return };
    match judge_linked(cur, stain) {
        Lost::Back => {
            let lost = std::mem::take(&mut ds.lost);
            let ok = give_back(d, ds, &lost, true);
            log(&format!("死亡惩罚：血迹没了（卢恩取回了），遗失的 {} 件{}：{}", total(&lost), if ok { "发回来" } else { "要发回来，但没有发货表，发不了" }, fmt_list(&lost)));
            ds.stain = None;
            save_lost(ds);
        }
        Lost::Gone => {
            log(&format!("死亡惩罚：跟着的那摊血迹换成了别的（没取回又死了），遗失的 {} 件永久失去：{}", total(&ds.lost), fmt_list(&ds.lost)));
            ds.gone_note = true;
            ds.lost.clear();
            ds.stain = None;
            save_lost(ds);
        }
        _ => {}
    }
}

/// 直接放回背包：一轮一轮发（见文件开头），全部发完提示 death back
fn back_tick(d: &Defs, st: &mut St, pgd: &PlayerGameData, alive: bool, now: Instant) {
    if st.death.who.is_none() {
        return;
    }
    let busy = st.pending.is_some() || st.gift_wait.is_some();
    let ds = &mut st.death;
    let Some(b) = d.items.deathback.as_ref() else {
        // 换成了没有 deathback 行的重随包，记录里还有没发完的：走发货表
        if !ds.back.is_empty() {
            let v = std::mem::take(&mut ds.back);
            let ok = gift_back(&v);
            log(&format!("死亡惩罚：取回了还没发完的 {} 件改走发货表{}：{}", total(&v), if ok { "" } else { "，但没有发货表，发不了" }, fmt_list(&v)));
            if ok && std::mem::take(&mut ds.back_note) {
                let _ = crate::notes::push("death back");
            }
            save_lost(ds);
        }
        return;
    };
    if let Some(r) = ds.round.as_ref() {
        match flag_get(b.req) {
            Some(false) => {
                let r = ds.round.take().unwrap_or_else(|| unreachable!());
                let mut short = Vec::new();
                for (&(g, n), &was) in r.sent.iter().zip(&r.before) {
                    let got = count_lot_item(pgd, 1, g as i32).saturating_sub(was);
                    if got < n {
                        short.push((g, n - got));
                    }
                    take_out(&mut ds.back, g, n);
                }
                log(&format!("死亡惩罚：直接放回背包 {} 件（{}），还剩 {} 件", total(&r.sent), fmt_list(&r.sent), total(&ds.back)));
                if !short.is_empty() {
                    let ok = gift_back(&short);
                    log(&format!("死亡惩罚：其中 {} 件背包里没多出来（可能放不下），改走发货表{}：{}", total(&short), if ok { "" } else { "，但没有发货表，发不了" }, fmt_list(&short)));
                }
                save_lost(ds);
            }
            Some(true) if now - r.t0 >= ROUND_WAIT => {
                flag_set(b.req, false);
                b.clear_bits();
                ds.round = None;
                let v = std::mem::take(&mut ds.back);
                let ok = gift_back(&v);
                log(&format!("死亡惩罚：放回背包的请求 {} 秒没人处理（游戏脚本包没挂上？），剩下的 {} 件改走发货表{}：{}",
                             ROUND_WAIT.as_secs(), total(&v), if ok { "" } else { "，但没有发货表，发不了" }, fmt_list(&v)));
                save_lost(ds);
            }
            _ => return,
        }
    }
    if ds.round.is_some() {
        return;
    }
    if ds.back.is_empty() {
        if ds.back_note && alive && crate::notes::push("death back") {
            ds.back_note = false;
        }
        return;
    }
    // 新一轮：活着、在场，别的发货没在进行（核对件数时不受它们影响）
    if !alive || busy || flag_get(b.req) != Some(false) {
        return;
    }
    let plan = round_plan(&ds.back, b);
    if plan.is_empty() {
        // 剩下的都不在 deathback 的种类里：走发货表
        let v = std::mem::take(&mut ds.back);
        let ok = gift_back(&v);
        log(&format!("死亡惩罚：{} 件不能直接放回背包，改走发货表{}：{}", total(&v), if ok { "" } else { "，但没有发货表，发不了" }, fmt_list(&v)));
        save_lost(ds);
        return;
    }
    b.clear_bits();
    let mut sent = Vec::new();
    let mut before = Vec::new();
    for &(i, g, k) in &plan {
        for j in 0..k {
            flag_set(b.bit(i, j), true);
        }
        sent.push((g, k));
        before.push(count_lot_item(pgd, 1, g as i32));
    }
    if flag_set(b.req, true) {
        ds.round = Some(Round { t0: now, sent, before });
    } else {
        b.clear_bits();
    }
}

pub(super) fn tick(d: &Defs, st: &mut St, pgd: &mut PlayerGameData) {
    let pct = d.items.deathloss;
    let now = Instant::now();
    let me = unsafe { WorldChrMan::instance() }.ok().and_then(|w| w.main_player.as_ref()).map(|p| {
        let j = crate::curses::revive_just();
        let just = j > 0 && p.chr_ins.special_effect.entries().any(|x| x.param_id == j);
        (p.chr_ins.modules.data.hp, just, p.current_block_id.area() == COLOS_AREA)
    });
    let (present, hp, just, colos) = me.map_or((false, 0, false, false), |(h, j, c)| (true, h, j, c));
    // 遗失还没取回的照样看（关掉死亡惩罚以后也要把欠着的还回来）
    let alive = present && hp > 0 && st.death.w.zero_at.is_none();
    st.death.alive_since = if alive { Some(st.death.alive_since.unwrap_or(now)) } else { None };
    lost_tick(d, st, alive, now);
    back_tick(d, st, pgd, alive, now);
    // 永久遗失的提示同样等复活后活着满 NOTE_DELAY（lost_tick 在复活后第一帧就认出新血迹）
    if st.death.gone_note && note_ready(st.death.alive_since, now) && crate::notes::push("death gone") {
        st.death.gone_note = false;
    }
    if pct <= 0.0 {
        return;
    }
    match st.death.w.step(present, hp, just, colos, now) {
        Ev::Died(held) => {
            log(&format!("死亡惩罚：死了（血量 0 停了 {:.1} 秒），扣未鉴定物品", held.as_secs_f32()));
            st.death.owe = true;
            if st.death.fresh.is_empty() {
                st.death.before = st.death.alive_stain;
            }
        }
        Ev::Skip(why) => log(&format!("死亡惩罚：血量到 0，{why}，不扣")),
        Ev::None => {}
    }
    if !present {
        return;
    }
    if st.death.owe && st.pending.is_none() && st.gift_wait.is_none() {
        st.death.owe = false;
        let got = apply(d, pgd, pct, &mut Rng::new());
        if !got.is_empty() {
            for (g, n) in got {
                match st.death.fresh.iter_mut().find(|x| x.0 == g) {
                    Some(x) => x.1 += n,
                    None => st.death.fresh.push((g, n)),
                }
            }
            st.death.wait_from = None;
            save_lost(&st.death);
            st.death.note = true;
        }
    }
    // 复活后在场活着满 NOTE_DELAY 才提示（用户 2026-11-22「给死亡时会遗失未鉴定的装备也加闪烁提示 不需要写明数量」：
    // 以前人物刚出现、血量回来那一帧就排进提示队列，读图那几帧事件标记读不到时 notes 会把整个队列清掉，这条就没了）
    if st.death.note && note_ready(st.death.alive_since, now) && crate::notes::push("death loss") {
        st.death.note = false;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(t0: Instant, ms: u64) -> Instant {
        t0 + Duration::from_millis(ms)
    }

    /// 遗失提示：不在场 / 死着不发；复活后活着满 3 秒才发
    #[test]
    fn loss_note_waits_after_respawn() {
        let t0 = Instant::now();
        assert!(!note_ready(None, at(t0, 10_000)));
        assert!(!note_ready(Some(t0), t0));
        assert!(!note_ready(Some(t0), at(t0, 2_900)));
        assert!(note_ready(Some(t0), at(t0, 3_000)));
    }

    #[test]
    fn real_death_counts_once() {
        let t0 = Instant::now();
        let mut w = Watch::default();
        assert_eq!(w.step(true, 100, false, false, t0), Ev::None);
        assert_eq!(w.step(true, 0, false, false, at(t0, 10)), Ev::None);
        assert_eq!(w.step(true, 0, false, false, at(t0, 2000)), Ev::None);
        assert!(matches!(w.step(true, 0, false, false, at(t0, 2600)), Ev::Died(_)));
        assert_eq!(w.step(true, 0, false, false, at(t0, 4000)), Ev::None);
        // 死亡画面后读图、回到赐福：都不再算
        assert_eq!(w.step(false, 0, false, false, at(t0, 6000)), Ev::None);
        assert_eq!(w.step(true, 500, false, false, at(t0, 9000)), Ev::None);
        assert!(w.zero_at.is_none());
    }

    #[test]
    fn gift_revive_and_colosseum_skip() {
        let t0 = Instant::now();
        let mut w = Watch::default();
        w.step(true, 0, false, false, t0);
        // 血量 0 停了 1 秒多才复活（2026-11-14 的日志）：血量回来时身上有「刚复活」
        assert_eq!(w.step(true, 0, true, false, at(t0, 1200)), Ev::None);
        assert_eq!(w.step(true, 900, true, false, at(t0, 1300)), Ev::Skip("被馈赠复活顶掉了"));
        assert!(w.zero_at.is_none());
        // 一直 0、见过「刚复活」：到 HOLD 也不算
        w.step(true, 0, true, false, at(t0, 5000));
        assert_eq!(w.step(true, 0, false, false, at(t0, 7600)), Ev::Skip("被馈赠复活顶掉了"));
        w.step(true, 800, false, false, at(t0, 8000));
        // 斗技场里
        w.step(true, 0, false, true, at(t0, 9000));
        assert_eq!(w.step(true, 0, false, true, at(t0, 11600)), Ev::Skip("在斗技场里"));
    }

    #[test]
    fn short_zero_ignored_but_spectate_counts() {
        let t0 = Instant::now();
        let mut w = Watch::default();
        // 读图时一两帧 0
        w.step(true, 0, false, false, t0);
        assert_eq!(w.step(true, 700, false, false, at(t0, 100)), Ev::None);
        // 联机观战：0 停了 1 秒血量回来、没有「刚复活」
        w.step(true, 0, false, false, at(t0, 1000));
        w.step(true, 0, false, false, at(t0, 2000));
        assert!(matches!(w.step(true, 700, false, false, at(t0, 2100)), Ev::Died(_)));
        // 0 停够了人物没了（读图）：判一次；回来再清
        w.step(true, 0, false, false, at(t0, 3000));
        w.step(true, 0, false, false, at(t0, 3800));
        assert!(matches!(w.step(false, 0, false, false, at(t0, 3900)), Ev::Died(_)));
        assert_eq!(w.step(false, 0, false, false, at(t0, 9000)), Ev::None);
        assert_eq!(w.step(true, 700, false, false, at(t0, 12000)), Ev::None);
        // 不在场的时间不算进血量 0 的时间
        w.step(true, 0, false, false, at(t0, 13000));
        assert_eq!(w.step(false, 0, false, false, at(t0, 13100)), Ev::None);
        assert_eq!(w.step(true, 700, false, false, at(t0, 20000)), Ev::None);
    }

    #[test]
    fn items_line() {
        let base = "container\tw\t240000000\t10000\t2\t10\t\ncontainer\tp\t30000000\t100\t2\t10\t\ncontainer\ta\t20000\t1\t2\t10\t\n\
                    text\tN\t128\ntext\tI\t160\ntext\tC\t640\nlabel\tzh\tx\nlabel\ten\ty\ngoods\t2\t3\t8023\n\
                    deliver\t10900\t32\t93501\nidentify\t93502\nlotlayout\t44\t0\t32\t40\t36\t28\n";
        let pct = |extra: &str| parse_items(&format!("{base}{extra}")).map(|it| it.deathloss);
        assert_eq!(pct(""), Some(0.0));
        assert_eq!(pct("deathloss\t25\n"), Some(25.0));
        assert_eq!(pct("deathloss\t12.5\n"), Some(12.5));
        assert_eq!(pct("deathloss\t250\n"), Some(100.0));
        // 看不懂只当没有，别的定义照用
        assert_eq!(pct("deathloss\tx\n"), Some(0.0));
        if let Some((items, _)) = super::super::tests::real_defs() {
            eprintln!("真实 items.txt 的死亡惩罚：{}%", items.deathloss);
        }
    }

    #[test]
    fn follow_the_bloodstain() {
        let a = Stain { block: 0x3c2a2800, pos: [10, 20, 30], runes: 5000 };
        let b = Stain { runes: 800, ..a };
        let s = Duration::from_secs;
        // 刚扣掉：死后出现了新血迹（之前没有 / 之前是另一摊）才跟上
        assert_eq!(judge_fresh(Some(a), None, s(1)), Lost::Link);
        assert_eq!(judge_fresh(Some(b), Some(a), s(1)), Lost::Link);
        // 还是死之前那摊（献祭细枝）、或者一直没有血迹：等，等够了直接还
        assert_eq!(judge_fresh(Some(a), Some(a), s(10)), Lost::Wait);
        assert_eq!(judge_fresh(None, None, s(10)), Lost::Wait);
        assert_eq!(judge_fresh(Some(a), Some(a), NO_STAIN), Lost::NoStain);
        assert_eq!(judge_fresh(None, Some(a), NO_STAIN), Lost::NoStain);
        // 跟着的血迹：还在就等，没了 = 卢恩取回了，换成别的 = 没取回又死了
        assert_eq!(judge_linked(Some(a), a), Lost::Wait);
        assert_eq!(judge_linked(None, a), Lost::Back);
        assert_eq!(judge_linked(Some(b), a), Lost::Gone);
    }

    #[test]
    fn lost_record() {
        let text = "# 说明\nname\t褪色者\nstain\t1010040000\t12\t-34\t56\t2500\nbefore\t1\t2\t3\t4\t5\ng\t9203\t2\ng\t9212\t1\nf\t9221\t3\ng\tx\t1\nb\t9200\t11\n";
        let (lost, stain, fresh, before, back) = parse_lost(text, "褪色者").unwrap();
        assert_eq!(lost, vec![(9203, 2), (9212, 1)]);
        assert_eq!(stain, Some(Stain { block: 1010040000, pos: [12, -34, 56], runes: 2500 }));
        assert_eq!(fresh, vec![(9221, 3)]);
        assert_eq!(before, Some(Stain { block: 1, pos: [2, 3, 4], runes: 5 }));
        assert_eq!(back, vec![(9200, 11)]);
        // 别的角色的记录不认
        assert!(parse_lost(text, "别人").is_none());
        assert_eq!(total(&lost), 3);
        assert_eq!(fmt_list(&lost), "9203×2、9212×1");
    }

    /// deathback 行；每轮每种最多 per 件，不在种类里的不发；发完一轮减掉
    #[test]
    fn back_rounds() {
        let f: Vec<&str> = "deathback\t92640\t92641\t8\t9200,9201,9202".split('\t').collect();
        let b = Back::parse(&f).unwrap();
        assert_eq!((b.req, b.bit0, b.per, b.goods.clone()), (92640, 92641, 8, vec![9200, 9201, 9202]));
        assert_eq!((b.bit(0, 0), b.bit(1, 0), b.bit(2, 7)), (92641, 92649, 92664));
        assert!(Back::parse(&"deathback\t92640\t92641\t0\t9200".split('\t').collect::<Vec<_>>()).is_none());
        assert!(Back::parse(&"deathback\t92640\t92641\t8\t9200,x".split('\t').collect::<Vec<_>>()).is_none());
        let mut back = vec![(9201, 11), (9999, 2), (9200, 3)];
        assert_eq!(round_plan(&back, &b), vec![(1, 9201, 8), (0, 9200, 3)]);
        take_out(&mut back, 9201, 8);
        take_out(&mut back, 9200, 3);
        assert_eq!(back, vec![(9201, 3), (9999, 2)]);
        assert_eq!(round_plan(&back, &b), vec![(1, 9201, 3)]);
        let mut v = vec![(9200, 1)];
        add_to(&mut v, &[(9200, 2), (9201, 1)]);
        assert_eq!(v, vec![(9200, 3), (9201, 1)]);
    }

    #[test]
    fn count_and_pick() {
        assert_eq!(how_many(4, 25.0, 0.99), 1);
        assert_eq!(how_many(8, 25.0, 0.0), 2);
        assert_eq!(how_many(3, 25.0, 0.74), 1);
        assert_eq!(how_many(3, 25.0, 0.76), 0);
        assert_eq!(how_many(0, 25.0, 0.0), 0);
        assert_eq!(how_many(5, 100.0, 0.5), 5);
        assert_eq!(how_many(5, 0.0, 0.0), 0);
        let have = [(100u32, 10u32), (200, 1), (300, 5)];
        let mut rng = Rng(7);
        for k in [0u32, 1, 4, 16, 30] {
            let got = pick(&have, k, &mut rng);
            assert_eq!(got.iter().map(|x| x.1).sum::<u32>(), k.min(16));
            for (g, n) in got {
                assert!(n <= have.iter().find(|h| h.0 == g).unwrap().1);
            }
        }
        // 每件机会一样：编号 100 占 10/16，扣 1 件时大约 62.5% 落在它上面
        let mut hits = 0;
        for _ in 0..4000 {
            if pick(&have, 1, &mut rng)[0].0 == 100 {
                hits += 1;
            }
        }
        assert!((2300..2700).contains(&hits), "{hits}");
    }
}
