# 玩家自己加的东西（用户 2026-11-16「怎么能方便玩家可以自己手动编辑yafsml」→「两层都做」）：
#   mods\                 整合包根目录，放游戏文件类的 mod（外观、模型、特效……解压后带 parts / chr / sfx 这些文件夹的）。
#                         一个 mod 一个文件夹，每次启动自动扫描，加进 YAFSML 的 [mod]，排在整合包自己的包前面（同名文件以整合包为准，不会把整合包弄坏）；
#                         文件夹名以 _ 开头 = 停用；按名字顺序。解压多套了一两层文件夹的自己往里找；直接把 parts 之类放进 mods\ 的，把 mods\ 整个当一个 mod。
#   YAFSML自定义.ini      整合包根目录，玩家改加载器设置的地方（yafsml\YAFSML.ini 每次启动按模板重写，改了会被覆盖）：
#                         [patch] [tweak] [log] 等里写的项替换模板里同名的（存档、内存相关的几项不让改，见 $UserIniLocked）；
#                         [mod] 的行排在整合包前面，[mod_after] 的排在最后（同名文件以它为准），[dll] 的加在 DLL 最后（联机的 ersc.dll 之前）。
#                         路径可以写完整的，也可以写相对整合包根目录的。没有这个文件时启动器第一次启动写一份带说明的。
# 两样都不在发布包里（dev\tools\make_package.py 的 EXCL），整合包更新不会动。
# launcher.ps1 和 gui.ps1（网页界面的「模组」按钮）都 dot-source 本文件：这里只定义函数，不做别的；要先有 $Paly。

$UserModDir  = Join-Path $Paly 'mods'
$UserIniPath = Join-Path $Paly 'YAFSML自定义.ini'
# 不让玩家改的：存档文件名（改了会读写原版 / 法魂的存档）、防止往存档写「已修改」、内存分配器（关掉进游戏就崩）、游戏
$UserIniLocked = @('game', 'replace_save_filename', 'replace_seamless_coop_save_filename', 'prevent_regulation_save_write', 'patch_mem')
# 游戏数据的顶层文件夹 / 文件（mod 文件夹里有这些才算找到了 mod 的根）
$GameDataNames = @('action', 'asset', 'chr', 'cutscene', 'event', 'expression', 'facegen', 'font', 'map', 'material', 'menu', 'movie',
                   'msg', 'other', 'param', 'parts', 'script', 'sd', 'sfx', 'shader', 'sound', 'regulation.bin')

function Test-GameDataRoot([string]$Dir) {
    foreach ($n in $GameDataNames) { if (Test-Path -LiteralPath (Join-Path $Dir $n)) { return $true } }
    return $false
}

# 一个 mod 文件夹里真正的根（带 parts / chr … 的那一层）：自己就是，或者往里找两层（压缩包解压常多套一层）；
# 找到不止一个（几个版本让玩家挑的那种）返回全部，交给调用的报错
function Find-ModRoots([string]$Dir, [int]$Depth = 2) {
    if (Test-GameDataRoot $Dir) { return @($Dir) }
    if ($Depth -le 0) { return @() }
    $found = @()
    foreach ($d in @(Get-ChildItem -LiteralPath $Dir -Directory -ErrorAction SilentlyContinue | Sort-Object Name)) {
        if ($d.Name.StartsWith('_')) { continue }
        $found += @(Find-ModRoots $d.FullName ($Depth - 1))
    }
    return $found
}

# mods\ 里的每个 mod：@{ Name; Path（根，没找到是 $null）; Off（_ 开头停用）; Issues（给玩家看的问题）}
function Get-UserModInfo {
    $out = @()
    if (-not (Test-Path -LiteralPath $UserModDir)) { return $out }
    if (Test-GameDataRoot $UserModDir) {
        # 直接把 parts 之类放进了 mods\：整个 mods\ 当一个 mod（里面别的子文件夹不会被当成游戏文件，不碍事）
        $out += @{ Name = 'mods'; Path = $UserModDir; Off = $false; Issues = @() }
    }
    foreach ($d in @(Get-ChildItem -LiteralPath $UserModDir -Directory -ErrorAction SilentlyContinue | Sort-Object Name)) {
        if ($GameDataNames -contains $d.Name.ToLowerInvariant()) { continue }        # 上面整个 mods\ 已经算了
        if ($d.Name.StartsWith('_')) { $out += @{ Name = $d.Name; Path = $null; Off = $true; Issues = @() }; continue }
        $roots = @(Find-ModRoots $d.FullName)
        $m = @{ Name = $d.Name; Path = $null; Off = $false; Issues = @() }
        if ($roots.Count -eq 0) {
            $m.Issues += '里面没找到游戏文件（parts、chr、sfx 这类文件夹），没有加载'
            if (@(Get-ChildItem -LiteralPath $d.FullName -Filter '*.dll' -File -Recurse -Depth 2 -ErrorAction SilentlyContinue).Count) {
                $m.Issues += '里面是 DLL：DLL 类的 mod 要放进整合包的 dll 文件夹'
            }
        } elseif ($roots.Count -gt 1) {
            $m.Issues += ('里面有 ' + $roots.Count + ' 套文件（' + (($roots | ForEach-Object { Split-Path $_ -Leaf }) -join '、') +
                          '），没有加载：留下要用的那套，别的删掉或在文件夹名前加 _')
        } else {
            $m.Path = $roots[0]
        }
        $out += $m
    }
    foreach ($m in $out) {
        if (-not $m.Path) { continue }
        if (Test-Path -LiteralPath (Join-Path $m.Path 'regulation.bin')) {
            $m.Issues += '带了 regulation.bin：里面的数值改动不会生效（整合包自己的优先），外观之类的照常加载'
        }
        if (@(Get-ChildItem -LiteralPath $m.Path -Filter '*.dll' -File -ErrorAction SilentlyContinue).Count) {
            $m.Issues += '里面的 DLL 不会加载：要放进整合包的 dll 文件夹'
        }
    }
    return $out
}

# 路径：完整路径照用；相对路径按整合包根目录算
function Resolve-UserPath([string]$P) {
    $P = $P.Trim().Trim('"')
    if (-not $P) { return '' }
    if ([System.IO.Path]::IsPathRooted($P)) { return $P }
    return [System.IO.Path]::GetFullPath((Join-Path $Paly $P))
}

# YAFSML自定义.ini → @{ Sections = 有序字典 { 段名小写 = 有序字典 { 键 = 值 } }; Order = 段名（原样）}；没有文件 = 空的
function Read-UserIni {
    $sec = [ordered]@{}
    $names = @{}
    if (-not (Test-Path -LiteralPath $UserIniPath)) { return @{ Sections = $sec; Names = $names } }
    $cur = $null
    foreach ($raw in [System.IO.File]::ReadAllLines($UserIniPath, [System.Text.Encoding]::UTF8)) {
        $l = $raw.Trim()
        if (-not $l -or $l.StartsWith(';') -or $l.StartsWith('#')) { continue }
        if ($l -match '^\[([^\]]+)\]$') {
            $cur = $Matches[1].Trim().ToLowerInvariant()
            $names[$cur] = $Matches[1].Trim()
            if (-not $sec.Contains($cur)) { $sec[$cur] = [ordered]@{} }
            continue
        }
        if ($null -eq $cur -or $l -notmatch '^([^=]+?)\s*=\s*(.*)$') { continue }
        $sec[$cur][$Matches[1].Trim()] = $Matches[2].Trim()
    }
    return @{ Sections = $sec; Names = $names }
}

# 没有 YAFSML自定义.ini 就写一份带说明的（UTF-8 带 BOM：老系统的记事本也认得中文）；返回路径
function New-UserIni {
    if (Test-Path -LiteralPath $UserIniPath) { return $UserIniPath }
    $t = @(
        '; 暗黑重铸 · YAFSML 自定义配置（自己改这个文件；整合包更新不会动它）',
        '; 启动器每次启动都会重新生成 yafsml\YAFSML.ini，直接改那个会被覆盖，所以改这里。改完下次启动游戏生效。',
        ';',
        '; [patch] [tweak] [log]：写在这里的设置替换整合包里同名的设置（下面的例子去掉行首的分号就生效）。',
        ';     存档和内存相关的几项（replace_save_filename、replace_seamless_coop_save_filename、prevent_regulation_save_write、patch_mem）不能改，写了也不生效。',
        '; [mod]：额外加载的 mod，一行一个「名字=文件夹」，文件夹里是 parts、chr、sfx 这些。排在整合包前面，同名文件以整合包为准。',
        ';     更省事的办法：把 mod 文件夹直接放进整合包根目录的 mods 文件夹，不用写这里。',
        '; [mod_after]：排在整合包后面，同名文件以这个 mod 为准（可能让整合包的功能失效，确定需要再用）。',
        '; [dll]：额外加载的 DLL，一行一个「名字=dll 路径」（也可以直接放进整合包的 dll 文件夹）。',
        '; 路径可以写完整路径，也可以写相对整合包根目录的路径。',
        '',
        '[patch]',
        '; 跳过开场动画（整合包默认就是 1）',
        ';skip_intro=1',
        '; 游戏里能用输入法打中文（整合包默认 0）',
        ';enable_ime=1',
        '',
        '[tweak]',
        ';cpu_affinity=0',
        '',
        '[mod]',
        ';look=D:\ERMods\look',
        '',
        '[mod_after]',
        '',
        '[dll]',
        ''
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($UserIniPath, $t, (New-Object System.Text.UTF8Encoding($true)))
    return $UserIniPath
}

# 要加进 YAFSML.ini 的玩家内容：@{ Before = [mod] 前面的行; After = [mod] 最后的行; Dll = [dll] 的行; Mods = mods\ 里加载了的名字; Notes = 给玩家看的提示 }
function Get-UserLoadLines {
    $r = @{ Before = ''; After = ''; Dll = ''; Mods = @(); Notes = @() }
    $before = @(); $after = @(); $dll = @()
    $used = @{}
    $key = {
        param($prefix, $name)
        $k = $prefix + ($name -replace '[^A-Za-z0-9_]', '_')
        $k2 = $k; $n = 2
        while ($used.ContainsKey($k2)) { $k2 = $k + '_' + $n; $n++ }
        $used[$k2] = $true
        return $k2
    }
    foreach ($m in @(Get-UserModInfo)) {
        foreach ($i in $m.Issues) { $r.Notes += ('mods\' + $m.Name + '：' + $i) }
        if ($m.Off -or -not $m.Path) { continue }
        $before += ((& $key 'user_mod_' $m.Name) + '=' + $m.Path)
        $r.Mods += $m.Name
    }
    if ($before.Count) { $before = @('; 玩家的 mod（整合包根目录 mods\，自动扫描；排在整合包前面，同名文件以整合包为准）') + $before }
    $ini = Read-UserIni
    foreach ($s in @('mod', 'mod_after', 'dll')) {
        if (-not $ini.Sections.Contains($s)) { continue }
        foreach ($k in @($ini.Sections[$s].Keys)) {
            $v = [string]$ini.Sections[$s][$k]
            $cond = ''
            if ($s -eq 'dll' -and $v.Contains('|')) { $cond = $v.Substring($v.IndexOf('|')); $v = $v.Substring(0, $v.IndexOf('|')) }
            $p = Resolve-UserPath $v
            if (-not $p -or -not (Test-Path -LiteralPath $p)) {
                $r.Notes += ('YAFSML自定义.ini [' + $s + '] 的 ' + $k + '：找不到 ' + $v + '，没有加载')
                continue
            }
            # Seamless Co-op 只能走联机启动（联机计划 13.2 G9）：那里会查联机密码（空的会让游戏退出）、把联机存档和单机分开
            if ($s -eq 'dll' -and [System.IO.Path]::GetFileName($p) -ieq 'ersc.dll') {
                $r.Notes += ('YAFSML自定义.ini [dll] 的 ' + $k + '：Seamless Co-op（ersc.dll）不在这里加载，联机请用启动器的「联机」启动')
                continue
            }
            $line = (& $key 'custom_' $k) + '=' + $p + $cond
            if ($s -eq 'mod') { $before += $line } elseif ($s -eq 'mod_after') { $after += $line } else { $dll += $line }
        }
    }
    if ($before.Count) { $r.Before = ($before -join "`r`n") }
    if ($after.Count) { $r.After = ("; YAFSML自定义.ini 的 [mod_after]（排在整合包后面）`r`n" + ($after -join "`r`n")) }
    if ($dll.Count) { $r.Dll = ("; YAFSML自定义.ini 的 [dll]`r`n" + ($dll -join "`r`n")) }
    return $r
}

# 生成的 YAFSML.ini 文字里，按 YAFSML自定义.ini 替换 / 加上设置（[mod] [mod_after] [dll] 以外的段）；返回 @{ Text; Applied = 改了哪些; Notes = 提示 }
function Merge-UserIniSettings([string]$Text) {
    $res = @{ Text = $Text; Applied = @(); Notes = @() }
    $ini = Read-UserIni
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($l in ($Text -split "`r?`n")) { $lines.Add($l) }
    foreach ($s in @($ini.Sections.Keys)) {
        if ($s -in @('mod', 'mod_after', 'dll')) { continue }
        foreach ($k in @($ini.Sections[$s].Keys)) {
            $v = [string]$ini.Sections[$s][$k]
            if ($UserIniLocked -contains $k.ToLowerInvariant()) {
                $res.Notes += ('YAFSML自定义.ini 的 ' + $k + ' 不能改（存档 / 内存相关），用整合包的设置')
                continue
            }
            # 找这一段：[段名] 到下一个 [ 之间
            $h = -1
            for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i].Trim() -match ('^\[' + [regex]::Escape($s) + '\]$')) { $h = $i; break } }
            if ($h -lt 0) {
                $lines.Add(''); $lines.Add('[' + $ini.Names[$s] + ']'); $lines.Add($k + '=' + $v)
                $res.Applied += ('[' + $ini.Names[$s] + '] ' + $k + '=' + $v)
                continue
            }
            $end = $lines.Count
            for ($i = $h + 1; $i -lt $lines.Count; $i++) { if ($lines[$i].Trim().StartsWith('[')) { $end = $i; break } }
            $hit = -1; $last = $h
            for ($i = $h + 1; $i -lt $end; $i++) {
                $t = $lines[$i].Trim()
                if ($t -and -not $t.StartsWith(';')) { $last = $i }
                if ($t -match ('^' + [regex]::Escape($k) + '\s*=')) { $hit = $i }
            }
            if ($hit -ge 0) { $lines[$hit] = $k + '=' + $v } else { $lines.Insert($last + 1, $k + '=' + $v) }
            $res.Applied += ('[' + $ini.Names[$s] + '] ' + $k + '=' + $v)
        }
    }
    $res.Text = ($lines -join "`r`n")
    return $res
}

# 诊断包用：mods\ 和 YAFSML自定义.ini 的情况（几行文字）
function Get-UserModSummary {
    $out = @()
    $mods = @(Get-UserModInfo)
    if ($mods.Count) {
        $out += ('mods 文件夹：' + (($mods | ForEach-Object {
            $_.Name + $(if ($_.Off) { '（停用）' } elseif (-not $_.Path) { '（没加载）' } elseif ($_.Path -eq $UserModDir) { '（直接放在 mods 里的）' } elseif ($_.Path -ne (Join-Path $UserModDir $_.Name)) { '（根：' + $_.Path.Substring($UserModDir.Length).TrimStart('\') + '）' } else { '' })
        }) -join '、'))
    } else { $out += 'mods 文件夹：没有' }
    $out += ('YAFSML自定义.ini：' + $(if (Test-Path -LiteralPath $UserIniPath) { '有（诊断包里附了一份）' } else { '没有' }))
    return $out
}
