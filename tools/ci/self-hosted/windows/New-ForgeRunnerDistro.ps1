<#
.SYNOPSIS
  Create the dedicated, isolated WSL2 distro that hosts the Forge CI runner instances.

.DESCRIPTION
  Imports a fresh Ubuntu root filesystem as its own distro (NOT your personal Ubuntu, and not
  Docker Desktop's), then writes /etc/wsl.conf inside it so that

    * Windows drives are NOT mounted   ([automount] enabled=false)
    * Windows programs cannot be run   ([interop] enabled=false, appendWindowsPath=false)
    * systemd runs                     ([boot] systemd=true)

  A job that runs in this distro therefore cannot read or write any file on C: or D:, and
  cannot start a Windows process. That, plus a non-root user with no sudo, is what limits the
  damage a bad job can do to your PC. It does not make untrusted code safe to run.

  It does not modify your existing distros or your global .wslconfig (it prints the settings
  it recommends). It never registers a runner.

.PARAMETER RootFs
  Path to an Ubuntu 24.04 WSL root filesystem tarball, e.g.
  ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz from https://cloud-images.ubuntu.com/wsl/noble/current/
  (verify its checksum against SHA256SUMS on that page).

.PARAMETER InstallDir
  Where the distro's virtual disk lives. Put it on a drive with room: each parallel mutation
  shard copies about 75 MB per mutation, and Docker layers live here too. Default D:\WSL\forge-runner.

.PARAMETER RegisterAutostart
  Also register a per-user scheduled task that keeps the distro running from logon, so the
  runner services are up whenever you are logged in.

.EXAMPLE
  .\New-ForgeRunnerDistro.ps1 -RootFs D:\Downloads\ubuntu-noble-wsl-amd64-wsl.rootfs.tar.gz -RegisterAutostart
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$RootFs,
  [string]$InstallDir = 'D:\WSL\forge-runner',
  [string]$DistroName = 'forge-runner',
  [switch]$RegisterAutostart
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $RootFs -PathType Leaf)) { throw "RootFs not found: $RootFs" }
if ((Get-Command wsl.exe -ErrorAction SilentlyContinue) -eq $null) { throw 'wsl.exe is not available; enable WSL first.' }

# wsl.exe writes UTF-16 to a pipe; normalise before comparing names.
$existing = (& wsl.exe --list --quiet) -join "`n" -replace "`0", ''
if ($existing -split "`r?`n" | Where-Object { $_.Trim() -eq $DistroName }) {
  throw "A WSL distro named '$DistroName' already exists. Choose another -DistroName, or remove it deliberately with: wsl --unregister $DistroName"
}
if (Test-Path -LiteralPath $InstallDir) {
  if (Get-ChildItem -LiteralPath $InstallDir -Force | Select-Object -First 1) { throw "$InstallDir is not empty" }
} else {
  New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

Write-Host "Importing $RootFs as '$DistroName' into $InstallDir ..."
& wsl.exe --import $DistroName $InstallDir $RootFs --version 2
if ($LASTEXITCODE -ne 0) { throw "wsl --import failed ($LASTEXITCODE)" }

$wslConf = @"
[boot]
systemd=true

[automount]
enabled=false
mountFsTab=false

[interop]
enabled=false
appendWindowsPath=false

[user]
default=root
"@
# LF line endings, written from inside the distro
($wslConf -replace "`r`n", "`n") | & wsl.exe -d $DistroName -u root -- tee /etc/wsl.conf | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'could not write /etc/wsl.conf' }

# Apply wsl.conf: it is read when the distro starts. Terminate only this distro (a full
# 'wsl --shutdown' would also stop your other distros and Docker Desktop).
& wsl.exe --terminate $DistroName | Out-Null

Write-Host ''
Write-Host "Verifying isolation inside '$DistroName' ..."
& wsl.exe -d $DistroName -u root -- sh -c 'test ! -d /mnt/c && echo "OK: no Windows drives" || { echo "FAIL: /mnt/c is mounted"; exit 1; }'
if ($LASTEXITCODE -ne 0) { throw 'isolation check failed: Windows drives are mounted' }
& wsl.exe -d $DistroName -u root -- sh -c 'command -v powershell.exe >/dev/null 2>&1 && { echo "FAIL: interop enabled"; exit 1; } || echo "OK: no Windows interop"'
if ($LASTEXITCODE -ne 0) { throw 'isolation check failed: Windows interop is enabled' }
& wsl.exe -d $DistroName -u root -- sh -c 'systemctl is-system-running --wait 2>/dev/null | head -1'

$wslConfigPath = Join-Path $env:USERPROFILE '.wslconfig'
Write-Host ''
Write-Host "Recommended settings for $wslConfigPath (NOT applied automatically: this file is global to every WSL2 distro):"
Write-Host @'
  [wsl2]
  memory=24GB        # this PC has ~32 GB; leave the rest to Windows
  processors=20      # of 24 logical processors
  swap=8GB
  [experimental]
  autoMemoryReclaim=gradual
'@
Write-Host "Apply with 'wsl --shutdown' when nothing else important is running in WSL."

if ($RegisterAutostart) {
  $action = New-ScheduledTaskAction -Execute 'wsl.exe' -Argument "-d $DistroName -u root --exec /bin/sleep infinity"
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
  Register-ScheduledTask -TaskName 'ForgeRunnerWSL' -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Keeps the Forge CI runner distro (and its runner services) running while this user is logged in.' -Force | Out-Null
  Write-Host "Registered scheduled task 'ForgeRunnerWSL' (runs at logon as $env:USERNAME)."
}

Write-Host ''
Write-Host "Done. Next, inside the distro: wsl -d $DistroName   (then part 2 of docs/assurance/SELF_HOSTED_RUNNER.md)"
