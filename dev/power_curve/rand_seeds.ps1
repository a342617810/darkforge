# Power-curve helper: run the enemy randomizer on COPIES with new seeds (dev only, never packaged).
# Each copy lives in <Rz>\seed_<k>\ (program files copied, diste\ is a junction to the real one). Junctions need NTFS and the
# game drive may be exFAT, so the default Rz is on C: under %LOCALAPPDATA%\DarkReforged_dev\rz.
# The real randomizer\ output and its settings are never touched:
#   - options are READ from the real randomizer settings (launcher\randomizer_settings_path.txt), never written;
#   - each copy gets its own settings file (the randomizer keys settings by exe path) and its own map file in Rz.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File rand_seeds.ps1 -Count 3
param([int]$Count = 3, [string]$Rz = (Join-Path $env:LOCALAPPDATA 'DarkReforged_dev\rz'))
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Paly = (Resolve-Path (Join-Path $Here '..\..')).Path
$LauncherDir = Join-Path $Paly 'launcher'
$RealRand = Join-Path $Paly 'randomizer'
New-Item -ItemType Directory -Force -Path $Rz | Out-Null

$root = ([string](Get-Content -LiteralPath (Join-Path $LauncherDir 'game_path.txt') -TotalCount 1 -Encoding UTF8)).Trim()
$GameExe = Join-Path $root 'Game\eldenring.exe'
if (-not (Test-Path -LiteralPath $GameExe)) { throw "game exe not found: $GameExe" }

# options the player last used in the real randomizer (read-only)
$RandomDir = $RealRand
. (Join-Path $LauncherDir 'randomize.ps1')
$realMap = Join-Path $LauncherDir 'randomizer_settings_path.txt'
$realFile = if (Test-Path -LiteralPath $realMap) { ([string](Get-Content -LiteralPath $realMap -TotalCount 1 -Encoding UTF8)).Trim() } else { '' }
$opt = Get-RandSetting $realFile 'Options'
if (-not $opt -or $opt -notmatch '\bv\d+\b') { $opt = $RandDefaultOptions }
$tok = @(($opt -split '\s+') | Where-Object { $_ -and $_ -notmatch '^seed2?:' })
if ($tok -notcontains 'enemy') { $tok += 'enemy' }
$Options = $tok -join ' '
Write-Host "options: $Options"

for ($k = 1; $k -le $Count; $k++) {
    $dir = Join-Path $Rz ('seed_' + $k)
    if ((Test-Path -LiteralPath (Join-Path $dir 'regulation.bin')) -and (Get-ChildItem -LiteralPath (Join-Path $dir 'spoiler_logs') -Filter '*_log_*.txt' -ErrorAction SilentlyContinue)) {
        Write-Host "seed_$k already done, skipped"
        continue
    }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Get-ChildItem -LiteralPath $RealRand -File | Where-Object { $_.Name -ne 'regulation.bin' } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dir -Force }
    foreach ($d in 'dll', 'presets') { Copy-Item -LiteralPath (Join-Path $RealRand $d) -Destination $dir -Recurse -Force }
    if (-not (Test-Path -LiteralPath (Join-Path $dir 'diste'))) { cmd /c mklink /J (Join-Path $dir 'diste') (Join-Path $RealRand 'diste') | Out-Null }
    if (-not (Test-Path -LiteralPath (Join-Path $dir 'diste\Vanilla'))) { throw "junction to diste failed in $dir" }
    New-Item -ItemType Directory -Force -Path (Join-Path $dir 'spoiler_logs') | Out-Null
    # point the shared randomize.ps1 functions at this copy, with its own settings map
    $RandomDir = $dir
    $RandSettingsMap = Join-Path $Rz ('settings_map_' + $k + '.txt')
    function Get-RandomizeOptions { return @{ Options = $Options; From = 'real randomizer options'; HasItem = ($Options -split '\s+' -contains 'item') } }
    Write-Host "seed_$k : randomizing (2-5 min)..."
    $ErrorActionPreference = 'Continue'      # enemypreset.py writes to stderr; not fatal
    $r = Invoke-RandomizeEnemies $GameExe
    $ErrorActionPreference = 'Stop'
    Write-Host ("seed_$k : " + $r.Ok + ' ' + $r.Msg)
}
