//! 联机装备赠送（联机计划 13.7；用户 2026-11-16「赠送做到置物包里吧 还能新增一个按钮吗」）。
//! 背包里点一件新装备 → 物品菜单里 dark_lock 加的「送给 <队友>」（问 dr_gift_can、选了调 dr_gift_begin）→ 这里：
//! - 送：这件要在背包里（不在仓库）、没装备着、没锁定、是这个角色的新装备。经联机通道把配方（rec_line）和强化等级发给那个队友（GIFT），
//!   对方回 GOK 才把这件从背包移走、从记录删掉（不进回购商店）；回 GNO 或 GIVE_WAIT 内没回音就什么都不动，提示没送出去。
//!   回 GOK 时再看一次：等回话时装备上了（或换了角色）就不移（游戏的移除函数会把穿着的整格删掉，装备表指着空格），
//!   提示没送出去，发 GBK 让对方把送去的那件退回（对方那件也装备上了 / 不在背包里就退不了，两边各留一件）。
//! - 收：通道收到 GIFT（link.rs 只转发档案和本机一致的队员发来的），按配方挑一个空格、改写参数行和文字，走发货表发进背包
//!   （同开发工具 devgive / ship，只是武器带上强化等级）；deliver_check 核对到了、记进记录后回 GOK，没空格 / 配方看不懂 / 没到账回 GNO。
//!   同一份（队员, 随机数）只处理一次。
//! - 提示：原版闪烁提示 gift sent / gift fail / gift got（rr/notes.py）；菜单选项里的队友名字由 confirm_tick 写进占位 #IC~#IG（sc/lock.py）。

use std::collections::HashSet;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use super::*;
use crate::link::{Kind, Packet};

/// 送出去等对方回话最多等多久
const GIVE_WAIT: Duration = Duration::from_secs(60);
/// 收下的多久内还认对方的退回（GBK：对方收到 GOK 当场就发）
const BACK_KEEP: Duration = Duration::from_secs(300);
/// 菜单里最多列几个队友（sc/lock.py 的文字 4192~4196，占位 #IC~#IG）
pub(crate) const MAX_PEERS: usize = 5;

struct Out {
    nonce: u64,
    peer: u64,
    cat: usize,
    idx: u32,
    raw: u32,
    name: String,
    t0: Instant,
    /// 送的时候是哪个角色（等回话时换了角色就不动背包）
    who: (i32, String),
}

struct In {
    peer: u64,
    nonce: u64,
    cat: usize,
    idx: u32,
    desc: String,
}

/// 收下了的（对方可能还要退回）
struct Got {
    peer: u64,
    nonce: u64,
    cat: usize,
    idx: u32,
    desc: String,
    who: (i32, String),
    t: Instant,
}

#[derive(Default)]
struct G {
    /// 物品菜单的请求：(类, 物品编号含强化, 第几个队友)
    req: Vec<(usize, u32, usize)>,
    out: Vec<Out>,
    /// 收到的 GIFT（还没处理）
    inq: Vec<(u64, Packet)>,
    /// 正在发进背包的那一份
    wait_in: Option<In>,
    seen: HashSet<(u64, u64)>,
    /// 对方的回话：(队员, 随机数, 收下没有, 原因)
    results: Vec<(u64, u64, bool, String)>,
    /// 对方要退回的：(队员, 随机数)
    back: Vec<(u64, u64)>,
    /// 最近收下的（BACK_KEEP 内、最多 16 份）
    got: Vec<Got>,
    rng: u64,
}

static GS: Mutex<Option<G>> = Mutex::new(None);

fn with<R>(f: impl FnOnce(&mut G) -> R) -> R {
    let mut g = GS.lock().unwrap_or_else(|e| e.into_inner());
    f(g.get_or_insert_with(G::default))
}

/// 背包里的物品编号（武器含强化等级）→ 容器序号；不是新装备 None（同 held 的认法）
fn cont_of(d: &Defs, cat: usize, pid: u32) -> Option<u32> {
    if cat >= NCAT {
        return None;
    }
    let key = if cat == 0 { pid / 10000 * 10000 } else { pid };
    d.items.cont[cat].idx_of(key).or_else(|| start_off(&d.items, cat, key))
}

/// 这一格（背包格序号、物品编号原始值）是不是装备着。装备表存的是 key_cap + 格序号（同 recycle_list / ih_armor，只比格序号永远对不上）；
/// 物品编号再和身上的六把武器、四件防具、四个护符、誓约槽（dark_slot 的第五个护符槽）比一遍（同 dark_sell 的 equipped_ids）
fn worn(pgd: &PlayerGameData, slot: usize, raw: u32) -> bool {
    let key_cap = pgd.equipment.equip_inventory_data.items_data.key_items_capacity;
    if pgd.equipment.equipment_item_idx_list.contains(&(key_cap + slot as u32)) {
        return true;
    }
    let e = &pgd.equipment.equipment_entries;
    let gear = [
        e.weapon_primary_left,
        e.weapon_primary_right,
        e.weapon_secondary_left,
        e.weapon_secondary_right,
        e.weapon_tertiary_left,
        e.weapon_tertiary_right,
        e.protector_head,
        e.protector_chest,
        e.protector_hands,
        e.protector_legs,
    ];
    gear.iter().map(|x| x.into_inner()).chain(e.accessories.iter().chain(std::iter::once(&e.covenant)).map(|x| x.into_inner())).any(|x| x == raw)
}

/// 背包（不含仓库）里这个容器（类, 序号）的那一格 →（格序号, 物品编号原始值）：按容器认，挪过格子、强化过都找得到；好几格时先挑编号是 prefer 的
fn slot_of(d: &Defs, pgd: &PlayerGameData, cat: usize, idx: u32, prefer: Option<u32>) -> Option<(usize, u32)> {
    let v: Vec<(usize, u32)> = pgd
        .equipment
        .equip_inventory_data
        .items_data
        .normal_entries()
        .iter()
        .enumerate()
        .filter_map(|(i, e)| e.as_option().map(|it| (i, it)))
        .filter(|(_, it)| it.item_id.category() as u8 == INV_CAT[cat] && it.quantity > 0 && cont_of(d, cat, it.item_id.param_id()) == Some(idx))
        .map(|(i, it)| (i, it.item_id.into_inner()))
        .collect();
    v.iter().copied().find(|&(_, r)| Some(r) == prefer).or_else(|| v.first().copied())
}

/// dark_lock 建物品菜单时问：这件（类 0 武器 / 1 防具 / 2 护符，物品编号）能送给几个队友（0 = 不加选项）
#[unsafe(no_mangle)]
pub extern "C" fn dr_gift_can(cat: u32, id: u32) -> u32 {
    // dark_lock 给的是背包里的物品编号，带类别高位（防具 0x1…、护符 0x2…）：去掉再认（同 dark_lock 的 key_id；联机实测 2026-11-17 菜单里没有「送给」）
    let id = id & 0x0FFF_FFFF;
    let n = crate::link::gift_peers().len().min(MAX_PEERS);
    if n == 0 {
        return 0;
    }
    let Some(d) = defs() else { return 0 };
    if cont_of(d, cat as usize, id).is_none() {
        // 诊断：有能送的队友、这件却认不出是新装备（前 10 件写一行）
        static LOGGED: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
        if LOGGED.fetch_add(1, std::sync::atomic::Ordering::Relaxed) < 10 {
            log(&format!("赠送：物品菜单问的这件（类 {cat}，编号 {id}）不是新装备，不加「送给」"));
        }
        return 0;
    }
    n as u32
}

/// dark_lock：选了「送给第 i 个队友」
#[unsafe(no_mangle)]
pub extern "C" fn dr_gift_begin(cat: u32, id: u32, i: u32) {
    let id = id & 0x0FFF_FFFF;
    with(|g| {
        if g.req.len() < 8 {
            g.req.push((cat as usize, id, i as usize));
        }
    });
}

/// link.rs：收到 GIFT / GBK（退回）
pub(crate) fn gift_in(from: u64, pk: Packet) {
    with(|g| {
        if pk.kind == Kind::GiftBack {
            if let Some(n) = pk.get("n").and_then(|x| x.parse::<u64>().ok()) {
                if g.back.len() < 16 {
                    g.back.push((from, n));
                }
            }
        } else if g.inq.len() < 16 {
            g.inq.push((from, pk));
        }
    });
}

/// link.rs：对方回了 GOK / GNO
pub(crate) fn gift_result(from: u64, nonce: u64, ok: bool, why: String) {
    with(|g| g.results.push((from, nonce, ok, why)));
}

fn next_nonce(g: &mut G) -> u64 {
    if g.rng == 0 {
        g.rng = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos() as u64).unwrap_or(1) | 1;
    }
    g.rng ^= g.rng << 13;
    g.rng ^= g.rng >> 7;
    g.rng ^= g.rng << 17;
    g.rng.max(1)
}

fn reply(to: u64, nonce: u64, ok: bool, why: &str) {
    let pk = if ok { Packet::new(Kind::GiftOk).with("n", nonce) } else { Packet::new(Kind::GiftNo).with("n", nonce).with("why", why) };
    crate::link::send_to(to, pk);
}

/// 送：检查这件、发 GIFT；返回送给谁（日志用）
fn give(d: &Defs, st: &St, pgd: &PlayerGameData, who: &(i32, String), g: &mut G, cat: usize, pid: u32, i: usize) -> Result<String, String> {
    let peers = crate::link::gift_peers();
    let (peer, pname) = peers.get(i).cloned().ok_or("这个队友已经不在会话里了")?;
    let idx = cont_of(d, cat, pid).ok_or("不是新装备")?;
    let rec = st.recs.get(&(cat, idx)).cloned().ok_or("不是这个角色的新装备（没有记录）")?;
    let slots = inv_slots(pgd, INV_CAT[cat], pid);
    let (_, raw) = *slots.first().ok_or("要在背包里才能送（仓库里的先取出来）")?;
    if slots.iter().any(|&(s, r)| worn(pgd, s, r)) {
        return Err("装备着的不能送，先卸下来".into());
    }
    let key_id = if cat == 0 { pid / 100 * 100 } else { pid };
    if locked_keys(&rec_read(LOCK_FILE).unwrap_or_default(), who).contains(&(cat, key_id)) {
        return Err("锁定着，先解锁".into());
    }
    if g.out.iter().any(|o| o.cat == cat && o.idx == idx) {
        return Err("这件正在送".into());
    }
    let nonce = next_nonce(g);
    let lv = if cat == 0 { pid % 100 } else { 0 };
    crate::link::send_to(peer, Packet::new(Kind::Gift).with("n", nonce).with("c", cat).with("lv", lv).with("r", rec_line(&rec)));
    g.out.push(Out { nonce, peer, cat, idx, raw, name: pname.clone(), t0: Instant::now(), who: who.clone() });
    Ok(format!("{}（{}），等对方收下", pname, compose_cap(&d.lib, &rec, 0, d.items.cap[1])[0]))
}

/// 收：按配方挑空格、改写、发进背包；返回 (随机数, 类, 容器序号, 说明)，出错返回 (随机数, 原因)
fn receive(d: &Defs, st: &mut St, pgd: &PlayerGameData, pk: &Packet) -> Result<(u64, usize, u32, String), (u64, String)> {
    let nonce = pk.get("n").and_then(|x| x.parse::<u64>().ok()).ok_or((0, "随机数读不出来".to_string()))?;
    let e = |s: &str| (nonce, s.to_string());
    let cat = pk.get("c").and_then(|x| x.parse::<usize>().ok()).filter(|&c| c < NCAT).ok_or_else(|| e("类别不对"))?;
    let lv = pk.get("lv").and_then(|x| x.parse::<u32>().ok()).unwrap_or(0).min(25);
    let mut rec = pk.get("r").and_then(rec_parse).ok_or_else(|| e("配方看不懂（两边整合包版本不一样？）"))?;
    if rec.cat != cat {
        return Err(e("配方的类别对不上"));
    }
    let held = held(d, pgd);
    let free = free(d, st, &held);
    let idx = *free[cat].first().ok_or_else(|| e("对方这一类的新装备满了，放不下"))?;
    rec.idx = idx;
    // 强化等级超过新强化类型的上限（对方那把是 +rmax 以上的老武器，对方那边也照原版强化）：这一格记进 over_max，build_row 保留本体的
    // 原版强化类型（新强化类型只有 0~rmax 级，+lv 查不到强化行）；进存档时 over_max 照背包重算，这把照样在里面。
    // 没超的从 over_max 拿掉（空出来的格子可能是之前那把超限武器留下的），照新武器换成新强化类型
    if cat == 0 && d.lib.rmax > 0 {
        if lv > d.lib.rmax {
            st.over_max.insert(idx);
        } else {
            st.over_max.remove(&idx);
        }
    }
    write_row(d, st, &rec).map_err(|x| e(&format!("改写参数行失败：{x}")))?;
    // 改写后这把的强化类型里要有 +lv 那一行，没有就不发（物品编号指着不存在的强化行）
    if cat == 0 && lv > 0 {
        let ok = unsafe { SoloParamRepository::instance() }.ok().is_some_and(|r| {
            r.get::<EquipParamWeapon>(d.items.cont[0].id(idx)).is_some_and(|w| r.get::<ReinforceParamWeapon>(w.reinforce_type_id() as u32 + lv).is_some())
        });
        if !ok {
            return Err(e(&format!("这把在对方那边强化不到 +{lv}（两边整合包版本不一样？）")));
        }
    }
    write_texts(d, &rec);
    let id = d.items.cont[cat].id(idx) as i32 + if cat == 0 { lv as i32 } else { 0 };
    lot_write(&d.items, &[(LOT_CAT[cat], id, 1)]).map_err(|x| e(&format!("改写发货表失败：{x}")))?;
    if !flag_set(d.items.deliver_flag, true) {
        return Err(e("点亮发货标记失败"));
    }
    st.batches += 1;
    let desc = compose_cap(&d.lib, &rec, 0, d.items.cap[1])[0].clone();
    st.pending = Some(Pending::new(vec![(Made::Gear(rec), 0)]));
    Ok((nonce, cat, idx, desc))
}

/// gear::tick 在 deliver_check 后面调（同一帧里先认它刚到的，再开新的一批）
pub(super) fn tick(d: &Defs, st: &mut St, pgd: &mut PlayerGameData, who: &(i32, String)) {
    let mut g = GS.lock().unwrap_or_else(|e| e.into_inner());
    let g = g.get_or_insert_with(G::default);
    // 物品菜单的请求
    for (cat, pid, i) in std::mem::take(&mut g.req) {
        match give(d, st, pgd, who, g, cat, pid, i) {
            Ok(s) => log(&format!("赠送：送给 {s}")),
            Err(why) => {
                log(&format!("赠送：没送（{why}）"));
                crate::notes::push("gift fail");
            }
        }
    }
    // 对方的回话
    for (from, nonce, ok, why) in std::mem::take(&mut g.results) {
        let Some(pos) = g.out.iter().position(|o| o.nonce == nonce && o.peer == from) else { continue };
        let o = g.out.remove(pos);
        if !ok {
            log(&format!("赠送：{} 没收下（{why}），装备还在你这里", o.name));
            crate::notes::push("gift fail");
            continue;
        }
        // 移走背包里的这一件（按容器认：挪过格子、强化过都找得到），删记录（不进回购商店：回购只收记录里有的）。
        // 先再看一次：等回话时装备上了的不移（游戏的移除函数会把穿着的整格删掉，装备表指着空格）、换了角色的不动（背包和记录都是别的角色的了），
        // 这件留着、记录也留着，让对方把送去的那件退回
        let switched = o.who != *who;
        let slot = if switched { None } else { slot_of(d, pgd, o.cat, o.idx, Some(o.raw)) };
        if switched || slot.is_some_and(|(s, r)| worn(pgd, s, r)) {
            crate::link::send_to(o.peer, Packet::new(Kind::GiftBack).with("n", o.nonce));
            log(&format!("赠送：{} 收下了，但{}，这件没从背包移走；请对方把送去的那件退回", o.name,
                         if switched { "你已经换了角色" } else { "这件在等回话时装备上了" }));
            crate::notes::push("gift fail");
            continue;
        }
        let removed = slot.is_some_and(|(s, r)| remove_slot(pgd, s, r));
        st.recs.remove(&(o.cat, o.idx));
        rec_save(who, st);
        log(&format!("赠送：{} 收下了{}", o.name, if removed { "，已从背包移走" } else { "；这件已经不在背包里了，记录照删" }));
        crate::notes::push("gift sent");
    }
    // 对方要退回（GBK：对方回 GOK 后发现那件装备上了 / 换了角色，没送成）：送来的这件还在背包里、没装备着就移走、删记录；不然两边各留一件
    let now = Instant::now();
    g.got.retain(|x| now.duration_since(x.t) < BACK_KEEP);
    for (from, nonce) in std::mem::take(&mut g.back) {
        let Some(pos) = g.got.iter().position(|x| x.peer == from && x.nonce == nonce) else {
            log("赠送：队友说上次那件没送成、要退回，但找不到是哪一件（太久以前的？），不动");
            continue;
        };
        let w = g.got.remove(pos);
        let why = if w.who != *who {
            "你已经换了角色"
        } else {
            match slot_of(d, pgd, w.cat, w.idx, None) {
                None => "这件已经不在背包里",
                Some((s, r)) if worn(pgd, s, r) => "这件你已经装备上了",
                Some((s, r)) => {
                    if remove_slot(pgd, s, r) {
                        st.recs.remove(&(w.cat, w.idx));
                        rec_save(who, st);
                        log(&format!("赠送：队友那边没送成，送来的 {} 退回了（已从背包移走）", w.desc));
                        continue;
                    }
                    "从背包移不掉"
                }
            }
        };
        log(&format!("赠送：队友那边没送成，送来的 {} 没退回（{why}），两边各留一件", w.desc));
    }
    // 等太久的
    let late: Vec<Out> = {
        let (late, keep): (Vec<Out>, Vec<Out>) = std::mem::take(&mut g.out).into_iter().partition(|o| now.duration_since(o.t0) >= GIVE_WAIT);
        g.out = keep;
        late
    };
    for o in late {
        log(&format!("赠送：{} {} 秒没回话，没送出去，装备还在你这里", o.name, GIVE_WAIT.as_secs()));
        crate::notes::push("gift fail");
    }
    // 收：上一份发完了（deliver_check 处理过、pending 清掉了）就回话
    if g.wait_in.is_some() {
        if st.pending.is_some() {
            return;
        }
        let w = g.wait_in.take().unwrap();
        let ok = st.recs.contains_key(&(w.cat, w.idx)) && held(d, pgd).contains(&(w.cat, w.idx));
        reply(w.peer, w.nonce, ok, "没收到（发货没到背包）");
        log(&format!("赠送：收下队友送的 {}{}", w.desc, if ok { "" } else { "——没到背包，告诉对方没收下" }));
        if ok {
            crate::notes::push("gift got");
            if g.got.len() >= 16 {
                g.got.remove(0);
            }
            g.got.push(Got { peer: w.peer, nonce: w.nonce, cat: w.cat, idx: w.idx, desc: w.desc, who: who.clone(), t: Instant::now() });
        }
    }
    if st.pending.is_some() || st.more || g.inq.is_empty() {
        return;
    }
    let (from, pk) = g.inq.remove(0);
    let nonce = pk.get("n").and_then(|x| x.parse::<u64>().ok()).unwrap_or(0);
    if !g.seen.insert((from, nonce)) {
        return; // 同一份重复发来的
    }
    match receive(d, st, pgd, &pk) {
        Ok((nonce, cat, idx, desc)) => {
            log(&format!("赠送：队友送来 {desc}，发进背包"));
            g.wait_in = Some(In { peer: from, nonce, cat, idx, desc });
        }
        Err((nonce, why)) => {
            log(&format!("赠送：队友送来的没收下（{why}）"));
            reply(from, nonce, false, &why);
        }
    }
}

/// 物品菜单选项里写的队友名字（confirm_tick：占位 #IC 起，第 i 个队友）
pub(super) fn label(i: usize) -> Option<(String, String)> {
    let peers = crate::link::gift_peers();
    peers.get(i).map(|(_, n)| (format!("送给 {n}"), format!("Give to {n}")))
}
