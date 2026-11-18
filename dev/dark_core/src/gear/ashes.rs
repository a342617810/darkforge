//! 骨灰稀有度 + 词条（用户 2026-11-09 / 10，提案 dev\item_system\骨灰词条提案.md；参数侧 rr/ashcont.py，定义 ashes.txt）。
//! 照装备系统的容器做，只写玩家拥有的：
//! - 拿到原版骨灰（不管从哪来：掉落、宝箱、Boss、商店、NPC 给的；以前拿到的进存档后也算）进背包，就挑一个空容器，
//!   稀有度按 rar 行的权重抽、数值词条按稀有度抽几条（每条一样的几率，不重复）、传说带集结（召唤数量 +1，复制原版最后一行：
//!   仿身泪滴是多一个仿身，原版 5 只的变 6 只；ELDEN VINS 的仿身泪滴一次 5 个仿身，用玩家形象的也能多个），改写容器的参数行，扣掉原版那个，走发货表发容器的同一等级（游戏里弹「获得物品」）。
//! - 容器 c：道具 / 召唤效果 goods0 + 100c + L（L = 强化等级，照原版那一级的道具行复制；强化接下一级、改稀有度、节俭改消耗），
//!   强化加成 dop0 + 11c + L（照原版那一级的加成复制，没有的用 neutral；血量 × 稀有度倍率 × (1 + 坚韧)、攻击 × 稀有度倍率 × (1 + 锋锐)、
//!   各减伤 × (1 − 坚甲)、受到的削韧 × (1 − 稳固)、七种异常抗性 × (1 + 清明)、再生：每秒扣 −# % 血量 = 回血），
//!   召唤参数 buddy0 + per·c + k（照原版那几行复制，触发效果换成容器的、强化加成换成容器的；集结多复制一行，换个站位；用不到的行触发 −1）。
//! - 文字：容器每一级的名字 / 简介 / 说明 / 血条名字写进占位（同装备容器的 #DRC 占位，血条名字的编号 = 道具编号 + info2_off）。
//!   名字「稀有度 [集结·]原版名＋等级」，说明是原版说明后面接稀有度加成和词条（上稀有度的颜色）。
//! - 记录：%APPDATA%\…\角色记录\ashes_<格子>.txt（第一行角色名），一行一个容器；进存档时按记录重建参数行，扫完占位后写文字。
//!   容器不在背包 / 仓库里（丢了）就算空的，下次拿到骨灰可以再用。
//! - 容器按召唤只数分组（ashes.txt 的 pool 行；用户 2026-11-10 测出集结那一只没出来）：游戏进存档时按召唤参数的触发效果建
//!   「召唤效果 → 召唤参数」表，之后改触发效果不认，所以每个容器几行、触发效果重随写死了，这里只改行的内容、挑只数对得上的容器；
//!   集结那一组满了就不带集结。记录和分组对不上的（这次更新前拿到的）进存档后换回原版骨灰，再按规则重新抽。
//! - 仿身泪滴只放专用容器（pool 行第 5 列 = 原版骨灰本体）：游戏写死了召唤参数 20700000 才复制召唤者，mimic.rs 改那两处判断
//!   认专用容器那一段（mimic 行）；改不成就不换（留原版）。仿身那一行原版用自己那套强化加成，专用容器的第二套在 dop1。
//! - 第二期（用户 2026-11-10「做一下第二期 然后把日志做好」）：机制前缀（pre 行：爆裂 / 殉道 / 激昂 / 庇护 / 共鸣 / 战意），
//!   稀有度按 rar 行的几率带一条（每条一样的几率），名字里接在集结前面；效果和召唤日志在 fx.rs（运行时做，不改参数）。
//!   开发工具「骨灰 档= 件数= 本体= 等级= 前缀= 词条= 集结=」直接生成（照武器 / 护符的写法，dev_give；不写的照规则抽），
//!   「骨灰状态」把记录和在场的召唤物写进日志。
//! - 获取处直接是我们的骨灰（用户 2026-11-11「去掉一下原版骨灰的掉落 … 应该是以我们的作为替换」，选了「进存档时就抽好」）：
//!   ashes.txt 的 src 行 = 原版骨灰所在的掉落格（地图 / 敌人掉落表，有拿过标记的）和商店行。还没拿的每一格先抽好一个容器
//!   （记录第 8 列 = 这一格的键，「备着的」），把这一格在内存里改成容器：地上捡起、商店里看到的就是带稀有度、词条的名字，拿了不再换。
//!   - 进存档：按记录把各格改成这个角色备着的容器（别的格改回原版骨灰；同一次进游戏换角色时参数还是上一个角色改的）；
//!   - 稳定以后每 30 帧：备着的进了背包 / 仓库 → 归玩家；还没备的格抽一个。进存档后第一次另外放掉
//!     已经拿过（标记亮着）、格子没了、种类变了（一次性重随）的；平时不放（捡起时标记先亮、东西后到，会误放）；
//!   - 容器不够、仿身泪滴的判断没改成的那几格留原版，进背包后照旧换。没写进 src 的（事件直接给的、换骨灰用的没标记的格）也照旧换。

use super::*;
use eldenring::cs::{BuddyParam, EquipParamGoods, ItemLotParam_enemy, PlayerGameData, SoloParamRepository, SpEffectParam};
use eldenring::param::{BUDDY_PARAM_ST, ITEMLOT_PARAM_ST};
use std::time::Duration;

mod fx;
mod mimic;

const LEVELS: u32 = 11;
/// 发了还没进背包，多久以后不再占着容器
const PENDING: Duration = Duration::from_secs(60);

#[derive(Debug, Clone, Copy, PartialEq)]
enum Field {
    Hp,
    Atk,
    Cut,
    Poise,
    Resist,
    Regen,
    Cost,
}

impl Field {
    fn of(s: &str) -> Option<Field> {
        Some(match s {
            "hp" => Field::Hp,
            "atk" => Field::Atk,
            "cut" => Field::Cut,
            "poise" => Field::Poise,
            "resist" => Field::Resist,
            "regen" => Field::Regen,
            "cost" => Field::Cost,
            _ => return None,
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
struct Aff {
    key: String,
    field: Field,
    vals: [f32; 4],
    text: [String; 2],
}

/// 机制前缀的做法（fx.rs）
#[derive(Debug, Clone, Copy, PartialEq)]
enum PreKind {
    Blast,
    Martyr,
    Fury,
    Shelter,
    Resonance,
    Zeal,
}

impl PreKind {
    fn of(s: &str) -> Option<PreKind> {
        Some(match s {
            "blast" => PreKind::Blast,
            "martyr" => PreKind::Martyr,
            "fury" => PreKind::Fury,
            "shelter" => PreKind::Shelter,
            "resonance" => PreKind::Resonance,
            "zeal" => PreKind::Zeal,
            _ => return None,
        })
    }

    /// 要参数行（爆裂 = 子弹，激昂 / 庇护 / 共鸣 = 效果）
    fn needs_ids(self) -> bool {
        matches!(self, PreKind::Blast | PreKind::Fury | PreKind::Shelter | PreKind::Resonance)
    }
}

/// 一条机制前缀：四档数值、参数（激昂 = 血量线 %，战意 = 米）、四档的子弹 / 效果编号、名字、说明（# 换成数值）
#[derive(Debug, Clone, PartialEq)]
struct Pre {
    key: String,
    kind: PreKind,
    vals: [f32; 4],
    arg: f32,
    ids: [i32; 4],
    name: [String; 2],
    text: [String; 2],
}

#[derive(Debug, Clone, Default, PartialEq)]
struct Kind {
    base: u32,
    levels: u32,
    special: bool,
    rows: Vec<u32>,
    name: [String; 2],
    info: [String; 2],
    cap: [String; 2],
    info2: [String; 2],
}

#[derive(Debug, Clone, Copy, Default, PartialEq)]
struct Rar {
    weight: u32,
    mult: f32,
    suffixes: u32,
    rally: bool,
    /// 带一条机制前缀的几率 %
    pre: f32,
}

#[derive(Debug, Default, PartialEq)]
struct Def {
    goods0: u32,
    n: u32,
    dop0: u32,
    neutral: u32,
    buddy0: u32,
    per: u32,
    info2_off: u32,
    rar: [Rar; 4],
    affs: Vec<Aff>,
    pres: Vec<Pre>,
    bonus: [String; 2],
    /// 集结：前缀名（中、英）、说明（中、英）
    rally: [String; 4],
    lvl: Vec<[String; 2]>,
    kinds: Vec<Kind>,
    /// 容器分组：(召唤几只, 第一个容器, 几个, 只给哪种骨灰用)
    pools: Vec<(u32, u32, u32, Option<u32>)>,
    /// 仿身泪滴专用容器的召唤参数 [起, 止)（mimic.rs 改游戏的判断认这一段）
    mimic_rows: Option<(u32, u32)>,
    /// 专用容器的第二套强化加成起点（0 = 没有）：起 + 11 × 容器 + 等级
    dop1: u32,
    /// 原版骨灰各级的道具编号 → (种类序号, 等级)
    by_id: HashMap<u32, (usize, u32)>,
    /// 原版骨灰的获取格（src 行）
    srcs: Vec<AshSrc>,
    /// 局内难度：(玩家身上那一档的效果, 召唤物挂的造成伤害效果)（diffash 行，rr/difficulty.py；fx.rs 照玩家的档给召唤物挂）
    diff_ash: Vec<(i32, i32)>,
}

/// 获取格在哪张表
#[derive(Debug, Clone, Copy, PartialEq)]
enum SrcAt {
    Map,
    Enemy,
    Shop,
}

/// 原版骨灰的一个获取格：键（记录里用）、哪张表、行、格（0~7，商店 0）、原版骨灰道具、拿过的标记（商店 = 库存计数标记起点；0 = 看不出来）
#[derive(Debug, Clone, PartialEq)]
struct AshSrc {
    key: String,
    at: SrcAt,
    row: u32,
    slot: u8,
    goods: u32,
    flag: u32,
}

impl Def {
    /// 这个容器召唤几只（不在任何一组里 = None）
    fn count_of(&self, idx: u32) -> Option<u32> {
        self.pools.iter().find(|p| idx >= p.1 && idx < p.1 + p.2).map(|p| p.0)
    }

    /// 这种骨灰有专用容器
    fn dedicated(&self, kind: u32) -> bool {
        self.pools.iter().any(|p| p.3 == Some(kind))
    }

    /// 这一组能放这种骨灰（专用的只放那一种；有专用的骨灰不放通用组）
    fn pool_takes(&self, p: &(u32, u32, u32, Option<u32>), kind: u32) -> bool {
        if self.dedicated(kind) { p.3 == Some(kind) } else { p.3.is_none() }
    }

    /// 记录放在这个容器里对不对（只数、专用）
    fn fits(&self, rec: &AshRec, k: &Kind) -> bool {
        self.pools.iter().find(|p| rec.idx >= p.1 && rec.idx < p.1 + p.2).is_some_and(|p| p.0 == summons(rec, k) && self.pool_takes(p, k.base))
    }
}

/// 这个骨灰召唤几只：原版几行 + 集结（同 write_container 写的行数）
fn summons(rec: &AshRec, k: &Kind) -> u32 {
    k.rows.len() as u32 + rec_extra(rec, k) as u32
}

/// 集结多写的一行（原版不到 6 只；用玩家形象的也行，2026-11-10 起）
fn rec_extra(rec: &AshRec, k: &Kind) -> bool {
    rec.rally && k.rows.len() < 6
}

/// 抽好的骨灰挑一个空容器（只数对得上的那一组）；集结那一组满了就不带集结。返回 (容器, 是不是去掉了集结)
fn place(def: &Def, rec: &mut AshRec, k: &Kind, busy: impl Fn(u32) -> bool) -> Option<(u32, bool)> {
    let pick = |need: u32| def.pools.iter().filter(|p| p.0 == need && def.pool_takes(p, k.base)).flat_map(|p| p.1..p.1 + p.2).find(|&i| !busy(i));
    if let Some(i) = pick(summons(rec, k)) {
        rec.idx = i;
        return Some((i, false));
    }
    if rec.rally {
        rec.rally = false;
        if let Some(i) = pick(summons(rec, k)) {
            rec.idx = i;
            return Some((i, true));
        }
        rec.rally = true;
    }
    None
}

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    let s2 = |a: &str, b: &str| [unesc(a), unesc(b)];
    for f in lines(text) {
        match (f[0], f.len()) {
            ("cont", 8..) => {
                let v: Vec<u32> = f[1..8].iter().filter_map(|x| x.parse().ok()).collect();
                if v.len() == 7 {
                    (d.goods0, d.n, d.dop0, d.neutral, d.buddy0, d.per, d.info2_off) = (v[0], v[1], v[2], v[3], v[4], v[5], v[6]);
                }
            }
            ("pool", 4..) => {
                if let (Ok(m), Ok(first), Ok(n)) = (f[1].parse::<u32>(), f[2].parse::<u32>(), f[3].parse::<u32>()) {
                    if m > 0 && n > 0 {
                        d.pools.push((m, first, n, f.get(4).and_then(|x| x.parse().ok())));
                    }
                }
            }
            ("mimic", 3..) => {
                if let (Ok(lo), Ok(hi)) = (f[1].parse::<u32>(), f[2].parse::<u32>()) {
                    d.mimic_rows = (hi > lo).then_some((lo, hi));
                }
            }
            ("dop1", 2..) => d.dop1 = f[1].parse().unwrap_or(0),
            ("diffash", 3..) => {
                if let (Ok(a), Ok(b)) = (f[1].parse::<i32>(), f[2].parse::<i32>()) {
                    if a > 0 && b > 0 {
                        d.diff_ash.push((a, b));
                    }
                }
            }
            ("src", 6..) => {
                let at = match f[1] {
                    "m" => SrcAt::Map,
                    "e" => SrcAt::Enemy,
                    "s" => SrcAt::Shop,
                    _ => continue,
                };
                if let (Ok(row), Ok(slot), Ok(goods), Ok(flag)) = (f[2].parse::<u32>(), f[3].parse::<u8>(), f[4].parse::<u32>(), f[5].parse::<u32>()) {
                    if slot < 8 {
                        d.srcs.push(AshSrc { key: format!("{}{row}.{slot}", f[1]), at, row, slot, goods, flag });
                    }
                }
            }
            ("rar", 6..) => {
                if let (Ok(r), Ok(w), Ok(m), Ok(s)) = (f[1].parse::<usize>(), f[2].parse(), f[3].parse(), f[4].parse()) {
                    if r < 4 {
                        let pre = f.get(6).and_then(|x| x.parse().ok()).unwrap_or(0.0);
                        d.rar[r] = Rar { weight: w, mult: m, suffixes: s, rally: f[5] == "1", pre };
                    }
                }
            }
            ("aff", 6..) => {
                let v: Vec<f32> = f[3].split(',').filter_map(|x| x.parse().ok()).collect();
                if let (Some(field), Ok(vals)) = (Field::of(f[2]), <[f32; 4]>::try_from(v)) {
                    d.affs.push(Aff { key: f[1].to_string(), field, vals, text: s2(f[4], f[5]) });
                }
            }
            ("pre", 10..) => {
                let v: Vec<f32> = f[3].split(',').filter_map(|x| x.parse().ok()).collect();
                let ids: Vec<i32> = f[5].split(',').filter_map(|x| x.parse().ok()).collect();
                if let (Some(kind), Ok(vals), Ok(ids), Ok(arg)) = (PreKind::of(f[2]), <[f32; 4]>::try_from(v), <[i32; 4]>::try_from(ids), f[4].parse::<f32>()) {
                    if !kind.needs_ids() || ids.iter().all(|&i| i > 0) {
                        d.pres.push(Pre { key: f[1].to_string(), kind, vals, arg, ids, name: s2(f[6], f[7]), text: s2(f[8], f[9]) });
                    }
                }
            }
            ("bonus", 3..) => d.bonus = s2(f[1], f[2]),
            ("rally", 5..) => d.rally = [unesc(f[1]), unesc(f[2]), unesc(f[3]), unesc(f[4])],
            ("lvl", 4..) => {
                if let Ok(lv) = f[1].parse::<usize>() {
                    if d.lvl.len() <= lv {
                        d.lvl.resize(lv + 1, [String::new(), String::new()]);
                    }
                    d.lvl[lv] = s2(f[2], f[3]);
                }
            }
            ("kind", 13..) => {
                let (Ok(base), Ok(levels)) = (f[1].parse::<u32>(), f[2].parse::<u32>()) else { continue };
                let rows: Vec<u32> = f[4].split(',').filter_map(|x| x.parse().ok()).collect();
                if rows.is_empty() {
                    continue;
                }
                d.kinds.push(Kind {
                    base,
                    levels: levels.clamp(1, LEVELS),
                    special: f[3] == "1",
                    rows,
                    name: s2(f[5], f[6]),
                    info: s2(f[7], f[8]),
                    cap: s2(f[9], f[10]),
                    info2: s2(f[11], f[12]),
                });
            }
            _ => {}
        }
    }
    for (ki, k) in d.kinds.iter().enumerate() {
        for lv in 0..k.levels {
            d.by_id.insert(k.base + lv, (ki, lv));
        }
    }
    let by_id = &d.by_id;
    d.srcs.retain(|s| by_id.contains_key(&s.goods));
    let mut seen = HashSet::new();
    d.srcs.retain(|s| seen.insert(s.key.clone()));
    (d.n > 0 && d.per > 0 && !d.kinds.is_empty() && d.rar.iter().any(|r| r.weight > 0)).then_some(d)
}

static ADEF: OnceLock<Option<Def>> = OnceLock::new();

fn adef() -> Option<&'static Def> {
    ADEF.get_or_init(|| parse(&fs::read_to_string(dir().join("ashes.txt")).unwrap_or_default())).as_ref()
}

pub(super) fn describe() -> String {
    match adef() {
        Some(d) => format!(
            "骨灰稀有度（{} 种骨灰、{} 个容器、{} 条数值词条、{} 条机制前缀、{} 个获取格直接放容器）",
            d.kinds.len(),
            d.n,
            d.affs.len(),
            d.pres.len(),
            d.srcs.len()
        ),
        None => "骨灰稀有度（没有 ashes.txt，不管）".into(),
    }
}

/// 一个容器：序号、原版骨灰本体编号、稀有度 0~3、数值词条的键、带不带集结、机制前缀的键、
/// 备给哪个获取格（还没拿到；None = 玩家的）
#[derive(Debug, Clone, PartialEq)]
struct AshRec {
    idx: u32,
    kind: u32,
    rar: usize,
    affs: Vec<String>,
    rally: bool,
    pre: Option<String>,
    src: Option<String>,
}

fn rec_line(r: &AshRec) -> String {
    format!(
        "c\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
        r.idx,
        r.kind,
        r.rar,
        if r.affs.is_empty() { "-".to_string() } else { r.affs.join(",") },
        r.rally as u8,
        r.pre.as_deref().unwrap_or("-"),
        r.src.as_deref().unwrap_or("-")
    )
}

fn rec_parse(line: &str) -> Option<AshRec> {
    let f: Vec<&str> = line.split('\t').collect();
    if f.len() < 6 || f[0] != "c" {
        return None;
    }
    Some(AshRec {
        idx: f[1].parse().ok()?,
        kind: f[2].parse().ok()?,
        rar: f[3].parse::<usize>().ok()?.min(3),
        affs: f[4].split(',').filter(|x| !x.is_empty() && *x != "-").map(str::to_string).collect(),
        rally: f[5] == "1",
        pre: f.get(6).filter(|x| !x.is_empty() && **x != "-").map(|x| x.to_string()),
        src: f.get(7).filter(|x| !x.is_empty() && **x != "-").map(|x| x.to_string()),
    })
}

fn rec_file(slot: i32) -> PathBuf {
    data_dir().join(format!("ashes_{slot}.txt"))
}

/// 记录文件：第一行「name<TAB>角色名」，角色名对不上就当没有
fn rec_load_text(text: &str, name: &str) -> HashMap<u32, AshRec> {
    let mut it = text.lines().map(|l| l.trim_start_matches('\u{feff}'));
    if it.next().and_then(|l| l.strip_prefix("name\t")) != Some(name) {
        return HashMap::new();
    }
    it.filter_map(rec_parse).map(|r| (r.idx, r)).collect()
}

fn rec_text(name: &str, recs: &HashMap<u32, AshRec>) -> String {
    let mut v: Vec<&AshRec> = recs.values().collect();
    v.sort_by_key(|r| r.idx);
    let mut out = format!("name\t{name}\n");
    for r in v {
        out += &rec_line(r);
        out.push('\n');
    }
    out
}

#[derive(Default)]
struct AshSt {
    who: Option<(i32, String)>,
    recs: HashMap<u32, AshRec>,
    /// 发了还没进背包的容器 → 什么时候发的
    pending: HashMap<u32, Instant>,
    /// 文字要重写（进存档、换了容器）；上次写文字时占位扫了几遍
    dirty: bool,
    scans: u32,
    full_told: bool,
    /// 记录和容器分组对不上的（这次更新前拿到的）：稳定以后背包里的换回原版骨灰
    stale: Vec<AshRec>,
    /// 开发工具「骨灰转换 关」：先不把原版骨灰换成容器（拿原版的对照）
    paused: bool,
    /// 进存档后看过一遍获取格了（放掉拿过的、格子没了的备用容器只在这一遍做）
    src_seen: bool,
    /// 获取格备不了容器（容器不够）已经写过日志
    src_full_told: bool,
}

impl AshSt {
    /// 这个容器备给了某个获取格（还没拿到）
    fn reserved(&self, idx: u32) -> bool {
        self.recs.get(&idx).is_some_and(|r| r.src.is_some())
    }
}

/// 开发工具指定的骨灰（devgive 的「骨灰」行）：None / 空 = 照规则抽
#[derive(Debug, Clone, Default, PartialEq)]
pub(super) struct AshSpec {
    /// 原版骨灰本体编号
    pub(super) kind: Option<u32>,
    pub(super) rar: Option<usize>,
    /// 强化等级（超过这种骨灰的上限就用上限）
    pub(super) lv: u32,
    /// None = 照几率；Some(None) = 不带；Some(Some(键)) = 指定
    pub(super) pre: Option<Option<String>>,
    /// 数值词条的键（空 = 照稀有度抽）
    pub(super) affs: Vec<String>,
    /// None = 照规则（传说带）
    pub(super) rally: Option<bool>,
}

static AST: Mutex<Option<AshSt>> = Mutex::new(None);

fn save(a: &AshSt) {
    let Some(who) = a.who.as_ref() else { return };
    let path = rec_file(who.0);
    if let Some(p) = path.parent() {
        let _ = fs::create_dir_all(p);
    }
    rec_set_aside(&path, &who.1); // 这一格原来是别的角色的记录：先另存（gear.rs）
    let tmp = path.with_extension("tmp");
    if fs::write(&tmp, rec_text(&who.1, &a.recs)).is_ok() {
        let _ = fs::rename(&tmp, &path);
    }
}

/// 抽一个：稀有度按权重，数值词条按稀有度几条（每条一样、不重复），机制前缀按稀有度的几率带一条（每条一样），
/// 传说带集结（召唤数量 +1；原版已经 5 只、用玩家形象的不带，指定了也不带）。spec = 开发工具指定的（没写的照规则）
fn roll(def: &Def, idx: u32, k: &Kind, rng: &mut Rng, spec: Option<&AshSpec>) -> AshRec {
    let w: Vec<u32> = def.rar.iter().map(|r| r.weight).collect();
    let rar = match spec.and_then(|s| s.rar) {
        Some(r) => r.min(3),
        None => choose_weighted(rng, &w, 1).first().copied().unwrap_or(0).min(3),
    };
    let mut want: Vec<String> = Vec::new();
    for key in spec.map_or(&[][..], |s| &s.affs[..]) {
        if def.affs.iter().any(|a| a.key == *key) && !want.contains(key) {
            want.push(key.clone());
        }
    }
    let affs = if want.is_empty() {
        choose(rng, def.affs.len(), def.rar[rar].suffixes as usize).into_iter().map(|i| def.affs[i].key.clone()).collect()
    } else {
        want
    };
    let can_rally = k.rows.len() < 6;
    let rally = can_rally && spec.and_then(|s| s.rally).unwrap_or(def.rar[rar].rally);
    let pre = match spec.and_then(|s| s.pre.clone()) {
        Some(p) => p.filter(|key| def.pres.iter().any(|x| x.key == *key)),
        None => {
            let hit = !def.pres.is_empty() && (rng.below(10000) as f32) < def.rar[rar].pre * 100.0;
            hit.then(|| def.pres[rng.below(def.pres.len() as u64) as usize].key.clone())
        }
    };
    AshRec { idx, kind: k.base, rar, affs, rally, pre, src: None }
}

/// 这个容器某一类数值词条加起来多少（%）
fn total(def: &Def, rec: &AshRec, field: Field) -> f32 {
    rec.affs.iter().filter_map(|key| def.affs.iter().find(|a| a.key == *key)).filter(|a| a.field == field).map(|a| a.vals[rec.rar.min(3)]).sum()
}

fn num(v: f32) -> String {
    if (v - v.round()).abs() < 1e-4 { format!("{}", v.round() as i32) } else { format!("{:.1}", v).trim_end_matches('0').to_string() }
}

/// 一个容器第 lv 级的（名字, 简介, 说明, 血条名字），lang 0 中文 / 1 英文
fn compose(lib: &Lib, def: &Def, k: &Kind, rec: &AshRec, lv: u32, lang: usize) -> [String; 4] {
    let r = rec.rar.min(3);
    let tag = lib.rar.get(r).map_or(String::new(), |x| x[lang].clone());
    let sep = if lang == 0 { "·" } else { " " };
    let mech = rec.pre.as_ref().and_then(|key| def.pres.iter().find(|p| p.key == *key));
    let mut pre = mech.map_or(String::new(), |p| format!("{}{sep}", p.name[lang]));
    if rec.rally {
        pre += &format!("{}{sep}", def.rally[lang]);
    }
    let lvl = def.lvl.get(lv as usize).map_or(String::new(), |x| x[lang].clone());
    let name = format!("{tag} {pre}{}{lvl}", k.name[lang]).trim().to_string();
    let mut lines: Vec<String> = Vec::new();
    let m = def.rar[r].mult;
    if m > 1.0 + 1e-4 {
        lines.push(def.bonus[lang].replace('#', &num((m - 1.0) * 100.0)));
    }
    if let Some(p) = mech {
        lines.push(p.text[lang].replace('#', &num(p.vals[r])));
    }
    for key in &rec.affs {
        if let Some(a) = def.affs.iter().find(|a| a.key == *key) {
            lines.push(a.text[lang].replace('#', &num(a.vals[r])));
        }
    }
    if rec.rally {
        lines.push(def.rally[2 + lang].clone());
    }
    let painted: Vec<String> = lines.iter().map(|s| paint(lib, r, s)).collect();
    let cap = if painted.is_empty() { k.cap[lang].clone() } else { format!("{}\n\n{}", k.cap[lang], painted.join("\n")) };
    [name, k.info[lang].clone(), cap, k.info2[lang].clone()]
}

fn dop_get(b: &BUDDY_PARAM_ST, lv: u32) -> i32 {
    match lv {
        0 => b.doping_sp_effect_lv0(),
        1 => b.doping_sp_effect_lv1(),
        2 => b.doping_sp_effect_lv2(),
        3 => b.doping_sp_effect_lv3(),
        4 => b.doping_sp_effect_lv4(),
        5 => b.doping_sp_effect_lv5(),
        6 => b.doping_sp_effect_lv6(),
        7 => b.doping_sp_effect_lv7(),
        8 => b.doping_sp_effect_lv8(),
        9 => b.doping_sp_effect_lv9(),
        _ => b.doping_sp_effect_lv10(),
    }
}

fn dop_set(b: &mut BUDDY_PARAM_ST, lv: u32, v: i32) {
    match lv {
        0 => b.set_doping_sp_effect_lv0(v),
        1 => b.set_doping_sp_effect_lv1(v),
        2 => b.set_doping_sp_effect_lv2(v),
        3 => b.set_doping_sp_effect_lv3(v),
        4 => b.set_doping_sp_effect_lv4(v),
        5 => b.set_doping_sp_effect_lv5(v),
        6 => b.set_doping_sp_effect_lv6(v),
        7 => b.set_doping_sp_effect_lv7(v),
        8 => b.set_doping_sp_effect_lv8(v),
        9 => b.set_doping_sp_effect_lv9(v),
        _ => b.set_doping_sp_effect_lv10(v),
    }
}

fn scale_i16(v: i16, pct: f32) -> i16 {
    if v <= 0 { v } else { ((v as f32) * (1.0 - pct / 100.0)).round().max(1.0) as i16 }
}

/// 改写一个容器的参数行（道具 11 级、强化加成 11 级、召唤参数这一组的几行）
fn write_container(def: &Def, rec: &AshRec) -> Result<(), String> {
    let k = def.kinds.iter().find(|k| k.base == rec.kind).ok_or_else(|| format!("骨灰 {} 不在定义里", rec.kind))?;
    let slots = def.count_of(rec.idx).ok_or_else(|| format!("容器 {} 不在任何一组里", rec.idx))?;
    if !def.fits(rec, k) {
        return Err(format!("容器 {} 是召唤 {slots} 只的（或者是别的骨灰专用的），这个骨灰召唤 {} 只", rec.idx, summons(rec, k)));
    }
    let repo = unsafe { SoloParamRepository::instance_mut() }.map_err(|_| "参数还没载入".to_string())?;
    let cbase = def.goods0 + 100 * rec.idx;
    let r = rec.rar.min(3);
    let m = def.rar[r].mult;
    let (hp, atk, cut, poise, res, regen, cost) = (
        total(def, rec, Field::Hp),
        total(def, rec, Field::Atk),
        total(def, rec, Field::Cut),
        total(def, rec, Field::Poise),
        total(def, rec, Field::Resist),
        total(def, rec, Field::Regen),
        total(def, rec, Field::Cost),
    );
    for lv in 0..k.levels {
        let id = cbase + lv;
        let src = param_bytes::<EquipParamGoods>(repo, k.base + lv).ok_or_else(|| format!("原版骨灰 {} 不在参数里", k.base + lv))?;
        let dst = param_mut::<EquipParamGoods>(repo, id).ok_or_else(|| format!("容器道具 {id} 不在参数里（这次不是用重随的模式启动的？）"))?;
        dst.copy_from_slice(&src);
        let g = repo.get_mut::<EquipParamGoods>(id).ok_or("容器道具读不到")?;
        g.set_ref_id_default(id as i32);
        g.set_reinforce_goods_id(if lv + 1 < k.levels { (id + 1) as i32 } else { -1 });
        g.set_rarity(r as u8);
        if cost > 0.0 {
            g.set_consume_mp(scale_i16(g.consume_mp(), cost));
            g.set_consume_hp(scale_i16(g.consume_hp(), cost));
        }
    }
    // 每一行原版用哪套强化加成（仿身泪滴：银色泪滴 290000 系列、仿身 290200 系列）；第二套写在 dop1（只有专用容器有那几行）
    let series: Vec<Vec<i32>> = k
        .rows
        .iter()
        .map(|&i| repo.get::<BuddyParam>(i).map(|b| (0..LEVELS).map(|lv| dop_get(b, lv)).collect()).ok_or_else(|| format!("原版召唤参数 {i} 读不到")))
        .collect::<Result<_, _>>()?;
    let mut uniq: Vec<Vec<i32>> = Vec::new();
    for x in &series {
        if !uniq.contains(x) {
            uniq.push(x.clone());
        }
    }
    let two = uniq.len() > 1 && def.dop1 > 0 && repo.get::<SpEffectParam>(def.dop1 + LEVELS * rec.idx).is_some();
    let base_of = |si: usize| if si >= 1 && two { def.dop1 + LEVELS * rec.idx } else { def.dop0 + LEVELS * rec.idx };
    for (si, dops) in uniq.iter().enumerate().take(if two { 2 } else { 1 }) {
    for lv in 0..LEVELS {
        let v = dops[lv as usize];
        let from = if v > 0 && repo.get::<SpEffectParam>(v as u32).is_some() { v as u32 } else { def.neutral };
        let src = param_bytes::<SpEffectParam>(repo, from).ok_or_else(|| format!("强化加成 {from} 读不到"))?;
        let id = base_of(si) + lv;
        let dst = param_mut::<SpEffectParam>(repo, id).ok_or_else(|| format!("容器的强化加成 {id} 不在参数里"))?;
        dst.copy_from_slice(&src);
        let s = repo.get_mut::<SpEffectParam>(id).ok_or("强化加成读不到")?;
        let hm = m * (1.0 + hp / 100.0);
        s.set_max_hp_rate(s.max_hp_rate() * hm);
        let am = m * (1.0 + atk / 100.0);
        s.set_physics_attack_power_rate(s.physics_attack_power_rate() * am);
        s.set_magic_attack_power_rate(s.magic_attack_power_rate() * am);
        s.set_fire_attack_power_rate(s.fire_attack_power_rate() * am);
        s.set_thunder_attack_power_rate(s.thunder_attack_power_rate() * am);
        s.set_dark_attack_power_rate(s.dark_attack_power_rate() * am);
        // 用玩家形象的（仿身泪滴）伤害走玩家那一套，原版 +10 也是靠这几项涨
        s.set_atk_player_dmg_correct_rate_physics(s.atk_player_dmg_correct_rate_physics() * am);
        s.set_atk_player_dmg_correct_rate_magic(s.atk_player_dmg_correct_rate_magic() * am);
        s.set_atk_player_dmg_correct_rate_fire(s.atk_player_dmg_correct_rate_fire() * am);
        s.set_atk_player_dmg_correct_rate_thunder(s.atk_player_dmg_correct_rate_thunder() * am);
        s.set_atk_player_dmg_correct_rate_dark(s.atk_player_dmg_correct_rate_dark() * am);
        if cut > 0.0 {
            let c = 1.0 - cut / 100.0;
            s.set_slash_damage_cut_rate(s.slash_damage_cut_rate() * c);
            s.set_blow_damage_cut_rate(s.blow_damage_cut_rate() * c);
            s.set_thrust_damage_cut_rate(s.thrust_damage_cut_rate() * c);
            s.set_neutral_damage_cut_rate(s.neutral_damage_cut_rate() * c);
            s.set_magic_damage_cut_rate(s.magic_damage_cut_rate() * c);
            s.set_fire_damage_cut_rate(s.fire_damage_cut_rate() * c);
            s.set_thunder_damage_cut_rate(s.thunder_damage_cut_rate() * c);
            s.set_dark_damage_cut_rate(s.dark_damage_cut_rate() * c);
        }
        if poise > 0.0 {
            s.set_sa_receive_damage_rate(s.sa_receive_damage_rate() * (1.0 - poise / 100.0));
        }
        if res > 0.0 {
            let x = 1.0 + res / 100.0;
            s.set_regist_poizon_change_rate(s.regist_poizon_change_rate() * x);
            s.set_regist_disease_change_rate(s.regist_disease_change_rate() * x);
            s.set_regist_blood_change_rate(s.regist_blood_change_rate() * x);
            s.set_regist_curse_change_rate(s.regist_curse_change_rate() * x);
            s.set_regist_freeze_change_rate(s.regist_freeze_change_rate() * x);
            s.set_regist_sleep_change_rate(s.regist_sleep_change_rate() * x);
            s.set_regist_madness_change_rate(s.regist_madness_change_rate() * x);
        }
        if regen > 0.0 && s.change_hp_rate() == 0.0 {
            s.set_change_hp_rate(-regen);
            s.set_motion_interval(1.0);
        }
    }
    }
    // 第 j 行（集结多的那行同原版最后一行）用哪套
    let row_base = |j: usize| {
        let x = &series[j.min(series.len() - 1)];
        base_of(uniq.iter().position(|u| u == x).unwrap_or(0))
    };
    let rows: Vec<Vec<u8>> = k
        .rows
        .iter()
        .map(|&i| param_bytes::<BuddyParam>(repo, i).ok_or_else(|| format!("原版召唤参数 {i} 读不到")))
        .collect::<Result<_, _>>()?;
    for j in 0..slots {
        let id = def.buddy0 + def.per * rec.idx + j;
        let dst = param_mut::<BuddyParam>(repo, id).ok_or_else(|| format!("容器的召唤参数 {id} 不在参数里（这次不是用重随的模式启动的？）"))?;
        let extra = j as usize >= rows.len();
        dst.copy_from_slice(if extra { rows.last().ok_or("原版没有召唤参数")? } else { &rows[j as usize] });
        let p = repo.get_mut::<BuddyParam>(id).ok_or("召唤参数读不到")?;
        p.set_trigger_sp_effect_id(cbase as i32); // 重随已经写死了同一个，这里只是保险
        for lv in 0..LEVELS {
            dop_set(p, lv, (row_base(j as usize) + lv) as i32);
        }
        if extra {
            // 集结多的那一只：只有一只的照它镜像站到另一边，几只的往后站一点
            if rows.len() == 1 {
                let x = p.x_offset();
                p.set_x_offset(if x.abs() > 0.3 { -x } else { x + 1.5 });
            } else {
                p.set_z_offset(p.z_offset() - 1.5);
            }
        }
    }
    Ok(())
}

/// 背包 + 仓库里的容器序号
fn held(def: &Def, pgd: &PlayerGameData) -> HashSet<u32> {
    let mut out = HashSet::new();
    let mut add = |inv: &EquipInventoryData| {
        for it in inv.items_data.items() {
            if it.item_id.category() as u8 != INV_GOODS {
                continue;
            }
            let id = it.item_id.param_id();
            if id >= def.goods0 && id < def.goods0 + 100 * def.n && (id - def.goods0) % 100 < LEVELS {
                out.insert((id - def.goods0) / 100);
            }
        }
    };
    add(&pgd.equipment.equip_inventory_data);
    if let Some(s) = &pgd.storage {
        add(&**s);
    }
    out
}

/// 背包里这个容器的道具：(道具编号, 等级)
fn in_bag(def: &Def, pgd: &PlayerGameData, idx: u32) -> Vec<(u32, u32)> {
    let base = def.goods0 + 100 * idx;
    pgd.equipment
        .equip_inventory_data
        .items_data
        .items()
        .filter(|it| it.item_id.category() as u8 == INV_GOODS && it.quantity > 0)
        .map(|it| it.item_id.param_id())
        .filter(|&id| id >= base && id < base + LEVELS)
        .map(|id| (id, id - base))
        .collect()
}

/// 背包里的原版骨灰：(道具编号, 种类序号, 等级)
fn vanilla(def: &Def, pgd: &PlayerGameData) -> Vec<(u32, usize, u32)> {
    let mut v: Vec<(u32, usize, u32)> = pgd
        .equipment
        .equip_inventory_data
        .items_data
        .items()
        .filter(|it| it.item_id.category() as u8 == INV_GOODS && it.quantity > 0)
        .filter_map(|it| def.by_id.get(&it.item_id.param_id()).map(|&(k, lv)| (it.item_id.param_id(), k, lv)))
        .collect();
    v.sort();
    v
}

fn lot_get(p: &ITEMLOT_PARAM_ST, slot: u8) -> i32 {
    match slot {
        0 => p.lot_item_id01(),
        1 => p.lot_item_id02(),
        2 => p.lot_item_id03(),
        3 => p.lot_item_id04(),
        4 => p.lot_item_id05(),
        5 => p.lot_item_id06(),
        6 => p.lot_item_id07(),
        _ => p.lot_item_id08(),
    }
}

fn lot_set(p: &mut ITEMLOT_PARAM_ST, slot: u8, v: i32) {
    match slot {
        0 => p.set_lot_item_id01(v),
        1 => p.set_lot_item_id02(v),
        2 => p.set_lot_item_id03(v),
        3 => p.set_lot_item_id04(v),
        4 => p.set_lot_item_id05(v),
        5 => p.set_lot_item_id06(v),
        6 => p.set_lot_item_id07(v),
        _ => p.set_lot_item_id08(v),
    }
}

/// 获取格现在放的东西（行不在参数里 = None）
fn src_get(repo: &SoloParamRepository, s: &AshSrc) -> Option<i32> {
    match s.at {
        SrcAt::Map => repo.get::<ItemLotParam_map>(s.row).map(|p| lot_get(p, s.slot)),
        SrcAt::Enemy => repo.get::<ItemLotParam_enemy>(s.row).map(|p| lot_get(p, s.slot)),
        SrcAt::Shop => repo.get::<ShopLineupParam>(s.row).map(|p| p.equip_id()),
    }
}

fn src_put(repo: &mut SoloParamRepository, s: &AshSrc, v: i32) {
    match s.at {
        SrcAt::Map => {
            if let Some(p) = repo.get_mut::<ItemLotParam_map>(s.row) {
                lot_set(p, s.slot, v);
            }
        }
        SrcAt::Enemy => {
            if let Some(p) = repo.get_mut::<ItemLotParam_enemy>(s.row) {
                lot_set(p, s.slot, v);
            }
        }
        SrcAt::Shop => {
            if let Some(p) = repo.get_mut::<ShopLineupParam>(s.row) {
                p.set_equip_id(v);
            }
        }
    }
}

/// 这一格拿过了：掉落格看拿过标记；商店看库存计数（限 1 件的，计数占几位不确定，同回购商店整段看）；没有标记 = 看不出来
fn src_taken(s: &AshSrc) -> bool {
    if s.flag == 0 {
        return false;
    }
    match s.at {
        SrcAt::Shop => (s.flag..s.flag + STOCK_BITS).any(|f| flag_get(f) == Some(true)),
        _ => flag_get(s.flag) == Some(true),
    }
}

/// 这一格该放什么：备着容器就放容器（同一等级），没备就放原版骨灰
fn src_want(def: &Def, mine: &HashMap<&str, u32>, s: &AshSrc) -> i32 {
    let lv = def.by_id.get(&s.goods).map_or(0, |x| x.1);
    match mine.get(s.key.as_str()) {
        Some(&idx) => (def.goods0 + 100 * idx + lv) as i32,
        None => s.goods as i32,
    }
}

/// 把各获取格改成这个角色备着的容器（没备的改回原版骨灰）。格子里现在既不是原版那个、也不是容器（别的东西改过）就不动。
/// 返回 (放了容器的格, 改回原版的格, 对不上没动的格)
fn src_apply(def: &Def, a: &AshSt) -> (u32, u32, u32) {
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return (0, 0, 0) };
    let mine: HashMap<&str, u32> = a.recs.values().filter_map(|r| r.src.as_deref().map(|k| (k, r.idx))).collect();
    let ours = |v: i32| v >= def.goods0 as i32 && (v as u32) < def.goods0 + 100 * def.n;
    let (mut set, mut back, mut bad) = (0, 0, 0);
    for s in &def.srcs {
        let want = src_want(def, &mine, s);
        let Some(cur) = src_get(repo, s) else {
            bad += 1;
            continue;
        };
        if cur == want {
            set += (want != s.goods as i32) as u32;
            continue;
        }
        if cur != s.goods as i32 && !ours(cur) {
            bad += 1;
            if bad <= 3 {
                log(&format!("骨灰：获取格 {} 现在放的是 {cur}（不是原版骨灰 {}，也不是容器），不动", s.key, s.goods));
            }
            continue;
        }
        src_put(repo, s, want);
        if want == s.goods as i32 { back += 1 } else { set += 1 }
    }
    (set, back, bad)
}

/// 获取格（稳定以后每 30 帧，now = 背包 + 仓库里的容器）：备着的进了背包 → 归玩家；还没拿、没备的格抽一个容器备上。
/// 进存档后第一遍另外放掉拿过了（标记亮着、人没拿到这一个）、格子没了、种类变了的。返回记录变没变
fn src_tick(def: &Def, a: &mut AshSt, now: &HashSet<u32>, rng: &mut Rng) -> bool {
    let first = !a.src_seen;
    a.src_seen = true;
    let (mut got, mut freed, mut made) = (0, 0, 0);
    let mine: Vec<(u32, String, u32)> = a.recs.values().filter_map(|r| r.src.clone().map(|k| (r.idx, k, r.kind))).collect();
    for (idx, key, kind) in mine {
        if now.contains(&idx) {
            if let Some(r) = a.recs.get_mut(&idx) {
                r.src = None;
            }
            got += 1;
            log(&format!("骨灰：获取格 {key} 备着的容器 {idx} 拿到了"));
            continue;
        }
        if first {
            let s = def.srcs.iter().find(|s| s.key == key);
            let same = s.is_some_and(|s| def.by_id.get(&s.goods).map(|x| def.kinds[x.0].base) == Some(kind));
            if !same || s.is_some_and(src_taken) {
                a.recs.remove(&idx);
                freed += 1;
            }
        }
    }
    let have: HashSet<String> = a.recs.values().filter_map(|r| r.src.clone()).collect();
    for s in &def.srcs {
        if have.contains(&s.key) || src_taken(s) {
            continue;
        }
        let Some(&(ki, _)) = def.by_id.get(&s.goods) else { continue };
        let k = &def.kinds[ki];
        if def.dedicated(k.base) && !mimic::ok() {
            continue; // 仿身泪滴的判断没改成：这一格留原版
        }
        let mut rec = roll(def, 0, k, rng, None);
        let Some((idx, _)) = place(def, &mut rec, k, |i| now.contains(&i) || a.pending.contains_key(&i) || a.reserved(i)) else {
            if !a.src_full_told {
                a.src_full_told = true;
                log(&format!("骨灰：召唤 {} 只的容器都用着，获取格 {} 先放原版骨灰（拿到后照旧换）", summons(&rec, k), s.key));
            }
            continue;
        };
        if let Err(e) = write_container(def, &rec) {
            log(&format!("骨灰：给获取格 {} 改写容器 {idx} 失败：{e}，这一格先放原版骨灰", s.key));
            break;
        }
        rec.src = Some(s.key.clone());
        a.recs.insert(idx, rec);
        made += 1;
    }
    if got + freed + made > 0 {
        log(&format!(
            "骨灰：获取格 {} 个：这次拿到 {got} 个，{}新备上 {made} 个；现在备着 {} 个",
            def.srcs.len(),
            if freed > 0 { format!("放掉拿过 / 不在了的 {freed} 个，") } else { String::new() },
            a.recs.values().filter(|r| r.src.is_some()).count()
        ));
    }
    got + freed + made > 0
}

fn texts(d: &Defs, def: &Def, a: &mut AshSt) {
    let mut g = TXT.lock().unwrap_or_else(|e| e.into_inner());
    let Some(t) = g.as_mut() else { return };
    if t.scanning || (t.scans == a.scans && !a.dirty) {
        return;
    }
    a.scans = t.scans;
    a.dirty = false;
    let (mut n, mut bad) = (0, 0);
    for rec in a.recs.values() {
        let Some(k) = def.kinds.iter().find(|k| k.base == rec.kind) else { continue };
        for lv in 0..k.levels {
            let tx = [compose(&d.lib, def, k, rec, lv, 0), compose(&d.lib, def, k, rec, lv, 1)];
            let id = def.goods0 + 100 * rec.idx + lv;
            // 名字每级一个占位；简介 / 说明 / 血条名字各级共用 +0 那个（重随写的同一个占位），只在 +0 写一次
            let base = def.goods0 + 100 * rec.idx;
            let fields: &[(usize, u32, usize)] = if lv == 0 { &[(0, id, 0), (1, base, 1), (2, base, 2), (0, base + def.info2_off, 3)] } else { &[(0, id, 0)] };
            for &(field, key, which) in fields {
                let (x, y) = write_field(d, t, key, field, [&tx[0][which], &tx[1][which]]);
                n += x;
                bad += y;
            }
        }
    }
    if n > 0 || bad > 0 {
        log(&format!("骨灰：文字写了 {n} 处{}", if bad > 0 { format!("，{bad} 处核对不上没写") } else { String::new() }));
    }
}

/// 进存档：读这个角色的记录，按记录重建容器的参数行（文字等占位扫完再写）
pub(super) fn on_load(who: &(i32, String)) {
    let Some(def) = adef() else { return };
    let mut g = AST.lock().unwrap_or_else(|e| e.into_inner());
    let a = g.get_or_insert_with(AshSt::default);
    a.who = Some(who.clone());
    let text = fs::read_to_string(rec_file(who.0)).unwrap_or_default();
    a.recs = rec_load_text(&text, &who.1);
    if a.recs.is_empty() && rec_text_name(&text).as_deref() != Some(who.1.as_str()) {
        // 这一格的记录是别的角色的（或者没有）：到 旧记录 里找这个角色以前被挪开的那份（gear.rs）
        if let Some((p, t)) = rec_find_aside(&rec_file(who.0), &who.1) {
            a.recs = rec_load_text(&t, &who.1);
            log(&format!("骨灰：格子 {} 的记录不是「{}」的，从 {} 找回 {} 个", who.0, who.1, p.display(), a.recs.len()));
        }
    }
    a.recs.retain(|idx, r| *idx < def.n && def.kinds.iter().any(|k| k.base == r.kind));
    a.stale = a
        .recs
        .values()
        .filter(|r| def.kinds.iter().find(|k| k.base == r.kind).is_none_or(|k| !def.fits(r, k)))
        .cloned()
        .collect();
    for r in &a.stale {
        a.recs.remove(&r.idx);
    }
    if !a.stale.is_empty() {
        log(&format!("骨灰：{} 个记录和现在的容器分组对不上（这次更新前拿到的），稳定以后换回原版骨灰再重新抽", a.stale.len()));
    }
    a.pending.clear();
    a.dirty = true;
    a.full_told = false;
    a.src_seen = false;
    a.src_full_told = false;
    fx::reset();
    if let Some(rows) = def.mimic_rows {
        mimic::install(rows, def.per);
    }
    let (mut ok, mut bad) = (0, 0);
    for r in a.recs.values() {
        match write_container(def, r) {
            Ok(()) => ok += 1,
            Err(e) => {
                bad += 1;
                if bad <= 3 {
                    log(&format!("骨灰：重建容器 {} 失败：{e}", r.idx));
                }
            }
        }
    }
    log(&format!("骨灰：进存档（格子 {}）→ 按记录重建 {ok} 个骨灰容器{}；{}", who.0, if bad > 0 { format!("（{bad} 个失败）") } else { String::new() }, tally(&a.recs)));
    if !def.srcs.is_empty() {
        let (set, back, bad) = src_apply(def, a);
        log(&format!(
            "骨灰：获取格 {} 个 → {set} 个放这个角色备着的容器、{back} 个改回原版骨灰（稳定以后没备的再抽）{}",
            def.srcs.len(),
            if bad > 0 { format!("，{bad} 个对不上没动") } else { String::new() }
        ));
    }
}

/// 记录的统计：各稀有度几个、各前缀几个、集结几个
fn tally(recs: &HashMap<u32, AshRec>) -> String {
    let mut by = [0; 4];
    let mut pres: Vec<(String, u32)> = Vec::new();
    for r in recs.values() {
        by[r.rar.min(3)] += 1;
        if let Some(p) = &r.pre {
            match pres.iter_mut().find(|x| x.0 == *p) {
                Some(x) => x.1 += 1,
                None => pres.push((p.clone(), 1)),
            }
        }
    }
    pres.sort();
    let rally = recs.values().filter(|r| r.rally).count();
    let held_for = recs.values().filter(|r| r.src.is_some()).count();
    format!("普通 {} / 稀有 {} / 史诗 {} / 传说 {}，前缀 {:?}，集结 {rally}；其中 {held_for} 个是备在获取格里、还没拿到的", by[0], by[1], by[2], by[3], pres)
}

/// 开发工具：照 spec 直接生成 count 个骨灰容器、发出去（同拿到原版骨灰时换容器，只是不用原版那个）；返回每个的日志
pub(super) fn dev_give(pgd: &PlayerGameData, spec: &AshSpec, count: u32) -> Vec<String> {
    dev_give_ids(pgd, spec, count).0
}

/// 同 dev_give，另外返回排队发出去的道具编号（斗技场试炼死了要收回，arena.rs）
pub(super) fn dev_give_ids(pgd: &PlayerGameData, spec: &AshSpec, count: u32) -> (Vec<String>, Vec<u32>) {
    let mut ids = Vec::new();
    let Some(def) = adef() else { return (vec!["没有 ashes.txt（骨灰稀有度没开），不发".into()], ids) };
    let mut g = AST.lock().unwrap_or_else(|e| e.into_inner());
    let Some(a) = g.as_mut().filter(|a| a.who.is_some()) else { return (vec!["还没进存档，不发".into()], ids) };
    let ki = match spec.kind {
        Some(b) => match def.kinds.iter().position(|k| k.base == b) {
            Some(i) => Some(i),
            None => return (vec![format!("骨灰 {b} 不在 ashes.txt 的种类里，不发")], ids),
        },
        None => None,
    };
    let now = held(def, pgd);
    a.pending.retain(|idx, t0| !now.contains(idx) && t0.elapsed() < PENDING);
    let mut rng = Rng::new();
    let mut out = Vec::new();
    for _ in 0..count.clamp(1, 20) {
        let k = &def.kinds[ki.unwrap_or_else(|| rng.below(def.kinds.len() as u64) as usize)];
        let lv = spec.lv.min(k.levels - 1);
        if def.dedicated(k.base) && !mimic::ok() {
            out.push(format!("{}：仿身泪滴的判断没改成（看日志「仿身泪滴判断」），不发容器", k.name[0]));
            continue;
        }
        let mut rec = roll(def, 0, k, &mut rng, Some(spec));
        let Some((idx, dropped)) = place(def, &mut rec, k, |i| now.contains(&i) || a.pending.contains_key(&i) || a.reserved(i)) else {
            out.push(format!("召唤 {} 只的容器都用着，发不了了", summons(&rec, k)));
            break;
        };
        if dropped {
            out.push(format!("召唤 {} 只的容器都用着，这一个不带集结", summons(&rec, k) + 1));
        }
        if let Err(e) = write_container(def, &rec) {
            out.push(format!("改写容器 {idx} 失败：{e}"));
            break;
        }
        let id = def.goods0 + 100 * idx + lv;
        if !gift_n(1, id as i32, 1) {
            out.push("没有发货表，发不了".into());
            break;
        }
        ids.push(id);
        out.push(format!(
            "{}＋{lv} → 容器 {idx}（{id}）：稀有度 {}，前缀 {}，词条 {:?}{}，已排队发",
            k.name[0],
            rec.rar,
            rec.pre.as_deref().unwrap_or("无"),
            rec.affs,
            if rec.rally { "，集结" } else { "" }
        ));
        a.pending.insert(idx, Instant::now());
        a.recs.insert(idx, rec);
    }
    a.dirty = true;
    save(a);
    (out, ids)
}

/// 开发工具「骨灰转换 关 / 开」：暂停 / 恢复把原版骨灰换成容器
pub(super) fn set_paused(on: bool) {
    let mut g = AST.lock().unwrap_or_else(|e| e.into_inner());
    g.get_or_insert_with(AshSt::default).paused = on;
    log(&format!("骨灰：{}", if on { "暂停把原版骨灰换成容器（开发工具；进背包的原版骨灰先留着）" } else { "恢复把原版骨灰换成容器" }));
}

/// 开发工具「骨灰状态」：记录和在场的召唤物写进日志
pub(super) fn status() {
    let g = AST.lock().unwrap_or_else(|e| e.into_inner());
    let Some(a) = g.as_ref() else {
        log("骨灰状态：还没进存档");
        return;
    };
    let def = adef();
    log(&format!("骨灰状态：角色 {:?}，容器 {} 个（{}）", a.who, a.recs.len(), tally(&a.recs)));
    let mut v: Vec<&AshRec> = a.recs.values().collect();
    v.sort_by_key(|r| r.idx);
    for r in v.iter().take(60) {
        let name = def.and_then(|d| d.kinds.iter().find(|k| k.base == r.kind)).map_or(r.kind.to_string(), |k| k.name[0].clone());
        log(&format!(
            "骨灰状态：容器 {} = {name}，稀有度 {}，前缀 {}，词条 {:?}{}{}",
            r.idx,
            r.rar,
            r.pre.as_deref().unwrap_or("无"),
            r.affs,
            if r.rally { "，集结" } else { "" },
            r.src.as_ref().map_or(String::new(), |k| format!("，备在获取格 {k}（还没拿到）"))
        ));
    }
    log(&format!("骨灰状态：{}", fx::status()));
}

/// 每帧：写文字；稳定以后每 30 帧看一次背包里有没有原版骨灰，有就换成容器
pub(super) fn tick(d: &Defs, st: &St, pgd: &mut PlayerGameData, who: &(i32, String)) {
    let Some(def) = adef() else { return };
    let mut g = AST.lock().unwrap_or_else(|e| e.into_inner());
    let Some(a) = g.as_mut().filter(|a| a.who.as_ref() == Some(who)) else { return };
    texts(d, def, a);
    fx::tick(def, a); // 机制前缀 + 召唤日志（没有召唤物时只看一眼列表）
    if st.frames < SETTLE_FRAMES || st.frames % 30 != 7 {
        return;
    }
    // 更新前拿到的、记录和分组对不上的：背包里的换回原版骨灰（下面再按规则重新抽）
    for r in std::mem::take(&mut a.stale) {
        let Some(k) = def.kinds.iter().find(|k| k.base == r.kind) else { continue };
        for (id, lv) in in_bag(def, pgd, r.idx) {
            let back = k.base + lv.min(k.levels - 1);
            if remove_goods(pgd, id, 1) == 1 && gift_n(1, back as i32, 1) {
                log(&format!("骨灰：容器 {}（{id}）是更新前的，换回原版 {}＋{lv}（{back}），等下重新抽", r.idx, k.name[0]));
            }
        }
    }
    let now = held(def, pgd);
    a.pending.retain(|idx, t0| !now.contains(idx) && t0.elapsed() < PENDING);
    if a.paused {
        return;
    }
    let mut rng = Rng::new();
    let mut changed = false;
    // 获取格：备着的拿到了就归玩家，没备的抽一个备上，再把各格改成备着的容器
    if !def.srcs.is_empty() && src_tick(def, a, &now, &mut rng) {
        let (_, _, bad) = src_apply(def, a);
        if bad > 0 {
            log(&format!("骨灰：获取格有 {bad} 个对不上没改"));
        }
        changed = true;
    }
    let found = vanilla(def, pgd);
    if found.is_empty() {
        if changed {
            a.dirty = true;
            save(a);
        }
        return;
    }
    for (gid, ki, lv) in found {
        let k = &def.kinds[ki];
        if def.dedicated(k.base) && !mimic::ok() {
            continue; // 仿身泪滴的判断没改成：留原版（换了会穿默认装备）
        }
        let mut rec = roll(def, 0, k, &mut rng, None);
        let Some((idx, dropped)) = place(def, &mut rec, k, |i| now.contains(&i) || a.pending.contains_key(&i) || a.reserved(i)) else {
            if !a.full_told {
                a.full_told = true;
                log(&format!("骨灰：召唤 {} 只的容器都用着，背包里的原版骨灰 {gid} 先不换（丢掉一些容器骨灰就能空出来）", summons(&rec, k)));
            }
            continue;
        };
        if dropped {
            log(&format!("骨灰：召唤 {} 只的容器都用着，{gid} 这次不带集结", summons(&rec, k) + 1));
        }
        if let Err(e) = write_container(def, &rec) {
            log(&format!("骨灰：改写容器 {idx} 失败：{e}，{gid} 先不换"));
            break;
        }
        if remove_goods(pgd, gid, 1) != 1 {
            log(&format!("骨灰：背包里的 {gid} 扣不掉，先不换"));
            continue;
        }
        let new = def.goods0 + 100 * idx + lv;
        if !gift_n(1, new as i32, 1) {
            log(&format!("骨灰：没有发货表，{gid} 已经扣了、容器 {idx} 没发出去"));
            break;
        }
        log(&format!(
            "骨灰：{}（{gid}，+{lv}）换成容器 {idx}（{new}）：稀有度 {}，前缀 {}，词条 {:?}{}",
            k.name[0],
            rec.rar,
            rec.pre.as_deref().unwrap_or("无"),
            rec.affs,
            if rec.rally { "，集结" } else { "" }
        ));
        a.pending.insert(idx, Instant::now());
        a.recs.insert(idx, rec);
        changed = true;
    }
    if changed {
        a.dirty = true;
        save(a);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub(super) fn sample() -> Def {
        parse(concat!(
            "# x\ncont\t150000000\t120\t7320000\t7319999\t39900000\t6\t10000000\n",
            "pool\t1\t0\t60\npool\t2\t60\t30\npool\t3\t90\t10\npool\t4\t100\t10\npool\t5\t110\t10\npool\t6\t120\t5\n",
            "pool\t1\t125\t2\t216000\npool\t2\t127\t2\t216000\nmimic\t39900750\t39900774\ndop1\t7323000\n",
            "rar\t0\t40\t1\t1\t0\t0\nrar\t1\t30\t1.05\t1\t0\t30\nrar\t2\t20\t1.1\t2\t0\t60\nrar\t3\t10\t1.2\t2\t1\t100\n",
            "pre\tblast\tblast\t250,300,400,550\t0\t94900000,94900001,94900002,94900003\t爆裂\tBursting\t召唤物倒下时爆炸，造成 # 点火焰伤害\tExplode for # fire\n",
            "pre\tzeal\tzeal\t5,8,12,20\t20\t0,0,0,0\t战意\tSpirited\t所有召唤物恢复 #％ 的血量\tSummons restore #% HP\n",
            "pre\tfury\tfury\t15,20,30,40\t30\t0,0,0,0\t激昂\tFrenzied\t攻击力＋#％\tAttack +#%\n",
            "aff\thp\thp\t10,15,20,30\t召唤物的血量上限＋#％\tSummon max HP +#%\n",
            "aff\tatk\tatk\t8,12,16,24\t召唤物的攻击力＋#％\tSummon attack +#%\n",
            "aff\tregen\tregen\t0.5,0.8,1.2,1.5\t召唤物每秒恢复 #％ 的血量\tSummons restore #% HP per second\n",
            "diffash\t369005\t369455\ndiffash\t369007\t369457\ndiffash\t0\t369450\n",
            "bonus\t召唤物的血量上限、攻击力＋#％（稀有度）\tSummon max HP and attack +#% (rarity)\n",
            "rally\t集结\tRallying\t召唤数量＋1\tSummons one more spirit\n",
            "lvl\t0\t\t\nlvl\t3\t＋３\t +3\n",
            "src\tm\t20000\t0\t232000\t520000\nsrc\ts\t100300\t0\t200000\t130000\nsrc\tm\t20000\t0\t232000\t1\n",
            "src\te\t5\t2\t232003\t0\nsrc\te\t5\t9\t232000\t0\nsrc\tm\t7\t1\t999999\t0\nsrc\tx\t1\t0\t232000\t0\n",
            "kind\t232000\t11\t0\t23200000,23200001,23200002\t离群野狼的骨灰\tLone Wolf Ashes\t能召唤３只离群野狼的灵魂\tinfo\t寄宿着灵魂的骨灰。\tcap\t离群野狼\tLone Wolves\n",
            "kind\t200000\t11\t0\t20000000\t“黑刀”狄希\tBlack Knife Tiche\ti\ti\tc\tc\t狄希\tTiche\n",
            "kind\t216000\t11\t1\t21600000\t仿身泪滴\tMimic Tear\ti\ti\tc\tc\t泪滴\tMimic\n",
            "kind\t234000\t11\t0\t1,2,3,4,5\t亚人集团的骨灰\tDemi-Human Ashes\ti\ti\tc\tc\t亚人\tDemi\n",
        ))
        .unwrap()
    }

    /// 定义文件：容器、稀有度、词条、等级后缀、种类；原版各级编号能查到种类和等级
    #[test]
    fn parse_def() {
        let d = sample();
        assert_eq!((d.goods0, d.n, d.dop0, d.neutral, d.buddy0, d.per, d.info2_off), (150000000, 120, 7320000, 7319999, 39900000, 6, 10000000));
        assert_eq!(d.rar[3], Rar { weight: 10, mult: 1.2, suffixes: 2, rally: true, pre: 100.0 });
        assert_eq!(d.rar[1].pre, 30.0);
        assert_eq!(d.diff_ash, vec![(369005, 369455), (369007, 369457)], "编号 0 的不要");
        assert_eq!(d.pres.iter().map(|p| p.key.as_str()).collect::<Vec<_>>(), vec!["blast", "zeal"], "激昂没有效果编号：不要");
        assert_eq!((d.pres[0].ids[3], d.pres[1].arg, d.pres[1].kind), (94900003, 20.0, PreKind::Zeal));
        assert_eq!(d.affs.len(), 3);
        assert_eq!(d.by_id.get(&232003), Some(&(0, 3)));
        assert_eq!(d.by_id.get(&232011), None);
        assert_eq!(d.lvl[3], ["＋３".to_string(), " +3".to_string()]);
        assert_eq!(d.kinds[0].rows, vec![23200000, 23200001, 23200002]);
        assert!(d.kinds[2].special);
        assert_eq!((d.count_of(0), d.count_of(59), d.count_of(60), d.count_of(119), d.count_of(120), d.count_of(125), d.count_of(129)), (Some(1), Some(1), Some(2), Some(5), Some(6), Some(1), None));
    }

    /// 抽：稀有度比例照权重，词条条数照稀有度、不重复；集结只有传说，用玩家形象的、原版 5 只的不带
    #[test]
    fn roll_rules() {
        let d = sample();
        let mut rng = Rng(9);
        let mut by = [0u32; 4];
        let mut with_pre = [0u32; 4];
        for i in 0..20000 {
            let r = roll(&d, i % 120, &d.kinds[0], &mut rng, None);
            by[r.rar] += 1;
            with_pre[r.rar] += r.pre.is_some() as u32;
            assert_eq!(r.affs.len(), d.rar[r.rar].suffixes as usize);
            let mut u = r.affs.clone();
            u.dedup();
            assert_eq!(u.len(), r.affs.len(), "词条重复：{:?}", r.affs);
            assert_eq!(r.rally, r.rar == 3);
        }
        for (r, &w) in [40.0, 30.0, 20.0, 10.0].iter().enumerate() {
            let p = by[r] as f64 * 100.0 / 20000.0;
            assert!((p - w).abs() < 1.5, "稀有度 {r} 出了 {p:.1}%，应该约 {w}%");
        }
        for (r, &c) in [0.0, 30.0, 60.0, 100.0].iter().enumerate() {
            let p = with_pre[r] as f64 * 100.0 / by[r].max(1) as f64;
            assert!((p - c).abs() < 4.0, "稀有度 {r} 带前缀 {p:.1}%，应该约 {c}%");
        }
        for _ in 0..200 {
            let r = roll(&d, 0, &d.kinds[2], &mut rng, None);
            assert_eq!(r.rally, r.rar == 3, "仿身泪滴（用玩家形象）也带集结");
            let r = roll(&d, 0, &d.kinds[3], &mut rng, None);
            assert_eq!((r.rally, summons(&r, &d.kinds[3])), (r.rar == 3, if r.rar == 3 { 6 } else { 5 }), "原版 5 只的带集结变 6 只");
        }
        let spec = AshSpec { rar: Some(2), pre: Some(Some("zeal".into())), affs: vec!["regen".into(), "hp".into(), "regen".into(), "nope".into()], rally: Some(true), ..AshSpec::default() };
        let f = roll(&d, 0, &d.kinds[0], &mut rng, Some(&spec));
        assert_eq!((f.rar, f.pre.as_deref(), f.affs.clone(), f.rally), (2, Some("zeal"), vec!["regen".to_string(), "hp".to_string()], true), "开发工具指定：词条去重、不认识的不要");
        let f = roll(&d, 0, &d.kinds[2], &mut rng, Some(&spec));
        assert!(f.rally, "仿身泪滴指定集结也带");
        let spec = AshSpec { rar: Some(3), pre: Some(None), rally: Some(false), ..AshSpec::default() };
        let f = roll(&d, 0, &d.kinds[0], &mut rng, Some(&spec));
        assert_eq!((f.rar, f.pre, f.rally, f.affs.len()), (3, None, false, 2), "指定不带前缀、不带集结；词条照传说抽 2 条");
        let spec = AshSpec { rar: Some(0), pre: Some(Some("nope".into())), ..AshSpec::default() };
        assert_eq!(roll(&d, 0, &d.kinds[0], &mut rng, Some(&spec)).pre, None, "不认识的前缀不要");
    }

    /// 挑容器：只数对得上的那一组；集结那组满了就不带集结；都满了就没有
    #[test]
    fn place_by_summon_count() {
        let d = sample();
        let wolf = &d.kinds[0]; // 3 只
        let mut rec = AshRec { idx: 0, kind: 232000, rar: 3, affs: vec![], rally: true, pre: None, src: None };
        assert_eq!(place(&d, &mut rec, wolf, |_| false), Some((100, false)), "3 + 集结 = 4 只那一组");
        assert_eq!(place(&d, &mut rec, wolf, |i| i < 110 && i >= 100), Some((90, true)), "4 只那组满了：不带集结，放 3 只那组");
        assert!(!rec.rally);
        let mut rec = AshRec { idx: 0, kind: 232000, rar: 3, affs: vec![], rally: true, pre: None, src: None };
        assert_eq!(place(&d, &mut rec, wolf, |i| (90..110).contains(&i)), None, "都满了");
        assert!(rec.rally, "放不下就别改记录");
        let tiche = &d.kinds[1];
        let mut rec = AshRec { idx: 0, kind: 200000, rar: 0, affs: vec![], rally: false, pre: None, src: None };
        assert_eq!(place(&d, &mut rec, tiche, |i| i < 5), Some((5, false)));
        assert_eq!(rec.idx, 5);
    }

    /// 专用容器：仿身泪滴（样例里是 216000，1 行）只放专用组，别的骨灰不进专用组；放错组的记录算对不上
    #[test]
    fn dedicated_pool() {
        let d = sample();
        assert_eq!((d.mimic_rows, d.dop1), (Some((39900750, 39900774)), 7323000));
        let mimic = &d.kinds[2];
        assert!(d.dedicated(216000) && !d.dedicated(200000));
        let mut rec = AshRec { idx: 0, kind: 216000, rar: 0, affs: vec![], rally: false, pre: None, src: None };
        assert_eq!(place(&d, &mut rec, mimic, |_| false), Some((125, false)), "1 只：专用组");
        let mut rec = AshRec { idx: 0, kind: 216000, rar: 3, affs: vec![], rally: true, pre: None, src: None };
        assert_eq!(place(&d, &mut rec, mimic, |_| false), Some((127, false)), "集结 2 只：专用组");
        assert!(d.fits(&rec, mimic));
        let wrong = AshRec { idx: 60, ..rec.clone() };
        assert!(!d.fits(&wrong, mimic), "仿身泪滴放在通用的 2 只组：对不上");
        let tiche = &d.kinds[1];
        let mut t = AshRec { idx: 0, kind: 200000, rar: 0, affs: vec![], rally: false, pre: None, src: None };
        assert_eq!(place(&d, &mut t, tiche, |i| i < 60), None, "通用 1 只组满了也不进专用组");
    }

    /// 获取格：src 行（重复的键、格超过 7、不认识的骨灰、不认识的表都不要）；记录第 8 列读写得回来；
    /// 备着容器的格放容器的同一等级，没备的放原版
    #[test]
    fn sources() {
        let d = sample();
        let got: Vec<(&str, SrcAt, u32, u8, u32)> = d.srcs.iter().map(|s| (s.key.as_str(), s.at, s.row, s.slot, s.flag)).collect();
        assert_eq!(got, vec![("m20000.0", SrcAt::Map, 20000, 0, 520000), ("s100300.0", SrcAt::Shop, 100300, 0, 130000), ("e5.2", SrcAt::Enemy, 5, 2, 0)]);
        assert!(!src_taken(&d.srcs[2]), "没有标记：看不出来拿没拿过，一直备着");
        let rec = AshRec { idx: 7, kind: 232000, rar: 1, affs: vec!["hp".into()], rally: false, pre: None, src: Some("e5.2".into()) };
        let line = rec_line(&rec);
        assert!(line.ends_with("\t-\te5.2"), "{line}");
        assert_eq!(rec_parse(&line), Some(rec.clone()));
        assert_eq!(rec_parse("c\t3\t200000\t1\t-\t0\tblast").map(|r| (r.pre, r.src)), Some((Some("blast".into()), None)), "第二期的记录（7 列）照样读");
        let mine: HashMap<&str, u32> = HashMap::from([("e5.2", 7)]);
        assert_eq!(src_want(&d, &mine, &d.srcs[2]), (d.goods0 + 700 + 3) as i32, "+3 的格放容器的 +3");
        assert_eq!(src_want(&d, &mine, &d.srcs[0]), 232000, "没备的放原版");
        let mut st = AshSt::default();
        st.recs.insert(7, rec);
        st.recs.insert(8, AshRec { idx: 8, kind: 200000, rar: 0, affs: vec![], rally: false, pre: None, src: None });
        assert!(st.reserved(7) && !st.reserved(8) && !st.reserved(9));
    }

    /// 文字：名字带稀有度和集结、接等级后缀；说明是原版说明 + 稀有度加成 + 词条 + 集结；记录一行写出去读得回来
    #[test]
    fn compose_and_record() {
        let d = sample();
        let mut lib = Lib::default();
        lib.rar = [["普通".into(), "Common".into()], ["稀有".into(), "Rare".into()], ["史诗".into(), "Epic".into()], ["传说".into(), "Legendary".into()]];
        let rec = AshRec { idx: 5, kind: 232000, rar: 3, affs: vec!["hp".into(), "regen".into()], rally: true, pre: Some("blast".into()), src: None };
        let [name, info, cap, info2] = compose(&lib, &d, &d.kinds[0], &rec, 3, 0);
        assert_eq!(name, "传说 爆裂·集结·离群野狼的骨灰＋３");
        assert_eq!(compose(&lib, &d, &d.kinds[0], &rec, 3, 1)[0], "Legendary Bursting Rallying Lone Wolf Ashes +3");
        assert_eq!(info, "能召唤３只离群野狼的灵魂");
        assert_eq!(info2, "离群野狼");
        assert!(cap.starts_with("寄宿着灵魂的骨灰。\n\n"), "{cap}");
        for s in ["召唤物的血量上限、攻击力＋20％（稀有度）", "召唤物倒下时爆炸，造成 550 点火焰伤害", "召唤物的血量上限＋30％", "召唤物每秒恢复 1.5％ 的血量", "召唤数量＋1"] {
            assert!(cap.contains(s), "说明里没有「{s}」：{cap}");
        }
        let plain = AshRec { idx: 1, kind: 200000, rar: 0, affs: vec!["atk".into()], rally: false, pre: None, src: None };
        assert_eq!(compose(&lib, &d, &d.kinds[1], &plain, 0, 1)[0], "Common Black Knife Tiche");
        let text = rec_text("褪色者", &HashMap::from([(5, rec.clone()), (1, plain.clone())]));
        let back = rec_load_text(&text, "褪色者");
        assert_eq!((back.get(&5), back.get(&1)), (Some(&rec), Some(&plain)));
        assert!(rec_load_text(&text, "别人").is_empty(), "角色名对不上就不认");
        assert_eq!(rec_parse("c\t3\t200000\t1\t-\t0").map(|r| r.pre), Some(None), "第一期的记录（没有前缀那一列）照样读");
        assert_eq!((num(1.5), num(20.0), num(0.8)), ("1.5".to_string(), "20".to_string(), "0.8".to_string()));
        assert_eq!(total(&d, &rec, Field::Hp), 30.0);
        assert_eq!(scale_i16(55, 20.0), 44);
    }
}
