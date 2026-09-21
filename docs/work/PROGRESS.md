# Forge Work Progress

This file is persistent engineering memory for long-running AI-assisted work.
Keep it concise and factual. Do not use it as a release note or marketing log.

## Current branch / PR

- Branch: `refactor/repository-architecture-cleanup`
- PR: #65 — repository architecture and layer boundaries
- Base: `main`

## Completed in this line of work

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

## Sprint 3 — battery + thermal flagship (branch `claude/battery-thermal-flagship-sprint-3`)

Real NASA PCoE Li-ion discharge data driven through the authorized multiphysics
path. Full record in `benchmarks/battery_thermal_flagship_s3/ROUND_REPORT.md`
and `RESULT.json`.

**Result: Gate A NOT PASSED.** Temperature passes on the locked holdout (MAE
1.29 K, RMSE 1.65 K, P95 3.27 K against 2.5 / 3.0 / 5.0). Voltage does not:
MAE 38.4 mV passes its 40 mV limit, RMSE 62.4 mV and P95 108.1 mV fail their
50 and 90 mV limits. Two of the three holdout cells predict at about 20 mV
RMSE; the third, B0044, gives 99.7 mV and delivers 8.4% less charge than the
calibration cell its parameter set was fitted on. The model's charge-state
basis is a declared constant, which that gap breaks — an exclusion the model
record already states.

### Test runs

```
python -m pytest benchmarks/battery_thermal_flagship_s3/tests -q -p no:randomly
33 passed
```

```
python -m pytest -m "not expensive" -q -n 4 -p no:randomly
173 failed, 8188 passed, 8 skipped, 63 errors
```

That failure count is compared against a pristine worktree of the base commit
`d28c150e` run with the identical command, which gives **175** failing. The
difference is two pre-existing failures now fixed and **no new ones**:

- `tests/domains/test_evidentiary_level_audit.py::test_every_check_in_the_domains_is_accounted_for_by_the_audit`
  was red at the base because `independent_solver_agreement` was reachable and
  had no row. It now has one, alongside the flagship's two new checks.
- `tests/test_core_guards.py::test_the_solver_discovery_found_the_adapters`
  was red at the base at 10 solvers against an expected 9. The count is now 11
  with both increments named; the 9 -> 10 step is not this sprint's and is not
  claimed to be investigated.

Two exact counts in `test_core_guards.py` moved because the sprint adds one
model: `EXPECTED_MODELS` 17 -> 18 and `EXPECTED_CONDITION_NAMES` 92 -> 97, each
with its reason recorded beside it.

### Failed approaches, recorded so they are not repeated

- **A single parameter set across all experiment groups does not fit.** Driving
  the lumped thermal model with the dissipation the *measured* voltage implies
  — no electrical parameter involved — fits every calibration cell to under 1 K
  but returns hA = 0.039-0.050 W/K for one set of test campaigns and
  0.103-0.121 W/K for another. One value fits neither, and a joint fit that
  tried produced 92 mV voltage MAE on calibration alone. The thermal boundary
  is a fixture property; a parameter set is now fitted per experiment group.
- **Fitting capacity alongside the ECM parameters is circular here.** The OCV
  authority is a curve against charge state, and the charge-state axis would
  then depend on a parameter the authority is an input to. The basis is now a
  declared constant, and the cell-to-cell capacity spread it cannot absorb is
  exactly what Gate A failed on — visible rather than hidden in a fit.
- **The calibration march and the authorized path diverged at rest.** The
  authorized path presents a current inside the composition's declared rest
  band as rest when it builds the load schedule; the fitting march did not, so
  on nine of twenty-seven calibration trajectories it reached a charge state
  above full on channel noise and contributed only a penalty. Found by the
  march-equivalence test, which requires the two to agree to 1e-12, and not by
  any holdout result. The corrected fit got a newly governed holdout evaluation
  rather than a second opening of the first; both results are reported and they
  agree.
- **A strict non-negative current predicate fires on instrument noise.** The
  rest channel scatters by a few milliamps about its own zero, so a pure
  discharge contains samples of both signs. The guardrail now uses a declared
  50 mA rest band — two orders of magnitude below the smallest calibrated load
  — in the predicate and in the schedule, so the two cannot disagree.

### One runtime correction

`MultiphysicsRuntime._scenario_schedules` tested STEP sample instants against
multiples of the nominal coupling window only, so it refused a change that does
land on a boundary cut by a scheduled event. It now checks the boundaries the
runtime actually produces. Private helper, not a frozen surface, and it still
refuses a change that falls mid-window.
