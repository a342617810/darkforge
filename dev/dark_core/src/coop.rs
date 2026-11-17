//! 联机诊断（用户 2026-11-02，计划见 dev\coop\联机计划.md）：只记录，不改任何游戏行为。用来弄清「dark_core 直接改敌人的词条在
//! Seamless Co-op 联机里会不会同步」：
//! - 进游戏记一次 Seamless Co-op（ersc.dll）有没有加载；
//! - 每 EVERY 帧读一次游戏的会话管理器（CSSessionManager）：大厅状态（主机 / 客机 / 不在会话中）、人数、本机是不是主机，变了记一行；
//! - 在会话里时，积木引擎对敌人的四种直接改动（挂 / 摘效果、改动作速度、改架势）和时隙改速度记一行：目标的实体编号（两台电脑一样，
//!   用来对照两边的日志）、阵营、网络权字段、「按距离分配网络更新权」标志；CHECK_AFTER 后回查这个改动还在不在；
//! - 在会话里时，周围角色身上出现了不是本机挂的词条效果（编号 OURS，命中标记这类按本机攻击挂的除外）记一行：推测是对方挂的、游戏同步过来的。
//! 不在会话里只每 EVERY 帧读一次大厅状态；同一种改动最多记 PER_KIND 次、每次进游戏最多 MAX_LINES 行

use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use eldenring::cs::{CSSessionManager, ChrIns, WorldChrMan};
use fromsoftware_shared::FromStatic;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::core::w;

use crate::log;

const EVERY: u32 = 30;
const MAX_LINES: u32 = 400;
const PER_KIND: u32 = 6;
const CHECK_AFTER: Duration = Duration::from_secs(1);
/// 本机挂的效果多久以内还算「本机的」（之后再看到就当外来的）
const RECENT: Duration = Duration::from_secs(5);
/// 词条库自己的效果编号段（新词条的标记、扣血档、异常累积、猎印等都在这里）
const OURS: std::ops::Range<i32> = 7_200_000..7_300_000;

static ACTIVE: AtomicBool = AtomicBool::new(false);
static ERSC: AtomicBool = AtomicBool::new(false);

/// Seamless Co-op（ersc.dll）加载了没有：加载了游戏就只用联机存档（ER0000.rng.co2，格子编号和单机各算各的），
/// 角色记录要放 角色记录\联机\（gear.rs 的 data_dir；dark_sell、dark_lock 各自也这样判断，dev\coop\联机计划.md 1.1）。
/// 加载以后不会卸载，查到一次就记住；没加载时每次现查（它可能比本 DLL 晚加载）
pub fn ersc_loaded() -> bool {
    if ERSC.load(Ordering::Relaxed) {
        return true;
    }
    let on = unsafe { GetModuleHandleW(w!("ersc.dll")) }.is_ok();
    if on && !ERSC.swap(true, Ordering::Relaxed) {
        log("联机诊断：Seamless Co-op 已加载，角色记录改用 角色记录\\联机（联机存档 ER0000.rng.co2 的格子编号和单机各算各的）");
    }
    on
}

/// 一次对别的角色的直接改动
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Op {
    Apply(i32),
    Remove(i32),
    Speed(f32),
    Poise(f32),
    /// 时隙改动作速度（每帧都写，每个角色只记第一次）
    Slip(f32),
}

impl Op {
    fn text(&self) -> String {
        match self {
            Op::Apply(sp) => format!("挂效果 {sp}"),
            Op::Remove(sp) => format!("摘效果 {sp}"),
            Op::Speed(m) => format!("改动作速度 ×{m:.2}"),
            Op::Poise(v) => format!("改架势 → {v:.0}"),
            Op::Slip(m) => format!("时隙改动作速度 ×{m:.2}"),
        }
    }

    /// 限流用的种类：效果按编号分，速度 / 架势各算一种
    fn kind(&self) -> (u8, i32) {
        match self {
            Op::Apply(sp) => (0, *sp),
            Op::Remove(sp) => (1, *sp),
            Op::Speed(_) => (2, 0),
            Op::Poise(_) => (3, 0),
            Op::Slip(_) => (4, 0),
        }
    }
}

struct Check {
    at: Instant,
    chr: usize,
    who: String,
    op: Op,
}

#[derive(Default)]
struct St {
    frame: u32,
    ersc_logged: bool,
    /// 上次的（大厅状态, 人数, 本机是主机）
    last: Option<(u32, usize, bool)>,
    lines: u32,
    per_kind: HashMap<(u8, i32), u32>,
    checks: Vec<Check>,
    /// 本机最近挂的（角色地址, 效果）→ 时间
    mine: HashMap<(usize, i32), Instant>,
    /// 记过的外来效果（实体编号, 效果）
    foreign_seen: HashSet<(u32, i32)>,
    /// 时隙记过的角色
    slip_seen: HashSet<usize>,
    /// 按本机攻击由游戏挂的效果（命中标记等，积木引擎给），不算外来
    ignore: HashSet<i32>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 现在是不是在联机会话里（主机或客机）
pub fn active() -> bool {
    ACTIVE.load(Ordering::Relaxed)
}

fn say(st: &mut St, s: &str) {
    if st.lines >= MAX_LINES {
        return;
    }
    st.lines += 1;
    log(&format!("联机诊断：{s}"));
    if st.lines == MAX_LINES {
        log("联机诊断：这次进游戏记满了，后面不再记");
    }
}

fn lobby_name(v: u32) -> &'static str {
    match v {
        0 => "不在会话中",
        1 => "正在建会话",
        2 => "建会话失败",
        3 => "主机",
        4 => "正在加入",
        5 => "加入失败",
        6 => "客机",
        7 => "正在离开",
        8 => "离开失败",
        _ => "未知",
    }
}

/// （大厅状态的原始值, 会话里几个人, 本机是不是主机）
fn session() -> Option<(u32, usize, bool)> {
    let sm = unsafe { CSSessionManager::instance() }.ok()?;
    // 按原始数值读（枚举里没有的值不能直接当枚举用）
    let raw = unsafe { *(&sm.lobby_state as *const _ as *const u32) };
    let host = sm.players.iter().any(|p| p.is_local_player && p.is_host);
    Some((raw, sm.players.len(), host))
}

pub(crate) fn describe_chr(c: &ChrIns) -> String {
    format!(
        "NPC {}（实体 {}，阵营 {}，网络权 {}，按距离同步 {}，联机人数修正 {}）",
        c.npc_param_id,
        c.event_entity_id,
        c.team_type,
        c.network_authority,
        if c.net_chr_sync_flags.distance_based_network_update_authority() { "是" } else { "否" },
        c.coop_players_for_multiplay_correction
    )
}

/// 积木引擎 / 时隙改别的角色之前调：在会话里才记
pub fn note(op: Op, c: &ChrIns) {
    if !active() {
        return;
    }
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let Some(st) = g.as_mut() else { return };
    let ptr = c as *const ChrIns as usize;
    let now = Instant::now();
    if let Op::Apply(sp) = op {
        st.mine.insert((ptr, sp), now);
    }
    if let Op::Slip(_) = op {
        if !st.slip_seen.insert(ptr) {
            return;
        }
    }
    let n = st.per_kind.entry(op.kind()).or_default();
    if *n >= PER_KIND {
        return;
    }
    *n += 1;
    let who = describe_chr(c);
    say(st, &format!("本机{}：{who}", op.text()));
    st.checks.push(Check { at: now + CHECK_AFTER, chr: ptr, who, op });
}

/// 积木引擎给：按本机攻击由游戏挂到敌人身上的效果（命中标记等），外来效果不算它们
pub fn set_ignore(ids: impl Iterator<Item = i32>) {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(st) = g.as_mut().filter(|st| st.ignore.is_empty()) {
        st.ignore.extend(ids);
    }
}

fn has_sp(c: &ChrIns, sp: i32) -> bool {
    c.special_effect.entries().any(|s| s.param_id == sp)
}

fn check_text(c: &ChrIns, op: Op) -> String {
    match op {
        Op::Apply(sp) => if has_sp(c, sp) { format!("效果 {sp} 还在") } else { format!("效果 {sp} 已经没了（到期或被同步覆盖）") },
        Op::Remove(sp) => if has_sp(c, sp) { format!("效果 {sp} 又出现了（可能被同步回来）") } else { format!("效果 {sp} 确实摘掉了") },
        Op::Speed(m) | Op::Slip(m) => format!("动作速度现在 ×{:.2}（写的 ×{m:.2}）", c.modules.behavior.animation_speed),
        Op::Poise(v) => format!("架势现在 {:.0}（写的 {v:.0}，上限 {:.0}）", c.modules.super_armor.sa_durability, c.modules.super_armor.sa_durability_max),
    }
}

pub fn tick() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    if !st.ersc_logged {
        st.ersc_logged = true;
        log(&format!("联机诊断：Seamless Co-op（ersc.dll）{}", if ersc_loaded() { "已加载" } else { "没有加载" }));
    }
    st.frame = st.frame.wrapping_add(1);
    if st.frame % EVERY != 0 {
        return;
    }
    let s = session();
    if s != st.last {
        let text = match s {
            Some((l, n, h)) => format!("大厅状态 {}，会话里 {n} 人，本机{}主机", lobby_name(l), if h { "是" } else { "不是" }),
            None => "读不到会话管理器".to_string(),
        };
        say(st, &text);
        st.last = s;
    }
    let on = matches!(s, Some((3 | 6, ..)));
    ACTIVE.store(on, Ordering::Relaxed);
    if !on {
        st.checks.clear();
        st.mine.clear();
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(me) = wcm.main_player.as_ref().map(|p| &p.chr_ins as *const ChrIns as usize) else { return };
    let now = Instant::now();
    // 回查到时间的改动（角色还在场才看：地址可能已经释放）
    if st.checks.iter().any(|c| c.at <= now) {
        let alive = live!(wcm);
        let (due, keep): (Vec<Check>, Vec<Check>) = std::mem::take(&mut st.checks).into_iter().partition(|c| c.at <= now);
        st.checks = keep;
        for c in due {
            let text = if alive.contains(&c.chr) {
                check_text(unsafe { &*(c.chr as *const ChrIns) }, c.op)
            } else {
                "角色已经不在场".to_string()
            };
            say(st, &format!("1 秒后回查（{}）：{}：{text}", c.op.text(), c.who));
        }
    }
    // 外来效果：周围角色身上有词条库的效果、但不是本机最近挂的
    if let Some(around) = around!(wcm, me) {
        let mut found = Vec::new();
        for e in &around {
            let ptr = e.chr_ins.as_ptr() as usize;
            if ptr == me {
                continue;
            }
            let c = unsafe { e.chr_ins.as_ref() };
            for sp in c.special_effect.entries().map(|s| s.param_id) {
                if !OURS.contains(&sp) || st.ignore.contains(&sp) {
                    continue;
                }
                if st.mine.get(&(ptr, sp)).is_some_and(|t| now.duration_since(*t) < RECENT) {
                    continue;
                }
                if st.foreign_seen.insert((c.event_entity_id, sp)) {
                    found.push(format!("{}（{:.1} 米）身上有效果 {sp}，不是本机最近挂的", describe_chr(c), e.distance));
                }
            }
        }
        for f in found {
            say(st, &format!("外来效果：{f}"));
        }
    }
    st.mine.retain(|_, t| now.duration_since(*t) < RECENT * 4);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn op_kinds_and_text() {
        assert_eq!(Op::Apply(7210001).kind(), (0, 7210001));
        assert_eq!(Op::Speed(0.4).kind(), Op::Speed(0.9).kind(), "速度不分数值算一种");
        assert_eq!(Op::Poise(12.0).text(), "改架势 → 12");
        assert_eq!(lobby_name(3), "主机");
        assert_eq!(lobby_name(6), "客机");
        assert!(!active(), "没进会话不算联机");
    }
}
