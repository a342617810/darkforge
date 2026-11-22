//! 斗技场试炼（参数侧 rr/arena.py，地图 / 事件 / 雕像对话 sc/arena.py；用户 2026-11-10，提案 dev\item_system\斗技场试炼提案.md）：
//! - 雕像对话选了场次：场次写进 len0 / len1 两位、点亮请求 req。这里看到请求：按玩家所在地图认是哪个雕像（statue 行），
//!   扣星光碎片，两位改写成竞技场编号 + 1、点亮传送请求 warp（公共事件把玩家传进竞技场），排好这一次的出场顺序。
//! - 进了竞技场等几秒出第一波：一波魇化精英（per 个，站位不重复；nightmare.rs 强制魇化）、一波 Boss 轮流；
//!   精英位有 scarab% 换成红 / 蓝粪金龟（打死回一次红露滴 / 蓝露滴；用户 2026-11-15，一波里至少留一个真精英；
//!   不魇化、不加血，会逃跑钻地，所以不算进「这一波都死了」）；点亮各部件的出场标记，
//!   竞技场的事件启用它们、死了点亮死亡标记。敌人读进来以后（就绪标记）点亮开打标记，事件打开 AI、关掉无敌。
//!   这一波都死了：奖励直接发进背包（精英波 items_e 件未鉴定物品；Boss 波 items_b 件 + ash_b 个骨灰；
//!   用户 2026-11-10「每波结束的奖励也要让玩家知道 可以先发放到背包里 如果死亡再扣除」），记下发了哪些道具；
//!   不是最后一波就点亮问继续（是 → 下一波；否 / 取消 → 离开），最后一波另给 bonus 件史诗 / 传说，离开。
//! - 离开：点亮离开标记（竞技场的事件把玩家传回进来的雕像旁）。
//! - 死了：这次试炼发的道具全部收回（等发货队列发完再扣），提示「斗技场试炼失败」（notes.rs 的 arena fail）；
//!   复活点由竞技场的事件设到进来的雕像旁（run 标记亮着时玩家死了，2003[23]）。没死就离开了竞技场（别的办法出去）：奖励保留。
//!   真死了才算（death_tick）：血量 0 停了 DEATH_HOLD 还没被高难度的馈赠复活顶掉，或者血量回来了身上却没有「刚复活」的效果
//!   （以前血量一到 0 就记死亡，馈赠复活以后这一波永远不结算、离开时还按失败收回）。
//! - 每波出场时给敌人挂的（通用的敌人效果模块 foefx.rs，来源「斗技场」；下一波、结束时放掉）：血量随波次（hpwave，粪金龟不挂），
//!   加上 wfx 规则命中的效果包（用户 2026-11-17「给任意指定波数敌人挂自定义效果」：哪个竞技场、哪种场次、第几波、哪种敌人、几率）。
//! - 稀有度：rar（这个竞技场所在地区档的权重）× dmult（当前难度档的倍率）；骨灰 ashrar × dmult。DLC 档的传说给传说（幽影之地）。
//! - 竞技场里的提示（第几波、本波肃清、完成）：编号写进本图的 note0 起 note_n 位（竞技场的事件显示）。
//! - 试炼中退出游戏：arena_run.txt 记着在哪个竞技场、从哪个雕像进来的；下次进存档人还在那个竞技场里就传回雕像旁（不在就删掉记录）。
//! - 联机（联机计划 13.13，用户 2026-11-17「开始做」；照黄金树爬塔的思路，没抄代码）：房主带队。
//!   房主在雕像开始：出场顺序房主排，每秒经联机通道给各个队员发一次进度（state：第几波、出场了没有、开打了没有、打完了几波、问谁继续、
//!   结束了没有；变了马上发），队员每秒报一次自己的情况（me：付没付碎片、进场了没有、这一波就绪了没有、倒下了没有、怎么回答的）。
//!   都是「现在是什么样」而不是「发生了什么」，会话断开又连上也对得上。
//!   - 队员收到进度：扣自己的星光碎片（不够的只能帮忙、不拿奖励），传进竞技场；房主出场了就点亮自己的出场标记（敌人是同一批，
//!     竞技场的事件都关了网络同步，各自启用自己那份），房主开打了就点亮自己的开打标记；打完一波各自发自己的奖励。
//!   - 房主等队员都进场（或者 ARRIVE_GIVEUP）才出第一波；每一波等各台电脑都就绪（或者 BIND_GIVEUP）才开打；这一波打完没有看房主自己那份。
//!   - 问继续：房主活着问房主，房主倒下了问第一个活着的队员。
//!   - 倒下的人收回自己这次的奖励（观战到试炼结束，不传送）；所有人都倒下才算失败。房主离开了竞技场试炼就结束（队员保留奖励、传回雕像旁）。
//!   - 魇化精英：房主抽、广播（nightmare.rs），队员照着挂，自己不抽。
//! 定义 arena.txt（rr/arena.py 的 def_lines）。

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use std::path::PathBuf;

use eldenring::cs::{GameDataMan, SoloParamRepository, SpEffectParam, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::foefx::Fx;
use crate::gear::{count_goods, flag_get, flag_set, gifts_pending, gift_log, give_ashes, remove_goods};
use crate::link::{Kind, Packet};
use crate::{dir, log};

const STEP: Duration = Duration::from_millis(100);
/// 在敌人效果模块（foefx.rs）里的来源名
const FX_TAG: &str = "斗技场";
/// 进了竞技场多久出第一波
const ARRIVE_WAIT: Duration = Duration::from_secs(4);
/// 扣了碎片多久还没进竞技场就算传送失败（退还碎片）
const GO_TIMEOUT: Duration = Duration::from_secs(40);
/// 选了继续多久出下一波
const NEXT_WAIT: Duration = Duration::from_secs(3);
/// 一波打完多久才问继续（等「获得物品」和「本波已肃清」的提示过去，太早对话框会被顶掉、以取消结束）
const ASK_DELAY: Duration = Duration::from_secs(4);
/// 问了这么短就回「否」：人按不了这么快，当成对话框被别的提示顶掉、以取消结束，再问一次
const TOO_FAST: Duration = Duration::from_millis(1500);
/// 出场多久以后核对一次：一个都不在就是地图没放上（退还碎片、离开）
const CHECK_AFTER: Duration = Duration::from_secs(8);
/// 结算以后多久传出去（看完提示）
const LEAVE_WAIT: Duration = Duration::from_secs(4);
/// 最后一波打完多久传出去（多看一会儿 TRIAL COMPLETE 字幕，用户 2026-11-10「结束时的传送晚2s」）
const CLEAR_LEAVE_WAIT: Duration = Duration::from_secs(6);
/// 试炼中不在竞技场里多久算离开了（死了复活在赐福）
const AWAY_HOLD: Duration = Duration::from_secs(3);
/// 读档后人在竞技场里、记录说试炼没结束：多久以后传回雕像旁
const STUCK_AFTER: Duration = Duration::from_secs(8);
/// 血量 0 停了这么久还没被馈赠复活顶掉，算真的死了（复活有时要等 1 秒多：咒痕 2026-11-14 的日志）
const DEATH_HOLD: Duration = Duration::from_millis(2500);
/// 出场这么久还没等到就绪标记：看得到这个敌人、活着就算读进来了
const BIND_FALLBACK: Duration = Duration::from_millis(1500);
/// 联机：等各台电脑就绪最多等多久（之后照样开打）
const BIND_GIVEUP: Duration = Duration::from_secs(15);
/// 联机：等队员进场最多等多久
const ARRIVE_GIVEUP: Duration = Duration::from_secs(30);
/// 联机：多久发一次进度 / 报一次自己的情况（变了马上发）
const SYNC_EVERY: Duration = Duration::from_secs(1);
/// 联机：这么久没收到队员的消息就不等他了（读图慢的回来了照样算）
const MATE_LOST: Duration = Duration::from_secs(20);
/// 联机：队员这么久没收到房主的进度，试炼结束（奖励保留）
const HOST_LOST: Duration = Duration::from_secs(30);
/// 联机：问队员继续不继续最多等多久（之后当成离开）
const ASK_GIVEUP: Duration = Duration::from_secs(120);
/// 联机：试炼结束后房主再发这么久「结束」（队员那几秒正好断了也能收到）
const END_RESEND: Duration = Duration::from_secs(10);
const RAR_ZH: [&str; 5] = ["普通", "稀有", "史诗", "传说", "传说（幽影之地）"];
const CAT_ZH: [&str; 3] = ["武器", "防具", "护符"];
const RUN_FILE: &str = "arena_run.txt";

#[derive(Debug, Default, Clone, PartialEq)]
struct Part {
    k: u32,
    boss: bool,
    /// 红 / 蓝粪金龟（arena.txt 的 kind 's'）
    scarab: bool,
    ent: u32,
    spot: i32,
    name: String,
}

#[derive(Debug, Default, Clone, PartialEq)]
struct Colo {
    x: u32,
    flag: u32,
    /// (雕像序号, 地图块 area block region index)
    statues: Vec<(u32, [u8; 4])>,
    /// 未鉴定物品的稀有度：[精英波, Boss 波]（0 普通 … 3 传说、4 传说（幽影之地））
    tiers: [usize; 2],
    /// 件数倍率
    scale: u32,
    ashrar: [f32; 4],
    parts: Vec<Part>,
    /// 复活用的生成器（arena.txt 的 gen 行）：(部件 k 的复活请求标记起点, 部件 k 的生成器实体起点)，都 + k
    revive: Option<(u32, u32)>,
}

#[derive(Debug, Default, PartialEq)]
struct Def {
    req: u32,
    len: [u32; 2],
    warp: u32,
    shard: u32,
    goods0: i32,
    spawn: u32,
    dead: u32,
    ask: u32,
    leave: u32,
    /// 试炼进行中（+ 雕像序号）：竞技场的事件看到它亮着、玩家死了，就把复活点设到那个雕像旁
    run: u32,
    /// 最后一波打完的大字幕（竞技场的事件放 TRIAL COMPLETE；0 = 没有，照旧用闪烁提示）
    banner: u32,
    note0: u32,
    note_n: u32,
    /// 部件 k 读进来了（+ k，竞技场的事件点亮；0 = 旧的事件没有）
    ready: u32,
    /// 开打（竞技场的事件打开 AI、关掉无敌；0 = 旧的事件没有，出场就打）
    engage: u32,
    /// 本机死了（这里点亮，竞技场的事件照样把复活点设到雕像旁）
    mydead: u32,
    per: usize,
    /// 精英位换成粪金龟的几率 %
    scarab: f32,
    items_e: u32,
    items_b: u32,
    ash_b: u32,
    cat: [f32; 3],
    /// (当前档标记起点, 档数, 普通是第几档)
    diff: Option<(u32, usize, usize)>,
    /// 死亡以上的奖励（lockrew 行）：(稀有度, 难度档)；试炼开始时是这几档，三个竞技场的未鉴定物品都用这个稀有度
    /// （用户 2026-11-20「死亡以上的竞技场的奖励统一为幽影地传说」）
    lockrew: Option<(usize, Vec<usize>)>,
    dmult: Vec<[f32; 4]>,
    /// 场次（1 起）→ (波数, 碎片, 全部打完多给几件, 全部打完退还几个碎片)
    runs: Vec<(usize, u32, u32, u32)>,
    colos: Vec<Colo>,
    notes: HashMap<String, u32>,
    /// 每档难度魇化精英带两条的几率 %
    two: Vec<f32>,
    /// 血量随波次：(每几波一档, 第一档的效果, 档数)；第 w 波（0 起）= w / every 档
    hpwave: Option<(usize, i32, usize)>,
    /// 按波次挂的效果包
    wfx: Vec<WaveFx>,
    /// 无尽试炼（arena.txt 的 endless 行）
    endless: Option<EndlessDef>,
}

/// 无尽试炼（用户 2026-11-19，提案 dev\item_system\无尽模式提案.md；rr/arena.py 的 ENDLESS_*）：只在死亡以上开放、不花碎片、
/// 每波敌人血量 +step（第 1 波不加、不封顶）、每波奖励最多 cap 件、不给骨灰、死了不收回、每波之后可以保存进度离开
#[derive(Debug, Clone, PartialEq)]
struct EndlessDef {
    /// 雕像菜单选了无尽（场次位 1 = 继续、2 = 从第 1 波开始）
    req: u32,
    /// 竞技场 X 有保存的进度：has0 + X（进存档时写，菜单按它列不列「继续」）
    has0: u32,
    /// 血量效果行（每波开打前改它的 maxHpRate）
    sp: u32,
    step: f32,
    cap: u32,
    /// 竞技场里的标记 F + local：无尽试炼进行中（问继续的事件换成「选否 = 保存进度离开」那句）
    local: u32,
    /// 开放的难度档（difficulty 里标了 lock 的：死亡、不可能）
    tiers: Vec<usize>,
}

/// 生成器（rr/arena.py 的 GEN_*）：哪个竞技场、部件 k 的复活请求标记起点（+ k，竞技场的复活事件听着叫部件 k 的生成器）、
/// 部件 k 的生成器实体起点（+ k，只写日志用）。开发工具按钮、记录按现在的试炼 / 人在的竞技场取（gen_here）
#[derive(Debug, Clone, Copy, PartialEq)]
struct GenTest {
    x: u32,
    req0: u32,
    gen0: u32,
}

/// 生成器实验：进了那个竞技场的试炼、或者点过按钮以后这么久里一直记那个竞技场的敌人
const GEN_WATCH: Duration = Duration::from_secs(600);
const GEN_SCAN: Duration = Duration::from_millis(500);
const GEN_LOGS: u32 = 400;
/// 复活后再看一次身上的效果（别的模块可能隔一会儿才挂回去）
const GEN_RECHECK: Duration = Duration::from_secs(3);
/// 两次扫描之间活着挪了这么远：当成被生成器挪到了出生点（跑动 0.5 秒到不了）
const GEN_JUMP: f32 = 5.0;

/// 生成器实验：一只敌人上次看到的样子
#[derive(Debug, Default, Clone)]
struct GenSeen {
    ent: u32,
    hp: i32,
    max: i32,
    pos: [f32; 3],
    /// ChrIns 的几个状态字（第六轮 enable_render 32 只全是开着的，分不出禁用 / 生成器没放出来的，这轮记原始值找规律）：
    /// [load_state, chr_activation_flags, debug_flags]；chr_flags1c4~1ca 的 7 个字节（里面有每帧变的位，只写进记录、不比变化）
    st: [u32; 3],
    fl: [u8; 7],
    /// 活着时最后一次看到的身上的效果、血量上限
    sps: Vec<i32>,
    alive_max: i32,
    died_at: Option<Instant>,
}

/// 生成器实验的记录（地址 → 上次看到的样子）
#[derive(Debug, Default)]
struct GenWatch {
    until: Option<Instant>,
    next: Option<Instant>,
    seen: HashMap<usize, GenSeen>,
    logs: u32,
    born: u32,
    died: u32,
    revived: u32,
    /// 叫过生成器的部件 k
    called: HashSet<u32>,
    /// 复活后过一会儿再看效果：(地址, 到什么时候, 倒下前的效果)
    recheck: Vec<(usize, Instant, Vec<i32>)>,
    /// 玩家身上的卢恩（上次看到的）
    runes: Option<u32>,
}

/// 按波次挂的效果（arena.txt 的 wfx 行，rr/arena.py wave_fx_lines）：wfx 竞技场 场次的总波数 哪种敌人 第几波 几率% 效果包（- = 不限）
#[derive(Debug, Clone, PartialEq)]
struct WaveFx {
    /// 哪些竞技场（空 = 全部）
    colos: Vec<u32>,
    /// 哪种场次：场次的总波数（空 = 全部）
    runs: Vec<usize>,
    /// Boss / 精英 / 粪金龟
    who: [bool; 3],
    /// 第几波（1 起，闭区间；usize::MAX = 往后都算）
    waves: Vec<(usize, usize)>,
    /// 每个敌人挂上的几率 %
    chance: f32,
    packs: Vec<String>,
}

/// 「3」「3-6」「5+」逗号分开
fn parse_waves(s: &str) -> Option<Vec<(usize, usize)>> {
    let mut out = Vec::new();
    for t in s.split(',').map(str::trim) {
        let r: (usize, usize) = if let Some(a) = t.strip_suffix('+') {
            (a.parse().ok()?, usize::MAX)
        } else if let Some((a, b)) = t.split_once('-') {
            (a.parse().ok()?, b.parse().ok()?)
        } else {
            let a = t.parse().ok()?;
            (a, a)
        };
        if r.0 == 0 || r.1 < r.0 {
            return None;
        }
        out.push(r);
    }
    (!out.is_empty()).then_some(out)
}

/// 逗号分开的数（- = 空，不限）
fn num_list<T: std::str::FromStr>(s: &str) -> Option<Vec<T>> {
    if s == "-" {
        return Some(Vec::new());
    }
    s.split(',').map(|x| x.trim().parse().ok()).collect()
}

impl WaveFx {
    fn parse(f: &[&str]) -> Option<WaveFx> {
        let who = f.get(3)?;
        let packs: Vec<String> = f.get(6)?.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
        (!packs.is_empty()).then_some(())?;
        Some(WaveFx {
            colos: num_list(f.get(1)?)?,
            runs: num_list(f.get(2)?)?,
            who: [who.contains('b'), who.contains('e'), who.contains('s')],
            waves: parse_waves(f.get(4)?)?,
            chance: f.get(5)?.parse::<f32>().ok().filter(|x| x.is_finite())?.clamp(0.0, 100.0),
            packs,
        })
    }

    /// 竞技场 x、总波数 waves 的场次里第 wave 波（1 起）出场的 p 归不归这条规则管（几率另算）
    fn matches(&self, x: u32, waves: usize, wave: usize, p: &Part) -> bool {
        let kind = if p.boss { 0 } else if p.scarab { 2 } else { 1 };
        self.who[kind]
            && (self.colos.is_empty() || self.colos.contains(&x))
            && (self.runs.is_empty() || self.runs.contains(&waves))
            && self.waves.iter().any(|&(a, b)| (a..=b).contains(&wave))
    }
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn f4(f: &[&str]) -> Option<[f32; 4]> {
    let v: Vec<f32> = f.iter().filter_map(|x| x.parse().ok()).collect();
    (v.len() >= 4).then(|| [v[0], v[1], v[2], v[3]])
}

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    let mut colos: HashMap<u32, Colo> = HashMap::new();
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}').trim_end();
        if l.starts_with('#') || l.is_empty() {
            continue;
        }
        let f: Vec<&str> = l.split('\t').collect();
        let n = |i: usize| f.get(i).and_then(|x| x.parse::<u32>().ok());
        match f[0] {
            "req" => {
                d.req = n(1)?;
                d.len = [n(2)?, n(3)?];
                d.warp = n(4)?;
            }
            "shard" => d.shard = n(1)?,
            "goods0" => d.goods0 = n(1)? as i32,
            "local" => {
                (d.spawn, d.dead, d.ask, d.leave, d.note0, d.note_n, d.run) = (n(1)?, n(2)?, n(3)?, n(4)?, n(5)?, n(6)?, n(7)?);
                d.banner = n(8).unwrap_or(0);
                (d.ready, d.engage, d.mydead) = (n(9).unwrap_or(0), n(10).unwrap_or(0), n(11).unwrap_or(0));
            }
            "per" => d.per = n(1)? as usize,
            "scarab" => d.scarab = f.get(1).and_then(|x| x.parse::<f32>().ok())?.clamp(0.0, 100.0),
            "items" => (d.items_e, d.items_b, d.ash_b) = (n(1)?, n(2)?, n(3)?),
            "cat" => d.cat = [n(1)? as f32, n(2)? as f32, n(3)? as f32],
            "diff" => d.diff = Some((n(1)?, n(2)? as usize, n(3)? as usize)),
            "lockrew" => {
                d.lockrew = Some(((n(1)? as usize).min(4), f.get(2).map(|t| t.split(',').filter_map(|v| v.trim().parse().ok()).collect()).unwrap_or_default()))
            }
            "dmult" => {
                let k = n(1)? as usize;
                if d.dmult.len() <= k {
                    d.dmult.resize(k + 1, [1.0; 4]);
                }
                d.dmult[k] = f4(&f[2..])?;
            }
            "hpwave" => d.hpwave = Some(((n(1)? as usize).max(1), n(2)? as i32, n(3)? as usize)),
            "endless" => {
                d.endless = Some(EndlessDef {
                    req: n(1)?,
                    has0: n(2)?,
                    sp: n(3)?,
                    step: f.get(4)?.parse().ok()?,
                    cap: n(5)?,
                    local: n(6)?,
                    tiers: f.get(7).map(|t| t.split(',').filter_map(|v| v.trim().parse().ok()).collect()).unwrap_or_default(),
                })
            }
            "gen" | "gentest" => colos.entry(n(1)?).or_default().revive = Some((n(2)?, n(3)?)),
            // 写错的一条不要（不影响整个试炼）
            "wfx" => match WaveFx::parse(&f) {
                Some(w) => d.wfx.push(w),
                None => log(&format!("竞技场：看不懂这条按波次挂的效果「{}」，不要", l)),
            },
            "two" => {
                let k = n(1)? as usize;
                if d.two.len() <= k {
                    d.two.resize(k + 1, 0.0);
                }
                d.two[k] = f.get(2).and_then(|x| x.parse().ok())?;
            }
            "run" => {
                let k = n(1)? as usize;
                if k == 0 {
                    return None;
                }
                if d.runs.len() < k {
                    d.runs.resize(k, (0, 0, 0, 0));
                }
                d.runs[k - 1] = (n(2)? as usize, n(3)?, n(4)?, n(5).unwrap_or(0).min(n(3)?));
            }
            "colo" => {
                let x = n(1)?;
                let c = colos.entry(x).or_default();
                c.x = x;
                c.flag = n(2)?;
            }
            "statue" => {
                let x = n(1)?;
                let b = [n(3)? as u8, n(4)? as u8, n(5)? as u8, n(6)? as u8];
                colos.entry(x).or_default().statues.push((n(2)?, b));
            }
            "rew" => {
                let c = colos.entry(n(1)?).or_default();
                c.tiers = [(n(2)? as usize).min(4), (n(3)? as usize).min(4)];
                c.scale = n(4)?.max(1);
            }
            "ashrar" => colos.entry(n(1)?).or_default().ashrar = f4(&f[2..])?,
            "part" => {
                let x = n(1)?;
                let p = Part {
                    k: n(2)?,
                    boss: f.get(3) == Some(&"b"),
                    scarab: f.get(3) == Some(&"s"),
                    ent: n(4)?,
                    spot: f.get(6).and_then(|s| s.parse().ok())?,
                    name: f.get(7).unwrap_or(&"").to_string(),
                };
                colos.entry(x).or_default().parts.push(p);
            }
            "note" => {
                d.notes.insert(f.get(1)?.to_string(), n(2)?);
            }
            _ => {}
        }
    }
    let mut cs: Vec<Colo> = colos.into_values().filter(|c| c.flag > 0 && !c.statues.is_empty() && !c.parts.is_empty()).collect();
    cs.sort_by_key(|c| c.x);
    d.colos = cs;
    (d.req > 0 && d.warp > 0 && d.shard > 0 && d.goods0 > 0 && d.note_n > 0 && !d.runs.is_empty() && !d.colos.is_empty()).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("arena.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!(
            "斗技场试炼（{} 个竞技场，{} 个敌人；场次 {:?}{}）",
            d.colos.len(),
            d.colos.iter().map(|c| c.parts.len()).sum::<usize>(),
            d.runs.iter().map(|r| r.0).collect::<Vec<_>>(),
            if d.engage > 0 { "；就绪后开打，联机房主带队" } else { "；旧的竞技场事件，没有开打标记" }
        ) + &d.endless.as_ref().map_or(String::new(), |e| format!("；无尽试炼（难度档 {:?} 开放，每波血量 +{}%，每波最多 {} 件）", e.tiers, e.step * 100.0, e.cap)),
        None => "斗技场试炼（没有 arena.txt，不管）".into(),
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Phase {
    /// 扣了碎片、点了传送请求，等玩家进竞技场
    Going,
    /// 进了竞技场，等着出第一波
    Arrived,
    Fight,
    Ask,
    /// 选了继续，等着出下一波
    Next,
    /// 结算完，等传出去
    Leaving,
}

// ------------------------------------------------------------------ 联机的消息

/// 队员报给房主的：自己现在的情况（每秒一次，变了马上发）
#[derive(Debug, Clone, Default, PartialEq)]
struct Report {
    /// 付了星光碎片（拿奖励）
    paid: bool,
    inside: bool,
    /// 就绪了的那一波
    bound: Option<usize>,
    dead: bool,
    /// 试炼对他来说结束了（离开了竞技场 / 倒下后复活在外面）
    out: bool,
    /// 回答了第几波打完以后继续不继续
    ans: Option<(usize, bool)>,
    /// 不来了的原因（空 = 来）
    no: String,
}

impl Report {
    fn packet(&self, id: u64) -> Packet {
        Packet::new(Kind::Arena)
            .with("op", "me")
            .with("id", id)
            .with("paid", self.paid as u8)
            .with("in", self.inside as u8)
            .with("bound", self.bound.map_or(-1, |w| w as i64))
            .with("dead", self.dead as u8)
            .with("out", self.out as u8)
            .with("ans", self.ans.map_or("-".to_string(), |(w, y)| format!("{w}:{}", y as u8)))
            .with("no", &self.no)
    }

    fn decode(pk: &Packet) -> Option<(u64, Report)> {
        let b = |k: &str| pk.get(k) == Some("1");
        let ans = pk.get("ans").and_then(|a| {
            let (w, y) = a.split_once(':')?;
            Some((w.parse().ok()?, y == "1"))
        });
        Some((pk.get("id")?.parse().ok()?, Report {
            paid: b("paid"),
            inside: b("in"),
            bound: pk.get("bound").and_then(|x| x.parse::<i64>().ok()).filter(|&w| w >= 0).map(|w| w as usize),
            dead: b("dead"),
            out: b("out"),
            ans,
            no: pk.get("no").unwrap_or("").to_string(),
        }))
    }
}

/// 房主发给队员的进度（每秒一次，变了马上发）
#[derive(Debug, Clone, Default, PartialEq)]
struct HostState {
    id: u64,
    x: u32,
    v: u32,
    code: usize,
    /// 出场顺序：每一波的部件 k
    lineup: Vec<Vec<u32>>,
    /// going 房主还在传送 / wait 等人进场 / fight / ask / next / end
    ph: String,
    w: usize,
    /// 第 w 波出场了
    spawned: bool,
    /// 第 w 波开打了
    go: bool,
    /// 打完了几波
    clr: usize,
    /// 问的是你（每个队员单独发）
    ask: bool,
    /// 结束的原因：clear 打完 / leave 选了离开 / abort 没做成（退碎片）/ wipe 全队倒下 / host_out 房主离开了竞技场
    why: String,
    /// 无尽试炼：从第几波开始（0 = 不是无尽；旧版房主不发，当 0）
    e: u32,
}

impl HostState {
    fn packet(&self) -> Packet {
        let l: Vec<String> = self.lineup.iter().map(|w| w.iter().map(|k| k.to_string()).collect::<Vec<_>>().join(".")).collect();
        Packet::new(Kind::Arena)
            .with("op", "state")
            .with("id", self.id)
            .with("x", self.x)
            .with("v", self.v)
            .with("code", self.code)
            .with("l", l.join("/"))
            .with("ph", &self.ph)
            .with("w", self.w)
            .with("spawned", self.spawned as u8)
            .with("go", self.go as u8)
            .with("clr", self.clr)
            .with("ask", self.ask as u8)
            .with("why", &self.why)
            .with("e", self.e)
    }

    fn decode(pk: &Packet) -> Option<HostState> {
        let n = |k: &str| pk.get(k).and_then(|x| x.parse::<u64>().ok());
        let mut lineup = Vec::new();
        for w in pk.get("l")?.split('/').filter(|w| !w.is_empty()) {
            lineup.push(w.split('.').map(|k| k.parse::<u32>().ok()).collect::<Option<Vec<u32>>>()?);
        }
        Some(HostState {
            id: n("id")?,
            x: n("x")? as u32,
            v: n("v")? as u32,
            code: n("code")? as usize,
            lineup,
            ph: pk.get("ph")?.to_string(),
            w: n("w")? as usize,
            spawned: pk.get("spawned") == Some("1"),
            go: pk.get("go") == Some("1"),
            clr: n("clr")? as usize,
            ask: pk.get("ask") == Some("1"),
            why: pk.get("why").unwrap_or("").to_string(),
            e: n("e").unwrap_or(0) as u32,
        })
    }
}

/// 出场顺序：部件下标 → k（发给队员）
fn lineup_ks(c: &Colo, lineup: &[Vec<usize>]) -> Vec<Vec<u32>> {
    lineup.iter().map(|w| w.iter().map(|&i| c.parts[i].k).collect()).collect()
}

/// 出场顺序：k → 部件下标（收到的；有对不上的 None）
fn lineup_idx(c: &Colo, ks: &[Vec<u32>]) -> Option<Vec<Vec<usize>>> {
    ks.iter().map(|w| w.iter().map(|k| c.parts.iter().position(|p| p.k == *k)).collect::<Option<Vec<usize>>>()).collect()
}

struct Mate {
    id: u64,
    rep: Option<Report>,
    /// 最近一次收到他的消息（开始时 = 开始的时间）
    at: Instant,
    /// 上次发给他的进度（内容, 时间）
    sent: Option<(Packet, Instant)>,
}

impl Mate {
    fn lost(&self, now: Instant) -> bool {
        now.duration_since(self.at) > MATE_LOST
    }

    /// 进场有结果了（进来了 / 不来 / 出去了 / 断了）
    fn settled(&self, now: Instant) -> bool {
        self.lost(now) || self.rep.as_ref().is_some_and(|r| r.inside || r.out || !r.no.is_empty())
    }

    /// 在竞技场里、活着
    fn alive(&self, now: Instant) -> bool {
        !self.lost(now) && self.rep.as_ref().is_some_and(|r| r.inside && !r.out && !r.dead && r.no.is_empty())
    }

    fn name(&self) -> String {
        format!("队员 …{:04}", self.id % 10000)
    }
}

enum Role {
    Solo,
    Host {
        mates: Vec<Mate>,
        /// 问继续问的是哪个队员（None = 房主自己）、从什么时候问的
        asking: Option<(u64, Instant)>,
    },
    Client {
        host: u64,
        /// 付了碎片（拿奖励）
        paid: bool,
        /// 最近一次收到房主的进度
        seen: Instant,
        hs: HostState,
        /// 回答了第几波打完以后继续不继续
        ans: Option<(usize, bool)>,
        /// 上次报的（内容, 时间）
        sent: Option<(Packet, Instant)>,
    },
}

struct Run {
    /// d.colos 的下标
    ci: usize,
    /// 从哪个雕像进来（离开标记 + v）
    v: u32,
    /// 场次（1 起）
    code: usize,
    waves: usize,
    cost: u32,
    bonus: u32,
    /// 全部打完退还的星光碎片（用户 2026-11-10：花 1 个的不退，2 个退 1，3 个退 2；开发工具直接进的也照场次退，方便测试）
    refund: u32,
    /// 每一波出场的部件（d.colos[ci].parts 的下标）
    lineup: Vec<Vec<usize>>,
    wave: usize,
    phase: Phase,
    at: Instant,
    diff: usize,
    /// 这次试炼发进背包的道具：(道具编号, 个数)（未鉴定物品、骨灰容器；死了照这个收回）
    given: Vec<(u32, u32)>,
    n_items: u32,
    n_ashes: u32,
    /// 在竞技场里真的死过（death_tick）：离开竞技场时按失败处理
    died: bool,
    /// 血量到 0 的时间（还没认定死没死）
    zero_at: Option<Instant>,
    checked: bool,
    /// 这一次问继续的标记点亮过了（at = 点亮的时间）
    asked: bool,
    /// 太快回「否」重新问过几次
    reasks: u32,
    left: bool,
    /// 联机的这次试炼编号（房主排的，队员照用）
    nonce: u64,
    role: Role,
    /// 本机出场了的那一波、出场的时间
    spawned: Option<usize>,
    spawned_at: Option<Instant>,
    /// 这一波点亮了开打
    engaged: bool,
    /// 本机这一波就绪了（队员报给房主）
    bound: Option<usize>,
    /// 这一波的敌人：看到活着的 / 认定死了的（部件 k；死亡标记亮了，或者看到它活过、血量又到 0）
    seen_alive: HashSet<u32>,
    dead_k: HashSet<u32>,
    /// 打完了几波（发了奖励的）
    cleared: usize,
    /// 结束的原因（联机发给队员）
    why: &'static str,
    /// 开发工具直接进的（生成器的详细记录只在这种试炼里写）
    dev: bool,
    /// 无尽试炼：这一场从第几波开始（第 i 波（下标）是第 endless + i 波）；0 = 不是无尽
    endless: u32,
}

/// 结束了的联机试炼（队员这边）：房主还在发这一场的进度时，回报最后的情况（最多记几场）
struct Done {
    id: u64,
    host: u64,
    rep: Report,
    sent: Option<Instant>,
}

struct St {
    next: Instant,
    rng: u64,
    run: Option<Run>,
    away: Option<Instant>,
    stuck: Option<Instant>,
    /// 失败后要收回的道具（等发货队列发完、人物读进来再扣）
    takeback: Vec<(u32, u32)>,
    /// 竞技场里的提示排队：(竞技场下标, 编号)
    notes: Vec<(usize, u32)>,
    /// 进存档后看过一次 arena_run.txt
    run_file_seen: bool,
    /// 联机：房主新开的一场（队员这边，等人物在场再接）
    offer: Option<(u64, HostState)>,
    done: Vec<Done>,
    /// 联机：房主结束以后接着发的「结束」：(进度, 发给谁, 到什么时候, 上次发的时间)
    end_resend: Option<(Packet, Vec<u64>, Instant, Instant)>,
    /// 生成器实验的记录
    genw: GenWatch,
    /// 进场后等敌人都读进来再记一行（竞技场下标, 进场的时间）：池子做大（用户 2026-11-19「先试试32种敌人和boss」）看读图快慢、内存
    load_watch: Option<(usize, Instant)>,
    /// 无尽试炼的进度（这个角色的）
    prog: Prog,
}

/// 无尽试炼的进度：每个角色、每个竞技场「下次从第几波开始、最高打完第几波」，存在角色记录 无尽进度_<格子>.txt
#[derive(Default)]
struct Prog {
    who: Option<(i32, String)>,
    /// 竞技场 x → (下次从第几波开始, 最高打完第几波)
    by_x: HashMap<u32, (u32, u32)>,
    /// 上次交给菜单的（标记、文字），变了才重写
    shown: String,
}

static ST: Mutex<Option<St>> = Mutex::new(None);
/// 联机通道收到的斗技场消息（link.rs 放进来，tick 里处理）：(谁发的, 是不是房主, 消息)
static INBOX: Mutex<Vec<(u64, bool, Packet)>> = Mutex::new(Vec::new());

/// link.rs：收到斗技场的消息（档案一致的队员发来的）
pub fn net_in(from: u64, from_host: bool, pk: Packet) {
    let mut q = INBOX.lock().unwrap_or_else(|e| e.into_inner());
    if q.len() < 64 {
        q.push((from, from_host, pk));
    }
}

impl St {
    fn roll(&mut self) -> u64 {
        self.rng = self.rng.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.rng;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn below(&mut self, n: usize) -> usize {
        if n == 0 {
            0
        } else {
            (self.roll() % n as u64) as usize
        }
    }

    /// 按权重挑一个下标（全是 0 就 0）
    fn weighted(&mut self, w: &[f32]) -> usize {
        let total: f32 = w.iter().map(|x| x.max(0.0)).sum();
        if total <= 0.0 {
            return 0;
        }
        let mut r = (self.roll() % 1_000_000) as f32 / 1_000_000.0 * total;
        for (i, x) in w.iter().enumerate() {
            r -= x.max(0.0);
            if r < 0.0 {
                return i;
            }
        }
        w.len() - 1
    }

    fn fresh(rng: u64) -> St {
        St {
            next: Instant::now(),
            rng,
            run: None,
            away: None,
            stuck: None,
            takeback: Vec::new(),
            notes: Vec::new(),
            run_file_seen: false,
            offer: None,
            done: Vec::new(),
            end_resend: None,
            genw: GenWatch::default(),
            load_watch: None,
            prog: Prog::default(),
        }
    }
}

/// 进场后最多等敌人读进来多久（到时还没全读进来也记一行）
const LOAD_WATCH: Duration = Duration::from_secs(20);

#[repr(C)]
#[derive(Default)]
struct ProcMem {
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
struct SysMem {
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

#[link(name = "kernel32")]
unsafe extern "system" {
    fn K32GetProcessMemoryInfo(h: isize, c: *mut ProcMem, cb: u32) -> i32;
    fn GlobalMemoryStatusEx(s: *mut SysMem) -> i32;
}

/// 「游戏内存 x GB（工作集 y GB），系统可用 z GB」，同性能记录的写法（提交的私有内存）
fn mem_note() -> String {
    let gb = |b: u64| format!("{:.2} GB", b as f64 / (1u64 << 30) as f64);
    let mut p = ProcMem { cb: size_of::<ProcMem>() as u32, ..ProcMem::default() };
    let mut s = SysMem { len: size_of::<SysMem>() as u32, ..SysMem::default() };
    let game = if unsafe { K32GetProcessMemoryInfo(-1, &mut p, p.cb) } != 0 {
        format!("游戏内存 {}（工作集 {}）", gb(p.private as u64), gb(p.working_set as u64))
    } else {
        "游戏内存读不到".to_string()
    };
    let sys = if unsafe { GlobalMemoryStatusEx(&mut s) } != 0 { format!("，系统可用 {}", gb(s.avail_phys)) } else { String::new() };
    game + &sys
}

/// 这个角色在 ChrSet 条目里的状态字节（按字节读，不当枚举用）：0 没读进来、1 正在建、2 / 4 在场（游戏里稳定在场的是 4）、5 正在拆。
/// 条目不指回它就 None
fn load_status(c: &eldenring::cs::ChrIns) -> Option<u8> {
    let e = c.chr_set_entry.as_ptr() as *const u8;
    if e.is_null() || unsafe { (e as *const usize).read() } != c as *const _ as usize {
        return None;
    }
    Some(unsafe { e.add(std::mem::offset_of!(eldenring::cs::ChrSetEntry<eldenring::cs::ChrIns>, chr_load_status)).read() })
}

/// 进场以后：竞技场的敌人都真的读进来了（ChrSet 条目状态 2 / 4），或者等了 LOAD_WATCH，记一行。
/// 2026-11-19 98 只、57 种模型那次：条目都在（以前这里按条目数记成 98 / 98），实际 41 只一直是 0（没读进来），出场的看不见
fn load_watch_tick(d: &Def, st: &mut St, wcm: &WorldChrMan, in_ci: Option<usize>, now: Instant) {
    let Some((ci, at)) = st.load_watch else { return };
    if in_ci != Some(ci) {
        st.load_watch = None;
        return;
    }
    let c = &d.colos[ci];
    let by_ent: HashMap<u32, &Part> = c.parts.iter().map(|p| (p.ent, p)).collect();
    let mut stat: HashMap<u32, Option<u8>> = HashMap::new();
    for s in wcm.chr_sets.iter().flatten() {
        for ch in s.characters() {
            if by_ent.contains_key(&ch.event_entity_id) {
                stat.insert(ch.event_entity_id, load_status(ch));
            }
        }
    }
    let loaded = stat.values().filter(|s| matches!(s, Some(2) | Some(4))).count();
    let waited = now - at;
    if loaded < c.parts.len() && waited < LOAD_WATCH {
        return;
    }
    st.load_watch = None;
    let mut hist: Vec<(String, usize)> = Vec::new();
    for s in stat.values() {
        let key = s.map_or("对不上".to_string(), |v| v.to_string());
        match hist.iter_mut().find(|h| h.0 == key) {
            Some(h) => h.1 += 1,
            None => hist.push((key, 1)),
        }
    }
    hist.sort();
    let missing: Vec<String> = c.parts.iter().filter(|p| !matches!(stat.get(&p.ent), Some(Some(2)) | Some(Some(4))))
        .map(|p| format!("{}{} {}（{}）", if p.boss { "B" } else if p.scarab { "S" } else { "E" }, p.k, p.name,
                         stat.get(&p.ent).map_or("没有条目".to_string(), |s| s.map_or("对不上".to_string(), |v| format!("状态 {v}")))))
        .collect();
    let models: HashSet<&str> = c.parts.iter().map(|p| p.name.split('_').next().unwrap_or("")).collect();
    log(&format!("竞技场：进场后 {:.1} 秒，竞技场的敌人真的读进来 {loaded} / {} 个（{} 种模型；状态 {}）{}；{}", waited.as_secs_f32(), c.parts.len(), models.len(),
                 hist.iter().map(|(k, n)| format!("{k}×{n}")).collect::<Vec<_>>().join(" "),
                 if missing.is_empty() { String::new() } else { format!("，没读进来的 {} 个：{}", missing.len(), missing.join("、")) }, mem_note()));
}

/// 出场顺序：偶数波（第 1、3…波）精英 per 个，奇数波 Boss 一个（整场不重复）；哪种用完了就用另一种。
/// 同一波的精英种类（部件名，同种的副本照抄同一个敌人）不重复、站位不重复（同种的副本站同一个位置），先挑剩得多的种类（用户 2026-11-10）。
/// 每个精英位有 scarab% 换成粪金龟（红、蓝各占一个站位，洗过的顺序里先到先用）；这一波只剩最后一位、前面都是粪金龟的，这一位不换
fn lineup(d: &Def, c: &Colo, waves: usize, st: &mut St) -> Vec<Vec<usize>> {
    let mut bosses: Vec<usize> = (0..c.parts.len()).filter(|&i| c.parts[i].boss).collect();
    let mut elites: Vec<usize> = (0..c.parts.len()).filter(|&i| !c.parts[i].boss && !c.parts[i].scarab).collect();
    let mut scarabs: Vec<usize> = (0..c.parts.len()).filter(|&i| c.parts[i].scarab).collect();
    for v in [&mut bosses, &mut elites, &mut scarabs] {
        for i in (1..v.len()).rev() {
            let j = st.below(i + 1);
            v.swap(i, j);
        }
    }
    let mut out = Vec::new();
    for w in 0..waves {
        let want_elite = w % 2 == 0;
        let mut wave: Vec<usize> = Vec::new();
        if (want_elite && !elites.is_empty()) || bosses.is_empty() {
            let mut names: HashSet<&str> = HashSet::new();
            let mut spots = HashSet::new();
            while wave.len() < d.per.max(1) {
                let real = wave.iter().any(|&m| !c.parts[m].scarab);
                let last = wave.len() + 1 >= d.per.max(1);
                if d.scarab > 0.0 && (real || !last) && (st.roll() % 10_000) < (d.scarab * 100.0).round() as u64 {
                    if let Some(i) = scarabs.iter().position(|&s| !spots.contains(&c.parts[s].spot)) {
                        let s = scarabs.remove(i);
                        spots.insert(c.parts[s].spot);
                        wave.push(s);
                        continue;
                    }
                }
                // 还能用的种类里剩得最多的（同样多的按洗过的顺序）
                let mut best: Option<(usize, usize)> = None;
                for (i, &e) in elites.iter().enumerate() {
                    let p = &c.parts[e];
                    if names.contains(p.name.as_str()) || spots.contains(&p.spot) {
                        continue;
                    }
                    let left = elites.iter().filter(|&&o| c.parts[o].name == p.name).count();
                    if best.is_none_or(|(_, l)| left > l) {
                        best = Some((i, left));
                    }
                }
                let Some((i, _)) = best else { break };
                let e = elites.remove(i);
                names.insert(c.parts[e].name.as_str());
                spots.insert(c.parts[e].spot);
                wave.push(e);
            }
        } else if let Some(b) = bosses.pop() {
            wave.push(b);
        }
        if wave.is_empty() {
            break;
        }
        out.push(wave);
    }
    out
}

fn diff_now(d: &Def) -> usize {
    match d.diff {
        Some((cur0, n, normal)) => (0..n as u32).find(|&k| flag_get(cur0 + k) == Some(true)).map_or(normal, |k| k as usize),
        None => 2,
    }
}

fn mult(d: &Def, diff: usize) -> [f32; 4] {
    d.dmult.get(diff).copied().unwrap_or([1.0; 4])
}

/// 一件未鉴定物品：(道具编号, 类别)；稀有度固定（rew 行），类别按 cat 抽
fn roll_item(d: &Def, tier: usize, st: &mut St) -> (i32, usize) {
    let cat = st.weighted(&d.cat);
    (d.goods0 + 10 * cat as i32 + tier as i32, cat)
}

/// 这一波的未鉴定物品：(稀有度, 件数)。第 j 个同类波（精英波 / Boss 波分开数）给 items × j × 倍率（用户 2026-11-10：
/// 宁姆格福第 1 波 2 件史诗、第 2 波 1 件传说 + 骨灰、第 3 波 4 件史诗、第 4 波 2 件传说 + 骨灰，往后线性外推）
fn wave_items(d: &Def, c: &Colo, lineup: &[Vec<usize>], wave: usize, diff: usize) -> (usize, u32) {
    let is_boss = |w: &Vec<usize>| w.iter().any(|&m| c.parts[m].boss);
    let boss = is_boss(&lineup[wave]);
    let j = lineup[..=wave].iter().filter(|w| is_boss(w) == boss).count() as u32;
    let base = if boss { d.items_b } else { d.items_e };
    (rew_tiers(d, c, diff)[boss as usize], base * j * c.scale.max(1))
}

/// 这个竞技场的未鉴定物品稀有度 [精英波, Boss 波]：试炼开始时的难度是 lockrew 的档（死亡以上）就都用 lockrew 的稀有度，否则照 rew 行
fn rew_tiers(d: &Def, c: &Colo, diff: usize) -> [usize; 2] {
    match &d.lockrew {
        Some((t, ds)) if ds.contains(&diff) => [*t, *t],
        _ => c.tiers,
    }
}

fn roll_ash(d: &Def, c: &Colo, diff: usize, st: &mut St) -> usize {
    let m = mult(d, diff);
    let w: Vec<f32> = (0..4).map(|r| c.ashrar[r] * m[r]).collect();
    st.weighted(&w)
}

/// 记下发进背包的一件（死了照这个收回）
fn add_given(r: &mut Run, id: u32) {
    match r.given.iter_mut().find(|x| x.0 == id) {
        Some(x) => x.1 += 1,
        None => r.given.push((id, 1)),
    }
}

/// 发一件未鉴定物品进背包：走发货表，只进边上的获得记录、不弹屏幕中间的框（用户 2026-11-22「竞技场的奖励发放都走不弹窗」→
/// 「可以是不弹屏幕中间的框只弹边上的框吗」；gear.rs 的 gift_log）。斗技场发的东西（奖励、退还的星光碎片、骨灰）都这样发
fn give_item(r: &mut Run, id: i32) -> bool {
    if gift_log(id as u32, 1) {
        add_given(r, id as u32);
        r.n_items += 1;
        true
    } else {
        false
    }
}

fn note(d: &Def, st: &mut St, ci: usize, key: &str) {
    match d.notes.get(key) {
        Some(&v) => st.notes.push((ci, v)),
        None => log(&format!("竞技场：arena.txt 里没有提示「{key}」")),
    }
}

fn save_run(c: &Colo, v: u32) {
    let _ = fs::write(dir().join(RUN_FILE), format!("{} {}\n", c.x, v));
}

fn clear_run_file() {
    let _ = fs::remove_file(dir().join(RUN_FILE));
}

fn load_run() -> Option<(u32, u32)> {
    let t = fs::read_to_string(dir().join(RUN_FILE)).ok()?;
    let mut it = t.split_whitespace().filter_map(|x| x.parse::<u32>().ok());
    Some((it.next()?, it.next()?))
}

/// 雕像对话的请求
fn request(d: &Def, st: &mut St, blk: [u8; 4], now: Instant) {
    let code = (flag_get(d.len[0]) == Some(true)) as usize | ((flag_get(d.len[1]) == Some(true)) as usize) << 1;
    let done = |why: &str| {
        flag_set(d.req, false);
        if let Some(e) = &d.endless {
            flag_set(e.req, false);
        }
        log(&format!("竞技场：{why}"));
    };
    if st.run.is_some() {
        return done("已经在试炼中，不接新的请求");
    }
    // 雕像菜单在会话里不给队员开始（sc/arena.py）；万一是旧的菜单
    if crate::coop::client() {
        return done("联机时由房主开始试炼，本机是队员，不接（没扣碎片）");
    }
    let Some((ci, v)) = d.colos.iter().enumerate().find_map(|(ci, c)| c.statues.iter().find(|s| s.1 == blk).map(|s| (ci, s.0))) else {
        return done(&format!("请求时玩家在地图 m{}_{:02}_{:02}_{:02}，不是竞技场雕像所在的地图，不管", blk[0], blk[1], blk[2], blk[3]));
    };
    // 无尽试炼（菜单另外点亮了无尽的请求；场次位 1 = 继续、2 = 从第 1 波开始）：不花碎片
    if let Some(e) = d.endless.as_ref().filter(|e| flag_get(e.req) == Some(true)) {
        flag_set(e.req, false);
        let diff = diff_now(d);
        if !e.tiers.contains(&diff) {
            return done(&format!("无尽试炼只在死亡以上难度开放（现在是第 {diff} 档）"));
        }
        let x = d.colos[ci].x;
        let (next, best) = st.prog.by_x.get(&x).copied().unwrap_or((1, 0));
        let start = if code == 1 {
            next.max(1)
        } else {
            if next > 1 {
                st.prog.by_x.insert(x, (1, best));
                prog_save(&st.prog);
            }
            1
        };
        flag_set(d.req, false);
        let how = format!("从雕像 {v}（m{}_{:02}_{:02}_{:02}）进无尽试炼，{}", blk[0], blk[1], blk[2], blk[3],
                          if code == 1 { format!("从保存的第 {start} 波继续") } else { "从第 1 波开始".to_string() });
        start_endless(d, st, ci, v, start, &how, now);
        return;
    }
    let Some(&(_, cost, _, _)) = code.checked_sub(1).and_then(|i| d.runs.get(i)) else {
        return done(&format!("场次位 {code} 不对"));
    };
    let Ok(gdm) = (unsafe { GameDataMan::instance_mut() }) else { return };
    let pgd = &mut gdm.main_player_game_data;
    let have = count_goods(pgd, d.shard);
    if have < cost {
        return done(&format!("星光碎片 {have} 个，不够 {cost} 个（对话里已经看过，多半是刚好用掉了）"));
    }
    let got = remove_goods(pgd, d.shard, cost);
    if got != cost {
        if got > 0 {
            gift_log(d.shard, got);
        }
        return done(&format!("扣星光碎片失败（扣到 {got} / {cost}），已退回"));
    }
    flag_set(d.req, false);
    start_run(d, st, ci, v, code, cost, &format!("从雕像 {v}（m{}_{:02}_{:02}_{:02}）进，扣 {cost} 个星光碎片（剩 {}）", blk[0], blk[1], blk[2], blk[3], have - cost), now);
}

/// 点亮传送请求（场次位改成竞技场编号 + 1，公共事件把玩家传进去）
fn warp_in(d: &Def, c: &Colo) {
    let to = c.x as usize + 1;
    flag_set(d.len[0], to & 1 == 1);
    flag_set(d.len[1], to & 2 == 2);
    flag_set(d.warp, true);
}

fn new_run(ci: usize, v: u32, code: usize, cost: u32, lineup: Vec<Vec<usize>>, run: (usize, u32, u32, u32), diff: usize, nonce: u64, role: Role, now: Instant) -> Run {
    let (_, _, bonus, refund) = run;
    Run {
        ci,
        v,
        code,
        waves: lineup.len(),
        cost,
        bonus,
        refund,
        lineup,
        wave: 0,
        phase: Phase::Going,
        at: now,
        diff,
        given: Vec::new(),
        n_items: 0,
        n_ashes: 0,
        died: false,
        zero_at: None,
        checked: false,
        asked: false,
        reasks: 0,
        left: false,
        nonce,
        role,
        spawned: None,
        spawned_at: None,
        engaged: false,
        bound: None,
        seen_alive: HashSet::new(),
        dead_k: HashSet::new(),
        cleared: 0,
        why: "end",
        dev: false,
        endless: 0,
    }
}

/// 排好出场、点亮传送请求。在会话里当房主、有连上的队员：带上他们（联机计划 13.13）
fn start_run(d: &Def, st: &mut St, ci: usize, v: u32, code: usize, cost: u32, how: &str, now: Instant) {
    let Some(&run) = code.checked_sub(1).and_then(|i| d.runs.get(i)) else { return };
    let c = &d.colos[ci];
    warp_in(d, c);
    let diff = diff_now(d);
    let lineup = lineup(d, c, run.0, st);
    let names: Vec<String> = lineup
        .iter()
        .map(|w| w.iter().map(|&i| c.parts[i].name.clone()).collect::<Vec<_>>().join("+"))
        .collect();
    let peers: Vec<u64> = if crate::coop::host() { crate::link::gift_peers().into_iter().map(|p| p.0).collect() } else { Vec::new() };
    let nonce = st.roll() | 1;
    let role = if peers.is_empty() {
        Role::Solo
    } else {
        Role::Host { mates: peers.iter().map(|&id| Mate { id, rep: None, at: now, sent: None }).collect(), asking: None }
    };
    log(&format!(
        "竞技场：{how}，竞技场 {}，{} 波，难度档 {diff}；出场 {}{}",
        c.x,
        lineup.len(),
        names.join(" / "),
        if peers.is_empty() { String::new() } else { format!("；联机房主，带 {} 个队员（试炼 {nonce}）", peers.len()) }
    ));
    save_run(c, v);
    st.run = Some(new_run(ci, v, code, cost, lineup, run, diff, nonce, role, now));
}

/// 开始一场无尽试炼（从第 start 波）：先排好第一波，之后每波开打前现排（endless_extend）
fn start_endless(d: &Def, st: &mut St, ci: usize, v: u32, start: u32, how: &str, now: Instant) {
    let c = &d.colos[ci];
    let start = start.max(1);
    // 没有生成器（arena.txt 没有 gen 行，还没重随）：用过的敌人叫不回来，出场时还是死的，那一波会直接算打完
    if c.revive.is_none() {
        log(&format!("竞技场：{how}：竞技场 {} 没有复活用的生成器（还没重随？），不开无尽试炼", c.x));
        return;
    }
    warp_in(d, c);
    let diff = diff_now(d);
    let first = endless_pick(d, c, &[], start, 0, st);
    let peers: Vec<u64> = if crate::coop::host() { crate::link::gift_peers().into_iter().map(|p| p.0).collect() } else { Vec::new() };
    let nonce = st.roll() | 1;
    let role = if peers.is_empty() {
        Role::Solo
    } else {
        Role::Host { mates: peers.iter().map(|&id| Mate { id, rep: None, at: now, sent: None }).collect(), asking: None }
    };
    let names: Vec<&str> = first.iter().map(|&m| c.parts[m].name.as_str()).collect();
    log(&format!(
        "竞技场：{how}，竞技场 {}，难度档 {diff}；第 {start} 波出场 {}{}",
        c.x,
        names.join("+"),
        if peers.is_empty() { String::new() } else { format!("；联机房主，带 {} 个队员（试炼 {nonce}）", peers.len()) }
    ));
    save_run(c, v);
    let mut r = new_run(ci, v, 0, 0, vec![first], (0, 0, 0, 0), diff, nonce, role, now);
    r.endless = start;
    r.waves = usize::MAX;
    st.run = Some(r);
}

/// 无尽试炼第 i 波（下标；第 start + i 波）出哪几只：偶数波 1 个 Boss，奇数波 d.per 只精英（名字、站位不重复，可能换成粪金龟）。
/// 先挑这一场还没出过的（洗乱），都出过了挑最久没出场的（出场时用它的生成器复活）；粪金龟一场只出一次（钻地跑掉的叫不回来）
fn endless_pick(d: &Def, c: &Colo, lineup: &[Vec<usize>], start: u32, i: usize, st: &mut St) -> Vec<usize> {
    let abs = start + i as u32;
    let last = |m: usize| lineup.iter().rposition(|w| w.contains(&m));
    let order = |pool: Vec<usize>, st: &mut St| -> Vec<usize> {
        let (mut fresh, mut used): (Vec<usize>, Vec<usize>) = pool.into_iter().partition(|&m| last(m).is_none());
        for j in (1..fresh.len()).rev() {
            let k = st.below(j + 1);
            fresh.swap(j, k);
        }
        used.sort_by_key(|&m| last(m));
        fresh.extend(used);
        fresh
    };
    let bosses: Vec<usize> = (0..c.parts.len()).filter(|&m| c.parts[m].boss).collect();
    if abs % 2 == 0 && !bosses.is_empty() {
        return order(bosses, st).into_iter().take(1).collect();
    }
    let mut rest = order((0..c.parts.len()).filter(|&m| !c.parts[m].boss && !c.parts[m].scarab).collect(), st);
    let mut scarabs: Vec<usize> = (0..c.parts.len()).filter(|&m| c.parts[m].scarab && last(m).is_none()).collect();
    let per = d.per.max(1);
    let (mut wave, mut names, mut spots): (Vec<usize>, HashSet<&str>, HashSet<i32>) = (Vec::new(), HashSet::new(), HashSet::new());
    while wave.len() < per {
        let real = wave.iter().any(|&m| !c.parts[m].scarab);
        let last_slot = wave.len() + 1 >= per;
        if d.scarab > 0.0 && (real || !last_slot) && (st.roll() % 10_000) < (d.scarab * 100.0).round() as u64 {
            if let Some(j) = scarabs.iter().position(|&s| !spots.contains(&c.parts[s].spot)) {
                let s = scarabs.remove(j);
                spots.insert(c.parts[s].spot);
                wave.push(s);
                continue;
            }
        }
        let Some(j) = rest.iter().position(|&m| !names.contains(c.parts[m].name.as_str()) && !spots.contains(&c.parts[m].spot)) else { break };
        let m = rest.remove(j);
        names.insert(c.parts[m].name.as_str());
        spots.insert(c.parts[m].spot);
        wave.push(m);
    }
    if wave.is_empty() && !bosses.is_empty() {
        return order(bosses, st).into_iter().take(1).collect();
    }
    wave
}

/// 无尽试炼：第 i 波还没排就现排（房主 / 单人；队员照房主发来的）
fn endless_extend(d: &Def, st: &mut St, r: &mut Run, i: usize) {
    if r.endless == 0 || matches!(r.role, Role::Client { .. }) {
        return;
    }
    let c = &d.colos[r.ci];
    while r.lineup.len() <= i {
        let w = endless_pick(d, c, &r.lineup, r.endless, r.lineup.len(), st);
        r.lineup.push(w);
    }
}

/// 无尽试炼第 i 波的血量：把血量效果行的 maxHpRate 改成 1 + step × (第几波 − 1)（第 1 波不加；同一时间只有这一波的敌人活着，共用一行）
fn endless_hp(d: &Def, r: &Run, i: usize, why: &str) -> Option<(usize, i32)> {
    let e = d.endless.as_ref()?;
    let abs = r.endless + i as u32;
    if abs < 2 {
        return None;
    }
    let v = 1.0 + e.step * (abs - 1) as f32;
    let ok = unsafe { SoloParamRepository::instance_mut() }.ok().and_then(|repo| repo.get_mut::<SpEffectParam>(e.sp)).map(|s| s.set_max_hp_rate(v)).is_some();
    log(&format!("竞技场：{why}无尽试炼第 {abs} 波，敌人血量 ×{v:.2}（效果 {}{}）", e.sp, if ok { "" } else { "；效果行改不了，这一波不加" }));
    ok.then_some((abs as usize, e.sp as i32))
}

/// 角色记录的文件夹（同 gear.rs：%APPDATA%\EldenRing\DarkReforged\角色记录，联机时是里面的 联机\）
fn rec_dir() -> PathBuf {
    let base = std::env::var_os("APPDATA").map(|a| PathBuf::from(a).join("EldenRing").join("DarkReforged").join("角色记录")).unwrap_or_else(dir);
    if crate::coop::ersc_loaded() { base.join("联机") } else { base }
}

fn prog_path(slot: i32) -> PathBuf {
    rec_dir().join(format!("无尽进度_{slot}.txt"))
}

/// 读进度（第一行「name<TAB>角色名」对不上的不认）：竞技场 → (下次从第几波开始, 最高打完第几波)
fn prog_parse(text: &str, name: &str) -> Option<HashMap<u32, (u32, u32)>> {
    let mut lines = text.lines().map(|l| l.trim_start_matches('\u{feff}').trim_end_matches('\r')).filter(|l| !l.starts_with('#'));
    if lines.next()?.strip_prefix("name\t")? != name {
        return None;
    }
    let mut out = HashMap::new();
    for l in lines {
        let f: Vec<&str> = l.split('\t').collect();
        let num = |i: usize| f.get(i).and_then(|v| v.parse::<u32>().ok());
        if f[0] == "colo" {
            if let (Some(x), Some(next), Some(best)) = (num(1), num(2), num(3)) {
                out.insert(x, (next.max(1), best));
            }
        }
    }
    Some(out)
}

fn prog_save(p: &Prog) {
    let Some((slot, name)) = &p.who else { return };
    let mut s = format!("# 斗技场无尽试炼的进度（dark_core arena.rs）：colo 竞技场 下次从第几波开始 最高打完第几波\nname\t{name}\n");
    let mut xs: Vec<(&u32, &(u32, u32))> = p.by_x.iter().collect();
    xs.sort();
    for (x, (next, best)) in xs {
        s += &format!("colo\t{x}\t{next}\t{best}\n");
    }
    let path = prog_path(*slot);
    let _ = fs::create_dir_all(rec_dir());
    let tmp = path.with_extension("tmp");
    if fs::write(&tmp, s).and_then(|_| fs::rename(&tmp, &path)).is_err() {
        log(&format!("竞技场：无尽试炼的进度记不下来（{}）", path.display()));
    }
}

/// 取文字钩子的占位（「〔#I<种类> …〕」，msghook.rs）
fn set_text(kind: u8, zh: &str, en: &str) {
    crate::msghook::set_confirm(b'I', kind, &zh.encode_utf16().collect::<Vec<u16>>(), &en.encode_utf16().collect::<Vec<u16>>());
}

/// 「第 N 波」（竞技场里的提示「无尽试炼　第〔#IQ …〕波」「下次从第〔#IQ …〕波继续」）
fn endless_wave_text(n: u32) {
    set_text(26, &n.to_string(), &n.to_string());
}

/// 进存档 / 换了角色：读这个角色的无尽进度；变了就把菜单要的交出去：竞技场 X 有进度的标记（列不列「继续」）、
/// 「继续（第 N 波，最高第 M 波）」「从第 1 波开始（最高第 M 波）」的占位（#IK~M、#IN~P，种类 20~25）
fn prog_tick(d: &Def, st: &mut St) {
    let Some(e) = &d.endless else { return };
    let w = crate::who::confirmed();
    if w != st.prog.who {
        st.prog.by_x = w.as_ref().and_then(|(slot, name)| fs::read_to_string(prog_path(*slot)).ok().and_then(|t| prog_parse(&t, name))).unwrap_or_default();
        if let Some((slot, name)) = &w {
            if !st.prog.by_x.is_empty() {
                let mut xs: Vec<String> = st.prog.by_x.iter().map(|(x, (n, b))| format!("竞技场 {x} 下次第 {n} 波、最高 {b}")).collect();
                xs.sort();
                log(&format!("竞技场：格子 {slot}「{name}」的无尽试炼进度：{}", xs.join("；")));
            }
        }
        st.prog.who = w;
        st.prog.shown.clear();
    }
    if st.prog.who.is_none() {
        return;
    }
    let mut v: Vec<(u32, (u32, u32))> = st.prog.by_x.iter().map(|(a, b)| (*a, *b)).collect();
    v.sort();
    let key = format!("{v:?}");
    if key == st.prog.shown {
        return;
    }
    st.prog.shown = key;
    for x in 0..3u32 {
        let (next, best) = st.prog.by_x.get(&x).copied().unwrap_or((1, 0));
        flag_set(e.has0 + x, next > 1);
        let (bz, be) = if best > 0 { (format!("，最高第 {best} 波"), format!(", best wave {best}")) } else { (String::new(), String::new()) };
        set_text(20 + x as u8, &format!("（第 {next} 波{bz}）"), &format!(" (wave {next}{be})"));
        if best > 0 {
            set_text(23 + x as u8, &format!("（最高第 {best} 波）"), &format!(" (best wave {best})"));
        } else {
            set_text(23 + x as u8, "", "");
        }
    }
}

/// 无尽试炼打完一波：更新最高波数（房主 / 单人记自己的）
fn endless_cleared(d: &Def, st: &mut St, r: &Run) {
    if r.endless == 0 || matches!(r.role, Role::Client { .. }) {
        return;
    }
    let x = d.colos[r.ci].x;
    let abs = r.endless + r.wave as u32;
    let e = st.prog.by_x.entry(x).or_insert((1, 0));
    if abs > e.1 {
        e.1 = abs;
        prog_save(&st.prog);
    }
}

/// 无尽试炼选了「否」：保存进度（下次从下一波开始），提示一下
fn endless_save(d: &Def, st: &mut St, r: &Run) {
    if r.endless == 0 || matches!(r.role, Role::Client { .. }) {
        return;
    }
    let x = d.colos[r.ci].x;
    let next = r.endless + r.wave as u32 + 1;
    let e = st.prog.by_x.entry(x).or_insert((1, 0));
    e.0 = next;
    e.1 = e.1.max(next - 1);
    prog_save(&st.prog);
    endless_wave_text(next);
    note(d, st, r.ci, "endless saved");
    log(&format!("竞技场：无尽试炼保存进度，下次从第 {next} 波开始"));
}

/// 队员：接下房主新开的一场（人物在场才接）。不接的原因写进 Err
fn client_join(d: &Def, st: &mut St, host: u64, hs: HostState, hp: i32, now: Instant) -> Result<(), String> {
    if !crate::coop::client() {
        return Err("本机不是队员".into());
    }
    if st.run.is_some() {
        return Err("你已经在另一场试炼里".into());
    }
    if hp <= 0 {
        return Err("你倒下了".into());
    }
    if hs.ph != "going" && hs.ph != "wait" {
        return Err(format!("试炼已经开打了（{}）", hs.ph));
    }
    let ci = d.colos.iter().position(|c| c.x == hs.x).ok_or(format!("没有竞技场 {}", hs.x))?;
    let c = &d.colos[ci];
    // 无尽试炼：不花碎片，出场顺序照房主每波发来的
    if hs.e > 0 {
        let lineup = lineup_idx(c, &hs.lineup).filter(|l| !l.is_empty()).ok_or("出场顺序和本机的竞技场对不上")?;
        if !c.statues.iter().any(|s| s.0 == hs.v) {
            return Err(format!("没有雕像 {}", hs.v));
        }
        warp_in(d, c);
        save_run(c, hs.v);
        crate::notes::push("arena coop join");
        let diff = diff_now(d);
        log(&format!("竞技场：房主开始了无尽试炼（试炼 {}），竞技场 {}，从第 {} 波；传进竞技场", hs.id, c.x, hs.e));
        let (id, v, e) = (hs.id, hs.v, hs.e);
        let role = Role::Client { host, paid: true, seen: now, hs, ans: None, sent: None };
        let mut r = new_run(ci, v, 0, 0, lineup, (0, 0, 0, 0), diff, id, role, now);
        r.endless = e;
        r.waves = usize::MAX;
        st.run = Some(r);
        return Ok(());
    }
    let run = *hs.code.checked_sub(1).and_then(|i| d.runs.get(i)).ok_or(format!("场次 {} 不对", hs.code))?;
    let lineup = lineup_idx(c, &hs.lineup).filter(|l| !l.is_empty()).ok_or("出场顺序和本机的竞技场对不上")?;
    if !c.statues.iter().any(|s| s.0 == hs.v) {
        return Err(format!("没有雕像 {}", hs.v));
    }
    let Ok(gdm) = (unsafe { GameDataMan::instance_mut() }) else { return Err("读不到背包".into()) };
    let pgd = &mut gdm.main_player_game_data;
    let cost = run.1;
    let have = count_goods(pgd, d.shard);
    let mut paid = false;
    if have >= cost {
        let got = remove_goods(pgd, d.shard, cost);
        if got == cost {
            paid = true;
        } else if got > 0 {
            gift_log(d.shard, got);
        }
    }
    warp_in(d, c);
    save_run(c, hs.v);
    crate::notes::push("arena coop join");
    if !paid {
        crate::notes::push("arena coop helper");
    }
    let diff = diff_now(d);
    log(&format!(
        "竞技场：房主开始了斗技场试炼（试炼 {}），竞技场 {}，{} 波；{}，传进竞技场",
        hs.id,
        c.x,
        lineup.len(),
        if paid { format!("扣 {cost} 个星光碎片（剩 {}）", have - cost) } else { format!("星光碎片 {have} 个不够 {cost} 个，这次只能帮忙、不拿奖励") }
    ));
    let (id, v, code) = (hs.id, hs.v, hs.code);
    let role = Role::Client { host, paid, seen: now, hs, ans: None, sent: None };
    let mut r = new_run(ci, v, code, if paid { cost } else { 0 }, lineup, run, diff, id, role, now);
    if !paid {
        (r.bonus, r.refund) = (0, 0);
    }
    st.run = Some(r);
    Ok(())
}

/// 按波次挂效果的几率用的随机数：只看试炼编号（房主开场时抽、发给队员）、第几波、实体编号、第几条规则，
/// 两台电脑算出来一样（敌人身上的效果两边各挂各的，联机计划 13.2 G2；房主和队员各自 st.roll() 会对不上）
fn fx_roll(nonce: u64, wave: usize, ent: u32, rule: usize) -> u64 {
    let mut z = nonce ^ (wave as u64) << 48 ^ (rule as u64) << 32 ^ ent as u64;
    // splitmix64
    z = z.wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

fn start_wave(d: &Def, st: &mut St, r: &mut Run, i: usize, now: Instant) {
    let c = &d.colos[r.ci];
    r.wave = i;
    r.phase = Phase::Fight;
    r.at = now;
    r.checked = false;
    r.spawned = Some(i);
    r.spawned_at = Some(now);
    r.engaged = false;
    r.bound = None;
    r.seen_alive.clear();
    r.dead_k.clear();
    let members = r.lineup[i].clone();
    // 开打标记先熄灭（上一波点亮过），出场的这一波读进来了再点亮；旧的竞技场事件没有开打标记，出场就打
    if d.engage > 0 {
        flag_set(c.flag + d.engage, false);
    } else {
        r.engaged = true;
    }
    let mut back: Vec<&str> = Vec::new();
    for &m in &members {
        let p = &c.parts[m];
        // 无尽试炼：这一场出过的（死了）用它的生成器复活：死亡、就绪标记先熄掉，竞技场的复活事件复活以后再点亮
        if r.endless > 0 && r.lineup[..i].iter().any(|w| w.contains(&m)) {
            if let Some((req0, _)) = c.revive {
                flag_set(c.flag + d.dead + p.k, false);
                if d.ready > 0 {
                    flag_set(c.flag + d.ready + p.k, false);
                }
                flag_set(req0 + p.k, true);
                back.push(p.name.as_str());
                continue;
            }
        }
        flag_set(c.flag + d.spawn + p.k, true);
    }
    if let Some(e) = &d.endless {
        flag_set(c.flag + e.local, r.endless > 0);
    }
    crate::foefx::release(FX_TAG);
    wave_effects(d, r, i, &members, "");
    let names: Vec<&str> = members.iter().map(|&m| c.parts[m].name.as_str()).collect();
    if r.endless > 0 {
        let abs = r.endless + i as u32;
        endless_wave_text(abs);
        let boss = members.iter().any(|&m| c.parts[m].boss);
        note(d, st, r.ci, if boss { "endless boss" } else { "endless elite" });
        log(&format!("竞技场：无尽试炼第 {abs} 波出场 {}{}", names.join("、"), if back.is_empty() { String::new() } else { format!("（复活：{}）", back.join("、")) }));
    } else {
        note(d, st, r.ci, &format!("wave {} {}", r.waves, i + 1));
        log(&format!("竞技场：第 {} / {} 波出场 {}", i + 1, r.waves, names.join("、")));
    }
}

/// 第 i 波的这些部件（d.colos[r.ci].parts 的下标）要挂的：血量随波次（粪金龟不挂）+ 命中的 wfx 规则的效果包，交给敌人效果模块
/// （出场后挂上、上限变了按比例补血；效果没了它自己补挂），精英登记魇化。出场时用；生成器实验复活时也用（复活会清掉身上全部效果，
/// 清场时这一波已经从敌人效果模块、魇化里放掉了，要重新登记；why 写进日志）
fn wave_effects(d: &Def, r: &Run, i: usize, members: &[usize], why: &str) {
    let c = &d.colos[r.ci];
    let hp_sp = if r.endless > 0 {
        endless_hp(d, r, i, why)
    } else {
        d.hpwave.and_then(|(every, sp0, count)| {
            let step = (i / every).min(count);
            (step > 0).then(|| (step, sp0 + step as i32 - 1))
        })
    };
    if let Some((step, sp)) = hp_sp.filter(|_| r.endless == 0) {
        log(&format!("竞技场：{why}第 {} 波敌人血量加成第 {step} 档（效果 {sp}）", i + 1));
    }
    for &m in members {
        let p = &c.parts[m];
        let mut fx = Fx::default();
        if let Some((_, sp)) = hp_sp.filter(|_| !p.scarab) {
            fx.add(&Fx::sp(sp));
        }
        let mut got: Vec<&str> = Vec::new();
        for (ri, w) in d.wfx.iter().enumerate() {
            if !w.matches(c.x, r.waves, i + 1, p) || fx_roll(r.nonce, i, p.ent, ri) % 10_000 >= (w.chance * 100.0).round() as u64 {
                continue;
            }
            for name in &w.packs {
                match crate::foefx::pack(name) {
                    Some(f) => {
                        fx.add(&f);
                        got.push(name);
                    }
                    None => log(&format!("竞技场：第 {} 条按波次挂的效果要的效果包「{name}」没有定义（foefx.txt），不挂", ri + 1)),
                }
            }
        }
        if !got.is_empty() {
            log(&format!("竞技场：{why}第 {} 波 {} 挂效果包 {}（效果 {:?}，动作速度 ×{:.2}）", i + 1, p.name, got.join("、"), fx.sps, fx.speed));
        }
        crate::foefx::attach(FX_TAG, p.ent, &fx);
    }
    // 队员这边也登记：nightmare.rs 看到是队员，不自己抽，等房主广播的词条
    let elites: Vec<u32> = members.iter().filter(|&&m| !c.parts[m].boss && !c.parts[m].scarab).map(|&m| c.parts[m].ent).collect();
    if !elites.is_empty() {
        crate::nightmare::force(&elites, d.two.get(r.diff).copied().unwrap_or(0.0));
    }
}

/// 点亮开打（竞技场的事件打开 AI、关掉无敌）
fn engage(d: &Def, c: &Colo, r: &mut Run, why: &str) {
    if d.engage > 0 {
        flag_set(c.flag + d.engage, true);
    }
    r.engaged = true;
    log(&format!("竞技场：第 {} 波开打（{why}）", r.wave + 1));
}

/// 本机这一波的敌人都读进来了：就绪标记亮了；或者出场 BIND_FALLBACK 以后看得到它、活着
fn bound_now(d: &Def, c: &Colo, r: &Run, wcm: &WorldChrMan, now: Instant) -> bool {
    let (Some(w), Some(at)) = (r.spawned, r.spawned_at) else { return false };
    let fallback = now.duration_since(at) >= BIND_FALLBACK;
    let mut alive: HashSet<u32> = HashSet::new();
    if fallback {
        for s in wcm.chr_sets.iter().flatten() {
            for ch in s.characters() {
                if ch.modules.data.hp > 0 {
                    alive.insert(ch.event_entity_id);
                }
            }
        }
    }
    r.lineup[w].iter().all(|&m| {
        let p = &c.parts[m];
        (d.ready > 0 && flag_get(c.flag + d.ready + p.k) == Some(true)) || alive.contains(&p.ent) || r.dead_k.contains(&p.k)
    })
}

/// 这一波的敌人死没死：死亡标记亮了，或者看到它活过、血量又到 0（标记万一被清掉也认得出）
fn track_dead(d: &Def, c: &Colo, r: &mut Run, wcm: &WorldChrMan) {
    let Some(w) = r.spawned else { return };
    let by_ent: HashMap<u32, u32> = r.lineup[w].iter().map(|&m| (c.parts[m].ent, c.parts[m].k)).collect();
    for s in wcm.chr_sets.iter().flatten() {
        for ch in s.characters() {
            let Some(&k) = by_ent.get(&ch.event_entity_id) else { continue };
            if ch.modules.data.hp > 0 {
                r.seen_alive.insert(k);
            } else if r.seen_alive.contains(&k) {
                r.dead_k.insert(k);
            }
        }
    }
    for &k in by_ent.values() {
        if flag_get(c.flag + d.dead + k) == Some(true) {
            r.dead_k.insert(k);
        }
    }
}

/// 本机角色在竞技场里真的死了没有（返回 true = 这一下认定死了）：
/// 血量 0 停了 DEATH_HOLD 还没被馈赠复活顶掉；或者血量回来了身上却没有「刚复活」的效果（联机观战时血量会回来，黄金树爬塔的记录）
fn death_tick(r: &mut Run, hp: i32, revived: bool, now: Instant) -> bool {
    if r.died {
        return false;
    }
    if hp <= 0 {
        let t = *r.zero_at.get_or_insert(now);
        if now.duration_since(t) >= DEATH_HOLD && !revived {
            r.died = true;
            r.zero_at = None;
            return true;
        }
        return false;
    }
    let Some(t) = r.zero_at.take() else { return false };
    if revived {
        log(&format!("竞技场：血量到 0 后被馈赠复活了（停了 {:.1} 秒），试炼照常", now.duration_since(t).as_secs_f32()));
        return false;
    }
    r.died = true;
    log(&format!("竞技场：血量到 0 停了 {:.1} 秒后又有了，但不是馈赠复活（多半是联机观战），当成倒下", now.duration_since(t).as_secs_f32()));
    true
}

/// 这一波打完：奖励直接发进背包（用户 2026-11-10：让玩家知道每波给了什么，死了再扣）
fn wave_reward(d: &Def, st: &mut St, r: &mut Run) {
    let c = &d.colos[r.ci];
    // 无尽试炼：件数照第几波涨（第 j 个精英波 items_e × j、Boss 波 items_b × j，再 × 件数倍率），最多 cap 件；不给骨灰
    if r.endless > 0 {
        let abs = r.endless + r.wave as u32;
        let boss = r.lineup[r.wave].iter().any(|&m| c.parts[m].boss);
        let j = abs.div_ceil(2);
        let cap = d.endless.as_ref().map_or(10, |e| e.cap);
        let n = ((if boss { d.items_b } else { d.items_e }) * j * c.scale.max(1)).min(cap);
        let tier = rew_tiers(d, c, r.diff)[boss as usize];
        let mut got = Vec::new();
        for _ in 0..n {
            let (id, cat) = roll_item(d, tier, st);
            let ok = give_item(r, id);
            got.push(format!("{}·{}{}", RAR_ZH[tier], CAT_ZH[cat], if ok { "" } else { "（没有发货表，没发）" }));
        }
        log(&format!("竞技场：无尽试炼第 {abs} 波肃清，发进背包 {n} 件：{}", got.join("、")));
        return;
    }
    let boss = r.lineup[r.wave].iter().any(|&m| c.parts[m].boss);
    let n_ash = if boss { d.ash_b } else { 0 };
    let (tier, n_items) = wave_items(d, c, &r.lineup, r.wave, r.diff);
    let mut got = Vec::new();
    let mut rolls: Vec<(i32, usize, usize, &str)> = (0..n_items).map(|_| {
        let (id, cat) = roll_item(d, tier, st);
        (id, cat, tier, "")
    }).collect();
    if r.wave + 1 == r.waves {
        // 全部打完多给的：Boss 波的稀有度
        let bt = rew_tiers(d, c, r.diff)[1];
        for _ in 0..r.bonus * c.scale.max(1) {
            let (id, cat) = roll_item(d, bt, st);
            rolls.push((id, cat, bt, "全部打完多给："));
        }
    }
    if r.wave + 1 == r.waves && r.refund > 0 {
        // 退还的碎片不记进 given：打完了就不会再收回
        let ok = gift_log(d.shard, r.refund);
        got.push(format!("退还星光碎片 ×{}{}", r.refund, if ok { "" } else { "（没有发货表，没发）" }));
    }
    for (id, cat, tier, why) in rolls {
        let ok = give_item(r, id);
        got.push(format!("{why}{}·{}{}", RAR_ZH[tier], CAT_ZH[cat], if ok { "" } else { "（没有发货表，没发）" }));
    }
    for _ in 0..n_ash {
        let rar = roll_ash(d, c, r.diff, st);
        let (lines, ids) = give_ashes(rar, 1);
        for id in &ids {
            add_given(r, *id);
        }
        r.n_ashes += ids.len() as u32;
        got.push(format!("骨灰·{}：{}", RAR_ZH[rar], lines.join("；")));
    }
    log(&format!("竞技场：第 {} 波肃清，发进背包 {}", r.wave + 1, got.join("、")));
}

/// 死了：这次发的道具全部收回（tick 里等发货队列发完再扣），提示失败
fn fail(st: &mut St, r: &Run, why: &str) {
    if r.endless > 0 {
        // 无尽试炼：死了不收回奖励，进度留在上次保存的那一波
        log(&format!("竞技场：无尽试炼结束（{why}），打到第 {} 波；奖励不收回（这次发了 {} 件），进度留在上次保存的那一波",
                     r.endless + r.wave as u32, r.n_items));
    } else {
        log(&format!("竞技场：试炼失败（{why}），打到第 {} / {} 波，收回这次发的 {} 件物品、{} 个骨灰", r.wave + 1, r.waves, r.n_items, r.n_ashes));
        st.takeback.extend(r.given.iter().copied());
        crate::notes::push("arena fail");
    }
    crate::nightmare::unforce();
    crate::foefx::release(FX_TAG);
    clear_run_file();
    st.notes.clear();
}

/// 没死就结束了（选了离开 / 打完 / 用别的办法出了竞技场）：奖励保留
fn finish(st: &mut St, r: &Run, why: &str) {
    if r.endless > 0 {
        log(&format!("竞技场：无尽试炼结束（{why}），这次从第 {} 波打到第 {} 波，奖励保留：{} 件物品", r.endless, r.endless + r.cleared as u32 - 1, r.n_items));
    } else {
        log(&format!("竞技场：试炼结束（{why}），打完 {} / {} 波，奖励保留：{} 件物品、{} 个骨灰", r.cleared, r.waves, r.n_items, r.n_ashes));
    }
    crate::nightmare::unforce();
    crate::foefx::release(FX_TAG);
    clear_run_file();
    st.notes.clear();
}

/// 收回失败的试炼发的道具：发货队列空了、人物读进来了才扣（扣不到的记日志）
fn takeback_tick(st: &mut St) {
    if st.takeback.is_empty() || gifts_pending() > 0 {
        return;
    }
    let Ok(gdm) = (unsafe { GameDataMan::instance_mut() }) else { return };
    let pgd = &mut gdm.main_player_game_data;
    if pgd.level == 0 {
        return;
    }
    let mut lines = Vec::new();
    for (id, n) in std::mem::take(&mut st.takeback) {
        let got = remove_goods(pgd, id, n);
        lines.push(if got == n { format!("{id} ×{n}") } else { format!("{id} ×{got} / {n}（背包里不够）") });
    }
    log(&format!("竞技场：收回 {}", lines.join("、")));
}

/// 中止（地图上没有敌人、没传进去）：退还碎片
fn abort(d: &Def, r: &Run, why: &str) {
    log(&format!("竞技场：{why}，退还 {} 个星光碎片", r.cost));
    if r.cost > 0 {
        gift_log(d.shard, r.cost);
    }
    crate::nightmare::unforce();
    crate::foefx::release(FX_TAG);
}

/// 这个部件在不在场上（读图后的角色里有没有这个实体）
fn present(wcm: &WorldChrMan, ents: &HashSet<u32>) -> usize {
    let mut n = 0;
    for s in wcm.chr_sets.iter().flatten() {
        for c in s.characters() {
            if ents.contains(&c.event_entity_id) {
                n += 1;
            }
        }
    }
    n
}

/// 问继续的对话框（竞技场的事件弹框；被取消会自己再弹，选了是 / 否才熄灭问话标记）。返回 Some(继续不继续)
fn ask_tick(d: &Def, st: &St, r: &mut Run, now: Instant) -> Option<bool> {
    let f = d.colos[r.ci].flag;
    if !r.asked {
        // 奖励发完、提示播完再问
        if now - r.at >= ASK_DELAY && gifts_pending() == 0 && st.notes.is_empty() {
            for k in 0..4 {
                flag_set(f + d.ask + k, false);
            }
            flag_set(f + d.ask, true);
            r.asked = true;
            r.at = now;
            log(&format!("竞技场：问要不要继续第 {} 波", r.wave + 2));
        }
        return None;
    }
    let yes = flag_get(f + d.ask + 1) == Some(true);
    let no = flag_get(f + d.ask + 2) == Some(true) || flag_get(f + d.ask + 3) == Some(true);
    if yes || no {
        for k in 0..4 {
            flag_set(f + d.ask + k, false);
        }
    }
    if no && !yes && now - r.at < TOO_FAST && r.reasks < 3 {
        r.reasks += 1;
        log(&format!("竞技场：问了 {:.1} 秒就回了「否」（多半是对话框被别的提示顶掉），再问一次", (now - r.at).as_secs_f32()));
        r.asked = false;
        r.at = now - ASK_DELAY + Duration::from_secs(1);
        return None;
    }
    if yes {
        Some(true)
    } else if no {
        Some(false)
    } else {
        None
    }
}

/// 收起没答完的问话（问的人换了）
fn ask_cancel(d: &Def, r: &mut Run) {
    if r.asked {
        let f = d.colos[r.ci].flag;
        for k in 0..4 {
            flag_set(f + d.ask + k, false);
        }
        r.asked = false;
    }
}

/// 进去以后共同的：试炼进行中的标记、死没死。返回 true = 这一下认定死了
fn common_inside(d: &Def, r: &mut Run, hp: i32, revived: bool, now: Instant) -> bool {
    let c = &d.colos[r.ci];
    let f = c.flag;
    // 试炼进行中的标记：结算前一直亮着（竞技场的事件这时看到玩家死了就把复活点设到雕像旁）；结算后熄灭
    let run_flag = f + d.run + r.v;
    let running = r.phase != Phase::Leaving;
    if d.run > 0 && flag_get(run_flag) == Some(!running) {
        flag_set(run_flag, running);
    }
    let died = death_tick(r, hp, revived, now);
    if died {
        log(&format!("竞技场：玩家倒下了（第 {} / {} 波）", r.wave + 1, r.waves));
        if d.mydead > 0 {
            flag_set(f + d.mydead, true);
        }
    }
    died
}

/// 单人 / 房主推进一次试炼；返回 false = 试炼结束（成功、失败、中止）
fn lead_step(d: &Def, st: &mut St, r: &mut Run, in_arena: bool, hp: i32, revived: bool, wcm: &WorldChrMan, now: Instant) -> bool {
    let c = &d.colos[r.ci];
    let f = c.flag;
    let host = matches!(r.role, Role::Host { .. });
    if r.phase == Phase::Going {
        if in_arena && hp > 0 {
            r.phase = Phase::Arrived;
            r.at = now;
            log("竞技场：已进入竞技场");
        } else if now - r.at > GO_TIMEOUT {
            flag_set(d.warp, false);
            flag_set(d.len[0], false);
            flag_set(d.len[1], false);
            clear_run_file();
            abort(d, r, "没传进竞技场");
            r.why = "abort";
            return false;
        }
        return true;
    }
    // 进去以后：不在竞技场里了（死了复活在赐福、或者别的办法出去了）
    if !in_arena {
        if r.phase == Phase::Leaving && r.left && !r.died {
            finish(st, r, "已传回雕像旁");
            return false;
        }
        if r.zero_at.take().is_some() {
            r.died = true;
        }
        let t = *st.away.get_or_insert(now);
        if now - t >= AWAY_HOLD {
            st.away = None;
            if r.phase != Phase::Leaving {
                r.why = "host_out";
            }
            if r.died {
                fail(st, r, "死亡");
            } else {
                finish(st, r, "没死、用别的办法离开了竞技场");
            }
            return false;
        }
        return true;
    }
    st.away = None;
    if common_inside(d, r, hp, revived, now) && host {
        crate::notes::push("arena coop down");
    }
    // 联机：房主倒下了、竞技场里没有活着的队员 = 全队倒下
    if host && r.died {
        let alive = match &r.role {
            // 还在传送进来的也算（还没报进场）
            Role::Host { mates, .. } => mates.iter().any(|m| m.alive(now) || !m.settled(now)),
            _ => false,
        };
        if !alive {
            if r.phase == Phase::Leaving {
                // 已经结算了（队员选的离开 / 打完了）：房主倒在里面，自己这次的奖励收回
                fail(st, r, "倒下了，试炼由队友打完");
            } else {
                r.why = "wipe";
                fail(st, r, "全队都倒下了");
            }
            return false;
        }
    }
    match r.phase {
        Phase::Going => {}
        Phase::Arrived => {
            let waiting: Vec<String> = match &r.role {
                Role::Host { mates, .. } => mates.iter().filter(|m| !m.settled(now)).map(|m| m.name()).collect(),
                _ => Vec::new(),
            };
            if now - r.at >= ARRIVE_WAIT && (waiting.is_empty() || now - r.at >= ARRIVE_GIVEUP) {
                if !waiting.is_empty() {
                    log(&format!("竞技场：等了 {} 秒，{} 还没进场，先开始", ARRIVE_GIVEUP.as_secs(), waiting.join("、")));
                }
                if let Role::Host { mates, .. } = &r.role {
                    let s: Vec<String> = mates.iter().map(|m| format!("{}：{}", m.name(), match &m.rep {
                        _ if m.lost(now) => "没消息".to_string(),
                        Some(x) if !x.no.is_empty() => format!("不来（{}）", x.no),
                        Some(x) if x.inside => if x.paid { "进场了".to_string() } else { "进场了（只帮忙）".to_string() },
                        _ => "还没进场".to_string(),
                    })).collect();
                    log(&format!("竞技场：联机：{}", s.join("；")));
                }
                endless_extend(d, st, r, 0);
                start_wave(d, st, r, 0, now);
            }
        }
        Phase::Fight => {
            track_dead(d, c, r, wcm);
            let members = r.lineup[r.wave].clone();
            if !r.checked && now - r.at >= CHECK_AFTER {
                r.checked = true;
                let ents: HashSet<u32> = members.iter().map(|&m| c.parts[m].ent).collect();
                let n = present(wcm, &ents);
                if n == 0 {
                    abort(d, r, &format!("第 {} 波的敌人一个都不在场上（地图没放上？）", r.wave + 1));
                    r.phase = Phase::Leaving;
                    r.why = "abort";
                    r.at = now;
                    return true;
                }
            }
            // 开打：本机读进来了、活着的队员也都就绪了（或者等太久）
            if !r.engaged {
                let me_ok = bound_now(d, c, r, wcm, now);
                let waiting: Vec<String> = match &r.role {
                    Role::Host { mates, .. } => mates.iter().filter(|m| m.alive(now) && m.rep.as_ref().and_then(|x| x.bound) != Some(r.wave)).map(|m| m.name()).collect(),
                    _ => Vec::new(),
                };
                let t = now.duration_since(r.spawned_at.unwrap_or(now));
                if me_ok && waiting.is_empty() {
                    engage(d, c, r, if host { "各台电脑都就绪了" } else { "敌人读进来了" });
                } else if t >= BIND_GIVEUP {
                    let why = format!("等了 {} 秒，{}{}没就绪，照样开打", BIND_GIVEUP.as_secs(), if me_ok { "" } else { "本机的敌人、" }, waiting.join("、"));
                    engage(d, c, r, &why);
                }
            }
            // 粪金龟会逃跑钻地，不等它（打死了照样回露滴）。单人死了不结算；联机房主倒下了照样结算（队友还在打），只是自己不拿奖励
            if !(r.died && !host) && members.iter().all(|&m| c.parts[m].scarab || r.dead_k.contains(&c.parts[m].k)) {
                if r.died {
                    log(&format!("竞技场：第 {} 波肃清（你倒下了，这一波不发奖励）", r.wave + 1));
                } else {
                    wave_reward(d, st, r);
                }
                r.cleared = r.wave + 1;
                endless_cleared(d, st, r);
                crate::nightmare::unforce();
                crate::foefx::release(FX_TAG);
                if r.wave + 1 >= r.waves {
                    if d.banner > 0 {
                        flag_set(f + d.banner, true);
                    } else {
                        note(d, st, r.ci, "clear");
                    }
                    r.phase = Phase::Leaving;
                    r.why = "clear";
                    r.at = now;
                } else {
                    note(d, st, r.ci, if r.endless > 0 { "endless cleared" } else { "cleared" });
                    r.phase = Phase::Ask;
                    r.at = now;
                    r.asked = false;
                    r.reasks = 0;
                    if let Role::Host { asking, .. } = &mut r.role {
                        *asking = None;
                    }
                }
            }
        }
        Phase::Ask => {
            // 问谁：自己活着问自己，倒下了问第一个活着的队员
            let decider: Option<u64> = match &r.role {
                Role::Host { mates, .. } if r.died => mates.iter().find(|m| m.alive(now)).map(|m| m.id),
                _ => None,
            };
            let mut answer: Option<bool> = None;
            match decider {
                None => {
                    if let Role::Host { asking, .. } = &mut r.role {
                        if asking.is_some() {
                            *asking = None;
                            r.at = now - ASK_DELAY;
                        }
                    }
                    answer = ask_tick(d, st, r, now);
                }
                Some(id) => {
                    ask_cancel(d, r);
                    let wave = r.wave;
                    if let Role::Host { mates, asking } = &mut r.role {
                        if asking.is_none_or(|a| a.0 != id) {
                            *asking = Some((id, now));
                            log(&format!("竞技场：你倒下了，问 队员 …{:04} 要不要继续第 {} 波", id % 10000, wave + 2));
                        }
                        let since = asking.map_or(now, |a| a.1);
                        answer = mates.iter().find(|m| m.id == id).and_then(|m| m.rep.as_ref()).and_then(|x| x.ans).filter(|a| a.0 == wave).map(|a| a.1);
                        if answer.is_none() && now.duration_since(since) >= ASK_GIVEUP {
                            log(&format!("竞技场：等队员回答等了 {} 秒，当成离开", ASK_GIVEUP.as_secs()));
                            answer = Some(false);
                        }
                    }
                }
            }
            match answer {
                Some(true) => {
                    log(&format!("竞技场：继续第 {} 波", r.wave + 2));
                    r.phase = Phase::Next;
                    r.at = now;
                }
                Some(false) => {
                    log("竞技场：选择离开");
                    endless_save(d, st, r);
                    r.phase = Phase::Leaving;
                    r.why = "leave";
                    r.at = now - LEAVE_WAIT + Duration::from_secs(1);
                }
                None => {}
            }
        }
        Phase::Next => {
            if now - r.at >= NEXT_WAIT {
                let i = r.wave + 1;
                endless_extend(d, st, r, i);
                start_wave(d, st, r, i, now);
            }
        }
        Phase::Leaving => {
            // 联机房主倒在里面（队友打完的）：不传送（在观战），上面全队倒下那里按失败结束
            if r.died {
                return true;
            }
            let wait = if r.why == "clear" { CLEAR_LEAVE_WAIT } else { LEAVE_WAIT };
            if !r.left && now - r.at >= wait {
                flag_set(f + d.leave + r.v, true);
                r.left = true;
                r.at = now;
                log("竞技场：传回雕像旁");
            } else if r.left && now - r.at > Duration::from_secs(15) {
                flag_set(f + d.leave + r.v, true);      // 事件没接住：再点一次
                r.at = now;
            }
        }
    }
    true
}

/// 队员推进一次试炼（照房主的进度）；返回 false = 这一场对本机结束了
fn client_step(d: &Def, st: &mut St, r: &mut Run, in_arena: bool, hp: i32, revived: bool, wcm: &WorldChrMan, now: Instant) -> bool {
    let c = &d.colos[r.ci];
    let f = c.flag;
    let Role::Client { paid, seen, hs, .. } = &r.role else { return false };
    let (paid, hs) = (*paid, hs.clone());
    let lost = now.duration_since(*seen) > HOST_LOST;
    // 无尽试炼：出场顺序房主每波现排，照它发来的接上
    if r.endless > 0 && hs.lineup.len() > r.lineup.len() {
        if let Some(l) = lineup_idx(c, &hs.lineup) {
            r.lineup = l;
        }
    }
    // 和房主断了：结束（奖励保留，倒下了照样收回）
    if lost && r.phase != Phase::Leaving {
        log(&format!("竞技场：{} 秒没收到房主的进度，试炼结束", HOST_LOST.as_secs()));
        crate::notes::push("arena coop lost");
        if r.died {
            fail(st, r, "倒下了，房主断开");
            return false;
        }
        if r.phase == Phase::Going {
            flag_set(d.warp, false);
            flag_set(d.len[0], false);
            flag_set(d.len[1], false);
            clear_run_file();
            abort(d, r, "还没进竞技场就和房主断开了");
            return false;
        }
        if !in_arena {
            finish(st, r, "和房主断开了");
            return false;
        }
        r.phase = Phase::Leaving;
        r.why = "lost";
        r.at = now - LEAVE_WAIT;
    }
    if r.phase == Phase::Going {
        if hs.ph == "end" {
            flag_set(d.warp, false);
            flag_set(d.len[0], false);
            flag_set(d.len[1], false);
            clear_run_file();
            abort(d, r, &format!("还没进竞技场房主就结束了（{}）", hs.why));
            return false;
        }
        if in_arena && hp > 0 {
            r.phase = Phase::Arrived;
            r.at = now;
            log("竞技场：已进入竞技场（跟着房主）");
        } else if now - r.at > GO_TIMEOUT {
            flag_set(d.warp, false);
            flag_set(d.len[0], false);
            flag_set(d.len[1], false);
            clear_run_file();
            abort(d, r, "没传进竞技场");
            return false;
        }
        return true;
    }
    if !in_arena {
        if r.phase == Phase::Leaving && r.left && !r.died {
            finish(st, r, "已传回雕像旁");
            return false;
        }
        if r.zero_at.take().is_some() {
            r.died = true;
        }
        let t = *st.away.get_or_insert(now);
        if now - t >= AWAY_HOLD {
            st.away = None;
            if r.died {
                fail(st, r, "倒下了，复活在竞技场外");
            } else {
                finish(st, r, "没死、用别的办法离开了竞技场");
            }
            return false;
        }
        return true;
    }
    st.away = None;
    if common_inside(d, r, hp, revived, now) {
        crate::notes::push("arena coop down");
    }
    // 房主结束了
    if hs.ph == "end" && r.phase != Phase::Leaving {
        log(&format!("竞技场：房主结束了试炼（{}）", match hs.why.as_str() {
            "clear" => "全部打完",
            "leave" => "选了离开",
            "abort" => "没做成，退还碎片",
            "wipe" => "全队倒下",
            "host_out" => "房主离开了竞技场",
            _ => "其他",
        }));
        if hs.why == "abort" {
            abort(d, r, "房主那边没做成");
        }
        // 最后一波的奖励先补上（打完的进度和结束可能一起到）
        client_rewards(d, st, r, &hs, paid);
        // 房主说全队倒下、本机却活着（房主那边以为本机断了）：照样保留奖励
        if r.died {
            fail(st, r, "倒下了");
            return false;
        }
        r.phase = Phase::Leaving;
        r.why = if hs.why == "clear" { "clear" } else { "leave" };
        r.at = now;
    }
    if r.phase == Phase::Leaving {
        if r.died {
            // 倒在里面（观战）：不传送，按失败结束
            fail(st, r, "倒下了");
            return false;
        }
        let wait = if r.why == "clear" { CLEAR_LEAVE_WAIT } else { LEAVE_WAIT };
        if !r.left && now - r.at >= wait {
            flag_set(f + d.leave + r.v, true);
            r.left = true;
            r.at = now;
            log("竞技场：传回雕像旁");
        } else if r.left && now - r.at > Duration::from_secs(15) {
            flag_set(f + d.leave + r.v, true);
            r.at = now;
        }
        return true;
    }
    // 打完的波：发自己的奖励
    client_rewards(d, st, r, &hs, paid);
    // 出场：房主出场了这一波、本机还没出
    if hs.spawned && hs.w < r.waves && hs.w >= r.cleared && r.spawned.is_none_or(|w| w < hs.w) {
        start_wave(d, st, r, hs.w, now);
    }
    if r.phase == Phase::Fight || r.phase == Phase::Ask || r.phase == Phase::Next {
        if r.spawned == Some(hs.w) && r.bound != Some(hs.w) && bound_now(d, c, r, wcm, now) {
            r.bound = Some(hs.w);
            log(&format!("竞技场：第 {} 波本机就绪", hs.w + 1));
        }
        if hs.go && r.spawned == Some(hs.w) && !r.engaged {
            engage(d, c, r, "房主说开打");
        }
    }
    r.phase = match hs.ph.as_str() {
        "ask" => Phase::Ask,
        "next" => Phase::Next,
        "fight" => Phase::Fight,
        _ => r.phase,
    };
    // 问继续：房主倒下了，问的是你
    if hs.ph == "ask" && hs.ask && !r.died {
        let answered = matches!(&r.role, Role::Client { ans: Some(a), .. } if a.0 == hs.w);
        if !answered {
            if let Some(yes) = ask_tick(d, st, r, now) {
                log(&format!("竞技场：房主倒下了，你选了{}", if yes { "继续" } else { "离开" }));
                if let Role::Client { ans, .. } = &mut r.role {
                    *ans = Some((hs.w, yes));
                }
                r.reasks = 0;
            }
        }
    } else if r.asked {
        ask_cancel(d, r);
        r.reasks = 0;
    }
    true
}

/// 队员：房主打完了的波，本机还没发的奖励发掉（付了碎片、没倒下才发）
fn client_rewards(d: &Def, st: &mut St, r: &mut Run, hs: &HostState, paid: bool) {
    let c = &d.colos[r.ci];
    let f = c.flag;
    while r.cleared < hs.clr.min(r.waves) {
        let w = r.cleared;
        r.wave = w;
        if paid && !r.died {
            wave_reward(d, st, r);
        } else {
            log(&format!("竞技场：第 {} 波肃清（{}，不发奖励）", w + 1, if r.died { "你倒下了" } else { "这次只帮忙" }));
        }
        r.cleared += 1;
        crate::nightmare::unforce();
        if r.cleared >= r.waves {
            if d.banner > 0 {
                flag_set(f + d.banner, true);
            } else {
                note(d, st, r.ci, "clear");
            }
        } else {
            note(d, st, r.ci, if r.endless > 0 { "endless cleared" } else { "cleared" });
        }
        r.at = Instant::now();
        r.asked = false;
    }
}

/// 队员现在的情况（报给房主）
fn report_of(r: &Run, in_arena: bool) -> Report {
    let (paid, ans) = match &r.role {
        Role::Client { paid, ans, .. } => (*paid, *ans),
        _ => (false, None),
    };
    Report { paid, inside: in_arena && r.phase != Phase::Going, bound: r.bound, dead: r.died, out: false, ans, no: String::new() }
}

/// 房主发给这个队员的进度
fn host_state(d: &Def, r: &Run, mate: u64) -> HostState {
    let c = &d.colos[r.ci];
    let asking = matches!(&r.role, Role::Host { asking: Some(a), .. } if a.0 == mate);
    HostState {
        id: r.nonce,
        x: c.x,
        v: r.v,
        code: r.code,
        lineup: lineup_ks(c, &r.lineup),
        ph: match r.phase {
            Phase::Going => "going",
            Phase::Arrived => "wait",
            Phase::Fight => "fight",
            Phase::Ask => "ask",
            Phase::Next => "next",
            Phase::Leaving => "end",
        }
        .to_string(),
        w: r.wave,
        spawned: r.spawned == Some(r.wave) && r.phase != Phase::Arrived,
        go: r.engaged && r.spawned == Some(r.wave),
        clr: r.cleared,
        ask: asking && r.phase == Phase::Ask,
        why: if r.phase == Phase::Leaving { r.why.to_string() } else { String::new() },
        e: r.endless,
    }
}

/// 收到的联机消息
fn net_handle(st: &mut St, from: u64, from_host: bool, pk: &Packet, now: Instant) {
    match pk.get("op") {
        Some("state") if from_host => {
            let Some(hs) = HostState::decode(pk) else {
                log("竞技场：联机：房主的进度看不懂，丢掉");
                return;
            };
            if let Some(r) = st.run.as_mut().filter(|r| r.nonce == hs.id) {
                if let Role::Client { seen, hs: h, host, .. } = &mut r.role {
                    if *host == from {
                        *seen = now;
                        *h = hs;
                    }
                }
                return;
            }
            // 结束了的这一场（或者没接的）：回报最后的情况，房主就不等了
            if let Some(x) = st.done.iter_mut().find(|x| x.id == hs.id && x.host == from) {
                if hs.ph != "end" && x.sent.is_none_or(|t| now.duration_since(t) >= SYNC_EVERY) {
                    crate::link::send_to(from, x.rep.packet(x.id));
                    x.sent = Some(now);
                }
                return;
            }
            if hs.ph != "end" {
                st.offer = Some((from, hs));
            }
        }
        Some("me") => {
            let Some((id, rep)) = Report::decode(pk) else { return };
            let Some(r) = st.run.as_mut().filter(|r| r.nonce == id) else { return };
            let wave = r.wave;
            if let Role::Host { mates, .. } = &mut r.role {
                if let Some(m) = mates.iter_mut().find(|m| m.id == from) {
                    let changed = m.rep.as_ref().is_none_or(|old| old.inside != rep.inside || old.dead != rep.dead || old.out != rep.out || old.no != rep.no);
                    if changed {
                        let what = if !rep.no.is_empty() {
                            format!("不来（{}）", rep.no)
                        } else if rep.out {
                            "离开了竞技场".to_string()
                        } else if rep.dead {
                            "倒下了".to_string()
                        } else if rep.inside {
                            if rep.paid { "进场了".to_string() } else { "进场了（碎片不够，只帮忙）".to_string() }
                        } else {
                            "接下了，正在传送".to_string()
                        };
                        log(&format!("竞技场：联机：{} {what}（第 {} 波）", m.name(), wave + 1));
                    }
                    m.rep = Some(rep);
                    m.at = now;
                }
            }
        }
        _ => {}
    }
}

/// 记下本机结束了的联机试炼（之后房主还发这一场的进度时回报最后的情况）
fn remember_done(st: &mut St, id: u64, host: u64, rep: Report) {
    crate::link::send_to(host, rep.packet(id));
    st.done.retain(|x| x.id != id);
    st.done.push(Done { id, host, rep, sent: Some(Instant::now()) });
    if st.done.len() > 8 {
        st.done.remove(0);
    }
}

/// 联机：发进度（房主）/ 报情况（队员），变了马上发、没变每 SYNC_EVERY 发一次
fn sync_send(d: &Def, st: &mut St, in_arena: bool, now: Instant) {
    if let Some((pk, ids, until, last)) = st.end_resend.as_mut() {
        if now >= *until {
            st.end_resend = None;
        } else if now.duration_since(*last) >= SYNC_EVERY {
            *last = now;
            for &id in ids.iter() {
                crate::link::send_to(id, pk.clone());
            }
        }
    }
    let Some(r) = st.run.as_mut() else { return };
    match &r.role {
        Role::Host { mates, .. } => {
            let states: Vec<(u64, Packet)> = mates.iter().map(|m| (m.id, host_state(d, r, m.id).packet())).collect();
            if let Role::Host { mates, .. } = &mut r.role {
                for (m, (_, pk)) in mates.iter_mut().zip(states) {
                    if m.sent.as_ref().is_none_or(|(old, t)| *old != pk || now.duration_since(*t) >= SYNC_EVERY) {
                        crate::link::send_to(m.id, pk.clone());
                        m.sent = Some((pk, now));
                    }
                }
            }
        }
        Role::Client { .. } => {
            let pk = report_of(r, in_arena).packet(r.nonce);
            if let Role::Client { host, sent, .. } = &mut r.role {
                if sent.as_ref().is_none_or(|(old, t)| *old != pk || now.duration_since(*t) >= SYNC_EVERY) {
                    crate::link::send_to(*host, pk.clone());
                    *sent = Some((pk, now));
                }
            }
        }
        Role::Solo => {}
    }
}

/// 一场试炼对本机结束了：联机的善后（房主接着发「结束」，队员回报最后的情况）
fn run_over(d: &Def, st: &mut St, r: Run, now: Instant) {
    match r.role {
        Role::Host { ref mates, .. } => {
            let mut hs = host_state(d, &r, 0);
            hs.ph = "end".into();
            if hs.why.is_empty() || r.phase != Phase::Leaving {
                hs.why = r.why.to_string();
            }
            let ids: Vec<u64> = mates.iter().map(|m| m.id).collect();
            let pk = hs.packet();
            for &id in &ids {
                crate::link::send_to(id, pk.clone());
            }
            log(&format!("竞技场：联机：告诉 {} 个队员试炼结束（{}）", ids.len(), hs.why));
            st.end_resend = Some((pk, ids, now + END_RESEND, now));
        }
        Role::Client { host, paid, ans, .. } => {
            let rep = Report { paid, inside: false, bound: r.bound, dead: r.died, out: true, ans, no: String::new() };
            remember_done(st, r.nonce, host, rep);
        }
        Role::Solo => {}
    }
}

/// 开发工具（dll\dark_dev「斗技场试炼测试」写 arena_req.txt，处理完删掉）：
/// 进 <竞技场> <场次>（不扣碎片、不用站在雕像旁；联机房主照样带队员）/ 清场（这一波的敌人血量设 0）/ 结算（离开，奖励保留）/
/// 放弃（当死亡：收回奖励）/ 碎片 <n> / 状态
fn dev_req(d: &Def, st: &mut St, wcm: &mut WorldChrMan, now: Instant) {
    let path = dir().join("arena_req.txt");
    let Ok(text) = fs::read_to_string(&path) else { return };
    let _ = fs::remove_file(&path);
    for line in text.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')) {
        let f: Vec<&str> = line.split_whitespace().collect();
        match f.as_slice() {
            ["进", x, code] => {
                let (Ok(x), Ok(code)) = (x.parse::<u32>(), code.parse::<usize>()) else { continue };
                let Some(ci) = d.colos.iter().position(|c| c.x == x) else {
                    log(&format!("竞技场：开发工具：arena.txt 里没有竞技场 {x}"));
                    continue;
                };
                if st.run.is_some() {
                    log("竞技场：开发工具：已经在试炼中");
                    continue;
                }
                if crate::coop::client() {
                    log("竞技场：开发工具：本机是联机队员，试炼要房主开始");
                    continue;
                }
                if code == 0 || code > d.runs.len() {
                    log(&format!("竞技场：开发工具：场次 {code} 不对"));
                    continue;
                }
                start_run(d, st, ci, 0, code, 0, "开发工具：直接进（不扣碎片，离开时传到雕像 0 旁）", now);
                if let Some(r) = st.run.as_mut() {
                    r.dev = true;
                }
            }
            ["无尽", x, n] => {
                let (Ok(x), Ok(n)) = (x.parse::<u32>(), n.parse::<u32>()) else { continue };
                let Some(ci) = d.colos.iter().position(|c| c.x == x) else {
                    log(&format!("竞技场：开发工具：arena.txt 里没有竞技场 {x}"));
                    continue;
                };
                if st.run.is_some() {
                    log("竞技场：开发工具：已经在试炼中");
                    continue;
                }
                if crate::coop::client() {
                    log("竞技场：开发工具：本机是联机队员，试炼要房主开始");
                    continue;
                }
                let n = n.max(1);
                start_endless(d, st, ci, 0, n, &format!("开发工具：直接进无尽试炼第 {n} 波（不看难度档，离开时传到雕像 0 旁）"), now);
                if let Some(r) = st.run.as_mut() {
                    r.dev = true;
                }
            }
            ["无尽清", x] => {
                let Ok(x) = x.parse::<u32>() else { continue };
                let best = st.prog.by_x.get(&x).map_or(0, |p| p.1);
                st.prog.by_x.insert(x, (1, best));
                prog_save(&st.prog);
                log(&format!("竞技场：开发工具：竞技场 {x} 的无尽试炼进度清掉了（最高第 {best} 波保留）"));
            }
            ["清场"] => {
                let Some(r) = st.run.as_ref().filter(|r| r.phase == Phase::Fight) else {
                    log("竞技场：开发工具：现在没有在打的一波");
                    continue;
                };
                let c = &d.colos[r.ci];
                let ents: HashSet<u32> = r.lineup[r.wave].iter().map(|&m| c.parts[m].ent).collect();
                let mut n = 0;
                for s in wcm.chr_sets.iter().flatten() {
                    for ch in s.characters() {
                        if ents.contains(&ch.event_entity_id) && ch.modules.data.hp > 0 {
                            ch.modules.data.hp = 0;
                            n += 1;
                        }
                    }
                }
                log(&format!("竞技场：开发工具：清场，{n} 个敌人血量设成 0"));
            }
            ["结算"] => match st.run.as_mut() {
                Some(r) if r.phase != Phase::Going && r.phase != Phase::Leaving && !matches!(r.role, Role::Client { .. }) => {
                    crate::nightmare::unforce();
                    r.phase = Phase::Leaving;
                    r.why = "leave";
                    r.at = now - LEAVE_WAIT;
                }
                _ => log("竞技场：开发工具：现在不在竞技场里的试炼中（联机队员不能结算）"),
            },
            ["放弃"] => {
                if let Some(mut r) = st.run.take() {
                    let c = &d.colos[r.ci];
                    fail(st, &r, "开发工具：放弃");
                    flag_set(c.flag + d.leave + r.v, true);
                    r.died = true;
                    r.why = "host_out";
                    run_over(d, st, r, now);
                }
            }
            ["生成器", cmd] => gen_req(d, st, wcm, cmd, now),
            ["碎片", n] => {
                let n = n.parse::<u32>().unwrap_or(3);
                log(&format!("竞技场：开发工具：发 {n} 个星光碎片{}", if gift_log(d.shard, n) { "" } else { "（没有发货表，没发）" }));
            }
            // 只进获得记录的发放测试：和每波奖励同一条路（未鉴定传说 3 件 + 史诗骨灰 1 个），不记进这次试炼
            ["奖励测试"] => {
                let mut got = Vec::new();
                for _ in 0..3 {
                    let (id, cat) = roll_item(d, 3, st);
                    got.push(format!("{}·{}{}", RAR_ZH[3], CAT_ZH[cat], if gift_log(id as u32, 1) { "" } else { "（没有发货表，没发）" }));
                }
                let (lines, _) = give_ashes(2, 1);
                got.push(format!("骨灰·{}：{}", RAR_ZH[2], lines.join("；")));
                log(&format!("竞技场：开发工具：试发奖励 {}（发货表发，只进边上的获得记录；到了看「发货：」那一行）", got.join("、")));
            }
            ["状态"] => match st.run.as_ref() {
                Some(r) => log(&format!(
                    "竞技场：开发工具：竞技场 {}，{:?}，第 {} / {} 波（打完 {}），已发 {} 件物品、{} 个骨灰，难度档 {}{}{}{}",
                    d.colos[r.ci].x,
                    r.phase,
                    r.wave + 1,
                    r.waves,
                    r.cleared,
                    r.n_items,
                    r.n_ashes,
                    r.diff,
                    if r.died { "，倒下过" } else { "" },
                    if r.engaged { "，开打了" } else { "" },
                    match &r.role {
                        Role::Solo => String::new(),
                        Role::Host { mates, .. } => format!("，联机房主（{} 个队员，{} 个活着在场）", mates.len(), mates.iter().filter(|m| m.alive(now)).count()),
                        Role::Client { paid, hs, .. } => format!("，联机队员（{}；房主 {} 第 {} 波）", if *paid { "付了碎片" } else { "只帮忙" }, hs.ph, hs.w + 1),
                    }
                )),
                None => log("竞技场：开发工具：没有在试炼中"),
            },
            _ => log(&format!("竞技场：开发工具：看不懂「{line}」")),
        }
    }
}

/// 生成器实验（开发工具「生成器 复活这一波 / 叫精英 / 叫Boss / 记录」，第六轮）：点亮部件 k 的请求标记（竞技场的事件听着叫部件 k
/// 自己的生成器，只在那个竞技场里有用），之后 GEN_WATCH 里一直记那个竞技场的敌人
/// 开发工具的生成器按钮、记录对着哪个竞技场：试炼进行中就是那个，不然是人在的那个（m45_0X）；那个竞技场要有生成器（arena.txt 的 gen 行）
fn gen_here(d: &Def, st: &St, wcm: &WorldChrMan) -> Option<GenTest> {
    let x = match st.run.as_ref() {
        Some(r) => d.colos.get(r.ci)?.x,
        None => {
            let b = wcm.main_player.as_ref()?.current_block_id;
            (b.area() == 45).then_some(b.block() as u32)?
        }
    };
    let (req0, gen0) = d.colos.iter().find(|c| c.x == x)?.revive?;
    Some(GenTest { x, req0, gen0 })
}

fn gen_req(d: &Def, st: &mut St, wcm: &WorldChrMan, cmd: &str, now: Instant) {
    let Some(g) = gen_here(d, st, wcm) else {
        log("生成器：现在不在试炼里、也不在竞技场里，或者这个竞技场没有生成器（arena.txt 里没有 gen 行，还没重随）");
        return;
    };
    let Some(c) = d.colos.iter().find(|c| c.x == g.x) else {
        log(&format!("生成器实验：arena.txt 里没有竞技场 {}", g.x));
        return;
    };
    let here = wcm.main_player.as_ref().map(|p| {
        let b = p.current_block_id;
        (b.area(), b.block())
    });
    if here != Some((45, g.x as u8)) {
        log(&format!("生成器实验：现在不在竞技场 {}（m45_0{}）里，标记点了也没人听（人在 {:?}）", g.x, g.x, here));
    }
    let look = gen_look(c, wcm);
    let of = |ent: u32| look.iter().find(|(_, (_, s))| s.ent == ent).map(|(&a, (_, s))| (a, s));
    let run = st.run.as_ref().filter(|r| d.colos.get(r.ci).is_some_and(|rc| rc.x == g.x));
    match cmd {
        "复活这一波" => {
            let Some(r) = run else {
                log("生成器实验：复活这一波：现在不在这个竞技场的试炼里");
                return;
            };
            let Some(w) = r.spawned else {
                log("生成器实验：复活这一波：这次试炼还没有敌人出场");
                return;
            };
            let (mut called, mut alive, mut back) = (Vec::new(), Vec::new(), Vec::new());
            for &m in &r.lineup[w] {
                let p = &c.parts[m];
                // 看得到就按血量（复活过的死亡标记还亮着）；看不到才按死亡标记
                let gone = match of(p.ent) {
                    Some((_, s)) => s.hp <= 0,
                    None => flag_get(c.flag + d.dead + p.k) == Some(true),
                };
                if gone {
                    // 死亡、就绪标记第一次出场时亮过：先熄掉，复活事件复活以后再点亮（清场、开打照它们看）
                    flag_set(c.flag + d.dead + p.k, false);
                    if d.ready > 0 {
                        flag_set(c.flag + d.ready + p.k, false);
                    }
                    flag_set(g.req0 + p.k, true);
                    st.genw.called.insert(p.k);
                    called.push(format!("{}（生成器 {}）", gen_name(p), g.gen0 + p.k));
                    back.push(m);
                } else {
                    alive.push(gen_name(p));
                }
            }
            log(&format!("生成器实验：复活这一波（第 {} 波）：叫 {}；没倒下的不叫：{}", w + 1,
                         if called.is_empty() { "没有".to_string() } else { called.join("、") },
                         if alive.is_empty() { "没有".to_string() } else { alive.join("、") }));
            // 第八轮：复活会清掉身上全部效果（第七轮实测魇化的血量、描边都没了），按它那一波重新登记魇化、血量加成和效果包
            // （活着时魇化、敌人效果模块自己会补挂；魇化重新抽词条）
            if !back.is_empty() {
                wave_effects(d, r, w, &back, "生成器实验复活：");
                let elites = back.iter().filter(|&&m| !c.parts[m].boss && !c.parts[m].scarab).count();
                log(&format!("生成器实验：复活的 {} 只按第 {} 波重新登记效果（其中精英 {elites} 只重新魇化）", back.len(), w + 1));
            }
        }
        "叫精英" | "叫Boss" => {
            let boss = cmd == "叫Boss";
            // 优先这次试炼排不到的（排到了的出场时还会被启用一次）
            let later: HashSet<usize> = run.map(|r| r.lineup.iter().flatten().copied().collect()).unwrap_or_default();
            let pick = c.parts.iter().enumerate()
                .filter(|(_, p)| p.boss == boss && !p.scarab && flag_get(c.flag + d.spawn + p.k) != Some(true) && !st.genw.called.contains(&p.k))
                .min_by_key(|(m, _)| later.contains(m));
            let Some((m, p)) = pick else {
                log(&format!("生成器实验：{cmd}：没有没出场、也没叫过的了"));
                return;
            };
            let before = of(p.ent).map_or("现在不在角色列表里".to_string(), |(a, s)| format!("叫之前 地址 {a:x} 血 {}/{} 位置 {}，{}", s.hp, s.max,
                                                                                         fmt_pos(s.pos), fmt_state(s)));
            flag_set(g.req0 + p.k, true);
            st.genw.called.insert(p.k);
            log(&format!("生成器实验：{cmd}：叫没出场的 {}（生成器 {}{}）；{before}", gen_name(p), g.gen0 + p.k,
                         if later.contains(&m) { "，这次试炼后面的波次会排到它" } else { "" }));
        }
        "记录" => {
            let wave: HashSet<usize> = run.and_then(|r| r.spawned.map(|w| r.lineup[w].iter().copied().collect())).unwrap_or_default();
            let mut v: Vec<(&usize, &(usize, GenSeen))> = look.iter().collect();
            v.sort_by_key(|(_, (i, _))| *i);
            let mut lines = Vec::new();
            for (&a, (i, s)) in v {
                let p = &c.parts[*i];
                let tag = if wave.contains(i) { "，这一波的" } else if st.genw.called.contains(&p.k) { "，叫过" } else { "" };
                lines.push(format!("{} 地址 {a:x} 血 {}/{} 位置 {} {}{tag}{}；效果 {:?}", gen_name(p), s.hp, s.max, fmt_pos(s.pos),
                                   fmt_state(s), if crate::nightmare::is_elite(a) { "，魇化记着它" } else { "" }, s.sps));
            }
            log(&format!("生成器实验：记录：{} 只（出现过 {}、倒下过 {}、又活过 {}）{}", lines.len(), st.genw.born,
                         st.genw.died, st.genw.revived, if lines.is_empty() { String::new() } else { format!("：{}", lines.join("；")) }));
        }
        _ => {
            log(&format!("生成器实验：看不懂「{cmd}」"));
            return;
        }
    }
    st.genw.until = Some(now + GEN_WATCH);
    st.genw.next = None;
}

fn gen_name(p: &Part) -> String {
    format!("部件 {} {}（实体 {}）", p.k, p.name, p.ent)
}

fn fmt_pos(p: [f32; 3]) -> String {
    format!("({:.1}, {:.1}, {:.1})", p[0], p[1], p[2])
}

/// 状态字（原始值）：读取状态 / 激活 / 调试标志，和 0x1c4 起 7 个字节
fn fmt_state(s: &GenSeen) -> String {
    format!("状态 {:08x}/{:08x}/{:08x} {}", s.st[0], s.st[1], s.st[2], s.fl.iter().map(|b| format!("{b:02x}")).collect::<String>())
}

/// 复活前后身上的效果比一比
fn sp_diff(before: &[i32], after: &[i32]) -> String {
    let lost: Vec<i32> = before.iter().filter(|x| !after.contains(x)).copied().collect();
    let new: Vec<i32> = after.iter().filter(|x| !before.contains(x)).copied().collect();
    format!("效果 倒下前 {} 个、现在 {} 个，少了 {lost:?}，多了 {new:?}", before.len(), after.len())
}

/// 那个竞技场的部件现在的样子：地址 → (部件在 c.parts 的下标, 样子)。全部角色集合（chrs.rs 的 live!）
fn gen_look(c: &Colo, wcm: &WorldChrMan) -> HashMap<usize, (usize, GenSeen)> {
    let by_ent: HashMap<u32, usize> = c.parts.iter().enumerate().map(|(i, p)| (p.ent, i)).collect();
    let mut out = HashMap::new();
    for a in crate::chrs::collect(&wcm.player_chr_set, [&wcm.ghost_chr_set, &wcm.summon_buddy_chr_set, &wcm.debug_chr_set, &wcm.open_field_chr_set.base], &wcm.chr_sets) {
        let ch = unsafe { &*(a as *const eldenring::cs::ChrIns) };
        let Some(&i) = by_ent.get(&ch.event_entity_id) else { continue };
        let p = &ch.modules.physics.position;
        let (hp, max) = (ch.modules.data.hp, ch.modules.data.max_hp);
        let base = ch as *const eldenring::cs::ChrIns as *const u8;
        let u32_at = |off: usize| unsafe { std::ptr::read_unaligned(base.add(off) as *const u32) };
        let f0 = std::mem::offset_of!(eldenring::cs::ChrIns, chr_flags1c4);
        out.insert(a, (i, GenSeen {
            ent: ch.event_entity_id,
            hp,
            max,
            pos: [p.0, p.1, p.2],
            st: [u32_at(std::mem::offset_of!(eldenring::cs::ChrIns, load_state)), u32_at(std::mem::offset_of!(eldenring::cs::ChrIns, chr_activation_flags)),
                 u32_at(std::mem::offset_of!(eldenring::cs::ChrIns, debug_flags))],
            fl: std::array::from_fn(|j| unsafe { *base.add(f0 + j) }),
            sps: if hp > 0 { ch.special_effect.entries().map(|s| s.param_id).collect() } else { Vec::new() },
            alive_max: if hp > 0 { max } else { 0 },
            died_at: None,
        }));
    }
    out
}

/// 生成器实验：进了那个竞技场的试炼、或者点过按钮以后，每 GEN_SCAN 看一眼那个竞技场的敌人：倒下 / 又活了（复活前后的效果、血量上限）/
/// 被挪到出生点 / 开始显示，叫过的出现、不再显示，玩家卢恩多了多少
fn gen_tick(d: &Def, st: &mut St, wcm: &WorldChrMan, now: Instant) {
    // 只在开发工具直接进的试炼里记（2026-11-19 生成器转正以后每个竞技场都有，玩家从雕像进的不写这些）
    if !st.run.as_ref().is_some_and(|r| r.dev) && st.genw.until.is_none() {
        return;
    }
    let Some(g) = gen_here(d, st, wcm) else { return };
    let Some(c) = d.colos.iter().find(|c| c.x == g.x) else { return };
    // 进了这个竞技场的试炼就开始记（第一波出场、魇化挂上以后的样子也要）
    if st.run.as_ref().is_some_and(|r| r.dev && d.colos.get(r.ci).is_some_and(|rc| rc.x == g.x)) && st.genw.until.is_none_or(|t| now > t) {
        st.genw.until = Some(now + GEN_WATCH);
        st.genw.next = None;
        log(&format!("生成器实验：在竞技场 {} 的试炼里，开始记那里的敌人（{} 分钟）", g.x, GEN_WATCH.as_secs() / 60));
    }
    // 这一波出场的（状态字变了要记）
    let wave: HashSet<usize> = st.run.as_ref().filter(|r| d.colos.get(r.ci).is_some_and(|rc| rc.x == g.x))
        .and_then(|r| r.spawned.map(|w| r.lineup[w].iter().copied().collect())).unwrap_or_default();
    let w = &mut st.genw;
    if w.until.is_none_or(|t| now > t) || w.next.is_some_and(|t| now < t) {
        return;
    }
    w.next = Some(now + GEN_SCAN);
    let mut cur = gen_look(c, wcm);
    let mut lines = Vec::new();
    let (mut n_new, mut n_gone) = (0, 0);
    for (&a, (i, s)) in cur.iter_mut() {
        let p = &c.parts[*i];
        let called = w.called.contains(&p.k);
        let Some(o) = w.seen.get(&a) else {
            w.born += 1;
            if called {
                lines.push(format!("出现 {} 地址 {a:x} 血 {}/{} 位置 {} {}", gen_name(p), s.hp, s.max, fmt_pos(s.pos), fmt_state(s)));
            } else {
                n_new += 1;
            }
            continue;
        };
        // 倒下了也留着活着时的效果、血量上限，和倒下的时间
        if s.hp <= 0 {
            s.sps = o.sps.clone();
            s.alive_max = o.alive_max;
        }
        s.died_at = o.died_at;
        if o.ent != s.ent {
            lines.push(format!("实体编号变了 地址 {a:x}：{} → {}", o.ent, s.ent));
        }
        if o.hp > 0 && s.hp <= 0 {
            w.died += 1;
            s.died_at = Some(now);
            lines.push(format!("倒下 {} 位置 {}", gen_name(p), fmt_pos(s.pos)));
        } else if o.hp <= 0 && s.hp > 0 {
            w.revived += 1;
            let after = s.died_at.take().map_or(String::new(), |t| format!("，倒下后 {:.1} 秒", now.duration_since(t).as_secs_f32()));
            lines.push(format!("又活了 {} 血 {}/{}（倒下前上限 {}）位置 {}{after}；{}；{}", gen_name(p), s.hp, s.max, o.alive_max, fmt_pos(s.pos),
                               sp_diff(&o.sps, &s.sps), if crate::nightmare::is_elite(a) { "魇化还记着它" } else { "魇化没记它" }));
            w.recheck.push((a, now + GEN_RECHECK, o.sps.clone()));
        } else if o.hp > 0 && s.hp > 0 {
            let dist = ((o.pos[0] - s.pos[0]).powi(2) + (o.pos[1] - s.pos[1]).powi(2) + (o.pos[2] - s.pos[2]).powi(2)).sqrt();
            if dist > GEN_JUMP {
                lines.push(format!("挪了 {} {} → {}（{dist:.1} 米）", gen_name(p), fmt_pos(o.pos), fmt_pos(s.pos)));
            }
        }
        // 读取状态 / 激活 / 调试标志变了（叫过的、这一波的才记：出场、开打、复活时变没变）
        if o.st != s.st && (called || wave.contains(i)) {
            lines.push(format!("状态变了 {} {:08x}/{:08x}/{:08x} → {}", gen_name(p), o.st[0], o.st[1], o.st[2], fmt_state(s)));
        }
    }
    let due: Vec<(usize, Instant, Vec<i32>)> = w.recheck.iter().filter(|x| now >= x.1).cloned().collect();
    w.recheck.retain(|x| now < x.1);
    for (a, _, before) in due {
        if let Some((i, s)) = cur.get(&a).filter(|(_, s)| s.hp > 0) {
            lines.push(format!("复活 {} 秒后 {} 血 {}/{}；{}；{}", GEN_RECHECK.as_secs(), gen_name(&c.parts[*i]), s.hp, s.max, sp_diff(&before, &s.sps),
                               if crate::nightmare::is_elite(a) { "魇化还记着它" } else { "魇化没记它" }));
        }
    }
    n_gone += w.seen.keys().filter(|a| !cur.contains_key(a)).count();
    // 卢恩只记多了的（庆典油脂每秒扣、存银行不算）
    let runes = wcm.main_player.as_ref().map(|p| unsafe { p.player_game_data.as_ref() }.rune_count);
    if let (Some(a), Some(b)) = (w.runes, runes) {
        if b > a {
            lines.push(format!("卢恩 +{}（现在 {b}）", b - a));
        }
    }
    w.runes = runes;
    if n_new > 0 {
        lines.push(format!("另有 {n_new} 只出现"));
    }
    if n_gone > 0 {
        lines.push(format!("{n_gone} 只消失"));
    }
    let alive = cur.values().filter(|(_, s)| s.hp > 0).count();
    let total = cur.len();
    w.seen = cur.into_iter().map(|(a, (_, s))| (a, s)).collect();
    if !lines.is_empty() && w.logs < GEN_LOGS {
        w.logs += 1;
        log(&format!("生成器实验：{}；现在 {total} 只、活着 {alive} 只（出现过 {}、倒下过 {}、又活过 {}）", lines.join("；"), w.born, w.died, w.revived));
    }
}

/// 竞技场里的提示：几位都熄了才写下一条（竞技场的事件显示完熄灭）
fn notes_tick(d: &Def, st: &mut St, in_ci: Option<usize>) {
    let Some(&(ci, v)) = st.notes.first() else { return };
    if in_ci != Some(ci) {
        return;
    }
    let c = &d.colos[ci];
    let bits: Vec<u32> = (0..d.note_n).map(|i| c.flag + d.note0 + i).collect();
    let mut busy = false;
    for &b in &bits {
        match flag_get(b) {
            None => return,
            Some(on) => busy |= on,
        }
    }
    if busy {
        return;
    }
    for (i, &b) in bits.iter().enumerate() {
        flag_set(b, (v >> i) & 1 == 1);
    }
    st.notes.remove(0);
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St::fresh(SystemTime::now().duration_since(UNIX_EPOCH).map_or(11, |t| t.as_nanos() as u64)));
    if now < st.next {
        return;
    }
    st.next = now + STEP;
    let inbox: Vec<(u64, bool, Packet)> = std::mem::take(&mut *INBOX.lock().unwrap_or_else(|e| e.into_inner()));
    for (from, from_host, pk) in inbox {
        net_handle(st, from, from_host, &pk, now);
    }
    let in_arena = body(d, st, now);
    sync_send(d, st, in_arena, now);
}

/// 每 STEP 一次（人物在场时）；返回本机在不在这一场的竞技场里
fn body(d: &Def, st: &mut St, now: Instant) -> bool {
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return false };
    let Some(p) = wcm.main_player.as_ref() else { return false };
    let b = p.current_block_id;
    let blk = [b.area(), b.block(), b.region(), b.index()];
    let hp = p.chr_ins.modules.data.hp;
    let just = crate::curses::revive_just();
    let revived = just > 0 && p.chr_ins.special_effect.entries().any(|x| x.param_id == just);
    let in_ci = (blk[0] == 45).then(|| d.colos.iter().position(|c| c.x == blk[1] as u32)).flatten();
    notes_tick(d, st, in_ci);
    takeback_tick(st);
    prog_tick(d, st);
    if flag_get(d.req) == Some(true) {
        request(d, st, blk, now);
    }
    // 队员：房主新开的一场
    if let Some((host, hs)) = st.offer.take() {
        let id = hs.id;
        if let Err(why) = client_join(d, st, host, hs, hp, now) {
            log(&format!("竞技场：联机：房主开始了斗技场试炼（试炼 {id}），没跟着进：{why}"));
            let rep = Report { no: why, ..Report::default() };
            remember_done(st, id, host, rep);
        }
    }
    dev_req(d, st, wcm, now);
    gen_tick(d, st, wcm, now);
    load_watch_tick(d, st, wcm, in_ci, now);
    let mut inside = false;
    match st.run.take() {
        Some(mut r) => {
            let in_arena = in_ci == Some(r.ci);
            inside = in_arena;
            let going = (r.phase == Phase::Going).then_some(r.at);
            let go_on = if matches!(r.role, Role::Client { .. }) {
                client_step(d, st, &mut r, in_arena, hp, revived, wcm, now)
            } else {
                lead_step(d, st, &mut r, in_arena, hp, revived, wcm, now)
            };
            if go_on {
                if let Some(t0) = going.filter(|_| r.phase != Phase::Going) {
                    log(&format!("竞技场：从开始到进场 {:.1} 秒；{}", (now - t0).as_secs_f32(), mem_note()));
                    st.load_watch = Some((r.ci, now));
                }
                st.run = Some(r);
            } else {
                run_over(d, st, r, now);
            }
        }
        None => {
            // 试炼中退出了游戏：记录说没结束、人还在那个竞技场里 → 传回雕像旁；不在竞技场里就删掉记录
            let rec = load_run();
            match (rec, in_ci) {
                (Some((x, v)), Some(ci)) if d.colos[ci].x == x => {
                    let t = *st.stuck.get_or_insert(now);
                    if now - t >= STUCK_AFTER {
                        st.stuck = Some(now);
                        flag_set(d.colos[ci].flag + d.leave + v, true);
                        log(&format!("竞技场：读档时人在竞技场 {x} 里（上次试炼没结束），传回雕像 {v} 旁"));
                    }
                }
                (Some(_), _) if !st.run_file_seen || in_ci.is_none() => {
                    if blk[0] != 45 && hp > 0 {
                        clear_run_file();
                        st.stuck = None;
                    }
                }
                _ => {}
            }
            st.run_file_seen = true;
        }
    }
    inside
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "req\t93670\t93671\t93672\t93673\nshard\t1290\ngoods0\t9200\nlocal\t2400\t2500\t2600\t2610\t2630\t5\t2620\t2604\nper\t3\n\
items\t2\t1\t1\ncat\t30\t60\t10\ndiff\t9950\t8\t2\ndmult\t0\t1.6\t1.2\t0.7\t0.4\ndmult\t2\t1\t1\t1\t1\ntwo\t2\t10\nhpwave\t2\t7319970\t4\n\
run\t1\t2\t1\t1\t0\nrun\t2\t4\t2\t2\t1\nrun\t3\t8\t3\t4\t2\ncolo\t1\t45010000\t45013980\nstatue\t1\t0\t60\t42\t40\t0\n\
rew\t1\t2\t3\t1\nashrar\t1\t50\t35\t13\t2\n\
part\t1\t0\tb\t45013000\t99300100\t-1\tc4800_9000\npart\t1\t1\tb\t45013001\t99300101\t-1\tc4020_9000\n\
part\t1\t2\te\t45013002\t99300102\t0\tc3010_9006\npart\t1\t3\te\t45013003\t99300103\t0\tc3010_9006\n\
part\t1\t4\te\t45013004\t99300104\t0\tc3010_9006\npart\t1\t5\te\t45013005\t99300105\t1\tc4602_9004\n\
part\t1\t6\te\t45013006\t99300106\t1\tc4602_9004\npart\t1\t7\te\t45013007\t99300107\t2\tc3970_9050\npart\t1\t8\te\t45013008\t99300108\t2\tc3970_9050\n\
note\twave 2 1\t1\nnote\twave 2 2\t2\nnote\tclear\t15\n\
wfx\t-\t4,8\tb\t3-6,8+\t100\t狂暴,铁壁\nwfx\t1\t-\te,s\t2\t50\tarena_rule2\nwfx\t-\t-\tb\t0\t100\tx\nwfx\t-\t-\tb\t1\t100\t\n\
gentest\t1\t45012700\t45013700\n";

    /// 按波次挂效果的几率：同样的试炼编号 / 波次 / 实体 / 规则两台电脑一样，换一样就变；50% 大约一半
    #[test]
    fn fx_roll_shared() {
        assert_eq!(fx_roll(77, 2, 12001800, 0), fx_roll(77, 2, 12001800, 0));
        assert_ne!(fx_roll(77, 2, 12001800, 0), fx_roll(78, 2, 12001800, 0));
        assert_ne!(fx_roll(77, 2, 12001800, 0), fx_roll(77, 3, 12001800, 0));
        assert_ne!(fx_roll(77, 2, 12001800, 0), fx_roll(77, 2, 12001801, 0));
        assert_ne!(fx_roll(77, 2, 12001800, 0), fx_roll(77, 2, 12001800, 1));
        let hit = (0..2000u32).filter(|&e| fx_roll(77, 0, 12000000 + e, 0) % 10_000 < 5_000).count();
        assert!((850..1150).contains(&hit), "{hit}");
    }

    #[test]
    fn wave_fx_rules() {
        let d = parse(SAMPLE).unwrap();
        // 后两条写错（第 0 波、没写效果包）：不要，其余照常
        assert_eq!(d.wfx.len(), 2);
        let w = &d.wfx[0];
        assert_eq!((w.colos.clone(), w.runs.clone(), w.who, w.chance), (vec![], vec![4, 8], [true, false, false], 100.0));
        assert_eq!(w.waves, vec![(3, 6), (8, usize::MAX)]);
        assert_eq!(w.packs, vec!["狂暴".to_string(), "铁壁".to_string()]);
        let c = &d.colos[0];
        let (boss, elite) = (&c.parts[0], &c.parts[2]);
        assert!(w.matches(1, 8, 3, boss) && w.matches(1, 8, 6, boss) && w.matches(1, 8, 12, boss));
        assert!(!w.matches(1, 8, 7, boss) && !w.matches(1, 8, 2, boss), "第 7、2 波不在范围里");
        assert!(!w.matches(1, 2, 3, boss), "2 波的场次不管");
        assert!(!w.matches(1, 8, 4, elite), "只管 Boss");
        let w2 = &d.wfx[1];
        assert_eq!((w2.colos.clone(), w2.who, w2.chance), (vec![1], [false, true, true], 50.0));
        assert!(w2.matches(1, 4, 2, elite) && !w2.matches(0, 4, 2, elite) && !w2.matches(1, 4, 2, boss));
        assert_eq!(parse_waves("1, 3-4 ,7+"), Some(vec![(1, 1), (3, 4), (7, usize::MAX)]));
        assert!(parse_waves("4-2").is_none() && parse_waves("").is_none() && parse_waves("a").is_none());
    }

    #[test]
    fn parse_def() {
        let d = parse(SAMPLE).unwrap();
        assert_eq!((d.req, d.len, d.warp, d.shard, d.goods0), (93670, [93671, 93672], 93673, 1290, 9200));
        assert_eq!((d.spawn, d.dead, d.ask, d.leave, d.note0, d.note_n, d.run), (2400, 2500, 2600, 2610, 2630, 5, 2620));
        assert_eq!(d.banner, 2604);
        assert_eq!((d.ready, d.engage, d.mydead), (0, 0, 0), "旧的 local 行没有这三项");
        let d2 = parse(&SAMPLE.replace("2620	2604
", "2620	2604	2640	2605	2606
")).unwrap();
        assert_eq!((d2.ready, d2.engage, d2.mydead), (2640, 2605, 2606));
        assert_eq!(d.runs, vec![(2, 1, 1, 0), (4, 2, 2, 1), (8, 3, 4, 2)]);
        assert_eq!(d.colos.len(), 1);
        let c = &d.colos[0];
        assert_eq!((c.x, c.flag, c.statues.clone(), c.tiers, c.scale), (1, 45010000, vec![(0, [60, 42, 40, 0])], [2, 3], 1));
        assert_eq!(c.parts.len(), 9);
        assert!(c.parts[0].boss && !c.parts[2].boss && c.parts[5].spot == 1);
        assert_eq!(d.notes.get("wave 2 1"), Some(&1));
        assert_eq!(d.notes.get("clear"), Some(&15));
        assert_eq!(d.dmult[1], [1.0; 4]);
        assert_eq!(d.two, vec![0.0, 0.0, 10.0]);
        assert_eq!(d.hpwave, Some((2, 7319970, 4)));
        assert_eq!(c.revive, Some((45012700, 45013700)));
        assert!(parse("req\t1\t2\t3\t4\n").is_none());
    }

    #[test]
    fn lineup_alternates() {
        let d = parse(SAMPLE).unwrap();
        let mut st = St::fresh(5);
        let c = &d.colos[0];
        for _ in 0..20 {
            let l = lineup(&d, c, 4, &mut st);
            assert_eq!(l.len(), 4);
            // 精英波：3 个、种类和站位都不重复
            for w in [&l[0], &l[2]] {
                assert!(w.len() == 3 && w.iter().all(|&i| !c.parts[i].boss), "{w:?}");
                let names: HashSet<&str> = w.iter().map(|&i| c.parts[i].name.as_str()).collect();
                let spots: HashSet<i32> = w.iter().map(|&i| c.parts[i].spot).collect();
                assert_eq!((names.len(), spots.len()), (3, 3));
            }
            assert!(l[1].len() == 1 && c.parts[l[1][0]].boss);
            assert!(l[3].len() == 1 && c.parts[l[3][0]].boss && l[3][0] != l[1][0]);
            // 精英整场不重复
            let all: Vec<usize> = l.iter().flatten().copied().collect();
            assert_eq!(all.iter().collect::<HashSet<_>>().len(), all.len());
        }
        // 8 波：Boss 只有 2 个，用完以后都是精英，精英也用完就提前结束
        let l = lineup(&d, c, 8, &mut st);
        assert!(l.len() <= 8 && l.iter().flatten().count() <= 9);
    }

    /// 粪金龟：只进精英波、红蓝各一个站位不重复、每波至少一个真精英、几率大致是 scarab%
    #[test]
    fn lineup_scarabs() {
        let extra = "scarab\t20\npart\t1\t9\ts\t45013009\t99300109\t5\tc4191_9000\npart\t1\t10\ts\t45013010\t99300110\t5\tc4191_9000\n\
part\t1\t11\ts\t45013011\t99300111\t6\tc4191_9003\npart\t1\t12\ts\t45013012\t99300112\t6\tc4191_9003\n";
        let d = parse(&format!("{SAMPLE}{extra}")).unwrap();
        assert_eq!(d.scarab, 20.0);
        let c = &d.colos[0];
        assert!(c.parts[9].scarab && !c.parts[9].boss && !c.parts[2].scarab);
        let mut st = St::fresh(7);
        let (mut slots, mut hits) = (0, 0);
        for _ in 0..2000 {
            let l = lineup(&d, c, 4, &mut st);
            for (w, wave) in l.iter().enumerate() {
                let n_s = wave.iter().filter(|&&i| c.parts[i].scarab).count();
                if w % 2 == 1 {
                    assert_eq!(n_s, 0);
                    continue;
                }
                assert!(wave.iter().any(|&i| !c.parts[i].scarab && !c.parts[i].boss), "{wave:?}");
                let spots: HashSet<i32> = wave.iter().map(|&i| c.parts[i].spot).collect();
                assert_eq!(spots.len(), wave.len());
                slots += wave.len();
                hits += n_s;
            }
            let all: Vec<usize> = l.iter().flatten().copied().collect();
            assert_eq!(all.iter().collect::<HashSet<_>>().len(), all.len());
        }
        let share = hits as f32 / slots as f32;
        assert!((0.14..0.22).contains(&share), "{share}");
        // 0 = 不换
        let d0 = parse(&format!("{SAMPLE}{}", extra.replacen("scarab\t20", "scarab\t0", 1))).unwrap();
        for _ in 0..50 {
            assert!(lineup(&d0, &d0.colos[0], 4, &mut st).iter().flatten().all(|&i| !d0.colos[0].parts[i].scarab));
        }
    }

    #[test]
    fn rolls() {
        let d = parse(SAMPLE).unwrap();
        let mut st = St::fresh(9);
        let c = &d.colos[0];
        for _ in 0..200 {
            let (id, cat) = roll_item(&d, 4, &mut st);
            assert!(cat < 3 && id == 9204 + 10 * cat as i32);
            assert!(roll_ash(&d, c, 0, &mut st) < 4);
        }
        // 第 j 个同类波 × j：精英波 2 / 4 件史诗，Boss 波 1 / 2 件传说
        let lu = vec![vec![2, 5, 7], vec![0], vec![3, 6], vec![1]];
        assert_eq!(wave_items(&d, c, &lu, 0, 0), (2, 2));
        assert_eq!(wave_items(&d, c, &lu, 1, 0), (3, 1));
        assert_eq!(wave_items(&d, c, &lu, 2, 0), (2, 4));
        assert_eq!(wave_items(&d, c, &lu, 3, 0), (3, 2));
        // 死亡以上（lockrew 的档）：稀有度都换成 lockrew 的，件数不变；别的档照旧
        let dl = parse(&format!("{SAMPLE}lockrew\t4\t6,7\n")).unwrap();
        assert_eq!(dl.lockrew, Some((4, vec![6, 7])));
        let cl = &dl.colos[0];
        assert_eq!(wave_items(&dl, cl, &lu, 0, 6), (4, 2));
        assert_eq!(wave_items(&dl, cl, &lu, 1, 7), (4, 1));
        assert_eq!(wave_items(&dl, cl, &lu, 1, 2), (3, 1), "死亡以下照 rew 行");
        assert_eq!(rew_tiers(&d, c, 6), c.tiers, "没有 lockrew 行：照 rew 行");
    }

    /// 无尽试炼：endless 行；出场顺序：偶数波 Boss、先挑这一场没出过的、都出过了挑最久没出场的；粪金龟一场只出一次
    #[test]
    fn endless_lineup() {
        let extra = "endless\t92596\t92597\t7319974\t0.05\t10\t2607\t6,7\nscarab\t100\npart\t1\t9\ts\t45013009\t99300109\t5\tc4191_9000\n";
        let d = parse(&format!("{SAMPLE}{extra}")).unwrap();
        let e = d.endless.clone().unwrap();
        assert_eq!((e.req, e.has0, e.sp, e.cap, e.local, e.tiers.clone()), (92596, 92597, 7319974, 10, 2607, vec![6, 7]));
        assert!((e.step - 0.05).abs() < 1e-6);
        assert!(parse(SAMPLE).unwrap().endless.is_none());
        let c = &d.colos[0];
        let mut st = St::fresh(3);
        let mut lu: Vec<Vec<usize>> = Vec::new();
        for i in 0..40 {
            let w = endless_pick(&d, c, &lu, 1, i, &mut st);
            if (1 + i) % 2 == 0 {
                assert!(w.len() == 1 && c.parts[w[0]].boss, "第 {} 波 {w:?}", i + 1);
            } else {
                assert!(!w.is_empty() && w.iter().all(|&m| !c.parts[m].boss), "第 {} 波 {w:?}", i + 1);
                let names: HashSet<&str> = w.iter().map(|&m| c.parts[m].name.as_str()).collect();
                let spots: HashSet<i32> = w.iter().map(|&m| c.parts[m].spot).collect();
                assert_eq!((names.len(), spots.len()), (w.len(), w.len()));
            }
            lu.push(w);
        }
        // Boss 只有 2 个：第 2、4 波各出一个，之后轮着（最久没出场的先）
        assert_ne!(lu[1][0], lu[3][0]);
        assert_eq!((lu[5][0], lu[7][0]), (lu[1][0], lu[3][0]));
        // 精英：没出过的先（第 1、3 波不重样）
        let first: HashSet<usize> = lu[0].iter().copied().filter(|&m| !c.parts[m].scarab).collect();
        assert!(lu[2].iter().all(|m| !first.contains(m)), "{:?} / {:?}", lu[0], lu[2]);
        // 粪金龟一场只出一次
        assert_eq!(lu.iter().flatten().filter(|&&m| c.parts[m].scarab).count(), 1);
        // 从第 2 波续上：第一波就是 Boss 波
        let w = endless_pick(&d, c, &[], 2, 0, &mut st);
        assert!(w.len() == 1 && c.parts[w[0]].boss);
    }

    /// 无尽进度的记录：名字对不上的不认；下次第 0 波当第 1 波
    #[test]
    fn endless_progress_file() {
        let t = "# 说明\nname\t褪色者\ncolo\t2\t13\t20\ncolo\t0\t0\t5\nbad\tline\n";
        let m = prog_parse(t, "褪色者").unwrap();
        assert_eq!((m.get(&2), m.get(&0), m.len()), (Some(&(13, 20)), Some(&(1, 5)), 2));
        assert!(prog_parse(t, "别人").is_none());
    }

    fn run_for(d: &Def) -> Run {
        let lu = vec![vec![2, 5, 7], vec![0]];
        new_run(0, 0, 1, 1, lu, d.runs[0], 2, 77, Role::Solo, Instant::now())
    }

    /// 联机的两种消息编码再解码不变；出场顺序 k ↔ 下标
    #[test]
    fn coop_packets_roundtrip() {
        let d = parse(SAMPLE).unwrap();
        let c = &d.colos[0];
        let lu = vec![vec![2, 5, 7], vec![0], vec![3, 6], vec![1]];
        let ks = lineup_ks(c, &lu);
        assert_eq!(ks, vec![vec![2, 5, 7], vec![0], vec![3, 6], vec![1]]);
        assert_eq!(lineup_idx(c, &ks), Some(lu.clone()));
        assert_eq!(lineup_idx(c, &[vec![99]]), None, "对不上的部件");
        let hs = HostState { id: 123456789012345, x: 1, v: 0, code: 2, lineup: ks, ph: "fight".into(), w: 2, spawned: true, go: false, clr: 2, ask: true,
                             why: String::new(), e: 7 };
        let pk = hs.packet();
        assert_eq!(pk.kind, Kind::Arena);
        let back = Packet::decode(&pk.encode()).unwrap();
        assert_eq!(HostState::decode(&back), Some(hs));
        let rep = Report { paid: true, inside: true, bound: Some(3), dead: false, out: false, ans: Some((1, true)), no: String::new() };
        let back = Packet::decode(&rep.packet(42).encode()).unwrap();
        assert_eq!(Report::decode(&back), Some((42, rep)));
        let no = Report { no: "你倒下了".into(), ..Report::default() };
        assert_eq!(Report::decode(&Packet::decode(&no.packet(7).encode()).unwrap()), Some((7, no)));
    }

    /// 真死判定：血量 0 停够了才算；馈赠复活顶掉的不算；血量回来了却没有复活效果（观战）算
    #[test]
    fn death_needs_hold_or_no_revive() {
        let d = parse(SAMPLE).unwrap();
        let t0 = Instant::now();
        let mut r = run_for(&d);
        assert!(!death_tick(&mut r, 0, false, t0));
        assert!(!death_tick(&mut r, 0, false, t0 + Duration::from_millis(1200)), "1.2 秒还不算");
        assert!(!death_tick(&mut r, 500, true, t0 + Duration::from_millis(1300)), "馈赠复活了");
        assert!(!r.died && r.zero_at.is_none());
        assert!(!death_tick(&mut r, 0, false, t0 + Duration::from_secs(5)));
        assert!(death_tick(&mut r, 0, false, t0 + Duration::from_secs(8)), "停了 3 秒");
        assert!(r.died);
        assert!(!death_tick(&mut r, 0, false, t0 + Duration::from_secs(9)), "只认一次");
        let mut r = run_for(&d);
        assert!(!death_tick(&mut r, 0, false, t0));
        assert!(death_tick(&mut r, 800, false, t0 + Duration::from_millis(500)), "血量回来了但没有复活效果");
        let mut r = run_for(&d);
        assert!(!death_tick(&mut r, 900, false, t0), "一直活着");
        assert!(!r.died);
    }

    /// 队员：进场有结果、活着在场
    #[test]
    fn mate_states() {
        let t0 = Instant::now();
        let mut m = Mate { id: 76561198000001234, rep: None, at: t0, sent: None };
        assert!(!m.settled(t0) && !m.alive(t0));
        assert!(m.settled(t0 + MATE_LOST + Duration::from_secs(1)), "断了也算有结果");
        m.rep = Some(Report { inside: true, paid: true, ..Report::default() });
        assert!(m.settled(t0) && m.alive(t0));
        m.rep = Some(Report { inside: true, dead: true, ..Report::default() });
        assert!(m.settled(t0) && !m.alive(t0));
        m.rep = Some(Report { no: "你倒下了".into(), ..Report::default() });
        assert!(m.settled(t0) && !m.alive(t0));
        assert_eq!(m.name(), "队员 …1234");
    }

    /// 房主发给队员的进度：问继续只告诉被问的那个；结束了带原因
    #[test]
    fn host_state_per_mate() {
        let d = parse(SAMPLE).unwrap();
        let t0 = Instant::now();
        let mut r = run_for(&d);
        r.role = Role::Host { mates: vec![Mate { id: 5, rep: None, at: t0, sent: None }, Mate { id: 6, rep: None, at: t0, sent: None }],
                              asking: Some((6, t0)) };
        r.phase = Phase::Ask;
        r.spawned = Some(0);
        r.engaged = true;
        r.cleared = 1;
        let a = host_state(&d, &r, 5);
        let b = host_state(&d, &r, 6);
        assert_eq!((a.ph.as_str(), a.ask, b.ask, a.clr, a.spawned, a.go), ("ask", false, true, 1, true, true));
        r.phase = Phase::Arrived;
        assert!(!host_state(&d, &r, 5).spawned, "等人进场时还没出场");
        r.phase = Phase::Leaving;
        r.why = "clear";
        let e = host_state(&d, &r, 5);
        assert_eq!((e.ph.as_str(), e.why.as_str(), e.ask), ("end", "clear", false));
    }
}
