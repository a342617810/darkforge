//! 积木引擎（dev\item_system\bd设计.md 6.5）：积木词条（extract_affixes.py 的 RULE_AFFIXES）照 runtime.txt 的规则做，不再按词条写专用代码。
//! 输入：玩家身上的效果——词条标记（→ 戴着的稀有度）、事件的脉冲标记（玩家脚本 sc/hks.py 的 DR_Event 挂）——和当前动作编号。
//! 定义行（重随 rr/affixes.py runtime_parts 写）：
//!   mark <事件> <脉冲标记>；aff <词条键> <标记 普通~传说（不出的稀有度 -1）>；rule <词条键> <类型> <参数=值>…（按稀有度的值逗号分隔）
//! 规则类型：
//!   - while [cond=<事件>] [unless=<事件>] [hp_below=百分比] [hp_above=百分比] [stack=<词条> min=<层>] [effect=<各稀有度效果>] [fp_to_hp=<各稀有度百分比>]：
//!     条件成立（持续状态的事件在、unless 的事件不在、血量低于 hp_below 且不低于 hp_above、那条词条的叠层至少 min 层（上一帧的）；不写就是一直成立）就一直挂效果，不在就摘；fp_to_hp：专注一直补满，掉了多少按百分比扣血（刚戴上那一帧只补不扣）。
//!     stamina_to_hp=<各稀有度：一整管精力折最大血量的百分比>（燃血）：条件成立时掉的精力补回来，按「掉的 ÷ 精力上限 × 百分比 × 最大血量」扣血，
//!     可以扣到死（Act::HpCost）；同一帧几条都成立只算一次。hp_flat=<各稀有度点数>（血瓮）：按基础血量上限挑最接近的 bursttier hpmax 档
//!     （血量上限 +百分比的效果）挂上，等于加这么多点血量上限。
//!     （while / stack 的效果都是不限时的，引擎每帧对照该挂的和身上实际有的，见 Engine::step）
//!     [prog=下限,上限]：另外要求人物当前动作播到这一段（0~1，播放时间 ÷ 动作长度）；[prog_from=<事件>]：这一段从这个事件在这个动作里
//!     第一次出现时算起（满蓄力的重击：蓄力段过完才算出手，相杀用，用户 2026-11-04）；
//!     [hit=提前,延后]：改按当前动作的攻击判定算（秒，hitwin.txt 里这个动作第一个判定开始前「提前」秒到最后一个判定结束后「延后」秒；
//!     用户 2026-11-04「那就按照攻击判定算」：后摇、连击时被下一刀切掉的部分不算）；表里没有这个动作才退回 prog（没写 prog 就不开）
//!   - hitwin <动作编号> <判定开始> <判定结束>（hitwin.txt，重随 rr/affixes.py hitwin_lines，数据 dev/item_system/build_hit_windows.py）
//!   - on event=<事件> [when=end] [cond=<事件>] [hp_below=百分比] [cooldown=秒（一个，或各稀有度四个）] [fp= / stamina= / hp= / hp_pct= / fp_pct=<各稀有度加减>] [effect=<各稀有度效果>]
//!     [deny_heal=秒]：事件刚发生（when=end：刚结束）、cond 的状态在时做一次；hp_pct / fp_pct 是最大值的百分比；
//!     deny_heal：之后这么多秒里回的血（不算引擎自己回的）全部扣回去（血债：红瓶不回血）；
//!     every=秒：不看事件，每隔这么久做一次（take 拿不到层就等到有为止）；
//!     冲击波：burst=<右手武器攻击力的百分比> 或 burst_flat=<固定伤害>（× 拿走的层数），burst_kind=<哪套档位，默认 phys>；
//!       burst_each=1：每层单独放一次（一颗接一颗，间隔 BURST_GAP；法球射辉石魔砾），每次挑最接近「每层伤害」的那档；
//!       burst_spell=1：固定伤害再乘拿着的法器的法术补正面板 ÷ 200（法球，spellbase.rs）；
//!       burst_grow=<百分比>：每层再乘 1 + 百分比 × 拿走的层数（迸发：一次射出的越多每颗越痛，用户 2026-11-05「按C吧」）；
//!       grow_held=1：burst_grow 改按拿走之前身上有几层算（星群一次只射一颗，按身边有几颗算，用户 2026-11-06）；
//!       take_full=1：take 的那条叠层满了才做（拿走全部），做了的这一帧那条叠层不再加层（迸发：法球满了，下一次施法全部射出）；
//!       take_fresh=1：只认叠层加上之后才开始的动作里的命中（积蓄：翻滚 / 跳跃 / 蹲下后新出的招）；翻滚、后撤步中的命中，
//!       之前出的招晚到的命中都不算，层数留着（用户 2026-11-05：翻滚时莫名附加了异常）；
//!     take=<词条> 拿走它的叠层（take_max=最多拿几层，默认全部），没有层就整条不做；
//!   - stack add=<事件,…> [clear=…] [consume=…] max=<层> [timeout=秒] fx0~fx3=<各稀有度每层的效果> [stamina= / hp=] [log=名字]：
//!     add 加一层（同时扣 stamina / hp）；clear 清零；consume 等当前动作做完再清零（发生后 CONSUME_SETTLE 内跟着动作编号走，
//!     之后动作编号一变就算这一下做完了，这一击能吃到加成）；timeout 秒没加层清零（等着消耗时不算）；按层数挂 fx；
//!     max_boost_key=<词条> max_boost=<层（按那条词条戴着的稀有度，逗号分隔）>：戴着那条词条时上限再加；cond=<事件>：这个状态在时 add 才算。
//! 内置的状态：ground（站在地上）/ air（在空中）：玩家脚本在空中时每帧发 air 的脉冲（有 air 标记时，没收到就算 ground）；
//!   没有 air 标记（旧的定义）才退回物理模块的「站在 / 碰到地面」（在空中也常是真，不可靠）。
//! 内置的事件 mikiri（见切）：翻滚 / 后撤步的无敌帧内，有敌人的攻击正好落在身上（mikiri_reason），一次翻滚最多一次。
//!   原版的翻滚无敌是把受击体挪到攻击查不到的碰撞层，被躲掉的攻击不会产生命中（诊断实测过），所以是近似：
//!   子弹按真实位置（离玩家 ≤ 子弹命中半径 + MIKIRI_BODY）；近战看敌人这一刻的攻击判定在不在（foewin.txt：这个模型这个动作的
//!   攻击行为时间段，前后不留余量；用户 2026-11-11「见切的判定时间有点过于宽松了」→「用出招判定帧」→「见切前后不用留了」），
//!   再看面朝玩家（夹角 ≤ MIKIRI_ARC）、离玩家 ≤ MIKIRI_REACH + 敌人体型半径；同一个敌人的同一招只算一次。
//!   表里没有这个模型（变体退到个位、十位清零的基础模型也没有）才用以前的近似：动作 3000~3999、进度在 MIKIRI_PROGRESS。
//!   - foewin <模型号> <动作编号> <开始,结束[;开始,结束…]>（foewin.txt，重随 rr/affixes.py foewin_lines，数据 dev/item_system/build_foe_windows.py）
//!   戴着见切类词条时，没成立的翻滚也写一行（RollDbg：这次翻滚的无敌帧数、最近一个出招敌人的动作 / 进度 / 距离 / 夹角，正反两种朝向都写），方便调阈值。
//! on 的 foe_slow=<百分比> foe_radius=米 foe_secs=秒 [freeze_key=<词条> freeze_secs=秒]：周围敌人的动作速度降低（戴着 freeze_key 改成停住）；
//! on 的 rest=秒：做完以后，触发它的事件挡住一段时间——从效果（减速 / 停住）结束时起算（见切：减速结束后 5 秒内不会再见切）；
//! while 的 layer_speed=百分比：条件成立时玩家动作速度 × (1 + 百分比 × stack 那条词条的层数)（星群：施法中每颗法球加快施法）。
//! while 的 cut_after=秒：条件连续成立这么久以后清掉玩家的无敌位（影步：翻滚无敌减半，runtime::pre_physics 清）。on 的 stamina_back=<百分比>：这一帧掉的精力按百分比补回来。
//! on 的 guard_scale=<倍数> short_hp=<百分比>（不动如山）：标记效果让引擎防御时只扣 1/guard_scale 的精力（不会自己判破防），
//!   这里按「掉的 × guard_scale」算真正的消耗、补扣剩下的；精力不够的部分改扣 short_hp% 的血。精力见底时引擎量不出来，
//!   用 GUARD_COST_KEEP 内最近一次量到的消耗估（没有就按最大精力的 GUARD_COST_DEFAULT%）。
//!   - rally event=<事件> window=<秒> pct=<百分比> [effect=<窗口期的效果>] [flash=<每次回血挂的效果>] [boost_key=<词条> boost=倍数] [log=名字]：
//!     受伤（受击事件 hit 前后 HIT_LINK 内掉的血）后 window 秒内，每次事件回 这段时间损失的 pct%（最多回满损失的部分；戴着 boost_key 再 ×boost）。
//!   - free fp=<各稀有度专注值>（无尽箭袋）：戴着、专注够时打开游戏的调试开关「所有箭矢不消耗」；新的一次射击 / 投掷（玩家脚本的 shot_new / throw_new）
//!     扣 fp，付过的这一下（shot / throw 的脉冲还在，最多 FREE_HOLD）专注掉到不够也不消耗；投掷道具只在付过的投掷动作里打开「玩家道具不消耗」
//!     （别的时候红瓶之类照常消耗）。tick 照 Engine::free 开关（set_free）。2026-10-29 以前是数背包返还，连着射 / 投和用掉最后一个时返还不了。
//! 其他行：crushtier <伤害> <放冲击波的效果>（物理那套，碾压 / 反震共用）；bursttier <哪套> <伤害> <效果> [子弹]（别的属性，比如法球的魔力；
//! 带子弹编号的可以不挂效果、直接从法器的点位射出：orbshot <右手点位> <左手点位> 行打开，见 orbshot.rs）；iframe <效果>（身上有就设翻滚同款的无敌位，runtime::pre_physics）。
//! 目标层（周围 FOE_RANGE 米内的角色，tick 读：发作中的异常、最大血量、位置、这一帧有没有被打中）：
//!   - foe_aura range= fx0~fx3=<按异常种数的效果>：每 0.5 秒给范围内每个敌人挂「身上发作中的异常有几种就第几个」的效果（狂乱共鸣）；
//!   - foe_react when=<异常> need=<异常> pct= [remove=1]：敌人身上新发作 when、身上已有 need 时，追加 when 一跳伤害的 pct%，remove 摘掉 need（碎冰）；
//!   - foe_spread range= amount= kinds=<异常,…>：敌人新发作这些异常时，给它周围 range 米内的其他敌人挂 amount 点同种累积（连锁）；
//!   - on event=land 的 target_has=<异常,…>（被打中的敌人身上要有；sleep 按「这一下打中之前在睡」算，见 Foe::slept / track_sleep）/
//!     target_remove=1（摘掉它们）/ target_settle=<百分比>（剩下的伤害一次结算）/
//!     target_buildup=<点数> [buildup_kinds=…]（随机一种异常的累积）/
//!     target_hp_pct=<百分比> [target_nth=N target_nth_pct=<百分比>] [target_cap=<右手武器攻击力的百分比>] [target_reset=秒]
//!     （巨人杀手：按它的最大血量扣血，同一个敌人每第 N 下再加；挑最接近的 hp 档，同一档 TIER_BUSY 内不重复挂给同一个敌人）。
//!   伤害用 bursttier hp 那套（挂给敌人的扣血效果），累积用 buildup <异常> <点数> <效果> 行（照原版武器的异常效果复制）。
//! 事件 land（命中）不是玩家身上的标记：命中时触发的效果把 land 的标记挂到被打的角色身上，tick 扫周围角色，有新挂上的就算发生一次（目标层）。
//! 看不懂的规则写一行日志跳过。Engine::step 是纯逻辑（有单元测试），tick 把玩家身上的东西读进来、把动作做到玩家身上。

use std::collections::{HashMap, HashSet, VecDeque};
use std::fs;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use eldenring::cs::{CSBulletManager, ChrAsmArmStyle, ChrAsmHand, ChrIns, ChrInsExt, EquipParamWeapon, FieldInsHandle, SoloParamRepository, SpEffectParam, WorldChrMan, WorldChrManDbgFlags};
use eldenring::param::EquipParamWearable;
use fromsoftware_shared::FromStatic;

use crate::{dir, log};

const CONSUME_SETTLE: Duration = Duration::from_millis(150);
const CONSUME_MAX: Duration = Duration::from_secs(4);
/// 掉血和受击事件（玩家脚本的 hit）相差这么久以内，才算受伤（自己扣的血、毒之类不算）
const HIT_LINK: Duration = Duration::from_millis(300);
/// on 的 stamina_back / guard_scale 算「这一下掉了多少精力」时往前看几帧
const STAMINA_LOOKBACK: usize = 3;
/// guard_scale：量到的防御消耗多久内拿来估精力见底时的消耗；一次都没量到时按最大精力的百分之几
const GUARD_COST_KEEP: Duration = Duration::from_secs(10);
const GUARD_COST_DEFAULT: i32 = 20;
/// target_hp_pct：算出来不到这么多就不扣（最小的 hp 档是 5）；同一档挂给同一个敌人这么久内算还在身上（hp 档持续 1 秒）
const PCT_MIN_DMG: f32 = 3.0;
const TIER_BUSY: Duration = Duration::from_millis(1100);
/// 扫多远内的角色（命中标记、异常）
const FOE_RANGE: f32 = 40.0;
/// 扫周围角色的范围：实际上是距离列表里的全部（用户 2026-11-05「30m对于远程来说还是太近了」：以前也是 40 米，
/// 远处被箭 / 法术打中的敌人看不到，猎印、回收、巨人杀手这些都不触发）。FOE_RANGE 只剩规则没写 range 时的默认
const FOE_SCAN: f32 = 1000.0;
/// 见切（mikiri_reason）：近战的够得着距离（再加敌人体型半径）、玩家体型半径（子弹用）、出招进度、面朝的夹角（度）；敌人的攻击动作编号范围
const MIKIRI_REACH: f32 = 4.0;
const MIKIRI_BODY: f32 = 0.6;
const MIKIRI_PROGRESS: (f32, f32) = (0.2, 0.75);
const MIKIRI_ARC: f32 = 60.0;
const ATTACK_ANIMS: std::ops::Range<i32> = 3000..4000;

/// 敌人的动作是不是攻击：动作编号 = 分段 × 1000000 + 编号（玩家的如 30032500），有的敌人攻击在别的分段，只看编号
fn is_attack(a: i32) -> bool {
    ATTACK_ANIMS.contains(&(a % 1_000_000))
}
/// 这一帧真正的翻滚无敌（runtime::pre_physics 在碾压 / 影步 / 飞鸿改过之后记）
pub static IFRAMES: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
/// 影步：tick 照引擎的 CutIFrames 设，runtime::pre_physics 看到就清玩家的无敌位
pub static CUT_IFRAMES: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
/// 减速 / 停住的敌人转身也放慢（用户 2026-11-03：见切后被影步停住的敌人还会朝人物转；见切减速时的转身也一样）：
/// 地址 → (倍数, 上一次放行后的朝向 yaw, 最后一次压速度的时间)。积木引擎每帧压动作速度（Act::FoeSpeed）时记，改回 1 就去掉；
/// turn_hold 在物理更新前（ChrIns_PrePhysics，同唤声船改朝向的时机）只放行游戏这一帧转的 × 倍数（停住 = 不转）
static TURN: Mutex<Option<HashMap<usize, (f32, Option<f32>, Instant)>>> = Mutex::new(None);
/// 这么久没压速度（引擎不管它了：离开扫描范围、卸载）就不管它的转身
const TURN_STALE: Duration = Duration::from_millis(300);

fn turn_set(id: usize, m: f32) {
    let mut g = TURN.lock().unwrap_or_else(|e| e.into_inner());
    let map = g.get_or_insert_with(HashMap::new);
    if m >= 0.999 {
        map.remove(&id);
    } else {
        let e = map.entry(id).or_insert((m, None, Instant::now()));
        e.0 = m;
        e.2 = Instant::now();
    }
}

/// 放行后的朝向：上一次放行后的 held 往游戏现在的朝向 now 转 × 倍数 m（走短的那边；第一次记现在的）
fn turn_step(held: Option<f32>, now: f32, m: f32) -> f32 {
    match held {
        Some(y) => crate::boat::wrap(y + crate::boat::wrap(now - y) * m),
        None => now,
    }
}

/// ChrIns_PrePhysics 每帧调：表里没有敌人就什么都不做
pub fn turn_hold() {
    let mut g = TURN.lock().unwrap_or_else(|e| e.into_inner());
    let Some(map) = g.as_mut() else { return };
    if map.is_empty() {
        return;
    }
    map.retain(|_, e| e.2.elapsed() < TURN_STALE);
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let live = live!(wcm);
    map.retain(|id, _| live.contains(id));
    for (&id, e) in map.iter_mut() {
        let ph = &mut unsafe { &mut *(id as *mut ChrIns) }.modules.physics;
        let now = crate::boat::quat_yaw(&ph.orientation);
        let y = turn_step(e.1, now, e.0);
        e.1 = Some(y);
        if crate::boat::wrap(now - y).abs() > 1e-4 {
            let q = crate::boat::yaw_quat(y);
            ph.orientation = q;
            ph.interpolated_orientation = q;
        }
    }
}
/// 连射：拉弓 / 换弹的速度倍数（f32 的位），runtime 的巧手那里乘上；1.0 = 不变
pub static RELOAD_MULT: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0x3f80_0000);

pub fn reload_mult() -> f32 {
    f32::from_bits(RELOAD_MULT.load(std::sync::atomic::Ordering::Relaxed))
}
/// 积木词条（处刑 haste、转念 act_speed）算出来的玩家动作速度倍数（f32 的位），runtime 那里乘上；1.0 = 不变
pub static ACTION_MULT: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0x3f80_0000);

pub fn action_mult() -> f32 {
    f32::from_bits(ACTION_MULT.load(std::sync::atomic::Ordering::Relaxed))
}
/// 背包里物品的类别（ItemCategory）：武器（箭、弩箭也是）、道具
const INV_WEAPON: u8 = 0;
const INV_GOODS: u8 = 4;
/// 崩架势：敌人这么久内被你打中过才算你打崩的
const BREAK_RECENT: Duration = Duration::from_secs(3);
/// 无尽箭袋（free）：付过专注的这一下射击 / 投掷最多算多久（动作的脉冲没断就一直算，这是兜底）
const FREE_HOLD: Duration = Duration::from_secs(3);
/// 无尽箭袋：这边打开着的游戏调试开关（1 = 「所有箭矢不消耗」，2 = 「玩家道具不消耗」）；关的时候只关自己开的，别的工具开的不碰
static FREE_SET: std::sync::atomic::AtomicU8 = std::sync::atomic::AtomicU8::new(0);
/// 不算敌人的阵营（NpcParam.teamType，按原版数据看的：0 友好 NPC、1 / 2 协力和友方召唤、26 / 28 能对话的 NPC、47 骨灰），
/// 再加上和玩家同阵营的；其余都算敌人（原版敌人用的号很多：6、7、27、48、51、33……，用白名单会漏）
pub(crate) const FRIENDLY_TEAMS: [u8; 6] = [0, 1, 2, 26, 28, 47];

// ------------------------------------------------------------------ 联机的命中归属（联机计划 13.7）
/// 子弹记多久、离敌人多远内算落在它身上（照黄金树爬塔：0.7 秒、6 米）
const BULLET_MEMORY: Duration = Duration::from_millis(700);
const BULLET_REACH: f32 = 6.0;

/// 落在敌人 BULLET_REACH 米内、最近的那颗子弹是不是自己放的；附近没有子弹 None
pub(crate) fn bullet_owner_is_mine(foe: [f32; 3], bullets: &[(Instant, [f32; 3], bool)]) -> Option<bool> {
    bullets.iter().map(|&(_, q, m)| (dist3(foe, q), m)).filter(|&(d, _)| d <= BULLET_REACH).min_by(|a, b| a.0.total_cmp(&b.0)).map(|x| x.1)
}

/// 离敌人最近的是不是自己 / 自己的召唤物（不比队友远就算）；自己一个都不在场 false
pub(crate) fn nearest_is_mine(foe: [f32; 3], mine: &[[f32; 3]], others: &[[f32; 3]]) -> bool {
    let closest = |set: &[[f32; 3]]| set.iter().map(|&q| dist3(foe, q)).fold(f32::INFINITY, f32::min);
    !mine.is_empty() && closest(mine) <= closest(others)
}

/// 一帧里算归属要的：自己 / 队友的句柄、位置（只要本机所在大区的）
struct Attrib {
    own: Vec<eldenring::cs::FieldInsHandle>,
    area: u8,
    mine_at: Vec<[f32; 3]>,
    others_at: Vec<[f32; 3]>,
}

impl Attrib {
    fn read(summon_set: &eldenring::cs::ChrSet<ChrIns>, player_set: &eldenring::cs::ChrSet<eldenring::cs::PlayerIns>, me: &ChrIns,
            bullets: &mut Vec<(Instant, [f32; 3], bool)>, now: Instant) -> Attrib {
        let pos = |c: &ChrIns| [c.modules.physics.position.0, c.modules.physics.position.1, c.modules.physics.position.2];
        let area = me.block_id.area();
        let alive = |c: &ChrIns| c.modules.data.hp > 0;
        let summons: Vec<&ChrIns> = summon_set.characters().map(|c| &*c).collect();
        let own: Vec<eldenring::cs::FieldInsHandle> = std::iter::once(me.field_ins_handle).chain(summons.iter().map(|c| c.field_ins_handle)).collect();
        let mine_at = std::iter::once(pos(me)).chain(summons.iter().filter(|c| alive(c) && c.block_id.area() == area).map(|c| pos(c))).collect();
        let mates: Vec<&ChrIns> = player_set.characters().map(|p| &p.chr_ins).filter(|c| !own.contains(&c.field_ins_handle)).collect();
        let others_at = mates.iter().filter(|c| alive(c) && c.block_id.area() == area).map(|c| pos(c)).collect();
        // 这一帧在飞的、自己或队友放的子弹
        bullets.retain(|x| now.duration_since(x.0) <= BULLET_MEMORY);
        if let Ok(m) = unsafe { eldenring::cs::CSBulletManager::instance() } {
            for b in m.bullets() {
                let owner = b.targeting_owner.owner_chr_handle;
                let mine = own.contains(&owner);
                if mine || mates.iter().any(|c| c.field_ins_handle == owner) {
                    let q = &b.physics.position;
                    bullets.push((now, [q.0, q.1, q.2], mine));
                }
            }
        }
        if bullets.len() > 512 {
            let n = bullets.len() - 512;
            bullets.drain(..n);
        }
        Attrib { own, area, mine_at, others_at }
    }

    /// 这个敌人身上的命中算不算自己的，和怎么认的（日志用）
    fn mine(&self, c: &ChrIns, bullets: &[(Instant, [f32; 3], bool)]) -> (bool, &'static str) {
        let a = c.last_hit_by;
        if !a.is_empty() {
            return (self.own.contains(&a), "最后打中它的是别人");
        }
        if c.block_id.area() != self.area {
            return (false, "不在你所在的大区");
        }
        let q = [c.modules.physics.position.0, c.modules.physics.position.1, c.modules.physics.position.2];
        match bullet_owner_is_mine(q, bullets) {
            Some(m) => (m, "落在它身上的子弹是队友的"),
            None => (nearest_is_mine(q, &self.mine_at, &self.others_at), "离它最近的是队友"),
        }
    }
}

/// 算不算敌人：阵营号不是友方、不是自己的阵营，也不是玩家角色（chrs::is_player；联机计划 13.2 G8，入侵者、队友都不算）
pub(crate) fn is_foe(c: &ChrIns, my_team: u8) -> bool {
    !FRIENDLY_TEAMS.contains(&c.team_type) && c.team_type != my_team && !crate::chrs::is_player(c)
}

#[derive(Debug, Clone, PartialEq)]
enum Kind {
    While {
        /// 持续状态的事件；None = 不看事件
        cond: Option<String>,
        /// 这个事件在的时候不成立（天堑：站在地上、但跳劈落地那一下不算）
        unless: Option<String>,
        /// 血量低于这个百分比才成立；0 = 不看血量
        hp_below: f32,
        /// 血量不低于这个百分比才成立；0 = 不看（背水：每一档只挂一行，图标写着档数）
        hp_above: f32,
        /// 这条词条的叠层至少 min 层
        stack: Option<String>,
        min: u32,
        effect: [i32; 4],
        /// 专注不再消耗：每帧补满，掉的部分按百分比扣血（各稀有度）
        fp_to_hp: [f32; 4],
        /// 条件成立时掉的精力补回来、改扣血：一整管精力折最大血量的这么多百分比（各稀有度；燃血，可以扣到死）
        stamina_to_hp: [f32; 4],
        /// 血量上限加这么多点（各稀有度；血瓮）：按基础血量上限挑 hpmax 档
        hp_flat: [f32; 4],
        /// 条件连续成立这么久以后清无敌位；0 = 不管
        cut_after: f32,
        /// 条件成立时玩家动作速度 × (1 + 百分比 × stack 那条词条的层数)
        layer_speed: [f32; 4],
        /// 千钧：条件成立期间（满蓄力这一击），身边这么多米内的普通敌人挂上 poise_fx（受到的削韧 ×1000），打中的当场崩架势；
        /// Boss 出手时先扣上限的 poise_boss_pct%，打中时引擎连同这一击的削韧一起判崩，没打中就加回去；0 = 不管
        poise_radius: f32,
        poise_boss_pct: [f32; 4],
        poise_fx: [i32; 4],
        /// 动作播放进度的区间（0~1）；None = 不看
        prog: Option<(f32, f32)>,
        /// 进度从这个事件在当前动作里第一次出现时算起；None = 从动作开头
        prog_from: Option<String>,
        /// 按攻击判定开窗口：(判定开始前多少秒, 判定结束后多少秒)；None = 不看
        hit: Option<(f32, f32)>,
    },
    On {
        /// 动作加快的百分比、持续秒数（处刑；只用这条规则的稀有度）
        haste: [f32; 4],
        haste_secs: f32,
        event: String,
        /// 事件结束（标记消失）时才做
        at_end: bool,
        /// 这个持续状态的事件在才做
        cond: Option<String>,
        /// 血量低于这个百分比才做；0 = 不看（回光）
        hp_below: f32,
        /// 各稀有度的冷却（秒）
        cooldown: [f32; 4],
        fp: [i32; 4],
        stamina: [i32; 4],
        hp: [i32; 4],
        /// 最大血量 / 专注的百分比
        hp_pct: [f32; 4],
        fp_pct: [f32; 4],
        /// 之后这么多秒里自然回的血扣回去
        deny_heal: f32,
        effect: [i32; 4],
        /// 每隔这么久做一次（不看事件）；0 = 看事件
        every: f32,
        /// 放冲击波：右手武器攻击力的百分比 / 固定伤害（各稀有度），× 层数，在 burst_kind 那套档位里挑最接近的
        burst: [f32; 4],
        burst_flat: [f32; 4],
        burst_kind: String,
        burst_each: bool,
        /// burst_spell=1：固定伤害再乘拿着的法器的法术补正面板 ÷ 200（法球，spellbase.rs）
        burst_spell: bool,
        /// burst_grow：每层伤害再乘 1 + 百分比 / 100 × 拿走的层数（各稀有度）
        burst_grow: [f32; 4],
        /// grow_held=1：burst_grow 按拿走之前身上的层数算（星群）
        grow_held: bool,
        /// 消耗这个词条（第一条叠层规则）的层数（take_max 层为止，0 = 全部）：冲击波 × 层数；没有层数就整条不做
        take: Option<String>,
        take_max: u32,
        /// take_full：那条叠层满了才做（拿走全部）；做了的这一帧它不再加层（迸发：法球满了下一次施法射出全部，这次施法不另出一颗）
        take_full: bool,
        /// take_fresh：只认叠层加上之后才开始的动作里的命中，翻滚 / 后撤步中的不算（积蓄）
        take_fresh: bool,
        /// 防御：引擎只扣了 1/guard_scale 的精力，补扣剩下的；不够的部分扣 short_hp 百分比的血（各稀有度）
        guard_scale: f32,
        short_hp: [f32; 4],
        /// 这一下掉的精力补回百分比（各稀有度）
        stamina_back: [f32; 4],
        /// 周围 foe_radius 米内的敌人动作速度降低百分比，foe_secs 秒；戴着 freeze_key 改成停住 freeze_secs 秒
        foe_slow: [f32; 4],
        foe_radius: f32,
        foe_secs: [f32; 4],
        freeze_key: Option<String>,
        freeze_secs: f32,
        /// 做完后把触发事件挡住多久（从减速 / 停住结束时起算）；0 = 不挡
        rest: f32,
        /// 被打中的敌人（land）：身上要有这些异常 / 摘掉它们 / 剩下的伤害结算百分比 / 挂随机一种异常的累积
        target_has: Vec<String>,
        target_remove: bool,
        target_settle: [f32; 4],
        target_buildup: [f32; 4],
        /// 按被打中的敌人最大血量扣血（巨人杀手）：每下 target_hp_pct%，同一个敌人每第 target_nth 下再加 target_nth_pct%
        /// （target_reset 秒没再打中它就重新数）；每下最多右手武器攻击力的 target_cap%；挑最接近的 hp 档挂给它
        target_hp_pct: [f32; 4],
        target_nth: u32,
        target_nth_pct: [f32; 4],
        target_cap: [f32; 4],
        target_reset: f32,
        buildup_kinds: Vec<String>,
        /// 这些事件在时不做（比如近战命中 = land 但不是 shot_hit / item_hit）
        unless: Vec<String>,
        /// 做的几率（各稀有度，%）；0 = 一定做
        chance: [f32; 4],
        /// 目标：land（刚被打中的敌人）/ break（刚被打崩架势的敌人）
        target_on: String,
        /// 给目标挂的效果（各稀有度）
        target_fx: [i32; 4],
        /// 给目标叠标记（猎印）：标记名、最多几层、持续几秒、每层一行效果（各稀有度，mfx0~mfx3）
        target_mark: Option<String>,
        mark_max: u32,
        mark_secs: f32,
        mark_fx: [Vec<i32>; 4],
        /// 消耗目标身上的标记（全部层）：每层右手武器攻击力的百分比，挑最接近的 hp 档挂给它；
        /// take_grow：不是每层一样，而是第一层这么多、每多一层再乘这个数（引爆）；0 = 没写，按层数加
        target_take: Option<String>,
        take_grow: f32,
        take_pct: [f32; 4],
        /// 消耗标记时给目标挂的一闪的特效（各稀有度一组，按消耗的层数挑：第 n 层用第 n 个，不够用最后一个；tfx0~tfx3。猎印碎裂，用户 2026-11-13）
        take_fx: [Vec<i32>; 4],
        /// 返还刚用掉的弹药 / 投掷道具：这么多秒内最近用掉、还没返还过的那个（回收）
        refund: f32,
    },
    Stack {
        add: Vec<String>,
        /// 这个状态在时加层才算
        cond: Option<String>,
        clear: Vec<String>,
        consume: Vec<String>,
        /// 层数上限（各稀有度）；戴着 max_boost_key 再加 max_boost（按 max_boost_key 那条戴着的稀有度；盈满 1~4，2026-11-04）
        max: [u32; 4],
        max_boost_key: Option<String>,
        max_boost: [u32; 4],
        timeout: f32,
        fx: [Vec<i32>; 4],
        stamina: [i32; 4],
        hp: [i32; 4],
        log: Option<String>,
        /// 每层加快拉弓 / 换弹的百分比（连射；runtime 的巧手那里乘上 RELOAD_MULT）
        reload_speed: [f32; 4],
        /// 消耗中（consume 的那个动作还没做完）玩家动作加快的百分比（转念）
        act_speed: [f32; 4],
    },
    FoeAura {
        range: f32,
        fx: [Vec<i32>; 4],
    },
    FoeReact {
        when: String,
        need: String,
        pct: [f32; 4],
        remove: bool,
        log: Option<String>,
    },
    FoeSpread {
        range: f32,
        amount: [f32; 4],
        kinds: Vec<String>,
        log: Option<String>,
    },
    Rally {
        event: String,
        window: [f32; 4],
        pct: [f32; 4],
        effect: [i32; 4],
        flash: [i32; 4],
        boost_key: Option<String>,
        boost: f32,
        log: Option<String>,
    },
    /// 无尽箭袋：每次射击 / 投掷扣的专注（各稀有度）
    Free {
        fp: [i32; 4],
    },
    /// 静息（泡盾）：持续 secs 秒没受到伤害就挂 effect（照原版珍珠泡状露滴：下一次受到的伤害减少、受伤就消失）。
    /// 受击（hit 事件）或者效果刚没了（被打掉的那一帧受击事件可能还没到，不算的话会马上又挂回去）都算刚受过伤、重新计时；刚戴上也从头计时
    Quiet {
        secs: f32,
        effect: [i32; 4],
    },
}

#[derive(Debug, Clone, PartialEq)]
struct Rule {
    key: String,
    kind: Kind,
    /// 要扫周围的角色（foe_needs）：戴着这条词条时 tick 才每帧扫
    foes: bool,
    /// requires=<词条>：要那条词条一起戴才生效（影步要见切）；缺了整条词条当没戴（drop_unmet_needs）。
    /// 不叫 need：foe_react 的 need=<异常> 已经占了（碎冰）
    requires: Option<String>,
}

/// 戴着的词条里，有规则 requires 的另一条词条没戴的，当这条没戴（不扫周围、不触发、它的常驻效果也摘掉）；连着要的一直查到不再变
fn drop_unmet_needs(d: &Def, tiers: &mut HashMap<String, usize>) {
    loop {
        let drop: Vec<String> = d
            .rules
            .iter()
            .filter(|r| tiers.contains_key(&r.key) && r.requires.as_ref().is_some_and(|k| !tiers.contains_key(k)))
            .map(|r| r.key.clone())
            .collect();
        if drop.is_empty() {
            return;
        }
        for k in drop {
            tiers.remove(&k);
        }
    }
}

/// 靠扫周围角色才知道的事件：命中（land）、箭 / 投掷道具命中、打崩架势、见切
const FOE_EVENTS: [&str; 6] = ["land", "shot_hit", "item_hit", "cast_hit", "break", "mikiri"];

/// 这条规则要不要扫周围的角色（目标层、上面那些事件、压周围敌人的架势 / 减速）。
/// 用户 2026-11-01：每帧的活要挂在穿戴上——以前词条库里有这类规则就每帧扫，不管戴没戴
fn foe_needs(kind: &Kind) -> bool {
    let ev = |e: &str| FOE_EVENTS.contains(&e);
    let opt = |e: &Option<String>| e.as_deref().is_some_and(ev);
    match kind {
        Kind::While { cond, unless, poise_radius, .. } => opt(cond) || opt(unless) || *poise_radius > 0.0,
        Kind::On {
            event, cond, unless, foe_slow, target_has, target_remove, target_settle, target_buildup, target_hp_pct, target_fx, target_mark,
            target_take, ..
        } => {
            // 有目标层的效果（同 step 里的 targeted；target_on 默认就是 land，不能拿它判断）
            let targeted = !target_has.is_empty()
                || *target_remove
                || target_settle.iter().chain(target_buildup).chain(target_hp_pct).any(|&x| x > 0.0)
                || target_fx.iter().any(|&x| x > 0)
                || target_mark.is_some()
                || target_take.is_some();
            ev(event) || opt(cond) || unless.iter().any(|e| ev(e)) || targeted || foe_slow.iter().any(|&x| x > 0.0)
        }
        Kind::Stack { add, cond, clear, consume, .. } => opt(cond) || add.iter().chain(clear).chain(consume).any(|e| ev(e)),
        Kind::FoeAura { .. } | Kind::FoeReact { .. } | Kind::FoeSpread { .. } => true,
        Kind::Rally { event, .. } => ev(event),
        Kind::Free { .. } | Kind::Quiet { .. } => false,
    }
}

#[derive(Debug, Default, PartialEq, Clone)]
struct Def {
    /// 事件 → 脉冲标记
    marks: HashMap<String, i32>,
    /// 词条键 → 标记（普通 ~ 传说，不出的稀有度 -1）
    affs: HashMap<String, [i32; 4]>,
    /// 写在武器上的词条：必须由当前出招手上的武器携带对应标记才生效
    weapon_keys: HashSet<String>,
    rules: Vec<Rule>,
    /// 跳过的行（写日志）
    skipped: Vec<String>,
    /// 引擎管的效果（while 的 effect、stack 的 fx，所有稀有度）：不该挂时身上有就摘
    managed: HashSet<i32>,
    /// 有血瓮（hp_flat）：hpmax 那套档位也归引擎管（parse 末尾加进 managed）
    hp_flat: bool,
    /// 冲击波各套各档：套 → (伤害, 放冲击波的效果)；crushtier 行是 phys 那套（和碾压共用）
    tiers: HashMap<String, Vec<(f32, i32)>>,
    /// 精确扣血的专用效果行（hppool）；没有就按档位
    hp_pool: Vec<i32>,
    /// 物理冲击波（反震 / 坠星）的实时伤害专用行：(放冲击波的效果, 它的攻击行)，轮流用（shocklive 行，用户 2026-11-12）；没有就按 phys 档位
    shock_live: Vec<(i32, u32)>,
    /// 武器重击的削韧倍率％（heavypoise 行，同 runtime.rs）：物理冲击波的削韧 = 右手武器的重击削韧
    heavy_poise: HashMap<(u8, i32), f32>,
    /// 档位效果 → 它放的子弹（bursttier 行第 5 项；法球那套有，直接射用）
    tier_bullet: HashMap<i32, i32>,
    /// 法球直接从法器点位射出：(右手武器的点位, 左手的)（orbshot 行；没有 = 照旧挂效果）
    orbshot: Option<(i32, i32)>,
    /// 只在地上放的冲击波效果（GROUND_KINDS 那几套的所有档）
    ground: HashSet<i32>,
    /// 身上有就无敌的效果（iframe 行）
    iframes: Vec<i32>,
    /// 异常累积：异常 → (点数, 效果)（buildup 行）
    buildups: HashMap<String, Vec<(f32, i32)>>,
    /// 被命中标记顶掉的命中时触发：(玩家身上的效果, 补挂的副本, wepParamChange：0 = 不分手)（atkfwd 行，重随 rr/atkfwd.py）
    atkfwd: Vec<(i32, i32, i32)>,
    /// 有目标层的规则（要扫周围角色的异常）
    foe_rules: bool,
    /// 发狂发作（敌人身上新出现发狂类的效果）时架势扣上限的几成：runtime.txt 的 madpoise 行（重随 rr/ailments.py），0 = 不扣
    mad_poise: f32,
    /// 敌人发狂发作时给它挂的特效效果（runtime.txt 的 madvfx 行，重随 rr/ailments.py；原版玩家发狂硬直动作里的特效，敌人没有这个动作），0 = 不挂
    mad_vfx: i32,
    /// 有规则在听见切（要看周围敌人的动作）；听见切的词条（戴着才写没成立的日志）
    mikiri: bool,
    mikiri_keys: Vec<String>,
    /// 会被返还的弹药 / 投掷道具：(背包类别 0 武器 / 4 道具, 编号)（ammo 行）；有规则要返还才数背包
    ammo: HashSet<(u8, u32)>,
    refunds: bool,
    /// Boss 的 NpcParam 编号（boss 行；千钧只扣它们强韧度上限的一部分）
    bosses: HashSet<i32>,
    /// 叠标记（猎印）每层挂给敌人的效果（tick 的诊断日志认它们）
    mark_fx_ids: HashSet<i32>,
    /// 玩家动作 → 攻击判定的时间段（秒；hitwin 行，while 的 hit 用）
    hits: Arc<HashMap<i32, (f32, f32)>>,
    /// 敌人（模型号, 动作编号）→ 攻击判定的时间段（秒；foewin 行，见切用）；表里有的模型
    foe_hits: Arc<HashMap<(u32, i32), Vec<(f32, f32)>>>,
    foe_models: Arc<HashSet<u32>>,
}

impl Def {
    /// 这个词条的第一条叠层规则
    /// 第 j 条（叠层规则）现在的层数上限：它那条词条戴着的稀有度的 max，戴着 max_boost_key 再加
    fn stack_cap(&self, j: usize, tiers: &HashMap<String, usize>) -> u32 {
        let rule = &self.rules[j];
        let Kind::Stack { max, max_boost_key, max_boost, .. } = &rule.kind else { return u32::MAX };
        let r = tiers.get(&rule.key).copied().unwrap_or(0);
        max[r].max(1) + max_boost_key.as_ref().and_then(|k| tiers.get(k)).map_or(0, |&rb| max_boost[rb])
    }

    fn stack_of(&self, key: &str) -> Option<usize> {
        self.rules.iter().position(|r| r.key == key && matches!(r.kind, Kind::Stack { .. }))
    }

    /// 武器类规则：当前出招手上的武器必须携带这个稀有度的特效标记。
    /// 护符 / 防具词条不在 weapon_keys 里，照旧只按玩家身上的标记生效。
    fn weapon_ok(&self, key: &str, r: usize, fr: &Frame) -> bool {
        if !self.weapon_keys.contains(key) {
            return true;
        }
        self.affs.get(key).and_then(|m| m.get(r)).is_some_and(|&m| m > 0 && fr.weapon_markers.contains(&m))
    }

    /// 这种异常最接近 amount 的那档累积
    fn buildup(&self, kind: &str, amount: f32) -> Option<i32> {
        self.buildups.get(kind)?.iter().copied().min_by(|a, b| (a.0 - amount).abs().total_cmp(&(b.0 - amount).abs())).map(|x| x.1)
    }

    /// 这套里最接近 dmg 的那档冲击波
    fn tier(&self, kind: &str, dmg: f32) -> Option<(f32, i32)> {
        self.tier_except(kind, dmg, |_| false)
    }

    /// 同 tier，跳过 busy 的效果（同一档刚挂给同一个敌人、还在身上：再挂可能只是续时间）
    fn tier_except(&self, kind: &str, dmg: f32, busy: impl Fn(i32) -> bool) -> Option<(f32, i32)> {
        self.tiers.get(kind)?.iter().copied().filter(|x| !busy(x.1)).min_by(|a, b| (a.0 - dmg).abs().total_cmp(&(b.0 - dmg).abs()))
    }

    /// 加起来接近 dmg、又不超过 cap 的几档（回响祝福：有伤害数字，但不打死）；busy 的效果跳过（同一档还在身上，再挂可能只是续时间）
    fn tiers_within(&self, kind: &str, dmg: f32, cap: f32, busy: impl Fn(i32) -> bool) -> Vec<(f32, i32)> {
        let Some(all) = self.tiers.get(kind) else { return Vec::new() };
        let start = dmg.min(cap);
        let (mut left, mut room) = (start, cap);
        let mut out: Vec<(f32, i32)> = Vec::new();
        while let Some(t) = all
            .iter()
            .copied()
            .filter(|x| x.0 <= room && !busy(x.1) && !out.iter().any(|o| o.1 == x.1) && (out.is_empty() || x.0 <= left * 1.2))
            .min_by(|a, b| (a.0 - left).abs().total_cmp(&(b.0 - left).abs()))
        {
            out.push(t);
            left -= t.0;
            room -= t.0;
            if left < start * 0.1 {
                break;
            }
        }
        out
    }

    /// 加起来接近 dmg 的几档：一般就是最接近的一档；最高档也不够（引爆翻倍后）就往下一档档加，每档只用一次（同一个效果挂两次不叠）
    fn tiers_sum(&self, kind: &str, dmg: f32) -> Vec<(f32, i32)> {
        let mut out: Vec<(f32, i32)> = Vec::new();
        let mut left = dmg;
        while let Some(t) = self.tier_except(kind, left, |sp| out.iter().any(|x| x.1 == sp)) {
            out.push(t);
            left -= t.0;
            if left < dmg * 0.1 {
                break;
            }
        }
        out
    }
}

/// 精确扣血的专用行写了数值后留这么久不再改（效果本身持续 1 秒；游戏可能晚几帧才读数值）
const HP_ROW_HOLD: Duration = Duration::from_millis(1200);
static HP_ROWS: Mutex<Option<HashMap<i32, Instant>>> = Mutex::new(None);

/// 挑一行能写的：没被占着，这个敌人身上也没有（再挂可能只是续时间）
fn free_hp_row(pool: &[i32], held: &HashMap<i32, Instant>, now: Instant, on_foe: impl Fn(i32) -> bool) -> Option<i32> {
    pool.iter().copied().find(|sp| held.get(sp).is_none_or(|t| now >= *t) && !on_foe(*sp))
}

/// 给敌人扣精确的血（用户 2026-11-09）：参数行启动时就定了、挂效果只能传行号，所以运行时把数值写进专用行再挂，游戏显示的就是这个数。
/// 专用行都占着 / 没有专用行时返回 false，调用的地方退回固定档位
pub fn foe_hp_exact(c: &mut ChrIns, amt: i32) -> bool {
    let d = def();
    if d.hp_pool.is_empty() || amt <= 0 {
        return false;
    }
    let now = Instant::now();
    let mut g = HP_ROWS.lock().unwrap_or_else(|e| e.into_inner());
    let held = g.get_or_insert_with(HashMap::new);
    let Some(sp) = free_hp_row(&d.hp_pool, held, now, |sp| c.special_effect.entries().any(|e| e.param_id == sp)) else { return false };
    let wrote = unsafe { SoloParamRepository::instance_mut() }.ok().and_then(|repo| repo.get_mut::<SpEffectParam>(sp as u32)).map(|s| s.set_change_hp_point(amt)).is_some();
    if !wrote {
        return false;
    }
    held.insert(sp, now + HP_ROW_HOLD);
    crate::coop::note(crate::coop::Op::Apply(sp), c);
    c.apply_speffect(sp, false);
    true
}

/// 给敌人的固定扣血档（bursttier hp，引爆、碎冰用的那套，游戏会显示伤害数字）：加起来接近 dmg、不超过 cap，返回 (伤害, 效果)
pub fn hp_burst(dmg: f32, cap: f32, busy: impl Fn(i32) -> bool) -> Vec<(f32, i32)> {
    def().tiers_within("hp", dmg, cap, busy)
}

/// 冲击波档位（burst_kind）的固定伤害按哪项属性乘倍率（procs::mults：物理 魔力 火 雷 圣）：
/// magic / pebble（法球的辉石魔砾）按智力、信仰里高的（用户 2026-11-15；魔力那项按智力、火那项按信仰，倍率随属性单调，取大的就是取高的属性），其他按物理
fn kind_scale(kind: &str, scale: &[f32; 5]) -> f32 {
    if matches!(kind, "magic" | "pebble") { scale[1].max(scale[2]) } else { scale[0] }
}

/// 按稀有度的四个值；只写一个就四档一样
fn four_f(s: Option<&&str>) -> [f32; 4] {
    let v: Vec<f32> = s.map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.trim().parse::<f32>().ok()).collect());
    match v.len() {
        1 => [v[0]; 4],
        _ => v.try_into().unwrap_or([0.0; 4]),
    }
}

/// 没写 foe_secs 时保持旧默认；写了就让每档不同
fn four_f_or(s: Option<&&str>, default: f32) -> [f32; 4] {
    if s.is_none() { [default; 4] } else { four_f(s) }
}

fn four(s: Option<&&str>) -> [i32; 4] {
    four_f(s).map(|x| x.round() as i32)
}

fn names(s: Option<&&str>) -> Vec<String> {
    s.map_or(Vec::new(), |s| s.split(',').map(str::trim).filter(|x| !x.is_empty()).map(String::from).collect())
}

fn parse(text: &str) -> Def {
    let mut d = Def::default();
    let mut rules = Vec::new();
    for line in text.lines().map(|l| l.trim_start_matches('\u{feff}').trim_end()) {
        let f: Vec<&str> = line.split('\t').collect();
        match (f[0], f.len()) {
            ("mark", 3..) => {
                if let Ok(id) = f[2].parse() {
                    d.marks.insert(f[1].to_string(), id);
                }
            }
            ("aff", 3..) => {
                let m = f[2].split(',').filter_map(|x| x.trim().parse().ok()).collect::<Vec<i32>>();
                match <[i32; 4]>::try_from(m) {
                    Ok(m) => {
                        d.affs.insert(f[1].to_string(), m);
                    }
                    Err(_) => d.skipped.push(format!("词条 {} 的标记不是 4 个", f[1])),
                }
            }
            ("weapon", 2..) => {
                d.weapon_keys.insert(f[1].to_string());
            }
            ("rule", 3..) => rules.push(f.iter().map(|s| s.to_string()).collect::<Vec<_>>()),
            ("hitwin", 4..) => {
                if let (Ok(a), Ok(lo), Ok(hi)) = (f[1].parse(), f[2].parse(), f[3].parse()) {
                    Arc::make_mut(&mut d.hits).insert(a, (lo, hi));
                }
            }
            ("foewin", 4..) => {
                if let (Ok(m), Ok(a)) = (f[1].parse::<u32>(), f[2].parse::<i32>()) {
                    let w: Vec<(f32, f32)> = f[3]
                        .split(';')
                        .filter_map(|p| {
                            let (s, e) = p.split_once(',')?;
                            Some((s.parse().ok()?, e.parse().ok()?))
                        })
                        .collect();
                    if !w.is_empty() {
                        Arc::make_mut(&mut d.foe_models).insert(m);
                        Arc::make_mut(&mut d.foe_hits).insert((m, a), w);
                    }
                }
            }
            ("madpoise", 2..) => {
                d.mad_poise = f[1].parse::<f32>().map_or(0.0, |v| (v / 100.0).clamp(0.0, 1.0));
                d.foe_rules |= d.mad_poise > 0.0;
            }
            ("madvfx", 2..) => {
                d.mad_vfx = f[1].parse().unwrap_or(0).max(0);
                d.foe_rules |= d.mad_vfx > 0;
            }
            ("crushtier", 3..) => {
                if let (Ok(dmg), Ok(sp)) = (f[1].parse(), f[2].parse()) {
                    d.tiers.entry("phys".into()).or_default().push((dmg, sp));
                }
            }
            ("hppool", 2..) => d.hp_pool = f[1].split(',').filter_map(|x| x.parse().ok()).collect(),
            ("shocklive", 3..) => {
                if let (Ok(sp), Ok(atk)) = (f[1].parse(), f[2].parse()) {
                    d.shock_live.push((sp, atk));
                }
            }
            ("heavypoise", 4..) => {
                if let (Ok(cat), Ok(bv), Ok(pct)) = (f[1].parse(), f[2].parse(), f[3].parse()) {
                    d.heavy_poise.insert((cat, bv), pct);
                }
            }
            ("bursttier", 4..) => {
                if let (Ok(dmg), Ok(sp)) = (f[2].parse(), f[3].parse()) {
                    d.tiers.entry(f[1].to_string()).or_default().push((dmg, sp));
                    if let Some(Ok(b)) = f.get(4).map(|x| x.parse::<i32>()) {
                        d.tier_bullet.insert(sp, b);
                        if f[1] == "pebble" {
                            crate::orbshot::offer_test(dmg, sp);
                        }
                    }
                }
            }
            ("orbshot", 3..) => {
                if let (Ok(r), Ok(l)) = (f[1].parse(), f[2].parse()) {
                    d.orbshot = Some((r, l));
                }
            }
            ("buildup", 4..) => {
                if let (Ok(n), Ok(sp)) = (f[2].parse(), f[3].parse()) {
                    d.buildups.entry(f[1].to_string()).or_default().push((n, sp));
                }
            }
            ("atkfwd", 4..) => {
                if let (Ok(buff), Ok(copy), Ok(wep)) = (f[1].parse(), f[2].parse(), f[3].parse()) {
                    d.atkfwd.push((buff, copy, wep));
                }
            }
            ("iframe", 2..) => d.iframes.extend(f[1].split(',').filter_map(|x| x.trim().parse::<i32>().ok()).filter(|&x| x > 0)),
            ("ammo", 3..) => {
                let cat = match f[1] {
                    "w" => Some(INV_WEAPON),
                    "g" => Some(INV_GOODS),
                    _ => None,
                };
                if let (Some(c), Ok(id)) = (cat, f[2].parse()) {
                    d.ammo.insert((c, id));
                }
            }
            ("boss", 2..) => d.bosses.extend(f[1].parse::<i32>().ok()),
            _ => {}
        }
    }
    for f in rules {
        let kv: HashMap<&str, &str> = f[3..].iter().filter_map(|x| x.split_once('=')).collect();
        let kind = match f[2].as_str() {
            "while" => ["cond", "unless", "hp_below", "hp_above", "stack", "effect", "fp_to_hp", "stamina_to_hp", "hp_flat", "cut_after"].iter().any(|k| kv.contains_key(k)).then(|| Kind::While {
                cond: kv.get("cond").map(|c| c.to_string()),
                unless: kv.get("unless").map(|c| c.to_string()),
                hp_below: kv.get("hp_below").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                hp_above: kv.get("hp_above").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                stack: kv.get("stack").map(|c| c.to_string()),
                min: kv.get("min").and_then(|x| x.parse().ok()).unwrap_or(1),
                effect: four(kv.get("effect")),
                fp_to_hp: four_f(kv.get("fp_to_hp")),
                stamina_to_hp: four_f(kv.get("stamina_to_hp")),
                hp_flat: four_f(kv.get("hp_flat")),
                cut_after: kv.get("cut_after").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                layer_speed: four_f(kv.get("layer_speed")),
                poise_radius: kv.get("poise_radius").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                poise_boss_pct: four_f(kv.get("poise_boss_pct")),
                poise_fx: four(kv.get("poise_fx")),
                prog: kv.get("prog").and_then(|x| {
                    let (a, b) = x.split_once(',')?;
                    Some((a.trim().parse().ok()?, b.trim().parse().ok()?))
                }),
                prog_from: kv.get("prog_from").map(|c| c.to_string()),
                hit: kv.get("hit").and_then(|x| {
                    let (a, b) = x.split_once(',')?;
                    Some((a.trim().parse().ok()?, b.trim().parse().ok()?))
                }),
            }),
            "on" => (kv.contains_key("event") || kv.contains_key("every")).then(|| Kind::On {
                haste: four_f(kv.get("haste")),
                haste_secs: kv.get("haste_secs").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                event: kv.get("event").map_or(String::new(), |e| e.to_string()),
                every: kv.get("every").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                at_end: kv.get("when") == Some(&"end"),
                cond: kv.get("cond").map(|c| c.to_string()),
                hp_below: kv.get("hp_below").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                cooldown: four_f(kv.get("cooldown")),
                fp: four(kv.get("fp")),
                stamina: four(kv.get("stamina")),
                hp: four(kv.get("hp")),
                hp_pct: four_f(kv.get("hp_pct")),
                fp_pct: four_f(kv.get("fp_pct")),
                deny_heal: kv.get("deny_heal").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                effect: four(kv.get("effect")),
                burst: four_f(kv.get("burst")),
                burst_flat: four_f(kv.get("burst_flat")),
                burst_kind: kv.get("burst_kind").map_or("phys".into(), |x| x.to_string()),
                burst_each: kv.get("burst_each").is_some_and(|x| *x != "0"),
                burst_spell: kv.get("burst_spell").is_some_and(|x| *x != "0"),
                burst_grow: four_f(kv.get("burst_grow")),
                grow_held: kv.get("grow_held").is_some_and(|x| *x != "0"),
                take: kv.get("take").map(|x| x.to_string()),
                take_max: kv.get("take_max").and_then(|x| x.parse().ok()).unwrap_or(0),
                take_full: kv.get("take_full").is_some_and(|x| *x != "0"),
                take_fresh: kv.get("take_fresh").is_some_and(|x| *x != "0"),
                guard_scale: kv.get("guard_scale").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                short_hp: four_f(kv.get("short_hp")),
                stamina_back: four_f(kv.get("stamina_back")),
                foe_slow: four_f(kv.get("foe_slow")),
                foe_radius: kv.get("foe_radius").and_then(|x| x.parse().ok()).unwrap_or(8.0),
                foe_secs: four_f_or(kv.get("foe_secs"), 2.0),
                freeze_key: kv.get("freeze_key").map(|x| x.to_string()),
                freeze_secs: kv.get("freeze_secs").and_then(|x| x.parse().ok()).unwrap_or(1.0),
                rest: kv.get("rest").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                target_has: names(kv.get("target_has")),
                target_remove: kv.get("target_remove") == Some(&"1"),
                target_settle: four_f(kv.get("target_settle")),
                target_buildup: four_f(kv.get("target_buildup")),
                target_hp_pct: four_f(kv.get("target_hp_pct")),
                target_nth: kv.get("target_nth").and_then(|x| x.parse().ok()).unwrap_or(0),
                target_nth_pct: four_f(kv.get("target_nth_pct")),
                target_cap: four_f(kv.get("target_cap")),
                target_reset: kv.get("target_reset").and_then(|x| x.parse().ok()).unwrap_or(5.0),
                buildup_kinds: names(kv.get("buildup_kinds")),
                unless: names(kv.get("unless")),
                chance: four_f(kv.get("chance")),
                target_on: kv.get("target_on").map_or("land".into(), |x| x.to_string()),
                target_fx: four(kv.get("target_fx")),
                target_mark: kv.get("target_mark").map(|x| x.to_string()),
                mark_max: kv.get("mark_max").and_then(|x| x.parse().ok()).unwrap_or(1),
                mark_secs: kv.get("mark_secs").and_then(|x| x.parse().ok()).unwrap_or(10.0),
                mark_fx: std::array::from_fn(|r| {
                    kv.get(format!("mfx{r}").as_str()).map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.trim().parse().ok()).collect())
                }),
                target_take: kv.get("target_take").map(|x| x.to_string()),
                take_grow: kv.get("take_grow").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                take_pct: four_f(kv.get("take_pct")),
                take_fx: std::array::from_fn(|r| {
                    kv.get(format!("tfx{r}").as_str()).map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.trim().parse().ok()).collect())
                }),
                refund:kv.get("refund").and_then(|x| x.parse().ok()).unwrap_or(0.0),
            }),
            "stack" => Some(Kind::Stack {
                add: names(kv.get("add")),
                cond: kv.get("cond").map(|x| x.to_string()),
                clear: names(kv.get("clear")),
                consume: names(kv.get("consume")),
                max: if kv.contains_key("max") { four(kv.get("max")).map(|x| x.max(1) as u32) } else { [1; 4] },
                max_boost_key: kv.get("max_boost_key").map(|x| x.to_string()),
                max_boost: four(kv.get("max_boost")).map(|x| x.max(0) as u32),
                timeout: kv.get("timeout").and_then(|x| x.parse().ok()).unwrap_or(0.0),
                fx: std::array::from_fn(|r| {
                    kv.get(format!("fx{r}").as_str()).map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.trim().parse().ok()).collect())
                }),
                stamina: four(kv.get("stamina")),
                hp: four(kv.get("hp")),
                log: kv.get("log").map(|x| x.to_string()),
                reload_speed: four_f(kv.get("reload_speed")),
                act_speed: four_f(kv.get("act_speed")),
            }),
            "foe_aura" => Some(Kind::FoeAura {
                range: kv.get("range").and_then(|x| x.parse().ok()).unwrap_or(FOE_RANGE),
                fx: std::array::from_fn(|r| {
                    kv.get(format!("fx{r}").as_str()).map_or(Vec::new(), |s| s.split(',').filter_map(|x| x.trim().parse().ok()).collect())
                }),
            }),
            "foe_react" => kv.get("when").zip(kv.get("need")).map(|(w, n)| Kind::FoeReact {
                when: w.to_string(),
                need: n.to_string(),
                pct: four_f(kv.get("pct")),
                remove: kv.get("remove") == Some(&"1"),
                log: kv.get("log").map(|x| x.to_string()),
            }),
            "foe_spread" => Some(Kind::FoeSpread {
                range: kv.get("range").and_then(|x| x.parse().ok()).unwrap_or(6.0),
                amount: four_f(kv.get("amount")),
                kinds: names(kv.get("kinds")),
                log: kv.get("log").map(|x| x.to_string()),
            }),
            "rally" => kv.get("event").map(|e| Kind::Rally {
                event: e.to_string(),
                window: four_f(kv.get("window")),
                pct: four_f(kv.get("pct")),
                effect: four(kv.get("effect")),
                flash: four(kv.get("flash")),
                boost_key: kv.get("boost_key").map(|x| x.to_string()),
                boost: kv.get("boost").and_then(|x| x.parse().ok()).unwrap_or(1.0),
                log: kv.get("log").map(|x| x.to_string()),
            }),
            "free" => kv.contains_key("fp").then(|| Kind::Free { fp: four(kv.get("fp")) }),
            "quiet" => kv.contains_key("effect").then(|| Kind::Quiet {
                secs: kv.get("secs").and_then(|x| x.parse().ok()).unwrap_or(15.0),
                effect: four(kv.get("effect")),
            }),
            _ => None,
        };
        match kind {
            Some(_) if !d.affs.contains_key(&f[1]) => d.skipped.push(format!("规则 {} {}：没有这个词条的 aff 行", f[1], f[2])),
            Some(kind) => {
                match &kind {
                    Kind::While { effect, hp_flat, .. } => {
                        d.managed.extend(effect.iter().copied().filter(|&x| x > 0));
                        d.hp_flat |= hp_flat.iter().any(|&x| x > 0.0);
                    }
                    Kind::Stack { fx, add, .. } => {
                        d.managed.extend(fx.iter().flatten().copied().filter(|&x| x > 0));
                        if add.iter().any(|e| e == "mikiri") {
                            d.mikiri = true;
                            d.mikiri_keys.push(f[1].clone());
                        }
                    }
                    Kind::Rally { effect, .. } | Kind::Quiet { effect, .. } => d.managed.extend(effect.iter().copied().filter(|&x| x > 0)),
                    Kind::FoeAura { .. } | Kind::FoeReact { .. } | Kind::FoeSpread { .. } => d.foe_rules = true,
                    Kind::Free { .. } => {}
                    Kind::On { event, target_on, refund, mark_fx, .. } => {
                        d.mark_fx_ids.extend(mark_fx.iter().flatten().copied().filter(|&x| x > 0));
                        if event == "mikiri" {
                            d.mikiri = true;
                            d.mikiri_keys.push(f[1].clone());
                        }
                        if target_on == "break" {
                            d.foe_rules = true;
                        }
                        d.refunds |= *refund > 0.0;
                    }
                }
                d.rules.push(Rule { key: f[1].clone(), foes: foe_needs(&kind), requires: kv.get("requires").map(|x| x.to_string()), kind })
            }
            None => d.skipped.push(format!("规则 {} {}：类型不认识或缺参数", f[1], f[2])),
        }
    }
    d.ground = GROUND_KINDS.iter().filter_map(|k| d.tiers.get(*k)).flatten().map(|x| x.1).collect();
    if d.hp_flat {
        let ids: Vec<i32> = d.tiers.get("hpmax").map_or(Vec::new(), |t| t.iter().map(|x| x.1).collect());
        d.managed.extend(ids);
    }
    d
}

/// 只在地上放的冲击波（物理那套：碾压 / 反震 / 坠星；法球的魔力那套）：在空中要放的先排着，落地那一刻放，
/// GROUND_WAIT 内没落地就不放了（用户 2026-11-01：冲击波不能在半空放）。碾压（runtime）也走这里
const GROUND_KINDS: [&str; 2] = ["phys", "magic"];
const GROUND_WAIT: Duration = Duration::from_secs(3);
static GROUND_QUEUE: Mutex<Vec<(i32, Instant)>> = Mutex::new(Vec::new());

/// 在空中：排进落地队列，返回 true（调用的别挂）；在地上返回 false（调用的照常挂）
pub(crate) fn defer_until_ground(sp: i32, air: bool) -> bool {
    if air {
        GROUND_QUEUE.lock().unwrap_or_else(|e| e.into_inner()).push((sp, Instant::now()));
    }
    air
}

/// 落地了：排着的冲击波放出来（太久的丢掉）；返回要挂的效果
fn ground_due(air: bool) -> Vec<i32> {
    let mut q = GROUND_QUEUE.lock().unwrap_or_else(|e| e.into_inner());
    let n0 = q.len();
    q.retain(|(_, t)| t.elapsed() <= GROUND_WAIT);
    if n0 > q.len() {
        log(&format!("冲击波：在空中 {} 秒都没落地，{} 个没放", GROUND_WAIT.as_secs(), n0 - q.len()));
    }
    if air || q.is_empty() {
        return Vec::new();
    }
    let out: Vec<(i32, Instant)> = q.drain(..).collect();
    log(&format!("冲击波：落地了，放出空中排着的 {} 个（等了 {:.2} 秒）", out.len(), out[0].1.elapsed().as_secs_f32()));
    out.into_iter().map(|x| x.0).collect()
}

static DEF: OnceLock<Def> = OnceLock::new();
static DEF_ARC: OnceLock<Arc<Def>> = OnceLock::new();

/// 原来的 Def 的一份 Arc（不覆盖时 tick 用它，和覆盖过的一样拿 Arc）
fn base_arc(base: &'static Def) -> Arc<Def> {
    DEF_ARC.get_or_init(|| Arc::new(base.clone())).clone()
}

fn def() -> &'static Def {
    DEF.get_or_init(|| {
        // 攻击判定表单独一个文件（四千多行，runtime.txt 留着好读）；敌人的攻击判定表（见切）也是
        let read = |n: &str| fs::read_to_string(dir().join(n)).unwrap_or_default();
        let text = read("runtime.txt") + "\n" + &read("hitwin.txt") + "\n" + &read("foewin.txt");
        let d = parse(&text);
        if !d.hits.is_empty() {
            log(&format!("积木引擎：攻击判定表 {} 个动作", d.hits.len()));
        }
        if !d.foe_hits.is_empty() {
            log(&format!("积木引擎：敌人攻击判定表 {} 个模型、{} 个动作（见切）", d.foe_models.len(), d.foe_hits.len()));
        }
        for s in &d.skipped {
            log(&format!("积木引擎：跳过 {s}"));
        }
        d
    })
}

// ------------------------------------------------------------------ 词条数值随机二期（用户 2026-11-15「开始第二期吧」）
/// 规则里这一档的数改成身上那件生成装备的位置的精确数（gear::rule_nums；挂的效果行由 gear/valfx.rs 原地改写，编号不变）。
/// 覆盖过的 Def 按（键, 稀有度, 位置）缓存；攻击判定表这些大表是 Arc 共用的，复制一份只是规则和几张小表
static OVR: Mutex<Option<(Vec<(String, usize, i16)>, Arc<Def>)>> = Mutex::new(None);
static OVR_CACHE: Mutex<Vec<(Vec<(String, usize, i16)>, Arc<Def>)>> = Mutex::new(Vec::new());
const OVR_CACHE_MAX: usize = 32;

/// 规则里一个数（rr extract VAL_RULE_NUMS 的字段名）改成 v：只改这一档
fn set_num(kind: &mut Kind, field: &str, r: usize, v: f32) -> bool {
    let i = |x: &mut [i32; 4]| {
        x[r] = v.round() as i32;
        true
    };
    let f = |x: &mut [f32; 4]| {
        x[r] = v;
        true
    };
    match (kind, field) {
        (Kind::On { stamina, .. }, "stamina") | (Kind::Stack { stamina, .. }, "stamina") => i(stamina),
        (Kind::On { fp, .. }, "fp") => i(fp),
        (Kind::On { hp_pct, .. }, "hp_pct") => f(hp_pct),
        (Kind::On { fp_pct, .. }, "fp_pct") => f(fp_pct),
        (Kind::On { burst, .. }, "burst") => f(burst),
        (Kind::On { burst_flat, .. }, "burst_flat") => f(burst_flat),
        (Kind::On { chance, .. }, "chance") => f(chance),
        (Kind::On { haste, .. }, "haste") => f(haste),
        (Kind::On { take_pct, .. }, "take_pct") => f(take_pct),
        (Kind::On { cooldown, .. }, "cooldown") => f(cooldown),
        (Kind::On { foe_secs, .. }, "foe_secs") => f(foe_secs),
        (Kind::While { hp_flat, .. }, "hp_flat") => f(hp_flat),
        (Kind::Stack { act_speed, .. }, "act_speed") => f(act_speed),
        (Kind::Stack { reload_speed, .. }, "reload_speed") => f(reload_speed),
        _ => false,
    }
}

/// 按这一帧戴着的档（tiers）和身上生成装备的位置，得出要用的 Def：没有要覆盖的就是原来的
fn current_def(base: &'static Def, tiers: &HashMap<String, usize>) -> Arc<Def> {
    let keys = crate::gear::rule_keys();
    let mut sig: Vec<(String, usize, i16)> = Vec::new();
    if !keys.is_empty() {
        for (k, &r) in tiers {
            if keys.contains(k) {
                if let Some(p) = crate::gear::val_best(k, r) {
                    sig.push((k.clone(), r, (p * 1000.0).round() as i16));
                }
            }
        }
        sig.sort();
    }
    let mut g = OVR.lock().unwrap_or_else(|e| e.into_inner());
    if sig.is_empty() {
        if g.is_some() {
            log("积木引擎：规则里的数照回原来的（身上没有数值随机的积木词条了）");
            *g = None;
        }
        return base_arc(base);
    }
    if let Some((s0, d)) = g.as_ref().filter(|x| x.0 == sig) {
        let _ = s0;
        return d.clone();
    }
    let mut cache = OVR_CACHE.lock().unwrap_or_else(|e| e.into_inner());
    let d = match cache.iter().find(|x| x.0 == sig) {
        Some(x) => x.1.clone(),
        None => {
            let mut nd = base.clone();
            let mut done = Vec::new();
            for (k, r, p) in &sig {
                let nums = crate::gear::rule_nums(k, *r, *p as f32 / 1000.0);
                let mut nth = 0usize;
                for rule in nd.rules.iter_mut().filter(|x| &x.key == k) {
                    for (n, field, v) in nums.iter().filter(|x| x.0 == nth) {
                        let _ = n;
                        if set_num(&mut rule.kind, field, *r, *v) {
                            done.push(format!("{k}#{nth}.{field}={v}"));
                        } else {
                            log(&format!("积木引擎：{k} 第 {nth} 条规则没有字段 {field}，照原来的数"));
                        }
                    }
                    nth += 1;
                }
            }
            log(&format!("积木引擎：规则里的数按身上的装备改成 {}", done.join("，")));
            let d = Arc::new(nd);
            if cache.len() >= OVR_CACHE_MAX {
                cache.remove(0);
            }
            cache.push((sig.clone(), d.clone()));
            d
        }
    };
    *g = Some((sig, d.clone()));
    d
}

/// 身上有就无敌的效果（runtime::pre_physics 设无敌位）
pub fn iframes() -> &'static [i32] {
    &def().iframes
}

pub fn describe() -> String {
    let d = def();
    if d.rules.is_empty() {
        return "积木词条（没有规则，不管）".into();
    }
    let mut keys: Vec<&str> = d.rules.iter().map(|r| r.key.as_str()).collect();
    keys.dedup();
    format!("积木词条 {} 条（规则 {} 条{}）", keys.len(), d.rules.len(), if d.skipped.is_empty() { String::new() } else { format!("，跳过 {}", d.skipped.len()) })
}

// ------------------------------------------------------------------ 引擎（纯逻辑）
/// 周围的一个角色（目标层）
#[derive(Debug, Clone, Default)]
struct Foe {
    /// ChrIns 的地址
    id: usize,
    dist: f32,
    pos: [f32; 3],
    max_hp: i32,
    /// 阵营号（ChrIns.team_type）、算不算敌人（FRIENDLY_TEAMS）
    team: u8,
    hostile: bool,
    /// 当前动作编号
    anim: Option<i32>,
    /// 这一帧刚被玩家打中；被什么打中：Some("shot_hit") 箭 / 弩箭、Some("item_hit") 投掷道具、None 别的（近战、法术……），见 FOE_HIT_KINDS
    landed: bool,
    via: Option<&'static str>,
    /// 这一下是命中标记（land）生效的：玩家身上别的命中时触发被顶掉了，要补挂（SHADOW_*）；0 = 不用补（见 Def::atkfwd）
    shadow: u8,
    /// 架势（super_armor 模块的 sa_durability / 上限）；这一帧刚被你打崩架势；是 Boss（boss 行）
    poise: f32,
    poise_max: f32,
    broke: bool,
    boss: bool,
    /// 发作中的异常
    sts: Vec<Ail>,
    /// 这一下打中之前就在睡的话，那时身上的睡眠（规则的 target_has=sleep 按它算，不看 sts 里的睡眠：
    /// 打睡着的那一下睡眠刚挂上，不算「打中睡着的敌人」；打醒的那一下游戏可能先摘了睡眠，照样算。见 tick 的 pre_sleep）
    slept: Option<Ail>,
    /// NpcParam 编号（日志用）、体型半径、当前动作播到几成（0~1）、面朝的水平方向（单位向量 x, z）
    npc: i32,
    radius: f32,
    progress: f32,
    fwd: [f32; 2],
    /// 模型号（ChrIns.character_id，c4300 = 4300；人形是 0）、当前动作播了几秒（读不到是负的）：见切查攻击判定表用
    model: u32,
    play: f32,
    /// 这一帧同时也在播的其他动作（动作队列里这一帧播放时间变了的，不含上面读到的那个）：(动作编号, 播了几秒)。
    /// 梅瑟莫这类 Boss 身上一直叠着一层没有出招数据的动作（43000），读到的「当前动作」总是它，真正的出招在这里（用户 2026-11-12）
    layers: Vec<(i32, f32)>,
}

/// 场上的一颗子弹（见切）
#[derive(Debug, Clone, Default)]
struct Shot {
    pos: [f32; 3],
    /// 子弹参数的命中半径（取 hitRadius / hitRadiusMax 大的那个）
    radius: f32,
    /// 发射者是敌人
    hostile: bool,
}

/// 这个敌人的模型在攻击判定表里用哪个：自己的，没有就退到个位、十位清零的基础模型（自己没有动作包的变体，如 c4301 用 c4300 的）
fn foe_model(d: &Def, model: u32) -> Option<u32> {
    [model, model / 10 * 10, model / 100 * 100].into_iter().find(|m| d.foe_models.contains(m))
}

/// 见切看敌人这一刻的攻击判定：Some(true) 判定在（只认判定时间段本身，前后不留）；Some(false) 表里有这个模型，
/// 但这一刻没有判定（这个动作根本没有攻击判定也算：吼叫、强化、只放子弹的）；None 表里没有这个模型 → 用以前的近似
fn foe_hit_now(d: &Def, f: &Foe, a: i32, play: f32) -> Option<bool> {
    let m = foe_model(d, f.model)?;
    let Some(w) = d.foe_hits.get(&(m, a)) else { return Some(false) };
    Some(play >= 0.0 && w.iter().any(|&(s, e)| play >= s && play <= e))
}

/// 日志用：这个敌人这个动作的攻击判定时间段（表里没有这个模型 / 这个动作没有判定也写出来）
fn foe_win_text(d: &Def, f: &Foe, a: i32, play: f32) -> String {
    match foe_model(d, f.model) {
        None => format!("模型 c{:04} 不在判定表里，按进度 {:.0}% 估", f.model, f.progress * 100.0),
        Some(m) => match d.foe_hits.get(&(m, a)) {
            None => format!("第 {:.2} 秒，这个动作没有攻击判定", play),
            Some(w) => format!(
                "第 {:.2} 秒（判定 {}）",
                play,
                w.iter().map(|(s, e)| format!("{s:.2}–{e:.2}")).collect::<Vec<_>>().join("、")
            ),
        },
    }
}

/// 见切的判定（近似，见文件开头）：返回（日志里的说明, 用掉的敌人出招）
fn mikiri_reason(d: &Def, fr: &Frame, used: &HashMap<usize, i32>) -> Option<(String, Option<(usize, i32)>)> {
    for s in fr.shots.iter().filter(|s| s.hostile) {
        let dist = dist3(s.pos, fr.me);
        if dist <= s.radius + MIKIRI_BODY {
            return Some((format!("子弹（命中半径 {:.1}，距离 {dist:.1}）", s.radius), None));
        }
    }
    for f in fr.foes.iter().filter(|f| f.hostile) {
        let Some(a0) = f.anim else { continue };
        // 读到的当前动作，再加上这一帧同时在播的（叠着的那层下面才是出招，见 Foe::layers）
        for (k, (a, play)) in std::iter::once((a0, f.play)).chain(f.layers.iter().copied()).enumerate() {
            if used.get(&f.id) == Some(&a) {
                continue;
            }
            match foe_hit_now(d, f, a, play) {
                Some(true) => {}
                Some(false) => continue,
                None => {
                    // 表里没有的模型照旧按动作编号段和进度估，只看当前动作
                    if k > 0 || !is_attack(a) || f.progress < MIKIRI_PROGRESS.0 || f.progress > MIKIRI_PROGRESS.1 {
                        continue;
                    }
                }
            }
            let (flat, ang) = foe_geom(fr, f);
            if flat > MIKIRI_REACH + f.radius {
                continue;
            }
            if ang > MIKIRI_ARC {
                continue;
            }
            return Some((
                format!("近战（NPC {} 动作 {a}{} {} 距离 {flat:.1} 体型 {:.1} 夹角 {ang:.0}°）", f.npc, if k > 0 { "（叠着播的）" } else { "" },
                        foe_win_text(d, f, a, play), f.radius),
                Some((f.id, a)),
            ));
        }
    }
    None
}

/// 敌人到玩家的水平距离、敌人面朝方向和「敌人→玩家」的夹角（度）
fn foe_geom(fr: &Frame, f: &Foe) -> (f32, f32) {
    let (dx, dz) = (fr.me[0] - f.pos[0], fr.me[2] - f.pos[2]);
    let flat = (dx * dx + dz * dz).sqrt();
    let ang = if flat < 0.01 { 0.0 } else { ((dx * f.fwd[0] + dz * f.fwd[1]) / flat).clamp(-1.0, 1.0).acos().to_degrees() };
    (flat, ang)
}

/// 一次翻滚里见切没成立时的调参日志：帧数、无敌帧数、最近一个出招的敌人 / 最近的敌人 / 最近的敌方子弹（距离, 说明）
#[derive(Default)]
struct RollDbg {
    frames: u32,
    iframes: u32,
    /// 翻滚时见切还在冷却
    cooling: bool,
    atk: Option<(f32, String)>,
    near: Option<(f32, String)>,
    shot: Option<(f32, String)>,
}

impl RollDbg {
    fn keep(slot: &mut Option<(f32, String)>, d: f32, s: impl FnOnce() -> String) {
        if slot.as_ref().is_none_or(|x| d < x.0) {
            *slot = Some((d, s()));
        }
    }

    /// 无敌帧里看一眼周围（出招的：表里有这个模型就看这个动作有没有攻击判定，没有这个模型就看动作编号在不在 3000 段）
    fn observe(&mut self, d: &Def, fr: &Frame) {
        for f in fr.foes.iter() {
            let (flat, ang) = foe_geom(fr, f);
            let who = format!("NPC {} 阵营 {}{}", f.npc, f.team, if f.hostile { "" } else { "（不算敌人）" });
            let layers = if f.layers.is_empty() {
                String::new()
            } else {
                format!("（同时在播 {}）", f.layers.iter().map(|(a, p)| format!("{a} 第 {p:.2} 秒")).collect::<Vec<_>>().join("、"))
            };
            Self::keep(&mut self.near, flat, || format!("{who} 动作 {:?}{layers} 距离 {flat:.1}", f.anim));
            let attacking = |a: i32| match foe_model(d, f.model) {
                Some(m) => d.foe_hits.contains_key(&(m, a)),
                None => is_attack(a),
            };
            for (a, play) in f.anim.map(|a| (a, f.play)).into_iter().chain(f.layers.iter().copied()).filter(|&(a, _)| attacking(a)) {
                Self::keep(&mut self.atk, flat, || {
                    format!("{who} 动作 {a} {} 距离 {flat:.1}（够得着 {:.1}）夹角 {ang:.0}°（反过来算 {:.0}°）", foe_win_text(d, f, a, play),
                            MIKIRI_REACH + f.radius, 180.0 - ang)
                });
            }
        }
        for s in fr.shots.iter().filter(|s| s.hostile) {
            let d = dist3(s.pos, fr.me);
            Self::keep(&mut self.shot, d, || format!("距离 {d:.1} 命中半径 {:.1}", s.radius));
        }
    }

    fn line(&self) -> String {
        let show = |x: &Option<(f32, String)>| x.as_ref().map_or("无".to_string(), |x| x.1.clone());
        format!("见切没成立（{}翻滚 {} 帧，其中无敌 {} 帧）：最近出招的角色 {}；最近的角色 {}；最近的敌方子弹 {}", if self.cooling { "冷却中，" } else { "" },
                self.frames, self.iframes, show(&self.atk),
                show(&self.near), show(&self.shot))
    }
}

/// 四元数的水平前方（+Z 转过去，单位向量 x, z）；正负由 tick 的朝向校准定
fn flat_forward(q: &eldenring::rotation::Quaternion) -> [f32; 2] {
    let (x, y, z, w) = (q.0, q.1, q.2, q.3);
    let (fx, fz) = (2.0 * (x * z + w * y), 1.0 - 2.0 * (x * x + y * y));
    let l = (fx * fx + fz * fz).sqrt();
    if l < 1e-6 { [0.0, 0.0] } else { [fx / l, fz / l] }
}

/// 发作中的一个异常（敌人身上 spCategory 10003~10010 的效果）
#[derive(Debug, Clone, PartialEq)]
struct Ail {
    kind: &'static str,
    sp: i32,
    /// 还剩几秒、几秒一跳、一跳：最大血量的百分比 + 点数
    left: f32,
    every: f32,
    rate: f32,
    point: i32,
}

fn ail_kind(sp_category: i32) -> Option<&'static str> {
    Some(match sp_category {
        10003 => "bleed",
        10004 => "poison",
        10005 => "rot",
        10007 => "frost",
        10008 => "death",
        10009 => "sleep",
        10010 => "madness",
        _ => return None,
    })
}

impl Ail {
    fn tick(&self, max_hp: i32) -> f32 {
        self.rate / 100.0 * max_hp as f32 + self.point as f32
    }

    /// 剩下的伤害：持续掉血的（毒、腐败）按剩下几跳算；只跳一次的（出血、冻伤）算一跳
    fn rest(&self, max_hp: i32) -> f32 {
        let n = if self.every > 0.0 && self.every < self.left + self.every { (self.left / self.every).floor().max(1.0) } else { 1.0 };
        n * self.tick(max_hp)
    }
}

fn dist3(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

#[derive(Debug, PartialEq)]
enum Act {
    Apply(i32),
    /// 法球那档：挂这个放子弹的效果，挂之前把效果的点位改成拿法器那只手的武器点位（orbshot.rs 的 aim）
    Shot(i32),
    Remove(i32),
    /// 给周围的角色挂 / 摘效果（目标层）
    FoeApply(usize, i32),
    /// 给周围的角色扣这么多血（有伤害数字），见 foe_hp_exact
    FoeHp(usize, i32),
    FoeRemove(usize, i32),
    /// 改周围角色的动作速度（见切）
    FoeSpeed(usize, f32),
    /// 清 / 不清玩家的无敌位（影步）
    CutIFrames(bool),
    Stamina(i32),
    Fp(i32),
    Hp(i32),
    /// 扣血，可以扣到 0（燃血：用血代替精力，血不够会死）
    HpCost(i32),
    /// 背包里这件（类别, 编号）加回 1 个
    Refund(u8, u32),
    /// 把周围这个角色的架势设成这么多
    FoePoise(usize, f32),
    /// 物理冲击波的实时伤害（反震 / 坠星）：tick 挑一套 shocklive 专用行，写进这么多伤害和右手武器的重击削韧再放；写不进去按 phys 档位
    ShockLive(f32),
    Log(String),
}

#[derive(Default)]
struct RState {
    stacks: u32,
    last_add: Option<Instant>,
    cool_until: Option<Instant>,
    /// 等着消耗：(当时的动作编号, 发生的时间)
    consume: Option<(Option<i32>, Instant)>,
    /// 上一帧已经戴着（fp_to_hp：刚戴上 / 读档那一帧只补满专注，不扣血）
    armed: bool,
    /// rally：窗口到什么时候、还能回多少、这段时间一共损失多少；on 的 deny_heal：扣回回血到什么时候
    until: Option<Instant>,
    pool: i32,
    lost: i32,
    /// take_full 拿走了全部层数：这一帧不再加层
    hold_add: bool,
    /// while 的 prog_from：看着的动作、事件在这个动作里第一次出现时的播放时间
    prog_anim: Option<i32>,
    prog_t0: Option<f32>,
    /// while 的 prog 诊断（相杀没触发，用户 2026-11-04）：条件成立着的动作、最大进度、窗口开过没有、这个动作的播放时间 / 长度
    diag_anim: Option<i32>,
    diag_max: f32,
    diag_open: bool,
    diag_t: (f32, f32),
}

#[derive(Default)]
struct Engine {
    st: Vec<RState>,
    /// 物理冲击波的实时伤害：下一次用第几套 shocklive 行
    shock_next: usize,
    /// 这一帧见切成立了、身上戴着听见切的词条：tick 放防御反击的音效（clash::mikiri_sound）
    mikiri_sound: bool,
    /// 周围角色上一次扫到时的动作队列（动作编号, 播放时间的位）：这一帧变了的就是这一帧也在播的（Foe::layers）
    queue_prev: HashMap<usize, [(i32, u32); 10]>,
    /// 玩家现在的动作、播到哪、什么时候开始的（take_fresh 看命中是不是叠层加上之后新出的招）
    act_anim: Option<i32>,
    act_t: f32,
    act_at: Option<Instant>,
    /// take_fresh 不算的命中，日志记了几行（一次进游戏最多 FRESH_LOG_MAX 行）
    fresh_told: u32,
    last_present: HashSet<String>,
    /// 前 STAMINA_LOOKBACK 帧的精力（算「这一下掉了多少」）
    stamina_hist: VecDeque<i32>,
    /// guard_scale：最近一次量到的防御消耗、什么时候
    guard_cost: Option<(i32, Instant)>,
    /// target_hp_pct：每个敌人被打中第几下、上一下什么时候；每个敌人每档扣血效果上一次挂的时间
    foe_hits: HashMap<usize, (u32, Instant)>,
    foe_tier_at: HashMap<(usize, i32), Instant>,
    /// 敌人身上的标记（猎印）：(敌人, 标记名) → (层数, 到什么时候, 挂着的那行效果)
    foe_marks: HashMap<(usize, String), (u32, Instant, i32)>,
    /// 崩架势（tick 用）：每个敌人上一帧的架势、上一次被你打中的时间
    foe_poise: HashMap<usize, f32>,
    foe_land_at: HashMap<usize, Instant>,
    /// 用掉的弹药 / 投掷道具：(类别, 编号, 什么时候, 返还过没有)
    used: VecDeque<(u8, u32, Instant, bool)>,
    /// 无尽箭袋（free）：这一帧要不要打开（「箭矢不消耗」,「道具不消耗」）（tick 照这个开关，set_free）；
    /// 付过专注的这一下射击 / 投掷从什么时候起（动作还在就一直算付过）
    free: (bool, bool),
    free_shot: Option<Instant>,
    free_throw: Option<Instant>,
    /// 连射：这一帧拉弓 / 换弹的速度倍数（tick 写进 RELOAD_MULT）
    reload_mult: f32,
    /// 这一帧玩家动作的速度倍数（tick 写进 ACTION_MULT）；0 = 还没算过
    action_mult: f32,
    /// 处刑、影步（on 的 haste）：词条 → 到什么时候、倍数（各算各的，同时在就相乘）
    haste: HashMap<String, (Instant, f32)>,
    /// 见切触发的加速（影步）单独挂的光晕：词条 → 这一轮加速第一次看到的时间、挂上了没有（tick 用，late_glow_step）
    late_glow: HashMap<String, (Instant, bool)>,
    /// tick 用：上一帧背包里每种弹药 / 投掷道具的数量（没戴要返还的词条时是 None）
    ammo_cnt: Option<HashMap<(u8, u32), u32>>,
    /// while 的 poise_radius（千钧）：满蓄力这一击的窗口到什么时候（含刚结束的 POISE_GRACE）；挂了 poise_fx 的普通敌人；
    /// 这一击已经先扣过架势的 Boss；其中还没被打中的 → 扣了多少（没打中就加回去）；扣了架势的 Boss → (保持在多少, 保持到什么时候)
    poise_until: Option<Instant>,
    poise_fx_on: HashSet<usize>,
    poise_hit: HashSet<usize>,
    poise_pre: HashMap<usize, f32>,
    poise_hold: HashMap<usize, (f32, Instant)>,
    /// tick 用：翻滚中上一帧的动作和播放时间（连滚的下一段）
    roll_anim: Option<(i32, f32)>,
    last_hp: Option<i32>,
    /// 上一帧引擎自己让血量变了多少（tick 照实际改的填）：算「自然」掉血 / 回血时扣掉
    own_hp: i32,
    /// 最近一次受击事件
    last_hit: Option<Instant>,
    /// 还没对上受击事件的掉血（掉血先于受击事件到的时候）
    pending: Option<(i32, Instant)>,
    /// 上一帧身上有命中标记的角色（tick 用）
    land_seen: HashSet<usize>,
    /// 联机时「命中标记不是你打的」记过几次（最多记 6 次）
    not_mine_logged: u32,
    /// 联机时最近的玩家子弹：(时间, 位置, 是不是自己放的)，给查不到攻击者的命中归属用（Attrib）
    coop_bullets: Vec<(Instant, [f32; 3], bool)>,
    /// 睡眠（惊醒，tick 用）：在睡的角色 → 身上的睡眠、什么时候睡着、上次扫到还在睡的时间；
    /// 被打中（命中 / 子弹标记刚出现）之前就在睡的角色 → 那时的睡眠、什么时候被打（等这一下算打中时交给规则，见 Foe::slept）
    sleep_seen: HashMap<usize, Sleeping>,
    pre_sleep: HashMap<usize, (Ail, Instant)>,
    /// 睡着 / 醒来的诊断这次进游戏写了几行（最多 SLEEP_DIAG_MAX）
    sleep_diag: u32,
    /// 上一帧戴着的词条（变了记一行，最多 WORN_DIAG_MAX 行）
    worn_prev: Vec<String>,
    worn_diag: u32,
    /// 上一帧每个角色身上发作中的异常（找新发作的）
    foe_kinds: HashMap<usize, HashSet<&'static str>>,
    /// 随机数（目标层随机挑异常）
    seed: u64,
    /// 见过的阵营号（tick 写日志用）
    teams_seen: HashSet<u8>,
    /// 这次翻滚已经见切过；见切用掉的敌人出招（敌人 → 动作编号，动作换了就去掉）
    dodged: bool,
    mikiri_used: HashMap<usize, i32>,
    /// 这次翻滚的调参日志（戴着见切类词条才记）
    roll_dbg: Option<RollDbg>,
    /// 朝向校准（tick）：自由跑动时「+Z 前方」和位移同向的累计、样本数
    cal: (f32, u32),
    /// 被挡住的事件 → 到什么时候（on 的 rest，比如见切的冷却）
    blocked: HashMap<String, Instant>,
    /// 减速中的敌人：动作速度倍数、到什么时候
    slowed: HashMap<usize, (f32, Instant)>,
    /// 影步：上一次发出的清无敌位
    cut: bool,
    /// burst_each 排着的后几下：(什么时候放, 放哪个效果)
    burst_queue: VecDeque<(Instant, i32, bool)>,
    /// 命中类脉冲（PULSE_KEYS）刚到、还在等敌人身上的命中标记：脉冲 → 什么时候到的
    pulse_wait: HashMap<&'static str, Instant>,
    /// tick 用：上一帧身上有箭 / 道具命中标记的角色；命中标记（land）先到、还在等子弹标记的角色 → 什么时候到的；
    /// 被箭 / 道具打中的角色 → 什么时候（这一下随后到的 land 不再另算一次）
    hit_seen: HashMap<&'static str, HashSet<usize>>,
    land_wait: HashMap<usize, Instant>,
    bullet_at: HashMap<usize, Instant>,
    /// 被箭打中、land 还没到的角色 → 什么时候（到了才知道这一箭是 land 生效的，见 Foe::shadow）
    shot_wait: HashMap<usize, Instant>,
    /// 命中补挂的日志写了几行（最多 ATKFWD_LOG）
    atkfwd_told: u32,
    /// 诊断日志（戴着叠标记的词条时记箭命中 / 命中 / 挂标记）：这次进游戏已经写了几行（最多 DIAG_MAX）
    diag_used: u32,
    /// 燃血扣血的日志这次进游戏写了几行（最多 BLOOD_LOG_MAX）
    blood_logs: u32,
    /// 燃血诊断：精力掉了一大截却没换成扣血，写了几行（最多 BLOOD_DIAG_MAX）
    blood_diag: u32,
    /// 法球命中探针：上一次射出法球的时间和那一下算的伤害（那档的数值）；探针开着时周围敌人的血量；写了几行（最多 ORB_PROBE_MAX）
    orb_probe: Option<(Instant, i32)>,
    orb_hp: HashMap<usize, i32>,
    orb_probe_logs: u32,
    /// 开发工具 devsp.txt：上次看到的修改时间、帧计数
    devsp_mtime: Option<std::time::SystemTime>,
    devsp_wait: u32,
    /// 扫周围角色的帧计数（没戴要看周围的词条时只为全局的发狂每 10 帧扫一次）
    scan_wait: u32,
    /// 开发工具挂的效果：(角色, 效果, 什么时候挂的)，1 秒后再看一次还在不在
    devsp_watch: Vec<(usize, i32, Instant)>,
    /// 敌人血量诊断：角色 → (上一次看到的血量上限, 什么时候)；这次进游戏写了几行（最多 HP_DIAG_MAX）
    hp_seen: HashMap<usize, (i32, Instant)>,
    hp_diag: u32,
    /// 敌人异常抗性诊断：角色 → (上一次读到的抗性模块, 什么时候)；见过上限的敌人编号；这次进游戏写了几行（最多 RES_DIAG_MAX）
    res_seen: HashMap<usize, ([i32; 14], Instant)>,
    res_npcs: HashSet<i32>,
    res_diag: u32,
    /// 连击值：上一帧身上有没有 hit_self、这一下什么时候到的（还没判）；最近一次正常的命中标记
    self_hit_on: bool,
    self_hit_at: Option<Instant>,
    last_land: Option<Instant>,
    /// 连击值诊断：累积效果第一次挂的时间、记过「在不在身上」没有；记过「打中了却找不到目标」没有
    acc_diag: Option<Instant>,
    acc_seen: bool,
    self_hit_none: bool,
    /// 不在距离列表里、按身上的命中标记补进来的角色（日志每种只记一次）
    extra_npcs: HashSet<i32>,
    /// 不在距离列表里、按物理位置在 EXTRA_RANGE 内的敌对角色（每 EXTRA_EVERY 帧重扫）；日志记过的（每种一次）
    extra_foes: Vec<usize>,
    extra_near_npcs: HashSet<i32>,
    /// 物理位置算的距离和游戏的对不上，记过日志了
    chunk_bad_told: bool,
}

/// 不在距离列表里的敌人：每多少帧扫一遍在场角色、多少米内（全局地图坐标）算周围的敌人
const EXTRA_EVERY: u32 = 30;
const EXTRA_RANGE: f32 = 20.0;

/// 千钧压低的架势保持多久（期间游戏自己回上来的压回去；被打崩 / 到时间交还给游戏）
const POISE_HOLD: Duration = Duration::from_secs(15);
/// 千钧：满蓄力的标记消失后这一击还算多久（命中标记晚 LAND_HOLD 到，连击值扫全场晚 HIT_SELF_WAIT）
const POISE_GRACE: Duration = Duration::from_millis(500);
/// 连击值：hit_self 到了以后等多久看有没有正常的命中标记（命中标记还要等 LAND_HOLD）
const HIT_SELF_WAIT: Duration = Duration::from_millis(150);

/// 在睡的角色（Engine::sleep_seen）
#[derive(Debug, Clone)]
struct Sleeping {
    ail: Ail,
    since: Instant,
    last: Instant,
}

/// 「上一次扫到时在睡」最多隔多久还算数（没戴看周围的词条时 10 帧扫一次）
const SLEEP_GAP: Duration = Duration::from_millis(500);
/// 睡着 / 醒来的诊断、戴着的词条变了的日志，每次进游戏最多写几行
const SLEEP_DIAG_MAX: u32 = 60;
const WORN_DIAG_MAX: u32 = 100;

/// 戴着的词条变了记一行（换武器、换护符；读图时标记会掉了又回来，有上限）
fn worn_diag(eng: &mut Engine, tiers: &HashMap<String, usize>) {
    let mut now: Vec<&String> = tiers.keys().collect();
    now.sort();
    if now.len() == eng.worn_prev.len() && now.iter().zip(&eng.worn_prev).all(|(a, b)| *a == b) {
        return;
    }
    if eng.worn_diag < WORN_DIAG_MAX {
        eng.worn_diag += 1;
        let on: Vec<&str> = now.iter().filter(|k| !eng.worn_prev.contains(k)).map(|k| k.as_str()).collect();
        let off: Vec<&str> = eng.worn_prev.iter().filter(|k| !tiers.contains_key(*k)).map(|k| k.as_str()).collect();
        log(&format!(
            "积木引擎：戴着的词条变了{}{}（现在 {} 条）",
            if on.is_empty() { String::new() } else { format!("，戴上 {}", on.join("、")) },
            if off.is_empty() { String::new() } else { format!("，摘下 {}", off.join("、")) },
            now.len()
        ));
    }
    eng.worn_prev = now.into_iter().cloned().collect();
}

/// 睡眠（惊醒）：打中的那一下会改睡眠——打睡着的那一下睡眠刚挂上，打醒的那一下游戏可能先摘掉——
/// 所以按「这一下打中之前（上一次扫到时）在不在睡」算：命中 / 子弹标记刚出现（struck）时记下那时的睡眠，
/// 这一下算打中（landed，近战要等 LAND_HOLD）时交出去（Foe::slept）。顺便记睡着 / 醒来的诊断（敌对角色）。
#[allow(clippy::too_many_arguments)]
fn track_sleep(
    eng: &mut Engine, id: usize, sts: &[Ail], struck: bool, landed: bool, hit: bool, now: Instant, who: impl Fn(&str) -> String, hostile: bool,
) -> Option<Ail> {
    let asleep = sts.iter().find(|a| a.kind == "sleep");
    let before = eng.sleep_seen.get(&id).filter(|s| now.duration_since(s.last) <= SLEEP_GAP).cloned();
    if struck {
        match &before {
            Some(s) => {
                eng.pre_sleep.insert(id, (s.ail.clone(), now));
            }
            None => {
                eng.pre_sleep.remove(&id);
            }
        }
    }
    let slept = if landed { eng.pre_sleep.remove(&id).map(|(a, _)| a) } else { None };
    let msg = match (asleep, &before) {
        (Some(a), Some(_)) => {
            if let Some(s) = eng.sleep_seen.get_mut(&id) {
                s.ail = a.clone();
                s.last = now;
            }
            None
        }
        (Some(a), None) => {
            eng.sleep_seen.insert(id, Sleeping { ail: a.clone(), since: now, last: now });
            Some(who(&format!("睡着了，睡眠效果 {}（还剩 {:.0} 秒）{}", a.sp, a.left, if struck { "，就是这一下打睡着的" } else { "" })))
        }
        (None, Some(s)) => {
            eng.sleep_seen.remove(&id);
            let why = if slept.is_some() || eng.pre_sleep.contains_key(&id) || hit { "被打醒（这一下之前在睡）" } else { "没被打（时间到或别的原因）" };
            Some(who(&format!("醒了，睡了 {:.1} 秒，{why}", now.duration_since(s.since).as_secs_f32())))
        }
        (None, None) => None,
    };
    if let Some(m) = msg.filter(|_| hostile && eng.sleep_diag < SLEEP_DIAG_MAX) {
        eng.sleep_diag += 1;
        log(&format!("睡眠（诊断）：{m}"));
    }
    slept
}

/// 敌人血量诊断每次进游戏最多写几行
const HP_DIAG_MAX: u32 = 40;
/// 敌人异常抗性诊断每次进游戏最多写几行
const RES_DIAG_MAX: u32 = 60;
/// 抗性模块里七种异常的顺序（同 Souls Vision 的 ChrResistModule）
const RES_ZH: [&str; 7] = ["毒", "腐败", "出血", "咒死", "冻伤", "睡眠", "发狂"];

/// 角色的异常抗性模块（ChrInsModuleContainer +0x20）：+0x10 起七个「还差多少发作」、+0x2C 起七个上限（顺序见 RES_ZH；上限 999 = 免疫）
pub(crate) fn resist_of(c: &ChrIns) -> Option<[i32; 14]> {
    let mc = &*c.modules as *const _ as *const usize;
    let rm = unsafe { mc.add(4).read() };
    (rm != 0).then(|| unsafe { std::ptr::read_unaligned((rm + 0x10) as *const [i32; 14]) })
}

/// 诊断用：「毒 剩余/上限，腐败 …」
fn resist_text(r: &[i32; 14]) -> String {
    RES_ZH.iter().enumerate().map(|(k, n)| format!("{n} {}/{}", r[k], r[k + 7])).collect::<Vec<_>>().join("，")
}

/// 开发工具：角色身上这个效果的状态（在不在、还剩几秒）
fn sp_state(c: &eldenring::cs::ChrIns, sp: i32) -> String {
    match c.special_effect.entries().find(|e| e.param_id == sp) {
        Some(e) => format!("身上有，还剩 {:.1} 秒", e.removal_timer),
        None => "身上没有".into(),
    }
}

/// burst_each：一颗接一颗的间隔（法球射辉石魔砾）
const BURST_GAP: Duration = Duration::from_millis(120);
/// 诊断日志每次进游戏最多写几行
const DIAG_MAX: u32 = 60;
/// 燃血（精力改扣血）每次进游戏最多记几行
const BLOOD_LOG_MAX: u32 = 40;
/// 燃血诊断：一帧掉这么多精力（跑动每帧只掉一点）、没在翻滚 / 后撤，却没换成扣血，写一行当时的事件；每次进游戏最多几行
const BLOOD_DIAG_MIN: i32 = 8;
const BLOOD_DIAG_MAX: u32 = 12;
/// 法球命中探针：射出后多久内周围敌人掉的血算这一颗的（写日志对一下算的伤害和实际打出来的），每次进游戏最多几行
const ORB_PROBE_WIN: Duration = Duration::from_millis(2500);
const ORB_PROBE_MAX: u32 = 40;
/// 箭 / 投掷道具打中：标记挂在被打的敌人身上（子弹命中时挂，重随 ranged_hits 塞进子弹的效果位），tick 扫敌人时看谁身上刚出现，
/// 这一下算「被箭 / 道具打中」（Foe::via），和飞行时间无关、每个敌人分开算。
/// （以前用子弹的 spEffectIDForShooter 挂给射手当脉冲：那个是发射时挂的，2026-10-28 游戏里量到比命中早 0.35~0.56 秒 = 飞行时间，
/// 射空也算、射远了对不上，改成这样）
pub(crate) const FOE_HIT_KINDS: [&str; 3] = ["cast_hit", "shot_hit", "item_hit"];   // cast_hit：法术、调香等别的道具放的子弹
/// 命中标记（land）和子弹标记不一定同一帧到：land 先到的等 LAND_HOLD 看子弹标记来不来，不来才算近战等别的命中；
/// 子弹标记先到的，BULLET_LAND_SUPPRESS 内这个敌人随后到的 land 是同一下，不另算
const LAND_HOLD: Duration = Duration::from_millis(60);
/// Foe::shadow：近战等（玩家身上的都补）；箭（只补不分手的：油脂只管手上的武器，蛇弓的不分手）
const SHADOW_MELEE: u8 = 1;
const SHADOW_SHOT: u8 = 2;
const ATKFWD_LOG: u32 = 20;
const BULLET_LAND_SUPPRESS: Duration = Duration::from_millis(250);
/// 施法的脉冲 cast（玩家脚本 MagicFire* 时挂）比法术打中早：脉冲到了先等着，PULSE_GRACE 内的下一次命中（land）算它的
/// （cond / unless 都按这样看），算过就用掉。法术飞得比这久的还是会被当成别的命中（近身的 unless=cast 漏掉），法术没有子弹标记
const PULSE_KEYS: [&str; 1] = ["cast"];
const PULSE_GRACE: Duration = Duration::from_millis(600);
const FRESH_LOG_MAX: u32 = 30;
/// 开发工具：dll\dark_core\devsp.txt，每保存一次按每行挂一次效果（打包不带这个文件）。
/// 一行：「我 <效果编号>」挂给自己；「敌 <效果编号>」挂给 15 米内最近的敌人。# 开头是注释。
/// 进游戏时已经在的那份不执行（同 devgive.txt）。结果写日志（开头「开发工具（效果）」）
const DEVSP_FILE: &str = "devsp.txt";
/// 悬浮窗口（dll\dark_dev）写的请求：格式同 devsp.txt，有就执行、执行完删掉
const DEVSP_REQ_FILE: &str = "devsp_req.txt";
const DEVSP_RANGE: f32 = 15.0;

/// 这一帧的输入（tick 从玩家身上读）
struct Frame<'a> {
    /// 戴着的词条 → 稀有度（0~3）
    tiers: &'a HashMap<String, usize>,
    /// 挂着的事件标记
    present: &'a HashSet<String>,
    /// 玩家身上现在的效果
    have: &'a HashSet<i32>,
    /// 当前动作编号、播放到第几秒、动作长度（秒，0 = 不知道）
    anim: Option<i32>,
    anim_t: f32,
    anim_len: f32,
    now: Instant,
    /// 这一下普通攻击实际使用的武器上的特效标记（左手 / 右手按当前出招手算）
    weapon_markers: &'a HashSet<i32>,
    /// 右手武器攻击力（冲击波按它算）
    ar: f32,
    /// 触发词条的属性倍率（物理 魔力 火 雷 圣，procs 模块按人物属性算）：固定伤害的冲击波（法球）、引爆乘它
    scale: [f32; 5],
    /// 拿着的法器的法术补正面板 ÷ 200（没有法器按面板 100 算）：burst_spell 的法球乘它（spellbase 模块）
    spell: f32,
    /// 难度的「玩家造成伤害」倍率（难度效果的物理伤害倍率 = 1 / 敌人血量倍率；没有难度效果 = 1）。直接扣血的（引爆 / 近身、巨人杀手、
    /// 瘟疫爆发、碎冰）不走攻击结算，难度效果管不到，算出来的量乘它（用户 2026-11-13「异常骨灰不管 其他的要纳入」）
    dealt: f32,
    stamina: i32,
    max_stamina: i32,
    hp: i32,
    max_hp: i32,
    /// 基础血量上限（只按生命力，不算效果的倍率；血瓮按它折百分比）
    base_hp: i32,
    fp: i32,
    max_fp: i32,
    /// 周围的角色（目标层）
    foes: &'a [Foe],
    /// 这一帧扫过周围（没扫的帧 foes 是空的，别当成「周围没人」去清状态）
    scanned: bool,
    /// 见切：玩家位置、这一帧真正的翻滚无敌、场上的子弹
    me: [f32; 3],
    iframe: bool,
    shots: &'a [Shot],
    /// 这一帧用掉的弹药 / 投掷道具（背包里数量变少的，类别 + 编号，每少一个算一次）
    used: &'a [(u8, u32)],
}

fn costs(acts: &mut Vec<Act>, r: usize, stamina: &[i32; 4], hp: &[i32; 4]) {
    if stamina[r] != 0 {
        acts.push(Act::Stamina(stamina[r]));
    }
    if hp[r] != 0 {
        acts.push(Act::Hp(hp[r]));
    }
}

/// 用掉的弹药 / 投掷道具里，within 内最近一个还没返还过的：记成返还过，返回它
fn take_used(used: &mut VecDeque<(u8, u32, Instant, bool)>, now: Instant, within: Duration) -> Option<(u8, u32)> {
    let e = used.iter_mut().rev().find(|x| !x.3 && now.duration_since(x.2) <= within)?;
    e.3 = true;
    Some((e.0, e.1))
}

impl Engine {
    /// while / stack 挂的效果是不限时的（限时的话快到期时状态图标会一直闪）：每帧对照「该挂的」和身上实际有的——
    /// 该有没有就挂，引擎管的效果（Def::managed）不该有却有就摘（摘下装备、读档、换稀有度留下的也能清掉）。
    /// on 规则先做（take 会把别的词条的层数清掉，清掉的层数这一帧就不挂效果）
    fn step(&mut self, d: &Def, fr: &Frame) -> Vec<Act> {
        let (tiers, present, have, anim, now) = (fr.tiers, fr.present, fr.have, fr.anim, fr.now);
        let mut fired: HashSet<&str> = present.difference(&self.last_present).map(|s| s.as_str()).collect();
        // 动作换了、或者同一个动作重新从头播：新的一个动作从这一帧开始
        if anim != self.act_anim || fr.anim_t + 0.05 < self.act_t || self.act_at.is_none() {
            self.act_at = Some(now);
        }
        self.act_anim = anim;
        self.act_t = fr.anim_t;
        // 命中脉冲先到就等着，这一帧有命中（land）就算它的、用掉（见 PULSE_KEYS）
        for k in PULSE_KEYS {
            if fired.contains(k) {
                self.pulse_wait.insert(k, now);
            }
        }
        self.pulse_wait.retain(|_, t| now.duration_since(*t) <= PULSE_GRACE);
        let late: HashSet<&str> = if present.contains("land") { self.pulse_wait.drain().map(|(k, _)| k).collect() } else { HashSet::new() };
        let has = |c: &str| present.contains(c) || late.contains(c);
        self.blocked.retain(|_, t| now < *t);
        self.foe_hits.retain(|_, (_, t)| now.duration_since(*t) < Duration::from_secs(30));
        self.foe_tier_at.retain(|_, t| now.duration_since(*t) < TIER_BUSY);
        let mut early: Vec<Act> = Vec::new();
        // burst_each 排着的后几下：到时间就放
        while self.burst_queue.front().is_some_and(|x| now >= x.0) {
            if let Some((_, sp, shot)) = self.burst_queue.pop_front() {
                early.push(if shot { Act::Shot(sp) } else { Act::Apply(sp) });
            }
        }
        // 用掉的弹药 / 投掷道具（回收从里面挑）
        for &(c, id) in fr.used {
            self.used.push_back((c, id, now, false));
        }
        while self.used.front().is_some_and(|x| now.duration_since(x.2) > Duration::from_secs(30)) {
            self.used.pop_front();
        }
        // 到期的标记（猎印）：摘掉效果
        let expired: Vec<(usize, String)> = self.foe_marks.iter().filter(|(_, v)| now >= v.1).map(|(k, _)| k.clone()).collect();
        for k in expired {
            if let Some((_, _, sp)) = self.foe_marks.remove(&k) {
                if sp > 0 {
                    early.push(Act::FoeRemove(k.0, sp));
                }
            }
        }
        fired.retain(|e| !self.blocked.contains_key(*e));
        let mikiri_cool = self.blocked.contains_key("mikiri");
        let ended: HashSet<&str> = self.last_present.difference(present).map(|s| s.as_str()).collect();
        // 见切：翻滚 / 后撤步的无敌帧内有敌人的攻击落在身上，一次翻滚算一次
        self.mikiri_used.retain(|id, a| fr.foes.iter().any(|f| f.id == *id && f.anim == Some(*a)));
        let mut mikiri_log = None;
        let wear = d.mikiri_keys.iter().any(|k| tiers.contains_key(k));
        let rolling = present.contains("roll") || present.contains("backstep");
        if !rolling {
            if let Some(r) = self.roll_dbg.take().filter(|_| !self.dodged) {
                mikiri_log = Some(Act::Log(r.line()));
            }
            self.dodged = false;
        } else {
            if wear {
                let r = self.roll_dbg.get_or_insert_with(RollDbg::default);
                r.frames += 1;
                r.cooling |= mikiri_cool;
                if fr.iframe {
                    r.iframes += 1;
                    if !self.dodged {
                        r.observe(d, fr);
                    }
                }
            }
        }
        if rolling && d.mikiri && fr.iframe && !self.dodged && !mikiri_cool {
            if let Some((why, used)) = mikiri_reason(d, fr, &self.mikiri_used) {
                self.dodged = true;
                self.mikiri_used.extend(used);
                fired.insert("mikiri");
                mikiri_log = Some(Act::Log(format!("见切：{why}")));
                // 音效只在戴着听见切的词条（见切、残心、影步）时放
                self.mikiri_sound = d.mikiri_keys.iter().any(|k| tiers.contains_key(k));
            }
        }
        let hit = |evs: &[String]| evs.iter().any(|e| fired.contains(e.as_str()));
        // 前几帧里最高的精力减现在的：事件标记（脚本挂的）可能比引擎扣精力晚一两帧才看到
        let lost_stamina = self.stamina_hist.iter().max().map_or(0, |&s| (s - fr.stamina).max(0));
        // 燃血：几条规则同一帧都成立时只补一次精力、只扣一次血
        let mut stamina_paid = false;
        // 「自然」的血量变化（不算引擎自己扣 / 回的）：掉血要和受击事件对上才算受伤
        let natural = self.last_hp.map_or(0, |h| fr.hp - h - self.own_hp);
        if present.contains("hit") {
            self.last_hit = Some(now);
        }
        let last_hit = self.last_hit;
        let mut took = 0;
        if natural < 0 {
            if last_hit.is_some_and(|h| now.duration_since(h) <= HIT_LINK) {
                took = -natural;
            } else {
                self.pending = Some((-natural, now));
            }
        }
        if let Some((x, t)) = self.pending {
            if last_hit.is_some_and(|h| h >= t && h.duration_since(t) <= HIT_LINK) {
                took += x;
                self.pending = None;
            } else if now.duration_since(t) > HIT_LINK {
                self.pending = None;
            }
        }
        let healed = natural.max(0);
        let fresh: Vec<HashSet<&'static str>> = fr
            .foes
            .iter()
            .map(|f| {
                let last = self.foe_kinds.get(&f.id);
                f.sts.iter().map(|a| a.kind).filter(|k| last.is_none_or(|l| !l.contains(k))).collect()
            })
            .collect();
        self.st.resize_with(d.rules.len(), RState::default);
        let mut acts: Vec<Act> = mikiri_log.into_iter().collect();
        acts.extend(early);
        // 被命中标记顶掉的命中时触发（油脂、附魔祷告、蛇弓）：游戏只认一个，这一下认的是 land，别的补挂上去。
        // 分不出这一下是哪只手打的，左右手各涂一种时两种都挂（用户 2026-11-06「结冰油脂没生效」，rr/atkfwd.py）
        for f in fr.foes.iter().filter(|f| f.shadow > 0 && f.hostile) {
            for &(buff, copy, wep) in &d.atkfwd {
                if (f.shadow == SHADOW_MELEE || wep == 0) && have.contains(&buff) {
                    acts.push(Act::FoeApply(f.id, copy));
                    if self.atkfwd_told < ATKFWD_LOG {
                        self.atkfwd_told += 1;
                        acts.push(Act::Log(format!("命中补挂：身上的 {buff} 被命中标记顶掉，给 NPC {} 挂 {copy}", f.npc)));
                    }
                }
            }
        }
        // 发狂发作（发作的效果挂 1 秒，这一帧新出现）：挂发作特效；敌人的架势扣上限的 mad_poise，最低压到 1（下一下打崩，同千钧）；不看戴什么
        if d.mad_poise > 0.0 || d.mad_vfx > 0 {
            for (f, new) in fr.foes.iter().zip(&fresh) {
                if d.mad_vfx > 0 && f.hostile && new.contains("madness") {
                    acts.push(Act::FoeApply(f.id, d.mad_vfx));
                }
                if d.mad_poise > 0.0 && f.hostile && f.poise_max > 0.0 && new.contains("madness") {
                    let low = (f.poise - f.poise_max * d.mad_poise).max(1.0);
                    if low < f.poise {
                        acts.push(Act::FoePoise(f.id, low));
                        acts.push(Act::Log(format!("发狂发作：敌人（参数 {}）架势 {:.0} → {:.0}（上限 {:.0}）", f.npc, f.poise, low, f.poise_max)));
                    }
                }
            }
        }
        let mut want: Vec<i32> = Vec::new();
        for i in 0..d.rules.len() {
            let rule = &d.rules[i];
            let Kind::On {
                event, every, at_end, cond, hp_below, cooldown, fp, stamina, hp, hp_pct, fp_pct, deny_heal, effect, burst, burst_flat, burst_kind, burst_each, burst_spell, burst_grow, grow_held, take, take_max, take_full,
                take_fresh, guard_scale, short_hp, stamina_back, foe_slow, foe_radius, foe_secs, freeze_key, freeze_secs, rest, target_has, target_remove, target_settle,
                target_buildup, buildup_kinds, target_hp_pct, target_nth, target_nth_pct, target_cap, target_reset, unless, chance, target_on,
                target_fx, target_mark, mark_max, mark_secs, mark_fx, target_take, take_grow, take_pct, take_fx, refund, haste, haste_secs,
            } = &rule.kind
            else {
                continue;
            };
            let Some(&r) = tiers.get(&rule.key) else { continue };
            if !d.weapon_ok(&rule.key, r, fr) {
                continue;
            }
            let happened = if *every > 0.0 {
                true
            } else if *at_end {
                ended.contains(event.as_str())
            } else {
                fired.contains(event.as_str())
            };
            let targeted = !target_has.is_empty()
                || *target_remove
                || target_settle[r] > 0.0
                || target_buildup[r] > 0.0
                || target_hp_pct[r] > 0.0
                || target_fx[r] > 0
                || target_mark.is_some()
                || target_take.is_some();
            // 目标层的规则：「被箭 / 道具打中」的 unless 按每个敌人看（下面挑敌人时），这里不看（同一帧近战打中 A、箭打中 B，A 照样算）
            let foe_kind = |u: &String| targeted && FOE_HIT_KINDS.contains(&u.as_str());
            if !happened
                || cond.as_ref().is_some_and(|c| !has(c))
                || (*hp_below > 0.0 && (fr.hp as f32) * 100.0 >= hp_below * fr.max_hp as f32)
                || unless.iter().any(|u| !foe_kind(u) && has(u))
                || self.st[i].cool_until.is_some_and(|t| now < t)
            {
                continue;
            }
            if chance[r] > 0.0 {
                self.seed = self.seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                if ((self.seed >> 33) % 10000) as f32 >= chance[r] * 100.0 {
                    continue;
                }
            }
            if haste[r] > 0.0 {
                self.haste.insert(rule.key.clone(), (now + Duration::from_secs_f32(*haste_secs), 1.0 + haste[r] / 100.0));
                acts.push(Act::Log(format!("{}：{} 秒内动作加快 {}%", rule.key, haste_secs, haste[r])));
            }
            let (mut n, mut held) = (1, 1);
            if let Some(k) = take {
                let Some(j) = d.stack_of(k) else { continue };
                if *take_full && self.st[j].stacks < d.stack_cap(j, tiers) {
                    continue;
                }
                held = self.st[j].stacks;
                n = if *take_max > 0 { held.min(*take_max) } else { held };
                if n == 0 {
                    continue;
                }
                // 积蓄：这一下得是叠层加上之后才开始的动作打中的；翻滚 / 后撤步中、或者动作是加层之前就开始的（之前出的招晚到的命中）不算，层数留着
                if *take_fresh {
                    let dodging = has("roll") || has("backstep");
                    let fresh = self.act_at.zip(self.st[j].last_add).is_some_and(|(a, t)| a > t);
                    if dodging || !fresh {
                        if self.fresh_told < FRESH_LOG_MAX {
                            self.fresh_told += 1;
                            acts.push(Act::Log(format!(
                                "{}：这一下命中不算（{}，动作 {:?}），层数留着",
                                rule.key,
                                if dodging { "翻滚 / 后撤步中" } else { "不是加层之后新出的招" },
                                anim
                            )));
                        }
                        continue;
                    }
                }
                self.st[j].stacks -= n;
                self.st[j].consume = None;
                self.st[j].hold_add |= *take_full;
            }
            if targeted {
                let mut did = false;
                // 被箭 / 道具打中的条件按每个敌人自己被什么打中看（Foe::via）
                let kind_ok = |f: &Foe| {
                    cond.as_ref().is_none_or(|c| !FOE_HIT_KINDS.contains(&c.as_str()) || f.via == Some(c.as_str()))
                        && !unless.iter().any(|u| FOE_HIT_KINDS.contains(&u.as_str()) && f.via == Some(u.as_str()))
                };
                for f in fr.foes.iter().filter(|f| if target_on == "break" { f.broke } else { f.landed }).filter(|f| kind_ok(f)) {
                    let hits: Vec<&Ail> = f
                        .sts
                        .iter()
                        .filter(|a| a.kind != "sleep" && target_has.iter().any(|k| k == a.kind))
                        .chain(f.slept.iter().filter(|_| target_has.iter().any(|k| k == "sleep")))
                        .collect();
                    if !target_has.is_empty() && hits.is_empty() {
                        continue;
                    }
                    // 消耗标记（引爆、近身）：身上没有这个标记的不算
                    if let Some(k) = target_take {
                        let Some((layers, _, sp)) = self.foe_marks.remove(&(f.id, k.clone())) else { continue };
                        if sp > 0 {
                            acts.push(Act::FoeRemove(f.id, sp));
                        }
                        // 碎裂特效：消耗了几层用第几个（层数越多越大）
                        if let Some(&fx) = take_fx[r].get(layers.max(1) as usize - 1).or(take_fx[r].last()) {
                            if fx > 0 {
                                acts.push(Act::FoeApply(f.id, fx));
                            }
                        }
                        // 按武器面板算；take_grow（引爆）：第一层是这么多，每多一层再乘它；没写的每层一样（近身）
                        let per = fr.ar * take_pct[r] / 100.0;
                        let want = (if *take_grow > 0.0 { per * take_grow.powi(layers as i32 - 1) } else { per * layers as f32 }) * fr.dealt;
                        let picked = if d.hp_pool.is_empty() { d.tiers_sum("hp", want) } else { Vec::new() };
                        if !d.hp_pool.is_empty() {
                            acts.push(Act::FoeHp(f.id, want.round() as i32));
                            acts.push(Act::Log(format!("{}：{k} {layers} 层 → {want:.0}", rule.key)));
                        }
                        if !picked.is_empty() {
                            acts.extend(picked.iter().map(|x| Act::FoeApply(f.id, x.1)));
                            let used: Vec<String> = picked.iter().map(|x| x.0.to_string()).collect();
                            acts.push(Act::Log(format!("{}：{k} {layers} 层 → {want:.0}（用 {} 那档）", rule.key, used.join("+"))));
                        }
                    }
                    did = true;
                    if target_fx[r] > 0 {
                        acts.push(Act::FoeApply(f.id, target_fx[r]));
                    }
                    // 叠标记（猎印）：加一层（到上限为止），换成这一层的效果，重新计时
                    if let Some(k) = target_mark {
                        let e = self.foe_marks.entry((f.id, k.clone())).or_insert((0, now, -1));
                        let n = (e.0 + 1).min((*mark_max).max(1));
                        let sp = mark_fx[r].get(n as usize - 1).or(mark_fx[r].last()).copied().unwrap_or(-1);
                        if sp != e.2 {
                            if e.2 > 0 {
                                acts.push(Act::FoeRemove(f.id, e.2));
                            }
                            if sp > 0 {
                                acts.push(Act::FoeApply(f.id, sp));
                            }
                        } else if sp > 0 {
                            acts.push(Act::FoeApply(f.id, sp)); // 同一层再挂一次，续上效果的时间
                        }
                        *e = (n, now + Duration::from_secs_f32(*mark_secs), sp);
                    }
                    if target_hp_pct[r] > 0.0 {
                        let count = {
                            let e = self.foe_hits.entry(f.id).or_insert((0, now));
                            if now.duration_since(e.1).as_secs_f32() > *target_reset {
                                e.0 = 0;
                            }
                            (e.0, e.1) = (e.0 + 1, now);
                            e.0
                        };
                        let nth = *target_nth > 0 && count % *target_nth == 0;
                        let pct = target_hp_pct[r] + if nth { target_nth_pct[r] } else { 0.0 };
                        let full = f.max_hp as f32 * pct / 100.0;
                        let cap = if target_cap[r] > 0.0 && fr.ar > 0.0 { fr.ar * target_cap[r] / 100.0 } else { f32::MAX };
                        let want = full.min(cap) * fr.dealt;
                        let busy = |sp: i32| self.foe_tier_at.get(&(f.id, sp)).is_some_and(|t| now.duration_since(*t) < TIER_BUSY);
                        if want >= PCT_MIN_DMG && !d.hp_pool.is_empty() {
                            acts.push(Act::FoeHp(f.id, want.round() as i32));
                            if nth {
                                acts.push(Act::Log(format!("{}：第 {count} 下，最大血量 {} 的 {pct}% = {full:.0}", rule.key, f.max_hp)));
                            }
                        } else if want >= PCT_MIN_DMG {
                            if let Some((dmg, sp)) = d.tier_except("hp", want, busy) {
                                self.foe_tier_at.insert((f.id, sp), now);
                                acts.push(Act::FoeApply(f.id, sp));
                                if nth || full > cap {
                                    acts.push(Act::Log(format!(
                                        "{}：{}最大血量 {} 的 {pct}% = {full:.0}{}（用 {dmg} 那档）",
                                        rule.key,
                                        if nth { format!("第 {count} 下，") } else { String::new() },
                                        f.max_hp,
                                        if full > cap { format!("，超过上限 {cap:.0}") } else { String::new() }
                                    )));
                                }
                            }
                        }
                    }
                    for a in &hits {
                        if target_settle[r] > 0.0 {
                            let want = a.rest(f.max_hp) * target_settle[r] / 100.0 * fr.dealt;
                            if !d.hp_pool.is_empty() {
                                acts.push(Act::FoeHp(f.id, (want.round() as i32).max(1)));
                                acts.push(Act::Log(format!("{}：{} 剩下 {want:.0}", rule.key, a.kind)));
                            } else if let Some((dmg, sp)) = d.tier("hp", want) {
                                acts.push(Act::FoeApply(f.id, sp));
                                acts.push(Act::Log(format!("{}：{} 剩下 {want:.0}（用 {dmg} 那档）", rule.key, a.kind)));
                            }
                        }
                        if *target_remove {
                            acts.push(Act::FoeRemove(f.id, a.sp));
                        }
                    }
                    if target_buildup[r] > 0.0 {
                        let mut kinds: Vec<&String> = if buildup_kinds.is_empty() { d.buildups.keys().collect() } else { buildup_kinds.iter().collect() };
                        kinds.sort();
                        if !kinds.is_empty() {
                            self.seed = self.seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                            let k = kinds[(self.seed >> 33) as usize % kinds.len()];
                            if let Some(sp) = d.buildup(k, target_buildup[r]) {
                                acts.push(Act::FoeApply(f.id, sp));
                                acts.push(Act::Log(format!("{}：附加 {k} 累积 {}", rule.key, target_buildup[r])));
                            }
                        }
                    }
                }
                if !did {
                    continue;
                }
            }
            // 回收：返还 refund 秒内最近用掉、还没返还过的那个
            if *refund > 0.0 {
                if let Some((c, id)) = take_used(&mut self.used, now, Duration::from_secs_f32(*refund)) {
                    acts.push(Act::Refund(c, id));
                    acts.push(Act::Log(format!("{}：返还 {id}", rule.key)));
                }
            }
            if fp[r] != 0 {
                acts.push(Act::Fp(fp[r]));
            }
            costs(&mut acts, r, stamina, hp);
            if hp_pct[r] != 0.0 {
                acts.push(Act::Hp((fr.max_hp as f32 * hp_pct[r] / 100.0).round() as i32));
            }
            if fp_pct[r] != 0.0 {
                acts.push(Act::Fp((fr.max_fp as f32 * fp_pct[r] / 100.0).round() as i32));
            }
            if *deny_heal > 0.0 {
                self.st[i].until = Some(now + Duration::from_secs_f32(*deny_heal));
            }
            if effect[r] > 0 {
                acts.push(Act::Apply(effect[r]));
            }
            // 固定伤害（法球）按那套档位的属性乘倍率（procs），法球再乘法器基数（burst_spell）；按武器攻击力百分比的已经随属性变
            let per = if burst_flat[r] > 0.0 {
                burst_flat[r] * kind_scale(burst_kind, &fr.scale) * if *burst_spell { fr.spell } else { 1.0 }
            } else {
                fr.ar * burst[r] / 100.0
            } * (1.0 + burst_grow[r] / 100.0 * (if *grow_held { held } else { n }) as f32);
            if per > 0.0 && *burst_each {
                // 每层单独放：第一下马上，后面的排进队列，隔 BURST_GAP 一下
                if let Some((dmg, sp)) = d.tier(burst_kind, per) {
                    // 带子弹编号、开了 orbshot 的（法球）：Act::Shot = 效果的点位改到法器上再挂
                    let shot = d.orbshot.is_some() && d.tier_bullet.contains_key(&sp);
                    acts.push(if shot { Act::Shot(sp) } else { Act::Apply(sp) });
                    for k in 1..n {
                        self.burst_queue.push_back((now + BURST_GAP * k, sp, shot));
                    }
                    acts.push(Act::Log(format!("{}：{} 层 → {n} 下，每下 {per:.0}（{burst_kind} 用 {dmg} 那档）", rule.key, n)));
                }
            } else if per > 0.0 && burst_kind == "phys" && !d.shock_live.is_empty() {
                // 物理冲击波走实时伤害（用户 2026-11-12）：伤害照算好的写进专用行，削韧按右手武器的重击（tick 里算）
                let want_dmg = per * n as f32;
                acts.push(Act::ShockLive(want_dmg));
                acts.push(Act::Log(format!("{}：{} 层 → 冲击波 {want_dmg:.0}（实时）", rule.key, n)));
            } else if per > 0.0 {
                let want_dmg = per * n as f32;
                if let Some((dmg, sp)) = d.tier(burst_kind, want_dmg) {
                    acts.push(Act::Apply(sp));
                    acts.push(Act::Log(format!("{}：{} 层 → 冲击波 {want_dmg:.0}（{burst_kind} 用 {dmg} 那档）", rule.key, n)));
                }
            }
            let mut busy = 0.0;
            if foe_slow[r] > 0.0 {
                let freeze = freeze_key.as_ref().is_some_and(|k| tiers.contains_key(k));
                let (mult, secs) = if freeze { (0.0, *freeze_secs) } else { (1.0 - foe_slow[r] / 100.0, foe_secs[r]) };
                busy = secs;
                let n = fr.foes.iter().filter(|f| f.hostile && f.dist <= *foe_radius).map(|f| self.slowed.insert(f.id, (mult, now + Duration::from_secs_f32(secs)))).count();
                acts.push(Act::Log(format!("{}：周围 {n} 个敌人{}（{secs} 秒）{}", rule.key, if freeze { "停住".to_string() } else { format!("动作 ×{mult:.2}") },
                                           if *rest > 0.0 { format!("；冷却到 {:.0} 秒后", secs + rest) } else { String::new() })));
            }
            if *rest > 0.0 && !event.is_empty() {
                self.blocked.insert(event.clone(), now + Duration::from_secs_f32(busy + rest));
            }
            if stamina_back[r] > 0.0 && lost_stamina > 0 {
                acts.push(Act::Stamina((lost_stamina as f32 * stamina_back[r] / 100.0).round() as i32));
            }
            if *guard_scale > 0.0 {
                let mut cost = (lost_stamina as f32 * guard_scale).round() as i32;
                if fr.stamina == 0 {
                    // 精力见底：引擎没扣全（或者判了破防、被脚本换掉了），用最近一次量到的估
                    let recent = self.guard_cost.filter(|(_, t)| now.duration_since(*t) <= GUARD_COST_KEEP).map(|(c, _)| c);
                    cost = cost.max(recent.unwrap_or(fr.max_stamina * GUARD_COST_DEFAULT / 100));
                } else if lost_stamina > 0 {
                    self.guard_cost = Some((cost, now));
                }
                let extra = cost - lost_stamina;
                let pay = extra.clamp(0, fr.stamina);
                if pay > 0 {
                    acts.push(Act::Stamina(-pay));
                }
                let short = extra - pay;
                if short > 0 && short_hp[r] > 0.0 {
                    acts.push(Act::Hp(-((short as f32 * short_hp[r] / 100.0).round() as i32).max(1)));
                }
            }
            self.st[i].cool_until = Some(now + Duration::from_secs_f32(cooldown[r].max(*every).max(0.0)));
        }
        let counts: Vec<u32> = self.st.iter().map(|s| s.stacks).collect();
        let mut cut = false;
        let mut reload = 1.0f32;
        let mut action = 1.0f32;
        for (rule, st) in d.rules.iter().zip(self.st.iter_mut()) {
            let Some(&r) = tiers.get(&rule.key) else {
                *st = RState::default();
                continue;
            };
            if !d.weapon_ok(&rule.key, r, fr) {
                *st = RState::default();
                continue;
            }
            match &rule.kind {
                Kind::While { cond, unless, hp_below, hp_above, stack, min, effect, fp_to_hp, stamina_to_hp, hp_flat, cut_after, layer_speed, poise_radius, poise_boss_pct, poise_fx, prog, prog_from, hit } => {
                    // 进度：prog_from 的事件在这个动作里第一次出现时记下播放时间，从那里算到动作结束
                    if st.prog_anim != fr.anim {
                        st.prog_anim = fr.anim;
                        st.prog_t0 = None;
                    }
                    if prog_from.as_ref().is_some_and(|e| present.contains(e)) && st.prog_t0.is_none() {
                        st.prog_t0 = Some(fr.anim_t);
                    }
                    // 这一帧的进度（没有起点 / 不知道动作长度是 None）
                    let t0 = if prog_from.is_some() { st.prog_t0 } else { Some(0.0) };
                    let x = t0.filter(|&t0| fr.anim_len > t0 + 1e-3).map(|t0| (fr.anim_t - t0) / (fr.anim_len - t0));
                    let by_prog = |need: bool| prog.map_or(!need, |(lo, hi)| x.is_some_and(|x| (lo..=hi).contains(&x)));
                    // 按攻击判定：这个动作的判定段前后放宽（秒）；表里没有这个动作退回 prog（没写 prog 就不开）
                    let win = hit.and_then(|(pre, post)| fr.anim.and_then(|a| d.hits.get(&a)).map(|&(lo, hi)| (lo - pre, hi + post)));
                    let in_prog = match (hit, win) {
                        (_, Some((lo, hi))) => (lo..=hi).contains(&fr.anim_t),
                        (Some(_), None) => by_prog(true),
                        (None, None) => by_prog(false),
                    };
                    // 诊断：条件成立的每一个动作记一行开始、窗口打开、结束（只有带 prog / hit 的规则，戴着才会走到这里）
                    if prog.is_some() || hit.is_some() {
                        let cond_on = cond.as_ref().is_none_or(|c| present.contains(c));
                        let name = cond.as_deref().unwrap_or("-");
                        if cond_on {
                            if st.diag_anim != fr.anim {
                                if let Some(a) = st.diag_anim {
                                    acts.push(Act::Log(format!("{}（{name}）诊断：动作 {a} 结束，播到 {:.2} / {:.2} 秒，最大进度 {:.0}%，窗口{}", rule.key,
                                        st.diag_t.0, st.diag_t.1, st.diag_max * 100.0, if st.diag_open { "开过" } else { "没开过" })));
                                }
                                st.diag_anim = fr.anim;
                                st.diag_max = 0.0;
                                st.diag_open = false;
                                let how = match (hit, win) {
                                    (_, Some((lo, hi))) => format!("，按判定开窗口 {lo:.2}~{hi:.2} 秒"),
                                    (Some(_), None) => format!("，判定表里没有这个动作（{}）", if prog.is_some() { "按进度" } else { "不开窗口" }),
                                    (None, None) => String::new(),
                                };
                                acts.push(Act::Log(format!("{}（{name}）诊断：动作 {:?} 开始，播到 {:.2} / 长度 {:.2} 秒{how}{}", rule.key, fr.anim, fr.anim_t, fr.anim_len,
                                    if prog_from.is_some() { format!("，{} 起点 {:?}", prog_from.as_deref().unwrap_or(""), st.prog_t0) } else { String::new() })));
                            }
                            st.diag_max = st.diag_max.max(x.unwrap_or(0.0));
                            st.diag_t = (fr.anim_t, fr.anim_len);
                            if in_prog && !st.diag_open {
                                st.diag_open = true;
                                acts.push(Act::Log(format!("{}（{name}）诊断：窗口打开，播到 {:.2} 秒（进度 {:.0}%），挂效果 {}", rule.key, fr.anim_t, x.unwrap_or(0.0) * 100.0, effect[r])));
                            }
                        } else if let Some(a) = st.diag_anim.take() {
                            acts.push(Act::Log(format!("{}（{name}）诊断：动作 {a} 结束，播到 {:.2} / {:.2} 秒，最大进度 {:.0}%，窗口{}", rule.key,
                                st.diag_t.0, st.diag_t.1, st.diag_max * 100.0, if st.diag_open { "开过" } else { "没开过" })));
                        }
                    }
                    let on = cond.as_ref().is_none_or(|c| present.contains(c))
                        && unless.as_ref().is_none_or(|c| !present.contains(c))
                        && (*hp_below <= 0.0 || (fr.hp as f32) * 100.0 < hp_below * fr.max_hp as f32)
                        && (*hp_above <= 0.0 || (fr.hp as f32) * 100.0 >= hp_above * fr.max_hp as f32)
                        && stack.as_ref().is_none_or(|k| d.stack_of(k).is_some_and(|j| counts[j] >= *min))
                        && in_prog;
                    if on && effect[r] > 0 {
                        want.push(effect[r]);
                    }
                    if on && layer_speed[r] > 0.0 {
                        if let Some(j) = stack.as_ref().and_then(|k| d.stack_of(k)) {
                            action *= 1.0 + counts[j] as f32 * layer_speed[r] / 100.0;
                        }
                    }
                    if on && fp_to_hp[r] > 0.0 && fr.fp < fr.max_fp {
                        let lost = fr.max_fp - fr.fp;
                        acts.push(Act::Fp(lost));
                        if st.armed {
                            let cost = ((lost as f32 * fp_to_hp[r] / 100.0).round() as i32).max(1);
                            acts.push(Act::Hp(-cost));
                            if lost >= 5 {
                                acts.push(Act::Log(format!("{}：专注 {lost} → 扣血 {cost}", rule.key)));
                            }
                        }
                    }
                    if on && stamina_to_hp[r] > 0.0 && lost_stamina > 0 && !stamina_paid {
                        stamina_paid = true;
                        acts.push(Act::Stamina(lost_stamina));
                        let cost = ((lost_stamina as f32 / fr.max_stamina.max(1) as f32 * stamina_to_hp[r] / 100.0 * fr.max_hp as f32).round() as i32).max(1);
                        acts.push(Act::HpCost(cost));
                        if self.blood_logs < BLOOD_LOG_MAX {
                            self.blood_logs += 1;
                            acts.push(Act::Log(format!("{}：精力 {lost_stamina} / {} → 扣血 {cost}（剩 {}）", rule.key, fr.max_stamina, (fr.hp - cost).max(0))));
                        }
                    }
                    if on && hp_flat[r] > 0.0 && fr.base_hp > 0 {
                        if let Some((_, sp)) = d.tier("hpmax", hp_flat[r] * 100.0 / fr.base_hp as f32) {
                            want.push(sp);
                        }
                    }
                    st.armed = true;
                    if *cut_after > 0.0 {
                        if !on {
                            st.until = None;
                        } else if st.until.is_none() {
                            st.until = Some(now);
                        }
                        cut |= st.until.is_some_and(|t| now.duration_since(t).as_secs_f32() >= *cut_after);
                    }
                    // 千钧（用户 2026-11-01 改成命中时生效；以前满蓄力出手时就把身边敌人的架势压低，没打中的也被压着）。
                    // 命中后再改架势值引擎当场不判崩，所以都得在打中之前准备好，这一击（含标记消失后的 POISE_GRACE）结束时收回没打中的：
                    // · 普通敌人：挂上 poise_fx（受到的削韧 ×1000，原版 saReceiveDamageRate），打中的当场崩，没打中的什么都不变；
                    // · Boss（方案 A）：出手时先扣上限的 poise_boss_pct%（最低 1），打中时引擎连同这一击自己的削韧一起判崩；
                    //   这一击结束还没打中（也没崩）就加回去。扣了的保持 POISE_HOLD（没挨打时游戏回架势很快）：
                    //   回上来的压回去，被打得更低的按更低的保持、重新计时；崩了 / 到时间交还给游戏
                    if *poise_radius > 0.0 {
                        if on {
                            self.poise_until = Some(now + POISE_GRACE);
                        }
                        let pct = poise_boss_pct[r] / 100.0;
                        let mut just = HashSet::new();
                        if on {
                            let mut n = 0;
                            for f in fr.foes.iter().filter(|f| f.hostile && f.dist <= *poise_radius && f.poise_max > 0.0) {
                                if !f.boss {
                                    if poise_fx[r] > 0 && self.poise_fx_on.insert(f.id) {
                                        acts.push(Act::FoeApply(f.id, poise_fx[r]));
                                        n += 1;
                                    }
                                } else if self.poise_hit.insert(f.id) {
                                    let low = (f.poise - f.poise_max * pct).max(1.0);
                                    if low < f.poise {
                                        acts.push(Act::FoePoise(f.id, low));
                                        acts.push(Act::Log(format!(
                                            "{}：满蓄力，Boss（NPC {}）架势先扣 {:.0} → {:.0}（上限 {:.0}），没打中就加回去",
                                            rule.key, f.npc, f.poise, low, f.poise_max
                                        )));
                                        self.poise_pre.insert(f.id, f.poise - low);
                                        self.poise_hold.insert(f.id, (low, now + POISE_HOLD));
                                        just.insert(f.id);
                                    }
                                }
                            }
                            if n > 0 {
                                acts.push(Act::Log(format!("{}：满蓄力，身边 {n} 个敌人这一击打中就崩架势", rule.key)));
                            }
                        }
                        if self.poise_until.is_some_and(|t| now <= t) {
                            // 被这一击打中 / 打崩的 Boss：扣掉的不再加回去
                            for f in fr.foes.iter().filter(|f| f.landed || f.broke) {
                                self.poise_pre.remove(&f.id);
                            }
                        } else {
                            let mut ids: Vec<usize> = self.poise_fx_on.drain().collect();
                            ids.sort_unstable();
                            acts.extend(ids.into_iter().map(|id| Act::FoeRemove(id, poise_fx[r])));
                            self.poise_hit.clear();
                            // 这一击没打中的 Boss：扣掉的加回去（期间别人打掉的照算），不再保持；不在场的直接放掉
                            for f in fr.foes.iter() {
                                let Some(taken) = self.poise_pre.remove(&f.id) else { continue };
                                self.poise_hold.remove(&f.id);
                                if !f.broke && f.poise > 0.0 {
                                    let back = (f.poise + taken).min(f.poise_max);
                                    acts.push(Act::FoePoise(f.id, back));
                                    acts.push(Act::Log(format!("{}：没打中 Boss（NPC {}），架势加回 {:.0} → {:.0}", rule.key, f.npc, f.poise, back)));
                                }
                            }
                            for (id, _) in self.poise_pre.drain() {
                                self.poise_hold.remove(&id);
                            }
                        }
                        self.poise_hold.retain(|_, h| now < h.1);
                        let mut gone = Vec::new();
                        for f in fr.foes.iter().filter(|f| !just.contains(&f.id)) {
                            let Some(h) = self.poise_hold.get_mut(&f.id) else { continue };
                            if f.broke || f.poise <= 0.0 {
                                gone.push(f.id);
                            } else if f.poise < h.0 - 0.01 {
                                *h = (f.poise, now + POISE_HOLD);
                            } else if f.poise > h.0 + 0.01 {
                                acts.push(Act::FoePoise(f.id, h.0));
                            }
                        }
                        for id in gone {
                            self.poise_hold.remove(&id);
                        }
                    }
                }
                Kind::FoeAura { .. } | Kind::FoeReact { .. } | Kind::FoeSpread { .. } | Kind::Free { .. } => {}
                Kind::Quiet { secs, effect } => {
                    let fx = effect[r];
                    if fx > 0 {
                        let on = have.contains(&fx);
                        if !st.armed || present.contains("hit") || (st.stacks > 0 && !on) {
                            st.until = Some(now);
                        }
                        st.armed = true;
                        st.stacks = on as u32;
                        if on || st.until.is_none_or(|t| now.duration_since(t).as_secs_f32() >= *secs) {
                            want.push(fx);
                        }
                    }
                }
                Kind::On { deny_heal, .. } => {
                    if *deny_heal > 0.0 && healed > 0 && st.until.is_some_and(|t| now <= t) {
                        acts.push(Act::Hp(-healed));
                        acts.push(Act::Log(format!("{}：回血 {healed} 扣回去", rule.key)));
                    }
                }
                Kind::Rally { event, window, pct, effect, flash, boost_key, boost, log } => {
                    if st.until.is_some_and(|t| now > t) {
                        st.pool = 0;
                        st.lost = 0;
                        st.until = None;
                    }
                    if took > 0 {
                        st.pool += took;
                        st.lost += took;
                        st.until = Some(now + Duration::from_secs_f32(window[r].max(0.0)));
                    }
                    if st.pool > 0 && fired.contains(event.as_str()) {
                        let mult = if boost_key.as_ref().is_some_and(|k| tiers.contains_key(k)) { *boost } else { 1.0 };
                        let heal = ((st.lost as f32 * pct[r] / 100.0 * mult).round() as i32).clamp(1, st.pool);
                        st.pool -= heal;
                        acts.push(Act::Hp(heal));
                        if flash[r] > 0 {
                            acts.push(Act::Apply(flash[r]));
                        }
                        if let Some(name) = log {
                            acts.push(Act::Log(format!("{name}：回 {heal}（损失 {}，还能回 {}）", st.lost, st.pool)));
                        }
                    }
                    if st.pool > 0 && effect[r] > 0 {
                        want.push(effect[r]);
                    }
                }
                Kind::Stack { add, cond, clear, consume, max, max_boost_key, max_boost, timeout, fx, stamina, hp, log, reload_speed, act_speed } => {
                    let cap = max[r].max(1) + max_boost_key.as_ref().and_then(|k| tiers.get(k)).map_or(0, |&rb| max_boost[rb]);
                    st.stacks = st.stacks.min(cap);
                    let before = st.stacks;
                    let mut why = "";
                    if st.stacks > 0 && *timeout > 0.0 && st.consume.is_none() && st.last_add.is_some_and(|t| now.duration_since(t).as_secs_f32() > *timeout) {
                        st.stacks = 0;
                        why = "超时";
                    }
                    if st.stacks > 0 && hit(clear) {
                        st.stacks = 0;
                        st.consume = None;
                        why = "清零";
                    }
                    if let Some((a, t0)) = st.consume {
                        let dt = now.duration_since(t0);
                        if dt < CONSUME_SETTLE {
                            st.consume = Some((anim, t0));
                        } else if anim != a || dt > CONSUME_MAX {
                            st.stacks = 0;
                            st.consume = None;
                            why = "用掉";
                        }
                    }
                    if st.stacks > 0 && st.consume.is_none() && hit(consume) {
                        st.consume = Some((anim, now));
                    }
                    let held = std::mem::take(&mut st.hold_add);   // 只管这一帧
                    if hit(add) && !held && cond.as_ref().is_none_or(|c| present.contains(c)) {
                        st.stacks = (st.stacks + 1).min(cap);
                        st.last_add = Some(now);
                        st.consume = None;
                        costs(&mut acts, r, stamina, hp);
                        why = "加一层";
                    }
                    if st.stacks != before {
                        if let Some(name) = log {
                            acts.push(Act::Log(format!("{name}：{} 层（{why}）", st.stacks)));
                        }
                    }
                    if let Some(&w) = fx[r].get((st.stacks as usize).wrapping_sub(1)) {
                        want.push(w);
                    }
                    if reload_speed[r] > 0.0 {
                        reload *= 1.0 + st.stacks as f32 * reload_speed[r] / 100.0;
                    }
                    if act_speed[r] > 0.0 && st.stacks > 0 && st.consume.is_some() {
                        action *= 1.0 + act_speed[r] / 100.0;
                    }
                }
            }
        }
        self.reload_mult = reload;
        self.haste.retain(|_, (until, _)| now < *until);
        for (_, m) in self.haste.values() {
            action *= m;
        }
        self.action_mult = action;
        // 无尽箭袋（free）：专注够就一直「箭矢不消耗」；新的一次射击 / 投掷（shot_new / throw_new 刚出现）扣专注、记成付过了，
        // 这一下的动作（shot / throw 的脉冲）还在就一直算付过（专注掉到不够也不消耗）；道具只在付过的投掷动作里不消耗（红瓶之类照常）
        let mut free = (false, false);
        let mut left = fr.fp + acts.iter().map(|a| if let Act::Fp(v) = a { *v } else { 0 }).sum::<i32>();
        let mut wearing = false;
        for rule in &d.rules {
            let (Kind::Free { fp }, Some(&r)) = (&rule.kind, tiers.get(&rule.key)) else { continue };
            wearing = true;
            let cost = fp[r].max(0);
            for (new, state, what, shot) in [("shot_new", "shot", "射击", true), ("throw_new", "throw", "投掷", false)] {
                let paid = if shot { &mut self.free_shot } else { &mut self.free_throw };
                if paid.is_some_and(|t| now.duration_since(t) > FREE_HOLD) || !(present.contains(new) || present.contains(state)) {
                    *paid = None;
                }
                if !fired.contains(new) {
                    continue;
                }
                if left >= cost {
                    left -= cost;
                    *paid = Some(now);
                    // 不扣专注的（用户 2026-11-04 无尽箭袋取消专注消耗）：不发扣专注、不记日志（每一下都记太多）
                    if cost > 0 {
                        acts.push(Act::Fp(-cost));
                        acts.push(Act::Log(format!("{}：{what}，扣 {cost} 专注（剩 {left}）", rule.key)));
                    }
                } else {
                    *paid = None;
                    acts.push(Act::Log(format!("{}：{what}，专注 {left} 不够 {cost}，照常消耗", rule.key)));
                }
            }
            free.0 |= left >= cost || self.free_shot.is_some();
            free.1 |= self.free_throw.is_some();
        }
        if !wearing {
            self.free_shot = None;
            self.free_throw = None;
        }
        self.free = free;
        for (i, rule) in d.rules.iter().enumerate() {
            let Some(&r) = tiers.get(&rule.key) else { continue };
            match &rule.kind {
                Kind::FoeAura { range, fx } => {
                    if self.st[i].cool_until.is_some_and(|t| now < t) {
                        continue;
                    }
                    self.st[i].cool_until = Some(now + Duration::from_millis(500));
                    for f in fr.foes.iter().filter(|f| f.hostile && f.dist <= *range) {
                        let n = f.sts.iter().map(|a| a.kind).collect::<HashSet<_>>().len();
                        if n > 0 {
                            if let Some(&sp) = fx[r].get(n - 1).or(fx[r].last()) {
                                acts.push(Act::FoeApply(f.id, sp));
                            }
                        }
                    }
                }
                Kind::FoeReact { when, need, pct, remove, log } => {
                    for (f, new) in fr.foes.iter().zip(&fresh) {
                        if !f.hostile || !new.contains(when.as_str()) {
                            continue;
                        }
                        let (Some(w), Some(n)) = (f.sts.iter().find(|a| a.kind == when), f.sts.iter().find(|a| a.kind == need)) else { continue };
                        let want = w.tick(f.max_hp) * pct[r] / 100.0 * fr.dealt;
                        if !d.hp_pool.is_empty() {
                            acts.push(Act::FoeHp(f.id, (want.round() as i32).max(1)));
                            if let Some(name) = log {
                                acts.push(Act::Log(format!("{name}：{need} 上发作 {when}，追加 {want:.0}")));
                            }
                        } else if let Some((dmg, sp)) = d.tier("hp", want) {
                            acts.push(Act::FoeApply(f.id, sp));
                            if let Some(name) = log {
                                acts.push(Act::Log(format!("{name}：{need} 上发作 {when}，追加 {want:.0}（用 {dmg} 那档）")));
                            }
                        }
                        if *remove {
                            acts.push(Act::FoeRemove(f.id, n.sp));
                        }
                    }
                }
                Kind::FoeSpread { range, amount, kinds, log } => {
                    for (f, new) in fr.foes.iter().zip(&fresh) {
                        if !f.hostile {
                            continue;
                        }
                        for k in kinds.iter().filter(|k| new.contains(k.as_str())) {
                            let Some(sp) = d.buildup(k, amount[r]) else { continue };
                            let others: Vec<usize> =
                                fr.foes.iter().filter(|g| g.hostile && g.id != f.id && dist3(g.pos, f.pos) <= *range).map(|g| g.id).collect();
                            if let Some(name) = log {
                                acts.push(Act::Log(format!("{name}：{k} 传给 {} 个", others.len())));
                            }
                            acts.extend(others.into_iter().map(|g| Act::FoeApply(g, sp)));
                        }
                    }
                }
                _ => {}
            }
        }
        if fr.scanned {
            self.foe_kinds = fr.foes.iter().map(|f| (f.id, f.sts.iter().map(|a| a.kind).collect())).collect();
        }
        // 减速中的敌人：每帧压一次速度（时隙之类也会改），到期改回 1（这一帧没扫就照旧）。
        // 不在扫描列表里了也先改回 1 再去掉：拉塔恩这类不在游戏距离列表里、按物理位置补进来的敌人，补的列表一清空（距离对不上、
        // 离开 20 米、换了大区）就掉出去，以前直接去掉不改回，就一直停在减速 / 停住的速度（用户 2026-11-12）；
        // 死了、卸载了的，执行动作前会先查在不在场（apply），不会写到已经释放的角色上
        let mut ids: Vec<usize> = self.slowed.keys().copied().collect();
        ids.sort_unstable();
        for id in ids {
            let (m, until) = self.slowed[&id];
            if fr.scanned && !fr.foes.iter().any(|f| f.id == id) {
                acts.push(Act::FoeSpeed(id, 1.0));
                self.slowed.remove(&id);
            } else if now < until {
                acts.push(Act::FoeSpeed(id, m));
            } else {
                acts.push(Act::FoeSpeed(id, 1.0));
                self.slowed.remove(&id);
            }
        }
        if cut != self.cut {
            self.cut = cut;
            acts.push(Act::CutIFrames(cut));
        }
        let mut drop: Vec<i32> = d.managed.iter().copied().filter(|x| have.contains(x) && !want.contains(x)).collect();
        drop.sort_unstable();
        acts.extend(drop.into_iter().map(Act::Remove));
        acts.extend(want.into_iter().filter(|x| !have.contains(x)).map(Act::Apply));
        // 燃血诊断：戴着燃血，这一帧掉了一大截精力（不在翻滚 / 后撤），却没换成扣血：写下当时的事件和动作（看是哪种动作没认出来）
        if !stamina_paid
            && lost_stamina >= BLOOD_DIAG_MIN
            && self.blood_diag < BLOOD_DIAG_MAX
            && !present.contains("roll")
            && !present.contains("backstep")
            && d.rules.iter().any(|r| tiers.contains_key(&r.key) && matches!(&r.kind, Kind::While { stamina_to_hp, .. } if stamina_to_hp.iter().any(|&x| x > 0.0)))
        {
            self.blood_diag += 1;
            let mut ev: Vec<&str> = present.iter().map(String::as_str).collect();
            ev.sort_unstable();
            acts.push(Act::Log(format!("燃血（诊断）：这一帧精力掉了 {lost_stamina}，没换成扣血；这时的事件 {ev:?}，动作 {anim:?}")));
        }
        self.last_present = present.clone();
        // 这一帧补回 / 扣掉的精力算进去，免得下一帧又把同一下算一遍
        let given: i32 = acts.iter().map(|a| if let Act::Stamina(v) = a { *v } else { 0 }).sum();
        if given != 0 {
            self.stamina_hist.clear();
        }
        self.stamina_hist.push_back(fr.stamina + given);
        while self.stamina_hist.len() > STAMINA_LOOKBACK {
            self.stamina_hist.pop_front();
        }
        self.last_hp = Some(fr.hp);
        self.own_hp = 0;
        acts
    }
}

static ENGINE: Mutex<Option<Engine>> = Mutex::new(None);

/// 见切触发的加速（影步）的光晕晚挂多久：见切的羽毛特效 0.25 秒（rr/sounds.py MIKIRI_VFX_SECS）之后
const LATE_GLOW_DELAY: Duration = Duration::from_millis(350);

/// 见切触发的加速的光晕（用户 2026-11-14「特效虽然能正常在调试工具中播放 但是实际触发时没有这个特效」：单独挂光晕正常，
/// 和见切的羽毛、见切自己的效果同一帧挂、人还在翻滚里时不出来）。st = 这一轮加速第一次看到的时间、挂上了没有；
/// active = 加速还在。返回 Some(true) = 现在挂、Some(false) = 现在摘、None = 不动。加速期间等 LATE_GLOW_DELAY、不在翻滚 / 后撤步里才挂
fn late_glow_step(st: &mut Option<(Instant, bool)>, now: Instant, active: bool, dodging: bool) -> Option<bool> {
    if !active {
        return st.take().and_then(|(_, on)| on.then_some(false));
    }
    let (since, on) = st.get_or_insert((now, false));
    if !*on && !dodging && now.duration_since(*since) >= LATE_GLOW_DELAY {
        *on = true;
        return Some(true);
    }
    None
}

/// 难度效果的特殊效果类别（rr/difficulty.py 的 SP_CATEGORY，原版没用过）
const DIFF_CATEGORY: u16 = 9100;
/// 上次找到的难度效果（编号、伤害倍率）、上次全扫的时间
static DEALT: Mutex<(i32, f32, Option<Instant>)> = Mutex::new((0, 1.0, None));

/// 难度的玩家造成伤害倍率：身上特殊效果类别是 DIFF_CATEGORY 的那个效果的物理伤害倍率（难度把五种都写成 1 / 敌人血量倍率）；
/// 没有 = 1。上次那个效果还在身上就直接用，不在了最多每秒全扫一次（读参数行）；变了记一行日志
fn difficulty_dealt(ids: &HashSet<i32>) -> f32 {
    let mut g = DEALT.lock().unwrap_or_else(|e| e.into_inner());
    if g.0 > 0 && ids.contains(&g.0) {
        return g.1;
    }
    if g.2.is_some_and(|t| t.elapsed() < Duration::from_secs(1)) {
        return if g.0 > 0 { 1.0 } else { g.1 };
    }
    let found = unsafe { SoloParamRepository::instance() }.ok().and_then(|repo| {
        ids.iter().find_map(|&id| repo.get::<SpEffectParam>(id as u32).filter(|r| r.sp_category() == DIFF_CATEGORY).map(|r| (id, r.physics_attack_rate())))
    });
    let (id, m) = found.filter(|x| x.1 > 0.0 && x.1.is_finite()).unwrap_or((0, 1.0));
    if id != g.0 || (m - g.1).abs() > 1e-4 {
        log(&format!("积木引擎：难度的玩家造成伤害 ×{m:.3}（效果 {id}），直接扣血的词条跟着乘"));
    }
    *g = (id, m, Some(Instant::now()));
    m
}

pub fn tick() {
    let d = def();
    if d.rules.is_empty() {
        return;
    }
    let mut g = ENGINE.lock().unwrap_or_else(|e| e.into_inner());
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else {
        if let Some(e) = g.as_ref().filter(|e| !e.slowed.is_empty()) {
            let live = live!(wcm);
            for &id in e.slowed.keys().filter(|id| live.contains(id)) {
                unsafe { &mut *(id as *mut eldenring::cs::ChrIns) }.modules.behavior.animation_speed = 1.0;
                turn_set(id, 1.0);
            }
        }
        *g = None;
        set_free(false, false, None);
        CUT_IFRAMES.store(false, std::sync::atomic::Ordering::Relaxed);
        ACTION_MULT.store(1.0f32.to_bits(), std::sync::atomic::Ordering::Relaxed);
        return;
    };
    let eng = g.get_or_insert_with(Engine::default);
    let ids: HashSet<i32> = p.chr_ins.special_effect.entries().map(|e| e.param_id).collect();
    let mut tiers: HashMap<String, usize> =
        d.affs.iter().filter_map(|(k, m)| (0..4).rev().find(|&r| m[r] > 0 && ids.contains(&m[r])).map(|r| (k.clone(), r))).collect();
    drop_unmet_needs(d, &mut tiers);
    worn_diag(eng, &tiers);
    // 词条数值随机二期：规则里这一档的数按身上那件的位置（没有要覆盖的就是原来的 Def）
    let cur = current_def(d, &tiers);
    let d: &Def = &cur;
    // 戴着的、看睡眠的词条（惊醒）：敌人睡着 / 醒来的诊断日志里写
    let sleep_worn: Vec<&str> = d
        .rules
        .iter()
        .filter(|r| tiers.contains_key(&r.key) && matches!(&r.kind, Kind::On { target_has, .. } if target_has.iter().any(|k| k == "sleep")))
        .map(|r| r.key.as_str())
        .collect();
    let mut present: HashSet<String> = d.marks.iter().filter(|(_, sp)| ids.contains(sp)).map(|(n, _)| n.clone()).collect();
    // 目标层：周围的角色。命中标记 land 挂在被打的角色身上，新挂上的这一帧算被打中（事件 land 发生一次）；发作中的异常从效果的参数认
    let land = d.marks.get("land").copied();
    // 箭 / 道具命中标记（挂在被打的敌人身上，见 FOE_HIT_KINDS）
    let hit_marks: Vec<(&'static str, i32)> = FOE_HIT_KINDS.iter().filter_map(|k| d.marks.get(*k).map(|&sp| (*k, sp))).collect();
    let mut foes = Vec::new();
    let mut owners: HashMap<FieldInsHandle, bool> = HashMap::new();
    // 朝向校准：不锁定、站在地上跑动时角色面朝移动方向；看「+Z 前方」和这一帧位移同向还是反向，定下正负（敌人用同一个）
    let ph = &p.chr_ins.modules.physics;
    let me_pos = [ph.position.0, ph.position.1, ph.position.2];
    let (mx, mz) = (ph.position.0 - ph.last_update_position.0, ph.position.2 - ph.last_update_position.2);
    let mv = (mx * mx + mz * mz).sqrt();
    if d.mikiri && !p.chr_ins.is_locked_on && ph.standing_on_solid_ground && mv > 0.03 && eng.cal.1 < 600 {
        let f = flat_forward(&ph.orientation);
        eng.cal.0 += (f[0] * mx + f[1] * mz) / mv;
        eng.cal.1 += 1;
        if eng.cal.1 == 60 {
            log(&format!("积木引擎（见切）：朝向校准 {}（60 帧平均 {:.2}）", if eng.cal.0 >= 0.0 { "+Z 是正前方" } else { "−Z 是正前方" }, eng.cal.0 / 60.0));
        }
    }
    let sign = if eng.cal.0 < 0.0 { -1.0 } else { 1.0 };
    // 扫周围的角色：戴着要看周围的词条（foe_needs）时每帧扫；发狂扣架势 / 发作特效是全局的（不看戴什么），发作效果挂 1 秒，
    // 没戴那类词条时每 10 帧扫一次就够（用户 2026-11-01：每帧的活挂在穿戴上；以前词条库里有这类规则就每帧扫）
    eng.scan_wait = eng.scan_wait.wrapping_add(1);
    let worn_foes = d.rules.iter().any(|r| r.foes && tiers.contains_key(&r.key));
    let global_foes = d.mad_poise > 0.0 || d.mad_vfx > 0;
    let want = worn_foes || (global_foes && eng.scan_wait % 10 == 0);
    // 连击值：戴着要看周围的词条时一直挂着玩家自己的命中累积（hit_acc，1.5 秒，掉了就补），每打中一下给自己挂 hit_self（0.1 秒），
    // 这时扫一遍全场（不在距离列表里的拉塔恩等），谁身上刚出现命中标记就算打中了谁
    if worn_foes {
        if let Some(&acc) = d.marks.get("hit_acc") {
            // 诊断：第一次挂上后记一行在不在身上（挂了 2 秒还没看到也记）
            match (ids.contains(&acc), eng.acc_diag) {
                (true, _) if !eng.acc_seen => {
                    eng.acc_seen = true;
                    log(&format!("积木引擎（连击值）：命中累积效果 {acc} 挂在身上了"));
                }
                (false, Some(t)) if !eng.acc_seen && t.elapsed() >= Duration::from_secs(2) => {
                    eng.acc_seen = true;
                    log(&format!("积木引擎（连击值）：命中累积效果 {acc} 挂了 2 秒还不在身上，打中时扫全场不会起作用"));
                }
                _ => {}
            }
            if !ids.contains(&acc) {
                p.apply_speffect(acc, false);
                eng.acc_diag.get_or_insert_with(Instant::now);
            }
        }
    }
    let self_hit = d.marks.get("hit_self").is_some_and(|sp| ids.contains(sp));
    if self_hit && !eng.self_hit_on {
        eng.self_hit_at = Some(Instant::now());
    }
    eng.self_hit_on = self_hit;
    let me = &p.chr_ins as *const _ as usize;
    // 游戏的距离列表还没就绪（读图中，见 chrs.rs）这一帧不扫，也算没扫
    let around = if want { around!(wcm, me) } else { None };
    let scanned = around.is_some();
    let prof_scan = crate::prof::on().then(Instant::now);
    if let Some(around) = &around {
        let my_team = p.chr_ins.team_type;
        let now = Instant::now();
        let mut marked = HashSet::new();
        let mut hit_now: HashMap<&'static str, HashSet<usize>> = HashMap::new();
        // 不在游戏距离列表里的角色（拉塔恩：打他的时候一直不在列表里，2026-11-01 诊断），距离按物理位置算（只认同一个大区的，见下面 dist_of）：
        //   - 身上有命中 / 子弹标记的：这一下连击值刚到、还没判完时扫（还在等子弹标记的也带上），按打中了它算；
        //   - 每 EXTRA_EVERY 帧扫一遍，EXTRA_RANGE 米内活着的敌对角色记下来，每帧都当周围的敌人（千钧压架势、光环等对它也生效）
        let mut extra = Vec::new();
        let mut live_n = 0;
        let hit_scan = self_hit || eng.self_hit_at.is_some();
        let refresh = eng.scan_wait % EXTRA_EVERY == 0;
        if hit_scan || refresh || !eng.extra_foes.is_empty() {
            let listed: HashSet<usize> = around.iter().map(|e| e.chr_ins.as_ptr() as usize).collect();
            let watch: Vec<i32> = land.into_iter().chain(hit_marks.iter().map(|x| x.1)).collect();
            let all = live!(wcm);
            live_n = all.len();
            // 距离按物理位置算，只认和玩家同一个大区（地图块编号的区号）的：物理位置是各自地图块里的坐标，跨区相减没意义。
            // （2026-11-01 先试过全局地图坐标 chunk_position，和游戏的距离差 300~476 米，用不了；打中拉塔恩时物理位置算出来是对的）
            let my_area = p.chr_ins.block_id.area();
            let dist_of = |c: &ChrIns| {
                if c.block_id.area() != my_area {
                    return f32::INFINITY;
                }
                let x = &c.modules.physics.position;
                ((x.0 - me_pos[0]).powi(2) + (x.1 - me_pos[1]).powi(2) + (x.2 - me_pos[2]).powi(2)).sqrt()
            };
            if refresh {
                // 物理位置靠不靠得住：拿列表里 30 米内同一大区的普通角色比一比游戏给的距离，一半以上差 3 米以内才用。
                // Boss（阵营 7）不当样本：拉塔恩开场时列表给的是 14.6 米，物理位置算 100 多米（他本来就在远处，列表的读数才是错的，
                // 2026-11-01）；没有能比的就照物理位置用（同大区的限制照旧）
                let diffs: Vec<f32> = around
                    .iter()
                    .filter(|e| e.distance > 0.0 && e.distance < 30.0)
                    .map(|e| unsafe { e.chr_ins.as_ref() })
                    .filter(|c| c.team_type != 7 && c.block_id.area() == my_area)
                    .take(8)
                    .map(|c| (dist_of(c) - around.iter().find(|e| std::ptr::eq(e.chr_ins.as_ptr(), c)).map_or(0.0, |e| e.distance)).abs())
                    .collect();
                let ok = diffs.is_empty() || diffs.iter().filter(|&&x| x < 3.0).count() * 2 >= diffs.len();
                if !ok && !diffs.is_empty() && !eng.chunk_bad_told {
                    eng.chunk_bad_told = true;
                    log(&format!("积木引擎（目标层）：物理位置算的距离和游戏的对不上（差 {:?} 米），先不补列表外的敌人", diffs));
                }
                eng.extra_foes = if !ok {
                    Vec::new()
                } else {
                    all.iter()
                        .copied()
                        .filter(|a| *a != me && !listed.contains(a))
                        .filter(|&a| {
                            let c = unsafe { &*(a as *const ChrIns) };
                            is_foe(c, my_team) && c.modules.data.hp > 0 && dist_of(c) <= EXTRA_RANGE
                        })
                        .collect()
                };
            }
            eng.extra_foes.retain(|a| all.contains(a) && !listed.contains(a));
            for &a in &all {
                if a == me || listed.contains(&a) {
                    continue;
                }
                let c = unsafe { &*(a as *const ChrIns) };
                let marked = hit_scan && (eng.land_wait.contains_key(&a) || c.special_effect.entries().any(|s| watch.contains(&s.param_id)));
                let near = eng.extra_foes.contains(&a);
                if !marked && !near {
                    continue;
                }
                let d = dist_of(c);
                let dist = if d.is_finite() && d <= FOE_SCAN { d } else { 0.0 };
                if let Some(chr_ins) = std::ptr::NonNull::new(a as *mut ChrIns) {
                    extra.push(crate::chrs::Near { chr_ins, distance: dist });
                }
                if marked && eng.extra_npcs.insert(c.npc_param_id) {
                    log(&format!("积木引擎（目标层）：NPC {}（阵营 {}）不在游戏的距离列表里，身上有命中标记，按打中了它算", c.npc_param_id, c.team_type));
                }
                if near && eng.extra_near_npcs.insert(c.npc_param_id) {
                    log(&format!("积木引擎（目标层）：NPC {}（阵营 {}，{dist:.1} 米）不在游戏的距离列表里，按物理位置算进周围的敌人", c.npc_param_id, c.team_type));
                }
            }
        }
        // 联机：命中标记（近战 land、子弹的 shot / item / cast）只算自己打的（队友戴同样的词条也挂同一个标记；联机计划 13.7，
        // 照黄金树爬塔的思路）：见 Attrib
        let coop_on = crate::coop::active();
        let att = if coop_on { Some(Attrib::read(&wcm.summon_buddy_chr_set, &wcm.player_chr_set, &p.chr_ins, &mut eng.coop_bullets, now)) } else { None };
        for e in around.iter().chain(extra.iter()).filter(|e| e.distance <= FOE_SCAN && e.chr_ins.as_ptr() as usize != me) {
            let c = unsafe { e.chr_ins.as_ref() };
            let id = e.chr_ins.as_ptr() as usize;
            let mut sts = Vec::new();
            let mut hit = false;
            let mut via = None;
            let (mine, why) = att.as_ref().map_or((true, ""), |a| a.mine(c, &eng.coop_bullets));
            for s in c.special_effect.entries() {
                let marked = Some(s.param_id) == land || hit_marks.iter().any(|x| x.1 == s.param_id);
                if marked && !mine && !eng.land_seen.contains(&id) && eng.not_mine_logged < 6 {
                    eng.not_mine_logged += 1;
                    log(&format!("积木引擎（联机）：NPC {} 身上的命中标记不是你打的（{why}），不算", c.npc_param_id));
                }
                hit |= mine && Some(s.param_id) == land;
                for &(k, sp) in &hit_marks {
                    if mine && s.param_id == sp {
                        hit_now.entry(k).or_default().insert(id);
                        if !eng.hit_seen.get(k).is_some_and(|x| x.contains(&id)) {
                            via = Some(k);
                        }
                    }
                }
                if let Some(pd) = s.param_data {
                    let pr = unsafe { pd.as_ref() };
                    if let Some(kind) = ail_kind(pr.sp_category() as i32) {
                        sts.push(Ail { kind, sp: s.param_id, left: s.removal_timer, every: pr.motion_interval(), rate: pr.change_hp_rate(), point: pr.change_hp_point() });
                    }
                }
            }
            if hit {
                marked.insert(id);
            }
            // 这一下算不算被打中、被什么打中：子弹标记刚出现 = 被箭 / 道具打中（随后到的 land 不另算）；
            // land 刚出现、没有子弹标记 = 先等 LAND_HOLD，期间子弹标记来了算箭 / 道具，没来才算近战等别的命中
            let new_land = hit && !eng.land_seen.contains(&id);
            // 身上真的出现了 land = 这一下游戏认的是命中标记，别的命中时触发被顶掉了（Foe::shadow）；没出现就是游戏自己挂了原版的，不补
            let mut shadow = 0;
            let landed = if via.is_some() {
                let waited = eng.land_wait.remove(&id).is_some();
                eng.bullet_at.insert(id, now);
                if via == Some("shot_hit") {
                    if waited || new_land {
                        shadow = SHADOW_SHOT;
                    } else {
                        eng.shot_wait.insert(id, now);
                    }
                }
                true
            } else if new_land {
                if !eng.bullet_at.get(&id).is_some_and(|t| now.duration_since(*t) <= BULLET_LAND_SUPPRESS) {
                    eng.land_wait.insert(id, now);
                } else if eng.shot_wait.remove(&id).is_some() {
                    shadow = SHADOW_SHOT;
                }
                false
            } else if eng.land_wait.get(&id).is_some_and(|t| now.duration_since(*t) >= LAND_HOLD) {
                eng.land_wait.remove(&id);
                shadow = SHADOW_MELEE;
                true
            } else {
                false
            };
            let hostile = is_foe(c, my_team);
            if e.distance <= 15.0 && eng.teams_seen.insert(c.team_type) {
                log(&format!("积木引擎（目标层）：第一次见到阵营 {}（NPC {}，{}）", c.team_type, c.npc_param_id, if hostile { "算敌人" } else { "不算敌人" }));
            }
            let slept = track_sleep(eng, id, &sts, new_land || via.is_some(), landed, hit, now, |what| {
                format!("NPC {}（{:.1} 米）{what}；戴着看睡眠的词条：{}", c.npc_param_id, e.distance, if sleep_worn.is_empty() { "没有".into() } else { sleep_worn.join("、") })
            }, hostile);
            // 诊断（2026-10-29 用户报：有的褪色者入侵敌人在玩家复活后不满血）：敌人第一次出现时不满血、或者之后血量上限变了，各记一行
            if hostile {
                let d0 = &c.modules.data;
                let (hp, max) = (d0.hp, d0.max_hp);
                let first = !eng.hp_seen.contains_key(&id);
                let prev = eng.hp_seen.insert(id, (max, now));
                if eng.hp_diag < HP_DIAG_MAX && ((first && hp < max) || prev.is_some_and(|(m, _)| m != max)) {
                    eng.hp_diag += 1;
                    let sps: Vec<String> = c.special_effect.entries().map(|s| s.param_id.to_string()).collect();
                    log(&format!(
                        "敌人血量（诊断）：NPC {}（阵营 {}，{:.1} 米）{}血 {hp} / {max}；身上的效果 {}",
                        c.npc_param_id, c.team_type, e.distance,
                        match prev { Some((m, _)) if m != max => format!("血量上限 {m} → {max}，"), _ => "出现时不满血，".to_string() },
                        sps.join(",")
                    ));
                }
            }
            // 诊断（2026-10-29 用户报：Souls Vision 看不到敌人的咒死累积）：15 米内每种敌人第一次见到记一行抗性上限，
            // 之后累积（剩余值）有变化就记一行，看咒死上限是不是 999、打了有没有在涨
            if hostile {
                if let Some(rs) = resist_of(c) {
                    let prev = eng.res_seen.insert(id, (rs, now)).map(|(p, _)| p);
                    let first = e.distance <= 15.0 && eng.res_npcs.insert(c.npc_param_id);
                    if eng.res_diag < RES_DIAG_MAX && (first || prev.is_some_and(|p| p[..7] != rs[..7])) {
                        eng.res_diag += 1;
                        log(&format!(
                            "敌人异常抗性（诊断）：NPC {}（{:.1} 米）{}：{}",
                            c.npc_param_id, e.distance, if first { "第一次见到" } else { "累积变了" }, resist_text(&rs)
                        ));
                    }
                }
            }
            // 法球命中探针：射出后 ORB_PROBE_WIN 内，周围敌人掉的血写一行（对一下算的伤害和实际打出来的；只在刚射过法球时看）
            if hostile && eng.orb_probe.is_some_and(|(t, _)| now.duration_since(t) <= ORB_PROBE_WIN) {
                let hp = c.modules.data.hp;
                if let Some(prev) = eng.orb_hp.insert(id, hp) {
                    if hp < prev && eng.orb_probe_logs < ORB_PROBE_MAX {
                        let (t, want) = eng.orb_probe.unwrap_or((now, 0));
                        eng.orb_probe_logs += 1;
                        log(&format!(
                            "法球命中（探针）：射出后 {} 毫秒，NPC {}（{:.1} 米）掉血 {}（{} → {}）；这一颗算的伤害 {want}（多颗连发时可能是前一颗的）",
                            now.duration_since(t).as_millis(),
                            c.npc_param_id,
                            e.distance,
                            prev - hp,
                            prev,
                            hp
                        ));
                    }
                }
            }
            let x = &c.modules.physics.position;
            let ta = &c.modules.time_act;
            let cur = (!ta.anim_queue.is_empty()).then(|| &ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()]);
            // 同时在播的其他动作：和上一次扫到时比，播放时间变了的格子（第一次扫到的不算）
            let ri = ta.read_idx as usize % ta.anim_queue.len().max(1);
            let snap: [(i32, u32); 10] = std::array::from_fn(|k| (ta.anim_queue[k].anim_id, ta.anim_queue[k].play_time.to_bits()));
            let cur_id = cur.map(|a| a.anim_id);
            let layers: Vec<(i32, f32)> = match eng.queue_prev.insert(id, snap) {
                Some(prev) => (0..snap.len())
                    .filter(|&k| k != ri && snap[k].0 > 0 && snap[k] != prev[k] && Some(snap[k].0) != cur_id)
                    .map(|k| (snap[k].0, ta.anim_queue[k].play_time))
                    .collect(),
                None => Vec::new(),
            };
            owners.insert(c.field_ins_handle, hostile);
            let fwd = flat_forward(&c.modules.physics.orientation);
            foes.push(Foe {
                id,
                anim: cur.map(|a| a.anim_id),
                npc: c.npc_param_id,
                radius: c.modules.physics.chr_hit_radius.max(0.0),
                // 动作总长读不到（0）时当「不知道」，算一半，不按进度挡
                progress: cur.map_or(0.5, |a| if a.anim_length > 0.0 { a.play_time / a.anim_length } else { 0.5 }),
                model: c.character_id,
                play: cur.map_or(-1.0, |a| a.play_time),
                layers,
                fwd: [fwd[0] * sign, fwd[1] * sign],
                dist: e.distance,
                pos: [x.0, x.1, x.2],
                max_hp: c.modules.data.max_hp,
                team: c.team_type,
                hostile,
                landed,
                via,
                shadow,
                sts,
                slept,
                poise: c.modules.super_armor.sa_durability,
                poise_max: c.modules.super_armor.sa_durability_max,
                broke: false,
                boss: d.bosses.contains(&c.npc_param_id),
            });
        }
        let seen: HashSet<usize> = foes.iter().map(|f: &Foe| f.id).collect();
        eng.queue_prev.retain(|k, _| seen.contains(k));
        eng.hit_seen = hit_now;
        if !eng.orb_probe.is_some_and(|(t, _)| now.duration_since(t) <= ORB_PROBE_WIN) {
            eng.orb_hp.clear();
        }
        eng.hp_seen.retain(|_, (_, t)| now.duration_since(*t) < Duration::from_secs(30));
        eng.res_seen.retain(|_, (_, t)| now.duration_since(*t) < Duration::from_secs(30));
        eng.land_wait.retain(|_, t| now.duration_since(*t) < Duration::from_secs(1));
        eng.bullet_at.retain(|_, t| now.duration_since(*t) < Duration::from_secs(1));
        eng.shot_wait.retain(|_, t| now.duration_since(*t) <= BULLET_LAND_SUPPRESS);
        eng.pre_sleep.retain(|_, (_, t)| now.duration_since(*t) < Duration::from_secs(1));
        eng.sleep_seen.retain(|_, s| now.duration_since(s.last) < Duration::from_secs(30));
        // 连击值：hit_self 刚出现后 HIT_SELF_WAIT 内前后哪个角色都没出现命中标记 / 子弹标记，只记一行日志，不算打中谁。
        // 以前按距离算打中了 12 米内最近的敌人（为拉塔恩加的）；拉塔恩真正的原因是不在距离列表里，已经改成打中时扫全场看谁身上有标记。
        // 按距离猜会误判：词条自己的攻击（辉石碎片等，命中不挂标记）、打中远处的敌人或物件也会让连击值涨，算到贴着你的敌人头上，
        // 巨人杀手之类就跟着扣它的血——看起来像翻滚撞到敌人掉血（用户 2026-11-01，日志里有「12 米内也没有敌人」的补判）
        if foes.iter().any(|f| f.landed) || !eng.land_wait.is_empty() {
            eng.last_land = Some(now);
        }
        if let Some(t) = eng.self_hit_at.filter(|t| now.duration_since(*t) >= HIT_SELF_WAIT) {
            eng.self_hit_at = None;
            if !eng.last_land.is_some_and(|l| l + HIT_SELF_WAIT >= t) && !eng.self_hit_none {
                // 一次进游戏只记一行
                eng.self_hit_none = true;
                log(&format!(
                    "积木引擎（连击值）：连击值涨了一下，但谁身上都没有命中标记，不算打中（距离列表 {} 项，在场角色 {live_n} 个；词条自己的攻击、打中物件都会这样）",
                    around.len()
                ));
            }
        }
        for k in FOE_HIT_KINDS {
            if foes.iter().any(|f| f.via == Some(k)) {
                present.insert(k.into());
            }
        }
        // 崩架势：BREAK_RECENT 内被你打中过的敌人，架势从大于 0 掉到 0；或者刚被打中时架势从一半以下一下回满（引擎崩架势时可能同一帧就重置）
        for f in foes.iter_mut() {
            if f.landed {
                eng.foe_land_at.insert(f.id, now);
            }
            let recent = eng.foe_land_at.get(&f.id).is_some_and(|t| now.duration_since(*t) <= BREAK_RECENT);
            if let Some(&prev) = eng.foe_poise.get(&f.id) {
                let reset = f.landed && f.poise_max > 0.0 && prev < f.poise_max * 0.5 && f.poise >= f.poise_max * 0.99;
                f.broke = recent && ((prev > 0.0 && f.poise <= 0.0) || reset);
            }
        }
        eng.foe_poise = foes.iter().map(|f| (f.id, f.poise)).collect();
        eng.foe_land_at.retain(|_, t| now.duration_since(*t) <= BREAK_RECENT);
        if foes.iter().any(|f| f.landed) {
            present.insert("land".into());
        }
        if let Some(f) = foes.iter().find(|f| f.broke) {
            present.insert("break".into());
            log(&format!("积木引擎：NPC {} 被打崩架势（上限 {:.0}）", f.npc, f.poise_max));
        }
        eng.land_seen = marked;
    }
    if let Some(t0) = prof_scan.filter(|_| scanned) {
        crate::prof::part("积木引擎·扫周围的角色", t0.elapsed());
    }
    // 诊断：戴着叠标记的词条（猎印）时，记箭命中、命中（land）和挂标记，查「标记没挂上」还是「挂上了没显示」
    let marking = d.rules.iter().any(|r| tiers.contains_key(&r.key) && matches!(&r.kind, Kind::On { target_mark: Some(_), .. }));
    if marking && eng.diag_used < DIAG_MAX {
        let landed: Vec<String> = foes
            .iter()
            .filter(|f| f.landed)
            .map(|f| format!("NPC {}（{}）", f.npc, match f.via { Some("shot_hit") => "箭", Some("item_hit") => "投掷道具", Some("cast_hit") => "法术、调香", _ => "近战等" }))
            .collect();
        if !landed.is_empty() {
            eng.diag_used += 1;
            log(&format!("积木引擎（诊断）：命中 {}", landed.join("、")));
        }
    }
    // 开发工具：悬浮窗口（dll\dark_dev）写的 devsp_req.txt 有就执行、删掉；devsp.txt 保存一次执行一次（我 / 敌 + 效果编号）
    eng.devsp_wait = eng.devsp_wait.wrapping_add(1);
    let mut texts = Vec::new();
    if eng.devsp_wait % 10 == 0 {
        let req = dir().join(DEVSP_REQ_FILE);
        if let Ok(t) = fs::read_to_string(&req) {
            let _ = fs::remove_file(&req);
            texts.push(t);
        }
    }
    if eng.devsp_wait % 60 == 0 {
        let path = dir().join(DEVSP_FILE);
        if let Ok(m) = fs::metadata(&path).and_then(|x| x.modified()) {
            let first = eng.devsp_mtime.is_none();
            if eng.devsp_mtime.is_none_or(|old| old < m) {
                eng.devsp_mtime = Some(m);
                if !first {
                    texts.push(fs::read_to_string(&path).unwrap_or_default());
                }
            }
        }
    }
    if !texts.is_empty() {
        let me = &p.chr_ins as *const _ as usize;
        let my_team = p.chr_ins.team_type;
        let around = around!(wcm, me).unwrap_or_default();   // 距离列表还没就绪时当周围没人
        for line in texts.iter().flat_map(|t| t.lines()) {
            let line = line.trim_start_matches('\u{feff}').trim();
            if line.starts_with('#') {
                continue;
            }
            // 「查 敌」：最近的敌人的血量、上限和身上的效果（还剩几秒）
            if line.starts_with('查') {
                let near = around.iter().find(|e| {
                    let c = unsafe { e.chr_ins.as_ref() };
                    e.distance <= DEVSP_RANGE && e.chr_ins.as_ptr() as usize != me && is_foe(c, my_team)
                });
                match near {
                    Some(e) => {
                        let c = unsafe { e.chr_ins.as_ref() };
                        let sps: Vec<String> = c.special_effect.entries().map(|s| format!("{}（{:.0}）", s.param_id, s.removal_timer)).collect();
                        log(&format!("开发工具（查看）：NPC {}（阵营 {}，{:.1} 米）血 {} / {}；身上的效果（括号里是还剩几秒，-1 = 不限时）{}；异常（还差多少 / 上限）{}",
                                     c.npc_param_id, c.team_type, e.distance, c.modules.data.hp, c.modules.data.max_hp, sps.join(","),
                                     resist_of(c).map(|r| resist_text(&r)).unwrap_or_else(|| "读不到".into())));
                    }
                    None => log(&format!("开发工具（查看）：{DEVSP_RANGE} 米内没有敌人")),
                }
                continue;
            }
            let mut it = line.split_whitespace();
            let (Some(who), Some(Ok(sp))) = (it.next(), it.next().map(|x| x.parse::<i32>())) else { continue };
            match who {
                "我" | "me" => {
                    p.apply_speffect(sp, false);
                    log(&format!("开发工具（效果）：给自己挂 {sp}（{}）", sp_state(&p.chr_ins, sp)));
                    eng.devsp_watch.push((me, sp, Instant::now()));
                }
                "敌" | "foe" => {
                    let near = around.iter().find(|e| {
                        let c = unsafe { e.chr_ins.as_ref() };
                        e.distance <= DEVSP_RANGE
                            && e.chr_ins.as_ptr() as usize != me
                            && is_foe(c, my_team)
                    });
                    match near {
                        Some(e) => {
                            let (dist, c) = (e.distance, unsafe { &mut *e.chr_ins.as_ptr() });
                            c.apply_speffect(sp, false);
                            let pos = &c.modules.physics.position;
                            log(&format!(
                                "开发工具（效果）：给 NPC {}（{dist:.1} 米，阵营 {}，位置 {:.1},{:.1},{:.1}）挂 {sp}（{}）",
                                c.npc_param_id, c.team_type, pos.0, pos.1, pos.2, sp_state(c, sp)
                            ));
                            eng.devsp_watch.push((e.chr_ins.as_ptr() as usize, sp, Instant::now()));
                        }
                        None => log(&format!("开发工具（效果）：{DEVSP_RANGE} 米内没有敌人，{sp} 没挂")),
                    }
                }
                _ => log(&format!("开发工具（效果）：看不懂这一行（要写 我 / 敌 + 效果编号）：{line}")),
            }
        }
    }
    // 挂上 1 秒后再看一次还在不在（角色已经不在周围列表里就不看了）
    if !eng.devsp_watch.is_empty() {
        let me = &p.chr_ins as *const _ as usize;
        let due: Vec<(usize, i32, Instant)> = eng.devsp_watch.iter().filter(|w| w.2.elapsed() >= Duration::from_secs(1)).copied().collect();
        eng.devsp_watch.retain(|w| w.2.elapsed() < Duration::from_secs(1));
        for (id, sp, _) in due {
            if id == me {
                log(&format!("开发工具（效果）：1 秒后，自己身上 {sp}：{}", sp_state(&p.chr_ins, sp)));
            } else if live!(wcm).contains(&id) {
                let c = unsafe { &*(id as *const ChrIns) };
                log(&format!("开发工具（效果）：1 秒后，NPC {} 身上 {sp}：{}", c.npc_param_id, sp_state(c, sp)));
            }
        }
    }
    // 弹药 / 投掷道具：戴着要返还的词条时数背包，数量变少的算用掉了（每少一个算一次）
    let mut used = Vec::new();
    let refunding = d.refunds
        && d.rules.iter().any(|r| tiers.contains_key(&r.key) && matches!(&r.kind, Kind::On { refund, .. } if *refund > 0.0));
    if refunding {
        let pgd = unsafe { p.player_game_data.as_ref() };
        let mut now_cnt: HashMap<(u8, u32), u32> = HashMap::new();
        for it in pgd.equipment.equip_inventory_data.items_data.items() {
            let k = (it.item_id.category() as u8, it.item_id.param_id());
            if d.ammo.contains(&k) {
                *now_cnt.entry(k).or_default() += it.quantity;
            }
        }
        if let Some(old) = eng.ammo_cnt.as_ref() {
            for (k, &n) in old {
                let m = now_cnt.get(k).copied().unwrap_or(0);
                for _ in m..n.min(m + 5) {
                    used.push(*k);
                }
            }
        }
        eng.ammo_cnt = Some(now_cnt);
    } else {
        eng.ammo_cnt = None;
    }
    // 见切：场上的子弹（发射者在周围、是敌人的才算）
    let mut shots = Vec::new();
    if d.mikiri {
        if let Ok(bm) = unsafe { CSBulletManager::instance() } {
            for b in bm.bullets() {
                let Some(&hostile) = owners.get(&b.targeting_owner.owner_chr_handle) else { continue };
                let radius = [&b.wait_state.base, &b.fly_state.base, &b.exp_state.base]
                    .iter()
                    .filter_map(|s| s.param.param_row)
                    .map(|pr| {
                        let pr = unsafe { pr.as_ref() };
                        pr.hit_radius().max(pr.hit_radius_max())
                    })
                    .fold(0.0f32, f32::max);
                let x = &b.physics.position;
                shots.push(Shot { pos: [x.0, x.1, x.2], radius, hostile });
            }
        }
    }
    // 在地上 / 在空中：玩家脚本在空中时每帧发 air（原版判断落地的 IsLanding），没收到就是在地上。
    // 物理模块的「站在 / 碰到地面」在空中也是真（dark_wings 实测；凌空的层刚加上就被当成落地清掉，2026-10-29 日志），只在没有 air 标记时退回它
    if d.marks.contains_key("air") {
        if !present.contains("air") {
            present.insert("ground".into());
        }
    } else {
        let ph = &p.chr_ins.modules.physics;
        present.insert(if ph.standing_on_solid_ground || ph.touching_solid_ground { "ground" } else { "air" }.into());
    }
    let ta = &p.chr_ins.modules.time_act;
    let anim = (!ta.anim_queue.is_empty()).then(|| ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].anim_id);
    // 连滚：翻滚脉冲一直不断，事件 roll 不会再「刚发生」，见切也一次连滚只算一次。翻滚中动作换了、或同一个动作重新从头播，
    // 当成新的一段：上一帧的 roll 去掉（这一帧就算刚发生），见切的「这次翻滚已经见切过」清掉
    let play = (!ta.anim_queue.is_empty()).then(|| ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].play_time);
    let roll_now = anim.zip(play).filter(|_| present.contains("roll"));
    if roll_now.zip(eng.roll_anim).is_some_and(|(a, b)| a.0 != b.0 || a.1 + 0.05 < b.1) {
        eng.last_present.remove("roll");
        eng.dodged = false;
    }
    eng.roll_anim = roll_now;
    // 这一下普通攻击是哪只手打的：HKS 的 DR_ClashFrame 发 clash_<轻/重/蓄满>_<左/右>。
    // 双手持握时即使没有脉冲也按握法判断；左右手都出现时取并集（双持同时攻击）。
    let style = unsafe { p.player_game_data.as_ref() }.equipment.chr_asm.equipment.arm_style;
    let attack_left = present.contains("clash_l_l") || present.contains("clash_h_l") || present.contains("clash_hc_l");
    let attack_right = present.contains("clash_l_r") || present.contains("clash_h_r") || present.contains("clash_hc_r");
    // 攻击中严格按出招手；不在攻击中时把当前装备的两把手都算上（给 while 类的武器常驻效果用）。
    let (left_hand, right_hand) = if attack_left || attack_right {
        (attack_left, attack_right)
    } else {
        match style {
            ChrAsmArmStyle::LeftBothHands => (true, false),
            ChrAsmArmStyle::RightBothHands => (false, true),
            _ => (true, true),
        }
    };
    let mut weapon_markers: HashSet<i32> = HashSet::new();
    if left_hand || right_hand {
        if let Ok(repo) = unsafe { SoloParamRepository::instance() } {
            let asm = &unsafe { p.player_game_data.as_ref() }.equipment.chr_asm;
            for (hand, use_hand) in [(ChrAsmHand::Left, left_hand), (ChrAsmHand::Right, right_hand)] {
                if !use_hand { continue; }
                let slot = asm.equipment.active_weapon_slot(hand) as usize;
                let id = asm.equipment_param_ids.get(slot).copied().unwrap_or(-1);
                if id <= 0 { continue; }
                if let Some(w) = repo.get::<EquipParamWeapon>((id / 100 * 100) as u32) {
                    for sp in [w.resident_sp_effect_id(), w.resident_sp_effect_id1(), w.resident_sp_effect_id2(), w.resident_sp_effect_id3(),
                               w.sp_effect_behavior_id0(), w.sp_effect_behavior_id1(), w.sp_effect_behavior_id2()] {
                        if sp > 0 { weapon_markers.insert(sp); }
                    }
                }
            }
        }
    }
    // 连续施法：施法的脉冲 cast 连着施法时一直不断，只表示「施法中」；新的一次施法是玩家脚本另发的 cast_new
    // （发起施法的事件当帧发，连续施法的第 2 / 3 段也算，2026-10-29；以前在这里按动作编号猜，半身施法、连段施法认不出来）
    let ar = {
        let pgd = unsafe { p.player_game_data.as_ref() };
        let a = &pgd.attack_rating;
        let slot = pgd.equipment.chr_asm.equipment.selected_slots.right_weapon_slot;
        [a.right_armament_primary, a.right_armament_secondary, a.right_armament_tertiary][(slot as usize).min(2)].max(0) as f32
    };
    let x = &p.chr_ins.modules.data;
    let (anim_t, anim_len) = if ta.anim_queue.is_empty() {
        (0.0, 0.0)
    } else {
        let a = &ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()];
        (a.play_time, a.anim_length)
    };
    let fr = Frame {
        tiers: &tiers,
        present: &present,
        have: &ids,
        weapon_markers: &weapon_markers,
        anim,
        anim_t,
        anim_len,
        now: Instant::now(),
        ar,
        scale: crate::procs::mults(),
        spell: crate::spellbase::orb_factor(),
        dealt: difficulty_dealt(&ids),
        stamina: x.stamina,
        max_stamina: x.max_stamina,
        hp: x.hp,
        max_hp: x.max_hp,
        base_hp: unsafe { p.player_game_data.as_ref() }.base_max_hp as i32,
        fp: x.fp,
        max_fp: x.max_fp,
        foes: &foes,
        scanned,
        me: me_pos,
        iframe: IFRAMES.load(std::sync::atomic::Ordering::Relaxed),
        shots: &shots,
        used: &used,
    };
    let mut own_hp = 0;
    let air = present.contains("air");
    let acts = eng.step(d, &fr);
    if std::mem::take(&mut eng.mikiri_sound) {
        crate::clash::mikiri_sound();
        if let Some(sp) = crate::clash::mikiri_vfx() {
            p.apply_speffect(sp, false);           // 潜雾猛禽化成羽毛的原版特效（用户 2026-11-13「见切触发时加个视觉特效」→「用A吧」）
        }
    }
    for sp in ground_due(air) {
        p.apply_speffect(sp, false);
    }
    // 见切触发的加速（影步）的光晕：不跟加速效果同一帧挂，等一会儿、翻滚完了单独挂，加速结束就摘（late_glow_step）
    let dodging = present.contains("roll") || present.contains("backstep");
    for (key, sp) in crate::clash::late_glows() {
        let mut st = eng.late_glow.remove(key);
        let since = st.map(|x| x.0);
        match late_glow_step(&mut st, fr.now, eng.haste.contains_key(key), dodging) {
            Some(true) => {
                p.apply_speffect(*sp, false);
                log(&format!("积木引擎：{key} 的加速光晕挂上（效果 {sp}，加速开始后 {:.2} 秒）", since.map_or(0.0, |t| fr.now.duration_since(t).as_secs_f32())));
            }
            Some(false) => {
                p.remove_speffect(*sp);
                log(&format!("积木引擎：{key} 的加速结束，光晕摘掉（效果 {sp}）"));
            }
            None => {}
        }
        if let Some(x) = st {
            eng.late_glow.insert(key.clone(), x);
        }
    }
    RELOAD_MULT.store(if eng.reload_mult > 0.0 { eng.reload_mult } else { 1.0 }.to_bits(), std::sync::atomic::Ordering::Relaxed);
    ACTION_MULT.store(if eng.action_mult > 0.0 { eng.action_mult } else { 1.0 }.to_bits(), std::sync::atomic::Ordering::Relaxed);
    let mut alive: Option<HashSet<usize>> = None;
    // 联机诊断：按本机攻击由游戏挂到敌人身上的命中标记不算「外来效果」（见 coop.rs）
    if crate::coop::active() {
        crate::coop::set_ignore(d.marks.values().copied());
    }
    for act in acts {
        // 给周围角色的动作：记下来的地址（比如到期要摘的猎印、减速中的敌人）可能已经卸载 / 读档释放了，还在场才做（见 chrs.rs）
        if let Act::FoeApply(id, _) | Act::FoeHp(id, _) | Act::FoeRemove(id, _) | Act::FoeSpeed(id, _) | Act::FoePoise(id, _) = &act {
            if !alive.get_or_insert_with(|| live!(wcm)).contains(id) {
                continue;
            }
        }
        match act {
            Act::Apply(sp) => {
                if !(d.ground.contains(&sp) && defer_until_ground(sp, air)) {
                    p.apply_speffect(sp, false);
                }
            }
            Act::ShockLive(want) => {
                let (sp, atk) = d.shock_live[eng.shock_next % d.shock_live.len()];
                eng.shock_next = eng.shock_next.wrapping_add(1);
                let hp = crate::runtime::right_heavy_poise(&d.heavy_poise);
                match crate::runtime::write_live_atk(atk, want, hp.map_or(0.0, |x| x.0)) {
                    Some(dmg) => {
                        p.apply_speffect(sp, false);
                        log(&format!("积木引擎：物理冲击波实时伤害 {dmg:.0}、削韧 {:.1}（右手武器 {:?} 的重击）", hp.map_or(0.0, |x| x.0), hp.map(|x| x.1)));
                    }
                    None => {
                        if let Some((dmg, sp)) = d.tier("phys", want) {
                            p.apply_speffect(sp, false);
                            log(&format!("积木引擎：物理冲击波的专用行不在参数里，按档位 {dmg}（要 {want:.0}）"));
                        }
                    }
                }
            }
            Act::Remove(sp) => p.remove_speffect(sp),
            Act::Shot(sp) => {
                // 照常挂「放子弹」的效果（效果 → 行为 → 子弹，伤害走游戏自己的路子），先把效果的点位改成拿法器那只手的武器点位（orbshot.rs）。
                // 以前直接调游戏生成子弹的函数（没有行为），打出来只有个位数（用户 2026-11-11）
                if let Some(dm) = d.orbshot {
                    crate::orbshot::aim(sp, dm);
                }
                p.apply_speffect(sp, false);
                if eng.orb_probe_logs < ORB_PROBE_MAX {
                    let dmg = d.tiers.get("pebble").and_then(|v| v.iter().find(|x| x.1 == sp)).map_or(0.0, |x| x.0);
                    eng.orb_probe = Some((Instant::now(), dmg.round() as i32));
                }
            }
            Act::Stamina(v) => {
                let x = &mut p.chr_ins.modules.data;
                x.stamina = (x.stamina + v).clamp(0, x.max_stamina);
            }
            Act::Fp(v) => {
                let x = &mut p.chr_ins.modules.data;
                x.fp = (x.fp + v).clamp(0, x.max_fp);
            }
            Act::Hp(v) => {
                let x = &mut p.chr_ins.modules.data;
                let old = x.hp;
                x.hp = (x.hp + v).clamp(1, x.max_hp);
                own_hp += x.hp - old;
            }
            Act::HpCost(v) => {
                let x = &mut p.chr_ins.modules.data;
                let old = x.hp;
                x.hp = (x.hp - v).clamp(0, x.max_hp);
                own_hp += x.hp - old;
            }
            Act::FoeApply(id, sp) => {
                let c = unsafe { &mut *(id as *mut eldenring::cs::ChrIns) };
                if marking && eng.diag_used < DIAG_MAX && d.mark_fx_ids.contains(&sp) {
                    eng.diag_used += 1;
                    log(&format!("积木引擎（诊断）：给 NPC {} 挂标记效果 {sp}", c.npc_param_id));
                }
                crate::coop::note(crate::coop::Op::Apply(sp), c);
                c.apply_speffect(sp, false)
            }
            Act::FoeHp(id, amt) => {
                let c = unsafe { &mut *(id as *mut eldenring::cs::ChrIns) };
                // 客机不直接写血量，改走扣血效果（挂效果走游戏同步，联机计划 13.2 G2）
                if crate::coop::client_skip("积木引擎的精确扣血") || !foe_hp_exact(c, amt) {
                    for (_, sp) in d.tiers_sum("hp", amt as f32) {
                        crate::coop::note(crate::coop::Op::Apply(sp), c);
                        c.apply_speffect(sp, false);
                    }
                }
            }
            Act::FoeRemove(id, sp) => {
                let c = unsafe { &mut *(id as *mut eldenring::cs::ChrIns) };
                crate::coop::note(crate::coop::Op::Remove(sp), c);
                c.remove_speffect(sp)
            }
            // 客机：改敌人的动作速度、架势转给房主去改（联机计划 13.5；改回 ×1 本机也照写，免得进会话前改过的卡住）
            Act::FoeSpeed(id, m) if crate::coop::client() => {
                let c = unsafe { &mut *(id as *mut eldenring::cs::ChrIns) };
                crate::link::foe_to_host(c.event_entity_id, "speed", m);
                if m == 1.0 {
                    c.modules.behavior.animation_speed = m;
                    turn_set(id, m);
                } else {
                    crate::coop::client_skip("改敌人动作速度（见切、影步）：转给房主");
                }
            }
            Act::FoeSpeed(id, m) => {
                let c = unsafe { &mut *(id as *mut eldenring::cs::ChrIns) };
                crate::coop::note(crate::coop::Op::Speed(m), c);
                c.modules.behavior.animation_speed = m;
                turn_set(id, m);
            }
            Act::FoePoise(id, v) if crate::coop::client() => {
                let c = unsafe { &*(id as *const eldenring::cs::ChrIns) };
                crate::link::foe_to_host(c.event_entity_id, "poise", v);
                crate::coop::client_skip("改敌人架势（千钧、发狂）：转给房主");
            }
            Act::FoePoise(id, v) => {
                let c = unsafe { &mut *(id as *mut eldenring::cs::ChrIns) };
                crate::coop::note(crate::coop::Op::Poise(v), c);
                c.modules.super_armor.sa_durability = v
            }
            Act::CutIFrames(on) => CUT_IFRAMES.store(on, std::sync::atomic::Ordering::Relaxed),
            Act::Refund(c, id) => {
                let pgd = unsafe { p.player_game_data.as_ref() };
                if let Some(it) = pgd.equipment.equip_inventory_data.items_data.items_mut().find(|it| it.item_id.category() as u8 == c && it.item_id.param_id() == id) {
                    it.quantity += 1;
                    // 下一帧数背包时别把加回去的当成「多出来」：直接记成现在的数
                    if let Some(cnt) = eng.ammo_cnt.as_mut() {
                        *cnt.entry((c, id)).or_default() += 1;
                    }
                } else {
                    log(&format!("积木引擎：要返还的 {id} 已经不在背包里（用完了？），没返还"));
                }
            }
            Act::Log(s) => log(&s),
        }
    }
    eng.own_hp = own_hp;
    set_free(eng.free.0, eng.free.1, Some(&mut p.chr_ins));
}

/// 无尽箭袋：照引擎这一帧要的开关游戏的调试开关（WorldChrManDbgFlags；道具那个同时设玩家自己的「道具不消耗」位）。
/// 要开的每帧都写（被别的东西改掉也马上恢复），要关的只关自己开过的
fn set_free(arrows: bool, goods: bool, chr: Option<&mut ChrIns>) {
    use std::sync::atomic::Ordering::Relaxed;
    let want = arrows as u8 | (goods as u8) << 1;
    let had = FREE_SET.load(Relaxed);
    if want == 0 && had == 0 {
        return;
    }
    let Ok(f) = (unsafe { WorldChrManDbgFlags::instance_mut() }) else { return };
    if arrows || had & 1 != 0 {
        f.all_no_arrow_consume = arrows;
    }
    if goods || had & 2 != 0 {
        f.player_no_goods_consume = goods;
        if let Some(c) = chr {
            c.debug_flags.set_infinite_consumables(goods);
        }
    }
    if (want ^ had) & 1 != 0 {
        log(if arrows { "无尽箭袋：箭矢不消耗（打开）" } else { "无尽箭袋：箭矢照常消耗（摘下或专注不够）" });
    }
    FREE_SET.store(want, Relaxed);
}

#[cfg(test)]
mod tests {
    #[test]
    fn coop_attribution_follows_bullet_then_distance() {
        let now = Instant::now();
        let foe = [20.0, 0.0, 0.0];
        assert_eq!(bullet_owner_is_mine(foe, &[(now, [19.0, 0.0, 0.0], true), (now, [30.0, 0.0, 0.0], false)]), Some(true), "自己的法术落在它身上");
        assert_eq!(bullet_owner_is_mine(foe, &[(now, [18.0, 0.0, 0.0], true), (now, [20.5, 0.0, 0.0], false)]), Some(false), "队友的箭更近");
        assert_eq!(bullet_owner_is_mine(foe, &[(now, [0.0, 0.0, 0.0], true)]), None, "附近没有子弹，改比距离");
        let foe = [0.0, 0.0, 0.0];
        assert!(nearest_is_mine(foe, &[[1.0, 0.0, 0.0]], &[[3.0, 0.0, 0.0]]), "贴着敌人近战");
        assert!(!nearest_is_mine(foe, &[[5.0, 0.0, 0.0]], &[[2.0, 0.0, 0.0]]), "队友更近");
        assert!(nearest_is_mine(foe, &[[9.0, 0.0, 0.0], [0.5, 0.0, 0.0]], &[[2.0, 0.0, 0.0]]), "自己的骨灰最近");
        assert!(nearest_is_mine(foe, &[[40.0, 0.0, 0.0]], &[]), "附近没有队友");
        assert!(!nearest_is_mine(foe, &[], &[]));
    }

    use super::*;

    const DEFS: &str = "mark\tstyle\t900\nmark\tgrip1\t901\nmark\tattack\t902\nmark\thit\t903\n\
        aff\tdr_calm\t10,11,12,13\nrule\tdr_calm\twhile\tcond=grip1\teffect=20,21,22,23\n\
        aff\tdr_turn\t30,31,32,33\nrule\tdr_turn\ton\tevent=style\tcooldown=3\tfp=5,8,11,15\n\
        aff\tdr_break\t40,41,42,43\nrule\tdr_break\tstack\tadd=style\tconsume=attack\tmax=1\ttimeout=3\tfx0=50\tfx1=51\tfx2=52\tfx3=53\n\
        aff\tdr_flow\t-1,-1,-1,60\nrule\tdr_flow\tstack\tadd=style\tclear=hit\tmax=5\ttimeout=10\tfx0=\tfx1=\tfx2=\tfx3=61,62,63,64,65\tstamina=-15,-15,-15,-15\tlog=心流\n\
        rule\tdr_none\twhile\tcond=grip1\teffect=1,1,1,1\nrule\tdr_calm\tfly\tx=1\n";

    fn set(xs: &[&str]) -> HashSet<String> {
        xs.iter().map(|x| x.to_string()).collect()
    }

    fn worn(xs: &[(&str, usize)]) -> HashMap<String, usize> {
        xs.iter().map(|(k, r)| (k.to_string(), *r)).collect()
    }

    /// 模拟玩家身上的效果：每一步把挂 / 摘真的作用上去，下一步当 have 传进去
    struct Sim {
        e: Engine,
        have: HashSet<i32>,
        t0: Instant,
        ar: f32,
        scale: [f32; 5],
        spell: f32,
        dealt: f32,
        stamina: i32,
        hp: i32,
        fp: i32,
        foes: Vec<Foe>,
        weapon_markers: HashSet<i32>,
        iframe: bool,
        shots: Vec<Shot>,
        /// 这一步用掉的弹药（用完清空）
        used: Vec<(u8, u32)>,
        /// 当前动作播到第几秒、动作长度
        anim_t: f32,
        anim_len: f32,
    }

    impl Sim {
        fn new() -> Self {
            Sim { e: Engine::default(), have: HashSet::new(), t0: Instant::now(), ar: 0.0, scale: [1.0; 5], spell: 1.0, dealt: 1.0, stamina: 100, hp: 1000, fp: 100, foes: Vec::new(),
                  iframe: true, shots: Vec::new(), used: Vec::new(), anim_t: 0.0, anim_len: 0.0, weapon_markers: HashSet::new() }
        }

        fn step(&mut self, d: &Def, w: &HashMap<String, usize>, ev: &[&str], anim: Option<i32>, ms: u64) -> Vec<Act> {
            let present = set(ev);
            let used = std::mem::take(&mut self.used);
            let mut w = w.clone();
            drop_unmet_needs(d, &mut w);
            let fr = Frame { tiers: &w, present: &present, have: &self.have, weapon_markers: &self.weapon_markers, anim, anim_t: self.anim_t, anim_len: self.anim_len,
                             now: self.t0 + Duration::from_millis(ms), ar: self.ar,
                             scale: self.scale, spell: self.spell, dealt: self.dealt, stamina: self.stamina, max_stamina: 100, hp: self.hp, max_hp: 1000, base_hp: 800, fp: self.fp, max_fp: 100, foes: &self.foes, scanned: true, me: [0.0; 3],
                             iframe: self.iframe, shots: &self.shots, used: &used };
            let acts = self.e.step(d, &fr);
            let mut own_hp = 0;
            for a in &acts {
                match a {
                    Act::Apply(x) => {
                        self.have.insert(*x);
                    }
                    Act::Remove(x) => {
                        self.have.remove(x);
                    }
                    Act::Hp(v) => {
                        let old = self.hp;
                        self.hp = (self.hp + v).clamp(1, 1000);
                        own_hp += self.hp - old;
                    }
                    Act::HpCost(v) => {
                        let old = self.hp;
                        self.hp = (self.hp - v).clamp(0, 1000);
                        own_hp += self.hp - old;
                    }
                    Act::Fp(v) => self.fp = (self.fp + v).clamp(0, 100),
                    Act::Stamina(v) => self.stamina = (self.stamina + v).clamp(0, 100),
                    _ => {}
                }
            }
            self.e.own_hp = own_hp;
            acts
        }
    }

    #[test]
    fn weapon_rules_follow_the_attack_hand() {
        let d = parse("mark\thit\t900\nweapon\tdr_weapon\naff\tdr_weapon\t10,11,12,13\nrule\tdr_weapon\ton\tevent=hit\teffect=20,21,22,23\n");
        let w = worn(&[("dr_weapon", 0)]);
        let mut s = Sim::new();
        assert!(s.step(&d, &w, &["hit"], None, 0).is_empty(), "左手攻击时主手武器没有这个标记");
        s.have.clear();
        s.e.last_present.clear();
        s.weapon_markers.insert(10);
        assert_eq!(s.step(&d, &w, &["hit"], None, 200), vec![Act::Apply(20)], "当前出招武器带标记才生效");
    }

    #[test]
    fn parse_lines() {
        let d = parse(DEFS);
        assert_eq!(d.marks["style"], 900);
        assert_eq!(d.affs["dr_flow"], [-1, -1, -1, 60]);
        assert_eq!(d.rules.len(), 4);
        assert_eq!(d.skipped.len(), 2, "{:?}", d.skipped);
        let Kind::Stack { fx, stamina, max, log, .. } = &d.rules[3].kind else { panic!() };
        assert_eq!((fx[0].clone(), fx[3].clone(), stamina[3], *max, log.as_deref()), (vec![], vec![61, 62, 63, 64, 65], -15, [5; 4], Some("心流")));
        let mut m: Vec<i32> = d.managed.iter().copied().collect();
        m.sort();
        assert_eq!(m, vec![20, 21, 22, 23, 50, 51, 52, 53, 61, 62, 63, 64, 65], "on 的效果（一次性）不归引擎管");
        // 这些规则都只看玩家自己：戴着也不用扫周围
        assert!(d.rules.iter().all(|r| !r.foes), "{:?}", d.rules.iter().map(|r| (&r.key, r.foes)).collect::<Vec<_>>());
    }

    /// 静息（泡盾）：刚戴上从头计时，15 秒没受伤挂上；被打掉的那一帧（受击事件还没到）不马上挂回，受击后重新计时 15 秒；摘下就摘
    #[test]
    fn quiet_shield_after_no_damage() {
        let d = parse("mark\thit\t900\naff\tdr_bubble\t-1,-1,-1,95\nrule\tdr_bubble\tquiet\tsecs=15\teffect=-1,-1,-1,96\n");
        assert!(d.skipped.is_empty() && d.managed.contains(&96), "{:?}", d.skipped);
        let w = worn(&[("dr_bubble", 3)]);
        let mut s = Sim::new();
        assert!(s.step(&d, &w, &[], None, 0).is_empty(), "刚戴上从头计时");
        assert!(s.step(&d, &w, &[], None, 14_000).is_empty());
        assert_eq!(s.step(&d, &w, &[], None, 15_000), vec![Act::Apply(96)]);
        assert!(s.step(&d, &w, &[], None, 16_000).is_empty(), "挂着就不动");
        s.have.remove(&96); // 被打掉（原版效果受伤就消失），受击事件还没到
        assert!(s.step(&d, &w, &[], None, 17_000).is_empty(), "不马上挂回去");
        assert!(s.step(&d, &w, &["hit"], None, 17_100).is_empty());
        assert!(s.step(&d, &w, &[], None, 32_000).is_empty(), "受击后才 14.9 秒");
        assert_eq!(s.step(&d, &w, &[], None, 32_200), vec![Act::Apply(96)]);
        assert_eq!(s.step(&d, &HashMap::new(), &[], None, 33_000), vec![Act::Remove(96)], "摘下就摘");
    }

    /// 冲击波只在地上放：物理 / 魔力两套的档进 ground（别的套不进）；在空中排队，落地那一帧一起放
    #[test]
    fn hp_pool_rows() {
        assert_eq!(parse("hppool\t7,8,9\n").hp_pool, vec![7, 8, 9]);
        let now = Instant::now();
        let mut held = HashMap::new();
        assert_eq!(free_hp_row(&[1, 2, 3], &held, now, |_| false), Some(1));
        held.insert(1, now + Duration::from_secs(1));
        assert_eq!(free_hp_row(&[1, 2, 3], &held, now, |_| false), Some(2), "占着的跳过");
        assert_eq!(free_hp_row(&[1, 2, 3], &held, now, |sp| sp == 2), Some(3), "敌人身上有的跳过");
        assert_eq!(free_hp_row(&[1, 2, 3], &held, now + Duration::from_secs(2), |_| false), Some(1), "到期能再用");
        assert_eq!(free_hp_row(&[1], &held, now, |_| false), None, "都占着");
        assert_eq!(free_hp_row(&[], &held, now, |_| false), None, "没有专用行");
    }

    /// 回响祝福选档：最接近的一档；不超过上限（不打死）；身上还有的跳过；小到没有档就空
    #[test]
    fn hp_tiers_within_cap() {
        let d = parse("bursttier\thp\t40\t831\nbursttier\thp\t100\t832\nbursttier\thp\t200\t833\n");
        let ids = |v: Vec<(f32, i32)>| v.iter().map(|x| x.1).collect::<Vec<_>>();
        assert_eq!(ids(d.tiers_within("hp", 95.0, 1000.0, |_| false)), vec![832]);
        assert_eq!(ids(d.tiers_within("hp", 95.0, 90.0, |_| false)), vec![831]);
        assert_eq!(ids(d.tiers_within("hp", 300.0, 1000.0, |_| false)), vec![833, 832]);
        assert_eq!(ids(d.tiers_within("hp", 95.0, 1000.0, |sp| sp == 832)), vec![831]);
        assert!(d.tiers_within("hp", 95.0, 30.0, |_| false).is_empty());
    }

    #[test]
    fn ground_shockwaves_wait_for_landing() {
        let d = parse("crushtier\t40\t801\ncrushtier\t100\t802\nbursttier\tmagic\t40\t811\nbursttier\tpebble\t40\t821\t9000\nbursttier\thp\t40\t831\n");
        assert_eq!(d.ground, HashSet::from([801, 802, 811]));
        assert!(!defer_until_ground(801, false), "在地上照常挂");
        assert!(defer_until_ground(802, true) && defer_until_ground(811, true), "在空中排队");
        assert!(ground_due(true).is_empty(), "还在空中不放");
        assert_eq!(ground_due(false), vec![802, 811], "落地一起放");
        assert!(ground_due(false).is_empty());
    }

    /// 哪些规则要扫周围的角色（foe_needs）：命中 / 崩架势 / 见切事件、目标层、周围敌人减速、千钧压架势、周围异常
    #[test]
    fn foe_needs_by_rule() {
        let d = parse(
            "mark\tland\t900\nmark\tattack\t901\nmark\troll\t902\n\
             aff\tdr_a\t10,11,12,13\nrule\tdr_a\ton\tevent=land\thp=1,1,1,1\n\
             aff\tdr_b\t20,21,22,23\nrule\tdr_b\ton\tevent=attack\tburst=10,10,10,10\n\
             aff\tdr_c\t30,31,32,33\nrule\tdr_c\tstack\tadd=land\tmax=3\ttimeout=5\n\
             aff\tdr_d\t40,41,42,43\nrule\tdr_d\twhile\tcond=roll\teffect=1,2,3,4\n\
             aff\tdr_e\t50,51,52,53\nrule\tdr_e\ton\tevent=mikiri\tfoe_slow=30,40,50,60\tfoe_radius=8\tfoe_secs=2\n",
        );
        let foes: HashMap<&str, bool> = d.rules.iter().map(|r| (r.key.as_str(), r.foes)).collect();
        assert_eq!(foes, HashMap::from([("dr_a", true), ("dr_b", false), ("dr_c", true), ("dr_d", false), ("dr_e", true)]), "{:?}", d.skipped);
    }

    #[test]
    fn while_and_on() {
        let d = parse(DEFS);
        let mut s = Sim::new();
        let w = worn(&[("dr_calm", 2), ("dr_turn", 1)]);
        assert_eq!(s.step(&d, &w, &["grip1"], None, 0), vec![Act::Apply(22)]);
        assert!(s.step(&d, &w, &["grip1"], None, 600).is_empty(), "不限时，不再续（续会让图标闪）");
        // 切到双手：静心摘掉，转念回专注；冷却 3 秒内再切不回
        assert_eq!(s.step(&d, &w, &["style"], None, 700), vec![Act::Fp(8), Act::Remove(22)]);
        assert!(s.step(&d, &w, &[], None, 800).is_empty());
        assert_eq!(s.step(&d, &w, &["style", "grip1"], None, 900), vec![Act::Apply(22)], "冷却中不回专注");
        // 被游戏清掉了（比如读档）：身上没有了就再挂
        s.have.clear();
        assert_eq!(s.step(&d, &w, &["grip1"], None, 1000), vec![Act::Apply(22)]);
        assert_eq!(s.step(&d, &w, &["grip1", "style"], None, 3800), vec![Act::Fp(8)]);
        // 摘下静心：效果跟着摘
        assert_eq!(s.step(&d, &worn(&[("dr_turn", 1)]), &["grip1"], None, 3900), vec![Act::Remove(22)]);
        // 换了别的稀有度的静心：旧稀有度的摘掉、挂新的
        s.have.insert(21);
        assert_eq!(s.step(&d, &worn(&[("dr_calm", 3)]), &["grip1"], None, 4000), vec![Act::Remove(21), Act::Apply(23)]);
    }

    #[test]
    fn stack_consume_after_the_attack() {
        let d = parse(DEFS);
        let mut s = Sim::new();
        let w = worn(&[("dr_break", 3)]);
        assert_eq!(s.step(&d, &w, &["style"], Some(1000), 0), vec![Act::Apply(53)]);
        // 攻击开始：先跟着动作编号走（还是原来的动作，下一帧变成攻击），攻击动作做完（编号再变）才清
        assert!(s.step(&d, &w, &["attack"], Some(1000), 300).is_empty());
        assert!(s.step(&d, &w, &[], Some(3000010), 350).is_empty());
        assert!(s.step(&d, &w, &[], Some(3000010), 900).is_empty(), "攻击还没做完");
        assert!(s.step(&d, &w, &[], Some(3000010), 3500).is_empty(), "等着消耗时不算超时");
        assert_eq!(s.step(&d, &w, &[], Some(3000020), 3600), vec![Act::Remove(53)], "下一击开始，这一层用掉");
        // 切换后 3 秒没攻击：超时清掉
        assert_eq!(s.step(&d, &w, &["style"], Some(1000), 5000), vec![Act::Apply(53)]);
        assert!(s.step(&d, &w, &[], Some(1000), 7000).is_empty());
        assert_eq!(s.step(&d, &w, &[], Some(1000), 8100), vec![Act::Remove(53)]);
    }

    #[test]
    fn cooldown_depends_on_rarity() {
        let d = parse("mark\tsw\t900\naff\tk\t10,11,12,13\nrule\tk\ton\tevent=sw\tcooldown=20,17,13,10\tstamina=9999\n");
        for (r, secs) in [(0usize, 20u64), (3, 10)] {
            let mut s = Sim::new();
            let w = worn(&[("k", r)]);
            assert_eq!(s.step(&d, &w, &["sw"], None, 0), vec![Act::Stamina(9999)], "第一次切换就回满");
            s.step(&d, &w, &[], None, 100);
            assert_eq!(s.step(&d, &w, &["sw"], None, secs * 1000 - 500), vec![], "冷却没到");
            s.step(&d, &w, &[], None, secs * 1000 - 400);
            assert_eq!(s.step(&d, &w, &["sw"], None, secs * 1000 + 100), vec![Act::Stamina(9999)], "冷却到了");
        }
    }

    #[test]
    fn stack_layers_costs_and_clear() {
        let d = parse(DEFS);
        let mut s = Sim::new();
        let w = worn(&[("dr_flow", 3)]);
        assert_eq!(s.step(&d, &w, &["style"], None, 0), vec![Act::Stamina(-15), Act::Log("心流：1 层（加一层）".into()), Act::Apply(61)]);
        s.step(&d, &w, &[], None, 100);
        assert_eq!(s.step(&d, &w, &["style"], None, 200),
                   vec![Act::Stamina(-15), Act::Log("心流：2 层（加一层）".into()), Act::Remove(61), Act::Apply(62)]);
        assert_eq!(s.step(&d, &w, &["hit"], None, 300), vec![Act::Log("心流：0 层（清零）".into()), Act::Remove(62)]);
        // 只出传说：别的稀有度标记是 -1，tick 不会算成戴着；规则对没戴的词条什么都不做
        assert!(s.step(&d, &worn(&[]), &["style"], None, 400).is_empty());
    }

    /// 处刑（用户 2026-11-06）：致命一击的动作结束时开始算，10 秒内动作加快，到时恢复
    #[test]
    fn execute_haste_starts_when_crit_ends() {
        let d = parse("mark\tcrit\t906\naff\tdr_execute\t500,501,502,503\nrule\tdr_execute\ton\tevent=crit\twhen=end\teffect=510,511,512,513\thaste=20\thaste_secs=10\n");
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_execute", 3)]);
        let mut s = Sim::new();
        s.step(&d, &w, &["crit"], Some(1), 100);
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "处决动作中不变速");
        let acts = s.step(&d, &w, &[], Some(2), 200);
        assert!(acts.contains(&Act::Apply(513)), "{acts:?}");
        assert!((s.e.action_mult - 1.2).abs() < 1e-5);
        s.step(&d, &w, &[], Some(2), 10_100);
        assert!((s.e.action_mult - 1.2).abs() < 1e-5, "10 秒内");
        s.step(&d, &w, &[], Some(2), 10_300);
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "10 秒到");
    }

    /// 转念（用户 2026-11-06）：切换握法后一直等到下一次攻击，这一击的动作加快，动作换掉就用完
    #[test]
    fn turn_speeds_only_the_next_attack() {
        let d = parse("mark\tstyle\t906\nmark\tattack\t907\naff\tdr_turn\t500,501,502,503\nrule\tdr_turn\tstack\tadd=style\tconsume=attack\tmax=1\tact_speed=10,20,30,40\tfx0=510\tfx1=511\tfx2=512\tfx3=513\n");
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_turn", 3)]);
        let mut s = Sim::new();
        let acts = s.step(&d, &w, &["style"], Some(1), 100);
        assert!(acts.contains(&Act::Apply(513)), "{acts:?}");
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "切换握法本身不加快");
        s.step(&d, &w, &[], Some(1), 60_000);
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "还没攻击");
        s.step(&d, &w, &["attack"], Some(30000), 60_100);
        assert!((s.e.action_mult - 1.4).abs() < 1e-5, "这一击加快");
        s.step(&d, &w, &[], Some(30000), 60_500);
        assert!((s.e.action_mult - 1.4).abs() < 1e-5, "动作没换还算这一击");
        s.step(&d, &w, &[], Some(30001), 60_900);
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "动作换了，用完");
    }

    /// 乘势（用户 2026-11-04）：普通攻击打中（land + swing）加层，最多 3 层；受击掉一层（战技中不掉）；满 3 层战技期间挂 full；战技结束全部用掉
    const MOMENTUM: &str = "mark\tland\t906\nmark\tswing\t907\nmark\thit\t908\nmark\tskill\t909\n\
        aff\tdr_momentum\t500,501,502,503\n\
        rule\tdr_momentum\tstack\tadd=land\tcond=swing\tmax=3\tfx0=510,511,512\tfx1=515,516,517\tfx2=520,521,522\tfx3=530,531,532\tlog=乘势\n\
        rule\tdr_momentum\ton\tevent=hit\tunless=skill\ttake=dr_momentum\ttake_max=1\n\
        rule\tdr_momentum\ton\tevent=skill\twhen=end\ttake=dr_momentum\n\
        rule\tdr_momentum\twhile\tcond=skill\tstack=dr_momentum\tmin=3\teffect=540,541,542,543\n";

    #[test]
    fn momentum_layers_hit_and_full_skill() {
        let d = parse(MOMENTUM);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_momentum", 3)]);
        let nl = |v: Vec<Act>| v.into_iter().filter(|a| !matches!(a, Act::Log(_))).collect::<Vec<_>>();
        let mut s = Sim::new();
        let mut t = 0;
        let mut step = |s: &mut Sim, ev: &[&str]| {
            t += 100;
            nl(s.step(&d, &w, ev, Some(30000), t))
        };
        assert_eq!(step(&mut s, &["land", "swing"]), vec![Act::Apply(530)], "普通攻击打中：1 层");
        step(&mut s, &[]);
        assert!(step(&mut s, &["land"]).is_empty(), "不在普通攻击里打中（战技、道具）不加");
        step(&mut s, &[]);
        assert_eq!(step(&mut s, &["land", "swing"]), vec![Act::Remove(530), Act::Apply(531)], "2 层");
        step(&mut s, &[]);
        assert_eq!(step(&mut s, &["hit"]), vec![Act::Remove(531), Act::Apply(530)], "受击掉一层");
        step(&mut s, &[]);
        step(&mut s, &["land", "swing"]);
        step(&mut s, &[]);
        assert_eq!(step(&mut s, &["land", "swing"]), vec![Act::Remove(531), Act::Apply(532)], "3 层");
        step(&mut s, &[]);
        step(&mut s, &["land", "swing"]);
        step(&mut s, &[]);
        // 满层放战技：战技期间挂 full；战技中受击不掉层
        assert_eq!(step(&mut s, &["skill"]), vec![Act::Apply(543)], "满层战技：霸体");
        assert!(step(&mut s, &["skill", "hit"]).is_empty(), "战技中受击：不掉层、霸体还在");
        assert!(step(&mut s, &["skill"]).is_empty());
        // 战技结束：层全部用掉，霸体摘掉
        let a = step(&mut s, &[]);
        assert!(a.contains(&Act::Remove(532)) && a.contains(&Act::Remove(543)) && a.len() == 2, "{a:?}");
        assert!(step(&mut s, &["skill"]).is_empty(), "没层的战技：什么都没有");
        step(&mut s, &[]);
        // 不满层的战技没有霸体，结束时照样用掉
        step(&mut s, &["land", "swing"]);
        step(&mut s, &[]);
        assert!(step(&mut s, &["skill"]).is_empty(), "1 层战技：没有霸体");
        assert_eq!(step(&mut s, &[]), vec![Act::Remove(530)], "用掉");
    }

    const BULWARK: &str = "mark\tguard_hit\t910\nmark\tguard_counter\t911\ncrushtier\t40\t801\ncrushtier\t100\t802\ncrushtier\t300\t803\n\
        aff\tdr_bulwark\t70,71,72,73\nrule\tdr_bulwark\tstack\tadd=guard_hit\tmax=3,4,5,6\ttimeout=10\tfx0=74\tfx1=74\tfx2=74\tfx3=75,76,77,78,79,80\n\
        aff\tdr_recoil\t81,82,83,84\nrule\tdr_recoil\ton\tevent=guard_counter\tburst=10,14,18,25\ttake=dr_bulwark\n\
        aff\tdr_unshaken\t-1,-1,-1,85\nrule\tdr_unshaken\ton\tevent=guard_hit\tguard_scale=4\tshort_hp=200\n";

    #[test]
    fn bulwark_recoil_and_unshaken() {
        let d = parse(BULWARK);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let mut s = Sim::new();
        s.ar = 400.0;
        let w = worn(&[("dr_bulwark", 3), ("dr_recoil", 3)]);
        let mut t = 0;
        for n in 1..=7 {
            t += 200;
            s.step(&d, &w, &["guard_hit"], None, t);
            t += 100;
            s.step(&d, &w, &[], None, t);
            assert!(s.have.contains(&(74 + n.min(6))), "第 {n} 次防住：传说上限 6 层");
        }
        // 防御反击：6 层 × 400 × 25% = 600，挑最接近的 300 那档；壁垒清空
        let acts = s.step(&d, &w, &["guard_counter"], None, t + 200);
        assert_eq!(acts, vec![Act::Apply(803), Act::Log("dr_recoil：6 层 → 冲击波 600（phys 用 300 那档）".into()), Act::Remove(80)]);
        // 有专用行（shocklive）时走实时伤害：伤害照算好的 600，不挑档（用户 2026-11-12）
        let dl = parse(&format!("{BULWARK}shocklive\t990\t7001\nheavypoise\t23\t200\t200\n"));
        assert_eq!((dl.shock_live.clone(), dl.heavy_poise.len()), (vec![(990, 7001)], 1));
        let mut sl = Sim::new();
        sl.ar = 400.0;
        let mut tl = 0;
        for _ in 0..6 {
            tl += 200;
            sl.step(&dl, &w, &["guard_hit"], None, tl);
            tl += 100;
            sl.step(&dl, &w, &[], None, tl);
        }
        let acts = sl.step(&dl, &w, &["guard_counter"], None, tl + 200);
        assert_eq!(acts, vec![Act::ShockLive(600.0), Act::Log("dr_recoil：6 层 → 冲击波 600（实时）".into()), Act::Remove(80)]);
        assert!(s.step(&d, &w, &[], None, t + 300).is_empty());
        assert!(s.step(&d, &w, &["guard_counter"], None, t + 400).is_empty(), "没有壁垒，反击什么都不放");
        // 不动如山：引擎只扣了 1/4（5），真正的消耗 20：补扣 15，够就不扣血
        let w = worn(&[("dr_unshaken", 3)]);
        s.stamina = 100;
        s.step(&d, &w, &[], None, t + 500);
        s.stamina = 95;
        assert_eq!(s.step(&d, &w, &["guard_hit"], None, t + 600), vec![Act::Stamina(-15)]);
        assert_eq!(s.stamina, 80);
        assert!(s.step(&d, &w, &[], None, t + 616).is_empty(), "补扣以后不再算一遍");
        // 精力 20，消耗 40（引擎扣了 10）：剩的 10 扣光，不够的 20 扣两倍的血；事件标记晚一帧看到也照样算上
        s.stamina = 20;
        for k in 0..STAMINA_LOOKBACK as u64 {
            s.step(&d, &w, &[], None, t + 680 + 16 * k);
        }
        s.stamina = 10;
        assert!(s.step(&d, &w, &[], None, t + 712).is_empty());
        assert_eq!(s.step(&d, &w, &["guard_hit"], None, t + 728), vec![Act::Stamina(-10), Act::Hp(-40)]);
        assert_eq!(s.stamina, 0);
        // 精力见底再挨一下（引擎量不出来）：按最近一次量到的 40 估，全扣两倍的血
        s.step(&d, &w, &[], None, t + 744);
        assert_eq!(s.step(&d, &w, &["guard_hit"], None, t + 760), vec![Act::Hp(-80)]);
        // 很久没量过：按最大精力的 20% 估
        s.step(&d, &w, &[], None, t + 776);
        assert_eq!(s.step(&d, &w, &["guard_hit"], None, t + 776 + 11_000), vec![Act::Hp(-40)]);
    }

    /// 相杀（用户 2026-11-04）：轻 / 重击动作播到 25%~75% 挂效果；满蓄力的那一下从蓄力段过完（charged 第一次出现）算起
    const CLASH: &str = "mark\tclash_l_r\t960\nmark\tclash_hc_r\t961\nmark\tcharged\t962\n\
        aff\tdr_clash\t-1,-1,-1,70\n\
        rule\tdr_clash\twhile\tcond=clash_l_r\tprog=0.25,0.75\teffect=-1,-1,-1,71\n\
        rule\tdr_clash\twhile\tcond=clash_hc_r\tprog=0.25,0.75\tprog_from=charged\teffect=-1,-1,-1,72\n";

    /// 相杀按攻击判定（用户 2026-11-04「那就按照攻击判定算」）：判定 0.333~0.400 → 窗口 0.183~0.500；表里没有的动作退回进度 / 不开
    #[test]
    fn clash_hit_window() {
        let d = parse("mark\tclash_l_r\t960\nmark\tclash_h_r\t961\naff\tdr_clash\t-1,-1,-1,70\n\
            rule\tdr_clash\twhile\tcond=clash_l_r\thit=0.15,0.1\tprog=0.25,0.75\teffect=-1,-1,-1,71\n\
            rule\tdr_clash\twhile\tcond=clash_h_r\thit=0.15,0.1\teffect=-1,-1,-1,72\n\
            hitwin\t20030000\t0.333\t0.400\nhitwin\tx\t1\t2\n");
        assert_eq!(d.hits.len(), 1);
        let w = worn(&[("dr_clash", 3)]);
        let nl = |v: Vec<Act>| v.into_iter().filter(|a| !matches!(a, Act::Log(_))).collect::<Vec<_>>();
        let mut s = Sim::new();
        s.anim_len = 1.33;
        s.anim_t = 0.15;
        assert!(nl(s.step(&d, &w, &["clash_l_r"], Some(20030000), 0)).is_empty(), "判定前 0.15 秒以前");
        s.anim_t = 0.2;
        assert_eq!(nl(s.step(&d, &w, &["clash_l_r"], Some(20030000), 20)), vec![Act::Apply(71)], "判定前 0.15 秒内：挂上");
        s.anim_t = 0.48;
        assert!(nl(s.step(&d, &w, &["clash_l_r"], Some(20030000), 40)).is_empty(), "判定后 0.1 秒内：还在");
        s.anim_t = 0.55;
        assert_eq!(nl(s.step(&d, &w, &["clash_l_r"], Some(20030000), 60)), vec![Act::Remove(71)], "后摇：摘掉（进度才 41%）");
        // 表里没有的动作：有 prog 按进度，没 prog 不开
        let mut s = Sim::new();
        s.anim_len = 2.0;
        s.anim_t = 0.6;
        assert_eq!(nl(s.step(&d, &w, &["clash_l_r"], Some(20099999), 0)), vec![Act::Apply(71)], "退回进度 30%");
        let mut s = Sim::new();
        s.anim_len = 2.0;
        s.anim_t = 0.6;
        assert!(nl(s.step(&d, &w, &["clash_h_r"], Some(20099999), 0)).is_empty(), "没 prog：不开");
    }

    #[test]
    fn clash_progress_window() {
        let d = parse(CLASH);
        let w = worn(&[("dr_clash", 3)]);
        // 诊断日志不算
        let nl = |v: Vec<Act>| v.into_iter().filter(|a| !matches!(a, Act::Log(_))).collect::<Vec<_>>();
        let mut s = Sim::new();
        s.anim_len = 2.0;
        s.anim_t = 0.4;
        assert!(nl(s.step(&d, &w, &["clash_l_r"], Some(30000), 0)).is_empty(), "20%：还没到");
        s.anim_t = 0.6;
        assert_eq!(nl(s.step(&d, &w, &["clash_l_r"], Some(30000), 50)), vec![Act::Apply(71)], "30%：挂上");
        s.anim_t = 1.6;
        assert_eq!(nl(s.step(&d, &w, &["clash_l_r"], Some(30000), 100)), vec![Act::Remove(71)], "80%：摘掉");
        // 满蓄力：同一个动作里 charged 在 1.0 秒第一次出现，剩下 1.0 秒的 25%~75% = 1.25~1.75 秒
        let mut s = Sim::new();
        s.anim_len = 2.0;
        s.anim_t = 0.9;
        assert!(nl(s.step(&d, &w, &[], Some(30500), 0)).is_empty(), "蓄力中");
        s.anim_t = 1.0;
        assert!(nl(s.step(&d, &w, &["clash_hc_r", "charged"], Some(30500), 50)).is_empty(), "刚出手");
        s.anim_t = 1.3;
        assert_eq!(nl(s.step(&d, &w, &["clash_hc_r", "charged"], Some(30500), 100)), vec![Act::Apply(72)]);
        s.anim_t = 1.8;
        assert_eq!(nl(s.step(&d, &w, &["clash_hc_r", "charged"], Some(30500), 150)), vec![Act::Remove(72)]);
        // 换了动作：起点重新记
        s.anim_t = 0.6;
        assert!(nl(s.step(&d, &w, &["clash_hc_r"], Some(30505), 200)).is_empty(), "新动作里 charged 还没出现");
        // 诊断：动作开始、窗口打开、结束各记一行
        let mut s = Sim::new();
        s.anim_len = 2.0;
        s.anim_t = 0.6;
        let logs = |v: Vec<Act>| v.into_iter().filter_map(|a| if let Act::Log(t) = a { Some(t) } else { None }).collect::<Vec<_>>();
        let l = logs(s.step(&d, &w, &["clash_l_r"], Some(30010), 0));
        assert!(l.iter().any(|t| t.contains("开始")) && l.iter().any(|t| t.contains("窗口打开")), "{l:?}");
        let l = logs(s.step(&d, &w, &[], Some(30010), 50));
        assert!(l.iter().any(|t| t.contains("结束") && t.contains("开过")), "{l:?}");
    }

    const BLOOD: &str = "aff\tdr_pact\t-1,-1,-1,90\nrule\tdr_pact\twhile\tfp_to_hp=150\n\
        aff\tdr_surge\t91,92,93,94\nrule\tdr_surge\twhile\thp_below=50\teffect=95,96,97,98\nrule\tdr_surge\twhile\thp_below=50\teffect=99,100,101,102\n";

    #[test]
    fn blood_pact_and_surge() {
        let d = parse(BLOOD);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let mut s = Sim::new();
        let w = worn(&[("dr_pact", 3), ("dr_surge", 1)]);
        // 刚戴上：专注只补满，不扣血
        s.fp = 60;
        assert_eq!(s.step(&d, &w, &[], None, 0), vec![Act::Fp(40)]);
        s.fp = 100;
        assert!(s.step(&d, &w, &[], None, 100).is_empty());
        // 施法掉 20 专注：补回来，扣 30 血
        s.fp = 80;
        assert_eq!(s.step(&d, &w, &[], None, 200), vec![Act::Fp(20), Act::Hp(-30), Act::Log("dr_pact：专注 20 → 扣血 30".into())]);
        s.fp = 98;
        assert_eq!(s.step(&d, &w, &[], None, 300), vec![Act::Fp(2), Act::Hp(-3)], "持续耗蓝的每帧也扣，少的不写日志");
        // 血量低于一半：血涌的两行都挂；回到一半以上摘掉
        s.fp = 100;
        s.hp = 499;
        assert_eq!(s.step(&d, &w, &[], None, 400), vec![Act::Apply(96), Act::Apply(100)]);
        s.hp = 500;
        assert_eq!(s.step(&d, &w, &[], None, 500), vec![Act::Remove(96), Act::Remove(100)]);
        // 摘下血契再戴上：又是刚戴上
        s.step(&d, &worn(&[]), &[], None, 600);
        s.fp = 50;
        assert_eq!(s.step(&d, &w, &[], None, 700), vec![Act::Fp(50)]);
    }

    #[test]
    fn desperate_one_tier_at_a_time() {
        // 背水：每一档只挂一行（hp_below / hp_above 夹着），图标写着档数
        let d = parse("aff\tdr_back\t1,2,3,4\nrule\tdr_back\twhile\thp_below=90\thp_above=80\teffect=11,12,13,14\n\
            rule\tdr_back\twhile\thp_below=80\teffect=21,22,23,24\n");
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let mut s = Sim::new();
        let w = worn(&[("dr_back", 3)]);
        assert!(s.step(&d, &w, &[], None, 0).is_empty(), "满血不挂");
        s.hp = 850;
        assert_eq!(s.step(&d, &w, &[], None, 100), vec![Act::Apply(14)]);
        s.hp = 800;
        assert!(s.step(&d, &w, &[], None, 200).is_empty(), "正好 80％ 还是第一档");
        s.hp = 799;
        assert_eq!(s.step(&d, &w, &[], None, 300), vec![Act::Remove(14), Act::Apply(24)], "进第二档：换一行，不是叠着");
        s.hp = 1000;
        assert_eq!(s.step(&d, &w, &[], None, 400), vec![Act::Remove(24)]);
    }

    const RALLY: &str = "mark\thit\t903\nmark\tflask\t904\nmark\tphysick\t905\nmark\tland\t906\nmark\tbleed\t907\n\
        aff\tdr_rally\t110,111,112,113\nrule\tdr_rally\trally\tevent=land\twindow=3,3.5,4,5\tpct=10,14,18,25\teffect=114,114,114,115\tflash=116\tboost_key=dr_debt\tboost=3\tlog=反扑\n\
        aff\tdr_debt\t-1,-1,-1,120\nrule\tdr_debt\ton\tevent=flask\tfp_pct=30\tdeny_heal=3\teffect=121\n\
        aff\tdr_ward\t130,131,132,133\nrule\tdr_ward\ton\tevent=physick\teffect=134,135,136,137\n\
        aff\tdr_thirst\t140,140,140,140\nrule\tdr_thirst\ton\tevent=land\tcond=bleed\thp_pct=3\n\
        iframe\t134,135,136,137\n";

    #[test]
    fn rally_takes_back_lost_hp() {
        let d = parse(RALLY);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let mut s = Sim::new();
        let w = worn(&[("dr_rally", 3)]);
        assert!(s.step(&d, &w, &[], None, 0).is_empty());
        // 受击掉 200：窗口 5 秒，挂窗口期的效果
        s.hp = 800;
        assert_eq!(s.step(&d, &w, &["hit"], None, 100), vec![Act::Apply(115)]);
        // 每次命中回 损失的 25%
        assert_eq!(s.step(&d, &w, &["land"], None, 200), vec![Act::Hp(50), Act::Apply(116), Act::Log("反扑：回 50（损失 200，还能回 150）".into())]);
        assert!(s.step(&d, &w, &[], None, 300).is_empty(), "自己回的血不算自然回血 / 掉血");
        assert_eq!(s.step(&d, &w, &["land"], None, 400)[0], Act::Hp(50));
        // 窗口过了：清空，命中不再回
        assert_eq!(s.step(&d, &w, &[], None, 5200), vec![Act::Remove(115)]);
        assert!(s.step(&d, &w, &["land"], None, 5300).is_empty());
        // 掉血比受击事件早到：等 HIT_LINK 内对上
        s.hp = 800;
        assert!(s.step(&d, &w, &[], None, 6000).is_empty());
        assert_eq!(s.step(&d, &w, &["hit"], None, 6100), vec![Act::Apply(115)]);
        // 没有受击事件的掉血（毒之类）不算
        s.hp = 700;
        s.step(&d, &w, &[], None, 7000);
        s.step(&d, &w, &[], None, 7400);
        assert_eq!(s.step(&d, &w, &["land"], None, 7500)[2], Act::Log("反扑：回 25（损失 100，还能回 75）".into()));
    }

    #[test]
    fn blood_debt_flask_ward_and_thirst() {
        let d = parse(RALLY);
        assert_eq!(d.iframes, vec![134, 135, 136, 137]);
        // 血债：反扑 ×3；红瓶回 30% 专注，之后 3 秒自然回的血扣回去
        let mut s = Sim::new();
        let w = worn(&[("dr_rally", 3), ("dr_debt", 3)]);
        s.step(&d, &w, &[], None, 0);
        s.hp = 800;
        s.step(&d, &w, &["hit"], None, 100);
        assert_eq!(s.step(&d, &w, &["land"], None, 200)[0], Act::Hp(150));
        s.fp = 50;
        assert_eq!(s.step(&d, &w, &["flask"], None, 300), vec![Act::Fp(30), Act::Apply(121)]);
        s.hp = 1000;
        assert_eq!(s.step(&d, &w, &["flask"], None, 400), vec![Act::Hp(-50), Act::Log("dr_debt：回血 50 扣回去".into())]);
        assert!(s.step(&d, &w, &[], None, 500).is_empty());
        s.hp = 1000;
        assert!(s.step(&d, &w, &[], None, 3400).is_empty(), "过了 3 秒不再扣");
        // 无敌：开始喝灵药的第一帧就挂，持续时间从这一刻起算并覆盖喝药动作
        let mut s = Sim::new();
        let w = worn(&[("dr_ward", 1)]);
        assert_eq!(s.step(&d, &w, &["physick"], None, 0), vec![Act::Apply(135)]);
        assert!(s.step(&d, &w, &["physick"], None, 100).is_empty(), "喝药动作持续时不要重复挂");
        assert!(s.step(&d, &w, &[], None, 200).is_empty(), "效果已经挂上，结束时不再补一次");
        // 渴血：周围出血的状态在时，命中回 3% 最大血量
        let mut s = Sim::new();
        let w = worn(&[("dr_thirst", 0)]);
        assert!(s.step(&d, &w, &["land"], None, 0).is_empty());
        s.step(&d, &w, &[], None, 50);
        assert_eq!(s.step(&d, &w, &["land", "bleed"], None, 100), vec![Act::Hp(30)]);
    }

    const ORB: &str = "mark\tcast\t950\nmark\tbackstep\t951\n\
        bursttier\tpebble\t60\t960\nbursttier\tpebble\t150\t961\nbursttier\tpebble\t400\t962\n\
        aff\tdr_orb\t200,201,202,203\nrule\tdr_orb\tstack\tadd=cast\tmax=1,2,2,3\tmax_boost_key=dr_hawk\tmax_boost=1,2,3,4\ttimeout=20\tfx0=210,211\tfx1=210,211,212\tfx2=210,211,212\tfx3=210,211,212,213\n\
        aff\tdr_flowing\t220,221,222,223\nrule\tdr_flowing\twhile\tstack=dr_orb\tmin=1\teffect=230,231,232,233\nrule\tdr_flowing\twhile\tstack=dr_orb\tmin=2\teffect=240,241,242,243\n\
        aff\tdr_burst\t250,251,252,253\nrule\tdr_burst\ton\tevent=cast\ttake=dr_orb\ttake_full=1\tburst_flat=60,90,120,160\tburst_kind=pebble\tburst_each=1\n\
        aff\tdr_swarm\t-1,-1,-1,260\nrule\tdr_swarm\ton\tevery=2\ttake=dr_orb\ttake_max=1\tburst_flat=160\tburst_kind=pebble\tburst_each=1\tburst_spell=1\n\
        aff\tdr_hawk\t270,271,272,273\n";

    #[test]
    fn orbs_gather_flow_and_burst() {
        let d = parse(ORB);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let mut s = Sim::new();
        let w = worn(&[("dr_orb", 0), ("dr_hawk", 0), ("dr_flowing", 0), ("dr_burst", 3)]);
        assert_eq!(s.step(&d, &w, &["cast"], None, 0), vec![Act::Apply(210)]);
        assert_eq!(s.step(&d, &w, &[], None, 100), vec![Act::Apply(230)], "涌流看上一帧的颗数");
        assert_eq!(s.step(&d, &w, &["cast"], None, 200), vec![Act::Remove(210), Act::Apply(211)], "盈满（普通 +1）：普通的上限 1 + 1");
        assert_eq!(s.step(&d, &w, &[], None, 300), vec![Act::Apply(240)]);
        // 满了之后下一次施法：两颗全部射出，一颗接一颗（每颗 160，魔砾那套最接近的是 150），这次施法不另出一颗；第二颗 BURST_GAP 后
        s.step(&d, &w, &[], None, 350);
        assert_eq!(s.step(&d, &w, &["cast"], None, 400),
                   vec![Act::Apply(961), Act::Log("dr_burst：2 层 → 2 下，每下 160（pebble 用 150 那档）".into()), Act::Remove(211), Act::Remove(230), Act::Remove(240)]);
        assert!(s.step(&d, &w, &[], None, 460).is_empty(), "第二颗还没到时间");
        assert_eq!(s.step(&d, &w, &[], None, 400 + BURST_GAP.as_millis() as u64), vec![Act::Apply(961)]);
        assert!(s.step(&d, &w, &[], None, 700).is_empty(), "只有两颗");
        // 射空以后施法照常攒；没满时施法不射
        assert_eq!(s.step(&d, &w, &["cast"], None, 800), vec![Act::Apply(210)]);
        s.step(&d, &w, &[], None, 900);
        assert_eq!(s.step(&d, &w, &["cast"], None, 1000)[..2], [Act::Remove(210), Act::Apply(211)], "1 颗时施法：加到 2 颗，不射");
        // 星群：每 2 秒自动射出一颗
        let mut s = Sim::new();
        let w = worn(&[("dr_orb", 3), ("dr_swarm", 3)]);
        assert!(s.step(&d, &w, &[], None, 0).is_empty(), "没有法球就等着");
        assert_eq!(s.step(&d, &w, &["cast"], None, 100), vec![Act::Apply(210)]);
        assert_eq!(s.step(&d, &w, &[], None, 200),
                   vec![Act::Apply(961), Act::Log("dr_swarm：1 层 → 1 下，每下 160（pebble 用 150 那档）".into()), Act::Remove(210)]);
        assert_eq!(s.step(&d, &w, &["cast"], None, 300), vec![Act::Apply(210)]);
        assert!(s.step(&d, &w, &[], None, 2100).is_empty(), "2 秒内不再射");
        assert_eq!(s.step(&d, &w, &[], None, 2300)[0], Act::Apply(961));
        // 智力的倍率 ×2.5（procs）：每颗 400，用 400 那档；物理的倍率不管
        s.scale = [9.0, 2.5, 1.0, 1.0, 1.0];
        s.step(&d, &w, &["cast"], None, 2400);
        assert_eq!(s.step(&d, &w, &[], None, 4400),
                   vec![Act::Apply(962), Act::Log("dr_swarm：1 层 → 1 下，每下 400（pebble 用 400 那档）".into()), Act::Remove(210)]);
        // 拿着基数 150 的法器（burst_spell）：再 ×1.5 = 600，最接近的还是 400 那档；迸发没写 burst_spell，不乘
        s.spell = 1.5;
        s.step(&d, &w, &["cast"], None, 4500);
        assert_eq!(s.step(&d, &w, &[], None, 6500),
                   vec![Act::Apply(962), Act::Log("dr_swarm：1 层 → 1 下，每下 600（pebble 用 400 那档）".into()), Act::Remove(210)]);
    }

    /// 星群每颗法球加快 5% 施法（用户 2026-11-06）：只在施法全程（casting）生效，按身边的颗数，平时不变速
    #[test]
    fn swarm_cast_speed_per_orb() {
        let text = format!("{ORB}mark\tcasting\t952\naff\tdr_cs\t-1,-1,-1,280\nrule\tdr_cs\twhile\tcond=casting\tstack=dr_orb\tmin=1\tlayer_speed=5\n");
        let d = parse(&text);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let mut s = Sim::new();
        let w = worn(&[("dr_orb", 3), ("dr_cs", 3)]);
        s.step(&d, &w, &["casting"], None, 0);
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "没有法球：不变速");
        for t in [100, 300, 500] {
            s.step(&d, &w, &["cast"], None, t);
            s.step(&d, &w, &[], None, t + 100);
            assert!((s.e.action_mult - 1.0).abs() < 1e-5, "没在施法：不变速");
        }
        s.step(&d, &w, &["casting"], None, 700);
        assert!((s.e.action_mult - 1.15).abs() < 1e-5, "3 颗：×1.15，实际 {}", s.e.action_mult);
        s.step(&d, &w, &[], None, 800);
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "施法结束：恢复");
    }

    /// 星群吃迸发的「每颗 +15%」（用户 2026-11-06）：一次只射一颗，按射出时身边有几颗算（含这一颗）
    #[test]
    fn swarm_grows_with_held_orbs() {
        let text = ORB.replace("take_max=1\tburst_flat=160\tburst_kind=pebble\tburst_each=1\tburst_spell=1",
                               "take_max=1\tburst_flat=160\tburst_kind=pebble\tburst_each=1\tburst_spell=1\tburst_grow=15\tgrow_held=1");
        assert_ne!(text, ORB);
        let d = parse(&text);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let mut s = Sim::new();
        let w = worn(&[("dr_orb", 3), ("dr_swarm", 3)]);
        let log = |dmg: u32| Act::Log(format!("dr_swarm：1 层 → 1 下，每下 {dmg}（pebble 用 150 那档）"));
        s.step(&d, &w, &[], None, 0);
        s.step(&d, &w, &["cast"], None, 100);
        assert!(s.step(&d, &w, &[], None, 200).contains(&log(184)), "身边 1 颗：×1.15");
        for t in [300, 500, 700] {
            s.step(&d, &w, &["cast"], None, t);
            s.step(&d, &w, &[], None, t + 100);
        }
        assert!(s.step(&d, &w, &[], None, 2300).contains(&log(232)), "身边 3 颗：×1.45");
        assert!(s.step(&d, &w, &[], None, 4400).contains(&log(208)), "还剩 2 颗：×1.30");
    }

    /// 盈满（原名鹰眼视觉，2026-11-04）：法球上限按盈满戴着的稀有度多 1 / 2 / 3 / 4 颗
    #[test]
    fn brimming_boost_by_rarity() {
        let d = parse("mark\tcast\t960\naff\tdr_orb\t200,201,202,203\n\
            rule\tdr_orb\tstack\tadd=cast\tmax=1,2,2,3\tmax_boost_key=dr_hawk\tmax_boost=1,2,3,4\ttimeout=20\tfx0=210,211,212,213,214,215,216\n\
            aff\tdr_hawk\t270,271,272,273\n");
        let cap = |hawk: Option<usize>| {
            let w = match hawk {
                Some(r) => worn(&[("dr_orb", 0), ("dr_hawk", r)]),
                None => worn(&[("dr_orb", 0)]),
            };
            let mut s = Sim::new();
            let mut n = 0;
            for k in 0..10u64 {
                let a = s.step(&d, &w, &["cast"], None, k * 200);
                n += a.iter().filter(|x| matches!(x, Act::Apply(_))).count();
                s.step(&d, &w, &[], None, k * 200 + 100);
            }
            n
        };
        assert_eq!(cap(None), 1, "没戴盈满：普通凝聚 1 颗");
        assert_eq!(cap(Some(0)), 2, "普通盈满 +1");
        assert_eq!(cap(Some(1)), 3, "稀有 +2");
        assert_eq!(cap(Some(3)), 5, "传说 +4");
    }

    const AIR: &str = "mark\tland\t906\nmark\tjump\t990\nmark\tfloat_hit\t991\nmark\tair_jump\t992\nmark\tjland\t993\nmark\tjatk\t994\nmark\tair\t995\n\
        aff\tdr_aerial\t400,401,402,403\nrule\tdr_aerial\tstack\tadd=land\tcond=jatk\tmax=1\ttimeout=0.5\tfx0=410\tfx1=411\tfx2=412\tfx3=413\n\
        rule\tdr_aerial\ton\tevent=air_jump\ttake=dr_aerial\ttake_max=1\n\
        rule\tdr_aerial\tstack\tadd=air_jump\tmax=5\ttimeout=2.5\tfx0=430,431,432,433,434\tfx1=440,441,442,443,444\tfx2=450,451,452,453,454\tfx3=460,461,462,463,464\n\
        aff\tdr_chasm\t-1,-1,-1,420\nrule\tdr_chasm\ton\tevent=jump\tstamina_back=100\nrule\tdr_chasm\twhile\tcond=ground\tunless=jland\teffect=421\n";

    #[test]
    fn air_jumps_and_free_jumping() {
        let d = parse(AIR);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        // 凌空（命中后接跳）：跳跃攻击中（jatk）命中 → 0.5 秒「可以接跳」；接跳拿走它、连跳加一层（换下一层的效果）；2.5 秒没接跳连跳清零
        let mut s = Sim::new();
        let w = worn(&[("dr_aerial", 3)]);
        s.step(&d, &w, &["ground"], None, 0);
        assert!(s.step(&d, &w, &["ground", "land"], None, 100).is_empty(), "不是跳跃攻击的命中不给");
        s.step(&d, &w, &["air", "jatk"], None, 200);
        assert_eq!(s.step(&d, &w, &["ground", "jatk", "land"], None, 300), vec![Act::Apply(413)], "跳跃攻击命中给「可以接跳」");
        assert_eq!(s.step(&d, &w, &["ground", "air_jump"], None, 400), vec![Act::Remove(413), Act::Apply(460)], "接跳：拿走「可以接跳」、连跳一层");
        assert!(s.step(&d, &w, &["air"], None, 450).is_empty());
        assert_eq!(s.step(&d, &w, &["ground", "jatk", "land"], None, 1500), vec![Act::Apply(413)]);
        assert_eq!(s.step(&d, &w, &["ground", "air_jump"], None, 1600), vec![Act::Remove(413), Act::Remove(460), Act::Apply(461)], "连跳两层");
        assert_eq!(s.step(&d, &w, &["ground", "jatk", "land"], None, 2000), vec![Act::Apply(413)]);
        assert_eq!(s.step(&d, &w, &["ground"], None, 2700), vec![Act::Remove(413)], "命中了没接跳：0.5 秒后过期");
        assert_eq!(s.step(&d, &w, &["ground"], None, 4300), vec![Act::Remove(461)], "2.5 秒没接跳：连跳清零");
        // 天堑：起跳掉的精力补回来；在地上挂减伤害的效果，跳劈落地（jland）那一下不挂
        let mut s = Sim::new();
        let w = worn(&[("dr_chasm", 3)]);
        assert_eq!(s.step(&d, &w, &["ground"], None, 0), vec![Act::Apply(421)]);
        s.stamina = 80;
        assert_eq!(s.step(&d, &w, &["ground", "jump"], None, 100), vec![Act::Stamina(20)]);
        assert_eq!(s.step(&d, &w, &["air", "jump"], None, 200), vec![Act::Remove(421)]);
        assert!(s.step(&d, &w, &["ground", "jland"], None, 300).is_empty(), "跳劈落地不减");
        assert_eq!(s.step(&d, &w, &["ground"], None, 400), vec![Act::Apply(421)], "落地动作做完才减");
    }

    const DODGE: &str = "mark\troll\t907\nmark\tattack\t902\n\
        aff\tdr_mikiri\t500,501,502,503\nrule\tdr_mikiri\ton\tevent=mikiri\tfoe_slow=30,40,50,60\tfoe_radius=8\tfoe_secs=2\tfreeze_key=dr_shadow\tfreeze_secs=1\n\
        aff\tdr_zanshin\t510,511,512,513\nrule\tdr_zanshin\tstack\tadd=mikiri\tconsume=attack\tmax=1\ttimeout=3\tfx0=520\tfx1=521\tfx2=522\tfx3=523\n\
        aff\tdr_shadow\t-1,-1,-1,530\nrule\tdr_shadow\twhile\tcond=roll\tcut_after=0.2\n";

    #[test]
    fn mikiri_slows_and_shadowstep() {
        let d = parse(DODGE);
        assert!(d.skipped.is_empty() && d.mikiri, "{:?}", d.skipped);
        let mut s = Sim::new();
        let w = worn(&[("dr_mikiri", 3), ("dr_zanshin", 0)]);
        let mut a = foe(1, 3.0, vec![], false);
        a.anim = Some(3010);
        s.foes = vec![a, foe(2, 7.0, vec![], false), foe(3, 12.0, vec![], false)];
        assert!(s.step(&d, &w, &[], None, 0).is_empty(), "不在翻滚");
        // 翻滚中 3 米内的敌人在出招：8 米内的两个敌人减速 60%，残心挂上
        let m: f32 = 1.0 - 60.0 / 100.0;
        assert_eq!(s.step(&d, &w, &["roll"], None, 100),
                   vec![Act::Log("见切：近战（NPC 0 动作 3010 模型 c0000 不在判定表里，按进度 50% 估 距离 3.0 体型 0.5 夹角 0°）".into()),
                        Act::Log("dr_mikiri：周围 2 个敌人动作 ×0.40（2 秒）".into()), Act::FoeSpeed(1, m), Act::FoeSpeed(2, m), Act::Apply(520)]);
        assert_eq!(s.step(&d, &w, &["roll"], None, 200), vec![Act::FoeSpeed(1, m), Act::FoeSpeed(2, m)], "一次翻滚只算一次");
        assert_eq!(s.step(&d, &w, &[], None, 2200), vec![Act::FoeSpeed(1, 1.0), Act::FoeSpeed(2, 1.0)], "2 秒到期改回");
        assert_eq!(s.step(&d, &w, &[], None, 3200), vec![Act::Remove(520)], "残心 3 秒没出手就散");
        // 影步：减速变成停住 1 秒；翻滚 0.2 秒后清无敌位
        let mut s = Sim::new();
        let w = worn(&[("dr_mikiri", 3), ("dr_shadow", 3)]);
        let mut a = foe(1, 3.0, vec![], false);
        a.anim = Some(3010);
        s.foes = vec![a];
        s.step(&d, &w, &[], None, 0);
        assert_eq!(s.step(&d, &w, &["roll"], None, 100)[1..], [Act::Log("dr_mikiri：周围 1 个敌人停住（1 秒）".into()), Act::FoeSpeed(1, 0.0)]);
        assert_eq!(s.step(&d, &w, &["roll"], None, 350), vec![Act::FoeSpeed(1, 0.0), Act::CutIFrames(true)]);
        assert_eq!(s.step(&d, &w, &[], None, 400), vec![Act::FoeSpeed(1, 0.0), Act::CutIFrames(false)]);
        assert_eq!(s.step(&d, &w, &[], None, 1200), vec![Act::FoeSpeed(1, 1.0)]);
    }

    /// 减速中的敌人掉出扫描列表（拉塔恩这类按物理位置补进来的，补的列表清空了）：马上改回 1，不再一直慢着（用户 2026-11-12）
    #[test]
    fn slowed_foe_leaving_scan_is_restored() {
        let d = parse(DODGE);
        let mut s = Sim::new();
        let w = worn(&[("dr_mikiri", 3)]);
        let mut a = foe(1, 3.0, vec![], false);
        a.anim = Some(3010);
        s.foes = vec![a];
        s.step(&d, &w, &[], None, 0);
        let m: f32 = 1.0 - 60.0 / 100.0;
        assert!(s.step(&d, &w, &["roll"], None, 100).contains(&Act::FoeSpeed(1, m)));
        s.foes.clear();
        assert_eq!(s.step(&d, &w, &[], None, 300), vec![Act::FoeSpeed(1, 1.0)], "掉出列表就改回");
        assert!(s.step(&d, &w, &[], None, 2200).is_empty(), "已经去掉了，到期不再发");
    }

    /// 见切触发的加速的光晕：等 0.35 秒、翻滚完才挂；挂一次；加速结束摘；没挂过就不用摘；下一轮重新算
    #[test]
    fn late_glow_waits_for_dodge() {
        let t0 = Instant::now();
        let ms = |m: u64| t0 + Duration::from_millis(m);
        let mut st = None;
        assert_eq!(late_glow_step(&mut st, ms(0), true, true), None, "刚见切：不挂");
        assert_eq!(late_glow_step(&mut st, ms(400), true, true), None, "还在翻滚：不挂");
        assert_eq!(late_glow_step(&mut st, ms(600), true, false), Some(true), "翻滚完、过了 0.35 秒：挂");
        assert_eq!(late_glow_step(&mut st, ms(700), true, false), None, "挂过了不再挂");
        assert_eq!(late_glow_step(&mut st, ms(3000), false, false), Some(false), "加速结束：摘");
        assert_eq!(st, None);
        assert_eq!(late_glow_step(&mut st, ms(3100), false, false), None, "没在加速：不动");
        assert_eq!(late_glow_step(&mut st, ms(5000), true, false), None, "下一轮刚开始：等");
        assert_eq!(late_glow_step(&mut st, ms(5200), false, false), None, "还没挂就结束了：不用摘");
        assert_eq!(late_glow_step(&mut st, ms(6000), true, false), None);
        assert_eq!(late_glow_step(&mut st, ms(6350), true, false), Some(true), "没翻滚：0.35 秒后挂");
    }

    /// 影步（用户 2026-11-12「改为见切后自身动作加快50%3s」「影步必须有见切才生效」）：不再停住敌人；只戴影步不触发；
    /// 和处刑的加快各算各的，同时在就相乘
    #[test]
    fn shadowstep_haste_after_mikiri() {
        let d = parse("mark\troll\t907\nmark\tcrit\t906\n\
            aff\tdr_mikiri\t500,501,502,503\nrule\tdr_mikiri\ton\tevent=mikiri\tfoe_slow=30,40,50,60\tfoe_radius=8\tfoe_secs=2\n\
            aff\tdr_shadowstep\t-1,-1,-1,540\nrule\tdr_shadowstep\ton\tevent=mikiri\teffect=550,551,552,553\thaste=50\thaste_secs=3\trequires=dr_mikiri\n\
            aff\tdr_execute\t510,511,512,513\nrule\tdr_execute\ton\tevent=crit\twhen=end\teffect=520,521,522,523\thaste=20\thaste_secs=10\n");
        assert!(d.skipped.is_empty() && d.mikiri, "{:?}", d.skipped);
        let attacker = || {
            let mut a = foe(1, 3.0, vec![], false);
            a.anim = Some(3010);
            vec![a]
        };
        // 只戴影步：见切判定照样有，但影步当没戴，不加快
        let alone = worn(&[("dr_shadowstep", 3)]);
        let mut s = Sim::new();
        s.foes = attacker();
        s.step(&d, &alone, &[], None, 0);
        let acts = s.step(&d, &alone, &["roll"], None, 100);
        assert!(!acts.contains(&Act::Apply(553)), "{acts:?}");
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "只戴影步不加快：{}", s.e.action_mult);
        // 见切 + 影步 + 处刑
        let w = worn(&[("dr_mikiri", 3), ("dr_shadowstep", 3), ("dr_execute", 3)]);
        let mut s = Sim::new();
        s.foes = attacker();
        s.step(&d, &w, &[], None, 0);
        let acts = s.step(&d, &w, &["roll"], None, 100);
        assert!(acts.contains(&Act::Apply(553)), "{acts:?}");
        assert!(acts.contains(&Act::FoeSpeed(1, 1.0 - 60.0 / 100.0)), "见切照样减速、不停住：{acts:?}");
        assert!((s.e.action_mult - 1.5).abs() < 1e-5, "{}", s.e.action_mult);
        s.step(&d, &w, &["crit"], Some(1), 200);
        s.step(&d, &w, &[], Some(2), 300);
        assert!((s.e.action_mult - 1.8).abs() < 1e-5, "影步 × 处刑：{}", s.e.action_mult);
        s.step(&d, &w, &[], Some(2), 3200);
        assert!((s.e.action_mult - 1.2).abs() < 1e-5, "影步 3 秒到，只剩处刑：{}", s.e.action_mult);
        s.step(&d, &w, &[], Some(2), 10_400);
        assert!((s.e.action_mult - 1.0).abs() < 1e-5, "都到期：{}", s.e.action_mult);
    }

    /// 减速 / 停住的敌人转身：停住不转、减半只转一半、跨过 ±180° 走短的那边
    #[test]
    fn turn_slowdown() {
        assert_eq!(turn_step(None, 0.7, 0.0), 0.7);
        assert_eq!(turn_step(Some(0.0), 0.3, 0.0), 0.0);
        assert!((turn_step(Some(0.0), 0.4, 0.5) - 0.2).abs() < 1e-6);
        let y = turn_step(Some(3.1), -3.1, 0.5);
        assert!((crate::boat::wrap(y - 3.1) - (2.0 * std::f32::consts::PI - 6.2) / 2.0).abs() < 1e-4, "{y}");
    }

    #[test]
    fn mikiri_filters() {
        let d = parse(DODGE);
        let w = worn(&[("dr_mikiri", 3)]);
        let attacker = |x: f32| {
            let mut f = foe(1, x, vec![], false);
            f.anim = Some(3010);
            f
        };
        let hit = |s: &mut Sim, t: u64| {
            s.step(&d, &w, &[], None, t);
            let a = s.step(&d, &w, &["roll"], None, t + 50);
            a.first().and_then(|x| if let Act::Log(m) = x { m.strip_prefix("见切：").map(String::from) } else { None })
        };
        // 不在无敌帧（比如碾压清掉了）不算
        let mut s = Sim::new();
        s.foes = vec![attacker(3.0)];
        s.iframe = false;
        assert_eq!(hit(&mut s, 0), None);
        // 出招刚起手 / 快收招、背对着、太远：都不算
        for f in [|f: &mut Foe| f.progress = 0.1, |f: &mut Foe| f.progress = 0.9, |f: &mut Foe| f.fwd = [1.0, 0.0], |f: &mut Foe| f.pos = [6.0, 0.0, 0.0]] {
            let mut s = Sim::new();
            let mut a = attacker(3.0);
            f(&mut a);
            s.foes = vec![a];
            assert_eq!(hit(&mut s, 0), None);
        }
        // 大体型：5.5 米外也够得着（4 + 2）
        let mut s = Sim::new();
        let mut a = attacker(5.5);
        a.radius = 2.0;
        s.foes = vec![a];
        assert!(hit(&mut s, 0).is_some_and(|m| m.starts_with("近战")));
        // 同一招只算一次：再滚一次不算，换了一招又算
        assert_eq!(hit(&mut s, 1000), None);
        s.foes[0].anim = Some(3020);
        assert!(hit(&mut s, 2000).is_some());
        // 子弹：敌人的子弹落在身上算，自己人的不算
        let mut s = Sim::new();
        s.shots = vec![Shot { pos: [1.0, 0.5, 0.0], radius: 0.8, hostile: false }];
        assert_eq!(hit(&mut s, 0), None);
        s.shots[0].hostile = true;
        assert_eq!(hit(&mut s, 1000), Some("子弹（命中半径 0.8，距离 1.1）".into()));
        // 没成立的翻滚写一行调参日志（背对着：夹角 180°，反过来算 0°）
        let mut s = Sim::new();
        let mut a = attacker(3.0);
        a.fwd = [1.0, 0.0];
        s.foes = vec![a];
        s.step(&d, &w, &[], None, 0);
        assert!(s.step(&d, &w, &["roll"], None, 50).is_empty());
        assert_eq!(s.step(&d, &w, &[], None, 100),
                   vec![Act::Log("见切没成立（翻滚 1 帧，其中无敌 1 帧）：最近出招的角色 NPC 0 阵营 6 动作 3010 模型 c0000 不在判定表里，按进度 50% 估 距离 3.0（够得着 4.5）夹角 180°（反过来算 0°）；\
                                  最近的角色 NPC 0 阵营 6 动作 Some(3010) 距离 3.0；最近的敌方子弹 无".into())]);
        // 后撤步也算
        let mut s = Sim::new();
        s.foes = vec![attacker(2.0)];
        s.step(&d, &w, &[], None, 0);
        assert!(matches!(s.step(&d, &w, &["backstep"], None, 50).first(), Some(Act::Log(m)) if m.starts_with("见切")));
    }

    /// 见切按敌人的攻击判定算（用户 2026-11-11「用出招判定帧」「见切前后不用留了」）：只有判定中算，判定前后差一点也不算，出招了但判定没到 / 过了不算；
    /// 表里有这个模型但这个动作没有攻击判定（吼叫）不算；变体模型用基础模型的表；表里没有的模型照旧按进度估
    #[test]
    fn mikiri_uses_attack_windows() {
        let d = parse(&format!("{DODGE}foewin\t4300\t3000\t2.567,2.733\nfoewin\t4300\t3002\t1.233,1.4;2.5,2.667\nfoewin\t4300\tx\t1,2\n"));
        assert_eq!((d.foe_models.len(), d.foe_hits.len()), (1, 2));
        let w = worn(&[("dr_mikiri", 3)]);
        let hit = |model: u32, anim: i32, play: f32| {
            let mut s = Sim::new();
            let mut f = foe(1, 3.0, vec![], false);
            (f.model, f.anim, f.play) = (model, Some(anim), play);
            s.foes = vec![f];
            s.step(&d, &w, &[], None, 0);
            let a = s.step(&d, &w, &["roll"], None, 50);
            a.first().and_then(|x| if let Act::Log(m) = x { m.strip_prefix("见切：").map(String::from) } else { None })
        };
        assert_eq!(hit(4300, 3000, 2.6), Some("近战（NPC 0 动作 3000 第 2.60 秒（判定 2.57–2.73） 距离 3.0 体型 0.5 夹角 0°）".into()));
        assert_eq!(hit(4300, 3000, 2.53), None, "判定前 0.04 秒（前后不留余量）");
        assert_eq!(hit(4300, 3000, 2.76), None, "判定后 0.03 秒");
        assert!(hit(4300, 3000, 2.567).is_some(), "判定开始那一刻");
        assert_eq!(hit(4300, 3000, 1.5), None, "出招了但判定还没到（以前按进度 50% 会算）");
        assert_eq!(hit(4300, 3000, 2.9), None, "判定过了");
        assert_eq!(hit(4300, 3000, -1.0), None, "读不到播放时间");
        assert!(hit(4300, 3002, 2.55).is_some(), "第二刀");
        assert_eq!(hit(4300, 3002, 1.9), None, "两刀之间");
        assert_eq!(hit(4300, 3010, 1.0), None, "这个动作没有攻击判定");
        assert!(hit(4301, 3000, 2.6).is_some(), "变体模型用基础模型的表");
        assert_eq!(hit(4301, 3000, 1.0), None);
        assert!(hit(2500, 3010, 1.0).is_some_and(|m| m.contains("模型 c2500 不在判定表里，按进度 50% 估")), "表里没有的模型照旧估");
    }

    /// 叠着播的动作（用户 2026-11-12：梅瑟莫模组 c5130 一直读到 43000，出招在同时在播的另一格里）：叠着的那个在判定里也算
    #[test]
    fn mikiri_sees_layered_attack() {
        let d = parse(&format!("{DODGE}foewin\t5130\t3010\t0.400,0.600\n"));
        let w = worn(&[("dr_mikiri", 3)]);
        let hit = |layers: Vec<(i32, f32)>| {
            let mut s = Sim::new();
            let mut f = foe(1, 3.0, vec![], false);
            (f.model, f.anim, f.play, f.layers) = (5130, Some(43000), 5.0, layers);
            s.foes = vec![f];
            s.step(&d, &w, &[], None, 0);
            let a = s.step(&d, &w, &["roll"], None, 50);
            a.first().and_then(|x| if let Act::Log(m) = x { m.strip_prefix("见切：").map(String::from) } else { None })
        };
        assert_eq!(hit(vec![]), None, "只有 43000（没有出招数据）");
        assert_eq!(hit(vec![(3010, 0.5)]), Some("近战（NPC 0 动作 3010（叠着播的） 第 0.50 秒（判定 0.40–0.60） 距离 3.0 体型 0.5 夹角 0°）".into()));
        assert_eq!(hit(vec![(3010, 0.9)]), None, "叠着的出招判定已经过了");
    }

    /// 见切成立时放防御反击的音效（用户 2026-11-12）：只在戴着听见切的词条时
    #[test]
    fn mikiri_plays_guard_counter_sound() {
        let d = parse(DODGE);
        let sound = |w: HashMap<String, usize>| {
            let mut s = Sim::new();
            let mut a = foe(1, 3.0, vec![], false);
            a.anim = Some(3010);
            s.foes = vec![a];
            s.step(&d, &w, &[], None, 0);
            let acts = s.step(&d, &w, &["roll"], None, 100);
            (acts.iter().any(|x| matches!(x, Act::Log(m) if m.starts_with("见切："))), s.e.mikiri_sound)
        };
        assert_eq!(sound(worn(&[("dr_mikiri", 3)])), (true, true));
        assert_eq!(sound(worn(&[("dr_zanshin", 0)])), (true, true), "残心也听见切");
        assert_eq!(sound(worn(&[("dr_shadow", 3)])), (true, false), "判出来了，但没戴听见切的词条，不放");
    }

    #[test]
    fn mikiri_cooldown_after_slow_ends() {
        let d = parse("mark\troll\t907\naff\tdr_mikiri\t500,501,502,503\nrule\tdr_mikiri\ton\tevent=mikiri\tfoe_slow=30,40,50,60\tfoe_radius=8\tfoe_secs=2\trest=5\n");
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_mikiri", 3)]);
        let mut s = Sim::new();
        let mut a = foe(1, 3.0, vec![], false);
        a.anim = Some(3010);
        s.foes = vec![a];
        let roll = |s: &mut Sim, t: u64, anim: i32| {
            s.foes[0].anim = Some(anim);
            s.step(&d, &w, &[], None, t);
            let x = s.step(&d, &w, &["roll"], None, t + 50);
            let y = s.step(&d, &w, &[], None, t + 100);
            (x, y)
        };
        let is = |acts: &[Act], head: &str| acts.iter().any(|a| matches!(a, Act::Log(m) if m.starts_with(head)));
        let (x, _) = roll(&mut s, 0, 3010);
        assert!(matches!(&x[1], Act::Log(m) if m.ends_with("（2 秒）；冷却到 7 秒后")), "{x:?}");
        // 减速 2 秒 + 冷却 5 秒：这段时间里再滚不算，写「冷却中」
        let (x, y) = roll(&mut s, 3000, 3020);
        assert!(!is(&x, "见切：") && is(&y, "见切没成立（冷却中"), "{x:?} {y:?}");
        let (x, _) = roll(&mut s, 7200, 3030);
        assert!(is(&x, "见切："), "{x:?}");
    }

    const FOE: &str = "mark\tland\t906\n\
        bursttier\thp\t50\t970\nbursttier\thp\t200\t971\nbursttier\thp\t800\t972\n\
        buildup\tpoison\t80\t980\nbuildup\tpoison\t150\t981\nbuildup\tbleed\t80\t982\n\
        aff\tdr_res\t300,301,302,303\nrule\tdr_res\tfoe_aura\trange=30\tfx0=310,311,312,313\tfx1=\tfx2=\tfx3=\n\
        aff\tdr_shatter\t320,320,320,320\nrule\tdr_shatter\tfoe_react\twhen=bleed\tneed=frost\tpct=60\tremove=1\tlog=碎冰\n\
        aff\tdr_chain\t-1,-1,-1,330\nrule\tdr_chain\tfoe_spread\trange=6\tamount=80\tkinds=poison,bleed\tlog=连锁\n\
        aff\tdr_awake\t340,340,340,340\nrule\tdr_awake\ton\tevent=land\ttarget_has=sleep\ttarget_remove=1\ttarget_buildup=150\tbuildup_kinds=poison\n\
        aff\tdr_plague\t350,350,350,350\nrule\tdr_plague\ton\tevent=land\ttarget_has=poison,rot\ttarget_remove=1\ttarget_settle=100\n";

    fn ail(kind: &'static str, sp: i32, left: f32, every: f32, rate: f32, point: i32) -> Ail {
        Ail { kind, sp, left, every, rate, point }
    }

    fn foe(id: usize, x: f32, sts: Vec<Ail>, landed: bool) -> Foe {
        // 默认：出招进度一半、体型 0.5、面朝原点（玩家）
        Foe { id, dist: x.abs(), pos: [x, 0.0, 0.0], max_hp: 1000, team: 6, hostile: true, anim: None, landed, via: None, shadow: 0, sts, npc: 0, radius: 0.5,
              progress: 0.5, fwd: [-x.signum(), 0.0], poise: 50.0, poise_max: 50.0, broke: false, boss: false, slept: None, model: 0, play: -1.0,
              layers: Vec::new() }
    }

    /// 被命中标记顶掉的命中时触发：身上有才补；近战全补，箭只补不分手的；不是敌人、这一下不是 land 生效的不补；日志有上限
    #[test]
    fn shadowed_hit_effects() {
        let d = parse("atkfwd\t3140\t900\t1\natkfwd\t1938\t901\t0\natkfwd\tx\t1\t0\n");
        assert_eq!(d.atkfwd, vec![(3140, 900, 1), (1938, 901, 0)], "写坏的行跳过");
        let w = worn(&[]);
        let applied = |a: &[Act]| a.iter().filter_map(|x| if let Act::FoeApply(_, sp) = x { Some(*sp) } else { None }).collect::<Vec<_>>();
        let mut s = Sim::new();
        s.foes = vec![foe(7, 3.0, vec![], true)];
        s.foes[0].shadow = SHADOW_MELEE;
        assert!(s.step(&d, &w, &[], None, 0).is_empty(), "身上没有油脂");
        s.have.insert(3140);
        assert_eq!(applied(&s.step(&d, &w, &[], None, 10)), vec![900]);
        s.have.insert(1938);
        assert_eq!(applied(&s.step(&d, &w, &[], None, 20)), vec![900, 901], "近战全补");
        s.foes[0].shadow = SHADOW_SHOT;
        assert_eq!(applied(&s.step(&d, &w, &[], None, 30)), vec![901], "箭只补不分手的");
        s.foes[0].shadow = 0;
        assert!(applied(&s.step(&d, &w, &[], None, 40)).is_empty(), "这一下不是 land 生效的（游戏自己挂了）");
        s.foes[0].shadow = SHADOW_MELEE;
        s.foes[0].hostile = false;
        assert!(applied(&s.step(&d, &w, &[], None, 50)).is_empty(), "不是敌人");
        s.foes[0].hostile = true;
        s.e.atkfwd_told = ATKFWD_LOG;
        let a = s.step(&d, &w, &[], None, 60);
        assert_eq!(applied(&a), vec![900, 901]);
        assert!(!a.iter().any(|x| matches!(x, Act::Log(_))), "日志写够了就不写，照样补");
    }

    #[test]
    fn foes_resonance_shatter_and_chain() {
        let d = parse(FOE);
        assert!(d.skipped.is_empty() && d.foe_rules, "{:?}", d.skipped);
        let poison = ail("poison", 106000, 10.0, 1.0, 0.07, 7);
        let frost = ail("frost", 107500, 30.0, 99.0, 10.0, 30);
        let bleed = ail("bleed", 6401, 1.0, 2.0, 15.0, 100);
        // 狂乱共鸣：几种异常挂第几个；每 0.5 秒一次
        let mut s = Sim::new();
        let w = worn(&[("dr_res", 0)]);
        s.foes = vec![foe(1, 3.0, vec![poison.clone(), frost.clone()], false), foe(2, 4.0, vec![], false), foe(3, 5.0, vec![bleed.clone()], false)];
        assert_eq!(s.step(&d, &w, &[], None, 0), vec![Act::FoeApply(1, 311), Act::FoeApply(3, 310)]);
        assert!(s.step(&d, &w, &[], None, 100).is_empty());
        s.foes[0].hostile = false;
        assert_eq!(s.step(&d, &w, &[], None, 600), vec![Act::FoeApply(3, 310)], "不是敌人的不算");
        // 碎冰：冻伤中新发作出血，追加出血一跳（15%×1000+100）的 60% = 150，摘掉冻伤
        let mut s = Sim::new();
        let w = worn(&[("dr_shatter", 0)]);
        s.foes = vec![foe(1, 3.0, vec![frost.clone()], false)];
        assert!(s.step(&d, &w, &[], None, 0).is_empty());
        s.foes[0].sts.push(bleed.clone());
        assert_eq!(s.step(&d, &w, &[], None, 100),
                   vec![Act::FoeApply(1, 971), Act::Log("碎冰：frost 上发作 bleed，追加 150（用 200 那档）".into()), Act::FoeRemove(1, 107500)]);
        assert!(s.step(&d, &w, &[], None, 200).is_empty(), "不是新发作的不算");
        // 连锁：新发作中毒，传给 6 米内的其他敌人
        let mut s = Sim::new();
        let w = worn(&[("dr_chain", 3)]);
        s.foes = vec![foe(1, 0.0, vec![], false), foe(2, 3.0, vec![], false), foe(3, 10.0, vec![], false)];
        s.step(&d, &w, &[], None, 0);
        s.foes[0].sts.push(poison.clone());
        assert_eq!(s.step(&d, &w, &[], None, 100), vec![Act::Log("连锁：poison 传给 1 个".into()), Act::FoeApply(2, 980)]);
        assert!(s.step(&d, &w, &[], None, 200).is_empty());
    }

    /// 积蓄（take_fresh）：翻滚加一层；翻滚中的命中、翻滚前就开始的动作晚到的命中都不算（层数留着），翻滚后新出的招打中才附加
    #[test]
    fn charge_needs_a_fresh_attack() {
        let d = parse(concat!(
            "mark\troll\t901\nbuildup\tpoison\t200\t983\n",
            "aff\tdr_charge\t350,350,350,350\n",
            "rule\tdr_charge\tstack\tadd=jump,crouch,roll\tmax=1\ttimeout=3\n",
            "rule\tdr_charge\ton\tevent=land\ttake=dr_charge\ttake_fresh=1\ttarget_buildup=200\tbuildup_kinds=poison\n",
        ));
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_charge", 3)]);
        let mut s = Sim::new();
        s.foes = vec![foe(1, 1.0, vec![], false)];
        // 攻击动作 100 里翻滚（翻滚动作 200）：加一层
        s.step(&d, &w, &[], Some(100), 0);
        s.step(&d, &w, &["roll"], Some(200), 100);
        // 翻滚中命中：不算，层数留着
        s.foes[0].landed = true;
        let a = s.step(&d, &w, &["roll", "land"], Some(200), 200);
        assert!(!a.iter().any(|x| matches!(x, Act::FoeApply(..))), "翻滚中的命中不该附加：{a:?}");
        s.foes[0].landed = false;
        s.step(&d, &w, &[], Some(200), 300);
        // 翻滚刚结束、还在翻滚的动作里（之前的命中晚到）：也不算
        s.foes[0].landed = true;
        let a = s.step(&d, &w, &["land"], Some(200), 400);
        assert!(!a.iter().any(|x| matches!(x, Act::FoeApply(..))), "加层之前开始的动作里的命中不该附加：{a:?}");
        s.foes[0].landed = false;
        // 翻滚攻击（新动作 300）打中：附加，层数用掉
        s.step(&d, &w, &[], Some(300), 500);
        s.foes[0].landed = true;
        assert_eq!(s.step(&d, &w, &["land"], Some(300), 600), vec![Act::FoeApply(1, 983), Act::Log("dr_charge：附加 poison 累积 200".into())]);
        s.foes[0].landed = false;
        s.step(&d, &w, &[], Some(300), 700);
        s.foes[0].landed = true;
        assert!(!s.step(&d, &w, &["land"], Some(300), 800).iter().any(|x| matches!(x, Act::FoeApply(..))), "层数已经用掉");
    }

    #[test]
    fn foes_hit_by_the_player() {
        let d = parse(FOE);
        // 惊醒：打中之前就在睡的敌人（Foe::slept；游戏先摘了睡眠、sts 里没有也算），摘掉睡眠、附加中毒累积 150
        let mut s = Sim::new();
        let w = worn(&[("dr_awake", 0)]);
        let sleep = ail("sleep", 6454, 60.0, 65.0, 0.0, 0);
        s.foes = vec![Foe { slept: Some(sleep.clone()), ..foe(1, 2.0, vec![], true) }, foe(2, 3.0, vec![], true)];
        assert_eq!(s.step(&d, &w, &["land"], None, 0),
                   vec![Act::FoeRemove(1, 6454), Act::FoeApply(1, 981), Act::Log("dr_awake：附加 poison 累积 150".into())]);
        // 打睡着的那一下：睡眠刚挂上（在 sts 里），打中之前没睡（slept 空）→ 不算
        s.foes = vec![foe(3, 2.0, vec![sleep.clone()], true)];
        assert!(s.step(&d, &w, &["land"], None, 50).is_empty(), "打睡着的那一下不算");
        s.foes = vec![foe(2, 3.0, vec![], false)];
        s.step(&d, &w, &[], None, 100);
        s.foes[0].landed = true;
        assert!(s.step(&d, &w, &["land"], None, 200).is_empty(), "没睡着的不管");
        // 瘟疫爆发：中毒还剩 10 跳 ×（0.07%×1000 + 7）= 77，一次结算
        let mut s = Sim::new();
        let w = worn(&[("dr_plague", 0)]);
        s.foes = vec![foe(1, 2.0, vec![ail("poison", 106000, 10.0, 1.0, 0.07, 7)], true)];
        assert_eq!(s.step(&d, &w, &["land"], None, 0),
                   vec![Act::FoeApply(1, 970), Act::Log("dr_plague：poison 剩下 77（用 50 那档）".into()), Act::FoeRemove(1, 106000)]);
    }

    /// 睡眠按「打中之前在睡」（track_sleep）：打睡着的那一下不交出去；睡着后再打，游戏在命中同一帧先摘了睡眠也交出去
    #[test]
    fn sleep_before_the_hit() {
        let mut eng = Engine::default();
        let t0 = Instant::now();
        let ms = |n: u64| t0 + Duration::from_millis(n);
        let sleep = ail("sleep", 6451, 60.0, 65.0, 0.0, 0);
        let who = |w: &str| w.to_string();
        // 第 1 下：命中标记和睡眠同一帧出现（打睡着的那一下），等 60 毫秒算打中 → 不交
        assert_eq!(track_sleep(&mut eng, 1, &[sleep.clone()], true, false, true, ms(0), who, false), None);
        assert_eq!(track_sleep(&mut eng, 1, &[sleep.clone()], false, true, true, ms(60), who, false), None);
        // 睡着（每帧扫到）
        assert_eq!(track_sleep(&mut eng, 1, &[sleep.clone()], false, false, false, ms(76), who, false), None);
        assert_eq!(track_sleep(&mut eng, 1, &[sleep.clone()], false, false, false, ms(92), who, false), None);
        // 第 2 下：命中标记出现的同一帧睡眠已经没了 → 记下「之前在睡」，算打中时交出去
        assert_eq!(track_sleep(&mut eng, 1, &[], true, false, true, ms(108), who, false), None);
        assert_eq!(track_sleep(&mut eng, 1, &[], false, true, true, ms(168), who, false), Some(sleep.clone()));
        // 第 3 下：醒着 → 不交
        assert_eq!(track_sleep(&mut eng, 1, &[], true, false, true, ms(400), who, false), None);
        assert_eq!(track_sleep(&mut eng, 1, &[], false, true, true, ms(460), who, false), None);
        // 箭打中睡着的（子弹标记出现的同一帧就算打中）
        let mut eng = Engine::default();
        track_sleep(&mut eng, 2, &[sleep.clone()], false, false, false, ms(0), who, false);
        assert_eq!(track_sleep(&mut eng, 2, &[sleep.clone()], true, true, true, ms(16), who, false), Some(sleep.clone()));
    }

    const HUNT: &str = "mark\tland\t906\nmark\tshot_hit\t907\nmark\titem_hit\t908\nmark\tshot\t909\nmark\tbreak\t910\n\
        bursttier\thp\t30\t960\nbursttier\thp\t60\t961\nbursttier\thp\t100\t962\nbursttier\thp\t300\t963\n\
        aff\tdr_hunt\t1,1,1,1\nrule\tdr_hunt\ton\tevent=land\tcond=shot_hit\ttarget_mark=hunt\tmark_max=3\tmark_secs=10\tmfx3=71,72,73\n\
        aff\tdr_detonate\t2,2,2,2\nrule\tdr_detonate\ton\tevent=land\tcond=item_hit\ttarget_take=hunt\ttake_pct=3\ttake_grow=2\n\
        aff\tdr_close\t3,3,3,3\nrule\tdr_close\ton\tevent=land\tunless=shot_hit,item_hit\ttarget_take=hunt\ttake_pct=10\n\
        aff\tdr_opening\t4,4,4,4\nrule\tdr_opening\ton\tevent=break\ttarget_on=break\ttarget_fx=80\n\
        aff\tdr_salvage\t5,5,5,5\nrule\tdr_salvage\ton\tevent=shot_hit\tchance=100\trefund=10\n\
        aff\tdr_inf\t6,6,6,6\nrule\tdr_inf\tfree\tfp=8\n\
        aff\tdr_inf0\t9,9,9,9\nrule\tdr_inf0\tfree\tfp=0\n\
        aff\tdr_volley\t7,7,7,7\nrule\tdr_volley\tstack\tadd=shot_hit\tmax=5\ttimeout=3\treload_speed=10\n\
        aff\tdr_coin\t8,8,8,8\nrule\tdr_coin\ton\tevent=shot\tchance=30\tfp=1\n";

    /// 近身：法术、调香的命中有自己的标记，不算近战（法术飞到时早就收招了，以前 cast 排除不掉）
    #[test]
    fn close_ignores_spell_hits() {
        let def = format!("mark\tcast_hit\t911\n{}", HUNT.replace("unless=shot_hit,item_hit", "unless=shot_hit,item_hit,cast_hit"));
        let d = parse(&def);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_hunt", 3), ("dr_close", 3)]);
        let mut s = Sim::new();
        s.ar = 5000.0;
        let hit = |s: &mut Sim, ev: &[&str], t: u64| {
            s.foes = vec![foe(1, 2.0, vec![], true)];
            s.foes[0].via = FOE_HIT_KINDS.iter().find(|k| ev.contains(k)).copied();
            let a = s.step(&d, &w, ev, None, t);
            s.foes[0].landed = false;
            s.step(&d, &w, &[], None, t + 50);
            a
        };
        hit(&mut s, &["land", "shot_hit"], 0);
        let a = hit(&mut s, &["land", "cast_hit"], 200);
        assert!(!a.iter().any(|x| matches!(x, Act::FoeRemove(..))), "法术命中不该清猎印：{a:?}");
        let a = hit(&mut s, &["land"], 400);
        assert!(a.iter().any(|x| matches!(x, Act::FoeRemove(..))), "近战命中才清：{a:?}");
    }

    const BURN: &str = "mark\tattack\t901\nmark\tskill\t902\nmark\tland\t906\n\
        bursttier\thpmax\t10\t951\nbursttier\thpmax\t20\t952\nbursttier\thpmax\t30\t953\n\
        aff\tdr_burn\t-1,-1,-1,11\nrule\tdr_burn\twhile\tcond=attack\tstamina_to_hp=20\nrule\tdr_burn\twhile\tcond=swing\tunless=roll\tstamina_to_hp=20\nrule\tdr_burn\twhile\tcond=skill\tstamina_to_hp=20\n\
        aff\tdr_glow\t12,12,12,12\nrule\tdr_glow\ton\tevent=land\thp_below=10\thp_pct=2,3,4,5\n\
        aff\tdr_urn\t13,13,13,13\nrule\tdr_urn\twhile\thp_flat=60,120,180,250\n";

    #[test]
    fn bloodburn_pays_attacks_with_hp_once_per_frame() {
        let d = parse(BURN);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_burn", 3)]);
        let mut s = Sim::new();
        s.step(&d, &w, &[], None, 0);
        // 攻击和战技的标记同一帧都在：精力掉了 25（满 100），补回来，扣 25% × 20% × 1000 = 50，只算一次
        s.stamina = 75;
        let a = s.step(&d, &w, &["attack", "skill"], None, 100);
        assert_eq!(a[..2], [Act::Stamina(25), Act::HpCost(50)]);
        assert_eq!((s.stamina, s.hp), (100, 950));
        // 下一帧没再掉，不重复扣
        assert!(s.step(&d, &w, &["attack"], None, 116).iter().all(|x| !matches!(x, Act::HpCost(_))));
        // 不在攻击里（翻滚）掉的精力照常
        s.stamina = 70;
        assert!(s.step(&d, &w, &[], None, 400).iter().all(|x| !matches!(x, Act::HpCost(_) | Act::Stamina(_))));
        assert_eq!(s.stamina, 70);
        // 出招的脉冲灭了、还在普通攻击的状态里（swing）时才扣精力（游戏在攻击判定出来时扣）：照样换成扣血；翻滚中的不算
        for t in [450, 466, 482] {
            s.step(&d, &w, &[], None, t); // 站着不动几帧：前几帧的精力记录都是 70
        }
        s.stamina = 50;
        let a = s.step(&d, &w, &["swing"], None, 500);
        assert_eq!(a[..2], [Act::Stamina(20), Act::HpCost(40)], "普通攻击中掉的精力");
        s.stamina = 40;
        assert!(s.step(&d, &w, &["swing", "roll"], None, 600).iter().all(|x| !matches!(x, Act::HpCost(_) | Act::Stamina(_))), "攻击刚完接翻滚：翻滚的精力照常");
        // 血不够扣到 0
        s.hp = 20;
        s.stamina = 40;
        s.step(&d, &w, &["attack"], None, 800);
        assert_eq!(s.hp, 0);
    }

    #[test]
    fn last_light_heals_only_below_ten_percent_and_urn_picks_a_tier() {
        let d = parse(BURN);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_glow", 3), ("dr_urn", 1)]);
        let mut s = Sim::new();
        let hit = |s: &mut Sim, t: u64| {
            s.foes = vec![foe(1, 2.0, vec![], true)];
            let a = s.step(&d, &w, &["land"], None, t);
            s.foes[0].landed = false;
            s.step(&d, &w, &[], None, t + 50);
            a
        };
        // 血瓮稀有：120 点 ÷ 基础血量 800 = 15%，10% 和 20% 一样近，挑先列的 10%；一直挂着
        s.step(&d, &w, &[], None, 0);
        assert!(s.have.contains(&951) && !s.have.contains(&952));
        // 血量 20%：命中不回
        s.hp = 200;
        assert!(hit(&mut s, 200).iter().all(|x| !matches!(x, Act::Hp(_))));
        // 血量 9%：每下回最大血量 5% = 50
        s.hp = 90;
        assert!(hit(&mut s, 400).contains(&Act::Hp(50)));
        s.hp = 60;
        assert!(hit(&mut s, 600).contains(&Act::Hp(50)));
        // 回到 10% 以上（110）就停
        assert_eq!(s.hp, 110);
        assert!(hit(&mut s, 800).iter().all(|x| !matches!(x, Act::Hp(_))));
    }

    /// 引爆 / 近身消耗猎印时挂碎裂特效：消耗了几层用第几个，超过就用最后一个（tfx0~3 = 各稀有度）
    #[test]
    fn take_fx_picks_burst_by_layers() {
        let def = HUNT.replace("take_grow=2\n", "take_grow=2\ttfx3=81,82,83\n").replace("take_pct=10\n", "take_pct=10\ttfx3=85\n");
        let d = parse(&def);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_hunt", 3), ("dr_detonate", 3), ("dr_close", 3)]);
        let mut s = Sim::new();
        s.ar = 1000.0;
        let hit = |s: &mut Sim, ev: &[&str], t: u64| {
            s.foes = vec![foe(1, 2.0, vec![], true)];
            s.foes[0].via = FOE_HIT_KINDS.iter().find(|k| ev.contains(k)).copied();
            let a = s.step(&d, &w, ev, None, t);
            s.foes[0].landed = false;
            s.step(&d, &w, &[], None, t + 50);
            a
        };
        hit(&mut s, &["land", "shot_hit"], 0);
        hit(&mut s, &["land", "shot_hit"], 200);
        assert_eq!(hit(&mut s, &["land", "item_hit"], 400),
                   vec![Act::FoeRemove(1, 72), Act::FoeApply(1, 82), Act::FoeApply(1, 961), Act::Log("dr_detonate：hunt 2 层 → 60（用 60 那档）".into())]);
        // 近身只写了一个：几层都用它；没有猎印时不挂
        assert!(hit(&mut s, &["land"], 600).is_empty());
        for t in [800, 1000, 1200] {
            hit(&mut s, &["land", "shot_hit"], t);
        }
        let a = hit(&mut s, &["land"], 1400);
        assert_eq!(a[..2], [Act::FoeRemove(1, 73), Act::FoeApply(1, 85)]);
    }

    #[test]
    fn detonate_grow_is_per_extra_mark() {
        let d = parse(&HUNT.replace("take_grow=2", "take_grow=1.3"));
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_hunt", 3), ("dr_detonate", 3)]);
        let mut s = Sim::new();
        s.ar = 1000.0;
        let hit = |s: &mut Sim, ev: &[&str], t: u64| {
            s.foes = vec![foe(1, 2.0, vec![], true)];
            s.foes[0].via = FOE_HIT_KINDS.iter().find(|k| ev.contains(k)).copied();
            let a = s.step(&d, &w, ev, None, t);
            s.foes[0].landed = false;
            s.step(&d, &w, &[], None, t + 50);
            a
        };
        for t in [0, 200, 400] {
            hit(&mut s, &["land", "shot_hit"], t);
        }
        // 面板 1000 × 3% = 30，3 层 × 1.3 × 1.3 = 50.7，用 60 那档
        assert_eq!(hit(&mut s, &["land", "item_hit"], 600),
                   vec![Act::FoeRemove(1, 73), Act::FoeApply(1, 961), Act::Log("dr_detonate：hunt 3 层 → 51（用 60 那档）".into())]);
    }

    #[test]
    fn detonate_grows_per_mark_and_splits_past_the_top_tier() {
        let d = parse(HUNT);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_hunt", 3), ("dr_detonate", 3)]);
        let mut s = Sim::new();
        s.ar = 5000.0;
        let hit = |s: &mut Sim, ev: &[&str], t: u64| {
            s.foes = vec![foe(1, 2.0, vec![], true)];
            s.foes[0].via = FOE_HIT_KINDS.iter().find(|k| ev.contains(k)).copied();
            let a = s.step(&d, &w, ev, None, t);
            s.foes[0].landed = false;
            s.step(&d, &w, &[], None, t + 50);
            a
        };
        for t in [0, 200, 400] {
            hit(&mut s, &["land", "shot_hit"], t);
        }
        // 面板 5000 × 3% = 150，3 层翻两次 = 600，超过最高档 300：往下一档档加
        assert_eq!(hit(&mut s, &["land", "item_hit"], 600),
                   vec![Act::FoeRemove(1, 73), Act::FoeApply(1, 963), Act::FoeApply(1, 962), Act::FoeApply(1, 961), Act::FoeApply(1, 960),
                        Act::Log("dr_detonate：hunt 3 层 → 600（用 300+100+60+30 那档）".into())]);
        // 够了就停：390 = 300 + 100（差不到一成）；不超过最高档就一档
        assert_eq!(d.tiers_sum("hp", 390.0).iter().map(|x| x.1).collect::<Vec<_>>(), vec![963, 962]);
        assert_eq!(d.tiers_sum("hp", 110.0).iter().map(|x| x.1).collect::<Vec<_>>(), vec![962]);
    }

    #[test]
    fn hunt_marks_detonate_and_close() {
        let d = parse(HUNT);
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_hunt", 3), ("dr_detonate", 3), ("dr_close", 3)]);
        let mut s = Sim::new();
        s.ar = 1000.0;
        // 被箭 / 道具打中的敌人带上 via（tick 从敌人身上的子弹标记认）
        let hit = |s: &mut Sim, ev: &[&str], t: u64| {
            s.foes = vec![foe(1, 2.0, vec![], true)];
            s.foes[0].via = FOE_HIT_KINDS.iter().find(|k| ev.contains(k)).copied();
            let a = s.step(&d, &w, ev, None, t);
            s.foes[0].landed = false;
            s.step(&d, &w, &[], None, t + 50);
            a
        };
        // 箭打中：叠猎印，换成这一层的效果（近身有 unless=shot_hit 不做）
        assert_eq!(hit(&mut s, &["land", "shot_hit"], 0), vec![Act::FoeApply(1, 71)]);
        assert_eq!(hit(&mut s, &["land", "shot_hit"], 200), vec![Act::FoeRemove(1, 71), Act::FoeApply(1, 72)]);
        // 投掷道具打中：引爆按武器面板，1000 × 3% = 30，2 层翻倍 = 60
        assert_eq!(hit(&mut s, &["land", "item_hit"], 400),
                   vec![Act::FoeRemove(1, 72), Act::FoeApply(1, 961), Act::Log("dr_detonate：hunt 2 层 → 60（用 60 那档）".into())]);
        // 属性倍率（procs）不再乘：1 层还是 30
        s.scale = [5.0, 1.0, 1.0, 1.0, 1.0];
        hit(&mut s, &["land", "shot_hit"], 450);
        assert_eq!(hit(&mut s, &["land", "item_hit"], 500),
                   vec![Act::FoeRemove(1, 71), Act::FoeApply(1, 960), Act::Log("dr_detonate：hunt 1 层 → 30（用 30 那档）".into())]);
        s.scale = [1.0; 5];
        // 没有猎印时近战打中：什么都不做；有一层时：右手攻击力 1000 × 10% = 100
        assert!(hit(&mut s, &["land"], 600).is_empty());
        hit(&mut s, &["land", "shot_hit"], 800);
        assert_eq!(hit(&mut s, &["land"], 1000),
                   vec![Act::FoeRemove(1, 71), Act::FoeApply(1, 962), Act::Log("dr_close：hunt 1 层 → 100（用 100 那档）".into())]);
        // 最多 3 层；10 秒没再叠就摘掉
        for t in [1200, 1400, 1600, 1800] {
            hit(&mut s, &["land", "shot_hit"], t);
        }
        assert_eq!(s.e.foe_marks.get(&(1, "hunt".to_string())).map(|x| x.0), Some(3));
        assert_eq!(s.step(&d, &w, &[], None, 12_000), vec![Act::FoeRemove(1, 73)]);
        // 同一帧箭打中 1、近战打中 2：只有 1 叠猎印；2 没有猎印，近身什么都不做
        let two = |s: &mut Sim, shot: usize, t: u64| {
            s.foes = vec![foe(1, 2.0, vec![], true), foe(2, 3.0, vec![], true)];
            s.foes[shot - 1].via = Some("shot_hit");
            let a = s.step(&d, &w, &["land", "shot_hit"], None, t);
            s.foes.iter_mut().for_each(|f| f.landed = false);
            s.step(&d, &w, &[], None, t + 50);
            a
        };
        assert_eq!(two(&mut s, 1, 13_000), vec![Act::FoeApply(1, 71)]);
        // 反过来：箭打中 2（叠一层），近战打中 1（近身收掉 1 身上那层）
        assert_eq!(two(&mut s, 2, 13_200),
                   vec![Act::FoeApply(2, 71), Act::FoeRemove(1, 71), Act::FoeApply(1, 962), Act::Log("dr_close：hunt 1 层 → 100（用 100 那档）".into())]);
    }

    #[test]
    fn thousandweight_breaks_on_hit() {
        let d = parse(
            "mark\tcharged\t911\n\
             aff\tdr_thousand\t-1,-1,-1,90\nrule\tdr_thousand\twhile\tcond=charged\tpoise_radius=6\tpoise_boss_pct=30\tpoise_fx=-1,-1,-1,95\n\
             rule\tdr_thousand\twhile\tunless=charged\teffect=-1,-1,-1,91\n",
        );
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_thousand", 3)]);
        let mut s = Sim::new();
        // 身边：普通敌人、Boss A（上限 200，现在 150）、Boss B（上限 200，现在 50，不到 30%）；远处的不管
        let mut a = foe(2, 3.0, vec![], false);
        (a.boss, a.poise, a.poise_max) = (true, 150.0, 200.0);
        let mut b = foe(4, 4.0, vec![], false);
        (b.boss, b.poise, b.poise_max) = (true, 50.0, 200.0);
        s.foes = vec![foe(1, 2.0, vec![], false), a, foe(3, 20.0, vec![], false), b];
        let pre = |from: f32, to: f32| Act::Log(format!("dr_thousand：满蓄力，Boss（NPC 0）架势先扣 {from:.0} → {to:.0}（上限 200），没打中就加回去"));
        // 平时：削韧 ×0 的效果挂着
        assert_eq!(s.step(&d, &w, &[], None, 0), vec![Act::Apply(91)]);
        // 满蓄力出手：普通敌人挂上削韧 ×1000（打中就崩）；两个 Boss 先扣上限的 30%（150 → 90，50 → 1）；削韧 ×0 摘掉
        assert_eq!(s.step(&d, &w, &["charged"], None, 100),
                   vec![Act::FoeApply(1, 95), Act::FoePoise(2, 90.0), pre(150.0, 90.0), Act::FoePoise(4, 1.0), pre(50.0, 1.0),
                        Act::Log("dr_thousand：满蓄力，身边 1 个敌人这一击打中就崩架势".into()), Act::Remove(91)]);
        s.foes[1].poise = 90.0;
        s.foes[3].poise = 1.0;
        // Boss A 被这一击打中（90 → 70）：不再扣，按 70 保持
        s.foes[1].landed = true;
        s.foes[1].poise = 70.0;
        assert!(s.step(&d, &w, &["charged"], None, 200).is_empty(), "同一击不重复扣；被打得更低按更低的保持");
        s.foes[1].landed = false;
        // 满蓄力标记消失：POISE_GRACE 内还算这一击，之后摘掉削韧 ×1000，没打中的 Boss B 加回去（1 + 49 = 50）
        assert_eq!(s.step(&d, &w, &[], None, 400), vec![Act::Apply(91)]);
        assert_eq!(s.step(&d, &w, &[], None, 900),
                   vec![Act::FoeRemove(1, 95), Act::FoePoise(4, 50.0), Act::Log("dr_thousand：没打中 Boss（NPC 0），架势加回 1 → 50".into())]);
        s.foes[3].poise = 50.0;
        // 游戏自己回架势：打中的 Boss A 压回去，加回去的 Boss B 不管
        s.foes[1].poise = 200.0;
        s.foes[3].poise = 80.0;
        assert_eq!(s.step(&d, &w, &[], None, 1000), vec![Act::FoePoise(2, 70.0)]);
        s.foes[1].poise = 70.0;
        s.foes[3].poise = 50.0;
        // 普通攻击打中 Boss A：不扣
        s.foes[1].landed = true;
        assert!(s.step(&d, &w, &[], None, 1100).is_empty());
        s.foes[1].landed = false;
        // 下一次满蓄力：再各扣 30%（70 → 10，50 → 1）
        assert_eq!(s.step(&d, &w, &["charged"], None, 2000),
                   vec![Act::FoeApply(1, 95), Act::FoePoise(2, 70.0 - 200.0 * 0.3f32), pre(70.0, 10.0), Act::FoePoise(4, 1.0), pre(50.0, 1.0),
                        Act::Log("dr_thousand：满蓄力，身边 1 个敌人这一击打中就崩架势".into()), Act::Remove(91)]);
        s.foes[3].poise = 1.0;
        // Boss A 被打崩（游戏重置回满）：交还给游戏，不加回去也不再压
        (s.foes[1].landed, s.foes[1].broke, s.foes[1].poise) = (true, true, 200.0);
        assert!(s.step(&d, &w, &["charged"], None, 2100).is_empty());
        (s.foes[1].landed, s.foes[1].broke) = (false, false);
        // 这一击结束：Boss B 没打中，加回去
        assert_eq!(s.step(&d, &w, &[], None, 40_000),
                   vec![Act::FoeRemove(1, 95), Act::FoePoise(4, 50.0), Act::Log("dr_thousand：没打中 Boss（NPC 0），架势加回 1 → 50".into()),
                        Act::Apply(91)]);
    }

    /// 发狂发作扣架势：只在发狂刚出现的那一帧扣上限的 30%，最低 1；别的异常、友方、还挂着的不扣
    #[test]
    fn madness_proc_cuts_poise() {
        let d = parse("madpoise\t30\n");
        assert!(d.skipped.is_empty() && d.foe_rules && (d.mad_poise - 0.3).abs() < 1e-6, "{:?}", d.skipped);
        let mad = ail("madness", 6750, 1.0, 2.0, 5.0, 0);
        let bleed = ail("bleed", 6401, 1.0, 2.0, 15.0, 100);
        let w = worn(&[]);
        let mut s = Sim::new();
        let mut boss = foe(2, 3.0, vec![mad.clone()], false);
        (boss.boss, boss.poise, boss.poise_max, boss.npc) = (true, 150.0, 200.0, 7);
        let mut low = foe(3, 4.0, vec![mad.clone()], false);
        low.poise = 10.0;
        let mut ally = foe(4, 5.0, vec![mad.clone()], false);
        ally.hostile = false;
        s.foes = vec![foe(1, 2.0, vec![bleed.clone()], false), boss, low, ally];
        assert_eq!(s.step(&d, &w, &[], None, 0), vec![
            Act::FoePoise(2, 90.0), Act::Log("发狂发作：敌人（参数 7）架势 150 → 90（上限 200）".into()),
            Act::FoePoise(3, 1.0), Act::Log("发狂发作：敌人（参数 0）架势 10 → 1（上限 50）".into()),
        ]);
        s.foes[1].poise = 90.0;
        assert!(s.step(&d, &w, &[], None, 100).is_empty(), "还挂着不再扣");
        s.foes[1].sts.clear();
        assert!(s.step(&d, &w, &[], None, 200).is_empty());
        s.foes[1].sts.push(mad.clone());
        match s.step(&d, &w, &[], None, 300)[0] {
            Act::FoePoise(2, v) => assert!((v - 30.0).abs() < 0.01, "再次发作再扣：{v}"),
            ref a => panic!("再次发作再扣：{a:?}"),
        }
        assert!(Sim::new().step(&parse(""), &w, &[], None, 0).is_empty(), "没有 madpoise 行不扣");
        // 发作特效：先挂特效再扣架势；只有 madvfx 也挂
        let dv = parse("madpoise\t30\nmadvfx\t7299110\n");
        let mut s = Sim::new();
        s.foes = vec![foe(2, 3.0, vec![mad.clone()], false)];
        assert_eq!(s.step(&dv, &w, &[], None, 0)[..2], [Act::FoeApply(2, 7299110), Act::FoePoise(2, 35.0)]);
        let dv = parse("madvfx\t7299110\n");
        assert!(dv.foe_rules);
        let mut s = Sim::new();
        s.foes = vec![foe(2, 3.0, vec![mad.clone()], false)];
        assert_eq!(s.step(&dv, &w, &[], None, 0), vec![Act::FoeApply(2, 7299110)]);
    }

    #[test]
    fn break_target_refund_volley_and_chance() {
        let d = parse(HUNT);
        // 崩架势：只给被打崩的敌人挂
        let w = worn(&[("dr_opening", 0)]);
        let mut s = Sim::new();
        let mut f = foe(1, 2.0, vec![], false);
        f.broke = true;
        s.foes = vec![f, foe(2, 3.0, vec![], true)];
        assert_eq!(s.step(&d, &w, &["break"], None, 0), vec![Act::FoeApply(1, 80)]);
        // 回收：返还最近用掉、还没返还过的；同一支箭不返两次
        let w = worn(&[("dr_salvage", 3)]);
        let mut s = Sim::new();
        s.used = vec![(0, 50000)];
        assert!(s.step(&d, &w, &[], None, 0).is_empty());
        assert_eq!(s.step(&d, &w, &["shot_hit"], None, 500), vec![Act::Refund(0, 50000), Act::Log("dr_salvage：返还 50000".into())]);
        s.step(&d, &w, &[], None, 600);
        assert!(s.step(&d, &w, &["shot_hit"], None, 700).is_empty());
        // 无尽箭袋：专注够就箭矢不消耗；新的一次射击扣 8 专注，这一下还在就算付过（专注掉到不够也不消耗）；
        // 道具只在付过的投掷动作里不消耗
        let w = worn(&[("dr_inf", 3)]);
        let mut s = Sim::new();
        s.fp = 10;
        assert!(s.step(&d, &w, &[], None, 0).is_empty());
        assert_eq!(s.e.free, (true, false));
        assert_eq!(s.step(&d, &w, &["shot_new"], None, 50), vec![Act::Fp(-8), Act::Log("dr_inf：射击，扣 8 专注（剩 2）".into())]);
        assert_eq!(s.e.free, (true, false));
        assert!(s.step(&d, &w, &["shot_new", "shot"], None, 100).is_empty(), "同一下不重复扣");
        assert_eq!(s.e.free, (true, false), "付过的这一下还在");
        s.step(&d, &w, &[], None, 150);
        assert_eq!(s.e.free, (false, false), "这一下做完了、专注不够");
        assert_eq!(s.step(&d, &w, &["shot_new"], None, 200), vec![Act::Log("dr_inf：射击，专注 2 不够 8，照常消耗".into())]);
        assert_eq!(s.e.free, (false, false));
        s.fp = 100;
        s.step(&d, &w, &[], None, 250);
        assert_eq!(s.step(&d, &w, &["throw_new"], None, 300).len(), 2);
        assert_eq!(s.e.free, (true, true));
        s.step(&d, &w, &["throw"], None, 400);
        assert_eq!(s.e.free, (true, true));
        s.step(&d, &w, &[], None, 500);
        assert_eq!(s.e.free, (true, false), "投掷做完，道具照常消耗");
        assert!(s.step(&d, &w, &["throw"], None, 600).is_empty(), "没有新的投掷不扣");
        assert_eq!(s.e.free, (true, false));
        assert!(s.step(&d, &worn(&[]), &["throw_new"], None, 700).is_empty());
        assert_eq!(s.e.free, (false, false), "摘下");
        // 不扣专注的（用户 2026-11-04）：专注 0 也一直不消耗，射击 / 投掷不发扣专注、不记日志
        let w = worn(&[("dr_inf0", 3)]);
        let mut s = Sim::new();
        s.fp = 0;
        assert!(s.step(&d, &w, &[], None, 0).is_empty());
        assert_eq!(s.e.free, (true, false));
        assert!(s.step(&d, &w, &["shot_new"], None, 50).is_empty());
        assert!(s.step(&d, &w, &["throw_new"], None, 100).is_empty());
        assert_eq!(s.e.free, (true, true));
        // 连射：每层拉弓快 10%
        let w = worn(&[("dr_volley", 3)]);
        let mut s = Sim::new();
        s.step(&d, &w, &["shot_hit"], None, 0);
        s.step(&d, &w, &[], None, 100);
        s.step(&d, &w, &["shot_hit"], None, 200);
        assert!((s.e.reload_mult - 1.2).abs() < 1e-5);
        s.step(&d, &w, &[], None, 4000);
        assert!((s.e.reload_mult - 1.0).abs() < 1e-5, "3 秒没命中就散");
        // 几率 30%
        let w = worn(&[("dr_coin", 3)]);
        let mut s = Sim::new();
        let mut n = 0;
        for k in 0..2000u64 {
            n += s.step(&d, &w, &["shot"], None, k * 100).len();
            s.step(&d, &w, &[], None, k * 100 + 50);
        }
        assert!((450..750).contains(&n), "{n}");
    }

    #[test]
    fn giant_slayer_by_max_hp() {
        let d = parse(
            "mark\tland\t906\n\
             bursttier\thp\t5\t960\nbursttier\thp\t10\t961\nbursttier\thp\t40\t962\nbursttier\thp\t100\t963\nbursttier\thp\t300\t964\n\
             aff\tdr_giant\t360,360,360,360\nrule\tdr_giant\ton\tevent=land\ttarget_hp_pct=1\ttarget_nth=3\ttarget_nth_pct=3\ttarget_cap=100\ttarget_reset=5\n",
        );
        assert!(d.skipped.is_empty(), "{:?}", d.skipped);
        let w = worn(&[("dr_giant", 3)]);
        let mut s = Sim::new();
        s.ar = 100.0;
        let hit = |s: &mut Sim, max_hp: i32, t: u64| {
            let mut f = foe(1, 2.0, vec![], true);
            f.max_hp = max_hp;
            s.foes = vec![f];
            let a = s.step(&d, &w, &["land"], None, t);
            s.foes[0].landed = false;
            s.step(&d, &w, &[], None, t + 100);
            a
        };
        // 最大血量 1000：每下 1% = 10；同一档 1 秒内刚挂过，第二下换最接近的另一档（5）；第三下 1% + 3% = 40
        assert_eq!(hit(&mut s, 1000, 0), vec![Act::FoeApply(1, 961)]);
        assert_eq!(hit(&mut s, 1000, 500), vec![Act::FoeApply(1, 960)]);
        assert_eq!(hit(&mut s, 1000, 1000), vec![Act::FoeApply(1, 962), Act::Log("dr_giant：第 3 下，最大血量 1000 的 4% = 40（用 40 那档）".into())]);
        // 5 秒没打中它：重新数，第一下又是 1%
        assert_eq!(hit(&mut s, 1000, 7000), vec![Act::FoeApply(1, 961)]);
        // 血量很多（难度放大的 Boss）：1% = 1000，超过右手武器攻击力 100 的上限
        assert_eq!(hit(&mut s, 100_000, 7500), vec![Act::FoeApply(1, 963), Act::Log("dr_giant：最大血量 100000 的 1% = 1000，超过上限 100（用 100 那档）".into())]);
        // 小怪：1% 不到 3 点不扣
        assert!(hit(&mut s, 200, 20_000).is_empty());
        // 难度把玩家造成的伤害打对折：直接扣血也跟着减半（1% = 10 → 5）
        let mut s = Sim::new();
        s.ar = 100.0;
        s.dealt = 0.5;
        assert_eq!(hit(&mut s, 1000, 0), vec![Act::FoeApply(1, 960)]);
    }

    /// 法球（magic / pebble）的固定伤害按智力、信仰里高的（倍率：物理 魔力 火 雷 圣），别的冲击波按物理
    #[test]
    fn orb_scale_int_or_faith() {
        let s = [1.1, 1.3, 1.6, 1.2, 1.6];
        assert_eq!(kind_scale("pebble", &s), 1.6);
        assert_eq!(kind_scale("magic", &s), 1.6);
        assert_eq!(kind_scale("pebble", &[1.1, 1.7, 1.2, 1.0, 1.2]), 1.7);
        assert_eq!(kind_scale("phys", &s), 1.1);
        assert_eq!(kind_scale("", &s), 1.1);
    }

    /// 词条数值随机二期：affixes.txt 的 famrnum（第几条规则的哪个字段）在真的 runtime.txt 里都认得、能改，这一档原来的数 = a + b × 现在的数；
    /// 复制的 Def 共用攻击判定表这些大表。DR_DEFS_DIR 指向重随的输出（没有就用 dll\dark_core 的；还没重随出这些行就不测）
    #[test]
    fn value_random_rule_fields() {
        let base = std::env::var_os("DR_DEFS_DIR").map(std::path::PathBuf::from).unwrap_or_else(|| {
            std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..").join("dll").join("dark_core")
        });
        let (Ok(rt), Ok(aff)) = (fs::read_to_string(base.join("runtime.txt")), fs::read_to_string(base.join("affixes.txt"))) else { return };
        let d = parse(&rt);
        let mut key_of = HashMap::new();
        let mut centers: HashMap<(usize, usize), Vec<Option<f32>>> = HashMap::new();
        let mut want = Vec::new();
        for l in aff.lines() {
            let f: Vec<&str> = l.split('\t').collect();
            match f[0] {
                "fam" if f.len() > 6 => {
                    key_of.insert(f[1].parse::<usize>().unwrap(), f[6].to_string());
                }
                "famnum" => {
                    centers.insert((f[1].parse().unwrap(), f[2].parse().unwrap()), f[5].split(',').map(|x| x.parse().ok()).collect());
                }
                "famrnum" => want.push((
                    f[1].parse::<usize>().unwrap(),
                    f[2].parse::<usize>().unwrap(),
                    f[3].parse::<usize>().unwrap(),
                    f[4].to_string(),
                    f[5].parse::<f32>().unwrap(),
                    f[6].parse::<f32>().unwrap(),
                    f[7].parse::<usize>().unwrap(),
                )),
                _ => {}
            }
        }
        if want.is_empty() {
            return;
        }
        let mut nd = d.clone();
        assert!(Arc::ptr_eq(&nd.hits, &d.hits) && Arc::ptr_eq(&nd.foe_hits, &d.foe_hits), "复制的 Def 共用大表");
        for (k, r, nth, field, a, b, j) in &want {
            let key = &key_of[k];
            let rule = nd.rules.iter_mut().filter(|x| &x.key == key).nth(*nth).unwrap_or_else(|| panic!("{key} 没有第 {nth} 条规则"));
            let before = format!("{:?}", rule.kind);
            let c = centers[&(*k, *j)][*r].unwrap();
            assert!(set_num(&mut rule.kind, field, *r, 12345.0), "{key} 第 {nth} 条规则（{}）不认得 {field}", before.split(' ').next().unwrap_or(""));
            let after = format!("{:?}", rule.kind);
            assert!(after.contains("12345"), "{key}.{field} 没写进去");
            // 原来这一档的数 = a + b × 现在的数：放回去和原来一样
            assert!(set_num(&mut rule.kind, field, *r, a + b * c));
            assert_eq!(format!("{:?}", rule.kind), before, "{key}.{field}：a + b × 现在的数 {c} 和原来这一档的数不一样");
        }
        eprintln!("词条数值随机二期：规则里的数 {} 处都认得", want.len());
    }
}
