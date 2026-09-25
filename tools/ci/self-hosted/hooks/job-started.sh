#!/usr/bin/env bash
# Runner hook: ACTIONS_RUNNER_HOOK_JOB_STARTED.
#
# Installed as /opt/forge-runner/hooks/job-started.sh (root-owned) and pointed at by a
# root-owned systemd drop-in. It runs before any step of the job; a non-zero exit fails the
# job at "Set up job", so a refused job never executes a line of the workflow.
#
# WHAT THIS PROTECTS, HONESTLY: it stops jobs from FORKS and other unexpected events. It
# does not stop a job it has ADMITTED from changing the machine afterwards: an admitted job
# runs as the runner user, which owns the runner binaries and (through the docker group) is
# root-equivalent inside this distro. A hostile collaborator's job can therefore disable this
# hook for later jobs. That is why the fork-approval setting is a precondition and why the
# distro must be rebuilt after any suspicious job (docs/assurance/SELF_HOSTED_RUNNER.md).
#
# It only ADMITS. Cleanup is done when the service (re)starts and after each job, never
# here, because the runner has already prepared its directories by now.
set -euo pipefail

# A hermetic environment: nothing a previous job left in the search path, the interpreter's
# user site directory or PYTHONPATH can substitute for the tools below.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE PYTHONINSPECT LD_PRELOAD LD_LIBRARY_PATH BASH_ENV ENV

conf=/opt/forge-runner/guard.conf
log_dir=/var/log/forge-runner
# shellcheck disable=SC1090
. "$conf"

log() {
  printf '%s %s\n' "$(/usr/bin/date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$log_dir/hook.log" 2>/dev/null || true
}

# -I: isolated (ignores PYTHON* variables and the user site), -S: no site-packages, so a
# usercustomize.py or a planted package cannot run inside the guard.
if /usr/bin/python3 -I -S /opt/forge-runner/bin/runner_guard.py \
     --repository "$REPOSITORY" --workflows "$WORKFLOWS" 2> >(/usr/bin/tee -a "$log_dir/hook.log" >&2); then
  log "admitted run=${GITHUB_RUN_ID:-?} event=${GITHUB_EVENT_NAME:-?} workflow_ref=${GITHUB_WORKFLOW_REF:-?} actor=${GITHUB_ACTOR:-?}"
else
  log "REFUSED run=${GITHUB_RUN_ID:-?} event=${GITHUB_EVENT_NAME:-?} workflow_ref=${GITHUB_WORKFLOW_REF:-?} actor=${GITHUB_ACTOR:-?} repository=${GITHUB_REPOSITORY:-?}"
  echo "forge runner guard refused this job; see $log_dir/hook.log on the runner" >&2
  exit 1
fi
