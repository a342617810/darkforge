//! 第五护符槽诊断（用户 2026-11-13「第五护符槽位装备加属性的护符是会出现计算两次的情况」）：第五格（原版的盟约槽，dll\dark_slot 打开）
//! 放着护符时，每 15 帧看一次：五个护符格各放的什么、每件护符的效果在人物身上挂了几份（正常 1 份；2 份 = 游戏挂了两次），
//! 身上所有效果加的能力值合计、人物原始能力值和血量上限；有变化才记一行（每次进游戏最多 MAX_LINES 行）。
//! 第五格是空的就什么都不做（空了以后记一次）

use std::collections::HashMap;
use std::sync::Mutex;

use eldenring::cs::{EquipParamAccessory, GameDataMan, ItemCategory, SoloParamRepository, SpEffectParam, WorldChrMan};
use eldenring::param::SP_EFFECT_PARAM_ST;
use fromsoftware_shared::FromStatic;

use crate::log;

const EVERY: u32 = 15;
const MAX_LINES: u32 = 200;
const ATTR: [&str; 8] = ["生命力", "集中力", "耐力", "力气", "灵巧", "智力", "信仰", "感应"];

/// 帧计数、上次记的内容、这次进游戏记了几行
static ST: Mutex<(u32, Option<String>, u32)> = Mutex::new((0, None, 0));

fn adds(r: &SP_EFFECT_PARAM_ST) -> [i32; 8] {
    [
        r.add_life_force_status() as i32,
        r.add_willpower_status() as i32,
        r.add_endure_status() as i32,
        r.add_strength_status() as i32,
        r.add_dexterity_status() as i32,
        r.add_magic_status() as i32,
        r.add_faith_status() as i32,
        r.add_luck_status() as i32,
    ]
}

/// 能力值加成写成「力气+5 灵巧+3」，全是 0 写 empty
fn fmt_attr(a: &[i32; 8], empty: &str) -> String {
    let v: Vec<String> = ATTR.iter().zip(a).filter(|(_, x)| **x != 0).map(|(n, x)| format!("{n}{x:+}")).collect();
    if v.is_empty() { empty.to_string() } else { v.join(" ") }
}

fn slot_name(k: usize) -> String {
    if k == 4 { "第五格".into() } else { format!("第{}格", k + 1) }
}

pub fn tick() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    g.0 = g.0.wrapping_add(1);
    if g.0 % EVERY != 0 {
        return;
    }
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return };
    let pd = &gdm.main_player_game_data;
    let e = &pd.equipment.equipment_entries;
    let fifth = e.covenant.as_valid().is_some_and(|id| matches!(id.category(), ItemCategory::Accessory));
    if !fifth {
        if g.1.take().is_some() {
            log("第五护符槽诊断：第五格空了，不再看");
        }
        return;
    }
    if g.2 >= MAX_LINES {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else { return };
    let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return };
    // 人物身上的效果：编号 → 份数；能力值加成合计（每一份都算）
    let mut count: HashMap<i32, usize> = HashMap::new();
    let mut sum = [0i32; 8];
    for x in p.chr_ins.special_effect.entries() {
        *count.entry(x.param_id).or_default() += 1;
        if let Some(r) = repo.get::<SpEffectParam>(x.param_id as u32) {
            for (s, a) in sum.iter_mut().zip(adds(r)) {
                *s += a;
            }
        }
    }
    let mut parts = Vec::new();
    for (k, id) in e.accessories.iter().chain(std::iter::once(&e.covenant)).enumerate() {
        let Some(id) = id.as_valid() else { continue };
        if !matches!(id.category(), ItemCategory::Accessory) {
            continue;
        }
        let Some(r) = repo.get::<EquipParamAccessory>(id.param_id()) else { continue };
        let effs: Vec<String> = [r.ref_id(), r.resident_sp_effect_id1(), r.resident_sp_effect_id2(), r.resident_sp_effect_id3(), r.resident_sp_effect_id4()]
            .into_iter()
            .filter(|&s| s > 0)
            .map(|s| {
                let attr = repo.get::<SpEffectParam>(s as u32).map(|x| fmt_attr(&adds(x), "")).unwrap_or_default();
                format!("效果 {s} 挂了 {} 份{}", count.get(&s).copied().unwrap_or(0), if attr.is_empty() { String::new() } else { format!("（{attr}）") })
            })
            .collect();
        parts.push(format!("{} 护符 {}：{}", slot_name(k), id.param_id(), if effs.is_empty() { "没有效果".to_string() } else { effs.join("、") }));
    }
    let base = [pd.vigor, pd.mind, pd.endurance, pd.strength, pd.dexterity, pd.intelligence, pd.faith, pd.arcane];
    let base: Vec<String> = ATTR.iter().zip(base).map(|(n, v)| format!("{n}{v}")).collect();
    let line = format!(
        "{}；身上所有效果的能力值加成合计：{}；人物原始能力值 {}；血量上限 {}（不算加成 {}）",
        parts.join("；"),
        fmt_attr(&sum, "无"),
        base.join(" "),
        pd.current_max_hp,
        pd.base_max_hp
    );
    if g.1.as_deref() != Some(line.as_str()) {
        g.2 += 1;
        log(&format!("第五护符槽诊断：{line}{}", if g.2 == MAX_LINES { "（这次进游戏记满了，不再记）" } else { "" }));
        g.1 = Some(line);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn attr_text() {
        assert_eq!(fmt_attr(&[0, 0, 0, 5, 3, 0, 0, 0], "无"), "力气+5 灵巧+3");
        assert_eq!(fmt_attr(&[0; 8], "无"), "无");
        assert_eq!(fmt_attr(&[-2, 0, 0, 0, 0, 0, 0, 1], ""), "生命力-2 感应+1");
        assert_eq!(slot_name(4), "第五格");
        assert_eq!(slot_name(0), "第1格");
    }
}
