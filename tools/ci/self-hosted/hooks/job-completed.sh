#!/usr/bin/env bash
# Runner hook: ACTIONS_RUNNER_HOOK_JOB_COMPLETED. Runs after every job, pass or fail.
#
# Installed root-owned beside job-started.sh. Best effort by design: it must never turn a
# finished job's result into a failure, and the service-start reset is the backstop for
# anything it misses (a killed runner runs no hook at all).
set -uo pipefail

work="${FORGE_RUNNER_WORK:-}"

# stray processes of the finished job (a test that daemonised, a solver that was left running)
# are identified by a working directory inside this instance's workspace
if [ -n "$work" ] && [ -d "$work" ]; then
  for cwd in /proc/[0-9]*/cwd; do
    pid="${cwd#/proc/}"; pid="${pid%/cwd}"
    [ "$pid" = "$$" ] || [ "$pid" = "$PPID" ] && continue
    target="$(readlink "$cwd" 2>/dev/null || true)"
    case "$target" in
      "$work"/*) kill -9 "$pid" 2>/dev/null || true ;;
    esac
  done
fi

/opt/forge-runner/bin/reset-instance.sh "$work" || true

# containers that finished more than an hour ago and images nothing refers to; running
# containers (another instance's job) and the layer cache are left alone
if command -v docker >/dev/null 2>&1; then
  docker container prune -f --filter "until=1h" >/dev/null 2>&1 || true
  docker image prune -f >/dev/null 2>&1 || true
fi
exit 0
