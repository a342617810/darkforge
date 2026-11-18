# 联机码压缩（用户 2026-11-17「可以编码一下联机码吗」→「不要按照默认的做 信息要完整只是某种方式压缩一下」）：launcher.ps1 和 gui.ps1 共用。
# DR3 整段原文（launcher.ps1 Get-CoopCode3）→ 词表里的词换成一个字节（0x80 起；表里没有的照原样，完全无损）→ deflate → base64url，前面加「DR4z」。
# 566 个字符的码压到 190 个字符左右；解开就是原来那一整段。只压全是 ASCII 的 DR3（别的照原样返回）。
# 词表只能往后加（解码靠下标）；要改已有的词就换一个模式字母（DR4z → DR4y），旧码按旧表解。前面的长词要排在它包含的短词前面
$CoopCodeWords = @(
    'DR3', '|v=', '|m=rand', '|m=plain', '|pw=', '|w=low', '|w=high', '|sc=', '|em=', '|bp=', '|ps=', '|nat=', '|o=',
    'allow_summons=', 'boss_damage_scaling=', 'boss_health_scaling=', 'boss_posture_scaling=', 'death_debuffs=',
    'enemy_damage_scaling=', 'enemy_health_scaling=', 'enemy_posture_scaling=',
    'allmaps', 'bossbgm', 'changestats', 'crashfix', 'customenemy', 'dlcblessing', 'dlckeysilo', 'earlylegacy', 'editnames',
    'markareas', 'mats', 'norandom_health', 'norandom_scadu', 'norandom_upgrades', 'norandom', 'phasehp', 'raceloc_health',
    'raceloc_scadu', 'spellshops', 'weaponprogression', 'scale', 'enemy', ' dlc', ' v16', 'bias:', 'seed:', 'item'
)
$CoopCodeLatin1 = [System.Text.Encoding]::GetEncoding(28591)

# DR3 → DR4z（不是 DR3、或者有非 ASCII 的字符：照原样返回）
function Compress-CoopCode([string]$Text) {
    if (-not $Text.StartsWith('DR3|') -or $Text -match '[^\x20-\x7E]') { return $Text }
    $t = $Text
    for ($i = 0; $i -lt $CoopCodeWords.Count; $i++) { $t = $t.Replace($CoopCodeWords[$i], [string][char](0x80 + $i)) }
    $bytes = $CoopCodeLatin1.GetBytes($t)
    $ms = New-Object System.IO.MemoryStream
    $ds = New-Object System.IO.Compression.DeflateStream($ms, [System.IO.Compression.CompressionMode]::Compress)
    $ds.Write($bytes, 0, $bytes.Length)
    $ds.Close()
    return 'DR4z' + [Convert]::ToBase64String($ms.ToArray()).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

# DR4z → DR3 原文（聊天软件折了行、加了空格也行）；不是 DR4 照原样返回；解不开返回空串
function Expand-CoopCode([string]$Text) {
    $t = ([string]$Text -replace '\s+', '')
    if (-not $t.StartsWith('DR4')) { return $Text }
    if (-not $t.StartsWith('DR4z')) { return '' }
    try {
        $s = $t.Substring(4).Replace('-', '+').Replace('_', '/')
        $s += '=' * ((4 - $s.Length % 4) % 4)
        $in = New-Object System.IO.MemoryStream(, [Convert]::FromBase64String($s))
        $ds = New-Object System.IO.Compression.DeflateStream($in, [System.IO.Compression.CompressionMode]::Decompress)
        $out = New-Object System.IO.MemoryStream
        $ds.CopyTo($out)
        $ds.Close()
        $sb = New-Object System.Text.StringBuilder
        foreach ($ch in $CoopCodeLatin1.GetString($out.ToArray()).ToCharArray()) {
            $k = [int]$ch - 0x80
            if ($k -lt 0) { [void]$sb.Append($ch) }
            elseif ($k -lt $CoopCodeWords.Count) { [void]$sb.Append($CoopCodeWords[$k]) }
            else { return '' }
        }
        $r = $sb.ToString()
        if (-not $r.StartsWith('DR3|')) { return '' }
        return $r
    } catch { return '' }
}
