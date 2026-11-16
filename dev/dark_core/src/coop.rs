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
/// 在会话里、而且本机是房主（大厅状态 3）
static HOST: AtomicBool = AtomicBool::new(false);
/// 会话标记（联机计划 13.3 C3；92570~92581 扫过没人用，dev\event_flags\说明.md 登记了）：在会话里 / 本机是房主时点亮，
/// 不在会话里熄灭。菜单脚本按它们隐藏会话里不能用的功能（launcher\reroll\sc 里同样写死这两个编号，两边一起改）。
/// 92000 块会存档：万一会话中途崩了留着亮的，下次进游戏 0.5 秒内这里就熄灭
pub const SESSION_FLAG: u32 = 92570;
pub const HOST_FLAG: u32 = 92571;
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

/// 在会话里、本机是客机：直接写敌人内存的那些（联机计划 13.2 G2）、魇化抽签（G3）这时跳过
pub fn client() -> bool {
    ACTIVE.load(Ordering::Relaxed) && !HOST.load(Ordering::Relaxed)
}

/// 在会话里、本机是房主（联机随机码、自动兼容比对这些以后会用）
#[allow(dead_code)]
pub fn host() -> bool {
    HOST.load(Ordering::Relaxed)
}

/// 客机跳过了一种直接改敌人的操作：每种只记一行（联机计划 13.2 G2）
static SKIPPED: Mutex<Vec<&'static str>> = Mutex::new(Vec::new());

/// 本机是客机就记一行、返回 true（调用处跳过这次写入）；不是客机返回 false
pub fn client_skip(what: &'static str) -> bool {
    if !client() {
        return false;
    }
    let mut g = SKIPPED.lock().unwrap_or_else(|e| e.into_inner());
    if !g.contains(&what) {
        g.push(what);
        log(&format!("联机：本机是客机，{what}跳过（敌人一侧只让房主改，联机计划 13.2 G2；之后同类不再记）"));
    }
    true
}

/// 会话标记跟着现在的状态走（不一样才写）
fn sync_flag(f: u32, on: bool) -> bool {
    if crate::gear::flag_get(f) == Some(on) {
        return false;
    }
    crate::gear::flag_set(f, on)
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

/// 会话里的一个人（联机通道 link.rs 用）
pub struct Member {
    pub id: u64,
    pub host: bool,
    pub local: bool,
    /// Steam 名字（赠送菜单里写「送给 <名字>」）
    pub name: String,
}

/// 大厅状态的原始值（读不到会话管理器 None）：0 不在会话中，1 正在建，3 主机，4 正在加入，6 客机……（lobby_name）
pub fn lobby() -> Option<u32> {
    session().map(|s| s.0)
}

/// 人物在场（读档、切图时没有主角）
pub fn in_world() -> bool {
    unsafe { WorldChrMan::instance() }.ok().is_some_and(|w| w.main_player.as_ref().is_some())
}

/// 会话就绪时的名单：大厅状态 主机 / 客机、协议 Ingame（6）、没人在加入中、正好一个本机、ID 不重复不为 0；不然 None。
/// 按原始数值读两个状态（枚举里没有的值不能直接当枚举用）
pub fn roster() -> Option<Vec<Member>> {
    let sm = unsafe { CSSessionManager::instance() }.ok()?;
    let lobby = unsafe { *(&sm.lobby_state as *const _ as *const u32) };
    let proto = unsafe { *(&sm.protocol_state as *const _ as *const u32) };
    if !matches!(lobby, 3 | 6) || proto != 6 {
        return None;
    }
    let mut v: Vec<Member> = Vec::new();
    for p in sm.players.iter() {
        if p.join_wait || p.rebreak_in {
            return None;
        }
        let id = p.base.steam_id;
        if id == 0 || v.iter().any(|m| m.id == id) || v.len() >= 64 {
            return None;
        }
        let name = p.base.steam_name.to_string().unwrap_or_default().trim().to_string();
        v.push(Member { id, host: p.is_host, local: p.is_local_player, name });
    }
    (v.iter().filter(|m| m.local).count() == 1 && v.iter().filter(|m| m.host).count() <= 1).then_some(v)
}

fn describe_chr(c: &ChrIns) -> String {
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
    let host = matches!(s, Some((3, ..)));
    ACTIVE.store(on, Ordering::Relaxed);
    HOST.store(host, Ordering::Relaxed);
    let a = sync_flag(SESSION_FLAG, on);
    let b = sync_flag(HOST_FLAG, host);
    if a || b {
        log(&format!("联机：会话标记 {SESSION_FLAG} {}、房主标记 {HOST_FLAG} {}", if on { "亮" } else { "灭" }, if host { "亮" } else { "灭" }));
    }
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
