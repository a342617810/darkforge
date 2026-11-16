//! 相杀（参数侧 extract_affixes.py 的 dr_clash、rr/affixes.py clash_lines → clash.txt；用户 2026-11-04「做成臂甲词缀和护符 改一下名字叫相杀
//! 设计成轻击或重击的25-75%动画播放阶段时具有相杀效果；现改为固定减伤 60%，不再区分武器、强化、轻重击或左右手」）：
//! 积木引擎按动作进度挂相杀的效果行（轻击 / 重击 × 左手 / 右手武器，rules.rs 的 while prog），这里把这几行受到的伤害
//! 固定为 40%（即减伤 60%），不再区分武器、强化、轻重击或左右手。
//! 不被打断、防御火花在玩家脚本（sc/hks.py DR_DamageLevel，相杀时这一帧挨了打才放火花）；火花效果出现就记一行日志（挡下一次攻击）。
//! 定义 clash.txt：row <效果> <l|r> <倍率>、spark <火花效果>
//! 开发工具（dll\dark_dev「相杀火花测试」，用户 2026-11-04「确实还是一点没播放出来 开发工具加按钮吧」）：clashfx_req.txt 一行一个
//! 「fx <特效> <挂点> <0 身体 / 1 右手武器 / 2 左手武器> <持续|起手>」= 把第一个火花效果的光效行（内存里）改成这样、马上给自己挂上火花效果；
//! 「fx 恢复」= 改回重随写的样子。测试挂的不算「挡下一次攻击」
//! 音效试听（用户 2026-11-04「相杀的音效还没做」）：「se <音效> <持续|起手>」= 把音效放进火花特效的那一格（持续：持续音效 midstSeId，
//! 和持续特效一起放；起手：起手特效也放一份火花、起手音效 initSeId 跟它一起放），另一格的音效清掉；-1 = 不放；马上挂一次。
//! 第一版只写起手音效、起手那格没有特效，一个都不响（用户 2026-11-04「一个音效都没响」）：原版带音效的光效行都是同一格有特效
//! （sfx 类音效，在常驻的 cs_main 库里才稳）。挑好的编号写进 extract_affixes.py 的 CLASH_SPARK_SE
//! 人物类音效（原版防御反击那一声 c 999999984，用户 2026-11-04「就用原版防御反击的声音吧」）光效行放不了 → 事件脚本放（rr/sounds.py、sc/sounds.py）：
//! clash.txt 的 sound <标记> = 火花出现（挡下一次攻击）时点亮它，公共事件在玩家身上放音效、熄灭；stest <标记> <类> <编号> <说明> = 试听候选，
//! 开发工具发「snd <标记>」就点亮那个标记

use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{ChrInsExt, GameDataMan, SoloParamRepository, SpEffectParam, SpEffectVfxParam, WorldChrMan};
use fromsoftware_shared::FromStatic;
use eldenring::param::SP_EFFECT_VFX_PARAM_ST;

use crate::{dir, log};

const SCAN: Duration = Duration::from_millis(250);

#[derive(Debug, Default, PartialEq)]
struct Def {
    /// (效果行, 右手, 倍率)
    rows: Vec<(u32, bool, f32)>,
    /// 防御火花效果
    sparks: Vec<i32>,
    /// 挡下一次攻击时点亮的音效标记（事件脚本放音效）
    sound: Option<u32>,
    /// 试听候选的标记（开发工具出按钮；这里只认标记）
    stests: Vec<u32>,
    /// 见切成立时点亮的音效标记（msound 行，用户 2026-11-12；没有就用相杀的 sound）
    msound: Option<u32>,
    /// 装备工坊（继承 / 重铸 / 超限）成功时点亮的音效标记（usound 行，用户 2026-11-10「加一个原版强化武器的音效」）
    usound: Option<u32>,
    /// 雷电羊球按住连滚：每隔几毫秒、轮流点亮的音效标记（ramsound 行；用户 2026-11-11）
    ram: Option<(u64, Vec<u32>)>,
    /// 见切成立时挂给自己的特效效果（mvfx 行：潜雾猛禽化成羽毛的原版特效，rr/sounds.py；用户 2026-11-13「用A吧」）
    mvfx: Option<i32>,
    /// 见切触发的加速（影步）晚一点单独挂的光晕：词条键 → 光晕效果（hglow 行，rr/sounds.py；用户 2026-11-14 实际触发时光晕不出来）
    hglow: Vec<(String, i32)>,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    for l in text.lines() {
        let f: Vec<&str> = l.trim_start_matches('\u{feff}').split_whitespace().collect();
        if let ["row", sp, hand @ ("l" | "r"), mult] = f.as_slice() {
            if let (Ok(sp), Ok(mult)) = (sp.parse(), mult.parse()) {
                d.rows.push((sp, *hand == "r", mult));
            }
        }
        if let ["spark", sp] = f.as_slice() {
            if let Ok(sp) = sp.parse() {
                d.sparks.push(sp);
            }
        }
        if let ["sound", flag] = f.as_slice() {
            d.sound = flag.parse().ok();
        }
        if let ["msound", flag] = f.as_slice() {
            d.msound = flag.parse().ok();
        }
        if let ["usound", flag] = f.as_slice() {
            d.usound = flag.parse().ok();
        }
        if let ["mvfx", sp] = f.as_slice() {
            d.mvfx = sp.parse().ok().filter(|&x: &i32| x > 0);
        }
        if let ["hglow", key, sp] = f.as_slice() {
            if let Some(sp) = sp.parse().ok().filter(|&x: &i32| x > 0) {
                d.hglow.push((key.to_string(), sp));
            }
        }
        if let ["ramsound", gap, flags] = f.as_slice() {
            let fl: Vec<u32> = flags.split(',').filter_map(|x| x.parse().ok()).collect();
            if let (Ok(gap), false) = (gap.parse::<u64>(), fl.is_empty()) {
                d.ram = Some((gap.max(50), fl));
            }
        }
        if let ["stest", flag, ..] = f.as_slice() {
            if let Ok(flag) = flag.parse() {
                d.stests.push(flag);
            }
        }
    }
    (!d.rows.is_empty()).then_some(d)
}

/// 雷电羊球按住连滚（用户 2026-11-11）：循环那两段动作（a713 的 40010 / 40015）加速了 10 倍，原版音效每秒响十来次，
/// 所以那两段的音效静音了（rr/skillgems.py），这里在循环段里每 gap 毫秒点亮一个 ramsound 标记（轮流），公共事件放原版的滚动声。
/// 刚进循环先等一个间隔（起手那段自己有声音）
const RAM_LOOP: [i32; 2] = [713_040_010, 713_040_015];
static RAM: Mutex<(Option<Instant>, usize)> = Mutex::new((None, 0));

/// 这一帧要不要响、响哪个：（上一次响的时刻 / 进循环的时刻, 轮到第几个）
fn ram_step(looping: bool, last: Option<Instant>, now: Instant, gap: u64) -> (Option<Instant>, bool) {
    match (looping, last) {
        (false, _) => (None, false),
        (true, None) => (Some(now), false),
        (true, Some(t)) if now.duration_since(t).as_millis() as u64 >= gap => (Some(now), true),
        (true, Some(t)) => (Some(t), false),
    }
}

pub fn ram_tick(anim: Option<i32>, now: Instant) {
    let Some((gap, flags)) = def().and_then(|d| d.ram.as_ref()) else { return };
    let mut g = RAM.lock().unwrap_or_else(|e| e.into_inner());
    let looping = anim.is_some_and(|a| RAM_LOOP.contains(&a));
    let (last, fire) = ram_step(looping, g.0, now, *gap);
    g.0 = last;
    if fire {
        crate::gear::flag_set(flags[g.1 % flags.len()], true);
        g.1 = g.1.wrapping_add(1);
    }
}

/// 见切成立：点亮见切的音效标记（msound 行，音效在 settings 的 mikiri_sound；没有这行就用相杀那个 sound），公共事件下一帧在玩家身上放
/// （用户 2026-11-12「见切成功时播放防御反击的音效 和相杀一样」→「有没有更合适一点的音效」；积木引擎 rules.rs 的 tick 调）
pub fn mikiri_sound() {
    if let Some(f) = def().and_then(|d| d.msound.or(d.sound)) {
        crate::gear::flag_set(f, true);
    }
}

/// 见切成立时挂给自己的特效效果（mvfx 行；没有这行就不挂）：rules.rs 的 tick 在放见切音效的同一帧挂
pub fn mikiri_vfx() -> Option<i32> {
    def().and_then(|d| d.mvfx)
}

/// 见切触发的加速晚一点单独挂的光晕（hglow 行：词条键、光晕效果）：rules.rs 的 tick 在加速期间等翻滚结束再挂、加速结束就摘
pub fn late_glows() -> &'static [(String, i32)] {
    def().map(|d| d.hglow.as_slice()).unwrap_or(&[])
}

/// 装备工坊成功：点亮 usound 标记，公共事件下一帧在玩家身上放强化音效（rr/sounds.py；没有 clash.txt / usound 就不响）
pub fn workshop_sound() {
    if let Some(f) = def().and_then(|d| d.usound) {
        crate::gear::flag_set(f, true);
    }
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("clash.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("相杀（{} 行效果固定减伤 60%）", d.rows.len()),
        None => "相杀（没有 clash.txt，不管）".into(),
    }
}

/// 相杀固定受到 40% 伤害，即减伤 60%
const CLASH_DAMAGE_MULT: f32 = 0.4;

struct St {
    next: Instant,
    /// 上一帧身上有火花效果、它还剩几秒（连着挨打时玩家脚本清掉重挂，剩余时间跳回去 = 又挡下一次）；这次进存档挡下的次数
    spark: bool,
    spark_t: f32,
    hits: u32,
    /// 火花测试：隔几帧看一次请求文件；光效行原来的样子（第一次改之前存下）
    fx_wait: u32,
    fx_orig: Option<VfxRow>,
    /// 「效果固定为…」写过了（以前每 0.25 秒写一行，2026-11-09 用户的日志里刷满了）
    told: bool,
}

/// 光效行里火花测试会改的字段
#[derive(Clone, Copy, Debug)]
struct VfxRow {
    midst: i32,
    midst_dmy: i16,
    init: i32,
    init_dmy: i16,
    midst_se: i32,
    init_se: i32,
    ty: u8,
    midst_full: bool,
    init_full: bool,
}

const FX_REQ: &str = "clashfx_req.txt";

static ST: Mutex<Option<St>> = Mutex::new(None);

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St { next: now, spark: false, spark_t: 0.0, hits: 0, fx_wait: 0, fx_orig: None, told: false });
    fx_test(d, st);
    hit_log(d, st);
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(gdm) = (unsafe { GameDataMan::instance() }) else { return };
    let pgd = &gdm.main_player_game_data;
    if pgd.level == 0 {
        return; // 还在主菜单
    }
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    for &(sp, _right, _mult) in &d.rows {
        let Some(s) = repo.get_mut::<SpEffectParam>(sp) else { continue };
        s.set_slash_damage_cut_rate(CLASH_DAMAGE_MULT);
        s.set_blow_damage_cut_rate(CLASH_DAMAGE_MULT);
        s.set_thrust_damage_cut_rate(CLASH_DAMAGE_MULT);
        s.set_neutral_damage_cut_rate(CLASH_DAMAGE_MULT);
        s.set_magic_damage_cut_rate(CLASH_DAMAGE_MULT);
        s.set_fire_damage_cut_rate(CLASH_DAMAGE_MULT);
        s.set_thunder_damage_cut_rate(CLASH_DAMAGE_MULT);
        s.set_dark_damage_cut_rate(CLASH_DAMAGE_MULT);
    }
    if !st.told {
        st.told = true;
        log(&format!("相杀：{} 行效果固定为受到伤害 ×{CLASH_DAMAGE_MULT:.2}（减伤 60%）", d.rows.len()));
    }
}

/// 火花效果刚出现、或者剩余时间跳回去（玩家脚本：相杀时挨了打，清掉重挂）→ 记两行：挡下一次攻击（哪只手、轻击还是重击、
/// 这次受到的伤害倍率（物理））、火花（效果 → 光效行 → 特效、挂点，看参数链通不通，用户 2026-11-04「给火花也加日志」）
fn hit_log(d: &Def, st: &mut St) {
    if d.sparks.is_empty() {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance() }) else { return };
    let Some(p) = wcm.main_player.as_ref() else {
        st.spark = false;
        return;
    };
    let fx = &p.chr_ins.special_effect;
    let spark = fx.entries().find(|e| d.sparks.contains(&e.param_id)).map(|e| (e.param_id, e.removal_timer, e.duration));
    let on = spark.is_some();
    let again = spark.is_some_and(|(_, t, _)| st.spark && t > st.spark_t + 0.05);
    if on && (!st.spark || again) {
        st.hits += 1;
        let row = d.rows.iter().find(|r| fx.entries().any(|e| e.param_id == r.0 as i32));
        let what = match row {
            Some(&(sp, right, _mult)) => {
                let taken = unsafe { SoloParamRepository::instance() }.ok().and_then(|r| r.get::<SpEffectParam>(sp)).map_or(1.0, |s| s.slash_damage_cut_rate());
                format!("{}（效果 {sp}，受到物理伤害 ×{taken:.2}，固定减伤 60%）", if right { "右手" } else { "左手" })
            }
            None => "相杀效果这一帧已经摘了".into(),
        };
        // 那一声：点亮音效标记，公共事件下一帧在玩家身上放、熄灭
        if let Some(f) = d.sound {
            crate::gear::flag_set(f, true);
        }
        log(&format!("相杀：挡下一次攻击，{what}，这次进游戏第 {} 次", st.hits));
        if let Some((sp, t, dur)) = spark {
            log(&format!("相杀火花：{}", spark_text(sp, t, dur)));
        }
    }
    st.spark = on;
    st.spark_t = spark.map_or(0.0, |x| x.1);
}

fn vfx_read(v: &SP_EFFECT_VFX_PARAM_ST) -> VfxRow {
    VfxRow {
        midst: v.midst_sfx_id(),
        midst_dmy: v.midst_dmy_id(),
        init: v.init_sfx_id(),
        init_dmy: v.init_dmy_id(),
        midst_se: v.midst_se_id(),
        init_se: v.init_se_id(),
        ty: v.effect_type(),
        midst_full: v.is_midst_fullbody(),
        init_full: v.is_init_fullbody(),
    }
}

fn vfx_write(v: &mut SP_EFFECT_VFX_PARAM_ST, r: &VfxRow) {
    v.set_midst_sfx_id(r.midst);
    v.set_midst_dmy_id(r.midst_dmy);
    v.set_init_sfx_id(r.init);
    v.set_init_dmy_id(r.init_dmy);
    v.set_midst_se_id(r.midst_se);
    v.set_init_se_id(r.init_se);
    v.set_effect_type(r.ty);
    v.set_is_midst_fullbody(r.midst_full);
    v.set_is_init_fullbody(r.init_full);
}

/// 火花测试的一行请求
#[derive(Debug, PartialEq)]
enum Req {
    /// 改回重随写的样子
    Restore,
    /// 特效 挂点 类型 持续（否则起手）
    Fx(i32, i16, u8, bool),
    /// 音效（-1 = 不放）放进持续特效那格（否则起手那格）
    Se(i32, bool),
    /// 点亮事件脚本放音效的标记（试听）
    Snd(u32),
}

/// 「fx 特效 挂点 类型 持续|起手」「fx 恢复」「se 音效 持续|起手」
fn parse_fx(line: &str) -> Option<Req> {
    let f: Vec<&str> = line.split_whitespace().collect();
    match f.as_slice() {
        ["fx", "恢复"] => Some(Req::Restore),
        ["fx", sfx, dmy, ty, slot @ ("持续" | "起手")] => Some(Req::Fx(sfx.parse().ok()?, dmy.parse().ok()?, ty.parse().ok()?, *slot == "持续")),
        ["se", id, slot @ ("持续" | "起手")] => Some(Req::Se(id.parse().ok()?, *slot == "持续")),
        ["snd", flag] => Some(Req::Snd(flag.parse().ok()?)),
        _ => None,
    }
}

/// 开发工具的火花测试：改第一个火花效果的光效行、给自己挂上火花效果（写日志：改成什么样、挂上没有）
fn fx_test(d: &Def, st: &mut St) {
    st.fx_wait = st.fx_wait.wrapping_add(1);
    if st.fx_wait % 15 != 0 {
        return;
    }
    let req = dir().join(FX_REQ);
    let Ok(text) = fs::read_to_string(&req) else { return };
    let _ = fs::remove_file(&req);
    let Some(&sp) = d.sparks.first() else {
        log("相杀火花测试：clash.txt 里没有火花效果（没开新装备系统或者还没重随）");
        return;
    };
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    let Some(vid) = repo.get::<SpEffectParam>(sp as u32).map(|r| r.vfx_id()) else {
        log(&format!("相杀火花测试：效果行 {sp} 不存在"));
        return;
    };
    let Some(vfx) = repo.get_mut::<SpEffectVfxParam>(vid.max(0) as u32) else {
        log(&format!("相杀火花测试：效果 {sp} 的光效行 {vid} 不存在"));
        return;
    };
    let orig = *st.fx_orig.get_or_insert_with(|| vfx_read(vfx));
    for line in text.lines().map(|l| l.trim_start_matches('\u{feff}').trim()).filter(|l| !l.is_empty() && !l.starts_with('#')) {
        let Some(want) = parse_fx(line) else {
            log(&format!("相杀火花测试：看不懂这一行：{line}"));
            continue;
        };
        if let Req::Snd(f) = want {
            let ok = d.stests.contains(&f) && crate::gear::flag_set(f, true);
            log(&format!("相杀音效试听：{}标记 {f}（事件脚本下一帧在玩家身上放音效）", if ok { "点亮" } else { "没点亮（不是 clash.txt 的试听标记或者还没进存档）" }));
            continue;
        }
        let now = vfx_read(vfx);
        let row = match want {
            Req::Restore => orig,
            Req::Fx(sfx, dmy, ty, midst) => VfxRow {
                midst: if midst { sfx } else { -1 },
                midst_dmy: if midst { dmy } else { -1 },
                init: if midst { -1 } else { sfx },
                init_dmy: if midst { -1 } else { dmy },
                midst_se: now.midst_se,
                init_se: now.init_se,
                ty,
                midst_full: false,
                init_full: false,
            },
            // 持续：跟持续特效（火花）一起放；起手：起手那格也放一份火花（同一个挂点），音效跟它一起放
            Req::Se(se, true) => VfxRow { midst_se: se, init_se: -1, ..now },
            Req::Se(se, false) => {
                let (sfx, dmy) = if now.midst >= 0 { (now.midst, now.midst_dmy) } else { (now.init, now.init_dmy) };
                VfxRow { init: sfx, init_dmy: dmy, init_se: se, midst_se: -1, ..now }
            }
            Req::Snd(_) => continue, // 上面处理过
        };
        vfx_write(vfx, &row);
        let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
        let Some(p) = wcm.main_player.as_mut() else {
            log("相杀火花测试：人物还没生成");
            return;
        };
        let had = p.chr_ins.special_effect.entries().any(|e| e.param_id == sp);
        if had {
            p.remove_speffect(sp);
        }
        p.apply_speffect(sp, false);
        let on = p.chr_ins.special_effect.entries().find(|e| e.param_id == sp).map(|e| e.removal_timer);
        // 测试挂的不算挡下：当成上一帧就有、剩余时间很长（下一帧不会被认成新挂上的）
        st.spark = true;
        st.spark_t = 99.0;
        log(&format!(
            "相杀火花测试：光效 {vid} 改成{}（持续特效 {} 挂点 {} 音效 {}，起手特效 {} 挂点 {} 音效 {}，类型 {}），{}给自己挂效果 {sp}：{}",
            if want == Req::Restore { "原来的样子" } else { "" },
            row.midst, row.midst_dmy, row.midst_se, row.init, row.init_dmy, row.init_se, row.ty,
            if had { "摘掉旧的再" } else { "" },
            on.map_or("没挂上".into(), |t| format!("挂上了（还剩 {t:.2} 秒）"))
        ));
    }
}

/// 火花效果 → 光效行（vfxId）→ 特效编号、挂点、哪只手的武器；链子断在哪一环就写哪一环
fn spark_text(sp: i32, t: f32, dur: f32) -> String {
    let head = format!("效果 {sp} 挂上了（还剩 {t:.2} / {dur:.2} 秒）");
    let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return head + "，参数表还没准备好" };
    let Some(row) = repo.get::<SpEffectParam>(sp as u32) else { return head + "，但效果行不存在" };
    let v = row.vfx_id();
    if v <= 0 {
        return format!("{head}，但效果行没有光效（vfxId {v}），不会出火花");
    }
    let Some(vfx) = repo.get::<SpEffectVfxParam>(v as u32) else { return format!("{head}，但光效行 {v} 不存在，不会出火花") };
    let hand = match vfx.effect_type() {
        1 => "右手武器",
        2 => "左手武器",
        _ => "身体",
    };
    format!("{head} → 光效 {v} → 特效 {}（挂点 {}，{hand}）", vfx.midst_sfx_id(), vfx.midst_dmy_id())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_def() {
        let d = parse("# x\nrow 7210900 r 0.5\nrow 7210901 l 1\nrow x r 1\nrow 7 m 1\nspark 7210902\nspark x\n").unwrap();
        assert_eq!(d.rows, vec![(7210900, true, 0.5), (7210901, false, 1.0)]);
        assert_eq!(d.sparks, vec![7210902]);
        assert_eq!(parse_fx("fx 恢复"), Some(Req::Restore));
        assert_eq!(parse_fx("fx 990040 10300 1 持续"), Some(Req::Fx(990040, 10300, 1, true)));
        assert_eq!(parse_fx("fx 201001 220 0 起手"), Some(Req::Fx(201001, 220, 0, false)));
        assert_eq!(parse_fx("fx 1 2"), None);
        assert_eq!(parse_fx("se 440550 持续"), Some(Req::Se(440550, true)));
        assert_eq!(parse_fx("se -1 起手"), Some(Req::Se(-1, false)));
        assert_eq!(parse_fx("se 440550"), None);
        assert_eq!(parse_fx("se x 持续"), None);
        assert_eq!(parse_fx("snd 93645"), Some(Req::Snd(93645)));
        let d = parse("row 7210900 r 0.5\nsound 93645\nmsound 93650\nusound 93647\nramsound 450 93648,93649\nstest 93645 c 999999984 原版防御反击\nstest 93646 s 440550 x\n").unwrap();
        assert_eq!((d.sound, d.stests.clone(), d.usound, d.msound), (Some(93645), vec![93645, 93646], Some(93647), Some(93650)));
        assert_eq!(d.ram, Some((450, vec![93648, 93649])));
        assert_eq!(d.mvfx, None, "没有 mvfx 行就不挂见切特效");
        assert_eq!(parse("row 7210900 r 0.5\nmvfx 7299130\n").unwrap().mvfx, Some(7299130));
        assert_eq!(parse("row 7210900 r 0.5\nmvfx x\nmvfx -1\n").unwrap().mvfx, None);
        assert!(d.hglow.is_empty(), "没有 hglow 行就照旧");
        let g = parse("row 7210900 r 0.5\nhglow dr_shadowstep 7299138\nhglow dr_x x\nhglow dr_y -1\n").unwrap().hglow;
        assert_eq!(g, vec![("dr_shadowstep".to_string(), 7299138)]);
        // 羊球：进循环先等一个间隔，到点响一下，出循环清掉
        let t0 = Instant::now();
        let ms = |m: u64| t0 + std::time::Duration::from_millis(m);
        assert_eq!(ram_step(true, None, t0, 450), (Some(t0), false));
        assert_eq!(ram_step(true, Some(t0), ms(300), 450), (Some(t0), false));
        assert_eq!(ram_step(true, Some(t0), ms(460), 450), (Some(ms(460)), true));
        assert_eq!(ram_step(false, Some(t0), ms(500), 450), (None, false));
        assert!(parse("# 空\n").is_none());
    }

    #[test]
    fn fixed_60_percent_reduction() {
        assert!((1.0 - CLASH_DAMAGE_MULT - 0.6).abs() < f32::EPSILON);
    }
}
