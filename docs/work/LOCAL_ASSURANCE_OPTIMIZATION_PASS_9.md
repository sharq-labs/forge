# Local Assurance optimization pass 9 — certification scope fix and V4 verification cost

HEAD: 8d5eed3f47a0490d481b7ff5c9927f2f944096db. Passes 2–9 uncommitted.
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN. No certificate generated.

## Part 1 — certification control registration

`tools/certification/core_certificate.py` (explicitly authorized):

- `tools/certification/mutation_startup.py` gained a CERTIFICATION_CONTROL_FILES reason
  (sealed Python/pytest startup, interpreter identity, forced plugin/bytecode policy and
  the Formal/V4 invocation flags).
- `tests/test_mutation_workspace.py` (already reasoned) joined the `certification_control`
  patterns as an exact path, following 4f3a7631's precedent for `tests/test_local_assurance.py`.

## Part 5 — state transition model of one V4 attempt (written BEFORE any change)

Measured on a V4-shaped tree (`mutation_v4_runner.populate`): 8,354 files, 88.8 MB,
including `.git`. S = full seed SHA-256 snapshot, W = full worker SHA-256 snapshot,
D = metadata-only worker walk. "Exposure" = a target child process exists; targets run
as the shard's uid, so they CAN chmod and write both seed and worker (seed read-only
modes stop accidents only — LOCAL_ASSURANCE.md: "not an operating-system sandbox").

| # | Transition | Pass | Bytes | Invariant established | Seed mutable? | Worker mutable? | Proven by another transition? | Class |
|---|---|---|---|---|---|---|---|---|
| P0 | seed construction | copy source→seed | 88.8 MB read | seed populated | shard only | n/a | — | REQUIRED |
| P1 | seed admission | S (PristineIndex.build) | 88.8 MB | authenticated immutable index | shard only | n/a | — | REQUIRED |
| P2 | seed admission | `_check_git_seed` | config/packed-refs | no external Git storage/helpers | shard only | n/a | — | REQUIRED |
| P3 | worker creation | copy seed→worker | 88.8 MB read | worker populated | shard only | shard only | — | REQUIRED |
| P5 | `__enter__` verify | S + W | 177.6 MB | seed modes/bytes and worker == index | no exposure yet | no exposure yet | A1/A2 of first attempt, nothing between | MERGEABLE (once per shard, ~0.9 s; not changed) |
| A1 | attempt start | S | 88.8 MB | seed == index before execution | no live target since A6 | — | previous A6 (no exposure in between) | REDUNDANT-IN-MODEL, **SPEC-PINNED** (`test_new_index_cannot_mask_seed_link_or_type_contamination[same-size-seed]`: refuse before the body runs) — RETAINED |
| A2 | attempt start | W | 88.8 MB | worker == index before execution | — | no live target since A9 | previous A9 (no exposure in between) | REDUNDANT-IN-MODEL, **SPEC-PINNED** (`test_contamination_before_attempt_invalidates_without_entering`) — RETAINED |
| A3 | mutation | read/write declared target | 1 file | declared edit applied | — | shard | — | REQUIRED |
| A4 | pytest | — | — | (exposure) | **yes (same uid)** | **yes** | — | — |
| A5 | drain | — | — | no live descendant | — | — | — | REQUIRED |
| A6 | restore start | S | 88.8 MB | seed == index after exposure, before any seed byte is used | exposure just ended | — | none: seed immutability is unprovable (same uid can chmod; `chattr +i` needs CAP_LINUX_IMMUTABLE) | REQUIRED |
| A7 | delta detection | D | 0 hashed | dirty set (created/deleted/metadata) | — | — | — | REQUIRED (cheap) |
| A8 | repair | dirty seed entries only, each digest-checked | dirty bytes | dirty paths restored from authenticated seed bytes | — | shard | — | already INCREMENTAL |
| A9 | final integrity | W | 88.8 MB | worker == index, incl. same-size hidden bytes | — | — | none: metadata cannot prove content (racy timestamps, mmap writes) | REQUIRED |
| A10 | conditional | sparse repair + S + W | only on hidden change | as above | — | — | — | REQUIRED when triggered |

Per attempt: 2 S + 2 W + 1 D. Every full pass is REQUIRED or SPEC-PINNED. Removing A1/A2
would change a declared property (refuse BEFORE execution) and is an owner decision, not
an optimization; it is not done here.

### Hypothesis of Part 7 (seed sealed after admission) — REJECTED

Seed immutability after admission cannot be proven in this environment: targets run as
the shard uid and may `chmod u+w` and write the seed (Pass 8 case E did exactly that);
no root-only immutability (`chattr +i`), separate uid or mount namespace is available;
the trust model is explicitly "not an operating-system sandbox". Per-entry checks at
restore would authenticate restoration bytes but would lose detection of a target that
wrote outside its worker. A6 keeps the full seed hash.

### Part 8 — worker hash

A9 cannot use dirty-path knowledge or metadata: Pass 8 case A2 (same-size, timestamp-restored
change in an undeclared file) is detected only by content. A Merkle structure would still
need either full content hashing or trusted metadata to find changed leaves — no benefit.
Full worker SHA retained.

### Where the time actually goes

| Pass on 88.8 MB / 8,354 files | Production | Floor: plain os.scandir (+ SHA-256 of all bytes) |
|---|---|---|
| full SHA snapshot (S/W) | 0.430 s | 0.082 s |
| metadata walk (D) | 0.273 s | 0.016 s |

cProfile: pathlib construction, `relative_to` and `as_posix` per entry dominate; SHA-256
`update` is ~0.04 s. The optimization is therefore implementation-only: the same passes,
the same SHA-256 over every byte, the same manifest — without per-entry pathlib work.

## Implementation (after the table)

`snapshot()` builds relative names as `prefix + DirEntry.name` and accumulates the three
structural counters locally (flushed in `finally`). Unchanged: root lstat refusal, fsencode
sort, lstat per entry, every regular file through `_digest` (full SHA-256, 1 MiB chunks),
Entry fields, symlink/special handling, final sorted dict. No pass was removed; no byte
cache; no metadata substitutes for content.

Equivalence (old Pass 2–8 function vs new, rows + manifest digest + telemetry counters):
real V4 tree (8,776 entries), real Formal tree (5,542), hostile tree (non-UTF-8 name,
backslash, unicode, file/dir/dangling symlinks, hardlink, FIFO, read-only dir, `.git`/
`.gitignore`/`.github`), both SHA and metadata modes: IDENTICAL. Error shapes for missing
root, root symlink and root file: IDENTICAL.

## Runtime results

- 182 Pass 2–7 specs: pass on 3.11 and 3.12. Targeted 12-module set: 442 passed, 2 failed
  (pre-existing certificate drift, also at a pristine HEAD clone).
- Pass 8 restoration probe (17 cases) re-run on the new code: identical outcomes.
- Like-for-like V4 micro-run (B56a B19j B11a B12a B29c + control, nothing else running):

| Measure | Before | After |
|---|---|---|
| total wall | 28.98 s | 18.40 s |
| median mutation attempt | 3.74 s | 2.15 s |
| seed verifications | 13 / 5.51 s | 13 / 2.13 s |
| seed bytes hashed | 1,243,236,132 | 1,243,241,872 |
| worker full hashes | 13 / 5.48 s | 13 / 2.09 s |
| worker bytes hashed | 1,154,149,139 | 1,154,154,469 |
| delta scans | 6 / 1.70 s | 6 / 0.26 s |
| restoration bytes | 306,290 | 306,290 |
| pytest-reported total | 12.19 s | 11.71 s |
| verdicts | 4 KILLED, 1 SURVIVED, control GREEN | identical |

The few-KB byte difference is the larger new mutation_workspace.py inside the copied seed.
Formal: semantics unchanged (shared snapshot is faster; Formal time is ~99% test execution).
No full-run extrapolation is claimed.

## Independent review

Independent read-only review (forge-scientific-reviewer) of the snapshot() rewrite and the
scope registration: PASS. LOW finding (no test pinned the equivalence claim) fixed with
test_string_path_snapshot_equals_the_pathlib_manifest_and_counters and
test_mid_walk_failure_still_reports_entries_already_scanned in tests/test_mutation_workspace.py
(pass on 3.11/3.12 and against the pre-Pass-9 implementation). LOW pre-existing finding recorded,
not changed: core_certificate.py OUT_OF_SCOPE prose still says "the two self-check modules".
Final targeted set: 444 passed, 2 failed (baseline certificate drift) in 29.97 s; new specs
184 passed on 3.11 (2.04 s).

OPTIMIZATION_PASS_9_READY
