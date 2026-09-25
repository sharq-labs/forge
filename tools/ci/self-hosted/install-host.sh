#!/usr/bin/env bash
# One-time preparation of the dedicated WSL2 distro that hosts the runner instances.
#
#   sudo bash tools/ci/self-hosted/install-host.sh
#
# Run it as root INSIDE the dedicated distro (see docs/assurance/SELF_HOSTED_RUNNER.md, part 1),
# from a checkout of this repository. It is idempotent. It installs the system packages the
# heavy jobs need, creates the unprivileged runner user, and installs the admission guard and
# hooks root-owned and read-only to that user. It never registers a runner.
set -euo pipefail

if [ "$(id -u)" != "0" ]; then echo "run as root (inside the dedicated distro)" >&2; exit 1; fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/../../.." && pwd)"

REPOSITORY="${FORGE_REPOSITORY:-sharq-labs/forge}"
WORKFLOWS="${FORGE_ALLOWED_WORKFLOWS:-tests,recertify-hardened-core,trust-mutations,self-hosted-smoke}"
RUNNER_USER=forge-runner

# ---- refuse to run where the isolation assumptions do not hold ---------------------------------
if [ -d /mnt/c ] || ls /mnt/*/Windows >/dev/null 2>&1; then
  echo "Windows drives are mounted in this distro. Set [automount] enabled=false in /etc/wsl.conf," >&2
  echo "run 'wsl --shutdown' from Windows, and start again (docs part 1)." >&2
  exit 1
fi
if command -v powershell.exe >/dev/null 2>&1 || command -v cmd.exe >/dev/null 2>&1; then
  echo "Windows interop is enabled. Set [interop] enabled=false in /etc/wsl.conf (docs part 1)." >&2
  exit 1
fi
if ! [ -d /run/systemd/system ]; then
  echo "systemd is not running. Set [boot] systemd=true in /etc/wsl.conf and restart the distro." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# git/curl/jq/build tools: the runner and setup-python; ngspice: the scientific gate's provider;
# docker.io: the reproducibility image; python3: this guard and the hooks
apt-get install -y -qq \
  ca-certificates curl git jq build-essential unzip tar gzip \
  python3 python3-venv python3-pip \
  libicu-dev libssl-dev \
  ngspice docker.io
systemctl enable --now docker

# ---- the unprivileged user ---------------------------------------------------------------------
id "$RUNNER_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$RUNNER_USER"
# Docker access is root-equivalent INSIDE this distro (which cannot reach Windows), and is what
# the reproduce job needs. It is deliberately the only privilege the user gets: no sudo.
usermod -aG docker "$RUNNER_USER"
rm -f "/etc/sudoers.d/$RUNNER_USER"

# ---- guard, hooks, reset script: root-owned, not writable by the runner user --------------------
install -d -m 0755 -o root -g root /opt/forge-runner /opt/forge-runner/bin /opt/forge-runner/hooks
install -m 0755 -o root -g root "$repo_root/tools/ci/runner_guard.py"            /opt/forge-runner/bin/runner_guard.py
install -m 0755 -o root -g root "$here/bin/reset-instance.sh"                    /opt/forge-runner/bin/reset-instance.sh
install -m 0755 -o root -g root "$here/bin/maintenance.sh"                       /opt/forge-runner/bin/maintenance.sh
install -m 0755 -o root -g root "$here/hooks/job-started.sh"                     /opt/forge-runner/hooks/job-started.sh
install -m 0755 -o root -g root "$here/hooks/job-completed.sh"                   /opt/forge-runner/hooks/job-completed.sh
printf 'REPOSITORY=%q\nWORKFLOWS=%q\n' "$REPOSITORY" "$WORKFLOWS" > /opt/forge-runner/guard.conf
chown root:root /opt/forge-runner/guard.conf && chmod 0644 /opt/forge-runner/guard.conf

# ---- shared, owner-controlled state ------------------------------------------------------------
install -d -m 0755 -o "$RUNNER_USER" -g "$RUNNER_USER" /var/log/forge-runner /var/cache/forge-runner /var/cache/forge-runner/pip
install -d -m 0755 -o "$RUNNER_USER" -g "$RUNNER_USER" "/home/$RUNNER_USER/runners"

# ---- weekly maintenance (docker build cache age-out, pip cache size cap) ------------------------
install -m 0644 "$here/systemd/forge-runner-maintenance.service" /etc/systemd/system/forge-runner-maintenance.service
install -m 0644 "$here/systemd/forge-runner-maintenance.timer"   /etc/systemd/system/forge-runner-maintenance.timer
systemctl daemon-reload
systemctl enable --now forge-runner-maintenance.timer

echo "host ready: repository=$REPOSITORY workflows=$WORKFLOWS user=$RUNNER_USER"
echo "next: sudo bash $here/install-runner-instance.sh <N> <registration-token>"
