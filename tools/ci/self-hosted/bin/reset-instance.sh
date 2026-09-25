#!/usr/bin/env bash
# Remove what a previous job may have left in ONE runner instance.
#
#   reset-instance.sh /home/forge-runner/runners/N/_work
#
# Used (a) by the systemd drop-in before the runner starts, so a crash, reboot or power cut
# cannot hand the next job a half-finished workspace, and (b) by the job-completed hook.
#
# Each instance owns its own work directory, HOME (<instance>/_home) and TMPDIR
# (<instance>/_tmp), set by the root-owned drop-in, so this never touches another instance.
# What it removes: the checkout, downloaded actions, job scratch (venvs, mutation trees,
# evidence files), the instance's HOME and TMPDIR contents, and -- unless
# FORGE_KEEP_TOOLCACHE=1 -- the tool cache of Python interpreters (a job can write into it,
# and a poisoned interpreter would flavour every later job's evidence).
# What it cannot remove: the runner's own underscore-prefixed bookkeeping, the shared pip and
# Docker caches (documented residual risk), and a process that daemonised away from the
# workspace. It refuses any path that is not exactly a runner work directory.
set -euo pipefail

work="${1:?usage: reset-instance.sh <runner work dir>}"
# FORGE_RUNNERS_ROOT comes from root-owned configuration (the systemd drop-in); it exists so the
# script can be tested against a scratch tree.
root="${FORGE_RUNNERS_ROOT:-/home/forge-runner/runners}"
case "$work" in
  *..*|*//*) echo "refusing to clean $work: not a normalised path" >&2; exit 2 ;;
esac
instance="${work%/_work}"
case "$work" in
  "$root"/[0-9]*/_work) ;;
  *) echo "refusing to clean $work: not a forge runner work directory" >&2; exit 2 ;;
esac
case "${instance#"$root"/}" in
  ''|*/*|*[!0-9]*) echo "refusing to clean $work: not a numbered instance" >&2; exit 2 ;;
esac
[ -d "$work" ] || exit 0

# the checked-out repository (the workspace is _work/<repo>/<repo>) and any stray directory or file
find "$work" -mindepth 1 -maxdepth 1 ! -name '_*' -exec rm -rf -- {} +
# actions downloaded for a job: writable by the job that used them, so never reused across jobs
rm -rf -- "$work/_actions"
if [ "${FORGE_KEEP_TOOLCACHE:-0}" != "1" ]; then
  rm -rf -- "$work/_tool"
fi
# job scratch that is not the runner's own bookkeeping
if [ -d "$work/_temp" ]; then
  find "$work/_temp" -mindepth 1 -maxdepth 1 ! -name '_*' -exec rm -rf -- {} +
fi
# per-instance HOME and TMPDIR: dotfiles, user site-packages, git config, docker config, /tmp-style files
for extra in "$instance/_home" "$instance/_tmp"; do
  if [ -d "$extra" ]; then
    find "$extra" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  fi
done
