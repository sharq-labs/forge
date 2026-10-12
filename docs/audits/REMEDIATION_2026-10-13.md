# Scientific-integrity, certification and engineering remediation — 2026-10-13

**Historical snapshot** (see [README.md](README.md)). Base: `origin/main` `c4e05ee6` ("Merge test-loop optimization and
cleanup", pushed to `main` directly, not through a PR). Work: local branch `fix/remediation-2026-10-12` in worktree
`D:/forge-remed`; pristine comparison worktree `D:/forge-remed-base` (detached at `c4e05ee6`). The shared checkout
(`main` @ `a3f757eb`, 1,300+ commits behind, with uncommitted `ACTIVE_PLAN`/`PROGRESS` edits and an untracked review
file) was not touched. Nothing was committed, pushed, merged, recertified or changed in GitHub settings.

Environment: Windows 11 Pro 10.0.26200, 24 logical CPUs, CPython 3.14.2 (`.venv`), numpy 2.5, scipy 1.18. Provider
measurements: WSL2 Ubuntu, micromamba envs `fenicsx` (CPython 3.11.15) and `sci` (CPython 3.11.16). CI interpreters
3.11 / 3.12 on Windows: **NOT RUN**.

## Summary table

| Priority | Finding | Confirmed? | Root cause | Files changed | Tests | Remaining risk | Final status |
|---|---|---|---|---|---|---|---|
| P0 | Certification drift | Yes | `certification/current_core_v2.json` certifies `39d43456` (branch `fix/trust-repair-pass1`, an ancestor of `main`); 14 certified files changed afterwards in 13 commits (2026-10-09 .. 10-12), all landed without recertification | none (no regeneration) | `core_certificate.py --verify` (read-only): FAILED, 14 files / 4 areas | every commit since `39d43456` is uncertified; this branch adds `execution/sweep.py` and 8 `certified:harness` test files | BLOCKED_OWNER_RECERTIFICATION |
| P0 | Branch protection | Yes | private repo on a free User plan: protection / rulesets API 403; `main` `protected: false`; squash and rebase merges enabled; `c4e05ee6` was pushed to `main` without a PR | none | read-only `gh api` | any push lands on `main`; certificate lineage can be broken by squash/rebase | OWNER_ACTION_REQUIRED |
| P0 | `ChallengeReport.status` overstates mixed outcomes | Yes | `status` returns `survived_attempted_challenges` when any challenge survived, whatever the others; `not_challenged` when all attempted ones were INCONCLUSIVE | `claims/analysis/challenge.py` | +6 (`test_sensitivity_robustness_challenge.py`); 6/6 fail on base (incl. review M1: guard band SURVIVED on an undecided verdict, fixed) | the serialized one-word `status` keeps its old meaning (vocabulary change = owner decision OD-R1) | PARTIALLY_FIXED |
| P1 | Provider subprocess timeouts | Yes (several paths) | `ProcessWorkspace` drained pipes with an unbounded `communicate()` after the kill, so a descendant that escaped termination held a timed-out run for its full lifetime; capture unbounded in memory; launch `OSError` raw; discovery `run_provider` raised raw `TimeoutExpired`/`JSONDecodeError` and killed only the wrapper; ngspice probe ignored exit status and leaked `TimeoutExpired`; preCICE never removed its temp dir and could leave a participant running; code_aster leaked its workspace when setup refused | `providers/process.py`, `claims/discovery_providers.py`, `domains/electrical/ngspice.py`, `providers/precice/forge_precice/__init__.py`, `providers/code_aster/forge_code_aster/__init__.py` | +4 process, +5 discovery, +10 ngspice probe (ported); escaped-descendant case: base **60.1 s** for a 2 s timeout, branch returns at the timeout | see §B: escrow transports, blindfold `run_discovery`, ngspice `run()` on Windows, version probes | PARTIALLY_FIXED |
| P1 | Conservation checks | Partly | drone `coupling_balances` reported as if a balance; `winding_heat_balance_residual` is the thermal node's own law re-evaluated (0.0 K on a real run), `bus_power_balance_residual` is the last bus-voltage update times the current (−5.8e−11 W) | `systems/products/drone_coupled.py` (docstring + result note only) | existing drone tests | no independent chain balance is evaluated anywhere in drone, Thevenin, throughput fade, conduction 1D/2D, NAFEMS T3; each needs a declared, justified tolerance | SCIENTIFIC_DECISION_REQUIRED |
| P1 | Parameter-set validity | Yes | selection reads only `ModelUse.definition.validity`; no claim-path record carries parameter provenance / calibration domain / dataset identity; caller-typed parameters (battery R_int, OCV, TCR) can reach SUPPORTED with only the generic `validation.verification_only` gap. Also D3: an array input feeding a model not instanced over that array never reached validity assessment | `claims/capabilities.py` (D3 only) | +2 (`test_claims_selection.py`); D3 test fails on base | parameter-provenance visibility needs a new assessment-record field (record version decision, OD-R3); D2 (NOT_ASSESSABLE invisible to the compiler) open | PARTIALLY_FIXED |
| P1 | Sweep execution budgets | Yes | `run_sweep` has no budget; `ResourceBudget` existed but nothing enforced it for sweeps | `execution/sweep.py` (non-exported `run_sweep_within_budget`, `BudgetedSweep`) | +7 (`test_execution_sweep.py`); all fail on base | certified file: RECERTIFICATION_REQUIRED; promotion into the frozen `engcore.execution` surface is a Core Freeze decision (OD-R4) | FIXED (RECERTIFICATION_REQUIRED) |
| P1 | Model-form UQ trust | Yes — not production-ready | no capability declares MODEL_FORM; replay crashed on any record with pairs (`NameError`) and on early-stop records (`UnboundLocalError`); the bridge ignored the discrepancy protocol's verdict and dropped points of unknown uncertainty (a FAILED_VALIDATION discrepancy came out `ModelFormStatus.VALIDATED` on base) | `claims/analysis/model_discrepancy.py`, `claims/uq_studies.py` (ported), `claims/model_form_uq.py` | +10 replay (ported), +2 bridge; all discriminating ones fail on base | see §A: empty qualification registry, overlapping production split, under-covering promoted interval, no context-vs-envelope check | PARTIALLY_FIXED |
| P2 | Documentation consistency | Yes | ACTIVE_PLAN "Verified state" described `4634eba`; TESTING.md said PRs are classified automatically although every workflow is `workflow_dispatch`-only | `docs/work/ACTIVE_PLAN.md`, `docs/work/PROGRESS.md`, `docs/TESTING.md`, this report | n/a | `CLAUDE.md` "CI policy" still describes automatic classification (owner file, OD-R6) | PARTIALLY_FIXED |
| P2 | External solver performance | Measured where available | — | none | provider test suites under a metrics plugin, base vs branch | §D | see §D |

## A. Scientific integrity report

Changes that can influence a scientific outcome, each a tightening:

1. **Model-form bridge** (`claims/model_form_uq.py`). Only a `VALIDATED_CANDIDATE` discrepancy reaches the model-form
   study; every other protocol status maps to a non-promotable `ModelFormStatus` (INSUFFICIENT_DATA,
   CALIBRATED_UNVALIDATED, FAILED_HOLDOUT, UNRESOLVED) with no half-width. A point of unknown uncertainty is no longer
   dropped; on a validated candidate it raises. Before: calibration |r| = 4, known = 1; validation |r| = 6.5,
   known = 0.5 — the protocol said FAILED_VALIDATION, the bridge's 2× coverage test said VALIDATED. Latent: no
   production capability declares MODEL_FORM.
2. **Model-form replay** (ported from the reviewed, never-committed 2026-10-09 pass in `D:/forge-review-fixes`):
   `PairedObservation.from_dict` imports `Mapping`; `verify_study_records` reads the recorded qualification before
   branching, refuses a malformed one as forgery and refuses one that differs from its canonical form.
3. **Selection D3** (`claims/capabilities.py`): a declaration whose array input feeds a model not instanced over that
   array is refused. Such a value could never reach the validity assessment, so an OUTSIDE value could never be seen.
   No production declaration is affected (the production registry is constructed in a test).
4. **Challenge summary** (`claims/analysis/challenge.py`): `outcome_counts()`, `unresolved`, `outcome_summary()`
   expose attempted / survived / weakened / inconclusive / not-attempted counts and `unresolved_remain`. `to_dict()`
   and the digest are byte-identical to base (pinned in a test). The verdict is untouched.
5. **ngspice identity** (ported): a version probe that exits non-zero or times out forms no `SolverIdentity`.

6. **Guard-band challenge** (`claims/analysis/challenge.py::_guard_band`, review M1): SURVIVED only when the nominal
   verdict is decided (supported / contradicted) and unchanged under the band. An `insufficient_evidence` claim
   (electrothermal, ambient 400 K, declared ambient range) used to report SURVIVED there and, with every other
   challenge inconclusive or not attempted, the headline `survived_attempted_challenges`.

No tolerance, threshold, expected result or frozen artifact was changed. No UNKNOWN became known.

Model-form readiness (evidence-backed; no production use justified new infrastructure):

| Item | State |
|---|---|
| Capabilities declaring MODEL_FORM | none (`system.battery`, `system.electrothermal`: EPISTEMIC_PARAMETER; `benchmark.nafems_t3`: NUMERICAL; `kinetics.cstr.production`: none) |
| Trusted qualification | `PRODUCTION_MODEL_FORM_QUALIFICATIONS` is empty by design |
| Empirical records | 6 S-OCV LiFePO4 OCV observations (DOI 10.21227/651q-8v82), all pinned; **both cells appear in calibration and validation**, so the leakage guard raises `ModelFormDiscrepancyError` — uncaught by `_model_form`, contradicting "expected outcomes are records". BATT_001 at SOC 1 also set `open_circuit_voltage_at_full` in the benchmark calibration |
| Statistics | coverage is observations / validation observations with no confidence bound; n = 2 validation points; the promoted interval is ±candidate while coverage was tested at ±2×candidate |
| Applicability | `_model_form` substitutes each observation's conditions; the claim's own context is never compared with the studied envelope |
| Aggregation | linear sum of demanded channels, any unusable channel → NOT_EVALUATED (no independence assumed) |
| Drift | trust-registry digest changes are graph nodes and detected by `detect_changes` (test exists) |
| MCP | `describe_empirical_uq` would report `production_ready` on a single qualification pin despite the blockers |

## B. Security and execution report

`ProcessWorkspace` now writes each step's stdout/stderr to an unnamed temporary file instead of a pipe, waits on the
process (not on the pipes), kills the tree on timeout (`killpg` on POSIX — a vanished group is tolerated;
`taskkill /T /F` then `kill` on Windows) and reaps the direct child with a bounded wait (`REAP_TIMEOUT_S = 10`,
operational). Digests are computed over exactly the bytes as before (`sha256(b"\n".join(step outputs))`, pinned in a
test) and memory no longer grows with solver output. A launch `OSError` is a `ProviderRefusal`. `run_bounded` gives a
JSON runner the same rules; discovery `run_provider` uses it and turns timeout, launch failure and non-object output
into `ProviderRefused`. preCICE: one deadline for both participants, file capture (the old sequential pipe drain could
deadlock coupled participants), every participant killed in `finally`, the temp directory removed. code_aster: the
workspace is created where the `try` that removes it begins.

Not guaranteed, and stated in code: a descendant that leaves the process group (POSIX `setsid`) or is orphaned before
the kill (Windows `taskkill /T` follows parent links) can survive termination. It can no longer hold the caller; it can
keep running. A Windows Job Object would close this; not built.

Remaining subprocess risks (not changed here):

| Site | Risk |
|---|---|
| `blindfold/isolation.py::IsolatedEscrow.run_discovery` | blocking `readline()` / `read()` before `wait(timeout)`; sequential stdout/stderr reads can deadlock; kill reaches only `unshare`. Linux-root only; not testable here |
| `blindfold/isolation.py::IsolatedEscrow.start/stop`, `blindfold/escrow.py::SubprocessTransport` | unbounded handshake/request `readline()`; `wait(timeout=10)` raises uncaught with no kill |
| `domains/electrical/ngspice.py::run` | `subprocess.run`: on Windows a timeout kills `wsl.exe` only and then drains without bound; the domain layer does not import `engcore.providers` |
| `providers/health.py`, `providers/catalog.py` probes, `claims/replay/bundle.py` git probes, OpenFOAM `probe` | `subprocess.run` kill of the direct child only, unbounded capture (probes print little) |
| `discovery/dakota_runner.py` | `dakota -version` without a timeout (bounded now by the outer `run_bounded`) |

## C. Certification readiness report

`python tools/certification/core_certificate.py --verify` on pristine `c4e05ee6`: **FAILED**. Certified commit
`39d43456` (`fix/trust-repair-pass1`, recertified in `795042e1`; an ancestor of `main`), HEAD `c4e05ee6`; aggregate
`30702e0e…` expected, `761a6811…` actual.

| Area | File | Changed by |
|---|---|---|
| certification_control | `tests/test_mutation_population_v4.py` | `577451c7` |
| certification_control | `tests/test_skip_admission.py` | `50deced7`, `6a7c7856` |
| certification_control | `tools/certification/guard_reach.py` | `8788c9ea` |
| certification_control | `tools/certification/skip_admission.py` | `50deced7`, `d8b99d45`, `db78090b`, `0535be53` |
| certification_control | `tools/forge_check.py` | `088a8c8c`, `4118c626` |
| harness | `tests/hybrid_uq/test_hybrid_uq_identifiability_predictive.py` | `ff30a082` |
| harness | `tests/inference/test_grid_resolution_repair.py` | `577451c7` |
| harness | `tests/inference/test_tcr_heldout_uq.py` | `577451c7`, `88a258f2` |
| harness | `tests/test_core_guards.py` | `319de9a7`, `f71f66d6`, `577451c7`, `2cd4e04b` |
| harness | `tests/test_core_scientific_audit_batch24.py`, `batch25.py` | `33caf644` |
| harness | `tests/test_core_semantic_invariants.py` | `577451c7`, `88a258f2` |
| inference_admission | `src/engcore/inference/grid.py` | `8788c9ea` |
| runtime_dependencies | `pyproject.toml` | `6ae0e0a9`, `f71f66d6` |

This branch adds `src/engcore/execution/sweep.py` (area `execution_trust`) and, per
`recertification_scope explain`, `ngspice.py` (mutation target; its 3 anchors still match exactly once,
`test_r67_every_folded_mutation_still_matches_the_live_source_exactly_once` passes) and 8 `certified:harness` test
files. Prerequisites for a genuine owner-run recertification:

1. Decide the HEAD to certify (OD-3) — normally `main` after this branch lands, so one recertification covers both.
2. Python 3.12 environment (the V4 surface tests are 3.14-only failures; never regenerate the certificate on 3.14).
3. A clean tree; `tools.certification.local_assurance` source gates on 3.11 and 3.12; formal and V4 mutation
   populations; then the certificate-only child and `local_assurance verify` (`docs/assurance/LOCAL_ASSURANCE.md`).
4. Merge commits only, so the child's lineage survives.

Until then: **BLOCKED_OWNER_RECERTIFICATION**. The committed certificate is a valid historical record of `39d43456`;
it does not certify `main`.

## D. Performance report

Method. Each provider's own test module (its representative workloads; nothing new invented) run under a
measurement-only pytest plugin (`D:/remed-bench/remed_metrics.py`) that records every `ProviderExecutionRecord`'s own
`metrics` (the adapters time generate / process / parse, or setup / solve) plus process peaks from `getrusage`. WSL2
Ubuntu, envs `fenicsx` (process providers, FEniCSx) and `sci` (Python providers; SU2 / OpenFOAM, whose tests need
CoolProp). Base `c4e05ee6` and branch interleaved. "Wall" is the whole pytest process: interpreter start, imports,
discovery, collection and every test (the cold start of a provider-using process). Provider envs were found via
`FORGE_PROVIDER_ENVS=~/mm/root/envs`; nothing was installed or downloaded.

| Provider | Available | Tests (both trees) | Process wall (cold, whole run) | First record (cold call) | Median record (warm) | Peak RSS self / largest child | Leftover processes |
|---|---|---|---|---|---|---|---|
| CalculiX (process) | yes | 3 passed | 5.8 – 8.6 s | process 16 ms | process 14 ms, generate 1 ms, parse 1 ms | 261 / 261 MB | none |
| code_aster (process) | yes | 1 passed | 7.2 – 12.7 s | process 0.76 – 1.42 s | process 0.39 – 0.72 s | 236 / 338 MB | none |
| OpenFOAM icoFoam (process) | yes | 4 passed | 8.6 – 9.9 s | process 0.47 – 0.60 s | process 0.34 – 0.41 s | 208 / 208 MB | none |
| SU2 (process) | yes | 3 passed | 26.9 – 33.6 s | process 1.9 – 2.1 s | process 2.0 – 3.2 s (7 runs) | 209 / 209 MB | none |
| OpenModelica (process) | yes | 2 passed | 5.3 – 8.5 s | process 0.37 – 0.50 s | process 0.36 – 0.45 s | 117 / 115 MB | none |
| FEniCSx (in-process) | yes | 16 passed | 5.9 – 6.6 s | NOT MEASURED (no provider record in that module) | — | 236 MB | n/a |
| PyBaMM 24.1 (in-process) | yes | 4 passed, 5 skipped | 5.1 – 5.2 s | NOT MEASURED (records come from skipped tests) | — | 110 MB | n/a |
| TESPy 0.11.2 (in-process) | yes | 2 passed | 11.4 – 15.5 s | build 16 – 18 ms, solve 15 – 24 ms | build 15 ms, solve 15 – 18 ms | 205 MB | n/a |
| Cantera 3.2 (in-process) | yes | 3 passed | 4.5 – 5.8 s | setup 61 – 84 ms, solve 2 ms | setup 57 – 85 ms, solve 2 ms | 251 MB | n/a |
| CoolProp 8.0 (in-process) | yes | 4 passed | 7.0 – 7.9 s | NOT MEASURED (no record emitted) | — | 168 MB | n/a |
| Chrono, OpenRadioss, OpenVSP, preCICE | no (adapter or library absent) | skipped | NOT MEASURED | | | | |

Breakdown. On every workload here provider overhead (deck generation and output parsing, ≤ 3 ms) is two to three
orders of magnitude below the solver process (14 ms – 3 s), and both are dwarfed by process start-up and imports
(5 – 8 s per pytest process). Scientific-validation and evidence/serialization overhead were not separated on these
workloads: NOT MEASURED. Result consistency: each provider's tests assert its results against references or a second
solver and passed identically on base and branch; outputs were not separately digested and compared.

Before / after this branch (`process_s`, the part `ProcessWorkspace` owns):

| Provider | Base median | Branch, first version (file capture + `Popen.wait(timeout)`) | Branch, final (reaper thread) |
|---|---:|---:|---:|
| CalculiX (n = 9 each, final) | 14.3 ms | 20 – 23 ms (**regression**) | 14.3 ms |
| OpenModelica (n = 6 each, final) | 377 ms | 448 ms (**regression**) | 380 ms |
| OpenFOAM (n = 6 each, final) | 387 ms | 342 – 390 ms | 321 ms |
| SU2, code_aster | 2.0 – 3.2 s / 0.43 – 0.72 s | 2.0 – 2.2 s / 0.39 – 0.44 s | not re-measured |

The first version regressed short solves: on POSIX `Popen.wait(timeout)` polls with a back-off up to 50 ms, while the
old pipe drain woke on EOF. The final version blocks in a reaper thread and signals an event; the regression is gone
within noise. Expensive FEM/CFD campaigns were not run; these are small verification workloads and do not predict
production-size solves.

## E. Git diff review

`git status` in `D:/forge-remed` shows only the files listed in the summary table plus two new test modules
(`tests/claims/test_model_form_study_replay.py`, `tests/test_ngspice_version_probe.py`, both ported) and this report.
`CLAUDE.md`, certification records, frozen manifests, benchmark records and the shared checkout are untouched. The
ported changes come from the uncommitted worktree `D:/forge-review-fixes` (read, not modified). `recertification_scope
explain` classifies `execution/sweep.py`, `domains/electrical/ngspice.py` (mutation target) and 8 test modules as
RECERTIFY; everything else is ordinary. Mutation anchors on changed files still match exactly once.

Verification (this session; Windows CPython 3.14.2 unless stated):

* `python tools/forge_check.py --changed --base origin/main --workers 6` (before the review fixes): exit 1, 156
  failures. Against the saved pristine FAST failure list (`D:/forge-perf-logs/fast_base.failed`) 4 were new by name;
  run directly on both trees, 2 are parametrize-ID escaping of the same `test_formal_xdist` errors (identical on base)
  and 2 (`test_the_tree_is_core_freeze_v1`, `test_the_v3_contract_is_superseded…`) fail only on `tree.clean` because
  the branch is uncommitted; both pass on the clean base. No source-caused new failure.
* Final tree, same gate: exit 1; 9,529 tests, 136 failed, 21 errors, 181 skipped (118 s); the same 4 explained names
  are the only ones outside the pristine list (one more selected test, the Windows subprocess-escrow handshake,
  fails identically on base).
* Affected suites on the final tree: `tests/claims tests/test_execution_sweep.py tests/test_provider_boundary.py
  tests/foundations/test_v2_discovery_providers.py tests/test_ngspice_version_probe.py tests/uq/model_form`, `-n 4`:
  826 passed, 1 skipped (before the last two process fixes); after them `tests/test_provider_boundary.py
  tests/foundations/test_v2_discovery_providers.py`: 42 passed, 1 skipped on Windows and 42 passed, 1 skipped on
  Linux (WSL, CPython 3.11.16) — the skip is the pre-existing optional `psutil` check.
* Fail-before on `D:/forge-remed-base`: 15 / 20 ported tests and 20 / 23 new tests fail there (the rest are identity
  invariants meant to pass on both); the escaped-descendant test returns after 60.1 s on base.
* `tests/test_core_scientific_audit_batch55.py tests/test_core_guards.py -k "anchor or exactly_once or mutation or
  guard"`: 269 passed. `tests/test_execution_sweep.py tests/test_core_freeze_policy.py
  tests/test_core_runtime_api_surface.py tests/test_core_api_layering.py`: 72 passed.
* FAST, SCIENTIFIC, FULL, hardened recertification, Local Assurance, CPython 3.11 / 3.12 on Windows: **NOT RUN**.

Reviews (read-only `forge-scientific-reviewer`, static): round 1 CHANGES REQUIRED (no BLOCKER / HIGH): M1 fixed (an
`insufficient_evidence` claim got a guard-band SURVIVED and the headline `survived_attempted_challenges`); M2 recorded
(OD-R1); M3 recorded (RECERTIFICATION_REQUIRED, OD-R4); L2, L3, L4, L5, L7 fixed; L1 (producer-rule marker on model-form
records) and L6 (preCICE kills only the direct participant; drivers start no children) recorded. Round 2 (narrow):
PASS; its one residual (`run_bounded` read with a moving file position) fixed.

## F. Remaining owner decisions

| ID | Decision |
|---|---|
| OD-R1 | Change `ChallengeReport.status` vocabulary (e.g. `survived_with_unresolved_challenges`, and `attempted_inconclusive` instead of `not_challenged`) with tag `crafty.claims.challenge/2`, or keep the lossy headline plus `outcome_summary()` |
| OD-R2 | Branch protection: make the repo public or upgrade the plan (rulesets), or formally accept local assurance as the only merge control (OD-1); in any case disable squash and rebase merges now (available on the free plan) and stop pushing merges to `main` directly |
| OD-R3 | Parameter-set validity: add a parameter-provenance record to the assessment (new record version; historical replays must keep their identity) |
| OD-R4 | Promote `run_sweep_within_budget` into the frozen `engcore.execution` surface (Core Freeze, additive) or keep it as an implementation detail |
| OD-R5 | Conservation tolerances: drone energy-chain balance, conduction global heat balance, NAFEMS T3 energy — each needs a declared, justified tolerance before it can become a check |
| OD-R6 | `CLAUDE.md` "CI policy" says PRs are classified and `main` pushes rerun checks; every workflow is `workflow_dispatch`-only. Update the contract or restore triggers |
| OD-R7 | Model-form: an independently reviewed qualification, a cell-disjoint dataset (≥ 2 calibration and ≥ 2 other validation cells), fixing the ±candidate vs ±2×candidate coverage mismatch, and a claim-context applicability check — before any capability declares MODEL_FORM |
| OD-R8 | The rest of the stranded 2026-10-09 pass in `D:/forge-review-fixes` (B1 probabilistic-UQ sampler, B5 multiphysics import) is still uncommitted there |
| OD-3 | Hardened recertification (owner-run) |
