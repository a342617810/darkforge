//! 离线预览（不开游戏）：用 ui.rs 的界面、模拟快照（launcher 外的 mock_snap.py 生成，格式同 dark_core 的快照）、真的原版素材和图标，
//! 按给的按键一帧帧走，最后一帧的 ImGui 绘制结果在 CPU 上画成 PNG。
//! 用法：cargo run --release --features preview --bin preview -- <dark_ui_sprites.bin> <dr_frames 目录> <affixes.txt> <快照> <输出.png> [按键…]
//! 按键：a b x y lb rb up down left right（一个一帧），比如 a down a 就是选来源 → 下一条词条 → 进目标栏
//! 关键词：q:文字；词条筛选窗口：filter（窗口里还是 a / x / b / up / down）
//! 鼠标：m:x,y（移到屏幕坐标）、click / rclick（按一下）、wheelup / wheeldown、wait（一帧不做事，指针停留要 6 帧才算选中）
use std::collections::HashMap;
use std::path::Path;

use dark_ui::assets::{Assets, Rgba};
use dark_ui::data::{Prev, Snap};
use dark_ui::fonts;
use dark_ui::ui::{Act, Img, Tex, Workshop};
use hudhook::imgui::{self, DrawCmd, DrawCmdParams, TextureId};

const W: usize = 1920;
const H: usize = 1080;

struct PTex<'a> {
    assets: &'a Assets,
    imgs: HashMap<usize, Rgba>,
    sprites: HashMap<String, Option<Img>>,
    icons: HashMap<u16, Option<Img>>,
}

impl PTex<'_> {
    fn add(&mut self, r: Option<Rgba>) -> Option<Img> {
        let r = r?;
        let id = self.imgs.len() + 2;
        let img = Img { id: TextureId::new(id), w: r.w as f32, h: r.h as f32 };
        self.imgs.insert(id, r);
        Some(img)
    }
}

impl Tex for PTex<'_> {
    fn sprite(&mut self, name: &str) -> Option<Img> {
        if !self.sprites.contains_key(name) {
            let r = self.assets.sprite(name);
            let img = self.add(r);
            self.sprites.insert(name.to_string(), img);
        }
        self.sprites[name]
    }

    fn icon(&mut self, id: u16) -> Option<Img> {
        if !self.icons.contains_key(&id) {
            let r = self.assets.icon(id);
            let img = self.add(r);
            self.icons.insert(id, img);
        }
        self.icons[&id]
    }
}

fn act(k: &str) -> Act {
    let mut a = Act::default();
    match k {
        "a" => a.a = true,
        "b" => a.b = true,
        "x" => a.x = true,
        "y" => a.y = true,
        "lb" => a.lb = true,
        "rb" => a.rb = true,
        "up" => a.up = true,
        "down" => a.down = true,
        "left" => a.left = true,
        "right" => a.right = true,
        "lt" => a.lt = true,
        "rt" => a.rt = true,
        "filter" => a.filter = true,
        "search" => a.search = true,
        _ => {}
    }
    a
}

/// 双线性取样（超出夹边）
fn sample(t: &Rgba, u: f32, v: f32) -> [f32; 4] {
    let x = (u * t.w as f32 - 0.5).clamp(0.0, t.w as f32 - 1.0);
    let y = (v * t.h as f32 - 0.5).clamp(0.0, t.h as f32 - 1.0);
    let (x0, y0) = (x.floor() as usize, y.floor() as usize);
    let (x1, y1) = ((x0 + 1).min(t.w as usize - 1), (y0 + 1).min(t.h as usize - 1));
    let (fx, fy) = (x - x0 as f32, y - y0 as f32);
    let px = |xx: usize, yy: usize| {
        let i = (yy * t.w as usize + xx) * 4;
        [t.data[i] as f32, t.data[i + 1] as f32, t.data[i + 2] as f32, t.data[i + 3] as f32]
    };
    let (a, b, c, d) = (px(x0, y0), px(x1, y0), px(x0, y1), px(x1, y1));
    let mut o = [0.0; 4];
    for k in 0..4 {
        o[k] = (a[k] * (1.0 - fx) + b[k] * fx) * (1.0 - fy) + (c[k] * (1.0 - fx) + d[k] * fx) * fy;
        o[k] /= 255.0;
    }
    o
}

/// ImGui 的绘制结果画到 RGB 缓冲（底色是一张暗的「游戏画面」）
fn raster(dd: &imgui::DrawData, texs: &HashMap<usize, Rgba>) -> Vec<f32> {
    let mut buf = vec![0f32; W * H * 3];
    for y in 0..H {
        for x in 0..W {
            let i = (y * W + x) * 3;
            let g = 0.18 + 0.1 * (x as f32 / W as f32);
            buf[i] = g * 0.9;
            buf[i + 1] = g;
            buf[i + 2] = g * 0.8;
        }
    }
    for list in dd.draw_lists() {
        let vtx = list.vtx_buffer();
        let idx = list.idx_buffer();
        for cmd in list.commands() {
            let DrawCmd::Elements { count, cmd_params: DrawCmdParams { clip_rect, texture_id, vtx_offset, idx_offset } } = cmd else { continue };
            let tex = texs.get(&texture_id.id());
            for t in (0..count).step_by(3) {
                let v = [0, 1, 2].map(|j| vtx[idx[idx_offset + t + j] as usize + vtx_offset]);
                let (p0, p1, p2) = (v[0].pos, v[1].pos, v[2].pos);
                let area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0]);
                if area.abs() < 1e-6 {
                    continue;
                }
                let xs = [p0[0], p1[0], p2[0]];
                let ys = [p0[1], p1[1], p2[1]];
                let x0 = xs.iter().cloned().fold(f32::MAX, f32::min).max(clip_rect[0]).max(0.0).floor() as i32;
                let x1 = xs.iter().cloned().fold(f32::MIN, f32::max).min(clip_rect[2]).min(W as f32).ceil() as i32;
                let y0 = ys.iter().cloned().fold(f32::MAX, f32::min).max(clip_rect[1]).max(0.0).floor() as i32;
                let y1 = ys.iter().cloned().fold(f32::MIN, f32::max).min(clip_rect[3]).min(H as f32).ceil() as i32;
                for py in y0..y1 {
                    for px in x0..x1 {
                        // 采样点稍微错开一点、严格在里面才算：两个三角形共用的边不会画两遍
                        let (fx, fy) = (px as f32 + 0.5013, py as f32 + 0.5027);
                        if fx < clip_rect[0] || fx >= clip_rect[2] || fy < clip_rect[1] || fy >= clip_rect[3] {
                            continue;
                        }
                        let w0 = ((p1[0] - fx) * (p2[1] - fy) - (p1[1] - fy) * (p2[0] - fx)) / area;
                        let w1 = ((p2[0] - fx) * (p0[1] - fy) - (p2[1] - fy) * (p0[0] - fx)) / area;
                        let w2 = 1.0 - w0 - w1;
                        if w0 <= 0.0 || w1 <= 0.0 || w2 <= 0.0 {
                            continue;
                        }
                        let u = w0 * v[0].uv[0] + w1 * v[1].uv[0] + w2 * v[2].uv[0];
                        let vv = w0 * v[0].uv[1] + w1 * v[1].uv[1] + w2 * v[2].uv[1];
                        let mut col = [0f32; 4];
                        for k in 0..4 {
                            col[k] = (w0 * v[0].col[k] as f32 + w1 * v[1].col[k] as f32 + w2 * v[2].col[k] as f32) / 255.0;
                        }
                        let s = tex.map_or([1.0; 4], |t| sample(t, u, vv));
                        let a = col[3] * s[3];
                        if a <= 0.0 {
                            continue;
                        }
                        let i = (py as usize * W + px as usize) * 3;
                        for k in 0..3 {
                            buf[i + k] = col[k] * s[k] * a + buf[i + k] * (1.0 - a);
                        }
                    }
                }
            }
        }
    }
    buf
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 6 {
        eprintln!("用法：preview <dark_ui_sprites.bin> <dr_frames 目录> <affixes.txt> <快照> <输出.png> [按键…]");
        std::process::exit(2);
    }
    let assets = Assets::load(Path::new(&args[1]), Path::new(&args[2]));
    eprintln!("{}", assets.note);
    let lib = std::fs::read_to_string(&args[3]).unwrap_or_default();
    let snap = Snap::parse(&std::fs::read_to_string(&args[4]).expect("快照读不了"));
    let mut ctx = imgui::Context::create();
    ctx.set_ini_filename(None);
    let menu = Path::new(&args[1]).parent().unwrap_or(Path::new("."));
    let (font, ids) = fonts::add(&mut ctx, &lib, menu);
    eprintln!("字体：{font}");
    let mut texs: HashMap<usize, Rgba> = HashMap::new();
    {
        let fonts = ctx.fonts();
        let t = fonts.build_rgba32_texture();
        eprintln!("字体图集 {}×{}", t.width, t.height);
        texs.insert(1, Rgba { w: t.width, h: t.height, data: t.data.to_vec() });
        fonts.tex_id = TextureId::new(1);
    }
    ctx.io_mut().display_size = [W as f32, H as f32];
    ctx.io_mut().delta_time = 1.0 / 60.0;
    let mut ws = Workshop::default();
    // 入口（环境变量 DR_MODE：0 装备工坊、1 魇印、2 咒痕）
    ws.set_mode(std::env::var("DR_MODE").ok().and_then(|m| m.parse().ok()).unwrap_or(0));
    ws.codex = dark_ui::ui::Codex::parse(&lib, &std::fs::read_to_string(Path::new(&args[2]).join("dr_frames.txt")).unwrap_or_default());
    ws.set_snap(snap);
    ws.fonts = ids.map(|f| f.map(dark_ui::ui::UiFont));
    let mut tex = PTex { assets: &assets, imgs: HashMap::new(), sprites: HashMap::new(), icons: HashMap::new() };
    let keys: Vec<&str> = std::iter::once("wait").chain(args[6..].iter().map(|k| k.as_str())).chain(["wait", "wait"]).collect();
    let n = keys.len();
    let mut release = None;
    for (f, k) in keys.into_iter().enumerate() {
        use imgui::MouseButton as B;
        let io = ctx.io_mut();
        if let Some(b) = release.take() {
            io.add_mouse_button_event(b, false);
        }
        match k {
            "click" | "rclick" => {
                let b = if k == "click" { B::Left } else { B::Right };
                io.add_mouse_button_event(b, true);
                release = Some(b);
            }
            "wheelup" => io.add_mouse_wheel_event([0.0, 1.0]),
            "wheeldown" => io.add_mouse_wheel_event([0.0, -1.0]),
            _ => {
                if let Some(q) = k.strip_prefix("q:") {
                    ws.set_query(q);
                }
                if let Some((x, y)) = k.strip_prefix("m:").and_then(|p| p.split_once(',')) {
                    io.add_mouse_pos_event([x.parse().unwrap_or(0.0), y.parse().unwrap_or(0.0)]);
                }
            }
        }
        let a = act(k);
        let ui = ctx.new_frame();
        ws.frame(ui, &mut tex, a, [W as f32, H as f32]);
        if !ws.reqs.is_empty() {
            eprintln!("请求：{:?}", ws.reqs);
            // 重铸范围：模拟的（环境变量 DR_PV 指的文件，格式同 dark_core 的 dr_ws_get(2)），编号换成要的那把
            for r in &ws.reqs {
                if let dark_ui::ui::Req::Preview(k) = r {
                    if let Ok(t) = std::fs::read_to_string(std::env::var("DR_PV").unwrap_or_default()) {
                        ws.preview = Prev::parse(&t).map(|p| Prev { idx: *k, ..p });
                    }
                }
            }
            ws.reqs.clear();
        }
        let dd = ctx.render();
        if f + 1 == n {
            let mut all = std::mem::take(&mut tex.imgs);
            all.extend(texs.drain());
            let buf = raster(dd, &all);
            let px: Vec<u8> = buf.iter().map(|v| (v.clamp(0.0, 1.0) * 255.0) as u8).collect();
            let file = std::fs::File::create(&args[5]).expect("写不了 PNG");
            let mut enc = png::Encoder::new(std::io::BufWriter::new(file), W as u32, H as u32);
            enc.set_color(png::ColorType::Rgb);
            enc.set_depth(png::BitDepth::Eight);
            enc.write_header().unwrap().write_image_data(&px).unwrap();
            eprintln!("写好 {}", args[5]);
        }
    }
}
