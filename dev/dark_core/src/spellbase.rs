//! 法器面板给法球用（用户 2026-11-03「法球发射能吃法杖的魔法加成」，2026-11-06「*3 的那部分不动 然后把稀有度倍率改成面板倍率」「面板除200吧」）：
//! 法球（迸发、星群）是 dark_core 放的固定伤害，不吃法杖补正。rules.rs 的 burst_spell 规则乘 orb_factor()：
//! 左右手拿着的法器（原版的也算）里，法术补正面板最高的那件 ÷ PANEL_DIV；没拿法器按面板的基数 100 算（0.5），换成近战武器不会反而更高。
//! 智力倍率是另外的 procs 模块，也乘，所以智力算两遍是用户定的。
//! 面板 = 100 + Σ 补正值 × 强化系数 × 补正曲线(属性)% ÷ 100（五项属性，元素表 AttackElementCorrectParam 说这种伤害吃的才算），
//! 卢瑟特的辉石杖 +10、智力 80 算出来 414，和原版一致。法杖按魔力伤害的那组，圣印记按圣属性（dark）的那组，都能用的取高的。
//! 生成法器的稀有度倍率已经乘在补正值里（gear.rs build_row），面板自然带上。属性用 effective_*：算上护符、词条加的，和游戏面板一样。
//! 每 6 帧看一次拿着什么、属性多少，变了才重算。

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Mutex;

use eldenring::cs::{AttackElementCorrectParam, CalcCorrectGraph, EquipParamWeapon, GameDataMan, ReinforceParamWeapon, SoloParamRepository};
use fromsoftware_shared::FromStatic;

use crate::log;

const EVERY: u32 = 6;
/// 面板除以多少（用户 2026-11-06）
const PANEL_DIV: f32 = 200.0;

/// 左手、右手的武器编号和五项属性（力 灵 智 信 感）
type Key = (i32, i32, [u32; 5]);

struct St {
    frame: u32,
    /// 上次按什么算的
    key: Option<Key>,
    /// 上次写日志的面板（四舍五入）
    told: Option<i32>,
}

static ST: Mutex<St> = Mutex::new(St { frame: 0, key: None, told: None });
/// 法球的倍率（f32 的位）：拿着的法器里面板最高的 ÷ PANEL_DIV，没有法器按面板 100 算；tick 第一次算之前 = 1
static ORB: AtomicU32 = AtomicU32::new(0x3F80_0000);

pub fn describe() -> String {
    format!("法器面板：法球乘拿着的法器的法术补正 ÷ {PANEL_DIV}")
}

/// 法球伤害的倍率（rules.rs 每帧读）
pub fn orb_factor() -> f32 {
    f32::from_bits(ORB.load(Ordering::Relaxed))
}

/// 法术补正面板：100 + Σ 补正值 × 强化系数 × 曲线% ÷ 100；by = 这种伤害吃不吃这项属性；curve = 属性 → %
fn panel(corr: [f32; 5], rate: [f32; 5], by: [bool; 5], stats: [u32; 5], curve: impl Fn(f32) -> f32) -> f32 {
    100.0 + (0..5).filter(|&k| by[k]).map(|k| corr[k] * rate[k] * curve(stats[k] as f32) / 100.0).sum::<f32>()
}

/// 两只手的面板（不是法器 = None）→ 法球倍率：最高的 ÷ PANEL_DIV，没拿法器按面板的基数 100 算
fn orb_of(held: [Option<f32>; 2]) -> f32 {
    held.into_iter().flatten().reduce(f32::max).unwrap_or(100.0) / PANEL_DIV
}

/// 这把武器（带强化等级的编号）的法术补正面板；不是法器 = None
fn catalyst_panel(repo: &SoloParamRepository, pid: i32, stats: [u32; 5]) -> Option<f32> {
    if pid <= 0 {
        return None;
    }
    let level = (pid % 100) as u32;
    let w = repo.get::<EquipParamWeapon>(pid as u32 - level)?;
    let (sorc, inc) = (w.enable_magic(), w.enable_miracle());
    if !sorc && !inc {
        return None;
    }
    let corr = [w.correct_strength(), w.correct_agility(), w.correct_magic(), w.correct_faith(), w.correct_luck()];
    let rate = repo.get::<ReinforceParamWeapon>((w.reinforce_type_id() as i32 + level as i32) as u32).map_or([1.0; 5], |r| {
        [r.correct_strength_rate(), r.correct_agility_rate(), r.correct_magic_rate(), r.correct_faith_rate(), r.correct_luck_rate()]
    });
    let ae = repo.get::<AttackElementCorrectParam>(w.attack_element_correct_id() as u32);
    let of = |gid: u8, by: [bool; 5]| -> Option<f32> {
        let g = repo.get::<CalcCorrectGraph>(gid as u32)?;
        Some(panel(corr, rate, by, stats, |x| crate::gear::graph(g, x)))
    };
    let magic = ae.map_or([false; 5], |a| {
        [a.is_strength_correct_by_magic(), a.is_dexterity_correct_by_magic(), a.is_magic_correct_by_magic(), a.is_faith_correct_by_magic(), a.is_luck_correct_by_magic()]
    });
    let dark = ae.map_or([false; 5], |a| {
        [a.is_strength_correct_by_dark(), a.is_dexterity_correct_by_dark(), a.is_magic_correct_by_dark(), a.is_faith_correct_by_dark(), a.is_luck_correct_by_dark()]
    });
    let a = if sorc { of(w.correct_type_magic(), magic) } else { None };
    let b = if inc { of(w.correct_type_dark(), dark) } else { None };
    a.into_iter().chain(b).reduce(f32::max)
}

pub fn tick() {
    let mut st = ST.lock().unwrap_or_else(|e| e.into_inner());
    st.frame = st.frame.wrapping_add(1);
    if st.frame % EVERY != 0 {
        return;
    }
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return };
    let pgd = &gdm.main_player_game_data;
    let asm = &pgd.equipment.chr_asm;
    let slot_id = |slot: usize| asm.equipment_param_ids.get(slot).copied().unwrap_or(-1);
    let (lid, rid) = (slot_id(asm.equipment.active_left_weapon_slot() as usize), slot_id(asm.equipment.active_right_weapon_slot() as usize));
    let stats = [pgd.effective_strength, pgd.effective_dexterity, pgd.effective_intelligence, pgd.effective_faith, pgd.effective_arcane];
    let key = (lid, rid, stats);
    if st.key == Some(key) {
        return;
    }
    let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return };
    st.key = Some(key);
    let m = orb_of([catalyst_panel(repo, lid, stats), catalyst_panel(repo, rid, stats)]);
    ORB.store(m.to_bits(), Ordering::Relaxed);
    let now = (m * 100.0).round() as i32;
    if st.told != Some(now) {
        log(&format!("法器面板：左手 {lid}、右手 {rid}，属性 {stats:?}，法球 ×{m:.2}"));
        st.told = Some(now);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 只算这种伤害吃的属性；曲线按属性查；没有补正值的不加
    #[test]
    fn panel_formula() {
        // 卢瑟特的辉石杖 +10 类似的数：智力补正 150、强化 ×2，曲线 80 点 = 90％ → 100 + 150 × 2 × 90 ÷ 100 = 370
        let curve = |x: f32| if x >= 80.0 { 90.0 } else { 30.0 };
        let (corr, rate) = ([0.0, 0.0, 150.0, 40.0, 0.0], [2.0; 5]);
        assert_eq!(panel(corr, rate, [false, false, true, false, false], [10, 10, 80, 10, 10], curve), 370.0);
        // 信仰也吃：再加 40 × 2 × 30 ÷ 100 = 24
        assert_eq!(panel(corr, rate, [false, false, true, true, false], [10, 10, 80, 10, 10], curve), 394.0);
        assert_eq!(panel(corr, rate, [false; 5], [10, 10, 80, 10, 10], curve), 100.0, "元素表说都不吃：基数 100");
    }

    #[test]
    fn orb_from_held() {
        assert_eq!(orb_of([Some(121.0), Some(414.0)]), 2.07, "两只手都是法器：取高的，÷ 200");
        assert_eq!(orb_of([None, Some(250.0)]), 1.25);
        assert_eq!(orb_of([None, None]), 0.5, "没拿法器：按面板 100 算");
    }
}
