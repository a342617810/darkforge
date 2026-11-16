# -*- coding: utf-8 -*-
"""做离线增量更新包（用户 2026-11-10「先做离线增量包」）：比较两个完整整合包，只收变了的文件。
  python dev\\tools\\make_delta.py <旧版本.zip> <新版本.zip> [输出.zip]
输出默认放在新版本旁边：Darkforge_v<旧>_to_v<新>_update.zip。可以拿更早的版本做旧版本，直接跨几个版本。
格式见 launcher\\update.py（玩家在启动器点「导入更新包」应用）。
- 两个包都要是 make_package.py 打的（顶层文件夹 darkforge\\，launcher\\version.txt 是版本号）；
- 改了 / 删了 launcher\\python 里的文件就拒绝（更新程序自己在用，换不了，只能发完整包）；
- 玩家能改的 JSON（MERGE_JSON）另外带上旧版本的样子，应用时按键合并，玩家改过的设置不丢。"""
import hashlib
import json
import os
import sys
import zipfile

TOP = 'darkforge/'
VERSION_FILE = 'launcher/version.txt'
MERGE_JSON = ['launcher/reroll/settings.json']
BLOCKED = ('launcher/python/',)

# 公开发布（publish_update.py 传到公开仓库）时拦住的文件，按 2026-10-29 查的各作者许可（记忆 nexus-publish-permissions）：
# PUBLIC_DENY 作者明确不许转载 / 许可不许分发：随机器（SoulsRandomizers 许可）
#   Souls Vision、Transmogrify Armor、ELDEN VINS、Modular Wall Jump 2026-11-12 拿到了作者授权，从这两张表里放行了
PUBLIC_DENY = ['randomizer/*']
# PUBLIC_ASK 用了别人的东西、还没拿到许可：默认也拦，确定可以公开后发布时加 --allow-third-party
#   Boss 模组数据、照黄金时代重写的第 5 护符栏
PUBLIC_ASK = ['launcher/reroll/data/bossmods/*', 'dll/dark_slot/*']


def public_check(paths):
    """（不许公开的, 要先确认许可的）"""
    import fnmatch
    deny = [p for p in paths if any(fnmatch.fnmatch(p, g) for g in PUBLIC_DENY)]
    ask = [p for p in paths if p not in deny and any(fnmatch.fnmatch(p, g) for g in PUBLIC_ASK)]
    return deny, ask


def entries(z):
    out = {}
    for i in z.infolist():
        if i.is_dir() or not i.filename.startswith(TOP):
            continue
        rel = i.filename[len(TOP):]
        data = z.read(i)
        out[rel] = (hashlib.sha256(data).hexdigest(), len(data))
    return out


def version(z):
    return z.read(TOP + VERSION_FILE).decode('utf-8-sig').strip()


def build(old_zip, new_zip, out=None):
    zo, zn = zipfile.ZipFile(old_zip), zipfile.ZipFile(new_zip)
    vo, vn = version(zo), version(zn)
    if vo == vn:
        raise SystemExit('两个包的版本号一样（%s），没法做更新包' % vo)
    eo, en = entries(zo), entries(zn)
    changed = sorted(r for r in en if r not in eo or eo[r][0] != en[r][0])
    deleted = sorted(r for r in eo if r not in en)
    bad = [r for r in changed + deleted if r.startswith(BLOCKED)]
    if bad:
        raise SystemExit('改动包括 launcher\\python（%s 等 %d 个），更新程序换不了它，这个版本只能发完整包' % (bad[0], len(bad)))
    if VERSION_FILE not in changed:
        raise SystemExit('新包里没有 %s 的改动' % VERSION_FILE)
    man = {'format': 1, 'name': 'Darkforge', 'from': vo, 'to': vn,
           'files': [{'path': r, 'sha256': en[r][0], 'size': en[r][1], 'old_sha256': eo[r][0] if r in eo else None} for r in changed],
           'delete': [{'path': r, 'old_sha256': eo[r][0]} for r in deleted],
           'merge_json': [r for r in MERGE_JSON if r in changed]}
    out = out or os.path.join(os.path.dirname(os.path.abspath(new_zip)), 'Darkforge_v%s_to_v%s_update.zip' % (vo, vn))
    tmp = out + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr('update.json', json.dumps(man, ensure_ascii=False, indent=1))
        for r in changed:
            z.writestr('files/' + r, zn.read(TOP + r))
        for r in man['merge_json']:
            if r in eo:
                z.writestr('base/' + r, zo.read(TOP + r))
        z.writestr('说明.txt', '暗黑重铸 v%s → v%s 的更新包。\r\n\r\n'
                   '用法：打开启动器 → 工具「导入更新包」→ 选这个 zip。不用解压。\r\n'
                   '只能用在 v%s 上；更早的版本请先导入之前的更新包，或者下载完整的整合包。\r\n'
                   '更新前会自动备份要改动的文件（整合包目录里的「更新备份」），你改过的 settings.json 设置会保留。\r\n\r\n'
                   '启动器里还没有「导入更新包」按钮（v0.10.0 及更早）：先退出游戏，把这个压缩包里 files 文件夹中的所有内容\r\n'
                   '解压到整合包文件夹里（和「启动.bat」同一层），提示重名时选「全部替换」。这样做会覆盖你改过的 settings.json。\r\n'
                   '之后的版本就能直接用「导入更新包」了。\r\n' % (vo, vn, vo))
    os.replace(tmp, out)
    size = sum(en[r][1] for r in changed)
    print('v%s → v%s：改动 %d 个文件（%.1f MB 未压缩）、删除 %d 个；更新包 %.1f MB：%s' % (
        vo, vn, len(changed), size / 1048576, len(deleted), os.path.getsize(out) / 1048576, out))
    deny, ask = public_check(changed + deleted)
    if deny:
        print('注意：这个更新包不能公开发布（publish_update.py 会拒绝），里面有作者不许转载的文件：%s' % '、'.join(deny[:5]))
    elif ask:
        print('注意：这个更新包里有还没确认许可的第三方文件（公开发布要加 --allow-third-party）：%s' % '、'.join(ask[:5]))
    return out


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
