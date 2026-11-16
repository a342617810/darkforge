# Dark Reforged · 启动前自动备份 / 恢复（启动器和图形界面共用，用 . 引入）
# 我们自己的东西都在存档文件夹 %APPDATA%\EldenRing 下的 DarkReforged\ 里（游戏自己的 <SteamID>\ER0000.rng、GraphicsConfig.xml 不动）：
#   DarkReforged\角色记录\     DLL 记的装备配方（items_<格子>.txt）、锁定名单、免费许愿次数，一次性重随的结果（once.json）
#       角色记录\联机\            联机（Seamless Co-op）存档 ER0000.rng.co2 的角色的同样这些（格子编号和单机各算各的，dev\coop\联机计划.md 1.1）
#   DarkReforged\启动前备份\   每次启动游戏前（两种启动方式都一样）存一份：
#       <时间>_启动前\<SteamID>\ER0000.rng、<时间>_启动前\角色记录\…、backup_info.json（什么时候、哪种启动）
#   DarkReforged\旧文件\       不再使用的：RNG Lands 时代的 RNGLands_*（RNG Lands\）、重置前的一次性重随记录等，确认不要了可以整个删掉
#   DarkReforged\version.txt   上次用的整合包版本（更新提醒）
# 2026-10-29 以前这些都散在 EldenRing 根目录（DarkReforged_*.txt、DarkReforged_启动前备份\ 等）：Move-RngLegacyFiles 搬进来。
# 角色记录是按存档里的角色记的，恢复时和存档一起换。
# 和「备份存档」按钮（整合包里的「存档备份」）的文件夹结构相同，恢复时两种都能用；以前的备份（记录直接放在备份里、带 DarkReforged_ 前缀）也能恢复。
# 放在存档旁边而不是整合包目录：换一个整合包目录启动也能找回来。
# 和上一份内容完全相同（存档、记录都没变）就不重复存；启动前备份只留最近 $RngBackupKeep 份（一份约 30 MB）。

$RngSaveRoot    = Join-Path $env:APPDATA 'EldenRing'
$RngDataDir     = Join-Path $RngSaveRoot 'DarkReforged'
$RngRecordDir   = Join-Path $RngDataDir '角色记录'
$RngBackupDir   = Join-Path $RngDataDir '启动前备份'
$RngOldDir      = Join-Path $RngDataDir '旧文件'
$RngVersionFile = Join-Path $RngDataDir 'version.txt'
$RngBackupKeep  = 10

# 存档操作记录 launcher\logs\save_ops.txt（留最近 300 行，诊断包会带上）：每次备份 / 恢复 / 删旧备份 / 整理旧文件记一行。
# 图形界面（备份、恢复按钮）和启动器（启动前备份）都会写；玩家说「恢复以后进度没了」之类的时候看这个
$RngOpsLog = Join-Path $PSScriptRoot 'logs\save_ops.txt'
function Add-RngOpsLog([string]$Text) {
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $RngOpsLog -Parent) | Out-Null
        $old = @(if (Test-Path -LiteralPath $RngOpsLog) { [System.IO.File]::ReadAllLines($RngOpsLog, [System.Text.Encoding]::UTF8) })
        $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $Text
        [System.IO.File]::WriteAllLines($RngOpsLog, [string[]](@($old | Select-Object -Last 299) + $line), (New-Object System.Text.UTF8Encoding($true)))
    } catch { }
}

# 现在的 Dark Reforged 存档：<SteamID>\ER0000.rng，联机的 <SteamID>\ER0000.rng.co2（.bak 是游戏自己留的上一份，不备份）
$RngSaveNames = @('ER0000.rng', 'ER0000.rng.co2')
function Get-RngSaveFiles {
    $out = @()
    foreach ($d in (Get-ChildItem -LiteralPath $RngSaveRoot -Directory -ErrorAction SilentlyContinue)) {
        foreach ($n in $RngSaveNames) {
            $f = Join-Path $d.FullName $n
            if (Test-Path -LiteralPath $f) { $out += Get-Item -LiteralPath $f }
        }
    }
    return $out
}

# 一份备份（或任意文件夹）里的存档文件：单机的、联机的都算
function Get-RngSavesIn([string]$Dir) {
    return @(Get-ChildItem -LiteralPath $Dir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -in $RngSaveNames })
}

# 角色记录：不给 $Backup 是现在的（角色记录\ 和 角色记录\联机\ 下的 .txt / .json；写到一半的 .tmp 不算）；
# 给一份备份的目录：新的在 <备份>\角色记录\（联机的在里面的 联机\），2026-10-29 以前的直接在备份里（DarkReforged_*.txt，版本记录不算；DarkReforged_once.json）
function Get-RngRecordFiles([string]$Backup = '') {
    $dir = if ($Backup) { Join-Path $Backup '角色记录' } else { $RngRecordDir }
    if ($Backup -and -not (Test-Path -LiteralPath $dir)) {
        return @(Get-ChildItem -LiteralPath $Backup -File -Filter 'DarkReforged_*' -ErrorAction SilentlyContinue |
            Where-Object { ($_.Extension -eq '.txt' -and $_.Name -ne 'DarkReforged_version.txt') -or $_.Name -eq 'DarkReforged_once.json' })
    }
    $out = @()
    foreach ($d in @($dir, (Join-Path $dir '联机'))) {
        $out += @(Get-ChildItem -LiteralPath $d -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @('.txt', '.json') })
    }
    return $out
}

# 记录在 角色记录\ 里的相对路径（联机的是 联机\<名字>；以前的备份里带 DarkReforged_ 前缀）
function Get-RngRecordName($File) {
    $n = ($File.Name -replace '^DarkReforged_', '')
    if ($File.Directory.Name -eq '联机') { return ('联机\' + $n) }
    return $n
}

# 把记录复制到 <$Dir>\<相对路径>（联机的要先建 联机\）
function Copy-RngRecord($File, [string]$Dir) {
    $to = Join-Path $Dir (Get-RngRecordName $File)
    New-Item -ItemType Directory -Force -Path (Split-Path $to -Parent) | Out-Null
    Copy-Item -LiteralPath $File.FullName -Destination $to -Force
}

# 文件的指纹（大小 + 修改时间）：判断和上一份备份是不是一样
function Get-RngFileSig($Files) {
    return (@($Files | Sort-Object FullName | ForEach-Object { $_.FullName + '|' + $_.Length + '|' + $_.LastWriteTimeUtc.Ticks }) -join ';')
}

# 把 $Item（文件或文件夹）挪到 $To；$To 已经有了：文件留修改时间新的那份，另一份放旧文件\（名字后面加时间）；文件夹挪进旧文件\
function Move-RngItem($Item, [string]$To) {
    New-Item -ItemType Directory -Force -Path (Split-Path $To -Parent) | Out-Null
    if (-not (Test-Path -LiteralPath $To)) { Move-Item -LiteralPath $Item.FullName -Destination $To; return }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    New-Item -ItemType Directory -Force -Path $RngOldDir | Out-Null
    $cur = Get-Item -LiteralPath $To
    if (-not $Item.PSIsContainer -and $Item.LastWriteTimeUtc -gt $cur.LastWriteTimeUtc) {
        Move-Item -LiteralPath $cur.FullName -Destination (Join-Path $RngOldDir ($cur.Name + '.' + $stamp))
        Move-Item -LiteralPath $Item.FullName -Destination $To
    } else {
        Move-Item -LiteralPath $Item.FullName -Destination (Join-Path $RngOldDir ($Item.Name + '.' + $stamp))
    }
}

# 旧版散在 EldenRing 根目录的东西搬进 DarkReforged\（见文件开头）。游戏开着时不搬（DLL 可能正在写）；
# 搬不动的（被占用）跳过，下次再搬。返回搬了几项
function Move-RngLegacyFiles {
    if (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) { return 0 }
    if (-not (Test-Path -LiteralPath $RngSaveRoot)) { return 0 }
    $n = 0
    # DarkReforged_<名字>：版本记录 → version.txt；.txt / .json → 角色记录\<名字>；别的（.before_reset、.tmp……）→ 旧文件\
    foreach ($f in @(Get-ChildItem -LiteralPath $RngSaveRoot -File -Filter 'DarkReforged_*' -ErrorAction SilentlyContinue)) {
        $name = Get-RngRecordName $f
        $to = Join-Path $RngOldDir $name
        if ($name -eq 'version.txt') {
            $to = $RngVersionFile
        } elseif ($f.Extension -in @('.txt', '.json')) {
            $to = Join-Path $RngRecordDir $name
        }
        try { Move-RngItem $f $to; $n++ } catch { }
    }
    # 启动前备份：每一份挪进 启动前备份\，挪空了删掉旧文件夹
    $oldBk = Join-Path $RngSaveRoot 'DarkReforged_启动前备份'
    if (Test-Path -LiteralPath $oldBk) {
        foreach ($d in @(Get-ChildItem -LiteralPath $oldBk -Force -ErrorAction SilentlyContinue)) {
            try { Move-RngItem $d (Join-Path $RngBackupDir $d.Name); $n++ } catch { }
        }
        if (@(Get-ChildItem -LiteralPath $oldBk -Force -ErrorAction SilentlyContinue).Count -eq 0) { Remove-Item -LiteralPath $oldBk -Force -ErrorAction SilentlyContinue }
    }
    # RNG Lands 时代的（RNGLands_*，现在不用）：原样挪进 旧文件\RNG Lands\
    foreach ($x in @(Get-ChildItem -LiteralPath $RngSaveRoot -Filter 'RNGLands_*' -Force -ErrorAction SilentlyContinue)) {
        try { Move-RngItem $x (Join-Path (Join-Path $RngOldDir 'RNG Lands') $x.Name); $n++ } catch { }
    }
    if ($n) { Add-RngOpsLog ('整理旧版的存档文件：搬进 ' + $RngDataDir + ' ' + $n + ' 项') }
    return $n
}

# $Tag：启动前 / 恢复前；返回备份目录（没有可备份的返回 $null，和上一份相同时返回上一份）
function New-RngBackup([string]$Tag, [string]$Mode = '') {
    $what = $Tag + $(if ($Mode) { '，' + $Mode } else { '' })
    $saves = @(Get-RngSaveFiles)
    $records = @(Get-RngRecordFiles)
    if ($saves.Count + $records.Count -eq 0) { Add-RngOpsLog ('备份（' + $what + '）：没有存档和角色记录，不用存'); return $null }
    $sig = Get-RngFileSig (@($saves) + @($records))
    $last = @(Get-RngBackups | Where-Object { $_.Tag -eq $Tag }) | Select-Object -First 1
    if ($last -and $last.Sig -eq $sig) { Add-RngOpsLog ('备份（' + $what + '）：和上一份一样，没再存（' + (Split-Path $last.Dir -Leaf) + '）'); return $last.Dir }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $dst = Join-Path $RngBackupDir ($stamp + '_' + $Tag)
    for ($n = 2; Test-Path -LiteralPath $dst; $n++) { $dst = Join-Path $RngBackupDir ($stamp + '_' + $Tag + '_' + $n) }   # 同一秒里存了两份
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    foreach ($f in $saves) {
        $to = Join-Path $dst $f.Directory.Name
        New-Item -ItemType Directory -Force -Path $to | Out-Null
        Copy-Item -LiteralPath $f.FullName -Destination $to -Force
    }
    if ($records.Count) {
        $to = Join-Path $dst '角色记录'
        New-Item -ItemType Directory -Force -Path $to | Out-Null
        foreach ($f in $records) { Copy-RngRecord $f $to }
    }
    $info = [ordered]@{ tag = $Tag; time = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'); mode = $Mode; sig = $sig }
    [System.IO.File]::WriteAllText((Join-Path $dst 'backup_info.json'), ($info | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
    Add-RngOpsLog ('备份（' + $what + '）：存档 ' + $saves.Count + ' 个、角色记录 ' + $records.Count + ' 个 → ' + (Split-Path $dst -Leaf))
    # 每种只留最近几份（恢复前的备份不会把启动前的挤掉）
    $keep = if ($Tag -eq '启动前') { $RngBackupKeep } else { 5 }
    foreach ($old in (@(Get-RngBackups | Where-Object { $_.Tag -eq $Tag }) | Select-Object -Skip $keep)) {
        Remove-Item -LiteralPath $old.Dir -Recurse -Force -ErrorAction SilentlyContinue
        Add-RngOpsLog ('删掉旧备份（每种只留最近 ' + $keep + ' 份）：' + (Split-Path $old.Dir -Leaf))
    }
    return $dst
}

# 启动前备份 + 恢复前备份 + 「存档备份」按钮存的（$ManualDir），新的在前
function Get-RngBackups([string]$ManualDir = '') {
    $list = @()
    foreach ($d in (Get-ChildItem -LiteralPath $RngBackupDir -Directory -ErrorAction SilentlyContinue)) {
        $infoFile = Join-Path $d.FullName 'backup_info.json'
        if (-not (Test-Path -LiteralPath $infoFile)) { continue }       # 没写完的
        try { $info = Get-Content -LiteralPath $infoFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
        $list += [pscustomobject]@{
            Dir = $d.FullName; Tag = [string]$info.tag; Time = [datetime]$info.time; Mode = [string]$info.mode; Sig = [string]$info.sig
            Records = @(Get-RngRecordFiles $d.FullName).Count
            Saves = @(Get-RngSavesIn $d.FullName).Count
        }
    }
    if ($ManualDir) {
        foreach ($d in (Get-ChildItem -LiteralPath $ManualDir -Directory -ErrorAction SilentlyContinue)) {
            $rc = @(Get-RngRecordFiles $d.FullName).Count
            $sv = @(Get-RngSavesIn $d.FullName).Count
            if ($sv -eq 0) { continue }
            $list += [pscustomobject]@{ Dir = $d.FullName; Tag = '存档备份'; Time = $d.LastWriteTime; Mode = ''; Sig = ''; Records = $rc; Saves = $sv }
        }
    }
    return @($list | Sort-Object Time, Dir -Descending)
}

# 恢复一份备份：先把现在的存档和记录存成「恢复前」备份（恢复错了还能换回来），再复制回去。
# 角色记录整套换成备份里的：备份之后才有的记录删掉（已经存进「恢复前」），免得和换回去的存档对不上。
# 备份里没有联机存档、也没有联机记录（加联机以前的备份）时，现在的联机存档和 联机\ 记录不动（不然联机角色的装备记录会被删光）
function Restore-RngBackup($Backup) {
    [void](Move-RngLegacyFiles)
    $pre = New-RngBackup '恢复前'
    $done = @()
    $saves = @(Get-RngSavesIn $Backup.Dir)
    foreach ($f in $saves) {
        $to = Join-Path $RngSaveRoot $f.Directory.Name
        New-Item -ItemType Directory -Force -Path $to | Out-Null
        Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $to $f.Name) -Force
        $done += ($(if ($f.Name -like '*.co2') { '联机存档 ' } else { '存档 ' }) + $f.Directory.Name)
    }
    $coop = ($saves | Where-Object { $_.Name -like '*.co2' }) -or (Test-Path -LiteralPath (Join-Path $Backup.Dir '角色记录\联机'))
    $keep = @{}
    New-Item -ItemType Directory -Force -Path $RngRecordDir | Out-Null
    foreach ($f in (Get-RngRecordFiles $Backup.Dir)) {
        Copy-RngRecord $f $RngRecordDir
        $keep[(Get-RngRecordName $f)] = $true
    }
    foreach ($f in (Get-RngRecordFiles)) {
        $name = Get-RngRecordName $f
        if ($name -like '联机\*' -and -not $coop) { continue }
        if (-not $keep.ContainsKey($name)) { Remove-Item -LiteralPath $f.FullName -Force }
    }
    $done += ('角色记录 ' + $keep.Count + ' 个')
    Add-RngOpsLog ('恢复：' + ($done -join '、') + '，来自 ' + $Backup.Dir + '（' + $Backup.Tag + ' ' + $Backup.Time.ToString('yyyy-MM-dd HH:mm:ss') + '）；' +
                   '恢复前的存档和记录存在 ' + $(if ($pre) { Split-Path $pre -Leaf } else { '（没有，原来就是空的）' }))
    return $done
}

# 引入时先整理一次（游戏开着就等下次）；启动前备份那里还会再整理一次
try { [void](Move-RngLegacyFiles) } catch { }
