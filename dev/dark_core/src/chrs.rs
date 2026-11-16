//! 周围角色的安全遍历。游戏的「按距离排序的角色列表」WorldChrMan::chr_inses_by_distance 读图时会失效：
//! - 切存档 / 读档时还留着上一个世界已经释放的角色，直接解引用就内存访问错误（2026-11-01 玩家诊断包，v0.8：进存档那一刻
//!   dark_core 崩在 runtime::tick（时隙）和 boat::tick（唤声船），十次都是）；
//! - 新开局读图那一刻连列表本身的内存都读不了（2026-11-01 第二份诊断包，v0.8.1：崩在 rules::tick 读距离那一步）。
//! 所以：
//! - live!：从游戏自己维护的各个 ChrSet 收集在场角色的地址（不碰距离列表），用来核对一个地址还在不在；
//! - around!：要距离的功能先确认距离列表正常加载了再用。每次用 ReadProcessMemory 把整张列表复制出来（内存读不了时它返回失败，
//!   不会崩），项数、距离要正常，不能是空的（读图时是空的），每一项都得是在场的角色；这样连续 READY 才算就绪，之后用这一份副本
//!   （个别不在场的项跳过）。主角换了、检查中断超过 GAP、列表读不了 / 不正常 / 空了、一半以上的项不在场（换了世界）就重新等。
//! - 列表里没有主角自己；进图后头几帧会有负的距离（-1~-3，日志里见过），不算坏。
//! - v0.8.2 一度改成按物理位置自己算距离，用户觉得不靠谱，查实确实不对：物理位置是各自地图块里的坐标，跨地图块直接相减没意义
//!   （2026-11-01 运行中读：游戏距离 13.5 米的敌人按位置算 103 米）。改回用游戏的距离、加就绪检查。
//! 宏里只借 WorldChrMan 的这几个字段，调用处同时可变借着 main_player 也行。

use std::collections::HashSet;
use std::ffi::c_void;
use std::ptr::NonNull;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::{ChrIns, ChrSet, PlayerIns, WorldChrMan};
use fromsoftware_shared::{FromStatic, OwnedPtr, Subclass};
use windows::Win32::System::Diagnostics::Debug::ReadProcessMemory;
use windows::Win32::System::Threading::GetCurrentProcess;

use crate::log;

/// 在场角色的地址（玩家、灵体、召唤、调试、开放地图、各地图块的 ChrSet）
macro_rules! live {
    ($w:expr) => {
        $crate::chrs::collect(
            &$w.player_chr_set,
            [&$w.ghost_chr_set, &$w.summon_buddy_chr_set, &$w.debug_chr_set, &$w.open_field_chr_set.base],
            &$w.chr_sets,
        )
    };
}

/// 周围的角色（游戏算的距离，由近到远），距离列表还没就绪时是 None；$me = 主角 ChrIns 的地址（换了就重新等）
macro_rules! around {
    ($w:expr, $me:expr) => {{
        let t0 = $crate::prof::on().then(std::time::Instant::now);
        let r = $crate::chrs::around(&$w.chr_inses_by_distance, live!($w), $me);
        if let Some(t0) = t0 {
            $crate::prof::around_done(t0.elapsed(), r.as_ref().map_or(0, |v| v.len()));
        }
        r
    }};
}

fn add<T: Subclass<ChrIns> + 'static>(out: &mut HashSet<usize>, s: &ChrSet<T>) {
    out.extend(s.characters().map(|c| c as *mut T as usize));
}

pub fn collect(players: &ChrSet<PlayerIns>, fixed: [&ChrSet<ChrIns>; 4], sets: &[Option<OwnedPtr<ChrSet<ChrIns>>>]) -> HashSet<usize> {
    let mut out = HashSet::new();
    add(&mut out, players);
    for s in fixed {
        add(&mut out, s);
    }
    for s in sets.iter().flatten() {
        add(&mut out, s);
    }
    out
}

/// 玩家角色（本机主角、联机的队友、入侵者：都在 WorldChrMan 的 player_chr_set 里）的地址，每帧开头刷新一次（lib.rs）。
/// 「找敌人」的地方用 rules::is_foe 跳过它们：玩家角色永远不算敌人（联机计划 13.2 G8，单机也一样）。以前只按阵营号排除友方，
/// 入侵的真人玩家会被当成敌人（扣血档、猎印、改架势、减速），时隙还会改队友的速度
static PLAYERS: Mutex<Vec<usize>> = Mutex::new(Vec::new());

pub fn refresh_players() {
    let mut v = Vec::new();
    if let Ok(wcm) = unsafe { WorldChrMan::instance() } {
        v.extend(wcm.player_chr_set.characters().map(|c| c as *mut PlayerIns as usize));
    }
    *PLAYERS.lock().unwrap_or_else(|e| e.into_inner()) = v;
}

/// 这个角色是不是玩家角色（PlayerIns 的第一个字段就是 ChrIns，地址一样）
pub fn is_player(c: &ChrIns) -> bool {
    let a = c as *const ChrIns as usize;
    PLAYERS.lock().unwrap_or_else(|e| e.into_inner()).contains(&a)
}

/// 周围的一个角色（字段名照游戏距离列表的项）
pub struct Near {
    pub chr_ins: NonNull<ChrIns>,
    pub distance: f32,
}

/// 距离列表连续正常多久才用
const READY: Duration = Duration::from_secs(1);
/// 两次检查隔太久（读图时没人用、或者很卡）就当没连上，重新等
const GAP: Duration = Duration::from_millis(500);
/// 等这么久还没就绪就写一次日志（带最近一次不通过的原因）
const SLOW: Duration = Duration::from_secs(10);
/// 列表最多多少项，再多就当读到的是垃圾
const MAX_ITEMS: usize = 8192;
/// 距离列表相对 vendored 结构里 chr_inses_by_distance 的位置：游戏 2.7.2.0 的 WorldChrMan 在它前面多了 0x10 字节（两个 exe 的机器码比对过：
/// 这个字段、chr_cam、按更新优先级的列表都 +0x10），vendored 的定义是 2.7.1.0 的。不按版本号分，逐个试，整张列表都是在场的角色才认
/// （玩家诊断包 2026-11-09：2.7.2.0 上一直「列表头不对：堆地址..模块地址」，读到的 last 其实是这张表的分配器，靠周围角色的词条全不工作）
const HEAD_DELTAS: [usize; 2] = [0, 0x10];
const DELTA_UNKNOWN: usize = usize::MAX;
static HEAD_DELTA: AtomicUsize = AtomicUsize::new(DELTA_UNKNOWN);

struct Gate {
    me: usize,
    last: Option<Instant>,
    since: Option<Instant>,
    ready: bool,
    wait_from: Option<Instant>,
    told: bool,
}

static GATE: Mutex<Gate> = Mutex::new(Gate { me: 0, last: None, since: None, ready: false, wait_from: None, told: false });

pub fn around<T>(list: &T, live: HashSet<usize>, me: usize) -> Option<Vec<Near>> {
    let now = Instant::now();
    let mut g = GATE.lock().unwrap_or_else(|e| e.into_inner());
    if g.me != me || g.last.is_none_or(|t| now - t > GAP) {
        *g = Gate { me, last: None, since: None, ready: false, wait_from: Some(now), told: false };
    }
    g.last = Some(now);
    let res = read_list(list as *const T as *const u8, &live, g.ready);
    match res {
        Err(why) => {
            if g.ready {
                log(&format!("周围角色：距离列表失效（{why}），用到周围角色的词条先停下，等它恢复"));
                g.wait_from = Some(now);
                g.told = false;
            }
            g.ready = false;
            g.since = None;
            if !g.told && g.wait_from.is_some_and(|t| now - t >= SLOW) {
                g.told = true;
                log(&format!("周围角色：距离列表 {} 秒还没就绪（{why}），用到周围角色的词条还没开始", SLOW.as_secs()));
            }
            None
        }
        Ok(items) => {
            let since = *g.since.get_or_insert(now);
            if !g.ready {
                if now - since < READY {
                    return None;
                }
                g.ready = true;
                log(&format!("周围角色：距离列表正常（{} 项），开始用", items.len()));
            }
            Some(items.into_iter().filter_map(|(a, distance)| Some(Near { chr_ins: NonNull::new(a as *mut ChrIns)?, distance })).collect())
        }
    }
}

/// 读距离列表：位置认出来了就照它读；没认出来就逐个试（读图时列表是空的、都不通过，下一轮再试）
fn read_list(base: *const u8, live: &HashSet<usize>, ready: bool) -> Result<Vec<(usize, f32)>, String> {
    let known = HEAD_DELTA.load(Ordering::Relaxed);
    if known != DELTA_UNKNOWN {
        return snapshot(unsafe { base.add(known) } as *const usize).and_then(|items| judge(items, live, ready));
    }
    let (delta, items) = find_head(base, live)?;
    HEAD_DELTA.store(delta, Ordering::Relaxed);
    if delta != 0 {
        log(&format!("周围角色：距离列表在原定义之后 {delta:#x} 字节（游戏 2.7.2.0）"));
    }
    Ok(items)
}

/// 逐个位置试，第一个整张都是在场角色的算数；都不对返回第一个位置的原因（日志照旧）
fn find_head(base: *const u8, live: &HashSet<usize>) -> Result<(usize, Vec<(usize, f32)>), String> {
    let mut why = None;
    for d in HEAD_DELTAS {
        match snapshot(unsafe { base.add(d) } as *const usize).and_then(|items| judge(items, live, false)) {
            Ok(items) => return Ok((d, items)),
            Err(e) => {
                why.get_or_insert(e);
            }
        }
    }
    Err(why.unwrap_or_default())
}

/// 把距离列表整张复制出来：head 指向 std::vector 的头（msvc2015 布局：分配器、first、last、end），每项 16 字节（角色地址、距离、空）。
/// 列表的内存读不了时 ReadProcessMemory 返回失败（不会像直接读那样崩）
fn snapshot(head: *const usize) -> Result<Vec<(usize, f32)>, String> {
    let (first, last) = unsafe { (head.add(1).read(), head.add(2).read()) };
    if first == 0 && last == 0 {
        return Ok(Vec::new());
    }
    if first == 0 || last < first || (last - first) % 16 != 0 || (last - first) / 16 > MAX_ITEMS {
        return Err(format!("列表头不对：{first:#x}..{last:#x}"));
    }
    let n = (last - first) / 16;
    let mut buf = vec![[0u64; 2]; n];
    unsafe { ReadProcessMemory(GetCurrentProcess(), first as *const c_void, buf.as_mut_ptr() as *mut c_void, n * 16, None) }
        .map_err(|_| format!("列表的内存读不了（{n} 项）"))?;
    let mut out = Vec::with_capacity(n);
    for e in &buf {
        let d = f32::from_bits(e[1] as u32);
        if e[0] == 0 || !d.is_finite() || d.abs() > 1e6 {
            return Err(format!("列表里有不正常的项（地址 {:#x}，距离 {d}）", e[0]));
        }
        out.push((e[0] as usize, d));
    }
    Ok(out)
}

/// 列表能不能用：空的不算（读图时是空的）；还没就绪时每一项都得在场；就绪以后个别不在场的跳过（角色刚卸载），一半以上不在场算换了世界
fn judge(items: Vec<(usize, f32)>, live: &HashSet<usize>, ready: bool) -> Result<Vec<(usize, f32)>, String> {
    if items.is_empty() {
        return Err("列表是空的".into());
    }
    let stale = items.iter().filter(|(a, _)| !live.contains(a)).count();
    if stale > 0 && (!ready || stale * 2 > items.len()) {
        return Err(format!("{} 项里 {stale} 项不是在场的角色", items.len()));
    }
    Ok(items.into_iter().filter(|(a, _)| live.contains(a)).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn head(items: &[[u64; 2]]) -> [usize; 4] {
        let first = items.as_ptr() as usize;
        [0, first, first + items.len() * 16, first + items.len() * 16]
    }

    /// 复制：正常的列表照读；读不了的内存、不正常的距离、乱的列表头都报不通过，不崩
    #[test]
    fn snapshot_checks() {
        let items = [[0x1000u64, 2.5f32.to_bits() as u64], [0x2000, 7.0f32.to_bits() as u64]];
        assert_eq!(snapshot(head(&items).as_ptr()), Ok(vec![(0x1000, 2.5), (0x2000, 7.0)]));
        assert_eq!(snapshot([0usize; 4].as_ptr()), Ok(vec![]));
        assert!(snapshot([0, 0x10, 0x30, 0x30].as_ptr()).is_err()); // 指向读不了的内存（v0.8.1 新开局崩的那种）
        assert!(snapshot([0, 0x1000, 0x1008, 0x1008].as_ptr()).is_err()); // 长度不是 16 的倍数
        let bad = [[0x1000u64, f32::NAN.to_bits() as u64]];
        assert!(snapshot(head(&bad).as_ptr()).is_err());
        let near = [[0x1000u64, (-1.8f32).to_bits() as u64]]; // 进图头几帧见过的负距离，不算坏
        assert_eq!(snapshot(head(&near).as_ptr()), Ok(vec![(0x1000, -1.8)]));
    }

    /// 2.7.2.0：原位置读到的 first 是前一个字段、last 是分配器（模块地址），+0x10 才是列表头；2.7.1.0 的原位置直接认
    #[test]
    fn head_delta() {
        let items = [[0x1000u64, 2.5f32.to_bits() as u64], [0x2000, 7.0f32.to_bits() as u64]];
        let live: HashSet<usize> = [0x1000, 0x2000].into_iter().collect();
        let h = head(&items);
        let v272: [usize; 6] = [0, 0x2ccc_2ac7_000, 0x7ffc_0e20_3550, h[1], h[2], h[3]];
        assert_eq!(find_head(v272.as_ptr() as *const u8, &live).map(|x| x.0), Ok(0x10));
        let v271: [usize; 6] = [0x7ffc_0e20_3550, h[1], h[2], h[3], 0, 0];
        assert_eq!(find_head(v271.as_ptr() as *const u8, &live).map(|x| x.0), Ok(0));
        // 读图时两个位置都不通过：不认，报第一个位置的原因
        let empty = [0usize; 6];
        assert_eq!(find_head(empty.as_ptr() as *const u8, &live), Err("列表是空的".to_string()));
    }

    /// 就绪前一项不在场都不行；就绪后个别不在场的跳过，一半以上不在场算换了世界
    #[test]
    fn judge_stale() {
        let live: HashSet<usize> = [1, 2, 3].into_iter().collect();
        let all = vec![(1, 1.0), (2, 2.0), (3, 3.0)];
        let one_gone = vec![(1, 1.0), (2, 2.0), (3, 3.0), (9, 4.0)];
        let most_gone = vec![(1, 1.0), (8, 2.0), (9, 3.0)];
        assert_eq!(judge(all.clone(), &live, false), Ok(all));
        assert!(judge(one_gone.clone(), &live, false).is_err());
        assert_eq!(judge(one_gone, &live, true).map(|v| v.len()), Ok(3));
        assert!(judge(most_gone, &live, true).is_err());
        assert!(judge(vec![], &live, false).is_err()); // 空的 = 还在读图
        assert!(judge(vec![], &live, true).is_err());
    }
}
