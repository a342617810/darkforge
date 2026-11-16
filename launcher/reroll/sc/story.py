# -*- coding: utf-8 -*-
"""加载提示里的背景文字（dev\\narrative\\叙事方案.md）：替换原版的联机类提示（模组里用不上原版联机）。
不新增编号：游戏怎么抽提示没查过，替换现有编号最稳。LoadingTitle / LoadingText 都在 menu_dlc02，走 scripts.py 的 texts() 合并。"""

# 编号: (中文标题, 中文, 英文标题, 英文)
TIPS = {
    101: ('流纹文字', '装备上的词条，是钢铁皱褶内的流纹文字。在远古时代，铁匠用这些文字固定武器的灵魂。',
          'Smithscript', 'The affixes on gear are smithscript, written in the folds of the steel. In ancient times, smiths used such script to bind the soul of an armament.'),
    102: ('未鉴定物品', '来历不明的装备，流纹文字已经模糊。在赐福鉴定后，才能辨认它的力量。',
          'Unidentified Items', 'On gear of unknown origin, the smithscript has faded. Identify it at a site of grace to read what power it holds.'),
    105: ('铁匠修古', '圆桌厅堂的铁匠修古，是被锁链束缚的俘虏。他并不排斥替褪色者锻造武器。',
          'Smithing Master Hewg', 'Hewg, blacksmith of the Roundtable Hold, is a prisoner in chains. He does not mind forging armaments for the Tarnished.'),
    106: ('修古的誓言', '修古向玛莉卡女王立下誓言，要锻造弒神武器。祈祷的时光，是他仅存的自由。',
          "Hewg's Oath", 'Hewg swore an oath to Queen Marika to forge a godslaying armament. His hours of prayer are the only freedom left to him.'),
    107: ('调灵师', '修古曾受一位调灵师的照顾。他把所知的调灵知识，全部告诉了来到圆桌厅堂的女孩。',
          'Spirit Tuner', 'Hewg was once looked after by a spirit tuner. All he knew of the art, he told to the girl who came to the Roundtable Hold.'),
    108: ('流浪民族', '流浪民族曾组成大商队行商。被活埋地底深处之后，他们仍在做着生意。',
          'The Nomads', 'The nomadic people once traded in a great caravan. Buried alive far underground, they still keep up their trade.'),
    109: ('暗黑商店', '暗黑商店的货物来自地底。每当一个地区的头目倒下，交易项目就会增加。',
          'Dark Shop', "The Dark Shop's wares come from below. Whenever a region's boss falls, more items go on sale."),
    110: ('回购', '卖出的装备，流浪民族的商人不会转手。地底深处的货物已经所剩无几。',
          'Buyback', 'The nomadic merchants do not resell the gear you sell them. Few goods remain so far underground.'),
    # 用户 2026-11-13：要先击败黑剑才能进入「死亡」（sc/difficulty.py 的门槛）
    111: ('命定之死', '黄金律法成立之时，命定之死就被去除，由「黑剑」玛利喀斯封印。击败玛利喀斯、释放命定之死之后，才能踏上「死亡」的道路。',
          'Destined Death', 'When the Golden Order was established, Destined Death was removed, and Maliketh, the Black Blade, sealed it away. '
          'Only once Maliketh is defeated and Destined Death released can the path of Death be walked.'),
    113: ('咒痕', '半神初次死去时，身上会留下咒痕。进入「死亡」难度后，褪色者身上也会刻下七道。',
          'Cursemarks', 'When a demigod first dies, a cursemark is left on the body. On the Death difficulty, seven are carved into the Tarnished as well.'),
    116: ('魇化', '死根沿着地底的大树根，蔓延到交界地各处。魇化的敌人，据说是受到死根侵蚀的人。',
          'Nightmare Enemies', 'Deathroot has spread along the great roots below, across all the Lands Between. Nightmare enemies are said to be those eroded by it.'),
    119: ('魇火', '魇化的敌人死后，身上会留下紫色的魇火。夺取魇火的举动，与拉卡德的亵渎如出一辙。',
          'Nightmare Embers', 'Nightmare enemies leave purple embers when they die. Seizing them is no different from the blasphemy of Rykard.'),
}


def texts(cx, key):
    t, b = (0, 1) if key == 'zh' else (2, 3)
    return {'LoadingTitle': {i: v[t] for i, v in TIPS.items()}, 'LoadingText': {i: v[b] for i, v in TIPS.items()}}
