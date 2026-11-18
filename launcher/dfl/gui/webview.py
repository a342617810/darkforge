# -*- coding: utf-8 -*-
"""一个装着 WebView2 网页的 Win32 窗口（ctypes 直接调包里的 WebView2Loader.dll 和 COM 接口，不要第三方库；以前是 webui.ps1 的 WinForms + WebView2）。
- 无边框（页面自己画标题栏，拖动靠页面发消息 → drag()）、Windows 11 圆角、图标、任务栏分组 ID（AppUserModelID）。
- 网页从虚拟主机 https://<host>/ 加载本地文件夹（SetVirtualHostNameToFolderMapping）；用户数据文件夹固定，页面的 localStorage 设置沿用。
- 页面 → 宿主：window.chrome.webview.postMessage(对象)，这里拿到 JSON 文字交给 on_message；宿主 → 页面：post_json(JSON 文字)。
- 所有 WebView2 调用都要在窗口线程上：别的线程用 invoke(函数) 排进窗口线程。set_timer 的回调也在窗口线程。
接口方法的槽位从包里的 Microsoft.Web.WebView2.Core.dll 读出来（Marshal.GetComSlotForMethodInfo，2026-11-18），IUnknown 占 0~2。
注意：在 Claude 的命令沙盒里建不起 WebView2 控件（一直等、最后 E_ABORT），要在普通终端里跑。"""
import ctypes
import os
import queue
import threading
import uuid
from ctypes import wintypes as W

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
ole32 = ctypes.WinDLL('ole32')
shell32 = ctypes.WinDLL('shell32')
shlwapi = ctypes.WinDLL('shlwapi')
dwmapi = ctypes.WinDLL('dwmapi')

HRESULT = ctypes.c_long
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = W.HWND
user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.SendMessageW.restype = LRESULT
user32.LoadImageW.restype = W.HANDLE
user32.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
user32.SetTimer.argtypes = [W.HWND, ctypes.c_size_t, W.UINT, ctypes.c_void_p]
user32.KillTimer.argtypes = [W.HWND, ctypes.c_size_t]
user32.MonitorFromWindow.restype = W.HANDLE
user32.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
user32.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT]
for _n in ('ShowWindow',):
    getattr(user32, _n).argtypes = [W.HWND, ctypes.c_int]
for _n in ('UpdateWindow', 'DestroyWindow', 'IsIconic', 'SetForegroundWindow', 'GetDpiForWindow'):
    getattr(user32, _n).argtypes = [W.HWND]
user32.GetClientRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
user32.GetMonitorInfoW.argtypes = [W.HANDLE, ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
dwmapi.DwmSetWindowAttribute.argtypes = [W.HWND, W.DWORD, ctypes.c_void_p, W.DWORD]
shlwapi.SHCreateStreamOnFileEx.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, W.BOOL, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]

WM_DESTROY, WM_SIZE, WM_MOVE, WM_ACTIVATE, WM_CLOSE, WM_TIMER, WM_SETICON = 0x0002, 0x0005, 0x0003, 0x0006, 0x0010, 0x0113, 0x0080
WM_NCLBUTTONDOWN, WM_APP, WM_GETMINMAXINFO, WM_DPICHANGED = 0x00A1, 0x8000, 0x0024, 0x02E0
WS_POPUP, WS_MINIMIZEBOX, WS_SYSMENU, WS_CLIPCHILDREN, WS_EX_APPWINDOW = 0x80000000, 0x00020000, 0x00080000, 0x02000000, 0x00040000

# WebView2 接口编号（IID）和槽位
IID = {
    'env_done': '4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d',        # ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler
    'ctl_done': '6c4819f3-c9b7-4260-8127-c9f5bde7f68c',        # ICoreWebView2CreateCoreWebView2ControllerCompletedHandler
    'msg': '57213f19-00e6-49fa-8e07-898ea01ecbd2',             # ICoreWebView2WebMessageReceivedEventHandler
    'nav': 'd33a35bf-1c49-4f98-93ab-006e0533fe1c',             # ICoreWebView2NavigationCompletedEventHandler
    'newwin': 'd4c185fe-c81c-4989-97af-2d3fa7ab5651',          # ICoreWebView2NewWindowRequestedEventHandler
    'capture': '697e05e9-3d8f-45fa-96f4-8ffe1ededaf5',         # ICoreWebView2CapturePreviewCompletedHandler
    'script': '49511172-cc67-4bca-9923-137112f4c4cc',          # ICoreWebView2ExecuteScriptCompletedHandler
    'wv3': 'a0d6df20-3b92-416d-aa0c-437a9c727857',             # ICoreWebView2_3
    'settings3': 'fdb5ab74-af33-4854-84f0-0a631deb5eba',       # ICoreWebView2Settings3
    'ctl2': 'c979903e-d4ca-4228-92eb-47ee3fa96eab',            # ICoreWebView2Controller2
}
S_ENV_CREATE_CONTROLLER = 3
S_CTL_PUT_VISIBLE, S_CTL_PUT_BOUNDS, S_CTL_MOVE_FOCUS, S_CTL_NOTIFY_MOVED, S_CTL_CLOSE, S_CTL_GET_WEBVIEW = 4, 6, 12, 23, 24, 25
S_CTL2_PUT_BG = 27
S_WV_GET_SETTINGS, S_WV_NAVIGATE, S_WV_ADD_NAV_COMPLETED, S_WV_EXECUTE_SCRIPT, S_WV_CAPTURE = 3, 5, 15, 29, 30
S_WV_POST_JSON, S_WV_ADD_MSG, S_WV_OPEN_DEVTOOLS, S_WV_ADD_NEWWIN = 32, 34, 51, 44
S_WV3_MAP_HOST = 71
S_SET_STATUSBAR, S_SET_DEVTOOLS, S_SET_CONTEXTMENU, S_SET_ZOOM = 10, 12, 14, 18
S_SET3_ACCEL = 24
S_MSGARGS_JSON = 4
S_NAVARGS_SUCCESS, S_NAVARGS_STATUS = 3, 4
S_NEWWIN_PUT_HANDLED = 6


class GUID(ctypes.Structure):
    _fields_ = [('b', ctypes.c_ubyte * 16)]


def guid(s):
    g = GUID()
    ctypes.memmove(ctypes.byref(g), uuid.UUID(s).bytes_le, 16)
    return g


def method(ptr, slot, *argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)(vtbl[slot])


def addref(ptr):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)(vtbl[1])(ptr)


def release(ptr):
    if ptr:
        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)(vtbl[2])(ptr)


def query(ptr, iid):
    """QueryInterface：拿到别的接口（新一点的 WebView2 才有的方法在 _2 / _3 这类接口上）；没有返回 None"""
    out = ctypes.c_void_p()
    g = guid(iid)
    hr = method(ptr, 0, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(ptr, ctypes.byref(g), ctypes.byref(out))
    return out.value if hr >= 0 and out.value else None


DONE = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, HRESULT, ctypes.c_void_p)            # 完成回调：(this, 错误码, 结果)
EVENT = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)   # 事件回调：(this, sender, args)
SCRIPT_DONE = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, HRESULT, W.LPCWSTR)
CAPTURE_DONE = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, HRESULT)


class Handler:
    """一个只实现 IUnknown + Invoke 的 COM 回调对象（引用计数不管：对象一直留在 Python 这边，窗口关掉前不释放）"""
    QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    REF = ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)

    def __init__(self, invoke_type, fn, iid):
        self.iids = {'00000000-0000-0000-c000-000000000046', iid}
        self.fns = [self.QI(self._qi), self.REF(lambda this: 1), self.REF(lambda this: 1), invoke_type(self._safe(fn))]
        self.vtbl = (ctypes.c_void_p * 4)(*[ctypes.cast(f, ctypes.c_void_p) for f in self.fns])
        self.obj = ctypes.c_void_p(ctypes.addressof(self.vtbl))
        self.ptr = ctypes.addressof(self.obj)

    @staticmethod
    def _safe(fn):
        def f(*a):
            try:
                fn(*a)
            except Exception:                    # 回调里的异常不能穿出去（会弄坏 WebView2）
                import traceback
                traceback.print_exc()
            return 0
        return f

    def _qi(self, this, riid, ppv):
        g = str(uuid.UUID(bytes_le=ctypes.string_at(riid, 16)))
        if g in self.iids:
            ppv[0] = this
            return 0
        ppv[0] = None
        return -2147467262                         # E_NOINTERFACE


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', W.UINT), ('style', W.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', W.HINSTANCE), ('hIcon', W.HICON), ('hCursor', W.HANDLE), ('hbrBackground', W.HBRUSH),
                ('lpszMenuName', W.LPCWSTR), ('lpszClassName', W.LPCWSTR), ('hIconSm', W.HICON)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('dwFlags', W.DWORD)]


class COLOR(ctypes.Structure):
    _fields_ = [('A', ctypes.c_ubyte), ('R', ctypes.c_ubyte), ('G', ctypes.c_ubyte), ('B', ctypes.c_ubyte)]


def set_dpi_aware():
    """按每台显示器的 DPI 显示（字和网页不发糊）；要在建窗口之前调"""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))          # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass


def set_app_id(app_id):
    """任务栏分组用自己的 ID（不和别的 Python 程序归到一起）"""
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except (AttributeError, OSError):
        pass


def runtime_version(loader_dir):
    """电脑上装的 WebView2 运行时版本（没有返回 ''）"""
    try:
        loader = ctypes.WinDLL(os.path.join(loader_dir, 'WebView2Loader.dll'))
        f = loader.GetAvailableCoreWebView2BrowserVersionString
        f.argtypes = [W.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
        out = ctypes.c_void_p()
        if f(None, ctypes.byref(out)) < 0 or not out.value:
            return ''
        try:
            return ctypes.wstring_at(out.value)
        finally:
            ole32.CoTaskMemFree(out)
    except OSError:
        return ''


class WebViewWindow:
    """用法：w = WebViewWindow(...)；w.on_message = f(json)；w.run()（在主线程里，窗口关了才返回）"""

    def __init__(self, title, loader_dir, user_data_dir, host_name, host_folder, start_url, design_size=(1280, 720),
                 icon_path=None, background=(17, 16, 14), browser_args='', devtools=False, class_name='DarkforgeLauncher'):
        self.title, self.loader_dir, self.udf = title, loader_dir, user_data_dir
        self.host_name, self.host_folder, self.start_url = host_name, host_folder, start_url
        self.design_size, self.icon_path, self.background = design_size, icon_path, background
        self.browser_args, self.devtools, self.class_name = browser_args, devtools, class_name
        self.hwnd = None
        self.env = self.ctl = self.wv = None
        self.ready = False                       # 网页导航完成
        self.on_message = None                   # f(json 文字)，窗口线程
        self.on_navigated = None                 # f(成功?, 错误码)，窗口线程
        self.on_failed = None                    # f(说明)：WebView2 建不起来（没装运行时之类）
        self.on_close = None                     # f() -> True 才关（点 × / close()）；None = 直接关
        self._handlers = []
        self._calls = queue.Queue()
        self._timers = {}
        self._next_timer = 100
        self._ui_thread = threading.get_ident()
        self._wndproc = WNDPROC(self._proc)

    # ---------------------------------------------------------------- 窗口
    def _create_window(self):
        hinst = kernel32.GetModuleHandleW(None)
        icon = None
        if self.icon_path and os.path.isfile(self.icon_path):
            icon = user32.LoadImageW(None, self.icon_path, 1, 0, 0, 0x10 | 0x40)       # IMAGE_ICON, LR_LOADFROMFILE | LR_DEFAULTSIZE
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self._wndproc, hInstance=hinst, lpszClassName=self.class_name,
                         hCursor=user32.LoadCursorW(None, ctypes.c_void_p(32512)), hIcon=icon, hIconSm=icon,
                         hbrBackground=None)
        user32.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(WS_EX_APPWINDOW, self.class_name, self.title, WS_POPUP | WS_MINIMIZEBOX | WS_SYSMENU | WS_CLIPCHILDREN,
                                           0, 0, 100, 100, None, None, hinst, None)
        if icon:
            user32.SendMessageW(self.hwnd, WM_SETICON, 0, icon)
            user32.SendMessageW(self.hwnd, WM_SETICON, 1, icon)
        v = ctypes.c_int(2)                                                             # Windows 11 圆角（DWMWA_WINDOW_CORNER_PREFERENCE = ROUND）
        dwmapi.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(v), 4)
        self._place()
        user32.ShowWindow(self.hwnd, 5)
        user32.UpdateWindow(self.hwnd)

    def _place(self):
        """设计尺寸 × DPI，屏幕（工作区）放不下就按比例缩到 92%，放在中间（webui.ps1 的 Set-WebWindowSize）"""
        try:
            dpi = user32.GetDpiForWindow(self.hwnd) or 96
        except (AttributeError, OSError):
            dpi = 96
        s = dpi / 96.0
        w, h = int(self.design_size[0] * s), int(self.design_size[1] * s)
        mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(user32.MonitorFromWindow(self.hwnd, 2), ctypes.byref(mi))
        wa = mi.rcWork
        ww, wh = wa.right - wa.left, wa.bottom - wa.top
        k = min(1.0, (ww * 0.92) / w, (wh * 0.92) / h)
        w, h = int(w * k), int(h * k)
        user32.SetWindowPos(self.hwnd, None, wa.left + (ww - w) // 2, wa.top + (wh - h) // 2, w, h, 0x0004 | 0x0010)   # NOZORDER | NOACTIVATE

    def _proc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_APP:
                self._drain()
                return 0
            if msg == WM_TIMER:
                fn = self._timers.get(wp)
                if fn:
                    try:
                        fn()
                    except Exception:
                        import traceback
                        traceback.print_exc()
                return 0
            if msg == WM_SIZE:
                self._resize()
            elif msg == WM_MOVE and self.ctl:
                method(self.ctl, S_CTL_NOTIFY_MOVED)(self.ctl)
            elif msg == WM_ACTIVATE and self.ctl and (wp & 0xFFFF):
                method(self.ctl, S_CTL_MOVE_FOCUS, ctypes.c_int)(self.ctl, 0)     # 窗口激活时把键盘焦点给网页
            elif msg == WM_CLOSE:
                if self.on_close and not self.on_close():
                    return 0
                self._shutdown()
                user32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            import traceback
            traceback.print_exc()
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def _resize(self):
        if self.ctl:
            r = W.RECT()
            user32.GetClientRect(self.hwnd, ctypes.byref(r))
            method(self.ctl, S_CTL_PUT_BOUNDS, W.RECT)(self.ctl, r)

    def _shutdown(self):
        for k in list(self._timers):
            user32.KillTimer(self.hwnd, k)
        self._timers.clear()
        if self.ctl:
            try:
                method(self.ctl, S_CTL_CLOSE)(self.ctl)
            except OSError:
                pass

    # ---------------------------------------------------------------- 线程
    def invoke(self, fn):
        """在窗口线程上执行 fn()（别的线程调；窗口线程自己调就直接执行）"""
        if threading.get_ident() == self._ui_thread:
            fn()
            return
        self._calls.put(fn)
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP, 0, 0)

    def _drain(self):
        while True:
            try:
                fn = self._calls.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception:
                import traceback
                traceback.print_exc()

    def set_timer(self, ms, fn):
        """每 ms 毫秒在窗口线程上调一次 fn；返回编号（kill_timer 用）"""
        self._next_timer += 1
        self._timers[self._next_timer] = fn
        user32.SetTimer(self.hwnd, self._next_timer, int(ms), None)
        return self._next_timer

    def kill_timer(self, tid):
        self._timers.pop(tid, None)
        user32.KillTimer(self.hwnd, tid)

    # ---------------------------------------------------------------- 窗口操作（窗口线程）
    def drag(self):
        user32.ReleaseCapture()
        user32.SendMessageW(self.hwnd, WM_NCLBUTTONDOWN, 2, 0)                          # HTCAPTION：按住标题栏拖
    def minimize(self):
        user32.ShowWindow(self.hwnd, 6)

    def close(self):
        """像点了 ×（会问 on_close）"""
        user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def destroy(self):
        """不问，直接关"""
        self.on_close = None
        user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def bring_front(self):
        """后台进程要弹窗时把窗口拿到前台（最小化了先还原；置顶一下再取消，抢到前台）"""
        if user32.IsIconic(self.hwnd):
            user32.ShowWindow(self.hwnd, 9)
        user32.SetWindowPos(self.hwnd, W.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002)          # HWND_TOPMOST, NOSIZE | NOMOVE
        user32.SetWindowPos(self.hwnd, W.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002)          # HWND_NOTOPMOST
        user32.SetForegroundWindow(self.hwnd)

    # ---------------------------------------------------------------- WebView2
    def _start_webview(self):
        if self.browser_args:
            os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = self.browser_args     # 加给浏览器进程的参数（WebView2 认这个环境变量）
        try:
            loader = ctypes.WinDLL(os.path.join(self.loader_dir, 'WebView2Loader.dll'))
        except OSError as e:
            self._fail('找不到 WebView2Loader.dll：%s' % e)
            return
        f = loader.CreateCoreWebView2EnvironmentWithOptions
        f.argtypes = [W.LPCWSTR, W.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
        f.restype = HRESULT
        h = self._handler(DONE, self._on_env, 'env_done')
        hr = f(None, self.udf, None, h.ptr)
        if hr < 0:
            self._fail('WebView2 建不起来（0x%08X）' % (hr & 0xFFFFFFFF))

    def _handler(self, kind, fn, iid_key):
        h = Handler(kind, fn, IID[iid_key])
        self._handlers.append(h)
        return h

    def _fail(self, why):
        if self.on_failed:
            self.on_failed(why)

    def _on_env(self, this, hr, env):
        if hr < 0 or not env:
            self._fail('WebView2 运行时用不了（0x%08X）' % (hr & 0xFFFFFFFF))
            return
        addref(env)
        self.env = env
        h = self._handler(DONE, self._on_controller, 'ctl_done')
        hr2 = method(env, S_ENV_CREATE_CONTROLLER, W.HWND, ctypes.c_void_p)(env, self.hwnd, h.ptr)
        if hr2 < 0:
            self._fail('WebView2 控件建不起来（0x%08X）' % (hr2 & 0xFFFFFFFF))

    def _on_controller(self, this, hr, ctl):
        if hr < 0 or not ctl:
            self._fail('WebView2 控件建不起来（0x%08X）' % (hr & 0xFFFFFFFF))
            return
        addref(ctl)
        self.ctl = ctl
        c2 = query(ctl, IID['ctl2'])
        if c2:                                                                          # 网页加载前的底色（和页面背景一样，不闪白）
            r, g, b = self.background
            method(c2, S_CTL2_PUT_BG, COLOR)(c2, COLOR(255, r, g, b))
            release(c2)
        wv = ctypes.c_void_p()
        method(ctl, S_CTL_GET_WEBVIEW, ctypes.POINTER(ctypes.c_void_p))(ctl, ctypes.byref(wv))
        self.wv = wv.value
        self._resize()
        # 设置：右键菜单、状态栏、缩放、浏览器快捷键都关掉；开发者工具只在调试时开
        st = ctypes.c_void_p()
        method(self.wv, S_WV_GET_SETTINGS, ctypes.POINTER(ctypes.c_void_p))(self.wv, ctypes.byref(st))
        if st.value:
            for slot, on in ((S_SET_DEVTOOLS, self.devtools), (S_SET_CONTEXTMENU, False), (S_SET_STATUSBAR, False), (S_SET_ZOOM, False)):
                method(st.value, slot, W.BOOL)(st.value, bool(on))
            s3 = query(st.value, IID['settings3'])
            if s3:
                method(s3, S_SET3_ACCEL, W.BOOL)(s3, False)
                release(s3)
            release(st.value)
        wv3 = query(self.wv, IID['wv3'])
        if wv3:                                                                         # https://<host>/ → 本地文件夹
            method(wv3, S_WV3_MAP_HOST, W.LPCWSTR, W.LPCWSTR, ctypes.c_int)(wv3, self.host_name, self.host_folder, 1)
            release(wv3)
        token = ctypes.c_int64()
        h = self._handler(EVENT, self._on_web_message, 'msg')
        method(self.wv, S_WV_ADD_MSG, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64))(self.wv, h.ptr, ctypes.byref(token))
        h = self._handler(EVENT, self._on_nav, 'nav')
        method(self.wv, S_WV_ADD_NAV_COMPLETED, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64))(self.wv, h.ptr, ctypes.byref(token))
        h = self._handler(EVENT, self._on_new_window, 'newwin')
        method(self.wv, S_WV_ADD_NEWWIN, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64))(self.wv, h.ptr, ctypes.byref(token))
        method(self.wv, S_WV_NAVIGATE, W.LPCWSTR)(self.wv, self.start_url)

    def _on_web_message(self, this, sender, args):
        s = ctypes.c_void_p()
        if method(args, S_MSGARGS_JSON, ctypes.POINTER(ctypes.c_void_p))(args, ctypes.byref(s)) < 0 or not s.value:
            return
        try:
            text = ctypes.wstring_at(s.value)
        finally:
            ole32.CoTaskMemFree(s)
        if self.on_message:
            self.on_message(text)

    def _on_nav(self, this, sender, args):
        ok = W.BOOL()
        st = ctypes.c_int()
        method(args, S_NAVARGS_SUCCESS, ctypes.POINTER(W.BOOL))(args, ctypes.byref(ok))
        method(args, S_NAVARGS_STATUS, ctypes.POINTER(ctypes.c_int))(args, ctypes.byref(st))
        if ok.value:
            self.ready = True
        if self.on_navigated:
            self.on_navigated(bool(ok.value), st.value)

    def _on_new_window(self, this, sender, args):
        method(args, S_NEWWIN_PUT_HANDLED, W.BOOL)(args, True)                          # 页面里不开新窗口

    def post_json(self, text):
        """把一段 JSON 发给页面（任何线程都能调）。页面脚本的 ready 比导航完成的事件先到，所以不等导航完成，有网页控件就发"""
        def send():
            if self.wv:
                method(self.wv, S_WV_POST_JSON, W.LPCWSTR)(self.wv, text)
        self.invoke(send)

    def execute_script(self, js):
        def run():
            if self.wv:
                h = self._handler(SCRIPT_DONE, lambda this, hr, res: None, 'script')
                method(self.wv, S_WV_EXECUTE_SCRIPT, W.LPCWSTR, ctypes.c_void_p)(self.wv, js, h.ptr)
        self.invoke(run)

    def capture_png(self, path, done=None):
        """把网页截成 PNG（测试用，webui.ps1 的 DARKFORGE_WEBUI_SHOT）；done(成功?) 在窗口线程上调"""
        def run():
            stream = ctypes.c_void_p()
            hr = shlwapi.SHCreateStreamOnFileEx(path, 0x00001000 | 0x00000001 | 0x00000020, 0x80, True, None, ctypes.byref(stream))  # CREATE|WRITE|SHARE_DENY_WRITE
            if hr < 0:
                if done:
                    done(False)
                return

            def fin(this, hr2):
                release(stream.value)
                if done:
                    done(hr2 >= 0)
            h = self._handler(CAPTURE_DONE, fin, 'capture')
            method(self.wv, S_WV_CAPTURE, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(self.wv, 0, stream.value, h.ptr)
        self.invoke(run)

    def open_devtools(self):
        self.invoke(lambda: self.wv and method(self.wv, S_WV_OPEN_DEVTOOLS)(self.wv))

    # ---------------------------------------------------------------- 跑起来
    def run(self):
        ole32.CoInitializeEx(None, 2)
        self._ui_thread = threading.get_ident()
        self._create_window()
        self._start_webview()
        msg = W.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
