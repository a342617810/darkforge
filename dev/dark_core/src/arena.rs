//! 斗技场试炼（参数侧 rr/arena.py，地图 / 事件 / 雕像对话 sc/arena.py；用户 2026-11-10，提案 dev\item_system\斗技场试炼提案.md）：
//! - 雕像对话选了场次：场次写进 len0 / len1 两位、点亮请求 req。这里看到请求：按玩家所在地图认是哪个雕像（statue 行），
//!   扣星光碎片，两位改写成竞技场编号 + 1、点亮传送请求 warp（公共事件把玩家传进竞技场），排好这一次的出场顺序。
//! - 进了竞技场等几秒出第一波：一波魇化精英（per 个，站位不重复；nightmare.rs 强制魇化）、一波 Boss 轮流；
//!   精英位有 scarab% 换成红 / 蓝粪金龟（打死回一次红露滴 / 蓝露滴；用户 2026-11-15，一波里至少留一个真精英；
//!   不魇化、不加血，会逃跑钻地，所以不算进「这一波都死了」）；点亮各部件的出场标记，
//!   竞技场的事件启用它们、死了点亮死亡标记。这一波都死了：奖励直接发进背包（精英波 items_e 件未鉴定物品；Boss 波 items_b 件 + ash_b 个骨灰；
//!   用户 2026-11-10「每波结束的奖励也要让玩家知道 可以先发放到背包里 如果死亡再扣除」），记下发了哪些道具；
//!   不是最后一波就点亮问继续（是 → 下一波；否 / 取消 → 离开），最后一波另给 bonus 件史诗 / 传说，离开。
//! - 离开：点亮离开标记（竞技场的事件把玩家传回进来的雕像旁）。
//! - 死了：这次试炼发的道具全部收回（等发货队列发完再扣），提示「斗技场试炼失败」（notes.rs 的 arena fail）；
//!   复活点由竞技场的事件设到进来的雕像旁（run 标记亮着时玩家死了，2003[23]）。没死就离开了竞技场（别的办法出去）：奖励保留。
//!   真死了才算（death_tick）：血量 0 停了 DEATH_HOLD 还没被高难度的馈赠复活顶掉，或者血量回来了身上却没有「刚复活」的效果
//!   （以前血量一到 0 就记死亡，馈赠复活以后这一波永远不结算、离开时还按失败收回；联机分支 276824b 一起改的）。
//! - 每波出场时给敌人挂的（通用的敌人效果模块 foefx.rs，来源「斗技场」；下一波、结束时放掉）：血量随波次（hpwave，粪金龟不挂），
//!   加上 wfx 规则命中的效果包（用户 2026-11-17「给任意指定波数敌人挂自定义效果」：哪个竞技场、哪种场次、第几波、哪种敌人、几率）。
//! - 稀有度：rar（这个竞技场所在地区档的权重）× dmult（当前难度档的倍率）；骨灰 ashrar × dmult。DLC 档的传说给传说（幽影之地）。
//! - 竞技场里的提示（第几波、本波肃清、完成）：编号写进本图的 note0 起 note_n 位（竞技场的事件显示）。
//! - 试炼中退出游戏：arena_run.txt 记着在哪个竞技场、从哪个雕像进来的；下次进存档人还在那个竞技场里就传回雕像旁（不在就删掉记录）。
//! 定义 arena.txt（rr/arena.py 的 def_lines）。

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use eldenring::cs::{GameDataMan, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::foefx::Fx;
use crate::gear::{count_goods, flag_get, flag_set, gift_n, gifts_pending, give_ashes, remove_goods};
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
    /// 按波次挂的效果包
    wfx: Vec<WaveFx>,
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
            "斗技场试炼（{} 个竞技场，{} 个敌人；场次 {:?}）",
            d.colos.len(),
            d.colos.iter().map(|c| c.parts.len()).sum::<usize>(),
            d.runs.iter().map(|r| r.0).collect::<Vec<_>>()
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

struct Run {
    /// d.colos 的下标
    ci: usize,
    /// 从哪个雕像进来（离开标记 + v）
    v: u32,
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
}

static ST: Mutex<Option<St>> = Mutex::new(None);

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

/// 排好出场、点亮传送请求（场次位改成竞技场编号 + 1，公共事件把玩家传进去）
fn start_run(d: &Def, st: &mut St, ci: usize, v: u32, code: usize, cost: u32, how: &str, now: Instant) {
    let Some(&(waves, _, bonus, refund)) = code.checked_sub(1).and_then(|i| d.runs.get(i)) else { return };
    let c = &d.colos[ci];
    let to = c.x as usize + 1;
    flag_set(d.len[0], to & 1 == 1);
    flag_set(d.len[1], to & 2 == 2);
    flag_set(d.warp, true);
    let diff = diff_now(d);
    let lineup = lineup(d, c, waves, st);
    let names: Vec<String> = lineup
        .iter()
        .map(|w| w.iter().map(|&i| c.parts[i].name.clone()).collect::<Vec<_>>().join("+"))
        .collect();
    log(&format!("竞技场：{how}，竞技场 {}，{waves} 波，难度档 {diff}；出场 {}", c.x, names.join(" / ")));
    save_run(c, v);
    st.run = Some(Run {
        ci,
        v,
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
    });
}

fn start_wave(d: &Def, st: &mut St, r: &mut Run, i: usize, now: Instant) {
    let c = &d.colos[r.ci];
    r.wave = i;
    r.phase = Phase::Fight;
    r.at = now;
    r.checked = false;
    let members = &r.lineup[i];
    for &m in members {
        flag_set(c.flag + d.spawn + c.parts[m].k, true);
    }
    // 这一波要挂的：血量随波次（粪金龟不挂）+ 命中的 wfx 规则的效果包，交给敌人效果模块（出场后挂上、上限变了按比例补血）
    crate::foefx::release(FX_TAG);
    let hp_sp = d.hpwave.and_then(|(every, sp0, count)| {
        let step = (i / every).min(count);
        (step > 0).then(|| (step, sp0 + step as i32 - 1))
    });
    if let Some((step, sp)) = hp_sp {
        log(&format!("竞技场：第 {} 波敌人血量加成第 {step} 档（效果 {sp}）", i + 1));
    }
    for &m in members {
        let p = &c.parts[m];
        let mut fx = Fx::default();
        if let Some((_, sp)) = hp_sp.filter(|_| !p.scarab) {
            fx.add(&Fx::sp(sp));
        }
        let mut got: Vec<&str> = Vec::new();
        for (ri, w) in d.wfx.iter().enumerate() {
            if !w.matches(c.x, r.waves, i + 1, p) || st.roll() % 10_000 >= (w.chance * 100.0).round() as u64 {
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
            log(&format!("竞技场：第 {} 波 {} 挂效果包 {}（效果 {:?}，动作速度 ×{:.2}）", i + 1, p.name, got.join("、"), fx.sps, fx.speed));
        }
        crate::foefx::attach(FX_TAG, p.ent, &fx);
    }
    let elites: Vec<u32> = members.iter().filter(|&&m| !c.parts[m].boss && !c.parts[m].scarab).map(|&m| c.parts[m].ent).collect();
    if !elites.is_empty() {
        crate::nightmare::force(&elites, d.two.get(r.diff).copied().unwrap_or(0.0));
    }
    note(d, st, r.ci, &format!("wave {} {}", r.waves, i + 1));
    let names: Vec<&str> = members.iter().map(|&m| c.parts[m].name.as_str()).collect();
    log(&format!("竞技场：第 {} / {} 波出场 {}", i + 1, r.waves, names.join("、")));
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
    crate::foefx::release(FX_TAG);
    clear_run_file();
    st.notes.clear();
}

/// 没死就结束了（选了离开 / 打完 / 用别的办法出了竞技场）：奖励保留
fn finish(st: &mut St, r: &Run, why: &str) {
    log(&format!("竞技场：试炼结束（{why}），打完 {} / {} 波，奖励保留：{} 件物品、{} 个骨灰", r.wave + 1, r.waves, r.n_items, r.n_ashes));
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
    gift_n(1, d.shard as i32, r.cost);
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

/// 本机角色在竞技场里真的死了没有（返回 true = 这一下认定死了）：
/// 血量 0 停了 DEATH_HOLD 还没被馈赠复活顶掉；或者血量回来了身上却没有「刚复活」的效果
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
    log(&format!("竞技场：血量到 0 停了 {:.1} 秒后又有了，但不是馈赠复活，当成死亡", now.duration_since(t).as_secs_f32()));
    true
}

/// 推进一次试炼；返回 false = 试炼结束（成功、失败、中止）
fn step(d: &Def, st: &mut St, r: &mut Run, in_arena: bool, hp: i32, revived: bool, wcm: &WorldChrMan, now: Instant) -> bool {
    let c = &d.colos[r.ci];
    let f = c.flag;
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
        // 血量 0 还没认定就复活在外面了
        if r.zero_at.take().is_some() {
            r.died = true;
        }
        let t = *st.away.get_or_insert(now);
        if now - t >= AWAY_HOLD {
            st.away = None;
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
    if death_tick(r, hp, revived, now) {
        log(&format!("竞技场：玩家死亡（第 {} / {} 波）", r.wave + 1, r.waves));
    }
    // 试炼进行中的标记：结算前一直亮着（竞技场的事件这时看到玩家死了就把复活点设到雕像旁）；结算后熄灭
    let run_flag = f + d.run + r.v;
    let running = r.phase != Phase::Leaving;
    if d.run > 0 && flag_get(run_flag) == Some(!running) {
        flag_set(run_flag, running);
    }
    match r.phase {
        Phase::Going => {}
        Phase::Arrived => {
            if now - r.at >= ARRIVE_WAIT {
                start_wave(d, st, r, 0, now);
            }
        }
        Phase::Fight => {
            let members = r.lineup[r.wave].clone();
            if !r.checked && now - r.at >= CHECK_AFTER {
                r.checked = true;
                let ents: HashSet<u32> = members.iter().map(|&m| c.parts[m].ent).collect();
                let n = present(wcm, &ents);
                if n == 0 {
                    abort(d, r, &format!("第 {} 波的敌人一个都不在场上（地图没放上？）", r.wave + 1));
                    r.phase = Phase::Leaving;
                    r.at = now;
                    return true;
                }
            }
            // 粪金龟会逃跑钻地，不等它（打死了照样回露滴）
            if !r.died && members.iter().all(|&m| c.parts[m].scarab || flag_get(f + d.dead + c.parts[m].k) == Some(true)) {
                wave_reward(d, st, r);
                crate::nightmare::unforce();
                crate::foefx::release(FX_TAG);
                if r.wave + 1 >= r.waves {
                    if d.banner > 0 {
                        flag_set(f + d.banner, true);
                    } else {
                        note(d, st, r.ci, "clear");
                    }
                    r.phase = Phase::Leaving;
                    r.at = now;
                } else {
                    note(d, st, r.ci, "cleared");
                    r.phase = Phase::Ask;
                    r.at = now;
                    r.asked = false;
                }
            }
        }
        Phase::Ask => {
            if !r.asked {
                // 奖励发完、提示播完再问（竞技场的事件弹框；被取消会自己再弹，选了是 / 否才熄灭问话标记）
                if now - r.at >= ASK_DELAY && gifts_pending() == 0 && st.notes.is_empty() {
                    for k in 0..4 {
                        flag_set(f + d.ask + k, false);
                    }
                    flag_set(f + d.ask, true);
                    r.asked = true;
                    r.at = now;
                    log(&format!("竞技场：问要不要继续第 {} 波", r.wave + 2));
                }
                return true;
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
                return true;
            }
            if yes {
                log(&format!("竞技场：继续第 {} 波", r.wave + 2));
                r.phase = Phase::Next;
                r.at = now;
            } else if no {
                log("竞技场：选择离开");
                r.phase = Phase::Leaving;
                r.at = now - LEAVE_WAIT + Duration::from_secs(1);
            }
        }
        Phase::Next => {
            if now - r.at >= NEXT_WAIT {
                let i = r.wave + 1;
                start_wave(d, st, r, i, now);
            }
        }
        Phase::Leaving => {
            let wait = if r.wave + 1 >= r.waves && !r.died { CLEAR_LEAVE_WAIT } else { LEAVE_WAIT };
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

/// 开发工具（dll\dark_dev「斗技场试炼测试」写 arena_req.txt，处理完删掉）：
/// 进 <竞技场> <场次>（不扣碎片、不用站在雕像旁）/ 清场（这一波的敌人血量设 0）/ 结算（离开，奖励保留）/ 放弃（当死亡：收回奖励）/ 碎片 <n> / 状态
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
                Some(r) if r.phase != Phase::Going && r.phase != Phase::Leaving => {
                    crate::nightmare::unforce();
                    r.phase = Phase::Leaving;
                    r.at = now - LEAVE_WAIT;
                }
                _ => log("竞技场：开发工具：现在不在竞技场里的试炼中"),
            },
            ["放弃"] => {
                if let Some(r) = st.run.take() {
                    let c = &d.colos[r.ci];
                    fail(st, &r, "开发工具：放弃");
                    flag_set(c.flag + d.leave + r.v, true);
                }
            }
            ["碎片", n] => {
                let n = n.parse::<u32>().unwrap_or(3);
                log(&format!("竞技场：开发工具：发 {n} 个星光碎片{}", if gift_n(1, d.shard as i32, n) { "" } else { "（没有发货表，没发）" }));
            }
            ["状态"] => match st.run.as_ref() {
                Some(r) => log(&format!(
                    "竞技场：开发工具：竞技场 {}，{:?}，第 {} / {} 波，已发 {} 件物品、{} 个骨灰，难度档 {}{}",
                    d.colos[r.ci].x,
                    r.phase,
                    r.wave + 1,
                    r.waves,
                    r.n_items,
                    r.n_ashes,
                    r.diff,
                    if r.died { "，死过" } else { "" }
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
    let st = g.get_or_insert_with(|| St {
        next: now,
        rng: SystemTime::now().duration_since(UNIX_EPOCH).map_or(11, |t| t.as_nanos() as u64),
        run: None,
        away: None,
        stuck: None,
        takeback: Vec::new(),
        notes: Vec::new(),
        run_file_seen: false,
    });
    if now < st.next {
        return;
    }
    st.next = now + STEP;
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_ref() else { return };
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
    dev_req(d, st, wcm, now);
    match st.run.take() {
        Some(mut r) => {
            let in_arena = in_ci == Some(r.ci);
            if step(d, st, &mut r, in_arena, hp, revived, wcm, now) {
                st.run = Some(r);
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
wfx\t-\t4,8\tb\t3-6,8+\t100\t狂暴,铁壁\nwfx\t1\t-\te,s\t2\t50\tarena_rule2\nwfx\t-\t-\tb\t0\t100\tx\nwfx\t-\t-\tb\t1\t100\t\n";

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
        let mut st = St { next: Instant::now(), rng: 5, run: None, away: None, stuck: None, takeback: Vec::new(), notes: Vec::new(), run_file_seen: false };
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
        let mut st = St { next: Instant::now(), rng: 7, run: None, away: None, stuck: None, takeback: Vec::new(), notes: Vec::new(), run_file_seen: false };
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
        let mut st = St { next: Instant::now(), rng: 9, run: None, away: None, stuck: None, takeback: Vec::new(), notes: Vec::new(), run_file_seen: false };
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

    /// 真死判定：血量 0 停够了才算；馈赠复活顶掉的不算；血量回来了却没有复活效果算
    #[test]
    fn death_needs_hold_or_no_revive() {
        let d = parse(SAMPLE).unwrap();
        let t0 = Instant::now();
        let mut r = Run { ci: 0, v: 0, waves: 2, cost: 0, bonus: 0, refund: 0, lineup: vec![vec![2], vec![0]], wave: 0, phase: Phase::Fight, at: t0,
                          diff: 2, given: Vec::new(), n_items: 0, n_ashes: 0, died: false, zero_at: None, checked: false, asked: false, reasks: 0,
                          left: false };
        assert!(d.runs.len() > 0);
        assert!(!death_tick(&mut r, 0, false, t0));
        assert!(!death_tick(&mut r, 0, false, t0 + Duration::from_millis(1200)), "1.2 秒还不算");
        assert!(!death_tick(&mut r, 500, true, t0 + Duration::from_millis(1300)), "馈赠复活了");
        assert!(!r.died && r.zero_at.is_none());
        assert!(!death_tick(&mut r, 0, false, t0 + Duration::from_secs(5)));
        assert!(death_tick(&mut r, 0, false, t0 + Duration::from_secs(8)), "停了 3 秒");
        assert!(r.died && !death_tick(&mut r, 0, false, t0 + Duration::from_secs(9)), "只认一次");
        r.died = false;
        assert!(!death_tick(&mut r, 0, false, t0));
        assert!(death_tick(&mut r, 800, false, t0 + Duration::from_millis(500)), "血量回来了但没有复活效果");
    }
}
