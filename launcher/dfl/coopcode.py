# -*- coding: utf-8 -*-
"""联机码压缩（coopcode.ps1；用户 2026-11-17「可以编码一下联机码吗」→「不要按照默认的做 信息要完整只是某种方式压缩一下」）。
DR3 整段原文（coop.get_coop_code3）→ 词表里的词换成一个字节（0x80 起；表里没有的照原样，完全无损）→ deflate → base64url，前面加「DR4z」。
566 个字符的码压到 190 个字符左右；解开就是原来那一整段。只压全是 ASCII 的 DR3（别的照原样返回）。
词表只能往后加（解码靠下标）；要改已有的词就换一个模式字母（DR4z → DR4y），旧码按旧表解。前面的长词要排在它包含的短词前面。

联机码在装了不同版本的玩家之间传：PowerShell 版压的这里要解得开，反过来也一样。.NET 的 DeflateStream（默认 Optimal）
就是 zlib 第 6 级、窗口 -15，压出来的字节和这里一模一样（tests\\test_coopcode.py 对照过）。
解出来的只是文本（联机设置），不执行任何东西。"""
import base64
import binascii
import re
import zlib

CoopCodeWords = [
    'DR3', '|v=', '|m=rand', '|m=plain', '|pw=', '|w=low', '|w=high', '|sc=', '|em=', '|bp=', '|ps=', '|nat=', '|o=',
    'allow_summons=', 'boss_damage_scaling=', 'boss_health_scaling=', 'boss_posture_scaling=', 'death_debuffs=',
    'enemy_damage_scaling=', 'enemy_health_scaling=', 'enemy_posture_scaling=',
    'allmaps', 'bossbgm', 'changestats', 'crashfix', 'customenemy', 'dlcblessing', 'dlckeysilo', 'earlylegacy', 'editnames',
    'markareas', 'mats', 'norandom_health', 'norandom_scadu', 'norandom_upgrades', 'norandom', 'phasehp', 'raceloc_health',
    'raceloc_scadu', 'spellshops', 'weaponprogression', 'scale', 'enemy', ' dlc', ' v16', 'bias:', 'seed:', 'item',
]

# -match '[^\x20-\x7E]' 不分大小写：开尔文符号 K（U+212A）、带点的 İ（U+0130）转小写后是 ASCII，.NET 不把它们当「非 ASCII」；
# 接着 Latin-1 编码时前者变成 ?、后者变成 I（实测）。照样做，两边压出来的才一样
_LOWER_ASCII = {'K': b'?', 'İ': b'I'}

# .NET 正则的 \s（和 Python 的差在 \x1c-\x1f：Python 算空白，.NET 不算）
_NET_WS_RE = re.compile('[\t\n\x0b\x0c\r \x85\xa0  -     　]+')
_B64_RE = re.compile(r'[A-Za-z0-9+/]*={0,2}')


def compress_coop_code(Text):
    """DR3 → DR4z（不是 DR3、或者有非 ASCII 的字符：照原样返回）"""
    Text = Text or ''
    if not Text.startswith('DR3|'):
        return Text
    for c in Text:
        if not ('\x20' <= c <= '\x7e') and c not in _LOWER_ASCII:
            return Text
    t = Text
    for i, w in enumerate(CoopCodeWords):
        t = t.replace(w, chr(0x80 + i))
    data = b''.join(_LOWER_ASCII[c] if c in _LOWER_ASCII else c.encode('latin-1') for c in t)
    c = zlib.compressobj(6, zlib.DEFLATED, -15)                       # = .NET DeflateStream（CompressionLevel.Optimal）
    z = c.compress(data) + c.flush()
    return 'DR4z' + base64.urlsafe_b64encode(z).decode('ascii').rstrip('=')


def expand_coop_code(Text):
    """DR4z → DR3 原文（聊天软件折了行、加了空格也行）；不是 DR4 照原样返回；解不开返回空串"""
    Text = Text or ''
    t = _NET_WS_RE.sub('', Text)
    if not t.startswith('DR4'):
        return Text
    if not t.startswith('DR4z'):
        return ''
    try:
        s = t[4:].replace('-', '+').replace('_', '/')
        s += '=' * ((4 - len(s) % 4) % 4)
        if len(s) % 4 or not _B64_RE.fullmatch(s):                     # [Convert]::FromBase64String 不认的
            return ''
        raw = binascii.a2b_base64(s)
        d = zlib.decompressobj(-15)
        out = d.decompress(raw) + d.flush()
        if not d.eof:
            # 没复制完整（deflate 流断在半截）：.NET 的 DeflateStream 这时一个字节也不给（实测每个截断长度都是 0），照样当解不开
            return ''
        sb = []
        for ch in out.decode('latin-1'):
            k = ord(ch) - 0x80
            if k < 0:
                sb.append(ch)
            elif k < len(CoopCodeWords):
                sb.append(CoopCodeWords[k])
            else:
                return ''
        r = ''.join(sb)
        if not r.startswith('DR3|'):
            return ''
        return r
    except (ValueError, zlib.error, binascii.Error):
        return ''
