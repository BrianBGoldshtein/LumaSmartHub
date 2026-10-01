# Exercise the Windows armer against a temporary SUBST drive, never a real card.
$ErrorActionPreference = 'Stop'
$fixture = Join-Path ([System.IO.Path]::GetTempPath()) ('luma-v025-arm-' + [Guid]::NewGuid().ToString('N'))
$letter = @('Z', 'Y', 'X', 'W', 'V') | Where-Object { -not (Get-PSDrive -Name $_ -ErrorAction SilentlyContinue) } | Select-Object -First 1
if (-not $letter) { throw 'No unused temporary drive letter is available.' }
$created = $false
$mapped = $false
try {
    $null = New-Item -ItemType Directory -Path $fixture -ErrorAction Stop
    $created = $true
    & subst.exe "${letter}:" $fixture | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Temporary drive mapping failed.' }
    $mapped = $true
    $original = 'console=serial0,115200 root=PARTUUID=11111111-02 rootfstype=ext4 fsck.repair=yes rootwait' + "`n"
    [System.IO.File]::WriteAllText((Join-Path $fixture 'cmdline.txt'), $original, [System.Text.Encoding]::ASCII)
    [System.IO.File]::WriteAllText((Join-Path $fixture 'config.txt'), '[all]' + "`n", [System.Text.Encoding]::ASCII)
    [System.IO.File]::WriteAllText((Join-Path $fixture 'kernel8.img'), 'fixture only', [System.Text.Encoding]::ASCII)
    $sourceFolder = Join-Path $fixture 'source'
    $null = New-Item -ItemType Directory -Path $sourceFolder
    $dummyBundle = Join-Path $sourceFolder 'luma-update-0.2.5.lup'
    [System.IO.File]::WriteAllText($dummyBundle, 'not a signed bundle; Pi verification is separate', [System.Text.Encoding]::ASCII)
    function Get-Volume { param([string]$DriveLetter) [pscustomobject]@{ FileSystem = 'FAT32' } }
    $armer = Join-Path $PSScriptRoot 'arm-supervised-update.ps1'
    $wrongBundle = Join-Path $sourceFolder 'luma-update-0.2.4.lup'
    [System.IO.File]::WriteAllText($wrongBundle, 'wrong version', [System.Text.Encoding]::ASCII)
    $wrongAccepted = $false
    try { & $armer -BootDrive "${letter}:" -Bundle $wrongBundle | Out-Null; $wrongAccepted = $true } catch { }
    if ($wrongAccepted -or [System.IO.File]::ReadAllText((Join-Path $fixture 'cmdline.txt')) -ne $original) {
        throw 'A wrong-version bundle changed the boot card.'
    }
    & $armer -BootDrive "${letter}:" -Bundle $dummyBundle | Out-Null
    $backup = [System.IO.File]::ReadAllText((Join-Path $fixture 'cmdline.luma-v025-original.txt'), [System.Text.Encoding]::ASCII)
    if ($backup -ne $original) { throw 'Original boot command line was not preserved.' }
    $armed = [System.IO.File]::ReadAllText((Join-Path $fixture 'cmdline.txt'), [System.Text.Encoding]::ASCII)
    if ($armed -notmatch 'systemd\.run="/usr/bin/bash /boot/firmware/luma-v025-run.sh"') {
        throw 'One-shot boot command was not armed.'
    }
    $copiedHash = (Get-FileHash -LiteralPath (Join-Path $fixture 'luma-update-0.2.5.lup') -Algorithm SHA256).Hash.ToLowerInvariant()
    $recordedHash = [System.IO.File]::ReadAllText((Join-Path $fixture 'luma-v025-bundle.sha256')).Trim()
    if ($copiedHash -ne $recordedHash) { throw 'Bundle transfer hash was not recorded accurately.' }
    $rearmed = $false
    try { & $armer -BootDrive "${letter}:" -Bundle $dummyBundle | Out-Null; $rearmed = $true } catch { }
    if ($rearmed) { throw 'The armer accepted a second run against an already armed card.' }
    Write-Output '0.2.5 Windows BOOT arming fixture passed; no real card was touched.'
} finally {
    if ($mapped) { & subst.exe "${letter}:" /D | Out-Null }
    if ($created) {
        $resolved = [System.IO.Path]::GetFullPath($fixture)
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
            -not ([System.IO.Path]::GetFileName($resolved) -match '^luma-v025-arm-[0-9a-f]{32}$')) {
            throw 'Refusing to remove a fixture outside the temporary test scope.'
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
