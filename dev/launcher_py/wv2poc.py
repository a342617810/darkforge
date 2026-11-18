# -*- coding: utf-8 -*-
"""可行性验证：纯 Python（ctypes）开一个 Win32 窗口、用包里的 WebView2Loader.dll 嵌网页，网页 → 宿主 → 网页 来回一次消息，然后自己关掉。
不加任何第三方库。用法：python wv2poc.py <WebView2Loader.dll 所在目录> <用户数据目录> <结果文件>"""
import ctypes
import json
import os
import sys
from ctypes import wintypes as W

LOADER_DIR, UDF, OUT = sys.argv[1:4]
user32, kernel32, ole32 = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.ole32
HRESULT = ctypes.c_long
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = W.HWND
user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
log = []
import time
T0 = time.time()
_append = log.append
log = type('L', (list,), {'append': lambda self, x: list.append(self, (round(time.time() - T0, 2),) + tuple(x))})()


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', W.UINT), ('style', W.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', W.HINSTANCE), ('hIcon', W.HICON), ('hCursor', W.HANDLE), ('hbrBackground', W.HBRUSH),
                ('lpszMenuName', W.LPCWSTR), ('lpszClassName', W.LPCWSTR), ('hIconSm', W.HICON)]


def method(ptr, slot, *argtypes):
    """COM 接口指针 ptr 的第 slot 个方法"""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)(vtbl[slot])


class Handler:
    """一个只实现 IUnknown + Invoke 的 COM 回调对象"""
    QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    REF = ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)

    def __init__(self, invoke_type, fn, iid):
        self.iids = {'00000000-0000-0000-c000-000000000046', iid}
        self.fns = [self.QI(self._qi), self.REF(lambda this: 1), self.REF(lambda this: 1), invoke_type(fn)]
        self.vtbl = (ctypes.c_void_p * 4)(*[ctypes.cast(f, ctypes.c_void_p) for f in self.fns])
        self.obj = ctypes.c_void_p(ctypes.addressof(self.vtbl))
        self.ptr = ctypes.addressof(self.obj)

    def _qi(self, this, riid, ppv):
        import uuid
        g = str(uuid.UUID(bytes_le=ctypes.string_at(riid, 16)))
        if g in self.iids:
            ppv[0] = this
            return 0
        log.append(('QI miss', g))
        ppv[0] = None
        return -2147467262                                                # E_NOINTERFACE


state = {}


def resize(hwnd):
    c = state.get('ctl')
    if not c:
        return
    r = W.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    method(c, 6, W.RECT)(c, r)                                            # ICoreWebView2Controller::put_Bounds


@WNDPROC
def wndproc(hwnd, msg, wp, lp):
    if msg == 0x0005:                                                     # WM_SIZE
        resize(hwnd)
    elif msg == 0x0002:                                                   # WM_DESTROY
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wp, lp)


PAGE = """<!doctype html><meta charset=utf-8><body style='background:#111;color:#ddd;font:20px sans-serif'>
<p id=t>页面加载了</p><script>
window.chrome.webview.addEventListener('message', e => { document.getElementById('t').textContent = '宿主回复：' + JSON.stringify(e.data);
  window.chrome.webview.postMessage(JSON.stringify({type: 'done', got: e.data})); });
window.chrome.webview.postMessage(JSON.stringify({type: 'hello', text: '中文 ✓'}));
</script>"""


def on_message(this, sender, args):
    s = ctypes.c_wchar_p()
    hr = method(args, 5, ctypes.POINTER(ctypes.c_wchar_p))(args, ctypes.byref(s))   # TryGetWebMessageAsString
    text = s.value
    ole32.CoTaskMemFree(s)
    m = json.loads(text)
    log.append(('page→host', hr, m))
    wv = state['wv']
    if m['type'] == 'hello':
        method(wv, 32, W.LPCWSTR)(wv, json.dumps({'reply': '收到：' + m['text']}, ensure_ascii=False))   # PostWebMessageAsJson
    elif m['type'] == 'done':
        user32.PostMessageW(state['hwnd'], 0x0010, 0, 0)                  # WM_CLOSE
    return 0


MSG_INVOKE = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
DONE_INVOKE = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, HRESULT, ctypes.c_void_p)   # 完成回调：(this, 错误码, 结果)


def on_controller(this, hr, ctl):
    log.append(('controller', hr))
    if hr != 0:
        user32.PostMessageW(state['hwnd'], 0x0010, 0, 0)
        return 0
    vtbl = ctypes.cast(ctl, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)(vtbl[1])(ctl)            # IUnknown::AddRef：控制器自己留着
    state['ctl'] = ctl
    wv = ctypes.c_void_p()
    method(ctl, 25, ctypes.POINTER(ctypes.c_void_p))(ctl, ctypes.byref(wv))  # get_CoreWebView2
    state['wv'] = wv.value
    resize(state['hwnd'])
    state['msg_handler'] = h = Handler(MSG_INVOKE, on_message, '57213f19-00e6-49fa-8e07-898ea01ecbd2')
    token = ctypes.c_int64()
    log.append(('add_WebMessageReceived', method(wv.value, 34, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64))(wv.value, h.ptr, ctypes.byref(token))))
    log.append(('NavigateToString', method(wv.value, 6, W.LPCWSTR)(wv.value, PAGE)))
    return 0


def on_env(this, hr, env):
    log.append(('environment', hr))
    if hr != 0:
        user32.PostMessageW(state['hwnd'], 0x0010, 0, 0)
        return 0
    ev = ctypes.cast(env, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(W.ULONG, ctypes.c_void_p)(ev[1])(env)              # AddRef：环境对象自己留着
    state['env'] = env
    state['ctl_handler'] = h = Handler(DONE_INVOKE, on_controller, '6c4819f3-c9b7-4260-8127-c9f5bde7f68c')
    log.append(('CreateController', method(env, 3, W.HWND, ctypes.c_void_p)(env, state['hwnd'], h.ptr)))
    return 0


def main():
    ole32.CoInitializeEx(None, 2)
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=wndproc, hInstance=hinst, lpszClassName='DrWv2Poc',
                     hCursor=user32.LoadCursorW(None, ctypes.c_void_p(32512)))
    if not user32.RegisterClassExW(ctypes.byref(wc)):
        raise OSError('RegisterClassExW')
    hwnd = user32.CreateWindowExW(0, 'DrWv2Poc', 'WebView2 PoC', 0x10CF0000, 100, 100, 800, 500, None, None, hinst, None)
    state['hwnd'] = hwnd
    loader = ctypes.WinDLL(os.path.join(LOADER_DIR, 'WebView2Loader.dll'))
    f = loader.CreateCoreWebView2EnvironmentWithOptions
    f.argtypes = [W.LPCWSTR, W.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
    f.restype = HRESULT
    state['env_handler'] = h = Handler(DONE_INVOKE, on_env, '4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d')
    log.append(('CreateEnvironment', f(None, UDF, None, h.ptr)))
    user32.SetTimer(hwnd, 1, 60000, None)                                 # 60 秒还没结束就算失败
    msg = W.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == 0x0113 and msg.hWnd == hwnd and msg.wParam == 1:   # 自己的 WM_TIMER（WebView2 也有自己的计时器）
            log.append(('timeout',))
            user32.DestroyWindow(hwnd)
            continue
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    json.dump([list(map(str, x)) for x in log], open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


main()
