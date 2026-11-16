//! 「咒痕」页（原名七咒；赐福「暗黑重铸」→「咒痕」单独打开，不在装备工坊里；用户 2026-11-03；规则在 dark_core 的 curses.rs，只看不改）：
//!   左：七道咒痕（图标、名字、区域），最后一行是对勇于挑战者的馈赠（用户 2026-11-05：不写碎片，直接以祝福显示；need = 0）
//!   右：选中那条现在生效的效果（诅咒或祝福）、另一面、一排碎片图标（拿到的血红 / 反转后金色，没拿到的暗）、右下一张大图标、最下面一段来历（dev\narrative\叙事方案.md）
//! 用户 2026-11-03：碎片不用进度条和「n / 5」字样（有图标就不写数），左边不放碎片，整页少放字。
//! 操作：上下选，B 关窗口。
use super::*;

/// 诅咒的暗红、祝福的金（文字）
const CURSED: [u8; 3] = [214, 92, 74];
const BLESSED: [u8; 3] = [240, 200, 80];
/// 碎片图标的大小、间距
const SHARD: f32 = 72.0;
const SHARD_GAP: f32 = 10.0;
/// 来历那段离右栏顶的距离（右栏高 830，放两行字）
const LORE_Y: f32 = 700.0;
/// 左边每行的图标、右边的大图标（离右栏顶和右边的距离；在碎片那一行右边、来历上面）
const ROW_ICON: f32 = 76.0;
const BIG_ICON: f32 = 230.0;
const BIG_Y: f32 = 400.0;
const BIG_RIGHT: f32 = 40.0;

impl Workshop {
    /// 左边的咒痕（按关键词筛过）
    fn curses(&self) -> Vec<CurseRow> {
        let terms = self.terms(4);
        let Some(s) = &self.snap else { return Vec::new() };
        s.curses.iter().filter(|c| filter::has_all(&terms, &format!("{}\x01{} {} {} {}", c.name, c.region, c.curse, c.bless, c.lore).to_lowercase())).cloned().collect()
    }

    pub(super) fn handle_curse(&mut self, a: Act) {
        let n = self.curses().len();
        if a.up && self.csel > 0 {
            self.csel -= 1;
        }
        if a.down && self.csel + 1 < n {
            self.csel += 1;
        }
        if a.b {
            self.reqs.push(Req::Close);
        }
    }

    pub(super) fn click_curse(&mut self, h: Hit) {
        if let Hit::CRow(i) = h {
            self.csel = i;
        }
    }

    /// 一排碎片（从 x 往右）：拿到的（反转后金色），没拿到的暗；菜单包里没有碎片图标就写「n / 5」
    fn draw_shards(&self, d: &mut Draw, x: f32, y: f32, c: &CurseRow) {
        let ic = self.snap.as_ref().map_or([0; 3], |s| s.shard_icons);
        let got = if c.rev { ic[1] } else { ic[0] };
        if got == 0 || ic[2] == 0 {
            d.text(x, y, 24.0, if c.rev { BLESSED } else { TEXT }, 1.0, &format!("{} / {}", c.shards, c.need));
            return;
        }
        for k in 0..c.need.max(1) {
            let on = c.rev || k < c.shards;
            d.icon(if on { got } else { ic[2] }, x + k as f32 * (SHARD + SHARD_GAP), y, SHARD, 1.0);
        }
    }

    pub(super) fn draw_curses(&mut self, d: &mut Draw) {
        let rows = self.curses();
        self.csel = self.csel.min(rows.len().saturating_sub(1));
        // 左：七条
        let (x, y, w) = (70.0, 150.0, 520.0);
        d.sprite("MENU_BaseMain_02", x - 20.0, y - 10.0, w + 60.0, 820.0, 0.55);
        if rows.is_empty() && !self.terms(4).is_empty() {
            d.wrapped(x + 20.0, y + 30.0, w - 40.0, 22.0, DIM, 1.0, self.t("没有符合搜索的咒痕", "No cursemarks match"));
        } else if rows.is_empty() {
            d.wrapped(x + 20.0, y + 30.0, w - 40.0, 22.0, DIM, 1.0, self.t("这次没开咒痕（重随设置 curses）", "Cursemarks are disabled"));
        }
        let rh = 96.0;
        for (i, c) in rows.iter().enumerate() {
            let ry = y + 8.0 + i as f32 * rh;
            if i == self.csel {
                d.sprite("MENU_FL_Cursor_Wide", x - 8.0, ry + 2.0, w + 16.0, rh - 4.0, 1.0);
            }
            d.icon(c.icon, x + 10.0, ry + (rh - ROW_ICON) / 2.0, ROW_ICON, 1.0);
            let tx = if c.icon != 0 { x + 16.0 + ROW_ICON } else { x + 20.0 };
            d.text(tx, ry + if c.region.is_empty() { 32.0 } else { 14.0 }, 28.0, if c.rev { BLESSED } else { CURSED }, 1.0, &c.name);
            d.text_clip(tx, ry + 56.0, x + w - 20.0 - tx, 19.0, DIM, 1.0, &c.region);
            if i + 1 < rows.len() {
                d.sprite("MENU_Line_01", x + 12.0, ry + rh - 1.0, w - 24.0, 2.0, 0.35);
            }
            self.hit(x, ry, w, rh, Hit::CRow(i));
        }
        // 右：现在生效的一面、另一面、碎片
        let (mx, my, mw) = (630.0, 150.0, 1220.0);
        d.sprite("MENU_FL_MenuBase", mx - 16.0, my - 8.0, mw + 32.0, 830.0, 0.9);
        let Some(c) = rows.get(self.csel) else { return };
        let col = if c.rev { BLESSED } else { CURSED };
        d.sprite(if c.rev { "MENU_FL_Rar_d2" } else { "MENU_FL_Rar_d0" }, mx - 10.0, my, mw + 20.0, 76.0, 0.9);
        d.text_clip(mx + 20.0, my + 10.0, mw - 40.0, 28.0, col, 1.0, &c.name);
        d.text_clip(mx + 20.0, my + 46.0, mw - 40.0, 19.0, DIM, 1.0, &c.region);
        d.icon(c.icon, mx + mw - BIG_RIGHT - BIG_ICON, my + BIG_Y, BIG_ICON, 1.0);
        if !c.lore.is_empty() {
            d.sprite("MENU_Line_01", mx + 12.0, my + LORE_Y, mw - 24.0, 2.0, 0.35);
            d.wrapped(mx + 28.0, my + LORE_Y + 20.0, mw - 56.0, 21.0, DIM, 1.0, &c.lore);
        }
        let mut ty = my + 104.0;
        let (now_h, now_t, other_h, other_t) = if c.rev {
            (self.t("祝福", "Blessing"), &c.bless, self.t("反转前", "Before reversal"), &c.curse)
        } else {
            (self.t("诅咒", "Curse"), &c.curse, self.t("反转后", "Once reversed"), &c.bless)
        };
        self.section(d, mx + 16.0, ty, mw - 32.0, now_h);
        ty += 50.0;
        ty += d.wrapped(mx + 28.0, ty, mw - 56.0, 24.0, TEXT, 1.0, now_t) + 34.0;
        if c.need == 0 {
            return; // 馈赠：直接是祝福，没有反转前和碎片
        }
        self.section(d, mx + 16.0, ty, mw - 32.0, other_h);
        ty += 50.0;
        ty += d.wrapped(mx + 28.0, ty, mw - 56.0, 21.0, DIM, 1.0, other_t) + 34.0;
        self.section(d, mx + 16.0, ty, mw - 32.0, self.t("碎片", "Shards"));
        self.draw_shards(d, mx + 28.0, ty + 54.0, c);
    }
}
