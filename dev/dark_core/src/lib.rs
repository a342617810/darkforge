//! Dark Reforged 杂项（dark_core）：零碎的小改动都放这里，一个功能一个模块，每帧由 FrameBegin 任务挨个调用。
//!   - festive：庆典油脂——卢恩越多伤害越高、每秒扣当前卢恩（参数侧在重随的 rr/festive.py）
//!   - gear：新装备系统——赐福「一键鉴定」按词条库生成装备、改写容器、发货、记录（参数侧在 rr/containers.py、rr/unidentified.py、rr/affixes.py）
//!   - scaling：武器补正显示具体数值（启动时改一次代码，不用每帧）
//!   - runtime：新词条里要 DLL 做的（优雅：姿势叠伤害；鸡尾酒：定时随机增益），按装备上的标记效果
//!   - rules：积木引擎，积木词条照 runtime.txt 的规则做（叠层、事件触发、条件效果）
//!   - boat：战灰「唤声船」——骑船、瞬移、下船，击败唤声船发碎片 / 战灰（参数侧在 rr/mariner.py；物理更新前跑）
//!   - procs：触发词条的属性补正——按人物属性改词条专用的攻击行 / 治疗效果，法球、引爆的倍率（参数侧在 rr/procs.py）
//!   - skillmult：战技伤害按放战技那把生成武器的稀有度乘倍率（参数侧在 rr/affixes.py skill_mults）
//!   - hpunify：高难度血量补正——「死亡」「不可能」里给在场的敌人挂最大血量倍率（参数侧在 rr/hpunify.py）
//!   - curses：咒痕（原名七咒）——「死亡」「不可能」里七道咒痕，区域 Boss 首杀给碎片、凑满反转成祝福（参数侧在 rr/curses.py）
//!   - notes：原版闪烁提示——魇火、魇印、咒痕碎片的提示排队写进标记，公共事件显示（参数侧在 rr/notes.py、sc/notes.py）
//!   - nightmare：魇化精英与魇印——「死亡」「不可能」里小怪魇化、夺魇火，魇印刻进刻印位后所有难度都生效（参数侧在 rr/nightmare.py）
//!   - fusion：融锻之心、许愿石的 Boss 掉落——平时追忆 Boss 按难度递增、「死亡」「不可能」里所有 Boss 照龙心脏的数量（许愿石每场 1 个、追忆 3 个），各只给一次（参数侧在 rr/bosses.py fusion_lines）
//!   - wishstone：许愿石升级——赐福菜单选一项能力值，扣 1 个许愿石、能力值 +1、等级 +1（参数侧在 rr/wishstone.py、sc/wishstone.py）
//!   - levelup：开发工具「能力值调整」写 levelup_req.txt，直接改一项能力值和等级（±1）
//!   - clash：相杀——相杀的效果行按拿着的武器的防御时减伤率改（轻击一半、重击全额；挂不挂由积木引擎按动作进度，参数侧在 extract_affixes.py dr_clash）
//!   - shopstage：暗黑商店分阶段解锁——打败有新东西上架的区域的追忆 Boss 时弹原版闪烁提示（参数侧在 rr/darkshop.py stage_lines）
//!   - ovldrop：超限锻造石的掉落——「死亡」「不可能」里 Boss 每档第一次击败、附近小怪死亡按几率发（参数侧在 rr/overlimit.py）
//!   - glow：传说武器的属性光效——换武器后光效落到手上，等新武器拿到手再让游戏重挂（用户 2026-11-05）
//!   - spellbase：法器面板给法球用——左右手拿着的法器里法术补正面板最高的 ÷ 200，给法球（迸发、星群）乘。
//! 每个模块的定义文件由重随写在 DLL 旁边（没有就不管这个功能）；日志 dark_core.log。
//! 认 eldenring.exe 2.7.1.0 / 2.7.2.0（地址表在 ../vendor 的 fromsoftware-rs 副本里），别的版本不工作。
//! 加新功能：新建一个模块，提供 tick()，在 DllMain 的任务里加一行（出错只记日志、不影响其他功能）。

mod arena;
mod attrstack;
#[macro_use]
mod chrs;
mod ashdiag;
mod boat;
mod castpanel;
mod bossmode;
mod barrier;
mod coop;
mod curses;
mod festive;
mod flagguard;
mod fusion;
mod glow;
mod gear;
mod hpunify;
mod levelup;
mod link;
mod net;
mod wishstone;
mod shopstage;
mod clash;
mod nightmare;
mod notes;
mod orbshot;
mod ovldrop;
mod pickup;
mod plague;
mod unseen;
mod procs;
mod prof;
mod rules;
mod shots;
mod speed;
mod runebank;
mod runtime;
mod scaling;
mod skillmult;
mod slotdiag;
mod sound;
mod spellbase;
mod transmogicon;

use std::fs;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::PathBuf;
use std::sync::{Condvar, Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{CSTaskGroupIndex, CSTaskImp, GameDataMan};
use eldenring::fd4::FD4TaskData;
use fromsoftware_shared::{FromStatic, SharedTaskImpExt};
use windows::Win32::Foundation::HMODULE;
use windows::Win32::System::LibraryLoader::GetModuleFileNameW;

static DIR: OnceLock<PathBuf> = OnceLock::new();

pub(crate) fn dir() -> PathBuf {
    DIR.get().cloned().unwrap_or_else(|| PathBuf::from("."))
}

/// 日志后台写（用户 2026-11-05「高难下有点卡顿」：每行开关一次文件，在主线程上要 1.5 毫秒（移动硬盘实测），战斗里每秒几行、进图时一秒几十行）。
/// log() 只把一行放进缓冲区，开文件、写文件都在 dark_core_log 线程；顺序不变，每行的时间是调用时的时间。线程起不来就当场写
static LOG_BUF: Mutex<Vec<u8>> = Mutex::new(Vec::new());
static LOG_WAKE: Condvar = Condvar::new();
static LOG_THREAD: OnceLock<bool> = OnceLock::new();

fn log_write(bytes: &[u8]) {
    use std::io::Write;
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(dir().join("dark_core.log")) {
        let _ = f.write_all(bytes);
    }
}

fn log_thread() {
    let mut out = Vec::new();
    loop {
        {
            let mut g = LOG_BUF.lock().unwrap_or_else(|e| e.into_inner());
            while g.is_empty() {
                g = LOG_WAKE.wait(g).unwrap_or_else(|e| e.into_inner());
            }
            std::mem::swap(&mut *g, &mut out);
        }
        log_write(&out);
        out.clear();
    }
}

pub(crate) fn log(msg: &str) {
    use std::io::Write;
    let t = local_time();
    let threaded = *LOG_THREAD.get_or_init(|| std::thread::Builder::new().name("dark_core_log".into()).spawn(log_thread).is_ok());
    let mut g = LOG_BUF.lock().unwrap_or_else(|e| e.into_inner());
    let _ = writeln!(g, "{:02}:{:02}:{:02}.{:03} {msg}", t.hour, t.min, t.sec, t.ms);
    if threaded {
        drop(g);
        LOG_WAKE.notify_one();
    } else {
        log_write(&g);
        g.clear();
    }
}

/// 本地时间：日志每行开头写时:分:秒.毫秒，加载时写一行日期（直接调 kernel32，不用给 windows crate 加特性）
#[repr(C)]
#[derive(Default)]
struct LocalTime {
    year: u16,
    month: u16,
    _weekday: u16,
    day: u16,
    hour: u16,
    min: u16,
    sec: u16,
    ms: u16,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetLocalTime(t: *mut LocalTime);
}

fn local_time() -> LocalTime {
    let mut t = LocalTime::default();
    unsafe { GetLocalTime(&mut t) };
    t
}

/// 现在的本地日期时间「2026-11-01 17:34:30」（写进记录文件的）
pub(crate) fn now_text() -> String {
    let t = local_time();
    format!("{}-{:02}-{:02} {:02}:{:02}:{:02}", t.year, t.month, t.day, t.hour, t.min, t.sec)
}

fn module_dir(h: u64) -> PathBuf {
    let mut buf = [0u16; 1024];
    let n = unsafe { GetModuleFileNameW(Some(HMODULE(h as *mut _)), &mut buf) } as usize;
    let p = PathBuf::from(String::from_utf16_lossy(&buf[..n]));
    p.parent().map(|d| d.to_path_buf()).unwrap_or_else(|| PathBuf::from("."))
}

/// 版本不对时库里查地址表会 panic：在这里接住
fn version_ok() -> bool {
    catch_unwind(|| {
        let _ = unsafe { GameDataMan::instance() };
    })
    .is_ok()
}

/// 跑一个功能的 tick：panic 只记前 3 次日志，不影响别的功能
fn guarded(name: &'static str, errs: &mut u32, f: fn()) {
    let t0 = prof::on().then(Instant::now);
    if catch_unwind(AssertUnwindSafe(f)).is_err() {
        *errs += 1;
        if *errs <= 3 {
            log(&format!("{name}：出错（已跳过这一帧）"));
        }
    }
    if let Some(t0) = t0 {
        prof::add(name, t0.elapsed());
    }
}

/// # Safety
/// 由加载器（YAFSML / me3）调用，不要自己调用。
#[unsafe(no_mangle)]
pub unsafe extern "system" fn DllMain(hmodule: u64, reason: u32, _reserved: *mut std::ffi::c_void) -> i32 {
    if reason != 1 {
        return 1;
    }
    let _ = DIR.set(module_dir(hmodule));
    // 同一处 panic 只记前 3 次、之后每 100 次记一次（读图时参数还没好，有的每帧都报，以前一次启动能刷几百行）
    std::panic::set_hook(Box::new(|info| {
        static SEEN: std::sync::Mutex<std::collections::BTreeMap<String, u32>> = std::sync::Mutex::new(std::collections::BTreeMap::new());
        let at = info.location().map(|l| format!("{}:{}", l.file(), l.line())).unwrap_or_default();
        let n = match SEEN.try_lock() {
            Ok(mut m) => {
                let n = m.entry(at).or_insert(0);
                *n += 1;
                *n
            }
            Err(_) => 1,
        };
        if n <= 3 || n % 100 == 0 {
            log(&format!("panic{}：{info}", if n > 3 { format!("（这一处第 {n} 次）") } else { String::new() }));
        }
    }));
    let t = local_time();
    log(&format!("==== {}-{:02}-{:02} 加载（进程 {}）", t.year, t.month, t.day, std::process::id()));
    std::thread::spawn(|| {
        if !version_ok() {
            log("游戏版本不是 2.7.1.0（1.17.1）/ 2.7.2.0（1.17.2），dark_core 不工作");
            return;
        }
        let scaling = catch_unwind(scaling::install).unwrap_or_else(|_| "补正显示数值（出错，没改）".into());
        // 能施法的近战武器（卡利亚魔法剑）面板上显示魔法加成（用户 2026-11-13），自己记日志
        if catch_unwind(castpanel::install).is_err() {
            log("能施法的近战武器显示魔法加成：出错，没改");
        }
        let combat = runtime::init();
        transmogicon::start();
        // 加载器注入得很早：任务调度器可能还没建好，每秒重试（最多 10 分钟）
        let mut task = None;
        for _ in 0..600 {
            if let Ok(t) = CSTaskImp::wait_for_instance(Duration::from_secs(1)) {
                task = Some(t);
                break;
            }
            std::thread::sleep(Duration::from_secs(1));
        }
        let Some(task) = task else {
            log("10 分钟内等不到 CSTaskImp，dark_core 不工作");
            return;
        };
        log(&format!("dark_core 已加载：{}；{}；{}；{}（{combat}）；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{}；{scaling}", arena::describe(), festive::describe(), gear::describe(), runtime::describe(),
                     rules::describe(), procs::describe(), boat::describe(), attrstack::describe(), skillmult::describe(), spellbase::describe(), hpunify::describe(), ovldrop::describe(), fusion::describe(), nightmare::describe(), curses::describe(), notes::describe(), plague::describe(), wishstone::describe(), shopstage::describe(), clash::describe(), bossmode::describe(), glow::describe(), runebank::describe()));
        let mut errs = [0u32; 32];
        task.run_recurring(
            move |_: &FD4TaskData| {
                prof::frame();
                chrs::refresh_players();      // 这一帧的玩家角色（rules::is_foe 跳过它们，联机计划 13.2 G8）
                // 联机时记玩家放出的子弹（远程命中归属，联机计划 13.7）：放在积木引擎、咒痕前面；不在会话里什么都不读
                guarded("联机子弹记录", &mut errs[30], shots::tick);
                guarded("庆典油脂", &mut errs[0], festive::tick);
                guarded("新装备系统", &mut errs[1], gear::tick);
                guarded("新词条", &mut errs[2], runtime::tick);
                guarded("触发词条补正", &mut errs[4], procs::tick);
                guarded("法器倍率", &mut errs[8], spellbase::tick);
                guarded("积木引擎", &mut errs[3], rules::tick);
                guarded("数值词条叠加", &mut errs[5], attrstack::tick);
                guarded("第五护符槽诊断", &mut errs[27], slotdiag::tick);
                guarded("战技伤害按稀有度", &mut errs[7], skillmult::tick);
                guarded("高难度血量补正", &mut errs[9], hpunify::tick);
                guarded("超限锻造石掉落", &mut errs[10], ovldrop::tick);
                guarded("融锻之心掉落", &mut errs[14], fusion::tick);
                guarded("魇化", &mut errs[11], nightmare::tick);
                guarded("咒痕", &mut errs[12], curses::tick);
                guarded("原版提示", &mut errs[13], notes::tick);
                guarded("疫病护符", &mut errs[15], plague::tick);
                guarded("无形", &mut errs[23], unseen::tick);
                guarded("能力值调整（开发工具）", &mut errs[16], levelup::tick);
                guarded("许愿石升级", &mut errs[17], wishstone::tick);
                guarded("卢恩银行", &mut errs[26], runebank::tick);
                guarded("暗黑商店分阶段解锁提示", &mut errs[18], shopstage::tick);
                guarded("相杀", &mut errs[19], clash::tick);
                guarded("高难度 Boss 改版", &mut errs[20], bossmode::tick);
                guarded("传说光效重挂", &mut errs[21], glow::tick);
                guarded("法球发射点测试", &mut errs[22], orbshot::tick);
                guarded("骨灰诊断", &mut errs[24], ashdiag::tick);
                // 放在魇化后面：同一帧里登记的强制魇化下一帧生效（魇化每 250 毫秒扫一次，不差这一帧）
                guarded("斗技场试炼", &mut errs[25], arena::tick);
                // 放在积木引擎后面：同一帧里它刚记下的改动、挂的效果这里都看得到
                guarded("联机诊断", &mut errs[6], coop::tick);
                // 联机通道（Steam 消息，联机计划 13.4）：没加载 Seamless、没有开发工具请求时什么都不做
                guarded("联机通道", &mut errs[28], link::tick);
                // 别的角色的动作速度（时隙、见切 / 影步减速、魇化加快、客机转来的）：放在它们后面，乘起来写一次（speed.rs）
                guarded("动作速度", &mut errs[31], speed::flush);
                // 存档标记护栏（联机计划 13.3 C7）：会话里把外来改动的卢恩银行余额、魇火等改回去
                guarded("存档标记护栏", &mut errs[29], flagguard::tick);
            },
            CSTaskGroupIndex::FrameBegin,
        );
        // 碾压：动作更新完、物理和伤害判定之前清翻滚的无敌位（FrameBegin 清了会被动作事件重新设上）
        let mut err_pp = 0u32;
        task.run_recurring(
            move |_: &FD4TaskData| guarded("碾压（物理前）", &mut err_pp, runtime::pre_physics),
            CSTaskGroupIndex::ChrIns_PrePhysicsSafe,
        );
        // 唤声船：改位置要在物理更新前（同 dark_wings 的飞行）
        let mut err_boat = 0u32;
        task.run_recurring(move |_: &FD4TaskData| guarded("唤声船", &mut err_boat, boat::tick), CSTaskGroupIndex::ChrIns_PrePhysics);
        // 「死亡」以上难度和这次加载的世界对不上时的屏障（bossmode 定要不要）：推回圈里同样要在物理更新前
        let mut err_bar = 0u32;
        task.run_recurring(move |_: &FD4TaskData| guarded("难度屏障", &mut err_bar, barrier::tick), CSTaskGroupIndex::ChrIns_PrePhysics);
        // 见切减速 / 影步停住的敌人：转身同样放慢（改朝向也要在物理更新前；没有减速中的敌人就什么都不做）
        let mut err_turn = 0u32;
        task.run_recurring(move |_: &FD4TaskData| guarded("减速敌人的转身", &mut err_turn, rules::turn_hold), CSTaskGroupIndex::ChrIns_PrePhysics);
    });
    1
}

#[cfg(test)]
mod tests {
    /// 日志在后台写：调用马上返回，过一会儿文件里有，顺序不变
    #[test]
    fn log_in_background() {
        let tag = format!("日志测试 {}", std::process::id());
        for k in 0..50 {
            super::log(&format!("{tag} 第 {k} 行"));
        }
        let path = super::dir().join("dark_core.log");
        let t0 = std::time::Instant::now();
        loop {
            let text = std::fs::read_to_string(&path).unwrap_or_default();
            if let Some(last) = text.find(&format!("{tag} 第 49 行")) {
                assert!(text.find(&format!("{tag} 第 0 行")).unwrap() < text.find(&format!("{tag} 第 25 行")).unwrap());
                assert!(text.find(&format!("{tag} 第 25 行")).unwrap() < last);
                break;
            }
            assert!(t0.elapsed() < std::time::Duration::from_secs(5), "5 秒还没写进文件");
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
    }

    /// 日志用的本地时间：结构体和 Windows 的 SYSTEMTIME 对得上（年月日时分秒都在正常范围）
    #[test]
    fn local_time_sane() {
        let t = super::local_time();
        assert!((2020..2100).contains(&t.year) && (1..=12).contains(&t.month) && (1..=31).contains(&t.day), "{}-{}-{}", t.year, t.month, t.day);
        assert!(t.hour < 24 && t.min < 60 && t.sec < 60 && t.ms < 1000);
    }
}
