# -*- coding: utf-8 -*-
"""Boss 模组的文字（rr/bossmods.py 放进 features.json 的 boss_mods，只在这次加载了 Boss 模组时有）：
台词写进 menu_dlc02 的 TalkMsg（texts），别的菜单文字（例如击败横幅 GR_MenuText，menu_fmg）写进各自的表。
没加载时什么都不加，文字包和整合前一样。"""


def texts(cx, key):
    f = cx.feat.get('boss_mods')
    if not f:
        return {}
    out = {}
    rows = (f.get('texts') or {}).get(key) or {}
    if rows:
        out['TalkMsg'] = {int(k): v for k, v in rows.items()}
    for fmg, by_lang in (f.get('menu_fmg') or {}).items():
        rows = by_lang.get(key) or {}
        if rows:
            out.setdefault(fmg, {}).update({int(k): v for k, v in rows.items()})
    return out

