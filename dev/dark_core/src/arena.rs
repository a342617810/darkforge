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

use eldenring::cs::{ChrInsExt, GameDataMan, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::gear::{count_goods, flag_get, flag_set, gift_n, gifts_pending, give_ashes, remove_goods};
use crate::link::{Kind, Packet};
use crate::{dir, log};

const STEP: Duration = Duration::from_millis(100);
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
/// 血量加成：出场后这么久还没挂上（敌人没读进来）就不管了
const BOOST_GIVEUP: Duration = Duration::from_secs(20);
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
    dmult: Vec<[f32; 4]>,
    /// 场次（1 起）→ (波数, 碎片, 全部打完多给几件, 全部打完退还几个碎片)
    runs: Vec<(usize, u32, u32, u32)>,
    colos: Vec<Colo>,
    notes: HashMap<String, u32>,
    /// 每档难度魇化精英带两条的几率 %
    two: Vec<f32>,
    /// 血量随波次：(每几波一档, 第一档的效果, 档数)；第 w 波（0 起）= w / every 档
    hpwave: Option<(usize, i32, usize)>,
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
            "dmult" => {
                let k = n(1)? as usize;
                if d.dmult.len() <= k {
                    d.dmult.resize(k + 1, [1.0; 4]);
                }
                d.dmult[k] = f4(&f[2..])?;
            }
            "hpwave" => d.hpwave = Some(((n(1)? as usize).max(1), n(2)? as i32, n(3)? as usize)),
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
        ),
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
    /// 这一波要挂的血量加成：(实体, 效果, 挂上时的血量上限)
    boosts: Vec<(u32, i32, Option<i32>)>,
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
        }
    }
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
fn wave_items(d: &Def, c: &Colo, lineup: &[Vec<usize>], wave: usize) -> (usize, u32) {
    let is_boss = |w: &Vec<usize>| w.iter().any(|&m| c.parts[m].boss);
    let boss = is_boss(&lineup[wave]);
    let j = lineup[..=wave].iter().filter(|w| is_boss(w) == boss).count() as u32;
    let base = if boss { d.items_b } else { d.items_e };
    (c.tiers[boss as usize], base * j * c.scale.max(1))
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

/// 发一件未鉴定物品进背包（走发货表，游戏会弹「获得物品」）
fn give_item(r: &mut Run, id: i32) -> bool {
    if gift_n(1, id, 1) {
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
            gift_n(1, d.shard as i32, got);
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
        boosts: Vec::new(),
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
            gift_n(1, d.shard as i32, got);
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
    let members = &r.lineup[i];
    // 开打标记先熄灭（上一波点亮过），出场的这一波读进来了再点亮；旧的竞技场事件没有开打标记，出场就打
    if d.engage > 0 {
        flag_set(c.flag + d.engage, false);
    } else {
        r.engaged = true;
    }
    for &m in members {
        flag_set(c.flag + d.spawn + c.parts[m].k, true);
    }
    r.boosts.clear();
    if let Some((every, sp0, count)) = d.hpwave {
        let step = (i / every).min(count);
        if step > 0 {
            let sp = sp0 + step as i32 - 1;
            r.boosts = members.iter().filter(|&&m| !c.parts[m].scarab).map(|&m| (c.parts[m].ent, sp, None)).collect();
            log(&format!("竞技场：第 {} 波敌人血量加成第 {step} 档（效果 {sp}）", i + 1));
        }
    }
    // 队员这边也登记：nightmare.rs 看到是队员，不自己抽，等房主广播的词条
    let elites: Vec<u32> = members.iter().filter(|&&m| !c.parts[m].boss && !c.parts[m].scarab).map(|&m| c.parts[m].ent).collect();
    if !elites.is_empty() {
        crate::nightmare::force(&elites, d.two.get(r.diff).copied().unwrap_or(0.0));
    }
    note(d, st, r.ci, &format!("wave {} {}", r.waves, i + 1));
    let names: Vec<&str> = members.iter().map(|&m| c.parts[m].name.as_str()).collect();
    log(&format!("竞技场：第 {} / {} 波出场 {}", i + 1, r.waves, names.join("、")));
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
    let boss = r.lineup[r.wave].iter().any(|&m| c.parts[m].boss);
    let n_ash = if boss { d.ash_b } else { 0 };
    let (tier, n_items) = wave_items(d, c, &r.lineup, r.wave);
    let mut got = Vec::new();
    let mut rolls: Vec<(i32, usize, usize, &str)> = (0..n_items).map(|_| {
        let (id, cat) = roll_item(d, tier, st);
        (id, cat, tier, "")
    }).collect();
    if r.wave + 1 == r.waves {
        // 全部打完多给的：Boss 波的稀有度
        for _ in 0..r.bonus * c.scale.max(1) {
            let (id, cat) = roll_item(d, c.tiers[1], st);
            rolls.push((id, cat, c.tiers[1], "全部打完多给："));
        }
    }
    if r.wave + 1 == r.waves && r.refund > 0 {
        // 退还的碎片不记进 given：打完了就不会再收回
        let ok = gift_n(1, d.shard as i32, r.refund);
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
    log(&format!("竞技场：试炼失败（{why}），打到第 {} / {} 波，收回这次发的 {} 件物品、{} 个骨灰", r.wave + 1, r.waves, r.n_items, r.n_ashes));
    st.takeback.extend(r.given.iter().copied());
    crate::notes::push("arena fail");
    crate::nightmare::unforce();
    clear_run_file();
    st.notes.clear();
}

/// 没死就结束了（选了离开 / 打完 / 用别的办法出了竞技场）：奖励保留
fn finish(st: &mut St, r: &Run, why: &str) {
    log(&format!("竞技场：试炼结束（{why}），打完 {} / {} 波，奖励保留：{} 件物品、{} 个骨灰", r.cleared, r.waves, r.n_items, r.n_ashes));
    crate::nightmare::unforce();
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
        gift_n(1, d.shard as i32, r.cost);
    }
    crate::nightmare::unforce();
}

/// 这一波的血量加成：敌人出现了（血量 > 0）就挂效果，上限变了以后补满血（出场时血是满的；挂效果游戏不按比例补当前血量）。
/// 两台电脑都挂（敌人身上的效果不走网络同步，联机计划 13.9）；补满血只让房主写（血量跟着房主那份同步）
fn boost_tick(r: &mut Run, wcm: &WorldChrMan, now: Instant) {
    if r.boosts.is_empty() {
        return;
    }
    if now - r.at > BOOST_GIVEUP {
        log(&format!("竞技场：{} 个敌人的血量加成没挂上（没读进来），不管了", r.boosts.len()));
        r.boosts.clear();
        return;
    }
    for s in wcm.chr_sets.iter().flatten() {
        for c in s.characters() {
            let Some(b) = r.boosts.iter_mut().find(|b| b.0 == c.event_entity_id) else { continue };
            if c.modules.data.hp <= 0 {
                continue;
            }
            match b.2 {
                None => {
                    if !c.special_effect.entries().any(|x| x.param_id == b.1) {
                        c.apply_speffect(b.1, false);
                    }
                    b.2 = Some(c.modules.data.max_hp);
                }
                Some(m0) if c.modules.data.max_hp != m0 => {
                    if !crate::coop::client_skip("斗技场加血以后补满血") {
                        c.modules.data.hp = c.modules.data.max_hp;
                    }
                    b.0 = 0; // 做完了
                }
                Some(_) => {}
            }
        }
    }
    r.boosts.retain(|b| b.0 != 0);
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
                start_wave(d, st, r, 0, now);
            }
        }
        Phase::Fight => {
            boost_tick(r, wcm, now);
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
                crate::nightmare::unforce();
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
                    note(d, st, r.ci, "cleared");
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
        boost_tick(r, wcm, now);
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
            note(d, st, r.ci, "cleared");
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
            ["碎片", n] => {
                let n = n.parse::<u32>().unwrap_or(3);
                log(&format!("竞技场：开发工具：发 {n} 个星光碎片{}", if gift_n(1, d.shard as i32, n) { "" } else { "（没有发货表，没发）" }));
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
    let mut inside = false;
    match st.run.take() {
        Some(mut r) => {
            let in_arena = in_ci == Some(r.ci);
            inside = in_arena;
            let go_on = if matches!(r.role, Role::Client { .. }) {
                client_step(d, st, &mut r, in_arena, hp, revived, wcm, now)
            } else {
                lead_step(d, st, &mut r, in_arena, hp, revived, wcm, now)
            };
            if go_on {
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
note\twave 2 1\t1\nnote\twave 2 2\t2\nnote\tclear\t15\n";

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
        assert_eq!(wave_items(&d, c, &lu, 0), (2, 2));
        assert_eq!(wave_items(&d, c, &lu, 1), (3, 1));
        assert_eq!(wave_items(&d, c, &lu, 2), (2, 4));
        assert_eq!(wave_items(&d, c, &lu, 3), (3, 2));
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
                             why: String::new() };
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
