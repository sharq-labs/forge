#!/usr/bin/env bash
# Install and register ONE runner instance as a systemd service.
#
#   sudo bash tools/ci/self-hosted/install-runner-instance.sh <N> <registration-token>
#
# <N> is a small integer (1, 2, ...): each instance runs one job at a time, so N instances
# run N heavy jobs in parallel. The registration token is short-lived (about an hour); create
# it in the repository's Settings > Actions > Runners > New self-hosted runner, or with
# `gh api -X POST repos/OWNER/REPO/actions/runners/registration-token --jq .token`.
# Run install-host.sh once first.
set -euo pipefail

if [ "$(id -u)" != "0" ]; then echo "run as root" >&2; exit 1; fi
index="${1:?usage: install-runner-instance.sh <N> <registration-token>}"
token="${2:?usage: install-runner-instance.sh <N> <registration-token>}"
case "$index" in ''|*[!0-9]*) echo "N must be a positive integer" >&2; exit 1;; esac

REPOSITORY="${FORGE_REPOSITORY:-sharq-labs/forge}"
# Pinned initial download. Verify RUNNER_SHA256 against the release page before trusting it:
# https://github.com/actions/runner/releases/tag/v${RUNNER_VERSION}. The runner updates itself.
RUNNER_VERSION="${RUNNER_VERSION:-2.337.0}"
RUNNER_SHA256="${RUNNER_SHA256:-70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613}"
RUNNER_USER=forge-runner
name="forge-pc-${index}"
dir="/home/${RUNNER_USER}/runners/${index}"
work="${dir}/_work"

[ -x /opt/forge-runner/hooks/job-started.sh ] || { echo "run install-host.sh first" >&2; exit 1; }
if [ -e "$dir/.runner" ]; then echo "instance $index is already configured at $dir" >&2; exit 1; fi

install -d -o "$RUNNER_USER" -g "$RUNNER_USER" "$dir" "$dir/_home" "$dir/_tmp"
tarball="/tmp/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
curl -fsSL -o "$tarball" \
  "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
echo "${RUNNER_SHA256}  ${tarball}" | sha256sum -c -
runuser -u "$RUNNER_USER" -- tar -xzf "$tarball" -C "$dir"
rm -f "$tarball"
"$dir/bin/installdependencies.sh" >/dev/null

# The labels the workflows target are [self-hosted, linux, x64, forge-pc]; the first three are added
# by the runner itself.
runuser -u "$RUNNER_USER" -- "$dir/config.sh" --unattended --replace \
  --url "https://github.com/${REPOSITORY}" --token "$token" \
  --name "$name" --labels forge-pc --work _work

# ---- service, with the guard wired in by root-owned configuration --------------------------------
( cd "$dir" && ./svc.sh install "$RUNNER_USER" )
unit="$(cd "$dir" && cat .service)"
install -d -m 0755 "/etc/systemd/system/${unit}.d"
cat > "/etc/systemd/system/${unit}.d/forge.conf" <<EOF
# Root-owned configuration for the runner service. It keeps the hook wiring out of the runner
# directory's own .env. Be clear about what that buys: it is NOT tamper-proof against a job the
# guard admitted, because that job runs as ${RUNNER_USER}, owns the runner binaries and (docker
# group) is root-equivalent inside this distro. It protects against accidents and against forks
# the guard refuses; a hostile collaborator's job is handled by rebuilding the distro.
[Service]
# each instance has its own HOME and TMPDIR so cleaning one can never disturb another
Environment=HOME=${dir}/_home
Environment=TMPDIR=${dir}/_tmp
Environment=ACTIONS_RUNNER_HOOK_JOB_STARTED=/opt/forge-runner/hooks/job-started.sh
Environment=ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/opt/forge-runner/hooks/job-completed.sh
Environment=FORGE_RUNNER_WORK=${work}
Environment=PIP_CACHE_DIR=/var/cache/forge-runner/pip
Environment=PIP_DISABLE_PIP_VERSION_CHECK=1
Environment=CRAFTY_NGSPICE_ARGV=ngspice
Environment=LANG=C.UTF-8
# every (re)start begins from an empty workspace: crash, reboot or power loss cannot leak state
ExecStartPre=/opt/forge-runner/bin/reset-instance.sh ${work}
EOF
systemctl daemon-reload
systemctl enable "$unit"
systemctl restart "$unit"
sleep 2
systemctl --no-pager --lines=5 status "$unit" || true
echo "instance ${index} (${name}) installed as ${unit}"
