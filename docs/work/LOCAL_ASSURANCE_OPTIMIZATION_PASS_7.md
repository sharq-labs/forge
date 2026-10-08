# Local Assurance optimization pass 7 — static startup cost model

HEAD: 8d5eed3f47a0490d481b7ff5c9927f2f944096db. Passes 2–7 uncommitted.
Workspace trust architecture remains frozen under controlled targets/toolchain.
TESTS_RUN: 0. ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No project execution, imports, tests, collection, subprocess probes, timing,
benchmarks or certificate generation. Counts below use AST literal parsing only.

## Chosen architecture

FRESH_PROCESS_OPTIMIZED. Each mutation attempt still launches a fresh Python/pytest
child through the existing shard supervisor and exclusive descendant owner. There
is no process pool, fork bootstrap, persistent pytest, batching, result cache or resume.
Restoration and complete worker verification are unchanged.

## Repeated work and invocation counts

Each launched attempt repeats interpreter/site startup, installed dependencies and
pytest imports, builtin plugin registration, config/rootdir discovery, conftest,
target-module imports and collection, fixture setup, test execution, output handling
and interpreter teardown. V4 also initializes/writes JUnit per target. Formal retains
its existing transcript evidence and does not add JUnit. Some builtins initialize
without doing work (e.g. a run without doctests); no seconds/percentages are inferred.

284 Formal entries, 48 TARGETS modules, four first controls: at most 288 launches
if every application succeeds. 680 V4 entries: 666 KILLED expectations, 12 SURVIVED,
two NOT_MUTATED excluded by CLI. 678 executed mutations plus eight last controls:
at most 686 launches. Combined full-shard target launch count: 974. Application
refusal or early infrastructure failure reduces this count. This excludes shard
processes, population selection/recording, source gates and certificate self checks.
No interpreter starts were measured; the optimization does not reduce this count.

V4 population: 590 distinct nodeids, 120 test modules, 121 mutation source files.
Formal mutation source files: 70. Formal guard declarations and REFUSED_AT_IMPORT
are mechanism strings rather than equivalent V4 nodeids; no invented one-to-one
mapping narrows its 48-module execution contract.

Most repeated V4 modules (population entries):
- tests/test_core_scientific_audit_batch15.py: 21
- tests/test_guard_reach_ledger.py: 21
- tests/test_core_scientific_audit_batch13.py: 18
- tests/hybrid_uq/test_core_scientific_audit_batch1.py: 17
- tests/hybrid_uq/test_core_scientific_audit_batch21.py: 17
- tests/hybrid_uq/test_core_scientific_audit_batch38.py: 17
- tests/hybrid_uq/test_core_scientific_audit_batch11.py: 16
- tests/hybrid_uq/test_core_scientific_audit_batch12.py: 16

Top repeated V4 nodeids:
- batch21::test_r15_a_clipped_probe_is_counted_and_compared_at_the_radius_it_reached: 4
- batch56::test_r69_the_additive_changes_the_owner_allowed_are_the_only_ones_accepted: 4
- batch11::test_the_leverage_test_is_the_pooled_test_when_every_weight_is_equal: 3
- batch15::test_r72_the_kinds_the_three_declaring_problems_name_are_all_registered: 3
The full module paths are those in tests/mutation_population_v4.py; the abbreviated
names above are display only, never passed to pytest.

Most repeated Formal source files: arbiter.py 19, local_gaussian.py 16,
scientific/models/definition.py 15, hybrid_uq/router.py 15,
scientific/results/validation.py 14, scientific/results/result.py 13.
Grouping is metadata, not permission to reuse imports or batch mutations.

## Plugin and collection policy

A source scan of 165 distinct target modules plus their applicable conftest found
no pytest_plugins declaration or external pytest-plugin import. Only tests/conftest.py
applies to these target paths. Project dev dependencies declare pytest and optional
xdist; these mutation commands request no parallel plugin functionality. Required
fixtures are pytest builtins, module-local fixtures and parametrization; repository
conftest tier labels remain. No installed entry-point plugins are admitted:
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 is forced for every child, including controls.
Coverage, asyncio, benchmark, randomization and unrelated host autoload are blocked.
This does not block explicit repository conftest registration; controlled source
and installed pytest remain part of the accepted contract.

Installed pytest config source was read (not imported) under .forge/venvs/3.12:
default builtin loading is separate from pytest11 entry-point autoload. Preserve
builtins rather than trying to infer a minimal transitive builtin dependency graph.
Builtins include essential config/main/runner/fixtures/helpconfig, python, terminal,
unittest, capture, skipping, tmpdir, monkeypatch, recwarn, assertion, junitxml,
warnings, logging, faulthandler and version-dependent auxiliaries. V4's existing
no:cacheprovider stays; Formal's no:randomly stays as harmless explicit intent.
No exact installed third-party list is needed because admission is empty.

V4 already uses the exact population nodeid as one argv element, including parameter
cases. Controls use a sorted unique union; Formal TARGETS and continue-on-collection
errors stay broad and unchanged. Keep pyproject discovery/pythonpath and conftest:
-noconftest/alternate empty config would remove required behavior. No collection
cache or pre-collected pytest Items are introduced.

## Startup inputs, commands and executable identity

mutation_startup.py owns immutable invariant command flags and plugin/bytecode policy.
StartupInputs copies the parent environment once per workspace/shard into a
MappingProxyType. Every child receives a separately constructed sealed dict with
new owned runtime temp/Git-template paths. Children cannot mutate the snapshot.
All inherited PYTHON* startup variables and PYTEST_ADDOPTS/PYTEST_PLUGINS are removed;
only reviewed no-user-site and no-bytecode-write flags are restored. Git sealing
is unchanged. Inherited warnings/optimization cannot silently change assertions.

The absolute interpreter spelling is captured once; its venv symlink is deliberately
not resolved, preserving Python site/pyvenv discovery. The executable target's
(device,inode,mode,size,mtime_ns,ctime_ns) is checked before every target/control.
This detects accidental executable drift, not deliberate malicious metadata spoofing,
and cannot seal installed dependencies or pyvenv.cfg. Those remain controlled
immutable toolchain assumptions; no cryptographic executable-certification claim.
The exec/check race is under that same toolchain contract. Git executable resolution
remains controlled PATH rather than inventing an additional process layer.

Population tuples and nodeid strings are already parsed once per shard. No additional
metadata cache is useful: command arguments reference existing immutable scalar
metadata, and exact runtime JUnit/output remains the evidence. No pytest Items,
fixtures, imported worker modules or runtime results are retained.

## Bytecode and Python flags

Both population copiers now exclude __pycache__ and *.pyc. Each child is forced to
PYTHONDONTWRITEBYTECODE=1; inherited PYTHONPYCACHEPREFIX is stripped. No shard-shared
bytecode cache is introduced. No target import can leave bytecode for the next
attempt; full workspace verification remains the final contamination check.
No-write does not disable reads from controlled installed dependency bytecode, nor
prevent a deliberate target writing a file; existing repair handles the latter.
Initial worker caches are excluded and attempt-created files are restored away.
An external shared cache could timestamp-alias restored mutation files, so reject it.
Reduced filesystem writes may trade for repeated compilation; no speedup claimed.

-I: not applied; isolation removes cwd paths and ignores PYTHON* controls, risking
repo helpers and environment semantics. -s: compatible but redundant with forced
PYTHONNOUSERSITE. -E: not applied; ignores deliberate PYTHON* policy including no-write
and runtime temp-independent controls, offering no gain after sealing. -S: rejected;
skipping site initialization breaks installed dependencies and editable behavior.
Keep Formal -X utf8 and V4's existing interpreter mode; no global semantic flag change.

## JUnit, Formal output and failure semantics

JUnit remains one independently owned report per V4 attempt; previous report is
unlinked before launch, parsed exactly once and kept until workspace cleanup. It
already lives outside worker, so deleting earlier offers no proven benefit and loses
diagnostics. Strict UTF8 and testsuite/testsuites structure now refuse non-JUnit
XML; testcases must belong directly to suites. Exact named/parameter matching is
unchanged. Missing, malformed, errored/skipped/uncollected reports never earn kill.

Formal keeps full captured output, existing FAILED/core-refusal matching and summary.
A streamed/truncated parser could omit refusal context or final evidence, so no
bounded-buffer rewrite without a separately specified exact parser. No attribution
text is truncated. Existing run_captured centralizes cwd/env, close_fds, pipe lifetime,
session creation, timeout and Linux descendant drain. No additional supervisor.
Startup launch failure/infrastructure status refuses; timeout is absence of evidence;
Formal explicit collection-refusal mechanism and V4 0/1 admission stay unchanged.

## Design classification

| Option | Classification | Reason |
| --- | --- | --- |
| Fresh Python + deterministic plugins | SAFE_TO_IMPLEMENT | Implemented; fresh runtime, exact pytest semantics |
| Direct nodeids / immutable templates | SAFE_TO_IMPLEMENT | Already narrow; command flags/snapshot consolidated |
| Fresh programmatic pytest.main wrapper | NO_MEANINGFUL_GAIN | Imports/collection remain; another wrapper |
| Direct function/test harness | TRUST_RISK_TOO_HIGH | Fixtures/hooks/JUnit/parametrization not equivalent |
| Reused process pool | TRUST_RISK_TOO_HIGH | Modules/globals/fixtures/hooks cannot be completely reset |
| Pool destroying child each attempt | NO_MEANINGFUL_GAIN | Current shard supervisor already does this |
| Persistent pytest | TRUST_RISK_TOO_HIGH | Retains mutable runtime state |
| Fork after stdlib-only bootstrap | POSSIBLE_WITH_STRONG_RESET_CONTRACT | Little work amortized; threads/signals/descriptors/random/subreaper hazards; not implemented |
| Fork after pytest/project import | TRUST_RISK_TOO_HIGH | Imports and unsafe library/thread state inherited |
| Collection metadata | POSSIBLE_WITH_STRONG_RESET_CONTRACT | Needs exact source/plugin/config binding; cannot replace collection |
| Same interpreter batching | TRUST_RISK_TOO_HIGH | Shared state survives restore |

## Intended adversarial specifications — NOT RUN

New test_mutation_startup.py covers immutable parent/template/child separation,
plugin autoload overrides, no inherited shared pycache, host Python switches,
executable replacement and venv spelling, exact parameter nodeids, one launcher call
per attempt, independent report paths, no mutable startup imports, malformed JUnit,
invalid UTF8/non-JUnit structure and Formal legacy bytecode exclusion. Existing
workspace specs cover descriptor/quiescence ownership, stale JUnit removal, process
failure and infrastructure status refusal. No fork-only specs needed; no fork exists.

## Review and next pass

Final independent hostile review: PASS, implementation/specifications/documentation
reinspected after all findings were repaired. No runtime checks authorized.
Recommended Pass 8: authorize bounded runtime validation of fresh-process policy,
controls, builtin fixture/JUnit/plugin admission, environment and bytecode isolation,
then measurements to choose the next bottleneck. Keep workspace trust frozen; do
not infer performance improvements from these source counts.

Eligible V4 subset: 588 distinct nodeids and 120 modules.


## Final independent review record

A. Scope: implementation, specifications and all Pass 7 documentation.
B. Authority: immutable startup inputs are not evidence; fresh subprocesses retained.
C. Applicability: scientific/domain behavior unchanged.
D. Verification/validation: static review only; zero tests or runtime measurements.
E. Uncertainty: unchanged.
F. Evidence/context/policy: sealed startup/plugin policy and strict JUnit admission.
G. Provenance/replay: venv spelling preserved; metadata checks detect accidental drift.
H. Coverage: adversarial specs inspected, NOT RUN.
I. Findings: all reported defects repaired; no remaining actionable static finding.
Runtime dependency/plugin compatibility and process lifecycle remain unestablished.
J. Verdict: PASS.

Pass 7 files changed: mutation_startup.py, mutation_workspace.py,
mutation_v4_runner.py, tests/mutation_guards.py, tests/test_mutation_startup.py,
docs/assurance/LOCAL_ASSURANCE.md, docs/work/ACTIVE_PLAN.md,
docs/work/PROGRESS.md and this document.

FRESH_PROCESS_OPTIMIZED
