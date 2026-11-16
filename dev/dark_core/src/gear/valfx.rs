//! 词条数值随机（用户 2026-11-15「数值类型词条的数值变为一个随机范围 截断正态」，同日「不能是占位效果行然后改写内存吗」）：
//! 数值随机的词条不挂在装备行上（build_row 写 -1）。这里每 EVERY 帧看一次身上的生成防具（4 件）和护符（4 格 + 第五护符槽）的配方，
//! 每条随机词条分一组占位效果行（affixes.txt 的 valpool，BLOCK 行一组，rr/affixes.py val_pool 建的），
//! 整行照这一档的效果链抄过来（游戏内存里的参数行）、链内引用改指到这一组、和数成线性关系的字段写成按位置算出的精确数值，
//! 再把链头挂到人物身上；脱下就摘掉。同名的各占一组，所以同稀有度也叠加（不用叠加副本）。
//! 第一次用一条词条的一档时核对：按现在的数算出来的字段要和游戏里这一档的效果行一样（不是用重随的参数启动、或者定义和参数对不上），
//! 对不上的这条词条照固定数值挂这一档原来的效果行。
//! 二期（积木规则 / 专用模块按位置取数）用 worn()：身上每条随机词条的（键, 稀有度, 位置）。
use super::*;

use eldenring::cs::SpEffectParam;

const EVERY: u32 = 15;
/// 一条词条最多几行效果链（rr/affixes.py VAL_BLOCK）
const BLOCK: usize = 4;

/// 身上的一条随机词条：(类, 容器序号, 第几条)
type Inst = (usize, u32, usize);

/// 二期：规则挂的效果行（积木引擎认编号，不能换成占位行）原地改写：每条词条按身上最好的那件（稀有度最高、同稀有度位置最高；同名只认最高）
/// 写这一档的效果行，别的档 / 不戴了的改回原样（第一次改之前存的原行）。改了的行如果正挂在身上就摘掉，积木引擎下一帧按新数值重新挂
fn slots_tick(d: &Defs, st: &mut St, want: &[(Inst, String, usize, i16)]) {
    let v = &mut st.val;
    if want.iter().all(|w| d.lib.fam_by_key.get(&w.1).and_then(|&k| d.lib.fams[k].r[w.2].as_ref()).and_then(|x| x.val.as_ref()).is_none_or(|x| x.slots.is_empty()))
        && v.slot_now.is_empty()
    {
        return;
    }
    // 每条词条最好的那件
    let mut best: HashMap<&str, (usize, i16)> = HashMap::new();
    for (_, key, r, pos) in want {
        let e = best.entry(key.as_str()).or_insert((*r, *pos));
        if (*r, *pos) > *e {
            *e = (*r, *pos);
        }
    }
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    let mut desired: HashMap<i32, Vec<u8>> = HashMap::new();
    for (key, (r, pos)) in &best {
        let Some(val) = d.lib.fam_by_key.get(*key).and_then(|&k| d.lib.fams[k].r[*r].as_ref()).and_then(|x| x.val.as_deref()) else { continue };
        if val.slots.is_empty() {
            continue;
        }
        let nums: HashMap<usize, f32> = val.nums_at(pos_f(*pos)).into_iter().collect();
        let c: HashMap<usize, f32> = val.nums_at(0.0).into_iter().collect();
        for (id, ws) in &val.slots {
            let Some(orig) = v.slot_orig.get(id).cloned().or_else(|| param_bytes::<SpEffectParam>(repo, *id as u32)) else { continue };
            // 第一次核对：按现在的数算的和原行一样
            let ok = *v.checked.entry((format!("{key}#{id}"), *r)).or_insert_with(|| {
                let ok = ws.iter().all(|&(off, fc, a, b, j)| {
                    let want = a as f64 + b as f64 * c.get(&j).copied().unwrap_or(f32::NAN) as f64;
                    get_field(&orig, off, fc).is_some_and(|x| (x - want).abs() <= 1e-3 + 1e-3 * want.abs())
                });
                if !ok {
                    log(&format!("词条数值随机：{key}（稀有度 {r}）挂的效果 {id} 和定义对不上，照固定数值"));
                }
                ok
            });
            if !ok {
                continue;
            }
            v.slot_orig.entry(*id).or_insert_with(|| orig.clone());
            let mut row = orig;
            for &(off, fc, a, b, j) in ws {
                if let Some(n) = nums.get(&j) {
                    put_field(&mut row, off, fc, a as f64 + b as f64 * *n as f64);
                }
            }
            desired.insert(*id, row);
        }
    }
    // 不再需要的改回原样，要的写成精确数值；变了的如果正挂着就摘掉（积木引擎下一帧重新挂）
    let mut touched: Vec<i32> = Vec::new();
    let ids: Vec<i32> = v.slot_now.keys().chain(desired.keys()).copied().collect::<HashSet<_>>().into_iter().collect();
    for id in ids {
        let want_row = desired.get(&id).or_else(|| v.slot_orig.get(&id));
        let Some(want_row) = want_row.cloned() else { continue };
        if v.slot_now.get(&id).map_or_else(|| v.slot_orig.get(&id) == Some(&want_row), |x| *x == want_row) {
            if !desired.contains_key(&id) {
                v.slot_now.remove(&id);
            }
            continue;
        }
        if let Some(dst) = param_mut::<SpEffectParam>(repo, id as u32).filter(|x| x.len() == want_row.len()) {
            dst.copy_from_slice(&want_row);
            touched.push(id);
        }
        if desired.contains_key(&id) {
            v.slot_now.insert(id, want_row);
        } else {
            v.slot_now.remove(&id);
        }
    }
    if touched.is_empty() {
        return;
    }
    log(&format!("词条数值随机：规则挂的效果行改写 {} 行（{:?}）", touched.len(), best));
    if let Some(p) = unsafe { WorldChrMan::instance_mut() }.ok().and_then(|w| w.main_player.as_mut()) {
        let on: HashSet<i32> = p.chr_ins.special_effect.entries().map(|x| x.param_id).collect();
        for id in touched.into_iter().filter(|id| on.contains(id)) {
            p.remove_speffect(id);
        }
    }
}

#[derive(Default)]
pub(super) struct ValSt {
    /// 正挂着的：词条 → (第几组, 写进去的各行)
    held: HashMap<Inst, (usize, Vec<Vec<u8>>)>,
    /// 核对过的（键, 稀有度）→ 定义和游戏参数对得上
    checked: HashMap<(String, usize), bool>,
    /// 占位行在不在游戏参数里（第一次要用时查）
    pool_ok: Option<bool>,
    /// 组不够用记过日志了
    full_logged: bool,
    /// 二期：改写过的规则效果行的原样、现在写成的样子
    slot_orig: HashMap<i32, Vec<u8>>,
    slot_now: HashMap<i32, Vec<u8>>,
}

/// 身上每条随机词条的（键, 稀有度, 位置 -1~1）；二期的积木规则 / 专用模块按这个取数（gear::val_best）
pub(crate) fn worn() -> Vec<(String, usize, f32)> {
    WORN.lock().map(|g| g.clone()).unwrap_or_default()
}

static WORN: Mutex<Vec<(String, usize, f32)>> = Mutex::new(Vec::new());

/// 写一个字段（类型照参数定义的格式字符）
fn put_field(row: &mut [u8], off: usize, fc: u8, v: f64) {
    let w = |row: &mut [u8], b: &[u8]| {
        if off + b.len() <= row.len() {
            row[off..off + b.len()].copy_from_slice(b);
        }
    };
    match fc {
        b'f' => w(row, &(v as f32).to_le_bytes()),
        b'd' => w(row, &v.to_le_bytes()),
        b'i' => w(row, &(v.round() as i32).to_le_bytes()),
        b'I' => w(row, &(v.round().max(0.0) as u32).to_le_bytes()),
        b'h' => w(row, &(v.round() as i16).to_le_bytes()),
        b'H' => w(row, &(v.round().max(0.0) as u16).to_le_bytes()),
        b'b' => w(row, &(v.round() as i8).to_le_bytes()),
        b'B' => w(row, &(v.round().clamp(0.0, 255.0) as u8).to_le_bytes()),
        _ => {}
    }
}

/// 读一个字段
fn get_field(row: &[u8], off: usize, fc: u8) -> Option<f64> {
    let b = |n: usize| row.get(off..off + n);
    Some(match fc {
        b'f' => f32::from_le_bytes(b(4)?.try_into().ok()?) as f64,
        b'd' => f64::from_le_bytes(b(8)?.try_into().ok()?),
        b'i' => i32::from_le_bytes(b(4)?.try_into().ok()?) as f64,
        b'I' => u32::from_le_bytes(b(4)?.try_into().ok()?) as f64,
        b'h' => i16::from_le_bytes(b(2)?.try_into().ok()?) as f64,
        b'H' => u16::from_le_bytes(b(2)?.try_into().ok()?) as f64,
        b'b' => b(1)?[0] as i8 as f64,
        b'B' => b(1)?[0] as f64,
        _ => return None,
    })
}

/// 一组占位行的内容：照这一档的效果链（tpl，和 v.rows 一一对应）抄，链内引用指到这一组（ids），字段写成位置 p 的数
fn block_rows(v: &Val, p: f32, tpl: &[Vec<u8>], ids: &[i32]) -> Vec<Vec<u8>> {
    let nums: HashMap<usize, f32> = v.nums_at(p).into_iter().collect();
    let mut out: Vec<Vec<u8>> = tpl.to_vec();
    for &(row, off, to) in &v.refs {
        if let (Some(r), Some(&id)) = (out.get_mut(row), ids.get(to)) {
            put_field(r, off, b'i', id as f64);
        }
    }
    for &(row, off, fc, a, b, j) in &v.fields {
        if let (Some(r), Some(&n)) = (out.get_mut(row), nums.get(&j)) {
            put_field(r, off, fc, a as f64 + b as f64 * n as f64);
        }
    }
    out
}

/// 定义和游戏里这一档的效果行对得上：按现在的数（位置 0）算出来的字段和原行一样
fn matches(v: &Val, tpl: &[Vec<u8>]) -> bool {
    let nums: HashMap<usize, f32> = v.nums_at(0.0).into_iter().collect();
    v.fields.iter().all(|&(row, off, fc, a, b, j)| {
        let (Some(t), Some(&n)) = (tpl.get(row), nums.get(&j)) else { return false };
        let want = a as f64 + b as f64 * n as f64;
        get_field(t, off, fc).is_some_and(|x| (x - want).abs() <= 1e-3 + 1e-3 * want.abs())
    })
}

/// 分组：留着的照旧，摘掉的空出来，新的从空的里按顺序拿（不够的不挂）。返回 新的 → 组
fn assign(held: &HashMap<Inst, (usize, Vec<Vec<u8>>)>, want: &[Inst], n: usize) -> (HashMap<Inst, usize>, Vec<Inst>) {
    let keep: HashMap<Inst, usize> = want.iter().filter_map(|i| held.get(i).map(|x| (*i, x.0))).collect();
    let used: HashSet<usize> = keep.values().copied().collect();
    let mut free = (0..n).filter(|b| !used.contains(b));
    let mut out = keep;
    let mut miss = Vec::new();
    for i in want {
        if out.contains_key(i) {
            continue;
        }
        match free.next() {
            Some(b) => {
                out.insert(*i, b);
            }
            None => miss.push(*i),
        }
    }
    (out, miss)
}

pub(super) fn tick(d: &Defs, st: &mut St, pgd: &PlayerGameData) {
    let pool = &d.lib.valpool;
    // 没有占位行（关了词条数值随机、或只有二期的词条）也照样记身上的随机词条、改写二期的效果行，只是不挂一期的占位行
    if st.frames % EVERY != 7 || d.lib.fams.is_empty() {
        return;
    }
    let groups = pool.len() / BLOCK;
    // 身上的随机词条
    let e = &pgd.equipment.equipment_entries;
    let mut want: Vec<(Inst, String, usize, i16)> = Vec::new(); // 一期、二期都在这里，记完 worn 再只留一期
    for id in [e.protector_head, e.protector_chest, e.protector_hands, e.protector_legs] {
        let Some(idx) = d.items.cont[1].idx_of(id.param_id()) else { continue };
        if let Some(Rec { recipe: Recipe::P { sps, pos, .. }, .. }) = st.recs.get(&(1, idx)) {
            for (i, (sp, key)) in sps.iter().enumerate() {
                if let Some(r) = sp_rar(&d.lib, key, *sp).filter(|&r| has_val(&d.lib, key, r)) {
                    want.push(((1, idx, i), key.clone(), r, pos_at(pos, i)));
                }
            }
        }
    }
    for id in e.accessories.iter().chain(std::iter::once(&e.covenant)).filter_map(|x| x.as_valid()) {
        let Some(idx) = d.items.cont[2].idx_of(id.param_id()) else { continue };
        if let Some(Rec { recipe: Recipe::A { sp, key, pos, .. }, .. }) = st.recs.get(&(2, idx)) {
            if let Some(r) = sp_rar(&d.lib, key, *sp).filter(|&r| has_val(&d.lib, key, r)) {
                if !want.iter().any(|w| w.0 == (2, idx, 0)) {
                    want.push(((2, idx, 0), key.clone(), r, *pos));
                }
            }
        }
    }
    if let Ok(mut g) = WORN.lock() {
        *g = want.iter().map(|w| (w.1.clone(), w.2, pos_f(w.3))).collect();
    }
    // 二期的（积木规则 / 专用模块）：效果行原地改写，规则里的数、模块的数由 rules.rs / runtime.rs 按 worn() 取；下面占位行只管一期
    slots_tick(d, st, &want);
    want.retain(|w| is_val(&d.lib, &w.1, w.2));
    if pool.is_empty() && want.is_empty() {
        return;
    }
    let v = &mut st.val;
    if want.is_empty() && v.held.is_empty() {
        return;
    }
    let Ok(wcm) = (unsafe { WorldChrMan::instance_mut() }) else { return };
    let Some(p) = wcm.main_player.as_mut() else { return };
    let Ok(repo) = (unsafe { SoloParamRepository::instance_mut() }) else { return };
    if v.pool_ok.is_none() {
        let ok = pool.iter().all(|&id| repo.get::<SpEffectParam>(id as u32).is_some());
        if !ok {
            log("词条数值随机：占位效果行不在游戏参数里（这次不是用重随的参数启动？），随机词条照固定数值挂");
        }
        v.pool_ok = Some(ok);
    }
    let on: HashSet<i32> = p.chr_ins.special_effect.entries().map(|x| x.param_id).collect();
    let ids = |b: usize| -> Vec<i32> { pool[b * BLOCK..(b + 1) * BLOCK].to_vec() };
    let insts: Vec<Inst> = want.iter().map(|w| w.0).collect();
    let (plan, miss) = if v.pool_ok == Some(true) { assign(&v.held, &insts, groups) } else { (HashMap::new(), insts.clone()) };
    // 摘掉不穿的 / 换了组的
    let gone: Vec<Inst> = v.held.keys().filter(|i| plan.get(i) != v.held.get(i).map(|x| &x.0)).copied().collect();
    for i in gone {
        if let Some((b, _)) = v.held.remove(&i) {
            for id in ids(b) {
                if on.contains(&id) {
                    p.remove_speffect(id);
                }
            }
        }
    }
    let mut fixed: HashSet<i32> = HashSet::new();
    for (inst, key, r, pos) in &want {
        let Some(val) = d.lib.fam_by_key.get(key).and_then(|&k| d.lib.fams[k].r[*r].as_ref()).and_then(|x| x.val.as_deref()) else { continue };
        let tpl: Option<Vec<Vec<u8>>> = val.rows.iter().map(|&sp| param_bytes::<SpEffectParam>(repo, sp as u32)).collect();
        let ok = *v.checked.entry((key.clone(), *r)).or_insert_with(|| {
            let ok = tpl.as_ref().is_some_and(|t| t.len() <= BLOCK && matches(val, t));
            if !ok {
                log(&format!("词条数值随机：{key}（稀有度 {r}）的定义和游戏参数对不上，照固定数值"));
            }
            ok
        });
        let block = plan.get(inst).copied().filter(|_| ok);
        let (Some(b), Some(tpl)) = (block, tpl) else {
            // 照固定数值：挂这一档原来的链头（同一个效果挂一次就够）
            if let Some(&root) = val.rows.first() {
                fixed.insert(root);
            }
            continue;
        };
        let bid = ids(b);
        let rows = block_rows(val, pos_f(*pos), &tpl, &bid);
        let same = v.held.get(inst).is_some_and(|x| x.1 == rows);
        if !same {
            for &id in &bid {
                if on.contains(&id) {
                    p.remove_speffect(id);
                }
            }
            for (k, row) in rows.iter().enumerate() {
                if let Some(dst) = param_mut::<SpEffectParam>(repo, bid[k] as u32).filter(|x| x.len() == row.len()) {
                    dst.copy_from_slice(row);
                }
            }
            log(&format!("词条数值随机：{key}（稀有度 {r}，位置 {pos}‰）挂到第 {b} 组：{:?}", val.nums_at(pos_f(*pos))));
            v.held.insert(*inst, (b, rows));
            p.apply_speffect(bid[0], false);
        } else if !on.contains(&bid[0]) {
            p.apply_speffect(bid[0], false); // 死了 / 读图后被清掉了：补挂
        }
    }
    // 照固定数值挂的（对不上定义的、组不够的）：只在身上没有时挂；不再需要的不摘（装备行没挂过它们，原版一样的效果别的来源也可能挂着）
    for root in fixed {
        if !on.contains(&root) {
            p.apply_speffect(root, false);
        }
    }
    if !miss.is_empty() && v.pool_ok == Some(true) && !v.full_logged {
        log(&format!("词条数值随机：身上的随机词条 {} 条，占位行只够 {groups} 组，多的照固定数值", insts.len()));
        v.full_logged = true;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn val() -> Val {
        Val {
            lo: 4.0,
            hi: 8.0,
            mu: 6.0,
            sigma: 1.0,
            c: 6.0,
            main: 0,
            prec: 0.1,
            others: vec![(1, 1.0, vec![(2.0, 20.0), (6.0, 30.0), (10.0, 40.0)])],
            tpl: ["伤害＋{0}％，回复{1}点".into(), "dmg {0}% heal {1}".into()],
            span: Default::default(),
            rows: vec![100, 101],
            refs: vec![(0, 8, 1)],
            fields: vec![(1, 0, b'f', 1.0, 0.01, 0), (1, 4, b'i', 0.0, -1.0, 1)],
            ..Default::default()
        }
    }

    /// 占位行：照模板抄、引用指到这一组、字段写成精确的数；按现在的数算的和原行一样才算对得上
    #[test]
    fn block_rows_and_check() {
        let v = val();
        let mut t1 = vec![0u8; 16];
        put_field(&mut t1, 0, b'f', 1.06);
        put_field(&mut t1, 4, b'i', -30.0);
        let tpl = vec![vec![0u8; 16], t1];
        assert!(matches(&v, &tpl));
        let rows = block_rows(&v, 1.0, &tpl, &[900, 901, 902, 903]);
        assert_eq!(get_field(&rows[0], 8, b'i'), Some(901.0), "链头的引用指到这一组的第 1 行");
        assert!((get_field(&rows[1], 0, b'f').unwrap() - 1.08).abs() < 1e-6, "上端 8％");
        assert_eq!(get_field(&rows[1], 4, b'i'), Some(-35.0), "跟着插值：主数 8 → 35 点");
        let rows = block_rows(&v, -0.5, &tpl, &[900, 901, 902, 903]);
        assert!((get_field(&rows[1], 0, b'f').unwrap() - 1.05).abs() < 1e-6, "下半段一半：5％");
        let mut bad = tpl.clone();
        put_field(&mut bad[1], 0, b'f', 1.07);
        assert!(!matches(&v, &bad), "参数和定义对不上");
        assert_eq!(v.text(1.0, 0), "伤害＋8％，回复35点");
        assert_eq!(v.text(0.0, 1), "dmg 6% heal 30");
        assert_eq!(v.text(0.25, 0), "伤害＋6.5％，回复31点");
    }

    /// 分组：留着的照旧，新的拿空的，不够的记下来
    #[test]
    fn assign_keeps_and_fills() {
        let mut held = HashMap::new();
        held.insert((1, 5, 0), (2, Vec::new()));
        held.insert((2, 9, 0), (0, Vec::new()));
        let want = [(1, 5, 0), (1, 6, 1), (1, 7, 0)];
        let (plan, miss) = assign(&held, &want, 3);
        assert_eq!(plan[&(1, 5, 0)], 2, "留着的照旧");
        assert_eq!(plan[&(1, 6, 1)], 0, "摘掉的那组空出来给新的");
        assert_eq!(plan[&(1, 7, 0)], 1);
        assert!(miss.is_empty());
        let (plan, miss) = assign(&HashMap::new(), &want, 2);
        assert_eq!(plan.len(), 2);
        assert_eq!(miss, vec![(1, 7, 0)]);
    }

    /// 抽位置：落在范围里、均值接近现在的数，取整后再算回来是同一个数
    #[test]
    fn sample_stays_in_range() {
        let mut v = val();
        v.lo = 1.0;
        v.hi = 3.875;
        v.c = 2.0;
        v.mu = 1.62147;
        v.sigma = 0.9375;
        v.prec = 1.0;
        let mut rng = Rng(11);
        let mut sum = 0.0;
        let n = 20000;
        for _ in 0..n {
            let p = v.sample(&mut rng);
            let x = v.main_at(pos_f(p));
            assert!((1.0..=4.0).contains(&x), "{x}");
            assert_eq!(x, x.round());
            sum += x as f64;
        }
        let mean = sum / n as f64;
        assert!((mean - 2.0).abs() < 0.08, "均值 {mean}");
    }
}
