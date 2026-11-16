//! 「词条百科」页（装备工坊最左边一页；用户 2026-11-09）：
//!   左：类别页签（武器 / 头部 / 身体 / 手部 / 腿部 / 护符 / 骨灰）+ 这一类能出的词条，流派词条按流派排在前面
//!   中：选中词条的说明，按稀有度分行（说明一样的相邻稀有度合成一行），各档都有的说明行放最后写一次
//!   右：相关词条（只有流派词条有）：规则上直接联动的在前，后面是同流派的
//! 操作：上下选词条，X / Tab 换类别，A / 右 / RB 到相关词条，那边 A 跳过去；B 从跳转的地方回来，没跳转过就返回 / 关窗口。
//! 扩展：这里不写死任何词条。内容全部来自 dll\dark_core\affixes.txt（fam / famw / famr / wspec，重随写的），流派和联动也是重随算好的
//! （extract_affixes.py ARCHETYPES、rr/affixes.py codex_lines）：新词条、新武器特效重随后自动出现。
//! 只有新加「类别」或者想给新流派排序、起英文名时才改这个文件（CATS / ARCH；没登记的新流派照样算流派词条，按中文名显示）。
//! 图标：affixes.txt 的 famicon 行（原图标，优先 launcher\reroll\data\codex_icons.json，其次这个词条的护符现在的图标），这里按 dr_frames.txt 换成各稀有度带框的；
//! 换图标不用改这个文件：改护符的图标或者 codex_icons.json，重随后就变。
//! 骨灰（2026-11-10）：dll\dark_core\ashes.txt 的 ashcx 行（rr/ashcont.py codex_lines：稀有度、集结、数值词条，各档文字已经填好数），
//! 只进「骨灰」这一类，不算流派（没有相关词条）。
use std::collections::HashMap;

use super::*;

/// 类别：武器、四个防具部位、护符、骨灰
pub(super) const CATS: usize = 7;
const WEAPON: usize = 0;
const ARMOR: [usize; 4] = [1, 2, 3, 4];
const TALISMAN: usize = 5;
const ASH: usize = 6;
const CAT_NAME: [[&str; CATS]; 2] =
    [["武器", "头部", "身体", "手部", "腿部", "护符", "骨灰"], ["Armament", "Head", "Chest", "Arms", "Legs", "Talisman", "Spirit Ashes"]];
const CAT_TAB: [&str; CATS] = ["MENU_Tab_Weapon", "MENU_Tab_10", "MENU_Tab_11", "MENU_Tab_12", "MENU_Tab_13", "MENU_Tab_15", "MENU_Tab_29_Buddy"];

/// 流派的显示顺序和英文名；没登记的新流派排在它们后面
const ARCH: [(&str, &str); 11] = [
    ("命中连击", "Combo"),
    ("重击处决", "Heavy & Critical"),
    ("战技", "Skills"),
    ("法术", "Spells"),
    ("远程", "Ranged"),
    ("异常", "Ailments"),
    ("防御", "Guard"),
    ("闪避", "Evasion"),
    ("机动空战", "Mobility"),
    ("姿态", "Stance"),
    ("反击回血", "Recovery"),
];
/// 不算流派的分类（通用数值）：没有相关词条，排在列表最后；「召唤」= 骨灰词条
const GENERIC: [(&str, &str); 5] = [("属性", "Attributes"), ("生存", "Survival"), ("杂项", "Misc"), ("其他", "Other"), ("召唤", "Summon")];

/// 左边、右边一屏几行
pub(super) const LIST_VIS: usize = 14;
pub(super) const REL_VIS: usize = 14;

fn is_build(arch: &str) -> bool {
    !GENERIC.iter().any(|g| g.0 == arch)
}

/// 列表里的先后：登记的流派、没登记的流派、通用
fn arch_rank(arch: &str) -> usize {
    if let Some(i) = ARCH.iter().position(|a| a.0 == arch) {
        return i;
    }
    match GENERIC.iter().position(|g| g.0 == arch) {
        Some(i) => ARCH.len() + 1 + i,
        None => ARCH.len(),
    }
}

fn arch_name(arch: &str, l: usize) -> &str {
    ARCH.iter().chain(GENERIC.iter()).find(|a| a.0 == arch).map_or(arch, |a| if l == 0 { a.0 } else { a.1 })
}

#[derive(Clone, Debug, Default)]
struct Entry {
    key: String,
    name: [String; 2],
    arch: String,
    /// 前缀（机制类）/ 后缀（数值类）；武器特效没有
    mech: Option<bool>,
    /// 各类别能出的稀有度（位：普通 1 / 稀有 2 / 史诗 4 / 传说 8），0 = 这一类不出
    rars: [u8; CATS],
    /// 各稀有度的说明 [中文, 英文]
    text: [[String; 2]; 4],
    /// 规则上直接联动的词条（在 entries 里的序号）
    links: Vec<usize>,
    /// 各稀有度的图标（带框的，0 = 这一档没有）
    icon: [u16; 4],
    /// 搜索用的文字（小写）：名字、流派、各档说明
    hay: String,
}

impl Entry {
    /// 这一档的图标，这一档没有就用别的档的
    fn icon_at(&self, r: usize) -> u16 {
        std::iter::once(r).chain(0..4).map(|x| self.icon[x]).find(|&i| i != 0).unwrap_or(0)
    }

    /// mask 里最高一档的图标
    fn top_icon(&self, mask: u8) -> u16 {
        self.icon_at((0..4).rev().find(|r| mask & (1 << r) != 0).unwrap_or(3))
    }
}

/// 从词条库解析出来的百科（不碰游戏，只读 affixes.txt）
#[derive(Default)]
pub struct Codex {
    entries: Vec<Entry>,
    /// 各类别的词条（在 entries 里的序号）
    lists: [Vec<usize>; CATS],
    /// 所有词条的名字（含停用的：旧装备身上可能还有）、键 → entries 里的序号（词条筛选用）
    names: HashMap<String, [String; 2]>,
    pos: HashMap<String, usize>,
}

fn unesc(s: &str) -> String {
    s.replace("\\n", "\n")
}

fn bits(s: &str) -> u8 {
    s.split(',').take(4).enumerate().filter(|(_, x)| x.parse::<i64>().unwrap_or(0) > 0).fold(0, |m, (i, _)| m | 1 << i)
}

impl Codex {
    /// lib：词条库全文（认识的行才用，别的行不管）；frames：dr_frames.txt（原图标 稀有度 带框的图标）。停用的词条（能出的稀有度全是 0）不进百科
    pub fn parse(lib: &str, frames: &str) -> Codex {
        struct Raw {
            armor: u8,
            tal: u8,
            has_text: u8,
            has_tal: u8,
            slots: u8,
        }
        let mut entries: Vec<Entry> = Vec::new();
        let mut raws: Vec<Option<Raw>> = Vec::new(); // 武器特效是 None，rars 直接定好
        let mut of_idx: HashMap<&str, usize> = HashMap::new();
        let mut archs: Vec<(&str, &str)> = Vec::new();
        let mut links: Vec<(&str, Vec<&str>)> = Vec::new();
        let mut icons: Vec<(&str, &str)> = Vec::new();
        // 词条数值随机（famspan，rr/affixes.py val_lines）：这一档的说明换成「下限~上限」的
        let mut spans: Vec<(usize, usize, [String; 2])> = Vec::new();
        for line in lib.lines() {
            let f: Vec<&str> = line.split('\t').collect();
            match f[0] {
                "fam" if f.len() >= 11 => {
                    of_idx.insert(f[1], entries.len());
                    let w = |s: &str| if s.parse::<i64>().unwrap_or(0) > 0 { 15 } else { 0 };
                    raws.push(Some(Raw { armor: w(f[2]), tal: w(f[3]), has_text: 0, has_tal: 0, slots: f[7].parse().unwrap_or(0) }));
                    entries.push(Entry { key: f[6].into(), name: [unesc(f[4]), unesc(f[5])], arch: unesc(f[10]), mech: Some(f[8] == "1"), ..Entry::default() });
                }
                "famw" if f.len() >= 4 => {
                    if let Some(raw) = of_idx.get(f[1]).and_then(|&i| raws[i].as_mut()) {
                        raw.armor = bits(f[2]);
                        raw.tal = bits(f[3]);
                    }
                }
                "famr" if f.len() >= 7 => {
                    let (Some(&i), Ok(r)) = (of_idx.get(f[1]), f[2].parse::<usize>()) else { continue };
                    if r < 4 {
                        entries[i].text[r] = [unesc(f[5]), unesc(f[6])];
                        if let Some(raw) = raws[i].as_mut() {
                            raw.has_text |= 1 << r;
                            if f[4] != "-1" {
                                raw.has_tal |= 1 << r;
                            }
                        }
                    }
                }
                "wspec" if f.len() >= 10 && f[3].parse::<i64>().unwrap_or(0) > 0 => {
                    // 武器特效的说明开头是「名字：」，上面已经有名字了
                    let zh = unesc(f[7]);
                    let en = unesc(f[8]);
                    let zh = zh.strip_prefix(&format!("{}：", f[5])).unwrap_or(&zh).to_string();
                    let en = en.strip_prefix(&format!("{}: ", f[6])).unwrap_or(&en).to_string();
                    let mask = f[9].parse::<u8>().unwrap_or(15) & 15;
                    let mut e = Entry { key: f[1].into(), name: [unesc(f[5]), unesc(f[6])], arch: "其他".into(), ..Entry::default() };
                    e.rars[WEAPON] = mask;
                    e.text = std::array::from_fn(|_| [zh.clone(), en.clone()]);
                    entries.push(e);
                    raws.push(None);
                }
                "ashcx" if f.len() >= 14 => {
                    // 骨灰词条：各档文字填好了，空着 = 这一档没有
                    let mech = match f[4] {
                        "1" => Some(true),
                        "0" => Some(false),
                        _ => None,
                    };
                    let mut e = Entry { key: f[1].into(), name: [unesc(f[2]), unesc(f[3])], arch: "召唤".into(), mech, ..Entry::default() };
                    e.text = std::array::from_fn(|r| [unesc(f[6 + 2 * r]), unesc(f[7 + 2 * r])]);
                    e.rars[ASH] = (0..4).filter(|&r| !e.text[r][0].is_empty()).fold(0, |m, r| m | 1 << r);
                    icons.push((f[1], f[5]));
                    entries.push(e);
                    raws.push(None);
                }
                "famspan" if f.len() >= 5 => {
                    let (Some(&i), Ok(r)) = (of_idx.get(f[1]), f[2].parse::<usize>()) else { continue };
                    if r < 4 {
                        spans.push((i, r, [unesc(f[3]), unesc(f[4])]));
                    }
                }
                "wspecarch" if f.len() >= 3 => archs.push((f[1], f[2])),
                "famlink" if f.len() >= 3 => links.push((f[1], f[2].split(',').collect())),
                "famicon" if f.len() >= 3 => icons.push((f[1], f[2])),
                _ => {}
            }
        }
        for (i, r, t) in spans {
            entries[i].text[r] = t;
        }
        for (e, raw) in entries.iter_mut().zip(&raws) {
            let Some(raw) = raw else { continue };
            for (k, c) in ARMOR.into_iter().enumerate() {
                if raw.slots & (1 << k) != 0 {
                    e.rars[c] = raw.armor & raw.has_text;
                }
            }
            e.rars[TALISMAN] = raw.tal & raw.has_tal;
        }
        for (k, a) in archs {
            if let Some(e) = entries.iter_mut().find(|e| e.key == k) {
                e.arch = unesc(a);
            }
        }
        let names: HashMap<String, [String; 2]> = entries.iter().map(|e| (e.key.clone(), e.name.clone())).collect();
        // 停用的去掉以后序号才定下来，联动放到最后接
        entries.retain(|e| e.rars.iter().any(|&m| m != 0));
        let of_key: HashMap<String, usize> = entries.iter().enumerate().map(|(i, e)| (e.key.clone(), i)).collect();
        for (k, v) in links {
            if let Some(&i) = of_key.get(k) {
                entries[i].links = v.iter().filter_map(|o| of_key.get(*o).copied()).collect();
            }
        }
        let framed: HashMap<(u16, usize), u16> = frames
            .lines()
            .filter_map(|l| {
                let mut p = l.split('\t');
                Some(((p.next()?.parse().ok()?, p.next()?.parse().ok()?), p.next()?.parse().ok()?))
            })
            .collect();
        for (k, v) in icons {
            let Some(&i) = of_key.get(k) else { continue };
            for (r, x) in v.split(',').take(4).enumerate() {
                let base = x.parse().unwrap_or(0);
                entries[i].icon[r] = framed.get(&(base, r)).copied().unwrap_or(base); // 自制图标（56000+）没有带框版，就是它自己
            }
        }
        let lists = std::array::from_fn(|c| {
            let mut v: Vec<usize> = (0..entries.len()).filter(|&i| entries[i].rars[c] != 0).collect();
            v.sort_by_key(|&i| arch_rank(&entries[i].arch)); // 稳定排序：同流派里保持词条库的先后
            v
        });
        for e in &mut entries {
            let text: Vec<&str> = e.text.iter().flatten().map(String::as_str).collect();
            e.hay = format!("{} {} {}\x01{}", e.name[0], e.name[1], e.arch, text.join(" ")).to_lowercase();
        }
        Codex { entries, lists, names, pos: of_key }
    }

    /// 词条的名字（词条库里没有就显示键）
    pub(super) fn key_name(&self, key: &str, l: usize) -> String {
        self.names.get(key).map_or_else(|| key.to_string(), |n| n[l.min(1)].clone())
    }

    /// 词条筛选窗口搜词条用
    pub(super) fn key_hay(&self, key: &str) -> String {
        format!("{} {}", self.key_name(key, 0), self.key_name(key, 1)).to_lowercase()
    }

    pub(super) fn key_icon(&self, key: &str) -> u16 {
        self.pos.get(key).map_or(0, |&i| self.entries[i].top_icon(15))
    }

    /// 词条筛选窗口里的先后：和百科一样（流派词条在前），停用的在最后
    pub(super) fn key_order(&self, key: &str) -> (usize, usize) {
        self.pos.get(key).map_or((usize::MAX, 0), |&i| (arch_rank(&self.entries[i].arch), i))
    }

    /// 第 c 类里符合关键词的
    fn filtered(&self, c: usize, terms: &[String]) -> Vec<usize> {
        self.lists[c.min(CATS - 1)].iter().copied().filter(|&i| filter::has_all(terms, &self.entries[i].hay)).collect()
    }

    /// 相关词条：（序号, 规则上直接联动）。只有流派词条有
    fn related(&self, i: usize) -> Vec<(usize, bool)> {
        let e = &self.entries[i];
        if !is_build(&e.arch) {
            return Vec::new();
        }
        let same = (0..self.entries.len()).filter(|&k| k != i && self.entries[k].arch == e.arch && !e.links.contains(&k));
        e.links.iter().map(|&k| (k, true)).chain(same.map(|k| (k, false))).collect()
    }
}

/// 中间的说明，分三块
#[derive(Debug, Default, PartialEq)]
struct Blocks {
    /// 各档都一样、写在数值前面的行（效果本身）
    lead: Vec<String>,
    /// （这一行对应的稀有度, 文字）；相邻稀有度说明一样的合成一行
    rows: Vec<(Vec<usize>, String)>,
    /// 各档都一样、写在数值后面的行（随什么属性提升、叠加规则这些）
    notes: Vec<String>,
}

fn blocks(e: &Entry, mask: u8, l: usize) -> Blocks {
    let texts: Vec<(usize, Vec<&str>)> = (0..4).filter(|r| mask & (1 << r) != 0).map(|r| (r, e.text[r][l].split('\n').filter(|x| !x.is_empty()).collect())).collect();
    let Some(first) = texts.first() else { return Blocks::default() };
    let same = |x: &&str| texts.iter().all(|t| t.1.contains(x));
    let (mut lead, mut notes): (Vec<&str>, Vec<&str>) = (Vec::new(), Vec::new());
    if first.1.iter().all(|x| same(&x)) {
        notes.extend(first.1.iter().skip(1)); // 各档完全一样：第一行是效果本身，放在稀有度那一行
    } else {
        let n = first.1.iter().take_while(|x| same(x)).count();
        lead.extend(&first.1[..n]);
        notes.extend(first.1[n..].iter().filter(|x| same(x)));
    }
    let mut rows: Vec<(Vec<usize>, String)> = Vec::new();
    for (r, lines) in &texts {
        let body = lines.iter().copied().filter(|x| !lead.contains(x) && !notes.contains(x)).collect::<Vec<_>>().join("\n");
        match rows.last_mut() {
            Some(last) if last.1 == body => last.0.push(*r),
            _ => rows.push((vec![*r], body)),
        }
    }
    let own = |v: Vec<&str>| v.into_iter().map(String::from).collect();
    Blocks { lead: own(lead), rows, notes: own(notes) }
}

fn rar_label(rs: &[usize], l: usize) -> String {
    match rs {
        [] => String::new(),
        [r] => RAR_NAME[l][*r].to_string(),
        [a, .., b] => format!("{} ~ {}", RAR_NAME[l][*a], RAR_NAME[l][*b]),
    }
}

impl Workshop {
    fn k_cur(&self) -> Option<usize> {
        self.v_k.get(self.ksel[self.kcat]).copied()
    }

    fn k_related(&self) -> Vec<(usize, bool)> {
        self.k_cur().map(|i| self.codex.related(i)).unwrap_or_default()
    }

    pub(super) fn codex_has_related(&self) -> bool {
        !self.k_related().is_empty()
    }

    /// 底部提示：B 是回到跳转前的词条
    pub(super) fn codex_can_back(&self) -> bool {
        self.page == 5 && !self.khist.is_empty()
    }

    pub(super) fn codex_filtered(&self, c: usize, terms: &[String]) -> Vec<usize> {
        self.codex.filtered(c, terms)
    }

    /// 第一个有结果的类别和它的结果
    pub(super) fn codex_first_hit(&self, terms: &[String]) -> Option<(usize, Vec<usize>)> {
        (0..CATS).map(|c| (c, self.codex.filtered(c, terms))).find(|x| !x.1.is_empty())
    }

    /// 关键词变了：回到第一行
    pub(super) fn codex_reset_sel(&mut self) {
        self.ksel = [0; CATS];
        self.ktop = [0; CATS];
        self.kcol = 0;
        self.krel = 0;
        self.krtop = 0;
        self.khist.clear();
    }

    fn k_move(&mut self, i: usize) {
        self.ksel[self.kcat] = i;
        self.krel = 0;
        self.krtop = 0;
    }

    fn k_cat(&mut self, c: usize) {
        self.kcat = c.min(CATS - 1);
        self.kcol = 0;
        self.krel = 0;
        self.krtop = 0;
        self.khist.clear();
    }

    /// 跳到一条相关词条：这一类里有就留在这一类，没有就去第一个有它的类别
    fn k_jump(&mut self, e: usize) {
        // 搜索着的时候目标可能被筛掉了：跳转前清掉关键词
        if !self.query[5].is_empty() {
            self.query[5].clear();
            self.refresh_views();
        }
        let find = |c: usize| self.codex.lists[c].iter().position(|&x| x == e).map(|i| (c, i));
        let Some((c, i)) = find(self.kcat).or_else(|| (0..CATS).find_map(find)) else { return };
        self.khist.push((self.kcat, self.ksel[self.kcat]));
        self.kcat = c;
        self.kcol = 0;
        self.k_move(i);
    }

    pub(super) fn handle_codex(&mut self, a: Act) {
        if a.x {
            return self.k_cat((self.kcat + 1) % CATS);
        }
        let rel = self.k_related();
        if self.kcol == 0 {
            let n = self.v_k.len();
            let s = self.ksel[self.kcat];
            if a.up && s > 0 {
                self.k_move(s - 1);
            }
            if a.down && s + 1 < n {
                self.k_move(s + 1);
            }
            if (a.a || a.right || a.rb) && !rel.is_empty() {
                self.kcol = 1;
                self.krel = 0;
                self.krtop = 0;
            }
            if a.b {
                match self.khist.pop() {
                    Some((c, i)) => {
                        self.kcat = c;
                        self.k_move(i);
                    }
                    None => self.reqs.push(Req::Close),
                }
            }
            return;
        }
        if a.up && self.krel > 0 {
            self.krel -= 1;
        }
        if a.down && self.krel + 1 < rel.len() {
            self.krel += 1;
        }
        if a.a {
            if let Some(&(e, _)) = rel.get(self.krel) {
                self.k_jump(e);
            }
        } else if a.b || a.left || a.lb {
            self.kcol = 0;
        }
    }

    pub(super) fn click_codex(&mut self, h: Hit) {
        let a = Act { a: true, ..Act::default() };
        match h {
            Hit::KTab(i) => self.k_cat(i),
            Hit::KRow(i) => {
                // 百科只是翻看：点一下选上，不跳到右边（相关词条直接点）
                self.kcol = 0;
                if self.ksel[self.kcat] != i {
                    self.k_move(i);
                }
            }
            Hit::KRel(i) => {
                let again = self.kcol == 1 && self.krel == i;
                self.kcol = 1;
                self.krel = i;
                if again {
                    self.handle_codex(a);
                }
            }
            _ => {}
        }
    }

    /// 鼠标停在一行上：左边选这条词条，右边选这条相关词条
    pub(super) fn hover_codex(&mut self, h: Hit) {
        match h {
            Hit::KRow(i) => {
                self.kcol = 0;
                if self.ksel[self.kcat] != i {
                    self.k_move(i);
                }
            }
            Hit::KRel(i) => {
                self.kcol = 1;
                self.krel = i;
            }
            _ => {}
        }
    }

    /// 滚动：（第一行, 一屏几行, 总行数）；rel = 右边的相关词条
    pub(super) fn codex_scroll(&self, rel: bool) -> (usize, usize, usize) {
        if rel { (self.krtop, REL_VIS, self.k_related().len()) } else { (self.ktop[self.kcat], LIST_VIS, self.v_k.len()) }
    }

    pub(super) fn codex_set_top(&mut self, rel: bool, top: usize) {
        if rel {
            self.krtop = top;
        } else {
            self.ktop[self.kcat] = top;
        }
    }

    pub(super) fn draw_codex(&mut self, d: &mut Draw) {
        let l = self.lang().min(1);
        let cat = self.kcat;
        // 左：类别页签 + 词条列表
        let (x, y, w) = (70.0, 150.0, 560.0);
        d.sprite("MENU_BaseMain_02", x - 20.0, y - 10.0, w + 60.0, 820.0, 0.55);
        // 七个页签挤一行（2026-11-10 加了骨灰）：页签缩到 0.9，类别名接在后面
        const TS: f32 = 0.9;
        let step = 60.0 * TS + 2.0;
        for (i, name) in CAT_TAB.iter().enumerate() {
            let tx = x + 10.0 + i as f32 * step;
            if i == cat {
                d.sprite("MENU_FL_Tab_Cursor", tx - 12.0 * TS, y - 6.0 * TS, 84.0 * TS, 72.0 * TS, 1.0);
            }
            d.sprite_fit(name, tx, y, 60.0 * TS, 58.0 * TS, if i == cat { 1.0 } else { 0.4 });
            self.hit(tx - 1.0, y - 4.0, step, 62.0, Hit::KTab(i));
        }
        let gx = x + 14.0 + CATS as f32 * step;
        d.glyph("KG_XboxSeries_R_L", gx, y + 9.0, 34.0);
        d.text_clip_mid(gx + 40.0, y + 26.0, x + w - gx - 40.0, 24.0, GOLD, 1.0, CAT_NAME[l][cat]);
        d.sprite("MENU_Line_01", x, y + 70.0, w, 3.0, 0.8);
        let list = self.v_k.clone();
        let (ly, rh) = (y + 82.0, 50.0);
        let sel = self.ksel[cat];
        fit_top(&mut self.ktop[cat], sel, LIST_VIS, list.len(), self.follow);
        let top = self.ktop[cat];
        self.hit(x, ly, w, rh * LIST_VIS as f32, Hit::Area(Scroll::KRow));
        if list.is_empty() {
            let msg = if self.filtering() {
                self.t("没有符合搜索的词条", "No affixes match")
            } else if cat == ASH {
                self.t("骨灰稀有度没开，没有骨灰词条", "Spirit ash rarity is off")
            } else { self.t("这一类没有词条（没开未鉴定物品时没有词条库）", "No affixes here (the affix library needs unidentified gear enabled)") };
            d.wrapped(x + 20.0, ly + 20.0, w - 40.0, 22.0, DIM, 1.0, msg);
        }
        for (i, &e) in list.iter().enumerate().skip(top).take(LIST_VIS) {
            let ry = ly + (i - top) as f32 * rh;
            if i == sel {
                d.sprite("MENU_FL_Cursor_Wide", x - 8.0, ry + 1.0, w + 16.0, rh - 2.0, if self.kcol == 0 { 1.0 } else { 0.45 });
            }
            let en = &self.codex.entries[e];
            let tag = arch_name(&en.arch, l);
            let tw = d.width(tag, 19.0);
            d.icon(en.top_icon(en.rars[cat]), x + 8.0, ry + 4.0, 42.0, 1.0);
            d.text_clip_mid(x + 60.0, ry + rh / 2.0, w - 90.0 - tw, 23.0, TEXT, 1.0, &en.name[l]);
            d.text_mid(x + w - 14.0 - tw, ry + rh / 2.0, 19.0, DIM, 1.0, tag);
            self.hit(x, ry, w, rh, Hit::KRow(i));
        }
        for i in window(top, LIST_VIS, list.len(), LIST_MARGIN).filter(|&i| i < top || i >= top + LIST_VIS) {
            let en = &self.codex.entries[list[i]];
            d.preload(en.top_icon(en.rars[cat]));
        }
        self.bar(d, Scroll::KRow, x + w + 8.0, ly, rh * LIST_VIS as f32, top, LIST_VIS, list.len());
        // 中：说明
        let (mx, my, mw) = (670.0, 150.0, 720.0);
        d.sprite("MENU_FL_MenuBase", mx - 16.0, my - 8.0, mw + 32.0, 830.0, 0.9);
        let Some(cur) = self.k_cur() else { return };
        let e = self.codex.entries[cur].clone();
        d.sprite("MENU_FL_Rar_d1", mx - 10.0, my, mw + 20.0, 76.0, 0.9);
        d.icon(e.top_icon(e.rars[cat]), mx + 14.0, my + 6.0, 64.0, 1.0);
        d.text_clip(mx + 92.0, my + 10.0, mw - 110.0, 26.0, TEXT, 1.0, &e.name[l]);
        let cats = (0..CATS).filter(|&c| e.rars[c] != 0).map(|c| CAT_NAME[l][c]).collect::<Vec<_>>().join(" / ");
        // 前缀 / 后缀只有防具、骨灰上才有
        let slot = e.mech.filter(|_| ARMOR.iter().chain(&[ASH]).any(|&c| e.rars[c] != 0)).map(|m| if m { ["前缀", "Prefix"][l] } else { ["后缀", "Suffix"][l] });
        let sub = [Some(arch_name(&e.arch, l)), slot].into_iter().flatten().collect::<Vec<_>>().join("  ·  ");
        d.text_clip(mx + 92.0, my + 44.0, mw - 110.0, 19.0, DIM, 1.0, &sub);
        let where_ = self.t("可出现 / 装备部位", "Appears on");
        let lw = d.width(where_, 21.0);
        d.text(mx + 24.0, my + 90.0, 21.0, GOLD, 1.0, where_);
        d.text_clip(mx + 44.0 + lw, my + 90.0, mw - 68.0 - lw, 21.0, TEXT, 1.0, &cats);
        d.sprite("MENU_Line_01", mx + 24.0, my + 122.0, mw - 48.0, 2.0, 0.6);
        let Blocks { lead, rows, notes } = blocks(&e, e.rars[cat], l);
        let labels: Vec<String> = rows.iter().map(|(rs, _)| rar_label(rs, l)).collect();
        // 每档一个带框的图标
        const RI: f32 = 44.0;
        let col = RI + 12.0 + labels.iter().map(|t| d.width(t, 21.0)).fold(0.0, f32::max) + 24.0;
        let (tx, tw) = (mx + 24.0 + col, mw - 48.0 - col);
        let full = mw - 48.0;
        let lines_h = |d: &Draw, v: &[String], w: f32, px: f32, gap: f32| v.iter().map(|n| d.wrap(n, w, px).len() as f32 * px * 1.3 + gap).sum::<f32>();
        // 放不下就缩字（说明特别长的词条）
        let mut px = 21.0;
        for p in [21.0, 19.0, 17.0] {
            px = p;
            let h = lines_h(d, &lead, full, p, 6.0)
                + if lead.is_empty() { 0.0 } else { 24.0 }
                + rows.iter().map(|(_, t)| (d.wrap(t, tw, p).len() as f32 * p * 1.3).max(RI) + 22.0).sum::<f32>()
                + lines_h(d, &notes, full, p.min(19.0), 4.0)
                + if notes.is_empty() { 0.0 } else { 26.0 };
            if h <= 682.0 {
                break;
            }
        }
        let mut ty = my + 136.0;
        for t in &lead {
            ty += d.wrapped(mx + 24.0, ty, full, px, TEXT, 1.0, t) + 6.0;
        }
        if !lead.is_empty() {
            ty += 8.0;
            d.sprite("MENU_Line_01", mx + 24.0, ty, full, 2.0, 0.6);
            ty += 16.0;
        }
        for (k, (rs, body)) in rows.iter().enumerate() {
            let r = rs.last().copied().unwrap_or(0).min(3);
            let n = d.wrap(body, tw, px).len() as f32;
            let h = (n * px * 1.3).max(RI);
            d.icon(e.icon_at(r), mx + 24.0, ty + (h - RI) / 2.0, RI, 1.0);
            d.text_mid(mx + 24.0 + RI + 12.0, ty + h / 2.0, px, RAR[r], 1.0, &labels[k]);
            // 按字的墨迹居中，和图标、稀有度名对齐
            d.wrapped(tx, ty + h / 2.0 - (n - 1.0) * px * 0.65 - TEXT_MID * px, tw, px, TEXT, 1.0, body);
            ty += h + 10.0;
            if k + 1 < rows.len() {
                d.sprite("MENU_Line_01", mx + 24.0, ty, mw - 48.0, 2.0, 0.35);
            }
            ty += 12.0;
        }
        if !notes.is_empty() {
            d.sprite("MENU_Line_01", mx + 24.0, ty + 4.0, mw - 48.0, 2.0, 0.6);
            ty += 20.0;
            for n in &notes {
                ty += d.wrapped(mx + 24.0, ty, mw - 48.0, px.min(19.0), DIM, 1.0, n) + 4.0;
            }
        }
        // 右：相关词条（只有流派词条有，别的这一栏不画）
        let rel = self.codex.related(cur);
        if rel.is_empty() {
            return;
        }
        let (rx, ry, rw) = (1430.0, 150.0, 420.0);
        d.text(rx + 8.0, ry + 12.0, 24.0, GOLD, 1.0, self.t("相关词条", "Related Affixes"));
        d.sprite("MENU_Line_01", rx, ry + 52.0, rw, 3.0, 0.8);
        let (rly, rrh) = (ry + 64.0, 50.0);
        fit_top(&mut self.krtop, self.krel, REL_VIS, rel.len(), self.follow && self.kcol == 1);
        let rtop = self.krtop;
        self.hit(rx, rly, rw, rrh * REL_VIS as f32, Hit::Area(Scroll::KRel));
        for (i, &(k, direct)) in rel.iter().enumerate().skip(rtop).take(REL_VIS) {
            let y1 = rly + (i - rtop) as f32 * rrh;
            if self.kcol == 1 && i == self.krel {
                d.sprite("MENU_FL_Cursor_Wide", rx - 8.0, y1 + 1.0, rw + 16.0, rrh - 2.0, 1.0);
            }
            let tag = if direct { ["联动", "Linked"][l] } else { "" };
            let tagw = if direct { d.width(tag, 19.0) } else { 0.0 };
            let en = &self.codex.entries[k];
            d.icon(en.top_icon(en.rars.iter().fold(0, |m, x| m | x)), rx + 8.0, y1 + 4.0, 42.0, 1.0);
            d.text_clip_mid(rx + 60.0, y1 + rrh / 2.0, rw - 90.0 - tagw, 23.0, if direct { GOLD } else { TEXT }, 1.0, &en.name[l]);
            if direct {
                d.text_mid(rx + rw - 14.0 - tagw, y1 + rrh / 2.0, 19.0, GOLD, 1.0, tag);
            }
            self.hit(rx, y1, rw, rrh, Hit::KRel(i));
        }
        for i in window(rtop, REL_VIS, rel.len(), LIST_MARGIN).filter(|&i| i < rtop || i >= rtop + REL_VIS) {
            let en = &self.codex.entries[rel[i].0];
            d.preload(en.top_icon(en.rars.iter().fold(0, |m, x| m | x)));
        }
        self.bar(d, Scroll::KRel, rx + rw + 8.0, rly, rrh * REL_VIS as f32, rtop, REL_VIS, rel.len());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const LIB: &str = "wspec\tbr\t1\t1\t\t血狂\tFrenzy\t血狂：轻击提升攻击力\\n同名取最高\tFrenzy: light hits\\nStacks no\t8\n\
wspec\toff\t1\t0\t\t停用\tOff\t停用：无\tOff: none\t15\n\
fam\t0\t100\t100\t甲\tA\tkey_a\t3\t1\t-\t法术\n\
famw\t0\t1,1,1,1\t1,1,0,0\n\
famr\t0\t0\t1\t10\t效果1\\n叠加说明\tE1\\nNote\n\
famr\t0\t1\t2\t11\t效果1\\n叠加说明\tE1\\nNote\n\
famr\t0\t2\t3\t-1\t效果2\\n叠加说明\tE2\\nNote\n\
famr\t0\t3\t4\t-1\t效果3\\n叠加说明\tE3\\nNote\n\
fam\t1\t100\t0\t乙\tB\tkey_b\t8\t0\t-\t法术\n\
famw\t1\t0,0,0,1\t0,0,0,0\n\
famr\t1\t3\t5\t-1\t乙的效果\tB effect\n\
fam\t2\t100\t100\t丙\tC\tkey_c\t15\t0\t-\t属性\n\
famw\t2\t1,1,1,1\t1,1,1,1\n\
famr\t2\t0\t6\t12\t力气＋1\tStr +1\n\
fam\t3\t100\t100\t停\tOld\tkey_old\t15\t0\t-\t法术\n\
famw\t3\t0,0,0,0\t0,0,0,0\n\
famr\t3\t0\t7\t13\t旧\tOld\n\
wspecarch\tbr\t法术\n\
famlink\tkey_a\tkey_b,key_old\n";

    fn pos(c: &Codex, key: &str) -> usize {
        c.entries.iter().position(|e| e.key == key).unwrap()
    }

    #[test]
    fn parse_sorts_into_categories_and_drops_retired() {
        let c = Codex::parse(LIB, "");
        assert!(!c.entries.iter().any(|e| e.key == "key_old" || e.key == "off"));
        let (a, b, cc, br) = (pos(&c, "key_a"), pos(&c, "key_b"), pos(&c, "key_c"), pos(&c, "br"));
        assert_eq!(c.lists[WEAPON], vec![br]);
        assert_eq!(c.lists[1], vec![a, cc], "头：流派词条在通用词条前");
        assert_eq!(c.lists[2], vec![a, cc]);
        assert_eq!(c.lists[3], vec![cc]);
        assert_eq!(c.lists[4], vec![b, cc]);
        assert_eq!(c.lists[TALISMAN], vec![a, cc]);
        assert_eq!(c.entries[a].rars[TALISMAN], 0b0011, "护符只出前两档");
        assert_eq!(c.entries[b].rars[4], 0b1000);
        assert_eq!(c.entries[br].arch, "法术");
        assert_eq!(c.entries[br].text[3][0], "轻击提升攻击力\n同名取最高", "武器特效去掉名字前缀");
    }

    #[test]
    fn related_only_for_builds_direct_first() {
        let c = Codex::parse(LIB, "");
        let (a, b, cc, br) = (pos(&c, "key_a"), pos(&c, "key_b"), pos(&c, "key_c"), pos(&c, "br"));
        assert_eq!(c.related(a), vec![(b, true), (br, false)], "停用的联动丢掉，直接联动在前");
        assert!(c.related(cc).is_empty(), "通用词条没有相关词条");
    }

    #[test]
    fn search_jumps_to_a_category_with_results() {
        let mut w = Workshop::default();
        w.codex = Codex::parse(LIB, "");
        w.page = 5;
        w.refresh_views();
        assert_eq!(w.kcat, 0);
        w.set_query("乙的效果");
        assert_eq!(w.kcat, 4, "武器里没有，腿部有");
        assert_eq!(w.v_k.len(), 1);
        assert_eq!(w.k_cur(), Some(pos(&w.codex, "key_b")));
    }

    /// 词条数值随机：famspan 的说明换掉这一档 famr 的；没有的照 famr
    #[test]
    fn value_span_replaces_text() {
        let lib = format!("{LIB}famspan\t2\t0\t力气＋1~4\tStr +1~4\n");
        let c = Codex::parse(&lib, "");
        assert_eq!(c.entries[pos(&c, "key_c")].text[0], ["力气＋1~4".to_string(), "Str +1~4".to_string()]);
        assert_eq!(c.entries[pos(&c, "key_a")].text[0][0], "效果1\n叠加说明", "没有范围的照 famr");
    }

    #[test]
    fn unknown_archetype_still_counts_as_build() {
        let lib = "fam\t0\t1\t1\t新\tN\tn1\t15\t0\t-\t新流派\nfamr\t0\t0\t1\t1\t说明\tT\nfam\t1\t1\t1\t新二\tN2\tn2\t15\t0\t-\t新流派\nfamr\t1\t0\t1\t1\t说明\tT\n";
        let c = Codex::parse(lib, "");
        assert_eq!(c.related(0), vec![(1, false)]);
        assert_eq!(arch_name("新流派", 1), "新流派");
    }

    #[test]
    fn blocks_merge_equal_rarities_and_pull_common_lines() {
        let c = Codex::parse(LIB, "");
        let a = &c.entries[pos(&c, "key_a")];
        let b = blocks(a, a.rars[1], 0);
        assert!(b.lead.is_empty());
        assert_eq!(b.rows, vec![(vec![0, 1], "效果1".to_string()), (vec![2], "效果2".to_string()), (vec![3], "效果3".to_string())]);
        assert_eq!(b.notes, vec!["叠加说明".to_string()]);
        // 只出一档 / 各档一样：第一行留作效果
        let br = &c.entries[pos(&c, "br")];
        let b = blocks(br, br.rars[WEAPON], 0);
        assert!(b.lead.is_empty());
        assert_eq!(b.rows, vec![(vec![3], "轻击提升攻击力".to_string())]);
        assert_eq!(b.notes, vec!["同名取最高".to_string()]);
        assert_eq!(rar_label(&[0, 1], 0), "普通 ~ 稀有");
    }

    #[test]
    fn icons_use_framed_copy_and_fall_back() {
        let lib = "fam\t0\t1\t1\t甲\tA\tk\t15\t0\t-\t法术\nfamr\t0\t0\t1\t1\tx\tx\nfamicon\tk\t100,100,0,56000\n";
        let c = Codex::parse(lib, "# 说明\n100\t0\t50000\n100\t1\t50001\ncustom\tx\t56000\n");
        let e = &c.entries[0];
        assert_eq!(e.icon, [50000, 50001, 0, 56000]);
        assert_eq!(e.icon_at(2), 50000, "这一档没有就用别的档的");
        assert_eq!(e.top_icon(0b0011), 50001);
    }

    #[test]
    fn ash_lines_go_to_their_own_category() {
        let lib = format!(
            "{LIB}ashcx\tash_rally\t集结\tRallying\t1\t18880,18880,18880,18880\t\t\t\t\t\t\t召唤数量＋1\\n最多 5 只\tOne more\\nUp to 5\n\
ashcx\tash_hp\t坚韧\tSturdy\t0\t18000,18000,18000,18000\t血量＋10％\tHP +10%\t血量＋15％\tHP +15%\t血量＋20％\tHP +20%\t血量＋30％\tHP +30%\n"
        );
        let c = Codex::parse(&lib, "18000\t0\t50000\n18000\t3\t50003\n");
        let (ra, hp) = (pos(&c, "ash_rally"), pos(&c, "ash_hp"));
        assert_eq!(c.lists[ASH], vec![ra, hp], "文件里的先后");
        assert_eq!(c.entries[ra].rars, [0, 0, 0, 0, 0, 0, 0b1000], "只进骨灰，只有传说");
        assert_eq!(c.entries[hp].rars[ASH], 15);
        assert!(c.related(hp).is_empty(), "骨灰词条不算流派");
        assert_eq!(c.entries[hp].icon[0], 50000);
        assert_eq!(c.entries[hp].icon[3], 50003);
        assert_eq!(c.entries[ra].mech, Some(true));
        let b = blocks(&c.entries[ra], 0b1000, 0);
        assert_eq!(b.rows, vec![(vec![3], "召唤数量＋1".to_string())]);
        assert_eq!(b.notes, vec!["最多 5 只".to_string()]);
        assert!(!c.lists[TALISMAN].contains(&hp));
    }

    #[test]
    fn blocks_keep_shared_effect_above_the_numbers() {
        let lib = "fam\t0\t1\t1\t甲\tA\tk\t15\t0\t-\t法术\n\
famr\t0\t0\t1\t1\t积蓄力量\\n伤害 10\\n随智力提升\tx\n\
famr\t0\t1\t1\t1\t积蓄力量\\n伤害 20\\n随智力提升\tx\n";
        let c = Codex::parse(lib, "");
        let e = &c.entries[0];
        let b = blocks(e, e.rars[1], 0);
        assert_eq!(b.lead, vec!["积蓄力量".to_string()]);
        assert_eq!(b.rows, vec![(vec![0], "伤害 10".to_string()), (vec![1], "伤害 20".to_string())]);
        assert_eq!(b.notes, vec!["随智力提升".to_string()]);
    }
}
