//! 直接放 WAV（用户 2026-11-11「唤声船和雷电羊球的音效呢」）：唤声船的声音原版在唤声者自己的音效库 cs_c4950 里，平时没载入放不出来，
//! 所以骑船的摇铃、幽灵嗡鸣是自己合成的（dev\dark_core\sounds\make_boat.py），放在 dll\dark_core\sounds\，用 Windows 的 PlaySoundW 放
//! （winmm.dll 用到时才载入、动态取函数，不用改链接）。不走游戏的音效系统：游戏音量管不到、没有方位；整个进程同时只放一个
//! （dark_ui 的铁砧声也是这个函数，两个撞上时后放的打断先放的，平时碰不到：一个在赐福、一个在骑船）。文件没有就不响。
use std::os::windows::ffi::OsStrExt;
use std::path::Path;
use std::sync::OnceLock;

use windows::Win32::System::LibraryLoader::{GetProcAddress, LoadLibraryA};
use windows::core::s;

type PlaySoundW = unsafe extern "system" fn(*const u16, isize, u32) -> i32;

const SND_ASYNC: u32 = 0x0001;
const SND_NODEFAULT: u32 = 0x0002;
const SND_LOOP: u32 = 0x0008;
const SND_FILENAME: u32 = 0x0002_0000;

fn play_sound_w() -> Option<PlaySoundW> {
    static F: OnceLock<Option<usize>> = OnceLock::new();
    let p = *F.get_or_init(|| unsafe {
        let m = LoadLibraryA(s!("winmm.dll")).ok()?;
        GetProcAddress(m, s!("PlaySoundW")).map(|f| f as usize)
    });
    p.map(|p| unsafe { std::mem::transmute::<usize, PlaySoundW>(p) })
}

/// 异步放一个 WAV（looped = 一直循环到 stop）；放不了（文件没有、winmm 载不进来）返回 false
pub fn play(path: &Path, looped: bool) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(f) = play_sound_w() else { return false };
    let w: Vec<u16> = path.as_os_str().encode_wide().chain(std::iter::once(0)).collect();
    let flags = SND_ASYNC | SND_NODEFAULT | SND_FILENAME | if looped { SND_LOOP } else { 0 };
    unsafe { f(w.as_ptr(), 0, flags) != 0 }
}

/// 停掉正在放的（PlaySound 的「空声音」）
pub fn stop() {
    if let Some(f) = play_sound_w() {
        unsafe {
            f(std::ptr::null(), 0, 0);
        }
    }
}

/// WAV 的时长（秒）：data 块的字节数 / 每秒字节数；读不懂返回 None
pub fn wav_secs(path: &Path) -> Option<f32> {
    let b = std::fs::read(path).ok()?;
    wav_secs_of(&b)
}

fn wav_secs_of(b: &[u8]) -> Option<f32> {
    if b.len() < 12 || &b[0..4] != b"RIFF" || &b[8..12] != b"WAVE" {
        return None;
    }
    let (mut p, mut rate) = (12usize, 0u32);
    while p + 8 <= b.len() {
        let id = &b[p..p + 4];
        let size = u32::from_le_bytes(b[p + 4..p + 8].try_into().ok()?) as usize;
        if id == b"fmt " && p + 20 <= b.len() {
            rate = u32::from_le_bytes(b[p + 16..p + 20].try_into().ok()?);
        }
        if id == b"data" {
            return (rate > 0).then(|| size as f32 / rate as f32);
        }
        p += 8 + size + (size & 1);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wav_length_from_header() {
        let mut b = Vec::new();
        b.extend(b"RIFF");
        b.extend(0u32.to_le_bytes());
        b.extend(b"WAVEfmt ");
        b.extend(16u32.to_le_bytes());
        b.extend([1, 0, 1, 0]);
        b.extend(44100u32.to_le_bytes());
        b.extend(88200u32.to_le_bytes());
        b.extend([2, 0, 16, 0]);
        b.extend(b"data");
        b.extend(264600u32.to_le_bytes());
        assert_eq!(wav_secs_of(&b), Some(3.0));
        assert_eq!(wav_secs_of(b"nope"), None);
    }
}
