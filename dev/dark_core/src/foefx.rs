//! 敌人效果（通用模块；用户 2026-11-17「和斗技场结合 实现可以给任意指定波数敌人挂自定义效果」「可以抽象成一个通用模块」）。
//! 效果包定义 foefx.txt（重随 rr/foefx.py）：pack <包名> <动作速度> <效果,效果…|->（效果 = 效果行编号，自定义数值的行重随做好）。
//! 别的模块按实体编号登记（attach(来源, 实体, 效果)），不要了按来源放掉（release）。这里每 SCAN 扫一遍在场角色：
//! - 活着、身上缺了就挂（读图、休息清掉了也补）；第一次给这个角色挂之前记下血量 / 上限，之后上限变了、血量还停在原来那个数
//!   （挂最大血量倍率时游戏不按比例补当前血量），按原来的比例补上（同 hpunify.rs；刚出场满血的就是补满）；血量动过一次就不再管；
//!   联机时效果两台电脑各挂各的（敌人身上的效果不走网络同步，联机计划 13.9），补血只有房主写（客机 client_skip）；
//! - 动作速度报给 speed.rs（来源「敌人效果」，和时隙、减速、魇化相乘），联机只有房主写）；
//! - 放掉的、来源不再要的：下一轮扫到还在场的就摘掉我们挂的效果（别的来源还要的留着）、停掉速度；
//! - 登记以后 GIVEUP 还一次都没见到（没读进来 / 地图没放上）：写一行日志。
//! 没有登记、也没有挂着要摘的就不扫。斗技场试炼（arena.rs）用它挂每波的血量加成和 arena.txt 的 wfx 规则。

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{ChrIns, ChrInsExt, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

const SCAN: Duration = Duration::from_millis(250);
/// 登记了这么久还没见到这个实体：写一次日志
const GIVEUP: Duration = Duration::from_secs(20);
/// 挂上以后这么久里看血量上限变没变（之后不再补）
const WATCH_FOR: Duration = Duration::from_secs(10);
/// 前这么多次挂效果逐个写日志
const LOG_EACH: u32 = 40;
/// 动作速度在 speed.rs 里的来源名
const SPEED_TAG: &str = "敌人效果";

/// 要挂的：效果行 + 动作速度倍数（1 = 不改）
#[derive(Debug, Clone, PartialEq)]
pub struct Fx {
    pub sps: Vec<i32>,
    pub speed: f32,
}

impl Default for Fx {
    fn default() -> Self {
        Fx { sps: Vec::new(), speed: 1.0 }
    }
}

impl Fx {
    pub fn sp(sp: i32) -> Fx {
        Fx { sps: vec![sp], speed: 1.0 }
    }

    /// 合进来：效果取并集，速度相乘
    pub fn add(&mut self, o: &Fx) {
        for &s in &o.sps {
            if !self.sps.contains(&s) {
                self.sps.push(s);
            }
        }
        self.speed *= o.speed;
    }

    pub fn is_empty(&self) -> bool {
        self.sps.is_empty() && (self.speed - 1.0).abs() < 1e-6
    }
}

#[derive(Debug, Default, PartialEq)]
struct Def {
    packs: HashMap<String, Fx>,
}

static DEF: OnceLock<Def> = OnceLock::new();

fn parse(text: &str) -> Def {
    let mut d = Def::default();
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}').trim_end();
        if l.starts_with('#') || l.is_empty() {
            continue;
        }
        let f: Vec<&str> = l.split('\t').collect();
        if f[0] != "pack" || f.len() < 4 {
            continue;
        }
        let Ok(speed) = f[2].parse::<f32>() else { continue };
        let sps: Vec<i32> = f[3].split(',').filter_map(|x| x.trim().parse::<i32>().ok()).filter(|&x| x > 0).collect();
        d.packs.insert(f[1].to_string(), Fx { sps, speed: if speed.is_finite() { speed.clamp(0.0, 3.0) } else { 1.0 } });
    }
    d
}

fn def() -> &'static Def {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("foefx.txt")).unwrap_or_default()))
}

/// 效果包（没有这个包 None）
pub fn pack(name: &str) -> Option<Fx> {
    def().packs.get(name).cloned()
}

pub fn describe() -> String {
    let d = def();
    if d.packs.is_empty() {
        return "敌人效果包（没有 foefx.txt，只挂别的模块直接给的效果）".into();
    }
    let mut names: Vec<&str> = d.packs.keys().map(String::as_str).collect();
    names.sort_unstable();
    format!("敌人效果包 {} 个（{}）", names.len(), names.join("、"))
}

struct Entry {
    tag: &'static str,
    ent: u32,
    fx: Fx,
    since: Instant,
    seen: bool,
    warned: bool,
}

/// 我们给一个角色挂上的（摘的时候只摘这些）
struct On {
    ent: u32,
    npc: i32,
    sps: Vec<i32>,
    sped: bool,
}

#[derive(Default)]
struct St {
    next: Option<Instant>,
    entries: Vec<Entry>,
    on: HashMap<usize, On>,
    /// 角色地址 → (挂之前的血量, 上限, 挂的时间)
    watch: HashMap<usize, (i32, i32, Instant)>,
    logged: u32,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 给这个实体挂 fx（同一来源同一实体再登记就合进去）
pub fn attach(tag: &'static str, ent: u32, fx: &Fx) {
    if ent == 0 || fx.is_empty() {
        return;
    }
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    match st.entries.iter_mut().find(|e| e.tag == tag && e.ent == ent) {
        Some(e) => e.fx.add(fx),
        None => st.entries.push(Entry { tag, ent, fx: fx.clone(), since: Instant::now(), seen: false, warned: false }),
    }
}

/// 这个来源登记的全部放掉（还在场的下一轮摘掉效果、停掉速度）
pub fn release(tag: &'static str) {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(st) = g.as_mut() {
        st.entries.retain(|e| e.tag != tag);
    }
}

/// 各来源合起来：实体 → 要挂的
fn wanted(entries: &[Entry]) -> HashMap<u32, Fx> {
    let mut out: HashMap<u32, Fx> = HashMap::new();
    for e in entries {
        out.entry(e.ent).or_default().add(&e.fx);
    }
    out
}

/// 一个角色这一轮要做什么（纯函数，单元测试用）：on = 我们挂过的，has = 身上现在有没有，want = 要的（None = 不要了），alive = 血量 > 0。
/// 返回 (要挂的, 要摘的)
fn plan(on: &[i32], has: &dyn Fn(i32) -> bool, want: Option<&Fx>, alive: bool) -> (Vec<i32>, Vec<i32>) {
    let keep: &[i32] = want.map_or(&[], |w| w.sps.as_slice());
    let remove: Vec<i32> = on.iter().copied().filter(|sp| !keep.contains(sp) && has(*sp)).collect();
    let apply: Vec<i32> = if alive { keep.iter().copied().filter(|&sp| !has(sp)).collect() } else { Vec::new() };
    (apply, remove)
}

/// 挂上之后血量上限变了、血量还停在挂之前的数：按原来的比例该补到多少（None = 不用补）
fn refill(before: (i32, i32), hp: i32, max: i32) -> Option<i32> {
    let (h0, m0) = before;
    (hp == h0 && max != m0 && m0 > 0).then(|| ((h0 as f64 / m0 as f64) * max as f64).round().clamp(1.0, max.max(1) as f64) as i32)
}

fn each(wcm: &WorldChrMan, mut f: impl FnMut(&mut ChrIns)) {
    for s in wcm.chr_sets.iter().flatten() {
        s.characters().for_each(&mut f);
    }
    wcm.open_field_chr_set.base.characters().for_each(&mut f);
}

pub fn tick() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let Some(st) = g.as_mut() else { return };
    if st.entries.is_empty() && st.on.is_empty() {
        return;
    }
    let now = Instant::now();
    if st.next.is_some_and(|t| now < t) {
        return;
    }
    st.next = Some(now + SCAN);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let want = wanted(&st.entries);
    let mut seen_ent: HashSet<u32> = HashSet::new();
    let mut live: HashSet<usize> = HashSet::new();
    each(wcm, |c| {
        let a = c as *mut ChrIns as usize;
        live.insert(a);
        let ent = c.event_entity_id;
        // 这个地址换成别的角色了：旧记录作废（不往别人身上摘）
        if st.on.get(&a).is_some_and(|o| o.ent != ent || o.npc != c.npc_param_id) {
            st.on.remove(&a);
            st.watch.remove(&a);
        }
        let w = want.get(&ent);
        if w.is_none() && !st.on.contains_key(&a) {
            return;
        }
        seen_ent.insert(ent);
        let (hp, max) = (c.modules.data.hp, c.modules.data.max_hp);
        let alive = hp > 0;
        let on_sps: Vec<i32> = st.on.get(&a).map_or(Vec::new(), |o| o.sps.clone());
        let (apply, remove) = {
            let has = |sp: i32| c.special_effect.entries().any(|e| e.param_id == sp);
            plan(&on_sps, &has, w, alive)
        };
        for &sp in &remove {
            crate::coop::note(crate::coop::Op::Remove(sp), c);
            c.remove_speffect(sp);
        }
        if !apply.is_empty() {
            // 每次挂（含被清掉以后补挂）都记下挂之前的血量 / 上限：挂的是最大血量倍率时下面按比例补
            st.watch.insert(a, (hp, max, now));
            for &sp in &apply {
                crate::coop::note(crate::coop::Op::Apply(sp), c);
                c.apply_speffect(sp, false);
            }
            if st.logged < LOG_EACH {
                st.logged += 1;
                log(&format!("敌人效果：NPC {}（实体 {ent}）挂 {}，挂之前血 {hp} / {max}", c.npc_param_id,
                             apply.iter().map(|s| s.to_string()).collect::<Vec<_>>().join("、")));
            }
        }
        // 血量上限变了、血量还没动：按原比例补
        if let Some(&(h0, m0, t)) = st.watch.get(&a) {
            if !alive || hp != h0 || now - t > WATCH_FOR {
                st.watch.remove(&a);
            } else if let Some(v) = refill((h0, m0), hp, max) {
                st.watch.remove(&a);
                // 补血只让房主写（血量跟着房主那份同步；联机计划 13.2 G2）。效果本身两台电脑各挂各的（13.9）
                if !crate::coop::client_skip("敌人效果的按比例补血") {
                    c.modules.data.hp = v;
                    if st.logged < LOG_EACH {
                        st.logged += 1;
                        log(&format!("敌人效果：NPC {}（实体 {ent}）血量上限 {m0} → {max}，血量按比例补到 {v}", c.npc_param_id));
                    }
                }
            }
        }
        // 动作速度：活着、要改就每轮报一次（speed.rs 过了保持时间没再报就当不要了）
        let speed = w.map_or(1.0, |w| w.speed);
        let sped = alive && (speed - 1.0).abs() > 1e-6;
        if sped {
            crate::speed::want(c, SPEED_TAG, speed, crate::speed::HOLD_SCAN);
        } else if st.on.get(&a).is_some_and(|o| o.sped) {
            crate::speed::stop(a, SPEED_TAG);
        }
        // 记下我们挂着的
        let keep: Vec<i32> = on_sps.iter().copied().filter(|sp| !remove.contains(sp)).chain(apply.iter().copied()).collect();
        if keep.is_empty() && !sped && w.is_none() {
            st.on.remove(&a);
        } else {
            let o = st.on.entry(a).or_insert(On { ent, npc: c.npc_param_id, sps: Vec::new(), sped: false });
            o.sps = keep;
            o.sped = sped;
        }
    });
    st.on.retain(|a, _| live.contains(a));
    st.watch.retain(|a, _| live.contains(a));
    for e in st.entries.iter_mut() {
        if seen_ent.contains(&e.ent) {
            e.seen = true;
        } else if !e.seen && !e.warned && now - e.since > GIVEUP {
            e.warned = true;
            log(&format!("敌人效果：{} 登记的实体 {} 过了 {} 秒还没出现（没读进来？），效果先不挂", e.tag, e.ent, GIVEUP.as_secs()));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_packs() {
        let d = parse("# 头\npack\t狂暴\t1.2\t7311000,7311001\npack\t只加速\t1.5\t-\npack\t坏的\tx\t1\npack\t太快\t9\t7311002\n");
        assert_eq!(d.packs.get("狂暴"), Some(&Fx { sps: vec![7311000, 7311001], speed: 1.2 }));
        assert_eq!(d.packs.get("只加速"), Some(&Fx { sps: vec![], speed: 1.5 }));
        assert!(d.packs.get("坏的").is_none());
        assert_eq!(d.packs.get("太快").map(|f| f.speed), Some(3.0));
    }

    #[test]
    fn fx_merges() {
        let mut a = Fx { sps: vec![1, 2], speed: 1.2 };
        a.add(&Fx { sps: vec![2, 3], speed: 1.5 });
        assert_eq!(a.sps, vec![1, 2, 3]);
        assert!((a.speed - 1.8).abs() < 1e-6);
        assert!(Fx::default().is_empty() && !Fx::sp(5).is_empty());
    }

    #[test]
    fn plan_applies_missing_and_removes_unwanted() {
        let has_set = [1, 2, 9];
        let has = |sp: i32| has_set.contains(&sp);
        // 要 1、3：缺 3 就挂；我们挂过的 2 不要了、身上有 → 摘；9 不是我们挂的，不碰
        let (apply, remove) = plan(&[1, 2], &has, Some(&Fx { sps: vec![1, 3], speed: 1.0 }), true);
        assert_eq!((apply, remove), (vec![3], vec![2]));
        // 死了：不挂新的；放掉了：我们挂的全摘
        assert_eq!(plan(&[1], &has, Some(&Fx::sp(3)), false), (vec![], vec![1]));
        assert_eq!(plan(&[1, 2, 4], &has, None, true), (vec![], vec![1, 2]));
    }

    #[test]
    fn refill_keeps_ratio() {
        assert_eq!(refill((1000, 1000), 1000, 1300), Some(1300));     // 满血出场 → 补满
        assert_eq!(refill((500, 1000), 500, 2000), Some(1000));       // 半血 → 还是一半
        assert_eq!(refill((1000, 1000), 990, 1300), None);            // 挨过打了：不管
        assert_eq!(refill((1000, 1000), 1000, 1000), None);           // 上限没变
    }

    #[test]
    fn wanted_merges_sources() {
        let t = Instant::now();
        let e = |tag, ent, fx: Fx| Entry { tag, ent, fx, since: t, seen: false, warned: false };
        let w = wanted(&[e("a", 7, Fx::sp(1)), e("b", 7, Fx { sps: vec![2], speed: 1.5 }), e("a", 8, Fx::sp(3))]);
        assert_eq!(w[&7], Fx { sps: vec![1, 2], speed: 1.5 });
        assert_eq!(w[&8], Fx::sp(3));
    }
}
