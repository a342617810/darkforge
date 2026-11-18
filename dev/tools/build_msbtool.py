# -*- coding: utf-8 -*-
"""编 launcher\\reroll\\data\\msbtool\\msbtool.dll（Windows 自带 csc + 整合包带的 .NET 8 引用库 + 运行时用的那份 SoulsFormats：
launcher\\reroll\\cache\\msbtool 里从随机器单文件包取出来的，没有就先跑一次重随 / sc.extragrace.tool()）。
  python dev\\tools\\build_msbtool.py"""
import glob
import os
import subprocess
import sys

H = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(H, '..', '..'))
RR = os.path.join(PALY, 'launcher', 'reroll')
TOOL = os.path.join(RR, 'data', 'msbtool')
NET = glob.glob(os.path.join(PALY, 'launcher', 'dotnet', 'shared', 'Microsoft.NETCore.App', '8.*'))[0]
SF = os.path.join(RR, 'cache', 'msbtool', 'SoulsFormats.dll')
if not os.path.isfile(SF):
    sys.path.insert(0, RR)
    from sc import extragrace
    d, why = extragrace.tool()
    if not d:
        sys.exit('拿不到 SoulsFormats：' + why)
refs = [p for p in glob.glob(os.path.join(NET, '*.dll')) if os.path.basename(p).startswith(('System.', 'mscorlib', 'netstandard')) and '.Native.' not in os.path.basename(p)]
out = os.path.join(TOOL, 'msbtool.new.dll')
rsp = os.path.join(TOOL, 'build_msbtool.rsp')
with open(rsp, 'w', encoding='utf-8') as f:
    f.write('/nostdlib+ /target:exe /out:"%s"\n' % out)
    for r in refs + [SF]:
        f.write('/r:"%s"\n' % r)
    f.write('"%s"\n' % os.path.join(TOOL, 'msbtool.cs'))
r = subprocess.run([r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe', '/noconfig', '@' + rsp], capture_output=True, text=True, encoding='oem', errors='replace')
os.remove(rsp)
err = [l for l in r.stdout.splitlines() if 'error' in l]
if err or not os.path.isfile(out):
    print('\n'.join(err[:20]) or r.stdout[-2000:])
    if os.path.isfile(out):
        os.remove(out)
    sys.exit('failed')
os.replace(out, os.path.join(TOOL, 'msbtool.dll'))
print('ok')
