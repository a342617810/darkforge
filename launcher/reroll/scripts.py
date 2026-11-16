# -*- coding: utf-8 -*-
"""游戏脚本覆盖包（以前叫 bossres）：赐福对话脚本、菜单文字、公共事件、玩家 / 灵马脚本、商人对话、圆桌地图，
按 YAFSML [mod] 的加载顺序取最后生效的那份（没有就用随机器自带的原版）改好，写到覆盖包目录（YAFSML 最后加载）；来源没变就不重写。
各功能在 sc/ 下按模块分开（接口见 sc/__init__.py），这里只负责：找来源 → 按顺序调用各功能 → 写出、换上覆盖包。

用法（由启动器调用）：scripts.py --sources <目录1> <目录2> ... --out <覆盖包目录> --dll-dir <有 oo2core 的目录>
最后一行输出 JSON：{"ok": true/false, "msg": ..., "warn": 可选}"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import emevd  # noqa: E402
import erlib  # noqa: E402
import esd  # noqa: E402
from sc import arena, avatarfix, bells, bossarena, bossaward, bossmods, darkshop, difficulty, extragrace, forge, grace, gracelook, guide, hks, identify, inherit, lock, lostarena, runebank, sell, slot, story, sounds, start, training, twin, wish, wishstone, wspages, notes  # noqa: E402
from sc.common import LANGS, SETTINGS, TALK, Ctx, last_with, vanilla  # noqa: E402
from sc.esdutil import ROOT, dup_picks, write_check  # noqa: E402

VERSION = 'scripts-1'
SIG_FILE = 'scripts_source.txt'
# 赐福菜单里加选项的顺序就是这里的顺序（难度 → 一键鉴定 → 许愿 → 一键出售 → DR 说明 → 暗黑商店 → 双子老妪）
FEATURES = (grace, difficulty, identify, wish, inherit, wspages, wishstone, runebank, notes, sounds, sell, guide, darkshop, forge, twin, lock, slot, start, hks, bells, training, extragrace, bossarena, avatarfix, bossaward, bossmods, arena, story, lostarena, gracelook)   # forge 要在登记进「暗黑重铸」的功能之后，gracelook 最后；lostarena 在改地图的那几个（extragrace、bossarena、avatarfix、arena、story）之后，接着它们改好的那份补


NO_SYNC = {'bank': 2000, 'id': 2, 'args': b'\0\0\0\0', 'layer': None}     # Set Network Sync State(Disabled)


def no_network_sync(e, base_ids):
    """联机（联机计划 13.3 C6）：整合包往公共事件脚本里加的事件（发货、难度、提示、音效、开局、Boss 奖励、斗技场传送）都只管自己，
    开头关掉网络同步：照原版公共事件 710 / 711 / 740 等第一条的 2000[2] 参数 0（原版 569 处里 0 占绝大多数、多半在第一条）。
    不然 Seamless 联机时事件里点亮 / 熄灭的标记会同步给队友（黄金树爬塔实测：房主开过的宝箱客机只能开到空的）。
    插在第一条，参数替换表按指令序号记的要跟着 +1；已经是这条开头的不重复加。返回加了几个"""
    n = 0
    for ev in e['events']:
        if ev['id'] in base_ids or (ev['ins'] and (ev['ins'][0]['bank'], ev['ins'][0]['id']) == (2000, 2)):
            continue
        ev['ins'].insert(0, dict(NO_SYNC))
        ev['params'] = [(p[0] + 1,) + tuple(p[1:]) for p in ev['params']]
        n += 1
    return n


def sig_of(cx, paths):
    h = hashlib.sha1(VERSION.encode())
    code = sorted(glob.glob(os.path.join(HERE, 'sc', '*.py'))) + [os.path.join(HERE, f) for f in ('emevd.py', 'esd.py', 'erlib.py')] + [os.path.abspath(__file__), SETTINGS]
    # 都按内容算：完整重随会重写重随包里的文件（修改时间变了，内容多半没变），不用跟着重做（用户 2026-11-05「只重做需要的部分」）
    for p in paths + code + [cx.features_file]:
        if p and os.path.isfile(p):
            h.update(('%s|%s;' % (os.path.abspath(p), hashlib.sha1(open(p, 'rb').read()).hexdigest())).encode())
    return h.hexdigest()


def build(sources, out):
    cx = Ctx(sources)
    talk = last_with(sources, TALK)
    talk_from = os.path.dirname(os.path.dirname(os.path.dirname(talk))) if talk else '原版'
    talk = talk or vanilla(TALK)
    if not talk:
        raise RuntimeError('找不到赐福对话脚本（加载的包里没有，随机器自带的原版也没有）')
    menus = {lang: last_with(sources, os.path.join('msg', lang, 'menu_dlc02.msgbnd.dcx'))
             or vanilla(os.path.join('msg', lang, 'menu_dlc02.msgbnd.dcx')) for lang, _ in LANGS}
    srcs = [talk, cx.common] + [p for p in menus.values() if p]
    for m in FEATURES:
        if hasattr(m, 'sources'):
            srcs += m.sources(cx)
    sig = sig_of(cx, srcs)
    sigf = os.path.join(out, SIG_FILE)
    if os.path.isfile(sigf) and open(sigf, encoding='utf-8').read().strip() == sig:
        return '来源没变，沿用上次的结果'
    tmp = out + '.tmp'
    if os.path.isdir(tmp):
        retry(shutil.rmtree, tmp)
    os.makedirs(tmp)

    # 赐福对话脚本：先合并「更多选项」，再让各功能往里加
    bnd = erlib.Bnd4(erlib.dcx_decompress(open(talk, 'rb').read()))
    name = next(n for n in bnd.entries if n.lower().endswith('t000001000.esd'))
    merged, n_grp, remap = grace.merge(esd.read(bytes(bnd.get(name))))
    cx.root = remap.get(ROOT, ROOT)
    dup0 = dup_picks(merged['groups'])
    for m in FEATURES:
        if hasattr(m, 'esd'):
            m.esd(cx, merged['groups'])
    # 菜单选项编号撞了（卢恩银行以前用 41，和原版「开始第 N 次的世界」撞了，通关后点它进下一周目，用户 2026-11-13）
    dup = sorted(dup_picks(merged['groups']) - dup0)
    if dup:
        raise RuntimeError('赐福菜单里选项编号撞了（组, 状态, 编号）：%s' % dup)
    bnd.put(name, write_check(merged))
    os.makedirs(os.path.join(tmp, os.path.dirname(TALK)))
    erlib.write_dcx_file(os.path.join(tmp, TALK), bytes(bnd.data))

    # 菜单文字：各功能给的 {FMG 名字结尾: {编号: 文字}} 合进 menu_dlc02
    for lang, key in LANGS:
        if not menus[lang]:
            continue
        add = {}
        for m in FEATURES:
            if hasattr(m, 'texts'):
                for fmg, rows in m.texts(cx, key).items():
                    add.setdefault(fmg, {}).update(rows)
        mb = erlib.Bnd4(erlib.dcx_decompress(open(menus[lang], 'rb').read()))
        # 合好之后再改样式（sc/gracelook.py 加图标、上色）：要看别的功能给的文字和包里原有的对话文字（DLC 的表盖前面的）
        talk = {}
        for x in sorted(mb.entries, key=lambda x: re.split(r'[\\/]', x)[-1]):
            if re.fullmatch(r'EventTextForTalk(_dlc\d+)?\.fmg', re.split(r'[\\/]', x)[-1]):
                talk.update((tid, t) for tid, t in erlib.read_fmg_full(mb.get(x))[1] if t is not None)
        for m in FEATURES:
            if hasattr(m, 'restyle'):
                m.restyle(cx, key, add, talk.get)
        for fmg, rows in add.items():
            f = next(x for x in mb.entries if re.split(r'[\\/]', x)[-1] == fmg + '.fmg')
            hdr, ents = erlib.read_fmg_full(mb.get(f))
            rows = dict(rows)
            ents = [(tid, rows.pop(tid, t)) for tid, t in ents] + sorted(rows.items())
            mb.put(f, erlib.write_fmg(hdr, sorted(ents)))
        os.makedirs(os.path.join(tmp, 'msg', lang))
        erlib.write_dcx_file(os.path.join(tmp, 'msg', lang, 'menu_dlc02.msgbnd.dcx'), bytes(mb.data))

    # 公共事件脚本
    if cx.common:
        e = emevd.read(erlib.dcx_decompress(open(cx.common, 'rb').read()))
        ev0 = next(ev for ev in e['events'] if ev['id'] == 0)
        n_ev = len(e['events'])
        base_ids = {ev['id'] for ev in e['events']}
        for m in FEATURES:
            if hasattr(m, 'events'):
                m.events(cx, e, ev0)
        no_network_sync(e, base_ids)
        if len(e['events']) != n_ev:
            os.makedirs(os.path.join(tmp, 'event'), exist_ok=True)
            open(os.path.join(tmp, 'event', 'common.emevd.dcx'), 'wb').write(erlib.dcx_compress_dflt(emevd.write(e), level=6))

    # 其他文件（玩家 / 灵马脚本、商人对话、圆桌地图）
    for m in FEATURES:
        if hasattr(m, 'files'):
            m.files(cx, tmp)

    open(os.path.join(tmp, SIG_FILE), 'w', encoding='utf-8').write(sig + getattr(cx, 'sig_extra', '') + '\n')
    swap_in(tmp, out)
    problems = ''.join('；' + p for p in cx.notes if any(k in p for k in ('没', '失败', '跳过')))
    return '已合并（%d 个状态机；赐福脚本来自 %s%s）' % (n_grp, talk_from, problems)


def retry(fn, *a, tries=10):
    """刚写完的文件常被杀毒软件扫描占着，删除 / 目录改名会「拒绝访问」，等一会儿再试"""
    for i in range(tries):
        try:
            return fn(*a)
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(0.5)


def swap_in(tmp, out):
    """新做的覆盖包换上去。旧包在新包放好之前不删：2026-10-24 两次改名被拒绝，旧包已经删了，整个覆盖包都没加载"""
    old = out + '.old'
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(out):
        retry(os.replace, out, old)          # 挪不开就报错，旧包原样留着
    try:
        try:
            retry(os.replace, tmp, out)
        except OSError:
            shutil.copytree(tmp, out)        # 目录改名一直被拒绝就复制一份（读文件不受影响）
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        if os.path.isdir(old):
            retry(os.replace, old, out)      # 把旧包放回去
        raise
    shutil.rmtree(old, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sources', nargs='+', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--dll-dir', action='append', default=[])
    a = ap.parse_args()
    erlib.DLL_DIRS.extend(a.dll_dir)
    try:
        r = {'ok': True, 'msg': build([s for s in a.sources if os.path.isdir(s)], a.out)}
    except Exception as e:
        err = '%s: %s' % (type(e).__name__, e)
        # 覆盖包只会是完整的旧包或完整的新包（签名文件最后写、整个目录换上去）：有上次的就接着用
        if os.path.isfile(os.path.join(a.out, SIG_FILE)):
            r = {'ok': True, 'warn': True, 'msg': '这次没做成，沿用上次的结果（%s）' % err}
        else:
            r = {'ok': False, 'msg': err}
    print(json.dumps(r, ensure_ascii=True))


if __name__ == '__main__':
    main()
