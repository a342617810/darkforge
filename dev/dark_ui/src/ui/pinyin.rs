//! 拼音搜索（用户 2026-11-09「用拼音搜索吧 中文输入还是有点问题」）：搜索框里打字母就能搜中文。全拼、首字母、混着打都行，最后一个音节可以只打一半：
//! 「法术」打 fashu / fs / fash / fshu 都能搜到。空格、标点会隔开，不跨过去匹配。
//! 文字分两段，用 \x01 隔开：前面是名字（首字母、半个音节都算），后面是说明（第一个音节要打全、不认首字母，不然 fs 这种两个字母在长说明里到处都能碰上）。
//! 读音表 pinyin_table.bin 由 dev/tools/make_pinyin.py 生成（Windows 自带 ICU 的数据，每个字一个最常见的读音），一字多音的其他读音在 EXTRA。
use std::collections::HashMap;
use std::sync::OnceLock;

static TABLE: &[u8] = include_bytes!("pinyin_table.bin");
const FIRST: u32 = 0x4E00;
const LAST: u32 = 0x9FFF;

/// 一字多音：表里只有最常见的读音，这里补词条和装备文字里常见字的其他读音（新词条遇到别的多音字加在这里）
const EXTRA: &[(char, &str)] = &[
    ('度', "duo"),
    ('会', "kuai"),
    ('提', "di"),
    ('血', "xue"),
    ('血', "xie"),
    ('长', "chang"),
    ('长', "zhang"),
    ('石', "dan"),
    ('重', "zhong"),
    ('重', "chong"),
    ('强', "qiang"),
    ('强', "jiang"),
    ('地', "di"),
    ('地', "de"),
    ('削', "xue"),
    ('削', "xiao"),
    ('落', "luo"),
    ('落', "la"),
    ('露', "lu"),
    ('露', "lou"),
    ('恶', "e"),
    ('恶', "wu"),
    ('调', "tiao"),
    ('调', "diao"),
    ('降', "jiang"),
    ('降', "xiang"),
    ('行', "xing"),
    ('行', "hang"),
    ('角', "jiao"),
    ('角', "jue"),
    ('得', "de"),
    ('得', "dei"),
    ('和', "he"),
    ('和', "huo"),
    ('了', "le"),
    ('了', "liao"),
    ('便', "bian"),
    ('便', "pian"),
    ('传', "chuan"),
    ('传', "zhuan"),
    ('奇', "qi"),
    ('奇', "ji"),
    ('还', "hai"),
    ('还', "huan"),
    ('率', "lv"),
    ('率', "shuai"),
    ('朝', "chao"),
    ('朝', "zhao"),
    ('模', "mo"),
    ('模', "mu"),
    ('给', "gei"),
    ('给', "ji"),
    ('着', "zhe"),
    ('着', "zhao"),
    ('着', "zhuo"),
    ('薄', "bao"),
    ('薄', "bo"),
    ('剥', "bo"),
    ('剥', "bao"),
    ('差', "cha"),
    ('差', "chai"),
    ('宿', "su"),
    ('宿', "xiu"),
    ('弹', "dan"),
    ('弹', "tan"),
    ('数', "shu"),
    ('数', "shuo"),
];

struct Data {
    syl: Vec<&'static str>,
    table: &'static [u8],
    extra: HashMap<char, Vec<&'static str>>,
    /// 基本汉字区里哪些字在 EXTRA（大多数字不用查表）
    flagged: Vec<bool>,
}

fn data() -> &'static Data {
    static D: OnceLock<Data> = OnceLock::new();
    D.get_or_init(|| {
        let len = u16::from_le_bytes([TABLE[2], TABLE[3]]) as usize;
        let syl = std::str::from_utf8(&TABLE[4..4 + len]).unwrap_or("").split(' ').collect();
        let mut extra: HashMap<char, Vec<&'static str>> = HashMap::new();
        let mut flagged = vec![false; (LAST - FIRST + 1) as usize];
        for &(c, p) in EXTRA {
            extra.entry(c).or_default().push(p);
            flagged[(c as u32 - FIRST) as usize] = true;
        }
        Data { syl, table: &TABLE[4 + len..], extra, flagged }
    })
}

/// 这个字所有的读音（不是汉字就没有）
fn readings(c: char) -> impl Iterator<Item = &'static str> {
    let d = data();
    let cp = c as u32;
    let i = (FIRST..=LAST).contains(&cp).then(|| (cp - FIRST) as usize);
    let main = i.and_then(|i| {
        let v = u16::from_le_bytes([*d.table.get(i * 2)?, *d.table.get(i * 2 + 1)?]) as usize;
        v.checked_sub(1).and_then(|v| d.syl.get(v).copied())
    });
    let extra = i.filter(|&i| d.flagged[i]).and_then(|_| d.extra.get(&c));
    main.into_iter().chain(extra.into_iter().flatten().copied())
}

/// 从第 i 个字开始，q（还没配上的字母，非空）能不能读下去。first = 这是第一个字
fn step(cs: &[char], i: usize, q: &[u8], name_end: usize, first: bool) -> bool {
    let Some(&c) = cs.get(i) else { return false };
    let in_name = i < name_end;
    readings(c).any(|p| {
        let p = p.as_bytes();
        // 最后一个音节打了一半
        if q.len() < p.len() && p.starts_with(q) && (in_name || !first) {
            return true;
        }
        // 打了整个音节
        if q.starts_with(p) && (q.len() == p.len() || step(cs, i + 1, &q[p.len()..], name_end, false)) {
            return true;
        }
        // 只打了首字母（只认名字）
        in_name && p[0] == q[0] && (q.len() == 1 || step(cs, i + 1, &q[1..], name_end, false))
    })
}

/// hay（小写，\x01 前是名字、后是说明）里有没有一段能读成 q（全是小写字母，非空）
pub(super) fn matches(hay: &str, q: &str) -> bool {
    let cs: Vec<char> = hay.chars().collect();
    let name_end = cs.iter().position(|&c| c == '\x01').unwrap_or(cs.len());
    (0..cs.len()).any(|i| step(&cs, i, q.as_bytes(), name_end, true))
}

#[cfg(test)]
mod tests {
    use super::matches;

    #[test]
    fn full_initials_and_mixed() {
        for q in ["fashu", "fs", "fash", "fshu", "f", "fa", "shu"] {
            assert!(matches("法术\x01", q), "{q}");
        }
        for q in ["xyz", "fashux", "sf"] {
            assert!(!matches("法术\x01", q), "{q}");
        }
    }

    #[test]
    fn descriptions_need_a_whole_first_syllable() {
        let hay = "甲\x01法术";
        for q in ["fashu", "fa", "fas", "fash"] {
            assert!(matches(hay, q), "{q}");
        }
        for q in ["fs", "f"] {
            assert!(!matches(hay, q), "{q}");
        }
    }

    #[test]
    fn heteronyms_take_any_reading() {
        for q in ["zhongji", "chongji", "zj", "cj"] {
            assert!(matches("重击\x01", q), "{q}");
        }
        for q in ["xuejian", "xiaojian", "chuanshuo", "cs"] {
            assert!(matches("削减传说\x01", q), "{q}");
        }
    }

    #[test]
    fn spaces_break_a_match() {
        assert!(!matches("法 术\x01", "fashu"));
        assert!(matches("法 术\x01", "shu"));
    }

    #[test]
    fn every_syllable_is_lowercase_ascii() {
        let d = super::data();
        assert!(d.syl.len() > 300);
        assert!(d.syl.iter().all(|s| !s.is_empty() && s.bytes().all(|b| b.is_ascii_lowercase())));
    }
}
