//! 庆典油脂（参数侧见重随的 rr/festive.py）：油脂效果（右手 / 左手各一个）在玩家身上时，每秒扣当前卢恩的 drain%，
//! 再按扣完的卢恩挂加伤档位：+k%，k = 档数 × min(卢恩, 满加成卢恩) ÷ 满加成卢恩（取整），效果编号 = 起点 + k。
//! 每秒先摘旧档再挂新档（档位效果自己只持续几秒，这里停了也会自己消失）；涂上那一下不扣、直接按当前卢恩挂；油脂没了就摘掉。
//! 定义：DLL 旁边的 festive.txt（重随时生成），一行「油脂效果编号（逗号分隔）<TAB>档位起点<TAB>档数<TAB>满加成卢恩<TAB>每秒扣的百分比」。

use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{ChrInsExt, SoloParamRepository, SpEffectParam, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

#[derive(Debug, PartialEq)]
struct Def {
    ids: Vec<i32>,
    base: i32,
    tiers: u32,
    full: u32,
    drain: f64,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();
/// 游戏里的参数是不是重随改过的：加伤档位效果存在、油脂效果的「命中得卢恩」已清掉。不重随的模式启动时游戏用原版油脂，
/// festive.txt 却还是上次重随留下的——这时不扣卢恩、不加伤。第一次检测到油脂生效时查（那时参数一定载入了）
static PARAMS_OK: OnceLock<bool> = OnceLock::new();
/// 进行中：（现在挂着的档位, 下一次扣卢恩 / 换档的时间, 开始时的卢恩）
static ST: Mutex<Option<(u32, Instant, u32)>> = Mutex::new(None);

fn parse(text: &str) -> Option<Def> {
    let line = text.lines().map(|l| l.trim_start_matches('\u{feff}')).find(|l| !l.starts_with('#') && !l.trim().is_empty())?;
    let f: Vec<&str> = line.trim_end().split('\t').collect();
    if f.len() < 5 {
        return None;
    }
    let ids = f[0].split(',').map(|s| s.trim().parse::<i32>().ok()).collect::<Option<Vec<_>>>()?;
    let (base, tiers, full, drain) = (f[1].parse().ok()?, f[2].parse().ok()?, f[3].parse().ok()?, f[4].parse::<f64>().ok()?);
    (!ids.is_empty() && tiers > 0 && full > 0 && (0.0..=100.0).contains(&drain)).then_some(Def { ids, base, tiers, full, drain })
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("festive.txt")).unwrap_or_default())).as_ref()
}

/// 卢恩 → 档位（+k%）
fn tier(d: &Def, runes: u32) -> u32 {
    (d.tiers as u64 * runes.min(d.full) as u64 / d.full as u64) as u32
}

/// 每秒扣的卢恩（向下取整）
fn cost(d: &Def, runes: u32) -> u32 {
    (runes as f64 * d.drain / 100.0).floor() as u32
}

fn params_ok(d: &Def) -> bool {
    *PARAMS_OK.get_or_init(|| {
        let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return false };
        let tiers = repo.get::<SpEffectParam>((d.base + 1) as u32).is_some() && repo.get::<SpEffectParam>((d.base + d.tiers as i32) as u32).is_some();
        let grease = d.ids.iter().all(|&i| repo.get::<SpEffectParam>(i as u32).is_some_and(|p| p.cycle_occurrence_sp_effect_id() == -1));
        let ok = tiers && grease;
        if !ok {
            log(&format!("庆典油脂：游戏里的参数不是重随改过的（加伤档位 {tiers}，油脂效果 {grease}，大概是用不重随的模式启动的），这次不扣卢恩、不加伤"));
        }
        ok
    })
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("庆典油脂（{} 卢恩时 +{}%，每秒扣 {}% 卢恩）", d.full, d.tiers, d.drain),
        None => "庆典油脂（没有 festive.txt，不管）".into(),
    }
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut st = ST.lock().unwrap_or_else(|e| e.into_inner());
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        *st = None;
        return;
    };
    let active = p.chr_ins.special_effect.entries().any(|e| d.ids.contains(&e.param_id)) && params_ok(d);
    let now = Instant::now();
    let mut gd = p.player_game_data;
    let pgd = unsafe { gd.as_mut() };
    match (*st, active) {
        (None, false) => {}
        (Some((old, _, start)), false) => {
            if old > 0 {
                p.remove_speffect(d.base + old as i32);
            }
            log(&format!("庆典油脂：结束（卢恩 {start} → {}）", pgd.rune_count));
            *st = None;
        }
        (Some((_, due, _)), true) if now < due => {}
        (cur, true) => {
            let start = cur.map(|c| c.2).unwrap_or(pgd.rune_count);
            if cur.is_some() {
                pgd.rune_count -= cost(d, pgd.rune_count);
            }
            let k = tier(d, pgd.rune_count);
            let old = cur.map(|c| c.0).unwrap_or(0);
            if old > 0 {
                p.remove_speffect(d.base + old as i32);
            }
            if k > 0 {
                p.apply_speffect(d.base + k as i32, false);
            }
            if cur.is_none() {
                log(&format!("庆典油脂：开始（卢恩 {start}，伤害 +{k}%）"));
            }
            // 下一秒；卡顿过了就从现在算，不一口气补扣
            let next = cur.map(|c| c.1 + Duration::from_secs(1)).filter(|t| *t > now).unwrap_or(now + Duration::from_secs(1));
            *st = Some((k, next, start));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn def_and_tiers() {
        let d = parse("# 注释\n20501620,20501622\t369200\t50\t1000000\t1\n").unwrap();
        assert_eq!(d, Def { ids: vec![20501620, 20501622], base: 369200, tiers: 50, full: 1000000, drain: 1.0 });
        assert_eq!(tier(&d, 0), 0);
        assert_eq!(tier(&d, 19999), 0);
        assert_eq!(tier(&d, 20000), 1);
        assert_eq!(tier(&d, 500000), 25);
        assert_eq!(tier(&d, 1000000), 50);
        assert_eq!(tier(&d, 9999999), 50);
        assert_eq!(cost(&d, 1000000), 10000);
        assert_eq!(cost(&d, 99), 0);
        assert_eq!(parse(""), None);
        assert_eq!(parse("1\t2\t3\n"), None);
        assert_eq!(parse("x\t369200\t50\t1000000\t1\n"), None);
    }
}
