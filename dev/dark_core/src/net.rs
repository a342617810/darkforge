//! 联机通道的传输层（联机计划 13.4）：游戏自带 steam_api64.dll 的 SteamNetworkingMessages v002 扁平接口，在整合包自己的频道上
//! 收发可靠消息。只在游戏的任务线程里调（lib.rs 每帧的任务），不开线程。
//! - 接口按名字从已经加载的 steam_api64.dll 取（有的加载器把原版改名成 steam_api64_o.dll，先找它），一个都不缺才用；
//! - 只关自己的频道（CloseChannelWithUser），不关整个 Steam 会话：Seamless Co-op 可能在同一条会话上收发；
//! - 结构照 Steamworks SDK 的 steamnetworkingtypes.h：SteamNetworkingIdentity 136 字节；SteamNetworkingMessage_t 只读开头的
//!   数据指针、长度、连接、对方身份，读完用 SteamAPI_SteamNetworkingMessage_t_Release 还回去。
//! 参考：黄金树爬塔（github.com/tamikip/erdtree-tower）的 native/src/steam_messages.rs 证明了这条路能和 Seamless 一起用（只借思路，没抄代码）。

use std::ffi::c_void;
use std::sync::OnceLock;

use windows::Win32::System::LibraryLoader::{GetModuleHandleW, GetProcAddress};
use windows::core::{PCSTR, PCWSTR};

use crate::log;

/// 整合包自己的频道号（「DFL1」）；Seamless 和游戏用别的频道，互不相干
pub const CHANNEL: i32 = 0x4446_4C31;
/// k_nSteamNetworkingSend_Reliable | k_nSteamNetworkingSend_AutoRestartBrokenSession
const SEND_FLAGS: i32 = 8 | 32;
/// 一次最多取几条
const RECV_MAX: usize = 32;
/// 单条消息最多多少字节（再大的不发、收到也丢掉）
pub const MAX_BYTES: usize = 64 * 1024;

#[repr(C, align(8))]
struct Identity {
    b: [u8; 136],
}

#[repr(C)]
struct Msg {
    data: *const u8,
    size: i32,
    conn: u32,
    peer: Identity,
}

type FnIface = unsafe extern "C" fn() -> *mut c_void;
type FnSend = unsafe extern "C" fn(*mut c_void, *const Identity, *const c_void, u32, i32, i32) -> i32;
type FnRecv = unsafe extern "C" fn(*mut c_void, i32, *mut *mut Msg, i32) -> i32;
type FnAccept = unsafe extern "C" fn(*mut c_void, *const Identity) -> bool;
type FnCloseCh = unsafe extern "C" fn(*mut c_void, *const Identity, i32) -> bool;
type FnSetId = unsafe extern "C" fn(*mut Identity, u64);
type FnGetId = unsafe extern "C" fn(*const Identity) -> u64;
type FnRelease = unsafe extern "C" fn(*mut Msg);
type FnSteamId = unsafe extern "C" fn(*mut c_void) -> u64;

pub struct Steam {
    iface: usize,
    send_fn: FnSend,
    recv_fn: FnRecv,
    accept_fn: FnAccept,
    close_fn: FnCloseCh,
    set_id: FnSetId,
    get_id: FnGetId,
    release: FnRelease,
    /// 本机的 Steam ID（SteamUser 接口给的；读不到是 0，会话里另外从名单拿）
    pub me: u64,
    /// 从哪个 DLL 取的接口
    pub module: &'static str,
}

static STEAM: OnceLock<Option<Steam>> = OnceLock::new();

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// 取一个导出函数（名字要带结尾的 \0）
unsafe fn sym(m: windows::Win32::Foundation::HMODULE, name: &[u8]) -> Option<unsafe extern "system" fn() -> isize> {
    unsafe { GetProcAddress(m, PCSTR(name.as_ptr())) }
}

fn load() -> Result<Steam, String> {
    for module in ["steam_api64_o.dll", "steam_api64.dll"] {
        let w = wide(module);
        let Ok(m) = (unsafe { GetModuleHandleW(PCWSTR(w.as_ptr())) }) else { continue };
        if m.is_invalid() {
            continue;
        }
        macro_rules! get {
            ($name:literal, $ty:ty) => {
                match unsafe { sym(m, concat!($name, "\0").as_bytes()) } {
                    Some(f) => unsafe { std::mem::transmute::<unsafe extern "system" fn() -> isize, $ty>(f) },
                    None => return Err(format!("{module} 里没有 {}", $name)),
                }
            };
        }
        let iface_fn = get!("SteamAPI_SteamNetworkingMessages_SteamAPI_v002", FnIface);
        let s = Steam {
            iface: 0,
            send_fn: get!("SteamAPI_ISteamNetworkingMessages_SendMessageToUser", FnSend),
            recv_fn: get!("SteamAPI_ISteamNetworkingMessages_ReceiveMessagesOnChannel", FnRecv),
            accept_fn: get!("SteamAPI_ISteamNetworkingMessages_AcceptSessionWithUser", FnAccept),
            close_fn: get!("SteamAPI_ISteamNetworkingMessages_CloseChannelWithUser", FnCloseCh),
            set_id: get!("SteamAPI_SteamNetworkingIdentity_SetSteamID64", FnSetId),
            get_id: get!("SteamAPI_SteamNetworkingIdentity_GetSteamID64", FnGetId),
            release: get!("SteamAPI_SteamNetworkingMessage_t_Release", FnRelease),
            me: 0,
            module,
        };
        let iface = unsafe { iface_fn() };
        if iface.is_null() {
            return Err(format!("{module} 的 SteamNetworkingMessages 接口是空的（Steam 没初始化？）"));
        }
        // 本机 Steam ID：SteamUser 接口（游戏这一版的 steam_api64 是 v021；新一些的有 v023）
        let mut me = 0u64;
        for user in [b"SteamAPI_SteamUser_v021\0".as_slice(), b"SteamAPI_SteamUser_v022\0", b"SteamAPI_SteamUser_v023\0"] {
            let (Some(u), Some(g)) = (unsafe { sym(m, user) }, unsafe { sym(m, b"SteamAPI_ISteamUser_GetSteamID\0") }) else { continue };
            let u: FnIface = unsafe { std::mem::transmute::<unsafe extern "system" fn() -> isize, FnIface>(u) };
            let g: FnSteamId = unsafe { std::mem::transmute::<unsafe extern "system" fn() -> isize, FnSteamId>(g) };
            let up = unsafe { u() };
            if !up.is_null() {
                me = unsafe { g(up) };
                break;
            }
        }
        return Ok(Steam { iface: iface as usize, me, ..s });
    }
    Err("没找到已经加载的 steam_api64.dll".into())
}

/// 接口（第一次调用时取，取不到记一行日志，之后都是 None）
pub fn steam() -> Option<&'static Steam> {
    STEAM
        .get_or_init(|| match load() {
            Ok(s) => {
                log(&format!("联机通道：Steam 消息接口就绪（{}，频道 0x{CHANNEL:08X}，本机 Steam ID {}）", s.module,
                             if s.me != 0 { "读到了" } else { "没读到" }));
                Some(s)
            }
            Err(e) => {
                log(&format!("联机通道：Steam 消息接口用不了（{e}），联机通道不工作"));
                None
            }
        })
        .as_ref()
}

impl Steam {
    fn ident(&self, id: u64) -> Identity {
        let mut i = Identity { b: [0; 136] };
        unsafe { (self.set_id)(&mut i, id) };
        i
    }

    /// 发一条可靠消息；返回 Steam 的结果码（1 = 成功）
    pub fn send(&self, to: u64, data: &[u8]) -> i32 {
        if data.is_empty() || data.len() > MAX_BYTES {
            return 0;
        }
        let i = self.ident(to);
        unsafe { (self.send_fn)(self.iface as *mut c_void, &i, data.as_ptr() as *const c_void, data.len() as u32, SEND_FLAGS, CHANNEL) }
    }

    /// 取这一帧收到的（发送者 Steam ID, 内容）；超长的丢掉
    pub fn recv(&self) -> Vec<(u64, Vec<u8>)> {
        let mut ptrs: [*mut Msg; RECV_MAX] = [std::ptr::null_mut(); RECV_MAX];
        let n = unsafe { (self.recv_fn)(self.iface as *mut c_void, CHANNEL, ptrs.as_mut_ptr(), RECV_MAX as i32) };
        let mut out = Vec::new();
        for &m in ptrs.iter().take(n.clamp(0, RECV_MAX as i32) as usize) {
            if m.is_null() {
                continue;
            }
            let (data, size) = unsafe { ((*m).data, (*m).size) };
            let from = unsafe { (self.get_id)(&(*m).peer) };
            if !data.is_null() && size > 0 && (size as usize) <= MAX_BYTES {
                out.push((from, unsafe { std::slice::from_raw_parts(data, size as usize) }.to_vec()));
            }
            unsafe { (self.release)(m) };
        }
        out
    }

    /// 接受这个人发来的会话请求（还没有请求时什么都不做）
    pub fn accept(&self, peer: u64) {
        let i = self.ident(peer);
        unsafe { (self.accept_fn)(self.iface as *mut c_void, &i) };
    }

    /// 关掉和这个人在本频道上的往来（不碰整个会话）
    pub fn close(&self, peer: u64) {
        let i = self.ident(peer);
        unsafe { (self.close_fn)(self.iface as *mut c_void, &i, CHANNEL) };
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 结构大小、偏移照 Steamworks SDK（SteamNetworkingIdentity 136 字节、8 字节对齐；消息的对方身份在 16 字节处）
    #[test]
    fn layouts_match_sdk() {
        assert_eq!(std::mem::size_of::<Identity>(), 136);
        assert_eq!(std::mem::align_of::<Identity>(), 8);
        assert_eq!(std::mem::offset_of!(Msg, size), 8);
        assert_eq!(std::mem::offset_of!(Msg, conn), 12);
        assert_eq!(std::mem::offset_of!(Msg, peer), 16);
    }
}
