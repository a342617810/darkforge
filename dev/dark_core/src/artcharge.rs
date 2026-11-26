//! 艾珀莉亚漩涡（战技 5270，类型 328）在别的武器上充能（用户 2026-11-25 报告：战灰 29719 装到其他武器后无法自行充能）。
//! 原版：艾珀莉亚（武器 10500000）的常驻效果 19870 / 19871 是状态 506 的累积（上限 25 / 50 → 挂 19874 / 19875，30 秒）；
//! 累积是它自己的攻击行（行为变体 1010）命中时挂的 19893 / 19892（+8 / +6）加的；玩家脚本在战技类型 328、身上有 19875 / 19874 时
//! 放充能版（c0000.hks 的 SwordArtsOneShotCategory 12 / 11），不看是哪把武器。战灰只换战技，不带武器的常驻效果，别的武器的攻击行
//! 也不加累积；生成武器的常驻效果槽写的是词条 / 光效，生成的艾珀莉亚同样充不了。
//! 这里：左右手当前那把武器的战技是 5270（装的战灰，或者武器自带）、而且手上没有自带 19870 / 19871 的武器（原版艾珀莉亚，游戏自己算）时，
//! 自己记累积：每打中一下（连击值的 hit_self 脉冲，要挂着 hit_acc，掉了就补）加 19893 的累积值，每秒减 19870 的衰减（累积值 ÷ 间隔），
//! 封顶最高一档；够第一档挂 19874、够第二档挂 19875，打中时重挂（刷新 30 秒），身上已有高一档的不挂低一档；放这个战技
//! （动作段 600 + 类型）时清零（充能版的动作自己会把 19874 / 19875 顶掉）。离开手上时累积留着、照常衰减，读图 / 死亡清零。
//! 数值都从参数读，读不到（不是这一版的参数）就不做。每 CHECK 帧看一次手上的武器，有这个战技时每帧看命中

use std::fs;
use std::sync::Mutex;
use std::time::Instant;

use eldenring::cs::{
    CSGaitemImp, CSGaitemIns, CSWepGaitemIns, ChrInsExt, EquipParamGem, EquipParamWeapon, GaitemCategory, GaitemHandle, GameDataMan,
    SoloParamRepository, SpEffectParam, SwordArtsParam, WorldChrMan,
};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

/// 艾珀莉亚漩涡
const ARTS: i32 = 5270;
/// 原版艾珀莉亚的两个常驻累积（低档、高档）
const ACC: [i32; 2] = [19870, 19871];
/// 原版攻击行命中时加的累积（大部分攻击 +8）
const ADD_SP: i32 = 19893;
const CHECK: u32 = 10;
const MAX_LINES: u32 = 40;

#[derive(Debug, Clone, PartialEq)]
struct Def {
    /// 战技的动作段（600 + swordArtsTypeNew）
    section: i32,
    /// (累积上限, 到了挂的效果)，从低到高
    tiers: Vec<(f32, i32)>,
    add: f32,
    /// 每秒减多少
    decay: f32,
    hit_acc: i32,
    hit_self: i32,
}

#[derive(Default)]
struct St {
    frames: u32,
    /// None = 还没读参数；Some(None) = 读过了，做不了
    def: Option<Option<Def>>,
    /// 手上有这个战技（上一次看的结果）
    active: bool,
    val: f32,
    last: Option<Instant>,
    prev_hit: bool,
    /// 上一帧的档（-1 = 没到第一档），变了记日志
    tier: i32,
    /// 上一次记的手上武器（编号, 是不是战灰），变了记日志
    told: Option<(i32, bool)>,
    lines: u32,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

fn say(st: &mut St, msg: &str) {
    if st.lines < MAX_LINES {
        st.lines += 1;
        log(&format!("艾珀莉亚漩涡充能：{msg}{}", if st.lines == MAX_LINES { "（后面不再记）" } else { "" }));
    }
}

/// runtime.txt 的「mark<TAB>名字<TAB>效果」
fn marks(text: &str) -> (Option<i32>, Option<i32>) {
    let mut out = (None, None);
    for l in text.lines() {
        let f: Vec<&str> = l.trim_end().split('\t').collect();
        if f.len() >= 3 && f[0] == "mark" {
            let v = f[2].parse::<i32>().ok().filter(|&x| x > 0);
            match f[1] {
                "hit_acc" => out.0 = v,
                "hit_self" => out.1 = v,
                _ => {}
            }
        }
    }
    out
}

fn load(repo: &SoloParamRepository) -> Result<Def, String> {
    let arts = repo.get::<SwordArtsParam>(ARTS as u32).ok_or("战技 5270 不在参数里")?;
    let mut tiers = Vec::new();
    let mut decay: f32 = 0.0;
    for a in ACC {
        let r = repo.get::<SpEffectParam>(a as u32).ok_or(format!("累积效果 {a} 不在参数里"))?;
        let (over, fire) = (r.accumu_over_val(), r.accumu_over_fire_id());
        if over <= 0 || fire <= 0 || repo.get::<SpEffectParam>(fire as u32).is_none() {
            return Err(format!("累积效果 {a} 的上限 {over} / 效果 {fire} 不对"));
        }
        tiers.push((over as f32, fire));
        if r.accumu_val() < 0 && r.motion_interval() > 0.0 {
            decay = decay.max(-r.accumu_val() as f32 / r.motion_interval());
        }
    }
    tiers.sort_by(|a, b| a.0.total_cmp(&b.0));
    let add = repo.get::<SpEffectParam>(ADD_SP as u32).map(|r| r.accumu_val()).filter(|&v| v > 0).ok_or("命中累积 19893 不对")? as f32;
    let (hit_acc, hit_self) = marks(&fs::read_to_string(dir().join("runtime.txt")).unwrap_or_default());
    let (Some(hit_acc), Some(hit_self)) = (hit_acc, hit_self) else { return Err("runtime.txt 没有连击值的标记（hit_acc / hit_self），认不出命中".into()) };
    Ok(Def { section: 600 + arts.sword_arts_type_new() as i32, tiers, add, decay, hit_acc, hit_self })
}

/// 过了 dt 秒、这一帧打中了没有、在不在放这个战技 → 新的累积
fn step(d: &Def, val: f32, dt: f32, hit: bool, skill: bool) -> f32 {
    if skill {
        return 0.0;
    }
    let top = d.tiers.last().map_or(0.0, |x| x.0);
    let v = (val - d.decay * dt.max(0.0)).max(0.0);
    if hit { (v + d.add).min(top) } else { v }
}

/// 现在到了第几档（-1 = 没到）
fn tier_of(d: &Def, val: f32) -> i32 {
    d.tiers.iter().rposition(|x| val >= x.0).map_or(-1, |t| t as i32)
}

/// 这一帧要挂的效果：到了的那一档；打中时重挂刷新，没打中时身上没有才挂；身上有高一档的不挂
fn wanted(d: &Def, val: f32, hit: bool, has: impl Fn(i32) -> bool) -> Option<i32> {
    let t = d.tiers.iter().rposition(|x| val >= x.0)?;
    if d.tiers[t + 1..].iter().any(|x| has(x.1)) {
        return None;
    }
    let sp = d.tiers[t].1;
    (hit || !has(sp)).then_some(sp)
}

/// 手上那把武器的战技：装着战灰就是战灰的，否则武器自带的。wid = 装备里的武器编号（带强化等级）
fn arts_of(imp: &CSGaitemImp, repo: &SoloParamRepository, h: GaitemHandle, wid: i32, own: i32) -> (i32, bool) {
    let n = imp.gaitems.len();
    let ok = |h: &GaitemHandle, cat: GaitemCategory| h.is_indexed() && (h.index() as usize) < n && matches!(h.category(), Ok(c) if c == cat);
    if !ok(&h, GaitemCategory::Weapon) {
        return (own, false);
    }
    let Some(ins) = imp.gaitem_ins_by_handle(&h) else { return (own, false) };
    // 句柄对上的要是这把武器（强化等级不比）
    if ins.item_id.param_id().is_none_or(|x| x / 100 != wid as u32 / 100) {
        return (own, false);
    }
    // 武器类的句柄就是带战灰槽的武器实例
    let wep = unsafe { &*(ins as *const CSGaitemIns as *const CSWepGaitemIns) };
    let gh = wep.gem_slot_table.gem_slots[0].gaitem_handle;
    if !ok(&gh, GaitemCategory::Gem) {
        return (own, false);
    }
    let gem = imp.gaitem_ins_by_handle(&gh).and_then(|g| g.item_id.param_id()).and_then(|id| repo.get::<EquipParamGem>(id));
    match gem.map(|g| g.sword_arts_param_id()).filter(|&a| a > 0) {
        Some(a) => (a, true),
        None => (own, false),
    }
}

/// 左右手当前的武器里：战技是 5270 的那把（编号, 是不是战灰）；手上有自带累积的（原版艾珀莉亚）就交给游戏，返回 None
fn holder(repo: &SoloParamRepository) -> Option<(i32, bool)> {
    let gdm = unsafe { GameDataMan::instance() }.ok()?;
    let imp = unsafe { CSGaitemImp::instance() }.ok()?;
    let asm = &gdm.main_player_game_data.equipment.chr_asm;
    let mut found = None;
    for slot in [asm.equipment.active_right_weapon_slot() as usize, asm.equipment.active_left_weapon_slot() as usize] {
        let wid = asm.equipment_param_ids.get(slot).copied().unwrap_or(-1);
        let Some(w) = (wid > 0).then(|| repo.get::<EquipParamWeapon>((wid / 100 * 100) as u32)).flatten() else { continue };
        if [w.resident_sp_effect_id(), w.resident_sp_effect_id1(), w.resident_sp_effect_id2()].iter().any(|r| ACC.contains(r)) {
            return None;
        }
        let Some(&h) = asm.gaitem_handles.get(slot) else { continue };
        let (a, gem) = arts_of(imp, repo, h, wid, w.sword_arts_param_id());
        if a == ARTS && found.is_none() {
            found = Some((wid, gem));
        }
    }
    found
}

pub fn tick() {
    let mut guard = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = guard.get_or_insert_with(St::default);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        // 读图 / 死亡：清零（原版的常驻累积也是重新挂的）
        st.val = 0.0;
        st.last = None;
        st.prev_hit = false;
        st.tier = -1;
        st.active = false;
        return;
    };
    st.frames = st.frames.wrapping_add(1);
    if st.frames % CHECK == 0 {
        let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return };
        let who = holder(repo);
        if who.is_some() && st.def.is_none() {
            let r = load(repo);
            if let Err(e) = &r {
                say(st, &format!("{e}，不做"));
            }
            st.def = Some(r.ok());
        }
        if who != st.told {
            if let Some((wid, gem)) = who {
                say(st, &format!("手上的 {wid}（{}）是这个战技，打中自己记充能", if gem { "装的战灰" } else { "武器自带" }));
            } else if st.told.is_some() {
                say(st, "手上没有这个战技了，充能留着照常衰减");
            }
            st.told = who;
        }
        st.active = who.is_some();
    }
    if !st.active {
        return;
    }
    let Some(Some(d)) = st.def.clone() else { return };
    let now = Instant::now();
    let dt = st.last.map_or(0.0, |t| now.duration_since(t).as_secs_f32());
    st.last = Some(now);
    let mut have = Vec::new();
    for e in p.chr_ins.special_effect.entries() {
        if e.param_id == d.hit_acc || e.param_id == d.hit_self || d.tiers.iter().any(|x| x.1 == e.param_id) {
            have.push(e.param_id);
        }
    }
    if !have.contains(&d.hit_acc) {
        p.apply_speffect(d.hit_acc, false);
    }
    let self_hit = have.contains(&d.hit_self);
    let hit = self_hit && !st.prev_hit;
    st.prev_hit = self_hit;
    let ta = &p.chr_ins.modules.time_act;
    let anim = ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].anim_id;
    let skill = anim > 0 && anim / 1_000_000 == d.section;
    let before = st.val;
    st.val = step(&d, st.val, dt, hit && !skill, skill);
    let t = tier_of(&d, st.val);
    if let Some(sp) = wanted(&d, st.val, hit && !skill, |x| have.contains(&x)) {
        p.apply_speffect(sp, false);
    }
    if t != st.tier {
        if t > st.tier {
            say(st, &format!("充能到第 {} 档（累积 {:.0}，挂 {}）", t + 1, st.val, d.tiers[t as usize].1));
        } else if skill && before > 0.0 {
            say(st, &format!("放了战技，充能清零（之前 {before:.0}）"));
        }
        st.tier = t;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn def() -> Def {
        Def { section: 928, tiers: vec![(25.0, 19874), (50.0, 19875)], add: 8.0, decay: 1.0, hit_acc: 7210970, hit_self: 7210968 }
    }

    #[test]
    fn reads_marks() {
        let t = "mark\thit_acc\t7210970\nmark\tland\t7210966\nmark\thit_self\t7210968\naff\tx\t1\n";
        assert_eq!(marks(t), (Some(7210970), Some(7210968)));
        assert_eq!(marks("mark\thit_acc\t-1\n"), (None, None));
    }

    #[test]
    fn charge_and_decay() {
        let d = def();
        let mut v = 0.0;
        for _ in 0..3 {
            v = step(&d, v, 0.0, true, false);
        }
        assert_eq!(v, 24.0);
        assert_eq!(tier_of(&d, v), -1, "三下 24，还差一点");
        v = step(&d, v, 0.0, true, false);
        assert_eq!(tier_of(&d, v), 0, "第四下到第一档");
        for _ in 0..10 {
            v = step(&d, v, 0.0, true, false);
        }
        assert_eq!(v, 50.0, "封顶最高一档");
        assert_eq!(tier_of(&d, v), 1);
        v = step(&d, v, 2.5, false, false);
        assert_eq!(v, 47.5, "每秒减 1");
        assert_eq!(step(&d, v, 100.0, false, false), 0.0, "不会减成负的");
        assert_eq!(step(&d, v, 0.0, true, true), 0.0, "放战技清零，这一下不算");
    }

    #[test]
    fn which_effect() {
        let d = def();
        assert_eq!(wanted(&d, 10.0, true, |_| false), None, "没到第一档");
        assert_eq!(wanted(&d, 30.0, true, |_| false), Some(19874));
        assert_eq!(wanted(&d, 30.0, false, |x| x == 19874), None, "没打中、身上有：不重挂");
        assert_eq!(wanted(&d, 30.0, true, |x| x == 19874), Some(19874), "打中了重挂刷新");
        assert_eq!(wanted(&d, 30.0, false, |_| false), Some(19874), "掉了（30 秒到了）还够就补");
        assert_eq!(wanted(&d, 30.0, true, |x| x == 19875), None, "身上有第二档：不挂第一档");
        assert_eq!(wanted(&d, 50.0, true, |x| x == 19874), Some(19875), "到第二档");
    }
}
