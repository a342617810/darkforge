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
from sc import arena, avatarfix, bells, clergyfix, bossarena, bossaward, bossmods, darkshop, difficulty, extragrace, forge, grace, gracelook, guide, hks, identify, inherit, lock, lostarena, runebank, sell, slot, story, sounds, start, training, twin, wish, wishstone, wspages, notes, varrefix  # noqa: E402
from sc.common import LANGS, SETTINGS, TALK, Ctx, last_with, vanilla  # noqa: E402
from sc.esdutil import ROOT, dup_picks, write_check  # noqa: E402

VERSION = 'scripts-1'
SIG_FILE = 'scripts_source.txt'
MAPS_FILE = 'scripts_maps.txt'      # 做这个包时各来源包里的地图 / 事件脚本（maps_sig）：这次做不成时比它，变了就不沿用旧包
# 赐福菜单里加选项的顺序就是这里的顺序（难度 → 一键鉴定 → 许愿 → 一键出售 → DR 说明 → 暗黑商店 → 双子老妪）
FEATURES = (grace, difficulty, identify, wish, inherit, wspages, wishstone, runebank, notes, sounds, sell, guide, darkshop, forge, twin, lock, slot, start, hks, bells, training, extragrace, bossarena, avatarfix, clergyfix, bossaward, bossmods, arena, story, lostarena, varrefix, gracelook)   # forge 要在登记进「暗黑重铸」的功能之后，gracelook 最后；lostarena 在改地图的那几个（extragrace、bossarena、avatarfix、arena、story）之后，接着它们改好的那份补


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


def maps_sig(sources):
    """各来源包里的地图和事件脚本（map\\mapstudio\\*.msb.dcx、event\\*.emevd.dcx）：路径、大小、修改时间（只看文件信息，几百张图也很快）。
    覆盖包里整张的地图 / 事件是在这些上面改的，地图里敌人引用的敌人参数编号（重随复制出来的那几行，rr/stage3.py）随机器输出一变就整体移位：
    来源变了还沿用旧包，敌人引用缺行或错行（崩溃风险审查 2026-11-19 第 6 条）。重随只重写变了的地图，随机器只在重新随机化时写，
    所以修改时间变了基本就是内容变了；误判也只是这次不沿用"""
    h = hashlib.sha1(b'maps-1')
    for s in sources:
        for pat in (('map', 'mapstudio', '*.msb.dcx'), ('event', '*.emevd.dcx')):
            for p in sorted(glob.glob(os.path.join(s, *pat))):
                st = os.stat(p)
                h.update(('%s|%d|%d;' % (os.path.abspath(p).lower(), st.st_size, st.st_mtime_ns)).encode('utf-8'))
    return h.hexdigest()


def old_usable(sources, out):
    """这次做不成时能不能沿用上次的包：（能不能, 不能的原因）。上次的包要完整（有签名文件），而且来源里的地图 / 事件脚本和做它的时候一样"""
    if not os.path.isfile(os.path.join(out, SIG_FILE)):
        return False, ''
    mf = os.path.join(out, MAPS_FILE)
    try:
        same = os.path.isfile(mf) and open(mf, encoding='utf-8').read().strip() == maps_sig(sources)
    except OSError:
        same = False
    if not same:
        return False, '；上次的包是按另一份地图做的（重新随机化过，或者别的包换了地图），不能沿用'
    return True, ''


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
        # 内容没变但文件信息变了（同样的内容重写过）：记下现在的，免得以后做不成时误判成来源变了
        try:
            ms, mf = maps_sig(sources), os.path.join(out, MAPS_FILE)
            if not (os.path.isfile(mf) and open(mf, encoding='utf-8').read().strip() == ms):
                with open(mf + '.tmp', 'w', encoding='utf-8') as f:
                    f.write(ms + '\n')
                os.replace(mf + '.tmp', mf)
        except OSError:
            pass                                    # 记不下只是以后做不成时不沿用
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

    open(os.path.join(tmp, MAPS_FILE), 'w', encoding='utf-8').write(maps_sig(sources) + '\n')
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
    # dark_core 的定义文件目录（斗技场换阵容要改 arena.txt 的部件行、记轮到第几批）；副本测试改到副本里。
    # 不给：只有输出是本体的 out\ 下（启动器）才写本体的 dll\dark_core，别处的（副本测试没给）不换阵容，
    # 免得副本的 arena.txt 盖掉本体的（2026-11-19 别的会话的副本重随把本体的 arena.txt 换成了副本那份）
    ap.add_argument('--core-dir', default=None)
    a = ap.parse_args()
    if a.core_dir is None:
        root = os.path.normcase(os.path.abspath(os.path.dirname(os.path.dirname(HERE))))
        out = os.path.normcase(os.path.abspath(a.out))
        if out.startswith(os.path.join(root, 'out') + os.sep):
            a.core_dir = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'dll', 'dark_core')
    erlib.DLL_DIRS.extend(a.dll_dir)
    sources = [s for s in a.sources if os.path.isdir(s)]
    try:
        r = {'ok': True, 'msg': build(sources, a.out)}
    except Exception as e:
        err = '%s: %s' % (type(e).__name__, e)
        # 覆盖包只会是完整的旧包或完整的新包（签名文件最后写、整个目录换上去）：有上次的、而且来源的地图没变就接着用
        usable, why = old_usable(sources, a.out)
        if usable:
            r = {'ok': True, 'warn': True, 'msg': '这次没做成，沿用上次的结果（%s）' % err}
        else:
            r = {'ok': False, 'msg': err + why}
    if r['ok'] and a.core_dir:
        # 斗技场每次启动换一批阵容（sc/arena.py pick；联机启动的覆盖包目录是 scripts_coop…，按日期选，两台电脑一样）。
        # 换不成照样启动，用覆盖包里原样的那一批
        try:
            coop = os.path.basename(os.path.normpath(a.out)).lower().startswith('scripts_coop')
            note = arena.pick(a.out, a.core_dir, coop=coop)
            if note:
                r['msg'] += '；' + note
        except Exception as e:
            r['msg'] += '；斗技场换阵容没做成，用上次那一批（%s: %s）' % (type(e).__name__, e)
    print(json.dumps(r, ensure_ascii=True))


if __name__ == '__main__':
    main()
