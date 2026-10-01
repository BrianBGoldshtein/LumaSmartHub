# One-shot 0.2.5 test update via the FAT BOOT partition of a powered-off Pi.
# The application settings and Google credentials live on the Linux partition;
# this tool does not read, format, or replace that partition.
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z]:$')]
    [string]$BootDrive,
    [Parameter(Mandatory = $true)]
    [string]$Bundle
)
$ErrorActionPreference = 'Stop'
$drive = $BootDrive.Substring(0, 1).ToUpperInvariant()
$volume = Get-Volume -DriveLetter $drive -ErrorAction Stop
if ($volume.FileSystem -notin @('FAT32', 'FAT')) {
    throw 'The selected drive is not a Pi FAT BOOT partition.'
}
$root = $drive + ':\'
$cmdline = Join-Path $root 'cmdline.txt'
$config = Join-Path $root 'config.txt'
$kernel = Join-Path $root 'kernel8.img'
$backup = Join-Path $root 'cmdline.luma-v025-original.txt'
$bundleTarget = Join-Path $root 'luma-update-0.2.5.lup'
$scriptSource = Join-Path $PSScriptRoot 'boot-supervised-update.sh'
$scriptTarget = Join-Path $root 'luma-v025-run.sh'
$cmdHashPath = Join-Path $root 'luma-v025-cmdline.sha256'
$bundleHashPath = Join-Path $root 'luma-v025-bundle.sha256'
$resultPath = Join-Path $root 'luma-v025-result.log'
foreach ($required in @($cmdline, $config, $kernel, $scriptSource, $Bundle)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required file missing: $required"
    }
}
if ((Split-Path -Leaf $Bundle) -ne 'luma-update-0.2.5.lup') {
    throw 'Choose the final luma-update-0.2.5.lup bundle, not a different version or draft.'
}
foreach ($target in @($backup, $bundleTarget, $scriptTarget, $cmdHashPath, $bundleHashPath, $resultPath)) {
    if (Test-Path -LiteralPath $target) {
        throw "The BOOT card already contains $target. Stop and inspect it before retrying."
    }
}
if ((Get-Item -LiteralPath $Bundle).Length -gt 26214400) {
    throw 'The update bundle is unexpectedly large.'
}
$original = [System.IO.File]::ReadAllText($cmdline, [System.Text.Encoding]::ASCII)
$oneLine = $original.TrimEnd("`r", "`n")
if ($oneLine -match '[\r\n]' -or $oneLine -match 'systemd\.run=' -or $oneLine.Length -lt 20) {
    throw 'Unexpected Pi boot command line; refusing to modify it.'
}
$bundleHash = (Get-FileHash -LiteralPath $Bundle -Algorithm SHA256).Hash.ToLowerInvariant()
Copy-Item -LiteralPath $Bundle -Destination $bundleTarget -ErrorAction Stop
if ((Get-FileHash -LiteralPath $bundleTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $bundleHash) {
    throw 'The bundle copy did not verify; the boot command line was not changed.'
}
Copy-Item -LiteralPath $scriptSource -Destination $scriptTarget -ErrorAction Stop
if ((Get-FileHash -LiteralPath $scriptTarget -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath $scriptSource -Algorithm SHA256).Hash) {
    throw 'The recovery script copy did not verify; the boot command line was not changed.'
}
Copy-Item -LiteralPath $cmdline -Destination $backup -ErrorAction Stop
$originalHash = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
if ($originalHash -ne (Get-FileHash -LiteralPath $cmdline -Algorithm SHA256).Hash.ToLowerInvariant()) {
    throw 'The boot command-line backup did not verify; the boot command line was not changed.'
}
[System.IO.File]::WriteAllText($cmdHashPath, $originalHash + "`n", [System.Text.Encoding]::ASCII)
[System.IO.File]::WriteAllText($bundleHashPath, $bundleHash + "`n", [System.Text.Encoding]::ASCII)
$extra = ' systemd.unit=graphical.target systemd.wants=kernel-command-line.service systemd.run_success_action=none systemd.run_failure_action=none systemd.run="/usr/bin/bash /boot/firmware/luma-v025-run.sh"'
$armed = $oneLine + $extra + "`n"
try {
    [System.IO.File]::WriteAllText($cmdline, $armed, [System.Text.Encoding]::ASCII)
    if ([System.IO.File]::ReadAllText($cmdline, [System.Text.Encoding]::ASCII) -ne $armed) {
        throw 'The armed boot command-line readback differed.'
    }
} catch {
    Copy-Item -LiteralPath $backup -Destination $cmdline -Force
    throw
}
Write-Output '0.2.5 supervised update armed. Safely eject the card, insert it in the powered-off Pi, then power on.'
Write-Output 'The Pi will restore its normal boot command line before verifying the signed bundle.'
Write-Output 'After boot, the result will be recorded on BOOT as luma-v025-result.log.'
