# -*- coding: utf-8 -*-
"""打开启动器窗口（以前是 gui.ps1）。用包里自带的 pythonw.exe 跑（没有黑框）：
  launcher\\python\\pythonw.exe -I launcher\\dfgui.py
界面在 dfl\\gui\\app.py；后台步骤（启动游戏、重随敌人……）照样交给 launcher\\df.py 子进程。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)            # 自带的 Python 有 ._pth，不会自己把脚本所在的文件夹加进来

# pythonw 没有控制台：sys.stdout / sys.stderr 是 None，print 和 traceback 会出错。输出扔掉，出错的堆栈记进 logs\gui_trace.txt
# （确认只开这一个之后再打开：不然第二个启动器会把开着的那个的记录清空）
_TRACE = sys.stderr is None
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')


def _open_trace():
    if not _TRACE:
        return
    try:
        os.makedirs(os.path.join(HERE, 'logs'), exist_ok=True)
        sys.stderr = open(os.path.join(HERE, 'logs', 'gui_trace.txt'), 'w', encoding='utf-8', buffering=1)
    except OSError:
        pass


_MUTEX = None


def _single_instance(wait_ms=15000):
    """一个整合包只开一个启动器（崩溃风险审查 2026-11-19 第 15 条：两个启动器同时生成会互相写坏 out\\ 里的文件、抢着启动游戏）。
    互斥量按整合包的位置起名（别的文件夹里的整合包、测试用的副本不算），主线程一直拿着，进程结束时系统自己放掉。
    已经开着：把那个窗口提到前面，再等它一会儿（wait_ms）——更新完重开启动器时（app.start_gui_again）新的先起来、旧的随后才退出，
    等到了就照常开；一直等不到返回 False（这个就不开了）。建不了互斥量就照常开"""
    global _MUTEX
    import ctypes
    import hashlib
    from ctypes import wintypes as W
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateMutexW.restype = W.HANDLE
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, W.BOOL, W.LPCWSTR]
    k32.WaitForSingleObject.restype = W.DWORD
    k32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    k32.CloseHandle.argtypes = [W.HANDLE]
    name = 'Local\\Darkforge.Launcher.' + hashlib.sha1(os.path.normcase(HERE).encode('utf-8')).hexdigest()[:16]
    h = k32.CreateMutexW(None, True, name)
    if not h:
        return True
    if ctypes.get_last_error() != 183:                 # ERROR_ALREADY_EXISTS：不是就是这次新建的，已经拿着了
        _MUTEX = h
        return True
    try:
        _bring_front(k32)
    except Exception:
        pass
    if k32.WaitForSingleObject(h, wait_ms) in (0, 0x80):   # WAIT_OBJECT_0 / WAIT_ABANDONED：前一个退出了，现在归这个
        _MUTEX = h
        return True
    k32.CloseHandle(h)
    return False


def _bring_front(k32):
    """把同一个整合包（同一个 launcher\\python\\pythonw.exe）开着的启动器窗口提到前面"""
    import ctypes
    from ctypes import wintypes as W
    u32 = ctypes.WinDLL('user32', use_last_error=True)
    k32.OpenProcess.restype = W.HANDLE
    k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    u32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    u32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    mine = os.path.normcase(os.path.join(HERE, 'python'))
    found = []

    def exe_of(pid):
        hp = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not hp:
            return ''
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = W.DWORD(1024)
            return buf.value if k32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)) else ''
        finally:
            k32.CloseHandle(hp)

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def each(hwnd, _):
        cls = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(hwnd, cls, 64)
        if cls.value == 'DarkforgeLauncher':
            pid = W.DWORD(0)
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if os.path.normcase(os.path.dirname(exe_of(pid.value))) == mine:
                found.append(hwnd)
                return False
        return True
    u32.EnumWindows(each, 0)
    if found:
        if u32.IsIconic(found[0]):
            u32.ShowWindow(found[0], 9)                # SW_RESTORE
        u32.SetForegroundWindow(found[0])


if __name__ == '__main__':
    if not _single_instance():
        sys.exit(0)
    _open_trace()
    from dfl.gui import app  # noqa: E402
    sys.exit(app.main())
