//! 超限锻造石的掉落（参数侧 rr/overlimit.py；设计稿 dev\item_system\超限锻造石与高难度.md §2）：只在标了 lock 的难度档
//! （「死亡」「不可能」，当前档标记亮着）里——
//! - Boss：每场 Boss 战（击败标记，data\boss_overlimit_flags.json）在每一档只掉一次：击败标记从灭变亮、这一档的「掉过」标记还没亮，
//!   就发货并点亮它。tier 行的 boss 颗数：1 = 武器 / 防具随机一颗，2 = 各一颗；掉落追忆的头目（rem 行的击败标记）按 tier 行第 5 项的颗数
//!   （用户 2026-11-09「死亡追忆boss掉10个两种碎片吧 不可能20个」）。
//!   进这几档、读档以后先把现在的状态记下来（SETTLE 之后），不算——已经打过的不补发；复活后在同一档再打不再掉。
//! - 小怪：游戏距离列表（见 chrs.rs）里的敌对角色（range 0 = 不限距离，用户 2026-11-05：远程打死的也算），血量从大于 0 变成 0 就算死了（不要求是玩家打死的，用户定），
//!   按档掷几率给 1 颗（武器 / 防具各一半）。Boss 位置的实体（bossent）、Boss 战的召唤物和训练木桩（nodrop）不算。
//! - 骨灰（rr/ashcont.py 的 boss_drop，用户 2026-11-10「死亡模式下每个boss都会掉落随机骨灰」）：Boss 战在这一档第一次击败时（同上面的
//!   掉过标记），另外发 ash 行这一档的个数个骨灰：直接是带稀有度、词条的容器（gear\ashes.rs，2026-11-11 起）；发不出容器的
//!   照旧从 ashes 行随机挑原版骨灰（+0），进背包后再换。
//! - 发货走 gear 的 gift_n（发货表 + 公共事件，游戏里弹「获得物品」）。
//! 每 SCAN 扫一次（距离列表两次调用隔太久会重新等就绪，见 chrs.rs 的 GAP）；不在这几档时什么都不做。联机先不管。
//! 定义 ovldrop.txt：tier 当前档标记 boss颗数 小怪几率% [追忆头目颗数]；rem 追忆头目战的击败标记…；goods 武器石 防具石；range 米；boss 击败标记 各档的掉过标记…；bossent 实体…；nodrop 敌人参数…；
//! ash 各档骨灰个数…；ashes 原版骨灰编号…

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use eldenring::cs::WorldChrMan;
use fromsoftware_shared::FromStatic;

use crate::gear::{flag_get, flag_set, gift_n};
use crate::rules::is_foe;
use crate::{dir, log};

const SCAN: Duration = Duration::from_millis(250);
/// 进存档 / 进这几档多久以后才开始记 Boss 的状态（读档时标记会变）
const SETTLE: Duration = Duration::from_secs(3);

#[derive(Debug, Default, PartialEq)]
struct Def {
    /// (当前档标记, Boss 给几颗, 小怪几率 %)
    tiers: Vec<(u32, u32, f32)>,
    /// 各档掉落追忆的头目给几颗（tier 行没写就同 Boss 的）
    rem_n: Vec<u32>,
    /// 掉落追忆的头目战的击败标记
    rem: HashSet<u32>,
    goods: [i32; 2],
    range: f32,
    /// (击败标记, 各档的掉过标记)
    bosses: Vec<(u32, Vec<u32>)>,
    bossent: HashSet<u32>,
    nodrop: HashSet<i32>,
    /// 各档 Boss 战第一次击败掉几个骨灰；随机挑的原版骨灰（+0 的道具编号）
    ash_n: Vec<u32>,
    ashes: Vec<i32>,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn parse(text: &str) -> Option<Def> {
    let mut d = Def { range: 30.0, ..Def::default() };
    for l in text.lines() {
        let f: Vec<&str> = l.trim_start_matches('\u{feff}').split_whitespace().collect();
        let nums = |from: usize| -> Vec<u32> { f.iter().skip(from).filter_map(|x| x.parse().ok()).collect() };
        match f.first().copied() {
            Some("tier") if f.len() >= 4 => {
                if let (Ok(a), Ok(b), Ok(c)) = (f[1].parse(), f[2].parse(), f[3].parse()) {
                    d.tiers.push((a, b, c));
                    d.rem_n.push(f.get(4).and_then(|x| x.parse().ok()).unwrap_or(b));
                }
            }
            Some("goods") if f.len() >= 3 => d.goods = [f[1].parse().ok()?, f[2].parse().ok()?],
            Some("range") if f.len() >= 2 => d.range = f[1].parse().ok()?,
            Some("boss") if f.len() >= 3 => {
                let v = nums(1);
                if v.len() == f.len() - 1 {
                    d.bosses.push((v[0], v[1..].to_vec()));
                }
            }
            Some("bossent") => d.bossent.extend(nums(1)),
            Some("rem") => d.rem.extend(nums(1)),
            Some("nodrop") => d.nodrop.extend(nums(1).into_iter().map(|x| x as i32)),
            Some("ash") => d.ash_n = nums(1),
            Some("ashes") => d.ashes.extend(nums(1).into_iter().map(|x| x as i32)),
            _ => {}
        }
    }
    let n = d.tiers.len();
    d.bosses.retain(|b| b.1.len() == n);
    (n > 0 && d.goods.iter().all(|&g| g > 0)).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("ovldrop.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!(
            "超限锻造石掉落（{} 档，Boss 战 {} 场（追忆 {} 场），小怪 {} 米内；Boss 掉骨灰 {:?} 个，{} 种里随机）",
            d.tiers.len(),
            d.bosses.len(),
            d.rem.len(),
            d.range,
            d.ash_n,
            d.ashes.len()
        ),
        None => "超限锻造石掉落（没有 ovldrop.txt，不管）".into(),
    }
}

const SEEN_MIN: Duration = Duration::from_secs(3);

struct St {
    next: Instant,
    /// 现在在第几档（tiers 的序号）和从什么时候起
    tier: Option<(usize, Instant)>,
    /// Boss 击败标记上一次看到的状态（SETTLE 之后才记）
    boss: HashMap<u32, bool>,
    /// 附近敌人上一次看到的血量（按地址）
    hp: HashMap<usize, i32>,
    /// 第一次看到的时间：读图时被事件直接弄死的（看到不到 SEEN_MIN）不算
    first: HashMap<usize, Instant>,
    rng: u64,
    mobs: u32,
    stones: u32,
    ashes: u32,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

impl St {
    fn roll(&mut self) -> u64 {
        self.rng = self.rng.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.rng;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

/// 发 n 颗：n = 1 武器 / 防具随机，n ≥ 2 两种轮流（第一颗随机）
fn give(d: &Def, st: &mut St, n: u32, why: &str) {
    let first = (st.roll() % 2) as usize;
    let mut cnt = [0u32; 2];
    for i in 0..n as usize {
        cnt[(first + i) % 2] += 1;
    }
    for (k, &c) in cnt.iter().enumerate() {
        if c > 0 && !gift_n(1, d.goods[k], c) {
            log("超限锻造石掉落：没有发货表，没发");
            return;
        }
    }
    st.stones += n;
    log(&format!("超限锻造石掉落：{why} → 武器石 {}、防具石 {}（这次进游戏累计 {} 颗）", cnt[0], cnt[1], st.stones));
}

/// Boss 战第一次在第 t 档被击败：直接发带稀有度、词条的骨灰容器（gear\ashes.rs，种类随机、稀有度照规则抽；
/// 用户 2026-11-11「去掉原版骨灰的掉落 … 以我们的作为替换」）。容器发不出（骨灰稀有度没开、容器满了）的照旧随机挑原版骨灰发
fn give_ash(d: &Def, st: &mut St, t: usize, defeat: u32) {
    let n = d.ash_n.get(t).copied().unwrap_or(0);
    if d.ashes.is_empty() || n == 0 {
        return;
    }
    let (lines, ids) = crate::gear::give_ashes_rolled(n);
    for l in &lines {
        log(&format!("骨灰掉落：Boss 战 {defeat} 第一次在这一档被击败 → {l}"));
    }
    st.ashes += ids.len() as u32;
    for _ in ids.len() as u32..n {
        let id = d.ashes[(st.roll() % d.ashes.len() as u64) as usize];
        if !gift_n(1, id, 1) {
            log("骨灰掉落：没有发货表，没发");
            return;
        }
        st.ashes += 1;
        log(&format!("骨灰掉落：Boss 战 {defeat} 第一次在这一档被击败 → 原版骨灰 {id}（进背包后换成带稀有度的；这次进游戏累计 {} 个）", st.ashes));
    }
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St {
        next: now,
        tier: None,
        boss: HashMap::new(),
        hp: HashMap::new(),
        first: HashMap::new(),
        rng: SystemTime::now().duration_since(UNIX_EPOCH).map_or(1, |t| t.as_nanos() as u64),
        mobs: 0,
        stones: 0,
        ashes: 0,
    });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_ref() else {
        st.tier = None;
        st.boss.clear();
        st.hp.clear();
        return;
    };
    let me = &p.chr_ins as *const _ as usize;
    let my_team = p.chr_ins.team_type;
    let cur = d.tiers.iter().position(|t| flag_get(t.0) == Some(true));
    match (cur, st.tier) {
        (None, _) => {
            st.tier = None;
            st.boss.clear();
            st.hp.clear();
            return;
        }
        (Some(t), Some((t0, _))) if t == t0 => {}
        (Some(t), _) => {
            st.tier = Some((t, now));
            st.boss.clear();
            st.hp.clear();
            log(&format!("超限锻造石掉落：在第 {} 档（标记 {}），开始算掉落", t + 1, d.tiers[t].0));
        }
    }
    let Some((t, since)) = st.tier else { return };
    if now - since < SETTLE {
        return;
    }
    let (_, boss_n, pct) = d.tiers[t];
    // Boss：击败标记从灭变亮
    for (defeat, got) in &d.bosses {
        let Some(on) = flag_get(*defeat) else { continue };
        let was = st.boss.insert(*defeat, on);
        if on && was == Some(false) && flag_get(got[t]) == Some(false) {
            flag_set(got[t], true);
            let rem = d.rem.contains(defeat);
            let n = if rem { d.rem_n.get(t).copied().unwrap_or(boss_n) } else { boss_n };
            give(d, st, n, &format!("{}Boss 战 {defeat} 第一次在这一档被击败", if rem { "追忆 " } else { "" }));
            give_ash(d, st, t, *defeat);
            crate::curses::on_boss_first(*defeat); // 七咒：这个区域的碎片
        }
    }
    // 小怪：附近的敌对角色血量从大于 0 变成 0
    let Some(around) = around!(wcm, me) else { return };
    let mut seen = HashSet::new();
    for e in &around {
        let a = e.chr_ins.as_ptr() as usize;
        if a == me || (d.range > 0.0 && e.distance > d.range) {
            continue;
        }
        let c = unsafe { e.chr_ins.as_ref() };
        if !is_foe(c, my_team) {
            continue;
        }
        let hp = c.modules.data.hp;
        seen.insert(a);
        let was = st.hp.insert(a, hp);
        let first = *st.first.entry(a).or_insert(now);
        // 魇化精英的石头在 nightmare.rs 按精英的几率掉
        if hp <= 0
            && was.is_some_and(|x| x > 0)
            && now.duration_since(first) >= SEEN_MIN
            && !d.bossent.contains(&c.event_entity_id)
            && !d.nodrop.contains(&c.npc_param_id)
            && !crate::nightmare::is_elite(a)
        {
            st.mobs += 1;
            let r = (st.roll() % 10000) as f32;
            if r < pct * 100.0 {
                give(d, st, 1, &format!("NPC {}（实体 {}）死了（第 {} 只）", c.npc_param_id, c.event_entity_id, st.mobs));
            }
        }
    }
    st.hp.retain(|a, _| seen.contains(a));
    st.first.retain(|a, _| seen.contains(a));
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 定义：档、石头、范围、Boss（掉过标记的个数要和档数一样，不一样的丢掉）、排除的实体 / 敌人参数
    #[test]
    fn parse_def() {
        let d = parse("# x\ntier 9956 1 10\ntier 9957 2 20\ngoods 9242 9243\nrange 25\nboss 10000800 10007995 10007994\nboss 1 2\nbossent 10000800 10000850\nnodrop 56009900\n").unwrap();
        assert_eq!(d.tiers, vec![(9956, 1, 10.0), (9957, 2, 20.0)]);
        assert_eq!(d.rem_n, vec![1, 2], "没写追忆颗数就同 Boss 的");
        let r = parse("tier 9956 5 10 10\ntier 9957 10 20 20\ngoods 9242 9243\nrem 10000800 11000800\n").unwrap();
        assert_eq!((r.rem_n.clone(), r.rem.contains(&10000800), r.rem.contains(&10000850)), (vec![10, 20], true, false));
        assert_eq!((d.goods, d.range), ([9242, 9243], 25.0));
        assert_eq!(d.bosses, vec![(10000800, vec![10007995, 10007994])]);
        assert!(d.bossent.contains(&10000850) && d.nodrop.contains(&56009900));
        assert!(parse("goods 9242 9243\n").is_none());
        assert!(d.ash_n.is_empty() && d.ashes.is_empty(), "没写骨灰就不掉");
        let a = parse("tier 9956 5 10 10\ntier 9957 10 20 20\ngoods 9242 9243\nash 1 2\nashes 200000 232000\nashes 2200000\n").unwrap();
        assert_eq!((a.ash_n.clone(), a.ashes.clone()), (vec![1, 2], vec![200000, 232000, 2200000]));
    }
}
