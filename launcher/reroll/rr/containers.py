# -*- coding: utf-8 -*-
"""容器（新装备系统阶段 1，设计文档 8.5 / 8.6）：鉴定时 dark_core 把生成的装备写进去的空白参数行，加上发货掉落表。

每个容器 = 一行参数 + 名字 / 简介 / 说明三段文字占位（中英文字包各一份）：
  - 武器 W0 起，每个占 1 万个编号（末四位是质变 × 100 + 强化等级；物品编号只有 28 位，W0 起只放得下 W_SEG1 个）；
    再多的放第二段 W2 起（用户 2026-10-30 扩到 3000；第一段的编号不能挪，已经拿到的生成武器就是这些编号），到开局装备编号段为止；
  - 防具 P0 起每个占 100；护符 A0 起每个一个；数量在 settings.json 的 containers（一个角色同时能拿着的上限，背包 + 仓库）。
  - 行先照一件原版装备复制（DLL 没工作时就是它）；跟编号绑定、改写时要留容器自己的字段：武器的 originEquipWep*（各强化等级的原武器编号）。
  - 文字占位开头「#DRC<编号>#<N/I/C>」，后面补空格到固定长度 CAP；DLL 在内存里找到后原地改写（长度不能超）。
发货（8.6）：地图掉落表 DELIVER_LOT 起连续 DELIVER_ROWS 行（前后各空一个号，免得别的表连过来），重随写成空的；
  DLL 改成这批容器 + 点亮 DELIVER_FLAG，公共事件（sc/identify.py）发这串表再熄灭标记。
给 dark_core 的定义写在 dll\\dark_core\\items.txt（write_def）。"""
from .common import *  # noqa: F401,F403
from .unidentified import CATS, TIERS, goods_id

W0, W_STEP = 240000000, 10000
W_SEG1 = (0x10000000 - 26 - W0) // W_STEP + 1   # 第一段能放几个（最后一个 +25 强化也不超过 28 位）：2843
W2 = 200000000                                 # 第二段：到开局装备编号段（startgear.START_W0 = 230000000）为止，最多 3000 个
P0, P_STEP = 30000000, 100
A0, A_STEP = 20000, 1
W_DONOR, A_DONOR = 1000000, 1000              # 短剑、赤琥珀链坠（没被改写时的样子）
CAP = {'N': 192, 'I': 160, 'C': 1280}          # 占位长度（字数）：名字带稀有度颜色、前缀 + 两个后缀（英文最坏约 160 字）；说明最多三条词条（2026-10-31 英文最长的三条约 830 字，
                                               # 每行再包一层稀有度颜色 29 字，最长的词条 5 行 → 最坏约 1091；触发词条再加一行补正提示（rr/procs.py）→ 最坏约 1231；
                                               # 中文约 608。dark_core 的测试 generate_from_real_library 算最坏情况）
FMG = {'w': 'Weapon', 'p': 'Protector', 'a': 'Accessory'}
FIELD = {'N': 'Name', 'I': 'Info', 'C': 'Caption'}
LABEL = {'zh': '装备的文字没有显示出来，请用启动器重新启动游戏', 'en': 'Gear text did not load. Please restart the game from the launcher.'}   # 只在 dark_core 没改写时看得到；DLL 靠它分中英文，两种开头要不同
LANGS = (('zh', 'zhocn'), ('en', 'engus'))
DELIVER_ROWS, DELIVER_FROM = 32, 10900         # 发货表：一次最多 32 件；从 10900 起找连续空号
DELIVER_FLAG, IDENTIFY_FLAG = 93501, 93502     # 发货（DLL 点亮、公共事件发完熄灭）、一键鉴定请求（赐福菜单点亮、DLL 处理完熄灭）
DEFAULT_N = {'weapon': 3000, 'armor': 6000, 'talisman': 600}
# 定向鉴定（用户 2026-11-03）：赐福「暗黑重铸」→「鉴定」里选武器类型、稀有度，每件 directed_identify.cost 卢恩（sc/identify.py、dark_core gear.rs）。
# 请求标记；类型序号写进 6 位、稀有度写进 3 位（0~4 = 普通 / 稀有 / 史诗 / 传说 / 传说（幽影之地），5 = 全部）；一件都没鉴定时 DLL 点亮的标记（dev\event_flags\说明.md）
DIR_FLAG, DIR_TYPE0, DIR_TYPE_BITS, DIR_RAR0, DIR_RAR_BITS, DIR_NONE = 93634, 93635, 6, 93641, 3, 93644
DIR_COST = [10, 100, 500, 1000, 2000]          # 每件卢恩，按未鉴定物品的档（用户 2026-11-03）
# 防具 / 护符鉴定（用户 2026-11-09「新加防具鉴定和护符鉴定 防具鉴定可以定向部位 护符鉴定可以定向流派 护符鉴定价格是其他的10倍」）：
# 种类写进 2 位（0 武器 / 1 防具 / 2 护符），序号照旧写进类型那 6 位（防具 = 部位，护符 = 流派序号）；防具同武器的价，护符 × talisman_mult
DIR_KIND0, DIR_KIND_BITS = 93668, 2
DIR_TALISMAN_MULT = 10
ARMOR_SLOTS = [[0, '头部', 'Head'], [1, '身体', 'Chest'], [2, '手部', 'Arms'], [3, '腿部', 'Legs']]    # 部位序号同 dark_core 的 PBase.slot；名字同词条百科（codex.rs CAT_NAME）
# 护符的流派（词条库 affixes.json 的 archetype）：顺序和英文名同词条百科（dev\\dark_ui\\src\\ui\\codex.rs 的 ARCH，后面是不算流派的 GENERIC），
# 改了那边这里一起改（用户 2026-11-09「这里的流派要和词条百科保持一致」）；词条库里有护符词条的才列，没登记的新流派排在流派后面、通用前面
ARCH_EN = [('命中连击', 'Combo'), ('重击处决', 'Heavy & Critical'), ('战技', 'Skills'), ('法术', 'Spells'), ('远程', 'Ranged'),
           ('异常', 'Ailments'), ('防御', 'Guard'), ('闪避', 'Evasion'), ('机动空战', 'Mobility'), ('姿态', 'Stance'), ('反击回血', 'Recovery')]
ARCH_GENERIC = [('属性', 'Attributes'), ('生存', 'Survival'), ('杂项', 'Misc'), ('其他', 'Other')]
# wepType → 游戏里的类型名（中文取 GR_MenuText 600xx，英文照官方）；词条库里能生成、这里有名字的类型才列
WEP_TYPES = {1: ('短剑', 'Dagger'), 3: ('直剑', 'Straight Sword'), 5: ('大剑', 'Greatsword'), 7: ('特大剑', 'Colossal Sword'),
             9: ('曲剑', 'Curved Sword'), 11: ('大曲剑', 'Curved Greatsword'), 13: ('刀', 'Katana'), 14: ('双头剑', 'Twinblade'),
             15: ('刺剑', 'Thrusting Sword'), 16: ('重刺剑', 'Heavy Thrusting Sword'), 17: ('斧', 'Axe'), 19: ('大斧', 'Greataxe'),
             21: ('槌', 'Hammer'), 23: ('大槌', 'Great Hammer'), 24: ('连枷', 'Flail'), 25: ('矛', 'Spear'), 28: ('大矛', 'Great Spear'),
             29: ('戟', 'Halberd'), 31: ('镰刀', 'Reaper'), 35: ('拳头', 'Fist'), 37: ('钩爪', 'Claw'), 39: ('软鞭', 'Whip'),
             41: ('特大武器', 'Colossal Weapon'), 50: ('小弓', 'Light Bow'), 51: ('长弓', 'Bow'), 53: ('大弓', 'Greatbow'),
             55: ('弩', 'Crossbow'), 56: ('弩炮', 'Ballista'), 57: ('手杖', 'Glintstone Staff'), 61: ('圣印记', 'Sacred Seal'),
             65: ('小盾', 'Small Shield'), 67: ('中盾', 'Medium Shield'), 69: ('大盾', 'Greatshield'), 87: ('火把', 'Torch'),
             88: ('格斗术', 'Hand-to-Hand Art'), 89: ('调香瓶', 'Perfume Bottle'), 90: ('突刺盾', 'Thrusting Shield'),
             91: ('投掷剑', 'Throwing Blade'), 92: ('反手剑', 'Backhand Blade'), 93: ('轻大剑', 'Light Greatsword'),
             94: ('大刀', 'Great Katana'), 95: ('兽爪', 'Beast Claw')}


def directed(ctx):
    """定向鉴定的设置：{flag, type0, type_bits, rar0, rar_bits, none, cost, types: [[wepType, 中文, 英文]],
    kind0, kind_bits, slots: [[部位, 中文, 英文]], archs: [[流派, 英文]], tcost}；没开就 None"""
    c = ctx.S.get('directed_identify') or {}
    if not c.get('enabled', True):
        return None
    lib = json.load(open(os.path.join(ctx.data_dir, 'affixes', 'affixes.json'), encoding='utf-8'))
    have = {int(t) for r in lib['weapon']['types'] for t in lib['weapon']['types'][r]}
    types = [[t] + list(WEP_TYPES[t]) for t in sorted(have) if t in WEP_TYPES]
    if not types or len(types) > 1 << DIR_TYPE_BITS:
        return None
    cost = c.get('cost', DIR_COST)
    cost = [int(cost)] * len(TIERS) if isinstance(cost, (int, float)) else [int(x) for x in cost]
    if len(cost) != len(TIERS):
        raise RuntimeError('定向鉴定：directed_identify.cost 要 %d 个数（普通 / 稀有 / 史诗 / 传说 / 传说（幽影之地）），现在 %d 个' % (len(TIERS), len(cost)))
    mult = float(c.get('talisman_mult', DIR_TALISMAN_MULT))
    tcost = [int(round(x * mult)) for x in cost]
    tal = [f for f in lib.get('gear', {}).values() if any(w > 0 for w in (f.get('weight_r') or {}).get('talisman') or [])]
    have = {f.get('archetype') or '其他' for f in tal}
    known = {zh for zh, _ in ARCH_EN + ARCH_GENERIC}
    archs = [[zh, en] for zh, en in ARCH_EN if zh in have] + [[a, a] for a in sorted(have - known)] + \
        [[zh, en] for zh, en in ARCH_GENERIC if zh in have]
    return dict(flag=DIR_FLAG, type0=DIR_TYPE0, type_bits=DIR_TYPE_BITS, rar0=DIR_RAR0, rar_bits=DIR_RAR_BITS, none=DIR_NONE,
                cost=cost, types=types, kind0=DIR_KIND0, kind_bits=DIR_KIND_BITS, slots=ARMOR_SLOTS, archs=archs[:1 << DIR_TYPE_BITS], tcost=tcost)


def w_ids(n):
    """武器容器的编号：第一段 W0 起最多 W_SEG1 个，再多的接第二段 W2 起"""
    return [W0 + k * W_STEP for k in range(min(n, W_SEG1))] + [W2 + k * W_STEP for k in range(max(0, n - W_SEG1))]


def placeholder(cid, field, lang):
    return ('#DRC%d#%s %s' % (cid, field, LABEL[lang])).ljust(CAP[field])


def counts(S):
    c = S.get('containers') or {}
    n = {k: int(c.get(k, v)) for k, v in DEFAULT_N.items()}
    if n['weapon'] > W_SEG1 + (230000000 - W2) // W_STEP:
        raise RuntimeError('容器：武器 %d 个太多（两段编号都放满了，最多 %d 个）' % (n['weapon'], W_SEG1 + (230000000 - W2) // W_STEP))
    return n


def protector_donor(ctx, Pp):
    """防具容器照哪一行复制：编号 10 万起第一件胸甲（protectorCategory = 1）。
    以前是第一行（头盔 100000）：幻化插件 ertransmogrify 给每件防具排的商店格子 = 部位基数（头 4000000、身 4100000、
    手 4200000、腿 4300000，每家 10 万格）+ 编号 // 100，容器 30000000 + 100k 当头盔算出来是 4300000 + k，正好落进腿甲商店、
    按编号后来的盖掉了编号 60 万以下的 47 件原版腿甲（大山羊腿甲、熔炉腿甲、不穿腿甲……，用户 2026-11-16 玩家反馈）。
    当胸甲算是 4400000 + k，超出四家商店，插件不显示也不盖别人。用上的容器 dark_core 读档时照本体整行改写（部位跟着换），
    所以照哪件复制只影响空容器"""
    lay = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'EquipParamProtector.xml')))[0]}
    fc, o = lay['protectorCategory'][1], lay['protectorCategory'][2]
    for i in sorted(Pp.rows):
        if i >= 100000 and struct.unpack_from('<' + fc, Pp.rows[i], o)[0] == 1:
            return i
    raise RuntimeError('容器：EquipParamProtector 里找不到编号 10 万以上的胸甲')


def build(ctx):
    ctx.containers = None
    if not getattr(ctx, 'unid', None):
        return
    n = counts(ctx.S)
    bnd = ctx.bnd
    wf = json.load(open(os.path.join(ctx.data_dir, 'weapon_fields.json'), encoding='utf-8'))
    origin = [(o, sz) for f, o, sz in wf['own'] if f.startswith('originEquipWep')]
    W = erlib.Param(bnd.get('EquipParamWeapon.param'))
    Pp = erlib.Param(bnd.get('EquipParamProtector.param'))
    A = erlib.Param(bnd.get('EquipParamAccessory.param'))
    if W.row_size != wf['row_size'] or W_DONOR not in W.rows or A_DONOR not in A.rows:
        raise RuntimeError('容器：EquipParamWeapon 行大小不对，或缺少原版短剑 / 赤琥珀链坠')
    p_donor = protector_donor(ctx, Pp)
    ids = {'w': w_ids(n['weapon']), 'p': [P0 + k * P_STEP for k in range(n['armor'])],
           'a': [A0 + k * A_STEP for k in range(n['talisman'])]}
    for cat, P, donor in (('w', W, W_DONOR), ('p', Pp, p_donor), ('a', A, A_DONOR)):
        used = [i for i in ids[cat] if i in P.rows]
        if used:
            raise RuntimeError('容器：%s 编号 %s 已被占用' % (FMG[cat], used[:5]))
        for i in ids[cat]:
            row = bytearray(P.rows[donor])
            if cat == 'w':
                for o, sz in origin:
                    if struct.unpack_from('<i', row, o)[0] == donor:
                        struct.pack_into('<i', row, o, i)
            P.add_row(i, bytes(row))
    bnd.put('EquipParamWeapon.param', W.serialize())
    bnd.put('EquipParamProtector.param', Pp.serialize())
    bnd.put('EquipParamAccessory.param', A.serialize())
    # 文字占位
    for lang, code in LANGS:
        mp = os.path.join(ctx.msg_out, code, 'item_dlc02.msgbnd.dcx')
        if not erlib.dcx_exists(mp):
            continue
        mb = erlib.Bnd4(erlib.read_dcx(mp))
        for cat, lst in ids.items():
            for fld, fn in FIELD.items():
                fmg = FMG[cat] + fn + '.fmg'
                hdr, ents = erlib.read_fmg_full(mb.get(fmg))
                d = dict(ents)
                d.update({i: placeholder(i, fld, lang) for i in lst})
                mb.put(fmg, erlib.write_fmg(hdr, sorted(d.items())))
        erlib.write_dcx_file(mp, bytes(mb.data))
    # 发货表：前后各空一个号
    P = ctx.P_mp
    base = DELIVER_FROM
    while any((base + k) in P.rows for k in range(-1, DELIVER_ROWS + 1)):
        base += 100
    tmpl = P.rows[min(P.rows)]
    for k in range(DELIVER_ROWS):
        row = bytearray(tmpl)
        for i in range(8):
            erlib.lot_clear_slot(row, i)
        struct.pack_into('<I', row, erlib.LOT_FLAG, 0)
        P.add_row(base + k, bytes(row))
    keep = ','.join('%d:%d' % x for x in origin)
    ctx.containers = dict(ids=ids, sizes={'w': W.row_size, 'p': Pp.row_size, 'a': A.row_size}, keep={'w': keep, 'p': '', 'a': ''},
                          deliver=base)
    ctx.features['identify'] = {'deliver_lot': base, 'deliver_rows': DELIVER_ROWS, 'deliver_flag': DELIVER_FLAG,
                                'identify_flag': IDENTIFY_FLAG}
    ctx.dirident = directed(ctx)
    if ctx.dirident:
        ctx.features['identify']['dir'] = ctx.dirident
        ctx.report.append('防具鉴定：%d 个部位，每件同武器；护符鉴定：%d 个流派（%s），每件 %s 卢恩' % (
            len(ctx.dirident['slots']), len(ctx.dirident['archs']), '、'.join(a[0] for a in ctx.dirident['archs']), ' / '.join(map(str, ctx.dirident['tcost']))))
        ctx.report.append('定向鉴定：%d 种武器类型，每件 %s 卢恩（请求标记 %d，类型 %d 起 %d 位，稀有度 %d 起 %d 位，没鉴定 %d）' % (
            len(ctx.dirident['types']), ' / '.join(map(str, ctx.dirident['cost'])), DIR_FLAG, DIR_TYPE0, DIR_TYPE_BITS, DIR_RAR0, DIR_RAR_BITS, DIR_NONE))
    seg2 = max(0, n['weapon'] - W_SEG1)
    ctx.report.append('容器：武器 %d（%d 起，每个 1 万号%s）、防具 %d（%d 起）、护符 %d（%d 起），文字占位 %s 字；发货表 %d~%d（标记 %d），'
                      '一键鉴定请求标记 %d；改写、发货要 dll\\dark_core' % (
                          n['weapon'], W0, '；%d 个放第二段 %d 起' % (seg2, W2) if seg2 else '',
                          n['armor'], P0, n['talisman'], A0, '/'.join(str(CAP[f]) for f in 'NIC'),
                          base, base + DELIVER_ROWS - 1, DELIVER_FLAG, IDENTIFY_FLAG))


def sell_list(ctx):
    """一键出售（dll\\dark_sell）认的名单：「类别（0 武器 / 1 防具 / 2 护符）<TAB>编号」，武器写 +0 的编号。就是全部容器"""
    c = getattr(ctx, 'containers', None)
    if not c:
        return []
    return ['%d\t%d' % (k, i) for k, cat in enumerate(('w', 'p', 'a')) for i in c['ids'][cat]]


def add_pool(ctx, srcs, cat, tiers, pct, lot_cat, item_id, n=1, name=''):
    """掉落池（items.txt 的 pool 行，dark_core gear/batch.rs）：srcs 这些来源（identify 一键鉴定 / directed 定向鉴定 / wish 许愿）
    做第 cat 类（0 武器 / 1 防具 / 2 护符）、tiers 这几档（0~4）的东西时，有 pct% 换成这件固定物品（掉落表类别 lot_cat：1 道具 / 2 武器 /
    3 防具 / 4 护符，编号 item_id，n 个）。固定物品不占容器，到了照样扣未鉴定道具。往鉴定 / 许愿里加东西只调这个，不用改 DLL"""
    if pct > 0:
        ctx.unid_pool = getattr(ctx, 'unid_pool', []) + [(','.join(srcs), cat, ','.join(map(str, tiers)), float(pct), lot_cat, item_id, n, name)]


def death_pct(S):
    """死亡惩罚：真死了扣掉背包里未鉴定物品的百分比（settings 的 death_penalty；没写这项按 25，用户 2026-11-19）；0 = 关掉"""
    v = S.get('death_penalty') or {}
    if not v.get('enabled', True):
        return 0
    try:
        return max(0.0, min(100.0, float(v.get('unid_pct', 25))))
    except (TypeError, ValueError):
        return 25.0


def write_def(ctx, path):
    """dark_core 用的定义（一行一项，Tab 分隔）。没有容器就删掉，DLL 看不到这个文件就什么都不做"""
    c = getattr(ctx, 'containers', None)
    if not os.path.isdir(os.path.dirname(path)):
        return
    if not c:
        if os.path.exists(path):
            os.remove(path)
        return
    lines = ['# 新装备系统（dark_core 用，见重随的 rr/containers.py、rr/unidentified.py）。每次重随自动生成，不要手改',
             '# container <类> <第一个编号> <间隔> <个数> <行大小> <改写时留的字段 偏移:长度,...> [<第二段第一个编号> <第二段从第几个起>]  类：w 武器 / p 防具 / a 护符']
    for cat in ('w', 'p', 'a'):
        ids = c['ids'][cat]
        step = (ids[1] - ids[0]) if len(ids) > 1 else 1
        split = next((k for k in range(len(ids)) if ids[k] != ids[0] + k * step), len(ids))
        if any(ids[k] != ids[split] + (k - split) * step for k in range(split, len(ids))):
            raise RuntimeError('容器：%s 的编号不是一段或两段等间隔' % FMG[cat])
        line = ['container', cat, str(ids[0] if ids else 0), str(step), str(len(ids)), str(c['sizes'][cat]), c['keep'][cat]]
        if split < len(ids):
            line += [str(ids[split]), str(split)]
        lines.append('\t'.join(line))
    lines.append('# text <字段 N/I/C> <长度>：占位 = 「#DRC<编号>#<字段> 」+ 说明（label，按语言），补空格到这个长度')
    lines += ['text\t%s\t%d' % (f, CAP[f]) for f in 'NIC']
    lines += ['label\t%s\t%s' % (lang, LABEL[lang]) for lang in ('zh', 'en')]
    lines.append('# goods <类 0 武器 / 1 防具 / 2 护符> <档 0~4：普通 / 稀有 / 史诗 / 传说 / 传说（幽影之地）> <道具编号>')
    lines += ['goods\t%d\t%d\t%d' % (ci, t, goods_id(ci, t)) for ci in range(len(CATS)) for t in range(len(TIERS))]
    di = getattr(ctx, 'dirident', None)
    if di:
        lines.append('# dirident <请求标记> <类型序号的第一个标记> <位数> <稀有度的第一个标记> <位数> <没鉴定标记> <每件卢恩：普通,稀有,史诗,传说,传说（幽影之地）> <类型序号 → wepType,...>：定向鉴定（sc/identify.py）')
        lines.append('# dirident 后四列（用户 2026-11-09）：<种类的第一个标记> <位数> <护符每件卢恩：普通,…> <护符的流派序号 → 名字,…>；防具的序号就是部位 0 头 / 1 身 / 2 手 / 3 腿')
        lines.append('dirident\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s' % (di['flag'], di['type0'], di['type_bits'], di['rar0'], di['rar_bits'], di['none'],
                                                                     ','.join(map(str, di['cost'])), ','.join(str(t[0]) for t in di['types']))
                     + '\t%d\t%d\t%s\t%s' % (di['kind0'], di['kind_bits'], ','.join(map(str, di['tcost'])), ','.join(a[0] for a in di['archs'])))
    dp = death_pct(ctx.S)
    if dp > 0:
        lines.append('# deathloss <几 %>：死亡惩罚（settings 的 death_penalty，用户 2026-11-19），真死了按这个比例随机扣掉背包里的未鉴定物品（gear/deathloss.rs）')
        lines.append('deathloss\t%g' % dp)
    lines += ['deliver\t%d\t%d\t%d' % (c['deliver'], DELIVER_ROWS, DELIVER_FLAG), 'identify\t%d' % IDENTIFY_FLAG,
              'lotlayout\t%d\t%d\t%d\t%d\t%d\t%d' % (ctx.P_mp.row_size, erlib.LOT_ID, erlib.LOT_CAT, erlib.LOT_PT, erlib.LOT_NUM, erlib.LOT_FLAG)]
    starts = getattr(ctx, 'start_items', None) or []
    if starts:
        lines.append('# startids <武器第一个编号> <间隔> <防具第一个编号> <间隔>：开局装备的编号段（角色记录里的开局装备按编号存）')
        lines.append('startids\t%d\t%d\t%d\t%d' % ctx.start_ids)
        lines.append('# start <类 0 武器 / 1 防具> <编号> <档> <本体> <种子> <能力需求上限 力,技,智,信,感> <补正取分布前几 %> <至少几种异常> <1 = 战技和常驻效果照本体> '
                     '<主补正放在哪项属性 0~4，-1 = 不管> <1 = 人物拿到时按那时的属性生成（大蛇狩猎矛）> <1 = 不照本体也按原版比例抽全能>：'
                     '开局装备（rr/startgear.py）、追忆换的成品传说（rr/remembrance.py）和商人卖的小极品传说武器（rr/shops.py），DLL 一启动就按种子生成，角色拿到后记进这个角色的记录')
        lines += ['start\t%d\t%d\t%d\t%d\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d' % (s['cat'], s['id'], s['tier'], s['base'], s['seed'], ','.join(map(str, s['maxreq'])),
                                                                        s.get('top', 100), s.get('min_status', 0), 1 if s.get('keep') else 0, s.get('main', -1),
                                                                        1 if s.get('pick') else 0, 1 if s.get('full') else 0)
                  for s in starts]
    bb = getattr(ctx, 'buyback', None)
    if bb:
        lines.append('# buyback <第一行> <行数> <上架标记起> <卖完标记起>：暗黑商店的回购商店（rr/darkshop.py），DLL 放最后卖掉的生成装备')
        lines.append('buyback\t%d\t%d\t%d\t%d' % bb)
    ws = getattr(ctx, 'weapon_shop', None)
    if ws:
        lines.append('# wshop <商店行> <武器类型 wepType> <档 0~2>：暗黑商店的武器商店（rr/darkshop.py），DLL 进存档时每格按类型、档生成一把放进去，买走了换新的')
        lines += ['wshop\t%d\t%d\t%d' % w for w in ws]
    pools = getattr(ctx, 'unid_pool', [])
    if pools:
        lines.append('# pool <来源,…> <类 0~2> <档,…> <几率 %> <掉落表类别> <编号> <个数> <名字>：掉落池（add_pool），鉴定 / 许愿做这类这档时按几率换成这件固定物品')
        lines += ['pool\t%s\t%d\t%s\t%g\t%d\t%d\t%d\t%s' % p for p in pools]
    from . import inherit, overlimit, reforge, wish
    lines += wish.lines(ctx)
    lines += reforge.lines(ctx)
    lines += overlimit.lines(ctx)
    lines += inherit.lines(ctx)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, path)
