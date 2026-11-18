# -*- coding: utf-8 -*-
"""Windows 的 UI 自动化（UIA）客户端，只有操作随机器窗口要用的那几样（randomize.ps1 以前用 .NET 的 System.Windows.Automation）。
随机器是 Avalonia 程序：按钮、勾选框都画在一个窗口里，没有自己的窗口句柄，只能走 UIA 的 COM 接口（ctypes 直接调，不要第三方库）。
用到的：按进程号找顶层窗口、按控件类型找子孙、读名字、点按钮（Invoke）、勾选框（Toggle）、关窗口（Window）。
接口方法的槽位照 UIAutomationClient.h（IUnknown 占 0~2）。"""
import ctypes
import uuid
from ctypes import wintypes as W

ole32 = ctypes.WinDLL('ole32')
oleaut32 = ctypes.WinDLL('oleaut32')
oleaut32.SysAllocString.restype = ctypes.c_void_p
oleaut32.SysAllocString.argtypes = [W.LPCWSTR]
oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]
ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, W.DWORD]

HRESULT = ctypes.c_long
CLSID_CUIAutomation = '{ff48dba4-60ef-4201-aa87-54103eef594e}'
IID_IUIAutomation = '{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}'          # 注册表 HKCR\Interface 里核对过（2026-11-18）
IID_INVOKE = '{fb377fbe-8ea6-46d5-9c73-6499642d3059}'
IID_TOGGLE = '{94cf8058-9b8d-4ab9-8bfd-4cd0a33c8c70}'
IID_WINDOW = '{0faef453-9208-43ef-bbb2-3b485177864f}'

# 属性、控件类型、模式、范围
UIA_ProcessIdPropertyId = 30002
UIA_ControlTypePropertyId = 30003
UIA_NamePropertyId = 30005
CONTROL_TYPES = {'Button': 50000, 'CheckBox': 50002, 'Window': 50032}
UIA_InvokePatternId = 10000
UIA_WindowPatternId = 10009
UIA_TogglePatternId = 10015
TreeScope_Children = 2
TreeScope_Descendants = 4
TOGGLE_STATES = {0: 'Off', 1: 'On', 2: 'Indeterminate'}

# 槽位
IUIAutomation_GetRootElement = 5
IUIAutomation_CreatePropertyCondition = 23
IUIElement_FindFirst = 5
IUIElement_FindAll = 6
IUIElement_GetCurrentPatternAs = 14
IUIElement_CurrentProcessId = 20
IUIElement_CurrentName = 23
IUIArray_Length = 3
IUIArray_GetElement = 4


class GUID(ctypes.Structure):
    _fields_ = [('b', ctypes.c_ubyte * 16)]


def _guid(s):
    g = GUID()
    ctypes.memmove(ctypes.byref(g), uuid.UUID(s).bytes_le, 16)
    return g


class VARIANT(ctypes.Structure):
    """VARIANT（x64 上 24 字节）：只用到 VT_I4 / VT_BSTR"""
    _fields_ = [('vt', ctypes.c_ushort), ('r1', ctypes.c_ushort), ('r2', ctypes.c_ushort), ('r3', ctypes.c_ushort),
                ('val', ctypes.c_longlong), ('val2', ctypes.c_longlong)]


def _method(ptr, slot, *argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)(vtbl[slot])


def _release(ptr):
    if ptr:
        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)(vtbl[2])(ptr)


def _check(hr, what):
    if hr < 0:
        raise OSError('UI 自动化出错（%s，0x%08X）' % (what, hr & 0xFFFFFFFF))


class Com:
    """持有一个 COM 接口指针，回收时 Release"""

    def __init__(self, ptr):
        self.ptr = ptr

    def __del__(self):
        try:
            _release(self.ptr)
        except Exception:
            pass
        self.ptr = None


class Element(Com):
    def find_first(self, scope, cond):
        out = ctypes.c_void_p()
        _check(_method(self.ptr, IUIElement_FindFirst, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            self.ptr, scope, cond.ptr, ctypes.byref(out)), 'FindFirst')
        return Element(out.value) if out.value else None

    def find_all(self, scope, cond):
        arr = ctypes.c_void_p()
        _check(_method(self.ptr, IUIElement_FindAll, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            self.ptr, scope, cond.ptr, ctypes.byref(arr)), 'FindAll')
        if not arr.value:
            return []
        try:
            n = ctypes.c_int()
            _check(_method(arr.value, IUIArray_Length, ctypes.POINTER(ctypes.c_int))(arr.value, ctypes.byref(n)), 'Length')
            out = []
            for i in range(n.value):
                e = ctypes.c_void_p()
                _check(_method(arr.value, IUIArray_GetElement, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(arr.value, i, ctypes.byref(e)), 'GetElement')
                if e.value:
                    out.append(Element(e.value))
            return out
        finally:
            _release(arr.value)

    @property
    def name(self):
        """Current.Name（读不到返回 ''）"""
        b = ctypes.c_void_p()
        hr = _method(self.ptr, IUIElement_CurrentName, ctypes.POINTER(ctypes.c_void_p))(self.ptr, ctypes.byref(b))
        if hr < 0 or not b.value:
            return ''
        try:
            return ctypes.wstring_at(b.value)
        finally:
            oleaut32.SysFreeString(b.value)

    @property
    def process_id(self):
        n = ctypes.c_int()
        _check(_method(self.ptr, IUIElement_CurrentProcessId, ctypes.POINTER(ctypes.c_int))(self.ptr, ctypes.byref(n)), 'ProcessId')
        return n.value

    def pattern(self, pattern_id, iid):
        out = ctypes.c_void_p()
        g = _guid(iid)
        _check(_method(self.ptr, IUIElement_GetCurrentPatternAs, ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
            self.ptr, pattern_id, ctypes.byref(g), ctypes.byref(out)), 'GetCurrentPattern')
        if not out.value:
            raise OSError('UI 自动化出错（这个控件不支持模式 %d）' % pattern_id)
        return Com(out.value)

    def invoke(self):
        """InvokePattern.Invoke（点按钮）"""
        p = self.pattern(UIA_InvokePatternId, IID_INVOKE)
        _check(_method(p.ptr, 3)(p.ptr), 'Invoke')

    def toggle_state(self):
        """TogglePattern.Current.ToggleState：'Off' / 'On' / 'Indeterminate'"""
        p = self.pattern(UIA_TogglePatternId, IID_TOGGLE)
        n = ctypes.c_int()
        _check(_method(p.ptr, 4, ctypes.POINTER(ctypes.c_int))(p.ptr, ctypes.byref(n)), 'ToggleState')
        return TOGGLE_STATES.get(n.value, str(n.value))

    def toggle(self):
        p = self.pattern(UIA_TogglePatternId, IID_TOGGLE)
        _check(_method(p.ptr, 3)(p.ptr), 'Toggle')

    def close_window(self):
        """WindowPattern.Close（正常关闭：随机器会把设置写回文件）"""
        p = self.pattern(UIA_WindowPatternId, IID_WINDOW)
        _check(_method(p.ptr, 3)(p.ptr), 'Close')


class Automation(Com):
    """IUIAutomation（Initialize-Uia）。调用它的线程要是 STA（这里自己 CoInitializeEx）"""

    def __init__(self):
        ole32.CoInitializeEx(None, 2)                     # COINIT_APARTMENTTHREADED；已经初始化过也没关系
        out = ctypes.c_void_p()
        clsid, iid = _guid(CLSID_CUIAutomation), _guid(IID_IUIAutomation)
        _check(ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(out)), 'CoCreateInstance')
        super().__init__(out.value)

    def root(self):
        out = ctypes.c_void_p()
        _check(_method(self.ptr, IUIAutomation_GetRootElement, ctypes.POINTER(ctypes.c_void_p))(self.ptr, ctypes.byref(out)), 'GetRootElement')
        return Element(out.value)

    def prop_cond(self, prop_id, value):
        """PropertyCondition(属性, 值)：值是整数（进程号、控件类型）或字符串"""
        v = VARIANT()
        bstr = None
        if isinstance(value, str):
            bstr = oleaut32.SysAllocString(value)
            v.vt, v.val = 8, bstr                         # VT_BSTR
        else:
            v.vt, v.val = 3, int(value)                   # VT_I4
        out = ctypes.c_void_p()
        try:
            _check(_method(self.ptr, IUIAutomation_CreatePropertyCondition, ctypes.c_int, VARIANT, ctypes.POINTER(ctypes.c_void_p))(
                self.ptr, prop_id, v, ctypes.byref(out)), 'CreatePropertyCondition')
        finally:
            if bstr:
                oleaut32.SysFreeString(bstr)
        return Com(out.value)

    def control_type_cond(self, type_name):
        return self.prop_cond(UIA_ControlTypePropertyId, CONTROL_TYPES[type_name])

    def process_cond(self, pid):
        return self.prop_cond(UIA_ProcessIdPropertyId, pid)
