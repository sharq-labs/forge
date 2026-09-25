#!/usr/bin/env bash
# Remove everything a previous job may have left in one runner instance's work directory.
#
#   reset-instance.sh /home/forge-runner/runners/N/_work
#
# Used (a) by the systemd drop-in before the runner starts -- so a crash, a reboot or a power
# cut can never hand the next job a half-finished workspace -- and (b) by the job-completed
# hook. It never touches _tool (the Python interpreters setup-python installs, kept for
# speed) and never the runner's own underscore-prefixed bookkeeping in _temp.
#
# It refuses any path that is not exactly a runner work directory, so a bad argument cannot
# turn it into a general delete.
set -euo pipefail

work="${1:?usage: reset-instance.sh <runner work dir>}"
case "$work" in
  /home/forge-runner/runners/*/_work) ;;
  *) echo "refusing to clean $work: not a forge runner work directory" >&2; exit 2 ;;
esac
[ -d "$work" ] || exit 0

# the checked-out repository (the workspace is _work/<repo>/<repo>)
find "$work" -mindepth 1 -maxdepth 1 -type d \
  ! -name '_*' -exec rm -rf -- {} +
# actions downloaded for a job: content-addressed by SHA in the workflow, but writable by
# the job that used them, so they are not reused across jobs
rm -rf -- "$work/_actions"
# job scratch: venvs, mutation trees, evidence files
if [ -d "$work/_temp" ]; then
  find "$work/_temp" -mindepth 1 -maxdepth 1 ! -name '_*' -exec rm -rf -- {} +
fi
