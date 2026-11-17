//! 新词条里要 DLL 做的（参数侧：dev\item_system\extract_affixes.py 的 CUSTOM，重随的 rr/affixes.py write_runtime 写 runtime.txt）。
//! 装备 / 护符上挂的是「标记」效果（普通 ~ 传说各一个），这里看玩家身上有哪个标记，按最高的那个稀有度做：
//!   - elegance 优雅：做同一个姿势（动作 80000 + 姿势号 × 10 起的那组）满 hold 秒，记这个姿势一层，持续 dur 秒（同一个姿势再做只刷新时间）；
//!     按层数挂效果（每层一行，效果本身 20 秒，每 5 秒续一次；层数变了先摘旧的）；
//!   - cocktail 鸡尾酒：每 period 秒随机挂一种正面效果（效果本身 period 秒）；
//!   - timeslip 时隙：玩家周围 radius 米内所有角色（不分敌我，含自己和灵马）的动画速度 ×(1 + pct%)：每帧改角色行为模块的 animation_speed，
//!     出了范围 / 摘下护符的，值还是我们设的就改回 1（只碰这一帧列表里的角色，不存指针）。
//!   - deft 巧手：玩家脚本在弩换弹 / 拉弓状态里挂「换弹」脉冲标记，有标记时玩家的动画速度 ×(1 + pct%)（和时隙的倍数相乘）；
//!   - quickcharge 寸劲（原名沉稳；用户 2026-11-05「重蓄霸体的词条改为减少重蓄所需时间传说最高50%每级10%」）：玩家脚本按住重击蓄力时发
//!     「蓄力」脉冲（charging），有脉冲时玩家的动画速度 ×1 / (1 − pct%)（蓄力所需时间减少 pct%；同样和时隙、巧手的倍数相乘）；
//!   - crush 碾压：玩家脚本在翻滚状态里挂「翻滚」脉冲标记。翻滚中，ChrIns_PrePhysicsSafe 任务（pre_physics）每帧清掉玩家的无敌位
//!     （动作事件设的 dodging / perfect_invincibility / pve_only_iframes）；翻滚到原版无敌时间结束那一刻（滚完起身，清之前读动作事件的 dodging；
//!     一直没见到无敌的翻滚在翻滚结束时）按右手武器攻击力 × pct% 挑最接近的一档冲击波（crushtier 行，放子弹的瞬间效果）挂到玩家身上；
//!   - bloodrage 血狂（武器特殊效果，武器上的常驻标记）：玩家脚本在攻击开始 / 受击时挂脉冲标记。每次攻击 +1 层（最多 stacks 层），
//!     扣 层数 × hp% 最大血量（不会扣到 0；已经满层的攻击不扣），挂这一层的增伤效果；受击、reset 秒不攻击、换掉武器就清零。
//! 定义：DLL 旁边的 runtime.txt，每行 <种类> <稀有度 0~3> <标记效果> <效果编号, 逗号分隔> <秒 a> [<秒 b>]
//!   （elegance：a = 满几秒、b = 一层持续几秒；cocktail：a = 间隔秒；timeslip：效果编号那列是加速百分比，a = 半径；
//!    deft / crush / quickcharge：效果编号那列是百分比）；另外 mark <名字> <效果>（脉冲标记）、crushtier <伤害> <效果>、
//!    crushlive <效果> <攻击行>（碾压的实时伤害：放之前把这次的伤害和削韧写进攻击行，用户 2026-11-12「走实时计算伤害的路线」）、
//!    heavypoise <动作类别> <行为变体|-1> <倍率％>（碾压的削韧 = 右手武器重击的削韧 = saWeaponDamage × 倍率，用户 2026-11-12）、
//!   bloodrage <标记> <每层效果, 逗号分隔> <每层扣血 %> <几秒不攻击清零>、hks <名字> <标记, 普通 ~ 传说> <数值>（玩家脚本做的词条）
//!   - leap 飞鸿：玩家脚本起跳时挂计时标记（第 5 列），标记挂着时 pre_physics 每帧设翻滚同款的无敌位 dodging；
//!   - wolf 狼魂（玩家脚本做，这里只写日志）：每次按防御，记下那一刻原版的输入 / 取消窗口、动作、精力，
//!     再看之后 0.4 秒里按住计时和玩家脚本挂的标记（wolf_atk 攻击类状态里调到了 / wolf_van 原版时机防御了 / wolf_try 尝试 / wolf_ok 成功），写一行

use std::collections::HashMap;
use std::fs;
use std::sync::atomic::AtomicUsize;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use eldenring::cs::{AtkParam_Pc, ChrAsmHand, ChrInsExt, EquipParamAccessory, EquipParamProtector, EquipParamWeapon, GameDataMan, ItemCategory, SoloParamRepository, WorldChrMan};
use eldenring::param::EquipParamWearable;
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

const GESTURE_ANIMS: std::ops::Range<i32> = 80000..90000;
/// 致命舞：多久重新算一次装备重量（只在戴着时算）
const LOAD_EVERY: Duration = Duration::from_millis(500);
/// 单独调速的战技：(动作段, 倍数)。动作段 = 600 + SwordArtsParam.swordArtsTypeNew，一种战技独占一段。
/// 雷电羊球（类型 113，a713）×10（用户 2026-11-09「让动作加速10倍」）：判定窗口 0.5 秒，加速后 0.05 秒，60 帧下还有 3 帧，不会被跳过
/// 雷云化身（类型 226，a826）×2（用户 2026-11-09，×10 时判定窗口 0.2 秒只剩 0.02 秒，掉帧会漏段，「那*2就行」）：判定窗口 0.1 秒，60 帧下 6 帧
const SKILL_SPEED: [(i32, f32); 2] = [(713, 10.0), (826, 2.0)];

/// 当前动作（段 × 1000000 + 编号）属于单独调速的战技时的倍数，其余 1
fn skill_speed(anim: Option<i32>) -> f32 {
    let Some(sec) = anim.filter(|&a| a > 0).map(|a| a / 1_000_000) else { return 1.0 };
    SKILL_SPEED.iter().find(|x| x.0 == sec).map_or(1.0, |x| x.1)
}
const REFRESH: Duration = Duration::from_secs(5);

#[derive(Debug, Default, Clone, PartialEq)]
struct Kind {
    marker: [i32; 4],
    sp: [Vec<i32>; 4],
    a: f32,
    b: f32,
}

#[derive(Debug, Default, Clone, PartialEq)]
struct Bloodrage {
    marker: i32,
    stacks: Vec<i32>,
    hp: f32,
    reset: f32,
}

#[derive(Debug, Default, PartialEq)]
struct Def {
    elegance: Option<Kind>,
    cocktail: Option<Kind>,
    timeslip: Option<Kind>,
    deft: Option<Kind>,
    /// 寸劲：蓄力所需时间减少的百分比
    quickcharge: Option<Kind>,
    /// 致命舞（用户 2026-11-06）：装备重量越轻，所有动作越快；「效果编号」那列是空载时的百分比
    loadspeed: Option<Kind>,
    crush: Option<Kind>,
    /// 拾遗：效果编号那列是吸取半径（米），pickup.rs 做
    magnet: Option<Kind>,
    /// 脉冲标记：roll / reload / attack / hit
    marks: HashMap<String, i32>,
    /// 碾压冲击波：(伤害, 效果)
    crush_tiers: Vec<(f32, i32)>,
    /// 碾压的实时伤害：(放冲击波的效果, 它的攻击行)，轮流用；空的就挑 crush_tiers 里最接近的档
    crush_live: Vec<(i32, u32)>,
    /// 武器重击的削韧倍率％：(动作类别, 行为变体；-1 = 这个类别的默认) → 倍率
    heavy_poise: HashMap<(u8, i32), f32>,
    bloodrage: Option<Bloodrage>,
    /// 玩家脚本做的词条
    hks: HashMap<String, HksRun>,
}

#[derive(Debug, Default, Clone, PartialEq)]
struct HksRun {
    marker: [i32; 4],
    vals: Vec<f32>,
    /// 玩家脚本挂的效果（普通 ~ 传说；飞鸿 = 起跳后的计时标记）
    sp: Vec<i32>,
}

impl Def {
    fn mark(&self, name: &str) -> i32 {
        self.marks.get(name).copied().unwrap_or(-1)
    }

    fn any(&self) -> bool {
        self.elegance.is_some() || self.cocktail.is_some() || self.timeslip.is_some() || self.deft.is_some() || self.crush.is_some()
            || self.quickcharge.is_some()
            || self.loadspeed.is_some()
            || self.magnet.is_some()
            || self.bloodrage.is_some() || self.hks.contains_key("wolf") || self.hks.contains_key("overlord")
    }
}

const WOLF_WATCH: Duration = Duration::from_millis(400);
const WOLF_MAX_LINES: u32 = 300;
const RARITY: [&str; 4] = ["普通", "稀有", "史诗", "传说"];

/// 狼魂日志这一帧要看的
#[derive(Debug, Default, Clone, Copy)]
struct WolfIn {
    /// 防御键（ACTION_ARM_L1）：手柄原始输入、按住计时（秒，就是脚本的 ActionDuration）
    l1: bool,
    timer: f32,
    /// 原版这一刻 L1 在不在输入窗口 / 取消窗口里（ActionRequest 只认两个都在的）
    input: bool,
    cancel: bool,
    anim: Option<i32>,
    stamina: i32,
    /// 玩家脚本挂的标记
    atk: bool,
    van: bool,
    try_: bool,
    ok: bool,
}

#[derive(Default)]
struct WolfLog {
    tier: Option<usize>,
    held_last: bool,
    /// 正在看的这次按键：(按下的时间, 按下那一刻, 之后累计：计时取最长、标记取有没有出现过)
    press: Option<(Instant, WolfIn, WolfIn)>,
    lines: u32,
}

/// 碾压：这一帧玩家在翻滚、戴着碾压（tick 设，pre_physics 用）
static CRUSH_ROLLING: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
/// 这一帧玩家要的动作速度（tick 算的；NaN = 不管）：联机时 pre_behavior 在动画更新前补写
static PLAYER_WANT: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0x7FC0_0000);
/// pre_behavior 发现被改过的次数、写过几行日志、上次写统计的时间
static PLAYER_FIX: Mutex<(u64, u32, Option<Instant>)> = Mutex::new((0, 0, None));

/// 玩家自己的动作速度（时隙、巧手、寸劲、致命舞、处刑、转念、战技速度……）真正生效的地方：ChrIns_PreBehavior（动画更新前）。
/// 每帧的顺序是 FrameBegin（tick 算、也写一次）→ 角色网络同步 → 行为前 → 动画更新（HavokBehavior）。玩家的动作速度在帧开头到
/// 动画更新之间会被游戏重算（敌人的不会，写给敌人的能留住），FrameBegin 写的到动画更新时已经没了——用户 2026-11-17「时隙，自己画面不快」，
/// 先以为是联机同步改的，只在会话里补写；单机下戴也不快（「时隙功能还是不正常」）。dark_wings 定住动画也是在这个阶段写，能生效。
/// 单机、联机都在这里写 tick 算好的值（PLAYER_WANT；NaN = 不管，比如飞行中由 dark_wings 管）；第一次和之后每 10 分钟记一行
pub fn pre_behavior() {
    let want = f32::from_bits(PLAYER_WANT.load(std::sync::atomic::Ordering::Relaxed));
    if !want.is_finite() {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else { return };
    let cur = &mut p.chr_ins.modules.behavior.animation_speed;
    if (*cur - want).abs() <= 1e-4 {
        return;
    }
    let was = *cur;
    *cur = want;
    let mut g = PLAYER_FIX.lock().unwrap_or_else(|e| e.into_inner());
    g.0 += 1;
    let now = Instant::now();
    if g.1 == 0 || g.2.is_none_or(|t| now.duration_since(t) >= Duration::from_secs(600)) {
        g.1 += 1;
        g.2 = Some(now);
        log(&format!("玩家动作速度：动画更新前读到 ×{was:.3}，写成 ×{want:.3}（帧开头写的被游戏重算掉了，在这里写才生效；累计 {} 帧）", g.0));
    }
}
/// 碾压：上一帧动作事件给翻滚设的无敌位（pre_physics 清之前读，tick 用来找无敌时间结束的那一刻）
static CRUSH_TAE: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
/// 碾压的冲击波冷却（用户 2026-10-28 定 3 秒，2026-11-01 改 1 秒）；翻滚没有无敌这个代价不受冷却影响
const CRUSH_COOLDOWN: Duration = Duration::from_secs(1);
/// 找 dark_wings 的导出没找到时，隔多久再找一次（它可能晚一点才载入，或者没装）
const WINGS_RETRY: Duration = Duration::from_secs(2);

/// dark_wings（熔炉百相之羽飞行）现在是不是正定住主角的动画：是的话这一帧不写主角的动画速度，免得两边同时写打架
/// （用户 2026-11-12「飞行的时候衣服的裙子会不自然地重复循环扩张」→「先修冲突」）。没装 dark_wings / 找不到导出就当没在飞
fn wings_frozen() -> bool {
    use std::sync::atomic::Ordering::Relaxed;
    use windows::Win32::System::LibraryLoader::{GetModuleHandleW, GetProcAddress};
    use windows::core::{s, w};
    type Frozen = unsafe extern "C" fn() -> u8;
    static FN: AtomicUsize = AtomicUsize::new(0);
    static LAST_TRY: Mutex<Option<Instant>> = Mutex::new(None);
    let mut f = FN.load(Relaxed);
    if f == 0 {
        let mut last = LAST_TRY.lock().unwrap_or_else(|e| e.into_inner());
        if last.is_some_and(|t| t.elapsed() < WINGS_RETRY) {
            return false;
        }
        *last = Some(Instant::now());
        let Ok(m) = (unsafe { GetModuleHandleW(w!("dark_wings.dll")) }) else { return false };
        let Some(p) = (unsafe { GetProcAddress(m, s!("dark_wings_frozen")) }) else { return false };
        f = p as usize;
        FN.store(f, Relaxed);
        log("找到 dark_wings 的 dark_wings_frozen：飞行时不写主角的动画速度");
    }
    unsafe { std::mem::transmute::<usize, Frozen>(f)() != 0 }
}
/// 重击削韧倍率表里查不到（类别也没有默认）时用的倍率％：原版轻量武器的点按重击
const HEAVY_POISE_DEFAULT: f32 = 200.0;

/// 武器重击的削韧 = saWeaponDamage × 倍率％：先按（动作类别, 行为变体）查，再按类别默认，都没有用 HEAVY_POISE_DEFAULT
pub(crate) fn heavy_poise(table: &HashMap<(u8, i32), f32>, cat: u8, bv: i32, sa: f32) -> f32 {
    let pct = table.get(&(cat, bv)).or_else(|| table.get(&(cat, -1))).copied().unwrap_or(HEAVY_POISE_DEFAULT);
    sa.max(0.0) * pct / 100.0
}

/// 右手武器（现在拿着的那格）的重击削韧：(削韧, (动作类别, 行为变体, saWeaponDamage))；碾压、积木引擎的物理冲击波用
pub(crate) fn right_heavy_poise(table: &HashMap<(u8, i32), f32>) -> Option<(f32, (u8, i32, f32))> {
    let gdm = unsafe { GameDataMan::instance() }.ok()?;
    let asm = &gdm.main_player_game_data.equipment.chr_asm;
    let id = asm.equipment_param_ids.get(asm.equipment.active_weapon_slot(ChrAsmHand::Right) as usize).copied().unwrap_or(-1);
    if id <= 0 {
        return None;
    }
    let repo = unsafe { SoloParamRepository::instance() }.ok()?;
    let w = repo.get::<EquipParamWeapon>((id / 100 * 100) as u32)?;
    let (cat, bv, sa) = (w.wepmotion_category(), w.behavior_variation_id(), w.sa_weapon_damage());
    Some((heavy_poise(table, cat, bv, sa), (cat, bv, sa)))
}

/// 实时伤害的专用攻击行：写这次的物理攻击力和削韧；行不在游戏的参数里（不重随的模式）返回 None，否则返回写进去的伤害
pub(crate) fn write_live_atk(atk: u32, dmg: f32, poise: f32) -> Option<f32> {
    let repo = unsafe { SoloParamRepository::instance_mut() }.ok()?;
    let a = repo.get_mut::<AtkParam_Pc>(atk)?;
    let dmg = dmg.round().clamp(1.0, u16::MAX as f32);
    a.set_atk_phys(dmg as u16);
    a.set_atk_super_armor(poise.max(0.0));
    Some(dmg)
}
/// 同一个翻滚动作的播放时间倒回这么多秒以上，算重新从头播（连滚的下一段）
const ROLL_RESTART: f32 = 0.05;

#[derive(Default)]
struct St {
    /// 正在做的姿势：(姿势号, 开始时间, 这次已经记过层)
    gesture: Option<(i32, Instant, bool)>,
    /// 姿势号 → 记层的时间
    stacks: HashMap<i32, Instant>,
    /// 现在挂着的层数效果、上次挂的时间
    applied: Option<(i32, Instant)>,
    next_cocktail: Option<Instant>,
    seed: u64,
    slip_on: bool,
    /// 上一次读到的本体战斗状态（变了写日志）
    combat_last: Option<bool>,
    /// 玩家的动画速度上一帧是不是我们设的（时隙 × 巧手；不是 1 才设，回到 1 时还原一次）
    player_speed: Option<f32>,
    /// 致命舞：下次算装备重量的时间、算出来的倍数（戴着时）、写过日志的百分比
    load_at: Option<Instant>,
    load_mult: f32,
    load_logged: i32,
    /// 上一帧的脉冲标记：翻滚 / 攻击 / 受击（看「刚出现」）
    roll_last: bool,
    /// 翻滚中上一帧的动作和播放时间（连滚：动作换了或重新从头播算新的一段）；碾压上次放冲击波的时间
    roll_anim: Option<(i32, f32)>,
    crush_at: Option<Instant>,
    /// 碾压：这段翻滚还没放冲击波（里面是见没见过动作事件的无敌）；放过 / 不在翻滚是 None
    crush_seg: Option<bool>,
    /// 碾压的实时伤害：下一次用第几套专用行
    crush_live_next: usize,
    attack_last: bool,
    hit_last: bool,
    /// 血狂：层数、上次攻击的时间、挂着的层数效果
    br_n: usize,
    /// 最近一次普通攻击是哪只手（HKS 的 clash_*_l/r；血狂按这个限制武器来源）
    weapon_hand: Option<bool>,
    br_at: Option<Instant>,
    br_sp: Option<i32>,
    wolf: WolfLog,
    overlord: OverlordLog,
}

/// 霸王日志：戴着的稀有度、身上的战技霸体效果 (开始的时间, 效果)、这段霸体里受击几次（玩家脚本挂的受击标记，看「刚出现」）
#[derive(Default)]
struct OverlordLog {
    tier: Option<usize>,
    on: Option<(Instant, i32)>,
    hits: u32,
    hit_last: bool,
}

static DEF: OnceLock<Def> = OnceLock::new();
static ST: Mutex<Option<St>> = Mutex::new(None);

fn parse(text: &str) -> Def {
    let mut d = Def::default();
    for line in text.lines().map(|l| l.trim_start_matches('\u{feff}').trim_end()) {
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let f: Vec<&str> = line.split('\t').collect();
        match (f[0], f.len()) {
            ("mark", 3..) => {
                if let Ok(id) = f[2].parse() {
                    d.marks.insert(f[1].to_string(), id);
                }
                continue;
            }
            ("heavypoise", 4..) => {
                if let (Ok(cat), Ok(bv), Ok(pct)) = (f[1].parse(), f[2].parse(), f[3].parse()) {
                    d.heavy_poise.insert((cat, bv), pct);
                }
                continue;
            }
            ("crushlive", 3..) => {
                if let (Ok(sp), Ok(atk)) = (f[1].parse(), f[2].parse()) {
                    d.crush_live.push((sp, atk));
                }
                continue;
            }
            ("crushtier", 3..) => {
                if let (Ok(dmg), Ok(sp)) = (f[1].parse(), f[2].parse()) {
                    d.crush_tiers.push((dmg, sp));
                }
                continue;
            }
            ("bloodrage", 5..) => {
                let stacks = f[2].split(',').filter_map(|x| x.trim().parse().ok()).collect::<Vec<i32>>();
                if let (Ok(marker), Ok(hp), Ok(reset)) = (f[1].parse(), f[3].parse(), f[4].parse()) {
                    if !stacks.is_empty() {
                        d.bloodrage = Some(Bloodrage { marker, stacks, hp, reset });
                    }
                }
                continue;
            }
            ("hks", 3..) => {
                let m: Vec<i32> = f[2].split(',').filter_map(|x| x.trim().parse().ok()).collect();
                let vals = f.get(3).map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.trim().parse().ok()).collect());
                let sp = f.get(4).map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.trim().parse().ok()).collect());
                if let Ok(marker) = <[i32; 4]>::try_from(m) {
                    d.hks.insert(f[1].to_string(), HksRun { marker, vals, sp });
                }
                continue;
            }
            _ => {}
        }
        if f.len() < 5 {
            continue;
        }
        let slot = match f[0] {
            "elegance" => &mut d.elegance,
            "cocktail" => &mut d.cocktail,
            "timeslip" => &mut d.timeslip,
            "deft" => &mut d.deft,
            "quickcharge" => &mut d.quickcharge,
            "loadspeed" => &mut d.loadspeed,
            "crush" => &mut d.crush,
            "magnet" => &mut d.magnet,
            _ => continue,
        };
        let (Ok(r), Ok(marker)) = (f[1].parse::<usize>(), f[2].parse::<i32>()) else { continue };
        let Some(sp) = f[3].split(',').map(|x| x.trim().parse::<i32>().ok()).collect::<Option<Vec<_>>>() else { continue };
        if r > 3 || sp.is_empty() {
            continue;
        }
        let k = slot.get_or_insert_with(Kind::default);
        k.marker[r] = marker;
        k.sp[r] = sp;
        k.a = f[4].parse().unwrap_or(0.0);
        k.b = f.get(5).and_then(|x| x.parse().ok()).unwrap_or(0.0);
    }
    for slot in [&mut d.elegance, &mut d.cocktail, &mut d.timeslip, &mut d.deft, &mut d.quickcharge, &mut d.loadspeed, &mut d.crush, &mut d.magnet] {
        if slot.as_ref().is_some_and(|k| k.marker.iter().any(|&m| m <= 0) || k.a <= 0.0) {
            *slot = None;
        }
    }
    d
}

fn def() -> &'static Def {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("runtime.txt")).unwrap_or_default()))
}

pub fn describe() -> String {
    let d = def();
    let mut v = Vec::new();
    if let Some(k) = &d.elegance {
        v.push(format!("优雅（肢体动作满 {} 秒一层，{} 秒）", k.a, k.b));
    }
    if let Some(k) = &d.cocktail {
        v.push(format!("鸡尾酒（每 {} 秒）", k.a));
    }
    if let Some(k) = &d.timeslip {
        v.push(format!("时隙（{} 米）", k.a));
    }
    if d.deft.is_some() {
        v.push("巧手".into());
    }
    if d.quickcharge.is_some() {
        v.push("寸劲（蓄力加快）".into());
    }
    if d.loadspeed.is_some() {
        v.push("致命舞（越轻动作越快）".into());
    }
    if d.crush.is_some() {
        v.push(format!("碾压（冲击波 {} 档）", d.crush_tiers.len()));
    }
    if d.magnet.is_some() {
        v.push("拾遗".into());
    }
    if let Some(b) = &d.bloodrage {
        v.push(format!("血狂（{} 层）", b.stacks.len()));
    }
    if d.hks.contains_key("wolf") {
        v.push("狼魂（只写日志）".into());
    }
    if !leap_sp(d).is_empty() {
        v.push("飞鸿（起跳无敌）".into());
    }
    if d.hks.contains_key("overlord") {
        v.push("霸王（只写日志）".into());
    }
    if v.is_empty() { "新词条（没有 runtime.txt，不管）".into() } else { format!("新词条：{}", v.join("、")) }
}

/// 身上有的最高稀有度（0~3）
fn tier(k: &Kind, has: &dyn Fn(i32) -> bool) -> Option<usize> {
    (0..4).rev().find(|&r| has(k.marker[r]))
}

fn next_rand(seed: &mut u64) -> u64 {
    if *seed == 0 {
        *seed = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_nanos() as u64).unwrap_or(1) | 1;
    }
    *seed ^= *seed << 13;
    *seed ^= *seed >> 7;
    *seed ^= *seed << 17;
    *seed
}

// ------------------------------------------------------------------ 本体的「战斗中」
// 菜单里「战斗中不能用」的那一处（ErdTools 的 enable_map_in_combat 改的也是这里）：
//   mov rcx, [rip+全局]   ; 单例指针
//   call 判断函数          ; bool f(单例)，真 = 战斗中
//   test al, al / jne … / cmp [rbx+…], al / jne … / and esi, -2
// 特征码从 call 开始；启动时找一次（找整个代码段要一两秒），之后每帧直接调
const COMBAT_AOB: [Option<u8>; 20] = [
    Some(0xE8), None, None, None, None, Some(0x84), Some(0xC0), Some(0x75), None, Some(0x38),
    Some(0x83), None, None, None, None, Some(0x75), None, Some(0x83), Some(0xE6), Some(0xFE),
];
/// (判断函数, 单例指针所在的地址)
static COMBAT: OnceLock<Option<(usize, usize)>> = OnceLock::new();

fn find_combat() -> Result<(usize, usize), String> {
    let m = crate::gear::aob_scan_unique(&COMBAT_AOB)?;
    unsafe {
        let rel = std::ptr::read_unaligned((m + 1) as *const i32);
        let f = (m + 5).wrapping_add_signed(rel as isize);
        let mov = std::slice::from_raw_parts((m - 7) as *const u8, 3);
        if mov != [0x48, 0x8B, 0x0D] {
            return Err(format!("call 前面不是 mov rcx,[rip+x]（{:02x?}）", mov));
        }
        let disp = std::ptr::read_unaligned((m - 4) as *const i32);
        Ok((f, m.wrapping_add_signed(disp as isize)))
    }
}

/// 启动时（DllMain 的线程里）找本体的战斗判断，返回给日志的一句话
pub fn init() -> String {
    let r = COMBAT.get_or_init(|| match std::panic::catch_unwind(find_combat) {
        Ok(Ok(x)) => Some(x),
        Ok(Err(e)) => {
            log(&format!("本体的战斗判断没找到：{e}（优雅不会记层）"));
            None
        }
        Err(_) => None,
    });
    match r {
        Some(_) => "本体的战斗判断已找到".into(),
        None => "本体的战斗判断没找到".into(),
    }
}

/// 本体判断的「战斗中」；启动时没找到判断函数就是 None
fn in_combat() -> Option<bool> {
    let &(f, g) = COMBAT.get()?.as_ref()?;
    let obj = unsafe { *(g as *const usize) };
    if obj == 0 {
        return Some(false);
    }
    let func: extern "C" fn(usize) -> u8 = unsafe { std::mem::transmute(f) };
    Some(func(obj) != 0)
}

/// 优雅：按当前动作更新层数，返回应该挂的层数效果；combat = 本体判断的「战斗中」，不在战斗中做满也不记层
fn elegance_want(k: &Kind, r: usize, st: &mut St, anim: Option<i32>, now: Instant, combat: bool) -> Option<i32> {
    let g = anim.filter(|a| GESTURE_ANIMS.contains(a)).map(|a| (a - GESTURE_ANIMS.start) / 10);
    st.gesture = match (g, st.gesture) {
        (Some(g), Some((cur, t0, done))) if cur == g => {
            if !done && combat && now.duration_since(t0).as_secs_f32() >= k.a {
                st.stacks.insert(g, now);
                log(&format!("优雅：肢体动作 {g} 满 {} 秒，记一层（现在 {} 层）", k.a, st.stacks.len()));
                Some((g, t0, true))
            } else {
                Some((g, t0, done))
            }
        }
        (Some(g), _) => Some((g, now, false)),
        (None, _) => None,
    };
    st.stacks.retain(|_, t| now.duration_since(*t).as_secs_f32() < k.b);
    let n = st.stacks.len().min(k.sp[r].len());
    (n > 0).then(|| k.sp[r][n - 1])
}

pub fn tick() {
    let d = def();
    if !d.any() {
        return;
    }
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        *g = None;
        CRUSH_ROLLING.store(false, std::sync::atomic::Ordering::Relaxed);
        return;
    };
    let st = g.get_or_insert_with(St::default);
    let now = Instant::now();
    let ids: Vec<i32> = p.chr_ins.special_effect.entries().map(|e| e.param_id).collect();
    let has = |id: i32| ids.contains(&id);
    // 拾遗：戴着的那档的半径交给 pickup.rs（只在变了的时候动手）
    if let Some(k) = &d.magnet {
        crate::pickup::update(tier(k, &has).map(|r| run_num("magnet", k, r)).filter(|&m| m > 0.0));
    }
    let ta = &p.chr_ins.modules.time_act;
    let anim = (!ta.anim_queue.is_empty()).then(|| ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].anim_id);
    let play = (!ta.anim_queue.is_empty()).then(|| ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].play_time);
    // 雷电羊球按住连滚：定时放原版的滚动声（clash.rs）
    crate::clash::ram_tick(anim, now);

    // 优雅
    let want = match &d.elegance {
        Some(k) => match tier(k, &has) {
            Some(r) => {
                let combat = in_combat();
                if combat != st.combat_last {
                    st.combat_last = combat;
                    log(&format!("优雅：本体的战斗状态 → {}", match combat {
                        Some(true) => "战斗中",
                        Some(false) => "不在战斗中",
                        None => "读不到（启动时没找到判断函数，优雅不记层）",
                    }));
                }
                elegance_want(k, r, st, anim, now, combat == Some(true))
            }
            None => {
                st.stacks.clear();
                st.gesture = None;
                None
            }
        },
        None => None,
    };
    let cur = st.applied.map(|x| x.0);
    if want != cur || st.applied.is_some_and(|(_, t)| now.duration_since(t) >= REFRESH) {
        if let Some(old) = cur.filter(|&o| Some(o) != want) {
            p.remove_speffect(old);
        }
        if let Some(w) = want {
            p.apply_speffect(w, false);
        }
        st.applied = want.map(|w| (w, now));
    }

    // 鸡尾酒
    match d.cocktail.as_ref().and_then(|k| tier(k, &has).map(|r| (k, r))) {
        Some((k, r)) => {
            if st.next_cocktail.is_none_or(|t| now >= t) {
                let list = &k.sp[r];
                let pick = list[(next_rand(&mut st.seed) % list.len() as u64) as usize];
                p.apply_speffect(pick, false);
                st.next_cocktail = Some(now + Duration::from_secs_f32(k.a));
            }
        }
        None => st.next_cocktail = None,
    }

    // 时隙（别的角色）；玩家自己的速度在下面和巧手一起算
    let slip = d.timeslip.as_ref().and_then(|k| tier(k, &has).map(|r| 1.0 + run_num("timeslip", k, r) / 100.0));
    // 只在戴着、或刚摘下要还原时才扫周围（以前词条库里有时隙就每帧扫，切存档时距离列表里有已经释放的角色，崩过，见 chrs.rs）
    if let Some(k) = d.timeslip.as_ref().filter(|_| slip.is_some() || st.slip_on) {
        let me = &p.chr_ins as *const _ as usize;
        let client = crate::coop::client();
        // 游戏的距离列表还没就绪（读图中，见 chrs.rs）就先不动；摘下后不再报，speed.rs 过了保持时间自己改回 1
        if let Some(around) = around!(wcm, me) {
            let mut to_host: Vec<u32> = Vec::new();
            for e in &around {
                if e.chr_ins.as_ptr() as usize == me {
                    continue;
                }
                let c = unsafe { e.chr_ins.as_ref() };
                // 玩家角色（队友、入侵者）不改（联机计划 13.2 G8）
                let Some(m) = slip.filter(|_| e.distance <= k.a && !crate::chrs::is_player(c)) else { continue };
                if client {
                    // 客机不写敌人（联机计划 13.2 G2）：范围里有实体编号的报给房主，房主那边乘进去（speed.rs）
                    if c.event_entity_id != 0 {
                        to_host.push(c.event_entity_id);
                    }
                } else {
                    crate::coop::note(crate::coop::Op::Slip(m), c);
                    crate::speed::want(c, "时隙", m, crate::speed::HOLD_FRAME);
                }
            }
            if client {
                crate::link::slip_to_host(&to_host, slip.unwrap_or(1.0));
            }
            if slip.is_some() != st.slip_on {
                st.slip_on = slip.is_some();
                log(&format!("时隙：{}", slip.map_or("摘下，周围的动作速度还原".to_string(), |m| format!("戴上，周围 {} 米 ×{m}", k.a))));
            }
        }
    }
    // 致命舞：只在戴着时读装备重量
    let load = match d.loadspeed.as_ref().and_then(|k| tier(k, &has).map(|r| run_num("loadspeed", k, r))) {
        Some(pct) => {
            if st.load_at.is_none_or(|t| now >= t) {
                st.load_at = Some(now + LOAD_EVERY);
                if let Some((w, max)) = equip_load(unsafe { p.player_game_data.as_ref() }) {
                    st.load_mult = load_speed(pct, w, max);
                    let shown = ((st.load_mult - 1.0) * 100.0).round() as i32;
                    if shown != st.load_logged {
                        st.load_logged = shown;
                        log(&format!("致命舞：装备重量 {w:.1} / {max:.1}，所有动作 +{shown}%"));
                    }
                }
            }
            st.load_mult.max(1.0)
        }
        None => {
            st.load_at = None;
            st.load_logged = 0;
            1.0
        }
    };
    // 玩家的动画速度 = 时隙 × 巧手 × 连射（积木引擎的叠层；后两个只在弩换弹 / 拉弓中）× 寸劲（只在按住重击蓄力中）× 致命舞 × 处刑、转念（积木引擎）；
    // 后三个在处决、被抓时不算（动作和对方同步，变速会对不上；玩家脚本发 sync）
    let reloading = has(d.mark("reload"));
    let deft = d.deft.as_ref().and_then(|k| tier(k, &has).map(|r| 1.0 + run_num("deft", k, r) / 100.0)).filter(|_| reloading);
    let volley = if reloading { crate::rules::reload_mult() } else { 1.0 };
    let charging = has(d.mark("charging"));
    let quick = d.quickcharge.as_ref().and_then(|k| tier(k, &has).map(|r| charge_pct(run_num("quickcharge", k, r)))).filter(|_| charging);
    let action = if has(d.mark("sync")) { 1.0 } else { load * crate::rules::action_mult() };
    let speed = slip.unwrap_or(1.0) * deft.unwrap_or(1.0) * volley * quick.unwrap_or(1.0) * action * skill_speed(anim);
    // 动画更新前真正写进去（pre_behavior）：要的值记下来，不管的时候是 NaN
    PLAYER_WANT.store(if wings_frozen() || ((speed - 1.0).abs() <= 1e-6 && st.player_speed.is_none()) { f32::NAN } else { speed }.to_bits(),
                      std::sync::atomic::Ordering::Relaxed);
    let cur = &mut p.chr_ins.modules.behavior.animation_speed;
    if wings_frozen() {
        // 飞行中 dark_wings 定住了动画：这一帧不写（飞完它写回起飞前的速度，之后这里照常接着管）
    } else if (speed - 1.0).abs() > 1e-6 {
        *cur = speed;
        st.player_speed = Some(speed);
    } else if let Some(old) = st.player_speed.take() {
        if (*cur - old).abs() < 1e-6 {
            *cur = 1.0;
        }
    }

    // 碾压：翻滚中让 pre_physics 清无敌；冲击波放在翻滚中途：原版这段翻滚的无敌时间结束那一刻（滚完起身；用户 2026-10-31：开始就放怪怪的），
    // 一直没见到无敌的段不放（crush_step）。CRUSH_COOLDOWN 内只放一次。
    // 连滚时翻滚脉冲一直不断（用户 2026-10-28：第二段起不触发），所以翻滚中动作换了、或者同一个动作重新从头播，也算新的一段
    let rolling = has(d.mark("roll"));
    let roll_anim = anim.zip(play);
    let new_roll = rolling
        && (!st.roll_last
            || roll_anim.zip(st.roll_anim).is_some_and(|(a, b)| a.0 != b.0 || a.1 + ROLL_RESTART < b.1));
    let roll_play = if rolling && !new_roll { roll_anim } else { st.roll_anim }.map(|a| a.1);
    st.roll_anim = if rolling { roll_anim } else { None };
    let crush = d.crush.as_ref().and_then(|k| tier(k, &has).map(|r| (k, r)));
    CRUSH_ROLLING.store(rolling && crush.is_some(), std::sync::atomic::Ordering::Relaxed);
    let tae = CRUSH_TAE.load(std::sync::atomic::Ordering::Relaxed);
    let fire = crush_step(&mut st.crush_seg, rolling, new_roll, tae, crush.is_some());
    let ready = st.crush_at.is_none_or(|t| now.duration_since(t) >= CRUSH_COOLDOWN);
    if let (Some((k, r)), Some(why), true) = (crush, fire, ready) {
        st.crush_at = Some(now);
        let pgd = unsafe { p.player_game_data.as_ref() };
        let ar = &pgd.attack_rating;
        let slot = pgd.equipment.chr_asm.equipment.selected_slots.right_weapon_slot;
        let atk = [ar.right_armament_primary, ar.right_armament_secondary, ar.right_armament_tertiary][(slot as usize).min(2)];
        let pct = run_num("crush", k, r);
        let want = atk.max(0) as f32 * pct / 100.0;
        // 实时伤害：专用攻击行写这次的伤害和削韧，轮流用（冷却 1 秒，上一颗早打完了）；行不在游戏的参数里（不重随的模式）就退回挑最接近的档。
        // 削韧 = 右手武器重击的削韧（用户 2026-11-12「削韧按照武器的重击作为削韧值」）：武器行的 saWeaponDamage × 重击倍率（heavypoise 表）
        let hp = right_heavy_poise(&d.heavy_poise);
        let (poise, wpn) = (hp.map(|x| x.0), hp.map(|x| x.1));
        let live = (!d.crush_live.is_empty()).then(|| d.crush_live[st.crush_live_next % d.crush_live.len()]).and_then(|(sp, atk_id)| {
            write_live_atk(atk_id, want, poise.unwrap_or(0.0)).map(|dmg| (dmg, sp))
        });
        if live.is_some() {
            st.crush_live_next = st.crush_live_next.wrapping_add(1);
        }
        let pick = live.map(|(dmg, sp)| (dmg, sp, true)).or_else(|| {
            d.crush_tiers.iter().min_by(|a, b| (a.0 - want).abs().total_cmp(&(b.0 - want).abs())).map(|&(dmg, sp)| (dmg, sp, false))
        });
        if let Some((dmg, sp, exact)) = pick {
            // 在空中（滚下台阶等）先排着，落地再放（rules::defer_until_ground，积木引擎落地时放）
            let air = has(d.mark("air"));
            if !crate::rules::defer_until_ground(sp, air) {
                p.apply_speffect(sp, false);
            }
            log(&format!("碾压：翻滚冲击波（{why}，翻滚 {:.2} 秒处；右手攻击力 {atk} × {}% ≈ {want:.0}，{}{}）",
                         roll_play.unwrap_or(0.0), pct,
                         if exact { format!("实时伤害 {dmg:.0}、削韧 {:.1}（右手武器 {:?} 的重击）", poise.unwrap_or(0.0), wpn) } else { format!("用 {dmg} 那档") },
                         if air { "；在空中，落地再放" } else { "" }));
        }
    }
    st.roll_last = rolling;

    // 血狂（武器上的标记）
    if let Some(b) = &d.bloodrage {
        let attack = has(d.mark("light_new"));  // 只有轻击才叠层、扣血、续时间（用户 2026-11-06）
        let hit = has(d.mark("hit"));
        // 普通攻击的左右手提示由 HKS 的 DR_ClashFrame 发出；没有提示时沿用上一只出招的手。
        let left_now = has(d.mark("clash_l_l")) || has(d.mark("clash_h_l")) || has(d.mark("clash_hc_l"));
        let right_now = has(d.mark("clash_l_r")) || has(d.mark("clash_h_r")) || has(d.mark("clash_hc_r"));
        if left_now || right_now {
            st.weapon_hand = if left_now && !right_now { Some(true) } else if right_now && !left_now { Some(false) } else { None };
        }
        let hand = if left_now || right_now { None } else { st.weapon_hand };
        let weapon_has = |left: bool| {
            let pgd = unsafe { p.player_game_data.as_ref() };
            let asm = &pgd.equipment.chr_asm;
            let h = if left { ChrAsmHand::Left } else { ChrAsmHand::Right };
            let slot = asm.equipment.active_weapon_slot(h) as usize;
            let id = asm.equipment_param_ids.get(slot).copied().unwrap_or(-1);
            if id <= 0 { return false; }
            let Ok(repo) = (unsafe { SoloParamRepository::instance() }) else { return false };
            let Some(w) = repo.get::<EquipParamWeapon>((id / 100 * 100) as u32) else { return false };
            [w.resident_sp_effect_id(), w.resident_sp_effect_id1(), w.resident_sp_effect_id2(), w.resident_sp_effect_id3(),
             w.sp_effect_behavior_id0(), w.sp_effect_behavior_id1(), w.sp_effect_behavior_id2()].contains(&b.marker)
        };
        let on = has(b.marker) && if left_now || right_now {
            (left_now && weapon_has(true)) || (right_now && weapon_has(false))
        } else {
            hand.is_some_and(weapon_has)
        };
        let reset = !on || (hit && !st.hit_last) || st.br_at.is_some_and(|t| now.duration_since(t).as_secs_f32() > b.reset);
        if reset && st.br_n > 0 {
            if let Some(old) = st.br_sp.take() {
                p.remove_speffect(old);
            }
            log(&format!("血狂：清零（{} 层；{}）", st.br_n, if !on { "换掉了武器" } else if hit && !st.hit_last { "被击中" } else { "太久没轻击" }));
            st.br_n = 0;
            st.br_at = None;
        }
        if on && attack && !st.attack_last {
            // 已经满层的轻击不扣血（用户 2026-10-31）：叠到满层那一下照扣，之后只续时间
            let full = st.br_n >= b.stacks.len();
            st.br_n = (st.br_n + 1).min(b.stacks.len());
            st.br_at = Some(now);
            if !full {
                let data = &mut p.chr_ins.modules.data;
                let cost = (data.max_hp as f32 * b.hp * st.br_n as f32 / 100.0).round() as i32;
                data.hp = (data.hp - cost).max(1);
            }
            let sp = b.stacks[st.br_n - 1];
            if let Some(old) = st.br_sp.filter(|&o| o != sp) {
                p.remove_speffect(old);
            }
            p.apply_speffect(sp, false);
            st.br_sp = Some(sp);
        }
        st.attack_last = attack;
        st.hit_last = hit;
    }

    // 狼魂（玩家脚本做，这里只写日志）
    if let Some(HksRun { marker: m, vals: cost, .. }) = d.hks.get("wolf") {
        let ar = &p.chr_ins.modules.action_request;
        let i = WolfIn {
            l1: ar.action_requests.l1(),
            timer: ar.action_timers.l1,
            input: ar.possible_action_inputs.l1(),
            cancel: ar.possible_action_cancels.l1(),
            anim,
            stamina: p.chr_ins.modules.data.stamina,
            atk: has(d.mark("wolf_atk")),
            van: has(d.mark("wolf_van")),
            try_: has(d.mark("wolf_try")),
            ok: has(d.mark("wolf_ok")),
        };
        let r = (0..4).rev().find(|&r| has(m[r]));
        for line in wolf_step(&mut st.wolf, r, cost, i, now) {
            log(&line);
        }
    }

    // 霸王（玩家脚本在战技状态里每帧挂霸体效果，这里只写日志）
    if let Some(h) = d.hks.get("overlord") {
        let r = (0..4).rev().find(|&r| has(h.marker[r]));
        let on = h.sp.iter().copied().find(|&s| has(s));
        let hit = has(d.mark("overlord_hit"));
        let fresh_hit = hit && !st.overlord.hit_last;
        for line in overlord_step(&mut st.overlord, r, &h.vals, on, hit, anim, now) {
            log(&line);
        }
        // 一次性霸体用掉了：玩家脚本不再挂，这里马上摘掉剩下的效果（光效、图标、减伤）
        if let (true, Some(sp)) = (fresh_hit, on) {
            p.remove_speffect(sp);
        }
    }
}

/// 霸王日志：戴上 / 摘下（身上的标记）、战技霸体开始 / 结束（身上的霸体效果，没挨打时结束时长含效果本身的 0.3 秒）、
/// 霸体挡下一次硬直（玩家脚本挂的受击标记刚出现；之后这次战技没有霸体）
fn overlord_step(o: &mut OverlordLog, tier: Option<usize>, cut: &[f32], on: Option<i32>, hit: bool, anim: Option<i32>, now: Instant) -> Vec<String> {
    let mut out = Vec::new();
    if tier != o.tier {
        o.tier = tier;
        out.push(match tier {
            Some(r) => format!("霸王：戴上（{}，霸体期间受到的伤害 -{}%）", RARITY[r], cut.get(r).copied().unwrap_or(0.0)),
            None => "霸王：摘下".into(),
        });
    }
    let anim_s = anim.map_or("?".to_string(), |a| a.to_string());
    match (on, o.on) {
        (Some(sp), None) => {
            o.on = Some((now, sp));
            o.hits = 0;
            out.push(format!("霸王：战技霸体开始（效果 {sp}，动作 {anim_s}）"));
        }
        (None, Some((t0, sp))) => {
            o.on = None;
            let how = if o.hits > 0 { "挡下了一次硬直" } else { "没挨打" };
            out.push(format!("霸王：战技霸体结束（{:.1} 秒，效果 {sp}，{how}）", now.duration_since(t0).as_secs_f32()));
        }
        _ => {}
    }
    if hit && !o.hit_last {
        o.hits += 1;
        out.push(format!("霸王：霸体挡下一次硬直（动作 {anim_s}），这次战技的霸体用掉了"));
    }
    o.hit_last = hit;
    out
}

/// 狼魂日志：戴上 / 摘下写一行；每次按防御（原始输入或按住计时从无到有）记下，WOLF_WATCH 后（或又按了一次）写一行
fn wolf_step(w: &mut WolfLog, tier: Option<usize>, cost: &[f32], i: WolfIn, now: Instant) -> Vec<String> {
    let mut out = Vec::new();
    if tier != w.tier {
        w.tier = tier;
        out.push(match tier {
            Some(r) => format!("狼魂：戴上（{}，每次 {} 精力）", RARITY[r], cost.get(r).copied().unwrap_or(0.0)),
            None => "狼魂：摘下".into(),
        });
    }
    if tier.is_none() {
        w.press = None;
        w.held_last = false;
        return out;
    }
    let held = i.l1 || i.timer > 0.0;
    let new_press = held && !w.held_last;
    w.held_last = held;
    if let Some((_, _, acc)) = &mut w.press {
        acc.timer = acc.timer.max(i.timer);
        acc.atk |= i.atk;
        acc.van |= i.van;
        acc.try_ |= i.try_;
        acc.ok |= i.ok;
    }
    if w.press.as_ref().is_some_and(|(t, ..)| new_press || now.duration_since(*t) >= WOLF_WATCH) {
        let (_, at, acc) = w.press.take().unwrap();
        if w.lines < WOLF_MAX_LINES {
            w.lines += 1;
            out.push(wolf_line(&at, &acc, &i));
            if w.lines == WOLF_MAX_LINES {
                out.push(format!("狼魂：按键日志写满 {WOLF_MAX_LINES} 条，后面的不写了（读一次盘重新计数）"));
            }
        }
    }
    if new_press {
        w.press = Some((now, i, i));
    }
    out
}

/// at = 按下那一刻，acc = 之后累计，end = 写日志这一帧
fn wolf_line(at: &WolfIn, acc: &WolfIn, end: &WolfIn) -> String {
    let yn = |b: bool| if b { "是" } else { "否" };
    let anim = |a: Option<i32>| a.map_or("?".to_string(), |x| x.to_string());
    let why = if acc.ok {
        "狼魂生效"
    } else if acc.van {
        "原版的取消时机防御了（不算狼魂）"
    } else if !acc.atk {
        "不在攻击类状态（脚本没调到狼魂，普通防御不用管）"
    } else if acc.timer <= 0.0 {
        "按住计时一直是 0：脚本读不到这次按键"
    } else if acc.try_ {
        "脚本尝试防御但没成功（武器不能防御 / 精力为 0 / …）"
    } else {
        "脚本没尝试：攻击开始前就按着防御，或在原版取消窗口里但原版没防御"
    };
    format!(
        "狼魂：按防御｜动作 {}→{}｜攻击类状态 {}｜原版 输入窗口 {}、取消窗口 {}｜按住计时最长 {:.2} 秒｜脚本 原版取消 {}、尝试 {}、成功 {}｜精力 {}→{}｜{}",
        anim(at.anim), anim(end.anim), yn(acc.atk), yn(at.input), yn(at.cancel), acc.timer,
        yn(acc.van), yn(acc.try_), yn(acc.ok), at.stamina, end.stamina, why
    )
}

/// 飞鸿：玩家脚本起跳时挂的计时标记（普通 ~ 传说）
fn leap_sp(d: &Def) -> &[i32] {
    d.hks.get("leap").map_or(&[], |h| h.sp.as_slice())
}

/// 飞鸿的无敌正在生效：(开始的时间, 帧数, 标记)；只给日志用
static LEAP_ON: Mutex<Option<(Instant, u32, i32)>> = Mutex::new(None);
static WARD_ON: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
/// 这次无敌里骑马时有没有给灵马设过无敌位（只给日志用：每次无敌记一次）
static WARD_HORSE: std::sync::atomic::AtomicU8 = std::sync::atomic::AtomicU8::new(0);

/// ChrIns_PrePhysicsSafe（动作更新完、物理和伤害判定之前）每帧调：
///   - 碾压：玩家在翻滚、戴着碾压，就清掉动作事件设的无敌位（清之前记进 CRUSH_TAE，冲击波等它变回灭）；
///   - 飞鸿：玩家身上有起跳计时标记，就设翻滚同款的无敌位 dodging（TAE ChrActionFlag 8 FLAG_AS_DODGING），放在碾压后面：起跳无敌优先
pub fn pre_physics() {
    let crush = CRUSH_ROLLING.load(std::sync::atomic::Ordering::Relaxed);
    let leap = leap_sp(def());
    let ward = crate::rules::iframes();
    // 影步：积木引擎说翻滚已经过了一半无敌时间，清掉（和碾压一样）
    let cut = crate::rules::CUT_IFRAMES.load(std::sync::atomic::Ordering::Relaxed);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else { return };
    // 见切要知道这一帧真正的翻滚无敌：没人改就是动作事件设的，改了就是改完的（下面最后再记）
    let iframes = &crate::rules::IFRAMES;
    if !crush && !cut && leap.is_empty() && ward.is_empty() {
        iframes.store(p.chr_ins.modules.action_flag.action_modifiers_flags.dodging(), std::sync::atomic::Ordering::Relaxed);
        CRUSH_TAE.store(false, std::sync::atomic::Ordering::Relaxed);
        return;
    }
    let ids: Vec<i32> = p.chr_ins.special_effect.entries().map(|e| e.param_id).collect();
    let jumping = ids.iter().copied().find(|id| leap.contains(id));
    // 积木词条的无敌效果（rules 的 iframe 行，比如喝完灵药后的无敌）
    let warded = ids.iter().copied().find(|id| ward.contains(id));
    let f = &mut p.chr_ins.modules.action_flag.action_modifiers_flags;
    // 碾压的冲击波等原版无敌时间结束：清之前记下动作事件设的（每帧都会重新设）
    CRUSH_TAE.store(crush && f.dodging(), std::sync::atomic::Ordering::Relaxed);
    if crush || cut {
        f.set_dodging(false);
        f.set_perfect_invincibility(false);
        f.set_pve_only_iframes(false);
    }
    if jumping.is_some() || warded.is_some() {
        f.set_dodging(true);
    }
    iframes.store(f.dodging(), std::sync::atomic::Ordering::Relaxed);
    // 骑着灵马时：攻击可能打在灵马身上、不看人物的无敌位，灵马也设上（用户 2026-11-13「无敌没有覆盖到…在马上喝灵药的动画」）
    let ride = &p.chr_ins.modules.ride;
    let horse = (warded.is_some() && ride.is_mounted).then(|| ride.ride_node.pair_anim_node.counter_party.clone());
    if warded.is_some() != WARD_ON.swap(warded.is_some(), std::sync::atomic::Ordering::Relaxed) {
        log(&format!("积木词条的无敌：{}", warded.map_or("结束".to_string(), |sp| format!("开始（效果 {sp}）"))));
        WARD_HORSE.store(0, std::sync::atomic::Ordering::Relaxed);
    }
    let mut on = LEAP_ON.lock().unwrap_or_else(|e| e.into_inner());
    match (jumping, on.as_mut()) {
        (Some(sp), None) => {
            *on = Some((Instant::now(), 1, sp));
            log(&format!("飞鸿：起跳，无敌开始（标记 {sp}）"));
        }
        (Some(_), Some(x)) => x.1 += 1,
        (None, Some(&mut (t0, n, sp))) => {
            *on = None;
            log(&format!("飞鸿：无敌结束（{:.2} 秒、{n} 帧，标记 {sp}）", t0.elapsed().as_secs_f32()));
        }
        (None, None) => {}
    }
    drop(on);
    if let Some(h) = horse {
        let found = match wcm.chr_ins_by_handle_mut(&h) {
            Some(c) => {
                c.modules.action_flag.action_modifiers_flags.set_dodging(true);
                1
            }
            None => 2,
        };
        if WARD_HORSE.swap(found, std::sync::atomic::Ordering::Relaxed) != found {
            log(if found == 1 { "积木词条的无敌：骑马中，灵马也设上无敌" } else { "积木词条的无敌：骑马中，没找到灵马（只有人物无敌）" });
        }
    }
}

/// 碾压：这一帧该不该放冲击波（返回原因，写日志用）。seg = 这段翻滚还没放（里面是见没见过动作事件的无敌），
/// tae = 上一帧动作事件设的无敌位，active = 戴着碾压。见过无敌、无敌没了就放；无敌还没完就换成下一段 / 翻滚结束的，那时放。
/// 一直没见到无敌的那段不放：翻滚动作播完切到起身 / 跑动时翻滚脉冲还要亮一会儿，会被当成新的一段，
/// 以前在脉冲灭时补放，就成了「翻滚完了还放」（2026-11-01 日志：这种段只播了 0~0.15 秒；原版翻滚都有无敌）
fn crush_step(seg: &mut Option<bool>, rolling: bool, new_roll: bool, tae: bool, active: bool) -> Option<&'static str> {
    let mut fire = None;
    if let Some(seen) = *seg {
        if !rolling || new_roll {
            *seg = None;
            fire = seen.then_some("翻滚结束");
        } else if tae {
            *seg = Some(true);
        } else if seen {
            *seg = None;
            fire = Some("无敌结束");
        }
    }
    if new_roll && active {
        *seg = Some(false);
    }
    fire
}

/// 时隙 / 巧手这个稀有度的速度倍数（1 + 百分比；现在只有单元测试用）
#[cfg(test)]
fn slip_mult(k: &Kind, r: usize) -> f32 {
    1.0 + k.sp[r].first().copied().unwrap_or(0) as f32 / 100.0
}

/// 模块这一档的数：词条数值随机的按身上那件生成装备的位置取精确的数（gear::run_val，二期），没有就照这一档的
fn run_num(run: &str, k: &Kind, r: usize) -> f32 {
    crate::gear::run_val(run, r).unwrap_or_else(|| k.sp[r].first().copied().unwrap_or(0) as f32)
}

/// 致命舞：空载 +pct%，满载（及超重）0，中间按重量比例
fn load_speed(pct: f32, weight: f32, max: f32) -> f32 {
    1.0 + pct / 100.0 * (1.0 - (weight / max).clamp(0.0, 1.0))
}

/// 现在的装备重量、装备重量上限：六把武器（升级的等级在编号末两位）、四件防具、护符（含盟约槽）。上限还读不到（读档中）是 None
fn equip_load(pgd: &eldenring::cs::PlayerGameData) -> Option<(f32, f32)> {
    let max = pgd.max_equip_load;
    if max <= 0.0 {
        return None;
    }
    let repo = unsafe { SoloParamRepository::instance() }.ok()?;
    let e = &pgd.equipment.equipment_entries;
    let mut w = 0.0;
    for id in [e.weapon_primary_left, e.weapon_primary_right, e.weapon_secondary_left, e.weapon_secondary_right, e.weapon_tertiary_left, e.weapon_tertiary_right] {
        if matches!(id.category(), ItemCategory::Weapon) {
            let pid = id.param_id();
            w += repo.get::<EquipParamWeapon>(pid - pid % 100).map_or(0.0, |r| r.weight());
        }
    }
    for id in [e.protector_head, e.protector_chest, e.protector_hands, e.protector_legs] {
        if matches!(id.category(), ItemCategory::Protector) {
            w += repo.get::<EquipParamProtector>(id.param_id()).map_or(0.0, |r| r.weight());
        }
    }
    for id in e.accessories.iter().chain(std::iter::once(&e.covenant)).filter_map(|x| x.as_valid()) {
        if matches!(id.category(), ItemCategory::Accessory) {
            w += repo.get::<EquipParamAccessory>(id.param_id()).map_or(0.0, |r| r.weight());
        }
    }
    Some((w, max))
}

/// 寸劲：蓄力所需时间减少 pct% → 动画速度 ×1 / (1 − pct%)（最多减 90%）
#[cfg(test)]
fn charge_mult(k: &Kind, r: usize) -> f32 {
    charge_pct(k.sp[r].first().copied().unwrap_or(0) as f32)
}

/// 寸劲：蓄力时间减少 pct% → 蓄力动作的速度倍率
fn charge_pct(pct: f32) -> f32 {
    1.0 / (1.0 - pct.clamp(0.0, 90.0) / 100.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 雷电羊球的动作段 ×10、雷云化身的 ×2，别的动作不变；没有动作、负数编号不算
    #[test]
    fn skill_speed_by_section() {
        assert_eq!(skill_speed(Some(713_040_000)), 10.0);
        assert_eq!(skill_speed(Some(713_040_015)), 10.0);
        assert_eq!(skill_speed(Some(826_040_000)), 2.0, "雷云化身");
        assert_eq!(skill_speed(Some(826_040_001)), 2.0, "雷云化身的短突刺");
        assert_eq!(skill_speed(Some(712_040_000)), 1.0, "别的战技");
        assert_eq!(skill_speed(Some(20_030_000)), 1.0, "普通攻击");
        assert_eq!(skill_speed(None), 1.0);
        assert_eq!(skill_speed(Some(-1)), 1.0);
    }

    #[test]
    fn load_speed_by_weight() {
        assert!((load_speed(30.0, 0.0, 60.0) - 1.3).abs() < 1e-5, "空载最高");
        assert!((load_speed(30.0, 30.0, 60.0) - 1.15).abs() < 1e-5, "一半重量一半加成");
        assert!((load_speed(30.0, 60.0, 60.0) - 1.0).abs() < 1e-5, "满载不加");
        assert!((load_speed(30.0, 90.0, 60.0) - 1.0).abs() < 1e-5, "超重也不减");
    }

    #[test]
    fn parse_shared_lines() {
        let mut t = String::new();
        for r in 0..4 {
            t += &format!("deft\t{r}\t{}\t{}\t1\ncrush\t{r}\t{}\t{}\t1\n", 300 + r, 15 + r, 400 + r, 30 + r * 10);
        }
        t += "mark\troll\t901\nmark\treload\t902\ncrushtier\t40\t911\ncrushtier\t47\t912\ncrushlive\t913\t7001\ncrushlive\t914\t7002\nbloodrage\t920\t921,922,923\t1\t5\n";
        t += "hks\twolf\t931,932,933,934\t20,14,8,0\nhks\tbad\t1,2\t0\nhks\tleap\t941,943,945,947\t0.2,0.3,0.4,0.5\t942,944,946,948\n";
        let d = parse(&t);
        assert_eq!(d.hks.get("wolf"), Some(&HksRun { marker: [931, 932, 933, 934], vals: vec![20.0, 14.0, 8.0, 0.0], sp: vec![] }));
        assert!(!d.hks.contains_key("bad"), "标记不是 4 个不收");
        assert_eq!(leap_sp(&d), &[942, 944, 946, 948]);
        assert!(leap_sp(&Def::default()).is_empty());
        assert_eq!(d.mark("roll"), 901);
        assert_eq!(d.mark("nope"), -1);
        assert_eq!(d.crush_tiers, vec![(40.0, 911), (47.0, 912)]);
        assert_eq!(d.crush_live, vec![(913, 7001), (914, 7002)]);
        assert_eq!(d.bloodrage, Some(Bloodrage { marker: 920, stacks: vec![921, 922, 923], hp: 1.0, reset: 5.0 }));
        let k = d.deft.as_ref().unwrap();
        assert_eq!(k.marker, [300, 301, 302, 303]);
        assert!((slip_mult(k, 3) - 1.18).abs() < 1e-6);
        assert_eq!(d.crush.as_ref().unwrap().sp[3], vec![60]);
        assert!(d.any());
        // 寸劲：蓄力时间减少 20 / 50% → 速度 ×1.25 / ×2
        let q = parse("quickcharge\t0\t500\t20\t1\nquickcharge\t1\t501\t30\t1\nquickcharge\t2\t502\t40\t1\nquickcharge\t3\t503\t50\t1\n");
        let k = q.quickcharge.as_ref().unwrap();
        assert!((charge_mult(k, 0) - 1.25).abs() < 1e-6 && (charge_mult(k, 3) - 2.0).abs() < 1e-6);
        assert!(q.any());
    }

    /// 碾压的削韧 = 武器重击削韧（用户 2026-11-12）：先按（类别, 变体），再按类别默认，都没有按 200%
    #[test]
    fn heavy_poise_lookup() {
        let d = parse("heavypoise\t23\t200\t200\nheavypoise\t25\t300\t240\nheavypoise\t25\t-1\t240\n");
        assert_eq!(d.heavy_poise.len(), 3);
        assert_eq!(heavy_poise(&d.heavy_poise, 23, 200, 5.0), 10.0, "长剑 5 × 200%");
        assert!((heavy_poise(&d.heavy_poise, 25, 300, 5.5) - 13.2).abs() < 1e-4, "大剑 5.5 × 240%");
        assert!((heavy_poise(&d.heavy_poise, 25, 399, 5.5) - 13.2).abs() < 1e-4, "变体对不上按类别默认");
        assert_eq!(heavy_poise(&d.heavy_poise, 41, 3300, 3.0), 6.0, "类别也没有按 200%");
    }

    #[test]
    fn parse_and_stacks() {
        let d = parse("# x\nelegance\t0\t100\t1,2,3\t1\t20\nelegance\t1\t101\t4,5,6\t1\t20\nelegance\t2\t102\t7\t1\t20\nelegance\t3\t103\t8,9\t1\t20\n\
                       cocktail\t0\t200\t11,12\t10\ncocktail\t1\t201\t13\t10\n");
        let k = d.elegance.clone().unwrap();
        assert_eq!(k.marker, [100, 101, 102, 103]);
        assert_eq!(k.sp[3], vec![8, 9]);
        assert_eq!((k.a, k.b), (1.0, 20.0));
        assert!(d.cocktail.is_none(), "鸡尾酒四个稀有度没写全，不该启用");
        let has = |id: i32| id == 101 || id == 103;
        assert_eq!(tier(&k, &has), Some(3));
        // 姿势 3（动作 80030）做满 1 秒才记一层；换姿势 5 再记一层；没在做姿势不记
        let mut st = St::default();
        let t0 = Instant::now();
        let ms = |x: u64| t0 + Duration::from_millis(x);
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80030), t0, true), None);
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80031), ms(500), true), None);
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80030), ms(1100), true), Some(4));
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80030), ms(1500), true), Some(4), "同一个姿势只算一层");
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80050), ms(1600), true), Some(4));
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80050), ms(2700), true), Some(5));
        assert_eq!(elegance_want(&k, 1, &mut st, Some(1000), ms(3000), true), Some(5));
        assert_eq!(elegance_want(&k, 1, &mut st, None, t0 + Duration::from_secs(22), true), Some(4), "第一层 20 秒后掉");
        assert_eq!(elegance_want(&k, 1, &mut st, None, t0 + Duration::from_secs(23), true), None);
        // 不在战斗中：做满也不记；做着做着进了战斗，进战斗那一刻记
        let mut st = St::default();
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80070), t0, false), None);
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80070), ms(1500), false), None, "不在战斗中不记层");
        assert_eq!(elegance_want(&k, 1, &mut st, Some(80070), ms(1600), true), Some(4));
    }

    #[test]
    fn wolf_log_lines() {
        let cost = [20.0, 14.0, 8.0, 0.0];
        let t0 = Instant::now();
        let ms = |x: u64| t0 + Duration::from_millis(x);
        let mut w = WolfLog::default();
        let idle = WolfIn { anim: Some(1000), stamina: 100, ..Default::default() };
        assert!(wolf_step(&mut w, None, &cost, idle, t0).is_empty(), "没戴不写");
        assert_eq!(wolf_step(&mut w, Some(3), &cost, idle, t0), vec!["狼魂：戴上（传说，每次 0 精力）"]);
        // 攻击中按防御：脚本尝试、成功，0.4 秒后写一行
        let atk = WolfIn { anim: Some(3000010), stamina: 80, atk: true, ..Default::default() };
        assert!(wolf_step(&mut w, Some(3), &cost, atk, ms(10)).is_empty());
        let press = WolfIn { l1: true, ..atk };
        assert!(wolf_step(&mut w, Some(3), &cost, press, ms(20)).is_empty());
        let fired = WolfIn { timer: 0.03, try_: true, ok: true, anim: Some(3001010), ..press };
        assert!(wolf_step(&mut w, Some(3), &cost, fired, ms(50)).is_empty());
        let out = wolf_step(&mut w, Some(3), &cost, WolfIn { timer: 0.4, atk: false, anim: Some(3001010), ..press }, ms(430));
        assert_eq!(out.len(), 1);
        assert!(out[0].contains("动作 3000010→3001010") && out[0].contains("尝试 是、成功 是") && out[0].ends_with("狼魂生效"), "{}", out[0]);
        assert!(out[0].contains("按住计时最长 0.40 秒"), "{}", out[0]);
        // 一直按着不算新按；松开再按、不在攻击里：写「不在攻击类状态」
        assert!(wolf_step(&mut w, Some(3), &cost, WolfIn { timer: 0.5, ..idle }, ms(500)).is_empty());
        assert!(wolf_step(&mut w, Some(3), &cost, idle, ms(600)).is_empty());
        assert!(wolf_step(&mut w, Some(3), &cost, WolfIn { l1: true, ..idle }, ms(700)).is_empty());
        let out = wolf_step(&mut w, Some(3), &cost, WolfIn { l1: true, timer: 0.4, ..idle }, ms(1100));
        assert!(out[0].ends_with("不在攻击类状态（脚本没调到狼魂，普通防御不用管）"), "{}", out[0]);
        // 攻击中按下但计时一直是 0
        assert!(wolf_step(&mut w, Some(3), &cost, atk, ms(1200)).is_empty());
        assert!(wolf_step(&mut w, Some(3), &cost, press, ms(1300)).is_empty());
        let out = wolf_step(&mut w, Some(3), &cost, press, ms(1700));
        assert!(out[0].ends_with("按住计时一直是 0：脚本读不到这次按键"), "{}", out[0]);
        assert_eq!(wolf_step(&mut w, None, &cost, idle, ms(1800)), vec!["狼魂：摘下"]);
    }

    #[test]
    fn overlord_log_lines() {
        let cut = [10.0, 15.0, 20.0, 30.0];
        let t0 = Instant::now();
        let mut o = OverlordLog::default();
        let ms = |x: u64| t0 + Duration::from_millis(x);
        assert!(overlord_step(&mut o, None, &cut, None, false, None, t0).is_empty());
        assert_eq!(overlord_step(&mut o, Some(2), &cut, None, false, None, t0), vec!["霸王：戴上（史诗，霸体期间受到的伤害 -20%）"]);
        assert_eq!(overlord_step(&mut o, Some(2), &cut, Some(77), false, Some(3100000), t0), vec!["霸王：战技霸体开始（效果 77，动作 3100000）"]);
        // 受击标记刚出现写一行（连着几帧只写一次）；效果摘掉后写结束
        assert_eq!(overlord_step(&mut o, Some(2), &cut, Some(77), true, Some(3100000), ms(100)),
                   vec!["霸王：霸体挡下一次硬直（动作 3100000），这次战技的霸体用掉了"]);
        assert!(overlord_step(&mut o, Some(2), &cut, None, true, Some(3100000), ms(116))[0].starts_with("霸王：战技霸体结束（0.1 秒，效果 77，挡下了一次硬直"));
        assert!(overlord_step(&mut o, Some(2), &cut, None, false, None, ms(200)).is_empty());
        // 下一次战技：没挨打
        assert_eq!(overlord_step(&mut o, Some(2), &cut, Some(77), false, None, ms(1000)).len(), 1);
        assert_eq!(overlord_step(&mut o, Some(2), &cut, None, false, None, ms(1500)), vec!["霸王：战技霸体结束（0.5 秒，效果 77，没挨打）"]);
        assert_eq!(overlord_step(&mut o, None, &cut, None, false, None, t0), vec!["霸王：摘下"]);
    }

    #[test]
    fn crush_fires_when_iframes_end() {
        // 一帧：(在翻滚, 新的一段, 上一帧的动作事件无敌)
        let run = |frames: &[(bool, bool, bool)]| {
            let mut seg = None;
            frames.iter().enumerate().filter_map(|(i, &(r, n, t))| crush_step(&mut seg, r, n, t, true).map(|w| (i, w))).collect::<Vec<_>>()
        };
        // 开始那一帧不放（无敌还没读到），无敌几帧后变灭才放，放完这段剩下的不再放
        assert_eq!(run(&[(true, true, false), (true, false, true), (true, false, true), (true, false, false), (true, false, false), (false, false, false)]),
                   vec![(3, "无敌结束")]);
        // 一直没见到无敌的段不放（翻滚完切到别的动作、翻滚脉冲还亮着，被当成新的一段）
        assert!(run(&[(true, true, false), (true, false, false), (false, false, false)]).is_empty());
        // 翻滚无敌结束放一次；翻滚播完切到起身（脉冲还亮着，算新的一段，没有无敌），脉冲灭时不再放
        assert_eq!(run(&[(true, true, false), (true, false, true), (true, false, false), (true, true, false), (true, false, false), (false, false, false)]),
                   vec![(2, "无敌结束")]);
        // 连滚：第一段无敌结束放一次，第二段从头再等它的无敌
        assert_eq!(run(&[(true, true, false), (true, false, true), (true, false, false), (true, true, false), (true, false, true), (true, false, false)]),
                   vec![(2, "无敌结束"), (5, "无敌结束")]);
        // 无敌还没结束就换成下一段：上一段在换的那一帧放
        assert_eq!(run(&[(true, true, false), (true, false, true), (true, true, true)]), vec![(2, "翻滚结束")]);
        // 没戴碾压不开段
        let mut seg = None;
        assert_eq!(crush_step(&mut seg, true, true, false, false), None);
        assert_eq!(seg, None);
    }
}
