//! 法球从法器的发射点位射出（用户 2026-11-05「法球发射能做成直接发射身边环绕的法球而不是从身体中间发射吗」→
//! 「或者改成从原版法杖的发射点位发射 看着好些」）。
//! 法球照常给自己挂「放子弹」的效果（效果 → 行为 → 子弹，伤害走游戏自己的路子），挂之前把效果的点位（SpEffectParam.dmypolyId，
//! 参数说明「点位 0~999，千位、万位是类别」）改成拿法器那只手的武器点位（右手 10000 + n、左手 20000 + n，同原版动作事件的写法；
//! 用户试过 100 号点合适）。以前这一栏没填（-1），子弹从身体中间出来。
//! - 2026-11-05 ~ 11-11 用的是直接调游戏生成子弹的函数（fromsoftware-rs 的 CSBulletManager::spawn_bullet，RVA 0x3a2cb0）：
//!   点位对了，可是没有「行为」，伤害算不对（用户 2026-11-11「伤害太低了 甚至都是个位数」），所以法球不再用它；
//!   生成子弹的函数留给死亡以上难度错配屏障的圆顶（spawn_at，barrier.rs），调之前照旧比对函数开头的特征码。
//! - 积木引擎（rules.rs）的法球那档、runtime.txt 有 orbshot 行才改点位（Act::Shot → aim）；
//! - 开发工具「法球发射点测试」：orbshot_req.txt 一行「shot <点位>」= 最低一档的法球效果改成这个点位、挂给自己（同正式的路子），写日志。
use std::fs;
use std::sync::atomic::{AtomicI32, AtomicU32, Ordering};
use std::sync::Mutex;

use eldenring::cs::{BulletSpawnData, CSBulletManager, ChrIns, ChrInsExt, EquipParamWeapon, GameDataMan, SoloParamRepository, SpEffectParam, WorldChrMan};
use fromsoftware_shared::{F32Vector4, FromStatic};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;

use crate::{dir, log};

/// 生成子弹函数的 RVA（fromsoftware-rs 的 rva 表：1.17.1 / 1.17.2 同址；库里的 rva 模块不对外，这里自己比对）和开头的特征码
/// （同它的 mapper-profile；本机 2.7.1.0 只在这一处出现，2026-11-05 查过）
const SPAWN_RVA: usize = 0x3a2cb0;
const PROLOGUE: [u8; 21] = [0x40, 0x53, 0x55, 0x56, 0x57, 0x48, 0x81, 0xec, 0x98, 0x07, 0x00, 0x00, 0x48, 0xc7, 0x44, 0x24, 0x50, 0xfe, 0xff, 0xff, 0xff];
const REQ: &str = "orbshot_req.txt";
/// 法杖、圣印记的武器类型
const STAFF: u16 = 57;
const SEAL: u16 = 61;

/// 特征码比对结果：0 没比、1 对得上、2 对不上
static CHECKED: AtomicU32 = AtomicU32::new(0);
/// 测试用的（最低一档的法球）：放子弹的效果、它的伤害
static TEST_SP: AtomicI32 = AtomicI32::new(-1);
static TEST_DMG: AtomicU32 = AtomicU32::new(u32::MAX);
static WAIT: Mutex<u32> = Mutex::new(0);

/// rules.rs 读 runtime.txt 时报法球那套的档位：留伤害最低的一档给测试用
pub fn offer_test(dmg: f32, sp: i32) {
    let d = dmg.max(0.0) as u32;
    if d < TEST_DMG.load(Ordering::Relaxed) {
        TEST_DMG.store(d, Ordering::Relaxed);
        TEST_SP.store(sp, Ordering::Relaxed);
    }
}

/// 拿法器那只手的武器点位：右手 10000 + 右、左手 20000 + 左（dmys = runtime.txt 的 orbshot 行）
fn hand_dmy(dmys: (i32, i32)) -> i32 {
    if catalyst_right() { 10000 + dmys.0 } else { 20000 + dmys.1 }
}

/// 把放子弹的效果 sp 的点位改成 dmy（游戏挂这个效果时，行为从这个点位放子弹）；行不在参数里 / 点位超出这一栏的范围 = false
fn set_dmy(sp: i32, dmy: i32) -> bool {
    let Ok(dmy16) = i16::try_from(dmy) else { return false };
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return false };
    let Some(row) = repo.get_mut::<SpEffectParam>(sp as u32) else { return false };
    row.set_dmypoly_id(dmy16);
    true
}

/// 积木引擎的法球（Act::Shot，挂效果之前调）：效果的点位改成拿法器那只手的武器点位；返回用的点位（改不了 = None，照旧从身体中间放）
pub fn aim(sp: i32, dmys: (i32, i32)) -> Option<i32> {
    let dmy = hand_dmy(dmys);
    set_dmy(sp, dmy).then_some(dmy)
}

/// 生成子弹函数在不在（第一次调时比对特征码，记日志）
fn usable() -> bool {
    match CHECKED.load(Ordering::Relaxed) {
        1 => return true,
        2 => return false,
        _ => {}
    }
    let ok = (|| {
        let base = unsafe { GetModuleHandleW(None) }.ok()?.0 as usize;
        // SAFETY: 游戏主程序代码段，进程里一直映射着
        let b = unsafe { std::slice::from_raw_parts((base + SPAWN_RVA) as *const u8, PROLOGUE.len()) };
        Some(b == PROLOGUE)
    })()
    .unwrap_or(false);
    CHECKED.store(if ok { 1 } else { 2 }, Ordering::Relaxed);
    log(&format!("法球发射点：生成子弹的函数{}", if ok { "对得上，可以直接从法器点位射出" } else { "特征码对不上，不用（照旧挂效果）" }));
    ok
}

/// 拿着法器的那只手：右手是法杖 / 圣印记就右手，否则左手是就左手，都不是按右手
fn catalyst_right() -> bool {
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return true };
    let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return true };
    let asm = &gdm.main_player_game_data.equipment.chr_asm;
    let id = |slot: usize| asm.equipment_param_ids.get(slot).copied().unwrap_or(-1);
    let is_cat = |pid: i32| {
        pid > 0 && repo.get::<EquipParamWeapon>((pid - pid % 100) as u32).is_some_and(|w| matches!(w.wep_type(), STAFF | SEAL))
    };
    let (l, r) = (id(asm.equipment.active_left_weapon_slot() as usize), id(asm.equipment.active_right_weapon_slot() as usize));
    is_cat(r) || !is_cat(l)
}

/// 在 pos（物理坐标）放一颗 bullet，不指定点位、朝北（死亡以上难度错配屏障的圆顶，barrier.rs：公共事件没放出来时补放）
pub fn spawn_at(chr: &ChrIns, bullet: i32, pos: [f32; 3]) -> Result<(), String> {
    if !usable() {
        return Err("生成子弹的函数对不上".into());
    }
    let Ok(bm) = (unsafe { CSBulletManager::instance_mut() }) else { return Err("没有子弹管理器".into()) };
    let data = BulletSpawnData::new(chr.field_ins_handle, bullet, -1, F32Vector4(0.0, 0.0, 1.0, 0.0), F32Vector4(pos[0], pos[1], pos[2], 1.0));
    bm.spawn_bullet(&data).map_err(|e| format!("游戏返回错误 {e}"))
}

/// 开发工具的测试请求（每 15 帧看一次）
pub fn tick() {
    {
        let mut w = WAIT.lock().unwrap_or_else(|e| e.into_inner());
        *w = w.wrapping_add(1);
        if *w % 15 != 0 {
            return;
        }
    }
    let path = dir().join(REQ);
    let Ok(text) = fs::read_to_string(&path) else { return };
    let _ = fs::remove_file(&path);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        log("法球发射点测试：人物还没生成");
        return;
    };
    let sp = TEST_SP.load(Ordering::Relaxed);
    for line in text.lines().map(|l| l.trim_start_matches('\u{feff}').trim()).filter(|l| !l.is_empty()) {
        let f: Vec<&str> = line.split_whitespace().collect();
        let dmy = match f.as_slice() {
            ["shot", d] => d.parse::<i32>().ok(),
            _ => None,
        };
        let Some(dmy) = dmy else {
            log(&format!("法球发射点测试：看不懂这一行：{line}"));
            continue;
        };
        if sp < 0 {
            log("法球发射点测试：runtime.txt 里没有法球档位（还没重随）");
            return;
        }
        let hand = if catalyst_right() { "右手" } else { "左手" };
        if !set_dmy(sp, dmy) {
            log(&format!("法球发射点测试：效果 {sp} 的点位改不成 {dmy}（不在参数里，或者点位超出范围）"));
            continue;
        }
        p.chr_ins.apply_speffect(sp, false);
        log(&format!("法球发射点测试：效果 {sp} 改成点位 {dmy}、挂给自己（现在拿法器的是{hand}）"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bullet_lowest() {
        offer_test(400.0, 3);
        offer_test(40.0, 1);
        offer_test(90.0, 2);
        assert_eq!(TEST_SP.load(Ordering::Relaxed), 1);
    }
}
