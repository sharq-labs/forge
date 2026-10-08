# Local Assurance optimization pass 5 — static audit and contract

HEAD: 8d5eed3f47a0490d481b7ff5c9927f2f944096db. Passes 2–5 remain uncommitted.
Implementation and source-only review; no project imports, tests, mutation runs,
assurance, benchmarks, certification or performance measurements.

## Exact boundary — explicitly accepted by the user

Implemented controls cover declared mutation application, independently copied
worker/seed state, inherited passive Git inputs and runner-owned cleanup under a
controlled Linux interpreter/toolchain. Targets/providers and other same-UID
processes are trusted not to intentionally access unrelated filesystem paths or
change the parent's native process ownership state. The implementation is NOT
an OS-enforced filesystem sandbox. Absolute Python opens and explicit Git -C/
--git-dir/environment overrides can reach the real checkout or another shard;
this is a demonstrated capability, not an unlikely event or a proved exclusion.

The user explicitly selected: "Controlled targets and toolchain; seal inherited
inputs and runner-owned paths." Review is governed by that accepted contract.
Arbitrary-target isolation would require a separate OS boundary; no such guarantee
is claimed or silently introduced. No scientific/provider semantics are changed.

## One Git execution contract

For controlled invocations, Git discovers repositories from cwd within the owned
workspace: worker .git and test-created fixture repositories under owned artifact/
runtime directories. It reads copied working-tree/Git files and explicitly set
Git configuration. Inherited host redirects/configuration and default host Git
ignore/attributes cannot select outside inputs. It cannot inherit parent/shard
metadata, external alternates, templates, hooks or replacement history through
admitted initial state. Explicit overrides issued by target code are outside this
boundary, as is intentional absolute filesystem access.

Executable sealing lives in mutation_workspace.py: _check_git_seed and
mutation_environment. There is no second Git policy implementation in the runners.

| Input | Classification and reason |
| --- | --- |
| GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE, GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES, GIT_COMMON_DIR | neutralized: strip inherited GIT_*; repository identity uses natural cwd discovery |
| GIT_CONFIG_SYSTEM, GIT_CONFIG_GLOBAL | neutralized then explicitly /dev/null |
| GIT_CONFIG_NOSYSTEM | explicitly 1 |
| GIT_CONFIG_COUNT, GIT_CONFIG_KEY_*, GIT_CONFIG_VALUE_* | neutralized; controlled count 3 sets hooksPath, excludesFile and attributesFile to /dev/null |
| GIT_TEMPLATE_DIR | neutralized; explicitly owned empty per-target template directory |
| GIT_CEILING_DIRECTORIES | neutralized then owned workspace parent ceiling; nested fixture repos remain discoverable |
| GIT_DISCOVERY_ACROSS_FILESYSTEM | neutralized then 0; no accidental upward/cross-mount search |
| other inherited GIT_* (trace, replace-base, helpers, namespaces etc.) | neutralized uniformly; no existing source contract requires inherited Git-specific overrides |
| HOME, XDG_CONFIG_HOME | deliberately inherited for non-Git scientific/runtime configuration; Git global config and default ignore/attributes are overridden, hooks/templates are controlled |
| include.path, includeIf.* | refused; case-normalized sections and canonical grammar admission |
| core.worktree, core.hooksPath, fsmonitor, attributesFile, excludesFile, sshCommand, pager | refused in seed config; no initial external pointer/helper |
| extensions.worktreeConfig, unknown format extensions, non-sha1 objectFormat | refused; only supported sha1 objectFormat admitted, mixed-case sections included |
| partialClone, remote.*.promisor, objects/pack/*.promisor | refused; git show must not lazily fetch missing objects from an external repository |
| objects/info/alternates, http-alternates, commondir, gitdir indirection, worktree config/admin state | refused; .git must be an independent actual directory, seed symlinks/hardlinks refused |
| replace refs, packed replace refs, info/grafts | refused; historical identity must not be rewritten |
| shallow history | allowed as copied state; required commit/ancestor closure still must resolve or guards fail, never synthesized/fetched |
| submodules | baseline .gitmodules or .git/modules refused; no submodule initialization/update is part of the required Git closure |
| HEAD, refs, index, packed refs, ordinary remote URLs | allowed as copied/manifest-bound state; URLs do not authorize fetching and promisor behavior is refused |
| Git executable, installed toolchain, explicit fixture overrides | deliberately trusted execution inputs; sealing is not privilege isolation |

Minimum required closure includes current/source commits, manifest-pinned V1/V2
baseline commits and blobs, historical assurance commit and its measured parent,
ancestor graph for merge-base, history reachable for git log and arbitrary pinned
git show commit:path reads. Source consumers include core_freeze_v4.py
(descends_from, historical assurance problems, stored frozen snapshots) and
core_freeze/v2/v3 certificate helpers; fixtures additionally init/add/commit/checkout
private repositories. Refs/HEAD and loose/packed objects supply these reads; tags
may resolve symbolic revisions. Hooks and reflogs have no established requirement
for these reads, and worktree external metadata is refused. Full .git is retained
because no authenticated closure exporter/pruner has established a smaller exact
closure. No alternates, hardlinks or cross-shard Git sharing are introduced.

## Temporary ownership and deletion table

An in-memory OwnedRoot token is minted only from mkdtemp creation and records
root/ancestor device+inode identities and real-directory status. It is checked
before cleanup; a caller-supplied marker/name alone grants no deletion authority.
Path checks assume no concurrent hostile same-UID renames; they are not OS access
control. Artifact root identity is also checked before use.

| Path | Creator / owner / lifetime / cleanup and failure boundary |
| --- | --- |
| caller scratch container | CLI/caller; never recursively deleted by a shard; existing caller basetemp/JUnit untouched |
| forge-<shard>-* parent + tree | local_assurance OwnedRoot; one child shard; removed only on normal child completion with no retained workspace; every abnormal path retains entire parent, including constructor/stream/signal/hard-kill failures |
| workspace-* home | PersistentWorkspace OwnedRoot; one shard; contains seed, worker and owned artifacts; after proven quiescence unlock seed dirs and remove only original root; substitution/uncertain drain retains/refuses |
| seed | populated once into fresh absent destination; shard-owned read-only byte source; never executed; complete identity failure poisons before repair |
| worker | independent initial copy; one shard; sparse repair after drain; no normal full rebuild; links/type replacement checked without writing through linked targets |
| artifacts/junit, artifacts/basetemp, artifacts/pt/bt | workspace creates artifact root; every target validates active workspace and root identity before pytest clearing/report use; root is inside owned home and outside worker manifest; cleanup with home after drain |
| runtime-* and git-template | run_captured OwnedRoot; one target; TMPDIR/TMP/TEMP and empty Git templates; remove only after confirmed drain and original-root identity checks; uncertainty retains with home |
| performance destination + exclusive sibling temp | telemetry binds real parent chain, writes exclusive temporary inode and atomically replaces destination; cannot write through a linked target; substituted parent makes diagnostics unavailable; temp cleanup never follows substituted parents |
| official ids/log/record/gate paths | fixed per-shard evidence layout of fresh source run; no temporary cleanup; parent waits for all shards and refuses on any failure |
| prior source assurance directory with --reuse | caller-selected previous state; never recursively deleted; moved into newly owned unique quarantine sibling and excluded from new run admission; no gate/evidence reuse |

The old Formal population helper's deletion of arbitrary preexisting destination
was removed. V4 population also requires fresh absent destination. Private target
helpers require active workspace/artifacts, not arbitrary pytest basetemp paths.
Source assurance --reuse keeps old bytes in quarantine rather than guessing old
ownership from a directory name. Retention and quarantine require explicit later
operator cleanup; this pass does not delete them.

## Process model and concurrency

Retain dedicated Linux main-thread + kernel-single-thread, default/unblocked
SIGCHLD, no preexisting children/subreaper and process-local execution lock.
Recheck reaper/thread/signal state before each drain enumeration and at final
empty-tree proof, including installed subreaper identity. Direct children are
only the current frontier, not proof of the whole tree: killing/reaping that
frontier repeatedly adopts orphan grandchildren, detached/double-forked processes
and nested descendant subreapers. Exec does not change ancestry. Pipes held by
descendants cause communicate timeout and mandatory drain. Wait/signal/reaper
errors retain and refuse; restoration begins only after proven empty ownership.

No numeric process-group kill after leader reaping remains. Parent stream failure
requests cooperative shard SIGTERM, waits for its drain, then kills the direct
Popen if necessary; every such parent failure retains scratch. Shard target
sessions differ from shard PGID, so parent group membership was never proof of
nested ownership. Popen constructor failure still enters shard drain when setup
active; abrupt process death leaves retained scratch and cannot yield SOURCE_PASS.
SIGINT during restore may poison/invalidate; hard kill can leave owned roots.
Pidfds are not added: direct-child zombie/PID ownership is sufficient under the
no-competing-reaper contract and does not grant descendant-tree ownership by
itself. Native malicious reapers, PID-namespace tricks or external writers are
outside the controlled-process boundary and not certified away.

Default mutation-workers stays 2. Formal 4-job and V4 8-job groups run sequentially;
max active shards is min(default 2, group size). Each gate name has separate ids,
log, record, clean proof, telemetry and mkdtemp root. Duplicate job IDs are refused
before submission; duplicate CLI V4 mutation IDs refuse. Closures capture index/
name by value. No chdir or os.environ mutation; child env dictionaries are private.
Signal handlers belong to dedicated child main threads, not parent pool threads.
Tracker shared maps use a lock. Executor waits for all jobs before aggregated
failure; failed required shard cannot proceed to SOURCE_PASS/build_assurance.
No cached verdict, resume, population/default/expectation/attribution changes.

## Copies, scans and reads after Pass 5

Let B be the selected complete baseline bytes (G Git bytes included for V4;
Formal G=0), E entries,
R bytes of files actually restored, C bytes of same-sized independent dirty
candidates read to authenticate whether a rewrite is necessary, A artifact bytes,
T temporary target bytes and U extra worker files. Values are structural symbols,
not measured sizes/times. Five snapshots are MANIFEST SCANS, not five tree copies.

| Snapshot | Purpose / tree / mutability / lifetime / bytes copied / why distinct |
| --- | --- |
| pre-attempt seed | full seed metadata+SHA; immutable by contract but writable same UID; seed lives shard, scan map temporary; includes .git only when selected (V4); copies 0; catches seed changes since prior boundary |
| pre-attempt worker | full worker metadata+SHA; mutable independent tree; map temporary; includes .git only when selected (V4); copies 0; catches inter-attempt contamination before any next target |
| pre-repair seed | full seed metadata+SHA after target/drain; seed shard lifetime; map temporary; includes .git only when selected (V4); copies 0; target could change seed despite modes, so pre-attempt check cannot authenticate this transition |
| worker delta | structural full worker walk; mutable tree; map retained through sparse repair; includes .git only when selected (V4); copies 0, reads file contents 0; detects extras/deletions/types/link counts/modes independent of declared hints |
| post-repair worker | full worker metadata+SHA; map temporary; includes .git only when selected (V4); copies 0; hashes resulting bytes including unrelated same-size changes and repair effects; pre-attempt/delta scans cannot establish post-target/post-repair identity |

Physical complete copies: before 2, after 2 per shard (seed population from source,
worker copy from seed); zero per mutation. .git copies: 2 independent per V4 shard; Formal _COPIED excludes .git, so
Formal has zero Git copies and G=0.
No physical snapshot copy removed; all five scans retained because no authenticated
immutable seed lifetime or worker transition proves them redundant. Original source
checkout is not a mutable mutation workspace copy.

| Hash pass | Reads / when / invariant / detected failure |
| --- | --- |
| seed pre-attempt | B; before target; full seed metadata/content index identity; stale/corrupt/missing/extra seed |
| worker pre-attempt | B; before target; clean mutation starting state; contaminated bytes/types/modes/links |
| seed pre-repair | B; after target drain and before any repair; target did not invalidate byte source; seed tampering despite read-only modes |
| dirty candidate | C; before sparse file rewrite; SHA proves clean content and allows mode-only fix/no rewrite; same-size target byte corruption cannot hide behind metadata |
| restored seed file | R; one streamed read/hash during copy; bytes actually supplied match digest; corrupt seed stream cannot authorize reuse |
| worker post-repair | B; after repair; complete byte/structure identity; hidden unrelated same-size changes or failed repair |

Normal full seed reads 2B, worker reads 2B plus C, restore reads R. First index
hash and initial seed/worker verify are once per shard (three manifest scans).
Hidden unrelated content repair reuses its already-authenticated worker SHA, so
no redundant candidate read; adds its seed restore bytes plus full seed/worker
verification pair. No seed file reopening just for pre-copy hashing; restored
seed file is read once while writing, with digest checked before reuse. No fsync
was added; durability is not assurance proof. Clean hinted files and byte-clean
mode-only files are no longer recopied. Hardlinked candidates are always replaced
rather than chmod'd through a shared inode. Redundant indexed files/directories
name tuples and obsolete local signal/tempfile imports were removed; legacy
require_an_isolated_tree remains because mutation B55d targets its exact guard.

Persistent shard disk roughly 2B + artifact/extra data; peak 2B + A + T + U plus
filesystem metadata. At default two active shards, sum these per-shard quantities
for at most two distinct roots; retained failed shards and quarantined old runs
add persistent storage outside that active bound. Artifact/target output sizes
are not bounded by this patch. Index/manifests O(E), stream buffers O(1 MiB),
directory listings O(E), diagnostics O(lifecycle events), captured stdout/stderr
O(output bytes). Total RAM is not claimed constant or measured. No runtime
percentage or speedup claim follows from these structural quantities.

## Telemetry authority and review status

Choose semantics A: diagnostic failure is ignorable and grants no PASS. Timing,
counters, failure context and archive data are never read for verdict/restore/gate
admission. Official manifest scans only evidence/; diagnostics are siblings.
Certificate binds imported helper SOURCE code, not its nondeterministic data.
Both authority flags remain false; no diagnostic value can issue SAFE_TO_PUSH.
Atomic replacement and owned parent checks also prevent linked diagnostic writes
from mutating unrelated bytes under the controlled no-concurrent-writer contract.

New/updated source-only specifications cover clean candidate skip, owned artifact
roots, preexisting user files, root substitution, linked diagnostics, unsafe Git
partial clones/extensions, discovery ceiling, abnormal retention, reaper changes,
duplicate shard IDs and quarantine preservation. All tests NOT RUN.
Initial independent final review found a BLOCKER only under literal arbitrary-
target OS isolation. The user then explicitly accepted the controlled-runtime
contract; that scope blocker is resolved by the user's decision, not by an OS
sandbox implementation. Controlled-input production findings were corrected.
Cost-model P2 corrected: Formal selects no .git, V4 has two independent copies.
Final independent reviewer disposition under the accepted contract: PASS. No
demonstrated controlled-path defect remains. This is static review only, not
executed verification or OS-sandbox certification.
