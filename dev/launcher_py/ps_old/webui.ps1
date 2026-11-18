# 暗黑重铸启动器的网页界面（用户 2026-11-10「把我们的启动器映射到这个框架上」）：gui.ps1 最后 dot-source 本文件、调 Enable-WebUi。
# 做法：gui.ps1 照旧建好经典界面的所有控件、按钮处理、对话框和后台运行；这里在同一个窗口上盖一层 WebView2（launcher\ui\index.html），
# 把经典控件藏起来。页面的点击转成调用经典按钮的 OnClick（按钮藏着也能调），状态（卡片、按钮副标题、日志、进度、忙不忙）
# 每 300 毫秒读经典控件的属性拼成 JSON，有变化才推给页面。弹窗（提示、确认框、恢复存档、敌人设置、常见问题、有新版本）也显示在页面里（下面「弹窗」一节），
# 选文件 / 文件夹还是 Windows 自带的选择框。
# 用不了（没有 launcher\webview2、电脑没装 WebView2 运行时、有 launcher\classic_ui.txt、页面加载失败）就保持经典界面。
# WebView2 的用户数据放 %LOCALAPPDATA%\Darkforge\WebView2（不能放在 powershell.exe 旁边，那里写不进去）。

$WebUiDir = Join-Path $LauncherDir 'ui'
$WebView2Dir = Join-Path $LauncherDir 'webview2'
$ClassicFlag = Join-Path $LauncherDir 'classic_ui.txt'
$WebLinks = @('https://github.com/tamikip/hyp-launcher-ui')     # 页面能让宿主用浏览器打开的网址（别的一律不开）
# 「模组」一类（用户 2026-11-16「怎么能方便玩家可以自己手动编辑yafsml」，launcher\usermods.ps1）：只在新界面有。(名字, 说明)
$WebModTools = @(
    @('mods 文件夹', '放外观、模型、特效这类 mod（解压后带 parts、chr、sfx 等文件夹的）：一个 mod 一个文件夹，下次启动游戏自动加载，排在整合包前面（同名文件以整合包为准）。文件夹名前加 _ 就停用。整合包更新不会动它'),
    @('DLL 文件夹', '放 DLL 类的 mod（.dll；带配置文件的整个文件夹放进来）：下次启动游戏自动加载，文件名前加 _ 就停用'),
    @('自定义配置', '用记事本打开 YAFSML自定义.ini：改模组加载器的设置（比如游戏里用输入法）、按路径加 mod 或 DLL。整合包更新不会动它；改完下次启动游戏生效')
)

# 「联机」一类（联机分支 coop，联机计划 13.3 C11）：只在新界面有。「联机」打开经典界面同一个联机菜单（gui.ps1 的 Show-CoopMenu，弹窗显示在页面里）
# 联机还在测试，默认不显示（用户 2026-11-17：先合进主分支一起发，联机稳定了再公开）：有 launcher\coop_test.txt 才显示这一类（打包不带它）
$WebCoopOn = Test-Path -LiteralPath (Join-Path $LauncherDir 'coop_test.txt')
$WebCoopTools = @(
    @('联机', '和朋友用 Seamless Co-op 联机（要自己下载放进整合包的 dll\ 文件夹）：房主点「开房」，把联机码发给队友，队友点「加入」'),
    @('联机设置', '用记事本打开 Seamless Co-op 的设置文件（ersc_settings.ini）：随人数加强的血量和伤害等。联机密码开房时自动生成、队友加入时自动填，一般不用改')
)

function Invoke-WebCoopTool([string]$Name) {
    try {
        switch ($Name) {
            '联机' { Show-CoopMenu }
            '联机设置' {
                $e = Find-ErscPath
                if (-not $e) { Show-Info '没找到 Seamless Co-op。它要自己下载：把压缩包里的 SeamlessCoop 文件夹整个放进整合包的 dll\ 文件夹（变成 dll\SeamlessCoop\ersc.dll）。'; return }
                $ini = Join-Path (Split-Path $e -Parent) 'ersc_settings.ini'
                if (-not (Test-Path -LiteralPath $ini)) { Show-Info ('Seamless Co-op 旁边没有设置文件：' + $ini + "`r`n`r`n" + '重新解压一次 Seamless Co-op 的压缩包。'); return }
                Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + $ini + '"')
            }
        }
    } catch { Send-WebJson (@{ type = 'toast'; text = '没能打开：' + $_.Exception.Message; error = $true } | ConvertTo-Json -Compress) }
}

function Invoke-WebModTool([string]$Name) {
    try {
        switch ($Name) {
            'mods 文件夹' {
                if (-not (Test-Path -LiteralPath $UserModDir)) { New-Item -ItemType Directory -Force -Path $UserModDir | Out-Null }
                Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $UserModDir + '"')
            }
            'DLL 文件夹' { Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + (Join-Path $Paly 'dll') + '"') }
            '自定义配置' { Start-Process -FilePath 'notepad.exe' -ArgumentList ('"' + (New-UserIni) + '"') }
        }
    } catch { Send-WebJson (@{ type = 'toast'; text = '没能打开：' + $_.Exception.Message; error = $true } | ConvertTo-Json -Compress) }
}
$script:WebView = $null
$script:WebLast = ''
$script:WebReady = $false
$script:WebUiOn = $false          # 新界面挂上了（Enable-WebUi 成功、还没退回经典界面）：gui.ps1 打开时的检查等页面就绪再做
$script:WebPageReady = $false     # 页面脚本发过 ready
$DlgDir = Join-Path $LauncherDir 'logs\dlg'
$env:DARKFORGE_DLG_DIR = $null    # 更新后重开的启动器会继承旧进程的这两个，先清掉（Enable-WebUi 成功后再设）
$env:DARKFORGE_GUI_PID = $null

function Test-WebUiAvailable {
    if (Test-Path -LiteralPath $ClassicFlag) { return $false }
    if ($env:DARKFORGE_CLASSIC_UI) { return $false }
    foreach ($f in @('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll', 'WebView2Loader.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $WebView2Dir $f))) { return $false }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $WebUiDir 'index.html'))) { return $false }
    try {
        Add-Type -Path (Join-Path $WebView2Dir 'Microsoft.Web.WebView2.Core.dll')
        Add-Type -Path (Join-Path $WebView2Dir 'Microsoft.Web.WebView2.WinForms.dll')
        [Microsoft.Web.WebView2.Core.CoreWebView2Environment]::SetLoaderDllFolderPath($WebView2Dir)
        $v = [Microsoft.Web.WebView2.Core.CoreWebView2Environment]::GetAvailableBrowserVersionString()
        return [bool]$v
    } catch { return $false }
}

# 无边框窗口：拖动（ReleaseCapture + WM_NCLBUTTONDOWN）、Windows 11 圆角
if (-not ('DarkforgeWebNative' -as [type])) {
    Add-Type @"
using System; using System.Runtime.InteropServices;
public static class DarkforgeWebNative {
    [DllImport("user32.dll")] public static extern bool ReleaseCapture();
    [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
    [DllImport("dwmapi.dll")] public static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref int v, int size);
    public static void Drag(IntPtr h) { ReleaseCapture(); SendMessage(h, 0xA1, (IntPtr)2, IntPtr.Zero); }
    public static void Round(IntPtr h) { int v = 2; try { DwmSetWindowAttribute(h, 33, ref v, 4); } catch { } }
}
"@
}

function Get-AccentName($c) {
    $a = $c.ToArgb()
    if ($a -eq $Thm::Gold.ToArgb()) { return 'gold' }
    if ($a -eq $Thm::Ok.ToArgb()) { return 'ok' }
    if ($a -eq $Thm::Warn.ToArgb()) { return 'warn' }
    return 'muted'
}

# 存档里有没有死亡以上难度的角色（gui.ps1 的 Get-HighChars：角色记录 + 核对存档里的名字，会调一次 Python）：
# 页面据此选背景（用户 2026-11-10「第一次启动时默认用低难的图 有高难角色后改为高难」）。只在页面就绪和每次运行结束后算，不放进 300 毫秒的定时器
$script:WebHasHard = $false
$script:WebWasBusy = $false
function Update-WebHasHard {
    try { $script:WebHasHard = [bool](@(Get-HighChars).Count) } catch { $script:WebHasHard = $false }
}

# 在线更新（2026-11-11）：页面就绪后、之后每 5 分钟（页面设置里「自动检查更新」开着才会发 checkupdate，df.js autoCheck）在后台跑一次 update.py --check，不进运行日志；
# 结果（logs\update_check.json，gui.ps1 的 Read-UpdateCheck）放进状态推给页面：有新版本时「工具」按钮上出红点、面板上方出一条「有新版本」。
# 手动「检查更新」和在线更新跑完后也重读一次。检查结果是别的版本（刚更新过）的不算
$script:WebUpdProc = $null
$script:WebUpdate = $null
function Start-WebUpdateCheck {
    if ($script:WebUpdProc -and -not $script:WebUpdProc.HasExited) { return }
    $py = Join-Path $LauncherDir 'python\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { return }
    $a = '-X utf8 "' + (Join-Path $LauncherDir 'update.py') + '" --root "' + (Split-Path -Parent $LauncherDir) + '" --check'
    if ($env:DARKFORGE_UPDATE_MANIFEST) { $a += ' --manifest "' + $env:DARKFORGE_UPDATE_MANIFEST + '"' }     # 测试用（本机模拟服务器）
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $py
    $psi.Arguments = $a
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WorkingDirectory = $LauncherDir
    try { $script:WebUpdProc = [System.Diagnostics.Process]::Start($psi) } catch { $script:WebUpdProc = $null }
}

function Get-WebUpdateInfo {
    $c = Read-UpdateCheck
    if (-not $c -or [string]$c.cur -ne [string]$PackVersion) { return $null }
    $notes = Get-UpdateNotesText $c 360
    return @{ status = [string]$c.status; cur = [string]$c.cur; latest = [string]$c.latest; size = [double]$c.size
              checked = [string]$c.time; error = [string]$c.error; notes = $notes }
}

# 敌人信息 mod（Souls Vision）开关：reroll\state\enemy_info_mod.txt（on / off，没有 = 没动过，照常加载；启动器 Test-EnemyInfoMod 读）
function Get-WebEnemyInfo {
    try {
        if (Test-Path -LiteralPath $EnemyInfoChoice) { return ([System.IO.File]::ReadAllText($EnemyInfoChoice)).Trim() }
    } catch { }
    return ''
}

function Get-WebState {
    $lines = @($logBox.Lines | Where-Object { $_ -ne $null })
    if ($lines.Count -gt 300) { $lines = $lines[($lines.Count - 300)..($lines.Count - 1)] }
    while ($lines.Count -and -not $lines[-1]) { $lines = @($lines[0..($lines.Count - 2)]) }
    $pct = $null
    if ($script:PlayerView -and $script:BarLine -ge 0 -and $script:BarLine -lt $script:ViewLines.Count -and ([string]$script:ViewLines[$script:BarLine]) -match '(\d+)%\s*$') { $pct = [int]$Matches[1] }
    $rs = Get-RandomizerStatus
    $card = { param($c) @{ value = [string]$c.Value; accent = (Get-AccentName $c.Accent); tip = [string]$ToolTipCtl.GetToolTip($c) } }
    return @{
        type = 'state'; version = [string]$PackVersion; busy = [bool]$script:Running; hasHard = [bool]$script:WebHasHard
        randomizerOk = [bool]$rs.Ok; mode = $(if ($rs.Ok) { 'rand' } else { 'vanilla' })
        cards = @{ path = (& $card $cardPath); rand = (& $card $cardRand); last = (& $card $cardLast) }
        subs = @{ launchV = [string]$bLaunchV.Sub; launchR = [string]$bLaunchR.Sub; randEnemy = [string]$bRandEnemy.Sub; randItems = '骨灰、开局装备重抽，新角色生效' }
        run = @{ player = [bool]$script:PlayerView; lines = [string[]]$lines; pct = $pct; error = [bool]$script:SawError }
        # 「打开随机器」在新界面里是工具里的一行（和「一键重随物品」对调了位置，用户 2026-11-12），说明用经典界面那个大按钮的
        tools = @($small | ForEach-Object { @{ name = $_[0]; tip = $_[2] } }) + @(@{ name = '打开随机器'; tip = ([string]$bRandomizer.Sub + '。' + [string]$ToolTipCtl.GetToolTip($bRandomizer)) }) +
                @($WebModTools | ForEach-Object { @{ name = $_[0]; tip = $_[1] } }) +
                @($WebCoopTools | Where-Object { $WebCoopOn } | ForEach-Object { @{ name = $_[0]; tip = $_[1] } })
        coop = [bool]$WebCoopOn
        update = $script:WebUpdate
        enemyInfo = (Get-WebEnemyInfo)
    }
}

function Send-WebJson([string]$Json) {
    if (-not $script:WebReady -or -not $script:WebView -or -not $script:WebView.CoreWebView2) { return }
    try { $script:WebView.CoreWebView2.PostWebMessageAsJson($Json) } catch { }
}

function Push-WebState([switch]$Force) {
    if (-not $script:WebReady) { return }
    if ($script:WebWasBusy -and -not $script:Running) { Update-WebHasHard; $script:WebUpdate = Get-WebUpdateInfo }   # 刚跑完（可能刚玩过、进了死亡以上；或者刚检查过更新）
    $script:WebWasBusy = [bool]$script:Running
    if ($script:WebUpdProc -and $script:WebUpdProc.HasExited) { $script:WebUpdProc = $null; $script:WebUpdate = Get-WebUpdateInfo }
    $j = (Get-WebState) | ConvertTo-Json -Depth 6 -Compress
    if ($Force -or $j -ne $script:WebLast) { $script:WebLast = $j; Send-WebJson $j }
}

# 刚更新到新版本（gui.ps1 的 Show-VersionNotice 设的 $script:UpdatedNote）：弹一条提示、切到「更新日志」页。
# 页面发 ready 时宿主可能还没标记加载完成（NavigationCompleted 在页面脚本之后），两处都调，发出去了才清掉
function Send-WebUpdatedNote {
    if (-not $script:UpdatedNote -or -not $script:WebReady) { return }
    Send-WebJson (@{ type = 'toast'; text = $script:UpdatedNote; ms = 6000 } | ConvertTo-Json -Compress)
    Send-WebJson '{"type":"tab","tab":"news"}'
    $script:UpdatedNote = $null
}

function Send-WebChangelog {
    $cl = Join-Path $Paly '更新日志.txt'
    $text = ''
    try {
        $all = [System.IO.File]::ReadAllText($cl, [Text.Encoding]::UTF8)
        $idx = [regex]::Matches($all, '(?m)^v\d[^\r\n]*\r?\n-{3,}')
        $end = if ($idx.Count -gt 3) { $idx[3].Index } else { $all.Length }
        $text = $all.Substring(0, [Math]::Min($all.Length, $end))
    } catch { }
    Send-WebJson (@{ type = 'changelog'; text = $text } | ConvertTo-Json -Compress)
}

# ---------------------------------------------------------------- 弹窗（用户 2026-11-11「能把目前的弹窗都接入新的ui吗」）
# gui.ps1 的弹窗在这里换成页面里的弹层（df.js 的 openDialog），调用的地方不用改：Show-DrDialog（提示 / 确认框，ui.ps1）、
# Show-BackupPick（恢复存档：手动选）、Show-EnemyDialog（敌人设置）、Show-Faq（常见问题）、Show-UpdateOffer（有新版本）。
# 原来的函数改名成 …Classic 留着：新界面用不了（经典界面、页面没加载好、窗口在关）时照旧弹原来的暗色窗口。
# 弹层是同步的：发给页面后在这里转消息循环（DoEvents）等页面回答，调用的地方照旧拿到返回值。WebView2 的事件处理里不能这样等
# （等的时候它的消息进不来），所以页面发来的点击先排队，事件处理完了再由 $script:WebQTimer 执行（Receive-WebMessage）。
# 启动器后台进程（launcher.ps1：双显卡加载着敌人信息 mod 时崩了问要不要关、游戏出错导出了诊断包）的弹窗：ui.ps1 的 Request-HostDialog 把请求写进 logs\dlg，
# 这边 Watch-HostDialogs 在页面里弹、把选了第几个写回去；启动器窗口关了它就自己弹原来的窗口。
$script:WebDlgSeq = 0
$script:WebDlgAns = @{}                                       # 弹层号 → 页面的回答
$script:WebDlgOps = New-Object System.Collections.ArrayList   # 弹层里不关窗口的按钮（常见问题里的「打开存档文件夹」等）点了的
$script:WebQueue = New-Object System.Collections.Queue
$script:WebQBusy = $false
$script:HostDlgBusy = $false

function Test-WebDialog {
    # 主窗口是 ShowDialog 开的：Close() 只设 DialogResult，要回到它自己的消息循环才真关（在这里等弹层时回不去），所以也看 DialogResult
    return [bool]($script:WebUiOn -and $script:WebReady -and $script:WebPageReady -and $script:WebView -and $script:WebView.CoreWebView2 -and
                   -not $form.IsDisposed -and $form.Visible -and $form.DialogResult -eq [System.Windows.Forms.DialogResult]::None)
}

# 在页面里弹一层，等回答（页面回的 {id, result = 第几个按钮（-1 = 点 × 关掉）, pick, e, b}）。
# $OnOp：弹层里不关窗口的按钮点了时调（参数是 op），返回 'close' 就关掉这层（返回 @{ result = -2 }）。
# 等的时候页面没了 / 窗口关了返回 $null（调用的按「没选」处理）
function Show-WebModal([hashtable]$Spec, [scriptblock]$OnOp = $null) {
    $script:WebDlgSeq++
    $id = $script:WebDlgSeq
    $Spec.type = 'dialog'
    $Spec.id = $id
    Send-WebJson ($Spec | ConvertTo-Json -Depth 6 -Compress)
    while (-not $script:WebDlgAns.ContainsKey($id)) {
        if (-not (Test-WebDialog)) { return $null }
        foreach ($o in @($script:WebDlgOps | Where-Object { $_.id -eq $id })) {
            $script:WebDlgOps.Remove($o)
            $r = if ($OnOp) { & $OnOp ([string]$o.op) } else { $null }
            if (@($r) -contains 'close') {
                Send-WebJson (@{ type = 'dialogclose'; id = $id } | ConvertTo-Json -Compress)
                return @{ result = -2 }
            }
        }
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 15
    }
    $a = $script:WebDlgAns[$id]
    $script:WebDlgAns.Remove($id)
    return $a
}

# 提示 / 确认框（ui.ps1 的 Show-DrDialog，参数一样）：给了父窗口（图形界面里的都给了 $form）、新界面能用就在页面里弹
${function:Show-DrDialogClassic} = ${function:Show-DrDialog}
function Show-DrDialog {
    param([string]$Text, [string]$Title = '暗黑重铸', [string[]]$Buttons = @('确定'), [int]$Default = 0, [int]$Cancel = -1,
          [string]$Icon = 'info', $Owner = $null)
    if ($Owner -and (Test-WebDialog)) {
        $a = Show-WebModal @{ kind = 'msg'; title = $Title; text = $Text; buttons = [string[]]$Buttons; def = $Default; cancel = $Cancel; icon = $Icon }
        if ($null -eq $a) { return $Cancel }
        return [int]$a.result
    }
    return (Show-DrDialogClassic -Text $Text -Title $Title -Buttons $Buttons -Default $Default -Cancel $Cancel -Icon $Icon -Owner $Owner)
}

# 恢复存档：手动选一份备份
${function:Show-BackupPickClassic} = ${function:Show-BackupPick}
function Show-BackupPick($Items) {
    if (-not (Test-WebDialog)) { return (Show-BackupPickClassic $Items) }
    $a = Show-WebModal @{ kind = 'pick'; title = '恢复存档：手动选择备份'; icon = ''; text = $BackupPickHelp
                          items = [string[]]@($Items | ForEach-Object { Get-BackupText $_ }); sel = 0
                          buttons = @('恢复选中的这份', '取消'); def = 0; cancel = 1 }
    if ($null -eq $a -or [int]$a.result -ne 0 -or $null -eq $a.pick) { return -1 }
    $i = [int]$a.pick
    if ($i -lt 0 -or $i -ge @($Items).Count) { return -1 }
    return $i
}

# 敌人设置：两组档位（页面上点了哪档回 e / b，没点过是 -1，保存时照原来的数）
${function:Show-EnemyDialogClassic} = ${function:Show-EnemyDialog}
function Show-EnemyDialog($st, $base) {
    if (-not (Test-WebDialog)) { return (Show-EnemyDialogClassic $st $base) }
    $el = @(for ($i = 0; $i -lt $EliteLevels.Count; $i++) { @{ name = $EliteLevels[$i][0]; sub = $EliteLevels[$i][2]; desc = (Get-EliteDesc $EliteLevels[$i][1] $base) } })
    $bl = @(for ($i = 0; $i -lt $BossLevels.Count; $i++) { @{ name = $BossLevels[$i][0]; sub = $BossLevels[$i][2]; desc = (Get-BossDesc $BossLevels[$i][1]) } })
    $a = Show-WebModal @{ kind = 'enemy'; title = '暗黑重铸 · 敌人设置'; icon = ''
        elite = @{ title = '精英怪比例'; desc = '敌人随机时，普通敌人里有多少换成精英怪（越往后的地区越多）。'; levels = $el; sel = $st.E; orig = (Get-EliteDesc $st.EV $base) }
        boss = @{ title = '头目出现在普通敌人位置'; desc = '开启后，敌人随机时有一部分普通敌人会换成随机头目，路上可能突然遇到头目。'; levels = $bl; sel = $st.B; orig = (Get-BossDesc $st.BV) }
        note = '这两项只影响敌人随机：保存后要点「一键重随敌人」才会生效，已经随机好的敌人不会变。没开敌人随机（一键启动 · 无敌人随机）时不起作用。'
        buttons = @('保存并重随敌人', '只保存', '取消'); def = 0; cancel = 2 }
    if ($null -eq $a) { return $st }
    $r = [int]$a.result
    if ($r -ne 0 -and $r -ne 1) { return $st }
    $e = if ($null -ne $a.e) { [int]$a.e } else { -1 }
    $b = if ($null -ne $a.b) { [int]$a.b } else { -1 }
    if ($e -ge 0 -and $e -lt $EliteLevels.Count) { $st.E = $e; $st.ED = $true }
    if ($b -ge 0 -and $b -lt $BossLevels.Count) { $st.B = $b; $st.BD = $true }
    $st.Go = $(if ($r -eq 0) { 'rand' } else { 'save' })
    return $st
}

# 常见问题：左下角几个按钮点了不关窗口（打开文件夹）；「沿用旧版本的敌人随机」确认后关掉、开始复制
${function:Show-FaqClassic} = ${function:Show-Faq}
function Show-Faq {
    if (-not (Test-WebDialog)) { Show-FaqClassic; return }
    $ops = @(@{ op = 'bk'; label = '打开自动备份文件夹' }, @{ op = 'save'; label = '打开存档文件夹' })
    $need = (Get-RandomizerStatus).Ok -and (Test-NeedOldRandom)
    $script:FaqCarry = if ($need) { @(Find-OldRandoms) | Select-Object -First 1 } else { $null }
    $script:FaqGo = $null
    if ($need) { $ops += @{ op = 'carry'; label = '沿用旧版本的敌人随机' } }
    [void](Show-WebModal @{ kind = 'msg'; wide = $true; title = '常见问题'; icon = ''; text = (Get-FaqText); ops = $ops
                            buttons = @('关闭'); def = 0; cancel = 0 } {
        param($op)
        switch ($op) {
            'bk' {
                $d = if (Test-Path -LiteralPath $RngBackupDir) { $RngBackupDir } else { $RngSaveRoot }
                if (-not (Test-Path -LiteralPath $d)) { Show-Info ('还没有备份（' + $RngBackupDir + '）：启动过一次游戏后才会有。'); return }
                Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $d + '"')
            }
            'save' {
                if (-not (Test-Path -LiteralPath $RngSaveRoot)) { Show-Info ('没有找到存档文件夹：' + $RngSaveRoot); return }
                Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $RngSaveRoot + '"')
            }
            'carry' {
                if (-not $script:FaqCarry) {
                    $script:FaqCarry = Select-OldPack
                    if (-not $script:FaqCarry) { return }
                }
                $c = $script:FaqCarry
                $msg = "把旧版本整合包里的敌人随机结果复制过来（约 100 MB，几秒钟），敌人和之前一模一样：`r`n" +
                       "  文件夹：" + $c.Pack + "（v" + $c.Version + "）`r`n" +
                       "  随机化于：" + $c.Time.ToString('yyyy-MM-dd HH:mm') + $(if ($c.Seed) { "，种子 " + $c.Seed } else { '' }) + "`r`n`r`n现在复制吗？"
                if (-not (Confirm-Box $msg '沿用旧版本的敌人随机结果')) { return }
                $script:FaqGo = $c
                return 'close'
            }
        }
    })
    if ($script:FaqGo) { $c = $script:FaqGo; $script:FaqGo = $null; Start-LauncherRun '沿用旧版本的敌人随机结果' @(Get-CarryCall $c) }
}

# 有新版本：更新内容 + 现在更新 / 以后再说
${function:Show-UpdateOfferClassic} = ${function:Show-UpdateOffer}
function Show-UpdateOffer($c) {
    if (-not (Test-WebDialog)) { return (Show-UpdateOfferClassic $c) }
    $mb = '{0:0.0}' -f ([double]$c.size / 1MB)
    $head = "现在是 v" + $c.cur + "，可以更新到 v" + $c.latest + "：要下载 " + @($c.chain).Count + " 个更新包，共 " + $mb + " MB。`r`n" +
            "只替换改了的文件，敌人随机结果、存档和角色记录都不受影响；改动前自动备份，失败自动还原。更新前要先退出游戏。`r`n`r`n"
    return ((Show-DrDialog ($head + (Get-UpdateNotesText $c)) ('暗黑重铸 · 有新版本 v' + $c.latest) @('现在更新', '以后再说') 0 1 'info' $form) -eq 0)
}

# 后台进程的弹窗请求（ui.ps1 的 Request-HostDialog）：<id>.req.json 改名成 .busy.json 认领，弹完把选了第几个写进 <id>.ans.json
function Show-WebWindowFront {
    try {
        if ($form.WindowState -eq 'Minimized') { $form.WindowState = 'Normal' }
        $form.TopMost = $true
        $form.TopMost = $false
        $form.Activate()
    } catch { }
}

function Watch-HostDialogs {
    if ($script:HostDlgBusy -or -not [System.IO.Directory]::Exists($DlgDir)) { return }
    $f = @([System.IO.Directory]::GetFiles($DlgDir, '*.req.json')) | Select-Object -First 1
    if (-not $f) { return }
    $busy = $f.Substring(0, $f.Length - 9) + '.busy.json'
    $ans = $f.Substring(0, $f.Length - 9) + '.ans.json'
    try { [System.IO.File]::Move($f, $busy) } catch { return }       # 后台进程等不及已经自己弹了
    $script:HostDlgBusy = $true
    try {
        $q = [System.IO.File]::ReadAllText($busy, [Text.Encoding]::UTF8) | ConvertFrom-Json
        [System.IO.File]::Delete($busy)
        Show-WebWindowFront
        $r = Show-DrDialog ([string]$q.text) ([string]$q.title) ([string[]]@($q.buttons)) ([int]$q.def) ([int]$q.cancel) ([string]$q.icon) $form
        [System.IO.File]::WriteAllText($ans + '.tmp', [string][int]$r)
        [System.IO.File]::Move($ans + '.tmp', $ans)
    } catch {
        try { [System.IO.File]::Delete($busy) } catch { }
    } finally { $script:HostDlgBusy = $false }
}

# 页面发来的消息：弹层的回答、拖动 / 最小化马上处理（不会弹窗），别的排队等这次事件处理完再做（见上面）
function Add-WebQueue([string]$Json) {
    $script:WebQueue.Enqueue($Json)
    $script:WebQTimer.Start()
}

function Receive-WebMessage([string]$Json) {
    try { $m = $Json | ConvertFrom-Json } catch { return }
    $a = [string]$m.action
    if ($a -eq 'dialog') { $script:WebDlgAns[[int]$m.id] = $m; return }
    if ($a -eq 'dialogop') { [void]$script:WebDlgOps.Add(@{ id = [int]$m.id; op = [string]$m.op }); return }
    if ($a -eq 'win' -and [string]$m.op -ne 'close') { Invoke-WebMessage $Json; return }
    Add-WebQueue $Json
}

$script:WebQTimer = New-Object System.Windows.Forms.Timer
$script:WebQTimer.Interval = 1
$script:WebQTimer.Add_Tick({
    $script:WebQTimer.Stop()
    if ($script:WebQBusy) { return }          # 前一个还在等弹窗：做完它会接着做排着的
    $script:WebQBusy = $true
    try {
        while ($script:WebQueue.Count -gt 0) {
            $j = [string]$script:WebQueue.Dequeue()
            try { Invoke-WebMessage $j } catch { Add-Log ('界面操作出错：' + $_.Exception.Message) }
        }
    } finally { $script:WebQBusy = $false }
})

# 打开时的检查（gui.ps1 的 $script:StartupFlow：版本、游戏路径、沿用旧版本的敌人随机）：新界面要等页面就绪；退回经典界面了就直接做
function Start-WebStartup {
    if ($script:StartupDone -or -not $script:StartupFlow) { return }
    if ($script:WebUiOn -and -not ($script:WebReady -and $script:WebPageReady)) { return }
    $script:StartupDone = $true
    & $script:StartupFlow
    Send-WebUpdatedNote
}

# 调经典按钮的点击处理（按钮藏着、PerformClick 不管用，直接调 OnClick）
function Invoke-ClassicClick($Btn) {
    if (-not $Btn -or -not $Btn.Enabled) { return }
    $m = [System.Windows.Forms.Control].GetMethod('OnClick', [Reflection.BindingFlags]'NonPublic, Instance')
    [void]$m.Invoke($Btn, @([EventArgs]::Empty))
}

function Invoke-WebMessage([string]$Json) {
    try { $m = $Json | ConvertFrom-Json } catch { return }
    switch ([string]$m.action) {
        'ready'      {
            $script:WebPageReady = $true
            Update-WebHasHard; Push-WebState -Force
            Send-WebUpdatedNote
            if ($script:WebShot) { Start-WebShot }
            Start-WebStartup
        }
        '_startup'   { Start-WebStartup }        # 宿主自己排的：页面加载完成 / 退回经典界面
        'changelog'  { Send-WebChangelog }
        'launch'     { if ($m.mode -eq 'vanilla') { Invoke-ClassicClick $bLaunchV } else { Invoke-ClassicClick $bLaunchR } }
        'randenemy'  { Invoke-ClassicClick $bRandEnemy }
        'randomizer' { Invoke-ClassicClick $bRandomizer }
        'checkupdate' { Start-WebUpdateCheck }
        'enemyinfo'  {
            $v = $(if ([string]$m.value -eq 'off') { 'off' } else { 'on' })
            try {
                New-Item -ItemType Directory -Force -Path (Split-Path $EnemyInfoChoice -Parent) | Out-Null
                [System.IO.File]::WriteAllText($EnemyInfoChoice, ($v + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
                Send-WebJson (@{ type = 'toast'; text = $(if ($v -eq 'off') { '已关掉敌人信息 mod，下次启动游戏时生效' } else { '已打开敌人信息 mod，下次启动游戏时生效' }) } | ConvertTo-Json -Compress)
            } catch { Send-WebJson (@{ type = 'toast'; text = '没能保存设置：' + $_.Exception.Message; error = $true } | ConvertTo-Json -Compress) }
        }
        'autoupdate' {
            if ($script:Running) { break }
            $c = Read-UpdateCheck
            if ($c -and [string]$c.cur -eq [string]$PackVersion -and $c.status -eq 'available') { if (Show-UpdateOffer $c) { Start-OnlineUpdate } }
            elseif ($c -and [string]$c.cur -eq [string]$PackVersion -and $c.status -eq 'full') { Show-FullPackage $c }
            else { Invoke-ClassicClick $smallBtns['检查更新'] }
        }
        'tool'       {
            $n = [string]$m.name
            if ($smallBtns.ContainsKey($n)) { Invoke-ClassicClick $smallBtns[$n] }
            elseif (@($WebModTools | ForEach-Object { $_[0] }) -contains $n) { Invoke-WebModTool $n }
            elseif ($WebCoopOn -and @($WebCoopTools | ForEach-Object { $_[0] }) -contains $n) { Invoke-WebCoopTool $n }
        }
        'openurl'    {      # 「关于」里的链接：只开写死的这几个，用系统默认浏览器
            if ($WebLinks -contains [string]$m.url) { Start-Process -FilePath ([string]$m.url) }
        }
        'classic'    {
            $r = Show-DrDialog "下次打开启动器时换回经典界面（功能完全一样）。`r`n`r`n想再换回新界面：删掉 launcher\classic_ui.txt。" '暗黑重铸 · 经典界面' @('换回经典界面', '取消') 0 1 'question' $form
            if ($r -eq 0) {
                try { [System.IO.File]::WriteAllText($ClassicFlag, "删掉这个文件就会用新界面。`r`n", (New-Object System.Text.UTF8Encoding($true))) } catch { }
                Send-WebJson '{"type":"toast","text":"已设置：下次打开启动器时用经典界面"}'
            }
        }
        'win'        {
            switch ([string]$m.op) {
                'drag'     { [DarkforgeWebNative]::Drag($form.Handle) }
                'minimize' { $form.WindowState = 'Minimized' }
                'close'    { $form.Close() }
            }
        }
    }
    Push-WebState
}

# 窗口大小：设计是 1280×720；屏幕（工作区）放不下就按 16:9 缩到 92%
function Set-WebWindowSize {
    $wa = [System.Windows.Forms.Screen]::FromControl($form).WorkingArea
    $scale = $form.DeviceDpi / 96.0
    $w = [int](1280 * $scale); $h = [int](720 * $scale)
    $k = [Math]::Min(1.0, [Math]::Min(($wa.Width * 0.92) / $w, ($wa.Height * 0.92) / $h))
    $form.MinimumSize = New-Object System.Drawing.Size(0, 0)
    $form.ClientSize = New-Object System.Drawing.Size([int]($w * $k), [int]($h * $k))
    $form.Location = New-Object System.Drawing.Point(($wa.X + [int](($wa.Width - $form.Width) / 2)), ($wa.Y + [int](($wa.Height - $form.Height) / 2)))
}

function Restore-ClassicUi {
    if ($script:WebView) { try { $form.Controls.Remove($script:WebView); $script:WebView.Dispose() } catch { } }
    $script:WebView = $null; $script:WebReady = $false; $script:WebUiOn = $false
    $env:DARKFORGE_DLG_DIR = $null; $env:DARKFORGE_GUI_PID = $null
    Add-WebQueue '{"action":"_startup"}'       # 打开时的检查还没做的话，用经典界面做
    $form.FormBorderStyle = $script:ClassicBorder
    $form.MinimumSize = $script:ClassicMin
    $form.ClientSize = $script:ClassicSize
    foreach ($c in $script:ClassicControls) { $c.Visible = $true }
    $form.CenterToScreen()
}

# 测试用：设了 DARKFORGE_WEBUI_SHOT=<png> 时，页面就绪后截一张图（WebView2 自己的 CapturePreview）然后关窗口
$script:WebShot = $env:DARKFORGE_WEBUI_SHOT
function Start-WebShot {
    # 分三步（等页面画好 → 可选执行一段脚本 → 截图 → 等截完关窗口），都用脚本级变量（事件处理里看不到这个函数的局部变量）
    $script:ShotStep = 0
    $script:ShotTimer = New-Object System.Windows.Forms.Timer
    $script:ShotTimer.Interval = [int]$(if ($env:DARKFORGE_WEBUI_SHOT_DELAY) { $env:DARKFORGE_WEBUI_SHOT_DELAY } else { 1500 })
    $script:ShotTimer.Add_Tick({
        $script:ShotStep++
        if ($script:ShotStep -eq 1) {
            if ($env:DARKFORGE_WEBUI_SHOT_JS) { [void]$script:WebView.CoreWebView2.ExecuteScriptAsync($env:DARKFORGE_WEBUI_SHOT_JS) }
            $script:ShotTimer.Interval = [int]$(if ($env:DARKFORGE_WEBUI_SHOT_AFTER) { $env:DARKFORGE_WEBUI_SHOT_AFTER } else { 800 })    # 脚本执行后多久截图
        } elseif ($script:ShotStep -eq 2) {
            $script:ShotStream = [System.IO.File]::Create($script:WebShot)
            $script:ShotTask = $script:WebView.CoreWebView2.CapturePreviewAsync([Microsoft.Web.WebView2.Core.CoreWebView2CapturePreviewImageFormat]::Png, $script:ShotStream)
            $script:ShotTimer.Interval = 200
        } elseif ($script:ShotTask -and $script:ShotTask.IsCompleted) {
            $script:ShotTimer.Stop(); $script:ShotStream.Dispose(); $form.Close()
        }
    })
    $script:ShotTimer.Start()
}

# 开新界面：成功挂上返回 $true（真正加载完成前失败会自动退回经典界面）
function Enable-WebUi {
    if (-not (Test-WebUiAvailable)) { return $false }
    try {
        $script:ClassicControls = @($form.Controls | ForEach-Object { $_ })
        $script:ClassicBorder = $form.FormBorderStyle
        $script:ClassicSize = $form.ClientSize
        $script:ClassicMin = $form.MinimumSize
        $wv = New-Object Microsoft.Web.WebView2.WinForms.WebView2
        $props = New-Object Microsoft.Web.WebView2.WinForms.CoreWebView2CreationProperties
        $props.UserDataFolder = Join-Path $env:LOCALAPPDATA 'Darkforge\WebView2'
        $props.AdditionalBrowserArguments = '--disable-features=msSmartScreenProtection'
        $wv.CreationProperties = $props
        $wv.DefaultBackgroundColor = [System.Drawing.Color]::FromArgb(17, 16, 14)
        $wv.Dock = 'Fill'
        $script:WebView = $wv
        foreach ($c in $script:ClassicControls) { $c.Visible = $false }
        $form.FormBorderStyle = 'None'
        Set-WebWindowSize
        $form.Controls.Add($wv)
        $wv.BringToFront()
        $wv.Add_CoreWebView2InitializationCompleted({
            param($s, $e)
            if (-not $e.IsSuccess) { Add-Log ('新界面加载失败，改用经典界面：' + $e.InitializationException); Restore-ClassicUi; return }
            $cw = $script:WebView.CoreWebView2
            $cw.Settings.AreDevToolsEnabled = [bool]$env:DARKFORGE_WEBUI_DEVTOOLS
            $cw.Settings.AreDefaultContextMenusEnabled = $false
            $cw.Settings.IsStatusBarEnabled = $false
            $cw.Settings.IsZoomControlEnabled = $false
            $cw.Settings.AreBrowserAcceleratorKeysEnabled = $false
            $cw.SetVirtualHostNameToFolderMapping('darkforge.local', $WebUiDir, [Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind]::Allow)
            $cw.add_WebMessageReceived({ param($s2, $m) Receive-WebMessage $m.WebMessageAsJson })
            $cw.add_NavigationCompleted({
                param($s3, $n)
                if ($n.IsSuccess) { $script:WebReady = $true; Push-WebState -Force; Send-WebUpdatedNote; Add-WebQueue '{"action":"_startup"}' }
                else { Add-Log ('新界面页面打不开（' + $n.WebErrorStatus + '），改用经典界面。'); Restore-ClassicUi }
            })
            $cw.add_NewWindowRequested({ param($s4, $w) $w.Handled = $true })    # 页面里不开新窗口
            $cw.Navigate('https://darkforge.local/index.html')
        })
        $form.Add_HandleCreated({ [DarkforgeWebNative]::Round($form.Handle) })
        $form.Add_Shown({ [void]$script:WebView.EnsureCoreWebView2Async($null) })
        $script:WebTimer = New-Object System.Windows.Forms.Timer
        $script:WebTimer.Interval = 300
        $script:WebTimer.Add_Tick({ Push-WebState; Watch-HostDialogs })
        $script:WebTimer.Start()
        $script:WebUiOn = $true
        $env:DARKFORGE_DLG_DIR = $DlgDir          # 启动器后台进程（launcher.ps1）的弹窗交给这边显示（ui.ps1 的 Request-HostDialog）
        $env:DARKFORGE_GUI_PID = [string]$PID
        return $true
    } catch {
        Add-Log ('新界面初始化出错，改用经典界面：' + $_.Exception.Message)
        Restore-ClassicUi
        return $false
    }
}
