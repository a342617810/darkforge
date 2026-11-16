# -*- coding: utf-8 -*-
"""启动器网页界面的背景（用户 2026-11-10「烟雾飘动的粒子效果能做吗」）：和游戏标题封面同一套生成代码，分层导出，烟雾在网页里动。
  python make_launcher_bg.py
输出到 launcher\\ui\\img：
  bg_<封面>.jpg      底图（不含烟雾、不含字样，环在里面），1920×1080
  top_<封面>.png     字样层（直通透明度，裁到有字的范围），位置写在 layers.json
  puff_<封面>_<k>.png  烟雾贴图（同 make_anim.puff_texture，256×256，黑底亮度，网页里按加法叠）
  layers.json        {封面: {top: [x, y, w, h]（1920×1080 坐标）, peak: 烟雾亮度倍数, seed: 粒子种子}}
网页（launcher\\ui\\js\\smoke.js）照 make_anim.gen_puffs 的规则生成粒子：从屏幕下沿附近出来，顺同一个风向往上飘，慢慢变大、淡出。"""
import json
import os

import numpy as np
from PIL import Image

import make_anim
import make_covers

UI_IMG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'launcher', 'ui', 'img')
SIZE = (1920, 1080)


def to8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    os.makedirs(UI_IMG, exist_ok=True)
    meta = {}
    for name, fn in (('normal', make_covers.normal), ('hard', make_covers.hard)):
        img, top, _info = fn()
        H, W = img.shape[:2]
        k = SIZE[0] / W
        Image.fromarray(to8(img)).resize(SIZE, Image.LANCZOS).save(os.path.join(UI_IMG, 'bg_%s.jpg' % name), quality=88, optimize=True, progressive=True)
        # 字样层：预乘 → 直通，裁掉透明边
        a = top[..., 3]
        ys, xs = np.where(a > 0.003)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = top[y0:y1, x0:x1]
        al = crop[..., 3:4]
        rgb = np.where(al > 0.003, crop[..., :3] / np.maximum(al, 0.003), 0)
        im = Image.fromarray(np.dstack([to8(rgb), to8(al)]), 'RGBA')
        w, h = int(round((x1 - x0) * k)), int(round((y1 - y0) * k))
        im.resize((w, h), Image.LANCZOS).save(os.path.join(UI_IMG, 'top_%s.png' % name), optimize=True)
        st = make_anim.STYLE[name]
        for p in range(make_anim.PUFF_N):
            Image.fromarray(make_anim.puff_texture(40 + p, st['color'])[..., :3]).save(os.path.join(UI_IMG, 'puff_%s_%d.png' % (name, p)), optimize=True)
        meta[name] = dict(top=[round(x0 * k), round(y0 * k), w, h], peak=st['peak'], seed=st['seed'])
        print(name, '底图 + 字样', meta[name]['top'], '+ 烟雾贴图', make_anim.PUFF_N)
    json.dump(meta, open(os.path.join(UI_IMG, 'layers.json'), 'w', encoding='utf-8'), indent=1)
    # 网页里直接用（不用 fetch：页面里先放好）
    with open(os.path.join(os.path.dirname(UI_IMG), 'js', 'layers.js'), 'w', encoding='utf-8') as f:
        f.write('/* make_launcher_bg.py 生成，别手改 */\nwindow.DF_LAYERS = %s;\n' % json.dumps(meta))


if __name__ == '__main__':
    main()
