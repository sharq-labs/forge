# Forge Work Progress

This file is persistent engineering memory for long-running AI-assisted work.
Keep it concise and factual. Do not use it as a release note or marketing log.

## Current branch / PR

- Branch: `ci/self-hosted-heavy-runner` (from `origin/main` @ `2b76017f`, PR #106 merged)
- PR: none recorded yet; verify GitHub before making a current PR claim.
- Base: `main`
- Strategic contract: `docs/project/FORGE_MASTER_PLAN.md`
- Current execution authority: `docs/work/ACTIVE_PLAN.md`

## 2026-09-25 self-hosted heavy CI runner (design + tooling; NOT RUN on the PC)

Goal: run the expensive CI jobs on the owner's PC without weakening any gate.
Full design, threat model, setup and operating procedure: `docs/assurance/SELF_HOSTED_RUNNER.md`.

- Heavy jobs (`fast`, `mutations`, `scientific`, `reproduce`, `benchmark`; recertify `fast311/312`,
  `scientific312`, `campaign312`, `regression312`, `formal_mutations_0-3`, `v4_mutations_0-7`,
  `trust_mutations`; `trust-mutations`) use `runs-on: fromJSON(<classifier>.outputs.heavy_runs_on)`.
  Everything that mints or pushes trust (`certify`, certificate verification, both gates,
  `branch-policy`, classifiers) stays GitHub-hosted. Job names, `needs:` and evidence names are unchanged.
- `tools/ci/select_heavy_runner.py`: default `github-hosted`; `FORGE_HEAVY_RUNNER=self-hosted` opts in;
  untrusted events (forks, non-collaborators, odd event types) stay on GitHub-hosted; an unknown value
  fails the run. An offline PC waits in the queue (never re-routed); optional `RUNNER_STATUS_TOKEN`
  fails fast instead.
- **The workflow-side routing is not the security boundary** (a fork's PR runs its own copy of the workflow).
  The boundary is `tools/ci/runner_guard.py` run by a root-owned job-started hook on the PC, the repository's
  fork-approval setting, and a dedicated WSL2 distro with no Windows drives/interop and no sudo.
- Each heavy job now: read-only token, `persist-credentials: false`, asserts HEAD == the commit under test and
  a clean tree before any gate, installs into a job-scoped venv on self-hosted, records
  `runner-identity-<job>-<sha>`. The scientific gates require ngspice on the PC.
- Read-only finding: `fork-pr-contributor-approval` is `first_time_contributors` (too weak for this design);
  no runners or variables existed. **No repository setting was changed.**
- Failed/abandoned approaches: an uncertified composite action for the shared steps (rejected: `.github/**`
  outside the two workflows is outside the certificate, so weakening it would not move the control-plane digest);
  ephemeral runners (rejected: they need an Administration-scoped token stored on the PC); wiping `_temp` or the
  workspace in the job-started hook (rejected: the runner has already prepared them; cleanup runs after each job and
  before every service start instead).
- P0.1 status is unchanged by this slice: PR #106's Recertify run was still executing when #106 merged, so its
  certificate child can never reach `main` and `certification/current_core_v2.json` stays stale. This PR edits the
  certified workflows, so it is classified source-mode and its own recertification produces the certificate child.

2026-09-25 (local, Windows host, Python 3.14; not on a runner)
command: `python -m pytest -q tests/test_ci_runner_selection.py`
result: PASS
summary: 72 passed (routing, availability, machine-side guard). 16 targeted mutations of `tools/ci/` were each killed by a test.
commit: working tree on 2b76017f

2026-09-25 (local)
command: `python -m pytest -q -n 4 tests/test_recertification_scope.py tests/test_certification_control_plane.py tests/test_certificate_lineage.py tests/test_hardening_assurance.py tests/test_ci_runner_selection.py tests/test_core_guards.py tests/test_pin_portability.py`
result: PASS
summary: 537 passed against the modified workflows (topology, gate names, no `git clean`/reset text, control-plane pins)
commit: working tree on 2b76017f

NOT RUN: `actionlint`; installing/registering the runner; the hooks on a real runner (whether the runner exports the guard's
variables to hooks is unobserved and the guard refuses if they are absent); the heavy jobs on the PC; numerical agreement of
pinned-digest tests on the PC's CPU; the `RUNNER_STATUS_TOKEN` API check.

## 2026-09-25 P0.1 failure triage

`main` @ `deabe5cb` was RED. Read from GitHub Actions (run 36117761308, Tests):
FAST 3.12, FAST 3.11 and SCIENTIFIC each failed the same **54** tests; the
`mutations` job's CONTROL was RED (round void) because of 3 of them; `reproduce`
(Docker) failed 165; `Branch Policy` failed with `POLICY NOT ENFORCED`.

Root causes (all local, none needed a guard weakened):

| Cluster | Tests | Cause | Fix |
| --- | --- | --- | --- |
| predictive/hybrid UQ fixtures | 24 | fixtures declared no observation noise; production correctly refuses it | fixtures declare a noise sigma |
| `float(P.sigma)` | 3 | `P.sigma` is a per-observation vector; current numpy rejects `float()` | `P.sigma[5]` |
| consensus non-finite | 20 | **production regression**: `over()` compared raw values but stored only finite ones, so the record-recompute check raised at construction | see "Consensus decision" below |
| standard uncertainty to an affine target | 1 | **production defect**: propagated spread was stamped in `degree_Celsius`, which the spread rule refuses | carried on the dimension's base unit (kelvin), slope-only conversion |
| exact-identity attribution | 2 | tests attributed by prose/`@` substring, the spoofing path BIG 1 closed | tests name exact identities; new test that prose is refused |
| multiphysics expectations | 3 | one test forged an empty iteration (refused earlier, by the record) and two expected `UnitCompatibilityError` where the port-contract check raises `InvalidScientificProblem` | two-participant fixture; exception class |
| independence-group message | 1 | message reworded to cover calibration/validation/holdout | match updated |
| stability reasons | 3 | `in tuple` where a substring was meant | `any(... in reason)` |
| stale mutation `B48c` | 2 | target line changed to `references` | repointed; same killing test |
| certificate | 2 | `certification/current_core_v2.json` describes an older tree | **not edited**: regenerated only by the CI certify child on 3.12 |

### Consensus decision (recorded so it is not re-litigated)

BIG 1 made a non-finite reading on an *unshared* diagnostic stop erasing a real
finite disagreement, but did it inconsistently. The rule now, for shared and
unshared readings alike: a non-finite reading **never helps routes agree**
(agreement with any non-finite reading present is a "nothing compared" refusal),
**never hides** a disagreement the finite shared readings show (kept, with the
offenders named), is **not a reported output**, and numbers travel with the record
only when **every** reading is finite, so such a record can never be `earned`.
A finite disagreement kept beside a non-finite reading is a FAIL built from a
route the module calls unfinished. That is fail-closed (it can only withhold), and
was chosen over NOT_RUN so a route cannot avoid a FAIL by emitting a NaN. The
scientific reviewer (read-only) required the single-rule fix; it is applied.
Not changed, pre-existing, noted by the reviewer: `to_check` can report PASS for a
comparison with no recomputable numbers (level still withheld); finite extremes
(1e308 vs -1e308) raise instead of recording; `_delta_magnitude_in` re-implements
`Quantity.magnitude_as_spread_in` with ~1e-13 cancellation error.

### Repository-level findings (not code)

- The `Protect main` ruleset (id 23351506, active, no bypass actors) contains
  `deletion`, `non_fast_forward` and `pull_request` (0 approvals) but **no
  `required_status_checks` rule**. `main` therefore does NOT require
  `tests-gate` or `recertification-gate`. Restoring it is a repository-settings
  change and needs the owner's explicit go-ahead; do it only once the gates are green,
  or the fix PR itself cannot merge.
- The Docker `reproduce` job has failed on every `main` push since 2026-09-14
  (`.dockerignore` excludes `.git`, so certification tests find no repository).
  It is outside `tests-gate`; not fixed by this slice.

## 2026-09-25 scientific-correctness hardening handoff

This is the current AI/session handoff. Read it before older progress entries.
The work below is **implemented but NOT RUN/verified** unless a later
verification entry explicitly says otherwise.

### Why this slice exists

After P0 assurance stabilization, the scientific audit exposed false-confidence
and evidence-integrity paths that must be hardened before P1 Time Engine work.
Reproduce each finding against current code, prefer minimal fail-closed changes,
and never weaken UNKNOWN/evidence semantics merely to make tests green.

### Source lineage

The branch received an automatic recertification child at
`26c8b9b01b9d88b78ce526b4b6e50735e26f8b41`, parent
`44885bf01aa4ceafddaaf317ba2569ef1d04a904`.

Scientific hardening was developed as a detached chain from the same source
parent so CI would not restart after every micro-fix:

- `7efa13d792caf6e9d47a0e976437bbb16f83fb77` — evidence monotonicity and run integrity
- `706756c7d4f7b4216859e4e776b2917e171f0c07` — uncertainty/stability false-confidence paths
- `655f20fe69ef8aae22a657b5ed5af56bede7f226` — independent evidence and oracle provenance
- `ab59ec47d5cd0e53f7b84df398431fb930f9dda0` — missing-noise refusal and exact UQ provenance

The current branch merges that detached chain with the certification child
instead of replacing either history. The old certificate child is historical
evidence only; after source changes it does not certify the new head.

### Implemented in BIG 1 — verification pending

1. **Coverage / evidence monotonicity**
   - unresolved/adverse in-domain outcomes block `SUPPORTED`;
   - coverage counts independent evidence groups rather than correlated case copies;
   - one independence group may not cross calibration/validation/holdout roles.

2. **Campaign adequacy / comparison integrity**
   - independent failure without scored calibration evidence becomes
     `INSUFFICIENT_EVIDENCE`, not automatic model-form failure;
   - exact-zero tolerance keeps FAIL semantics without non-finite JSON.

3. **Consensus**
   - unrelated non-finite diagnostics no longer erase a real shared disagreement;
   - shared non-finite values remain unusable evidence.

4. **Multiphysics**
   - composition fingerprint recursion removed and candidate-derived ambiguity enforced;
   - frame transforms must be proper rotations, not reflections;
   - run end cannot exceed plan horizon;
   - termination instant must equal actual end;
   - every iteration must record exactly one step per graph participant;
   - participant steps must span their coupling window;
   - scenario inputs and QoIs are checked against port value/uncertainty contracts;
   - scheduled events inside the executed horizon require reached receipts;
   - state-transition digest chains must remain contiguous.

5. **Replay**
   - zero expected outputs cannot count as verified replay output agreement.

6. **Uncertainty / UQ**
   - STANDARD uncertainty requires a spread/ratio-scale unit;
   - identifiability classification is fixed at 95%;
   - affine-temperature sigma/std conversions use spread semantics;
   - undeclared observation noise cannot silently become zero total uncertainty;
   - non-finite/negative numerical residual evidence follows an explicit refusal path;
   - model-form residual units must be spread units;
   - cross-domain uncertainty attribution uses exact identities, not substring matches.

7. **Oracle / discovery**
   - oracle binding requires a real `ScientificResult`, not duck typing;
   - discovery fingerprints bind candidate id, calibration/holdout RMSE,
     complexity and status;
   - holdout-result statuses require a holdout RMSE.

### Verification status

Superseded by the verification log below and the P0.1 triage above. The BIG 1
gates are **not** closed until the CI run on the final source head is green.
Do not claim PASS, green, verified, validated or certified from static inspection.

### Next executable work

1. Inspect current branch HEAD/diff; do not trust stale chat state.
2. Add/adjust focused regressions for each changed scientific invariant.
3. Run changed-area compile/tests and `git diff --check`.
4. Run `python tools/forge_check.py --changed`, then the required scientific tiers.
5. Diagnose failures without weakening scientifically valid guards to satisfy old tests.
6. Run the read-only scientific reviewer after tests stabilize.
7. Obtain green CI on the final source head.
8. Verify `main` rules require `recertification-gate` and `tests-gate`.
9. Only then start P1 Time Engine.

### Short recovery prompt

`Read CLAUDE.md, docs/project/FORGE_MASTER_PLAN.md, docs/work/ACTIVE_PLAN.md and docs/work/PROGRESS.md. Inspect the current feat/scientific-correctness-hardening HEAD and continue from the first unfinished scientific-correctness task. Treat NOT RUN as unverified; do not weaken scientific guards or change direction without repository evidence.`

## Completed in this line of work

- Added the persistent Forge Master Plan as the long-term project operating
  contract, including session recovery, roadmap precedence, solver/provider
  strategy, data policy, Time/Environment/Lifecycle pillars and flagship systems.
- Updated `CLAUDE.md` so every new agent/session reads the Master Plan before
  selecting work, and removed the obsolete manual-only CI policy.
- Reframed `ACTIVE_PLAN.md` around P0 assurance stabilization followed by
  Time, Environment and Lifecycle foundations.
- Restored automatic Tests and hardened-core recertification workflows on pull
  requests, retained manual fallback, made V4 mutation shards explicit
  certification prerequisites, fixed the assurance-builder CLI invocation and
  completed the declared Docker test/benchmark dependency set.
- Automatic workflow runs were triggered on PR #102 after these changes.
  Their final scientific/test result must be read from GitHub Actions before
  any PASS/green claim is made.

- Added deterministic hierarchical system/component topology bound to existing
  `ScientificTwin`, `PortDefinition`, `PhysicsGraph` and `CouplingEdge`
  authorities. Structural topology is bound through authorized execution;
  unconsumed parameter/state/constraint bindings fail closed.
- Routed window-aligned STEP scenario inputs through the live multiphysics
  runtime without reinitializing participant state; consumed values are
  receipted per window. Unsupported interpolation/features and schedule-less
  replay fail closed.
- Added immutable, unit-bearing, digestible generic scenario contracts with
  strict timeline, state, interpolation and wire-shape validation.
- Added additive GraphPlan v3 scenario binding. Authorized execution currently
  accepts timing-only scenarios and fail-closed refuses every material
  scenario field until runtime consumption and receipts are implemented.
- Removed battery/electrical/thermal realization and solver imports from
  `planning.production`; enabled validated Domain Packs are now the sole
  production source for these artifacts, with existing fail-closed identity
  collision checks retained.

- Extracted credibility/V&V implementation from MCP transport into
  `engcore.credibility`.
- Removed the `claims -> mcp` implementation dependency.
- Added compatibility shims for old MCP credibility imports.
- Grouped claim analysis, governance, replay and NL adapter implementations
  under subpackages while preserving old import identity.
- Added a current architecture entry point and historical-audit index.
- Added persistent Claude/agent working contract, scientific reviewer,
  regression manifest and fast changed-file gate.
- Added trust-registry change detection to impact analysis.
- Strengthened replay bundles with source/runtime environment fingerprints.
- Renamed sprint-phase claim tests by scientific feature.
- Added `tools/forge_impact.py` for dependency and reassessment queries.
- Added the Scientific Diagnostic Engine: blocking-cause classification, explicit assumption registry, model-data discrepancy diagnostics, corrective actions and sensitivity-ranked repair hypotheses.
- Added `tools/forge_diagnose.py`; diagnostics remain derived/non-authoritative and cannot alter verdicts.
- Hardened diagnostics: raw assessments are re-derived before diagnosis; custom-trust assessments require replay bundles; sensitivity/robustness artifacts are sealed and bound to assessment/plan/capability identity.
- Hardened impact drift: current oracle trust/digest changes and removed policy profiles now trigger reassessment.
- Strengthened replay source identity with tracked-diff and untracked-content digests.

## Verification log

2026-09-25 13:00 EDT
command: `python -m pytest -m "not expensive" -q -n 4` (Python 3.14, worktree D:/forge-p01, HEAD 46cf014b)
result: FAIL (expected baseline + 1 mine)
summary: 11 failed, 8407 passed, 8 skipped. Failures: 2 certificate tests (stale `current_core_v2.json`, CI certify child owns it); 6 freeze/API-surface tests (`test_r69...`, `test_a_descendant_that_keeps_the_contract_still_verifies`, `test_core_freeze_v4_is_the_contract_that_binds_on_this_tree`, 3 in `test_core_freeze_v4_manifest.py`) which fail IDENTICALLY on a pristine `origin/main` worktree under 3.14 (baseline artifact; CI 3.12 passes them); 2 fresh-process digest tests (pass with `PYTHONPATH='D:\\forge-p01\\src;D:\\forge-p01'`); `test_consensus_completeness_grows_linearly_with_required_outputs` (mine: an O(n^2) list membership, fixed in 63b94a3c).
commit: 46cf014b

2026-09-25 13:10 EDT
command: `python -m pytest -q tests/test_consensus_integrity.py tests/test_core_invariants_adversarial.py tests/test_core_numerical_integrity.py tests/test_trust_boundary_consensus.py tests/test_cross_solver_consensus.py tests/test_core_performance_guards.py tests/test_trusted_consensus_gate.py tests/test_audit_consensus*.py -n 4`
result: PASS
summary: 269 passed (before the 3 new regression tests); then tests/test_consensus_integrity.py 26 passed and tests/test_cross_domain_uq.py 13 passed after adding regressions
commit: 63b94a3c (+ working tree tests)

2026-09-25 12:50 EDT
command: `python -m pytest -q -n 4 <the 54 test ids that failed on main>` (Python 3.14)
result: PASS except the 2 certificate tests
summary: 52 of the 54 pass after the batch; the 2 remaining are `test_core_certificate.py::test_the_certificate_describes_this_tree` and `::test_the_certificate_records_the_v1_relationship_truthfully`, which need the CI certify child
commit: 46cf014b

2026-09-25 (GitHub Actions, read, not executed here)
command: Tests run 36117761308 on `main` @ deabe5cb; Recertify run 36114967466 on PR #105 head 5026b40b
result: FAIL
summary: Tests: 54 failed in FAST 3.12 / FAST 3.11 / SCIENTIFIC, mutations CONTROL RED, reproduce 165 failed, Branch Policy `POLICY NOT ENFORCED`. Recertify @ 5026b40b: regression312 and campaign312 SUCCESS; fast311/fast312/scientific312, formal_mutations_0..3, v4_mutations_0..7 FAILED (every V4 shard CONTROL RED with 2-3 failures; shard 0 also B48c NOT_APPLIED); trust_mutations SUCCESS; certify skipped.
commit: deabe5cb / 5026b40b

2026-09-23 19:05 +03:00
command: GitHub Actions PR #102 — Tests run 323 / Recertify Hardened Core run 205
result: FAIL
summary: normal Tests workflow passed; hardened recertification reached the heavy gates, but campaign312 and regression312 failed during pytest collection because duplicate test basenames were imported with legacy import semantics. Updated the recertification workflow so campaign uses --import-mode=importlib and regression sets PYTEST_ADDOPTS=--import-mode=importlib. New head: ddd358c72f9cd5d95cd41835de54dbc03ee17db9.
commit: ddd358c72f9cd5d95cd41835de54dbc03ee17db9


2026-09-21 11:07 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_system_topology.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py; git diff --check`
result: PASS
summary: 21 passed; topology hierarchy/identity/graph bijection and authorized roundtrip pass, while unsupported bindings and impossible constraints refuse; independent scientific review verdict PASS
commit: f1e32ac1 (working tree changes)

2026-09-21 11:00 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/execution; git diff --check`
result: PASS
summary: 26 passed; runtime consumes and receipts window-aligned STEP inputs, while authorized electrothermal execution refuses them under its static-input applicability rule; independent scientific review verdict PASS
commit: 440a8165 (working tree changes)

2026-09-21 10:56 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/scenarios src/engcore/planning/records.py src/engcore/execution/multiphysics/runtime.py src/engcore/assembly/multiphysics.py; py -3 -m pytest --import-mode=importlib -q tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/execution tests/scientific/replay_core/test_run_replay_v2.py; git diff --check`
result: PASS
summary: compileall passed, 31 tests passed, and diff whitespace validation passed; STEP scenario values are consumed and unsupported replay/features refuse
commit: 440a8165 (working tree changes)

2026-09-21 10:54 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py; git diff --check`
result: PASS
summary: 14 passed; scenario contracts round-trip, timing-only scenarios bind through authorized execution, and unsupported material scenario fields are refused
commit: bec4ac58 (working tree changes)

2026-09-21 10:35 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/planning/production.py; py -3 -m pytest --import-mode=importlib -q tests/test_multidomain_science_hardening.py tests/mcp/test_planning.py tests/mcp/test_intent.py; git diff --check; git status --short`
result: PASS
summary: compileall passed, 22 tests passed in importlib mode, and diff whitespace validation passed; status showed only this slice plus pre-existing untracked agent metadata
commit: 72ac242c (working tree changes)

2026-09-21 10:34 +03:00
command: `$env:PYTHONPATH='src'; py -3 tools/forge_check.py --changed`
result: FAIL
summary: collection stopped on 7 pre-existing duplicate test-module basename import mismatches (`test_verify`, `test_serialization`, `test_lineage`, `test_psd`)
commit: 72ac242c (working tree changes)

2026-09-21 10:33 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_multidomain_science_hardening.py tests/mcp/test_planning.py tests/mcp/test_intent.py`
result: PASS
summary: 22 passed; production realization/solver assembly is Domain-Pack-owned and the authorized multiphysics planning path remains operational
commit: 72ac242c (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/test_numerical_reliability.py tests/test_multidomain_science_hardening.py tests/domainpacks tests/domains/battery/test_battery_solver.py`
result: PASS
summary: 51 passed; numerical-health contradictions are refused and the atomic battery production Domain Pack is frozen/registered
commit: 979e9159 (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest --import-mode=importlib -q tests/test_numerical_reliability.py tests/test_multidomain_science_hardening.py tests/domainpacks tests/domains/battery/test_battery_solver.py`
result: FAIL
summary: battery solver test collection cannot resolve its sibling helper `battery_cases` under importlib mode; the same suite passes in the repository's normal import mode
commit: 979e9159 (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m tools.certification.core_freeze --verify; py -3 -m tools.certification.core_freeze_v2 --verify; py -3 -m tools.certification.core_freeze_v3 --verify`
result: FAIL
summary: historical freeze verifiers fail on the already-drifted live API/serialization and stale certificates; V2 also aborts on a hardened Hybrid UQ fixture, while dirty-tree checks additionally report the current worktree
commit: 979e9159 (working tree changes)

2026-09-20 21:51 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/domainpacks/builtin_battery.py src/engcore/scientific/numerics/health.py; py -3 -m pytest -q tests/test_numerical_reliability.py tests/test_multidomain_science_hardening.py tests/domainpacks tests/domains/battery/test_battery_solver.py tests/test_domain_pack_extension_binding.py; git diff --check`
result: PASS
summary: compileall passed, 57 tests passed, and diff whitespace validation passed
commit: 979e9159 (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest -q tests/mcp/test_intent.py tests/test_multidomain_science_hardening.py`
result: PASS
summary: 16 passed; production fidelity selection and immediate unit grounding regressions passed
commit: 9143516e (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 tools/forge_check.py --changed`
result: FAIL
summary: collection stopped on 7 pre-existing duplicate test-module basename import mismatches (`test_verify`, `test_serialization`, `test_lineage`, `test_psd`)
commit: 9143516e (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest --import-mode=importlib -q tests/mcp/test_intent.py tests/mcp/test_planning.py tests/test_multidomain_science_hardening.py tests/test_design_d0_contracts.py`
result: PASS
summary: 25 passed
commit: 9143516e (working tree changes)

2026-09-20 21:46 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/mcp/intent.py src/engcore/planning/production.py; py -3 -m pytest --import-mode=importlib -q tests/mcp/test_intent.py tests/mcp/test_planning.py tests/test_multidomain_science_hardening.py tests/test_design_d0_contracts.py tests/test_design_d1_evaluation_archives.py tests/test_model0r_realization_foundation.py; git diff --check`
result: PASS
summary: compileall passed, 145 tests passed, and diff whitespace validation passed
commit: 9143516e (working tree changes)

Status: targeted changed-area tests pass; the repository changed-file gate is
blocked by duplicate test-module basename collection errors recorded above.

Environment note (2026-09-19): attempts to access the branch from the
assistant's local execution container were blocked before checkout because that
container could not resolve `github.com`. The latest hardening verification attempt
ran `git clone ... && python -m compileall -q src tools tests`, but clone failed first
with `Could not resolve host: github.com`; therefore compileall and pytest did not run.
This is not a test result and the status remains NOT RUN.

When a command is executed, append entries in this exact shape:

```text
YYYY-MM-DD HH:MM TZ
command: <exact command>
result: PASS | FAIL | BLOCKED
summary: <counts or first relevant failures>
commit: <sha>
```

Never convert NOT RUN into PASS based on code inspection.

## Failed approaches / dead ends

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 tools/forge_check.py --changed`
result: FAIL
summary: collection stopped on the 7 known duplicate test-module basename import mismatches (`test_verify`, `test_serialization`, `test_lineage`, `test_psd`); no changed-area test failure was produced
commit: 531a104a

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/scientific/multiphysics src/engcore/execution/multiphysics src/engcore/scenarios src/engcore/planning src/engcore/assembly; py -3 -m pytest --import-mode=importlib -q tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py; git diff --check`
result: PASS
summary: compileall passed, 138 tests passed, and diff whitespace validation passed for typed scheduled/reached synchronization receipts
commit: f61a40a8 (working tree changes)

Scientific review milestone: the first scheduled-event review returned CHANGES
REQUIRED because requested controls were stored under `final_outputs`, where
they could be mistaken for calculated results. The corrected design uses
dedicated typed requested/reached synchronization records, exact boundary
indices and the authorized scenario digest; the read-only reviewer then
returned PASS. Neither review executed tests or constitutes validation.

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m compileall -q src/engcore/scientific/multiphysics src/engcore/execution/multiphysics src/engcore/scenarios src/engcore/planning src/engcore/assembly; py -3 -m pytest --import-mode=importlib -q tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py; git diff --check`
result: PASS
summary: compileall passed, 133 tests passed, and diff whitespace validation passed for the first corrected initial-state implementation
commit: 374c709f (working tree changes)

2026-09-21 11:20 +03:00
command: `$env:PYTHONPATH='src'; py -3 -m pytest --import-mode=importlib -q tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py; git diff --check`
result: PASS
summary: 135 tests passed after adding fail-closed rejection for unknown state owners and dimensionally incompatible state uncertainty; diff whitespace validation passed
commit: 374c709f (working tree changes)

Scientific review milestone: the read-only `forge-scientific-review` reviewer
returned PASS for the corrected initial-state slice. The review did not execute
tests and is not a validation result. The accepted design requires a declared
participant state schema, exact values with existing uncertainty records, a
participant-produced receipt, dedicated run-record provenance, applicability
evaluation and fail-closed replay.

- Rejected an optional `initialize_state` callback that inferred state support
  from callback presence and let the runtime synthesize its own receipt. A
  no-op callback could acknowledge a requested state without installing it.
  The uncommitted implementation was removed. The next design must include a
  participant-declared state schema, state uncertainty, a typed participant
  acknowledgement/resulting-state identity, applicability evaluation, and a
  dedicated run-record receipt before initial state may enter authorization.

Record failed experiments here with the reason they failed before trying a new
approach. Do not delete old failed approaches merely because a later approach
works.

## Open structural follow-ups

- Manually run `python tools/forge_check.py --changed` on PR #65.
- Run FAST and SCIENTIFIC tiers before merge.
- Split the still-large `mcp/problem.py` in a separate structural slice.
- Continue reducing the remaining flat claim modules only after PR #65 is
  verified.
- Do not expand the frozen Scientific Core for repository-layout aesthetics.
