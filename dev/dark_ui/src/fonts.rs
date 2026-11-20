//! 字体：优先用游戏自带的（用户 2026-10-31）——启动器合成菜单包时从本机 Data0 转出来的 out\menu\dark_ui_font_zh.ttf（方正书宋）、
//! dark_ui_font_en.ttf（Agmena），转换在 launcher\reroll\gfxfont.py。中文界面用方正书宋，游戏字库里没有的字用系统字体补；
//! 英文界面用 Agmena，没有的符号用中文那份补。没转出来就用系统的思源宋体（Win11 自带）、宋体、微软雅黑。
//! 只建常用汉字 + 实际会出现的字（词条库 affixes.txt、界面和 dark_core 源码里的文字），字体图集小一些；按 ui::FONT_PX 建，用的时候缩放。
//! 字体文件交给 ImGui 前先查格式（check_font），坏文件跳过、退回下一个；文件和字形范围只读、算一次（hudhook 重建画面管线时 initialize 会再跑）
use std::path::Path;
use std::sync::OnceLock;

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

/// 读好、查过的字体文件和算好的字形范围（第一次 add 时读、算，之后每次重建都用这一份）。
/// ImGui 装字体时自己拷一份字体数据，字形范围只存指针（建图集时才读），所以放在静态变量里一直留着
struct Files {
    ranges: Vec<u32>,
    game_zh: Option<Vec<u8>>,
    game_en: Option<Vec<u8>>,
    sys: Option<(&'static str, Vec<u8>)>,
    /// 格式不对、跳过的文件（路径：原因）
    bad: Vec<String>,
}

static FILES: OnceLock<Files> = OnceLock::new();

impl Files {
    fn load(extra: &str, menu: &Path) -> Self {
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
        let mut bad = Vec::new();
        let mut read = |p: &Path| -> Option<Vec<u8>> {
            let b = std::fs::read(p).ok()?;
            match check_font(&b) {
                Ok(()) => Some(b),
                Err(e) => {
                    bad.push(format!("{}：{e}", p.display()));
                    None
                }
            }
        };
        let game_zh = read(&menu.join("dark_ui_font_zh.ttf"));
        let game_en = read(&menu.join("dark_ui_font_en.ttf"));
        let sys = SYSTEM.iter().find_map(|p| read(Path::new(p)).map(|d| (*p, d)));
        Files { ranges, game_zh, game_en, sys, bad }
    }
}

/// 加字体：extra 是另外要有的字（词条库全文），menu 是 out\menu。返回（说明, [中文界面的字体, 英文界面的字体]）
pub fn add(ctx: &mut imgui::Context, extra: &str, menu: &Path) -> (String, [Option<FontId>; 2]) {
    add_at(ctx, extra, menu, 0)
}

/// 同 add；step 是字体图集连着建不出来时退几步：1 = 不装常用汉字表，只装实际会出现的字；2 = 不装自己的字体（ImGui 自带的西文字体）。
/// extra、menu 只在第一次调用时用（文件和字形范围之后不再读、算）
pub fn add_at(ctx: &mut imgui::Context, extra: &str, menu: &Path, step: u32) -> (String, [Option<FontId>; 2]) {
    let f: &'static Files = FILES.get_or_init(|| Files::load(extra, menu));
    let mut note: Vec<String> = f.bad.iter().map(|b| format!("跳过格式不对的字体 {b}")).collect();
    if step >= 2 {
        note.push("字体图集建不出来，只用 ImGui 自带的西文字体".to_string());
        return (note.join("、"), [None, None]);
    }
    let common = step == 0;
    let extra_ranges: &'static [u32] = &f.ranges;
    let cfg = |r: FontGlyphRanges| Some(FontConfig { glyph_ranges: r, oversample_h: 2, oversample_v: 1, ..FontConfig::default() });
    let src = |data: &'static [u8], r: FontGlyphRanges| FontSource::TtfData { data, size_pixels: FONT_PX, config: cfg(r) };

    let game_zh = f.game_zh.as_deref();
    let game_en = f.game_en.as_deref();
    let sys = f.sys.as_ref().map(|(p, d)| (*p, d.as_slice()));
    // 中文界面：游戏字体在前（同一个字前面的优先），系统字体补缺
    let mut zh_src = Vec::new();
    if let Some(d) = game_zh {
        if common {
            zh_src.push(src(d, FontGlyphRanges::chinese_simplified_common()));
        }
        zh_src.push(src(d, FontGlyphRanges::from_slice(extra_ranges)));
        note.push("游戏字体（方正书宋）".to_string());
    }
    if let Some((p, d)) = sys {
        if common {
            zh_src.push(src(d, FontGlyphRanges::chinese_simplified_common()));
        }
        zh_src.push(src(d, FontGlyphRanges::from_slice(extra_ranges)));
        note.push(format!("补缺 {p}"));
    }
    if !common {
        note.push("字体图集建不出来，常用汉字表不装了".to_string());
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

/// 字体文件交给 ImGui（stb_truetype）前先查一遍：sfnt 头、表目录、每张表都在文件里；stb_truetype 要的表都有、长度够
/// （cmap / head / hhea / hmtx，glyf + loca + maxp 或 CFF）；loca 指的字形都在 glyf 里；cmap 里有它会用的 Unicode 子表。
/// ttc 查第一个字体（ImGui 默认用第 0 个，表的偏移从文件开头算）。坏文件交给 ImGui 会断言失败或越界读，之后每次启动都一样。
/// 字形内部的轮廓数据不查
pub fn check_font(b: &[u8]) -> Result<(), String> {
    let u16_at = |o: usize| b.get(o..o.checked_add(2)?).map(|x| u16::from_be_bytes([x[0], x[1]]));
    let u32_at = |o: usize| b.get(o..o.checked_add(4)?).map(|x| u32::from_be_bytes([x[0], x[1], x[2], x[3]]));
    let short = || "文件不完整".to_string();
    let start = if b.starts_with(b"ttcf") {
        let ver = u32_at(4).ok_or_else(short)?;
        if ver != 0x0001_0000 && ver != 0x0002_0000 {
            return Err(format!("ttc 版本 {ver:#x} 不认识"));
        }
        if u32_at(8).ok_or_else(short)? == 0 {
            return Err("ttc 里没有字体".into());
        }
        u32_at(12).ok_or_else(short)? as usize
    } else {
        0
    };
    match b.get(start..start.saturating_add(4)) {
        Some([0, 1, 0, 0] | [b'1', 0, 0, 0] | b"true" | b"OTTO") => {}
        Some(_) => return Err("不是 TrueType / OpenType 字体".into()),
        None => return Err(short()),
    }
    let n = u16_at(start + 4).ok_or_else(short)? as usize;
    if n == 0 {
        return Err("表目录是空的".into());
    }
    let dir = start + 12;
    if b.len() < dir + 16 * n {
        return Err("表目录超出文件".into());
    }
    let mut tables: Vec<([u8; 4], usize, usize)> = Vec::with_capacity(n);
    for i in 0..n {
        let rec = dir + 16 * i;
        let tag = [b[rec], b[rec + 1], b[rec + 2], b[rec + 3]];
        let (off, len) = (u32_at(rec + 8).ok_or_else(short)? as usize, u32_at(rec + 12).ok_or_else(short)? as usize);
        if off.checked_add(len).is_none_or(|end| end > b.len()) {
            return Err(format!("表 {} 超出文件（文件不完整？）", String::from_utf8_lossy(&tag)));
        }
        tables.push((tag, off, len));
    }
    let find = |t: &[u8; 4]| tables.iter().find(|x| &x.0 == t).map(|x| (x.1, x.2));
    let need = |t: &[u8; 4], min: usize| -> Result<(usize, usize), String> {
        let name = String::from_utf8_lossy(t);
        match find(t) {
            Some((o, l)) if l >= min => Ok((o, l)),
            Some(_) => Err(format!("表 {name} 太短")),
            None => Err(format!("缺表 {name}")),
        }
    };
    let (head, _) = need(b"head", 54)?;
    let (hhea, _) = need(b"hhea", 36)?;
    let (_, hmtx_len) = need(b"hmtx", 0)?;
    let long_metrics = u16_at(hhea + 34).ok_or_else(short)? as usize;
    if long_metrics == 0 || hmtx_len < 4 * long_metrics {
        return Err("hmtx 和 hhea 对不上".into());
    }
    // 字形：TrueType 轮廓查 loca 每一项都落在 glyf 里；CFF 只查表在
    if let Some((_, glyf_len)) = find(b"glyf") {
        let (maxp, _) = need(b"maxp", 6)?;
        let glyphs = u16_at(maxp + 4).ok_or_else(short)? as usize;
        let long = match u16_at(head + 50).ok_or_else(short)? {
            0 => false,
            1 => true,
            x => return Err(format!("head 的 loca 格式 {x} 不认识")),
        };
        let (loca, loca_len) = need(b"loca", 0)?;
        let size = if long { 4 } else { 2 };
        if loca_len < (glyphs + 1) * size {
            return Err("loca 比字形数短".into());
        }
        for i in 0..=glyphs {
            let at = if long { u32_at(loca + 4 * i).map(|x| x as usize) } else { u16_at(loca + 2 * i).map(|x| x as usize * 2) };
            if at.ok_or_else(short)? > glyf_len {
                return Err("loca 指到 glyf 外面".into());
            }
        }
    } else {
        need(b"CFF ", 1)?;
    }
    // cmap：stb_truetype 用最后一个 Unicode 子表（平台 0，或平台 3 编码 1 / 10）
    let (cmap, cmap_len) = need(b"cmap", 4)?;
    let subs = u16_at(cmap + 2).ok_or_else(short)? as usize;
    if cmap_len < 4 + 8 * subs {
        return Err("cmap 目录超出表".into());
    }
    let mut pick = None;
    for i in 0..subs {
        let rec = cmap + 4 + 8 * i;
        let (plat, enc) = (u16_at(rec).ok_or_else(short)?, u16_at(rec + 2).ok_or_else(short)?);
        if plat == 0 || (plat == 3 && (enc == 1 || enc == 10)) {
            pick = Some(u32_at(rec + 4).ok_or_else(short)? as usize);
        }
    }
    let sub = pick.ok_or("cmap 里没有 Unicode 子表")?;
    let sub_len = match (sub.checked_add(4).is_some_and(|x| x <= cmap_len)).then(|| u16_at(cmap + sub)).flatten() {
        Some(0 | 2 | 4 | 6) => u16_at(cmap + sub + 2).map(|x| x as usize),
        Some(12 | 13) => u32_at(cmap + sub + 4).map(|x| x as usize),
        Some(_) => Some(0),
        None => return Err("cmap 子表在表外面".into()),
    };
    if sub_len.is_none_or(|l| sub.checked_add(l).is_none_or(|end| end > cmap_len)) {
        return Err("cmap 子表超出表".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::check_font;

    fn be16(v: &mut Vec<u8>, x: u16) {
        v.extend(x.to_be_bytes());
    }

    fn be32(v: &mut Vec<u8>, x: u32) {
        v.extend(x.to_be_bytes());
    }

    /// 最小的 TrueType：1 个字形（空轮廓），cmap 格式 4 只有结尾段
    fn tables() -> Vec<([u8; 4], Vec<u8>)> {
        let mut cmap = Vec::new();
        be16(&mut cmap, 0); // 版本
        be16(&mut cmap, 1); // 子表数
        be16(&mut cmap, 3);
        be16(&mut cmap, 1);
        be32(&mut cmap, 12);
        let f4 = [4u16, 24, 0, 2, 2, 0, 0, 0xFFFF, 0, 0xFFFF, 1, 0];
        f4.iter().for_each(|&x| be16(&mut cmap, x));
        let mut head = vec![0u8; 54];
        head[12..16].copy_from_slice(&0x5F0F3CF5u32.to_be_bytes());
        head[18..20].copy_from_slice(&1000u16.to_be_bytes());
        let mut hhea = vec![0u8; 36];
        hhea[34..36].copy_from_slice(&1u16.to_be_bytes());
        let mut maxp = Vec::new();
        be32(&mut maxp, 0x0000_5000);
        be16(&mut maxp, 1);
        let hmtx = vec![0u8; 4];
        let loca = vec![0u8; 4];
        vec![(*b"cmap", cmap), (*b"glyf", Vec::new()), (*b"head", head), (*b"hhea", hhea), (*b"hmtx", hmtx), (*b"loca", loca), (*b"maxp", maxp)]
    }

    /// 拼成字体文件；base 是这份字体在整个文件里的起点（ttc 里表的偏移从文件开头算）
    fn build(t: &[([u8; 4], Vec<u8>)], base: usize) -> Vec<u8> {
        let mut v = Vec::new();
        be32(&mut v, 0x0001_0000);
        be16(&mut v, t.len() as u16);
        v.extend([0u8; 6]);
        let mut off = base + 12 + 16 * t.len();
        for (tag, d) in t {
            v.extend(tag);
            be32(&mut v, 0);
            be32(&mut v, off as u32);
            be32(&mut v, d.len() as u32);
            off += d.len().div_ceil(4) * 4;
        }
        for (_, d) in t {
            v.extend(d);
            v.resize(v.len().div_ceil(4) * 4, 0);
        }
        v
    }

    /// 只装一个字体的 ttc：版本、字体数、第一个字体的偏移
    fn ttc(ver: u32, count: u32, first: u32) -> Vec<u8> {
        let mut v = b"ttcf".to_vec();
        be32(&mut v, ver);
        be32(&mut v, count);
        be32(&mut v, first);
        v.extend(build(&tables(), 16));
        v
    }

    #[test]
    fn good_font_passes() {
        assert_eq!(check_font(&build(&tables(), 0)), Ok(()));
    }

    #[test]
    fn bad_files_fail() {
        let good = build(&tables(), 0);
        assert!(check_font(&[]).is_err());
        assert!(check_font(&good[..good.len() / 2]).is_err(), "截断");
        let mut v = good.clone();
        v[0..4].copy_from_slice(b"wOFF");
        assert!(check_font(&v).is_err(), "不是 sfnt");
        let mut v = good.clone();
        v[4..6].copy_from_slice(&200u16.to_be_bytes());
        assert!(check_font(&v).is_err(), "表目录太长");
        assert!(check_font(&vec![0u8; 4096]).is_err(), "全是 0");
    }

    #[test]
    fn missing_or_broken_tables_fail() {
        let mut t = tables();
        t.retain(|x| &x.0 != b"cmap");
        assert!(check_font(&build(&t, 0)).unwrap_err().contains("cmap"));
        let mut t = tables();
        t.retain(|x| &x.0 != b"loca");
        assert!(check_font(&build(&t, 0)).unwrap_err().contains("loca"));
        let mut t = tables();
        t[5].1 = vec![0, 0, 0, 9]; // loca 第二项指到 glyf（长 0）外面
        assert!(check_font(&build(&t, 0)).is_err());
        let mut t = tables();
        t[0].1[4..6].copy_from_slice(&1u16.to_be_bytes()); // cmap 唯一的子表改成 Mac 平台（平台 1、编码 0）
        t[0].1[6..8].copy_from_slice(&0u16.to_be_bytes());
        assert!(check_font(&build(&t, 0)).unwrap_err().contains("Unicode"));
        let mut t = tables();
        t[0].1[14..16].copy_from_slice(&500u16.to_be_bytes()); // 格式 4 的长度超出 cmap
        assert!(check_font(&build(&t, 0)).is_err());
    }

    #[test]
    fn ttc_uses_first_font() {
        assert_eq!(check_font(&ttc(0x0001_0000, 1, 16)), Ok(()));
        assert_eq!(check_font(&ttc(0x0002_0000, 1, 16)), Ok(()));
        assert!(check_font(&ttc(0x0001_0000, 1, 1 << 20)).is_err(), "第一个字体的偏移在文件外");
        assert!(check_font(&ttc(0x0001_0000, 0, 16)).is_err(), "没有字体");
        assert!(check_font(&ttc(0x0003_0000, 1, 16)).is_err(), "版本不认识");
        assert!(check_font(&ttc(0x0001_0000, 1, 4)).is_err(), "偏移指到 ttc 头里");
    }

    /// 本机有的真字体都要能过（没有就跳过）
    #[test]
    fn real_fonts_pass() {
        let menu = concat!(env!("CARGO_MANIFEST_DIR"), "/../../out/menu/");
        let game = [format!("{menu}dark_ui_font_zh.ttf"), format!("{menu}dark_ui_font_en.ttf")];
        for p in super::SYSTEM.iter().map(|s| s.to_string()).chain(game) {
            if let Ok(b) = std::fs::read(&p) {
                assert_eq!(check_font(&b), Ok(()), "{p}");
            }
        }
    }
}
