//! 联机的远程命中归属（联机计划 13.7；用户 2026-11-16「按这个改」）：敌人身上新出现的子弹命中标记（箭、投掷道具、法术）是不是你打的。
//! 游戏里每颗飞行中的子弹都记着是谁放的（CSBulletManager 的 owner_chr_handle）。联机时每帧记下玩家放出的子弹位置
//! （你的 / 队友的，保留 MEMORY），新标记出现时：
//! - 最近有你的子弹到过这个敌人 REACH 米内 → 你的；
//! - 只有队友的子弹到过 → 队友的；
//! - 谁的都没记到（贴脸射击一帧都没记到、敌人不在你所在的大区）→ 退回「最近你放过远程」（rules::own_ranged）。
//! 只看子弹是谁放的，不看敌人「最后被谁打中」、不比谁离得近；近战另看连击值（rules::own_melee）。
//! 物理坐标只在同一大区里能直接比（chrs.rs），所以只认你所在大区的敌人。思路借鉴黄金树爬塔的 embers.rs，代码自己写。

use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::{CSBulletManager, ChrIns, WorldChrMan};
use fromsoftware_shared::FromStatic;

/// 子弹记多久、离敌人多远内算到过它身边
const MEMORY: Duration = Duration::from_millis(700);
const REACH: f32 = 6.0;

/// (时间, 位置, 是不是你放的)
static SHOTS: Mutex<Vec<(Instant, [f32; 3], bool)>> = Mutex::new(Vec::new());
/// 你所在的大区（记子弹那一帧的）
static AREA: Mutex<Option<u8>> = Mutex::new(None);

fn dist(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

/// 每帧（lib.rs，积木引擎、咒痕之前）：联机时记玩家放出的子弹；不在会话里清空、什么都不读
pub fn tick() {
    let mut g = SHOTS.lock().unwrap_or_else(|e| e.into_inner());
    if !crate::coop::active() {
        g.clear();
        return;
    }
    let now = Instant::now();
    g.retain(|x| now.duration_since(x.0) <= MEMORY);
    let Ok(w) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(me) = w.main_player.as_ref().map(|p| (p.chr_ins.field_ins_handle, p.chr_ins.block_id.area())) else { return };
    *AREA.lock().unwrap_or_else(|e| e.into_inner()) = Some(me.1);
    let players: Vec<_> = w.player_chr_set.characters().map(|p| p.chr_ins.field_ins_handle).collect();
    let Ok(m) = (unsafe { CSBulletManager::instance() }) else { return };
    for b in m.bullets() {
        let owner = b.targeting_owner.owner_chr_handle;
        if owner == me.0 || players.contains(&owner) {
            let q = &b.physics.position;
            g.push((now, [q.0, q.1, q.2], owner == me.0));
        }
    }
    if g.len() > 1024 {
        let n = g.len() - 1024;
        g.drain(..n);
    }
}

/// 判断（纯函数，单元测试用）：same_area = 敌人在你所在的大区；fired_recent = 最近你放过远程（找不到子弹记录时用）
pub(crate) fn ranged_rule(foe: [f32; 3], same_area: bool, shots: &[(Instant, [f32; 3], bool)], now: Instant, fired_recent: bool) -> bool {
    if same_area {
        let near: Vec<bool> = shots.iter().filter(|s| now.saturating_duration_since(s.0) <= MEMORY && dist(foe, s.1) <= REACH).map(|s| s.2).collect();
        if near.iter().any(|&m| m) {
            return true;
        }
        if !near.is_empty() {
            return false;
        }
    }
    fired_recent
}

/// 联机时这个敌人身上新出现的子弹标记算不算你打的（不在会话里一律算）
pub(crate) fn ranged_mine(c: &ChrIns, fired_recent: bool) -> bool {
    if !crate::coop::active() {
        return true;
    }
    let area = *AREA.lock().unwrap_or_else(|e| e.into_inner());
    let q = &c.modules.physics.position;
    let g = SHOTS.lock().unwrap_or_else(|e| e.into_inner());
    ranged_rule([q.0, q.1, q.2], area == Some(c.block_id.area()), &g, Instant::now(), fired_recent)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn own_bullet_then_teammate_then_fallback() {
        let now = Instant::now();
        let foe = [20.0, 0.0, 0.0];
        assert!(ranged_rule(foe, true, &[(now, [19.0, 0.0, 0.0], true)], now, false), "你的箭到过它身边：你的");
        assert!(ranged_rule(foe, true, &[(now, [18.0, 0.0, 0.0], true), (now, [20.5, 0.0, 0.0], false)], now, false), "你和队友的都到过：算你的");
        assert!(!ranged_rule(foe, true, &[(now, [20.5, 0.0, 0.0], false)], now, true), "只有队友的箭到过：队友的（你最近放过远程也不算）");
        assert!(ranged_rule(foe, true, &[], now, true), "谁的都没记到（贴脸射击）：退回最近放过远程");
        assert!(!ranged_rule(foe, true, &[], now, false), "谁的都没记到、你也没放过：不算");
        assert!(ranged_rule(foe, false, &[(now, [20.5, 0.0, 0.0], false)], now, true), "不在你所在的大区：坐标不能比，退回最近放过远程");
        assert!(ranged_rule(foe, true, &[(now, [0.0, 0.0, 0.0], true)], now, true), "你的子弹离得远：没记到它身边，退回最近放过远程");
        let old = now - Duration::from_secs(2);
        assert!(!ranged_rule(foe, true, &[(old, [20.0, 0.0, 0.0], true), (now, [20.5, 0.0, 0.0], false)], now, true), "你的那颗是 2 秒前的，过期");
    }
}
