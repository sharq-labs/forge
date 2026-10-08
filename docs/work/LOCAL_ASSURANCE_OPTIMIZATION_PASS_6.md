# Local Assurance optimization pass 6 — static integration audit

Source: 8d5eed3f47a0490d481b7ff5c9927f2f944096db. Passes 2–6 uncommitted.
Controlled repository targets and controlled toolchain; inherited inputs and
runner-owned paths are sealed. There is no same-UID hostile-code OS sandbox.
TESTS_RUN: 0. ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.

## Dependency and ownership map

Local Assurance -> repository invocation lock -> source identity/clean gate ->
canonical mutation_population shard selection -> bounded shard scheduler ->
Formal/V4 runner -> PersistentWorkspace -> OwnedRoot seed/worker/artifacts ->
attempt verification -> mutation application -> run_captured admission ->
fresh pytest subprocess -> descendant drain -> sparse restore -> complete SHA
verification -> runner transcript/JUnit attribution -> population record ->
clean record -> exact evidence manifest -> hardening_assurance -> certificate ->
source receipt. Certificate-child verify rechecks frozen evidence, lineage,
self checks and unchanged HEAD before granting its final receipt.

| Resource | Owner / lifetime |
| --- | --- |
| Repository lock | prepare/run/verify wrapper; fd held to final receipt, inode persists |
| Shard temp parent | Local Assurance OwnedRoot; abnormal release retains it |
| Seed / worker / artifact root | PersistentWorkspace; never shared or resumed |
| JUnit / basetemp | Runner inside checked workspace artifact root |
| Target process / pipes / runtime temp | run_captured; drain before restore or deletion |
| IDs / transcript / official records | Unique canonical gate directory and shard |
| Manifest / receipts | Locked invocation; atomic sibling replacement |
| Performance / failure telemetry | Best effort diagnostic owner outside evidence |
| Quarantined prior run | Preserved sibling; never admitted as current evidence |

## Defects and source-of-truth consolidation

Concurrent invocations previously shared source directories and certificate
output. A repository-wide nonblocking Linux flock now serializes prepare, run
and verify even with differing local roots or SHAs. No lock inode unlink.
JSON manifest, receipt, assurance and failure writes now use atomic replacement.
Manifest rows refuse absolute/traversal/duplicate/link paths. Production admission
requires exactly the canonical EVIDENCE closure and source/tree binding; diagnostics
and unexpected files are refused rather than swept into evidence. Receipt manifest
name is fixed. Stale certificate self-check JUnit is unlinked before execution.
HEAD checks cover manifest, certificate, receipt and child verification boundaries.
Failure persistence errors no longer replace the primary refusal. Retention context
includes source/tree/execution and shard/retained storage without environment dumps.
Workspace infrastructure errors preserve their original cause instead of replacing
it during an attempted restore of an already poisoned workspace.

mutation_population owns Formal/V4 shard counts; Local Assurance now imports them.
DEFAULT_MUTATION_WORKERS owns CLI/API default two. PERFORMANCE_SCHEMA and its
non-authority admission helper own diagnostic archive validation. EVIDENCE owns
official filenames; PristineIndex owns seed identities; OwnedRoot owns deletion
admission. Runner timeouts remain intentionally separate (Formal 2400s, V4 1800s).
Legacy V4 isolation helper remains because B55d mutates its exact source token;
removing it would change the certified population. No broad cleanup or new framework.

## Formal / V4 compatibility

| Contract | Formal | V4 |
| --- | --- | --- |
| Copy | src/tests/tools/experiments/docs/benchmarks and pyproject | src/tests/experiments/certification tools/.git, pyproject, benchmark JSON |
| Git | No copied .git | Private standalone copied .git; sealed configuration |
| Control | Before mutations | After mutations |
| Application | Existing token/parse guards | Same guards, named target and additional edits |
| Pytest | Whole TARGETS, no randomly, continue collection errors | Named test, no cacheprovider, runxfail, JUnit |
| Attribution | Named transcript failure or admissible core import refusal | Exact named-test JUnit; absent/skip/error/collection statuses preserved |
| Exit code | 0/1; 2 only admissible import refusal; other infrastructure refused | Only 0/1 admitted before JUnit attribution |
| Restore/process | Shared verified workspace + subreaper drain | Same ownership semantics |
| Evidence | Exact population transcript record | Exact population/JUnit-attributed transcript record |
| Telemetry | Diagnostic only | Diagnostic only |

Timeout is absence of evidence, never a mutation kill. Exit 3/4/5 and negative
signal exits cannot earn mutation credit. Formal collection exit 2 cannot earn
ordinary named-guard credit; its explicit import-refusal mechanism is preserved.
No population, expected verdict or certification schema changed.

## Authority, identity, collisions and atomicity

Performance/failure schemas have fixed false authority flags. Certificate builders
never consume timings, workspace manifests, retained trees or diagnostic files.
Exact EVIDENCE filenames are the production manifest closure. Immutable indexed
seed identity and fresh random owned roots prevent accidental workspace reuse;
source/shard/execution telemetry is explanatory, not evidence admission.
Each family/shard uses a distinct canonical prefix, owned temp parent and private
JUnit/basetemp. The repository lock prevents cross-invocation collisions.
--reuse quarantines the old directory and executes all gates anew; it is not resume.

Logs remain streaming and IDs/records/JUnit retain their existing writer contracts:
process success, complete population/selection/log digests and report validators
must succeed before final manifest/receipt admission. Interrupted partial files
cannot alone grant completion. Certificate write uses its existing deterministic
writer and subsequent content/verification checks; no new certificate was made.

All runtime outputs are external temp or intentionally ignored .forge storage.
Certificate remains the sole expected tracked generation change. Lock/quarantine
and diagnostic additions cannot excuse another tracked or unignored change.

## Platform and import contracts

Linux/WSL authoritative entry is enforced; native Windows/macOS refused. /proc,
single-thread/main-thread ownership, empty initial child frontier, subreaper and
SIGCHLD state are detected and refused if ambiguous. Directory ancestor/inode,
regular-file link-count, nofollow open and permission assumptions are checked.
POSIX flock is a Linux contract. Case-sensitive Linux paths and controlled installed
toolchain/PATH/plugins remain deployment assumptions; deliberately malicious
same-UID code can still open arbitrary absolute paths.

Inherited GIT_* and Python injection variables are sealed; global/system Git
config is null, external object/helper/history redirections refused. Cwd discovery
is preserved for synthetic Git repositories whose helpers supply explicit author
identity. pyproject pythonpath retains src, '.', test/benchmark/experiment helper
roots. Provider/flagship paths remain declared but outside historical mutation copy
scope; controlled optional installed adapters are a toolchain assumption. This pass
makes no new provider applicability or scientific claim and does not enlarge scope.

## Intended specifications — NOT RUN

Existing workspace specifications cover seed/worker contamination, hidden same-size
changes, sparse repairs, symlink/hardlink substitution, ownership, descendant drain,
SIGCHLD races, Git redirects, environment injection, telemetry authority and quarantine.
Local Assurance specs cover bounded families, failed scratch retention, exact source
identity, gate propagation and clean tree. Pass 6 corrects old assertions that deleted
failed roots and adds unsafe-manifest-path, invocation-lock and diagnostic-write-error
specifications. Runtime validation of all specs remains required before integration.

## Complexity and next frontier

Workspace trust semantics are explicit and specific; no generic scheduler or cache
admission was added. There is still complete verification cost per attempt by design.
The next frontier is interpreter/pytest/plugin/import/conftest/collection/JUnit setup.
For M_F selected Formal mutations and M_V eligible V4 mutations, full shards launch
M_F + 4 and M_V + 8 fresh target interpreters respectively (plus selection/recording
and ordinary gates); apply refusals reduce launches. These are source counts, not
measurements. Fresh processes preserve the cleanest isolation contract. Precomputed
collection metadata needs exact source/plugin/config binding and cannot replace actual
collection evidence. Pools, persistent Python/pytest and direct test invocation have
higher risk from module globals, monkeypatches, fixtures, plugin state, collection and
JUnit semantics. Do not implement these alternatives before authorized runtime checks.

Independent complete accumulated Pass 2–6 hostile static review: PASS.
Freeze decision: READY_TO_FREEZE_WORKSPACE_ARCHITECTURE. Static readiness never establishes
runtime compatibility or measured performance. Future performance passes should keep
workspace trust semantics fixed unless runtime validation exposes a defect.


## Independent review record

A. Scope: complete accumulated tracked/untracked Pass 2–6, source inspection only.
B. Authority: diagnostic flags remain false; canonical evidence only; infrastructure exits refused.
C. Applicability: no scientific/domain applicability change.
D. Verification/validation: review is not runtime verification or scientific validation.
E. Uncertainty: no missing-information defaults introduced.
F. Evidence/context/policy: locking, manifest source/tree/path/closure and attribution preserved.
G. Provenance/replay: fresh roots, source guards, disabled resume and quarantine reruns.
H. Coverage: hostile specifications inspected, never executed.
I. Findings: all reported static defects repaired and reinspected; no remaining actionable
static defect under the controlled-target/toolchain contract. Runtime lifecycle and import
closure remain untested. No OS sandbox against malicious same-UID code is claimed.
J. Verdict: PASS.

Complete accumulated files changed:
- tools/certification/local_assurance.py
- tools/certification/mutation_workspace.py
- tools/certification/performance_telemetry.py
- tools/certification/mutation_v4_runner.py
- tools/certification/core_certificate.py
- tests/mutation_guards.py
- tests/test_mutation_workspace.py
- tests/test_local_assurance.py
- docs/assurance/LOCAL_ASSURANCE.md
- docs/work/ACTIVE_PLAN.md
- docs/work/PROGRESS.md
- docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_3.md
- docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_4.md
- docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_5.md
- docs/work/LOCAL_ASSURANCE_WORKSPACE_STATIC_REVIEW.md
- docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_6.md
