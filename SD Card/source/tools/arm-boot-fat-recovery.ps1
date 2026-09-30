# Run only against the FAT BOOT partition of the powered-off Pi's microSD.
# This does not format the card, access ext4, or read Luma's private settings.
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z]:$')]
    [string]$BootDrive,
    [string]$Bundle
)
$ErrorActionPreference = 'Stop'
if (-not $Bundle) {
    $Bundle = Join-Path $PSScriptRoot 'luma-update-0.2.2.lup'
}
$drive = $BootDrive.Substring(0, 1).ToUpperInvariant()
$volume = Get-Volume -DriveLetter $drive -ErrorAction Stop
if ($volume.FileSystem -notin @('FAT32', 'FAT')) {
    throw 'Selected drive is not the Pi FAT BOOT partition.'
}
$root = $drive + ':\'
$cmdline = Join-Path $root 'cmdline.txt'
$config = Join-Path $root 'config.txt'
$kernel = Join-Path $root 'kernel8.img'
$backup = Join-Path $root 'cmdline.luma-r14-original.txt'
$scriptSource = Join-Path $PSScriptRoot 'boot-fat-recovery.sh'
$bundleTarget = Join-Path $root 'luma-update-0.2.2.lup'
foreach ($required in @($cmdline, $config, $kernel, $scriptSource, $Bundle)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required file missing: $required"
    }
}
if (Test-Path -LiteralPath $backup) {
    throw 'This card already has an r14 recovery backup. Stop and inspect it before retrying.'
}
if ((Get-Item -LiteralPath $Bundle).Length -gt 26214400) {
    throw 'Bundle is unexpectedly large.'
}
$original = [System.IO.File]::ReadAllText($cmdline, [System.Text.Encoding]::ASCII)
$oneLine = $original.TrimEnd("`r", "`n")
if ($oneLine -match '[\r\n]' -or $oneLine -match 'systemd\.run=' -or $oneLine.Length -lt 20) {
    throw 'Unexpected Pi boot command line; refusing to modify it.'
}
$bundleHash = (Get-FileHash -LiteralPath $Bundle -Algorithm SHA256).Hash.ToLowerInvariant()
Copy-Item -LiteralPath $Bundle -Destination $bundleTarget -ErrorAction Stop
if ((Get-FileHash -LiteralPath $bundleTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $bundleHash) {
    throw 'Bundle copy did not verify; boot command line was not changed.'
}
Copy-Item -LiteralPath $scriptSource -Destination (Join-Path $root 'luma-r14-recover.sh') -ErrorAction Stop
Copy-Item -LiteralPath $cmdline -Destination $backup -ErrorAction Stop
$originalHash = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
if ($originalHash -ne (Get-FileHash -LiteralPath $cmdline -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'Boot command-line backup did not verify; boot command line was not changed.'
}
[System.IO.File]::WriteAllText((Join-Path $root 'luma-r14-cmdline.sha256'), $originalHash + "`n", [System.Text.Encoding]::ASCII)
[System.IO.File]::WriteAllText((Join-Path $root 'luma-r14-bundle.sha256'), $bundleHash + "`n", [System.Text.Encoding]::ASCII)
$extra = ' systemd.unit=graphical.target systemd.wants=kernel-command-line.service systemd.run_success_action=none systemd.run_failure_action=none systemd.run="/usr/bin/bash /boot/firmware/luma-r14-recover.sh"'
$armed = $oneLine + $extra + "`n"
try {
    [System.IO.File]::WriteAllText($cmdline, $armed, [System.Text.Encoding]::ASCII)
    if ([System.IO.File]::ReadAllText($cmdline, [System.Text.Encoding]::ASCII) -ne $armed) {
        throw 'Boot command line readback differed.'
    }
} catch {
    Copy-Item -LiteralPath $backup -Destination $cmdline -Force
    throw
}
Write-Output 'Recovery armed. Safely eject the SD card, insert it in the powered-off Pi, then power on.'
Write-Output 'The Pi will restore its original boot command line before verifying and installing the signed update.'
