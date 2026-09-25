#!/usr/bin/env bash
# Weekly housekeeping for the runner host (systemd timer). Reclaims disk; touches no
# result and no job that is running.
#
# * Docker build cache older than 7 days, and images nothing uses. Recent layers stay, so the
#   reproducibility image still builds incrementally. `docker build --pull` in the workflow
#   refreshes the pinned base tag on every run.
# * pip's cache: anything not read in 30 days.
set -uo pipefail

if command -v docker >/dev/null 2>&1; then
  docker builder prune -f --filter "until=168h" >/dev/null 2>&1 || true
  docker image prune -af --filter "until=168h" >/dev/null 2>&1 || true
fi
find /var/cache/forge-runner/pip -type f -atime +30 -delete 2>/dev/null || true
find /var/cache/forge-runner/pip -type d -empty -delete 2>/dev/null || true
echo "maintenance done: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
df -h / | tail -1
