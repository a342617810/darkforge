//! 「魇印」页（赐福「暗黑重铸」→「魇印」单独打开，不在装备工坊里；用户 2026-11-03，魇化精英；规则在 dark_core 的 nightmare.rs）：
//!   左：14 种能夺的词条（名字、等级、夺取次数 / 下一级要几次），没夺到过的变暗
//!   中：选中那种的说明：现在这一级、下一级；下面是身上的魇火
//!   右：5 个刻印位（没开的写开启条件），刻的是哪种、几级
//! 操作：上下选词条，A 到右边、上下选刻印位、再 A 刻上（同一种刻在别的位上会对调）；X 取下这一位；B 返回 / 关窗口。刻印不消耗东西，不弹确认。
use super::*;

/// 精英的强化（词条分组，同 rr/nightmare.py 的 BUFFS）；字一律魇化描边的紫色（用户 2026-11-03：以前按强化分红 / 蓝 / 金 / 绿）
const NCOL: [u8; 3] = [190, 120, 255];
const NCOL_NAME: [[&str; 4]; 2] = [["攻击", "迅捷", "坚韧", "再生"], ["Might", "Swiftness", "Fortitude", "Renewal"]];
const ROMAN: [&str; 5] = ["—", "I", "II", "III", "IV"]; // 游戏字体里没有 Ⅰ~Ⅳ（显示成「?」）
/// 各级用哪个稀有度的效果（Ⅰ 普通 … Ⅳ 传说）
const LV_RAR: [usize; 4] = [0, 1, 2, 3];

impl Workshop {
    /// 左边的词条（按关键词筛过）
    fn nfams(&self) -> Vec<NmFam> {
        let terms = self.terms(3);
        let Some(s) = &self.snap else { return Vec::new() };
        s.nm_fams.iter().filter(|f| filter::has_all(&terms, &format!("{}\x01{} {}", f.name, f.now, f.up).to_lowercase())).cloned().collect()
    }

    pub(super) fn handle_seal(&mut self, a: Act) {
        let n = self.nfams().len();
        self.nsel = self.nsel.min(n.saturating_sub(1));
        if self.ncol == 0 {
            if a.up && self.nsel > 0 {
                self.nsel -= 1;
            }
            if a.down && self.nsel + 1 < n {
                self.nsel += 1;
            }
            if (a.a || a.right || a.rb) && n > 0 {
                self.ncol = 1;
            }
            if a.b {
                self.reqs.push(Req::Close);
            }
            return;
        }
        if a.up && self.nslot > 0 {
            self.nslot -= 1;
        }
        if a.down && self.nslot + 1 < NM_SLOTS {
            self.nslot += 1;
        }
        if a.a || a.y {
            self.seal_go(Some(self.nsel));
        } else if a.x {
            self.seal_go(None);
        } else if a.b || a.left || a.lb {
            self.ncol = 0;
        }
    }

    fn seal_go(&mut self, fam: Option<usize>) {
        let fam = match fam {
            Some(i) => match self.nfams().get(i) {
                Some(f) => Some(f.idx),
                None => return,
            },
            None => None,
        };
        self.reqs.push(Req::Seal { slot: self.nslot, fam });
        self.waiting = true;
        self.msg = Some((true, self.t("处理中……", "Working…").to_string()));
    }

    pub(super) fn click_seal(&mut self, h: Hit) {
        match h {
            Hit::NFam(i) => {
                self.ncol = 0;
                self.nsel = i;
            }
            Hit::NSlot(i) => {
                let again = self.ncol == 1 && self.nslot == i;
                self.ncol = 1;
                self.nslot = i.min(NM_SLOTS - 1);
                if again {
                    self.seal_go(Some(self.nsel));
                }
            }
            _ => {}
        }
    }

    pub(super) fn draw_seal(&mut self, d: &mut Draw) {
        let l = self.lang();
        let fams = self.nfams();
        // 魇火、刻印位按全部词条查（筛选只影响左边的列表）
        let all: Vec<NmFam> = self.snap.as_ref().map(|s| s.nm_fams.clone()).unwrap_or_default();
        let (open, slots, need, embers) = self.snap.as_ref().map_or((0, [None; NM_SLOTS], Vec::new(), Vec::new()), |s| (s.nm_open, s.nm_slots, s.nm_need.clone(), s.nm_embers.clone()));
        // 左：词条列表
        let (x, y, w) = (70.0, 150.0, 520.0);
        d.sprite("MENU_BaseMain_02", x - 20.0, y - 10.0, w + 60.0, 820.0, 0.55);
        d.text(x + 8.0, y + 12.0, 24.0, GOLD, 1.0, self.t("魇化词条", "Nightmare Affixes"));
        d.sprite("MENU_Line_01", x, y + 52.0, w, 3.0, 0.8);
        if fams.is_empty() {
            let msg = if all.is_empty() { self.t("这次没开魇化（重随设置 nightmare）", "Nightmare seals are disabled") } else { self.t("没有符合搜索的词条", "No affixes match") };
            d.wrapped(x + 20.0, y + 80.0, w - 40.0, 22.0, DIM, 1.0, msg);
        }
        let (ly, rh) = (y + 64.0, 52.0);
        for (i, f) in fams.iter().enumerate() {
            let ry = ly + i as f32 * rh;
            if i == self.nsel {
                d.sprite("MENU_FL_Cursor_Wide", x - 8.0, ry + 1.0, w + 16.0, rh - 2.0, if self.ncol == 0 { 1.0 } else { 0.45 });
            }
            let got = f.count > 0;
            d.icon(f.icon, x + 8.0, ry + 3.0, 46.0, if got { 1.0 } else { 0.3 });
            d.text_clip(x + 66.0, ry + 13.0, 200.0, 22.0, if got { TEXT } else { DIM }, 1.0, &f.name);
            d.text(x + 280.0, ry + 13.0, 22.0, if f.level > 0 { GOLD } else { DIM }, 1.0, ROMAN[f.level.min(4)]);
            let cnt = if f.next > 0 { format!("{} / {}", f.count, f.next) } else if l == 0 { format!("{}（满级）", f.count) } else { format!("{} (max)", f.count) };
            let cw = d.width(&cnt, 19.0);
            d.text(x + w - 14.0 - cw, ry + 15.0, 19.0, DIM, 1.0, &cnt);
            self.hit(x, ry, w, rh, Hit::NFam(i));
        }
        // 中：说明 + 魇火
        let (mx, my, mw) = (630.0, 150.0, 760.0);
        d.sprite("MENU_FL_MenuBase", mx - 16.0, my - 8.0, mw + 32.0, 830.0, 0.9);
        if let Some(f) = fams.get(self.nsel) {
            d.sprite("MENU_FL_Rar_d1", mx - 10.0, my, mw + 20.0, 76.0, 0.9);
            d.icon(f.icon, mx + 14.0, my + 6.0, 64.0, if f.count > 0 { 1.0 } else { 0.4 });
            d.text_clip(mx + 92.0, my + 10.0, mw - 110.0, 26.0, TEXT, 1.0, &f.name);
            let sub = if l == 0 {
                format!("  ·  魇印 {}  ·  夺取 {} 次", ROMAN[f.level.min(4)], f.count)
            } else {
                format!("  ·  Seal {}  ·  seized {}×", ROMAN[f.level.min(4)], f.count)
            };
            // 敌人身上那一类的颜色：只在这一行的类别名上
            let cat = NCOL_NAME[l.min(1)][f.color.min(3)];
            d.text(mx + 92.0, my + 44.0, 19.0, NCOL, 1.0, cat);
            let cw = d.width(cat, 19.0);
            d.text_clip(mx + 92.0 + cw, my + 44.0, mw - 110.0 - cw, 19.0, DIM, 1.0, &sub);
            let mut ty = my + 100.0;
            if f.level > 0 {
                let h = if l == 0 {
                    format!("现在（{} · {}）", ROMAN[f.level], RAR_NAME[0][LV_RAR[f.level - 1]])
                } else {
                    format!("Now ({} · {})", ROMAN[f.level], RAR_NAME[1][LV_RAR[f.level - 1]])
                };
                self.section(d, mx + 16.0, ty, mw - 32.0, &h);
                ty += 44.0;
                ty += d.wrapped(mx + 28.0, ty, mw - 56.0, 21.0, TEXT, 1.0, &f.now) + 20.0;
            }
            if f.level < 4 && !f.up.is_empty() {
                let h = match (l, f.level) {
                    (0, 0) => format!("夺取 {} 次解锁（I · {}）", f.next.max(1), RAR_NAME[0][0]),
                    (0, lv) => format!("下一级（{} · {}，还要 {} 次）", ROMAN[lv + 1], RAR_NAME[0][LV_RAR[lv]], f.next.saturating_sub(f.count)),
                    (_, 0) => format!("Unlocks after {} seizure(s) (I · {})", f.next.max(1), RAR_NAME[1][0]),
                    (_, lv) => format!("Next ({} · {}, {} more)", ROMAN[lv + 1], RAR_NAME[1][LV_RAR[lv]], f.next.saturating_sub(f.count)),
                };
                self.section(d, mx + 16.0, ty, mw - 32.0, &h);
                ty += 44.0;
                ty += d.wrapped(mx + 28.0, ty, mw - 56.0, 21.0, DIM, 1.0, &f.up) + 20.0;
            }
            ty = ty.max(my + 520.0);
            self.section(d, mx + 16.0, ty, mw - 32.0, self.t("身上的魇火（死亡后消失）", "Embers (lost on death)"));
            ty += 44.0;
            if embers.is_empty() {
                d.text(mx + 28.0, ty, 20.0, DIM, 1.0, self.t("（在「死亡」「不可能」里击败魇化精英获得）", "(defeat nightmare elites on Death / Impossible)"));
            }
            for (k, r, ic) in &embers {
                let Some(ef) = all.iter().find(|x| x.idx == *k) else { continue };
                d.icon(*ic, mx + 26.0, ty - 6.0, 40.0, 1.0);
                d.text_mid(mx + 76.0, ty + 14.0, 21.0, RAR[(*r).min(3)], 1.0, &format!("{}（{}）", ef.name, RAR_NAME[l][(*r).min(3)]));
                ty += 46.0;
            }
        }
        // 右：刻印位
        let (rx, ry0, rw) = (1430.0, 150.0, 420.0);
        d.text(rx, ry0 + 6.0, 26.0, GOLD, 1.0, self.t("刻印位", "Seal Slots"));
        d.sprite("MENU_Line_01", rx, ry0 + 46.0, rw, 3.0, 0.8);
        d.wrapped(rx, ry0 + 58.0, rw, 19.0, DIM, 1.0, self.t(
            "刻上的魇印一直生效，不占装备，任何难度都有效；随时可以换。解锁的种类越多，开的刻印位越多。",
            "Engraved seals always apply, take no equipment slot and work on every difficulty; swap any time. Unlocking more affixes opens more slots.",
        ));
        let mut sy = ry0 + 150.0;
        for i in 0..NM_SLOTS {
            let bh = 100.0;
            // 框两边的括号占 ~20 像素：内容从 rx + 36 起，图标上下都留在框里
            let focus = self.ncol == 1 && self.nslot == i;
            if focus {
                d.sprite("MENU_FL_Cursor_Ent", rx, sy, rw, bh, 1.0);
            }
            d.sprite("MENU_FL_Cursor_EntWaku", rx, sy, rw, bh, if focus { 1.0 } else { 0.6 });
            let label = if l == 0 { format!("第 {} 位", i + 1) } else { format!("Slot {}", i + 1) };
            d.text(rx + 36.0, sy + 10.0, 18.0, DIM, 1.0, &label);
            if i >= open {
                let n = need.get(i).copied().unwrap_or(0);
                let tip = if l == 0 { format!("解锁 {n} 种后开启") } else { format!("Opens at {n} unlocked") };
                d.text(rx + 36.0, sy + 52.0, 22.0, DIM, 1.0, &tip);
            } else {
                match slots[i].and_then(|k| all.iter().find(|x| x.idx == k)) {
                    Some(f) => {
                        d.icon(f.icon, rx + 36.0, sy + 40.0, 48.0, 1.0);
                        d.text_clip(rx + 96.0, sy + 52.0, rw - 132.0, 24.0, TEXT, 1.0, &format!("{}  {}", f.name, ROMAN[f.level.min(4)]));
                    }
                    None => d.text(rx + 36.0, sy + 52.0, 22.0, DIM, 1.0, self.t("（空）", "(empty)")),
                }
            }
            self.hit(rx, sy, rw, bh, Hit::NSlot(i));
            sy += bh + 10.0;
        }
        d.wrapped(rx, sy + 10.0, rw, 18.0, DIM, 1.0, self.t(
            "左边选一种，A 到这里选刻印位，再按 A 刻上；X 取下这一位。",
            "Pick an affix on the left, press A to choose a slot, then A to engrave; X removes the seal in that slot.",
        ));
    }
}
