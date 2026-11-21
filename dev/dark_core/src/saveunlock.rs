//! 存档解锁（用户 2026-11-20「给存档里有死亡难度下反转完七道咒痕角色的存档解锁死亡以上难度 不再需要打败黑剑解锁了」）：
//! 赐福「难度调整」第一次进「死亡」「不可能」本来要先击败黑剑（sc/difficulty.py 的门槛 RELEASE_FLAG）；同一个存档文件里有角色
//! 七道咒痕都反转了，门槛就不看了：对话脚本另外看标记 unlock（curses.txt 的 unlock 行），亮着就直接走三个确认框。
//! - 每次认准一个角色（who.rs；回标题再读档也算一次）判断一次，结果写进 unlock，亮、灭都写（老存档里这一位以前当过原版提示的编号位，
//!   残留的值不算数）：这个角色自己七道都反转了（游戏里的标记）→ 亮；否则在后台读存档文件，有格子里的角色七道都反转了 → 亮；
//!   都没有、读不了 → 灭。切换角色要先回标题，游戏这时会存档，所以别的角色的进度在文件里是新的；碎片只增不减，文件里这个角色自己的
//!   那一格不会比游戏里的多，所以不用跳过。
//! - 存档文件：%APPDATA%\EldenRing\<SteamID>\ER0000.rng（单机）、ER0000.rngcoop（联机；以前叫 ER0000.rng.co2）。几个 SteamID 文件夹都有时，
//!   先挑摘要里这个格子正是这个角色名字的，再挑修改时间最新的。
//! - 读法（只读，dev\event_flags 的存档读法）：BND4 第 0~9 项是格子、第 10 项是摘要（都去掉开头 16 字节 MD5）。格子里的事件标记表
//!   0x1BF99F 字节 + 1 字节结尾，后面紧跟 5 个带长度的世界结构（第 2~4 个以 CHR / MOEG / FOEG 开头），照这个找表头。
//!   标记 n 在表里第 holder(n / 1000) × 125 + (n % 1000) / 8 字节的第 7 − n % 8 位；holder 是游戏里这个块在标记数组里的位置
//!   （CSFD4VirtualMemoryFlag 的块描述，只认存在数组里、会存档的块），在游戏线程上取好再交给后台。
//! - 二周目以后（用户 2026-11-21「修一下死亡难度角色进入二周目后不能马上切换到死亡难度的问题」）：进下一周目时游戏清掉了这几个标记
//!   （黑剑的击败标记、难度的锁定和当前档、unlock 都不跨周目），角色又回到第一次进「死亡」的门槛，被「命定之死尚未被释放」拦下。
//!   能进下一周目就是上一周目打通了，黑剑在主线上必经（开敌人随机时是那个位置的头目），所以周目数（GameDataMan.ng_lvl）≥ 1 就点亮 unlock。
//!   通关后直接进下一周目、不回标题时还是同一个角色，所以每帧看：周目数 ≥ 1 而 unlock 灭着（刚被清掉）就再点亮。

use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;
use std::sync::mpsc::{self, Receiver, TryRecvError};
use std::time::SystemTime;

use eldenring::cs::{CSEventFlagMan, GameDataMan};
use fromsoftware_shared::FromStatic;

use crate::gear::{flag_get, flag_set};
use crate::log;

/// 周目数读到比这个大就当结构对不上（不算二周目）
const NG_MAX: u32 = 100;
/// GameDataMan.ng_lvl 的偏移（测试里和 vendored 定义对一下）。2026-11-21 在 2.7.1.0 / 2.7.2.0 两个 exe 里核对：读 GameDataMan 静态指针后
/// 按 dword 读写 +0x120 / +0x124、+0x128 / +0x12c、+0x130 / +0x134 各成一对（本机、房主、备份的「周目数 + 随机出现槽」），和 vendored 一致
#[cfg(test)]
const NG_LVL_AT: usize = 0x120;

const EF_SIZE: usize = 0x1BF99F;
const BLOCK: usize = 125;
const MAGICS: [&[u8; 4]; 3] = [b"CHR ", b"MOEG", b"FOEG"];
const SUMMARY_ON: usize = 0x1954;
const SUMMARY_NAME: usize = 0x195E;
const SUMMARY_STEP: usize = 0x24C;
const SINGLE: [&str; 1] = ["ER0000.rng"];
const COOP: [&str; 2] = ["ER0000.rngcoop", "ER0000.rng.co2"];

/// 后台读存档的结果：Ok(Some((格子, 名字))) = 找到七道都反转的角色
type Found = Result<Option<(usize, String)>, String>;

#[derive(Default)]
struct St {
    who: Option<(i32, String)>,
    rx: Option<Receiver<Found>>,
    /// 上一帧是按周目数点亮的（周目数变回 0 = 换了角色，重新照存档判断）
    by_ng: bool,
    /// 记过日志的（角色, 周目数）：同一个只记一次
    ng_logged: Option<((i32, String), u32)>,
}

static ST: Mutex<Option<St>> = Mutex::new(None);

/// 现在这个角色的周目数（0 = 一周目）；读不到、数值不像周目数就是 None
fn ng_level() -> Option<u32> {
    let n = unsafe { GameDataMan::instance() }.ok()?.ng_lvl;
    (n <= NG_MAX).then_some(n)
}

pub fn tick() {
    let Some((flag, need, regions)) = crate::curses::unlock_def() else { return };
    let cur = crate::who::confirmed();
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    let st = g.get_or_insert_with(St::default);
    // 二周目以后：每帧看一眼，unlock 灭着就点亮（进下一周目时游戏清掉了它），不读存档
    if let Some((who, ng)) = cur.clone().zip(ng_level().filter(|&n| n >= 1)) {
        st.who = cur;
        st.rx = None;
        st.by_ng = true;
        if flag_get(flag) != Some(true) {
            flag_set(flag, true);
            if st.ng_logged.as_ref() != Some(&(who.clone(), ng)) {
                log(&format!("存档解锁：格子 {}「{}」在第 {} 周目（上一周目打通了，黑剑已经击败过），进「死亡」以上不用先击败黑剑", who.0, who.1, ng + 1));
                st.ng_logged = Some((who, ng));
            }
        }
        return;
    }
    if std::mem::take(&mut st.by_ng) {
        st.who = None;
    }
    if cur != st.who {
        st.who = cur.clone();
        st.rx = None;
        let Some(who) = cur else { return };
        if crate::curses::all_reversed() {
            flag_set(flag, true);
            log(&format!("存档解锁：格子 {}「{}」自己七道咒痕都反转了，进「死亡」以上不用先击败黑剑", who.0, who.1));
            return;
        }
        let Some(holders) = holders(&regions) else {
            flag_set(flag, false);
            log("存档解锁：游戏里找不到咒痕碎片所在标记块的位置，不读存档，这个角色进「死亡」以上照旧要先击败黑剑");
            return;
        };
        let (tx, rx) = mpsc::channel();
        let coop = crate::coop::ersc_loaded();
        std::thread::spawn(move || {
            let _ = tx.send(scan(&who, coop, &holders, need, &regions));
        });
        st.rx = Some(rx);
        return;
    }
    let Some(rx) = &st.rx else { return };
    let res = match rx.try_recv() {
        Ok(r) => r,
        Err(TryRecvError::Empty) => return,
        Err(TryRecvError::Disconnected) => Err("读存档的线程出错".into()),
    };
    st.rx = None;
    let who = st.who.clone().unwrap_or_default();
    match res {
        Ok(Some((slot, name))) => {
            flag_set(flag, true);
            log(&format!("存档解锁：存档里格子 {slot}「{name}」七道咒痕都反转了 → 格子 {}「{}」进「死亡」以上不用先击败黑剑", who.0, who.1));
        }
        Ok(None) => {
            flag_set(flag, false);
            log(&format!("存档解锁：存档里没有七道咒痕都反转的角色，格子 {}「{}」进「死亡」以上要先击败黑剑", who.0, who.1));
        }
        Err(e) => {
            flag_set(flag, false);
            log(&format!("存档解锁：{e}，格子 {}「{}」进「死亡」以上照旧要先击败黑剑", who.0, who.1));
        }
    }
}

/// 碎片标记所在的块 → 在标记数组（= 存档里的标记表）里的位置；有一个块不在数组里就是 None
fn holders(regions: &[Vec<u32>]) -> Option<HashMap<u32, u32>> {
    let m = unsafe { CSEventFlagMan::instance() }.ok()?;
    let vm = &m.virtual_memory_flag;
    if vm.event_flag_divisor != 1000 || vm.event_flag_holder_size as usize != BLOCK {
        return None;
    }
    let mut out = HashMap::new();
    for f in regions.iter().flatten() {
        let b = f / 1000;
        if let std::collections::hash_map::Entry::Vacant(e) = out.entry(b) {
            e.insert(vm.holder_index(b)?);
        }
    }
    Some(out)
}

fn scan(who: &(i32, String), coop: bool, holders: &HashMap<u32, u32>, need: u32, regions: &[Vec<u32>]) -> Found {
    let names: &[&str] = if coop { &COOP } else { &SINGLE };
    let root = std::env::var_os("APPDATA").map(|a| PathBuf::from(a).join("EldenRing")).ok_or("没有 APPDATA")?;
    let mut files = Vec::new();
    for e in fs::read_dir(&root).map_err(|_| format!("读不了 {}", root.display()))?.flatten() {
        if !e.file_name().to_string_lossy().bytes().all(|c| c.is_ascii_digit()) {
            continue;
        }
        if let Some(p) = names.iter().map(|n| e.path().join(n)).find(|p| p.is_file()) {
            files.push(p);
        }
    }
    if files.is_empty() {
        return Err(format!("{} 下面没有存档文件 {}", root.display(), names[0]));
    }
    let mut best: Option<(u8, SystemTime, PathBuf, Vec<u8>)> = None;
    for p in files {
        let Ok(raw) = fs::read(&p) else { continue };
        let Some(ents) = bnd_entries(&raw) else { continue };
        let Some(sum) = ents.get(10).and_then(|e| summary(e)) else { continue };
        let score = if sum.iter().any(|(k, n)| *k as i32 == who.0 && *n == who.1) { 2 } else { u8::from(sum.iter().any(|(_, n)| *n == who.1)) };
        let mtime = fs::metadata(&p).and_then(|m| m.modified()).unwrap_or(SystemTime::UNIX_EPOCH);
        if best.as_ref().is_none_or(|b| (score, mtime) > (b.0, b.1)) {
            best = Some((score, mtime, p, raw));
        }
    }
    let (_, _, path, raw) = best.ok_or("存档文件都读不了")?;
    find(&raw, holders, need, regions).map_err(|e| format!("{}：{e}", path.display()))
}

/// 一个存档文件里第一个七道咒痕都反转了的角色（格子, 名字）
fn find(raw: &[u8], holders: &HashMap<u32, u32>, need: u32, regions: &[Vec<u32>]) -> Result<Option<(usize, String)>, String> {
    let ents = bnd_entries(raw).ok_or("不是 BND4 存档")?;
    let sum = ents.get(10).and_then(|e| summary(e)).ok_or("没有角色摘要")?;
    let mut missed = 0;
    for (k, name) in sum {
        let Some(body) = ents.get(k).and_then(|e| e.get(16..)) else { continue };
        let Some(ef) = flags_start(body) else {
            missed += 1;
            continue;
        };
        let all = regions.iter().all(|r| {
            let v = r.iter().enumerate().fold(0u32, |v, (i, &f)| v | (u32::from(flag_at(body, ef, holders, f) == Some(true)) << i));
            v >= need
        });
        if all {
            return Ok(Some((k, name)));
        }
    }
    if missed > 0 {
        log(&format!("存档解锁：{missed} 个格子里找不到事件标记表，没算"));
    }
    Ok(None)
}

fn u32_at(d: &[u8], o: usize) -> Option<u32> {
    Some(u32::from_le_bytes(d.get(o..o.checked_add(4)?)?.try_into().ok()?))
}

/// BND4 的各项（按顺序；存档里第 0~9 项是格子 USER_DATA000~009，第 10 项是摘要 USER_DATA010）
fn bnd_entries(d: &[u8]) -> Option<Vec<&[u8]>> {
    if d.get(..4)? != b"BND4" {
        return None;
    }
    let n = u32_at(d, 0x0C)? as usize;
    if n > 64 {
        return None;
    }
    (0..n)
        .map(|i| {
            let o = 0x40 + i * 0x20;
            let size = u64::from_le_bytes(d.get(o + 8..o + 16)?.try_into().ok()?) as usize;
            let off = u32_at(d, o + 0x10)? as usize;
            d.get(off..off.checked_add(size)?)
        })
        .collect()
}

/// 摘要里在用的格子：[(格子, 名字)]
fn summary(ent: &[u8]) -> Option<Vec<(usize, String)>> {
    let u = ent.get(16..)?;
    let mut out = Vec::new();
    for i in 0..10 {
        if *u.get(SUMMARY_ON + i)? == 0 {
            continue;
        }
        let b = SUMMARY_NAME + i * SUMMARY_STEP;
        let w: Vec<u16> = u.get(b..b + 32)?.chunks_exact(2).map(|c| u16::from_le_bytes([c[0], c[1]])).take_while(|&c| c != 0).collect();
        out.push((i, String::from_utf16_lossy(&w)));
    }
    Some(out)
}

fn chain_ok(body: &[u8], mut pos: usize) -> bool {
    for k in 0..5 {
        let Some(size) = u32_at(body, pos).map(|s| s as i32) else { return false };
        if !(0..=0x8000).contains(&size) || (k == 0 && size < 4) {
            return false;
        }
        if (1..=3).contains(&k) && body.get(pos + 4..pos + 8) != Some(&MAGICS[k - 1][..]) {
            return false;
        }
        pos += 4 + size as usize;
    }
    true
}

/// 格子数据（去掉 MD5）里事件标记表的开头
fn flags_start(body: &[u8]) -> Option<usize> {
    let mut from = 0;
    while let Some(c) = body.get(from..)?.windows(4).position(|w| w == MAGICS[0]).map(|p| p + from) {
        from = c + 1;
        let Some(pos1) = c.checked_sub(4) else { continue };
        for size0 in 4..0x8000usize {
            let Some(pos0) = pos1.checked_sub(4 + size0) else { break };
            if pos0 < EF_SIZE + 1 {
                break;
            }
            if u32_at(body, pos0) == Some(size0 as u32) && chain_ok(body, pos0) {
                return Some(pos0 - 1 - EF_SIZE);
            }
        }
    }
    None
}

fn flag_at(body: &[u8], ef: usize, holders: &HashMap<u32, u32>, n: u32) -> Option<bool> {
    let h = *holders.get(&(n / 1000))? as usize;
    let idx = (n % 1000) as usize;
    if (h + 1) * BLOCK > EF_SIZE {
        return None;
    }
    body.get(ef + h * BLOCK + idx / 8).map(|b| (b >> (7 - idx % 8)) & 1 == 1)
}

/// 测试用：读一个存档文件（不在游戏里，块位置照 dev\event_flags 的存档读法：93 → 43、92 → 42）
#[cfg(test)]
fn find_in(path: &std::path::Path, regions: &[Vec<u32>]) -> Result<Option<(usize, String)>, String> {
    let raw = fs::read(path).map_err(|e| e.to_string())?;
    find(&raw, &HashMap::from([(93, 43), (92, 42)]), 5, regions)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 周目数在 GameDataMan 里的位置（vendored 定义；两个 exe 里读它的代码核对过，见 NG_LVL_AT）
    #[test]
    fn ng_lvl_offset() {
        assert_eq!(std::mem::offset_of!(GameDataMan, ng_lvl), NG_LVL_AT);
    }

    fn regions() -> Vec<Vec<u32>> {
        let f: Vec<u32> = (93993..94000).chain(92582..92596).collect();
        f.chunks(3).map(|c| c.to_vec()).collect()
    }

    /// 造一个格子：标记表在 ef，后面 5 个世界结构；按 flags 点亮
    fn slot(ef: usize, lit: &[u32]) -> Vec<u8> {
        let mut b = vec![0u8; ef + EF_SIZE + 1];
        for &n in lit {
            let h = match n / 1000 {
                93 => 43,
                92 => 42,
                _ => unreachable!(),
            };
            let idx = (n % 1000) as usize;
            b[ef + h * BLOCK + idx / 8] |= 1 << (7 - idx % 8);
        }
        for (k, size) in [(0usize, 8u32), (1, 12), (2, 12), (3, 12), (4, 6)] {
            b.extend_from_slice(&size.to_le_bytes());
            let mut s = vec![0u8; size as usize];
            if (1..=3).contains(&k) {
                s[..4].copy_from_slice(MAGICS[k - 1]);
            }
            b.extend_from_slice(&s);
        }
        let mut out = vec![0u8; 16];
        out.extend_from_slice(&b);
        out
    }

    fn save(slots: &[(usize, &str, Vec<u8>)]) -> Vec<u8> {
        let mut sum = vec![0u8; 16 + SUMMARY_NAME + 10 * SUMMARY_STEP];
        for (k, name, _) in slots {
            sum[16 + SUMMARY_ON + k] = 1;
            for (i, c) in name.encode_utf16().enumerate() {
                sum[16 + SUMMARY_NAME + k * SUMMARY_STEP + i * 2..][..2].copy_from_slice(&c.to_le_bytes());
            }
        }
        let mut ents: Vec<Vec<u8>> = (0..10).map(|k| slots.iter().find(|s| s.0 == k).map_or(vec![0u8; 32], |s| s.2.clone())).collect();
        ents.push(sum);
        let mut d = vec![0u8; 0x40 + ents.len() * 0x20];
        d[..4].copy_from_slice(b"BND4");
        d[0x0C..0x10].copy_from_slice(&(ents.len() as u32).to_le_bytes());
        for (i, e) in ents.iter().enumerate() {
            let off = d.len();
            let o = 0x40 + i * 0x20;
            d[o + 8..o + 16].copy_from_slice(&(e.len() as u64).to_le_bytes());
            d[o + 0x10..o + 0x14].copy_from_slice(&(off as u32).to_le_bytes());
            d.extend_from_slice(e);
        }
        d
    }

    /// 七个区域都是 5（101）才算；差一个区域不算；摘要里没在用的格子不看
    #[test]
    fn finds_reversed_character() {
        let r = regions();
        let five: Vec<u32> = r.iter().flat_map(|g| [g[0], g[2]]).collect();
        let h = HashMap::from([(93, 43), (92, 42)]);
        let d = save(&[(0, "A", slot(0x3000, &[])), (3, "D", slot(0x37ef, &five))]);
        assert_eq!(find(&d, &h, 5, &r), Ok(Some((3, "D".into()))));
        let four: Vec<u32> = five.iter().copied().filter(|&f| f != r[6][2]).collect();
        let d = save(&[(3, "D", slot(0x37ef, &four))]);
        assert_eq!(find(&d, &h, 5, &r), Ok(None));
        let mut d = save(&[(3, "D", slot(0x37ef, &five))]);
        let sum_off = u32_at(&d, 0x40 + 10 * 0x20 + 0x10).unwrap() as usize;
        d[sum_off + 16 + SUMMARY_ON + 3] = 0;
        assert_eq!(find(&d, &h, 5, &r), Ok(None), "删掉的角色不算");
        assert!(find(b"nope", &h, 5, &r).is_err());
    }

    /// 本机的存档副本（有就读，没有跳过）：DARKFORGE_SAVE_COPY 指向一份 ER0000.rng 副本，DARKFORGE_SAVE_EXPECT 是七道都反转的格子号（没有写 none）
    #[test]
    fn real_save_copy() {
        let (Some(p), Some(want)) = (std::env::var_os("DARKFORGE_SAVE_COPY"), std::env::var_os("DARKFORGE_SAVE_EXPECT")) else { return };
        let got = find_in(std::path::Path::new(&p), &regions()).unwrap().map(|(k, _)| k.to_string()).unwrap_or_else(|| "none".into());
        assert_eq!(got, want.to_string_lossy());
    }
}
