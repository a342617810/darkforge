# -*- coding: utf-8 -*-
"""敌人（和 NPC 人形）攻击动作的攻击判定时间段（见切按判定算，用户 2026-11-11「见切的判定时间有点过于宽松了」→「用出招判定帧」）：
游戏目录各个包（Data0~3、DLC）里每个角色模型的动作包 chr\\cXXXX.anibnd.dcx（还有 _div00~03 分包）的 TAE，
每个动画里攻击行为事件（TAE 类型 1：刀刃 / 身体的判定出现的时间段，开始、结束都是秒，动作自己的播放时间，和 dark_core 读到的 play_time 同一套）。
  - 一个动画几个攻击行为就记几段（连招一个动画里几刀），重叠的合并；
  - 自己一个事件都没有、mini 头是「导入别的动画」（类型 1，+0x18 导入的完整编号）的，顺着导入的找；
  - 子弹行为（类型 2）不记：见切对子弹看场上子弹的真实位置（rules.rs mikiri_reason），比时间准；
  - 动作编号：敌人的 TAE 文件（cXXXX.tae）里存的就是完整编号（如 1003029，和游戏里一样）；玩家模型 c0000 的分段文件 aXXX.tae 里存的是段内编号，
    完整 = 段 × 1000000 + 段内（同 build_hit_windows.py）。c0000 是人形 NPC（入侵者、褪色者 NPC 等）用的，也记。
输出 launcher\\reroll\\data\\foe_windows.txt：「m 模型号」一行开始一个模型，之后每行「动作编号 开始,结束[;开始,结束…]」。
rr/affixes.py foewin_lines 在有见切规则时写成 dll\\dark_core\\foewin.txt，积木引擎的 mikiri_reason 按它判断「这一刻敌人的攻击判定在不在」。
Boss 模组（用户 2026-11-12「这是我们整合进来的boss出招 这个也要加进来」：梅瑟莫模组的 c5130 出招 43000 原版表里没有）：
  launcher\\reroll\\data\\bossmods\\<键>\\files\\chr\\ 里带的动作包照游戏的挂法算（模组带了的那个分包用模组的，没带的分包照原版），
  写进同目录的 bossmods\\<键>\\foe_windows.txt（只有模组带了动作包的模型）；重随时这次加载的模组整块盖掉原版表里同一个模型。
游戏里模型号是 ChrIns.character_id；自己没有动作包的变体模型（如 c4301）DLL 退到同系列的基础模型（个位、十位清零）。游戏更新改了动作要重跑。
用法：launcher\\python\\python.exe -X utf8 dev\\item_system\\build_foe_windows.py [--mods]（只读游戏的包；包的公钥在本目录 keys\\）；
--mods 只重做 Boss 模组的表（原版表不动，快）。换了 / 更新了 Boss 模组要重跑。"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
RR = os.path.join(PALY, 'launcher', 'reroll')
sys.path.insert(0, RR)
import erlib  # noqa: E402

GAME = os.path.dirname(PALY)
erlib.DLL_DIRS = [os.path.join(PALY, 'randomizer'), GAME]
OUT = os.path.join(RR, 'data', 'foe_windows.txt')
KEYS = os.path.join(HERE, 'keys')
ARCHIVES = ('Data0', 'Data1', 'Data2', 'Data3', 'DLC')
SUFFIXES = ('',) + tuple('_div%02d' % k for k in range(10))   # 分包（拉卡德的模组带到 _div05）
BOSSMODS = os.path.join(RR, 'data', 'bossmods')
ATTACK_EVENT = 1
IMPORT = 1


def read_tae(b, sec):
    """一个 TAE 文件 → {完整动画编号: (攻击行为时间段列表, 事件数, 导入的动画)}；sec = None：文件里存的就是完整编号"""
    if b[:4] != b'TAE ' or b[7] != 0xFF:
        raise ValueError('不是 64 位 TAE')
    q = lambda o: struct.unpack_from('<q', b, o)[0]
    i32 = lambda o: struct.unpack_from('<i', b, o)[0]
    f32 = lambda o: struct.unpack_from('<f', b, o)[0]
    out = {}
    n_anim, anims_off = i32(0x54), q(0x58)
    for k in range(n_anim):
        aid, aoff = q(anims_off + k * 16), q(anims_off + k * 16 + 8)
        ev_off, n_ev = q(aoff), i32(aoff + 32)
        mini = q(aoff + 24)
        imp = i32(mini + 0x18) if i32(mini) == IMPORT else None
        spans = []
        for e in range(n_ev):
            h = ev_off + e * 24
            if i32(q(h + 16)) == ATTACK_EVENT:
                t0, t1 = f32(q(h)), f32(q(h + 8))
                if t1 > t0:
                    spans.append((t0, t1))
        full = aid if sec is None else sec * 1000000 + aid
        out[full] = (spans, n_ev, imp)
    return out


def merged(spans):
    out = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1] + 1e-4:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def windows(info, a, depth=0):
    v = info.get(a)
    if v is None or depth > 8:
        return []
    spans, n_ev, imp = v
    if spans:
        return merged(spans)
    if n_ev == 0 and imp:
        return windows(info, imp, depth + 1)
    return []


def tae_info(m, raws):
    """一个模型的动作包（[(分包后缀, 解压后的 anibnd)]，同一个后缀后面的盖前面的）→ {动画编号: (攻击时间段, 事件数, 导入)}"""
    info = {}
    for suf, raw in raws:
        bnd = erlib.Bnd4(raw)
        for name in bnd.entries:
            base = name.replace('\\', '/').split('/')[-1].lower()
            if not base.endswith('.tae'):
                continue
            # 分段文件 aXXX.tae 存的是段内编号；cXXXX.tae（敌人）存的是完整编号
            sec = int(base[1:-4]) if base.startswith('a') and base[1:-4].isdigit() else None
            if m == 0 and sec is None:
                continue        # c0000 只认分段的（别的包里的旧 c0000.tae 编号会和分段的撞）
            try:
                info.update(read_tae(bnd.get(name), sec))
            except (ValueError, struct.error) as e:
                print('  c%04d%s %s 读不了：%s' % (m, suf, name, e))
    return info


def rows_of(info):
    rows = []
    for a in sorted(info):
        w = windows(info, a)
        if w:
            rows.append('%d %s' % (a, ';'.join('%.3f,%.3f' % x for x in w)))
    return rows


def mod_anibnds():
    """{模组键: {模型号: {分包后缀: 文件路径}}}：bossmods\\<键>\\files\\chr\\cXXXX[_divNN].anibnd.dcx"""
    out = {}
    for k in sorted(os.listdir(BOSSMODS)):
        d = os.path.join(BOSSMODS, k, 'files', 'chr')
        if k.startswith('_') or not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            low = fn.lower()
            if not (low.startswith('c') and low.endswith('.anibnd.dcx')):
                continue
            stem = low[:-len('.anibnd.dcx')]
            m, suf = (stem[1:5], stem[5:])
            if not m.isdigit() or suf not in SUFFIXES:
                print('  模组 %s：认不出的动作包 %s，跳过' % (k, fn))
                continue
            out.setdefault(k, {}).setdefault(int(m), {})[suf] = os.path.join(d, fn)
    return out


def main():
    mods_only = '--mods' in sys.argv[1:]
    t0 = time.time()
    arcs = []
    for n in ARCHIVES:
        bhd = os.path.join(GAME, n + '.bhd')
        key = os.path.join(KEYS, n + '_key.pem')
        if os.path.isfile(bhd) and os.path.isfile(key):
            arcs.append(erlib.GameArchive(bhd, open(key, encoding='ascii').read()))

    def rd(p):
        """每个包里的这个文件都读（同名的可能不止一个包有，比如 c0000：分段的 aXXX.tae 在 Data3）"""
        out = []
        for a in arcs:
            try:
                d = a.read(p)
            except Exception:
                d = None
            if d:
                out.append(erlib.dcx_decompress(d))
        return out

    def vanilla(m):
        return [(suf, raw) for suf in SUFFIXES for raw in rd('/chr/c%04d%s.anibnd.dcx' % (m, suf))]

    if not mods_only:
        lines = ['# 敌人攻击动作的攻击判定时间段（dev/item_system/build_foe_windows.py 从游戏包的 chr\\cXXXX.anibnd 生成，TAE 攻击行为事件）：'
                 '「m 模型号」开始一个模型，之后「动作编号 开始,结束[;开始,结束…]」（秒）。见切用']
        n_mdl = n_anim = 0
        for m in range(10000):
            rows = rows_of(tae_info(m, vanilla(m)))
            if rows:
                n_mdl += 1
                n_anim += len(rows)
                lines.append('m %d' % m)
                lines += rows
            if m % 1000 == 999:
                print('  扫到 c%04d：%d 个模型、%d 个攻击动作（%.0f 秒）' % (m, n_mdl, n_anim, time.time() - t0), flush=True)
        open(OUT, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
        print('写好 %s：%d 个模型、%d 个攻击动作（%.0f 秒）' % (OUT, n_mdl, n_anim, time.time() - t0))

    # Boss 模组：模组带了的分包用模组的（游戏里模组那层盖在原版上面），没带的照原版
    for k, models in mod_anibnds().items():
        lines = ['# Boss 模组 %s 的动作包算出来的攻击判定时间段（dev/item_system/build_foe_windows.py）：格式同 data\\foe_windows.txt；'
                 '重随加载这个模组时整块盖掉原版表里同一个模型' % k]
        notes = []
        for m, files in sorted(models.items()):
            van = vanilla(m)
            raws = [(suf, raw) for suf, raw in van if suf not in files] + \
                   [(suf, erlib.dcx_decompress(open(files[suf], 'rb').read())) for suf in SUFFIXES if suf in files]
            base = rows_of(tae_info(m, van))
            rows = rows_of(tae_info(m, raws))
            if rows:
                lines.append('m %d' % m)
                lines += rows
            added = len({r.split()[0] for r in rows} - {r.split()[0] for r in base})
            notes.append('c%04d %d 个攻击动作（原版 %d，模组新加的动作 %d 个）' % (m, len(rows), len(base), added))
        out = os.path.join(BOSSMODS, k, 'foe_windows.txt')
        open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
        print('模组 %s：%s' % (k, '，'.join(notes)))
    print('完成（%.0f 秒）' % (time.time() - t0))


if __name__ == '__main__':
    main()
