//! 超限锻造石（参数侧 rr/overlimit.py；设计稿 dev\item_system\超限锻造石与高难度.md §1）：装备工坊「超限」页的规则和执行
//! （界面 dll\dark_ui，接口和快照在 workshop.rs）。
//! - 武器：这把所有有补正的项，每颗各加一个步长，各自到超限上限为止（按稀有度和补正项数，Lib 的 ovlw：原上限 × 1.1）；
//!   记录里标「超限过」，不能再重铸。改的是配方里的补正值，法器倍率、强化照旧乘在上面。
//! - 防具：减伤倍率每颗加一个步长，到超限上限为止（ovlp：原上限 × 1.2）；第一次超限时从现在按记录算的倍率起，之后存在记录里
//!   （继承词条换了词条也不变）。
//! - 步长 = （超限上限 − 中位）÷ steps（items.txt 的 overlimit 行，默认 50），按稀有度固定：抽得好的用得少。
//! - 先改行、再扣石头，扣不掉就改回去（同重铸）；然后存记录。说明里不写超限（用户 2026-11-03）：超过原上限的补正在原版面板上变金色（scaling.rs）。
//! - 防具词条升级（用户 2026-11-04「超限锻造石可以提升词条等级的功能 最高还是传说」「只有防具石升防具」，消耗 1 / 2 / 3 颗）：
//!   防具的一条词条升到上一个稀有度（词条库里这条词条有的下一档），升到稀有 1 颗、史诗 2 颗、传说 3 颗防具石。武器的词条没有档位，不能升。
//!   减伤倍率是按记录（含各词条的效果编号）抽的，换了效果编号会变：没定住的先把现在的倍率存进记录（同超限），升词条不改减伤。
use super::*;

/// 升到稀有度 t 要几颗防具石（用户 2026-11-04：1 / 2 / 3）
pub(super) fn affix_cost(t: usize) -> u32 {
    t.clamp(1, 3) as u32
}

/// 防具第 i 条词条升一档：(新配方, 原稀有度, 新稀有度)；不能升的返回原因（中文, 英文）
pub(super) fn affix_up(lib: &Lib, rec: &Rec, i: usize) -> Result<(Rec, usize, usize), [&'static str; 2]> {
    let Recipe::P { sps, .. } = &rec.recipe else { return Err(["只有防具的词条能升级", "only armor affixes can be upgraded"]) };
    let (sp, key) = sps.get(i).ok_or(["没有这条词条", "no such affix"])?;
    let f = lib.fam_by_key.get(key.as_str()).map(|&k| &lib.fams[k]).ok_or(["词条库里没有这条词条", "unknown affix"])?;
    let r = sp_rar(lib, key, *sp).ok_or(["这条词条的稀有度对不上", "unknown affix rarity"])?;
    // 词条数值随机：记录里的位置不变，升上去还是在那一档范围里的同一个位置（偏低的升上去还是偏低）
    let (t, nsp) = (r + 1..4).find_map(|t| f.r[t].as_ref().map(|x| (t, x.sp))).ok_or(["已经是最高稀有度", "already at its highest rarity"])?;
    let mut new = rec.clone();
    if let Recipe::P { sps, mult, .. } = &mut new.recipe {
        if mult.is_none() {
            *mult = armor_now(lib, rec);
        }
        sps[i].0 = nsp;
    }
    Ok((new, r, t))
}

/// 装备工坊「超限」页的防具词条升级：配方序号 k 的第 i 条
pub(super) fn affix_apply(d: &Defs, st: &mut St, pgd: &mut PlayerGameData, who: &(i32, String), k: u32, i: usize) -> Result<[String; 2], [String; 2]> {
    let e = |zh: &str, en: &str| [zh.to_string(), en.to_string()];
    let o = d.items.overlimit.ok_or_else(|| e("这次没开超限锻造石", "Overlimit Smithing Stones are disabled"))?;
    let old = st.recs.get(&(1, k)).cloned().ok_or_else(|| e("不是你的生成防具", "this is not your generated armor"))?;
    let base = rec_id(&d.items, &old);
    let held = pgd.equipment.equip_inventory_data.items_data.normal_entries().iter().filter_map(|x| x.as_option()).any(|it| {
        it.item_id.category() as u8 == INV_CAT[1] && it.quantity > 0 && it.item_id.param_id() == base
    });
    if !held {
        return Err(e("这件防具不在背包里了", "the armor is no longer in your inventory"));
    }
    let (new, r, t) = affix_up(&d.lib, &old, i).map_err(|w| e(w[0], w[1]))?;
    let cost = affix_cost(t);
    let have = count_goods(pgd, o.ga);
    if have < cost {
        return Err([format!("要 {cost} 颗超限锻造石（防具），现有 {have} 颗"), format!("needs {cost} Overlimit Smithing Stones (Armor); you have {have}")]);
    }
    write_row(d, st, &new).map_err(|x| [format!("改写失败：{x}"), format!("failed to rewrite: {x}")])?;
    let got = remove_goods(pgd, o.ga, cost);
    if got < cost {
        let _ = write_row(d, st, &old);
        if got > 0 {
            gift_n(1, o.ga as i32, got); // 扣了一部分：还回去
        }
        return Err(e("扣不掉超限锻造石（防具），已改回原样", "could not use the Overlimit Smithing Stones (Armor); nothing changed"));
    }
    write_texts(d, &new);
    let key = match &new.recipe {
        Recipe::P { sps, .. } => sps[i].1.clone(),
        _ => String::new(),
    };
    let rn = |x: usize, l: usize| strip_font(&d.lib.rar[x.min(3)][l]);
    log(&format!("词条升级：{base} 第 {i} 条 {key} {} → {}，用了 {cost} 颗防具石
  旧 {}
  新 {}", rn(r, 0), rn(t, 0), rec_line(&old), rec_line(&new)));
    let names = [plain_name(d, &new, 0), plain_name(d, &new, 1)];
    let worn = worn_armor(pgd).contains(&base);
    if worn {
        // 随机词条不在装备行上（gear/valfx.rs 下一轮按新稀有度换占位行），这里只同步装备行上挂的
        log(&format!("词条升级：这件正穿着，{}", sync_worn_effects(pgd, &native_sps(&d.lib, &old), &native_sps(&d.lib, &new))));
    }
    st.recs.insert((new.cat, new.idx), new);
    rec_save(who, st);
    Ok([
        format!(
            "「{}」的「{}」升到{}，用了 {cost} 颗超限锻造石（防具）{}",
            names[0],
            suffix(&d.lib, &key, 0),
            rn(t, 0),
            if worn { "；正穿着，已经生效" } else { "" }
        ),
        format!(
            "\"{}\" on \"{}\" is now {}: used {cost} Overlimit Smithing Stones (Armor){}",
            suffix(&d.lib, &key, 1),
            names[1],
            rn(t, 1),
            if worn { "; it is worn and already takes effect" } else { "" }
        ),
    ])
}

/// 武器的 (中位, 原上限, 超限上限)：按稀有度和补正项数（没有这个项数的照两项）
pub(super) fn cap_w(lib: &Lib, r: usize, cor: &[f32; 5]) -> Option<(f32, f32, f32)> {
    let n = cor.iter().filter(|&&c| c > 0.0).count() as u32;
    lib.ovlw.get(&(r, n)).or_else(|| lib.ovlw.get(&(r, 2))).copied()
}

/// 这把武器自己的超限上限倍率（用户 2026-11-21）：法杖、圣印记（有法器倍率的，wcast）是 1；别的武器按记录抽
/// 1 ± spread 的截断正态（同法器倍率的抽法，种子不同：同一把一直一样，不用存）
pub(super) fn cap_mult(lib: &Lib, rec: &Rec, spread: f32) -> f32 {
    let Recipe::W { base, .. } = &rec.recipe else { return 1.0 };
    if spread <= 0.0 || lib.wcast.contains_key(base) {
        return 1.0;
    }
    let s = spread as f64;
    trunc_normal(1.0 - s, 1.0 + s, 0x0C4F_7A11_CA9E_0001u64 ^ (rec.idx as u64) << 24 ^ (rec.tier as u64) << 56 ^ *base as u64) as f32
}

/// 武器的 (中位, 原上限, 这把的超限上限, 每颗的步长)：步长按没随机的超限上限算（每颗加的量同稀有度一样），到这把自己的上限为止。
/// 这把的超限上限不低于原上限（用户 2026-11-22「改为正负10%吧 不然会出现超限上限反而比原上限更低的问题」：±10% 时最低是原上限 × 1.1 × 0.9，
/// 还是比原上限低一点，压到原上限）
pub(super) fn cap_rec(lib: &Lib, rec: &Rec, o: &Overlimit) -> Option<(f32, f32, f32, f32)> {
    let Recipe::W { cor, .. } = &rec.recipe else { return None };
    let (med, hi, cap) = cap_w(lib, rec.rar(), cor)?;
    Some((med, hi, (cap * cap_mult(lib, rec, o.wspread)).max(hi), (cap - med) / o.steps_for(rec).max(1) as f32))
}

/// 防具现在的减伤倍率：超限过的存在记录里，没有就按记录算（armor_mult）
pub(super) fn armor_now(lib: &Lib, rec: &Rec) -> Option<f64> {
    let Recipe::P { base, sps, mult, .. } = &rec.recipe else { return None };
    mult.or_else(|| lib.pdef[rec.rar()].map(|(lo, hi)| armor_mult(lo, hi, rec, *base, sps)))
}

/// 用最多 n 颗以后的配方、实际用了几颗（每项各自到上限为止，全部到顶就停）；已经到顶 / 没有上限数据 None。
/// 武器到这把自己的超限上限（cap_rec）；已经高过它的项（上限抽得低、以前超限过的）不降，只是不再涨
pub(super) fn step(lib: &Lib, rec: &Rec, n: u32, o: &Overlimit) -> Option<(Rec, u32)> {
    let r = rec.rar();
    let steps = o.steps_for(rec);
    let mut new = rec.clone();
    let used = match &mut new.recipe {
        Recipe::W { cor, ovl, .. } => {
            let (_, _, cap, s) = cap_rec(lib, rec, o)?;
            if s <= 0.0 {
                return None;
            }
            let need = (0..5).filter(|&k| cor[k] > 0.0).map(|k| ((cap - cor[k]) / s - 1e-3).ceil().max(0.0) as u32).max()?;
            let used = n.min(need);
            for c in cor.iter_mut().filter(|c| **c > 0.0) {
                *c = (*c + s * used as f32).min(cap).max(*c);
            }
            *ovl = true;
            used
        }
        Recipe::P { mult, .. } => {
            let cur = armor_now(lib, rec)?;
            let (med, _, cap) = lib.ovlp[r]?;
            let s = (cap - med) / steps.max(1) as f64;
            if s <= 0.0 {
                return None;
            }
            let need = ((cap - cur) / s - 1e-6).ceil().max(0.0) as u32;
            let used = n.min(need);
            *mult = Some((cur + s * used as f64).min(cap).max(cur));
            used
        }
        Recipe::A { .. } => return None,
    };
    (used > 0).then_some((new, used))
}

/// 到超限上限还要几颗
pub(super) fn need(lib: &Lib, rec: &Rec, o: &Overlimit) -> u32 {
    step(lib, rec, u32::MAX, o).map_or(0, |x| x.1)
}

/// 用之前 → 之后（结果提示用）：武器各项补正、防具倍率
fn change(lib: &Lib, old: &Rec, new: &Rec) -> [String; 2] {
    match (&old.recipe, &new.recipe) {
        (Recipe::W { cor: a, .. }, Recipe::W { cor: b, .. }) => {
            let parts = |l: usize| -> Vec<String> {
                (0..5).filter(|&k| a[k] > 0.0).map(|k| format!("{} {:.0} → {:.0}", lib.stat.get(k).map_or("", |s| s[l].as_str()), a[k].floor(), b[k].floor())).collect()
            };
            [parts(0).join("、"), parts(1).join(", ")]
        }
        _ => {
            let (a, b) = (armor_now(lib, old).unwrap_or(1.0), armor_now(lib, new).unwrap_or(1.0));
            [format!("减伤倍率 ×{a:.2} → ×{b:.2}"), format!("negation multiplier ×{a:.2} → ×{b:.2}")]
        }
    }
}

/// 装备工坊「超限」：cat 0 武器 / 1 防具，k = 配方序号，n = 最多用几颗（u32::MAX = 用到上限，石头不够就用光）
pub(super) fn apply(d: &Defs, st: &mut St, pgd: &mut PlayerGameData, who: &(i32, String), cat: usize, k: u32, n: u32) -> Result<[String; 2], [String; 2]> {
    let e = |zh: &str, en: &str| [zh.to_string(), en.to_string()];
    let o = d.items.overlimit.ok_or_else(|| e("这次没开超限锻造石", "Overlimit Smithing Stones are disabled"))?;
    if cat > 1 {
        return Err(e("只有武器和防具能超限", "only armaments and armor can be overlimited"));
    }
    let goods = if cat == 0 { o.gw } else { o.ga };
    let stone = if cat == 0 { ["超限锻造石（武器）", "Overlimit Smithing Stone (Armament)"] } else { ["超限锻造石（防具）", "Overlimit Smithing Stone (Armor)"] };
    let old = st.recs.get(&(cat, k)).cloned().ok_or_else(|| e("不是你的生成装备", "this is not your generated equipment"))?;
    let base = rec_id(&d.items, &old);
    let held = pgd.equipment.equip_inventory_data.items_data.normal_entries().iter().filter_map(|x| x.as_option()).any(|it| {
        let pid = it.item_id.param_id();
        it.item_id.category() as u8 == INV_CAT[cat] && it.quantity > 0 && if cat == 0 { pid / 10000 * 10000 } else { pid } == base
    });
    if !held {
        return Err(e("这件装备不在背包里了", "the item is no longer in your inventory"));
    }
    let have = count_goods(pgd, goods);
    if have < 1 {
        return Err([format!("没有{}", stone[0]), format!("you have no {}", stone[1])]);
    }
    let (mut new, mut used) = step(&d.lib, &old, n.min(have), &o).ok_or_else(|| e("已经到超限上限了", "already at the overlimit cap"))?;
    write_row(d, st, &new).map_err(|x| [format!("改写失败：{x}"), format!("failed to rewrite: {x}")])?;
    let got = remove_goods(pgd, goods, used);
    if got < used {
        // 只扣掉一部分：按扣掉的颗数重算；一颗都没扣掉就改回去
        match step(&d.lib, &old, got, &o).filter(|_| got > 0) {
            Some((r2, u2)) if write_row(d, st, &r2).is_ok() => (new, used) = (r2, u2),
            _ => {
                let _ = write_row(d, st, &old);
                return Err([format!("扣不掉{}，已改回原样", stone[0]), format!("could not use the {}; nothing changed", stone[1])]);
            }
        }
    }
    write_texts(d, &new);
    let ch = change(&d.lib, &old, &new);
    log(&format!("超限：{base} 用了 {used} 颗（{}）\n  旧 {}\n  新 {}", ch[0], rec_line(&old), rec_line(&new)));
    let names = [plain_name(d, &new, 0), plain_name(d, &new, 1)];
    st.recs.insert((new.cat, new.idx), new);
    rec_save(who, st);
    Ok([format!("「{}」用了 {used} 颗{}：{}", names[0], stone[0], ch[0]), format!("Used {used} {} on \"{}\": {}", stone[1], names[1], ch[1])])
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lib() -> Lib {
        let mut l = Lib::default();
        l.ovlw.insert((3, 2), (125.0, 150.0, 165.0));
        l.ovlw.insert((3, 5), (60.0, 72.0, 79.2));
        l.ovlp[3] = Some((1.7, 1.8, 2.16));
        l.pdef[3] = Some((1.6, 1.8));
        l
    }

    /// 50 颗到顶、不随机上限（原来的规则）
    const O50: Overlimit = Overlimit { gw: 9242, ga: 9243, steps: 50, asteps: 50, wspread: 0.0 };

    fn wrec(cor: [f32; 5]) -> Rec {
        wrec_at(1, 1, cor)
    }

    fn wrec_at(idx: u32, base: u32, cor: [f32; 5]) -> Rec {
        Rec {
            cat: 0,
            idx,
            tier: 3,
            recipe: Recipe::W { base, var: 0, skill: -1, cor, req: [0; 5], curve: [0; CURVE_N], st: [-1; 3], res: [-1; 2], glow: -1, spec: -1, atk: 0, ovl: false, elem: 0, share: 0 },
        }
    }

    /// 随机上限：法杖、圣印记（wcast）和 spread 0 是 1；别的武器在 0.8~1.2、同一把一直一样、平均约 1；每颗加的量不变，到这把自己的上限为止；
    /// 上限低过现在补正的不降、用不了
    #[test]
    fn weapon_cap_rand() {
        let mut l = lib();
        l.wcast.insert(7, (true, false));
        let o = Overlimit { wspread: 0.2, ..O50 };
        assert_eq!(cap_mult(&l, &wrec_at(3, 7, [110.0, 145.0, 0.0, 0.0, 0.0]), 0.2), 1.0, "法杖不随机");
        assert_eq!(cap_mult(&l, &wrec_at(3, 1, [110.0, 145.0, 0.0, 0.0, 0.0]), 0.0), 1.0, "没写 spread 不随机");
        let ms: Vec<f32> = (0..2000).map(|i| cap_mult(&l, &wrec_at(i, 1000000 + i % 7 * 100, [110.0, 0.0, 0.0, 0.0, 0.0]), 0.2)).collect();
        assert!(ms.iter().all(|m| (0.8..=1.2).contains(m)));
        let mean = ms.iter().sum::<f32>() / ms.len() as f32;
        assert!((mean - 1.0).abs() < 0.01, "{mean}");
        assert!(ms.iter().any(|&m| m < 0.85) && ms.iter().any(|&m| m > 1.15), "两头都抽得到");
        let r = wrec_at(5, 1000000, [110.0, 145.0, 0.0, 0.0, 0.0]);
        assert_eq!(cap_mult(&l, &r, 0.2), cap_mult(&l, &r.clone(), 0.2), "同一把一样");
        let m = cap_mult(&l, &r, 0.2);
        let (med, hi, cap, s) = cap_rec(&l, &r, &o).unwrap();
        assert_eq!((med, hi), (125.0, 150.0));
        assert!((cap - (165.0 * m).max(150.0)).abs() < 1e-3 && (s - 0.8).abs() < 1e-6, "{cap} {s}");
        // 超限上限不低于原上限（±20% 时抽得低的压到 150；±10% 时最低 148.5 也压到 150）
        for spread in [0.2f32, 0.1] {
            let o2 = Overlimit { wspread: spread, ..O50 };
            for i in 0..500 {
                let (_, hi, cap, _) = cap_rec(&l, &wrec_at(i, 1000000 + i % 7 * 100, [110.0, 145.0, 0.0, 0.0, 0.0]), &o2).unwrap();
                assert!(cap >= hi && cap <= 165.0 * (1.0 + spread) + 1e-3, "{spread} {cap}");
            }
        }
        let (top, _) = step(&l, &r, u32::MAX, &o).unwrap_or((r.clone(), 0));
        let Recipe::W { cor, .. } = &top.recipe else { panic!() };
        assert!(cor[0] <= cap + 1e-3 && cor[0] >= 110.0, "{cor:?} {cap}");
        // 上限比现在的补正低：不降，用不了
        let low = (0..2000).map(|i| wrec_at(i, 1000000, [160.0, 0.0, 0.0, 0.0, 0.0])).find(|r| 165.0 * cap_mult(&l, r, 0.2) < 160.0).unwrap();
        assert!(step(&l, &low, 5, &o).is_none());
        assert_eq!(need(&l, &low, &o), 0);
        // 法杖照旧到 165
        let (staff, u) = step(&l, &wrec_at(5, 7, [110.0, 0.0, 0.0, 0.0, 0.0]), u32::MAX, &o).unwrap();
        let Recipe::W { cor, .. } = &staff.recipe else { panic!() };
        assert_eq!((cor[0], u), (165.0, 69));
    }

    /// 武器：每颗各项加 (165 − 125) ÷ 50 = 0.8，各自到 165 为止；补正 110 到顶要 69 颗；到顶后不能再用；标上超限过
    #[test]
    fn weapon_steps() {
        let l = lib();
        let r = wrec([110.0, 145.0, 0.0, 0.0, 0.0]);
        assert_eq!(need(&l, &r, &O50), 69);
        let (n1, u) = step(&l, &r, 1, &O50).unwrap();
        assert_eq!(u, 1);
        let Recipe::W { cor, ovl, .. } = n1.recipe else { panic!() };
        assert!((cor[0] - 110.8).abs() < 1e-4 && (cor[1] - 145.8).abs() < 1e-4 && cor[2] == 0.0 && ovl);
        let (top, u) = step(&l, &r, u32::MAX, &O50).unwrap();
        assert_eq!(u, 69);
        let Recipe::W { cor, .. } = &top.recipe else { panic!() };
        assert_eq!((cor[0], cor[1]), (165.0, 165.0));
        assert!(step(&l, &top, 1, &O50).is_none());
        assert_eq!(rec_parse(&rec_line(&top)), Some(top.clone())); // 记录里存得下「超限过」
        assert_eq!(rec_parse(&rec_line(&r)).map(|x| x.recipe), Some(r.recipe.clone())); // 没超限的格式不变
        // 全能按五项的上限
        assert_eq!(cap_w(&l, 3, &[60.0; 5]), Some((60.0, 72.0, 79.2)));
    }

    /// 防具：没存倍率时从按记录算的那个数起；每颗 (2.16 − 1.7) ÷ 50；存进记录、读回一样；继续用从存的那个数起
    #[test]
    fn armor_steps() {
        let l = lib();
        let r = Rec { cat: 1, idx: 7, tier: 3, recipe: Recipe::P { base: 470200, sps: vec![(7210425, "dr_bulwark".into())], mult: None, pos: Vec::new() } };
        let m0 = armor_now(&l, &r).unwrap();
        assert!((1.6..=1.8).contains(&m0));
        let (r1, u) = step(&l, &r, 10, &O50).unwrap();
        assert_eq!(u, 10);
        let m1 = armor_now(&l, &r1).unwrap();
        assert!((m1 - (m0 + 0.092)).abs() < 1e-9, "{m0} {m1}");
        assert_eq!(rec_parse(&rec_line(&r1)).and_then(|x| armor_now(&l, &x)).map(|m| (m - m1).abs() < 1e-9), Some(true));
        let (top, _) = step(&l, &r1, u32::MAX, &O50).unwrap();
        assert_eq!(armor_now(&l, &top), Some(2.16));
        assert_eq!(need(&l, &top, &O50), 0);
    }

    /// 防具词条升一档：效果编号换成下一档的；减伤倍率先定住（换了效果编号也不变）；跳过词条库里没有的档；传说不能再升；武器不行；颗数 1 / 2 / 3
    #[test]
    fn affix_upgrade() {
        let mut l = lib();
        let fam = |key: &str, sps: [Option<i32>; 4]| Fam {
            key: key.into(),
            armor_w: [0; 4],
            tal_w: [0; 4],
            suffix: [key.into(), key.into()],
            r: sps.map(|sp| sp.map(|sp| FamR { sp, tal: 0, text: [String::new(), String::new()], val: None })),
            slots: 15,
            mech: false,
            group: String::new(),
        };
        l.fams = vec![fam("a", [Some(100), Some(101), Some(102), Some(103)]), fam("b", [Some(200), None, Some(202), Some(203)])];
        l.fam_by_key = l.fams.iter().enumerate().map(|(i, f)| (f.key.clone(), i)).collect();
        let r = Rec { cat: 1, idx: 7, tier: 3, recipe: Recipe::P { base: 470200, sps: vec![(100, "a".into()), (200, "b".into()), (103, "a".into())], mult: None, pos: Vec::new() } };
        let m0 = armor_now(&l, &r).unwrap();
        let (n0, from, to) = affix_up(&l, &r, 0).unwrap();
        assert_eq!((from, to), (0, 1));
        let Recipe::P { sps, mult, .. } = &n0.recipe else { panic!() };
        assert_eq!(sps[0], (101, "a".to_string()));
        assert_eq!(*mult, Some(m0));
        assert_eq!(armor_now(&l, &n0), Some(m0));
        assert_eq!(affix_up(&l, &r, 1).map(|x| (x.1, x.2)), Ok((0, 2))); // 稀有没有，直接到史诗
        assert!(affix_up(&l, &r, 2).is_err()); // 已经传说
        assert!(affix_up(&l, &r, 3).is_err());
        assert_eq!(rec_parse(&rec_line(&n0)), Some(n0.clone()));
        assert!(affix_up(&l, &wrec([100.0, 0.0, 0.0, 0.0, 0.0]), 0).is_err());
        assert_eq!([1, 2, 3].map(affix_cost), [1, 2, 3]);
    }
}
