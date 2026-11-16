//! 七咒（参数侧 rr/curses.py；设计稿 dev\item_system\超限锻造石与高难度.md §9；用户 2026-11-03）：标了 lock 的难度档（当前档标记亮着）里七条诅咒都生效，
//! 区域碎片凑满 shards 片的那一条反转成祝福。碎片在 ovldrop 发 Boss 首杀的超限锻造石时一起给（on_boss_first），存在事件标记里（每个区域 3 位）。
//! - 常驻的（每 0.5 秒核对，缺了补挂、不要了摘掉）：诅咒监听标记 listen（玩家脚本见到它才发七咒要的事件）、焚魂、众目、蚀甲的祝福；
//!   黯辉：身上出现大卢恩的激活效果 → 诅咒摘掉 / 祝福换成翻倍的副本（没有副本的照旧）。
//! - 事件（每帧看玩家身上的脉冲标记，刚出现的算一次，标记编号读 runtime.txt 的 mark 行）：受击 hit → 蚀甲诅咒加一层（erode_secs 秒没再挨打就清零）；
//!   出招类别：攻击 attack（翻滚后 ROLL_LINK 内算翻滚攻击）、跳劈 jatk、蓄力 charged、施法 cast_new、射击 shot_new、防御反击 guard_counter、致命一击 crit。
//! - 周围的敌人（每 SCAN 一次，游戏距离列表 echo_range 米内的敌对角色）：血量掉了、而且 CAT_LINK 内你出过招，就算你打中了它：
//!   千变：同一类连着打它，诅咒按次数挂「受到的伤害」降档；换一类，祝福按次数升档（每个敌人各记各的）；回响祝福：BURST 后追加掉血的 echo%（不会打死）。
//!   烙印：每 brand_every 秒在 brand_range 米内随机挑一个敌人挂印记，印记持续 brand_secs 秒后摘掉，到下一次之间没有印记
//!   （用户 2026-11-04「改为有间隔，而不是持续被烙印」：以前印记留到换下一个，只有一个敌人的 Boss 战等于一直被烙印）
//!   （诅咒：它的攻击 ×2 / 祝福：它受到的伤害 ×1.3，杀死它回复 brand_heal% 生命和专注）。
//! - 你自己：掉血和受击事件对得上（HURT_LINK 内），回响诅咒在 echo_hurt 秒后再扣一次 echo%（最多扣到 1，不会致死）——旧的；
//!   有 echodown 行（用户 2026-11-04「每5s没命中敌人 伤害降低5% 最多5层 命中敌人后清零」）就改成：从上一次打中敌人（周围敌人那一轮认的）起
//!   每 echo_every 秒一层，挂第几层的「造成的伤害」降低效果，打中敌人清零；不再回响受到的伤害。
//! - 对勇于挑战者的馈赠（revive，用户 2026-11-05；不是咒痕，没有碎片，咒痕页直接以祝福显示）：这几档里每次休息后第一次死亡满状态复活。
//!   死亡由玩家脚本拦下（sc/hks.py 的 DR_Revive），它挂「刚复活」的效果；这里每帧看，刚出现就补满生命、专注、精力，点亮「用过了」的标记（存档，退出重进不刷新），
//!   摘掉「可用」的效果（带状态图标）。坐上赐福，或者真的死了（比如掉进深渊）回到赐福，标记熄灭、又能用。
//! - 离开这几档：摘掉玩家身上的、敌人身上的（还在场的）。联机先不管。
//! - 叙事提示（dev\narrative\叙事方案.md）：第一次进这几档放两行开场（标记 openseen，每个角色一次；开了 Boss 改版时 bossmode 等世界对上了才叫 opening，
//!   不然和重启提示混在一起；没开时这里自己放）；每道咒痕反转后接一句 revline，七道都反转再放 all。咒痕页的来历是 curses.txt 的 lore 行。
//! - 开发工具（dll\dark_dev「七咒测试」）写 curses_req.txt：碎片 <区域序号|全部> <n>、烙印 换、开场 试放|重置、反转提示 <区域序号>、全反转提示。

use std::collections::{HashMap, HashSet};
use std::fs;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use eldenring::cs::{BlockId, BonfireWarpParam, ChrInsExt, SoloParamRepository, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::gear::{flag_get, flag_set};
use crate::rules::{FOE_HIT_KINDS, is_foe};
use crate::{dir, log};

const SLOW: Duration = Duration::from_millis(500);
/// 敌人身上的子弹命中标记只挂 0.1 秒，要比它勤
const SCAN: Duration = Duration::from_millis(50);
/// 出招以后这么久以内敌人掉血，算你打的
const CAT_LINK: Duration = Duration::from_millis(1500);
/// 翻滚以后这么久以内出招，算翻滚攻击
const ROLL_LINK: Duration = Duration::from_millis(800);
/// 同一个敌人两次掉血隔这么久才算两下（多段攻击别一下就把千变叠满）
const FOE_HIT_GAP: Duration = Duration::from_millis(300);
/// 回响祝福挂上扣血效果后，这么久以内敌人掉的血算回响自己的（效果晚几帧才扣），过了还没到的作废
const ECHO_LAND: Duration = Duration::from_millis(500);
/// 你掉血和受击事件相差这么久以内才算挨打（毒、焚魂这类不算）
const HURT_LINK: Duration = Duration::from_millis(400);
/// 血量 0 持续这么久才算真的死了（读档时一瞬间的 0、复活还没写进去的那一帧不算）
const DEAD_HOLD: Duration = Duration::from_secs(1);
/// 在这几档待这么久才放开场提示（读档时别和别的提示挤在一起）
const OPEN_HOLD: Duration = Duration::from_secs(3);
/// 读图（传送、死了回来、读档）后人物站稳多久再看离赐福多远
const GRACE_SETTLE: Duration = Duration::from_millis(1500);
/// 读图后人物一直没放进地图（块号 -1）最多等这么久，过了就不看了
const GRACE_GIVE_UP: Duration = Duration::from_secs(20);
/// 读图后离赐福这么近（米）就算传送到了赐福：原版传送到赐福本来就算休息（敌人重生、圣杯瓶补满），站在赐福旁也随时能坐下休息
const GRACE_NEAR: f32 = 12.0;

/// 赐福在整张地图上的位置：赐福传送表（BonfireWarpParam）的地图块 + 坐标（坐标就是赐福资产在块里的位置，rr/extragrace.py 核对过）。
/// 参数表读好了才建，建一次
static GRACES: OnceLock<Vec<(u32, crate::barrier::G)>> = OnceLock::new();

fn graces() -> Option<&'static [(u32, crate::barrier::G)]> {
    if let Some(g) = GRACES.get() {
        return Some(g);
    }
    let repo = unsafe { SoloParamRepository::instance() }.ok()?;
    let v: Vec<(u32, crate::barrier::G)> = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        repo.rows::<BonfireWarpParam>()
            .map(|(id, r)| (id, crate::barrier::global(BlockId::from_parts(r.area_no(), r.grid_x_no(), r.grid_z_no(), 0), r.pos_x(), r.pos_y(), r.pos_z())))
            .collect()
    }))
    .ok()?;
    if v.is_empty() {
        return None;
    }
    Some(GRACES.get_or_init(|| v))
}

/// 同一张地图上离 me 最近的赐福：(传送行, 距离米)
fn nearest_grace(list: &[(u32, crate::barrier::G)], me: &crate::barrier::G) -> Option<(u32, f32)> {
    list.iter()
        .filter(|(_, g)| g.key == me.key)
        .map(|(id, g)| (*id, ((g.x - me.x).powi(2) + (g.y - me.y).powi(2) + (g.z - me.z).powi(2)).sqrt()))
        .min_by(|a, b| a.1.total_cmp(&b.1))
}

/// 出招类别（千变）：1 攻击、2 跳劈、3 蓄力、4 施法、5 射击、6 防御反击、7 致命一击、8 翻滚攻击（攻击之前 ROLL_LINK 内翻滚过）
const CAT_EVENTS: [(&str, u8); 8] = [("jatk", 2), ("charged", 3), ("cast_new", 4), ("shot_new", 5), ("guard_counter", 6), ("crit", 7), ("throw_new", 9), ("aroma", 10)];
/// 命中累积（hit_self：你的攻击打中了东西，箭、法术、道具都算，多远都算）之后多久内敌人掉血算你打中的
const SELF_HIT_LINK: Duration = Duration::from_millis(300);
/// 放过箭 / 法术 / 道具之后这么久内，距离列表里没有的敌人（拉塔恩等）也看子弹命中标记
const RANGED_LINK: Duration = Duration::from_secs(10);

#[derive(Debug, Default, PartialEq)]
struct Region {
    key: String,
    flags: Vec<u32>,
    name: [String; 2],
}

#[derive(Debug, Default, PartialEq)]
struct Def {
    tiers: Vec<u32>,
    listen: i32,
    shards: u32,
    regions: Vec<Region>,
    /// 诅咒键 → [中文名, 英文名, 中文诅咒, 中文祝福, 英文诅咒, 英文祝福]
    texts: HashMap<String, Vec<String>>,
    burn: (i32, i32),
    gaze: (i32, i32),
    erode_b: i32,
    erode_secs: f32,
    erode_c: Vec<i32>,
    /// 回响诅咒（新）：每几秒一层、各层的效果；空 = 旧的（受到的伤害再回响一次）
    echo_every: f32,
    echo_down: Vec<i32>,
    brand: (i32, i32),
    brand_every: f32,
    brand_range: f32,
    brand_heal: f32,
    /// 印记持续几秒（0 = 留到下一次换目标，旧定义）
    brand_secs: f32,
    vary_c: Vec<i32>,
    vary_b: Vec<i32>,
    /// 千变的招式标记（玩家脚本在各招式的动作状态里挂，持续 vary_secs 秒）：身上有几种 = 最近用过几种招式
    vary_marks: HashSet<i32>,
    /// 千变诅咒每隔几秒才加重一档（0 = 马上到位）
    vary_ramp: f32,
    gloom_rm: Vec<i32>,
    gloom_dbl: HashMap<i32, i32>,
    echo: f32,
    echo_hurt: f32,
    echo_hit: f32,
    echo_range: f32,
    bosses: HashMap<u32, usize>,
    /// 事件 → 脉冲标记（runtime.txt 的 mark 行）
    marks: HashMap<String, i32>,
    /// 战斗复活：可用的效果、刚复活的效果、这次休息后用过了的标记（0 = 没开）
    revive: (i32, i32, u32),
    /// 咒痕页那一行：[中文名, 英文名, 中文说明, 英文说明]
    gift: Vec<String>,
    /// 咒痕页的来历：诅咒键（馈赠是 gift）→ [中文, 英文]
    lore: HashMap<String, Vec<String>>,
    /// 开场提示放过了的标记（存档；0 = 没有开场）
    open_seen: u32,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();

fn list(s: &str) -> Vec<i32> {
    s.split(',').filter_map(|x| x.trim().parse().ok()).collect()
}

fn parse(text: &str, runtime: &str) -> Option<Def> {
    let mut d = Def { shards: 5, ..Def::default() };
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}');
        if l.starts_with("region\t") || l.starts_with("text\t") || l.starts_with("gift\t") || l.starts_with("lore\t") {
            let f: Vec<&str> = l.split('\t').collect();
            if f[0] == "region" && f.len() >= 6 {
                d.regions.push(Region {
                    key: f[2].to_string(),
                    flags: list(f[3]).into_iter().map(|x| x as u32).collect(),
                    name: [f[4].to_string(), f[5].to_string()],
                });
            } else if f[0] == "text" && f.len() >= 8 {
                d.texts.insert(f[1].to_string(), f[2..8].iter().map(|x| x.to_string()).collect());
            } else if f[0] == "gift" && f.len() >= 5 {
                d.gift = f[1..5].iter().map(|x| x.to_string()).collect();
            } else if f[0] == "lore" && f.len() >= 4 {
                d.lore.insert(f[1].to_string(), f[2..4].iter().map(|x| x.to_string()).collect());
            }
            continue;
        }
        let f: Vec<&str> = l.split_whitespace().collect();
        let n = |i: usize| f.get(i).and_then(|x| x.parse::<f64>().ok());
        match f.as_slice() {
            ["tier", ..] => d.tiers.push(n(1)? as u32),
            ["listen", ..] => d.listen = n(1)? as i32,
            ["shards", ..] => d.shards = n(1)? as u32,
            ["burn", ..] => d.burn = (n(1)? as i32, n(2)? as i32),
            ["gaze", ..] => d.gaze = (n(1)? as i32, n(2)? as i32),
            ["erode", _, _, c] => (d.erode_b, d.erode_secs, d.erode_c) = (n(1)? as i32, n(2)? as f32, list(c)),
            ["echodown", _, c] => (d.echo_every, d.echo_down) = (n(1)? as f32, list(c)),
            ["brand", ..] if f.len() >= 6 => {
                (d.brand, d.brand_every, d.brand_range, d.brand_heal) = ((n(1)? as i32, n(2)? as i32), n(3)? as f32, n(4)? as f32, n(5)? as f32);
                d.brand_secs = f.get(6).and_then(|x| x.parse().ok()).unwrap_or(0.0);
            }
            ["vary", c, b] => (d.vary_c, d.vary_b) = (list(c), list(b)),
            ["varyramp", ..] => d.vary_ramp = n(1)? as f32,
            ["varymark", ..] => {
                let (a, k) = (n(1)? as i32, n(2)? as i32);
                d.vary_marks = (a..a + k.max(0)).collect();
            }
            ["gloom", rm, dbl] => {
                d.gloom_rm = list(rm);
                d.gloom_dbl = dbl.split(',').filter_map(|x| x.split_once(':')).filter_map(|(a, b)| Some((a.parse().ok()?, b.parse().ok()?))).collect();
            }
            ["echo", ..] if f.len() >= 5 => (d.echo, d.echo_hurt, d.echo_hit, d.echo_range) = (n(1)? as f32, n(2)? as f32, n(3)? as f32, n(4)? as f32),
            ["boss", ..] if f.len() >= 3 => _ = d.bosses.insert(n(1)? as u32, n(2)? as usize),
            ["revive", ..] if f.len() >= 4 => d.revive = (n(1)? as i32, n(2)? as i32, n(3)? as u32),
            ["openseen", ..] => d.open_seen = n(1)? as u32,
            _ => {}
        }
    }
    for l in runtime.lines() {
        let f: Vec<&str> = l.split('\t').collect();
        if f.len() >= 3 && f[0] == "mark" {
            if let Ok(sp) = f[2].trim().parse() {
                d.marks.insert(f[1].to_string(), sp);
            }
        }
    }
    (!d.tiers.is_empty() && d.listen > 0 && d.regions.len() == 7).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| {
        parse(&fs::read_to_string(dir().join("curses.txt")).unwrap_or_default(), &fs::read_to_string(dir().join("runtime.txt")).unwrap_or_default())
    })
    .as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("咒痕（{} 档，{} 场 Boss 掉碎片，{} 个事件标记）", d.tiers.len(), d.bosses.len(), d.marks.len()),
        None => "咒痕（没有 curses.txt，不管）".into(),
    }
}

fn shards(d: &Def, r: usize) -> u32 {
    d.regions[r].flags.iter().enumerate().filter(|(_, f)| flag_get(**f) == Some(true)).fold(0, |v, (i, _)| v | 1 << i)
}

fn set_shards(d: &Def, r: usize, v: u32) {
    for (i, f) in d.regions[r].flags.iter().enumerate() {
        flag_set(*f, v >> i & 1 == 1);
    }
}

fn name(d: &Def, key: &str, lang: usize) -> String {
    d.texts.get(key).and_then(|t| t.get(lang)).cloned().unwrap_or_else(|| key.to_string())
}

/// ovldrop：这场 Boss 战第一次在这一档被打败——它所在区域的碎片 +1，凑满反转
pub fn on_boss_first(defeat: u32) {
    let Some(d) = def() else { return };
    let Some(&r) = d.bosses.get(&defeat) else { return };
    let old = shards(d, r);
    if old >= d.shards {
        return;
    }
    set_shards(d, r, old + 1);
    let key = &d.regions[r].key;
    let zh = name(d, key, 0);
    log(&format!("咒痕：Boss 战 {defeat} → {} 的碎片 {old} → {}（{zh}）", d.regions[r].name[0], old + 1));
    // 原版闪烁提示（notes.rs）
    if old + 1 >= d.shards {
        crate::notes::push(&format!("rev {r}"));
        crate::notes::push(&format!("revline {r}"));
        if (0..d.regions.len()).all(|k| shards(d, k) >= d.shards) {
            crate::notes::push("all");
        }
    } else {
        crate::notes::push(&format!("shard {r} {}", old + 1));
    }
}

/// 第一次进「死亡」以上的开场提示（每个角色一次）：不在这几档、放过了就什么都不做
pub fn opening() {
    let Some(d) = def() else { return };
    if d.open_seen == 0 || flag_get(d.open_seen) != Some(false) || !d.tiers.iter().any(|&f| flag_get(f) == Some(true)) {
        return;
    }
    if crate::notes::push("open 1") && crate::notes::push("open 2") {
        flag_set(d.open_seen, true);
        log("咒痕：第一次进高难度档，放开场提示");
    }
}

/// 「七咒」页：每条（键, 碎片, 要几片, 反转了没有, 区域名, [名字, 诅咒, 祝福, 来历]）按语言
pub fn ui_state(lang: usize) -> Option<Vec<(String, u32, u32, bool, String, [String; 4])>> {
    let d = def()?;
    let l = lang.min(1);
    let lore = |k: &str| d.lore.get(k).and_then(|x| x.get(l)).cloned().unwrap_or_default();
    let mut out: Vec<_> = d
        .regions
        .iter()
        .enumerate()
        .map(|(r, g)| {
            let n = shards(d, r).min(d.shards);
            let t = d.texts.get(&g.key);
            let pick = |i: usize| t.and_then(|t| t.get(i)).cloned().unwrap_or_default();
            (g.key.clone(), n, d.shards, n >= d.shards, g.name[l].clone(), [pick(l), pick(2 + l * 2), pick(3 + l * 2), lore(&g.key)])
        })
        .collect();
    // 对勇于挑战者的馈赠：没有碎片（need = 0），直接当祝福显示
    if d.revive.0 > 0 && d.gift.len() >= 4 {
        out.push(("gift".to_string(), 0, 0, true, String::new(), [d.gift[l].clone(), String::new(), d.gift[2 + l].clone(), lore("gift")]));
    }
    Some(out)
}

/// 千变：最近用过 kinds 种招式时挂第几档（1 起；None = 不挂）。诅咒：只用 1 种是最重的 nc 档，每多 1 种轻 1 档；祝福：每多 1 种高 1 档，最多 nb 档
fn vary_level(rev: bool, kinds: usize, nc: usize, nb: usize) -> Option<usize> {
    if kinds == 0 {
        return None;
    }
    let n = if rev { (kinds - 1).min(nb) } else { nc.saturating_sub(kinds - 1) };
    (n > 0).then_some(n)
}

/// 千变诅咒渐进（用户 2026-11-09「渐进生效吧」）：变轻马上变；变重先到 1 档，之后到了间隔（due）才再重 1 档
fn vary_step(cur: usize, target: usize, due: bool) -> usize {
    if target <= cur {
        target
    } else if cur == 0 || due {
        cur + 1
    } else {
        cur
    }
}

struct Foe {
    hp: i32,
    last_hit: Option<Instant>,
    /// 上一轮身上有没有子弹命中标记
    marked: bool,
    /// 回响祝福已经挂上、还没扣到的血，到什么时候作废
    echo_due: i32,
    echo_at: Option<Instant>,
}

/// 这一轮的掉血先抵回响自己的（不算打中，否则回响会再回响）：返回 (还没扣到的, 剩下算别的伤害的)
fn take_echo(due: i32, drop: i32) -> (i32, i32) {
    let own = due.min(drop.max(0));
    (due - own, drop - own)
}

/// 这一轮算不算打中这个敌人、算哪一类出招：子弹命中标记刚出现一定算（箭、道具、法术，飞多久都算，类别按最近一次出招）；
/// 否则要掉血、而且刚出过招（用户 2026-11-05「远程射击还是不能清空沉寂」：箭不一定触发命中累积 hit_self，飞得久的也过了 CAT_LINK）
fn foe_hit_cat(fresh_mark: bool, dropped: bool, my_cat: Option<u8>, last_cat: u8) -> Option<u8> {
    if fresh_mark {
        Some(my_cat.unwrap_or(last_cat))
    } else if dropped {
        my_cat
    } else {
        None
    }
}

struct St {
    dev_at: Instant,
    in_tier: bool,
    slow_at: Instant,
    scan_at: Instant,
    reversed: HashMap<String, bool>,
    applied: HashSet<i32>,
    pulse_prev: HashSet<i32>,
    cat: Option<(u8, Instant)>,
    roll_at: Option<Instant>,
    hit_at: Option<Instant>,
    /// 命中累积刚到的时间；这一下还没算给沉寂
    self_hit_at: Option<Instant>,
    self_hit_new: bool,
    /// 最近一次放箭 / 法术 / 道具
    ranged_at: Option<Instant>,
    echo_log: u32,
    erode: (usize, Option<Instant>, Option<i32>),
    /// 千变：现在挂的那档、这次进游戏换档写了几行日志
    vary_sp: Option<i32>,
    vary_log: u32,
    /// 诅咒现在第几档（渐进用）、上一次换档的时间
    vary_n: usize,
    vary_at: Option<Instant>,
    /// 回响诅咒（新）：上一次打中敌人（或者开始算）的时间、现在挂的那层
    echo_quiet: Option<Instant>,
    echo_sp: Option<i32>,
    foes: HashMap<usize, Foe>,
    brand: Option<(usize, i32)>,
    brand_at: Instant,
    /// 这一个印记到什么时候摘掉（brand_secs 为 0 时不摘）
    brand_until: Option<Instant>,
    foe_echo: Vec<(Instant, usize, i32)>,
    my_echo: Vec<(Instant, i32)>,
    my_hp: i32,
    /// 还没对上受击事件的掉血
    my_drop: Option<(i32, Instant)>,
    /// 战斗复活：上一帧有没有「刚复活」、上一帧坐没坐在赐福、血量 0 从什么时候开始、真的死了还没回来
    revive_on: bool,
    revive_sit: bool,
    revive_dead_at: Option<Instant>,
    revive_dead: bool,
    /// 读过图（人物不在场过）还没看离赐福多远、回来后第一次看到人物的时刻
    revive_loaded: bool,
    revive_back_at: Option<Instant>,
    /// 开场提示：第一次看到在这几档的时刻、这次读档看过了
    open_at: Option<Instant>,
    open_done: bool,
    rng: u64,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

impl St {
    fn rev(&self, key: &str) -> bool {
        self.reversed.get(key).copied().unwrap_or(false)
    }

    fn roll(&mut self) -> u64 {
        self.rng = self.rng.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.rng;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

/// 离开这几档：摘掉玩家和还在场的敌人身上的
fn strip(d: &Def, st: &mut St, wcm: &mut WorldChrMan) {
    let live = live!(wcm);
    if let Some(p) = wcm.main_player.as_mut() {
        let mine: Vec<i32> = st.applied.iter().copied().chain(st.erode.2).chain(st.echo_sp).chain(st.vary_sp).collect();
        for sp in mine {
            p.remove_speffect(sp);
        }
    }
    let foe_sps: HashSet<i32> = [d.brand.0, d.brand.1].into_iter().collect();
    for s in wcm.chr_sets.iter().flatten() {
        for c in s.characters() {
            let a = c as *mut _ as usize;
            if !live.contains(&a) || !(st.foes.contains_key(&a) || st.brand.is_some_and(|b| b.0 == a)) {
                continue;
            }
            for sp in c.special_effect.entries().map(|x| x.param_id).filter(|x| foe_sps.contains(x)).collect::<Vec<_>>() {
                c.remove_speffect(sp);
            }
        }
    }
    log("咒痕：离开高难度档，摘掉诅咒 / 祝福");
    st.applied.clear();
    st.erode = (0, None, None);
    (st.vary_sp, st.vary_n, st.vary_at) = (None, 0, None);
    st.echo_quiet = None;
    st.echo_sp = None;
    st.foes.clear();
    st.brand = None;
    st.foe_echo.clear();
    st.my_echo.clear();
}

/// 开发工具的请求（dll\dark_dev 写 curses_req.txt，处理完删掉）
fn show_flag(v: Option<bool>) -> &'static str {
    match v {
        Some(true) => "亮",
        Some(false) => "灭",
        None => "读不到",
    }
}

fn dev_req(d: &Def, st: &mut St, now: Instant) {
    let path = dir().join("curses_req.txt");
    let Ok(text) = fs::read_to_string(&path) else { return };
    let _ = fs::remove_file(&path);
    for line in text.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')) {
        let f: Vec<&str> = line.split_whitespace().collect();
        match f.as_slice() {
            ["碎片", r, n] => {
                let Ok(n) = n.parse::<u32>() else { continue };
                let rs: Vec<usize> = match r.parse::<usize>() {
                    Ok(k) if k < d.regions.len() => vec![k],
                    _ => (0..d.regions.len()).collect(),
                };
                for k in rs {
                    set_shards(d, k, n.min(d.shards));
                }
                st.slow_at = now;
                log(&format!("咒痕：开发工具：区域 {r} 的碎片设成 {n}"));
            }
            ["复活", "重置"] => {
                if d.revive.2 > 0 {
                    flag_set(d.revive.2, false);
                    st.slow_at = now;
                    log("咒痕（馈赠）：开发工具：重置成这次休息后没用过");
                }
            }
            ["开场", "试放"] => {
                crate::notes::push("open 1");
                crate::notes::push("open 2");
            }
            ["开场", "重置"] => {
                if d.open_seen > 0 {
                    flag_set(d.open_seen, false);
                    (st.open_at, st.open_done) = (None, false);
                    log("咒痕：开发工具：开场提示重置成没放过");
                }
            }
            ["反转提示", r] => {
                crate::notes::push(&format!("rev {r}"));
                crate::notes::push(&format!("revline {r}"));
            }
            ["全反转提示"] => {
                crate::notes::push("all");
            }
            ["烙印", "换"] => {
                st.brand_at = now;
                log("咒痕：开发工具：马上换烙印的目标");
            }
            // 开发工具直接点亮 / 熄灭一个我们自己的标记（93000 块；比如高难度锁定 93910，用户 2026-11-14 录素材要切回普通）
            ["标记", f, on @ ("亮" | "灭")] => {
                let Some(f) = f.parse::<u32>().ok().filter(|f| (93000..94000).contains(f)) else {
                    log(&format!("咒痕：开发工具：标记 {f} 不在 93000~93999，不改"));
                    continue;
                };
                let was = flag_get(f);
                flag_set(f, *on == "亮");
                log(&format!("咒痕：开发工具：标记 {f} {on}（之前 {}，现在 {}）", show_flag(was), show_flag(flag_get(f))));
            }
            _ => log(&format!("咒痕：开发工具：看不懂「{line}」")),
        }
    }
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| St {
        dev_at: now,
        in_tier: false,
        slow_at: now,
        scan_at: now,
        reversed: HashMap::new(),
        applied: HashSet::new(),
        pulse_prev: HashSet::new(),
        cat: None,
        roll_at: None,
        hit_at: None,
        self_hit_at: None,
        self_hit_new: false,
        ranged_at: None,
        echo_log: 0,
        erode: (0, None, None),
        vary_sp: None,
        vary_log: 0,
        vary_n: 0,
        vary_at: None,
        echo_quiet: None,
        echo_sp: None,
        foes: HashMap::new(),
        brand: None,
        brand_at: now,
        brand_until: None,
        foe_echo: Vec::new(),
        my_echo: Vec::new(),
        my_hp: 0,
        my_drop: None,
        revive_on: false,
        revive_sit: false,
        revive_dead_at: None,
        revive_dead: false,
        revive_loaded: false,
        revive_back_at: None,
        open_at: None,
        open_done: false,
        rng: SystemTime::now().duration_since(UNIX_EPOCH).map_or(3, |t| t.as_nanos() as u64),
    });
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    if wcm.main_player.is_none() {
        st.foes.clear();
        st.brand = None;
        st.foe_echo.clear();
        st.my_echo.clear();
        st.applied.clear();
        st.erode = (0, None, None);
        (st.vary_sp, st.vary_n, st.vary_at) = (None, 0, None);
        st.echo_quiet = None;
        st.echo_sp = None;
        st.revive_on = false;
        st.revive_dead_at = None;
        st.revive_loaded = true;
        st.revive_back_at = None;
        (st.open_at, st.open_done) = (None, false);
        return;
    }
    if now >= st.dev_at {
        st.dev_at = now + SLOW;
        dev_req(d, st, now);
    }
    // 在不在这几档：不在时 0.5 秒看一次
    if !st.in_tier && now < st.slow_at {
        return;
    }
    let in_tier = d.tiers.iter().any(|&f| flag_get(f) == Some(true));
    if !in_tier {
        if st.in_tier {
            strip(d, st, wcm);
        }
        st.in_tier = false;
        st.slow_at = now + SLOW;
        (st.open_at, st.open_done) = (None, false);
        return;
    }
    if !st.in_tier {
        st.in_tier = true;
        st.slow_at = now;
        log("咒痕：在高难度档里，诅咒生效");
    }
    // 开场提示：这次读档只看一次；开了 Boss 改版时归 bossmode 叫（要等世界对上）
    if !st.open_done {
        let at = *st.open_at.get_or_insert(now);
        if now - at >= OPEN_HOLD {
            st.open_done = true;
            if !crate::bossmode::active() {
                opening();
            }
        }
    }
    let Some(p) = wcm.main_player.as_mut() else { return };
    let me = &p.chr_ins as *const _ as usize;
    let my_team = p.chr_ins.team_type;
    let ids: HashSet<i32> = p.chr_ins.special_effect.entries().map(|x| x.param_id).collect();
    // 对勇于挑战者的馈赠（放在常驻的前面：复活的这一帧别把「可用」又补回去）
    if d.revive.0 > 0 {
        let (ready, just, used) = d.revive;
        let on = ids.contains(&just);
        if on && !st.revive_on {
            flag_set(used, true);
            p.remove_speffect(ready);
            let x = &mut p.chr_ins.modules.data;
            x.hp = x.max_hp;
            x.fp = x.max_fp;
            x.stamina = x.max_stamina;
            crate::notes::push("revive");
            log("咒痕（馈赠）：这次休息后第一次死亡，满状态复活");
            // 复活顶掉了这次死亡：血量 0 停了 1 秒以上才复活时（日志 2026-11-14 15:02:03），别再当成「死了回到赐福」把复活又放开
            st.revive_dead = false;
            st.revive_dead_at = None;
        }
        st.revive_on = on;
        let ta = &p.chr_ins.modules.time_act;
        let sitting = !ta.anim_queue.is_empty() && (68000..68100).contains(&ta.anim_queue[ta.read_idx as usize % ta.anim_queue.len()].anim_id);
        if sitting && !st.revive_sit && flag_get(used) == Some(true) {
            flag_set(used, false);
            st.slow_at = now;
            log("咒痕（馈赠）：休息了，复活又能用");
        }
        st.revive_sit = sitting;
        // 传送到赐福也算休息（用户 2026-11-14「高难下传送到赐福没有正确挂上复活」：在野外打开地图传送不坐下，以前标记一直亮着）：
        // 读图后站稳了离最近的赐福够近就复活又能用。死了回到赐福、在赐福旁读档也算（坐下本来就能休息）
        if st.revive_loaded {
            let at = *st.revive_back_at.get_or_insert(now);
            // 人物出现后要过一会儿才放进地图（块号 -1、坐标 0 时看不出在哪），等块号有效再看
            let placed = i32::from(p.current_block_id) != -1;
            if now - at >= GRACE_SETTLE && (placed || now - at >= GRACE_GIVE_UP) {
                st.revive_loaded = false;
                st.revive_back_at = None;
                let b = p.block_position;
                let me = crate::barrier::global(p.current_block_id, b.x, b.y, b.z);
                let near = graces().and_then(|g| nearest_grace(g, &me));
                match near {
                    Some((id, d)) if d <= GRACE_NEAR => {
                        if flag_get(used) == Some(true) {
                            flag_set(used, false);
                            st.slow_at = now;
                            log(&format!("咒痕（馈赠）：传送到了赐福（传送行 {id}，离 {d:.1} 米），复活又能用"));
                        }
                    }
                    _ => log(&format!(
                        "咒痕（馈赠）：读图后不在赐福旁（{} 块里 ({:.1}, {:.1}, {:.1})，最近的赐福 {}），复活照旧",
                        p.current_block_id,
                        b.x,
                        b.y,
                        b.z,
                        near.map_or("没找到".to_string(), |(id, d)| format!("传送行 {id}，{d:.1} 米"))
                    )),
                }
            }
        }
        let dead = p.chr_ins.modules.data.hp <= 0;
        st.revive_dead_at = if dead { st.revive_dead_at.or(Some(now)) } else { None };
        if st.revive_dead_at.is_some_and(|t| now - t >= DEAD_HOLD) {
            st.revive_dead = true;
        }
        if !dead && st.revive_dead {
            st.revive_dead = false;
            if flag_get(used) == Some(true) {
                flag_set(used, false);
                st.slow_at = now;
                log("咒痕（馈赠）：死了回到赐福，复活又能用");
            }
        }
    }
    // 常驻的：每 0.5 秒
    if now >= st.slow_at {
        st.slow_at = now + SLOW;
        for (r, g) in d.regions.iter().enumerate() {
            st.reversed.insert(g.key.clone(), shards(d, r) >= d.shards);
        }
        let pick = |rev: bool, (c, b): (i32, i32)| if rev { b } else { c };
        let mut want: HashSet<i32> = [d.listen, pick(st.rev("burn"), d.burn), pick(st.rev("gaze"), d.gaze)].into_iter().filter(|&x| x > 0).collect();
        if st.rev("erode") && d.erode_b > 0 {
            want.insert(d.erode_b);
        }
        if d.revive.0 > 0 && flag_get(d.revive.2) == Some(false) {
            want.insert(d.revive.0);
        }
        for &sp in want.difference(&ids) {
            p.apply_speffect(sp, false);
        }
        for &sp in st.applied.difference(&want) {
            p.remove_speffect(sp);
        }
        st.applied = want;
        // 黯辉：大卢恩的激活效果
        for &rm in d.gloom_rm.iter().filter(|x| ids.contains(x)) {
            if !st.rev("gloom") {
                p.remove_speffect(rm);
                log(&format!("咒痕（黯辉）：摘掉大卢恩的激活效果 {rm}"));
            } else if let Some(&dbl) = d.gloom_dbl.get(&rm) {
                p.remove_speffect(rm);
                p.apply_speffect(dbl, false);
                log(&format!("咒痕（黯辉反转）：大卢恩的激活效果 {rm} 换成翻倍的 {dbl}"));
            }
        }
    }
    // 事件：脉冲标记刚出现
    let fired = |name: &str| d.marks.get(name).is_some_and(|sp| ids.contains(sp) && !st.pulse_prev.contains(sp));
    if d.marks.get("roll").is_some_and(|sp| ids.contains(sp)) {
        st.roll_at = Some(now);
    }
    let mut cat = None;
    if fired("attack") {
        cat = Some(if st.roll_at.is_some_and(|t| now - t <= ROLL_LINK) { 8 } else { 1 });
    }
    for (ev, k) in CAT_EVENTS {
        if fired(ev) {
            cat = Some(k);
        }
    }
    if let Some(k) = cat {
        st.cat = Some((k, now));
        if matches!(k, 4 | 5 | 9 | 10) {
            st.ranged_at = Some(now);
        }
    }
    let hit = fired("hit");
    let self_hit = fired("hit_self");
    st.pulse_prev = d.marks.values().copied().filter(|sp| ids.contains(sp)).collect();
    if self_hit {
        st.self_hit_at = Some(now);
        st.self_hit_new = true;
    }
    // 命中累积（同 rules.rs 的连击值）：你的攻击打中东西时给你挂 hit_self。沉寂靠它算「打中了」（用户 2026-11-05：
    // 以前只看 30 米内的敌人掉血、1.5 秒内出过招，远处的箭、投掷道具、飞得慢的法术都不算）
    if let Some(&acc) = d.marks.get("hit_acc") {
        if !ids.contains(&acc) {
            p.apply_speffect(acc, false);
        }
    }
    // 蚀甲诅咒：每次受击加一层，erode_secs 秒没再挨打清零
    let swap = |p: &mut eldenring::cs::PlayerIns, old: Option<i32>, new: Option<i32>| {
        if old != new {
            if let Some(o) = old {
                p.remove_speffect(o);
            }
            if let Some(n) = new {
                p.apply_speffect(n, false);
            }
        }
    };
    if !st.rev("erode") && !d.erode_c.is_empty() {
        let (mut n, mut until, old) = st.erode;
        if hit {
            n = (n + 1).min(d.erode_c.len());
            until = Some(now + Duration::from_secs_f32(d.erode_secs));
        }
        if until.is_some_and(|t| now >= t) {
            n = 0;
            until = None;
        }
        let new = (n > 0).then(|| d.erode_c[n - 1]);
        swap(p, old, new);
        st.erode = (n, until, new);
    } else if st.erode.2.is_some() {
        swap(p, st.erode.2, None);
        st.erode = (0, None, None);
    }
    // 千变（用户 2026-11-09 照 Golden Age 的多才多艺重做）：身上有几种招式标记 = 最近 vary_secs 秒用过几种招式，换成对应那档
    if !d.vary_marks.is_empty() {
        let kinds = ids.iter().filter(|x| d.vary_marks.contains(x)).count();
        let rev = st.rev("vary");
        let lvl = vary_level(rev, kinds, d.vary_c.len(), d.vary_b.len()).unwrap_or(0);
        let n = if rev {
            lvl
        } else {
            let due = st.vary_at.is_none_or(|t| now - t >= Duration::from_secs_f32(d.vary_ramp));
            let n = vary_step(st.vary_n, lvl, due);
            if n != st.vary_n {
                st.vary_at = Some(now);
            }
            n
        };
        st.vary_n = n;
        let want = (n > 0).then(|| if rev { d.vary_b.get(n - 1) } else { d.vary_c.get(n - 1) }).flatten().copied();
        if want != st.vary_sp {
            swap(p, st.vary_sp, want);
            if st.vary_log < 40 {
                st.vary_log += 1;
                log(&format!("咒痕（千变{}）：最近用过 {kinds} 种招式 → 效果 {}", if rev { "祝福" } else { "" }, want.map_or("无".into(), |x| x.to_string())));
            }
            st.vary_sp = want;
        }
    }
    // 回响诅咒：掉血和受击事件对得上才算挨打
    let hp = p.chr_ins.modules.data.hp;
    if hit {
        st.hit_at = Some(now);
    }
    if hp < st.my_hp && hp > 0 {
        st.my_drop = Some((st.my_hp - hp, now));
    }
    st.my_hp = hp;
    if let Some((drop, t)) = st.my_drop {
        let linked = st.hit_at.is_some_and(|h| (if h > t { h - t } else { t - h }) <= HURT_LINK);
        if linked {
            if !st.rev("echo") && d.echo > 0.0 && d.echo_down.is_empty() {
                let amt = (drop as f32 * d.echo / 100.0).round() as i32;
                if amt > 0 {
                    st.my_echo.push((now + Duration::from_secs_f32(d.echo_hurt), amt));
                }
            }
            st.my_drop = None;
        } else if now - t > HURT_LINK {
            st.my_drop = None;
        }
    }
    let due: Vec<i32> = st.my_echo.iter().filter(|e| now >= e.0).map(|e| e.1).collect();
    st.my_echo.retain(|e| now < e.0);
    for amt in due {
        let x = &mut p.chr_ins.modules.data;
        if x.hp > 1 {
            x.hp = (x.hp - amt).max(1);
            st.my_hp = x.hp;
        }
    }
    // 周围的敌人
    if now < st.scan_at {
        return;
    }
    st.scan_at = now + SCAN;
    // 出招 CAT_LINK 内掉血算你打中的；飞得慢的（出招后超过 CAT_LINK 才打到）看命中累积，算最近一次出招的类别
    let self_recent = st.self_hit_at.is_some_and(|t| now - t <= SELF_HIT_LINK);
    let my_cat = st.cat.filter(|c| now - c.1 <= CAT_LINK).map(|c| c.0).or_else(|| self_recent.then(|| st.cat.map_or(1, |c| c.0)));
    let last_cat = st.cat.map_or(1, |c| c.0);
    let bullet: Vec<i32> = FOE_HIT_KINDS.iter().filter_map(|k| d.marks.get(*k).copied()).collect();
    let Some(around) = around!(wcm, me) else { return };
    let mut seen = HashSet::new();
    let mut brand_pool = Vec::new();
    let mut heal = 0.0f32;
    let (rev_brand, rev_echo, brand_addr) = (st.rev("brand"), st.rev("echo"), st.brand.map(|b| b.0));
    let mut brand_dead = false;
    let mut hit_any = false;
    let mut hit_mark = false;
    for e in &around {
        let a = e.chr_ins.as_ptr() as usize;
        if a == me || e.distance > d.echo_range.max(d.brand_range) {
            continue;
        }
        let c = unsafe { &mut *e.chr_ins.as_ptr() };
        if !is_foe(c, my_team) {
            continue;
        }
        seen.insert(a);
        let hp = c.modules.data.hp;
        if hp > 0 && e.distance <= d.brand_range {
            brand_pool.push(a);
        }
        let marked = c.special_effect.entries().any(|s| bullet.contains(&s.param_id));
        let foe = st.foes.entry(a).or_insert(Foe { hp, last_hit: None, marked: false, echo_due: 0, echo_at: None });
        let fresh_mark = marked && !foe.marked;
        foe.marked = marked;
        let drop = foe.hp - hp;
        let was = foe.hp;
        foe.hp = hp;
        if foe.echo_at.is_some_and(|t| now > t) {
            (foe.echo_due, foe.echo_at) = (0, None);
        }
        let (due, drop) = take_echo(foe.echo_due, drop);
        foe.echo_due = due;
        // 烙印祝福：杀死被烙印的敌人
        if was > 0 && hp <= 0 && brand_addr == Some(a) {
            if rev_brand {
                heal = d.brand_heal;
            }
            brand_dead = true;
        }
        hit_any |= fresh_mark;
        hit_mark |= fresh_mark;
        if foe_hit_cat(fresh_mark, drop > 0 && hp >= 0, my_cat, last_cat).is_none() {
            continue;
        }
        if foe.last_hit.is_some_and(|t| now - t < FOE_HIT_GAP) {
            continue;
        }
        foe.last_hit = Some(now);
        hit_any = true;
        // 回响祝福
        if rev_echo && d.echo > 0.0 && e.distance <= d.echo_range {
            let amt = (drop as f32 * d.echo / 100.0).round() as i32;
            if amt > 0 {
                st.foe_echo.push((now + Duration::from_secs_f32(d.echo_hit), a, amt));
            }
        }
    }
    if brand_dead {
        st.brand = None;
        st.brand_until = None;
    }
    // 命中累积到了就算打中（打中物件也算，分不出来）
    hit_any |= std::mem::take(&mut st.self_hit_new);
    // 距离列表里没有的敌人（拉塔恩等，同 rules.rs）：刚放过箭 / 法术 / 道具才看，平时不扫全场
    if !hit_any && !st.rev("echo") && st.ranged_at.is_some_and(|t| now - t <= RANGED_LINK) {
        let listed: HashSet<usize> = around.iter().map(|e| e.chr_ins.as_ptr() as usize).collect();
        for &a in live!(wcm).iter().filter(|a| **a != me && !listed.contains(*a)) {
            let c = unsafe { &*(a as *const eldenring::cs::ChrIns) };
            if is_foe(c, my_team) && c.special_effect.entries().any(|s| bullet.contains(&s.param_id)) {
                hit_any = true;
                hit_mark = true;
                break;
            }
        }
    }
    if hit_any && st.echo_sp.is_some() && st.echo_log < 20 {
        st.echo_log += 1;
        log(if hit_mark { "咒痕（沉寂）：箭 / 法术 / 道具打中了，层数清零" } else { "咒痕（沉寂）：打中了，层数清零" });
    }
    // 回响诅咒（新）：从上一次打中敌人起每 echo_every 秒一层，打中清零；反转了就摘掉
    if !d.echo_down.is_empty() {
        let want = if st.rev("echo") {
            None
        } else {
            let since = *st.echo_quiet.get_or_insert(now);
            if hit_any {
                st.echo_quiet = Some(now);
            }
            echo_layer(d, if hit_any { Duration::ZERO } else { now - since })
        };
        if want != st.echo_sp {
            swap(p, st.echo_sp, want);
            st.echo_sp = want;
        }
    }
    if heal > 0.0 {
        let x = &mut p.chr_ins.modules.data;
        x.hp = (x.hp + (x.max_hp as f32 * heal / 100.0) as i32).min(x.max_hp);
        x.fp = (x.fp + (x.max_fp as f32 * heal / 100.0) as i32).min(x.max_fp);
        log(&format!("咒痕（烙印反转）：杀死被烙印的敌人，回复 {heal}% 生命和专注"));
    }
    // 回响祝福：到时间的追加伤害（还在场、还活着才扣，最多扣到 1）
    if !st.foe_echo.is_empty() {
        let live = live!(wcm);
        let due: Vec<(usize, i32)> = st.foe_echo.iter().filter(|x| now >= x.0).map(|x| (x.1, x.2)).collect();
        st.foe_echo.retain(|x| now < x.0);
        let mut total: HashMap<usize, i32> = HashMap::new();
        for (a, amt) in due {
            if live.contains(&a) {
                *total.entry(a).or_default() += amt;
            }
        }
        for (a, amt) in total {
            let c = unsafe { &mut *(a as *mut eldenring::cs::ChrIns) };
            let hp = c.modules.data.hp;
            if hp <= 1 {
                continue;
            }
            // 精确伤害（用户 2026-11-09）：写进专用效果行再挂，游戏显示的就是这个数；行都占着时退回下面的固定档位
            let amt = amt.min(hp - 1);
            // 客机不直接写敌人血量（联机计划 13.2 G2）：只走下面的扣血效果
            if !crate::coop::client() && crate::rules::foe_hp_exact(c, amt) {
                if let Some(f) = st.foes.get_mut(&a) {
                    f.echo_due += amt;
                    f.echo_at = Some(now + ECHO_LAND);
                }
                continue;
            }
            // 走引爆那套扣血效果，游戏才显示伤害数字（用户 2026-11-09）；小到没有档时照旧直接扣
            let picked = crate::rules::hp_burst(amt as f32, (hp - 1) as f32, |sp| c.special_effect.entries().any(|e| e.param_id == sp));
            if picked.is_empty() {
                if crate::coop::client_skip("咒痕回响的直接扣血") {
                    continue;
                }
                c.modules.data.hp = (hp - amt).max(1);
                if let Some(f) = st.foes.get_mut(&a) {
                    f.hp = c.modules.data.hp;
                }
                continue;
            }
            for &(_, sp) in &picked {
                crate::coop::note(crate::coop::Op::Apply(sp), c);
                c.apply_speffect(sp, false);
            }
            if let Some(f) = st.foes.get_mut(&a) {
                f.echo_due += picked.iter().map(|x| x.0 as i32).sum::<i32>();
                f.echo_at = Some(now + ECHO_LAND);
            }
        }
    }
    st.foes.retain(|a, _| seen.contains(a));
    // 烙印：印记到时间就摘掉（到下一次之间没有印记）
    if let (Some((a, sp)), Some(t)) = (st.brand, st.brand_until) {
        if now >= t {
            if seen.contains(&a) {
                unsafe { &mut *(a as *mut eldenring::cs::ChrIns) }.remove_speffect(sp);
            }
            st.brand = None;
            st.brand_until = None;
        }
    }
    // 每 brand_every 秒烙一个：印记有持续时间时上一个已经摘了，谁都能被选（只有一个敌人的 Boss 战隔一段烙一次）；
    // 没有持续时间（旧定义）照旧换一个别的
    if now >= st.brand_at && d.brand.0 > 0 {
        st.brand_at = now + Duration::from_secs_f32(d.brand_every.max(1.0));
        let sp = if st.rev("brand") { d.brand.1 } else { d.brand.0 };
        let cur = st.brand.map(|b| b.0);
        let pool: Vec<usize> = brand_pool.iter().copied().filter(|&a| Some(a) != cur).collect();
        let pick = (!pool.is_empty()).then(|| pool[(st.roll() % pool.len() as u64) as usize]);
        if let Some(a) = pick {
            // 换目标：先摘掉上一个（还在场的）
            if let Some((old, old_sp)) = st.brand.take() {
                if seen.contains(&old) {
                    unsafe { &mut *(old as *mut eldenring::cs::ChrIns) }.remove_speffect(old_sp);
                }
            }
            let c = unsafe { &mut *(a as *mut eldenring::cs::ChrIns) };
            c.apply_speffect(sp, false);
            log(&format!("咒痕（烙印{}）：NPC {}（实体 {}）被烙印", if st.rev("brand") { "反转" } else { "" }, c.npc_param_id, c.event_entity_id));
            st.brand = Some((a, sp));
            st.brand_until = (d.brand_secs > 0.0).then(|| now + Duration::from_secs_f32(d.brand_secs));
        }
    }
}

/// 沉寂（回响诅咒的新版）：离上一次打中敌人多久 → 挂第几层（每 echo_every 秒一层，最多层数；不到一层不挂）
fn echo_layer(d: &Def, quiet: Duration) -> Option<i32> {
    if d.echo_down.is_empty() || d.echo_every <= 0.0 {
        return None;
    }
    let n = ((quiet.as_secs_f32() / d.echo_every) as usize).min(d.echo_down.len());
    (n > 0).then(|| d.echo_down[n - 1])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn echo_drop_not_a_hit() {
        assert_eq!(take_echo(100, 100), (0, 0), "全是回响自己的");
        assert_eq!(take_echo(100, 30), (70, 0), "分几帧到");
        assert_eq!(take_echo(100, 250), (0, 150), "同时挨了别的伤害");
        assert_eq!(take_echo(0, 40), (0, 40));
        assert_eq!(take_echo(50, -10), (50, -10), "回血不抵");
    }

    /// 子弹命中标记刚出现一定算打中（飞得久、没掉血也算）；只有掉血要刚出过招
    #[test]
    fn foe_hits() {
        assert_eq!(foe_hit_cat(true, false, None, 5), Some(5), "箭飞了很久才到：算最近一次出招");
        assert_eq!(foe_hit_cat(true, true, Some(1), 5), Some(1));
        assert_eq!(foe_hit_cat(false, true, None, 5), None, "别人打掉的血不算");
        assert_eq!(foe_hit_cat(false, true, Some(1), 5), Some(1));
        assert_eq!(foe_hit_cat(false, false, Some(1), 5), None);
    }

    /// 沉寂：每 5 秒没打中一层，最多 5 层；不到 5 秒不挂
    #[test]
    fn echo_layers() {
        let d = Def { echo_every: 5.0, echo_down: vec![7304081, 7304082, 7304083, 7304084, 7304085], ..Default::default() };
        let s = Duration::from_secs_f32;
        assert_eq!(echo_layer(&d, s(4.9)), None);
        assert_eq!(echo_layer(&d, s(5.0)), Some(7304081));
        assert_eq!(echo_layer(&d, s(12.0)), Some(7304082));
        assert_eq!(echo_layer(&d, s(99.0)), Some(7304085));
        assert_eq!(echo_layer(&Def::default(), s(99.0)), None, "没有 echodown 行：旧的回响");
    }

    /// 千变（照多才多艺）：诅咒只用 1 种最重、5 种起不扣；祝福 2 种起 +1 档、封顶
    #[test]
    fn vary_levels() {
        assert_eq!(vary_level(false, 0, 4, 5), None);
        assert_eq!(vary_level(false, 1, 4, 5), Some(4));
        assert_eq!(vary_level(false, 4, 4, 5), Some(1));
        assert_eq!(vary_level(false, 5, 4, 5), None);
        assert_eq!(vary_level(true, 1, 4, 5), None);
        assert_eq!(vary_level(true, 3, 4, 5), Some(2));
        assert_eq!(vary_level(true, 20, 4, 5), Some(5));
    }

    /// 诅咒渐进：从 1 档起，没到间隔不再加重；变轻（换招）马上；没招式了清零
    #[test]
    fn vary_ramp() {
        assert_eq!(vary_step(0, 4, false), 1);
        assert_eq!(vary_step(1, 4, false), 1);
        assert_eq!(vary_step(1, 4, true), 2);
        assert_eq!(vary_step(3, 1, false), 1);
        assert_eq!(vary_step(2, 0, false), 0);
        assert_eq!(vary_step(4, 4, true), 4);
    }

    /// 读图后找最近的赐福：只比同一张地图；大地图跨格子按整张地图坐标算
    #[test]
    fn nearest_grace_same_map() {
        use crate::barrier::global;
        let list = vec![
            (61423600, global(BlockId::from_parts(60, 42, 36, 0), -40.7, 91.0, 79.3)),
            (110007, global(BlockId::from_parts(11, 0, 0, 0), -55.1, 47.5, -307.2)),
            (110504, global(BlockId::from_parts(11, 5, 0, 0), -55.1, 47.5, -307.2)),
        ];
        // 隔壁格子看同一个赐福：x 差一个格子（256 米）
        let me = global(BlockId::from_parts(60, 43, 36, 0), -40.7 - 256.0 + 3.0, 91.0, 79.3 + 4.0);
        let (id, d) = nearest_grace(&list, &me).unwrap();
        assert_eq!(id, 61423600);
        assert!((d - 5.0).abs() < 1e-3);
        // 王城和灰城坐标一样也是两张图
        let me = global(BlockId::from_parts(11, 5, 0, 0), -50.0, 47.5, -307.2);
        assert_eq!(nearest_grace(&list, &me).map(|x| x.0), Some(110504));
        // 别的地图没有赐福
        assert_eq!(nearest_grace(&list, &global(BlockId::from_parts(10, 0, 0, 0), 0.0, 0.0, 0.0)), None);
    }

    /// 定义：档、监听、区域（碎片标记、名字）、文字、各条的效果行和数值、Boss → 区域；事件标记从 runtime.txt 读
    #[test]
    fn parse_def() {
        let mut t = String::from("tier 9956\ntier 9957\nlisten 7304000\nshards 5\n");
        for k in 0..7 {
            t += &format!("region\t{k}\tgaze\t{},{},{}\t区{k}\tR{k}\n", 100 + k * 3, 101 + k * 3, 102 + k * 3);
        }
        t += "text\tgaze\t众目\tMany Eyes\t诅咒\t祝福\tcurse\tbless\nburn 7304010 7304011\ngaze 7304020 7304021\n\
              erode 7304030 10 7304031,7304032\nbrand 7304040 7304041 15 20 20 5\nvary 7304051,7304052 7304061\nvarymark 7304200 3\nvaryramp 2.5\ngloom 600,610 600:7304070\n\
              echo 20 3 1 30\nboss 10000800 0\nrevive 7304090 7304091 93488\ngift\t名\tName\t说明\tDesc\n";
        let d = parse(&t, "mark\thit\t7210756\nmark\tattack\t7210755\n").unwrap();
        assert_eq!((d.tiers.len(), d.listen, d.shards, d.regions.len()), (2, 7304000, 5, 7));
        assert_eq!(d.revive, (7304090, 7304091, 93488));
        assert_eq!(d.gift, ["名", "Name", "说明", "Desc"]);
        assert_eq!(d.regions[1].flags, vec![103, 104, 105]);
        assert_eq!(d.texts["gaze"][3], "祝福");
        assert_eq!((d.erode_b, d.erode_secs, d.erode_c.clone()), (7304030, 10.0, vec![7304031, 7304032]));
        assert_eq!((d.brand, d.brand_every, d.brand_heal, d.brand_secs), ((7304040, 7304041), 15.0, 20.0, 5.0));
        assert_eq!((d.vary_c.len(), d.vary_b.len()), (2, 1));
        assert_eq!(d.vary_marks, [7304200, 7304201, 7304202].into_iter().collect());
        assert_eq!(d.vary_ramp, 2.5);
        assert_eq!(d.gloom_dbl.get(&600), Some(&7304070));
        assert_eq!((d.echo, d.echo_hurt, d.echo_hit, d.echo_range), (20.0, 3.0, 1.0, 30.0));
        assert_eq!(d.bosses.get(&10000800), Some(&0));
        assert_eq!(d.marks.get("hit"), Some(&7210756));
    }
}
