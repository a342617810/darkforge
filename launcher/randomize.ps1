# Dark Reforged · 一键重随敌人（启动器和图形界面共用，用 . 引入；需要先定义 $LauncherDir / $RandomDir）
# 随机器（EldenRingRandomizer.exe，Avalonia 版）没有命令行模式，只能操作它的窗口：
#   1. 把要用的设置写进随机器自己的设置文件（%LOCALAPPDATA%\EldenRingRandomizer.Avalo\…\user.config）：
#      选项 = 玩家上次在随机器里用的设置（改过就按改过的），从没用过随机器就用整合包的默认设置（只开敌人随机）；
#      种子每次换新的；不合并别的包（「合并其它MOD」清空，整合包直接在原版上随机）；游戏 exe = 启动器的游戏路径
#   2. 打开随机器，用 Windows UI 自动化点「随机化敌人」，等它写完新的 spoiler 日志，再关掉随机器
#   3. 每次都勾「重roll种子」让随机器自己换新种子（设置里不写种子）；某些种子随机器自己会失败（日志里是报错堆栈），换种子再试，最多 3 次
# 随机器的设置文件按 exe 所在位置分开存（文件夹名里是路径的哈希），找到后记在 launcher\randomizer_settings_path.txt

$RandSettingsRoot = Join-Path $env:LOCALAPPDATA 'EldenRingRandomizer.Avalo'
$RandSettingsMap  = Join-Path $LauncherDir 'randomizer_settings_path.txt'
# 整合包的默认设置：只开敌人随机，其余是随机器推荐项。物品随机玩家可以在随机器里自己开（重随认得出来，dev\item_rand\物品随机兼容.md）
$RandDefaultOptions = 'allmaps bossbgm changestats crashfix dlc dlcblessing dlckeysilo earlylegacy editnames enemy markareas mats norandom norandom_health norandom_scadu norandom_upgrades phasehp raceloc_health raceloc_scadu scale spellshops v16 weaponprogression bias:20'

# 随机器要 .NET 8 运行时。整合包自带一份便携版（launcher\dotnet）：
# 引入这个文件时就把 DOTNET_ROOT 指过去，之后打开的随机器都继承，优先用自带的，新电脑不用装。
# 自带的被删了才看系统里装的（共享框架目录里有没有 Microsoft.NETCore.App 8.x）
$DotNet8Url = 'https://dotnet.microsoft.com/download/dotnet/8.0'
$BundledDotNet = Join-Path $LauncherDir 'dotnet'
if (Get-ChildItem -LiteralPath (Join-Path $BundledDotNet 'shared\Microsoft.NETCore.App') -Directory -Filter '8.*' -ErrorAction SilentlyContinue) {
    $env:DOTNET_ROOT = $BundledDotNet
    $env:DOTNET_ROOT_X64 = $BundledDotNet
}
function Test-DotNet8 {
    $roots = @()
    if ($env:DOTNET_ROOT) { $roots += $env:DOTNET_ROOT }
    if ($env:ProgramFiles) { $roots += (Join-Path $env:ProgramFiles 'dotnet') }
    foreach ($r in $roots) {
        $d = Join-Path $r 'shared\Microsoft.NETCore.App'
        if (Get-ChildItem -LiteralPath $d -Directory -Filter '8.*' -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
}
function Get-DotNet8Msg {
    return ('找不到 .NET 8 运行时（整合包自带的 launcher\dotnet 不见了，系统里也没装），随机器打不开。' + "`r`n" +
            '重新解压整合包可以恢复自带的；或者' + "`r`n" +
            '请到 ' + $DotNet8Url + ' 下载「.NET 桌面运行时 8.0」的 Windows x64 安装包，装好后再试。' + "`r`n" +
            '（不玩敌人随机的话不用装：无敌人随机照常能玩。）')
}

# ---------------------------------------------------------------- 随机器装了没有（正式发布不带随机器，dev\release\第三方分离.md 第 4 节）
# 随机器（thefifthmatt 的 Elden Ring Item and Enemy Randomizer）的许可不许转发，玩家自己下载、把压缩包里的东西解压到整合包的 randomizer\。
# 敌人随机要 randomizer\EldenRingRandomizer.exe 和它的数据（diste\Base\enemy.txt：重随按位置修正、敌人预设都要读）都在。
# 版本按程序的 SHA-256 认（文件版本号里没有）：测过的才算，别的版本照样能用，只提示没测过
$RandomizerUrl = 'https://www.nexusmods.com/eldenring/mods/428'
$RandomizerTested = @{ '8eb132f8e47a21dfffb3d0016c1117de2bb6c86b643ad9f8fba99079ab1c6cf4' = 'v0.12.2' }

function Get-RandomizerHowTo {
    return ('敌人随机要用 thefifthmatt 的随机器（Elden Ring Item and Enemy Randomizer）。整合包不带它（它的许可不许转发），要自己下载：' + "`r`n`r`n" +
            '1. 打开 ' + $RandomizerUrl + '，在 Files 里下载 v0.12.2（整合包测过的版本，在 Old files 里）；' + "`r`n" +
            '2. 把压缩包里的东西全部解压到整合包的 randomizer 文件夹（和 launcher 文件夹并排；图形界面里点「打开 randomizer 文件夹」能直接打开）。' + "`r`n" +
            '    解压好后 randomizer 文件夹里直接就是 EldenRingRandomizer.exe，中间不要多一层文件夹；' + "`r`n" +
            '3. 重新打开启动器。' + "`r`n`r`n" +
            '不装随机器也能玩「无敌人随机」，联机也能用「联机 · 无敌人随机」。')
}

# 随机器的状态 @{ Ok; Msg; Version; Tested }：Ok = 能用；Msg = 不能用时给玩家看的说明。每次现查（玩家可能开着启动器时装上），
# 只有算程序的哈希按大小和修改时间缓存
function Get-RandomizerStatus {
    $exe = Join-Path $RandomDir 'EldenRingRandomizer.exe'
    if (-not (Test-Path -LiteralPath $exe)) {
        $nested = Get-ChildItem -LiteralPath $RandomDir -Filter 'EldenRingRandomizer.exe' -Recurse -Depth 2 -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($nested) {
            $sub = $nested.DirectoryName.Substring($RandomDir.Length).TrimStart('\')
            return @{ Ok = $false; Msg = ('随机器解压多了一层文件夹（randomizer\' + $sub + '）。' + "`r`n`r`n" +
                                          '把这个文件夹里的东西全部挪到 randomizer 文件夹下面（EldenRingRandomizer.exe 要直接在 randomizer 文件夹里），再重新打开启动器。') }
        }
        return @{ Ok = $false; Msg = (Get-RandomizerHowTo) }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RandomDir 'diste\Base\enemy.txt'))) {
        return @{ Ok = $false; Msg = '随机器文件夹不完整（缺 diste 文件夹）。重新下载随机器，把压缩包里的东西全部解压到整合包的 randomizer 文件夹。' }
    }
    $it = Get-Item -LiteralPath $exe
    $key = [string]$it.Length + '|' + $it.LastWriteTimeUtc.Ticks
    if (-not $script:RandExeHash -or $script:RandExeHash.Key -ne $key) {
        $h = try { (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant() } catch { '' }
        $script:RandExeHash = @{ Key = $key; Hash = $h }
    }
    $v = $RandomizerTested[$script:RandExeHash.Hash]
    return @{ Ok = $true; Msg = ''; Version = $v; Tested = [bool]$v }
}

# 没测过的版本提示一句（启动器日志用）
function Get-RandomizerUntestedMsg {
    return ('这个版本的随机器整合包没测过（测过的是 v0.12.2），可能有问题：比如敌人预设、按位置修正对不上。出问题时换回 v0.12.2（' + $RandomizerUrl + ' 的 Old files）。')
}

# 这份随机器对应的设置文件；还没有（从没打开过这份随机器）返回 $null
function Find-RandSettingsFile {
    if (Test-Path -LiteralPath $RandSettingsMap) {
        $p = ([string](Get-Content -LiteralPath $RandSettingsMap -TotalCount 1 -Encoding UTF8)).Trim()
        if ($p -and (Test-Path -LiteralPath $p)) { return $p }
    }
    $dllDir = (Join-Path $RandomDir 'dll').ToLowerInvariant()
    foreach ($f in (Get-ChildItem -LiteralPath $RandSettingsRoot -Recurse -Filter 'user.config' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)) {
        # 随机器开了崩溃修复时，额外 DLL 里是它自己 dll 目录的完整路径：能认出是哪一份
        if ([System.IO.File]::ReadAllText($f.FullName).ToLowerInvariant().Contains($dllDir)) {
            [System.IO.File]::WriteAllText($RandSettingsMap, $f.FullName, (New-Object System.Text.UTF8Encoding($false)))
            return $f.FullName
        }
    }
    return $null
}

function Get-RandSetting([string]$File, [string]$Name) {
    if (-not $File -or -not (Test-Path -LiteralPath $File)) { return $null }
    try { $x = [xml][System.IO.File]::ReadAllText($File) } catch { return $null }
    $n = $x.SelectSingleNode("//setting[@name='$Name']/value")
    if ($n) { return [string]$n.InnerText }
    return $null
}

# 这次要用的选项：@{ Options = 不含种子的选项; From = 说明; HasItem = 是否开着物品随机 }
function Get-RandomizeOptions {
    $opt = Get-RandSetting (Find-RandSettingsFile) 'Options'
    $from = '上一次在随机器里用的设置'
    if (-not $opt -or $opt -notmatch '\bv\d+\b') {
        # 这个文件夹的随机器还没用过（多半是刚更新到新版本）：沿用旧版本随机器里的设置（见文件末尾「更新后沿用」）
        $opt = $null
        foreach ($p in (Get-OtherPacks)) {
            $o2 = Get-RandSetting (Find-RandSettingsFileFor (Join-Path $p 'randomizer')) 'Options'
            if ($o2 -and $o2 -match '\bv\d+\b') { $opt = $o2; $from = '旧版本随机器里的设置（' + $p + '）'; break }
        }
    }
    if (-not $opt -or $opt -notmatch '\bv\d+\b') { $opt = $RandDefaultOptions; $from = '整合包默认设置（只开敌人随机）' }
    $tok = @(($opt -split '\s+') | Where-Object { $_ -and $_ -notmatch '^seed2?:' })
    if ($tok -notcontains 'enemy') { $tok += 'enemy' }             # 一键重随的就是敌人
    return @{ Options = ($tok -join ' '); From = $from; HasItem = ($tok -contains 'item') }
}

function Set-RandSettings([string]$File, [hashtable]$Values) {
    $x = [xml][System.IO.File]::ReadAllText($File)
    $sec = $x.SelectSingleNode('//userSettings/*')
    foreach ($k in $Values.Keys) {
        $v = $x.SelectSingleNode("//setting[@name='$k']/value")
        if (-not $v) {
            $s = $x.CreateElement('setting')
            $s.SetAttribute('name', $k)
            $s.SetAttribute('serializeAs', 'String')
            $v = $x.CreateElement('value')
            [void]$s.AppendChild($v)
            [void]$sec.AppendChild($s)
        }
        $v.InnerText = [string]$Values[$k]
    }
    $w = New-Object System.Xml.XmlWriterSettings
    $w.Indent = $true
    $w.Encoding = New-Object System.Text.UTF8Encoding($false)
    $xw = [System.Xml.XmlWriter]::Create($File, $w)
    try { $x.Save($xw) } finally { $xw.Close() }
}

# 自己打开随机器之前：把它设置里的「合并其它MOD」清空（以前的版本会填可玩包的路径），游戏 exe 填好。
# 种子不动：随机器不勾「重roll种子」就沿用设置里上次的种子（结果和上次一模一样），由玩家自己勾（用户 2026-11-04，说明文字里提醒）。
# 也照一键重随那样写好整合包的自定义敌人预设（新的预设种子）、设置里勾上「自定义敌人」（customenemy）：追忆 Boss 只在追忆之间换、
# 按地区控制精英比例（用户 2026-11-12「可以在玩家手动的预设里也加上customenemy」：测试者自己开随机器随机化，选项里没有它，追忆 Boss 乱放了）。
# 还没有设置文件（这份随机器没打开过）就先打开一次让它生成（同一键重随）。
# 随机器开着时不改（它关掉时会把自己的设置写回去）。返回给玩家看的一句话（空 = 没什么要说的）
function Reset-RandMod([string]$GameExe) {
    if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { return '' }
    $file = Find-RandSettingsFile
    $note = ''
    if (-not $file) {
        $exe = Join-Path $RandomDir 'EldenRingRandomizer.exe'
        if (-not (Test-Path -LiteralPath $exe)) { return '' }
        try { Initialize-Uia; $file = New-RandSettingsFile $exe } catch { $file = $null }
        if (-not $file) { return '' }
    }
    $v = @{ Mod = '' }
    if ($GameExe -and (Test-Path -LiteralPath $GameExe)) { $v.Exe = $GameExe }
    if (Update-ManualPreset) {
        $opt = Get-RandSetting $file 'Options'
        $tok = @(([string]$opt -split '\s+') | Where-Object { $_ })
        if (-not ($opt -match '\bv\d+\b')) { $tok = @(((Get-RandomizeOptions).Options -split '\s+') | Where-Object { $_ }) }   # 设置里还是随机器自己的默认值
        if ($tok -notcontains 'customenemy') { $tok += 'customenemy' }
        $v.Options = $tok -join ' '
        $note = '已写好整合包的自定义敌人预设，随机器里「自定义敌人」已经勾上（追忆 Boss 只在追忆之间换、按地区控制精英比例），不要取消它。'
    }
    try { Set-RandSettings $file $v } catch { $note = '' }
    return $note
}

# 敌人预设的种子和自然精英比例：随机器 presets\.dr_manual.preset（时间、种子、比例三行）。每次重写自定义敌人预设都记一下，
# 之后找到比它新、选项带 customenemy、旁边还没有 .preset 的 spoiler 日志（玩家自己开随机器随机化的），Get-RandomInfo 照它补写 .preset
# （联机随机码、高难度世界要用这两个数重现同一份预设）
function Save-PresetRecord([string]$RandDir, [int]$Seed, [string]$Nat) {
    $f = Join-Path $RandDir 'presets\.dr_manual.preset'
    try { [System.IO.File]::WriteAllText($f, ((Get-Date).ToString('o') + "`n" + [string]$Seed + "`n" + $Nat + "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
}

# 重写自定义敌人预设（reroll\enemypreset.py，新的预设种子；选项照 Get-RandomizeOptions），写好了记下种子返回 $true；不限制 / 失败返回 $false
function Update-ManualPreset {
    $py = Join-Path $LauncherDir 'python\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { return $false }
    $o = Get-RandomizeOptions
    $seed = Get-Random -Minimum 1 -Maximum 2147483647
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = @(& $py -X utf8 (Join-Path $LauncherDir 'reroll\enemypreset.py') --randomizer-dir $RandomDir --dll-dir $RandomDir --options $o.Options --seed $seed 2>&1)
        $code = $LASTEXITCODE
    } catch {
        $code = -1
        $out = @()
    } finally {
        $ErrorActionPreference = $eap
    }
    if ($code -ne 0) { return $false }
    $nat = ''
    foreach ($l in $out) { if ([string]$l -match '^NAT:(.*)$') { $nat = $Matches[1].Trim() } }
    Save-PresetRecord $RandomDir $seed $nat
    return $true
}

# ---------------------------------------------------------------- 操作随机器窗口
function Initialize-Uia {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
}

function Wait-RandWindow([int]$ProcId, [int]$Seconds = 90) {
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcId)
    for ($i = 0; $i -lt $Seconds * 2; $i++) {
        $w = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
        if ($w) {
            $b = Find-RandButton $w
            if ($b) { return $w }                      # 主按钮出来了才算加载完
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Find-RandControl($Win, [string]$Type, [string]$NamePattern) {
    $ct = [System.Windows.Automation.ControlType]::$Type
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $ct)
    foreach ($e in $Win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)) {
        if ($e.Current.Name -match $NamePattern) { return $e }
    }
    return $null
}

# 随机器主按钮的文字随选项变（「随机化敌人」「随机化物品与敌人」「以设定种子运行随机」「运行新一轮随机！」……，界面语言不同也不同）：
# 从随机器自己的界面文字（diste\Messages\*.json 里 EldenForm_randomize* 那几条的 text / english_text）收集所有写法。
# 以前只认「随机化 / Randomize」开头：开了物品随机、用固定种子时按钮是「以设定种子运行随机」，认不出来，等 90 秒后把随机器关了（2026-11-02）
function Get-RandButtonNames {
    if ($null -ne $script:RandButtonNames) { return $script:RandButtonNames }
    $set = @{}
    foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $RandomDir 'diste\Messages') -Filter '*.json' -File -ErrorAction SilentlyContinue)) {
        try {
            $j = [System.IO.File]::ReadAllText($f.FullName) | ConvertFrom-Json
            foreach ($m in @($j.messages)) {
                # 两个页面都没勾时的「???」不算（点了也不会随机化）
                if ([string]$m.name -like 'EldenForm_randomize*' -and [string]$m.name -ne 'EldenForm_randomizeNothing') {
                    foreach ($t in @([string]$m.text, [string]$m.english_text)) { if ($t.Trim()) { $set[$t.Trim()] = $true } }
                }
            }
        } catch { }
    }
    $script:RandButtonNames = @($set.Keys)
    return $script:RandButtonNames
}

# 主按钮（随机化）：名字是上面任一种写法，或者老规则「随机化 / Randomize」开头
function Find-RandButton($Win) {
    $names = Get-RandButtonNames
    $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)
    foreach ($e in $Win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)) {
        $n = ([string]$e.Current.Name).Trim()
        if ($n -and (($names -contains $n) -or $n -match '^(随机化|Randomize)')) { return $e }
    }
    return $null
}

function Close-RandWindow($Proc) {
    try {
        $cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $Proc.Id)
        foreach ($w in [System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)) {
            $wp = $w.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern)
            $wp.Close()                                # 正常关闭：随机器会把设置写回文件
        }
    } catch { }
    if (-not $Proc.WaitForExit(15000)) { try { Stop-Process -Id $Proc.Id -Force } catch { } }
}

# 打开一次再正常关掉，让随机器生成自己的设置文件（第一次用这份随机器时）
function New-RandSettingsFile([string]$Exe) {
    $t0 = Get-Date
    $p = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe) -PassThru
    $w = Wait-RandWindow $p.Id
    Close-RandWindow $p
    if (-not $w) { return $null }
    $f = Get-ChildItem -LiteralPath $RandSettingsRoot -Recurse -Filter 'user.config' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $t0.AddSeconds(-2) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $f) { return $null }
    [System.IO.File]::WriteAllText($RandSettingsMap, $f.FullName, (New-Object System.Text.UTF8Encoding($false)))
    return $f.FullName
}

# 读随机器正在写 / 刚写完的日志（它一直开着这个文件，要允许共享读写）
function Read-SharedText([string]$Path) {
    try {
        $fs = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try { return (New-Object System.IO.StreamReader($fs)).ReadToEnd() } finally { $fs.Close() }
    } catch { return '' }
}

# 一次随机化的结果：'ok' / 'fail'（随机器报错，可换种子重试）/ 'timeout' / 'closed'
# 判断完成：随机化时按钮文字变成「随机中...」，完成或出错后变回来；之后日志才写完
function Wait-RandResult($Proc, $Btn, [datetime]$Since, [int]$Minutes = 15) {
    $logDir = Join-Path $RandomDir 'spoiler_logs'
    $deadline = (Get-Date).AddMinutes($Minutes)
    $busy = '(中\.\.\.|中…|ing\.\.\.)$'
    $seenBusy = $false
    while ((Get-Date) -lt $deadline) {
        if ($Proc.HasExited) { return 'closed' }
        $name = ''
        try { $name = [string]$Btn.Current.Name } catch { }
        if ($name -match $busy) { $seenBusy = $true }
        elseif ($seenBusy -or (Get-Date) -gt $Since.AddSeconds(30)) { break }   # 30 秒都没进入「随机中」也去看日志
        Start-Sleep -Seconds 2
    }
    if ((Get-Date) -ge $deadline) { return 'timeout' }
    for ($i = 0; $i -lt 15; $i++) {                    # 日志可能晚一点才写完
        $log = Get-ChildItem -LiteralPath $logDir -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $Since.AddSeconds(-2) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($log) {
            $txt = Read-SharedText $log.FullName
            if ($txt -match '(?m)^\s+at RandomizerCommon\.') { return 'fail' }
            if ($txt.Contains('Basic placements')) { return 'ok' }
        }
        Start-Sleep -Seconds 2
    }
    return 'fail'
}

# 整个流程。$GameExe = eldenring.exe。返回 @{ Ok; Msg; Options }
# $Fixed（联机随机码，见 launcher.ps1 的 Get-CoopCode）：@{ Options = 随机器的选项和种子（带 seed:N）; PresetSeed = 敌人预设的种子;
#   Nat = 敌人预设用的随机器自然精英比例 }。给了就照它重随（不勾「重roll种子」，只试一次），和对方的随机结果一模一样；
#   不给就是平常的一键重随（随机器自己换新种子）。
# 敌人预设的种子和自然精英比例记在新 spoiler 日志旁边的 <日志名>.preset（两行；联机随机码要用；随机器自己的种子在日志第一行）
function Invoke-RandomizeEnemies([string]$GameExe, $Fixed = $null) {
    $exe = Join-Path $RandomDir 'EldenRingRandomizer.exe'
    if (-not (Test-Path -LiteralPath $exe)) { return @{ Ok = $false; Msg = '找不到随机器：' + $exe } }
    if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { return @{ Ok = $false; Msg = '随机器已经开着，先把它关掉再点一键重随敌人。' } }
    if (-not (Test-DotNet8)) { return @{ Ok = $false; Msg = (Get-DotNet8Msg) } }
    Initialize-Uia
    if ($Fixed) {
        $tok = @(($Fixed.Options -split '\s+') | Where-Object { $_ })
        $o = @{ Options = ($tok -join ' '); From = $(if ($Fixed.From) { $Fixed.From } else { '联机随机码' }); HasItem = ($tok -contains 'item') }
    } else {
        $o = Get-RandomizeOptions
    }
    $file = Find-RandSettingsFile
    if (-not $file) {
        Write-Host '  第一次用这份随机器：先打开一次让它生成设置文件（会自动关掉，不要点它）...'
        $file = New-RandSettingsFile $exe
        if (-not $file) { return @{ Ok = $false; Msg = '随机器没有生成设置文件（窗口没有正常打开？）。请先手动打开随机器一次再试。' } }
    }
    $seed = if ($Fixed) { [int]$Fixed.PresetSeed } else { Get-Random -Minimum 1 -Maximum 2147483647 }
    $nat = ''
    $wantSeed = if ($Fixed -and $o.Options -match '(?:^|\s)seed:(\d+)') { $Matches[1] } else { '' }
    # 前期位置少放精英：往随机器的自定义敌人预设里写指定（launcher\reroll\enemypreset.py），写好了就开「自定义敌人」
    $py = Join-Path $LauncherDir 'python\python.exe'
    if (Test-Path -LiteralPath $py) {
        # 2>&1 把错误输出也收进来显示；启动器默认 ErrorActionPreference = Stop，那样错误输出第一行（哪怕只是警告）就会被当成异常、整个重随中断，这里临时改成 Continue
        $eap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $pa = @('--randomizer-dir', $RandomDir, '--dll-dir', $RandomDir, '--options', $o.Options, '--seed', $seed)
        if ($Fixed) { $pa += @('--nat', $Fixed.Nat) }
        if ($Fixed -and $Fixed.FixedBosses) { $pa += @('--fixed-bosses', $Fixed.FixedBosses) }    # 高难度世界（下面 Invoke-RandomizeHiWorld）
        $out = & $py -X utf8 (Join-Path $LauncherDir 'reroll\enemypreset.py') @pa 2>&1
        $ErrorActionPreference = $eap
        # NAT: 那行是这次用的随机器自然精英比例，记进 .preset，不显示
        $out | ForEach-Object { $l = [string]$_; if ($l -match '^NAT:(.*)$') { $nat = $Matches[1].Trim() } else { Write-Host $l } }
        $tok = @(($o.Options -split '\s+') | Where-Object { $_ })
        if ($LASTEXITCODE -eq 0) {
            if ($tok -notcontains 'customenemy') { $tok += 'customenemy' }
            Save-PresetRecord $RandomDir $seed $nat
        }
        $o.Options = $tok -join ' '
    }
    Copy-Item -LiteralPath $file -Destination ($file + '.dr.bak') -Force
    # 种子交给随机器：勾「重roll种子」，它每次自己换新种子（设置里不写种子）；不合并别的包。
    # 联机随机码：选项里带着 seed:N，不勾「重roll种子」，随机器就用这个种子
    Set-RandSettings $file @{ Options = $o.Options; Mod = ''; Exe = $GameExe }
    Write-Host ('  设置：' + $o.From + $(if ($Fixed) { '（固定种子 ' + $wantSeed + '，敌人预设种子 ' + $seed + '）' } else { '（勾「重roll种子」，每次换新种子）' }))
    Write-Host ('  选项：' + $o.Options)
    if ($o.HasItem) { Write-Host '  开着物品随机：法术祷告、道具、材料、锻造石的位置和商人货架也会打乱（原版武器防具护符整合包照样换成未鉴定物品）。' }

    Write-Host '  [提示] 随机器窗口马上会打开并自动操作：这期间不要点随机器窗口，也不要关掉它，完成后会自动关闭。' -ForegroundColor Yellow
    $p = Start-Process -FilePath $exe -WorkingDirectory $RandomDir -PassThru
    try {
        $w = Wait-RandWindow $p.Id
        if (-not $w) { return @{ Ok = $false; Msg = '随机器窗口没有在 90 秒内打开。' } }
        for ($try = 1; $try -le $(if ($Fixed) { 1 } else { 3 }); $try++) {
            $btn = Find-RandButton $w
            $cb = Find-RandControl $w 'CheckBox' '(重roll种子|Reroll seed)'
            if ($cb) {                                 # 平常每次（含失败重试）都勾「重roll种子」：随机器自己换新种子；联机随机码不勾（用码里的种子）
                $tp = $cb.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
                $want = if ($Fixed) { 'Off' } else { 'On' }
                if ([string]$tp.Current.ToggleState -ne $want) { $tp.Toggle() }
            } elseif ($Fixed) {
                return @{ Ok = $false; Msg = '在随机器窗口里找不到「重roll种子」，没法确认用的是联机随机码里的种子，这次没有重随。' }
            } else {
                Write-Host '  [提示] 在随机器窗口里找不到「重roll种子」，这次用随机器自己的种子设置。' -ForegroundColor Yellow
            }
            if (-not $btn) { return @{ Ok = $false; Msg = '在随机器窗口里找不到「随机化」按钮。' } }
            Write-Host ('  第 ' + $try + ' 次：点「' + $btn.Current.Name + '」，随机化大约要 2~5 分钟...')
            $t0 = Get-Date
            $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
            $r = Wait-RandResult $p $btn $t0
            if ($r -eq 'ok') {
                $log = Get-ChildItem -LiteralPath (Join-Path $RandomDir 'spoiler_logs') -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending | Select-Object -First 1
                $usedSeed = if ($log -and $log.Name -match '_log_(\d+)_') { $Matches[1] } else { '' }
                if ($log) {
                    try { [System.IO.File]::WriteAllText(($log.FullName -replace '\.txt$', '.preset'), ([string]$seed + "`n" + $nat + "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
                }
                if ($Fixed -and $usedSeed -ne $wantSeed) {
                    return @{ Ok = $false; Msg = ('随机器用的种子（' + $usedSeed + '）和联机随机码里的（' + $wantSeed + '）不一样，随机结果和对方对不上。') }
                }
                $used = if ($usedSeed) { '，种子 ' + $usedSeed } else { '' }
                return @{ Ok = $true; Msg = '敌人已重新随机化（' + $o.From + $used + '）'; Options = $o.Options }
            }
            if ($r -ne 'fail') { return @{ Ok = $false; Msg = $(if ($r -eq 'timeout') { '随机化超过 15 分钟没有完成。' } else { '随机器窗口被关掉了。' }) } }
            if ($Fixed) { return @{ Ok = $false; Msg = '随机器用联机随机码里的种子失败了（日志里是报错）。确认两边的整合包版本一样。' } }
            Write-Host '  [提示] 这个种子随机器自己失败了（日志里是报错），换个种子再试...' -ForegroundColor Yellow
        }
        return @{ Ok = $false; Msg = '换了 3 个种子都失败了，请点「打开随机器」手动看看是哪个选项有问题。' }
    } finally {
        Close-RandWindow $p
    }
}

# ---------------------------------------------------------------- 高难度世界（Boss 模组，dev\boss_mods\README.md）
# 只在「死亡」以上加载的 Boss 改版，敌人随机时也要在原场地（用户 2026-11-05「只在高难度固定」）。随机器每次只出一套世界，
# 所以一键重随敌人成功后，用同一个种子、同一份精英指定再让它跑一遍：这一遍把整合了改版的 Boss 固定在原位
# （enemypreset.py --fixed-bosses：DontRandomize + RemoveSource），输出搬到 randomizer_hi\。随机器自带的数据（diste）不搬也不建联接
# （E: 这种 exFAT 盘建不了，用户 2026-11-05 遇到），重随读 diste 时在高难度世界里找不到就用旁边 randomizer\diste（rr/stage3.py 的 diste）。
# 启动时角色是高难度就用这一套（launcher.ps1 的 Get-RandHiWorld）。
# 搬的时候先把正常那一套挪到 randomizer\.dr_lo，随机器跑完不管成没成功都搬回来（finally）；随机器的设置、自定义敌人预设也还原成正常那一遍的。
$RandomHiDir = Join-Path $Paly 'randomizer_hi'
$RandHiItems = @('map', 'event', 'msg', 'script', 'sfx', 'regulation.bin', 'config_eldenringrandomizer.toml')
$RandHiSource = 'hi_source.json'

# settings.json 的 boss_mods 里开着、数据也在的模组要固定的 Boss 实体（mod.json 的 fixed）；关着（mode off）就是空
function Get-BossFixedIds {
    $ids = @()
    try { $s = [System.IO.File]::ReadAllText((Join-Path $LauncherDir 'reroll\settings.json')) | ConvertFrom-Json } catch { return $ids }
    $bm = $s.boss_mods
    if (-not $bm -or [string]$bm.mode -eq 'off' -or -not $bm.mods) { return $ids }
    foreach ($p in $bm.mods.PSObject.Properties) {
        if ($p.Name.StartsWith('_') -or $p.Value -ne $true) { continue }
        $mj = Join-Path $LauncherDir ('reroll\data\bossmods\' + $p.Name + '\mod.json')
        try { $m = [System.IO.File]::ReadAllText($mj) | ConvertFrom-Json } catch { continue }
        foreach ($e in @($m.fixed)) { if ($e) { $ids += [long]$e } }
    }
    # 有高难度世界时，「花蕾圣女」萝蜜娜也固定在原位（用户 2026-11-13「只在高难不随机」）：烧封印树后花蕾教堂整块换成解封版，
    # 进「死亡」复活后要把这一仗补进解封版（reroll\sc\lostarena.py），补的内容按原版萝蜜娜写死，位置上必须是她。
    # 蒙葛特当时也固定了，灰城那一场决定不补（「不补 也不用说明了」）后改回随机（「改回随机」）
    if ($ids.Count) { $ids += @([long]2044450800) }
    return @($ids | Sort-Object -Unique)
}

# 删掉高难度世界：diste 是目录联接，先单独删联接（不递归，不会碰 randomizer\diste 里的东西），再删其余
function Remove-RandHiDir {
    if (-not (Test-Path -LiteralPath $RandomHiDir)) { return }
    $j = Join-Path $RandomHiDir 'diste'
    if (Test-Path -LiteralPath $j) { [System.IO.Directory]::Delete($j, $false) }
    Remove-Item -LiteralPath $RandomHiDir -Recurse -Force
}

# 能用的高难度世界：$null = 没有 / 过期（不是跟着现在这次随机化做的、或者固定的 Boss 不全）。$Need = 这次要固定的实体。
# $HiDir / $LoDir：看别的整合包（更新后沿用）时给它的 randomizer_hi / randomizer，不给就是这个整合包的
function Get-RandHiWorld($Need, [string]$HiDir = $RandomHiDir, [string]$LoDir = $RandomDir) {
    $f = Join-Path $HiDir $RandHiSource
    if (-not (Test-Path -LiteralPath $f) -or -not (Test-Path -LiteralPath (Join-Path $HiDir 'regulation.bin'))) { return $null }
    try { $h = [System.IO.File]::ReadAllText($f) | ConvertFrom-Json } catch { return $null }
    $lo = Get-ChildItem -LiteralPath (Join-Path $LoDir 'spoiler_logs') -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $lo -or $lo.Name -ne [string]$h.lo_log) { return $null }
    $have = @($h.fixed | ForEach-Object { [long]$_ })
    foreach ($e in @($Need)) { if ($have -notcontains [long]$e) { return $null } }
    return $h
}

# 一键重随敌人成功之后：同一个种子再跑一遍高难度世界。返回 @{ Ok; Msg }（没开 Boss 模组时 Ok、Msg 空）
function Invoke-RandomizeHiWorld([string]$GameExe) {
    $fixed = @(Get-BossFixedIds)
    Remove-RandHiDir                                  # 旧的高难度世界跟着旧的随机化，作废
    if (-not $fixed.Count) { return @{ Ok = $true; Msg = '' } }
    $logDir = Join-Path $RandomDir 'spoiler_logs'
    $log = Get-ChildItem -LiteralPath $logDir -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $log -or $log.Name -notmatch '_log_(\d+)_') { return @{ Ok = $false; Msg = '找不到刚才随机化的日志' } }
    $seed = $Matches[1]
    $optLine = Get-Content -LiteralPath $log.FullName -TotalCount 5 -Encoding UTF8 | Where-Object { $_ -match '^Options and seed:' } | Select-Object -First 1
    if (-not $optLine) { return @{ Ok = $false; Msg = '刚才随机化的日志里没有选项' } }
    $opt = @((($optLine -replace '^Options and seed:\s*', '') -split '\s+') | Where-Object { $_ -and $_ -notmatch '^seed2?:' }) -join ' '
    $pf = $log.FullName -replace '\.txt$', '.preset'
    $pl = if (Test-Path -LiteralPath $pf) { @(Get-Content -LiteralPath $pf -Encoding UTF8) } else { @() }
    if ($pl.Count -lt 1 -or -not $pl[0]) { return @{ Ok = $false; Msg = '刚才随机化没有记下敌人预设的种子' } }
    $file = Find-RandSettingsFile
    $preset = Join-Path $RandomDir 'presets\CustomEnemy.txt'
    $lo = Join-Path $RandomDir '.dr_lo'
    Write-Host ''
    Write-Host ('  高难度世界：同一个种子（' + $seed + '）再随机化一遍，这一遍 ' + $fixed.Count + ' 个 Boss 留在原位（整合了改版的、萝蜜娜；只在「死亡」以上用）...')
    if ($file) { Copy-Item -LiteralPath $file -Destination ($file + '.hi.bak') -Force }
    if (Test-Path -LiteralPath $preset) { Copy-Item -LiteralPath $preset -Destination ($preset + '.hi.bak') -Force }
    $ok = $false
    try {
        if (Test-Path -LiteralPath $lo) { Remove-Item -LiteralPath $lo -Recurse -Force }
        [void](New-Item -ItemType Directory -Path $lo)
        foreach ($n in $RandHiItems) { $p = Join-Path $RandomDir $n; if (Test-Path -LiteralPath $p) { Move-Item -LiteralPath $p -Destination (Join-Path $lo $n) } }
        $fx = @{ Options = ($opt + ' seed:' + $seed); PresetSeed = $pl[0]; Nat = $(if ($pl.Count -gt 1) { $pl[1] } else { '' });
                 From = '高难度世界（同一个种子）'; FixedBosses = ($fixed -join ',') }
        $r = Invoke-RandomizeEnemies $GameExe $fx
        if (-not $r.Ok) { return @{ Ok = $false; Msg = $r.Msg } }
        $hiLog = Get-ChildItem -LiteralPath $logDir -Filter '*_log_*.txt' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        [void](New-Item -ItemType Directory -Path (Join-Path $RandomHiDir 'spoiler_logs') -Force)
        foreach ($n in $RandHiItems) { $p = Join-Path $RandomDir $n; if (Test-Path -LiteralPath $p) { Move-Item -LiteralPath $p -Destination (Join-Path $RandomHiDir $n) } }
        foreach ($p in @($hiLog.FullName, ($hiLog.FullName -replace '\.txt$', '.preset'))) {
            if (Test-Path -LiteralPath $p) { Move-Item -LiteralPath $p -Destination (Join-Path $RandomHiDir 'spoiler_logs') }
        }
        $info = [ordered]@{ lo_log = $log.Name; hi_log = $hiLog.Name; seed = $seed; fixed = $fixed; time = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }
        [System.IO.File]::WriteAllText((Join-Path $RandomHiDir $RandHiSource), ($info | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
        $ok = $true
        return @{ Ok = $true; Msg = ('高难度世界也随机化好了（' + $fixed.Count + ' 个 Boss 留在原位）') }
    } finally {
        if (-not $ok) {
            # 没成功：随机器这一遍的半截输出清掉，它的日志改名（免得被当成最近一次随机化），高难度世界不要
            foreach ($n in $RandHiItems) { $p = Join-Path $RandomDir $n; if ((Test-Path -LiteralPath $p) -and (Test-Path -LiteralPath (Join-Path $lo $n))) { Remove-Item -LiteralPath $p -Recurse -Force } }
            Get-ChildItem -LiteralPath $logDir -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt $log.LastWriteTime } |
                ForEach-Object { Rename-Item -LiteralPath $_.FullName -NewName ($_.Name + '.hi_failed') -ErrorAction SilentlyContinue }
            if (Test-Path -LiteralPath $RandomHiDir) { try { Remove-RandHiDir } catch { } }
        }
        foreach ($n in $RandHiItems) {
            $src = Join-Path $lo $n
            if (Test-Path -LiteralPath $src) { Move-Item -LiteralPath $src -Destination (Join-Path $RandomDir $n) }
        }
        if ((Test-Path -LiteralPath $lo) -and -not @(Get-ChildItem -LiteralPath $lo -Force).Count) { Remove-Item -LiteralPath $lo -Force }
        if ($file -and (Test-Path -LiteralPath ($file + '.hi.bak'))) { Move-Item -LiteralPath ($file + '.hi.bak') -Destination $file -Force }
        if (Test-Path -LiteralPath ($preset + '.hi.bak')) { Move-Item -LiteralPath ($preset + '.hi.bak') -Destination $preset -Force }
    }
}

# ---------------------------------------------------------------- 更新后沿用旧版本的敌人随机结果
# 每次更新都解压到新文件夹，新文件夹的 randomizer\ 里没有随机器输出（约 100 MB、1000 多个文件，不打进 zip），以前第一次用敌人随机启动就会重新随机化，
# 打到一半敌人全换了（2026-11-01 用户要求解决）。现在：
#   - 每次启动游戏把整合包路径记进 %APPDATA%\EldenRing\DarkReforged\packs.txt（最近 10 个，新的在前；Save-PackPath）；
#   - 新文件夹还没有能用的随机结果时，在记下的整合包、以及这个整合包上一级 / 上两级目录往下两层里找旧版本的随机结果（Find-OldRandoms），
#     图形界面问玩家要不要沿用，同意就由启动器复制过来（-Action carryrand）；
#   - 一键重随敌人时，新文件夹的随机器还没用过就沿用旧版本随机器里的设置（Get-RandomizeOptions）。
# 只沿用整合包版本不低于 $RandCarryMinVersion 的（v0.7 起随机器不再合并别的包；以后改了要重新随机化才生效的东西就调高它），合并别的包做的也不要
$RandCarryMinVersion = [version]'0.7'
$RandPacksFile = Join-Path $RngDataDir 'packs.txt'
# 随机器生成的东西（打包时排除的那些）；spoiler_logs 放最后：复制到一半中断时不会被当成完整的结果
$RandOutputItems = @('map', 'event', 'msg', 'script', 'sfx', 'regulation.bin', 'config_eldenringrandomizer.toml', 'spoiler_logs')

function Get-PackVersion([string]$Pack) {
    try { return [version]([string](Get-Content -LiteralPath (Join-Path $Pack 'launcher\version.txt') -TotalCount 1 -ErrorAction Stop)).Trim() } catch { return $null }
}

# 一个随机器文件夹里的随机结果：最新 spoiler 日志的时间、种子、有没有开敌人随机、是不是合并别的包做的、
# 选项和种子（日志第一行，联机随机码用）、敌人预设的种子和自然精英比例（一键重随记在日志旁边的 .preset 两行，没有是空）；没有 regulation.bin 或日志返回 $null
function Get-RandomInfo([string]$RandDir) {
    if (-not (Test-Path -LiteralPath (Join-Path $RandDir 'regulation.bin'))) { return $null }
    $log = Get-ChildItem -LiteralPath (Join-Path $RandDir 'spoiler_logs') -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $log) { return $null }
    $head = @(Get-Content -LiteralPath $log.FullName -TotalCount 40 -Encoding UTF8 -ErrorAction SilentlyContinue)
    $opt = [string]($head | Where-Object { $_ -match '^Options and seed:' } | Select-Object -First 1)
    $pf = $log.FullName -replace '\.txt$', '.preset'
    if (-not (Test-Path -LiteralPath $pf) -and $opt -match '(^|\s)customenemy(\s|$)') {
        # 玩家自己开随机器随机化的：照上一次写自定义敌人预设时记下的种子补写（Save-PresetRecord）
        $mf = Join-Path $RandDir 'presets\.dr_manual.preset'
        $m = if (Test-Path -LiteralPath $mf) { @(Get-Content -LiteralPath $mf -TotalCount 3 -Encoding UTF8 -ErrorAction SilentlyContinue) } else { @() }
        $t = [datetime]::MinValue
        if ($m.Count -ge 3 -and [datetime]::TryParse([string]$m[0], [ref]$t) -and $log.LastWriteTime -ge $t -and ([string]$m[1]).Trim()) {
            try { [System.IO.File]::WriteAllText($pf, (([string]$m[1]).Trim() + "`n" + ([string]$m[2]).Trim() + "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
        }
    }
    $pre = if (Test-Path -LiteralPath $pf) { @(Get-Content -LiteralPath $pf -TotalCount 2 -ErrorAction SilentlyContinue) } else { @() }
    return [pscustomobject]@{
        Time     = $log.LastWriteTime
        Seed     = $(if ($log.Name -match '_log_(\d+)_') { $Matches[1] } else { '' })
        HasEnemy = [bool]($opt -match '(^|\s)enemy(\s|$)')
        HasItem  = [bool]($opt -match '(^|\s)item(\s|$)')
        Merged   = [bool]($head | Where-Object { $_ -match '^Checking other mod directory \S' })
        Options  = ($opt -replace '^Options and seed:\s*', '').Trim()
        PresetSeed = $(if ($pre.Count -ge 1) { ([string]$pre[0]).Trim() } else { '' })
        PresetNat  = $(if ($pre.Count -ge 2) { ([string]$pre[1]).Trim() } else { '' })
        Log      = $log.FullName
    }
}

# 启动游戏时记下这个整合包的位置（更新到新版本后从这里找旧版本）
function Save-PackPath {
    try {
        $cur = [System.IO.Path]::GetFullPath($Paly).TrimEnd('\')
        $old = @(if (Test-Path -LiteralPath $RandPacksFile) { Get-Content -LiteralPath $RandPacksFile -Encoding UTF8 })
        $list = @($cur) + @($old | ForEach-Object { ([string]$_).Trim().TrimEnd('\') } | Where-Object { $_ -and $_ -ine $cur })
        New-Item -ItemType Directory -Force -Path $RngDataDir | Out-Null
        [System.IO.File]::WriteAllLines($RandPacksFile, [string[]]@($list | Select-Object -First 10), (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

# 别的整合包文件夹（有 launcher\launcher.ps1 的）：先是 packs.txt 记的（最近用过的在前），再往下两层找：
# 这个整合包上一级、上两级目录（解压到旁边的文件夹最常见），桌面、下载、文档，游戏目录和它的 Game 文件夹。
#（v0.8.5 以前没记 packs.txt；再找不到，点「一键启动（敌人随机）」时图形界面让玩家自己选旧版本文件夹，不会不问就重新随机化）
function Get-OtherPacks {
    $cur = [System.IO.Path]::GetFullPath($Paly).TrimEnd('\')
    $seen = @{}
    $out = New-Object System.Collections.Generic.List[string]
    $add = { param($p) $k = $p.ToLowerInvariant(); if ($p -and $p -ine $cur -and -not $seen.ContainsKey($k) -and (Test-Path -LiteralPath (Join-Path $p 'launcher\launcher.ps1'))) { $seen[$k] = $true; $out.Add($p) } }
    foreach ($p in @(if (Test-Path -LiteralPath $RandPacksFile) { Get-Content -LiteralPath $RandPacksFile -Encoding UTF8 })) {
        if ($p -and ([string]$p).Trim()) { & $add ([string]$p).Trim().TrimEnd('\') }
    }
    $up1 = [System.IO.Path]::GetDirectoryName($cur)
    $up2 = if ($up1) { [System.IO.Path]::GetDirectoryName($up1) } else { $null }
    $bases = @($up1, $up2, [Environment]::GetFolderPath('Desktop'), (Join-Path $env:USERPROFILE 'Downloads'), [Environment]::GetFolderPath('MyDocuments'))
    try {
        $gr = ([string](Get-Content -LiteralPath (Join-Path $LauncherDir 'game_path.txt') -TotalCount 1 -ErrorAction Stop)).Trim()
        if ($gr) { $bases += @($gr, (Join-Path $gr 'Game')) }
    } catch { }
    $done = @{}
    foreach ($base in $bases) {
        if (-not $base -or -not (Test-Path -LiteralPath $base)) { continue }
        $bk = $base.TrimEnd('\').ToLowerInvariant()
        if ($done.ContainsKey($bk)) { continue }
        $done[$bk] = $true
        foreach ($d1 in @(Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue)) {
            & $add $d1.FullName
            foreach ($d2 in @(Get-ChildItem -LiteralPath $d1.FullName -Directory -ErrorAction SilentlyContinue)) { & $add $d2.FullName }
        }
    }
    return @($out)
}

# 一个整合包文件夹里的随机结果能不能沿用（开了敌人随机、不是合并别的包做的、整合包版本够新）：能就返回候选（Pack / Version / Time / Seed），
# 不能返回原因（字符串，给玩家自己选文件夹时看）
function Get-OldRandom([string]$Pack) {
    if (-not (Test-Path -LiteralPath (Join-Path $Pack 'launcher\launcher.ps1'))) { return '这里不是暗黑重铸整合包的文件夹（里面没有 launcher\launcher.ps1）。' }
    $info = Get-RandomInfo (Join-Path $Pack 'randomizer')
    if (-not $info) { return '这个整合包里没有敌人随机结果（randomizer 文件夹里没有 regulation.bin 或 spoiler_logs）。' }
    if ($info.Merged) { return '这份随机结果是旧版本合并别的包做的，不能沿用。' }
    if (-not ($info.HasEnemy -or $info.HasItem)) { return '这份随机结果没开敌人随机。' }
    $ver = Get-PackVersion $Pack
    if (-not $ver -or $ver -lt $RandCarryMinVersion) { return ('这个整合包版本太旧（' + $(if ($ver) { 'v' + $ver } else { '读不到版本' }) + '），要 v' + $RandCarryMinVersion + ' 以上。') }
    return [pscustomobject]@{ Pack = $Pack; Version = $ver; Time = $info.Time; Seed = $info.Seed }
}

# 玩家选的文件夹 → 整合包文件夹：可以是整合包本身、它里面的随便哪一层（randomizer、launcher…），或者包着它的那一层
#（解压出来的 Dark_Reforged_v0.x、放了好几个版本的文件夹：往下两层里挑能沿用的、随机化最晚的那个）
function Resolve-PackDir([string]$Dir) {
    $d = [System.IO.Path]::GetFullPath($Dir).TrimEnd('\')
    for ($p = $d; $p; $p = [System.IO.Path]::GetDirectoryName($p)) {
        if (Test-Path -LiteralPath (Join-Path $p 'launcher\launcher.ps1')) { return $p }
    }
    $cur = [System.IO.Path]::GetFullPath($Paly).TrimEnd('\')
    $packs = @()
    foreach ($c1 in @(Get-ChildItem -LiteralPath $d -Directory -ErrorAction SilentlyContinue)) {
        foreach ($c in @($c1) + @(Get-ChildItem -LiteralPath $c1.FullName -Directory -ErrorAction SilentlyContinue)) {
            if ($c.FullName -ine $cur -and (Test-Path -LiteralPath (Join-Path $c.FullName 'launcher\launcher.ps1'))) { $packs += $c.FullName }
        }
    }
    $best = @($packs | ForEach-Object { Get-OldRandom $_ } | Where-Object { $_ -isnot [string] } | Sort-Object Time -Descending) | Select-Object -First 1
    if ($best) { return $best.Pack }
    if ($packs.Count) { return $packs[0] }
    return $d
}

# 旧版本整合包里能沿用的随机结果，随机化时间新的在前
function Find-OldRandoms {
    $out = @(foreach ($p in (Get-OtherPacks)) { Get-OldRandom $p } )
    return @($out | Where-Object { $_ -isnot [string] } | Sort-Object Time -Descending)
}

# 这个整合包需不需要沿用：还没有随机结果，或者现在的是合并别的包做的
function Test-NeedOldRandom {
    $cur = Get-RandomInfo $RandomDir
    return (-not $cur -or $cur.Merged)
}

# 某个随机器文件夹对应的随机器设置文件（同 Find-RandSettingsFile 的认法：设置里额外 DLL 写的是它自己 dll 目录的完整路径）
function Find-RandSettingsFileFor([string]$RandDir) {
    $dllDir = (Join-Path $RandDir 'dll').ToLowerInvariant()
    foreach ($f in (Get-ChildItem -LiteralPath $RandSettingsRoot -Recurse -Filter 'user.config' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)) {
        if ([System.IO.File]::ReadAllText($f.FullName).ToLowerInvariant().Contains($dllDir)) { return $f.FullName }
    }
    return $null
}
