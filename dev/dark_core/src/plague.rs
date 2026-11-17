//! 词条「疫病」dr_pestilence 的敌人一侧（2026-11-06 用户「疫病也应该是词条啊 以后也没有固定护符」，以前是固定护符；词条本身在词条库，参数侧见重随的 rr/plague.py；用户 2026-11-04「让所有敌人都能中毒和腐败，参考法魂」，同日「改为不免疫所有异常
//! 同时增加所有异常的抗性 传说无负面」扩到七种：中毒、腐败、出血、冻伤、睡眠、发狂、咒死，种数和顺序照 plague.txt 的 status 行）：
//! 戴着时（玩家身上有护符的标记效果）所有敌人都会陷入这些异常，摘下恢复。分稀有度（用户 2026-11-04）：普通 / 稀有 / 史诗 / 传说
//! 四件，各有一个标记；戴着低稀有度的，所有敌人的这几种异常抗性再 +raise%（默认 30 / 20 / 10 / 0）。
//! - 每 0.5 秒扫一遍游戏的 ChrSet（各地图块 + 开放地图，同 hpunify.rs）：只在戴着时扫（没戴什么都不做）。
//!   敌对的、活着的敌人，每种异常各挂一行抗性倍率效果（第 k 行 = 抗性 × k%）：
//!   plague.txt 里有它的敌人参数、那一项要摘免疫的：摘掉「XX无效」效果（90000 中毒 / 90010 腐败 / 90020 出血 / 90040 冻伤 / 90060 发狂 /
//!   90030 咒死 / 90300 睡眠；免疫效果写 -1 的那种只靠抗性 999），挂「降到的比例 × (1 + raise%)」；
//!   不免疫的挂「100 + raise」（传说 raise 0，不挂）。游戏又把免疫效果挂回来（读图、换阶段）就再摘一次；这组效果已经挂着就不重复挂。
//! - 摘下护符（标记连续 1 秒没有，读档时可能闪一下）或换了别的稀有度：在场的角色身上有这组效果的，摘掉它们，
//!   参数里本来挂着免疫效果的挂回去，一次（换稀有度的下一轮按新的挂）。重新读图的敌人照参数重新生成。
//! - 反复发作抗性不再上涨（用户 2026-11-06）：戴着时把游戏内存里的 ResistCorrectParam 整张表改成「不加不乘」，摘下还原。
//!   游戏的做法（2.7.1.0 逆向）：发作时 0x43de00 把这项的次数（抗性模块 +0x64，最多 5）加一，0x43ef70 再按敌人参数的 resistCorrectId_*
//!   现查一行，上限（+0x2C）= 基础 × 第 n 次的 add_rate + 第 n 次的 add_point。这张表只有这一处读、每次发作现读，改了下一次发作就生效，
//!   不用 hook，也不用逐个敌人改。次数照常累积：戴上前涨过的，下一次发作回到基础值；摘下后下一次发作按累积的次数涨。
//!   玩家没有敌人参数，不走这段；友方 NPC、骨灰也用这张表，一起不涨（它们很少中异常，不单独区分）。
//! - 只在重随启动时工作（游戏里的参数没有这组效果就不挂）。
//! - 看不见的辅助角色（模型 c1000，地图事件、Boss 放招用的，原版七种全免疫）不管（2026-11-17 日志里它们也被摘了免疫）。
//! - 挂上的抗性倍率没多久又没了的（2026-11-17 联机重进会话后一分钟重挂了近 10 万次）：等 RETRY 再挂，前 LOST_LOG 次逐个记是谁。

use std::collections::HashMap;
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{ChrIns, ChrInsExt, ResistCorrectParam, SoloParamRepository, SpEffectParam, WorldChrMan};
use eldenring::param::RESIST_CORRECT_PARAM_ST;
use fromsoftware_shared::FromStatic;

use crate::rules::FRIENDLY_TEAMS;
use crate::{dir, log};

/// 多久扫一遍
const SCAN: Duration = Duration::from_millis(500);
/// 标记没有多久才算摘下（读档时可能闪一下）
const OFF_GRACE: Duration = Duration::from_secs(1);
/// 前这么多次逐个写日志（游戏里核对用），之后每分钟写一次累计
const LOG_EACH: u32 = 30;
/// 各异常的名字（plague.txt status 行的顺序，同 rr/plague.py 的 STATUS）
const ZH: [&str; 7] = ["中毒", "腐败", "出血", "冻伤", "睡眠", "发狂", "咒死"];
const RAR_ZH: [&str; 4] = ["普通", "稀有", "史诗", "传说"];
/// 不管的模型：c1000（看不见的辅助角色）
const SKIP_MODELS: [u32; 1] = [1000];
/// 挂上的抗性倍率又没了：从发现没了起等这么久再挂；挂上超过这么久才没的（读图、换阶段）当场再挂
const RETRY: Duration = Duration::from_secs(5);
/// 挂上不到 RETRY 就没了的，前这么多次逐个写日志
const LOST_LOG: u32 = 20;
/// 记挂过的角色超过这么多条就清掉重记（角色换了一批，旧地址的记录没用了）
const PUT_MAX: usize = 60_000;

#[derive(Debug, Default, PartialEq)]
struct Def {
    /// 各稀有度的标记效果、敌人抗性加多少 %
    marks: Vec<i32>,
    raise: Vec<i32>,
    /// 各异常：免疫效果（-1 = 没有）、抗性倍率效果起点、行数（第 k 行 = 起点 + k - 1，抗性 × k%）
    imm: Vec<i32>,
    base: Vec<i32>,
    steps: Vec<i32>,
    /// 敌人参数 → (各异常降到第几行；0 = 不免疫), 位（第 j 位 = 参数里挂着第 j 种的免疫效果）
    npc: HashMap<i32, (Vec<i32>, u8)>,
}

impl Def {
    fn ours(&self, j: usize, sp: i32) -> bool {
        (self.base[j]..self.base[j] + self.steps[j]).contains(&sp)
    }

    /// 戴着第 tier 件时这一项挂第几行（0 = 不挂）：免疫的降到的比例 × (1 + raise%)，不免疫的 100 + raise
    fn row_for(&self, k: i32, tier: usize) -> i32 {
        let raise = self.raise.get(tier).copied().unwrap_or(0);
        let want = if k > 0 { k } else { 100 };
        let row = ((want * (100 + raise)) as f64 / 100.0).round() as i32;
        if k == 0 && row == 100 { 0 } else { row.clamp(1, self.steps.iter().copied().min().unwrap_or(1)) }
    }

    fn n(&self) -> usize {
        self.imm.len()
    }
}

/// 第 j 种的名字
fn zh(j: usize) -> &'static str {
    ZH.get(j).copied().unwrap_or("异常")
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();
static PARAMS_OK: OnceLock<bool> = OnceLock::new();

fn nums<T: std::str::FromStr>(xs: &[&str]) -> Vec<T> {
    xs.iter().filter_map(|x| x.parse().ok()).collect()
}

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    let mut rows: Vec<Vec<i32>> = Vec::new();
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}').trim();
        let f: Vec<&str> = l.split_whitespace().collect();
        match f.as_slice() {
            ["mark", xs @ ..] => d.marks = nums(xs),
            ["raise", xs @ ..] => d.raise = nums(xs),
            ["status", j, imm, base, n] => {
                if let (Ok(j), Ok(imm), Ok(base), Ok(n)) = (j.parse::<usize>(), imm.parse(), base.parse(), n.parse()) {
                    if j < 8 {
                        if d.imm.len() <= j {
                            d.imm.resize(j + 1, -1);
                            d.base.resize(j + 1, 0);
                            d.steps.resize(j + 1, 0);
                        }
                        (d.imm[j], d.base[j], d.steps[j]) = (imm, base, n);
                    }
                }
            }
            // n 敌人参数 各异常第几行… 位（种数照 status 行，最后再对）
            ["n", xs @ ..] if xs.len() >= 3 => {
                let v: Vec<i32> = nums(xs);
                if v.len() == xs.len() {
                    rows.push(v);
                }
            }
            _ => {}
        }
    }
    d.marks.retain(|&m| m > 0);
    let n = d.n();
    for v in rows {
        if v.len() != n + 2 {
            continue;
        }
        let ks = v[1..=n].to_vec();
        if (0..n).all(|j| (0..=d.steps[j]).contains(&ks[j])) && ks.iter().any(|&x| x > 0) {
            d.npc.insert(v[0], (ks, v[n + 1].clamp(0, 255) as u8));
        }
    }
    (!d.marks.is_empty() && n > 0 && d.steps.iter().all(|&s| s > 0)).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("plague.txt")).unwrap_or_default())).as_ref()
}

/// 游戏里的参数是不是重随改过的（标记和两组效果的头尾都在）：不重随的模式启动时 plague.txt 还是上次重随留下的
fn params_ok(d: &Def) -> bool {
    *PARAMS_OK.get_or_init(|| {
        let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return false };
        let has = |sp: i32| repo.get::<SpEffectParam>(sp as u32).is_some();
        let ok = d.marks.iter().all(|&m| has(m)) && (0..d.n()).all(|j| has(d.base[j]) && has(d.base[j] + d.steps[j] - 1));
        if !ok {
            log("疫病护符：游戏里的参数没有这组效果（大概是用不重随的模式启动的），这次不管");
        }
        ok
    })
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("疫病护符（{} 个稀有度，{} 种异常，敌人抗性 +{:?}%，{} 个敌人参数要摘免疫）", d.marks.len(), d.n(), d.raise, d.npc.len()),
        None => "疫病护符（没有 plague.txt，不管）".into(),
    }
}

struct St {
    next: Instant,
    /// 正在按第几件挂（None = 没戴）
    on: Option<usize>,
    off_since: Option<Instant>,
    /// 摘免疫 / 挂抗性倍率的次数
    stripped: u64,
    cut: u64,
    logged: u32,
    told: u64,
    told_at: Instant,
    /// 抗性上涨表改之前的原值（行编号 → 值；空 = 没改）
    growth: HashMap<u32, [f32; 10]>,
    /// 挂过抗性倍率的：(角色地址, 第几种) → (什么时候挂的, 什么时候发现没了)
    put: HashMap<(usize, u8), (Instant, Option<Instant>)>,
    /// 挂上不到 RETRY 就没了的次数、等着没挂的轮数、写过几行
    lost: u64,
    waited: u64,
    lost_logged: u32,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 抗性上涨表「不加不乘」的一行：五个 add_point 全 0、五个 add_rate 全 1
const NO_GROWTH: [f32; 10] = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0];

fn growth_row(r: &RESIST_CORRECT_PARAM_ST) -> [f32; 10] {
    [r.add_point1(), r.add_point2(), r.add_point3(), r.add_point4(), r.add_point5(),
     r.add_rate1(), r.add_rate2(), r.add_rate3(), r.add_rate4(), r.add_rate5()]
}

fn set_growth_row(r: &mut RESIST_CORRECT_PARAM_ST, v: &[f32; 10]) {
    r.set_add_point1(v[0]);
    r.set_add_point2(v[1]);
    r.set_add_point3(v[2]);
    r.set_add_point4(v[3]);
    r.set_add_point5(v[4]);
    r.set_add_rate1(v[5]);
    r.set_add_rate2(v[6]);
    r.set_add_rate3(v[7]);
    r.set_add_rate4(v[8]);
    r.set_add_rate5(v[9]);
}

/// 戴着时每轮调一次：还没改的行记下原值、改成不加不乘。每轮都看，游戏重新载入过参数也能补回来；原本就不涨的行不用记
fn freeze_growth(st: &mut St) {
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    let mut n = 0;
    for (id, r) in repo.rows_mut::<ResistCorrectParam>() {
        let v = growth_row(r);
        if v != NO_GROWTH {
            st.growth.insert(id, v);
            set_growth_row(r, &NO_GROWTH);
            n += 1;
        }
    }
    if n > 0 {
        log(&format!("疫病护符：抗性上涨表 {n} 行改成不加不乘，敌人反复发作抗性不再上涨"));
    }
}

/// 摘下：还原抗性上涨表
fn thaw_growth(st: &mut St) {
    if st.growth.is_empty() {
        return;
    }
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    for (id, r) in repo.rows_mut::<ResistCorrectParam>() {
        if let Some(v) = st.growth.get(&id) {
            set_growth_row(r, v);
        }
    }
    log(&format!("疫病护符：抗性上涨表还原 {} 行", st.growth.len()));
    st.growth.clear();
}

/// 各地图块和开放地图的在场角色（不含玩家）
fn each(wcm: &WorldChrMan, mut f: impl FnMut(&mut ChrIns)) {
    for s in wcm.chr_sets.iter().flatten() {
        s.characters().for_each(&mut f);
    }
    wcm.open_field_chr_set.base.characters().for_each(&mut f);
}

fn strip(wcm: &WorldChrMan, d: &Def, tier: usize, my_team: u8, st: &mut St, now: Instant) {
    if st.put.len() > PUT_MAX {
        st.put.clear();
    }
    each(wcm, |c| {
        if FRIENDLY_TEAMS.contains(&c.team_type) || c.team_type == my_team || c.modules.data.hp <= 0 || SKIP_MODELS.contains(&c.character_id) {
            return;
        }
        let none = vec![0; d.n()];
        let ks = d.npc.get(&c.npc_param_id).map_or(&none, |x| &x.0);
        let mut sps: Option<Vec<i32>> = None;
        for j in 0..d.n() {
            let row = d.row_for(ks[j], tier);
            if row == 0 {
                continue;
            }
            let sps = sps.get_or_insert_with(|| c.special_effect.entries().map(|e| e.param_id).collect());
            let imm = ks[j] > 0 && d.imm[j] > 0 && sps.contains(&d.imm[j]);
            if imm {
                c.remove_speffect(d.imm[j]);
                st.stripped += 1;
            }
            let mut fresh = !sps.iter().any(|&sp| d.ours(j, sp));
            let key = (c as *const ChrIns as usize, j as u8);
            if fresh {
                // 挂过又没了：挂了超过 RETRY 才没的（读图、换阶段）当场再挂；没多久就没了的等 RETRY 再挂，前几次记是谁
                if let Some((put, gone)) = st.put.get_mut(&key) {
                    let since = *gone.get_or_insert_with(|| {
                        let held = now.duration_since(*put);
                        if held < RETRY {
                            st.lost += 1;
                            if st.lost_logged < LOST_LOG {
                                st.lost_logged += 1;
                                log(&format!("疫病护符：{}（模型 c{:04}，血 {} / {}）{}的抗性倍率挂上 {:.1} 秒就没了，{} 秒后再挂{}",
                                             crate::coop::describe_chr(c), c.character_id, c.modules.data.hp, c.modules.data.max_hp, zh(j),
                                             held.as_secs_f32(), RETRY.as_secs(), if st.lost_logged == LOST_LOG { "；之后只记累计" } else { "" }));
                            }
                            now
                        } else {
                            now - RETRY
                        }
                    });
                    if now.duration_since(since) < RETRY {
                        st.waited += 1;
                        fresh = false;
                    }
                }
            } else if let Some((_, gone)) = st.put.get_mut(&key) {
                // 等着的时候自己又回来了（多半是效果列表那一下没读全）：照挂着算
                *gone = None;
            }
            if fresh {
                c.apply_speffect(d.base[j] + row - 1, false);
                st.cut += 1;
                st.put.insert(key, (now, None));
            }
            if (imm || fresh) && st.logged < LOG_EACH {
                st.logged += 1;
                log(&format!("疫病护符：NPC {}（实体 {}，阵营 {}）{}{}{}", c.npc_param_id, c.event_entity_id, c.team_type, zh(j),
                             if imm { "摘掉免疫" } else { "" },
                             if fresh { format!("，抗性 × {row}%") } else { String::new() }));
            }
        }
    });
}

fn restore(wcm: &WorldChrMan, d: &Def) -> (u32, u32) {
    let (mut chrs, mut back) = (0, 0);
    each(wcm, |c| {
        let sps: Vec<i32> = c.special_effect.entries().map(|e| e.param_id).collect();
        let bits = d.npc.get(&c.npc_param_id).map(|x| x.1).unwrap_or(0);
        let mut any = false;
        for j in 0..d.n() {
            let mine: Vec<i32> = sps.iter().copied().filter(|&sp| d.ours(j, sp)).collect();
            if mine.is_empty() {
                continue;
            }
            any = true;
            for sp in mine {
                c.remove_speffect(sp);
            }
            if bits & (1 << j) != 0 && d.imm[j] > 0 && !sps.contains(&d.imm[j]) {
                c.apply_speffect(d.imm[j], false);
                back += 1;
            }
        }
        chrs += any as u32;
    });
    (chrs, back)
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St {
        next: now,
        on: None,
        off_since: None,
        stripped: 0,
        cut: 0,
        logged: 0,
        told: 0,
        told_at: now,
        growth: HashMap::new(),
        put: HashMap::new(),
        lost: 0,
        waited: 0,
        lost_logged: 0,
    });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(p) = wcm.main_player.as_ref() else { return };
    // 戴着哪一件（同一个护符组不能一起戴；万一有几个标记取稀有度最高的）
    let worn = d.marks.iter().rposition(|&m| p.chr_ins.special_effect.entries().any(|e| e.param_id == m));
    match worn {
        Some(tier) => {
            st.off_since = None;
            if !params_ok(d) {
                return;
            }
            if st.on != Some(tier) {
                st.put.clear();
                if st.on.is_some() {
                    let (n, back) = restore(wcm, d);
                    log(&format!("疫病护符：换成{}的，先恢复 {n} 个在场的敌人（挂回免疫效果 {back} 个）", RAR_ZH.get(tier).unwrap_or(&"?")));
                }
                st.on = Some(tier);
                log(&format!("疫病护符：戴上{}的（敌人{}抗性 +{}%），开始给在场的敌人摘这些异常的免疫",
                             RAR_ZH.get(tier).unwrap_or(&"?"), (0..d.n()).map(zh).collect::<Vec<_>>().join("、"),
                             d.raise.get(tier).copied().unwrap_or(0)));
            }
            freeze_growth(st);
            strip(wcm, d, tier, p.chr_ins.team_type, st, now);
            if st.stripped + st.cut != st.told && now - st.told_at >= Duration::from_secs(60) {
                st.told = st.stripped + st.cut;
                st.told_at = now;
                log(&format!("疫病护符：累计摘免疫 {} 次、挂抗性倍率 {} 次（挂上没多久又没了 {} 次，等着再挂 {} 轮）", st.stripped, st.cut, st.lost, st.waited));
            }
        }
        None if st.on.is_some() => {
            let t = *st.off_since.get_or_insert(now);
            if now - t >= OFF_GRACE {
                st.on = None;
                st.off_since = None;
                st.put.clear();
                let (n, back) = restore(wcm, d);
                log(&format!("疫病护符：摘下了，{n} 个在场的敌人恢复（挂回免疫效果 {back} 个）"));
                thaw_growth(st);
            }
        }
        None => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TXT: &str = "\u{feff}# 头\nmark 7305000 7305001 7305002 7305003\nraise 30 20 10 0\n\
                       status 0 90000 7305100 130\nstatus 1 90010 7305300 130\n\
                       n 43000010 40 100 3\nn 1 0 0 0\nn 2 131 5 1\nn 3 0 7 2\nx y\n";

    /// 定义文件：各稀有度、两组效果、敌人参数；第几行超出范围、两项都是 0 的跳过；没有标记 / 效果就不工作
    #[test]
    fn parse_def() {
        let d = parse(TXT).unwrap();
        assert_eq!((d.marks.clone(), d.raise.clone()), (vec![7305000, 7305001, 7305002, 7305003], vec![30, 20, 10, 0]));
        assert_eq!((d.imm.clone(), d.base.clone(), d.steps.clone()), (vec![90000, 90010], vec![7305100, 7305300], vec![130, 130]));
        assert_eq!(d.npc, HashMap::from([(43000010, (vec![40, 100], 3)), (3, (vec![0, 7], 2))]));
        assert!(d.ours(0, 7305100) && d.ours(0, 7305229) && !d.ours(0, 7305230) && d.ours(1, 7305300) && !d.ours(1, 7305430));
        assert!(parse("status 0 90000 7305100 130\nstatus 1 90010 7305300 130\nn 3 0 7 2\n").is_none());
        // 种数照 status 行（2026-11-04 起不固定两种）：只有一种也工作，种数对不上的 n 行跳过
        let one = parse("mark 7305000\nstatus 0 90000 7305100 130\nn 3 0 7 2\n").unwrap();
        assert_eq!((one.n(), one.npc.len()), (1, 0));
        // 没有要摘免疫的敌人参数也工作（低稀有度照样给所有敌人加抗性）
        assert!(parse("mark 7305000\nstatus 0 90000 7305100 130\nstatus 1 90010 7305300 130\n").is_some());
    }

    /// 七种异常（2026-11-04）：status 行几种，n 行就要几个数 + 位；睡眠没有免疫效果（-1）；种数对不上的 n 行跳过
    #[test]
    fn parse_seven() {
        let t = "mark 7305000 7305001 7305002 7305003\nraise 30 20 10 0\n\
                 status 0 90000 7305100 130\nstatus 1 90010 7305300 130\nstatus 2 90020 7305500 130\nstatus 3 90040 7305700 130\n\
                 status 4 -1 7305900 130\nstatus 5 90060 7306100 130\nstatus 6 90030 7306300 130\n\
                 n 10 40 0 0 0 40 0 40 97\nn 11 40 100 3\nn 12 0 0 0 0 0 0 0 0\n";
        let d = parse(t).unwrap();
        assert_eq!(d.n(), 7);
        assert_eq!(d.imm[4], -1);
        assert_eq!(d.npc, HashMap::from([(10, (vec![40, 0, 0, 0, 40, 0, 40], 97))]), "旧格式的、全 0 的跳过");
        assert!(d.ours(6, 7306300) && d.ours(6, 7306429) && !d.ours(6, 7306430));
        assert_eq!(zh(4), "睡眠");
    }

    /// 抗性上涨表的一行：读写的十个字段一一对应（写反了摘下时就还原错了）；不加不乘 = 加值全 0、倍率全 1
    #[test]
    fn growth_row_round_trip() {
        let mut r: RESIST_CORRECT_PARAM_ST = unsafe { std::mem::zeroed() };
        let v = [21.0, 49.0, 91.0, 189.0, 479.0, 1.3, 1.77, 2.44, 4.0, 8.6];
        set_growth_row(&mut r, &v);
        assert_eq!(growth_row(&r), v);
        assert_eq!((r.add_point1(), r.add_point5(), r.add_rate1(), r.add_rate5()), (21.0, 479.0, 1.3, 8.6));
        set_growth_row(&mut r, &NO_GROWTH);
        assert_eq!([r.add_point3(), r.add_rate3()], [0.0, 1.0]);
    }

    /// 挂第几行：免疫的降到的比例 × (1 + raise%)，不免疫的 100 + raise，传说不免疫的不挂；超出行数压到最后一行
    #[test]
    fn rows() {
        let d = parse(TXT).unwrap();
        assert_eq!((d.row_for(40, 0), d.row_for(40, 1), d.row_for(40, 2), d.row_for(40, 3)), (52, 48, 44, 40));
        assert_eq!((d.row_for(100, 0), d.row_for(100, 3)), (130, 100));
        assert_eq!((d.row_for(0, 0), d.row_for(0, 1), d.row_for(0, 2), d.row_for(0, 3)), (130, 120, 110, 0));
        assert_eq!(d.row_for(99, 0), 129);
        // 没有 raise 行（旧定义）当 0
        let old = parse("mark 7305000\nstatus 0 90000 7305100 130\nstatus 1 90010 7305300 130\n").unwrap();
        assert_eq!((old.row_for(0, 0), old.row_for(40, 0)), (0, 40));
    }
}
