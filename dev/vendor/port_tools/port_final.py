# -*- coding: utf-8 -*-
"""2.7.2.0 的最终地址：核对虚表各项（旧 +0x16F0）、生成 dark_lock 的 CHECKS（新 exe 的开头字节）"""
import struct, sys
sys.argv = ['x']
g = {}
exec(open(__file__.replace('port_final.py', 'port_rvas.py'), encoding='utf-8').read().split('FUNCS = {')[0], g)
old, new = g['old'], g['new']
OLD = {'POPUP': 0x8fc570, 'FINALIZE': 0x78e780, 'ADD_ITEM': 0x745600, 'TEXT_LABEL': 0x7617c0, 'TEXT_HELP': 0x7615e0, 'TEXT_DTOR': 0x743ae0,
       'RESULT2': 0x7a80d0, 'CALL_FIN': 0x8fd02d, 'OPEN_FILE': 0xd6d280, 'MEMFILE_VT': 0x2ba7d70, 'BIND': 0x900940, 'REFRESH': 0x900610,
       'RESOLVE': 0x74b140, 'SETVIS': 0x734190, 'VT0': 0xce9730, 'NO_ARROW_CHECK': 0x65a758, 'NO_ARROW_FLAG': 0x3d6a216}
NEW = {'POPUP': 0x8fca20, 'FINALIZE': 0x78ec30, 'ADD_ITEM': 0x745ab0, 'TEXT_LABEL': 0x761c70, 'TEXT_HELP': 0x761a90, 'TEXT_DTOR': 0x743f90,
       'RESULT2': 0x7a8580, 'CALL_FIN': 0x8fd4dd, 'OPEN_FILE': 0xd6e970, 'MEMFILE_VT': 0x2baa020, 'BIND': 0x900df0, 'REFRESH': 0x900ac0,
       'RESOLVE': 0x74b5f0, 'SETVIS': 0x734640, 'VT0': 0xceae20, 'NO_ARROW_CHECK': 0x65ac08, 'NO_ARROW_FLAG': 0x3d6d236}
# 虚表：新的每一项 = 旧的那一项 + 0x16F0？
for k in range(8):
    o = struct.unpack_from('<Q', old.data, OLD['MEMFILE_VT'] + 8 * k)[0] - old.base
    n = struct.unpack_from('<Q', new.data, NEW['MEMFILE_VT'] + 8 * k)[0] - new.base
    print('虚表[%d] 旧 %#x 新 %#x 差 %#x' % (k, o, n, n - o))
# 旧 CHECKS 和旧 exe 一致（证明表没抄错）
for k in ('OPEN_FILE', 'BIND', 'REFRESH', 'RESOLVE', 'SETVIS', 'POPUP', 'FINALIZE', 'ADD_ITEM', 'TEXT_LABEL', 'TEXT_HELP', 'TEXT_DTOR', 'RESULT2'):
    print('    (%s, &[%s]),' % (k, ', '.join('0x%02x' % b for b in new.data[NEW[k]:NEW[k] + 16])))
cf = new.data[NEW['CALL_FIN']:NEW['CALL_FIN'] + 5]
print('    (CALL_FIN, &[%s]),' % ', '.join('0x%02x' % b for b in cf), ' 目标', hex(NEW['CALL_FIN'] + 5 + struct.unpack_from('<i', cf, 1)[0]))
print('箭袋指令字节', new.data[NEW['NO_ARROW_CHECK']:NEW['NO_ARROW_CHECK'] + 7].hex(), '→', hex(NEW['NO_ARROW_CHECK'] + 7 + struct.unpack_from('<i', new.data, NEW['NO_ARROW_CHECK'] + 2)[0]))
