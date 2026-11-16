//! 数值词条同稀有度叠加（用户 2026-11-01 属性加点；2026-11-03 扩到原版类型的数值词条，触发型除外）：每条词条每个稀有度只有一个效果编号，两件同稀有度的装备挂的是
//! 同一个效果，游戏里同一个效果挂两次只算一次。重随给每个这样的效果建了几份数值一样、编号不同的副本（rr/affixes.py attr_copies），
//! 这里数身上的防具（4 件）和护符（4 格 + 盟约槽）里每个效果出现几次：第一件由装备自己给，第 2 件起挂副本；不需要了就摘掉。
//! 游戏自己挂了几份也要数：普通护符格和第五护符槽（盟约槽，dll\dark_slot）各挂一份同一个效果，不会合成一份（用户 2026-11-13
//! 「普通护符栏位和第五护符槽同时装备同一种属性加成护符会生效3次而不是两次」），所以只补「件数 − 游戏已经挂的份数」。
//! 定义：runtime.txt 的 attrdup 行「attrdup<TAB>词条键<TAB>稀有度 0~3<TAB>效果编号<TAB>副本编号（逗号分隔）」。
//! 每 15 帧数一次；身上没有这类词条、也没挂着副本时什么都不做

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};

use eldenring::cs::{
    ChrInsExt, EquipParamAccessory, EquipParamProtector, GameDataMan, ItemCategory, SoloParamRepository, SpEffectParam, WorldChrMan,
};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

#[derive(Debug, Default, PartialEq)]
struct Def {
    /// 效果编号 → (词条键, 稀有度, 副本编号)
    dup: HashMap<i32, (String, usize, Vec<i32>)>,
    /// 所有副本编号（不想要了就摘）
    all: HashSet<i32>,
}

const RAR_ZH: [&str; 4] = ["普通", "稀有", "史诗", "传说"];
const EVERY: u32 = 15;

static DEF: OnceLock<Def> = OnceLock::new();
/// 帧计数；副本效果行在不在游戏参数里（不在 = 这次不是用重随的参数启动，什么都不做；第一次要用时查）；
/// 上次每个效果数到几件、游戏自己挂了几份（变了才记日志）
static ST: Mutex<(u32, Option<bool>, Option<HashMap<i32, (usize, usize)>>)> = Mutex::new((0, None, None));

fn parse(text: &str) -> Def {
    let mut d = Def::default();
    for line in text.lines().map(|l| l.trim_end()) {
        let f: Vec<&str> = line.split('\t').collect();
        if f.len() < 5 || f[0] != "attrdup" {
            continue;
        }
        let (Ok(r), Ok(sp)) = (f[2].parse::<usize>(), f[3].parse::<i32>()) else { continue };
        let copies: Vec<i32> = f[4].split(',').filter_map(|x| x.trim().parse().ok()).filter(|&x| x > 0).collect();
        if r < 4 && sp > 0 && !copies.is_empty() {
            d.all.extend(&copies);
            d.dup.insert(sp, (f[1].to_string(), r, copies));
        }
    }
    d
}

fn def() -> &'static Def {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("runtime.txt")).unwrap_or_default()))
}

pub fn describe() -> String {
    let d = def();
    if d.dup.is_empty() { "数值词条叠加：没有定义".into() } else { format!("数值词条叠加：{} 个效果、各 {} 份副本", d.dup.len(), d.dup.values().map(|v| v.2.len()).max().unwrap_or(0)) }
}

/// 游戏自己挂了几份（至少按 1 份算：刚换装备、游戏还没挂上时照以前的算法）
fn game_has(applied: &HashMap<i32, usize>, sp: i32) -> usize {
    applied.get(&sp).copied().unwrap_or(0).max(1)
}

/// 装备上的效果出现次数 → 该挂的副本：效果出现 n 次、游戏自己挂了 g 份，就挂前 n − g 份（最多到副本份数）
fn wanted(d: &Def, counts: &HashMap<i32, usize>, applied: &HashMap<i32, usize>) -> HashSet<i32> {
    let mut out = HashSet::new();
    for (sp, &n) in counts {
        if let Some((_, _, copies)) = d.dup.get(sp) {
            out.extend(copies.iter().take(n.saturating_sub(game_has(applied, *sp))));
        }
    }
    out
}

pub fn tick() {
    let d = def();
    if d.dup.is_empty() {
        return;
    }
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    g.0 = g.0.wrapping_add(1);
    if g.0 % EVERY != 0 {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        g.2 = None;
        return;
    };
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return };
    let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return };
    let e = &gdm.main_player_game_data.equipment.equipment_entries;
    let mut effects: Vec<i32> = Vec::new();
    for id in [e.protector_head, e.protector_chest, e.protector_hands, e.protector_legs] {
        if matches!(id.category(), ItemCategory::Protector) {
            if let Some(r) = repo.get::<EquipParamProtector>(id.param_id()) {
                effects.extend([r.resident_sp_effect_id(), r.resident_sp_effect_id2(), r.resident_sp_effect_id3()]);
            }
        }
    }
    for id in e.accessories.iter().chain(std::iter::once(&e.covenant)).filter_map(|x| x.as_valid()) {
        if matches!(id.category(), ItemCategory::Accessory) {
            if let Some(r) = repo.get::<EquipParamAccessory>(id.param_id()) {
                effects.extend([r.ref_id(), r.resident_sp_effect_id1(), r.resident_sp_effect_id2(), r.resident_sp_effect_id3(), r.resident_sp_effect_id4()]);
            }
        }
    }
    let mut counts: HashMap<i32, usize> = HashMap::new();
    for sp in effects.into_iter().filter(|sp| d.dup.contains_key(sp)) {
        *counts.entry(sp).or_default() += 1;
    }
    // 身上已经挂着的副本；游戏自己给装备上的效果挂了几份
    let mut have: HashSet<i32> = HashSet::new();
    let mut applied: HashMap<i32, usize> = HashMap::new();
    for x in p.chr_ins.special_effect.entries() {
        if d.all.contains(&x.param_id) {
            have.insert(x.param_id);
        } else if counts.contains_key(&x.param_id) {
            *applied.entry(x.param_id).or_default() += 1;
        }
    }
    if counts.is_empty() && have.is_empty() {
        g.2 = None;
        return;
    }
    let want = wanted(d, &counts, &applied);
    if !want.is_empty() && g.1.is_none() {
        let ok = want.iter().all(|&sp| repo.get::<SpEffectParam>(sp as u32).is_some());
        if !ok {
            log("数值词条叠加：副本效果不在游戏参数里（这次不是用重随的参数启动？），不叠加");
        }
        g.1 = Some(ok);
    }
    if g.1 == Some(false) {
        return;
    }
    for &sp in want.difference(&have) {
        p.apply_speffect(sp, false);
    }
    for &sp in have.difference(&want) {
        p.remove_speffect(sp);
    }
    // 件数变了记一行（每种效果出现 2 件以上的）
    let multi: HashMap<i32, (usize, usize)> =
        counts.iter().filter(|e| *e.1 >= 2).map(|(&k, &n)| (k, (n, applied.get(&k).copied().unwrap_or(0)))).collect();
    if g.2.as_ref().map_or(!multi.is_empty(), |m| *m != multi) {
        let mut parts: Vec<String> = multi
            .iter()
            .filter_map(|(sp, &(n, a))| {
                d.dup.get(sp).map(|(k, r, c)| {
                    let add = n.saturating_sub(a.max(1)).min(c.len());
                    format!("{k}（{}）{n} 件，游戏挂了 {a} 份 → 加挂 {add} 份", RAR_ZH[*r])
                })
            })
            .collect();
        parts.sort();
        log(&format!("数值词条叠加：{}", if parts.is_empty() { "没有重复的了，副本全摘掉".to_string() } else { parts.join("；") }));
        g.2 = Some(multi);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_and_want() {
        let d = parse("# x\nattrdup\tstr\t3\t7002030\t11,12,13\nattrdup\tdex\t0\t7002200\t21,22\nboss\t1\nattrdup\tbad\t9\t1\t2\n");
        assert_eq!(d.dup.len(), 2);
        assert_eq!(d.all, HashSet::from([11, 12, 13, 21, 22]));
        let none = HashMap::new();
        let c = HashMap::from([(7002030, 3), (7002200, 1), (5, 4)]);
        assert_eq!(wanted(&d, &c, &none), HashSet::from([11, 12]), "3 件挂 2 份；1 件不挂；不认识的不管");
        let c = HashMap::from([(7002030, 9)]);
        assert_eq!(wanted(&d, &c, &none), HashSet::from([11, 12, 13]), "超过副本份数就挂满");
        // 普通护符格 + 第五护符槽：游戏自己挂了两份，只补差的
        let c = HashMap::from([(7002030, 2)]);
        assert!(wanted(&d, &c, &HashMap::from([(7002030, 2)])).is_empty(), "2 件、游戏已经挂了 2 份：不补");
        assert_eq!(wanted(&d, &c, &HashMap::from([(7002030, 1)])), HashSet::from([11]), "2 件都在普通格：游戏只挂 1 份，补 1 份");
        let c = HashMap::from([(7002030, 3)]);
        assert_eq!(wanted(&d, &c, &HashMap::from([(7002030, 2)])), HashSet::from([11]), "3 件、游戏挂了 2 份：补 1 份");
        assert!(wanted(&d, &HashMap::from([(7002030, 1)]), &HashMap::from([(7002030, 2)])).is_empty(), "游戏挂得比件数还多：不补");
    }
}
