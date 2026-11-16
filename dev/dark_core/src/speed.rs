//! 别的角色（敌人、NPC、灵马、骨灰；不含玩家）的动作速度：几处功能报倍数，帧末这里乘起来写一次（用户 2026-11-16「参考一下」爬塔 mod 迅猛词条；
//! 2026-11-17「魇化精英也搬」从联机分支搬到主分支，主分支没有联机的部分）。
//! 以前时隙（runtime.rs）、见切 / 影步减速（rules.rs）、魇化精英加快（nightmare.rs）各自直接写 animation_speed，同一帧后写的盖掉先写的：
//! 魇化精英加快每 250 毫秒写回 1.x，见切、影步对精英就时灵时不灵；时隙和减速同理。现在：
//! - 各功能调 want(角色, 来源, 倍数, 保持多久)：同一个角色几个来源的倍数相乘（精英 ×1.3、被见切 ×0.3 → ×0.39），
//!   同一来源再报就换掉旧的；过了保持时间没再报就当不要了（每帧报的给 HOLD_FRAME，魇化 250 毫秒扫一次给 HOLD_SCAN）；
//! - flush()（lib.rs，这一帧所有功能之后）写进去；没人要了、上次是我们写的、值也还是我们写的那个 → 改回 1（不碰游戏或别的 mod 改的）。
//! 角色按地址 + NPC 编号认，每帧对照游戏的角色列表（live!），不在了的丢掉，不往已经释放的角色上写。

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::{ChrIns, WorldChrMan};
use fromsoftware_shared::FromStatic;

/// 每帧报的来源：这么久没再报就当不要了（读图、某一帧没跑到时不至于闪回原速）
pub const HOLD_FRAME: Duration = Duration::from_millis(120);
/// 魇化每 250 毫秒扫一次
pub const HOLD_SCAN: Duration = Duration::from_millis(400);
/// 写进去的倍数范围（0 = 停住）
const MAX: f32 = 3.0;

#[derive(Default)]
struct St {
    /// (角色地址, 来源) → (倍数, 到期, NPC 编号)
    wants: HashMap<(usize, &'static str), (f32, Instant, i32)>,
    /// 上次我们写进去的：角色地址 → 值
    wrote: HashMap<usize, f32>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

fn ok(m: f32) -> bool {
    m.is_finite() && (0.0..=MAX).contains(&m)
}

/// 这个角色要乘 m，保持 hold（同一来源再报就换掉；m = 1 也可以报）
pub fn want(c: &ChrIns, tag: &'static str, m: f32, hold: Duration) {
    if !ok(m) {
        return;
    }
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    g.get_or_insert_with(St::default).wants.insert((c as *const ChrIns as usize, tag), (m, Instant::now() + hold, c.npc_param_id));
}

/// 这个来源不要了（马上，不等保持时间）
pub fn stop(addr: usize, tag: &'static str) {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(st) = g.as_mut() {
        st.wants.remove(&(addr, tag));
    }
}

/// 各来源合起来：角色地址 → 倍数（相乘；过期的不算）
pub(crate) fn combine(wants: &HashMap<(usize, &'static str), (f32, Instant, i32)>, now: Instant) -> HashMap<usize, f32> {
    let mut out: HashMap<usize, f32> = HashMap::new();
    for (&(a, _), &(m, until, _)) in wants {
        if until > now {
            *out.entry(a).or_insert(1.0) *= m;
        }
    }
    out
}

/// 这一帧要写什么（纯函数，单元测试用）：want = 要的倍数，wrote = 上次写的，cur = 现在的值（不在场的 None）。
/// 返回 (要写的 (地址, 值), 新的 wrote)
pub(crate) fn plan(want: &HashMap<usize, f32>, wrote: &HashMap<usize, f32>, cur: &dyn Fn(usize) -> Option<f32>) -> (Vec<(usize, f32)>, HashMap<usize, f32>) {
    let mut out = Vec::new();
    let mut next = HashMap::new();
    for (&a, &m) in want {
        let Some(c) = cur(a) else { continue };
        let v = m.clamp(0.0, MAX);
        if (v - 1.0).abs() < 1e-6 && !wrote.contains_key(&a) {
            continue; // 要 ×1、我们也没改过：不碰
        }
        if (c - v).abs() > 1e-4 {
            out.push((a, v));
        }
        next.insert(a, v);
    }
    for (&a, &w) in wrote {
        if next.contains_key(&a) {
            continue;
        }
        // 没人要了：值还是我们写的才改回 1（不碰游戏或别的 mod 改的）
        if let Some(c) = cur(a) {
            if (c - w).abs() < 1e-4 && (c - 1.0).abs() > 1e-6 {
                out.push((a, 1.0));
            }
        }
    }
    (out, next)
}

/// 每帧（lib.rs，时隙、积木引擎、魇化之后）
pub fn flush() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let Some(st) = g.as_mut() else { return };
    let now = Instant::now();
    st.wants.retain(|_, v| v.1 > now);
    if st.wants.is_empty() && st.wrote.is_empty() {
        return;
    }
    let Ok(w) = (unsafe { WorldChrMan::instance() }) else { return };
    let live = live!(w);
    // 不在场了、或者这个地址已经换成别的角色了：丢掉
    st.wants.retain(|k, v| {
        if !live.contains(&k.0) {
            return false;
        }
        let c = unsafe { &*(k.0 as *const ChrIns) };
        c.npc_param_id == v.2
    });
    let want = combine(&st.wants, now);
    let cur = |a: usize| {
        live.contains(&a).then(|| {
            let c = unsafe { &*(a as *const ChrIns) };
            c.modules.behavior.animation_speed
        })
    };
    let (out, next) = plan(&want, &st.wrote, &cur);
    for (a, v) in out {
        let c = unsafe { &mut *(a as *mut ChrIns) };
        c.modules.behavior.animation_speed = v;
    }
    st.wrote = next;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn combine_multiplies_and_expires() {
        let now = Instant::now();
        let later = now + Duration::from_secs(1);
        let mut w: HashMap<(usize, &'static str), (f32, Instant, i32)> = HashMap::new();
        w.insert((1, "魇化"), (1.3, later, 0));
        w.insert((1, "减速"), (0.3, later, 0));
        w.insert((2, "时隙"), (1.2, later, 0));
        w.insert((3, "时隙"), (1.2, now, 0)); // 过期
        let m = combine(&w, now);
        assert!((m[&1] - 0.39).abs() < 1e-5, "精英加快 × 见切减速相乘：{}", m[&1]);
        assert_eq!(m[&2], 1.2);
        assert!(!m.contains_key(&3));
    }

    #[test]
    fn write_then_restore() {
        let want: HashMap<usize, f32> = [(1, 0.39), (2, 1.2)].into_iter().collect();
        let cur = |a: usize| [1usize, 2, 4].contains(&a).then_some(1.0f32);
        let (mut out, wrote) = plan(&want, &HashMap::new(), &cur);
        out.sort_by(|a, b| a.0.cmp(&b.0));
        assert_eq!(out, vec![(1, 0.39), (2, 1.2)]);
        assert_eq!(wrote.len(), 2);
        // 下一帧没人要了：值还是我们写的 → 改回 1；被别人改过的不碰；不在场的丢掉
        let prev: HashMap<usize, f32> = [(1, 0.39), (2, 1.2), (5, 0.5)].into_iter().collect();
        let cur2 = |a: usize| match a {
            1 => Some(0.39f32),
            2 => Some(0.8f32),
            _ => None,
        };
        let (out2, wrote2) = plan(&HashMap::new(), &prev, &cur2);
        assert_eq!(out2, vec![(1, 1.0)]);
        assert!(wrote2.is_empty());
    }

    #[test]
    fn unit_want_does_not_touch() {
        let want: HashMap<usize, f32> = [(1, 1.0)].into_iter().collect();
        let cur = |_a: usize| Some(0.7f32);
        let (out, wrote) = plan(&want, &HashMap::new(), &cur);
        assert!(out.is_empty() && wrote.is_empty());
    }
}
