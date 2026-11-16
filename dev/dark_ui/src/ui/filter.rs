//! 关键词搜索和按词条筛选（用户 2026-11-09「给所有界面都添加关键词搜索 然后给继承重铸超限添加按词条筛选 继承最多可选3个词条 超限武器界面一个 装备界面3个」）：
//!   搜索框：标题栏右边，每页一份关键词（打开窗口时清空）。/ 或 Ctrl+F 开始输入，Enter 结束，Esc 取消；空格分开的几段都要有，不分大小写；打字母按拼音搜（pinyin.rs）。
//!     装备搜名字、词条名和词条说明（武器还有战技、特效、武器类型）；这些文字第一次搜索时才向 dark_core 要（分几帧发完，见 workshop.rs 的 s）。
//!     魇印、咒痕、词条百科的内容界面上本来就有，直接搜。
//!   词条筛选：继承 3 个、重铸 1 个、超限的武器 1 个、超限的防具 3 个（防具最多 3 条词条，武器只有一个特效）；选几个就要同时有这几个。
//!     手柄在列表第一行按上走到标题栏的筛选按钮（A 打开、X 清除、下 / B 回列表），或者按 Start；键盘 F；鼠标点按钮。只列这一页（当前页签）装备身上有的词条，后面是选上它之后还剩几件。
//!   列表（v_src / v_wpn / v_ovl / v_k）跟着页签、关键词、词条筛选变（refresh_views），关键词或筛选一变就回到第一行。
//!   继承页排序（用户 2026-11-10「给装备工坊的继承界面加根据减伤率和重量排序 下拉框自己选按哪个 然后可以升序降序」）：
//!     标题栏搜索框右边一个下拉（默认 / 稀有度 / 减伤率 / 重量；稀有度是用户 2026-11-11 加的）和一个升序 / 降序按钮，左边的来源、右边的目标一起按它排；
//!     减伤率 = 八种减伤的平均，和重量都是游戏参数里这件现在的数（dark_core 索引 a 行最后两列）。默认 = 穿着的在前、按获得时间（降序 = 新的在前）；
//!     按稀有度 / 减伤率 / 重量排时一样的再按默认的顺序。换排序时选中的来源跟着走。
//!     手柄：列表第一行按上到标题栏（落在词条筛选上），左右在 排序 / 升降序 / 词条筛选 之间走，A 打开 / 切换，X 恢复默认。
use super::reforge::wtype_name;
use super::*;

/// 词条筛选窗口一屏几行
pub(super) const PICK_VIS: usize = 12;

/// 继承页的排序有几种：0 默认、1 稀有度、2 减伤率、3 重量
pub(super) const SORT_N: usize = 4;
/// 继承页的排序：名字（中 / 英）、下拉菜单里的说明
const SORT_NAMES: [[&str; SORT_N]; 2] = [["默认", "稀有度", "减伤率", "重量"], ["Default", "Rarity", "Negation", "Weight"]];
const SORT_HINTS: [[&str; SORT_N]; 2] = [
    ["穿着的在前，按获得时间", "普通、稀有、史诗、传说", "八种减伤的平均", "装备重量"],
    ["Worn first, then by time acquired", "Common, Rare, Epic, Legendary", "Average of all eight negations", "Equip weight"],
];
/// 标题栏里排序下拉、升降序按钮的宽度
const SORT_W: f32 = 176.0;
const ORD_W: f32 = 64.0;

/// 继承页的排序（来源、目标都用）：0 默认（穿着的在前、按获得顺序；降序 = 新的在前）、1 稀有度（降序 = 传说在前）、2 减伤率、3 重量
/// （一样的按默认的顺序）
pub(super) fn order_pieces(s: &Snap, v: &mut [usize], sort: usize, asc: bool) {
    let p = &s.pieces;
    let base = |i: usize| (!p[i].worn, std::cmp::Reverse(p[i].sort));
    match sort {
        1..=3 => {
            let val = |i: usize| match sort {
                1 => p[i].rar as f32,
                2 => p[i].cut,
                _ => p[i].weight,
            };
            v.sort_by(|&a, &b| {
                let o = val(a).partial_cmp(&val(b)).unwrap_or(std::cmp::Ordering::Equal);
                (if asc { o } else { o.reverse() }).then_with(|| base(a).cmp(&base(b)))
            });
        }
        _ => v.sort_by_key(|&i| (!p[i].worn, if asc { p[i].sort as i64 } else { -(p[i].sort as i64) })),
    }
}

/// 词条筛选窗口
#[derive(Default)]
pub(super) struct Picker {
    pub(super) sel: usize,
    pub(super) top: usize,
    query: String,
    /// 能选的词条：键、选上它之后还剩几件
    rows: Vec<(String, usize)>,
}

/// 列表跟着这些变
#[derive(PartialEq, Clone, Default)]
pub(super) struct ViewKey {
    gen_: u64,
    filter: usize,
    rfilter: usize,
    otab: usize,
    kcat: usize,
    q: [String; 6],
    kf: [Vec<String>; 4],
    sort: usize,
    asc: bool,
}

/// 关键词拆成几段（空格分开，每段都要有），不分大小写
pub(super) fn terms_of(q: &str) -> Vec<String> {
    q.to_lowercase().split_whitespace().map(String::from).collect()
}

/// 每段都要有：原样出现，或者（全是字母的）读音对得上。hay 是小写的，\x01 前是名字、后是说明
pub(super) fn has_all(terms: &[String], hay: &str) -> bool {
    terms.iter().all(|t| hay.contains(t.as_str()) || (t.bytes().all(|b| b.is_ascii_lowercase()) && pinyin::matches(hay, t)))
}

fn piece_ok(s: &Snap, p: &Piece, terms: &[String], kf: &[String], l: usize) -> bool {
    if !kf.iter().all(|k| p.keys.contains(k)) {
        return false;
    }
    if terms.is_empty() {
        return true;
    }
    let text = s.search.get(&(0, p.idx)).cloned().unwrap_or_else(|| p.name.to_lowercase());
    has_all(terms, &format!("{} {text}", PART[l].get(p.part).unwrap_or(&"").to_lowercase()))
}

fn weapon_ok(s: &Snap, w: &Wpn, terms: &[String], kf: &[String], l: usize) -> bool {
    if !kf.iter().all(|k| w.spec == *k) {
        return false;
    }
    if terms.is_empty() {
        return true;
    }
    let text = s.search.get(&(1, w.idx)).cloned().unwrap_or_else(|| w.name.to_lowercase());
    has_all(terms, &format!("{} {text}", wtype_name(w.wtype, l).to_lowercase()))
}

impl Workshop {
    /// 正在往输入框里打字（键盘不当操作用）
    pub fn typing(&self) -> bool {
        self.typing
    }

    /// 设这一页的关键词（离线预览、测试用）
    pub fn set_query(&mut self, q: &str) {
        self.query[self.page.min(5)] = q.to_string();
        self.refresh_views();
    }

    /// 这一页的关键词（拆好的）
    pub(super) fn terms(&self, page: usize) -> Vec<String> {
        terms_of(&self.query[page.min(5)])
    }

    /// 这一页的词条筛选：（第几份, 最多选几个）；没有筛选的页是 None
    pub(super) fn kf_slot(&self) -> Option<(usize, usize)> {
        match (self.page, self.otab) {
            (0, _) => Some((0, 3)),
            (1, _) => Some((1, 1)),
            (2, 0) => Some((2, 1)),
            (2, _) => Some((3, 3)),
            _ => None,
        }
    }

    /// 关键词或者词条筛选在起作用（列表空了要说「没有符合条件的」）
    pub(super) fn filtering(&self) -> bool {
        !self.terms(self.page).is_empty() || self.kf_slot().is_some_and(|(k, _)| !self.kf[k].is_empty())
    }

    /// 页签、关键词、词条筛选、快照变了就重算列表；关键词或筛选一变回到第一行
    pub(super) fn refresh_views(&mut self) {
        let key = ViewKey {
            gen_: self.snap_gen,
            filter: self.filter.min(4),
            rfilter: self.rfilter.min(3),
            otab: self.otab.min(1),
            kcat: self.kcat,
            q: self.query.clone(),
            kf: self.kf.clone(),
            sort: self.sort.min(SORT_N - 1),
            asc: self.asc,
        };
        if self.view_key.as_ref() == Some(&key) {
            return;
        }
        let prev_src = self.v_src.get(self.sel[0]).copied();
        let old = self.view_key.replace(key.clone());
        let l = self.lang().min(1);
        let t: [Vec<String>; 6] = std::array::from_fn(|i| terms_of(&key.q[i]));
        if let Some(s) = &self.snap {
            self.v_src = s.src_view[key.filter].iter().copied().filter(|&i| piece_ok(s, &s.pieces[i], &t[0], &key.kf[0], l)).collect();
            let mut tgt = s.tgt_view.clone();
            if (key.sort, key.asc) != (0, false) {
                order_pieces(s, &mut self.v_src, key.sort, key.asc);
                order_pieces(s, &mut tgt, key.sort, key.asc);
            }
            self.tgt_rank = tgt.iter().enumerate().map(|(r, &i)| (s.pieces[i].idx, r)).collect();
            self.v_tgt = tgt;
            self.v_wpn = s.wpn_view[key.rfilter].iter().copied().filter(|&i| weapon_ok(s, &s.weapons[i], &t[1], &key.kf[1], l)).collect();
            self.v_ovl = if key.otab == 0 {
                s.ovl_view[0].iter().copied().filter(|&i| weapon_ok(s, &s.weapons[i], &t[2], &key.kf[2], l)).collect()
            } else {
                s.ovl_view[1].iter().copied().filter(|&i| piece_ok(s, &s.pieces[i], &t[2], &key.kf[3], l)).collect()
            };
        } else {
            self.v_src.clear();
            self.v_wpn.clear();
            self.v_ovl.clear();
            self.v_tgt.clear();
            self.tgt_rank.clear();
        }
        self.v_k = self.codex_filtered(key.kcat, &t[5]);
        // 百科搜索：这一类没有结果就跳到第一个有结果的类别
        if self.v_k.is_empty() && !t[5].is_empty() && old.as_ref().is_some_and(|o| o.q[5] != key.q[5]) {
            if let Some((c, v)) = self.codex_first_hit(&t[5]) {
                self.kcat = c;
                self.v_k = v;
                if let Some(k) = &mut self.view_key {
                    k.kcat = c;
                }
            }
        }
        let Some(o) = old else { return };
        // 换了排序（关键词、筛选没变）：选中的来源跟着走，目标格子回到第一格
        if (o.sort, o.asc) != (key.sort, key.asc) && o.q[0] == key.q[0] && o.kf[0] == key.kf[0] && o.filter == key.filter {
            self.sel[0] = prev_src.and_then(|p| self.v_src.iter().position(|&x| x == p)).unwrap_or(0);
            self.sel[2] = 0;
            self.top[2] = 0;
            self.follow = true;
        }
        if o.q[0] != key.q[0] || o.kf[0] != key.kf[0] {
            self.sel = [0; 4];
            self.top = [0; 4];
            self.col = 0;
        }
        if o.q[1] != key.q[1] || o.kf[1] != key.kf[1] {
            (self.rsel, self.rtop, self.rcol) = (0, 0, 0);
        }
        if o.q[2] != key.q[2] || o.kf[2] != key.kf[2] || o.kf[3] != key.kf[3] {
            (self.osel, self.otop, self.ocol) = (0, 0, 0);
        }
        if o.q[3] != key.q[3] {
            (self.nsel, self.ncol) = (0, 0);
        }
        if o.q[4] != key.q[4] {
            self.csel = 0;
        }
        if o.q[5] != key.q[5] {
            self.codex_reset_sel();
        }
    }

    // ------------------------------------------------------------ 词条筛选窗口
    pub(super) fn open_picker(&mut self) {
        if self.kf_slot().is_some() {
            self.picker = Some(Picker::default());
            self.rebuild_pick();
        }
    }

    /// 这一页（当前页签）的装备身上有的词条，和选上它之后还剩几件
    fn rebuild_pick(&mut self) {
        let (Some((slot, cap)), Some(s)) = (self.kf_slot(), &self.snap) else { return };
        let pieces = |v: &[usize]| -> Vec<Vec<String>> { v.iter().map(|&i| s.pieces[i].keys.clone()).collect() };
        let weapons = |v: &[usize]| -> Vec<Vec<String>> { v.iter().map(|&i| vec![s.weapons[i].spec.clone()]).collect() };
        let items = match (self.page, self.otab) {
            (0, _) => pieces(&s.src_view[self.filter.min(4)]),
            (1, _) => weapons(&s.wpn_view[self.rfilter.min(3)]),
            (_, 0) => weapons(&s.ovl_view[0]),
            _ => pieces(&s.ovl_view[1]),
        };
        let chosen = &self.kf[slot];
        let mut keys: Vec<&String> = items.iter().flatten().filter(|k| !k.is_empty()).chain(chosen).collect();
        keys.sort_by_key(|k| (self.codex.key_order(k), k.to_string()));
        keys.dedup();
        // 只能选一个的：选它就换掉原来的，只看它自己
        let others: &[String] = if cap == 1 { &[] } else { chosen };
        let rows: Vec<(String, usize)> = keys.iter().map(|k| ((*k).clone(), items.iter().filter(|it| it.contains(k) && others.iter().all(|c| it.contains(c))).count())).collect();
        if let Some(p) = &mut self.picker {
            p.rows = rows;
        }
    }

    /// 窗口里现在列出来的（窗口自己的搜索框筛过）
    pub(super) fn pick_rows(&self) -> Vec<(String, usize)> {
        let Some(p) = &self.picker else { return Vec::new() };
        let terms = terms_of(&p.query);
        p.rows.iter().filter(|r| has_all(&terms, &self.codex.key_hay(&r.0))).cloned().collect()
    }

    fn picker_toggle(&mut self, i: usize) {
        let Some((slot, cap)) = self.kf_slot() else { return };
        let Some(key) = self.pick_rows().get(i).map(|r| r.0.clone()) else { return };
        let v = &mut self.kf[slot];
        if let Some(p) = v.iter().position(|k| *k == key) {
            v.remove(p);
        } else if cap == 1 {
            *v = vec![key];
        } else if v.len() < cap {
            v.push(key);
        } else {
            self.msg = Some((false, if self.lang() == 0 { format!("最多选 {cap} 个词条") } else { format!("Up to {cap} affixes") }));
            return;
        }
        self.msg = None;
        self.rebuild_pick();
    }

    pub(super) fn picker_click(&mut self, i: usize) {
        if let Some(p) = &mut self.picker {
            p.sel = i;
        }
        self.picker_toggle(i);
    }

    pub(super) fn kf_clear(&mut self) {
        if let Some((slot, _)) = self.kf_slot() {
            self.kf[slot].clear();
            self.rebuild_pick();
        }
    }

    pub(super) fn query_clear(&mut self) {
        self.query[self.page.min(5)].clear();
    }

    /// 手柄 / 方向键：在列表第一行再往上就走到标题栏的筛选按钮
    pub(super) fn at_list_top(&self) -> bool {
        self.kf_slot().is_some()
            && match self.page {
                0 => self.col == 0 && self.sel[0] == 0,
                1 => self.rcol == 0 && self.rsel == 0,
                _ => self.ocol == 0 && self.osel == 0,
            }
    }

    /// 光标在标题栏：继承页左右在 排序 / 升降序 / 词条筛选 之间走；排序上 A 打开下拉、升降序上 A 切换、X 恢复默认；
    /// 筛选按钮上 A 打开、X 清除；下 / B 回列表
    pub(super) fn handle_head(&mut self, a: Act) {
        let at = if self.page == 0 { self.head_at.min(2) } else { 2 };
        if a.down || a.b {
            self.head = false;
        } else if self.page == 0 && a.left && at > 0 {
            self.head_at = at - 1;
        } else if self.page == 0 && a.right && at < 2 {
            self.head_at = at + 1;
        } else if at == 0 && a.a {
            self.toggle_sort_menu();
        } else if at == 1 && a.a {
            self.toggle_order();
        } else if at < 2 && a.x {
            (self.sort, self.asc) = (0, false);
            self.refresh_views();
        } else if a.a {
            self.open_picker();
        } else if a.x {
            self.kf_clear();
        }
    }

    // ------------------------------------------------------------ 继承页排序
    pub(super) fn toggle_sort_menu(&mut self) {
        self.sort_menu = if self.sort_menu.is_some() || self.page != 0 { None } else { Some(self.sort.min(SORT_N - 1)) };
    }

    pub(super) fn toggle_order(&mut self) {
        self.asc = !self.asc;
        self.sort_menu = None;
        self.refresh_views();
    }

    pub(super) fn pick_sort(&mut self, i: usize) {
        self.sort = i.min(SORT_N - 1);
        self.sort_menu = None;
        self.refresh_views();
    }

    /// 下拉菜单开着：上下选、A 定、B 关
    pub(super) fn handle_sort_menu(&mut self, a: Act) {
        let Some(cur) = self.sort_menu else { return };
        if a.up && cur > 0 {
            self.sort_menu = Some(cur - 1);
        } else if a.down && cur + 1 < SORT_N {
            self.sort_menu = Some(cur + 1);
        } else if a.a {
            self.pick_sort(cur);
        } else if a.b || a.lt || a.rt {
            self.sort_menu = None;
        }
    }

    /// 标题栏：排序下拉（名字后面一个小三角）、升序 / 降序
    fn draw_sort_btns(&mut self, d: &mut Draw, x: f32, y: f32, h: f32) {
        let l = self.lang().min(1);
        d.rect(x, y, SORT_W, h, [18, 16, 11], 0.85);
        d.sprite("MENU_Line_01", x, y + h - 2.0, SORT_W, 2.0, 0.7);
        if self.head && self.head_at == 0 {
            d.sprite("MENU_FL_Cursor_Wide", x - 6.0, y + 1.0, SORT_W + 12.0, h - 2.0, 1.0);
        }
        let on = (self.sort, self.asc) != (0, false);
        let t = format!("{}{}", self.t("排序：", "Sort: "), SORT_NAMES[l][self.sort.min(SORT_N - 1)]);
        d.text_clip_mid(x + 12.0, y + h / 2.0, SORT_W - 40.0, 22.0, if on { GOLD } else { TEXT }, 1.0, &t);
        // 小三角（字体里不一定有 ▾，用几条横线拼）：开着朝上、关着朝下
        let (cx, cy) = (x + SORT_W - 18.0, y + h / 2.0);
        for r in 0..6 {
            let half = if self.sort_menu.is_some() { r as f32 } else { (5 - r) as f32 };
            d.rect(cx - half - 0.5, cy - 3.0 + r as f32, half * 2.0 + 1.0, 1.0, if on { GOLD } else { TEXT }, 0.9);
        }
        self.hit(x, y, SORT_W, h, Hit::SortBtn);
        let ox = x + SORT_W + 8.0;
        d.rect(ox, y, ORD_W, h, [18, 16, 11], 0.85);
        d.sprite("MENU_Line_01", ox, y + h - 2.0, ORD_W, 2.0, 0.7);
        if self.head && self.head_at == 1 {
            d.sprite("MENU_FL_Cursor_Wide", ox - 6.0, y + 1.0, ORD_W + 12.0, h - 2.0, 1.0);
        }
        let o = if self.asc { self.t("升序", "Asc") } else { self.t("降序", "Desc") }.to_string();
        let ow = d.width(&o, 22.0);
        d.text_mid(ox + (ORD_W - ow) / 2.0, y + h / 2.0, 22.0, if self.asc { GOLD } else { TEXT }, 1.0, &o);
        self.hit(ox, y, ORD_W, h, Hit::SortOrd);
    }

    /// 排序的下拉菜单：标题栏下面，一种一行（名字 + 说明），现在用的标金色
    pub(super) fn draw_sort_menu(&mut self, d: &mut Draw) {
        if self.page != 0 {
            self.sort_menu = None;
            return;
        }
        let Some(cur) = self.sort_menu else { return };
        let l = self.lang().min(1);
        let (x, y, w, rh) = (900.0 + 250.0 + 12.0, 102.0, 420.0, 54.0);
        d.rect(x - 8.0, y - 4.0, w + 16.0, rh * SORT_N as f32 + 12.0, [12, 11, 8], 0.97);
        d.sprite("MENU_FL_MenuBase", x - 8.0, y - 4.0, w + 16.0, rh * SORT_N as f32 + 12.0, 1.0);
        for i in 0..SORT_N {
            let ry = y + 2.0 + i as f32 * rh;
            if i == cur {
                d.sprite("MENU_FL_Cursor_Wide", x - 6.0, ry + 1.0, w + 12.0, rh - 2.0, 1.0);
            }
            let chosen = i == self.sort.min(SORT_N - 1);
            d.text_mid(x + 14.0, ry + rh / 2.0, 24.0, if chosen { GOLD } else { TEXT }, 1.0, SORT_NAMES[l][i]);
            let nw = d.width(SORT_NAMES[l][i], 24.0);
            d.text_clip_mid(x + 30.0 + nw, ry + rh / 2.0, w - 44.0 - nw, 19.0, DIM, 1.0, SORT_HINTS[l][i]);
            self.hit(x, ry, w, rh, Hit::SortRow(i));
        }
    }

    pub(super) fn handle_picker(&mut self, a: Act) {
        let n = self.pick_rows().len();
        let Some(p) = &mut self.picker else { return };
        p.sel = p.sel.min(n.saturating_sub(1));
        if a.up && p.sel > 0 {
            p.sel -= 1;
        }
        if a.down && p.sel + 1 < n {
            p.sel += 1;
        }
        let sel = p.sel;
        if a.a {
            self.picker_toggle(sel);
        } else if a.x {
            self.kf_clear();
        } else if a.b || a.filter {
            self.picker = None;
        }
    }

    // ------------------------------------------------------------ 画
    /// 标题栏右边：搜索框、词条筛选按钮
    pub(super) fn draw_search(&mut self, d: &mut Draw) {
        let sorting = self.page == 0;
        let (x, y, w, h) = (900.0, 58.0, if sorting { 250.0 } else { 350.0 }, 40.0);
        let p = self.page.min(5);
        if self.picker.is_none() && !self.confirm {
            let hint = self.t("拼音搜索（按 / 输入）", "Search (press /)").to_string();
            let focus = std::mem::take(&mut self.focus_search);
            self.typing |= d.input("##dr_q", x, y, w - 40.0, h, &mut self.query[p], &hint, focus);
            if !self.query[p].is_empty() {
                d.rect(x + w - 40.0, y, 40.0, h, [18, 16, 11], 0.85);
                d.text_mid(x + w - 28.0, y + h / 2.0, 26.0, DIM, 1.0, "×");
                self.hit(x + w - 40.0, y, 40.0, h, Hit::QClear);
            } else {
                d.rect(x + w - 40.0, y, 40.0, h, [18, 16, 11], 0.85);
            }
        } else {
            d.rect(x, y, w, h, [18, 16, 11], 0.85);
            d.text_clip_mid(x + 12.0, y + h / 2.0, w - 24.0, 22.0, TEXT, 1.0, &self.query[p]);
        }
        let mut bx = x + w + 12.0;
        if sorting {
            self.draw_sort_btns(d, bx, y, h);
            bx += SORT_W + 8.0 + ORD_W + 12.0;
        }
        let Some((slot, cap)) = self.kf_slot() else { return };
        let bw = if sorting { 176.0 } else { 190.0 };
        let n = self.kf[slot].len();
        d.rect(bx, y, bw, h, [18, 16, 11], 0.85);
        d.sprite("MENU_Line_01", bx, y + h - 2.0, bw, 2.0, 0.7);
        if self.head && (!sorting || self.head_at >= 2) {
            d.sprite("MENU_FL_Cursor_Wide", bx - 6.0, y + 1.0, bw + 12.0, h - 2.0, 1.0);
        }
        let t = format!("{} {n}/{cap}", self.t("词条筛选", "Affix filter"));
        d.text_clip_mid(bx + 14.0, y + h / 2.0, bw - 20.0, 22.0, if n > 0 { GOLD } else { TEXT }, 1.0, &t);
        self.hit(bx, y, bw, h, Hit::KfBtn);
    }

    /// 左栏列表下面一行：筛的是哪几个词条（能清除）、搜索文字还在加载
    pub(super) fn draw_kf_strip(&mut self, d: &mut Draw, x: f32, y: f32, w: f32) {
        let Some((slot, _)) = self.kf_slot() else { return };
        let l = self.lang().min(1);
        let searching = !self.terms(self.page).is_empty() && self.snap.as_ref().is_some_and(|s| s.lazy && !s.search_done);
        if self.kf[slot].is_empty() {
            if searching {
                d.text_mid(x + 8.0, y + 16.0, 20.0, DIM, 1.0, self.t("搜索中……", "Searching…"));
            }
            return;
        }
        let names = self.kf[slot].iter().map(|k| self.codex.key_name(k, l)).collect::<Vec<_>>().join(" · ");
        d.text_clip_mid(x + 8.0, y + 16.0, w - 60.0, 20.0, GOLD, 1.0, &format!("{}{names}", self.t("筛选：", "Filter: ")));
        d.text_mid(x + w - 32.0, y + 16.0, 26.0, DIM, 1.0, "×");
        self.hit(x + w - 48.0, y, 48.0, 32.0, Hit::KfClear);
    }

    pub(super) fn draw_picker(&mut self, d: &mut Draw) {
        let Some((slot, cap)) = self.kf_slot() else { return };
        let l = self.lang().min(1);
        d.rect(-2000.0, -2000.0, 6000.0, 6000.0, [0, 0, 0], 0.62);
        let (x, y, w) = (480.0, 120.0, 960.0);
        d.rect(x - 16.0, y - 8.0, w + 32.0, 860.0, [12, 11, 8], 0.96);
        d.sprite("MENU_FL_MenuBase", x - 16.0, y - 8.0, w + 32.0, 860.0, 1.0);
        let title = format!("{}  {}/{cap}", self.t("按词条筛选", "Filter by affix"), self.kf[slot].len());
        d.text(x + 16.0, y + 14.0, 28.0, GOLD, 1.0, &title);
        let hint = self.t("拼音搜索词条（按 / 输入）", "Find an affix (press /)").to_string();
        let focus = std::mem::take(&mut self.focus_search);
        if let Some(p) = &mut self.picker {
            self.typing |= d.input("##dr_pq", x + w - 380.0, y + 10.0, 380.0, 42.0, &mut p.query, &hint, focus);
        }
        d.sprite("MENU_Line_01", x, y + 62.0, w, 3.0, 0.8);
        let rows = self.pick_rows();
        let (ly, rh, vis) = (y + 72.0, 56.0, PICK_VIS);
        let follow = self.follow;
        let Some(p) = &mut self.picker else { return };
        p.sel = p.sel.min(rows.len().saturating_sub(1));
        fit_top(&mut p.top, p.sel, vis, rows.len(), follow);
        let (sel, top) = (p.sel, p.top);
        self.hit(x, ly, w, rh * vis as f32, Hit::Area(Scroll::Pick));
        if rows.is_empty() {
            d.wrapped(x + 20.0, ly + 20.0, w - 40.0, 22.0, DIM, 1.0, self.t("这一页的装备身上没有词条，或者没有符合搜索的词条", "No affixes on the gear in this tab, or none match your search"));
        }
        for i in window(top, vis, rows.len(), 0) {
            let (key, n) = &rows[i];
            let ry = ly + (i - top) as f32 * rh;
            if i == sel {
                d.sprite("MENU_FL_Cursor_Wide", x - 8.0, ry + 1.0, w + 16.0, rh - 2.0, 1.0);
            }
            let chosen = self.kf[slot].contains(key);
            let a = if *n > 0 || chosen { 1.0 } else { 0.45 };
            d.icon(self.codex.key_icon(key), x + 10.0, ry + 5.0, 46.0, a);
            d.text_clip_mid(x + 70.0, ry + rh / 2.0, w - 260.0, 24.0, if chosen { GOLD } else { TEXT }, a, &self.codex.key_name(key, l));
            let cnt = if l == 0 { format!("{n} 件") } else { format!("{n}") };
            let cw = d.width(&cnt, 20.0);
            d.text_mid(x + w - 16.0 - cw, ry + rh / 2.0, 20.0, DIM, 1.0, &cnt);
            if chosen {
                let tag = self.t("已选", "Selected");
                d.text_mid(x + w - 100.0 - d.width(tag, 20.0), ry + rh / 2.0, 20.0, GOLD, 1.0, tag);
            }
            self.hit(x, ry, w, rh, Hit::PRow(i));
        }
        for i in window(top, vis, rows.len(), LIST_MARGIN).filter(|&i| i < top || i >= top + vis) {
            d.preload(self.codex.key_icon(&rows[i].0));
        }
        self.bar(d, Scroll::Pick, x + w + 8.0, ly, rh * vis as f32, top, vis, rows.len());
        self.draw_guide(d);
    }
}
