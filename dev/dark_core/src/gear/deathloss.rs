//! 死亡惩罚（用户 2026-11-19「加一下死亡惩罚 死亡时永久遗失身上25%的未鉴定装备」；比例是 items.txt 的 deathloss 行，
//! 重随 settings 的 death_penalty）：
//! - 认真死了没有（Watch）：血量 0 停了 HOLD 身上一直没有馈赠复活的「刚复活」效果；或者血量 0 停了 MIN_ZERO 以上又回来了、
//!   没见过「刚复活」（联机观战时血量会回来，同 arena.rs 的 death_tick）；或者血量 0 停够 MIN_ZERO 后人物没了（死亡画面后读图）。
//!   血量 0 的时间只数人物在场的时候。血量到 0 时在斗技场（m45：斗技场试炼、原版对战）的不算，试炼有自己的收回。
//! - 扣：背包（不含仓库）里的未鉴定道具一共 N 件，扣 N × 比例（不是整数时余下的部分按几率多扣一件），每件被挑中的机会一样。
//!   新装备正在发货（鉴定、许愿、赠送）时先欠着，发完再扣：发货核对还要扣掉换掉的未鉴定道具。回主菜单、换角色时欠着的作废。
//! - 扣掉了：血量回来、人物在场后原版闪烁提示 death loss（rr/notes.py）。
//! - 联机：只动自己的背包，各台电脑各算各的，不用房主定（联机计划 13.2 的 G 规则管的是敌人身上的效果和抽签）。
use std::time::{Duration, Instant};

use super::*;

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

/// 扣掉背包里的未鉴定道具，返回实际扣掉几件
fn apply(d: &Defs, pgd: &mut PlayerGameData, pct: f64, rng: &mut Rng) -> u32 {
    let have = unidentified(d, pgd);
    let total: u32 = have.iter().map(|x| x.1).sum();
    if total == 0 {
        log("死亡惩罚：背包里没有未鉴定物品，不扣");
        return 0;
    }
    let k = how_many(total, pct, unit(rng));
    if k == 0 {
        log(&format!("死亡惩罚：背包里未鉴定物品 {total} 件，按 {pct}% 这次没扣到"));
        return 0;
    }
    let mut gone = 0;
    let mut parts = Vec::new();
    for (g, n) in pick(&have, k, rng) {
        let got = remove_goods(pgd, g, n);
        gone += got;
        let name = d.items.goods.get(&g).map_or_else(|| format!("道具 {g}"), |&(c, t)| format!("{}（{}）", DIR_CAT_ZH.get(c).unwrap_or(&"?"), TIER_ZH.get(t).unwrap_or(&"?")));
        parts.push(if got == n { format!("{name}×{n}") } else { format!("{name}×{n}（只扣掉 {got}）") });
    }
    log(&format!("死亡惩罚：背包里未鉴定物品 {total} 件，按 {pct}% 扣 {k} 件：{}；实际扣掉 {gone} 件", parts.join("、")));
    gone
}

pub(super) fn tick(d: &Defs, st: &mut St, pgd: &mut PlayerGameData) {
    let pct = d.items.deathloss;
    if pct <= 0.0 {
        return;
    }
    let now = Instant::now();
    let me = unsafe { WorldChrMan::instance() }.ok().and_then(|w| w.main_player.as_ref()).map(|p| {
        let j = crate::curses::revive_just();
        let just = j > 0 && p.chr_ins.special_effect.entries().any(|x| x.param_id == j);
        (p.chr_ins.modules.data.hp, just, p.current_block_id.area() == COLOS_AREA)
    });
    let (present, hp, just, colos) = me.map_or((false, 0, false, false), |(h, j, c)| (true, h, j, c));
    match st.death.w.step(present, hp, just, colos, now) {
        Ev::Died(held) => {
            log(&format!("死亡惩罚：死了（血量 0 停了 {:.1} 秒），扣未鉴定物品", held.as_secs_f32()));
            st.death.owe = true;
        }
        Ev::Skip(why) => log(&format!("死亡惩罚：血量到 0，{why}，不扣")),
        Ev::None => {}
    }
    if !present {
        return;
    }
    if st.death.owe && st.pending.is_none() && st.gift_wait.is_none() {
        st.death.owe = false;
        let lost = apply(d, pgd, pct, &mut Rng::new());
        st.death.note |= lost > 0;
    }
    if st.death.note && hp > 0 && st.death.w.zero_at.is_none() && crate::notes::push("death loss") {
        st.death.note = false;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn at(t0: Instant, ms: u64) -> Instant {
        t0 + Duration::from_millis(ms)
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
