// 构建版本（dark_core.log 开头写，联机计划 13.9 D；黄金树爬塔好几轮测试白跑，进程里还是旧 DLL）：
// git 提交号（src 有没提交的改动加「+改动」；读不到 git 写 unknown）+ 构建时间（UTC）。src 改了就重跑
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

fn git(args: &[&str]) -> Option<String> {
    let o = Command::new("git").args(["-c", "safe.directory=*"]).args(args).output().ok()?;
    o.status.success().then(|| String::from_utf8_lossy(&o.stdout).trim().to_string())
}

/// 1970-01-01 起的天数 → 年月日（Howard Hinnant 的 civil_from_days）
fn civil(days: i64) -> (i64, u32, u32) {
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z.rem_euclid(146097);
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (yoe + era * 400 + i64::from(m <= 2), m, d)
}

fn main() {
    let commit = git(&["rev-parse", "--short=8", "HEAD"]).filter(|s| !s.is_empty()).unwrap_or_else(|| "unknown".into());
    let dirty = git(&["status", "--porcelain", "--", "src", "Cargo.toml", "build.rs"]).is_some_and(|s| !s.is_empty());
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs() as i64).unwrap_or(0);
    let (y, mo, d) = civil(secs.div_euclid(86400));
    let t = secs.rem_euclid(86400);
    println!("cargo:rustc-env=DR_BUILD={commit}{}", if dirty { "+改动" } else { "" });
    println!("cargo:rustc-env=DR_BUILD_TIME={y}-{mo:02}-{d:02} {:02}:{:02} UTC", t / 3600, t % 3600 / 60);
    println!("cargo:rerun-if-changed=src");
    println!("cargo:rerun-if-changed=Cargo.toml");
    println!("cargo:rerun-if-changed=build.rs");
}
