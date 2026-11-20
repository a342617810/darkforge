//! 联机通道（联机计划 13.4）：Seamless Co-op 之外，整合包自己在队员之间收发消息的基础设施。传输见 net.rs。
//! 这一版只把通道跑通，上面还没有挂功能（以后的队友装备显示、赠送、房主下发抽签结果都走它）：
//! - 名单：coop::roster()，会话就绪（大厅 主机 / 客机、协议 Ingame、没人在加入中）才连；名单里不是本机的都是要连的队员；
//! - 握手：每个队员各自给对方发 HELLO（随机数 + 协议版本 + 兼容档案），收到对方的 HELLO 回 ACK（带回对方的随机数）。
//!   本机的 HELLO 被确认、也收到了对方的 HELLO = 连上。对方重发了新的随机数（对方重启了 / 重连了）就重新算；
//! - 兼容档案：启动器联机启动时写 dll\dark_core\coop_profile.txt（一行一项：整合包版本、联机核对码、世界、Seamless 的随人数加强、
//!   敌人设置），握手时逐项比对，不一样的记日志，连接标成「档案不一致」（以后要同步的功能看 compatible()）；
//! - 心跳：连上后每 PING_EVERY 发 PING，对方回 PONG，算往返时间；LOST 内收不到对方任何消息 = 断了，从握手重来；
//! - 握手退避：对方一直没回音时 HELLO 越发越慢，几分钟后停（HELLO_GIVE_UP / HELLO_BUDGET），名单变了或对方来了消息再开始；
//! - 只收名单里的人发来的（自测时收自己发给自己的）；看不懂的、协议版本不同的丢掉并记一次。加载了 Seamless 就每帧收，
//!   不在会话里收到的直接丢（不让 Steam 攒着）；发件箱有上限，通道用不了时清掉。
//! - 开发工具（F9「联机通道测试」）写 coopnet_req.txt：状态 / 自测 / 测试 <文字>。
//! 日志开头「联机通道」。参考黄金树爬塔（github.com/tamikip/erdtree-tower）的握手思路，没抄代码。

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use eldenring::cs::ChrInsExt;

use crate::{dir, log};

/// 协议版本：消息格式改了就加一，不同版本的互相不认
pub const PROTO: u32 = 3;
const MAGIC: &str = "DFL";
const HELLO_EVERY: Duration = Duration::from_secs(1);
/// 握手的退避：一直没有对方的任何消息时，头 HELLO_FAST_FOR 每秒一条 HELLO，之后每 HELLO_SLOW 一条，到 HELLO_GIVE_UP 就不发了
/// （名单变了、或者对方来了消息再开始）。对方一直不读整合包的频道（没装整合包、dark_core 没起来、名单一直没就绪）时，
/// Steam 给他攒着的消息不会一直涨（和 Seamless 共用同一条连接，接收缓冲攒满了会丢包）
const HELLO_FAST_FOR: Duration = Duration::from_secs(30);
const HELLO_SLOW: Duration = Duration::from_secs(5);
const HELLO_GIVE_UP: Duration = Duration::from_secs(180);
/// 同一个队员一直没回音时，这次会话里最多给他发几条 HELLO（名单变了重新开始的也算在里面；收到他的消息就重新算）
const HELLO_BUDGET: u32 = 200;
/// 发件箱最多攒几条（通道用不了时不让它一直涨；满了丢最早的）
const OUT_MAX: usize = 256;
const PING_EVERY: Duration = Duration::from_secs(5);
const LOST: Duration = Duration::from_secs(20);
const RTT_LOG_EVERY: Duration = Duration::from_secs(60);
const SELFTEST_WAIT: Duration = Duration::from_secs(5);
const ROSTER_EVERY: Duration = Duration::from_millis(500);
/// 兼容档案里各项的中文名（对不上时写日志用）
const LABELS: [(&str, &str); 7] =
    [("version", "整合包版本"), ("fingerprint", "联机核对码"), ("world", "世界"), ("scaling", "Seamless 随人数加强"), ("enemy", "敌人设置"),
     ("seamless", "Seamless Co-op 版本"), ("mods", "自己加的模组")];

// ------------------------------------------------------------------ 消息

#[derive(Clone, Debug, PartialEq)]
pub enum Kind {
    Hello,
    Ack,
    Ping,
    Pong,
    Text,
    /// 客机 → 房主：替我改这个敌人（联机计划 13.5）：e 实体编号、op speed / poise / rmsp、v 值
    Foe,
    /// 房主 → 客机：这个敌人魇化了（e 实体编号、f 词条序号，逗号隔开）
    Nm,
    /// 客机 → 房主：我戴着时隙，这几个敌人（e 实体编号，逗号隔开）乘 m；m = 1 = 摘下了（speed.rs，协议 2 起）
    Slip,
    /// 房主 → 客机：房主亮着的难度档位标记（f，逗号隔开；空 = 普通），客机的敌人一侧照用（coop::tier_flag，联机计划 13.9 A）
    Tier,
    /// 赠送（联机计划 13.7，gear/gift.rs）：n 随机数、c 类别、lv 强化等级、r 配方
    Gift,
    /// 收下了（n）
    GiftOk,
    /// 没收下（n、why）
    GiftNo,
    /// 送的人 → 收的人：对方回 GOK 时这件已经装备上了（或换了角色），没送成，请把送来的那件（n）退回（gear/gift.rs）。
    /// 后加的种类，没改协议版本：赠送只在档案一致（整合包版本一样）的队员之间，老版本不会收到
    GiftBack,
    /// 斗技场试炼（arena.rs，协议 3 起）：房主 → 队员 op=state（进度），队员 → 房主 op=me（自己的情况）
    Arena,
}

impl Kind {
    fn name(&self) -> &'static str {
        match self {
            Kind::Hello => "HELLO",
            Kind::Ack => "ACK",
            Kind::Ping => "PING",
            Kind::Pong => "PONG",
            Kind::Text => "TEXT",
            Kind::Foe => "FOE",
            Kind::Nm => "NM",
            Kind::Slip => "SLIP",
            Kind::Tier => "TIER",
            Kind::Gift => "GIFT",
            Kind::GiftOk => "GOK",
            Kind::GiftNo => "GNO",
            Kind::GiftBack => "GBK",
            Kind::Arena => "ARENA",
        }
    }

    fn parse(s: &str) -> Option<Kind> {
        Some(match s {
            "HELLO" => Kind::Hello,
            "ACK" => Kind::Ack,
            "PING" => Kind::Ping,
            "PONG" => Kind::Pong,
            "TEXT" => Kind::Text,
            "FOE" => Kind::Foe,
            "NM" => Kind::Nm,
            "SLIP" => Kind::Slip,
            "TIER" => Kind::Tier,
            "GIFT" => Kind::Gift,
            "GOK" => Kind::GiftOk,
            "GNO" => Kind::GiftNo,
            "GBK" => Kind::GiftBack,
            "ARENA" => Kind::Arena,
            _ => return None,
        })
    }
}

/// 一条消息：头一行「DFL 协议版本 种类」，后面每行「键=值」（值里不能有换行，编码时换成空格）
#[derive(Clone, Debug, PartialEq)]
pub struct Packet {
    pub kind: Kind,
    pub fields: Vec<(String, String)>,
}

impl Packet {
    pub fn new(kind: Kind) -> Self {
        Packet { kind, fields: Vec::new() }
    }

    pub fn with(mut self, k: &str, v: impl ToString) -> Self {
        self.fields.push((k.to_string(), v.to_string().replace(['\r', '\n'], " ")));
        self
    }

    pub fn get(&self, k: &str) -> Option<&str> {
        self.fields.iter().find(|(a, _)| a == k).map(|(_, b)| b.as_str())
    }

    pub fn encode(&self) -> Vec<u8> {
        let mut s = format!("{MAGIC} {PROTO} {}\n", self.kind.name());
        for (k, v) in &self.fields {
            s.push_str(k);
            s.push('=');
            s.push_str(v);
            s.push('\n');
        }
        s.into_bytes()
    }

    /// 解码；不是整合包的消息 / 协议版本不同返回 Err（说明原因）
    pub fn decode(b: &[u8]) -> Result<Packet, String> {
        let s = std::str::from_utf8(b).map_err(|_| "不是文字".to_string())?;
        let mut lines = s.lines();
        let head = lines.next().unwrap_or("");
        let mut h = head.split(' ');
        if h.next() != Some(MAGIC) {
            return Err("不是整合包的消息".into());
        }
        let v: u32 = h.next().and_then(|x| x.parse().ok()).ok_or("协议版本读不出来")?;
        if v != PROTO {
            return Err(format!("协议版本不同（对方 {v}，本机 {PROTO}；两边整合包版本不一样？）"));
        }
        let kind = h.next().and_then(Kind::parse).ok_or("种类不认识")?;
        let mut fields = Vec::new();
        for l in lines {
            if let Some((k, v)) = l.split_once('=') {
                fields.push((k.to_string(), v.to_string()));
            }
        }
        Ok(Packet { kind, fields })
    }
}

// ------------------------------------------------------------------ 兼容档案

/// coop_profile.txt：一行「键 值」（Tab 或空格隔开），# 开头是注释
pub fn parse_profile(text: &str) -> Vec<(String, String)> {
    text.lines()
        .map(|l| l.trim_start_matches('\u{feff}').trim())
        .filter(|l| !l.is_empty() && !l.starts_with('#'))
        .filter_map(|l| l.split_once(['\t', ' ']).map(|(k, v)| (k.trim().to_string(), v.trim().to_string())))
        .collect()
}

/// 两份档案不一样的项（中文名、本机的、对方的）
pub fn profile_diff(mine: &[(String, String)], theirs: &[(String, String)]) -> Vec<(String, String, String)> {
    let mut keys: Vec<&str> = mine.iter().chain(theirs).map(|(k, _)| k.as_str()).collect();
    keys.sort();
    keys.dedup();
    let get = |p: &[(String, String)], k: &str| p.iter().find(|(a, _)| a == k).map(|(_, v)| v.clone()).unwrap_or_else(|| "（没有）".into());
    keys.into_iter()
        .filter_map(|k| {
            let (a, b) = (get(mine, k), get(theirs, k));
            (a != b).then(|| (LABELS.iter().find(|(x, _)| *x == k).map_or(k.to_string(), |(_, n)| n.to_string()), a, b))
        })
        .collect()
}

// ------------------------------------------------------------------ 收发（测试时换成假的）

pub trait Transport {
    fn send(&mut self, to: u64, data: &[u8]) -> bool;
    fn recv(&mut self) -> Vec<(u64, Vec<u8>)>;
    fn accept(&mut self, peer: u64);
    fn close(&mut self, peer: u64);
    /// 和这个人的 Steam 连接状态（日志用的一句；测试的假网络没有）
    fn conn_text(&mut self, _peer: u64) -> Option<String> {
        None
    }
}

/// 日志后面接的「；Steam 连接：…」
fn conn_suffix(t: &mut impl Transport, peer: u64) -> String {
    t.conn_text(peer).map_or(String::new(), |s| format!("；{s}"))
}

// ------------------------------------------------------------------ 每个队员的状态

#[derive(Debug)]
pub struct Peer {
    pub id: u64,
    pub host: bool,
    /// 本机发给他的 HELLO 用的随机数
    my_nonce: u64,
    /// 他的 HELLO 里的随机数（收到过）
    their_nonce: Option<u64>,
    /// 他确认了本机的 HELLO
    acked: bool,
    pub profile_diff: Vec<(String, String, String)>,
    last_rx: Option<Instant>,
    last_hello: Option<Instant>,
    /// 这一轮没回音的握手从什么时候开始（收到他的任何消息清掉）；退避到头了不再发 HELLO（gave_up）
    quiet_since: Option<Instant>,
    gave_up: bool,
    last_ping: Option<Instant>,
    ping_seq: u32,
    ping_sent: HashMap<u32, Instant>,
    pub rtt_ms: Option<u32>,
    rtt_logged: Option<Instant>,
    linked_logged: bool,
    /// 他 HELLO 里带的联机随机码（房主的：档案对不上时存给启动器导入）
    pub code: Option<String>,
}

impl Peer {
    fn fresh(id: u64, host: bool, my_nonce: u64) -> Peer {
        Peer {
            id, host, my_nonce, their_nonce: None, acked: false, profile_diff: Vec::new(), last_rx: None, last_hello: None, quiet_since: None,
            gave_up: false, last_ping: None, ping_seq: 0, ping_sent: HashMap::new(), rtt_ms: None, rtt_logged: None, linked_logged: false, code: None,
        }
    }

    pub fn linked(&self) -> bool {
        self.acked && self.their_nonce.is_some()
    }
}

pub struct Link {
    pub me: u64,
    pub profile: Vec<(String, String)>,
    pub peers: HashMap<u64, Peer>,
    rng: u64,
    told_bad: Vec<String>,
    /// 收到的、要游戏里处理的（FOE、NM）：(发送者, 消息)，tick 取走
    pub inbox: Vec<(u64, Packet)>,
    /// 每个队员：上次收到他的消息以后发了几条 HELLO（跨名单变化、断线重握手都算，到 HELLO_BUDGET 就不发了）
    unanswered: BTreeMap<u64, u32>,
}

fn short(id: u64) -> String {
    // 日志只写 Steam ID 的后 4 位（够分清是谁，不把整串账号写进诊断包）
    format!("…{:04}", id % 10_000)
}

impl Link {
    pub fn new(me: u64, profile: Vec<(String, String)>, seed: u64) -> Self {
        Link { me, profile, peers: HashMap::new(), rng: seed | 1, told_bad: Vec::new(), inbox: Vec::new(), unanswered: BTreeMap::new() }
    }

    fn nonce(&mut self) -> u64 {
        // splitmix64
        self.rng = self.rng.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.rng;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        (z ^ (z >> 31)).max(1)
    }

    fn hello(&self, p: &Peer) -> Packet {
        let mut pk = Packet::new(Kind::Hello).with("nonce", p.my_nonce);
        for (k, v) in &self.profile {
            pk = pk.with(&format!("p.{k}"), v);
        }
        pk
    }

    /// 名单变了：新来的建状态，走了的关频道、删掉。roster = (Steam ID, 是不是房主)，不含本机
    pub fn set_roster(&mut self, roster: &[(u64, bool)], t: &mut impl Transport) {
        let gone: Vec<u64> = self.peers.keys().copied().filter(|id| !roster.iter().any(|(r, _)| r == id)).collect();
        let mut changed = !gone.is_empty();
        for id in gone {
            self.peers.remove(&id);
            let conn = conn_suffix(t, id);
            t.close(id);
            log(&format!("联机通道：队员 {} 离开了会话{conn}", short(id)));
        }
        for &(id, host) in roster {
            if id == self.me || id == 0 {
                continue;
            }
            if let Some(p) = self.peers.get_mut(&id) {
                p.host = host;
                continue;
            }
            let n = self.nonce();
            self.peers.insert(id, Peer::fresh(id, host, n));
            changed = true;
            log(&format!("联机通道：会话里有队员 {}（{}），开始握手", short(id), if host { "房主" } else { "客机" }));
        }
        // 名单变了：没连上的从头退避（停了的重新开始发 HELLO；HELLO_BUDGET 用完了的不再开始，等他来消息）
        if changed {
            for p in self.peers.values_mut().filter(|p| !p.linked()) {
                if self.unanswered.get(&p.id).is_some_and(|&n| n >= HELLO_BUDGET) {
                    continue;
                }
                if p.gave_up {
                    log(&format!("联机通道：名单变了，重新和队员 {} 握手", short(p.id)));
                }
                p.gave_up = false;
                p.quiet_since = None;
                p.last_hello = None;
            }
        }
    }

    /// 每帧：收消息、按时发 HELLO / PING、看有没有断
    pub fn poll(&mut self, t: &mut impl Transport, now: Instant) {
        for (from, data) in t.recv() {
            self.handle(from, &data, t, now);
        }
        let ids: Vec<u64> = self.peers.keys().copied().collect();
        for id in ids {
            let mut out: Vec<Packet> = Vec::new();
            let mut reset = false;
            {
                let p = self.peers.get_mut(&id).unwrap();
                if p.linked() && p.last_rx.is_some_and(|r| now.duration_since(r) >= LOST) {
                    log(&format!("联机通道：队员 {} {} 秒没有消息，当作断了，重新握手{}", short(id), LOST.as_secs(), conn_suffix(t, id)));
                    reset = true;
                } else if !p.linked() {
                    // 退避：没回音的时间越长发得越慢，到头了不发（见 HELLO_GIVE_UP / HELLO_BUDGET）
                    if !p.gave_up {
                        let quiet = now.duration_since(*p.quiet_since.get_or_insert(now));
                        let sent = self.unanswered.get(&id).copied().unwrap_or(0);
                        if quiet >= HELLO_GIVE_UP || sent >= HELLO_BUDGET {
                            p.gave_up = true;
                            log(&format!("联机通道：队员 {} {}，先不发握手了（对方可能没用整合包；名单变了或者对方来了消息再试）{}", short(id),
                                         if sent >= HELLO_BUDGET { format!("发了 {sent} 次握手都没有回音") } else { format!("{} 秒没有回音", quiet.as_secs()) },
                                         conn_suffix(t, id)));
                        } else if p.last_hello.is_none_or(|h| now.duration_since(h) >= if quiet < HELLO_FAST_FOR { HELLO_EVERY } else { HELLO_SLOW }) {
                            p.last_hello = Some(now);
                            out.push(Packet::new(Kind::Hello)); // 占位，下面换成真的 HELLO（借 self 的档案）
                        }
                    }
                } else if p.last_ping.is_none_or(|h| now.duration_since(h) >= PING_EVERY) {
                    p.last_ping = Some(now);
                    p.ping_seq += 1;
                    let seq = p.ping_seq;
                    p.ping_sent.insert(seq, now);
                    p.ping_sent.retain(|_, at| now.duration_since(*at) < LOST);
                    out.push(Packet::new(Kind::Ping).with("seq", seq));
                }
            }
            if reset {
                let n = self.nonce();
                let p = self.peers.get_mut(&id).unwrap();
                *p = Peer::fresh(id, p.host, n);
                continue;
            }
            for pk in out {
                let pk = if pk.kind == Kind::Hello {
                    t.accept(id);
                    *self.unanswered.entry(id).or_insert(0) += 1;
                    self.hello(&self.peers[&id])
                } else {
                    pk
                };
                t.send(id, &pk.encode());
            }
        }
    }

    fn bad_once(&mut self, what: String) {
        if !self.told_bad.contains(&what) && self.told_bad.len() < 20 {
            log(&format!("联机通道：{what}"));
            self.told_bad.push(what);
        }
    }

    fn handle(&mut self, from: u64, data: &[u8], t: &mut impl Transport, now: Instant) {
        if from == self.me {
            if let Ok(pk) = Packet::decode(data) {
                if pk.kind == Kind::Text {
                    log(&format!("联机通道：收到了自己发给自己的消息「{}」（自测：Steam 的收发是通的）", pk.get("text").unwrap_or("")));
                    SELFTEST.lock().unwrap_or_else(|e| e.into_inner()).take();
                }
            }
            return;
        }
        if !self.peers.contains_key(&from) {
            self.bad_once(format!("收到不在名单里的 {} 发来的消息，丢掉", short(from)));
            return;
        }
        let pk = match Packet::decode(data) {
            Ok(pk) => pk,
            Err(e) => {
                self.bad_once(format!("队员 {} 的消息看不懂：{e}", short(from)));
                return;
            }
        };
        let profile = self.profile.clone();
        let p = self.peers.get_mut(&from).unwrap();
        p.last_rx = Some(now);
        // 他在读本频道：握手的退避从头算，停了的马上重发 HELLO（对方晚起来时靠这个接上）
        self.unanswered.remove(&from);
        p.quiet_since = None;
        if p.gave_up {
            p.gave_up = false;
            p.last_hello = None;
            log(&format!("联机通道：队员 {} 来了消息，重新握手", short(from)));
        }
        let mut reply: Vec<Packet> = Vec::new();
        let mut keep: Option<Packet> = None;
        match pk.kind {
            Kind::Hello => {
                let Some(n) = pk.get("nonce").and_then(|x| x.parse::<u64>().ok()) else { return };
                // 对方换了随机数 = 对方从头握手（断过、重连了）：本机也退回握手、马上重发 HELLO，不然对方等不到本机的 HELLO
                if p.their_nonce.is_some_and(|old| old != n) {
                    log(&format!("联机通道：队员 {} 重新握手（对方重连了？）", short(from)));
                    p.linked_logged = false;
                    p.acked = false;
                    p.last_hello = None;
                }
                p.their_nonce = Some(n);
                let theirs: Vec<(String, String)> =
                    pk.fields.iter().filter_map(|(k, v)| k.strip_prefix("p.").map(|k| (k.to_string(), v.clone()))).collect();
                // 联机随机码不算档案的一项（核对码已经管着），单独记下
                p.code = theirs.iter().find(|(k, _)| k == "code").map(|(_, v)| v.clone());
                let strip = |v: &[(String, String)]| v.iter().filter(|(k, _)| k != "code").cloned().collect::<Vec<_>>();
                p.profile_diff = profile_diff(&strip(&profile), &strip(&theirs));
                reply.push(Packet::new(Kind::Ack).with("nonce", n));
            }
            Kind::Ack => {
                if pk.get("nonce").and_then(|x| x.parse::<u64>().ok()) == Some(p.my_nonce) {
                    p.acked = true;
                }
            }
            Kind::Ping => {
                if let Some(seq) = pk.get("seq") {
                    reply.push(Packet::new(Kind::Pong).with("seq", seq));
                }
            }
            Kind::Pong => {
                if let Some(at) = pk.get("seq").and_then(|x| x.parse::<u32>().ok()).and_then(|s| p.ping_sent.remove(&s)) {
                    let ms = now.duration_since(at).as_millis().min(60_000) as u32;
                    p.rtt_ms = Some(ms);
                    if p.rtt_logged.is_none_or(|l| now.duration_since(l) >= RTT_LOG_EVERY) {
                        p.rtt_logged = Some(now);
                        log(&format!("联机通道：队员 {} 往返 {ms} 毫秒{}", short(from), conn_suffix(t, from)));
                    }
                }
            }
            Kind::Text => log(&format!("联机通道：队员 {} 发来测试消息「{}」", short(from), pk.get("text").unwrap_or(""))),
            Kind::Foe | Kind::Nm | Kind::Slip | Kind::Tier | Kind::Gift | Kind::GiftOk | Kind::GiftNo | Kind::GiftBack | Kind::Arena => keep = Some(pk.clone()),
        }
        if p.linked() && !p.linked_logged {
            p.linked_logged = true;
            if p.profile_diff.is_empty() {
                log(&format!("联机通道：和队员 {}（{}）连上了，兼容档案一致", short(from), if p.host { "房主" } else { "客机" }));
            } else {
                let d: Vec<String> = p.profile_diff.iter().map(|(n, a, b)| format!("{n}：本机 {a} / 队员 {b}")).collect();
                log(&format!("联机通道：和队员 {}（{}）连上了，但兼容档案不一致（要同步的功能先不开）：{}", short(from),
                             if p.host { "房主" } else { "客机" }, d.join("；")));
            }
        }
        for r in reply {
            t.send(from, &r.encode());
        }
        if let Some(k) = keep {
            self.inbox.push((from, k));
        }
    }

    /// 发给房主（连上了才发）；返回发没发
    pub fn send_host(&mut self, pk: &Packet, t: &mut impl Transport) -> bool {
        let Some(id) = self.peers.values().find(|p| p.host && p.linked()).map(|p| p.id) else { return false };
        t.send(id, &pk.encode())
    }

    /// 从这个队员来的、他是房主
    pub fn from_host(&self, id: u64) -> bool {
        self.peers.get(&id).is_some_and(|p| p.host && p.linked())
    }

    /// 和这个队员连上了、档案也一致（赠送等要同步的功能看它）
    pub fn compatible(&self, id: u64) -> bool {
        self.peers.get(&id).is_some_and(|p| p.linked() && p.profile_diff.is_empty())
    }

    /// 给所有连上的队员发一条
    pub fn broadcast(&mut self, pk: &Packet, t: &mut impl Transport) -> usize {
        let ids: Vec<u64> = self.peers.values().filter(|p| p.linked()).map(|p| p.id).collect();
        for &id in &ids {
            t.send(id, &pk.encode());
        }
        ids.len()
    }

    pub fn status(&self) -> String {
        if self.peers.is_empty() {
            return "没有队员（不在会话里，或会话里只有自己）".into();
        }
        let mut v: Vec<String> = self.peers.values().map(|p| {
            format!("{}（{}）{}{}{}", short(p.id), if p.host { "房主" } else { "客机" },
                    if p.linked() { "已连上" } else if p.gave_up { "一直没回音，先不握手了" } else if p.their_nonce.is_some() { "等对方确认" } else { "等对方回话" },
                    p.rtt_ms.map(|m| format!("，往返 {m} 毫秒")).unwrap_or_default(),
                    if p.linked() && !p.profile_diff.is_empty() { "，档案不一致" } else { "" })
        }).collect();
        v.sort();
        v.join("；")
    }
}

// ------------------------------------------------------------------ 游戏里

struct SteamT(&'static crate::net::Steam);

impl Transport for SteamT {
    fn send(&mut self, to: u64, data: &[u8]) -> bool {
        self.0.send(to, data) == 1
    }
    fn recv(&mut self) -> Vec<(u64, Vec<u8>)> {
        self.0.recv()
    }
    fn accept(&mut self, peer: u64) {
        self.0.accept(peer)
    }
    fn close(&mut self, peer: u64) {
        self.0.close(peer)
    }
    fn conn_text(&mut self, peer: u64) -> Option<String> {
        self.0.conn_info(peer).map(|c| c.text())
    }
}

struct St {
    link: Option<Link>,
    roster_at: Option<Instant>,
    me: u64,
    /// 存过的房主联机随机码（不重复写）
    code_saved: Option<String>,
    foe_logged: u32,
    /// 房主：上次发的难度档（档位标记, 时间）、下次看的时间
    tier_sent: Option<(Vec<u32>, Instant)>,
    tier_check: Option<Instant>,
    /// 名单里的名字（Steam ID → 名字）
    names: std::collections::BTreeMap<u64, String>,
    /// 斗技场消息因为档案不一致没收的队员（每人只记一行）
    arena_warned: std::collections::BTreeSet<u64>,
    /// 通道关掉（不在会话里 / 有人在加入中）时留下的 Link::unanswered，下次建通道接着算（HELLO_BUDGET 不因为会话重新就绪就清零）
    hello_spent: BTreeMap<u64, u32>,
}

static ST: Mutex<St> = Mutex::new(St { link: None, roster_at: None, me: 0, code_saved: None, foe_logged: 0, tier_sent: None, tier_check: None,
                                       names: std::collections::BTreeMap::new(), arena_warned: std::collections::BTreeSet::new(),
                                       hello_spent: BTreeMap::new() });
/// 房主的难度档没变时多久重发一次
const TIER_EVERY: Duration = Duration::from_secs(5);
/// 发件箱：别的模块排进来（不碰 ST，免得互相锁住），tick 里发
static OUT: Mutex<Vec<(To, Packet)>> = Mutex::new(Vec::new());
#[derive(Clone, Copy)]
enum To {
    All,
    Host,
    Peer(u64),
}
/// 能送装备的队员（连上了、档案一致；按 Steam ID 排序）：(Steam ID, 名字)，tick 里更新（gear/gift.rs、dark_lock 的菜单用）
static GIFT_PEERS: Mutex<Vec<(u64, String)>> = Mutex::new(Vec::new());

pub fn gift_peers() -> Vec<(u64, String)> {
    GIFT_PEERS.lock().unwrap_or_else(|e| e.into_inner()).clone()
}

/// 排进发件箱；满了（OUT_MAX）丢最早的一条
fn push_out(to: To, pk: Packet) {
    let mut o = OUT.lock().unwrap_or_else(|e| e.into_inner());
    if o.len() >= OUT_MAX {
        let (_, old) = o.remove(0);
        log_drop(&old.kind, "发件箱满了，丢掉最早的一条");
    }
    o.push((to, pk));
}

/// 通道用不了（没加载 Seamless、Steam 消息接口用不了）时清掉发件箱，不让它一直攒
fn clear_out() {
    let mut o = OUT.lock().unwrap_or_else(|e| e.into_inner());
    if let Some((_, pk)) = o.first() {
        log_drop(&pk.kind, &format!("联机通道用不了，发件箱里 {} 条清掉", o.len()));
        o.clear();
    }
}

/// 发给某一个队员（连上了才发）
pub fn send_to(peer: u64, pk: Packet) {
    push_out(To::Peer(peer), pk);
}
/// 最近转给房主的（实体, 操作, 值）：同样的 2 秒内不重复发（疫病每 0.5 秒扫一遍）
static RECENT: Mutex<Vec<(u32, &'static str, i32, Instant)>> = Mutex::new(Vec::new());
const FOE_LOG: u32 = 30;
/// 客机「转给房主」、发件箱发不出去 的日志最多写几行（这次进游戏）
const SEND_LOG: u32 = 30;
const DROP_LOG: u32 = 20;
static SEND_LOGGED: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
static ZERO_LOGGED: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
static DROP_LOGGED: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
/// 不在会话里收到、丢掉的消息（日志最多 10 行）
static IDLE_DROP_LOGGED: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);

/// 有上限的日志：counter 记写了几行，到 cap 时说明后面不再记
fn log_capped(counter: &std::sync::atomic::AtomicU32, cap: u32, msg: impl FnOnce() -> String) {
    let n = counter.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    if n < cap {
        log(&format!("{}{}", msg(), if n + 1 == cap { "；后面同类不再记" } else { "" }));
    }
}

/// 发给所有连上的队员（房主魇化广播等）
pub fn send_all(pk: Packet) {
    push_out(To::All, pk);
}

/// 客机：这个敌人要改，转给房主（联机计划 13.5：直接写敌人内存的只让房主写）。实体编号 0（临时生成的）不转
pub fn foe_to_host(entity: u32, op: &'static str, v: f32) {
    if entity == 0 {
        log_capped(&ZERO_LOGGED, 5, || format!("联机通道：要改的敌人是临时生成的（没有实体编号），{op} 没法转给房主"));
        return;
    }
    let now = Instant::now();
    let key = (v * 1000.0).round() as i32;
    {
        let mut r = RECENT.lock().unwrap_or_else(|e| e.into_inner());
        r.retain(|x| now.duration_since(x.3) < Duration::from_secs(2));
        if r.iter().any(|x| x.0 == entity && x.1 == op && x.2 == key) {
            return;
        }
        r.push((entity, op, key, now));
    }
    push_out(To::Host, Packet::new(Kind::Foe).with("e", entity).with("op", op).with("v", v));
    log_capped(&SEND_LOGGED, SEND_LOG, || format!("联机通道：转给房主：实体 {entity} {op} = {v}"));
}

/// 客机戴着时隙：上次报给房主的（时间, 倍数, 敌人）
static SLIP_SENT: Mutex<Option<(Instant, f32, Vec<u32>)>> = Mutex::new(None);
const SLIP_EVERY: Duration = Duration::from_millis(500);

/// 客机：时隙范围里的敌人报给房主（runtime.rs 每帧调；敌人变了或者过了 SLIP_EVERY 才发；m = 1 = 摘下了，只发一次）
pub fn slip_to_host(entities: &[u32], m: f32) {
    let now = Instant::now();
    let mut ids: Vec<u32> = entities.to_vec();
    ids.sort_unstable();
    ids.dedup();
    ids.truncate(64);
    let mut g = SLIP_SENT.lock().unwrap_or_else(|e| e.into_inner());
    let off = (m - 1.0).abs() < 1e-6;
    let same = g.as_ref().is_some_and(|x| (x.1 - m).abs() < 1e-6 && x.2 == ids);
    if off {
        if g.take().is_some() {
            push_out(To::Host, Packet::new(Kind::Slip).with("m", 1).with("e", ""));
            log_capped(&SEND_LOGGED, SEND_LOG, || "联机通道：转给房主：时隙摘下了".to_string());
        }
        return;
    }
    if same && g.as_ref().is_some_and(|x| now.duration_since(x.0) < SLIP_EVERY) {
        return;
    }
    if !same {
        log_capped(&SEND_LOGGED, SEND_LOG, || format!("联机通道：转给房主：时隙 ×{m:.2}，范围里 {} 个敌人", ids.len()));
    }
    let list: Vec<String> = ids.iter().map(|e| e.to_string()).collect();
    push_out(To::Host, Packet::new(Kind::Slip).with("m", m).with("e", list.join(",")));
    *g = Some((now, m, ids));
}

/// 发件箱里发不出去的（没连上 / 没有连上的房主 / 没有连上的队员）
fn log_drop(kind: &Kind, why: &str) {
    log_capped(&DROP_LOGGED, DROP_LOG, || format!("联机通道：{} 消息没发出去（{why}）", kind.name()));
}

/// 房主：替客机改敌人。只认这几种、值在范围内的
fn apply_foe(pk: &Packet) -> Option<String> {
    let e = pk.get("e")?.parse::<u32>().ok()?;
    let op = pk.get("op")?;
    let v = pk.get("v")?.parse::<f32>().ok()?;
    let cp = crate::chrs::find_entity(e)?;
    let c = unsafe { &mut *cp.as_ptr() };
    match op {
        "poise" if v >= 0.0 => c.modules.super_armor.sa_durability = v.min(c.modules.super_armor.sa_durability_max),
        "rmsp" if (90000.0..90400.0).contains(&v) => c.remove_speffect(v as i32),
        _ => return None,
    }
    Some(format!("NPC {}（实体 {e}）{op} {v}", c.npc_param_id))
}
/// 自测发出去的时间（收到了就清掉）
static SELFTEST: Mutex<Option<Instant>> = Mutex::new(None);

fn load_profile() -> Vec<(String, String)> {
    fs::read_to_string(dir().join("coop_profile.txt")).map(|t| parse_profile(&t)).unwrap_or_default()
}

/// 上次看 coopnet_req.txt 的时间：每帧开一次文件（文件不在也要走一趟文件系统）单机时整个通道每帧 0.17 毫秒
/// （2026-11-19 性能记录「联机通道 0.17」），改成半秒看一次，开发工具的请求晚半秒没关系
static REQ_AT: Mutex<Option<Instant>> = Mutex::new(None);
const REQ_EVERY: Duration = Duration::from_millis(500);

fn take_req() -> Vec<String> {
    {
        let now = Instant::now();
        let mut at = REQ_AT.lock().unwrap_or_else(|e| e.into_inner());
        if at.is_some_and(|t| now.duration_since(t) < REQ_EVERY) {
            return Vec::new();
        }
        *at = Some(now);
    }
    let p = dir().join("coopnet_req.txt");
    let Ok(t) = fs::read_to_string(&p) else { return Vec::new() };
    let _ = fs::remove_file(&p);
    t.lines().map(|l| l.trim_start_matches('\u{feff}').trim().to_string()).filter(|l| !l.is_empty()).collect()
}

fn seed() -> u64 {
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos() as u64).unwrap_or(0);
    t ^ (std::process::id() as u64) << 32
}

pub fn tick() {
    let reqs = take_req();
    let selftest_on = SELFTEST.lock().unwrap_or_else(|e| e.into_inner()).is_some();
    // 没加载 Seamless 时只管开发工具的请求和自测，不碰 Steam
    if !crate::coop::ersc_loaded() && reqs.is_empty() && !selftest_on {
        clear_out();
        return;
    }
    let Some(steam) = crate::net::steam() else {
        if !reqs.is_empty() {
            log("联机通道：Steam 消息接口用不了，请求没有处理");
        }
        clear_out();
        return;
    };
    let mut t = SteamT(steam);
    let now = Instant::now();
    let mut g = ST.lock().unwrap_or_else(|e| e.into_inner());
    // 名单（半秒看一次）：会话就绪才有；本机 Steam ID 以名单为准
    if g.roster_at.is_none_or(|r| now.duration_since(r) >= ROSTER_EVERY) {
        g.roster_at = Some(now);
        match crate::coop::roster() {
            Some(r) => {
                let me = r.iter().find(|m| m.local).map(|m| m.id).unwrap_or(steam.me);
                if g.link.as_ref().is_none_or(|l| l.me != me) {
                    let prof = load_profile();
                    log(&format!("联机通道：会话就绪，{} 个队员；兼容档案 {} 项{}", r.len().saturating_sub(1), prof.len(),
                                 if prof.is_empty() { "（没有 coop_profile.txt：不是用启动器的联机启动？档案不比）" } else { "" }));
                    let mut l = Link::new(me, prof, seed());
                    // 握手次数接着上一条通道算（会话重新就绪不清零）
                    l.unanswered = match g.link.take() {
                        Some(old) => old.unanswered,
                        None => std::mem::take(&mut g.hello_spent),
                    };
                    g.link = Some(l);
                }
                g.me = me;
                let others: Vec<(u64, bool)> = r.iter().filter(|m| !m.local).map(|m| (m.id, m.host)).collect();
                g.names = r.iter().map(|m| (m.id, m.name.clone())).collect();
                if let Some(l) = g.link.as_mut() {
                    l.set_roster(&others, &mut t);
                }
            }
            None => {
                if let Some(l) = g.link.as_mut() {
                    if !l.peers.is_empty() {
                        l.set_roster(&[], &mut t);
                        log("联机通道：不在会话里了，通道关掉");
                    }
                }
                if let Some(l) = g.link.take() {
                    g.hello_spent = l.unanswered;
                }
            }
        }
    }
    if let Some(l) = g.link.as_mut() {
        l.poll(&mut t, now);
    } else {
        // 不在会话里（或会话还没就绪）：本频道的消息照样每帧收掉、直接丢，不让 Steam 一直攒着（和 Seamless 共用一条连接）；
        // 只有自测发给自己的拿来处理
        let me = steam.me;
        let mut dropped = 0usize;
        for (from, data) in t.recv() {
            if selftest_on && me != 0 && from == me {
                let mut l = Link::new(me, Vec::new(), 1);
                l.handle(from, &data, &mut t, now);
            } else {
                dropped += 1;
            }
        }
        if dropped > 0 {
            log_capped(&IDLE_DROP_LOGGED, 10, || format!("联机通道：不在会话里（或会话还没就绪），收到 {dropped} 条消息，丢掉"));
        }
    }
    // 房主的难度档（联机计划 13.9 A）：每秒看一次，变了马上发、没变每 TIER_EVERY 发一次
    if crate::coop::host() && g.link.as_ref().is_some_and(|l| l.peers.values().any(|p| p.linked())) && g.tier_check.is_none_or(|t| now >= t) {
        g.tier_check = Some(now + Duration::from_secs(1));
        let v = crate::coop::my_tier_flags();
        if g.tier_sent.as_ref().is_none_or(|x| x.0 != v || now.duration_since(x.1) >= TIER_EVERY) {
            let list: Vec<String> = v.iter().map(|f| f.to_string()).collect();
            send_all(Packet::new(Kind::Tier).with("f", list.join(",")));
            g.tier_sent = Some((v, now));
        }
    }
    // 发件箱
    let out: Vec<(To, Packet)> = std::mem::take(&mut *OUT.lock().unwrap_or_else(|e| e.into_inner()));
    if let Some(l) = g.link.as_mut() {
        for (to, pk) in out {
            match to {
                To::Host => {
                    if !l.send_host(&pk, &mut t) {
                        log_drop(&pk.kind, "还没和房主连上");
                    }
                }
                To::All => {
                    if l.broadcast(&pk, &mut t) == 0 {
                        log_drop(&pk.kind, "还没和任何队员连上");
                    }
                }
                To::Peer(id) => {
                    if l.peers.get(&id).is_some_and(|p| p.linked()) {
                        t.send(id, &pk.encode());
                    } else {
                        log_drop(&pk.kind, &format!("和队员 {} 没连上", short(id)));
                    }
                }
            }
        }
    } else {
        for (_, pk) in out {
            log_drop(&pk.kind, "联机通道还没建好（不在会话里，或会话还没就绪）");
        }
    }
    // 能送装备的队员（名字从名单来；没名字写 Steam ID 后 4 位）
    {
        let mut v: Vec<(u64, String)> = g.link.as_ref().map_or_else(Vec::new, |l| {
            l.peers.values().filter(|p| p.linked() && p.profile_diff.is_empty()).map(|p| {
                let n = g.names.get(&p.id).filter(|n| !n.is_empty()).cloned().unwrap_or_else(|| format!("队友 {}", short(p.id)));
                (p.id, n.chars().take(16).collect())
            }).collect()
        });
        v.sort_by_key(|x| x.0);
        *GIFT_PEERS.lock().unwrap_or_else(|e| e.into_inner()) = v;
    }
    // 收件箱：客机转来的改敌人（本机是房主才做）、房主的魇化（本机是客机才收）
    let inbox: Vec<(u64, Packet)> = g.link.as_mut().map(|l| std::mem::take(&mut l.inbox)).unwrap_or_default();
    for (from, pk) in inbox {
        match pk.kind {
            Kind::Foe if crate::coop::host() && pk.get("op") == Some("speed") => {
                let e = pk.get("e").and_then(|x| x.parse::<u32>().ok()).unwrap_or(0);
                if let Some(v) = pk.get("v").and_then(|x| x.parse::<f32>().ok()) {
                    crate::speed::remote(e, crate::speed::Src::Slow, from, v);
                    if g.foe_logged < FOE_LOG {
                        g.foe_logged += 1;
                        log(&format!("联机通道：替客机 {} 改实体 {e} 的动作速度 ×{v}（{}）", short(from), if v == 1.0 { "改回" } else { "减速" }));
                    }
                }
            }
            Kind::Tier if g.link.as_ref().is_some_and(|l| l.from_host(from)) => {
                let f: Vec<u32> = pk.get("f").unwrap_or("").split(',').filter_map(|x| x.parse().ok()).collect();
                crate::coop::set_host_tier(f);
            }
            Kind::Slip if crate::coop::host() => {
                let m = pk.get("m").and_then(|x| x.parse::<f32>().ok()).unwrap_or(1.0);
                crate::speed::remote_clear(crate::speed::Src::Slip, from);
                if (m - 1.0).abs() > 1e-6 {
                    for e in pk.get("e").unwrap_or("").split(',').filter_map(|x| x.parse::<u32>().ok()) {
                        crate::speed::remote(e, crate::speed::Src::Slip, from, m);
                    }
                }
            }
            Kind::Foe if crate::coop::host() => {
                if let Some(s) = apply_foe(&pk) {
                    if g.foe_logged < FOE_LOG {
                        g.foe_logged += 1;
                        log(&format!("联机通道：替客机 {} 改了 {s}", short(from)));
                    }
                }
            }
            // 赠送：档案一致的才收（两边词条库一样，配方才对得上）
            Kind::Gift => {
                if g.link.as_ref().is_some_and(|l| l.compatible(from)) {
                    crate::gear::gift_in(from, pk);
                } else if let Some(n) = pk.get("n") {
                    let no = Packet::new(Kind::GiftNo).with("n", n).with("why", "两边的游戏数据不一样");
                    t.send(from, &no.encode());
                }
            }
            Kind::GiftOk | Kind::GiftNo => {
                if let Some(n) = pk.get("n").and_then(|x| x.parse::<u64>().ok()) {
                    crate::gear::gift_result(from, n, pk.kind == Kind::GiftOk, pk.get("why").unwrap_or("").to_string());
                }
            }
            // 送的人要退回（gift.rs 的 gift_in 按种类分开排队）
            Kind::GiftBack => {
                if g.link.as_ref().is_some_and(|l| l.compatible(from)) {
                    crate::gear::gift_in(from, pk);
                }
            }
            // 斗技场试炼：档案一致的才收（两边的 arena.txt 一样，出场的部件才对得上）；房主发来的进度、队员报的情况都交给 arena.rs
            Kind::Arena => {
                let (host, ok) = g.link.as_ref().map_or((false, false), |l| (l.from_host(from), l.compatible(from)));
                if ok {
                    crate::arena::net_in(from, host, pk);
                } else if g.arena_warned.insert(from) {
                    log(&format!("联机通道：队员 {} 的游戏数据和本机对不上，斗技场试炼的消息不收", short(from)));
                }
            }
            Kind::Nm if g.link.as_ref().is_some_and(|l| l.from_host(from)) => {
                let e = pk.get("e").and_then(|x| x.parse::<u32>().ok()).unwrap_or(0);
                let f: Vec<usize> = pk.get("f").unwrap_or("").split(',').filter_map(|x| x.parse().ok()).collect();
                if e != 0 && !f.is_empty() {
                    crate::nightmare::remote_elite(e, f);
                }
            }
            _ => {}
        }
    }
    // 房主的联机随机码：档案对不上时存给启动器（「联机」→「导入随机码」剪贴板里没有码时用它）
    let host_code = g.link.as_ref().and_then(|l| l.peers.values().find(|p| p.host && p.linked() && !p.profile_diff.is_empty()).and_then(|p| p.code.clone()));
    if let Some(code) = host_code.filter(|c| g.code_saved.as_ref() != Some(c)) {
        let path = dir().join("coop_host_code.txt");
        if fs::write(&path, format!("{code}\n")).is_ok() {
            log("联机通道：和房主的游戏数据对不上，房主的联机随机码存下了（退出游戏后在启动器「联机」→「导入随机码」导入）");
        }
        g.code_saved = Some(code);
    }
    let mut st = SELFTEST.lock().unwrap_or_else(|e| e.into_inner());
    if st.is_some_and(|at| now.duration_since(at) >= SELFTEST_WAIT) {
        *st = None;
        log(&format!("联机通道：自测 {} 秒内没收到发给自己的消息（Steam 可能不回送给自己；要两台电脑实测）", SELFTEST_WAIT.as_secs()));
    }
    drop(st);
    for r in reqs {
        let (cmd, arg) = r.split_once(' ').map_or((r.as_str(), ""), |(a, b)| (a, b.trim()));
        match cmd {
            "状态" | "status" => log(&format!("联机通道（状态）：Seamless {}；{}", if crate::coop::ersc_loaded() { "已加载" } else { "没加载" },
                                              g.link.as_ref().map_or("不在会话里".to_string(), |l| l.status()))),
            "自测" | "selftest" => {
                let me = if g.me != 0 { g.me } else { steam.me };
                if me == 0 {
                    log("联机通道：自测做不了，读不到本机的 Steam ID");
                    continue;
                }
                let pk = Packet::new(Kind::Text).with("text", "自测");
                let rc = t.0.send(me, &pk.encode());
                *SELFTEST.lock().unwrap_or_else(|e| e.into_inner()) = Some(now);
                log(&format!("联机通道：自测，发给自己（Steam 结果码 {rc}，1 = 发出去了），等 {} 秒看收不收得到", SELFTEST_WAIT.as_secs()));
            }
            "测试" | "test" => {
                let text = if arg.is_empty() { "你好" } else { arg };
                let n = g.link.as_mut().map_or(0, |l| l.broadcast(&Packet::new(Kind::Text).with("text", text), &mut t));
                log(&format!("联机通道：测试消息「{text}」发给了 {n} 个连上的队员"));
            }
            _ => log(&format!("联机通道：请求「{r}」不认识")),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;
    use std::rc::Rc;

    /// 内存里的网络：每个人一个收件箱
    #[derive(Default)]
    struct Net {
        boxes: HashMap<u64, Vec<(u64, Vec<u8>)>>,
        drop_from: Option<u64>,
    }

    struct Fake {
        me: u64,
        net: Rc<RefCell<Net>>,
    }

    impl Transport for Fake {
        fn send(&mut self, to: u64, data: &[u8]) -> bool {
            let mut n = self.net.borrow_mut();
            if n.drop_from == Some(self.me) {
                return true;
            }
            n.boxes.entry(to).or_default().push((self.me, data.to_vec()));
            true
        }
        fn recv(&mut self) -> Vec<(u64, Vec<u8>)> {
            std::mem::take(self.net.borrow_mut().boxes.entry(self.me).or_default())
        }
        fn accept(&mut self, _: u64) {}
        fn close(&mut self, _: u64) {}
    }

    fn prof(v: &str) -> Vec<(String, String)> {
        parse_profile(&format!("version 0.10.10\nfingerprint {v}\n"))
    }

    fn pair(pa: Vec<(String, String)>, pb: Vec<(String, String)>) -> (Link, Fake, Link, Fake, Rc<RefCell<Net>>) {
        let net = Rc::new(RefCell::new(Net::default()));
        let (mut a, mut ta) = (Link::new(1, pa, 11), Fake { me: 1, net: net.clone() });
        let (mut b, mut tb) = (Link::new(2, pb, 22), Fake { me: 2, net: net.clone() });
        a.set_roster(&[(2, false)], &mut ta);
        b.set_roster(&[(1, true)], &mut tb);
        (a, ta, b, tb, net)
    }

    fn run(a: &mut Link, ta: &mut Fake, b: &mut Link, tb: &mut Fake, t0: Instant, secs: f32) -> Instant {
        let mut now = t0;
        let end = t0 + Duration::from_secs_f32(secs);
        while now < end {
            a.poll(ta, now);
            b.poll(tb, now);
            now += Duration::from_millis(100);
        }
        now
    }

    #[test]
    fn packet_roundtrip_and_reject() {
        let p = Packet::new(Kind::Hello).with("nonce", 42).with("p.version", "0.10.10\nx");
        let q = Packet::decode(&p.encode()).unwrap();
        assert_eq!(q.kind, Kind::Hello);
        assert_eq!(q.get("nonce"), Some("42"));
        assert_eq!(q.get("p.version"), Some("0.10.10 x"), "值里的换行换成空格");
        assert!(Packet::decode(b"DFL 999 HELLO\n").unwrap_err().contains("协议版本不同"));
        assert!(Packet::decode(b"XYZ 1 HELLO\n").is_err());
        assert!(Packet::decode(&[0xff, 0xfe]).is_err());
    }

    #[test]
    fn handshake_links_both_sides() {
        let (mut a, mut ta, mut b, mut tb, _) = pair(prof("aaa"), prof("aaa"));
        run(&mut a, &mut ta, &mut b, &mut tb, Instant::now(), 3.0);
        assert!(a.peers[&2].linked() && b.peers[&1].linked());
        assert!(a.compatible(2) && b.compatible(1));
        assert!(a.status().contains("已连上"));
    }

    #[test]
    fn profile_mismatch_is_reported() {
        let (mut a, mut ta, mut b, mut tb, _) = pair(prof("aaa"), prof("bbb"));
        run(&mut a, &mut ta, &mut b, &mut tb, Instant::now(), 3.0);
        assert!(a.peers[&2].linked(), "档案不一致也连上（好排查）");
        assert!(!a.compatible(2));
        assert_eq!(a.peers[&2].profile_diff, vec![("联机核对码".to_string(), "aaa".to_string(), "bbb".to_string())]);
    }

    #[test]
    fn ping_measures_rtt_and_loss_resets() {
        let (mut a, mut ta, mut b, mut tb, net) = pair(prof("aaa"), prof("aaa"));
        let t0 = Instant::now();
        let now = run(&mut a, &mut ta, &mut b, &mut tb, t0, 12.0);
        assert!(a.peers[&2].rtt_ms.is_some(), "连上后发 PING、收到 PONG");
        // b 不再发东西：a 过 LOST 秒后当作断了，从握手重来
        net.borrow_mut().drop_from = Some(2);
        let later = run(&mut a, &mut ta, &mut b, &mut tb, now, 25.0);
        assert!(!a.peers[&2].linked());
        // 恢复后两边都重新连上（b 看到 a 换了随机数，自己也重新握手）
        net.borrow_mut().drop_from = None;
        run(&mut a, &mut ta, &mut b, &mut tb, later, 3.0);
        assert!(a.peers[&2].linked() && b.peers[&1].linked());
        assert!(a.peers[&2].rtt_ms.is_none() || a.peers[&2].linked());
    }

    #[test]
    fn strangers_and_roster_changes() {
        let (mut a, mut ta, _b, _tb, net) = pair(prof("aaa"), prof("aaa"));
        net.borrow_mut().boxes.entry(1).or_default().push((99, Packet::new(Kind::Text).with("text", "x").encode()));
        a.poll(&mut ta, Instant::now());
        assert!(!a.peers.contains_key(&99), "不在名单里的不收");
        a.set_roster(&[], &mut ta);
        assert!(a.peers.is_empty(), "走了的删掉");
        a.set_roster(&[(1, false), (0, false)], &mut ta);
        assert!(a.peers.is_empty(), "本机、0 不算队员");
    }

    #[test]
    fn broadcast_only_to_linked() {
        let (mut a, mut ta, mut b, mut tb, _) = pair(prof("aaa"), prof("aaa"));
        assert_eq!(a.broadcast(&Packet::new(Kind::Text).with("text", "hi"), &mut ta), 0, "还没连上不发");
        run(&mut a, &mut ta, &mut b, &mut tb, Instant::now(), 3.0);
        assert_eq!(a.broadcast(&Packet::new(Kind::Text).with("text", "hi"), &mut ta), 1);
    }

    #[test]
    fn foe_goes_to_inbox_and_host_only() {
        let (mut a, mut ta, mut b, mut tb, _) = pair(prof("aaa"), prof("aaa"));
        run(&mut a, &mut ta, &mut b, &mut tb, Instant::now(), 3.0);
        // b 看 a 是房主：b 发给房主
        assert!(b.send_host(&Packet::new(Kind::Foe).with("e", 1001).with("op", "speed").with("v", 0.5), &mut tb));
        // a 看 b 是客机：a 发给房主发不出去
        assert!(!a.send_host(&Packet::new(Kind::Foe).with("e", 1), &mut ta));
        a.poll(&mut ta, Instant::now() + Duration::from_secs(4));
        assert_eq!(a.inbox.len(), 1);
        assert_eq!(a.inbox[0].1.get("e"), Some("1001"));
        assert!(b.from_host(1) && !a.from_host(2));
    }

    #[test]
    fn code_is_not_a_profile_item() {
        let mut pa = prof("aaa");
        pa.push(("code".into(), "DR2|1".into()));
        let mut pb = prof("aaa");
        pb.push(("code".into(), "DR2|2".into()));
        let (mut a, mut ta, mut b, mut tb, _) = pair(pa, pb);
        run(&mut a, &mut ta, &mut b, &mut tb, Instant::now(), 3.0);
        assert!(a.compatible(2), "随机码不同不算档案不一致：{:?}", a.peers[&2].profile_diff);
        assert_eq!(b.peers[&1].code.as_deref(), Some("DR2|1"));
    }

    /// 对方一直不读本频道：HELLO 先每秒一条、再每 5 秒一条，3 分钟后停；名单变了重新开始；对方来了消息马上重发；总数不超过 HELLO_BUDGET
    #[test]
    fn hello_backs_off_and_stops() {
        let (mut a, mut ta, _b, _tb, net) = pair(prof("aaa"), prof("aaa"));
        let to_b = |net: &Rc<RefCell<Net>>| net.borrow().boxes.get(&2).map_or(0, |v| v.len());
        let t0 = Instant::now();
        let mut now = t0;
        let mut at_30 = 0;
        while now < t0 + Duration::from_secs(400) {
            a.poll(&mut ta, now);
            if now < t0 + HELLO_FAST_FOR {
                at_30 = to_b(&net);
            }
            now += Duration::from_millis(100);
        }
        let n = to_b(&net);
        assert!((29..=31).contains(&at_30), "头 30 秒每秒一条：{at_30}");
        assert!(n > at_30 && n <= at_30 + 31, "之后每 5 秒一条、3 分钟停：{n}");
        assert!(a.peers[&2].gave_up);
        a.poll(&mut ta, now + Duration::from_secs(60));
        assert_eq!(to_b(&net), n, "停了就不再发");
        // 名单变了（来了个队员 3）：和 2 也重新开始
        a.set_roster(&[(2, false), (3, false)], &mut ta);
        a.poll(&mut ta, now);
        assert_eq!(to_b(&net), n + 1);
        // 一直没回音，名单来回变：HELLO 总数不超过 HELLO_BUDGET
        for k in 0..10 {
            a.set_roster(if k % 2 == 0 { &[(2, false)][..] } else { &[(2, false), (3, false)][..] }, &mut ta);
            let end = now + Duration::from_secs(400);
            while now < end {
                a.poll(&mut ta, now);
                now += Duration::from_millis(500);
            }
        }
        let total = to_b(&net);
        assert!(total <= HELLO_BUDGET as usize, "{total}");
        assert!(a.peers[&2].gave_up);
        // 对方来了消息（晚起来了）：马上回 ACK、重发 HELLO
        net.borrow_mut().boxes.entry(1).or_default().push((2, Packet::new(Kind::Hello).with("nonce", 7).encode()));
        a.poll(&mut ta, now);
        assert!(!a.peers[&2].gave_up);
        let last: Vec<Kind> = net.borrow().boxes[&2][total..].iter().map(|(_, d)| Packet::decode(d).unwrap().kind).collect();
        assert_eq!(last, vec![Kind::Ack, Kind::Hello]);
    }

    #[test]
    fn profile_parse_and_diff_labels() {
        let p = parse_profile("\u{feff}# 注释\nversion\t0.10.10\nworld _coop\n\nscaling enemy_health_scaling=35,boss=100\n");
        assert_eq!(p.len(), 3);
        assert_eq!(p[2], ("scaling".to_string(), "enemy_health_scaling=35,boss=100".to_string()));
        let d = profile_diff(&p, &parse_profile("version 0.10.9\nworld _coop\n"));
        assert_eq!(d[0].0, "Seamless 随人数加强");
        assert_eq!(d[0].2, "（没有）");
        assert_eq!(d[1], ("整合包版本".to_string(), "0.10.10".to_string(), "0.10.9".to_string()));
    }
}
