//! 传说武器的属性光效（用户 2026-11-05「传说武器属性光效会在切换武器后挂在手上而不是武器上」）：光效是生成武器参数行的常驻效果
//! （residentSpEffectId2 = 7092000~7092050，gear 的 build_row 写），它的光效行是原版武器附魔那种（effectType 1 右手武器，
//! 附魔挂点 10300 / 11300…在武器模型上），效果挂上的那一下绑到武器模型的挂点。换武器时游戏马上按新装备挂常驻效果，
//! 新武器的模型却要到换武器动作中途才拿到手上，绑的时候找不到武器的挂点就落到了手上（按参数推断，没在游戏里验证）。
//! 这里：左右手武器或持握方式变了 REBIND_AFTER 秒后（新武器已经在手上），把拿着的武器的光效摘掉，让游戏按装备重挂；
//! CHECK_AFTER 秒后游戏还没挂回来就自己挂上（记在 ours，不拿着那把武器了就摘掉）。结果写日志（开头「传说光效」）。
//! 身上有别的挂在武器上的光效（原版油脂、附魔祷告、战技的附魔……，光效行 effectType 1 / 2）时不动光效：摘掉再挂上会把那些附魔顶掉
//! （用户 2026-11-05「这样修会把岩石剑之类的附魔效果顶掉」），等附魔没了再重挂。
//! 开发工具（F9「传说光效测试」）写 glow_req.txt：「重挂」马上做一次（不等换武器）、「查」记一行现在拿的武器和身上的光效。
//! 定义：affixes.txt 的 glow 行「glow<TAB>属性<TAB>效果编号」（重随写）；没有就什么都不做。每 3 帧看一次左右手武器编号

use std::collections::HashSet;
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{ChrInsExt, EquipParamWeapon, GameDataMan, SoloParamRepository, SpEffectVfxParam, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

const EVERY: u32 = 3;
/// 换武器后等多久再重挂：换武器的动作大约 0.5~0.9 秒，新模型在中途拿到手上
const REBIND_AFTER: Duration = Duration::from_millis(1000);
/// 摘掉后等多久看游戏有没有挂回来
const CHECK_AFTER: Duration = Duration::from_millis(300);
/// 一次进游戏日志最多记几行（换武器很频繁）
const LOG_MAX: u32 = 60;
/// 生成武器的编号从这里起，以下是原版
const OWN_WEAPON: i32 = 100_000_000;
const REQ_FILE: &str = "glow_req.txt";

static DEF: OnceLock<HashSet<i32>> = OnceLock::new();

#[derive(Default)]
struct St {
    n: u32,
    /// 上次看到的（左手武器, 右手武器, 持握方式）
    key: Option<(i32, i32, u32)>,
    /// 换了武器的时间（等 REBIND_AFTER 再重挂）
    changed_at: Option<Instant>,
    /// 摘掉了、等着看游戏挂不挂回来的光效
    pending: Vec<(i32, Instant)>,
    /// 游戏没挂回来、自己挂上的光效
    ours: HashSet<i32>,
    /// 该重挂了但身上有附魔，等附魔没了再重挂（为什么重挂、附魔那行日志记过没有）
    waiting: Option<(&'static str, bool)>,
    told: u32,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

fn parse(text: &str) -> HashSet<i32> {
    text.lines()
        .filter_map(|l| {
            let f: Vec<&str> = l.trim_end().split('\t').collect();
            (f.len() >= 3 && f[0] == "glow").then(|| f[2].parse::<i32>().ok()).flatten()
        })
        .filter(|&sp| sp > 0)
        .collect()
}

fn def() -> &'static HashSet<i32> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("affixes.txt")).unwrap_or_default()))
}

pub fn describe() -> String {
    let d = def();
    if d.is_empty() {
        return "传说光效重挂：没有定义".into();
    }
    format!("传说光效重挂：{} 种光效，换武器 {:.1} 秒后重挂", d.len(), REBIND_AFTER.as_secs_f32())
}

fn say(st: &mut St, line: String) {
    if st.told < LOG_MAX {
        st.told += 1;
        log(&line);
    }
}

pub fn tick() {
    let d = def();
    if d.is_empty() {
        return;
    }
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    st.n = st.n.wrapping_add(1);
    // 开发工具的请求（每 30 帧看一次文件）
    let req = if st.n % 30 == 0 {
        let path = dir().join(REQ_FILE);
        fs::read_to_string(&path).ok().inspect(|_| {
            let _ = fs::remove_file(&path);
        })
    } else {
        None
    };
    if st.n % EVERY != 0 && req.is_none() {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        // 没有角色（标题画面、读档中）：从头来，自己挂的游戏读档时都清了
        st.key = None;
        st.changed_at = None;
        st.pending.clear();
        st.ours.clear();
        st.waiting = None;
        return;
    };
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return };
    let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return };
    let asm = &gdm.main_player_game_data.equipment.chr_asm;
    let slot_id = |slot: usize| asm.equipment_param_ids.get(slot).copied().unwrap_or(-1);
    let (lid, rid) = (slot_id(asm.equipment.active_left_weapon_slot() as usize), slot_id(asm.equipment.active_right_weapon_slot() as usize));
    let style = asm.equipment.arm_style as u32;
    let glow_of = |id: i32| -> Option<i32> {
        if id < OWN_WEAPON {
            return None;
        }
        let sp = repo.get::<EquipParamWeapon>((id / 100 * 100) as u32)?.resident_sp_effect_id2();
        d.contains(&sp).then_some(sp)
    };
    let held: Vec<i32> = [lid, rid].into_iter().filter_map(glow_of).collect();
    let now = Instant::now();
    macro_rules! have {
        ($sp:expr) => {
            p.chr_ins.special_effect.entries().any(|e| e.param_id == $sp)
        };
    }
    // 身上别的挂在武器上的光效（附魔）：有就返回它的效果编号
    macro_rules! enchant {
        () => {
            p.chr_ins.special_effect.entries().filter(|e| !d.contains(&e.param_id)).find_map(|e| {
                let pr = unsafe { e.param_data?.as_ref() };
                let vids = [pr.vfx_id(), pr.vfx_id1(), pr.vfx_id2(), pr.vfx_id3(), pr.vfx_id4(), pr.vfx_id5(), pr.vfx_id6(), pr.vfx_id7()];
                vids.iter()
                    .any(|&v| v > 0 && repo.get::<SpEffectVfxParam>(v as u32).is_some_and(|x| matches!(x.effect_type(), 1 | 2)))
                    .then_some(e.param_id)
            })
        };
    }

    // 自己挂的：不拿着那把武器了就摘掉
    let drop: Vec<i32> = st.ours.iter().copied().filter(|sp| !held.contains(sp)).collect();
    for sp in drop {
        st.ours.remove(&sp);
        if have!(sp) {
            p.remove_speffect(sp);
        }
    }

    // 换武器 / 持握方式变了：等 REBIND_AFTER 再重挂（第一次看到不算，读档时游戏自己挂好了）
    let key = (lid, rid, style);
    if st.key != Some(key) {
        if st.key.is_some() {
            st.changed_at = Some(now);
        }
        st.key = Some(key);
    }
    let manual = req.as_deref().is_some_and(|r| r.contains("重挂"));
    if manual || st.changed_at.is_some_and(|t| now.duration_since(t) >= REBIND_AFTER) {
        st.changed_at = None;
        st.waiting = (!held.is_empty()).then_some((if manual { "开发工具要求" } else { "换了武器" }, false));
    }
    if let Some((why, told)) = st.waiting {
        if held.is_empty() {
            st.waiting = None;
        } else if let Some(x) = enchant!() {
            // 身上有附魔：先不动（摘掉再挂会把附魔顶掉），附魔没了再重挂
            if !told {
                st.waiting = Some((why, true));
                say(st, format!("传说光效：{why}，但身上有附魔效果 {x}，先不重挂（会把它顶掉），附魔没了再重挂"));
            }
        } else {
            st.waiting = None;
            for &sp in &held {
                if st.pending.iter().any(|x| x.0 == sp) {
                    continue;
                }
                let on = have!(sp);
                if on {
                    p.remove_speffect(sp);
                    st.ours.remove(&sp);
                }
                st.pending.push((sp, now));
                say(st, format!("传说光效：{why}，摘下光效 {sp}（之前{}）让游戏按装备重挂；左手 {lid} 右手 {rid} 持握 {style}", if on { "在身上" } else { "不在身上" }));
            }
        }
    }

    // 摘掉 CHECK_AFTER 后：游戏挂回来了最好（这时绑在新武器上）；没挂回来就自己挂
    let due: Vec<i32> = st.pending.iter().filter(|x| now.duration_since(x.1) >= CHECK_AFTER).map(|x| x.0).collect();
    st.pending.retain(|x| now.duration_since(x.1) < CHECK_AFTER);
    let busy = if due.is_empty() { None } else { enchant!() };
    for sp in due {
        if busy.is_some() {
            // 附魔还在：过一会儿再看（不摘、不挂）
            if held.contains(&sp) {
                st.pending.push((sp, now));
            }
        } else if have!(sp) {
            say(st, format!("传说光效：游戏把光效 {sp} 挂回来了"));
        } else if held.contains(&sp) {
            p.apply_speffect(sp, false);
            st.ours.insert(sp);
            say(st, format!("传说光效：游戏没把光效 {sp} 挂回来，自己挂上"));
        }
    }

    if req.as_deref().is_some_and(|r| r.contains("查")) {
        let on: Vec<i32> = d.iter().copied().filter(|&sp| have!(sp)).collect();
        log(&format!(
            "传说光效（查）：左手 {lid} 右手 {rid} 持握 {style}；拿着的武器的光效 {held:?}；身上的光效 {on:?}；自己挂的 {:?}；附魔 {:?}",
            st.ours,
            enchant!()
        ));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_glow_lines() {
        let d = parse("wbase\t1\t2\nglow\t1\t7092020\nglow\t2\t7092030\nglow\t4\t-1\nglow\tx\n");
        assert_eq!(d, HashSet::from([7092020, 7092030]));
    }
}
