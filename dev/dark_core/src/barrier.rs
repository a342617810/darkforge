//! 「死亡」以上难度错配时的屏障（用户 2026-11-05「从低难度世界进入高难度世界后在人物周边生成屏障 可以参考原版封印监牢 … 当加载的世界和
//! 玩家难度统一时人物周边屏障消失 错配时都会出现屏障 也不允许传送」）。要不要屏障由 bossmode.rs 定（set_wanted）：Boss 改版按角色难度
//! 自动加载、这次启动加载的世界和读进来的角色难度对不上、又不是联机时才要。
//! - 圆顶：围起来 DOME_DELAY 秒后在圆心直接生成一颗不动、不伤人、很久才消失的子弹 BULLET（orbshot.rs 的 spawn_at，游戏生成子弹的函数），
//!   子弹挂我们的特效 990050（dev\item_system\sfx\barrier_dome.js：原版封印监牢圆顶 806700 缩到半径 10 米 + 圆周上往上飘的光幕 + 地上一圈光）。
//!   子弹行由 rr/bossmods.py 加（只在 auto 模式）；生成失败（读图中）隔 1 秒再试，最多 DOME_TRIES 次。
//!   以前是点亮请求标记让公共事件发子弹（EMEVD 2003:5），三次实测都说明它发不出来：只有公共事件的两次都是「隐形空气墙」，
//!   看得到特效的那次是 dark_core 补放的（用户 2026-11-05「从普通难度切换到死亡难度屏障特效又没显示了」），所以去掉了公共事件。
//! - 墙：每帧物理更新前看人物离圆心多远，超过 RADIUS 就推回边上（只推水平方向；骑着灵马时推灵马）。距离按「地图块里的位置 + 块的格子」
//!   换成的整张地图坐标算：大地图走远时游戏会整体平移物理坐标（world shift），直接存物理坐标的圆心会跟着错位。
//! - 一帧里位置跳了 JUMP 米以上（死了在赐福复活、读图、被传送走）就在新位置重新围起来、重新放圆顶。
//! - 禁止传送：错配期间每帧把 FieldArea 的「允许快速传送的标记」改成 FT_OFF（一个永远不亮的标记），地图上就传送不了；
//!   不要屏障了改回游戏原来的值（游戏换地图时会重写这个值，所以每帧都看）。
//! 开发工具（dll\dark_dev「死亡以上难度屏障测试」）写 barrier_req.txt：开 / 关（不管难度，强制在当前位置围起来）、半径 <米>、圆顶（在当前
//! 位置重新围、重新放圆顶）、查（日志记一行现在的状态）、提示 <键>（马上闪一条 notes 的提示，看文字）。日志开头「难度屏障」。
use std::fs;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use eldenring::cs::{BlockId, ChrIns, FieldArea, PlayerIns, WorldChrMan};
use eldenring::position::HavokPosition;
use fromsoftware_shared::{F32Vector4, FromStatic};

use crate::{dir, log};

/// 永远不亮的标记（dev\event_flags\说明.md：扫过没人引用，我们也从不点亮）
pub const FT_OFF: u32 = 93018;
/// 半径（用户 2026-11-05「屏障缩小到10m」；特效 990050 的光幕、地面圈和缩小的圆顶都是这么大，barrier_dome.js 的 RADIUS）
const RADIUS: f32 = 10.0;
/// 圆顶子弹（Bullet，rr/bossmods.py 的 BARRIER_ID）
const BULLET: i32 = 99806700;
/// 围起来以后多久放圆顶（刚进游戏时还在读图；实测 1.5 秒时放得出来）
const DOME_DELAY: Duration = Duration::from_millis(1000);
/// 生成失败最多试几次（每次隔 1 秒）
const DOME_TRIES: u32 = 5;
/// 一帧里跳这么远算被送走了（死亡复活、读图、传送），在新位置重新围
const JUMP: f32 = 20.0;
const REQ_FILE: &str = "barrier_req.txt";

static WANT: AtomicBool = AtomicBool::new(false);

/// bossmode.rs 每次看完难度调用：要不要屏障
pub fn set_wanted(on: bool) {
    WANT.store(on, Ordering::Relaxed);
}

/// 整张地图坐标：(地图键, x, y, z)。大地图（area 50~88）的块 = 格子，块里的位置加上格子的偏移（格子 256 米，index 每加一级大一倍）；
/// 别的地图（地下城、传说地牢）块里的位置就是它自己的坐标
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct G {
    pub(crate) key: i64,
    pub(crate) x: f32,
    pub(crate) y: f32,
    pub(crate) z: f32,
}

pub(crate) fn global(b: BlockId, x: f32, y: f32, z: f32) -> G {
    let (area, gx, gz, idx) = (b.area() as i64, b.block() as f32, b.region() as f32, b.index() as u32);
    if b.is_overworld() {
        let size = 256.0 * (1u32 << idx.min(4)) as f32;
        G { key: area, x: x + gx * size, y, z: z + gz * size }
    } else {
        G { key: ((area << 24) | ((b.block() as i64) << 16) | ((b.region() as i64) << 8) | idx as i64) + 1_000, x, y, z }
    }
}

fn dist_xz(a: &G, b: &G) -> f32 {
    ((a.x - b.x).powi(2) + (a.z - b.z).powi(2)).sqrt()
}

/// 推回边上要挪的水平距离（在圈里 = None）
fn push_back(anchor: &G, at: &G, r: f32) -> Option<(f32, f32)> {
    let (dx, dz) = (at.x - anchor.x, at.z - anchor.z);
    let d = (dx * dx + dz * dz).sqrt();
    (d > r && d > 1e-3).then(|| {
        let k = r / d - 1.0;
        (dx * k, dz * k)
    })
}

#[derive(Default)]
struct St {
    n: u32,
    anchor: Option<G>,
    last: Option<G>,
    /// 改之前游戏的「允许快速传送的标记」
    ft_saved: Option<i32>,
    /// 开发工具：不管难度强制围起来 / 半径
    force: bool,
    radius: Option<f32>,
    pushes: u32,
    /// 什么时候看圆顶子弹在不在、圆心的物理坐标（补放用）
    dome_check: Option<(Instant, [f32; 3], u32)>,
}


static ST: Mutex<Option<St>> = Mutex::new(None);

fn moved(c: &mut ChrIns, dx: f32, dz: f32) {
    let m = &mut c.modules;
    let p = m.physics.position;
    m.physics.position = HavokPosition(p.0 + dx, p.1, p.2 + dz, p.3);
    m.physics.chr_proxy_pos_update_requested = true;
    m.behavior.root_motion = F32Vector4(0.0, 0.0, 0.0, 0.0);
    m.physics.root_motion = F32Vector4(0.0, 0.0, 0.0, 0.0);
}

fn where_is(p: &PlayerIns) -> G {
    let b = p.block_position;
    global(p.current_block_id, b.x, b.y, b.z)
}

/// 允许快速传送的标记：要屏障时改成 FT_OFF，不要了改回去
fn fast_travel(st: &mut St, block: bool) {
    let Ok(fa) = (unsafe { FieldArea::instance_mut() }) else { return };
    let cur = fa.enable_fast_travel_event_flag;
    if block {
        if cur != FT_OFF as i32 {
            if st.ft_saved.is_none() {
                log(&format!("难度屏障：禁止传送（允许传送的标记 {cur} → {FT_OFF}）"));
            }
            st.ft_saved = Some(cur);
            fa.enable_fast_travel_event_flag = FT_OFF as i32;
        }
    } else if let Some(old) = st.ft_saved.take() {
        if cur == FT_OFF as i32 {
            fa.enable_fast_travel_event_flag = old;
        }
        log(&format!("难度屏障：恢复传送（允许传送的标记改回 {old}）"));
    }
}

fn dev(st: &mut St) {
    let path = dir().join(REQ_FILE);
    let Ok(t) = fs::read_to_string(&path) else { return };
    let _ = fs::remove_file(&path);
    for l in t.lines().map(|l| l.trim_start_matches('\u{feff}').trim()).filter(|l| !l.is_empty()) {
        // 看提示文字：「提示 boss on」= 马上排一条 notes 的这个键
        if let Some(k) = l.strip_prefix("提示 ") {
            let ok = crate::notes::push(k.trim());
            log(&format!("难度屏障（开发工具）：试提示「{}」{}", k.trim(), if ok { "" } else { "（notes.txt 里没有，这次不是 auto 模式启动的？）" }));
            continue;
        }
        let mut it = l.split_whitespace();
        match (it.next(), it.next()) {
            (Some("开"), _) => {
                st.force = true;
                st.anchor = None;
                log("难度屏障（开发工具）：强制打开，在现在的位置围起来");
            }
            (Some("关"), _) => {
                st.force = false;
                log(&format!("难度屏障（开发工具）：不强制了（难度错配要的还是会有：{}）", WANT.load(Ordering::Relaxed)));
            }
            (Some("半径"), Some(v)) => match v.parse::<f32>() {
                Ok(r) if r >= 1.0 => {
                    st.radius = Some(r);
                    log(&format!("难度屏障（开发工具）：推回的半径 {r} 米（特效还是 {RADIUS} 米那么大）"));
                }
                _ => log(&format!("难度屏障（开发工具）：半径「{v}」不对")),
            },
            (Some("圆顶"), _) => {
                st.anchor = None;
                log("难度屏障（开发工具）：在现在的位置重新围、重新放圆顶");
            }
            (Some("查"), _) => {
                let fa = unsafe { FieldArea::instance() }.ok().map(|f| f.enable_fast_travel_event_flag);
                let at = unsafe { WorldChrMan::instance() }.ok().and_then(|w| w.main_player.as_ref().map(|p| {
                    let h = p.chr_ins.modules.physics.position;
                    format!("块 {} 块里 ({:.1}, {:.1}, {:.1}) 物理 ({:.1}, {:.1}, {:.1}) 骑马 {}", p.current_block_id, p.block_position.x, p.block_position.y,
                            p.block_position.z, h.0, h.1, h.2, p.chr_ins.modules.ride.is_mounted)
                }));
                let off = match (&st.anchor, unsafe { WorldChrMan::instance() }.ok().and_then(|w| w.main_player.as_ref().map(|p| where_is(p)))) {
                    (Some(a), Some(g)) if a.key == g.key => format!("{:.1} 米", dist_xz(a, &g)),
                    _ => "—".into(),
                };
                log(&format!("难度屏障（开发工具）：要屏障 {}（强制 {}），圆心 {:?}，离圆心 {off}，半径 {}，允许传送的标记 {:?}（改前 {:?}），圆顶{}，推回过 {} 次；{}",
                             WANT.load(Ordering::Relaxed), st.force, st.anchor, st.radius.unwrap_or(RADIUS), fa, st.ft_saved,
                             if st.dome_check.is_some() { "还没放" } else { "放过了" }, st.pushes,
                             at.unwrap_or_else(|| "没有角色".into())));
            }
            _ => log(&format!("难度屏障（开发工具）：看不懂「{l}」（开 / 关 / 半径 <米> / 圆顶 / 查）")),
        }
    }
}

/// 每帧（物理更新前）
pub fn tick() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    st.n = st.n.wrapping_add(1);
    if st.n % 30 == 0 {
        dev(st);
    }
    let want = WANT.load(Ordering::Relaxed) || st.force;
    if !want {
        if st.anchor.take().is_some() {
            log("难度屏障：撤掉（难度对上了）");
        }
        st.last = None;
        fast_travel(st, false);
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        st.anchor = None;
        st.last = None;
        return;
    };
    fast_travel(st, true);
    let at = where_is(p);
    let jumped = match (&st.anchor, &st.last) {
        (Some(a), Some(l)) => a.key != at.key || l.key != at.key || dist_xz(l, &at) > JUMP || (l.y - at.y).abs() > JUMP,
        _ => true,
    };
    if jumped {
        log(&format!("难度屏障：在 {}（块里 {:.1}, {:.1}, {:.1}）围起来，半径 {} 米，{:.1} 秒后放圆顶", p.current_block_id, p.block_position.x,
                     p.block_position.y, p.block_position.z, st.radius.unwrap_or(RADIUS), DOME_DELAY.as_secs_f32()));
        st.anchor = Some(at);
        let h = p.chr_ins.modules.physics.position;
        st.dome_check = Some((Instant::now() + DOME_DELAY, [h.0, h.1, h.2], 0));
    }
    // 在圆心放圆顶（物理坐标：刚围起来时人物的位置）
    if let Some((t, pos, tries)) = st.dome_check {
        if Instant::now() >= t {
            match crate::orbshot::spawn_at(&p.chr_ins, BULLET, pos) {
                Ok(()) => {
                    st.dome_check = None;
                    log(&format!("难度屏障：放了圆顶（第 {} 次试）", tries + 1));
                }
                Err(e) if tries + 1 < DOME_TRIES => {
                    st.dome_check = Some((Instant::now() + Duration::from_secs(1), pos, tries + 1));
                    log(&format!("难度屏障：放圆顶失败（{e}），1 秒后再试"));
                }
                Err(e) => {
                    st.dome_check = None;
                    log(&format!("难度屏障：放圆顶失败（{e}），试了 {DOME_TRIES} 次，不放了（推回和禁止传送照样有）"));
                }
            }
        }
    }
    st.last = Some(at);
    let Some(a) = st.anchor else { return };
    let Some((dx, dz)) = push_back(&a, &at, st.radius.unwrap_or(RADIUS)) else { return };
    st.pushes = st.pushes.wrapping_add(1);
    st.last = Some(G { x: at.x + dx, z: at.z + dz, ..at });
    // 骑着灵马：推灵马（人跟着马走）；找不到马就推人
    let ride = &p.chr_ins.modules.ride;
    let horse = ride.is_mounted.then(|| ride.ride_node.pair_anim_node.counter_party.clone());
    if let Some(h) = horse {
        if let Some(c) = wcm.chr_ins_by_handle_mut(&h) {
            moved(c, dx, dz);
            return;
        }
    }
    if let Some(p) = wcm.main_player.as_mut() {
        moved(&mut p.chr_ins, dx, dz);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overworld_tiles_join_up() {
        // 同一个点从两个相邻格子看（格子 256 米）：整张地图坐标一样
        let a = global(BlockId::from_parts(60, 42, 37, 0), 130.0, 5.0, 10.0);
        let b = global(BlockId::from_parts(60, 43, 37, 0), -126.0, 5.0, 10.0);
        assert_eq!(a, b);
        // 地下城：块不同就是不同的地图
        let c = global(BlockId::from_parts(10, 0, 0, 0), 1.0, 2.0, 3.0);
        let d = global(BlockId::from_parts(11, 0, 0, 0), 1.0, 2.0, 3.0);
        assert_ne!(c.key, d.key);
        assert_ne!(c.key, a.key);
    }

    #[test]
    fn push_back_to_the_edge() {
        let a = G { key: 60, x: 0.0, y: 0.0, z: 0.0 };
        assert_eq!(push_back(&a, &G { x: 10.0, ..a }, 30.0), None);
        let (dx, dz) = push_back(&a, &G { x: 40.0, z: 0.0, ..a }, 30.0).unwrap();
        assert!((dx + 10.0).abs() < 1e-4 && dz.abs() < 1e-4);
        let (dx, dz) = push_back(&a, &G { x: 30.0, z: 40.0, ..a }, 30.0).unwrap();
        assert!(((30.0 + dx) - 18.0).abs() < 1e-3 && ((40.0 + dz) - 24.0).abs() < 1e-3);
    }
}
