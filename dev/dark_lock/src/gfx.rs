//! 物品格子界面文件（Scaleform GFX = 未压缩 SWF）的运行时改写：往格子元件里加一个名叫 RngLock 的锁图标。
//!
//! 格子元件 = 第一帧里有名叫 ItemIcon、inadequacy、StockNum 子元素的 DefineSprite（背包 02_020_inventory、仓库 03_050_itembox）。
//! 锁图标是一张 40x42 的位图（lock_bitmap.bin，和原版「装备中」标记 MENU_EquMark 同尺寸、同画风，dev\dark_lock\draw_lock.py 画的），
//! 插在格子元件定义前面：DefineBitsLossless2 + 用它裁剪填充的矩形 DefineShape3 + 按 0.56 倍（和 MENU_EquMark 一样）摆好的 DefineSprite；
//! 格子第一帧加 PlaceObject2（深度 = 原来最大深度 + 1，名字 RngLock）。显示 / 隐藏由 DLL 在格子刷新时设置。
//! 已经有 RngLock、或认不出格子元件，就原样不动（返回 None）。

const CELL_NAMES: [&str; 3] = ["ItemIcon", "inadequacy", "StockNum"];
pub const LOCK_NAME: &str = "RngLock";
/// DefineBitsLossless2 正文（不含编号）：格式 5 + 宽 + 高 + zlib(预乘 alpha 的 ARGB)
const LOCK_BITMAP: &[u8] = include_bytes!("lock_bitmap.bin");
/// 和 MENU_EquMark 一样按 0.56 倍显示（约 22x24 像素）
const LOCK_IMG_SCALE: f64 = 0.56;
/// 锁图左上角在格子里的位置（twips，1/20 像素）：「装备中」标记占 (-874, -934)~(-426, -464)，锁放在它正下方
const LOCK_X: i32 = -874;
const LOCK_Y: i32 = -450;

struct Tag {
    code: u16,
    /// 整个 tag（含头）的起止
    start: usize,
    body: usize,
    end: usize,
}

fn read_tags(b: &[u8], mut o: usize, end: usize) -> Result<Vec<Tag>, String> {
    let mut v = Vec::new();
    while o + 2 <= end {
        let h = u16::from_le_bytes([b[o], b[o + 1]]);
        let code = h >> 6;
        let mut len = (h & 0x3F) as usize;
        let mut body = o + 2;
        if len == 0x3F {
            if o + 6 > end {
                return Err("tag 头越界".into());
            }
            len = u32::from_le_bytes(b[o + 2..o + 6].try_into().unwrap()) as usize;
            body = o + 6;
        }
        let e = body + len;
        if e > end {
            return Err(format!("tag {code} 越界"));
        }
        v.push(Tag { code, start: o, body, end: e });
        o = e;
        if code == 0 {
            break;
        }
    }
    Ok(v)
}

fn tag_header(code: u16, len: usize) -> Vec<u8> {
    let mut v = Vec::new();
    if len < 0x3F && !matches!(code, 6 | 21 | 35 | 20 | 36 | 90) {
        v.extend_from_slice(&((code << 6) | len as u16).to_le_bytes());
    } else {
        v.extend_from_slice(&((code << 6) | 0x3F).to_le_bytes());
        v.extend_from_slice(&(len as u32).to_le_bytes());
    }
    v
}

fn tag(code: u16, body: &[u8]) -> Vec<u8> {
    let mut v = tag_header(code, body.len());
    v.extend_from_slice(body);
    v
}

// ---- 位读写
struct BitReader<'a> {
    b: &'a [u8],
    o: usize,
    bit: u32,
}

impl BitReader<'_> {
    fn ub(&mut self, n: u32) -> Result<u32, String> {
        let mut v = 0u32;
        for _ in 0..n {
            let byte = *self.b.get(self.o).ok_or("位读取越界")?;
            v = (v << 1) | ((byte >> (7 - self.bit)) & 1) as u32;
            self.bit += 1;
            if self.bit == 8 {
                self.bit = 0;
                self.o += 1;
            }
        }
        Ok(v)
    }
    fn align(&mut self) -> usize {
        if self.bit != 0 {
            self.bit = 0;
            self.o += 1;
        }
        self.o
    }
}

#[derive(Default)]
struct BitWriter {
    v: Vec<u8>,
    bit: u32,
}

impl BitWriter {
    fn ub(&mut self, n: u32, val: u32) {
        for i in (0..n).rev() {
            if self.bit == 0 {
                self.v.push(0);
            }
            if (val >> i) & 1 != 0 {
                *self.v.last_mut().unwrap() |= 1 << (7 - self.bit);
            }
            self.bit = (self.bit + 1) % 8;
        }
    }
    fn sb(&mut self, n: u32, val: i32) {
        self.ub(n, (val as u32) & if n >= 32 { u32::MAX } else { (1u32 << n) - 1 });
    }
    fn finish(self) -> Vec<u8> {
        self.v
    }
}

/// 有符号数需要的位数（含符号位）
fn sbits(vals: &[i32]) -> u32 {
    let mut n = 1;
    for &v in vals {
        let need = if v >= 0 { 33 - (v as u32).leading_zeros() } else { 33 - (!(v as u32)).leading_zeros() };
        n = n.max(need);
    }
    n
}

fn write_rect(w: &mut BitWriter, x0: i32, x1: i32, y0: i32, y1: i32) {
    let n = sbits(&[x0, x1, y0, y1]);
    w.ub(5, n);
    for v in [x0, x1, y0, y1] {
        w.sb(n, v);
    }
}

fn matrix_bytes(scale: f64, tx: i32, ty: i32) -> Vec<u8> {
    let mut w = BitWriter::default();
    if (scale - 1.0).abs() > 1e-6 {
        let s = (scale * 65536.0).round() as i32;
        let n = sbits(&[s]);
        w.ub(1, 1);
        w.ub(5, n);
        w.sb(n, s);
        w.sb(n, s);
    } else {
        w.ub(1, 0);
    }
    w.ub(1, 0);
    let n = sbits(&[tx, ty]);
    w.ub(5, n);
    w.sb(n, tx);
    w.sb(n, ty);
    w.finish()
}

/// 跳过 MATRIX
fn skip_matrix(b: &[u8], o: usize) -> Result<usize, String> {
    let mut r = BitReader { b, o, bit: 0 };
    if r.ub(1)? == 1 {
        let n = r.ub(5)?;
        r.ub(n * 2)?;
    }
    if r.ub(1)? == 1 {
        let n = r.ub(5)?;
        r.ub(n * 2)?;
    }
    let n = r.ub(5)?;
    r.ub(n * 2)?;
    Ok(r.align())
}

fn skip_cxform_alpha(b: &[u8], o: usize) -> Result<usize, String> {
    let mut r = BitReader { b, o, bit: 0 };
    let add = r.ub(1)?;
    let mul = r.ub(1)?;
    let n = r.ub(4)?;
    r.ub(n * 4 * (add + mul))?;
    Ok(r.align())
}

/// PlaceObject2 / PlaceObject3 → （深度, 名字）
fn place_info(code: u16, b: &[u8]) -> Result<(u16, Option<String>), String> {
    let f = *b.first().ok_or("空 PlaceObject")?;
    let mut p = 1;
    let mut f2 = 0;
    if code == 70 {
        f2 = *b.get(1).ok_or("PlaceObject3 太短")?;
        p = 2;
    }
    let depth = u16::from_le_bytes(b.get(p..p + 2).ok_or("PlaceObject 太短")?.try_into().unwrap());
    p += 2;
    if code == 70 && f2 & 0x08 != 0 {
        p += b[p..].iter().position(|&c| c == 0).ok_or("类名没结尾")? + 1;
    }
    if f & 0x02 != 0 {
        p += 2;
    }
    if f & 0x04 != 0 {
        p = skip_matrix(b, p)?;
    }
    if f & 0x08 != 0 {
        p = skip_cxform_alpha(b, p)?;
    }
    if f & 0x10 != 0 {
        p += 2;
    }
    let name = if f & 0x20 != 0 {
        let e = b[p..].iter().position(|&c| c == 0).ok_or("名字没结尾")?;
        Some(String::from_utf8_lossy(&b[p..p + e]).into_owned())
    } else {
        None
    };
    Ok((depth, name))
}

/// 位图填充的矩形：(0, 0)~(宽, 高) 像素，1 像素 = 20 twips
fn bitmap_shape_tag(id: u16, bitmap: u16, w: i32, h: i32) -> Vec<u8> {
    let (w, h) = (w * 20, h * 20);
    let mut body = id.to_le_bytes().to_vec();
    let mut bw = BitWriter::default();
    write_rect(&mut bw, 0, w, 0, h);
    body.extend(bw.finish());
    body.push(1); // 1 个填充样式：裁剪、平滑的位图填充
    body.push(0x41);
    body.extend(bitmap.to_le_bytes());
    body.extend(matrix_bytes(20.0, 0, 0));
    body.push(0); // 没有线条样式
    let mut bw = BitWriter::default();
    bw.ub(4, 1); // NumFillBits
    bw.ub(4, 0); // NumLineBits
    bw.ub(6, 0b000101); // StyleChange：FillStyle1 + MoveTo
    bw.ub(5, 1);
    bw.sb(1, 0);
    bw.sb(1, 0);
    bw.ub(1, 1); // FillStyle1 = 1
    let mut cur = (0, 0);
    for (x, y) in [(w, 0), (w, h), (0, h), (0, 0)] {
        let (dx, dy) = (x - cur.0, y - cur.1);
        let n = sbits(&[dx, dy]).max(2);
        bw.ub(2, 0b11); // 边 + 直线
        bw.ub(4, n - 2);
        bw.ub(1, 1); // GeneralLine
        bw.sb(n, dx);
        bw.sb(n, dy);
        cur = (x, y);
    }
    bw.ub(6, 0); // EndShape
    body.extend(bw.finish());
    tag(32, &body)
}

fn defined_ids(b: &[u8], tags: &[Tag]) -> Vec<u16> {
    let mut ids = Vec::new();
    for t in tags {
        let defines = matches!(
            t.code,
            2 | 22 | 32 | 83 | 46 | 84 | 39 | 37 | 11 | 33 | 10 | 48 | 75 | 6 | 21 | 35 | 90 | 20 | 36 | 7 | 34 | 14 | 60 | 1001 | 1005 | 1008 | 1009
        );
        if defines && t.end >= t.body + 2 {
            ids.push(u16::from_le_bytes([b[t.body], b[t.body + 1]]));
        }
    }
    ids
}

/// 改写一个界面文件：认出格子元件就返回改好的字节
pub fn patch(src: &[u8]) -> Result<Option<Vec<u8>>, String> {
    if src.len() < 21 || !(src.starts_with(b"GFX") || src.starts_with(b"FWS")) {
        return Ok(None); // 压缩的或不是 SWF：不动
    }
    let nbits = (src[8] >> 3) as usize;
    let hdr = 8 + (5 + nbits * 4).div_ceil(8) + 4;
    let tags = read_tags(src, hdr, src.len())?;
    // 找格子元件
    let mut cells = Vec::new();
    for (i, t) in tags.iter().enumerate() {
        if t.code != 39 {
            continue;
        }
        let kids = read_tags(src, t.body + 4, t.end)?;
        let mut names = Vec::new();
        let mut max_depth = 0u16;
        let mut first_frame = None;
        for k in &kids {
            if matches!(k.code, 26 | 70) {
                let (d, n) = place_info(k.code, &src[k.body..k.end])?;
                max_depth = max_depth.max(d);
                if first_frame.is_none() {
                    if let Some(n) = n {
                        names.push(n);
                    }
                }
            } else if k.code == 1 && first_frame.is_none() {
                first_frame = Some(k.start);
            }
        }
        if names.iter().any(|n| n == LOCK_NAME) {
            return Ok(None); // 已经改过
        }
        if CELL_NAMES.iter().all(|c| names.iter().any(|n| n == c)) {
            if let Some(ff) = first_frame {
                cells.push((i, max_depth, ff));
            }
        }
    }
    if cells.is_empty() {
        return Ok(None);
    }
    let ids = defined_ids(src, &tags);
    let next = ids.iter().copied().max().unwrap_or(0) as u32 + 1;
    if next + 3 > 0xFFFF || LOCK_BITMAP.len() < 5 {
        return Err("编号用完了 / 位图数据不对".into());
    }
    let (bmp, shape, lock_id) = (next as u16, next as u16 + 1, next as u16 + 2);
    let bw = u16::from_le_bytes([LOCK_BITMAP[1], LOCK_BITMAP[2]]) as i32;
    let bh = u16::from_le_bytes([LOCK_BITMAP[3], LOCK_BITMAP[4]]) as i32;
    let mut defs = Vec::new();
    let mut b36 = bmp.to_le_bytes().to_vec();
    b36.extend_from_slice(LOCK_BITMAP);
    defs.extend(tag(36, &b36));
    defs.extend(bitmap_shape_tag(shape, bmp, bw, bh));
    let mut po = vec![0x06u8]; // HasMatrix | HasCharacter
    po.extend(1u16.to_le_bytes());
    po.extend(shape.to_le_bytes());
    po.extend(matrix_bytes(LOCK_IMG_SCALE, 0, 0));
    let mut sp = lock_id.to_le_bytes().to_vec();
    sp.extend(1u16.to_le_bytes());
    sp.extend(tag(26, &po));
    sp.extend(tag(1, &[]));
    sp.extend(tag(0, &[]));
    defs.extend(tag(39, &sp));

    // 重新拼：在第一个格子元件前插定义；每个格子元件第一帧前插 PlaceObject2
    let mut out = src[..hdr].to_vec();
    let mut last = hdr;
    for (n, &(i, max_depth, ff)) in cells.iter().enumerate() {
        let t = &tags[i];
        out.extend_from_slice(&src[last..t.start]);
        if n == 0 {
            out.extend_from_slice(&defs);
        }
        let mut po = vec![0x26u8]; // HasName | HasMatrix | HasCharacter
        po.extend((max_depth + 1).to_le_bytes());
        po.extend(lock_id.to_le_bytes());
        po.extend(matrix_bytes(1.0, LOCK_X, LOCK_Y));
        po.extend(LOCK_NAME.as_bytes());
        po.push(0);
        let mut body = src[t.body..ff].to_vec();
        body.extend(tag(26, &po));
        body.extend_from_slice(&src[ff..t.end]);
        let mut hdr39 = Vec::new();
        hdr39.extend(((39u16 << 6) | 0x3F).to_le_bytes());
        hdr39.extend((body.len() as u32).to_le_bytes());
        out.extend(hdr39);
        out.extend(body);
        last = t.end;
    }
    out.extend_from_slice(&src[last..]);
    let len = out.len() as u32;
    out[4..8].copy_from_slice(&len.to_le_bytes());
    Ok(Some(out))
}

/// 武器补正那一格：武器详情（02_055_detailstatus_weapon1）一格、对比（03_030_comparison_equip_weapon1）两格 DefineEditText，
/// 变量名空、初始文字「A」、宽 27 像素、右对齐。dark_core 把字母换成数字后三位数放不下（100 显示成「10」，用户 2026-10-29），
/// 照 ERR（加宽到 37~39.5 像素）加宽到 SCALE_W；往左加，右边不动（数字右对齐，左边属性名那格右半是空的，不挤右边下一列）
const SCALE_TEXT: &[u8] = b"\0A\0";
const SCALE_W: i32 = 800;

/// 加宽补正格；没有要加宽的（不是这几个文件、已经够宽）就返回 None
pub fn widen_scaling(src: &[u8]) -> Result<Option<Vec<u8>>, String> {
    if src.len() < 21 || !(src.starts_with(b"GFX") || src.starts_with(b"FWS")) {
        return Ok(None);
    }
    let nbits = (src[8] >> 3) as usize;
    let hdr = 8 + (5 + nbits * 4).div_ceil(8) + 4;
    let tags = read_tags(src, hdr, src.len())?;
    let mut out = src[..hdr].to_vec();
    let mut last = hdr;
    let mut n = 0;
    for t in &tags {
        let body = &src[t.body..t.end];
        if t.code != 37 || body.len() < 4 || !body.ends_with(SCALE_TEXT) {
            continue;
        }
        let mut r = BitReader { b: body, o: 2, bit: 0 };
        let nb = r.ub(5)?;
        let mut v = [0i32; 4];
        for x in v.iter_mut() {
            let u = r.ub(nb)?;
            *x = if nb > 0 && u >> (nb - 1) != 0 { (u as i64 - (1i64 << nb)) as i32 } else { u as i32 };
        }
        let rest = r.align();
        let [x0, x1, y0, y1] = v;
        if x1 - x0 >= SCALE_W {
            continue;
        }
        let mut w = BitWriter::default();
        write_rect(&mut w, x1 - SCALE_W, x1, y0, y1);
        let mut nbody = body[..2].to_vec();
        nbody.extend(w.finish());
        nbody.extend_from_slice(&body[rest..]);
        out.extend_from_slice(&src[last..t.start]);
        out.extend(tag(37, &nbody));
        last = t.end;
        n += 1;
    }
    if n == 0 {
        return Ok(None);
    }
    out.extend_from_slice(&src[last..]);
    let len = out.len() as u32;
    out[4..8].copy_from_slice(&len.to_le_bytes());
    Ok(Some(out))
}

#[cfg(test)]
mod tests {
    /// 样本：游戏目录（仓库在 Game\dark_reforged）里别的 mod 留下的界面文件；没有就跳过这一个
    fn sample(rel: &str) -> Option<Vec<u8>> {
        let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(r"..\..\..").join(rel);
        let b = std::fs::read(&p).ok();
        if b.is_none() {
            println!("没有样本 {}，跳过", p.display());
        }
        b
    }

    /// 补正格：武器详情一格、对比两格加宽到 40 像素（右边不动），别的不变；再改一次不动
    #[test]
    fn widen_samples() {
        for (src, want) in [
            (r"mod\menu\02_055_detailstatus_weapon1.gfx", 1),
            (r"mod\menu\03_030_comparison_equip_weapon1.gfx", 2),
        ] {
            let Some(b) = sample(src) else { continue };
            let p = super::widen_scaling(&b).unwrap().expect("没找到补正格");
            assert!(super::widen_scaling(&p).unwrap().is_none(), "二次改写应该不动");
            let hdr = 8 + (5 + (b[8] >> 3) as usize * 4).div_ceil(8) + 4;
            let (ta, tb) = (super::read_tags(&b, hdr, b.len()).unwrap(), super::read_tags(&p, hdr, p.len()).unwrap());
            assert_eq!(ta.len(), tb.len());
            assert_eq!(u32::from_le_bytes(p[4..8].try_into().unwrap()) as usize, p.len());
            let mut changed = 0;
            for (x, y) in ta.iter().zip(&tb) {
                assert_eq!(x.code, y.code);
                let (bx, by) = (&b[x.body..x.end], &p[y.body..y.end]);
                if bx != by {
                    changed += 1;
                    assert_eq!(x.code, 37);
                    assert!(by.ends_with(super::SCALE_TEXT));
                    let mut r = super::BitReader { b: by, o: 2, bit: 0 };
                    let nb = r.ub(5).unwrap();
                    let s = |u: u32| if u >> (nb - 1) != 0 { u as i64 - (1i64 << nb) } else { u as i64 };
                    let (x0, x1) = (s(r.ub(nb).unwrap()), s(r.ub(nb).unwrap()));
                    assert_eq!((x0, x1), (500 - super::SCALE_W as i64, 500), "右边 25 像素不动");
                }
            }
            assert_eq!(changed, want);
        }
    }

    #[test]
    fn patch_samples() {
        for (src, dst) in [
            (r"mod\menu\02_020_inventory.gfx", "inv"),
            (r"mod\menu\03_050_itembox.gfx", "box"),
            (r"ERRv2.3.5.3\mod\menu\02_020_inventory.gfx", "err_inv"),
        ] {
            let Some(b) = sample(src) else { continue };
            let p = super::patch(&b).unwrap().expect("没认出格子元件");
            assert!(super::patch(&p).unwrap().is_none(), "二次改写应该不动");
            let out = std::env::var("RNG_LOCK_TEST_OUT").unwrap_or_else(|_| ".".into());
            std::fs::write(format!("{out}/{dst}.gfx"), &p).unwrap();
            println!("{dst}: {} -> {}", b.len(), p.len());
        }
    }
}
