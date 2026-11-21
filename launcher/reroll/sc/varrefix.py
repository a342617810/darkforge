# -*- coding: utf-8 -*-
"""白面具瓦雷支线最后一环的兜底（用户 2026-11-21「修一下白面具任务最后卡在伸出指头 没有发放最后的奖励」，
「不给勋章 之前不是改过支线最后一环的奖励么 用那个就行了」「刺手指可以正常完成 但是奖励只给传说」）。
原版流程（对话 t301006000 + 玫瑰教堂 m60_35_44 的事件）：
  1. 交了浸血的布：说完「……来吧，请伸出你的手指。」点亮 STEP_TALK，对话结束；
  2. 接着的对话点亮请求 REQ_PLAYER / REQ_VARRE，等公共函数事件 90005740（玩家）/ 90005741（瓦雷）回 ACK_PLAYER / ACK_VARRE：
     玩家 2 秒内走到瓦雷面前的标记点（0.35 米以内，事件动作带的特效 9900 要一直在）、瞬移过去、播刺手指的动作 90201；
  3. 两边都回了，对话等 11.5 秒说「刚才的惨叫真是动听啊」，点亮 STEP_SCENE、SCENE_DONE，没拿过血指（BLOODY_FLAG）给掉落表 BLOODY_LOT；
  4. 再对话给纯血骑士勋章（掉落表 100320，点亮 MEDAL_DONE）；rr/unidentified.py 在 100320 后面接了 3 行未鉴定传说（支线最后一环），一起给。
第 2 步失败时（没走到、动作被打断，或者玩家那个事件根本没跑：联机当客机时它开头就结束），对话要么直接结束、要么一直干等，
STEP_SCENE 没亮，再对话又从第 2 步重来，一直卡在这一段。对话、事件、地图、参数和原版一样，运行时是什么打断的查不到，这里加一个公共事件兜底：
  - STEP_SCENE 亮着就结束（已经过了这一步）；
  - 等请求亮；8 秒后请求还亮着、两个回应却没齐（原版 3 秒内就齐）→ 对话在干等：替两个事件回应，对话照原版说完、点亮 STEP_SCENE、给血指，
    记下「卡过」（STUCK）；回应齐了就是正常在播，不管；
  - 等请求熄灭（这一段结束或被打断）、再等 1 秒：没卡过而 STEP_SCENE 亮了 → 正常做完，重新开始（开头就结束）；
    卡过、或者 STEP_SCENE 没亮 → 替这一步做完（STEP_SCENE、SCENE_DONE、没拿过的血指），奖励只发接上的那 3 行传说、不发勋章：
    点亮 MEDAL_DONE（对话不再走给勋章那一段），直接发那 3 行（获取标记和勋章同一个，之后也领不到勋章）。
    重随没写那 3 行从哪起（features.json 的 quest_final_rows）就不点 MEDAL_DONE，照原版下次对话给勋章。"""
import emevd

# 不存档的 1040490 块（dev\event_flags\说明.md），读档都重新跑；720 起那一段会被乱写（dark_sell 的难度请求以前在那里），
# 用斗技场传送（872~874）和音效（880）中间空着的
EVENT = 1040490876              # VARRE_EVENT
STUCK = 1040490877              # 这一次对话卡过（只在这个事件里用，同一块不存档）
STEP_TALK = 1035449225           # 「伸出你的手指」那段说完
STEP_SCENE = 1035449227          # 刺手指这一段做完（对话看它决定走不走给勋章那一段）
SCENE_DONE = 9432                # 同一段里对话还会点亮的
MEDAL_DONE = 1035449226          # 给勋章那一段做完
REQ_PLAYER, ACK_PLAYER = 1035442705, 1035442706
REQ_VARRE, ACK_VARRE = 1035442708, 1035442709
BLOODY_FLAG, BLOODY_LOT = 60270, 100340      # 血指（这一段结尾没拿过才给）
MEDAL_LOT = 100320               # 勋章 + 接上的传说（quest_final_rows 按这个找）
STUCK_SECS = 8.0
SETTLE_SECS = 1.0


def wait_flag(flag, on, group=0):
    """IF Event Flag(组, 状态, 标记)"""
    return emevd.ins(3, 0, ('s8', group), ('u8', int(on)), ('u8', 0), ('u32', flag))


def set_flag(flag, on=True):
    return emevd.ins(2003, 66, ('u8', 0), ('u32', flag), ('u8', int(on)))


def end_if(flag, on, restart):
    """END IF Event Flag：restart = 重新开始，否则结束"""
    return emevd.ins(1003, 2, ('u8', int(restart)), ('u8', int(on)), ('u8', 0), ('u32', flag))


def skip_if(lines, on, flag):
    """SKIP IF Event Flag：标记是 on 就跳过后面 lines 行"""
    return emevd.ins(1003, 1, ('u8', lines), ('u8', int(on)), ('u8', 0), ('u32', flag))


def body(legend_lot):
    """legend_lot：接在勋章后面的那 3 行传说的第一行；None = 不知道，照原版给勋章"""
    reward = [set_flag(MEDAL_DONE), emevd.ins(2003, 4, ('s32', legend_lot))] if legend_lot else []
    return [
        end_if(STEP_SCENE, True, False),                                  # 0 这一步已经过了
        wait_flag(REQ_PLAYER, True),                                       # 1 对话开始刺手指这一段
        wait_flag(REQ_PLAYER, False, -1),                                  # 2 请求熄了，或者
        emevd.ins(1, 0, ('s8', -1), ('f32', STUCK_SECS)),                  # 3 过了 8 秒
        emevd.ins(0, 0, ('s8', 0), ('u8', 1), ('s8', -1)),                 # 4
        skip_if(7, False, REQ_PLAYER),                                     # 5 请求已经熄了 → 13
        skip_if(2, False, ACK_PLAYER),                                     # 6 回应没齐 → 9
        skip_if(1, False, ACK_VARRE),                                      # 7 回应没齐 → 9
        emevd.ins(1000, 3, ('u8', 3)),                                     # 8 回应齐了（正常在播）→ 12
        set_flag(ACK_PLAYER),                                              # 9 对话在干等：替两个事件回应，对话接着往下走
        set_flag(ACK_VARRE),                                               # 10
        set_flag(STUCK),                                                   # 11
        wait_flag(REQ_PLAYER, False),                                      # 12 等这一段结束（对话说完 / 被打断）
        emevd.ins(1001, 0, ('f32', SETTLE_SECS)),                          # 13
        skip_if(2, True, STUCK),                                           # 14 卡过 → 17
        end_if(STEP_SCENE, True, True),                                    # 15 对话自己正常做完了
        end_if(STEP_TALK, False, True),                                    # 16
        set_flag(STUCK, False),                                            # 17 替这一步做完
        set_flag(STEP_SCENE),
        set_flag(SCENE_DONE),
        skip_if(1, True, BLOODY_FLAG),
        emevd.ins(2003, 4, ('s32', BLOODY_LOT)),
    ] + reward + [
        emevd.ins(1000, 4, ('u8', 1)),                                     # 重新开始（开头结束）
    ]


def legend_lot(cx):
    v = (cx.feat.get('quest_final_rows') or {}).get(str(MEDAL_LOT))
    return int(v) if v else None


def events(cx, e, ev0):
    if any(ev['id'] == EVENT for ev in e['events']):
        raise RuntimeError('白面具兜底：公共事件 %d 已经被用了' % EVENT)
    lot = legend_lot(cx)
    e['events'].append({'id': EVENT, 'rest': 0, 'ins': body(lot), 'params': []})
    ev0['ins'].append(emevd.ins(2000, 0, ('s32', 0), ('u32', EVENT), ('u32', 0)))
    # 句子里别带「没」「失败」「跳过」：scripts.py 会把带这些字的当成问题报出来
    cx.notes.append('白面具支线：刺手指那一段卡住时由公共事件 %d 补完，%s' % (
        EVENT, '奖励只发掉落表 %d 起的传说、不发勋章' % lot if lot else '下次对话照原版给勋章（重随包里找不到接上的传说）'))
