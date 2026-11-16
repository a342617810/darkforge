//! 魇化精英与魇印（参数侧 rr/nightmare.py；设计稿 dev\item_system\超限锻造石与高难度.md §8；用户 2026-11-03）：
//! - 只在标了 lock 的难度档里：游戏距离列表里的普通小怪（nightmare.txt 的 mobe / mobn），第一次看到时按档掷 chance% 魇化（double% 带两条），
//!   挂血量 ×2（hp）和词条分组的强化（color：0 攻击 / 1 加快 / 2 减伤 / 3 回血；描边一律紫色，用户 2026-11-03），加快的动作速度由这里改（同时隙）。
//!   挂血量时游戏不按比例补当前血量的（被事件禁用着的），同血量补正按原比例补上。休息（坐上赐福）时摘掉、清空，重生后重掷。
//!   休息时游戏重新生成敌人、清掉身上的效果（坐下那一刻抽中的精英也一样）：每轮看记录里的精英，效果缺了就补挂、按比例补当前血量（用户 2026-11-05「有的有有的没有」）。
//! - 魇化精英死了（不要求是你打死的；range 0 = 不限距离，用户 2026-11-05「30m对于远程来说还是太近了」）：词条变成「魇火」——这条词条在这一档魇火稀有度的效果行直接挂在玩家身上
//!   （规则引擎、玩家脚本认的就是身上的标记效果），最多 ember_max 个、先进先出；夺取次数 +1（事件标记，存档）；超限锻造石按 stone_pct% 掉
//!   （ovldrop 看 is_elite 跳过普通小怪的几率）。魇火只在死亡时清掉（用户 2026-11-03：休息不清），存进存档标记（ember0：每个第几种 + 1、
//!   稀有度 << 4），读档 / 换角色后 LOAD_DELAY 读回来，所以退出游戏也还在。
//! - 魇印：次数到 levels 的种类能刻进刻印位（赐福「暗黑重铸」→「魇印」→ gear\workshop.rs → set_slot），刻上的按等级（Ⅰ~Ⅳ = 普通~传说）挂效果行，
//!   所有难度都生效。开几位看解锁了几种（slots）。
//! - 魇火、魇印要挂的效果每 0.5 秒核对：缺了补挂（读档、死后），不要了摘掉；身上的装备自己带同一个效果的不摘（同 attrstack 读装备的常驻效果）。
//! - 提示（夺得魇火、解锁 / 升级魇印、开新刻印位）走原版闪烁提示（notes.rs，用户 2026-11-03：用原版提示框）；夺取时给玩家挂 drain
//!   （原版亵渎圣剑战技回血的特效改成紫色，rr/nightmare.py；下一次扫描时挂）。
//! - 开发工具（dll\dark_dev「魇化测试」）写 nightmare_req.txt：夺取 <序号|随机>、次数 <序号|全部> <n>、清空魇火、魇化最近。
//! 只在这些档里扫敌人；不在时只核对玩家身上的魇火 / 魇印（没有就什么都不做）。联机先不管。

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use eldenring::cs::{
    ChrInsExt, EquipParamAccessory, EquipParamProtector, GameDataMan, GameMan, ItemCategory, SoloParamRepository, SpEffectParam, WorldChrMan,
};
use fromsoftware_shared::FromStatic;

use crate::gear::{fam_info, flag_get, flag_set, gift_n};
use crate::rules::FRIENDLY_TEAMS;
use crate::{dir, log};

const SCAN: Duration = Duration::from_millis(250);
const SYNC: Duration = Duration::from_millis(500);
/// 换了角色（含刚进游戏）多久以后从存档标记读回魇火
const LOAD_DELAY: Duration = Duration::from_secs(3);
/// 血量 0 持续这么久才算死亡（读档时一瞬间的 0 不算，免得把存着的魇火清掉）
const DEAD_HOLD: Duration = Duration::from_secs(1);
const RAR_ZH: [&str; 4] = ["普通", "稀有", "史诗", "传说"];
const ROMAN: [&str; 5] = ["", "I", "II", "III", "IV"]; // 游戏字体里没有 Ⅰ~Ⅳ
/// 前这么多个精英逐个写日志
const LOG_ELITES: u32 = 20;

#[derive(Debug, Default, PartialEq)]
struct Def {
    /// (当前档标记, 魇化几率 %, 带两条几率 %, 魇火稀有度 0~3, 精英掉石头几率 %)
    tiers: Vec<(u32, f32, f32, usize, f32)>,
    hp_sp: i32,
    /// 颜色 → (强化效果, 动作速度)
    colors: Vec<(i32, f32)>,
    /// 夺取时给玩家挂的特效（紫色的吸取；0 = 没有）
    drain: i32,
    /// (词条键, 颜色)
    fams: Vec<(String, usize)>,
    ember_max: usize,
    range: f32,
    levels: Vec<u32>,
    slots: Vec<u32>,
    count0: (u32, u32),
    /// 刻印位：每位几个标记、各位的第一个标记（不连号，见 rr/nightmare.py 的 SLOT_FLAGS）
    slot_bits: u32,
    slot_at: Vec<u32>,
    goods: [i32; 2],
    /// 魇火存进的标记：(第一个, 每个几位, 几个)
    ember0: (u32, u32, usize),
    mob_e: HashSet<u32>,
    mob_n: HashSet<i32>,
}

impl Def {
    /// 次数 → 等级 0~4
    fn level(&self, n: u32) -> usize {
        self.levels.iter().filter(|&&x| n >= x).count()
    }

    /// 解锁 k 种 → 开几个刻印位
    fn open_slots(&self, unlocked: u32) -> usize {
        self.slots.iter().filter(|&&x| unlocked >= x).count()
    }
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn parse(text: &str) -> Option<Def> {
    let mut d = Def { ember_max: 3, range: 30.0, ..Def::default() };
    for l in text.lines() {
        let f: Vec<&str> = l.trim_start_matches('\u{feff}').split_whitespace().collect();
        let n = |i: usize| f.get(i).and_then(|x| x.parse::<f64>().ok());
        let nums = |from: usize| -> Vec<u32> { f.iter().skip(from).filter_map(|x| x.parse().ok()).collect() };
        match f.first().copied() {
            Some("tier") if f.len() >= 6 => d.tiers.push((n(1)? as u32, n(2)? as f32, n(3)? as f32, (n(4)? as usize).min(3), n(5)? as f32)),
            Some("hp") => d.hp_sp = n(1)? as i32,
            Some("drain") => d.drain = n(1)? as i32,
            Some("color") if f.len() >= 4 => {
                let k = n(1)? as usize;
                if d.colors.len() <= k {
                    d.colors.resize(k + 1, (0, 1.0));
                }
                d.colors[k] = (n(2)? as i32, n(3)? as f32);
            }
            Some("fam") if f.len() >= 4 => d.fams.push((f[2].to_string(), n(3)? as usize)),
            Some("ember_max") => d.ember_max = n(1)? as usize,
            Some("range") => d.range = n(1)? as f32,
            Some("levels") => d.levels = nums(1),
            Some("slots") => d.slots = nums(1),
            Some("count0") if f.len() >= 3 => d.count0 = (n(1)? as u32, n(2)? as u32),
            Some("slot_at") if f.len() >= 3 => {
                d.slot_bits = n(1)? as u32;
                d.slot_at = nums(2);
            }
            Some("ember0") if f.len() >= 4 => d.ember0 = (n(1)? as u32, n(2)? as u32, n(3)? as usize),
            Some("goods") if f.len() >= 3 => d.goods = [n(1)? as i32, n(2)? as i32],
            Some("mobe") => d.mob_e.extend(nums(1)),
            Some("mobn") => d.mob_n.extend(nums(1).into_iter().map(|x| x as i32)),
            _ => {}
        }
    }
    let ok = !d.tiers.is_empty() && !d.fams.is_empty() && d.colors.len() == 4 && d.count0.0 > 0 && !d.slot_at.is_empty() && d.levels.len() == 4;
    ok.then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("nightmare.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("魇化精英（{} 档，{} 种词条，小怪 {} 处 / {} 行）", d.tiers.len(), d.fams.len(), d.mob_e.len(), d.mob_n.len()),
        None => "魇化精英（没有 nightmare.txt，不管）".into(),
    }
}

// ------------------------------------------------------------------ 标记里的次数、刻印位
fn read_bits(first: u32, bits: u32) -> u32 {
    (0..bits).filter(|&i| flag_get(first + i) == Some(true)).fold(0, |v, i| v | 1 << i)
}

fn write_bits(first: u32, bits: u32, v: u32) {
    for i in 0..bits {
        flag_set(first + i, v >> i & 1 == 1);
    }
}

fn count_of(d: &Def, k: usize) -> u32 {
    read_bits(d.count0.0 + k as u32 * d.count0.1, d.count0.1)
}

fn set_count(d: &Def, k: usize, v: u32) {
    write_bits(d.count0.0 + k as u32 * d.count0.1, d.count0.1, v.min((1 << d.count0.1) - 1));
}

/// 魇火存进标记（每个：第几种 + 1（0 = 空）| 稀有度 << 4），跟着存档走
fn save_embers(d: &Def, embers: &[(usize, usize)]) {
    let (first, bits, n) = d.ember0;
    if first == 0 {
        return;
    }
    for i in 0..n {
        let v = embers.get(i).map_or(0, |&(k, r)| (k as u32 + 1) | (r as u32) << 4);
        write_bits(first + i as u32 * bits, bits, v);
    }
}

/// 读回存档里的魇火；不像样（种类超出、重复、中间有空）就清掉这几个标记
fn load_embers(d: &Def) -> Vec<(usize, usize)> {
    let (first, bits, n) = d.ember0;
    if first == 0 {
        return Vec::new();
    }
    let raw: Vec<u32> = (0..n).map(|i| read_bits(first + i as u32 * bits, bits)).collect();
    let mut out: Vec<(usize, usize)> = Vec::new();
    let mut gap = false;
    for &v in &raw {
        if v == 0 {
            gap = true;
            continue;
        }
        let (k, r) = ((v & 15) as usize, (v >> 4 & 3) as usize);
        if gap || k == 0 || k > d.fams.len() || out.iter().any(|e| e.0 == k - 1) {
            log(&format!("魇化：存档里的魇火标记不对（{raw:?}），清掉"));
            save_embers(d, &[]);
            return Vec::new();
        }
        out.push((k - 1, r));
    }
    out.truncate(d.ember_max.max(1));
    out
}

/// 第 i 个刻印位刻的是第几种（None = 空）
fn slot_of(d: &Def, i: usize) -> Option<usize> {
    let v = read_bits(*d.slot_at.get(i)?, d.slot_bits) as usize;
    (v >= 1 && v <= d.fams.len()).then(|| v - 1)
}

fn set_slot_raw(d: &Def, i: usize, fam: Option<usize>) {
    if let Some(&first) = d.slot_at.get(i) {
        write_bits(first, d.slot_bits, fam.map_or(0, |k| k as u32 + 1));
    }
}

// ------------------------------------------------------------------ 状态
struct Elite {
    fams: Vec<usize>,
    color: usize,
    /// 上一次看到的血量
    hp: i32,
    /// 挂血量时的 (血量, 上限)：上限变了、血量还停在那个数就按比例补
    fix: Option<(i32, i32)>,
    /// 第一次看到的时间：读图时被事件直接弄死的（看到不到 SEEN_MIN）不算
    at: Instant,
}

const SEEN_MIN: Duration = Duration::from_secs(3);

struct St {
    next: Instant,
    sync_at: Instant,
    who: Option<(i32, String)>,
    elites: HashMap<usize, Elite>,
    rolled: HashSet<usize>,
    /// 斗技场试炼登记的、已经魇化过的角色（同一个地址只魇化一次；登记清空时清掉）
    forced_done: HashSet<usize>,
    /// 魇火：(第几种, 稀有度)，先进先出
    embers: Vec<(usize, usize)>,
    /// 这里挂到玩家身上的效果
    applied: HashSet<i32>,
    sitting: bool,
    /// 补挂写过几次日志
    relit_log: u32,
    /// 这次死亡已经处理过（血量回到 0 以上才清）
    dead: bool,
    /// 血量从什么时候起是 0
    dead_since: Option<Instant>,
    /// 什么时候从存档标记读回魇火（换了角色以后）
    load_at: Option<Instant>,
    tier: Option<usize>,
    rng: u64,
    n_elites: u32,
    /// 刚夺取过：下一次扫描给玩家挂 drain
    drain: bool,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 一定要魇化的实体（斗技场试炼的精英，arena.rs 出场时登记、结束时清掉）和带两条的几率 %：任何难度都魇化，
/// 只在标了 lock 的档里死了才夺魇火 / 掉石头（同普通精英）
static FORCED: Mutex<(Vec<u32>, f32)> = Mutex::new((Vec::new(), 0.0));

/// arena.rs：这些实体一出现就魇化
pub fn force(ents: &[u32], two_pct: f32) {
    let mut f = FORCED.lock().unwrap_or_else(|e| e.into_inner());
    f.0.extend(ents.iter().copied());
    f.1 = two_pct;
}

/// arena.rs：试炼结束
pub fn unforce() {
    FORCED.lock().unwrap_or_else(|e| e.into_inner()).0.clear();
}

impl St {
    fn roll(&mut self) -> u64 {
        self.rng = self.rng.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.rng;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// 0~100 的随机数是不是小于 pct
    fn chance(&mut self, pct: f32) -> bool {
        ((self.roll() % 10000) as f32) < pct * 100.0
    }
}

fn name(d: &Def, k: usize) -> [String; 2] {
    d.fams.get(k).and_then(|f| fam_info(&f.0)).map(|x| x.0).unwrap_or_else(|| [format!("#{k}"), format!("#{k}")])
}

/// ovldrop 用：这个角色是魇化精英（它的超限锻造石在这里掉，普通小怪的几率不算）
pub fn is_elite(addr: usize) -> bool {
    ST.lock().ok().is_some_and(|g| g.as_ref().is_some_and(|s| s.elites.contains_key(&addr)))
}

/// 夺得一次第 k 种：魇火（这一档的稀有度）+ 次数 +1，提示升级 / 开新刻印位
fn seize(d: &Def, st: &mut St, k: usize, rar: usize, why: &str) {
    let nm = name(d, k);
    if st.load_at.take().is_some() {
        st.embers = load_embers(d);
    }
    st.embers.retain(|e| e.0 != k);
    st.embers.push((k, rar));
    while st.embers.len() > d.ember_max.max(1) {
        st.embers.remove(0);
    }
    save_embers(d, &st.embers);
    let unlocked_before = (0..d.fams.len()).filter(|&i| count_of(d, i) > 0).count() as u32;
    let old = count_of(d, k);
    set_count(d, k, old + 1);
    let new = count_of(d, k);
    log(&format!("魇化：{why} → 魇火 {}（{}），夺取次数 {old} → {new}；现在的魇火 {:?}", nm[0], RAR_ZH[rar], st.embers));
    let (lv0, lv1) = (d.level(old), d.level(new));
    // 原版闪烁提示（notes.rs 排队，一条接一条）+ 下一次扫描给玩家挂紫色的吸取特效
    crate::notes::push(&format!("seize {k}"));
    if lv1 > lv0 {
        crate::notes::push(&format!("level {k} {lv1}"));
    }
    let unlocked = unlocked_before + (old == 0) as u32;
    if d.open_slots(unlocked) > d.open_slots(unlocked_before) {
        crate::notes::push(&format!("slot {}", d.open_slots(unlocked)));
    }
    st.drain = true;
}

/// 「魇印」页：把第 fam 种刻进第 slot 位（None = 取下）。同一种刻在别的位上就换过来
pub fn set_slot(slot: usize, fam: Option<usize>) -> Result<[String; 2], [String; 2]> {
    let e = |zh: &str, en: &str| [zh.to_string(), en.to_string()];
    let d = def().ok_or_else(|| e("这次没开魇化", "Nightmare seals are disabled"))?;
    let unlocked = (0..d.fams.len()).filter(|&i| count_of(d, i) > 0).count() as u32;
    if slot >= d.slot_at.len() || slot >= d.open_slots(unlocked) {
        return Err(e("这个刻印位还没开", "this seal slot is not open yet"));
    }
    match fam {
        None => {
            set_slot_raw(d, slot, None);
            Ok(e("已取下", "Seal removed"))
        }
        Some(k) if k < d.fams.len() && count_of(d, k) > 0 => {
            let old = slot_of(d, slot);
            for i in 0..d.slot_at.len() {
                if i != slot && slot_of(d, i) == Some(k) {
                    set_slot_raw(d, i, old); // 刻在别的位上：两位对调
                }
            }
            set_slot_raw(d, slot, Some(k));
            let nm = name(d, k);
            let lv = d.level(count_of(d, k));
            log(&format!("魇化：第 {} 个刻印位刻上 {} {}", slot + 1, nm[0], ROMAN[lv]));
            Ok([format!("刻上魇印：{} {}", nm[0], ROMAN[lv]), format!("Seal engraved: {} {}", nm[1], ROMAN[lv])])
        }
        _ => Err(e("这种魇印还没解锁", "this seal is not unlocked yet")),
    }
}

/// 工坊快照用：每种 (键, 颜色, 次数, 等级)、刻印位（开了几个、各刻的什么）、魇火、各级要的次数
pub struct UiState {
    pub fams: Vec<(String, usize, u32, usize)>,
    pub open: usize,
    pub slots: Vec<Option<usize>>,
    pub embers: Vec<(usize, usize)>,
    pub levels: Vec<u32>,
    /// 各刻印位要解锁几种
    pub need: Vec<u32>,
}

pub fn ui_state() -> Option<UiState> {
    let d = def()?;
    let counts: Vec<u32> = (0..d.fams.len()).map(|k| count_of(d, k)).collect();
    let unlocked = counts.iter().filter(|&&c| c > 0).count() as u32;
    let embers = ST.lock().ok().and_then(|g| g.as_ref().map(|s| s.embers.clone())).unwrap_or_default();
    Some(UiState {
        fams: d.fams.iter().zip(&counts).map(|(f, &c)| (f.0.clone(), f.1, c, d.level(c))).collect(),
        open: d.open_slots(unlocked).min(d.slot_at.len()),
        slots: (0..d.slot_at.len()).map(|i| slot_of(d, i)).collect(),
        embers,
        levels: d.levels.clone(),
        need: d.slots.clone(),
    })
}

/// 身上装备的常驻效果（防具三格、护符四格 + 盟约槽；同 attrstack）
fn worn_effects() -> HashSet<i32> {
    let mut out = HashSet::new();
    let (Ok(gdm), Ok(repo)) = (unsafe { GameDataMan::instance() }, unsafe { SoloParamRepository::instance() }) else { return out };
    let e = &gdm.main_player_game_data.equipment.equipment_entries;
    for id in [e.protector_head, e.protector_chest, e.protector_hands, e.protector_legs] {
        if matches!(id.category(), ItemCategory::Protector) {
            if let Some(r) = repo.get::<EquipParamProtector>(id.param_id()) {
                out.extend([r.resident_sp_effect_id(), r.resident_sp_effect_id2(), r.resident_sp_effect_id3()]);
            }
        }
    }
    for id in e.accessories.iter().chain(std::iter::once(&e.covenant)).filter_map(|x| x.as_valid()) {
        if matches!(id.category(), ItemCategory::Accessory) {
            if let Some(r) = repo.get::<EquipParamAccessory>(id.param_id()) {
                out.extend([r.ref_id(), r.resident_sp_effect_id1(), r.resident_sp_effect_id2(), r.resident_sp_effect_id3(), r.resident_sp_effect_id4()]);
            }
        }
    }
    out
}

/// 玩家身上该有的：魇印（各刻印位按等级）+ 魇火
fn wanted(d: &Def, st: &St) -> HashSet<i32> {
    let mut out = HashSet::new();
    let sp = |k: usize, r: usize| d.fams.get(k).and_then(|f| fam_info(&f.0)).and_then(|x| x.1[r]);
    for i in 0..d.slot_at.len() {
        if let Some(k) = slot_of(d, i) {
            let lv = d.level(count_of(d, k));
            if lv > 0 {
                out.extend(sp(k, lv - 1));
            }
        }
    }
    for &(k, r) in &st.embers {
        out.extend(sp(k, r));
    }
    out
}

/// 当前角色（存档格、名字）：换了角色清掉魇火
fn who() -> Option<(i32, String)> {
    let slot = unsafe { GameMan::instance() }.ok()?.save_slot;
    let gdm = unsafe { GameDataMan::instance() }.ok()?;
    let n = &gdm.main_player_game_data.character_name;
    let len = n.iter().position(|&c| c == 0).unwrap_or(n.len());
    (slot >= 0 && len > 0).then(|| (slot, String::from_utf16_lossy(&n[..len])))
}

/// 摘掉在场角色身上的魇化效果、动作速度还原（休息、离开这几档时）
fn strip_elites(d: &Def, st: &mut St, live: &HashSet<usize>, wcm: &WorldChrMan) {
    let ours: HashSet<i32> = std::iter::once(d.hp_sp).chain(d.colors.iter().map(|c| c.0)).collect();
    let mut n = 0;
    for s in wcm.chr_sets.iter().flatten() {
        for c in s.characters() {
            let a = c as *mut _ as usize;
            let Some(e) = st.elites.get(&a) else { continue };
            if !live.contains(&a) {
                continue;
            }
            for sp in c.special_effect.entries().map(|x| x.param_id).filter(|x| ours.contains(x)).collect::<Vec<_>>() {
                c.remove_speffect(sp);
            }
            if d.colors.get(e.color).is_some_and(|x| x.1 != 1.0) {
                c.modules.behavior.animation_speed = 1.0;
            }
            n += 1;
        }
    }
    if !st.elites.is_empty() {
        log(&format!("魇化：摘掉 {n} 个精英身上的效果（共记着 {} 个）", st.elites.len()));
    }
    st.elites.clear();
    st.rolled.clear();
}

/// 开发工具的请求（dll\dark_dev 写 nightmare_req.txt，处理完删掉）
fn dev_req(d: &Def, st: &mut St, wcm: &mut WorldChrMan, me: usize, my_team: u8) {
    let path = dir().join("nightmare_req.txt");
    let Ok(text) = fs::read_to_string(&path) else { return };
    let _ = fs::remove_file(&path);
    let rar = st.tier.map_or(1, |t| d.tiers[t].3);
    for line in text.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')) {
        let f: Vec<&str> = line.split_whitespace().collect();
        match f.as_slice() {
            ["夺取", x] => {
                let k = x.parse::<usize>().ok().filter(|&k| k < d.fams.len()).unwrap_or_else(|| (st.roll() % d.fams.len() as u64) as usize);
                seize(d, st, k, rar, "开发工具：夺取");
            }
            ["次数", x, n] => {
                let Ok(n) = n.parse::<u32>() else { continue };
                let ks: Vec<usize> = match x.parse::<usize>() {
                    Ok(k) if k < d.fams.len() => vec![k],
                    _ => (0..d.fams.len()).collect(),
                };
                for k in ks {
                    set_count(d, k, n);
                }
                log(&format!("魇化：开发工具：次数 {x} 设成 {n}"));
            }
            ["清空魇火"] => {
                st.embers.clear();
                st.load_at = None;
                save_embers(d, &[]);
                log("魇化：开发工具：清空魇火");
            }
            ["魇化最近"] => {
                let Some(around) = around!(wcm, me) else { continue };
                let near = around.iter().filter(|e| e.chr_ins.as_ptr() as usize != me && e.distance <= 15.0).find(|e| {
                    let c = unsafe { e.chr_ins.as_ref() };
                    !FRIENDLY_TEAMS.contains(&c.team_type) && c.team_type != my_team && c.modules.data.hp > 0
                });
                match near {
                    Some(e) => {
                        let a = e.chr_ins.as_ptr() as usize;
                        st.elites.remove(&a);
                        make_elite(d, st, unsafe { &mut *e.chr_ins.as_ptr() }, a, true);
                    }
                    None => log("魇化：开发工具：15 米内没有敌人"),
                }
            }
            _ => log(&format!("魇化：开发工具：看不懂「{line}」")),
        }
    }
}

/// 把这个角色变成魇化精英：挑词条、挂血量和颜色强化
/// 这个精英该挂的效果，按挂的顺序：血量、词条分组的强化（第一条的颜色最后挂，描边以它为准）
fn elite_sps(d: &Def, fams: &[usize]) -> Vec<i32> {
    let mut cols: Vec<usize> = fams.iter().map(|&k| d.fams[k].1.min(3)).collect();
    cols.dedup();
    std::iter::once(d.hp_sp).chain(cols.iter().rev().map(|&cl| d.colors[cl].0)).collect()
}

fn make_elite(d: &Def, st: &mut St, c: &mut eldenring::cs::ChrIns, addr: usize, two_ok: bool) {
    make_elite_with(d, st, c, addr, two_ok, None)
}

/// two：带两条的几率 %（None = 这一档的）
fn make_elite_with(d: &Def, st: &mut St, c: &mut eldenring::cs::ChrIns, addr: usize, two_ok: bool, two: Option<f32>) {
    let n = d.fams.len() as u64;
    let k1 = (st.roll() % n) as usize;
    let double = two.unwrap_or_else(|| st.tier.map_or(0.0, |t| d.tiers[t].2));
    let mut fams = vec![k1];
    if two_ok && st.chance(double) {
        let k2 = (k1 + 1 + (st.roll() % (n - 1)) as usize) % n as usize;
        fams.push(k2);
    }
    let color = d.fams[k1].1.min(3);
    let (hp, max) = (c.modules.data.hp, c.modules.data.max_hp);
    for sp in elite_sps(d, &fams) {
        c.apply_speffect(sp, false);
    }
    st.n_elites += 1;
    if st.n_elites <= LOG_ELITES {
        let names: Vec<String> = fams.iter().map(|&k| name(d, k)[0].clone()).collect();
        log(&format!("魇化：NPC {}（实体 {}）魇化 → {}（颜色 {color}），挂之前血 {hp} / {max}", c.npc_param_id, c.event_entity_id, names.join("、")));
    }
    st.elites.insert(addr, Elite { fams, color, hp, fix: Some((hp, max)), at: Instant::now() });
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St {
        next: now,
        sync_at: now,
        who: None,
        elites: HashMap::new(),
        rolled: HashSet::new(),
        forced_done: HashSet::new(),
        embers: Vec::new(),
        applied: HashSet::new(),
        sitting: false,
        relit_log: 0,
        dead: false,
        dead_since: None,
        load_at: None,
        tier: None,
        rng: SystemTime::now().duration_since(UNIX_EPOCH).map_or(7, |t| t.as_nanos() as u64),
        n_elites: 0,
        drain: false,
    });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        st.elites.clear();
        st.rolled.clear();
        return;
    };
    if std::mem::take(&mut st.drain) && d.drain > 0 {
        p.apply_speffect(d.drain, false);
    }
    let me = &p.chr_ins as *const _ as usize;
    let my_team = p.chr_ins.team_type;
    let w = who();
    if w.is_some() && w != st.who {
        if st.who.is_some() {
            log("魇化：换了角色，魇火按存档重读");
        }
        st.who = w;
        st.embers.clear();
        st.applied.clear();
        st.elites.clear();
        st.rolled.clear();
        st.load_at = Some(now + LOAD_DELAY);
    }
    if st.load_at.is_some_and(|t| now >= t) {
        st.load_at = None;
        st.embers = load_embers(d);
        if !st.embers.is_empty() {
            log(&format!("魇化：从存档读回魇火 {:?}", st.embers));
        }
    }
    // 死亡：清掉魇火（休息不清，用户 2026-11-03）；坐上赐福（休息）时精英摘掉、重掷
    let ta = &p.chr_ins.modules.time_act;
    let anim = (!ta.anim_queue.is_empty()).then(|| ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].anim_id);
    let sitting = anim.is_some_and(|a| (68000..68100).contains(&a));
    let dead = p.chr_ins.modules.data.hp <= 0;
    let rested = sitting && !st.sitting;
    st.dead_since = if dead { st.dead_since.or(Some(now)) } else { None };
    if !dead {
        st.dead = false;
    } else if !st.dead && st.load_at.is_none() && st.dead_since.is_some_and(|t| now - t >= DEAD_HOLD) {
        st.dead = true;
        if !st.embers.is_empty() {
            log(&format!("魇化：死亡，魇火清掉（{} 个）", st.embers.len()));
        }
        st.embers.clear();
        save_embers(d, &[]);
    }
    st.sitting = sitting;
    st.tier = d.tiers.iter().position(|t| flag_get(t.0) == Some(true));
    dev_req(d, st, wcm, me, my_team);
    // 魇火、魇印：缺了补挂、不要了摘掉
    if now >= st.sync_at {
        st.sync_at = now + SYNC;
        let want = wanted(d, st);
        if !want.is_empty() || !st.applied.is_empty() {
            let Some(p) = wcm.main_player.as_mut() else { return };
            let have: HashSet<i32> = p.chr_ins.special_effect.entries().map(|x| x.param_id).collect();
            let params_ok = unsafe { SoloParamRepository::instance() }.ok();
            for &sp in want.difference(&have) {
                if params_ok.is_some_and(|r| r.get::<SpEffectParam>(sp as u32).is_some()) {
                    p.apply_speffect(sp, false);
                }
            }
            let gone: Vec<i32> = st.applied.difference(&want).copied().collect();
            if !gone.is_empty() {
                let worn = worn_effects();
                for sp in gone.into_iter().filter(|sp| !worn.contains(sp) && have.contains(sp)) {
                    p.remove_speffect(sp);
                }
            }
            st.applied = want;
        }
    }
    let live = live!(wcm);
    let (forced, two): (HashSet<u32>, f32) = {
        let f = FORCED.lock().unwrap_or_else(|e| e.into_inner());
        (f.0.iter().copied().collect(), f.1)
    };
    if forced.is_empty() {
        st.forced_done.clear();
    }
    if rested || (st.tier.is_none() && forced.is_empty()) {
        if !st.elites.is_empty() {
            strip_elites(d, st, &live, wcm);
        }
        if st.tier.is_none() {
            st.rolled.clear();
            return;
        }
    }
    // 不在标了 lock 的档（只有斗技场试炼登记的精英）：不随机魇化、死了不夺魇火
    let (chance, rar, stone) = st.tier.map_or((0.0, 0, 0.0), |t| (d.tiers[t].1, d.tiers[t].3, d.tiers[t].4));
    let Some(around) = around!(wcm, me) else { return };
    st.elites.retain(|a, _| live.contains(a));
    st.rolled.retain(|a| live.contains(a));
    let mut relit = 0u32;
    for e in &around {
        let a = e.chr_ins.as_ptr() as usize;
        if a == me {
            continue;
        }
        let c = unsafe { &mut *e.chr_ins.as_ptr() };
        if FRIENDLY_TEAMS.contains(&c.team_type) || c.team_type == my_team {
            continue;
        }
        let hp = c.modules.data.hp;
        if hp > 0 && forced.contains(&c.event_entity_id) && !st.elites.contains_key(&a) && st.forced_done.insert(a) {
            st.rolled.insert(a);
            make_elite_with(d, st, c, a, true, Some(two));
            continue;
        }
        if hp > 0 && st.rolled.insert(a) {
            let mob = d.mob_e.contains(&c.event_entity_id) || d.mob_n.contains(&c.npc_param_id);
            if mob && st.chance(chance) {
                make_elite(d, st, c, a, true);
            }
            continue;
        }
        let Some(el) = st.elites.get_mut(&a) else { continue };
        // 效果没了就补挂：休息时游戏重新生成敌人、清掉身上的效果，坐下那一刻抽中的精英只剩记录，没有描边、血量和强化，打死却照样给魇火。
        // 血量效果也没了的话，同刚挂上时一样按比例补当前血量（下面的 fix）
        if hp > 0 {
            let missing: Vec<i32> = elite_sps(d, &el.fams).into_iter().filter(|sp| !c.special_effect.entries().any(|x| x.param_id == *sp)).collect();
            if !missing.is_empty() {
                if missing.contains(&d.hp_sp) {
                    el.fix = Some((hp, c.modules.data.max_hp));
                }
                for sp in missing {
                    c.apply_speffect(sp, false);
                }
                relit += 1;
            }
        }
        // 挂上血量倍率后游戏没按比例补当前血量：补上
        if let Some((h0, m0)) = el.fix {
            let max = c.modules.data.max_hp;
            if hp != h0 {
                el.fix = None;
            } else if max != m0 && m0 > 0 {
                c.modules.data.hp = ((h0 as f64 / m0 as f64) * max as f64).round().clamp(1.0, max as f64) as i32;
                el.fix = None;
            }
        }
        // 加快交给 speed.rs 和见切 / 影步减速、时隙乘起来写（以前直接写，见切、影步对精英时灵时不灵）；250 毫秒扫一次，保持 HOLD_SCAN
        let speed = d.colors[el.color].1;
        if speed != 1.0 && hp > 0 {
            crate::speed::want(c, "魇化", speed, crate::speed::HOLD_SCAN);
        }
        let was = el.hp;
        el.hp = c.modules.data.hp;
        if was > 0 && el.hp <= 0 && st.tier.is_none() {
            log(&format!("魇化：精英 NPC {}（实体 {}）死了（不在高难度档，不夺魇火）", c.npc_param_id, c.event_entity_id));
        } else if was > 0 && el.hp <= 0 && (d.range <= 0.0 || e.distance <= d.range) && now.duration_since(el.at) >= SEEN_MIN {
            let fams = el.fams.clone();
            let why = format!("精英 NPC {}（实体 {}）死了（{:.0} 米）", c.npc_param_id, c.event_entity_id, e.distance);
            for k in fams {
                seize(d, st, k, rar, &why);
            }
            if d.goods[0] > 0 && st.chance(stone) {
                let g = d.goods[(st.roll() % 2) as usize];
                if gift_n(1, g, 1) {
                    log(&format!("魇化：精英掉了超限锻造石 {g}"));
                }
            }
        }
    }
    if relit > 0 && st.relit_log < 10 {
        st.relit_log += 1;
        log(&format!("魇化：{relit} 个精英身上的效果没了（多半是休息时敌人重新生成），已补挂"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 精英该挂的效果：血量在前，第一条的颜色最后挂（描边以它为准），两条同色只挂一次
    #[test]
    fn elite_effects() {
        let d = Def {
            hp_sp: 1,
            colors: vec![(10, 1.0), (11, 1.2), (12, 1.0), (13, 1.0)],
            fams: vec![("a".into(), 2), ("b".into(), 0), ("c".into(), 2)],
            ..Def::default()
        };
        assert_eq!(elite_sps(&d, &[1]), [1, 10]);
        assert_eq!(elite_sps(&d, &[0, 1]), [1, 10, 12]);
        assert_eq!(elite_sps(&d, &[0, 2]), [1, 12]);
    }

    /// 定义：档、效果、词条、等级门槛、刻印位门槛、标记段、小怪；等级 / 刻印位按次数算
    #[test]
    fn parse_def() {
        let t = "tier 9956 5 0 1 50\ntier 9957 8 30 2 50\nhp 7303000\ndrain 7303005\ncolor 0 7303001 1\ncolor 1 7303002 1.2\ncolor 2 7303003 1\ncolor 3 7303004 1\n\
                 fam 0 dr_blood_drink 3\nfam 1 max_hp_pct 2\nember_max 3\nrange 30\nlevels 1 5 15 30\nslots 0 4 7 11 14\ncount0 93911 5\nslot_at 4 93981 93985 93989 93492 93496\n\
                 goods 9242 9243\nember0 93616 6 3\nmobe 1 2 3\nmobn 40000\n";
        let d = parse(t).unwrap();
        assert_eq!(d.tiers[1], (9957, 8.0, 30.0, 2, 50.0));
        assert_eq!(d.colors[1], (7303002, 1.2));
        assert_eq!(d.drain, 7303005);
        assert_eq!(d.fams[0], ("dr_blood_drink".to_string(), 3));
        assert_eq!((d.count0, d.slot_bits, d.goods, d.ember0), ((93911, 5), 4, [9242, 9243], (93616, 6, 3)));
        assert_eq!(d.slot_at, [93981, 93985, 93989, 93492, 93496]);
        assert!(d.mob_e.contains(&2) && d.mob_n.contains(&40000));
        assert_eq!([0, 1, 4, 5, 14, 15, 29, 30, 31].map(|n| d.level(n)), [0, 1, 1, 2, 2, 3, 3, 4, 4]);
        assert_eq!([0, 3, 4, 6, 7, 10, 11, 13, 14].map(|n| d.open_slots(n)), [1, 1, 2, 2, 3, 3, 4, 4, 5]);
        assert!(parse("tier 9956 5 0 1 50\n").is_none());
    }
}
