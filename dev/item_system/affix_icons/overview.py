# -*- coding: utf-8 -*-
"""把 设计清单.md 里全部词条的 out/charm_<key>.png 拼成一张带中文名的总览图 out/总览.png（按清单顺序，每批一段）"""
import os
import re

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
COLS, CW, CH, LH = 10, 176, 160, 30
BG = (40, 36, 30, 255)


def entries():
    rows = []
    for line in open(os.path.join(HERE, '设计清单.md'), encoding='utf-8'):
        m = re.match(r'\|\s*(dr_\w+)\s*\|\s*([^|]+?)\s*\|', line)
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def main():
    rows = entries()
    n = len(rows)
    nr = (n + COLS - 1) // COLS
    im = Image.new('RGBA', (COLS * CW, nr * (CH + LH) + 10), BG)
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 18)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 12)
    missing = []
    for i, (key, name) in enumerate(rows):
        x, y = (i % COLS) * CW, (i // COLS) * (CH + LH)
        p = os.path.join(OUT, 'charm_%s.png' % key)
        if os.path.exists(p):
            im.alpha_composite(Image.open(p).convert('RGBA'), (x + (CW - 160) // 2, y))
        else:
            missing.append(key)
        d.text((x + CW // 2, y + CH + 2), '%d %s' % (i + 1, name), font=font, fill=(214, 200, 170), anchor='ma')
        d.text((x + CW - 4, y + 4), key[3:], font=small, fill=(110, 100, 86), anchor='ra')
    im.save(os.path.join(OUT, '总览.png'))
    print(n, '个', '缺：' + ','.join(missing) if missing else '齐')


if __name__ == '__main__':
    main()
