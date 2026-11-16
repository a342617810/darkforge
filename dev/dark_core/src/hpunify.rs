//! 高难度血量补正（参数侧见重随的 rr/hpunify.py；设计稿 dev\item_system\超限锻造石与高难度.md §3）：
//! 「死亡」「不可能」（当前档标记亮着）时给在场的敌人挂最大血量倍率效果——小怪统一拉到毕业水平、Boss 统一难度。
//! 每个位置挂哪一档由重随算好：hpunify.txt 的 e 实体 效果 / n 敌人参数 效果（实体优先）。
//! 攻击力（用户 2026-11-03：前期小怪根本打不动人）：另一组效果（arange），ae 实体 效果 / an 敌人参数 效果，同样在扫描时挂、切出时摘。
//! 卢恩（用户 2026-11-04「补正一下高难度下boss的卢恩获取 20w起步」…「小怪直接均匀一点好了 因为难度也均匀了」）：小怪第三组效果
//! （rrange，haveSoulRate 倍率：角色身上的卢恩出去时乘），re 实体 效果 / rn 敌人参数 效果，同攻击力；
//! Boss 的击败奖励：area 区域行 单人 多人（GameAreaParam 的 bonusSoul_single / multi），进这几档时改参数（记下原来的）、切出时改回。
//! 小怪掉落统一到 DLC 最后一档（用户 2026-11-04「高难度后小怪爆率统一到dlc后期」，参数侧 rr/unidentified.py 的 hard_lines）：
//! droptgt 种类（0 普通 / 1 精英）目标第一行 行数；dropcopy 种类 第一行 行数 = 一张复制表接上的那几行。进这几档时把目标行的道具格
//! （道具 / 类别 / 权重 / 每格标记 0~127 字节、个数 / 发现力 138~147 字节）照抄到每张复制表的那几行（记下原来的），切出时改回。
//! 异常抗性（用户 2026-11-09「死亡和不可能敌人异常抗性也*2.22和2.5」）：sr 档位标记 效果 = 七种抗性乘同一个倍率的效果行，每档一行。敌对、活着的角色都挂当前档的
//! （不看有没有血量补正），「死亡」「不可能」互相切换时摘掉另一档的。乘的是敌人的抗性，累积从哪来都算（武器、法术、道具、油脂的命中时触发）。
//! - 每 0.5 秒扫一遍游戏的 ChrSet（各地图块 + 开放地图，不碰距离列表，见 chrs.rs）：活着、查得到、身上没有那一档的就挂上。
//!   Boss 在进 Boss 房之前就加载着，开打时已经改过；死了重置、休息后重新生成的效果没了，下一轮再挂。
//! - 挂上时记下当时的血量 / 上限。之后上限变了、血量还停在原来那个数（被事件禁用着的敌人挂上去，游戏不按比例补当前血量；
//!   随机器挂缩放时见过，落叶丹恩出场约 70%），按原来的比例补上；血量动过一次就不再管。
//! - 切出这几档（标记连续 1 秒没亮）：摘掉在场敌人身上的这组效果，一次。
//! - 只在这几档里跑；不重随启动（参数里没有这组效果）时不挂。联机先不管（用户 2026-11-03）。

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{ChrIns, ChrInsExt, GameAreaParam, ItemLotParam_enemy, SoloParamRepository, SpEffectParam, WorldChrMan};
use eldenring::param::ITEMLOT_PARAM_ST;
use fromsoftware_shared::FromStatic;

use crate::rules::FRIENDLY_TEAMS;
use crate::{dir, log};

/// 多久扫一遍
const SCAN: Duration = Duration::from_millis(500);
/// 标记没亮多久才算切出这几档（读档时可能闪一下）
const OFF_GRACE: Duration = Duration::from_secs(1);
/// 前这么多次挂效果 / 补血量逐个写日志（游戏里核对用），之后每分钟写一次累计
const LOG_EACH: u32 = 30;

#[derive(Debug, Default, PartialEq)]
struct Def {
    flags: Vec<u32>,
    base: i32,
    n: i32,
    ent: HashMap<u32, i32>,
    npc: HashMap<i32, i32>,
    /// 攻击力倍率那组效果：起点、行数；实体 / 敌人参数 → 效果
    abase: i32,
    an: i32,
    aent: HashMap<u32, i32>,
    anpc: HashMap<i32, i32>,
    /// 卢恩倍率那组效果：起点、行数；实体 / 敌人参数 → 效果
    rbase: i32,
    rn: i32,
    rent: HashMap<u32, i32>,
    rnpc: HashMap<i32, i32>,
    /// 异常抗性：(档位标记, 这一档的效果)
    res: Vec<(u32, i32)>,
    /// Boss 击败奖励：(区域行, 单人, 多人)
    area: Vec<(u32, u32, u32)>,
    /// 掉落统一：目标行（普通 / 精英：第一行, 行数）、复制表接上的行（种类, 第一行, 行数）
    drop_tgt: [(u32, u32); 2],
    drop_copy: Vec<(usize, u32, u32)>,
}

/// 掉落表一行里道具格的两段（字节范围）：道具 / 类别 / 权重 / 每格标记、个数 / 发现力
const LOT_SPANS: [(usize, usize); 2] = [(0, 128), (138, 148)];

impl Def {
    fn owns(&self, sp: i32) -> bool {
        (self.base..self.base + self.n).contains(&sp) || (self.abase..self.abase + self.an).contains(&sp)
            || (self.rbase..self.rbase + self.rn).contains(&sp)
            || self.res.iter().any(|&(_, s)| s == sp)
    }
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();
static PARAMS_OK: OnceLock<bool> = OnceLock::new();

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}').trim();
        let f: Vec<&str> = l.split_whitespace().collect();
        match f.as_slice() {
            ["flag", x] => d.flags.extend(x.parse::<u32>().ok()),
            ["range", b, n] => {
                if let (Ok(b), Ok(n)) = (b.parse(), n.parse()) {
                    (d.base, d.n) = (b, n);
                }
            }
            ["e", e, sp] => {
                if let (Ok(e), Ok(sp)) = (e.parse(), sp.parse()) {
                    d.ent.insert(e, sp);
                }
            }
            ["n", n, sp] => {
                if let (Ok(n), Ok(sp)) = (n.parse(), sp.parse()) {
                    d.npc.insert(n, sp);
                }
            }
            ["arange", b, n] => {
                if let (Ok(b), Ok(n)) = (b.parse(), n.parse()) {
                    (d.abase, d.an) = (b, n);
                }
            }
            ["ae", e, sp] => {
                if let (Ok(e), Ok(sp)) = (e.parse(), sp.parse()) {
                    d.aent.insert(e, sp);
                }
            }
            ["an", n, sp] => {
                if let (Ok(n), Ok(sp)) = (n.parse(), sp.parse()) {
                    d.anpc.insert(n, sp);
                }
            }
            ["rrange", b, n] => {
                if let (Ok(b), Ok(n)) = (b.parse(), n.parse()) {
                    (d.rbase, d.rn) = (b, n);
                }
            }
            ["re", e, sp] => {
                if let (Ok(e), Ok(sp)) = (e.parse(), sp.parse()) {
                    d.rent.insert(e, sp);
                }
            }
            ["rn", n, sp] => {
                if let (Ok(n), Ok(sp)) = (n.parse(), sp.parse()) {
                    d.rnpc.insert(n, sp);
                }
            }
            ["sr", f, sp] => {
                if let (Ok(f), Ok(sp)) = (f.parse(), sp.parse()) {
                    d.res.push((f, sp));
                }
            }
            ["area", r, a, b] => {
                if let (Ok(r), Ok(a), Ok(b)) = (r.parse(), a.parse(), b.parse()) {
                    d.area.push((r, a, b));
                }
            }
            ["droptgt", k, first, n] => {
                if let (Ok(k), Ok(first), Ok(n)) = (k.parse::<usize>(), first.parse(), n.parse()) {
                    if k < 2 {
                        d.drop_tgt[k] = (first, n);
                    }
                }
            }
            ["dropcopy", k, first, n] => {
                if let (Ok(k), Ok(first), Ok(n)) = (k.parse::<usize>(), first.parse(), n.parse()) {
                    if k < 2 {
                        d.drop_copy.push((k, first, n));
                    }
                }
            }
            _ => {}
        }
    }
    d.ent.retain(|_, sp| (d.base..d.base + d.n).contains(sp));
    d.npc.retain(|_, sp| (d.base..d.base + d.n).contains(sp));
    d.aent.retain(|_, sp| (d.abase..d.abase + d.an).contains(sp));
    d.anpc.retain(|_, sp| (d.abase..d.abase + d.an).contains(sp));
    d.rent.retain(|_, sp| (d.rbase..d.rbase + d.rn).contains(sp));
    d.rnpc.retain(|_, sp| (d.rbase..d.rbase + d.rn).contains(sp));
    // 目标没写（或者行数对不上）的复制表不改
    let tgt = d.drop_tgt;
    d.drop_copy.retain(|&(k, _, n)| tgt[k].1 > 0 && n == tgt[k].1);
    let any = !d.ent.is_empty() || !d.npc.is_empty() || !d.aent.is_empty() || !d.anpc.is_empty() || !d.rent.is_empty()
        || !d.rnpc.is_empty() || !d.res.is_empty() || !d.area.is_empty() || !d.drop_copy.is_empty();
    (!d.flags.is_empty() && d.n > 0 && any).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("hpunify.txt")).unwrap_or_default())).as_ref()
}

/// 游戏里的参数是不是重随改过的（这组效果的头尾都在）：不重随的模式启动时 hpunify.txt 还是上次重随留下的
fn params_ok(d: &Def) -> bool {
    *PARAMS_OK.get_or_init(|| {
        let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return false };
        let ok = repo.get::<SpEffectParam>(d.base as u32).is_some() && repo.get::<SpEffectParam>((d.base + d.n - 1) as u32).is_some()
            && d.res.iter().all(|&(_, sp)| repo.get::<SpEffectParam>(sp as u32).is_some());
        if !ok {
            log("高难度血量补正：游戏里的参数没有这组效果（大概是用不重随的模式启动的），这次不挂");
        }
        ok
    })
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("高难度血量补正（标记 {:?}，{} 个实体、{} 个敌人参数；攻击力 {} 个实体、{} 个敌人参数；卢恩 {} 个实体、{} 个敌人参数、Boss 奖励 {} 处；异常抗性 {} 档）",
                           d.flags, d.ent.len(), d.npc.len(), d.aent.len(), d.anpc.len(), d.rent.len(), d.rnpc.len(), d.area.len(), d.res.len()),
        None => "高难度血量补正（没有 hpunify.txt，不管）".into(),
    }
}

/// 挂上时的血量、上限
struct Watch {
    hp: i32,
    max: i32,
}

struct St {
    next: Instant,
    on: bool,
    off_since: Option<Instant>,
    watch: HashMap<usize, Watch>,
    applied: u64,
    fixed: u64,
    /// 攻击力 / 卢恩倍率挂了几次
    atk: u64,
    rune: u64,
    /// 异常抗性挂了几次
    res: u64,
    /// 改过的 Boss 击败奖励原来的值（区域行, 单人, 多人）；空 = 没改
    area_orig: Vec<(u32, u32, u32)>,
    /// 改过的掉落表行原来的道具格（行, 两段字节）；空 = 没改
    drop_orig: Vec<(u32, Vec<u8>)>,
    logged: u32,
    told: (u64, u64),
    told_at: Instant,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 各地图块和开放地图的在场角色（不含玩家）
fn each(wcm: &WorldChrMan, mut f: impl FnMut(&mut ChrIns)) {
    for s in wcm.chr_sets.iter().flatten() {
        s.characters().for_each(&mut f);
    }
    wcm.open_field_chr_set.base.characters().for_each(&mut f);
}

fn scan(wcm: &WorldChrMan, d: &Def, my_team: u8, st: &mut St) {
    let mut seen = HashSet::new();
    let res = d.res.iter().find(|&&(f, _)| crate::gear::flag_get(f) == Some(true)).map(|&(_, sp)| sp);
    each(wcm, |c| {
        if !d.res.is_empty() && !FRIENDLY_TEAMS.contains(&c.team_type) && c.team_type != my_team && c.modules.data.hp > 0 {
            for &(_, sp) in &d.res {
                let has = c.special_effect.entries().any(|e| e.param_id == sp);
                if Some(sp) == res && !has {
                    c.apply_speffect(sp, false);
                    st.res += 1;
                    if st.logged < LOG_EACH {
                        st.logged += 1;
                        log(&format!("高难度异常抗性：NPC {}（实体 {}）挂 {sp}", c.npc_param_id, c.event_entity_id));
                    }
                } else if Some(sp) != res && has {
                    c.remove_speffect(sp);
                }
            }
        }
        let hp_sp = d.ent.get(&c.event_entity_id).or_else(|| d.npc.get(&c.npc_param_id)).copied();
        let atk_sp = d.aent.get(&c.event_entity_id).or_else(|| d.anpc.get(&c.npc_param_id)).copied();
        let rune_sp = d.rent.get(&c.event_entity_id).or_else(|| d.rnpc.get(&c.npc_param_id)).copied();
        if hp_sp.is_none() && atk_sp.is_none() && rune_sp.is_none() {
            return;
        }
        let (hp, max) = (c.modules.data.hp, c.modules.data.max_hp);
        if hp <= 0 || max <= 0 {
            return;
        }
        let addr = c as *mut ChrIns as usize;
        seen.insert(addr);
        if let Some(sp) = atk_sp.filter(|&sp| !c.special_effect.entries().any(|e| e.param_id == sp)) {
            c.apply_speffect(sp, false);
            st.atk += 1;
            if st.logged < LOG_EACH {
                st.logged += 1;
                log(&format!("高难度攻击力补正：NPC {}（实体 {}）挂 {sp}", c.npc_param_id, c.event_entity_id));
            }
        }
        if let Some(sp) = rune_sp.filter(|&sp| !c.special_effect.entries().any(|e| e.param_id == sp)) {
            c.apply_speffect(sp, false);
            st.rune += 1;
            if st.logged < LOG_EACH {
                st.logged += 1;
                log(&format!("高难度卢恩补正：NPC {}（实体 {}）挂 {sp}", c.npc_param_id, c.event_entity_id));
            }
        }
        let Some(sp) = hp_sp else { return };
        if !c.special_effect.entries().any(|e| e.param_id == sp) {
            st.watch.insert(addr, Watch { hp, max });
            c.apply_speffect(sp, false);
            st.applied += 1;
            if st.logged < LOG_EACH {
                st.logged += 1;
                log(&format!("高难度血量补正：NPC {}（实体 {}）挂 {sp}，挂之前血 {hp} / {max}", c.npc_param_id, c.event_entity_id));
            }
            return;
        }
        let Some(w) = st.watch.get(&addr) else { return };
        if hp != w.hp {
            st.watch.remove(&addr); // 游戏自己按比例补了，或者已经挨打
        } else if max != w.max {
            let want = ((w.hp as f64 / w.max as f64) * max as f64).round() as i32;
            c.modules.data.hp = want.clamp(1, max);
            st.fixed += 1;
            if st.logged < LOG_EACH {
                st.logged += 1;
                log(&format!("高难度血量补正：NPC {}（实体 {}）上限 {} → {max}，血量停在 {hp}，按比例补到 {}",
                             c.npc_param_id, c.event_entity_id, w.max, c.modules.data.hp));
            }
            st.watch.remove(&addr);
        }
    });
    st.watch.retain(|a, _| seen.contains(a));
}

/// 改 Boss 击败奖励（进这几档时一次，记下原来的）；改回（切出时）。返回改了几处
fn set_areas(d: &Def, st: &mut St, on: bool) -> usize {
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return 0 };
    if on {
        if !st.area_orig.is_empty() {
            return 0;
        }
        for &(r, a, b) in &d.area {
            if let Some(g) = repo.get_mut::<GameAreaParam>(r) {
                st.area_orig.push((r, g.bonus_soul_single(), g.bonus_soul_multi()));
                g.set_bonus_soul_single(a);
                g.set_bonus_soul_multi(b);
            }
        }
        st.area_orig.len()
    } else {
        let n = st.area_orig.len();
        for (r, a, b) in st.area_orig.drain(..) {
            if let Some(g) = repo.get_mut::<GameAreaParam>(r) {
                g.set_bonus_soul_single(a);
                g.set_bonus_soul_multi(b);
            }
        }
        n
    }
}

/// 掉落表一行的字节（游戏里参数行就是文件里那 152 个字节）
fn lot_bytes(repo: &mut SoloParamRepository, id: u32) -> Option<&'static mut [u8]> {
    let row = repo.get_mut::<ItemLotParam_enemy>(id)?;
    let n = std::mem::size_of::<ITEMLOT_PARAM_ST>();
    if n < LOT_SPANS[1].1 {
        return None;
    }
    Some(unsafe { std::slice::from_raw_parts_mut(row as *mut ITEMLOT_PARAM_ST as *mut u8, n) })
}

/// 掉落统一：进这几档时把目标行的道具格抄到每张复制表接上的行（记下原来的），切出时改回。返回改了几行
fn set_drops(d: &Def, st: &mut St, on: bool) -> usize {
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return 0 };
    if on {
        if !st.drop_orig.is_empty() {
            return 0;
        }
        // 目标行先读出来（两组，各几行）
        let mut tgt: [Vec<Vec<u8>>; 2] = [Vec::new(), Vec::new()];
        for k in 0..2 {
            let (first, n) = d.drop_tgt[k];
            for i in 0..n {
                let Some(b) = lot_bytes(repo, first + i) else { break };
                tgt[k].push(LOT_SPANS.iter().flat_map(|&(a, z)| b[a..z].to_vec()).collect());
            }
        }
        for &(k, first, n) in &d.drop_copy {
            if tgt[k].len() != n as usize {
                continue;
            }
            for i in 0..n {
                let Some(b) = lot_bytes(repo, first + i) else { continue };
                st.drop_orig.push((first + i, LOT_SPANS.iter().flat_map(|&(a, z)| b[a..z].to_vec()).collect()));
                let src = &tgt[k][i as usize];
                let mut o = 0;
                for &(a, z) in &LOT_SPANS {
                    b[a..z].copy_from_slice(&src[o..o + (z - a)]);
                    o += z - a;
                }
            }
        }
        st.drop_orig.len()
    } else {
        let n = st.drop_orig.len();
        for (id, old) in st.drop_orig.drain(..) {
            let Some(b) = lot_bytes(repo, id) else { continue };
            let mut o = 0;
            for &(a, z) in &LOT_SPANS {
                b[a..z].copy_from_slice(&old[o..o + (z - a)]);
                o += z - a;
            }
        }
        n
    }
}

fn remove_all(wcm: &WorldChrMan, d: &Def) -> u32 {
    let mut n = 0;
    each(wcm, |c| {
        let mine: Vec<i32> = c.special_effect.entries().map(|e| e.param_id).filter(|&sp| d.owns(sp)).collect();
        for sp in mine {
            c.remove_speffect(sp);
            n += 1;
        }
    });
    n
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St {
        next: now,
        on: false,
        off_since: None,
        watch: HashMap::new(),
        applied: 0,
        fixed: 0,
        atk: 0,
        rune: 0,
        res: 0,
        area_orig: Vec::new(),
        drop_orig: Vec::new(),
        logged: 0,
        told: (0, 0),
        told_at: now,
    });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(player) = wcm.main_player.as_ref() else {
        st.watch.clear();
        return;
    };
    let my_team = player.chr_ins.team_type;
    let on = d.flags.iter().any(|&f| crate::gear::flag_get(f) == Some(true));
    if on {
        st.off_since = None;
        if !st.on {
            st.on = true;
            log("高难度血量补正：在「死亡」/「不可能」里，开始给在场的敌人挂最大血量倍率");
        }
        if params_ok(d) {
            if st.area_orig.is_empty() && !d.area.is_empty() {
                let n = set_areas(d, st, true);
                if n > 0 {
                    log(&format!("高难度卢恩补正：{n} 处 Boss 击败奖励改成补正后的"));
                }
            }
            if st.drop_orig.is_empty() && !d.drop_copy.is_empty() {
                let n = set_drops(d, st, true);
                if n > 0 {
                    log(&format!("高难度掉落统一：{} 张复制表的 {n} 行换成 DLC 最后一档的", d.drop_copy.len()));
                }
            }
            scan(wcm, d, my_team, st);
        }
        if (st.applied + st.atk + st.res, st.fixed) != st.told && now - st.told_at >= Duration::from_secs(60) {
            st.told = (st.applied + st.atk + st.res, st.fixed);
            st.told_at = now;
            log(&format!("高难度血量补正：累计挂了 {} 次（攻击力 {} 次、卢恩 {} 次、异常抗性 {} 次），补血量 {} 次", st.applied, st.atk, st.rune, st.res, st.fixed));
        }
    } else if st.on {
        let t = *st.off_since.get_or_insert(now);
        if now - t >= OFF_GRACE {
            st.on = false;
            st.off_since = None;
            st.watch.clear();
            let n = remove_all(wcm, d);
            let a = set_areas(d, st, false);
            let l = set_drops(d, st, false);
            log(&format!("高难度血量补正：离开这几档，摘掉在场敌人身上的 {n} 个，Boss 击败奖励改回 {a} 处，掉落表改回 {l} 行"));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 定义文件：标记、范围、实体 / 敌人参数；范围外的效果、看不懂的行跳过；没有标记或一条都没有就不工作
    #[test]
    fn parse_def() {
        let d = parse("\u{feff}# 头\nflag 9956\nflag 9957\nrange 7302000 204\ne 10000800 7302080\nn 43000010 7302100\ne 1 9999\nx y\n").unwrap();
        assert_eq!(d.flags, vec![9956, 9957]);
        assert_eq!((d.base, d.n), (7302000, 204));
        assert_eq!(d.ent, HashMap::from([(10000800, 7302080)]));
        assert_eq!(d.npc, HashMap::from([(43000010, 7302100)]));
        assert!(d.owns(7302000) && d.owns(7302203) && !d.owns(7302204));
        assert!(parse("range 7302000 204\ne 1 7302001\n").is_none());
        // 攻击力那组：范围内的才要，范围外的跳过；只有攻击力也能工作
        let a = parse("flag 9956\nrange 7302000 204\narange 7302300 61\nae 10000800 7302340\nan 43000010 7302310\nan 2 7302999\n").unwrap();
        assert_eq!((a.abase, a.an, a.aent.get(&10000800), a.anpc.get(&43000010), a.anpc.get(&2)), (7302300, 61, Some(&7302340), Some(&7302310), None));
        assert!(a.owns(7302300) && a.owns(7302360) && !a.owns(7302361));
        assert!(parse("flag 9956\nrange 7302000 204\n").is_none());
        // 卢恩那组（同攻击力）+ Boss 击败奖励；只有卢恩也能工作
        let r = parse("flag 9956\nrange 7302000 204\nrrange 7302400 180\nre 10000800 7302450\nrn 43000010 7302401\nrn 3 7303000\narea 10000800 282000 300000\narea x 1 2\n").unwrap();
        assert_eq!((r.rent.get(&10000800), r.rnpc.get(&43000010), r.rnpc.get(&3)), (Some(&7302450), Some(&7302401), None));
        assert_eq!(r.area, vec![(10000800, 282000, 300000)]);
        assert!(r.owns(7302400) && r.owns(7302579) && !r.owns(7302580));
        assert!(parse("flag 9956\nrange 7302000 204\narea 10000800 282000 300000\n").is_some());
        // 异常抗性：档位标记 → 效果；只有它也能工作，算这组效果（切出时摘）
        let sr = parse("flag 9956\nrange 7302000 204\nsr 9956 7302806\nsr 9957 7302807\nsr x 1\n").unwrap();
        assert_eq!(sr.res, vec![(9956, 7302806), (9957, 7302807)]);
        assert!(sr.owns(7302806) && sr.owns(7302807) && !sr.owns(7302808));
        // 掉落统一：目标行数对不上的复制表丢掉；没有目标的不改
        let dr = parse("flag 9956\nrange 7302000 204\ndroptgt 0 1950900000 7\ndroptgt 1 1950900010 13\n\
                        dropcopy 0 1950000003 7\ndropcopy 1 1950000013 13\ndropcopy 0 1950000023 6\ndropcopy 2 1 7\n").unwrap();
        assert_eq!(dr.drop_tgt, [(1950900000, 7), (1950900010, 13)]);
        assert_eq!(dr.drop_copy, vec![(0, 1950000003, 7), (1, 1950000013, 13)]);
        assert!(parse("flag 9956\nrange 7302000 204\ndropcopy 0 1950000003 7\n").is_none(), "没有目标就什么都不改");
    }
}
