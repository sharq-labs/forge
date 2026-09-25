#!/bin/sh
# Verify, on the running system, the isolation the self-hosted runner distro depends on:
#
#   1. no Windows drive is mounted       (judged from the kernel's mount table, not from directories)
#   2. Windows programs cannot be started (no enabled binfmt_misc handler for PE files, none on PATH)
#   3. systemd is PID 1
#   4. /etc/wsl.conf keeps all of the above across restarts
#
#   sh tools/ci/self-hosted/check-isolation.sh
#
# It is the single definition of "isolated" used by New-ForgeRunnerDistro.ps1 (which pipes it into
# the distro), install-host.sh and the self-hosted smoke workflow. POSIX sh; runs as root or as the
# unprivileged runner user.
#
# Fail-closed: every check must positively establish its property. Anything it cannot read or parse
# is a failure, never a pass. The last line is exactly "FORGE-ISOLATION: PASS" (exit 0) only when
# every check passed; otherwise it is "FORGE-ISOLATION: FAIL ..." (exit 1).
#
# Why not `test -d /mnt/c`: WSL creates /mnt/c the first time the distro starts with automount on
# (New-ForgeRunnerDistro.ps1 has to start it once to write wsl.conf), and the empty directory stays
# after automount is turned off. Directory existence therefore says nothing about whether C: is
# mounted; the mount table does.
#
# FORGE_ISOLATION_FIXTURE_ROOT (tests only): read proc/, run/, etc/ and mnt/ under that directory
# instead of the real ones. The output then says so on its first line, and the result describes the
# fixture, not this machine. Nothing in the setup sets it; install-host.sh and the smoke workflow
# unset it explicitly.
set -u

root="${FORGE_ISOLATION_FIXTURE_ROOT:-}"
if [ -n "$root" ]; then
  echo "NOTE: FIXTURE MODE ($root): this result describes a test tree, NOT this machine"
fi
mountinfo="$root/proc/self/mountinfo"
binfmt="$root/proc/sys/fs/binfmt_misc"
pid1_comm="$root/proc/1/comm"
systemd_dir="$root/run/systemd/system"
wsl_conf="$root/etc/wsl.conf"
mnt="$root/mnt"

problems=0
ok()   { echo "OK:   $*"; }
fail() { echo "FAIL: $*"; problems=$((problems + 1)); }
note() { echo "NOTE: $*"; }

for tool in awk grep head sed; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "FAIL: '$tool' is not available, so isolation cannot be checked"
    echo "FORGE-ISOLATION: FAIL (checker prerequisites missing)"
    exit 1
  fi
done

# ---- 1. Windows drives ------------------------------------------------------------------------------
# /proc/self/mountinfo is the kernel's own table (what findmnt and mountpoint read). A line is
#   id parent maj:min root MOUNT-POINT opts [optional...] - FSTYPE SOURCE SUPER-OPTS
# with space, tab, newline and backslash octal-escaped. A Windows drive in WSL2 appears as
#   ... /mnt/c ... - 9p C:\134 rw,...,aname=drvfs;path=C:\134;...
# (drvfs under WSL1; virtiofs when that experimental transport is on). /usr/lib/wsl/drivers is also 9p
# (aname=drivers: the read-only GPU driver store WSL always provides); it is not a drive and is not
# counted. Any mount at all on /mnt/<letter> is counted regardless of type.
# (procfs files report size 0, so emptiness is judged by what awk actually read, not by test -s.)
if [ ! -r "$mountinfo" ]; then
  fail "cannot read the mount table ($mountinfo): whether a Windows drive is mounted is unknown"
else
  drives="$(awk '
    function unescape(s) { gsub(/\\040/, " ", s); gsub(/\\011/, "\t", s); gsub(/\\012/, "\n", s); gsub(/\\134/, "\\", s); return s }
    {
      sep = 0
      for (i = 7; i <= NF; i++) if ($i == "-") { sep = i; break }
      if (sep == 0 || NF < sep + 2) { print "unparseable mount table line " NR ": " $0; bad = 1; next }
      mp = unescape($5); fstype = $(sep + 1); source = unescape($(sep + 2))
      opts = (NF >= sep + 3) ? $(sep + 3) : ""
      why = ""
      if (fstype == "drvfs") why = "drvfs mount"
      else if ((fstype == "9p" || fstype == "virtiofs") && (source ~ /^[A-Za-z]:/ || source ~ /^drvfs/ || opts ~ /path=[A-Za-z]:/)) why = fstype " mount of a Windows drive"
      else if (mp ~ /^\/mnt\/[A-Za-z]$/) why = "mount on a drive-letter mount point"
      if (why != "") print why ": " source " on " mp " (" fstype ")"
    }
    END { if (NR == 0) exit 4; exit bad ? 3 : 0 }' "$mountinfo")"
  status=$?
  if [ "$status" -eq 4 ]; then
    fail "the mount table ($mountinfo) is empty: whether a Windows drive is mounted is unknown"
  elif [ "$status" -eq 3 ]; then
    fail "the mount table has lines this check cannot parse, so whether a Windows drive is mounted is unknown:"
    printf '%s\n' "$drives" | sed 's/^/        /'
  elif [ "$status" -ne 0 ]; then
    fail "could not parse the mount table ($mountinfo, awk exit $status): whether a Windows drive is mounted is unknown"
  elif [ -n "$drives" ]; then
    fail "Windows drives are mounted in this distro (set [automount] enabled=false and mountFsTab=false in /etc/wsl.conf, then restart the distro):"
    printf '%s\n' "$drives" | sed 's/^/        /'
  else
    ok "no Windows drive in the mount table"
  fi
fi
# Second opinion from mountpoint(1) on the conventional drive-letter directories, and an explanation
# for a leftover directory, which is harmless and is exactly what the old directory test tripped on.
for d in "$mnt"/?; do
  [ -d "$d" ] || continue
  if command -v mountpoint >/dev/null 2>&1 && mountpoint -q "$d"; then
    fail "$d is a mount point (mountpoint(1))"
  else
    note "$d exists as a plain directory with nothing mounted on it (a leftover from an earlier start with automount on; not a Windows drive)"
  fi
done

# ---- 2. Windows interop -----------------------------------------------------------------------------
# WSL starts Windows programs through a binfmt_misc handler (WSLInterop, or WSLInterop-late when
# systemd re-registers it) that hands PE files ("MZ", magic 4d5a) to /init. With appendWindowsPath=false
# powershell.exe is never on PATH even when interop is ON, so a PATH lookup alone proves nothing; the
# handler table is what decides whether a Windows program can run.
if [ ! -r "$binfmt/status" ] && [ -z "$root" ] && [ "$(id -u)" = "0" ] && [ -d "$binfmt" ]; then
  # Not mounted yet (systemd normally automounts it on first access). Mounting it only makes the
  # kernel's existing handler table visible; it registers nothing.
  if mount -t binfmt_misc binfmt_misc "$binfmt" 2>/dev/null; then note "mounted binfmt_misc at $binfmt to inspect it"; fi
fi
if [ ! -r "$binfmt/status" ]; then
  fail "cannot read $binfmt/status: whether Windows programs can be started is unknown"
else
  live=""
  for f in "$binfmt"/*; do
    [ -f "$f" ] || continue
    name="${f##*/}"
    case "$name" in register|status) continue ;; esac
    if [ ! -r "$f" ]; then live="$live $name(unreadable)"; continue; fi
    [ "$(head -n 1 "$f")" = "enabled" ] || continue
    case "$name" in WSLInterop*) live="$live $name"; continue ;; esac
    if grep -q '^magic 4d5a' "$f" || grep -qx 'interpreter /init' "$f"; then live="$live $name"; fi
  done
  # An enabled handler fails even if binfmt_misc is globally disabled right now: root can re-enable
  # it with one write, and WSL never relies on that switch.
  binfmt_state="$(head -n 1 "$binfmt/status")"
  if [ -n "$live" ]; then
    fail "Windows interop is live: enabled binfmt_misc handler(s):$live (set [interop] enabled=false in /etc/wsl.conf, then restart the distro)"
  else
    ok "no enabled binfmt_misc handler can start a Windows program (binfmt_misc: $binfmt_state)"
  fi
fi
on_path=""
for exe in powershell.exe pwsh.exe cmd.exe wsl.exe explorer.exe; do
  if command -v "$exe" >/dev/null 2>&1; then on_path="$on_path $exe"; fi
done
if [ -n "$on_path" ]; then
  fail "Windows programs are on PATH:$on_path (set [interop] appendWindowsPath=false in /etc/wsl.conf)"
else
  ok "no Windows program on PATH"
fi

# ---- 3. systemd -------------------------------------------------------------------------------------
pid1=""
[ -r "$pid1_comm" ] && pid1="$(head -n 1 "$pid1_comm")"
if [ "$pid1" = "systemd" ] && [ -d "$systemd_dir" ]; then
  ok "systemd is PID 1"
  if [ -z "$root" ] && command -v systemctl >/dev/null 2>&1; then
    if command -v timeout >/dev/null 2>&1; then
      state="$(timeout 90 systemctl is-system-running --wait 2>/dev/null | head -n 1)"
    else
      state="$(systemctl is-system-running 2>/dev/null | head -n 1)"
    fi
    note "systemd state: ${state:-unknown} (informational; 'degraded' is common under WSL and is not an isolation failure)"
  fi
else
  fail "systemd is not running as PID 1 (PID 1 is '${pid1:-unreadable}'; set [boot] systemd=true in /etc/wsl.conf, then restart the distro)"
fi

# ---- 4. /etc/wsl.conf keeps it that way after a restart --------------------------------------------
# WSL reads wsl.conf at start, and a missing key means its default (drives and interop ON). Sections,
# keys and values must be spelled exactly as written by New-ForgeRunnerDistro.ps1.
if [ ! -r "$wsl_conf" ]; then
  fail "cannot read $wsl_conf: without it WSL mounts Windows drives and enables interop on the next start"
else
  conf="$(awk '
    { sub(/\r$/, ""); line = $0; sub(/^[ \t]+/, "", line); sub(/[ \t]+$/, "", line) }
    line == "" || line ~ /^[#;]/ { next }
    line ~ /^\[.*\]$/ { section = substr(line, 2, length(line) - 2); next }
    {
      eq = index(line, "="); if (eq == 0) next
      key = substr(line, 1, eq - 1); value = substr(line, eq + 1)
      sub(/[ \t]+$/, "", key); sub(/^[ \t]+/, "", value)
      seen[section "." key] = value
    }
    END {
      n = split("boot.systemd=true automount.enabled=false automount.mountFsTab=false interop.enabled=false interop.appendWindowsPath=false", want, " ")
      for (i = 1; i <= n; i++) {
        split(want[i], kv, "=")
        got = (kv[1] in seen) ? seen[kv[1]] : "<missing>"
        if (got != kv[2]) print kv[1] " is " got ", must be " kv[2]
      }
    }' "$wsl_conf")"
  status=$?
  if [ "$status" -ne 0 ]; then
    fail "could not parse $wsl_conf (awk exit $status)"
  elif [ -n "$conf" ]; then
    fail "$wsl_conf does not keep the distro isolated after a restart:"
    printf '%s\n' "$conf" | sed 's/^/        /'
  else
    ok "$wsl_conf: systemd=true, automount off (incl. fstab), interop off, Windows PATH not appended"
  fi
fi

if [ "$problems" -eq 0 ]; then
  echo "FORGE-ISOLATION: PASS"
  exit 0
fi
echo "FORGE-ISOLATION: FAIL ($problems problem(s))"
exit 1
