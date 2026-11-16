//! 开发工具：按 dll\dark_core\devgive.txt 直接拿指定的装备（测试用；打包不带这个文件，没有这个文件就什么都不做）。
//! 进游戏后每保存一次这个文件就发一次（看修改时间；DLL 第一次看到时已经在的那份不发，要再保存一下）。
//! 游戏里的悬浮窗口（dll\dark_dev，F9）写 devgive_req.txt：格式一样，有就发、发完删掉。
//! 生成后和鉴定一样走发货表放进背包、记进角色记录。结果写日志（dark_core.log，开头「开发工具」）。
//! 一行一件：<类> [参数=值 …]，类：武器 / w、防具 / p、护符 / a；# 开头是注释；没写的参数照常随机。
//!   通用：档=0~4（4 = 传说（幽影之地），默认 3）、件数=N（默认 1）
//!   武器：本体=编号或名字片段、类型=武器类型编号、项数=1/2/3/5、补正=力气:120,灵巧:80（写了就只有这几项）、
//!         异常=出血,冻伤:80（冒号后是强度，不写按这个稀有度随机；写「无」就不带）、战技=编号或名字片段、
//!         常驻=效果编号或名字片段（法杖 / 圣印记的流派加成、盾牌抗性，最多 2 个；写「无」就不带）、
//!         特效=键或短名（武器的特殊效果词条位，比如 血狂；写「无」就不带）、强攻=基础攻击力 +%（比如 20；写「无」就不带）、
//!         属性=物理 / 魔力 / 火 / 雷 / 圣（物理＋这种元素，冒号后是元素占比 %，不写按区间随机）/ 纯魔力 / 纯火 / 纯雷 / 纯圣 / 原版
//!         （补正变了需求按鉴定的规则重抽：排序同补正、史诗 / 传说最低等级）
//!   防具：本体=编号或名字片段、部位=头/身/手/腿、词条=键或后缀名,…（最多 3 个，写了就只有这些）
//!   护符：词条=键或后缀名
//! 另外「道具 <编号> [个数]」直接发道具（dll\dark_dev「高难度测试」区发超限锻造石用的；测试都用 F9 窗口，不再手写 devgive.txt）。

use std::collections::HashMap;
use std::fs;
use std::time::UNIX_EPOCH;

use super::*;

const FILE: &str = "devgive.txt";
/// 悬浮窗口（dll\dark_dev）写的请求：格式同 devgive.txt，有就发、发完删掉
const REQ_FILE: &str = "devgive_req.txt";
const STATUS_NAMES: [[&str; 3]; STATUS_N] = [
    ["出血", "bleed", "blood"],
    ["中毒", "poison", "poison"],
    ["腐败", "rot", "scarlet"],
    ["冻伤", "frost", "frostbite"],
    ["睡眠", "sleep", "sleep"],
    ["咒死", "death", "blight"],
    ["发狂", "madness", "madness"],
];
const STAT_NAMES: [[&str; 3]; 5] =
    [["力气", "str", "strength"], ["灵巧", "dex", "dexterity"], ["智力", "int", "intelligence"], ["信仰", "fai", "faith"], ["感应", "arc", "arcane"]];
const SLOT_NAMES: [[&str; 3]; 4] = [["头", "head", "helm"], ["身", "body", "chest"], ["手", "arm", "gauntlet"], ["腿", "leg", "legs"]];

fn name_idx<const N: usize>(names: &[[&str; 3]; N], v: &str) -> Option<usize> {
    let v = v.trim().to_lowercase();
    names.iter().position(|n| n.iter().any(|x| *x == v) || (!v.is_empty() && n[0].starts_with(&v)))
}

/// 编号或名字片段（中文 / 英文，不分大小写）
fn find<'a, T>(list: &'a [T], v: &str, id: impl Fn(&T) -> u32, name: impl Fn(&T) -> &[String; 2], what: &str) -> Result<&'a T, String> {
    if let Ok(n) = v.parse::<u32>() {
        return list.iter().find(|x| id(x) == n).ok_or_else(|| format!("没有编号 {n} 的{what}本体"));
    }
    let low = v.to_lowercase();
    list.iter()
        .find(|x| name(x).iter().any(|s| *s == v))
        .or_else(|| list.iter().find(|x| name(x).iter().any(|s| s.to_lowercase().contains(&low))))
        .ok_or_else(|| format!("找不到名字里有「{v}」的{what}本体"))
}

fn find_fam(lib: &Lib, v: &str) -> Result<usize, String> {
    let v = v.trim();
    lib.fam_by_key
        .get(v)
        .copied()
        .or_else(|| lib.fams.iter().position(|f| f.suffix.iter().any(|s| s == v)))
        .or_else(|| lib.fams.iter().position(|f| f.suffix.iter().any(|s| s.to_lowercase().contains(&v.to_lowercase()))))
        .ok_or_else(|| format!("没有词条「{v}」（写词条的键或后缀名，见 affixes.txt 的 fam 行）"))
}

fn opt<'a>(o: &'a HashMap<String, String>, keys: &[&str]) -> Option<&'a str> {
    keys.iter().find_map(|k| o.get(*k)).map(|s| s.as_str())
}

/// 这种异常这个稀有度的效果：强度写了就找最接近的，没写按分布抽
fn status_sp(lib: &Lib, k: usize, r: usize, power: Option<u32>, rng: &mut Rng) -> Option<i32> {
    let p = power.or_else(|| lib.wstat_pow.get(&(k, r)).and_then(|d| d.pick(rng)).map(|x| x as u32))?;
    let table = &lib.wstat_sp[k];
    table.get(&p).copied().or_else(|| table.iter().min_by_key(|(q, _)| q.abs_diff(p)).map(|(_, s)| *s))
}

fn weapon(lib: &Lib, tier: usize, o: &HashMap<String, String>, rng: &mut Rng) -> Result<Recipe, String> {
    let r = tier.min(3);
    let base = match (opt(o, &["本体", "base"]), opt(o, &["类型", "type"])) {
        (Some(v), _) => Some(find(&lib.wbase, v, |b| b.id, |b| &b.name, "武器")?.clone()),
        (None, Some(t)) => {
            let t: u16 = t.parse().map_err(|_| format!("类型要写数字：{t}"))?;
            let list: Vec<&WBase> = lib.wbase.iter().filter(|b| b.typ == t).collect();
            Some((*list.get(rng.below(list.len().max(1) as u64) as usize).ok_or_else(|| format!("没有类型 {t} 的武器本体"))?).clone())
        }
        _ => None,
    };
    let fix = base.as_ref().map(|b| WFix { base: b.id, maxreq: [99; 5], top: 1.0, min_status: 0, keep: false, main: -1, full: false });
    let mut rec = gen_weapon_on(lib, tier, fix, rng).ok_or("武器生成失败（词条库里没有能用的本体）")?;
    let Recipe::W { base: bid, var, skill, cor, req, st, res, glow, spec, atk, elem, share, .. } = &mut rec else { unreachable!() };
    // 强攻：基础攻击力 +%（0 / 无 = 不带）
    if let Some(v) = opt(o, &["强攻", "atk"]) {
        *atk = match v.trim() {
            "无" | "none" => 0,
            x => x.trim_end_matches(['%', '％']).parse().map_err(|_| format!("强攻要写百分比数字：{x}"))?,
        };
    }
    // 特殊效果词条位：键 / 短名 / 效果编号；写「无」就不带
    if let Some(v) = opt(o, &["特效", "spec"]) {
        let v = v.trim();
        *spec = match v {
            "无" | "none" | "0" => -1,
            _ => v
                .parse::<i32>()
                .ok()
                .or_else(|| lib.wspec.iter().find(|x| x.key == v || x.name.iter().any(|n| n.contains(v))).map(|x| x.sp))
                .ok_or_else(|| format!("没有特效「{v}」（见 affixes.txt 的 wspec 行）"))?,
        };
    }
    // 常驻效果（法杖 / 圣印记的流派加成、盾牌抗性、武器特殊效果如血狂）：效果编号或名字片段，最多 2 个；写「无」就不带
    if let Some(v) = opt(o, &["常驻", "res"]) {
        let mut out = [-1i32; 2];
        if !matches!(v.trim(), "无" | "none" | "0") {
            for (j, part) in v.split([',', '，']).map(str::trim).filter(|x| !x.is_empty()).take(2).enumerate() {
                out[j] = match part.parse::<i32>() {
                    Ok(n) => n,
                    Err(_) => lib
                        .res
                        .iter()
                        .flat_map(|x| x.1.pool.iter())
                        .find(|p| p.2.iter().any(|n| n.contains(part)))
                        .map(|p| p.0)
                        .ok_or_else(|| format!("没有常驻效果「{part}」（见 affixes.txt 的 wres 行）"))?,
                };
            }
        }
        *res = out;
    }
    let b = lib.wbase.iter().find(|x| x.id == *bid).cloned().ok_or("本体不在词条库里")?;
    // 属性：物理＋元素（:占比）/ 纯元素 / 纯物理 / 原版（照本体）；传说的光效跟着换
    if let Some(v) = opt(o, &["属性", "elem"]) {
        let (name, pct) = match v.split_once([':', '：']) {
            Some((n, p)) => (n.trim(), Some(p.trim().trim_end_matches(['%', '％']).parse::<u8>().map_err(|_| format!("元素占比要写数字：{p}"))?)),
            None => (v.trim(), None),
        };
        const EL: [&str; 4] = ["魔力", "火", "雷", "圣"];
        let w = &lib.welem;
        (*elem, *share) = match name {
            "原版" | "本体" | "keep" => (0, 0),
            "物理" | "纯物理" | "phys" => (1, 0),
            n => {
                let (pure, n) = match n.strip_prefix('纯') {
                    Some(x) => (true, x),
                    None => (false, n),
                };
                let k = EL.iter().position(|x| *x == n).ok_or_else(|| format!("没有属性「{v}」（物理 / 魔力 / 火 / 雷 / 圣 / 纯魔力 … / 原版）"))? as u8;
                if pure {
                    (6 + k, 100)
                } else {
                    (2 + k, pct.unwrap_or_else(|| w.lo + rng.below((w.hi - w.lo) as u64 + 1) as u8).clamp(1, 99))
                }
            }
        };
        *glow = elem_glow(lib, r, *elem, b.elem);
    }
    // 补正 / 项数
    let mut new_cor = None;
    if let Some(v) = opt(o, &["补正", "cor"]) {
        let mut c = [0f32; 5];
        for part in v.split([',', '，']).filter(|x| !x.trim().is_empty()) {
            let (k, val) = part.split_once([':', '：']).ok_or_else(|| format!("补正写成 力气:120 这样：{part}"))?;
            let k = name_idx(&STAT_NAMES, k).ok_or_else(|| format!("没有属性「{k}」"))?;
            c[k] = val.trim().parse().map_err(|_| format!("补正值不是数字：{val}"))?;
        }
        new_cor = Some(c);
    } else if let Some(n) = opt(o, &["项数", "n"]) {
        let n: usize = n.parse().map_err(|_| format!("项数要写数字：{n}"))?;
        let mut c = [0f32; 5];
        let vd = lib.wscal_v.get(&(r, n as u32)).or_else(|| lib.wscal_v.get(&(r, 2)));
        for k in choose(rng, 5, n.clamp(1, 5)) {
            c[k] = vd.and_then(|d| d.pick(rng)).unwrap_or(50.0) as f32;
        }
        new_cor = Some(c);
    }
    if let Some(c) = new_cor {
        *cor = c;
        let stats: Vec<usize> = (0..5).filter(|&k| c[k] > 0.0).collect();
        let mut q = [0u8; 5];
        for &k in &stats {
            q[k] = lib.wreq.get(&(r, k)).and_then(|d| d.pick(rng)).unwrap_or(0.0).clamp(0.0, 99.0) as u8;
        }
        if lib.wreq_sorted {
            sort_req(&stats, &c, &mut q);
        }
        lift_level(&stats, &c, &mut q, lib.wreq_minlvl[r]);
        *req = q;
        if stats.len() >= 5 && lib.full_no_status && opt(o, &["异常", "status"]).is_none() {
            *st = [-1; 3];
        }
    }
    // 异常
    if let Some(v) = opt(o, &["异常", "status"]) {
        let mut s = [-1i32; 3];
        if !matches!(v.trim(), "无" | "none" | "0") {
            for (j, part) in v.split([',', '，']).filter(|x| !x.trim().is_empty()).take(3).enumerate() {
                let (k, p) = match part.split_once([':', '：']) {
                    Some((k, p)) => (k, Some(p.trim().parse::<u32>().map_err(|_| format!("异常强度不是数字：{p}"))?)),
                    None => (part, None),
                };
                let k = name_idx(&STATUS_NAMES, k).ok_or_else(|| format!("没有异常「{k}」"))?;
                s[j] = status_sp(lib, k, r, p, rng).ok_or_else(|| format!("异常「{part}」在这个稀有度没有强度表"))?;
            }
        }
        *st = s;
    }
    // 战技：通用战灰照本体的行为变体；专属战技在同一大类的本体上用它自己的行为变体
    if let Some(v) = opt(o, &["战技", "skill"]) {
        let s = match v.parse::<i32>() {
            Ok(n) => n,
            Err(_) => *lib
                .skillinfo
                .iter()
                .find(|(_, i)| i.name.iter().any(|x| x.contains(v)))
                .ok_or_else(|| format!("找不到名字里有「{v}」的战技"))?
                .0,
        };
        let info = lib.skillinfo.get(&s).ok_or_else(|| format!("战技 {s} 不在词条库里"))?;
        (*skill, *var) = match info {
            i if i.gem => (s, b.var),
            i if i.native >= 0 && i.native / 100 == b.var / 100 => (s, i.native),
            i if i.native >= 0 => {
                log(&format!("开发工具：专属战技 {s} 装在不同大类的本体 {} 上，可能只有动作没有伤害", b.id));
                (s, i.native)
            }
            _ => (s, b.var),
        };
    }
    Ok(rec)
}

fn armor(lib: &Lib, tier: usize, o: &HashMap<String, String>, rng: &mut Rng) -> Result<Recipe, String> {
    let r = tier.min(3);
    let base = match (opt(o, &["本体", "base"]), opt(o, &["部位", "slot"])) {
        (Some(v), _) => Some(find(&lib.pbase, v, |b| b.id, |b| &b.name, "防具")?.id),
        (None, Some(s)) => {
            let s = name_idx(&SLOT_NAMES, s).ok_or_else(|| format!("没有部位「{s}」（头 / 身 / 手 / 腿）"))? as u8;
            let list: Vec<&PBase> = lib.pbase.iter().filter(|b| b.slot == s).collect();
            Some(list.get(rng.below(list.len().max(1) as u64) as usize).ok_or("这个部位没有防具本体")?.id)
        }
        _ => None,
    };
    let mut rec = gen_armor_on(lib, tier, base, false, rng).ok_or("防具生成失败")?;
    if let Some(v) = opt(o, &["词条", "affix"]) {
        let Recipe::P { sps, pos, .. } = &mut rec else { unreachable!() };
        let mut out = Vec::new();
        for part in v.split([',', '，']).filter(|x| !x.trim().is_empty()).take(3) {
            let k = find_fam(lib, part)?;
            let f = &lib.fams[k];
            let fr = f.r[r].as_ref().ok_or_else(|| format!("词条 {} 没有这个稀有度", f.key))?;
            out.push((fr.sp, f.key.clone()));
        }
        // 词条数值随机：位置照指定的词条重新抽（原来的是生成时那几条的）
        *pos = out.iter().map(|x| lib.fam_by_key.get(&x.1).and_then(|&k| lib.fams[k].r[r].as_ref()).and_then(|fr| fr.val.as_ref()).map_or(0, |v| v.sample(rng))).collect();
        if pos.iter().all(|&p| p == 0) {
            pos.clear();
        }
        *sps = out;
    }
    Ok(rec)
}

fn talisman(lib: &Lib, tier: usize, o: &HashMap<String, String>, rng: &mut Rng) -> Result<Recipe, String> {
    let r = tier.min(3);
    match opt(o, &["词条", "affix"]) {
        Some(v) => {
            let f = &lib.fams[find_fam(lib, v)?];
            let fr = f.r[r].as_ref().filter(|x| x.tal >= 0).ok_or_else(|| format!("词条 {} 没有这个稀有度的护符（只出在防具上？）", f.key))?;
            Ok(Recipe::A { tal: fr.tal as u32, sp: fr.sp, key: f.key.clone(), pos: fr.val.as_ref().map_or(0, |v| v.sample(rng)) })
        }
        None => gen_talisman(lib, tier, rng).ok_or_else(|| "护符生成失败".into()),
    }
}

/// 一行 → (类, 档, 件数, 参数)
fn parse_line(line: &str) -> Result<(usize, usize, u32, HashMap<String, String>), String> {
    let mut it = line.split_whitespace();
    let cat = match it.next().unwrap_or_default() {
        "武器" | "w" | "weapon" => 0,
        "防具" | "p" | "armor" => 1,
        "护符" | "a" | "talisman" => 2,
        x => return Err(format!("第一个词要写 武器 / 防具 / 护符：{x}")),
    };
    let mut o = HashMap::new();
    for kv in it {
        let (k, v) = kv.split_once(['=', '＝']).ok_or_else(|| format!("参数写成 名字=值：{kv}"))?;
        o.insert(k.trim().to_string(), v.trim().to_string());
    }
    let tier = opt(&o, &["档", "tier"]).map_or(Ok(3), |v| v.parse::<usize>().map_err(|_| format!("档要写 0~4：{v}")))?;
    if tier > 4 {
        return Err(format!("档要写 0~4：{tier}"));
    }
    let n = opt(&o, &["件数", "count"]).map_or(Ok(1), |v| v.parse::<u32>().map_err(|_| format!("件数要写数字：{v}")))?;
    Ok((cat, tier, n.clamp(1, 32), o))
}

/// 一行生成 n 件
fn make(lib: &Lib, line: &str, rng: &mut Rng) -> Result<Vec<(usize, usize, Recipe)>, String> {
    let (cat, tier, n, o) = parse_line(line)?;
    (0..n)
        .map(|_| {
            let r = match cat {
                0 => weapon(lib, tier, &o, rng),
                1 => armor(lib, tier, &o, rng),
                _ => talisman(lib, tier, &o, rng),
            }?;
            Ok((cat, tier, r))
        })
        .collect()
}

pub(super) fn tick(d: &Defs, st: &mut St, pgd: &PlayerGameData) {
    st.dev_wait = st.dev_wait.wrapping_add(1);
    if st.dev_wait % 60 != 0 || st.pending.is_some() || st.more || st.wish_queue > 0 {
        return;
    }
    // 悬浮窗口（dll\dark_dev）的请求：有就发，发完删掉
    let req = dir().join(REQ_FILE);
    if let Ok(text) = fs::read_to_string(&req) {
        let _ = fs::remove_file(&req);
        process(d, st, pgd, &text, REQ_FILE);
        return;
    }
    let path = dir().join(FILE);
    let m = fs::metadata(&path).and_then(|x| x.modified()).unwrap_or(UNIX_EPOCH);
    match st.dev_mtime {
        None => {
            st.dev_mtime = Some(m); // 第一次看到：已经在的那份不发
            return;
        }
        Some(old) if old >= m => return,
        _ => st.dev_mtime = Some(m),
    }
    let text = fs::read_to_string(&path).unwrap_or_default();
    process(d, st, pgd, &text, FILE);
}

/// 「骨灰」行的参数：档=0~3（4 = 幽影之地的传说，同 3）、件数、本体=原版骨灰编号、等级=0~10、前缀=键 / 无、词条=键,键、集结=有 / 无
fn ash_spec(rest: &str) -> Result<(super::ashes::AshSpec, u32), String> {
    let mut spec = super::ashes::AshSpec::default();
    let mut n = 1;
    for kv in rest.split_whitespace() {
        let Some((k, v)) = kv.split_once('=') else { return Err(format!("不认识「{kv}」（要写 键=值）")) };
        let num = |v: &str| v.parse::<u32>().map_err(|_| format!("{k}={v} 不是数字"));
        match k {
            "档" => spec.rar = Some(num(v)?.min(3) as usize),
            "件数" => n = num(v)?.max(1),
            "本体" => spec.kind = Some(num(v)?),
            "等级" => spec.lv = num(v)?,
            "前缀" => spec.pre = Some((v != "无").then(|| v.to_string())),
            "词条" => spec.affs = v.split(',').filter(|x| !x.is_empty()).map(str::to_string).collect(),
            "集结" => spec.rally = Some(v == "有"),
            _ => return Err(format!("不认识的参数「{k}」")),
        }
    }
    Ok((spec, n))
}

/// 按文本里每一行生成、发货
fn process(d: &Defs, st: &mut St, pgd: &PlayerGameData, text: &str, src: &str) {
    let mut rng = Rng::new();
    let held = held(d, pgd);
    let mut free = free(d, st, &held);
    let mut items = Vec::new();
    let mut lines_ok = 0;
    for (no, line) in text.lines().enumerate() {
        let line = line.trim_start_matches('\u{feff}').trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        // 骨灰转换 关 / 开：暂停 / 恢复把原版骨灰换成容器（拿原版骨灰对照）
        if let Some(rest) = line.strip_prefix("骨灰转换") {
            super::ashes::set_paused(rest.trim() == "关");
            lines_ok += 1;
            continue;
        }
        // 骨灰状态：骨灰记录、在场的召唤物写进日志（gear\ashes.rs）
        if line.starts_with("骨灰状态") {
            super::ashes::status();
            lines_ok += 1;
            continue;
        }
        // 骨灰 档= 件数= 本体= 等级= 前缀= 词条= 集结=（同武器 / 护符那几行的写法；F9 发放窗口的「骨灰」类别写的）：直接生成骨灰容器
        if let Some(rest) = line.strip_prefix("骨灰 ").or_else(|| (line == "骨灰").then_some("")) {
            match ash_spec(rest) {
                Ok((spec, n)) => {
                    for l in super::ashes::dev_give(pgd, &spec, n) {
                        log(&format!("开发工具：第 {} 行 → 骨灰 {l}", no + 1));
                    }
                }
                Err(e) => log(&format!("开发工具：第 {} 行没生成：{e}（{line}）", no + 1)),
            }
            lines_ok += 1;
            continue;
        }
        // 道具 <编号> [个数]：借发货表发（超限锻造石这类测试用的材料）
        if let Some(rest) = line.strip_prefix("道具").or_else(|| line.strip_prefix("goods ")) {
            let mut it = rest.split_whitespace();
            match (it.next().and_then(|x| x.parse::<i32>().ok()), it.next().map_or(Some(1), |x| x.parse::<u32>().ok())) {
                (Some(id), Some(n)) if n > 0 => {
                    let ok = gift_n(1, id, n.min(999));
                    log(&format!("开发工具：第 {} 行 → 道具 {id} × {}{}", no + 1, n.min(999), if ok { "，已排队发" } else { "，没发（没有发货表）" }));
                }
                _ => log(&format!("开发工具：第 {} 行要写 道具 <编号> [个数]（{line}）", no + 1)),
            }
            lines_ok += 1;
            continue;
        }
        // 护符编号 <编号>：直接发这件护符模板（不走生成）
        if let Some(rest) = line.strip_prefix("护符编号") {
            match rest.trim().parse::<i32>() {
                Ok(id) => {
                    let ok = gift_n(LOT_CAT[2], id, 1);
                    log(&format!("开发工具：第 {} 行 → 护符 {id}{}", no + 1, if ok { "，已排队发" } else { "，没发（没有发货表）" }));
                }
                Err(_) => log(&format!("开发工具：第 {} 行要写 护符编号 <编号>（{line}）", no + 1)),
            }
            lines_ok += 1;
            continue;
        }
        match make(&d.lib, line, &mut rng) {
            Ok(v) => {
                lines_ok += 1;
                for (cat, tier, recipe) in v {
                    if items.len() as u32 >= d.items.deliver_rows || free[cat].is_empty() {
                        log(&format!("开发工具：第 {} 行有一件放不下（发货表满了或{}容器满了）", no + 1, CAT_ZH[cat]));
                        continue;
                    }
                    let idx = free[cat].remove(0);
                    let rec = Rec { cat, idx, tier: tier as u8, recipe };
                    log(&format!("开发工具：第 {} 行 → {}　{}", no + 1, compose_cap(&d.lib, &rec, 0, d.items.cap[1])[0], rec_line(&rec)));
                    items.push((rec, 0u32));
                }
            }
            Err(e) => log(&format!("开发工具：第 {} 行没生成：{e}（{line}）", no + 1)),
        }
    }
    if items.is_empty() {
        log(&format!("开发工具：{src} 里 {lines_ok} 行，没有要发的"));
        return;
    }
    let n = items.len();
    if let Some(ok) = ship(d, st, items.into_iter().map(|(rec, g)| (Made::Gear(rec), g)).collect()) {
        log(&format!("开发工具：发 {} / {n} 件", ok.len()));
        st.pending = Some(Pending::new(ok));
    }
}

#[cfg(test)]
mod ash_line_tests {
    use super::*;

    /// 「骨灰」行：同 F9 发放窗口写的格式
    #[test]
    fn ash_line() {
        let (s, n) = ash_spec("档=4 件数=2 本体=232000 等级=3 前缀=blast 词条=hp,atk 集结=有").unwrap();
        assert_eq!(n, 2);
        assert_eq!((s.rar, s.kind, s.lv, s.pre, s.affs, s.rally), (Some(3), Some(232000), 3, Some(Some("blast".into())), vec!["hp".to_string(), "atk".to_string()], Some(true)));
        let (s, n) = ash_spec("").unwrap();
        assert_eq!((n, s), (1, super::super::ashes::AshSpec::default()));
        assert_eq!(ash_spec("前缀=无").unwrap().0.pre, Some(None));
        assert!(ash_spec("档=x").is_err());
        assert!(ash_spec("颜色=红").is_err());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn make_from_real_library() {
        let Some((_items, lib)) = super::super::tests::real_defs() else {
            eprintln!("没有 dll\\dark_core\\affixes.txt（先跑一次重随），跳过");
            return;
        };
        let mut rng = Rng(5);
        let v = make(&lib, "武器 档=3 本体=长剑 补正=力气:130,灵巧:90 异常=出血:60,冻伤 件数=2", &mut rng).unwrap();
        assert_eq!(v.len(), 2);
        let Recipe::W { base, cor, req, st, .. } = &v[0].2 else { panic!() };
        assert_eq!(*base, 2000000);
        assert_eq!(cor, &[130.0, 90.0, 0.0, 0.0, 0.0]);
        assert!(req[0] >= req[1] && req[2..].iter().all(|&x| x == 0), "需求排序同补正：{req:?}");
        assert!(need_level(req) >= lib.wreq_minlvl[3]);
        assert!(st[0] > 0 && st[1] > 0 && st[2] <= 0, "两种异常：{st:?}");
        let v = make(&lib, "武器 档=2 项数=5", &mut rng).unwrap();
        let Recipe::W { cor, st, .. } = &v[0].2 else { panic!() };
        assert_eq!(cor.iter().filter(|&&c| c > 0.0).count(), 5);
        assert!(st.iter().all(|&s| s <= 0), "全能不带异常");
        let v = make(&lib, "防具 档=4 部位=腿 词条=飞鸿,dr_gale,鸡尾酒", &mut rng).unwrap();
        let Recipe::P { base, sps, .. } = &v[0].2 else { panic!() };
        assert_eq!(lib.pbase.iter().find(|b| b.id == *base).unwrap().slot, 3);
        assert_eq!(sps.iter().map(|x| x.1.as_str()).collect::<Vec<_>>(), ["dr_leap", "dr_gale", "dr_cocktail"]);
        let v = make(&lib, "武器 档=3 本体=长剑 特效=血狂", &mut rng).unwrap();
        let Recipe::W { spec, .. } = &v[0].2 else { panic!() };
        let br = lib.wspec.iter().find(|x| x.key == "bloodrage").expect("词条库里没有血狂特效");
        assert_eq!(*spec, br.sp, "特效=血狂");
        let v = make(&lib, "武器 档=3 本体=长剑 特效=无", &mut rng).unwrap();
        assert!(matches!(&v[0].2, Recipe::W { spec: -1, .. }));
        let v = make(&lib, "护符 档=1 词条=时隙", &mut rng).unwrap();
        assert!(matches!(&v[0].2, Recipe::A { key, .. } if key == "dr_timeslip"));
        assert!(make(&lib, "护符 词条=飞鸿", &mut rng).is_err(), "飞鸿只出在腿甲上，没有护符");
        assert!(make(&lib, "鞋子 档=1", &mut rng).is_err());
        assert!(make(&lib, "武器 补正=魅力:10", &mut rng).is_err());
    }

    /// dark_dev「一键发放流派」写出的每一行（环境变量 DR_KIT_LINES 指的文件，dark_dev 的 kits_from_real_library 测试写）都生成得出来，
    /// 防具上就是写的那几条词条
    #[test]
    fn kit_lines_generate() {
        let (Some(path), Some((_items, lib))) = (std::env::var_os("DR_KIT_LINES"), super::super::tests::real_defs()) else {
            eprintln!("没设 DR_KIT_LINES 或没有定义文件，跳过");
            return;
        };
        let text = fs::read_to_string(path).unwrap();
        let mut rng = Rng(7);
        let mut n = 0;
        for line in text.lines().filter(|l| !l.trim().is_empty()) {
            let v = make(&lib, line, &mut rng).unwrap_or_else(|e| panic!("{line}：{e}"));
            assert_eq!(v.len(), 1, "{line}");
            if let (Recipe::P { sps, .. }, Some(want)) = (&v[0].2, line.split_whitespace().find_map(|x| x.strip_prefix("词条="))) {
                assert_eq!(sps.iter().map(|x| x.1.as_str()).collect::<Vec<_>>().join(","), want, "{line}");
            }
            n += 1;
        }
        assert!(n > 0);
        eprintln!("一键发放流派：{n} 行都生成得出来");
    }
}
