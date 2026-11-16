//! 原版的闪烁提示（屏幕中间一行字、几秒后淡出，EMEVD 2007:4，文字在 EventTextForMap；用户 2026-11-03：夺取魇火的提示用原版提示框，
//! 不用 dark_ui 自己画的）：魇火、魇印、刻印位、咒痕碎片的提示都走这里。
//! 编号在重随里分好（rr/notes.py → notes.txt：bits <7 个标记>、note <键> <编号>），公共事件（sc/notes.py）每 0.25 秒看这 7 个标记，
//! 有编号就显示那条文字、3 秒后全部熄灭。这里排队：7 个标记全灭了才写下一条，一条接一条。
//! 键：seize <种>、level <种> <级 1~4>、slot <第几位>（nightmare.rs）；shard <区域> <第几片>、rev <区域>（curses.rs）。
//! 只在队列里有东西时才读标记；不在游戏里（标题画面、读档中）队列直接丢掉。
use std::collections::{HashMap, VecDeque};
use std::fs;
use std::sync::{Mutex, OnceLock};

use crate::gear::{flag_get, flag_set};
use crate::{dir, log};

#[derive(Debug, Default, PartialEq)]
struct Def {
    /// 编号按位写进这几个标记（第 i 个 = 第 i 位）
    bits: Vec<u32>,
    ids: HashMap<String, u32>,
}

static DEF: OnceLock<Option<Def>> = OnceLock::new();
static Q: Mutex<VecDeque<u32>> = Mutex::new(VecDeque::new());

fn parse(text: &str) -> Option<Def> {
    let mut d = Def::default();
    for l in text.lines() {
        let l = l.trim_start_matches('\u{feff}');
        if let Some(rest) = l.strip_prefix("bits ") {
            d.bits = rest.split_whitespace().filter_map(|x| x.parse().ok()).collect();
        } else if let ["note", key, v] = l.split('\t').collect::<Vec<_>>()[..] {
            if let Ok(v) = v.parse() {
                d.ids.insert(key.to_string(), v);
            }
        }
    }
    let cap = 1u32.checked_shl(d.bits.len() as u32).unwrap_or(0);
    d.ids.retain(|_, v| *v > 0 && *v < cap);
    (!d.bits.is_empty() && !d.ids.is_empty()).then_some(d)
}

fn def() -> Option<&'static Def> {
    DEF.get_or_init(|| parse(&fs::read_to_string(dir().join("notes.txt")).unwrap_or_default())).as_ref()
}

pub fn describe() -> String {
    match def() {
        Some(d) => format!("原版提示（{} 条）", d.ids.len()),
        None => "原版提示（没有 notes.txt，不提示）".into(),
    }
}

/// 没有排队等着显示的提示（bossmode.rs 错配时一条接一条不停地提示重启）
pub fn idle() -> bool {
    Q.lock().map(|q| q.is_empty()).unwrap_or(false)
}

/// 把还在排队的这几条删掉（bossmode.rs：难度对上了、回到标题时，删掉还没显示的重启提示，换个对得上的角色不会再冒出来）
pub fn forget(keys: &[&str]) {
    let Some(d) = def() else { return };
    let vals: Vec<u32> = keys.iter().filter_map(|k| d.ids.get(*k).copied()).collect();
    if vals.is_empty() {
        return;
    }
    Q.lock().unwrap_or_else(|e| e.into_inner()).retain(|v| !vals.contains(v));
}

/// 排一条提示（键见文件开头）；没有这一条只写日志。排上队了返回 true（notes.txt 里没有这个键 = false）
pub fn push(key: &str) -> bool {
    match def().and_then(|d| d.ids.get(key)) {
        Some(&v) => {
            Q.lock().unwrap_or_else(|e| e.into_inner()).push_back(v);
            true
        }
        None => {
            log(&format!("原版提示：notes.txt 里没有「{key}」"));
            false
        }
    }
}

pub fn tick() {
    let Some(d) = def() else { return };
    let mut q = Q.lock().unwrap_or_else(|e| e.into_inner());
    let Some(&v) = q.front() else { return };
    let mut busy = false;
    for &b in &d.bits {
        match flag_get(b) {
            None => {
                q.clear();
                return;
            }
            Some(on) => busy |= on,
        }
    }
    if busy {
        return;
    }
    for (i, &b) in d.bits.iter().enumerate() {
        flag_set(b, (v >> i) & 1 == 1);
    }
    q.pop_front();
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 定义：位标记、键 → 编号；超出位数的、0 号不要
    #[test]
    fn parse_def() {
        let d = parse("bits 93093 93094 93095\nnote\tseize 0\t1\nnote\tlevel 0 2\t7\nnote\tbad\t8\nnote\tzero\t0\n").unwrap();
        assert_eq!(d.bits, vec![93093, 93094, 93095]);
        assert_eq!(d.ids.get("seize 0"), Some(&1));
        assert_eq!(d.ids.get("level 0 2"), Some(&7));
        assert!(!d.ids.contains_key("bad") && !d.ids.contains_key("zero"));
        assert!(parse("note\tseize 0\t1\n").is_none());
    }
}
