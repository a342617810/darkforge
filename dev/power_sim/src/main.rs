//! Dark Reforged 数值模型的模拟部分：dev\power_curve\model.py 里 run_dr / vanilla_line / job_affix 的 Rust 版。
//! 读数据（regulation、地图、掉落表、词条效果）还是 Python（bundle.py 导出数据包），这里只做蒙特卡洛和评估。
//! 用法：power_sim <配置.json>（model.py 写：数据包路径、假设、难度分组、跑几次、几个线程），结果写到配置的 out：{series, affix_rank}，
//! 格式和 Python 版一样（report.py 不用改）。算法逐条照 model.py（函数名一样），只有随机数的序列不同。
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

type V5 = [f64; 5];
type V6 = [f64; 6];
type S8 = [f64; 8]; // 属性：生命力、精神、耐力、力气、灵巧、智力、信仰、感应
const BIG: f64 = 1e30; // 数据包里的无穷大
const STAT_KEYS: [&str; 8] = ["vit", "wil", "end", "str", "dex", "mag", "fai", "luc"];
const ST_STAT: [usize; 6] = [0, 0, 2, 2, 1, 1]; // 玩家异常抗性看的属性：免疫（生命力）/ 健壮（耐力）/ 理智（精神）
const UNID0: i64 = 9200;
const SMITH: [i64; 8] = [10100, 10101, 10102, 10103, 10104, 10105, 10106, 10107];
const SOMBER: [i64; 9] = [10160, 10161, 10162, 10163, 10164, 10165, 10166, 10167, 10168];

// ------------------------------------------------------------------ 数据包
#[derive(Deserialize, Clone, Debug)]
struct Eff {
    dealt: V5,
    pow: V5,
    taken: V5,
    defr: V5,
    hp: f64,
    st: S8,
    res: V6,
    flat: f64,
    pct: f64,
    pcap: f64,
    regen: f64,
    regen_pct: f64,
}

impl Eff {
    fn neutral() -> Eff {
        Eff { dealt: [1.0; 5], pow: [1.0; 5], taken: [1.0; 5], defr: [1.0; 5], hp: 1.0, st: [0.0; 8], res: [0.0; 6], flat: 0.0, pct: 0.0, pcap: BIG, regen: 0.0, regen_pct: 0.0 }
    }
    fn add(&self, b: &Eff) -> Eff {
        let m5 = |x: &V5, y: &V5| std::array::from_fn(|i| x[i] * y[i]);
        Eff {
            dealt: m5(&self.dealt, &b.dealt),
            pow: m5(&self.pow, &b.pow),
            taken: m5(&self.taken, &b.taken),
            defr: m5(&self.defr, &b.defr),
            hp: self.hp * b.hp,
            st: std::array::from_fn(|i| self.st[i] + b.st[i]),
            res: std::array::from_fn(|i| self.res[i] + b.res[i]),
            flat: self.flat + b.flat,
            pct: self.pct + b.pct,
            pcap: self.pcap.min(b.pcap),
            regen: self.regen + b.regen,
            regen_pct: self.regen_pct + b.regen_pct,
        }
    }
}

#[derive(Deserialize)]
struct Group {
    hp: Vec<f64>,
    atk: Vec<V5>,
    def: Vec<V5>,
    cut: Vec<V5>,
    res: Vec<V6>,
    rcpt: Vec<[V5; 6]>,
    rcrt: Vec<[V5; 6]>,
    sdef: Vec<V6>,
    ebu: Vec<V6>,
    eproc: Vec<[V6; 6]>,
    w: Vec<f64>,
}

#[derive(Deserialize)]
struct Ref {
    def: V5,
    cut: V5,
    atk: V5,
    hp: f64,
    #[allow(dead_code)]
    res: V6,
}

#[derive(Deserialize)]
struct BandDrops {
    t: HashMap<String, f64>,
    s: HashMap<String, f64>,
}

#[derive(Deserialize)]
struct StRec {
    bu: V6,
    proc: V6,
    corr: bool,
}

#[derive(Deserialize)]
struct Level {
    rate: V5,
    #[serde(rename = "crate")]
    crate_: V5,
    luck: f64,
    st: Vec<StRec>,
}

#[derive(Deserialize)]
struct Weapon {
    rar: i64,
    w: f64,
    req: [f64; 5],
    melee: bool,
    base: V5,
    corr: V5,
    ctype: [i64; 5],
    stc: [i64; 6],
    flags: [[bool; 5]; 5],
    res: Vec<i64>,
    levels: Vec<Level>,
}

#[derive(Deserialize)]
struct Armor {
    #[allow(dead_code)]
    slot: String,
    w: f64,
    cut: V5,
    res: V6,
    sp: Vec<i64>,
    has: bool,
}

#[derive(Deserialize)]
struct Tal {
    key: Vec<i64>,
    group: i64,
    eff: Eff,
}

#[derive(Deserialize)]
struct Graph {
    st: V5,
    gr: V5,
    ad: V5,
}

#[derive(Deserialize)]
struct Build {
    w: Vec<(String, f64)>,
    cap: HashMap<String, f64>,
    van: i64,
    van_cands: Vec<i64>,
    base: HashMap<String, f64>,
    start_lv: i64,
}

#[derive(Deserialize)]
struct PW {
    id: i64,
    cor: V5,
    req: V5,
}

#[derive(Deserialize)]
struct Pool {
    bias: usize,
    w: HashMap<String, Vec<PW>>,
    p: HashMap<String, Vec<(i64, String)>>,
    a: HashMap<String, Vec<i64>>,
}

#[derive(Deserialize)]
struct AffixRow {
    key: String,
    name: String,
    group: String,
    kind: String,
    note: String,
    #[serde(rename = "where")]
    where_: String,
    sps: [i64; 4],
}

#[derive(Deserialize)]
struct RawBundle {
    mode: String,
    enemies: Vec<Group>,
    bosses: Vec<Option<Group>>,
    #[serde(rename = "ref")]
    refs: Vec<Ref>,
    soul: Vec<f64>,
    boss_soul: Vec<f64>,
    count: Vec<f64>,
    stone_tiers: Vec<(i64, i64)>,
    drops: HashMap<String, Vec<BandDrops>>,
    mdrops: HashMap<String, Vec<Vec<(String, i64, f64, String)>>>,
    weapons: HashMap<String, Weapon>,
    armors: HashMap<String, Armor>,
    effects: HashMap<String, Option<Eff>>,
    talismans: HashMap<String, Tal>,
    graphs: HashMap<String, Option<Graph>>,
    load_graph: Graph,
    builds: HashMap<String, Build>,
    van_pieces: HashMap<String, Vec<i64>>,
    pool: Option<Pool>,
    affix: Option<Vec<AffixRow>>,
}

/// 数据包（编号键换成整数，掉落表排好序，随机数用得一样就能复现）
struct Bundle {
    mode: String,
    enemies: Vec<Group>,
    bosses: Vec<Option<Group>>,
    refs: Vec<Ref>,
    soul: Vec<f64>,
    boss_soul: Vec<f64>,
    count: Vec<f64>,
    stone_tiers: Vec<(i64, i64)>,
    /// 发现力 → 每档：护符 [(编号, 每杀件数)]、道具 [(编号, 每杀件数)]
    drops: HashMap<String, Vec<(Vec<(i64, f64)>, Vec<(i64, f64)>)>>,
    mdrops: HashMap<String, Vec<Vec<(String, i64, f64, String)>>>,
    weapons: HashMap<i64, Weapon>,
    armors: HashMap<i64, Armor>,
    effects: HashMap<i64, Option<Eff>>,
    talismans: HashMap<i64, Tal>,
    graphs: HashMap<i64, Graph>,
    load_graph: Graph,
    builds: HashMap<String, Build>,
    van_pieces: HashMap<String, Vec<i64>>,
    pool: Option<Pool>,
    affix: Option<Vec<AffixRow>>,
}

fn ikeys<T>(m: HashMap<String, T>) -> HashMap<i64, T> {
    m.into_iter().map(|(k, v)| (k.parse().expect("编号"), v)).collect()
}

fn sorted_ids(m: &HashMap<String, f64>) -> Vec<(i64, f64)> {
    let mut v: Vec<(i64, f64)> = m.iter().map(|(k, &p)| (k.parse().expect("编号"), p)).collect();
    v.sort_by_key(|x| x.0);
    v
}

fn load_bundle(path: &str) -> Bundle {
    let text = std::fs::read_to_string(path).unwrap_or_else(|e| panic!("读不了数据包 {path}：{e}"));
    let r: RawBundle = serde_json::from_str(&text).unwrap_or_else(|e| panic!("数据包 {path} 格式不对：{e}"));
    Bundle {
        mode: r.mode,
        enemies: r.enemies,
        bosses: r.bosses,
        refs: r.refs,
        soul: r.soul,
        boss_soul: r.boss_soul,
        count: r.count,
        stone_tiers: r.stone_tiers,
        drops: r.drops.into_iter().map(|(d, v)| (d, v.iter().map(|b| (sorted_ids(&b.t), sorted_ids(&b.s))).collect())).collect(),
        mdrops: r.mdrops,
        weapons: ikeys(r.weapons),
        armors: ikeys(r.armors),
        effects: ikeys(r.effects),
        talismans: ikeys(r.talismans),
        graphs: ikeys(r.graphs).into_iter().filter_map(|(k, v)| v.map(|g| (k, g))).collect(),
        load_graph: r.load_graph,
        builds: r.builds,
        van_pieces: r.van_pieces,
        pool: r.pool,
        affix: r.affix,
    }
}

// ------------------------------------------------------------------ 配置（model.py 写）
#[derive(Deserialize)]
struct Tier {
    name: String,
    enemy_hp: f64,
    enemy_damage: f64,
}

#[derive(Deserialize)]
struct GroupCfg {
    rb: f64,
    db: f64,
    tiers: Vec<Tier>,
}

#[derive(Deserialize)]
struct Assume {
    kill_ratio: f64,
    /// Boss 清除率、宝箱 / 拾取拿几成（model.py 写；mdrops 的来源 "b" / "m" 按这两个乘概率）
    #[serde(default = "one")]
    boss_ratio: f64,
    #[serde(default = "one")]
    treasure_ratio: f64,
    player_def: [f64; 2],
    vanilla_upgrade: Vec<usize>,
    dlc_blessing: Vec<f64>,
    blessing_dealt: f64,
    blessing_taken: f64,
    arcane_discovery: bool,
    load_ratio: f64,
    slot_share: Vec<(String, f64)>,
    hit_interval: f64,
    enemy_hit_interval: f64,
    status_sim_hits: usize,
    vanilla_armor_pct: f64,
    free_wishes: Vec<(usize, usize)>,
    start_armor_tiers: Vec<usize>,
    start_weapon_tier: usize,
    boss_flasks: Vec<f64>,
    flask_heal: f64,
    regen_cap: f64,
    flat_eff: f64,
}

fn one() -> f64 {
    1.0
}

impl Assume {
    fn drop_ratio(&self, src: &str) -> f64 {
        if src == "b" {
            self.boss_ratio
        } else {
            self.treasure_ratio
        }
    }
}

#[derive(Deserialize)]
struct Config {
    bundles: Vec<String>,
    out: String,
    runs: usize,
    seed: u64,
    threads: usize,
    bands: usize,
    assume: Assume,
    groups: Vec<GroupCfg>,
    build_order: Vec<String>,
    slots_v: Vec<usize>,
    slots_r: Vec<usize>,
    band_weights: Vec<[f64; 4]>,
    cat_w: [f64; 3],
    upgrade_stones: HashMap<String, Vec<i64>>,
}

// ------------------------------------------------------------------ 随机数
struct Rng([u64; 4]);

impl Rng {
    fn new(seed: u64) -> Rng {
        let mut z = seed;
        let mut sm = || {
            z = z.wrapping_add(0x9E3779B97F4A7C15);
            let mut x = z;
            x = (x ^ (x >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
            x = (x ^ (x >> 27)).wrapping_mul(0x94D049BB133111EB);
            x ^ (x >> 31)
        };
        Rng([sm(), sm(), sm(), sm()])
    }
    fn next(&mut self) -> u64 {
        let s = &mut self.0;
        let r = s[1].wrapping_mul(5).rotate_left(7).wrapping_mul(9);
        let t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = s[3].rotate_left(45);
        r
    }
    fn f(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
    fn below(&mut self, n: usize) -> usize {
        ((self.f() * n as f64) as usize).min(n - 1)
    }
    fn choose_w(&mut self, w: &[f64]) -> usize {
        let tot: f64 = w.iter().sum();
        let mut x = self.f() * tot;
        for (i, &v) in w.iter().enumerate() {
            if x < v {
                return i;
            }
            x -= v;
        }
        w.len() - 1
    }
    fn gauss(&mut self) -> f64 {
        let u1 = self.f().max(1e-300);
        let u2 = self.f();
        (-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos()
    }
    fn poisson(&mut self, lam: f64) -> u64 {
        if lam <= 0.0 {
            return 0;
        }
        if lam < 30.0 {
            let l = (-lam).exp();
            let (mut k, mut p) = (0u64, 1.0);
            loop {
                p *= self.f();
                if p <= l {
                    return k;
                }
                k += 1;
            }
        }
        (lam + lam.sqrt() * self.gauss()).round().max(0.0) as u64
    }
}

// ------------------------------------------------------------------ 公式
fn defense_mult(r: f64) -> f64 {
    if r > 8.0 {
        0.9
    } else if r > 2.5 {
        0.9 - 0.2 * ((8.0 - r) / 5.5).powi(2)
    } else if r > 1.0 {
        0.7 - 0.3 * ((2.5 - r) / 1.5).powi(2)
    } else if r > 0.125 {
        0.1 + 0.3 * ((r - 0.125) / 0.875).powi(2)
    } else {
        0.1
    }
}

fn graph_raw(g: &Graph, stat: f64) -> f64 {
    let mut val = g.gr[4];
    for k in 0..4 {
        if stat <= g.st[k + 1] {
            let mut t = if g.st[k + 1] > g.st[k] { (stat - g.st[k]) / (g.st[k + 1] - g.st[k]) } else { 1.0 };
            t = t.clamp(0.0, 1.0);
            t = if g.ad[k] > 0.0 { t.powf(g.ad[k]) } else { 1.0 - (1.0 - t).powf(-g.ad[k]) };
            val = g.gr[k] + (g.gr[k + 1] - g.gr[k]) * t;
            break;
        }
    }
    val
}

fn rune_cost(l: i64) -> f64 {
    let x = (((l + 81) - 92) as f64 * 0.02).max(0.0);
    ((x + 0.1) * ((l + 81) as f64).powi(2) + 1.0).floor()
}

fn level_from_runes(start_lv: i64, runes: f64) -> i64 {
    let (mut l, mut r) = (start_lv, runes);
    while l < 713 && r >= rune_cost(l) {
        r -= rune_cost(l);
        l += 1;
    }
    l
}

fn hp_from_vigor(v: f64) -> f64 {
    if v <= 25.0 {
        300.0 + 500.0 * ((v - 1.0) / 24.0).max(0.0).powf(1.5)
    } else if v <= 40.0 {
        800.0 + 650.0 * ((v - 25.0) / 15.0).powf(1.1)
    } else if v <= 60.0 {
        1450.0 + 450.0 * (1.0 - (1.0 - (v - 40.0) / 20.0).powf(1.2))
    } else {
        1900.0 + 200.0 * (1.0 - (1.0 - (v - 60.0).min(39.0) / 39.0).powf(1.2))
    }
}

fn allocate(b: &Build, lv: i64) -> S8 {
    let mut s: S8 = std::array::from_fn(|i| b.base.get(STAT_KEYS[i]).copied().unwrap_or(10.0));
    let idx = |k: &str| STAT_KEYS.iter().position(|x| *x == k).expect("属性");
    let mut added: HashMap<usize, f64> = HashMap::new();
    for _ in 0..(lv - b.start_lv).max(0) {
        let cand: Vec<&(String, f64)> = b.w.iter().filter(|(k, _)| s[idx(k)] < b.cap.get(k.as_str()).copied().unwrap_or(99.0)).collect();
        let cand: Vec<&(String, f64)> = if cand.is_empty() { b.w.iter().collect() } else { cand };
        let mut best: Option<(usize, f64)> = None;
        for (k, w) in cand {
            let i = idx(k);
            let v = (added.get(&i).copied().unwrap_or(0.0) + 1.0) / w;
            if best.is_none_or(|(_, bv)| v < bv) {
                best = Some((i, v));
            }
        }
        let i = best.unwrap().0;
        s[i] += 1.0;
        *added.entry(i).or_insert(0.0) += 1.0;
    }
    s
}

fn resist_base(l: f64, stat: f64) -> f64 {
    let x = l + 79.0;
    let lv = if l <= 71.0 {
        75.0 + 30.0 * (x - 1.0) / 149.0
    } else if l <= 111.0 {
        105.0 + 40.0 * (x - 150.0) / 40.0
    } else if l <= 161.0 {
        145.0 + 15.0 * (x - 190.0) / 50.0
    } else {
        160.0 + 20.0 * (x - 240.0) / 552.0
    };
    let st = if stat <= 30.0 {
        0.0
    } else if stat <= 40.0 {
        30.0 * (stat - 30.0) / 10.0
    } else if stat <= 60.0 {
        30.0 + 10.0 * (stat - 40.0) / 20.0
    } else {
        40.0 + 10.0 * (stat.min(99.0) - 60.0) / 39.0
    };
    lv + st
}

fn wmedian(v: &[f64], w: &[f64]) -> f64 {
    let mut o: Vec<usize> = (0..v.len()).collect();
    o.sort_by(|&a, &b| v[a].total_cmp(&v[b]));
    let tot: f64 = w.iter().sum();
    let mut c = 0.0;
    for &i in &o {
        c += w[i];
        if c >= tot / 2.0 {
            return v[i];
        }
    }
    v[*o.last().unwrap()]
}

fn pct(vals: &[Option<f64>], q: f64) -> Option<f64> {
    let mut v: Vec<f64> = vals.iter().filter_map(|x| *x).filter(|x| x.is_finite()).collect();
    if v.is_empty() {
        return None;
    }
    v.sort_by(|a, b| a.total_cmp(b));
    let k = (v.len() - 1) as f64 * q;
    let (lo, hi) = (k.floor() as usize, k.ceil() as usize);
    Some(v[lo] + (v[hi] - v[lo]) * (k - lo as f64))
}

fn build_weight(it: &PW, s: &[f64; 5]) -> f64 {
    let gap: f64 = (0..5).map(|k| (it.req[k] - s[k]).max(0.0)).sum();
    let put: Vec<f64> = s.iter().map(|&x| (x - 10.0).max(0.0)).collect();
    let top = put.iter().copied().fold(0.0, f64::max);
    let sc: f64 = it.cor.iter().map(|&c| c.max(0.0)).sum();
    let fit = if sc > 0.0 && top > 0.0 { (0..5).map(|k| it.cor[k].max(0.0) * put[k]).sum::<f64>() / (sc * top) } else { 0.5 };
    0.5f64.powf(gap / 4.0) * (0.1 + fit).powi(2)
}

fn dkey(d: f64) -> String {
    if d.fract() == 0.0 { format!("{}", d as i64) } else { format!("{d}") }
}

// ------------------------------------------------------------------ 一种情况的计算（带缓存）
struct Sim<'a> {
    b: &'a Bundle,
    a: &'a Assume,
    ar_cache: HashMap<(i64, usize, [i64; 5]), V5>,
    comb_cache: HashMap<Vec<i64>, Eff>,
}

/// 评估结果：每档难度 (砍几刀, 能挨几下, 战斗力指数, 不算异常时的指数)
type Ev = Vec<[f64; 4]>;

impl<'a> Sim<'a> {
    fn new(b: &'a Bundle, a: &'a Assume) -> Sim<'a> {
        Sim { b, a, ar_cache: HashMap::new(), comb_cache: HashMap::new() }
    }

    fn graph(&self, gid: i64, stat: f64) -> f64 {
        self.b.graphs.get(&gid).map_or(0.0, |g| graph_raw(g, stat) / 100.0)
    }

    fn wp(&self, wid: i64) -> &'a Weapon {
        self.b.weapons.get(&wid).unwrap_or_else(|| panic!("数据包里没有武器 {wid}"))
    }

    fn max_level(&self, wid: i64) -> usize {
        self.wp(wid).levels.len() - 1
    }

    fn usable(&self, wid: i64, s: &S8) -> bool {
        let w = self.wp(wid);
        let have = [(s[3] * 1.5).floor(), s[4], s[5], s[6], s[7]];
        w.melee && (0..5).all(|k| w.req[k] <= have[k])
    }

    fn ar(&mut self, wid: i64, lv: usize, s: &S8) -> V5 {
        let key = (wid, lv, std::array::from_fn(|i| (s[3 + i] * 1000.0).round() as i64));
        if let Some(v) = self.ar_cache.get(&key) {
            return *v;
        }
        let w = self.wp(wid);
        let l = &w.levels[lv.min(w.levels.len() - 1)];
        let stat = [s[3], s[4], s[5], s[6], s[7]];
        let mut out = [0.0; 5];
        for t in 0..5 {
            let b = w.base[t] * l.rate[t];
            if b <= 0.0 {
                continue;
            }
            let mut bonus = 0.0;
            for k in 0..5 {
                if w.flags[t][k] {
                    bonus += b * w.corr[k] * l.crate_[k] / 100.0 * self.graph(w.ctype[t], stat[k]);
                }
            }
            out[t] = b + bonus;
        }
        self.ar_cache.insert(key, out);
        out
    }

    /// 武器每一下叠的异常 (6) 和发作效果 (6×6)
    fn status(&self, wid: i64, lv: usize, luc: f64) -> (V6, [V6; 6]) {
        let w = self.wp(wid);
        let l = &w.levels[lv.min(w.levels.len() - 1)];
        let (mut bu, mut proc) = ([0.0; 6], [[0.0; 6]; 6]);
        for r in &l.st {
            for t in 0..6 {
                let mut v = r.bu[t];
                if v <= 0.0 {
                    continue;
                }
                if w.stc[t] >= 0 && l.luck > 0.0 && r.corr {
                    v *= 1.0 + l.luck / 100.0 * self.graph(w.stc[t], luc);
                }
                bu[t] += v;
                proc[t] = r.proc;
            }
        }
        (bu, proc)
    }

    fn effect(&self, sid: i64) -> Option<&'a Eff> {
        self.b.effects.get(&sid).and_then(|e| e.as_ref())
    }

    /// 几个特效合起来（逐个相加，同一个只算一次）
    fn combine(&mut self, sids: &HashSet<i64>) -> Eff {
        let mut key: Vec<i64> = sids.iter().copied().collect();
        key.sort_unstable();
        if let Some(e) = self.comb_cache.get(&key) {
            return e.clone();
        }
        let mut e = Eff::neutral();
        for s in &key {
            if let Some(x) = self.effect(*s) {
                e = e.add(x);
            }
        }
        self.comb_cache.insert(key, e.clone());
        e
    }

    fn extra_out(&self, ar_sum: f64, cut_mean: f64, hp: f64, flat: f64, pct: f64, pcap: f64) -> f64 {
        flat * self.a.flat_eff * cut_mean + (pct * hp).min(pcap * ar_sum)
    }

    fn regen_in(&self, d_in: f64, regen: f64) -> f64 {
        (d_in - regen * self.a.enemy_hit_interval).max((1.0 - self.a.regen_cap) * d_in)
    }

    /// 参考敌人上的战斗力（能挨几下 ÷ 砍几刀，不含异常）
    fn ref_score(&mut self, wid: i64, lv: usize, s: &S8, pdef: f64, cut: &V5, e: &Eff, r: &Ref) -> f64 {
        let st: S8 = std::array::from_fn(|i| s[i] + e.st[i]);
        let a0 = self.ar(wid, lv, &st);
        let ar: V5 = std::array::from_fn(|t| a0[t] * e.pow[t]);
        let mut d_out = 0.0;
        for t in 0..5 {
            d_out += ar[t] * defense_mult(ar[t] / r.def[t]) * r.cut[t] * e.dealt[t];
        }
        d_out += self.extra_out(ar.iter().sum(), r.cut.iter().sum::<f64>() / 5.0, r.hp, e.flat, e.pct, e.pcap);
        let mut d_in = 0.0;
        for t in 0..5 {
            d_in += r.atk[t] * defense_mult(r.atk[t] / (pdef * e.defr[t])) * cut[t] * e.taken[t];
        }
        let hp = hp_from_vigor(st[0]) * e.hp;
        let d_in = self.regen_in(d_in, e.regen + e.regen_pct * hp);
        hp / d_in.max(1e-6) * d_out
    }

    fn weapon_value(&mut self, wid: i64, lv: usize, s: &S8, r: &Ref) -> f64 {
        let a = self.ar(wid, lv, s);
        let d: f64 = (0..5).map(|t| a[t] * defense_mult(a[t] / r.def[t]) * r.cut[t]).sum();
        let (bu, proc) = self.status(wid, lv, s[7]);
        let dt = self.a.hit_interval;
        let mut extra = 0.0;
        for t in 0..6 {
            if bu[t] <= 0.0 || r.res[t] >= 1e29 {
                continue;
            }
            let [rate, pt, isdot, itv, dur, mult] = proc[t];
            let tick = rate / 100.0 * r.hp + pt;
            let win = if isdot > 0.0 || mult != 1.0 { dur / dt } else { 0.0 };
            let cyc = (r.res[t] / bu[t]).ceil() + win;
            extra += (if isdot > 0.0 { tick / itv * dur } else { tick }) / cyc + d * (mult - 1.0) * win / cyc;
        }
        d + extra
    }

    fn armor_effect(&mut self, pieces: &[i64]) -> (V5, Eff, HashSet<i64>, V6) {
        let (mut cut, mut res, mut sids) = ([1.0; 5], [0.0; 6], HashSet::new());
        for p in pieces {
            let a = &self.b.armors[p];
            for t in 0..5 {
                cut[t] *= a.cut[t];
            }
            for t in 0..6 {
                res[t] += a.res[t];
            }
            sids.extend(a.sp.iter().copied());
        }
        let e = self.combine(&sids);
        (cut, e, sids, res)
    }

    fn armor_gain(&mut self, wid: i64, lv: usize, s: &S8, pdef: f64, pcut: &V5, e: &Eff, r: &Ref) -> f64 {
        self.ref_score(wid, lv, s, pdef, pcut, e, r) / self.ref_score(wid, lv, s, pdef, pcut, &Eff::neutral(), r).max(1e-9)
    }

    /// 每个部位挑负重放得下的：先挑减伤最高的，再逐个部位换成让参考战斗力最高的那件（算上词条），来回两遍
    fn pick_armor(&mut self, owned: &HashMap<String, Vec<i64>>, budget: f64, wid: i64, lv: usize, s: &S8, pdef: f64, r: &Ref) -> Vec<i64> {
        let arm = &self.b.armors;
        let mut slots: Vec<(String, Vec<i64>)> = Vec::new();
        for (slot, share) in &self.a.slot_share {
            let all = owned.get(slot).map(|v| v.as_slice()).unwrap_or(&[]);
            let mut lst: Vec<i64> = all.iter().copied().filter(|p| arm[p].w <= budget * share).collect();
            if lst.is_empty() {
                let mut l2 = all.to_vec();
                l2.sort_by(|a, b| arm[a].w.total_cmp(&arm[b].w));
                lst = l2.into_iter().take(1).collect();
            }
            if lst.is_empty() {
                continue;
            }
            let mut plain: Vec<i64> = lst.iter().copied().filter(|p| !arm[p].has).collect();
            plain.sort_by(|a, b| arm[a].cut[0].total_cmp(&arm[b].cut[0]));
            plain.truncate(3);
            let mut best: Vec<(Vec<i64>, i64)> = Vec::new();
            for &p in &lst {
                if !arm[&p].has {
                    continue;
                }
                match best.iter_mut().find(|(k, _)| *k == arm[&p].sp) {
                    Some(x) => {
                        if arm[&p].cut[0] < arm[&x.1].cut[0] {
                            x.1 = p;
                        }
                    }
                    None => best.push((arm[&p].sp.clone(), p)),
                }
            }
            plain.extend(best.into_iter().map(|x| x.1));
            slots.push((slot.clone(), plain));
        }
        let mut pick: Vec<i64> = slots
            .iter()
            .map(|(_, l)| {
                let mut m = l[0];
                for &p in l {
                    if arm[&p].cut[0] < arm[&m].cut[0] {
                        m = p;
                    }
                }
                m
            })
            .collect();
        for _ in 0..2 {
            let mut moved = false;
            for si in 0..slots.len() {
                let lst = slots[si].1.clone();
                if lst.len() < 2 {
                    continue;
                }
                let (mut cut_o, mut sids_o) = ([1.0; 5], HashSet::new());
                for (j, &p) in pick.iter().enumerate() {
                    if j != si {
                        for t in 0..5 {
                            cut_o[t] *= arm[&p].cut[t];
                        }
                        sids_o.extend(arm[&p].sp.iter().copied());
                    }
                }
                let eff_o = self.combine(&sids_o);
                let mut sc = Vec::with_capacity(lst.len());
                for &p in &lst {
                    let a = &arm[&p];
                    let extra: HashSet<i64> = a.sp.iter().copied().filter(|x| !sids_o.contains(x)).collect();
                    let e = if extra.is_empty() { eff_o.clone() } else { eff_o.add(&self.combine(&extra)) };
                    let cut: V5 = std::array::from_fn(|t| cut_o[t] * a.cut[t]);
                    sc.push(self.ref_score(wid, lv, s, pdef, &cut, &e, r));
                }
                let mut j = 0;
                for (k, &v) in sc.iter().enumerate() {
                    if v > sc[j] {
                        j = k;
                    }
                }
                let cur = lst.iter().position(|&p| p == pick[si]).unwrap_or(0);
                if j != cur && sc[j] > sc[cur] * (1.0 + 1e-9) {
                    pick[si] = lst[j];
                    moved = true;
                }
            }
            if !moved {
                break;
            }
        }
        pick
    }

    /// 从拥有的护符里贪心挑 slots 件；返回 (合并后的倍率（含 base）, 戴了几件, 护符让参考指数乘了多少)
    fn pick_talismans(&mut self, owned: &[i64], slots: usize, wid: i64, lv: usize, s: &S8, pdef: f64, pcut: &V5, r: &Ref, base: &Eff, skip: &HashSet<i64>) -> (Eff, usize, f64) {
        let mut cur = base.clone();
        let mut ids: Vec<i64> = owned.to_vec();
        ids.sort_unstable();
        ids.dedup();
        let mut cands: Vec<&'a Tal> = Vec::new();
        let mut keys: Vec<&Vec<i64>> = Vec::new();
        for t in ids {
            if let Some(e) = self.b.talismans.get(&t) {
                if !keys.contains(&&e.key) && !e.key.iter().any(|x| skip.contains(x)) {
                    keys.push(&e.key);
                    cands.push(e);
                }
            }
        }
        if cands.is_empty() || slots == 0 {
            return (cur, 0, 1.0);
        }
        let s0 = self.ref_score(wid, lv, s, pdef, pcut, &cur, r);
        let mut now = s0;
        let mut chosen: Vec<&Tal> = Vec::new();
        for _ in 0..slots {
            let mut best: Option<(usize, f64)> = None;
            for (j, c) in cands.iter().enumerate() {
                if chosen.iter().any(|x| x.key == c.key || (c.group >= 0 && c.group == x.group)) {
                    continue;
                }
                let v = self.ref_score(wid, lv, s, pdef, pcut, &cur.add(&c.eff), r);
                if best.is_none_or(|(_, bv)| v > bv) {
                    best = Some((j, v));
                }
            }
            let Some((j, v)) = best else { break };
            if v <= now * (1.0 + 1e-9) {
                break;
            }
            chosen.push(cands[j]);
            cur = cur.add(&cands[j].eff);
            now = v;
        }
        let n = chosen.len();
        (cur, n, if s0 > 0.0 { now / s0 } else { 1.0 })
    }

    /// 逐击模拟一个目标「几下打死」（带小数，最少 1），照 model.py 的 sim_hits（一行）
    #[allow(clippy::too_many_arguments)]
    fn sim_one(&self, h: f64, d: f64, bu: &V6, thr0: &V6, proc: &[V6; 6], sdef: &V6, dt: f64, rc: Option<(&[V5; 6], &[V5; 6])>) -> f64 {
        let mut tick = [0.0; 6];
        let mut act = [false; 6];
        for t in 0..6 {
            tick[t] = (proc[t][0] / 100.0 * h + proc[t][1]) * sdef[t];
            act[t] = bu[t] > 0.0 && thr0[t] < 1e29 && (tick[t] > 0.0 || proc[t][5] != 1.0);
        }
        if !act.iter().any(|&x| x) {
            return (h / d.max(1e-6)).max(1.0);
        }
        let isdot: [bool; 6] = std::array::from_fn(|t| proc[t][2] > 0.0);
        let dot: V6 = std::array::from_fn(|t| if isdot[t] { tick[t] / if proc[t][3] > 0.0 { proc[t][3] } else { 1.0 } * dt } else { 0.0 });
        let (mut thr, mut meter, mut until, mut k) = (*thr0, [0.0; 6], [-1.0; 6], [0usize; 6]);
        let (mut left, mut last) = (h, 0.0);
        let cap = self.a.status_sim_hits;
        for i in 1..=cap {
            let t = i as f64 * dt;
            let on: [bool; 6] = std::array::from_fn(|j| until[j] > t);
            let mut mult = 1.0;
            let mut dots = 0.0;
            for j in 0..6 {
                if on[j] {
                    mult *= proc[j][5];
                    dots += dot[j];
                }
            }
            let mut dmg = d * mult + dots;
            for j in 0..6 {
                if act[j] && !on[j] {
                    meter[j] += bu[j];
                    if meter[j] >= thr[j] {
                        if !isdot[j] {
                            dmg += tick[j];
                        }
                        until[j] = t + proc[j][4];
                        meter[j] = 0.0;
                        if let Some((rp, rr)) = rc {
                            k[j] = (k[j] + 1).min(5);
                            let kk = k[j].saturating_sub(1);
                            thr[j] = thr0[j] * rr[j][kk] + rp[j][kk];
                        }
                    }
                }
            }
            let new = left - dmg;
            if new <= 0.0 {
                return ((i - 1) as f64 + left / dmg).max(1.0);
            }
            left = new;
            if i + 20 > cap {
                last += dmg;
            }
        }
        (cap as f64 + left / (last / 20.0).max(1e-6)).max(1.0)
    }

    /// 这一档的普通敌人（boss = false）或 Boss：每档难度一组 (砍几刀, 能挨几下, 指数, 不算异常时的指数)（按个数加权的中位数）
    #[allow(clippy::too_many_arguments)]
    fn evaluate(&self, band: usize, ar: &V5, php: f64, pdef: &V5, pcut: &V5, dealt: &V5, taken: f64, wst: &(V6, [V6; 6]), pres: &V6, tiers: &[(f64, f64)], e_x: &Eff, regen: f64, boss: bool) -> Option<Ev> {
        let (g, php) = if boss {
            let g = self.b.bosses.get(band)?.as_ref()?;
            let f = self.a.boss_flasks[band.min(self.a.boss_flasks.len() - 1)];
            (g, php * (1.0 + f * self.a.flask_heal))
        } else {
            (&self.b.enemies[band], php)
        };
        let n = g.hp.len();
        let ar_sum: f64 = ar.iter().sum();
        let mut d_out = vec![0.0; n];
        let mut d_in = vec![0.0; n];
        for u in 0..n {
            let mut o = 0.0;
            let mut i = 0.0;
            for t in 0..5 {
                o += ar[t] * defense_mult(ar[t] / g.def[u][t]) * g.cut[u][t] * dealt[t];
                i += g.atk[u][t] * defense_mult(g.atk[u][t] / pdef[t]) * pcut[t] * taken;
            }
            d_out[u] = o + self.extra_out(ar_sum, g.cut[u].iter().sum::<f64>() / 5.0, g.hp[u], e_x.flat, e_x.pct, e_x.pcap);
            d_in[u] = self.regen_in(i, regen);
        }
        let mut out = Vec::with_capacity(tiers.len());
        let (mut h2k, mut h2d, mut idx, mut sx) = (vec![0.0; n], vec![0.0; n], vec![0.0; n], vec![0.0; n]);
        for &(hm, dm) in tiers {
            for u in 0..n {
                let dk = d_out[u] / hm;
                let dd = d_in[u] * dm;
                h2k[u] = self.sim_one(g.hp[u], dk, &wst.0, &g.res[u], &wst.1, &g.sdef[u], self.a.hit_interval, Some((&g.rcpt[u], &g.rcrt[u])));
                h2d[u] = self.sim_one(php, dd, &g.ebu[u], pres, &g.eproc[u], &[1.0; 6], self.a.enemy_hit_interval, None);
                idx[u] = h2d[u] / h2k[u];
                let k0 = (g.hp[u] / dk.max(1e-6)).max(1.0);
                let d0 = (php / dd.max(1e-6)).max(1.0);
                sx[u] = d0 / k0;
            }
            out.push([wmedian(&h2k, &g.w), wmedian(&h2d, &g.w), wmedian(&idx, &g.w), wmedian(&sx, &g.w)]);
        }
        Some(out)
    }

    /// 在防具词条之上挑护符，再算这一档的普通敌人和 Boss：(普通敌人, 戴了几件, 护符倍数, Boss)
    #[allow(clippy::too_many_arguments)]
    fn tal_eval(&mut self, band: usize, owned_t: &[i64], slots: usize, wid: i64, lv: usize, s: &S8, lvl: f64, pdef: f64, pcut: &V5, a_eff: &Eff, a_sids: &HashSet<i64>, a_res: &V6, dealt: f64, taken: f64, tiers: &[(f64, f64)]) -> (Ev, usize, f64, Option<Ev>) {
        let r = &self.b.refs[band];
        let (eff, n, gain) = self.pick_talismans(owned_t, slots, wid, lv, s, pdef, pcut, r, a_eff, a_sids);
        let s2: S8 = std::array::from_fn(|i| s[i] + eff.st[i]);
        let a0 = self.ar(wid, lv, &s2);
        let a: V5 = std::array::from_fn(|t| a0[t] * eff.pow[t]);
        let php = hp_from_vigor(s2[0]) * eff.hp;
        let pres: V6 = std::array::from_fn(|k| resist_base(lvl, s2[ST_STAT[k]]) + a_res[k] + eff.res[k]);
        let pdef5: V5 = std::array::from_fn(|t| pdef * eff.defr[t]);
        let pcut5: V5 = std::array::from_fn(|t| pcut[t] * eff.taken[t]);
        let dealt5: V5 = std::array::from_fn(|t| dealt * eff.dealt[t]);
        let wst = self.status(wid, lv, s2[7]);
        let mut ex = eff.clone();
        ex.flat *= dealt;
        let regen = eff.regen + eff.regen_pct * php;
        let ev = self.evaluate(band, &a, php, &pdef5, &pcut5, &dealt5, taken, &wst, &pres, tiers, &ex, regen, false).expect("这一档没有普通敌人");
        let evb = self.evaluate(band, &a, php, &pdef5, &pcut5, &dealt5, taken, &wst, &pres, tiers, &ex, regen, true);
        (ev, n, gain, evb)
    }

    fn max_load(&self, end: f64) -> f64 {
        graph_raw(&self.b.load_graph, end)
    }

    fn stone_tier(&self, sid: i64, band: usize) -> i64 {
        let st = &self.b.stone_tiers;
        if st.is_empty() || band >= st.len() {
            return sid;
        }
        let (lo, hi) = st[band];
        for seq in [&SMITH[..], &SOMBER[..]] {
            if let Some(i) = seq.iter().position(|&x| x == sid) {
                let lv = ((i as i64 + 1).max(lo)).min(hi).min(seq.len() as i64);
                return seq[(lv - 1) as usize];
            }
        }
        sid
    }

    fn cumulative(&self, bands: usize, c: f64, bonus: f64) -> Vec<f64> {
        let mut out = Vec::new();
        let mut acc = 0.0;
        for b in 0..bands {
            let x = c * self.b.soul[b] + self.a.boss_ratio * self.b.boss_soul[b];
            out.push((acc + x / 2.0) * (1.0 + bonus));
            acc += x;
        }
        out
    }
}

// ------------------------------------------------------------------ 一次推图（DR）
/// 一档的记录：(普通敌人, 攻击力合计, 强化, 稀有度, 血量, 物理减伤, 护符件数, 护符倍数, 防具和武器词条倍数, 带不带异常, Boss)
struct Rec {
    ev: Ev,
    ar: f64,
    lv: f64,
    rar: f64,
    hp: f64,
    neg: f64,
    tal: f64,
    talx: f64,
    armx: f64,
    stw: f64,
    evb: Option<Ev>,
    /// 各稀有度（0~3）：手上能用的武器件数、用手上的石头能强化到几级
    own_ok: [f64; 4],
    lv_r: [f64; 4],
}

struct Owned {
    w: Vec<i64>,
    t: Vec<i64>,
    a: HashMap<String, Vec<i64>>,
}

fn draw(sim: &Sim, pool: &Pool, rng: &mut Rng, code: i64, s: &S8, own: &mut Owned) {
    let (cat, t) = (code / 10, (code % 10).to_string());
    match cat {
        0 => {
            let Some(lst) = pool.w.get(&t).filter(|l| !l.is_empty()) else { return };
            let n = pool.bias.max(1);
            let cands: Vec<&PW> = (0..n).map(|_| &lst[rng.below(lst.len())]).collect();
            let j = if cands.len() > 1 {
                let s5 = [s[3], s[4], s[5], s[6], s[7]];
                let ws: Vec<f64> = cands.iter().map(|c| (build_weight(c, &s5) * 10000.0).floor() + 1.0).collect();
                rng.choose_w(&ws)
            } else {
                0
            };
            own.w.push(cands[j].id);
        }
        1 => {
            let Some(lst) = pool.p.get(&t).filter(|l| !l.is_empty()) else { return };
            let (pid, slot) = &lst[rng.below(lst.len())];
            if sim.b.armors.contains_key(pid) {
                own.a.entry(slot.clone()).or_default().push(*pid);
            }
        }
        _ => {
            let Some(lst) = pool.a.get(&t).filter(|l| !l.is_empty()) else { return };
            own.t.push(lst[rng.below(lst.len())]);
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn run_dr(sim: &mut Sim, cfg: &Config, build: &Build, d: f64, runes: &[f64], kills: &[f64], tiers: &[(f64, f64)], slots: &[usize]) -> (Vec<Vec<Option<Rec>>>, Vec<i64>) {
    let a = cfg.assume_ref();
    let bands = cfg.bands;
    let b = sim.b;
    let pool = b.pool.as_ref().expect("DR 数据包没有装备样本");
    let dk = dkey(d);
    let drops = &b.drops[&dk];
    let mdrops = &b.mdrops[&dk];
    let levels: Vec<i64> = (0..bands).map(|i| level_from_runes(build.start_lv, runes[i])).collect();
    let stats: Vec<S8> = levels.iter().map(|&l| allocate(build, l)).collect();
    let u_rate: Vec<Vec<(i64, f64)>> = (0..bands).map(|i| drops[i].1.iter().filter(|(id, _)| (UNID0..UNID0 + 25).contains(id)).map(|&(id, p)| (id - UNID0, p)).collect()).collect();
    let stone_rate: Vec<Vec<(i64, f64)>> = (0..bands).map(|i| drops[i].1.iter().filter(|(id, _)| (10100..=10210).contains(id)).copied().collect()).collect();
    let mut rng = Rng::new(cfg.seed);
    let mut out = Vec::with_capacity(cfg.runs);
    for _ in 0..cfg.runs {
        let mut own = Owned { w: Vec::new(), t: Vec::new(), a: HashMap::new() };
        let s0 = stats[0];
        // 开局：稀有武器（偏向职业加点、近战能用）+ 每个部位一件防具
        for _ in 0..20 {
            let mut tmp = Owned { w: Vec::new(), t: Vec::new(), a: HashMap::new() };
            draw(sim, pool, &mut rng, a.start_weapon_tier as i64, &s0, &mut tmp);
            if let Some(&w) = tmp.w.first() {
                if sim.usable(w, &s0) {
                    own.w.push(w);
                    break;
                }
            }
        }
        for (slot, _) in &a.slot_share {
            let t = a.start_armor_tiers[rng.below(a.start_armor_tiers.len())].to_string();
            let lst: Vec<&(i64, String)> = pool.p.get(&t).map(|l| l.iter().filter(|x| &x.1 == slot).collect()).unwrap_or_default();
            if !lst.is_empty() {
                own.a.entry(slot.clone()).or_default().push(lst[rng.below(lst.len())].0);
            }
        }
        let mut stones: HashMap<i64, i64> = HashMap::new();
        let mut res: Vec<Option<Rec>> = Vec::with_capacity(bands);
        for bi in 0..bands {
            let half = kills[bi] / 2.0;
            let mitems = &mdrops[bi];
            let first: Vec<bool> = mitems.iter().map(|_| rng.f() < 0.5).collect();
            let got: Vec<bool> = mitems.iter().map(|x| rng.f() < x.2 * a.drop_ratio(&x.3)).collect();
            for step in 0..2 {
                let s = stats[bi];
                if step == 0 {
                    if let Some(&(_, n)) = a.free_wishes.iter().find(|x| x.0 == bi) {
                        let w = cfg.band_weights[bi.min(cfg.band_weights.len() - 1)];
                        let tiers_w: Vec<(i64, f64)> = (0..4).filter(|&k| w[k] > 0.0).map(|k| (if bi >= 4 && k == 3 { 4 } else { k as i64 }, w[k])).collect();
                        let ww: Vec<f64> = tiers_w.iter().map(|x| x.1).collect();
                        for _ in 0..n {
                            let cat = rng.choose_w(&cfg.cat_w) as i64;
                            let t = tiers_w[rng.choose_w(&ww)].0;
                            draw(sim, pool, &mut rng, cat * 10 + t, &s, &mut own);
                        }
                    }
                }
                for j in 0..mitems.len() {
                    if got[j] && (first[j] == (step == 0)) {
                        let (k, iid, _, _) = &mitems[j];
                        if k == "s" {
                            *stones.entry(sim.stone_tier(*iid, bi)).or_insert(0) += 1;
                        } else if k == "u" {
                            draw(sim, pool, &mut rng, iid - UNID0, &s, &mut own);
                        }
                    }
                }
                for &(code, p) in &u_rate[bi] {
                    let n = rng.poisson(half * p);
                    for _ in 0..n {
                        draw(sim, pool, &mut rng, code, &s, &mut own);
                    }
                }
                for &(sid, p) in &stone_rate[bi] {
                    *stones.entry(sim.stone_tier(sid, bi)).or_insert(0) += rng.poisson(half * p) as i64;
                }
                if step != 0 {
                    continue;
                }
                let r = &b.refs[bi];
                let mut ws = own.w.clone();
                ws.sort_unstable();
                ws.dedup();
                let mut best: Option<(i64, usize, V5, i64, f64)> = None;
                let mut best_v = -1.0;
                let mut own_ok = [0.0; 4];
                let mut lv_r = [0.0; 4];
                for (k, x) in lv_r.iter_mut().enumerate() {
                    if let Some(seq) = cfg.upgrade_stones.get(&k.to_string()) {
                        *x = seq.iter().take_while(|st| stones.get(st).copied().unwrap_or(0) > 0).count() as f64;
                    }
                }
                for w in ws {
                    if !sim.usable(w, &s) {
                        continue;
                    }
                    let wp = sim.wp(w);
                    own_ok[(wp.rar.clamp(0, 3)) as usize] += 1.0;
                    let mut lv = 0;
                    if let Some(seq) = cfg.upgrade_stones.get(&wp.rar.to_string()) {
                        for st in seq.iter().take(sim.max_level(w)) {
                            if stones.get(st).copied().unwrap_or(0) <= 0 {
                                break;
                            }
                            lv += 1;
                        }
                    }
                    let res_s: HashSet<i64> = wp.res.iter().copied().collect();
                    let we = sim.combine(&res_s);
                    let a_ = sim.ar(w, lv, &s);
                    let mean_dp = (0..5).map(|t| we.dealt[t] * we.pow[t]).sum::<f64>() / 5.0;
                    let v = sim.weapon_value(w, lv, &s, r) * mean_dp
                        + sim.extra_out(a_.iter().sum(), r.cut.iter().sum::<f64>() / 5.0, r.hp, we.flat, we.pct, we.pcap);
                    if v > best_v {
                        best_v = v;
                        best = Some((w, lv, a_, wp.rar, wp.w));
                    }
                }
                let Some((wid, lv, ar_, rar, wgt)) = best else {
                    res.push(None);
                    continue;
                };
                let load = (sim.max_load(s[2]) * a.load_ratio - wgt).max(0.0);
                let pdef = a.player_def[0] + a.player_def[1] * (levels[bi] - 1) as f64;
                let pick = sim.pick_armor(&own.a, load, wid, lv, &s, pdef, r);
                let (pcut, a_eff, mut a_sids, a_res) = sim.armor_effect(&pick);
                let w_sids: HashSet<i64> = sim.wp(wid).res.iter().copied().filter(|x| !a_sids.contains(x)).collect();
                let a_eff = a_eff.add(&sim.combine(&w_sids));
                a_sids.extend(w_sids);
                let php = hp_from_vigor(s[0]);
                let dealt = 1.0 + a.blessing_dealt * a.dlc_blessing[bi];
                let taken = 1.0 / (1.0 + a.blessing_taken * a.dlc_blessing[bi]);
                let (ev, nt, gain, evb) = sim.tal_eval(bi, &own.t, slots[bi], wid, lv, &s, levels[bi] as f64, pdef, &pcut, &a_eff, &a_sids, &a_res, dealt, taken, tiers);
                let armx = sim.armor_gain(wid, lv, &s, pdef, &pcut, &a_eff, r);
                let stw = if sim.status(wid, lv, s[7]).0.iter().any(|&x| x > 0.0) { 1.0 } else { 0.0 };
                res.push(Some(Rec { ev, ar: ar_.iter().sum(), lv: lv as f64, rar: rar as f64, hp: php, neg: 1.0 - pcut[0], tal: nt as f64, talx: gain, armx, stw, evb, own_ok, lv_r }));
            }
        }
        out.push(res);
    }
    (out, levels)
}

// ------------------------------------------------------------------ 原版对照
fn vanilla_line(sim: &mut Sim, cfg: &Config, build: &Build, runes: &[f64], d: f64, kills: &[f64], slots: &[usize]) -> Value {
    let a = cfg.assume_ref();
    let bands = cfg.bands;
    let b = sim.b;
    struct Fixed {
        s: S8,
        lv: usize,
        ar: V5,
        pcut: V5,
        a_eff: Eff,
        a_sids: HashSet<i64>,
        a_res: V6,
        php: f64,
        pdef: f64,
        dealt: f64,
        taken: f64,
        wid: i64,
        l: i64,
    }
    let mut fixed = Vec::new();
    for bi in 0..bands {
        let l = level_from_runes(build.start_lv, runes[bi]);
        let s = allocate(build, l);
        let lv = a.vanilla_upgrade[bi].min(sim.max_level(build.van));
        let r = &b.refs[bi];
        let cands: Vec<i64> = build.van_cands.iter().copied().filter(|&w| b.weapons.contains_key(&w) && sim.usable(w, &s)).collect();
        let cands = if cands.is_empty() { vec![build.van] } else { cands };
        let mut wid = cands[0];
        let mut wv = sim.weapon_value(wid, lv, &s, r);
        for &w in &cands[1..] {
            let v = sim.weapon_value(w, lv, &s, r);
            if v > wv {
                wv = v;
                wid = w;
            }
        }
        let ar = sim.ar(wid, lv, &s);
        let load = sim.max_load(s[2]) * a.load_ratio - sim.wp(wid).w;
        let pdef = a.player_def[0] + a.player_def[1] * (l - 1) as f64;
        let mut chosen = Vec::new();
        for (slot, share) in &a.slot_share {
            let mut fit: Vec<(f64, i64)> = Vec::new();
            for &p in b.van_pieces.get(slot).map(|v| v.as_slice()).unwrap_or(&[]) {
                let ap = &b.armors[&p];
                if ap.w <= load * share {
                    let sp: HashSet<i64> = ap.sp.iter().copied().collect();
                    let e = sim.combine(&sp);
                    let cut = ap.cut;
                    fit.push((sim.ref_score(wid, lv, &s, pdef, &cut, &e, r), p));
                }
            }
            if !fit.is_empty() {
                // 打分取整到 1e-9 再排（几乎一样的两件不因为运算顺序的末位误差换位置；一样的保持原来的顺序，和 Python 版一致）
                fit.sort_by_key(|x| (x.0 * 1e9).round() as i64);
                chosen.push(fit[(fit.len() as f64 * a.vanilla_armor_pct) as usize].1);
            }
        }
        let (pcut, a_eff, a_sids, a_res) = sim.armor_effect(&chosen);
        if std::env::var_os("DR_DEBUG").is_some() {
            eprintln!("原版 档{bi} 等级 {l} 属性 {s:?} 武器 {wid}+{lv} 负重 {load:.1} 防具 {chosen:?} 受伤 {pcut:?}");
        }
        let php = hp_from_vigor(s[0]);
        let dealt = 1.0 + a.blessing_dealt * a.dlc_blessing[bi];
        let taken = 1.0 / (1.0 + a.blessing_taken * a.dlc_blessing[bi]);
        fixed.push(Fixed { s, lv, ar, pcut, a_eff, a_sids, a_res, php, pdef, dealt, taken, wid, l });
    }
    let dk = dkey(d);
    let tl: Vec<&Vec<(i64, f64)>> = (0..bands).map(|i| &b.drops[&dk][i].0).collect();
    let mt: Vec<Vec<(i64, f64)>> = (0..bands).map(|i| b.mdrops[&dk][i].iter().filter(|x| x.0 == "t").map(|x| (x.1, x.2 * a.drop_ratio(&x.3))).collect()).collect();
    let mut rng = Rng::new(cfg.seed);
    let mut sims: Vec<Vec<[Option<f64>; 9]>> = Vec::new();
    for _ in 0..cfg.runs {
        let mut owned: Vec<i64> = Vec::new();
        let mut res = Vec::new();
        for bi in 0..bands {
            let first: Vec<bool> = mt[bi].iter().map(|_| rng.f() < 0.5).collect();
            let got: Vec<bool> = mt[bi].iter().map(|x| rng.f() < x.1).collect();
            for step in 0..2 {
                for j in 0..mt[bi].len() {
                    if got[j] && (first[j] == (step == 0)) {
                        owned.push(mt[bi][j].0);
                    }
                }
                if !tl[bi].is_empty() {
                    let ps: Vec<f64> = tl[bi].iter().map(|x| x.1).collect();
                    let n = rng.poisson(kills[bi] / 2.0 * ps.iter().sum::<f64>());
                    for _ in 0..n {
                        owned.push(tl[bi][rng.choose_w(&ps)].0);
                    }
                }
                if step == 0 {
                    let f = &fixed[bi];
                    let (ev, nt, gain, evb) = sim.tal_eval(bi, &owned, slots[bi], f.wid, f.lv, &f.s, f.l as f64, f.pdef, &f.pcut, &f.a_eff, &f.a_sids, &f.a_res, f.dealt, f.taken, &[(1.0, 1.0)]);
                    let e = ev[0];
                    let bb = evb.map(|x| x[0]);
                    res.push([Some(e[0]), Some(e[1]), Some(e[2]), Some(e[3]), Some(nt as f64), Some(gain), bb.map(|x| x[0]), bb.map(|x| x[1]), bb.map(|x| x[2])]);
                }
            }
        }
        sims.push(res);
    }
    let mut cols: HashMap<&str, Vec<Value>> = HashMap::new();
    for bi in 0..bands {
        let med: Vec<Option<f64>> = (0..9).map(|k| pct(&sims.iter().map(|r| r[bi][k]).collect::<Vec<_>>(), 0.5)).collect();
        let f = &fixed[bi];
        let armx = sim.armor_gain(f.wid, f.lv, &f.s, f.pdef, &f.pcut, &f.a_eff, &b.refs[bi]);
        let stw = if sim.status(f.wid, f.lv, f.s[7]).0.iter().any(|&x| x > 0.0) { 1.0 } else { 0.0 };
        let stx = match (med[2], med[3]) {
            (Some(x), Some(y)) => Some(x / y),
            _ => None,
        };
        for (k, v) in [
            ("h2k", med[0]), ("h2d", med[1]), ("idx", med[2]), ("stx", stx), ("tal", med[4]), ("talx", med[5]),
            ("bh2k", med[6]), ("bh2d", med[7]), ("bidx", med[8]), ("ar", Some(f.ar.iter().sum())), ("upgrade", Some(f.lv as f64)),
            ("hp", Some(f.php)), ("neg", Some(1.0 - f.pcut[0])), ("armx", Some(armx)), ("stw", Some(stw)), ("wid", Some(f.wid as f64)),
        ] {
            cols.entry(k).or_default().push(json!(v));
        }
    }
    let mut ser = serde_json::Map::new();
    ser.insert("mode".into(), json!("原版"));
    ser.insert("difficulty".into(), json!("普通"));
    ser.insert("level".into(), json!(fixed.iter().map(|f| f.l).collect::<Vec<_>>()));
    for (k, v) in cols {
        ser.insert(k.into(), Value::Array(v));
    }
    Value::Object(ser)
}

// ------------------------------------------------------------------ 词条排行
fn job_affix(sim: &mut Sim, cfg: &Config, build: &Build) -> Value {
    let a = cfg.assume_ref();
    let bands = cfg.bands;
    let runes = sim.cumulative(bands, a.kill_ratio, 0.0);
    let at: Vec<usize> = (0..4)
        .map(|r| {
            let share: Vec<f64> = (0..bands).map(|b| cfg.band_weights[b][r] / cfg.band_weights[b].iter().sum::<f64>().max(1.0)).collect();
            let mut m = 0;
            for (i, &v) in share.iter().enumerate() {
                if v > share[m] {
                    m = i;
                }
            }
            m
        })
        .collect();
    let mut ctxs = Vec::new();
    for &b in &at {
        let l = level_from_runes(build.start_lv, runes[b]);
        let s = allocate(build, l);
        let lv = a.vanilla_upgrade[b].min(sim.max_level(build.van));
        let pdef = a.player_def[0] + a.player_def[1] * (l - 1) as f64;
        let pcut = [0.6; 5];
        let s0 = sim.ref_score(build.van, lv, &s, pdef, &pcut, &Eff::neutral(), &sim.b.refs[b]);
        ctxs.push((lv, s, pdef, pcut, b, s0));
    }
    let mut rows = Vec::new();
    for x in sim.b.affix.as_ref().expect("没有词条表") {
        let mut gains = Vec::new();
        for (k, &sp) in x.sps.iter().enumerate() {
            if sp <= 0 {
                gains.push(Value::Null);
                continue;
            }
            let (lv, s, pdef, pcut, b, s0) = ctxs[k];
            let g = match sim.effect(sp) {
                None => 1.0,
                Some(e) => {
                    let e = e.clone();
                    sim.ref_score(build.van, lv, &s, pdef, &pcut, &e, &sim.b.refs[b]) / s0.max(1e-9)
                }
            };
            gains.push(json!(g));
        }
        rows.push(json!({"key": x.key, "name": x.name, "group": x.group, "kind": x.kind, "note": x.note, "where": x.where_, "gain": gains}));
    }
    json!({"bands_at": at, "rows": rows})
}

impl Config {
    fn assume_ref(&self) -> &Assume {
        &self.assume
    }
}

// ------------------------------------------------------------------ 任务
enum Job {
    Van(String),
    Affix,
    Dr(usize, String, usize),
}

fn d_of(cfg: &Config, build: &Build, db: f64) -> f64 {
    let luc = if cfg.assume.arcane_discovery { build.base.get("luc").copied().unwrap_or(0.0) } else { 0.0 };
    100.0 + luc + 100.0 * db
}

fn run_job(cfg: &Config, bundles: &[Bundle], job: &Job) -> Value {
    let a = &cfg.assume;
    let bands = cfg.bands;
    match job {
        Job::Van(bn) => {
            let b = &bundles[0];
            let build = &b.builds[bn];
            let mut sim = Sim::new(b, a);
            let runes = sim.cumulative(bands, a.kill_ratio, 0.0);
            let kills: Vec<f64> = (0..bands).map(|i| a.kill_ratio * b.count[i]).collect();
            let mut ser = vanilla_line(&mut sim, cfg, build, &runes, d_of(cfg, build, 0.0), &kills, &cfg.slots_v);
            ser["build"] = json!(bn);
            json!([ser])
        }
        Job::Affix => {
            let b = &bundles[1];
            let mut sim = Sim::new(b, a);
            job_affix(&mut sim, cfg, &b.builds["力敏"])
        }
        Job::Dr(mi, bn, gi) => {
            let b = &bundles[*mi];
            let build = &b.builds[bn];
            let g = &cfg.groups[*gi];
            let mut sim = Sim::new(b, a);
            let runes = sim.cumulative(bands, a.kill_ratio, g.rb);
            let kills: Vec<f64> = (0..bands).map(|i| a.kill_ratio * b.count[i]).collect();
            let tiers: Vec<(f64, f64)> = g.tiers.iter().map(|t| (t.enemy_hp, t.enemy_damage)).collect();
            let (sims, levels) = run_dr(&mut sim, cfg, build, d_of(cfg, build, g.db), &runes, &kills, &tiers, &cfg.slots_r);
            let mut out = Vec::new();
            for (j, t) in g.tiers.iter().enumerate() {
                let mut ser = serde_json::Map::new();
                ser.insert("mode".into(), json!(b.mode));
                ser.insert("build".into(), json!(bn));
                ser.insert("difficulty".into(), json!(t.name));
                ser.insert("level".into(), json!(levels));
                let getters: [(&str, Box<dyn Fn(&Rec) -> Option<f64>>); 15] = [
                    ("h2k", Box::new(move |x: &Rec| Some(x.ev[j][0]))),
                    ("h2d", Box::new(move |x: &Rec| Some(x.ev[j][1]))),
                    ("idx", Box::new(move |x: &Rec| Some(x.ev[j][2]))),
                    ("stx", Box::new(move |x: &Rec| Some(x.ev[j][2] / x.ev[j][3]))),
                    ("ar", Box::new(|x: &Rec| Some(x.ar))),
                    ("upgrade", Box::new(|x: &Rec| Some(x.lv))),
                    ("rarity", Box::new(|x: &Rec| Some(x.rar))),
                    ("hp", Box::new(|x: &Rec| Some(x.hp))),
                    ("neg", Box::new(|x: &Rec| Some(x.neg))),
                    ("tal", Box::new(|x: &Rec| Some(x.tal))),
                    ("talx", Box::new(|x: &Rec| Some(x.talx))),
                    ("armx", Box::new(|x: &Rec| Some(x.armx))),
                    ("bh2k", Box::new(move |x: &Rec| x.evb.as_ref().map(|e| e[j][0]))),
                    ("bh2d", Box::new(move |x: &Rec| x.evb.as_ref().map(|e| e[j][1]))),
                    ("bidx", Box::new(move |x: &Rec| x.evb.as_ref().map(|e| e[j][2]))),
                ];
                for (k, f) in &getters {
                    for (q, qn) in [(0.1, "_p10"), (0.5, ""), (0.9, "_p90")] {
                        let col: Vec<Value> = (0..bands)
                            .map(|bi| json!(pct(&sims.iter().filter_map(|r| r[bi].as_ref()).map(|x| f(x)).collect::<Vec<_>>(), q)))
                            .collect();
                        ser.insert(format!("{k}{qn}"), Value::Array(col));
                    }
                }
                let stw: Vec<Value> = (0..bands)
                    .map(|bi| {
                        let v: Vec<f64> = sims.iter().filter_map(|r| r[bi].as_ref()).map(|x| x.stw).collect();
                        json!(if v.is_empty() { 0.0 } else { v.iter().sum::<f64>() / v.len() as f64 })
                    })
                    .collect();
                ser.insert("stw".into(), Value::Array(stw));
                // 各稀有度：主力武器是这个稀有度的比例、手上能用的件数（平均）、能强化到几级（中位）
                let per_rar = |f: &dyn Fn(&Rec, usize) -> f64, mean: bool| -> Value {
                    Value::Array(
                        (0..bands)
                            .map(|bi| {
                                let rs: Vec<&Rec> = sims.iter().filter_map(|r| r[bi].as_ref()).collect();
                                json!((0..4)
                                    .map(|k| {
                                        let v: Vec<f64> = rs.iter().map(|x| f(x, k)).collect();
                                        if v.is_empty() {
                                            None
                                        } else if mean {
                                            Some(v.iter().sum::<f64>() / v.len() as f64)
                                        } else {
                                            pct(&v.iter().map(|&x| Some(x)).collect::<Vec<_>>(), 0.5)
                                        }
                                    })
                                    .collect::<Vec<_>>())
                            })
                            .collect(),
                    )
                };
                ser.insert("rar_share".into(), per_rar(&|x, k| if x.rar.round() as usize == k { 1.0 } else { 0.0 }, true));
                ser.insert("own_ok".into(), per_rar(&|x, k| x.own_ok[k], true));
                ser.insert("lv_r".into(), per_rar(&|x, k| x.lv_r[k], false));
                out.push(Value::Object(ser));
            }
            Value::Array(out)
        }
    }
}

fn main() {
    let path = std::env::args().nth(1).expect("用法：power_sim <配置.json>");
    let cfg: Config = serde_json::from_str(&std::fs::read_to_string(&path).expect("读不了配置")).expect("配置格式不对");
    let t0 = Instant::now();
    let bundles: Vec<Bundle> = std::thread::scope(|sc| {
        let hs: Vec<_> = cfg.bundles.iter().map(|p| sc.spawn(move || load_bundle(p))).collect();
        hs.into_iter().map(|h| h.join().expect("读数据包")).collect()
    });
    println!("读数据包 {:.1} 秒", t0.elapsed().as_secs_f64());
    let mut jobs: Vec<Job> = Vec::new();
    for bn in &cfg.build_order {
        jobs.push(Job::Van(bn.clone()));
    }
    jobs.push(Job::Affix);
    for mi in 1..bundles.len() {
        for bn in &cfg.build_order {
            for gi in 0..cfg.groups.len() {
                jobs.push(Job::Dr(mi, bn.clone(), gi));
            }
        }
    }
    let next = AtomicUsize::new(0);
    let done = AtomicUsize::new(0);
    let results: Mutex<Vec<Option<Value>>> = Mutex::new((0..jobs.len()).map(|_| None).collect());
    let total = jobs.len();
    std::thread::scope(|sc| {
        for _ in 0..cfg.threads.max(1) {
            sc.spawn(|| loop {
                let i = next.fetch_add(1, Ordering::SeqCst);
                if i >= jobs.len() {
                    break;
                }
                let v = run_job(&cfg, &bundles, &jobs[i]);
                let label = match &jobs[i] {
                    Job::Van(b) => format!("{b} · 原版"),
                    Job::Affix => "词条排行".into(),
                    Job::Dr(mi, b, gi) => format!("{b} · {} · 卢恩 {:+.0}% 发现力 {:+.0}", bundles[*mi].mode, cfg.groups[*gi].rb * 100.0, cfg.groups[*gi].db * 100.0),
                };
                results.lock().unwrap()[i] = Some(v);
                let n = done.fetch_add(1, Ordering::SeqCst) + 1;
                println!("  [{n}/{total} {:4.0} 秒] {label}", t0.elapsed().as_secs_f64());
            });
        }
    });
    let results = results.into_inner().unwrap();
    let get = |pred: &dyn Fn(&Job) -> bool| -> Value { results[jobs.iter().position(|j| pred(j)).unwrap()].clone().unwrap() };
    let mut series = Vec::new();
    for bn in &cfg.build_order {
        if let Value::Array(v) = get(&|j| matches!(j, Job::Van(b) if b == bn)) {
            series.extend(v);
        }
        for mi in 1..bundles.len() {
            for gi in 0..cfg.groups.len() {
                if let Value::Array(v) = get(&|j| matches!(j, Job::Dr(m, b, g) if *m == mi && b == bn && *g == gi)) {
                    series.extend(v);
                }
            }
        }
    }
    let affix = get(&|j| matches!(j, Job::Affix));
    let out = json!({"series": series, "affix_rank": affix});
    std::fs::write(&cfg.out, serde_json::to_string(&out).unwrap()).expect("写不了结果");
    println!("模拟完：{:.0} 秒", t0.elapsed().as_secs_f64());
}
