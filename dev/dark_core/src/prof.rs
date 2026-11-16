//! 帧耗时统计（用户 2026-11-05「高难下有点卡顿」「我们在帧里面塞了多少逻辑」）：每个模块的 tick 一帧花多久、游戏一帧多长。
//! 平时只多读一个原子变量。dll\dark_dev 的「帧耗时统计」按钮直接调导出的 dr_prof_set / dr_prof_get（不走请求文件，免得测量本身添乱）；
//! 停止时把开始以来的结果写进 dark_core.log。「其中」那几行是某个模块里的一部分，不算进合计。

use std::cmp::Reverse;
use std::fmt::Write;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use crate::log;

/// 界面上「最近」这一段的长度
const WINDOW: Duration = Duration::from_secs(2);
/// 超过这么久的帧算读图（不算进帧长）
const LOAD_FRAME: Duration = Duration::from_secs(1);
const SLOW_FRAME: Duration = Duration::from_millis(20);
const HITCH_FRAME: Duration = Duration::from_millis(33);

static ON: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Default)]
struct Stat {
    name: &'static str,
    /// 只是某个模块里的一部分，不算进合计
    part: bool,
    total: Duration,
    max: Duration,
    calls: u32,
}

/// 一段时间的累计
#[derive(Clone, Default)]
struct Acc {
    stats: Vec<Stat>,
    frames: u32,
    frame_total: Duration,
    frame_max: Duration,
    slow: u32,
    hitch: u32,
    around_calls: u32,
    around_items: u64,
}

impl Acc {
    fn add(&mut self, name: &'static str, part: bool, dt: Duration) {
        let i = match self.stats.iter().position(|s| s.part == part && s.name == name) {
            Some(i) => i,
            None => {
                self.stats.push(Stat { name, part, ..Stat::default() });
                self.stats.len() - 1
            }
        };
        let s = &mut self.stats[i];
        s.total += dt;
        s.max = s.max.max(dt);
        s.calls += 1;
    }

    fn frame(&mut self, dt: Duration) {
        self.frames += 1;
        self.frame_total += dt;
        self.frame_max = self.frame_max.max(dt);
        self.slow += (dt >= SLOW_FRAME) as u32;
        self.hitch += (dt >= HITCH_FRAME) as u32;
    }

    /// 给人看的结果：游戏一帧多长、dark_core 合计、各模块（平均 / 最长，按平均从大到小）
    fn render(&self) -> String {
        let mut out = String::new();
        let frames = self.frames.max(1);
        let avg = self.frame_total.as_secs_f64() * 1000.0 / frames as f64;
        let fps = if avg > 0.0 { 1000.0 / avg } else { 0.0 };
        let _ = writeln!(
            out,
            "游戏一帧：平均 {avg:.1} 毫秒（{fps:.0} 帧/秒），最长 {:.1} 毫秒；超过 20 毫秒 {} 帧，超过 33 毫秒 {} 帧（共 {} 帧）",
            self.frame_max.as_secs_f64() * 1000.0,
            self.slow,
            self.hitch,
            self.frames
        );
        let sum: Duration = self.stats.iter().filter(|s| !s.part).map(|s| s.total).sum();
        let mine = sum.as_secs_f64() * 1000.0 / frames as f64;
        let share = if avg > 0.0 { mine / avg * 100.0 } else { 0.0 };
        let _ = writeln!(out, "dark_core 合计：平均每帧 {mine:.2} 毫秒（占一帧的 {share:.1}%）");
        let mut rows: Vec<&Stat> = self.stats.iter().collect();
        rows.sort_by_key(|s| Reverse(s.total));
        let _ = writeln!(out, "各模块（平均每帧 / 单次最长，微秒）：");
        for s in rows.iter().filter(|s| !s.part) {
            let _ = writeln!(out, "  {}：{} / {}", s.name, s.total.as_micros() as u64 / frames as u64, s.max.as_micros());
        }
        for s in rows.iter().filter(|s| s.part) {
            let _ = writeln!(out, "  其中 {}：{} / {}", s.name, s.total.as_micros() as u64 / frames as u64, s.max.as_micros());
        }
        if self.around_calls > 0 {
            let _ = writeln!(
                out,
                "距离列表：每帧取 {:.1} 次，平均 {} 项",
                self.around_calls as f64 / frames as f64,
                self.around_items / self.around_calls as u64
            );
        }
        out
    }
}

struct Prof {
    last_frame: Option<Instant>,
    window_from: Option<Instant>,
    window: Acc,
    all: Acc,
    text: String,
}

static PROF: Mutex<Prof> = Mutex::new(Prof { last_frame: None, window_from: None, window: new_acc(), all: new_acc(), text: String::new() });

const fn new_acc() -> Acc {
    Acc { stats: Vec::new(), frames: 0, frame_total: Duration::ZERO, frame_max: Duration::ZERO, slow: 0, hitch: 0, around_calls: 0, around_items: 0 }
}

pub fn on() -> bool {
    ON.load(Ordering::Relaxed)
}

fn with(f: impl FnOnce(&mut Prof)) {
    f(&mut PROF.lock().unwrap_or_else(|e| e.into_inner()));
}

/// 一个模块的 tick 花了这么久
pub fn add(name: &'static str, dt: Duration) {
    with(|p| {
        p.window.add(name, false, dt);
        p.all.add(name, false, dt);
    });
}

/// 某个模块里的一部分（不算进合计）
pub fn part(name: &'static str, dt: Duration) {
    with(|p| {
        p.window.add(name, true, dt);
        p.all.add(name, true, dt);
    });
}

/// 取了一次距离列表（around!）：花的时间、项数
pub fn around_done(dt: Duration, items: usize) {
    with(|p| {
        p.window.add("取距离列表", true, dt);
        p.all.add("取距离列表", true, dt);
        for a in [&mut p.window, &mut p.all] {
            a.around_calls += 1;
            a.around_items += items as u64;
        }
    });
}

/// 每帧开头调一次：算帧长，够一段了就把结果整理好给界面
pub fn frame() {
    if !on() {
        return;
    }
    let now = Instant::now();
    with(|p| {
        if let Some(t) = p.last_frame {
            let dt = now - t;
            if dt < LOAD_FRAME {
                p.window.frame(dt);
                p.all.frame(dt);
            }
        }
        p.last_frame = Some(now);
        let from = *p.window_from.get_or_insert(now);
        if now - from >= WINDOW {
            p.text = p.window.render();
            p.window = new_acc();
            p.window_from = Some(now);
        }
    });
}

fn set(enable: bool) {
    if enable == on() {
        return;
    }
    if enable {
        with(|p| *p = Prof { last_frame: None, window_from: None, window: new_acc(), all: new_acc(), text: "统计中，2 秒后出第一段结果……".to_string() });
        log("帧耗时统计：开始");
        ON.store(true, Ordering::Relaxed);
    } else {
        ON.store(false, Ordering::Relaxed);
        let mut text = String::new();
        with(|p| text = p.all.render());
        log(&format!("帧耗时统计：停止，开始以来的结果：\n{}", text.trim_end()));
    }
}

/// 开 / 关统计（dark_dev 调）
#[unsafe(no_mangle)]
pub extern "C" fn dr_prof_set(enable: u32) {
    set(enable != 0);
}

/// 最近一段的结果（UTF-8）写进 buf，返回写了多少字节（dark_dev 调）
///
/// # Safety
/// buf 要能写 cap 个字节。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn dr_prof_get(buf: *mut u8, cap: usize) -> usize {
    let mut n = 0;
    with(|p| {
        n = p.text.len().min(cap);
        unsafe { std::ptr::copy_nonoverlapping(p.text.as_ptr(), buf, n) };
    });
    n
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 合计不含「其中」；各模块按平均从大到小；帧长分档；距离列表每帧几次、平均几项
    #[test]
    fn render_sums_and_sorts() {
        let ms = Duration::from_millis;
        let mut a = new_acc();
        for dt in [ms(10), ms(25), ms(40), ms(5)] {
            a.frame(dt);
        }
        a.add("小", false, Duration::from_micros(400));
        a.add("大", false, ms(4));
        a.add("大", false, ms(2));
        a.add("大里的", true, ms(5));
        a.around_calls = 2;
        a.around_items = 120;
        let t = a.render();
        assert!(t.contains("平均 20.0 毫秒（50 帧/秒），最长 40.0 毫秒；超过 20 毫秒 2 帧，超过 33 毫秒 1 帧（共 4 帧）"), "{t}");
        assert!(t.contains("平均每帧 1.60 毫秒（占一帧的 8.0%）"), "{t}");
        assert!(t.find("  大：1500 / 4000").unwrap() < t.find("  小：100 / 400").unwrap(), "{t}");
        assert!(t.contains("  其中 大里的：1250 / 5000"), "{t}");
        assert!(t.contains("每帧取 0.5 次，平均 60 项"), "{t}");
    }
}
