# Dark Reforged · 图形界面
# 只是外壳：所有启动逻辑都调用同目录的 launcher.ps1（-Action ...），输出实时显示在窗口下方。
# 会卡住的交互（选游戏路径）在这里先处理掉，子进程不会等键盘输入。
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$LauncherDir = $PSScriptRoot
$Paly        = Split-Path -Parent $LauncherDir
$Launcher    = Join-Path $LauncherDir 'launcher.ps1'
$RandomDir   = Join-Path $Paly 'randomizer'
$RandomExe   = Join-Path $RandomDir 'EldenRingRandomizer.exe'
$YafDir      = Join-Path $Paly 'yafsml'
$GamePathFile = Join-Path $LauncherDir 'game_path.txt'
# 上次启动用的重随包（按世界各存一份，见 launcher.ps1 的 Set-WorldPacks）
function Get-RerollPack {
    $w = ''
    try { $w = ([System.IO.File]::ReadAllText((Join-Path $Paly 'out\current_world.txt'))).Trim() } catch { }
    return (Join-Path $Paly ('out\reroll' + $(if ($w -match '^[a-z_]*$') { $w } else { '' })))
}
$Settings    = Join-Path $LauncherDir 'reroll\settings.json'
$Utf8NoBom   = New-Object System.Text.UTF8Encoding($false)

# 这个窗口是隐藏的 PowerShell 开的（启动.bat），界面自己出的错（按钮里出错之类）玩家看不到：
# 关窗口时把这次运行里记下的错误写进 launcher\logs\gui_errors.txt（只留这一次的，最近 30 条），诊断包会带上
$GuiErrLog = Join-Path $LauncherDir 'logs\gui_errors.txt'
function Save-GuiErrors {
    if ($Error.Count -eq 0) { return }
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $GuiErrLog -Parent) | Out-Null
        $lines = @('==== ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' 关闭启动器窗口时记下的错误（共 ' + $Error.Count + ' 条，这里是最近 30 条，有的已经处理过、不影响使用）')
        foreach ($e in @($Error | Select-Object -First 30)) {
            $lines += '- ' + $e.ToString()
            if ($e.InvocationInfo) { $lines += '  ' + ($e.InvocationInfo.PositionMessage -replace "`r?`n", "`r`n  ") }
        }
        [System.IO.File]::WriteAllLines($GuiErrLog, [string[]]$lines, (New-Object System.Text.UTF8Encoding($true)))
    } catch { }
}

# ---------------------------------------------------------------- 读状态（和启动器同样的规则）
function Get-LatestRandom {
    $logDir = Join-Path $RandomDir 'spoiler_logs'
    if (-not (Test-Path -LiteralPath (Join-Path $RandomDir 'regulation.bin'))) { return $null }
    $log = Get-ChildItem -LiteralPath $logDir -Filter '*_log_*.txt' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $log) { return $null }
    $head = Get-Content -LiteralPath $log.FullName -TotalCount 5 -Encoding UTF8
    $opt = $head | Where-Object { $_ -match '^Options and seed:' } | Select-Object -First 1
    # 以前的版本让随机器合并可玩包：那样的输出带着别的包的参数，要重新随机化（和启动器的规则一样）
    $merged = [bool]($head | Where-Object { $_ -match '^Checking other mod directory \S' })
    return [pscustomobject]@{ Time = $log.LastWriteTime; HasEnemy = [bool]($opt -and $opt -match '(^|\s)enemy(\s|$)'); HasItem = [bool]($opt -and $opt -match '(^|\s)item(\s|$)'); Merged = $merged }
}

function Get-GameRoot {
    if (-not (Test-Path -LiteralPath $GamePathFile)) { return $null }
    $p = ([string](Get-Content -LiteralPath $GamePathFile -TotalCount 1 -Encoding UTF8)).Trim()
    if ($p -and (Test-Path -LiteralPath (Join-Path $p 'Game\eldenring.exe'))) { return $p }
    return $null
}

# ---------------------------------------------------------------- 界面
# 暗色 + 金色的控件、窗口和弹窗在 ui.ps1（启动器后台进程的弹窗也用）
. (Join-Path $LauncherDir 'ui.ps1')
Import-UiTypes
$Thm = [DarkReforgedUI.Theme]

$font  = New-Object System.Drawing.Font('Microsoft YaHei UI', 10)
$fontB = New-Object System.Drawing.Font('Microsoft YaHei UI', 13, [System.Drawing.FontStyle]::Bold)
$fontM = New-Object System.Drawing.Font('Microsoft YaHei UI', 10.5)
$fontS = New-Object System.Drawing.Font('Microsoft YaHei UI', 9.5)

$form = New-Object System.Windows.Forms.Form
$form.Text = '暗黑重铸 启动器'
$form.Font = $font
$form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Dpi
$form.ClientSize = New-Object System.Drawing.Size(900, 820)
$form.MinimumSize = New-Object System.Drawing.Size(916, 720)
$form.StartPosition = 'CenterScreen'
Set-DarkForm $form

$ToolTipCtl = New-Object DarkReforgedUI.DarkTip     # 别叫 $tip：PowerShell 变量不分大小写，会被 New-Btn 的 -Tip 参数遮住
$ToolTipCtl.AutoPopDelay = 20000

$PackVersion = if (Test-Path -LiteralPath (Join-Path $LauncherDir 'version.txt')) { ([string](Get-Content -LiteralPath (Join-Path $LauncherDir 'version.txt') -TotalCount 1 -Encoding UTF8)).Trim() } else { '' }
$header = New-Object DarkReforgedUI.DrHeader
$header.Subtitle = '暗黑重铸'
$header.Badge = $(if ($PackVersion) { 'v' + $PackVersion } else { '' })
$header.Font = $font
$header.Location = New-Object System.Drawing.Point(0, 0)
$header.Size = New-Object System.Drawing.Size(900, 124)
$header.Anchor = 'Top,Left,Right'
$form.Controls.Add($header)

# 状态卡片：游戏路径 / 敌人随机结果 / 上次启动
function New-Card([string]$Caption, [string]$Glyph, [int]$X) {
    $c = New-Object DarkReforgedUI.DrCard
    $c.Caption = $Caption
    $c.Glyph = $Glyph
    $c.Font = $font
    $c.Location = New-Object System.Drawing.Point($X, 140)
    $c.Size = New-Object System.Drawing.Size(276, 64)
    $form.Controls.Add($c)
    return $c
}
$cardPath = New-Card '游戏路径' ([string][char]0xE7FC) 24
$cardRand = New-Card '敌人随机' ([string][char]0xE8B1) 312
$cardLast = New-Card '上次启动' ([string][char]0xE823) 600

$buttons = New-Object System.Collections.Generic.List[System.Windows.Forms.Button]
function New-Btn([string]$Text, [int]$X, [int]$Y, [int]$W, [int]$H, [string]$Tip, $Font, [string]$Look = 'Secondary', [string]$Glyph = '', [string]$Sub = '') {
    $b = New-Object DarkReforgedUI.DrButton
    $b.Look = [DarkReforgedUI.Kind]$Look
    $b.Glyph = $Glyph
    $b.Sub = $Sub
    $b.Text = $Text
    $b.Location = New-Object System.Drawing.Point($X, $Y)
    $b.Size = New-Object System.Drawing.Size($W, $H)
    if ($Font) { $b.Font = $Font }
    if ($Tip) { $ToolTipCtl.SetToolTip($b, $Tip) }
    $form.Controls.Add($b)
    $buttons.Add($b)
    return $b
}

$gPlay = [string][char]0xE768
$bLaunchV = New-Btn '一键启动' 24 222 420 82 '在原版上生成重随包（敌人血量分档、Boss 奖励、局内难度等）后启动。' $fontB 'Primary' $gPlay '无敌人随机'
$bLaunchR = New-Btn '一键启动' 456 222 420 82 '在最近一次随机器输出（敌人随机）上生成重随包后启动。还没有随机器输出时，会先自动随机化一次敌人（期间不要点随机器窗口）。' $fontB 'Primary' $gPlay '敌人随机'
$bRandEnemy = New-Btn '一键重随敌人' 24 316 420 58 ("换一个新种子重新随机化敌人（不启动游戏，约 2~5 分钟）。`r`n" +
    "设置：在随机器里改过就按上一次的设置，没用过随机器就按整合包默认（只开敌人随机）。`r`n" +
    "随机器窗口会自动打开、点按钮、完成后自动关闭——期间不要点随机器窗口，也不要关它。") $fontM 'Secondary' ([string][char]0xE8B1) '换一个新种子，不启动游戏'
$bRandomizer = New-Btn '打开随机器' 456 316 420 58 '会先显示操作步骤（敌人随机要开，物品随机可开可不开）。在这里改过的设置，以后「一键重随敌人」也会沿用。' $fontM 'Secondary' ([string][char]0xE713) '自己配置敌人 / 物品随机'

$toolsLabel = New-Object System.Windows.Forms.Label
$toolsLabel.Text = '工具'
$toolsLabel.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 8.5)
$toolsLabel.ForeColor = $Thm::FgMuted
$toolsLabel.AutoSize = $true
$toolsLabel.Location = New-Object System.Drawing.Point(26, 390)
$form.Controls.Add($toolsLabel)

$small = @(
    @('游戏路径', 0xE8B7, '设置 / 修改游戏目录（包含 Game\eldenring.exe 的那一层）'),
    @('备份存档', 0xE74E, '把暗黑重铸存档（ER0000.rng）和角色记录（存档文件夹里的 DarkReforged\角色记录）复制到「存档备份」文件夹'),
    @('恢复存档', 0xE81C, '回到上次启动游戏前的样子，之后玩的进度会丢失（确认前会显示差多少）；每次启动前自动备份，留最近 10 份，也可以手动挑别的备份。只是遇到问题的话，先点「导出诊断包」'),
    @('重随设置', 0xE713, '用记事本打开重随规则 settings.json（敌人血量、Boss 奖励、局内难度等）'),
    # 以前叫「一次性重随」（用户 2026-11-12 改名；新界面里放在「打开随机器」原来的位置，打开随机器挪进工具）
    @('一键重随物品', 0xE72C, '骨灰的位置、开局装备、开局遗物只在第一次启动时抽一次，之后固定。点这里后，下次启动会重新抽一次（之后再固定）；只对之后新建的角色生效'),
    # 联机（Seamless Co-op）先不显示（用户 2026-11-10「先把联机隐藏不显示了」）：按钮去掉，Show-CoopMenu 和 launcher.ps1 的 -Action coop* 都还在，
    # 想恢复就把下面这一行放回来（位置换成「敌人设置」）
    # @('联机', 0xE716, '和朋友联机（Seamless Co-op，要自己下载）：联机启动、复制 / 导入联机随机码。联机存档 ER0000.rngcoop 和单机存档分开'),
    @('敌人设置', 0xE9E9, '调整敌人随机：精英怪的多少、头目会不会出现在普通敌人的位置。改完点「一键重随敌人」生效'),
    @('报告 / 日志', 0xE8A5, '打开上次重随报告和 YAFSML 日志所在位置'),
    @('导出诊断包', 0xE7B8, '出问题时点这里：把日志、配置、游戏版本和 Windows 崩溃记录打成一个 zip 放到桌面，发给帮你排查的人（不含存档）'),
    @('常见问题', 0xE897, '怎么重新随机敌人、怎么回退整合包版本、自动备份的存档在哪'),
    @('更新日志', 0xE8FD, '打开整合包的「更新日志.txt」：每个版本改了什么'),
    @('导入更新包', 0xE896, '选下载好的更新包（Darkforge_v旧_to_v新_update.zip，不用解压），只替换改了的文件；改动前自动备份，失败自动还原，你改过的设置会保留'),
    @('检查更新', 0xE895, '联网看看有没有新版本；有的话下载更新包并更新（只替换改了的文件，改动前自动备份，失败自动还原，你改过的设置会保留）')
)
$smallBtns = @{}
for ($i = 0; $i -lt $small.Count; $i++) {            # 两排，每排 6 个（2026-11-10 加了「导入更新包」，5 个一排放不下；2026-11-11 加了「检查更新」，正好 12 个）
    $smallBtns[$small[$i][0]] = New-Btn $small[$i][0] (24 + ($i % 6) * 143) (412 + [Math]::Floor($i / 6) * 48) 137 40 $small[$i][2] $fontS 'Ghost' ([string][char]$small[$i][1])
}

$logCard = New-Object DarkReforgedUI.DrCard
$logCard.Header = $true
$logCard.Caption = '运行日志'
$logCard.Font = $font
$logCard.BackColor = $Thm::LogBg
$logCard.Location = New-Object System.Drawing.Point(24, 514)
$logCard.Size = New-Object System.Drawing.Size(852, 286)
$logCard.Anchor = 'Top,Bottom,Left,Right'
$logCard.Padding = New-Object System.Windows.Forms.Padding(14, 32, 4, 10)
$form.Controls.Add($logCard)

$logBox = New-DarkText $true
$logBox.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
$logBox.Dock = 'Fill'
$logCard.Controls.Add($logBox)

function Add-Log([string]$Text) {
    if ($script:PlayerView) { [void]$script:ViewLines.Add($Text); Show-ViewLines } else { $logBox.AppendText($Text + "`r`n") }
}

function Update-Status {
    $latest = Get-LatestRandom
    $root = Get-GameRoot
    if ($root) {
        $cardPath.Value = $root; $cardPath.Accent = $Thm::Gold
        $ToolTipCtl.SetToolTip($cardPath, $root)
    } else {
        $cardPath.Value = '未设置'; $cardPath.Accent = $Thm::Warn
        $ToolTipCtl.SetToolTip($cardPath, '未设置（第一次启动时会自动检测，找不到会让你选）')
    }
    # 没装随机器（正式发布不带）：敌人随机那几个按钮的副标题写明，点了弹说明（Confirm-Randomizer）
    $rs = Get-RandomizerStatus
    $bLaunchR.Sub = $(if ($rs.Ok) { '敌人随机' } else { '敌人随机 · 要先装随机器' })
    $bRandEnemy.Sub = $(if ($rs.Ok) { '换一个新种子，不启动游戏' } else { '要先装随机器' })
    $bRandomizer.Sub = $(if ($rs.Ok) { '自己配置敌人 / 物品随机' } else { '要先装随机器' })
    foreach ($b in @($bLaunchR, $bRandEnemy, $bRandomizer)) { $b.Invalidate() }
    if (-not $rs.Ok) {
        $cardRand.Value = '没装随机器'; $cardRand.Accent = $Thm::FgMuted
        $ToolTipCtl.SetToolTip($cardRand, '敌人随机要先装随机器（整合包不带），点「一键启动（敌人随机）」看怎么装。不装也能玩无敌人随机。')
    } elseif ($latest -and $latest.Merged) {
        $cardRand.Value = $latest.Time.ToString('yyyy-MM-dd HH:mm') + ' · 要重新随机化'; $cardRand.Accent = $Thm::Warn
        $ToolTipCtl.SetToolTip($cardRand, '随机器输出：' + $latest.Time.ToString('yyyy-MM-dd HH:mm') + '（旧版本合并别的包做的，玩敌人随机前会先重新随机化一次）')
    } elseif ($latest -and -not $latest.HasEnemy -and -not $latest.HasItem) {
        $cardRand.Value = $latest.Time.ToString('yyyy-MM-dd HH:mm') + ' · 没勾敌人随机'; $cardRand.Accent = $Thm::Warn
        $ToolTipCtl.SetToolTip($cardRand, '随机器输出：' + $latest.Time.ToString('yyyy-MM-dd HH:mm') + '（没有勾敌人随机！）')
    } elseif ($latest) {
        $what = (@($(if ($latest.HasEnemy) { '敌人随机' }), $(if ($latest.HasItem) { '物品随机' })) | Where-Object { $_ }) -join ' + '
        $cardRand.Value = $latest.Time.ToString('yyyy-MM-dd HH:mm') + $(if ($latest.HasItem) { ' · 含物品' } else { '' }); $cardRand.Accent = $Thm::Ok
        $ToolTipCtl.SetToolTip($cardRand, '随机器输出：' + $latest.Time.ToString('yyyy-MM-dd HH:mm') + '（' + $what + '）')
    } else {
        $cardRand.Value = '还没有'; $cardRand.Accent = $Thm::FgMuted
        $ToolTipCtl.SetToolTip($cardRand, '还没有随机器输出（点「一键启动（敌人随机）」会先自动随机化一次）')
    }
    $rep = Join-Path (Get-RerollPack) 'reroll_report.txt'
    if (Test-Path -LiteralPath $rep) {
        $h = Get-Content -LiteralPath $rep -TotalCount 3 -Encoding UTF8
        $when = (($h | Where-Object { $_ -like '时间：*' }) -replace '^时间：', '')
        $cardLast.Value = [string]$when
        $cardLast.Accent = $Thm::Gold
        $ToolTipCtl.SetToolTip($cardLast, '上次启动：' + $when)
    } else {
        $cardLast.Value = '还没启动过'
        $cardLast.Accent = $Thm::FgMuted
        $ToolTipCtl.SetToolTip($cardLast, '还没有启动过')
    }
    foreach ($c in @($cardPath, $cardRand, $cardLast)) { $c.Invalidate() }
}

# ---------------------------------------------------------------- 后台跑启动器，输出写到临时文件，定时读回窗口
$script:Running = $false
$script:Proc = $null
$script:LogFile = Join-Path $env:TEMP 'darkforge_gui_run.log'
# 这次运行的步骤写成的脚本（powershell -File 跑它）；运行进程的标准输出 / 错误流 → 日志文件的后台拷贝和文件流。
# 脚本放 launcher\logs，不放系统临时文件夹（用户 2026-11-14：从临时文件夹跑脚本也是安全软件常拦的写法）
$script:RunScript = Join-Path $LauncherDir 'logs\gui_run.ps1'
$script:RunCopy = $null
$script:RunStreams = @()
$script:LogLen = 0
# 启动、重随敌人时日志框只显示给玩家看的进度（launcher.ps1 的 Write-Player，开头 §）和 [错误]（用户 2026-11-05「只需要让玩家知道游戏正在正常加载就行」）；
# 完整输出照样在 $script:LogFile 和 launcher\logs\（「报告 / 日志」按钮打开）
$script:PlayerView = $false
$script:SawError = $false
# 玩家视图时日志框的内容就是这几行：进度条（launcher.ps1 / reroll\progress.py 打的「§% 百分比」）要改已经显示的那一行，整段重画（行数很少）
$script:ViewLines = New-Object System.Collections.ArrayList
$script:BarLine = -1          # 进度条是第几行（第一次收到「§%」时另起一行，一般在「正在生成这一局的游戏数据……」下面；用户 2026-11-05「进度条换行」）
function Show-ViewLines {
    $logBox.Text = (@($script:ViewLines) -join "`r`n") + "`r`n"
    $logBox.SelectionStart = $logBox.TextLength
    $logBox.ScrollToCaret()
}
function Get-BarText([int]$Pct) {
    $p = [Math]::Max(0, [Math]::Min(100, $Pct))
    $n = [int][Math]::Round($p / 10.0)
    return ('■' * $n) + ('□' * (10 - $n)) + ' ' + $p + '%'
}

function Set-Busy([bool]$Busy) {
    $script:Running = $Busy
    foreach ($b in $buttons) { $b.Enabled = -not $Busy }
    $header.Busy = $Busy
    $header.Badge = $(if ($Busy) { '运行中' } elseif ($PackVersion) { 'v' + $PackVersion } else { '' })
    $header.Invalidate()
    if (-not $Busy) { Update-Status }
}

function Start-LauncherRun([string]$Title, [string[]]$Calls) {
    if ($script:Running) { return }
    $q = { param($s) "'" + ($s -replace "'", "''") + "'" }
    $body = '[Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; '
    foreach ($c in $Calls) {
        # 以 ! 开头的步骤失败（启动器 exit 非 0）就不再做后面的步骤（如：随机化失败就不启动游戏）
        if ($c.StartsWith('!')) { $body += '$global:LASTEXITCODE = 0; & ' + (& $q $Launcher) + ' ' + $c.Substring(1) + '; if ($LASTEXITCODE) { exit $LASTEXITCODE }; ' }
        else { $body += '& ' + (& $q $Launcher) + ' ' + $c + '; ' }
    }
    # 步骤写成普通的脚本文件，这里直接用 powershell -File 跑（用户 2026-11-14：以前用 cmd 隐藏启动 powershell -EncodedCommand、输出靠 cmd 重定向，
    # 火绒「系统加固」把它当「利用PowerShell执行可疑脚本」拦下）。带 BOM：PowerShell 5.1 才按 UTF-8 读脚本（路径里可能有中文）
    [void][System.IO.Directory]::CreateDirectory((Split-Path -Parent $script:RunScript))
    [System.IO.File]::WriteAllText($script:RunScript, $body, (New-Object System.Text.UTF8Encoding($true)))
    [System.IO.File]::WriteAllText($script:LogFile, '', $Utf8NoBom)
    $script:LogLen = 0
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'powershell.exe'
    $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $script:RunScript + '"'
    # 启动器的提示（Write-Host）和 Python 输出都在标准输出；错误流里只有 PowerShell 的 CLIXML 进度信息，单独存一份不显示。
    # 两个都用管道接住、后台原样拷进文件（Read-RunLog 照旧定时读日志文件）；标准输入马上关掉（同以前的 < nul）
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = $true
    $psi.WorkingDirectory = $LauncherDir
    $logBox.Clear()
    $script:PlayerView = [bool](@($Calls | Where-Object { $_ -match '-Action (vanilla|randenemy|rand|coopvanilla|coop|update|checkupdate|autoupdate)(\s|$)' }).Count)
    $script:SawError = $false
    $script:ViewLines.Clear()
    $script:BarLine = -1
    Add-Log ('=== ' + $Title + ' ===')
    Set-Busy $true
    $script:Proc = [System.Diagnostics.Process]::Start($psi)
    $script:Proc.StandardInput.Close()
    # 文件流不带缓冲（缓冲 1 字节）：拷进来的马上落到文件里，日志框和进度条照样实时；共享读写，Read-RunLog 能同时读
    $out = New-Object System.IO.FileStream($script:LogFile, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite, 1)
    $err = New-Object System.IO.FileStream(($script:LogFile + '.err'), [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite, 1)
    $script:RunStreams = @($out, $err)
    $script:RunCopy = [System.Threading.Tasks.Task[]]@($script:Proc.StandardOutput.BaseStream.CopyToAsync($out), $script:Proc.StandardError.BaseStream.CopyToAsync($err))
    $timer.Start()
}

# 运行进程结束后：等后台拷贝把最后的输出写完（最多 3 秒：启动器拉起的进程如果继承了管道、一直开着，就不等它），关掉文件
function Close-RunStreams {
    if ($script:RunCopy) { try { [void][System.Threading.Tasks.Task]::WaitAll($script:RunCopy, 3000) } catch { } }
    foreach ($f in $script:RunStreams) { try { $f.Dispose() } catch { } }
    $script:RunCopy = $null
    $script:RunStreams = @()
}

# 每次把整个日志读回来，只追加还没显示过的完整行（$Final 时连最后半行也追加）
function Read-RunLog([bool]$Final = $false) {
    try {
        $fs = [System.IO.File]::Open($script:LogFile, 'Open', 'Read', 'ReadWrite')
        try {
            $buf = New-Object byte[] ($fs.Length)
            [void]$fs.Read($buf, 0, $buf.Length)
        } finally { $fs.Dispose() }
        $text = [Text.Encoding]::UTF8.GetString($buf)
        $end = if ($Final) { $text.Length } else { $text.LastIndexOf("`n") + 1 }
        if ($end -gt $script:LogLen) {
            $add = $text.Substring($script:LogLen, $end - $script:LogLen)
            if ($script:PlayerView) {
                $changed = $false
                foreach ($l in (($add -replace "`r", '') -split "`n")) {
                    if ($l -match '^§% (\d+)\s*$') {
                        if ($script:BarLine -lt 0) { $script:BarLine = $script:ViewLines.Add('') }
                        $script:ViewLines[$script:BarLine] = '    ' + (Get-BarText ([int]$Matches[1]))
                        $changed = $true
                    }
                    elseif ($l.StartsWith('§ ')) { [void]$script:ViewLines.Add($l.Substring(2)); $changed = $true }
                    elseif ($l -match '\[错误\]') { $script:SawError = $true; [void]$script:ViewLines.Add($l.Trim()); $changed = $true }
                }
                if ($changed) { Show-ViewLines }
            } else {
                $logBox.AppendText(($add -replace "`r", '' -replace "`n", "`r`n"))
            }
            $script:LogLen = $end
        }
    } catch { }
}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 400
$timer.Add_Tick({
    Read-RunLog
    if ($script:Proc -and $script:Proc.HasExited) {
        Close-RunStreams
        Read-RunLog $true
        $timer.Stop()
        $script:Proc = $null
        if ($script:PlayerView -and $script:SawError) { Add-Log '（完整的运行输出在「报告 / 日志」打开的 logs 文件夹里，出问题时点「导出诊断包」发过来）' }
        Add-Log '=== 完成 ==='
        Set-Busy $false
        if ($script:AfterRun) { $f = $script:AfterRun; $script:AfterRun = $null; & $f }    # 这次运行结束后要做的事（导入更新包后重开启动器）
    }
})

# 弹窗都用 ui.ps1 的 Show-DrDialog（和启动器同样的暗色 + 金色，不用系统白色的 MessageBox）
function Show-Info([string]$Text, [string]$Title = '暗黑重铸') {
    [void](Show-DrDialog $Text $Title @('确定') 0 0 'info' $form)
}

# 检测到 eldenring.exe 时列出详情（进程号、启动时间、路径、有没有窗口），让玩家选择强制结束：
# 崩溃后残留在后台、Windows 开机自动重开等情况下，进程还在但游戏其实没开，以前只能重启电脑
function Get-GameProcText {
    $boot = $null
    try { $boot = (Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime } catch { }
    $lines = @()
    foreach ($p in @(Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue)) {
        $start = $null; $path = $null
        try { $start = $p.StartTime } catch { }
        try { $path = $p.Path } catch { }
        if (-not $path) {
            try { $path = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $p.Id) -ErrorAction Stop).ExecutablePath } catch { }
        }
        $win = if ($p.MainWindowHandle -ne [IntPtr]::Zero) { '有窗口' } else { '没有窗口（后台）' }
        $resp = try { if ($p.Responding) { '有响应' } else { '无响应' } } catch { '未知' }
        $lines += ('  进程号 ' + $p.Id + '，启动于 ' + $(if ($start) { $start.ToString('MM-dd HH:mm:ss') } else { '未知' }) +
                   '，' + $win + '，' + $resp + "`r`n  路径：" + $(if ($path) { $path } else { '读不到（可能是管理员权限启动的）' }))
    }
    if ($boot) { $lines += ('  （电脑本次开机时间：' + $boot.ToString('MM-dd HH:mm:ss') + '）') }
    return ($lines -join "`r`n")
}

# 返回 $true = 游戏没在运行（或已按玩家确认强制结束），可以继续
function Confirm-GameClosed([string]$Why) {
    if (-not (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue)) { return $true }
    $msg = "检测到 eldenring.exe 还在运行：`r`n`r`n" + (Get-GameProcText) + "`r`n`r`n" + $Why + "`r`n`r`n" +
           "如果游戏其实已经关了（崩溃后残留在后台、看不到窗口等），点「是」强制结束这个进程再继续；`r`n" +
           "正在玩的话点「否」，先在游戏里正常退出（系统 → 退出游戏）。强制结束正在玩的游戏，没存档的进度会丢。"
    if ((Show-DrDialog $msg '暗黑重铸 · 游戏还在运行' @('是', '否') 1 1 'warn' $form) -ne 0) { return $false }
    Add-Log ('强制结束 eldenring.exe：' + ((@(Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue) | ForEach-Object { $_.Id }) -join ', '))
    foreach ($p in @(Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue)) { try { $p.Kill() } catch { } }
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-Process -Name 'eldenring' -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Milliseconds 500
    }
    Show-Info ("没能结束 eldenring.exe（可能是以管理员身份启动的）。`r`n`r`n" +
               "请打开任务管理器（Ctrl+Shift+Esc）→「详细信息」，找到 eldenring.exe 右键「结束任务」；还不行就重启电脑。")
    return $false
}

function Confirm-Box([string]$Text, [string]$Title) {
    return ((Show-DrDialog $Text $Title @('确定', '取消') 0 1 'question' $form) -eq 0)
}

# ---------------------------------------------------------------- 存档备份 / 恢复 / 版本提醒
# 存档在 %APPDATA%\EldenRing\<SteamID>，角色记录、启动前备份在 %APPDATA%\EldenRing\DarkReforged（backup.ps1）；每次启动前自动备份一份
$VersionFile = Join-Path $LauncherDir 'version.txt'
. (Join-Path $LauncherDir 'backup.ps1')      # 启动前备份 / 恢复（和启动器共用）
. (Join-Path $LauncherDir 'randomize.ps1')   # 一键重随敌人：用哪份设置（和启动器共用）
. (Join-Path $LauncherDir 'coopcode.ps1')    # 联机码压缩（DR3 ↔ DR4z，和启动器共用）
. (Join-Path $LauncherDir 'usermods.ps1')    # 网页界面「模组」：mods 文件夹、YAFSML自定义.ini（和启动器共用）
$LastVerFile = $RngVersionFile
$OldVerFile = Join-Path $RngSaveRoot 'DarkReforged_version.txt'   # 2026-10-29 以前的位置（游戏开着时还没搬过来）

function Get-Ver([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $t = ([string](Get-Content -LiteralPath $Path -TotalCount 1 -Encoding UTF8)).Trim()
    try { return [version]$t } catch { return $null }
}

# 整合包版本和这台电脑上次用的版本不一样时（打开窗口时，启动前再兜底检查一次）：
#   升级 → 不弹窗（用户 2026-11-11「启动器现在更新后不用再弹已更新的窗了」）：记下版本，运行日志里说一句，
#          新界面打开后弹一条提示、切到「更新日志」页（webui.ps1 读 $script:UpdatedNote）
#   降级 → 警告（旧版本可能看不懂新版本的角色记录）；启动时还要再确认一次
$script:UpdatedNote = $null

# 对话框里的一块只读文字（圆角卡片里放一个无边框文本框）
function New-TextCard([int]$X, [int]$Y, [int]$W, [int]$H, [string]$Text, [string]$Anchor = 'Top,Left') {
    $card = New-Object DarkReforgedUI.DrCard
    $card.Header = $true
    $card.Location = New-Object System.Drawing.Point($X, $Y)
    $card.Size = New-Object System.Drawing.Size($W, $H)
    $card.Anchor = $Anchor
    $card.Padding = New-Object System.Windows.Forms.Padding(14, 12, 4, 10)
    $tb = New-DarkText
    $tb.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10)
    $tb.Dock = 'Fill'
    $tb.Text = $Text
    $card.Controls.Add($tb)
    return @($card, $tb)
}

function Show-TextDialog([string]$Title, [string]$Text, [string]$OkText = '我已了解') {
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = $Title
    $dlg.Font = $font
    $dlg.Size = New-Object System.Drawing.Size(700, 340)
    $dlg.StartPosition = 'CenterParent'
    $dlg.FormBorderStyle = 'FixedDialog'
    $dlg.MaximizeBox = $false
    $dlg.MinimizeBox = $false
    Set-DarkForm $dlg
    $card, $tb = New-TextCard 12 12 660 222 $Text
    $dlg.Controls.Add($card)
    $ok = New-DlgBtn $OkText 532 246 140 36 $true
    $ok.DialogResult = 'OK'
    $dlg.Controls.Add($ok)
    $dlg.AcceptButton = $ok
    $dlg.Add_Shown({ $tb.SelectionLength = 0; $ok.Focus() })
    [void]$dlg.ShowDialog($form)
}

# 返回 'same' / 'fresh' / 'upgrade' / 'downgrade'（以及版本）
function Get-VersionState {
    $cur = Get-Ver $VersionFile
    if (-not $cur) { return @{ Kind = 'same' } }
    $last = Get-Ver $LastVerFile
    if (-not $last) { $last = Get-Ver $OldVerFile }
    if ($last -and $last -eq $cur) { return @{ Kind = 'same'; Cur = $cur } }
    if ($last -and $last -gt $cur) { return @{ Kind = 'downgrade'; Cur = $cur; Last = $last } }
    if (-not $last) { return @{ Kind = 'fresh'; Cur = $cur } }
    return @{ Kind = 'upgrade'; Cur = $cur; Last = $last }
}

function Get-DowngradeText($v) {
    return ("这台电脑上已经用过更新的整合包 " + $v.Last + "，现在打开的是旧版本 " + $v.Cur + "。`r`n`r`n" +
            "旧版本可能看不懂新版本记下的角色记录（装备、锁定、难度等），用它启动可能出错。`r`n`r`n" +
            "强烈建议关掉这个窗口，改用新版本的整合包启动。")
}

# 打开窗口时
function Show-VersionNotice {
    $v = Get-VersionState
    if ($v.Kind -in @('fresh', 'upgrade')) { New-Item -ItemType Directory -Force -Path $RngDataDir | Out-Null }
    switch ($v.Kind) {
        'fresh' { [System.IO.File]::WriteAllText($LastVerFile, [string]$v.Cur + "`r`n", $Utf8NoBom) }   # 第一次用，不用提醒
        'upgrade' {
            [System.IO.File]::WriteAllText($LastVerFile, [string]$v.Cur + "`r`n", $Utf8NoBom)
            $script:UpdatedNote = '已更新到 v' + $v.Cur + '（原来是 v' + $v.Last + '），改了什么见「更新日志」'
            Add-Log $script:UpdatedNote
        }
        'downgrade' { [void](Show-DrDialog (Get-DowngradeText $v) '版本比这台电脑上用过的旧' @('我已了解') 0 0 'warn' $form) }
    }
}

# 启动前兜底：降级要再确认；升级的记下版本（窗口打开时被跳过的话）
function Test-VersionChange {
    $v = Get-VersionState
    if ($v.Kind -eq 'downgrade') {
        return ((Show-DrDialog ((Get-DowngradeText $v) + "`r`n仍然要用旧版本启动吗？") '版本比这台电脑上用过的旧' @('是', '否') 1 1 'warn' $form) -eq 0)
    }
    if ($v.Kind -eq 'upgrade' -or $v.Kind -eq 'fresh') { Show-VersionNotice }
    return $true
}

# 恢复：默认恢复最近一次「启动前备份」，也可以手动从所有备份里挑；存档和角色记录一起换
function Get-BackupText($b) {
    $what = @()
    if ($b.Saves -gt 0) { $what += ('存档 ' + $b.Saves + ' 个') }
    if ($b.Records -gt 0) { $what += ('角色记录 ' + $b.Records + ' 个') }
    return ('{0}   {1}{2}   （{3}）' -f $b.Time.ToString('yyyy-MM-dd HH:mm:ss'), $b.Tag, $(if ($b.Mode) { ' · ' + $b.Mode } else { '' }), ($what -join ' + '))
}

# 恢复前算差别（launcher\\reroll\\savediff.py，只读）：现在 → 恢复后每个角色的等级、游戏时间，一行一个；算不出来返回空，不挡恢复
function Get-RestoreDiffLines($Backup) {
    $py = Join-Path $LauncherDir 'python\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { return @() }
    try {
        $out = & $py -X utf8 (Join-Path $LauncherDir 'reroll\savediff.py') $Backup.Dir $RngSaveRoot 2>$null
        if ($LASTEXITCODE -ne 0) { return @() }
        $j = (@($out) | Select-Object -Last 1) | ConvertFrom-Json     # PS 5.1 把整个数组当一个对象输出，要再展开
        return @($j | ForEach-Object { [string]$_ })
    } catch { return @() }
}

# 恢复确认框的文字：恢复成什么、差多少
function Get-RestoreWarnText($Backup) {
    $diff = @(Get-RestoreDiffLines $Backup)
    $what = if ($diff.Count) { "和现在相比：`r`n" + (($diff | ForEach-Object { '    ' + $_ }) -join "`r`n") } else { '（读不出这份备份和现在差多少）' }
    return ("存档和角色记录都会换成这份备份，备份之后玩的进度会丢失：`r`n`r`n    " + (Get-BackupText $Backup) + "`r`n`r`n" + $what + "`r`n`r`n" +
            "现在的会先自动存成「恢复前」备份，恢复错了还能选它换回来。只是遇到问题的话，先点「导出诊断包」，不用恢复。")
}

function Invoke-Restore($Pick) {
    $done = @(Restore-RngBackup $Pick)
    Add-Log ('已恢复（' + ($done -join '、') + '）：' + (Get-BackupText $Pick))
    Show-Info ("已恢复：" + ($done -join '、') + "`r`n" + (Get-BackupText $Pick) + "`r`n`r`n" +
               "恢复前的存档和记录已存成「恢复前」备份（" + $RngBackupDir + "），恢复错了可以再选它换回来。")
}

# 手动选一份备份（恢复存档第二步）：返回第几份，取消返回 -1。新界面开着时 webui.ps1 换成页面里的列表
$BackupPickHelp = "启动前 = 每次启动游戏前自动存的；恢复前 = 每次恢复前自动存的；存档备份 = 点「备份存档」存的。`r`n" +
                  "存档和角色记录一起换回去，那之后的游戏进度会丢失（现在的会先自动备份）。"
function Show-BackupPick($Items) {
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = '恢复存档：手动选择备份'
    $dlg.Font = $font
    $dlg.Size = New-Object System.Drawing.Size(720, 460)
    $dlg.StartPosition = 'CenterParent'
    $dlg.FormBorderStyle = 'FixedDialog'
    $dlg.MaximizeBox = $false
    Set-DarkForm $dlg
    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text = $BackupPickHelp
    $lbl.ForeColor = $Thm::FgDim
    $lbl.Location = New-Object System.Drawing.Point(14, 12)
    $lbl.Size = New-Object System.Drawing.Size(680, 48)
    $dlg.Controls.Add($lbl)
    $card = New-Object DarkReforgedUI.DrCard
    $card.Header = $true
    $card.Location = New-Object System.Drawing.Point(12, 64)
    $card.Size = New-Object System.Drawing.Size(682, 290)
    $card.Padding = New-Object System.Windows.Forms.Padding(6, 6, 6, 6)
    $lb = New-Object System.Windows.Forms.ListBox
    $lb.Dock = 'Fill'
    $lb.BorderStyle = 'None'
    $lb.BackColor = $Thm::Surface
    $lb.ForeColor = $Thm::Fg
    $lb.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9.5)
    $lb.DrawMode = 'OwnerDrawFixed'
    $lb.ItemHeight = [int]($lb.Font.Height * 1.7)
    $lb.IntegralHeight = $false
    $lb.Add_HandleCreated({ param($s, $e) [DarkReforgedUI.Theme]::DarkScroll($s) })
    $lb.Add_DrawItem({
        param($s, $e)
        if ($e.Index -lt 0) { return }
        $sel = ($e.State -band [System.Windows.Forms.DrawItemState]::Selected) -ne 0
        $br = New-Object System.Drawing.SolidBrush($(if ($sel) { [System.Drawing.Color]::FromArgb(58, 50, 34) } else { $Thm::Surface }))
        $e.Graphics.FillRectangle($br, $e.Bounds)
        $br.Dispose()
        $y = $e.Bounds.Y + [int](($e.Bounds.Height - $e.Font.Height) / 2)
        [System.Windows.Forms.TextRenderer]::DrawText($e.Graphics, [string]$s.Items[$e.Index], $e.Font,
            (New-Object System.Drawing.Point(($e.Bounds.X + 10), $y)), $(if ($sel) { $Thm::GoldHi } else { $Thm::Fg }))
    })
    foreach ($it in $Items) { [void]$lb.Items.Add((Get-BackupText $it)) }
    $lb.SelectedIndex = 0
    $card.Controls.Add($lb)
    $dlg.Controls.Add($card)
    $ok = New-DlgBtn '恢复选中的这份' 424 368 150 36 $true
    $ok.DialogResult = 'OK'
    $cancel = New-DlgBtn '取消' 582 368 112 36
    $cancel.DialogResult = 'Cancel'
    $dlg.Controls.AddRange(@($ok, $cancel))
    $dlg.AcceptButton = $ok
    $dlg.CancelButton = $cancel
    if ($dlg.ShowDialog($form) -ne 'OK' -or $lb.SelectedIndex -lt 0) { return -1 }
    return $lb.SelectedIndex
}

function Show-RestoreSaves {
    if (-not (Confirm-GameClosed '恢复存档要在游戏关闭后做。')) { return }
    $items = @(Get-RngBackups (Join-Path $Paly '存档备份') | Where-Object { $_.Saves -gt 0 })
    if ($items.Count -eq 0) { Show-Info ('没有找到可以恢复的备份。' + "`r`n" + '（以后每次启动游戏前会自动备份到 ' + $RngBackupDir + '）'); return }

    # 第一步：最近一次启动前的备份
    $last = $items | Where-Object { $_.Tag -eq '启动前' } | Select-Object -First 1
    if ($last) {
        # 默认按钮是取消：回车不会丢进度
        $r = Show-DrDialog (Get-RestoreWarnText $last) '恢复到上次启动前' @('丢弃进度并恢复', '手动选择…', '取消') 2 2 'warn' $form
        if ($r -eq 0) { Invoke-Restore $last; return }
        if ($r -ne 1) { return }
    }

    # 第二步：手动选
    $i = Show-BackupPick $items
    if ($i -lt 0) { return }
    $pick = $items[$i]
    if ((Show-DrDialog (Get-RestoreWarnText $pick) '确认恢复存档' @('确认恢复', '取消') 1 1 'warn' $form) -ne 0) { return }
    Invoke-Restore $pick
}

# 游戏路径：先让启动器自动检测（只有一个候选时会记住），还没有就弹选择框；保证子进程不会停在键盘输入上
function Ensure-GameRoot {
    if (Get-GameRoot) { return $true }
    # 不开窗口地跑一次（用户 2026-11-14：不再用 Start-Process -WindowStyle Hidden，安全软件把隐藏窗口的 powershell 当可疑脚本）；标准输入马上关掉
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'powershell.exe'
    $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $Launcher + '" -Action list'
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.WorkingDirectory = $LauncherDir
    try { $p = [System.Diagnostics.Process]::Start($psi); $p.StandardInput.Close(); $p.WaitForExit() } catch { }
    if (Get-GameRoot) { return $true }
    return (Select-GameRoot '没有自动找到游戏，请手动选一下。')
}

# 手动选游戏路径（用户 2026-11-16「选的时候提示一定要选中 game 文件夹 并给出路径示意」）：
# 选中 Game 文件夹（里面有 eldenring.exe）就记它的上一层；选成 ELDEN RING 那一层也认。选错了说明一下再让选，点取消才算没选
# 选择框上面只有 3 行、约 390 像素宽，长路径会被截掉：框里只写到 steamapps 后面，完整的例子在选错时的提示里
$GamePickHint = '请选中游戏的 Game 文件夹（里面有 eldenring.exe）' + "`r`n" + '例如 …\steamapps\common\ELDEN RING\Game'
$GamePickWrong = '要选的是游戏的 Game 文件夹（里面有 eldenring.exe），Steam 版一般在：' + "`r`n" +
    '    C:\Program Files (x86)\Steam\steamapps\common\ELDEN RING\Game' + "`r`n" +
    '    D:\SteamLibrary\steamapps\common\ELDEN RING\Game（游戏装在别的盘时）' + "`r`n`r`n" +
    '不知道装在哪：在 Steam 库里右键艾尔登法环 →「管理」→「浏览本地文件」，打开的文件夹里的 Game 就是。'

# 选择框一打开先定位到哪：已经设过就是那个 Game 文件夹，没设过就是 Steam 的游戏文件夹（steamapps\common）
function Get-GamePickStart {
    $cur = Get-GameRoot
    if ($cur) { return (Join-Path $cur 'Game') }
    try {
        $sp = (Get-ItemProperty -Path 'HKCU:\Software\Valve\Steam' -Name SteamPath -ErrorAction Stop).SteamPath
        $c = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($sp, 'steamapps\common'))
        if ([System.IO.Directory]::Exists($c)) { return $c }
    } catch { }
    return $null
}

function Select-GameRoot([string]$Why = '') {
    while ($true) {
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = $(if ($Why) { $Why + "`r`n" } else { '' }) + $GamePickHint
        $dlg.ShowNewFolderButton = $false
        $start = Get-GamePickStart
        if ($start -and [System.IO.Directory]::Exists($start)) { $dlg.SelectedPath = $start }
        if ($dlg.ShowDialog($form) -ne 'OK') { return $false }
        $path = $dlg.SelectedPath.TrimEnd('\')
        $root = $null
        if (Test-Path -LiteralPath (Join-Path $path 'eldenring.exe')) { $root = Split-Path -Parent $path }
        elseif (Test-Path -LiteralPath (Join-Path $path 'Game\eldenring.exe')) { $root = $path }
        if ($root) {
            [System.IO.File]::WriteAllText($GamePathFile, $root + "`r`n", $Utf8NoBom)
            Add-Log ('游戏路径已设为：' + $root)
            Update-Status
            return $true
        }
        Show-Info ('这个文件夹里没有 eldenring.exe：' + "`r`n" + $path + "`r`n`r`n" + $GamePickWrong) '游戏路径'
    }
}

# 每次启动游戏前：游戏没在运行、路径、版本
function Before-Launch {
    if (-not (Confirm-GameClosed '启动前要重新生成重随包，游戏开着时不能覆盖它正在用的文件。')) {
        return $false
    }
    if (-not (Ensure-GameRoot)) { return $false }
    if (-not (Test-VersionChange)) { return $false }
    return $true
}

# ---------------------------------------------------------------- 死亡以上难度（Boss 改版只在死亡以上加载，dev\boss_mods\README.md）
# settings.json 的 boss_mods 是 auto、开着模组时，单机启动前看存档里有没有死亡以上难度的角色：dark_core 进存档后按格子记在
# 角色记录\boss_slots.txt（还没有这个文件时用旧的 boss_mode.txt 记的最后那个），和存档 ER0000.rng 里现在的角色名对得上才算
# （格子对不上、名字在别的格子也算：格子编号万一和存档的不一样，宁可多问一次）。有就问这次以哪种难度的世界启动，
# 用 -BossWorld high|low 交给 launcher.ps1，选了死亡以上再提醒进游戏后读那个角色；没有就 low。联机开房另外问（Ask-CoopWorld），加入照联机码。
# 进游戏后读的角色和选的难度对不上时，dark_core 在角色周围围屏障、禁止传送、提示重启（barrier.rs）。
function Test-BossAuto {
    try { $bm = ([System.IO.File]::ReadAllText($Settings) | ConvertFrom-Json).boss_mods } catch { return $false }
    if (-not $bm -or [string]$bm.mode -ne 'auto' -or -not $bm.mods) { return $false }
    # 数据也要在（发布的整合包不带 Boss 模组的数据，dev\tools\make_package.py；同 launcher.ps1 的 Get-BossMods）
    foreach ($p in $bm.mods.PSObject.Properties) {
        if (-not $p.Name.StartsWith('_') -and $p.Value -eq $true -and (Test-Path -LiteralPath (Join-Path $LauncherDir ('reroll\data\bossmods\' + $p.Name + '\files')))) { return $true }
    }
    return $false
}

# 存档（单机 ER0000.rng / 联机 $RngCoopSave，最近改过的那份）里各格的角色名：@{格子 = 名字}；读不了返回 $null（不核对）
function Get-SaveSlotNames([string]$File = 'ER0000.rng') {
    $save = @(Get-RngSaveFiles | Where-Object { $_.Name -eq $File } | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
    if (-not $save.Count) { return @{} }
    $py = Join-Path $LauncherDir 'python\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { return $null }
    $code = 'import sys, json; sys.path.insert(0, sys.argv[1]); import erlib; print(json.dumps({str(k): v[0] for k, v in erlib.save_profiles(sys.argv[2]).items()}))'
    try {
        $out = & $py -X utf8 -c $code (Join-Path $LauncherDir 'reroll') $save[0].FullName 2>$null
        $j = (@($out) | Select-Object -Last 1) | ConvertFrom-Json
        $h = @{}
        foreach ($p in $j.PSObject.Properties) { $h[[int]$p.Name] = [string]$p.Value }
        return $h
    } catch { return $null }
}

# 死亡以上的角色：@(@{ Slot; Name })。$Coop = 联机存档的（角色记录\联机\ 里的记录，对联机存档里的角色名）
function Get-HighChars([bool]$Coop = $false) {
    $rows = @()
    $dir = if ($Coop) { Join-Path $RngRecordDir '联机' } else { $RngRecordDir }
    $slots = Join-Path $dir 'boss_slots.txt'
    $rec = Join-Path $dir 'boss_mode.txt'
    try {
        if (Test-Path -LiteralPath $slots) {
            foreach ($l in [System.IO.File]::ReadAllLines($slots, [Text.Encoding]::UTF8)) {
                $f = $l.Split("`t")
                if (-not $l.StartsWith('#') -and $f.Count -ge 4 -and $f[1] -eq '1') { $rows += [pscustomobject]@{ Slot = [int]$f[0]; Name = $f[3] } }
            }
        } elseif (Test-Path -LiteralPath $rec) {
            $kv = @{}
            foreach ($l in [System.IO.File]::ReadAllLines($rec, [Text.Encoding]::UTF8)) { $i = $l.IndexOf("`t"); if ($i -gt 0) { $kv[$l.Substring(0, $i)] = $l.Substring($i + 1) } }
            if ($kv['high'] -eq '1' -and $kv['name']) { $rows += [pscustomobject]@{ Slot = [int]$kv['slot']; Name = $kv['name'] } }
        }
    } catch { return @() }
    $names = Get-SaveSlotNames $(if ($Coop) { $RngCoopSave } else { 'ER0000.rng' })
    if ($null -eq $names) { return $rows }
    $out = @()
    foreach ($r in $rows) {
        if ($names.ContainsKey($r.Slot) -and $names[$r.Slot] -eq $r.Name) { $out += $r; continue }
        $k = @($names.Keys | Where-Object { $names[$_] -eq $r.Name } | Select-Object -First 1)
        if ($k.Count) { $out += [pscustomobject]@{ Slot = [int]$k[0]; Name = $r.Name } }
    }
    return @($out | Sort-Object Slot -Unique)
}

# 返回 '' = 功能没开（不传）、'high' / 'low'、$null = 取消启动
function Ask-BossWorld {
    if (-not (Test-BossAuto)) { return '' }
    $hi = @(Get-HighChars)
    if (-not $hi.Count) { return 'low' }
    $who = (@($hi | ForEach-Object { '「' + $_.Name + '」（第 ' + ($_.Slot + 1) + ' 格）' }) -join '、')
    $msg = "存档里有死亡以上难度的角色：" + $who + "`r`n`r`n要以死亡以上难度启动吗？`r`n`r`n" +
           "· 玩上面这些角色：选「死亡以上难度」。`r`n" +
           "· 玩别的角色：选「普通难度」。`r`n`r`n" +
           "进游戏后读取的角色和这里选的难度对不上时，角色周围会出现屏障、不能传送，要重启游戏重新选择。"
    $r = Show-DrDialog $msg '暗黑重铸 · 选择难度' @('死亡以上难度', '普通难度', '取消') 0 2 'question' $form
    if ($r -eq 0) {
        Show-Info ("进入游戏后，请读取死亡以上难度的角色：" + $who + "。") '暗黑重铸 · 死亡以上难度'
        return 'high'
    }
    if ($r -eq 1) { return 'low' }
    return $null
}

function Get-BossArg($Bw) { if ($Bw) { return ' -BossWorld ' + $Bw } else { return '' } }

# 联机开房选世界（用户 2026-11-17「为什么开始联机没有难度选项」→「需要加难度选项」）：Boss 改版开着时问这次联机用哪种难度的世界，
# 写进联机码（w=），队友点「加入」时照它；默认选房主上次玩的联机角色的难度。返回 '' = 功能没开（不传）、'high' / 'low'、$null = 取消。
# 联机存档里没有死亡以上的角色就不给选死亡以上（用户 2026-11-18「联机也加存档检测 没有死亡以上角色不让开死亡难度房间 … 只是要求房主必须是死亡以上就行了」）：
# 死亡以上的房间只要求房主是死亡以上，队友用普通角色也能加入（dark_core 的 bossmode.rs 对加入的不提示重启）
function Ask-CoopWorld {
    if (-not (Test-BossAuto)) { return '' }
    $hi = @(Get-HighChars $true)
    if (-not $hi.Count) {
        $msg = "联机存档里还没有死亡以上难度的角色，这次只能以普通难度开房。`r`n`r`n" +
               "要开死亡以上难度的房间，房主要先有一个死亡以上难度的联机角色（队友不需要）。"
        $r = Show-DrDialog $msg '暗黑重铸 · 联机难度' @('普通难度开房', '取消') 0 1 'info' $form
        if ($r -eq 0) { return 'low' }
        return $null
    }
    $high = $false
    try {
        $rec = Join-Path (Join-Path $RngRecordDir '联机') 'boss_mode.txt'
        if (Test-Path -LiteralPath $rec) { $high = @([System.IO.File]::ReadAllLines($rec, [Text.Encoding]::UTF8) | Where-Object { $_ -match '^high\t1' }).Count -gt 0 }
    } catch { }
    $who = (@($hi | ForEach-Object { '「' + $_.Name + '」（第 ' + ($_.Slot + 1) + ' 格）' }) -join '、')
    $msg = "这次联机用哪种难度的世界？`r`n`r`n" +
           "· 死亡以上难度：加载 Boss 改版。进游戏后房主请读取死亡以上难度的联机角色：" + $who + "。队友用什么角色都可以。`r`n" +
           "· 普通难度：原版 Boss。`r`n`r`n" +
           "选的世界写进联机码，队友点「加入」时自动用同一个。"
    $r = Show-DrDialog $msg '暗黑重铸 · 联机难度' @('死亡以上难度', '普通难度', '取消') $(if ($high) { 0 } else { 1 }) 2 'question' $form
    if ($r -eq 0) { return 'high' }
    if ($r -eq 1) { return 'low' }
    return $null
}

# 敌人随机时选了死亡以上难度、这次用的随机结果却没有配套的世界（randomizer_hi，randomize.ps1 的 Get-RandHiWorld）：问玩家怎么办。
# 原来启动器只在日志里提示一行、游戏照常启动，Boss 不在原位、场地也没移植，玩家以为改版没加载（2026-11-08 测试者诊断包）。
# 补做要用随机化时记下的敌人预设种子（日志旁的 .preset，Invoke-RandomizeHiWorld）；太旧的随机结果没有，只能重新随机化。
# $Pack = 这次要从旧版本沿用过来的整合包（看它的）。返回启动前要先做的调用（'!-Action randhi' / '!-Action randenemy'）、'' = 已经有了不用做、$null = 取消启动。
# 只能生成或取消，不给「先这样启动」（用户 2026-11-08）
function Ask-MissingHiWorld([string]$Pack = '') {
    $lo = if ($Pack) { Join-Path $Pack 'randomizer' } else { $RandomDir }
    $hi = if ($Pack) { Join-Path $Pack 'randomizer_hi' } else { $RandomHiDir }
    if (Get-RandHiWorld @(Get-BossFixedIds) $hi $lo) { return '' }
    $info = Get-RandomInfo $lo
    $keep = [bool]($info -and $info.PresetSeed)
    $how = if ($keep) { "「现在生成」：约 1~5 分钟，完成后直接启动，普通难度的敌人不变。" }
           else { "这份敌人随机结果是旧版本做的，没法单独补做。「重新随机化」：约 2~10 分钟，完成后直接启动，两种难度的敌人都会换一批" +
                  $(if ($info -and $info.HasItem) { "，道具位置和商人货架也会重新打乱。" } else { "。" }) }
    $msg = "死亡以上难度要用单独生成的一份敌人世界，现在还没有（从旧版本更新、沿用了旧的敌人随机结果时常见）。`r`n`r`n" +
           "没有它，部分追忆 Boss 不在原来的位置，改版 Boss 的场地内容也不会生效，所以要先生成才能启动。`r`n`r`n" + $how + "`r`n`r`n" +
           "⚠ 随机器窗口会自动打开、自动操作、完成后自动关闭：这期间不要点随机器窗口，也不要关掉它。"
    $r = Show-DrDialog $msg '暗黑重铸 · 死亡以上难度' @($(if ($keep) { '现在生成' } else { '重新随机化' }), '取消') 0 1 'question' $form
    if ($r -ne 0) { return $null }
    if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { Show-Info '随机器已经开着，先把它关掉。'; return $null }
    return $(if ($keep) { '!-Action randhi' } else { '!-Action randenemy' })
}

# ---------------------------------------------------------------- 按钮
$bLaunchV.Add_Click({
    if (-not (Before-Launch)) { return }
    $bw = Ask-BossWorld
    if ($null -eq $bw) { return }
    Start-LauncherRun '启动 · 无敌人随机' @('-Action vanilla' + (Get-BossArg $bw))
})

# 还没有随机器输出（第一次玩敌人随机）：先自动重随一次敌人（-Action randenemy），成功了再接着启动
# 更新后沿用旧版本的敌人随机结果（randomize.ps1 末尾「更新后沿用」）：这个整合包还没有能用的随机结果、旧版本里有，就问要不要沿用。
# 选了「否」记在 launcher\reroll\state\carry_declined.txt，之后不再问（「一键启动（敌人随机）」照常重新随机化；想沿用：「常见问题」里的「沿用旧版本的敌人随机」）。
# 返回要沿用的那份（$null = 不沿用 / 没找到）
$CarryDeclined = Join-Path $LauncherDir 'reroll\state\carry_declined.txt'
# 敌人信息 mod 的开关（on / off；没有 = 没动过，照常加载）：「工具与设置」→「游戏」里改，启动器 Test-EnemyInfoMod 按它加载
$EnemyInfoChoice = Join-Path $LauncherDir 'reroll\state\enemy_info_mod.txt'
# 第一次打开启动器时的说明看过了（Show-EnemyInfoFirst）
$EnemyInfoNoted = Join-Path $LauncherDir 'reroll\state\enemy_info_noted.txt'

# 第一次打开启动器时说明一次敌人信息 mod（用户 2026-11-16：先是「单双在第一次打开启动器时都提示一下」，
# 后改「只是说明可能导致游戏无法启动并给出关闭的路径 不需要让玩家一开始就选是否加载」）：不问，默认加载；
# 动过开关（有 enemy_info_mod.txt）或看过说明（enemy_info_noted.txt）就不再显示
function Show-EnemyInfoFirst {
    if ((Test-Path -LiteralPath $EnemyInfoChoice) -or (Test-Path -LiteralPath $EnemyInfoNoted)) { return }
    $gpus = @(Get-GpuNames)
    $text = "整合包带有敌人信息 mod：在敌人头上显示血条和异常状态条，默认加载。`r`n`r`n" +
            "在少数电脑上（多见于有两块显卡的，比如核显 + 独显的笔记本），它可能导致游戏无法启动或读档时闪退。" +
            $(if ($gpus.Count -ge 2) { "这台电脑有两块显卡（" + ($gpus -join '、') + "），遇到的可能性大一些。" } else { '' }) +
            "N 卡开启插帧（帧生成）时，它也会导致游戏崩溃。`r`n`r`n" +
            "遇到的话，在启动器「工具与设置」→「游戏」里把「敌人信息 mod」关掉，下次启动游戏生效。关掉后游戏里没有敌人头上的血条和状态条，别的功能都不受影响。"
    [void](Show-DrDialog $text '暗黑重铸 · 敌人信息 mod' @('知道了') 0 0 'info' $form)
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $EnemyInfoNoted -Parent) | Out-Null
        [System.IO.File]::WriteAllText($EnemyInfoNoted, ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "`r`n"), $Utf8NoBom)
    } catch { }
}
# 敌人随机相关的按钮点之前：随机器没装（正式发布不带）就弹说明（去哪下载、解压到哪），不往下做
function Confirm-Randomizer {
    $rs = Get-RandomizerStatus
    if ($rs.Ok) { return $true }
    $r = Show-DrDialog $rs.Msg '暗黑重铸 · 要先装随机器' @('打开下载页', '打开 randomizer 文件夹', '关闭') 0 2 'info' $form
    if ($r -eq 0) { try { Start-Process $RandomizerUrl } catch { } }
    if ($r -eq 1) {
        New-Item -ItemType Directory -Force -Path $RandomDir | Out-Null
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $RandomDir + '"')
    }
    return $false
}

# 记下「不沿用」（之后不再问）
function Save-CarryDeclined([string]$What) {
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $CarryDeclined -Parent) | Out-Null
        [System.IO.File]::WriteAllText($CarryDeclined, ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' 不沿用 ' + $What + "`r`n"), $Utf8NoBom)
    } catch { }
}

# 让玩家自己选旧版本的文件夹（自动没找到时）：选整合包文件夹、它里面的随便哪一层、或者包着它的那一层都行。
# 能沿用返回候选（Pack / Version / Time / Seed）；取消或者选的不能用（弹原因）返回 $null
function Select-OldPack {
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = '选择旧版本的整合包文件夹（里面有 launcher、randomizer 的那一层；选包着它的那一层也行）'
    $dlg.SelectedPath = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($Paly).TrimEnd('\'))
    if ($dlg.ShowDialog($form) -ne 'OK') { return $null }
    $pack = Resolve-PackDir $dlg.SelectedPath
    if ($pack -ieq [System.IO.Path]::GetFullPath($Paly).TrimEnd('\')) {
        Show-Info ('选的是现在这个整合包自己（' + $pack + '）。要选的是旧版本解压出来的那个文件夹。')
        return $null
    }
    $c = Get-OldRandom $pack
    if ($c -is [string]) {
        Show-Info ('不能沿用这个文件夹里的敌人随机结果：' + "`r`n  " + $pack + "`r`n`r`n" + $c)
        return $null
    }
    return $c
}

# 自动找不到旧版本、又要重新随机化（$Launching：点了「一键启动（敌人随机）」）时：玩家已经有 Dark Reforged 存档，多半是更新过来接着玩的，
# 先问清楚（2026-11-04 用户反馈：直接点一键启动就换了新种子重新随机化，没问要不要沿用）。
# 返回候选（选了文件夹）、$null（不沿用，接着重新随机化）或 'cancel'（这次先不启动）
function Ask-PickOldRandom {
    $msg = "这个整合包里还没有敌人随机结果，自动也没找到旧版本的（记下的整合包、旁边的文件夹、桌面 / 下载 / 文档、游戏目录、各盘根目录往下两层都找过）。`r`n`r`n" +
           "你已经有暗黑重铸存档：如果是从旧版本更新过来接着玩，重新随机化后敌人会全部换掉。`r`n`r`n" +
           "旧版本的文件夹还在的话，点「选择旧版本文件夹」选它，复制过来后敌人和之前一模一样。`r`n" +
           "确定不要沿用（新开一局、或者就想换一批敌人），点「重新随机化」，之后不再问。"
    while ($true) {
        $r = Show-DrDialog $msg '沿用旧版本的敌人随机结果' @('选择旧版本文件夹', '重新随机化', '取消') 0 2 'question' $form
        if ($r -eq 1) { Save-CarryDeclined '（没找到旧版本，玩家选重新随机化）'; return $null }
        if ($r -ne 0) { return 'cancel' }
        $c = Select-OldPack
        if ($c) { return $c }
    }
}

function Ask-OldRandom([switch]$Launching) {
    if (-not (Get-RandomizerStatus).Ok) { return $null }       # 没装随机器，沿用了也玩不了敌人随机
    if (Test-Path -LiteralPath $CarryDeclined) { return $null }
    if (-not (Test-NeedOldRandom)) { return $null }
    $c = @(Find-OldRandoms) | Select-Object -First 1
    if (-not $c) {
        if ($Launching -and @(Get-RngSaveFiles).Count) { return (Ask-PickOldRandom) }
        return $null
    }
    $msg = "在旧版本的整合包里找到了敌人随机结果：`r`n" +
           "  文件夹：" + $c.Pack + "（v" + $c.Version + "）`r`n" +
           "  随机化于：" + $c.Time.ToString('yyyy-MM-dd HH:mm') + $(if ($c.Seed) { "，种子 " + $c.Seed } else { '' }) + "`r`n`r`n" +
           "要沿用吗？`r`n`r`n" +
           "是：复制过来（约 100 MB，几秒钟），敌人和之前一模一样，接着玩不受影响。`r`n`r`n" +
           "否：第一次用「一键启动（敌人随机）」时会重新随机化一次，敌人会全部换掉。之后不再问（想沿用可以在「常见问题」里点「沿用旧版本的敌人随机」）。"
    # 点标题栏的 × 关掉（-1）不算「否」：这次不沿用、也不记下来，下次打开再问
    $r = Show-DrDialog $msg '沿用旧版本的敌人随机结果' @('是', '否') 0 -1 'question' $form
    if ($r -eq 0) { return $c }
    if ($r -ne 1) { return $(if ($Launching) { 'cancel' } else { $null }) }   # 点 × 关掉：启动时当作这次先不启动
    Save-CarryDeclined $c.Pack
    return $null
}

# 启动器沿用这一份的调用参数（路径里的单引号要双写）
function Get-CarryCall($Cand) {
    return ('-Action carryrand -FromPack ''' + ($Cand.Pack -replace "'", "''") + '''')
}

function Confirm-FirstRandomize([bool]$Merged) {
    $o = Get-RandomizeOptions
    $why = if ($Merged) { "现在的敌人随机结果是旧版本合并别的包做的，带着那个包的参数，" } else { "这个文件夹里还没有敌人随机的结果（randomizer 文件夹里没有 regulation.bin 或随机器日志），" }
    $msg = $why + "这次会先自动随机化一次敌人（约 1~5 分钟），完成后直接启动游戏。`r`n`r`n" +
           "⚠ 随机器窗口会自动打开、自动操作、完成后自动关闭：这期间不要点随机器窗口，也不要关掉它。`r`n`r`n" +
           "随机器设置：" + $o.From + "`r`n" +
           $(if ($o.HasItem) { "`r`n这份设置开着物品随机：法术祷告、道具、材料、锻造石的位置和商人货架也会打乱（原版武器防具护符整合包照样换成未鉴定物品）。`r`n" } else { '' }) +
           "`r`n现在开始吗？"
    return (Confirm-Box $msg '第一次玩敌人随机')
}

$bLaunchR.Add_Click({
    if (-not (Confirm-Randomizer)) { return }
    $latest = Get-LatestRandom
    if (-not $latest -or $latest.Merged) {
        if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { Show-Info '随机器已经开着，先把它关掉。'; return }
        if (-not (Before-Launch)) { return }
        $c = Ask-OldRandom -Launching
        if ($c -is [string]) { return }
        $bw = Ask-BossWorld
        if ($null -eq $bw) { return }
        if ($c) {
            $step = if ($bw -eq 'high') { Ask-MissingHiWorld $c.Pack } else { '' }
            if ($null -eq $step) { return }
            if ($step -eq '!-Action randenemy') { Start-LauncherRun '重随敌人 + 启动 · 敌人随机' @($step, ('-Action rand' + (Get-BossArg $bw))); return }     # 重新随机化就不用先沿用了
            Start-LauncherRun '沿用旧版本的敌人随机结果 + 启动 · 敌人随机' (@('!' + (Get-CarryCall $c)) + @($step | Where-Object { $_ }) + @('-Action rand' + (Get-BossArg $bw)))
            return
        }
        if (-not (Confirm-FirstRandomize ([bool]$latest))) { return }
        Start-LauncherRun '重随敌人 + 启动 · 敌人随机' @('!-Action randenemy', ('-Action rand' + (Get-BossArg $bw)))
        return
    }
    if (-not $latest.HasEnemy -and -not $latest.HasItem) {
        if (-not (Confirm-Box '最近一次随机化没有勾选敌人随机，这样启动和“无敌人随机”差不多。仍然启动吗？' '提示')) { return }
    }
    if (-not (Before-Launch)) { return }
    $bw = Ask-BossWorld
    if ($null -eq $bw) { return }
    $step = if ($bw -eq 'high') { Ask-MissingHiWorld } else { '' }
    if ($null -eq $step) { return }
    if ($step) { Start-LauncherRun '生成死亡以上难度的世界 + 启动 · 敌人随机' @($step, ('-Action rand' + (Get-BossArg $bw))); return }
    Start-LauncherRun '启动 · 敌人随机' @('-Action rand' + (Get-BossArg $bw))
})

# 一键重随敌人：先说明会做什么、用哪份设置，确认后由启动器 -Action randenemy 操作随机器（randomize.ps1）
$bRandEnemy.Add_Click({
    if (-not (Confirm-Randomizer)) { return }
    if (-not (Confirm-GameClosed '重随敌人要在游戏关闭后做。')) { return }
    if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { Show-Info '随机器已经开着，先把它关掉再点一键重随敌人。'; return }
    if (-not (Get-GameRoot)) {
        if (-not (Select-GameRoot '随机器要读游戏文件，先选一下游戏路径。')) { return }
    }
    $o = Get-RandomizeOptions
    $warn = ''
    if ($o.HasItem) { $warn += "`r`n这份设置开着物品随机：法术祷告、道具、材料、锻造石的位置和商人货架也会打乱（原版武器防具护符整合包照样换成未鉴定物品）。`r`n" }
    $msg = "⚠ 随机器窗口会自动打开、自动点「随机化敌人」、完成后自动关闭。`r`n" +
           "    这期间不要点随机器窗口里的任何东西，也不要关掉它（大约 1~5 分钟）。`r`n`r`n" +
           "换一个新种子重新随机化敌人，不启动游戏。`r`n" +
           "随机器设置：" + $o.From + "`r`n" + $warn + "`r`n" +
           "· 想改随机器设置（难度、DLC、Boss 是否混合等）：点「打开随机器，自己配置」改好；以后一键重随都按你上一次的设置。`r`n" +
           "· 完成后点「一键启动（敌人随机）」玩。旧的随机结果会被覆盖。`r`n`r`n" +
           "现在开始吗？"
    if (-not (Confirm-Box $msg '一键重随敌人')) { return }
    Start-LauncherRun '一键重随敌人' @('-Action randenemy')
})

$bRandomizer.Add_Click({
    if (-not (Confirm-Randomizer)) { return }
    if (-not (Test-DotNet8)) {
        Show-Info (Get-DotNet8Msg)
        try { Start-Process $DotNet8Url } catch { }
        return
    }
    if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { Show-Info '随机器已经开着。'; return }
    $msg = "在随机器窗口里这样做：`r`n" +
           "1. 第一次使用：点右下的「选择游戏exe启动文件」，选游戏的 eldenring.exe。`r`n" +
           "2. 「合并其它MOD」留空（整合包直接用原版，不合并别的包；以前填过的已经自动清掉）。`r`n" +
           "3. 顶部的「敌人随机」：勾选，点进去按喜好调整；「DLC设置」「杂项设置」也可以按喜好改。`r`n" +
           "    「自定义敌人」启动器已经勾好，不要取消（追忆 Boss 只在追忆之间换、按地区控制精英比例都靠它）。`r`n" +
           "4. 顶部的「物品随机」：可开可不开。开了会打乱法术祷告、道具、材料、锻造石的位置和商人货架；`r`n" +
           "    原版武器、防具、护符整合包照样换成未鉴定物品，Boss 奖励、未鉴定掉落、暗黑商店不受影响。`r`n" +
           "    关键道具（钥匙、大卢恩等）要不要打乱，看「物品随机」里关键道具那一项。`r`n" +
           "5. 点右下的「随机化敌人」（开了物品随机时按钮写的是「随机化物品与敌人」），`r`n" +
           "    想要新的随机结果，点之前先勾上「重roll种子」（不勾会沿用上次的种子，敌人和上次一模一样）；`r`n" +
           "    等提示完成后关掉随机器。不要点随机器里的「启动游戏」。`r`n" +
           "6. 回到这里，点「一键启动（敌人随机）」。`r`n`r`n" +
           "点「确定」打开随机器。"
    if (-not (Confirm-Box $msg '打开随机器')) { return }
    $root = Get-GameRoot
    $note = Reset-RandMod $(if ($root) { Join-Path $root 'Game\eldenring.exe' } else { '' })
    Start-Process -FilePath $RandomExe -WorkingDirectory $RandomDir
    Add-Log '已打开随机器。'
    if ($note) { Add-Log $note }
})

$smallBtns['游戏路径'].Add_Click({ [void](Select-GameRoot) })

$smallBtns['恢复存档'].Add_Click({ Show-RestoreSaves })

$smallBtns['备份存档'].Add_Click({
    $saves = @(Get-RngSaveFiles)
    if ($saves.Count -eq 0) { Show-Info ('没有找到暗黑重铸存档（' + $RngSaveRoot + '\<SteamID>\ER0000.rng，联机的是 ER0000.rngcoop）。'); return }
    $records = @(Get-RngRecordFiles)
    $dst = Join-Path (Join-Path $Paly '存档备份') (Get-Date -Format 'yyyyMMdd_HHmmss')
    foreach ($s in $saves) {
        $d = Join-Path $dst $s.Directory.Name
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Copy-Item -LiteralPath $s.FullName -Destination $d -Force
    }
    if ($records.Count) {
        $rd = Join-Path $dst '角色记录'
        New-Item -ItemType Directory -Force -Path $rd | Out-Null
        foreach ($f in $records) { Copy-RngRecord $f $rd }   # 联机的放 角色记录\联机\
    }
    Add-Log ('存档已备份到：' + $dst + '（' + $saves.Count + ' 个存档 + ' + $records.Count + ' 个角色记录）')
    Add-RngOpsLog ('手动备份（「备份存档」按钮）：存档 ' + $saves.Count + ' 个、角色记录 ' + $records.Count + ' 个 → ' + $dst)
    Show-Info ("已备份到：`r`n" + $dst + "`r`n`r`n要换回来时点「恢复存档」→「手动选择…」，选这份。")
    Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $dst + '"')
})

$smallBtns['重随设置'].Add_Click({ Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $Settings + '"') })

$smallBtns['报告 / 日志'].Add_Click({
    $rep = Join-Path (Get-RerollPack) 'reroll_report.txt'
    if (Test-Path -LiteralPath $rep) { Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $rep + '"') }
    Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + (Join-Path $YafDir 'log') + '"')
    $ld = Join-Path $LauncherDir 'logs'
    if (Test-Path -LiteralPath $ld) { Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $ld + '"') }
})

$smallBtns['导出诊断包'].Add_Click({ Start-LauncherRun '导出诊断包' @('-Action diag') })

# ---------------------------------------------------------------- 敌人设置（用户 2026-11-10：启动器里调精英怪比例、开头目出现在普通敌人位置）
# 只改 settings.json 里的 elite_share_mult / boss_in_basic_pct 两个数（文件其余部分原样不动）；一键重随敌人时 reroll\enemypreset.py 按它们写随机器的自定义敌人预设：
#   精英：elite_share_by_band 各档 × 倍数（每档最多 60%）；头目：预设里普通敌人类加一个「全部 Boss」来源组，占这么多 %
$EliteLevels = @(@('最少', 0.0, '不额外放'), @('少', 0.5, '× 0.5'), @('默认', 1.0, '× 1'), @('较多', 1.5, '× 1.5'), @('多', 2.0, '× 2'), @('很多', 3.0, '× 3'))
$BossLevels  = @(@('关闭', 0.0, '不出现'), @('很少', 1.0, '约 1%'), @('少量', 3.0, '约 3%'), @('较多', 6.0, '约 6%'), @('很多', 10.0, '约 10%'))
$EliteBandNames = @('前期', '利耶尼亚 / 盖利德', '王城 / 山顶', '雪原 / 圣树', 'DLC 前中期', 'DLC 后期')
$Inv = [Globalization.CultureInfo]::InvariantCulture

function Get-SettingNum([string]$Text, [string]$Name, [double]$Default) {
    $m = [regex]::Match($Text, '(?m)^\s*"' + [regex]::Escape($Name) + '"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)')
    if (-not $m.Success) { return $Default }
    return [double]::Parse($m.Groups[1].Value, $Inv)
}

# 改一个数：有这个键就只换数字；没有就在 $Before 那个键的前一行加上（后面还有别的键，逗号不会错）
function Set-SettingNum([string]$Text, [string]$Name, [double]$Value, [string]$Before) {
    $v = $Value.ToString('0.###', $Inv)
    $m = [regex]::Match($Text, '(?m)^\s*"' + [regex]::Escape($Name) + '"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)')
    if ($m.Success) {
        $g = $m.Groups[1]
        return $Text.Substring(0, $g.Index) + $v + $Text.Substring($g.Index + $g.Length)
    }
    $nl = $(if ($Text.Contains("`r`n")) { "`r`n" } else { "`n" })
    $b = [regex]::Match($Text, '(?m)^[ \t]*"' + [regex]::Escape($Before) + '"\s*:')
    $at = $(if ($b.Success) { $b.Index } else { $Text.IndexOf('{') + 1 + $nl.Length })
    return $Text.Substring(0, $at) + '  "' + $Name + '": ' + $v + ',' + $nl + $Text.Substring($at)
}

function Get-NearestLevel($Levels, [double]$Value) {
    $best = 0
    for ($i = 1; $i -lt $Levels.Count; $i++) { if ([Math]::Abs($Levels[$i][1] - $Value) -lt [Math]::Abs($Levels[$best][1] - $Value)) { $best = $i } }
    return $best
}

function Get-EliteDesc([double]$Mult, [double[]]$Base) {
    if ($Mult -le 0) { return '不额外放精英：前期没有精英怪，其他地区只有随机器自己随机到的少量精英怪。' }
    $parts = for ($i = 0; $i -lt $Base.Count; $i++) {
        $nm = $(if ($i -lt $EliteBandNames.Count) { $EliteBandNames[$i] } else { '第 ' + ($i + 1) + ' 档' })
        $nm + ' ' + ([Math]::Min(60.0, $Base[$i] * $Mult)).ToString('0.#', $Inv) + '%'
    }
    return '普通敌人里精英怪的比例：' + ($parts -join '，') + '。'
}

function Get-BossDesc([double]$Pct) {
    if ($Pct -le 0) { return '关闭：普通敌人的位置只会出现普通敌人和精英怪。' }
    return ('约 ' + $Pct.ToString('0.#', $Inv) + '% 的普通敌人会换成随机头目（大约每 ' + [Math]::Round(100 / $Pct) + ' 个里 1 个）。追忆头目不会出现在这些位置。')
}

# 敌人设置的窗口：$st 里是现在的档位（E / B，没点过时 ED / BD 为假、保存原来的数 EV / BV），点了「保存并重随敌人」/「只保存」把 Go 设成 rand / save。
# 新界面开着时 webui.ps1 换成页面里的弹层
function Show-EnemyDialog($st, $base) {
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = '暗黑重铸 · 敌人设置'
    $dlg.Font = $font
    $dlg.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Dpi
    $dlg.ClientSize = New-Object System.Drawing.Size(660, 470)
    $dlg.StartPosition = 'CenterParent'
    $dlg.FormBorderStyle = 'FixedDialog'
    $dlg.MaximizeBox = $false
    $dlg.MinimizeBox = $false
    $dlg.ShowInTaskbar = $false
    Set-DarkForm $dlg
    $fontH = New-Object System.Drawing.Font('Microsoft YaHei UI', 11.5, [System.Drawing.FontStyle]::Bold)
    $mk = {
        param([string]$Text, [int]$X, [int]$Y, [int]$W, [int]$H, $Color, $Font)
        $l = New-Object System.Windows.Forms.Label
        $l.Text = $Text
        $l.AutoSize = $false
        $l.UseMnemonic = $false
        $l.Location = New-Object System.Drawing.Point($X, $Y)
        $l.Size = New-Object System.Drawing.Size($W, $H)
        $l.ForeColor = $Color
        $l.BackColor = $Thm::Bg
        $l.Font = $Font
        $dlg.Controls.Add($l)
        $l
    }
    [void](& $mk '精英怪比例' 22 18 616 26 $Thm::Gold $fontH)
    [void](& $mk '敌人随机时，普通敌人里有多少换成精英怪（越往后的地区越多）。' 22 46 616 22 $Thm::FgDim $fontS)
    $segE = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $EliteLevels.Count; $i++) {
        $b = New-DlgBtn $EliteLevels[$i][0] (22 + $i * 104) 74 98 46
        $b.Sub = $EliteLevels[$i][2]
        $b.Font = $font
        $b.Tag = $i
        $b.Add_Click({ $st.E = [int]$this.Tag; $st.ED = $true; & $refresh })
        $dlg.Controls.Add($b)
        [void]$segE.Add($b)
    }
    $infoE = & $mk '' 22 128 616 42 $Thm::Fg $fontS
    $line = New-Object System.Windows.Forms.Panel
    $line.BackColor = $Thm::Border
    $line.Location = New-Object System.Drawing.Point(22, 180)
    $line.Size = New-Object System.Drawing.Size(616, 1)
    $dlg.Controls.Add($line)
    [void](& $mk '头目出现在普通敌人位置' 22 194 616 26 $Thm::Gold $fontH)
    [void](& $mk '开启后，敌人随机时有一部分普通敌人会换成随机头目，路上可能突然遇到头目。' 22 222 616 22 $Thm::FgDim $fontS)
    $segB = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $BossLevels.Count; $i++) {
        $b = New-DlgBtn $BossLevels[$i][0] (22 + $i * 125) 250 118 46
        $b.Sub = $BossLevels[$i][2]
        $b.Font = $font
        $b.Tag = $i
        $b.Add_Click({ $st.B = [int]$this.Tag; $st.BD = $true; & $refresh })
        $dlg.Controls.Add($b)
        [void]$segB.Add($b)
    }
    $infoB = & $mk '' 22 304 616 42 $Thm::Fg $fontS
    [void](& $mk ('这两项只影响敌人随机：保存后要点「一键重随敌人」才会生效，已经随机好的敌人不会变。' +
                  '没开敌人随机（一键启动 · 无敌人随机）时不起作用。') 22 352 616 42 $Thm::FgMuted $fontS)
    $refresh = {
        for ($k = 0; $k -lt $segE.Count; $k++) {
            $segE[$k].Look = $(if ($k -eq $st.E) { [DarkReforgedUI.Kind]::Primary } else { [DarkReforgedUI.Kind]::Secondary })
            $segE[$k].Invalidate()
        }
        for ($k = 0; $k -lt $segB.Count; $k++) {
            $segB[$k].Look = $(if ($k -eq $st.B) { [DarkReforgedUI.Kind]::Primary } else { [DarkReforgedUI.Kind]::Secondary })
            $segB[$k].Invalidate()
        }
        $infoE.Text = Get-EliteDesc $(if ($st.ED) { $EliteLevels[$st.E][1] } else { $st.EV }) $base
        $infoB.Text = Get-BossDesc $(if ($st.BD) { $BossLevels[$st.B][1] } else { $st.BV })
    }
    & $refresh
    $foot = New-Object System.Windows.Forms.Panel
    $foot.BackColor = $Thm::Surface
    $foot.Location = New-Object System.Drawing.Point(0, 406)
    $foot.Size = New-Object System.Drawing.Size(660, 64)
    $fl = New-Object System.Windows.Forms.Panel
    $fl.BackColor = $Thm::Border
    $fl.Location = New-Object System.Drawing.Point(0, 0)
    $fl.Size = New-Object System.Drawing.Size(660, 1)
    $foot.Controls.Add($fl)
    $bGo = New-DlgBtn '保存并重随敌人' 238 14 168 36 $true
    $bSave = New-DlgBtn '只保存' 414 14 108 36
    $bCancel = New-DlgBtn '取消' 530 14 108 36
    foreach ($b in @($bGo, $bSave, $bCancel)) { $b.Font = $font; $foot.Controls.Add($b) }
    $bGo.Add_Click({ $st.Go = 'rand'; $dlg.Close() })
    $bSave.Add_Click({ $st.Go = 'save'; $dlg.Close() })
    $bCancel.Add_Click({ $dlg.Close() })
    $dlg.CancelButton = $bCancel
    $dlg.Controls.Add($foot)
    $dlg.Add_Shown({ $this.ActiveControl = $bGo })
    [void]$dlg.ShowDialog($form)
    $dlg.Dispose()
    return $st
}

function Show-EnemySettings {
    try { $txt = [System.IO.File]::ReadAllText($Settings) } catch { Show-Info ('读不了重随设置：' + $Settings); return }
    $base = [double[]]@(2.5, 5, 7.5, 10, 12.5, 15)
    $bm = [regex]::Match($txt, '"elite_share_by_band"\s*:\s*\[([^\]]*)\]')
    if ($bm.Success) { try { $base = [double[]]@($bm.Groups[1].Value -split ',' | ForEach-Object { [double]::Parse($_.Trim(), $Inv) }) } catch { } }
    $em = Get-SettingNum $txt 'elite_share_mult' 1.0
    $bp = Get-SettingNum $txt 'boss_in_basic_pct' 0.0
    # 设置里不是档位上的数（手改过 settings.json）：先高亮最近的一档，没点就照原数保存
    $st = @{ E = (Get-NearestLevel $EliteLevels $em); B = (Get-NearestLevel $BossLevels $bp); EV = $em; BV = $bp; ED = $false; BD = $false; Go = '' }

    $st = Show-EnemyDialog $st $base
    if (-not $st.Go) { return }

    $ev = $(if ($st.ED) { $EliteLevels[$st.E][1] } else { $st.EV })
    $bv = $(if ($st.BD) { $BossLevels[$st.B][1] } else { $st.BV })
    try {
        $new = Set-SettingNum $txt 'elite_share_mult' $ev 'elite_share_by_band'
        $new = Set-SettingNum $new 'boss_in_basic_pct' $bv 'elite_share_by_band'
        [void]($new | ConvertFrom-Json)                  # 改完还得是合法的 JSON，不是就不写
        if ($new -ne $txt) { [System.IO.File]::WriteAllText($Settings, $new, (New-Object System.Text.UTF8Encoding($false))) }
    } catch {
        Show-DrDialog ('保存失败：' + $_.Exception.Message + "`r`n`r`n设置文件：" + $Settings) '暗黑重铸 · 敌人设置' @('确定') 0 0 'error' $form | Out-Null
        return
    }
    $sum = '精英怪比例：' + $EliteLevels[(Get-NearestLevel $EliteLevels $ev)][0] + '；头目出现在普通敌人位置：' + $BossLevels[(Get-NearestLevel $BossLevels $bv)][0]
    Add-Log ('敌人设置已保存（' + $sum + '）')
    if ($st.Go -eq 'rand') { Invoke-ClassicClick $bRandEnemy; return }
    Show-Info ('已保存（' + $sum + '）。' + "`r`n`r`n" + '下次点「一键重随敌人」时生效。')
}

# ---------------------------------------------------------------- 联机（Seamless Co-op；启动器 launcher.ps1 的「联机」一节，dev\coop\联机计划.md）
# Seamless Co-op 的 ersc.dll：整合包 dll\ 和下一层文件夹（_ 开头的不算），再看游戏目录 Game\SeamlessCoop\（和启动器的 Find-Ersc 一样）；没有返回 $null
function Find-ErscPath {
    $ud = Join-Path $Paly 'dll'
    $c = @(Get-ChildItem -LiteralPath $ud -Filter 'ersc.dll' -File -ErrorAction SilentlyContinue)
    foreach ($d in (Get-ChildItem -LiteralPath $ud -Directory -ErrorAction SilentlyContinue | Sort-Object Name)) {
        if ($d.Name.StartsWith('_')) { continue }
        $c += @(Get-ChildItem -LiteralPath $d.FullName -Filter 'ersc.dll' -File -ErrorAction SilentlyContinue)
    }
    $root = Get-GameRoot
    if ($root) {
        $g = Join-Path $root 'Game\SeamlessCoop\ersc.dll'
        if (Test-Path -LiteralPath $g) { $c += Get-Item -LiteralPath $g }
    }
    $f = $c | Select-Object -First 1
    if ($f) { return $f.FullName }
    return $null
}

# Seamless Co-op 要求联机密码（ersc.dll 旁边 ersc_settings.ini 的 cooppassword）：空的会弹 Fatal Error 并让游戏退出（2.0.1）。
# 空的就提示，能直接打开设置文件改；返回能不能启动
function Confirm-ErscPassword([string]$Ersc) {
    $ini = Join-Path (Split-Path $Ersc -Parent) 'ersc_settings.ini'
    $txt = try { [System.IO.File]::ReadAllText($ini) } catch { '' }
    $m = [regex]::Match($txt, '(?im)^[ \t]*cooppassword[ \t]*=[ \t]*([^\r\n;]*)')
    if ($m.Success -and $m.Groups[1].Value.Trim()) { return $true }
    $r = Show-DrDialog ("Seamless Co-op 要求填联机密码，空着它会报错并让游戏退出。`r`n`r`n" +
        "在设置文件里找到 cooppassword = 这一行，在等号后面填一个密码（两个人填一样的），保存后再点联机启动。`r`n`r`n" + $ini) `
        '暗黑重铸 · 联机密码' @('打开设置文件', '取消') 0 1 'warn' $form
    if ($r -eq 0) { Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $ini + '"') }
    return $false
}

function Show-CoopMenu {
    $ersc = Find-ErscPath
    $need = "没找到 Seamless Co-op。它要自己下载：把压缩包里的 SeamlessCoop 文件夹整个放进整合包的 dll\ 文件夹（变成 dll\SeamlessCoop\ersc.dll）。"
    $msg = "联机用 Seamless Co-op 模组（整合包不带，要自己下载：把压缩包里的 SeamlessCoop 文件夹整个放进整合包的 dll\；压缩包里的 ersc_launcher.exe 不用，联机也从这里启动）。`r`n" +
           $(if ($ersc) { "已找到：" + $ersc } else { "⚠ 还没找到 Seamless Co-op。" }) + "`r`n`r`n" +
           "怎么联机（两人用同一个版本的整合包）：`r`n" +
           "1. 房主点「开房 · 敌人随机」或「开房 · 无敌人随机」：联机码自动复制到剪贴板，游戏同时启动。把联机码发给队友（码里有联机密码，只发给队友）。`r`n" +
           "2. 队友复制这一行，点「加入」：联机密码、Seamless Co-op 设置、敌人设置和世界照房主的改好；敌人随机和房主不一样时先重随（约 1~5 分钟），然后启动。`r`n" +
           "3. 进游戏后房主用 Seamless Co-op 的开房道具，队友用加入的道具。两边的游戏数据对不对得上，进同一个会话后自动核对。`r`n" +
           "下次还是同一队人：房主照样点「开房」，队友点「加入」（剪贴板里没有码时用上次的）。`r`n`r`n" +
           "联机时：以房主的世界为准；斗技场试炼由房主在雕像开始、队友一起进，头目复活只有房主能用；倒下了会观战队友，直到所有人都倒下或者有人在赐福休息；Seamless Co-op 的入侵会自动关掉；直接改敌人的词条效果由房主那边改。`r`n" +
           "联机存档是 ER0000.rngcoop（以前叫 ER0000.rng.co2，联机启动时会自动换过来），和单机存档分开；联机角色的新装备、锁定等记录也单独存，互不影响。`r`n" +
           "联机还在测试：队友身上的新装备在你这边样子和名字不对；新装备可以在背包里点它「送给」队友。出问题时点「导出诊断包」发过来。"
    $r = Show-DrDialog $msg '暗黑重铸 · 联机（Seamless Co-op）' @('开房 · 敌人随机', '开房 · 无敌人随机', '加入', '复制联机码', '关闭') 0 4 'question' $form
    switch ($r) {
        0 {
            if (-not $ersc) { Show-Info $need; return }
            if (-not (Confirm-Randomizer)) { return }
            $latest = Get-LatestRandom
            if (-not $latest -or $latest.Merged) { Show-Info '还没有能用的敌人随机结果：先「一键重随敌人」，或者点「开房 · 无敌人随机」。'; return }
            if (-not (Before-Launch)) { return }
            $bw = Ask-CoopWorld
            if ($null -eq $bw) { return }
            Start-LauncherRun '联机开房 · 敌人随机' @('-Action coophost' + (Get-BossArg $bw))
        }
        1 {
            if (-not $ersc) { Show-Info $need; return }
            if (-not (Before-Launch)) { return }
            $bw = Ask-CoopWorld
            if ($null -eq $bw) { return }
            Start-LauncherRun '联机开房 · 无敌人随机' @('-Action coophostvanilla' + (Get-BossArg $bw))
        }
        2 {
            if (-not $ersc) { Show-Info $need; return }
            # 联机码：剪贴板 → 联机时联机通道存下的房主的码、上次加入用的码（新的先；launcher.ps1 的 Invoke-CoopJoin 同样的顺序）
            $code = try { [string][System.Windows.Forms.Clipboard]::GetText() } catch { '' }
            $code = ($code -replace '\s+', ' ').Trim()
            if ($code -notmatch '^DR(?:[123]\||4)') {
                $code = ''
                $files = @((Join-Path $Paly 'dll\dark_core\coop_host_code.txt'), (Join-Path $LauncherDir 'reroll\state\coop_join_code.txt') |
                           Where-Object { Test-Path -LiteralPath $_ } | Sort-Object { (Get-Item -LiteralPath $_).LastWriteTime } -Descending)
                foreach ($f in $files) {
                    $t = (([System.IO.File]::ReadAllText($f)) -replace '\s+', ' ').Trim()
                    if ($t -match '^DR(?:[123]\||4)') { $code = $t; break }
                }
            }
            if (-not $code) { Show-Info '剪贴板里没有联机码。先复制房主发来的那一串（DR4 开头），再点「加入」。'; return }
            # 压缩过的（DR4z，coopcode.ps1）先解开，看是敌人随机还是无敌人随机
            $plain = Expand-CoopCode $code
            if (-not $plain) { Show-Info '这个联机码解不开（多半没复制完整）。让房主重新点「复制联机码」发一次。'; return }
            $rand = $plain -notmatch '^DR3\|' -or $plain -match '\|m=rand(\||$)'
            if ($rand) {
                if (-not (Confirm-Randomizer)) { return }
                if (Get-Process -Name 'EldenRingRandomizer' -ErrorAction SilentlyContinue) { Show-Info '随机器已经开着，先把它关掉。'; return }
            }
            if (-not (Before-Launch)) { return }
            if ($rand) {
                $msg2 = "加入房主的联机：联机密码、Seamless Co-op 设置、敌人设置和世界照房主的改好再启动。`r`n`r`n" +
                        "敌人随机和房主不一样时会先重随敌人：随机器窗口会自动打开、自动操作、完成后自动关闭，这期间不要点它，也不要关掉它（约 1~5 分钟）。`r`n`r`n现在开始吗？"
                if (-not (Confirm-Box $msg2 '加入联机')) { return }
            }
            Start-LauncherRun '加入队友的联机' @("-Action coopjoin -Code '" + ($code -replace "'", "''") + "'")
        }
        3 {
            if (-not $ersc) { Show-Info $need; return }
            Start-LauncherRun '复制联机码' @('-Action coopcode')
        }
    }
}

if ($smallBtns.ContainsKey('联机')) { $smallBtns['联机'].Add_Click({ Show-CoopMenu }) }     # 联机按钮现在不显示（见上面 $small）
$smallBtns['敌人设置'].Add_Click({ Show-EnemySettings })

$smallBtns['一键重随物品'].Add_Click({
    $msg = "骨灰的位置、职业的开局装备、开局遗物只在第一次启动时抽一次，之后一直固定。`r`n`r`n" +
           "确定后，下次启动时会重新抽一次，之后再固定下来。`r`n" +
           "（同一台电脑的所有角色共用这一套。开局装备、遗物和骨灰只对之后新建的角色生效：已有角色身上的装备和还没捡到的骨灰都按这个角色自己的记录，不会变。）"
    if (Confirm-Box $msg '一键重随物品') { Start-LauncherRun '一键重随物品' @('-Action oncereset') }
})

function Get-FaqText {
    return (
"问：我想重新随机敌人怎么办？`r`n" +
"1. 点「一键重随敌人」，等它跑完（2~5 分钟，期间不要碰随机器窗口）。`r`n" +
"2. 点「一键启动（敌人随机）」开始玩。`r`n" +
"`r`n" +
"问：更新到新版本后，敌人会全部换掉吗？`r`n" +
"不会，只要旧版本的文件夹还在：第一次打开新版本时会问你要不要沿用旧版本的敌人随机结果，选「是」敌人就和之前一样。`r`n" +
"当时选了「否」又想沿用：点下面的「沿用旧版本的敌人随机」（要在重新随机化之前；已经重新随机化过就没有这个按钮）。`r`n" +
"没自动找到旧版本（比如解压到了别的地方）：点「一键启动（敌人随机）」时会让你自己选旧版本的文件夹；也可以点下面的「沿用旧版本的敌人随机」去选。`r`n" +
"`r`n" +
"问：游戏里怎么没有敌人血条？`r`n" +
"敌人头上的血条、状态条来自整合包里的敌人信息 mod，默认加载。在「工具与设置」→「游戏」里关掉过的话，打开就有了。`r`n" +
"它在少数电脑上（多见于有两块显卡的，笔记本常见：核显 + 独显）可能导致游戏无法启动或读档时闪退：遇到的话在同一个地方把它关掉。`r`n" +
"`r`n" +
"问：怎么更新到新版本？`r`n" +
"能联网的话点「检查更新」：有新版本会显示改了什么，点「现在更新」自动下载更新包并更新。`r`n" +
"自己下载的更新包：`r`n" +
"1. 下载更新包（Darkforge_v旧版本_to_v新版本_update.zip，比完整的整合包小得多），不用解压。`r`n" +
"2. 退出游戏，点「导入更新包」选它；跨了几个版本就把几个更新包一起选上，会按顺序导入。`r`n" +
"3. 更新包要从你现在的版本开始（启动器右上角写着版本号）。接不上时请下载完整的整合包。`r`n" +
"只替换改了的文件，敌人随机结果、存档和角色记录都不受影响；你改过的重随设置会保留。改动前的文件备份在整合包文件夹里的「更新备份」。`r`n" +
"`r`n" +
"问：回退版本怎么办？`r`n" +
"1. 把旧版本的压缩包解压到另一个文件夹。`r`n" +
"2. 打开旧版本的启动器，点「恢复存档」→「手动选择…」，选一份更新之前的「启动前」备份，点恢复。`r`n" +
"3. 用旧版本启动。`r`n" +
"`r`n" +
"问：精英怪太多 / 太少，或者想在普通敌人的位置遇到头目？`r`n" +
"点「敌人设置」：精英怪比例有六档；「头目出现在普通敌人位置」可以选关闭或四档多少（追忆头目不会出现在这些位置）。`r`n" +
"改完点「一键重随敌人」才会生效，已经随机好的敌人不会变。`r`n" +
"`r`n" +
"问：自动备份的存档在哪？`r`n" +
"点下面的「打开自动备份文件夹」。每次启动游戏前都会自动存一份，文件夹名字就是时间。`r`n" +
"自己点「备份存档」存的，在整合包文件夹里的「存档备份」。`r`n" +
"`r`n" +
"手动恢复：`r`n" +
"1. 关掉游戏。`r`n" +
"2. 打开一份备份，把里面的 ER0000.rng 复制到「打开存档文件夹」里那个数字文件夹中，覆盖。`r`n" +
"3. 把备份里「角色记录」文件夹中的文件复制到「打开存档文件夹」里的 DarkReforged\角色记录，覆盖。`r`n" +
"   联机存档 ER0000.rngcoop 同样放进数字文件夹；备份的「角色记录」里的「联机」文件夹整个复制过去。`r`n" +
"   （2026-10-29 以前的备份里是 DarkReforged_*.txt、DarkReforged_once.json：去掉文件名开头的 DarkReforged_ 再放进去。）")
}

function Show-Faq {
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = '常见问题'
    $dlg.Font = $font
    $dlg.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Dpi
    $dlg.ClientSize = New-Object System.Drawing.Size(880, 566)
    $dlg.MinimumSize = New-Object System.Drawing.Size(560, 400)
    $dlg.StartPosition = 'CenterParent'
    $dlg.MinimizeBox = $false
    Set-DarkForm $dlg
    $card, $tb = New-TextCard 12 12 856 490 (Get-FaqText) 'Top,Bottom,Left,Right'
    $dlg.Controls.Add($card)
    $bBk = New-DlgBtn '打开自动备份文件夹' 12 516 190 38
    $bBk.Anchor = 'Bottom,Left'
    $bBk.Add_Click({
        $d = if (Test-Path -LiteralPath $RngBackupDir) { $RngBackupDir } else { $RngSaveRoot }
        if (-not (Test-Path -LiteralPath $d)) { Show-Info ('还没有备份（' + $RngBackupDir + '）：启动过一次游戏后才会有。'); return }
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $d + '"')
    })
    $dlg.Controls.Add($bBk)
    $bSave = New-DlgBtn '打开存档文件夹' 210 516 160 38
    $bSave.Anchor = 'Bottom,Left'
    $bSave.Add_Click({
        if (-not (Test-Path -LiteralPath $RngSaveRoot)) { Show-Info ('没有找到存档文件夹：' + $RngSaveRoot); return }
        Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $RngSaveRoot + '"')
    })
    $dlg.Controls.Add($bSave)
    $bx = 378
    # 更新后沿用旧版本的敌人随机结果（以前在命令行菜单 [6]）：这个整合包还没有能用的随机结果时显示；
    # 自动找到了旧版本就沿用它，没找到让玩家自己选文件夹（Select-OldPack）
    $need = (Get-RandomizerStatus).Ok -and (Test-NeedOldRandom)
    $carry = if ($need) { @(Find-OldRandoms) | Select-Object -First 1 } else { $null }
    if ($need) {
        $bCa = New-DlgBtn '沿用旧版本的敌人随机' $bx 516 180 38
        $bCa.Anchor = 'Bottom,Left'
        $bCa.Add_Click({
            if (-not $carry) {
                $carry = Select-OldPack
                if (-not $carry) { return }
            }
            $msg = "把旧版本整合包里的敌人随机结果复制过来（约 100 MB，几秒钟），敌人和之前一模一样：`r`n" +
                   "  文件夹：" + $carry.Pack + "（v" + $carry.Version + "）`r`n" +
                   "  随机化于：" + $carry.Time.ToString('yyyy-MM-dd HH:mm') + $(if ($carry.Seed) { "，种子 " + $carry.Seed } else { '' }) + "`r`n`r`n现在复制吗？"
            if (-not (Confirm-Box $msg '沿用旧版本的敌人随机结果')) { return }
            $dlg.Close()
            Start-LauncherRun '沿用旧版本的敌人随机结果' @(Get-CarryCall $carry)
        })
        $dlg.Controls.Add($bCa)
    }
    $ok = New-DlgBtn '关闭' 748 516 120 38 $true
    $ok.Anchor = 'Bottom,Right'
    $ok.DialogResult = 'OK'
    $dlg.Controls.Add($ok)
    $dlg.AcceptButton = $ok
    $dlg.CancelButton = $ok
    $dlg.Add_Shown({ $tb.SelectionLength = 0; $ok.Focus() })
    [void]$dlg.ShowDialog($form)
}

$smallBtns['常见问题'].Add_Click({ Show-Faq })

# 导入离线更新包 / 在线更新（launcher.ps1 -Action update / autoupdate → update.py）：成功就提示并重开启动器（启动器自己的文件也可能换了）
# 运行结束后才执行（$script:AfterRun）：只能用脚本级变量（点击时的局部变量那时已经没了）
$UpdateResultFile = Join-Path $LauncherDir 'logs\update_result.txt'
$UpdateCheckFile = Join-Path $LauncherDir 'logs\update_check.json'

# 重新打开启动器：包里的 pythonw 跑 spawn.py，不开窗口地启动 gui.ps1（用户 2026-11-14：命令行里带 -WindowStyle Hidden 的 powershell
# 会被安全软件当可疑脚本拦）；没有 Python 时照旧
function Start-GuiAgain {
    $pyw = Join-Path $LauncherDir 'python\pythonw.exe'
    $spawn = Join-Path $LauncherDir 'spawn.py'
    if ((Test-Path -LiteralPath $pyw) -and (Test-Path -LiteralPath $spawn)) {
        Start-Process -FilePath $pyw -ArgumentList @('-I', ('"' + $spawn + '"'), 'gui.ps1') -WorkingDirectory (Split-Path -Parent $LauncherDir)
        return
    }
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-WindowStyle', 'Hidden',
                                                            '-File', ('"' + (Join-Path $LauncherDir 'gui.ps1') + '"'))
}

$script:UpdateDone = {
    $res = if (Test-Path -LiteralPath $UpdateResultFile) { ([string](Get-Content -LiteralPath $UpdateResultFile -TotalCount 1 -Encoding UTF8)).Trim() } else { '' }
    if ($res -match '^ok (.+)$') {
        # 不弹「已经更新到」（用户 2026-11-11）：直接重开启动器用上新版本；新版本打开时 Show-VersionNotice 看到升级，
        # 在运行日志 / 新界面的提示条里说一声（所以这里不写 LastVerFile）
        Start-GuiAgain
        $form.Close()
    } elseif ($res -eq 'latest') {
        Show-Info '已经是最新版本，不用更新。'
    } elseif ($res -eq 'full') {
        Show-FullPackage (Read-UpdateCheck)
    }
}

$smallBtns['导入更新包'].Add_Click({
    if ($script:Running) { return }
    if (-not (Confirm-GameClosed '更新整合包之前要先退出游戏。')) { return }
    $ofd = New-Object System.Windows.Forms.OpenFileDialog
    $ofd.Title = '选择暗黑重铸的更新包（可以一次选好几个，会按版本顺序导入）'
    $ofd.Filter = '暗黑重铸更新包 (*.zip)|*.zip'
    $ofd.Multiselect = $true
    if ($ofd.ShowDialog($form) -ne [System.Windows.Forms.DialogResult]::OK) { return }
    $zips = ($ofd.FileNames -join '|') -replace "'", "''"
    Remove-Item -LiteralPath $UpdateResultFile -Force -ErrorAction SilentlyContinue
    $script:AfterRun = $script:UpdateDone
    Start-LauncherRun '导入更新包' @("!-Action update -UpdateZip '" + $zips + "'")
})

# 在线更新（用户 2026-11-11「通过 gitee 实现自动更新」）：update.py --check 的结果在 logs\update_check.json
function Read-UpdateCheck {
    try { return ([System.IO.File]::ReadAllText($UpdateCheckFile, [Text.Encoding]::UTF8) | ConvertFrom-Json) } catch { return $null }
}

function Get-UpdateNotesText($c, [int]$Max = 2400) {
    $t = ''
    foreach ($n in @($c.notes)) {
        if (-not $n) { continue }
        $t += 'v' + $n.version + $(if ($n.date) { '（' + $n.date + '）' } else { '' }) + "`r`n"
        $body = ([string]$n.text).Trim()
        $t += $(if ($body) { ($body -replace "`r?`n", "`r`n") } else { '（没有写更新内容）' }) + "`r`n`r`n"
    }
    if ($t.Length -gt $Max) { $t = $t.Substring(0, $Max) + "……`r`n（完整的更新内容更新后见「更新日志」）" }
    return $t.TrimEnd()
}

# 有新版本：显示更新内容，返回 $true = 现在更新
function Show-UpdateOffer($c) {
    $mb = '{0:0.0}' -f ([double]$c.size / 1MB)
    $dlg = New-Object System.Windows.Forms.Form
    $dlg.Text = '暗黑重铸 · 有新版本 v' + $c.latest
    $dlg.Font = $font
    $dlg.Size = New-Object System.Drawing.Size(720, 480)
    $dlg.StartPosition = 'CenterParent'
    $dlg.FormBorderStyle = 'FixedDialog'
    $dlg.MaximizeBox = $false
    $dlg.MinimizeBox = $false
    Set-DarkForm $dlg
    $head = "现在是 v" + $c.cur + "，可以更新到 v" + $c.latest + "：要下载 " + @($c.chain).Count + " 个更新包，共 " + $mb + " MB。`r`n" +
            "只替换改了的文件，敌人随机结果、存档和角色记录都不受影响；改动前自动备份，失败自动还原。更新前要先退出游戏。`r`n`r`n"
    $card, $tb = New-TextCard 12 12 680 362 ($head + (Get-UpdateNotesText $c))
    $dlg.Controls.Add($card)
    $ok = New-DlgBtn '现在更新' 412 386 140 36 $true
    $ok.DialogResult = 'OK'
    $dlg.Controls.Add($ok)
    $no = New-DlgBtn '以后再说' 560 386 132 36
    $no.DialogResult = 'Cancel'
    $dlg.Controls.Add($no)
    $dlg.AcceptButton = $ok
    $dlg.CancelButton = $no
    $dlg.Add_Shown({ $tb.SelectionLength = 0; $ok.Focus() })
    return ($dlg.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK)
}

# 更新包接不上（跨的版本太多、或者这一版只能发完整包）：打开完整整合包的下载页
function Show-FullPackage($c) {
    if (-not $c) { Show-Info '没有能直接更新的更新包，请下载完整的整合包。'; return }
    $why = "有新版本 v" + $c.latest + "，但没有能从你现在的 v" + $c.cur + " 直接更新的更新包（跨的版本太多，或者这一版改动太大），请下载完整的整合包。"
    if ($c.full_note) { $why += "`r`n`r`n" + $c.full_note }
    if (-not $c.full_url) { Show-Info $why; return }
    $r = Show-DrDialog ($why + "`r`n`r`n下载页：" + $c.full_url) '暗黑重铸 · 需要完整的整合包' @('打开下载页', '关闭') 0 1 'info' $form
    if ($r -eq 0 -and ([string]$c.full_url).StartsWith('https://')) { Start-Process -FilePath ([string]$c.full_url) }
}

function Start-OnlineUpdate {
    if ($script:Running) { return }
    if (-not (Confirm-GameClosed '更新整合包之前要先退出游戏。')) { return }
    Remove-Item -LiteralPath $UpdateResultFile -Force -ErrorAction SilentlyContinue
    $script:AfterRun = $script:UpdateDone
    Start-LauncherRun '在线更新' @('!-Action autoupdate')
}

$script:UpdateChecked = {
    $c = Read-UpdateCheck
    if (-not $c) { Show-Info '检查更新没有完成，详细看运行日志。'; return }
    switch ([string]$c.status) {
        'latest'    { Show-Info ('已经是最新版本 v' + $c.cur + '。') }
        'available' { if (Show-UpdateOffer $c) { Start-OnlineUpdate } }
        'full'      { Show-FullPackage $c }
        default     { Show-Info ('检查更新失败：' + $c.error + "`r`n`r`n网络不好时过一会儿再试；也可以自己下载更新包，用「导入更新包」导入。") }
    }
}

$smallBtns['检查更新'].Add_Click({
    if ($script:Running) { return }
    Remove-Item -LiteralPath $UpdateCheckFile -Force -ErrorAction SilentlyContinue
    $script:AfterRun = $script:UpdateChecked
    Start-LauncherRun '检查更新' @('-Action checkupdate')
})

$smallBtns['更新日志'].Add_Click({
    $cl = Join-Path $Paly '更新日志.txt'
    if (Test-Path -LiteralPath $cl) { Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $cl + '"') }
    else { Show-Info ('找不到更新日志：' + $cl) }
})

$form.Add_FormClosing({
    if ($script:Running) {
        $r = Show-DrDialog '启动器还在运行（生成掉落或等待游戏启动）。关掉窗口不会影响已经启动的游戏，确定关闭吗？' '暗黑重铸' @('关闭', '取消') 0 1 'question' $form
        if ($r -ne 0) { $_.Cancel = $true }
    }
})

Update-Status
Add-Log '选择上面的按钮开始。'
# 一打开：记下版本（降级要警告）；然后确定游戏路径（自动搜索，找不到或找到好几个就立刻让玩家选），
# 免得启动或随机器（要读游戏文件）用到时才发现没有
# 新界面开着时（$script:WebUiOn）不在这里做：等页面加载好由 webui.ps1 的 Start-WebStartup 调，弹窗就显示在新界面里
$script:StartupDone = $false
$script:StartupFlow = {
    Show-VersionNotice
    if (-not (Get-GameRoot)) {
        Add-Log '正在搜索游戏路径...'
        [System.Windows.Forms.Application]::DoEvents()
        if (Ensure-GameRoot) { Add-Log ('游戏路径：' + (Get-GameRoot)) }
        else { Add-Log '还没有设置游戏路径：启动游戏和一键重随敌人前都需要，点「游戏路径」选一下。' }
        Update-Status
    }
    Show-EnemyInfoFirst
    # 记下这个整合包的位置（以前只在启动游戏时记）：以后更新到新版本时从这里找敌人随机结果
    Save-PackPath
    # 刚更新到新版本：旧版本里有敌人随机结果就问要不要沿用
    $c = Ask-OldRandom
    if ($c) { Start-LauncherRun '沿用旧版本的敌人随机结果' @(Get-CarryCall $c) }
}
$form.Add_Shown({ if (-not $script:WebUiOn -and -not $script:StartupDone) { $script:StartupDone = $true; & $script:StartupFlow } })
# 新界面（launcher\webui.ps1，2026-11-10）：经典控件照旧建好，盖一层 WebView2 网页；用不了就保持经典界面
. (Join-Path $LauncherDir 'webui.ps1')
[void](Enable-WebUi)
[void]$form.ShowDialog()
Save-GuiErrors
