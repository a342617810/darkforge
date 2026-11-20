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
//! 在场 = ChrSet 条目的状态字节读到过 2 或 4 的角色（崩溃风险审查 2026-11-19 第 20 条：以前全收，没建好 / 没读进来 / 正在拆的也照样解引用、挂效果、改血量）。
//! - 第一版只收 vendored 枚举的 Active（2）：同日 18:18 实测稳定在场的主角一直是 4、从来不是 2，前 90 秒周围角色全空（斗技场第一波精英没魇化）。
//!   黄金树爬塔（1.17.1）把 2 | 4（Active / ReadyForActivation）当在场，没唤醒 / 被停读的地图敌人是 0。
//! - 第二版只排除 1 和 5，0 照算：19:43 斗技场 98 只里 41 只一直是 0（没读进来、玩家看不到），魇化照样给其中一只挂了效果、读了血量。
//!   现在 0 / 1 / 3 只有以前读到过 2 / 4 的才算（停读的照算，SEEN：不让 speed.rs / rules 丢掉要改回的记录）；5 不算、忘掉。
//!   联机：客机收到房主的魇化会等 120 秒等它出现；房主替客机减速每帧重新套；替客机改架势是一次性的，对方在房主这边没读进来就不改。
//! - 主角读到 2 或 4（确认这个字节就是状态）以前全收，不等、不会一开始全空；读到大于 5 的值就当不是状态，之后一直全收。
//! - status_diag 照样记实测的值（「周围角色（实测）」），以后要改规则先看它。

use std::collections::{BTreeMap, HashSet};
use std::ffi::c_void;
use std::ptr::NonNull;
use std::sync::atomic::{AtomicU8, AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::{ChrIns, ChrSet, ChrSetEntry, PlayerIns, WorldChrMan};
use fromsoftware_shared::{FromStatic, OwnedPtr, Subclass};
use windows::Win32::System::Diagnostics::Debug::ReadProcessMemory;
use windows::Win32::System::Threading::GetCurrentProcess;

use crate::log;

/// 在场角色的地址（玩家、灵体、召唤、调试、开放地图、各地图块的 ChrSet；正在建 / 正在拆的不算，见文件开头）
macro_rules! live {
    ($w:expr) => {
        $crate::chrs::collect_live(
            &$w.player_chr_set,
            [&$w.ghost_chr_set, &$w.summon_buddy_chr_set, &$w.debug_chr_set, &$w.open_field_chr_set.base],
            &$w.chr_sets,
        )
        .1
    };
}

/// 周围的角色（游戏算的距离，由近到远），距离列表还没就绪时是 None；$me = 主角 ChrIns 的地址（换了就重新等）。
/// 列表按所有非空条目核对，给出去的不含正在建 / 正在拆的
macro_rules! around {
    ($w:expr, $me:expr) => {{
        let t0 = $crate::prof::on().then(std::time::Instant::now);
        let (all, live) = $crate::chrs::collect_live(
            &$w.player_chr_set,
            [&$w.ghost_chr_set, &$w.summon_buddy_chr_set, &$w.debug_chr_set, &$w.open_field_chr_set.base],
            &$w.chr_sets,
        );
        let r = $crate::chrs::around(&$w.chr_inses_by_distance, all, &live, $me);
        if let Some(t0) = t0 {
            $crate::prof::around_done(t0.elapsed(), r.as_ref().map_or(0, |v| v.len()));
        }
        r
    }};
}

fn add<T: Subclass<ChrIns> + 'static>(out: &mut HashSet<usize>, s: &ChrSet<T>) {
    out.extend(s.characters().map(|c| c as *mut T as usize));
}

/// ChrSet 里所有非空条目（不看状态）：斗技场生成器要看还没生成的部件（arena.rs）；状态字节还没确认时 live! 也用它
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

/// 条目里状态字节的位置、条目长度（vendored 定义；两个游戏版本 ChrSet 的虚函数逐条一样：容量 +0x10、条目表 +0x18、每条 0x10 字节）
const STATUS_AT: usize = std::mem::offset_of!(ChrSetEntry<ChrIns>, chr_load_status);
const ENTRY_SIZE: usize = size_of::<ChrSetEntry<ChrIns>>();

/// 逐条看 ChrSet：（角色地址, 状态字节）。状态按字节读（值的意思还没定，不能当枚举用）
fn scan<T: Subclass<ChrIns> + 'static>(s: &ChrSet<T>, f: &mut impl FnMut(usize, u8)) {
    let base = s.entries.as_ptr() as *const u8;
    for i in 0..s.capacity as usize {
        let e = unsafe { base.add(i * ENTRY_SIZE) };
        let chr = unsafe { (e as *const usize).read() };
        if chr != 0 {
            f(chr, unsafe { e.add(STATUS_AT).read() });
        }
    }
}

/// 状态字节：在场（vendored 枚举 Active / ReadyForActivation；实测主角是 4）、正在拆（Unloading），比 STATUS_MAX 大就不是状态
const ACTIVE: u8 = 2;
const READY_ACT: u8 = 4;
const TEARING: u8 = 5;
const STATUS_MAX: u8 = 5;
/// 0 还没确认（主角还没读到 2 / 4，先全收）、1 确认了、2 读到不认识的值（这个字节不是状态）→ 一直全收
static STATUS_LAYOUT: AtomicU8 = AtomicU8::new(0);
/// 读到过 2 / 4 的角色地址：之后变成 0（停读）/ 1 / 3 也照样算在场；正在拆或者离开 ChrSet 就忘掉
static SEEN: Mutex<Option<HashSet<usize>>> = Mutex::new(None);

/// 状态字节读到不认识的值：之后不看状态（只记一次）
fn status_bad(why: &str) {
    if STATUS_LAYOUT.swap(2, Ordering::Relaxed) != 2 {
        log(&format!("周围角色：ChrSet 条目的状态字节对不上（{why}），之后不看状态、所有非空条目都算在场（同以前）"));
    }
}

/// （所有非空条目, 其中在场的，见 pick）。状态字节还没确认或者对不上时两份一样
pub fn collect_live(players: &ChrSet<PlayerIns>, fixed: [&ChrSet<ChrIns>; 4], sets: &[Option<OwnedPtr<ChrSet<ChrIns>>>]) -> (HashSet<usize>, HashSet<usize>) {
    if STATUS_LAYOUT.load(Ordering::Relaxed) != 1 {
        let all = collect(players, fixed, sets);
        return (all.clone(), all);
    }
    let mut entries = Vec::new();
    let mut f = |a: usize, st: u8| entries.push((a, st));
    scan(players, &mut f);
    for s in fixed {
        scan(s, &mut f);
    }
    for s in sets.iter().flatten() {
        scan(s, &mut f);
    }
    let all: HashSet<usize> = entries.iter().map(|e| e.0).collect();
    let mut g = SEEN.lock().unwrap_or_else(|e| e.into_inner());
    match pick(&entries, g.get_or_insert_with(HashSet::new)) {
        Ok(live) => (all, live),
        Err((a, st)) => {
            drop(g);
            status_bad(&format!("角色 {a:#x} 的状态是 {st}"));
            (all.clone(), all)
        }
    }
}

/// 按状态字节挑在场的：2 / 4 算；0 / 1 / 3 只算以前读到过 2 / 4 的（seen 跟着更新）；5 不算、忘掉；
/// 读到比 STATUS_MAX 大的值 = Err（不是状态）
fn pick(entries: &[(usize, u8)], seen: &mut HashSet<usize>) -> Result<HashSet<usize>, (usize, u8)> {
    if let Some(&odd) = entries.iter().find(|e| e.1 > STATUS_MAX) {
        return Err(odd);
    }
    let mut live: HashSet<usize> = entries.iter().filter(|e| e.1 == ACTIVE || e.1 == READY_ACT).map(|e| e.0).collect();
    let other: HashSet<usize> = entries.iter().filter(|e| e.1 != ACTIVE && e.1 != READY_ACT && e.1 != TEARING).map(|e| e.0).collect();
    // 正在拆的、不在 ChrSet 里的忘掉
    seen.retain(|a| live.contains(a) || other.contains(a));
    live.extend(other.iter().copied().filter(|a| seen.contains(a)));
    seen.extend(live.iter().copied());
    Ok(live)
}

/// 每帧（refresh_players）：主角读到 2 或 4 就确认这个字节是状态，开始排除正在建 / 正在拆的；读到不认识的值就一直全收
fn status_watch(w: &WorldChrMan) {
    if STATUS_LAYOUT.load(Ordering::Relaxed) != 0 {
        return;
    }
    let Some(me) = w.main_player.as_ref().map(|p| p.as_ptr() as usize) else { return };
    let mut main = None;
    scan(&w.player_chr_set, &mut |a, st| {
        if a == me {
            main = Some(st);
        }
    });
    match main {
        Some(st @ (ACTIVE | READY_ACT)) => {
            if STATUS_LAYOUT.compare_exchange(0, 1, Ordering::Relaxed, Ordering::Relaxed).is_ok() {
                log(&format!("周围角色：ChrSet 条目的状态字节对上了（主角是 {st}），之后只有读到过 2 / 4 的角色算在场（正在拆的 5 不算）"));
            }
        }
        Some(st) if st > STATUS_MAX => status_bad(&format!("主角的状态是 {st}")),
        _ => {}
    }
}

/// 状态字节实测（只记日志，不影响谁算在场）：每秒最多看一次；主角的值、玩家和其他角色各出现过哪些值，有变化才记一行，最多 STATUS_DIAG_MAX 行
struct StatusDiag {
    last: Option<Instant>,
    key: Option<(Option<u8>, Vec<u8>, Vec<u8>)>,
    lines: u32,
}

static STATUS_DIAG: Mutex<StatusDiag> = Mutex::new(StatusDiag { last: None, key: None, lines: 0 });
const STATUS_DIAG_MAX: u32 = 40;

fn status_diag(w: &WorldChrMan) {
    let now = Instant::now();
    let mut g = STATUS_DIAG.lock().unwrap_or_else(|e| e.into_inner());
    if g.lines >= STATUS_DIAG_MAX || g.last.is_some_and(|t| now - t < Duration::from_secs(1)) {
        return;
    }
    g.last = Some(now);
    let me = w.main_player.as_ref().map_or(0, |p| p.as_ptr() as usize);
    let mut main = None;
    let mut players: BTreeMap<u8, usize> = BTreeMap::new();
    let mut others: BTreeMap<u8, usize> = BTreeMap::new();
    scan(&w.player_chr_set, &mut |a, st| {
        if a == me {
            main = Some(st);
        }
        *players.entry(st).or_default() += 1;
    });
    let mut count = |_: usize, st: u8| *others.entry(st).or_default() += 1;
    for s in [&w.ghost_chr_set, &w.summon_buddy_chr_set, &w.debug_chr_set, &w.open_field_chr_set.base] {
        scan(s, &mut count);
    }
    for s in w.chr_sets.iter().flatten() {
        scan(s, &mut count);
    }
    let key = (main, players.keys().copied().collect::<Vec<_>>(), others.keys().copied().collect::<Vec<_>>());
    if g.key.as_ref() == Some(&key) {
        return;
    }
    g.key = Some(key);
    g.lines += 1;
    let fmt = |m: &BTreeMap<u8, usize>| m.iter().map(|(v, n)| format!("{v}×{n}")).collect::<Vec<_>>().join(" ");
    log(&format!(
        "周围角色（实测）：ChrSet 条目的状态字节：主角 {}；玩家 [{}]；其他角色 [{}]（值×个数；出现的值变了才记，最多 {STATUS_DIAG_MAX} 行{}）",
        main.map_or("不在".to_string(), |v| v.to_string()),
        fmt(&players),
        fmt(&others),
        if g.lines == STATUS_DIAG_MAX { "，后面不再记" } else { "" }
    ));
}

/// 玩家角色（本机主角、联机的队友、入侵者：都在 WorldChrMan 的 player_chr_set 里）的地址，每帧开头刷新一次（lib.rs）。
/// 「找敌人」的地方用 rules::is_foe 跳过它们：玩家角色永远不算敌人（联机计划 13.2 G8，单机也一样）。以前只按阵营号排除友方，
/// 入侵的真人玩家会被当成敌人（扣血档、猎印、改架势、减速），时隙还会改队友的速度
static PLAYERS: Mutex<Vec<usize>> = Mutex::new(Vec::new());

pub fn refresh_players() {
    let mut v = Vec::new();
    if let Ok(wcm) = unsafe { WorldChrMan::instance() } {
        v.extend(wcm.player_chr_set.characters().map(|c| c as *mut PlayerIns as usize));
        status_watch(wcm);
        status_diag(wcm);
    }
    *PLAYERS.lock().unwrap_or_else(|e| e.into_inner()) = v;
}

// ------------------------------------------------------------------ 人物结构自检（崩溃风险审查第 22 条）
/// 唤声船、难度屏障、碾压 / 飞鸿 / 见切的无敌直接写主角的物理、坠落、动作标记模块。这些偏移按 2.7.1.0 写，2.7.2.0 上用
/// 两个 exe 的机器码静态比对过（同样的代码、同样的位移），但不按版本号分；照 dark_wings 的做法第一次要写之前核对一次：
/// 各模块的「所属角色」都指回主角、几个布尔字节是 0 / 1、位置朝向血量在合理范围。
/// 0 还没核对过、1 通过、2 对不上（这次进游戏这几处都不写）
static PLAYER_LAYOUT: AtomicU8 = AtomicU8::new(0);
/// 一直核对不出来（数值不合理，可能还在读图）多久写一行日志
const LAYOUT_SLOW: Duration = Duration::from_secs(60);
static LAYOUT_WAIT: Mutex<(Option<Instant>, bool)> = Mutex::new((None, false));

/// Ok(true) 通过、Ok(false) 还看不出来（模块还没建好 / 数值还不正常，下次再看）、Err 对不上
fn check_player(p: &PlayerIns) -> Result<bool, String> {
    let me = &p.chr_ins as *const ChrIns as usize;
    if p.chr_ins.modules.as_ptr().is_null() {
        return Ok(false);
    }
    let m = &p.chr_ins.modules;
    let mods: [(&str, usize); 6] = [
        ("物理", m.physics.as_ptr() as usize),
        ("行为", m.behavior.as_ptr() as usize),
        ("坠落", m.fall.as_ptr() as usize),
        ("数据", m.data.as_ptr() as usize),
        ("动作标记", m.action_flag.as_ptr() as usize),
        ("骑乘", m.ride.as_ptr() as usize),
    ];
    if mods.iter().any(|x| x.1 == 0) {
        return Ok(false);
    }
    for (n, o) in [
        ("物理", m.physics.owner.as_ptr() as usize),
        ("行为", m.behavior.owner.as_ptr() as usize),
        ("坠落", m.fall.owner.as_ptr() as usize),
        ("数据", m.data.owner.as_ptr() as usize),
        ("动作标记", m.action_flag.owner.as_ptr() as usize),
        ("骑乘", m.ride.owner.as_ptr() as usize),
    ] {
        if o == 0 {
            return Ok(false);
        }
        if o != me {
            return Err(format!("{n}模块的所属角色对不上（{o:#x} / {me:#x}）"));
        }
    }
    // 布尔字段按字节读（不经过 bool）：不是 0 / 1 就是位置错了
    let byte = |p: *const bool| unsafe { (p as *const u8).read() };
    let ph = &m.physics;
    for (n, b) in [
        ("重力开关", byte(&raw const ph.gravity_disabled)),
        ("角色代理重放", byte(&raw const ph.chr_proxy_pos_update_requested)),
        ("按世界竖直扶正", byte(&raw const ph.use_world_y_alignment_logic)),
        ("骑着灵马", byte(&raw const m.ride.is_mounted)),
    ] {
        if b > 1 {
            return Err(format!("{n}读到 {b}（应该是 0 / 1）"));
        }
    }
    let pos = &ph.position;
    let q = &ph.orientation;
    let qn = q.0 * q.0 + q.1 * q.1 + q.2 * q.2 + q.3 * q.3;
    let d = &m.data;
    let fine = [pos.0, pos.1, pos.2].iter().all(|x| x.is_finite() && x.abs() < 1e5)
        && qn.is_finite()
        && (0.8..1.2).contains(&qn)
        && (1..=1_000_000).contains(&d.max_hp)
        && (0..=1_000_000).contains(&d.hp)
        && (0..=1_000_000).contains(&d.fp)
        && m.fall.fall_timer.is_finite();
    if !fine {
        let mut w = LAYOUT_WAIT.lock().unwrap_or_else(|e| e.into_inner());
        let t = *w.0.get_or_insert_with(Instant::now);
        if !w.1 && t.elapsed() >= LAYOUT_SLOW {
            w.1 = true;
            log(&format!("人物结构自检：{} 秒还核对不出来（位置 {:.1},{:.1},{:.1}，朝向长度 {qn:.3}，血 {} / {}，蓝 {}），这几处先不写",
                         LAYOUT_SLOW.as_secs(), pos.0, pos.1, pos.2, d.hp, d.max_hp, d.fp));
        }
        return Ok(false);
    }
    Ok(true)
}

/// 主角的结构能不能写（第一次核对通过后一直是 true；对不上一直是 false）
pub fn player_layout_ok(p: &PlayerIns) -> bool {
    match PLAYER_LAYOUT.load(Ordering::Relaxed) {
        1 => return true,
        2 => return false,
        _ => {}
    }
    match check_player(p) {
        Ok(true) => {
            PLAYER_LAYOUT.store(1, Ordering::Relaxed);
            log("人物结构自检通过（物理、行为、坠落、数据、动作标记、骑乘模块）");
            true
        }
        Ok(false) => false,
        Err(e) => {
            PLAYER_LAYOUT.store(2, Ordering::Relaxed);
            log(&format!("人物结构自检没通过（游戏版本的结构变了？）：{e}；这次进游戏唤声船、难度屏障推回、碾压 / 飞鸿 / 见切的无敌都不改人物"));
            false
        }
    }
}

/// 别的角色（灵马）的物理模块指回它自己才写
pub fn chr_physics_ok(c: &ChrIns) -> bool {
    let me = c as *const ChrIns as usize;
    !c.modules.as_ptr().is_null() && !c.modules.physics.as_ptr().is_null() && c.modules.physics.owner.as_ptr() as usize == me
}

/// 别的角色（灵马）的动作标记模块指回它自己才写
pub fn chr_action_flag_ok(c: &ChrIns) -> bool {
    let me = c as *const ChrIns as usize;
    !c.modules.as_ptr().is_null() && !c.modules.action_flag.as_ptr().is_null() && c.modules.action_flag.owner.as_ptr() as usize == me
}

/// 这个角色是不是玩家角色（PlayerIns 的第一个字段就是 ChrIns，地址一样）
pub fn is_player(c: &ChrIns) -> bool {
    let a = c as *const ChrIns as usize;
    PLAYERS.lock().unwrap_or_else(|e| e.into_inner()).contains(&a)
}

/// 按实体编号（MSB 里的，两台电脑一样）找在场的角色；0 不找（临时生成的角色没有编号，两边对不上）
pub fn find_entity(id: u32) -> Option<NonNull<ChrIns>> {
    if id == 0 {
        return None;
    }
    let w = unsafe { WorldChrMan::instance() }.ok()?;
    live!(w).into_iter().map(|a| a as *mut ChrIns).find(|&p| unsafe { (*p).event_entity_id } == id).and_then(NonNull::new)
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

/// live = 所有非空条目（核对列表用），keep = 其中在场的（给出去的只有这些）
pub fn around<T>(list: &T, live: HashSet<usize>, keep: &HashSet<usize>, me: usize) -> Option<Vec<Near>> {
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
            Some(items.into_iter().filter(|(a, _)| keep.contains(a)).filter_map(|(a, distance)| Some(Near { chr_ins: NonNull::new(a as *mut ChrIns)?, distance })).collect())
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

    /// 条目的布局（两个 exe 的 ChrSet 虚函数里核对过：条目 0x10 字节，状态字节在 +8）
    #[test]
    fn entry_layout() {
        assert_eq!((STATUS_AT, ENTRY_SIZE), (8, 16));
    }

    /// 2 / 4 算在场（实测主角是 4）；0（没读进来 / 没唤醒）、1、3 只算以前读到过 2 / 4 的；5 不算；不认识的值 = 不是状态
    #[test]
    fn pick_by_status() {
        let mut seen = HashSet::new();
        let live = pick(&[(10, 4), (11, 2), (12, 0), (13, 3), (14, 1), (15, 5)], &mut seen).unwrap();
        assert_eq!(live, [10, 11].into_iter().collect());
        // 10 停读了（0）、11 变成 1：读到过 4 / 2，照样算；12 一直是 0（斗技场没读进来的那种），不算；15 拆完不在了
        let live = pick(&[(10, 0), (11, 1), (12, 0), (13, 3)], &mut seen).unwrap();
        assert_eq!(live, [10, 11].into_iter().collect());
        // 12 唤醒了（4），之后再停读也算
        pick(&[(12, 4)], &mut seen).unwrap();
        assert_eq!(pick(&[(12, 0)], &mut seen).unwrap(), [12].into_iter().collect());
        // 12 开始拆：不算、忘掉；同一个地址后来又是 0 / 1：不再当读到过
        assert!(pick(&[(12, 5)], &mut seen).unwrap().is_empty());
        assert!(!seen.contains(&12));
        assert!(pick(&[(12, 1)], &mut seen).unwrap().is_empty());
        assert_eq!(pick(&[(10, 4), (16, 9)], &mut seen), Err((16, 9)));
    }
}
