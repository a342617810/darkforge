//! BC7 压缩（开发用，给 dev\item_system\make_frames.py 调）：逐字照搬 make_icons.py 的 encode_block（mode 6：单分区 RGBA，
//! 端点 7 位 + p 位，4 位索引；主轴定端点，按索引最小二乘修两轮），浮点运算顺序也一样，结果和 Python 逐字节相同；多线程。
//! 用法：bc7enc <输入> <输出>。输入是 N 个 4×4 块的 RGBA（每块 64 字节，块里按行），输出 N 个 BC7 块（每块 16 字节）。

use std::{env, fs, process, thread};

const W16: [i64; 16] = [0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64];

type Px = [i64; 4];

fn palette(e0: &[i64; 4], e1: &[i64; 4]) -> [[i64; 4]; 16] {
    let mut out = [[0; 4]; 16];
    for (k, w) in W16.iter().enumerate() {
        for c in 0..4 {
            out[k][c] = ((64 - w) * e0[c] + w * e1[c] + 32) >> 6;
        }
    }
    out
}

fn err(p: &Px, q: &[i64; 4]) -> f64 {
    let a = p[3] as f64 / 255.0;
    let rgb = (p[0] - q[0]).pow(2) + (p[1] - q[1]).pow(2) + (p[2] - q[2]).pow(2);
    rgb as f64 * (0.25 + a) + 2.0 * ((p[3] - q[3]).pow(2) as f64)
}

/// 端点量化到 7 位 + 共用的 p 位：两个 p 都试，挑误差小的。返回 (7 位的四个值, p, 实际 8 位值)
fn quant(c: &[f64; 4]) -> ([i64; 4], i64, [i64; 4]) {
    let mut best: Option<(f64, [i64; 4], i64, [i64; 4])> = None;
    for p in 0..2i64 {
        let mut q = [0i64; 4];
        let mut v = [0i64; 4];
        let mut e = 0.0f64;
        for k in 0..4 {
            q[k] = (((c[k] - p as f64) / 2.0).round_ties_even() as i64).clamp(0, 127);
            v[k] = q[k] * 2 + p;
        }
        for k in 0..4 {
            e += (v[k] as f64 - c[k]).powi(2);
        }
        if best.as_ref().is_none_or(|b| e < b.0) {
            best = Some((e, q, p, v));
        }
    }
    let b = best.unwrap();
    (b.1, b.2, b.3)
}

fn clamp255(x: f64) -> f64 {
    // Python：min(255, max(0, x))
    let y = if 0.0 > x { 0.0 } else { x };
    if 255.0 < y { 255.0 } else { y }
}

/// 给定索引，最小二乘求两端点（各通道分开）
fn fit(px: &[Px; 16], idx: &[usize; 16]) -> Option<([f64; 4], [f64; 4])> {
    let t: Vec<f64> = idx.iter().map(|&i| W16[i] as f64 / 64.0).collect();
    let (mut a11, mut a12, mut a22) = (0.0f64, 0.0f64, 0.0f64);
    for &x in &t {
        a11 += (1.0 - x).powi(2);
    }
    for &x in &t {
        a12 += (1.0 - x) * x;
    }
    for &x in &t {
        a22 += x * x;
    }
    let det = a11 * a22 - a12 * a12;
    if det.abs() < 1e-6 {
        return None;
    }
    let (mut e0, mut e1) = ([0.0; 4], [0.0; 4]);
    for ch in 0..4 {
        let (mut b1, mut b2) = (0.0f64, 0.0f64);
        for (x, p) in t.iter().zip(px) {
            b1 += (1.0 - x) * p[ch] as f64;
        }
        for (x, p) in t.iter().zip(px) {
            b2 += x * p[ch] as f64;
        }
        e0[ch] = clamp255((a22 * b1 - a12 * b2) / det);
        e1[ch] = clamp255((a11 * b2 - a12 * b1) / det);
    }
    Some((e0, e1))
}

struct Try {
    tot: f64,
    q0: [i64; 4],
    p0: i64,
    q1: [i64; 4],
    p1: i64,
    idx: [usize; 16],
}

fn try_ends(px: &[Px; 16], c0: &[f64; 4], c1: &[f64; 4]) -> Try {
    let (q0, p0, v0) = quant(c0);
    let (q1, p1, v1) = quant(c1);
    let pal = palette(&v0, &v1);
    let mut idx = [0usize; 16];
    let mut tot = 0.0f64;
    for (k, p) in px.iter().enumerate() {
        let (mut be, mut bi) = (f64::INFINITY, 0usize);
        for (i, q) in pal.iter().enumerate() {
            let e = err(p, q);
            if e < be {
                (be, bi) = (e, i);
            }
        }
        idx[k] = bi;
        tot += be;
    }
    Try { tot, q0, p0, q1, p1, idx }
}

fn encode_block(px: &[Px; 16]) -> [u8; 16] {
    if px.iter().all(|p| p[3] == 0) {
        let mut b = [0u8; 16];
        b[0] = 0x40;
        return b;
    }
    let n = 16.0f64;
    let mut mean = [0.0f64; 4];
    for c in 0..4 {
        mean[c] = px.iter().map(|p| p[c]).sum::<i64>() as f64 / n;
    }
    let d: Vec<[f64; 4]> = px.iter().map(|p| [p[0] as f64 - mean[0], p[1] as f64 - mean[1], p[2] as f64 - mean[2], p[3] as f64 - mean[3]]).collect();
    let mut cov = [[0.0f64; 4]; 4];
    for i in 0..4 {
        for j in 0..4 {
            let mut s = 0.0f64;
            for x in &d {
                s += x[i] * x[j];
            }
            cov[i][j] = s;
        }
    }
    let mut axis = [1.0f64; 4];
    for _ in 0..8 {
        let mut v = [0.0f64; 4];
        for i in 0..4 {
            let mut s = 0.0f64;
            for j in 0..4 {
                s += cov[i][j] * axis[j];
            }
            v[i] = s;
        }
        let m = v.iter().fold(f64::NEG_INFINITY, |a, &x| if x.abs() > a { x.abs() } else { a });
        if m < 1e-9 {
            break;
        }
        for i in 0..4 {
            axis[i] = v[i] / m;
        }
    }
    let t: Vec<f64> = d
        .iter()
        .map(|x| {
            let mut s = 0.0f64;
            for c in 0..4 {
                s += x[c] * axis[c];
            }
            s
        })
        .collect();
    let lo = t.iter().fold(f64::INFINITY, |a, &x| if x < a { x } else { a });
    let hi = t.iter().fold(f64::NEG_INFINITY, |a, &x| if x > a { x } else { a });
    let mut nn = 0.0f64;
    for a in &axis {
        nn += a * a;
    }
    if nn == 0.0 {
        nn = 1.0;
    }
    let mut c0 = [0.0f64; 4];
    let mut c1 = [0.0f64; 4];
    for c in 0..4 {
        c0[c] = clamp255(mean[c] + axis[c] * lo / nn);
        c1[c] = clamp255(mean[c] + axis[c] * hi / nn);
    }
    let mut best = try_ends(px, &c0, &c1);
    for _ in 0..2 {
        let Some((e0, e1)) = fit(px, &best.idx) else { break };
        let cand = try_ends(px, &e0, &e1);
        if cand.tot >= best.tot {
            break;
        }
        best = cand;
    }
    let Try { mut q0, mut p0, mut q1, mut p1, mut idx, .. } = best;
    if idx[0] >= 8 {
        // 第一个像素的索引最高位必须是 0：两端点对调
        std::mem::swap(&mut q0, &mut q1);
        std::mem::swap(&mut p0, &mut p1);
        for i in idx.iter_mut() {
            *i = 15 - *i;
        }
    }
    let mut bits: u128 = 1 << 6;
    let mut pos = 7u32;
    for c in 0..4 {
        for q in [q0[c], q1[c]] {
            bits |= (q as u128) << pos;
            pos += 7;
        }
    }
    bits |= (p0 as u128) << pos | (p1 as u128) << (pos + 1);
    pos += 2;
    for (k, &i) in idx.iter().enumerate() {
        bits |= (i as u128) << pos;
        pos += if k == 0 { 3 } else { 4 };
    }
    debug_assert_eq!(pos, 128);
    bits.to_le_bytes()
}

fn block_px(raw: &[u8]) -> [Px; 16] {
    let mut px = [[0i64; 4]; 16];
    for (k, p) in px.iter_mut().enumerate() {
        for c in 0..4 {
            p[c] = raw[k * 4 + c] as i64;
        }
    }
    px
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        eprintln!("用法：bc7enc <输入 RGBA 块> <输出 BC7 块>");
        process::exit(2);
    }
    let input = fs::read(&args[1]).unwrap_or_else(|e| {
        eprintln!("读不了 {}：{e}", args[1]);
        process::exit(1);
    });
    if input.len() % 64 != 0 {
        eprintln!("输入大小 {} 不是 64 的倍数", input.len());
        process::exit(1);
    }
    let n = input.len() / 64;
    let mut out = vec![0u8; n * 16];
    let threads = thread::available_parallelism().map_or(4, |x| x.get()).max(1);
    let per = n.div_ceil(threads).max(1);
    thread::scope(|s| {
        for (src, dst) in input.chunks(per * 64).zip(out.chunks_mut(per * 16)) {
            s.spawn(move || {
                for (b, o) in src.chunks(64).zip(dst.chunks_mut(16)) {
                    o.copy_from_slice(&encode_block(&block_px(b)));
                }
            });
        }
    });
    fs::write(&args[2], &out).unwrap_or_else(|e| {
        eprintln!("写不了 {}：{e}", args[2]);
        process::exit(1);
    });
}
