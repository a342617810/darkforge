//! 联机的远程命中归属（联机计划 13.7；用户 2026-11-16「按这个改」）：敌人身上新出现的子弹命中标记（箭、投掷道具、法术）是不是你打的。
//! 游戏里每颗飞行中的子弹都记着是谁放的（CSBulletManager 的 owner_chr_handle）。联机时每帧记下玩家放出的子弹位置
//! （你的 / 队友的，保留 MEMORY），新标记出现时：
//! - 最近有你的子弹到过这个敌人 REACH 米内 → 你的；
//! - 只有队友的子弹到过 → 队友的；
//! - 谁的都没记到（贴脸射击一帧都没记到、敌人不在你所在的大区）→ 退回「最近你放过远程」（rules::own_ranged）。
//! 只看子弹是谁放的，不看敌人「最后被谁打中」、不比谁离得近；近战另看连击值（rules::own_melee）。
//! 物理坐标只在同一大区里能直接比（chrs.rs），所以只认你所在大区的敌人。思路借鉴黄金树爬塔的 embers.rs，代码自己写。
//! 日志（用户 2026-11-16「补上日志」）：每次判定写一行为什么（同一个敌人 LOG_GAP 内结果不变不重复写，一次会话最多 LOG_MAX 行），
//! 会话里每分钟一行统计（记到你的 / 队友的子弹各几颗，判了几次、各走哪条路）。

use std::collections::hash_map::DefaultHasher;
use std::collections::{HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::{CSBulletManager, ChrIns, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::log;

/// 子弹记多久、离敌人多远内算到过它身边
const MEMORY: Duration = Duration::from_millis(700);
const REACH: f32 = 6.0;
/// 判定日志：同一个敌人这么久内结果不变不重复写；一次会话最多写几行
const LOG_GAP: Duration = Duration::from_secs(3);
const LOG_MAX: u32 = 60;
/// 统计行的间隔
const SUMMARY: Duration = Duration::from_secs(60);

/// 一条子弹记录：时间、位置、是不是你放的、哪颗子弹（句柄的哈希，统计「几颗」用）
#[derive(Clone, Copy)]
pub(crate) struct Shot {
    pub at: Instant,
    pub pos: [f32; 3],
    pub mine: bool,
    pub id: u64,
}

/// 判定走的哪条路（日志用）
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Why {
    /// 你的子弹到过（几颗）
    Own(usize),
    /// 只有队友的子弹到过（几颗）
    Mate(usize),
    /// 谁的都没记到它身边
    NoRecord,
    /// 它不在你所在的大区
    OtherArea,
}

#[derive(Default)]
struct Stats {
    mine: HashSet<u64>,
    mate: HashSet<u64>,
    own: u32,
    mate_n: u32,
    fallback_yes: u32,
    fallback_no: u32,
}

#[derive(Default)]
struct St {
    shots: Vec<Shot>,
    /// 你所在的大区（记子弹那一帧的）
    area: Option<u8>,
    /// 这次会话里开始记了没有（日志「开始记」只写一次）
    on: bool,
    logged: u32,
    /// 敌人地址 → (上次写判定日志的时间, 结果)
    last_log: HashMap<usize, (Instant, bool)>,
    stats: Stats,
    summary_at: Option<Instant>,
}

/// 不在会话里是 None（什么都不留）
static ST: Mutex<Option<St>> = Mutex::new(None);

fn dist(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

fn hash_of(h: &impl Hash) -> u64 {
    let mut s = DefaultHasher::new();
    h.hash(&mut s);
    s.finish()
}

fn summary_line(s: &Stats) -> Option<String> {
    if s.mine.is_empty() && s.mate.is_empty() && s.own + s.mate_n + s.fallback_yes + s.fallback_no == 0 {
        return None;
    }
    Some(format!("联机子弹记录：这 1 分钟记到你的子弹 {} 颗、队友的 {} 颗；远程归属判了 {} 次：你的子弹到过 {}、只有队友的 {}、没记到退回看你放没放过远程 {}（算 {} / 不算 {}）",
                 s.mine.len(), s.mate.len(), s.own + s.mate_n + s.fallback_yes + s.fallback_no, s.own, s.mate_n,
                 s.fallback_yes + s.fallback_no, s.fallback_yes, s.fallback_no))
}

/// 每帧（lib.rs，积木引擎、咒痕之前）：联机时记玩家放出的子弹；不在会话里清空、什么都不读
pub fn tick() {
    let mut guard = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    if !crate::coop::active() {
        if let Some(g) = guard.take().filter(|g| g.on) {
            if let Some(l) = summary_line(&g.stats) {
                log(&l);
            }
            log("联机子弹记录：不在会话里了，停止记录");
        }
        return;
    }
    let g = guard.get_or_insert_with(St::default);
    if !g.on {
        g.on = true;
        g.logged = 0;
        g.summary_at = Some(now + SUMMARY);
        log(&format!("联机子弹记录：进了会话，开始记玩家放出的子弹（记 {} 毫秒，离敌人 {REACH} 米内算到过它身边）", MEMORY.as_millis()));
    }
    if g.summary_at.is_some_and(|t| now >= t) {
        if let Some(l) = summary_line(&g.stats) {
            log(&l);
        }
        g.stats = Stats::default();
        g.summary_at = Some(now + SUMMARY);
        g.last_log.retain(|_, v| now.duration_since(v.0) < SUMMARY);
    }
    g.shots.retain(|x| now.duration_since(x.at) <= MEMORY);
    let Ok(w) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(me) = w.main_player.as_ref().map(|p| (p.chr_ins.field_ins_handle, p.chr_ins.block_id.area())) else { return };
    g.area = Some(me.1);
    let players: Vec<_> = w.player_chr_set.characters().map(|p| p.chr_ins.field_ins_handle).collect();
    let Ok(m) = (unsafe { CSBulletManager::instance() }) else { return };
    for b in m.bullets() {
        let owner = b.targeting_owner.owner_chr_handle;
        if owner == me.0 || players.contains(&owner) {
            let q = &b.physics.position;
            let id = hash_of(&b.field_ins_handle);
            let mine = owner == me.0;
            g.shots.push(Shot { at: now, pos: [q.0, q.1, q.2], mine, id });
            if mine {
                g.stats.mine.insert(id);
            } else {
                g.stats.mate.insert(id);
            }
        }
    }
    if g.shots.len() > 1024 {
        let n = g.shots.len() - 1024;
        g.shots.drain(..n);
    }
}

/// 判断（纯函数，单元测试用）：same_area = 敌人在你所在的大区；fired_recent = 最近你放过远程（找不到子弹记录时用）
pub(crate) fn ranged_rule(foe: [f32; 3], same_area: bool, shots: &[Shot], now: Instant, fired_recent: bool) -> (bool, Why) {
    if !same_area {
        return (fired_recent, Why::OtherArea);
    }
    let (mut mine, mut mate) = (HashSet::new(), HashSet::new());
    for s in shots.iter().filter(|s| now.saturating_duration_since(s.at) <= MEMORY && dist(foe, s.pos) <= REACH) {
        if s.mine {
            mine.insert(s.id);
        } else {
            mate.insert(s.id);
        }
    }
    if !mine.is_empty() {
        (true, Why::Own(mine.len()))
    } else if !mate.is_empty() {
        (false, Why::Mate(mate.len()))
    } else {
        (fired_recent, Why::NoRecord)
    }
}

fn why_text(why: Why, mine: bool) -> String {
    let fb = if mine { "你 5 秒内放过远程，算你的" } else { "你 5 秒内没放过远程，不算" };
    match why {
        Why::Own(n) => format!("算你的：最近 {} 毫秒有你的子弹到过它 {REACH} 米内（{n} 颗）", MEMORY.as_millis()),
        Why::Mate(n) => format!("不算：最近到过它身边的只有队友的子弹（{n} 颗）"),
        Why::NoRecord => format!("谁的子弹都没记到它身边，{fb}"),
        Why::OtherArea => format!("它不在你所在的大区（坐标没法比），{fb}"),
    }
}

/// 联机时这个敌人身上新出现的子弹标记算不算你打的（不在会话里一律算）。who = 谁在问（日志用：积木引擎 / 咒痕）
pub(crate) fn ranged_mine(c: &ChrIns, fired_recent: bool, who: &str) -> bool {
    if !crate::coop::active() {
        return true;
    }
    let now = Instant::now();
    let mut guard = ST.lock().unwrap_or_else(|e| e.into_inner());
    let g = guard.get_or_insert_with(St::default);
    let q = &c.modules.physics.position;
    let (mine, why) = ranged_rule([q.0, q.1, q.2], g.area == Some(c.block_id.area()), &g.shots, now, fired_recent);
    let addr = c as *const ChrIns as usize;
    let fresh = g.last_log.get(&addr).map_or(true, |v| now.duration_since(v.0) >= LOG_GAP || v.1 != mine);
    if fresh {
        match why {
            Why::Own(_) => g.stats.own += 1,
            Why::Mate(_) => g.stats.mate_n += 1,
            _ if mine => g.stats.fallback_yes += 1,
            _ => g.stats.fallback_no += 1,
        }
        g.last_log.insert(addr, (now, mine));
        if g.logged < LOG_MAX {
            g.logged += 1;
            log(&format!("{who}（联机）：NPC {}（实体 {}）身上新的子弹命中标记{}{}", c.npc_param_id, c.event_entity_id, why_text(why, mine),
                         if g.logged == LOG_MAX { "；这次会话的归属日志记满了，后面只在每分钟的统计里" } else { "" }));
        }
    }
    mine
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(at: Instant, x: f32, mine: bool, id: u64) -> Shot {
        Shot { at, pos: [x, 0.0, 0.0], mine, id }
    }

    #[test]
    fn own_bullet_then_teammate_then_fallback() {
        let now = Instant::now();
        let foe = [20.0, 0.0, 0.0];
        assert_eq!(ranged_rule(foe, true, &[s(now, 19.0, true, 1)], now, false), (true, Why::Own(1)), "你的箭到过它身边：你的");
        assert_eq!(ranged_rule(foe, true, &[s(now, 18.0, true, 1), s(now, 20.5, false, 2)], now, false), (true, Why::Own(1)), "你和队友的都到过：算你的");
        assert_eq!(ranged_rule(foe, true, &[s(now, 20.5, false, 2)], now, true), (false, Why::Mate(1)), "只有队友的箭到过：队友的（你最近放过远程也不算）");
        assert_eq!(ranged_rule(foe, true, &[], now, true), (true, Why::NoRecord), "谁的都没记到（贴脸射击）：退回最近放过远程");
        assert_eq!(ranged_rule(foe, true, &[], now, false), (false, Why::NoRecord), "谁的都没记到、你也没放过：不算");
        assert_eq!(ranged_rule(foe, false, &[s(now, 20.5, false, 2)], now, true), (true, Why::OtherArea), "不在你所在的大区：坐标不能比，退回最近放过远程");
        assert_eq!(ranged_rule(foe, true, &[s(now, 0.0, true, 1)], now, true), (true, Why::NoRecord), "你的子弹离得远：没记到它身边，退回最近放过远程");
        let old = now - Duration::from_secs(2);
        assert_eq!(ranged_rule(foe, true, &[s(old, 20.0, true, 1), s(now, 20.5, false, 2)], now, true), (false, Why::Mate(1)), "你的那颗是 2 秒前的，过期");
        // 同一颗子弹记了好几帧：算一颗
        let frames = [s(now, 19.0, true, 7), s(now, 19.5, true, 7), s(now, 20.0, true, 7), s(now, 21.0, true, 8)];
        assert_eq!(ranged_rule(foe, true, &frames, now, false), (true, Why::Own(2)));
    }

    #[test]
    fn summary_only_when_something_happened() {
        assert!(summary_line(&Stats::default()).is_none());
        let mut st = Stats::default();
        st.mate.insert(3);
        st.fallback_no = 1;
        let l = summary_line(&st).unwrap();
        assert!(l.contains("你的子弹 0 颗、队友的 1 颗") && l.contains("判了 1 次"), "{l}");
    }
}
