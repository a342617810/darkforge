//! 战技伤害按稀有度（用户 2026-11-02：「普通满强战技倍率为原版 0.5 稀有 0.7 史诗 1.0 传说 1.2」，整个战技伤害都算）：
//! 重随照「亚历山大的碎片」建了各稀有度的效果（五种攻击力倍率，只管战技的攻击，rr/affixes.py skill_mults），这里看放战技的是哪把武器，
//! 是生成武器就挂它稀有度的那个效果、别的摘掉；原版武器（编号 1 亿以下）不挂。
//! 放战技的武器：双手持握时是握着的那把；单手时左手是盾（小盾 / 中盾 / 大盾 / 突刺盾）就是盾（游戏用盾的战技），否则是右手。
//! 定义：runtime.txt 的 skillmult 行「skillmult<TAB>稀有度 0~3<TAB>效果编号<TAB>倍率」（倍率是 1 的稀有度没有行）。
//! 每 6 帧看一次；没有定义时什么都不做

use std::collections::HashMap;
use std::fs;
use std::sync::{Mutex, OnceLock};

use eldenring::cs::{ChrAsmArmStyle, ChrInsExt, EquipParamWeapon, GameDataMan, SoloParamRepository, SpEffectParam, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

#[derive(Debug, Default, PartialEq)]
struct Def {
    /// 稀有度 → (效果编号, 倍率)
    by_rar: HashMap<usize, (i32, f32)>,
}

const RAR_ZH: [&str; 4] = ["普通", "稀有", "史诗", "传说"];
const EVERY: u32 = 6;
/// 盾牌的武器类型（wepType）：小盾、中盾、大盾、突刺盾
const SHIELDS: [u16; 4] = [65, 67, 69, 90];
/// 生成武器的编号从这里起（容器、开局装备、追忆 / 商人的成品传说……），以下是原版
const OWN_WEAPON: i32 = 100_000_000;

static DEF: OnceLock<Def> = OnceLock::new();
/// 帧计数；效果行在不在游戏参数里（不在 = 这次不是用重随的参数启动，什么都不做）；上次挂的（武器编号, 效果）（变了才记日志）
static ST: Mutex<(u32, Option<bool>, Option<(i32, Option<i32>)>)> = Mutex::new((0, None, None));

fn parse(text: &str) -> Def {
    let mut d = Def::default();
    for line in text.lines().map(|l| l.trim_end()) {
        let f: Vec<&str> = line.split('\t').collect();
        if f.len() < 4 || f[0] != "skillmult" {
            continue;
        }
        let (Ok(r), Ok(sp), Ok(m)) = (f[1].parse::<usize>(), f[2].parse::<i32>(), f[3].parse::<f32>()) else { continue };
        if r < 4 && sp > 0 {
            d.by_rar.insert(r, (sp, m));
        }
    }
    d
}

fn def() -> &'static Def {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("runtime.txt")).unwrap_or_default()))
}

pub fn describe() -> String {
    let d = def();
    if d.by_rar.is_empty() {
        return "战技伤害按稀有度：没有定义".into();
    }
    let mut v: Vec<_> = d.by_rar.iter().collect();
    v.sort_by_key(|x| *x.0);
    format!("战技伤害按稀有度：{}", v.iter().map(|(r, (_, m))| format!("{} ×{m}", RAR_ZH[**r])).collect::<Vec<_>>().join("、"))
}

/// 放战技的是不是左手：双手持握看握的哪只手；单手时左手是盾就是左手
fn skill_left(style: ChrAsmArmStyle, left_type: Option<u16>) -> bool {
    match style {
        ChrAsmArmStyle::LeftBothHands => true,
        ChrAsmArmStyle::RightBothHands => false,
        _ => left_type.is_some_and(|t| SHIELDS.contains(&t)),
    }
}

/// 武器编号（带强化等级）→ 要挂的效果：生成武器按参数行的稀有度（3 以上算传说），原版、空手、这个稀有度倍率是 1 的不挂
fn wanted(d: &Def, id: i32, rarity: Option<u8>) -> Option<i32> {
    if id < OWN_WEAPON {
        return None;
    }
    d.by_rar.get(&(rarity? as usize).min(3)).map(|x| x.0)
}

pub fn tick() {
    let d = def();
    if d.by_rar.is_empty() {
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
    let asm = &gdm.main_player_game_data.equipment.chr_asm;
    let slot_id = |slot: usize| asm.equipment_param_ids.get(slot).copied().unwrap_or(-1);
    let row = |id: i32| if id > 0 { repo.get::<EquipParamWeapon>((id / 100 * 100) as u32) } else { None };
    let (lid, rid) = (slot_id(asm.equipment.active_left_weapon_slot() as usize), slot_id(asm.equipment.active_right_weapon_slot() as usize));
    let id = if skill_left(asm.equipment.arm_style, row(lid).map(|w| w.wep_type())) { lid } else { rid };
    let want = wanted(d, id, row(id).map(|w| w.rarity()));
    if want.is_some() && g.1.is_none() {
        let ok = d.by_rar.values().all(|&(sp, _)| repo.get::<SpEffectParam>(sp as u32).is_some());
        if !ok {
            log("战技伤害按稀有度：效果不在游戏参数里（这次不是用重随的参数启动？），不挂");
        }
        g.1 = Some(ok);
    }
    if g.1 == Some(false) {
        return;
    }
    for &(sp, _) in d.by_rar.values() {
        let has = p.chr_ins.special_effect.entries().any(|e| e.param_id == sp);
        if Some(sp) == want && !has {
            p.apply_speffect(sp, false);
        } else if Some(sp) != want && has {
            p.remove_speffect(sp);
        }
    }
    if g.2 != Some((id, want)) {
        let what = match d.by_rar.iter().find(|(_, x)| Some(x.0) == want) {
            Some((r, (_, m))) => format!("{}，战技伤害 ×{m}", RAR_ZH[*r]),
            None if id >= OWN_WEAPON => "这个稀有度不改".into(),
            None => "原版武器 / 空手，不改".into(),
        };
        log(&format!("战技伤害按稀有度：放战技的武器 {id}（{what}）"));
        g.2 = Some((id, want));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_skill_and_want() {
        let d = parse("# x\nskillmult\t0\t7296900\t0.5\nskillmult\t1\t7296901\t0.7\nskillmult\t3\t7296903\t1.2\nattrdup\tstr\t3\t1\t2\nskillmult\t9\t1\t2\n");
        assert_eq!(d.by_rar.len(), 3, "坏的行（稀有度 9）不要");
        assert_eq!(wanted(&d, 230000005, Some(0)), Some(7296900));
        assert_eq!(wanted(&d, 230000005, Some(2)), None, "史诗 1.0 没有行，不挂");
        assert_eq!(wanted(&d, 230000005, Some(4)), Some(7296903), "幽影之地的传说按传说");
        assert_eq!(wanted(&d, 2000000, Some(3)), None, "原版武器不挂");
        assert_eq!(wanted(&d, 230000000, None), None, "参数行找不到不挂");
    }

    #[test]
    fn skill_hand() {
        assert!(skill_left(ChrAsmArmStyle::LeftBothHands, None));
        assert!(!skill_left(ChrAsmArmStyle::RightBothHands, Some(67)), "双手持右手武器：用右手的，左手盾不管");
        assert!(skill_left(ChrAsmArmStyle::OneHanded, Some(67)), "单手、左手中盾：盾的战技");
        assert!(!skill_left(ChrAsmArmStyle::OneHanded, Some(57)), "单手、左手法杖：右手的战技");
        assert!(!skill_left(ChrAsmArmStyle::OneHanded, None));
    }
}
