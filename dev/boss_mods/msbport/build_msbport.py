# -*- coding: utf-8 -*-
"""编 msbport.dll（Windows 自带 csc + 整合包带的 .NET 8 引用库 + analysis\\msbdump 里的 SoulsFormats），同 msbtool 的做法"""
import glob, os, shutil, subprocess
H = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.normpath(os.path.join(H, '..', '..', '..'))
NET = glob.glob(os.path.join(PALY, 'launcher', 'dotnet', 'shared', 'Microsoft.NETCore.App', '8.*'))[0]
SF = os.path.join(H, '..', 'analysis', 'msbdump')
refs = [p for p in glob.glob(os.path.join(NET, '*.dll')) if os.path.basename(p).startswith(('System.', 'mscorlib', 'netstandard')) and '.Native.' not in os.path.basename(p)]
out = os.path.join(H, 'msbport.dll')
if os.path.exists(out):
    os.remove(out)
rsp = os.path.join(H, 'build_msbport.rsp')
with open(rsp, 'w', encoding='utf-8') as f:
    f.write('/nostdlib+ /target:exe /out:"%s"\n' % out)
    for r in refs + [os.path.join(SF, 'SoulsFormats.dll')]:
        f.write('/r:"%s"\n' % r)
    f.write('"%s"\n' % os.path.join(H, 'msbport.cs'))
r = subprocess.run([r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe', '/noconfig', '@' + rsp], capture_output=True, text=True, encoding='oem', errors='replace')
err = [l for l in r.stdout.splitlines() if 'error' in l]
print('\n'.join(err[:10]))
if os.path.exists(out) and not err:
    for n in ('SoulsFormats.dll', 'ZstdNet.dll'):
        shutil.copy2(os.path.join(SF, n), os.path.join(H, n))
    shutil.copy2(os.path.join(SF, 'msbdump.runtimeconfig.json'), os.path.join(H, 'msbport.runtimeconfig.json'))
    print('ok')
else:
    print('failed')
    print(r.stdout[-2000:])
