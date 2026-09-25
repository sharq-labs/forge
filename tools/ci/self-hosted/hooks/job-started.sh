#!/usr/bin/env bash
# Runner hook: ACTIONS_RUNNER_HOOK_JOB_STARTED.
#
# Installed as /opt/forge-runner/hooks/job-started.sh, owned by root and read-only to
# the runner user, and pointed at by the root-owned systemd drop-in -- never by a file the
# runner user can edit. It runs before any step of the job. A non-zero exit fails the job
# at "Set up job", so a refused job never executes a line of the workflow.
#
# It only ADMITS. Cleanup is done when the service (re)starts and after each job, never
# here, because the runner has already prepared its directories by now.
set -euo pipefail

conf=/opt/forge-runner/guard.conf
log_dir=/var/log/forge-runner
# shellcheck disable=SC1090
. "$conf"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$log_dir/hook.log" 2>/dev/null || true
}

if python3 /opt/forge-runner/bin/runner_guard.py \
     --repository "$REPOSITORY" --workflows "$WORKFLOWS" 2> >(tee -a "$log_dir/hook.log" >&2); then
  log "admitted run=${GITHUB_RUN_ID:-?} event=${GITHUB_EVENT_NAME:-?} workflow_ref=${GITHUB_WORKFLOW_REF:-?} actor=${GITHUB_ACTOR:-?}"
else
  log "REFUSED run=${GITHUB_RUN_ID:-?} event=${GITHUB_EVENT_NAME:-?} workflow_ref=${GITHUB_WORKFLOW_REF:-?} actor=${GITHUB_ACTOR:-?} repository=${GITHUB_REPOSITORY:-?}"
  echo "forge runner guard refused this job; see $log_dir/hook.log on the runner" >&2
  exit 1
fi
