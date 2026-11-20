//! 性能记录（用户 2026-11-19「看一下什么导致联机久了游戏会越来越卡直至崩溃」：那份诊断包里只有退出时的崩溃记录，
//! 看不出是什么在涨）。每 5 分钟往 dark_core.log 写一行「性能记录」：
//! - 游戏进程的内存（提交的私有内存、工作集）、系统还剩多少内存、显存（用了多少 / 系统给的预算、共享显存）、句柄数、线程数；
//! - dark_core 自己还占着的内存（全局分配器包一层系统分配器，分配 / 释放时加减计数）、这段时间分配了几次；
//! - 这段时间游戏的帧：平均、最长、超过 33 / 100 毫秒的帧数，超过 1 秒的（读图或卡住）单独数；
//! - dark_core 每帧花的时间（各模块 tick 加起来，lib.rs guarded）和最多的几个模块；
//! - 在不在联机（这段里几成时间在会话里）、地图、在场角色数。
//! 下次再卡，按时间看哪一项在涨。帧里只多记两次时间、加一次锁；到点时在主线程取游戏里的状态（地图、角色数），
//! 内存、显存、线程这些在 dark_core_perf 线程里查、写日志。

use std::alloc::{GlobalAlloc, Layout, System};
use std::fmt::Write;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Mutex, OnceLock, mpsc};
use std::time::{Duration, Instant};

use eldenring::cs::WorldChrMan;
use fromsoftware_shared::FromStatic;

use crate::log;

/// 多久记一行
const EVERY: Duration = Duration::from_secs(300);
/// 超过这么久的帧算读图或卡住（不算进帧长）
const LONG_FRAME: Duration = Duration::from_secs(1);
const HITCH: Duration = Duration::from_millis(33);
const FREEZE: Duration = Duration::from_millis(100);
/// 最多列几个模块
const TOP: usize = 3;

// ------------------------------------------------------------------ dark_core 自己占的内存
/// 包一层系统分配器：分配 / 释放时加减计数（Relaxed 原子操作，几纳秒），别的照旧
struct Counting;

static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
static ALLOCS: AtomicU64 = AtomicU64::new(0);

#[inline]
fn grow(n: usize) {
    let now = LIVE.fetch_add(n, Ordering::Relaxed).wrapping_add(n);
    if now > PEAK.load(Ordering::Relaxed) {
        PEAK.fetch_max(now, Ordering::Relaxed);
    }
}

#[inline]
fn shrink(n: usize) {
    LIVE.fetch_sub(n, Ordering::Relaxed);
}

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            grow(l.size());
            ALLOCS.fetch_add(1, Ordering::Relaxed);
        }
        p
    }

    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            grow(l.size());
            ALLOCS.fetch_add(1, Ordering::Relaxed);
        }
        p
    }

    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) };
        shrink(l.size());
    }

    unsafe fn realloc(&self, p: *mut u8, l: Layout, new: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, new) };
        if !q.is_null() {
            if new >= l.size() {
                grow(new - l.size());
            } else {
                shrink(l.size() - new);
            }
            ALLOCS.fetch_add(1, Ordering::Relaxed);
        }
        q
    }
}

#[global_allocator]
static GLOBAL: Counting = Counting;

// ------------------------------------------------------------------ 帧里的累计
struct Acc {
    /// 正常的帧（不到 1 秒）
    frames: u32,
    total: Duration,
    max: Duration,
    hitch: u32,
    freeze: u32,
    /// 超过 1 秒的帧（读图或卡住）
    long: u32,
    long_max: Duration,
    /// 调了几次 frame()、其中帧开头在联机会话里的
    ticks: u32,
    coop_frames: u32,
    /// dark_core 每帧花的（各模块 tick 加起来）：已经结束的帧的合计、最长、帧数，当前这一帧的
    mine_total: Duration,
    mine_max: Duration,
    mine_frames: u32,
    mine_cur: Duration,
    mods: Vec<(&'static str, Duration)>,
}

const fn new_acc() -> Acc {
    Acc {
        frames: 0,
        total: Duration::ZERO,
        max: Duration::ZERO,
        hitch: 0,
        freeze: 0,
        long: 0,
        long_max: Duration::ZERO,
        ticks: 0,
        coop_frames: 0,
        mine_total: Duration::ZERO,
        mine_max: Duration::ZERO,
        mine_frames: 0,
        mine_cur: Duration::ZERO,
        mods: Vec::new(),
    }
}

impl Acc {
    /// 新的一帧开始：上一帧的帧长 dt（第一帧没有）、上一帧 dark_core 花的收尾
    fn frame(&mut self, dt: Option<Duration>, coop: bool) {
        if let Some(dt) = dt {
            if dt >= LONG_FRAME {
                self.long += 1;
                self.long_max = self.long_max.max(dt);
            } else {
                self.frames += 1;
                self.total += dt;
                self.max = self.max.max(dt);
                self.hitch += (dt >= HITCH) as u32;
                self.freeze += (dt >= FREEZE) as u32;
            }
            self.mine_total += self.mine_cur;
            self.mine_max = self.mine_max.max(self.mine_cur);
            self.mine_frames += 1;
        }
        self.mine_cur = Duration::ZERO;
        self.ticks += 1;
        self.coop_frames += coop as u32;
    }

    fn add(&mut self, name: &'static str, dt: Duration) {
        self.mine_cur += dt;
        match self.mods.iter_mut().find(|m| std::ptr::eq(m.0, name) || m.0 == name) {
            Some(m) => m.1 += dt,
            None => self.mods.push((name, dt)),
        }
    }
}

struct St {
    start: Option<Instant>,
    from: Option<Instant>,
    last: Option<Instant>,
    acc: Acc,
}

static ST: Mutex<St> = Mutex::new(St { start: None, from: None, last: None, acc: new_acc() });

fn with<R>(f: impl FnOnce(&mut St) -> R) -> R {
    f(&mut ST.lock().unwrap_or_else(|e| e.into_inner()))
}

/// 一个模块的 tick 花了这么久（lib.rs guarded，每个任务组的都算）
pub fn add(name: &'static str, dt: Duration) {
    with(|s| s.acc.add(name, dt));
}

/// 到点时主线程取的游戏状态
#[derive(Default)]
struct Game {
    coop: bool,
    host: bool,
    map: Option<String>,
    chrs: Option<usize>,
}

fn game_state() -> Game {
    let mut g = Game { coop: crate::coop::active(), host: crate::coop::host(), ..Game::default() };
    if let Ok(w) = unsafe { WorldChrMan::instance() } {
        if let Some(p) = w.main_player.as_ref() {
            g.map = Some(p.current_block_id.to_string());
            g.chrs = Some(live!(w).len());
        }
    }
    g
}

struct Sample {
    up: Duration,
    span: Duration,
    acc: Acc,
    game: Game,
}

/// 每帧开头调一次（FrameBegin 最前面）：记帧长，到 5 分钟了交给 dark_core_perf 线程写一行
pub fn frame() {
    let now = Instant::now();
    let coop = crate::coop::active();
    let due = with(|s| {
        let dt = s.last.map(|t| now - t);
        s.last = Some(now);
        s.acc.frame(dt, coop);
        let start = *s.start.get_or_insert(now);
        let from = *s.from.get_or_insert(now);
        (now - from >= EVERY).then(|| {
            s.from = Some(now);
            (std::mem::replace(&mut s.acc, new_acc()), now - start, now - from)
        })
    });
    if let Some((acc, up, span)) = due {
        send(Sample { up, span, acc, game: game_state() });
    }
}

fn send(s: Sample) {
    static TX: OnceLock<Option<Mutex<mpsc::Sender<Sample>>>> = OnceLock::new();
    let tx = TX.get_or_init(|| {
        let (tx, rx) = mpsc::channel::<Sample>();
        std::thread::Builder::new()
            .name("dark_core_perf".into())
            .spawn(move || {
                for s in rx {
                    write(s);
                }
            })
            .ok()
            .map(|_| Mutex::new(tx))
    });
    match tx {
        Some(tx) => {
            let _ = tx.lock().unwrap_or_else(|e| e.into_inner()).send(s);
        }
        None => write(s),
    }
}

// ------------------------------------------------------------------ 进程、系统、显存
#[repr(C)]
#[derive(Default)]
struct MemCounters {
    cb: u32,
    page_faults: u32,
    peak_working_set: usize,
    working_set: usize,
    quota_peak_paged: usize,
    quota_paged: usize,
    quota_peak_nonpaged: usize,
    quota_nonpaged: usize,
    pagefile: usize,
    peak_pagefile: usize,
    private: usize,
}

#[repr(C)]
#[derive(Default)]
struct MemStatus {
    len: u32,
    load: u32,
    total_phys: u64,
    avail_phys: u64,
    total_page: u64,
    avail_page: u64,
    total_virtual: u64,
    avail_virtual: u64,
    avail_ext: u64,
}

#[repr(C)]
#[derive(Default)]
struct ThreadEntry {
    size: u32,
    usage: u32,
    thread_id: u32,
    owner_pid: u32,
    base_pri: i32,
    delta_pri: i32,
    flags: u32,
}

/// 当前进程的伪句柄（GetCurrentProcess 的返回值，不用关）
const ME: isize = -1;
const INVALID: isize = -1;
const SNAPTHREAD: u32 = 4;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn K32GetProcessMemoryInfo(h: isize, c: *mut MemCounters, cb: u32) -> i32;
    fn GetProcessHandleCount(h: isize, n: *mut u32) -> i32;
    fn GlobalMemoryStatusEx(s: *mut MemStatus) -> i32;
    fn CreateToolhelp32Snapshot(flags: u32, pid: u32) -> isize;
    fn Thread32First(h: isize, e: *mut ThreadEntry) -> i32;
    fn Thread32Next(h: isize, e: *mut ThreadEntry) -> i32;
    fn CloseHandle(h: isize) -> i32;
}

#[derive(Default)]
struct Sys {
    /// 提交的私有内存、工作集（字节）
    private: Option<(u64, u64)>,
    /// 系统可用 / 总物理内存（字节）
    phys: Option<(u64, u64)>,
    handles: Option<u32>,
    threads: Option<u32>,
    gpu: Option<Gpu>,
    /// dark_core 自己：还占着、这段最多、这段分配次数
    live: u64,
    peak: u64,
    allocs: u64,
}

#[derive(Clone, Copy, Default)]
struct Gpu {
    used: u64,
    budget: u64,
    shared: u64,
}

fn proc_mem() -> Option<(u64, u64)> {
    let mut c = MemCounters { cb: size_of::<MemCounters>() as u32, ..MemCounters::default() };
    (unsafe { K32GetProcessMemoryInfo(ME, &mut c, c.cb) } != 0).then_some((c.private as u64, c.working_set as u64))
}

fn phys_mem() -> Option<(u64, u64)> {
    let mut s = MemStatus { len: size_of::<MemStatus>() as u32, ..MemStatus::default() };
    (unsafe { GlobalMemoryStatusEx(&mut s) } != 0).then_some((s.avail_phys, s.total_phys))
}

fn handles() -> Option<u32> {
    let mut n = 0u32;
    (unsafe { GetProcessHandleCount(ME, &mut n) } != 0).then_some(n)
}

fn threads() -> Option<u32> {
    let snap = unsafe { CreateToolhelp32Snapshot(SNAPTHREAD, 0) };
    if snap == INVALID || snap == 0 {
        return None;
    }
    let pid = std::process::id();
    let mut n = 0u32;
    let mut e = ThreadEntry { size: size_of::<ThreadEntry>() as u32, ..ThreadEntry::default() };
    let mut ok = unsafe { Thread32First(snap, &mut e) } != 0;
    while ok {
        n += (e.owner_pid == pid) as u32;
        e.size = size_of::<ThreadEntry>() as u32;
        ok = unsafe { Thread32Next(snap, &mut e) } != 0;
    }
    unsafe { CloseHandle(snap) };
    (n > 0).then_some(n)
}

/// 本进程的显存：各块显卡里用得最多的那块（笔记本独显 + 核显时，游戏在独显上）
fn gpu() -> Option<Gpu> {
    use windows::Win32::Graphics::Dxgi::*;
    use windows::core::Interface;
    let f: IDXGIFactory1 = unsafe { CreateDXGIFactory1() }.ok()?;
    let mut best: Option<Gpu> = None;
    for i in 0..8 {
        let Ok(a) = (unsafe { f.EnumAdapters1(i) }) else { break };
        let Ok(desc) = (unsafe { a.GetDesc1() }) else { continue };
        if desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32 != 0 {
            continue;
        }
        let Ok(a3) = a.cast::<IDXGIAdapter3>() else { continue };
        let mut local = DXGI_QUERY_VIDEO_MEMORY_INFO::default();
        if unsafe { a3.QueryVideoMemoryInfo(0, DXGI_MEMORY_SEGMENT_GROUP_LOCAL, &mut local) }.is_err() {
            continue;
        }
        let mut shared = DXGI_QUERY_VIDEO_MEMORY_INFO::default();
        let _ = unsafe { a3.QueryVideoMemoryInfo(0, DXGI_MEMORY_SEGMENT_GROUP_NON_LOCAL, &mut shared) };
        let g = Gpu { used: local.CurrentUsage, budget: local.Budget, shared: shared.CurrentUsage };
        if best.is_none_or(|b| g.used + g.shared > b.used + b.shared) {
            best = Some(g);
        }
    }
    best
}

fn sys() -> Sys {
    let live = LIVE.load(Ordering::Relaxed);
    let peak = PEAK.swap(live, Ordering::Relaxed).max(live);
    Sys {
        private: proc_mem(),
        phys: phys_mem(),
        handles: handles(),
        threads: threads(),
        gpu: std::panic::catch_unwind(gpu).ok().flatten(),
        live: live as u64,
        peak: peak as u64,
        allocs: ALLOCS.swap(0, Ordering::Relaxed),
    }
}

fn write(s: Sample) {
    let sys = sys();
    log(&render(&s, &sys));
}

// ------------------------------------------------------------------ 写成一行
fn gb(b: u64) -> String {
    format!("{:.2} GB", b as f64 / (1u64 << 30) as f64)
}

fn mb(b: u64) -> String {
    format!("{:.1} MB", b as f64 / (1u64 << 20) as f64)
}

fn ms(d: Duration) -> f64 {
    d.as_secs_f64() * 1000.0
}

/// 次数：上万的写「x.x 万次」
fn count(n: u64) -> String {
    if n >= 10_000 { format!("{:.1} 万次", n as f64 / 10_000.0) } else { format!("{n} 次") }
}

fn render(s: &Sample, y: &Sys) -> String {
    let a = &s.acc;
    let mut o = String::new();
    let up = s.up.as_secs() / 60;
    let _ = write!(o, "性能记录（已运行 {}，这段 {} 分钟）：", if up >= 60 { format!("{} 小时 {} 分", up / 60, up % 60) } else { format!("{up} 分") },
                   (s.span.as_secs() + 30) / 60);
    if s.game.coop || a.coop_frames > 0 {
        let _ = write!(o, "{}（这段里 {}% 的时间在联机）", if !s.game.coop { "已不在联机" } else if s.game.host { "联机中，房主" } else { "联机中，客机" },
                       a.coop_frames as u64 * 100 / a.ticks.max(1) as u64);
    } else {
        o.push_str("单机");
    }
    match (&s.game.map, s.game.chrs) {
        (Some(m), Some(n)) => {
            let _ = write!(o, "；地图 {m}，在场角色 {n}");
        }
        _ => o.push_str("；不在地图里"),
    }
    o.push_str("；游戏内存 ");
    match y.private {
        Some((p, w)) => {
            let _ = write!(o, "{}（工作集 {}）", gb(p), gb(w));
        }
        None => o.push_str("读不到"),
    }
    if let Some((av, tot)) = y.phys {
        let _ = write!(o, "，系统可用 {} / {}", gb(av), gb(tot));
    }
    match y.gpu {
        Some(g) => {
            let _ = write!(o, "；显存 {} / 预算 {}，共享 {}", gb(g.used), gb(g.budget), gb(g.shared));
        }
        None => o.push_str("；显存读不到"),
    }
    let opt = |v: Option<u32>| v.map_or("读不到".to_string(), |n| n.to_string());
    let _ = write!(o, "；句柄 {}，线程 {}", opt(y.handles), opt(y.threads));
    let _ = write!(o, "；dark_core 自己 {}（这段最多 {}，分配 {}）", mb(y.live), mb(y.peak), count(y.allocs));
    if a.frames > 0 {
        let avg = ms(a.total) / a.frames as f64;
        let _ = write!(o, "；帧：平均 {avg:.1} 毫秒（{:.0} 帧/秒），最长 {:.0} 毫秒，超过 33 毫秒 {} 帧、超过 100 毫秒 {} 帧（共 {} 帧）",
                       if avg > 0.0 { 1000.0 / avg } else { 0.0 }, ms(a.max), a.hitch, a.freeze, a.frames);
    } else {
        o.push_str("；没有正常的帧");
    }
    if a.long > 0 {
        let _ = write!(o, "，超过 1 秒（读图或卡住）{} 次、最长 {:.1} 秒", a.long, a.long_max.as_secs_f64());
    }
    let mf = a.mine_frames.max(1) as f64;
    let _ = write!(o, "；dark_core 每帧平均 {:.2} 毫秒、最长 {:.1} 毫秒", ms(a.mine_total) / mf, ms(a.mine_max));
    let mut mods: Vec<&(&str, Duration)> = a.mods.iter().collect();
    mods.sort_by(|x, z| z.1.cmp(&x.1));
    if !mods.is_empty() {
        let top: Vec<String> = mods.iter().take(TOP).map(|(n, d)| format!("{n} {:.2}", ms(*d) / mf)).collect();
        let _ = write!(o, "，最多的：{}", top.join("、"));
    }
    o
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 帧长分档（超过 1 秒的单独数）、dark_core 每帧合计在下一帧开头收尾、联机帧数、模块按名字合并
    #[test]
    fn acc_frames_and_mods() {
        let m = Duration::from_millis;
        let mut a = new_acc();
        a.frame(None, false);
        a.add("积木引擎", m(2));
        a.add("新装备系统", m(1));
        a.frame(Some(m(16)), true);
        a.add("积木引擎", m(5));
        a.frame(Some(m(40)), true);
        a.frame(Some(m(150)), false);
        a.frame(Some(Duration::from_secs(3)), false);
        assert_eq!((a.frames, a.hitch, a.freeze, a.long), (3, 2, 1, 1));
        assert_eq!((a.total, a.max, a.long_max), (m(206), m(150), Duration::from_secs(3)));
        assert_eq!(a.coop_frames, 2);
        assert_eq!((a.mine_total, a.mine_max, a.mine_frames), (m(8), m(5), 4));
        assert_eq!(a.mods, vec![("积木引擎", m(7)), ("新装备系统", m(1))]);
    }

    /// 写出来的一行：运行时间、联机、地图、内存、显存、帧、模块
    #[test]
    fn render_line() {
        let m = Duration::from_millis;
        let mut a = new_acc();
        a.frame(None, true);
        a.add("积木引擎", m(3));
        a.add("联机通道", m(1));
        a.frame(Some(m(20)), true);
        a.frame(Some(m(120)), false);
        a.frame(Some(Duration::from_secs(2)), true);
        let s = Sample { up: Duration::from_secs(85 * 60 + 10), span: Duration::from_secs(300), acc: a,
                         game: Game { coop: true, host: false, map: Some("m60_43_36_00".into()), chrs: Some(152) } };
        let y = Sys { private: Some((5 << 30, 4 << 30)), phys: Some((3 << 30, 16 << 30)), handles: Some(3120), threads: Some(96),
                      gpu: Some(Gpu { used: 4 << 30, budget: 6 << 30, shared: 1 << 29 }), live: 8 << 20, peak: 9 << 20, allocs: 523_000 };
        let t = render(&s, &y);
        for want in ["性能记录（已运行 1 小时 25 分，这段 5 分钟）：联机中，客机（这段里 75% 的时间在联机）", "；地图 m60_43_36_00，在场角色 152",
                     "；游戏内存 5.00 GB（工作集 4.00 GB），系统可用 3.00 GB / 16.00 GB", "；显存 4.00 GB / 预算 6.00 GB，共享 0.50 GB",
                     "；句柄 3120，线程 96", "；dark_core 自己 8.0 MB（这段最多 9.0 MB，分配 52.3 万次）",
                     "；帧：平均 70.0 毫秒（14 帧/秒），最长 120 毫秒，超过 33 毫秒 1 帧、超过 100 毫秒 1 帧（共 2 帧），超过 1 秒（读图或卡住）1 次、最长 2.0 秒",
                     "；dark_core 每帧平均 1.33 毫秒、最长 4.0 毫秒，最多的：积木引擎 1.00、联机通道 0.33"] {
            assert!(t.contains(want), "缺「{want}」：{t}");
        }
        let s = Sample { up: Duration::from_secs(600), span: Duration::from_secs(300), acc: new_acc(), game: Game::default() };
        let t = render(&s, &Sys::default());
        assert!(t.starts_with("性能记录（已运行 10 分，这段 5 分钟）：单机；不在地图里；游戏内存 读不到；显存读不到；句柄 读不到，线程 读不到"), "{t}");
    }

    /// 分配器计数：分配一大块，还占着的涨上去，放掉落回来（别的测试同时在跑，留余量）
    #[test]
    fn counting_allocator() {
        const BIG: usize = 64 << 20;
        let before = LIVE.load(Ordering::Relaxed);
        let v = vec![1u8; BIG];
        let during = LIVE.load(Ordering::Relaxed);
        assert!(during >= before + BIG - (8 << 20), "{before} → {during}");
        assert!(PEAK.load(Ordering::Relaxed) >= during - (8 << 20));
        drop(v);
        let after = LIVE.load(Ordering::Relaxed);
        assert!(after + BIG - (8 << 20) <= during, "{during} → {after}");
    }

    /// 本机上真查一次：进程内存、句柄、线程都读得到（显存看机器，读不到也不算错）
    #[test]
    fn real_queries() {
        let y = sys();
        let (p, w) = y.private.expect("进程内存");
        assert!(p > 0 && w > 0);
        let (av, tot) = y.phys.expect("系统内存");
        assert!(av > 0 && tot >= av);
        assert!(y.handles.unwrap() > 0);
        assert!(y.threads.unwrap() >= 1);
        if let Some(g) = y.gpu {
            assert!(g.budget > 0 || g.used == 0);
        }
        eprintln!("{}", render(&Sample { up: Duration::from_secs(60), span: Duration::from_secs(60), acc: new_acc(), game: Game::default() }, &y));
    }
}
