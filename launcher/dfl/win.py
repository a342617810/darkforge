# -*- coding: utf-8 -*-
"""Windows 小工具（ctypes，代替 PowerShell 里的 Get-Process、剪贴板、已知文件夹、文件版本、MessageBox、Get-CimInstance、按区域规则排序）。
只读系统信息、操作自己启动的进程；不写注册表、不改系统设置。"""
import ctypes
import datetime
import os
from ctypes import wintypes as W

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
user32 = ctypes.WinDLL('user32', use_last_error=True)
shell32 = ctypes.WinDLL('shell32', use_last_error=True)
ole32 = ctypes.WinDLL('ole32', use_last_error=True)
version = ctypes.WinDLL('version', use_last_error=True)

PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
STILL_ACTIVE = 259
TH32CS_SNAPPROCESS = 0x2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', W.DWORD), ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD), ('pcPriClassBase', ctypes.c_long),
                ('dwFlags', W.DWORD), ('szExeFile', ctypes.c_wchar * 260)]


kernel32.CreateToolhelp32Snapshot.restype = W.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
kernel32.Process32FirstW.argtypes = [W.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [W.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.OpenProcess.restype = W.HANDLE
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.CloseHandle.argtypes = [W.HANDLE]
kernel32.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
kernel32.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
kernel32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
kernel32.WaitForSingleObject.restype = W.DWORD
kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
kernel32.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4


# ---------------------------------------------------------------- 进程
def processes():
    """所有进程：[(pid, 父进程 pid, exe 文件名)]"""
    out = []
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return out
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.th32ParentProcessID, e.szExeFile))
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return out


def find_pids(name):
    """Get-Process <名字>：名字不带 .exe、不分大小写"""
    want = name.casefold()
    if not want.endswith('.exe'):
        want += '.exe'
    return [pid for pid, _, exe in processes() if exe.casefold() == want]


class Proc:
    """打开的进程句柄（崩溃看守要在游戏退出后还读得到退出码，一开始就打开）"""

    def __init__(self, pid, access=PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE):
        self.pid = pid
        self.h = kernel32.OpenProcess(access, False, pid)

    def __bool__(self):
        return bool(self.h)

    def close(self):
        if self.h:
            kernel32.CloseHandle(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def exit_code(self):
        """还在跑返回 None"""
        c = W.DWORD()
        if not self.h or not self.wait(0) or not kernel32.GetExitCodeProcess(self.h, ctypes.byref(c)):
            return None
        return c.value

    def wait(self, timeout_ms):
        """等它退出：退出了 True，超时 False"""
        if not self.h:
            return True
        return kernel32.WaitForSingleObject(self.h, int(timeout_ms)) == 0

    def path(self):
        buf = ctypes.create_unicode_buffer(1024)
        n = W.DWORD(len(buf))
        if self.h and kernel32.QueryFullProcessImageNameW(self.h, 0, buf, ctypes.byref(n)):
            return buf.value
        return ''

    def start_time(self):
        """进程启动的时间（本地时间 datetime），读不到 None"""
        t = [W.FILETIME() for _ in range(4)]
        if not self.h or not kernel32.GetProcessTimes(self.h, *[ctypes.byref(x) for x in t]):
            return None
        return filetime_local(t[0])


def filetime_local(ft):
    v = (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    if not v:
        return None
    utc = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(microseconds=v // 10)
    return utc.astimezone().replace(tzinfo=None)


def pid_alive(pid):
    with Proc(pid) as p:
        return bool(p) and not p.wait(0)


def kill_pid(pid):
    """Stop-Process -Force"""
    h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h:
        return False
    try:
        return bool(kernel32.TerminateProcess(h, 1))
    finally:
        kernel32.CloseHandle(h)


# ---------------------------------------------------------------- 窗口
WNDENUMPROC = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, W.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.GetWindow.restype = W.HWND
user32.GetWindow.argtypes = [W.HWND, W.UINT]
user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]


def windows_of(pid, visible=True, top_owner=True):
    """这个进程的顶层窗口（Process.MainWindowHandle 的近似：看得见、没有所有者的）"""
    found = []

    def cb(hwnd, _):
        p = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and (not visible or user32.IsWindowVisible(hwnd)) and (not top_owner or not user32.GetWindow(hwnd, 4)):   # GW_OWNER
            found.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def main_window(pid):
    w = windows_of(pid)
    return w[0] if w else None


def window_text(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def close_window(hwnd):
    """WM_CLOSE（像点了右上角的 ×）"""
    return bool(user32.PostMessageW(hwnd, 0x0010, 0, 0))


# ---------------------------------------------------------------- 剪贴板
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
user32.OpenClipboard.argtypes = [W.HWND]
user32.GetClipboardData.restype = W.HANDLE
user32.GetClipboardData.argtypes = [W.UINT]
user32.SetClipboardData.restype = W.HANDLE
user32.SetClipboardData.argtypes = [W.UINT, W.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [W.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [W.HGLOBAL]
kernel32.GlobalAlloc.restype = W.HGLOBAL
kernel32.GlobalAlloc.argtypes = [W.UINT, ctypes.c_size_t]
kernel32.GlobalFree.argtypes = [W.HGLOBAL]


def _open_clipboard():
    import time
    for _ in range(20):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def clipboard_get():
    """Get-Clipboard -Raw：没有文字返回 ''"""
    if not _open_clipboard():
        return ''
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ''
        p = kernel32.GlobalLock(h)
        if not p:
            return ''
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def clipboard_set(text):
    """Set-Clipboard：成功返回 True"""
    data = (str(text) + '\0').encode('utf-16-le')
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            return False
        return True
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------- 已知文件夹（桌面可能被挪到 OneDrive）
FOLDERS = {
    'Desktop': '{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}',
    'Documents': '{FDD39AD0-238F-46AF-ADB4-6C85480369C7}',
    'MyDocuments': '{FDD39AD0-238F-46AF-ADB4-6C85480369C7}',
}


class GUID(ctypes.Structure):
    _fields_ = [('Data1', W.DWORD), ('Data2', W.WORD), ('Data3', W.WORD), ('Data4', ctypes.c_ubyte * 8)]


def guid(s):
    import uuid
    u = uuid.UUID(s)
    g = GUID()
    ctypes.memmove(ctypes.byref(g), u.bytes_le, 16)
    return g


shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), W.DWORD, W.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]


def known_folder(name):
    """[Environment]::GetFolderPath('Desktop' / 'MyDocuments')；读不到返回 ''"""
    p = ctypes.c_void_p()
    if shell32.SHGetKnownFolderPath(ctypes.byref(guid(FOLDERS[name])), 0, None, ctypes.byref(p)) != 0:
        return ''
    try:
        return ctypes.wstring_at(p.value)
    finally:
        ole32.CoTaskMemFree(p)


# ---------------------------------------------------------------- 文件版本
class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [(n, W.DWORD) for n in ('dwSignature', 'dwStrucVersion', 'dwFileVersionMS', 'dwFileVersionLS', 'dwProductVersionMS',
                                       'dwProductVersionLS', 'dwFileFlagsMask', 'dwFileFlags', 'dwFileOS', 'dwFileType', 'dwFileSubtype',
                                       'dwFileDateMS', 'dwFileDateLS')]


version.GetFileVersionInfoSizeW.argtypes = [W.LPCWSTR, ctypes.POINTER(W.DWORD)]
version.GetFileVersionInfoW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p]
version.VerQueryValueW.argtypes = [ctypes.c_void_p, W.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(W.UINT)]


def file_version(path):
    """exe / dll 的文件版本四段数字 (主, 次, 生成, 修订)（FileVersionInfo.FileMajorPart …）；读不到返回 None"""
    n = version.GetFileVersionInfoSizeW(path, None)
    if not n:
        return None
    buf = ctypes.create_string_buffer(n)
    if not version.GetFileVersionInfoW(path, 0, n, buf):
        return None
    p = ctypes.c_void_p()
    ln = W.UINT()
    if not version.VerQueryValueW(buf, '\\', ctypes.byref(p), ctypes.byref(ln)) or not p.value:
        return None
    fi = ctypes.cast(p, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    return (fi.dwFileVersionMS >> 16, fi.dwFileVersionMS & 0xFFFF, fi.dwFileVersionLS >> 16, fi.dwFileVersionLS & 0xFFFF)


def file_version_text(path):
    """FileVersionInfo.FileVersion：版本资源里写的「文件版本」文字（先按资源自己的语言，再试英文的几种代码页）；没有返回 ''"""
    n = version.GetFileVersionInfoSizeW(path, None)
    if not n:
        return ''
    buf = ctypes.create_string_buffer(n)
    if not version.GetFileVersionInfoW(path, 0, n, buf):
        return ''
    p = ctypes.c_void_p()
    ln = W.UINT()
    keys = []
    if version.VerQueryValueW(buf, '\\VarFileInfo\\Translation', ctypes.byref(p), ctypes.byref(ln)) and p.value and ln.value >= 4:
        lang, cp = ctypes.cast(p, ctypes.POINTER(W.WORD * 2)).contents
        keys.append('%04X%04X' % (lang, cp))
    keys += ['040904B0', '040904E4', '04090000']
    for k in keys:
        if version.VerQueryValueW(buf, '\\StringFileInfo\\' + k + '\\FileVersion', ctypes.byref(p), ctypes.byref(ln)) and p.value and ln.value:
            return ctypes.wstring_at(p.value, ln.value).rstrip('\0')
    return ''


# ---------------------------------------------------------------- 系统对话框
MB_ICONS = {'error': 0x10, 'question': 0x20, 'warn': 0x30, 'info': 0x40}
user32.MessageBoxW.argtypes = [W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT]


def message_box(text, title, flags):
    """MessageBoxW（置顶、拿前台）；返回系统的按钮编号（IDOK 1、IDCANCEL 2、IDYES 6、IDNO 7）"""
    return user32.MessageBoxW(None, text, title, flags | 0x00040000 | 0x00010000)     # MB_TOPMOST | MB_SETFOREGROUND


# ---------------------------------------------------------------- 文件夹 / 文件选择框（代替 WinForms 的 FolderBrowserDialog / OpenFileDialog）
BFFCALLBACK = ctypes.WINFUNCTYPE(ctypes.c_int, W.HWND, W.UINT, W.LPARAM, W.LPARAM)


class BROWSEINFOW(ctypes.Structure):
    _fields_ = [('hwndOwner', W.HWND), ('pidlRoot', ctypes.c_void_p), ('pszDisplayName', W.LPWSTR), ('lpszTitle', W.LPCWSTR),
                ('ulFlags', W.UINT), ('lpfn', BFFCALLBACK), ('lParam', W.LPARAM), ('iImage', ctypes.c_int)]


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [('lStructSize', W.DWORD), ('hwndOwner', W.HWND), ('hInstance', W.HINSTANCE), ('lpstrFilter', W.LPCWSTR),
                ('lpstrCustomFilter', W.LPWSTR), ('nMaxCustFilter', W.DWORD), ('nFilterIndex', W.DWORD), ('lpstrFile', ctypes.c_void_p),
                ('nMaxFile', W.DWORD), ('lpstrFileTitle', W.LPWSTR), ('nMaxFileTitle', W.DWORD), ('lpstrInitialDir', W.LPCWSTR),
                ('lpstrTitle', W.LPCWSTR), ('Flags', W.DWORD), ('nFileOffset', W.WORD), ('nFileExtension', W.WORD),
                ('lpstrDefExt', W.LPCWSTR), ('lCustData', W.LPARAM), ('lpfnHook', ctypes.c_void_p), ('lpTemplateName', W.LPCWSTR),
                ('pvReserved', ctypes.c_void_p), ('dwReserved', W.DWORD), ('FlagsEx', W.DWORD)]


shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFOW)]
shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, W.LPWSTR]
user32.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, W.DWORD]


def pick_folder(description, initial=None, owner=None):
    """FolderBrowserDialog（Description = description，SelectedPath = initial，不显示「新建文件夹」）：选了返回路径，取消返回 None"""
    ole32.CoInitializeEx(None, 2)
    start = ctypes.create_unicode_buffer(initial or '')

    def cb(hwnd, msg, lp, data):
        if msg == 1 and start.value:                                      # BFFM_INITIALIZED → BFFM_SETSELECTIONW
            user32.SendMessageW(hwnd, 0x0400 + 103, 1, ctypes.addressof(start))
        return 0
    fn = BFFCALLBACK(cb)
    name = ctypes.create_unicode_buffer(260)
    bi = BROWSEINFOW(hwndOwner=owner, pszDisplayName=ctypes.cast(name, W.LPWSTR), lpszTitle=description,
                     ulFlags=0x0001 | 0x0040 | 0x0200, lpfn=fn)          # BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE | BIF_NONEWFOLDERBUTTON
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
    if not pidl:
        return None
    try:
        out = ctypes.create_unicode_buffer(1024)
        return out.value if shell32.SHGetPathFromIDListW(pidl, out) else None
    finally:
        ole32.CoTaskMemFree(pidl)


def pick_file(title, filter='所有文件|*.*', initial=None, multi=False, owner=None):
    """OpenFileDialog（Filter 写法和 .NET 一样「说明|*.ext|说明|*.*」）：选了返回路径（multi=True 返回路径列表），取消返回 None"""
    comdlg32 = ctypes.WinDLL('comdlg32')
    comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
    parts = filter.split('|')
    flt = ''.join(p + '\0' for p in parts) + '\0'
    size = 65536 if multi else 1024
    buf = ctypes.create_unicode_buffer(size)
    of = OPENFILENAMEW(lStructSize=ctypes.sizeof(OPENFILENAMEW), hwndOwner=owner, lpstrFilter=flt, nFilterIndex=1,
                       lpstrFile=ctypes.cast(buf, ctypes.c_void_p), nMaxFile=size, lpstrInitialDir=initial, lpstrTitle=title,
                       Flags=0x00001000 | 0x00000800 | 0x00080000 | 0x00000008 | (0x00000200 if multi else 0))
    # OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER | OFN_NOCHANGEDIR | OFN_ALLOWMULTISELECT
    if not comdlg32.GetOpenFileNameW(ctypes.byref(of)):
        return None
    if not multi:
        return buf.value
    raw = ctypes.wstring_at(ctypes.addressof(buf), size).split('\0')
    items = []
    for x in raw:
        if not x:
            break
        items.append(x)
    if len(items) == 1:
        return items
    return [os.path.join(items[0], n) for n in items[1:]]


# ---------------------------------------------------------------- WMI（Python 自带的 _wmi，代替 Get-CimInstance）
def wmi_query(query):
    """[{属性: 值(字符串)}]；查不了返回 []"""
    try:
        import _wmi
        raw = _wmi.exec_query(query)
    except Exception:
        return []
    rows, cur = [], {}
    for part in raw.split('\0'):
        if not part:
            if cur:
                rows.append(cur)
                cur = {}
            continue
        k, _, v = part.partition('=')
        if k in cur:                       # 下一行开始了（同一个属性又出现）
            rows.append(cur)
            cur = {}
        cur[k] = v
    if cur:
        rows.append(cur)
    return rows


_GPU = None


def get_gpu_names():
    """Get-GpuNames（ui.ps1）：这台电脑的显卡，只数真的显卡：PCI 设备、工作正常（远程桌面、虚拟显示器、停用的核显不算）。结果缓存"""
    global _GPU
    if _GPU is None:
        _GPU = [r.get('Name', '') for r in wmi_query('SELECT Name, PNPDeviceID, ConfigManagerErrorCode FROM Win32_VideoController')
                if r.get('PNPDeviceID', '').upper().startswith('PCI\\') and r.get('ConfigManagerErrorCode') == '0']
    return _GPU


# ---------------------------------------------------------------- 按区域规则、不分大小写排序（Sort-Object 的默认比较）
kernel32.CompareStringEx.argtypes = [W.LPCWSTR, W.DWORD, W.LPCWSTR, ctypes.c_int, W.LPCWSTR, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, W.LPARAM]
NORM_IGNORECASE = 0x00000001


def culture_cmp(a, b):
    """PowerShell Sort-Object / -lt 比字符串：当前区域的规则、不分大小写（.NET Framework 在 Windows 上就是调 CompareStringEx）"""
    r = kernel32.CompareStringEx(None, NORM_IGNORECASE, str(a), -1, str(b), -1, None, None, 0)
    if r == 0:                                     # 出错：退回按码位、不分大小写
        x, y = str(a).casefold(), str(b).casefold()
        return (x > y) - (x < y)
    return r - 2


def ps_sort(items, cmp):
    """PowerShell 5.1 的 Sort-Object 用的排序法：List<T>.Sort(IComparer)，powershell.exe 按 .NET 4.0 的兼容方式跑，是旧的
    DepthLimitedQuickSort——不稳定，相等的几项排完谁在前也照它（实测 6 个一样的排成 4 5 6 1 2 3，两个一样的会对调）。
    一样新的两个文件挑哪个、只差大小写的名字谁在前，都靠这个和以前对得上。cmp(a, b) 返回负 / 0 / 正。
    （子代理移植 backup / randomizer 时分别查出来、各写了一份，2026-11-18 收到这里）"""
    a = list(items)
    n = len(a)
    if n < 2:
        return a

    def swap_if_greater(i, j):
        if i != j and cmp(a[i], a[j]) > 0:
            a[i], a[j] = a[j], a[i]

    def down_heap(i, m, lo):
        d = a[lo + i - 1]
        while i <= m // 2:
            child = 2 * i
            if child < m and cmp(a[lo + child - 1], a[lo + child]) < 0:
                child += 1
            if not cmp(d, a[lo + child - 1]) < 0:
                break
            a[lo + i - 1] = a[lo + child - 1]
            i = child
        a[lo + i - 1] = d

    def heapsort(lo, hi):
        m = hi - lo + 1
        for i in range(m // 2, 0, -1):
            down_heap(i, m, lo)
        for i in range(m, 1, -1):
            a[lo], a[lo + i - 1] = a[lo + i - 1], a[lo]
            down_heap(1, i - 1, lo)

    def quick(left, right, depth):
        while True:
            if depth == 0:
                heapsort(left, right)
                return
            i, j = left, right
            middle = i + ((j - i) >> 1)
            swap_if_greater(i, middle)
            swap_if_greater(i, j)
            swap_if_greater(middle, j)
            x = a[middle]
            while True:
                while cmp(a[i], x) < 0:
                    i += 1
                while cmp(x, a[j]) < 0:
                    j -= 1
                if i > j:
                    break
                if i < j:
                    a[i], a[j] = a[j], a[i]
                i += 1
                j -= 1
                if i > j:
                    break
            depth -= 1
            if j - left <= right - i:
                if left < j:
                    quick(left, j, depth)
                left = i
            else:
                if i < right:
                    quick(i, right, depth)
                right = j
            if left >= right:
                return

    quick(0, n - 1, 32)                    # QuickSortDepthThreshold
    return a


def ps_sort_key(items, key, descending=False):
    """Sort-Object <数字 / 时间属性> [-Descending]：按值比（-Descending = 比较结果取反，排序法同上）"""
    sign = -1 if descending else 1
    return ps_sort(items, lambda x, y: sign * ((key(x) > key(y)) - (key(x) < key(y))))


def culture_sorted(items, key=lambda x: x, reverse=False):
    """Sort-Object <字符串> [-Descending]：区域规则、不分大小写，排序法和 PowerShell 5.1 一样（相等的谁在前也一样）"""
    sign = -1 if reverse else 1
    return ps_sort(items, lambda x, y: sign * culture_cmp(key(x), key(y)))
