# -*- coding: utf-8 -*-
"""读 Windows 事件日志（代替 PowerShell 的 Get-WinEvent）：ctypes 直接调 wevtapi.dll，不要第三方库。

  query('Application', providers=['Application Error'], ids=[1000], since=datetime(...), levels=None, message=True)
  → [Rec(Provider, Id, Level, Time（本地时间）, Data（EventData 里各项的文字，= Get-WinEvent 的 Properties）, Message)]，新的在前

和 Get-WinEvent 的不同：Properties 在 PowerShell 里是带类型的值，这里一律是事件 XML 里的文字（十六进制的整数写成 0x…），
比较进程号之类用 to_int()。Message 用系统的语言（和 Get-WinEvent 一样），格式化不了时是空串。"""
import ctypes
import ctypes.wintypes as W
import datetime
import re
import xml.etree.ElementTree as ET

from .core import Rec

_wevt = None
NS = '{http://schemas.microsoft.com/win/2004/08/events/event}'
EvtQueryChannelPath = 0x1
EvtQueryReverseDirection = 0x200
EvtRenderEventXml = 1
EvtFormatMessageEvent = 1
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259


def _api():
    global _wevt
    if _wevt is None:
        w = ctypes.WinDLL('wevtapi', use_last_error=True)
        H = ctypes.c_void_p
        w.EvtQuery.argtypes = [H, W.LPCWSTR, W.LPCWSTR, W.DWORD]
        w.EvtQuery.restype = H
        w.EvtNext.argtypes = [H, W.DWORD, ctypes.POINTER(H), W.DWORD, W.DWORD, ctypes.POINTER(W.DWORD)]
        w.EvtNext.restype = W.BOOL
        w.EvtRender.argtypes = [H, H, W.DWORD, W.DWORD, ctypes.c_void_p, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD)]
        w.EvtRender.restype = W.BOOL
        w.EvtOpenPublisherMetadata.argtypes = [H, W.LPCWSTR, W.LPCWSTR, W.DWORD, W.DWORD]
        w.EvtOpenPublisherMetadata.restype = H
        w.EvtFormatMessage.argtypes = [H, H, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.c_wchar_p, ctypes.POINTER(W.DWORD)]
        w.EvtFormatMessage.restype = W.BOOL
        w.EvtClose.argtypes = [H]
        w.EvtClose.restype = W.BOOL
        _wevt = w
    return _wevt


def _xpath(providers, ids, since, levels):
    conds = []
    if providers:
        conds.append('Provider[' + ' or '.join("@Name='%s'" % p.replace("'", '') for p in providers) + ']')
    if ids:
        conds.append('(' + ' or '.join('EventID=%d' % int(i) for i in ids) + ')')
    if levels:
        conds.append('(' + ' or '.join('Level=%d' % int(l) for l in levels) + ')')
    if since is not None:
        utc = since.astimezone(datetime.timezone.utc) if since.tzinfo else since.astimezone().astimezone(datetime.timezone.utc)
        conds.append("TimeCreated[@SystemTime>='%s']" % utc.strftime('%Y-%m-%dT%H:%M:%S.000Z'))
    return '*[System[' + ' and '.join(conds) + ']]' if conds else '*'


def _render_xml(h):
    w = _api()
    used, cnt = W.DWORD(0), W.DWORD(0)
    w.EvtRender(None, h, EvtRenderEventXml, 0, None, ctypes.byref(used), ctypes.byref(cnt))
    if ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER:
        return ''
    buf = ctypes.create_unicode_buffer(used.value // 2 + 1)
    if not w.EvtRender(None, h, EvtRenderEventXml, used.value, buf, ctypes.byref(used), ctypes.byref(cnt)):
        return ''
    return buf.value


_PUB = {}


def _format_message(h, provider):
    w = _api()
    if provider not in _PUB:
        _PUB[provider] = w.EvtOpenPublisherMetadata(None, provider, None, 0, 0)
    pm = _PUB[provider]
    if not pm:
        return ''
    used = W.DWORD(0)
    w.EvtFormatMessage(pm, h, 0, 0, None, EvtFormatMessageEvent, 0, None, ctypes.byref(used))
    if not used.value:
        return ''
    buf = ctypes.create_unicode_buffer(used.value + 1)
    if not w.EvtFormatMessage(pm, h, 0, 0, None, EvtFormatMessageEvent, used.value, buf, ctypes.byref(used)):
        # 有的事件少了插入值（ERROR_EVT_UNRESOLVED_VALUE_INSERT 15029）也会给出文字，照样用
        if ctypes.get_last_error() != 15029:
            return ''
    return buf.value.rstrip('\0')


def _parse_time(s):
    """'2026-11-18T03:25:58.1234567Z' → 本地时间（不带时区的 datetime，和 Get-WinEvent 的 TimeCreated 一样）"""
    s = (s or '').rstrip('Z')
    main, _, frac = s.partition('.')
    try:
        t = datetime.datetime.strptime(main, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return None
    t = t.replace(microsecond=int((frac + '000000')[:6]) if frac else 0, tzinfo=datetime.timezone.utc)
    return t.astimezone().replace(tzinfo=None)


def _parse(xml_text):
    root = ET.fromstring(xml_text)
    sysn = root.find(NS + 'System')
    prov = sysn.find(NS + 'Provider')
    eid = sysn.find(NS + 'EventID')
    lvl = sysn.find(NS + 'Level')
    tc = sysn.find(NS + 'TimeCreated')
    data = []
    ed = root.find(NS + 'EventData')
    if ed is not None:
        data = [(d.text or '') for d in ed.findall(NS + 'Data')]
    else:
        ud = root.find(NS + 'UserData')
        if ud is not None and len(ud):
            data = [(c.text or '') for c in list(ud[0])]
    return Rec(Provider=prov.get('Name') if prov is not None else '', Id=int(eid.text) if eid is not None and eid.text else 0,
               Level=int(lvl.text) if lvl is not None and lvl.text else 0, Time=_parse_time(tc.get('SystemTime') if tc is not None else ''),
               Data=data, Message='')


def query(log, providers=None, ids=None, since=None, levels=None, message=True, limit=None, where=None, match=None):
    """查一个日志（Application / System …），新的在前；where(rec) 过滤（在取 Message 之前，免得每条都格式化），
    match：Message 里要找得到的正则（不分大小写，= Where-Object { $_.Message -match ... }），limit 最多几条（过滤之后数）。
    日志读不了（服务停了、没权限）抛 OSError，和 Get-WinEvent -ErrorAction Stop 一样由调用的地方接住"""
    w = _api()
    q = _xpath(providers, ids, since, levels)
    rs = w.EvtQuery(None, log, q, EvtQueryChannelPath | EvtQueryReverseDirection)
    if not rs:
        raise OSError(ctypes.get_last_error(), '读不了事件日志 ' + log)
    out = []
    try:
        arr = (ctypes.c_void_p * 32)()
        n = W.DWORD(0)
        while limit is None or len(out) < limit:
            if not w.EvtNext(rs, 32, arr, 0xFFFFFFFF, 0, ctypes.byref(n)):
                err = ctypes.get_last_error()
                if err == ERROR_NO_MORE_ITEMS:
                    break
                raise OSError(err, '读事件日志出错 ' + log)
            hs = [arr[i] for i in range(n.value)]
            try:
                for h in hs:
                    if limit is not None and len(out) >= limit:
                        break
                    x = _render_xml(h)
                    if not x:
                        continue
                    try:
                        r = _parse(x)
                    except ET.ParseError:
                        continue
                    if where and not where(r):
                        continue
                    if message or match:
                        r.Message = _format_message(h, r.Provider)
                    if match and not re.search(match, r.Message, re.I):
                        continue
                    out.append(r)
            finally:
                for h in hs:
                    w.EvtClose(h)
    finally:
        w.EvtClose(rs)
    return out


def to_int(s):
    """事件里的整数（十进制或 0x 开头的十六进制）；认不出返回 None"""
    try:
        return int(str(s).strip(), 0)
    except ValueError:
        try:
            return int(str(s).strip(), 16)
        except ValueError:
            return None
