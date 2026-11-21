//! 第五护符槽的效果补挂（用户 2026-11-21「修一下无尽箭袋装在第五格护符槽不生效的问题」，玩家反馈，细节不清楚）。
//! 第五格是 dll\dark_slot 打开的盟约槽：单机时游戏照常挂第五格护符的 refId / 常驻效果（日志里影步装第五格挂上了、也触发了），
//! 但有的情况游戏不挂，积木词条（无尽箭袋这类只认身上标记的）就当没戴。已知的可能：Seamless Co-op 改了「槽位可用」那个函数
//! （dark_slot 在联机时找不到它的特征码），装得进去、游戏却不认这一格；别的原因没复现。
//! 这里每 EVERY 帧看一次（只在第五格装着护符、或者我们补挂的还没摘时）：第五格护符参数行现在的效果，人物身上一份都没有就补挂一份，
//! 记成我们挂的；第五格换了 / 空了，补挂的那份摘掉（别的装备也提供、身上只剩一份的留着——那份是游戏自己挂的）；
//! 游戏后来自己也挂上了（身上两份、别的装备不提供）就摘掉一份。读图 / 读档时效果会重建，记的清掉，之后按身上的重新判断。
//! 补挂、摘掉都写日志（带第五格护符的组、前四格同组的护符、Seamless 有没有加载，方便看是哪种原因），一次进游戏最多 MAX_LINES 行。

use std::collections::{HashMap, HashSet};
use std::sync::Mutex;

use eldenring::cs::{
    ChrInsExt, EquipParamAccessory, EquipParamProtector, EquipParamWeapon, GameDataMan, ItemCategory, SoloParamRepository, SpEffectParam,
    WorldChrMan,
};
use fromsoftware_shared::FromStatic;

use crate::log;

const EVERY: u32 = 15;
const MAX_LINES: u32 = 60;

#[derive(Default)]
struct St {
    frames: u32,
    /// 我们补挂在身上的效果
    ours: HashSet<i32>,
    lines: u32,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 这一轮要挂 / 摘的效果，顺便更新 ours。expected = 第五格护符现在提供的效果；others = 别的装备（前四格护符、防具、武器）提供的；
/// have = 人物身上每个效果几份
fn plan(expected: &[i32], others: &HashSet<i32>, have: &HashMap<i32, usize>, ours: &mut HashSet<i32>) -> (Vec<i32>, Vec<i32>) {
    let n = |s: i32| have.get(&s).copied().unwrap_or(0);
    let mut put = Vec::new();
    let mut take = Vec::new();
    let mut mine: Vec<i32> = ours.iter().copied().collect();
    mine.sort_unstable();
    for s in mine {
        if !expected.contains(&s) {
            // 第五格不再提供：身上有就摘我们那份；别的装备也提供、只剩一份的是游戏自己挂的，留着
            ours.remove(&s);
            if n(s) >= 2 || (n(s) == 1 && !others.contains(&s)) {
                take.push(s);
            }
        } else if n(s) >= 2 && !others.contains(&s) {
            // 游戏自己也挂上了：摘掉多的一份
            ours.remove(&s);
            take.push(s);
        } else if n(s) == 0 {
            // 死了 / 别的模块摘掉了：下面当成没挂重新补
            ours.remove(&s);
        }
    }
    let mut seen = HashSet::new();
    for &s in expected {
        if s > 0 && seen.insert(s) && n(s) == 0 && !ours.contains(&s) {
            ours.insert(s);
            put.push(s);
        }
    }
    (put, take)
}

fn acc_effects(r: &eldenring::param::EQUIP_PARAM_ACCESSORY_ST) -> [i32; 5] {
    [r.ref_id(), r.resident_sp_effect_id1(), r.resident_sp_effect_id2(), r.resident_sp_effect_id3(), r.resident_sp_effect_id4()]
}

pub fn tick() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    st.frames = st.frames.wrapping_add(1);
    if st.frames % EVERY != 3 {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        st.ours.clear(); // 读图 / 读档：身上的效果会重建
        return;
    };
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return };
    let e = &gdm.main_player_game_data.equipment.equipment_entries;
    let cov = e.covenant.as_valid().filter(|id| matches!(id.category(), ItemCategory::Accessory));
    if cov.is_none() && st.ours.is_empty() {
        return;
    }
    let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return };
    let cov_row = cov.and_then(|id| repo.get::<EquipParamAccessory>(id.param_id()));
    let expected: Vec<i32> = cov_row
        .map(|r| acc_effects(r).into_iter().filter(|&s| s > 0 && repo.get::<SpEffectParam>(s as u32).is_some()).collect())
        .unwrap_or_default();
    if expected.is_empty() && st.ours.is_empty() {
        return;
    }
    let mut others: HashSet<i32> = HashSet::new();
    let mut same_group: Vec<u32> = Vec::new();
    let group = cov_row.map(|r| r.accessory_group());
    for id in e.accessories.iter().filter_map(|x| x.as_valid()).filter(|id| matches!(id.category(), ItemCategory::Accessory)) {
        if let Some(r) = repo.get::<EquipParamAccessory>(id.param_id()) {
            others.extend(acc_effects(r));
            if group.is_some_and(|gr| gr > 0 && gr == r.accessory_group()) {
                same_group.push(id.param_id());
            }
        }
    }
    for id in [e.protector_head, e.protector_chest, e.protector_hands, e.protector_legs] {
        if let Some(r) = repo.get::<EquipParamProtector>(id.param_id()) {
            others.extend([r.resident_sp_effect_id(), r.resident_sp_effect_id2(), r.resident_sp_effect_id3()]);
        }
    }
    for id in [e.weapon_primary_left, e.weapon_primary_right, e.weapon_secondary_left, e.weapon_secondary_right, e.weapon_tertiary_left, e.weapon_tertiary_right] {
        let pid = id.param_id();
        if let Some(r) = repo.get::<EquipParamWeapon>(pid - pid % 100) {
            others.extend([r.resident_sp_effect_id(), r.resident_sp_effect_id1(), r.resident_sp_effect_id2()]);
        }
    }
    others.retain(|&s| s > 0);
    let mut have: HashMap<i32, usize> = HashMap::new();
    for x in p.chr_ins.special_effect.entries() {
        *have.entry(x.param_id).or_default() += 1;
    }
    let (put, take) = plan(&expected, &others, &have, &mut st.ours);
    for &s in &take {
        p.remove_speffect(s);
    }
    for &s in &put {
        p.apply_speffect(s, false);
    }
    if (put.is_empty() && take.is_empty()) || st.lines >= MAX_LINES {
        return;
    }
    st.lines += 1;
    let last = if st.lines == MAX_LINES { "（这次进游戏记满了，不再记）" } else { "" };
    if !put.is_empty() {
        log(&format!(
            "第五护符槽：护符 {} 的效果 {put:?} 游戏没挂上，补挂一份（护符组 {}；前四格同组的护符 {}；Seamless Co-op {}）{last}",
            cov.map_or(0, |id| id.param_id()),
            group.unwrap_or(-1),
            if same_group.is_empty() { "没有".to_string() } else { format!("{same_group:?}") },
            if crate::coop::ersc_loaded() { "已加载" } else { "没有加载" },
        ));
    }
    if !take.is_empty() {
        log(&format!("第五护符槽：补挂的效果 {take:?} 摘掉（第五格换了 / 空了，或者游戏自己挂上了）{last}"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn have(xs: &[(i32, usize)]) -> HashMap<i32, usize> {
        xs.iter().copied().collect()
    }

    /// 游戏挂了第五格的：什么都不做；没挂：补一份，记成我们的
    #[test]
    fn put_only_when_missing() {
        let mut ours = HashSet::new();
        assert_eq!(plan(&[7210748], &HashSet::new(), &have(&[(7210748, 1)]), &mut ours), (vec![], vec![]));
        assert!(ours.is_empty());
        assert_eq!(plan(&[7210748, -1, 0, 7210748], &HashSet::new(), &have(&[]), &mut ours), (vec![7210748], vec![]));
        assert_eq!(ours, HashSet::from([7210748]));
        // 补上之后：身上一份，不动
        assert_eq!(plan(&[7210748], &HashSet::new(), &have(&[(7210748, 1)]), &mut ours), (vec![], vec![]));
        assert_eq!(ours, HashSet::from([7210748]));
    }

    /// 游戏后来自己也挂了（两份、别的装备不提供）：摘一份，不再算我们的；别的装备也提供的两份留着
    #[test]
    fn drop_extra_when_game_catches_up() {
        let mut ours = HashSet::from([5]);
        assert_eq!(plan(&[5], &HashSet::new(), &have(&[(5, 2)]), &mut ours), (vec![], vec![5]));
        assert!(ours.is_empty());
        let mut ours = HashSet::from([5]);
        assert_eq!(plan(&[5], &HashSet::from([5]), &have(&[(5, 2)]), &mut ours), (vec![], vec![]));
        assert_eq!(ours, HashSet::from([5]));
    }

    /// 第五格换了 / 空了：我们挂的摘掉；别的装备也提供、只剩一份的（游戏的）留着；身上已经没了的只忘掉
    #[test]
    fn take_ours_when_slot_changes() {
        let mut ours = HashSet::from([5, 6, 7]);
        let (put, take) = plan(&[9], &HashSet::from([6]), &have(&[(5, 1), (6, 1)]), &mut ours);
        assert_eq!(take, vec![5]);
        assert_eq!(put, vec![9]);
        assert_eq!(ours, HashSet::from([9]));
        let mut ours = HashSet::from([6]);
        assert_eq!(plan(&[], &HashSet::from([6]), &have(&[(6, 2)]), &mut ours), (vec![], vec![6]));
        assert!(ours.is_empty());
    }

    /// 补挂的被清掉了（死了、读图）：重新补
    #[test]
    fn reapply_after_cleared() {
        let mut ours = HashSet::from([5]);
        assert_eq!(plan(&[5], &HashSet::new(), &have(&[]), &mut ours), (vec![5], vec![]));
        assert_eq!(ours, HashSet::from([5]));
    }
}
