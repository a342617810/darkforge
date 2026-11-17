# Dark Reforged 启动器（YAFSML 注入）
# 由图形界面调用（-Action ...）；没有交互菜单了（2026-11-02），调试时直接在命令行带 -Action：
#   powershell -NoProfile -ExecutionPolicy Bypass -File launcher.ps1 -Action help
#   ... -Action vanilla -DryRun / -NoLaunch      无敌人随机（只看配置 / 生成并写配置但不启动）
#   ... -Action rand -DryRun / -NoLaunch         敌人随机
#   ... -Action coop / coopvanilla               联机启动（Seamless Co-op；敌人随机 / 无敌人随机，dev\coop\联机计划.md）
#   ... -Action coopcode / coopimport [-Code ..] 复制联机码 / 按联机随机码重随敌人（不给 -Code 读剪贴板）
#   ... -Action coophost / coophostvanilla [-BossWorld high|low]   联机开房：没密码就生成、联机码复制到剪贴板、联机启动（敌人随机 / 无敌人随机；
#                                                  -BossWorld = 这次联机的世界，写进联机码，不给按上次玩的联机角色）
#   ... -Action coopjoin [-Code ..]               加入队友：照联机码改好密码、Seamless 设置、敌人设置和世界，要重随才重随，然后联机启动
#   ... -Action update -UpdateZip "a.zip|b.zip"   导入离线更新包（launcher\update.py；几个包用 | 隔开，自动按版本排序）
#   ... -Action checkupdate / autoupdate          在线检查更新 / 下载并应用更新包（地址在 launcher\update_source.json；结果 logs\update_check.json）
#   ... -Action vanilla / rand -BossWorld high|low   这次以「死亡以上难度」/「普通难度」的世界启动（图形界面问过玩家；不给按上次玩的角色）
#
# 输出：Write-Player 的几行（开头 §）是给玩家看的进度，图形界面启动时只显示这几行和 [错误]；别的照样输出，完整的在 launcher\logs\。
#
# 每次启动前都重新生成两个覆盖包（YAFSML 按 [mod] 的顺序加载，后面的覆盖前面的）：
#   out\reroll    reroll\reroll.py：在原版（randomizer\diste\Vanilla）或随机器输出的 regulation 上改
#                 （敌人血量分档、Boss 奖励、开局物品、局内难度、训练木桩……），只写到这里，不改原文件
#   out\scripts   reroll\scripts.py：赐福菜单、公共事件、玩家动作脚本等，在前面各包最后生效的那份上合并
# 敌人随机时前面再加随机器输出（randomizer）和按新位置修补过的地图（out\reroll_maps）。
#
# 游戏路径不写死：优先读 launcher\game_path.txt，其次自动检测
#（Steam 库 / 整合包附近 / 常见目录），仍找不到就弹选择框。

[CmdletBinding()]
param(
    [ValidateSet('list', 'vanilla', 'rand', 'randomizer', 'help', 'setgame', 'diag', 'watch', 'oncereset', 'randenemy', 'randhi', 'carryrand',
                 'coop', 'coopvanilla', 'coopcode', 'coopimport', 'coophost', 'coophostvanilla', 'coopjoin', 'update', 'checkupdate', 'autoupdate')]
    [string]$Action = 'help',
    [int]$GamePid = 0,
    [string]$GamePath = '',
    [string]$FromPack = '',
    [string]$Code = '',
    [string]$UpdateZip = '',
    [ValidateSet('', 'high', 'low')]
    [string]$BossWorld = '',
    [switch]$DryRun,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
} catch { }

$LauncherDir = $PSScriptRoot
$Paly        = Split-Path -Parent $LauncherDir
$YafDir      = Join-Path $Paly 'yafsml'
$YafExe      = Join-Path $YafDir 'YAFSML.exe'
$YafIni      = Join-Path $YafDir 'YAFSML.ini'
$TplPath     = Join-Path $LauncherDir 'YAFSML.ini.tpl'
$RandomDir   = Join-Path $Paly 'randomizer'
$RandomExe   = Join-Path $RandomDir 'EldenRingRandomizer.exe'
$VanillaTool = Join-Path $LauncherDir 'reroll\vanilla.py'   # 原版文件从哪来：装了随机器用它带的，没装从玩家游戏取（Get-VanillaSource）
$RandomLog   = Join-Path $YafDir 'log\YAFSML.log'
$GamePathFile = Join-Path $LauncherDir 'game_path.txt'
$RerollTool   = Join-Path $LauncherDir 'reroll\reroll.py'
$ScriptsTool  = Join-Path $LauncherDir 'reroll\scripts.py'
# 重随包、修补过的地图、游戏脚本覆盖包按「世界」各存一份（敌人随机 / 无敌人随机、普通 / 死亡以上、联机：后缀 _van _hi _coop），
# 换世界不用重做（用户 2026-11-05「各部分分别缓存吧 只重做需要的部分」）。这里先指向上次启动用的那份（状态显示、诊断包读它），
# Invoke-Launch 再按这次的世界换。用英文路径，免得 YAFSML 读 ini 时中文路径出问题
$WorldFile = Join-Path $Paly 'out\current_world.txt'
function Set-WorldPacks([string]$Suffix) {
    $script:WorldSuffix = $Suffix
    $script:RerollPack = Join-Path $Paly ('out\reroll' + $Suffix)
    $script:RerollMapsPack = Join-Path $Paly ('out\reroll_maps' + $Suffix)   # 敌人随机时：按新位置修补过的地图（覆盖随机器输出）
    $script:ScriptsPack = Join-Path $Paly ('out\scripts' + $Suffix)          # 游戏脚本覆盖包（最后加载）
}
$lastWorld = ''
try { $lastWorld = ([System.IO.File]::ReadAllText($WorldFile)).Trim() } catch { }
Set-WorldPacks $(if ($lastWorld -match '^[a-z_]*$') { $lastWorld } else { '' })
$MenuTool     = Join-Path $LauncherDir 'reroll\menu.py'
$MenuPack     = Join-Path $Paly 'out\menu'            # 菜单覆盖包：自制状态图标、稀有度边框图标（从本机游戏的原版菜单文件合成）
$script:CacheGameRoot = $null

# ---------------------------------------------------------------- 输出小工具
function Write-Head([string]$Text) {
    Write-Host ''
    Write-Host ('=== ' + $Text + ' ===') -ForegroundColor Cyan
}
function Write-Ok([string]$Text)   { Write-Host ('  [OK] '   + $Text) -ForegroundColor Green }
function Write-Warn([string]$Text) { Write-Host ('  [提示] ' + $Text) -ForegroundColor Yellow }
function Write-Err([string]$Text)  { Write-Host ('  [错误] ' + $Text) -ForegroundColor Red }
# 给玩家看的进度（用户 2026-11-05「只需要让玩家知道游戏正在正常加载就行 后台输出可以保留」）：图形界面启动 / 重随敌人时只显示 § 开头的行和 [错误]
function Write-Player([string]$Text)     { Write-Host ('§ ' + $Text) -ForegroundColor Cyan }
function Write-PlayerWarn([string]$Text) { Write-Host ('§ [提示] ' + $Text) -ForegroundColor Yellow }
# 进度条（用户 2026-11-05）：「§% 百分比」，图形界面画在上一行给玩家看的进度后面（重随自己也打，reroll\progress.py）
function Write-Progress-Bar([int]$Pct) { Write-Host ('§% ' + $Pct) -ForegroundColor DarkGray }
# ---------------------------------------------------------------- 游戏路径
# 游戏路径不写死：优先读 launcher\game_path.txt（用户选择/自动检测后保存），
# 其次自动检测（Steam 库 / 整合包附近 / 常见目录），仍找不到就弹选择框。
function Test-NormalizeGameRoot([string]$Path) {
    # 全用 .NET 判断：PowerShell 5.1 的 Join-Path / Split-Path 遇到不存在的盘符（如旧 game_path.txt 里的 F:）会直接抛异常
    if (-not $Path) { return $null }
    $p = $Path.Trim()
    $p = $p.Trim('"').Trim()
    if (-not $p) { return $null }
    try {
        $p = [System.IO.Path]::GetFullPath($p).TrimEnd('\')
        if ([System.IO.Path]::GetFileName($p) -ieq 'eldenring.exe') {
            if (-not [System.IO.File]::Exists($p)) { return $null }
            $p = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetDirectoryName($p))
        }
        if ([System.IO.File]::Exists([System.IO.Path]::Combine($p, 'eldenring.exe'))) { return [System.IO.Path]::GetDirectoryName($p) }
        if ([System.IO.File]::Exists([System.IO.Path]::Combine($p, 'Game\eldenring.exe'))) { return $p }
    } catch { }
    return $null
}

function Get-SavedGameRoot {
    if (-not (Test-Path -LiteralPath $GamePathFile)) { return $null }
    $line = Get-Content -LiteralPath $GamePathFile -TotalCount 1 -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $line) { return $null }
    return (Test-NormalizeGameRoot ([string]$line))
}

function Save-GameRoot([string]$Root) {
    [System.IO.File]::WriteAllText($GamePathFile, $Root + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
    $script:CacheGameRoot = $Root
    Write-Ok ('已保存游戏路径：' + $Root)
}

# 路径去重，不分大小写，留第一次出现的写法。注册表里的 SteamPath 是小写加正斜杠（c:/program files (x86)/steam），
# 游戏库列表和按盘扫到的是 C:\Program Files (x86)\Steam：以前用 Select-Object -Unique（分大小写），同一个游戏算成两个候选，
# 「只有一个候选才自动记住」就不成立，游戏装在 C 盘 Steam 默认位置的玩家每次都要手选（2026-11-16 查出来）
function Get-UniquePaths($Paths) {
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $out = New-Object System.Collections.Generic.List[string]
    foreach ($p in @($Paths)) {
        if (-not $p) { continue }
        $k = ([string]$p).TrimEnd('\')
        if ($seen.Add($k)) { $out.Add($k) }
    }
    return @($out)
}

function Find-SteamGameRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    $steamPath = $null
    try { $steamPath = (Get-ItemProperty -Path 'HKCU:\Software\Valve\Steam' -Name SteamPath -ErrorAction Stop).SteamPath } catch { }
    if (-not $steamPath) {
        try { $steamPath = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam' -Name InstallPath -ErrorAction Stop).InstallPath } catch { }
    }
    $libs = New-Object System.Collections.Generic.List[string]
    if ($steamPath) {
        $vdf = Join-Path $steamPath 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $vdf) {
            try {
                $txt = Get-Content -LiteralPath $vdf -Raw -Encoding UTF8 -ErrorAction Stop
                foreach ($m in [regex]::Matches($txt, '"path"\s+"([^"]+)"')) {
                    $libs.Add(($m.Groups[1].Value -replace '\\\\', '\'))
                }
            } catch { }
        }
        $libs.Add($steamPath)                    # 放在库列表后面：库列表里的写法大小写正常，去重时留它
    }
    foreach ($l in $libs) {
        foreach ($sub in @('steamapps\common\ELDEN RING', 'steamapps\common\ELDEN RING\Game')) {
            $r = Test-NormalizeGameRoot ([System.IO.Path]::Combine($l, $sub))
            if ($r) { $roots.Add($r) }
        }
    }
    return @(Get-UniquePaths $roots)
}

function Find-NearbyGameRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    # 整合包直接解压在游戏文件夹里（Game 或 ELDEN RING 那一层，2026-11-16 有两个玩家这样放）：整合包目录自己和往上几层就是
    $up = $Paly
    for ($i = 0; $i -lt 3 -and $up; $i++) {
        $r = Test-NormalizeGameRoot $up
        if ($r) { $roots.Add($r) }
        $up = [System.IO.Path]::GetDirectoryName($up)
    }
    $dir = $LauncherDir
    for ($depth = 0; $depth -lt 4; $depth++) {
        if (-not $dir) { break }
        foreach ($pat in @('ELDEN RING*', '*ELDEN*', '*elden*', '*Ring*')) {
            $dirs = Get-ChildItem -LiteralPath $dir -Directory -Filter $pat -ErrorAction SilentlyContinue | Select-Object -First 40
            foreach ($d in $dirs) {
                $r = Test-NormalizeGameRoot $d.FullName
                if ($r) { $roots.Add($r) }
                $subs = Get-ChildItem -LiteralPath $d.FullName -Directory -ErrorAction SilentlyContinue | Select-Object -First 40
                foreach ($d2 in $subs) {
                    $r2 = Test-NormalizeGameRoot $d2.FullName
                    if ($r2) { $roots.Add($r2) }
                }
            }
        }
        $dir = Split-Path $dir -Parent
    }
    return @(Get-UniquePaths $roots)
}

# 要扫的盘：本机硬盘、移动硬盘、网络盘（光驱这类没放盘的跳过）
function Get-FixedDriveRoots {
    $out = New-Object System.Collections.Generic.List[string]
    try {
        foreach ($d in [System.IO.DriveInfo]::GetDrives()) {
            if ($d.DriveType -notin @([System.IO.DriveType]::Fixed, [System.IO.DriveType]::Removable, [System.IO.DriveType]::Network)) { continue }
            try { if ($d.IsReady) { $out.Add($d.RootDirectory.FullName) } } catch { }
        }
    } catch { }
    return @($out)
}

# 每个盘里 Steam 正版的默认位置（用户 2026-11-16「自动扫描所有盘下 steam 正版默认的路径」）：Steam 装在默认位置、在别的盘建的游戏库
# （Steam 默认叫 SteamLibrary），再加上盘根下每个文件夹当游戏库看一遍（X:\随便什么名字\steamapps\common\ELDEN RING，
# 比如 E:\SteamGames）和 X:\随便什么名字\Steam\…。只看固定的几层，不整盘搜
function Find-CommonGameRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    $rels = @(
        'Program Files (x86)\Steam\steamapps\common\ELDEN RING',
        'Program Files\Steam\steamapps\common\ELDEN RING',
        'SteamLibrary\steamapps\common\ELDEN RING',
        'Steam\steamapps\common\ELDEN RING',
        'Steam Library\steamapps\common\ELDEN RING',
        'SteamLibrary2\steamapps\common\ELDEN RING',
        'SteamGames\steamapps\common\ELDEN RING',
        'Games\Steam\steamapps\common\ELDEN RING',
        'Games\SteamLibrary\steamapps\common\ELDEN RING',
        'Games\ELDEN RING',
        'Game\ELDEN RING'
    )
    $skip = @('Windows', 'System Volume Information', '$Recycle.Bin', '$WinREAgent', 'Recovery', 'PerfLogs', 'ProgramData')
    foreach ($d in (Get-FixedDriveRoots)) {
        foreach ($rel in $rels) {
            $r = Test-NormalizeGameRoot ([System.IO.Path]::Combine($d, $rel))
            if ($r) { $roots.Add($r) }
        }
        $tops = @()
        try { $tops = @([System.IO.Directory]::GetDirectories($d) | Select-Object -First 300) } catch { }
        foreach ($t in $tops) {
            if ($skip -contains [System.IO.Path]::GetFileName($t)) { continue }
            foreach ($sub in @('steamapps\common\ELDEN RING', 'Steam\steamapps\common\ELDEN RING')) {
                $r = Test-NormalizeGameRoot ([System.IO.Path]::Combine($t, $sub))
                if ($r) { $roots.Add($r) }
            }
        }
    }
    return @(Get-UniquePaths $roots)
}

function Get-GameCandidates {
    return @(Get-UniquePaths (@(Find-SteamGameRoots) + @(Find-NearbyGameRoots) + @(Find-CommonGameRoots)))
}

# 自动检测到的游戏里挑一个：只有一个就是它；有好几个时，整合包解压在其中一个里面的用那个，否则 Steam 游戏库里登记的只有一个就用它；
# 还分不出来返回 $null（让玩家在「游戏路径」里自己选）
function Select-GameCandidate {
    $cands = @(Get-GameCandidates)
    if ($cands.Count -le 1) { return $(if ($cands.Count) { $cands[0] } else { $null }) }
    $inside = @($cands | Where-Object { ($Paly.TrimEnd('\') + '\').StartsWith($_ + '\', [System.StringComparison]::OrdinalIgnoreCase) })
    if ($inside.Count -eq 1) { return $inside[0] }
    $steam = @(Find-SteamGameRoots)
    if ($steam.Count -eq 1) { return $steam[0] }
    return $null
}

function Resolve-GameRoot([switch]$Refresh) {
    if (-not $Refresh -and $script:CacheGameRoot) { return $script:CacheGameRoot }
    $saved = Get-SavedGameRoot
    if ($saved) { $script:CacheGameRoot = $saved; return $saved }
    $pick = Select-GameCandidate
    if ($pick) {
        $script:CacheGameRoot = $pick
        try {
            [System.IO.File]::WriteAllText($GamePathFile, $pick + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
        } catch { }
        Write-Ok ('自动检测到游戏路径并已记住：' + $pick)
        return $pick
    }
    return $null
}

function Pick-FolderDialog([string]$Title) {
    try { Add-Type -AssemblyName System.Windows.Forms | Out-Null } catch { return $null }
    try {
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = $Title
        $dlg.ShowNewFolderButton = $false
        $cur = Resolve-GameRoot
        if ($cur) { $dlg.SelectedPath = $cur }
        if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $dlg.SelectedPath }
    } catch { }
    return $null
}

function Pick-ExeDialog([string]$Title) {
    try { Add-Type -AssemblyName System.Windows.Forms | Out-Null } catch { return $null }
    try {
        $dlg = New-Object System.Windows.Forms.OpenFileDialog
        $dlg.Title = $Title
        $dlg.Filter = 'eldenring.exe|eldenring.exe|所有文件|*.*'
        $cur = Resolve-GameRoot
        if ($cur) { $dlg.InitialDirectory = (Join-Path $cur 'Game') }
        if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $dlg.FileName }
    } catch { }
    return $null
}

function Set-GameRootInteractive {
    while ($true) {
        $cur = Get-SavedGameRoot
        $cands = @(Get-GameCandidates)
        Clear-Host
        Write-Host '==============================================================' -ForegroundColor Cyan
        Write-Host '   设置 Elden Ring 游戏路径（只需选一次，会记住）' -ForegroundColor Cyan
        Write-Host '==============================================================' -ForegroundColor Cyan
        if ($cur) {
            Write-Host ('  当前：' + $cur) -ForegroundColor Green
        } else {
            $resolved = Resolve-GameRoot
            if ($resolved) { Write-Host ('  当前：' + $resolved) -ForegroundColor Green }
            else { Write-Host '  当前：未设置' -ForegroundColor Yellow }
        }
        Write-Host ''
        if ($cands.Count -gt 0) {
            Write-Host '  自动检测到的候选：'
            for ($i = 0; $i -lt $cands.Count; $i++) {
                Write-Host ('   [{0}] {1}' -f ($i + 1), $cands[$i]) -ForegroundColor White
            }
        } else {
            Write-Host '  自动检测：没有找到（可手动浏览）' -ForegroundColor DarkGray
        }
        Write-Host ''
        Write-Host '   输入序号 = 使用该候选'
        Write-Host '   [F] 浏览文件夹（选游戏的 Game 文件夹，例如 C:\Program Files (x86)\Steam\steamapps\common\ELDEN RING\Game）'
        Write-Host '   [E] 直接选择 eldenring.exe'
        Write-Host '   [A] 重新自动检测'
        Write-Host '   [Q] 取消'
        Write-Host '=============================================================='
        $sel = Read-Host '请选择'
        if ($null -eq $sel) { return $false }
        $sel = ([string]$sel).Trim()
        if ($sel -eq '') { continue }
        if ($sel -match '^[qQ]$') { return $false }
        if ($sel -match '^[aA]$') { $script:CacheGameRoot = $null; continue }
        if ($sel -match '^[fF]$') {
            $picked = Pick-FolderDialog ('请选中游戏的 Game 文件夹（里面有 eldenring.exe）' + "`r`n" + '例如 …\steamapps\common\ELDEN RING\Game')
            if (-not $picked) { continue }
            $root = Test-NormalizeGameRoot $picked
            if ($root) { Save-GameRoot $root; return $true }
            Write-Err ('这个目录里没找到 Game\eldenring.exe：' + $picked)
            [void](Read-Host '按回车重试')
            continue
        }
        if ($sel -match '^[eE]$') {
            $picked = Pick-ExeDialog '选择 eldenring.exe'
            if (-not $picked) { continue }
            $root = Test-NormalizeGameRoot $picked
            if ($root) { Save-GameRoot $root; return $true }
            Write-Err ('这个 exe 的位置不像 Elden Ring 安装：' + $picked)
            [void](Read-Host '按回车重试')
            continue
        }
        $n = 0
        if ([int]::TryParse($sel, [ref]$n) -and $n -ge 1 -and $n -le $cands.Count) {
            Save-GameRoot $cands[$n - 1]
            return $true
        }
        $root = Test-NormalizeGameRoot $sel
        if ($root) { Save-GameRoot $root; return $true }
        Write-Err ('无法识别（可输入序号、[F]/[E]/[A]/[Q]，或粘贴路径）：' + $sel)
        [void](Read-Host '按回车重试')
    }
    return $false
}


# ---------------------------------------------------------------- 随机器输出
function Get-LatestRandom {
    $logDir = Join-Path $RandomDir 'spoiler_logs'
    if (-not (Test-Path -LiteralPath $logDir)) { return $null }
    $log = Get-ChildItem -LiteralPath $logDir -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $log) { return $null }
    $head = Get-Content -LiteralPath $log.FullName -TotalCount 40 -Encoding UTF8 -ErrorAction SilentlyContinue
    $optLine = $head | Where-Object { $_ -match '^Options and seed:' } | Select-Object -First 1
    # 以前的版本让随机器合并可玩包（日志开头有 Checking other mod directory），那样的输出带着别的包的参数，要重新随机化
    $modLine = $head | Where-Object { $_ -match '^Checking other mod directory \S' } | Select-Object -First 1
    return [pscustomobject]@{
        Log      = $log.FullName
        Time     = $log.LastWriteTime
        HasEnemy = [bool]($optLine -and ($optLine -match '(^|\s)enemy(\s|$)'))
        HasItem  = [bool]($optLine -and ($optLine -match '(^|\s)item(\s|$)'))
        Merged   = [bool]$modLine
    }
}

# ---------------------------------------------------------------- 存档：Dark Reforged 专用 ER0000.rng（YAFSML 的 replace_save_filename）
$SaveRootDir = Join-Path $env:APPDATA 'EldenRing'
. (Join-Path $LauncherDir 'backup.ps1')
. (Join-Path $LauncherDir 'randomize.ps1')
. (Join-Path $LauncherDir 'ui.ps1')         # 弹窗 Show-DrDialog（和图形界面同样的风格；要弹的时候才加载界面控件）
. (Join-Path $LauncherDir 'coopcode.ps1')   # 联机码压缩（DR3 ↔ DR4z，和图形界面共用）
. (Join-Path $LauncherDir 'usermods.ps1')   # 玩家自己加的：整合包根目录 mods\ 文件夹、YAFSML自定义.ini（用户 2026-11-16）

# 一键重随敌人（randomize.ps1）：用上次 / 默认的随机器设置、换新种子随机化一次，不启动游戏
function Invoke-RandEnemyAction {
    Write-Head '一键重随敌人'
    $rs = Get-RandomizerStatus
    if (-not $rs.Ok) { Write-Err $rs.Msg; return $false }
    if (-not $rs.Tested) { Write-Warn (Get-RandomizerUntestedMsg) }
    if (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) { Write-Err '游戏还在运行，先退出游戏再重随敌人。'; return $false }
    $erRoot = Resolve-GameRoot
    if (-not $erRoot) { Write-Err '还没有设置游戏路径（随机器要读游戏文件）。先点「游戏路径」选一下。'; return $false }
    if ($DryRun) { $o = Get-RandomizeOptions; Write-Host ('  ' + $o.From + '：' + $o.Options); return $true }
    Write-Player '正在随机化敌人（约 1~5 分钟）：随机器窗口会自动操作、完成后自动关闭，这期间不要点它，也不要关掉它……'
    $r = Invoke-RandomizeEnemies (Join-Path $erRoot 'Game\eldenring.exe')
    if ($r.Ok) {
        Write-Ok $r.Msg
        Write-Player '敌人随机化完成。'
        # 高难度世界（Boss 模组：整合了改版的 Boss 在「死亡」以上留在原位；没开 Boss 模组时什么都不做）
        if (@(Get-BossFixedIds).Count) { Write-Player '正在生成死亡以上难度的世界（随机器再跑一遍，约 1~5 分钟）……' }
        $h = Invoke-RandomizeHiWorld (Join-Path $erRoot 'Game\eldenring.exe')
        if ($h.Ok -and $h.Msg) { Write-Ok $h.Msg; Write-Player '死亡以上难度的世界也生成好了。' }
        elseif (-not $h.Ok) { Write-PlayerWarn ('死亡以上难度的世界没生成成功（正常的敌人随机不受影响；死亡以上难度时部分追忆 Boss 不在原位）：' + $h.Msg) }
        Write-Host '  现在点「一键启动 · 敌人随机」就能玩新的敌人配置。'
    } else { Write-Err ('一键重随敌人失败：' + $r.Msg) }
    return [bool]$r.Ok
}

# 只补做高难度世界（Boss 模组，randomize.ps1 的 Invoke-RandomizeHiWorld）：按现在这次敌人随机的种子再跑一遍随机器，平常的世界不动。
# 一键重随敌人会自动做；这里给「做的时候失败了 / 之后才开了新的 Boss 模组 / 自己打开随机器随机化的」补一次
function Invoke-RandHiAction {
    Write-Head '补做高难度世界'
    $rs = Get-RandomizerStatus
    if (-not $rs.Ok) { Write-Err $rs.Msg; return $false }
    if (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) { Write-Err '游戏还在运行，先退出游戏。'; return $false }
    $erRoot = Resolve-GameRoot
    if (-not $erRoot) { Write-Err '还没有设置游戏路径。先点「游戏路径」选一下。'; return $false }
    if (-not @(Get-BossFixedIds).Count) { Write-Ok '没有开着的 Boss 模组，不用做高难度世界。'; return $true }
    if ($DryRun) { Write-Host '  [-DryRun] 不跑随机器。'; return $true }
    Write-Player '正在生成死亡以上难度的世界（约 1~5 分钟）：随机器窗口会自动操作、完成后自动关闭，这期间不要点它，也不要关掉它……'
    $h = Invoke-RandomizeHiWorld (Join-Path $erRoot 'Game\eldenring.exe')
    if ($h.Ok) { Write-Ok $h.Msg; Write-Player '死亡以上难度的世界生成好了。' } else { Write-Err ('死亡以上难度的世界没生成成功：' + $h.Msg) }
    return [bool]$h.Ok
}

# 把一个文件夹里随机器生成的东西复制到另一个文件夹。出错返回原因，都成功返回 ''
function Copy-RandItems([string]$Src, [string]$Dst, [string[]]$Items) {
    foreach ($n in $Items) {
        $s = Join-Path $Src $n
        if (-not (Test-Path -LiteralPath $s)) { continue }
        if ((Get-Item -LiteralPath $s).PSIsContainer) {
            $mb = [Math]::Round((Get-ChildItem -LiteralPath $s -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB)
            Write-Host ('  复制 ' + $n + '（' + $mb + ' MB）...')
            # robocopy：多线程、保留修改时间（沿用后按 spoiler 日志的时间核对）；返回 8 以上才是失败
            & robocopy.exe $s (Join-Path $Dst $n) /E /MT:8 /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
            if ($LASTEXITCODE -ge 8) { return ('复制 ' + $n + ' 失败（robocopy 返回 ' + $LASTEXITCODE + '）') }
        } else {
            Copy-Item -LiteralPath $s -Destination $Dst -Force
        }
    }
    return ''
}

# 死亡以上难度的世界（randomizer_hi，本机生成、不打进 zip）跟着普通世界一起沿用：不带的话更新后死亡以上难度只能用普通世界，Boss 不在原位
#（2026-11-08 测试者诊断包）。旧整合包里没有、或者不是跟着这次随机化做的就不带，启动时图形界面会问要不要生成。这里失败不影响已经沿用好的普通世界
function Copy-OldRandHiWorld([string]$Pack) {
    $src = Join-Path $Pack 'randomizer_hi'
    if (-not (Get-RandHiWorld @() $src (Join-Path $Pack 'randomizer'))) { Write-Host '  旧版本没有配套的死亡以上难度世界，这部分不用沿用。'; return }
    try {
        Remove-RandHiDir
        [void](New-Item -ItemType Directory -Force -Path $RandomHiDir)
        $err = Copy-RandItems $src $RandomHiDir ($RandHiItems + 'spoiler_logs')
        if (-not $err) { $err = Copy-RandItems $src $RandomHiDir @($RandHiSource) }      # 记录文件最后复制：复制到一半中断时不会被当成完整的
        if ($err) { throw $err }
        if (-not (Get-RandHiWorld @())) { throw '复制完了却读不到这个世界' }
        Write-Ok '死亡以上难度的世界也沿用过来了。'
    } catch {
        Write-Warn ('死亡以上难度的世界没沿用成（普通世界不受影响，选死亡以上难度启动时会问要不要重新生成）：' + $_.Exception.Message)
        try { Remove-RandHiDir } catch { }
    }
}

# 沿用旧版本的敌人随机结果（randomize.ps1 末尾「更新后沿用」）：把旧整合包 randomizer\ 里随机器生成的东西复制过来，旧文件夹不动。
# $From 不给就用找到的最新一份；这个整合包已经有能用的随机结果就不覆盖。返回成功与否（图形界面靠退出码决定接不接着启动）
function Invoke-CarryRandom([string]$From) {
    Write-Head '沿用旧版本的敌人随机结果'
    $rs = Get-RandomizerStatus
    if (-not $rs.Ok) { Write-Err $rs.Msg; return $false }
    if (-not (Test-NeedOldRandom)) {
        $cur = Get-RandomInfo $RandomDir
        Write-Ok ('这个整合包已经有敌人随机结果了（随机化于 ' + $cur.Time.ToString('yyyy-MM-dd HH:mm') + '），不用沿用。')
        return $true
    }
    if ($From) {
        # 指定了文件夹（图形界面里自动找到的，或者玩家自己选的）：直接看那个文件夹，不用在自动找的范围里
        $pack = Resolve-PackDir $From
        if ($pack -ieq [System.IO.Path]::GetFullPath($Paly).TrimEnd('\')) { Write-Err ('选的是现在这个整合包自己：' + $pack); return $false }
        $c = Get-OldRandom $pack
        if ($c -is [string]) { Write-Err ('不能沿用 ' + $pack + '：' + $c); return $false }
    } else {
        $c = @(Find-OldRandoms) | Select-Object -First 1
        if (-not $c) { Write-Err '没找到能沿用的旧版本随机结果（记下的整合包、旁边的文件夹、桌面 / 下载 / 文档、游戏目录、各盘根目录往下两层里都没有）'; return $false }
    }
    $src = Join-Path $c.Pack 'randomizer'
    Write-Host ('  来源：' + $c.Pack + '（整合包 ' + $c.Version + '，随机化于 ' + $c.Time.ToString('yyyy-MM-dd HH:mm:ss') + $(if ($c.Seed) { '，种子 ' + $c.Seed } else { '' }) + '）')
    # 先删掉这里残缺的 / 合并别的包做的结果（spoiler_logs 先删）
    foreach ($n in @('spoiler_logs') + $RandOutputItems) {
        $t = Join-Path $RandomDir $n
        if (Test-Path -LiteralPath $t) { Remove-Item -LiteralPath $t -Recurse -Force }
    }
    $t0 = Get-Date
    $err = Copy-RandItems $src $RandomDir $RandOutputItems
    if ($err) { Write-Err $err; return $false }
    $now = Get-RandomInfo $RandomDir
    if (-not $now -or $now.Time -ne $c.Time) { Write-Err '复制完了却读不到随机结果（spoiler 日志或 regulation.bin 不对），这次没沿用成。'; return $false }
    Write-Ok ('已沿用旧版本的敌人随机结果（用时 ' + [int]((Get-Date) - $t0).TotalSeconds + ' 秒）：敌人和之前一样。')
    Copy-OldRandHiWorld $c.Pack
    return $true
}

# 启动游戏前自动备份存档 + 角色记录（backup.ps1）；图形界面「恢复存档」默认恢复最近一份
function Invoke-LaunchBackup([string]$Mode) {
    try {
        $n = Move-RngLegacyFiles
        if ($n) { Write-Host ('  整理存档文件夹：' + $n + ' 项搬进 ' + $RngDataDir) }
    } catch {
        Write-Warn ('整理存档文件夹失败（下次启动再试）：' + $_.Exception.Message)
    }
    try {
        $d = New-RngBackup '启动前' $Mode
        if ($d) { Write-Host ('  启动前备份：' + $d) }
    } catch {
        Write-Warn ('启动前备份失败（不影响游戏，但出问题时没法恢复到这次启动前）：' + $_.Exception.Message)
    }
}

# ---------------------------------------------------------------- 生成 ini
# 用户自己加的 DLL mod：整合包根目录的 dll\ 文件夹，每次生成配置时自动扫描（所有启动方式都加载）。
#   dll\xxx.dll           直接放
#   dll\某个mod\xxx.dll    mod 带配置文件 / 资源时整个文件夹放进来（只看这一层的 .dll）
#   文件名或文件夹名以 _ 开头 = 停用；按路径字母顺序加载
#   Seamless Co-op（ersc.dll）不在这里加载：只有联机启动才加载（见「联机」一节，Join-DllLines 放最后）
$UserDllDir = Join-Path $Paly 'dll'
function Get-UserDllLines {
    if (-not (Test-Path -LiteralPath $UserDllDir)) { return '' }
    $files = @(Get-ChildItem -LiteralPath $UserDllDir -Filter '*.dll' -File -ErrorAction SilentlyContinue)
    foreach ($d in (Get-ChildItem -LiteralPath $UserDllDir -Directory -ErrorAction SilentlyContinue)) {
        if ($d.Name.StartsWith('_')) { continue }
        $files += @(Get-ChildItem -LiteralPath $d.FullName -Filter '*.dll' -File -ErrorAction SilentlyContinue)
    }
    $lines = @()
    $used = @{}
    foreach ($f in ($files | Where-Object { -not $_.Name.StartsWith('_') } | Sort-Object FullName)) {
        if ($f.Name -ieq 'ersc.dll') { continue }
        if (-not (Test-UserDllSafe $f)) { continue }
        $rel = $f.FullName.Substring($UserDllDir.Length).TrimStart('\')
        $key = 'user_' + ($f.BaseName -replace '[^A-Za-z0-9_]', '_')
        $k = $key; $n = 2
        while ($used.ContainsKey($k)) { $k = $key + '_' + $n; $n++ }
        $used[$k] = $true
        $lines += ($k + '=..\dll\' + $rel)
    }
    if ($lines.Count -eq 0) { return '' }
    return ("; 用户 DLL（整合包根目录 dll\ 文件夹，自动扫描）`r`n" + ($lines -join "`r`n"))
}

# 会改存档文件名的 DLL：不处理的话会读写原版（.sl2）或法魂（.cnv）的存档
#   Erd Tools：把 ini 里的 save_extension 写进游戏内存（缺省 sl2；没有 ini 时扩展名会变成空的）→ 保证同目录有 ini，
#             单机为 rng、联机为 co2（$script:ErdSaveExt；和 Seamless Co-op 一致，YAFSML 再换成 .rngcoop，免得联机读写单机存档）
#   独立存档类 dll（alt_saves）：存档已由 YAFSML 的 replace_save_filename 隔离，再叠一个会改成别的文件 → 不加载
function Test-UserDllSafe($File) {
    $n = $File.Name.ToLowerInvariant()
    if ($n -like '*alt_saves*' -or $n -like '*altsaves*') {
        Write-Warn ('不加载 ' + $File.Name + '：它会另外改存档文件名，和整合包的独立存档（ER0000.rng）冲突。')
        return $false
    }
    if ($n -like 'souls_vision*.dll') { return (Test-EnemyInfoMod) }
    if ($n -like 'erdtools*.dll' -or $n -like 'erd_tools*.dll') {
        $ini = Join-Path $File.DirectoryName 'erd_tools.ini'
        $ext = $script:ErdSaveExt
        try {
            if (-not (Test-Path -LiteralPath $ini)) {
                [System.IO.File]::WriteAllText($ini, "[SAVE]`r`n; Dark Reforged：单机 rng、联机 co2，启动器每次启动按启动方式改（和 YAFSML 的 replace_save_filename 一致）`r`nsave_extension = $ext`r`n", (New-Object System.Text.UTF8Encoding($true)))
                Write-Warn ('Erd Tools 缺少 erd_tools.ini，已新建一个（只设了存档扩展名 ' + $ext + '，其他用默认）：' + $ini)
                return $true
            }
            $txt = [System.IO.File]::ReadAllText($ini)
            $m = [regex]::Match($txt, '(?im)^[ \t]*save_extension[ \t]*=[ \t]*([^\r\n;]*)')
            $cur = if ($m.Success) { $m.Groups[1].Value.Trim() } else { '' }
            if ($cur -ieq $ext) { return $true }
            if ($DryRun) { Write-Host ('  [-DryRun] Erd Tools 的存档扩展名现在是「' + $cur + '」，真的启动时会改成 ' + $ext); return $true }
            $flip = $cur -in @('rng', 'co2')    # 单机 / 联机之间切换：平常事，不备份
            if (-not $flip) { Copy-Item -LiteralPath $ini -Destination ($ini + '.bak_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) -Force }
            if ($m.Success) {
                $txt = $txt.Substring(0, $m.Groups[1].Index) + $ext + $txt.Substring($m.Groups[1].Index + $m.Groups[1].Length)
            } else {
                $txt = $txt.TrimEnd() + "`r`n`r`n[SAVE]`r`nsave_extension = $ext`r`n"
            }
            [System.IO.File]::WriteAllText($ini, $txt, (New-Object System.Text.UTF8Encoding($true)))
            if ($flip) { Write-Host ('  Erd Tools 的存档扩展名换成 ' + $ext + $(if ($ext -eq 'co2') { '（联机）' } else { '（单机）' })) }
            else { Write-Warn ('Erd Tools 的存档扩展名不是 ' + $ext + '（会读写别的存档），已改成 ' + $ext + '（原 ini 已备份）：' + $ini) }
            return $true
        } catch {
            Write-Err ('检查 Erd Tools 配置失败，这次不加载它：' + $_.Exception.Message)
            return $false
        }
    }
    return $true
}

# 敌人信息 mod（dll\souls_vision.dll：敌人头上的血条、状态条）在有的双显卡电脑（核显 + 独显，笔记本常见）上会让游戏读档时崩溃：
# 它启用悬浮层时自己建一个 DX12 设备，游戏的显卡设备随即丢失，读档时游戏锁显存缓冲区拿到空地址（2026-11-01 玩家 RTX 5070 笔记本 + Radeon 610M 核显，
# 两次诊断都是它启用后 1~2 秒设备丢失，关掉就好了）。不是每台双显卡电脑都会。以前检测到双显卡时让玩家自己选（用户 2026-11-01），
# 2026-11-16 改成不问、默认加载（用户「只是说明可能导致游戏无法启动并给出关闭的路径 不需要让玩家一开始就选是否加载」）：
# 第一次打开启动器时说明一次（gui.ps1 Show-EnemyInfoFirst），开关在「工具与设置」→「游戏」，记在 launcher\reroll\state\enemy_info_mod.txt（on / off）；
# 双显卡加载着它崩溃了，崩溃看守会问要不要改成不加载。给玩家看的文字一律叫「敌人信息 mod」，不用 mod 原名（用户 2026-11-01）。
# 显卡列表 Get-GpuNames 在 ui.ps1（图形界面第一次打开时也要问，用户 2026-11-16）
$EnemyInfoChoice = Join-Path $LauncherDir 'reroll\state\enemy_info_mod.txt'

# 玩家的选择：on / off；还没选返回 $null
function Get-EnemyInfoChoice {
    try {
        $v = ([string](Get-Content -LiteralPath $EnemyInfoChoice -TotalCount 1 -ErrorAction Stop)).Trim()
        if ($v -in @('on', 'off')) { return $v }
    } catch { }
    return $null
}

function Set-EnemyInfoChoice([string]$Value) {
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $EnemyInfoChoice -Parent) | Out-Null
        [System.IO.File]::WriteAllText($EnemyInfoChoice, ($Value + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

# 置顶的是 / 否对话框（ui.ps1 的 Show-DrDialog，不给父窗口就置顶：启动器在隐藏窗口里跑，不置顶会被图形界面挡住）；
# $DefaultNo = 默认按钮是「否」。返回 $true（是）/ $false（否）/ $null（点标题栏的 × 关掉了，没选）
function Show-TopYesNo([string]$Text, [string]$Title, [bool]$DefaultNo = $false) {
    $r = Show-DrDialog $Text $Title @('是', '否') $(if ($DefaultNo) { 1 } else { 0 }) -1 'question'
    if ($r -lt 0) { return $null }
    return ($r -eq 0)
}

# 加不加载敌人信息 mod：玩家在启动器「工具与设置」→「游戏」里关掉了就不加载（所有电脑都能关，2026-11-11 应 Souls Vision 作者的要求），否则加载（不问）
function Test-EnemyInfoMod {
    if ((Get-EnemyInfoChoice) -eq 'off') {
        Write-Host '  敌人信息 mod：按你的设置没加载（想打开：启动器「工具与设置」→「游戏」）。'
        return $false
    }
    $gpus = @(Get-GpuNames)
    if ($gpus.Count -ge 2) {
        Write-Host ('  敌人信息 mod：加载（这台电脑有两块显卡：' + ($gpus -join '、') + '；游戏启动不了或读档闪退的话，在启动器「工具与设置」→「游戏」里关掉它）')
    }
    return $true
}

# 崩溃看守：双显卡电脑上加载着敌人信息 mod 时游戏崩溃了，问要不要改成不加载
function Ask-EnemyInfoOffAfterCrash {
    if (@(Get-GpuNames).Count -lt 2 -or (Get-EnemyInfoChoice) -eq 'off' -or -not (Test-Path -LiteralPath (Join-Path $UserDllDir 'souls_vision.dll'))) { return }
    try {
        $off = Show-TopYesNo ("这台电脑有两块显卡，这次游戏加载了敌人信息 mod（敌人头上的血条、状态条）。" +
            "它在有的双显卡电脑上会让游戏读档时闪退。`r`n`r`n" +
            "要改成不加载吗？（游戏里就没有敌人血条和状态条了，以后想再用：启动器「工具与设置」→「游戏」）") '暗黑重铸 · 敌人信息 mod'
        if ($off -eq $true) { Set-EnemyInfoChoice 'off' }
    } catch { }
}

function Join-DllLines([string]$DllLines) {
    $u = Get-UserDllLines
    if ($u) { $DllLines = $DllLines + "`r`n" + $u }
    if ($script:PlayerLoad -and $script:PlayerLoad.Dll) { $DllLines = $DllLines + "`r`n" + $script:PlayerLoad.Dll }      # YAFSML自定义.ini 的 [dll]
    if ($script:CoopDll) { $DllLines = $DllLines + "`r`n; 联机启动：Seamless Co-op（和法魂一样放最后）`r`nseamlesscoop=" + $script:CoopDll }
    return $DllLines
}

# 游戏脚本覆盖包（reroll\scripts.py）：赐福脚本、公共事件、玩家动作脚本随机器输出也会改，不能直接用固定文件覆盖，
# 按 [mod] 的加载顺序取最后生效的那份，把我们的功能合并进去，写到 out\scripts；返回要追加的 [mod] 行（失败返回空，照常启动）
function Get-ScriptsLine([string]$ModLines) {
    if (-not (Test-Path -LiteralPath $ScriptsTool)) { return '' }
    $py = Find-Python
    if (-not $py) { Write-Warn '找不到 Python，这次不加载游戏脚本覆盖包。'; return '' }
    $dirs = @(($ModLines -split "`r?`n") | Where-Object { $_ -match '^\s*[^;=\s][^=]*=(.+)$' } | ForEach-Object { $Matches[1].Trim() })
    $a = @('-X', 'utf8', $ScriptsTool, '--out', $ScriptsPack, '--dll-dir', $RandomDir)
    $gr = Resolve-GameRoot
    if ($gr) { $a += @('--dll-dir', (Join-Path $gr 'Game')) }
    $a += @('--sources') + $dirs
    $r = Invoke-PyJson $py $a
    if ($r -and $r.ok -and $r.warn) { Write-Warn ('游戏脚本：' + $r.msg); return ("`r`nDR_Scripts=" + $ScriptsPack) }
    if ($r -and $r.ok) { Write-Ok ('游戏脚本：' + $r.msg); return ("`r`nDR_Scripts=" + $ScriptsPack) }
    Write-Warn ('游戏脚本覆盖包合并失败，这次不加载（赐福「更多选项」、局内难度、一键出售、不受坠落伤害、蹬墙跳、训练木桩这次都没有）：' + $(if ($r) { $r.msg } else { '没有输出' }))
    Write-PyErrors
    return ''
}

# 菜单覆盖包（reroll\menu.py）：自制状态图标（buff 图标）、生成装备的稀有度边框图标。从本机游戏 Data0 里的原版菜单文件合成到 out\menu（只读游戏文件，
# 没变就沿用上次的）；返回要追加的 [mod] 行（失败返回空，照常启动，只是没有自制图标）
function Get-MenuLine {
    if (-not (Test-Path -LiteralPath $MenuTool)) { return '' }
    $py = Find-Python
    $gr = Resolve-GameRoot
    if (-not $py -or -not $gr) { Write-Warn '找不到 Python 或游戏目录，这次不加载自制状态图标。'; return '' }
    $game = Join-Path $gr 'Game'
    $r = Invoke-PyJson $py @('-X', 'utf8', $MenuTool, '--out', $MenuPack, '--game', $game, '--dll-dir', $RandomDir, '--dll-dir', $game)
    if ($r -and $r.ok) {
        Write-Ok ('菜单：' + $r.msg)
        $line = "`r`nDR_Menu=" + $MenuPack
        # 标题封面（menu.py 做的两个小包，普通 / 死亡以上）：标题画面一启动就读进来，进了存档换不了，所以按启动时定的难度挂（$script:TitleCover，Invoke-Launch 里定）
        $cover = if ($script:TitleCover) { $script:TitleCover } else { 'normal' }
        $tp = if ($r.title) { $r.title.$cover } else { $null }
        if ($tp) {
            $line += "`r`nDR_Title=" + $tp
            Write-Host ('  标题封面   : ' + $(if ($cover -eq 'hard') { '死亡以上（魇火、咒痕）' } else { '普通（熔炉）' }))
        }
        return $line
    }
    Write-Warn ('菜单覆盖包合成失败，这次不加载（词条的叠层图标显示成原版的样子或不显示，生成装备照原版图标、没有稀有度边框）：' + $(if ($r) { $r.msg } else { '没有输出' }))
    Write-PyErrors
    return ''
}

# 跑一个最后输出一行 JSON 结果的 Python 工具（scripts.py、menu.py）：返回解析好的结果（没有返回 $null）。
# 错误输出（报错的 traceback 之类）留在 $script:PyErr，失败时 Write-PyErrors 把最后几行写进运行日志（以前直接丢掉，失败了只看得到「没有输出」）。
# 要在函数里把 ErrorActionPreference 设成 Continue：脚本默认是 Stop，2>&1 收进来的错误输出第一行就会被当成异常中断启动
function Invoke-PyJson([string]$Py, [string[]]$PyArgs) {
    $ErrorActionPreference = 'Continue'
    $env:PYTHONIOENCODING = 'utf-8'
    $out = @(& $Py @PyArgs 2>&1)
    $script:PyErr = @($out | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { $_.ToString() })
    $json = $out | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] -and ([string]$_).TrimStart().StartsWith('{') } | Select-Object -Last 1
    if (-not $json) { return $null }
    try { return ([string]$json | ConvertFrom-Json -ErrorAction Stop) } catch { return $null }
}

function Write-PyErrors {
    $lines = @($script:PyErr | Where-Object { $_ -and $_.Trim() } | Select-Object -Last 15)
    if (-not $lines) { return }
    Write-Host '  Python 的错误输出（最后几行）：' -ForegroundColor DarkYellow
    foreach ($l in $lines) { Write-Host ('    ' + $l) -ForegroundColor DarkYellow }
}

# 玩家自己加的（usermods.ps1）：mods\ 文件夹里的 mod、YAFSML自定义.ini 的 [mod] / [mod_after] / [dll]；出错不耽误启动。
# 记在 $script:PlayerLoad（Join-DllLines 读），给玩家看加载了哪些、有什么问题
function Get-PlayerLoad {
    $script:PlayerLoad = @{ Before = ''; After = ''; Dll = ''; Mods = @(); Notes = @() }
    try {
        [void](New-UserIni)
        $script:PlayerLoad = Get-UserLoadLines
    } catch {
        Write-PlayerWarn ('读 mods 文件夹 / YAFSML自定义.ini 出错，这次不加载自己加的 mod：' + $_.Exception.Message)
        return $script:PlayerLoad
    }
    if (@($script:PlayerLoad.Mods).Count) { Write-Player ('自己加的 mod：' + (@($script:PlayerLoad.Mods) -join '、')) }
    foreach ($n in @($script:PlayerLoad.Notes)) { Write-PlayerWarn $n }
    return $script:PlayerLoad
}

function Write-IniFile([string]$ModLines, [string]$DllLines) {
    if (-not (Test-Path -LiteralPath $TplPath)) { throw ('缺少模板：' + $TplPath) }
    # 玩家的 mod 排在整合包前面（同名文件以整合包为准）；也给游戏脚本合并当来源（按加载顺序取最后生效的那份，和 YAFSML 一样）
    $pl = Get-PlayerLoad
    if ($pl.Before) { $ModLines = $pl.Before + "`r`n" + $ModLines }
    $sl = Get-ScriptsLine $ModLines
    Write-Progress-Bar 97
    $ml = Get-MenuLine
    Write-Progress-Bar 100
    $ModLines = $ModLines + $sl + $ml
    if ($pl.After) { $ModLines = $ModLines + "`r`n" + $pl.After }      # YAFSML自定义.ini 的 [mod_after]：最后加载，同名文件以它为准
    $DllLines = Join-DllLines $DllLines
    $tpl = Get-Content -LiteralPath $TplPath -Raw -Encoding UTF8
    $out = $tpl.Replace('@MOD_LINES@', $ModLines).Replace('@DLL_LINES@', $DllLines)
    # YAFSML自定义.ini 的 [patch] [tweak] [log] 等：替换模板里同名的设置（存档 / 内存相关的不让改）
    try {
        $mg = Merge-UserIniSettings $out
        $out = $mg.Text
        foreach ($a in @($mg.Applied)) { Write-Host ('  自定义设置：' + $a) }
        foreach ($n in @($mg.Notes)) { Write-PlayerWarn $n }
    } catch { Write-PlayerWarn ('YAFSML自定义.ini 的设置没用上（读的时候出错）：' + $_.Exception.Message) }
    $out = $out -replace "`r?`n", "`r`n"
    [System.IO.File]::WriteAllText($YafIni, $out, (New-Object System.Text.UTF8Encoding($false)))
    Write-Ok ('已生成配置：' + $YafIni)
}

function Show-IniDry([string]$ModLines, [string]$DllLines) {
    Write-Head 'DRY-RUN：即将写入 yafsml\YAFSML.ini 的 [mod] / [dll]'
    $pl = Get-PlayerLoad
    Write-Host '[mod]'
    if ($pl.Before) { Write-Host $pl.Before }
    Write-Host $ModLines
    Write-Host ('DR_Scripts=' + $ScriptsPack + '   （启动时合并生成）')
    Write-Host ('DR_Menu=' + $MenuPack + '   （启动时从原版菜单文件合成）')
    if ($pl.After) { Write-Host $pl.After }
    Write-Host '[dll]'
    Write-Host (Join-DllLines $DllLines)
    Write-Host ''
    Write-Host '路径检查：'
    foreach ($line in ($ModLines -split "`r?`n")) {
        if ($line -match '^\s*(DR_\w+)\s*=\s*(.+)$') {
            $k = $Matches[1]; $v = $Matches[2].Trim()
            $exists = Test-Path -LiteralPath $v
            Write-Host ('  ' + $k + ' -> ' + $v + '  (存在=' + $exists + ')')
        }
    }
}

# ---------------------------------------------------------------- 启动游戏
# 以前 YAFSML 第一次启动（yafsml\cache 为空，或游戏更新后）会先「预热」一次：先启动一次只建 BootBoost 缓存再关掉，
# 因为那时候缓存现场建的那一局读档会崩在 YAFSML.dll 里。2026-10-30 用 YAFSML 0.10.4 测过缓存全空直接启动：
# 7 个缓存当场建好、文字包和 regulation 都覆盖上了、读档进地图不闪退，所以去掉了预热。

function Stop-EldenRing {
    $proc = Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue
    if (-not $proc) { return }
    $proc | ForEach-Object { try { $_.Kill() } catch { } }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue)) { break }
    }
}

# 启动前整理日志：
# - 每次启动都重写的日志（dark_ui、souls_vision）上一次的就没了：先复制一份到 launcher\logs\dll_runs
#  （文件名前面是那份日志最后写入的时间，每种留最近 10 份），诊断包会带上；
# - 一直往后追加的日志（各 DLL、YAFSML、随机器的 CrashFix）超过 2 MB 就挪成 <文件名>.old（只留一份），免得越积越大；
# - 幻化插件每天一个日志，只留最近 14 天；
# - YAFSML.log 自己不写时间：先追加一行分隔（时间 + 启动方式），分得清哪几行是哪次启动的
$RunLogDir = Join-Path $LauncherDir 'logs\dll_runs'
$AppendLogs = @('dark_core\dark_core.log', 'dark_lock\dark_lock.log', 'dark_sell\dark_sell.log', 'dark_slot\dark_slot.log', 'dark_wings\dark_wings.log')

function Save-RunLogs([string]$Mode) {
    $grow = @($AppendLogs | ForEach-Object { Join-Path $UserDllDir $_ }) + @($RandomLog, (Join-Path $RandomDir 'dll\RandomizerCrashFix_log.txt'))
    foreach ($f in $grow) {
        try {
            $it = Get-Item -LiteralPath $f -ErrorAction Stop
            if ($it.Length -gt 2MB) { Move-Item -LiteralPath $it.FullName -Destination ($it.FullName + '.old') -Force }
        } catch { }
    }
    Get-ChildItem -LiteralPath (Join-Path $UserDllDir 'logs') -Filter 'ertransmogrify_*.log' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Force -ErrorAction SilentlyContinue
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $RandomLog -Parent) | Out-Null
        [System.IO.File]::AppendAllText($RandomLog, ('==== ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' 暗黑重铸 启动（' + $Mode + '）====' + "`r`n"),
            (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
    foreach ($f in @((Join-Path $UserDllDir 'dark_ui\dark_ui.log'), (Join-Path $UserDllDir 'souls_vision.log'))) {
        try {
            $it = Get-Item -LiteralPath $f -ErrorAction Stop
            if ($it.Length -eq 0) { continue }
            New-Item -ItemType Directory -Force -Path $RunLogDir | Out-Null
            Copy-Item -LiteralPath $it.FullName -Destination (Join-Path $RunLogDir ($it.LastWriteTime.ToString('yyyyMMdd_HHmmss') + '_' + $it.Name)) -Force
            Get-ChildItem -LiteralPath $RunLogDir -Filter ('*_' + $it.Name) -File | Sort-Object Name -Descending | Select-Object -Skip 10 |
                Remove-Item -Force -ErrorAction SilentlyContinue
        } catch { }
    }
}

function Start-YafGame([string]$Mode = '') {
    if (-not (Test-Path -LiteralPath $YafExe))  { Write-Err ('找不到 YAFSML：' + $YafExe); return $false }
    $erRoot = Resolve-GameRoot
    if (-not $erRoot) {
        Write-Warn '还没有可用的游戏路径（未设置，或自动检测到多个候选）。先选一下游戏目录：'
        if (-not (Set-GameRootInteractive)) { Write-Err '未选择游戏路径，取消启动。'; return $false }
        $erRoot = Resolve-GameRoot -Refresh
    }
    $gameExe = Join-Path $erRoot 'Game\eldenring.exe'
    if (-not (Test-Path -LiteralPath $gameExe)) { Write-Err ('游戏路径无效（找不到 Game\eldenring.exe）：' + $erRoot); return $false }
    Write-Host ('  游戏：' + $gameExe)
    if ($NoLaunch) {
        Write-Warn '[-NoLaunch] 只写配置，不启动 YAFSML。'
        return $true
    }
    if (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) {
        Write-Warn '检测到游戏已在运行，先关闭旧进程...'
        Stop-EldenRing
    }
    Save-RunLogs $Mode
    $arg = @('--game-path', ('"' + $erRoot + '"'))
    Start-Process -FilePath $YafExe -ArgumentList $arg -WorkingDirectory $YafDir -WindowStyle Minimized
    Write-Host ''
    Write-Host '  已启动 YAFSML，等待 eldenring.exe（最多 60 秒）...'
    Write-Player '正在启动游戏……'
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) { $ok = $true; break }
    }
    if ($ok) {
        Write-Ok '游戏已启动。'
        Write-Player '游戏已启动。'
        # 后台看守：游戏崩溃时自动导出诊断包（正常退出什么都不做）
        $gp = Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1
        if ($gp) { Start-CrashWatch $gp.Id; Write-Host '  如果游戏崩溃，会自动导出诊断包到「崩溃诊断」文件夹。' }
    } else {
        Write-PlayerWarn ('60 秒内没看到游戏启动，看日志：' + $RandomLog)
    }
    Write-Host ('  日志：' + $RandomLog)
    return $ok
}

# ---------------------------------------------------------------- 动作：打开随机器
function Invoke-Randomizer {
    $rs = Get-RandomizerStatus
    if (-not $rs.Ok) { Write-Err $rs.Msg; return }
    if (-not (Test-DotNet8)) { Write-Err (Get-DotNet8Msg); return }
    if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { Write-Warn '随机器已经开着。'; return }
    Write-Head '打开随机器'
    Write-Host '  在随机器窗口里按下面做：' -ForegroundColor Yellow
    Write-Host '    1) 点「选择游戏exe启动文件」选好 eldenring.exe（第一次需要）'
    Write-Host '    2) 「合并其它MOD」留空（整合包直接用原版，不合并别的包；以前填过的已经自动清掉）'
    Write-Host '    3) 勾选「敌人随机」；「物品随机」可开可不开（开了会打乱法术祷告、道具、材料的位置和商人货架，原版装备整合包照样换掉）'
    Write-Host '       「自定义敌人」启动器已经勾好，不要取消（追忆 Boss 只在追忆之间换、按地区控制精英比例都靠它）'
    Write-Host '    4) 点「随机化敌人」（开了物品随机是「随机化物品与敌人」）；想要新的随机结果，点之前先勾上「重roll种子」（不勾会沿用上次的种子，敌人和上次一模一样）'
    Write-Host '       完成后关掉随机器（不要点它的「启动游戏」），回启动器点「一键启动（敌人随机）」'
    if ($DryRun) { Write-Warn '[-DryRun] 不启动随机器。'; return }
    $gr = Resolve-GameRoot
    $note = Reset-RandMod $(if ($gr) { Join-Path $gr 'Game\eldenring.exe' } else { '' })
    if ($note) { Write-Host ('  ' + $note) }
    Start-Process -FilePath $RandomExe -WorkingDirectory $RandomDir
}

# 离线增量更新（用户 2026-11-10）：launcher\update.py 核对、备份、替换，失败自动还原；结果写 logs\update_result.txt
function Invoke-Update([string]$Zips) {
    $a = @()
    foreach ($z in ($Zips -split '\|')) { if ($z.Trim()) { $a += @('--zip', $z.Trim()) } }
    if (-not $a.Count) { Write-Err '没有选更新包'; return $false }
    return (Invoke-UpdatePy $a)
}

# 在线更新（用户 2026-11-11「通过 gitee 实现自动更新」）：-Action checkupdate 只检查；autoupdate 检查 → 下载 → 应用（同上）
function Invoke-UpdatePy([string[]]$Extra) {
    $py = Find-Python
    if (-not $py) { Write-Err '找不到 Python（整合包里的 launcher\python 不见了？），没法更新'; return $false }
    $a = @('-X', 'utf8', (Join-Path $LauncherDir 'update.py'), '--root', (Split-Path -Parent $LauncherDir)) + $Extra
    if ($env:DARKFORGE_UPDATE_MANIFEST) { $a += @('--manifest', $env:DARKFORGE_UPDATE_MANIFEST) }    # 测试用（本机模拟服务器）
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = 0
    # 输出逐行 Write-Host（直接 & $py 的输出会变成函数的返回值：日志里看不到，返回值也总是「真」）
    & $py @a 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host ('  ' + $_.ToString()) -ForegroundColor DarkYellow } else { Write-Host $_ }
    }
    return ($LASTEXITCODE -eq 0)
}

# 找 Python 3.8+：优先用包里自带的 launcher\python\python.exe，其次系统里装的；找不到返回 $null
function Find-Python {
    $ErrorActionPreference = 'Continue'
    $cands = @(Join-Path $LauncherDir 'python\python.exe')
    foreach ($cmd in @('python', 'py')) {
        $c = Get-Command $cmd -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c) { $cands += $c.Source }
    }
    foreach ($p in $cands) {
        if (-not (Test-Path -LiteralPath $p)) { continue }
        & $p -c 'import sys, ctypes, zlib; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return $p }
    }
    return $null
}

# 原版文件的来源（reroll\vanilla.py）：装了随机器用它带的 diste\Vanilla；没装（正式发布不带随机器）从玩家的游戏取：
# regulation 用 Game\regulation.bin 并核对是不是原版，文字包从 Data0 解出来缓存。返回 @{ Reg; Msg; From; Check; Vanilla }，
# 拿不到返回 $null，原因在 $script:VanillaErr
function Get-VanillaSource([string]$Py) {
    if ($script:VanillaSrc) { return $script:VanillaSrc }
    $a = @('-X', 'utf8', $VanillaTool, 'prepare')
    $gr = Resolve-GameRoot
    if ($gr) { $a += @('--dll-dir', (Join-Path $gr 'Game')) }
    $r = Invoke-PyJson $Py $a
    if (-not $r -or -not $r.ok) {
        $script:VanillaErr = $(if ($r) { [string]$r.msg_err } else { '没有输出' })
        Write-PyErrors
        return $null
    }
    $script:VanillaSrc = @{ Reg = [string]$r.reg; Msg = [string]$r.msg; From = [string]$r.from; Check = [string]$r.check; Vanilla = [bool]$r.vanilla }
    return $script:VanillaSrc
}

# 生成重随包：基础 = 原版 / 随机器输出；文字包按语言先找随机器输出，没有就用原版；$Seed 给了就用它当重随的种子（否则重随自己随机取）；
# $State 给了就用它当一次性重随的记录（联机用 角色记录\联机\once_<种子>.json），不给是 reroll.py 默认的 角色记录\once.json
function Invoke-RerollGenerate([string]$Py, [bool]$Rand, $Seed = $null, [string]$State = '') {
    $ErrorActionPreference = 'Continue'
    $vs = Get-VanillaSource $Py
    if (-not $vs) { Write-Err ('拿不到原版文件：' + $script:VanillaErr); return $false }
    $world = if ($script:RandWorld) { $script:RandWorld } else { $RandomDir }      # 敌人随机：平常的世界或高难度世界（Boss 模组）
    $base = if ($Rand) { Join-Path $world 'regulation.bin' } else { $vs.Reg }
    $pyArgs = @('-X', 'utf8', $RerollTool, '--base-reg', $base, '--out', $RerollPack, '--dll-dir', $RandomDir,
                '--label', $(if ($Rand) { 'rand' } else { 'vanilla' }))
    if ($Rand) { $pyArgs += @('--msg-src', (Join-Path $world 'msg'), '--randomizer-dir', $world, '--maps-out', $RerollMapsPack) }
    $pyArgs += @('--msg-src', $vs.Msg)
    if ($null -ne $Seed) { $pyArgs += @('--seed', [string]$Seed) }
    if ($State) { $pyArgs += @('--state', $State) }
    if (@($script:BossKeys).Count) { $pyArgs += @('--boss-mods', (@($script:BossKeys) -join ',')) }
    if ($Rand -and @($script:BossArena).Count) { $pyArgs += @('--boss-arena', (@($script:BossArena) -join ',')) }
    $gr = Resolve-GameRoot
    if ($gr) { $pyArgs += @('--dll-dir', (Join-Path $gr 'Game')) }
    $env:PYTHONIOENCODING = 'utf-8'
    $env:DR_PROGRESS = '1'            # 重随打印「§% 百分比」行，图形界面画成进度条（reroll\progress.py）
    # 错误输出也收进来逐行显示（运行日志、图形界面里都看得到）：以前不重定向，报错的 traceback 只进控制台，日志里没有
    & $Py @pyArgs 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host ('  ' + $_.ToString()) -ForegroundColor DarkYellow } else { Write-Host $_ }
    }
    $code = $LASTEXITCODE
    Remove-Item Env:DR_PROGRESS -ErrorAction SilentlyContinue
    if ($code -eq 0) { Write-Progress-Bar 92 }
    return ($code -eq 0)
}

# 新开局（存档文件夹里还没有 Dark Reforged 存档）用敌人随机启动：先自动做一次一次性重随（骨灰位置、开局装备和遗物重新抽），
# 种子用这台电脑现在的时间（yyyyMMddHHmmss，用户 2026-10-29）。返回要传给重随的种子；不是新开局、或者是无敌人随机，返回 $null。
# 只看单机存档 ER0000.rng（联机存档 .co2 不算；联机启动不走这里，用联机种子）
function Get-NewGameSeed([bool]$Rand) {
    if (-not $Rand -or @(Get-RngSaveFiles | Where-Object { $_.Name -eq 'ER0000.rng' }).Count) { return $null }
    Write-Host '  没找到暗黑重铸存档（新开局）：先重随一次物品（同「一键重随物品」），种子用当前时间。'
    Invoke-OnceReset
    return [long](Get-Date -Format 'yyyyMMddHHmmss')
}

# ---------------------------------------------------------------- 联机（Seamless Co-op，dev\coop\联机计划.md 阶段一）
# - ersc.dll 玩家自己放（不打包）：整合包 dll\ 下（dll\SeamlessCoop\ersc.dll，连同它的 ersc_settings.ini、locale 文件夹），
#   没有就用游戏目录 Game\SeamlessCoop\ 里的。平常启动不加载它（Get-UserDllLines 跳过），联机启动才加载，和法魂一样放 [dll] 最后。
# - 存档：Seamless Co-op 把存档扩展名换成 co2，YAFSML 的 replace_seamless_coop_save_filename 再换成 ER0000.rngcoop（和单机的 ER0000.rng 分开；以前是 ER0000.rng.co2，见 YAFSML.ini.tpl）；
#   dark_core / dark_sell / dark_lock 看到 ersc.dll 加载了，角色记录就用 角色记录\联机\（格子编号和单机各算各的）；Erd Tools 的存档扩展名跟着换成 co2。
# - 两个人的游戏数据必须一样：重随用联机种子（敌人随机 = 随机器的种子，无敌人随机 = 固定的 $CoopVanillaSeed），
#   一次性重随记录用 角色记录\联机\once_<种子>.json（同一个种子抽出来的都一样）；敌人随机靠联机码对齐（Get-CoopCode3）。
# - 玩家流程（2026-11-16 起）：房主「开房」（Invoke-CoopHost），队友「加入」（Invoke-CoopJoin），一个联机码 DR3 带上密码、Seamless 规则、
#   敌人设置、世界和启动方式。联机核对码（reroll\coopfp.py）写进兼容档案，进会话后联机通道自动比对。
$CoopVanillaSeed = 20261102
$script:CoopDll = ''          # 联机启动时 [dll] 最后加的 ersc.dll（YAFSML.ini 里的写法；Join-DllLines）
$script:ErdSaveExt = 'rng'    # Erd Tools 的存档扩展名：单机 rng，联机 co2（Test-UserDllSafe）

# 找 Seamless Co-op 的 ersc.dll：整合包 dll\ 和下一层文件夹（_ 开头的不算），再看游戏目录 Game\SeamlessCoop\；没有返回 $null
function Find-Ersc {
    $cands = @()
    if (Test-Path -LiteralPath $UserDllDir) {
        $cands += @(Get-ChildItem -LiteralPath $UserDllDir -Filter 'ersc.dll' -File -ErrorAction SilentlyContinue)
        foreach ($d in (Get-ChildItem -LiteralPath $UserDllDir -Directory -ErrorAction SilentlyContinue | Sort-Object Name)) {
            if ($d.Name.StartsWith('_')) { continue }
            $cands += @(Get-ChildItem -LiteralPath $d.FullName -Filter 'ersc.dll' -File -ErrorAction SilentlyContinue)
        }
    }
    $gr = Resolve-GameRoot
    if ($gr) {
        $g = Join-Path $gr 'Game\SeamlessCoop\ersc.dll'
        if (Test-Path -LiteralPath $g) { $cands += Get-Item -LiteralPath $g }
    }
    return ($cands | Select-Object -First 1)
}

# ini 里某一项（key = value，分号后是注释）：返回正则匹配（Groups[1] 是值），没有返回 $null
function Get-IniMatch([string]$Text, [string]$Key) {
    $m = [regex]::Match($Text, '(?im)^[ \t]*' + [regex]::Escape($Key) + '[ \t]*=[ \t]*([^\r\n;]*)')
    if ($m.Success) { return $m }
    return $null
}

# Seamless Co-op 的配置（ersc.dll 旁边的 ersc_settings.ini）：
#   save_file_extension 必须是 co2（YAFSML 再换成 .rngcoop；别的扩展名会读写别的存档，sl2 还会被换成单机的 ER0000.rng）→ 不是就改（原 ini 备份）；
#   随人数加强（血量、架势、伤害，以主机的为准）会叠在整合包的敌人血量上 → 打印出来提醒；
#   联机密码（cooppassword）空的不让启动：Seamless Co-op 2.0.1 会弹「Please enter a session password」然后整个游戏退出（2026-11-02 实测）。
#   入侵（allow_invaders）关掉、死后一直观战（always_spectate_on_death）打开（斗技场试炼联机，联机计划 13.13）。
# 返回能不能联机启动
function Test-ErscSettings($Ersc) {
    $ini = Join-Path $Ersc.DirectoryName 'ersc_settings.ini'
    if (-not (Test-Path -LiteralPath $ini)) {
        Write-Err ('Seamless Co-op 缺少 ersc_settings.ini（应该和 ersc.dll 放在一起）：' + $Ersc.DirectoryName)
        return $false
    }
    try {
        $bytes = [System.IO.File]::ReadAllBytes($ini)
        $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
        $txt = [System.IO.File]::ReadAllText($ini)
        $m = Get-IniMatch $txt 'save_file_extension'
        $ext = if ($m) { $m.Groups[1].Value.Trim() } else { '' }
        if ($ext -ne 'co2') {
            if ($DryRun) {
                Write-Warn ('Seamless Co-op 的存档扩展名是「' + $ext + '」，真的启动时会改成 co2：' + $ini)
            } else {
                Copy-Item -LiteralPath $ini -Destination ($ini + '.bak_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) -Force
                if ($m) {
                    $txt = $txt.Substring(0, $m.Groups[1].Index) + 'co2' + $txt.Substring($m.Groups[1].Index + $m.Groups[1].Length)
                } else {
                    $txt = $txt.TrimEnd() + "`r`n`r`n[SAVE]`r`nsave_file_extension = co2`r`n"
                }
                [System.IO.File]::WriteAllText($ini, $txt, (New-Object System.Text.UTF8Encoding($bom)))
                Write-Warn ('Seamless Co-op 的存档扩展名是「' + $ext + '」，已改成 co2（联机存档是 ER0000.rngcoop，和单机存档分开；原 ini 已备份）：' + $ini)
            }
        }
        # 入侵关掉（联机计划 13.2 G7）：入侵者的游戏数据和我们对不上，Seamless 的反作弊按什么限制匹配也看不到
        $inv = Get-IniMatch $txt 'allow_invaders'
        if ($inv -and $inv.Groups[1].Value.Trim() -ne '0') {
            if ($DryRun) {
                Write-Warn ('Seamless Co-op 开着入侵（allow_invaders），真的启动时会关掉：' + $ini)
            } else {
                Copy-Item -LiteralPath $ini -Destination ($ini + '.bak_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) -Force
                $txt = $txt.Substring(0, $inv.Groups[1].Index) + '0' + $txt.Substring($inv.Groups[1].Index + $inv.Groups[1].Length)
                [System.IO.File]::WriteAllText($ini, $txt, (New-Object System.Text.UTF8Encoding($bom)))
                Write-Player '联机时不开放入侵：已把 Seamless Co-op 设置里的入侵关掉（整合包的数据和别的玩家对不上，入侵会出问题）。'
            }
        }
        # 死后一直观战（联机计划 13.13，照黄金树爬塔）：斗技场试炼倒下的队员留在竞技场里观战，队友接着打；所有人都倒下或者有人在赐福休息才复活。
        # 默认 0 只在 Boss 战观战，斗技场里倒下的人会马上复活在外面
        $spec = Get-IniMatch $txt 'always_spectate_on_death'
        if ($spec -and $spec.Groups[1].Value.Trim() -ne '1') {
            if ($DryRun) {
                Write-Warn ('Seamless Co-op 的死后观战（always_spectate_on_death）不是 1，真的启动时会改成 1：' + $ini)
            } else {
                Copy-Item -LiteralPath $ini -Destination ($ini + '.bak_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) -Force
                $txt = $txt.Substring(0, $spec.Groups[1].Index) + '1' + $txt.Substring($spec.Groups[1].Index + $spec.Groups[1].Length)
                [System.IO.File]::WriteAllText($ini, $txt, (New-Object System.Text.UTF8Encoding($bom)))
                Write-Player '联机时倒下了会观战队友，直到所有人都倒下或者有人在赐福休息：已把 Seamless Co-op 设置里的死后观战打开。'
            }
        }
        # 中文（用户 2026-11-17「先把无缝联机的汉化做了」）：launcher\ersc_locale\*.json 复制进 Seamless Co-op 的 locale 文件夹（不一样才复制）。
        # Seamless 按游戏的 Steam 语言找 locale\<语言>.json（简体中文 schinese）；Steam 语言是简体中文、mod_language_override 空着时再填上 schinese 保险
        if (-not $DryRun) {
            Install-ErscLocale $Ersc
            $lo = Get-IniMatch $txt 'mod_language_override'
            if ($lo -and -not $lo.Groups[1].Value.Trim() -and (Get-SteamGameLanguage) -eq 'schinese' -and
                (Test-Path -LiteralPath (Join-Path $Ersc.DirectoryName 'locale\schinese.json'))) {
                $txt = $txt.Substring(0, $lo.Groups[1].Index) + 'schinese' + $txt.Substring($lo.Groups[1].Index + $lo.Groups[1].Length)
                [System.IO.File]::WriteAllText($ini, $txt, (New-Object System.Text.UTF8Encoding($bom)))
                Write-Host '  Seamless Co-op 的语言设成简体中文（mod_language_override = schinese）'
            }
        }
        $sc = @()
        foreach ($p in @(@('enemy_health_scaling', '小怪血量'), @('boss_health_scaling', 'Boss 血量'), @('enemy_posture_scaling', '小怪架势'),
                         @('boss_posture_scaling', 'Boss 架势'), @('enemy_damage_scaling', '小怪伤害'), @('boss_damage_scaling', 'Boss 伤害'))) {
            $v = Get-IniMatch $txt $p[0]
            if ($v) { $sc += ($p[1] + ' +' + $v.Groups[1].Value.Trim() + '%') }
        }
        if ($sc) {
            Write-Host ('  Seamless Co-op 随人数加强（以主机的设置为准，每多一个玩家）：' + ($sc -join '，'))
            Write-Host '  整合包的敌人血量已经比原版高很多，再叠这里的加血会很肉；主机觉得太肉可以把 ersc_settings.ini 里的 boss_health_scaling、enemy_health_scaling 调低。'
        }
        $pw = Get-IniMatch $txt 'cooppassword'
        if (-not $pw -or -not $pw.Groups[1].Value.Trim()) {
            $m = 'ersc_settings.ini 里的联机密码（cooppassword）是空的，Seamless Co-op 会报错并让游戏退出。在启动器「联机」里点「开房」会自动生成一个；或者在 cooppassword = 后面自己填一个（两个人填一样的）：' + $ini
            if ($DryRun) { Write-Warn $m } else { Write-Err $m; return $false }
        }
        return $true
    } catch {
        Write-Err ('检查 Seamless Co-op 的配置失败，没有启动：' + $_.Exception.Message)
        return $false
    }
}

# Seamless Co-op 的中文：launcher\ersc_locale 里的语言文件（schinese.json，dev 用 scratchpad ersc_zh.py 照 english.json 逐行翻的）
# 复制进 Seamless 的 locale 文件夹，内容不一样才复制（玩家自己下载的 Seamless 也能用上）
$ErscLocaleDir = Join-Path $LauncherDir 'ersc_locale'
function Install-ErscLocale($Ersc) {
    try {
        $dst = Join-Path $Ersc.DirectoryName 'locale'
        foreach ($f in @(Get-ChildItem -LiteralPath $ErscLocaleDir -Filter '*.json' -File -ErrorAction SilentlyContinue)) {
            $to = Join-Path $dst $f.Name
            if ((Test-Path -LiteralPath $to) -and ((Get-FileHash -LiteralPath $to).Hash -eq (Get-FileHash -LiteralPath $f.FullName).Hash)) { continue }
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Copy-Item -LiteralPath $f.FullName -Destination $to -Force
            Write-Host ('  Seamless Co-op 中文：' + $f.Name + ' 已放进 ' + $dst)
        }
    } catch { Write-Warn ('Seamless Co-op 的中文没放进去：' + $_.Exception.Message) }
}

# 游戏的 Steam 语言（steamapps\appmanifest_1245620.acf 的 language，比如 schinese / english）；不是 Steam 版、读不到返回 ''
function Get-SteamGameLanguage {
    try {
        $gr = Resolve-GameRoot
        if (-not $gr) { return '' }
        $steamapps = [IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName($gr.TrimEnd('\')))
        if (-not $steamapps) { return '' }
        $acf = [IO.Path]::Combine($steamapps, 'appmanifest_1245620.acf')
        if (-not (Test-Path -LiteralPath $acf)) { return '' }
        $m = Select-String -LiteralPath $acf -Pattern '"language"\s+"([^"]*)"' | Select-Object -First 1
        if ($m) { return $m.Matches[0].Groups[1].Value }
    } catch { }
    return ''
}

# 文件在整合包里就写成相对 yafsml\ 的路径（..\dll\...，和用户 DLL 一样），不在就写完整路径
function Get-YafRelPath([string]$Full) {
    if ($Full.StartsWith($Paly + '\', [System.StringComparison]::OrdinalIgnoreCase)) { return ('..\' + $Full.Substring($Paly.Length + 1)) }
    return $Full
}

# 联机兼容档案（联机计划 13.4）：联机启动时写给 dark_core，联机通道（dev\dark_core\src\link.rs）握手时发给队友逐项比对。
# 一行「键<Tab>值」：整合包版本、联机核对码、世界、Seamless 的随人数加强和规则（不含密码）、敌人设置。改了键名要和 link.rs 的 LABELS 一起改
$CoopProfile = Join-Path $Paly 'dll\dark_core\coop_profile.txt'
# Seamless Co-op 的版本（联机计划 13.9 B）：ersc.dll 的 PE 时间戳 + 镜像大小；认得的写版本号（特征照黄金树爬塔记的），认不出写原始数值。
# 两人的 Seamless 版本必须一样，写进兼容档案让联机通道比对
$ErscKnown = @{ '6ae0ad1a:d65000' = '2.0.2'; '6af4b20a:d67000' = '2.0.3' }
function Get-ErscVersion($Ersc) {
    try {
        $fs = [System.IO.File]::OpenRead($Ersc.FullName)
        try { $b = New-Object byte[] 4096; [void]$fs.Read($b, 0, 4096) } finally { $fs.Close() }
        $pe = [BitConverter]::ToInt32($b, 0x3C)
        $ts = [BitConverter]::ToUInt32($b, $pe + 8)
        $soi = [BitConverter]::ToUInt32($b, $pe + 24 + 56)
        $key = ('{0:x8}:{1:x}' -f $ts, $soi)
        if ($ErscKnown.ContainsKey($key)) { return ($ErscKnown[$key] + '（' + $key + '）') }
        return ('未知（' + $key + '，' + $Ersc.Length + ' 字节）')
    } catch { return '' }
}

function Write-CoopProfile($Ersc, [string]$Fp, [bool]$Rand) {
    try {
        $ver = Get-CoopPackVersion
        $rules = @(Get-ErscRules $Ersc)
        $enemy = ''
        try {
            $s = [System.IO.File]::ReadAllText((Join-Path $LauncherDir 'reroll\settings.json')) | ConvertFrom-Json
            $enemy = 'elite_share_mult=' + $s.elite_share_mult + ',boss_in_basic_pct=' + $s.boss_in_basic_pct
        } catch { }
        $lines = @('# 联机兼容档案：启动器联机启动时写，dark_core 的联机通道握手时发给队友比对（不含联机密码）',
                   ('version' + "`t" + $ver), ('fingerprint' + "`t" + $Fp), ('world' + "`t" + $script:WorldSuffix),
                   ('scaling' + "`t" + ($rules -join ',')), ('enemy' + "`t" + $enemy), ('seamless' + "`t" + (Get-ErscVersion $Ersc)))
        # 联机码（不算比对的一项；DR3 带着联机密码，只发给会话里的队员）：队友和房主对不上时，联机通道把房主的存到队友的
        # dll\dark_core\coop_host_code.txt，队友退出后点「加入」剪贴板里没有码也能用它
        try { $cc = Get-CoopCode3 $Rand $Ersc; if ($cc.Ok) { $lines += ('code' + "`t" + $cc.Code) } } catch { }
        [System.IO.File]::WriteAllText($CoopProfile, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
        Write-Host ('  联机兼容档案：' + $CoopProfile)
    } catch {
        Write-Warn ('写不了联机兼容档案（联机通道握手时不比对）：' + $_.Exception.Message)
    }
}

# 联机种子：敌人随机 = 随机器的种子（两人用联机随机码对齐了敌人随机，种子就一样），无敌人随机 = 固定的 $CoopVanillaSeed；读不到返回 $null
function Get-CoopSeed([bool]$Rand) {
    if (-not $Rand) { return [long]$CoopVanillaSeed }
    $ri = Get-RandomInfo $RandomDir
    if (-not $ri -or -not $ri.Seed) { Write-Err '读不到随机器的种子（spoiler 日志的文件名里没有），定不了联机种子。先一键重随敌人一次。'; return $null }
    return [long]$ri.Seed
}

# 联机核对码（reroll\coopfp.py）：$Rand = 带上随机器输出的指纹，$WithReroll = 带上这次重随包的指纹；失败返回空串
function Get-CoopFingerprint([bool]$Rand, [bool]$WithReroll) {
    $ErrorActionPreference = 'Continue'
    $tool = Join-Path $LauncherDir 'reroll\coopfp.py'
    $py = Find-Python
    if (-not $py -or -not (Test-Path -LiteralPath $tool)) { return '' }
    $a = @('-X', 'utf8', $tool)
    if ($Rand) { $a += @('--rand', $RandomDir) }
    if ($WithReroll) { $a += @('--reroll', $RerollPack) }
    $a += @('--dll-dir', $RandomDir)
    $gr = Resolve-GameRoot
    if ($gr) { $a += @('--dll-dir', (Join-Path $gr 'Game')) }
    $env:PYTHONIOENCODING = 'utf-8'
    $out = @(& $py @a 2>$null) | Where-Object { $_ -is [string] -and $_.Trim() } | Select-Object -Last 1
    return ([string]$out).Trim()
}

# 联机随机码：「DR1|敌人预设种子|自然精英比例|随机器的选项和种子」。对方「按联机随机码重随敌人」就得到一模一样的敌人随机
#（randomize.ps1 的 Invoke-RandomizeEnemies $Fixed）。敌人预设的种子和用的随机器自然精英比例（按上一次的随机结果算的，
# 不带上的话对方按自己的上一次算，预设就不一样）是一键重随时记下的（spoiler 日志旁边的 .preset），
# 加联机功能以前随机化的、自己开随机器随机化的没有，要先一键重随一次
# 联机随机码第二版（联机计划 13.3 C9）：DR2|预设种子|自然精英比例|精英倍数|普通位置出头目|世界|随机器的选项和种子。
# 敌人设置（启动器「敌人设置」，settings.json 的 elite_share_mult / boss_in_basic_pct）决定敌人预设，世界（high = 死亡以上的改版 Boss 世界）
# 是房主联机启动会用的那个；队友导入时照着改、照着启动，两边的游戏数据才一样
$CoopWorldFile = Join-Path $LauncherDir 'reroll\state\coop_world.txt'
$CoopInv = [Globalization.CultureInfo]::InvariantCulture

function Get-CoopSettingNum([string]$Text, [string]$Name, [double]$Default) {
    $m = [regex]::Match($Text, '(?m)^\s*"' + [regex]::Escape($Name) + '"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)')
    if (-not $m.Success) { return $Default }
    return [double]::Parse($m.Groups[1].Value, $CoopInv)
}

# 只换已有键的数字（两个键在发布的 settings.json 里都有）；没有这个键返回 $null
function Set-CoopSettingNum([string]$Text, [string]$Name, [double]$Value) {
    $m = [regex]::Match($Text, '(?m)^\s*"' + [regex]::Escape($Name) + '"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)')
    if (-not $m.Success) { return $null }
    $g = $m.Groups[1]
    return $Text.Substring(0, $g.Index) + $Value.ToString('0.###', $CoopInv) + $Text.Substring($g.Index + $g.Length)
}

function Get-CoopCode {
    $ri = Get-RandomInfo $RandomDir
    if (-not $ri) { return @{ Ok = $false; Msg = '还没有敌人随机结果。先一键重随敌人一次。' } }
    if ($ri.Merged) { return @{ Ok = $false; Msg = '现在的敌人随机结果是旧版本合并别的包做的。先一键重随敌人一次。' } }
    if (-not $ri.PresetSeed -or -not $ri.PresetNat) { return @{ Ok = $false; Msg = '现在的敌人随机结果没记下敌人预设的种子（加联机功能以前做的，或者是自己开随机器做的）。先一键重随敌人一次再复制。' } }
    if ($ri.Options -notmatch '(?:^|\s)seed:\d+') { return @{ Ok = $false; Msg = 'spoiler 日志第一行里没有种子，生成不了联机随机码。先一键重随敌人一次。' } }
    $txt = try { [System.IO.File]::ReadAllText((Join-Path $LauncherDir 'reroll\settings.json')) } catch { '' }
    $em = (Get-CoopSettingNum $txt 'elite_share_mult' 1.0).ToString('0.###', $CoopInv)
    $bp = (Get-CoopSettingNum $txt 'boss_in_basic_pct' 0.0).ToString('0.###', $CoopInv)
    $world = if (@((Get-BossMods $true).Keys).Count) { 'high' } else { 'low' }
    return @{ Ok = $true; Code = ('DR2|' + $ri.PresetSeed + '|' + $ri.PresetNat + '|' + $em + '|' + $bp + '|' + $world + '|' + $ri.Options); Info = $ri; World = $world }
}

function Get-OptionKey([string]$Options) {
    return ((@($Options -split '\s+') | Where-Object { $_ }) -join ' ')
}

# 按联机随机码重随敌人：$Text 不给就读剪贴板。现在的敌人随机已经是这个码的就不重随
function Invoke-CoopImport([string]$Text) {
    Write-Head '按联机随机码重随敌人'
    $rs = Get-RandomizerStatus
    if (-not $rs.Ok) { Write-Err $rs.Msg; return $false }
    $from = if ($Text) { '给的' } else { '剪贴板里的' }
    if (-not $Text) { try { $Text = [string](Get-Clipboard -Raw) } catch { $Text = '' } }
    $t = ([string]$Text -replace '\s+', ' ').Trim()
    $em = $null; $bp = $null; $world = ''
    if ($t -match '^DR2\|(\d+)\|([-0-9=.,]+)\|([0-9.]+)\|([0-9.]+)\|(high|low)\|(.*(?:^|\s)seed:\d+.*)$') {
        $fixed = @{ PresetSeed = $Matches[1]; Nat = $Matches[2]; Options = (Get-OptionKey $Matches[6]) }
        $em = [double]::Parse($Matches[3], $CoopInv); $bp = [double]::Parse($Matches[4], $CoopInv); $world = $Matches[5]
    } elseif ($t -match '^DR1\|(\d+)\|([-0-9=.,]+)\|(.*(?:^|\s)seed:\d+.*)$') {
        $fixed = @{ PresetSeed = $Matches[1]; Nat = $Matches[2]; Options = (Get-OptionKey $Matches[3]) }
        Write-Warn '这是旧版的联机随机码（DR1）：不带敌人设置和世界，两人的「敌人设置」要自己对一样。'
    } else {
        $show = if ($t.Length -gt 80) { $t.Substring(0, 80) + '…' } elseif ($t) { $t } else { '（空的）' }
        Write-Err ($from + '不是联机随机码（应该是 DR2| 开头的一行，对方在启动器里点「联机」→「复制随机码」得到）：' + $show)
        return $false
    }
    if (-not (Import-CoopEnemy $fixed $em $bp $world)) { return $false }
    $fp = Get-CoopFingerprint $true $false
    if ($fp) { Write-Host ('  敌人随机核对码：' + $fp + '（和对方复制随机码时看到的应该一样）') -ForegroundColor Cyan }
    Write-Host '  现在两人都用「联机」→「联机 · 敌人随机」启动。'
    return $true
}

# 照房主的改敌人设置、世界，敌人随机和码不一样才重随（DR1 / DR2 导入和 DR3「加入」共用）。$em / $bp 是 $null = 码里没带敌人设置
function Import-CoopEnemy($fixed, $em, $bp, [string]$world) {
    # 敌人设置照房主的（不一样才改；原设置备份）。要在重随敌人之前改：敌人预设按它写
    if ($null -ne $em) {
        $sp = Join-Path $LauncherDir 'reroll\settings.json'
        $txt = [System.IO.File]::ReadAllText($sp)
        $myEm = Get-CoopSettingNum $txt 'elite_share_mult' 1.0
        $myBp = Get-CoopSettingNum $txt 'boss_in_basic_pct' 0.0
        if ($myEm -ne $em -or $myBp -ne $bp) {
            if ($DryRun) { Write-Host ('  [-DryRun] 敌人设置会改成房主的：精英倍数 ' + $em + '，普通位置出头目 ' + $bp + '%') }
            else {
                $new = Set-CoopSettingNum $txt 'elite_share_mult' $em
                if ($null -ne $new) { $new = Set-CoopSettingNum $new 'boss_in_basic_pct' $bp }
                if ($null -eq $new) { Write-Err ('改不了敌人设置（settings.json 里没有 elite_share_mult / boss_in_basic_pct）：' + $sp); return $false }
                [void]($new | ConvertFrom-Json)
                Copy-Item -LiteralPath $sp -Destination ($sp + '.bak_coop_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) -Force
                [System.IO.File]::WriteAllText($sp, $new, (New-Object System.Text.UTF8Encoding($false)))
                Write-Player ('敌人设置改成了房主的：精英倍数 ' + $em.ToString('0.###', $CoopInv) + '，普通位置出头目 ' + $bp.ToString('0.###', $CoopInv) + '%（原设置已备份）')
            }
        }
    }
    Set-CoopWorld $world
    $sd = if ($fixed.Options -match '(?:^|\s)seed:(\d+)') { $Matches[1] } else { '' }
    Write-Host ('  联机随机码：种子 ' + $sd + '，敌人预设种子 ' + $fixed.PresetSeed)
    $cur = Get-RandomInfo $RandomDir
    if ($cur -and -not $cur.Merged -and $cur.PresetSeed -eq $fixed.PresetSeed -and $cur.PresetNat -eq $fixed.Nat -and (Get-OptionKey $cur.Options) -eq $fixed.Options) {
        Write-Player '敌人随机已经和房主的一样，不用重随。'
    } else {
        if (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) { Write-Err '游戏还在运行，先退出游戏再重随敌人。'; return $false }
        $erRoot = Resolve-GameRoot
        if (-not $erRoot) { Write-Err '还没有设置游戏路径（随机器要读游戏文件）。先点「游戏路径」选一下。'; return $false }
        if ($DryRun) { Write-Host ('  [-DryRun] 不重随。选项：' + $fixed.Options); return $true }
        Write-Player '敌人随机和房主的不一样，先照房主的重随（随机器窗口会自动打开、自动关闭，约 1~5 分钟，期间不要点它）……'
        $r = Invoke-RandomizeEnemies (Join-Path $erRoot 'Game\eldenring.exe') $fixed
        if (-not $r.Ok) { Write-Err ('按联机码重随失败：' + $r.Msg); return $false }
        Write-Ok $r.Msg
    }
    return $true
}

# 联机世界照房主的（high = 死亡以上的改版 Boss 世界）：之后联机启动按它加载（Get-BossMods）；空 = 不改
function Set-CoopWorld([string]$world) {
    if (-not $world) { return }
    if (-not $DryRun) {
        [System.IO.File]::WriteAllText($CoopWorldFile, ($world + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    }
    Write-Player ('联机世界：' + $(if ($world -eq 'high') { '死亡以上（改版 Boss）' } else { '普通' }) + '，和房主一样')
}

# ---------------------------------------------------------------- 联机码第三版（用户 2026-11-16「参考爬塔mod简化一下联机流程」→「联机流程改」）
# 一个码带上队友加入要的全部东西：房主「开房」生成、复制、启动，队友「加入」照着改好再启动，不用再手动填密码、选启动方式、对核对码
#（核对改成联机通道进会话自动比对，dev\dark_core\src\link.rs）。参考黄金树爬塔：联机密码第一次开房自动生成、启动前先核对版本。
# DR3|v=整合包版本|m=rand / plain（敌人随机 / 无敌人随机）|pw=联机密码（UTF-8 的 base64）|w=high / low（世界）|sc=Seamless 的规则（键=值,…）
#    敌人随机的再加 |em=精英倍数|bp=普通位置出头目|ps=敌人预设种子|nat=自然精英比例|o=随机器的选项和种子（最后一项，里面有空格）
# 码里有联机密码：只发给队友；启动器日志里只打出去掉密码的（Hide-CoopSecret），诊断包里也去掉（Remove-CoopSecret）。DR2 / DR1 照收（不带密码）
$CoopRuleKeys = @('allow_summons', 'boss_damage_scaling', 'boss_health_scaling', 'boss_posture_scaling', 'death_debuffs',
                  'enemy_damage_scaling', 'enemy_health_scaling', 'enemy_posture_scaling')
$CoopHostModeFile = Join-Path $LauncherDir 'reroll\state\coop_host_mode.txt'
$CoopJoinCodeFile = Join-Path $LauncherDir 'reroll\state\coop_join_code.txt'
$CoopHostCodeFile = Join-Path $Paly 'dll\dark_core\coop_host_code.txt'

# 本包的版本（字符串）。不能叫 Get-PackVersion：randomize.ps1 里有同名的（读指定整合包的版本，返回 [version]），
# 后定义的会盖掉它，「沿用旧版本的敌人随机结果」就读成本包的版本、按字符串和 0.7 比，判成太旧（2026-11-17 测试包）
function Get-CoopPackVersion {
    $vp = Join-Path $LauncherDir 'version.txt'
    if (Test-Path -LiteralPath $vp) { return ([System.IO.File]::ReadAllText($vp)).Trim() }
    return ''
}

# ersc_settings.ini：路径、有没有 BOM、内容
function Read-ErscIni($Ersc) {
    $ini = Join-Path $Ersc.DirectoryName 'ersc_settings.ini'
    $bytes = [System.IO.File]::ReadAllBytes($ini)
    $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    return @{ Path = $ini; Bom = $bom; Text = [System.IO.File]::ReadAllText($ini) }
}

# ini 里这一项改成 $Value；没有就加在 [$Section] 下面（没有这一节就加在最后）
function Set-IniValue([string]$Text, [string]$Key, [string]$Value, [string]$Section) {
    $m = Get-IniMatch $Text $Key
    if ($m) {
        $g = $m.Groups[1]
        $old = $g.Value
        $keep = $old.Substring($old.TrimEnd().Length)      # 值后面、分号注释前的空格留着
        return $Text.Substring(0, $g.Index) + $Value + $keep + $Text.Substring($g.Index + $g.Length)
    }
    $sm = [regex]::Match($Text, '(?im)^[ \t]*\[' + [regex]::Escape($Section) + '\][ \t]*(?=\r?$)')
    if ($sm.Success) {
        $at = $sm.Index + $sm.Length
        return $Text.Substring(0, $at) + "`r`n" + $Key + ' = ' + $Value + $Text.Substring($at)
    }
    return $Text.TrimEnd() + "`r`n`r`n[" + $Section + "]`r`n" + $Key + ' = ' + $Value + "`r`n"
}

# Seamless 的规则（不含密码）：「键=值」数组，兼容档案和联机码共用
function Get-ErscRules($Ersc) {
    $rules = @()
    try { $txt = (Read-ErscIni $Ersc).Text } catch { return $rules }
    foreach ($k in $CoopRuleKeys) {
        $m = Get-IniMatch $txt $k
        if ($m) { $rules += ($k + '=' + $m.Groups[1].Value.Trim()) }
    }
    return $rules
}

function Get-ErscPassword($Ersc) {
    try {
        $m = Get-IniMatch (Read-ErscIni $Ersc).Text 'cooppassword'
        if ($m) { return $m.Groups[1].Value.Trim() }
    } catch { }
    return ''
}

# 16 位随机密码（去掉了容易看错的 0 O 1 l I）
function New-CoopPassword {
    $chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $b = New-Object byte[] 16
    $rng.GetBytes($b)
    return (-join ($b | ForEach-Object { $chars[$_ % $chars.Length] }))
}

# 房主：联机密码空着就生成一个写进去（原 ini 备份）；返回密码，失败返回空串
function Initialize-CoopPassword($Ersc) {
    try {
        $pw = Get-ErscPassword $Ersc
        if ($pw) { return $pw }
        $pw = New-CoopPassword
        if ($DryRun) { Write-Host '  [-DryRun] 联机密码是空的，真的开房时会自动生成一个'; return $pw }
        $f = Read-ErscIni $Ersc
        Copy-Item -LiteralPath $f.Path -Destination ($f.Path + '.bak_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) -Force
        [System.IO.File]::WriteAllText($f.Path, (Set-IniValue $f.Text 'cooppassword' $pw 'PASSWORD'), (New-Object System.Text.UTF8Encoding($f.Bom)))
        Write-Player '联机密码是空的，自动生成了一个（联机码里带着，队友加入时自动填上；原设置已备份）。'
        return $pw
    } catch {
        Write-Err ('写不了联机密码：' + $_.Exception.Message)
        return ''
    }
}

# 联机码里的密码换成「去掉了」（日志、诊断包用）
function Hide-CoopSecret([string]$Text) {
    $t = [regex]::Replace($Text, '(DR3\|[^\r\n]*?\|pw=)[A-Za-z0-9+/=]*', '${1}（去掉了）')
    return [regex]::Replace($t, 'DR4z[A-Za-z0-9_\-]{8,}', 'DR4z（去掉了）')      # 压缩过的（coopcode.ps1）解开就是带密码的原文
}

# 诊断包：文字文件里的联机码去掉密码
function Remove-CoopSecret([string]$Dir) {
    foreach ($f in @(Get-ChildItem -LiteralPath $Dir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @('.log', '.txt', '.ini', '.json') })) {
        try {
            $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
            $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
            $t = [System.IO.File]::ReadAllText($f.FullName)
            $n = Hide-CoopSecret $t
            if ($n -ne $t) { [System.IO.File]::WriteAllText($f.FullName, $n, (New-Object System.Text.UTF8Encoding($bom))) }
        } catch { }
    }
}

# 生成联机码（$Rand = 敌人随机）：@{ Ok; Code; Msg; World; Info }
function Get-CoopCode3([bool]$Rand, $Ersc) {
    $pw = Get-ErscPassword $Ersc
    if (-not $pw) { return @{ Ok = $false; Msg = '联机密码是空的：点「开房」会自动生成一个。' } }
    $world = if (@((Get-BossMods $true).Keys).Count) { 'high' } else { 'low' }
    $f = @('DR3', ('v=' + (Get-CoopPackVersion)), ('m=' + $(if ($Rand) { 'rand' } else { 'plain' })),
           ('pw=' + [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($pw))), ('w=' + $world), ('sc=' + (@(Get-ErscRules $Ersc) -join ',')))
    $info = $null
    if ($Rand) {
        $c2 = Get-CoopCode
        if (-not $c2.Ok) { return $c2 }
        $p = $c2.Code.Split('|')      # DR2|预设种子|自然精英比例|精英倍数|普通位置出头目|世界|选项（选项里不会有 |）
        $f += @(('em=' + $p[3]), ('bp=' + $p[4]), ('ps=' + $p[1]), ('nat=' + $p[2]), ('o=' + ($p[6..($p.Length - 1)] -join '|')))
        $info = $c2.Info
    }
    return @{ Ok = $true; Code = ($f -join '|'); World = $world; Info = $info }
}

# 读联机码第三版：@{ Ok; Msg; Version; Rand; Password; World; Rules; Em; Bp; Fixed }
function Read-CoopCode3([string]$Text) {
    $t = ([string]$Text -replace '\s+', ' ').Trim()
    if (-not $t.StartsWith('DR3|')) { return @{ Ok = $false; Msg = '不是 DR3| 开头' } }
    $parts = $t.Split('|')
    $h = @{}
    for ($i = 1; $i -lt $parts.Length; $i++) {
        $kv = $parts[$i]
        $eq = $kv.IndexOf('=')
        if ($eq -lt 1) { continue }
        $k = $kv.Substring(0, $eq)
        $v = $kv.Substring($eq + 1)
        if ($k -eq 'o') {
            if ($i -lt $parts.Length - 1) { $v = (@($v) + $parts[($i + 1)..($parts.Length - 1)]) -join '|' }
            $h[$k] = $v
            break
        }
        $h[$k] = $v
    }
    if ($h['m'] -notin @('rand', 'plain')) { return @{ Ok = $false; Msg = '启动方式看不懂（m=）' } }
    if ($h['w'] -notin @('high', 'low')) { return @{ Ok = $false; Msg = '世界看不懂（w=）' } }
    $pw = ''
    try { $pw = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$h['pw'])) } catch { }
    if (-not $pw -or $pw -match '[\r\n;]') { return @{ Ok = $false; Msg = '联机密码看不懂（pw=），码可能没复制完整' } }
    $rules = @(([string]$h['sc']).Split(',') | Where-Object { $_ -match '^[a-z_]+=-?[0-9]+$' })
    $r = @{ Ok = $true; Msg = ''; Version = [string]$h['v']; Rand = ($h['m'] -eq 'rand'); Password = $pw; World = $h['w']; Rules = $rules
            Em = $null; Bp = $null; Fixed = $null }
    if ($r.Rand) {
        if ([string]$h['ps'] -notmatch '^\d+$' -or [string]$h['nat'] -notmatch '^[-0-9=.,]+$' -or [string]$h['em'] -notmatch '^[0-9.]+$' -or
            [string]$h['bp'] -notmatch '^[0-9.]+$' -or [string]$h['o'] -notmatch '(?:^|\s)seed:\d+') {
            return @{ Ok = $false; Msg = '敌人随机的部分不完整，码可能没复制完整' }
        }
        $r.Em = [double]::Parse($h['em'], $CoopInv)
        $r.Bp = [double]::Parse($h['bp'], $CoopInv)
        $r.Fixed = @{ PresetSeed = $h['ps']; Nat = $h['nat']; Options = (Get-OptionKey $h['o']) }
    }
    return $r
}

# 队友：Seamless 的联机密码和规则照房主的（不一样才改；原 ini 备份）
function Set-ErscFromCode($Ersc, $C) {
    try {
        $f = Read-ErscIni $Ersc
        $t = $f.Text
        $what = @()
        if ((Get-ErscPassword $Ersc) -cne $C.Password) { $t = Set-IniValue $t 'cooppassword' $C.Password 'PASSWORD'; $what += '联机密码' }
        $ruleChanged = $false
        foreach ($rule in $C.Rules) {
            $eq = $rule.IndexOf('=')
            $k = $rule.Substring(0, $eq)
            $v = $rule.Substring($eq + 1)
            if ($CoopRuleKeys -notcontains $k) { continue }
            $m = Get-IniMatch $t $k
            if (-not $m -or $m.Groups[1].Value.Trim() -ne $v) {
                $t = Set-IniValue $t $k $v $(if ($k -in @('allow_summons', 'death_debuffs')) { 'GAMEPLAY' } else { 'SCALING' })
                $ruleChanged = $true
            }
        }
        if ($ruleChanged) { $what += '随人数加强等规则' }
        if (-not $what) { Write-Host '  Seamless Co-op 设置已经和房主一样'; return $true }
        if ($DryRun) { Write-Host ('  [-DryRun] Seamless Co-op 设置会照房主的改：' + ($what -join '、')); return $true }
        Copy-Item -LiteralPath $f.Path -Destination ($f.Path + '.bak_coop_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) -Force
        [System.IO.File]::WriteAllText($f.Path, $t, (New-Object System.Text.UTF8Encoding($f.Bom)))
        Write-Player ('Seamless Co-op 设置照房主的改了：' + ($what -join '、') + '（原设置已备份）')
        return $true
    } catch {
        Write-Err ('改不了 Seamless Co-op 的设置：' + $_.Exception.Message)
        return $false
    }
}

# 复制联机码到剪贴板，告诉房主发给队友（日志里只打去掉密码的；复制失败才把完整的打出来让玩家手动复制）
function Copy-CoopCode($C) {
    $ok = $true
    $short = Compress-CoopCode $C.Code      # 无损压缩成 DR4z 开头的一串（coopcode.ps1）
    try { Set-Clipboard -Value $short } catch { $ok = $false }
    $about = '（' + $(if ($C.Info) { '敌人随机，做于 ' + $C.Info.Time.ToString('yyyy-MM-dd HH:mm') } else { '无敌人随机' }) + '；世界：' +
             $(if ($C.World -eq 'high') { '死亡以上' } else { '普通' }) + '）'
    if ($ok) {
        Write-Player ('联机码已复制到剪贴板' + $about + '：发给队友，队友复制后在启动器「联机」里点「加入」。码里有联机密码，只发给队友。')
        Write-Host ('  ' + (Hide-CoopSecret $C.Code))
    } else {
        Write-Player ('复制到剪贴板失败，手动复制下面这一行发给队友' + $about + '（里面有联机密码，只发给队友）：')
        Write-Player $short
    }
}

# 复制联机码（不启动）：按上次开房的方式（没开过房按敌人随机）
function Invoke-CoopCodeAction {
    Write-Head '复制联机码'
    $ersc = Find-Ersc
    if (-not $ersc) { Write-Err ('没找到 Seamless Co-op。把它压缩包里的 SeamlessCoop 文件夹整个放进 ' + $UserDllDir + '（变成 dll\SeamlessCoop\ersc.dll）。'); return $false }
    $rand = $true
    if (Test-Path -LiteralPath $CoopHostModeFile) { $rand = ([System.IO.File]::ReadAllText($CoopHostModeFile)).Trim() -ne 'plain' }
    if ($rand) { $rs = Get-RandomizerStatus; if (-not $rs.Ok) { Write-Err $rs.Msg; return $false } }
    if (-not (Initialize-CoopPassword $ersc)) { return $false }
    $c = Get-CoopCode3 $rand $ersc
    if (-not $c.Ok) { Write-Err $c.Msg; return $false }
    Copy-CoopCode $c
    return $true
}

# 联机开房：没密码就生成、联机码复制到剪贴板、联机启动
function Invoke-CoopHost([bool]$Rand) {
    Write-Head ('联机开房 · ' + $(if ($Rand) { '敌人随机' } else { '无敌人随机' }))
    $ersc = Find-Ersc
    if (-not $ersc) { Write-Err ('没找到 Seamless Co-op。把它压缩包里的 SeamlessCoop 文件夹整个放进 ' + $UserDllDir + '（变成 dll\SeamlessCoop\ersc.dll；整合包不带 Seamless Co-op，要自己下载）。'); return $false }
    if ($Rand) { $rs = Get-RandomizerStatus; if (-not $rs.Ok) { Write-Err $rs.Msg; return $false } }
    # 世界：开房时选了（图形界面问的，-BossWorld high|low）就记下来，联机启动、联机码、标题封面都按它；
    # 没选（Boss 改版没开）就按自己上次玩的联机角色，以前当队友加入时照别人的码记下的去掉
    if ($BossWorld -in @('high', 'low')) {
        if (-not $DryRun) { [System.IO.File]::WriteAllText($CoopWorldFile, ($BossWorld + "`n"), (New-Object System.Text.UTF8Encoding($false))) }
        Write-Player ('联机世界：' + $(if ($BossWorld -eq 'high') { '死亡以上（改版 Boss）' } else { '普通' }) + '（开房时选的，队友加入时照联机码用同一个）')
    } elseif (Test-Path -LiteralPath $CoopWorldFile) {
        if (-not $DryRun) { Remove-Item -LiteralPath $CoopWorldFile -Force -ErrorAction SilentlyContinue }
        Write-Host '  以前加入队友时记下的联机世界去掉了：开房按自己上次玩的联机角色定'
    }
    if (-not (Initialize-CoopPassword $ersc)) { return $false }
    $c = Get-CoopCode3 $Rand $ersc
    if (-not $c.Ok) { Write-Err $c.Msg; return $false }
    if (-not $DryRun) {
        try { [System.IO.File]::WriteAllText($CoopHostModeFile, $(if ($Rand) { 'rand' } else { 'plain' }), (New-Object System.Text.UTF8Encoding($false))) } catch { }
    }
    Copy-CoopCode $c
    Invoke-Launch $Rand $true
    return $true
}

# 加入队友：找联机码（给的 / 剪贴板 → 联机时联机通道存下的房主的码、上次加入用的码，新的先），照着改好再联机启动
function Invoke-CoopJoin([string]$Text) {
    Write-Head '加入队友的联机'
    $ersc = Find-Ersc
    if (-not $ersc) { Write-Err ('没找到 Seamless Co-op。把它压缩包里的 SeamlessCoop 文件夹整个放进 ' + $UserDllDir + '（变成 dll\SeamlessCoop\ersc.dll；整合包不带 Seamless Co-op，要自己下载）。'); return $false }
    $cands = @()
    if ($Text) { $cands += , @('给的', $Text) }
    else { try { $cands += , @('剪贴板里的', [string](Get-Clipboard -Raw)) } catch { } }
    $files = @(@{ P = $CoopHostCodeFile; N = '上次联机时房主发来的' }, @{ P = $CoopJoinCodeFile; N = '上次加入时用的' } |
               Where-Object { Test-Path -LiteralPath $_.P } | Sort-Object { (Get-Item -LiteralPath $_.P).LastWriteTime } -Descending)
    foreach ($f in $files) { $cands += , @($f.N, [System.IO.File]::ReadAllText($f.P)) }
    $code = ''; $from = ''
    foreach ($c in $cands) {
        $t = ([string]$c[1] -replace '\s+', ' ').Trim()
        if ($t -match '^DR(?:[123]\||4)') { $code = $t; $from = $c[0]; break }
    }
    if (-not $code) { Write-Err '没找到联机码：先复制房主发来的那一串（DR4 开头），再点「加入」。'; return $false }
    if ($code.StartsWith('DR4')) {
        $plain = Expand-CoopCode $code
        if (-not $plain) { Write-Err ($from + '联机码解不开（多半没复制完整）：让房主重新点「复制联机码」发一次。'); return $false }
        $code = $plain
    }
    if (-not $code.StartsWith('DR3|')) {
        # 旧版的码（DR2 / DR1）：不带联机密码和启动方式，按敌人随机
        Write-Warn '这是旧版的联机随机码（不带联机密码）：两人的联机密码要自己填一样的（「工具与设置」→「联机设置」）。'
        if (-not (Test-ErscSettings $ersc)) { return $false }
        if (-not (Invoke-CoopImport $code)) { return $false }
        Invoke-Launch $true $true
        return $true
    }
    $c = Read-CoopCode3 $code
    if (-not $c.Ok) { Write-Err ($from + '联机码不对：' + $c.Msg + '。让房主重新点「复制联机码」发一次。'); return $false }
    $mine = Get-CoopPackVersion
    if ($c.Version -and $mine -and $c.Version -ne $mine) {
        Write-Err ('房主的整合包是 ' + $c.Version + '，你的是 ' + $mine + '：两人先更新成同一个版本再联机。')
        return $false
    }
    Write-Player ('按' + $from + '联机码加入：' + $(if ($c.Rand) { '敌人随机' } else { '无敌人随机' }) + '，世界：' + $(if ($c.World -eq 'high') { '死亡以上' } else { '普通' }))
    if (-not (Set-ErscFromCode $ersc $c)) { return $false }
    if ($c.Rand) {
        $rs = Get-RandomizerStatus
        if (-not $rs.Ok) { Write-Err $rs.Msg; return $false }
        if (-not (Import-CoopEnemy $c.Fixed $c.Em $c.Bp $c.World)) { return $false }
    } else {
        Set-CoopWorld $c.World
    }
    if (-not $DryRun) {
        try { [System.IO.File]::WriteAllText($CoopJoinCodeFile, ($code + "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
    }
    Invoke-Launch $c.Rand $true
    return $true
}

# ---------------------------------------------------------------- Boss 模组（只在高难度加载，dev\boss_mods\README.md）
# settings.json 的 boss_mods：mode = auto（按角色难度：图形界面启动时，存档里有「死亡」以上的角色就问这次用哪种难度的世界，-BossWorld high|low；
# 没给（命令行、联机）按上次玩的角色，dark_core 记在 角色记录\boss_mode.txt，「死亡」以上才加载）/ on（一直加载）/ off（不加载，
# 和整合前完全一样）；mods = 要整合哪些（键 = launcher\reroll\data\bossmods 下的文件夹）。
# 加载 = 角色层文件（data\bossmods\<键>\files：动作 / 行为 / 模型 / AI / 音频）挂成 YAFSML 最底层（别的包都盖在它上面）+ 重随带 --boss-mods 写参数和台词。
# 游戏里换不了：Boss 的动作和 AI 是读图时从硬盘读的，只能启动时定。每次启动把这次的决定写给 dark_core（dll\dark_core\bossmods.txt），
# 读进来的角色和这次对不上时它用原版提示说要重启；off 或者一个都没开时删掉这个文件，dark_core 什么都不做。
$BossModsDir = Join-Path $LauncherDir 'reroll\data\bossmods'
$BossModeDef = Join-Path $Paly 'dll\dark_core\bossmods.txt'

function Get-BossMods([bool]$Coop = $false) {
    $r = [pscustomobject]@{ Keys = @(); Want = @(); Mode = 'off'; Why = '' }
    $sp = Join-Path $LauncherDir 'reroll\settings.json'
    try { $s = [System.IO.File]::ReadAllText($sp) | ConvertFrom-Json } catch { $r.Why = '读不了设置'; return $r }
    $bm = $s.boss_mods
    if (-not $bm) { return $r }
    $r.Mode = [string]$bm.mode
    $want = @()
    if ($bm.mods) {
        foreach ($p in $bm.mods.PSObject.Properties) {
            if (-not $p.Name.StartsWith('_') -and $p.Value -eq $true -and (Test-Path -LiteralPath (Join-Path $BossModsDir ($p.Name + '\files')))) { $want += $p.Name }
        }
    }
    $r.Want = $want
    if (-not $want.Count -or $r.Mode -eq 'off') { $r.Why = '设置里关着'; return $r }
    if ($r.Mode -eq 'on') { $r.Keys = $want; $r.Why = '设置成一直加载'; return $r }
    if (-not $Coop -and $BossWorld -eq 'high') { $r.Keys = $want; $r.Why = '启动时选了死亡以上难度'; return $r }
    if (-not $Coop -and $BossWorld -eq 'low') { $r.Why = '启动时选了普通难度'; return $r }
    # 联机：开房时选的世界，或者加入时照房主的联机码记下的（联机计划 13.3 C9、13.8）
    if ($Coop -and (Test-Path -LiteralPath $CoopWorldFile)) {
        $w = ([System.IO.File]::ReadAllText($CoopWorldFile)).Trim()
        if ($w -eq 'high') { $r.Keys = $want; $r.Why = '联机世界（开房时选的 / 照房主的联机码）：死亡以上'; return $r }
        if ($w -eq 'low') { $r.Why = '联机世界（开房时选的 / 照房主的联机码）：普通'; return $r }
    }
    $dir = if ($Coop) { Join-Path $RngRecordDir '联机' } else { $RngRecordDir }
    $rec = Join-Path $dir 'boss_mode.txt'
    if (-not (Test-Path -LiteralPath $rec)) { $r.Why = '还不知道角色难度（进一次游戏读档后就记下了）'; return $r }
    $kv = @{}
    foreach ($l in @(Get-Content -LiteralPath $rec -Encoding UTF8)) { $i = $l.IndexOf("`t"); if ($i -gt 0) { $kv[$l.Substring(0, $i)] = $l.Substring($i + 1) } }
    $who = '上次玩的角色「' + $kv['name'] + '」'
    if ($kv['high'] -eq '1') { $r.Keys = $want; $r.Why = $who + '是「死亡」以上' } else { $r.Why = $who + '不是「死亡」以上' }
    return $r
}

# 标题封面用哪张：这次是死亡以上的世界就是 hard。判断同上面的 Boss 模组（启动时选的 -BossWorld，没给就看上次玩的角色），但不看 boss_mods 的设置：关了 Boss 模组也一样换
function Get-TitleCover([bool]$Coop = $false) {
    if (-not $Coop -and $BossWorld -eq 'high') { return 'hard' }
    if (-not $Coop -and $BossWorld -eq 'low') { return 'normal' }
    if ($Coop -and (Test-Path -LiteralPath $CoopWorldFile)) {
        $w = ([System.IO.File]::ReadAllText($CoopWorldFile)).Trim()
        if ($w -eq 'high') { return 'hard' }
        if ($w -eq 'low') { return 'normal' }
    }
    $dir = if ($Coop) { Join-Path $RngRecordDir '联机' } else { $RngRecordDir }
    $rec = Join-Path $dir 'boss_mode.txt'
    if (-not (Test-Path -LiteralPath $rec)) { return 'normal' }
    foreach ($l in @(Get-Content -LiteralPath $rec -Encoding UTF8)) { if ($l -match '^high\t1') { return 'hard' } }
    return 'normal'
}

function Get-BossModMeta([string]$Key) {
    try { return ([System.IO.File]::ReadAllText((Join-Path $BossModsDir ($Key + '\mod.json'))) | ConvertFrom-Json) } catch { return $null }
}

function Get-BossModName([string]$Key) {
    try { $m = [System.IO.File]::ReadAllText((Join-Path $BossModsDir ($Key + '\mod.json'))) | ConvertFrom-Json; if ($m.boss.zh) { return [string]$m.boss.zh } } catch { }
    return $Key
}

function Write-BossModeDef($Bm) {
    if ($Bm.Mode -eq 'off' -or -not @($Bm.Want).Count) { Remove-Item -LiteralPath $BossModeDef -Force -ErrorAction SilentlyContinue; return }
    $t = '# 启动器每次启动写（dark_core 的 bossmode.rs 读）：auto = 按角色难度自动加载；loaded = 这次加载了没有；keys = 设置里开着的' + "`n" +
         'auto ' + $(if ($Bm.Mode -eq 'auto') { '1' } else { '0' }) + "`n" + 'loaded ' + $(if (@($Bm.Keys).Count) { '1' } else { '0' }) + "`n" +
         'keys ' + (@($Bm.Want) -join ' ') + "`n"
    try { [System.IO.File]::WriteAllText($BossModeDef, $t, (New-Object System.Text.UTF8Encoding($false))) } catch { Write-Warn ('写不了 ' + $BossModeDef + '：' + $_.Exception.Message) }
}

# ---------------------------------------------------------------- 动作：启动（$Rand = 敌人随机，在最近一次随机器输出上做；否则在原版上做）
# $Coop = 联机启动（Seamless Co-op）：加载 ersc.dll、Erd Tools 存档扩展名换成 co2、重随用联机种子和联机专用的一次性记录（见上面「联机」一节）
function Invoke-Launch([bool]$Rand, [bool]$Coop = $false) {
    foreach ($t in @($RerollTool, $ScriptsTool)) { if (-not (Test-Path -LiteralPath $t)) { Write-Err ('缺少脚本：' + $t); return } }
    $modeText = $(if ($Coop) { '联机 · ' } else { '' }) + $(if ($Rand) { '敌人随机' } else { '无敌人随机' })
    Write-Head ('启动 · ' + $modeText)
    Write-Player ('正在准备启动（' + $modeText + '）……')
    Save-PackPath   # 记下这个整合包的位置：更新到新版本后从这里沿用敌人随机结果（randomize.ps1）
    $script:ErdSaveExt = if ($Coop) { 'co2' } else { 'rng' }
    $script:CoopDll = ''
    if ($Coop) {
        $ersc = Find-Ersc
        if (-not $ersc) {
            Write-Err ('没找到 Seamless Co-op。把它压缩包里的 SeamlessCoop 文件夹整个放进 ' + $UserDllDir + '（变成 dll\SeamlessCoop\ersc.dll；整合包不带 Seamless Co-op，要自己下载）。')
            return
        }
        Write-Host ('  Seamless Co-op：' + $ersc.FullName + '（版本 ' + (Get-ErscVersion $ersc) + '）')
        if (-not (Test-ErscSettings $ersc)) { return }
        # 联机存档 2026-11-17 起叫 ER0000.rngcoop（YAFSML.ini.tpl）：还没有就从旧的 ER0000.rng.co2 复制，免得 YAFSML 从原版联机存档 ER0000.co2 复制一份新的
        if (-not $DryRun) { [void](Move-CoopSaveName) }
        $script:CoopDll = Get-YafRelPath $ersc.FullName
    }
    # Boss 模组：按上次玩的角色的难度定这次加不加载（加载的挂在最前面 = 最底层）
    $bm = Get-BossMods $Coop
    # 这次的世界用哪一份输出（各存各的，见文件开头 Set-WorldPacks）
    Set-WorldPacks ($(if ($Coop) { '_coop' } else { '' }) + $(if ($Rand) { '' } else { '_van' }) + $(if (@($bm.Keys).Count) { '_hi' } else { '' }))
    if ($Rand) {
        # 敌人随机要随机器（正式发布不带，玩家自己装；重随按位置修正要读它的数据）
        $rs = Get-RandomizerStatus
        if (-not $rs.Ok) { Write-Err $rs.Msg; return }
        if (-not $rs.Tested) { Write-Warn (Get-RandomizerUntestedMsg) }
        $latest = Get-LatestRandom
        if (-not $latest -or -not (Test-Path -LiteralPath (Join-Path $RandomDir 'regulation.bin'))) {
            if (@(Find-OldRandoms).Count) { Write-Err '还没有随机器输出。旧版本里有敌人随机结果：在「常见问题」里点「沿用旧版本的敌人随机」（敌人和之前一样），或者「一键重随敌人」重新随机化一次。' }
            else { Write-Err '还没有随机器输出。先「一键重随敌人」随机化一次。' }
            return
        }
        if ($latest.Merged) {
            Write-Err '现在的随机器输出是旧版本合并别的包做的，带着那个包的参数。先「一键重随敌人」重新随机化一次。'
            return
        }
        # 写明沿用的是哪一次（2026-11-04 用户反馈：覆盖更新后看到重随包的「种子」，以为敌人被重新随机化了）
        $ri = Get-RandomInfo $RandomDir
        Write-Host ('  敌人随机   : 沿用 ' + $latest.Time.ToString('yyyy-MM-dd HH:mm:ss') + ' 随机化的结果' + $(if ($ri -and $ri.Seed) { '（随机器种子 ' + $ri.Seed + '）' } else { '' }) +
                    '，这次没有重新随机化；要换一批敌人点「一键重随敌人」')
        Write-Player ('敌人随机：沿用 ' + $latest.Time.ToString('yyyy-MM-dd HH:mm') + ' 随机化的结果（要换一批敌人点「一键重随敌人」）')
        if (-not $latest.HasEnemy -and -not $latest.HasItem) { Write-Warn '最近一次随机化的选项里没有 enemy（敌人随机），这样启动和无敌人随机差不多。' }
        if ($latest.HasItem) { Write-Host '  物品随机   : 开着（重随认出来了：商店重抽、骨灰打乱跳过，见 dev\item_rand\物品随机兼容.md）' }
        $modLines = 'DR_Randomizer=' + $RandomDir + "`r`n" + 'DR_RerollMaps=' + $RerollMapsPack + "`r`n" + 'DR_Reroll=' + $RerollPack
        $dllLines = 'randomizer_crashfix=..\randomizer\dll\RandomizerCrashFix.dll|early'
    } else {
        $modLines = 'DR_Reroll=' + $RerollPack
        $dllLines = '; 无敌人随机：不需要额外 DLL'
    }
    $script:BossKeys = @($bm.Keys)
    $script:TitleCover = Get-TitleCover $Coop
    if (@($bm.Want).Count) {
        $names = (@($bm.Want) | ForEach-Object { Get-BossModName $_ }) -join '、'
        Write-Host ('  高难度 Boss : ' + $(if (@($bm.Keys).Count) { '加载改版（' + $names + '）' } else { '不加载（' + $names + ' 用原版）' }) + '——' + $bm.Why)
        if ($bm.Mode -eq 'auto') { Write-Player ('难度：' + $(if (@($bm.Keys).Count) { '死亡以上难度' } else { '普通难度' })) }
    }
    # 敌人随机：用高难度世界（一键重随敌人时随机器多跑的一遍，这些 Boss 留在原位；randomize.ps1 的 Invoke-RandomizeHiWorld），
    # 场地在重随 / 游戏脚本里移植上去（--boss-arena）。没有或过期（不是跟着最近这次随机化做的）就用平常的世界，Boss 不固定、只换新动作
    $script:RandWorld = $RandomDir
    $script:BossArena = @()
    if ($Rand -and @($bm.Keys).Count) {
        $need = @(); $arenaKeys = @()
        foreach ($k in @($bm.Keys)) { $m = Get-BossModMeta $k; if ($m) { $need += @($m.fixed); if ($m.arena) { $arenaKeys += $k } } }
        $hi = if ($Coop) { $null } else { Get-RandHiWorld $need }
        if ($hi) {
            $script:RandWorld = $RandomHiDir
            $script:BossArena = $arenaKeys
            $modLines = $modLines.Replace('DR_Randomizer=' + $RandomDir, 'DR_Randomizer=' + $RandomHiDir)
            Write-Host ('  敌人随机   : 用高难度世界（' + $hi.time + ' 和平常的一起随机化的，种子 ' + $hi.seed + '；整合了改版的 Boss 在原场地）')
        } elseif ($Coop) {
            Write-Warn '联机先不用高难度世界：整合了改版的 Boss 不固定在原位（只换新动作）。'
        } else {
            Write-PlayerWarn ('还没有死亡以上难度的敌人随机世界（自己打开随机器随机化的、或者之后才开了新的 Boss 模组）：部分追忆 Boss 这次不在原位。' +
                              '点「一键重随敌人」重新随机化一次就有了。')
        }
    }
    if (@($bm.Keys).Count) {
        $bossLines = @($bm.Keys | ForEach-Object { 'DR_Boss_' + $_ + '=' + (Join-Path $BossModsDir ($_ + '\files')) })
        # 场地（新阶段的事件、新加的随从 / 物件，移植到原版地图上的成品）：只在 Boss 在原位时挂 = 不开敌人随机
        if (-not $Rand) {
            $bossLines += @($bm.Keys | Where-Object { Test-Path -LiteralPath (Join-Path $BossModsDir ($_ + '\arena')) } |
                            ForEach-Object { 'DR_BossArena_' + $_ + '=' + (Join-Path $BossModsDir ($_ + '\arena')) })
        }
        $modLines = ($bossLines -join "`r`n") + "`r`n" + $modLines
    }
    $seed = $null
    $state = ''
    if ($Coop) {
        $seed = Get-CoopSeed $Rand
        if ($null -eq $seed) { return }
        $state = Join-Path (Join-Path $RngRecordDir '联机') ('once_' + $seed + '.json')
        Write-Host ('  联机种子 : ' + $seed + $(if ($Rand) { '（= 随机器的种子：两人的敌人随机一样，种子就一样）' } else { '（无敌人随机固定用这个）' }))
        Write-Host ('  一次性重随记录（联机专用）: ' + $state)
    }
    if ($DryRun) { Show-IniDry $modLines $dllLines; Write-Warn '[-DryRun] 不生成覆盖包、不启动。'; return }
    # 要覆盖游戏正在用的 out\reroll 等文件
    if (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) {
        Write-Err '游戏还在运行。先在游戏里正常退出（系统 → 退出游戏），等游戏完全关闭后再启动。'
        return
    }
    $py = Find-Python
    if (-not $py) { Write-Err ('找不到 Python 3：包里自带的 ' + (Join-Path $LauncherDir 'python') + ' 不完整，系统里也没装（python.org 装 3.8 以上即可）'); return }
    # 原版文件：没装随机器时从游戏取，先核对游戏目录的 regulation.bin 是不是原版
    $vs = Get-VanillaSource $py
    if (-not $vs) { Write-Err ('拿不到原版文件，没有启动：' + $script:VanillaErr); return }
    if ($vs.From -eq 'game') {
        Write-Host ('  原版文件 : 从游戏取（没装随机器）；regulation.bin ' + $vs.Check)
        if (-not $vs.Vanilla) { Write-PlayerWarn '游戏目录的 regulation.bin 不是整合包认识的原版：游戏更新了，或者被别的 mod 改过。被改过的话，在 Steam 里对游戏「验证游戏文件的完整性」再启动。' }
    }
    Invoke-LaunchBackup $modeText
    if (-not $Coop) {
        $seed = Get-NewGameSeed $Rand
        if ($null -ne $seed) { Write-Host ('  这次重随的种子：' + $seed) }
    }
    Write-Host ''
    # 设置、整合包、随机器输出、一次性重随记录都没变时重随沿用上次的结果（launcher\reroll\rr\reuse.py），几秒就好
    if ($Rand) { Write-Host '  正在生成重随包（没变就沿用上次的；要重做约 20 秒，刚重新随机化过约 25 秒）...' } else { Write-Host '  正在生成重随包（没变就沿用上次的；要重做约 5 秒）...' }
    Write-Player ('正在生成这一局的游戏数据（没变化时几秒就好，要重做约 ' + $(if ($Rand) { '20' } else { '5' }) + ' 秒）……')
    if (-not (Invoke-RerollGenerate $py $Rand $seed $state)) {
        Write-Err '重随失败，没有启动游戏。'
        return
    }
    [System.IO.File]::WriteAllText($WorldFile, $script:WorldSuffix)     # 状态显示、诊断包读这一份
    if ($Coop) {
        $fp = Get-CoopFingerprint $Rand $true
        if ($fp) { Write-Host ('  联机核对码：' + $fp + '（进会话后自动和队友比对，对不上时日志里写是哪一项）') }
        Write-CoopProfile $ersc $fp $Rand
    } else {
        Remove-Item -LiteralPath $CoopProfile -Force -ErrorAction SilentlyContinue
    }
    Write-BossModeDef $bm
    Write-IniFile $modLines $dllLines
    [void](Start-YafGame $modeText)
}

function Get-RerollLastText {
    $rep = Join-Path $RerollPack 'reroll_report.txt'
    if (-not (Test-Path -LiteralPath $rep)) { return '（还没有）' }
    $lines = Get-Content -LiteralPath $rep -TotalCount 3 -Encoding UTF8
    $t = ($lines | Where-Object { $_ -like '时间：*' } | Select-Object -First 1) -replace '^时间：', ''
    $s = ($lines | Where-Object { $_ -like '种子：*' } | Select-Object -First 1) -replace '^种子：', ''
    return ($t + '（种子 ' + $s + '）')
}

# ---------------------------------------------------------------- 状态显示
function Show-Status {
    $gameRoot = Resolve-GameRoot
    if ($gameRoot) { Write-Host ('  游戏路径   : ' + $gameRoot) }
    else { Write-Host '  游戏路径   : （未设置 / 有多个候选，在图形界面点「游戏路径」选择）' -ForegroundColor Yellow }
    $latest = Get-LatestRandom
    if ($latest) {
        if ($latest.Merged) { $tag = '旧版本合并别的包做的，要重新随机化' } elseif ($latest.HasEnemy) { $tag = '有敌人随机' } elseif ($latest.HasItem) { $tag = '只有物品随机' } else { $tag = '未勾选敌人随机' }
        if ($latest.HasItem -and $latest.HasEnemy) { $tag += '，含物品随机' }
        Write-Host ('  随机器输出 : ' + $latest.Time.ToString('yyyy-MM-dd HH:mm:ss') + '（' + $tag + '）')
    } else {
        Write-Host '  随机器输出 : （还没有）'
    }
    Write-Host ('  上次重随   : ' + (Get-RerollLastText))
    $rs = Get-RandomizerStatus
    Write-Host ('  随机器     : ' + $(if (-not $rs.Ok) { '没装（敌人随机要自己下载，见 ' + $RandomizerUrl + '）' } elseif ($rs.Tested) { $rs.Version } else { '版本没测过（测过的是 v0.12.2）' }))
    $ersc = Find-Ersc
    Write-Host ('  联机       : ' + $(if ($ersc) { 'Seamless Co-op ' + $ersc.FullName } else { '没放 Seamless Co-op（放进 dll\SeamlessCoop\ 才能联机启动）' }))
}


# ---------------------------------------------------------------- 一次性重随：骨灰的位置、开局装备和遗物只在第一次启动时抽一次，记在 %APPDATA%\EldenRing\DarkReforged\角色记录\once.json；
# 删掉这个文件，下次启动就会重新抽一次（之后又固定）。原文件挪进 DarkReforged\旧文件（once_<时间>.json.before_reset）留着
function Invoke-OnceReset {
    Write-Head '一键重随物品'
    [void](Move-RngLegacyFiles)
    $state = Join-Path $RngRecordDir 'once.json'
    if (-not (Test-Path -LiteralPath $state)) { Write-Ok '还没有记录，下次启动时本来就会抽。'; return }
    New-Item -ItemType Directory -Force -Path $RngOldDir | Out-Null
    $kept = Join-Path $RngOldDir ('once_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json.before_reset')
    Move-Item -LiteralPath $state -Destination $kept -Force
    Write-Ok '记录已清除。下次启动时骨灰的位置、开局装备和遗物会重新抽一次，之后再固定下来；只对之后新建的角色生效（已有角色的装备和还没捡到的骨灰不变）。'
    Write-Host ('  原来的记录：' + $kept)
}

# ---------------------------------------------------------------- 诊断包：出问题时把排查需要的东西打成一个 zip 放到桌面
# 包含：YAFSML 日志/配置、重随报告、最近的启动器运行日志、每局游戏怎么结束的（game_sessions.txt）、退出时崩溃记录、图形界面的错误、
#       各项设置、随机器日志开头和 CrashFix 日志、dll 下最近 7 天写过的各 DLL 日志（含前几次启动被覆盖掉的，dll_logs_prev；超过 1 MB 的只取最后 1 MB）、
#       系统和游戏信息（含游戏语言、CPU / 内存 / 显卡和驱动、会往游戏里注入的程序、游戏目录顶层、dll 文件清单）、
#       崩溃调用栈（crash_stack.txt，从崩溃转储里取的）、最近 7 天 Windows 里和游戏有关的崩溃记录、显卡驱动和硬件错误（gpu_events.txt）。
#       不包含存档和转储本身。以前还读系统登记的杀毒软件和 Windows Defender 的检测记录（defender.txt），用户 2026-11-14 去掉了：
#       这类查询像恶意软件的侦察，安全软件会把导出诊断包当可疑脚本拦下。
# $DumpPath：崩溃看守传进来的这次崩溃的转储，调用栈排第一个
function Invoke-Diag([string]$OutDir = '', [string]$Reason = '', [string]$DumpPath = '') {
    $ErrorActionPreference = 'Continue'
    $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
    $tmp = Join-Path $env:TEMP ('darkforge_diag_' + $ts)
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    Write-Head '导出诊断包'
    if ($Reason) { [System.IO.File]::WriteAllText((Join-Path $tmp 'crash.txt'), $Reason, (New-Object System.Text.UTF8Encoding($true))) }
    # 收集到一半出错也照样把已经收集到的打包（诊断包就是出问题时用的），错误写进 diag_error.txt
    try { $null = Save-DiagContent $tmp $DumpPath }
    catch {
        $err = '收集到一半出错，后面的内容没收集到：' + $_.Exception.Message + "`r`n" + $_.InvocationInfo.PositionMessage
        [System.IO.File]::WriteAllText((Join-Path $tmp 'diag_error.txt'), $err, (New-Object System.Text.UTF8Encoding($true)))
        Write-Warn ('收集时出错，诊断包里会缺一部分：' + $_.Exception.Message)
    }
    $dir = $OutDir
    if (-not $dir) {
        $dir = [Environment]::GetFolderPath('Desktop')
        if (-not $dir -or -not (Test-Path -LiteralPath $dir)) { $dir = $Paly }
    }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $zip = Join-Path $dir ($(if ($Reason) { 'Darkforge_崩溃诊断_' } else { 'Darkforge_诊断_' }) + $ts + '.zip')
    Remove-CoopSecret $tmp
    Compress-Archive -Path (Join-Path $tmp '*') -DestinationPath $zip -Force
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $zip) {
        Write-Ok ('诊断包已导出：' + $zip)
        Write-Host '  把这个 zip 发给帮你排查的人即可（不含存档）。'
        if (-not $NoLaunch -and -not $Reason) { try { Start-Process -FilePath 'explorer.exe' -ArgumentList ('/select,"' + $zip + '"') } catch { } }
        return $zip
    }
    Write-Err '诊断包导出失败。'
    return $null
}

# 复制一个日志到诊断包：不存在就跳过；超过 $Max 只取最后 $Max（从下一个换行开始，免得切开半个字），开头写一行说明
function Copy-LogTail([string]$Src, [string]$Dst, [int64]$Max = 1MB) {
    try {
        $it = Get-Item -LiteralPath $Src -ErrorAction Stop
        New-Item -ItemType Directory -Force -Path (Split-Path $Dst -Parent) | Out-Null
        if ($it.Length -le $Max) { Copy-Item -LiteralPath $it.FullName -Destination $Dst -Force; return }
        $fs = [System.IO.File]::Open($it.FullName, 'Open', 'Read', 'ReadWrite')
        try {
            [void]$fs.Seek(-$Max, 'End')
            $buf = New-Object byte[] $Max
            $n = $fs.Read($buf, 0, $buf.Length)
        } finally { $fs.Dispose() }
        $start = [Array]::IndexOf($buf, [byte]10) + 1
        $head = [System.Text.Encoding]::UTF8.GetBytes('（原文件 ' + [Math]::Round($it.Length / 1MB, 1) + ' MB，这里只取了最后 ' + [Math]::Round($Max / 1MB, 1) + ' MB）' + "`r`n")
        $out = [System.IO.File]::Create($Dst)
        try { $out.Write($head, 0, $head.Length); $out.Write($buf, $start, $n - $start) } finally { $out.Dispose() }
    } catch { }
}

# 诊断包的内容：都写进 $tmp
function Save-DiagContent([string]$tmp, [string]$DumpPath) {
    $ErrorActionPreference = 'Continue'
    # 日志超过 1 MB 的只取最后 1 MB（最近几次启动），开头写一行说明
    $copy = @(
        @($RandomLog, 'YAFSML.log'), @($YafIni, 'YAFSML.ini'),
        @((Join-Path $RerollPack 'reroll_report.txt'), 'reroll_report.txt'), @((Join-Path $RerollPack 'features.json'), 'reroll_features.json'),
        @($GamePathFile, 'game_path.txt'),
        @((Join-Path $LauncherDir 'reroll\settings.json'), 'reroll_settings.json'),
        @((Join-Path $RandomDir 'config_eldenringrandomizer.toml'), 'randomizer_config.toml'),
        @((Join-Path $RandomDir 'dll\RandomizerCrashFix_log.txt'), 'RandomizerCrashFix_log.txt'),
        @($UserIniPath, 'YAFSML自定义.ini')
    )
    foreach ($c in $copy) { Copy-LogTail $c[0] (Join-Path $tmp $c[1]) }
    # 启动器：最近 10 次运行日志，每局游戏怎么结束的（game_sessions.txt），退出时崩溃的记录，图形界面自己出的错
    $logDir = Join-Path $LauncherDir 'logs'
    if (Test-Path -LiteralPath $logDir) {
        $dst = Join-Path $tmp 'launcher_logs'
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Get-ChildItem -LiteralPath $logDir -Filter '*.log' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 10 |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dst -Force }
        foreach ($n in @('game_sessions.txt', 'exit_crashes.txt', 'gui_errors.txt', 'save_ops.txt')) { Copy-LogTail (Join-Path $logDir $n) (Join-Path $dst $n) }
    }
    # dll\ 下各 DLL 自己的日志（dark_lock / dark_sell / dark_wings / dark_core 不工作时原因写在这里）、难度档位表、庆典油脂参数、飞行参数、锁定名单，按原来的子文件夹放；
    # 角色记录（%APPDATA%\EldenRing\DarkReforged\角色记录：DLL 记的装备配方、锁定名单等，一次性重随的 once.json）放 player_records\，联机的在 player_records\联机\
    foreach ($f in @(Get-RngRecordFiles)) { Copy-RngRecord $f (Join-Path $tmp 'player_records') }
    # 联机：Seamless Co-op 的配置（联机密码去掉）
    $ersc = Find-Ersc
    if ($ersc) {
        try {
            $t = [System.IO.File]::ReadAllText((Join-Path $ersc.DirectoryName 'ersc_settings.ini'))
            $t = [regex]::Replace($t, '(?im)^([ \t]*cooppassword[ \t]*=)[^\r\n]*', '$1 （诊断包里去掉了）')
            [System.IO.File]::WriteAllText((Join-Path $tmp 'ersc_settings.ini'), ('; 位置：' + $ersc.FullName + "`r`n" + $t), (New-Object System.Text.UTF8Encoding($true)))
        } catch { }
    }
    # 日志只要最近 7 天写过的（不再写的旧调试日志、幻化插件以前每天的日志不要）
    if (Test-Path -LiteralPath $UserDllDir) {
        $dllFiles = @(Get-ChildItem -LiteralPath $UserDllDir -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { ($_.Extension -eq '.log' -and $_.LastWriteTime -gt (Get-Date).AddDays(-7)) -or
                           $_.Name -in @('lock_items.txt', 'difficulty_tiers.txt', 'festive.txt', 'dark_wings.ini') })
        foreach ($f in $dllFiles) {
            Copy-LogTail $f.FullName (Join-Path (Join-Path $tmp 'dll_logs') $f.FullName.Substring($UserDllDir.Length).TrimStart('\'))
        }
    }
    if (Test-Path -LiteralPath $RunLogDir) {
        $dst = Join-Path $tmp 'dll_logs_prev'
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
        Get-ChildItem -LiteralPath $RunLogDir -File | Sort-Object Name -Descending | Select-Object -First 20 |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dst -Force }
    }
    $latest = Get-LatestRandom
    if ($latest) {
        Get-Content -LiteralPath $latest.Log -TotalCount 80 -Encoding UTF8 | Set-Content -LiteralPath (Join-Path $tmp 'randomizer_log_head.txt') -Encoding UTF8
    }
    # 系统 / 游戏 / 整合包信息
    $info = New-Object System.Collections.Generic.List[string]
    $info.Add('导出时间：' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    try { $os = Get-CimInstance Win32_OperatingSystem; $info.Add('系统：' + $os.Caption + ' ' + $os.Version) } catch { }
    $info.Add('PowerShell：' + $PSVersionTable.PSVersion)
    $info.Add('整合包目录：' + $Paly)
    $gr = Resolve-GameRoot
    if ($gr) {
        $exe = Join-Path $gr 'Game\eldenring.exe'
        $info.Add('游戏目录：' + $gr)
        if (Test-Path -LiteralPath $exe) { $info.Add('eldenring.exe 版本：' + (Get-Item -LiteralPath $exe).VersionInfo.FileVersion) }
        # 游戏语言：Steam 版看 steamapps\appmanifest_1245620.acf（菜单文字只做了简体中文 / 英文，别的语言新加的菜单项没字）。
        # 用 .NET 取往上两级：游戏装在盘符下一级（如 E:\ELDEN）时没有上两级，Split-Path 给空串、Join-Path 抛异常，以前整个诊断包都导不出来
        $steamapps = try { [IO.Path]::GetDirectoryName([IO.Path]::GetDirectoryName($gr.TrimEnd('\'))) } catch { $null }
        $acf = if ($steamapps) { [IO.Path]::Combine($steamapps, 'appmanifest_1245620.acf') } else { $null }
        $lang = if ($acf -and (Test-Path -LiteralPath $acf)) {
            $m = Select-String -LiteralPath $acf -Pattern '"language"\s+"([^"]*)"' | Select-Object -First 1
            if ($m) { $m.Matches[0].Groups[1].Value } else { 'acf 里没写' }
        } else { '找不到 Steam 的 appmanifest（不是 Steam 版？）' }
        $info.Add('游戏语言（Steam）：' + $lang)
    } else { $info.Add('游戏目录：未设置 / 找不到') }
    $py = Find-Python
    if ($py) { $info.Add('Python：' + $py + '  ' + ((& $py --version 2>&1) -join ' ')) } else { $info.Add('Python：找不到') }
    $cache = @(Get-ChildItem -LiteralPath (Join-Path $YafDir 'cache') -Filter '*.bhd.zz' -File -ErrorAction SilentlyContinue)
    $info.Add('YAFSML 缓存文件：' + $cache.Count + ' 个')
    try { foreach ($l in @(Get-UserModSummary)) { $info.Add($l) } } catch { }
    $rs = Get-RandomizerStatus
    $info.Add('随机器：' + $(if (-not $rs.Ok) { '没装 / 用不了：' + ($rs.Msg -split "`r`n")[0] } elseif ($rs.Tested) { $rs.Version } else { '版本没测过，程序 SHA-256 ' + $script:RandExeHash.Hash }))
    if ($latest) { $info.Add('随机器输出：' + $latest.Time.ToString('yyyy-MM-dd HH:mm:ss') + '，敌人随机=' + $latest.HasEnemy + '，物品随机=' + $latest.HasItem) } else { $info.Add('随机器输出：无') }
    $once = Join-Path $RngRecordDir 'once.json'
    $info.Add('一次性重随记录：' + $(if (Test-Path -LiteralPath $once) { (Get-Item -LiteralPath $once).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss') } else { '无' }))
    $info.Add('上次重随：' + (Get-RerollLastText))
    $saves = @(Get-RngSaveFiles)
    foreach ($k in @(@('ER0000.rng', '单机'), @($RngCoopSave, '联机'))) {
        $s = @($saves | Where-Object { $_.Name -eq $k[0] })
        $info.Add('暗黑重铸' + $k[1] + '存档（' + $k[0] + '）：' + $s.Count + ' 个' + $(if ($s) { '，最后修改 ' + ($s | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss') } else { '' }))
    }
    # 改名以前的联机存档（ER0000.rng.co2，还有以前套出来的 ER0000.rng.rng.co2 这类）
    $oldCoop = @(Get-ChildItem -LiteralPath $RngSaveRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^ER0000(\.rng)+\.co2$' } })
    if ($oldCoop) { $info.Add('旧名字的联机存档：' + (($oldCoop | ForEach-Object { $_.Name + '（' + $_.LastWriteTime.ToString('MM-dd HH:mm') + '）' }) -join '、')) }
    $info.Add('Seamless Co-op：' + $(if ($ersc) { $ersc.FullName + '，版本 ' + $ersc.VersionInfo.FileVersion } else { '没放' }))
    $info.Add('联机一次性重随记录：' + @(Get-ChildItem -LiteralPath (Join-Path $RngRecordDir '联机') -Filter 'once_*.json' -File -ErrorAction SilentlyContinue).Count + ' 份')
    $gps = @(Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue)
    $info.Add('游戏正在运行：' + [bool]$gps)
    foreach ($p in $gps) {
        $st = try { $p.StartTime.ToString('yyyy-MM-dd HH:mm:ss') } catch { '未知' }
        $pp = try { $p.Path } catch { $null }
        $resp = try { $p.Responding } catch { '未知' }
        $info.Add('  进程号 ' + $p.Id + '，启动于 ' + $st + '，窗口=' + ($p.MainWindowHandle -ne [IntPtr]::Zero) + '，响应=' + $resp + '，路径=' + $pp)
    }
    try { $info.Add('电脑开机时间：' + (Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime.ToString('yyyy-MM-dd HH:mm:ss')) } catch { }
    $dumps = @(Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'CrashDumps') -Filter 'eldenring*' -File -ErrorAction SilentlyContinue)
    $info.Add('崩溃转储（%LOCALAPPDATA%\CrashDumps，未打包）：' + (($dumps | ForEach-Object { $_.Name + ' ' + $_.LastWriteTime.ToString('MM-dd HH:mm') }) -join '；'))
    # 崩溃调用栈（crash_stack.txt）：用 Python 跑 reroll\crashstack.py，从转储里取异常、寄存器、调用栈、模块清单，转储本身不打包。
    # 崩溃看守传进来的那份排第一，再按时间从新到旧给最近 7 天的；退出时的崩溃（0x1ebb809）只记一行，完整写出的最多 3 份
    $picks = @()
    if ($DumpPath -and (Test-Path -LiteralPath $DumpPath)) { $picks += (Get-Item -LiteralPath $DumpPath).FullName }
    # 联机时的转储在游戏目录 SeamlessCoop\crashdumps\reports\（Get-ErscDumps），一起按时间排
    $erscDumps = @(Get-ErscDumps (Get-Date).AddDays(-7) (Get-Date))
    if ($erscDumps) { $info.Add('Seamless Co-op 的崩溃转储（未打包）：' + (($erscDumps | ForEach-Object { $_.Name + ' ' + $_.LastWriteTime.ToString('MM-dd HH:mm') }) -join '；')) }
    $picks += @(@($dumps | Where-Object { $_.Extension -eq '.dmp' -and $_.LastWriteTime -gt (Get-Date).AddDays(-7) }) + $erscDumps |
        Sort-Object LastWriteTime -Descending | ForEach-Object { $_.FullName })
    $picks = @($picks | Select-Object -Unique | Select-Object -First 10)
    $stackOut = Join-Path $tmp 'crash_stack.txt'
    if ($picks -and $py) {
        try { & $py (Join-Path $LauncherDir 'reroll\crashstack.py') $stackOut @picks 2>&1 | Out-Null } catch { }
    }
    $info.Add('崩溃调用栈：' + $(if (Test-Path -LiteralPath $stackOut) { 'crash_stack.txt' } elseif (-not $picks) { '最近 7 天没有崩溃转储' } elseif (-not $py) { '没生成（找不到 Python）' } else { '没生成（解析出错）' }))
    # 硬件：CPU / 内存 / 显卡（型号、驱动版本和日期、显存、当前分辨率）；游戏在 Windows 图形设置里指定的显卡；硬件加速 GPU 计划
    try {
        $cpu = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
        $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        $info.Add('CPU：' + ([string]$cpu.Name).Trim() + '（' + $cpu.NumberOfLogicalProcessors + ' 线程）；内存：' + [Math]::Round($cs.TotalPhysicalMemory / 1GB, 1) + ' GB')
    } catch { }
    # 显存：Win32_VideoController 的 AdapterRAM 最多到 4 GB，先从显卡驱动的注册表项里找真实大小
    $vram = @{}
    foreach ($k in @(Get-ChildItem -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}' -ErrorAction SilentlyContinue)) {
        try {
            $p = Get-ItemProperty -LiteralPath $k.PSPath -ErrorAction Stop
            if ($p.DriverDesc -and $p.'HardwareInformation.qwMemorySize') { $vram[[string]$p.DriverDesc] = [double]$p.'HardwareInformation.qwMemorySize' }
        } catch { }
    }
    try {
        foreach ($g in @(Get-CimInstance Win32_VideoController -ErrorAction Stop)) {
            $mem = if ($vram.ContainsKey([string]$g.Name)) { $vram[[string]$g.Name] } else { [double]$g.AdapterRAM }
            $dd = try { $g.DriverDate.ToString('yyyy-MM-dd') } catch { '日期不明' }
            $res = if ($g.CurrentHorizontalResolution) { '，当前 ' + $g.CurrentHorizontalResolution + '×' + $g.CurrentVerticalResolution + ' ' + $g.CurrentRefreshRate + 'Hz' } else { '，没接显示器' }
            $info.Add('显卡：' + $g.Name + '（驱动 ' + $g.DriverVersion + '，' + $dd + '，显存约 ' + [Math]::Round($mem / 1GB, 1) + ' GB' + $res + '）')
        }
    } catch { $info.Add('显卡：读不到（' + $_.Exception.Message + '）') }
    $gpuPref = '没指定'
    try {
        $pref = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\DirectX\UserGpuPreferences' -ErrorAction Stop
        $hits = @($pref.PSObject.Properties | Where-Object { $_.Name -match '(eldenring|YAFSML)\.exe$' } | ForEach-Object { $_.Name + ' = ' + $_.Value })
        if ($hits) { $gpuPref = ($hits -join '；') + '（GpuPreference=1 省电显卡，2 高性能显卡）' }
    } catch { }
    $info.Add('Windows 图形设置里给游戏指定的显卡：' + $gpuPref)
    if (Test-Path -LiteralPath (Join-Path $UserDllDir 'souls_vision.dll')) {
        $ch = Get-EnemyInfoChoice
        $info.Add('敌人信息 mod：' + $(if ($ch -eq 'off') { '玩家关掉了，不加载' } else { '加载' }) +
                  $(if (@(Get-GpuNames).Count -ge 2) { '（双显卡）' } else { '（单显卡）' }))
    }
    $hags = try { (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' -Name HwSchMode -ErrorAction Stop).HwSchMode } catch { $null }
    $info.Add('硬件加速 GPU 计划：' + $(if ($hags -eq 2) { '开' } elseif ($hags -eq 1) { '关' } else { '默认（没设置）' }))
    # 正在运行、会往游戏里注入画面层 / 钩子的常见程序（和整合包自己的两个画面层 dark_ui、souls_vision 叠在一起时可能冲突）
    $hookers = @('RTSS', 'RTSSHooksLoader64', 'MSIAfterburner', 'Discord', 'NVIDIA Overlay', 'nvsphelper64', 'NVIDIA Share', 'GameBar',
                 'Overwolf', 'obs64', 'bdcam', 'fraps', 'Action_x64', 'Medal', 'LosslessScaling', 'SKIF', 'FPSMonitor', 'CapFrameX',
                 'GameOverlayUI', 'AMDRSServ', 'RadeonSoftware', 'ReShade')
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in $hookers -or $_.ProcessName -match 'overlay|hook' } |
        Select-Object -ExpandProperty ProcessName -Unique | Sort-Object)
    $info.Add('正在运行的画面层 / 注入类程序：' + $(if ($running) { $running -join '、' } else { '没有' }))
    $info.Add('')
    $info.Add('---- 整合包目录 ----')
    foreach ($d in (Get-ChildItem -LiteralPath $Paly -Force -ErrorAction SilentlyContinue)) { $info.Add('  ' + $d.Name) }
    # 游戏目录 Game\ 顶层：别的 mod 加载器、ReShade 之类放的 dinput8.dll / dxgi.dll 会和整合包一起被游戏加载
    if ($gr) {
        $info.Add('')
        $info.Add('---- 游戏目录 Game\ 顶层 ----')
        foreach ($f in (Get-ChildItem -LiteralPath (Join-Path $gr 'Game') -Force -ErrorAction SilentlyContinue | Sort-Object Name)) {
            if ($f.PSIsContainer) { $info.Add('  [' + $f.Name + ']') }
            else { $info.Add('  ' + $f.Name + '  ' + $f.Length + ' 字节  ' + $f.LastWriteTime.ToString('yyyy-MM-dd HH:mm')) }
        }
    }
    # dll 文件夹（和随机器自带的 dll）：DLL 被杀毒软件删掉 / 改名停用时这里能看出来；.dll 带 SHA256 前 16 位，和发布的版本对照看文件坏没坏
    foreach ($d in @(@('dll 文件夹', $UserDllDir), @('randomizer\dll', (Join-Path $RandomDir 'dll')))) {
        $info.Add('')
        $info.Add('---- ' + $d[0] + ' ----')
        foreach ($f in (Get-ChildItem -LiteralPath $d[1] -Recurse -File -Force -ErrorAction SilentlyContinue | Sort-Object FullName)) {
            $h = ''
            if ($f.Extension -eq '.dll') {
                try { $h = '  SHA256 ' + (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256 -ErrorAction Stop).Hash.Substring(0, 16).ToLower() }
                catch { $h = '  SHA256 读不了（' + $_.Exception.Message + '）' }
            }
            $info.Add('  ' + $f.FullName.Substring($d[1].Length).TrimStart('\') + '  ' + $f.Length + ' 字节  ' + $f.LastWriteTime.ToString('yyyy-MM-dd HH:mm') + $h)
        }
    }
    [System.IO.File]::WriteAllLines((Join-Path $tmp 'system.txt'), $info, (New-Object System.Text.UTF8Encoding($true)))
    # 最近 7 天的崩溃记录
    $ev = @()
    try {
        $ev = @(Get-WinEvent -FilterHashtable @{ LogName = 'Application'; StartTime = (Get-Date).AddDays(-7) } -ErrorAction Stop |
            Where-Object { $_.ProviderName -in @('Application Error', 'Windows Error Reporting', 'Application Hang') -and $_.Message -match 'eldenring|YAFSML' })
    } catch { }
    $evText = $ev | ForEach-Object { '==== ' + $_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') + '  ' + $_.ProviderName + ' ' + $_.Id + "`r`n" + $_.Message + "`r`n" }
    if (-not $evText) { $evText = '最近 7 天没有游戏相关的崩溃记录。' }
    [System.IO.File]::WriteAllText((Join-Path $tmp 'windows_crash_events.txt'), ($evText -join "`r`n"), (New-Object System.Text.UTF8Encoding($true)))
    # 显卡驱动和硬件错误（gpu_events.txt，最近 7 天）：显卡驱动超时被重置（Display 4101）、显卡驱动 / 图形内核自己记的错误、
    # 硬件错误（WHEA-Logger：CPU / 内存不稳定时会有），以及显卡出错时 Windows 生成的内核报告（LiveKernelEvent 141、117 等）
    $gx = New-Object System.Collections.Generic.List[string]
    $since7 = (Get-Date).AddDays(-7)
    $gx.Add('---- 系统日志：显卡驱动 / 图形内核 / 硬件错误（最近 7 天，最多 40 条） ----')
    try {
        $evs = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; StartTime = $since7; Level = 1, 2, 3 } -ErrorAction Stop |
            Where-Object { $_.ProviderName -match '^Display$|WHEA|nvlddmkm|amdkmdag|amdwddmg|igfx|DxgKrnl' } | Select-Object -First 40)
        foreach ($x in $evs) {
            $gx.Add('==== ' + $x.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') + '  ' + $x.ProviderName + ' ' + $x.Id)
            foreach ($ln in @(([string]$x.Message) -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 6)) { $gx.Add('  ' + $ln.Trim()) }
        }
        if (-not $evs) { $gx.Add('  没有') }
    } catch { $gx.Add('  没有 / 读不到（' + $_.Exception.Message + '）') }
    $gx.Add('')
    $gx.Add('---- 显卡内核报告 LiveKernelEvent（最近 7 天，最多 20 条） ----')
    try {
        $evs = @(Get-WinEvent -FilterHashtable @{ LogName = 'Application'; ProviderName = 'Windows Error Reporting'; Id = 1001; StartTime = $since7 } -ErrorAction Stop |
            Where-Object { $_.Message -match 'LiveKernelEvent' } | Select-Object -First 20)
        foreach ($x in $evs) {
            $gx.Add('==== ' + $x.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'))
            foreach ($ln in @(([string]$x.Message) -split "`r?`n" | Where-Object { $_ -match '^(P1|P2|P3|P4):|事件名称|Event Name' })) { $gx.Add('  ' + $ln.Trim()) }
        }
        if (-not $evs) { $gx.Add('  没有') }
    } catch { $gx.Add('  没有 / 读不到（' + $_.Exception.Message + '）') }
    [System.IO.File]::WriteAllLines((Join-Path $tmp 'gpu_events.txt'), $gx, (New-Object System.Text.UTF8Encoding($true)))
}

# ---------------------------------------------------------------- 崩溃看守：启动游戏后在后台等游戏退出，
# 查 Windows 有没有记录这个进程号的崩溃（Application Error 1000）或卡住后被关掉（Application Hang 1002），
# 有就自动导出诊断包到 崩溃诊断\（留最近 10 个）并弹窗提示；每局怎么结束的都记一行到 launcher\logs\game_sessions.txt
$CrashDir = Join-Path $Paly '崩溃诊断'

# 看守进程由包里的 pythonw 跑 spawn.py 启动：不开窗口、不继承句柄（用户 2026-11-14：隐藏窗口的 powershell 会被安全软件当可疑脚本拦）；
# 没有 Python 时照旧用隐藏窗口的 powershell
function Start-CrashWatch([int]$ProcId) {
    if ($ProcId -le 0) { return }
    $pyw = Join-Path $LauncherDir 'python\pythonw.exe'
    $spawn = Join-Path $LauncherDir 'spawn.py'
    try {
        if ((Test-Path -LiteralPath $pyw) -and (Test-Path -LiteralPath $spawn)) {
            Start-Process -FilePath $pyw -ArgumentList @('-I', ('"' + $spawn + '"'), 'launcher.ps1', '-Action', 'watch', '-GamePid', $ProcId) -WorkingDirectory $LauncherDir
            return
        }
        Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File', ('"' + $PSCommandPath + '"'), '-Action', 'watch', '-GamePid', $ProcId)
    } catch { }
}

# Seamless Co-op 自己接管崩溃（crashpad）：联机时 Windows 不记崩溃事件，%LOCALAPPDATA%\CrashDumps 里也没有转储，
# 转储写在游戏目录的 SeamlessCoop\crashdumps\reports\（ersc.dll 放在整合包 dll\ 里也一样，2026-11-02 实测）。返回这段时间里写的转储（新的在前）
function Get-ErscDumps([datetime]$From, [datetime]$To) {
    $dirs = @()
    $gr = Resolve-GameRoot
    if ($gr) { $dirs += (Join-Path $gr 'Game\SeamlessCoop\crashdumps\reports') }
    $ersc = Find-Ersc
    if ($ersc) { $dirs += (Join-Path $ersc.DirectoryName 'crashdumps\reports') }
    return @($dirs | Select-Object -Unique | ForEach-Object { Get-ChildItem -LiteralPath $_ -Filter '*.dmp' -File -ErrorAction SilentlyContinue } |
        Where-Object { $_.LastWriteTime -ge $From -and $_.LastWriteTime -le $To } | Sort-Object LastWriteTime -Descending)
}

# 一份转储是不是退出游戏时那种没影响的崩溃（reroll\crashstack.py 认 DL_PANIC 的位置，认出来就只写一行「退出游戏时的崩溃」）
function Test-ExitCrashDump([string]$Dump) {
    $ErrorActionPreference = 'Continue'
    $py = Find-Python
    if (-not $py) { return $false }
    $out = [System.IO.Path]::GetTempFileName()
    try {
        & $py -X utf8 (Join-Path $LauncherDir 'reroll\crashstack.py') $out $Dump 2>&1 | Out-Null
        return [bool](Select-String -LiteralPath $out -Pattern '退出游戏时的崩溃' -Quiet -Encoding UTF8)
    } catch { return $false } finally { Remove-Item -LiteralPath $out -Force -ErrorAction SilentlyContinue }
}

# 退出时的崩溃（没影响）记一行到 launcher\logs\exit_crashes.txt
function Add-ExitCrashLine([string]$What) {
    try {
        New-Item -ItemType Directory -Force -Path (Join-Path $LauncherDir 'logs') | Out-Null
        Add-Content -LiteralPath (Join-Path $LauncherDir 'logs\exit_crashes.txt') -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' 退出时崩溃（已忽略）：' + $What) -Encoding UTF8
    } catch { }
}

function Invoke-CrashWatch([int]$ProcId) {
    $ErrorActionPreference = 'Continue'
    $p = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if (-not $p -or $p.ProcessName -ne 'eldenring') { return }
    try { $null = $p.Handle } catch { }   # 先拿住进程句柄，退出后才读得到退出码
    $started = $p.StartTime
    # 边等边记游戏窗口最后一次还在的时间：正常退出时窗口先关、进程后结束；游戏中崩溃时窗口会留到进程结束
    $winSeen = $false
    $lastWin = Get-Date
    try {
        while (-not $p.HasExited) {
            $p.Refresh()
            if ($p.MainWindowHandle -ne [IntPtr]::Zero) { $winSeen = $true; $lastWin = Get-Date }
            Start-Sleep -Milliseconds 500
        }
    } catch { while (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 5 } }
    $ended = Get-Date
    $windowClosedFirst = $winSeen -and (($ended - $lastWin).TotalSeconds -ge 1.5)
    $exitCode = try { '0x{0:X8}' -f $p.ExitCode } catch { '读不到' }
    Start-Sleep -Seconds 8   # 等 Windows 写完崩溃记录
    # 按事件字段判断（说明文字会随系统语言变）：[0] 程序名 [3] 崩溃模块 [6] 异常码 [7] 偏移 [8] 进程号（整数）
    $ev = $null
    try {
        $ev = Get-WinEvent -FilterHashtable @{ LogName = 'Application'; ProviderName = 'Application Error'; Id = 1000; StartTime = $started } -ErrorAction Stop |
            Where-Object { $_.Properties.Count -gt 8 -and [string]$_.Properties[0].Value -ieq 'eldenring.exe' -and
                           [int64]$_.Properties[8].Value -eq $ProcId } | Select-Object -First 1
    } catch { }
    if (-not $ev) {
        # 联机（Seamless Co-op）时崩溃由它的 crashpad 接管、Windows 没有记录：看它写的转储（退出时写，看守又等了 8 秒）
        $ed = @(Get-ErscDumps $started $ended.AddSeconds(15)) | Select-Object -First 1
        if ($ed) {
            if (Test-ExitCrashDump $ed.FullName) {
                Add-GameSession $started $ended ('退出时崩溃（没影响）：DL_PANIC（Seamless Co-op 的转储 ' + $ed.Name + '）')
                Add-ExitCrashLine ('DL_PANIC（Seamless Co-op 的转储 ' + $ed.FullName + '） 进程 ' + $ProcId)
                return
            }
            $playMin = [Math]::Round(($ended - $started).TotalMinutes, 1)
            Add-GameSession $started $ended ('崩溃（Seamless Co-op 的转储 ' + $ed.Name + '，退出码 ' + $exitCode + '）')
            $reason = "游戏崩溃（联机：Seamless Co-op 接管了崩溃，Windows 没有记录，转储是它写的）`r`n退出时间：" + $ended.ToString('yyyy-MM-dd HH:mm:ss') +
                      "`r`n游戏启动后：" + $playMin + " 分钟`r`n退出码：" + $exitCode + "`r`n进程号：" + $ProcId + "`r`n转储文件：" + $ed.FullName
            Export-CrashDiag $reason $ed.FullName ('崩溃了（游戏启动后 ' + $playMin + ' 分钟，退出码 ' + $exitCode + '）')
            Ask-EnemyInfoOffAfterCrash
            return
        }
        # 卡住（无响应）后被玩家关掉：Windows 记一条 Application Hang 1002，[0] 是程序名。同一时间只有一个游戏，按时间认
        $hang = $null
        try {
            $hang = Get-WinEvent -FilterHashtable @{ LogName = 'Application'; ProviderName = 'Application Hang'; Id = 1002; StartTime = $started } -ErrorAction Stop |
                Where-Object { $_.Properties.Count -gt 0 -and [string]$_.Properties[0].Value -ieq 'eldenring.exe' } | Select-Object -First 1
        } catch { }
        # Windows 没记崩溃事件（有的电脑关掉了错误报告），但退出码是异常码（0xC…，例如 0xC0000005 内存访问错误）、窗口也不是先关的：一样算崩溃
        if (-not $hang -and $exitCode -match '^0xC' -and -not $windowClosedFirst) {
            $playMin = [Math]::Round(($ended - $started).TotalMinutes, 1)
            Add-GameSession $started $ended ('崩溃（Windows 没有崩溃记录，退出码 ' + $exitCode + '）')
            $dump = Join-Path $env:LOCALAPPDATA ('CrashDumps\eldenring.exe.' + $ProcId + '.dmp')
            $reason = "游戏崩溃（Windows 没有记录这次崩溃，可能关掉了错误报告，所以不知道崩在哪个模块）`r`n退出时间：" + $ended.ToString('yyyy-MM-dd HH:mm:ss') +
                      "`r`n游戏启动后：" + $playMin + " 分钟`r`n退出码：" + $exitCode + "`r`n进程号：" + $ProcId + "`r`n" +
                      "转储文件：" + $(if (Test-Path -LiteralPath $dump) { $dump } else { '无' })
            Export-CrashDiag $reason $dump ('崩溃了（游戏启动后 ' + $playMin + ' 分钟，退出码 ' + $exitCode + '）')
            Ask-EnemyInfoOffAfterCrash
            return
        }
        if (-not $hang) {
            Add-GameSession $started $ended ('正常退出（退出码 ' + $exitCode + '）' + $(if (-not $winSeen) { '，没出现过游戏窗口' } else { '' }))
            return
        }
        $playMin = [Math]::Round(($hang.TimeCreated - $started).TotalMinutes, 1)
        Add-GameSession $started $ended '无响应（卡住）后被关掉'
        $reason = "游戏无响应（卡住）后被关掉`r`n时间：" + $hang.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') + "`r`n游戏启动后：" + $playMin + " 分钟`r`n" +
                  "进程号：" + $ProcId + "`r`n`r`n" + $hang.Message
        Export-CrashDiag $reason '' ('卡住后被关掉了（游戏启动后 ' + $playMin + ' 分钟）')
        return
    }
    $msg = $ev.Message
    $module = [string]$ev.Properties[3].Value
    $offset = [string]$ev.Properties[7].Value
    # 退出时的崩溃不算：游戏带 mod 退出时几乎每次都在 eldenring.exe+0x1ebb809（2.7.2.0 是 +0x1ebcef9，同一处 DL_PANIC）出错
    #（存档已经写完，没有影响），或者窗口已经先关了。只记一行到日志，不弹窗、不导出诊断包
    $exitCrash = ($module -ieq 'eldenring.exe' -and $offset -match '^(0x)?0*(1ebb809|1ebcef9)$') -or $windowClosedFirst
    if ($exitCrash) {
        Add-GameSession $started $ended ('退出时崩溃（没影响）：' + $module + ' ' + $offset)
        Add-ExitCrashLine ($module + ' ' + $offset + ' 进程 ' + $ProcId + ' 窗口先关闭=' + $windowClosedFirst)
        return
    }
    $playMin = [Math]::Round(($ev.TimeCreated - $started).TotalMinutes, 1)
    Add-GameSession $started $ended ('崩溃：' + $module + ' ' + $offset + '（退出码 ' + $exitCode + '）')
    $dump = Join-Path $env:LOCALAPPDATA ('CrashDumps\eldenring.exe.' + $ProcId + '.dmp')
    $reason = "游戏崩溃`r`n时间：" + $ev.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss') + "`r`n游戏启动后：" + $playMin + " 分钟`r`n" +
              "崩溃模块：" + $module + "`r`n位置：" + $offset + "`r`n进程号：" + $ProcId + "`r`n" +
              "转储文件（约 55 MB，未打包；调用栈已经取到 crash_stack.txt 里，一般不用再发）：" + $(if (Test-Path -LiteralPath $dump) { $dump } else { '无' }) + "`r`n`r`n" + $msg
    Export-CrashDiag $reason $dump ('崩溃了（崩溃模块：' + $module + '，游戏启动后 ' + $playMin + ' 分钟）')
    Ask-EnemyInfoOffAfterCrash
}

# 每局游戏一行记进 launcher\logs\game_sessions.txt（只留最近 300 行，诊断包会带上）：什么时候开始 / 结束、玩了多久、怎么结束的
function Add-GameSession([datetime]$Start, [datetime]$End, [string]$Result) {
    try {
        $f = Join-Path $LauncherDir 'logs\game_sessions.txt'
        New-Item -ItemType Directory -Force -Path (Split-Path $f -Parent) | Out-Null
        $line = $Start.ToString('yyyy-MM-dd HH:mm:ss') + ' ~ ' + $End.ToString('HH:mm:ss') + '（' + [Math]::Round(($End - $Start).TotalMinutes, 1) + ' 分钟）  ' + $Result
        $old = @(if (Test-Path -LiteralPath $f) { [IO.File]::ReadAllLines($f, [Text.Encoding]::UTF8) })
        [IO.File]::WriteAllLines($f, [string[]](@($old | Select-Object -Last 299) + $line), (New-Object Text.UTF8Encoding($true)))
    } catch { }
}

# 崩溃 / 卡住：导出诊断包到 崩溃诊断\（留最近 10 个）并弹窗
function Export-CrashDiag([string]$Reason, [string]$Dump, [string]$What) {
    $zip = Invoke-Diag $CrashDir $Reason $Dump
    Get-ChildItem -LiteralPath $CrashDir -Filter '*.zip' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 10 | Remove-Item -Force -ErrorAction SilentlyContinue
    if ($zip) {
        $r = Show-DrDialog ("游戏刚才" + $What + "。`r`n`r`n已自动导出诊断包：`r`n" + $zip + "`r`n`r`n需要别人帮忙排查时，把这个 zip 发给对方。") `
            '暗黑重铸 · 游戏出错' @('打开所在文件夹', '关闭') 0 1 'warn'
        if ($r -eq 0) { Start-Process -FilePath 'explorer.exe' -ArgumentList ('/select,"' + $zip + '"') }
    }
}

function Show-Help {
    Write-Host '用法：双击整合包里的「启动.bat」打开图形界面。'
    Write-Host ''
    Write-Host '命令行（调试用）：'
    Write-Host '  ... -Action list                    （状态）'
    Write-Host '  ... -Action vanilla -DryRun         （只打印将写入的配置）'
    Write-Host '  ... -Action rand -DryRun'
    Write-Host '  ... -Action vanilla -NoLaunch       （生成覆盖包、写配置，不启动）'
    Write-Host '  ... -Action setgame -GamePath "D:\ELDEN RING\Game"   （设置/修改游戏路径）'
    Write-Host '  ... -Action randenemy               （一键重随敌人）'
    Write-Host '  ... -Action oncereset               （一次性重随）'
    Write-Host '  ... -Action update -UpdateZip "a.zip"  （导入离线更新包）'
    Write-Host '  ... -Action checkupdate / autoupdate  （在线检查更新 / 下载并应用更新）'
    Write-Host '  ... -Action coop / coopvanilla      （联机启动 · 敌人随机 / 无敌人随机，要先放 Seamless Co-op）'
    Write-Host '  ... -Action coopcode                （复制联机码）'
    Write-Host '  ... -Action coophost / coophostvanilla   （联机开房 · 敌人随机 / 无敌人随机）'
    Write-Host '  ... -Action coopjoin [-Code "DR3|..."]   （加入队友：不给 -Code 读剪贴板）'
    Write-Host '  ... -Action coopimport [-Code "DR1|..."]   （按联机随机码重随敌人，不给 -Code 读剪贴板）'
}

# 启动日志：PowerShell 自动加的头尾（用户名、计算机名、一长串启动命令等）对排查没用，
# 结束时换成一行（动作、开始 / 结束时间、PowerShell 和 Windows 版本）
function Compress-TranscriptLog([string]$Path) {
    try {
        $lines = [IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)
        $stars = @(for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '^\*{10,}$') { $i } })
        if ($stars.Count -lt 2) { return }
        $end = if ($stars.Count -ge 4) { $stars[$stars.Count - 2] - 1 } else { $lines.Count - 1 }
        $body = @()
        if ($end -gt $stars[1]) { $body = @($lines[($stars[1] + 1)..$end]) }
        while ($body.Count -gt 0 -and [string]::IsNullOrWhiteSpace($body[0])) { $body = @($body | Select-Object -Skip 1) }
        $head = '# ' + $Action + ' · ' + $script:LogStart.ToString('yyyy-MM-dd HH:mm:ss') + ' ~ ' + (Get-Date).ToString('HH:mm:ss') +
                ' · PowerShell ' + $PSVersionTable.PSVersion + ' · Windows ' + [Environment]::OSVersion.Version
        [IO.File]::WriteAllLines($Path, [string[]](@($head) + $body), (New-Object Text.UTF8Encoding($true)))
    } catch { }
}

# ---------------------------------------------------------------- 入口
# 每次运行的完整输出（含重随的 Python 输出）存到 launcher\logs\，只留最近 30 份；导出诊断包时会带上
$script:Transcribing = $false
if ($Action -notin @('help', 'list', 'diag', 'watch')) {
    try {
        $logDir = Join-Path $LauncherDir 'logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        Get-ChildItem -LiteralPath $logDir -Filter '*.log' -File | Sort-Object LastWriteTime -Descending | Select-Object -Skip 29 |
            Remove-Item -Force -ErrorAction SilentlyContinue
        $script:LogStart = Get-Date
        $script:LogPath = Join-Path $logDir ($script:LogStart.ToString('yyyyMMdd_HHmmss_fff') + '_' + $Action + '.log')
        Start-Transcript -Path $script:LogPath -Force | Out-Null
        $script:Transcribing = $true
    } catch { }
}
try {
    switch ($Action) {
        'list'       { Write-Head '暗黑重铸 状态'; Show-Status }
        'setgame'    {
            if ($GamePath) {
                $root = Test-NormalizeGameRoot $GamePath
                if (-not $root) { Write-Err ('路径无效（需要包含 Game\eldenring.exe）：' + $GamePath); exit 1 }
                Save-GameRoot $root
            } else {
                [void](Set-GameRootInteractive)
            }
        }
        'vanilla'    { Invoke-Launch $false }
        'rand'       { Invoke-Launch $true }
        'coop'       { Invoke-Launch $true $true }
        'coopvanilla' { Invoke-Launch $false $true }
        'coopcode'   { $script:ExitCode = $(if (Invoke-CoopCodeAction) { 0 } else { 1 }) }
        'coopimport' { $script:ExitCode = $(if (Invoke-CoopImport $Code) { 0 } else { 1 }) }
        'coophost'   { $script:ExitCode = $(if (Invoke-CoopHost $true) { 0 } else { 1 }) }
        'coophostvanilla' { $script:ExitCode = $(if (Invoke-CoopHost $false) { 0 } else { 1 }) }
        'coopjoin'   { $script:ExitCode = $(if (Invoke-CoopJoin $Code) { 0 } else { 1 }) }
        'randenemy'  { $script:ExitCode = $(if (Invoke-RandEnemyAction) { 0 } else { 1 }) }    # 明确的退出码：图形界面靠它决定接不接着启动
        'randhi'     { $script:ExitCode = $(if (Invoke-RandHiAction) { 0 } else { 1 }) }       # 只补做高难度世界（Boss 模组）
        'carryrand'  { $script:ExitCode = $(if (Invoke-CarryRandom $FromPack) { 0 } else { 1 }) }
        'randomizer' { Invoke-Randomizer }
        'diag'       { [void](Invoke-Diag) }
        'watch'      {   # 看守在隐藏窗口里跑、不写运行日志：自己出错时记一行到 game_sessions.txt
            try { Invoke-CrashWatch $GamePid } catch { $t = Get-Date; Add-GameSession $t $t ('崩溃看守自己出错（这一局怎么结束的没记下来）：' + $_.Exception.Message) }
        }
        'oncereset'  { Invoke-OnceReset }
        'update'     { $script:ExitCode = $(if (Invoke-Update $UpdateZip) { 0 } else { 1 }) }
        'checkupdate' { $script:ExitCode = $(if (Invoke-UpdatePy @('--check')) { 0 } else { 1 }) }
        'autoupdate' { $script:ExitCode = $(if (Invoke-UpdatePy @('--fetch')) { 0 } else { 1 }) }
        'help'       { Show-Help }
    }
} catch {
    Write-Err ('运行出错：' + $_.Exception.Message)
    Write-Host ('  位置：' + $_.InvocationInfo.PositionMessage) -ForegroundColor DarkGray
    if ($script:Transcribing) { try { Stop-Transcript | Out-Null } catch { }; Compress-TranscriptLog $script:LogPath }
    exit 1
}
if ($script:Transcribing) { try { Stop-Transcript | Out-Null } catch { }; Compress-TranscriptLog $script:LogPath }
if ($null -ne $script:ExitCode) { exit $script:ExitCode }
