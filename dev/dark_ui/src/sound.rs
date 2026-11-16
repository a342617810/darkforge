//! 装备工坊成功时的铁砧敲击声（用户 2026-11-10「继承重铸和超限时加一个原版强化武器的音效」→ 游戏里的菜单音效都不像 →
//! 「能自己做或者搜索铁砧敲击的声音吗」→ 合成的太清脆 →「上网搜搜吧」「有没有厚重一点的」）：dll\dark_ui\anvil.wav
//! （Kenney「Impact Sounds」CC0 的挖矿敲击 + 一点钟形余音、提亮高频，dev\dark_ui\sounds\make_heavy.py 的 heavy_1b），
//! 用 Windows 的 PlaySoundW 异步放（winmm.dll 用到时才载入、动态取函数，不用改链接）。文件没有就不响；同时只放一个，新的打断旧的。
//! 不走游戏的音效系统，所以游戏里的音量设置管不到它（做的时候峰值压到 0.5）。
use std::os::windows::ffi::OsStrExt;
use std::path::Path;
use std::sync::OnceLock;

use hudhook::windows::Win32::System::LibraryLoader::{GetProcAddress, LoadLibraryA};
use hudhook::windows::core::s;

type PlaySoundW = unsafe extern "system" fn(*const u16, isize, u32) -> i32;

const SND_ASYNC: u32 = 0x0001;
const SND_NODEFAULT: u32 = 0x0002;
const SND_FILENAME: u32 = 0x0002_0000;

fn play_sound_w() -> Option<PlaySoundW> {
    static F: OnceLock<Option<usize>> = OnceLock::new();
    let p = *F.get_or_init(|| unsafe {
        let m = LoadLibraryA(s!("winmm.dll")).ok()?;
        GetProcAddress(m, s!("PlaySoundW")).map(|f| f as usize)
    });
    p.map(|p| unsafe { std::mem::transmute::<usize, PlaySoundW>(p) })
}

/// 异步放一个 WAV；放不了（文件没有、winmm 载不进来）就算了
pub fn play(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(f) = play_sound_w() else { return false };
    let w: Vec<u16> = path.as_os_str().encode_wide().chain(std::iter::once(0)).collect();
    unsafe { f(w.as_ptr(), 0, SND_ASYNC | SND_NODEFAULT | SND_FILENAME) != 0 }
}
