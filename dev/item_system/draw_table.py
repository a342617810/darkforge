# -*- coding: utf-8 -*-
"""抽取分布表：读 dark_core 的统计测试（gear.rs draw_stats）写的计数文件，做成 Excel（百分比都是公式，按「计数」页算）。
开发工具：
  1. 用一份重随出来的定义（items.txt / affixes.txt；游戏开着时用 safe_reroll 的副本）跑统计：
     DR_DEFS_DIR=<定义目录> DR_STATS_OUT=<计数文件> cargo test --release draw_stats -- --ignored --nocapture   （在 dev\\dark_core）
  2. launcher\\python\\python.exe -X utf8 dev\\item_system\\draw_table.py <计数文件> <定义目录> [输出 .xlsx]"""
import json
import os
import sys
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.dirname(os.path.dirname(HERE))
TIERS = ['普通', '稀有', '史诗', '传说', '传说（幽影）']
FONT = 'Arial'
HEAD = PatternFill('solid', start_color='DDE4EE')
SECT = PatternFill('solid', start_color='F2F2F2')
PCT = '0.0%;-0.0%;-'


def load(counts, defs):
    rows = [l.rstrip('\n').split('\t') for l in open(counts, encoding='utf-8') if l.strip()]
    n = int(next(r[3] for r in rows if r[0] == 'n'))
    data = [(r[0], int(r[1]), r[2], int(r[3])) for r in rows if r[0] != 'n']
    fam, wspec = {}, {}
    for l in open(os.path.join(defs, 'affixes.txt'), encoding='utf-8'):
        f = l.rstrip('\n').split('\t')
        if f[0] == 'fam' and len(f) >= 7:
            fam[f[6]] = dict(zh=f[4], en=f[5], mech=len(f) > 8 and f[8] == '1')
        elif f[0] == 'wspec' and len(f) >= 9:
            mask = int(f[9]) if len(f) > 9 else 15
            wspec[f[1]] = dict(zh=f[5], en=f[6], rars='、'.join(t for k, t in enumerate(TIERS[:4]) if mask & (1 << k)))
    lib = json.load(open(os.path.join(PALY, 'launcher', 'reroll', 'data', 'affixes', 'affixes.json'), encoding='utf-8'))
    for k, f in lib['gear'].items():
        if k in fam:
            fam[k]['group'] = f.get('group', '')
    return n, data, fam, wspec


def style_head(ws, row, ncol):
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(name=FONT, bold=True)
        cell.fill = HEAD
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def sumifs(kind, tier_col_or_num, key_ref):
    """计数页里 种类 = kind、档 = tier、键 = key 的件数"""
    return 'SUMIFS(计数!$D:$D,计数!$A:$A,"%s",计数!$B:$B,%s,计数!$C:$C,%s)' % (kind, tier_col_or_num, key_ref)


def main():
    counts, defs = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, '抽取分布.xlsx')
    n, data, fam, wspec = load(counts, defs)
    wb = Workbook()

    # ---------------------------------------------------------------- 总览
    ws = wb.active
    ws.title = '总览'
    ws['A1'] = '每档生成件数'
    ws['B1'] = n
    ws['B1'].font = Font(name=FONT, color='0000FF')
    ws['C1'] = '（dark_core 统计测试按真词条库生成；每类每档这么多件，百分比都按它算）'
    ws.append([])
    ws.append(['', '档 →'] + TIERS)
    ws.append(['', '档编号'] + list(range(5)))
    style_head(ws, 3, 7)
    for c in range(3, 8):
        ws.cell(row=4, column=c).font = Font(name=FONT, color='808080')
    r = 5

    def section(title):
        nonlocal r
        ws.cell(row=r, column=1, value=title).font = Font(name=FONT, bold=True)
        for c in range(1, 8):
            ws.cell(row=r, column=c).fill = SECT
        r += 1

    def line(label, note, formula):
        """formula(列字母) → 公式（不带 =）"""
        nonlocal r
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=note)
        for c in range(3, 8):
            col = get_column_letter(c)
            cell = ws.cell(row=r, column=c, value='=' + formula(col))
            cell.number_format = PCT
        r += 1

    tier = lambda col: '%s$4' % col
    section('防具')
    for k in (1, 2, 3):
        line('%d 个词条' % k, '件数占比', lambda col, k=k: '%s/$B$1' % sumifs('armor_cnt', tier(col), '"%d"' % k))
    line('有前缀', '至少一个机制类词条', lambda col: '%s/$B$1' % sumifs('armor_pre', tier(col), '"-"'))
    for k in (0, 1, 2):
        line('名字里 %d 个后缀' % k, '数值类最多放两个', lambda col, k=k: '%s/$B$1' % sumifs('armor_post', tier(col), '"%d"' % k))
    line('有词条没进名字', '第二个机制类，或第三个数值类', lambda col: '%s/$B$1' % sumifs('armor_hidden', tier(col), '"-"'))
    line('机制类占全部词条', '按词条个数算', lambda col: 'IFERROR(%s/%s,0)' % (sumifs('armor_mech', tier(col), '"-"'), sumifs('armor_all', tier(col), '"-"')))
    section('武器')
    line('有特效（前缀）', '特效位出不出沿用原包比例', lambda col: '%s/$B$1' % sumifs('weapon_spec_any', tier(col), '"-"'))
    line('全能', '五项都有补正', lambda col: '%s/$B$1' % sumifs('weapon_full', tier(col), '"-"'))
    line('强攻', 'settings 的 weapon_assault', lambda col: '%s/$B$1' % sumifs('weapon_atk', tier(col), '"-"'))
    section('护符')
    line('机制类', '「护符词条」页里机制类加起来',
         lambda col: "SUMIFS(护符词条!%s:%s,护符词条!$D:$D,\"机制\")" % (chr(ord(col) + 3), chr(ord(col) + 3)))   # 总览 C~G 对 护符词条 F~J
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 30
    for c in 'CDEFG':
        ws.column_dimensions[c].width = 13
    ws.freeze_panes = 'C5'

    # ---------------------------------------------------------------- 每个词条
    by = defaultdict(lambda: [0] * 5)
    for kind, t, key, cnt in data:
        by[(kind, key)][t] += cnt

    def affix_sheet(title, kind, note, with_prefix):
        s = wb.create_sheet(title)
        head = ['键', '名字', '英文', '类型', '分组'] + ['出现率\n' + t for t in TIERS]
        if with_prefix:
            head += ['做前缀\n' + t for t in TIERS]
        s.append(head)
        style_head(s, 1, len(head))
        keys = [k for (kd, k), v in by.items() if kd == kind and any(v)]
        keys.sort(key=lambda k: (not fam.get(k, {}).get('mech'), -by[(kind, k)][3], k))
        for i, k in enumerate(keys, start=2):
            f = fam.get(k, {})
            row = [k, f.get('zh', ''), f.get('en', ''), '机制' if f.get('mech') else '数值', f.get('group', '')]
            for t in range(5):
                row.append('=%s/总览!$B$1' % sumifs(kind, t, '$A%d' % i))
            if with_prefix:
                for t in range(5):
                    row.append('=%s/总览!$B$1' % sumifs('armor_prefix', t, '$A%d' % i) if f.get('mech') else '')
            s.append(row)
            for c in range(6, len(head) + 1):
                s.cell(row=i, column=c).number_format = PCT
        end = len(keys) + 2
        s.cell(row=end + 1, column=1, value=note).font = Font(name=FONT, italic=True, color='808080')
        widths = [18, 12, 26, 6, 12] + [11] * (len(head) - 5)
        for c, w in enumerate(widths, start=1):
            s.column_dimensions[get_column_letter(c)].width = w
        s.freeze_panes = 'F2'
        s.row_dimensions[1].height = 32
        return s

    affix_sheet('防具词条', 'armor_aff', '出现率 = 带这个词条的防具件数 ÷ 每档件数（一件最多 3 个词条，所以一列加起来会超过 100%）；'
                '做前缀 = 它是这件防具名字里的前缀（第一个机制类）。按 类型、传说出现率 排序', True)
    affix_sheet('护符词条', 'tal', '出现率 = 抽到这个词条的护符件数 ÷ 每档件数（护符一件一个词条，一列加起来 100%）', False)

    # ---------------------------------------------------------------- 武器特效
    s = wb.create_sheet('武器特效')
    head = ['键', '名字', '英文', '能出的稀有度'] + ['出现率\n' + t for t in TIERS]
    s.append(head)
    style_head(s, 1, len(head))
    keys = sorted(wspec, key=lambda k: (-by[('weapon_spec', k)][3], k))
    for i, k in enumerate(keys, start=2):
        w = wspec[k]
        s.append([k, w['zh'], w['en'], w['rars']] + ['=%s/总览!$B$1' % sumifs('weapon_spec', t, '$A%d' % i) for t in range(5)])
        for c in range(5, 10):
            s.cell(row=i, column=c).number_format = PCT
    s.cell(row=len(keys) + 3, column=1, value='出现率 = 带这个特效的武器件数 ÷ 每档件数；特效都是机制类，就是武器名字的前缀').font = Font(name=FONT, italic=True, color='808080')
    for c, wdt in enumerate([16, 12, 18, 16] + [11] * 5, start=1):
        s.column_dimensions[get_column_letter(c)].width = wdt
    s.freeze_panes = 'E2'
    s.row_dimensions[1].height = 32

    # ---------------------------------------------------------------- 计数（原始数据）
    s = wb.create_sheet('计数')
    s.append(['种类', '档', '键', '件数'])
    style_head(s, 1, 4)
    for kind, t, key, cnt in sorted(data):
        s.append([kind, t, key, cnt])
        s.cell(row=s.max_row, column=3).number_format = '@'
        s.cell(row=s.max_row, column=4).font = Font(name=FONT, color='0000FF')
    for c, wdt in zip('ABCD', (18, 6, 20, 10)):
        s.column_dimensions[c].width = wdt
    s.freeze_panes = 'A2'

    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.font.name != FONT:
                    cell.font = Font(name=FONT, bold=cell.font.bold, italic=cell.font.italic, color=cell.font.color)
    wb.save(out)
    print(out)


if __name__ == '__main__':
    main()
