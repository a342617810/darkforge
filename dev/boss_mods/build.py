# -*- coding: utf-8 -*-
"""从 dark_reforged\\boss\\ 里的原始压缩包抽出要整合的 Boss 模组（开发用，不随包发）：
    python -P build.py godfrey        （python -P：要用户目录里的 pycryptodome 解 regulation）
输出到 launcher\\reroll\\data\\bossmods\\<键>\\：
  files\\       原样的角色层文件（动作 / 行为 / 模型 / AI / 音频…），启动器按需把这个目录挂成 YAFSML 的一层（最底层）
  params.json   参数补丁：模组自己改的行（按位记录：只动模组改过的位，别的保持现在的原版）+ 模组新加的行
  mod.json      来源、版本、文件清单、文字（中英）、抽取时的提示

「模组自己改的」= 模组的值 ≠ 同一游戏版本的原版值。同版本原版值取同一版本的其他 Boss 模组里最多的那份（它们没改那一行），
没有就用现在的原版。按角色编号只留这个 Boss 的行，外加它引用到的特效 / 镜头 / 台词行（评估见 Boss模组整合评估.md 1.2）。"""
import os, sys, json, glob, hashlib, struct, zipfile, subprocess, tempfile, collections, re, shutil, difflib
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DR = os.path.normpath(os.path.join(HERE, '..', '..'))
ER = os.path.dirname(DR)
RR = os.path.join(DR, 'launcher', 'reroll')
sys.path.insert(0, RR)
import emevd  # noqa: E402
import erlib  # noqa: E402
import paramdef_min as pdm  # noqa: E402
import tae  # noqa: E402
erlib.DLL_DIRS[:] = [ER]
BOSS = os.path.join(DR, 'boss')
OUT = os.path.join(RR, 'data', 'bossmods')
SMITHBOX_DEFS = r'C:\Users\dxphh\Downloads\Smithbox_2_2_6_2026_09_20_b\Assets\PARAM\ER\Defs'

# ---------------------------------------------------------------- 各模组的配置
# 拉塔恩 20012814 用的指令参数：IF Character HP Value(组, 实体, 比较, 血量, ==, 1)；比较 2 是 >，3 是 <
CONSORT = 20010800
HP_BELOW_10 = struct.pack('<b3xIb3xib3xf', 0, CONSORT, 3, 10, 0, 1.0)
HP_ABOVE_0 = struct.pack('<b3xIb3xib3xf', 1, CONSORT, 2, 0, 0, 1.0)
MORTAL = struct.pack('<IB3x', CONSORT, 0)                    # Set Character Immortality(实体, 关)
# 蕾菈娜和米德拉的模组都带了作者改过的两个公共函数（aicommon 里：75 格、动作不传参数表），原版只有 50 格，
# 51 号以后的招式选不到。aicommon 不能整个换（别的 AI 用的是原版），这两个函数换个名字放进她们自己的脚本，函数体和模组的一样。
# 玛莲妮亚的模组没带这份，她的 51~55 号在作者的版本里也选不到，不要套这个
AI75_HEAD = """-- Dark Reforged: the author's versions of Common_Clear_Param / Common_Battle_Activate (aicommon is vanilla here)
function DR_Clear_Param75(f1_arg0, f1_arg1)
    for f1_local1 = 1, 75, 1 do
        f1_arg0[f1_local1] = 0
        f1_arg1[f1_local1] = nil
    end
end

function DR_Battle_Activate75(ai, goal, f2_arg2, f2_arg3, f2_arg4)
    local f2_local0 = {}
    local f2_local1 = {}
    local max = 0
    local f2_local3 = 1
    for f2_local4 = 1, 75, 1 do
        if f2_arg3[f2_local4] ~= nil then
            f2_local0[f2_local4] = f2_arg3[f2_local4]
        else
            f2_local0[f2_local4] = REGIST_FUNC(ai, goal, errorAct)
        end
        f2_local1[f2_local4] = f2_arg2[f2_local4]
        max = max + f2_local1[f2_local4]
    end
    local f2_local4 = 0
    local f2_local5 = ai:DbgGetForceActIdx()
    if 0 < f2_local5 and f2_local5 <= 60 then
        f2_local4 = f2_local0[f2_local5]()
        ai:DbgSetLastActIdx(f2_local5)
    else
        local random = ai:GetRandam_Int(1, max)
        local f2_local7 = 0
        local f2_local8 = 1
        for f2_local9 = 1, 75, 1 do
            f2_local7 = f2_local7 + f2_local1[f2_local9]
            if random <= f2_local7 then
                f2_local4 = f2_local0[f2_local9]()
                ai:DbgSetLastActIdx(f2_local9)
                f2_local9 = 75
            end
        end
    end
    local random = ai:GetRandam_Int(1, 100)
    if f2_local4 == nil or f2_arg4 == nil then
        f2_local4 = 0
    end
    if random <= f2_local4 then
        f2_arg4()
    end
end

"""
RELLANA_AI = {'head': AI75_HEAD, 'replace': [
    ('Common_Clear_Param(probabilities, acts, paramTbls)', 'DR_Clear_Param75(probabilities, acts)'),
    ('Common_Battle_Activate(ai, goal, probabilities, acts, actAfter)', 'DR_Battle_Activate75(ai, goal, probabilities, acts, actAfter)')]}
MIDRA_AI = {'head': AI75_HEAD, 'replace': [
    ('Common_Clear_Param(probabilities, acts, paramTbls)', 'DR_Clear_Param75(probabilities, acts)'),
    ('Common_Battle_Activate(ai, goal, probabilities, acts, actAfter, paramTbls)', 'DR_Battle_Activate75(ai, goal, probabilities, acts, actAfter)')]}
# 原版 SpEffect 5461：瞬间回复 100% 最大血量（只有这一项，对敌人也生效）。转阶段回满血用（用户 2026-11-13）
FULL_HEAL = 5461


def heal(ent):
    return (2004, 8, struct.pack('<ii', ent, FULL_HEAL))           # Set SpEffect(实体, 5461)


MODS = {
    'godfrey': dict(
        archive='Inner Godfrey*', root='Inner Godfrey (v1.13)/', name='Inner Godfrey', version='1.13', nexus=7140,
        boss={'zh': '葛孚雷 / 荷莱·露', 'en': 'Godfrey / Hoarah Loux'},
        chrs=[4720, 4721],
        # 高难度世界（敌人随机）里留在原位的 Boss 实体（随机器的编号，多阶段每段都给）
        fixed=[11050801, 11050800],
        files=['chr/c4720.anibnd.dcx', 'chr/c4720.behbnd.dcx', 'chr/c4720.chrbnd.dcx', 'chr/c4721.anibnd.dcx', 'chr/c4721.behbnd.dcx',
               'script/472000_battle.luabnd.dcx', 'script/472100_battle.luabnd.dcx',
               'sd/enus/cs_c4720.bnk', 'sd/enus/vc206.bnk', 'sd/enus/wem/65/650175479.wem', 'sd/enus/wem/70/704441477.wem'],
        # 对话包：只有列出的 ESD 和原版不同时才整包放进去（敌人随机时随机器的同名包盖在上面，用随机器的）
        talk={'script/talk/m11_05_00_00.talkesdbnd.dcx': ['t206101105.esd']},
        # 台词（TalkMsg，menu_dlc02）：模组新写的英文 + 我们翻的中文。11000100 是原版别人的台词编号，模组拿来写了葛孚雷的新台词，
        # 这里换成新编号（TalkParam 11000100 的 msgId 改过去），原版那句不动
        talkmsg={20070610: '勇敢的褪色者啊，成为王吧。去实现你的意志！',
                 20080400: '够了，别再做这为王的蠢事！',
                 11000100: '骄傲吧，战士。败给王，并不可耻。',
                 206804000: '你是真正的战士……',
                 206804010: '用你的力量，成为艾尔登之王吧。'},
        talkmsg_remap={11000100: 206809100},
    ),
    'godrick': dict(
        archive='Godrick overhaul*', root='mod/', name='Godrick overhaul', version='1.4', nexus=7155,
        boss={'zh': '接肢葛瑞克（+接肢贵族后裔）', 'en': 'Godrick the Grafted (+ Grafted Scion)'},
        chrs=[4750, 4690],
        fixed=[10000800],
        files=['chr/c4750.anibnd.dcx', 'chr/c4750.behbnd.dcx', 'chr/c4750_div00.anibnd.dcx', 'chr/c4750_div01.anibnd.dcx',
               'chr/c4690.anibnd.dcx', 'chr/c4690.behbnd.dcx', 'chr/c4690_div00.anibnd.dcx', 'chr/c4690_div01.anibnd.dcx',
               'chr/c4690_div02.anibnd.dcx', 'action/script/c4750.hks', 'script/475000_battle.luabnd.dcx'],
        # 模组塞进常驻特效包（sfxbnd_commoneffects）的新特效：重随时并进我们的 sfxbnd_c0000（常驻，不碰原版公共包）
        fx=[440574, 647507, 647508, 647509],
        # 场地（只在 Boss 在原位时用，现在 = 不开敌人随机）：作者标了 //NEW 的事件 + 开战事件里加的两句（无敌开关），
        # 地图加接肢贵族后裔（10000216）和两个传送用的物件（10001896 / 10001897；第三阶段的落点）。都移植到现在的原版文件上，不用模组的整文件
        arena=dict(map='m10_00_00_00', new_events=[10002812, 10002813, 10002814, 10002815, 10002816, 10002817],
                   replace_events={10002810: 2}, parts=['c4750_9001', 'AEG003_316_9003', 'AEG003_316_9004'],
                   # 转阶段动作里被打死：他倒下了但死亡事件等不到「已死亡」，一直不结算（用户 2026-11-08）。接龙头 / 换贵族后裔前先看是不是已经 0 血，
                   # 作者的另外 4 个新事件都有这个判断，这两个没有；死亡事件血量归零后最多再等 8 秒
                   guard_dead={10002811: (4, 13, 10000800), 10002812: (12, 2, 10000800)},
                   # 接龙头过场（二阶段）挂上 14750 之后回满血：两条路（过场后传送 / 玩家在场外）各一处，下标是原版事件的，从后往前插
                   edit_ins={10002811: [('ins', 38, [heal(10000800)]), ('ins', 18, [heal(10000800)])]},
                   death_timeout={10002800: (13, 4, 8.0)}),
        # 随从 → 跟着哪个 Boss 实体乘高难度补正（血量 / 攻击力），保持模组设计的比例
        helpers={10000216: 10000800},
        merge_csv=True,
    ),
    # 2026-11-05 用户「把剩下方便移植的boss都移植了吧」；抉择：大蛇狩猎矛用梅瑟莫的（×12）、复活重打不移植、普拉顿桑克斯带上贝勒的改动
    'messmer': dict(
        archive='Inner Serpent*', root='Inner Serpent v1.04.2 (Hotfix)/', name='Inner Serpent', version='1.04.2', nexus=7304,
        boss={'zh': '穿刺者梅瑟莫', 'en': 'Messmer the Impaler'},
        chrs=[5130, 5131, 5132, 5140, 5141],              # 5131 / 5132：梅瑟莫的另两套敌人参数（同一个 c5130）
        fixed=[21010801, 21010800],
        files=['chr/c5130.anibnd.dcx', 'chr/c5130.behbnd.dcx', 'chr/c5130.chrbnd.dcx', 'chr/c5140.anibnd.dcx', 'chr/c5140.behbnd.dcx',
               'chr/c5140.chrbnd.dcx', 'chr/c5141.anibnd.dcx', 'chr/c5141.behbnd.dcx', 'chr/c5141.chrbnd.dcx',
               'script/513000_battle.luabnd.dcx', 'sfx/sfxbnd_c5130.ffxbnd.dcx', 'sfx/sfxbnd_c5140.ffxbnd.dcx'],
        # 大蛇狩猎矛对 weakF（蛇形态）×12：配合蛇形态几乎打不动的伤害倍率（用户选梅瑟莫的）；新抓取技 ThrowParam
        # （ThrowParam 的号不在别的行 / 文件里直接出现，按 c5130 的号段点名要）
        rows=[('EquipParamWeapon', 17030000), ('ThrowParam', 34513000), ('ThrowParam', 34513010)],
        fx='auto',
        # 新事件 = 阶段辅助（只引用梅瑟莫本人）；21011997 是复活重打（不移植），地图上那个物件也是它的
        arena=dict(map='m21_01_00_00', new_events=[21012812, 21012813, 21012814], parts=[]),
    ),
    'consort': dict(
        archive='Inner Consort*', root='Inner Consort v1.06.6 - Main Version/', name='Inner Consort', version='1.06.6', nexus=6533,
        boss={'zh': '约定之王拉塔恩', 'en': 'Promised Consort Radahn'},
        chrs=[5220],
        fixed=[20010801, 20010800],
        files=['chr/c5220.anibnd.dcx', 'chr/c5220.behbnd.dcx', 'chr/c5220.chrbnd.dcx', 'script/522000_battle.luabnd.dcx',
               'sfx/sfxbnd_c5220.ffxbnd.dcx'],
        fx='auto',
        # 新事件：阶段辅助；20010999 / 20019991 和地图上的假人、物件是复活重打（不移植）。20012800 开战等待 4→6 秒、
        # 20012811 转阶段血量 0.65→0.55 + 新动作，换成模组版；其余改动是版本差 / 重编差异。挪动的 20011199 是场地外的原版机关，不动
        arena=dict(map='m20_01_00_00', new_events=[20010802, 20012812, 20012813, 20012814], mod_events=[20012800, 20012811], parts=[],
                   # 假死重生 20012814（血量 < 10 + 12299）放完会重新等待，只有 AI 打出 20034 才清 12299、解除不死（20012813），连招打不到那一段就一遍遍重放；
                   # 20057 又挂回 12299，致命一击时血量 0 也满足条件，对着死了的 Boss 再放一遍（用户 2026-11-09「三阶段之后死了重复进入三阶段」）。
                   # 改成：血量 > 0 才触发、一场只放一次；放完后血量再次 < 10 就解除不死。不在放完时直接解除：20034 自扣 99%，要靠不死留住 1 点
                   edit_ins={20012814: [('end', 14), ('ins', 13, [(4, 14, HP_BELOW_10), (2004, 12, MORTAL)]), ('ins', 0, [(4, 14, HP_ABOVE_0)])]}),
        # 5050 / 5051 拉卡德、蕾娜菈（同一作者，AI 脚本里写死了号）用来做别的；10697 / 10698 蒙格也有（10698 内容不同）。拉塔恩这边只在
        # 动作表和自己的参数里引用，换到 522 开头的空号（conflicts.py 查出来的）
        # 18406 / 18407 / 18409 和玛莲妮亚撞号（玛莲妮亚的 AI 写死了 18409），也是拉塔恩这边换
        renumber={('SpEffectParam', 5050): 52205050, ('SpEffectParam', 5051): 52205051,
                  ('SpEffectParam', 10697): 52210697, ('SpEffectParam', 10698): 52210698,
                  ('SpEffectParam', 18406): 52218406, ('SpEffectParam', 18407): 52218407, ('SpEffectParam', 18409): 52218409},
    ),
    'placidusax': dict(
        archive='Ancient Elden Lord*', root='Placidusax, Ancient Lord (v1.01.3)/', name='Ancient Elden Lord', version='1.01.3', nexus=9413,
        boss={'zh': '龙王普拉顿桑克斯（+贝勒）', 'en': 'Dragonlord Placidusax (+ Bayle)'},
        chrs=[4520, 5120],
        fixed=[13000830],
        files=['chr/c4520.anibnd.dcx', 'chr/c4520.behbnd.dcx', 'chr/c4520.chrbnd.dcx', 'script/452000_battle.luabnd.dcx',
               'script/512000_battle.luabnd.dcx', 'map/m13/m13_00_00_00/m13_00_00_00_0000.btl.dcx'],
        fx='all',
        # 新赐福「风暴之眼」的传送行；击败横幅：FeTextEffectParam 15（原版「STALEMATE」，竞技场平局用）改成「ELDEN LORD FALLEN」
        rows=[('BonfireWarpParam', 130011), ('FeTextEffectParam', 15)],
        texts={'GR_MenuText': {331310: 'ELDEN LORD FALLEN'}, 'PlaceName': {130011: '风暴之眼'}},
        # 新事件：阶段动作、换天气、光照、BGM；13002839 是「回溯时间」重打（不移植），地图上那个物件也是它的。
        # 13002830 横幅类型 15→32、13002840 换天气：用模组版。新赐福：玩家点 + 赐福资产 + 对话角色（模组复制了原版 c1000_9011 改作赐福对话，
        # 新的那个占了原名、原版的改叫「c1000_9011 {2}」；按实体挑新的那个，改名拷，原版的不动）
        arena=dict(map='m13_00_00_00', new_events=[13002831, 13002833, 13002836, 13002837, 13002838, 13002842, 13002843, 13002844, 13002845],
                   mod_events=[13002830, 13002840], ev0_ints=[13001961],
                   parts=['c0000_9033', 'AEG099_060_9011', 'c1000_9011~13000961>c1000_9911']),
    ),
    'mohg': dict(
        archive='2.00 Complete*', root='mod/', name='Mohg 2.00 Complete', version='2.00', nexus=4989,
        boss={'zh': '鲜血君王蒙格', 'en': 'Mohg, Lord of Blood'},
        chrs=[4800],
        fixed=[12050800],
        files=['chr/c4800.anibnd.dcx', 'chr/c4800.behbnd.dcx', 'script/480000_battle.luabnd.dcx'],
        talk={'script/talk/m12_05_00_00.talkesdbnd.dcx': ['t209101205.esd', 't418001205.esd']},
        fx='all',
        # 新事件：SpEffect 切阶段、换镜头；12052800 / 12052810 各插了几句。NPC 召唤（公共事件 90005780–82）召的是模组新加的
        # 「c0000_9005 {2}」（Smithbox 复制原版无名白面具入侵者时起的名字，实体 12050830），改个正常名字拷。12053718 没人初始化，不要
        arena=dict(map='m12_05_00_00', new_events=[12052812, 12052814, 12052850, 12052852, 12052853, 12052854],
                   replace_events={12052800: 1, 12052810: 2}, ev0_ints=[12050830],
                   parts=['c0000_9005 {2}>c0000_9905']),
        # 2000000 是通用 SpEffect（模组的 1.13 那份和现在不同 = 版本差），不要
        drop_rows=[('SpEffectParam', 2000000)],
    ),
    'rykard': dict(
        archive='Rykard Overhaul*', root='mod/', name='Rykard Overhaul', version='1.0', nexus=8415,
        boss={'zh': '亵渎君王拉卡德', 'en': 'Rykard, Lord of Blasphemy'},
        chrs=[4710, 4712],
        fixed=[16000801, 16000800],
        files=['action/script/c4712.hks', 'chr/c4710.anibnd.dcx', 'chr/c4710.behbnd.dcx', 'chr/c4710.chrbnd.dcx',
               'chr/c4710_div00.anibnd.dcx', 'chr/c4710_div01.anibnd.dcx', 'chr/c4710_div02.anibnd.dcx', 'chr/c4710_div03.anibnd.dcx',
               'chr/c4710_div04.anibnd.dcx', 'chr/c4710_div05.anibnd.dcx', 'chr/c4712.anibnd.dcx', 'chr/c4712.behbnd.dcx',
               'chr/c4712.chrbnd.dcx', 'script/471000_battle.luabnd.dcx', 'sfx/sfxbnd_c4710.ffxbnd.dcx'],
        merge_csv=True,
        # 用户选了梅瑟莫的大蛇狩猎矛（×12）：拉卡德这边对矛的削弱（weakF 0.3）和把拉卡德标成 weakF 都不要，保持原版的打法
        drop_rows=[('EquipParamWeapon', 17030000)],
        drop_fields={('NpcParam', 47100038): ['isWeakF'], ('NpcParam', 47101038): ['isWeakF']},
        # 新事件：两把剑（16000802 / 03）的出现 / 传送 / 子弹；开战事件 16002811 插了 4 句。
        # 地图只拷两把剑；场下 8 具 Boss 尸体（真的敌人部件，8 个别的 Boss 模型）和垫着它们的 35 块岩石是布景，不拷
        # （16003766 换镜头：模组里没有哪里初始化它，不要）
        # 用户 2026-11-14「让那把剑就开始就出来」：开战事件关掉两把剑、清标记之后等 2 帧再打开（同一帧 16002810 会关掉整个 Boss 组）；
        # keep_parts：高难度世界移植时不在读图后关它们（sc/bossarena.py hide_stray）
        arena=dict(map='m16_00_00_00', new_events=[16003767, 16003768, 16003769, 16003770],
                   replace_events={16002811: 4}, parts=['c4710_9009', 'c4710_9010'], keep_parts=['c4710_9009', 'c4710_9010'],
                   edit_ins={16002811: [('ins', 4, [(1001, 1, struct.pack('<i', 2)),
                                                    (2004, 5, struct.pack('<iB3x', 16000802, 1)), (2004, 5, struct.pack('<iB3x', 16000803, 1))])]}),
        helpers={16000802: 16000800, 16000803: 16000800},
    ),
    'midra': dict(
        archive='Midra*', root='midra/', name='Midra Overhaul', version='1.16.1', nexus=7570,
        boss={'zh': '癫火之王米德拉', 'en': 'Midra, Lord of Frenzied Flame'},
        chrs=[5050, 5051],
        fixed=[28000800],
        # 包里的 c0000（玩家动作，1.16.1 的旧版）和 aicommon 不要
        files=['chr/c5051.anibnd.dcx', 'chr/c5051.behbnd.dcx', 'chr/c5051.chrbnd.dcx', 'script/505100_battle.luabnd.dcx',
               'sfx/sfxbnd_c5050.ffxbnd.dcx', 'map/m28/m28_00_00_00/m28_00_00_00_0000.btl.dcx'],
        ref_params=['BuddyParam'],
        # 新事件：三个分身（28000805–07）的出现 / 传送、一个物件开关；28002821 换天气 + 跟着物件的特效，用模组版。
        # 地图：场地重做过（物件挪高、增删），整张图自动比对移植（区域 / 光照不动）
        arena=dict(map='m28_00_00_00', new_events=[28000808, 28000810, 28000811, 28000999], mod_events=[28002821], parts_auto=True),
        helpers={28000805: 28000800, 28000806: 28000800, 28000807: 28000800},
        lua_edits={'script/505100_battle.luabnd.dcx': MIDRA_AI},
    ),
    'rellana': dict(
        archive='Rellana*', root='mod/', name='Rellana Twin Moon Knight Overhaul', version='1.0', nexus=7074,
        boss={'zh': '双月骑士蕾菈娜', 'en': 'Rellana, Twin Moon Knight'},
        chrs=[5300],
        fixed=[2048440800],
        # aicommon_dlc02：模组的 goal_list_dlc2 是源码版，原版的全部登记 + 幻影用的 530010（多出的 522002 没人用，无害）
        files=['chr/c5300.anibnd.dcx', 'chr/c5300.behbnd.dcx', 'chr/c5300.chrbnd.dcx', 'script/530000_battle.luabnd.dcx',
               'script/530010_battle.luabnd.dcx', 'script/aicommon_dlc02.luabnd.dcx', 'sfx/sfxbnd_c5300.ffxbnd.dcx'],
        # 新事件：幻影（第二个蕾菈娜 2048440801）的出现 / 传送 / 重力 / 随机动作、换天气。
        # 地图只拷幻影：模组拆了屋顶和上层、外面摆了一圈幽影城的塔（64 个新物件，最远 215 米），
        # 用户 2026-11-09「幽影城的模型也被加载到了恩希斯城」，VINS 的场地也是原版。
        # 2049440804 模组的事件和 common_func 里都没有，那三句初始化不要
        # 2048442850（在这块地图上一直把时间改回半夜）不要：用户 2026-11-09「进入恩希斯城天气还是会突变」，VINS 也没有
        arena=dict(map='m61_48_44_00', new_events=[2048440801, 2048442851, 2049440802, 2049440803, 2049440805],
                   parts=['c5300 Rellana Phantom'], drop_inits=[2049440804],
                   # 原版的二阶段事件：等到 20012001（AI 转阶段动作挂上）设 BGM 标记，后面加一句回满血
                   edit_ins={2048442811: [('ins', 3, [heal(2048440800)])]}),
        helpers={2048440801: 2048440800},
        lua_edits={'script/530000_battle.luabnd.dcx': RELLANA_AI, 'script/530010_battle.luabnd.dcx': RELLANA_AI},
    ),
    'radahn': dict(
        archive='Vanilla Plus Radahn*', root='Vanilla+ Radahn/Vanilla Plus Radahn/mod/', name='Vanilla Plus Radahn', version='1.01', nexus=4683,
        boss={'zh': '“碎星”拉塔恩', 'en': 'Starscourge Radahn'},
        chrs=[4730, 4735, 4621],
        fixed=[1052380800],
        # 镜头 4731~4739：事件 1028430009 的初始化参数里（按 SpEffect 2200~2209 换镜头），抽取时看不到；行为 246200264 / 401、抓取 34462011 是艾丝缇（c4621，用 46200 这一档行为）的
        rows=[('LockCamParam', x) for x in (4731, 4732, 4733, 4734, 4736, 4737, 4738, 4739)] + [('BehaviorParam', 246200264), ('BehaviorParam', 246200401), ('ThrowParam', 34462011)],
        # c4730 的贴图和原版一样，不带。c4735 = 莱昂纳德（马），c4621 = 艾丝缇，都是新模型
        files=['chr/c4730.anibnd.dcx', 'chr/c4730.behbnd.dcx', 'chr/c4730.chrbnd.dcx',
               'chr/c4730_div00.anibnd.dcx', 'chr/c4730_div01.anibnd.dcx', 'chr/c4730_div02.anibnd.dcx',
               'chr/c4735.anibnd.dcx', 'chr/c4735.behbnd.dcx', 'chr/c4735.chrbnd.dcx',
               'chr/c4735_div00.anibnd.dcx', 'chr/c4735_div01.anibnd.dcx', 'chr/c4735_div02.anibnd.dcx',
               'chr/c4735_h.texbnd.dcx', 'chr/c4735_l.texbnd.dcx', 'chr/c4621.anibnd.dcx',
               'chr/c4621.behbnd.dcx', 'chr/c4621.chrbnd.dcx', 'chr/c4621_div00.anibnd.dcx',
               'chr/c4621_div01.anibnd.dcx', 'chr/c4621_div02.anibnd.dcx', 'chr/c4621_div03.anibnd.dcx',
               'chr/c4621_h.texbnd.dcx', 'chr/c4621_l.texbnd.dcx', 'action/script/c4621.hks',
               'action/script/c4735.hks', 'script/473000_battle.luabnd.dcx',],
        texts={'NpcName': {904730001: '莱昂纳德', 904730002: '“碎星英雄”拉塔恩将军'}},
        # 事件在小地块 m60_52_38_00，Boss 和新部件在大地块 m60_13_09_02（msb_map）。
        # 地图：加莱昂纳德、艾丝缇、第二个 c4730 和两个生成器；Boss 只挪位置，敌人参数留世界里的（:名字）；删作者删掉的 10 个召唤点和 1 个 NPC。
        # 作者在 m60_51_36_00（红狮子城）删的 NPC、挪的 c1000 不是这场战斗的，不要
        arena=dict(map='m60_52_38_00', msb_map='m60_13_09_02',
                   new_events=[1028430000, 1028430001, 1028430005, 1028430006, 1028430007, 1028430008, 1028430009, 1028430010, 1028430012, 1028430013, 1028430014],
                   mod_events=[1252382800, 1252382810],
                   parts=['m60_52_38_00-c4730_9003', 'm60_52_38_00-c4730_9004', 'm60_52_38_00-c4730_9005', ':m60_52_38_00-c4730_9002',
                          '^AstelSpawn', '%Astel', '%Leonard',
                          '-m60_52_39_00-c0000_9010', '-m60_52_39_00-AEG099_090_9000', '-m60_52_39_00-AEG099_090_9008',
                          '-m60_52_39_00-AEG099_090_9016', '-m60_52_39_00-AEG099_090_9024', '-m60_52_39_00-AEG099_090_9032',
                          '-m60_52_39_00-AEG099_090_9040', '-m60_52_39_00-AEG099_090_9048', '-m60_52_39_00-AEG099_090_9056',
                          '-m60_52_39_00-AEG099_090_9064', '-m60_52_39_00-AEG099_090_9072',]),
        helpers={425940000: 1052380800, 425940001: 1052380800, 425940002: 1052380800},
    ),
    'rennala': dict(
        archive='Rennala overhaul*', root='mod/', name='Rennala overhaul', version='1.2', nexus=7651,
        boss={'zh': '满月女王蕾娜菈', 'en': 'Rennala, Queen of the Full Moon'},
        chrs=[2030, 2031, 2032, 2040],
        fixed=[14000801, 14000800],
        files=['action/script/c2032.hks', 'chr/c2030.anibnd.dcx', 'chr/c2030.behbnd.dcx', 'chr/c2031.anibnd.dcx', 'chr/c2031.behbnd.dcx',
               'chr/c2031.chrbnd.dcx', 'chr/c2032.anibnd.dcx', 'chr/c2032.behbnd.dcx', 'chr/c2032.chrbnd.dcx', 'chr/c2032_h.texbnd.dcx',
               'chr/c2032_l.texbnd.dcx', 'script/203000_battle.luabnd.dcx', 'script/203100_battle.luabnd.dcx'],
        fx='all',
        merge_csv=True,
        # 新事件：阶段 SpEffect、召来客串（布莱泽 / 伊吉 / 亚杜拉…）、蛇形态；开战事件 14002810 插了 1 句。
        # 地图自动比对：新加的分身 / 客串 / 蛇形态、换了模型的召唤物；大书库赐福挪位置那几处不要（用户选留我们的「大书库门前」）。
        # 地图做在「原版 + 我们的额外赐福」上（with_graces），没开敌人随机、也没有随机器（拿不到 SoulsFormats）时赐福照样在
        arena=dict(map='m14_00_00_00', new_events=[14012490, 14012491, 14012492, 14012493, 14012494, 14012495, 14012496, 14012497, 14012498],
                   replace_events={14002810: 1}, parts_auto=True, exclude=['c1000_9000', 'c0000_9000', 'AEG099_060_9000'],
                   # 随机器改过 14002810（读图时启用分组 14005800 并开碰撞，新分身也在这个组），平常会跳过模组版；
                   # 用户 2026-11-09「二阶段空气墙，玩家和女王一起移动」，场地和 VINS 一样，这个事件也直接用模组版
                   force_events=[14002810],
                   with_graces=['raya_library']),
        # 新加的分身（14000843 / 44）、客串（14000835–38）、蛇形态（14000847–49）跟着第二阶段的蕾娜菈乘高难度补正
        helpers={e: 14000800 for e in (14000843, 14000844, 14000835, 14000836, 14000837, 14000838, 14000847, 14000848, 14000849)},
    ),
    # 2026-11-05 用户「先做马连尼亚吧」；米兰达小花 c4481 的动作包用户选「带上」（高难度下全世界的小花都用模组的）
    'malenia': dict(
        archive='Unalloyed Malenia*', root='Unalloyed 1.06/mod/', name='Unalloyed Malenia', version='1.06', nexus=4253,
        boss={'zh': '“米凯拉的锋刃”玛莲妮亚', 'en': 'Malenia, Blade of Miquella'},
        chrs=[2120, 2125, 4481, 4483],                     # 4481 / 4483：客串的腐败花（米兰达小花的动作）
        fixed=[15000800],
        # 2026-11-06 用户「水鸟的特效丢失」：游戏这张图没有请求 sfxbnd_c2120（YAFSML 日志里 c2120 的模型 / 动作 / AI / 行为都覆盖了，唯独没有它；
        # 同一局 c5220 有，原因没查明），模组新加的 22 个特效（水鸟多放的 100004891 等）和原版那 32 个都找不到。整包并进常驻包
        fx_chr='sfx/sfxbnd_c2120.ffxbnd.dcx',
        hp_forms=['c2120', 'c2125'],                       # 血量倍率（boss_mods.hp_mult）乘这两个模型：一二阶段、隐藏路线的形态、分身；花不算
        # 新加的行全要（VINS 也是整套照搬）。改原版的：玛莲妮亚的台词 / 腐败伤害梯度 / 镜头 / 投技点名要；SpEffect 7200 是圣树一带
        # 敌人共用的区域效果（模组把出血 / 冻伤减半），影响整个区域，不要
        all_new=True,
        rows=[('TalkParam', 2039000), ('TalkParam', 20390000), ('TalkParam', 20390401), ('SpEffectParam', 18411), ('SpEffectParam', 18418),
              ('SpEffectParam', 18419), ('LockCamParam', 2122), ('ThrowParam', 34212000), ('SpEffectVfxParam', 54221)],
        # 18406 玛莲妮亚没用到、又和拉塔恩撞号，不要；子弹 4720401 和蒙格撞号（两边都在用），玛莲妮亚这边换到 c2125 的空号
        drop_rows=[('SpEffectParam', 7200), ('SpEffectParam', 18406)],
        renumber={('Bullet', 4720401): 2125901},
        files=['action/script/c2120.hks', 'action/script/c2125.hks', 'chr/c2120.anibnd.dcx', 'chr/c2120.behbnd.dcx', 'chr/c2120.chrbnd.dcx',
               'chr/c2120_div00.anibnd.dcx', 'chr/c2120_div01.anibnd.dcx', 'chr/c2125.anibnd.dcx', 'chr/c2125.behbnd.dcx', 'chr/c2125.chrbnd.dcx',
               'chr/c2125_div00.anibnd.dcx', 'chr/c2125_div01.anibnd.dcx', 'chr/c2125_h.texbnd.dcx', 'chr/c2125_l.texbnd.dcx',
               'chr/c4481.anibnd.dcx', 'chr/c8900.chrbnd.dcx', 'cutscene/s15_00_0000.cutscenebnd.dcx', 'cutscene/s15_00_0010.cutscenebnd.dcx',
               'script/212000_battle.luabnd.dcx', 'script/212010_battle.luabnd.dcx', 'sfx/sfxbnd_c2120.ffxbnd.dcx'],
        # 对话：三个都是战斗台词（玛莲妮亚、新阶段、腐败女神形态）
        talk={'script/talk/m15_00_00_00.talkesdbnd.dcx': ['t203101500.esd', 't203102500.esd', 't204101500.esd']},
        talkmsg={203901001: '现在你明白了吗？', 203901002: '现在你明白了吗？'},
        texts={'NpcName': {902120002: '“不败的女武神”玛莲妮亚', 902100309: '“腐败女神”玛莲妮亚（练习）'}},
        # 事件：63 个新事件里不要「重置战斗」15000738（清击败标记、再发一次奖励）、练习模式用的 15000740，
        # 以及模组里没人初始化的 15002833 / 902 / 908 / 911 / 912；练习模式的开关这张图里没有
        # 地方打开，开战事件里那段分支平时走不到。改动的事件里真改了的换成模组版（初始化也跟着），其余是重编差异 / 版本差，保持原版
        arena=dict(map='m15_00_00_00',
                   new_events=[15000703, 15000717, 15000718, 15000719, 15000721, 15000722, 15000723, 15000724, 15000725, 15000726, 15000727,
                               15000728, 15000729, 15000730, 15000731, 15000732, 15000733, 15000734, 15000735, 15000736, 15000741, 15000742,
                               15000743, 15000744, 15002801, 15002802, 15002804, 15002807, 15002808, 15002821, 15002822, 15002823, 15002825,
                               15002826, 15002827, 15002828, 15002831, 15002834, 15002835, 15002836, 15002847, 15002853, 15002862,
                               15002901, 15002903, 15002904, 15002905, 15002906, 15002907, 15002910, 15002913, 15002914, 15002915, 15002916, 15002917, 15002918],
                   mod_events=[15000700, 15000702, 15000713, 15002810, 15002811, 15002820, 15002842, 15002849],
                   replace_events={15002800: 10}, ev0_ints=[15001744],
                   # 模组把追忆挪到自己的奖励表 10205、在死亡事件里发；我们不要模组的奖励表（奖励还是 Handle Boss Defeat 发 10200 那条链），
                   # 10205 在我们这里是链上的一格（未鉴定物品，标记也是 510200），这句留着会多发 / 抢标记
                   drop_ins={15002800: [(2003, 4)]},
                   # 地图整图比对：分身、腐败女神、20 朵花、客串、出生点 / 范围这些区域；删的地图块 m100076_2000 也删。
                   # 重置战斗的交互物件、和它配套的玩家点 / 物件不要
                   parts_auto=True, regions_auto=True, auto_remove_kinds=('Enemy', 'Asset', 'Player', 'MapPiece'),
                   exclude=['AEG260_009_1003', 'c0000_2291', 'AEG099_500_2291'],
                   helpers_auto=True),
    ),
}

CHR_RULES = ('NpcParam', 'NpcThinkParam', 'AtkParam_Npc', 'Bullet', 'BehaviorParam')
REF_PARAMS = ('SpEffectParam', 'SpEffectVfxParam', 'LockCamParam', 'TalkParam', 'Magic', 'ActionButtonParam')
# 其它配置项（每个模组可选）：
#   rows=[(参数, 行)]            额外要的行（模组改了才放）      drop_rows=[(参数, 行)]  不要的行
#   drop_fields={(参数, 行): [字段]}  这几个字段保持现在的原版（只对「改」的行）
#   ref_params=[参数]            除 REF_PARAMS 外，按引用收进来的参数表（例如 ThrowParam）
#   renumber={('SpEffectParam', 旧号): 新号}  和别的模组撞号的新 SpEffect 换号（参数里的 SpEffect 字段、动作表 66/67 事件一起改；conflicts.py 查）
#   arena 的 drop_ins={事件: [(bank, id)]}  replace_events 的事件里不要的指令（只能是不在 SKIP 范围里的）
#   lua_edits={文件: {'head': 开头加的文本, 'replace': [(原句, 新句)]}}  文本 AI 脚本里改句子（每句必须正好一处）
#   arena 的 msb_map='图'  部件放在另一张图上（开放世界 Boss：事件在小地块，部件在大地块）；parts 里还可以有 %名字（事件表的生成器）、:名字（只挪位置）
#   arena 的 drop_inits=[事件]  构造事件里这些事件的初始化不要（模组初始化了根本不存在的事件）
#   arena 的 force_events=[事件]  replace_events / mod_events 里随机器改过也照样整个换成模组版的（默认会跳过）
#   arena 的 edit_ins={事件: [('end', 第几条) 把这条 END 的类型改成「结束」不重启 / ('ins', 第几条之后, [(bank, id, 参数字节)])]}  下标是原事件的，按从后往前写
#   arena 的 guard_dead={事件: (第几条之后, 条件组, Boss 实体)}  在这一条后面插「这个 Boss 血量归零就结束这个事件」（转阶段事件，别对着已经死了的 Boss 转）
#   arena 的 death_timeout={事件: (第几条之后, 条件组, 秒)}  死亡事件等「已死亡」的条件组 -2 上并一个「房主 + 等够这么多秒」（血量归零后等不到已死亡就不会结算）
#   hp_forms=[模型]              场地地图里这些模型的敌人算 Boss 本体形态（mod.json 的 boss_forms，settings 的 boss_mods.hp_mult 乘它们；没配就是 fixed）
#   fx_chr='sfx/sfxbnd_cXXXX.ffxbnd.dcx'  这个角色特效包里的特效和资源全部并进常驻的 sfxbnd_c0000（游戏没请求这个包时也找得到）
#   fx='auto' | 'all' | [编号]   模组塞进公共特效包的新特效：auto = 按动作表 / 参数 / 自己的特效包引用到的（再加上特效之间的引用），
#                               all = 全部新特效；用到的贴图 / 模型 / 动画（公共包里新加的）一起带上
#   texts={FMG: {编号: 中文}}     别的文字（英文取模组 engus 文字包里的；menu* 里的进游戏脚本的 menu_dlc02，item* 里的进重随的 item_dlc02）
#   arena 里另外可以有：mod_events=[事件]（整个换成模组版：作者真改了内容、又不只是插几句的），ev0_ints=[数]（构造事件里模组新加的、
#                       参数里带这些数的指令也加，例如新赐福的登记），parts 里 '=名字' = 用模组的同名部件替换，'-名字' = 删掉
FX_EXT_DIR = {'.tpf': 'tex', '.flver': 'model', '.anibnd': 'hkx'}
ALL_NEW_SKIP = ('ItemLotParam_map', 'ItemLotParam_enemy', 'ActionButtonParam', 'ShopLineupParam', 'ShopLineupParam_Recipe',
                'EquipParamGoods', 'EquipParamWeapon', 'EquipParamProtector', 'EquipParamAccessory', 'EquipMtrlSetParam',
                'AssetEnvironmentGeometryParam', 'BonfireWarpParam', 'GameAreaParam')


def field_masks(ptype, names):
    """字段名 → {字节偏移: 位掩码}（位域只占它那几位）"""
    L = layout(ptype)
    out = {}
    for nm, fc, off, bp, bits, _d in L:
        if nm not in names:
            continue
        if bits:
            for k in range(bp, bp + bits):
                out[off + k // 8] = out.get(off + k // 8, 0) | (1 << (k % 8))
        else:
            for k in range(struct.calcsize('<' + fc)):
                out[off + k] = 0xFF
    miss = set(names) - {n for n, *_ in L}
    if miss:
        raise SystemExit('%s 没有字段 %s' % (ptype, sorted(miss)))
    return out


def all_ints(b):
    return set(struct.unpack_from('<%di' % (len(b) // 4), b[:len(b) // 4 * 4]))


def chr_of(p, r):
    if p in ('NpcParam', 'NpcThinkParam') and 10000000 <= r < 100000000:
        return r // 10000
    if p in ('AtkParam_Npc', 'Bullet') and 1000000 <= r < 10000000:
        return r // 1000
    if p in ('AtkParam_Npc', 'Bullet') and 200000000 <= r < 300000000:
        return (r - 200000000) // 1000
    if p == 'BehaviorParam' and 200000000 <= r < 300000000:
        return (r - 200000000) // 10000
    return None


# ---------------------------------------------------------------- 读压缩包
class Archive:
    def __init__(self, path):
        self.path = path
        self.tmp = None
        if path.lower().endswith('.zip'):
            self.z = zipfile.ZipFile(path)
            self.names = {n.replace('\\', '/'): n for n in self.z.namelist() if not n.endswith('/')}
        else:                                                   # rar：Windows 自带的 tar.exe（libarchive）能解
            self.z = None
            self.tmp = tempfile.mkdtemp(prefix='bossmod_')
            subprocess.run([os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'tar.exe'), '-xf', path, '-C', self.tmp], check=True)
            self.names = {}
            for r, ds, fs in os.walk(self.tmp):
                for f in fs:
                    full = os.path.join(r, f)
                    self.names[os.path.relpath(full, self.tmp).replace('\\', '/')] = full

    def find(self, suffix):
        s = suffix.lower()
        hits = [n for n in self.names if n.lower().endswith(s)]
        return hits

    def read(self, name):
        return self.z.read(self.names[name]) if self.z else open(self.names[name], 'rb').read()

    def close(self):
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def load_reg(raw_enc):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.bin')
    tmp.write(raw_enc)
    tmp.close()
    try:
        raw = erlib.read_regulation(tmp.name)
    finally:
        os.remove(tmp.name)
    b = erlib.Bnd4(raw)
    ver = bytes(raw[0x18:0x20]).rstrip(b'\0').decode('ascii', 'replace')
    return ver, {n[:-6]: erlib.Param(b.get(n)) for n in b.entries if n.endswith('.param')}


def all_regs():
    """boss\\ 里每个包的 regulation：[(包名, 版本, {参数: Param})]"""
    out = []
    cache = os.path.join(HERE, '.cache')                  # 加密的 regulation 原样缓存（按压缩包大小 + 修改时间），免得每次都解 12 个包
    os.makedirs(cache, exist_ok=True)
    for p in sorted(glob.glob(os.path.join(BOSS, '*'))):
        if not p.lower().endswith(('.zip', '.rar')):
            continue
        st = os.stat(p)
        cp = os.path.join(cache, '%s_%d_%d.reg' % (hashlib.sha1(os.path.basename(p).encode()).hexdigest()[:12], st.st_size, int(st.st_mtime)))
        if os.path.isfile(cp):
            raw = open(cp, 'rb').read()
        else:
            a = Archive(p)
            try:
                regs = [n for n in a.find('regulation.bin') if n.lower().endswith('/regulation.bin') or n.lower() == 'regulation.bin']
                regs = [n for n in regs if not n.lower().endswith(('.prev', '.bak'))]
                raw = a.read(sorted(regs, key=len)[0]) if regs else b''
            finally:
                a.close()
            open(cp, 'wb').write(raw)
        if raw:
            ver, P = load_reg(raw)
            out.append((os.path.basename(p), ver, P))
    return out


# ---------------------------------------------------------------- 参数定义（Smithbox 的 ER 定义，按 ParamType 找）
_defs = None


def layout(ptype):
    global _defs
    if _defs is None:
        _defs = {}
        for f in glob.glob(os.path.join(SMITHBOX_DEFS, '*.xml')):
            try:
                t = ET.parse(f).getroot().findtext('ParamType')
            except Exception:
                continue
            if t:
                _defs[t.strip()] = f
    f = _defs.get(ptype)
    return pdm.layout(pdm.load(f))[0] if f else None


def ints_of(P, row):
    L = layout(P.param_type.decode())
    if not L:
        return {}
    return {k: v for k, v in pdm.unpack(L, row).items() if isinstance(v, int)}


# ---------------------------------------------------------------- 主流程
def build(key):
    cfg = MODS[key]
    arcs = glob.glob(os.path.join(BOSS, cfg['archive']))
    if len(arcs) != 1:
        raise SystemExit('找不到（或不止一个）%s' % cfg['archive'])
    arc_path = arcs[0]
    out = os.path.join(OUT, key)
    log = []
    print('读原版 regulation…')
    vver, VP = load_reg(open(os.path.join(ER, 'regulation.bin'), 'rb').read())
    print('读 boss\\ 里所有包的 regulation（算同版本的原版值）…')
    regs = all_regs()
    me = next(r for r in regs if r[0] == os.path.basename(arc_path))
    mver, MP = me[1], me[2]
    others = [r for r in regs if r[1] == mver and r[0] != me[0]]
    log.append('模组 regulation 版本 %s（现在的原版 %s）；同版本参照 %d 个包' % (mver, vver, len(others)))

    def base_row(p, r):
        cnt = collections.Counter(bytes(P[p].rows[r]) for _n, _v, P in others if p in P and r in P[p].rows)
        if cnt:
            b, n = cnt.most_common(1)[0]
            return b, 'same-version'
        if p in VP and r in VP[p].rows:
            return bytes(VP[p].rows[r]), 'vanilla'
        return None, None

    # 模组自己改 / 加的行
    own = {}
    for p, P in MP.items():
        for r in P.ids:
            b, _src = base_row(p, r)
            if b is None or bytes(P.rows[r]) != b:
                own[(p, r)] = b
    chrs = set(cfg['chrs'])
    keep = {k for k in own if k[0] in CHR_RULES and chr_of(*k) in chrs}
    keep |= {k for k in own if k[0] == 'LockCamParam' and k[1] in chrs}
    # 角色文件（动作表 / AI）里出现的整数，用来判断特效等行是不是这个 Boss 在用
    a = Archive(arc_path)
    try:
        root = cfg['root']
        blobs = {}
        for rel in cfg['files']:
            blobs[rel] = a.read(root + rel)
        talk_raw = {rel: a.read(root + rel) for rel in cfg.get('talk', {})}
        msg_raw = a.read(root + 'msg/engus/menu_dlc02.msgbnd.dcx') if cfg.get('talkmsg') else None
        msg_en = {n.rsplit('/', 1)[-1]: a.read(n) for n in a.find('.msgbnd.dcx') if n.startswith(root + 'msg/engus/')} if cfg.get('texts') else {}
        fx_raw = a.read(root + 'sfx/sfxbnd_commoneffects.ffxbnd.dcx') if cfg.get('fx') else None
        ar = cfg.get('arena')
        arena_raw = {}
        if ar:
            arena_raw['emevd'] = a.read(root + 'event/%s.emevd.dcx' % ar['map'])
            arena_raw['msb'] = a.read(next(n for n in a.find('/%s.msb.dcx' % (ar.get('msb_map') or ar['map'])) if n.startswith(root)))
        # 作者给的合并清单（[MERGE]\*.csv，第一列是行号）：列了的行都要（只要模组真改了；0 号默认行不要）
        merge_rows = set()
        if cfg.get('merge_csv'):
            for n in a.find('.csv'):
                if n.startswith(root + '[MERGE]/'):
                    p = n.rsplit('/', 1)[-1][:-4]
                    for line in a.read(n).decode('utf-8', 'replace').splitlines()[1:]:
                        f0 = line.split(',', 1)[0].strip()
                        if f0.isdigit() and int(f0) != 0:
                            merge_rows.add((p, int(f0)))
    finally:
        a.close()
    if merge_rows:
        miss = sorted(k for k in merge_rows if k not in own)
        keep |= {k for k in merge_rows if k in own}
        log.append('作者合并清单 %d 行%s' % (len(merge_rows), '；其中 %d 行和同版本原版一样（不用改）：%s' % (len(miss), miss[:10]) if miss else ''))
    if cfg.get('all_new'):
        # 模组新加的行全要（像 VINS 那样整套照搬；引用方式太多追不全：事件、对话、过场、子弹链…），奖励 / 装备 / 商店类的除外
        add_all = {k for k in own if (own[k] is None or k[0] in VP and k[1] not in VP[k[0]].rows) and k[0] not in ALL_NEW_SKIP}
        # 别的角色号段里的（模组顺手改了别的 Boss）不在这里整批要：被这个 Boss 的行引用到的，下面的闭包会带上
        add_all = {k for k in add_all if not (k[0] in CHR_RULES and chr_of(*k) is not None and chr_of(*k) not in chrs)}
        log.append('模组新加的行全要（all_new）：%d 行' % len(add_all - keep))
        keep |= add_all
    for p, r in cfg.get('rows', []):
        if (p, r) in own:
            keep.add((p, r))
        else:
            log.append('！指定要的 %s %d 模组没改（和同版本原版一样），不用' % (p, r))
    ref_params = tuple(REF_PARAMS) + tuple(cfg.get('ref_params', ()))
    ref_ints = set()
    arena_events = None
    if ar:
        arena_events = port_events(ar, arena_raw['emevd'], log)
        for ev in arena_events['ported']:
            for ins in ev['ins']:
                b = ins['args']
                ref_ints.update(struct.unpack_from('<%di' % (len(b) // 4), b[:len(b) // 4 * 4]))
    # 动作表 / 行为图里模组比原版多出来的整数（同名条目对齐的 int32，减去原版那份里有的）：只用来认模组新加的 SpEffect / 特效行
    # （它们常在动作事件靠后的参数、行为图条件里）。公共行为图 c9997.hkx 本来就有大量巧合的数，所以要减原版
    deep_ints = set()
    for rel, raw in blobs.items():
        if rel.endswith(('.behbnd.dcx', '.anibnd.dcx')):
            van_raw = vread_path('/' + rel)
            van_ents = {k.lower(): v for k, v in bnd_all(van_raw).items()} if van_raw else {}
            for name, data in bnd_all(raw).items():
                if name.lower().endswith(('.hkx', '.tae')) and 'skeleton' not in name.lower():
                    v = van_ents.get(name.lower())           # 按完整路径对（同名的 hkx 不止一个）
                    deep_ints |= all_ints(data) - (all_ints(v) if v else set())
    for rel, raw in blobs.items():
        if rel.endswith('.hks'):
            ref_ints.update(int(x) for x in re.findall(rb'\b\d{3,10}\b', raw))
        if rel.endswith('.anibnd.dcx'):
            for name, data in bnd_all(raw).items():
                if name.endswith('.tae'):
                    for _aid, t, pos in tae.events(data):
                        if pos + 32 <= len(data):                # 前 8 个数（SpEffect 等编号有时不在前 4 个）
                            ref_ints.update(struct.unpack_from('<8i', data, pos))
                        elif pos + 16 <= len(data):
                            ref_ints.update(struct.unpack_from('<4i', data, pos))
        elif rel.endswith('.luabnd.dcx'):
            for name, data in bnd_all(raw).items():
                ref_ints.update(int(x) for x in re.findall(rb'\b\d{3,10}\b', data)) if not data.startswith(b'\x1bLua') else \
                    ref_ints.update(struct.unpack_from('<%di' % (len(data) // 4), data[:len(data) // 4 * 4]))
    for rel, raw in talk_raw.items():
        for name, data in bnd_all(raw).items():
            if name.split('/')[-1].split('\\')[-1] in cfg['talk'][rel]:
                ref_ints.update(struct.unpack_from('<%di' % (len(data) // 4), data[:len(data) // 4 * 4]))
    # 从已保留的行出发，把它们引用到的特效 / 镜头 / 台词等行一起收进来（闭包）
    changed = True
    while changed:
        changed = False
        vals = set(ref_ints)
        for p, r in keep:
            vals.update(ints_of(MP[p], bytes(MP[p].rows[r])).values())
        for k in own:
            if k in keep or k[1] <= 0:
                continue
            if k[0] in ref_params and chr_of(*k) is None and (
                    k[1] in vals or own[k] is None and k[0] in ('SpEffectParam', 'SpEffectVfxParam') and k[1] in deep_ints):
                keep.add(k)
                changed = True
            elif k[0] in ('Bullet', 'AtkParam_Npc', 'BehaviorParam') and (own[k] is None or k[1] not in VP[k[0]].rows) and (
                    k[1] in vals or k[1] in deep_ints):
                # 模组在别的角色号段新加、又被这个 Boss 引用的行（例如蒙格借用梅瑟莫的矛、古龙的雷）。别人号段里「改」的行不要
                keep.add(k)
                changed = True
    drop = {tuple(x) for x in cfg.get('drop_rows', [])}
    for k in sorted(drop & keep):
        log.append('不要 %s %d（配置的 drop_rows）' % k)
    keep -= drop
    skipped = sorted(k for k in own if k not in keep)
    # SpEffect 换号（renumber）：几个模组拿同一个空号做了不同的效果时，给能换的那一个换号（参数行里的 SpEffect 字段、动作表里
    # 加 SpEffect 的事件一起改）。AI 脚本里写死了号的那一边不能换
    ren = {'SpEffectParam': {}, 'Bullet': {}}
    others = collections.defaultdict(set)
    for f in glob.glob(os.path.join(OUT, '*', 'params.json')):
        if os.path.basename(os.path.dirname(f)) != key:
            for x in json.load(open(f, encoding='utf-8'))['rows']:
                others[x['param']].add(int(x['id']))
    for (pp, old), new in cfg.get('renumber', {}).items():
        if pp not in ren or (pp, old) not in keep or old in VP[pp].rows:
            raise SystemExit('renumber 只做模组新加、又要了的 SpEffect / 子弹：%s %d' % (pp, old))
        if new in VP[pp].rows or new in MP[pp].rows or new in others[pp]:
            raise SystemExit('换号 %s %d → %d：新号已经有人用' % (pp, old, new))
        ren[pp][old] = new
    BULLET_REF = ('HitBulletID', 'intervalCreateBulletId')

    def renum(p, data):
        if not (ren['SpEffectParam'] or ren['Bullet']):
            return data
        L = layout(MP[p].param_type.decode())
        b = bytearray(data)
        u = pdm.unpack(L, data) if L else {}
        for nm, fc, off, bp, bits, _d in (L or ()):
            if bits or fc not in ('i', 'I'):
                continue
            v = struct.unpack_from('<' + fc, b, off)[0]
            m = None
            if re.search(r'(?i)speffect|cycleoccurrence', nm):
                m = ren['SpEffectParam']
            elif nm in BULLET_REF:
                m = ren['Bullet']
            elif p == 'BehaviorParam' and nm == 'refId':
                m = {1: ren['Bullet'], 2: ren['SpEffectParam']}.get(u.get('refType'))
            if m and v in m:
                struct.pack_into('<' + fc, b, off, m[v])
        return bytes(b)

    # 输出参数补丁
    rows = []
    for p, r in sorted(keep):
        mod = renum(p, bytes(MP[p].rows[r]))
        base = own[(p, r)]
        cur = bytes(VP[p].rows[r]) if p in VP and r in VP[p].rows else None
        if base is None or cur is None:
            if cur is not None:
                log.append('！%s %d：同版本里没有这一行，现在的原版有了（后来的补丁加的）——用模组的整行盖' % (p, r))
            rows.append({'param': p, 'id': ren.get(p, {}).get(r, r), 'kind': 'add', 'data': mod.hex()})
            continue
        segs, conf = [], []
        dm = {}
        if (p, r) in cfg.get('drop_fields', {}):
            dm = field_masks(MP[p].param_type.decode(), cfg['drop_fields'][(p, r)])
        for i in range(len(mod)):
            m = (base[i] ^ mod[i]) & ~dm.get(i, 0) & 0xFF
            if m:
                if (cur[i] ^ base[i]) & m:
                    conf.append(i)
                segs.append([i, m, mod[i] & m])
        if conf:
            log.append('！%s %d：%d 个字节原版后来也改了同一位（以模组为准）：偏移 %s' % (p, r, len(conf), conf[:8]))
        if dm:
            log.append('%s %d：%s 保持原版（配置的 drop_fields）%s' % (p, r, '、'.join(cfg['drop_fields'][(p, r)]), '' if segs else '，别的没改，整行不用'))
        if segs:
            rows.append({'param': p, 'id': r, 'kind': 'patch', 'bits': segs})
    # TalkParam 换台词编号（别动原版别人的台词）
    remap = {int(k): v for k, v in cfg.get('talkmsg_remap', {}).items()}
    tl = layout('TALK_PARAM_ST')
    msg_off = next(o for n, fc, o, *_ in tl if n == 'msgId')
    msgf_off = next(o for n, fc, o, *_ in tl if n == 'msgId_female')
    for row in rows:
        if row['param'] == 'TalkParam' and row['kind'] == 'add':
            d = bytearray(bytes.fromhex(row['data']))
            for off in (msg_off, msgf_off):
                v = struct.unpack_from('<i', d, off)[0]
                if v in remap:
                    struct.pack_into('<i', d, off, remap[v])
                    log.append('TalkParam %d：台词编号 %d → %d（原版 %d 是别人的台词）' % (row['id'], v, remap[v], v))
            row['data'] = d.hex()
    # 台词文字：英文取模组的，中文用配置里翻的
    en_mod = {}
    for name, data in (bnd_all(msg_raw).items() if msg_raw else ()):
        if name.split('/')[-1].split('\\')[-1] == 'TalkMsg.fmg':
            en_mod = erlib.read_fmg(data)
    van_all = set()
    for lang in (('engus', 'zhocn') if remap else ()):
        for name, data in bnd_all(vread_msg(lang)).items():
            if name.split('/')[-1].split('\\')[-1].startswith('TalkMsg'):
                van_all |= set(erlib.read_fmg(data))
    texts = {'en': {}, 'zh': {}}
    for mid, zh in cfg.get('talkmsg', {}).items():
        new_id = remap.get(mid, mid)
        if mid in remap and new_id in van_all:
            raise SystemExit('新台词编号 %d 原版已经在用' % new_id)
        texts['en'][str(new_id)] = en_mod[mid]
        texts['zh'][str(new_id)] = zh
    # 别的文字（texts）：英文取模组 engus 文字包里的；在 menu* 包里的给游戏脚本（menu_dlc02），item* 里的给重随（item_dlc02）
    fmg_texts = {}
    for fmg, zh_rows in cfg.get('texts', {}).items():
        hit = None
        for bn in sorted(msg_en):
            for name, data in bnd_all(msg_en[bn]).items():
                if name.replace('\\', '/').split('/')[-1] == fmg + '.fmg':
                    d = erlib.read_fmg(data)
                    if all(i in d for i in zh_rows) and (hit is None or bn.endswith('_dlc02.msgbnd.dcx')):
                        hit = (bn, d)
        if not hit:
            raise SystemExit('模组的英文文字包里找不到 %s %s' % (fmg, sorted(zh_rows)))
        dest = 'menu' if hit[0].startswith('menu') else 'item'
        van_d = {}
        for name, data in bnd_all(vread_path('/msg/engus/%s_dlc02.msgbnd.dcx' % dest)).items():
            if name.replace('\\', '/').split('/')[-1] == fmg + '.fmg':
                van_d = erlib.read_fmg(data)
        for i in zh_rows:
            if van_d.get(i):
                log.append('！%s %d 原版已经有文字「%s」，用模组的盖' % (fmg, i, van_d[i]))
        fmg_texts[fmg] = {'dest': dest, 'en': {str(i): hit[1][i] for i in zh_rows}, 'zh': {str(i): z for i, z in zh_rows.items()}}
    # 对话包：只有列出的 ESD 不同才整包用
    talk_ok = {}
    for rel, raw in talk_raw.items():
        van = vread_path('/' + rel)
        V = {k.replace('\\', '/').split('/')[-1]: h for k, h in ((k, sha(x)) for k, x in bnd_all(van).items())}
        M = {k.replace('\\', '/').split('/')[-1]: h for k, h in ((k, sha(x)) for k, x in bnd_all(raw).items())}
        diff = sorted(k for k in set(V) | set(M) if V.get(k) != M.get(k))
        if set(diff) <= set(cfg['talk'][rel]):
            talk_ok[rel] = raw
        else:
            log.append('！%s 里除了 %s 还有别的不同（%s），这个对话包不放' % (rel, cfg['talk'][rel], diff))
    # 新加的敌人参数 / 思考参数行换编号：段末 9900 起（原版没有的号）。它们只给场地里新加的随从用（地图部件引用，下面 msbport 一起换）
    newid = {}
    taken = set()                       # 别的模组已经换到的号（几个模组同时加载时不能撞）
    for f in glob.glob(os.path.join(OUT, '*', 'params.json')):
        if os.path.basename(os.path.dirname(f)) != key:
            taken |= {(r['param'], int(r['id'])) for r in json.load(open(f, encoding='utf-8'))['rows']
                      if r['kind'] == 'add' and r['param'] in ('NpcParam', 'NpcThinkParam')}
    for row in rows:
        if row['kind'] == 'add' and row['param'] in ('NpcParam', 'NpcThinkParam'):
            blk = row['id'] // 10000 * 10000
            cand = next(c for c in range(blk + 9900, blk + 10000) if c not in VP[row['param']].rows and (row['param'], c) not in newid.values()
                        and (row['param'], c) not in taken)
            newid[(row['param'], row['id'])] = (row['param'], cand)
            log.append('%s %d → %d（新加的行换到段末，免得和随机器 / 重随新建的行撞）' % (row['param'], row['id'], cand))
            row['id'] = cand
    if ren['SpEffectParam'] or ren['Bullet']:
        log.append('换号：%s' % ', '.join('%s %d → %d' % (pp, a, b) for pp in ren for a, b in sorted(ren[pp].items())))
    if ren['SpEffectParam']:
        for rel in list(blobs):
            if rel.endswith('.anibnd.dcx'):
                blobs[rel], n = renum_tae(blobs[rel], ren['SpEffectParam'])
                if n:
                    log.append('%s：动作表里加 SpEffect 的事件改了 %d 处' % (rel, n))
    for rel, ed in cfg.get('lua_edits', {}).items():
        blobs[rel] = lua_edit(blobs[rel], ed)
        log.append('%s：AI 脚本开头加了公共函数，改了 %d 句' % (rel, len(ed['replace'])))
    # 写出
    if os.path.isdir(out):
        shutil.rmtree(out)
    files = {}
    for rel, raw in list(blobs.items()) + list(talk_ok.items()):
        dst = os.path.join(out, 'files', *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(raw)
        files[rel] = {'sha256': sha(raw), 'size': len(raw)}
    json.dump({'rows': rows}, open(os.path.join(out, 'params.json'), 'w', encoding='utf-8'), separators=(',', ':'))
    # 常驻特效（并进我们的 sfxbnd_c0000，rr/bossmods.py）：fx\f000xxxxxx.fxr + .ffxreslist
    fx_ids, fx_res = [], []
    if fx_raw:
        ents = {k.replace('\\', '/').split('/')[-1].lower(): x for k, x in bnd_all(fx_raw).items()}
        van_fx = {k.replace('\\', '/').split('/')[-1].lower() for k in bnd_all(vread_path('/sfx/sfxbnd_commoneffects.ffxbnd.dcx'))}
        cand = {int(n[1:10]): n for n in ents if n.endswith('.fxr') and n not in van_fx}
        want = cfg['fx']
        if want == 'all':
            sel = set(cand)
        elif want == 'auto':
            # 引用：动作表事件的前 8 个数、Boss 自己特效包里的特效、AI / HKS 里的数、Boss 的参数行（全部，不只改了的）和它们引用的 SpEffect / 特效行
            refs = set(ref_ints)
            for rel, raw in blobs.items():
                if rel.endswith('.anibnd.dcx'):
                    for name, data in bnd_all(raw).items():
                        if name.endswith('.tae'):
                            for _aid, t, pos in tae.events(data):
                                if pos + 32 <= len(data):
                                    refs.update(struct.unpack_from('<8i', data, pos))
                elif re.match(r'sfx/sfxbnd_c\d', rel):
                    for name, data in bnd_all(raw).items():
                        if name.lower().endswith('.fxr'):
                            refs |= all_ints(data)
            vals = set()
            for p, r in keep:
                vals.update(ints_of(MP[p], bytes(MP[p].rows[r])).values())
            for p in CHR_RULES:
                for r in MP[p].ids:
                    if chr_of(p, r) in chrs:
                        vals.update(ints_of(MP[p], bytes(MP[p].rows[r])).values())
            for _ in range(3):
                for p in ('SpEffectParam', 'SpEffectVfxParam'):
                    for r in MP[p].ids:
                        if r in vals and r > 1000:
                            vals.update(ints_of(MP[p], bytes(MP[p].rows[r])).values())
            refs |= vals
            sel, todo = set(), [i for i in cand if i in refs]
            while todo:                                    # 特效之间的引用（子特效）
                i = todo.pop()
                if i not in sel:
                    sel.add(i)
                    todo += [j for j in all_ints(ents[cand[i]]) if j in cand and j not in sel]
            log.append('公共包新特效 %d 个，按引用要 %d 个' % (len(cand), len(sel)))
        else:
            sel = set(want)
            for fid in sel:
                if 'f%09d.fxr' % fid in van_fx:
                    raise SystemExit('特效 %d 原版公共包里已经有了（不是模组新加的）' % fid)
        res = set()
        for fid in sel:
            for ln in ents['f%09d.ffxreslist' % fid].decode('ascii', 'replace').split():
                b = ln.rsplit('.', 1)[0].lower()
                for ext in FX_EXT_DIR:
                    if b + ext in ents and b + ext not in van_fx:
                        res.add(b + ext)
        os.makedirs(os.path.join(out, 'fx'))
        for fid in sorted(sel):
            for ext in ('fxr', 'ffxreslist'):
                n = 'f%09d.%s' % (fid, ext)
                open(os.path.join(out, 'fx', n), 'wb').write(ents[n])
            fx_ids.append(fid)
        for n in sorted(res):
            open(os.path.join(out, 'fx', n), 'wb').write(ents[n])
            fx_res.append(n)
        if fx_res:
            log.append('特效用到的公共包新资源 %d 个：%s' % (len(fx_res), ', '.join(fx_res)))
    # 角色特效包整包并进常驻包（fx_chr）：全部特效 + 包里的贴图 / 模型 / 动画（rr/bossmods.py 的 add_fx 按扩展名放）
    if cfg.get('fx_chr'):
        ents = {k.replace(chr(92), '/').split('/')[-1].lower(): x for k, x in bnd_all(blobs[cfg['fx_chr']]).items()}
        os.makedirs(os.path.join(out, 'fx'), exist_ok=True)
        n_chr = 0
        for n in sorted(ents):
            open(os.path.join(out, 'fx', n), 'wb').write(ents[n])
            if n.endswith('.fxr'):
                fx_ids.append(int(n[1:-4]))
                n_chr += 1
            elif not n.endswith('.ffxreslist'):
                if os.path.splitext(n)[1] not in FX_EXT_DIR:
                    raise SystemExit('特效包里有不认识的文件 %s' % n)
                fx_res.append(n)
        log.append('角色特效包 %s 整包并进常驻包：特效 %d 个、资源 %s' % (cfg['fx_chr'], n_chr, fx_res))
    # 场地：事件移植到现在的原版文件、地图加部件（离线 msbport），放 arena\（启动器只在 Boss 在原位时挂）
    arena = None
    if ar:
        ev = arena_events['emevd']
        dst = os.path.join(out, 'arena', 'event', ar['map'] + '.emevd.dcx')
        os.makedirs(os.path.dirname(dst))
        raw = erlib.dcx_compress_dflt(emevd.write(ev), level=9)
        open(dst, 'wb').write(raw)
        emevd.read(erlib.dcx_decompress(raw))       # 读得回来
        files_ar = {'event/%s.emevd.dcx' % ar['map']: sha(raw)}
        if ar.get('parts') or ar.get('parts_auto'):  # 没有要拷的部件就不放地图（只移植事件）
            msb = port_msb(ar, arena_raw['msb'], log, newid)
            dst2 = os.path.join(out, 'arena', 'map', 'mapstudio', (ar.get('msb_map') or ar['map']) + '.msb.dcx')
            os.makedirs(os.path.dirname(dst2))
            open(dst2, 'wb').write(msb)
            files_ar['map/mapstudio/%s.msb.dcx' % (ar.get('msb_map') or ar['map'])] = sha(msb)
            if ar.get('with_graces'):
                # sc/extragrace.py 看到场地成品已经带着这些赐福的部件，就直接用、不再拷（没有随机器时也拷不了）
                open(os.path.join(out, 'arena', 'graces.txt'), 'w', encoding='utf-8').write(''.join(g + '\n' for g in ar['with_graces']))
        # 运行时（高难度世界里 sc/bossarena.py 移植）从成品地图拷，用的是成品里的名字：「模组名>新名字」只留新名字
        run_parts = [(x[0] if x[0] in '=-' else '') + x.lstrip('=-').split('>')[-1] for x in ar.get('parts', [])]
        arena = dict(map=ar['map'], msb_map=ar.get('msb_map'), events=[e['id'] for e in arena_events['ported']], parts=run_parts,
                     new_events=list(ar.get('new_events', [])),
                     replace_events=sorted((set(ar.get('replace_events', {})) | set(ar.get('guard_dead', {})) | set(ar.get('death_timeout', {})) | set(ar.get('edit_ins', {}))) - set(ar.get('new_events', []))),
                     mod_events=list(ar.get('mod_events', [])), ev0_ints=list(ar.get('ev0_ints', [])),
                     force_events=list(ar.get('force_events', [])), keep_parts=list(ar.get('keep_parts', [])),
                     files=files_ar)
    helpers = dict(cfg.get('helpers', {}))
    if ar and ar.get('helpers_auto'):
        # 场地里拷 / 换上的敌人（分身、客串…）都跟着第一个固定的 Boss 乘高难度补正，保持模组设计的比例
        for e in getattr(port_msb, 'enemies', []):
            if e not in cfg['fixed']:
                helpers.setdefault(e, cfg['fixed'][0])
        log.append('场地新敌人跟着 %d 乘补正：%d 个' % (cfg['fixed'][0], len(helpers)))
    # 本体形态（hp_forms）：成品场地地图里这些模型的敌人实体
    forms = []
    if cfg.get('hp_forms'):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.msb')
        tmp.write(erlib.dcx_decompress(open(os.path.join(out, 'arena', 'map', 'mapstudio', (ar.get('msb_map') or ar['map']) + '.msb.dcx'), 'rb').read()))
        tmp.close()
        for _n, (ty, info) in msb_parts(tmp.name, os.path.join(DR, 'launcher', 'dotnet', 'dotnet.exe')).items():
            mm = re.match(r'model=(\S+) ent=(-?\d+)', info)
            if ty == 'Enemy' and mm and mm.group(1) in cfg['hp_forms'] and int(mm.group(2)) > 0:
                forms.append(int(mm.group(2)))
        os.remove(tmp.name)
        forms = sorted(set(forms))
        log.append('本体形态（%s）：%d 个实体' % ('、'.join(cfg['hp_forms']), len(forms)))
    by_param = collections.Counter((r['param'], r['kind']) for r in rows)
    meta = dict(key=key, name=cfg['name'], version=cfg['version'], nexus=cfg['nexus'], boss=cfg['boss'], chrs=cfg['chrs'],
                source=dict(archive=os.path.basename(arc_path), sha256=sha(open(arc_path, 'rb').read()), regulation=mver),
                built_against=vver, files=files, texts=texts, fmg_texts=fmg_texts, fx=fx_ids, fx_res=fx_res, arena=arena, fixed=list(cfg.get('fixed', [])),
                helpers={str(k): v for k, v in helpers.items()}, boss_forms=forms,
                params={'%s %s' % k: n for k, n in sorted(by_param.items())},
                skipped_rows=len(skipped), log=log)
    json.dump(meta, open(os.path.join(out, 'mod.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n'.join(log))
    print('参数：%s' % dict(meta['params']))
    print('没要的行 %d 个（别的 Boss 的 / 版本差）：%s' % (len(skipped), collections.Counter(p for p, _ in skipped)))
    if os.environ.get('BOSSMODS_SKIPPED'):
        print('  ' + ' '.join('%s:%d' % k for k in skipped))
    print('文件 %d 个，%.1f MB → %s' % (len(files), sum(f['size'] for f in files.values()) / 1048576, out))


def lua_edit(raw, ed):
    """文本 AI 脚本（luabnd 里的 *_battle.lua）：开头加 ed['head']，ed['replace'] 的句子每句必须正好出现一次"""
    bnd = erlib.Bnd4(erlib.dcx_decompress(raw) if raw[:4] == b'DCX\0' else raw)
    names = [n for n in bnd.entries if n.endswith('_battle.lua')]
    if len(names) != 1:
        raise SystemExit('AI 包里的脚本不是一个：%s' % names)
    s = bnd.get(names[0]).decode('ascii')
    for a, b in ed['replace']:
        if s.count(a) != 1:
            raise SystemExit('%s 里 %r 出现 %d 次' % (names[0], a, s.count(a)))
        s = s.replace(a, b)
    bnd.put(names[0], (ed['head'] + s).encode('ascii'))
    return erlib.dcx_compress_dflt(bytes(bnd.data), level=9)


def renum_tae(raw, ren):
    """动作包里加 SpEffect 的事件（类型 66 / 67，第一个参数是 SpEffect 号）按 ren 换号，原地改（大小不变），返回 (DCX, 改了几处)；
    没改就原样返回"""
    bnd = erlib.Bnd4(erlib.dcx_decompress(raw) if raw[:4] == b'DCX\0' else raw)
    n = 0
    for name, e in bnd.entries.items():
        if not name.endswith('.tae'):
            continue
        data = bnd.get(name)
        for _aid, t, pos in tae.events(data):
            if t in (66, 67) and pos + 4 <= len(data):
                v = struct.unpack_from('<i', data, pos)[0]
                if v in ren:
                    struct.pack_into('<i', bnd.data, e['off'] + pos, ren[v])
                    n += 1
    return (erlib.dcx_compress_dflt(bytes(bnd.data), level=9), n) if n else (raw, 0)


def _sig(ins):
    return (ins['bank'], ins['id'], ins['args'])


def emedf_names():
    """(bank, id) → 指令名（随机器自带的 er-common.emedf.json）"""
    d = json.load(open(os.path.join(DR, 'randomizer', 'diste', 'Base', 'er-common.emedf.json'), encoding='utf-8'))
    return {(c['index'], i['index']): i['name'] for c in d['main_classes'] for i in c['instrs']}


def port_events(ar, mod_raw, log):
    """模组地图事件 → 移植到现在的原版：新事件原样加上（构造事件 0 里照模组加初始化），replace_events 里的事件
    先确认「模组版 = 现在的原版 + 正好 N 条新指令」（作者标 //NEW 的那几句）再整个换成模组版；对不上就停（版本差混在里面）。
    指令的层（layer）按字节对到原版的层表，没有就加。返回 {'emevd': 改好的原版, 'ported': [移植的事件]}"""
    M = emevd.read(erlib.dcx_decompress(mod_raw))
    V = emevd.read(erlib.dcx_decompress(vread_path('/event/%s.emevd.dcx' % ar['map'])))
    MV = {e['id']: e for e in M['events']}
    VV = {e['id']: e for e in V['events']}

    def relayer(ev):
        for ins in ev['ins']:
            if ins['layer'] is not None:
                lb = M['layers'][ins['layer']]
                if lb not in V['layers']:
                    V['layers'].append(lb)
                ins['layer'] = V['layers'].index(lb)
        return ev

    ported = []
    names = emedf_names()
    for eid, n_new in ar.get('replace_events', {}).items():
        # 原版事件 + 模组插进去的那几条（作者用 DarkScript3 重编过，条件组编号会变：同一条指令只是参数不同、又是 IF / END IF 类的，算重编差异）
        va, ma = VV[eid]['ins'], MV[eid]['ins']
        a, b = [_sig(i) for i in va], [_sig(i) for i in ma]
        out, n_ins, n_re, n_chg = [], 0, 0, 0

        def only_group(x, y):
            # 只是条件组重新编号：指令的参数全是组号（IF / END IF Condition Group…），或者除了第一个字节（组号）都一样。
            # 2026-11-06：以前同类的 IF 一律算重编差异，玛莲妮亚 15002800 模组把等的实体从 15000800 改成 15000860 也被放过了，
            # 最后阶段打死后死亡事件等不到（用户「对话完之后就卡住了 没有后续了」）
            return 'Condition Group' in names.get((x['bank'], x['id']), '') or x['args'][1:] == y['args'][1:]
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == 'equal':
                out += va[i1:i2]
            elif tag == 'insert':
                out += [relayer({'events': None, 'ins': [x]})['ins'][0] for x in ma[j1:j2]]
                n_ins += j2 - j1
            elif tag == 'replace' and i2 - i1 == j2 - j1 and all(
                    (x['bank'], x['id']) == (y['bank'], y['id']) and names.get((x['bank'], x['id']), '').startswith(('IF ', 'END IF'))
                    for x, y in zip(va[i1:i2], ma[j1:j2])):
                for x, y in zip(va[i1:i2], ma[j1:j2]):
                    if only_group(x, y):
                        out.append(x)
                        n_re += 1
                    elif x['args'][:1] == y['args'][:1]:
                        # 同一个条件组、内容真改了（等的实体变了之类）：用模组的
                        out.append(relayer({'events': None, 'ins': [y]})['ins'][0])
                        n_chg += 1
                    else:
                        raise SystemExit('事件 %d：第 %d 条组号和内容都变了（%s → %s），要手动看' % (eid, i1, x['args'].hex(), y['args'].hex()))
            else:
                raise SystemExit('事件 %d：模组版不是「原版 + 插入的指令」（%s %s），要手动看' % (eid, tag, (i1, i2, j1, j2)))
        if n_ins != n_new:
            raise SystemExit('事件 %d：插入了 %d 条，配置说 %d 条' % (eid, n_ins, n_new))
        if VV[eid]['params']:
            raise SystemExit('事件 %d 有参数替换，插指令要改下标（还没做）' % eid)
        # 配置的 drop_ins：模组插的句子里不要的（例如发模组自己奖励表的 Award Item Lot）。不能夹在 SKIP 跳过的范围里（行数会错）
        for bid in ar.get('drop_ins', {}).get(eid, []):
            hit = [k for k, x in enumerate(out) if (x['bank'], x['id']) == tuple(bid)]
            for k in hit:
                for j, x in enumerate(out[:k]):
                    if names.get((x['bank'], x['id']), '').startswith('SKIP') and j + x['args'][0] >= k:
                        raise SystemExit('事件 %d：要去掉的第 %d 句在第 %d 句 SKIP 的范围里' % (eid, k, j))
            out = [x for k, x in enumerate(out) if k not in hit]
            log.append('事件 %d：去掉模组的 %s %d 句（drop_ins）' % (eid, names.get(tuple(bid), bid), len(hit)))
        VV[eid]['ins'] = out
        ported.append(VV[eid])
        log.append('事件 %d：原版 + 模组插入的 %d 条 + 模组改了内容的 %d 条（另有 %d 条只是重编时条件组编号不同，保持原版）' % (eid, n_ins, n_chg, n_re))
    for eid in ar.get('mod_events', []):
        # 作者真改了内容（不只是插几句）的原版事件：整个换成模组版（重编差异语义上一样）
        if eid not in VV or eid not in MV:
            raise SystemExit('事件 %d：原版或模组里没有' % eid)
        k = V['events'].index(VV[eid])
        V['events'][k] = VV[eid] = relayer(MV[eid])
        ported.append(VV[eid])
        log.append('事件 %d：换成模组版（%d 条指令，原版 %d 条）' % (eid, len(MV[eid]['ins']), len(V['events'][k]['ins'])))
    ev0v = VV[0]
    # 换成模组版 / 插了指令的事件：构造事件里它的初始化也跟模组走（模组改了参数、加了几份、或者不再初始化）。一样就不动
    inits = lambda ins, eid: [i for i in ins if i['bank'] == 2000 and i['id'] in (0, 6) and len(i['args']) >= 8 and
                              struct.unpack_from('<i', i['args'], 4)[0] == eid]
    for eid in list(ar.get('mod_events', [])) + list(ar.get('replace_events', {})):
        a, b = inits(ev0v['ins'], eid), inits(MV[0]['ins'], eid)
        if sorted(_sig(i) for i in a) != sorted(_sig(i) for i in b):
            ev0v['ins'] = [i for i in ev0v['ins'] if i not in a] + [relayer({'ins': [i]})['ins'][0] for i in b]
            log.append('事件 %d 的初始化换成模组的（原版 %d 条 → 模组 %d 条）' % (eid, len(a), len(b)))
    have = {_sig(i) for i in ev0v['ins']}
    want = set(ar.get('ev0_ints', []))
    if want:
        # 构造事件里模组新加的、参数带这些数的指令（例如新赐福的登记）
        for i in MV[0]['ins']:
            if _sig(i) not in have and want & all_ints(i['args']):
                ev0v['ins'].append(relayer({'ins': [i]})['ins'][0])
                have.add(_sig(i))
                log.append('构造事件加：%s' % (emedf_names().get((i['bank'], i['id']), (i['bank'], i['id'])),))
    for eid in ar.get('new_events', []):
        if eid in VV:
            raise SystemExit('新事件 %d 原版已经有了' % eid)
        V['events'].append(relayer(MV[eid]))
        ported.append(MV[eid])
        inits = [i for i in MV[0]['ins'] if i['bank'] == 2000 and i['id'] in (0, 6) and eid in struct.unpack_from('<%di' % (len(i['args']) // 4), i['args'])]
        if not inits:
            # 不在构造事件里初始化的：要有别的（移植过来的）事件初始化它
            by = [e['id'] for e in M['events'] if e['id'] != 0 and any(
                i['bank'] == 2000 and i['id'] in (0, 6) and len(i['args']) >= 8 and struct.unpack_from('<i', i['args'], 4)[0] == eid for i in e['ins'])]
            if not by:
                raise SystemExit('模组里没有哪里初始化 %d' % eid)
            log.append('事件 %d 由事件 %s 初始化（不在构造事件里）' % (eid, by))
        for i in inits:
            if struct.unpack_from('<i', i['args'], 4)[0] in ar.get('drop_inits', ()):
                continue
            if _sig(i) not in have:
                ev0v['ins'].append(i)
                have.add(_sig(i))
    log.append('新事件 %d 个（%s），构造事件里加了初始化' % (len(ar.get('new_events', [])), ', '.join(map(str, ar.get('new_events', [])))))

    def insert(eid, after, new):
        # 在第 after 条后面插几条（原版事件 / 新事件都行）。不能夹在 SKIP 跳过的范围里（行数会错），有参数替换的还没做
        ev = VV.get(eid) or MV[eid]
        if ev['params']:
            raise SystemExit('事件 %d 有参数替换，插指令要改下标（还没做）' % eid)
        for j, x in enumerate(ev['ins'][:after + 1]):
            if names.get((x['bank'], x['id']), '').startswith('SKIP') and j + x['args'][0] > after:
                raise SystemExit('事件 %d：第 %d 条后面在第 %d 句 SKIP 的范围里' % (eid, after, j))
        ev['ins'][after + 1:after + 1] = [dict(bank=b, id=i, args=a, layer=None) for b, i, a in new]
        if not any(e is ev for e in ported):
            ported.append(ev)
    for eid, edits in ar.get('edit_ins', {}).items():
        ev = VV.get(eid) or MV[eid]
        for e in edits:
            if e[0] == 'end':
                x = ev['ins'][e[1]]
                if (x['bank'], x['id']) != (1000, 4):
                    raise SystemExit('事件 %d：第 %d 条不是无条件 END' % (eid, e[1]))
                x['args'] = bytes([0]) + bytes(x['args'][1:])
            else:
                insert(eid, e[1], e[2])
        log.append('事件 %d：按 edit_ins 改了 %d 处' % (eid, len(edits)))
    for eid, (after, grp, ent) in ar.get('guard_dead', {}).items():
        insert(eid, after, [(4, 2, struct.pack('<b3xIb3xfb3xf', grp, ent, 5, 0.0, 0, 1.0)),      # IF Character HP Ratio(grp, ent, <=, 0, ==, 1)
                            (1000, 2, bytes([0, 1, grp & 0xFF, 0]))])                            # END IF Condition Group State(End, true, grp)
        log.append('事件 %d：第 %d 条后面加了 Boss 血量归零就结束' % (eid, after))
    for eid, (after, grp, sec) in ar.get('death_timeout', {}).items():
        ins = (VV.get(eid) or MV[eid])['ins']
        host = next(x for x in ins if (x['bank'], x['id']) == (3, 26))                           # IF Player Is In World Type(组, 房主)：抄这个事件自己的
        if ins[after]['bank'] != 3 or struct.unpack_from('<b', ins[after]['args'], 0)[0] != -2:
            raise SystemExit('事件 %d：第 %d 条不是往条件组 -2 里加的' % (eid, after))
        insert(eid, after, [(3, 26, bytes([grp & 0xFF]) + bytes(host['args'][1:])),
                            (1, 0, struct.pack('<b3xf', grp, sec)),                              # IF Elapsed Seconds(grp, sec)
                            (0, 0, bytes([0xFE, 1, grp & 0xFF, 0]))])                            # IF Condition Group(-2, true, grp)
        log.append('事件 %d：等已死亡的条件上并了「房主 + 等够 %g 秒」' % (eid, sec))
    return {'emevd': V, 'ported': ported}


def port_msb(ar, mod_raw, log, newid=None):
    """现在的原版地图 + 模组地图里的这几个部件（dev\\boss_mods\\msbport：SoulsFormats，按名字拷）→ DCX 字节。
    newid：{(参数表, 旧号): (参数表, 新号)}，拷过来的敌人部件用到的就换成新号（先拷一遍看部件用的号，再带 @ 拷一遍）"""
    tool = os.path.join(HERE, 'msbport')
    dotnet = os.path.join(DR, 'launcher', 'dotnet', 'dotnet.exe')
    tmp = tempfile.mkdtemp(prefix='msbport_')
    try:
        v, m, o = (os.path.join(tmp, n) for n in ('v.msb', 'm.msb', 'o.msb'))
        if ar.get('with_graces'):
            # 做在「原版 + 我们的额外赐福部件」的固定地图上（sc/extragrace.py 没开敌人随机时用的那份，data/graces/<图>.msb.dcx）
            base = os.path.join(RR, 'data', 'graces', ar['map'] + '.msb.dcx')
            open(v, 'wb').write(erlib.dcx_decompress(open(base, 'rb').read()))
            log.append('地图 %s 做在额外赐福的固定地图上（%s）' % (ar['map'], ', '.join(ar['with_graces'])))
        else:
            open(v, 'wb').write(erlib.dcx_decompress(vread_path('/map/mapstudio/%s.msb.dcx' % (ar.get('msb_map') or ar['map']))))
        open(m, 'wb').write(erlib.dcx_decompress(mod_raw))
        run = lambda parts: subprocess.run([dotnet, os.path.join(tool, 'msbport.dll'), v, m, o] + parts, capture_output=True, text=True,
                                           encoding='utf-8', errors='replace', cwd=tool)
        if ar.get('parts_auto'):
            # 场地整个重做过的（米德拉）：按名字比原版和模组的全部部件（敌人 / 物件 / 玩家点），删掉的删、改了的换、新加的拷；
            # 区域（光照、音效范围）不动。先删、再换、最后加（实体编号先腾出来）
            vv = os.path.join(tmp, 'vv.msb')                # 比对总是对原版（底图可能带着我们的额外赐福，那些不算模组删的）
            open(vv, 'wb').write(erlib.dcx_decompress(vread_path('/map/mapstudio/%s.msb.dcx' % ar['map'])))
            V, M = msb_parts(vv, dotnet), msb_parts(m, dotnet)
            ex = set(ar.get('exclude', []))
            kinds = ('Enemy', 'Asset', 'Player')
            rkinds = tuple(ar.get('auto_remove_kinds', kinds))            # 删的可以多几种（地图块等）
            rem = [n for n in V if n not in M and V[n][0] in rkinds and n not in ex]
            chg = [n for n in M if n in V and M[n] != V[n] and M[n][0] in kinds and n not in ex]
            add = [n for n in M if n not in V and M[n][0] in kinds and n not in ex]
            other = sorted({M.get(n, V.get(n))[0] for n in set(V) ^ set(M) | {n for n in M if n in V and M[n] != V[n]}} - set(kinds) - set(rkinds))
            regs = []
            if ar.get('regions_auto'):
                # 模组新加的区域（出生点、范围…）先拷，部件和事件会按名字 / 实体引用它们。改了的原版区域不动
                RV, RM = msb_parts(vv, dotnet, 'REGION'), msb_parts(m, dotnet, 'REGION')
                regs = ['^' + n for n in RM if n not in RV and n not in ex]
            ar['parts'] = regs + ['-' + n for n in rem] + ['=' + n for n in chg] + add + [x for x in ar.get('parts', []) if x not in add]
            log.append('地图 %s 自动比对：删 %d、换 %d、加 %d%s%s%s' % (ar['map'], len(rem), len(chg), len(add),
                                                           '、区域加 %d' % len(regs) if regs else '',
                                                           '；不拷的类型 %s' % other if other else '', '；排除 %s' % sorted(ex) if ex else ''))
        r = run(ar['parts'])
        if r.returncode or not r.stdout.strip().endswith('ok'):
            raise SystemExit('msbport 失败：' + (r.stdout + r.stderr)[-800:])
        if newid:
            spec = []
            for name in ar['parts']:
                mm = re.search(r'^(?:copied|replaced) %s \(Enemy,.*npc (-?\d+), think (-?\d+)\)' % re.escape(name.lstrip('=').split('>')[-1]), r.stdout, re.M)
                if mm and not name.startswith('-'):
                    npc, think = int(mm.group(1)), int(mm.group(2))
                    n2 = newid.get(('NpcParam', npc), ('', npc))[1]
                    t2 = newid.get(('NpcThinkParam', think), ('', think))[1]
                    if (n2, t2) != (npc, think):
                        spec.append('%s@%d@%d' % (name, n2, t2))
                        continue
                spec.append(name)
            r = run(spec)
            if r.returncode or not r.stdout.strip().endswith('ok'):
                raise SystemExit('msbport 失败：' + (r.stdout + r.stderr)[-800:])
        log.append('地图 %s：%s' % (ar.get('msb_map') or ar['map'], '；'.join(l for l in r.stdout.splitlines() if l.startswith(('copied', 'replaced', 'deleted', 'kept', 'absent', 'moved')))))
        port_msb.enemies = sorted({int(x) for x in re.findall(r'^(?:copied|replaced) .+? \(Enemy, model \S+, entity (\d+)', r.stdout, re.M)} - {0})
        return erlib.dcx_compress_dflt(open(o, 'rb').read(), level=9)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def msb_parts(path, dotnet, what='PART'):
    """解压后的 msb → {部件名: (类型, 模型 / 实体 / 位置 / 引用)}（analysis\\msbdump，只读）。名字里可能有空格（Smithbox 复制时起的「xxx {2}」）。
    what='REGION' 时列区域"""
    r = subprocess.run([dotnet, os.path.join(HERE, 'analysis', 'msbdump', 'msbdump.dll'), path, '0', '0', '0', '1e9'], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    out = {}
    for ln in r.stdout.splitlines():
        mm = re.match(r'PART (\w+) (.+?) (model=.*)$', ln) if what == 'PART' else re.match(r'REGION (\w+) (.+?) (ent=.*)$', ln)
        if mm:
            if mm.group(2) in out:
                raise SystemExit('地图里有重名部件 %s，自动比对做不了' % mm.group(2))
            out[mm.group(2)] = (mm.group(1), mm.group(3))
    if not out:
        raise SystemExit('msbdump 没列出部件：' + (r.stdout + r.stderr)[-300:])
    return out


_arcs = None


def vread_path(path):
    global _arcs
    if _arcs is None:
        keys = os.path.join(HERE, 'analysis', 'keys')
        _arcs = []
        for n in ('Data0', 'Data1', 'Data2', 'Data3', 'DLC'):
            pem = open(os.path.join(keys, n + '_key.pem'), 'rb').read()
            pem = pem.decode('utf-16') if pem[:2] in (b'\xff\xfe', b'\xfe\xff') else pem.decode('ascii', 'ignore')
            _arcs.append(erlib.GameArchive(os.path.join(ER, n + '.bhd'), pem))
    hit = None
    for a in _arcs:
        if a.entry(path) is not None:
            hit = a
    return hit.read(path) if hit else None


def vread_msg(lang):
    return vread_path('/msg/%s/menu_dlc02.msgbnd.dcx' % lang)


def bnd_all(raw):
    """BND4（可带 DCX）→ {完整名字: 数据}"""
    if raw[:4] == b'DCX\0':
        raw = erlib.dcx_decompress(raw)
    b = erlib.Bnd4(raw)
    out = {}
    pos = 0x40
    for _ in range(b.count):
        p = pos + 8
        size = struct.unpack_from('<q', raw, p)[0]
        p += 16 if b.compr else 8
        if b.long_off:
            off = struct.unpack_from('<q', raw, p)[0]; p += 8
        else:
            off = struct.unpack_from('<I', raw, p)[0]; p += 4
        if b.has_ids:
            p += 4
        noff = struct.unpack_from('<I', raw, p)[0]
        e = noff
        if b.unicode:
            while raw[e:e + 2] != b'\0\0':
                e += 2
            name = raw[noff:e].decode('utf-16le')
        else:
            name = raw[noff:raw.index(b'\0', noff)].decode('shift_jis')
        out[name] = raw[off:off + size]
        pos += b.hdr_size
    return out


if __name__ == '__main__':
    keys = sys.argv[1:] or list(MODS)
    if keys == ['all']:
        keys = list(MODS)
    for k in keys:
        build(k)
