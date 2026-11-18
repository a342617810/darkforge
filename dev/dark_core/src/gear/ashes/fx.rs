//! 骨灰的机制前缀（第二期，用户 2026-11-10「做一下第二期 然后把日志做好」；提案 dev\item_system\骨灰词条提案.md 的 C 类）和召唤日志。
//! 每 SCAN 看一眼召唤物列表（summon_buddy_chr_set，灵马除外），没有召唤物时什么都不做。有召唤物时：
//! - 现在召唤的是哪个骨灰：SummonBuddyManager 的 active_summon_goods_id（容器道具编号 → 容器序号、等级 → 这个角色记录里的稀有度、词条）；
//! - 前缀（ashes.txt 的 pre 行，参数行重随 rr/ashcont.py 建）：
//!   爆裂：召唤物倒下时在它的位置放爆炸子弹（子弹算召唤者的，攻击行在 procs.txt 里随信仰补正）；
//!   殉道：召唤物倒下时召唤者回血；
//!   激昂：召唤物血量低于参数 % 时给它挂攻击加成，回到以上摘掉；
//!   庇护 / 共鸣：有活着的召唤物时召唤者身上挂效果（被清掉了补挂），没有了摘掉；
//!   战意：召唤者参数米内的敌对角色血量变 0 → 活着的召唤物各回血（只有战意的召唤物在场时才看附近）。
//! - 强化加成（稀有度、坚韧这些在容器的强化加成效果里，召唤参数的 dopingSpEffect 挂）：召唤 CHECK_AFTER 后核对血量上限，
//!   等于「敌人参数的血量」（一点加成都没有，2026-11-10 用户测的 +0 狄希就是这样）就自己把容器这一级的强化加成挂上、补满血；
//!   日志里同时记游戏给这只召唤物记的召唤参数编号和挂的加成（SummonBuddyManager 的 groups）。
//! - 召唤物倒下 = 之前见过它血量 > 0、这次 ≤ 0（刚召唤出来那一下血量可能还没设好，不算）；被收回、走远消失的不算倒下。
//! - 日志（「骨灰召唤：」，每次进游戏最多 MAX_LINES 行）：召唤了哪个骨灰（容器、稀有度、前缀、词条、专注消耗和原版的比）、
//!   每只召唤物第一次出现（血量上限和「敌人参数的血量 × 容器这一级的加成」比，看第一期的数值有没有生效）、
//!   召唤 COUNT_AFTER 后数只数（集结多的一只出没出来）、每次前缀触发、召唤物倒下 / 消失、一轮结束的小结。

use super::*;
use eldenring::cs::{ChrIns, ChrInsExt, NpcParam, PlayerIns};
use fromsoftware_shared::Superclass;

use crate::rules::FRIENDLY_TEAMS;

const SCAN: Duration = Duration::from_millis(150);
/// 召唤后多久数一次只数
const COUNT_AFTER: Duration = Duration::from_secs(3);
/// 召唤物出现后多久核对血量上限（强化加成生效没有）
const CHECK_AFTER: Duration = Duration::from_millis(1000);
/// 补挂加成以后多久内上限涨了就补满血
const TOPUP: Duration = Duration::from_secs(3);
/// 灵马的敌人参数（也在召唤物列表里，一直在场，不算）
const TORRENT: std::ops::Range<i32> = 80000000..80100000;
const MAX_LINES: u32 = 800;
/// 激昂每只召唤物最多记几次开 / 关（血量在线上来回会刷屏）
const FURY_LOGS: u32 = 6;
const RAR_ZH: [&str; 4] = ["普通", "稀有", "史诗", "传说"];

#[derive(Debug, Default, Clone, PartialEq)]
struct Sum {
    npc: i32,
    hp: i32,
    max: i32,
    /// 第一次见到；核对过强化加成没有；补挂加成后补满血的期限（补挂时是满血才补）
    seen: Option<Instant>,
    checked: bool,
    topup: Option<Instant>,
    /// 见过血量 > 0
    alive_seen: bool,
    dead: bool,
    /// 身上挂着激昂
    fury: bool,
    fury_logs: u32,
}

/// 一只召唤物这次的变化：倒下了没有、激昂要不要换（Some(要挂)）
fn step(s: &mut Sum, hp: i32, max: i32, fury_line: Option<f32>) -> (bool, Option<bool>) {
    s.hp = hp;
    s.max = max;
    if hp > 0 {
        s.alive_seen = true;
    }
    let died = hp <= 0 && s.alive_seen && !s.dead;
    if died {
        s.dead = true;
    }
    let fury = fury_line.and_then(|pct| {
        let want = hp > 0 && max > 0 && (hp as f32) < pct / 100.0 * max as f32;
        (want != s.fury).then_some(want)
    });
    (died, fury)
}

#[derive(Default)]
struct Round {
    summons: u32,
    deaths: u32,
    gone: u32,
    blasts: u32,
    blast_fail: u32,
    martyr_hp: i32,
    fury_on: u32,
    kills: u32,
    zeal: u32,
    rebuff: u32,
}

#[derive(Default)]
struct Fx {
    next: Option<Instant>,
    lines: u32,
    told_on: bool,
    /// 这一轮召唤的骨灰道具编号；这一轮什么时候开始的（None = 没有召唤物）
    goods: i32,
    start: Option<Instant>,
    counted: bool,
    summons: HashMap<usize, Sum>,
    /// 战意：附近敌对角色的地址 → 上次的血量
    foes: HashMap<usize, i32>,
    /// 召唤者身上挂着的庇护 / 共鸣效果
    on_player: Option<i32>,
    round: Round,
}

static FX: Mutex<Option<Fx>> = Mutex::new(None);

fn say(fx: &mut Fx, s: String) {
    if fx.lines >= MAX_LINES {
        return;
    }
    fx.lines += 1;
    log(&format!("骨灰召唤：{s}"));
    if fx.lines == MAX_LINES {
        log("骨灰召唤：这次进游戏的日志写满了，后面的不记");
    }
}

/// 容器道具编号 → (容器序号, 等级)
fn cont_of(def: &Def, goods: i32) -> Option<(u32, u32)> {
    let g = u32::try_from(goods).ok()?;
    (g >= def.goods0 && g < def.goods0 + 100 * def.n && (g - def.goods0) % 100 < LEVELS).then(|| ((g - def.goods0) / 100, (g - def.goods0) % 100))
}

/// 现在召唤的容器：(序号, 等级, 记录, 种类)
fn current<'a>(def: &'a Def, a: &'a AshSt, goods: i32) -> Option<(u32, u32, &'a AshRec, &'a Kind)> {
    let (idx, lv) = cont_of(def, goods)?;
    let rec = a.recs.get(&idx)?;
    let k = def.kinds.iter().find(|k| k.base == rec.kind)?;
    Some((idx, lv, rec, k))
}

fn pre_of<'a>(def: &'a Def, rec: &AshRec) -> Option<&'a Pre> {
    rec.pre.as_ref().and_then(|key| def.pres.iter().find(|p| p.key == *key))
}

/// 前缀这一档的说明（数值填好）
fn pre_text(p: &Pre, r: usize) -> String {
    p.text[0].replace('#', &num(p.vals[r.min(3)]))
}

/// 召唤了哪个骨灰（一轮开始、换了骨灰时记）
fn header(def: &Def, a: &AshSt, goods: i32) -> String {
    let repo = unsafe { SoloParamRepository::instance() }.ok();
    let mp = |id: u32| repo.and_then(|r| r.get::<EquipParamGoods>(id)).map_or("?".to_string(), |g| g.consume_mp().to_string());
    if let Some((idx, lv, rec, k)) = current(def, a, goods) {
        let r = rec.rar.min(3);
        let pre = pre_of(def, rec).map_or("无".to_string(), |p| format!("{}（{}）", p.name[0], pre_text(p, r)));
        let rows = k.rows.len() + rec_extra(rec, k) as usize;
        return format!(
            "召唤 {}＋{lv}（容器 {idx}，道具 {goods}）：{}，前缀 {pre}，数值词条 {:?}{}；召唤参数 {rows} 行；专注消耗 {}（原版 {}）",
            k.name[0],
            RAR_ZH[r],
            rec.affs,
            if rec.rally { "，集结" } else { "" },
            mp(goods as u32),
            mp(k.base + lv)
        );
    }
    match cont_of(def, goods) {
        Some((idx, _)) => format!("召唤的是容器 {idx}（道具 {goods}），这个角色的记录里没有它：召唤物照容器参数出来，前缀不生效"),
        None if goods > 0 && def.by_id.contains_key(&(goods as u32)) => {
            format!("召唤的是原版骨灰 {goods}（还没换成容器：容器用满了，或者刚拿到还没转换），没有稀有度和词条")
        }
        None => format!("召唤的骨灰道具编号读到 {goods}：不是容器也不是原版骨灰（游戏结构对不上？），前缀不生效"),
    }
}

/// 召唤物 → (召唤参数编号, 挂的强化加成效果)：SummonBuddyManager 的 groups（最多看 64 组、每组 16 只）
fn groups(wcm: &WorldChrMan) -> HashMap<usize, (i32, u32)> {
    let mut out = HashMap::new();
    for pair in wcm.summon_buddy_manager.groups.iter().take(64) {
        for g in pair.second.iter().take(16) {
            out.insert(g.chr_ins.as_ptr() as usize, (g.buddy_param_id, g.dopping_level_sp_effect_id));
        }
    }
    out
}

/// 装备 22 格的名字（ChrAsmSlot 的顺序）
const SLOT_ZH: [&str; 22] = [
    "左手1", "右手1", "左手2", "右手2", "左手3", "右手3", "箭1", "弩箭1", "箭2", "弩箭2", "箭3", "弩箭3", "头", "身", "手", "腿", "（空格）", "护符1", "护符2",
    "护符3", "护符4", "第五护符",
];

/// 用玩家形象的召唤物（仿身泪滴、傀儡这些，游戏里是 PlayerIns；按 RTTI 认，认不出就 None）和召唤者每一格装备的参数编号比
fn gear_diff(wcm: &WorldChrMan, addr: usize) -> Option<String> {
    let mine = wcm.main_player.as_ref()?.chr_asm.equipment_param_ids;
    let c = wcm.summon_buddy_chr_set.characters().find(|c| &**c as *const ChrIns as usize == addr)?;
    let theirs = c.as_subclass::<PlayerIns>()?.chr_asm.equipment_param_ids;
    let diff: Vec<String> = (0..22).filter(|&i| mine[i] != theirs[i]).map(|i| format!("{} {}→{}", SLOT_ZH[i], mine[i], theirs[i])).collect();
    Some(if diff.is_empty() {
        "装备每一格都和召唤者一样".into()
    } else {
        format!("装备和召唤者不一样的 {} 格（召唤者→召唤物）：{}", diff.len(), diff.join("，"))
    })
}

/// 核对强化加成：(敌人参数的血量, 容器这一级的加成倍率, 原版这一级的加成倍率, 容器这一级的加成效果)
fn expect(def: &Def, cur: Option<(u32, u32, &AshRec, &Kind)>, npc: i32) -> Option<(f32, f32, f32, u32)> {
    let (idx, lv, _, k) = cur?;
    let repo = unsafe { SoloParamRepository::instance() }.ok()?;
    let base = repo.get::<NpcParam>(npc as u32)?.hp() as f32;
    let dop = def.dop0 + LEVELS * idx + lv;
    let rate = repo.get::<SpEffectParam>(dop)?.max_hp_rate();
    let vrate = repo.get::<BuddyParam>(k.rows[0]).map(|b| dop_get(b, lv)).filter(|&v| v > 0).and_then(|v| repo.get::<SpEffectParam>(v as u32)).map_or(1.0, |s| s.max_hp_rate());
    Some((base, rate, vrate, dop))
}

fn near(max: i32, x: f32) -> bool {
    (max as f32 - x).abs() <= (x * 0.02).max(2.0)
}

/// 一轮结束：摘掉召唤者身上的效果，记小结
fn end_round(fx: &mut Fx, wcm: &mut WorldChrMan, why: &str) {
    if let Some(id) = fx.on_player.take() {
        if let Some(p) = wcm.main_player.as_mut() {
            p.remove_speffect(id);
        }
        say(fx, format!("召唤者身上的效果 {id} 摘掉了（没有召唤物了）"));
    }
    let r = std::mem::take(&mut fx.round);
    let mut parts = vec![format!("召唤物 {} 只，倒下 {}，收回 / 消失 {}", r.summons, r.deaths, r.gone)];
    if r.blasts + r.blast_fail > 0 {
        parts.push(format!("爆裂 {} 次{}", r.blasts, if r.blast_fail > 0 { format!("（{} 次没放出来）", r.blast_fail) } else { String::new() }));
    }
    if r.martyr_hp > 0 {
        parts.push(format!("殉道一共回血 {}", r.martyr_hp));
    }
    if r.fury_on > 0 {
        parts.push(format!("激昂生效 {} 次", r.fury_on));
    }
    if r.kills > 0 {
        parts.push(format!("附近敌人死亡 {} 次（战意回血 {} 次）", r.kills, r.zeal));
    }
    if r.rebuff > 0 {
        parts.push(format!("召唤者身上的效果补挂 {} 次", r.rebuff));
    }
    say(fx, format!("{why}。这一轮：{}", parts.join("，")));
    fx.summons.clear();
    fx.foes.clear();
    fx.start = None;
    fx.counted = false;
}

/// 进存档：清掉上一轮（召唤者身上的效果不存档，不用摘）
pub(super) fn reset() {
    let mut g = FX.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(fx) = g.as_mut() {
        fx.summons.clear();
        fx.foes.clear();
        fx.on_player = None;
        fx.start = None;
        fx.counted = false;
        fx.goods = 0;
        fx.round = Round::default();
    }
}

/// 开发工具「骨灰状态」：现在在场的召唤物
pub(super) fn status() -> String {
    let g = FX.lock().unwrap_or_else(|e| e.into_inner());
    match g.as_ref().filter(|f| f.start.is_some()) {
        Some(f) => {
            let v: Vec<String> = f.summons.values().map(|s| format!("{} 血 {}/{}{}{}", s.npc, s.hp, s.max, if s.dead { " 倒下" } else { "" }, if s.fury { " 激昂中" } else { "" })).collect();
            format!("召唤物在场（道具 {}）：{}；召唤者身上挂着 {:?}", f.goods, v.join("；"), f.on_player)
        }
        None => "现在没有召唤物".into(),
    }
}

pub(super) fn tick(def: &Def, a: &AshSt) {
    let mut g = FX.lock().unwrap_or_else(|e| e.into_inner());
    let fx = g.get_or_insert_with(Fx::default);
    let now = Instant::now();
    if fx.next.is_some_and(|t| now < t) {
        return;
    }
    fx.next = Some(now + SCAN);
    if !fx.told_on {
        fx.told_on = true;
        let names: Vec<&str> = def.pres.iter().map(|p| p.name[0].as_str()).collect();
        say(fx, format!("开着（机制前缀 {} 条：{}；召唤、召唤物出现 / 倒下、前缀触发都记，每次进游戏最多 {MAX_LINES} 行）", names.len(), names.join("、")));
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    // 召唤物：(地址, 敌人参数, 血, 上限, 位置)
    let cur: Vec<(usize, i32, i32, i32, [f32; 3])> = wcm
        .summon_buddy_chr_set
        .characters()
        .filter(|c| !TORRENT.contains(&c.npc_param_id))
        .map(|c| {
            let a = &*c as *const ChrIns as usize;
            let p = &c.modules.physics.position;
            (a, c.npc_param_id, c.modules.data.hp, c.modules.data.max_hp, [p.0, p.1, p.2])
        })
        .collect();
    if cur.is_empty() {
        if fx.start.is_some() {
            end_round(fx, wcm, "召唤物都没了");
        }
        return;
    }
    let goods = wcm.summon_buddy_manager.active_summon_goods_id;
    if fx.start.is_none() || goods != fx.goods {
        if fx.start.is_some() {
            let why = format!("换了骨灰（{} → {goods}）", fx.goods);
            end_round(fx, wcm, &why);
        }
        fx.goods = goods;
        fx.start = Some(now);
        fx.counted = false;
        let h = header(def, a, goods);
        say(fx, h);
    }
    let cur_ash = current(def, a, goods);
    let r = cur_ash.map_or(0, |x| x.2.rar.min(3));
    let pre = cur_ash.and_then(|x| pre_of(def, x.2));
    let fury_line = pre.filter(|p| p.kind == PreKind::Fury).map(|p| p.arg);

    // 召唤物：第一次出现、倒下、激昂
    let mut died: Vec<(i32, [f32; 3])> = Vec::new();
    let mut fury_set: Vec<(usize, bool)> = Vec::new();
    let mut topups: Vec<usize> = Vec::new();
    let mut checks: Vec<(usize, i32, i32, i32)> = Vec::new();
    for (addr, npc, hp, max, pos) in &cur {
        if !fx.summons.contains_key(addr) {
            fx.round.summons += 1;
            say(fx, format!("召唤物出现：敌人参数 {npc}，血 {hp}/{max}（强化加成要过一会儿才挂上，{} 秒后核对）", CHECK_AFTER.as_secs_f32()));
            fx.summons.insert(*addr, Sum { npc: *npc, seen: Some(now), ..Sum::default() });
        }
        let Some(s) = fx.summons.get_mut(addr) else { continue };
        let grew = *max > s.max && s.max > 0;
        let (d, f) = step(s, *hp, *max, fury_line);
        // 补挂加成以后上限涨了：补满血
        if grew && s.topup.is_some_and(|t| now < t) && *hp > 0 {
            topups.push(*addr);
        }
        // 核对强化加成
        if !s.checked && *hp > 0 && s.seen.is_some_and(|t| now - t >= CHECK_AFTER) {
            s.checked = true;
            checks.push((*addr, *npc, *hp, *max));
        }
        if d {
            died.push((*npc, *pos));
        }
        if let Some(want) = f {
            fury_set.push((*addr, want));
        }
    }
    let here: HashSet<usize> = cur.iter().map(|x| x.0).collect();
    let mut gone = Vec::new();
    fx.summons.retain(|a, s| {
        let keep = here.contains(a);
        if !keep && !s.dead {
            gone.push(format!("召唤物消失（敌人参数 {}，血 {}/{}）：收回 / 走远了，不算倒下", s.npc, s.hp, s.max));
        }
        keep
    });
    for l in gone {
        fx.round.gone += 1;
        say(fx, l);
    }
    for (npc, _) in &died {
        fx.round.deaths += 1;
        say(fx, format!("召唤物倒下：敌人参数 {npc}"));
    }
    if !fx.counted && fx.start.is_some_and(|t| now - t >= COUNT_AFTER) {
        fx.counted = true;
        let n = cur.len();
        let line = match cur_ash {
            Some((_, _, rec, k)) => {
                let want = k.rows.len() + rec_extra(rec, k) as usize;
                format!(
                    "召唤 {} 秒后在场 {n} 只，召唤参数写了 {want} 行（原版 {}{}）{}",
                    COUNT_AFTER.as_secs(),
                    k.rows.len(),
                    if rec_extra(rec, k) { " + 集结 1" } else { "" },
                    if n == want { "，对得上" } else { "，对不上（有倒下的、还没出来的，或者集结那一只没召唤出来）" }
                )
            }
            None => format!("召唤 {} 秒后在场 {n} 只", COUNT_AFTER.as_secs()),
        };
        say(fx, line);
    }

    // 强化加成核对：上限 = 敌人参数的血量（一点加成都没有）→ 补挂容器这一级的加成
    let mut dop_fix: Vec<(usize, u32)> = Vec::new();
    if !checks.is_empty() {
        let gs = groups(wcm);
        for (addr, npc, hp, max) in checks {
            let g = gs.get(&addr).map_or("游戏的召唤记录里没找到它".to_string(), |(b, s)| format!("游戏记的召唤参数 {b}、强化加成 {s}"));
            // 用玩家形象的：血量照召唤者算，不按敌人参数核对；记装备
            if let Some(gear) = gear_diff(wcm, addr) {
                say(fx, format!("用玩家形象的召唤物（敌人参数 {npc}）：血 {hp}/{max}（照召唤者算，不核对强化加成）；{g}；{gear}"));
                continue;
            }
            let line = match expect(def, cur_ash, npc) {
                Some((base, rate, vrate, dop)) => {
                    let (ours, van) = ((base * rate).round(), (base * vrate).round());
                    if near(max, ours) {
                        format!("召唤物（敌人参数 {npc}）强化加成生效了：上限 {max} = {base} × {rate:.3}；{g}")
                    } else if near(max, base) {
                        dop_fix.push((addr, dop));
                        if let Some(s) = fx.summons.get_mut(&addr) {
                            s.topup = (hp >= max).then_some(now + TOPUP);
                        }
                        format!("召唤物（敌人参数 {npc}）没有强化加成：上限 {max} = 敌人参数的血量（应该 × {rate:.3} = {ours}）；{g}；补挂容器的加成 {dop}")
                    } else if near(max, van) {
                        format!("召唤物（敌人参数 {npc}）用的是原版的加成：上限 {max} = {base} × {vrate:.3}（容器的应该 {ours}）；{g}")
                    } else {
                        format!("召唤物（敌人参数 {npc}）上限 {max}，对不上：敌人参数 {base}、容器加成后 {ours}、原版加成后 {van}；{g}")
                    }
                }
                None => format!("召唤物（敌人参数 {npc}）上限 {max}（不是容器骨灰，或者参数读不到，不核对）；{g}"),
            };
            say(fx, line);
        }
    }

    // 战意：附近敌对角色血量变 0（先看，后面要拿召唤者的可变引用）
    let mut kills: Vec<(i32, f32)> = Vec::new();
    match pre.filter(|p| p.kind == PreKind::Zeal) {
        Some(p) => {
            let me = wcm.main_player.as_ref().map(|x| (&x.chr_ins as *const ChrIns as usize, x.chr_ins.team_type));
            if let (Some((me, my_team)), Some(around)) = (me, me.and_then(|m| around!(wcm, m.0))) {
                let mut seen = HashSet::new();
                for e in &around {
                    let a = e.chr_ins.as_ptr() as usize;
                    if a == me || e.distance > p.arg || here.contains(&a) {
                        continue;
                    }
                    let c = unsafe { e.chr_ins.as_ref() };
                    if FRIENDLY_TEAMS.contains(&c.team_type) || c.team_type == my_team {
                        continue;
                    }
                    seen.insert(a);
                    let hp = c.modules.data.hp;
                    if fx.foes.insert(a, hp).is_some_and(|h0| h0 > 0 && hp <= 0) {
                        kills.push((c.npc_param_id, e.distance));
                    }
                }
                fx.foes.retain(|a, _| seen.contains(a));
            }
        }
        None => fx.foes.clear(),
    }

    // 召唤者：爆裂、殉道、庇护 / 共鸣
    let any_alive = cur.iter().any(|x| x.2 > 0);
    if let Some(p) = wcm.main_player.as_mut() {
        if let Some(pr) = pre {
            let v = pr.vals[r];
            for (npc, pos) in &died {
                match pr.kind {
                    PreKind::Blast => {
                        let bullet = pr.ids[r];
                        let at = [pos[0], pos[1] + 0.5, pos[2]];
                        match crate::orbshot::spawn_at(&p.chr_ins, bullet, at) {
                            Ok(()) => {
                                fx.round.blasts += 1;
                                let m = crate::procs::mults()[2];
                                say(fx, format!(
                                    "爆裂：召唤物（敌人参数 {npc}）倒下，在 ({:.1}, {:.1}, {:.1}) 放爆炸子弹 {bullet}：火焰 {} × 信仰补正 {m:.2} ≈ {:.0}",
                                    at[0], at[1], at[2], num(v), v * m
                                ));
                            }
                            Err(e) => {
                                fx.round.blast_fail += 1;
                                say(fx, format!("爆裂：召唤物（敌人参数 {npc}）倒下，爆炸子弹 {bullet} 没放出来：{e}"));
                            }
                        }
                    }
                    PreKind::Martyr => {
                        let x = &mut p.chr_ins.modules.data;
                        if x.hp > 0 {
                            let before = x.hp;
                            x.hp = (x.hp + (x.max_hp as f32 * v / 100.0).round() as i32).min(x.max_hp);
                            fx.round.martyr_hp += x.hp - before;
                            let (h, m) = (x.hp, x.max_hp);
                            say(fx, format!("殉道：召唤物（敌人参数 {npc}）倒下，召唤者回血 {}％：{before} → {h} / {m}", num(v)));
                        } else {
                            say(fx, format!("殉道：召唤物（敌人参数 {npc}）倒下，召唤者已经倒下了，不回血"));
                        }
                    }
                    _ => {}
                }
            }
        }
        let want = pre.filter(|p| matches!(p.kind, PreKind::Shelter | PreKind::Resonance) && any_alive).map(|p| p.ids[r]);
        if let Some(old) = fx.on_player.filter(|o| Some(*o) != want) {
            p.remove_speffect(old);
            fx.on_player = None;
            say(fx, format!("召唤者身上的效果 {old} 摘掉了（{}）", if any_alive { "换了骨灰" } else { "召唤物都倒下了" }));
        }
        if let (Some(id), Some(pr)) = (want, pre) {
            if !p.chr_ins.special_effect.entries().any(|e| e.param_id == id) {
                p.apply_speffect(id, false);
                if fx.on_player == Some(id) {
                    fx.round.rebuff += 1;
                    say(fx, format!("{}：召唤者身上的效果 {id} 被清掉了，补挂", pr.name[0]));
                } else {
                    say(fx, format!("{}：有召唤物在场，召唤者挂上效果 {id}（{}）", pr.name[0], pre_text(pr, r)));
                }
            }
            fx.on_player = Some(id);
        }
    }

    // 局内难度（用户 2026-11-17「让骨灰也会被难度减伤」）：玩家身上是哪一档的难度效果，活着的召唤物就挂那一档的造成伤害效果
    // （×1/敌人血量；玩家自己的伤害就是这么降的，召唤物以前不吃）。换了档摘掉别的档；没选过难度 / 普通档就都不挂
    if !def.diff_ash.is_empty() {
        let want = wcm.main_player.as_ref().and_then(|p| {
            p.chr_ins.special_effect.entries().find_map(|e| def.diff_ash.iter().find(|x| x.0 == e.param_id).map(|x| x.1))
        });
        let mut put: Vec<(i32, i32)> = Vec::new();
        for c in wcm.summon_buddy_chr_set.characters() {
            if TORRENT.contains(&c.npc_param_id) || c.modules.data.hp <= 0 {
                continue;
            }
            let has: Vec<i32> = c.special_effect.entries().map(|e| e.param_id).filter(|id| def.diff_ash.iter().any(|x| x.1 == *id)).collect();
            for &id in has.iter().filter(|&&id| Some(id) != want) {
                c.remove_speffect(id);
            }
            if let Some(w) = want.filter(|w| !has.contains(w)) {
                c.apply_speffect(w, false);
                put.push((c.npc_param_id, w));
            }
        }
        for (npc, w) in put {
            say(fx, format!("难度：召唤物（敌人参数 {npc}）挂上这一档的造成伤害效果 {w}"));
        }
    }

    // 召唤物：补挂强化加成、补满血、激昂开关、战意回血
    if fury_set.is_empty() && kills.is_empty() && dop_fix.is_empty() && topups.is_empty() {
        return;
    }
    let (fury_sp, zeal_v) = match pre {
        Some(p) if p.kind == PreKind::Fury => (p.ids[r], 0.0),
        Some(p) if p.kind == PreKind::Zeal => (0, p.vals[r]),
        _ => (0, 0.0),
    };
    let mut lines = Vec::new();
    let mut healed = 0;
    for c in wcm.summon_buddy_chr_set.characters() {
        let a = &*c as *const ChrIns as usize;
        if let Some(&(_, dop)) = dop_fix.iter().find(|x| x.0 == a) {
            c.apply_speffect(dop as i32, false);
            let on = c.special_effect.entries().any(|e| e.param_id == dop as i32);
            lines.push(format!("补挂强化加成 {dop}：{}", if on { "挂上了" } else { "挂完身上没有（挂不上）" }));
        }
        if topups.contains(&a) {
            let x = &mut c.modules.data;
            let before = x.hp;
            x.hp = x.max_hp;
            lines.push(format!("强化加成挂上以后上限涨到 {}，补满血（{before} → {}）", x.max_hp, x.hp));
        }
        if let Some(&(_, on)) = fury_set.iter().find(|x| x.0 == a) {
            if on {
                c.apply_speffect(fury_sp, false);
            } else {
                c.remove_speffect(fury_sp);
            }
            if let Some(s) = fx.summons.get_mut(&a) {
                s.fury = on;
                if on {
                    fx.round.fury_on += 1;
                }
                if s.fury_logs < FURY_LOGS {
                    s.fury_logs += 1;
                    lines.push(format!(
                        "激昂：召唤物（敌人参数 {}）血 {}/{}，{}",
                        s.npc,
                        s.hp,
                        s.max,
                        if on { format!("挂上攻击加成 {fury_sp}") } else { format!("回到线以上，摘掉 {fury_sp}") }
                    ));
                }
            }
        }
        if !kills.is_empty() && zeal_v > 0.0 && here.contains(&a) {
            let x = &mut c.modules.data;
            if x.hp > 0 {
                x.hp = (x.hp + (x.max_hp as f32 * zeal_v / 100.0).round() as i32).min(x.max_hp);
                healed += 1;
            }
        }
    }
    for l in lines {
        say(fx, l);
    }
    for (npc, dist) in &kills {
        fx.round.kills += 1;
        say(fx, format!("附近的敌人死亡（敌人参数 {npc}，{dist:.1} 米）"));
    }
    if !kills.is_empty() && zeal_v > 0.0 {
        fx.round.zeal += 1;
        say(fx, format!("战意：{healed} 只召唤物各回血 {}％", num(zeal_v)));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 倒下：见过活的才算、只算一次；刚出来血量 0 不算
    #[test]
    fn death_needs_alive_first() {
        let mut s = Sum::default();
        assert_eq!(step(&mut s, 0, 0, None), (false, None), "刚召唤出来血量还没设好");
        assert_eq!(step(&mut s, 500, 500, None), (false, None));
        assert_eq!(step(&mut s, 0, 500, None), (true, None));
        assert_eq!(step(&mut s, 0, 500, None), (false, None), "只算一次");
    }

    /// 激昂：低于线挂、回到线以上摘、倒下摘
    #[test]
    fn fury_switches_on_the_line() {
        let mut s = Sum::default();
        assert_eq!(step(&mut s, 500, 500, Some(30.0)), (false, None));
        assert_eq!(step(&mut s, 149, 500, Some(30.0)), (false, Some(true)));
        s.fury = true;
        assert_eq!(step(&mut s, 120, 500, Some(30.0)), (false, None), "已经挂着");
        assert_eq!(step(&mut s, 151, 500, Some(30.0)), (false, Some(false)));
        s.fury = false;
        step(&mut s, 100, 500, Some(30.0));
        s.fury = true;
        assert_eq!(step(&mut s, 0, 500, Some(30.0)), (true, Some(false)), "倒下了摘掉");
    }

    #[test]
    fn container_of_goods() {
        let d = super::super::tests::sample();
        assert_eq!(cont_of(&d, 150000503), Some((5, 3)));
        assert_eq!(cont_of(&d, 150000511), None, "等级只到 10");
        assert_eq!(cont_of(&d, 232000), None);
        assert_eq!(cont_of(&d, -1), None);
        assert_eq!(cont_of(&d, (150000000 + 100 * 120) as i32), None, "超出容器数");
    }
}
