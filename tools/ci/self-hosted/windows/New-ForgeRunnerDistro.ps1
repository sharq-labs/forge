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

  Verification runs tools/ci/self-hosted/check-isolation.sh inside the distro, after a restart, and
  fails closed: the script must exit 0 AND print 'FORGE-ISOLATION: PASS'. It judges Windows drives by
  the kernel's mount table (a leftover, empty /mnt/c directory is not a mounted drive), interop by the
  binfmt_misc handler table (not by whether powershell.exe is on PATH), and systemd by PID 1.

.PARAMETER UseExisting
  Do not import anything: validate the distro named -DistroName that already exists. Its
  /etc/wsl.conf is rewritten only if it differs from the one this script writes; the distro is then
  terminated (this stops its runner services, if any) so that the verification sees a fresh start
  under that wsl.conf. Use it to resume after a failed verification, and to re-check the distro at
  any time. -RootFs and -InstallDir do not apply.

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

.EXAMPLE
  .\New-ForgeRunnerDistro.ps1 -UseExisting -RegisterAutostart
  Validate (and, if needed, re-configure) the existing 'forge-runner' distro without re-importing it.
#>
[CmdletBinding(DefaultParameterSetName = 'Create')]
param(
  [Parameter(Mandatory = $true, ParameterSetName = 'Create')][string]$RootFs,
  [Parameter(ParameterSetName = 'Create')][string]$InstallDir = 'D:\WSL\forge-runner',
  [Parameter(Mandatory = $true, ParameterSetName = 'Existing')][switch]$UseExisting,
  [string]$DistroName = 'forge-runner',
  [switch]$RegisterAutostart
)

$ErrorActionPreference = 'Stop'
$env:WSL_UTF8 = '1'   # newer wsl.exe then writes UTF-8 instead of UTF-16 to a pipe

$checkScript = Join-Path (Split-Path -Parent $PSScriptRoot) 'check-isolation.sh'
if (-not (Test-Path -LiteralPath $checkScript -PathType Leaf)) { throw "isolation check script not found: $checkScript" }
if ($null -eq (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { throw 'wsl.exe is not available; enable WSL first.' }

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
$wslConf = ($wslConf -replace "`r`n", "`n") + "`n"

function Get-WslDistro([switch]$Running) {
  $arguments = @('--list', '--quiet')
  if ($Running) { $arguments += '--running' }
  # older wsl.exe writes UTF-16 to a pipe; drop the NULs before comparing names
  $names = ((& wsl.exe @arguments) -join "`n") -replace "`0", ''
  return @($names -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Invoke-InDistro([string]$Script) {
  # The script travels as base64 in one argument: no stdin encoding, CRLF or quoting can alter a byte.
  $bytes = [System.Text.Encoding]::UTF8.GetBytes(($Script -replace "`r`n", "`n"))
  $b64 = [Convert]::ToBase64String($bytes)
  $boot = 'f=/run/forge-setup.$$; printf %s $1 | base64 -d > $f && /bin/sh $f; rc=$?; rm -f $f; exit $rc'
  # Windows PowerShell 5.1 turns a native command's stderr into a terminating error under 'Stop';
  # collect it as text instead, and decide from the exit code and the output.
  $ErrorActionPreference = 'Continue'
  $output = & wsl.exe -d $DistroName -u root --exec /bin/sh -c $boot forge-setup $b64 2>&1
  return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Lines = @($output | ForEach-Object { "$_" }) }
}

function Stop-Distro {
  & wsl.exe --terminate $DistroName | Out-Null
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-WslDistro -Running) -contains $DistroName) {
    if ((Get-Date) -gt $deadline) { throw "'$DistroName' is still running 30 s after 'wsl --terminate'; not verifying a distro that has not restarted" }
    Start-Sleep -Milliseconds 500
  }
}

function Set-WslConf {
  $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($wslConf))
  $result = Invoke-InDistro "printf %s '$b64' | base64 -d > /etc/wsl.conf.forge-new && mv -f /etc/wsl.conf.forge-new /etc/wsl.conf"
  if ($result.ExitCode -ne 0) { $result.Lines | Write-Host; throw 'could not write /etc/wsl.conf' }
}

if ($PSCmdlet.ParameterSetName -eq 'Create') {
  if (-not (Test-Path -LiteralPath $RootFs -PathType Leaf)) { throw "RootFs not found: $RootFs" }
  if ((Get-WslDistro) -contains $DistroName) {
    throw "A WSL distro named '$DistroName' already exists. To validate it, run this script with -UseExisting. To start over, remove it deliberately with: wsl --unregister $DistroName"
  }
  if (Test-Path -LiteralPath $InstallDir) {
    if (Get-ChildItem -LiteralPath $InstallDir -Force | Select-Object -First 1) { throw "$InstallDir is not empty" }
  } else {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
  }

  Write-Host "Importing $RootFs as '$DistroName' into $InstallDir ..."
  & wsl.exe --import $DistroName $InstallDir $RootFs --version 2
  if ($LASTEXITCODE -ne 0) { throw "wsl --import failed ($LASTEXITCODE)" }
  # This first start happens BEFORE wsl.conf exists, so WSL mounts the drives and creates /mnt/c
  # once. The directory stays after automount is off; the verification below knows that.
  Set-WslConf
  Write-Host 'Wrote /etc/wsl.conf.'
} else {
  if (-not ((Get-WslDistro) -contains $DistroName)) { throw "No WSL distro named '$DistroName' exists; create it without -UseExisting." }
  Write-Host "Validating the existing distro '$DistroName' (nothing is imported) ..."
  $current = Invoke-InDistro 'cat /etc/wsl.conf 2>/dev/null; exit 0'
  $currentText = (($current.Lines -join "`n") -replace "`r", '').TrimEnd()
  if ($currentText -ne $wslConf.TrimEnd()) {
    Write-Host '/etc/wsl.conf differs from the required configuration; rewriting it.'
    Set-WslConf
  } else {
    Write-Host '/etc/wsl.conf already has the required configuration.'
  }
}

# wsl.conf is read when the distro starts. Terminate only this distro (a full 'wsl --shutdown' would
# also stop your other distros and Docker Desktop), and verify what the next start actually produces.
Stop-Distro

Write-Host ''
Write-Host "Verifying isolation inside '$DistroName' (fresh start) ..."
$check = Invoke-InDistro ([System.IO.File]::ReadAllText($checkScript))
$check.Lines | ForEach-Object { Write-Host "  $_" }
$verdict = @($check.Lines | Where-Object { $_.Trim() }) | Select-Object -Last 1
if ($check.ExitCode -ne 0 -or $null -eq $verdict -or $verdict.Trim() -ne 'FORGE-ISOLATION: PASS') {
  $failed = @($check.Lines | Where-Object { $_ -like 'FAIL:*' }) -join '; '
  if (-not $failed) { $failed = "no PASS verdict from the check (exit $($check.ExitCode))" }
  throw "isolation check failed: $failed"
}
Write-Host 'Isolation verified.'

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
