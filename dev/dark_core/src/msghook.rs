//! 游戏取文字的函数挂钩（MsgRepositoryImp 查条目；用户 2026-11-18「直接改成挂钩」）。
//!
//! 以前（gear.rs 的 scan）扫整个进程的可读写内存找文字占位、原地改写。扫到的大多是临时副本（确认框占位一次 741 处，
//! 装备文字的副本有时上万份），确认框第一次写只核对开头 4 个字就整段写进去：那块内存要是已经被游戏释放、分给了别的东西，
//! 就把游戏的堆写坏了（两位玩家 2026-11-18 的崩溃里，坏掉的指针是 UTF-16 的「稀有 0」「有 1 」，正是定向鉴定确认框那行字；
//! 崩溃诊断 20261118_233705 / 20261118_222251）。现在不写游戏的内存，游戏取到占位文字时换成我们的：
//! - 整条是装备 / 骨灰容器的占位「#DRC<编号>#<N/I/C> <说明>」（名字、简介、说明）：返回我们自己的定长缓冲
//!   （cap 个字 + 结尾 0；改文字就地写，地址不变；一直不释放），语言按占位里的说明认；
//! - 文字里有确认框占位「〔#I<种类> …〕」/「[#I<种类> …]」（dark_core 写的件数、余额、送给队友……）或 dark_sell 的「#S<序号>」：
//!   返回把这几段换好的副本（按原文地址缓存，原文变了重拼；拼过的不释放，游戏可能还拿着旧的地址）；
//! - 幻化插件的赐福菜单项（文字类别 33、69000000）：前面加图标（以前的 transmogicon.rs，用户 2026-11-10）。
//!
//! 挂法：函数开头 5 字节（cmp edx,[rcx+10h] / jae 短跳）改成 jmp 到旁边申请的中转。开头已经被别的 mod 挂成 jmp（幻化插件等用
//! MinHook）就接在它前面；还是原样的话，跳板里放 cmp、改成长跳的 jae、跳回第 5 字节（以后 MinHook 也能把我们的 jmp 搬进它的跳板）。
//! 幻化插件在 YAFSML 的 DLL 列表里比我们靠后（晚约 1 秒加载）：先等它挂好再挂，不和它同时改同一处；没装插件就自己挂。

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU16, AtomicU32, AtomicUsize, Ordering};
use std::sync::{LazyLock, RwLock};
use std::time::{Duration, Instant};

use windows::Win32::System::Diagnostics::Debug::FlushInstructionCache;
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Memory::{PAGE_EXECUTE_READWRITE, PAGE_PROTECTION_FLAGS, VirtualProtect};
use windows::Win32::System::Threading::GetCurrentProcess;
use windows::core::w;

use crate::log;
use crate::pickup::{alloc_near, write_abs_jmp};

/// 幻化插件的「幻化防具」（赐福菜单那一项）：对话文字（类别 33）69000000，插件自己返回的字符串
const TALK_BND: u32 = 33;
const TRANSMOG_TEXT: i32 = 69_000_000;
/// 和 gracelook.py 的 ICON % ours('MENU_FL_Armor_40171') 一样
const TRANSMOG_PREFIX: &str = "<img src='img://MENU_DR_FL_Armor_40171.png' height='36' width='36' vspace='-18'/> ";
/// 特征码：后面紧跟的 call rel32 的目标就是查条目的函数（插件找的也是这个；游戏里有两处，都 call 同一个）
const AOB: [u8; 14] = [0x8B, 0xDA, 0x44, 0x8B, 0xCA, 0x33, 0xD2, 0x48, 0x8B, 0xF9, 0x44, 0x8D, 0x42, 0x6F];
/// 函数开头（两个游戏版本一样）：cmp edx,[rcx+10h]；jae +29h（去 +2Eh 的 xor eax,eax / ret）
const HEAD: [u8; 5] = [0x3B, 0x51, 0x10, 0x73, 0x29];
/// 第 5 字节起到 +29h 的 jmp 操作码（按版本 / 文字包号取表、取文字表，最后 jmp 到文字表的查找）：核对是不是这个函数
const BODY: [u8; 37] = [
    0x44, 0x3B, 0x41, 0x14, 0x73, 0x23, 0x48, 0x8B, 0x41, 0x08, 0x8B, 0xD2, 0x48, 0x8B, 0x0C, 0xD0, 0x48, 0x85, 0xC9, 0x74, 0x14, 0x41,
    0x8B, 0xC0, 0x48, 0x8B, 0x0C, 0xC1, 0x48, 0x85, 0xC9, 0x74, 0x08, 0x41, 0x8B, 0xD1, 0xE9,
];
/// +2Eh：查不到时 xor eax,eax / ret
const TAIL: [u8; 3] = [0x33, 0xC0, 0xC3];
/// 原文最多看这么多字（游戏里最长的是教程、载入提示，不到 2000 字）
const MAX_LEN: usize = 8192;
/// 确认框占位：左括号后面这么多字以内要有右括号
const MAX_FIELD: usize = 96;
/// 装备文字占位的开头、三个字段（名字 / 简介 / 说明；同 gear.rs 的 FIELDS）
const HOLE: [u16; 4] = [b'#' as u16, b'D' as u16, b'R' as u16, b'C' as u16];
const FIELDS: [u16; 3] = [b'N' as u16, b'I' as u16, b'C' as u16];
const ZH_OPEN: u16 = 0x3014;
const ZH_CLOSE: u16 = 0x3015;

type LookupFn = unsafe extern "C" fn(usize, u32, u32, i32) -> *const u16;

/// 钩子往下走的地址（跳板：原来的开头 + 跳回，或者接着跳到先挂的 mod）；0 = 还没挂
static NEXT: AtomicUsize = AtomicUsize::new(0);
static HOOKED: AtomicBool = AtomicBool::new(false);
/// 游戏取到的装备文字占位是哪种语言的（0 中文 / 1 英文），各几次（装备工坊按多的那种显示）
static LANG_SEEN: [AtomicU32; 2] = [AtomicU32::new(0), AtomicU32::new(0)];

/// 一条装备文字：cap 个字 + 结尾 0，游戏拿到的是它的地址，改文字就地写；一直不释放
type Buf = &'static [AtomicU16];

#[derive(Default)]
struct Store {
    /// 占位里的说明（items.txt 的 label 行，[中文, 英文]）：认占位是哪种语言的
    labels: [Vec<u16>; 2],
    /// (编号, 字段 0~2) → 各语言的文字
    items: HashMap<(u32, u8), [Option<Buf>; 2]>,
    /// 确认框：(记号 I / S, 种类) → [中文, 英文]
    confirm: HashMap<(u8, u8), [Vec<u16>; 2]>,
    /// 确认框文字改过几次（拼好的副本对得上这个数才直接用）
    rev: u64,
    /// 带确认框占位的原文（地址）→ 拼好的
    composed: HashMap<usize, Composed>,
    /// 幻化插件返回的地址 → 加了图标的副本
    transmog: HashMap<usize, &'static [u16]>,
}

struct Composed {
    /// 拼的时候原文是什么（同一地址换了文字就重拼）
    orig: Vec<u16>,
    rev: u64,
    /// None = 没有可换的（这几种还没有文字），照原文
    out: Option<&'static [u16]>,
}

static STORE: LazyLock<RwLock<Store>> = LazyLock::new(|| RwLock::new(Store::default()));

fn read() -> std::sync::RwLockReadGuard<'static, Store> {
    STORE.read().unwrap_or_else(|e| e.into_inner())
}

fn write() -> std::sync::RwLockWriteGuard<'static, Store> {
    STORE.write().unwrap_or_else(|e| e.into_inner())
}

// ------------------------------------------------------------------ 给别的模块用
/// 占位里的说明（[中文, 英文]）：items.txt 读进来时交过来
pub(crate) fn set_labels(labels: &[String; 2]) {
    let l = [labels[0].encode_utf16().collect::<Vec<u16>>(), labels[1].encode_utf16().collect()];
    let mut s = write();
    if s.labels != l {
        s.labels = l;
    }
}

/// 一条装备文字（编号, 字段, 语言）：text 是 cap 个字（短的后面补 0）。地址不变：同一条以后就地改
pub(crate) fn set_item(id: u32, field: u8, lang: usize, text: &[u16]) {
    let lang = lang.min(1);
    if let Some(b) = read().items.get(&(id, field)).and_then(|v| v[lang]).filter(|b| b.len() == text.len() + 1) {
        fill(b, text);
        return;
    }
    let mut s = write();
    let e = s.items.entry((id, field)).or_insert([None, None]);
    match e[lang] {
        Some(b) if b.len() == text.len() + 1 => fill(b, text),
        _ => {
            let b: Buf = Box::leak((0..=text.len()).map(|_| AtomicU16::new(0)).collect::<Vec<_>>().into_boxed_slice());
            fill(b, text);
            e[lang] = Some(b);
        }
    }
}

/// 就地写（别的线程这时正好在读的话，最多读到一半新一半旧；最后一格一直是 0，不会读出界）
fn fill(b: Buf, text: &[u16]) {
    let n = b.len() - 1;
    for (i, c) in b[..n].iter().enumerate() {
        c.store(text.get(i).copied().unwrap_or(0), Ordering::Relaxed);
    }
    b[n].store(0, Ordering::Release);
}

/// 确认框占位（记号 b'I' / b'S'，种类）的文字；和上次一样就不动
pub(crate) fn set_confirm(marker: u8, kind: u8, zh: &[u16], en: &[u16]) {
    let v = [zh.to_vec(), en.to_vec()];
    if read().confirm.get(&(marker, kind)) == Some(&v) {
        return;
    }
    let mut s = write();
    s.confirm.insert((marker, kind), v);
    s.rev += 1;
}

/// dark_sell 交过来的确认框文字（一键出售的预计件数 / 卢恩，占位 #S<序号>）：它每半秒算一次，变了才调
///
/// # Safety
/// zh / en 指向 zh_len / en_len 个 UTF-16 字（dark_sell 调用）
#[unsafe(no_mangle)]
pub unsafe extern "C" fn dr_msg_confirm(marker: u8, kind: u8, zh: *const u16, zh_len: usize, en: *const u16, en_len: usize) {
    if zh.is_null() || en.is_null() || zh_len > 512 || en_len > 512 || !matches!(marker, b'I' | b'S') {
        return;
    }
    let (zh, en) = unsafe { (std::slice::from_raw_parts(zh, zh_len), std::slice::from_raw_parts(en, en_len)) };
    set_confirm(marker, kind, zh, en);
}

/// 游戏语言：取到的装备文字占位多数是哪种（0 中文 / 1 英文；还没取到过算中文）
pub(crate) fn ui_lang() -> usize {
    (LANG_SEEN[1].load(Ordering::Relaxed) > LANG_SEEN[0].load(Ordering::Relaxed)) as usize
}

/// 钩子挂上了没有（没挂上时装备名字、说明、确认框显示占位里的提示）
#[allow(dead_code)]
pub(crate) fn hooked() -> bool {
    HOOKED.load(Ordering::Relaxed)
}

// ------------------------------------------------------------------ 认占位、拼文字
/// 「#DRC<编号>#<N/I/C> <说明>」→ (编号, 字段, 语言)
fn parse_hole(text: &[u16], labels: &[Vec<u16>; 2]) -> Option<(u32, u8, usize)> {
    let rest = text.strip_prefix(&HOLE)?;
    let n = rest.iter().take_while(|&&c| (b'0' as u16..=b'9' as u16).contains(&c)).count();
    if n == 0 || n > 10 {
        return None;
    }
    let id = rest[..n].iter().try_fold(0u32, |v, &c| v.checked_mul(10)?.checked_add((c - b'0' as u16) as u32))?;
    let rest = &rest[n..];
    if rest.first() != Some(&(b'#' as u16)) || rest.get(2) != Some(&(b' ' as u16)) {
        return None;
    }
    let field = FIELDS.iter().position(|&f| rest.get(1) == Some(&f))? as u8;
    let tail = &rest[3..];
    let lang = labels.iter().position(|l| !l.is_empty() && tail.starts_with(l))?;
    Some((id, field, lang))
}

/// i 处是不是确认框占位的左括号：「〔#I7 …〕」「[#SA …]」……→ (右括号的位置, (记号, 种类), 是不是中文)。
/// #I 的种类 0~9、A~Z（10~35；H 起给斗技场的无尽试炼，arena.rs），#S 的序号也是 0~9、A~Z（dark_sell：背包 0~B、木箱 C~N）
fn marker_at(text: &[u16], i: usize) -> Option<(usize, (u8, u8), bool)> {
    let open = text[i];
    let zh = open == ZH_OPEN;
    if !zh && open != b'[' as u16 {
        return None;
    }
    if text.get(i + 1) != Some(&(b'#' as u16)) || text.get(i + 4) != Some(&(b' ' as u16)) {
        return None;
    }
    let marker = u8::try_from(*text.get(i + 2)?).ok().filter(|m| matches!(m, b'I' | b'S'))?;
    let k = u8::try_from(*text.get(i + 3)?).ok()?;
    let kind = match (marker, k) {
        (_, b'0'..=b'9') => k - b'0',
        (_, b'A'..=b'Z') => k - b'A' + 10,
        _ => return None,
    };
    let close = if zh { ZH_CLOSE } else { b']' as u16 };
    let end = text[i + 1..].iter().take(MAX_FIELD).position(|&c| c == close)? + i + 1;
    Some((end, (marker, kind), zh))
}

fn has_marker(text: &[u16]) -> bool {
    (0..text.len()).any(|i| marker_at(text, i).is_some())
}

/// 原文里的确认框占位整段（括号、记号都不留）换成这一种的文字；还没有文字的那种照原样
fn compose(text: &[u16], confirm: &HashMap<(u8, u8), [Vec<u16>; 2]>) -> Vec<u16> {
    let mut out = Vec::with_capacity(text.len() + 16);
    let mut i = 0;
    while i < text.len() {
        if let Some((end, key, zh)) = marker_at(text, i) {
            if let Some(t) = confirm.get(&key) {
                out.extend_from_slice(&t[if zh { 0 } else { 1 }]);
                i = end + 1;
                continue;
            }
        }
        out.push(text[i]);
        i += 1;
    }
    out
}

/// p 开头的字符串（到结尾 0，最多 MAX_LEN 个字）
unsafe fn cstr<'a>(p: *const u16) -> &'a [u16] {
    let mut n = 0;
    while n < MAX_LEN && unsafe { *p.add(n) } != 0 {
        n += 1;
    }
    unsafe { std::slice::from_raw_parts(p, n) }
}

fn leak(mut v: Vec<u16>) -> &'static [u16] {
    v.push(0);
    Box::leak(v.into_boxed_slice())
}

fn item(p: *const u16, text: &[u16]) -> *const u16 {
    let s = read();
    let Some((id, field, lang)) = parse_hole(text, &s.labels) else { return p };
    LANG_SEEN[lang].fetch_add(1, Ordering::Relaxed);
    s.items.get(&(id, field)).and_then(|v| v[lang]).map_or(p, |b| b.as_ptr() as *const u16)
}

fn confirm(p: *const u16, text: &[u16]) -> *const u16 {
    let key = p as usize;
    let hit = |s: &Store| s.composed.get(&key).filter(|c| c.rev == s.rev && c.orig == text).map(|c| c.out.map_or(p, |o| o.as_ptr()));
    if let Some(r) = hit(&read()) {
        return r;
    }
    let mut s = write();
    if let Some(r) = hit(&s) {
        return r;
    }
    let rev = s.rev;
    let out = compose(text, &s.confirm);
    if let Some(c) = s.composed.get_mut(&key).filter(|c| c.orig == text) {
        // 换出来和上次一样：沿用上次那份
        let same = match c.out {
            Some(o) => o[..o.len() - 1] == out[..],
            None => out == text,
        };
        if same {
            c.rev = rev;
            return c.out.map_or(p, |o| o.as_ptr());
        }
    }
    let out = if out == text { None } else { Some(leak(out)) };
    s.composed.insert(key, Composed { orig: text.to_vec(), rev, out });
    out.map_or(p, |o| o.as_ptr())
}

fn transmog(p: *const u16, text: &[u16]) -> *const u16 {
    if let Some(s) = read().transmog.get(&(p as usize)) {
        return s.as_ptr();
    }
    let mut s = write();
    let v: Vec<u16> = TRANSMOG_PREFIX.encode_utf16().chain(text.iter().copied()).collect();
    let out = *s.transmog.entry(p as usize).or_insert_with(|| leak(v));
    out.as_ptr()
}

/// 往下走拿到的原文 p：要换就返回换好的
unsafe fn swap(p: *const u16, bnd: u32, id: i32) -> *const u16 {
    let text = unsafe { cstr(p) };
    if bnd == TALK_BND && id == TRANSMOG_TEXT {
        return transmog(p, text);
    }
    if text.starts_with(&HOLE) {
        return item(p, text);
    }
    if has_marker(text) {
        return confirm(p, text);
    }
    p
}

unsafe extern "C" fn detour(repo: usize, ver: u32, bnd: u32, id: i32) -> *const u16 {
    let next: LookupFn = unsafe { std::mem::transmute(NEXT.load(Ordering::Relaxed)) };
    let p = unsafe { next(repo, ver, bnd, id) };
    if p.is_null() {
        return p;
    }
    // 出错（不该有）就照原文：panic 不能跑出这个函数
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| unsafe { swap(p, bnd, id) })).unwrap_or(p)
}

// ------------------------------------------------------------------ 挂钩
/// 特征码在游戏里有两处，都 call 同一个函数：所有命中的目标一致才用
fn target() -> Result<usize, String> {
    let base = unsafe { GetModuleHandleW(None) }.map_err(|e| format!("取模块基址：{e}"))?.0 as usize;
    let mut found: Option<usize> = None;
    unsafe {
        let pe = base + *((base + 0x3C) as *const u32) as usize;
        let nsec = *((pe + 6) as *const u16) as usize;
        let opt = *((pe + 20) as *const u16) as usize;
        for k in 0..nsec {
            let sh = pe + 24 + opt + 40 * k;
            if *((sh + 36) as *const u32) & 0x2000_0000 == 0 {
                continue;
            }
            let va = base + *((sh + 12) as *const u32) as usize;
            let size = *((sh + 8) as *const u32) as usize;
            let mem = std::slice::from_raw_parts(va as *const u8, size);
            for i in memchr::memmem::find_iter(mem, &AOB) {
                let at = i + AOB.len();
                if at + 5 > size || mem[at] != 0xE8 {
                    return Err("特征码后面不是 call".into());
                }
                let rel = i32::from_le_bytes([mem[at + 1], mem[at + 2], mem[at + 3], mem[at + 4]]);
                let t = (va + at + 5).wrapping_add_signed(rel as isize);
                match found {
                    Some(f) if f != t => return Err("几处命中 call 的函数不一样".into()),
                    _ => found = Some(t),
                }
            }
        }
    }
    found.ok_or_else(|| "没找到".into())
}

/// 核对函数内容：Ok(true) = 开头已经被别的 mod 挂成 jmp，Ok(false) = 原样
fn check(t: usize) -> Result<bool, String> {
    let b = unsafe { std::slice::from_raw_parts(t as *const u8, 0x31) };
    if b[5..0x2A] != BODY || b[0x2E..0x31] != TAIL {
        return Err("函数内容对不上（游戏版本不对？）".into());
    }
    if b[..5] == HEAD {
        Ok(false)
    } else if b[0] == 0xE9 {
        Ok(true)
    } else {
        Err(format!("开头被改成了认不出的样子（{:02X?}）", &b[..5]))
    }
}

fn head8(t: usize) -> u64 {
    unsafe { (t as *const u64).read_volatile() }
}

/// 挂上：返回是原样挂的还是接在别的 mod 前面
fn install(t: usize) -> Result<&'static str, String> {
    if NEXT.load(Ordering::SeqCst) != 0 {
        return Err("已经挂过".into());
    }
    let hooked = check(t)?;
    let block = alloc_near(t).ok_or("函数附近申请不到内存")?;
    let head = head8(t).to_le_bytes();
    unsafe {
        // [0..14) 中转：跳到钩子；[16..) 跳板：钩子往下走
        write_abs_jmp(block, detour as *const () as usize);
        let tramp = block + 16;
        if hooked {
            let rel = i32::from_le_bytes([head[1], head[2], head[3], head[4]]);
            write_abs_jmp(tramp, (t + 5).wrapping_add_signed(rel as isize));
        } else {
            // cmp edx,[rcx+10h]（3 字节，原样）；jae rel32 → +23 的长跳（原来短跳的去处 t+2Eh）；不跳就去 +9 的长跳回 t+5
            let p = tramp as *mut u8;
            std::ptr::copy_nonoverlapping(head.as_ptr(), p, 3);
            std::ptr::copy_nonoverlapping([0x0F, 0x83].as_ptr(), p.add(3), 2);
            (p.add(5) as *mut i32).write_unaligned(14);
            write_abs_jmp(tramp + 9, t + 5);
            write_abs_jmp(tramp + 23, (t + 5).wrapping_add_signed(head[4] as i8 as isize));
        }
        NEXT.store(tramp, Ordering::SeqCst);
        let rel = (block as isize - (t as isize + 5)) as i32;
        let mut new = head;
        new[0] = 0xE9;
        new[1..5].copy_from_slice(&rel.to_le_bytes());
        let mut old = PAGE_PROTECTION_FLAGS(0);
        if let Err(e) = VirtualProtect(t as *const _, 8, PAGE_EXECUTE_READWRITE, &mut old) {
            NEXT.store(0, Ordering::SeqCst);
            return Err(format!("改内存属性：{e}"));
        }
        // 函数开头 16 字节对齐：8 字节一次写完（别的线程不会看到写到一半的指令）
        std::sync::atomic::AtomicU64::from_ptr(t as *mut u64).store(u64::from_le_bytes(new), Ordering::SeqCst);
        let _ = VirtualProtect(t as *const _, 8, old, &mut old);
        let _ = FlushInstructionCache(GetCurrentProcess(), Some(t as *const _), 8);
    }
    HOOKED.store(true, Ordering::SeqCst);
    Ok(if hooked { "接在别的 mod 前面" } else { "原样" })
}

fn plugin_loaded() -> bool {
    unsafe { GetModuleHandleW(w!("ertransmogrify.dll")) }.is_ok()
}

/// 等 cond 成立（每 50 毫秒看一次，最多 limit）
fn wait(limit: Duration, cond: impl Fn() -> bool) -> bool {
    let t0 = Instant::now();
    while !cond() {
        if t0.elapsed() > limit {
            return false;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    true
}

/// 后台线程：找函数、等幻化插件挂好、挂上
pub fn start() {
    std::thread::spawn(|| {
        let t = match target().and_then(|t| check(t).map(|_| t)) {
            Ok(t) => t,
            Err(e) => {
                log(&format!("取文字挂钩：找不到取文字的函数（{e}），装备名字、说明和确认框会显示占位里的提示"));
                return;
            }
        };
        let head0 = head8(t);
        // 幻化插件加载后要过约 20 秒（游戏到标题画面前后）才挂这个函数（以前的日志：dark_core 加载后 18~27 秒）。
        // 它自己那一项（幻化菜单）直接返回、不往下走：我们得在它前面才能加图标，所以等它挂好再挂（最多 3 分钟）。
        // 2026-11-18 第一版只等 10 秒，先挂上了，插件后挂在我们前面，图标没了
        let note = if plugin_loaded() && head0.to_le_bytes()[0] == 0xE9 {
            "" // 插件已经加载、开头已经是 jmp：当它挂好了
        } else if plugin_loaded() || wait(Duration::from_secs(8), plugin_loaded) {
            let changed = wait(Duration::from_secs(180), || head8(t) != head0);
            std::thread::sleep(Duration::from_millis(300));
            if changed { "" } else { "；幻化插件 3 分钟内没挂上" }
        } else {
            "；没有幻化插件"
        };
        let base = unsafe { GetModuleHandleW(None) }.map(|h| h.0 as usize).unwrap_or(0);
        match install(t) {
            Ok(how) => log(&format!("取文字挂钩：已挂上（eldenring.exe+{:#x}，{how}{note}）", t - base)),
            Err(e) => log(&format!("取文字挂钩：挂不上（{e}），装备名字、说明和确认框会显示占位里的提示")),
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn u(s: &str) -> Vec<u16> {
        s.encode_utf16().collect()
    }

    fn labels() -> [Vec<u16>; 2] {
        [u("生成的装备（dark_core 没有改写）"), u("Generated gear (not rewritten)")]
    }

    #[test]
    fn parse_holes() {
        let l = labels();
        let mut t = u("#DRC240010000#N 生成的装备（dark_core 没有改写）");
        t.resize(t.len() + 20, b' ' as u16);
        assert_eq!(parse_hole(&t, &l), Some((240010000, 0, 0)));
        assert_eq!(parse_hole(&u("#DRC20001#C Generated gear (not rewritten)   "), &l), Some((20001, 2, 1)));
        assert_eq!(parse_hole(&u("#DRC20001#X Generated gear (not rewritten)"), &l), None, "字段不对");
        assert_eq!(parse_hole(&u("#DRC#N 生成的装备（dark_core 没有改写）"), &l), None, "没有编号");
        assert_eq!(parse_hole(&u("#DRC99999999999#N 生成的装备（dark_core 没有改写）"), &l), None, "编号太长");
        assert_eq!(parse_hole(&u("#DRC20001#N 别的说明"), &l), None, "说明对不上");
        assert_eq!(parse_hole(&u("#DRC20001#N 生成的装备"), &[Vec::new(), Vec::new()]), None, "还没交说明");
    }

    #[test]
    fn markers_and_compose() {
        let t = u("要鉴定吗？\n〔#I7 正在清点背包……      〕\n[#SA estimating...   ] 〔#IG 送给队友 5　　〕〔#IH x〕〔#I7 没有右括号");
        let at: Vec<_> = (0..t.len()).filter_map(|i| marker_at(&t, i).map(|(_, k, zh)| (k, zh))).collect();
        assert_eq!(at, vec![((b'I', 7), true), ((b'S', 10), false), ((b'I', 16), true), ((b'I', 17), true)], "H 起是无尽试炼的（17~35）、没有右括号的不算");
        assert_eq!(marker_at(&u("〔#IZ x〕"), 0).map(|m| m.1), Some((b'I', 35)));
        assert_eq!(marker_at(&u("[#SN x]"), 0).map(|m| m.1), Some((b'S', 23)), "#S 木箱的序号 C~N");
        assert_eq!(marker_at(&u("[#Sa x]"), 0), None, "小写不算");
        assert!(has_marker(&t) && !has_marker(&u("普通的文字 [x] 〔#I〕")));
        let mut c = HashMap::new();
        assert_eq!(compose(&t, &c), t, "还没有文字的照原样");
        c.insert((b'I', 7), [u("未鉴定武器：普通 1 稀有 0"), u("Unidentified: Common 1")]);
        c.insert((b'S', 10), [u("预计卖出 3 件"), u("Est. 3 items")]);
        let out = String::from_utf16(&compose(&t, &c)).unwrap();
        assert_eq!(out, "要鉴定吗？\n未鉴定武器：普通 1 稀有 0\nEst. 3 items 〔#IG 送给队友 5　　〕〔#IH x〕〔#I7 没有右括号");
    }

    #[test]
    fn item_buffers_keep_address() {
        set_item(4_000_000_001, 1, 0, &u("一二三\0\0\0"));
        let a = read().items[&(4_000_000_001, 1)][0].unwrap().as_ptr() as usize;
        set_item(4_000_000_001, 1, 0, &u("四五\0\0\0\0"));
        let b = read().items[&(4_000_000_001, 1)][0].unwrap();
        assert_eq!(b.as_ptr() as usize, a, "同一条就地改");
        let s: Vec<u16> = b.iter().map(|c| c.load(Ordering::Relaxed)).collect();
        assert_eq!(s, u("四五\0\0\0\0\0"));
    }

    // ---- 整个挂钩：照游戏的函数做一个假的（同样的字节，最后 jmp 到假的文字表查找），挂上以后调它
    #[repr(C)]
    struct FakeRepo {
        vt: usize,
        vers: *const *const usize,
        nver: u32,
        nbnd: u32,
    }

    const FAKE_FMG: usize = 0x5151;
    static STRS: LazyLock<Vec<Vec<u16>>> = LazyLock::new(|| {
        let mut hole = u("#DRC4000000002#N 生成的装备（dark_core 没有改写）");
        hole.resize(hole.len() + 12, b' ' as u16);
        [hole, u("普通的文字"), u("要鉴定吗？〔#I9 正在清点背包……    〕"), u("幻化防具")]
            .into_iter()
            .map(|mut v| {
                v.push(0);
                v
            })
            .collect()
    });

    unsafe extern "C" fn fake_fmg(fmg: usize, id: u32) -> *const u16 {
        assert_eq!(fmg, FAKE_FMG);
        match id {
            1..=3 => STRS[id as usize - 1].as_ptr(),
            69_000_000 => STRS[3].as_ptr(),
            _ => std::ptr::null(),
        }
    }

    fn text_at(p: *const u16) -> String {
        String::from_utf16_lossy(unsafe { cstr(p) })
    }

    #[test]
    fn hook_fake_lookup() {
        let page = alloc_near(fake_fmg as *const () as usize).expect("申请可执行内存");
        unsafe {
            let p = page as *mut u8;
            std::ptr::copy_nonoverlapping(HEAD.as_ptr(), p, 5);
            std::ptr::copy_nonoverlapping(BODY.as_ptr(), p.add(5), BODY.len());
            (p.add(0x2A) as *mut i32).write_unaligned(0x40 - 0x2E); // jmp → +40h 的长跳 → fake_fmg
            std::ptr::copy_nonoverlapping(TAIL.as_ptr(), p.add(0x2E), 3);
            write_abs_jmp(page + 0x40, fake_fmg as *const () as usize);
        }
        let mut bnds = vec![0usize; 40];
        bnds[10] = FAKE_FMG;
        bnds[TALK_BND as usize] = FAKE_FMG;
        let vers = [bnds.as_ptr()];
        let repo = FakeRepo { vt: 0, vers: vers.as_ptr(), nver: 1, nbnd: bnds.len() as u32 };
        let r = &repo as *const FakeRepo as usize;
        let f: LookupFn = unsafe { std::mem::transmute(page) };
        let call = |ver, bnd, id| unsafe { f(r, ver, bnd, id) };
        assert_eq!(text_at(call(0, 10, 2)), "普通的文字", "挂之前");
        assert!(check(page).is_ok_and(|h| !h));
        assert_eq!(install(page), Ok("原样"));
        assert_eq!(repo.vt, 0);
        // 跳板里改成长跳的 jae、函数里的第二个检查、查不到：都是空
        assert!(call(1, 10, 2).is_null() && call(0, 99, 2).is_null() && call(0, 11, 2).is_null() && call(0, 10, 7).is_null());
        assert_eq!(call(0, 10, 2), STRS[1].as_ptr(), "普通文字照原样");
        // 装备文字：交了说明和文字才换
        assert_eq!(call(0, 10, 1), STRS[0].as_ptr());
        set_labels(&["生成的装备（dark_core 没有改写）".into(), "Generated gear (not rewritten)".into()]);
        assert_eq!(call(0, 10, 1), STRS[0].as_ptr(), "还没有这件的文字");
        let mut name = u("不屈的长剑");
        name.resize(40, 0);
        set_item(4_000_000_002, 0, 0, &name);
        let p = call(0, 10, 1);
        assert_eq!(text_at(p), "不屈的长剑");
        name[..5].copy_from_slice(&u("坚毅的长剑"));
        set_item(4_000_000_002, 0, 0, &name);
        assert_eq!((call(0, 10, 1), text_at(p)), (p, "坚毅的长剑".to_string()), "改文字地址不变");
        assert!(ui_lang() == 0);
        // 确认框：有文字才换，文字变了重拼，没变沿用同一份
        assert_eq!(call(0, 10, 3), STRS[2].as_ptr());
        set_confirm(b'I', 9, &u("未鉴定防具：普通 2"), &u("Unidentified: Common 2"));
        let c1 = call(0, 10, 3);
        assert_eq!(text_at(c1), "要鉴定吗？未鉴定防具：普通 2");
        assert_eq!(call(0, 10, 3), c1);
        set_confirm(b'I', 8, &u("别的"), &u("other"));
        assert_eq!(call(0, 10, 3), c1, "别的种类变了，拼出来一样就沿用");
        set_confirm(b'I', 9, &u("未鉴定防具：普通 0"), &u("Unidentified: Common 0"));
        let c2 = call(0, 10, 3);
        assert_ne!(c2, c1);
        assert_eq!((text_at(c2), text_at(c1)), ("要鉴定吗？未鉴定防具：普通 0".to_string(), "要鉴定吗？未鉴定防具：普通 2".to_string()), "旧的那份还在");
        // 幻化插件那一项加图标
        let t = call(0, TALK_BND, TRANSMOG_TEXT);
        assert_eq!(text_at(t), format!("{TRANSMOG_PREFIX}幻化防具"));
        assert_eq!(call(0, TALK_BND, TRANSMOG_TEXT), t);
        assert_eq!(call(0, 10, TRANSMOG_TEXT), STRS[3].as_ptr(), "别的类别不加");
        assert_eq!(install(page), Err("已经挂过".into()));
    }
}
