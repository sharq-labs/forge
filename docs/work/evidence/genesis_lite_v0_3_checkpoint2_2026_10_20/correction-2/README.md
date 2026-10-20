# Checkpoint 2 corrected tests — review required

2026-10-20 (Africa/Cairo). Production HEAD `1cb5e187ef46ba2735fa292112a5e2bfd2334007`.
**BLOCKED_WITH_PRECISE_EVIDENCE. Checkpoint 3 NOT STARTED.**
Final targeted execution: **94 failed, 28 passed, zero errors/skips, exit 1, 2.76 s**.
This is a failing-first specification, not successful isolation or scientific validation.

## Supersession

This record supersedes the prior linux-extension readiness claim and the
correction-1 proposal to stop all independent corrections. Parent clarified that
safe test-method corrections remained authorized; they are now implemented and
executed below, pending review acceptance. All prior evidence remains intact.
No claim is made that the five MAJORs have been accepted/closed by the reviewer.

## Exact execution

Cwd: `/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo`.
Existing Python 3.12.3 venv and rootless Podman 4.9.3; immutable image unchanged.
No installations, host security changes, image rebuilds or additional runtime
configurations after the permitted read-only experiment.

```sh
PYTHONPATH=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo/src:/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo TMPDIR=/tmp FORGE_CHECKPOINT_EVIDENCE=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/correction-2-final5-evidence FORGE_CHECKPOINT_SOURCE_SHA=1cb5e187ef46ba2735fa292112a5e2bfd2334007 /home/dev_kaeem/venvs/forge312/bin/python -m pytest tests/genesis_lite/test_genesis_lite_v0_3_container_isolation.py tests/genesis_lite/test_genesis_lite_v0_3_container_runtime.py tests/genesis_lite/test_genesis_lite_v0_3_container_contract.py tests/genesis_lite/test_genesis_lite_v0_3_readonly_inventory.py -q -p no:cacheprovider --basetemp=/tmp/forge-cp2-correction-2-final5 -rA --tb=short
```

`command.json` preserves the same argv/environment/cwd and child exit code.
`pytest.txt` contains every failed/passed node. Runtime stdout/stderr, argv,
inspections, raw mountinfo, parsed rows, mount-attributed cryptographic canaries,
image identities and cleanup are in runtime.json and readonly-runtime.json.

| Failure group | Count | Interpretation |
|---|---:|---|
| Existing launcher/checker regressions | 17 | Includes explicit private IPC; synthetic pre-admission test only |
| Legacy interface evidence regressions / image binding | 3 | Two fabricated REFUSED-detail enforcement tests; one missing launcher image identity |
| Proposed validator contract | 73 | Explicit MISSING_VALIDATION_CONTRACT assertions, not independent exploit reproductions |
| Strict real runtime inventory | 1 | Eight remaining rw pseudo/device mounts |

28 controls pass: 4 existing isolation controls, 6 runtime/control/cleanup tests,
and 18 fixture/parser/open-fd controls. No collection/setup failure in final run.

## Five review findings: implemented corrections, acceptance pending

1. **Complete per-card contract baseline.** Three distinct complete A/B/C records
   each contain raw inventory, parsed parent/device/root/topology, runtime views,
   all four required writable tmpfs targets, complete argv/binds/environment,
   image and source/tool/code provenance, capability/NNP/network state, restart
   result and per-mount observations. ro view with rw superblock is accepted as
   read-only. Positive baseline and escaped read-only alias baseline require PASS;
   independent negatives prevent always-accept. Shared control binds distinct
   immutable A/B IDs, image digests, identical paths, token and fd mount IDs;
   missing/reused IDs, wrong paths/images have specific negative cases.
   This is hypothetical admissible evidence, not a claim this Podman rig can
   produce an admissible inventory. The actual rig is explicitly blocked.
2. **Evidence synchronization.** Windows/host/shared/source/venv unsafe cases
   synchronize raw rows, parsed rows, runtime rows and relevant argv. Separate
   raw/parsed/runtime omission/spoof cases require reconciliation rejection.
   Configuration-versus-observation mismatch has explicit argv-only tests.
   Fixture-control tests check synchronization independently of absent production.
3. **Parser/topology.** Decode escapes after tokenization; retain parent/device,
   roots, optional propagation, stacked and nested records. Tests cover malformed
   and duplicate raw rows, escaped spaces/tabs/backslashes, bind aliases,
   stacked obscured rw views and nested overmount attribution. Proposed-validator
   cases require acceptance/rejection too; helper success cannot satisfy them.
   Actual runtime declared-target matching rejects duplicate candidates rather
   than choosing the first. Canary opens use /proc/self/fdinfo mnt_id and compare
   directory/write/readback IDs; an obscured record remains blocking.
4. **Explicit canary accounting and restart contract.** Each eligible A mount
   receives a separate secrets.token_hex(32) token, O_EXCL write, fsync and readback;
   fresh B/C must report READ_ABSENT at the identical path/token, with actual mount
   attribution. READ_ERROR, UNKNOWN, NOT_PROBED, missing coverage, wrong mount/path/
   token, failed write/readback are separate validator mutations. Actual shared
   bind A-write/B-read control passes. Devices and pseudo-files receive no writes.
   Two fresh verifier subprocesses are specified for PASS and three BLOCKED
   cases. **Their executions are currently blocked at the explicit missing API
   assertion**; container restart refusal alone is not counted as verifier restart
   consistency. No production restart-consistency result is claimed.
5. **Truthful labels and lifecycle.** Old REFUSED-detail tests are explicitly
   legacy-interface evidence-enforcement regressions, not actual malicious-card
   production exploits. Wrong absent digest is labeled absent-image refusal,
   not valid-image substitution. Runtime inspect proves private IPC. Both runtime
   fixtures use unique per-run names/ownership labels; finally cleanup inspects
   the exact identity and validates ownership before removal, including when
   create timed out before returning a CID. Injected timeout output retention and
   refusal to remove an unowned identity pass. Unexpected setup/inspect failures
   propagate, not broad prerequisite skips. The final runtime transcript includes
   one clearly test-injected timeout record (partial stdout/stderr, owned-id), not
   a real timeout incident. Real timeout/race recovery under daemon failure has
   not been demonstrated; no claim extends beyond the bounded test.

## Remaining strict runtime blocker

Same authorized configuration: read-only-tmpfs=false, proc-opts=ro,nosuid,nodev,noexec,
explicit private IPC, four private tmpfs directories restored. /proc and /dev are
ro views. Full inventory has 36 rows; eight residual rw records remain:

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

No exemptions, no canary/device endpoint writes, no added capabilities or
privileged mode. These eight remain UNPROBEABLE/blocking in the real rig.
Future runtime redesign or explicit policy decision is required; neither is
implemented or silently selected. The permitted configuration experiment does
not prove every unprivileged design impossible.

## Scope, preservation and unsupported details

Only tests and docs changed. All 4,608 tracked benchmarks/ and src/ files compared
byte-for-byte with HEAD blobs using git cat-file --batch; zero differences.
production-preservation.json contains every SHA256. Windows and Linux production
Git diffs are empty. Existing divergent Linux checkout remains
f7df896836b62e7bc96f2eaee28883d655cb4e3a. Dirty Windows main was not changed.
Final podman ps -a listed no containers. Process census saw Claude desktop plus
one CLI process without this-worktree/Forge in its command line; this does not
prove another process's cwd or absence of all possible writers. No competing
source change was observed. No process was stopped.

No production validator, formal launcher integration, scientific acceptance,
formal attempts, certification, full regression pack, changed-file gate,
commits, push, merge or freeze. A valid alternative-image runtime experiment was
not performed. Environment subdirectory-specific canaries are not measured beyond
the enclosing private mount/path contract. Hostile kernel/race scenarios beyond
the bounded observations are untested. Test-only parser correctness is not
production parser implementation. Parent retains checkpoint review.

## Preserved intermediate runs

- interim1: 78 failed, 26 passed, 2.54 s, no errors/skips.
- interim2: 90 failed, 28 passed, 2.85 s, no errors/skips.
- interim3: 94 failed, 28 passed, 2.96 s, no errors/skips.
- collection-error: 1 collection error, 0.11 s; direct sibling test import was
  incompatible with pytest import mode. Corrected using file-specific importlib.
- final: 94 failed, 28 passed, 2.76 s, no errors/skips.

Each preserved subdirectory contains exact command.json and pytest transcript;
successful runtime runs retain observations too. Prior linux-extension evidence
hashes still match the correction-1 snapshot. No prior artifact was rewritten.

Complete current five-file test patch: `complete-tests.patch` (55+ KB; exact size
is recorded by filesystem). SHA256: `2cf3f5dc46fa5a353959ff1928f4987111f19fb6b05552095f5d2db2551ce81a`.
`test-sources.json` binds all final test sources; SHA256SUMS binds this package.
The patch is a review candidate, not an assertion that every MAJOR is closed.
