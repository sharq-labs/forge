# Checkpoint 2 correction attempt 1 — strict inventory blocker

2026-10-20. Status: BLOCKED_WITH_PRECISE_EVIDENCE. Checkpoint 2 is NOT accepted.
Production HEAD: `1cb5e187ef46ba2735fa292112a5e2bfd2334007`.

The independent review supersedes the prior linux-extension readiness claim and
its description of the synthetic baseline as complete. Prior artifacts and their
hashes are preserved, not rewritten. The prior 40 failed / 9 passed run remains
historical execution evidence, but is NOT evidence that all five review findings
were corrected. The original tests/probe are unchanged in this attempt.

## Bounded feasibility execution

Added only `tests/genesis_lite/test_genesis_lite_v0_3_readonly_inventory.py`.
This is a new test-only configuration of the existing pinned development image.
It adds `--read-only-tmpfs=false`,
`--security-opt=proc-opts=ro,nosuid,nodev,noexec`, and `--ipc=private`;
explicit private tmpfs mounts at /tmp, /var/tmp, /run and /dev/shm remain.
No privileged mode, added capabilities, device writes, canaries, installations,
image rebuilds or host security changes. The existing probe runs with
`write_canaries=false`; it reads the complete raw mountinfo inventory only plus
process/network-interface metadata. No host/venv write probes are configured.

Exact pytest command (cwd is the dedicated Linux checkout):

```sh
PYTHONPATH=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo/src:/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo TMPDIR=/tmp FORGE_CHECKPOINT_EVIDENCE=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/correction-evidence /home/dev_kaeem/venvs/forge312/bin/python -m pytest tests/genesis_lite/test_genesis_lite_v0_3_readonly_inventory.py -q -p no:cacheprovider --basetemp=/tmp/forge-cp2-correction-ro -rA --tb=short
```

Result: **1 failed, 0 passed, 0 errors/skips, exit 1, 0.33 s**.
The failed node is `test_strict_readonly_inventory` at the final remaining-mount
assertion, after successful create, inspect, start, JSON parsing and cleanup.
This is the expected failing-first strict-policy counterexample, not a runtime
unavailability or setup error. Unexpected setup failures are not converted to skips.
Full exact argv/environment/exit are in command-readonly.json; raw inventory,
inspection, stdout/stderr and cleanup are in readonly-runtime.json.

Per-mount ro controls view writeability; superblock rw on an ro bind is not
classified as writable. This configuration makes /proc and /dev ro, but still
leaves the following eight writable pseudo/device mounts:

| Mount ID | Target | Filesystem | Per-mount options |
|---|---|---|---|
| 576 | /dev/pts | devpts | rw,nosuid,noexec,relatime |
| 577 | /dev/mqueue | mqueue | rw,nosuid,nodev,noexec,relatime |
| 580 | /dev/null | devtmpfs | rw,nosuid,noexec,relatime |
| 581 | /dev/zero | devtmpfs | rw,nosuid,noexec,relatime |
| 582 | /dev/full | devtmpfs | rw,nosuid,noexec,relatime |
| 583 | /dev/tty | devtmpfs | rw,nosuid,noexec,relatime |
| 584 | /dev/random | devtmpfs | rw,nosuid,noexec,relatime |
| 585 | /dev/urandom | devtmpfs | rw,nosuid,noexec,relatime |

The complete raw inventory contains 36 rows. No writable pseudo/device
mount is exempted or touched. The strict assertion includes every rw mount
outside the four explicitly restored private tmpfs targets. Passing this narrow
assertion alone would not establish private propagation, topology reconciliation,
canary coverage or deployment acceptance. Actual inspected IPC mode is private.
Own created CID is cleaned in finally with rm --force --ignore; cleanup exit 0.

## Review disposition and stop

All five original MAJOR findings remain OPEN pending the review owner. The bounded
experiment addresses only the configuration feasibility question in finding 5;
it does not correct the old fixture or grant the old synthetic baseline validity.
The complete per-card schema, synchronized policy/mismatch mutations, topology and
open-fd attribution, per-mount A-write/B-absence, independent verifier restart, and
legacy-evidence labeling still require corrections. They are NOT RUN in corrected
form. The previous legacy REFUSED-string experiments are evidence-enforcement
regressions, not actual malicious-card production exploits. The wrong absent-image
experiment proves absent-image refusal only, not valid-image substitution.

Under the forwarded stop condition, further strict-runtime work is blocked on
review of these eight residual mounts: the permitted documented options did not
remove their writeability. This is NOT proof that all possible unprivileged
runtime configurations are impossible; broader runtime design has not been tried.
No pseudo/device exemption or changed scientific acceptance rule is proposed as
an implicit fix. Review should select whether to authorize a bounded runtime
redesign that removes the residual rw views, or explicitly decide policy; neither
choice has been made here. Checkpoint 3 remains NOT STARTED.

Production bytes under benchmarks/ and src/ are compared with HEAD in
production-preservation.json. The prior evidence tree is hashed in
prior-evidence-preservation.json. complete-tests.patch contains all current test
additions, including the old unaccepted tests; it must not be called a fully
corrected patch. correction-only.patch contains this attempt's single new test.
No commits, push, merge, freeze, formal root admission or formal campaign.
