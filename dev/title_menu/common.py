import sys, os, io
R = r'E:/SteamLibrary/steamapps/common/ELDEN RING/Game/dark_reforged/launcher/reroll'
sys.path.insert(0, R)
import erlib
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
G = r'E:/SteamLibrary/steamapps/common/ELDEN RING/Game/'
erlib.DLL_DIRS[:] = [G, os.path.join(R, 'bin')]
OUT = os.path.dirname(os.path.abspath(__file__))
arc = erlib.GameArchive(G + 'Data0.bhd', open(os.path.join(R, 'data', 'menu', 'data0_key.pem'), encoding='ascii').read())
srcs = {'vanilla': lambda: erlib.dcx_decompress(arc.read('/menu/hi/01_common.tpf.dcx'))}
for tag, p in [('jianxin', '剑心修罗v0.4.6（正式版最终测试）/SHS/menu/hi/01_common.tpf.dcx'), ('vins', 'ELDEN VINS/mod/menu/hi/01_common.tpf.dcx'),
               ('ga', 'GoldenAge3.6.8/GA/menu/hi/01_common.tpf.dcx'), ('fahun', 'mod/menu/hi/01_common.tpf.dcx')]:
    srcs[tag] = (lambda p=p: erlib.read_dcx(G + p))
for tag, get in srcs.items():
    t = erlib.read_tpf(get())
    names = [x['name'] for x in t['tex']]
    hit = [x for x in t['tex'] if 'itle' in x['name'] or 'Shiki' in x['name'] or 'Logo' in x['name'] or 'LOGO' in x['name']]
    print(tag, len(names), [(x['name']) for x in hit])
    d = os.path.join(OUT, 'c_' + tag); os.makedirs(d, exist_ok=True)
    for x in hit:
        im = Image.open(io.BytesIO(x['data'])); im.load()
        im.save(os.path.join(d, x['name'] + '.png'))
        print('   ', x['name'], im.size)
