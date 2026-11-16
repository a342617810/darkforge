import sys, os, io
R = r'E:/SteamLibrary/steamapps/common/ELDEN RING/Game/dark_reforged/launcher/reroll'
sys.path.insert(0, R)
import erlib
from PIL import Image
G = r'E:/SteamLibrary/steamapps/common/ELDEN RING/Game/'
erlib.DLL_DIRS[:] = [G, os.path.join(R, 'bin')]
OUT = os.path.dirname(os.path.abspath(__file__))
arc = erlib.GameArchive(G + 'Data0.bhd', open(os.path.join(R, 'data', 'menu', 'data0_key.pem'), encoding='ascii').read())
srcs = {'vanilla': lambda: erlib.dcx_decompress(arc.read('/menu/hi/02_title.tpf.dcx'))}
for tag, p in [('jianxin', '剑心修罗v0.4.6（正式版最终测试）/SHS/menu/hi/02_title.tpf.dcx'), ('vins', 'ELDEN VINS/mod/menu/hi/02_title.tpf.dcx'),
               ('ga', 'GoldenAge3.6.8/GA/menu/hi/02_title.tpf.dcx'), ('fahun', 'mod/menu/hi/02_title.tpf.dcx')]:
    srcs[tag] = (lambda p=p: erlib.read_dcx(G + p))
for tag, get in srcs.items():
    try:
        t = erlib.read_tpf(get())
    except Exception as e:
        print(tag, 'ERR', e); continue
    d = os.path.join(OUT, tag); os.makedirs(d, exist_ok=True)
    for x in t['tex']:
        try:
            im = Image.open(io.BytesIO(x['data']))
            im.load()
            im.save(os.path.join(d, x['name'] + '.png'))
            print(tag, x['name'], im.size, im.mode)
        except Exception as e:
            print(tag, x['name'], 'decode fail', e, x['fmt'])
