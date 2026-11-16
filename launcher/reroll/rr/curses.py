# -*- coding: utf-8 -*-
"""咒痕（原名七咒，用户 2026-11-03 改名；settings.json 的 curses；用户 2026-11-03，设计稿 dev\\item_system\\超限锻造石与高难度.md §9）。
进入 difficulty 里标了 lock 的档（死亡 / 不可能）后七条诅咒全部生效；在这两档第一次打败某个区域的 Boss（和超限锻造石「每个 Boss 每档只掉一次」同一套，
dark_core 的 ovldrop 发石头时一起算）得到 1 片这个区域的碎片，凑满 5 片这一条自动反转成祝福（永久，存档的事件标记）。
区域 → 诅咒（REGIONS，默认按主题）；Boss → 区域是 data\\boss_curse_regions.json（dev\\item_system\\build_curse_regions.py 生成），本体里 7 个区域以外的（地下世界、法姆亚兹拉、最终 Boss）按流程等级归到最接近的区域，DLC 的不掉碎片。
七条（诅咒 / 反转后）：
  黯辉 gloom  大卢恩的激活效果摘掉 / 葛瑞克、拉塔恩、蒙葛特、拉卡德的换成数值翻倍的副本（GLOOM_DOUBLE）
  焚魂 burn   每秒损失 0.5% 生命 / 每秒回复 1%（changeHpRate，正数扣、负数回）
  众目 gaze   敌人发现你的距离 ×5 / ×0.05（sightSearchEnemyRate / hearingSearchEnemyRate）
  千变 vary   最近 vary_secs 秒里用过的招式种类越少伤害越低（只用 1 种 −60%，每多 1 种少降 15%）/ 每多 1 种 +10%（最多 +50%）：
              照 Golden Age 的多才多艺（用户 2026-11-09 重做）——玩家脚本在各招式的动作状态里挂招式标记（VARY_STATES，一种招式一个，持续 vary_secs 秒），
              dark_core 数身上有几种，给玩家挂档位效果（造成的伤害倍率，带状态图标）；诅咒渐进：变轻马上变，变重从 1 档起、每 vary_ramp 秒才再重 1 档（用户同日，刚开打别一下 −60%）。以前是按每个敌人看连续两下是不是同一类，看不见、也不好判断
  烙印 brand  每 15 秒附近一个敌人被烙上血月印记 5 秒（brand_secs，用户 2026-11-04「改为有间隔，而不是持续被烙印」；
              以前印记留到换下一个，只有一个敌人的 Boss 战等于一直被烙印）（自制特效 990004：被蚀的血月 + 一圈小月牙，悬在头上），它的攻击 ×2 /
              金色的 990005、受到的伤害 ×1.3，杀死它回复 20% 生命和专注（用户 2026-11-03：不用准星，另外做特效；make_sfx.py + sfx\\brand_mark.js）
  沉寂 echo   （原名回响，2026-11-04 用户「名字也跟着改一下」）每 5 秒没有命中敌人，造成的伤害 −5%，最多 5 层，命中敌人后清零（用户 2026-11-04「改成每10s没命中敌人 伤害降低5% 最多5层
              命中敌人后清零」「每5s吧」；以前是受到的伤害 3 秒后再回响一次 20%）/ 你的命中 1 秒后在敌人身上回响一次（20%，没改）
  蚀甲 erode  每被击中一次受到的伤害 +5%，10 秒，最多 5 层 / 受到的伤害 −25%（用户 2026-11-03 改）
对勇于挑战者的馈赠（revive；用户 2026-11-05，不是咒痕，没有碎片，咒痕页直接以祝福显示）：这两档里每次休息后第一次死亡满状态复活。
  玩家脚本在各个死亡入口拦下（sc/hks.py 的 DR_Revive，做法参考 Golden Age 的 Second Wind：不进死亡状态、回满血），挂 revive_secs 秒无敌（REVIVE_JUST）；
  dark_core 的 curses.rs 看到它就补满专注和精力、点亮 REVIVE_USED（存档，退出重进不会刷新），坐上赐福或真的死了回来才熄灭、再挂上 REVIVE_READY（带状态图标）。
事件（受击、攻击、跳劈、蓄力、施法、射击、防御反击、翻滚、致命一击）走玩家脚本的事件总线：LISTEN 这个标记效果挂在玩家身上时，
rr/affixes.py 的 runtime_parts 把它加进这些事件的监听表（CURSE_EVENTS），玩家脚本就发脉冲标记。
dll\\dark_core\\curses.txt（def_lines）；执行在 dark_core 的 curses.rs，界面是赐福「暗黑重铸」→「咒痕」（sc/wspages.py，只在高难度档列出来；dll\\dark_ui 只画这一页）。"""
from .common import *  # noqa: F401,F403

# (键, 中文名, 英文名, 诅咒说明, 祝福说明, 英文诅咒, 英文祝福)
CURSES = {
    'gloom': ('黯辉', 'Dimming', '大卢恩的激活效果不再生效', '葛瑞克、拉塔恩、蒙葛特、拉卡德的大卢恩激活效果变为两倍',
              'Great Rune activations have no effect', "Godrick's, Radahn's, Morgott's and Rykard's Great Rune activations are doubled"),
    'burn': ('焚魂', 'Soulburn', '灵魂被弒神火焰灼烧：每秒损失 {burn}% 生命', '受到祝福：每秒回复 {regen}% 生命',
             'Your soul burns in godslaying flame: lose {burn}% HP per second', 'Blessed: regain {regen}% HP per second'),
    'gaze': ('众目', 'Many Eyes', '敌人发现你的距离变为 {gaze} 倍', '几乎不会被敌人发现（被攻击后照常反击）',
             'Enemies notice you from {gaze}× as far', 'Enemies barely notice you (they still fight back when attacked)'),
    'vary': ('千变', 'Myriad Forms', '最近 {vary_secs} 秒里用过的招式种类越少，造成的伤害越低：只用 1 种时 −{vary_cmax}%，每多用 1 种少降 {vary_c}%（从 −{vary_c}% 起，每 {vary_ramp} 秒加重一档）',
             '最近 {vary_secs} 秒里每多用 1 种招式，造成的伤害 +{vary_b}%，最多 +{vary_bmax}%',
             'The fewer kinds of moves you used in the last {vary_secs}s, the less damage you deal: −{vary_cmax}% with one kind, {vary_c}% less for each extra kind (starts at −{vary_c}%, one step worse every {vary_ramp}s)',
             'Each extra kind of move used in the last {vary_secs}s: +{vary_b}% damage, up to +{vary_bmax}%'),
    'brand': ('烙印', 'Brand', '每 {brand_every} 秒附近一个敌人被烙上血月印记 {brand_secs} 秒，这期间它打你的伤害 ×{brand_atk}',
              '每 {brand_every} 秒附近一个敌人被烙上金色印记 {brand_secs} 秒，这期间它受到的伤害 ×{brand_take}，杀死它回复 {brand_heal}% 生命和专注',
              'Every {brand_every}s a nearby foe is branded with a blood moon for {brand_secs}s: meanwhile its damage to you ×{brand_atk}',
              'Every {brand_every}s a nearby foe is branded in gold for {brand_secs}s: meanwhile it takes ×{brand_take} damage; killing it restores {brand_heal}% HP and FP'),
    'echo': ('沉寂', 'Stillness', '每 {echo_every} 秒没有命中敌人，造成的伤害就降低 {echo_down}%，最多 {echo_down_max} 层；命中敌人后清零',
             '你的命中 {echo_hit} 秒后在敌人身上回响一次（{echo}%）',
             'Every {echo_every}s without hitting a foe, your damage drops by {echo_down}% (up to {echo_down_max} stacks); landing a hit clears it',
             'Your hits echo on the foe {echo_hit}s later ({echo}%)'),
    'erode': ('蚀甲', 'Corrosion', '每被击中一次，受到的伤害 +{erode}%，持续 {erode_secs} 秒，最多 {erode_max} 层', '受到的伤害 −{erode_bless}%',
              'Each hit taken: +{erode}% damage taken for {erode_secs}s, up to {erode_max} stacks', 'Damage taken −{erode_bless}%'),
}
# 区域（顺序同 data\boss_curse_regions.json 的 regions）：(中文, 英文, 诅咒)
REGIONS = [
    ('宁姆格福，啜泣半岛', 'Limgrave & Weeping Peninsula', 'gaze'),
    ('利耶尼亚', 'Liurnia', 'vary'),
    ('盖利德，龙墓', 'Caelid & Dragonbarrow', 'brand'),
    ('亚坛高原，王城', 'Altus Plateau & Leyndell', 'gloom'),
    ('格密尔火山', 'Mt. Gelmir', 'erode'),
    ('巨人山顶', 'Mountaintops of the Giants', 'burn'),
    ('化圣雪原，圣树，蒙格温', 'Snowfield, Haligtree & Mohgwyn', 'echo'),
]
# 碎片数：每个区域 3 位（0~5），共 21 个标记（93993~93999 + 92582~92595，2026-11-03 扫过没人引用；dev\event_flags\说明.md）
SHARD_FLAGS = list(range(93993, 94000)) + list(range(92582, 92596))
SHARD_BITS = 3
OPEN = 93092                             # 赐福「暗黑重铸」→「七咒」的打开请求（sc/wspages.py；应答 / 没界面和装备工坊共用）
LISTEN = 7304000
CURSE_EVENTS = ('hit', 'attack', 'jatk', 'charged', 'cast_new', 'shot_new', 'throw_new', 'aroma', 'guard_counter', 'roll', 'crit')
BURN, GAZE = (7304010, 7304011), (7304020, 7304021)
ERODE_BLESS, ERODE0 = 7304030, 7304031                    # 诅咒 1~5 层 = 7304031~7304035
BRAND = (7304040, 7304041)
VARY_C0, VARY_B0 = 7304051, 7304061                       # 诅咒 1~4 档、祝福 1~5 档（玩家身上，造成的伤害倍率）
VARY_MARK0 = 7304200                                      # 招式标记：VARY_STATES 第 i 种 = VARY_MARK0 + i
VARY_ICON_C0, VARY_ICON_B0 = 20840, 20860                 # 状态图标（extract_affixes.STATUS_ICONS 的 myriad / myriad_up，20600 + 20 × 12 / 13）
# 算「一种招式」的动作状态（玩家脚本的 <名字>_onUpdate）：Golden Age 多才多艺的 58 种（单手 / 双手 / 双持的轻击各段、重击蓄满 / 没蓄满、跑攻、滚攻、
# 蹲攻、后跳攻击、防御反击、架盾时攻击），加上左手、跳劈、弓弩、施法（左右手各段）、战技、投掷、调香、致命一击、梯子上的攻击
VARY_STATES = ['AttackRightLight1', 'AttackRightLight2', 'AttackRightLight3', 'AttackRightLight4', 'AttackRightLight5', 'AttackRightLight6', 'AttackRightLightStep', 'AttackRightLightStealth', 'AttackRightLightFastStep', 'AttackRightLightDash', 'AttackRightHeavyDash', 'AttackRightWhileGuard', 'AttackRightHeavy1Start', 'AttackRightHeavy1End', 'AttackRightHeavy2Start', 'AttackRightHeavy2End', 'AttackRightHeavySpecial1Start', 'AttackRightHeavySpecial1End', 'AttackRightHeavySpecial2Start', 'AttackRightHeavySpecial2End', 'AttackRightSpecial1', 'AttackRightSpecial2', 'AttackRightBackstep', 'AttackDualLight1', 'AttackDualLight2', 'AttackDualLight3', 'AttackDualLight4', 'AttackDualLight5', 'AttackDualLight6', 'AttackDualDash', 'AttackDualRolling', 'AttackDualStealth', 'AttackDualBackStep', 'AttackBothLight1', 'AttackBothLight2', 'AttackBothLight3', 'AttackBothLight4', 'AttackBothLight5', 'AttackBothLight6', 'AttackBothHeavy1Start', 'AttackBothHeavy1End', 'AttackBothHeavy2Start', 'AttackBothHeavy2End', 'AttackBothHeavySpecial1Start', 'AttackBothHeavySpecial1End', 'AttackBothHeavySpecial2Start', 'AttackBothHeavySpecial2End', 'AttackBothSpecial1', 'AttackBothSpecial2', 'AttackBothDash', 'AttackBothHeavyDash', 'AttackBothLightStep', 'AttackBothLightStealth', 'AttackBothBackstep', 'AttackRightLightCounter', 'AttackRightHeavyCounter', 'AttackBothLightCounter', 'AttackBothHeavyCounter', 'AttackLeftLight1', 'AttackLeftHeavy1', 'AttackLeftHeavy2', 'AttackLeftHeavy3', 'AttackLeftHeavy4', 'AttackLeftHeavy5', 'AttackLeftHeavy6', 'AttackBothLeft1', 'AttackBothLeft2', 'AttackBothLeft3', 'AttackBothLeftDash', 'AttackBothLeftStep', 'AttackBothLeftSpecial1', 'AttackBothLeftSpecial2', 'AttackBothLeftSpecial3', 'AttackBothLeftSpecial4', 'AttackBothLeftSpecial5', 'AttackBothLightGuard', 'JumpAttack_Start_Falling', 'JumpAttack_Start_Falling_F', 'JumpAttack_Start_Falling_D', 'AttackArrowRightFire', 'AttackArrowRightFireDash', 'AttackArrowRightFireStep', 'AttackArrowLeftFire', 'AttackArrowLeftFireDash', 'AttackArrowLeftFireStep', 'AttackCrossbowRightFire_Upper', 'AttackCrossbowLeftFire_Upper', 'AttackCrossbowBothLeftFire_Upper', 'AttackCrossbowBothRightFire_Upper', 'MagicFireRight_Upper', 'MagicFireRight2_Upper', 'MagicFireRight3_Upper', 'MagicFireLeft_Upper', 'MagicFireLeft2_Upper', 'MagicFireLeft3_Upper', 'MagicFireRightJump_Upper', 'MagicFireLeftJump_Upper', 'SwordArtsOneShot', 'SwordArtsOneShotComboEnd', 'SwordArtsOneShotComboEnd_2', 'SwordArtsLoopLoop', 'SwordArtsBothLoopLoop', 'SwordArtsLeftLoopLoop', 'SwordArtsStanceAttackLightStart', 'SwordArtsStanceAttackHeavyStart', 'DrawStanceRightAttackLight', 'DrawStanceRightAttackHeavy', 'DrawStanceRightAttackHeavy2', 'SwordArtsRolling', 'SwordArtsOneShotShieldLeft', 'SwordArtsOneShotShieldBoth', 'SwordArtsLeftGuardCounter', 'SwordArtsBothGuardCounter', 'SwordArtsArrowFire', 'ItemThrowKnife_Upper', 'ItemThrowBottle_Upper', 'ItemThrowBigBottle_Upper', 'ItemThrowSpear_Upper', 'ItemAromaWide_Upper', 'ItemAromaUp_Upper', 'ItemAromaBreath_Upper', 'ItemAromaFront_Upper', 'ThrowBackStab', 'ThrowAtk', 'LadderAttackUpRight', 'LadderAttackDownRight']
ECHO_DOWN0 = 7304081                                      # 回响诅咒 1~5 层（造成的伤害 ×(1 − 层 × echo_down%)）
# 沉寂 1~5 层的状态图标（用户 2026-11-04「补一下沉寂的buff图标」）：「死亡的咒痕」道具画 + 下降箭头 + 层数，dev\item_system\make_icons.py 画进
# data\menu\dr_status.dds；编号 = 20600 + 20 × 它在 extract_affixes.STATUS_ICONS 里的序号（stillness 是第 9 个）+ 层数 − 1，只画到 5 层
ECHO_ICON0, ECHO_ICON_N = 20780, 5
# 蚀甲 1~5 层的状态图标（用户 2026-11-04「蚀甲也要把图标加上」）：熔炉鳞护符的画 + 下降箭头 + 层数，同上（corrosion 是第 10 个）
ERODE_ICON0, ERODE_ICON_N = 20800, 5
SPELL_FLAGS = ('magParamChange', 'miracleParamChange', 'shamanParamChange')   # 攻击方倍率对魔法 / 祷告 / 咒术也生效（同 rr/difficulty.py）
REVIVE_READY, REVIVE_JUST = 7304090, 7304091              # 复活还能用（状态图标）/ 刚复活（无敌、光效）
REVIVE_USED = 93488                                       # 这次休息后用过了（dev\event_flags\说明.md）
REVIVE_VFX = 8535                                         # 原版亵渎圣剑「夺取者的火焰」回血的光效行（同 rr/nightmare.py 的 DRAIN_FROM）
GIFT_ICON = 20820                                         # 状态图标：替身枝的画（extract_affixes.STATUS_ICONS 的 gift，20600 + 20 × 11）
GIFT = ('对勇于挑战者的馈赠', 'A Gift to the Daring', '每次休息后，第一次死亡时满状态复活，并有 {revive_secs} 秒无敌',
        'After each rest, your first death revives you at full strength, invincible for {revive_secs}s')
# 叙事（dev\\narrative\\叙事方案.md）：咒痕页右栏最下面的来历（中, 英；诅咒和反转后都是这一段）、反转后接的提示、开场、七道全部反转
LORE = {
    'gaze': ('史东薇尔的战鹰在风暴中盘旋，俯视着踏上宁姆格福的每一个人。', 'The stormhawks of Stormveil wheel in the gale, looking down on all who set foot in Limgrave.'),
    'vary': ('魔法学院雷亚卢卡利亚设有多间教室，各自传授不同的魔法。只通晓一种魔法的学徒，戴不上辉石头罩。',
             'The Academy of Raya Lucaria keeps many classrooms, each teaching its own sorcery. A student versed in only one cannot wear a glintstone crown.'),
    'brand': ('盖利德是拉塔恩将军与玛莲妮亚交战的最终战场。红狮子的士兵会在最危险的敌人身上留下血红的印记。',
              'Caelid was the final battlefield of General Radahn and Malenia. Redmane soldiers leave a blood-red mark on the most dangerous foe.'),
    'gloom': ('王城罗德尔是黄金树之城。破碎战争之后，碎片君王的大卢恩都失去了恩惠的力量。',
              'Leyndell is the city of the Erdtree. After the Shattering, the Great Runes of the shardbearers lost their benediction.'),
    'erode': ('英雄们觐见“亵渎君王”拉卡德，连同铠甲没入大蛇的体内。在蛇腹之中，铠甲会一层一层被蚀穿。',
              'Heroes who came before Rykard, Lord of Blasphemy, sank into the great serpent, armor and all. In its belly, that armor is eaten through layer by layer.'),
    'burn': ('玛利喀斯封印命定之死之后，黑焰失去了狩猎神祇的力量。封印解开，黑焰的力量也回来了。',
             'When Maliketh sealed Destined Death, the black flame lost its power to slay gods. With the seal broken, that power has returned.'),
    'echo': ('化圣雪原是不被选上的人们走的路。背离引导的褪色者，在那片寂静里最为心慌。',
             'The Consecrated Snowfield is the road of those unchosen. Tarnished who strayed from guidance feel their dread most in its silence.'),
    'gift': ('步入死亡的褪色者，会被引导回赐福。刚在赐福休息过的人，能够挡下一次死亡。',
             'The Tarnished who walk into death are led back to grace. One who has just rested at grace can stave off a single death.'),
}
REV_NOTES = {
    'gaze': ('敌人的目光移开了。', 'Enemy eyes have turned away.'),
    'vary': ('招式的变化化作了力量。', 'Changing forms has become strength.'),
    'brand': ('血红的印记化作了金色。', 'The blood-red mark has turned to gold.'),
    'gloom': ('大卢恩的恩惠倍增了。', 'The benediction of the Great Runes has doubled.'),
    'erode': ('身上的侵蚀消退了。', 'The corrosion on your body has faded.'),
    'burn': ('灵魂的灼烧化作了赐福。', 'The burning of your soul has become a blessing.'),
    'echo': ('寂静之中传来了回响。', 'An echo sounds within the silence.'),
}
# 第一次进入「死亡」时的开场（用户 2026-11-13 改成击败黑剑才能进入：封印在玛利喀斯倒下时就解开了；
# 「应该是褪色者主动踏上 而不是被找上」→ 写褪色者自己迎向命定之死）
OPEN_NOTES = (('你迎向了命定之死。', 'You have gone forth to meet Destined Death.'),
              ('身上刻下了七道咒痕。', 'Seven cursemarks have been carved into you.'))
ALL_NOTE = ('七道咒痕尽数化为祝福。', 'All seven cursemarks have become blessings.')
OPEN_SEEN = 93686                                         # 开场提示放过了（存档，每个角色一份；dev\event_flags\说明.md）
GLOOM_REMOVE = (600, 610, 620, 630, 640, 649, 650, 651)   # 大卢恩的激活效果（葛瑞克 600、拉塔恩 610、蒙葛特 620、拉卡德 630、蒙格 640 / 649、玛莲妮亚 650 / 651）
GLOOM_DOUBLE = {600: 7304070, 610: 7304071, 620: 7304072, 630: 7304073}
GLOOM_SOUL, GLOOM_SOUL_DOUBLE = 500030, 7304074           # 拉卡德：杀敌时挂的回血（applyIdOnGetSoul），翻倍的副本
PLAYER_TEMPLATE = 360400                                  # 长尾猫护符的效果（常驻、挂给自己；同 rr/difficulty.py）
ENEMY_TEMPLATE = 90030                                    # 敌人身上的（同 rr/hpunify.py：去掉「咒死无效」那一位）
RETICLE_VFX = 990001                                      # 猎印准星的光效行（词条库建的，挂点 220），照它复制、持续特效换成血月印记
RETICLE_SFX = (990004, 990005)                            # 血月印记：诅咒血红 / 反转后金色（make_sfx.py 打包的自制特效）
DEFAULT = dict(burn=0.5, regen=1.0, gaze=5.0, gaze_bless=0.05, vary_c=15, vary_cmax=60, vary_b=10, vary_bmax=50, vary_secs=20, vary_ramp=2.5,
               brand_every=15, brand_secs=5, brand_atk=2.0, brand_take=1.3, brand_heal=20, brand_range=20, echo=20, echo_hurt=3, echo_hit=1, echo_range=1000,
               echo_every=5, echo_down=5, echo_down_max=5,
               erode=5, erode_secs=10, erode_max=5, erode_bless=25, shards=5, revive=True, revive_secs=2)


def cfg(S):
    c = S.get('curses') or {}
    if not c.get('enabled', True):
        return None
    out = dict(DEFAULT)
    out.update({k: c[k] for k in DEFAULT if k in c})
    return out


def texts(c):
    """{键: (中文名, 英文名, 中文诅咒, 中文祝福, 英文诅咒, 英文祝福)}，数值按设置填好"""
    v = {k: ('%g' % x if isinstance(x, float) else x) for k, x in c.items()}
    return {k: (t[0], t[1]) + tuple(x.format(**v) for x in t[2:]) for k, t in CURSES.items()}


def build(ctx):
    ctx.curses = None
    c = cfg(ctx.S)
    from .hpunify import flags as lock_flags
    if not c or not lock_flags(ctx.S):
        return
    S = erlib.Param(ctx.bnd.get('SpEffectParam.param'))
    V = erlib.Param(ctx.bnd.get('SpEffectVfxParam.param'))
    L = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffect.xml')))[0]}
    VL = {t[0]: t for t in pdm.layout(pdm.load(os.path.join(ctx.data_dir, 'SpEffectVfx.xml')))[0]}
    put = lambda lay, row, f, v: struct.pack_into('<' + lay[f][1], row, lay[f][2], v)
    get = lambda row, f: struct.unpack_from('<' + L[f][1], row, L[f][2])[0]

    def bit(row, f, on):
        o, b = L[f][2], L[f][3]
        row[o] = (row[o] | (1 << b)) if on else (row[o] & ~(1 << b))

    def add(rid, row):
        if rid in S.rows:
            raise RuntimeError('咒痕：效果编号 %d 已经有人用了' % rid)
        S.add_row(rid, bytes(row))

    def player():
        """玩家身上的：常驻、不存档、死了不删、休息不清（同难度效果；dark_core 自己补挂、摘掉）"""
        row = bytearray(S.rows[PLAYER_TEMPLATE])
        put(L, row, 'iconId', -1)
        put(L, row, 'effectEndurance', -1.0)
        put(L, row, 'fallDamageRate', 1.0)
        put(L, row, 'spCategory', 0)
        put(L, row, 'saveCategory', -1)
        bit(row, 'eraseOnBonfireRecover', False)
        bit(row, 'dontDeleteOnDead', True)
        return row

    def enemy():
        row = bytearray(S.rows[ENEMY_TEMPLATE])
        bit(row, 'disableCurse', False)
        put(L, row, 'iconId', -1)
        put(L, row, 'effectEndurance', -1.0)
        put(L, row, 'spCategory', 0)
        return row
    CUTS = ('slashDamageCutRate', 'blowDamageCutRate', 'thrustDamageCutRate', 'neutralDamageCutRate',
            'magicDamageCutRate', 'fireDamageCutRate', 'thunderDamageCutRate', 'darkDamageCutRate')
    ATKS = ('physicsAttackRate', 'magicAttackRate', 'fireAttackRate', 'thunderAttackRate', 'darkAttackRate')
    add(LISTEN, player())                                   # 只是标记：玩家脚本见到它就发七咒要的事件
    for n in range(1, int(c['echo_down_max']) + 1):          # 回响诅咒：第 n 层造成的伤害 ×(1 − n × echo_down%)，魔法 / 祷告也算
        row = player()
        for f in ATKS:
            put(L, row, f, max(0.0, 1 - n * float(c['echo_down']) / 100.0))
        for f in SPELL_FLAGS:
            bit(row, f, True)
        put(L, row, 'iconId', ECHO_ICON0 + min(n, ECHO_ICON_N) - 1)
        add(ECHO_DOWN0 + n - 1, row)
    for rid, rate in zip(BURN, (float(c['burn']), -float(c['regen']))):
        row = player()
        put(L, row, 'changeHpRate', rate)
        put(L, row, 'motionInterval', 1.0)
        add(rid, row)
    for rid, rate in zip(GAZE, (float(c['gaze']), float(c['gaze_bless']))):
        row = player()
        put(L, row, 'sightSearchEnemyRate', rate)
        put(L, row, 'hearingSearchEnemyRate', rate)
        add(rid, row)
    row = player()
    for f in CUTS:
        put(L, row, f, 1 - float(c['erode_bless']) / 100)
    add(ERODE_BLESS, row)
    for n in range(1, int(c['erode_max']) + 1):
        row = player()
        for f in CUTS:
            put(L, row, f, 1 + float(c['erode']) * n / 100)
        put(L, row, 'iconId', ERODE_ICON0 + min(n, ERODE_ICON_N) - 1)
        add(ERODE0 + n - 1, row)
    # 烙印：光效行照猎印准星的（990001，挂点 220）复制、持续特效换成血月印记（make_sfx.py 打包的 990004 / 990005）
    if RETICLE_VFX not in V.rows:
        raise RuntimeError('咒痕：没有猎印准星的光效行 %d（词条库没建）' % RETICLE_VFX)
    for k, (rid, sfx) in enumerate(zip(BRAND, RETICLE_SFX)):
        if sfx in V.rows:
            raise RuntimeError('咒痕：光效行 %d 已经有人用了' % sfx)
        v = bytearray(V.rows[RETICLE_VFX])
        put(VL, v, 'midstSfxId', sfx)
        V.add_row(sfx, bytes(v))
        row = enemy()
        put(L, row, 'vfxId', sfx)
        for f in (ATKS if k == 0 else CUTS):
            put(L, row, f, float(c['brand_atk']) if k == 0 else float(c['brand_take']))
        add(rid, row)
    # 千变：招式标记（一种招式一个，持续 vary_secs 秒，玩家脚本在动作状态里每帧挂）；玩家身上造成的伤害倍率（诅咒 1~4 档、祝福 1~5 档，带状态图标）
    nc = int(round(float(c['vary_cmax']) / float(c['vary_c'])))
    nb = int(round(float(c['vary_bmax']) / float(c['vary_b'])))
    for i in range(len(VARY_STATES)):
        row = player()
        put(L, row, 'effectEndurance', float(c['vary_secs']))
        bit(row, 'dontDeleteOnDead', False)
        add(VARY_MARK0 + i, row)
    for k, (rid0, icon0, nn, sign, step) in enumerate(((VARY_C0, VARY_ICON_C0, nc, -1, float(c['vary_c'])), (VARY_B0, VARY_ICON_B0, nb, 1, float(c['vary_b'])))):
        for n in range(1, nn + 1):
            row = player()
            for f in ATKS:
                put(L, row, f, max(0.05, 1 + sign * step * n / 100))
            for f in SPELL_FLAGS:
                bit(row, f, True)
            put(L, row, 'iconId', icon0 + min(n, (4, 5)[k]) - 1)
            add(rid0 + n - 1, row)
    # 黯辉反转：大卢恩激活效果的翻倍副本（照原版整行复制，只翻数值；拉卡德的杀敌回血另复制一份翻倍）
    STATS = ('addLifeForceStatus', 'addWillpowerStatus', 'addEndureStatus', 'addVitalityStatus', 'addStrengthStatus',
             'addDexterityStatus', 'addMagicStatus', 'addFaithStatus', 'addLuckStatus')
    for src, rid in GLOOM_DOUBLE.items():
        row = bytearray(S.rows[src])
        for f in STATS:
            if get(row, f):
                put(L, row, f, get(row, f) * 2)
        for f in ('maxHpRate', 'maxMpRate', 'maxStaminaRate'):
            if abs(get(row, f) - 1.0) > 1e-6:
                put(L, row, f, 1 + (get(row, f) - 1) * 2)
        if get(row, 'applyIdOnGetSoul') == GLOOM_SOUL:
            put(L, row, 'applyIdOnGetSoul', GLOOM_SOUL_DOUBLE)
        add(rid, row)
    soul = bytearray(S.rows[GLOOM_SOUL])
    for f in ('changeHpRate', 'changeHpPoint'):
        put(L, soul, f, get(soul, f) * 2)
    add(GLOOM_SOUL_DOUBLE, soul)
    if c['revive']:
        row = player()
        put(L, row, 'iconId', GIFT_ICON)
        add(REVIVE_READY, row)
        row = player()
        put(L, row, 'effectEndurance', float(c['revive_secs']))
        for f in CUTS:
            put(L, row, f, 0.0)
        put(L, row, 'saReceiveDamageRate', 0.0)
        if REVIVE_VFX in V.rows:
            put(L, row, 'vfxId', REVIVE_VFX)
        add(REVIVE_JUST, row)
    ctx.bnd.put('SpEffectParam.param', S.serialize())
    ctx.bnd.put('SpEffectVfxParam.param', V.serialize())
    ctx.curses = c
    ctx.features['curses'] = {'listen': LISTEN, 'open': OPEN, 'tiers': lock_flags(ctx.S),   # tiers：入口只在这几档列出来
                              'vary': {s: VARY_MARK0 + i for i, s in enumerate(VARY_STATES)},          # sc/hks.py 的千变招式标记
                              'revive': [REVIVE_READY, REVIVE_JUST] if c['revive'] else None}   # sc/hks.py 的 DR_Revive
    ctx.report.append('咒痕：标了 lock 的难度档里七道咒痕（效果 %d~%d），区域 Boss 每档第一次击败给 1 片碎片、%d 片反转（标记 %d~%d、%d~%d）' % (
        LISTEN, GLOOM_SOUL_DOUBLE, int(c['shards']), SHARD_FLAGS[0], SHARD_FLAGS[6], SHARD_FLAGS[7], SHARD_FLAGS[-1]))
    if c['revive']:
        ctx.report.append('对勇于挑战者的馈赠：这几档每次休息后第一次死亡满状态复活（效果 %d / %d，标记 %d，无敌 %g 秒）' % (
            REVIVE_READY, REVIVE_JUST, REVIVE_USED, float(c['revive_secs'])))


def def_lines(ctx):
    """dll\\dark_core\\curses.txt（格式见 dark_core 的 curses.rs）"""
    c = getattr(ctx, 'curses', None)
    if not c:
        return []
    from .hpunify import flags as lock_flags
    tx = texts(c)
    out = ['tier %d' % f for f in lock_flags(ctx.S)]
    out += ['listen %d' % LISTEN, 'shards %d' % int(c['shards'])]
    for k, (zh, en, key) in enumerate(REGIONS):
        fl = SHARD_FLAGS[k * SHARD_BITS:(k + 1) * SHARD_BITS]
        out.append('region\t%d\t%s\t%s\t%s\t%s' % (k, key, ','.join(map(str, fl)), zh, en))
    for key, t in tx.items():
        out.append('text\t%s\t%s' % (key, '\t'.join(t)))
    out += ['burn %d %d' % BURN, 'gaze %d %d' % GAZE,
            'erode %d %g %s' % (ERODE_BLESS, float(c['erode_secs']), ','.join(str(ERODE0 + n) for n in range(int(c['erode_max'])))),
            'brand %d %d %g %g %g %g' % (BRAND + (float(c['brand_every']), float(c['brand_range']), float(c['brand_heal']), float(c['brand_secs']))),
            'vary %s %s' % (','.join(str(VARY_C0 + n) for n in range(int(round(float(c['vary_cmax']) / float(c['vary_c']))))),
                            ','.join(str(VARY_B0 + n) for n in range(int(round(float(c['vary_bmax']) / float(c['vary_b'])))))),
            'varymark %d %d' % (VARY_MARK0, len(VARY_STATES)), 'varyramp %g' % float(c['vary_ramp']),
            'gloom %s %s' % (','.join(map(str, GLOOM_REMOVE)), ','.join('%d:%d' % kv for kv in GLOOM_DOUBLE.items())),
            'echo %g %g %g %g' % (float(c['echo']), float(c['echo_hurt']), float(c['echo_hit']), float(c['echo_range'])),
            'echodown %g %s' % (float(c['echo_every']), ','.join(str(ECHO_DOWN0 + n) for n in range(int(c['echo_down_max']))))]
    if c['revive']:
        v = {'revive_secs': '%g' % float(c['revive_secs'])}
        out += ['revive %d %d %d' % (REVIVE_READY, REVIVE_JUST, REVIVE_USED),
                'gift\t%s\t%s\t%s\t%s' % (GIFT[0], GIFT[1], GIFT[2].format(**v), GIFT[3].format(**v))]
    out += ['lore\t%s\t%s\t%s' % (k, z, e) for k, (z, e) in LORE.items()] + ['openseen %d' % OPEN_SEEN]
    regions = json.load(open(os.path.join(ctx.data_dir, 'boss_curse_regions.json'), encoding='utf-8'))['bosses']
    out += ['boss %s %d' % (k, v['region']) for k, v in sorted(regions.items(), key=lambda kv: int(kv[0]))]
    return out
