//! 骨灰诊断（用户 2026-11-09「出血没附加上 把日志输出做好」）：测试骨灰（重随 rr/ashtest.py）挂的「命中时触发」为什么没让狼的攻击附带出血，
//! 日志分三段，看断在哪一环：
//! - 召唤物：每只第一次出现记一行（敌人参数、实体、阵营、血量、身上所有特殊效果的编号、测试载体 CARRIER 在不在），之后只记载体的有无
//!   （第一版每次效果变化都记，战斗里一闪而过的效果刷满了日志，2026-11-09）；灵马（敌人参数 TORRENT 段）不算；
//! - 敌人：有测试召唤物（敌人参数 TEST_NPC）在场时，游戏距离列表里 RANGE 米内的敌对角色——第一次看到记血量和出血「还差多少 / 上限」，
//!   之后每次掉血记一行（这次出血有没有跟着变），出血自己变了、身上出现 / 消失出血累积效果 BUILDUP（命中时触发真的触发了，
//!   目标身上会挂它）各记一行。掉血是谁打的分不出来，测的时候别自己出手；
//! - 小结：召唤物全没了、以及在场时每 SUMMARY 记一行（几只召唤物、几只身上有载体、敌人掉血几次、其中出血跟着变几次、BUILDUP 出现了几次）。
//! 没有召唤物时只看一眼召唤物列表（summon_buddy_chr_set），什么都不做；每次进游戏最多 MAX_LINES 行。编号同 rr/ashtest.py。
//! 2026-11-10 起只在测试狼在场时记：一般召唤物（容器、稀有度、前缀、血量核对）的日志在 gear\ashes\fx.rs（「骨灰召唤：」）。

use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::{ChrIns, WorldChrMan};
use fromsoftware_shared::FromStatic;

use crate::log;
use crate::rules::FRIENDLY_TEAMS;

const SCAN: Duration = Duration::from_millis(250);
/// 测试骨灰召唤的狼（rr/ashtest.py 的 NPC）、狼身上的载体（CARRIER）、命中时给目标挂的出血累积（BUILDUP）
const TEST_NPC: i32 = 140709900;
const CARRIER: i32 = 7310000;
const BUILDUP: i32 = 7310001;
/// 看多远的敌人（游戏距离列表，离玩家）
const RANGE: f32 = 30.0;
const MAX_LINES: u32 = 300;
/// 召唤物在场时多久记一次小结
const SUMMARY: Duration = Duration::from_secs(10);
/// 灵马的敌人参数（也在召唤物列表里，一直在场，不算）
const TORRENT: std::ops::Range<i32> = 80000000..80100000;
/// 出血在抗性模块七项里的序号（毒、腐败、出血、咒死、冻伤、睡眠、发狂，同 rules.rs 的 RES_ZH）
const BLEED: usize = 2;

#[derive(Default)]
struct Round {
    summons: u32,
    with_carrier: u32,
    /// 敌人掉血几次、其中出血跟着变了几次
    hp_drops: u32,
    hp_with_bleed: u32,
    bleed_changes: u32,
    buildup_seen: u32,
}

impl Round {
    fn text(&self) -> String {
        format!("召唤物 {} 只，其中 {} 只身上有测试载体 {CARRIER}；敌人掉血 {} 次，其中出血跟着变 {} 次；出血一共变了 {} 次；敌人身上出现出血累积效果 {BUILDUP} {} 次",
                self.summons, self.with_carrier, self.hp_drops, self.hp_with_bleed, self.bleed_changes, self.buildup_seen)
    }
}

struct St {
    next: Instant,
    /// 召唤物地址 → 身上有没有载体
    summons: HashMap<usize, bool>,
    /// 敌人地址 → (血, 出血还差多少, 上限, 身上有没有 BUILDUP)
    foes: HashMap<usize, (i32, i32, i32, bool)>,
    round: Option<Round>,
    /// 上次记小结的时候
    told_at: Instant,
    lines: u32,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

fn say(st: &mut St, s: String) {
    if st.lines >= MAX_LINES {
        return;
    }
    st.lines += 1;
    log(&format!("骨灰诊断：{s}"));
    if st.lines == MAX_LINES {
        log("骨灰诊断：这次进游戏的日志写满了，后面的不记");
    }
}

fn effects(c: &ChrIns) -> Vec<i32> {
    let mut v: Vec<i32> = c.special_effect.entries().map(|e| e.param_id).collect();
    v.sort_unstable();
    v.dedup();
    v
}

pub fn tick() {
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let now = Instant::now();
    let st = g.get_or_insert_with(|| {
        log(&format!("骨灰诊断：开着（只看测试狼 {TEST_NPC}：在场时记它身上的效果、{RANGE} 米内敌人的出血和效果 {BUILDUP}；最多 {MAX_LINES} 行）"));
        St { next: now, summons: HashMap::new(), foes: HashMap::new(), round: None, told_at: now, lines: 0 }
    });
    if now < st.next {
        return;
    }
    st.next = now + SCAN;
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_ref() else {
        st.summons.clear();
        st.foes.clear();
        return;
    };
    let me = &p.chr_ins as *const _ as usize;
    let my_team = p.chr_ins.team_type;
    // 召唤物：(地址, 敌人参数, 实体, 阵营, 血, 上限, 效果)
    let mut cur: Vec<(usize, i32, u32, u8, i32, i32, Vec<i32>)> = Vec::new();
    for c in wcm.summon_buddy_chr_set.characters() {
        let c: &ChrIns = c;
        if TORRENT.contains(&c.npc_param_id) {
            continue;
        }
        cur.push((c as *const ChrIns as usize, c.npc_param_id, c.event_entity_id, c.team_type, c.modules.data.hp, c.modules.data.max_hp, effects(c)));
    }
    if !cur.iter().any(|x| x.1 == TEST_NPC) {
        cur.clear();
    }
    if cur.is_empty() {
        if let Some(r) = st.round.take() {
            say(st, format!("召唤物都没了。这一轮：{}", r.text()));
        }
        st.summons.clear();
        st.foes.clear();
        return;
    }
    let mut add = Round::default();
    let alive: HashSet<usize> = cur.iter().map(|x| x.0).collect();
    for (a, npc, ent, team, hp, max, eff) in &cur {
        let has = eff.contains(&CARRIER);
        match st.summons.get(a).copied() {
            None => {
                add.summons += 1;
                add.with_carrier += has as u32;
                say(st, format!(
                    "召唤物出现：敌人参数 {npc}{}（实体 {ent}，阵营 {team}），血 {hp}/{max}；身上的效果 {eff:?}；测试载体 {CARRIER} {}",
                    if *npc == TEST_NPC { "（测试狼）" } else { "" },
                    if has { "在" } else { "不在" }
                ));
            }
            Some(old) if old != has => {
                say(st, format!("召唤物（敌人参数 {npc}）身上的测试载体 {CARRIER} {}", if has { "又挂上了" } else { "没了" }));
            }
            _ => {}
        }
        st.summons.insert(*a, has);
    }
    st.summons.retain(|a, _| alive.contains(a));
    // 敌人：测试狼在场时才看
    if cur.iter().any(|x| x.1 == TEST_NPC) {
        if let Some(around) = around!(wcm, me) {
            let mut seen = HashSet::new();
            for e in &around {
                let a = e.chr_ins.as_ptr() as usize;
                if a == me || e.distance > RANGE {
                    continue;
                }
                let c = unsafe { e.chr_ins.as_ref() };
                if FRIENDLY_TEAMS.contains(&c.team_type) || c.team_type == my_team || c.modules.data.hp <= 0 {
                    continue;
                }
                let Some(rs) = crate::rules::resist_of(c) else { continue };
                let (rem, max) = (rs[BLEED], rs[BLEED + 7]);
                let bu = c.special_effect.entries().any(|x| x.param_id == BUILDUP);
                seen.insert(a);
                let npc = c.npc_param_id;
                let hp = c.modules.data.hp;
                match st.foes.insert(a, (hp, rem, max, bu)) {
                    None => say(st, format!("敌人（敌人参数 {npc}，{:.1} 米）：血 {hp}/{}，出血 {rem}/{max}{}", e.distance, c.modules.data.max_hp,
                                           if bu { "，身上有出血累积效果" } else { "" })),
                    Some((h0, r0, m0, b0)) => {
                        let bleed = (r0, m0) != (rem, max);
                        if hp < h0 {
                            add.hp_drops += 1;
                            add.hp_with_bleed += bleed as u32;
                            say(st, format!("敌人（敌人参数 {npc}，{:.1} 米）掉血 {h0} → {hp}；出血 {}", e.distance,
                                           if bleed { format!("{r0}/{m0} → {rem}/{max}") } else { format!("没变（{rem}/{max}）") }));
                        } else if bleed {
                            add.bleed_changes += 1;
                            say(st, format!("敌人（敌人参数 {npc}，{:.1} 米）出血 {r0}/{m0} → {rem}/{max}（没掉血）", e.distance));
                        }
                        if bleed && hp < h0 {
                            add.bleed_changes += 1;
                        }
                        if bu != b0 {
                            add.buildup_seen += bu as u32;
                            say(st, format!("敌人（敌人参数 {npc}）身上{}出血累积效果 {BUILDUP}", if bu { "出现了" } else { "没了" }));
                        }
                    }
                }
            }
            st.foes.retain(|a, _| seen.contains(a));
        }
    }
    let r = st.round.get_or_insert_with(Round::default);
    r.summons += add.summons;
    r.with_carrier += add.with_carrier;
    r.hp_drops += add.hp_drops;
    r.hp_with_bleed += add.hp_with_bleed;
    r.bleed_changes += add.bleed_changes;
    r.buildup_seen += add.buildup_seen;
    if now - st.told_at >= SUMMARY {
        st.told_at = now;
        let t = r.text();
        say(st, format!("召唤物在场，到现在：{t}"));
    }
}
