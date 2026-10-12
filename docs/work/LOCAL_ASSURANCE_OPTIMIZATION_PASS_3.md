> Historical design record. Passes 5–6 and LOCAL_ASSURANCE.md define the current contract.
> Formal has no copied .git; V4 has sealed copied .git. The current index stores entries and digest, not cached bytes or redundant name tuples.

# Local Assurance optimization pass 3 — historical static design record

Pass 4 supersedes the byte-cache and repeated-seed-hash design below. See the
current cost model at the end and LOCAL_ASSURANCE_OPTIMIZATION_PASS_4.md.
Historical counts describe the Pass 3 source, not current execution results.

Scope: implementation and static review only at source HEAD
8d5eed3f47a0490d481b7ff5c9927f2f944096db. No project code, tests,
assurance, timing experiments or certification were executed. No measured
performance conclusion follows from the operation counts below.

## Static cost model

Let E be all entries, F regular files, D directories, B total file bytes in a
shard baseline, and C dirty entries including affected ancestors. Counts cover
the ordinary attempt with one successful repair, excluding target execution
and its own filesystem activity. Population exclusions are unchanged.

| Operation per ordinary attempt | Pass 2 | Pass 3 |
| --- | --- | --- |
| Complete manifest/structural snapshots | 6: seed 3, worker 3 | 5: seed 2, worker 3 |
| Regular-file SHA-256 calls | 6F | 2F worker; zero seed rehashes |
| Complete seed byte reads | 3B | 2B, compared with immutable indexed bytes |
| Complete worker byte reads | 3B | 2B, both cryptographic |
| Snapshot metadata calls | 6 root lstat + 6E child stat (excluding roots) | 5 root lstat + 5E child stat (excluding roots) |
| Snapshot scandir calls | 6D | 5D |
| Repair data movement | changed-file seed reads plus worker writes | C file writes from indexed bytes, no disk seed copying |
| Whole-worker population/rebuild | none | none |
| .git processing | included in all seed/worker snapshots | included in both seed identity checks, both worker hash scans and metadata scan |
| Cleanup traversal | zero per attempt; shard exit removes two trees | zero per attempt; shard exit unlocks seed directories and removes two trees |

E above denotes entries excluding the root for child-stat counts; D includes
root. Sparse repair also performs per-affected-path lstat/mode operations and
ancestor checks, bounded by dirty paths and their depth, rather than a second
full structural scan. In-memory comparisons remain O(E). If unrelated byte
changes escape structural detection, one additional sparse repair adds one
complete seed byte comparison and one complete worker cryptographic snapshot.

At shard initialization, population occurs once, index construction reads and
hashes seed files once, worker copy occurs once, and initial verification reads
seed and hashes worker once. Index plus verification is three full snapshots;
copy/population traversal depends on the unchanged runner population selection.
Seed protection chmod visits every indexed entry once. Exit unlocks seed
directories without following symlinks before recursive removal. External JUnit,
basetemp and shard-parent cleanup costs are unchanged, outside attempt counts.

Pass 2 repeatedly computed seed hashes and scanned worker hashes before sparse
repair. Pass 3 removes that duplicate cryptographic work without substituting
metadata for byte identity. It does not eliminate O(B) boundary verification.

## Index, dirty hints and verification

Frozen Entry records and read-only mappings retain modes, types, size, link
counts, SHA-256 and immutable bytes. Deterministic sorted serialization gives
one index identity per shard. Seed read-only permissions discourage accidental
writes; full byte comparison and complete structural comparison establish its
identity on every boundary. Unexpected seed changes invalidate the round.

Declared mutation paths are hints. An independent no-follow metadata snapshot
identifies created, deleted, replaced and metadata-changed entries. Sparse
repair uses cached bytes and only affected directory ancestors. Every worker
file is then hashed, including unrelated files with restored timestamps and
matching sizes. Hidden content changes are repaired once, then complete
verification repeats. Structural repair failure poisons the workspace and
cannot authorize another attempt. No normal whole-worker rebuild is used.

## Git decision

Keep .git as independent seed and worker copies. Alternates, shared objects or
worktree common directories expose another writable filesystem path to the
same UID. Read-only modes can be reversed by that UID and do not establish an
immutable store. Existing external-storage/config pointers are refused. There
is no shared Git area, hardlinked administrative state or mutation verdict cache.

## Descendant ownership and diagnostics

The dedicated Linux shard main thread exclusively owns child creation and
reaping. Before launch it refuses unrelated children, installs subreaper state,
and obtains direct children from all /proc task child lists. Detached orphan
children are adopted; repeated kill/reap enumerations drain them. PID ownership
relies on no competing reaper: unreaped direct children cannot have reused PIDs.
No process-group kill risks a reused group ID. Constructor failure after spawning
also enters the drain path. Timeout/interrupt/drain failure invalidates the round;
unproven quiescence skips repair and retains isolated storage. A repeated SIGTERM
is ignored during drain. Hard termination can leave scratch and never authorizes
reuse. This is a controlled-process trust boundary, not a hostile OS sandbox.

Telemetry records lifecycle events and category/path/context failures separately
from official evidence, with certification_authority=false and
safe_to_push_authority=false. Timers separate population, indexing, worker init,
application, subprocess, drain, delta detection, repair, full cryptographic
verification, seed identity, control and cleanup. No timings were collected.

## Test specifications and limits

Source-only tests cover immutable index reuse, zero repeated seed digest calls,
dirty target repair, unrelated same-size/restored-mtime corruption, mode changes,
symlinks, directories, hardlinks, nested extras, deletion, seed tampering,
poisoned refusal, shard isolation, uncertain drain retention, constructor failure
and diagnostic authority/lifecycle context. TESTS_RUN: 0.

Memory grows by approximately B cached bytes plus index overhead per concurrent
shard, including .git. No memory or runtime value was measured. Same-UID external
writers and unrelated reapers violate the dedicated-process assumptions; byte
checks prove equality at boundaries, not continuous immutability. Source review
cannot establish operating-system behavior or compatibility by execution.

Recommended pass 4: continue static review of bounded-memory immutable storage,
Git sealing and process ownership assumptions; retain full byte verification.
Execute adversarial and integration tests only after explicit authorization
changes the current execution prohibition, then measure before claiming speedup.


## Pass 4 static cost-model update — current source

The index now retains O(E) metadata/digests, not B content bytes. There is no byte
cache. Hashing/restoration streams use 1 MiB chunks; per-file content buffering is
bounded independently of total B. Config admission is capped at 1 MiB characters,
and packed-ref lines at 1 MiB characters. Metadata manifests and serialization
still allocate O(E); this is bounded content buffering, not constant total RAM.

Normal attempt still has five complete snapshots: pre-attempt seed + worker,
pre-repair seed, worker structural delta scan, post-repair worker SHA scan.
Two full seed hash passes replace Pass 3's two full indexed-byte comparisons;
two full worker SHA passes remain. Each restored file adds one streamed seed read
and hash, plus worker write; only dirty files are physically restored. The complete
seed check now precedes every worker repair, so corrupted/missing seed entries
cannot permit restoration to start. Hidden unrelated byte changes add one repair
of their seed files and one complete seed/worker verification pair.

No full worker rebuild occurs normally. .git remains independently duplicated
per shard, included in all structural/cryptographic scans. Shard initialization
still has index + seed/worker verification (three snapshots), one population and
one worker copy. Cleanup still unlocks seed directories and removes owned trees
once per shard. Per target, an external owned runtime directory is created for
TMPDIR and empty Git templates, then removed only after confirmed drain. An
uncertain target retains that directory with the workspace. These counts exclude
target-internal work and parent-level JUnit/basetemp cleanup. No seconds,
percentages, memory measurements or speedup claims were produced.


## Pass 5 terminology and cost update

Five snapshots are manifest/metadata scans, not physical complete copies. Two
independent trees per shard remain: seed + worker, .git included. Pass 5 retains
all full seed/worker hash passes. It adds selected worker candidate hashes to
avoid rewriting unchanged hints and byte-clean mode-only entries; hidden-file
repair reuses an already authenticated SHA. Normal reads: seed 2B + restored R,
worker 2B + candidate C. No unbounded content cache or fsync added. Full copy/
scan/hash/footprint proof tables are in LOCAL_ASSURANCE_OPTIMIZATION_PASS_5.md.
