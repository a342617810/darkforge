//! 词条「无形」dr_unseen 的子弹那一路（参数侧见重随的 rr/unseen.py；用户 2026-11-06「能不能加个词条实现黑夜魔法的效果 不会被读指令」）。
//! 同日用户「只管远程箭和法术道具 近战不屏蔽」「喝药灵药也不拦截」，所以 unseen.txt 只有箭、法术、道具、法球的子弹。
//! 这条词条管两路：玩家脚本通知 AI 的施法（sc/hks.py 的 AFFIX_UNSEEN，戴着时不发），和这些子弹。
//! 游戏决定要不要让 AI 知道这颗子弹时（2.7.1.0 的 0x49e610）：子弹参数的 isDisableAiProjectileDodge（+0xC3 位 5）开着就不通知；
//! 否则有攻击力就通知，没攻击力再看 isAiInterruptShootNoDamageBullet（位 7）。原版黑夜魔法的根子弹攻击力是 0，走的是后面这条。
//! 这里戴着时把 unseen.txt 里的子弹的这一位打开（每颗子弹发射时现查这张表，下一发就生效），摘下 1 秒后把改过的还原。
//! 不用 hook，没有地址，两个游戏版本都能用。没重随的模式参数里没有标记，戴不上，什么都不做。

use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{Bullet, SoloParamRepository, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

/// 多久看一次戴没戴
const SCAN: Duration = Duration::from_millis(500);
/// 标记没有多久才算摘下（读档时可能闪一下）
const OFF_GRACE: Duration = Duration::from_secs(1);

#[derive(Debug, Default, PartialEq)]
struct Def {
    marks: Vec<i32>,
    /// 排好序的子弹编号
    bullets: Vec<u32>,
}

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    for l in text.lines() {
        let mut f = l.trim_start_matches('\u{feff}').split_whitespace();
        match f.next() {
            Some("mark") => d.marks.extend(f.filter_map(|x| x.parse::<i32>().ok()).filter(|&m| m > 0)),
            Some("b") => d.bullets.extend(f.filter_map(|x| x.parse::<u32>().ok())),
            _ => {}
        }
    }
    d.bullets.sort_unstable();
    d.bullets.dedup();
    (!d.marks.is_empty() && !d.bullets.is_empty()).then_some(d)
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("unseen.txt")).unwrap_or_default())).as_ref()
}

struct St {
    next: Instant,
    on: bool,
    off_since: Option<Instant>,
    /// 我们打开过的子弹（原来就开着的不算，摘下时不动）
    changed: Vec<u32>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 把清单里还没开的打开、记下来
fn open_all(d: &Def, st: &mut St) {
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    let mut n = 0;
    for (id, r) in repo.rows_mut::<Bullet>() {
        if !r.is_disable_ai_projectile_dodge() && d.bullets.binary_search(&id).is_ok() {
            r.set_is_disable_ai_projectile_dodge(true);
            st.changed.push(id);
            n += 1;
        }
    }
    st.changed.sort_unstable();
    st.changed.dedup();
    log(&format!("无形：戴上了，{n} 行子弹不再通知敌人的 AI"));
}

/// 还原我们打开过的
fn close_all(st: &mut St) {
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    for &id in &st.changed {
        if let Some(r) = repo.get_mut::<Bullet>(id) {
            r.set_is_disable_ai_projectile_dodge(false);
        }
    }
    log(&format!("无形：摘下了，{} 行子弹还原", st.changed.len()));
    st.changed.clear();
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St { next: now, on: false, off_since: None, changed: Vec::new() });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(p) = wcm.main_player.as_ref() else { return };
    let worn = p.chr_ins.special_effect.entries().any(|e| d.marks.contains(&e.param_id));
    if worn {
        st.off_since = None;
        // 已经开着时只看第一行：游戏重新载入过参数，这一位就回去了
        let stale = st.changed.first().is_some_and(|&id| unsafe { SoloParamRepository::instance() }
            .ok().and_then(|repo| repo.get::<Bullet>(id)).is_some_and(|r| !r.is_disable_ai_projectile_dodge()));
        if !st.on || stale {
            st.on = true;
            open_all(d, st);
        }
    } else if st.on {
        let t = *st.off_since.get_or_insert(now);
        if now - t >= OFF_GRACE {
            st.on = false;
            st.off_since = None;
            close_all(st);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use eldenring::param::BULLET_PARAM_ST;

    /// 定义文件：标记和子弹都要有；子弹排序去重；注释行、标记 -1 跳过
    #[test]
    fn parse_def() {
        let d = parse("\u{feff}# 头\nmark -1 7210999\ntalisman 9500\nb 30 10\nb 20 10\nx y\n").unwrap();
        assert_eq!(d, Def { marks: vec![7210999], bullets: vec![10, 20, 30] });
        assert!(parse("mark 1\n").is_none());
        assert!(parse("b 1\n").is_none());
        assert!(parse("").is_none());
    }

    /// 库里的字段就是逆向看到的那一位（+0xC3 位 5），不碰位 7（isAiInterruptShootNoDamageBullet）
    #[test]
    fn dodge_bit_matches_the_game_check() {
        let mut r: BULLET_PARAM_ST = unsafe { std::mem::zeroed() };
        let byte = |r: &BULLET_PARAM_ST| unsafe { *(r as *const BULLET_PARAM_ST as *const u8).add(0xC3) };
        r.set_is_disable_ai_projectile_dodge(true);
        assert_eq!(byte(&r), 0x20);
        assert!(r.is_disable_ai_projectile_dodge() && !r.is_ai_interrupt_shoot_no_damage_bullet());
        r.set_is_disable_ai_projectile_dodge(false);
        assert_eq!(byte(&r), 0);
    }
}
