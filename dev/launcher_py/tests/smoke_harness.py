# -*- coding: utf-8 -*-
"""对照测试框架自己的冒烟测试：PowerShell 那边能加载、能拿回结果；Python 这边能建 Ctx"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    env = harness.fake_env(tmp)
    r, out = harness.ps_call("$__r = @{ root = (Test-NormalizeGameRoot 'E:\\SteamLibrary\\steamapps\\common\\ELDEN RING\\Game\\eldenring.exe'); "
                             "data = $RngDataDir; code = (Compress-CoopCode 'DR3|v=1|m=rand') }", env)
    print('PS:', r, out[-3:])
    r2, out2 = harness.py_call(lambda ctx: {'data': ctx.RngDataDir, 'paly': ctx.Paly, 'world': ctx.WorldSuffix}, env)
    print('PY:', r2, out2)
    print('数据目录一样:', r['data'] == r2['data'])
