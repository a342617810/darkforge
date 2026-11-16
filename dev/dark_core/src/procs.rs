//! 触发词条的属性补正（参数侧见重随的 rr/procs.py；用户 2026-10-31）：词条触发的爆炸 / 子弹 / 治疗波原来是固定数值，
//! 现在按人物属性乘倍率——物理按力气、灵巧里高的，魔力按智力，火、圣按信仰，雷按灵巧；治疗按信仰。
//! 倍率 = 1 + K × 补正曲线(属性)%，K 让「属性 = at 时倍率 = mult」（scale 行，用户定 80 点约 ×3）。属性用人物本身的（不算护符加的）。
//! 改的是参数行本身：攻击行（AtkParam_Pc）的五种攻击力、治疗效果的 changeHpPoint，基础值 × 倍率取整；属性变了重写一次（每 0.5 秒查一次）。
//! 这些行重随时已经复制成词条专用的（原版法术用的不动）。法球、引爆是积木规则，rules 用 mults() 乘（法球按魔力、火两项里大的 = 智力、信仰取高；物理那一项）。
//! 定义：DLL 旁边的 procs.txt：scale <补正曲线> <属性> <倍率>；atk <编号> <物理> <魔力> <火> <雷> <圣>；heal <效果编号> <changeHpPoint>。
//! 第一次改之前核对游戏里的值和定义一致（不重随的模式启动时参数是原版的、定义却是上次重随留下的），对不上就不改这些行。

use std::fs;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{AtkParam_Pc, CalcCorrectGraph, SoloParamRepository, SpEffectParam, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

const CHECK_EVERY: Duration = Duration::from_millis(500);

#[derive(Debug, PartialEq)]
struct Def {
    graph: u32,
    at: f32,
    mult: f32,
    atk: Vec<(u32, [u16; 5])>,
    heal: Vec<(u32, i32)>,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();
/// 现在的倍率（物理 魔力 火 雷 圣），f32 的位；rules 的法球 / 引爆读。没有 procs.txt、还没算过都是 1
static MULT: [AtomicU32; 5] = [const { AtomicU32::new(0x3f80_0000) }; 5];

struct St {
    /// 参数行是不是重随改过的（第一次要写之前核对）
    rows_ok: Option<bool>,
    /// 上次按哪组属性（力 灵 智 信）写的
    applied: Option<[u32; 4]>,
    next: Instant,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

fn parse(text: &str) -> Option<Def> {
    let mut d = Def { graph: 0, at: 80.0, mult: 1.0, atk: Vec::new(), heal: Vec::new() };
    let mut scale = false;
    for line in text.lines().map(|l| l.trim_start_matches('\u{feff}').trim_end()) {
        let f: Vec<&str> = line.split('\t').collect();
        match (f[0], f.len()) {
            ("scale", 4..) => {
                d.graph = f[1].parse().ok()?;
                d.at = f[2].parse().ok()?;
                d.mult = f[3].parse().ok()?;
                scale = true;
            }
            ("atk", 7..) => {
                let v: Vec<u16> = f[2..7].iter().map(|x| x.parse().ok()).collect::<Option<_>>()?;
                d.atk.push((f[1].parse().ok()?, v.try_into().ok()?));
            }
            ("heal", 3..) => d.heal.push((f[1].parse().ok()?, f[2].parse().ok()?)),
            _ => {}
        }
    }
    (scale && d.at > 0.0 && d.mult >= 1.0).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("procs.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("触发词条补正（{} 点 ×{}，攻击行 {}、治疗 {}）", d.at, d.mult, d.atk.len(), d.heal.len()),
        None => "触发词条补正（没有 procs.txt，不管）".into(),
    }
}

/// 现在的倍率（物理 魔力 火 雷 圣）
pub fn mults() -> [f32; 5] {
    std::array::from_fn(|k| f32::from_bits(MULT[k].load(Ordering::Relaxed)))
}

/// 属性（力 灵 智 信）→ 五种伤害的倍率；curve 是补正曲线（属性 → %）
fn mults_for(d: &Def, stats: [u32; 4], curve: impl Fn(f32) -> f32) -> [f32; 5] {
    let ref_pct = curve(d.at);
    let k = if ref_pct > 0.0 { (d.mult - 1.0) / (ref_pct / 100.0) } else { 0.0 };
    let m = |s: u32| 1.0 + k * curve(s as f32) / 100.0;
    let [str_, dex, int, fai] = stats;
    [m(str_.max(dex)), m(int), m(fai), m(dex), m(fai)]
}

fn scaled(base: u16, m: f32) -> u16 {
    (base as f32 * m).round().clamp(0.0, u16::MAX as f32) as u16
}

/// 游戏里的行和定义的基础值一样（还没改过）：是重随生成的参数
fn rows_match(d: &Def, repo: &SoloParamRepository) -> bool {
    let atk = d.atk.iter().all(|(id, v)| {
        repo.get::<AtkParam_Pc>(*id).is_some_and(|a| [a.atk_phys(), a.atk_mag(), a.atk_fire(), a.atk_thun(), a.atk_dark()] == *v)
    });
    let heal = d.heal.iter().all(|(id, v)| repo.get::<SpEffectParam>(*id).is_some_and(|s| s.change_hp_point() == *v));
    atk && heal
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut guard = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = guard.get_or_insert_with(|| St { rows_ok: None, applied: None, next: Instant::now() });
    let now = Instant::now();
    if now < st.next {
        return;
    }
    st.next = now + CHECK_EVERY;
    let Ok(wcm) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(p) = wcm.main_player.as_ref() else { return };
    let pgd = unsafe { p.player_game_data.as_ref() };
    let stats = [pgd.strength, pgd.dexterity, pgd.intelligence, pgd.faith];
    if st.applied == Some(stats) {
        return;
    }
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    let Some(g) = repo.get::<CalcCorrectGraph>(d.graph) else {
        log(&format!("触发词条补正：补正曲线 {} 不存在，不改", d.graph));
        st.applied = Some(stats);
        return;
    };
    let m = mults_for(d, stats, |x| crate::gear::graph(g, x));
    for (k, v) in m.iter().enumerate() {
        MULT[k].store(v.to_bits(), Ordering::Relaxed);
    }
    let ok = *st.rows_ok.get_or_insert_with(|| {
        let ok = rows_match(d, repo);
        if !ok {
            log("触发词条补正：游戏里的攻击行 / 治疗效果和 procs.txt 对不上（大概是用不重随的模式启动的），这次不改这些行（法球、引爆照样按属性算）");
        }
        ok
    });
    if ok {
        for (id, v) in &d.atk {
            if let Some(a) = repo.get_mut::<AtkParam_Pc>(*id) {
                a.set_atk_phys(scaled(v[0], m[0]));
                a.set_atk_mag(scaled(v[1], m[1]));
                a.set_atk_fire(scaled(v[2], m[2]));
                a.set_atk_thun(scaled(v[3], m[3]));
                a.set_atk_dark(scaled(v[4], m[4]));
            }
        }
        for (id, v) in &d.heal {
            if let Some(s) = repo.get_mut::<SpEffectParam>(*id) {
                s.set_change_hp_point((*v as f32 * m[2]).round() as i32);
            }
        }
    }
    log(&format!("触发词条补正：力 {} 灵 {} 智 {} 信 {} → 物理 ×{:.2} 魔力 ×{:.2} 火 ×{:.2} 雷 ×{:.2} 圣 ×{:.2}{}", stats[0], stats[1], stats[2], stats[3],
                 m[0], m[1], m[2], m[3], m[4], if ok { "" } else { "（只用于法球、引爆）" }));
    st.applied = Some(stats);
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 原版补正曲线 0：1 → 0%、18 → 25%、60 → 75%、80 → 90%、150 → 110%，adjPt 1.2 / -1.2 / 1 / 1
    fn curve0(x: f32) -> f32 {
        let (smv, grow, adj) = ([1.0, 18.0, 60.0, 80.0, 150.0], [0.0, 25.0, 75.0, 90.0, 110.0], [1.2f32, -1.2, 1.0, 1.0, 1.0]);
        if x <= smv[0] {
            return grow[0];
        }
        if x >= smv[4] {
            return grow[4];
        }
        let mut i = 0;
        while i < 3 && x > smv[i + 1] {
            i += 1;
        }
        let t = (x - smv[i]) / (smv[i + 1] - smv[i]);
        let t = if adj[i] > 0.0 { t.powf(adj[i]) } else if adj[i] < 0.0 { 1.0 - (1.0 - t).powf(-adj[i]) } else { t };
        grow[i] + (grow[i + 1] - grow[i]) * t
    }

    #[test]
    fn parse_and_mults() {
        let d = parse("# 头\nscale\t0\t80\t3\natk\t308000000\t70\t384\t0\t0\t0\nheal\t7298000\t-230\nwhat\t1\n").unwrap();
        assert_eq!(d.atk, vec![(308000000, [70, 384, 0, 0, 0])]);
        assert_eq!(d.heal, vec![(7298000, -230)]);
        // 80 点正好 ×3；物理取力气、灵巧里高的；雷按灵巧；火、圣按信仰
        let m = mults_for(&d, [10, 80, 80, 80], curve0);
        assert!((m[0] - 3.0).abs() < 1e-4 && (m[1] - 3.0).abs() < 1e-4 && (m[3] - 3.0).abs() < 1e-4);
        let m = mults_for(&d, [80, 10, 1, 99], curve0);
        assert!((m[0] - 3.0).abs() < 1e-4, "{m:?}");
        assert!((m[1] - 1.0).abs() < 1e-4, "属性 1 时曲线是 0：倍率 1，{m:?}");
        assert!(m[2] > 3.0 && m[2] < 3.2 && m[4] == m[2], "{m:?}");
        assert!(m[3] > 1.2 && m[3] < 1.3, "灵巧 10 约 ×1.26：{m:?}");
        assert_eq!(scaled(384, 3.0), 1152);
        assert_eq!(scaled(60000, 3.0), u16::MAX);
        // 没有 scale 行 / 倍率小于 1：不认
        assert_eq!(parse("atk\t1\t1\t0\t0\t0\t0\n"), None);
        assert_eq!(parse("scale\t0\t80\t0.5\n"), None);
    }
}
