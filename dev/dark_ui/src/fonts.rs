//! 字体：优先用游戏自带的（用户 2026-10-31）——启动器合成菜单包时从本机 Data0 转出来的 out\menu\dark_ui_font_zh.ttf（方正书宋）、
//! dark_ui_font_en.ttf（Agmena），转换在 launcher\reroll\gfxfont.py。中文界面用方正书宋，游戏字库里没有的字用系统字体补；
//! 英文界面用 Agmena，没有的符号用中文那份补。没转出来就用系统的思源宋体（Win11 自带）、宋体、微软雅黑。
//! 只建常用汉字 + 实际会出现的字（词条库 affixes.txt、界面和 dark_core 源码里的文字），字体图集小一些；按 ui::FONT_PX 建，用的时候缩放
use std::path::Path;

use hudhook::imgui::{self, FontConfig, FontGlyphRanges, FontId, FontSource};

use crate::ui::FONT_PX;

const SYSTEM: [&str; 5] = [
    "C:\\Windows\\Fonts\\NotoSerifSC-VF.ttf",
    "C:\\Windows\\Fonts\\simsun.ttc",
    "C:\\Windows\\Fonts\\msyh.ttc",
    "C:\\Windows\\Fonts\\msyh.ttf",
    "C:\\Windows\\Fonts\\simhei.ttf",
];

/// 源码里的文字（界面的、dark_core 发来的原因和名字）
const SOURCES: [&str; 13] = [
    include_str!("ui.rs"),
    include_str!("ui/codex.rs"),
    include_str!("ui/filter.rs"),
    include_str!("ui/reforge.rs"),
    include_str!("ui/overlimit.rs"),
    include_str!("ui/seal.rs"),
    include_str!("ui/curse.rs"),
    include_str!("lib.rs"),
    include_str!("../../dark_core/src/gear.rs"),
    include_str!("../../dark_core/src/gear/workshop.rs"),
    include_str!("../../dark_core/src/gear/overlimit.rs"),
    include_str!("../../dark_core/src/nightmare.rs"),
    include_str!("../../dark_core/src/curses.rs"),
];

/// 西文：基本拉丁、拉丁补充 / 扩展、一般标点、字母式符号（◆◇ 这类几何符号 Agmena 里是方框，从中文那份取）
static LATIN: [u32; 7] = [0x0020, 0x024F, 0x2000, 0x206F, 0x2100, 0x214F, 0];

fn load(p: &Path) -> Option<&'static [u8]> {
    let b = std::fs::read(p).ok().filter(|b| b.len() > 1000)?;
    Some(Box::leak(b.into_boxed_slice()))
}

/// 加字体：extra 是另外要有的字（词条库全文），menu 是 out\menu。返回（说明, [中文界面的字体, 英文界面的字体]）
pub fn add(ctx: &mut imgui::Context, extra: &str, menu: &Path) -> (String, [Option<FontId>; 2]) {
    let mut cps: Vec<u32> = SOURCES.iter().flat_map(|s| s.chars()).chain(extra.chars()).map(|c| c as u32).filter(|&c| c >= 0x80).collect();
    cps.extend([0x2026, 0x25C6, 0x25C7, 0x2605, 0xFF0B, 0xFF05]);
    cps.sort_unstable();
    cps.dedup();
    let mut ranges: Vec<u32> = Vec::new();
    for c in cps {
        match ranges.len() {
            n if n >= 2 && ranges[n - 1] + 1 == c => ranges[n - 1] = c,
            _ => ranges.extend([c, c]),
        }
    }
    ranges.push(0);
    let extra_ranges: &'static [u32] = Box::leak(ranges.into_boxed_slice());
    let cfg = |r: FontGlyphRanges| Some(FontConfig { glyph_ranges: r, oversample_h: 2, oversample_v: 1, ..FontConfig::default() });
    let src = |data: &'static [u8], r: FontGlyphRanges| FontSource::TtfData { data, size_pixels: FONT_PX, config: cfg(r) };

    let game_zh = load(&menu.join("dark_ui_font_zh.ttf"));
    let game_en = load(&menu.join("dark_ui_font_en.ttf"));
    let sys = SYSTEM.iter().find_map(|p| load(Path::new(p)).map(|d| (*p, d)));
    let mut note = Vec::new();
    // 中文界面：游戏字体在前（同一个字前面的优先），系统字体补缺
    let mut zh_src = Vec::new();
    if let Some(d) = game_zh {
        zh_src.push(src(d, FontGlyphRanges::chinese_simplified_common()));
        zh_src.push(src(d, FontGlyphRanges::from_slice(extra_ranges)));
        note.push("游戏字体（方正书宋）".to_string());
    }
    if let Some((p, d)) = sys {
        zh_src.push(src(d, FontGlyphRanges::chinese_simplified_common()));
        zh_src.push(src(d, FontGlyphRanges::from_slice(extra_ranges)));
        note.push(format!("补缺 {p}"));
    }
    let zh = (!zh_src.is_empty()).then(|| ctx.fonts().add_font(&zh_src));
    // 英文界面：Agmena + 中文那份补符号
    let en = game_en.map(|d| {
        let mut v = vec![src(d, FontGlyphRanges::from_slice(&LATIN))];
        if let Some(z) = game_zh.or(sys.map(|s| s.1)) {
            v.push(src(z, FontGlyphRanges::from_slice(extra_ranges)));
        }
        note.push("英文 Agmena".to_string());
        ctx.fonts().add_font(&v)
    });
    (note.join("、"), [zh, en.or(zh)])
}
