# -*- coding: utf-8 -*-
"""定时备份（用户 2026-11-19「取消启动前备份和回复备份 改为定时备份 默认10min一次」「最多5个」「存成压缩包」）：dfl/backup.py 的
new_rng_timed_backup / timed_backup_due / 间隔设置 / 压缩包的列出和恢复，dfl/watch.py 的 TimedBackup。
全在假的 APPDATA 和临时的整合包根目录里跑（不碰真的存档）；最后一项只读地拿真存档核对存档格式的解析（没有就跳过）。
用法：python test_timed_backup.py"""
import datetime
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PALY = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, os.path.join(PALY, 'launcher'))
REAL_APPDATA = os.environ.get('APPDATA', '')

TMP = tempfile.mkdtemp(prefix='dftimed_')
os.environ['APPDATA'] = os.path.join(TMP, 'AppData', 'Roaming')
os.environ['LOCALAPPDATA'] = os.path.join(TMP, 'AppData', 'Local')
os.environ['DARKFORGE_ROOT'] = os.path.join(TMP, 'pack')
for d in (os.environ['APPDATA'], os.environ['LOCALAPPDATA'], os.path.join(TMP, 'pack', 'launcher', 'logs')):
    os.makedirs(d, exist_ok=True)

from dfl import backup, core, watch  # noqa: E402

FAILS = []
CLOCK = [datetime.datetime(2026, 11, 19, 20, 0, 0)]
backup._now = lambda: CLOCK[0]


def tick(sec):
    CLOCK[0] += datetime.timedelta(seconds=sec)


def check(name, cond, detail=''):
    print(('  ok  ' if cond else '  失败 ') + name + ('' if cond else '：' + str(detail)))
    if not cond:
        FAILS.append(name)


def fake_save(n=3, size=4096, seed=b'a'):
    """BND4：n 块，每块开头 16 字节是后面内容的 MD5（照游戏存档的样子）"""
    hdr_size = 0x20
    data_off = 0x40 + n * hdr_size
    head = bytearray(data_off)
    head[0:4] = b'BND4'
    struct.pack_into('<i', head, 0x0C, n)
    struct.pack_into('<q', head, 0x20, hdr_size)
    body = b''
    for i in range(n):
        payload = (seed * (size - 16))[:size - 16] + bytes([i])
        payload = payload[:size - 16]
        ent = hashlib.md5(payload).digest() + payload
        pos = 0x40 + i * hdr_size
        struct.pack_into('<q', head, pos + 8, len(ent))
        struct.pack_into('<I', head, pos + 16, data_off + len(body))
        body += ent
    return bytes(head) + body


def put(path, data, age=3600):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    t = time.time() - age
    os.utime(path, (t, t))


ctx = core.Ctx('watch')
SID = os.path.join(ctx.RngSaveRoot, '76561190000000001')
SAVE = os.path.join(SID, 'ER0000.rng')
REC0 = os.path.join(ctx.RngRecordDir, 'items_0.txt')
REC1 = os.path.join(ctx.RngRecordDir, '联机', 'items_1.txt')
put(SAVE, fake_save())
put(REC0, 'name\taa\nw\t1\n'.encode('utf-8'))
put(REC1, 'name\tbb\n'.encode('utf-8'))


def timed():
    return [b for b in backup.get_rng_backups(ctx) if b.Tag == backup.RngTimedTag]


def ops_log():
    try:
        return open(ctx.RngOpsLog, encoding='utf-8-sig').read()
    except OSError:
        return ''


print('存档格式')
check('假存档 MD5 对得上', backup.save_data_ok(fake_save()))
bad = bytearray(fake_save())
bad[-1] ^= 0xFF
check('改了一个字节就不对', not backup.save_data_ok(bytes(bad)))
check('截短了不对', not backup.save_data_ok(fake_save()[:3000]))
check('不是 BND4 的只要不空就算', backup.save_data_ok(b'xyz') and not backup.save_data_ok(b''))

print('存一份')
r, p = backup.new_rng_timed_backup(ctx)
check('存了', r == 'saved' and p and p.endswith('_定时.zip'), (r, p))
with zipfile.ZipFile(p) as z:
    names = sorted(z.namelist())
    info = json.loads(z.read('backup_info.json').decode('utf-8'))
    same_save = z.read('76561190000000001/ER0000.rng') == open(SAVE, 'rb').read()
check('压缩包里的文件', names == sorted(['76561190000000001/ER0000.rng', '角色记录/items_0.txt', '角色记录/联机/items_1.txt', 'backup_info.json']), names)
check('存档原样', same_save)
check('备份信息', info.get('tag') == '定时' and info.get('mode') == '游戏中' and info.get('sig'), info)
lst = timed()
check('列得出来', len(lst) == 1 and lst[0].Zip and lst[0].Saves == 1 and lst[0].Records == 2, lst)
check('记了存档操作日志', '定时备份（游戏中）：存档 1 个、角色记录 2 个 → 20261119_200000_定时.zip' in ops_log(), ops_log()[-300:])

print('没变就不存、存档刚写过等一会儿、撞上在写的不要')
tick(60)
r, _ = backup.new_rng_timed_backup(ctx)
check('和上一份一样', r == 'same', r)
put(REC0, 'name\taa\nw\t1\nw\t2\n'.encode('utf-8'))
put(SAVE, fake_save(seed=b'b'), age=1)
r, _ = backup.new_rng_timed_backup(ctx)
check('存档 1 秒前刚写过：等', r == 'busy', r)
put(SAVE, bytes(bad), age=60)
r, _ = backup.new_rng_timed_backup(ctx)
check('MD5 对不上：不存', r == 'busy' and len(timed()) == 1, r)
check('记了「正好在写」', '正好在写' in ops_log())
put(SAVE, fake_save(seed=b'b'), age=60)
r, _ = backup.new_rng_timed_backup(ctx)
check('好了就存', r == 'saved' and len(timed()) == 2, r)

print('只留 5 份')
for k in range(6):
    tick(600)
    put(REC0, ('name\taa\nw\t%d\n' % (10 + k)).encode('utf-8'))
    backup.new_rng_timed_backup(ctx)
lst = timed()
zips = [f for f in os.listdir(ctx.RngBackupDir) if f.endswith('.zip')]
check('5 份', len(lst) == 5 and len(zips) == 5, (len(lst), zips))
check('留的是最新的', lst[0].Time == CLOCK[0] and lst[-1].Time == CLOCK[0] - datetime.timedelta(seconds=2400), [b.Time for b in lst])
check('没有临时文件', not [f for f in os.listdir(ctx.RngBackupDir) if f.endswith('.tmp')])

print('间隔')
check('默认 10 分钟', backup.get_backup_interval(ctx) == 10)
check('刚存过：没到', not backup.timed_backup_due(ctx, CLOCK[0] + datetime.timedelta(minutes=9)))
check('差 10 秒也算到了', backup.timed_backup_due(ctx, CLOCK[0] + datetime.timedelta(minutes=10, seconds=-10)))
check('改成 5', backup.set_backup_interval(ctx, '5') == 5 and backup.get_backup_interval(ctx) == 5)
check('5 分钟后到了', backup.timed_backup_due(ctx, CLOCK[0] + datetime.timedelta(minutes=5)))
check('不认识的不改', backup.set_backup_interval(ctx, 7) == 5 and backup.get_backup_interval(ctx) == 5)
with open(ctx.BackupIntervalFile, 'wb') as f:
    f.write(b'abc')
check('文件坏了当 10', backup.get_backup_interval(ctx) == 10)
backup.set_backup_interval(ctx, 10)

print('以前的启动前备份（文件夹）照样列出来')
old = os.path.join(ctx.RngBackupDir, '20261118_170147_启动前')
put(os.path.join(old, '76561190000000001', 'ER0000.rng'), fake_save(seed=b'o'))
put(os.path.join(old, '角色记录', 'items_0.txt'), 'name\told\n'.encode('utf-8'))
with open(os.path.join(old, 'backup_info.json'), 'wb') as f:
    f.write(backup._ps_json_flat({'tag': '启动前', 'time': '2026-11-18 17:01:47', 'mode': '敌人随机', 'sig': 'x'}).encode('utf-8'))
allb = backup.get_rng_backups(ctx)
check('定时 5 份 + 启动前 1 份，新的在前', [b.Tag for b in allb] == ['定时'] * 5 + ['启动前'], [b.Tag for b in allb])

print('定时备份攒满 5 份后删掉以前的启动前 / 恢复前备份（「存档备份」按钮存的不动）')
pre = os.path.join(ctx.RngBackupDir, '20261117_120000_恢复前')
put(os.path.join(pre, '76561190000000001', 'ER0000.rng'), fake_save(seed=b'p'))
with open(os.path.join(pre, 'backup_info.json'), 'wb') as f:
    f.write(backup._ps_json_flat({'tag': '恢复前', 'time': '2026-11-17 12:00:00', 'mode': '', 'sig': 'y'}).encode('utf-8'))
half = os.path.join(ctx.RngBackupDir, '20261116_120000_启动前')       # 没写完的（没有 backup_info.json）：不认，也不删
put(os.path.join(half, '76561190000000001', 'ER0000.rng'), fake_save(seed=b'h'))
manual = os.path.join(TMP, 'pack', '存档备份', '20261115_120000')
put(os.path.join(manual, '76561190000000001', 'ER0000.rng'), fake_save(seed=b'm'))
check('手动存的列得出来', any(b.Tag == '存档备份' for b in backup.get_rng_backups(ctx, os.path.join(TMP, 'pack', '存档备份'))))
keep_old = os.path.join(TMP, '_keep_for_restore_test')          # 放在自动备份文件夹外面，不然也会被删
shutil.copytree(old, keep_old)                   # 下面「文件夹的备份照原样」还要用一份旧格式的
tick(600)
put(REC0, b'name\taa\nw\t77\n')
r, _ = backup.new_rng_timed_backup(ctx)
check('又存了一份（已经满 5 份）', r == 'saved' and len(timed()) == 5, r)
check('启动前、恢复前都删了', not os.path.exists(old) and not os.path.exists(pre))
check('没写完的不动', os.path.exists(half))
check('「存档备份」不动', os.path.exists(manual))
check('记了删掉的', '删掉以前的启动前 / 恢复前备份 2 份' in ops_log(), ops_log()[-400:])
shutil.move(keep_old, old)
allb = backup.get_rng_backups(ctx)

print('不满 5 份时不删')
ctx2_root = os.path.join(TMP, 'AppData2')
os.environ['APPDATA'] = ctx2_root
ctx2 = core.Ctx('watch')
put(os.path.join(ctx2.RngSaveRoot, '76561190000000001', 'ER0000.rng'), fake_save())
old2 = os.path.join(ctx2.RngBackupDir, '20261118_170147_启动前')
put(os.path.join(old2, '76561190000000001', 'ER0000.rng'), fake_save(seed=b'o'))
with open(os.path.join(old2, 'backup_info.json'), 'wb') as f:
    f.write(backup._ps_json_flat({'tag': '启动前', 'time': '2026-11-18 17:01:47', 'mode': '', 'sig': 'x'}).encode('utf-8'))
r, _ = backup.new_rng_timed_backup(ctx2)
check('第一份定时备份：旧的留着', r == 'saved' and os.path.exists(old2), r)
check('prune 直接调也不删', backup.prune_legacy_backups(ctx2) == 0 and os.path.exists(old2))
os.environ['APPDATA'] = os.path.join(TMP, 'AppData', 'Roaming')

print('从压缩包恢复')
pick = timed()[2]
with zipfile.ZipFile(pick.Dir) as z:
    want_save = z.read('76561190000000001/ER0000.rng')
    want_rec0 = z.read('角色记录/items_0.txt')
put(SAVE, fake_save(seed=b'z'))
extra = os.path.join(ctx.RngRecordDir, 'items_5.txt')
put(extra, b'name\tnew\n')
before_dirs = sorted(os.listdir(ctx.RngBackupDir))
done = backup.restore_rng_backup(ctx, pick)
check('存档换回去了', open(SAVE, 'rb').read() == want_save)
check('记录换回去了', open(REC0, 'rb').read() == want_rec0)
check('备份之后才有的记录删掉', not os.path.exists(extra))
check('联机记录还在', os.path.exists(REC1))
check('没再存「恢复前」', sorted(os.listdir(ctx.RngBackupDir)) == before_dirs, sorted(os.listdir(ctx.RngBackupDir)))
check('返回恢复了什么', done == ['存档 76561190000000001', '角色记录 2 个'], done)
check('恢复日志不提恢复前', '恢复前' not in ops_log().splitlines()[-1], ops_log().splitlines()[-1])
tmpdirs = []
with backup.backup_as_dir(pick) as d:
    tmpdirs.append(d)
    check('解出来的文件夹里有存档', os.path.exists(os.path.join(d, '76561190000000001', 'ER0000.rng')))
check('用完临时文件夹删掉', not os.path.exists(tmpdirs[0]))
with backup.backup_as_dir(allb[-1]) as d:
    check('文件夹的备份照原样', d == allb[-1].Dir)

print('游戏的 .bak 和存档一模一样时读 .bak（不碰游戏正在用的存档）')
st = os.stat(SAVE)
shutil.copy2(SAVE, SAVE + '.bak')
check('一样：读 .bak', backup._mirror_bak(SAVE) == SAVE + '.bak')
os.utime(SAVE + '.bak', ns=(st.st_atime_ns, st.st_mtime_ns - 10 ** 9))
check('修改时间不一样：读存档', backup._mirror_bak(SAVE) == SAVE)
os.remove(SAVE + '.bak')
check('没有 .bak：读存档', backup._mirror_bak(SAVE) == SAVE)
good = open(SAVE, 'rb').read()
broken = bytearray(good)
broken[-1] ^= 0xFF
put(SAVE + '.bak', good)
put(SAVE, bytes(broken))                          # 大小、修改时间一样，存档本身是坏的：读的是 .bak 就能存
mt = os.stat(SAVE).st_mtime_ns
os.utime(SAVE + '.bak', ns=(mt, mt))
put(REC0, b'name\taa\nw\t55\n')
r, p = backup.new_rng_timed_backup(ctx)
check('存了', r == 'saved', r)
if p:
    with zipfile.ZipFile(p) as z:
        check('存的是 .bak 的内容', z.read('76561190000000001/ER0000.rng') == good)
put(SAVE, good, age=120)
os.remove(SAVE + '.bak')

print('看守里的定时备份（假时钟）')
now = [1000.0]
tb = watch.TimedBackup(ctx, clock=lambda: now[0])
tick(3600)                                       # 离上一份够久了
put(REC0, b'name\taa\nw\t100\n')
n0 = len(os.listdir(ctx.RngBackupDir))
tb.poll()
check('不到一分钟不看', tb.th is None)
now[0] += 61
tb.poll()
tb.th.join(30)
check('到了：存了', tb.last == 'saved', tb.last)
tb.poll()
check('做完排下一次（60 秒后）', tb.th is None and tb.next == now[0] + 60, (tb.th, tb.next, now[0]))
now[0] += 61
tb.poll()
tb.th.join(30)
check('刚存过、没到间隔：等', tb.last == 'wait', tb.last)
put(REC0, b'name\taa\nw\t101\n')
tb.final()
check('退出游戏后再存一份（不管间隔）', tb.last == 'saved' and timed()[0].Mode == '退出游戏后', (tb.last, timed()[0].Mode))
check('还是只留 5 份', len(timed()) == 5)

print('真存档的格式（只读，没有就跳过）')
real = None
for d in (os.listdir(os.path.join(REAL_APPDATA, 'EldenRing')) if REAL_APPDATA and os.path.isdir(os.path.join(REAL_APPDATA, 'EldenRing')) else []):
    f = os.path.join(REAL_APPDATA, 'EldenRing', d, 'ER0000.rng')
    if os.path.isfile(f):
        real = f
        break
if real:
    sys.path.insert(0, os.path.join(PALY, 'launcher', 'reroll'))
    import erlib  # noqa: E402
    data = backup._read_shared(real)
    mine = backup._bnd4_entries(data)
    theirs = [(e['off'], e['size']) for e in erlib.Bnd4(data).entries.values()]
    check('和 erlib 解析的一样（%d 块）' % len(mine), mine == theirs, (mine[:3], theirs[:3]))
    check('真存档 MD5 都对', backup.save_data_ok(data))
else:
    print('  （没有真存档，跳过）')

shutil.rmtree(TMP, ignore_errors=True)
print('失败 %d 项' % len(FAILS) if FAILS else '全部通过')
sys.exit(1 if FAILS else 0)
