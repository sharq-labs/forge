# Forge Work Progress

## Approved D1/D2/D3 application and integration in progress — 2026-10-18

Owner explicitly approved the exact three corrections and resumption of bounded final integration. Proposal hashes and preimages verified against owner-analysis manifest; all three `git apply --check <exact proposal>` commands exited0, then `git apply <exact proposal>` exited0 for each. No broader source change; application and32-file preservation snapshot recorded in `.pytest-review-temp/final-integration-approved-2026-10-18/application.json`. Fresh census-before diagnostic confirmed same20 identities, sole M1C physical model0.1.0 addition, no import loss/collisions. Owner disposition status updated from actual approval/application, not inferred from file existence.

Shorter final suites executed: targeted29; discovery3; claims175; M1A/B/C124; fixed regression279; compatibility153/1 explicit Windows symlink skip. Exact commands/env/counts/wall times/failures/source indexes appended in job entries below. Task-local path observer confirms formerly unreached M1A coarsen and transfer each reach the exact issuance-key guard (line224 twice), and D1 all missing-M1/failed-M1 branches. The unified48 pack is running once with1200s timeout; result is not yet claimed. All completed jobs' before/after source hashes agree.

Separate archive diagnostic reproduced direct+registry refusal for frozen thermal.conduction1d.linear_diffusion@0.1.0 current/2 with null exclusions; direct+registry positive M1C control succeeds. Diagnostic exit0 is not compatibility PASS. Scientific impact remains UNCLASSIFIED and blocking dependent archive/readback claims; no archive behavior changed. Independent read-only reviews agree; no authority to repair reader or regenerate history inferred. No commit/push/merge/PR/OD-3/full assurance/full suite/standalone mutation campaign.

## P0 closure disposition — 2026-10-18

Final read-only checks: `git diff --check` executed, exit0 (only CRLF normalization warnings); no whitespace defects. Independent final report review:24 execution-log hashes and8 current source hashes match; all22 original failure/error cases covered exactly once. Final numerical reviewer found no remaining BLOCKER/MAJOR after reading both failure and corrected-pass traces. Review is static, not additional execution.

Owner-approved exact patches applied after independent read-only review. Final report: `docs/work/P0_SCIENTIFIC_CORRECTNESS_CLOSURE.md`; machine command/environment/hash evidence: `docs/work/evidence/p0_scientific_correctness_2026_10_18.json`.

Conservation suite:42 passed/6 failed in825.51s (826.182s wall). All failures were a new fixture confusing signed net2.75W with absolute exchange3.75W. Actual reported values0.0375/0.01875/0.009375J match approved absolute-exchange semantics. Independent reviewer confirmed; same rel1e-7 retained, production unchanged, six cases rerun6 passed in7.86s (8.466s wall). Original test snapshot and failure logs preserved. No single all48-pass rerun claimed. No normal solver case refused unexpectedly; extreme high-Fourier tests may refuse and do not establish global-gate reachability or general roundoff acceptance. Larger-mesh setup remains costly; kernel8192-entry median0.05164s is not end-to-end performance qualification.

Post-numerical bounded regression command/result and exact failing gate name are recorded in the execution entry below:277 passed/1 failed. Claims175 passed; compatibility153 passed/1 symlink skip; M1C/parent123 passed/1 M1A conservative refusal-text mismatch; discovery2 passed/1 count20-versus19 failure. Both reviewers found no remaining source BLOCKER/MAJOR; their static review is not test execution. Two report wording findings about source binding and pending numerical coverage were corrected before finalization.

All22 original failed/error cases individually dispositioned;21 claims cases now pass, gate case remains red. Final production digests captured before/after bounded/compatibility/post-numerical jobs, unchanged. Original eight-file snapshots checked against initial hashes; historical report/JSON/probe/import-smoke/conversion remain byte-identical. ACTIVE_PLAN/PROGRESS and remediation addendum preserve prior content. No count pin, certificate, historical bundle, epic/ledger, unrelated checkout or process modified; no commit, push, PR, merge, OD-3/full assurance/full suite/standalone mutation campaign. Branch proceeds to owner review only; broader readiness and owner decisions remain explicit in report.

This file is persistent engineering memory for long-running AI-assisted work.
Keep it concise and factual. Do not use it as a release note or marketing log.

## Current branch / PR

- As of 2026-10-11: `main` @ `4634eba`. Open PRs and the verified repository state are listed in
  `docs/work/ACTIVE_PLAN.md` ("Verified state"); verify GitHub before making a current PR claim.
- Previous value of this field (historical): branch `fix/big-14-review-r1-r4` (base `16c87f40`), worktree `D:/forge-r1r4`.
- Base: `main`
- Strategic contract: `docs/project/FORGE_MASTER_PLAN.md`
- Current execution authority: `docs/work/ACTIVE_PLAN.md`

## 2026-09-27 BIG 14 — 14.0 branch and baseline (read this first)

BIG 14 = Scientific Closure & Recertification (plan: `docs/work/ACTIVE_PLAN.md`). Plan committed `a2d33619`; `.gitignore` for the local Codex files
(`AGENTS.md`, `.agents/`, `.codex/`, owner decision) `f508387b`; the shared repository's `info/exclude` carries the same three lines until this merges.

### Environment inventory (2026-09-27)
- Windows core venv (`phyx/.venv`): CPython 3.14.2, numpy 2.5.2, scipy 1.18.1, Pint 0.25.3, pytest 9.1.1, xdist 3.8.0, mcp 2.1.1. NOT installed: sympy, meshio, gmsh,
  petsc4py (extras `symbolic`, `mesh`, `petsc`). 3.14 is not in any CI matrix.
- CI: Tests FAST matrix 3.11 + 3.12; recertification 3.12 (+ fast311). Installs `.[dev,mcp,oracles]` only - no `symbolic` / `mesh` / `petsc`, no provider or flagship packages.
- `pyproject.toml` advertises `requires-python = ">=3.11"` with no upper bound (3.13 / 3.14 untested in CI; 3.14 has known API-surface artifacts). Open item for 14.1.
- WSL Ubuntu micromamba 2.9.0, envs under `~/mm/root/envs`: `battery` (py3.12.14, PyBaMM 26.8.0.0, CoolProp 8.0.0, TESPy 0.11.2, meshio 5.3.5, Pint 0.26.1),
  `sci` (py3.11.16, Cantera 3.2.0, PyBaMM 24.1, CoolProp, TESPy), `fenicsx` (py3.11.15, dolfinx 0.11.0, petsc4py 3.25.5, gmsh 4.15.2, meshio 5.3.5; pyprecice
  metadata reports `0.0.0` while PROGRESS BIG 9 records preCICE 3.4.0 - the library version needs re-reading from the library, not the wheel metadata),
  `calculix` (`ccx`), `code_aster` (py3.14.7, `run_aster`), `openfoam` (`simpleFoam`, `icoFoam`), `su2` (`SU2_CFD`), `openmodelica` (`omc`); `/usr/bin/ngspice`.
- `tools/wsl_env.sh` hardcodes `R=/mnt/d/forge-b13` (the BIG 13 worktree): a committed tool pinned to one machine's worktree path. Open item.

### Baseline measurements on `a3f757eb` (pristine worktree `D:/forge-b14-base`, Windows venv 3.14.2)
- `TMPDIR=D:/ftmp14 PYTHONPATH='D:\forge-b14-base\src;D:\forge-b14-base' .venv/Scripts/python.exe -m pytest -m "not expensive" -q -n 4 --basetemp=D:/fbt14b -p no:cacheprovider -rfE`
  -> **23 failed, 8788 passed, 61 skipped, 15 errors in 301 s** (exit 1). Sorted failing ids: `D:/forge-b14-logs/fast_base.failed`.
- `python tools/forge_check.py --regression --workers 4` -> **225 passed in 9.7 s** (exit 0).
- `git diff --check` on the branch -> clean. Base worktree stayed clean after both runs.
- `forge_check.py --changed` NOT RUN as a baseline (no changed files; it would select only the architecture pack).

### CI state read from GitHub (sharq-labs/forge), not re-run
- PR #109 was MERGED with `recertification-gate` = FAILURE (fast311, fast312, scientific312, campaign312, formal_mutations_0-3 failed; v4_mutations_0-7 and
  trust_mutations succeeded; certify skipped). Tests `tests-gate` on the PR = SUCCESS because the classifier routed it to recertification and skipped fast.
- `main` push runs: Tests has FAILED on every push in the last 30 (latest a3f757eb, e3ae778a, 2b76017f, deabe5cb, 9b9693eb). FAST (3.11/3.12) was last green at
  `9361b97c` (2026-09-16); it went red at `9b9693eb` (PR #103). `reproduce` (Docker) has failed on every listed push (not part of `tests-gate`).
- Branch Policy on `main` FAILS: "POLICY NOT ENFORCED: no status checks are required; ['recertification-gate', 'tests-gate'] must be" (bypass actors unreadable
  without admin permission). This is why red gates did not block merges. Repository settings; code cannot fix it.
- CI FAST 3.11 and 3.12 at a3f757eb: 17 failed + 15 errors, identical to each other and to SCIENTIFIC. Local baseline = CI set + 6 local-only 3.14 failures.
  Mutations job: "CONTROL RED -- ROUND VOID: the copied tree fails with NO mutation applied" (3 failed) - the baseline failures void the round.
- Attribution by the first main push that showed each failure (FAST 3.12 lists compared push by push):
  - since `9b9693eb` (PR #103): the 2 `test_core_certificate` failures;
  - since `e3ae778a` (BIG 2-9 merge): freeze-policy, 2 core-guards, semantic-invariants, 3 numerical-foundation, 2 spatial-core, and 3 provider collection errors;
  - since `a3f757eb` (BIG 10-13, PR #109): 12 more provider/flagship collection errors and the 6 `test_flagship_portfolio` failures.
  (`deabe5cb` had 54 more failures; `2b76017f` / PR #106 fixed them.)

### Classification of the 38 local baseline failures
1. **15 collection errors + 6 `flagships/tests/test_flagship_portfolio.py` failures - test infrastructure, AUTHORITY-RELEVANT.** `forge_flagships` and every
   `forge_<provider>` adapter package are not importable in the core environment (they are separate distributions; the WSL runs put them on PYTHONPATH by hand).
   The portfolio tests are provider-free and are the pins of BIG 13's pre-registered criteria and reference records: **every CI run since they were added
   fails to import them**, so the pre-registration is enforced by nothing in CI. Provider suites belong to their provider environments and must skip, not error, elsewhere.
2. **`test_core_semantic_invariants::test_every_reader_that_writes_a_schema_also_checks_one` - product defect, AUTHORITY-RELEVANT (serialization/replay).**
   12 `from_dict` readers check no schema: `ParticipantStateContract` (coupling/adapters.py), `GatheredInput` (scenarios/lifecycle.py), `SpatialField`
   (spatial/fields.py), `RepresentativeWindow` (multiscale/windows.py), `AuthorityCheckpoint` (system_runtime/result.py), `EnvelopeBound`,
   `PredeclaredCriterion`, `ReferenceComparison`, `ReferenceCondition` (engineering/reference.py), `EvidenceLink`, `LevelEntry`, `VerificationLadder`
   (engineering/ladder.py). Each must either check its schema or be shown to be nested-only (no schema of its own, read through a parent that checks one).
3. **`test_core_freeze_policy::test_the_policy_names_every_non_core_package` - stale governance document.** `docs/CORE_FREEZE_POLICY.md` does not classify
   `materials`, `numerical`, `spatial`, `pde`, `coupling`, `providers`, `multiscale`, `system_runtime`, `engineering` (all registered non-Core in
   `tests/test_core_api_layering.py`).
4. **`test_core_guards::test_the_domain_names_were_derived_from_the_packages_not_listed` - stale pinned list.** `corrosion` and `hygrothermal` (BIG 4/5) are not listed.
5. **`test_core_guards::test_the_bare_install_the_readme_documents_is_the_one_that_must_be_green` + 3 `test_numerical_foundation` + 2 `test_spatial_core` -
   optional-dependency boundary defect.** `numerical/providers.py` (petsc4py), `numerical/symbolic.py` (sympy), `spatial/providers.py` (gmsh, meshio) reach for
   optional extras the guard allows only in `mcp/server.py`; five tests hard-require sympy/meshio and fail (not skip) on the bare CI install.
6. **2 `test_core_certificate` failures - stale certificate (assurance).** Areas certification_control, core, execution_trust, harness,
   predictive_representation, routed_uncertainty and runtime_dependencies have moved since the certificate. Needs the hardened recertification workflow on
   3.12; must not be regenerated locally on 3.14.
7. **6 local-only failures (`test_core_freeze_manifest` descendant, `test_core_freeze_v3_manifest` V4-binds, 3 `test_core_freeze_v4_manifest`, batch56 r69) -
   unsupported environment.** `api.deep_surface_is_the_live_one` / `api.manifest_records_this_comparison` differ only under 3.14 (inherited builtin methods);
   they are absent from CI 3.11/3.12. Same class as the drift recorded 2026-09-18.
- External-policy blocker (not a test): the `main` ruleset does not require `tests-gate` / `recertification-gate`. Only the repository owner can set it.
- Pre-existing environment failure (not gating): Docker `reproduce` - 128 failed, mostly `no repository root ... expected a directory holding both .git and
  pyproject.toml` (the image has no `.git`), plus 11 ngspice oracle failures inside the image.

### Baseline stop-gate decision
Classes 1, 2 and 6 can alter evidence admission / replay identity / assurance, and the ruleset blocker means a red gate cannot stop a merge. 14.2/14.3 flagship
evidence work stays blocked until 1, 2, 3, 4, 5 are repaired on this branch and 6 has a recertification run; the ruleset needs the owner.

## 2026-09-28 BIG 14 — flagship A: first comparison against measured LG M50 cells (branch `feat/big-14-flagship-a`)

The user chose flagship A for deep closure work. The work so far is below. Every study was pre-registered in a pushed commit before its first run.

### NASA PCoE is not applicable to flagship A's cell
- Flagship A runs PyBaMM's Chen2020 set, which models the LG M50 (21700, 5 Ah, NMC811/graphite-SiOx).
- The NASA PCoE cells are 2 Ah 18650s: a different cell. Comparing them would test the wrong cell.

### Data: Chen 2020 LG M50 validation discharges
- Source: Zenodo 10.5281/zenodo.4032561, CC-BY-4.0, 1.8 MB. Downloaded with the user's approval; the md5 of every file equals Zenodo's.
- Vendored in `benchmarks/measurements/chen2020_lgm50/` (`raw/` byte-exact with `-text`; `manifest.json` pins sha256).
- Content: 3 cells, CC-CV to 4.2 V then CC discharge at C/10, C/2, 1C and 1.5C, with surface and chamber temperature, 30 s sampling.
- Data-only facts, recorded before registration:
  - capacity 4.93-5.00 Ah, agreeing within 0.2 % between cells;
  - cell-to-cell voltage spread 0.9-5.8 mV RMS;
  - surface-temperature spread 0.2-1.5 K;
  - peak surface rise over the chamber up to 31 K at 1.5C.
- Chen2020 facts found:
  - the heat-transfer coefficient is a generic 10 W/m2K default;
  - only the exchange-current densities carry an Arrhenius term; transport has no temperature dependence.

### Study `big14-a-lgm50-validation`
- Pre-registered at `4656f339`; runner `13a5f647`; the JSON-record crash fixed at `2d09a0b3` (no computation changed).
- Result: NOT MET on all three cells.
  - SPM at C/2 (the flagship's rate): voltage RMSE 149-153 mV against <= 17 mV; capacity +3.1 % against <= 2 %.
  - Peak-rise T1 is met: -0.8, +0.4 and -1.6 K.
  - The calibrated h is 3.555 W/m2K; the cell02 1C temperature RMSE is 0.47 K.
- The run was repeated and was identical. Record: `docs/flagships/big14/lgm50_validation_study.json`.
- Labelled post-hoc diagnostic (`docs/flagships/big14/diagnostic_normalized_axis.py`). On a capacity-normalised axis the error is still 44-49 mV at C/10, so it is not capacity alone:
  - an equilibrium (electrode-balance / OCV) offset;
  - a rate-growing SPM model-form error: 156-169 mV for SPM against 75-87 mV for DFN at 1.5C.
- Independence of this data from the Chen2020 parameterisation stays UNCONFIRMED. It needs the paper text, and reading the PDF needs the user's approval.

### Study `big14-a-lgm50-electrode-balance`
- Pre-registered at `87c7a9ec`. Two active-material factors were calibrated on cell02 at C/10 only.
- Calibrated factors: negative 0.9798, positive **0.8500, which is the lower bound**. The optimum may lie outside the registered range.
- Held-out C/10 on cell03 and cell04: 11.8 mV, so the correction transfers across cells.
- Result at C/2: NOT MET.
  - SPM: 33-38 mV against <= 17 mV. Capacity +0.4-0.5 % meets C1.
  - DFN, reported and not judged: 14.7-18.7 mV.
- New at high rate: capacity is now under-predicted, -8 % at 1.5C. This is consistent with the declared missing temperature dependence of transport.
- Record: `docs/flagships/big14/lgm50_balance_study.json`.

### Study `big14-a-representative-day`
- Pre-registered at `31c10f2d`. Result: MET in both cases.
- Question: does the published 4-of-56-day representation reproduce a run that resolves every day?
- Record: `docs/flagships/big14/representative_day_study.json` and `representative_day_runs.jsonl`.
- Published run minus the 56-day reference:

  | Quantity | normal | hot |
  |---|---|---|
  | fade | -0.00070 (-1.33 %) | -0.00132 (-1.17 %) |
  | end-of-discharge voltage, aged | +0.48 mV | +0.91 mV |
  | peak cell temperature, aged | -0.0002 K | 0.0000 K |
  | min SOC, aged | +0.00039 | +0.00084 (84 % of the 0.001 tolerance) |
  | degradation voltage shift | +0.48 mV | +0.91 mV |

- Every quantity converges monotonically, and the error halves with each halving of the macro step (normal fade, x1e-6: -697, -322, -161, -54, 0). This is a first-order bias from holding the fade constant within a macro step.
- Wall time: 75 s for the 4-day run, 639 s for the 56-day reference.
- The representative-day approximation error is no longer UNKNOWN: it is measured for these two cases.
- Caveat (found by the parallel session): in the hot case peak_cell_temperature_aged is 323.950001 K in every run. It occurs at rest (0 A) and
  equals the coolant-inlet peak, so it is set by the environment and does not test the approximation there.
- The cell-energy check and the heat-of-mixing test are recorded below (entries `big14-a-cell-energy-check` and `big14-a-heat-of-mixing`).

### Data independence: the Chen 2020 paper read (`big14-a-chen2020-independence`)
- Record: `docs/flagships/big14/chen2020_independence.json`. Read from the open-access article's HTML full text in a browser. The IOP and Birmingham PDF
  endpoints returned bot-detection pages; they were not bypassed and nothing was downloaded.
- Answer: NOT independent. Chen2020 tuned the diffusivities, the maximum concentrations and the positive 100 % SOC stoichiometry by trial and error
  against the C/2, 1C and 1.5C discharges of the same three cells (1C first, then the negative diffusivity again per rate: 1.3e-14 at C/2, 6.3e-14 at 1.5C).
  PyBaMM ships the 1C column (checked in the battery env). C/10 is not named in the tuning.
- Consequences:
  - the two NOT MET LG M50 results stand, and they are stronger negatives, because the model misses its own tuning data;
  - any MET on these curves is in-sample and likely optimistic, and the out-of-sample error stays UNKNOWN;
  - the paper's licence is CC BY-NC-ND 4.0 (the dataset's CC-BY-4.0 is separate).

### Study `big14-a-lgm50-dfn` (the owner's DFN decision)
- Pre-registered at `64093638`; runner `91a0b66b`; run 2026-09-28 in the WSL battery env with a clean tree.
  Command: `python -m forge_flagships.lgm50_dfn --out /mnt/d/forge-b14-logs/dfn_study` (exit 0, 180 s).
  Record: `docs/flagships/big14/lgm50_dfn_study.json`.
- Classification: C/2-1.5C are Chen2020's own tuning data, so this is in-sample consistency, not validation.
- Result: PRIMARY NOT MET.
  - V1 met on all three cells: DFN C/2 voltage RMSE 16.5 / 16.9 / 13.6 mV, against SPM 33-38 mV.
  - C1 met on all three: +0.27 to +0.36 %.
  - T1 missed on cell02 and cell04: the model rise is 4.8 K against 7.5 and 8.3 K measured. cell03 passes (6.3 K measured).
- Identification:
  - balance factors: negative 0.9800, positive 0.8539, both interior to [0.70, 1.20], objective 9.85, 63 evaluations;
  - h = 18.12 W/m2K on cell02 1C (T RMSE 2.0 K). It was 3.555 for SPM without mixing: the heat of mixing is 35-40 % of DFN's heat.
- Decision rule applied as registered:
  - flagship A carries the two factors, labelled as identified, not measured;
  - it does not carry h;
  - the model-form band at C/2 is 13.6-16.9 mV voltage RMSE and -3.5 to -1.5 K peak-rise error, measured in-sample and likely optimistic.
- Reported, not judged:
  - 1C and 1.5C voltage RMSE 54-61 mV;
  - 1.5C capacity -7.7 to -7.9 % (stated limit: no Arrhenius term on diffusion);
  - C/10 cell03/cell04 9.6-9.9 mV (the calibration transfers between sibling cells).
- Post hoc, not a registered finding: the model's rise scales more steeply with rate than the measurement (C/2 : 1C : 1.5C = 0.33 : 1 : 1.86, against 0.46 : 1 : 1.66).
  That is the signature of a heat term linear in current, which points at the absent reversible (entropic) heat. Chen2020 has no entropic data.

### Flagship A switched to DFN; review; check `big14-a-cell-energy-check-dfn`
- Switch (`ab1c8370`, owner decision): `battery_cooling.MODEL = "DFN"`, `CELL_OPTIONS = {"heat of mixing": "true"}`.
  - The balance factors are read from the pinned `lgm50_dfn_study.json`. The decision is re-derived through `lgm50_dfn.judge` / `decision`.
  - Level 7 is now ATTEMPTED, NOT REACHED, with the in-sample, not_met cell comparison as its evidence.
  - `forge_pybamm.coupling.cell_participant` gained `model_options` and `balance` (`51a6513a`). A run of the pre-change `coupling.py` beside the new one gave
    identical state identity, execution identity and heat for SPM and DFN with defaults.
- `forge-scientific-review` of the switch: CHANGES REQUIRED.
  - M1 (the record's decision was trusted field by field) is fixed in `0640e1af`: the record digest is pinned and its judgement and decision are re-derived, with 8 tamper tests.
  - L1: the default execution payload is pinned.
  - L2: the level-7 and report prose is derived from the record.
  - L6: the band's rig context is stated.
  - L5 led to the check below.
  - L3: the "held-out" rows are held out from this study's identification only; they are in-sample to Chen2020. The committed record keeps its label and the runner is unchanged, so it still reproduces the record.
  - L4: the record lacks the PyBaMM version and input digests; the new DFN energy record carries them.
  - L8: the flagship reads `docs/flagships/big14/`, so an installed wheel fails closed.
- `cell_energy_check.py` now names SPM explicitly: its registration and committed record are for the SPM cell.
  The representative-day and window studies call `build_flagship`, so re-running them at HEAD runs DFN. Their records are SPM-era (commits in their entries).
- Check `big14-a-cell-energy-check-dfn`: pre-registered at `45719e11`, runner `0640e1af`.
  Command: `python -m forge_flagships.cell_energy_check_dfn --out /mnt/d/forge-b14-logs/edfn`, battery env, rc 0.
  Record: `docs/flagships/big14/cell_energy_check_dfn.json`.
  - Result: NOT MET. The bulk-OCV identity closes to 0.886 % at 300 K (met) and 1.104 % at 313.15 K (missed; the tolerance is 1 %).
  - The surface identity misses by 36.4 / 42.4 %, which equals the heat-of-mixing share (36.3 / 42.0 %).
  - The registration's stated limit named the expected source of a residual: U of the averaged concentration is not the average of U across a DFN electrode.
    That is not tested here and stays an explanation, not a finding.
  - The report states the result under Known limitations.
- Test runs:
  - battery env `test_pybamm_coupling_options.py`: 19 passed.
  - the flagship's M1 tests (`-k "pinned or refused or derived_from_the_record"`): 13 passed.
  - the full `test_flagship_battery.py` on `ab1c8370`: 11 passed, 1 failed (`test_window_refinement_meets_the_tolerances_but_not_the_monotone_requirement...`: it pins SPM's window outcome; updated after the bundles are regenerated).

### Flagship A regenerated on DFN
- `python -m forge_flagships.reports battery --docs docs/flagships --bundles docs/flagships/runs`, battery env, on `4b3141ca` + the review fixes (rc 0, 15 min, every bundle re-verified).
  The four battery bundles, `battery_cooling_lifecycle.md` and BUNDLE_DIGESTS were updated together.
- Normal / hot, SPM before -> DFN now (model outputs; every uncertainty UNKNOWN):

  | Quantity | normal | hot |
  |---|---|---|
  | degradation voltage shift | -33.7 -> -36.2 mV | -73.7 -> -76.8 mV |
  | fresh-day module heat removed | 28.8 -> 69.0 Wh | 15.0 -> 55.6 Wh |
  | fresh end-of-discharge voltage | 3.4948 -> 3.4009 V | not listed |
  | peak cell temperature, fresh | 301.28 -> 301.82 K | not listed |
  | fade | 0.0518 -> 0.0519 | 0.1118 -> 0.1120 |

- The degradation shift is now about 2x the cell model's in-sample C/2 voltage error (13.6-16.9 mV). Under SPM it was about equal to the error (33-38 mV).
  The comparison is in-sample, so this is a necessary condition only.
- Window refinement under DFN: successive differences decrease (monotone met), but the finest-pair peak-heat difference (13.3 mW) is outside its 2 % tolerance.
  Level 4 stays ATTEMPTED, NOT REACHED; the cause is not investigated.
  The test that pinned SPM's opposite outcome was rewritten to the observed DFN outcome, with the history kept in its docstring.
- `flagships/tests/test_flagship_portfolio.py` (venv): 35 passed.
- Battery env, `python -m pytest flagships/tests/test_flagship_battery.py --import-mode=importlib -q` on the regenerated tree: 22 passed (23.6 min).
- After merging feat/big-14-reviews (`4ed62b12` and its docs follow-ups), venv: `python tools/forge_check.py --changed`: 225 passed, rc 0.

### Consequence for flagship A (open decision for the owner)
- The flagship reports a degradation voltage shift of -34 mV at C/2.
- The SPM it uses has an error of 33-38 mV against the measured cells at that rate, even after the balance correction. As built, the flagship cannot support that claim.
- DFN with the identified balance comes close to the 17 mV bar.
- Proposal, to be decided by the owner:
  - move flagship A's cell model from SPM to DFN;
  - re-register the identification with a wider bound, because the positive factor hit its bound;
  - enable the heat of mixing;
  - carry the measured model-form bands instead of UNKNOWN: about 35 mV voltage for SPM, about 15-19 mV for DFN after the balance correction, and 2-3 K cell temperature at C/2.

### Check `big14-a-cell-energy-check` (BIG 13 review M5)
- Pre-registered at `b0814b83`; record `41cc1822` (`docs/flagships/big14/cell_energy_check.json`). Numerical verification of the model's heat bookkeeping, not validation.
- C1 MET at both temperatures: the cell's total heating equals I*(U_surface - V) + reversible heating to 2.9e-10 (300 K) and 4.5e-10 (313.15 K) relative.
- Reported, not judged: the heat of mixing PyBaMM leaves out by design is 83 % (300 K) and 128 % (313.15 K) of the heat it counts.
- The reversible heat is 0 because Chen2020 carries no entropic coefficient. That channel is ABSENT from the model, so its size is UNKNOWN; it is not a measured zero.

### Test `big14-a-heat-of-mixing` (hypothesis Hc)
- Hc: the low calibrated h (3.555 W/m2K) compensates for the omitted heat of mixing. Post-hoc hypothesis from the two results above, first registered test at `70d4d996`; record `c3c0f4b9`.
- Hc SUPPORTED as registered: P1 h recalibrates to 10.741 W/m2K (+202 %, bar +20 %); P2 held-out mean |peak-rise error| 2.13 -> 1.92 K.
- Not uniform, recorded so the mean does not hide it:
  - the calibration curve (cell02 1C) fits worse: temperature RMSE 0.47 -> 1.70 K;
  - C/2, the flagship's rate: peak-rise error worse on all three cells (cell02 -0.81 -> -2.52 K, cell03 +0.37 -> -1.32, cell04 -1.58 -> -3.26);
  - 1.5C: better on cell02 (-4.19 -> +0.40) and cell04 (-7.68 -> -3.05), worse on cell03 (-1.74 -> +3.04).
- Reading: with the heat of mixing the fitted h is near Chen2020's generic 10 W/m2K default. That makes h a compensating parameter in the baseline; it is not evidence that 10 W/m2K is right for the rig.
- Nothing here validates the thermal model; the reversible heat stays absent.

### Study `big14-a-window-study` (diagnosis of BIG 13 criterion 1)
- Pre-registered at `c2195c0b`; run 2026-09-28 at `c3c0f4b9`, WSL `battery` env, `python -m forge_flagships.window_study --out /mnt/d/forge-b14-logs/big14a/window` (exit 0, 5 runs, 12-33 s each).
  Record `docs/flagships/big14/window_study.json`. Numerical diagnosis of the same model; not validation.
- The BIG 13 differences reproduce: peak T 0.0032 K (3600->1800) then 0.0080 K (1800->900).
- H1 SUPPORTED as registered (pre-asymptotic quantity definition, not a coupling defect):
  - P1 met for all three quantities: the differences peak at 1800->900 and then fall; ratio of the last two 1.66 (peak T), 1.64 (end voltage), 1.57 (peak heat); bar 1.5.
    Peak T: 0.0032, 0.0080, 0.0060, 0.0036 K.
  - P2 met: the gap to the dense in-hour maximum heat (0.16987 W) shrinks monotonically: 9.4, 9.2, 6.3, 4.0, 2.6 mW.
- Limits:
  - the ratios (~1.6, not 2) show the approach is slower than first order; one extra halving would test that, and it was not registered;
  - H0 was not tested directly; P1/P2 are only consistent with H1;
  - BIG 13 criterion 1 stays NOT MET as registered then; this study does not re-judge it;
  - the largest difference (0.008 K) is under the flagship's own 0.05 K refinement tolerance, but the published 3600 s window under-reads the resolved peak heat by 5.5 % (0.1605 against 0.1699 W).
- Independent replay (second session, 2026-09-28, same env, `python -m forge_flagships.window_study --out /mnt/d/forge-b14-logs/window_study`, exit 0, H1 supported):
  every recorded value (three quantities, dense heat maximum, window count, verdict) is bit-identical to the committed record. Only `wall_s` and
  `result_digest` differ; the system result digest hashes `resource_usage.wall_seconds` (`system_runtime/result.py`), so it is not a replay identity.

## 2026-09-28 BIG 14 — owner decisions carried out: state reads, applicability disclosure, main ruleset, Pint (branch `feat/big-14-reviews`)

The owner said "do the three". The three were: `reads_owners`; undeclared applicability; the gates on `main`, the PR and the Pint decisions.

### What was done
- **`main` ruleset: CONFIGURED, NOT ENFORCED (corrected the same day).** Ruleset "Protect main" (id 23351506) was set to require
  `tests-gate` and `recertification-gate`, and at that moment `branch_policy` reported OK. The repository was later made PRIVATE on a free plan,
  and GitHub disables rulesets for that case. Re-checked as sharq-labs: `private: true`; `GET /rulesets` and `/rules/branches/main` return 403
  "Upgrade to GitHub Pro or make this repository public"; `branch_policy` fails with the same 403. **A red gate cannot block a merge now.**
  Owner decision: make it public, or upgrade. The configuration below is what takes effect when rulesets are available again.
  - Source is GitHub Actions, app 15368.
  - Strict up-to-date is on, merge commits only, no bypass actors.
  - Approvals stay 0. With a single owner account, a required approval would block every merge. `docs/assurance/BRANCH_PROTECTION.md` asks for 1; this is a stated deviation.
  - `python -m tools.certification.branch_policy --repository sharq-labs/forge` reported **OK** at configuration time (bypass actors unverified). It now FAILS with the 403 above.
  - Both workflows run on every `pull_request` with no path filter, and both gates end in `if: always()`, so a required gate always reports.
- **BIG 12 R2 / (d)-2, `246098fc`: state reads are declared edges.**
  - `NodeSpec.reads_owners`, carried on `PlanNode`. It is omitted from the wire when empty, so no stored request, plan or result digest moved.
  - Each node gets a `StateView` limited to the owners it reads or writes. The state clock is visible to committing nodes only; the chain fields are never visible.
  - `compile_plan` refuses:
    - a writer and any node that sees its owners, with no path between them;
    - any two committing nodes with no path between them, because they share the clock.
  - An UNKNOWN value in a visible owner is an UNKNOWN input, for both outputs and state proposals.
  - The built-in multiphysics and multiscale authorities refuse, in preflight, mapped owners the node does not declare (`UNDECLARED_STATE_READ`).
  - A read owner must exist in the initial state.
  - None of the 8 committed flagship requests needed a change. Only `aging` commits state, and the multiphysics nodes map no owner.
- **BIG 12 (b): undeclared applicability.** `undeclared_applicability(result)` is derived from the plan the result carries, and `trust_handoff` names those nodes in its notes.
  - No stored field was added, so no stored digest moved.
  - Mandatory declare-or-waive for output nodes is NOT enforced. It would be a request-contract change needing a regeneration.
- **U-05, `b07a58f1`.** The claims replay environment is `claim_replay_environment/2` and binds `units.registry_fingerprint`.
  - A `/1` bundle still VERIFIES as a record.
  - Exact replay needs `/2`. A `/1` bundle, or one made under other unit definitions, is NOT_REPRODUCIBLE.
  - No stored claims bundle is committed.
- **U-04.** `pint>=0.25.3,<0.27` in `pyproject.toml` and `requirements.txt`: exactly the measured versions (0.25.3 locally, 0.26.1 in CI and the battery env).
- **The PR.** It comes from `feat/big-14-flagship-a` after the other session merges this branch and pushes its DFN bundles. That session owns its CI, so a push does not cancel a running recertification.

### Reviews
- **Implementation review: CHANGES REQUIRED.**
  - M1: the clock and chain fields still leaked across unordered committers of different owners.
  - M2: an intact `/1` claims bundle read as TAMPERED.
  - LOW: a read owner was not checked; docstring; test gaps; a recursive `upstream()`.
  - All fixed. The M1 and M2 tests fail when their fix is reverted by hand.
  - The m6 and d1 tests now declare `depends_on=("thermal",)`. The ordering rule makes the dependency, not the taint, what blocks. The taint stays as defense in depth.
- **Focused re-review: CHANGES REQUIRED.** M1, M2 and the LOW fixes hold. The committer-ordering rule breaks no existing request. One latent MEDIUM:
  a committer could rewrite the provider checkpoints of owners it does not write, because the whole tuple was replaced.
  - Fixed, `feat/big-14-reviews` tip: foreign-owner checkpoints are refused, and checkpoints are merged BY OWNER. `None` still means unchanged.
  - Mutation-checked: with the refusal removed, the new test fails.
  - Two direct filter tests added.
  - Accepted residual (LOW): a node's execution identity still hashes the whole state digest. An unordered non-committing node's identity and
    cache key can therefore depend on the tie-break (not the values it sees). Changing it would move stored receipt identities; picked up with N3.

### Executed
- `pytest tests/test_system_runtime_*.py tests/test_engineering_*.py tests/claims flagships/tests -n 4` -> **889 passed, 39 skipped** (final tree).
- **CI PR #116 (`ad292325`), fast311 only:** 3 failures in `tests/claims/test_impact_replay.py`, each with the difference "stored replay environment: source-control dirty-tree state is unavailable". fast312 and scientific312 passed the same tests on the same commit. Cause: `_git_bytes` ran `git status` with a 2 s timeout, which a loaded runner exceeded. Fail-closed, but it makes a required gate flaky. Fixed: `GIT_PROBE_TIMEOUT_S = 30`, pinned by a test; a hung git still reads as UNAVAILABLE. `pytest tests/claims -n 4` -> 627 passed.
- WSL `battery` env on `4ed62b12`: `pytest providers/pybamm/tests/test_system_runtime_battery.py providers/pybamm/tests/test_pybamm_provider.py flagships/tests/test_flagship_battery.py` -> **28 passed**, exit 0.
- Full FAST tier `pytest -m "not expensive" -n 4` on the pre-M1 tree -> 10 failed, 9021 passed, 118 skipped.
  - Two of the ten (`test_the_tree_is_core_freeze_v1`, the V3 supersession check) failed only because the tree was dirty during the run. On the committed tree `b07a58f1` both **pass**.
  - The other 8 are baseline classes: 2 stale-certificate failures (class 6, need recertification) and 6 Python-3.14-only failures (class 7).
  - The a3f757eb baseline had 38 failures and errors.

## 2026-09-28 BIG 14 — 14.1 review debt: BIG 12 re-review, BIG 13 round 5, BIG 11 second re-review (branch `feat/big-14-reviews`)

Branch `feat/big-14-reviews` in worktree `D:/forge-b14-review`, cut from `origin/feat/big-14-flagship-a` @ `814e1492`. Ownership: this line = 14.1 review debt;
the flagship A science line is the other session's, on `feat/big-14-flagship-a` in `D:/forge-b14`, which merges this branch.
Four read-only `forge-scientific-reviewer` runs, static reading only (the reviewers ran no tests). After them, a review of this fix batch and a focused re-review of its second round.

### Reviews and verdicts
- **BIG 12 final fix batch (`21a2c75c`): CHANGES REQUIRED.** 1 HIGH, 7 MEDIUM, 7 LOW.
- **BIG 13 round 5 (`ac600555`): CHANGES REQUIRED.** 1 HIGH, 3 MEDIUM, 4 LOW.
  - F6 wording: no occurrence called a bundle "authenticated". Some sentences over-claimed what `verify_bundle` re-derives.
- **BIG 11 second re-review: CHANGES REQUIRED.** 1 HIGH, 1 MEDIUM, 4 LOW.
- **F-1 / F-2 `catalog._footprint` re-review: PASS.** LOW B1-B4 only.
- **Review of this fix batch: CHANGES REQUIRED.** 2 MEDIUM, 5 LOW; no guard was removed. All were fixed.
- **Focused re-review of those fixes: CHANGES REQUIRED.** One new MEDIUM, introduced by this batch: the `_state_mismatch` inner loop shadowed
  its `start` argument, so a second slow-owner domain raised (it failed closed: every two-domain run was falsely refused). Fixed, with a
  two-domain test on the fresh and resume paths. Its LOW notes (empty `unassessed_models`, in-memory reference data) were fixed too. The
  prefix rule and the wall-budget taint were confirmed; the N1-residual deferral was accepted on the conditions stated under "Deferred".

### Fixed (each with an adversarial test that fails on the unfixed code; the counts were checked by stashing the source change)

BIG 12, in `src/engcore/system_runtime`:
- **(a) HIGH, model selections.** A model selection was a request label, and it became `provenance.models`, the list the credibility layer reads as "what executed".
  - `trust_handoff` now refuses every `validity` record. No caller passes one.
  - `provenance.models` is now `()`. The labels move to `metadata["requested_model_selections"]`.
  - `trust_handoff` notes that executed models are unreported, so an empty `unassessed_models` means unknown, not "all assessed".
  - The real binding (authorities report the models they executed) is DEFERRED; see "Deferred" below.
- **R1, constraint binding.** Preflight now checks that the pinned definition's name is the constraint the node assesses. Before, a second declared constraint of the same dimension stood in for it.
- **N1, checkpoint after a failure.**
  - A checkpoint taken after a node did not succeed is now incomplete.
  - `verify_checkpoint` refuses any checkpoint whose completed set is not a prefix of the plan. The completeness flag alone is editable.
- **N2, MultiscaleAuthority ignored the committed state.**
  - A fresh stage refuses when the committed slow owner differs from `initial_slow_state`.
  - A resume stage refuses when it differs from the slow state of the macro checkpoint it continues.
- **(c), resume stages.**
  - A resume stage must name its `from` stage and depend on it.
  - The held checkpoint must come from that stage; `restore()` clears the origin until `restored_from()` names it.
  - `"from"` enters the authority identity only when present, so existing identities do not move.
- **(d)-1.** A committing node refused by the wall budget now taints later commits.
- **LOW.**
  - The authority checkpoint completeness flag is a strict boolean on `NodeOutcome` and `NodeReceipt.from_dict`.
  - An authority that cannot be resolved now fails `verify_checkpoint`; it was skipped before.

BIG 13 round 5, in `src/engcore/engineering`:
- **F1 HIGH, provider comparisons (partial).** A level-5 comparison must name two executions that the result recorded under two DIFFERENT provider ids, with labels that name those providers.
  - This refuses two OpenFOAM meshes relabelled "openfoam"/"su2". The test is a consistent rewrite of the committed `cavity_re100` bundle.
  - `post_hoc` and `within_tolerance` must be booleans, the relative tolerance numeric zero, and `max_absolute` canonical finite non-negative text.
- **F2.** No blank entry in any uncertainty list. No "none"-like entry in the UNKNOWN list ("none" in the KNOWN list is honest and stays).
- **F3.** The traced observable must be a key output.
- **F4.** The full `bundle_digest` and `summary_digest` of all 8 committed bundles are pinned in `flagships/tests/test_flagship_portfolio.py`. Regenerating a bundle must update the pin.
- **F5.** Reference readers take only the exact `repr` text `to_dict` writes. In memory, a number must be `numbers.Real` and not a bool.
- **F7.** Cavity level 5 with every comparison missing is ATTEMPTED_NOT_REACHED with the missing links.
- **F8.**
  - The status basis is a constant.
  - The summary has a strict key set.
  - A malformed manifest or plan is `BundleRefused`.
- **F6 wording.** `bundle.py`, `engineering.md`, `docs/flagships/README.md`, and `__main__.py` ("self-consistent (unkeyed manifest; not authenticated)").

BIG 11, second re-review:
- **A1 HIGH.** `forge_pybamm.segments_from_records` held a segment-start ambient as known when the channel was UNKNOWN inside the segment: NONE interpolation, a gap past `max_gap`, extrapolation, validity ending, or a discontinuity. It now also requires both records to be KNOWN 1 ms before each segment ends. Flagship A's INTERVAL_HISTORY channel was not affected.
- **A2 MEDIUM.** `OutputSelection` must be an affine combination: finite weights >= 0 summing to 1, and distinct non-negative indices. A zero map made any two records agree.

### Deferred, with reasons (not fixed; do not read as closed)
- **BIG 12 (a), binding.** Authorities do not report the models they executed. Until they do, no validity record is accepted through `trust_handoff`.
- **BIG 12 R2 / (d)-2, state reads (MEDIUM).** State reads are not DAG edges. A non-committing node can read an UNKNOWN or stale state and output a quantified value. The fix is a declared `reads_owners` on `NodeSpec`, with the planner ordering readers after writers. That changes how every flagship builds its nodes, so it needs a design decision. It is the next BIG 12 item.
- **BIG 12 (b), applicability (MEDIUM).** Output-only nodes need no applicability declaration, and none is disclosed. The fix is a re-derived `TrustInputs.undeclared_applicability`. It moves stored result digests, so it needs a version decision.
- **BIG 12, recorded LOW.**
  - (d)-3 `blocked_by` holds sentences.
  - (d)-4 derived-node cache reuse has no trace link.
  - (e) the waiver text and the `within` evidence digest are only format-checked.
  - R5: a loaded result does not tie `state_history` to its receipts.
  - N3 and the N1 residual: a complete checkpoint taken BEFORE a refusal can be resumed and re-roll the refused node, and a forger can
    truncate an incomplete checkpoint's tail to a consistent earlier prefix. Either way the result records no resumed-from link. This gives
    no more power than a fresh rerun, but the traceability gap is real. The resumed-from checkpoint digest on the result is the first item
    to pick up with N3. Until then, nothing downstream may treat a resumed result as an uninterrupted one.
- **BIG 13 F1(b), provider comparisons (documented limit).** Completeness and pre-registration are flagship records, not run artifacts, so a consistent rewrite that drops a failing comparison or re-classifies a post-hoc one verifies. The same holds for the comparison inputs (maximum difference, selections, same declared problem). The committed bundles are anchored by the F4 pins.
- **BIG 13, recorded limits.**
  - F2: the UNKNOWN list is not derived from the request.
  - Key outputs can be pruned.
- **BIG 13 M7.** The study and limit requests are not shipped, so their provider bindings are not compared with the main request. Already stated in `engineering.md`. DEFERRED to BIG 15 graph-level V&V.
- **BIG 11, LOW.**
  - A3: a hand-built `ProviderExecutionRecord` is still accepted by `ProviderAuthority`. It cannot become support while validity is refused.
  - A4: the library environment digest differs from the conda digest of the same prefix.
  - A5: values and unit can come from different entries.
  - A6: CalculiX region-name case collisions.
  - B1-B4 of the footprint review.

### Executed (this session; Windows core venv 3.14.2; `TMPDIR=D:/ftmp14r`, `PYTHONPATH='D:\forge-b14-review\src;D:\forge-b14-review'` plus `flagships` and `providers\pybamm` where needed)
- New regression files; every one of these tests fails with the source change stashed:
  - `tests/test_system_runtime_rereview_fixes.py` 13 passed (all fail with `src/engcore/system_runtime` stashed; the two-domain test fails on the shadowed loop);
  - `tests/test_engineering_round5_fixes.py` and the ladder test: 28 of the new cases fail unfixed (the other 12 were already refused);
  - `tests/test_big11_second_rereview_fixes.py` 15 passed / 15 fail unfixed;
  - the A1 test in `providers/pybamm/tests/test_pybamm_provider.py` DID NOT RAISE unfixed.
- `pytest tests/test_system_runtime_*.py tests/test_engineering_*.py tests/test_big11_*.py tests/test_provider_boundary.py tests/test_core_semantic_invariants.py tests/test_core_guards.py tests/test_core_api_layering.py tests/test_repository_architecture.py flagships/tests providers/pybamm/tests/test_pybamm_provider.py -n 4`
  -> **695 passed, 45 skipped, 0 failed** on the final tree (the skips are provider suites outside their environments).
- `python tools/forge_check.py --regression --workers 4` -> **225 passed**, exit 0.
- `python tools/forge_check.py --changed` -> 40 passed (architecture pack only), exit 0.
- WSL `battery` env from `D:/forge-b14-review`, `pytest providers/pybamm/tests/test_system_runtime_battery.py flagships/tests/test_flagship_battery.py`: **19 passed**, exit 0.
  - Some engineering edits landed during this run, so it was repeated on the final tree with
    `providers/pybamm/tests/test_pybamm_provider.py` added: **28 passed**, exit 0.
- NOT RUN: full FAST, full SCIENTIFIC, mutation populations, hardened recertification, and the other provider suites (OpenFOAM, SU2, CalculiX, Code_Aster, Cantera, FEniCSx).

## 2026-09-27 BIG 14 — 14.1 continued: PR #110 merged red, probe semantics, Units U-01..U-03, env re-check (PR #111)

- PR #110 (commits up to `86fa1896`) was MERGED at 17:26 UTC by the sharq-labs account while `recertification-gate` was red. Cause of the red:
  every formal mutation shard reported `CONTROL RED -- ROUND VOID` because `tests/mutation_guards.py` copies only `_COPIED` (no `flagships/`,
  `providers/`) and the new src->adapter guard asserted a non-empty set there. Fixed in `40cd5d75` (skip with the reason when neither tree exists);
  local harness `python tests/mutation_guards.py D:/fm14 G1a`: CONTROL GREEN 1139 passed, 1 skipped; G1a killed. Follow-up PR #111.
- Provider probe (`83791695`, `c1833e90`): exit code must be in `accepted_exit_codes` (default 0, validated non-empty non-negative ints); CalculiX
  declares 201 (measured in WSL: `env -i PATH=<env>/bin ccx -v` prints `This is Version 2.23`, exit 201, three runs); OpenFOAM's own probe requires
  exit 0 (`icoFoam -help` exits 0, three runs) and no longer raises out of `status()`; `status(refresh=True)` drops `_PY_ENV`; flagship / CalculiX
  suites fail on a `version probe of` refusal.
- Units U-01..U-03 (`92147e0b`, `c1833e90`, Core `scientific/units/quantity.py`): no `float()` pre-coercion in `from_dict` / `coerce_quantity`;
  `_require_numeric` for scalar `*` `/`; bool, numpy bool, numpy arrays of bool/text/bytes, text, bytes, memoryview refused; a number (incl. numpy
  numeric) is never a unit, numpy TEXT still is; the B26a/B26b-pinned constructor line is byte-identical.
- Review F2 (`ProcessInvocation.conda_environment`): a conda environment changed after discovery is refused at launch; all 9 adapter invocations
  declare it (static test). Operational only: `ProcessInvocation.to_dict` / digest unchanged.
- Scientific review of probe + units: CHANGES REQUIRED (F1-F3 MEDIUM, F4-F7 LOW) -> all fixed except the documented residuals (conda digest covers
  package records, not files edited in place; U-04 / U-05 are owner decisions).

### Executed
- FAST (3.14, `-n 4`) on `c1833e90`: 8 failed, 8907 passed, 118 skipped (344 s); the same 8 known failures (class 6 certificate, class 7 3.14-only).
- Units contract (`tests/test_units_type_boundaries.py`, units suites, batch26): 352 passed on Pint 0.25.3 (Windows) and 0.26.1 (WSL `battery`).
- Apply/revert: units 12/12 killed (incl. certified B26a/B26b); OpenFOAM exit-code mutant killed (WSL); F2 3/3 killed.
- WSL real process providers through the launch check: `battery` env openmodelica + su2 + openfoam 7 passed; `fenicsx` env calculix + code_aster
  3 passed (all tests those suites have). `default_registry`: calculix 2.23, code_aster 18.1.7, openmodelica 1.27.1, su2 8.5.0, openfoam v2412.
- NOT RUN: SCIENTIFIC tier, hardened recertification (CI on #111).

### Re-review of `c1833e90` / `5b66cbe3` (CHANGES REQUIRED) and fixes
- F1, F4-F7 FIXED; F2 FIXED for process providers; F3 was partial -> completed with `ProviderStatus.found_but_refused` (a present provider whose
  adapter / probe / version read failed), used by the CalculiX, OpenModelica and flagship suite guards.
- N1 MEDIUM (new): library providers imported their library at execution without checking it was the one discovery bound, and the plan item had
  been ticked with only the process fix -> FIXED: `require_library_unchanged(status)` in Cantera `_solution`, CoolProp `resolve`, PyBaMM `run`,
  TESPy `solve`. First version re-scanned sys.path (58-146 ms per call in WSL); now distributions are located once per process and their RECORD /
  METADATA re-read per check (1.1-3.1 ms); an upgrade (replaced dist-info) reads as absent and is refused.
- LOW fixed: L1 OpenFOAM hashes each executable once (identity digest = launch digest); L2 its executables must resolve inside the checked prefix;
  L3 the static adapter test requires a `conda_environment_of(...)` value; L4 a workspace is spent once a sequence starts; L5 unreadable
  environment records refuse, and Code_Aster derives the check before creating its workspace; L8 numpy magnitudes must be integer/real kinds
  (complex, object, timedelta refused), `array.array` refused, and no `numbers.Number` is a unit; L9 refresh drops `_LOCATED` / `_PY_ENV` (tested).
- LOW recorded: L6 a process provider found on PATH (no `FORGE_PROVIDER_ENVS`) binds no environment even when it lives in one (incomplete, not
  false); L7 the conda digest does not cover system tools reached through PATH.
- Executed: local affected suites 1130 passed, 103 skipped; apply/revert 8/8 killed (N1 x3, F3, L4, L8 x2, L9); WSL real providers: openmodelica +
  su2 + openfoam 7 passed, calculix + code_aster 3 passed, pybamm + coolprop + tespy 14 passed, cantera 3 passed.

### Re-review of `faf8d77c` (CHANGES REQUIRED: M1, M2 MEDIUM) and fixes
- M1: the battery flagship's PyBaMM path (`forge_pybamm/coupling.py::cell_participant` / `advance`) formed identities without the check -> FIXED; an
  AST rule now requires every identity-forming function in a library adapter to call the check ITSELF (a closure runs long after its
  constructor's check). Cantera's `_identity` checks too.
- M2: the check read the disk, not the module in memory (a refresh after an in-process upgrade re-bound the new version while the old code
  still ran; a shadowing checkout / editable install passed) -> FIXED: in-memory module location and `__version__` (first token; TESPy appends a
  release name) must match, a per-process pin (`_IMPORTED_UNDER`, never cleared) refuses a module first imported under another discovery, and
  discovery refuses a module whose origin is not one of its distribution's files. LOW-b (unreadable metadata refuses) and LOW-c (adapters name
  the package; the status is not trusted to say it) fixed; LOW-g positive float16 / longdouble / uint8 / 0-d array magnitudes tested.
- Recorded, not fixed: LOW-a `found_but_refused` is reason-prefix based; LOW-d FEniCSx does not use this check (it records the loaded dolfinx
  version); LOW-e undeclared execution-time dependencies unbound; LOW-f the static process test trusts the name `checked_environment`; LOW-h
  Code_Aster can leave a temp workspace if its invocation constructor refuses.
- Executed: provider boundary 25 passed, 3 skipped; affected suites 829 passed, 103 skipped; apply/revert 7/7 killed (a first version of the AST
  rule let a dropped per-window check survive -> rule tightened, then killed); WSL `battery` env all PyBaMM suites incl. the coupling path +
  coolprop + tespy 24 passed, 0 skipped (146 s); `sci` env cantera 3 passed. FAST on `faf8d77c`: 8 failed (the known 8), 8935 passed.
- Gotcha: `_IMPORTED_UNDER` is per process, so tests that pin the same package under different statuses must isolate it (monkeypatch).

### Re-review of `d0294654` (M1 FIXED, M2 PARTIAL -> MEDIUM residual) and fix
- Residual: declared dependencies (CoolProp under TESPy, casadi / pybammsolvers under PyBaMM) were checked on disk only, and the pin was keyed on
  the package's combined digest -> FIXED: pins are per DISTRIBUTION (package + each declared dependency, `(version, RECORD digest)`), a declared
  dependency's module in memory must carry the bound `__version__`, and a package not yet imported must now resolve (`find_spec`) to the
  discovered location (LOW-a).
- Declared limit (operating rule, in the code comment and the plan): a provider-environment change takes effect in a NEW process; a same-version
  rebuild of a module already in memory cannot be detected from inside the process.
- Correction of an earlier record: FEniCSx is NOT covered by the library check and the thermo-mechanical flagship binds the registry status, not
  the loaded dolfinx version; `require_library_unchanged(status, "dolfinx")` would falsely refuse (distribution `fenics-dolfinx`). Open item.
- LOW recorded: the static identity-forming rule hard-codes four packages (FEniCSx omitted) and accepts a check placed after the solve;
  modules without `__version__` get the location check only; the probe's origin check realpaths every RECORD entry (discovery only).
- Executed: provider boundary 25 passed, 3 skipped; apply/revert 4/4 killed; WSL battery env all PyBaMM suites incl. coupling + coolprop + tespy
  24 passed (139 s), sci env cantera 3 passed. FAST on `d0294654`: 8 failed (the known 8), 8936 passed.

- CI on faf8d77c / d0294654: formal mutation control VOID again, now from GUARD 19 (`test_every_dependency_the_tree_reaches_for_is_declared`): two
  new tests in `tests/test_provider_boundary.py` imported `forge_calculix` / `forge_openfoam`, which the harness copy (no `providers/`) cannot
  resolve. Moved to `providers/calculix/tests/test_calculix_descriptor.py` and `providers/openfoam/tests/test_openfoam_descriptor.py`. Local
  harness `tests/mutation_guards.py D:/fm14 G1a`: CONTROL GREEN 1139 passed, 1 skipped; G1a killed.

### Re-review of `0f18bd2b` / `aa1accf1` (MEDIUM N-1) and fix
- N-1: a declared dependency's LOAD LOCATION was never bound (a shadowed / editable CoolProp was refused as its own provider but admitted under
  TESPy's identity) -> FIXED: at discovery and at execution every top-level module of the package and of each declared dependency must load from
  that distribution's own files; a distribution that lists no module files (conda-installed casadi: no RECORD) is bounded by its install root and
  bound through the conda package record in the python-environment digest. LOW 1 (the not-yet-imported refusal) now has a test that fires it; LOW 3
  (`find_spec` raising) refuses.
- Failed approach (caught by the real WSL run, not by the core suite): the first version required module files to be LISTED, which made PyBaMM
  UNAVAILABLE in the `battery` env (casadi lists none) - and 15 PyBaMM tests SKIPPED silently because the library provider suites had no
  `found_but_refused` guard. Both fixed: the install-root rule, and the four library provider suites now fail on a present-but-refused provider.
- Cost: the first version re-ran `find_spec` per call (37-110 ms in WSL); lookups for not-yet-imported modules and `top_level.txt` are now
  resolved once per process (cleared by refresh, consistent with the new-process operating rule): 0.3-0.9 ms per call, first call 38-114 ms.
- Executed: provider boundary 25 passed, 1 skipped; provider + flagship suites 76 passed, 103 skipped; apply/revert 4/4 killed (runtime and
  discovery dependency origin, install-root footprint, package origin); WSL battery env all PyBaMM suites incl. coupling + coolprop + tespy
  24 passed (145 s), sci env cantera 3 passed. FAST on `aa1accf1`: 8 failed (the known 8), 8936 passed.

### Re-review of `88e7bc81` (M-1, M-2, M-3 MEDIUM) and fixes
- M-1: module names came from `top_level.txt` (setuptools only) and a module that could not be found read as clean -> modules are now DERIVED from
  the distribution's own files (underscore modules included).
- M-2: the install-root fallback admitted any distribution without a file list (egg-info in a checkout, develop installs) -> a distribution's
  footprint is its RECORD module files, else the conda package record that installed its dist-info (exact file list; casadi's lists 261 files),
  else EMPTY and refused at discovery and execution. No `commonpath` any more (the Windows cross-drive `ValueError` is gone).
- M-3: the probe filled the execution-time origin cache, so a shadow appearing between discovery and the first import passed -> discovery resolves
  uncached; every adapter re-checks right after its import (then the module is read from `sys.modules`), pinned by an AST rule.
- LOW: the remaining PyBaMM suites (multiscale, multiphysics, system-runtime battery) fail on a present-but-refused provider.
- Executed: provider boundary 27 passed, 1 skipped; providers + flagships + guards 344 passed, 103 skipped; apply/revert 6/6 killed (two first
  survivors were test gaps: an already-imported `pluggy` hid the discovery-cache path, and no test executed with an unestablished footprint);
  WSL battery env all PyBaMM suites incl. coupling + coolprop + tespy 24 passed (149 s), sci env cantera 3 passed; check cost 0.4-0.9 ms per
  call after a 49-113 ms first call. FAST on `88e7bc81`: 8 failed (the known 8), 8937 passed.

### Re-review of `b5462cd2` (F-1, F-2 MEDIUM) and fix - review loop closed here
- M-3 FIXED; M-1 / M-2 PARTIAL: F-1 an editable (PEP 660) dependency's RECORD lists only a `.pth` (+ finder), so its real package was never
  checked; F-2 `Distribution.files` falls back to SOURCES.txt, so a checkout egg-info got a footprint and a file-name-only digest -> FIXED: the
  footprint is the PARSED RECORD (never `dist.files` fallbacks), else the conda record, else empty; `direct_url.json` editable -> empty; a
  distribution from which no module can be derived is refused at discovery and execution. Tested with on-disk fixtures (editable dependency with
  finder; checkout egg-info with SOURCES.txt); apply/revert 2/2 killed (the F-2 mutant re-run from a script file with a compile check, because
  a heredoc-built mutant can be a syntax error that "kills" for the wrong reason).
- Real environments on this code: WSL `fenicsx` env FEniCSx AVAILABLE (0.11.0, conda dependencies via the conda-record path), fenicsx suites
  29 passed; `battery` env PyBaMM suites incl. coupling + coolprop + tespy 24 passed; `sci` env cantera 3 passed. FAST on `b5462cd2`: 8 failed
  (the known 8), 8939 passed. CI on `88e7bc81`: fast311 / fast312 / scientific312 / campaign312 / regression312, all v4 and trust mutation
  shards SUCCESS; formal shards past their control round.
- DECISION: this provider-identity sub-area had seven review rounds, each finding a narrower installation mode. The loop is closed here; the F-1 /
  F-2 fix is NOT re-reviewed and is carried as an explicit plan item into the next review batch, with the recorded LOW residuals.

### Gotchas
- A test under `tests/` must not import a `forge_*` adapter package: the certified mutation harness copies only `_COPIED` and GUARD 19 then
  reports it as an undeclared dependency, voiding every formal shard. Re-run `python tests/mutation_guards.py <scratch> G1a` (control round)
  after changing what `tests/` imports.
- The Bash tool halves backslashes inside heredocs: a Python patch passed through `<<'EOF'` turned `"\n"` into a real newline and broke a string.
  Write patch scripts with the Write tool and run them as files.
- `ids=repr` on parametrized `memoryview` / `object()` values puts a memory address in the test id; xdist workers then collect different tests.
- An open PR in this repository can be merged within the hour while red; push a coherent state before opening one.

## 2026-09-27 BIG 14 — 14.1 baseline repairs (classes 1-5) and three review rounds

Commits on `feat/big-14-scientific-closure` (none pushed): `cd8e71f7` class 1, `d2de31d1` classes 3-5, `7c9e7f7a` class 2, `1ae83bd2` `tools/wsl_env.sh`,
`a7f5723d` review round 1 fixes, `29900d60` review round 2 fixes, then the round-3 L1 fix and this entry.

### What changed
- Class 1: pytest `pythonpath` gains `flagships` and the eleven `providers/<name>` roots, so the flagship and adapter suites collect in the core env; the
  BIG 13 pre-registration pins now execute. Provider-free refusals skip per test, not per module (preCICE, CoolProp, PyBaMM). First-party adapter/flagship
  imports are no longer wrapped in `except ImportError/Exception` or `importorskip`; suites that use `default_registry()` assert no needed adapter failed to
  import/register (its reason would start with `adapter `).
- Class 2: `SpatialField.from_dict` checks `spatial_field/1` + classification; `verify_bundle` checks `summary.json`'s `SUMMARY_SCHEMA` before any nested
  ladder / comparison record is read. All nested-schema exemptions (20 older + 11 BIG 9-13) are file-qualified, must write no schema, and the 11 new ones
  must be read only by their schema-checking parent (call sites resolved through imports, aliases, re-exports, module-qualified and uncalled references,
  `getattr`). `RepresentativeWindow.from_dict` has no reader in the tree and must stay so.
- Class 3: `docs/CORE_FREEZE_POLICY.md` classifies nine more non-Core packages (23). Class 4: derived domain list adds `corrosion`, `hygrothermal`.
- Class 5 / optional extras: meshio absence now refuses with ProviderUnavailable; SymPy/meshio/PETSc/SUNDIALS refusals carry the import error;
  sympy-free NumericalProblem / SciPyRootProvider refusals run on the bare install (declared-identity problem); the bare-install guard proves each optional
  import is lazy and refused (try BODY with a refusing or recording handler, or an availability refusal before it, or a gated `NumericalProvider._execute`),
  pinned by 14 synthetic sources; GUARD 19 resolves `src/` names against `src/` only; a new guard refuses any `src/` import, adapter-name string, bare
  `forge_` prefix or `KNOWN_ADAPTERS` use outside the guarded discovery.
- `tools/wsl_env.sh` derives the checkout root (`FORGE_ROOT` overrides) instead of `/mnt/d/forge-b13`.
- New provider-free tests: forge_pybamm never-default refusals (gap-as-rest, change inside a segment, UNKNOWN current at 3600 s - the last had no test);
  `default_registry` missing-package and failing-register branches.

### Executed (this session; Windows core venv CPython 3.14.2 unless stated; TMPDIR=D:/ftmp14, `PYTHONPATH='D:\forge-b14\src;D:\forge-b14'`)
- FAST `python -m pytest -m "not expensive" -q -n 4 -p no:cacheprovider`:
  - `1ae83bd2`: 8 failed, 8818 passed, 124 skipped, 0 errors (293 s). `a7f5723d`: 8 failed, 8830 passed, 116 skipped. `29900d60`: 8 failed, 8846 passed,
    116 skipped (301 s). The same 8 each time, none new against the baseline list: 2 `test_core_certificate` (class 6, needs 3.12 recertification) and the
    6 Python-3.14-only V4 API-surface tests (class 7). Baseline had 23 failed + 15 errors.
- Affected suites after round 2 (`tests/test_core_guards.py tests/test_core_semantic_invariants.py tests/test_numerical_foundation.py tests/test_spatial_core.py
  tests/test_provider_boundary.py tests/test_engineering_contracts.py flagships/tests providers`, `-n 4`): 508 passed, 106 skipped.
- WSL `fenicsx` env (sympy, meshio, gmsh present) `tests/test_numerical_foundation.py tests/test_spatial_core.py`: 35 passed, 0 skipped.
- WSL real providers (`source tools/wsl_env.sh`, `-m "not expensive"`): `battery` env `providers/pybamm/tests/test_pybamm_provider.py providers/coolprop/tests`
  12 passed, 0 skipped (72 s); `fenicsx` env `providers/precice/tests` 6 passed.
- Apply/revert (scripts in `D:/forge-b14-logs/`, outside the repo; each mutant applied, the named test run, the bytes restored and compared):
  class 2 2/2 killed; round-1 counterexamples 5/5 killed; round-2 counterexamples 8/8 killed (su2 adapter register raising -> cavity flagship collection
  fails; aliased / module-qualified / getattr / re-export reads of nested ladder and comparison records; deleted gap-as-rest refusal; computed `forge_`
  import; `KNOWN_ADAPTERS` reuse).
- NOT RUN: SCIENTIFIC tier, mutation populations, hardened recertification, CI on this branch (nothing pushed).

### Scientific review (read-only `forge-scientific-reviewer`), dispositions
- Round 1 on `a3f757eb..1ae83bd2`: CHANGES REQUIRED (1 HIGH, 4 MEDIUM, 3 LOW). F1 HIGH the sympy skip hid bare-install NumericalProblem refusals -> FIXED.
  F2 src could import `forge_*` as first-party -> FIXED. F3 lazy-import claim unenforced -> FIXED. F4 nested exemptions unproven, RepresentativeWindow not
  honestly exempt -> FIXED. F5 provider-free tests behind module skips -> FIXED. F6/F7/F8 -> FIXED (completed in round 2).
- Round 2 on `a7f5723d`: CHANGES REQUIRED (4 MEDIUM, 4 LOW), no authority leak. N1-N8 all FIXED in `29900d60`.
- Round 3 on `29900d60`: PASS, no new HIGH/MEDIUM. LOW residuals:
  - L1 `test_every_adapter_is_unavailable_not_an_import_error_without_its_stack` accepted an adapter import failure -> FIXED (asserts no `adapter ` reason).
  - L2 `forge_precice` is in `KNOWN_ADAPTERS` but has no `descriptor.py`, so "precice" always reads as an adapter failure in `default_registry()`.
    NOT FIXED: adding a capability descriptor is provider work outside BIG 14's bounded scope; `test_default_registry_never_raises...` excludes it by name.
  - L3 lazy-import rule does not follow calls from class bodies / default arguments / other module-level functions, and accepts a handler that binds None and
    falls back after the `try`. None of these exists in the four provider modules. NOT FIXED (static-analysis completeness).
  - L4 the call-site resolver follows re-exports only through parent packages (not `summary` / `multiscale.fast` re-bindings), misses local rebinding,
    `type(x).from_dict`, star imports; neither it nor the `src/` adapter scan has an in-tree synthetic self-test (the apply/revert evidence is outside the
    repo). NOT FIXED; the in-tree lazy-import rule does have synthetic cases.
  - L5 `default_registry` can raise "already registered" if an adapter registers then fails - loud, not silent. Accepted.
  - L6 PROGRESS lacked this record -> this entry.

### Failed approaches / gotchas (do not repeat)
- In a bash loop building PYTHONPATH, `"...\\providers\\$(basename $d)"` escaped the `$` and produced literal `$(basename ...)` entries; use forward slashes
  (`D:/forge-b14/providers/$(basename $d)`) with `;` separators.
- `ast.walk` over an annotated assignment includes the annotation: `tuple[str, ...]` contributes an `Ellipsis` constant. Walk `node.value` only.
- `default_registry()` turns ANY adapter import/register exception into UNAVAILABLE; a test that only reads `available` cannot tell a defect from an absent
  stack. Check the reason prefix `adapter `.
- A bare-name exemption in `test_core_semantic_invariants.py` also covers every other class with that name (`ReferenceCondition`, `RouteComparison`,
  `ArtifactRef` each exist twice); qualify by file.
- The pyproject `pythonpath` change and the edits to `tests/test_core_guards.py` / `tests/test_core_semantic_invariants.py` move certified areas
  (runtime_dependencies, harness): class 6 recertification must run after these commits, on 3.12 in CI, never regenerated locally.

## BUILD-phase entries (BIG 2 to BIG 13) — archived

The 1163 lines of per-milestone entries from the 2026-09-25 P0.1 triage through BIG 13 (2026-09-26) were
moved verbatim to `docs/work/archive/PROGRESS_BUILD_PHASE_BIG2_TO_BIG13.md` on 2026-10-09. Their failed
approaches still apply; search that file before retrying a BUILD-phase technique.

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


## 2026-09-28 strategic decision — motion systems and electromechanical product behaviour

The post-hardening design roadmap now treats machine motion as first-class
engineering behaviour, not as an incidental property of CAD assemblies.

Strategic additions:

- restored the design-synthesis / buildable-assembly architecture on a current
  branch from `main`;
- added `docs/architecture/motion_systems.md`;
- future product synthesis explicitly includes kinematics and multibody
  dynamics, mechanism topology, joint limits, trajectories and inverse
  dynamics;
- springs, dampers, bushings, flexures, suspension elements, friction,
  backlash, compliance, vibration and contact are explicit future capability
  families;
- actuation includes electric, hydraulic, pneumatic and cable/tendon options
  where supported, plus transmissions and actuator sizing;
- electromechanical coupling includes motor electrical behaviour, losses,
  temperature feedback, sensing and control;
- wiring/harness design includes conductor/wire type, gauge/cross-section,
  insulation/rating, voltage drop, heating, connectors/protection, bend radius,
  routing, strain relief and provenance where data is available;
- robot arms, suspensions, grippers and machines are to be evaluated as dynamic
  assembled systems rather than collections of ideal hinges;
- the strategic Master Plan is extended through P36, while BIG 14/15 remain the
  active hardening/UQ work and are not displaced.

Tests: **NOT RUN** — documentation/strategic architecture changes only.


## 2026-09-28 strategic decision — global 3D engineering viewer

The post-hardening product/design roadmap now includes a dedicated global 3D
engineering visualization runtime immediately after parametric CAD/topology.

Recorded direction:

- P25 is the Global 3D Engineering Viewer + Scene Runtime; later future phases
  shift by one and validated design discovery becomes P36;
- Three.js is the initial web rendering provider, behind a provider-neutral
  Forge Scene IR rather than a Scientific Core dependency;
- whole vehicles, drones, machines, motors and robot systems should be viewable
  hierarchically with progressive level of detail;
- required inspection modes include normal, transparent/X-ray, section/cutaway,
  exploded, exact dimension/annotation, motion and scientific-overlay views;
- a motor may combine transparent/cutaway motion playback with electrical,
  thermal and limits/margin overlays;
- failure/risk visualization is downstream of authoritative models, applicable
  limits, uncertainty and evidence. A renderer cannot infer burnout/safety from
  colours or geometry;
- large-product scenes should stream subsystems/details rather than requiring
  every detailed component and analysis mesh at once;
- visualization remains downstream of authoritative product/CAD/simulation
  records and cannot become a second source of scientific truth.

Tests: **NOT RUN** — documentation/strategic architecture changes only.


## 2026-10-07 Local Assurance control-plane optimization

Scope: WSL /home/dev_kaeem/forge-local-assurance-72bf7c4c at
74e102a743fe7cf329353b7aa32e56b5cbc0940c. Full assurance, certification,
mutation populations, push, PR and merge explicitly deferred by user.

Command: `.forge/venvs/3.12/bin/python -m pytest tests/test_local_assurance.py -q`
Result: 8 failed, 14 passed in 0.64s. Failure names: all eight parametrizations
of test_shards_are_bounded_isolated_and_fail_closed. Failed approach: new owner
assertion compared underscore gate names with established hyphenated directory
identity; corrected assertion without changing deterministic evidence paths.

Command: `.forge/venvs/3.12/bin/python -m pytest tests/test_local_assurance.py -q`
Result: 29 passed in 1.30s.
Command: `.forge/venvs/3.12/bin/python -m pytest tests/test_local_assurance.py tests/test_mutation_population_v4.py tests/test_hardening_assurance.py tests/test_recertification_scope.py tests/test_branch_policy.py tests/test_certificate_lineage.py -q`
Result: 213 passed in 22.36s. Synthetic/mock concurrency only; no mutation
population or full assurance executed.
Independent review identified logged subprocess stream exceptions leaving a
child alive past shard cleanup and inaccurate local sequential/job wording.
Fixing process-group termination/reaping and execution metadata; rerun required.

Command: `.forge/venvs/3.12/bin/python -m pytest tests/test_local_assurance.py tests/test_mutation_population_v4.py tests/test_hardening_assurance.py tests/test_recertification_scope.py tests/test_branch_policy.py tests/test_certificate_lineage.py -q`
Result: 214 passed in 22.87s after process-group cleanup/metadata fixes.
Re-review found forced-kill ProcessLookupError could replace original stream
failure during a timeout race; guarded disappearing-group kill and added mocked
reaping/error-preservation regression.
Command: `.forge/venvs/3.11/bin/python -m pytest tests/test_local_assurance.py -q`
Result: 31 passed in 1.26s.
Final independent forge-scientific-review verdict: PASS (read-only review only).
All three reported control-plane findings addressed; no scientific/domain code
changed. Resume design documented; resume NOT implemented.
Failed tooling approach: Windows default text encoding corrupted existing
PROGRESS prose during append and later refused decode. Restored original HEAD
bytes and kept only new session entries; subsequent writes explicitly UTF-8.

Command: `.forge/venvs/3.12/bin/python -m pytest tests/test_local_assurance.py tests/test_mutation_population_v4.py tests/test_hardening_assurance.py tests/test_recertification_scope.py tests/test_branch_policy.py tests/test_certificate_lineage.py -q`
Result: 215 passed in 22.46s; 0 failed, 0 skipped.
Command: `git diff --check`
Result: PASS (exit 0).
Full FAST, SCIENTIFIC, campaign, regression, Formal/V4/Trust mutation
populations and Full Local Assurance: NOT RUN BY DESIGN.
Official certificate generation, certificate-only child, push, PR, merge: NO.
Final status: CONTROL_PLANE_READY_FOR_FURTHER_REVIEW.


## 2026-10-07 Local Assurance optimization pass 2 - implementation/static review

Base: 8d5eed3f47a0490d481b7ff5c9927f2f944096db; clean WSL checkout on arrival.
User forbids all test/project execution, smoke checks, assurance, benchmarking,
performance measurements and certification. TESTS_RUN: 0. All added test
specifications: NOT RUN. Prior pass results do not apply to these changes.

Implemented per-shard independent pristine seed + persistent worker, complete
SHA-256 byte/path/type/mode manifest, incremental restoration and poisoning on
failed restoration. V4 retains .git and original JUnit attribution; Formal
retains _COPIED, control-first order and guard mechanism attribution. No
population/expectation/shard changes. Helpers and future specifications are
registered in certification_control; no certificate is regenerated.

Performance schema forge.local_assurance_performance/1 denies certification
and SAFE_TO_PUSH authority. Local metadata resides in sibling performance/,
outside official evidence/ and its manifest. No real timings were collected.

Static review found that signaling a process group did not confirm descendant
termination and could miss setsid escape. Failed approach: group kill + leader
wait was insufficient for persistent reuse. Replaced it with Linux subreaper
ownership, exclusive per-shard target execution, kernel child enumeration and
confirmed reaping; inability to drain poisons the round and retains external
storage. The local parent respects retained workspaces instead of blindly
removing them. These changes are unverified by execution; lifecycle test
specifications are written only. Independent static re-review pending.

No scientific/domain code, thresholds, solver behavior or mutation definitions
changed. Resume: NOT implemented. Full Local Assurance: NOT_RUN_BY_DESIGN.
Certificate generation, push, PR and merge: NO. Changes remain uncommitted for
further review under this implementation-only request.

Independent static re-review: no remaining actionable findings in scope;
source-only verdict PASS under dedicated sequential Linux shard ownership.
Not test execution or scientific validation. Review and residual assumptions
recorded in docs/work/LOCAL_ASSURANCE_WORKSPACE_STATIC_REVIEW.md.
Builder static review additionally refuses external Git config includes so
copied .git cannot redirect worktree/storage through an external config.
Proposed Git-config regression cases added, NOT RUN.

Only file reads/searches/edits and Git diff/status source inspection performed.
No modified project imports, compilation, pytest, smoke, benchmarks, runtime
measurements, assurance or certification executed. All test commands: NOT RUN.
TESTS_RUN: 0. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
Status: CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS (static-only readiness).

Final static deltas: unavailable /proc children listing is a refusal, never
empty-scope proof; Git external include/worktree configuration is refused.
Independent reviewer inspected both deltas and retained source-only verdict
with no remaining actionable findings. Their new test specifications: NOT RUN.


## 2026-10-07 — Local Assurance optimization pass 3, source only

Built one immutable pristine index with cached restoration bytes per shard;
removed repeated seed SHA computations while retaining full seed byte checks.
Added independent structural dirty detection and sparse repair followed by full
worker SHA checks, with an additional verified repair for hidden same-size byte
changes. Seed permissions are read-only after worker initialization. Kept .git
independent because same-UID modes cannot seal shared storage.

Strengthened constructor-interruption drain handling and main-thread ownership;
added lifecycle stage/category/shard/mutation/retention/quiescence diagnostics.
Added test specifications only. Static inspection found that checking only the
last path component could follow an ancestor symlink during repair chmod; replaced
that approach with component-by-component lstat checks before deletion, creation,
file restoration and mode reset. Invalid dirty hints now poison the workspace.

All test/assurance/benchmark commands: NOT RUN by explicit user restriction.
TESTS_RUN: 0. ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No project imports/execution, certificates, commit, push, PR or merge.
Independent hostile review pending; no executed verification claim.

Independent hostile review identified a P1 Git admission gap: ConfigParser uses
case-sensitive section names while Git accepts mixed-case Core. Refusal now
casefolds section names; uppercase/mixed-case Core test specifications added.
Additional source-only specifications cover sparse ancestor symlink chmod and
invalid-hint poisoning. Index construction refuses size changes during reading.
Review reinspection requested. No tests executed after these corrections.

Static whitespace inspection: `git diff --check` executed in the WSL checkout,
exit 0, no output. This is source inspection only, not test execution. Gate
performance diagnostics now also name the shard/gate and record gate failure.

Final independent reviewer disposition: PASS, static review only. Reviewer
explicitly resolved prior Git Core finding; no remaining actionable finding
within documented Linux dedicated-process assumptions. Review recorded in
LOCAL_ASSURANCE_WORKSPACE_STATIC_REVIEW.md. Final source inspection commands:
`git diff --check` exit 0, no output; `git rev-parse HEAD` returned
8d5eed3f47a0490d481b7ff5c9927f2f944096db; `git branch --show-current`
returned local/local-only-assurance-validation. No project validation executed.
TESTS_RUN: 0; ASSURANCE_RUN: NO;
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN. No certificate/commit/push/PR/merge.
CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS.


## 2026-10-07 — Local Assurance optimization pass 4, implementation only

Removed all retained pristine content bytes. Index retains metadata/digests;
complete seed SHA scans run before attempts and before any repair. Restoration
streams selected seed files in 1 MiB chunks, checks metadata and hashes copied
bytes; no worker fallback or optional cache. This intentionally supersedes the
Pass 3 zero-repeat-seed-hash design to preserve a bounded content buffer and seed
filesystem authority. Normal snapshots remain five; two seed/two worker hash
passes plus hashes of restored seed files. No measured improvement claim.

Static environment investigation found synthetic Git repositories in target
fixtures, so rejected the approach of binding GIT_DIR/GIT_WORK_TREE to the worker.
Instead remove host GIT injections, null global/system config, inert hooks, empty
owned templates and retain cwd discovery. Refuse dangerous seed Git config,
alternates/worktree/history rewrite pointers. Neutralize host import/pytest
injections and put temporary directories under owned external storage; retain
scientific/provider settings and installed plugin/toolchain semantics.

Enforce Linux main thread + exactly one kernel task, default/unblocked SIGCHLD,
no children and no pre-existing subreaper. Ambiguous setup/drain/release poisons
and retains workspace. Explicit close_fds/pass_fds and context-managed file/pipe
lifetimes. Builder static inspection moved SIGTERM drain-handler setup inside the
fail-closed drain try and added runtime inode/type substitution checks.

Added source-only adversarial specifications and non-authoritative work counters.
`git diff --check` executed: exit 0, no output (source whitespace inspection only).
All project test/assurance/benchmark/validation commands: NOT RUN by instruction.
TESTS_RUN: 0; ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
Independent accumulated-diff review pending. No certificate/commit/push/PR/merge.

Independent review found P1 Git section grammar gaps: [core ]/[extensions ] and
deprecated [filter.driver]/[diff.driver] forms could bypass ConfigParser matching.
Added conservative canonical-section grammar admission and refusal specifications.
ConfigParser is explicitly treated as a limited supported parser; unfamiliar
forms refuse. Future real descendant specification now launches a dedicated
interpreter instead of borrowing the pytest process ownership context. NOT RUN.

Final accumulated Pass 2–4 independent reviewer: PASS, static review only.
Prior Git grammar finding explicitly resolved; no remaining actionable finding
within the dedicated Linux process/controlled-toolchain assumptions. Review
recorded in LOCAL_ASSURANCE_WORKSPACE_STATIC_REVIEW.md. Execution remains
unverified. Final static whitespace command `git diff --check`: exit 0, no output.
TESTS_RUN: 0; ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No certificate, commit, push, PR or merge. HEAD remains
8d5eed3f47a0490d481b7ff5c9927f2f944096db. Changes remain uncommitted.
CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS.


## 2026-10-07 — Local Assurance optimization pass 5, source-only audit

Fresh independent reviewer found concrete P1 paths: Formal population deleted
arbitrary preexisting destination; pytest artifacts lived in caller scratch;
linked diagnostic files could overwrite external data; partial-clone promisor
state could lazily fetch missing Git objects; parent killpg after reaping risked
PGID reuse and never proved nested-session ownership. Corrected statically:
fresh-only population, generated owned artifacts + in-memory root/ancestor inode
tokens, atomic diagnostic replacement, partialclone/promisor/unknown-extension
refusal, direct Popen termination and all-abnormal parent scratch retention.
Mixed-case format admission correction included. Existing evidence --reuse now
quarantines bytes instead of recursively deleting a caller-selected prior root.

Seal Git ancestor discovery ceiling and host default attributes/ignore inputs
without changing HOME/XDG or provider semantics. Refuse duplicate shard/CLI IDs.
Recheck thread/SIGCHLD/subreaper state during drain. Dirty candidates with matching
SHA skip copying (mode-only fix permitted only independent inode); already-known
hidden file digest reused. Remove unused index name tuples/imports; retain exact
B55d legacy isolation guard because it is a live mutation target. Physical copies
remain two per shard; five snapshots are scans, not copies. Full hash passes
remain required absent authenticated OS immutability. Added specs NOT RUN.

Reviewer established arbitrary same-UID target code can access checkout/shard
absolute paths. This is not an OS sandbox; requested contract clarification
asynchronously, while completing the authorized source audit. Do not silently
scope a literal isolation request down or claim an unqualified PASS.
`git diff --check` executed exit 0, no output (source whitespace only).
TESTS_RUN: 0; ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No project imports/execution, runtime measurements, certificate/commit/push/PR/merge.
Final independent review and isolation-contract disposition pending.

Final fresh reviewer verdict: BLOCKER, literal arbitrary-target isolation.
Demonstrated same-UID absolute-file and explicit Git override access remains;
controlled-path production findings corrected. Reviewer P2 corrected in cost model:
Formal copies no .git (G=0); V4 copies two. Contract clarification remains pending.
No project validation run. Final `git diff --check`: exit 0, no output; `git diff
--stat` and `git status --short` inspected; untracked source/doc files remain
unstaged and are listed separately by status. HEAD unchanged at
8d5eed3f47a0490d481b7ff5c9927f2f944096db.
TESTS_RUN: 0; ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
SCIENTIFIC_DOMAIN_CODE_CHANGED: NO; CERTIFICATE_GENERATED: NO;
COMMIT: NO; PUSH: NO; PR: NO; MERGE: NO. CONTROL_PLANE_NOT_READY.

User explicitly accepted controlled-target/toolchain isolation and inherited-input/
owned-path sealing, resolving the earlier literal-OS-isolation scope blocker.
No production code changed to resolve it, and no OS sandbox guarantee is claimed.
Requested final fresh reviewer disposition under that accepted contract. Tests,
assurance, benchmarks and publication remain prohibited and NOT RUN.

Final fresh independent reviewer PASS under the explicitly accepted controlled-
target/toolchain contract; previous scope blocker and cost P2 resolved. No OS
sandbox claim, no source execution or tests. Final git diff --check exit 0;
git diff --stat/status inspected, changes remain uncommitted, HEAD unchanged.
TESTS_RUN: 0; ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No scientific/domain change, certificate, commit, push, PR or merge.
Recommended Pass 6: statically audit specification/contract compatibility and
owned filesystem operations; first runtime validation requires explicit change
of execution authorization. CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS.


## Pass 6 static integration milestone

Repaired invocation collisions, manifest closure/path admission, atomic JSON writes,
source identity boundaries, pytest infrastructure attribution and failure context.
Corrected failed-scratch retention specifications; added manifest/lock/diagnostic specs.
Failed approach: prior broad evidence enumeration and unguarded pytest exits could
admit unexpected files or infrastructure failures; replaced with explicit admission.
Static command: `git diff --check` in the task checkout, exit 0 (source whitespace only).
TESTS_RUN: 0. ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
Tests, mutation, subprocess/Git/import probes, profiling and certification: NOT RUN.
No scientific/domain change; no certificate, commit, push, PR or merge.
Independent final static review remains pending; detailed audit in Pass 6 document.

Final independent complete Pass 2–6 hostile static review: PASS; all reported
static findings repaired and reinspected. Second pre-final source-only
`git diff --check`: exit 0. No runtime operation followed the final review.
READY_TO_FREEZE_WORKSPACE_ARCHITECTURE under the accepted controlled-target/toolchain
boundary. Runtime lifecycle, installed imports and specs remain NOT RUN.


## Pass 7 static startup milestone

Implemented immutable shard startup snapshot and command flags, executable metadata
checks, deterministic external-plugin autoload refusal, Python startup sealing and
no bytecode writes/shared caches. Formal excludes legacy .pyc. Hostile static review
found inherited Python flags and permissive JUnit XML decoding; repaired both and
added adversarial specifications. No scientific/domain logic changed.
Static source literal inspection: 284 Formal, 680 V4 (two NOT_MUTATED), 590 V4
nodeids/120 modules; eligible subset 588 nodeids. Maximum full-shard pytest starts
974 including controls, not measured. Initial source-analysis script failed to
handle AnnAssign and raised TypeError; corrected AST handling, no project execution.
TESTS_RUN: 0. ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
Tests/probes/benchmarks/certification: NOT RUN. No certificate/commit/push/PR/merge.

Static checks before final review: `py -3 -` with stdlib AST parsing of the five
Pass 7 Python source files, exit 0; no project imports or execution. Exact shell
whitespace command: `wsl.exe -e sh -c 'cd /home/dev_kaeem/forge-local-assurance-72bf7c4c && git diff --check'`, exit 0.
Final independent hostile review of implementation/specs/docs: PASS after repairs.
No runtime command followed review. FRESH_PROCESS_OPTIMIZED. Unexecuted specs,
controlled installed-toolchain compatibility and Linux lifecycle remain open for
explicitly authorized Pass 8 validation. TESTS_RUN: 0. ASSURANCE_RUN: NO.
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.


## Pass 8 bounded runtime validation (2026-10-07)

Takeover recovered the work in the WSL clone `/home/dev_kaeem/forge-local-assurance-72bf7c4c`
(not a phyx worktree), HEAD 8d5eed3f, Passes 2–7 uncommitted; diff and untracked files were
backed up before execution. All probes ran in WSL with `.forge/venvs/3.12`, outputs outside
the repository (`$HOME/forge-pass8`; WSL `/tmp` does not survive between `wsl` invocations).

Commands and results (bytecode writes and cacheprovider disabled):
- `python -m pytest -p no:cacheprovider -q tests/test_mutation_startup.py tests/test_mutation_workspace.py tests/test_local_assurance.py`: 182 passed (3.12, 2.45 s; 3.11, 2.10 s).
- Same set plus test_mutation_population_v4, test_mutation_harness, test_hardening_assurance,
  test_recertification_scope, test_certification_control_plane, test_certification_clean_tree,
  test_core_certificate, test_certification_mutation_population, test_certificate_lineage:
  440 passed, 4 failed in 29.36 s. New failures: test_certification_control_plane.py::
  test_every_control_plane_file_has_its_own_reason_and_the_real_build_accepts_them and
  ::test_the_certificate_is_never_inside_its_own_scope (mutation_startup.py had no reason;
  tests/test_mutation_workspace.py had a reason but no pattern). Baseline drift (also at a
  pristine 8d5eed3f clone, 291 passed / 2 failed): test_core_certificate.py::
  test_the_certificate_describes_this_tree and ::test_the_certificate_records_the_v1_relationship_truthfully.
- Failed approach: running tests/test_mutation_harness.py alone fails to collect
  (`import mutation_guards` needs tests/ on sys.path, inserted by test_mutation_population_v4.py);
  pre-existing order dependence, run that module first.
- Runtime probes (production PersistentWorkspace/run_captured/mutation_environment paths):
  pytest startup (builtins, conftest, fixtures, markers, importlib mode, JUnit, --runxfail)
  PASS; 16 hostile PYTHON*/PYTEST*/GIT_* parent values sealed, no .pyc; fake pytest11 plugin
  loads only with autoload re-enabled; 17 restoration/refusal cases PASS; 22 hostile .git
  states refused, hooks/global/system config/GIT_DIR sealed, ceiling holds; 14 process
  ownership cases PASS, no orphan/zombie; real `local_assurance run` with synthetic gate
  commands in a throwaway overlay clone: workers=1 peak 1, workers=2 peak 2, shard failure
  refuses the group, SAFE_TO_PUSH NO, no receipt/manifest/certificate.
- Formal micro-run (production shard path) G1a G1d G2f G27b: 4/4 killed by the named guard,
  control GREEN (1139 passed, 1 skipped), 676 s. V4 micro-run B56a B19j B11a B12a B29c:
  5/5 declared verdicts, control GREEN, 29.6 s (concurrent with the Formal shard).
- Residual, pre-existing: a target-launched Python subprocess imports engcore from the
  checkout via the editable .pth (only one target does this and it pins its own src);
  Formal shard stdout is block-buffered until exit.
Verdict: RUNTIME_VALIDATION_BLOCKED (certificate control registration).

## Pass 9 certification scope fix and V4 verification cost (2026-10-07)

core_certificate.py (authorized): mutation_startup.py reason added;
tests/test_mutation_workspace.py added to certification_control patterns.
- Blocker tests: the two test_certification_control_plane.py nodeids above: 2 passed in 1.09 s.
- Targeted set (12 modules, as Pass 8): 442 passed, 2 failed in 30.16 s; the 2 are the
  baseline certificate-drift failures above.
State-transition model (docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_9.md): every full
per-attempt pass is REQUIRED or SPEC-PINNED; seed-sealing hypothesis rejected (same-uid
targets can chmod the seed). Profile on a V4-shaped tree (8,354 files, 88.8 MB): full
snapshot 0.430 s vs 0.082 s floor (scandir + SHA-256 of every byte); metadata walk 0.273 s
vs 0.016 s; per-entry pathlib dominated. snapshot() now builds relative names from scandir
names; rows, manifest digests, telemetry counters and error shapes proven identical to the
previous implementation on the real V4 tree, real Formal tree and a hostile tree.
- After the change: 182 new specs pass on 3.11 and 3.12; targeted set 442 passed / same 2
  drift failures in 29.85 s; 17 restoration cases unchanged.
- Like-for-like V4 micro-run (same five entries + control, nothing else running): wall
  28.98 s -> 18.40 s; seed verify 13 passes 5.51 s -> 2.13 s; worker full 13 passes
  5.48 s -> 2.09 s; delta 6 scans 1.70 s -> 0.26 s; same verdicts, same bytes hashed,
  same 306,290 restoration bytes. Formal semantics unchanged.
ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN. No certificate/commit/push/PR/merge.

Independent read-only review (forge-scientific-reviewer) of the snapshot() rewrite and the
scope registration: PASS. LOW finding (no test pinned the equivalence claim) fixed with
test_string_path_snapshot_equals_the_pathlib_manifest_and_counters and
test_mid_walk_failure_still_reports_entries_already_scanned in tests/test_mutation_workspace.py
(pass on 3.11/3.12 and against the pre-Pass-9 implementation). LOW pre-existing finding recorded,
not changed: core_certificate.py OUT_OF_SCOPE prose still says "the two self-check modules".
Final targeted set: 444 passed, 2 failed (baseline certificate drift) in 29.97 s; new specs
184 passed on 3.11 (2.04 s).

## Pass 10 freeze and bounded concurrency measurement (2026-10-07)

Pre-freeze audit of the Passes 2–9 diff: only tools/certification, mutation/assurance tests
and docs touched; MUTATIONS/EVIDENCE/TARGETS/_COPIED AST-identical to 8d5eed3f; V4
population and selection modules untouched; no debug code; telemetry archived outside
evidence/. Stale "never executed"/"future execution" wording corrected. `git diff --check`: exit 0.
Pre-commit: blocker tests 2 passed; Passes 2–9 specs 184 passed on 3.11 and 3.12; targeted
12-module set 444 passed, 2 failed (baseline certificate drift) in 30.51 s.
Source commit: 4f2cdf4b5c38b17bc3188967d15503d51b907bed
"certification: optimize local mutation assurance" (local only; no certificate, push or PR).

Benchmark (not certification evidence): production _mutation_group/_mutation_scratch/_run
path at the committed source; Formal 4 shards x 1 mutation (G1a, G1d, G2f, G27b) + per-shard
control; V4 8 shards x 2 entries (B56a B19j B11a B12a B29c N61h N57i N57c N62i N63a N61o
B14o N57g N57p N60h B1q) + per-shard control; HEAD/clean checks around each shard.
Order w2, w4, w1, then w4, w2. Wall: w1 1106.6 s; w2 597.0 / 602.1 s; w4 335.2 / 336.5 s.
Formal group: 1050.7 / 563.1-568.6 / 310.8 s. V4 group: 56.0 / 33.5-33.9 / 24.4-25.6 s.
Peak process-tree RSS: 854 / ~1550 / ~3100 MB; min MemAvailable 20.3 GB. Mean CPU busy
6 / 12 / 22 % of 20 logical CPUs. Per-shard Formal time +4 % (w2) and +14 % (w4) vs w1.
All five runs: identical 20 verdicts, 12/12 controls GREEN, distinct scratch, no residue,
HEAD unchanged, tree clean. Recommendation: --mutation-workers 4 (CLI); code default left 2.

## Pass 11 Formal hot-path audit (2026-10-07)

Profiling only at source 4f2cdf4b (no source change; candidate via out-of-tree wrapper).
Probe: production PersistentWorkspace + run_captured, exact Formal TARGETS command, external
/proc sampler. Serial unmutated attempt 141.2 s (pytest 135.7 s), collect-only 6.2 s; four
modules = 80 % of test time; 1.20 cores used per attempt (single-thread CPU bound).
xdist controls n=2/n=4 loadfile/loadscope/load: 0 of 1140 per-nodeid outcome differences.
Failed approach: plain xdist (also with --max-worker-restart=0) turns a SIGSEGV test into
`FAILED <nodeid>` exit 1, which the Formal rule credits RED; serial gives exit -11 (no credit).
Candidate = xdist loadfile + refuse on worker crash/node-down markers (demonstrated).
Benchmark (G1a G1d G2f G27b, 4 shards, controls, mutation-workers=4, clean clone of 4f2cdf4b):
baseline 315.1 / 308.6 s; candidate n=2 207.7 s; n=4 187.2 s; identical verdicts, controls
GREEN, peak RSS 3.1 / 4.7 / 6.4 GB, no residue. Details:
docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_11.md. Not adopted: needs crash-refusal spec,
plugin-policy amendment, scientific review and an owner certification decision.

## Pass 12 safe Formal pytest-xdist (2026-10-07)

Opt-in --formal-pytest-workers / --pytest-workers (default 1, historical command). Details,
design, crash table, benchmarks and failed approaches: docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_12.md.
Commands (bytecode writes and cacheprovider off):
- python -m pytest tests/test_formal_xdist.py tests/test_local_assurance.py tests/test_mutation_startup.py
  tests/test_mutation_workspace.py tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared:
  253 passed (3.12, 17.0 s; 3.11, 15.7 s).
- Targeted 13-module control-plane set: 512 passed, 2 failed (baseline certificate drift:
  test_core_certificate.py::test_the_certificate_describes_this_tree and
  ::test_the_certificate_records_the_v1_relationship_truthfully) in 36.2 s.
- Full Formal TARGETS serially (python -X utf8 -m pytest <48 TARGETS> -q -p no:randomly -p no:cacheprovider
  --continue-on-collection-errors): 1140 passed in 132.9 s.
- Bounded benchmarks (Formal only, mutation-workers 4): serial 1431.5 s vs xdist n=2 1116.9 s on 32
  mutations (31 named + G1d), identical verdicts, controls GREEN, no residue.
Failed approach: pytest.importorskip("execnet") in a new spec turned every Formal CONTROL red through
the dependency guard; the earlier targeted set did not include test_core_guards.py.
ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN. No certificate/push/PR/merge.

## Pass 13 semantic skip admission (2026-10-08)

Previous refusal: full `local_assurance run --workers 4 --mutation-workers 4 --formal-pytest-workers 2`
at d5d886f9 (2h42m) passed every execution gate, then `build_assurance` raised AssuranceError:
FAST 3.11/3.12 and SCIENTIFIC each 142 skipped vs SKIP_CEILING FAST 19 / SCIENTIFIC 5; the runner
printed a traceback (exit 1) while writing the right failure record. Prior evidence kept in
.forge/assurance/d5d886f9.../ (failure record sha256 949d5aa2..., manifest 24f80976...).

Skip audit of the d5d886f9 JUnit (identical skip universe in FAST 3.11, FAST 3.12 and SCIENTIFIC):
142 = 133 optional provider (130 provider/flagship modules + 3 core tests needing Gmsh), 5 optional
extras (SymPy 2, meshio 2, psutil 1), 4 conditional (reason-truth U00048/U01031, exact-freeze domain
digest, blind-challenge dynamic import guard); 0 platform-specific; 0 unexplained.

Change: tools/certification/skip_admission.py (committed rules + providers, availability probe in
the gate's interpreter, JUnit skip parsing, per-skip admission, re-admission); assurance schema
/7 with a `skip_admission` section; /5 and /6 revalidate against LEGACY_SKIP_CEILING (telemetry);
probe step + evidence file in each FAST/SCIENTIFIC gate (local runner and recertify workflow);
`local_assurance verify` re-derives the section from frozen evidence; refusal UX
(REFUSED + FAILURE_RECORD + SAFE_TO_PUSH: NO, exit 1; INTERNAL_ERROR + traceback, exit 2).

Review (forge-scientific-review, one round, CHANGES REQUIRED, all addressed):
- HIGH registry "unavailable" for present-but-broken providers -> exact absence-reason allowlist,
  independent module/executable facet per registry provider, facet status re-derived from raw fields.
- HIGH Core PDE refusals only ran with Gmsh -> new provider-free tests on a hand-built mesh
  (tests/test_pde_contracts.py); the Gmsh-gated originals stay as they were.
- MEDIUM reason-truth skip covered two causes -> distinct reasons; rule admits only NOT_REPAIRABLE.
- MEDIUM blind-challenge import guard skipped in every gate -> runs in a fresh interpreter; rule removed.
- LOW freeze test skipped on any non-exact mode -> skips only on DESCENDANT, asserts EXACT otherwise.
- LOW stored facets believed on the child -> status re-derived; block interpreter checked against
  the environment section; docstrings corrected. LOW combined claim; protected entries must be files.
- Recorded, not changed: a module-scoped rule admits a new test in the same module only with the
  module's own pytestmark reason and an unavailable provider (by design); per-rule counts are
  telemetry, not pinned.

Failed approach: creating the synthetic harness kill-suite files inside certification_fixtures.make_repo
made the certificate builder refuse ("harness area does not pin ... modules the certified suites
import") in 47 control-plane tests; the files now live only in tests/test_skip_admission.py's fixture.
Failed approach: a long bash heredoc patch script for hardening_assurance.py wrote nothing (quote EOF).

Commands (WSL clone, TMPDIR=~/forge-pass13/tmp, -p no:cacheprovider):
- Dry-run audit of d5d886f9 JUnit with fresh probes: 3.11 / 3.12 FAST 142 accepted, 0 unexpected
  (inventory c8cae527...); SCIENTIFIC 142 / 0 (first policy version, before the review fixes).
- pytest tests/test_skip_admission.py test_hardening_assurance.py test_local_assurance.py
  test_certificate_lineage.py test_recertification_scope.py test_certification_control_plane.py
  test_core_certificate.py test_mutation_workspace.py test_formal_xdist.py test_mutation_population_v4.py
  test_forge_check.py (self-checks deselected): 560 passed on 3.12, 560 passed on 3.11.
- Full Formal TARGETS serially (python -X utf8 -m pytest <48 TARGETS> -q -p no:randomly
  --continue-on-collection-errors): 1140 passed in 141.1 s.
- pytest tests/test_provider_boundary.py providers/ flagships/tests: 93 passed, 130 skipped (3.12 and 3.11).
- tools/forge_check.py --changed: 225 passed.
- FAST preflight on the uncommitted tree (gate command, 3.12 and 3.11): 9365 passed, 141 skipped,
  1 failed each = tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds
  on tree.clean only (uncommitted changes); audit 141 accepted / 0 unexpected, inventory 14370d2c...
  identical on 3.11 and 3.12 (3 conditional, 5 extra, 133 provider).

## Full project review — 2026-10-05

Review: docs/work/PROJECT_REVIEW_2026-10-05.md. No production code changed. Initial ACTIVE_PLAN edit preserved. Python 3.14.2/Windows; not the declared CI environment. FAST and SCIENTIFIC overlapped, so these are diagnostic runs, not isolated clean-tree acceptance baselines. Generated benchmark JSONs were backed up and all 17 restored; logs were moved under .pytest-review-temp/full-project-logs-20261005/.

2026-10-05 19:12 +03:00
command: `python tools/forge_check.py --regression`
result: BLOCKED
summary: Windows Store alias reports Python not found; no tests executed.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 tools/forge_check.py --regression`
result: FAIL
summary: pytest temporary-root setup PermissionError [WinError 5] in test_untracked_manifest_digest_changes_with_file_content; not a product assertion failure.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 tools/forge_check.py --changed`
result: PASS
summary: 40 passed.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 -m pytest -m "not expensive" -q -n 4 --tb=short *> .pytest-full-project-review-fast.log`
result: BLOCKED
summary: xdist INTERNALERROR: PermissionError at pytest-of-dev_kaeem temporary root; retried with explicit workspace basetemp.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 -m pytest -q tests/scientific/replay_core/test_dirty_tree.py --tb=short`
result: FAIL
summary: No tests ran: requested test file does not exist; this was an incorrect diagnostic target, not a test failure.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `$env:PYTEST_ADDOPTS='--basetemp=.pytest-review-temp/regression-20261005'; py -3.14 tools/forge_check.py --regression *> .pytest-full-project-review-regression.log`
result: PASS
summary: 225 passed in 10.10s.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 -m pytest -m "not expensive" -q -n 4 --tb=short --basetemp=.pytest-review-temp/full-project-20261005 *> .pytest-full-project-review-fast.log`
result: FAIL
summary: 8640 passed, 33 failed, 88 skipped, 66 warnings, 20 collection errors in 315.15s; exit 1.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 -m pytest -m "not campaign" -q -n 4 --tb=short --basetemp=.pytest-review-temp/scientific-20261005 *> .pytest-full-project-review-scientific.log`
result: FAIL
summary: 9196 passed, 33 failed, 88 skipped, 66 warnings, 20 collection errors in 334.36s; exit 1.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 -m pytest -q tests/test_engineering_contracts.py tests/test_provider_boundary.py tests/test_big11_review_fixes.py --basetemp=.pytest-review-temp/focused-20261005 --tb=short`
result: PASS
summary: 52 passed, 1 skipped in 3.77s.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

2026-10-05 19:12 +03:00
command: `py -3.14 -m pytest -q tests/claims/test_impact_replay.py --basetemp=.pytest-review-temp/replay-isolated-20261005 --tb=short`
result: PASS
summary: 24 passed in 3.58s after benchmark-output cleanup and isolated execution.
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870 (existing plan edit)

Relevant failure names — FAST (full diagnostics in saved log):
```text
FAILED tests/domains/test_audit_domains_unscreened_claims.py::test_the_held_resistance_limitation_is_stated_where_a_caller_reads
FAILED tests/claims/test_impact_replay.py::test_a_bundle_verifies_without_execution_and_replays_identically
FAILED tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result
FAILED tests/claims/test_impact_replay.py::test_a_bundle_with_external_evidence_carries_its_trust_and_replays
FAILED tests/test_core_scientific_audit_batch56.py::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see
FAILED tests/test_core_semantic_invariants.py::test_every_reader_that_writes_a_schema_also_checks_one
FAILED flagships/tests/test_flagship_portfolio.py::test_ghia_excerpt_is_a_numerical_benchmark_with_a_content_identity_and_matches_an_independent_transcription
FAILED flagships/tests/test_flagship_portfolio.py::test_nist_hess_reference_is_analytic_carries_source_digests_and_its_numbers_recompute
FAILED flagships/tests/test_flagship_portfolio.py::test_the_nasa_battery_reference_is_pinned_by_the_repository_manifest_and_has_no_copied_data
FAILED flagships/tests/test_flagship_portfolio.py::test_the_analytic_references_of_the_structure_flagship_are_labelled_analytic_and_apply_only_inside_their_envelopes
FAILED flagships/tests/test_flagship_portfolio.py::test_the_first_law_reference_is_analytic_and_states_it_shares_a_property_backend
FAILED flagships/tests/test_flagship_portfolio.py::test_the_numeric_criteria_are_pinned_to_the_preregistration_file_and_recorded_failures_stay_recorded
FAILED tests/claims/test_claims_assessment.py::test_the_mcp_tool_returns_the_same_record
FAILED tests/test_core_api_contracts.py::test_the_frozen_digest_is_identical_in_fresh_processes
FAILED tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract
FAILED tests/test_core_api_snapshot.py::test_the_snapshot_is_byte_identical_across_fresh_processes
FAILED tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds
FAILED tests/test_core_certificate.py::test_the_certificate_describes_this_tree
FAILED tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully
FAILED tests/test_core_freeze_v4_manifest.py::test_the_deep_surface_carries_methods_and_member_positions
FAILED tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1 - ...
FAILED tests/test_core_freeze_manifest.py::test_the_command_line_verifier_agrees_with_the_function
FAILED tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies
FAILED tests/test_core_freeze_policy.py::test_the_policy_names_every_non_core_package
FAILED tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks
FAILED tests/test_core_guards.py::test_the_bare_install_the_readme_documents_is_the_one_that_must_be_green
FAILED tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree
FAILED tests/test_core_guards.py::test_the_battery_march_runs_the_solver_it_names
FAILED tests/test_core_guards.py::test_every_marched_step_carries_its_own_cell_report
FAILED tests/test_core_scientific_audit_batch24.py::test_r39_the_word_says_that_agreement_between_solvers_is_one_of_the_things_it_covers
FAILED tests/test_core_guards.py::test_the_domain_names_were_derived_from_the_packages_not_listed
FAILED tests/test_spatial_core.py::test_meshio_roundtrip_preserves_identity
FAILED tests/test_spatial_core.py::test_duplicate_facet_and_flattening_are_refused
ERROR flagships/tests/test_flagship_ladders.py - ImportError while importing ...
ERROR flagships/tests/test_thermoelastic_adapters.py - ImportError while impo...
ERROR providers/calculix/tests/test_calculix_provider.py - ImportError while ...
ERROR providers/cantera/tests/test_cantera_provider.py - ImportError while im...
ERROR providers/code_aster/tests/test_code_aster_provider.py - ImportError wh...
ERROR providers/coolprop/tests/test_coolprop_provider.py - ImportError while ...
ERROR providers/fenicsx/tests/test_coupling_fenicsx.py - ImportError while im...
ERROR providers/fenicsx/tests/test_multiscale_fenicsx.py - ImportError while ...
ERROR providers/fenicsx/tests/test_pde_fenicsx.py - ImportError while importi...
ERROR providers/openfoam/tests/test_openfoam_provider.py - ImportError while ...
ERROR providers/openmodelica/tests/test_openmodelica_provider.py - ImportErro...
ERROR providers/precice/tests/test_precice_provider.py - ImportError while im...
ERROR providers/pybamm/tests/test_pybamm_provider.py - ImportError while impo...
ERROR providers/su2/tests/test_su2_provider.py - ImportError while importing ...
ERROR providers/tespy/tests/test_tespy_provider.py - ImportError while import...
ERROR tests/domains/battery/test_audit_domains_battery_pulse.py - ImportError...
ERROR tests/mcp/test_answer.py - ImportError while importing test module 'C:\...
ERROR tests/mcp/test_audit_domains_electrothermal_transient.py - ImportError ...
ERROR tests/mcp/test_audit_domains_refused_coupling.py - ImportError while im...
ERROR tests/mcp/test_core_scientific_audit_batch8.py - ImportError while impo...
```

Relevant failure names — SCIENTIFIC (full diagnostics in saved log):
```text
FAILED tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result
FAILED tests/domains/test_audit_domains_unscreened_claims.py::test_the_held_resistance_limitation_is_stated_where_a_caller_reads
FAILED benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates
FAILED benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates
FAILED tests/test_core_scientific_audit_batch24.py::test_r39_the_word_says_that_agreement_between_solvers_is_one_of_the_things_it_covers
FAILED tests/test_core_api_contracts.py::test_the_frozen_digest_is_identical_in_fresh_processes
FAILED tests/test_core_api_snapshot.py::test_the_snapshot_is_byte_identical_across_fresh_processes
FAILED tests/test_core_certificate.py::test_the_certificate_describes_this_tree
FAILED tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully
FAILED tests/test_core_scientific_audit_batch56.py::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see
FAILED tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1 - ...
FAILED tests/test_core_freeze_manifest.py::test_the_command_line_verifier_agrees_with_the_function
FAILED flagships/tests/test_flagship_portfolio.py::test_ghia_excerpt_is_a_numerical_benchmark_with_a_content_identity_and_matches_an_independent_transcription
FAILED flagships/tests/test_flagship_portfolio.py::test_nist_hess_reference_is_analytic_carries_source_digests_and_its_numbers_recompute
FAILED flagships/tests/test_flagship_portfolio.py::test_the_nasa_battery_reference_is_pinned_by_the_repository_manifest_and_has_no_copied_data
FAILED flagships/tests/test_flagship_portfolio.py::test_the_analytic_references_of_the_structure_flagship_are_labelled_analytic_and_apply_only_inside_their_envelopes
FAILED flagships/tests/test_flagship_portfolio.py::test_the_first_law_reference_is_analytic_and_states_it_shares_a_property_backend
FAILED flagships/tests/test_flagship_portfolio.py::test_the_numeric_criteria_are_pinned_to_the_preregistration_file_and_recorded_failures_stay_recorded
FAILED tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies
FAILED tests/test_core_freeze_policy.py::test_the_policy_names_every_non_core_package
FAILED tests/claims/test_claims_assessment.py::test_the_mcp_tool_returns_the_same_record
FAILED tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks
FAILED tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree
FAILED tests/test_core_guards.py::test_the_battery_march_runs_the_solver_it_names
FAILED tests/test_core_guards.py::test_every_marched_step_carries_its_own_cell_report
FAILED tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract
FAILED tests/test_core_guards.py::test_the_domain_names_were_derived_from_the_packages_not_listed
FAILED tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds
FAILED tests/test_core_freeze_v4_manifest.py::test_the_deep_surface_carries_methods_and_member_positions
FAILED tests/test_core_guards.py::test_the_bare_install_the_readme_documents_is_the_one_that_must_be_green
FAILED tests/test_core_semantic_invariants.py::test_every_reader_that_writes_a_schema_also_checks_one
FAILED tests/test_spatial_core.py::test_meshio_roundtrip_preserves_identity
FAILED tests/test_spatial_core.py::test_duplicate_facet_and_flattening_are_refused
ERROR flagships/tests/test_flagship_ladders.py - ImportError while importing ...
ERROR flagships/tests/test_thermoelastic_adapters.py - ImportError while impo...
ERROR providers/calculix/tests/test_calculix_provider.py - ImportError while ...
ERROR providers/cantera/tests/test_cantera_provider.py - ImportError while im...
ERROR providers/code_aster/tests/test_code_aster_provider.py - ImportError wh...
ERROR providers/coolprop/tests/test_coolprop_provider.py - ImportError while ...
ERROR providers/fenicsx/tests/test_coupling_fenicsx.py - ImportError while im...
ERROR providers/fenicsx/tests/test_multiscale_fenicsx.py - ImportError while ...
ERROR providers/fenicsx/tests/test_pde_fenicsx.py - ImportError while importi...
ERROR providers/openfoam/tests/test_openfoam_provider.py - ImportError while ...
ERROR providers/openmodelica/tests/test_openmodelica_provider.py - ImportErro...
ERROR providers/precice/tests/test_precice_provider.py - ImportError while im...
ERROR providers/pybamm/tests/test_pybamm_provider.py - ImportError while impo...
ERROR providers/su2/tests/test_su2_provider.py - ImportError while importing ...
ERROR providers/tespy/tests/test_tespy_provider.py - ImportError while import...
ERROR tests/domains/battery/test_audit_domains_battery_pulse.py - ImportError...
ERROR tests/mcp/test_answer.py - ImportError while importing test module 'C:\...
ERROR tests/mcp/test_audit_domains_electrothermal_transient.py - ImportError ...
ERROR tests/mcp/test_audit_domains_refused_coupling.py - ImportError while im...
ERROR tests/mcp/test_core_scientific_audit_batch8.py - ImportError while impo...
```

Diagnostic counterexamples executed through PowerShell here-strings piped to `py -3.14 -`: failed version probe returned AVAILABLE and minted identity; changed synthetic installed solver bytes retained distribution_digest; infinite replay tolerance returned numerical_reproducibility=True; actual write_bundle with traversal reference ID wrote outside bundle in a disposable temporary directory. These are software counterexamples, not scientific validation. Independent scientific reviewer: CHANGES REQUIRED for supplied bundle/reference excerpts only; tests NOT RUN by reviewer.

Failed approach: broad tiers overlapped while SCIENTIFIC regenerated tracked benchmark reports, causing source-identity replay interference. Do not repeat this concurrency arrangement for an acceptance baseline. Isolated claim replay pack passed; other failures remain unclassified beyond dependency/dirty-tree categories. Hardened recertification, mutation populations, external solver validation, remote CI and branch policy: NOT RUN / NOT inspected.

2026-10-05 19:12 +03:00
command: `git diff --check`
result: PASS
summary: exit 0; no whitespace errors
commit: a3f757eb5fdbc804ef11e3c4088a757c31981870


## 2026-10-09 BIG 14 — review 2026-10-05 R1/R4 fixes (branch `fix/big-14-review-r1-r4`, worktree `D:/forge-r1r4`)

Base `origin/main` @ `16c87f40`. Commits `926836a4` (R1 + R4, review doc carried in, BUILD-phase PROGRESS archived) and
`26d04c14` (scientific review round 1 fixes).

- R1 (HIGH): `write_bundle` checked only `/` and a leading `.` in artifact names and nothing in reference ids. Counterexamples now
  refused: reference id `..\..\outside`; an artifact admitted by a SUCCEEDED receipt as `C:outside` (the receipt `_ID` grammar
  admits `:` and `/`). Names are one printable-ASCII segment without separators, colon, `~`, wildcards, leading/trailing dot or a
  Windows device name; case-only collisions are refused; no existing component below the root may be a link; every destination
  (manifest included) is checked before the first write; files are written to an exclusive temp file and renamed over the
  destination. `verify_bundle` reads under the same rule and refuses nested paths that write cannot make.
- R4 (MEDIUM): `compare_runs` tolerances must be finite, non-negative real numbers (not bool), and `rel_tol < 1`.
- R2/R3 were already covered on `origin/main` (version-probe `returncode` refusal; `catalog._footprint`). R5 is carried by the
  Pass 13 skip admission.
- forge-scientific-review, one round: CHANGES REQUIRED — HIGH-1 manifest.json written uncontained; MEDIUM-1 hard link / sibling
  link / check-then-open race; MEDIUM-2 `rel_tol >= 1` still accepts any same-signed drift; LOW-1 Unicode/8.3/device names; LOW-2
  manifest read and nested names in verify; LOW-3 overflow and missing acceptance tests. All fixed in `26d04c14`; no finding was
  dispositioned as not applicable. `abs_tol` being read in run `a`'s unit is pre-existing and out of scope (recorded, not changed).

Commands (Windows, Python 3.14 venv, `TMPDIR=D:/ftmp`, `-p no:cacheprovider`):
- `pytest tests/test_engineering_contracts.py tests/test_system_runtime_checkpoint.py tests/test_system_runtime_review_fixes.py
  tests/mcp/test_bundle.py tests/test_agent_workflow_contract.py tests/test_core_semantic_invariants.py tests/test_pin_portability.py
  flagships/tests providers/pybamm/tests/test_system_runtime_battery.py -n 4` on `926836a4`: 337 passed, 58 skipped.
- New tests against the pre-fix source (src stashed): round 1, 29 of 32 selected failed; round 2 (WSL 3.12), 17 failed, 18 passed.
- `python tools/forge_check.py --changed` on `926836a4`: 225 passed.
- FAST `pytest -m "not expensive" -q -n 4` on `926836a4` (Windows 3.14, a measurement, not the gate environment): 117 failed,
  9258 passed, 166 skipped, 19 errors. The same 8 files at pristine `16c87f40` (`D:/forge-review-main`): 117 failed, 19 errors;
  failures only on the fix branch: NONE. They are POSIX-only certification/mutation-workspace tests and clean-tree/freeze checks.
- `26d04c14`: `pytest tests/test_engineering_contracts.py tests/test_system_runtime_checkpoint.py tests/test_system_runtime_review_fixes.py`
  Windows 3.14: 125 passed, 3 skipped (file symlinks need privilege); WSL 3.12 (`/mnt/d/forge-r1r4b`, engcore imported from the
  worktree): 128 passed, 0 skipped.
- Full local assurance, mutation populations and hardened recertification: NOT RUN at the time of this entry.

Failed approach: a long bash heredoc patch script failed with "unexpected EOF" (nested quotes); patch scripts go through the file
tool. Editing the worktree while FAST ran would have contaminated it; round-2 fixes were made in a second detached worktree and
fast-forwarded.

## 2026-10-09 BIG 14 — flagship A 14.3: timebox, Kirkaldy 2024 pre-registration, B/C/D deferred (branch `feat/big-14-a-kirkaldy-fade`)

- Owner decisions 2026-10-09: download the Kirkaldy 2024 LG M50T subset; 14.3 timebox two weeks (2026-10-09 to 2026-10-23).
- Pre-registration commit `dd53eec7` (pushed to `origin/feat/big-14-a-kirkaldy-fade` before any capacity value was read and while
  the archives were still downloading): `big14_a_campaign_timebox_preregistration.json` and
  `big14_a_kirkaldy_fade_preregistration.json` (calibrate ThroughputArrheniusFade on Expt 5, hold out Expt 4; C1 pooled holdout
  RMSE <= 0.015, C2 per-temperature |bias| <= 0.010).
- Data: Zenodo 10637534 (CC-BY-4.0). Expt 5 10,443,549,687 B md5 298aa767..., Expt 4 11,376,117,549 B md5 99083707..., into
  `D:/forge-data/kirkaldy2024/raw` (not committed). A single curl stream ran at ~68 KB/s (~3.7 days); a 16-connection
  ranged download (stdlib, resumable per 128 MB chunk) runs at ~1 MB/s.
- B, C and D moved to DEFERRED in `docs/flagships/README.md`; verdicts and gaps unchanged.
- `pytest flagships/tests tests/test_agent_workflow_contract.py tests/test_repository_architecture.py` (Windows 3.14): 55 passed,
  50 skipped (provider-gated).
- Noted BEFORE any result (data still downloading): flagship A feeds ThroughputArrheniusFade the integral of |I| (charge AND
  discharge), while the pre-registered study throughput is discharge charge only. The study's criteria are unaffected (k_q
  absorbs a constant factor), but a k_q carried into flagship A must be converted to the |I| definition (about one half for
  full constant-current cycles; the drive-cycle regenerative pulses make the factor profile-dependent). The conversion will be
  stated with the transfer, never silently applied. The dataset's processed summaries carry `Charge Throughput [A h]` and
  `C/10 Capacity [mA h]` per RPT (example notebook, read as text only); which throughput the column measures is checked
  against the paper/set data before use.
- Data handling decided after reading the archive STRUCTURE and throughput columns, BEFORE any capacity value (recorded with
  the study code `flagships/forge_flagships/kirkaldy_fade.py`): the per-cycle file's numbering restarts per ageing set and runs
  through cycler fault rows (~1e-10 A h at -0.16 V), so RPTs are placed by charge, not by cycle number: the row where the
  cumulative charge + discharge of the cycle rows is nearest the RPT file's own `Charge Throughput [A h]`. Expt 5: every RPT
  but the last aligns within 4.4 A h; the last falls 37-99 A h short (the final set's cycle rows are incomplete). Rule: an RPT
  is used only if it aligns within 10 A h (about one full cycle); otherwise it is skipped with the reason and never estimated.
  `Charge Throughput [A h]` counts charge + discharge (about 8 A h per cycle), confirming the throughput note above.
- Archives admitted: Expt 5 md5 298aa767e4e14acdb348f5832e0cbae9, Expt 4 md5 99083707bc7a24e72d9865abac19ce50 (both equal to
  Zenodo; sha256 in the study record). The Expt 4 download stopped once on DNS failures (network loss) and resumed per chunk.
- **Study `big14-a-kirkaldy-fade`: NOT MET** (`docs/flagships/big14/kirkaldy_fade_study.json`;
  `python -m forge_flagships.kirkaldy_fade --data D:/forge-data/kirkaldy2024/raw --out D:/forge-data/kirkaldy2024/study`).
  - Calibration (Expt 5, 8 cells, 120 checkpoints): k_q 5.77e-5 per A h of discharge, activation energy AT ITS LOWER BOUND (0):
    fade is not monotone in temperature (10 degC cells fade most, ~22-27 % at the last aligned RPT; 25 degC least, ~18 %;
    40 degC ~21 %), which an Arrhenius factor cannot represent. Calibration RMSE 0.040.
  - Holdout (Expt 4, 8 different cells, 64 aged checkpoints; the reference RPT is excluded from the criteria after review
    M2, values with it in brackets): C1 pooled RMSE 0.0374 (0.0353) > 0.015 NOT MET; C2 mean signed residual 10 degC 0.0061
    (0.0054) met, 25 degC 0.0274 (0.0243) NOT met, 40 degC 0.0065 (0.0058) met. Max |residual| 0.105.
  - Uncertainty budget: numerical not applicable (closed form); parameter (leave-one-cell-out) k_q 5.49e-5 to 5.95e-5,
    CONDITIONAL on the activation energy at its bound; activation energy NOT ESTABLISHED (at the bound in 8/8 refits); measurement UNKNOWN (no repeated capacity check of an unaged cell in
    the summaries); model discrepancy NOT QUANTIFIED (unknown, not zero) because the holdout failed.
  - Reported, not judged: flagship A's declared fade (k_q 2e-4 per A h of |I|, 30 kJ/mol), applied with the |I| throughput
    flagship A feeds it, OVERPREDICTS the fade of these cells at every temperature; 38 of 64 predictions exceed the model's
    declared state range (fade < 0.5), so the RMSE (0.905) shows the direction, not a meaningful magnitude. Temperature is the
    setpoint, not flagship A's mean cell temperature. LG M50T is not flagship A's LG M50; this is an observation, not a
    correction of flagship A.
  - The last RPT of every cell is skipped (the per-cycle file does not reach its throughput); measured set temperatures run
    above setpoint at 10 degC (14-24 degC) and 25 degC (27-30 degC) through self-heating; the setpoint is used as registered.
- `pytest flagships/tests/test_kirkaldy_fade.py` (Windows 3.14): 4 passed. `recertification_scope explain` on every changed
  path: ordinary.
- forge-scientific-review of the study, one round: CHANGES REQUIRED, none able to turn NOT MET into MET; all addressed:
  H1 a bound-pinned activation energy carried a ~1e-12 "spread" -> NOT ESTABLISHED, k_q spread labelled conditional;
  M1 rules not in the pre-registration -> `deviations_from_preregistration` in the record with decision times and coverage
  (calibration 120/128, holdout 72/80 RPTs); M1a per-row alignment gaps emitted (holdout max 4.76 A h), the skip of the most
  aged RPT noted as biasing TOWARD MET; M2 reference RPT excluded from C1/C2 (moves AWAY from MET), both values reported;
  M3 C2 needs all three registered temperatures; M4 declared-parameter comparison relabelled (throughput as flagship A,
  temperature = setpoint) and out-of-state-range predictions counted; M5 independence now compares rig channels from
  experiment_metadata.xlsx (disjoint), the old key-based guard could never fire; M6 a blank RPT throughput is skipped, not
  zeroed (one Expt 4 cycle row with both capacities blank is counted in the record); M7 tests for every refusal path and the
  law pinned to ThroughputArrheniusFade.advance; L1 pre-registration sha256 pinned (da6ac0da..., the dd53eec7 bytes);
  L2 classification says level 7 NOT REACHED; L3 Expt 4 'Discharge Capacity' is gross drive-cycle discharge (5.87 vs 3.17 A h
  charge per cycle), recorded as a deviation; L4 measurement UNKNOWN stays a stated assertion.
- `pytest flagships/tests/test_kirkaldy_fade.py` (Windows 3.14): 9 passed.

## 2026-10-09 BIG 14 — Kirkaldy fade study closed NOT MET; branch synced with main after PR #120

- PR #120 (R1/R4, certified source `3e396bc4`, certificate child `d383eed0`) merged into main as `2c0e024b` (merge commit,
  parents `16c87f40` + `d383eed0`). `main` was merged INTO `feat/big-14-a-kirkaldy-fade` as `343b8937` (no rebase, so the
  pre-registration commit `dd53eec7` keeps its place before the results). The only conflict was an append/append in this file,
  resolved by keeping main's entries first and this branch's entry verbatim after them.
- Pre-registration blob `0668576d` (sha256 `da6ac0da...`, the value pinned in the study record) is unchanged before and after the
  merge; no file under `flagships/` or `docs/flagships/big14/` changed in this sync.
- Closure: the throughput-Arrhenius campaign ends as a justified negative result, NOT MET under its registered criteria. No
  threshold or split changed; the five recorded `deviations_from_preregistration` stand (one biases toward MET), and the
  outcome is NOT MET with or without the reference RPT. Activation energy NOT ESTABLISHED (bound-pinned in 8/8 refits;
  the refits' ~1e-13 J/mol spread is optimizer noise, not uncertainty). Model discrepancy NOT QUANTIFIED. The holdout is
  independent of calibration in cells (disjoint rig channels) and discharge profile only; laboratory, dataset programme, RPT
  procedure and cell type are shared, and batch independence is not claimed (pre-registration stated limit). Summary in `docs/flagships/README.md` ("BIG 14 status").
- forge-scientific-review of this close-out prose (static, one round): CHANGES REQUIRED, no BLOCKER/HIGH, none able to turn
  NOT MET into MET; all applied in prose: M "nothing changed" overstated (now names the five deviations); L reported-not-judged
  comparison no longer called evidence; L measurement UNKNOWN added; L shared rigs 2 and 5 added; L non-monotone claim cites
  `calibration_residuals_per_temperature`. Open item (not fixed, a post-result record edit is out of this pass's scope): the
  pre-registration said the leave-one-cell-out spread would be carried as parameter uncertainty; the record instead reports
  activation energy NOT ESTABLISHED (conservative) and does not list this among its deviations.
- Next fade law (non-monotone temperature dependence or other): NOT STARTED. It needs a new hypothesis, pre-registration,
  complexity control and a fresh confirmatory holdout; the observed Expt 4 holdout is exploratory evidence for it at most.
- Commands (Windows, phyx/.venv CPython 3.14.2 -- not a CI interpreter; PYTHONPATH=<worktree>/src;<worktree>;<worktree>/flagships;
  TMP=D:/forge-tmp-fade), final tree: `pytest flagships/tests/test_kirkaldy_fade.py`: 9 passed;
  `pytest -n 4 flagships/tests tests/test_agent_workflow_contract.py tests/test_repository_architecture.py
  tests/test_engineering_contracts.py tests/test_system_runtime_checkpoint.py tests/test_system_runtime_review_fixes.py`:
  189 passed, 53 skipped (provider-gated); `tools/forge_check.py --changed`: 225 passed; `recertification_scope explain` on
  every path changed against main: ordinary. The committed study record is byte-identical to
  `D:/forge-data/kirkaldy2024/study/kirkaldy_fade_study.json`; the study was not re-run and nothing was re-downloaded.
  Local Assurance / recertification: NOT RUN (no protected path changed).

## 2026-10-09 Big Rocks expansion program — platform foundations (branch `claude/adoring-cray-jj367z`)

- Owner-directed breadth program alongside BIG 14 (BIG 14 tasks unchanged). Base `origin/main` @
  `446370651bc1630daf55b9dc0e7db9189946f0fa`; final source SHA `d8b99d45` (this PROGRESS entry is a docs-only commit after it).
  Cloud container, Linux, CPython 3.12.13 (`.venv`), Gmsh 4.15.2 available; OpenVSP, OpenRadioss, Project Chrono, FEniCSx,
  CalculiX, Code_Aster, SU2, OpenFOAM, PyBaMM, Cantera, CoolProp, TESPy NOT available. Not pushed; no PR (owner instruction).
- Built (map and invariants: `docs/architecture/big_rocks_foundations.md`): provider-neutral geometry + parametric variants +
  general Gmsh adapter (`spatial/`); assembly topology, multibody declarations, Scientific Twin revisions, product templates for
  drone/vehicle/motor/HVAC (`systems/`); provider health/qualification (`providers/health.py`); discovery grammar,
  multi-fidelity, history, hierarchy, search (`design/`); Scene IR (`engineering/scene.py`); MCP describe/plan/run tools
  (`mcp/foundations.py`); fail-closed adapters `providers/{openvsp,openradioss,chrono}` (translations UNVERIFIED); the geometry
  vertical slice (`flagships/forge_flagships/geometry_slice.py`, verdict insufficient_evidence by construction).
- forge-scientific-review, four rounds, all CHANGES REQUIRED, all findings fixed or recorded (commit messages 129a4690,
  6fe3b6fe, 040a93ab, b6a8a9eb list each finding): geometry/provider identity (H1-H4, M1-M8), twin/evidence (H1-H3, M4-M6),
  discovery authority (H1-H3, M4-M9), integrated slice/products/MCP/scene (H1-H2, M3-M8). Deferred: twin vocabulary overlap
  (round 2 LOW-8) and the items in the DEFERRED_HARDENING ledger.
- Commands and results (final source `d8b99d45`, same container):
  - `python -m pytest -m "not expensive" -q -n 4 -p no:cacheprovider`: 15 failed, 9546 passed, 134 skipped. The same 15 node ids
    run on the pristine base worktree (`git worktree add --detach <dir> 44637065`): 13 fail there too (freeze-manifest /
    core-freeze v3-v4 / batch56 / mutation-workspace tests: environment drift in this container, git-override refusals);
    `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` fails only on the branch (certified files changed:
    recertification required, see below); `tests/test_formal_xdist.py::test_real_xdist_infrastructure_failure_never_earns_credit[worker_lost_before_target-reasons1]`
    failed once under load and passed in the two earlier FAST runs and 7/7 in isolation (timing-sensitive; not caused by this change).
  - Skip admission audit of that FAST JUnit: skipped 134, accepted 134, unexpected 0 (new: chrono 1, openvsp 1, openradioss 1).
  - `python tools/forge_check.py --changed`: 108 passed. `python tools/forge_check.py --regression`: 225 passed. `git diff --check`: clean.
  - Targeted: `pytest tests/foundations providers/{chrono,openvsp,openradioss}/tests flagships/tests/test_geometry_slice.py
    tests/mcp/test_foundations_tools.py`: all passed, 3 skipped (provider-gated real runs).
  - `recertification_scope classify --event pull_request --base 44637065 --head HEAD`: recertify_source (tests/**, pyproject.toml,
    tools/certification/skip_admission.py, src/engcore/mcp/server.py).
  - Hardened-core recertification / Local Assurance: NOT RUN. It writes `certification/current_core_v2.json`, which the owner
    instructed not to touch while the Trust Repair certification is in flight, and this container fails the freeze-manifest
    tests on the pristine base. SCIENTIFIC tier (`-m "not campaign"`): NOT RUN.
- Failed approaches / dead ends: `pip download pychrono` fetched an unrelated PyPI timing library of the same name (the Chrono
  probe now refuses it by API identity); openvsp.org is blocked by the egress policy; the OpenRadioss release API returned 403.
  A `ruff --fix` over `src/engcore/design` edited three pre-existing modules; they were restored byte-for-byte (0a0cb89f) —
  autofix is run only on files this program owns.

## 2026-10-09 Big Rocks — next three rocks (branch `claude/adoring-cray-jj367z`, grows PR #124)

- Owner-directed: (1) provider reality + qualification path, (2) executable drone product coupling, (3) TwinRevision
  evidence and DesignHistory in SRIA. Final source SHA `e572ea61` (this entry is a docs-only commit after it). Same cloud
  container, CPython 3.12.13 `.venv`. Commits: db78090b, cb95139a, 0535be53, 5c03b65c, 9a9c5c98, be21e65a, e572ea61.
- Provider environments (micromamba 2.9.0 bootstrapped from conda.anaconda.org; conda-forge only; `$HOME/mm/root/envs`,
  the `FORGE_PROVIDER_ENVS` layout): `chrono` (python 3.12, pychrono 10.0.0 + chrono 10.0.0), `fenicsx` (fenics-dolfinx 0.11.0,
  petsc4py, mpich, gmsh 4.15.2, meshio, scipy), `calculix` (calculix 2.23). Repo installed into the first two with
  `pip install --no-deps -e .` plus pint/pytest. OpenVSP and OpenRadioss: not on conda-forge, PyPI 404, openvsp.org blocked,
  GitHub releases 403 — NOT_INSTALLED, fail-closed.
- Real-run findings (Chrono 10.0.0): `ChMatrix33d.SetItem` does not exist (orientation now a plan quaternion); the NSC
  default solver PSOR did NOT hold the pendulum's bilateral revolute joint (4 mm length drift, no zero crossing in 2 s), while
  SPARSE_QR / SPARSE_LU / MINRES reproduced the period — the solver is now a required declaration (direct solvers only);
  conda-forge pychrono installs no dist-info and Chrono 10 has no `GetChronoVersion` (identity now bound to the conda
  records, the bytes of pychrono's .py/.so and chrono's shared libraries, and the env digest).
- Commands and results:
  - `$HOME/mm/root/envs/chrono/bin/python -m pytest -q providers/chrono/tests tests/foundations/test_provider_qualification.py`
    (rootdir/config = repo): 17 passed (both pendulum reference routes executed against Chrono 10.0.0).
  - `$HOME/mm/root/envs/chrono/bin/python tools/provider_routes.py chrono --out <ledger.json>`: rc 0;
    `chrono.pendulum_period.euler_implicit_linearized+sparse_qr` PASSED, relative error 1.3846e-07 (tolerance 1e-5);
    `…+sparse_lu` PASSED, 1.3846e-07; provider 10.0.0 digest `201e5097…`. Re-run after the Codex fixes changed the adapter
    source: adapter `0.3.0+src.209ff35ec371409e`, runs `621ee840…` / `22044e33…`, ledger head `daa2e259…` (the earlier
    adapter `…7883f603…` runs `75ab3a90…` / `8c49eb09…` do not transfer to it, by design). A route run is a check of one translation, not a qualification;
    no qualification was issued.
  - `FORGE_PROVIDER_ENVS=$HOME/mm/root/envs $HOME/mm/root/envs/fenicsx/bin/python -m pytest -q providers/fenicsx/tests
    providers/calculix/tests flagships/tests/test_geometry_slice.py tests/foundations`: 133 passed (FEniCSx suite, CalculiX
    suite incl. the FEniCSx-vs-CalculiX comparison, the slice's FEniCSx rung, foundations). Without the separate `calculix`
    env (ccx on the fenicsx env's PATH) the comparison is refused "independence UNKNOWN: calculix declares no dependency set"
    — correct fail-closed behaviour, recorded as a failed approach.
  - `python -m pytest -m "not expensive" -q -n 4 -rfE -p no:cacheprovider --junitxml=…` on `e572ea61`: 14 failed, 9577 passed,
    135 skipped. The 14 are exactly the base-drift set recorded in the previous entry (13 freeze-manifest / core-freeze v3-v4 /
    batch56 / mutation-workspace tests that also fail on the pristine base in this container) plus
    `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` (recertification required).
  - `python -m tools.certification.skip_admission audit --suite junit_fast` on that JUnit: skipped 135, accepted 135,
    unexpected 0, report/availability problems 0.
  - `python tools/forge_check.py --changed`: 225 passed. `--regression`: 225 passed. `git diff --check`: clean.
  - Targeted: `pytest -n 4 tests/test_core_guards.py tests/test_core_semantic_invariants.py tests/test_core_api_layering.py
    tests/test_repository_architecture.py tests/test_sria_*.py tests/test_audit_sria_*.py tests/foundations`: 1204 passed.
  - `recertification_scope classify --event pull_request --base 44637065 --head HEAD`: RECERTIFY (adds
    `src/engcore/sria/campaign/events.py`: mutation_targets). CORE_CERTIFIED `sria/campaign/runner.py` not modified.
  - Hardened-core recertification / Local Assurance: NOT RUN (writes `certification/current_core_v2.json`, which the owner
    instructed not to touch). SCIENTIFIC tier (`-m "not campaign"`): NOT RUN.
- forge-scientific-review, three rounds, all CHANGES REQUIRED, all HIGH/MEDIUM fixed (commit messages list each):
  Rock 1 (0535be53: unbacked qualifications, forged/hidden route runs, in-memory build pinning, PSOR/HHT defaults, tolerance
  basis, file-byte identity, adapter source digest); Rock 2 (5c03b65c: infeasible duty reported as computed, unbounded winding
  temperature, a balance that could not fail, Kv unit 2π ambiguity, runaway reason); Rock 3 (be21e65a: look-alike belief,
  unassessed verification, model binding / omitted contradictions, anchors appended around the runner).
- Failed approaches / dead ends: the SRIA bridges were first written under `engcore.sria` and broke GUARD 18 (SRIA may import
  only `scientific`); they now live in `engcore.claims`, and SRIA gained only a generic `RECORD_CHAIN_ANCHORED` primitive.
  A 2 s pendulum window with step-quantised crossings gave a single crossing interval and a 1e-3 tolerance with no margin;
  replaced by 10 s, interpolated crossings, 1e-5 from a stated error budget.
- PR #124 Codex review (4 threads on the first program's commit), all verified real and fixed: joint graphs with a cycle where
  each child has one parent (A->B, B->A) are refused; inertia is checked on its eigenvalues (a positive diagonal admitted
  `[[1,2,0],[2,1,0],[0,0,1]]`); Chrono joint outputs are refused at translation instead of failing the run;
  `GeometryVariant.verify` compares the whole replayed variant (shape digest, builder, receipt), not only the geometry digest.
  `pytest tests/foundations providers/chrono/tests tests/mcp/test_foundations_tools.py flagships/tests/test_geometry_slice.py`:
  119 passed, 2 skipped (provider-gated); chrono env `providers/chrono/tests`: 12 passed.
- Re-gate on `e5e3a81c` (after the Codex fixes): `python -m pytest -m "not expensive" -q -n 4 -rfE -p no:cacheprovider
  --junitxml=…`: 14 failed, 9577 passed, 135 skipped — the same 14 node ids as above; skip admission audit: skipped 135,
  accepted 135, unexpected 0. Hardened-core recertification and the SCIENTIFIC tier: still NOT RUN.

## 2026-10-09 Roadmap V2 — checkpoint 1: discovery authority + FidelityGraph (branch `feat/roadmap-v2-discovery`)

- Stacked on PR #124 head `6656042099796921572d7ef81600750b4ba576fe`; PR #124 frozen except critical fixes. Owner decision:
  no provider breadth, no product depth; build discovery + falsification authority (Roadmap V2 R1-R8).
- DISCOVERY_AUTHORITY_MAP: `docs/architecture/discovery_authority_map.md` (source-level inventory by three read-only
  explorers). CANONICAL_HYPOTHESIS_OWNER: `sria.decision.hypotheses.Hypothesis` (extended, M4G bytes preserved).
  CANONICAL_EXPERIMENT_PLANNER_OWNER: `sria.decision` (ActionFamily + one UtilityEngine); external engines/LLMs only via
  `sria.decision.external.ExternalSuggestion`; `claims.next_experiment.PLANNING_FAMILY` maps gap actions onto it.
  DUPLICATE_TYPES_FOUND: 3 hypothesis types, 4 candidate/hypothesis status vocabularies, 2 planning vocabularies, 2
  `FidelityRung` classes, 3 gap vocabularies (actions per type in the map). FIDELITY_GRAPH_DESIGN: `design.fidelity_graph`
  on the existing ladder/multifidelity (measured links, policy-bound admission, elimination only through an admitted
  in-domain quantified link, recorded stratified audit, suspension, resurrection). MIGRATION: additive only; no
  CORE_CERTIFIED file modified.
- HOSTILE_REVIEW_RESULTS: forge-scientific-reviewer on 17526a32 — CHANGES REQUIRED: 6 HIGH (admission settable/carried
  over; declared domain; fabricated eliminations; gameable audit; audited false elimination stays eliminated; assertable
  hypothesis status), 6 MEDIUM, 7 LOW. All HIGH and MEDIUM fixed in 0cf5aac3 with a regression test each; L1-L7 fixed.
- TARGETED_TESTS (this container, `.venv`, CPython 3.12.13):
  - `pytest tests/foundations/test_v2_discovery_authority.py tests/foundations/test_v2_fidelity_graph.py`: 9 + 25 passed
    (with `tests/test_sria_m4_decision.py`).
  - `pytest -n 4 tests/foundations tests/test_sria_*.py tests/claims tests/test_core_guards.py
    tests/test_core_semantic_invariants.py tests/test_core_api_layering.py`: 1771 passed.
  - `ruff --select F` on changed files: only pre-existing F401s in untouched `sria/decision` modules.
- Discovery providers: conda-forge envs `discovery` (pysindy 2.1.0, botorch 0.17.2, pytorch cpu) and `dakota` (6.16.0)
  created under `$HOME/mm/root/envs`; PySR needs Julia packages from the Julia registry (not attempted yet). No adapter yet.
- PENDING_ROADMAP_TRACKER_SYNC: no roadmap tracker exists on this branch; `docs/performance/core-performance.md` is the
  performance tracker and is updated in R8.
- Failed approaches: none at this checkpoint (a first FidelityGraph draft trusted any 'admitted' audit event and a
  caller-chosen audit seed; replaced, see review above).

## 2026-10-09 Roadmap V2 — checkpoints 2 and 3: Blindfold + escrow + isolation; falsifiers + multiplicity + novelty

- R3/R4 (FORGE Blindfold, new non-Core package `engcore.blindfold`; dbb65ecc): L5 synthetic universes (invented dimensions,
  dimensionless groups, non-textbook exponents, per-instance constants, power/exp/two-term/regime forms), controls
  NO_SOLUTION / INSUFFICIENT_EVIDENCE / INDISTINGUISHABLE / SPURIOUS_CORRELATE / CONFOUNDED, an escrow with one bytes
  entry point (in-process + subprocess transports, both labelled SECURITY_BOUNDARY_NOT_PROVEN), hash-chained HMAC-keyed
  query log, budgets, one sealed submission per universe, roles proposer -> admission -> evaluator -> adjudicator -> reporter.
- Checkpoint-2 hostile review (forge-scientific-reviewer) — CHANGES REQUIRED, 7 HIGH / 8 MEDIUM / 6 LOW; fixed in 2bd429c2
  (operator credential; inadmissible = -1; INDISTINGUISHABLE redesigned and verified dimensionally homogeneous with in/out
  margins; CONFOUNDED made real confounding scored on the interventional expectation; strict replay; credit over the best
  constant answer; canonical monomial structure digest; careful baseline pairing). Re-review — CHANGES REQUIRED, 1 HIGH
  (overflow killed the escrow) / 5 MEDIUM; fixed in b1e4714d (catch-all + guarded logging; pair hit needs mutual in-box
  agreement within 1 sigma, outside divergence, truth contained or bracketed; proposer crashes scored inadmissible; NO_SOLUTION
  noise like INSUFFICIENT; discovery vs control credit; allow-listed boundary labels; config digest declared at create).
- R5 (10ab0a8e): `claims.falsification`, `claims.multiplicity`, `claims.novelty`. Checkpoint-3 review — BLOCKER (caller-
  supplied prediction; forgeable/selective verdict store; self-reported exposure clock; unbounded k; NaN -> NOT_REFUTED; ...);
  fixed in 601ae459 (ExposureAuthority owns the clock; prediction/k/resolution sealed; verdicts in the registry chain).
  Re-review — BLOCKER (unjudged refuting releases; conditions unchecked) + 8 HIGH; fixed in dd289ed5 (judge-all on
  apply; conditions required; refutation follows the hypothesis id; RegistryAnchor; seal-time vacuity guards; novelty ledger
  on the authority clock with first-proposal ordering, canonicalizer self-test, declared equivalence, verify_novelty;
  multiplicity close()/verify_promoted, campaign ids never reused).
- Scientific design decisions taken (recorded so they are reviewable): (1) INDISTINGUISHABLE is by construction
  observationally equivalent in the box to a DISCOVERABLE universe with an extended region; it measures calibrated refusal to
  extrapolate, and a bracketing pair is credited without knowing which branch is true. (2) A refutation follows the
  hypothesis id; a narrower or different claim is a new hypothesis (`derive_hypothesis`). (3) Identical values from two
  acquisitions are two measurements; an acquisition re-released keeps its first exposure.
- Baseline scan (20 master seeds, MIX 8/3/3/3/3/3, DEFAULT_CREDIT): mean total / over-best-constant / discovery / control
  credit — always_law -14.1 / -18.6 / 0.3 / -14.4; always_refuse 3.0 / -1.5 / 0 / 3.0; always_insufficient 4.5 / 0.0 / 0 /
  4.5; single_setting (non-discoverer) 7.25 / 2.75 / 0 / 7.25; careful 10.1 / 5.6 / 1.15 / 8.95 (discovery success 0.16).
  Finding: careful is mostly a control classifier; in 6/20 seeds its discovery credit is not above the non-discoverer's,
  so the test asserts only the properties that held on 20/20 seeds and uses a fixed seed.
- TARGETED_TESTS (this container, `.venv`):
  - `pytest -q -n 4 tests/foundations/test_v2_falsifiers_multiplicity_novelty.py tests/foundations/test_v2_discovery_authority.py
    tests/foundations/test_v2_blindfold.py tests/foundations/test_v2_fidelity_graph.py tests/test_core_api_layering.py
    tests/test_core_semantic_invariants.py`: 162 passed, 1 failed (`test_credit_is_reported_over_the_best_constant_answer`,
    random master seed — fixed by seeding; re-run `pytest -n 4 tests/foundations/test_v2_blindfold.py`: 14 passed);
    `pytest tests/foundations/test_v2_falsifiers_multiplicity_novelty.py`: 8 passed.
- DEFERRED_HARDENING (LOW / design, recorded): Blindfold M7 SPURIOUS driver settable (weak control); L1 refusals free and
  unbounded in the log; L5 replay identity is the store writer's record, master seed held by the operator; L6 no exogenous
  u1 twin world, so CONFOUNDED law_pass is unreachable passively. R5 M2 no persistence/attestation of authority keys,
  registries or ledger seals (per process); M4 falsification retries (content revisions, falsifier versions) are not counted
  in multiplicity; forbidden-region relevance to the prediction is a preregistration-review judgment. All in-process
  separation is construction, not isolation.
- Failed approaches: (1) value-content de-duplication of evidence (blocked genuine repeat measurements); replaced by
  acquisition identity. (2) A free-standing VerdictStore (forgeable/selective); replaced by the registry chain. (3) Binding
  verdicts to a content digest that included the falsifier list (a falsifier revision minted "new content" and shed a
  refutation). (4) An unnormalised exp(-b g) form underflowed outside the box; replaced by a saturating form. (5) The rival
  law added as law + k law g^m exceeded the 96-node limit; written as law (1 + k g^m).

## 2026-10-10 Roadmap V2 — checkpoints 4 and 5, R8, battery readiness, final gate (branch `feat/roadmap-v2-discovery`)

- R6 Scientific Red Team (`claims.redteam`, `claims.redteam_suite`; cd2a16b7): declared attack space (every range has a
  source and a unit), seeded deterministic plan (digest binds space, budget, seed, edge-interior points, replay tolerance),
  replay of every candidate, cross-FAMILY confirmation (neither the candidate's nor the claim's route votes; skipped or
  unconverged voters -> UNCONFIRMED), artifact dismissal only by an ATTACKED refined route of the same family, TrustEnvelope
  `engcore.claims.trust_envelope/2` with outcomes FALSIFIED / SURVIVED / UNKNOWN (no SAFE). Seeded flaw suite: 7 flaws +
  an interior-only violation + 1 declared blind spot + 5 controls. Checkpoint-4 review — CHANGES REQUIRED (6 HIGH, 6
  MEDIUM); fixed in 4c67ad4a. Confirmation review — 3 MEDIUM + LOWs, fixed in a8ab8d22; second confirmation: no HIGH or
  BLOCKER on the Red Team side.
- SEEDED_FLAW_RESULTS (`run_suite()`, deterministic): detection_rate 1.0, false_alarm_rate 0.0, controls_as_expected 1.0,
  cross_family_confirmation_rate 1.0, evaluations to a confirmed counterexample min 13 / max 70 / mean ~26.1;
  blind_spots_missed = [flaw_outside_attack_space] (by design: a flaw outside the declared space is not found, and the
  SURVIVED statement names the region it covered).
- R7 credibility vectors (`claims.credibility_vector`; ceb99deb): f(C) projected from the existing ValidationLevel and UQ
  channel vocabulary over one EvidenceGraph; r(D) only from a registered, immutable, risk-monotone policy that dominates
  RISK_POLICY_V1; g = r - f with UNKNOWN below every level; defeaters; AND = weakest, OR = one whole positively independent
  branch. Review rounds: checkpoint-5 BLOCKER (caller-declared levels, policy as evidence, ...) -> 631bcb88; confirmation
  CHANGES REQUIRED (6 HIGH) -> a8ab8d22; second confirmation BLOCKER (subject/lineage contradictions ignored and child-order
  dependent; contradiction scope only over the selected support; superseded records revived by removing a pin; applicability
  and UQ as bare labels; outside-domain cancelled by a second citation; envelope bound only by claim id; calibration guard
  bypass) -> 8c2ed4dc; third confirmation BLOCKER (an unpinned SUPERSEDES edge lifted an outside-domain finding;
  contradicted calibration data dropped silently; same-content twins escaped contradiction / supersession; inputs not bound;
  an 'unknown' check outranked; NOT_APPLICABLE without provenance; obsolete subject not defeated) -> fbf79417; fourth
  confirmation CHANGES REQUIRED, no BLOCKER (1 HIGH: a linking edge exempted an obsolete subject; MEDIUM: OR branch choice
  not monotone in the requirement, independence and the calibration guard blind to shared calibrators / twins, a model's own
  zero model-form entry met 'declared', contradiction direction decided defeater vs note) -> f4513eb0; fifth confirmation
  CHANGES REQUIRED, no BLOCKER (1 HIGH: with both ends of a contradiction in the closure only the source was checked, so
  citing the contradicting record or an UNKNOWN lineage node lifted it; LOWs: no-op OR assertion, stale docstring, closing
  superseder twins) -> 759ed9bb; sixth confirmation CHANGES REQUIRED, no BLOCKER/HIGH (MEDIUM: a closing "v2" with the
  same content, or itself superseded, lifted a defeater; LOWs: closer contradicted only one way, explicit defeater could
  replace a computed one, docstring) -> f320c156; seventh confirmation APPROVED (no BLOCKER/HIGH/MEDIUM). Its one
  lifting LOW (L-b: a cited record pinned as a newer version of the applicability source could close the outside-domain
  finding; needs a trusted pin) was fixed post-approval in 1e7cbebc (lowering-only; not re-reviewed).
  Design decisions: applicability-inside is backed by a re-read `system_runtime.records.ApplicabilityReport`
  'within' whose evidence digest is the subject's content digest; UQ by a re-read `sria.assurance.uncertainty_budget.ChannelEntry`
  of that channel (quantified = KNOWN/BOUNDED with the channel's own UncertaintySource; UNKNOWN backs nothing;
  NOT_APPLICABLE backs only 'declared', with pinned provenance, from an authority that could have quantified the channel, and
  NEVER for model form — declaring model-form discrepancy impossible would turn missing discrepancy into zero); support
  disqualification follows the canonical any-SUPERSEDES rule, a supersession of what the subject rests on is a 'superseded'
  defeater; "rests on" = twins + ancestors (not through SUPERSEDES) + calibration inputs; an outside-domain finding is
  judged like a defeater; OR chooses a branch by the requirement first (requirement_met is monotone; per-factor levels
  are those of the chosen branch); a CONTRADICTS edge is a conflict whichever side wrote it; a model-form statement at any
  level needs an outside authority with pinned provenance; a validator sharing any record with the data that calibrated the
  subject is refused (hold-out siblings of one raw dataset too — over-conservative by choice); the report binds
  `inputs_digest` (schema `engcore.claims.credibility_vector/3`); the attacked statement is declared on the claim leaf and
  bound into the structure digest.
- R8 (c8853038, c3bb5f91): `claims.discovery_providers` + `providers/discovery/*` runners in separate envs; PROVIDER_STATUS
  pysindy / botorch / dakota EXECUTED_IN_PROVIDER_ENV (not qualified), ax / pysr NOT_INSTALLED. Proposers return PROPOSED
  hypotheses / ExternalSuggestion / untrusted raw output, never a verdict. Live runs moved to `tools/discovery_provider_smoke.py`
  (opt-in) after the skip-admission audit flagged env-gated skips; smoke run: PySINDy recovered du/dt = -0.50015 u, BoTorch
  suggestion inside bounds, Dakota moments present. Performance: `tools/discovery_performance.py`, documented in
  `docs/performance/core-performance.md` §9 (20k candidates, seed 7: tier 0 ~33k/s; tier 1 screen+record ~3.4k/s, trust
  overhead ~292 us/candidate; tier 2 ~640 verdicts/s, seal O(releases); tier 3 ~33 universes/s; 50.7 useful promotions per
  compute-hour under a DECLARED 60 s high-fidelity cost; false-elimination rate 0.0 recorded audit and ground truth).
- Battery: `docs/architecture/battery_discovery_readiness.md` — NOT READY for a confirmatory experiment, READY to draft
  the pre-registration; Kirkaldy 2024 stays NOT MET; nothing was run, re-fitted or pre-registered.
- TARGETED_TESTS (this container, `.venv`, this session):
  - `pytest -m "not expensive" -q -n 4 -rfE -p no:cacheprovider` (before a8ab8d22): 14 failed, 9638 passed, 137 skipped
    (464 s). The 14 are the known base-drift set, unchanged from the base: `test_core_certificate.py::
    test_the_certificate_describes_this_tree`, 5 in `test_core_freeze_manifest.py`, 2 in `test_core_freeze_v3_manifest.py`,
    3 in `test_core_freeze_v4_manifest.py`, `test_core_scientific_audit_batch56::test_r65...`, 2 in `test_mutation_workspace.py`.
  - Foundations JUnit through the skip-admission audit after c3bb5f91: skipped 0, accepted 0, unexpected 0.
  - After 8c2ed4dc: `pytest -q -n 4 -p no:cacheprovider tests/foundations tests/test_core_api_layering.py
    tests/test_core_semantic_invariants.py tests/test_core_guards.py tests/claims tests/test_sria_m4_decision.py`: 1217
    passed. `pytest tests/foundations/test_v2_credibility_vector.py`: 20 passed; the 8 new review tests FAIL against the
    a8ab8d22 implementation (checked by swapping the module in). `python tools/forge_check.py --changed`: 225 passed.
    `git diff --check`: clean.
  - After fbf79417: same multi-suite command: 1224 passed. `pytest tests/foundations/test_v2_credibility_vector.py`: 27
    passed; 8 (7 new + 1 changed) FAIL against the 8c2ed4dc module. `forge_check.py --changed`: 225 passed.
    `ruff check --select F,E9` on both files: clean. `git diff --check`: clean.
  - After f4513eb0: same multi-suite command: 1231 passed. `pytest tests/foundations/test_v2_credibility_vector.py`: 34
    passed; the 7 new tests FAIL against the fbf79417 module. `forge_check.py --changed`: 225 passed. ruff F/E9 clean;
    `git diff --check` clean.
  - After 759ed9bb: same multi-suite command: 1233 passed. `pytest tests/foundations/test_v2_credibility_vector.py`: 36
    passed; the 2 new tests FAIL against the f4513eb0 module. `forge_check.py --changed`: 225 passed. ruff F/E9 clean;
    `git diff --check` clean.
  - After f320c156: same multi-suite command: 1235 passed. `pytest tests/foundations/test_v2_credibility_vector.py`: 38
    passed; the 2 new tests FAIL against the 759ed9bb module. `forge_check.py --changed`: 225 passed. ruff F/E9 clean;
    `git diff --check` clean.
  - After 1e7cbebc: same multi-suite command: 1236 passed; `pytest tests/foundations/test_v2_credibility_vector.py`: 39
    passed (the new test FAILS against f320c156); `forge_check.py --changed`: 225 passed; `forge_check.py --regression`:
    225 passed; `git diff --check` clean.
  - On 1e7cbebc: `pytest -m "not expensive" -q -n 4 -rfE -p no:cacheprovider --junitxml=...`: 14 failed, 9668 passed,
    135 skipped (453 s). The 14 failures are exactly the base-drift set listed above (certificate, freeze v1/v3/v4 manifests,
    batch56 r65, 2 mutation-workspace); no V2 test failed. 2 fewer skips than before c3bb5f91 (the live provider tests
    moved to the opt-in smoke tool).
  - NOT RUN: `pytest -m "not campaign"`, hardened recertification, Local Assurance.
- CERTIFICATION_SCOPE: `recertification_scope classify --event pull_request --base 6656042 --head HEAD` -> recertify_source,
  triggered only by test files (tests are certified harness). No CORE_CERTIFIED file, no `certification/current_core_v2.json`
  change; recertification NOT RUN; V2 is not certified.
- DEFERRED_HARDENING (recorded, LOW / design): Blindfold M7 / L1 / L5 / L6 and R5 M2 / M4 / forbidden-region relevance (see
  the checkpoint 2-3 entry); FalsifierRegistry.seal is O(releases) (needs an index); in-process construction residuals
  (registries, oracle declarations, `_POLICIES`, TrustEnvelope can be hand-built, TrustedSourceRegistry is caller-supplied);
  red-team route families are self-declared; ValidationCheck / ChannelEntry are not bound to the result value they qualify
  (ApplicabilityReport is, through its evidence digest); the attacked statement is what the claim leaf declares, not a
  contract record; removing defeater-type edges (CONTRADICTS, CALIBRATES, SUPERSEDES, DERIVED_FROM) from the graph raises the
  outcome (the graph fingerprint is bound in the report); omitting a NEGATIVE input (an 'outside' / 'unknown' applicability
  report, a FALSIFIED / UNKNOWN / incoherent envelope) is detectable only through the bound `inputs_digest`;
  `fresh_enough` is True when freshness is unknown and no timestamp is required. Seventh-review LOWs recorded, not
  changed (over-conservative only): citation edits can move requirement_met within what an honest claim earns (a claimless
  OR branch forces AND; citing a closer protects it) -- they are claim changes bound by `claim_structure_digest`; closer
  qualification is not a lineage fixpoint and `superseders` matches the exact record, not its twins.
- Failed approaches: (0) disqualifying superseded support by any admissible superseder AND routing the outside-domain
  claim through the same `usable()` gate — an unpinned superseder then lifted a defeater; defeater claims now bypass it.
  (1) lineage that skipped the subject via view state (`view.subject`) — fixed independence but hid
  contradictions of the subject and made results child-order dependent; replaced by a `stop` parameter. (2) Reusing the strict
  "closing" superseder bar to disqualify superseded support — removing a pin revived stale records. (3) A flaky-trap control
  with a small, stateful spike — not detected reliably; replaced by a call-parity spike. (4) Env-gated live provider tests in
  the certified harness — flagged by the skip-admission audit; moved to an opt-in smoke tool.

## 2026-10-10 Big Rocks — Authority Integrity → Real Escrow → Battery Blind Readiness (branch `feat/big-rocks-authority-escrow-battery`)

Base `origin/main` `4634eba2` (Big Rocks PR #124 and Roadmap V2 PR #125 merged). PR #123 (trust repair) was not used,
cherry-picked, rebased or depended on. TRUST_REPAIR_DEPENDENCY_CANDIDATEs (both certified lane) are in
`docs/architecture/authority_integrity_map.md`: durable signed SRIA admission declarations; binding `ValidationCheck`
itself to a result.

### Delivered

- **Rock 1, issuer-bound authority** (`engcore.authority`, non-Core):
  - the ledger:
    - an ed25519-signed, hash-chained, persistent (flock'd, fsync'd JSONL) ledger;
    - root-signed register / set_roles / rotate / revoke / `declare_compromise`, with proof of possession;
    - test and production profiles; TrustAnchor pinning; re-verification on open.
  - binding records to results:
    - attestations bind a record (whole) to the exact result (an output of an EXECUTOR-attested NodeReceipt), its
      context and its role;
    - `verify_evidence` refuses wrong-subject, wrong-context, wrong-role, self-issued, out-of-order, revoked and
      compromise-window evidence.
  - credibility in issuer-bound mode:
    - a FAIL check with no level caps every factor of its role;
    - negative applicability reports count on their attested subject;
    - an exact type is required for the ledger;
    - `requirement_met` is never true in test mode.
  - `DurableCampaign` journals exposure, falsifiers, multiplicity and novelty into the ledger and replays them with
    head checks: one owner, compromise-aware, failed resumes released.
- **Rock 2, real escrow**:
  - the service: escrow-owned 0700 storage (secret, signing key, keyed journal with a genesis canary); persistent
    budgets, submissions and query ids.
  - protocol v4:
    - MAC requests that bind last sequence and head;
    - authentication before any state is touched;
    - signed responses; clients always pin the escrow key;
    - durable client checkpoints for rollback and replacement.
  - integrity:
    - journaled keyed world digests;
    - a deleted or torn journal refuses to start;
    - `EscrowIntegrityError` is never a refusal;
    - the escrow always states SECURITY_BOUNDARY_NOT_PROVEN.
  - isolation demo (`engcore.blindfold.isolation`, `tools/blindfold_isolation_demo.py`): a launcher-verified Discovery
    domain (uid 65534, no capabilities, no_new_privs, private namespaces, tmpfs over the storage), two runs with an
    escrow restart, 21 attacks, and a canary substring scan with a positive control.
- **Rock 3, battery blind readiness**:
  - campaign records:
    - a pre-registration (21 sections; lexical content guard; confirmatory dataset as an identity allowlist;
      machine-readable rule with a declared u_obs and a stated blind spot), frozen and chain-checked;
    - DatasetManifest with salted per-row commitments (per-row key openings journaled) and design conditions;
    - an ExposureGate (owner approval, sealing/abstention, commitments);
    - `verify_discipline` re-derives the discipline from the ledger and manifests alone.
  - evidence of the right origin:
    - fit-receipt-bound seals and abstentions;
    - DiscoveryPassport + `verify_passport`, which re-derives every field from the records (credibility re-run;
      Red Team from attestations; every admissible attack on the claim must have survived; pre-registered plan;
      exact registered hypothesis; a discovery needs a bar that requires validation).
  - the battery flagship:
    - hypothesis set; frozen prior-art family snapshot with numeric equivalence;
    - pre-registration draft; fixed Red Team plan; synthetic dry run of the whole chain.
  - readiness: `docs/flagships/BATTERY_CONFIRMATORY_READINESS.md` (generated by `tools/battery_readiness_report.py`):
    **NOT_READY**, with five derived blockers.
  - preserved: Kirkaldy 2024 stays NOT MET (artifacts digest-pinned). **No confirmatory datum was exposed**; no
    confirmatory campaign was run.

### Reviews (forge-scientific-reviewer, read-only)

Every finding below was fixed, with a test, unless it is listed under deferred hardening.

| review | commit reviewed | result | fixed in |
|---|---|---|---|
| checkpoint A | f71f66d6 | CHANGES REQUIRED: B1, H1–H3, M1–M5 | 4a7c392e |
| checkpoint A re-review | 4a7c392e | CHANGES REQUIRED: H-1, H-2, M-1–M-5 | 708a3036 |
| checkpoint B | 4a7c392e | CHANGES REQUIRED: H1, H2, M1–M7 | b195e093 |
| checkpoint C | 7772e070 | CHANGES REQUIRED: H1–H4, M1–M9 | 47ac6a74 |
| combined final review | b195e093 | CHANGES REQUIRED: H-1–H-3, M-1–M-6 | 09781568 |
| verification 1 | 09781568 | CHANGES REQUIRED | 642e324c |
| verification 2 | bb4ff5c4 | CHANGES REQUIRED | 71e02d8e |
| verification 3 | 71e02d8e | CHANGES REQUIRED | 4532ea58 |
| verification 4 | 4532ea58 | CHANGES REQUIRED | 2df9ba1b |
| verification 5 | 2df9ba1b | **NO BLOCKER/HIGH/AUTHORITY-MEDIUM** | coverage test in f99f74d0 |

### Tests (this container, `.venv` CPython 3.12, this session)

- Focused suite: `pytest -q -n 4 -p no:cacheprovider tests/foundations tests/claims tests/test_core_api_layering.py
  tests/test_core_semantic_invariants.py tests/test_core_guards.py tests/test_sria_m4_decision.py
  tests/test_core_freeze_policy.py flagships/tests`. On 4532ea58: 1395 passed, 50 skipped. On 2df9ba1b a narrower run
  (`-n 2`, without the semantic-invariants and m4 suites) gave 1257 passed, 50 skipped.
  `tests/claims/test_preregistration_exposure.py` on f99f74d0: 21 passed.
- `python tools/forge_check.py --changed`: 225 passed. `python tools/forge_check.py --regression`: 225 passed (both on the
  tree after b195e093 plus docs). `git diff --check`: clean.
- `pytest -m "not expensive" -q -n 4 -rfE -p no:cacheprovider`:
  - on b195e093 + docs: 15 failed, 9740 passed, 135 skipped. The 14 base-drift failures listed below, plus
    `test_core_freeze_policy::test_the_policy_names_every_non_core_package` (the new `authority` package was not
    classified; fixed in `docs/CORE_FREEZE_POLICY.md`).
  - on 09781568: 14 failed, 9745 passed, 135 skipped, exactly the base-drift set.
  - on bb4ff5c4 and 4532ea58: 15 failed. The base-drift set plus `test_formal_xdist.py::
    test_real_xdist_infrastructure_failure_never_earns_credit[worker_lost_before_target-reasons1]`. Both of those runs
    overlapped a concurrent focused-suite run on the same 4 cores. The test passes alone (`pytest
    tests/test_formal_xdist.py::test_real_xdist_infrastructure_failure_never_earns_credit`: 7 passed), and the campaign
    does not touch formal/xdist code: classified load-induced.
  - on f99f74d0 (final source, run alone): **14 failed, 9750 passed, 135 skipped (427 s)** -- exactly the base-drift set below;
    the xdist test passed, confirming the load classification.
  - The base-drift set (unchanged from `main`, certificate / freeze manifests describe an older tree):
    - `test_core_certificate::test_the_certificate_describes_this_tree`;
    - 5 in `test_core_freeze_manifest.py`, 2 in `test_core_freeze_v3_manifest.py`, 3 in `test_core_freeze_v4_manifest.py`;
    - `test_core_scientific_audit_batch56::test_r65...`;
    - 2 in `test_mutation_workspace.py`.
- Isolation demo (root, unshare/setpriv available):
  - normal run: `run_isolation_demo` → OS_ISOLATION_BOUNDARY_VERIFIED, every check true (launcher-verified ids,
    capabilities, namespaces and tmpfs on both runs), 0 attacks succeeded, 175 980 files stat'd, 2.6 s;
  - positive control (`leak_control=True`): SECURITY_BOUNDARY_NOT_PROVEN, canary found in the planted partial copy;
  - `tools/blindfold_isolation_demo.py`: exit 0.
- Performance: `python tools/authority_escrow_performance.py --n 200`, recorded in `docs/performance/core-performance.md`
  §10. Ledger open ~0.42 ms/event; issuer-bound credibility 4.35 ms median; stored escrow observe 0.69 ms median.
- NOT RUN: `pytest -m "not campaign"`, Local Assurance, hardened recertification, and any certificate rewrite (forbidden
  during the build campaign).

### Certification scope

`python -m tools.certification.recertification_scope classify --event pull_request --base 4634eba2 --head HEAD` gives
`recertify_source`. It is triggered only by `pyproject.toml` (new optional extra `[authority]`) and test files (the
certified harness). No CORE_CERTIFIED source changed, and `certification/current_core_v2.json` is untouched.
Recertification is owner-run and NOT RUN.

### Deferred hardening (recorded, not authority-blocking per the final verification)

- Front-running availability: an issuer holding RED_TEAM plus operator/EXPOSURE roles can attest an honest envelope
  first and deny the independent citation. It fails closed.
- Forged or compromised NEGATIVE red-team records veto permanently (they only lower).
- The Red Team plan binding checks `plan_digest` only. The credibility leaf subjects and the Red Team claim route bind to
  the hypothesis by label.
- The escrow's rollback detection needs a client checkpoint; a Discovery client without one cannot detect a restored
  backup.
- The isolation demo record is unsigned. Attack results are the probe's self-report; the launcher-side /proc checks and
  the canary scan are not.
- Ledger open is linear in events; a checkpointed open is the obvious fix. `producers_of` is O(receipts).
- The pre-registration content guard is lexical. Readiness constants are module constants, cleared only by owner
  provisioning.
- Escrow LOWs: no "fetch sealed result" after a crash; `auth_failures` is not persisted; the per-process HMAC
  derivation is untagged (no exploitable collision found).

### Failed approaches (do not repeat)

1. Classifying releases by the caller's `partition` label: a release around the gate without a label read as
   exploratory. Fixed by classifying from manifest rows.
2. Reading the passport's credibility / envelope / hypothesis from caller-built objects: look-alikes passed. Fixed:
   credibility is re-run, the envelope is read from its attestation, the hypothesis is the exact registered one.
3. A negative red-team scan that excluded operator roles and compared sequences: it let a duplicate shadow a
   falsification. Negatives are now counted per record digest from any RED_TEAM issuer.
4. Running the not-expensive tier concurrently with another pytest run: the xdist infrastructure test flakes under
   load. Run the tier alone.
5. `ruff --fix` over pre-existing files: it churned imports against the repo's compact style. Reverted; only
   campaign-new files are auto-fixed.

## 2026-10-11 Planning consolidation (docs only; uncommitted working tree on `main` @ `4634eba`)

- Problem: conflicting execution authority — Master Plan §8.1 "Big Rocks First" + P0–P40, the Completion Policy's
  paused-expansion epic, PERFORMANCE.md's three-rocks-then-pivot policy, an 800-line ACTIVE_PLAN mixing history with
  tasks, and the Genesis contract present only in PR #127.
- Done: Master Plan rewritten as Part I strategy (authority map, Now/Next/Later/Superseded, timebox framework, Trust-lane
  circuit breaker, control-plane budget, evidence-maturity progress metric) + Part II architecture reference;
  ACTIVE_PLAN reduced to the live queue (G0 → A1 → A2 → B1) with OWNER_DECISION_REQUIRED OD-1..OD-13; Genesis (from
  PR #127 head `4872b10`) gained substrate inventory §4.1, baseline families §10.5, compute estimate §10.6, timebox
  policy §18.0, Step-0 circuit breaker, Step 2B demo, evaluator-ownership rule; PERFORMANCE.md lost execution authority
  and gained measurement labels and compute staging; Completion Policy gained the planning relationship; CLAUDE.md
  gained a planning-authority section. Old texts archived verbatim: `docs/archive/FORGE_MASTER_PLAN_2026-10-10.md`
  (+ PERFORMANCE appendix), `docs/work/archive/ACTIVE_PLAN_HISTORY_TO_2026-10-10.md`.
- Verified state used: certificate binds `3e396bc4` (not `main`); rulesets API 403; open PRs #123 (conflicts), #126,
  #127, #117 (conflicts), stale #107/#39/#24; ledger computed stages unchanged.
- Commands (this session, scratch venv CPython 3.13, pytest only):
  - `python -m pytest -q -p no:cacheprovider tests/test_agent_workflow_contract.py tests/test_capability_completion.py`
    -> 7 passed.
  - `python3 -m tools.capability_maturity` -> "Capability completion ledger is coherent."
  - `git diff --check` on this session's incremental tracked diff -> no live-document whitespace findings. This is not a claim that the full planning diff against `main` is clean.
  - FAST / SCIENTIFIC tiers, regression pack, recertification: NOT RUN (docs-only change).
- No code, test, threshold, result, maturity state or certificate changed. Not committed or pushed.
- Correction pass (same day, docs only): (1) authority is by scope, not a global precedence chain ("execution authority
  does not imply semantic authority outside the document's scope"); (2) Completion Policy: no blanket Track A/B
  exemption — A1 limited to benchmark/measurement infrastructure, A2 and new B1 foundations need the active epic changed
  or one fully specified owner-approved exception, anti-loophole rule added; (3) circuit breaker has three states,
  `UNCLASSIFIED` is the blocking default and `GOVERNANCE_ONLY` needs a six-question evidence record; (4) the PERFORMANCE
  appendix in the Master Plan archive was rebuilt byte-exact inside `~~~~` fences (the first version had demoted
  headings, so it was not verbatim). Archive check (sha256 of archive bodies vs `git show 4634eba:<path>`, per-section
  containment, appendix blocks vs original line ranges): PASS. Cross-reference audit: no broken references.
  `python -m pytest -q -p no:cacheprovider tests/test_agent_workflow_contract.py tests/test_capability_completion.py`
  -> 7 passed; `python3 -m tools.capability_maturity` -> coherent; `git diff --check` on the incremental correction diff -> no live-document whitespace findings (not a claim about the full planning diff against `main`);
  `recertification_reasons` for every changed path -> none (ORDINARY). FAST / recertification: NOT RUN.

## 2026-10-11 Planning consolidation landing

- Reconstructed the reviewed docs tree on `docs/planning-consolidation-2026-10-11` from `main` @ `4634eba`, including the B1 non-shortcut circuit breaker. No maturity, code, test, or scientific-result change.
- `py -3 -m pytest -q -p no:cacheprovider tests/test_agent_workflow_contract.py tests/test_capability_completion.py` -> 7 passed.
- `py -3 -m tools.capability_maturity` -> "Capability completion ledger is coherent."
- `git diff --check` against the full planning diff reports exactly two archive-only trailing-whitespace findings inherited byte-exact from the historical Master Plan; no live-document whitespace findings. The incremental cleanup diff was clean where applicable. Those historical whitespace lines were not removed or normalized; archive byte integrity is intentional.
- ARCHIVE_VERIFY: PASS (Master Plan body, ACTIVE_PLAN body, PERFORMANCE.md lines 26–53 and 126–189, SHA-256 byte match).
- FAST / Full Local Assurance: NOT RUN.

## 2026-10-12 Test-suite runtime (owner-requested; branch `perf/test-suite-runtime`, base `main` @ `8b028dc`)

- Problem: FAST (`-m "not expensive"`) had grown to ~13–17 min on a 2-core host. Measured cause: (1) the tier tables
  were last extended at ~3k tests; at 10.4k, FAST carried ~680 s of solver runs, result reproductions and studies;
  (2) source-scanning guards recomputed identical sweeps (guard_reach tokenized `src/` 4x per `verify()` and ~25
  `verify()` calls per session; the nested `from_dict` scan parsed ~750 files once per exempted name; the dependency
  sweep ran once per caller); (3) `AdmittedForwardTable.__post_init__` parsed one admission string 847,242 times for
  one TCR grid; (4) 70% of TCR forward solves in four inference modules repeated inputs already solved in the session.
- Done (no assertion, tolerance, threshold or selection changed; every relabelled test still runs in SCIENTIFIC/FULL):
  - `src/engcore/inference/grid.py`: each distinct exact-`str` admission record parsed once per table; non-`str`
    refs parsed every time; refusal order/messages unchanged; mutation B45a still matches once and is still killed.
  - `tools/certification/guard_reach.py`: `_strip_comments_and_strings` memoized on the text.
  - tests: dependency sweep cached per process (copies to callers); nested `from_dict` scan parses/walks each file
    once for all names; `applied()` locates each spec / digests each unmutated file once; deterministic immutable
    TCR posterior builds shared (`lru_cache`, one module fixture).
  - `tests/conftest.py` `EXPENSIVE_TESTS`: 19 reproduction / convergence / oracle-agreement / positive-control tests
    labelled `expensive`; fixture-sharing tests labelled together. Refusal, forgery, context-binding and
    verdict-separation tests deliberately left in FAST (FAST is CI's only Python 3.11 tier).
  - Equivalence (old HEAD helper vs new, same tree): `guard_reach.verify()`, `_reached_modules()`, nested
    `from_dict` sites (all 11 names + synthetic file of every counted form), `applied()` -> all identical.
- forge-scientific-review: CHANGES REQUIRED (F1 MEDIUM: memo had no adversarial test, two memo mutants survived every
  existing test; F2 LOW: a test tampered a now-memoized posterior; F3 LOW: refusal tests moved out of FAST lost 3.11
  coverage; F4 LOW: restructured scan had no adversarial test). All four fixed in `88a258f2`: new
  `tests/inference/test_admission_record_memo.py` kills all three memo mutants and B45a; F2 tampers a copy; 11
  refusal tests returned to FAST; synthetic scan test kills four scan mutants. No finding overruled.
- Commands (this session, Linux container, 2 cores, CPython 3.13.16, pytest 9.1.1, xdist 3.8.0; history fetched to
  depth 3000 so the freeze verifiers can resolve their commits):
  - `python tools/forge_check.py --changed` (base `main`) -> 40 passed.
  - `python tools/forge_check.py --regression` -> 225 passed.
  - Targeted: `python -m pytest tests/test_core_scientific_audit_batch45.py tests/test_guard_reach_ledger.py
    tests/test_mutation_population_v4.py tests/test_core_scientific_audit_batch55.py tests/test_core_semantic_invariants.py
    tests/test_core_guards.py tests/test_core_api_contracts.py tests/inference tests/hybrid_uq/test_hybrid_uq_identifiability_predictive.py
    tests/test_core_scientific_audit_batch25.py -q -n 2 --dist loadfile` (on `5429b9de`) -> 700 passed.
  - `python -m pytest tests/test_tier_classification.py -q` -> 9 passed.
  - FAST, MEASURED back to back on one host, `python -m pytest -m "not expensive" -q -n 2 -p no:cacheprovider`:
    `main` `8b028dc` -> 9 failed, 9641 passed, 167 skipped, **992 s** wall; branch `88a258f2` -> 9 failed, 9630 passed,
    167 skipped, **476 s** wall. Identical failure set: `test_core_certificate::test_the_certificate_describes_this_tree`;
    `test_core_freeze_manifest::test_a_descendant_that_keeps_the_contract_still_verifies`;
    `test_core_freeze_v3_manifest::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree`;
    `test_core_freeze_v4_manifest::{test_once_assured_the_full_verification_holds, test_the_deep_surface_carries_methods_and_member_positions, test_the_tree_keeps_the_core_freeze_v4_contract}`;
    `test_core_scientific_audit_batch56::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see`;
    `test_mutation_workspace::{test_local_telemetry_is_outside_manifest_and_cannot_verify_as_receipt, test_mid_walk_failure_still_reports_entries_already_scanned}`.
    These fail on unmodified `main` too (certificate binds `3e396bc4`; certified files changed since `d383eed0`);
    the v4 deep-surface ones may also reflect Python 3.13 (unsupported per OD-2). UNCLASSIFIED here.
  - SCIENTIFIC, same protocol, `-m "not campaign"`: `main` -> 27 failed, 10165 passed, 167 skipped, 14 errors,
    **1448 s**; branch -> 27 failed, 10176 passed, 167 skipped, 14 errors, **1024 s**. Identical failure/error set:
    the nine above plus 26 `tests/test_heterogeneous_ngspice.py` (no `wsl.exe` / ngspice on this host),
    `tests/mcp/test_problem.py` (1), `tests/test_cross_solver_consensus.py` (1),
    `benchmarks/empirical_validation` (1), `benchmarks/model_measurement_validation` (1).
  - FULL, campaign tier, CI (3.11/3.12), hardened recertification: NOT RUN.
- Side finding (not fixed): `benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::
  test_rebuilding_everything_reproduces_the_published_gates` rewrites the committed `SAFETY_GATES.json` (MV-10 PASS ->
  FAIL on this host); a test writing committed evidence is a hermeticity defect and races under xdist.
- Recertification: every changed file except `docs/` is in the certified scope (`certified:harness`,
  `certified:inference_admission`, `certified:certification_control`), so this branch needs the owner-run hardened
  recertification (OD-3). Not pushed for merge; not recertified.
- Failed approaches: (1) holding every product AST to share across names -- correct but ~300 MB per worker; replaced
  by parse-and-walk-per-file. (2) Parsing each file once but still walking it once per name -- only 63 s -> 36 s; the
  walk, not the parse, was the cost; one walk for all names -> 5 s. (3) Moving refusal tests out of FAST for speed --
  reverted after review (F3): it silently drops their Python 3.11 execution. (4) Blaming `--dist loadfile` for the
  tail -- a scheduling simulation over measured durations put it at 10-15 %, not worth a change.

## 2026-10-12 PR landing pass (owner direction: resolve conflicts, merge the open PRs that pass every gate)

PR #126 merge preparation: `origin/main` `de36168e` merged into `feat/big-rocks-authority-escrow-battery` as `2cd4e04b`
(docs-only conflicts: PROGRESS, PERFORMANCE row 47, ACTIVE_PLAN; resolution in the merge commit message).
Commands (this session, Linux container, 4 cores, CPython 3.12.13 `.venv`, shallow clone):
- `python -m pytest -m "not expensive" -q -n 4 --dist loadfile -p no:cacheprovider` on `2cd4e04b` -> 15 failed,
  9738 passed, 135 skipped (330 s). 14 of the 15 also fail on unmodified `main` `de36168e` in the same environment
  (`tests/test_mutation_workspace.py` x2, `test_core_certificate::test_the_certificate_describes_this_tree`,
  `test_core_freeze_manifest` x5, `test_core_scientific_audit_batch56::test_r65_...`, `test_core_freeze_v3_manifest` x2,
  `test_core_freeze_v4_manifest` x3: same files on `de36168e` -> 14 failed, 200 passed). The 15th,
  `test_formal_xdist::test_real_xdist_infrastructure_failure_never_earns_credit[worker_lost_before_target-reasons1]`,
  passes alone (`python -m pytest -q tests/test_formal_xdist.py` -> 67 passed): the known load-sensitive case.
  The shallow clone may contribute to the freeze-verifier failures; UNCLASSIFIED here, unchanged from `main`.
- `python tools/forge_check.py --changed` -> 225 passed; `python tools/forge_check.py --regression` -> 225 passed.
- `python -m pytest -q -n 4 --dist loadfile tests/foundations tests/claims flagships/tests` -> 964 passed, 50 skipped.
- forge-scientific-review (read-only) of the combined `main` + #126 + #123 tree: PASS; three LOW findings.
- Hardened recertification: NOT RUN (owner-run, OD-3). SCIENTIFIC / FULL / campaign tiers: NOT RUN.


## Trust Repair Pass 1: R3-01 + R3-02 (2026-10-08, branch fix/trust-repair-pass1 from main 16c87f40)

R3-02. MCP `assess_claim` ran its own SRIA decision (report-wide levels, no comparison, no
uncertainty, discrepancy or policy). It now delegates to canonical `engcore.claims.assess_claim`
(`mcp/claim_assessment.py` rewritten).
- Case-shaped requests are translated through `inputs_from_case`, and they require an explicit
  `comparison` and `uncertainty` demand.
- `report_index`, free-text-only requests, and routing to another capability are refused.
- `assess_scientific_claim` shares the same helper.

R3-01. `verify_assessment` / `verify_bundle` accepted consistently rewritten forgeries.
New `claims/revalidation.py`:
- stored oracle checks are re-run against pinned evidence reached via the plan's routes;
- refuted checks raise `AssessmentForgeryError` (TAMPERED);
- every other level and every demanded run-quantified channel is REPLAY_REQUIRED;
- the verdict must be admissible and the comparison invariant over the pinned band.

`verify_bundle` NEVER returns VERIFIED any more. It returns at most SCIENTIFICALLY_REVALIDATED
(not publishable). VERIFIED comes only from `replay_bundle`, after re-execution.

Review history:
1. forge-scientific-review returned BLOCKER (F1): offline VERIFIED re-earned the level but not the
   verdict. A runtime adversary independently forged "T > 309.795 K" at 309.7999 K → VERIFIED supported.
   Fixed with band invariance.
   Also fixed: F2 (binding and authority lines), F4 (unroutable oracle refuted), F3 (diagnose carries
   the standing), F5/F6 (MCP uncertainty demand, routing guard), and the AttributeError crash.
2. Adversary round 2: the invariance rule held over 588 values x 3,380 claims (units, ulps,
   endpoints). New attack: a genuine 160-cell report carried under a 40-cell claim (real run
   INSUFFICIENT) verified offline. No offline rule can tell runs apart, so offline VERIFIED was
   removed.

Failed approaches:
- Treating offline revalidation as publishable. It verified the level and not the verdict, then
  not the run identity.
- Writing the F4 attack through a rerouted capability registry. CapabilityDeclaration already
  refuses untrusted or foreign route evidence.

Commands (WSL, `.forge/venvs/3.12`, TMPDIR outside repo, `-p no:cacheprovider`):
- `pytest tests/claims/test_offline_revalidation.py tests/mcp/test_claim_assessment.py
  tests/test_forge_diagnose.py`: 59 passed.
- `pytest tests/claims tests/mcp tests/test_forge_diagnose.py tests/credibility -n 4 -m "not campaign"`:
  1110 passed.
- `tools/forge_check.py --changed`: 225 passed.
- Formal TARGETS (48) + test_repository_architecture + test_core_api_layering + tests/mcp/test_bundle
  + tests/mcp/test_server, `-n 4`: 1224 passed.
- Adversary scripts attack1-7 on the final code: 0 offline VERIFIED.

Remaining Review 3 findings, untouched: R3-03, R3-04, R3-05, R3-06, R3-07, R3-08, R3-09, R3-10,
R3-11, R3-12, R3-13, R3-14, R3-15, R3-16.
New notes from this pass:
- a caller's free-text CONSTRAINED_PRIOR reference satisfies require_supported_discrepancy
  (canonical behaviour, = R3 A2-F10);
- replay tolerance is caller-chosen and unbounded (= R3-16);
- a bundle with capability=None skips the carried-capability check;
- a genuine record whose oracle check predates a change to compare() semantics would read TAMPERED
  (no compare-algorithm version is recorded).
Full suite and Local Assurance: NOT RUN (not required for this pass). Not pushed.

Pre-commit smoke (2026-10-09, same venv; `forge_check --changed` log 17:10 is after the last source edit 17:09):
- `pytest tests/claims/test_offline_revalidation.py tests/mcp/test_claim_assessment.py
  tests/test_forge_diagnose.py`: 59 passed.
- `pytest tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared
  tests/test_repository_architecture.py tests/mcp/test_bundle.py`: 32 passed.
- attack1-7 re-run: 0 offline VERIFIED; verify_bundle gave only replay_required,
  scientifically_revalidated or tampered. attack4 predates the F5 uncertainty requirement, so its
  case-shaped requests are now refused; attack5 covers case-shape parity with MCP.

## 2026-10-09 Trust Repair Pass 1 landing prep: main sync, focused regression, scope (branch `fix/trust-repair-pass1`)

The original Trust Repair Pass 1 commit `803946af` (tree `d93e84cd`, parent `16c87f40`) is kept unchanged. Main
`44637065` (after PR #121) was merged into the branch as `24373be4`, a normal merge with no rebase or cherry-pick.
- The only conflict was in this file. Both appended histories were kept: main's entries first, then the Trust Pass 1
  entry verbatim. Main's archival removals of 782 lines carried over exactly.
- Against `44637065`, the effective diff is the 12 Trust Pass 1 files. Eleven are blob-identical to `803946af`, and
  PROGRESS.md gains 67 lines. `certification/current_core_v2.json` is unchanged from main (`7756e5a6`).
- PR #120 commits (`2c0e024b`, `3e396bc4`, `d383eed0`) and PR #121 commits (`44637065`, `3f5096bb`) are ancestors.
- Prereg blob `0668576d` is unchanged, and the Kirkaldy NOT MET record is present.

Commands (WSL, the shared clone's `.forge/venvs/3.12`, `PYTHONPATH=<worktree>/src:<worktree>`, TMPDIR outside the
repo, `-p no:cacheprovider`), all on `24373be4`:
- `pytest tests/claims/test_offline_revalidation.py tests/mcp/test_claim_assessment.py tests/test_forge_diagnose.py`:
  59 passed.
- Adversary attack1-7 (`~/forge-pass1-adversary`, cwd = worktree): output is identical to the 2026-10-08 final logs
  (attack4 has no stored log; its MCP/canonical parity reads `identical_records=True`). Offline VERIFIED outcomes: 0.
  verify_bundle gave 14 replay_required, 14 scientifically_revalidated and 4 tampered.
  - The 305 K oracle forgery is refused at construction.
  - Numerics substitution (attack7) is at most scientifically_revalidated offline, and replay_bundle reports
    not_reproducible.
  - Run with the adversary directory as cwd, replay_bundle refuses earlier with "source-control commit identity is
    unavailable", because `_git_identity` reads the cwd. This is not a regression.
- `pytest tests/claims tests/mcp tests/test_forge_diagnose.py tests/credibility -n 4 -m "not campaign"`: 1110 passed.
- `tools/forge_check.py --changed --base gh/main` (gh/main = `44637065`): 225 passed.
- Formal TARGETS (48) + `tests/test_repository_architecture.py tests/test_core_api_layering.py tests/mcp/test_bundle.py
  tests/mcp/test_server.py`, `-n 4`: 1224 passed.
- `recertification_scope classify --event pull_request --base 44637065 --head 24373be4`: `recertify_source`.
  - RECERTIFY: `src/engcore/mcp/server.py` (mutation_targets), and four certified-harness/assurance-suite test files.
  - Observation: `recertification_scope explain` classifies the trust implementation paths themselves as ordinary:
    `claims/assessment.py`, `claims/replay/bundle.py`, `claims/revalidation.py` and `mcp/claim_assessment.py`.
    Recertification is triggered here only through `mcp/server.py` and the tests. This is a possible follow-up for
    scope policy and is not changed in this pass.

Full Local Assurance runs on the commit that adds this entry, in a dedicated clone, because the shared assurance clone
carries worktrees, which the mutation workspace refuses as external Git storage. Its result is recorded by the certificate-only child and the PR
body, not here, because any later edit would move the certification subject.

## 2026-10-12 PR #123 landing gates (owner direction; merge commits only, no rebase)

`origin/main` `17444e14` (with #126) merged into `fix/trust-repair-pass1`; conflicts were PROGRESS / ACTIVE_PLAN only.
The diff against `main` is exactly #123's 13 files plus docs. The owner-produced certificate (binds `39d43456`) is
carried unedited. One review LOW was fixed (`tools/forge_diagnose.py` comment: offline verification never yields VERIFIED).
Commands (this session, Linux container, 4 cores, CPython 3.12.13 `.venv`, shallow clone), on `fbb52f5e`:
- `python -m pytest -m "not expensive" -q -n 4 --dist loadfile -p no:cacheprovider` -> 14 failed, 9789 passed,
  135 skipped (287 s). The failure set is identical to unmodified `main` in the same environment (mutation_workspace x2,
  certificate x1, freeze v1 x5, batch56 r65, freeze v3 x2, freeze v4 x3).
- `python -m pytest -q -n 4 --dist loadfile -m "not campaign" tests/claims tests/mcp tests/test_forge_diagnose.py
  tests/credibility tests/foundations` -> 1380 passed.
- `python tools/forge_check.py --changed` -> 225 passed; `--regression` -> 225 passed.
- forge-scientific-review (read-only), combined `main` + #126 + #123: PASS. All #123 hardening intact after the
  `mcp/server.py` auto-merge; no #126 or `main` caller consumes offline VERIFIED; attestation / `verify_evidence` and
  offline revalidation never judge the same record. LOWs left open: (2) a REGISTRY_CHANGED bundle result carries the
  stored verdict without re-deriving it (`claims/replay/bundle.py`, pre-existing); (3) `mcp/foundations.py` catches
  bare `Exception` (from `main`, verdict pinned to insufficient_evidence).
- Hardened recertification of the merged tree: NOT RUN (owner-run, OD-3). SCIENTIFIC / FULL tiers: NOT RUN.



## NASA battery ingestion hostile review — 2026-10-06

Requested branch was absent from shared checkout (on main with pre-existing
work-document edits). Fetched origin/scientific/battery-1rc-production-closure
and created isolated ../forge-battery-review at d66c4756; shared edits preserved.

Confirmed/fixed: separate hash/parse reads could bind receipt A to content B;
arbitrary matrices and complex operational values were accepted; strings and
logical Python inputs were coerced into measurements; squeezed singleton MAT
samples crashed; empty impedance records were accepted. Hash/parse now share
one byte snapshot; finite real numeric operational vectors normalize to lists;
empty impedance is refused. Complex impedance remains explicit. Dataset URLs
are format metadata, not origin authentication; parsed helper receipts are
caller assertions. No SOC, segmentation, uncertainty or parameters inferred.

Read-only forge-scientific-review initially returned CHANGES REQUIRED with four
findings, then PASS after fixes. This is review, not executed tests or validation.
No implemented calibration/validation leakage path exists; cell-level split
controls remain deferred. real_data remains MISSING; capability matrix unchanged.

Executed commands (Python 3.14.2 / Windows, not CI acceptance environment):
- `py -3.14 -m pytest -q tests/domains/test_nasa_battery_aging_ingestion.py --basetemp=.pytest-review-temp/nasa-baseline`
  ERROR: 6 passed, 2 setup errors; missing basetemp parent. Relevant names:
  test_source_receipt_binds_exact_raw_bytes;
  test_real_matlab_file_round_trip_uses_the_documented_cycle_shape.
  Failed approach: create the basetemp parent before test execution.
- `py -3.14 -m pytest -q tests/domains/test_nasa_battery_aging_ingestion.py --basetemp=.pytest-review-temp/nasa-baseline-retry`
  PASS: 8 passed in 0.38s.
- `py -3.14 tools/forge_check.py --changed`
  ERROR: 224 passed, 1 setup error:
  test_untracked_manifest_digest_changes_with_file_content (default Windows tmp
  root permission). Retried using explicit workspace basetemp.
- `py -3.14 -m pytest -q tests/domains/test_nasa_battery_aging_ingestion.py --basetemp=.pytest-review-temp/nasa-fixed`
  PASS: 33 passed in 0.50s.
- `$env:PYTEST_ADDOPTS='--basetemp=.pytest-review-temp/nasa-changed'; py -3.14 tools/forge_check.py --changed *> .pytest-review-temp/nasa-changed.log`
  PASS: 225 passed in 10.80s.
- `py -3.14 -m pytest -q tests/domains/test_nasa_battery_aging_ingestion.py --basetemp=.pytest-review-temp/nasa-final`
  PASS: 63 passed in 0.51s. Synthetic fixtures, including genuine multi-cycle
  MATLAB struct arrays; not pinned NASA data or scientific validation.
- `git diff --check`
  PASS: exit 0.

Remaining scientific blockers: pinned original NASA bytes and frozen ingestion
receipt; source/license review; cell-independent calibration/holdout split;
parameter identifiability; measured uncertainty; parameter UQ; discrepancy;
independent held-out metrics; claims/DomainPack integration. No production
capability promotion authorized or performed.

- `py -3.14 -m pytest -q tests/domains/test_nasa_battery_aging_ingestion.py tests/test_capability_completion.py --basetemp=.pytest-review-temp/nasa-final-with-capability`
  PASS: 68 passed in 0.53s after final source/documentation edits.
Final independent read-only review: PASS; no remaining defect identified in
bounded ingestion scope. Reviewer executed no tests.

- `py -3.14 -m pytest -m "not expensive" -q -n 4 --tb=short --basetemp=.pytest-review-temp/nasa-fast *> .pytest-review-temp/nasa-fast.log`
  FAIL: 20 failed, 8948 passed, 170 skipped, 67 warnings, 5 collection errors in 319.24s; exit 1.
  Failures include core freeze/certificate and dirty-tree checks, MCP import
  failures, battery march imports and Cantera provider outputs. No clean-tree
  baseline run here, so pre-existing versus environmental status is not proven.
  These gates are not bypassed or fixed outside this bounded task.

Relevant FAST failure/error names:
```text
FAILED tests/domains/test_audit_domains_unscreened_claims.py::test_the_held_resistance_limitation_is_stated_where_a_caller_reads
FAILED tests/test_core_api_contracts.py::test_the_frozen_digest_is_identical_in_fresh_processes
FAILED tests/test_core_api_snapshot.py::test_the_snapshot_is_byte_identical_across_fresh_processes
FAILED tests/test_core_certificate.py::test_the_certificate_describes_this_tree
FAILED tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully
FAILED tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1 - ...
FAILED tests/test_core_freeze_manifest.py::test_the_command_line_verifier_agrees_with_the_function
FAILED tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies
FAILED tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks
FAILED tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree
FAILED tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract
FAILED tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds
FAILED tests/test_core_freeze_v4_manifest.py::test_the_deep_surface_carries_methods_and_member_positions
FAILED tests/test_core_guards.py::test_the_battery_march_runs_the_solver_it_names
FAILED tests/test_core_guards.py::test_every_marched_step_carries_its_own_cell_report
FAILED providers/cantera/tests/test_cantera_provider.py::test_proof_b_adiabatic_equilibrium_with_mechanism_bytes_bound
FAILED providers/cantera/tests/test_cantera_provider.py::test_proof_b_transient_constant_pressure_reactor_on_a_big2_window
FAILED tests/claims/test_claims_assessment.py::test_the_mcp_tool_returns_the_same_record
FAILED tests/test_core_scientific_audit_batch24.py::test_r39_the_word_says_that_agreement_between_solvers_is_one_of_the_things_it_covers
FAILED tests/test_core_scientific_audit_batch56.py::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see
ERROR tests/domains/battery/test_audit_domains_battery_pulse.py - ImportError...
ERROR tests/mcp/test_answer.py - ImportError while importing test module 'C:\...
ERROR tests/mcp/test_audit_domains_electrothermal_transient.py - ImportError ...
ERROR tests/mcp/test_audit_domains_refused_coupling.py - ImportError while im...
ERROR tests/mcp/test_core_scientific_audit_batch8.py - ImportError while impo...
```

- `py -3.14 -m pytest -m "not campaign" -q -n 4 --tb=short --basetemp=.pytest-review-temp/nasa-scientific *> .pytest-review-temp/nasa-scientific.log`
  FAIL: 22 failed, 9502 passed, 170 skipped, 67 warnings, 5 collection errors in 420.13s; exit 1.

Relevant SCIENTIFIC failure/error names:
```text
FAILED tests/domains/test_audit_domains_unscreened_claims.py::test_the_held_resistance_limitation_is_stated_where_a_caller_reads
FAILED tests/test_core_api_contracts.py::test_the_frozen_digest_is_identical_in_fresh_processes
FAILED tests/test_core_api_snapshot.py::test_the_snapshot_is_byte_identical_across_fresh_processes
FAILED tests/test_core_certificate.py::test_the_certificate_describes_this_tree
FAILED tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully
FAILED tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1 - ...
FAILED tests/test_core_freeze_manifest.py::test_the_command_line_verifier_agrees_with_the_function
FAILED tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies
FAILED tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks
FAILED tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree
FAILED benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates
FAILED benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates
FAILED tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract
FAILED tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds
FAILED tests/test_core_freeze_v4_manifest.py::test_the_deep_surface_carries_methods_and_member_positions
FAILED tests/test_core_guards.py::test_the_battery_march_runs_the_solver_it_names
FAILED tests/test_core_guards.py::test_every_marched_step_carries_its_own_cell_report
FAILED providers/cantera/tests/test_cantera_provider.py::test_proof_b_adiabatic_equilibrium_with_mechanism_bytes_bound
FAILED providers/cantera/tests/test_cantera_provider.py::test_proof_b_transient_constant_pressure_reactor_on_a_big2_window
FAILED tests/test_core_scientific_audit_batch24.py::test_r39_the_word_says_that_agreement_between_solvers_is_one_of_the_things_it_covers
FAILED tests/claims/test_claims_assessment.py::test_the_mcp_tool_returns_the_same_record
FAILED tests/test_core_scientific_audit_batch56.py::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see
ERROR tests/domains/battery/test_audit_domains_battery_pulse.py - ImportError...
ERROR tests/mcp/test_answer.py - ImportError while importing test module 'C:\...
ERROR tests/mcp/test_audit_domains_electrothermal_transient.py - ImportError ...
ERROR tests/mcp/test_audit_domains_refused_coupling.py - ImportError while im...
ERROR tests/mcp/test_core_scientific_audit_batch8.py - ImportError while impo...
```

Recommendation: DO NOT MERGE while integration tiers fail. Bounded ingestion
review PASS does not supersede the repository gates. Pinned NASA ingestion and
physical validation remain NOT RUN; real_data remains MISSING.

Integration runs were sequential. Backed up and restored 5 test-generated
tracked benchmark JSON reports; those paths were clean before execution.
Logs/backups remain under .pytest-review-temp in this isolated worktree.

## 2026-10-12 PR #117 landing gates (owner direction; merge commits only, no rebase)

`origin/main` `21b7d20f` (with #126 and #123) merged into `scientific/battery-1rc-production-closure` as `bfccb351`;
conflicts were PROGRESS / ACTIVE_PLAN only. The branch's ACTIVE_PLAN edit was not carried: it targeted the superseded
queue and had re-encoded UTF-8 characters (mojibake). Diff against `main`: the ingestion tool, its test, README,
prereg and docs. `tools/nasa_battery_aging.py` is standalone (numpy / scipy `loadmat`); it writes only the requested
output file and does not touch the capability ledger: `real_data` stays MISSING and the capability stays FOUNDATION.
Commands (this session, Linux container, 4 cores, CPython 3.12.13 `.venv`, shallow clone), on `bfccb351`:
- `python -m pytest -m "not expensive" -q -n 4 --dist loadfile -p no:cacheprovider` -> 14 failed, 9852 passed,
  135 skipped (286 s). Failure set identical to unmodified `main` in the same environment.
- `python -m pytest -q tests/domains/test_nasa_battery_aging_ingestion.py tests/test_capability_completion.py` -> 68 passed.
- `python tools/forge_check.py --changed` -> 225 passed; `--regression` -> 225 passed.
- Review: the branch's own read-only forge-scientific-review (2026-10-06, above) PASS; no code changed in this landing.
- Hardened recertification: NOT RUN (owner-run, OD-3; `tests/domains/...` is `certified:harness`). SCIENTIFIC / FULL: NOT RUN.

## 2026-10-12 Engineering / performance / scientific-integrity program (owner-requested, local only)

Base `origin/main` `2d0fa6c3`; branch `perf/engineering-program-2026-10-12` in worktree `D:/forge-perf`; commits
`088a8c8c`, `80a3dbe2` (+ this docs commit). Not pushed, not merged, not recertified. Report:
`docs/audits/ENGINEERING_PROGRAM_2026-10-12.md`.

Fixed (each with tests that fail on `2d0fa6c3`):
- `claims/selection.py`: a candidate with no active model is REJECTED (`VALIDITY_UNASSESSABLE`); it was SELECTED as
  sole survivor. No production capability changes selection (all have always-active models).
- `claims/analysis/sensitivity.py::robustness_envelope`: `resolution` validated; non-perturbable `parameters` refused
  (was silently dropped); bisection stops at the input's float resolution (`resolution=500`: 1,003 solves with 102
  distinct inputs -> 102 solves, 8.43 s -> ~1.1 s, identical boundaries; default resolution unchanged); records the
  probe-spacing assumption.
- `claims/analysis/challenge.py::_validity_stress`: NOT_ATTEMPTED instead of a silent skip; range edges compared in
  the stated unit (was raw degC vs K magnitudes); an edge not reached by a holding probe -> INCONCLUSIVE (was a false
  SURVIVED); edge-exact failure counts as inside; negative stated values judged against the right edge.
- `claims/analysis/impact.py`: UQ study trust registries are graph nodes and drift-detected (latent: no production
  capability declares ALEATORIC / MODEL_FORM).
- `providers/process.py`: Windows timeout terminates the process tree (`taskkill /T /F`); a 2 s timeout used to return
  after 60 s when a grandchild held the pipes.
- `tools/forge_check.py --changed`: working tree included (`--committed-only` opts out), renames/deletions reported,
  changed tests run, unclassified `src/engcore/**` and config files select the whole pack. **Certification-pinned
  file: needs the owner-run hardened recertification (OD-3).** `--regression` behaviour unchanged.

Measured and deliberately not built: parallel parameter UQ (93 ET samples: sequential 0.95 s; ThreadPool(4) 0.92-0.97 s,
GIL; one Windows process worker cold start 1.8-2.0 s); parallel refinement (4 solves, ~75 ms).

Commands (Windows 11, CPython 3.14.2 `.venv`, `TMPDIR`/`--basetemp` on D:, `PYTHONPATH='D:\forge-perf\src;D:\forge-perf'`):
- `python -m pytest -m "not expensive" -q -n 4 -p no:cacheprovider` on pristine `2d0fa6c3` (worktree `D:/forge-perf-base`)
  -> 151 failed, 9644 passed, 185 skipped, 21 errors (216 s).
- same on `088a8c8c` -> 151 failed, 9674 passed, 185 skipped, 21 errors (204 s). Sorted FAILED/ERROR node-id sets
  identical (`comm` empty both ways); +30 passes are the new tests. Lists: `D:/forge-perf-logs/fast_{base,branch}.failed`.
  The common set is Windows/3.14 environment (test_mutation_workspace, test_local_assurance source-gate,
  test_mutation_startup, test_formal_xdist, foundations escrow/authority subprocess tests, flagships battery blind
  readiness dry run) plus known drift (test_core_certificate, freeze v1/v3/v4 manifests, batch56 r69).
- on `80a3dbe2` (challenge follow-up): `python -m pytest -q -n 4 tests/claims` -> 694 passed.
- `python -m pytest -q tests/test_forge_check.py` -> 30 passed; `tests/test_provider_boundary.py` -> 29 passed, 1 skipped
  (pre-existing symlink-privilege skip).
- `python tools/forge_check.py --changed --base origin/main --workers 4` on the final tree -> 328 passed, 1 skipped (14.3 s); selected the whole pack (`providers/process.py`, `tools/forge_check.py` unclassified).
- SCIENTIFIC, FULL, hardened recertification, Python 3.11/3.12: NOT RUN.

Reviews (read-only forge-scientific-reviewer): selection audit (D1 fixed; D2 NOT_ASSESSABLE invisible to the
compiler and D3 array-section mismatch recorded, both fail closed); full diff PASS (M1 = certification pin; L1
Windows orphaned-descendant residual recorded; L3 false SURVIVED fixed); challenge-fix review: findings 2-3 fixed,
re-review PASS; finding 1 (`ChallengeReport.status` ignores INCONCLUSIVE, pre-existing) left as an owner decision
because it changes a serialized status vocabulary.

Failed approach: a bash heredoc for the first `forge_check.py` patch broke on quoting and wrote nothing; patch scripts
written with the editor tool worked.

## 2026-10-12 Test execution speed, developer loop and test-infrastructure cleanup (owner-requested, local only)

Base `origin/main` `305928f9`; branch `perf/test-loop-cleanup` (worktree `D:/forge-tl`), not pushed. Machine: Windows 11,
16 physical / 24 logical cores, 31.7 GB RAM (~9 GB free), CPython 3.14.2, pytest 9.1.1, pytest-xdist 3.8.0. Harness:
`-p no:cacheprovider`, bytecode caching on (this agent's shell sets `PYTHONDONTWRITEBYTECODE=1`; that costs ~20 s instead
of ~8 s of collection per process and was unset for every measurement), per-run wall / process-tree CPU / peak RSS by
psutil sampling, per-worker collection and busy time by a `-p` plugin, failure sets from JUnit. Scripts and raw runs:
`D:/forge-tl-bench/`.

Changes (all certified-harness or control-plane files except `tools/test_impact.py`, `docs/`): **RECERTIFICATION_REQUIRED**
(owner-run, once for the batch):
- certification suites build their synthetic certified repository once per module and copy it per test
  (`tests/certification_fixtures.py::clone_tree`); a test pins "private and location-free". Same 178 ids and outcomes;
  serial 172-176 s -> 30-34 s for lineage + skip_admission + hardening_assurance.
- hybrid-UQ classifier grids built in the test, not at import (ids unchanged).
- `forge_check --changed` adds the tests a change can reach (`tools/test_impact.py`: import graph, mentions, conftest,
  source walkers), classifies each changed path by ownership, prints the CI recertification triggers, lists affected
  expensive tests instead of running them (`--with-expensive`). `--regression` unchanged and never imports the module.
- five test modules imported shared helpers by bare name and could not be run alone (collection-order dependent); fixed.

Commands and results (sorted FAILED/ERROR node-id sets compared with `comm`; equal unless stated):
- Collection, whole suite, one process (`--collect-only -p no:xdist`): 10,615 tests; 8.0 s wall warm (pytest-reported
  5.6-6.4 s), 18-20 s with `PYTHONDONTWRITEBYTECODE=1`. Branch: pytest-reported 5.4-5.5 s vs 5.6-6.3 s interleaved -- no
  measurable change claimed. Hotspots: assertion rewriting (no cache when bytecode writing is off), the ngspice WSL probe
  at import (1.6 s), hybrid-UQ grids at import (moved), `production_registry()` at import (memoized; left).
- FAST `python -m pytest -m "not expensive" -q -n 4 --dist loadfile`: base 195.9 / 176.5 / 195.0 s, branch 161.1 / 163.3 s
  (at `4118c626`); 151 failed + 21 errors in every run, identical sets. `-n 8`: 139.9 -> 101.1 s, imbalance 1.19 -> 1.03.
- Worker scaling on base FAST: n1 589.2 s, n2 302.9, n4 176.5-195.9, n6 151.4, n8 139.9, n4 `--dist load` 189.8; same
  failure set; n12 not run (memory). Knee 6-8 on this host; CI stays `-n 4`.
- SCIENTIFIC as CI runs it (six deselects), `-n 4`: base 308.2 / 303.9 s, branch 245.4 / 275.7 s, identical failure sets,
  tree clean. Without the deselects: base 336.3 s, branch 284.0 s with two extra failures in
  `tests/claims/test_offline_revalidation.py` -- the rebuild tests rewrote tracked JSON mid-run and a replay correctly
  reported NOT_REPRODUCIBLE; the module passes alone (31 passed). Both no-deselect runs dirtied 17 committed JSONs.
- Certification suites (lineage + skip_admission + hardening_assurance + hybrid module), serial, twice each: base 176.1 /
  173.3 s, branch 35.9 / 34.5 s; same 178 ids and outcomes.
- Changed-file gate (`--workers 4`, one throwaway edit each, tree restored after every run, nothing else dirtied):
  thevenin.py 165 tests 11.2 s -> 1,858 tests 52.5 s; claims/selection.py 241 / 12.0 s -> 3,839 / 63.7 s; authority/ledger.py
  241 / 10.7 s -> 2,047 / 55.3 s; docs/TESTING.md 56 / 6.1 s -> 184 / 15.3 s. New-gate failures: the known environment set,
  plus batch24/25 (could not run outside the full suite; fixed on the branch).
- Isolation audit: all 579 test modules collected alone (8 parallel processes): 1 failure (test_mutation_harness, fixed);
  static scan for bare imports of test modules not on the pythonpath roots: batch24/25 real (fixed), the rest resolve
  through their own sys.path setup (alone == full-run outcome).
- Final head `e465ec2a`: FAST `-n 4` 157.4 s (10,061 tests: 151 failed + 21 errors, set identical to base, tree clean);
  SCIENTIFIC as CI runs it `-n 4` 269.1 s (identical failure set, tree clean).

Failed approaches:
- Regex over the raw text for dotted module names (to avoid a full AST walk) took a `thevenin.py` edit from 47 affected
  modules to 557 via package docstrings naming submodules, for 0.7 s; reverted to AST string constants < 400 chars.
- The first gate-timing pass ran decorator-marked expensive tests (tier detection read only conftest tables); the two
  benchmark rebuild tests rewrote 17 committed JSONs in the gate worktree and contaminated every later run. Fixed tier
  detection; the timing script now restores the tree after every run.
- Moving the ngspice availability probe out of import (1.6 s per collecting process on Windows+WSL) was not done: the
  skip would move from a `skipif` mark to a fixture, changing the JUnit skip location that certified skip admission
  matches on.

Open: the two `test_rebuilding_everything_reproduces_the_published_gates` tests write committed files in place (CI
deselects them; locally they race with `test_offline_revalidation`); the builders need an output-directory parameter.
SCIENTIFIC without the CI deselects is not equivalent to CI. FULL, Python 3.11/3.12, hardened recertification: NOT RUN.


## 2026-10-13 Scientific-integrity, certification and engineering remediation (owner-requested, local only)

Base `origin/main` `c4e05ee6`; branch `fix/remediation-2026-10-12` in worktree `D:/forge-remed`; pristine comparison
worktree `D:/forge-remed-base`. Uncommitted, not pushed, not recertified. Report:
`docs/audits/REMEDIATION_2026-10-13.md` (findings table, owner decisions OD-R1..OD-R8).

Fixed (tests fail on base unless stated):
- `claims/analysis/challenge.py`: `outcome_counts()` / `unresolved` / `outcome_summary()` (serialized `status`,
  `to_dict` and digest unchanged, digest pinned); `_guard_band` SURVIVED only for a decided, unchanged nominal verdict
  (an `insufficient_evidence` ET claim at 400 K got SURVIVED and the headline `survived_attempted_challenges`).
- `claims/model_form_uq.py`: only a VALIDATED_CANDIDATE discrepancy reaches the model-form study; no unknown-uncertainty
  point is dropped (base: a FAILED_VALIDATION discrepancy came out `ModelFormStatus.VALIDATED`).
- Ported from the reviewed but never-committed 2026-10-09 pass (`D:/forge-review-fixes`, B2 + B4 only):
  `model_discrepancy` `Mapping` import, `verify_study_records` qualification read-back, ngspice probe exit/timeout/
  OSError typing; plus ngspice `run()` OSError -> NgspiceUnavailable. B1 (probabilistic-UQ sampler) and B5 remain
  stranded there (OD-R8).
- `claims/capabilities.py`: selection D3 refused at declaration time.
- `providers/process.py`: output to temp files (same digest bytes), reaper-thread wait, tree kill then bounded reap,
  typed launch failure, `run_bounded`; `discovery_providers.run_provider` uses it; preCICE single deadline, cleanup,
  file capture; code_aster workspace created inside its `try`.
- `execution/sweep.py`: non-exported `run_sweep_within_budget` / `BudgetedSweep` over `ResourceBudget`
  (RECERTIFICATION_REQUIRED: certified `execution_trust`).
- `systems/products/drone_coupled.py`: docstring / note only — the winding residual is zero by construction (0.0 K on
  a real run), the bus residual is the last bus-voltage update times the current (-5.8e-11 W).

Commands (Windows 11, CPython 3.14.2 `.venv`, `TMPDIR`/`--basetemp` on D:, `PYTHONPATH='D:\forge-remed\src;D:\forge-remed'`):
- `python tools/certification/core_certificate.py --verify` on pristine `c4e05ee6`: FAILED, 14 files / 4 areas
  (certified `39d43456`). On the branch (`--allow-dirty`): the same plus `src/engcore/execution/sweep.py`.
- `python tools/forge_check.py --changed --base origin/main --workers 6 --junitxml D:/remed-gate.xml` (before the
  review fixes): exit 1, 156 failures; vs `D:/forge-perf-logs/fast_base.failed` 4 new by name, all explained: 2
  `test_formal_xdist` parametrize-ID escapes (same errors on base), `test_the_tree_is_core_freeze_v1` and
  `test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks` fail only on `tree.clean` (uncommitted
  branch; pass on clean base).
- final tree: `python tools/forge_check.py --changed --base origin/main --workers 6 --junitxml D:/remed-gate-final.xml`
  -> exit 1; 9,529 tests, 136 failed, 21 errors, 181 skipped (118 s). Versus the pristine FAST list the only
  names not in it are the same 4 explained above; `test_v2_blindfold::test_the_subprocess_escrow_keeps_its_secrets_in_the_child`
  (new to this selection) fails 3/3 identically on `D:/forge-remed-base` (Windows escrow handshake, in the baseline list).
- `python -m pytest -q -n 4 tests/claims tests/test_execution_sweep.py tests/test_provider_boundary.py
  tests/foundations/test_v2_discovery_providers.py tests/test_ngspice_version_probe.py tests/uq/model_form` -> 826
  passed, 1 skipped.
- after the last process fixes: `tests/test_provider_boundary.py tests/foundations/test_v2_discovery_providers.py` ->
  42 passed, 1 skipped (Windows); same on WSL CPython 3.11.16 (`sci` env) -> 42 passed, 1 skipped (optional psutil).
- `tests/test_core_scientific_audit_batch55.py tests/test_core_guards.py -k "anchor or exactly_once or mutation or
  guard"` -> 269 passed. `tests/test_execution_sweep.py tests/test_core_freeze_policy.py
  tests/test_core_runtime_api_surface.py tests/test_core_api_layering.py` -> 72 passed.
- Fail-before on `D:/forge-remed-base` (test files copied in temporarily, removed after): 15/20 ported, 20/23 new fail;
  escaped-descendant test 60.1 s for a 2 s timeout.
- Provider benchmark (WSL, provider tests under a metrics plugin, base vs branch): see the report §D.
- after commit `ce96fa06` (clean tree): `python -m pytest -q -n 0 tests/test_core_freeze_manifest.py
  tests/test_core_freeze_v3_manifest.py tests/test_core_freeze_v4_manifest.py` -> 5 failed, 41 passed, 1 skipped;
  pristine `c4e05ee6` -> the same 5 failed, 41 passed, 1 skipped. `test_the_tree_is_core_freeze_v1` and
  `test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks` now pass (they failed only on `tree.clean`).
  The 5 (`test_a_descendant_that_keeps_the_contract_still_verifies`, `test_core_freeze_v4_is_the_contract_that_binds_on_this_tree`,
  `test_the_tree_keeps_the_core_freeze_v4_contract`, `test_once_assured_the_full_verification_holds`,
  `test_the_deep_surface_carries_methods_and_member_positions`) fail on the same verifier checks on both trees:
  `api.deep_surface_is_the_live_one` and `api.manifest_records_this_comparison` (Python 3.14 V4 surface artifact) and
  `certificate.verifies` (certificate drift, OD-3).
- FAST, SCIENTIFIC, FULL, hardened recertification, Local Assurance, CPython 3.11/3.12 on Windows: NOT RUN.

Reviews (read-only forge-scientific-reviewer): round 1 CHANGES REQUIRED (no BLOCKER/HIGH): M1 fixed; M2 -> OD-R1;
M3 -> OD-3/OD-R4; L2-L5, L7 fixed; L1, L6 recorded. Round 2 (narrow) PASS; its residual (`run_bounded` reading with a
moving file position) fixed.

Failed approaches:
- The first process fix replaced `communicate(timeout)` by `Popen.wait(timeout)`; on POSIX that polls with a back-off
  up to 50 ms and regressed short solves (CalculiX 14 -> 21 ms, OpenModelica 365 -> 448 ms). A reaper thread blocking
  in `wait()` plus an event restored them (14.3 / 380 ms).
- `pytest.importorskip("psutil")` inside a test's `finally` turned the Linux escaped-descendant test into SKIPPED and
  would have hidden a failure; cleanup now uses `os.kill`.
- A `forge_check` run from a worktree whose rootdir is the branch imports the branch even with `PYTHONPATH` set to
  another tree (`pyproject` `pythonpath = ["src", ...]`); fail-before checks must run inside the base worktree.
- Long bash heredocs for patches broke on quoting again; patch scripts written with the editor tool worked.


## 2026-10-13 Test loop round 2: isolation, impact cache, worker mode, process hygiene (owner-requested, local only)

Base `origin/main` `ca24b152` (PR #133 merge; the task named `c4e05ee6`, main had moved). Branch `perf/test-loop-round2`,
worktree `D:/forge-tl2`; pristine twin `D:/forge-tl2-base`. Not pushed. Machine: Windows 11, 24 logical / 16 physical
CPUs, 31.7 GB RAM (9.4 GB available at start), CPython 3.14.2, pytest 9.1.1, pytest-xdist 3.8.0. Bytecode caching on for
every timing; `FORGE_IMPACT_CACHE=off` for every test run. Scripts and raw results: `D:/forge-tl2-bench/`.

Changes:
- Task 1 (`8b90e577`): the two benchmark rebuild tests write into a `tmp_path` copy (`ARTIFACT_DIR` in each round's audit
  package) and assert the committed round directory byte-identical. Before: 17 tracked JSONs rewritten (12 CRLF-only, 5
  with content changes). Both tests still fail for their pre-existing reasons (`assert False` / `9 == 10`: pinned
  scientific-core digest drift), identically to base on a clean tree.
- Task 2 (`1d26492a`): content-addressed per-file import-facts cache in `tools/test_impact.py`, used by
  `forge_check --changed`; graph identical to the uncached build (deps, reverse, texts, unparseable, roots).
- Task 3 (`1d26492a`, `148c475b`): `forge_check --workers safe-auto` (`tools/local_workers.py`).
- Task 4: no change needed (see audit below).
- Tasks 5-7 (`a1cc7bf6`): health/catalog probes through `run_bounded`; escrow `stop()` / `close()` kill on a timed-out
  graceful wait; `dakota -version` timeout and typed refusals in `providers/discovery/dakota_runner.py`; preCICE work
  directory removal retried (Windows left an empty directory 1/15 failure-path runs; 0/40 after).
- `20b79847`: the safe-auto test stubs the impact graph (it had taken the regression pack from 9 s to 25 s).

Measurements (same workload before / after):

| ID | Improvement | Before | After | Outcome match |
|---|---|---|---|---|
| T2 | `forge_check --changed --dry-run`, one `selection.py` edit | 5.89-6.38 s (median 6.37, n=5) | warm 1.71-2.19 s (median 1.81, n=5); cold 6.57 s; cache off 6.37-6.97 s | selections identical for 4 probe edits |
| T2 | `build_graph` alone | 4.97-5.04 s | warm 0.79-0.86 s; uncached 5.44-5.50 s | graph identical |
| T1 | tracked files written by the two rebuild tests | 17 | 0 | outcomes identical |
| - | FAST `-m "not expensive" -n 4 --dist loadfile` | 158.5 / 156.2 s | 135.6 / 168.9 s | no material change (noise); failure sets identical |
| - | SCIENTIFIC as CI runs it, `-n 4` | 279.7 s | 258.0 s | no material change claimed; failure sets identical |
| - | `forge_check --regression --workers 4` | 241 passed, 9.0-9.1 s | 251 passed, 9.2-9.5 s | +10 new tests |

Commands and results:
- FAST on base: 10,111 tests, 151 failed, 21 errors (172 ids), twice; `-n 8`: 105.6 s, same ids, peak 4,043 MB (tree) /
  1,207 MB (one process); `-n 4` peak 2,577 / 1,277 MB. On the branch (after `20b79847`): 10,148 tests, the same 172 ids,
  twice; tree clean.
- SCIENTIFIC (`-m "not campaign"`, CI's six deselects, `-n 4 --dist loadfile`): base 10,683 tests, branch 10,720, the same
  172 ids; peak 3,874 MB / 2,690 MB single process. Branch without the two rebuild deselects: + exactly those two
  (pre-existing), `test_offline_revalidation` clean, `assert_clean_tree` byte-identical.
- Concurrent race check (`-n 3 --dist load`, both rebuild tests + `tests/claims/test_offline_revalidation.py`): branch 0
  dirty files, base 17 (restored).
- Standalone audit: all 569 FAST test modules run alone, 8 at a time (218 s); after fixing the driver's own basetemp
  parent (36 spurious tmp_path errors), no module has a failure outside the full-run failure set: 0 order-dependent.
- `tests/test_change_impact.py tests/test_forge_check.py tests/test_forge_impact.py`: 88 passed (before the last two
  forge_check tests); `tests/test_forge_check.py`: 41 passed.
- Process tests on Windows and on WSL CPython 3.11.16: probes, run_bounded, escrow kill, Dakota (fake `dakota` on
  POSIX), preCICE cleanup; fail-before on base: the pipe-holding probe (60 s), both escrow kills, missing Dakota.
- `python tools/forge_check.py --regression --workers 4`: 251 passed (base 241).
- FULL, hardened recertification, Python 3.11/3.12 on Windows: NOT RUN.

Failed approaches / traps:
- The standalone driver deleted `D:/fbt-sa` and passed `--basetemp=D:/fbt-sa/NNNN`; pytest does not create basetemp
  parents, so every tmp_path test in 36 modules errored with FileNotFoundError. Not an order dependence.
- `pytest.importorskip` inside a cleanup helper again turned asserting tests into SKIPPED (preCICE, on WSL without psutil);
  the helper now returns None instead.
- The blindfold `run_discovery` timeout path was not changed: Linux-root only, and its tests need `cryptography`,
  absent in the WSL env; an untested edit to an isolation boundary was not made.


## 2026-10-13 Test loop round 3: one-command dev check, selective SCIENTIFIC, slowdown guard (owner-requested, local only)

Base `origin/main` `9ca337f9` (as expected). Branch `perf/test-loop-round3`, worktree `D:/forge-tl3`; pristine twin
`D:/forge-tl3-base`. Not pushed. Machine: Windows 11, 24 logical / 16 physical CPUs, 31.7 GB (14.5 GB free), CPython
3.14.2, pytest 9.1.1, xdist 3.8.0. Measurement instrument (outside the repo, same for base and branch):
`D:/forge-tl3-bench/tl3_metrics.py` (per-test start/stop per worker, Popen and probe counts). Bytecode caching on.

Implemented (`cd6fdc03`, `c2c79b02`):
- `forge_check --dev`: changed gate + safe-auto workers + timing report (`~/.cache/forge/timing/`) + warning-only
  comparison + summary (CHANGE CLASS / AFFECTED / RUN / EXPENSIVE AFFECTED / NEXT REQUIRED from
  `test_impact.next_required`).
- `forge_check --scientific`: affected tests incl. expensive (`-m "not campaign"`) when `test_impact.scientific_narrowing`
  allows; refuses (exit 2) for trust/authority, shared scientific, test infrastructure (conftest, pyproject, selector),
  unclassified and unresolved changes. `test_impact.scope_class` separates what a path is from its certification pin.
- `tools/test_timing.py`: developer telemetry plugin + `compare` / `history`; thresholds module x2 & +5 s, test x2 & +3 s,
  wall x1.4.

Measured (same workloads, base / branch):

| Measurement | Base | Branch | Outcome |
|---|---|---|---|
| Dev loop, one `thevenin.py` edit (`--changed -n 4` / `--dev`) | 50.9 s | 53.6 s (`-n 4`), 47.4 s (`--dev`, safe-auto 8) | same 9 known failures; no speedup claimed |
| Selective SCIENTIFIC (`--scientific`, -n 8) | full tier 267.0 s | docs 13.5 s, domain 63.7 s, provider 69.9 s; units / authority / conftest refused | failures all in the known set |
| FAST -n 4 (warm) | 147.6 / 148.9 s | 139.8 s | 172 ids identical |
| FAST -n 8 (safe-auto) | 101.5 s | 93.0 s | 172 ids identical |
| SCIENTIFIC as CI, -n 4 | 267.0 s | 240.9 s | 172 ids identical; within noise, not claimed |
| xdist imbalance (last worker after first) | FAST 4.5 s, SCI 9.5 s | FAST 4.7 s, SCI 8.2 s | unchanged |
| Regression pack | 252 passed | 256 passed | +4 new tests |
| Slowest module | `test_core_guards.py` 41-48 s (FAST); `scientific_truth` 120 s (SCI) | unchanged | - |

Measured and rejected:
- Provider-probe memoization (Task 5): one FAST run makes 44 `ProviderRegistry.discover()` calls (0.033 s each) and 21
  ngspice `probe_version` calls (1.85 s first per process through WSL, 0.08 s after). An in-process memo saves < 3 s of
  worker time (< 1 s wall), and a stale provider identity is the risk; a cross-run cache is not safe for a binary behind
  WSL. Not built.
- Giant-module splits (Task 4): imbalance is 4.5 s (FAST) / 9.5 s (SCIENTIFIC) at -n 4. `scientific_truth` (120 s, four
  independent diffusion tests) is not on the critical path at -n 4 and its node ids are pinned in `tests/conftest.py`
  tier tables and `tests/test_tier_classification.py`. Not split.

Selective SCIENTIFIC safety evidence:
- `tests/test_change_impact.py::test_every_expensive_test_reached_by_an_import_is_selected_with_expensive_included`:
  on the real tree every expensive module is reached by a change to any `src/engcore` module it imports.
- Mutation G9c (CSTR solver discards its validity assessment) applied temporarily: `--scientific` selected 554 modules
  and ran `tests/domains/kinetics/test_cstr_domain.py` (expensive), which failed; tree restored.

Flaky / isolation audit (repeated, failure sets compared run by run): preCICE x20, process-boundary timeouts x10,
timing plugin x10, rebuild tests + offline revalidation at -n 3 x3 (only the two pre-existing rebuild failures, tree
clean), certification suites at -n 4 x3, `test_benchmark_records` x3, impact / forge_check / timing at -n 4 x3: no run
differed. No edit made.

Commands: `python tools/forge_check.py --regression --workers 4` (base 252 passed, branch 256 passed, twice each);
FAST `-m "not expensive" -n 4|8 --dist loadfile`; SCIENTIFIC `-m "not campaign" -n 4 --dist loadfile` + CI's six
deselects; `python -m tools.certification.assert_clean_tree` clean. FULL, hardened recertification, Python 3.11/3.12:
NOT RUN.

Trap: a real-tree soundness test that called `impact_of` per dependency took 137 s; computing `importers` once per
dependency (what `impact_of` uses for import reach) takes 2.8 s.

## Hostile remediation round 1 — 2026-10-13, BLOCKED_WITH_EVIDENCE

Verified origin/main after fetch: 5d73e8f5118aa845f1957decc5aae986e72476a9.
Created clean D:/forge-hostile-remediation, branch fix/hostile-review-p0-p1.
Original dirty checkout preserved. No production edits, push, PR or merge.
Current bounded queue and evidence: HOSTILE_REMEDIATION_ROUND1.md and
hostile-round1-evidence/. No listed finding closed; phase 0 remains incomplete.

Commands executed in this session (working directory D:/forge-hostile-remediation):
- `git fetch origin`; `git rev-parse origin/main`: expected SHA above.
- `git worktree add -b fix/hostile-review-p0-p1 D:/forge-hostile-remediation origin/main`: exit 0.
- `py -0p`: Windows Python 3.10/3.14 only.
- `wsl --list --quiet`; `wsl -d Ubuntu -- bash -lc 'command -v python3.11; command -v python3.12; ls -d /opt/forge* /mnt/c/Users/dev_kaeem/Downloads/Compressed/phyx/.forge/venvs/* 2>/dev/null'`: BLOCKED, unresponsive, interrupted.
- `py -3.14 tools/forge_check.py --regression *> D:/forge-hostile-regression-baseline.log`: BLOCKED, interrupted. Direct executable retry also blocked.
- `& 'C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe' -c 'import faulthandler; faulthandler.dump_traceback_later(10); import engcore.claims; print("imported")'`, PYTHONPATH=src: BLOCKED; traceback shows platform._wmi_query while importing Pint/flexcache; interrupted.
- Diagnostic here-string piped to `& 'C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe' -`, PYTHONPATH=src;tests/claims, source: `import platform; platform._wmi=None; import pytest; from tools.forge_check import build_targets; raise SystemExit(pytest.main(build_targets([],regression=True)+['-q','--basetemp=D:/forge-hostile-diagnostic-pytest','-p','no:cacheprovider']))`: 256 passed in 11.85s, exit 0. Output regression-diagnostic.log. DIAGNOSTIC ONLY, unsupported Python and WMI fallback; not supported acceptance.
- `$env:PYTHONPATH='.;src;tests;tests/claims;tests/foundations'; & 'C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe' D:/forge-hostile-phase0-probes.py *> D:/forge-hostile-phase0-probes.log`: exit 0; exact script/output retained. 305K request ->309.75K proposal ->ready ->supported; FM14.55456 accepted; synthetic scanner reads environment; injected two-window conservation FAIL/PASS loses FAIL.
- In-memory certificate scope and verifier probe with WMI fallback: verdict/authority/blindfold files absent from scope; certificate verification FAILS on clean starting main. Certificate target 39d43456cab918ed0748efe7f5b0ff5781474ffa; source drift in certification_control, execution_trust, harness, inference_admission, runtime_dependencies. No certificate changed.
- `& 'C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe' -c 'from tools.certification.local_assurance import _require_linux; _require_linux()'`, PYTHONPATH=.;src: exit 1, native Windows refused. Authoritative recertification cannot prove this tree in available environment; user stop condition honored.
- `& 'C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe' -c 'import platform,runpy,sys; platform._wmi=None; sys.argv=["pip","install","--target","D:/forge-hostile-diagnostic-deps","cryptography"]; runpy.run_module("pip",run_name="__main__")'`: exit 0, external diagnostic-only cryptography50.0.2/cffi2.1.1/pycparser3.11 installation.
- `$env:PYTHONPATH='D:/forge-hostile-diagnostic-deps;.;src;tests;tests/foundations'; & 'C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe' D:/forge-hostile-phase0-mutations.py *> D:/forge-hostile-phase0-mutations-with-crypto.log`: harness exit0, pytest exit1, 15 failed/21 passed in2.11s. Exact script/output retained. HVAC module temporarily deleted/restored byte-for-byte; 47 selected modules, no HVAC-specific module, unresolved/refusal empty. In-memory genesis-signature guard mutation restored after tests.
- Genesis BASELINE, same diagnostic Python/PYTHONPATH, here-string `import platform; platform._wmi=None; import pytest; raise SystemExit(pytest.main(['tests/foundations/test_authority_integrity.py','tests/foundations/test_authority_durable_campaign.py','-q','-p','no:cacheprovider','--basetemp=D:/forge-hostile-genesis-baseline-temp']))`: exit1, 15 failed/21 passed in2.02s. Failures: os.geteuid/fcntl unavailable and default cp1252 decoding; full exact FAILED IDs in genesis-baseline.log.
- `Compare-Object $taskBaseline $taskMutant`, arrays populated from all exact `^FAILED ` lines in genesis-baseline.log and phase0-mutations-with-crypto.log: no differences. This compares IDs, not counts. Linux mutation population NOT RUN; no claim of completed mutation gate.
- `git diff --check`: PASS, exit0 before documentation commit.

Failed approaches: adapter function is not exported at top-level claims; external
script requires repository root explicitly on PYTHONPATH; initial authority pack
had35 failures/1pass from missing cryptography, corrected with isolated dependency
installation. No global environment changes and no remaining temporary source edits.

Supported Python3.11/3.12 FAST, SCIENTIFIC, FULL, complete selective mutation red
team, benchmark digest attribution, hardened recertification: NOT RUN. Original
critical false support remains OPEN. Remaining listed critical/high counts:1/7.
Scientific numerical/frozen experiment outputs changed:NO. No Mind work.

Checkpoint correction: `git diff --cached --check` initially FAILED on trailing
spaces emitted by pytest traceback transcripts. Normalized transcript trailing
whitespace only; raw originals retained outside the worktree. No evidence values,
failure IDs or source bytes changed. Rerun required below before final checkpoint.
`git diff --cached --check`: PASS after transcript whitespace normalization, exit 0.

## Hostile remediation round 1 — implementation, 2026-10-13/14 (Linux/WSL Ubuntu 24.04)

Branch `fix/hostile-review-p0-p1`, base `5d73e8f5`. Work clone `~/forge-hostile-dev`; integration
clone `~/forge-hostile-remediation` fast-forwarded from it; Python `.forge/venvs/3.11` and `3.12`
(pytest 9.1.1, xdist 3.8.0). No push, PR or merge. Evidence: `~/forge-hostile-evidence/` (WSL).

Fixes (each its own commit, each with adversarial tests and a targeted apply/revert mutation proof,
`mutate.py`: a mutant is KILLED only when pytest exits 1 with failures; bytes restored by SHA-256):

| Finding | Commits | Mutation proof |
|---|---|---|
| F1 LLM-authored criteria | dcfe4ca8, f54b2986, bc45e9c1, e5d862a1, c2d592a4, 86b6e51e, d150f975, aafd6a40 | 16 + 16 + 3 + 2 + 2 killed |
| F4 benchmark is verification | 81b2cf6a, 7970052d, d014e7da | 5 + 2 killed |
| F2 certificate covers verdict semantics | 8d81cb70, 50921eff, e00a9fce, 11f1514f, a40318dc, 57dd68ce, 659da048 | 6 + 8 + 10 + 4 + 4 + 1 + 1 killed |
| scanner ownership | ee2029f8, d9ad7bdd | 5 + 5 killed |
| F5 conservation per window | d63de65b, 1bccb1b4, f1f6dea5, 154706ec, 57dd68ce | 12 + 9 + 1 + 1 + 1 killed |
| F6 physical admissibility | 26240134 | 7 killed (1 equivalent pre-check removed) |
| F7 selective gate | 91cb9790, 11f1514f | 7 + 1 killed (1 equivalent branch removed) |
| FIX 8 empty UQ / undeclared correlation | 954213ac | 3 killed |
| FIX 9 (F8) CI triggers | 324d1a7e | 5 killed |

Independent reviews (forge-scientific-reviewer, read-only, static): eight passes. Every BLOCKER and
HIGH was fixed in the commits above; the eighth pass found the commit it reviewed correct and one
pre-existing scope leak (system_runtime), fixed in 659da048. Accepted residuals
(not fixed, reason stated in the commit messages): F1-I one-way input grounding and decision_id as a
label; decision/assumption statements recorded verbatim, not interpreted; F5 run records are unkeyed,
so an internally consistent forged history is not detected (enforcement re-derives verdicts from the
record, not from transfer receipts); no separate CONSERVATION gate in the trust assessment (an
authorized run whose required conservation failed cannot be constructed); executor callees inside
exempt answer packages are pinned only when they build evidence; SRIA budget independence is a stated
free-text assumption; guard_band takes a bare float; test_impact basename mentions; `-s` without `-S`
in the registry probe; planning/nl.py any-span weakness (no production caller); the registry probe
does not unwrap a decorated executor (none is decorated today); a fixed runtime returning a non-record
on a graph without balances skips the graph/plan check (test stubs only).

OPEN SCOPE FINDING (owner decision, not fixed): certified files import uncertified modules --
claims/design_memory.py (design/, sria/campaign/), claims/discovery_providers.py (providers/,
sria/decision/), claims/discovery_passport.py, durable_campaign.py, falsification.py (sria/decision/),
claims/twin_evidence.py (systems/), sria/campaign/runner.py (sria/campaign/*, sria/decision/*),
execution/multiphysics/runtime.py (scenarios/). None is on the assess_claim verdict path found by the
reviewers; seeding the authority closure with all of claims/** would bring 95 modules into scope.

Selective-gate hostile campaign (F7), separate clone at 91cb9790 then H10 re-run with a valid mutant:
`python selective_campaign.py ~/forge-hostile-sel` -> 10 hostile changes, 8 CAUGHT by the selection,
2 REFUSED_NARROWING (whole tier), FALSE_NEGATIVES 0, tree clean after. Logs:
`dev/selective_campaign.log`, `dev/selective_campaign_h10.log`.

Impact-selected gates during development (`tools/forge_check.py --changed --base HEAD --workers 6`,
dev clone): every run's only failures were the certificate-drift tests and, on a dirty tree, the
Core-freeze manifest tests (which pass once committed: `tests/test_core_freeze_*` 73 passed, 2
certificate-drift failed after commit).

Acceptance matrix (`gates.sh`, integration clone; FULL and SCIENTIFIC deselect the two JSON-rewriting
rebuild tests, three ngspice-process tests and the dependency guard, which runs separately):

| Gate | HEAD | Result |
|---|---|---|
| regression (`tools/forge_check.py --regression`) | 324d1a7e, 11f1514f | exit 0 |
| FAST 3.11 | 11f1514f | 10351 passed, 2 failed, 158 skipped |
| FAST 3.12 | 11f1514f | 10350 passed, 3 failed, 158 skipped |
| SCIENTIFIC 3.12 | 11f1514f | 10923 passed, 3 failed, 158 skipped |
| FULL 3.12 | 11f1514f | 10927 passed, 3 failed, 158 skipped |
| FAST 3.11 | a40318dc | 10358 passed, 2 failed, 158 skipped |
| FAST 3.12 | a40318dc | 10357 passed, 3 failed, 158 skipped |
| SCIENTIFIC 3.12 | a40318dc | 10930 passed, 3 failed, 158 skipped |
| FULL 3.12 | a40318dc | 10934 passed, 3 failed, 158 skipped |
| regression | a40318dc | 256 passed |

The final-HEAD matrix and hardened recertification are recorded in the next entry.

Failure identities against Phase 0 (5d73e8f5 + docs, same gates): CERTIFICATE_DRIFT
`test_core_certificate.py::test_the_certificate_describes_this_tree` (baseline) and
`::test_the_certificate_records_the_v1_relationship_truthfully` (new: F4 edits a Core file, which moves
the V1-compatible digest); PRE-EXISTING FLAKE `test_formal_xdist.py::test_plain_xdist_would_credit_a_crash_so_the_guard_is_required`
on 3.12 under `-n 4` (baseline; passes in isolation on 3.11 and 3.12). Phase 0's
`test_change_impact.py::test_the_old_gap_a_domain_models_own_tests_are_now_selected` now passes. No
REAL_REGRESSION.

Benchmark digest attribution (Phase 12): `git diff --stat 5d73e8f5..HEAD -- benchmarks experiments
flagships certification '*.json' '*.csv'` is empty: no committed numeric or benchmark artifact moved;
the digest-pinned benchmark tests pass in every tier above.

Host branch protection: NOT re-verified this session (`gh` is not installed in Ubuntu and the session
was restricted to Linux). Last recorded read-only check (ACTIVE_PLAN, 2026-10-13): `main` unprotected,
protection/ruleset endpoints 403, squash and rebase merges enabled. FIX 9 does not change any host
setting and makes no status check required.

Failed approaches: a closed-world reader that counted every input statement as read let an invented
`missing_inputs` path hide a retraction (fixed c2d592a4, d150f975); a duplicated-test-name probe and a
malformed H10 mutant (syntax error) were corrected; a commit helper that took an absolute message path
committed with a stale message once (amended before anything else built on it).
## Hostile remediation round 1 — final matrix and hardened recertification, 2026-10-14

Late fixes after the first entry: 313bbf1e (harness: a FAILED line is attributed to its own nodeid --
the 3.12 "xdist flake" since Phase 0 was a real parsing bug in tests/mutation_guards.py and the xdist
test driver, reproduced by terminal width: passes at COLUMNS 40/80, failed at 200; mutation HX-M1/M2
killed) and 05522b59 (no unadmitted skips: a provider liveness check that skipped without psutil now
reads the POSIX kernel, the case-twin ownership test runs on any filesystem; SK-M1..M3 killed; no skip
rule added).

Final matrix at ae25aed9 (`gates.sh phase11d`, integration clone): regression exit 0; FAST 3.11 10362
passed / 2 failed; FAST 3.12 10361 / 3; SCIENTIFIC 3.12 10934 / 3; FULL 3.12 10938 / 3 -- failures are
the two certificate-drift tests (resolved by recertification) and the xdist test fixed in 313bbf1e.

Hardened recertification (`python -m tools.certification.local_assurance run --reuse --repository
sharq-labs/forge --python311 .forge/venvs/3.11/bin/python --python312 .forge/venvs/3.12/bin/python`):
- run at ae25aed9 with system python3.11: REFUSED in 0 s (no pytest) -- wrong interpreter flag.
- run at ae25aed9 with venv interpreters: REFUSED at FAST 3.12 on the xdist parsing bug.
- run at 313bbf1e: every execution gate passed (FAST 3.11/3.12 10347, SCIENTIFIC 10920, campaign 4,
  regression 256, Formal 284/284 killed, V4 every entry at its declared verdict, trust 0 survived);
  REFUSED on two skips with no committed admission rule.
- run at 05522b59 (first attempt lost to a WSL restart mid-Formal; re-run): **SOURCE_PASS**, wall
  12422 s. FAST 3.11 10350 / 3.12 10350 passed, SCIENTIFIC 10923, campaign 4, regression 256, Formal
  284/284, V4 8 shards all at declared verdicts, trust 0 survived. SKIP_ADMISSION skipped 468, accepted
  468, unexpected 0. RECEIPT_SHA256 efe9d0940d2c2be94c8dca3a1850a02bc7f9289277c52dcc227171f0584e0cfc.
- certificate-only child b1eea81b "certification: recertify hardened core";
  `python -m tools.certification.local_assurance verify`: 22 deferred certificate/freeze self-checks
  passed; **LOCAL_ASSURANCE: PASS**, SOURCE_SHA 05522b59, CERTIFICATE_CHILD_SHA b1eea81b,
  RECEIPT_SHA256 51b42770425ad168b61bc4b7c8a850e34f0e794f0c50c16c6e24c9d5f7984d3a.
- fresh process, `env -u PYTHONPATH python -m tools.certification.core_certificate --verify --certificate
  certification/current_core_v2.json`: "certificate matches the tree", OK, exit 0. The certificate
  binds 05522b59 (clean) and adds the verdict_authority and system_runtime_authority areas and the
  production-registry pin (456 evidence-code files). Old target 39d43456 superseded.

Not pushed, not merged (user instruction). Host branch protection not re-verified.
## 2026-10-14 — User-requested gaps catalogue (docs only)

Created seven Arabic Markdown files under gaps/, preserving all five research
tables (57 entries, with intentional overlap), star ratings, implementation slices,
acceptance criteria and sources. This is a research catalogue, not an executable
queue or current defect certification. No production behavior changed.

Conversation baseline: a3f757eb5fdbc804ef11e3c4088a757c31981870.
PR base: 5d73e8f5118aa845f1957decc5aae986e72476a9. Main had advanced;
historical findings are explicitly marked for re-verification. Existing local
uncommitted planning/review files remain untouched in the original checkout.

Documentation validation: an inline Python script via PowerShell here-string
piped to `py -3.14 -` counted seven Markdown files, asserted 57 unique table IDs,
and checked every relative link and explicit HTML anchor. PASS, exit 0.
External URLs were not rechecked by that validator.

Command: `git diff --check`. Result: PASS, exit 0 before staging.
Scientific tests / forge_check / regression / FAST / SCIENTIFIC / certification:
**NOT RUN** (documentation-only). No scientific verification or validation claimed.

Failed approach: embedding the validator's PowerShell here-string inside another
here-string for a progress append produced a ParserError before execution. Used
apply_patch instead; no partial append or repository mutation from the failed command.

Command: git diff --cached --check. Initial result: seven trailing blank-line warnings in new Markdown files; trimmed EOF whitespace. Repeated result: PASS, exit 0.

## 2026-10-14 — Additional gaps catalogue review (docs only)

User requested additional cross-cutting gaps and publication on PR #136. Read the
PR state: already merged as 375ab559677768dec5ab2c7267f20d127f51b197.
Created codex/gaps-additional-review from that main HEAD for a follow-up PR.

Added ten proposals in gaps/06-additional-cross-cutting-gaps.md, each with inspected
source, existing capability, bounded next slice, counterexample/acceptance criteria,
ownership, dependencies, ease and impact. Index now counts 67 entries in six tables.
These are catalogue coverage gaps, not ten reproduced defects. No executable plan,
maturity evidence, certified artifacts or scientific behavior changed.

Documentation check command (executed in the PR worktree):
```powershell
@'
from pathlib import Path
import re
files=sorted(Path('gaps').glob('*.md'))
ids=[]
for p in files:
    text=p.read_text(encoding='utf-8')
    ids+=re.findall(r'^\| ([CRPGUN]\d{2}) \|',text,re.M)
    for target in re.findall(r'\]\(([^)]+)\)',text):
        if target.startswith(('https://','http://')): continue
        name,_,anchor=target.partition('#')
        dest=(p.parent/name).resolve() if name else p
        assert dest.exists(), (str(p),target)
        if anchor: assert f'id="{anchor}"' in dest.read_text(encoding='utf-8'), (str(p),anchor)
assert len(files)==8, len(files)
assert len(ids)==len(set(ids))==67, len(ids)
print('PASS: 8 Markdown files, 67 unique entries; local links and explicit anchors resolve. External URLs not checked.')
'@ | py -3.14 -
```
Result: PASS, exit 0. Eight Markdown files, 67 unique entries, all local links and
explicit anchors resolve. External URLs not checked. Scientific tests, regression,
FAST, SCIENTIFIC, certification: **NOT RUN** (documentation-only).

Read-only inspection traps: scientific/multiphysics/convergence.py does not exist;
the record is in plan.py and the calculator in execution/multiphysics/convergence.py.
PowerShell rg with a literal *.py path failed; use a directory plus -g '*.py'.
No code or state changed by either failed read.
Command: git diff --cached --check. Result: PASS, exit 0. Documentation link/count check repeated after the sources update: PASS, exit 0.

## 2026-10-14 — More design and coupling improvement proposals (docs only)

User requested more improvement proposals. PR #137 was read as open and unmerged;
continued on codex/gaps-additional-review at 415f9993056bce2a0bcd8a62d21c5184eef6f4ab.
Added eight source-linked proposals in gaps/07-design-and-coupling-improvements.md:
parameter identifiability, measured multifidelity screening, derivative consistency,
initial-state consistency, boundary/frame semantics, discontinuity semantics,
declared mesh transitions, and consumed material-property coverage.

Catalogue now has nine Markdown files and 75 table entries across seven tables.
Each proposal records existing code, bounded first slice, adversarial acceptance,
ownership/dependencies and ease/impact stars. No behavior, executable queue,
maturity evidence, frozen contract or certificate changed.

Documentation command:
```powershell
@'
from pathlib import Path
import re
files=sorted(Path('gaps').glob('*.md'))
ids=[]
for p in files:
    text=p.read_text(encoding='utf-8')
    ids+=re.findall(r'^\| ([CRPGUNX]\d{2}) \|',text,re.M)
    for target in re.findall(r'\]\(([^)]+)\)',text):
        if target.startswith(('https://','http://')): continue
        name,_,anchor=target.partition('#')
        dest=(p.parent/name).resolve() if name else p
        assert dest.exists(), (str(p),target)
        if anchor: assert f'id="{anchor}"' in dest.read_text(encoding='utf-8'), (str(p),anchor)
assert len(files)==9, len(files)
assert len(ids)==len(set(ids))==75, len(ids)
print('PASS: 9 Markdown files, 75 unique entries; local links and explicit anchors resolve. External URLs not checked.')
'@ | py -3.14 -
```
Result: PASS, exit 0; nine Markdown files, 75 unique table IDs, all local links and
explicit anchors resolve. External URLs not checked. Scientific tests, regression,
FAST, SCIENTIFIC and certification: **NOT RUN**, documentation-only.
Command: git diff --cached --check. Result: PASS, exit 0 for the design/coupling proposal update.

## 2026-10-15 — Quick wins: G0 CI record on `main` and catalogue item X08 (user-requested)

User request: read the plan and the Markdown files, then implement the easiest and quickest items.
Branch `fix/ci-reproduce-and-g0-record`, worktree `D:/forge-quickwins`, base `origin/main` `e193e573`.
No certified file, threshold, criterion, certificate or frozen artifact was changed.

### 1. The restored CI triggers did run on `main` (ACTIVE_PLAN item ticked)

Read-only `gh run list` / `gh run view --log` for `sharq-labs/forge`. On push of `e193e573` (PR #142),
2026-10-14: Tests run 38544091505, Branch Policy run 38544091368. Classification:

| Job | Result | Cause | Class |
|---|---|---|---|
| fast (3.11), fast (3.12) | 1 failed, 10359 passed, 170 skipped | `test_the_certificate_describes_this_tree` | GOVERNANCE: certificate does not bind `main` (OD-3) |
| scientific | 1 failed, 10946 passed, 156 skipped | same single test | same (OD-3) |
| Branch Policy | exit 1 | `gh api .../rules/branches/main` HTTP 403 (needs Pro or a public repo) | OD-1 |
| reproduce (Docker) | 161 failed, 10164 passed, 178 skipped | 150 need git history (`.dockerignore` drops `.git`; checkout is depth 1): no repository root, `git rev-parse` 128, freeze manifests, replay `NOT_REPRODUCIBLE` for a missing commit identity; 11 `test_oracle_ngspice_dc` because the image's ngspice-39 exits 1 after a correct `.control`/`op` run (ngspice-42 on the hosted runner exits 0) | CI environment, not a product regression; the fix needs `fetch-depth: 0` plus a `.git` mount in certified `tests.yml` (`certified:certification_control`), so it waits for OD-3 |
| mutations | cancelled at 6 h 0 m | GitHub job time limit | infrastructure |
| tests-gate | failure | aggregates the above | — |

No `SCIENTIFIC_CORRECTNESS` failure was found in these runs. This is a classification from the logs,
not a rerun.

### 2. X08 first slice: `engcore.materials.coverage` (gaps/07, ease 4/5)

`material_coverage_report(property_set, state, required, *, requirement_source, consumed=())` re-resolves
each STATED requirement through the existing `MaterialPropertySet.resolve` at one `MaterialState` and lists
`without_value`, `conflicted`, `uncertainty_unknown`, `assumed`, `interpolated` and `unrequired_with_data`
(named, not resolved, not judged). Classification `resolution_report_not_evidence`; status
`every_stated_requirement_has_a_value` / `a_stated_requirement_has_no_value`. No new resolution logic,
evidence, uncertainty vocabulary or provenance. Nothing in production imports it yet.

Independent `forge-scientific-review` (read-only): no BLOCKER; CHANGES REQUIRED for
- M1: the report was not bound to the run, so a caller could under-declare `required`. Fixed: statuses and
  fields renamed to say "stated"; a required `requirement_source`; an optional `consumed` list of the run's
  own `ResolvedProperty` records refuses an unstated consumed property and a record that does not equal a
  fresh resolution at this state.
- M2: the public constructors were unchecked. Fixed: `MaterialCoverageReport.__post_init__` refuses empty,
  unsorted or duplicate entries, entries resolved at another state or from another set, and overlap with
  `unrequired_with_data`.
- M3: the first draft re-exported the module from `src/engcore/materials/__init__.py`, an evidence-code file
  pinned by the certificate. Fixed: the re-export was reverted; `__init__.py` is byte-identical to base and
  the module is reachable by path only.
- Minor m1–m5 and m7 also fixed (uncertainty `source_kind`, structured `conflicted`, value and rule in the
  entry, stronger serialization assertions, a whitespace-duplicate case). m6 (an ASSUMED input to a
  FITTED/DERIVED datum resolves as SOURCED) is inherited from `properties.py` and is not changed here.

Commands (Windows, `.venv` Python 3.14, `PYTHONPATH="<wt>/src;<wt>"`, `--basetemp` on D:):

- `python -m pytest tests/test_materials_engine.py -q -p no:cacheprovider` -> 23 passed.
- Targeted mutation script (9 mutants of `coverage.py`, apply, run, restore): 8 KILLED. SURVIVED: removing
  the factory's duplicate check, an equivalent mutant because the report constructor refuses the same input.
- `tools/forge_check.py --changed --dry-run` selected the whole FAST tier, so FAST was run:
  `python -m pytest -m "not expensive" -q -n 4` -> branch (uncommitted): 155 failed, 10172 passed,
  189 skipped, 22 errors. Same command on a pristine `origin/main` worktree: 153 failed, 10167 passed,
  189 skipped, 22 errors. The failure sets are identical apart from two tests present only on the branch:
  `test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1` and
  `test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks`.
  Both report `tree.clean -- uncommitted`. Their rerun after the commit is recorded below. The 153 shared
  failures are the known Windows / certification baseline (mutation workspace, escrow, authority, formal
  xdist, local assurance, certificate and freeze self-checks); none is in `materials`.

Failed approach: the first `forge_check --changed` run started before the review fixes and was stopped; it
produced no result. Its process tree was killed by PID.

Not done: the Docker `reproduce` fix (needs OD-3 for `tests.yml`); X08 is not wired into any engineering or
system-runtime report yet; SCIENTIFIC tier, regression pack and Linux runs **NOT RUN**.

Rerun after commit `aa160b6d` (clean tree): `python -m pytest tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1 tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks tests/test_materials_engine.py -q` -> 25 passed. The branch's FAST failure set therefore equals the pristine base's (153 failed, 22 errors on Windows); no failure is attributable to this change.

## 2026-10-15 — Red `reproduce` job: full read-only history, non-root user, trixie ngspice (branch `fix/ci-reproduce-docker-history`, worktree `D:/forge-reproduce`, local only)

Base `origin/main` @ `e193e573`. Tests run `38544091505`, job `reproduce` (115786199600):
161 FAST failures (10164 passed, 178 skipped). On the same commit, hosted `fast (py 3.12)` failed only
`tests/test_core_certificate.py::test_the_certificate_describes_this_tree` (OD-3 drift:
`tests/test_formal_xdist.py`, `tests/mutation_guards.py`).

Causes, from the job log:
- **149 history.** `.dockerignore` drops `.git` and the checkout is depth 1. Errors included
  `no repository root above /crafty/...`, `git rev-parse HEAD` exiting 128, `af43c896`/`7876bd9f`
  snapshots unreadable, and replay `NOT_REPRODUCIBLE` (no commit identity).
- **1 root.** `test_mutation_workspace.py::test_mid_walk_failure_still_reports_entries_already_scanned`
  reported *DID NOT RAISE PermissionError*: chmod 000 does not stop root. The earlier "150 history"
  count included this one.
- **11 ngspice.** In `tests/oracles/test_oracle_ngspice_dc.py`, bookworm's ngspice-39 printed the
  correct OP and exited 1 (*no simulations run*). In `src/main.c` at tag ngspice-39 there is no
  `sim_status` branch. At tags 42 and 44.2 the batch-exit block is byte-identical and returns
  `EXIT_NORMAL` after a `.control` simulation. Debian trixie ships `44.2+ds-1`, whose only patch is
  `fixes/spelling-Fix-misspelled-word-unkown.patch` (read from sources.debian.org).

Change (`Dockerfile`, `.github/workflows/tests.yml` reproduce job, `docs/reproduce.md`):
- `python:3.12-slim-trixie`.
- The job checks out with `fetch-depth: 0` and `persist-credentials: false`, then runs
  `docker run --rm -v "${GITHUB_WORKSPACE}/.git:/mnt/history:ro"`.
- The script copies `/mnt/history` to `/crafty/.git` and runs as `crafty` (uid 10001).
- It refuses (exit 2) when history is missing, mounted at the old `/crafty/.git`, shallow, or
  when `HEAD` does not match the image tree.
- The oracle's `returncode == 0` assertion is unchanged, and nothing is deselected.

**Failed approach, do not repeat:** mounting `.git` in place with
`git config --system --add safe.directory /crafty`. `tools/certification/ownership.py` runs git with
global and system config switched off, so `git ls-files` still refused the foreign-owned mount as
*dubious ownership*. Exporting `GIT_CONFIG_SYSTEM` in the test environment trips admission instead
(*inherited Git overrides refused*).

Executed (WSL Ubuntu 24.04, CPython 3.12.3, ngspice-42; no Docker anywhere locally):
- Emulation v1 (in-place ro bind mount, safe.directory via `GIT_CONFIG_SYSTEM`, run as root):
  `python -m pytest -m "not expensive" -q -n 4 --dist loadfile`.
  Result: FAIL, 7 failed / 4 errors, 10365 passed, 155 skipped.
  - 6 `OwnershipError` dubious ownership: `test_change_impact` ×4 errors + f7,
    `test_repository_ownership::test_the_real_checkout_graph_never_contains_an_environment`.
  - Root: `test_mutation_workspace::test_mid_walk...`.
  - Emulation artifacts: `test_local_telemetry...` (env override) and `test_escrow_isolation` ×2
    (WSL root can `unshare`).
  - OD-3: the certificate test.
- Emulation v2, the shipped design: tree owned by uid 1000, history a root-owned copy unwritable by
  uid 1000, reproduce script generated from the Dockerfile's `printf` block.
  - Refusal controls: no history, old mount point, depth-1 history and tree drift each exit 2;
    the control exits 0; the source history is not writable by the test user.
  - The generated `reproduce`: `1 failed, 10375 passed, 155 skipped in 168.40s`. FAILED:
    `test_the_certificate_describes_this_tree` (drift: `.github/workflows/tests.yml` from this
    change, plus main's two files). This is the hosted failure set plus this change's certified file.
  - `pytest tests/oracles/test_oracle_ngspice_dc.py tests/test_mutation_workspace.py::test_mid_walk... tests/test_recertification_scope.py -q -rs`:
    117 passed, 0 skipped.
  - `python tools/forge_check.py --changed --base e193e573 --workers 4`: exit 0, 279 passed.
    It reports `.github/workflows/tests.yml` as RECERTIFICATION_REQUIRED (`certified:certification_control`)
    and `Dockerfile` as unclassified reach.
- **NOT RUN:** `docker build` / `docker run`, an ngspice-44.2 binary, SCIENTIFIC, hardened
  recertification. The first pushed `reproduce` run is the measurement. While main's certificate
  is stale, expect exactly the OD-3 certificate failure there; the benchmark stage does not run
  under `set -e`.

Owner: the workflow edit needs OD-3 recertification. Nothing is pushed or merged.

## 2026-10-15 - Solver support-gate review fixes

- Finding: ngspice DC adapter matched realizations by model id only (served_models=()), so a problem naming electrical.dc.kcl@99.0 was accepted while the native solver refused it.
- Finding: the native DC adapter accepted a problem naming a served model alongside an unknown one; the unknown model was silently never assessed.
- Fix: dc_realizations.py keys realizations by (model_id, version); ngspice.py gate and binding use the version key; dc/solver.py adds additional_support_gap refusing any named model it does not serve. The core protocol.py was NOT changed (pinned by certification/current_core_v2.json, digest-protected).
- Tests added: tests/domains/electrical/test_support_version_gate.py (6 tests; 4 fail on the committed files, confirmed by swap).
- Command: .venv/Scripts/python.exe -m pytest tests/domains/electrical tests/test_heterogeneous_ngspice.py -q -p no:cacheprovider --basetemp=<scratch>
  Result: 393 passed.
- Command: .venv/Scripts/python.exe -m pytest <127 test files referencing electrical/ngspice/consensus> -m "not expensive and not campaign" -q -n 4
  Result: 3084 passed, 3 skipped, 13 failed, 1 error. All 13 failures and the error are pre-existing harness issues: ModuleNotFoundError for bare sibling test imports (test_cross_solver_consensus, test_trusted_consensus_gate, mutation_guards) and two guard tests (test_the_bare_install_the_readme_documents_is_the_one_that_must_be_green, test_the_domain_names_were_derived_from_the_packages_not_listed) that also fail on the committed files.
- Not run: the full FAST/SCIENTIFIC tiers and the core certificate test (protocol.py untouched).
- Open (not fixed): DC validation _worst_against skips NaN residuals (electrical/dc/validation.py); CSTR sampled-extrema admission in cstr/solver.py bundle path; the core rule "any-overlap" in scientific/solvers/protocol.py needs a core-freeze decision.

## 2026-10-12 G0 evidence: FAST on `main` @ `8b028dc` in a supported Python, and failure attribution

- Command: `env -u GIT_* <py3.12 venv>/bin/python -m pytest -m "not expensive" -q -n 2 -p no:cacheprovider` in a clean
  worktree of `main` @ `8b028dc` (CPython 3.12.13 via uv, pytest 9.1.1, `.[dev,oracles,benchmarks,symbolic]`, the
  container's `GIT_CONFIG_*` proxy variables removed, running as root). Result: 7 failed, 9507 passed, 192 skipped,
  5 errors, 992 s. Tree clean afterwards.
- Re-run of those 12 node ids with `mcp>=2.1 anyio>=4.0` added: 2 failed, 41 passed. **So on a supported Python with
  the extras CI installs, FAST on `main` has exactly two failures:**
  - `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` — GOVERNANCE_ONLY candidate (evidence
    record not yet complete): areas `certification_control` (`skip_admission.py`, `test_skip_admission.py`), `harness`
    (`test_core_guards.py`) and `runtime_dependencies` (`pyproject.toml`) changed after recertification `d383eed0`.
  - `tests/test_mutation_workspace.py::test_mid_walk_failure_still_reports_entries_already_scanned` — ENVIRONMENT:
    `chmod(0)` does not deny root; the container runs as uid 0.
- Attribution of the earlier 3.13 drift set (same tests, same tree):
  - six freeze-v4 / batch56 failures are **Python-version artefacts**: `tools/certification/api_surface_v4.py` records
    methods Forge classes inherit from builtins; on 3.13 that adds 106 (`str.format`, `format_map`,
    `BaseException.add_note`, `with_traceback`, ...) and changes 29 (`str.replace` `count` became keyword-capable),
    with zero differences in Forge-defined members. The v4 surface is therefore only verifiable on <= 3.12.
  - `test_local_telemetry_is_outside_manifest_and_cannot_verify_as_receipt` is the `GIT_*` environment refusal in
    `local_assurance._assurance_lock`, not a defect.
- Without the `[mcp]` extra, 5 modules fail to import and 5 tests fail (`server.py` imports the SDK; several tests
  import it without `importorskip`, and five modules import helpers from `tests/mcp/test_battery_boundary.py`, which
  skips at module level). `pyproject.toml` states the suite must stay green without `[mcp]`; CI always installs it,
  so the rule is untested and currently false.
- Benchmark rounds `model_measurement_validation` and `empirical_validation` pin `EXPECTED_SCIENTIFIC_DIGEST` (a digest
  of live `src/engcore/scientific`); it last matched at `89b6eb31` and broke at `10bcbb65` (PR #21, 2026-09-12). Their
  "rebuild reproduces the published gates" tests have failed since, and the MV one rewrites the committed
  `SAFETY_GATES.json`.
- Checked and NOT a problem: a cProfile run attributed 478 s to one HiGHS call; measured directly it is 12 `linprog`
  calls totalling 0.07 s (profiler artefact). Test collection imports cost 8 s for 571 modules.
- Measured, not changed: `_distributions_providing` calls `importlib.metadata.packages_distributions()` per module
  (26 calls, ~612k file lookups each run) and `test_core_api_contracts._guard_module()` re-executes
  `test_core_guards.py` per call; caching both took the four dependency-hygiene tests from 75 s to 30 s (same result).

## 2026-10-12 PR landing pass — outcome (owner direction: resolve conflicts, merge what passes every gate)

- Merged, one at a time, each by a merge commit after merging `main` into the PR branch (no rebase, no force push, no
  force merge; each landing gate is recorded in the PR's own entry above):
  - #126 -> `17444e14`;
  - #123 -> `21b7d20f`;
  - #117 -> `2d0fa6c3`.
  After each merge, `main`'s tree was checked identical to the tested PR head (`git rev-parse origin/main^{tree}`).
- Blocked (not merged, no branch changed):
  - #107 (self-hosted heavy CI runner, 237 behind). `certification/current_core_v2.json` conflicts between two
    owner certificates. Resolving that means choosing one or editing a certified artifact. It also rewrites
    `tests.yml` / `recertify-hardened-core.yml` and adds self-hosted runners that read secrets: an owner decision (OD-11).
  - #39 (draft) and #24 (base `claude/core-v2-hybrid-uq`), 1,530 / 1,569 behind `main` (GitHub compare). They are not
    unrelated histories: the missing merge base came from this session's shallow clone. Their regression tests,
    copied onto `main` `2d0fa6c3` and removed afterwards:
    - `python -m pytest -q tests/_stale39_* tests/_stale24_*` -> 6 failed, 14 passed.
    - Two are API drift: hybrid `considered` rows; calibration `residuals` key.
    - Two are wording only: `main` already refuses the same non-finite / inconsistent predictive UQ inputs, with
      different messages.
    - Two (`test_result_is_usable_only_when_every_declared_model_is_in_domain`, in both PRs) are a real semantic
      difference. `main` deliberately excludes validity from `ScientificResult.is_usable`
      (`docs/assurance/CORE_SEMANTIC_INVARIANTS.md`, truth table pinned by test). Changing that in frozen Core is a
      scientific-design decision: OD-21 (numbered OD-15 on its branch; renumbered at the 2026-10-16 landing).
- Post-pass state: open PRs #107, #39, #24. Hardened recertification of `main`: NOT RUN (OD-3). FAST on `2d0fa6c3`
  itself: NOT RUN (its tree = `9e92573e`, whose FAST-tested parent `bfccb351` differs by one PROGRESS entry).
- Failed approach: `git merge-tree` against #39 / #24 exited 128 ("no merge base"). That was the shallow clone, not
  unrelated histories. Use the GitHub compare API, or deepen the clone, before calling histories unrelated.


## 2026-10-13 Final test infrastructure assurance closeout — BLOCKED

Source origin/main 5d73e8f5118aa845f1957decc5aae986e72476a9, tree ed305a44e69429fe06bb1e92954237aadd005080. Dedicated Windows and Linux worktrees; original dirty checkout preserved. Full commands, exact failures, outcomes and limits: `docs/work/FINAL_TEST_INFRASTRUCTURE_ASSURANCE_2026-10-13.md`. Raw argv/results/JUnit: `D:/forge-final-assurance-evidence/executed-commands-and-results.json`.

command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-m", "tools.certification.core_certificate", "--verify"]`
result: exit 1; wall 1.3 s; counts null; tracked byte drift 0; git status ''
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-m", "tools.certification.core_freeze_v4", "--verify"]`
result: exit 1; wall 17.22 s; counts null; tracked byte drift 0; git status ''
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.11/bin/python", "-c", "import sys,pytest,xdist,platform; print(sys.version); print(platform.platform()); print(\"pytest\",pytest.__version__,\"xdist\",xdist.__version__)"]`
result: exit 0; wall 1.84 s; counts null; tracked byte drift 0; git status ''
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.11/bin/python", "-m", "pytest", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "-q", "--junitxml", "/mnt/d/forge-final-assurance-evidence/linux-guard-311.xml"]`
result: exit 0; wall 9.22 s; counts {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}; tracked byte drift 0; git status ''
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.11/bin/python", "-m", "pytest", "-m", "not expensive", "-q", "-n", "4", "--dist", "loadfile", "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "--junitxml", "/mnt/d/forge-final-assurance-evidence/linux-fast-311.xml"]`
result: exit 1; wall 140.22 s; counts {"tests": 10185, "failures": 2, "errors": 0, "skipped": 157}; tracked byte drift 0; git status ''
failure: `tests.test_core_certificate::test_the_certificate_describes_this_tree`
failure: `tests.test_change_impact::test_the_old_gap_a_domain_models_own_tests_are_now_selected`
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-c", "import sys,pytest,xdist,platform; print(sys.version); print(platform.platform()); print(\"pytest\",pytest.__version__,\"xdist\",xdist.__version__)"]`
result: exit 0; wall 1.21 s; counts null; tracked byte drift 0; git status ''
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-m", "pytest", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "-q", "--junitxml", "/mnt/d/forge-final-assurance-evidence/linux-guard-312.xml"]`
result: exit 0; wall 9.22 s; counts {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}; tracked byte drift 0; git status ''
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-m", "pytest", "-m", "not expensive", "-q", "-n", "4", "--dist", "loadfile", "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "--junitxml", "/mnt/d/forge-final-assurance-evidence/linux-fast-312.xml"]`
result: exit 1; wall 132.22 s; counts {"tests": 10185, "failures": 2, "errors": 0, "skipped": 157}; tracked byte drift 0; git status ''
failure: `tests.test_core_certificate::test_the_certificate_describes_this_tree`
failure: `tests.test_change_impact::test_the_old_gap_a_domain_models_own_tests_are_now_selected`
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-m", "pytest", "-m", "not campaign", "-q", "-n", "4", "--dist", "loadfile", "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "--deselect", "tests/test_heterogeneous_ngspice.py::test_a_the_provider_is_a_real_external_process", "--deselect", "tests/test_heterogeneous_ngspice.py::test_g2_a_genuine_non_zero_exit_is_a_provider_failure", "--deselect", "tests/test_heterogeneous_ngspice.py::test_j_relocating_the_provider_leaves_the_result_byte_identical", "--deselect", "benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates", "--deselect", "benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates", "--junitxml", "/mnt/d/forge-final-assurance-evidence/linux-scientific-312.xml"]`
result: exit 1; wall 234.26 s; counts {"tests": 10758, "failures": 2, "errors": 0, "skipped": 157}; tracked byte drift 0; git status ''
failure: `tests.test_change_impact::test_the_old_gap_a_domain_models_own_tests_are_now_selected`
failure: `tests.test_core_certificate::test_the_certificate_describes_this_tree`
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "tools/forge_check.py", "--regression"]`
result: exit 0; wall 11.21 s; counts null; tracked byte drift 0; git status ''
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-m", "pytest", "-q", "-n", "8", "--dist", "loadfile", "--junitxml", "/mnt/d/forge-final-assurance-evidence/linux-full-312.xml"]`
result: exit 1; wall 147.29 s; counts {"tests": 10768, "failures": 4, "errors": 0, "skipped": 157}; tracked byte drift 0; git status ''
failure: `benchmarks.empirical_validation.tests.test_empirical_validation::test_rebuilding_everything_reproduces_the_published_gates`
failure: `benchmarks.model_measurement_validation.tests.test_model_measurement_validation::test_rebuilding_everything_reproduces_the_published_gates`
failure: `tests.test_core_certificate::test_the_certificate_describes_this_tree`
failure: `tests.test_change_impact::test_the_old_gap_a_domain_models_own_tests_are_now_selected`
command argv: `["/home/dev_kaeem/forge-final-assurance/.forge/venvs/3.12/bin/python", "-m", "tools.certification.assert_clean_tree"]`
result: exit 0; wall 1.21 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "tools.certification.core_certificate", "--verify"]`
result: exit 1; wall 1.69 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "tools.certification.core_freeze_v4", "--verify"]`
result: exit 1; wall 1.58 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "tools/forge_check.py", "--regression"]`
result: exit 0; wall 20.72 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "pytest", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "-q", "--junitxml", "D:\\forge-final-assurance-evidence\\winretry-dependency-guard.xml"]`
result: exit 0; wall 36.62 s; counts {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "pytest", "-m", "not expensive", "-q", "-n", "4", "--dist", "loadfile", "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "--junitxml", "D:\\forge-final-assurance-evidence\\winretry-fast.xml"]`
result: exit 1; wall 222.2 s; counts {"tests": 10056, "failures": 256, "errors": 27, "skipped": 210}; tracked byte drift 0; git status ''
failure: `::tests.domains.battery.test_audit_domains_battery_pulse`
failure: `::tests.mcp.test_answer`
failure: `::tests.mcp.test_audit_domains_electrothermal_transient`
failure: `::tests.mcp.test_audit_domains_refused_coupling`
failure: `::tests.mcp.test_claim_assessment`
failure: `::tests.mcp.test_core_scientific_audit_batch8`
failure: `tests.test_mutation_workspace::test_manifest_is_complete_deterministic_and_includes_git`
failure: `tests.test_mutation_workspace::test_mutation_changes_worker_only_and_repairs_exact_bytes`
failure: `tests.test_mutation_workspace::test_restore_repairs_all_contamination_types[deleted]`
failure: `tests.test_mutation_workspace::test_restore_repairs_all_contamination_types[unexpected]`
failure: `tests.test_mutation_workspace::test_restore_repairs_all_contamination_types[mode]`
failure: `tests.test_mutation_workspace::test_restore_repairs_all_contamination_types[git]`
failure: `tests.test_mutation_workspace::test_restore_repairs_all_contamination_types[replaced-directory]`
failure: `tests.test_mutation_workspace::test_contamination_before_attempt_invalidates_without_entering`
failure: `tests.test_mutation_workspace::test_restore_failure_cannot_issue_a_verdict_or_start_next_attempt`
failure: `tests.test_mutation_workspace::test_seed_tampering_refuses_restore`
failure: `tests.test_mutation_workspace::test_next_mutation_observes_pristine_identity`
failure: `tests.test_mutation_workspace::test_failure_restores_then_cleans_owned_workspace[OSError]`
failure: `tests.test_mutation_workspace::test_failure_restores_then_cleans_owned_workspace[KeyboardInterrupt]`
failure: `tests.test_mutation_workspace::test_concurrent_shards_have_distinct_mutable_state`
failure: `tests.test_mutation_workspace::test_worker_symlink_is_removed_without_touching_source`
failure: `tests.test_mutation_workspace::test_seed_symlink_and_git_external_pointer_are_refused`
failure: `tests.test_mutation_workspace::test_linked_artifacts_and_repository_local_storage_are_refused`
failure: `tests.test_mutation_workspace::test_v4_population_once_and_existing_transcript_contract`
failure: `tests.test_mutation_workspace::test_v4_failure_paths_restore_before_next_mutation[no-report]`
failure: `tests.test_mutation_workspace::test_v4_failure_paths_restore_before_next_mutation[timeout]`
failure: `tests.test_mutation_workspace::test_v4_failure_paths_restore_before_next_mutation[application-refusal]`
failure: `tests.test_mutation_workspace::test_v4_restore_failure_never_returns_killed`
failure: `tests.test_mutation_workspace::test_formal_control_first_single_population_and_guard_transcript`
failure: `tests.test_mutation_workspace::test_local_telemetry_is_outside_manifest_and_cannot_verify_as_receipt`
failure: `tests.test_mutation_workspace::test_detached_children_are_drained_after_adoption`
failure: `tests.test_mutation_workspace::test_undrained_descendant_refuses_without_restoration_or_cleanup`
failure: `tests.test_mutation_workspace::test_descendant_drain_timeout_is_not_a_mutation_verdict`
failure: `tests.test_mutation_workspace::test_parent_retains_unreleased_worker_storage[False]`
failure: `tests.test_mutation_workspace::test_parent_retains_unreleased_worker_storage[True]`
failure: `tests.test_mutation_workspace::test_external_git_configuration_is_refused[[core]\nworktree = /external/source\n]`
failure: `tests.test_mutation_workspace::test_external_git_configuration_is_refused[[Core]\nworktree = /external/source\n]`
failure: `tests.test_mutation_workspace::test_external_git_configuration_is_refused[[cOrE]\nWorkTree = /external/source\n]`
failure: `tests.test_mutation_workspace::test_external_git_configuration_is_refused[[include]\npath = /external/config\n]`
failure: `tests.test_mutation_workspace::test_pristine_index_is_reused_without_retaining_file_bytes`
failure: `tests.test_mutation_workspace::test_dirty_hints_do_not_hide_unrelated_same_size_and_restored_timestamp_bytes`
failure: `tests.test_mutation_workspace::test_known_target_restore_is_sparse_but_worker_sha_remains_complete`
failure: `tests.test_mutation_workspace::test_new_index_cannot_mask_seed_link_or_type_contamination[same-size-seed]`
failure: `tests.test_mutation_workspace::test_new_index_cannot_mask_seed_link_or_type_contamination[hardlink]`
failure: `tests.test_mutation_workspace::test_new_index_cannot_mask_seed_link_or_type_contamination[file-directory]`
failure: `tests.test_mutation_workspace::test_seed_permissions_are_read_only_and_cleanup_never_follows_substituted_directory`
failure: `tests.test_mutation_workspace::test_lifecycle_failure_diagnostics_preserve_exact_mutation_and_stage`
failure: `tests.test_mutation_workspace::test_drain_failure_stage_retains_worker_and_cannot_authorize_reuse`
failure: `tests.test_mutation_workspace::test_sparse_repair_does_not_chmod_through_symlink_ancestor`
failure: `tests.test_mutation_workspace::test_invalid_dirty_hint_poisoning_refuses_next_attempt`
failure: `tests.test_mutation_workspace::test_seed_mismatch_stops_before_first_restore_and_next_attempt[bytes]`
failure: `tests.test_mutation_workspace::test_seed_mismatch_stops_before_first_restore_and_next_attempt[deleted]`
failure: `tests.test_mutation_workspace::test_seed_mismatch_stops_before_first_restore_and_next_attempt[unexpected]`
failure: `tests.test_mutation_workspace::test_seed_mismatch_stops_before_first_restore_and_next_attempt[mode]`
failure: `tests.test_mutation_workspace::test_seed_mismatch_stops_before_first_restore_and_next_attempt[symlink]`
failure: `tests.test_mutation_workspace::test_seed_mismatch_stops_before_first_restore_and_next_attempt[hardlink]`
failure: `tests.test_mutation_workspace::test_seed_mismatch_stops_before_first_restore_and_next_attempt[directory]`
failure: `tests.test_mutation_workspace::test_restore_streams_seed_without_content_cache`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[core]\nhooksPath=/outside/hooks\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[Core]\nfsmonitor=/outside/monitor\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[extensions]\nworktreeConfig=true\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[includeIf "gitdir:/"]\npath=/outside/config\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[core ]\nworktree=/outside/work\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[core\t]\nworktree=/outside/work\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[extensions ]\nworktreeConfig=true\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[filter.driver]\nclean=/outside/helper\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[diff.driver]\ncommand=/outside/helper\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[filter "driver"]\nclean=/outside/helper\n]`
failure: `tests.test_mutation_workspace::test_git_external_helpers_and_worktree_config_are_refused[[core]\nattributesFile=/outside/attrs\n]`
failure: `tests.test_mutation_workspace::test_git_alternates_and_rewritten_history_are_refused[objects/info/alternates]`
failure: `tests.test_mutation_workspace::test_git_alternates_and_rewritten_history_are_refused[objects/info/http-alternates]`
failure: `tests.test_mutation_workspace::test_git_alternates_and_rewritten_history_are_refused[info/grafts]`
failure: `tests.test_mutation_workspace::test_git_alternates_and_rewritten_history_are_refused[refs/replace/name]`
failure: `tests.test_mutation_workspace::test_git_alternates_and_rewritten_history_are_refused[config.worktree]`
failure: `tests.test_mutation_workspace::test_ambiguous_owner_retains_worker_and_blocks_next_attempt`
failure: `tests.test_mutation_workspace::test_dedicated_process_contract_refuses_detectable_competing_owners[kernel-threads]`
failure: `tests.test_mutation_workspace::test_dedicated_process_contract_refuses_detectable_competing_owners[sigchld-handler]`
failure: `tests.test_mutation_workspace::test_dedicated_process_contract_refuses_detectable_competing_owners[sigchld-mask]`
failure: `tests.test_mutation_workspace::test_dedicated_process_contract_refuses_detectable_competing_owners[children]`
failure: `tests.test_mutation_workspace::test_dedicated_process_contract_refuses_detectable_competing_owners[subreaper]`
failure: `tests.test_mutation_workspace::test_telemetry_counter_accounting_failure_cannot_change_workspace_identity`
failure: `tests.test_mutation_workspace::test_seed_restore_open_descriptor_is_closed_on_write_failure`
failure: `tests.test_mutation_workspace::test_authenticated_clean_dirty_candidates_are_not_recopied[unchanged-hint]`
failure: `tests.test_mutation_workspace::test_authenticated_clean_dirty_candidates_are_not_recopied[mode-only]`
failure: `tests.test_mutation_workspace::test_cli_scratch_existing_user_artifacts_are_never_cleared`
failure: `tests.test_mutation_workspace::test_diagnostic_atomic_replacement_cannot_overwrite_link_target[symlink]`
failure: `tests.test_mutation_workspace::test_diagnostic_parent_substitution_is_ignorable_without_outside_write`
failure: `tests.test_mutation_workspace::test_git_lazy_fetch_and_unknown_formats_are_refused[[extensions]\npartialClone=origin\n]`
failure: `tests.test_mutation_workspace::test_git_lazy_fetch_and_unknown_formats_are_refused[[EXTENSIONS]\nobjectformat=sha256\n]`
failure: `tests.test_mutation_workspace::test_git_lazy_fetch_and_unknown_formats_are_refused[[remote "origin"]\npromisor=true\nurl=/outside/repo\n]`
failure: `tests.test_mutation_workspace::test_git_lazy_fetch_and_unknown_formats_are_refused[[extensions]\nunknownextension=true\n]`
failure: `tests.test_mutation_workspace::test_promisor_pack_marker_is_refused`
failure: `tests.test_mutation_workspace::test_abnormal_parent_retains_entire_scratch_without_workspace_marker`
failure: `tests.test_mutation_workspace::test_changed_sigchld_during_drain_retains_and_refuses`
failure: `tests.test_mutation_workspace::test_substituted_artifact_root_cannot_clear_user_basetemp`
failure: `tests.test_mutation_workspace::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[2]`
failure: `tests.test_mutation_workspace::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[3]`
failure: `tests.test_mutation_workspace::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[4]`
failure: `tests.test_mutation_workspace::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[5]`
failure: `tests.test_mutation_workspace::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[-9]`
failure: `tests.test_mutation_workspace::test_formal_infrastructure_exit_cannot_earn_transcript_credit[3]`
failure: `tests.test_mutation_workspace::test_formal_infrastructure_exit_cannot_earn_transcript_credit[4]`
failure: `tests.test_mutation_workspace::test_formal_infrastructure_exit_cannot_earn_transcript_credit[5]`
failure: `tests.test_mutation_workspace::test_formal_infrastructure_exit_cannot_earn_transcript_credit[-9]`
failure: `tests.test_core_guards::test_the_battery_march_runs_the_solver_it_names`
failure: `tests.test_mutation_workspace::test_string_path_snapshot_equals_the_pathlib_manifest_and_counters`
failure: `tests.test_mutation_workspace::test_mid_walk_failure_still_reports_entries_already_scanned`
failure: `tests.test_core_guards::test_every_marched_step_carries_its_own_cell_report`
failure: `tests.test_formal_xdist::test_every_infrastructure_defect_refuses[linked]`
failure: `tests.test_formal_xdist::test_formal_run_credits_only_with_a_clean_sentinel[clean]`
failure: `tests.test_formal_xdist::test_formal_run_credits_only_with_a_clean_sentinel[crash]`
failure: `tests.test_formal_xdist::test_formal_run_credits_only_with_a_clean_sentinel[absent]`
failure: `tests.test_formal_xdist::test_formal_run_credits_only_with_a_clean_sentinel[stale]`
failure: `tests.test_formal_xdist::test_serial_formal_run_has_no_xdist`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[1-FAILED tests/t.py::test_guard[a] - boom\n-True]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[1-FAILED tests/t.py::test_other - boom\n-False]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[0-1 passed\n-False]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[5-no tests ran\n-False]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[2-Interrupted\n-False]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[3-INTERNALERROR\n-WorkspaceError]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[4-usage\n-WorkspaceError]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[-11--WorkspaceError]`
failure: `tests.test_formal_xdist::test_serial_confirmation_only_credits_a_named_failure_alone[timeout--False]`
failure: `tests.test_formal_xdist::test_confirmation_needs_the_pristine_tree_plus_exactly_the_declared_edit`
failure: `tests.test_formal_xdist::test_confirmation_reads_the_name_from_the_nodeid_not_the_message`
failure: `tests.test_formal_xdist::test_named_alone_control_refuses_a_copy_changed_between_its_runs`
failure: `tests.test_formal_xdist::test_named_alone_control_selects_by_the_rule_and_voids_a_failing_guard[0]`
failure: `tests.test_formal_xdist::test_named_alone_control_selects_by_the_rule_and_voids_a_failing_guard[1]`
failure: `tests.test_formal_xdist::test_main_threads_workers_and_confirms_only_under_xdist`
failure: `tests.test_formal_xdist::test_an_unconfirmed_xdist_kill_is_not_credit`
failure: `tests.test_formal_xdist::test_import_refusal_attempts_stay_serial_with_a_serial_control`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[False-formal_mutations-4-1]`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[False-formal_mutations-4-2]`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[False-v4_mutations-8-1]`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[False-v4_mutations-8-2]`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[True-formal_mutations-4-1]`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[True-formal_mutations-4-2]`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[True-v4_mutations-8-1]`
failure: `tests.test_local_assurance::test_shards_are_bounded_isolated_and_fail_closed[True-v4_mutations-8-2]`
failure: `tests.test_local_assurance::test_source_gate_orchestration_preserves_checkout[None-1]`
failure: `tests.test_local_assurance::test_source_gate_orchestration_preserves_checkout[None-2]`
failure: `tests.test_local_assurance::test_source_gate_orchestration_preserves_checkout[formal_mutations_1-1]`
failure: `tests.test_local_assurance::test_source_gate_orchestration_preserves_checkout[formal_mutations_1-2]`
failure: `tests.test_local_assurance::test_source_gate_orchestration_preserves_checkout[v4_mutations_3-1]`
failure: `tests.test_local_assurance::test_source_gate_orchestration_preserves_checkout[v4_mutations_3-2]`
failure: `tests.test_local_assurance::test_child_exit_during_forced_kill_preserves_stream_error`
failure: `tests.foundations.test_v2_credibility_vector::test_the_projection_is_complete_and_a_fully_evidenced_claim_meets_high`
failure: `tests.foundations.test_v2_credibility_vector::test_levels_rest_on_issued_checks_and_registry_pinned_provenance`
failure: `tests.foundations.test_v2_credibility_vector::test_the_subject_is_bound_to_the_decision_context`
failure: `tests.foundations.test_v2_credibility_vector::test_levels_need_support_of_the_subject_admissible_authority_and_context`
failure: `tests.foundations.test_v2_credibility_vector::test_one_record_one_factor_is_decided_over_all_citations_and_removal_never_helps`
failure: `tests.foundations.test_v2_credibility_vector::test_independence_must_be_shown_positively`
failure: `tests.foundations.test_v2_credibility_vector::test_defeaters_block_and_only_a_newer_version_of_the_same_source_closes_one`
failure: `tests.foundations.test_v2_credibility_vector::test_an_outside_domain_finding_is_a_defeater_and_dominates`
failure: `tests.foundations.test_v2_credibility_vector::test_and_takes_the_weakest_and_or_takes_one_whole_independent_branch`
failure: `tests.foundations.test_v2_credibility_vector::test_adversarial_standing_needs_a_surviving_envelope_for_this_subject`
failure: `tests.foundations.test_v2_credibility_vector::test_removing_evidence_never_raises_any_factor_or_meets_a_requirement`
failure: `tests.foundations.test_v2_credibility_vector::test_a_contradiction_of_the_subject_or_its_lineage_is_a_defeater_in_any_child_order`
failure: `tests.foundations.test_v2_credibility_vector::test_a_cited_contradicted_record_defeats_even_when_it_did_not_win_its_factor`
failure: `tests.foundations.test_v2_credibility_vector::test_supersession_only_lowers_whatever_the_superseder_s_pin_or_standing`
failure: `tests.foundations.test_v2_credibility_vector::test_applicability_and_uq_are_backed_by_existing_records_not_labels`
failure: `tests.foundations.test_v2_credibility_vector::test_citing_an_outside_domain_record_twice_does_not_cancel_it`
failure: `tests.foundations.test_v2_credibility_vector::test_an_envelope_for_another_statement_of_the_claim_supplies_nothing`
failure: `tests.foundations.test_v2_credibility_vector::test_the_calibration_guard_follows_duplicate_content_and_lineage`
failure: `tests.foundations.test_v2_credibility_vector::test_refused_records_leave_a_note_and_falsified_envelopes_of_other_claims_are_not_defeaters`
failure: `tests.foundations.test_v2_credibility_vector::test_an_outside_domain_finding_is_judged_like_a_defeater`
failure: `tests.foundations.test_v2_credibility_vector::test_contradicted_calibration_data_defeats_and_nothing_is_dropped_silently`
failure: `tests.foundations.test_v2_credibility_vector::test_a_same_content_twin_does_not_escape_contradiction_or_supersession`
failure: `tests.foundations.test_v2_credibility_vector::test_the_report_binds_its_inputs_and_attested_negative_reports_count_on_their_subject`
failure: `tests.foundations.test_v2_credibility_vector::test_test_mode_never_meets_a_decision_requirement`
failure: `tests.foundations.test_v2_credibility_vector::test_an_unknown_check_caps_applicability_and_an_outside_report_sets_the_level`
failure: `tests.foundations.test_v2_credibility_vector::test_any_supersession_disqualifies_support_and_an_obsolete_subject_is_defeated`
failure: `tests.foundations.test_v2_credibility_vector::test_an_incoherent_envelope_backs_nothing`
failure: `tests.foundations.test_v2_credibility_vector::test_an_obsolete_subject_is_defeated_whatever_else_links_it_to_its_replacement`
failure: `tests.foundations.test_v2_credibility_vector::test_or_never_meets_a_requirement_because_a_branch_lost_evidence`
failure: `tests.foundations.test_v2_credibility_vector::test_independence_follows_shared_calibration_and_same_content_ancestry`
failure: `tests.foundations.test_v2_credibility_vector::test_the_calibration_guard_compares_the_validator_with_every_calibration_input`
failure: `tests.foundations.test_v2_credibility_vector::test_a_model_never_declares_its_own_model_form_discrepancy`
failure: `tests.foundations.test_v2_credibility_vector::test_a_contradiction_is_a_conflict_whichever_side_wrote_it`
failure: `tests.foundations.test_v2_credibility_vector::test_fourth_review_lows`
failure: `tests.foundations.test_v2_credibility_vector::test_a_contradiction_inside_the_closure_needs_only_one_admissible_end`
failure: `tests.foundations.test_v2_credibility_vector::test_a_contradicted_twin_disqualifies_a_closing_superseder`
failure: `tests.foundations.test_v2_credibility_vector::test_a_closing_version_must_be_other_content_and_not_itself_obsolete`
failure: `tests.foundations.test_v2_credibility_vector::test_an_explicit_defeater_may_add_but_never_replace_a_computed_one`
failure: `tests.foundations.test_v2_credibility_vector::test_the_claim_s_own_records_never_close_its_defeaters`
failure: `tests.test_core_certificate::test_the_certificate_describes_this_tree`
failure: `tests.claims.test_claims_assessment::test_the_mcp_tool_returns_the_same_record`
failure: `tests.foundations.test_authority_integrity::test_the_issuer_bound_path_admits_a_correctly_attested_record_and_nothing_else`
failure: `tests.foundations.test_authority_integrity::test_an_unopened_unanchored_or_foreign_ledger_is_refused`
failure: `tests.foundations.test_authority_integrity::test_forged_and_unknown_issuers_never_reach_the_ledger`
failure: `tests.foundations.test_authority_integrity::test_a_key_is_registered_only_by_its_holder_in_its_providers_class`
failure: `tests.foundations.test_authority_integrity::test_wrong_role_wrong_result_wrong_receipt_and_wrong_context_are_refused`
failure: `tests.foundations.test_authority_integrity::test_self_issued_support_is_refused_from_any_executor_of_the_receipt`
failure: `tests.foundations.test_authority_integrity::test_negative_records_cap_and_defeat_even_from_the_results_own_executor`
failure: `tests.foundations.test_authority_integrity::test_an_attested_falsification_follows_the_result_not_the_node_name`
failure: `tests.foundations.test_authority_integrity::test_attested_records_cannot_be_edited_in_memory`
failure: `tests.foundations.test_authority_integrity::test_revocation_rotation_and_history`
failure: `tests.foundations.test_authority_integrity::test_persistence_restart_and_tamper_detection`
failure: `tests.foundations.test_authority_integrity::test_a_second_writer_or_a_failed_append_never_forks_the_ledger`
failure: `tests.foundations.test_authority_integrity::test_negative_records_are_read_from_the_ledger_whatever_the_caller_supplies`
failure: `tests.foundations.test_authority_integrity::test_a_copied_record_or_a_mutated_result_backs_nothing`
failure: `tests.foundations.test_authority_integrity::test_key_material_placement`
failure: `tests.foundations.test_authority_integrity::test_an_attested_failed_check_without_a_level_caps_its_roles_factors`
failure: `tests.foundations.test_authority_integrity::test_an_attested_negative_report_counts_on_its_attested_subject_whatever_digest_it_carries`
failure: `tests.foundations.test_authority_integrity::test_a_ledger_subclass_is_refused`
failure: `tests.foundations.test_authority_integrity::test_residual_the_anchor_is_the_trust_root_so_it_never_comes_from_the_call_path`
failure: `tests.foundations.test_authority_integrity::test_a_minted_signer_cannot_be_relabelled`
failure: `tests.foundations.test_authority_integrity::test_a_compromise_window_withdraws_what_the_key_signed_in_it`
failure: `tests.foundations.test_authority_integrity::test_an_issuer_that_produced_the_same_output_elsewhere_is_self_issued`
failure: `tests.foundations.test_authority_integrity::test_an_attestation_subject_output_is_a_string`
failure: `tests.foundations.test_authority_integrity::test_a_retired_key_can_still_be_declared_compromised`
failure: `tests.foundations.test_authority_integrity::test_a_later_narrower_window_never_narrows_a_declared_compromise`
failure: `tests.test_core_freeze_manifest::test_the_command_line_verifier_agrees_with_the_function`
failure: `tests.test_core_freeze_manifest::test_a_descendant_that_keeps_the_contract_still_verifies`
failure: `tests.claims.test_preregistration_exposure::test_frozen_revisions_chain_and_ignore_other_issuers`
failure: `tests.claims.test_preregistration_exposure::test_the_gate_refuses_confirmatory_data_until_frozen_approved_and_sealed`
failure: `tests.claims.test_preregistration_exposure::test_an_owner_who_also_operates_or_was_revoked_does_not_count`
failure: `tests.claims.test_preregistration_exposure::test_a_row_is_released_only_if_it_matches_its_manifest_commitment`
failure: `tests.claims.test_preregistration_exposure::test_a_second_manifest_cannot_repartition_a_registered_row`
failure: `tests.claims.test_preregistration_exposure::test_the_gate_and_the_verifier_read_the_campaigns_own_issuer`
failure: `tests.claims.test_preregistration_exposure::test_releasing_around_the_gate_is_detected_whatever_the_label`
failure: `tests.claims.test_preregistration_exposure::test_the_gate_conditions_are_re_derived_at_the_first_confirmatory_release`
failure: `tests.claims.test_preregistration_exposure::test_revising_or_sealing_after_exposure_makes_the_campaign_exploratory`
failure: `tests.claims.test_preregistration_exposure::test_the_confirmatory_query_budget_and_multiplicity_come_from_the_journal`
failure: `tests.claims.test_preregistration_exposure::test_an_untestable_declaration_is_an_abstention_not_a_drop`
failure: `tests.claims.test_preregistration_exposure::test_untestable_is_not_a_choice_under_a_machine_readable_rule`
failure: `tests.claims.test_preregistration_exposure::test_verify_passport_re_derives_every_field_counts_as_discovery_trusts`
failure: `tests.claims.test_preregistration_exposure::test_a_released_value_is_re_checked_against_its_commitment_from_the_journal`
failure: `tests.claims.test_preregistration_exposure::test_counts_without_n_and_compromised_or_foreign_records_are_not_trusted`
failure: `tests.claims.test_preregistration_exposure::test_under_a_machine_readable_rule_a_seal_names_its_fit`
failure: `tests.claims.test_preregistration_exposure::test_a_survived_envelope_never_hides_another_attested_attack_on_the_same_claim`
failure: `tests.claims.test_preregistration_exposure::test_an_operator_role_falsification_is_counted_and_the_plan_is_bound`
failure: `tests.claims.test_preregistration_exposure::test_a_pre_registration_without_a_plan_digest_never_verifies_an_attack`
failure: `tests.foundations.test_escrow_boundary::test_budgets_submissions_and_query_ids_survive_an_escrow_restart`
failure: `tests.foundations.test_escrow_boundary::test_a_tampered_journal_refuses_to_start_and_a_truncated_one_is_caught_by_the_client`
failure: `tests.foundations.test_escrow_boundary::test_requests_are_capability_bound_and_never_carry_the_credential`
failure: `tests.foundations.test_escrow_boundary::test_responses_are_signed_and_bound_to_their_request`
failure: `tests.foundations.test_escrow_boundary::test_storage_is_private_and_outside_the_repository`
failure: `tests.foundations.test_escrow_boundary::test_the_subprocess_escrow_resumes_its_journal_but_stays_unproven`
failure: `tests.foundations.test_escrow_boundary::test_a_rolled_back_or_restored_journal_is_caught_by_a_durable_client_checkpoint`
failure: `tests.foundations.test_escrow_boundary::test_a_replaced_history_at_the_same_length_is_refused`
failure: `tests.foundations.test_escrow_boundary::test_a_deleted_journal_refuses_to_start`
failure: `tests.foundations.test_escrow_boundary::test_noise_after_a_rollback_is_not_reproduced_for_another_request`
failure: `tests.foundations.test_escrow_boundary::test_a_replaced_universe_refuses_to_start`
failure: `tests.foundations.test_escrow_boundary::test_unauthenticated_requests_never_touch_a_campaign`
failure: `tests.foundations.test_escrow_boundary::test_a_log_read_is_single_use_across_restarts`
failure: `tests.foundations.test_escrow_boundary::test_clients_always_pin_the_escrow_key_and_integrity_is_not_a_refusal`
failure: `tests.foundations.test_escrow_boundary::test_the_escrow_never_asserts_a_verified_boundary_and_query_keys_are_unambiguous`
failure: `tests.test_core_api_snapshot::test_the_snapshot_is_byte_identical_across_fresh_processes`
failure: `tests.foundations.test_v2_blindfold::test_the_observe_client_api_sends_only_observe_and_every_query_is_logged`
failure: `tests.foundations.test_v2_blindfold::test_budget_mix_bounds_and_malformed_requests_are_refused_not_fatal`
failure: `tests.foundations.test_v2_blindfold::test_indistinguishable_cannot_be_shotgunned_or_duplicated`
failure: `tests.foundations.test_v2_blindfold::test_an_inadmissible_proposal_is_kept_and_costs_credit_never_a_refusal`
failure: `tests.foundations.test_v2_blindfold::test_credit_is_reported_over_the_best_constant_answer`
failure: `tests.foundations.test_v2_blindfold::test_replay_is_complete_identity_bound_and_never_calls_the_proposer`
failure: `tests.foundations.test_v2_blindfold::test_the_subprocess_escrow_keeps_its_secrets_in_the_child`
failure: `tests.test_core_scientific_audit_batch56::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see`
failure: `tests.test_mutation_startup::test_environment_snapshot_is_independent_of_parent_and_each_child`
failure: `tests.test_mutation_startup::test_interpreter_replacement_is_refused_with_same_size`
failure: `tests.test_mutation_startup::test_venv_interpreter_symlink_spelling_is_preserved`
failure: `tests.test_core_freeze_v4_manifest::test_the_tree_keeps_the_core_freeze_v4_contract`
failure: `tests.test_core_freeze_v4_manifest::test_once_assured_the_full_verification_holds`
failure: `tests.test_core_api_contracts::test_the_frozen_digest_is_identical_in_fresh_processes`
failure: `tests.test_core_freeze_v4_manifest::test_the_deep_surface_carries_methods_and_member_positions`
failure: `tests.test_core_freeze_v3_manifest::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree`
failure: `tests.foundations.test_authority_durable_campaign::test_a_campaign_resumes_exactly_after_restart`
failure: `tests.foundations.test_authority_durable_campaign::test_restart_detects_dropped_reordered_or_rewritten_operations`
failure: `tests.foundations.test_authority_durable_campaign::test_another_key_or_issuer_cannot_resume_or_extend_the_campaign`
failure: `tests.foundations.test_authority_durable_campaign::test_a_mutation_around_the_journal_is_refused_not_lost`
failure: `tests.foundations.test_authority_durable_campaign::test_a_verdict_judged_before_restart_is_the_same_verdict_after`
failure: `tests.foundations.test_authority_durable_campaign::test_the_same_campaign_id_cannot_restart_its_multiplicity_count`
failure: `tests.foundations.test_authority_durable_campaign::test_foreign_journal_entries_cannot_squat_or_brick_a_campaign`
failure: `tests.foundations.test_authority_durable_campaign::test_a_dropped_journal_tail_after_the_operators_anchor_is_refused`
failure: `tests.foundations.test_authority_durable_campaign::test_a_second_exposure_issuer_cannot_fork_or_squat_the_campaign`
failure: `tests.foundations.test_authority_durable_campaign::test_a_journal_signed_in_a_compromise_window_cannot_be_resumed`
failure: `flagships.tests.test_battery_blind_readiness::test_the_dry_run_walks_the_whole_chain_without_claiming_anything`
failure: `flagships.tests.test_battery_blind_readiness::test_the_dry_run_records_every_abstention_with_its_rule_inputs`
failure: `tests.test_core_scientific_audit_batch24::test_r39_the_word_says_that_agreement_between_solvers_is_one_of_the_things_it_covers`
failure: `tests.domains.test_audit_domains_unscreened_claims::test_the_held_resistance_limitation_is_stated_where_a_caller_reads`
failure: `providers.cantera.tests.test_cantera_provider::test_proof_b_adiabatic_equilibrium_with_mechanism_bytes_bound`
failure: `providers.cantera.tests.test_cantera_provider::test_proof_b_transient_constant_pressure_reactor_on_a_big2_window`
failure: `tests.foundations.test_escrow_isolation::test_the_isolated_deployment_reports_exactly_what_it_established`
failure: `tests.foundations.test_escrow_isolation::test_the_leak_detector_catches_a_planted_partial_copy`
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "pytest", "-m", "not expensive", "-q", "-n", "4", "--dist", "loadfile", "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "--junitxml", "D:\\forge-final-assurance-evidence\\baselinewin-fast.xml"]`
result: exit 15; wall 510.82 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "tools.certification.assert_clean_tree"]`
result: exit 0; wall 1.37 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "tools.certification.core_certificate", "--verify"]`
result: exit 1; wall 1.32 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "tools.certification.core_freeze_v4", "--verify"]`
result: exit 1; wall 1.35 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "tools/forge_check.py", "--regression"]`
result: exit 1; wall 15.34 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "pytest", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "-q", "--junitxml", "D:\\forge-final-assurance-evidence\\win-dependency-guard.xml"]`
result: exit 0; wall 24.36 s; counts {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "pytest", "-m", "not expensive", "-q", "-n", "4", "--dist", "loadfile", "--deselect", "tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared", "--junitxml", "D:\\forge-final-assurance-evidence\\win-fast.xml"]`
result: exit 3; wall 1.35 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "pytest", "-q", "-n", "8", "--dist", "loadfile", "--junitxml", "D:\\forge-final-assurance-evidence\\win-full.xml"]`
result: exit 3; wall 1.35 s; counts null; tracked byte drift 0; git status ''
command argv: `["C:\\Users\\dev_kaeem\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe", "-m", "tools.certification.assert_clean_tree"]`
result: exit 0; wall 1.37 s; counts null; tracked byte drift 0; git status ''

Regression pack: corrected primary 3.14 run 256 passed; isolated 3.12 run 256 passed. Supported FAST (both versions): 10026 passed, 2 failed, 157 skipped; SCIENTIFIC: 10599 passed, same 2 failed, 157 skipped; FULL: 10607 passed, 4 failed, 157 skipped. Dependency guards: PASS. Failure classifications and Windows limitations are in the closeout report; unsupported primary Windows failures are not asserted a product regression. Baseline scanner tests ran on clean 9ca337f9, 3.11 and 3.12: both FAIL the same named test. Windows same-environment baseline FAST and direct Cantera diagnostics: INCOMPLETE, stopped; NOT accepted as a baseline proof.

command: `.forge/venvs/3.12/bin/python -m tools.certification.local_assurance run --repository sharq-labs/forge`
result: REFUSED, exit 1, fast311: 10005 passed, 1 failed (tests/test_change_impact.py::test_the_old_gap_a_domain_models_own_tests_are_now_selected), 157 skipped. No certificate written; later owner gates and certificate-child verify NOT RUN. Failure receipt SHA256 a1965de5a5495082706237ba7c5c6c4e251fffff812ab92286b6cf272ecde488.

Post-attempt commands: `.forge/venvs/3.12/bin/python -m tools.certification.core_certificate --verify` FAIL; `.forge/venvs/3.12/bin/python -m tools.certification.core_freeze_v4 --verify` FAIL only certificate.verifies; `.forge/venvs/3.12/bin/python tools/forge_check.py --regression` PASS 256 in 7.40s; `.forge/venvs/3.12/bin/python -m tools.certification.assert_clean_tree` PASS. Certificate unchanged: c22a012147c26183031b32b0e016c80ef86218ef3cd1664361be47d4cf2f186b, still names 39d43456cab918ed0748efe7f5b0ff5781474ffa.

Failed approaches: Linux Git rejected Windows absolute worktree .git pointer; use a Linux-created worktree. Initial pytest temp permission error and misparsed backslash basetemp: use forward slashes in an external basetemp. Untracked temp folder moved intact after automatic deletion rejection; tracked drift zero. Owner run needs explicit --repository for this local clone. Windows FULL stalled at79%, empty XML; controller had no workers. No final count or pass claimed. All test trees clean before documentation. No scientific implementation or frozen artifacts changed.

command: git diff --check
result: PASS, exit 0, executed before documentation commit; no whitespace errors.
Final additional Linux all-file hash replay: INCOMPLETE (new WSL invocation stalled and was stopped); prior per-tier 5514-file snapshots and post-owner assert_clean_tree remain the recorded integrity proofs. Windows final all-file hash replay: PASS, 5514 tracked files, drift0.


## 2026-10-13 Owner-requested scientific boundary repairs

Base `origin/main` `c4e05ee6`; isolated worktree, branch
`codex/repair-scientific-boundaries`. The shared checkout and its existing edits
are preserved. Scope: empty UQ budgets, discovery timeout, benchmark output
isolation, challenge summary, and unassessable applicability compilation.

Compatibility decision: keep frozen Core signatures, record field names, schema
strings and valid-budget serialization unchanged. Empty or missing budget
components are refused rather than interpreted as zero. The non-Core challenge
summary gains `inconclusive_attempted_challenges`; its existing digest formula
stays unchanged, but corrected summaries intentionally change the digest. Existing
historical records are not rewritten. The non-Core compiler gains an explicit
applicability gap and refuses readiness on evaluator failure.

Failed environment approaches: forge-runner WSL cannot start because its D:
virtual disk is unavailable. A venv under /tmp disappeared between WSL starts;
retry under the persistent Ubuntu user home succeeded (Python 3.12.3). Initial
forge_check launch did not execute tests because the /tmp interpreter was missing.
Tests: NOT RUN at the environment-preparation checkpoint; results appended below.

2026-10-13 — initial adversarial tests (Ubuntu Python 3.12.3; mounted Windows source)
command: `/home/dev_kaeem/forge-repair-venv/bin/python -m pytest -q tests/uq/budget tests/claims/test_challenge_summary.py tests/claims/test_unassessable_compilation.py tests/foundations/test_discovery_deadline.py --tb=short`
result: FAIL — 30 passed, 1 failed in 13.21 s.
failure: `test_timeout_covers_handshake_output_and_inherited_pipes` (leader exits, descendant pipes).
Cause: test expected a killed orphan's process group to disappear immediately; a zombie may persist until init reaps it. Corrected the assertion to reject any live member; no deadline or production behavior relaxed.

command: `/home/dev_kaeem/forge-repair-venv/bin/python tools/forge_check.py --changed --workers 4` (mounted Windows worktree)
result: BLOCKED — no tests executed; Linux git cannot resolve the Windows .git worktree path.
Correction: created a task-owned native Linux Git clone at `/home/dev_kaeem/forge-repair-src`, pinned at c4e05ee6, and copied only the repair changes with Git-normalized LF bytes. Python environment installed against that clone. Native checkout has its own Git identities and Linux-supported execution.

command: `/home/dev_kaeem/forge-repair-venv/bin/python tools/forge_check.py --changed --workers 4` (native Linux clone)
result: FAIL — 3889 passed, 59 skipped, 2 failed in 73.37 s.
failures: `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`; `tests/claims/test_sensitivity_robustness_challenge.py::test_a_claim_that_holds_across_its_declared_range_survives`.
Certificate failure names the pre-existing certified-area drift plus changed UQ/harness bytes and the uncommitted tree; no certificate regenerated. Challenge failure was an obsolete expected summary: real surviving range probes coexist with another INCONCLUSIVE challenge. Updated the test to assert both surviving routes and an honest overall inconclusive status; this is the requested behavior correction.

Independent read-only forge-scientific-review: PASS. Initial request for task-write/final-wait stall tests addressed; reviewer inspected them. No tests executed by reviewer, no scientific validation claimed. Pre-existing direct UncertaintyBudgetReport dataclass construction can carry arbitrary fields; no authority consumer found by reviewer, recorded as scope limitation. Aggregation/build/loading paths are hardened.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python -m pytest -q tests/uq/budget tests/claims/test_challenge_summary.py tests/claims/test_unassessable_compilation.py tests/claims/test_sensitivity_robustness_challenge.py tests/foundations/test_discovery_deadline.py tests/test_benchmark_output_isolation.py --tb=short` (native Linux clone)
result: PASS — 60 passed in 40.20 s.
Published benchmark JSON/Markdown bytes were compared before and after both builds by the isolation tests. Mutating/deleting the private generated result was detected instead of reading a published fallback. These are software tests, not physical validation.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python tools/forge_check.py --regression --workers 4` (native Linux clone)
result: PASS — 241 passed in 6.07 s.

command: `python3 .pytest-review-temp/compare_api.py` (WSL Ubuntu; script invokes `/home/dev_kaeem/forge-repair-venv/bin/python -X utf8 -m engcore.api_snapshot --frozen` with each checkout's own src on PYTHONPATH)
result: PASS — base c4e05ee6 and repair frozen API output bytes identical; SHA256 `0cfcaca6290cfe910e13d851986b62bbe55ae732a2e7a9f43174c5a319916072`.
This comparison establishes unchanged frozen API shape, not certificate validity.


Latest-main steering checkpoint: user requested a fresh check. Fetched `origin/main`
`5d73e8f5` (PRs #133–#135). Updated repair branch by fast-forward; upstream
benchmark isolation and additive challenge outcome_summary supersede the overlapping
local changes, which remain recoverable in the repair stash. Kept only empty-budget,
NOT_ASSESSABLE compiler and Discovery read-deadline repairs plus their tests.
The 60-test result and 241-test regression above describe the previous c4e05ee6
base, not this new base. Prior FAST run was interrupted before a result/XML was
available (lost exec session, partial log at 97%); result BLOCKED, never PASS.
New-baseline gates and scientific review follow below.

2026-10-13 — updated-main gate (`5d73e8f5` base)
command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python tools/forge_check.py --changed --workers 4`
result: FAIL — 3940 passed, 61 skipped, 1 failed in 44.50 s.
failure: `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`.
The remaining defect tests pass; certificate verification still reports certified-area byte drift, including the explicit UQ repair and earlier main changes. Not recertified, not accepted as a clean integration gate.
Independent read-only review of the updated-base, narrowed diff: PASS. No outstanding finding; review did not execute tests or establish physical validation.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python tools/forge_check.py --regression --workers 4` (updated base 5d73e8f5)
result: PASS — 256 passed in 5.22 s.

command: `wsl -d Ubuntu -- python3 /mnt/c/Users/dev_kaeem/.codex/worktrees/repair-scientific-boundaries/phyx/.pytest-review-temp/compare_latest_api.py`
result: PASS — latest base 5d73e8f5 and repair frozen API output bytes identical; SHA256 `0cfcaca6290cfe910e13d851986b62bbe55ae732a2e7a9f43174c5a319916072`.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python -m pytest -m "not expensive" -q -n 4 --tb=short --junitxml=/home/dev_kaeem/forge-repair-latest-fast.xml`
result: FAIL — 10041 passed, 157 skipped, 7 failed in 117.32 s.
Raw log and XML are in the task-owned Ubuntu user home. Failure names and base attribution appended after SCIENTIFIC completes; no result waived or certificate rewritten.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python -m pytest -m "not campaign" -q -n 4 --tb=short --junitxml=/home/dev_kaeem/forge-repair-latest-scientific.xml`
result: FAIL — 10617 passed, 157 skipped, 9 failed in 209.85 s.
Failure names (FAST plus SCIENTIFIC union):
- benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates
- benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates
- tests/test_core_certificate.py::test_the_certificate_describes_this_tree
- tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1
- tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies
- tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks
- tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree
- tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract
- tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds
Attribution run on pristine base 5d73e8f5 is underway. Dirty-tree failures are not called scientific regressions without this comparison; source/evidence replay remains bound to its actual checkout.

command: `CRAFTY_NGSPICE_ARGV=ngspice PYTHONPATH=/home/dev_kaeem/forge-repair-latest-base/src:/home/dev_kaeem/forge-repair-latest-base /home/dev_kaeem/forge-repair-venv/bin/python -m pytest -q -n 4 --tb=short --junitxml=/home/dev_kaeem/forge-repair-base-attribution.xml <the nine failure node IDs listed above>`
result: FAIL — 3 failed, 6 passed in 26.35 s on pristine 5d73e8f5.
Base failures: certificate_describes_this_tree and both historical benchmark rebuild tests. The six freeze tests pass on the clean base and reject the uncommitted repair tree specifically at tree.clean; a committed repair rerun will determine their status. No scientific regression was inferred from those dirty-tree failures; no gate was waived.

Exact base-attribution subprocess command (cwd `/home/dev_kaeem/forge-repair-latest-base`; PYTHONPATH set to that checkout src/root; CRAFTY_NGSPICE_ARGV=ngspice):
`/home/dev_kaeem/forge-repair-venv/bin/python -m pytest -q -n 4 --tb=short --junitxml=/home/dev_kaeem/forge-repair-base-attribution.xml benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates tests/test_core_certificate.py::test_the_certificate_describes_this_tree tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1 tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract`


## 2026-10-13 Final committed repair gates

Implementation commit: `cf0f31f1a0718b3921dc47e0bae71ea19bf39554`, base `5d73e8f5`.
Ubuntu / Python 3.12.3; all commands below ran sequentially against the clean,
Git-native clone of that exact implementation commit. No source change since the
independent latest-base review PASS. Valid frozen API output remains byte-identical
to base. Hardened recertification: NOT RUN (OD-3, owner-run).

Failed transport approach: fetching the implementation commit through the Windows
managed worktree path failed because Linux Git cannot resolve its Windows .git
pointer. The mistakenly started base-only runner was stopped and its partial
results were not used. Fetching the branch through the primary repository's .git
worked. The final runner asserts the exact HEAD and a clean tree before any test.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python tools/forge_check.py --regression --workers 4`
result: PASS — 256 passed in 5.19 s.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python -m pytest -m "not expensive" -q -n 4 --tb=short --junitxml=/home/dev_kaeem/forge-repair-latest-fast.xml`
result: FAIL — 10047 passed, 157 skipped, 1 failed in 119.30 s.
failure: `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`.

command: `CRAFTY_NGSPICE_ARGV=ngspice /home/dev_kaeem/forge-repair-venv/bin/python -m pytest -m "not campaign" -q -n 4 --tb=short --junitxml=/home/dev_kaeem/forge-repair-latest-scientific.xml`
result: FAIL — 10623 passed, 157 skipped, 3 failed in 204.95 s.
failures: certificate_describes_this_tree and both historical benchmark rebuild
nodes listed above. All three also fail on pristine 5d73e8f5; XML failure-ID union
comparison matched exactly. The six freeze checks that rejected the dirty tree
pass on the committed repair. No certificate, threshold, skip rule, reference
artifact or published negative result was rewritten to clear a gate.

command: `wsl -d Ubuntu -- python3 /mnt/c/Users/dev_kaeem/.codex/worktrees/repair-scientific-boundaries/phyx/.pytest-review-temp/compare_final_failures.py`
result: PASS — final FAST/SCIENTIFIC failure union equals the three failures from
the pristine-main attribution run. This is failure attribution, not a passing tier.

command: `/home/dev_kaeem/forge-repair-venv/bin/python -m tools.certification.assert_clean_tree`
result: PASS — `/home/dev_kaeem/forge-repair-src` byte-identical to HEAD after all tiers.

Outcome: the remaining three requested code repairs are implemented and reviewed;
latest-main benchmark and additive challenge-summary repairs are preserved.
Integration remains blocked by the actual red gates / certificate drift; no
G0 PASS, certification, qualification or physical validation is claimed.

## 2026-10-12 A1.5 manufacturer-rating applicability

- Added `engcore.scientific.knowledge.operating_rating` on HEAD `8b028dcf`. No Mind, no catalog search, no multirotor redesign.
- `python -m pytest tests/scientific/knowledge/test_operating_rating.py -q --tb=line` -> 15 passed in 4.61s. Python 3.11.17, venv `/home/dev_kaeem/forge-g0-repair-venv`.
- Seal rerun of the same command -> 15 passed in 4.41s.
- `python tools/forge_check.py --regression` -> 225 passed in 75.73s. No digest or certificate mismatch was reported by this gate. Pins were not republished.
- Frozen packet `a1-packet-c.json` SHA-256 remained `e1df8cefcf1ae85e7633aca6db084b635b9ffa6703363b593e64dc766db0ac30` before and after the seal rerun. Mission status `insufficient_evidence`. Component statuses: kde-4012, tmotor-mn4010-kv370, and mad-5008-400-eee `outside_duration_envelope`; mad-5010-240-eee `operating_point_not_established`. Not a physical-infeasibility claim.
- FAST / recertification: NOT RUN.

## 2026-10-12 A2 minimal next-action mind

- Substrate commit `67c6971113b88b2cdab953d8073406a746f472e7` on `feat/a1-5-operating-rating`. The Mind is uncommitted. It does not issue scientific verdicts.
- `python -m pytest tests/mind/test_transition.py -q --tb=line` -> 18 passed in 1.93s, and the seal rerun -> 18 passed in 2.02s. Python 3.11.17, venv `/home/dev_kaeem/forge-g0-repair-venv`.
- First `python tools/forge_check.py --regression` -> 1 failed, 224 passed in 80.64s. Failure: `tests/test_core_api_layering.py::test_every_package_under_engcore_is_classified_core_or_not`. `engcore.mind` was an unclassified package. It was recorded as non-Core because it issues no verdict. No digest or certificate was republished.
- Second `python tools/forge_check.py --regression` -> 225 passed in 72.20s.
- Frozen packets, scored after the review fixes: `a2-packet-1.json` `84baec613011f0063bed5a01500d9fcfb17df7b5f0aae314af38c1f908e6ad2b`; `a2-packet-2.json` `647d8a2232dca74df3277ada12a4da3086190d98fc910e2869d2b08bafffe8cb`; `a2-packet-3.json` `7a0c455fe88d82423179901aa920e5913e39bb11b539755f517a470ee583a352`. Bytes matched before and after scoring.
- Selected actions: `request-operating-point`, `check-identifiability`, `stop`. Score 15/15 on the A2 denominator. Unsupported scientific claims 0. Authority override attempts 0. LLM calls 0. Scientific capability calls 0.
- Belief revision after an operating-point availability observation: that dependency blocked, duration support and the three short-duration refusals unchanged, mission unresolved, next action `stop`.
- Scientific review of the Mind: CHANGES REQUIRED, then PASS after the five corrections. A PASS is a review result only. Recertification: NOT RUN.


## 2026-10-14 — BR-15 authority boundary & certification closure

Branch `fix/br15-authority-closure` (worktree `D:/forge-br15`; WSL clone `~/forge-br15`), base `origin/main`
`e193e573`. Commits: `dc26175d` (red reproducer), `6d62e5cf` (closure fix), `a49e8d12` (harness fix), `01073787`
(review LOWs) and `a22869d4` (recertification-scope test example). Not pushed. Report:
[BR15_AUTHORITY_CLOSURE.md](BR15_AUTHORITY_CLOSURE.md). Outcome: **PARTIALLY_CLOSED**, blocked on owner
recertification (OD-3) and on GitHub governance.

Post-merge truth:
- `core_certificate.py --verify` on `e193e573` FAILED: `tests/mutation_guards.py` and `tests/test_formal_xdist.py`
  were changed by PR #142 after certificate child `b1eea81b`.
- The PR #140 merge `623149f3` changed only docs and the certificate.
- CI on `main`: FAST 3.11/3.12 and SCIENTIFIC each failed one test, `test_the_certificate_describes_this_tree`.
  `reproduce` failed: the image has no `.git` and runs as root.
- Recertify on PR #140 and #142: all 8 `v4_mutations` shards failed, because `actions/checkout` writes
  `.git/config.worktree` and workspace admission refuses it.

Reproducers (before the fix):
- `pytest tests/test_certified_dependency_closure.py` against the `e193e573` verifier: 23 failed, 2 passed. The two
  that passed are the controls.
- At `dc26175d`: 14 failed, 2 passed.

After the fix:

| Run | Command | Result |
|---|---|---|
| Windows 3.14, serial | `pytest tests/test_certified_dependency_closure.py tests/test_certificate_verdict_scope.py tests/test_core_certificate.py` | 90 passed, 1 skipped, 1 failed (`test_the_certificate_describes_this_tree`, expected) |
| Windows | `tests/test_recertification_scope.py` | 115 passed |
| Windows | real tree | `certified_dependency_problems == []`, `authority_closure_problems == []` |
| Windows | production registry pin | unchanged (456 `evidence_code` files, equal digests, `registry_problems == []`) |
| WSL 3.12, FAST (`pytest -m "not expensive" -n 4`), base `e193e573` | | 10374 passed, 156 skipped, 1 failed (`test_the_certificate_describes_this_tree`) |
| WSL 3.12, FAST, fix `a22869d4` | | 10415 passed, 156 skipped, 1 failed (same test) |
| WSL 3.11, FAST, fix `a22869d4` | | 10415 passed, 156 skipped, 1 failed (same test) |
| WSL 3.12, impact selection (31 modules) at `a49e8d12` | | 926 passed, 2 failed: the certificate test, plus `test_recertification_scope.py::test_non_core_paths_stay_ordinary[src/engcore/sria/decision/utility.py]` (a real consequence of pinning sria/decision; fixed in `a22869d4`) |
| WSL 3.12, impact selection at `a22869d4` | | 940 passed, 1 skipped, 1 failed (the certificate test) |
| WSL 3.12, regression at `a22869d4` | `python tools/forge_check.py --regression` | 256 passed, exit 0 |

Hardened recertification, `local_assurance`, Formal and V4 mutation populations: **NOT RUN** (owner-run, OD-3).

Independent review (forge-scientific-reviewer, static):
- First pass: CHANGES REQUIRED. I-1 (package-wide exclusions) and I-2 (false multiscale and providers reasons) were
  HIGH; I-3 and I-4 MEDIUM; I-5 and I-6 LOW. All were fixed.
- Confirmation pass: ACCEPT, no BLOCKER or HIGH. Two of its LOWs were fixed. The LOW about `api_snapshot.py` being a
  non-seed pinned file was recorded as a residual.

Failed approaches, so they are not repeated:
- A first fix declared `providers/**` and `multiscale/**` as non-authoritative. The reasons were false: the system
  runtime commits multiscale state uncertainty and consumes provider records. Both were pinned instead.
- Package-wide exclusions were replaced by importer edges.
- The Windows `-n 4` runs of the certificate fixtures fail on `git add -A` (exit 128) on the base as well. It is an
  environment problem; run those serially on Windows.
## 2026-10-14 — BR-16 Genesis-lite v0: preregistered benchmark layer and Tier-1 pilot

Branch `feat/br16-genesis-lite-benchmark` (worktree `D:/forge-br16`, WSL clone `~/forge-br16`), base `origin/main`
`e193e573`. Code commit `e493ff3f`. Not pushed. Report: [GENESIS_LITE_V0.md](../discovery/GENESIS_LITE_V0.md).
Outcome: **PILOT_COMPLETE · BLOCKED_OWNER_APPROVAL**, not GENESIS_A1_PASS. G0 has not exited, the preregistration is
frozen for the pilot only, the formal ≥20-seed runs have not started, and the budget and evaluator owner decisions are
open.

Scope:
- `benchmarks/genesis_lite/` reuses `engcore.blindfold` unchanged; `tests/genesis_lite/` adds 42 tests. A1
  preparation only.
- Certificate scope check: 0 of the 15 changed files are pinned. The new tests are recertification *triggers* under
  the conservative `tests/**` rule.

Gates:

| Run | Command | Result |
|---|---|---|
| Windows 3.14 | `pytest tests/genesis_lite -q` | 42 passed |
| WSL 3.12, FAST at `e493ff3f` | `pytest -m "not expensive" -n 4` | 10416 passed, 156 skipped, 1 failed (`test_core_certificate.py::test_the_certificate_describes_this_tree`); base `e193e573` had 10374 passed + the same single failure |
| WSL 3.12, regression | `python tools/forge_check.py --regression` | 256 passed, exit 0 |

Hardened recertification: **NOT RUN** (and not required by any certified-file change).

Pilot (WSL 3.12.3, 20 CPUs, preregistration `f99fcfbd…`, root commitment `07381465…`, now revealed):
- Command: `python -m benchmarks.genesis_lite.pilot --root-file <root> --out ~/br16-evidence/pilot`.
- Result: 960 runs, 0 invalid, 0 inadmissible, 85.07 s.
- The separate evaluator agreed with the escrow on all 5,760 universes.
- Run log sha256 `0c279655…`.
- Formal baseline tier: 15,120 runs ≈ 1,185 s (ESTIMATED).

Pilot findings (indicative; 10 worlds per cell):
- P-1: the floor arm `always_law` dominates the discoverable cell (0.70 vs 0.27 for the best competence arm). The
  formal lift rule needs the v0.1 amendment (OD-16).
- P-2: the no_solution and insufficient_evidence cells look REPRESENTATION_LIMITED, and the confounded cell is solved
  by a non-discoverer.
- P-3: only 0.70, 0.50 and 0.40 of the discoverable, spurious and confounded worlds are inside the searched family.
- P-4: only the pair heuristic reaches full credit on indistinguishable worlds (0.20).
- P-5: the textbook answer failed in every trap world.

Review (forge-scientific-reviewer, static):
- Round 1: CHANGES REQUIRED, with 5 HIGH: cross-run linkage; monomial-only search; straw-man cells; no strongest-arm
  or decision rule; pseudo-replication.
- Round 2: 1 HIGH (paired lift impossible under distinct roots; Holm family not fixed) and 5 LOW.
- All were fixed before the freeze.

Failed approaches, so they are not repeated:
1. Reusing escrow universe ids across presentations: a stateful proposer could merge budgets. Replaced by run-private
   pseudonyms.
2. Selecting the structure on the same hold-out the gate judges. Replaced by CV inside the training split.
3. One master root per (arm, seed, presentation). That breaks paired lift; roots are now shared across arms.
4. Long `python -c` strings with f-strings through bash. They were mangled; use script files.


## 2026-10-14 -- BR-17 Minimal Mind: start gate BLOCKED_BY_PREREQUISITE

The gate was checked against the live origin/main e193e573. All three prerequisites are unmet:
- A1 has not passed: BR-16 is PILOT_COMPLETE / BLOCKED_OWNER_APPROVAL, and G0 has not exited because the certificate
  fails on main.
- No baseline identity is frozen for A1: v0 is frozen for the pilot only, and P-1 needs v0.1.
- The active epic is still battery.thevenin_1rc, and no exception is open.

No Mind code was written; the active epic and the ledger were not touched. Record and loop owner map:
[BR17_MINIMAL_MIND_READINESS.md](../discovery/BR17_MINIMAL_MIND_READINESS.md). Tests: NOT RUN (documentation only).

## 2026-10-14 -- BR-18: BLOCKED_BY_PREREQUISITE

BR-17 has not passed (BLOCKED_BY_PREREQUISITE), and origin/main e193e573 has no Mind to evaluate. No BR-18 work was started. The verified-guard map is in [BR17_MINIMAL_MIND_READINESS.md](../discovery/BR17_MINIMAL_MIND_READINESS.md). Tests: NOT RUN (documentation only).


## 2026-10-14 -- G0/A1 unblocking sprint (integration/g0-a1-unblock, local only)

Integration branch `integration/g0-a1-unblock` (worktree `D:/forge-g0a1`) = `origin/main` `e193e573` + BR-15
(`9df87275`) + BR-16 (`0f69a453`). Report: [G0_A1_UNBLOCKING.md](G0_A1_UNBLOCKING.md). Nothing pushed or merged.
Hardened recertification and FULL local assurance: NOT RUN (owner, OD-3).

Fixed with reproducers that fail first:
- F-9: a restored campaign could carry a stop-review outcome different from the one in its own log.
  Fix: `stop_review_disagreements`, used in both runner restore and `IncrementalCheckpointStore.materialize`.
  Test: `tests/test_audit_sria_stop_review_restore.py`.
- F-7: the CI V4 shards refused the `config.worktree` that `actions/checkout` writes.
  Fix: a workflow step removes exactly the three sparse-checkout defaults. Test: `tests/test_ci_v4_checkout_admission.py`.
  Not yet observed on GitHub.
- Escrow leak: in-process heap-scan and stack-walk attacks stole hidden laws while the runs stayed VALID.
  Fix: `isolation="proposer_process"` (`benchmarks/genesis_lite/proposer_host.py`).
  Test: `tests/genesis_lite/test_genesis_lite_isolation.py`. Same-account boundary only: SECURITY_BOUNDARY_NOT_PROVEN; OD-20.
- Crafted setting name (`rolled back`) that turned a losing run INVALID: refused at the client; `lift_decision`
  refuses incomplete coverage.
- P-1: the root cause comes from the v0 run log (per-cell metric, gated arms over-refusing, mostly in-family worlds;
  neither leakage nor scoring). Fix: the v0.1 joint-credit contract in `benchmarks/genesis_lite/analysis.py`, identity
  `genesis_lite.blindfold_l5.v0_1`, preregistration `94efff08...`. v0 (`f99fcfbd...`) is preserved byte for byte.

Gates on `5ead8312` (WSL clone, Linux):
- `python -m pytest -m "not expensive" -q -n 4` (3.12): 10493 passed, 156 skipped, 1 failed:
  `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` (expected until OD-3).
- Same command, 3.11: 10493 passed, 156 skipped, 1 failed (same test).
- `python -m pytest tests/genesis_lite tests/test_audit_sria_stop_review_restore.py tests/test_ci_v4_checkout_admission.py tests/test_certified_dependency_closure.py -q`: 108 passed.
- `python tools/forge_check.py --regression`: 256 passed, exit 0.
- Certificate pre-checks: dependency, authority, harness and registry problems all `[]`.
  `--verify` reports only the expected drift.

v0.1 Tier-1 cost pilot, BR-16 `90a970cf`/`ed65ef3c`, WSL 3.12, `python -m benchmarks.genesis_lite.pilot`:
- 1,560 runs, 0 invalid, 0 inadmissible, 374.6 s (MEASURED). The `90a970cf` run had 384.95 s, before the
  summary-shadowing fix.
- Strongest baseline `space_filling` (+3.175); `always_law` last (-4.642).
- Formal ESTIMATE: 31,200 runs, about 6,451 s.

Gates on the final code HEAD `eb2720f9` (WSL clone, Linux; the next commit adds only this record):
- `python -m pytest -m "not expensive" -q -n 4` (3.12): 10493 passed, 156 skipped, 1 failed:
  `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` (expected until OD-3); 395.9 s.
- Same command, 3.11: 10493 passed, 156 skipped, 1 failed (same test); 327.0 s.
- Focused set (same command as above): 108 passed.
- `python tools/forge_check.py --regression`: 256 passed, exit 0.

Failed approaches, so they are not repeated:
1. `git stash` in a worktree applies another session's stash. Use `git show rev:path > path` for fail-before runs.
2. Pilot concurrent with a FAST run: contaminated timing; killed by PID and rerun alone.
3. Environment scan by broad patterns (`ROOT`): SYSTEMROOT false positive; narrowed.


## 2026-10-14 -- G0/A1 final closure (integration/g0-a1-unblock, local only)

Report: [G0_A1_FINAL_CLOSURE.md](G0_A1_FINAL_CLOSURE.md). OD-6 package:
[OD6_GENESIS_EPIC_MIGRATION_PACKAGE.md](OD6_GENESIS_EPIC_MIGRATION_PACKAGE.md). Nothing pushed or merged.
Hardened recertification, FULL local assurance and the formal campaign: NOT RUN (owner).

Fixed, each with a reproducer committed red first:
- BR-15 certificate (tool 2.6.0):
  - C1, C2 and C3: `bb4f08d9` (red), fixed in `aedc7b24` and `a87ab594`.
  - Nine further loader forms and planted bytecode: `912539ac` (red), fixed in `26f2505c`.
  - Private importlib API, symlinks, and the registry probe's pycache: fixed in `3c28bedf`.
  - Static loader completeness stays UNRESOLVED (declared).
- Genesis-lite v0.2 (`genesis_lite.blindfold_l5.v0_2`, preregistration `878e6812...`):
  - D1-D7, credit binding and candidate naming: `a1b5ab9b` (red), fixed in `f3ca0e63`.
  - Screened world sets, record identity and outcome binding: `e7616785` (red), fixed in `80f798ba`.
  - Run identity from the code digests: `f18bc4fc` (red), fixed in `4a302959`.
  - Pilot evidence: `427dd66b`.
- Escrow (measured, not fixable in code):
  - A same-account proposer read `/proc/<ppid>/cmdline`, then the root file, and stole 5 of 6 laws in a VALID run.
  - It also had network access, a child that outlived the campaign, and writable benchmark code.
  - Remedy: the OD-20 deployment. Evidence: `D:/forge-g0a1-final-evidence/escrow_probe_2026-10-14.txt`.

Commands run (Windows `.venv` 3.14 unless stated):
- BR-16 `4a302959`: `python -m pytest tests/genesis_lite -n 4`: 94 passed.
  - WSL 3.12 (in `pilot02.sh`): 94 passed.
- BR-15 `3c28bedf`: `python -m pytest tests/test_certified_dependency_closure.py`: 58 passed, 1 skipped (symlink privilege).
- BR-15 `aedc7b24`, with the certificate, recertification-scope, F-9 and F-7 suites: 193 passed, 1 skipped, 1 failed.
  - The failure is `test_the_certificate_describes_this_tree`: certified-file drift and an uncommitted edit, expected until OD-3.
- Real tree at `3c28bedf`: `certified_dependency_problems`, `authority_closure_problems` and `source_form_problems` all `[]`.
- v0.2 Tier-1 pilot, WSL 3.12: `python -m benchmarks.genesis_lite.pilot --root-file <operator> --out <dir>`.
  - 1,560 runs, 0 invalid, 384.79 s; run log sha256 `d504f2e3...`.
  - Formal ESTIMATE: 6,608.1 s (95% 6,597.7-6,618.4).
- Superseded pilots (not committed; roots retired):
  - `7cc71b13`: 1,560 runs, 13 INVALID on one world set (literal audit, 0.642 coincidence); log `6e70c72a...`.
  - `ddc7c3a6`: 1,560 runs, 0 invalid, 402.58 s; log `ca0716f3...`.

Final gates on integration `7d6d398b` (WSL clone, Linux; the next commit adds only this record):
- `python tools/forge_check.py --changed --base e193e573` (3.12): 10549 passed, 156 skipped, 582 deselected, 1 failed.
- `python -m pytest -m "not expensive" -q -n 4`, 3.12: 10549 passed, 156 skipped, 1 failed (520 s).
- The same command, 3.11: 10549 passed, 156 skipped, 1 failed (539 s).
- In all three, the single failure is `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`.
  - Cause: certified-file drift, plus classification/pattern changes in `assurance_admission` and `verdict_authority`.
  - It is expected until OD-3 recertification.
- Focused set (`tests/genesis_lite`, the F-9, F-7 and closure suites, `test_capability_completion.py`): 169 passed.
- `python tools/forge_check.py --regression`: 256 passed, exit 0.
- Pins: `certified_dependency_problems`, `authority_closure_problems`, `source_form_problems` and
  `harness_pinning_problems` all `[]`.
- `prereg_matches_code()` is `(True, 878e6812...)`.

Failed approaches, so they are not repeated:
1. A static loader deny-list grew by three review rounds and is still incomplete. Further spellings belong to a
   runtime audit-hook cross-check, not to more AST rules.
2. Strict completeness plus a strict literal audit made a formal lift impossible. An arm-independent screen must exclude
   a world set for every arm alike, not block the claim.
3. Reusing a pilot root after a code change. A new preregistration needs a fresh root; three roots are retired.
4. `cat > file` with no input inside a Bash tool command blocks on stdin until the timeout.
5. A sandbox launcher for the proposer was started and abandoned; OD-20 stays a deployment decision.

## 2026-10-14 -- Battery 1RC scientific closure (feat/battery-1rc-scientific-closure, local only)

Evidence package: [benchmarks/battery_1rc_closure/README.md](../../benchmarks/battery_1rc_closure/README.md).
Nothing is pushed or merged, and no recertification has been run. The owner approved the NASA archive download
(209,708,670 bytes, sha256 82302a7d..., outside the repo).

Ledger (`python -m tools.capability_maturity`, coherent): battery.thevenin_1rc computes **FUNCTIONAL** (was FOUNDATION).
- PASS with evidence: execution, provenance_replay, real_data, benchmark_metrics.
- MISSING with measured blockers: calibration (NOT_IDENTIFIABLE), independent_validation (cross-cell FAIL; within-cell
  NOT_ASSESSABLE), measurement_uq (UNKNOWN), parameter_uq, model_discrepancy, claims_integration,
  domainpack_integration.

Order of record (the commit history is the evidence):
1. Preregistration v1 `f02bdedb`, then v2 `2301632c`. v2 changes the capacity basis, before any fit.
2. Calibration data `653b243f`.
3. Calibration and identifiability `dadafae4`.
4. Held-out data `0f01baa3`.
5. Held-out evaluation `8a1b406d`.
6. UQ `5aa5c493`.
7. Review corrections `d5d85743`, re-reported from the same frozen calibration with no data reopened.

Gates on `d5d85743` (WSL clone, Linux):
- `python -m pytest -m "not expensive" -q -n 4`, 3.12: 10426 passed, 157 skipped, 1 failed.
- The same command, 3.11: 10426 passed, 157 skipped, 1 failed.
  - On both versions the failure is `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`: the
    certificate is stale and the new model definition changes the registry pin. Expected until recertification.
- `python tools/forge_check.py --changed --base e193e573`: the same single failure. It lists four
  RECERTIFICATION_REQUIRED test files: test_battery_thevenin_route.py, test_evidentiary_level_audit.py,
  test_capability_completion.py and test_core_guards.py.
- `python tools/forge_check.py --regression`: 256 passed, exit 0.
- Focused set (closure, route, kernel, battery domain, capability, audit, guards, NASA importer/adapter): 682 passed,
  1 skipped. The skip is the opt-in raw-bytes test.
- On Windows `.venv` 3.14 with `FORGE_NASA_FY08Q4_DIR` set, the closure tests pass 22 of 22, including the rebuild of
  every trajectory file from the raw `.mat` bytes.
- Rerunning fit -> evaluate -> uq reproduces every scientific number bit for bit; only the timing fields differ.

Scientific review (forge-scientific-reviewer): CHANGES REQUIRED. F1 HIGH, F2-F5 MEDIUM and L1-L4 were fixed in
`d5d85743`. Deferred: F6, the caller-declared applicability range; it must be bound to a calibration record before
claims integration (recorded in the ledger). Not analysed: sensitivity to the rest band.

Failed approaches, so they are not repeated:
1. A capacity basis from NASA's `Capacity` field is wrong for cells that discharge below 2.7 V.
2. A parameter-set range equal to the calibration min/max is tripped by measurement-level excursions. Declare the range
   from evidence in the next preregistration, never by widening it after results.
3. Running benchmark modules without `PYTHONPATH="<wt>/src;<wt>"` imports the shared checkout's engcore.
4. `pytest ... | tail` in a command chain hides pytest's exit code; one commit went in with a red test, fixed in `a130a0e1`.

## 2026-10-14 -- Battery 1RC identifiability and independent evidence (feat/battery-1rc-identifiability, local only)

Evidence package: [benchmarks/battery_1rc_identifiability/README.md](../../benchmarks/battery_1rc_identifiability/README.md).
The branch is stacked on the closure branch (50671ebd), which is unchanged. Nothing is pushed or merged, and no
recertification has been run.

WP1. An independent review of the NASA closure found it SOUND_WITH_CAVEATS (eight caveats in the README). Its four
result digests are pinned unchanged by a test.

WP2. Dataset qualification:
- LG HG2 (McMaster, CC BY 4.0) is qualified and used. It is one cell; its bytes match Mendeley's published sha256.
- Kirkaldy 2024 is the cross-cell candidate. It is not acquired: a multi-GB download that needs owner approval.
- Jahn A123, Panasonic 18650PF, Chen 2020 and NASA were assessed.

WP3/4. Order of record (the commits are the evidence):
1. Preregistration f06905dc (d8acfb26...).
2. Data roles a4e83f72.
3. Calibration 6e69f0c9.
4. Held-out evaluation ec788c2f, opened once.
5. Tests and outcome 709a46de.
6. Ledger c99b1781.
7. README 7a2698d4.
8. Review corrections d35cecb0: re-reported from the same frozen records, with no threshold or mapping change.

Results:
- IDENTIFIABLE: R0 20.7 mOhm, R1 15.6 mOhm, C1 1586 F, tau 24.8 s, with the OCV measured from relaxed rests.
- Held-out 2C/4C pulses PASS the pooled limits (12.6 mV), but fail under load alone (19.7 mV).
- The 1C constant-current test FAILS marginally (28.7 mV, P95 50.7 mV).
- Outcome MODEL_REJECTED. Without the preregistered +/-1 degC widening it would be IDENTIFIABILITY_SUPPORTED.
- Ledger: calibration PASS (scoped); the computed stage stays FUNCTIONAL.

Commands and results:
- Windows .venv 3.14, `FORGE_LGHG2_DIR=<raw> pytest benchmarks/battery_1rc_identifiability/tests benchmarks/battery_1rc_closure/tests tests/test_capability_completion.py`:
  47 passed, 1 skipped (the closure's opt-in raw-bytes test). This includes the rebuild of every role from the raw
  LG HG2 bytes.
- Manual rerun of fit -> evaluate -> outcome reproduced CALIBRATION.json and VALIDATION.json byte for byte; only the
  unpinned TIMINGS files changed.
- Trial merge of integration/g0-a1-unblock with this branch:
  - conflicts only in docs/work/ACTIVE_PLAN.md and PROGRESS.md;
  - certified_dependency, authority_closure, source_form and harness_pinning problems all [];
  - 498 passed, 3 skipped (guards, audit, route, both battery benchmarks, closure tests, genesis_lite).
- WSL gates on d35cecb0:
  - `pytest -m "not expensive" -n 4`, 3.12: 10446 passed, 158 skipped, 1 failed.
  - The same, 3.11: 10446 passed, 158 skipped, 1 failed.
  - On both, the failure is `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`: the
    certificate is stale and the closure branch adds a model definition, so recertification is needed.
  - `forge_check --changed --base e193e573`: the same single failure, and the four RECERTIFICATION_REQUIRED test files.
  - `forge_check --regression`: 256 passed.
  - Focused set: 702 passed, 2 skipped (the opt-in raw-bytes tests).

Failed approaches, so they are not repeated:
1. Letting an out-of-domain set FAIL broke "contradiction requires admissible evidence". Out-of-domain is now
   NOT_ASSESSABLE in both directions. The closure's cross-cell FAIL carries this caveat and is not edited.
2. Pooling rest samples hid a load-only miss. Report load and rest separately alongside any pooled acceptance.
3. Comparisons with one unit need no verdict field, only a point difference.

## 2026-10-15 -- Owner decisions and the consolidated source (integration/g0a1-battery-1rc, local)

Owner reply "approved" (2026-10-15), applied to the three listed decisions:
1. The LG HG2 publisher-stated Type B accuracy is admitted for its own channels only
   (benchmarks/battery_1rc_identifiability/MEASUREMENT_UNCERTAINTY_DECISION.json). NASA stays UNKNOWN.
   - battery.thevenin_1rc measurement_uq is PASS.
   - The computed stage stays FUNCTIONAL: independent_validation (cross-cell) is the only gate left before
     EVIDENCE_BACKED.
   - No frozen acceptance or outcome changed.
2. Push and one hardened recertification of the consolidated source.
3. The Kirkaldy 2024 download: the exact files and sizes are listed for confirmation before any byte is fetched.

Consolidated source: `integration/g0a1-battery-1rc` (worktree `D:/forge-consolidated`). It is
`integration/g0-a1-unblock` (d1c96ae4) merged with `feat/battery-1rc-identifiability` (a4d4c24b) in 37674bfc. The
union resolution touched only docs/work/ACTIVE_PLAN.md and PROGRESS.md.
- `pytest benchmarks/battery_1rc_identifiability/tests benchmarks/battery_1rc_closure/tests tests/test_capability_completion.py`
  (Windows): 47 passed, 2 skipped (the opt-in raw-bytes tests).


## 2026-10-15 -- Battery 1RC cross-cell evaluation on Kirkaldy 2024 (feat/battery-1rc-crosscell, local only)

**Data.**
- Owner-approved partial download ("Partial: 25°C BoL tests"): the 36 RPT0 CSVs of the 12 LG M50T cells at 25 °C, about
  250 MB, read from the five Zenodo 10637534 archives by HTTP range. Each file was CRC32-checked.
- Location: D:/forge-data/kirkaldy2024/bol25 (receipts in bol25.sha256).

**Commits** (worktree D:/forge-battery-xcell, based on the certified source 5847345e, which is unchanged):
- cc4d1256: preregistration PREREGISTRATION.json b1704515..., frozen before any fit. After the freeze, and before
  data.py was written, a temperature-only dropout census over the 24 GITT files was run. It read no voltages.
- a5ad3523: roles.
  - The first roles commit, 256679db, was reset and never pushed. It committed the 85 MB window JSONs. The three window
    roles are now gitignored and pinned by their committed .sha256; a rebuild must reproduce them byte for byte.
  - Each build takes ~1 min.
  - The first build excluded 50 Expt 2,2 windows as "not relaxed". Reading the raw step edges of those HELD-OUT cells
    found a zero-current on-load transition record. Deviation 2 drops it by a uniform rule.
  - This partly unblinded the Expt 2,2 cells (on-load drops of 67-84 mV seen) before the fit. No model had run, and the
    fit had no free choice left.
  - Deviation 1 (exclude any window holding a temperature dropout) removed no window on these files.
- 3c865540: calibration on the 7 calibration cells, committed before the held-out evaluation ran.
  - IDENTIFIABLE: R0 33.1 mΩ, R1 20.2 mΩ, C1 5307 F, τ 107 s. Cell-block bootstrap CV ≤ 6.1 %.
- Held-out (5 cells, strict transfer through the engcore route):
  - Primary: 32/99 windows outside the unwidened calibration domain.
  - Secondary: 8/17 windows outside.
  - Causes: temperature down to 17.61 °C against a 23.19 °C minimum, and current up to 0.52 mA above the calibration
    maximum.
  - Both sets are NOT_ASSESSABLE, so the outcome is **IDENTIFIABILITY_SUPPORTED**. The ledger's independent_validation
    stays MISSING; the computed stage stays FUNCTIONAL.
  - Descriptive only (no verdict): in-domain-only 1RC RMSE is 9.5 mV primary and 11.8 mV secondary.
- evaluate.py ran four times after the held-out cells were opened.
  - Runs 2-4 added descriptive fields, gated the comparison verdict (stricter only), and applied the review fixes.
  - Every run-1 metric and acceptance value is unchanged; a test checks this.
  - Superseded records: results/superseded/VALIDATION_run{1,2,3}.json.

**Independent review** (forge-scientific-reviewer): CHANGES REQUIRED, no blocker. All findings fixed:
- M1: disclosure of the post-opening changes (VALIDATION.json post_opening_changes, README section).
- m1/m2: no verdict token in a NOT_ASSESSABLE comparison; the calibration comparison is IN_SAMPLE.
- m3: dropout counts and the split dropout reason.
- m4: partial-unblinding wording; "50 windows" corrected.
- m5: this entry.
- m6: a cycler accuracy cannot close the temperature gap (25 of 32 primary windows); the ledger was reworded.
- m7: the current excess is derived.
- m8: calibrated_z_span recorded (min 0.130).
- m9: the descriptive subsets are labelled as not neutral / all-window.
- m10: the OCV source wording.
- m11: tests added for synthetic route-vs-transcription, comparison gating, held-out leakage, knot-structure refusal,
  and absolute LG HG2 digests.

**Failed approach.** Committing native-0.1 s window JSONs (85 MB) does not scale. Pin them by digest and rebuild from
the pinned raw files.

**Tests** (Windows, this worktree):
- `FORGE_KIRKALDY_DIR=D:/forge-data/kirkaldy2024/bol25 python -m pytest -q -p no:cacheprovider --basetemp=<tmp> benchmarks/battery_1rc_crosscell/tests benchmarks/battery_1rc_identifiability/tests benchmarks/battery_1rc_closure/tests tests/test_capability_completion.py tests/domains/test_battery_thevenin_route.py tests/test_core_guards.py`
  - Result: 372 passed, 2 skipped. This includes the byte-for-byte rebuild of every role from the raw files.
- `python tools/forge_check.py --changed` (no --basetemp, so the Windows default temp root applies):
  - Result: 9868 passed, 18 failed, 734 errors.
  - The errors are all tmp_path PermissionError (known environment issue).
  - Running the same 18 on the untouched base 5847345e: 16 fail there too (mutation_workspace POSIX-only, blindfold
    escrow, certificate/freeze-v4 manifests).
  - The other 2 (test_the_tree_is_core_freeze_v1, test_the_v3_contract_is_superseded...) failed only on
    tree.clean (uncommitted files). They were rerun after the commit; see below.
- After commit 14d49ab6: `pytest tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1 tests/test_core_freeze_v3_manifest.py::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks`: 2 passed. The remaining 16 failures are the base's own Windows baseline.

- Follow-up (same day): the two env/file-gated cross-cell tests became the commands `data --verify-raw` and `evaluate --verify-route` (see the 5847345e recertification refusal entry). Run: `data --verify-raw D:/forge-data/kirkaldy2024/bol25` problems [], exit 0; `evaluate --verify-route` problems [], exit 0; `pytest -rs benchmarks/battery_1rc_crosscell/tests` 29 passed, 0 skipped.
## 2026-10-15 -- Hardened recertification of 5847345e: REFUSED (skip admission); source fix

**The run.** `local_assurance prepare` + `run --reuse --repository sharq-labs/forge` in the fresh WSL clone
~/forge-cons-assure, 2026-10-14T22:27Z to 2026-10-15T02:00Z, EXIT=1.
- Result: `LOCAL_ASSURANCE: REFUSED`, `REFUSAL_KIND: EXPECTED_ASSURANCE_REFUSAL`, `SAFE_TO_PUSH: NO`. Failure record
  sha256 f12457aa....
- All six refusal lines are `UNEXPECTED_SKIP ... no committed rule covers this node id`, in fast311, fast312 and
  scientific312, for the two opt-in raw-data tests:
  - `benchmarks/battery_1rc_closure/tests/test_battery_1rc_closure.py::test_every_trajectory_file_rebuilds_from_the_raw_nasa_bytes`;
  - `benchmarks/battery_1rc_identifiability/tests/test_battery_1rc_identifiability.py::test_every_role_rebuilds_from_the_raw_lg_hg2_bytes`.
- The trust mutation population finished with 0 survived. No certificate was written and nothing was pushed.

**Why not a skip rule.** The admission policy (tools/certification/skip_admission.py, certification tooling) admits
rule paths only under tests/, providers/ and flagships/. Widening it would weaken a certified gate to admit tests that
can never run in the gates, because the raw files are not shipped.

**Fix** (benchmarks only, no certified file touched):
- Each raw-bytes rebuild is now a command:
  - `python -m benchmarks.battery_1rc_closure.data --verify-raw <dir>`;
  - `python -m benchmarks.battery_1rc_identifiability.data --verify-raw <dir>`.
  - Each exits 1 and lists every problem.
- An always-running test checks that each command refuses when the files are absent.
- The ledger evidence and both READMEs follow.
- Commands run (Windows .venv, this worktree):
  - `... closure.data --verify-raw "D:/forge-data/nasa_pcoe_battery/extracted/1. BatteryAgingARC-FY08Q4"`: problems [],
    exit 0.
  - `... identifiability.data --verify-raw D:/forge-data/lg_hg2/raw`: problems [], exit 0.
  - `... identifiability.data --verify-raw D:/forge-data/nonexistent`: one "cannot rebuild" problem, exit 1.
  - `pytest -q -p no:cacheprovider --basetemp=<tmp> -rs benchmarks/battery_1rc_identifiability/tests benchmarks/battery_1rc_closure/tests tests/test_capability_completion.py tests/domains/test_battery_thevenin_route.py tests/test_core_guards.py`:
    345 passed, 0 skipped.

**Failed approach recorded.** An env-gated `pytest.mark.skipif` raw-data test always skips in the hardened gates and
refuses the whole run after ~3.5 h. Raw-data rebuilds belong in a command.

**Next.** One hardened local-assurance run on this new source commit, in a fresh WSL clone.

## 2026-10-15 -- Hardened run on 0bc8b1cb: all 18 gates passed, REFUSED at certificate generation (environment)

Run: fresh WSL clone ~/forge-cons-assure-2, `/usr/bin/python3.12 -m tools.certification.local_assurance run --reuse
--repository sharq-labs/forge --python311 .forge/venvs/3.11/bin/python --python312 .forge/venvs/3.12/bin/python`,
2026-10-15T02:06Z to 05:39Z, EXIT=1.

Result: `LOCAL_ASSURANCE: REFUSED`, `REFUSED_BY: CertificationError`, `SAFE_TO_PUSH: NO`. Failure record sha256
abba1c6a....
- Every execution gate completed:
  - fast311 and fast312: 10602 passed, 156 skipped;
  - scientific312: 11175 passed, 156 skipped;
  - campaign312 and regression312;
  - formal_mutations_0-3 and v4_mutations_0-7;
  - trust_mutations: 0 survived.
- Skip admission accepted every skip. The two raw-data skips that refused 5847345e are gone, and each gate gained the
  2 replacement tests.
- `failed_gate: certificate_generation`: "the production registry could not be read from the tree:
  ModuleNotFoundError: No module named 'pint'".

**Cause** (environment, not source):
- `core_certificate.production_registry_identity` (BR-15) re-runs `sys.executable -E -s -P`, so it uses the OUTER
  interpreter.
- The outer interpreter was `/usr/bin/python3.12`, which has no project dependencies. Checked read-only:
  - `/usr/bin/python3.12 -E -s -P -c "import pint"` gives ModuleNotFoundError;
  - `.forge/venvs/3.12/bin/python` with the same flags imports pint, numpy and scipy.
- The last local PASS (Pass 13) predates the BR-15 probe, so the outer system interpreter never mattered before.

**Remedy, not yet run:**
- Launch `local_assurance run` with `.forge/venvs/3.12/bin/python` as the outer interpreter, in a fresh clone, so run 2's
  evidence is preserved.
- There is no resume: `--reuse` discards evidence and re-runs every gate (~3.5 h).
- The certification source stays 0bc8b1cb.
- Waiting for owner approval.

## 2026-10-16 -- Landing pass: recent active work merged into main (integration/main-landing-2026-10-16)

**Owner direction (2026-10-16).**
- "Merge everything not merged and resolve the conflicts."
- Scope: recent active work. September and early-October stale branches are skipped.
- Certified files: merge now, recertify later.

**Merged, by merge commit** (branch heads kept, so the PRs show as merged):
- #145 `docs/local-assurance-interpreter`;
- #143 `fix/ci-reproduce-and-g0-record`, and `fix/ci-reproduce-docker-history` (local);
- #144 `fix/electrical-support-gates`;
- #130 `perf/test-suite-runtime` and #131 `claude/adoring-cray-jj367z` (docs);
- `codex/final-test-assurance-closeout`, `codex/repair-scientific-boundaries` and `feat/a1-5-operating-rating` (local);
- the chain `feat/battery-1rc-crosscell`. It carries:
  - `integration/g0a1-battery-1rc` (0bc8b1cb);
  - `integration/g0-a1-unblock`;
  - `fix/br15-authority-closure`;
  - `feat/br16-genesis-lite-benchmark`;
  - `feat/battery-1rc-scientific-closure`;
  - `feat/battery-1rc-identifiability`;
  - the Kirkaldy cross-cell experiment.

**Not merged:**
- `fix/final-assurance-blockers`, which is superseded:
  - Its `tools/test_impact.py` scanner conflicts with main's newer `tools.certification.ownership` design.
  - Its 7 tests in `tests/test_impact_repository_scope.py` encode the replaced contract (ValueError) and fail against
    main.
  - Its benchmark digest re-pin targets the scientific tree at 5d73e8f5 (OD-17).
- Stale branches, left untouched and listed for OD-11 hygiene:
  - September: provider-architecture-pybamm-pybop, battery-voltage-s3-recovery, battery-thermal-flagship-sprint-3,
    domain-real-data, multidomain-science-hardening, wip/applicability-screens-and-prerequisites, evidence-v11,
    fix-bisect-table, #39 core/p0-trust-boundaries-v2, #24 chatgpt/core-v2-trust-repair-1-4,
    codex/critical-production-closure, p0 fixes, docs/blind-rediscovery-benchmark-v1, docs/main-check-2026-10-13;
  - early October: #107 ci/self-hosted-heavy-runner, ci/local-only-assurance, ci/incremental-hardened-recertification.

**Conflict resolutions:**
- `docs/work/PROGRESS.md` and `ACTIVE_PLAN.md`: union of both sides.
- #130 and #131 both numbered a new decision OD-15. #131's `is_usable` decision is now **OD-21**: OD-15 stays #130's
  CI-policy decision, and OD-18..20 belong to the G0/A1 chain. References were updated, and the duplicate OD-14 row is
  gone.
- `uq/budget/aggregation.py`: the auto-merge produced two empty-budget refusals. Main's ("an empty budget is UNKNOWN,
  not zero") is kept. The branch's serializer refusal and its explicit-zero test are kept.
- `CORE_FREEZE_POLICY.md` and `test_core_api_layering.py`: both new non-Core packages are kept (`authority`, `mind`).

**Fixes needed to make the combination honest:**
- Core purity: the `operating_rating.py` docstring said "motor"/"flight", which is thing vocabulary.
- The schema-reader invariant: `engcore.mind` records read payloads with no schema. `MindState` now writes and checks
  `forge.mind.state/1`, and its nested records are path-qualified exemptions read only through it.
- Scientific review (forge-scientific-reviewer, CHANGES REQUIRED) of the a1-5 Core module:
  - MAJOR 1: a caller admission id plus an unpublished quantity yielded SUPPORTED_WITHIN_RATING. The operating point
    now needs a compared, same-kind published limit.
  - MAJOR 2: the packet and multirotor mission adapter moved to `engcore.systems.products.drone_ratings`.
  - Both fixed, with the counterexample pinned by a test.
- The BR-15 recertification instruction names the venv interpreter.

**Open review MINORs** (not fixed in this pass):
- `UncertaintyBudgetReport` has no `__post_init__`, so an empty, zero report can be constructed directly. This hole
  pre-exists the pass.
- `claims/compiler.py` labels every NOT_ASSESSABLE applicability as CAPABILITY_MISSING. That is conservative, but
  mislabelled.
- In `operating_rating`, any one supported component makes the mission SUPPORTED. The any-of/all-of semantics are not
  declared.
- `engcore.mind`'s `authority_result_id` is an unchecked string. It is harmless while nothing consumes MindState as a
  verdict.
- Main's ownership module misses three hostile cases from the unmerged branch:
  - inventory names escaping the root;
  - worktree `.git` pointing at another repository;
  - a tracked `.py` replaced by a directory.

**Certification state.** `main` now carries uncertified changes to certified files: BR-15 certification tooling, the
battery 1RC route in the production registry, and the Core module `scientific/knowledge/operating_rating.py`. The owner
accepted recertifying afterwards. `test_the_certificate_records_the_v1_relationship_truthfully` now fails with the
expected staleness (the V1-compatible Core digest moved), and `test_the_certificate_describes_this_tree` already failed
on main. The hardened run (prepared `~/cons-assure-3.sh` + `~/assurance-preflight.sh`) must target the new main HEAD,
not 0bc8b1cb.

**Tests** (WSL, CPython 3.12 venv, `PYTHONPATH=<tree>/src:<tree>`):
- `python -m pytest -m "not expensive" -q -n 4 -p no:cacheprovider -p no:randomly`.
- Pristine main e193e573: 10374 passed, 1 failed (`test_the_certificate_describes_this_tree`), 156 skipped.
- Landing tree bd927d8a: 10719 passed, 2 failed, 156 skipped, tracked tree clean afterwards. The only failure not present on main is `test_the_certificate_records_the_v1_relationship_truthfully` (expected certificate staleness, above). Earlier landing trees: 4f7576e0 had 3 failures (the third was the mind schema invariant, fixed in eecef67b); eecef67b had the same 2.
- Windows .venv 3.14 targeted runs: `tests/mind tests/test_core_semantic_invariants.py tests/test_core_api_layering.py tests/test_core_guards.py` 417 passed; `tests/scientific/knowledge tests/test_core_guards.py` 309 passed; `tests/uq/budget tests/claims/test_unassessable_compilation.py tests/foundations/test_discovery_deadline.py` 20 passed, 11 skipped (POSIX-only).

## 2026-10-16 -- FAST slowdown attribution across PR #146 (measurement only)

**Who measured this.** The attribution session ("Profile FAST slowdown on main 91b44e22") measured these figures on
2026-10-16, on Windows with .venv CPython 3.14.2, using `-n 4 --dist loadfile`; the N-* pair below used `--dist load`.
None of it was re-run for this entry.
- Raw data: `D:/pf/runs`.
- Full analysis: side-session note `fast-slowdown-attribution-2026-10-16.md`.
- The fix is the next entry.

**Headline numbers:**
- ABBA FAST wall, e193e573 -> 91b44e22: 267.6 -> 573.8 s (x2.14).
- Summed test time: +795.7 s, 97% of it in eight certification modules.
- One `verify_certificate` in isolation: 7.15 -> 27.2 s.
- A scratch prototype brought a repeated verify back to 7.2 s, with results identical to the shipped code. It used a
  byte-keyed memo, a per-call listdir memo and one private probe prefix per process.

**Exact commands run:**
```
# all: cwd=<worktree>, PYTHONDONTWRITEBYTECODE unset (except N-*), PYTHONPATH='<wt>\src;<wt>', TMP/TEMP/TMPDIR=D:\pft\<label>
.venv/Scripts/python.exe -m pytest -m "not expensive" -q -n 4 --dist loadfile --basetemp=D:\pfb\<label> --durations=40 --junitxml=D:\pf\runs\<label>\junit.xml
#   A1-old e193e573 243.9 s: 153 failed, 10167 passed, 189 skipped, 22 errors
#   B1-new 91b44e22 550.0 s: 154 failed, 10500 passed, 201 skipped, 22 errors
#   B2-new 91b44e22 597.6 s: same;  A2-old e193e573 291.2 s: same as A1
#   I-old / I-new (+ -p probe_metrics): 279.6 s / 577.6 s, same outcomes
# N-*: --dist load, PYTHONDONTWRITEBYTECODE=1, pycache-free worktrees
#   N-new 653.8 s: 154 failed, 10500 passed;  N-old 312.8 s: 153 failed, 10167 passed
# Only-new failure: tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully
```

## 2026-10-16 -- FAST slowdown fix: verifier analysis memo and per-process probe prefix (perf/cert-closure-memo, local only)

**Why.** PR #146 (main 91b44e22) made FAST about 2.1x slower on Windows: 97% of the delta sat in eight certification
modules, and one `verify_certificate(require_current_scope=True)` went from 7.15 s (e193e573) to 27.2 s. The cause was
in `tools/certification/core_certificate.py` (BR-15 6d62e5cf, aedc7b24, 26f2505c, 3c28bedf):
- the authority, certified-dependency and evidence-code closures re-parsed the same files on every call;
- `_spelled_on_disk` made about 220,000 `os.listdir` calls per verify;
- the registry probe compiled the interpreter's library, numpy, scipy and pint into a fresh pycache prefix on every
  probe.

Attribution: the previous entry, and side-session note `fast-slowdown-attribution-2026-10-16.md`.

**What changed** (certification-pinned; branch `perf/cert-closure-memo` from 91b44e22, worktree `D:/forge-cert-memo`):
- **Analysis memo.** `dynamic_imports` and `_engcore_imports` are memoized in-process. The key is the SHA-256 of the
  exact bytes parsed, plus the package (imports) or the rule tables (dynamic loads), plus `sys.get_int_max_str_digits()`.
  - Star-package listings, `is_file` and on-disk spelling are read on every call.
  - No disk, nothing shared across processes, no mtime keys.
- **Directory listings.** `_spelled_on_disk` reads them from a dict that lives for ONE closure walk; failed listings
  are not kept.
- **Probe prefix: one private directory per process.**
  - Made by `mkdtemp`, with only its parent resolved; never inside the tree; one prefix per interpreter (cache tag,
    magic number, executable).
  - Reused, and removed at exit, only while it is still the directory this process made: same lstat dev/inode, not a
    link or junction, and on POSIX this user's with no group/other bits. Never adopted by a forked child.
  - On Windows, used only where `mkdtemp` is private (CPython >= 3.12.4, or 3.13 from 3.13.0b1).
- **Seeding before EVERY probe.** A clean interpreter started like the probe (`-E -s -P -B -X pycache_prefix`):
  - compiles every `.py` under the resolved `src/` into the prefix as CHECKED_HASH `.pyc`, from the bytes it reads;
  - keeps a `.pyc` only when the source SHA-256 and the `.pyc` SHA-256 both match its record;
  - removes every other file under the tree's (and `src/`'s) part of the prefix;
  - refuses a link or junction anywhere from the prefix down.
- **Failure paths.** Any seeding failure gives the probe a one-shot prefix, as before. A one-shot directory swapped for
  a link fails the probe. Each probe gets a fresh working directory, probe results are never cached, and the tree's
  `__pycache__` is still never read.

**Results identical to the shipped verifier.** `equiv.py` (session scratchpad) takes the code from one tree and verifies
the pristine 91b44e22 tree. It compares 10 result groups:
- `verify_certificate` x3 (the full VerificationResult);
- `production_registry_identity` x2 (including 457 evidence-code digests);
- `authority_import_closure`, `authority_closure_problems`, `certified_dependency_problems`;
- `dynamic_imports` and `_engcore_imports` of all 726 files under `src/`.

All 10 were identical at 6749f1cd, a0e0ce4a, 32976cf4, eb7b0c9f, 4c3383de and the branch's last commit.

**Measured** (Windows, .venv CPython 3.14.2; host idle by `D:/pf/scripts/busy.py` before each run):
- **Isolation.** `D:/pf/scripts/iso.py <tree> <out> --freeze`, ABBA twice (A = pristine 91b44e22, B = this branch at
  6749f1cd and a0e0ce4a):

  | call | A | B |
  |---|---|---|
  | `verify_certificate(require_clean=False, require_commit=False)` | 25.4-29.5 s | 7.2-7.6 s |
  | `production_registry_identity`, warm | 11.6-12.6 s | 3.3-3.9 s |
  | `core_freeze_v4.verify()` | 50.7-60.5 s | 16.2-18.4 s |
  | `core_freeze.collect_live` | 25.1-29.5 s | 7.8-8.3 s |
  | `certified_dependency_problems` | 9.9-11.0 s | 4.6-5.0 s |

  The first `production_registry_identity` in a process still takes 11.2-13.3 s on B. For reference, e193e573's
  `core_freeze_v4.verify()` was 17.0 s.
- **FAST.** `fastrun_memo.py`, a copy of the attribution's runner, ran
  `.venv/Scripts/python.exe -m pytest -m "not expensive" -q -n 4 --dist loadfile --basetemp=D:\pfb\memo-<label>
  --durations=40 --junitxml=D:\pfm\runs\<label>\junit.xml`, with PYTHONDONTWRITEBYTECODE unset,
  `PYTHONPATH='<wt>\src;<wt>'` and TMP/TEMP/TMPDIR=`D:\pft\memo-<label>`:

  | run | tree | wall | result |
  |---|---|---|---|
  | FA1 | 91b44e22 | 567.8 s | 154 failed, 10500 passed, 201 skipped, 22 errors |
  | FB1 | a0e0ce4a | 328.4 s | 154 failed, 10527 passed, 202 skipped, 22 errors |
  | FB2 | a0e0ce4a | 306.1 s | as FB1 |
  | FA2 | 91b44e22 | 517.7 s | as FA1 |
  | FB3 | 32976cf4 | 314.9 s | same 176 failing ids as FA1 |
  | FB4 | eb7b0c9f | 260.1 s | same 176 failing ids as FA1 |
  | FB5 | 4c3383de | 260.2 s | same 176 failing ids as FA1 |

  - Wall mean (FA vs FB1/FB2): 542.8 -> 317.2 s (x1.71). Summed test time: 1583.1 -> 1010.3 s (-572.8 s).
  - The 176 failing ids are identical in all four ABBA runs, with none on one side only. They are the pre-existing
    Windows/worktree/py3.14 failures from the attribution's runs, plus `test_the_certificate_describes_this_tree` and
    `test_the_certificate_records_the_v1_relationship_truthfully` (expected on uncertified main).
  - Per module, summed s: core_freeze_v4_manifest 293.1 -> 122.5, core_freeze_v3_manifest 230.0 -> 98.5,
    certificate_verdict_scope 173.8 -> 64.9, core_freeze_manifest 134.8 -> 61.1, certification_control_plane
    71.2 -> 26.5, core_scientific_audit_batch56 65.9 -> 25.1, core_certificate 41.0 -> 21.5,
    certified_dependency_closure 27.9 -> 21.1. The new module adds 5.2 s.
  - No `forge-registry-probe-*` directory was left in any run's TMP: the xdist workers run the exit cleanup.

**Tests run** (exact commands, branch head):
- **New module, Windows.** `PYTHONPATH='D:\forge-cert-memo\src;D:\forge-cert-memo' TMP=D:\pft\memo-unit
  .venv/Scripts/python.exe -m pytest tests/test_certificate_verifier_memo.py -q -p no:cacheprovider -p no:randomly
  --basetemp=D:/pfb/memo-unit -rs` -> 51 passed, 3 skipped. Two skips are symlinks, which need a privilege here; one
  is the POSIX-only setgid test.
- **Certification modules, Windows.** `... -m pytest tests/test_certified_dependency_closure.py
  tests/test_certificate_verdict_scope.py tests/test_core_certificate.py tests/test_certificate_verifier_memo.py -q
  -p no:cacheprovider -n 4 --dist loadfile --basetemp=D:/pfb/memo-cert -rfs` -> 2 failed, 173 passed, 5 skipped.
  - The 2 failures are `test_the_certificate_describes_this_tree` and
    `test_the_certificate_records_the_v1_relationship_truthfully`, which also fail on 91b44e22.
  - The skips are symlink creation x4 and POSIX setgid.
- **New module, POSIX.** WSL Ubuntu, CPython 3.11.17, using the `~/forge-hostile-remediation/.forge/venvs/3.11` venv
  read-only with PYTHONDONTWRITEBYTECODE=1: `PYTHONPATH=/mnt/d/forge-cert-memo/src:/mnt/d/forge-cert-memo
  TMPDIR=/tmp/memo-posix-tmp python -m pytest tests/test_certificate_verifier_memo.py -q -p no:cacheprovider
  -p no:randomly --basetemp=/tmp/memo-posix-bt -rs` -> 54 passed, 0 skipped.
- **Flaw checks.** Scratch `mutate_check6.py` and `D:/pfm/mutate_posix.py` apply 42 deliberate flaws to
  `core_certificate.py` one at a time. Each run executes the tests that name the flaw, then restores the original
  bytes and checks their SHA-256.
  - Windows 3.14: 39 caught. Missed: M17 (mkdtemp result not resolved; equivalent on 3.12+), M26 (privacy back to
    exactly 0o700; its test is POSIX-only), M31 (file links not reported; needs a file symlink).
  - Linux 3.11: 41 of 42 caught (the first 41 run at 4c3383de, M32 at the last commit; the code between them
    differs only in comments). Missed: M23b (no reparse-point check; Linux has no junctions).
  - Every flaw is caught on at least one of the two platforms.

**Scientific review** (`forge-scientific-review`, read-only; no BLOCKER, HIGH or MEDIUM in any pass):

| reviewed | verdict | items | fixed in |
|---|---|---|---|
| 6749f1cd | CHANGES REQUIRED | I1-I6 (LOW) | a0e0ce4a |
| a0e0ce4a | CHANGES REQUIRED (I1-I6 closed) | LOW-1..3, O1-O4 | 32976cf4 |
| 32976cf4 | CHANGES REQUIRED (LOW-1..3 closed) | LOW-A..C, Ob-1..5 | eb7b0c9f |
| eb7b0c9f | CHANGES REQUIRED (LOW-A..C closed) | LOW-D..G, Ob-6..9 | 4c3383de |
| 4c3383de | **PASS** | LOW-H, Ob-10..12 | branch's last commit |

What each round of fixes did:
- a0e0ce4a: seeding moved into a clean interpreter; whole-tree sweep; fresh cwd per probe; directory identity check;
  resolved mkdtemp; failed listings not kept; more tests.
- 32976cf4: `src/` mirror swept when it lies outside the tree; privacy means no group/other bits, checked right after
  mkdtemp; residuals stated; tests for a forged checked-hash `.pyc` and a failed seeding.
- eb7b0c9f: parent-only resolve; junctions refused; Windows version gate; link pre-check in the seeding; setgid and
  mode tests.
- 4c3383de: the one-shot fallback refuses a swapped link; the gate excludes non-CPython and the 3.13 alphas; `-B` for
  the seeding; a same-owner private replacement test; file links refused.
- Branch's last commit: LOW-H, the link check between the prefix and the mirror, gets tests with the link above the
  mirror and at the prefix (they catch flaw M32 on both platforms); residual wording; the memo key's omission of the
  warnings filter is documented.
- The PASS came from the reviewer reading the code; the reviewer executed nothing.

**Residuals** (stated beside the code):
- Library bytecode carried over between probes is shared by every probe in a process, so tree code one probe runs
  could leave bytecode a later probe runs.
- Between seeding and import, a source is tied to its `.pyc` only by CPython's 64-bit source hash.
- A venv inside the tree is swept with it: the shared checkout's `.venv`, and the local_assurance clones'
  `.forge/venvs`. Those runs keep the analysis speed-up but recompile the library on each probe.
- What "private" rests on:
  - POSIX mode bits, which do not show macOS ACLs;
  - on Windows, mkdtemp's ACL;
  - nothing at all on a FAT/exFAT temp root.
- On a temp root where others can rename this user's entries:
  - a directory swapped for a link after its check is followed, as before;
  - on Windows, a real directory swapped in before the identity is read is accepted.
- A forked child that exits via `os._exit` leaks its directory, and a fork while `_PROBE_LOCK` is held deadlocks the
  child.
- The memo key leaves out the warnings filter. A file whose fresh parse raises under `-W error` is answered from the
  memo; the answer still describes the bytes on disk.

Not addressed (measured, out of scope): a warm `certified_dependency_problems` still spends about 3 s in pathlib
`relative_to` (3.14) and `is_file`. Those code paths are unchanged.

**Failed approaches (do not repeat):**
- Compiling the probe's bytecode in the verifier process with a reimplemented `cache_from_source` mapping. The
  verifier's own state (the integer-digit limit, a patched `compile`, `-O`, future flags) reached the probe (review I3).
- Sweeping only `src/`'s part of the prefix, and reusing the persistent directory as the probe's cwd (review I4).
- `.resolve()` on mkdtemp's result: it follows a link swapped in for the new directory (reviews LOW-A and LOW-D).
- Measurement mistakes:
  - the first equivalence run overlapped another session's WSL preflight FAST, so its timings were discarded;
  - `wsl.exe -d Ubuntu` used to inspect WSL processes boots the distro; rely on busy.py instead;
  - a bash heredoc turned `\\n` into newlines in a generated script; write scripts with the editor.

**RECERTIFICATION_REQUIRED (OD-3).** `tools/certification/core_certificate.py` is in the `certification_control` area
(`tools/certification/*.py`), so the certificate's control-area digest moves. Main already needs OD-3 recertification.

**TOOL_VERSION decision: unchanged at 2.6.0.** There is no algorithm or certificate-shape change (the results above are
identical), and the implementation is pinned by its bytes. Note that 26f2505c and 3c28bedf changed detection behaviour
without a bump, so the owner may prefer a single bump (e.g. 2.7.0) at recertification to cover those.

Nothing has been pushed, no PR opened, and no recertification run.

## 2026-10-13 Check of `main` @ `5d73e8f5` on Python 3.12 (cloud session, Linux; read-only except this entry)

Environment: Linux container, 2 CPUs, CPython 3.12.13 (uv venv) with full history fetched; `pip install -e
".[dev,mcp,oracles]"`. Python 3.11: NOT RUN. SCIENTIFIC, FULL and hardened recertification: NOT RUN.

| Command | Result |
|---|---|
| `python tools/forge_check.py --regression` | 256 passed (37.6 s) |
| `python -m pytest -m "not expensive" -q -n 2 --dist loadfile` | 5 failed, 10010 passed, 171 skipped (310 s) |
| `python tools/certification/core_certificate.py --verify` | FAILED: certified `39d43456`, HEAD `5d73e8f5`; 15 files in 5 areas (certification_control, execution_trust, harness, inference_admission, runtime_dependencies) |

FAST failures, classified:
- `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` — certificate drift (OD-3); the only
  failure that reflects the tree.
- `tests/test_mutation_workspace.py::{test_local_telemetry_is_outside_manifest_and_cannot_verify_as_receipt,
  test_mid_walk_failure_still_reports_entries_already_scanned}` — environment: run as root, so the read-only
  directory these tests build does not raise `PermissionError`.
- `tests/foundations/test_escrow_isolation.py::{test_the_isolated_deployment_reports_exactly_what_it_established,
  test_the_leak_detector_catches_a_planted_partial_copy}` — environment: inside the namespace only the interpreter
  prefix is mounted, and a uv venv keeps `cryptography` outside it. Both pass with the system interpreter
  (CPython 3.13.16): `python -m pytest tests/foundations/test_escrow_isolation.py` 2 passed.

Observed on 2026-10-12 with CPython 3.13 and a shallow clone (`2d0fa6c3`): 27 FAST failures, of which 18 came from
the shallow history and 6 from the V4 deep API surface gaining `format`/`format_map` (str enums) and
`add_note`/`with_traceback` (exceptions) under 3.13; the same tests pass on 3.12. The V4 surface is therefore
interpreter-dependent. The owner's local interpreter is 3.14 (REMEDIATION_2026-10-13); 3.14: NOT RUN here (OD-2).

## 2026-10-16 — Local Assurance performance investigation (read-only; documentation only)

Record: `docs/work/LOCAL_ASSURANCE_PERFORMANCE_INVESTIGATION_2026-10-16.md` (Arabic, with an English summary).
Base: `main` at `e193e573`.

No source, test, certified file, threshold, workflow or certificate was changed. Nothing was run on the
owner's WSL host. FULL_LOCAL_ASSURANCE: NOT RUN. Certificate: NOT GENERATED.

Findings (details and sources are in the record):

- **Late refusals.** Four full local runs between 2026-10-07 and 2026-10-15 were refused only after every
  execution gate had passed. Three were refused by skip admission, one by the runner interpreter at
  `certificate_generation`. Each was detectable with existing tools within 16 s to 20 min of the start.
- **Worker flags.** `run --workers 4 --mutation-workers 4 --formal-pytest-workers 2` ran in 2h42m–2h47m on the
  WSL host (Pass 13; PR #119). Three later runs used the default flags (`--mutation-workers 2
  --formal-pytest-workers 1`; their recorded commands carry no worker flags): 05522b59 took 3h27m, 5847345e
  3h33m and 0bc8b1cb 3h33m. The documented `run` command carries no worker flags.
- Facts and line references were re-checked against `main` at `91b44e22` (after PR #146).
- **CI mutations job.** The `mutations` job in `tests.yml` runs all 284 Formal mutations in one job. It cannot
  finish inside GitHub's 6 h job limit; PR #143 records the cancellation.
- **PR #145 check.** The suggested check `(cd /tmp && .forge/venvs/3.12/bin/python ...)` uses a relative
  interpreter path after `cd`. It exits 127 whatever the environment.

Commands. These ran in a 2-vCPU Linux sandbox (CPython 3.12.3, pytest 9.1.1, pytest-xdist 3.8.0) and are not
certification evidence.

- `python -X utf8 tests/mutation_guards.py <scratch> G1b G2a G6a G12c`
  -> exit 0, 580.1 s, 4/4 killed.
- `python -X utf8 tests/mutation_guards.py --pytest-workers 2 <scratch> G1b G2a G6a G12c`
  -> exit 0, 379.3 s, 4/4 killed, same failure counts as the serial run.
- `python -m tools.certification.mutation_v4_runner --scratch <s> --ids <V4 shard 0 of 8> --log <l>`
  -> exit 0, 273.6 s, 85/85 entries reached their declared verdict, CONTROL GREEN.
- `python benchmarks/trust_hardening/audit/mutations.py --json <j> --scratch <s>`
  -> exit 0, 47.4 s, 20 killed / 0 survived / 0 invalid.
- `python -X utf8 -m pytest <48 Formal TARGETS> -q -p no:randomly -p no:cacheprovider --continue-on-collection-errors`
  in a seed copy, with the child environment of the production harness -> exit 0, 1140 passed, 1 skipped,
  127.43 s.
- `core_certificate.production_registry_identity(root)` -> OK (456 evidence-code files), 15.8 s.
- `python -m tools.certification.core_certificate --verify --certificate certification/current_core_v2.json`
  -> exit 1, as expected: the certificate binds `05522b59` and HEAD is `e193e573`. Used for timing only
  (10.4 s).

Failed approach: a bytecode cache.

- A checked-hash pyc cache in an external `PYTHONPYCACHEPREFIX` does not speed up mutation children. Importing
  718 `engcore` modules took 4.89–4.93 s with it, against 4.05–4.26 s with no pyc. Timestamp pycs took
  2.72–2.75 s but are unsafe.
- `compileall -j 0` with `-X pycache_prefix` wrote 720 pyc files into the copied tree, because its forkserver
  workers do not inherit the prefix.
- Do not pursue it.
- `python tools/forge_check.py --changed` (sandbox, `PYTHONDONTWRITEBYTECODE=1`): both files classified
  `doc_only`; 85 passed in 9.88 s; exit 0.
- After merging `main` at `91b44e22`: `python tools/forge_check.py --changed --base origin/main`: both files
  classified `doc_only`; 158 passed in 11.87 s; exit 0.

## 2026-10-16 — Recent-branch documentation reconciliation

Copied the previously unmerged historical check record from `docs/main-check-2026-10-13` and the performance-investigation record from PR #147 into a documentation-only integration branch based on `36306da51`. These remain historical execution records. Scientific models, certificate identities, workflows and acceptance thresholds are unchanged by this reconciliation. TESTS: NOT RUN in this integration session. HARDENED RECERTIFICATION: NOT RUN. No claim of certified or passing CI is made.

## 2026-10-16 -- Open problems pass: review MINORs, Windows FAST triage (fix/open-problems-2026-10-16)

**Scope.** The user asked for "all current problems" to be solved. Worktree `D:/forge-open-problems`, base `origin/main`
`36306da5` (PR #148 merged). Commits `0bc9a892`, `7b84dce1`, `b12dc7c7`; merged with `origin/main` `062e1153` (PROGRESS-only conflict) and pushed for a PR on 2026-10-17. No recertification.

**What is owner-only and was not touched:** CI on `main` and on PRs fails in ~6 s with no runner (Actions billing),
OD-3 recertification of `main` (`test_the_certificate_describes_this_tree` and
`test_the_certificate_records_the_v1_relationship_truthfully`), branch-protection governance (OD-1), and the open
owner decisions listed in ACTIVE_PLAN.

**Fixed (each with a reproducer that fails on `36306da5`):**
- `uq.budget.UncertaintyBudgetReport` built directly could be empty (UNKNOWN read as zero) or carry an aggregate
  its components do not reproduce. `__post_init__` now re-aggregates and refuses both (landing-pass MINOR).
- A NOT_ASSESSABLE applicability made `assess_claim` raise `KeyError: 'applicability_unassessable'` in
  `explain()` (missing `_GAP_KIND` entry; found by the new test). Its gap was also labelled CAPABILITY_MISSING. The
  compiler now marks that repair (`detail.applicability = not_assessable`); gap analysis reports
  MODEL_APPLICABILITY_UNKNOWN (still blocking, verdict unchanged); the next step stays EXTEND_CAPABILITY.
- `operating_rating.assess_operating_ratings`: any-of composition is now declared in the docstring (behaviour
  unchanged).
- `tools/certification/ownership.py` refuses: inventory names escaping the root; a Git top level other than the
  root; a linked `.git` (symlink or junction); a `.git` directory whose Git directory is elsewhere; a `.git` file
  whose Git directory does not name the checkout back (relative back-references are read against the Git directory;
  `core.worktree` only from the repository's own config). A tracked file replaced by a directory is refused, with
  a case-folded comparison.
- `tools/certification/mutation_workspace.snapshot`: on Windows `os.scandir` reports `st_nlink == 0`, so every seed
  was refused as "links or special files". It now re-reads with `os.lstat`. Junctions are recorded as special and
  never walked (on 3.11 via reparse tag `0xA0000003`).
- `tests/foundations/test_authority_integrity.py` read MCP sources with the locale codec (cp1252 decode error on
  Windows); it now reads UTF-8.

**Not fixed (recorded):**
- `engcore.mind` `authority_result_id` is still an unchecked string. Binding it to a result record is a design
  decision, and nothing consumes MindState as a verdict today.
- Review I-5: any-of is declared, not enforced. A `composition` field would change the mission record schema
  (owner decision).
- Review N-4 (pre-existing): `ownership.copy_ignore` / `mutation_v4_runner.populate` never act on `owned.refused`.
  Copytree follows junctions; clean-tree gates probably cover it (not confirmed).
- Review N-5: two `is_link` definitions (`ownership` vs `core_certificate`); the case-fold skip can over-skip on a
  case-sensitive filesystem. Both fail safe.
- The remaining Windows FAST failures are by design or environment (see below).

**Windows FAST failure triage** (150 failures + errors at `7b84dce1`, down from 179 at `36306da5`; 0 new):
- POSIX-only by design: `fcntl` (authority ledger, durable campaign, battery blind readiness), `os.geteuid`
  (escrow), `os.killpg`, and the Linux child-subreaper (the mutation workspace refuses to run elsewhere).
- Environment: symlink creation without the Windows privilege (WinError 1314); escrow subprocess handshake;
  executable-bit checks on the interpreter; `.gitignore` CRLF reported dirty by `local_assurance`.
- Expected certification staleness (OD-3), plus py3.14-only deep-surface byte differences.
- Baseline caveat: the `36306da5` Windows run overlapped my first edits, so its tree-clean freeze failures (and
  one offline-revalidation race) are not fixed by this branch.

**Tests run** (Windows: `.venv` CPython 3.14.2; Linux: WSL Ubuntu CPython 3.12 from
`~/forge-cons-assure-2/.forge/venvs/3.12`, read-only, on a native clone `~/forge-open-problems`):
```
# Windows FAST, pristine 36306da5 (worktree D:/forge-open-problems before edits; edits began mid-run)
PYTHONPATH='<wt>\src;<wt>' TMP=D:\pft\op-fast .venv/Scripts/python.exe -m pytest -m "not expensive" -q -n 4 --dist loadfile -p no:cacheprovider --basetemp=D:/pfb/op-fast -rfE
#   157 failed, 10548 passed, 204 skipped, 22 errors
# Windows FAST, 7b84dce1 (same command, D:/pft/op-fast3)
#   128 failed, 10626 passed, 204 skipped, 22 errors; failure-id diff vs baseline: 0 new, 29 gone
# Linux FAST, clean committed 7b84dce1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=~/forge-open-problems/src:~/forge-open-problems python -m pytest -m "not expensive" -q -n 4 -p no:cacheprovider
#   2 failed, 10802 passed, 156 skipped; tracked tree clean afterwards
#   failures: test_the_certificate_describes_this_tree, test_the_certificate_records_the_v1_relationship_truthfully
# Linux, pristine 36306da5, certificate + freeze modules: the same 2 failed, 73 passed, 1 skipped
# Linux, b12dc7c7, targeted (new tests, ownership, mutation workspace, change impact, formal xdist, freeze, certificate, tests/claims, tests/uq)
#   2 failed (the same certificate pair), 1379 passed, 1 skipped
# Windows, b12dc7c7, targeted (new tests, ownership, change impact, tests/claims, tests/uq)
#   2 failed (symlink privilege, baseline), 1104 passed, 1 skipped
# Reproducers on pristine 36306da5: 16 of 22 first-round tests fail, 6 controls pass
```
- **Flaw checks.** `D:/pf/op/mutate_check.py` applies 10 deliberate flaws one at a time (linked .git, nlink
  fallback, junction, relative back-reference, case-fold, foreign worktree, empty UQ, gap relabel, escaping names,
  tracked-dir refusal), runs the tests that name each, and restores the bytes (SHA-256 checked): 10/10 caught. A
  global `core.worktree` mutant (N-1) is also caught.

**Scientific review** (`forge-scientific-review`, read-only):
- First pass: CHANGES REQUIRED (I-1 linked `.git` bypass and I-2 untested snapshot change, both MEDIUM; I-3..I-6
  LOW). All except I-5 were fixed.
- Second pass: PASS, with N-1..N-5 LOW. N-1 (global `core.worktree` vouches for a checkout) was fixed and tested,
  and N-2/N-3 were tested; N-4 and N-5 are recorded above.

**Failed approaches (do not repeat):**
- WSL pytest on a Windows git worktree: its `.git` file holds a Windows path, so commit identity is unavailable
  and replay/ownership tests fail. Use a native WSL clone.
- `stat.IO_REPARSE_TAG_MOUNT_POINT` exists only on Windows; use the constant `0xA0000003`.
- A bash heredoc again turned `\n` inside a generated Python string into real newlines; write such files with the
  editor.

**RECERTIFICATION_REQUIRED (OD-3).** The touched src/tools files are pinned (`certification/current_core_v2.json`),
and `main` already needs recertification.

## 2026-10-17 -- Engineering Runtime V1, Phase 1: solver-interoperability defects (fix/engrt-v1-phase1-interop, local only)

Branch `fix/engrt-v1-phase1-interop`, worktree `D:/forge-engrt-p1`, base `origin/main` `de7527fd`. Uncommitted, not
pushed or merged; no certificate generated, no hardened run. Defect fixes only (no new capability foundation), so the
Battery 1RC active-epic policy is respected. Pristine comparison worktree: `D:/forge-engrt-base` (detached `de7527fd`).
Logs: `D:/engrt-logs/`.

**Confirmed defects (each reproduced before the fix; the reproducers fail on `de7527fd`):**
1. Orchestration checkpoints crossed solver boundaries (`execution/orchestration/runner.py`, `advanced_runner.py`).
   `CheckpointReference` named no solver and `current_checkpoint` survived fallback, so solver B was resumed from
   solver A's state. A FAILED/DIVERGED attempt's checkpoint replaced the last good one. On ERROR_TARGET_SATISFIED the
   report carried another solver's diverged checkpoint (or a rejected refinement's) as `final_checkpoint`.
   Fix: `CheckpointReference.solver_id` (trailing, default "") and `adopt_checkpoint` / `resume_owner` /
   `resume_point_for` in `checkpoint.py`:
   - a checkpoint resumes only the solver that produced it;
   - adoption is an allow-list (converged, cancelled), so failed, diverged, planned and running attempts never supply
     a resume point;
   - an unbound caller checkpoint is refused with ValueError, never turned into a silent cold start;
   - a caller checkpoint bound to S runs no other solver, and the skip is recorded;
   - attempt records carry only adopted checkpoints;
   - ACCEPT reports the accepted attempt's own checkpoint, or None;
   - `run_plan` checks `backend.solver_id`, as the adaptive runner already did.
2. A SUM fan-in over an offset unit was unit-dependent (`scientific/multiphysics/graph.py`). Two 300 K sources summed
   into a port declared in degC delivered 53.7 degC (326.85 K); declared in K, the same sum was 600 K. It is now
   refused at graph construction (`is_ratio_scale`). MEAN/MIN/MAX are affine-invariant and SUM of difference units
   is unit-safe, so both stay admitted.
3. Interval fan-in and iterate relaxation overstated coverage (`execution/multiphysics/transfer.py`, `relaxation.py`).
   The combined bounds kept each source's own level, so 20 sources at 0.95 reported 0.95. They now report the union
   bound 1 - sum(1 - c_i), or None when a level is undeclared or the bound is <= 0. Separately, a STANDARD width on an
   offset target unit aborted because it was stated as a degC point; it is now stated in the ratio-scale base unit.
   (Raised by the scientific review, then reproduced.)
4. `ExternalSolverParticipant` restored another provider build's snapshot (`execution/multiphysics/external.py`).
   A `thermo@1.0` checkpoint was accepted by a `thermo@2.0` participant with the same id, and the record did not name
   the build. The participant now:
   - seals each token with the canonical-JSON identity scope and a nonce from its own issue registry;
   - binds the scope into `CheckpointRecord.provider_state_id`;
   - refuses another build, a relabelled record, a bare token and a wrapper it did not issue;
   - refuses a session whose identity changed, before or inside initialize/advance/snapshot/restore.

   No in-tree caller used this adapter. The first runtime test of it (implicit coupling of two MOCK sessions with
   per-iteration rollback) is in the new test file.

**Investigated, not defects (or not fixable as a defect fix):**
- Multiphysics runtime rollback: implicit coupling and event alignment already require deterministic checkpoint/restore
  on every participant and re-checkpoint after restore. A NaN residual cannot satisfy a criterion, because non-finite
  magnitudes are refused at construction.
- Provider qualification never gates a run (`providers/health.py`: `executable` includes UNQUALIFIED). This is by
  design and stated ("available is not qualified"); gating runs on qualification is an owner policy decision.
- An unpinned provider binding accepts any build of its version (`system_runtime/executor.py::_check_providers`).
  That is the request's own semantics. Build drift between preflight and execution is a TOCTOU limitation; pinning
  `provider_digest` closes it.
- `providers/compare.py` does not compare `problem_digest`. Provider-specific problem digests never match across
  input formats; a declared problem-equivalence binding would be a new capability, not a defect fix.
- The electrothermal fixed point accepts a mid-run solver change (`systems/electrothermal/coupled.py`). The final
  residual is still the residual of the last solver's own map, and every binding is recorded.

**Remaining limitations:**
- `CallbackParticipant`-based provider adapters (`providers/pybamm/forge_pybamm/coupling.py`,
  `coupling/adapters.py::provider_participant`) bind no provider build into their checkpoints.
  `provider_participant.restore` does not compare its token with the record digest; only the runtime's re-checkpoint
  catches that, and only for deterministic_restore participants.
- The ngspice cross-check identity is a version banner, with no executable digest and no qualification.
- `run_plan` has no problems channel (that would be a schema change).
- The adaptive runner carries refinement level across fallback; this is a discretization request, not solver state.
- The `_ScopedSnapshot` registry is per participant object and weak, so a checkpoint restores only into the
  participant that issued it, and only while some holder keeps it alive.

**Scientific review** (`forge-scientific-review` / `forge-scientific-reviewer`, read-only, static):
- Pass 1: CHANGES REQUIRED.
  - I-1 HIGH: unbound caller checkpoint became a silent cold start.
  - I-2: accepted result carried a rejected attempt's checkpoint.
  - I-3 HIGH: interval coverage overstated.
  - I-4: build binding relied on the editable record string alone.
  - I-5..I-7 LOW.
  - All fixed; I-8 recorded above.
- Pass 2: CHANGES REQUIRED (N-1 relaxation coverage and width, N-2 identity drift in advance, N-3..N-6 LOW). All fixed
  and tested.
- Pass 3: CHANGES REQUIRED.
  - F-1: deny-list adoption.
  - F-2: identity drift inside a call.
  - F-3 LOW: unauthenticated seal.
  - F-4 LOW: dropped problem text.
  - F-5 LOW: pre-existing refinement carry-over.
  - F-1..F-3 fixed and tested; F-4 documented in code; F-5 recorded above.
- Pass 4 (confirmation): CHANGES REQUIRED. F-1, F-2 and F-4 confirmed; F-3 residual MEDIUM: the registry bound
  only digest and slot, so a payload re-wrapped under an issued digest, slot and nonce restored. Fixed as the
  reviewer prescribed: the registry holds the issued snapshot object (`WeakValueDictionary`, bounded by live
  checkpoints) and restore requires identity. The reviewer's counterexample is now a test and is refused. No
  fifth review pass ran (the reviewer agent was no longer available in the session), so this fix is verified by
  its test only.

```text
# final tree, new tests + runtime neighbours (orchestration, external, fan-in, stateful runtime, big9 runtime,
#   conservation history): 115 passed; forge_check --regression: 256 passed in 10.8 s
# (the F-3 registry change came after the last FAST run; it touches only ExternalSolverParticipant)
# targeted (new tests, before F-3): 63 passed
TMPDIR=D:/ftmp PYTHONPATH='D:/forge-engrt-p1/src;D:/forge-engrt-p1' .venv/Scripts/python.exe -m pytest \
  tests/execution/orchestration tests/test_external_participant_checkpoints.py tests/test_multiphysics_fan_in_units.py -q
# reproducers copied into the pristine worktree D:/forge-engrt-base and run there:
#   orchestration module: collection error (helpers absent); external + fan-in: 20 failed, 8 passed (controls)
python tools/forge_check.py --regression --workers 4            -> 256 passed in 15.9 s
# 109 interop-related test files, -m "not expensive" -n 4 (before the review-round fixes):
#   11 failed, 3284 passed, 12 skipped -- all 11 in test_authority_integrity / test_local_assurance (also on baseline)
# FAST, Windows venv 3.14, -m "not expensive" -q -n 4 -p no:cacheprovider --basetemp=D:/fbt-engrt -rfE
#   baseline de7527fd : 128 failed, 10633 passed, 204 skipped, 22 errors in 431 s (150 failing ids)
#   fix (after review passes 1-3): 130 failed, 10687 passed, 204 skipped, 22 errors in 447 s (152 failing ids)
#   only in fix: test_core_freeze_manifest::test_the_tree_is_core_freeze_v1,
#                test_core_freeze_v3_manifest::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks
#     -> both are the verifier's `tree.clean` check listing the uncommitted files (baseline tree is clean)
#   only in baseline: none
#   V4 deep-surface failures: the built-vs-pinned surface diff is byte-identical on fix and baseline (859 entries,
#     Python 3.14 builtin-method artifacts), so it is environmental
# electrothermal + REAL ngspice (WSL /usr/bin/ngspice, version 42), no marker filter:
#   tests/test_heterogeneous_ngspice.py tests/test_cross_solver_consensus.py tests/test_ngspice_version_probe.py
#   tests/test_electrothermal_vertical.py tests/test_min_foundation_electrothermal.py
#   tests/test_coupled_transport_admission.py tests/test_stateful_multiphysics_runtime.py
#   tests/test_multiphysics_conservation_history.py tests/test_big9_review_runtime_fixes.py
#   tests/test_field_composition.py tests/mcp/test_problem.py      -> 357 passed, 0 skipped in 20 s
#   (these guard the existing electrothermal/ngspice route; they do not traverse the changed interop code, which
#    is exercised only by in-process MOCK sessions)
# SCIENTIFIC tier (-m "not campaign"): NOT RUN
```

**Failed approaches (do not repeat):**
- Red-checking new tests by pointing `PYTHONPATH` at a pristine worktree does not work: `pyproject.toml` sets pytest's
  `pythonpath`, so pytest imports the CURRENT worktree's `src` regardless. Copy the tests into the pristine worktree
  and run them there.
- Long bash heredocs again failed (`unexpected EOF`); patch scripts written with the editor work.
- `forge_check.py --changed` with a touched `scientific/` file selects the whole FAST tier (more than 10 min on
  Windows), so run FAST directly instead.

**RECERTIFICATION_REQUIRED (OD-3).** All touched src files are pinned in `certification/current_core_v2.json`:
orchestration, multiphysics external/transfer/relaxation, and scientific multiphysics graph. The new orchestration
test falls under a pinned glob. No touched file is in the frozen API snapshot. `main` already needs recertification.

**Committed (owner direction, local only, not pushed):** `04b12344` on `fix/engrt-v1-phase1-interop`. With the
tree clean, the two fix-only FAST failures (`test_core_freeze_manifest::test_the_tree_is_core_freeze_v1`,
`test_core_freeze_v3_manifest::test_the_v3_contract_is_superseded_and_its_verifier_says_which_checks`) pass:
`pytest <those two ids> -q` -> 2 passed in 37.8 s. The fix branch's FAST failure set therefore equals the
baseline's.

## 2026-10-17 -- Engineering Runtime V1 Big Rocks (build phase; feat/engrt-v1-big-rocks, pushed, no PR)
- Pushed 2026-10-17 on owner instruction. Branch only: no PR, no merge, no certificate.
  - `origin/feat/engrt-v1-big-rocks` = `23fb2bb1c1f9ebd5a12f7cad4f202af4e64e51ee`.
  - `origin/fix/engrt-v1-phase1-interop` = `423fb46714114d2a5aa2208804e96a65024c28e2`.
  - Both refs were checked against `git ls-remote`.
- Also pushed later on 2026-10-17, on owner instruction: `origin/fix/engrt-v1-callback-checkpoint-identity` =
  `debce509091949987fd51f387e5a0d4342772b1d`, made by another session. Pushed without upstream tracking, so that
  session's worktree is unchanged.
- Everything BR1-BR22 claims is still IMPLEMENTED / UNVERIFIED. The push runs no tests. The 16 pinned files the
  branch changes stay UNCERTIFIED until OD-3.

Owner direction (2026-10-17): build the Big Rocks first.
- No pytest, FAST, SCIENTIFIC, regression, mutation, benchmark or hardened run until the owner authorizes one.
  Only `py_compile` and import checks.
- Tests are written but NOT executed.
- Logical local commits; no push or PR.
- Owner decision on the active-epic policy: Big Rocks are runtime/platform engineering (no new tracked scientific
  capability, no ledger change). Anything adding new physics, models or a ledger capability stops for owner approval.

Branch `feat/engrt-v1-big-rocks` (worktree `D:/forge-engrt-br`), stacked on `fix/engrt-v1-phase1-interop`
`423fb467`. The linked session "Bind provider builds into adapter checkpoints" owns `coupling/adapters.py`,
`providers/pybamm/**`, `execution/multiphysics/external.py` and `participant.py`; this branch does not touch them.
Deferred tests and checks: [DEFERRED_VALIDATION.md](DEFERRED_VALIDATION.md).

### BR1 -- adaptive coupling-window control (`af7ea219`, tests NOT RUN)
- `scientific/multiphysics/plan.py`: `WindowControlPolicy` on `CouplingPlan` (optional, trailing).
  - Fields: `minimum_window` (required, no default), `reduction_factor`, `max_subdivisions`, and an optional
    `divergence_factor` (implicit only).
  - Serialized only when set.
  - Admission requires deterministic checkpoint/restore on every participant.
- `execution/multiphysics/runtime.py`:
  - `CouplingWindowNotConverged` (a subclass of `MultiphysicsExecutionError`) is raised for an iteration limit,
    for divergence, and for a participant's internal non-convergence.
  - `_controlled_window` rolls back and retries only numerical failures.
  - `_diverging_edge` implements the early divergence stop.
  - The log is surfaced in `final_outputs["_window_control"]`.
- Tests written: `tests/test_multiphysics_window_control.py` (policy bounds, serialization identity, admission,
  rollback accounting, exhaustion, refusal-not-retried, implicit subdivision, ITERATION_LIMIT never relabelled,
  divergence). Static checks only: py_compile, import of every test import (none missing), `git diff --check`.
- UNCERTIFIED: `plan.py`, `runtime.py` and both `__init__.py` files are pinned in
  `certification/current_core_v2.json`.

### BR2 -- joint IQN-ILS coupling acceleration (`35d8f557`, tests NOT RUN)
- `scientific/multiphysics/plan.py`: `RelaxationKind.IQN_ILS` and `RelaxationPolicy.iqn_columns` (1..50, serialized
  only for IQN). Admitted for JACOBI semantics only.
- `execution/multiphysics/relaxation.py`: `RelaxationController.relax_joint` takes one quasi-Newton step over the
  concatenated interface vector, with per-edge residual-RMS scaling and a constant-relaxation fallback. History
  resets every window. `propagate_uncertainty` returns UNKNOWN for IQN.
- `execution/multiphysics/runtime.py`: the Jacobi path calls `relax_joint`; IQN iterations record no scalar factor.
- Tests written: `tests/test_multiphysics_iqn_ils.py`. Expected values are hand-computed:
  (290,290) -> (285,290) -> (280,288) -> (300,300) for x = 2y - 300, y = x.
- Static checks only: py_compile, test-import resolution, an AST name-resolution check of the touched modules.

**Failed approach (do not repeat):** the first BR2 draft was per-edge IQN inside the serial Gauss-Seidel path. Working
the algorithm by hand showed each edge's secant history sees a map the other edge's update keeps changing, so it is
not a sound method there. Joint IQN over the Jacobi interface vector replaced it.

### BR3 -- coupling numerical-error accounting (tests NOT RUN)
- New `execution/multiphysics/numerical_error.py`: `assess_coupling_numerical_error(run)` derives an accounting from
  an existing run record and leaves the record unchanged.
  - Statuses: QUANTIFIED (the mapping bounds), ESTIMATED, UNQUANTIFIED, UNBOUNDED.
  - ESTIMATED is the q/(1-q) r_k iteration error of a converged plain fixed-point window. It is not a bound and is
    never summed into the bound.
  - UNQUANTIFIED: explicit splitting, accelerated or single-iteration windows.
  - UNBOUNDED: windows that ended at their iteration limit.
  - Verdict: BOUNDED / ESTIMATED / INCOMPLETE / UNBOUNDED / NO_COUPLING.
- Why derived rather than recorded: folding these sources into `final_outputs["_coupling_error"]` would change the
  serialized identity of every existing run. Whether to record it in runs is a later, explicit versioning decision.
- Gap this addresses: the run's `coupling_error_bound` sums mapping error only, so it read as the whole coupling error
  of runs that also staggered explicitly or stopped at an iteration limit. Nothing in `src` consumes that bound
  today.
- Tests written: `tests/test_multiphysics_numerical_error_accounting.py`. Static checks only.

### BR4 -- opt-in splitting-error estimate by coupling-window refinement (tests NOT RUN)
- New `execution/multiphysics/splitting.py`: `estimate_splitting_error(build, coupling_window=, run_id=,
  run_kwargs=, quantities=, levels=3 | 2 + declared order and basis)`.
  - Re-executes the explicit problem at dt, dt/2 (and dt/4) and applies Richardson extrapolation to named scalar
    outputs at the horizon end.
  - Three levels observe the order; two levels need a declared order with its basis.
  - A quantity outside the asymptotic range stays UNQUANTIFIED.
  - Refinements may change only the coupling window (graph, plan and end time are checked).
  - The estimate is bound to `canonical_digest(base_run.to_dict())`.
  - Cost: 3x the base run (two levels) or 7x (three levels).
- `numerical_error.assess_coupling_numerical_error(run, splitting=)` accepts the estimate only for that exact run.
  It turns the open splitting source into per-quantity ESTIMATED or UNQUANTIFIED sources, never a bound.
- Tests written: `tests/test_multiphysics_splitting_estimate.py`. The exact model problem is hand-derived: a right
  Riemann sum with x = 0.625, 0.5625, 0.53125, observed order 1, and an estimate equal to the true error 0.125.
- Static checks only. No certified file was touched.

### BR5 -- opt-in concurrent participant advance in Jacobi iterations (tests NOT RUN)
- New `execution/multiphysics/concurrency.py`:
  - `ConcurrentAdvancePolicy(participants, max_workers, basis)` declares thread-safety per participant, with a
    basis; it is never inferred.
  - `advance_in_plan_order` runs undeclared participants alone and first, and declared ones in a thread pool. Results
    are keyed in plan order, and the first failure in plan order is raised after all workers join.
- `runtime.py`:
  - `MultiphysicsRuntime(..., concurrency=)` and `from_factory_registry(..., concurrency=)`.
  - Admitted for JACOBI only.
  - The Jacobi loop prepares inputs in order and applies results in order.
  - `final_outputs["_concurrency"]` is written only when a policy is set.
- Why a runtime option rather than a spec field: thread-safety is a property of the executable participant, not of
  the scientific spec. A `ParticipantSpec` field would move every graph fingerprint, and `participant.py` is owned by
  the linked adapter session.
- Tests written: `tests/test_multiphysics_concurrent_jacobi.py`. Static checks only.

### BR6 -- coupling numerical error as a condition on the claims NUMERICAL channel (tests NOT RUN)
- New `claims/coupling_numerical.py`: `condition_numerical_uncertainty(study_record, run, splitting=None)`.
  - The input is a `uq_studies` refinement record. It is re-derived through `numerical_uq.estimate_from_dict`, and
    its level 0 must be `<run_id>~numerical~0`.
  - The coupling assessment is computed from the `MultiphysicsRunRecord` inside the call.
  - The study's NUMERICAL record passes unchanged only when the run has no coupling edge, or every coupling source
    is quantified as exactly 0. Otherwise the channel becomes UNKNOWN: estimates, open sources, non-zero bounds and
    incomplete windows all veto.
  - It never quantifies or widens. The vetoed record reaches `claims.uncertainty.transport` as an UNKNOWN NUMERICAL
    channel.
- Static scientific review (read-only agent; the review skill and reviewer agent type were unavailable):
  CHANGES REQUIRED. Fixed in `e4b5809c` and `33cefed8`:
  - F1 BLOCKER: caller-declared coverage was an authority leak. Removed.
  - F2 HIGH: binding by run_id only, and a hand-built assessment. The assessment is now computed from the run and
    stamps `run_digest` and `coupled`.
  - F3 HIGH: the NUMERICAL record was not tied to the run. Now re-derived and level-0-bound.
  - F5 MEDIUM: refused windows were assessed as converged. Now UNBOUNDED.
  - F6 MEDIUM: BR4 invented a zero for identical levels. It now applies the round-off floor and reports
    UNQUANTIFIED.
  - F7: tests rewritten.
  - F8: the claims -> execution edge is new and intentional (the architecture tests allow it).
- **Owner decisions (review F4, not fixed):**
  - Conditioning is opt-in. Making it mandatory for every claim built on a coupled run would change the NUMERICAL
    verdict of the existing electrothermal capability (`CouplingEvidence`). No claims capability yet produces a
    `MultiphysicsRunRecord`.
  - Capability-declared coverage (a `RefinementStudy` stating which coupling kinds its ladder refines, bound by the
    plan digest and checked against the ladder) is a design item. Iteration error is not coverable by today's
    integer-count ladders.
- **Failed approach (do not repeat):** a first BR6 design widened the claim interval by the coupling bound. Mapping
  bounds are relative FIELD norms, not QoI errors, so widening would invent a propagation rule. A second draft let
  callers declare coverage, which was the review's BLOCKER.
- Confirmation review: F1, F2, F5, F6 and F8 fixed; F4 open as an owner decision.
  - R1 MEDIUM: the binding check read `runs[0]` while the re-derived estimate carries its own level run ids. Fixed:
    estimate levels, study runs and `<run_id>~numerical~k` must agree, values included. Two tamper tests were added.
  - R2 LOW, recorded: the study-to-run binding is a run-id string convention. A digest link needs `uq_studies` to
    record the reported report's digest, which belongs to the same owner decision as F4.
- Owner decision (2026-10-17): coupling conditioning stays OPT-IN for now. F4 (mandatory conditioning, including the
  electrothermal `CouplingEvidence` path) remains an open owner decision; R2 (digest link) goes with it.

### BR7 -- nonlinear robustness: declared method chain and parameter continuation (tests NOT RUN)
- New `numerical/robust.py`. It composes `NumericalProvider.execute` only: no new algorithm, no new acceptance rule.
  - `solve_with_method_chain(provider, problem, methods)`: the same problem for every method, each starting from the
    declared initial values. Every attempt is recorded, and refusals propagate. This replaces callers hard-coding
    `lm` (the `hybr` false refusals in project memory) with a declared, recorded chain.
  - `solve_by_continuation(provider, family, method, initial_step=, minimum_step=, max_steps=)`: warm starts come only
    from converged outputs. A failed step halves the increment and is never reused. The accepted problem must equal
    `family(1)` except for its initial values.
- Tests written: `tests/numerical/test_robust_nonlinear.py`, using a deterministic fake "basin" provider plus one
  real `SciPyRootProvider` case. Static checks only.
- Not done: no caller uses these yet. The heater KVL `root_method="lm"` workaround is unchanged; migrating it is a
  separate change to a domain file.

### BR8 -- declared hybr -> lm root-method chain for the heater KVL (tests NOT RUN)
- `domains/electrical/heater_circuit.py`: `root_methods` (opt-in chain) and `solve_with_attempts`.
  - The chain uses `numerical.robust.solve_with_method_chain`, with the same problem, initial current and settings
    for every method.
  - The chain is named in the identity only when declared.
  - Without a chain, identity, operator digest and records are unchanged byte-for-byte.
- **Why the workaround caller was not migrated:** the only `root_method="lm"` caller is the test fixture
  `tests/multiscale_reference.py`. Migrating it changes its declared participant solver version (`lm`), its
  configuration identity (`"root_method": "lm"`), and its last-bit results wherever hybr converges first.
  Identical evidence (owner requirement) and migration are mutually exclusive; owner decision pending.
- Tests written: `tests/domains/electrical/test_heater_root_chain.py`.
  - Exact-equality invariant over a 200-state sweep: the chain's result equals the accepted method's own result,
    and the chain never fails where either method alone succeeds.
  - A SciPy-version-dependent check that the sweep exercises the hybr false refusal.
- Owner decision (2026-10-17): `tests/multiscale_reference.py` stays on `root_method="lm"`, so its evidence is
  unchanged. The hybr->lm chain is available opt-in only.

### BR9 -- multi-timescale: opt-in macro-window rejection on fast non-convergence (tests NOT RUN)
- Gap: the macro-step loop rejected and shortened windows for slow-state change, threshold localization and
  representativity, but not when the fast execution failed numerically. A non-converging coupled fast run refused the
  whole multi-timescale run, even though a shorter macro window shortens the resolved fast window.
- What changed:
  - `multiscale/windows.py`: `MacroStepPolicy.retry_fast_nonconvergence`, default off and serialized only when on.
  - `multiscale/fast.py`: the typed signal `FastExecutionNotConverged`.
  - `multiscale/runtime.py`: rejection kind `fast_nonconvergence`, recorded as a `RefinementDecision` with subject
    `fast_execution`, within the existing divisor, minimum window and rejection bound. Other refusals are never
    retried, and no accounting counter is added.
- Static checks caught a defect before commit: the text patch had put the existing `@dataclass(frozen=True)`
  decorator on the new exception class. It was fixed, and an AST scan of all 21 changed src files found no other
  decorated exception class.
- Tests written: `tests/test_multiscale_fast_nonconvergence.py`, using the unchanged reference fixture with a
  fail-first-N fast system. Static checks only.

### BR10 -- composition-pack templates declare window control (tests NOT RUN)
- Gap: BR1 window control could not be reached from any declared system. The composition-pack
  `CouplingPolicyTemplate` materialized plans without it. IQN-ILS (BR2) was already reachable through the template's
  `RelaxationPolicy`.
- `compositionpacks/blueprint.py`: `CouplingPolicyTemplate.window_control`.
  - Optional, and serialized only when declared; the built-in packs' identity was confirmed unchanged by reading the
    object.
  - Carried into `materialize()`.
  - Refused at declaration where the plan would refuse it, and refused by `validate_against_blueprint` unless every
    participant is deterministically restorable. No built-in blueprint participant is today.
- Deliberately not exposed: BR5 concurrency. Packs may not pin executors, and thread-safety belongs to the executor.
- Tests written: `tests/compositionpacks/test_template_window_control.py`, using the real built-in electrothermal
  pack objects. Static checks only.

### BR11 -- step-size memory for adaptive coupling windows (tests NOT RUN)
- Replay check first: `assembly/replay.compare_runs` skips underscore-prefixed outputs and compares `window_count`
  and the plan fingerprint. A concurrent run (BR5, `_concurrency`) and a window-controlled run (BR1) therefore
  replay-compare correctly. No defect found.
- Gap closed (BR1's recorded remaining work): after a subdivision the next window jumped back to the full width, so
  a stiff stretch repeated fail -> halve -> succeed every window.
- What changed:
  - `WindowControlPolicy.growth_factor` (optional, in (1, 10], serialized only when set).
  - `runtime._next_window_width` remembers the width a subdivided or exhausted window was accepted at, and grows it
    by the factor per accepted window up to the nominal width. Event and input-change cuts do not shrink it.
  - Width changes are logged.
- Tests appended to `tests/test_multiphysics_window_control.py`. A hand-traced stiff case: 8 subdivisions over 2 s
  without memory, 4 with growth 2, every accepted window <= the 0.25 s stability limit, rollback still exact.

### BR12 -- event-aligned windows keep their own failure outcome (defect fix, tests NOT RUN)
- **Defect, found by static review and NOT reproduced by execution (build phase):** `runtime._window` re-ran an
  implicit window up to a terminal event and always labelled the result `EVENT_ALIGNED`.
  - With `fail_on_nonconvergence=False`, a re-run that ended at its iteration limit was recorded as a completed
    window: false convergence.
  - It also defeated BR1 retries and BR3 accounting.
  - Fix: only a completed re-run is `EVENT_ALIGNED`; otherwise the re-run's outcome is kept and the event is still
    recorded.
- Tests written: `tests/test_multiphysics_event_aligned_outcome.py`.
  - A diverging loop with a mid-window trip must record `ITERATION_LIMIT`.
  - Accounting must mark window 0 UNBOUNDED.
  - A converging control stays `EVENT_ALIGNED`.
- Also surveyed (D5 from the first provider survey), not changed:
  - `MultiphysicsAuthority` reports no provider executions unless given a `providers` callable, so external
    providers inside a coupled node are not checked against the request's bindings.
  - No production code constructs `MultiphysicsAuthority` or uses `ExternalSolverParticipant`.
  - Deriving provider records from participants would be new evidence semantics: owner decision.
  - The authority also fails every window whose outcome is not `converged`, including `explicit_completed` and
    `event_aligned`. That looks unintended for explicit coupling, and is recorded for the owner rather than changed
    in the build phase.

### BR13 -- mapping extrapolation and unverified mappings as open error sources (tests NOT RUN)
- Survey: `execution/multiphysics/mapping.py` handles coverage soundly. `ExtrapolationPolicy.REFUSE` refuses, and
  allowed extrapolation is recorded (`extrapolated_count`, `coverage_fraction`).
- Gap in BR3: `_mapping_sources` read only the budget, which covers declared round-trip/conservation residuals.
  - Extrapolated sites, and mappings with no declared verification, produced no source at all.
  - They now produce UNQUANTIFIED sources, read from the same last-iteration diagnostics the budget uses.
  - BR6 then vetoes the claims NUMERICAL channel for them automatically.
- Owner item (recorded, not changed): the coupling error budget names a round-trip L2 residual a `relative_bound`.
  A round-trip residual measures information loss, not the forward transfer error.
- Tests appended to `tests/test_multiphysics_numerical_error_accounting.py` (stand-in runs). A real field-mapped
  coupled run is deferred (DV-22).

### BR14 -- coupled nodes may not run unreported external providers (defect fix, tests NOT RUN)
- `system_runtime/authorities.py`, `MultiphysicsAuthority._untraced_external_providers`: a coupled node whose
  runtime contains `ExternalSolverParticipant`s fails unless every admitted provider identity (id and version) is
  among its reported provider records.
  - This extends the executor's existing "an unreported provider is untraceable" rule to the case it missed (D5).
  - No record is derived.
  - It is a no-op for every current caller (none uses external participants).
- The D5 owner item is narrowed to whether provider records should ever be derived from participants. That remains
  open; this change only refuses.
- Tests written: `tests/test_system_runtime_external_providers.py` (mock sessions in a real implicit runtime).
- **Recertification note (from this pass):** certified modules may not import uncertified ones (BR-15 rule). Two
  Big Rock edges need pinning at recertification: `execution/multiphysics/runtime.py -> concurrency.py` (BR5) and
  `claims/coupling_numerical.py -> execution/multiphysics/numerical_error.py` (BR6; claims/** is a certified glob).
  The BR14 edge `authorities.py -> execution/multiphysics/external.py` is already pinned.

### BR15 -- fallback solver routes start at their own refinement level (review F-5, tests NOT RUN)
- Surveyed and not changed:
  - `execution/multiphysics/admission.py` is a plan-compatibility and factory-coverage report that
    `from_factory_registry` already enforces; it is not an applicability gate, so there is no gap.
  - Concurrent multiscale representative windows were rejected for now: `_execute` mutates shared accounting and the
    result cache, and a macro attempt usually holds one representative window.
- Fix: `run_adaptive_plan` resets `refinement` and `refinement_level` on every solver-route change, so
  `max_refinements` counts per route. This was the pre-existing finding F-5 from the Phase 1 review.
- Test appended to `tests/execution/orchestration/test_checkpoint_routing.py`.
- Owner instruction (2026-10-17): keep building Big Rocks continuously, without asking between them.

### BR16 -- QR filtering of near-dependent IQN-ILS secant pairs (tests NOT RUN)
- `relaxation.RelaxationController._qr_filter` runs newest-first modified Gram-Schmidt over the scaled V columns. A
  column is dropped when its new direction is below `iqn_filter` times its norm, and W keeps the same columns.
- `RelaxationPolicy.iqn_filter` defaults to 1e-10 and is IQN-only (refused on other kinds), serialized with
  `iqn_columns`. Non-IQN identity was confirmed unchanged by reading the policy dicts.
- This closes the BR2 assumption "lstsq rcond is the only conditioning filter".
- Tests appended to `tests/test_multiphysics_iqn_ils.py`: parallel columns keep only the newest, and independent
  columns are all kept.

### BR17 -- stagnation detection for implicit coupling windows (tests NOT RUN)
- `WindowControlPolicy.stagnation_iterations` (implicit only, serialized only when set) and
  `runtime._stagnating`.
  - Progress is the largest edge residual normalized by its first-iteration value.
  - When the last n iterations do not improve on the earlier best, the window raises `CouplingWindowNotConverged`
    ("stagnating") and BR1 subdivision takes over.
  - The plan and the BR10 template refuse it on explicit coupling.
- This closes BR1's assumption that slow non-improvement went undetected.
- Tests appended to `tests/test_multiphysics_window_control.py`:
  - x = y + 5 (constant 5 K step) is rejected after 4 of 200 iterations.
  - A contracting loop is never flagged.

### BR18 -- opt-in under-relaxation of the electrothermal fixed point (tests NOT RUN)
- The integration target's loop (`systems/electrothermal/coupled.py::run_fixed_point`) is separate from the
  multiphysics runtime and had no relaxation.
- `FixedPointCouplingPlan.relaxation_factor` (in (0, 1), serialized only when declared).
  - The next sweep's torn values are under-relaxed.
  - The stopping test stays the unrelaxed change.
  - A converged run reports the unrelaxed transported values.
  - The no-factor path is unchanged.
- Tests written: `tests/test_electrothermal_fixed_point_relaxation.py`, using the existing electrothermal fixture.
  - Relaxed and plain runs must agree within 1e-4 K.
  - The factor is recorded only when declared.

### BR19 -- adaptive mesh control slice 1: adaptive resolution (EXC-1, tests NOT RUN)
- Owner approved active-epic exception EXC-1 on 2026-10-17. All eight fields are recorded in ACTIVE_PLAN; the
  expiry of 2026-10-31 is Claude's proposal.
- Survey: `StructuredMesh` is uniform and states it has no refinement, and no local refinement exists anywhere. The
  claims refinement study measures a FIXED ladder; nothing chooses resolution.
- New `claims/adaptive_resolution.py`, `adapt_resolution(solve, policy, quantity=, units=)`:
  - refines `baseline * ratio**k`;
  - after each level, applies the CANONICAL `numerical_uq` estimator to the three finest levels;
  - TARGET_MET only on a quantified half-width within the target, otherwise BUDGET_EXHAUSTED (keeps the honest
    interval) or UNKNOWN;
  - an unusable level ends the search;
  - the target is a spread.
- Not done (next slices, same exception or a new one): wiring into `uq_studies` and capability declarations; local
  AMR (non-uniform mesh records, error indicators, solver support).
- Tests written: `tests/claims/test_adaptive_resolution.py`. Exact first-order model: n = 4, 8, 16, 32 meets a
  0.05 target with half-width 0.0390625 and extrapolate 1.0.

### BR20 -- adaptive mesh control slice 2: 1D local refinement kernel (EXC-1 A1, tests NOT RUN)
- EXC-1 amendment A1 (owner-approved 2026-10-17) adds `numerical/mesh_adaptation.py` to the scope. Still
  prohibited: solver changes, Core mesh records, and wiring adaptive resolution into `uq_studies` (owner decision:
  it would make a finer run than the claim's reported run carry its evidence).
- Survey: `conduction1d` is uniform-grid only (single dx, `linspace`), so local AMR cannot drive it without a
  solver change.
- The kernel:
  - `Grid1D`, a non-uniform grid;
  - P1 indicators `h**2/8 * max|u''|`, exact for quadratics;
  - deterministic Doerfler marking;
  - bisection with a minimum cell and gradation;
  - `adapt_grid`, which re-evaluates fresh values every cycle. Its statuses are TOLERANCE_MET_ESTIMATED,
    BUDGET_EXHAUSTED, NODE_BUDGET and RESOLUTION_FLOOR, and the record is classified not-evidence.
- Next slice (needs an EXC-1 amendment or a new exception): a non-uniform finite-difference conduction solver that
  `adapt_grid` can drive, plus wiring into a capability.
- Tests written: `tests/numerical/test_mesh_adaptation.py`.

### BR21 -- adaptive mesh control slice 3: non-uniform steady 1D conduction solver (EXC-1 A2, tests NOT RUN)
- EXC-1 amendment A2 (owner-approved 2026-10-17, commit 9e28c753) adds
  `domains/thermal_models/conduction1d_nonuniform.py` and its tests.
- Placement:
  - `domains/thermal` is pinned by set equality (adding a file breaks `test_every_thermal_source_file_is_pinned`),
    so the new solver lives in `thermal_models`, next to `conduction1d_bulk` and `conduction1d_schemes`.
  - No glob pin covers `thermal_models`; each existing file there is pinned individually.
  - It is imported by path; the pinned `thermal_models/__init__.py` is untouched.
- The solver (commit 1060175f):
  - steady `-(k u')' = q` on a `Grid1D` that must span exactly [0, L];
  - vertex-centred finite volumes, `k` at cell midpoints, `q` at nodes times the control-volume width;
  - explicit temperature or inward-heat-flux ends, never defaulted; two flux ends are refused;
  - `k` must be positive and finite at every face; Thomas solve;
  - exact at the nodes for constant `k` and constant `q` on any grid, flux ends included (checked by hand
    algebra, not by execution).
- Adaptation: `temperature_evaluator(problem)` gives the `adapt_grid` callable (a fresh solve per grid), and
  `adapt_conduction` is that call with `value_unit="kelvin"`.
- Guards checked by reading, not by running:
  - no `ValidationCheck`, `ScientificModelDefinition`, `ScientificSolver` or `ScientificResult` construction;
  - no `pint` import and no `_rel_tol` / `_atol` parameters;
  - the domain import of `engcore.numerical` has a precedent in `electrical/heater_circuit.py`.
- Static checks run: py_compile, an import of the new module from the worktree's src, the undefined-name checker,
  and `git diff --check`. pytest NOT RUN.
- Tests written: `tests/domains/thermal_models/test_conduction1d_nonuniform.py`.
- Next slice (needs an owner decision): declare the non-uniform path as a capability or realization, and/or a
  transient solver. Both are still prohibited under A2.

### BR22 -- adaptive mesh control slice 4: the non-uniform path declared as model + realization (EXC-1 A3, tests NOT RUN)
- EXC-1 amendment A3 (owner-approved 2026-10-17, commit 9f998024).
- Survey:
  - A `ModelRealizationDefinition` must reference a model.
  - The only conduction model, `thermal.conduction1d.linear_diffusion`, is transient, constant-diffusivity and
    source-free. A realization of it would misstate what this solver computes, so a new model record was needed.
  - Domain realizations follow `lumped.py` / `conduction1d_schemes.py`: a domain capability, a domain solver
    capability, and a fresh local registry.
- Declared in `conduction1d_nonuniform.py` (commit 89b9e7c3):
  - `STEADY_CONDUCTION_MODEL` = `thermal.conduction1d.steady_variable_conductivity@0.1.0`:
    - k and q are declared curves against `position` (`varies_with`);
    - four optional end inputs (temperature or inward flux, per end);
    - six exclusions;
    - NO validity conditions, so applicability assesses UNKNOWN (no limit has been sourced);
    - UNVALIDATED.
  - `NONUNIFORM_FV_REALIZATION`, which provides `thermal:steady_conduction_1d` and requires
    `thermal:nonuniform_steady_conduction_1d` + `core:linear_system`.
  - `steady_conduction_models()`, `nonuniform_conduction_realizations()` and
    `nonuniform_conduction_solver_capabilities()`.
  - The solution record now names its model and realization.
- Guard moves:
  - `tests/test_core_guards.py::EXPECTED_MODELS` 18 -> 19, deliberately. That file is certification-pinned, so it is
    UNCERTIFIED until OD-3.
  - Unchanged, because the model has no conditions and no derived quantities: `EXPECTED_CONDITION_NAMES`,
    `EXPECTED_RESERVED_NAMES` and `EXPECTED_RESERVING_MODELS`.
  - `EXPECTED_SOLVER_CLASSES` is unchanged (no `ScientificSolver`), and so is the evidentiary audit (no
    `ValidationCheck`).
  - API snapshots do not cover `engcore.domains`.
- Not done (still prohibited under A3): a claims-layer `CapabilityDeclaration`, a planning production-registry entry,
  and validity conditions. The path is unreachable from claims, SRIA and MCP.
- Static checks run:
  - py_compile;
  - an import of the module from the worktree's src (this constructs the module-level records);
  - the undefined-name checker;
  - `git diff --check`.
  pytest NOT RUN.
- Tests added to `tests/domains/thermal_models/test_conduction1d_nonuniform.py`.

## 2026-10-17 -- Engineering Runtime V1, Phase 1 follow-up: CallbackParticipant provider checkpoints bound to their build (fix/engrt-v1-callback-checkpoint-identity, local only)

Branch `fix/engrt-v1-callback-checkpoint-identity`, Claude worktree `.claude/worktrees/recursing-lichterman-6220f6`,
base `423fb467` (tip of `fix/engrt-v1-phase1-interop`, Phase 1 commit `04b12344`). Local commits `1439b470` and
`28ff37dc`; not pushed, no PR, no merge, no certificate, no hardened run. Closes Phase 1 limitation I-8. Defect fix
inside the Battery 1RC active-epic policy (no new capability foundation). Pristine comparison worktree:
`D:/forge-cbck-base` (detached `423fb467`). Logs: `D:/cbck-logs/`.

**Confirmed defects (reproduced before the fix):**
1. `coupling/adapters.py::provider_participant` restore set the held state from `cp.token` without comparing it with
   `cp.record.state_digest`. Only the runtime's re-checkpoint caught a mismatch, and only for deterministic_restore
   participants. The record named no provider build, so a checkpoint of a participant declaring `thermo@1.0` restored
   into one declaring `thermo@2.0` with the same participant id.
2. `forge_pybamm/coupling.py::cell_participant` restore accepted any token. With REAL PyBaMM 26.8.0.0, a Solution
   checkpointed by an SPM / fade 0.0 cell restored into a cell built with fade 0.2, or with SPMe. It also accepted a
   twin cell's token, a bare Solution, and a record with another digest. A spec naming another solver build was not
   refused.

**Fix (reuses Phase 1's pattern, no parallel provenance):**
- Phase 1's inline seal in `ExternalSolverParticipant` is now the reusable `CheckpointSeal` plus `checkpoint_scope`
  in `execution/multiphysics/external.py`. `ExternalSolverParticipant` uses it with its unchanged scope.
- The registry holds nonce -> (the issued state object, the record issued with it, an optional integrity
  fingerprint). Its entries are dropped by `weakref.finalize` when the token dies.
- `admit` checks, in order:
  1. token type;
  2. build scope and record slot;
  3. the state is the issued object;
  4. the record equals the issued record;
  5. the recomputed digest equals the issued digest, and so does the fingerprint.
- `provider_participant`: the scope is the spec-declared solver and adapter identity, labelled
  `build_basis: participant_spec_declaration` (a declaration, not a session-verified identity). The token state is a
  read-only `MappingProxyType` copy, and restore recomputes the digest from it.
- PyBaMM: the scope is `build_basis: provider_discovery` plus PyBaMM id, version, digest and dependencies, the
  adapter, the declared coupling adapter, and the configuration (model, parameter-set digest, initial SOC, fade,
  fade mapping, SOC definition, options, balance, solver settings). Restore recomputes sha256(y). A fingerprint of
  `last_state.y`, `last_state.t` and `t[-1]` is taken at issue; it is not part of the state identity, so no state
  digest moved. A spec whose solver id or version differs from the discovered provider is refused.

**Scientific review** (`forge-scientific-review` contract, run through the read-only reviewer agent because the
skill was not registered in this session; static only):
- Pass 1: CHANGES REQUIRED.
  - I-1 MEDIUM: the seal bound the token to the participant, not to its issued record. A mutable issued state edited
    in place, plus a re-made record, would be admitted.
  - I-2 LOW: PyBaMM restore aliases the issued Solution.
  - I-3 LOW: the declared build looked like a verified identity.
  - I-4 LOW: the PyBaMM spec adapter was not recorded.
  - I-5: test gaps.
  - All fixed and tested.
- Pass 2 (confirmation): PASS, with LOW notes.
  - R-1: two refusals shared the "digest disagree" phrase. Reworded, and tests match the full phrase.
  - R-2: unverified PyBaMM internals. An executed probe showed that in-place edits of `y` and `all_ys` were refused,
    but an edit of `Solution.t` was ADMITTED and moved the next window's heat. Fixed with the integrity fingerprint;
    an executed test now covers both edits.
  - R-3: opaque `ExternalSnapshot` tokens cannot be re-digested. Documented on `ExternalSnapshot`.
  - No third pass ran after the R-2 fingerprint, so that fix is verified by its tests only.

```text
# reproducers on the unfixed tree (423fb467)
.venv/Scripts/python.exe -m pytest tests/test_provider_participant_checkpoints.py -q   (first version, before the
    seal tests existed)                                         -> 7 failed, 3 passed (controls); failures DID NOT RAISE
WSL ~/mm/root/envs/battery (Python 3.12.14, PyBaMM 26.8.0.0), cwd D:/forge-cbck-base with the final test file copied in:
  pytest providers/pybamm/tests/test_pybamm_checkpoint_identity.py   -> 8 failed, 1 passed (own round-trip control)
# final tree (28ff37dc)
pytest tests/test_provider_participant_checkpoints.py tests/test_external_participant_checkpoints.py -q -> 33 passed
pytest tests/test_provider_participant_checkpoints.py tests/test_external_participant_checkpoints.py
  tests/test_multiscale_runtime.py -q (1439b470)                     -> 50 passed
# EXECUTED PROVIDER, WSL battery env, -p no:cacheprovider -rfs:
pytest providers/pybamm/tests (28ff37dc)                              -> 49 passed, 0 skipped in 183 s
pytest flagships/tests/test_flagship_battery.py (28ff37dc)            -> 22 passed in 1446 s (gate A, rollback, gate F replay)
# EXECUTED PROVIDER, WSL ~/mm/root/envs/fenicsx (dolfinx 0.11.0), providers/fenicsx/tests/test_coupling_fenicsx.py:
#   fix (before review) 7 passed, 2 failed; pristine base 7 passed, 2 failed -- the same two KeyError failures
#   (test_two_way_thermal_electrical_converges..., test_conservation_audit_passes_only_when...), pre-existing
python tools/forge_check.py --regression --workers 4                  -> 256 passed in 13.9 s
# FAST, Windows venv 3.14, -m "not expensive" -q -n 4 -p no:cacheprovider --basetemp=D:/fbt-cbck/<x> -rfE
#   baseline 423fb467 : 128 failed, 10690 passed, 204 skipped, 22 errors in 374 s (150 failing ids; equals the
#                       Phase 1 baseline set)
#   fix 28ff37dc      : 129 failed, 10706 passed, 215 skipped, 22 errors in 546 s (151 failing ids)
#   only in fix: tests/test_test_timing.py::test_the_plugin_records_telemetry_and_never_changes_an_outcome
#     -> environmental: the module key is '' when the worktree (C:) and basetemp (D:) are on different drives; it
#        passes on this tree with a C: basetemp (1 passed) and on the base worktree, which is on D:
#   only in baseline: none
#   +11 skips = the new PyBaMM test file, which skips on 3.14 (no PyBaMM there)
# SCIENTIFIC tier (-m "not campaign"): NOT RUN
```

**Environment:** the 3.13 provider env `D:/forge-prov-tools/provenv` no longer exists on D:. The executed-provider
runs used the WSL conda env `~/mm/root/envs/battery`, which has the same PyBaMM version (26.8.0.0) and Python 3.12.

**Failed approaches (do not repeat):**
- Bash heredocs with long Python patch scripts failed again (`unexpected EOF`); short ones and editor writes worked.
- Comparing only the state-identity digest misses continuation state outside it (the PyBaMM clock). Fingerprint
  that state at issue instead of widening the identity, which would move recorded digests.

**Remaining limitations:**
- `ExternalSolverParticipant` tokens are opaque, so their integrity rests on the session contract (documented).
- PyBaMM state outside y and t (for example the inputs carried on the Solution) is not fingerprinted. It is fixed
  per participant (scope) or re-supplied each window.
- `systems/products/drone_coupled.py` checkpoints a stateless CallbackParticipant with no build (token None). It is
  not a provider adapter and holds no state, so it was left unchanged.

**RECERTIFICATION_REQUIRED (OD-3).** `src/engcore/execution/multiphysics/external.py` is pinned in
`certification/current_core_v2.json`, and the new tests fall under the pinned `tests/**` area.
`coupling/adapters.py` and `providers/pybamm` are not pinned. No touched file is in the frozen API snapshot.

## 2026-10-17 -- Phase 1: scientific & numerical correctness (build phase; fix/phase1-scientific-numerical-correctness, local only)

Worktree `D:/forge-phase1`, base `origin/main` `de11dffa` (re-verified with `git fetch`; still HEAD). Owner direction:
build all seven rocks, write regression tests, **execute no test of any kind**, no push/PR/merge/certification, stop
after Phase 1. Rocks are numbered P1-BR1..P1-BR7 so they are not confused with ERT V1 BR1..BR22.

### Reconciliation against `main` (what already existed)

| Area | Existing and correct | Confirmed defect fixed here |
| --- | --- | --- |
| Coupling plan | criteria/relaxation validation, window control | `35d8f557` (ERT BR2) attached the implicit "requires criteria" check to the IQN-ILS test: every EXPLICIT plan was refused, including both built-in composition packs |
| Convergence | unrelaxed fixed-point residual, divergence/stagnation (opt-in) | no required-coverage policy: an implicit window could be CONVERGED with an iterated interface never measured |
| Conservative mapping | cell measures, extrapolation refusal for other methods | nearest-site values rescaled to the global integral (locally wrong, ~0 division for signed fields, not offset-unit invariant) |
| Error accounting | ESTIMATED/UNQUANTIFIED/UNBOUNDED split, run binding | round-trip + conservation residuals summed into a `relative_bound`, stored as `coupling_error_bound`, read as QUANTIFIED; the claims channel PASSED a mapped run on a 0.0 conservation residual |
| Time windows | event/change boundaries, step-size memory | float running sum, 1e-15 / 1e-12 tolerances, sliver final windows |
| Verification planning | dependency-derived independence, require_external | ordinal `level < minimum_level`: V6 experiment / V7 reproduction satisfied V2, V5 satisfied V4 |
| Sparse numerics | sparse digests, SciPy sparse providers | `.toarray()` on admission and in `condition_of`; storage-order-dependent digests |
| System runtime | graph/plan fingerprints, conservation refusal, untraced providers (ERT BR14) | only `converged` windows exposed: explicit and event-aligned runs always failed; a stub saying `converged` passed |

### Commits (all local)

`a1b6a87e` P1-BR1, `61226343` P1-BR2, `b7a3a032` P1-BR3, `b71eeb3e` P1-BR4, `56cd0e01` P1-BR5, `71085685` P1-BR6,
`20aa9503` P1-BR7, then a docs commit. Details, rules and assumptions per rock: DEFERRED_VALIDATION.md "Phase 1".

### What was executed

- `python -m py_compile` on every changed source and test file: OK (no output).
- `git diff --check` after every rock: clean. CR count of every changed file: 0.
- Import check (`PYTHONPATH=D:/forge-phase1/src`, `engcore.__file__` confirmed in the worktree) of the 15 changed or
  dependent modules, including both built-in composition packs: `imports ok`.
- No pytest, FAST, SCIENTIFIC, regression pack, hardened assurance, mutation, benchmark or certification. **NOT RUN.**
- A read-only static review of the full diff (subagent, no execution): 2 MAJOR, 8 MINOR; dispositions in
  DEFERRED_VALIDATION.md "Phase 1 static review". Findings 3, 4, 5, 6 and 8 fixed in the review-fix commit
  (py_compile, import check and `git diff --check` re-run: clean); 1 and 2 need OD-3 / test rewrites.

### Failed approaches (do not repeat)

- A half-ulp representability threshold for window boundaries (BR4) misses windows between ADJACENT doubles,
  because `exact_seconds` reads the shortest decimal `repr`, which can sit up to half an ulp from the double. One
  ulp per value is the resolution actually available.
- `scipy.sparse.linalg.onenormest` draws random starting columns (t > 1) and random resamples; its estimate would
  make execution records non-deterministic. The in-module xLACON (Hager/Higham, t = 1) estimator is used instead.
- A bash heredoc for a long patch script failed with an unmatched quote (project memory already warns); patch
  scripts were written with the Write tool.

### Certification-pinned files touched (UNCERTIFIED until OD-3)

All in `certification/current_core_v2.json`: `execution/multiphysics/{__init__,convergence,error,mapping,runtime}.py`,
`numerical/{core,providers}.py`, `planning/verification.py`, `scientific/multiphysics/{mapping,plan,report}.py`,
`scientific/verification/{__init__,ladder,plan_serialization,planning}.py`, `system_runtime/authorities.py`. Mutation
population V4: N60d pins the removed ordinal line in `planning.py` (DV-41); N60e/N60f/N60i lines are byte-identical.
No new certified -> uncertified import edge (new targets `scenarios/timeline.py` and `scientific/units/quantity.py`
are pinned; `numerical_error.py` -> `runtime.py` is uncertified -> certified).

### Owner decisions recorded, not taken

1. P1-BR4: should a schedule-forced window shorter than `minimum_window` be refused under window control?
2. P1-BR4: the participant reporting tolerance `1e-12 * max(1, |t|)` is loose for sub-microsecond windows.
3. P1-BR5: admitting `external_solver` and `analytical_reference` as code verification (the only many-to-one entry).
4. P1-BR1: a mesh-measure-weighted field residual norm (today `l2` is the RMS over stored values).
5. P1-BR2: 3D (tet/hex) intersection, non-convex cells, and a "restricted conservative" variant for one-sided coverage.
6. P1-BR6: the dense-conversion and factorization limits (1000, 4096, 5e6 stored entries) are memory-budget choices.
7. P1-BR7: rewrite of the stub-run authority tests (`test_h2_*`, `test_r2_*`, big13 extractor test) on real run records (DV-46/47).
8. Still open from ERT V1: mandatory conditioning of coupled claims; DV-24 closure; OD-3.

## 2026-10-17 -- Phase 2: unified solver & multiphysics architecture (build phase; feat/phase2-unified-solver-architecture, local only)

Worktree `D:/forge-phase2`, stacked on Phase 1 `6249c2d2` (re-verified: Phase 1 not pushed, not merged; `origin/main`
still `de11dffa`). Owner direction: build BR8..BR12 (numbered P2-BR8..P2-BR12), write tests, **execute no test**, no
push/PR/merge/certification, stop after Phase 2. Phase 1 deferred items are preserved, not resolved, except DV-34
(now written, still not run).

### Commits (all local)

`e4dec400` P2-BR8, `54ff4321` P2-BR9, `17dd89b6` P2-BR10, `77634711` P2-BR11, `e9d18d63` P2-BR12, then a review-fix /
docs commit. Per-rock scope, rules, limitations and assumptions: DEFERRED_VALIDATION.md "Phase 2".

### What was executed

- `python -m py_compile` on every changed source and test file: OK. `git diff --check` after every rock: clean;
  CR count of every changed file: 0.
- Import check (`PYTHONPATH=D:/forge-phase2/src;D:/forge-phase2/providers/pybamm`, `engcore.__file__` in the worktree)
  of 21 changed or dependent modules: `imports ok 21`.
- Three one-line arithmetic checks to choose test fixtures (float pairs where `old + (new - old) != new`).
- A read-only static review of the Phase 2 diff (subagent, no execution): 4 MAJOR, ~14 MINOR. M1, M2, M4 and six
  MINORs fixed in the review-fix commit; M3 kept deliberately as a recorded identity change. Dispositions:
  DEFERRED_VALIDATION.md "Phase 2 static review". `py_compile`, import check and `git diff --check` re-run: clean.
- No pytest, FAST, SCIENTIFIC, hardened assurance, mutation, benchmark, real external solver or certification:
  **NOT RUN**.

### Reconciliation (what existed, what was wrong)

| Area | Existing | Found and fixed here |
| --- | --- | --- |
| Coupling owners | `MultiphysicsRuntime`; electrothermal Picard loop; preCICE engine; provider participants | no declaration of which owns convergence; electrothermal provenance claimed "no relaxation" for relaxed runs (false support); NONE relaxation rounded the transfer; one object under two concurrent ids not refused |
| Field transfer | `FieldMapper` (runtime), P1 interpolation on `SpatialMesh`, structured contract checker | no admission table; O(N*M) scans; no 3D conservative remap; provenance only on conservative; arrays round-tripped through Python lists/tuples |
| Checkpoints | solver-id binding, failed-attempt discard, cold fallback (ERT Phase 1) | no build or problem binding; `provider_participant` and PyBaMM `restore` accepted any token (no content digest, no build check) -- the open ERT item |
| Comparison | `compare_providers` with independence and unit rules | no same-problem admission at all (provider problem digests are provider-specific) |
| External solvers | `ExternalSolverParticipant` sealing; FEniCSx via `provider_participant` | no mock label, no failure classes, no interface conservation semantics |

### Failed approaches (do not repeat)

- Driving the electrothermal composition through the runtime with invented initial outputs: a steady result has no
  value before its first solve; the runtime now accepts deferred outputs only where a serial sweep overwrites them.
- Mapping the native relaxed loop onto runtime relaxation: the runtime relaxes every serial edge, the native loop only
  torn values; the adapter refuses relaxed plans instead.
- Putting the mock check after the provider-trace check in `MultiphysicsAuthority`: every mock was refused as
  untraced, so an explicit admission could never take effect.
- `scipy.sparse.linalg.onenormest` (Phase 1) and KD-tree tie-breaking were not trusted for determinism; the KD-tree
  only bounds the search radius and the exhaustive arithmetic decides.

### Certification-pinned files touched (UNCERTIFIED until OD-3)

`current_core_v2.json`: `data/{field,mesh,resolver}.py`, `execution/multiphysics/{external,mapping,relaxation,runtime}.py`,
`execution/orchestration/{advanced_runner,checkpoint,plan,runner}.py`, `system_runtime/authorities.py`,
`systems/electrothermal/coupled.py`. New certified -> uncertified import edge: `execution/multiphysics/mapping.py` ->
`execution/multiphysics/spatial_index.py` (must be pinned or declared). No mutant of the V4 population pins a changed
line (N60d remains the Phase 1 item).

### Owner decisions recorded, not taken

- OD-P2-1: real FE <-> CFD conjugate heat transfer is a new capability foundation (active epic; EXC-1 open) -- BLOCKED.
- OD-P2-2: electrothermal migration: whether the product path may delegate to the runtime after parity (DV-49), and
  which relaxation semantics (torn-only vs every serial edge) the unified runtime should offer.
- OD-P2-3: make `compare_providers` refuse without same-problem admission (changes flagship level-5 evidence).
- OD-P2-4: preCICE: a participant transport under the runtime, or a declared external engine (today).
- OD-P2-5: hexahedral and mixed 3D conservative remap (a trilinear hex is not convex); 3D node fields.
- Still open from Phase 1: N60d / OD-3, stub-run tests, mesh-weighted residual, participant time tolerance, no
  mathematical coupling-error bound.

## 2026-10-17 -- Phase 3: advanced numerical & multiphysics engine (build phase; feat/phase3-advanced-numerical-multiphysics, local only)

Worktree `D:/forge-phase3`, stacked on Phase 2 `2661b640` (re-verified 2026-10-17: Phase 2 is a descendant of Phase 1
`6249c2d2`; neither is in `origin/main`, still `de11dffa`; no phase branch on the remote). Owner direction: build
BR13..BR17 (numbered P3-BR13..P3-BR17), write tests, **execute no test**, no push/PR/merge/certification, stop
after Phase 3. Phase 1/2 deferred items are preserved, not resolved.

### Commits (all local)

`1d80a142` P3-BR13, `9f96c560` P3-BR14, `87c271ab` P3-BR15, `f2df47d2` P3-BR16, `0a97c8a7` P3-BR17, `080751eb`
review fixes, then this docs commit. Per-rock scope, limits and assumptions: DEFERRED_VALIDATION.md "Phase 3".

### What was executed

- `python -m py_compile` on every changed source and test file: OK. `git diff --check` after every rock and after the
  fixes: clean. CR count of every changed source file: 0.
- Import checks (`PYTHONPATH=D:/forge-phase3/src`, `engcore.__file__` in the worktree) of every changed module and of
  `domains.electrical.heater_circuit`, `systems.electrothermal.runtime_adapter`, `domains.thermal_models.conduction1d_nonuniform`: OK.
  Two import checks also printed trivial values (the `ResidualNorm` members; one `RelaxationPolicy` IQN-IMVJ
  to_dict/from_dict round trip) -- a constructor smoke, not a test.
- Static grep checks: `execution/` imports only `scientific`, `data`, `scenarios`; `plan.py` has none of the core
  purity words.
- A read-only scientific review of the Phase 3 diff (subagent with Read/Grep/Glob only, no execution): 0 BLOCKER,
  5 MAJOR, 8 MINOR. All MAJORs and 5 MINORs fixed in `080751eb`; 3 MINORs recorded. Two written tests would have
  failed (M2, M3) and were corrected. Dispositions: DEFERRED_VALIDATION.md "Phase 3 static review".
- No pytest, FAST, SCIENTIFIC, hardened assurance, mutation, benchmark, real external solver or certification:
  **NOT RUN**.

### Reconciliation (what existed, what was added or fixed)

| Area | Existing | Phase 3 |
| --- | --- | --- |
| Nonlinear solves | SciPy hybr/lm provider; method chain; continuation | classified failures; damped Newton with declared scale-aware acceptance; a chain can no longer loosen acceptance (tolerances or acceptance options) |
| Coupling residuals | `linf`, `l2` = RMS over stored values | `l2_measure` (cell / lumped nodal measure); `l2` documented as unweighted |
| Acceleration | IQN-ILS inside `RelaxationController`, history reset every window | one accelerator; IQN-IMVJ with recorded carry/discard rules; supports never mixed; fresh controller per run |
| Window control | subdivision, divergence, stagnation, step memory | step-doubling error indicator with distinct rejection; forced short windows and clock differences recorded; subcycling contract |
| Mesh adaptation | 1D kernel (EXC-1 A1), steady non-uniform conduction | grid digests and per-cycle provenance; round-off bisection skipped; scope refusals; mesh validity checks |
| PDE / moving mesh | four linear templates, FEniCSx KSP | nonlinear admission contract (no template admitted); moving-mesh kinematics, mid-step inversion refusal, discrete GCL residual; no ALE |

### Failed approaches (do not repeat)

- Long bash heredocs for patch scripts again wrote nothing (`unexpected EOF`); write the script with the Write tool.
- Chaining `grep -c` into `&& git commit`: `grep -c` exits 1 when the count is 0, so the commit silently did not run.
- IQN-IMVJ with only the own-norm QR filter: near convergence a round-off secant column passes it and corrupts the
  CARRIED approximation; IMVJ also filters relative to the largest column, and (review M5) an edge scale is not set by
  a round-off residual.
- Carrying an IMVJ approximation across windows of different lengths was rejected: the window map is a different
  operator; only identical exact durations reuse it.

### Certification-pinned files touched (UNCERTIFIED until OD-3)

`current_core_v2.json`: `execution/multiphysics/{convergence,relaxation,runtime}.py`, `numerical/core.py`,
`scientific/multiphysics/plan.py`. New files in certified SCOPE patterns: `execution/multiphysics/{acceleration,
field_measures,subcycling}.py`, `numerical/{health,nonlinear,mesh_quality,moving_mesh}.py`, `pde/nonlinear.py`.
New certified -> unpinned edges: `convergence.py -> field_measures.py`, `relaxation.py -> acceleration.py`. No V4 mutant
targets a changed line.

### Owner decisions recorded, not taken

- OD-P3-1: EXC-1 amendment for coarsening, transient non-uniform 1D conduction and 1D grid-to-grid conservative state
  transfer (BR16 BLOCKED parts).
- OD-P3-2: triangle / tetrahedron refinement and coupled transfer between changing meshes (EXC-1 amendment, or a
  second exception -- which triggers the anti-loophole review).
- OD-P3-3: a nonlinear PDE template (e.g. k(T) diffusion) and a FEniCSx Newton adapter -- a new capability foundation.
- OD-P3-4: an ALE formulation of any governing equation -- a new capability foundation.
- OD-P3-5: confirm that the Phase 3 infrastructure (damped Newton, IMVJ, window error indicator, mesh quality,
  moving-mesh kinematics) is inside policy as runtime/numerical infrastructure, following the ERT V1 and Phase 1/2
  precedent. Claude judged it so; the owner has not confirmed.
- OD-P3-6: schedule-forced windows below `minimum_window` (open since P1-BR4): still recorded, not refused.
- OD-P3-7: whether `l2_measure` or window error control should become mandatory anywhere (identity change).
- Still open: OD-P2-1..OD-P2-5, Phase 1 items, OD-3.

## 2026-10-18 -- Phase 3.5: engineering foundation completion (build phase; feat/phase35-engineering-foundation-completion, local only)

Worktree `D:/forge-phase35`, on Phase 3 `7389f4b4` (re-verified 2026-10-18: Phase 1 -> 2 -> 3 ancestry intact; none in
`origin/main` `de11dffa`; no phase branch on the remote; all worktrees clean). Owner direction: complete the unfinished
foundations within policy, execute no test, no push/PR/merge/certification, stop before Phase 4.

### Commits (all local)

`8a76dbe2` WS1, `e740f208` WS2, `feb1f34e` WS3, `e30c33c0` policy proposals, `e01bc051` review fixes, then this docs
commit. Per-workstream status, DV rows and review dispositions: DEFERRED_VALIDATION.md "Phase 3.5".

### What was executed

- `python -m py_compile` on every changed source and test file; import checks (`PYTHONPATH=D:/forge-phase35/src;D:/forge-phase35/flagships`);
  `git diff --check`: clean.
- A read-only scientific review of the Phase 3.5 diff (subagent, Read/Grep/Glob only): 2 BLOCKER (stale test
  expectations), 3 MAJOR, 8 MINOR; all BLOCKERs and MAJORs fixed in `e01bc051`; MINORs fixed or recorded.
- No pytest, FAST, SCIENTIFIC, mutation, benchmark, real-provider run or certification: **NOT RUN**.

### Policy boundary (what was and was not done)

- Permitted and implemented: WS1 (owner-directed false-support fix, closes OD-P2-3), WS2 (runtime engineering under the
  existing coupling authority), WS3 provider-neutral infrastructure.
- Policy-blocked, NOT implemented: WS3 real FE/CFD adapters (OD-P2-1), WS4 transient 1D adaptation / conservative 1D
  transfer / coarsening / triangle refinement, WS5 nonlinear PDE template, WS6 ALE formulation. Drafts:
  `docs/work/PHASE_3_5_POLICY_PROPOSALS.md` (P35-A4, P35-A5 as EXC-1 amendments; P35-E1..E3 as new exceptions that
  trigger the OD-6 active-epic review). None is active.
- Technically blocked even if approved: no OpenFOAM time-window session or interface read-back; no FEniCSx boundary-trace
  flux output; no Newton path in `forge_fenicsx`.

### Failed approaches (do not repeat)

- A stored same-problem admission checked only for shape could be forged consistently by adding four keys: store the
  canonical problems and re-derive.
- Flagship canonical problems built from the flagship's shared constants declare SAME for sides given different
  inputs: derive each from the problem object the provider was handed.
- Making the runtime refuse a failed SINK result by default would break native parity; making it accept one by default
  would weaken the generic runtime: the tolerance is an explicit adapter opt-in.

### Owner decisions recorded, not taken

- OD-P35-1: approve, amend or reject P35-A4 / P35-A5 (EXC-1 amendments; EXC-1 expires 2026-10-31).
- OD-P35-2: decide OD-6 (active-epic change or program review) before any of P35-E1..E3 can start.
- OD-P35-3: regenerate the cavity and structure flagship bundles with the real providers (DV-93); until then their
  committed level-5 statements are stale and their bundles are refused.
- OD-P35-4: after DV-88..DV-90 pass, set `RUNTIME_PATH_PARITY_VERIFIED` and decide whether the product path delegates;
  whether `CouplingEvidence` should carry a structural marker for candidate runs.
- OD-P35-5: whether the Core consensus path and the verification ladder's V5 mapping must also require canonical
  same-problem admission (Core freeze implications).
- Still open: OD-P3-1..OD-P3-7, OD-P2-1/2/4/5, Phase 1 items, OD-3.

### 2026-10-18 -- Cross-domain architectural fixtures written (CDAR, OD-6 program; tests NOT RUN)

- Branch `test/cdar-architectural-fixtures` (worktree `D:/forge-cdar`, from the Phase 3.5 head `e89c5b5b`: on `main`
  explicit plans are refused until Phase 1 lands). New file `tests/architecture/test_cross_domain_fixtures.py`, test code
  only, participants built from `CallbackParticipant`; no `src/` change.
- Fixtures: RC circuit (explicit serial; v_N = Vs - (Vs - v0)(1 - dt/RC)^N exactly), spring-mass (symplectic Euler;
  Q = v^2 + w^2 x^2 - w^2 dt x v exactly conserved, |H_N - H0| bounded by (w dt/2) H0/(1 - w dt/2)), two-tank mixing
  (implicit serial; inventory conserved, difference decays by 1/(1 + 2 Q dt/V)). Closed forms checked by a plain
  arithmetic script outside the repository (no repository import); this is not a test run.
- Gap pins (ordinary tests asserting today's gap, not xfail): A-11 no ODE participant; A-1 a declared N/m stiffness ->
  surface-tension edge is accepted; A-9 FrameTransform has no translation/time fields; A-2 a species loss needs an
  EnergyConversion.
- New design finding (to add to `CROSS_DOMAIN_ARCHITECTURE_AUDIT.md` on the OD-6 branch): every SCALAR edge builds a
  `QuantityDependency`, whose energy-density rule (`composition/conversion.py` ENERGY_DERIVED_DIMENSIONS) covers force
  (J/m), pressure and surface tension; a mechanical edge must answer it with a prose `transport_declaration`. The audit
  named that rule for field edges only.
- Also found: the fixture's species balance (SOURCE == RECEIVED per scalar edge) holds by construction; storage terms
  cannot be bound into a balance (CDAR-2).
- Read-only review (subagent, nothing executed): 2 BLOCKER (undeclared force edge refused; the CDAR-1 probe was refused
  for the energy rule and would XPASS), 1 MAJOR (live xfails are UNEXPECTED_SKIPs in hardened recertification), minor
  wording; all fixed.
- Verification: `py_compile` and `git diff --check` only. `pytest tests/architecture/test_cross_domain_fixtures.py`
  NOT RUN (DV-99).

### Failed approaches (do not repeat)

- `xfail(strict=True)` probes for architecture gaps: pytest reports them as skips of type `pytest.xfail`, which
  `tools/certification/skip_admission.py` refuses as UNEXPECTED_SKIP; pin the current gap with an ordinary test instead.
- Probing a missing module by importing it: the dependency guard reads import strings; probe with `hasattr` on the
  existing package.


## 2026-10-18 -- OD-6 decided: the active epic becomes the engineering foundations program (branch feat/od6-engineering-program-epic, local only)

Owner decision in the Claude Code session: re-point the active epic from `battery.thevenin_1rc` to the research program
`engrt.numerical_foundations` (contract `docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md`), using the schema /2
research-program mechanism of the OD-6 package (Option C) with this program instead of Genesis. Implemented as the
canonical separate change on a branch from `origin/main` `de11dffa`; **in force only when reviewed and merged.**

- Ledger schema /2: `research_programs` with one entry (gates DV0, M1, M2, E1, E2, E3, all MISSING; build-first: no gate
  requires DV0, `requires` orders decisions only); `active_epic` names
  it; every capability, battery included, byte-identical in meaning.
- `tools/capability_maturity.py`: refuses /1 ("migrate"); validates programs (exact fields, own statuses, ordered
  `requires`, evidence paths, no maturity vocabulary, unique ids across both arrays); a decided program cannot stay the
  epic; renders a programs table.
- `tests/test_capability_completion.py`: the battery pin replaced by the program pin plus a battery snapshot (stage,
  statuses, evidence counts may only grow); negative cases for every back door. **This test edit is a recertification
  trigger (OD-3).**
- Policy, PR template, matrix (hand-edited to the renderer's format) and ACTIVE_PLAN's OD-6 row updated.

Executed: `py_compile` of the checker and the test, `git diff --check`. NOT RUN: `pytest tests/test_capability_completion.py`,
`python -m tools.capability_maturity` (check) and `--write` (the matrix must be regenerated or confirmed).
- Read-only merge review: 0 BLOCKER, 4 MAJOR, ~10 MINOR, fixed except one recorded limit; package:
  `docs/work/OD6_MERGE_REVIEW.md`. Merge preview against `origin/main`: clean. Nothing executed, no PR, nothing merged.

### 2026-10-18 -- Cross-Domain Scientific Architecture Requirements added to the program (owner direction)

- Read-only audit of the Phase 3.5 tree (two Explore subagents, nothing executed):
  `docs/work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md`. The runtime core is mostly physics-agnostic (and a steady coupled
  screening template spanning mechanical, electrical and thermal models exists); thermal hard-coding is confined to `conjugate_interface.py` (P) and
  one message; the real gaps are undeclared semantics (port roles, field kind, non-energy losses), missing ODE / DAE /
  chemical / mechanical participants, static frames, closed problem aspects.
- `ENGINEERING_FOUNDATIONS_PROGRAM.md`: CDAR-1..CDAR-10, multi-domain acceptance criteria for M1-E3, three
  architectural fixtures required before those gates are decided; one prohibition added. Policy: one sentence.
- Test pin added (NOT RUN). Core gaps A-1, A-2, A-3, A-7, A-9 recorded for the Core compatibility review, not implemented.
- Read-only review of the change: 0 BLOCKER, 2 MAJOR (fixture location/enforcement; M2/E2 dependence on Core review),
  minor wording and citations; all fixed.

### 2026-10-18 -- Audit gap A-13 (force edges and the energy-density rule), from the CDAR fixtures

- `CROSS_DOMAIN_ARCHITECTURE_AUDIT.md`: the edge-checks row now says the energy-density rule applies to scalar edges too
  (`graph.py:301` builds a `QuantityDependency`; `composition/dependency.py:231, 241`), and its set
  `ENERGY_DERIVED_DIMENSIONS` holds force, pressure and surface tension. New gap A-13 (CDAR-1, CDAR-2; Core review with
  A-1 and A-2): a mechanical edge can answer that rule only with a prose `transport_declaration`.
- Found while writing the fixtures on `test/cdar-architectural-fixtures` (`D:/forge-cdar`, `2e8434b7`); pinned there by
  `test_gap_a_force_edge_must_speak_in_energy_terms`. Fixture next-step bullet updated; `OD6_MERGE_REVIEW.md` gap range.
- Docs only. Verification: `git diff --check` only; no test was run.

### 2026-10-18 -- Codex handoff: preservation and integration into main (owner direction)

- Inventory: 111 local branches, 77 worktrees, 2 stashes in the Windows repo; WSL clones under `~/forge-*`. Only the
  work below existed outside GitHub; all of it is now pushed (a final `git rev-list <branch> --not --remotes=origin`
  over every local branch returned nothing).
- Pushed: the Phase 1 / 2 / 3 / 3.5 branches, `test/cdar-architectural-fixtures`, `feat/od6-engineering-program-epic`,
  `feat/battery-real-data-identifiability` (`7e923e75`, fetched from the WSL clone), `fix/final-assurance-blockers`,
  `evidence-v11`, `fix-bisect-table`, two September battery branches, `codex/multidomain-science-hardening`
  (fast-forward), `preserve/ci-local-only-assurance-local-2026-10-06` (diverged local branch), six
  `preserve/wip-*` snapshots of uncommitted worktree work (temporary index; worktrees untouched; UNREVIEWED, NOT RUN),
  four `preserve/stash-*` refs, `handoff/codex-2026-10-18`. Secret scan of every pushed range (file names and
  token/key patterns): none. Excluded: regenerated benchmark JSON in `forge-g0-main`, pytest temp directories.
- Integration branch `integration/codex-handoff-2026-10-18` from `origin/main` `de11dffa`: merges I-8 (`b35445ad`),
  Phase 1 (`0ae939f7`), Phase 2 (`0356dbdf`), Phase 3 (`29d37bf3`), Phase 3.5 (`2e800f6e`), CDAR (`a2a5123f`), OD-6
  (`0ae96d3e`), handoff page (`c4f3453e`). Conflicts and their resolutions: `docs/work/CODEX_HANDOFF.md` section 1.
  The I-8 vs P2-BR10 checkpoint-authority resolution makes cross-object restore a refusal and rewrites three Phase 2
  tests to that rule; it is a scientific-design decision for owner review (DV-100).
- Not integrated (preserved on GitHub): battery Practical Pass 1, the `preserve/wip-*` snapshots, stale September
  branches, `fix/final-assurance-blockers` (superseded), open PRs #107 / #39 / #24 (OD-11).
- The CDAR fixture docstring now cites audit gap A-13 (scalar edges, not field-only) (`ff66daef`).
- Verification: `py_compile` of the resolved files, `git diff --check`, conflict-marker scans and merge previews only.
  No pytest, tier, mutation, benchmark or certification ran: everything integrated is UNVERIFIED / UNCERTIFIED.

### Failed approaches (do not repeat)

- Fetching from a WSL *worktree* over `\\wsl.localhost`: its `.git` file names a Linux path; fetch from the clone's
  common git dir instead (`git rev-parse --git-common-dir`).

### 2026-10-18 -- Solver audit and quick fixes (Claude, owner direction in chat)

- Audit of the solver layers on `main` `0284ae16` (Linux, CPython 3.13.16, numpy 2.5.3, scipy 1.18.1, ngspice 44 from
  apt, `CRAFTY_NGSPICE_ARGV=ngspice`; `.` installed without extras):
  `python -m pytest -m "not expensive" -q -n 6 -p no:cacheprovider -rfE --tb=line`
  -> **278 failed, 11210 passed, 166 skipped, 1 error in 692.69 s**. 196 failures were raised directly at
  `execution/multiphysics/runtime.py:2297` (`min(end_exact, *pending)` with nothing pending, from `b71eeb3e`); the error
  was `benchmarks/scientific_truth` without `mpmath` (environment).
- GitHub Actions has started no job since 2026-10-15 (billing; see OD-25). Nothing merged since then ran CI.
- Fixes, each with its own tests run in this session:
  - `cf74cf1c`: window-boundary `min()` (+ `tests/test_multiphysics_windows_without_events.py`, fails without the fix,
    passes with it); `corroborate()` type check before `len()`; ngspice default argv by platform; `scipy>=1.12`;
    workflows pinned to `ubuntu-24.04`.
  - `fef66a75`: steady `CallbackParticipant.initialize` with no outputs admitted as the runtime already admits it;
    `DampedNewtonProvider` classifies `ValueError` domain errors and `newton_armijo` backtracks from an unevaluable
    trial point (+ `tests/numerical/test_newton_domain_errors.py`, 3 of 5 fail without the fix); `EdgeResidual`
    accepts every `ResidualNorm` (BR13 `l2_measure`); IMVJ logs dropping a staged approximation.
  - `f5a346ae`: preCICE path named by repository path (core layering guard); `MonitoredOutput` registered as a nested
    record in `tests/test_core_semantic_invariants.py` (certified file, OD-3); two stale refusal regexes; OD-22..OD-25.
- After the fixes, same environment plus `sympy`/`mpmath` left behind by a provider install:
  `python -m pytest -m "not expensive" -q -n 6 -p no:cacheprovider -rfE --tb=line`
  -> **22 failed, 11494 passed, 164 skipped in 741.68 s** (exit 1). The 22:
  - certification / freeze / mutation-population drift, waiting for OD-3 (10): `test_core_certificate` x2,
    `test_core_freeze_manifest::test_a_descendant_that_keeps_the_contract_still_verifies`,
    `test_core_freeze_v3_manifest::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree`,
    `test_core_freeze_v4_manifest` x3, `test_core_scientific_audit_batch55::test_r67_...`,
    `test_core_scientific_audit_batch56::test_r69_...`, `test_mutation_population_v4::test_every_folded_mutation_...`;
  - owner decisions (3): OD-22 window control, OD-23 `test_l3_no_relaxation...`, OD-24 self-loop edge;
  - test follow-ups (6): `test_phase2_review_regressions::test_a_redundant_forward_tear_is_refused` (no valid plan of
    this one-stage composition can reach the forward-tear refusal: its only other edges have other dimensions, which
    the plan refuses first); five system-runtime tests whose `SimpleNamespace` runtime stub is refused by the Phase 1 BR7
    run-record check (`test_system_runtime_big13_additions` x2, `test_system_runtime_review_fixes` x2,
    `test_system_runtime_state_reads` x1) -- they need a real `MultiphysicsRunRecord`;
  - maturity policy (1): `test_capability_completion::test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes[BLOCKED_WITH_EVIDENCE]`;
  - environment (2): `test_mutation_workspace` permission tests, run as root.
- Provider adapters with pip-installable backends (Cantera 3.2.0, CoolProp 8.0.0, PyBaMM 26.10.1.0, TESPy 0.11.3),
  before the fixes: `pytest providers/{cantera,coolprop,tespy,pybamm}/tests` -> 54 passed, 4 failed (all the `min()`
  bug); with the fix applied, `providers/pybamm/tests/test_pybamm_multiphysics.py` and
  `test_system_runtime_battery.py` -> 9 passed. Deprecations to act on: Cantera `ReactorBase.thermo` (removed after
  3.2) and the `clone` default; PyBaMM `npts`. With PyBaMM installed, the flagship battery tests in FAST take minutes
  each (the FAST tier exceeded 3000 s and was stopped); they skip when PyBaMM is absent.
- `python tools/forge_check.py --changed` escalated to a serial full run after the `pyproject.toml` / workflow change and
  was stopped after ~11 minutes; the FAST tier above was run instead.

## 2026-10-18 - A-1/A-2/A-13 semantic compatibility, Phase A/B

- Checkpoint branch preflight: clean at `02065a6dd25d16abdcac094f7c947148b954bc0e`;
  credential-pattern scan of both branch commits: zero matches; 21 changed paths, no
  temporary/credential artifacts. This bounded scan is not exhaustive secret detection.
- `git push -u origin codex/checkpoint-integrity-hardening`: exit 0. Draft PR #158
  https://github.com/sharq-labs/forge/pull/158 opened and attached; not merged.
  IMPLEMENTED / UNVERIFIED / UNCERTIFIED labels preserved.
- `git fetch origin main`: exit 0; latest origin/main remains `0284ae1`. New isolated
  branch `codex/quantity-semantics` starts there, not from checkpoint hardening.
- Proposal written before shared code: SEMANTIC_COMPATIBILITY_PROPOSAL.md.
  Direct static consumer inventory: 39 src/provider/flagship files, exact baseline lines
  in SEMANTIC_IMPACT_MATRIX.md; indirect/external consumers explicitly discussed.
- Independent Phase A/B read-only review `/root/semantic_review`: PASS before shared
  implementation, no HIGH/MEDIUM design finding. Review is not executed verification.
- Frozen QuantityDependency/EnergyConversion shapes and stored identities will remain;
  typed multiphysics scalar path is the bounded migration mechanism. Legacy aliases may
  refuse and need explicit migration; no auto-alias/physics guessing or evidence promotion.
- pytest/forge_check/provider solves/assurance/mutation/OD-3: NOT RUN by owner Build-First
  policy. Only lightweight static checks authorized. No semantic gap is CLOSED.


## 2026-10-18 semantic compatibility bounded implementation

Branch codex/quantity-semantics is independently based on fetched origin/main
0284ae161ad957d51674ee481e47cfd43d10c5f0. Checkpoint hardening remains clean at
02065a6dd25d16abdcac094f7c947148b954bc0e, matching its origin tracking ref, and
published as Draft PR #158; no merge. No checkpoint commits were combined here.

Design/compatibility proposal and independent design PASS preceded shared source
edits (design-only commit ab688c0f). Typed scalar meaning/role, structured transport,
exact conserved measures and realized contribution bindings are implemented. Frozen
QuantityDependency/EnergyConversion/LossPath exports and shapes are untouched.
Legacy aliases fail closed unless exactly matched conversion forms; typed fields
refuse pending A-3. UNKNOWN coefficients never imply lossless delivery or quantified
uncertainty. All work IMPLEMENTED / UNVERIFIED / UNCERTIFIED; no gaps CLOSED.

New adversarial fixtures cover semantic/role/identity/dimension refusal, actual named
loss partitions, energy/mass/charge/species/momentum-component arithmetic, explicit
fixture F*v power, thermal legacy intent, six /2 record schema boundaries and
quantified-input/UNKNOWN-output uncertainty. Existing stiffness gap pin was strengthened
into intended refusal, not weakened. Remaining legacy gap pins retain gap meaning.

Independent read-only review by /root/semantic_review: static design PASS, patch
PASS and final added-test addendum PASS. Resolved MEDIUM fixture construction issues:
duplicate BalanceTerm names prevented reaching schema assertions; use distinct names.
STANDARD/INTERVAL fixtures lacked mandatory method; add explicitly unqualified fixture
method. These were source-inspection findings, not observed test failures. No outstanding
HIGH/MEDIUM finding. Full A-J record: SEMANTIC_STATIC_REVIEW.md.

Lightweight checks actually executed (PowerShell pipeline into bundled Python at
C:/Users/dev_kaeem/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe):
- Compile-only exact operation: for each .py in union of `git diff --name-only origin/main`
  and `git ls-files --others --exclude-standard`, `compile(Path(name).read_bytes(), name, 'exec')`.
  Result: 9 changed Python files compiled; no compiled code executed and no Forge import.
- Exact command `git diff --check`: exit 0, no output.
- Changed-file UTF-8 credential-pattern scan (private-key headers, GitHub token patterns,
  AWS access key, sk token and quoted credential assignments): 0 matches; bounded,
  not a security certification. Untracked inventory exactly five intended deliverables,
  no temporary files. Exact total changed-file inventory 17, in SEMANTIC_MERGE_PACKAGE.md.
- Checkpoint exact commands `git status --porcelain` and
  `git rev-parse HEAD origin/codex/checkpoint-integrity-hardening`: clean and matching
  02065a6dd25d16abdcac094f7c947148b954bc0e.

Tests/provider execution/import checks/forge_check/full assurance/mutation/OD-3: NOT RUN.
DV-107..112 record exact deferred recipes, avoiding checkpoint DV-101..106. Final
integration needs consumer alias dispositions, normal CI and separately authorized
certification on the final source. Do not regenerate pins merely to silence failures.

Impact matrix now indexes 122 src/provider/flagship/test files with exact BASELINE line
references, not a claim of complete dynamic/external discovery or consumer migration.
Separate A-3 proposal uses unequal-cell integrated amounts (2,6): correct target(4,4),
total8; wrong density interpretation(4,6),total10 despite weighted-integral preservation.
Hand reasoning only; no mapping implementation/numerical execution. Next bounded task
is declared scalar field-kind contract and compatibility review, then unequal-cell tests
under separate execution authorization. Owner decisions and limitations are recorded in
SEMANTIC_MERGE_PACKAGE.md; no automatic semantic push/PR/merge performed.


## 2026-10-18 A-3 declared field kind mapping

Semantic branch codex/quantity-semantics pushed at 98da0c024bd59bd0b18844941eafad3f1d24d428
and opened as Draft PR #159 targeting main by owner authorization. Semantic worktree
was clean before publication; no merge. Prior local-only publication note superseded.
PR body records fail-closed legacy aliases, per-consumer migration and historical
identity preservation. Checkpoint Draft PR #158 remains independent and unmerged.

A-3 branch codex/declared-field-kind-mapping starts exactly at semantic98da0c02;
dependency explicitly recorded. Architecture and 62-file exact-baseline consumer
matrix committed before source edits (2e4fe486). No checkpoint commits combined.

Implemented FieldSemantics using existing QuantitySemantics/ConservedQuantity;
cell-average density, integrated amount and intensive have distinct operators/diagnostics.
Flux/interface support/normal/orientation are declarations only, execution refuses
pending A-4. Existing FieldMapper and new Grid1D adapter share the arithmetic kernel.
Integrated amounts divide by source measure before overlap; densities divide by target
measure. No dimensional inference, global rescaling or coverage extrapolation. UNKNOWN
uncertainty retained; no local physical validity or certified capability claim.

Compatibility: FieldDefinition typed /2 extension; untyped writer /1 retained; downgrade
and incomplete typed payload refusal. Unit conversion retains semantics. Source record
must match declared graph port. No frozen export/schema/certification manifest changed.
Legacy conservative_cell calls without kind now refuse: existing Phase1/Phase2 fixtures
require explicit owning-model migration before integration, not numerical expectation edits.

Independent read-only scientific reviewer /root/a3_review: final static PASS plus
read-only final-additions PASS. Corrections: MEDIUM legacy energy/prose requirement
still applied to typed energy fields (guard with not typed_field, regression written);
MEDIUM nonexistent numerical.errors test import (use numerical.core); LOW expected
measure-refusal text; LOW overclaim that supplied grid digests authenticate stale value
origin (corrected to caller-owned array origin); minor documentation qualified affine
refusal as conserved-field-only. Unit-conversion reconstruction initially would drop
new semantics; preserved explicitly before final review. None are executed test failures.

Tests written for hand-derived (2,6)->(4,4),total8, density contrast(4,6), unequal cells,
refinement/coarsening, partial coverage both directions, reversed axis/normal conventions,
units, intensive affine average, unsupported kinds, stale supplied identities, actual
source substitution, schema refusal and graph identity. Direct 2D tests distinguish
operators. Declared unequal-volume tetrahedral permutation test added; 3D split/merge
remains additional coverage. All tests NOT RUN. No gap CLOSED, A-4 remains open.

Lightweight static checks actually executed via bundled Python
C:/Users/dev_kaeem/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe:
- For the .py union from `git diff --name-only 98da0c02` and
  `git ls-files --others --exclude-standard`, exact operation
  `compile(Path(name).read_bytes(), name, 'exec')`: 10 changed Python files compiled;
  no compiled code executed and no Forge imports.
- `git diff --check`: exit0, no whitespace errors (Git LF normalization notices only).
No pytest, forge_check, mutation, numerical/provider execution, full assurance or OD-3.
DV-113..116 record exact deferred recipes. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.

Local Draft PR-ready package: A3_MERGE_PACKAGE.md, exact17-file inventory, no automatic
A-3 push/PR/merge. A3_COMPATIBILITY_MATRIX.md includes exact current implementation
lines and baseline consumers. No automatic historical relabeling. Remaining decisions:
consumer migrations, test/OD-3 authorization, A-4 face/sign execution, vector/frame scope,
adaptive lineage/history and 3D split/merge evidence. Integral conservation remains a
transfer diagnostic, never a local physical validation result.


Final packaging checks: compile-only repeated over all10 changed Python files, no
Forge imports/execution; `git diff --check` exit0. Bounded changed-file credential
pattern scan:0 matches; exact17 A-3 files, six intended new untracked deliverables
at scan time and no temporary artifacts. Semantic worktree `git status --porcelain`
clean; `git rev-parse HEAD origin/codex/quantity-semantics` both98da0c02. These static
checks provide no scientific verification, validation or certification.


## 2026-10-18 A-3 publication and A-4 interface execution

A-3 clean at4f239fa7fe705e3d8ae390a8e885302dcb07904e; `git status --porcelain`
empty. `git diff --check 98da0c02 HEAD` exit0. Bounded private-key/GitHub token/AWS/sk
and quoted credential-assignment pattern scan over17 intended source/test/doc paths:
0 matches; no untracked/temporary artifacts. Scan is not an exhaustive security audit.
Pushed codex/declared-field-kind-mapping and opened Draft PR#160 against
codex/quantity-semantics, NOT main, by explicit owner authorization. Dependency:
main0284ae1 -> semanticPR#159/98da0c02 -> A-3PR#160/4f239fa7. No merge. Prior A-3
local-only publication statement superseded. CheckpointPR#158 remains independent.

A-4 new branch codex/interface-flux-execution based exactly on A-3 head4f239fa7.
Architecture/Core compatibility decision and48-file baseline reference matrix committed
before source changes: dab92bf0. Typed InterfaceTransfer binds physical meaning,
conserved measure, density/integrated representation, support fingerprints, normals,
orientations, common-plane embedding, full coverage and qualified rectangle method.
Execution derives and applies normal/orientation sign through FieldMapper and
TransferEngine. Integrated values divide by source area; densities use target area.
No dimension-only meaning, unqualified projection, partial coverage or vector shortcut.

Neutral Dirichlet-Neumann admission now uses exact quantity semantics. CHT is its
explicit thermal wrapper; old prose-only/pre-signed conventions require migration.
Typed CHT /2 report binds generic admission to graph identity and says transfer already
applied sign. Edge /3 carries executable interface material; /1 and scalar /2 writers
retain their shapes. 3D normal declaration on2D parameter mesh alone grants no execution.
No frozen API exports, scientific evidence/UQ systems or certificate pins changed.

Independent read-only scientific review /root/a4_review: final static PASS, no unresolved
HIGH/MEDIUM defect in bounded source/tests. Resolved HIGH: interface mapper ignored
requested roundtrip verification/limits; now uses A-3 same-kind reverse norm, finite/limit
refusal and disabled-check-with-limit refusal. Resolved MEDIUM: integrated flux was
misclassified as density in admission; exact branch corrected. Direct/graph regressions
written. Preliminary port-frame finding retracted after confirming scalar ports forbid
that independent frame; no unnecessary guard added. No observed test failures: NOT RUN.

Written probes: opposing/same/reversed normals/orientations, unequal areas/discretizations,
integrated vs density, incorrect-sign outward sum, full-coverage both ways, missing normal,
orientation, unsupported geometry/vector/projection/method, stale support, units/meaning/
kind mismatch, schema downgrade/material identity, roundtrip limits, identity sign and
unit scaling, thermal CHT and nonthermal charge/potential. No provider/numerical execution.
Constructed integral transfer residual is separate from UNKNOWN independent coupled
physical conservation. Numerical solution verification and experimental validation remain
unestablished. Spatial error/model discrepancy uncertainty stays UNKNOWN.

Actual lightweight static checks: bundled Python
C:/Users/dev_kaeem/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe
compiled9 changed Python files from union of `git diff --name-only 4f239fa7` and
`git ls-files --others --exclude-standard` using exact operation
`compile(Path(name).read_bytes(), name, 'exec')`; no Forge imports or compiled code
executed. `git diff --check` exit0 (LF normalization notices only). No pytest, forge_check,
heavy provider runs, mutation, full assurance or OD-3. DV-117..120 record deferred recipes;
DV-101..116 remain NOT RUN. All new work IMPLEMENTED / UNVERIFIED / UNCERTIFIED.

A4_MERGE_PACKAGE.md records exact16-file inventory, compatibility limits and precise
nextM1 task: lineage-bound 1D transfer plus reversible recorded-bisection coarsening,
reusing A-3 arithmetic and existing data/provenance records; then the domain-owned
transient FV/backward-Euler conduction reference. OD-6 permits building before DV0;
scientific verification/validation and gate decisions require executed evidence.
Owner decisions remain consumer migrations, integration/validation authorization,
reference initial/boundary/material sources and final certification/gate decisions.
Unstructured/curved/vector/moving interfaces and independent coupled physical balance
remain open. No A-4 closure or E2 maturity claim. Local A-4 package, no auto publication/merge.


Final A-4 packaging: compile-only repeated over9 Python files; `git diff --check`
exit0. Bounded changed-file credential-pattern scan0 matches (not exhaustive), exact16
A-4 files and four intended untracked deliverables at scan time; no temporary artifacts.
A-3 worktree clean; HEAD and origin/codex/declared-field-kind-mapping both4f239fa7.
No tests or scientific assurance executed. Local package remains UNVERIFIED/UNCERTIFIED.


## 2026-10-18 A-4 publication and M1A lineage-bound adaptation

A-4 clean at1f43c59eab717aa7cbfea672b948accb37f3cc50. `git merge-base HEAD
codex/declared-field-kind-mapping` returned4f239fa7, `git diff --check 4f239fa7 HEAD`
exit0 and status empty. Bounded credential/artifact scan over16 intended files found
0 credential matches/no temporary artifacts. `git push -u origin codex/interface-flux-execution`
succeeded; Draft PR#161 targets codex/declared-field-kind-mapping, NOT main. Stack
main -> #159 -> #160 -> #161. No merge. Prior A-4 local-only publication note superseded.

M1A branch codex/m1a-mesh-lineage is based exactly on A-4 head1f43c59e. Full M1/CDAR
contract read; preimplementation architecture/compatibility decision cbecc2df. Adds
explicit local lineage issuer and numerical/interval_transfer managed adapter; existing
Grid1D/refine/adapt_grid identities and legacy guards unchanged. New deterministic
material includes context/frame, parent versions, exact intervals, bisections and policy.
Coarsening restores only exact recorded active siblings; no inferred ancestry. Captured
canonical snapshots and same-object issuance refuse clones/nested tampering. Exported
/1 audit records cannot authorize import or cross-process recovery.

Managed content-addressed states reuse ScientificDataReference/BulkDataResolver,
existing FieldSemantics and Uncertainty. Actual registered built-in dict/list solver
cache and coupling-history contents cleared on mesh changes; stale handles/fields refuse.
Exact immediate transition authorizes invalidated-source transfer, with populated or
consumed destination refusal. Source byte integrity rechecked. A-3 map_cells_1d reused;
independent coverage and actual amount totals guard admission. Intensive needs an explicit
rule and never a conservation claim; affine units refused. Transfer uncertainty UNKNOWN.
Caller initial values/context remain declarations, not authenticated source provenance.

Independent /root/m1a_review static A-J PASS and addenda PASS. Three MEDIUM corrections:
frame missing from mesh/state material (now root/version/state bound); repeated transfer
could overwrite newer state (consume/refuse populated target); uncertainty seconds could
bind kg state (check all supplied uncertainty dimensions). Legacy scope wording clarified
without relaxing old guards. Explicit root context exported to make identity preimage
auditable. These were source findings, not observed test failures. No outstanding
scientific-authority/evidence-integrity finding reported in reviewed bounded source/tests.

Tests written: unequal cells; refine-transfer-coarsen-transfer-back; density/amount kinds;
fine information loss; deterministic export vs cross-issuer refusal; forged/missing/
conflicting ancestry and sibling/geometry attacks; nested tampering; unrelated/partial
supports; stale fields/receipt replay; actual cache/history clearing; byte corruption;
affine units; misleading conserved/intensive diagnostics; unit conversion; frame identity;
known-to-UNKNOWN UQ and incompatible uncertainty dimensions. Nodal arrays explicitly
refuse interval-cell binding. All NOT RUN. No pytest, provider/numerical execution,
forge_check, full assurance, mutation or OD-3. DV-121..124 added; prior DV-101..120 NOT RUN.

Lightweight checks actually executed using bundled Python at
C:/Users/dev_kaeem/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe:
For .py union from `git diff --name-only 1f43c59e` and `git ls-files --others --exclude-standard`,
exact `compile(Path(name).read_bytes(), name, 'exec')`:3 Python files compiled; no Forge
imports or compiled code execution. `git diff --check` exit0. No scientific verification,
validation or certification follows. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.

Remaining M1 assessed against actual source: conduction1d_nonuniform is steady
vertex-centred FV only. M1A state is primal interval-cell, not vertex dual-volume state;
future adapter must explicitly bind dual supports to primal versions without inventing
bisection ancestry. Then implement transient backward Euler/order1, sourced initial/
material/boundary states, adaptive transient loop and actual numerical studies. Do not
invent density/heat capacity or source provenance, infer conserved energy from kelvin,
or recover arbitrary fine information after coarsening. M1 remains incomplete/MISSING.

M1A_MERGE_PACKAGE.md records exact10-file inventory, compatibility matrix and remaining
owner decisions: concrete dual-state placement design, source data/contexts, consumer and
stack/checkpoint integration, deferred execution and final certification/gate decision.
OD-6 permits bounded build before DV0. No M1A automatic publication/merge or maturity change.

M1A final independent-review addendum PASS: a fourth MEDIUM static finding was
corrected. Registry key aliases could hide a missing issued bisection; verify/lookup
now bind requested/stored keys to record identities. Dedicated wrong-key regression
written, NOT RUN. Current parent-chain records, missing ancestry and nodal-cell refusal
were also reviewed. Four MEDIUM findings resolved in total; no outstanding finding
reported within bounded static review. No scientific verification or M1 completion.

M1A final lightweight checks (2026-10-18): compile(Path(name).read_bytes(), name,
'exec') on the three changed Python files completed without execution or imports.
`git diff --check 1f43c59eab717aa7cbfea672b948accb37f3cc50` exit0. Bounded
credential-pattern scan over exact10-file inventory found zero matches; no additional
untracked artifacts. Explicit `git merge-base --is-ancestor` checks confirmed each
main -> semantic -> A-3 -> A-4 -> M1A edge. Scientific tests remain NOT RUN;
IMPLEMENTED / UNVERIFIED / UNCERTIFIED. No merge or M1A publication.


## 2026-10-18 M1A publication and M1B vertex dual state adapter

M1A exact7f8cb5dac01cd7a270ef72886b77c8cddf717d3b clean; explicit ancestry checks
main0284ae16 ->98da0c02 ->4f239fa7 ->1f43c59e ->M1A completed exit0. Bounded
credential pattern scan over ten intended files found zero matches; no untracked
artifacts; git diff --check 1f43c59e HEAD exit0. git push -u origin
codex/m1a-mesh-lineage succeeded. gh pr create --draft --repo sharq-labs/forge
--base codex/interface-flux-execution --head codex/m1a-mesh-lineage created
https://github.com/sharq-labs/forge/pull/162; attached to task. Nothing merged.

Created isolated managed worktree vertex-dual-state/phyx, branch
codex/m1b-vertex-dual-state from exact M1A7f8cb5da. Owner explicitly decided
vertex primary/dual conserved placement. Preimplementation architecture and Core
compatibility decision4fb78436 before source. Independent read-only reviewer
found no design blocker within declared adapter authority; existing source records
remain caller declarations, not physical applicability/evidence.

Added numerical/vertex_state.py only, no existing source modified. Compose M1A
lineage/cache management; exact issued primal versions derive midpoint/end-point
dual supports. Explicit placement counts distinguish vertex intensive vs dual
density/integrated content. A-3 remap applied to dual boundaries, independent
both-coverages/actual-total tolerance admission. No direct vertex interpolation,
coefficient remap, area/material defaults or affine quantities. Explicit positive
per-dual integrated linear storage binds exact primary/amount/optional density
meanings; missing/unsupported normalized source artifacts refuse. Reuse existing
KnowledgeSource/data/UQ records; output UQ UNKNOWN. This grants no scientific
source authenticity or new evidence/provenance authority.

Failed approaches found by static review (not observed executed failures): initially
density conversion checked only conserved quantity, allowing different density
meanings; now law explicitly binds optional exact density semantics. Initially
ancestry traversal checked state/law records but could miss removed old support
or primal invalidation issuance; now recursively require supports, mesh lineage,
dual/primal transitions. Two MEDIUM findings corrected with dedicated probes.
Independent /root/m1b_review final A-J PASS, no outstanding finding in bounded scope.
No scientific verification follows. Mesh-change failure after primal mutation poisons
adapter. Registered caches/history really clear; external sessions/concurrency unsupported.

Authored tests include nonuniform/half duals/counts, constant density and primary via
explicit storage, unequal amounts, refine/coarsen roundtrip/information loss, storage
discontinuities, unit/species/context/placement mismatch, stale handles, missing source
or ancestry, cloned records, real corrupt/missing bytes, false residuals and unsafe
post-change failure. All NOT RUN. Compile-only checked both new Python files; no
Forge imports/code execution. git diff --check exit0 at that checkpoint. Final bounded
checks recorded separately below. DV-125..128 added, predecessor DV rows NOT RUN.

Legacy require_supported_adaptation and all M1A/A-3/A-4 contracts unchanged. New explicit
OD-6 /1 admission permits state operations only; not a transient policy bypass.
M1C transient vertex FV/backward Euler with sourced physical inputs/BCs and numerical
studies remains next, then adaptive transient orchestration and executed M1/CDAR gate.
No provider execution/pytest/forge_check/full assurance/mutation/OD-3 or maturity change.
M1B remains local Draft PR-ready, IMPLEMENTED / UNVERIFIED / UNCERTIFIED.

M1B final lightweight checks: bundled Python compile(Path(name).read_bytes(), name,
'exec') completed on two new Python files, without importing/executing Forge code.
`git diff --check 7f8cb5dac01cd7a270ef72886b77c8cddf717d3b` exit0. Bounded credential
pattern scan over exact nine intended files found zero matches; artifact inventory
matched, no unexpected untracked files. Static AST counted 31 test functions;
all NOT RUN. Deferred DV-125..128 paths checked for existence only. No numerical
verification, physical validation, certification or M1 gate claim.


## 2026-10-18 M1B publication and M1C bounded transient FV

M1B exact9b092d563507b0de3563c4209d42d6fc0772ea0a clean, correct stack ancestry,
exact nine-file inventory and bounded credential-pattern scan zero matches;
git diff --check 7f8cb5da HEAD exit0. git push -u origin codex/m1b-vertex-dual-state
completed. gh pr create --draft --repo sharq-labs/forge --base codex/m1a-mesh-lineage
--head codex/m1b-vertex-dual-state created https://github.com/sharq-labs/forge/pull/165,
attached to task. No earlier PR retargeted or merged. Checkpoint#158 independent.

Created separate managed transient-fv-1d worktree/branch codex/m1c-transient-fv-1d
from exact M1B. Mathematical/compatibility decision ef11c1da before source. Owner
requested M1C only, not adaptive M1D or full M1. Added new thermal module only,
preserving all prior production source. Distinct transient model/realization;
explicit piecewise area/material/source, M1B dual storage, positive scalar
phase-constant MaterialPropertySet resolution, exact source byte hashes, series
conductivity/contact resistance. No rho/cp/area defaults or unsupported state dependence.
Both-Neumann transient admitted through positive storage, steady refusal unchanged.

Sparse tridiagonal BE through existing numerical protocol with domain-local sparse-only
SuperLU provider. Existing SciPyLinearProvider's small-system dense conditioning path
was rejected for this owner constraint; no existing provider changed. Conditioning
unresolved, provider identity binds source and actual SuperLU binary plus library
versions. Residuals never error bounds. Exact initial/current state/material/storage/
source/clock/window/dt/build binding. Per-face opposite powers, explicit volumetric and
boundary contributions, endpoint half-volume reservoir reactions. Failed attempts and
partial publication poison continuation. No rollback/adaptation/history M1D guarantee.

Independent forge-scientific-review skill/read-only /root/m1c_review: initial design
no blocker, final A-J static PASS after corrections. Failed approaches found statically,
not observed test failures: HIGH mixed Dirichlet K versus interior W rows/global norm
could hide wrong endpoints and reactions closed tautologically; now power-scaled rows,
explicit temperature tolerance and row-wise residual admission. HIGH live alternative
storage2*C could change returned energy without assembly change; now exact storage ID/
actual J/K bytes and initial clock bound. MEDIUM missing-boundary helper defaulted None
to valid zero flux; direct malformed step fixture now covers it. All fixes reread.
No scientific verification, validation or certification follows from review.

Known integration hold M1C-C1: tests/test_core_guards.py walker163 and exact count
pin199/assert534 expect19 models. New required model statically implies20. No execution
or observed failure claimed; no certified pin edit or hidden/lazy model discovery.
Owner compatibility/count-pin approval and separate certification handling required
before integration. Other unexecuted failures remain unknown.

Authored independent specified-flux/source energy balance, equilibrium/insulation,
nonuniform half-volume/interface/contact tests, exponential transient temporal-order
and sine/analytic-dual-source spatial refinement designs. Adversarial time/source/
material/initial/BC/state/build/provider substitution, false residual, during-provider
mutation and partial publication failure cases. No numerical expectation was tuned to
observed runs. All tests NOT RUN. Compile-only source/tests checked without imports
or execution. Final checks recorded below. DV-129..132 appended; earlier DV rows NOT RUN.
M1C package local only, IMPLEMENTED / UNVERIFIED / UNCERTIFIED. M1D/full M1 incomplete.
No pytest/provider solves/forge_check/full assurance/mutation/OD-3 executed.

M1C final lightweight checks: bundled Python compile(Path(name).read_bytes(), name,
'exec') completed for two new Python files without importing/executing their code.
Static AST counted 28 authored test functions, all NOT RUN. Exact nine-file
inventory and bounded credential-pattern scan zero matches; no unexpected artifacts.
Deferred DV-129..132 paths checked for existence only. Direct git-show/base-byte
comparison confirms old steady, M1B, numerical core/providers and certified model
census guard unchanged. No numerical solve or scientific evidence produced.

M1C final staged/static checks: `git diff --cached --check` and
`git diff --check 9b092d563507b0de3563c4209d42d6fc0772ea0a` both exit0.
Independent reviewer final addendum reread input validators, nonfinite/tensor
fixtures and full package: PASS, no new authority/evidence-integrity finding;
model-census integration hold remains. No commands/tests/imports by reviewer.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED, NOT INTEGRATION-READY.

## 2026-10-18 - Checkpoint integrity R1-R5 bounded repair (Build-First)

- Base `0284ae161ad957d51674ee481e47cfd43d10c5f0`, isolated branch
  `codex/checkpoint-integrity-hardening`, worktree
  `C:/Users/dev_kaeem/.codex/worktrees/checkpoint-integrity/phyx`. Shared stale main
  `a3f757e` and all pre-existing edits left untouched. No main merge/push.
- Owner decisions: preserve strict same-participant seal; durable cross-process recovery is
  separate; fail closed on required integrity/identity; preserve evidence/certification;
  tests are written but NOT RUN. No full assurance, mutation, expensive suite or OD-3.
- R1: mandatory provider codec of actual immutable continuation bytes (including resolution
  and verification of referenced content); SHA-256 computed by Forge, not accepted as a cached
  provider assertion. No automatic bytes-handle escape. No unsafe serializer.
- R2: run/restore failures retire the runtime; callback/external application failures retire
  wrappers. Safe record/foreign-object admission is separated from corrupt issued payloads.
  Process-local object retirement blocks custom participant reuse in fresh runtimes.
- R3: PyBaMM origin zero, requested/checkpoint/restored/solver time checks, current-state
  fingerprint against alias edits, and failed-step retirement; y digest/build scope preserved.
- R4: readable legacy references cannot resume without explicit build/problem; adoption
  requires known execution context; both runners refuse observable within-call build drift;
  cross-solver conversion requires the same canonical problem. Native declaration-only
  adapter scope remains labelled and cannot replace a required expected/observed build.
- R5: adversarial tests written, including review-driven counterexamples. Existing routing
  fixtures now provide explicit identities; original routing/science expectations retained.
  A corrupted PyBaMM session's subsequent attempt now expects permanent unusability.
- Independent reviews 1/2: CHANGES REQUIRED, read-only, no execution. Rejected approaches
  and dispositions are in CHECKPOINT_HARDENING.md; follow-up review pending.
- Deferred commands DV-101..DV-106 added; DV-100 then DV-99 remain first. All pytest,
  forge_check, tiers, provider solves, assurance, mutation and OD-3: NOT RUN.
- Environment observation: `python --version` returned exit 1 (Windows Store alias; no
  interpreter there). Used bundled Python for editing and compile-only static inspection.
- Static command executed (exit 0):
  `& 'C:/Users/dev_kaeem/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -c "import pathlib,subprocess; names=subprocess.check_output(['git','diff','--name-only'],text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines(); paths=sorted({n for n in names if n.endswith('.py')}); [compile(pathlib.Path(p).read_bytes(),p,'exec') for p in paths]; print('Static compilation only:',len(paths),'Python files; no modules imported or executed')"`
  Result: 15 changed Python files compiled as source; no Forge/provider modules imported,
  no tests or numerical code executed. This is syntax evidence only.
- Static command `git diff --check` executed, exit 0, no output. Later edits require final
  repeat of these static checks; no scientific verification or certification is claimed.

### Final independent disposition and package

- Independent reviewer `/root/checkpoint_review`: PASS after review-driven repairs; no
  outstanding HIGH/MEDIUM finding. Report: CHECKPOINT_HARDENING_REVIEW.md. No tests ran.
- Final inventory: 21 files (8 implementation, 7 test, 6 documentation). Exact paths, PR
  title/body, compatibility/limits and merge requirements: CHECKPOINT_HARDENING_MERGE_PACKAGE.md.
- Final static repeat: the exact compile-only command recorded above executed again,
  exit 0, 15 changed Python files; `git diff --check`, exit 0, no output. Syntax and
  whitespace only. pytest/forge_check/provider solves/full tiers/mutation/assurance/OD-3: NOT RUN.
- No source evidence, frozen snapshots, certificates, workflows or scientific acceptance
  thresholds regenerated. No capability promotion. IMPLEMENTED / UNVERIFIED / UNCERTIFIED.
- Next recommended bounded task: A-1/A-2/A-13 semantic compatibility proposal, then A-3
  declared-field-kind overlap rules. No additional implementation authorized by this slice.

- Failed documentation approach: a default-encoding whole-file read/write altered historical
  non-ASCII text in PROGRESS. Restored the exact baseline bytes and appended only this task's
  ASCII entries. Do not normalize historical evidence logs through locale-dependent text IO.
  Correction changes documentation only; independently reviewed implementation is unchanged.

### 2026-10-18 -- Batch 4: real coupled runs for five system-runtime tests; forward-tear reachability (branch `fix/batch4-system-runtime-real-runs`)

- Base `main` `4e339b5f8728088816a2584fe203b9b203a7b15e`; Linux, CPython 3.13.16, numpy 2.5.3, scipy 1.18.1,
  ngspice 44 (apt), `CRAFTY_NGSPICE_ARGV=ngspice`. Tests only; no `src/` file changed.
- 4A: `_coupled_stub()` (a `SimpleNamespace` "run") replaced by `_coupled_runtime(end_uncertainty)`, a genuine
  `MultiphysicsRuntime`: one transient `body` participant on a real graph, an explicit plan with one 1800 s window, an
  initial-state receipt that acknowledges the supplied state exactly, a real state identity and a public end state
  (305 K with the caller's uncertainty). `coupled_run_kwargs(call)` passes `external_inputs={}` and the run's authorized
  scenario (`call.context.scenario.digest`), as the PyBaMM and flagship authorities do. Assertions unchanged.
- 4B: `test_a_redundant_forward_tear_is_refused` has no valid fixture in the series pack. New
  `test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[1-3]` tries all 7 / 63 / 511 tear sets
  (tolerance in the torn dimension): 3 admitted per N, all backward; none reaches the forward-tear refusal. The
  original test is left failing and recorded as OD-26; nothing was fabricated.
- Before, the six tests:
  `python -m pytest -q -p no:cacheprovider <6 node ids>` -> **6 failed**.
- After:
  `python -m pytest -q -p no:cacheprovider tests/test_system_runtime_big13_additions.py tests/test_system_runtime_review_fixes.py tests/test_system_runtime_state_reads.py`
  -> **51 passed**;
  `python -m pytest -q -p no:cacheprovider tests/test_phase2_review_regressions.py` -> **7 passed, 1 failed**
  (`test_a_redundant_forward_tear_is_refused`, OD-26).
- Related regressions:
  `python -m pytest -q -p no:cacheprovider -n 4 tests/test_system_runtime_*.py tests/test_phase2_review_regressions.py tests/test_phase35_ws2_electrothermal_migration.py tests/test_electrothermal_vertical.py tests/test_phase2_coupling_authority.py tests/test_stateful_multiphysics_runtime.py`
  -> **269 passed, 2 failed** (`test_a_redundant_forward_tear_is_refused` OD-26; `test_l3_no_relaxation...` OD-23).
- Not run (not authorized): full FAST / SCIENTIFIC tiers, mutation, OD-3.
- Independent read-only review (`forge-scientific-reviewer`, static, ran nothing): **PASS**, no BLOCKER/MAJOR. Acted on: MINOR-1/2 (the enumeration now asserts every plan refusal is the mixed-dimension one, every adapter refusal is the cycle refusal, and the exact admitted sets), NOTE-1 (the no-state `initialize` starts from the declared 300 K every run), NOTE-2 (new `test_h2_a_known_end_uncertainty_over_a_known_prior_is_committed_as_the_participant_stated_it`). Recorded: MINOR-3 in OD-26, NOTE-3 as OD-27. After the fixes: `python -m pytest -q -p no:cacheprovider -n 4 tests/test_phase2_review_regressions.py tests/test_system_runtime_big13_additions.py tests/test_system_runtime_review_fixes.py tests/test_system_runtime_state_reads.py` -> **59 passed, 1 failed** (`test_a_redundant_forward_tear_is_refused`, OD-26).

### 2026-10-18 -- Batch 5: scenario identity integrity, OD-27 (branch `fix/od27-scenario-identity`)

- Base `main` `4e339b5f8728088816a2584fe203b9b203a7b15e`; Linux, CPython 3.13.16, numpy 2.5.3, scipy 1.18.1, ngspice 44,
  `CRAFTY_NGSPICE_ARGV=ngspice`. Independent of draft PR #163.
- `MultiphysicsAuthority.execute` now admits scenario identity twice: before `runtime.run` (a `run_kwargs` digest that is not
  the authorized `call.context.scenario.digest`, or scenario-driven arguments with no digest -> FAILED, nothing runs) and on
  the returned record, right after the graph/plan checks and before conservation, outcome, outputs, extractors, state,
  artifacts and provider records (a different digest, or scenario evidence without a digest -> FAILED). A record with no
  digest and no scenario evidence stays admitted: the runtime's and `MultiphysicsRunRecord`'s own scenario_bound contract.
  **Superseded by the review fixes below (`fa71030c`): inside an authorized execution an unbound run is refused.**
- `python -m pytest -q -p no:cacheprovider tests/test_system_runtime_scenario_identity.py` -> **11 passed**; with the
  `src` change stashed -> **8 failed, 3 passed** (the 3 are the admitted / compatibility cases).
- `python -m pytest -q -p no:cacheprovider -n 4 tests/test_system_runtime_*.py tests/test_phase1_system_runtime_outcomes.py
  tests/test_phase2_external_coupling.py tests/test_multiphysics_conservation_history.py tests/test_stateful_multiphysics_runtime.py`:
  before (main) **5 failed, 214 passed**; after, excluding the new file, **5 failed, 214 passed** -- the same five
  `SimpleNamespace`-stub tests PR #163 repairs (three now refused one step earlier, by the new pre-run check).
- Same suites plus `tests/test_phase2_review_regressions.py`, merged locally with PR #163 (temporary branch, discarded):
  **238 passed, 1 failed** (`test_a_redundant_forward_tear_is_refused`, OD-26).
- `providers/pybamm/tests/test_system_runtime_battery.py` (PyBaMM 26.10.1.0 and TESPy 0.11.3 installed for this run, then
  removed): **8 passed** -- the provider `runtime_factory` path, which passes the scenario digest, is unchanged.
- `src/engcore/system_runtime/authorities.py` is pinned in `certification/current_core_v2.json`: UNCERTIFIED until OD-3.
  Not run: FAST / SCIENTIFIC tiers, mutation, OD-3.
- Independent read-only review (`forge-scientific-reviewer`, static): **CHANGES REQUIRED** -- M1 (an unbound run, no
  digest and no scenario evidence, was admitted and could commit state inside an execution that has an authorized
  scenario; a runtime factory can carry scenario-derived state without leaving evidence), M2 (out of scope:
  `MultiscaleAuthority` binds no scenario / timeline / environment to the call context), m1 (top-level digest trusted
  alone), m2/m3 (untested branch, vacuous assertions), N1 (factory built before the check). Acted on: M1 -- with an
  authorized scenario the run must name exactly it, before the run and on the record; m1 -- every state transition,
  scenario input, operating condition, QoI and termination receipt must carry the authorized digest; N1 -- the check runs
  before the runtime factory; m2/m3 -- tests for a rewritten and a cleared digest, a providers hook, no vacuous asserts.
  Recorded for follow-up: M2 (proposed OD-28), N2 (mutable `RuntimeContext`), N3 (refusals drop provider records).
- After the review fixes: `python -m pytest -q -p no:cacheprovider tests/test_system_runtime_scenario_identity.py` ->
  **14 passed**; against main's `authorities.py` -> **11 failed, 3 passed** (the admitted cases).
  Related suites (as above, new file included) -> **5 failed, 228 passed** (the five #163 stub tests, now refused by the
  pre-run rule because their stub `run_kwargs` name no scenario; #163's fixture names it). Merged locally with #163
  (temporary, discarded; only `docs/work/PROGRESS.md` conflicted) -> **241 passed, 1 failed** (OD-26).
  `providers/pybamm/tests/test_system_runtime_battery.py` -> **8 passed** (PyBaMM/TESPy installed for the run, removed).
- Compatibility: inside a `SystemExecutor` run every `MultiphysicsAuthority` must now pass
  `scenario_digest=<authorized digest>` in `run_kwargs`. In-tree: the PyBaMM kit and the battery flagship already do;
  #163's fixture does; calls without an execution context (unit tests passing a bare call) are unaffected.
- Re-review of `fa71030c` (static): **PASS**; M1, m1, m2, m3, N1 closed. Follow-ups applied in the next commit: L1 (no-context
  branch also requires empty receipt digests), L2 (stale comment / superseded PROGRESS line), L3 (contract in the
  `MultiphysicsAuthority` docstring and `docs/architecture/engineering.md`), L4 (M2 as OD-28 in ACTIVE_PLAN). Not run by the
  builder: `flagships/tests/test_flagship_battery.py` (needs PyBaMM; minutes per test); statically it passes the authorized digest.

### 2026-10-18 -- Batch 6A (OD-28): MultiscaleAuthority bound to the authorized scenario / timeline / environment (branch `fix/od28-multiscale-identity`)

- Base `fix/od27-scenario-identity` `279a3fd749ded312bda53afb02dfd2a64e4fa568` (stacked on draft PR #164; `main`
  `4e339b5f` untouched). Linux, CPython 3.13.16.
- Decision: a `MultiTimescaleRuntime` is always scenario-bound (its constructor requires a scenario-bound timeline), so
  there is no scenario-independent multi-timescale path and no compatibility exception. `MultiscaleAuthority`:
  `preflight_findings` admits a node only when `runtime.identities()` scenario / timeline / environment equal
  `context.scenario/timeline/environment` digests (internally consistent) and the runtime is unchanged since construction
  (`declared_fast_state` excluded: the runtime re-derives it from the authority's declared fast state each run; record and
  checkpoints are compared on it exactly); `execute` refuses a node not admitted, a context that is no longer the admitted
  one, or a changed runtime, before run / resume; the returned record must belong to the runtime's run and carry exactly the
  runtime's identities (bound to the authorized ones), as must every macro checkpoint in it, before extractors /
  applicability / providers / state proposal / pending checkpoint; a held checkpoint carries `(request digest, identities)`
  and resumes only for them; a restored payload (binding None; the executor's `SystemCheckpoint` verification binds the
  request) and every resumed checkpoint must carry the authorized identities and the runtime's run id before
  `runtime.resume`. Codes `MULTISCALE_IDENTITY_MISSING` / `_MISMATCH` / `MULTISCALE_RUNTIME_CHANGED`. Authority identity
  payload unchanged (serialization identity preserved).
- New `tests/test_system_runtime_multiscale_identity.py` (24 tests, genuine `MultiTimescaleRuntime` over the heater/board
  reference, two-day program; adversaries are runtime subclasses) and shared `tests/system_runtime_multiscale_fixtures.py`.
  Before (base `authorities.py`): `python -m pytest -q -p no:cacheprovider -n 4 tests/test_system_runtime_multiscale_identity.py`
  -> **19 failed, 5 passed** (the 5 valid-path controls). After -> **24 passed**.
- Migrated (stub runtime `identities={"id": "stub"}` is now refused): `test_h5_...`, `test_m5_...`
  (`test_system_runtime_review_fixes.py`), `test_n2_...` x3, `test_c_...` x2 (`test_system_runtime_rereview_fixes.py`) to
  genuine runtimes on the request's own context; assertions kept (h5's literal stub payload became "the promoted
  checkpoint is the run's real macro checkpoint"; m5 uses a genuine runtime that stops at day 1; the two-domain test
  perturbs the second compared domain, `board_slow`). The migrated tests pass on the base `authorities.py` too (faithful).
- Regressions: `python -m pytest -q -p no:cacheprovider -n 4 tests/test_system_runtime_*.py tests/test_phase1_system_runtime_outcomes.py tests/test_multiscale_fast_nonconvergence.py tests/test_multiscale_review_fixes.py tests/test_multiscale_runtime.py tests/test_big11_review_fixes.py`
  -> after **5 failed, 253 passed**; base tracked tree with the new untracked tests -> **24 failed, 234 passed** (19 new
  OD-28 tests + the same 5). The 5 are the coupled-stub tests PR #163 repairs (`test_multiphysics_extractors_...`,
  `test_an_extractor_that_raises_...`, `test_a_committing_node_cannot_requantify_...`, `test_h2_...`, `test_r2_...`),
  failing identically on the base.
- Merged locally with #163 (temporary branch, discarded; only docs conflicted), same suites plus
  `tests/test_phase2_review_regressions.py` -> **1 failed, 266 passed** (`test_a_redundant_forward_tear_is_refused`, OD-26).
- `providers/pybamm/tests/test_system_runtime_battery.py` (PyBaMM 26.10.1.0, TESPy 0.11.3 installed for the run, then
  removed; `PYTHONPATH=providers/pybamm:providers/tespy`) -> **8 passed** (incl. Gate C, Gate E fresh-runtime resume,
  changed-context resume refusal: the production `MultiscaleAuthority` path).
- Compatibility: a `MultiscaleAuthority` now needs a runtime bound to the request's scenario / timeline / environment and
  a preflight admission before `execute` (direct `execute` calls must call `preflight_findings` first with the context);
  a request without an environment cannot run a multiscale node. In-tree production users (PyBaMM kit) already comply.
- Nested gap recorded as OD-29 (fast-system inner run records are not resolved; only self-reported echoes are checked).
- `src/engcore/system_runtime/authorities.py` is certification-pinned: UNCERTIFIED until OD-3. Not run: FAST / SCIENTIFIC,
  mutation, full assurance, OD-3.
- Independent read-only review (`forge-scientific-reviewer`, static): **CHANGES REQUIRED** -- MEDIUM-1 (the held
  checkpoint was `record.last_valid_checkpoint`, a property, while the verified object was `record.checkpoints[-1]`; a
  record look-alike or subclass could have a foreign checkpoint held and bound to the authorized request), MEDIUM-2 (h5's
  name promises "a fresh run never inherits one" but nothing tested it; pre-existing: the stub version also used two
  authorities), LOW-1 (identities are the runtime's self-report), LOW-2 (untested branches), LOW-3 (identity refusals are
  FAILED, not REFUSED), NOTE-1..4. Acted on: MEDIUM-1 -- the record must be a `MultiTimescaleRunRecord` and the held
  checkpoint is the verified list item; MEDIUM-2 -- h5 now runs a fresh (failing) stage on the same authority and asserts
  nothing is inherited; LOW-1 -- the reported scenario / timeline / environment must be those of `runtime.timeline` /
  `runtime.environment` (and the environment's timeline), at admission, before run and after the record; LOW-2 -- tests for
  a record differing in a non-bound key, a record missing a bound key, a renamed runtime; NOTE-1 -- docstring. Not changed:
  LOW-3 (kept consistent with OD-27 and the existing `MultiscaleAuthority` guards; recorded with NOTE-3 as OD-30); the
  held-binding identity branch is defence in depth (unreachable while the runtime is fixed and the request pins the context).
  Serialization identity checked: the authority `identity_digest` of a staged and a plain fixture authority is identical on
  base `279a3fd7` and on the fix.
- After the review fixes: `tests/test_system_runtime_multiscale_identity.py` -> **30 passed**; its 6 review tests against
  the pre-review fix -> **3 failed, 3 passed** (MEDIUM-1 x2 and LOW-1 caught; the LOW-2 branches were already handled).
  Same regression set as above -> **5 failed, 259 passed** (the same five #163 stub tests).
  `providers/pybamm/tests/test_system_runtime_battery.py` (PyBaMM/TESPy installed for the run, then removed) -> **8 passed**.
- Re-review of `9c5c7664` (static): **CHANGES REQUIRED** -- MEDIUM-2, LOW-1 closed, LOW-2 mostly closed; MEDIUM-1b: the
  checkpoint items were checked by attribute only and the held payload was whatever `serialize()` returned, so a
  look-alike or a `MacroCheckpoint` subclass could still get a foreign payload held. Acted on: exact types
  (`type(record) is MultiTimescaleRunRecord`, `type(cp) is MacroCheckpoint`) and the payload that would be held is
  deserialized and checked (run id, identities) before anything is exposed; tests for both adversaries, a record subclass
  overriding `last_valid_checkpoint` (now refused), and a runtime that starts lying after preflight (caught by the objects
  check at execute). The new m1b / record-subclass tests against `9c5c7664` -> **3 failed, 1 passed**.
- After: `tests/test_system_runtime_multiscale_identity.py` -> **33 passed**; regression set -> **5 failed, 262 passed**
  (the same five #163 stub tests); `providers/pybamm/tests/test_system_runtime_battery.py` (PyBaMM/TESPy installed for the
  run, removed) -> **8 passed**.
- Second re-review of `f726392d` (static): **PASS**; MEDIUM-1b closed. LOW note applied: `record.checkpoints` must be a
  tuple (a stateful container could yield another item after verification). After it:
  `python -m pytest -q -p no:cacheprovider -n 4 tests/test_system_runtime_multiscale_identity.py tests/test_system_runtime_review_fixes.py tests/test_system_runtime_rereview_fixes.py tests/test_multiscale_runtime.py tests/test_multiscale_review_fixes.py`
  -> **2 failed, 121 passed** (`test_h2_...`, `test_r2_...`: #163 stub tests, failing on the base too). Open: OD-29, OD-30;
  no test for one authority shared by two contexts (fails closed statically). UNCERTIFIED until OD-3.

## 2026-10-18 -- Post-merge remediation: defect census + Batch A (worktree `D:/forge-main-337519d1`, base `337519d1`)

- Census of Batches A-F (static only; four read-only review agents plus own spot checks): master table in
  `docs/work/REMEDIATION_2026-10-18.md`. Owner decisions now open: OD-22/23/24/26/29/30 (existing) and OD-31 (new).
- A1: static count of `ScientificModelDefinition(` in `src` is 19 at `89b9e7c3` and 20 at `337519d1`; the only addition
  is `thermal.conduction1d.transient_piecewise_linear@0.1.0`, which has no validity conditions and no derived quantities,
  so reserving 16 / conditions 96 / reserved 63 / solvers 11 do not move. Proposed patch
  `docs/work/proposals/A1_core_guards_model_count.patch` (19 -> 20), **not applied**: `tests/test_core_guards.py` is
  certification-pinned (OD-31).
- A2 (OD-26): the original test's fixture is refused by `FixedPointCouplingPlan.__post_init__` (mixed dimensions) before
  `runtime_equivalent` runs, so it is a test-design defect and the guard is defensive code. Added
  `test_a_tampered_plan_with_a_forward_tear_is_refused_by_the_runtime_build` (genuine 1-stage records, frozen plan altered
  after construction, fixture pinned). Original test kept for the owner.
- Failed approach: an import-only discovery replica (`pkgutil.walk_packages` over `engcore`) could not run. On this host
  `import pint` and `import scipy.sparse` never return (`import numpy` needs `OPENBLAS_NUM_THREADS=1` to return); about
  25 idle `python.exe` processes from other sessions were present and were not touched.
- Tests: **NOT RUN** (no pytest authorized). Only `ast.parse` of the edited test file was executed.

## 2026-10-18 -- Post-merge remediation: Batch C (numerical correctness), same worktree, uncommitted

- C1 (`numerical/nonlinear.py`, not pinned): Newton classifies only `ArithmeticError` and an exact-type `ValueError`
  carrying a CPython `math`/`cmath` domain text (3.14 texts probed on this interpreter, plus NaN-to-integer); numpy
  shape errors, `LinAlgError` and caller bugs now propagate from residual, Jacobian, Armijo trial points and
  `acceptance_measure`. Backtracked domain failures are counted. The recorded condition is judged against
  `min(declared limit, 1e12)`.
- C2 (`numerical/providers.py`, certified, already drifted): a non-finite SuperLU solution is FAILED "numerically
  singular matrix"; success path unchanged. CERTIFICATION PENDING (OD-3).
- C3: no source change. C3-3 (sign for CONTINUOUS with opposing normals) is correct by flux-vector continuity; C3-5 is
  unreachable (window records refuse empty iterations); C3-2 downgraded (shared declared frame). C3-1 limitation pinned
  by a test.
- Recorded OD-32 (C1-4 initial-point label, C2-1 residual measure label, C2-2 linear disclaimer, C3-1 relabel): each
  changes serialization identity or a pinned outcome.
- Rejected approaches: matching only the legacy "math domain error" text (Python 3.14 rewrote most `math` messages, so
  `math.log(-1)` would have crashed); suppressing `MatrixRankWarning` with `warnings.catch_warnings()` (process-global,
  unsafe under concurrent Jacobi); switching `sparse_direct` to `splu` (could change output bits of existing successful
  records; deferred to F1-c with measurement).
- Independent static review: PASS; M1/M2/M3/N2 applied (see `docs/work/REMEDIATION_2026-10-18.md`).
- Tests: **NOT RUN**. Executed only `ast.parse` of every changed file, `git diff --check`, and stdlib `math` probes.

## 2026-10-18 -- Post-merge remediation: Batch D (M1C/M1B verification readiness), same worktree, uncommitted

- D1-3 (`conduction1d_transient_fv.py`, not pinned): the energy admission's relative tolerance now applies to the
  step's exchanged energy `max(sum|C*dT|, dt*(|boundary|+|sources|))` instead of energy from 0 K, plus a labelled
  64*eps machine-precision floor; `conservation_rtol` must lie in (0, 1); the binding records both terms;
  implementation reference 0.2.0.
- D3-2 (`numerical/vertex_state.py`, not pinned): optional declared `AmountDistribution1D` for `transfer_state`
  (split by the integral of a storage weight); default behaviour and existing receipt identity unchanged.
- Tests (hand-derived, independent of the implementation): heterogeneous capacity and equilibrium, exact
  two-material steady state, datum invariance, a closed-slab leak the old scale admitted, rtol bounds, M1B
  heterogeneous refine (length split vs weighted split), distribution refusals.
- Rejected approaches: (1) a solver-floor equal to the admitted row allowance -- it would make the balance check
  implied by the row check (a weakening); (2) including interior face powers in the exchange scale -- they cancel in
  the balance and made the tolerance grow with node count (review MAJOR); (3) a unit-spelling identity test -- pint's
  canonical ordering could not be verified without running it.
- Recorded OD-33 (M1D must adopt the weighted transfer, or stay homogeneous-only).
- Independent static review: CHANGES REQUIRED (1 MAJOR, 3 MINOR) -> all acted on.
- Tests: **NOT RUN**. Executed only `ast.parse` of every changed file and `git diff --check`.

## 2026-10-18 -- Post-merge remediation: Batch E (runtime failure recovery, OD-22 evidence), same worktree, uncommitted

- E4-2 (`execution/multiphysics/acceleration.py`, not pinned): an event-aligned re-run's `begin_window` now logs the
  approximation the outer attempt had staged when it drops it.
- E4-3 (`execution/multiphysics/runtime.py`, certified): `_finalize_all` finalizes every participant even when one
  fails; failures are noted on the propagating exception, or raised together on the success path.
- E4-4 (`runtime.py`, certified): a refusal raised before any participant code runs no longer retires the
  participants (`_participants_touched`); a run started from inside a running run is refused and retires the runtime.
- OD-22: exact-rational replay (`docs/work/proposals/od22_replay.py`) gives 7 without memory, 4 with growth 2;
  proposed test patch `docs/work/proposals/OD22_window_control_subdivisions.patch`, not applied (owner decision).
- Known gaps left: a refusal between participant initialization and the main `try` still skips finalize
  (pre-existing); no runtime-level IMVJ + event-alignment test.
- Independent static review: PASS; MINOR-1 (re-entrancy) and the reason-text NOTE applied; MINOR-2/3 recorded.
- CERTIFICATION PENDING (OD-3) for `runtime.py`.
- Tests: **NOT RUN**. Executed only `ast.parse` of every changed file, `git diff --check`, and the pure-`fractions`
  replay script (`python -B -I docs/work/proposals/od22_replay.py`: "no memory: 7 subdivisions", "growth 2: 4").

## 2026-10-18 -- Post-merge remediation: Batch F (performance, output-identical slice), same worktree, uncommitted

- No benchmark was authorized and the host cannot import scipy/pint: **no speedup is claimed**; only changes whose
  outputs are identical (or strictly safer) were made.
- F2-1/F2-3 (`conduction1d_transient_fv.py`): build identity computed once at import (same bytes, same digest);
  private `_superlu` import and the build-digest file reads are guarded, so a SciPy layout change or an unreadable
  file makes the provider unavailable instead of the model unimportable.
- F1-d (`numerical/nonlinear.py`): the exit diagnostic reuses the admission estimate when matrix object and
  threshold are the same.
- F3-1 (`execution/multiphysics/runtime.py`, certified): `_next_window_width` scans back only over the current
  window's log block (ordering invariant proven by the reviewer).
- Not changed, recorded as proposals awaiting measurement (`docs/work/REMEDIATION_2026-10-18.md`): F1-a/b/c
  (factorization reuse changes recorded-condition semantics or output bits), F3-2..4, and F2-4 as OD-34
  (incremental verification would weaken tamper detection).
- Independent static review: PASS; MINOR-1/2/3 and the NOTE applied.
- Tests: **NOT RUN**. Executed only `ast.parse` of every changed file and `git diff --check`.

## 2026-10-18 -- Post-merge remediation: Batch B (identity integrity), same worktree, uncommitted

- OD-30 fast-state half (`multiscale/runtime.py` not pinned; `system_runtime/authorities.py` certified): the
  `MultiscaleAuthority` identity now states the authority's own declared fast state
  (`MultiTimescaleRuntime.declared_fast_state_digest`, pure, same normalization as `_state_from`) instead of the
  runtime's value at construction; the fast state is snapshotted and every returned record must declare the stated one.
  Payload shape unchanged (no version key); digests move only where the fast state was misstated -- including the
  flagship `cell-cooling-aging` authority on regeneration. Committed bundles still verify (they re-derive from stored
  files). The FAILED-vs-REFUSED half of OD-30 is not changed.
- B3a: `MultiphysicsAuthority` snapshots the scenario at preflight per node and refuses a call whose context was
  swapped after admission (checked before and after `run_kwargs`).
- Rejected approach: an `identity_version: 2` key -- it would move every multiscale digest, including correct ones.
- Independent static review: PASS; MINOR-1/2 and NOTE-2/4 applied; NOTE-1/3 recorded.
- CERTIFICATION PENDING (OD-3) for `authorities.py`.
- Tests: **NOT RUN**. Executed only `ast.parse` of every changed file and `git diff --check`.


### Post-merge verification 2026-10-18 / recipe-1
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase2_review_regressions.py`
- Result: EXECUTED, exit 2, 1.597s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\recipe-1.log`.
```text
    from ..fields.definition import FieldLocation
src\engcore\scientific\fields\__init__.py:30: in <module>
    from .conditions import (
src\engcore\scientific\fields\conditions.py:25: in <module>
    from .definition import FieldDefinition
src\engcore\scientific\fields\definition.py:24: in <module>
    from ..semantics import extend_payload, semantic_extension
src\engcore\scientific\semantics.py:13: in <module>
    from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
E   ImportError: cannot import name 'CONSERVATION_TOLERANCE' from partially initialized module 'engcore.scientific.composition.conversion' (most likely due to a circular import) (D:\forge-main-337519d1\src\engcore\scientific\composition\conversion.py)
=========================== short test summary info ===========================
ERROR tests/test_phase2_review_regressions.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.92s
```


### Post-merge verification 2026-10-18 / recipe-2
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"`
- Result: EXECUTED, exit 2, 1.765s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\recipe-2.log`.
```text
    from ..fields.definition import FieldLocation
src\engcore\scientific\fields\__init__.py:30: in <module>
    from .conditions import (
src\engcore\scientific\fields\conditions.py:25: in <module>
    from .definition import FieldDefinition
src\engcore\scientific\fields\definition.py:24: in <module>
    from ..semantics import extend_payload, semantic_extension
src\engcore\scientific\semantics.py:13: in <module>
    from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
E   ImportError: cannot import name 'CONSERVATION_TOLERANCE' from partially initialized module 'engcore.scientific.composition.conversion' (most likely due to a circular import) (D:\forge-main-337519d1\src\engcore\scientific\composition\conversion.py)
=========================== short test summary info ===========================
ERROR tests/test_core_guards.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.11s
```


### Post-merge verification 2026-10-18 / recipe-3
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_newton_domain_errors.py tests/test_phase3_br13_numerical_stability.py tests/numerical/test_robust_nonlinear.py`
- Result: EXECUTED, exit 2, 2.548s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\recipe-3.log`.
```text
    from ..fields.definition import FieldLocation
src\engcore\scientific\fields\__init__.py:30: in <module>
    from .conditions import (
src\engcore\scientific\fields\conditions.py:25: in <module>
    from .definition import FieldDefinition
src\engcore\scientific\fields\definition.py:24: in <module>
    from ..semantics import extend_payload, semantic_extension
src\engcore\scientific\semantics.py:13: in <module>
    from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
E   ImportError: cannot import name 'CONSERVATION_TOLERANCE' from partially initialized module 'engcore.scientific.composition.conversion' (most likely due to a circular import) (D:\forge-main-337519d1\src\engcore\scientific\composition\conversion.py)
=========================== short test summary info ===========================
ERROR tests/numerical/test_newton_domain_errors.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.90s
```


### Post-merge verification 2026-10-18 / recipe-4
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_phase1_sparse_correctness.py tests/test_interface_flux_execution.py`
- Result: EXECUTED, exit 2, 2.128s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\recipe-4.log`.
```text
    from ..fields.definition import FieldLocation
src\engcore\scientific\fields\__init__.py:30: in <module>
    from .conditions import (
src\engcore\scientific\fields\conditions.py:25: in <module>
    from .definition import FieldDefinition
src\engcore\scientific\fields\definition.py:24: in <module>
    from ..semantics import extend_payload, semantic_extension
src\engcore\scientific\semantics.py:13: in <module>
    from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
E   ImportError: cannot import name 'CONSERVATION_TOLERANCE' from partially initialized module 'engcore.scientific.composition.conversion' (most likely due to a circular import) (D:\forge-main-337519d1\src\engcore\scientific\composition\conversion.py)
=========================== short test summary info ===========================
ERROR tests/numerical/test_phase1_sparse_correctness.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.54s
```


### Post-merge verification 2026-10-18 / recipe-5
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- Result: EXECUTED, exit 2, 2.505s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\recipe-5.log`.
```text
    from ..fields.definition import FieldLocation
src\engcore\scientific\fields\__init__.py:30: in <module>
    from .conditions import (
src\engcore\scientific\fields\conditions.py:25: in <module>
    from .definition import FieldDefinition
src\engcore\scientific\fields\definition.py:24: in <module>
    from ..semantics import extend_payload, semantic_extension
src\engcore\scientific\semantics.py:13: in <module>
    from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
E   ImportError: cannot import name 'CONSERVATION_TOLERANCE' from partially initialized module 'engcore.scientific.composition.conversion' (most likely due to a circular import) (D:\forge-main-337519d1\src\engcore\scientific\composition\conversion.py)
=========================== short test summary info ===========================
ERROR tests/test_m1c_transient_fv.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.80s
```


### Post-merge verification 2026-10-18 / recipe-6
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase3_br14_iqn_imvj.py tests/test_multiphysics_window_control.py`
- Result: EXECUTED, exit 2, 2.106s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\recipe-6.log`.
```text
    from ..fields.definition import FieldLocation
src\engcore\scientific\fields\__init__.py:30: in <module>
    from .conditions import (
src\engcore\scientific\fields\conditions.py:25: in <module>
    from .definition import FieldDefinition
src\engcore\scientific\fields\definition.py:24: in <module>
    from ..semantics import extend_payload, semantic_extension
src\engcore\scientific\semantics.py:13: in <module>
    from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
E   ImportError: cannot import name 'CONSERVATION_TOLERANCE' from partially initialized module 'engcore.scientific.composition.conversion' (most likely due to a circular import) (D:\forge-main-337519d1\src\engcore\scientific\composition\conversion.py)
=========================== short test summary info ===========================
ERROR tests/test_phase3_br14_iqn_imvj.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.46s
```


### Post-merge verification 2026-10-18 / recipe-7
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_od30_multiscale_authority_identity.py tests/test_system_runtime_scenario_identity.py tests/test_system_runtime_multiscale_identity.py tests/test_multiscale_review_fixes.py`
- Result: EXECUTED, exit 2, 3.207s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\recipe-7.log`.
```text
    from ..fields.definition import FieldLocation
src\engcore\scientific\fields\__init__.py:30: in <module>
    from .conditions import (
src\engcore\scientific\fields\conditions.py:25: in <module>
    from .definition import FieldDefinition
src\engcore\scientific\fields\definition.py:24: in <module>
    from ..semantics import extend_payload, semantic_extension
src\engcore\scientific\semantics.py:13: in <module>
    from .composition.conversion import CONSERVATION_TOLERANCE, LossPath
E   ImportError: cannot import name 'CONSERVATION_TOLERANCE' from partially initialized module 'engcore.scientific.composition.conversion' (most likely due to a circular import) (D:\forge-main-337519d1\src\engcore\scientific\composition\conversion.py)
=========================== short test summary info ===========================
ERROR tests/test_od30_multiscale_authority_identity.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 2.39s
```


### Post-merge verification 2026-10-18 / corrected-recipe-1
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase2_review_regressions.py`
- Result: EXECUTED, exit 1, 2.566s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\corrected-recipe-1.log`.
```text
                    # refusal in whatever wording -- means a forward tear became reachable
>                   assert "leaves a cycle after its tears" in str(exc), (sorted(cp.edge_key(d) for d in subset), str(exc))
E                   AssertionError: ([('electrical_dc:electrothermal-series-R1-R2-R3', 'resistor_power:R1', 'thermal-lumped-R1', 'heat_input'), ('electric...r:R3', 'thermal-lumped-R3', 'heat_input')], 'legacy quantity meanings differ; explicit semantic migration is required')
E                   assert 'leaves a cycle after its tears' in 'legacy quantity meanings differ; explicit semantic migration is required'
E                    +  where 'legacy quantity meanings differ; explicit semantic migration is required' = str(InvalidScientificProblem('legacy quantity meanings differ; explicit semantic migration is required'))

tests\test_phase2_review_regressions.py:147: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_phase2_review_regressions.py::test_a_redundant_forward_tear_is_refused
FAILED tests/test_phase2_review_regressions.py::test_a_tampered_plan_with_a_forward_tear_is_refused_by_the_runtime_build
FAILED tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[1]
FAILED tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[2]
FAILED tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[3]
5 failed, 4 passed in 1.91s
```


### Post-merge verification 2026-10-18 / corrected-recipe-2
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"`
- Result: EXECUTED, exit 1, 7.544s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\corrected-recipe-2.log`.
```text
E       AssertionError: {'engcore.domains.thermal_models.conduction1d_transient_fv': "InvalidModelRealization: realization 'thermal.conduction...t declare at least one provided scientific capability; a realization that provides nothing can never satisfy anything"}
E       assert not {'engcore.domains.thermal_models.conduction1d_transient_fv': "InvalidModelRealization: realization 'thermal.conduction...t declare at least one provided scientific capability; a realization that provides nothing can never satisfy anything"}

tests\test_core_guards.py:1322: AssertionError
============================== warnings summary ===============================
tests\test_core_guards.py:102: 12 warnings
  D:\forge-main-337519d1\tests\test_core_guards.py:102: DeprecationWarning: 'maxsplit' is passed as positional argument
    distribution = re.split(r"[\s<>=!~\[;]", requirement.strip(), 1)[0]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_core_guards.py::test_the_discovery_found_exactly_the_repository
FAILED tests/test_core_guards.py::test_the_solver_discovery_found_the_adapters
2 failed, 1 passed, 271 deselected, 12 warnings in 6.39s
```


### Post-merge verification 2026-10-18 / corrected-recipe-3
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_newton_domain_errors.py tests/test_phase3_br13_numerical_stability.py tests/numerical/test_robust_nonlinear.py`
- Result: EXECUTED, exit 0, 2.098s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\corrected-recipe-3.log`.
```text
........................................................................ [ 91%]
.......                                                                  [100%]
79 passed in 1.43s
```


### Post-merge verification 2026-10-18 / corrected-recipe-4
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_phase1_sparse_correctness.py tests/test_interface_flux_execution.py`
- Result: EXECUTED, exit 1, 2.553s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\corrected-recipe-4.log`.
```text
    def test_unqualified_direct_mapper_escape_and_stale_support_refuse():
        a, b, fa, fb, transfer = fixture()
        store = InMemoryBulkStore()
        record, _ = FieldValue(fa, a, np.array([[2.,6.]])).store(store)
>       with pytest.raises(InvalidScientificProblem, match="A-4"):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'A-4'
E         Actual message: 'field meanings, kinds or measures differ; explicit transformation required'

tests\test_interface_flux_execution.py:189: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_interface_flux_execution.py::test_unqualified_direct_mapper_escape_and_stale_support_refuse
1 failed, 41 passed in 1.88s
```


### Post-merge verification 2026-10-18 / corrected-recipe-5
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- Result: EXECUTED, exit 2, 2.665s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\corrected-recipe-5.log`.
```text
_______________ ERROR collecting tests/test_m1c_transient_fv.py _______________
tests\test_m1c_transient_fv.py:26: in <module>
    from engcore.domains.thermal_models.conduction1d_transient_fv import (
src\engcore\domains\thermal_models\conduction1d_transient_fv.py:60: in <module>
    REALIZATION = ModelRealizationDefinition(
<string>:14: in __init__
    ???
src\engcore\scientific\realizations\definition.py:297: in __post_init__
    raise InvalidModelRealization(
E   engcore.scientific.errors.InvalidModelRealization: realization 'thermal.conduction1d.transient_piecewise_linear.vertex_fv_be' must declare at least one provided scientific capability; a realization that provides nothing can never satisfy anything
=========================== short test summary info ===========================
ERROR tests/test_m1c_transient_fv.py - engcore.scientific.errors.InvalidModel...
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.88s
```


### Post-merge verification 2026-10-18 / corrected-recipe-6
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase3_br14_iqn_imvj.py tests/test_multiphysics_window_control.py`
- Result: EXECUTED, exit 1, 2.027s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\corrected-recipe-6.log`.
```text
>       assert _subdivisions(plain) == 8 and _subdivisions(remembered) == 4
E       AssertionError: assert (7 == 8)
E        +  where 7 = _subdivisions(MultiphysicsRunRecord(run_id='wc', graph=PhysicsGraph(graph_id='wc-explicit', participants=(ParticipantSpec(participan...b0b488bfe16e27c9cb1fe030f456af6dc01', end_values=(), scenario_digest='')), termination=None, quantities_of_interest=()))

tests\test_multiphysics_window_control.py:298: AssertionError
============================== warnings summary ===============================
tests/test_phase3_br14_iqn_imvj.py::test_a_non_finite_carried_step_falls_back_and_discards_the_approximation
  D:\forge-main-337519d1\src\engcore\execution\multiphysics\acceleration.py:245: RuntimeWarning: invalid value encountered in matmul
    step = new - carried @ residual

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable
1 failed, 67 passed, 1 warning in 1.45s
```


### Post-merge verification 2026-10-18 / corrected-recipe-7
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_od30_multiscale_authority_identity.py tests/test_system_runtime_scenario_identity.py tests/test_system_runtime_multiscale_identity.py tests/test_multiscale_review_fixes.py`
- Result: EXECUTED, exit 0, 64.277s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\corrected-recipe-7.log`.
```text
........................................................................ [ 86%]
...........                                                              [100%]
83 passed in 63.55s (0:01:03)
```


### Post-merge verification 2026-10-18 / bounded-1
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --changed --dry-run`
- Result: EXECUTED, exit 0, 16.301s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\bounded-1.log`.
```text
  src/engcore/systems/multibody.py
  src/engcore/systems/products/__init__.py
  src/engcore/systems/products/drone.py
  src/engcore/systems/products/drone_coupled.py
  src/engcore/systems/products/drone_ratings.py
  src/engcore/systems/products/hvac.py
  src/engcore/systems/products/motor.py
  src/engcore/systems/products/template.py
  src/engcore/systems/products/vehicle.py
  src/engcore/systems/twin_revision.py
  tests/conftest.py
  tools/forge_check.py
  tools/test_impact.py
$ 'C:\Users\dev_kaeem\AppData\Local\Python\pythoncore-3.14-64\python.exe' -m pytest -q -m 'not expensive'
```


### Post-merge verification 2026-10-18 / bounded-2
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_post_merge_import_smoke.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- Result: EXECUTED, exit 1, 12.540s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\bounded-2.log`.
```text
        runtime, _ = session()
        original = state(runtime)
        split = refine(runtime)
        object.__setattr__(split.change.bisections[0].children[0], "parent_id", "forged")
>       with pytest.raises(NumericalRefusal, match="tampered|unissued"):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AssertionError: Regex pattern did not match.
E         Expected regex: 'tampered|unissued'
E         Actual message: 'conflicting issued mesh registry key'

tests\test_m1a_mesh_lineage.py:173: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_m1a_mesh_lineage.py::test_nested_record_tampering_poisoned_lineage_is_fail_closed
1 failed, 84 passed in 11.92s
```


### Post-merge verification 2026-10-18 / bounded-3
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- Result: EXECUTED, exit 1, 12.629s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\bounded-3.log`.
```text
FAILED tests/claims/test_scientific_diagnostics.py::test_model_form_gap_becomes_a_root_cause_and_a_non_guaranteed_corrective_action
FAILED tests/claims/test_scientific_diagnostics.py::test_admissible_model_data_mismatch_is_diagnosed_without_becoming_model_form_uq
FAILED tests/claims/test_scientific_diagnostics.py::test_sensitivity_can_rank_repair_hypotheses_but_never_establish_causality
FAILED tests/claims/test_scientific_diagnostics.py::test_sealed_sensitivity_from_another_assessment_is_refused
ERROR tests/test_forge_check.py::test_every_kind_of_change_is_detected_and_committed_only_is_narrower
ERROR tests/test_forge_check.py::test_an_uncommitted_change_on_the_base_branch_itself_is_detected
ERROR tests/test_forge_check.py::test_an_unknown_base_fails_loudly - Permissi...
ERROR tests/test_capability_completion.py::test_a_superseded_schema_is_refused_not_read
ERROR tests/claims/test_sria_context_authority.py::test_same_qoi_same_value_wrong_charter_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_wrong_decision_id_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_changed_context_cannot_become_valid
ERROR tests/claims/test_impact_replay.py::test_untracked_manifest_digest_changes_with_file_content
19 failed, 251 passed, 8 errors in 11.62s
$ 'C:\Users\dev_kaeem\AppData\Local\Python\pythoncore-3.14-64\python.exe' -m pytest -q tests/test_repository_architecture.py tests/test_core_api_layering.py tests/test_scientific_regression_manifest.py tests/test_forge_check.py tests/test_agent_workflow_contract.py tests/test_capability_completion.py tests/claims/test_claims_assessment.py::test_a_t3_claim_at_the_benchmark_point_is_supported_with_benchmark_validation tests/claims/test_claims_assessment.py::test_the_value_compared_is_the_reports_never_the_callers tests/claims/test_claims_assessment.py::test_a_violated_comparison_without_the_required_evidence_is_not_a_contradiction tests/claims/test_claims_assessment.py::test_verification_cannot_satisfy_a_validation_requirement tests/claims/test_claims_assessment.py::test_a_model_outside_its_domain_never_contradicts_the_claim tests/claims/test_claims_assessment.py::test_asking_for_more_evidence_never_firms_up_the_answer tests/claims/test_claims_compiler.py::test_a_complete_t3_claim_is_ready_on_the_benchmark_capability tests/claims/test_claims_compiler.py::test_compilation_never_executes tests/claims/test_claims_compiler.py::test_a_candidate_outside_its_validated_domain_is_unsupported_not_contradicted tests/claims/test_claims_selection.py::test_unknown_applicability_never_beats_a_known_in_domain_candidate tests/claims/test_claims_selection.py::test_two_applicable_candidates_are_ambiguous_not_ranked tests/claims/test_sria_context_authority.py::test_same_qoi_same_value_wrong_charter_cannot_become_valid tests/claims/test_sria_context_authority.py::test_same_evidence_wrong_decision_id_cannot_become_valid tests/claims/test_sria_context_authority.py::test_same_evidence_changed_context_cannot_become_valid tests/claims/test_quantitative_uq.py::test_a_second_order_sequence_is_quantified_and_brackets_the_exact_value tests/claims/test_quantitative_uq.py::test_every_rule_failure_is_unknown_never_zero tests/claims/test_quantitative_uq.py::test_an_interval_that_crosses_the_boundary_is_insufficient tests/claims/test_quantitative_uq.py::test_removing_uq_evidence_cannot_improve_the_verdict tests/claims/test_quantitative_uq.py::test_numerical_uq_cannot_satisfy_model_form tests/claims/test_quantitative_uq.py::test_parameter_uq_cannot_satisfy_a_numerical_demand tests/claims/test_evidence_policy.py::test_more_risk_never_requires_less_evidence_within_a_profile tests/claims/test_evidence_policy.py::test_consequence_is_stated_never_inferred tests/claims/test_evidence_policy.py::test_a_policy_cannot_grant_what_the_run_lacks tests/claims/test_external_evidence.py::test_an_unpinned_measurement_is_weak_however_good_it_looks tests/claims/test_external_evidence.py::test_a_pinned_applicable_quantified_measurement_is_admissible_and_still_not_validation tests/claims/test_external_evidence.py::test_offered_external_evidence_never_changes_the_verdict_or_the_levels tests/claims/test_evidence_gaps_next_experiment.py::test_every_verdict_is_fully_explained_by_its_blocking_gaps tests/claims/test_evidence_gaps_next_experiment.py::test_recommendations_address_real_gaps_and_promise_nothing tests/claims/test_sensitivity_robustness_challenge.py::test_a_challenge_never_changes_the_verdict tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result tests/claims/test_scientific_diagnostics.py::test_model_form_gap_becomes_a_root_cause_and_a_non_guaranteed_corrective_action tests/claims/test_scientific_diagnostics.py::test_admissible_model_data_mismatch_is_diagnosed_without_becoming_model_form_uq tests/claims/test_scientific_diagnostics.py::test_sensitivity_can_rank_repair_hypotheses_but_never_establish_causality tests/claims/test_scientific_diagnostics.py::test_sealed_sensitivity_from_another_assessment_is_refused tests/claims/test_impact_replay.py::test_current_oracle_digest_drift_is_detected tests/claims/test_impact_replay.py::test_a_removed_policy_profile_is_detected tests/claims/test_impact_replay.py::test_untracked_manifest_digest_changes_with_file_content tests/claims/test_measurement_dataset.py::test_raw_nasa_row_cannot_masquerade_as_complete_battery_evidence tests/claims/test_model_form_discrepancy.py::test_calibration_envelope_must_survive_independent_holdout tests/claims/test_model_form_discrepancy.py::test_same_independence_group_cannot_leak_across_the_split tests/claims/test_model_form_discrepancy.py::test_residuals_below_known_uncertainty_do_not_establish_zero_model_form tests/domains/test_battery_thevenin.py::test_rest_interval_relaxes_polarization_without_changing_soc tests/claims/test_nasa_battery_aging_adapter.py::test_direct_voltage_observation_remains_nonadmissible_without_calibration_uq tests/claims/test_nasa_battery_aging_adapter.py::test_soc_trace_is_explicitly_derived_not_measurement_evidence tests/domainpacks/test_domain_pack_v1.py::test_registering_a_pack_does_not_enable_it tests/domainpacks/test_domain_pack_v1.py::test_manifest_runtime_drift_is_refused_before_registration tests/scientific/equations/test_dimensions.py::test_addition_rejects_incompatible_dimensions tests/scientific/equations/test_dimensions.py::test_dimensionless_functions_reject_dimensional_arguments tests/scientific/equations/test_law.py::test_law_rejects_undeclared_symbol tests/scientific/equations/test_law.py::test_law_rejects_wrong_binding_dimension tests/scientific/equations/test_adversarial.py::test_expression_payload_is_data_not_python_code tests/scientific/equations/test_reference.py::test_law_reference_rejects_changed_contract_under_same_id tests/scientific/validation_core/test_report.py::test_accepted_report_cannot_hide_failed_stage tests/scientific/replay_core/test_verify.py::test_environment_drift_refuses_replay_verification tests/credibility/evidence_graph/test_conflict.py::test_support_and_contradict_same_edge_is_conflict tests/uq/budget/test_correlation.py::test_unknown_correlation_component_is_refused tests/scientific/verification/test_adjudication.py::test_agreement_without_independence_is_not_verified tests/execution/orchestration/test_retry.py::test_failed_attempt_retries_only_inside_budget tests/scientific/certification_core/test_verify.py::test_missing_required_gate_refuses_certification tests/scientific/assurance_flow/test_decision.py::test_trust_requires_all_three_layers_green tests/core_extensions/test_new_core_mutations.py::test_new_core_guard_mutations_are_killed tests/core_extensions/test_new_core_adversarial.py::test_validated_model_form_cannot_have_zero_half_width tests/uq/model_form/test_study.py::test_compatible_units_are_normalized_before_residual_comparison tests/uq/model_form/test_authority.py::test_authority_requires_independent_review_identity tests/claims/test_model_form_uncertainty.py::test_unvalidated_model_form_cannot_cross_authority_boundary tests/scientific/verification/test_serialization.py::test_verification_round_trip_rederives_decision tests/scientific/certification_core/test_serialization.py::test_certification_round_trip_rederives_verification tests/uq/budget/test_serialization.py::test_budget_round_trip_recomputes_aggregate tests/credibility/test_replay_binding.py::test_assurance_bundle_becomes_content_addressed_replay_artifact tests/scientific/verification/test_route_bound_independence.py::test_every_agreeing_route_requires_its_own_independence_evidence tests/uq/budget/test_psd.py::test_non_psd_correlation_matrix_is_refused_even_when_each_pair_is_in_range tests/credibility/evidence_graph/test_lineage.py::test_derived_from_cycle_is_refused tests/execution/orchestration/test_runner.py::test_runner_falls_back_deterministically_until_converged tests/scientific/equations/test_derivatives_v2.py::test_derivative_binding_with_wrong_dimension_is_refused tests/scientific/equations/test_constraints_v2.py::test_constraint_wire_verdict_is_rederived tests/scientific/equations/test_assumptions_v2.py::test_checkable_assumption_can_be_satisfied_violated_or_unknown tests/scientific/equations/test_conditions_v2.py::test_condition_refuses_a_conflicting_location_binding tests/scientific/equations/test_transformations_v2.py::test_safe_symbol_isolation_records_nonzero_side_condition tests/scientific/equations/test_nondimensional_v2.py::test_ohm_law_nondimensionalization_produces_dimensionless_residual_equation tests/scientific/equations/test_differential_ode_v2.py::test_ode_contract_classifies_order_conditions_and_round_trips tests/scientific/equations/test_differential_pde_v2.py::test_two_space_dimensional_heat_equation_is_dimensionally_complete tests/scientific/equations/test_law_system_v2.py::test_law_system_binds_assumptions_conditions_and_differential_evidence tests/scientific/equations/test_differential_ode_v2.py::test_differential_problem_rejects_derivative_on_undeclared_independent_variable tests/uq/model_form/test_authority.py::test_authority_requires_exact_target_scope tests/uq/model_form/test_authority.py::test_authority_requires_estimator_qualification tests/uq/model_form/test_serialization.py::test_v1_payload_is_read_as_unscoped_and_cannot_gain_scope tests/uq/combined/test_lineage.py::test_shared_primitive_lineage_is_refused_before_combination tests/uq/combined/test_standard_rss.py::test_rss_requires_explicit_pair_correlation_by_default tests/uq/combined/test_psd.py::test_combined_standard_uq_refuses_non_psd_declared_correlation_matrix tests/uq/combined/test_intervals.py::test_conservative_interval_adds_asymmetric_widths_without_independence_claim tests/uq/combined/test_intervals.py::test_hybrid_interval_requires_explicit_k_and_records_it tests/uq/combined/test_serialization.py::test_combination_wire_output_is_recomputed_from_inputs tests/uq/combined/test_model_form_integration.py::test_authorized_model_form_interval_combines_with_numerical_without_losing_source_identity tests/scientific/verification/test_dependency_independence_v2.py::test_dependency_manifests_derive_none_partial_strong_and_external tests/scientific/verification/test_planning_v2.py::test_plan_rejects_low_verification_level_and_partial_independence tests/scientific/verification/test_external_requirement_v2.py::test_require_external_policy_is_incomplete_when_only_internal_strong_route_exists tests/scientific/verification/test_quantity_comparison_v2.py::test_dimensionally_foreign_verification_value_is_refused tests/execution/test_verification_runner_identity_v2.py::test_backend_identity_must_match_planned_route_before_execution tests/scientific/verification/test_replay_v2.py::test_verification_plan_refuses_forged_selected_route tests/scientific/verification/test_replay_v2.py::test_verification_run_refuses_forged_verdict tests/scientific/verification/test_orchestration_v2.py::test_plan_observations_produce_verified_report_only_when_all_required_routes_arrive_and_agree tests/scientific/knowledge/test_source_trust.py::test_same_source_id_with_changed_document_digest_is_not_trusted tests/scientific/knowledge/test_freshness.py::test_unconfigured_source_class_is_unknown_not_not_applicable tests/scientific/knowledge/test_claim_snapshot.py::test_numeric_claim_interval_must_contain_claimed_value tests/scientific/knowledge/test_admission.py::test_changed_context_is_refused_even_for_pinned_current_source tests/scientific/knowledge/test_ingestion.py::test_ingestion_receipt_refuses_missing_or_extra_claim_digest tests/scientific/knowledge/test_conflicts.py::test_nonoverlapping_explicit_intervals_are_recorded_as_disagreement tests/credibility/evidence_graph/test_knowledge_bridge.py::test_tampered_pin_identity_rederives_untrusted_and_strict_policy_refuses tests/credibility/evidence_graph/test_knowledge_bridge.py::test_evidence_wire_trust_status_is_rederived_not_trusted tests/credibility/evidence_graph/test_knowledge_bridge.py::test_provenance_freshness_status_is_rederived_not_trusted tests/credibility/evidence_graph/test_knowledge_bridge.py::test_unadmitted_context_never_crosses_knowledge_to_evidence_bridge tests/credibility/test_knowledge_replay_binding.py::test_knowledge_snapshot_and_evidence_graph_are_content_addressed_replay_artifacts tests/scientific/replay_core/test_environment_v2.py::test_runtime_dependency_digest_requires_actual_sha256_not_only_length tests/scientific/replay_core/test_environment_v2.py::test_replay_tolerance_refuses_nan_and_infinity tests/scientific/replay_core/test_manifest_v2.py::test_missing_required_artifact_kind_is_refused tests/scientific/replay_core/test_manifest_v2.py::test_replay_exact_kinds_must_be_required_by_profile tests/scientific/replay_core/test_manifest_v2.py::test_manifest_wire_digest_is_rederived tests/scientific/replay_core/test_run_replay_v2.py::test_replay_requires_binding_to_exact_expected_manifest_and_matching_contract tests/scientific/replay_core/test_run_replay_v2.py::test_missing_or_out_of_tolerance_output_refuses_replay tests/scientific/replay_core/test_run_replay_v2.py::test_run_replay_wire_verification_is_rederived tests/scientific/replay_core/test_lineage_v2.py::test_manifest_lineage_refuses_missing_or_wrong_parent_identity tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_rederives_validation_instead_of_trusting_accepted_flag tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_requires_complete_independent_verification tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_refuses_certification_profile_with_no_required_gate tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_binds_provenance_commit_to_certification_commit tests/credibility/test_assurance_manifest_v2.py::test_full_production_manifest_can_be_replayed_with_new_run_provenance_and_typed_output_tolerance tests/credibility/test_assurance_replay_bundle_v2.py::test_production_assurance_bundle_round_trips_all_payloads_and_manifest tests/credibility/test_assurance_replay_bundle_v2.py::test_payload_change_with_old_manifest_is_refused_by_content_addressing tests/credibility/test_assurance_replay_bundle_v2.py::test_rehashed_forged_validation_is_still_refused_by_semantic_revalidation tests/credibility/test_assurance_replay_bundle_v2.py::test_rehashed_provenance_with_wrong_certified_commit_is_still_refused tests/scientific/replay_core/test_manifest_v2.py::test_whitespace_parent_run_id_is_refused_even_with_a_digest tests/scientific/replay_core/test_run_replay_v2.py::test_run_replay_boundary_requires_typed_manifests_expectations_and_observations
```


### Post-merge verification 2026-10-18 / bounded-4
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -I docs/work/proposals/od22_replay.py`
- Result: EXECUTED, exit 0, 0.084s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\bounded-4.log`.
```text
  [3/4, 1]  subdivisions=1
  [1, 5/4]  subdivisions=1
  [5/4, 3/2]  subdivisions=1
  [3/2, 7/4]  subdivisions=1
  [7/4, 2]  subdivisions=0
growth 2: 4 subdivisions over 8 accepted windows
  [0, 1/4]  subdivisions=1
  [1/4, 1/2]  subdivisions=0
  [1/2, 3/4]  subdivisions=1
  [3/4, 1]  subdivisions=0
  [1, 5/4]  subdivisions=1
  [5/4, 3/2]  subdivisions=0
  [3/2, 7/4]  subdivisions=1
  [7/4, 2]  subdivisions=0
```


### Post-merge verification 2026-10-18 / bounded-5
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase1_coupling_convergence_coverage.py tests/test_electrothermal_vertical.py tests/architecture/test_cross_domain_fixtures.py`
- Result: EXECUTED, exit 1, 3.199s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\bounded-5.log`.
```text
E           assert not True
E            +  where True = any(<generator object test_l3_no_relaxation_appears_anywhere_in_the_module.<locals>.<genexpr> at 0x000002386616FCA0>)

tests\test_electrothermal_vertical.py:1598: AssertionError
============================== warnings summary ===============================
tests/test_phase1_coupling_convergence_coverage.py::test_an_overflowing_iterate_fails_the_window_even_when_nonconvergence_is_allowed
  D:\forge-main-337519d1\src\engcore\execution\multiphysics\relaxation.py:203: RuntimeWarning: overflow encountered in subtract
    residual = new - old

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ===========================
FAILED tests/test_phase1_coupling_convergence_coverage.py::test_a_self_loop_is_a_lagged_edge
FAILED tests/test_electrothermal_vertical.py::test_l3_no_relaxation_appears_anywhere_in_the_module
2 failed, 87 passed, 1 warning in 2.50s
```


### Post-merge verification 2026-10-18 / final-bounded-1
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- Result: EXECUTED, exit 1, 12.795s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\final-bounded-1.log`.
```text
FAILED tests/claims/test_external_evidence.py::test_offered_external_evidence_never_changes_the_verdict_or_the_levels
FAILED tests/claims/test_sensitivity_robustness_challenge.py::test_a_challenge_never_changes_the_verdict
FAILED tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected[study]
FAILED tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected[value]
FAILED tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result
FAILED tests/claims/test_scientific_diagnostics.py::test_model_form_gap_becomes_a_root_cause_and_a_non_guaranteed_corrective_action
FAILED tests/claims/test_scientific_diagnostics.py::test_admissible_model_data_mismatch_is_diagnosed_without_becoming_model_form_uq
FAILED tests/claims/test_scientific_diagnostics.py::test_sensitivity_can_rank_repair_hypotheses_but_never_establish_causality
FAILED tests/claims/test_scientific_diagnostics.py::test_sealed_sensitivity_from_another_assessment_is_refused
ERROR tests/claims/test_sria_context_authority.py::test_same_qoi_same_value_wrong_charter_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_wrong_decision_id_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_changed_context_cannot_become_valid
19 failed, 256 passed, 3 errors in 11.85s
$ 'C:\Users\dev_kaeem\AppData\Local\Python\pythoncore-3.14-64\python.exe' -m pytest -q tests/test_repository_architecture.py tests/test_core_api_layering.py tests/test_scientific_regression_manifest.py tests/test_forge_check.py tests/test_agent_workflow_contract.py tests/test_capability_completion.py tests/claims/test_claims_assessment.py::test_a_t3_claim_at_the_benchmark_point_is_supported_with_benchmark_validation tests/claims/test_claims_assessment.py::test_the_value_compared_is_the_reports_never_the_callers tests/claims/test_claims_assessment.py::test_a_violated_comparison_without_the_required_evidence_is_not_a_contradiction tests/claims/test_claims_assessment.py::test_verification_cannot_satisfy_a_validation_requirement tests/claims/test_claims_assessment.py::test_a_model_outside_its_domain_never_contradicts_the_claim tests/claims/test_claims_assessment.py::test_asking_for_more_evidence_never_firms_up_the_answer tests/claims/test_claims_compiler.py::test_a_complete_t3_claim_is_ready_on_the_benchmark_capability tests/claims/test_claims_compiler.py::test_compilation_never_executes tests/claims/test_claims_compiler.py::test_a_candidate_outside_its_validated_domain_is_unsupported_not_contradicted tests/claims/test_claims_selection.py::test_unknown_applicability_never_beats_a_known_in_domain_candidate tests/claims/test_claims_selection.py::test_two_applicable_candidates_are_ambiguous_not_ranked tests/claims/test_sria_context_authority.py::test_same_qoi_same_value_wrong_charter_cannot_become_valid tests/claims/test_sria_context_authority.py::test_same_evidence_wrong_decision_id_cannot_become_valid tests/claims/test_sria_context_authority.py::test_same_evidence_changed_context_cannot_become_valid tests/claims/test_quantitative_uq.py::test_a_second_order_sequence_is_quantified_and_brackets_the_exact_value tests/claims/test_quantitative_uq.py::test_every_rule_failure_is_unknown_never_zero tests/claims/test_quantitative_uq.py::test_an_interval_that_crosses_the_boundary_is_insufficient tests/claims/test_quantitative_uq.py::test_removing_uq_evidence_cannot_improve_the_verdict tests/claims/test_quantitative_uq.py::test_numerical_uq_cannot_satisfy_model_form tests/claims/test_quantitative_uq.py::test_parameter_uq_cannot_satisfy_a_numerical_demand tests/claims/test_evidence_policy.py::test_more_risk_never_requires_less_evidence_within_a_profile tests/claims/test_evidence_policy.py::test_consequence_is_stated_never_inferred tests/claims/test_evidence_policy.py::test_a_policy_cannot_grant_what_the_run_lacks tests/claims/test_external_evidence.py::test_an_unpinned_measurement_is_weak_however_good_it_looks tests/claims/test_external_evidence.py::test_a_pinned_applicable_quantified_measurement_is_admissible_and_still_not_validation tests/claims/test_external_evidence.py::test_offered_external_evidence_never_changes_the_verdict_or_the_levels tests/claims/test_evidence_gaps_next_experiment.py::test_every_verdict_is_fully_explained_by_its_blocking_gaps tests/claims/test_evidence_gaps_next_experiment.py::test_recommendations_address_real_gaps_and_promise_nothing tests/claims/test_sensitivity_robustness_challenge.py::test_a_challenge_never_changes_the_verdict tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result tests/claims/test_scientific_diagnostics.py::test_model_form_gap_becomes_a_root_cause_and_a_non_guaranteed_corrective_action tests/claims/test_scientific_diagnostics.py::test_admissible_model_data_mismatch_is_diagnosed_without_becoming_model_form_uq tests/claims/test_scientific_diagnostics.py::test_sensitivity_can_rank_repair_hypotheses_but_never_establish_causality tests/claims/test_scientific_diagnostics.py::test_sealed_sensitivity_from_another_assessment_is_refused tests/claims/test_impact_replay.py::test_current_oracle_digest_drift_is_detected tests/claims/test_impact_replay.py::test_a_removed_policy_profile_is_detected tests/claims/test_impact_replay.py::test_untracked_manifest_digest_changes_with_file_content tests/claims/test_measurement_dataset.py::test_raw_nasa_row_cannot_masquerade_as_complete_battery_evidence tests/claims/test_model_form_discrepancy.py::test_calibration_envelope_must_survive_independent_holdout tests/claims/test_model_form_discrepancy.py::test_same_independence_group_cannot_leak_across_the_split tests/claims/test_model_form_discrepancy.py::test_residuals_below_known_uncertainty_do_not_establish_zero_model_form tests/domains/test_battery_thevenin.py::test_rest_interval_relaxes_polarization_without_changing_soc tests/claims/test_nasa_battery_aging_adapter.py::test_direct_voltage_observation_remains_nonadmissible_without_calibration_uq tests/claims/test_nasa_battery_aging_adapter.py::test_soc_trace_is_explicitly_derived_not_measurement_evidence tests/domainpacks/test_domain_pack_v1.py::test_registering_a_pack_does_not_enable_it tests/domainpacks/test_domain_pack_v1.py::test_manifest_runtime_drift_is_refused_before_registration tests/scientific/equations/test_dimensions.py::test_addition_rejects_incompatible_dimensions tests/scientific/equations/test_dimensions.py::test_dimensionless_functions_reject_dimensional_arguments tests/scientific/equations/test_law.py::test_law_rejects_undeclared_symbol tests/scientific/equations/test_law.py::test_law_rejects_wrong_binding_dimension tests/scientific/equations/test_adversarial.py::test_expression_payload_is_data_not_python_code tests/scientific/equations/test_reference.py::test_law_reference_rejects_changed_contract_under_same_id tests/scientific/validation_core/test_report.py::test_accepted_report_cannot_hide_failed_stage tests/scientific/replay_core/test_verify.py::test_environment_drift_refuses_replay_verification tests/credibility/evidence_graph/test_conflict.py::test_support_and_contradict_same_edge_is_conflict tests/uq/budget/test_correlation.py::test_unknown_correlation_component_is_refused tests/scientific/verification/test_adjudication.py::test_agreement_without_independence_is_not_verified tests/execution/orchestration/test_retry.py::test_failed_attempt_retries_only_inside_budget tests/scientific/certification_core/test_verify.py::test_missing_required_gate_refuses_certification tests/scientific/assurance_flow/test_decision.py::test_trust_requires_all_three_layers_green tests/core_extensions/test_new_core_mutations.py::test_new_core_guard_mutations_are_killed tests/core_extensions/test_new_core_adversarial.py::test_validated_model_form_cannot_have_zero_half_width tests/uq/model_form/test_study.py::test_compatible_units_are_normalized_before_residual_comparison tests/uq/model_form/test_authority.py::test_authority_requires_independent_review_identity tests/claims/test_model_form_uncertainty.py::test_unvalidated_model_form_cannot_cross_authority_boundary tests/scientific/verification/test_serialization.py::test_verification_round_trip_rederives_decision tests/scientific/certification_core/test_serialization.py::test_certification_round_trip_rederives_verification tests/uq/budget/test_serialization.py::test_budget_round_trip_recomputes_aggregate tests/credibility/test_replay_binding.py::test_assurance_bundle_becomes_content_addressed_replay_artifact tests/scientific/verification/test_route_bound_independence.py::test_every_agreeing_route_requires_its_own_independence_evidence tests/uq/budget/test_psd.py::test_non_psd_correlation_matrix_is_refused_even_when_each_pair_is_in_range tests/credibility/evidence_graph/test_lineage.py::test_derived_from_cycle_is_refused tests/execution/orchestration/test_runner.py::test_runner_falls_back_deterministically_until_converged tests/scientific/equations/test_derivatives_v2.py::test_derivative_binding_with_wrong_dimension_is_refused tests/scientific/equations/test_constraints_v2.py::test_constraint_wire_verdict_is_rederived tests/scientific/equations/test_assumptions_v2.py::test_checkable_assumption_can_be_satisfied_violated_or_unknown tests/scientific/equations/test_conditions_v2.py::test_condition_refuses_a_conflicting_location_binding tests/scientific/equations/test_transformations_v2.py::test_safe_symbol_isolation_records_nonzero_side_condition tests/scientific/equations/test_nondimensional_v2.py::test_ohm_law_nondimensionalization_produces_dimensionless_residual_equation tests/scientific/equations/test_differential_ode_v2.py::test_ode_contract_classifies_order_conditions_and_round_trips tests/scientific/equations/test_differential_pde_v2.py::test_two_space_dimensional_heat_equation_is_dimensionally_complete tests/scientific/equations/test_law_system_v2.py::test_law_system_binds_assumptions_conditions_and_differential_evidence tests/scientific/equations/test_differential_ode_v2.py::test_differential_problem_rejects_derivative_on_undeclared_independent_variable tests/uq/model_form/test_authority.py::test_authority_requires_exact_target_scope tests/uq/model_form/test_authority.py::test_authority_requires_estimator_qualification tests/uq/model_form/test_serialization.py::test_v1_payload_is_read_as_unscoped_and_cannot_gain_scope tests/uq/combined/test_lineage.py::test_shared_primitive_lineage_is_refused_before_combination tests/uq/combined/test_standard_rss.py::test_rss_requires_explicit_pair_correlation_by_default tests/uq/combined/test_psd.py::test_combined_standard_uq_refuses_non_psd_declared_correlation_matrix tests/uq/combined/test_intervals.py::test_conservative_interval_adds_asymmetric_widths_without_independence_claim tests/uq/combined/test_intervals.py::test_hybrid_interval_requires_explicit_k_and_records_it tests/uq/combined/test_serialization.py::test_combination_wire_output_is_recomputed_from_inputs tests/uq/combined/test_model_form_integration.py::test_authorized_model_form_interval_combines_with_numerical_without_losing_source_identity tests/scientific/verification/test_dependency_independence_v2.py::test_dependency_manifests_derive_none_partial_strong_and_external tests/scientific/verification/test_planning_v2.py::test_plan_rejects_low_verification_level_and_partial_independence tests/scientific/verification/test_external_requirement_v2.py::test_require_external_policy_is_incomplete_when_only_internal_strong_route_exists tests/scientific/verification/test_quantity_comparison_v2.py::test_dimensionally_foreign_verification_value_is_refused tests/execution/test_verification_runner_identity_v2.py::test_backend_identity_must_match_planned_route_before_execution tests/scientific/verification/test_replay_v2.py::test_verification_plan_refuses_forged_selected_route tests/scientific/verification/test_replay_v2.py::test_verification_run_refuses_forged_verdict tests/scientific/verification/test_orchestration_v2.py::test_plan_observations_produce_verified_report_only_when_all_required_routes_arrive_and_agree tests/scientific/knowledge/test_source_trust.py::test_same_source_id_with_changed_document_digest_is_not_trusted tests/scientific/knowledge/test_freshness.py::test_unconfigured_source_class_is_unknown_not_not_applicable tests/scientific/knowledge/test_claim_snapshot.py::test_numeric_claim_interval_must_contain_claimed_value tests/scientific/knowledge/test_admission.py::test_changed_context_is_refused_even_for_pinned_current_source tests/scientific/knowledge/test_ingestion.py::test_ingestion_receipt_refuses_missing_or_extra_claim_digest tests/scientific/knowledge/test_conflicts.py::test_nonoverlapping_explicit_intervals_are_recorded_as_disagreement tests/credibility/evidence_graph/test_knowledge_bridge.py::test_tampered_pin_identity_rederives_untrusted_and_strict_policy_refuses tests/credibility/evidence_graph/test_knowledge_bridge.py::test_evidence_wire_trust_status_is_rederived_not_trusted tests/credibility/evidence_graph/test_knowledge_bridge.py::test_provenance_freshness_status_is_rederived_not_trusted tests/credibility/evidence_graph/test_knowledge_bridge.py::test_unadmitted_context_never_crosses_knowledge_to_evidence_bridge tests/credibility/test_knowledge_replay_binding.py::test_knowledge_snapshot_and_evidence_graph_are_content_addressed_replay_artifacts tests/scientific/replay_core/test_environment_v2.py::test_runtime_dependency_digest_requires_actual_sha256_not_only_length tests/scientific/replay_core/test_environment_v2.py::test_replay_tolerance_refuses_nan_and_infinity tests/scientific/replay_core/test_manifest_v2.py::test_missing_required_artifact_kind_is_refused tests/scientific/replay_core/test_manifest_v2.py::test_replay_exact_kinds_must_be_required_by_profile tests/scientific/replay_core/test_manifest_v2.py::test_manifest_wire_digest_is_rederived tests/scientific/replay_core/test_run_replay_v2.py::test_replay_requires_binding_to_exact_expected_manifest_and_matching_contract tests/scientific/replay_core/test_run_replay_v2.py::test_missing_or_out_of_tolerance_output_refuses_replay tests/scientific/replay_core/test_run_replay_v2.py::test_run_replay_wire_verification_is_rederived tests/scientific/replay_core/test_lineage_v2.py::test_manifest_lineage_refuses_missing_or_wrong_parent_identity tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_rederives_validation_instead_of_trusting_accepted_flag tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_requires_complete_independent_verification tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_refuses_certification_profile_with_no_required_gate tests/credibility/test_assurance_manifest_v2.py::test_production_manifest_binds_provenance_commit_to_certification_commit tests/credibility/test_assurance_manifest_v2.py::test_full_production_manifest_can_be_replayed_with_new_run_provenance_and_typed_output_tolerance tests/credibility/test_assurance_replay_bundle_v2.py::test_production_assurance_bundle_round_trips_all_payloads_and_manifest tests/credibility/test_assurance_replay_bundle_v2.py::test_payload_change_with_old_manifest_is_refused_by_content_addressing tests/credibility/test_assurance_replay_bundle_v2.py::test_rehashed_forged_validation_is_still_refused_by_semantic_revalidation tests/credibility/test_assurance_replay_bundle_v2.py::test_rehashed_provenance_with_wrong_certified_commit_is_still_refused tests/scientific/replay_core/test_manifest_v2.py::test_whitespace_parent_run_id_is_refused_even_with_a_digest tests/scientific/replay_core/test_run_replay_v2.py::test_run_replay_boundary_requires_typed_manifests_expectations_and_observations
```


### Post-merge verification 2026-10-18 / final-bounded-2
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_checkpoint_integrity_hardening.py tests/test_external_participant_checkpoints.py tests/test_provider_participant_checkpoints.py`
- Result: EXECUTED, exit 0, 2.254s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\final-bounded-2.log`.
```text
.......................................................                  [100%]
55 passed in 1.63s
```


### Post-merge verification 2026-10-18 / final-bounded-3
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/architecture/test_quantity_semantics.py tests/test_declared_field_kind_mapping.py`
- Result: EXECUTED, exit 0, 1.974s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\final-bounded-3.log`.
```text
........................................................                 [100%]
56 passed in 1.32s
```


### Post-merge verification 2026-10-18 / final-bounded-4
- Commit: `93ed64b0292e9fea714ac83affb64b71488ac050 + uncommitted import-order correction`; environment: CPython3.14.2 Windows base; process-local platform._wmi=None fallback; BLAS threads=1; PYTHONPATH bootstrap+target/src.
- Exact command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py`
- Result: EXECUTED, exit 0, 30.625s. Log: `D:\forge-main-337519d1\.pytest-review-temp\post-merge-verification\final-bounded-4.log`.
```text
........................................................................ [ 47%]
........................................................................ [ 95%]
.....s.                                                                  [100%]
150 passed, 1 skipped in 29.87s
```


## Post-merge remediation verification closeout — 2026-10-18

Target clean initially at 93ed64b0292e9fea714ac83affb64b71488ac050 (parent 337519d1944bd52c5711a657a926ad855ac8d868), branch fix/post-merge-remediation-2026-10-18. Original inventory 23 files = 8 source + 9 tests + 6 docs/proposals (handoff claimed 10 tests + 5 docs). No existing changes overwritten; all edits uncommitted.

Environment diagnostic commands: bounded subprocess probes stored as exact argv in docs/work/evidence/post_merge_2026_10_18.json. Base import probe and venv Pint probe timed out 20s; venv SciPy probe and wsl.exe --list --quiet timed out 25s. Faulthandler at 12s located platform._wmi_query/_wmi.exec_query. Initial Get-CimInstance process query stalled and its own command was interrupted; no unrelated process touched. Get-Process observed 14 python processes including 6 shared-venv paths; exact session ownership unavailable. No installs/upgrades. Sampled RECORD hashes matched both dependency trees (partial integrity only).

Task-local bootstrap uses platform._wmi=None to activate real Windows fallback. Working imports completed 0.707s. Tests use base CPython3.14.2/NumPy2.4.3/SciPy1.18.0/Pint0.25.3/pytest9.0.2, BLAS thread limits1, PYTHONPATH bootstrap+target/src. This is not supported 3.11/3.12 certification evidence. For final-bounded-1..4 exact PYTEST_ADDOPTS values are preserved in evidence JSON (Windows backslashes; archive caveat below); this removed 5 environmental fixture errors, not 19 failures / 3 bridge type errors.

Bounded correction: scientific/composition/conversion.py publishes unchanged LossPath before importing unchanged ValidityStatus, breaking the import cycle. Independent compatibility reviewer found same symbols/signatures/schema/tolerance/serialization;150 compatibility tests passed, 1 skipped (skip identity not emitted). New 3 fresh-process import tests passed within bounded-2. All original 7 collection-failure logs retained. No scientific identity or count pin changed.

Exact numerical diagnostic command executed (with documented bootstrap/thread environment):
`C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B .pytest-review-temp/post-merge-verification/energy_probe.py`
Result: exit0; diagnostic-specific timing not isolated. Saved log energy-probe.log; reproducible script copied to docs/work/evidence/post_merge_2026_10_18_energy_probe.py. Source-extracted unchanged admission block (not production M1C execution): same 1e-7 J uniform leak rejected at 4/32/128 cells, admitted at 256/512 cells. Independent formula 64*eps*(600+120*N²) agrees. This contradicts mesh-independent admission; no numerical tolerance/floor changed. M1C realization refuses empty provided_capabilities; requires scientific identity/compatibility decision. Batch D end-to-end unavailable.

Positive subset results and every red command above are exact executed evidence only. Independent reviewers' static conclusions are not validation. Remaining cleanup gap before main runtime try/finally, unresolved OD-29 inner provenance, initial-slow identity and FAILED-vs-REFUSED are open. All named owner decisions remain open. Final fixed regression: 19 failed, 256 passed, 3 errors; complete names in evidence JSON and report. Do not infer baseline equivalence or environment-only causes without a control.

Review report: docs/work/POST_MERGE_REMEDIATION_VERIFICATION.md. Outcome: BLOCKED_BY_SCIENTIFIC_CORRECTNESS; merge/Phase3.5/recertification readiness not achieved. Genesis-lite preparation allowed; G0 and dependent scientific claims remain blocked. No active-epic/ledger change, commit/push/PR/merge, package mutation, bundle regeneration, full tier/full mutation campaign/full assurance/OD-3, reboot or unrelated-process termination.

Failed approaches to preserve: direct scientific imports remain host-WMI-blocked absent task-local fallback; original exact recipes all hit a repository cycle; the new tampered forward fixture never reaches the guard; whole M1C pack cannot collect due invalid realization; default pytest temp has WinError5; rerun with isolated temp still red. Do not repeat these without addressing causes. forge_check --changed dry-run selected full FAST; actual full FAST NOT RUN under user restriction.


Final documentation/evidence audit: use UTF-8 explicitly when reading the report; an initial closeout edit using Python's cp1252 default failed with UnicodeDecodeError before any write and was corrected. PYTEST_ADDOPTS Windows backslashes were consumed by pytest splitting, creating two task-specific temp directories at the target root. Exact original env values remain in evidence JSON. Those two generated directories were verified to resolve inside D:/forge-main-337519d1 and preserved by native PowerShell Move-Item into ignored .pytest-review-temp/post-merge-verification/archived-<original-name>. No unrelated paths were moved or deleted. Use forward slashes for future PYTEST_ADDOPTS. No scientific evidence was regenerated.

Independent final report reviewer requested correcting an overstrict certification prerequisite: Genesis governance permits isolating a proven GOVERNANCE_ONLY certificate blocker with all six circuit-breaker answers, preserving red and labelling outputs uncertified. Report corrected; current scientific/unclassified blockers do not qualify.


Final check executed: `git diff --check` -> exit 0 (only CRLF normalization notices). Evidence audit executed with stdlib Python: all 23 recorded command-log SHA-256 values and the three session source/test/probe digests match preserved files. This is file-integrity inspection, not scientific validation. HEAD and branch unchanged; eight task files remain uncommitted.


### P0 closure / baseline-regression / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\baseline-regression.json.
- Result: EXECUTED, exit 1, 13.365s; 20 failed, 255 passed, 3 errors in 12.34s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\baseline-regression.log`.
```text
FAILED tests/test_capability_completion.py::test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes[BLOCKED_WITH_EVIDENCE]
FAILED tests/test_capability_completion.py::test_the_governance_documents_name_the_ledgers_active_epic
FAILED tests/claims/test_claims_assessment.py::test_a_t3_claim_at_the_benchmark_point_is_supported_with_benchmark_validation
FAILED tests/claims/test_claims_assessment.py::test_the_value_compared_is_the_reports_never_the_callers
FAILED tests/claims/test_claims_assessment.py::test_a_violated_comparison_without_the_required_evidence_is_not_a_contradiction
FAILED tests/claims/test_claims_assessment.py::test_verification_cannot_satisfy_a_validation_requirement
FAILED tests/claims/test_quantitative_uq.py::test_an_interval_that_crosses_the_boundary_is_insufficient[tolerance_band]
FAILED tests/claims/test_quantitative_uq.py::test_an_interval_that_crosses_the_boundary_is_insufficient[threshold]
FAILED tests/claims/test_quantitative_uq.py::test_removing_uq_evidence_cannot_improve_the_verdict
FAILED tests/claims/test_quantitative_uq.py::test_numerical_uq_cannot_satisfy_model_form
FAILED tests/claims/test_quantitative_uq.py::test_parameter_uq_cannot_satisfy_a_numerical_demand
FAILED tests/claims/test_external_evidence.py::test_offered_external_evidence_never_changes_the_verdict_or_the_levels
FAILED tests/claims/test_sensitivity_robustness_challenge.py::test_a_challenge_never_changes_the_verdict
FAILED tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected[study]
FAILED tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected[value]
FAILED tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result
FAILED tests/claims/test_scientific_diagnostics.py::test_model_form_gap_becomes_a_root_cause_and_a_non_guaranteed_corrective_action
FAILED tests/claims/test_scientific_diagnostics.py::test_admissible_model_data_mismatch_is_diagnosed_without_becoming_model_form_uq
FAILED tests/claims/test_scientific_diagnostics.py::test_sensitivity_can_rank_repair_hypotheses_but_never_establish_causality
FAILED tests/claims/test_scientific_diagnostics.py::test_sealed_sensitivity_from_another_assessment_is_refused
ERROR tests/claims/test_sria_context_authority.py::test_same_qoi_same_value_wrong_charter_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_wrong_decision_id_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_changed_context_cannot_become_valid
```


### P0 closure / replay-negative-before / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_p0_replay_execution_authority.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-negative-before.json.
- Result: EXECUTED, exit 1, 4.679s; 3 failed in 3.83s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-negative-before.log`.
```text
FAILED tests/claims/test_p0_replay_execution_authority.py::test_matching_nonexecutions_cannot_receive_scientific_replay_verification[refused]
FAILED tests/claims/test_p0_replay_execution_authority.py::test_matching_nonexecutions_cannot_receive_scientific_replay_verification[missing_report]
FAILED tests/claims/test_p0_replay_execution_authority.py::test_matching_nonexecutions_cannot_receive_scientific_replay_verification[not_planned]
```


### P0 closure / identity-correction-targeted / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/claims/test_claims_assessment.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\identity-correction-targeted.json.
- Result: EXECUTED, exit 1, 116.791s; 2 failed, 68 passed in 115.99s (0:01:55). Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\identity-correction-targeted.log`.
```text
FAILED tests/test_m1c_transient_fv.py::test_exact_window_dt_basis_and_clock_identity_refuse
FAILED tests/claims/test_claims_assessment.py::test_the_mcp_tool_returns_the_same_record
```


### P0 closure / replay-negative-after / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_p0_replay_execution_authority.py tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result tests/test_m1c_transient_fv.py::test_exact_window_dt_basis_and_clock_identity_refuse`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-negative-after.json.
- Result: EXECUTED, exit 1, 6.265s; 1 failed, 4 passed in 5.50s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-negative-after.log`.
```text
FAILED tests/claims/test_p0_replay_execution_authority.py::test_matching_nonexecutions_cannot_receive_scientific_replay_verification[missing_report]
```


### P0 closure / replay-negative-after-fixture-repair / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_p0_replay_execution_authority.py tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-negative-after-fixture-repair.json.
- Result: EXECUTED, exit 1, 6.109s; 1 failed, 3 passed in 5.30s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-negative-after-fixture-repair.log`.
```text
FAILED tests/claims/test_p0_replay_execution_authority.py::test_matching_nonexecutions_cannot_receive_scientific_replay_verification[missing_report]
```


### P0 closure / replay-bound-negative-controls / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_p0_replay_execution_authority.py tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-bound-negative-controls.json.
- Result: EXECUTED, exit 0, 6.15s; 4 passed in 5.38s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\replay-bound-negative-controls.log`.
```text

```


### P0 closure / project-dependencies-probe / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -c "import sys,importlib.metadata as m,engcore,scipy,numpy,pint,mcp; print(sys.executable);print(engcore.__file__);print([(x,m.version(x)) for x in (\"numpy\",\"scipy\",\"pint\",\"pytest\",\"mcp\")]);print(scipy.__file__); print(mcp.__file__)"`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\project-dependencies-probe.json.
- Result: EXECUTED, exit 1, 0.966s; . Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\project-dependencies-probe.log`.
```text

```


### P0 closure / proper-project-venv-probe / 2026-10-18
- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -c "import sys,importlib.metadata as m,engcore,scipy,numpy,pint,mcp; print(sys.executable);print(engcore.__file__);print([(x,m.version(x)) for x in (\"numpy\",\"scipy\",\"pint\",\"pytest\",\"mcp\")]);print(scipy.__file__); print(mcp.__file__)"`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\proper-project-venv-probe.json.
- Result: EXECUTED, exit 0, 0.966s; . Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\proper-project-venv-probe.log`.
```text

```


P0 investigation milestone: baseline reproduced original19 failures/3 errors plus one new documentation-layout failure (20 failed,255 passed,3 errors). Prior verification inserted a section before the line3 active-epic pin. Moved the unchanged epic paragraph back to line3, preserving all prior section content and the same epic; no ledger or test assertion changed. Original baseline log preserved.

Owner explicitly approved existing transient capability + M1C realization0.2.0 correction, with unchanged physical model/equations/tolerances/pins/history. Independent exact-patch read-only review found precisely those3 source edits and accurate scientific meaning. Initial git apply--check/apply on CRLF proposal failed before writing; applied the exact three edits using patch tool. Snapshot .pytest-review-temp/p0-closure/m1c-identity-authorized-source.py preserves the identity-only source. Model report construction resumed. New TimePoint fixture error: integer0 rejected before intended dt mismatch; repaired to existing exact Fraction(0), no assertion changed. MCP optional environment failure in base3.14 is distinct; existing proper project venv imports all required packages without installation or environment edits. A failed mixed PYTHONPATH package-root probe lacked pywintypes because .pth initialization was absent; do not repeat that approach. Proper venv startup handles its native dependency paths, with task-local WMI workaround.

Independent replay review classified matching-refusal VERIFIED as an existing-contract bug; fixed via executed/bound/result/run-identity prerequisite without changing schemas, enums, trust bar or numeric comparison. Initial new missing-report test fixture was invalid at CapabilityRun construction; the second valid wrong-instance fixture was already rejected offline as TAMPERED. Replaced the new fixture with a genuine report under a different run id to reach the intended unbound replay boundary. These test-authoring failures are preserved in logs; no production guard was bypassed. Refusal/unplanned controls demonstrated false VERIFIED before fix; final refusal/wrong-run/unplanned plus numeric-drift controls4 passed.

Conservation exact rational global policy and separately retained local criterion have independent numerical review and an exact patch/decision document. Policy replacement remains pending explicit owner approval; M1C identity approval does not authorize it. No rtol/atol, count pin, certificate or historical bundle changed.


### P0 closure / affected-claims-suites / 2026-10-18
- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_claims_assessment.py tests/claims/test_quantitative_uq.py tests/claims/test_external_evidence.py tests/claims/test_sensitivity_robustness_challenge.py tests/claims/test_impact_replay.py tests/claims/test_scientific_diagnostics.py tests/claims/test_sria_context_authority.py tests/claims/test_p0_replay_execution_authority.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\affected-claims-suites.json.
- Result: EXECUTED, exit 0, 23.091s; 170 passed in 22.07s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\affected-claims-suites.log`.
```text

```


### P0 closure / production-leak-before-policy / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_p0_conservation_policy.py -k fixed_closed_system_leak`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\production-leak-before-policy.json.
- Result: EXECUTED, exit 2, 2.358s; 1 error in 1.64s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\production-leak-before-policy.log`.
```text
ERROR tests/test_p0_conservation_policy.py
```


### P0 closure / authority-structural-and-insufficient-controls / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_p0_replay_execution_authority.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\authority-structural-and-insufficient-controls.json.
- Result: EXECUTED, exit 0, 5.517s; 8 passed in 4.75s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\authority-structural-and-insufficient-controls.log`.
```text

```


### P0 closure / production-leak-before-policy-fixture-fixed / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_p0_conservation_policy.py -k fixed_closed_system_leak`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\production-leak-before-policy-fixture-fixed.json.
- Result: BLOCKED_TIMEOUT, exit None, 180.03s; . Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\production-leak-before-policy-fixture-fixed.log`.
```text

```


### P0 closure / discovery-after-identity / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\discovery-after-identity.json.
- Result: EXECUTED, exit 1, 6.951s; 1 failed, 2 passed, 273 deselected, 12 warnings in 5.81s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\discovery-after-identity.log`.
```text
FAILED tests/test_core_guards.py::test_the_discovery_found_exactly_the_repository
```


### P0 closure / bounded-regression-after-authority / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\bounded-regression-after-authority.json.
- Result: EXECUTED, exit 1, 15.238s; 1 failed, 277 passed in 14.21s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\bounded-regression-after-authority.log`.
```text
FAILED tests/test_capability_completion.py::test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes[BLOCKED_WITH_EVIDENCE]
```


### P0 closure / compatibility-after-authority / 2026-10-18
- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q -rs tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py tests/test_post_merge_import_smoke.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\compatibility-after-authority.json.
- Result: EXECUTED, exit 0, 34.11s; 153 passed, 1 skipped in 33.56s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\compatibility-after-authority.log`.
```text

```


### P0 closure / exact-kernel-reference-and-cost / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B D:\forge-main-337519d1\.pytest-review-temp\p0-closure\exact_kernel_analysis.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\exact-kernel-reference-and-cost.json.
- Result: EXECUTED, exit 0, 0.463s; . Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\exact-kernel-reference-and-cost.log`.
```text

```


### P0 closure / m1c-and-parent-integration-final / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\m1c-and-parent-integration-final.json.
- Result: EXECUTED, exit 1, 122.201s; 1 failed, 123 passed in 121.56s (0:02:01). Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\m1c-and-parent-integration-final.log`.
```text
FAILED tests/test_m1a_mesh_lineage.py::test_nested_record_tampering_poisoned_lineage_is_fail_closed
```


### P0 closure / affected-claims-final / 2026-10-18
- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_claims_assessment.py tests/claims/test_quantitative_uq.py tests/claims/test_external_evidence.py tests/claims/test_sensitivity_robustness_challenge.py tests/claims/test_impact_replay.py tests/claims/test_scientific_diagnostics.py tests/claims/test_sria_context_authority.py tests/claims/test_p0_replay_execution_authority.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\affected-claims-final.json.
- Result: EXECUTED, exit 0, 24.512s; 175 passed in 23.74s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\affected-claims-final.log`.
```text

```


## P0 exact-global policy milestone — 2026-10-18

Owner explicitly approved the reviewed exact-global Fraction proposal with unchanged model/rtol/atol, separately retained local allowance, explicit new policy/future receipt identity and preserved historical artifacts. Independent exact-patch reviewer found no BLOCKER/MAJOR; MINOR source-comment and display-overflow issues were fixed in proposal BEFORE approval/application. `git apply --check docs/work/proposals/P0_EXACT_GLOBAL_CONSERVATION.patch` -> exit0; `git apply docs/work/proposals/P0_EXACT_GLOBAL_CONSERVATION.patch` -> exit0. Only the approved domain-file policy patch was applied. No pin or certificate changed.

Actual-solver pre-policy28-case Cartesian leak pack exceeded180s (BLOCKED_TIMEOUT; no final counts). It emitted a failed leak rejection before timeout. Preserve log; never count the partial run PASS. Required finalized adversarial plan keeps ALL7 requested mesh sizes plus the shifted/dt counterexample, orthogonal normal-state/material/source/dt coverage and stress controls (48 cases). It removes redundant expensive Cartesian setup, not mesh sizes or scientific assertions. Existing N512 session/issuance work is slow before the policy; no performance refactor attempted.

After policy application, actual fixed-leak cases at4/16/32/64/128/256/512cells all rejected leakage; final whole-pack outcome is still pending. Exact-kernel diagnostic uses source-extracted actual rational block and independent4000-digit Decimal arithmetic for normal/subnormal/huge-finite values: all agree, exit0. Median5 samples:4entries0.0000417s;512entries0.0030858s;8192entries0.0516442s. This is arithmetic-kernel cost/agreement, NOT end-to-end solver accuracy or physical validation. Full script/log exact command recorded by run harness.

Post-authority fixed regression:277 passed,1 original contract failure; compatibility153 passed,1 explicit Windows symlink skip. Discovery20vs19 is now confirmed by import execution (not merely static count); original count pin remains unchanged. Final claims suite with structural and insufficient controls175 passed, no skips. M1C+M1B+M1A integration123 passed,1 M1A error-message mismatch (guard refuses conflicting issued mesh registry key; old regex expects tampered|unissued). No assertion/tolerance adjusted to clear it.

Positive replay compatibility control confirms completed/bound execution with UNKNOWN demanded MODEL_FORM stays insufficient even though identical replay is VERIFIED. That status verifies reproducibility of a real result, not support/validation. Narrow structural-error propagation underwent independent review and direct tests; no other ScientificCoreError classification changed.


### P0 closure / bounded-regression-final / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\bounded-regression-final.json.
- Result: EXECUTED, exit 1, 15.295s; 1 failed, 277 passed in 14.15s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\bounded-regression-final.log`.
```text
FAILED tests/test_capability_completion.py::test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes[BLOCKED_WITH_EVIDENCE]
```


### P0 closure / compatibility-final / 2026-10-18
- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q -rs tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py tests/test_post_merge_import_smoke.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\compatibility-final.json.
- Result: EXECUTED, exit 0, 34.042s; 153 passed, 1 skipped in 33.55s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\compatibility-final.log`.
```text

```


### P0 closure / exact-conservation-adversarial / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -vv --durations=12 tests/test_p0_conservation_policy.py`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\exact-conservation-adversarial.json.
- Result: EXECUTED, exit 1, 826.182s; ================== 6 failed, 42 passed in 825.51s (0:13:45) ===================. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\exact-conservation-adversarial.log`.
```text
FAILED tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[300-0.01] - assert 0.0375 == 0.0275 � 2.7e-09
FAILED tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[300-0.005] - assert 0.01875 == 0.01375 � 1.4e-09
FAILED tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[300-0.0025] - assert 0.009375 == 0.006875 � 6.9e-10
FAILED tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[3000-0.01] - assert 0.0375 == 0.0275 � 2.7e-09
FAILED tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[3000-0.005] - assert 0.01875 == 0.01375 � 1.4e-09
FAILED tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[3000-0.0025] - assert 0.009375 == 0.006875 � 6.9e-10
```


### P0 closure / datum-fixture-diagnosis / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[300-0.01]`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\datum-fixture-diagnosis.json.
- Result: EXECUTED, exit 1, 3.574s; 1 failed in 2.83s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\datum-fixture-diagnosis.log`.
```text
FAILED tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy[300-0.01]
```


### P0 closure / datum-fixture-corrected / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_p0_conservation_policy.py::test_timestep_and_datum_changes_preserve_global_policy`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\datum-fixture-corrected.json.
- Result: EXECUTED, exit 0, 8.466s; 6 passed in 7.86s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\datum-fixture-corrected.log`.
```text

```


### P0 closure / bounded-regression-post-numerical / 2026-10-18
- Command: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- Source: `93ed64b0292e9fea714ac83affb64b71488ac050` plus recorded working patch. Environment: CPython3.14.2, task-local WMI fallback and BLAS threads1; exact variables/source state in D:\forge-main-337519d1\.pytest-review-temp\p0-closure\bounded-regression-post-numerical.json.
- Result: EXECUTED, exit 1, 14.943s; 1 failed, 277 passed in 13.86s. Log: `D:\forge-main-337519d1\.pytest-review-temp\p0-closure\bounded-regression-post-numerical.log`.
```text
FAILED tests/test_capability_completion.py::test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes[BLOCKED_WITH_EVIDENCE]
```


## Final scientific integration preflight — 2026-10-18

BLOCKED_BY_OWNER at Phase0. Required FINAL_OWNER_DISPOSITIONS_2026_10_18.md absent; gate/census/M1A decisions remain explicitly open and prerequisite tests unchanged from HEAD. Existing approvals cover only M1C/conservation. Per new user restriction, all final integration tests including unified48: **NOT RUN**. Independent read-only p0_authority review confirmed prerequisite blocker; static review is not execution. Exact read-only commands/exit codes/durations/log hashes, environment metadata and source/working-file hashes: docs/work/evidence/final_scientific_integration_2026_10_18.json. Report: docs/work/FINAL_SCIENTIFIC_INTEGRATION_VERIFICATION.md. No source/tests/contracts/pins/certificates/historical logs changed, no commit/push/merge/OD-3. Earlier source hashes all match; this does not promote historical results into fresh PASS.


## Final owner-decision analysis — 2026-10-18

Created FINAL_OWNER_DISPOSITIONS_2026_10_18.md and three exact proposed patches (D1 gate diagnostic/policy alignment + explicit failed-prerequisite downstream PASS/FAIL controls; D2 census19->20 only; D3 both M1A integrity-message assertions). **PENDING OWNER APPROVAL; NOT APPLIED.** File creation does not satisfy final integration Phase0. Separate authorization also required before resuming integration.

Narrow read-only command (no pytest test functions called): `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B D:/forge-main-337519d1/.pytest-review-temp/owner-dispositions-2026-10-18/census.py`. Existing process-local platform._wmi=None fallback; BLAS threads1, PYTHONDONTWRITEBYTECODE1; target/src+root PYTHONPATH. CPython3.14.2, NumPy2.5.2, SciPy1.18.1, Pint0.25.3, pytest9.1.1, MCP2.1.1. Initial diagnostic exited1 in4.107s on full ModelRegistry roundtrip refusal for frozen linear_diffusion missing exclusions; first failure log preserved. Diagnostic revised to report each readback outcome without aborting inventory, exit0 in5.858s. This is diagnostic completion, NOT a registry-roundtrip PASS.20unique models; no import failures/optional absences; one object/serialized digest per key; historical89b9e7c3 AST19, sole added M1C physicalmodel0.1.0, none removed;16/96/63 unchanged;17realizations with nonempty capabilities and resolving model refs. ModelRegistry construction/identity lookup succeeds. Individual model readers19 succeed; frozen diffusion readback refuses, consistent with reader admission but conflicting with class/guard archive-readability documentation. Pre-existing limitation retained for separate owner review; no source/frozen-data repair.

Exact evidence, log hashes, full inventory/history, preimage hashes and independent reviewer findings: docs/work/evidence/final_owner_disposition_analysis_2026_10_18.json. Complete probe logs/script copied into evidence as new artifacts; original negative evidence untouched. All three `git apply --check <proposal>` commands executed exit0; applicability only, no patch applied. Read-only reviewers: p0_authority final D1 static PASS for proposal; closure_review D2 no blocking discrepancy with readback limitation; p0_conservation D3 no BLOCKER/MAJOR. Static review is not execution.

All proposal preimages and prior P0 source/test digests remain unchanged. Integration suites, unified48, full assurance, certification/OD-3 and mutation campaign: **NOT RUN**. No production/test/policy/pin/ledger/certificate change, commit, push, merge, PR or bundle regeneration. Stop awaiting explicit D1/D2/D3 approval and authorization before final integration resumes.


### Approved final integration / env-plain / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -c "import faulthandler; faulthandler.dump_traceback_later(5); import scipy.sparse,pint; print('scientific imports available')"`
- Result: BLOCKED_TIMEOUT, exitNone, 12.004s wall; ; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\env-plain.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / census-before / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B D:/forge-main-337519d1/.pytest-review-temp/owner-dispositions-2026-10-18/census.py`
- Result: EXECUTED, exit0, 5.048s wall; ; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\census-before.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / targeted-paths / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -p final_path_audit -vv tests/test_capability_completion.py tests/test_m1a_mesh_lineage.py::test_nested_record_tampering_poisoned_lineage_is_fail_closed`
- Result: EXECUTED, exit0, 50.035s wall; ============================= 29 passed in 49.40s =============================; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\targeted-paths.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / discovery-gates / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"`
- Result: EXECUTED, exit0, 7.47s wall; 3 passed, 273 deselected, 12 warnings in 6.39s; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\discovery-gates.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / claims-replay-final / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_claims_assessment.py tests/claims/test_quantitative_uq.py tests/claims/test_external_evidence.py tests/claims/test_sensitivity_robustness_challenge.py tests/claims/test_impact_replay.py tests/claims/test_scientific_diagnostics.py tests/claims/test_sria_context_authority.py tests/claims/test_p0_replay_execution_authority.py`
- Result: EXECUTED, exit0, 24.012s wall; 175 passed in 23.03s; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\claims-replay-final.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / m1abc-final / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- Result: EXECUTED, exit0, 123.817s wall; 124 passed in 123.16s (0:02:03); source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\m1abc-final.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / fixed-regression-final / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B tools/forge_check.py --regression`
- Result: EXECUTED, exit0, 14.31s wall; 279 passed in 13.48s; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\fixed-regression-final.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / compatibility-final / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q -rs tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py tests/test_post_merge_import_smoke.py`
- Result: EXECUTED, exit0, 35.436s wall; 153 passed, 1 skipped in 34.92s; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\compatibility-final.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / archive-readback-investigation / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B D:/forge-main-337519d1/.pytest-review-temp/final-integration-approved-2026-10-18/archive_readback_probe.py`
- Result: EXECUTED, exit0, 1.346s wall; ; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\archive-readback-investigation.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


### Approved final integration / unified-conservation-48 / 2026-10-18
- Exact command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -vv --durations=12 tests/test_p0_conservation_policy.py`
- Result: EXECUTED, exit0, 811.703s wall; ======================= 48 passed in 811.21s (0:13:31) ========================; source unchanged=True. Source HEAD 93ed64b0292e9fea714ac83affb64b71488ac050 plus working patch; before/after source indexes, environment, counts, state, log SHA256: D:\forge-main-337519d1\.pytest-review-temp\final-integration-approved-2026-10-18\unified-conservation-48.json.
- Failures/errors: none reported; non-pytest diagnostics require log interpretation.


## Final approved bounded integration closure — 2026-10-18

Owner-authorized D1/D2/D3 exact patches applied after final diff/preimage checks and fresh census. Unified48 pack **48 passed in one execution**,811.21s pytest/811.703s wall, exit0<1200s; no parameter/tolerance reduction or duplicate run. Other final outcomes:29targeted,3discovery,175claims/replay,124M1A/B/C,279fixed regression,153compatibility+1 explicit Windows symlink skip. Counts overlap and are not summed. Exact commands/env/failure/skip/source/log metadata are recorded per job and in docs/work/evidence/final_scientific_integration_approved_2026_10_18.json. All1464 indexed source/contract/certification files share canonical identity5f7c2171abca8e915bfc5102d5eb286d06d140bdfd6c6e1f0d4e99ed9547b3df across8postapply test/diagnostic jobs; before/after/current bytes match. No production source edits in this turn.

Intended paths observed: D1missingM1status3branches and failedM1→PASS/FAIL negative cases; D3transfer+coarsen both reached exact issuance-key refusal (line224 twice), restoring formerly unexecuted downstream evidence. Independent static final reviewers found no new correction/report integrity BLOCKER/MAJOR;10durable logs, sourceindexes and report hash checked. Reviewers executed no tests.

Separate FROZEN_MODEL_ARCHIVE_READBACK_INVESTIGATION_2026_10_18.md preserves current/2 DIFFUSION_MODEL readback/registry refusal and positive M1C control. Deliberate legacy/1 refusal does not satisfy current-format roundtrip contract. Compatibility FAIL_WITH_EVIDENCE; scientific impact remains UNCLASSIFIED/blocking for dependent archive/reconstruction claims. Static exact baseline/cert path tracing finds no failing decoder in inspected synthetic Genesis path, but grants no formal Step0/isolation/certification readiness. No archive behavior changed; separate owner decision required before repair.

Report: docs/work/FINAL_SCIENTIFIC_INTEGRATION_VERIFICATION.md. Prior Phase0blocked report copied unchanged into evidence/final_integration_phase0_blocked_2026_10_18.md; earlier32modified/untracked files snapshotted, prior negative reports/logs preserved. D1/D2/D3 and prior P0 source remain uncommitted/UNCERTIFIED. No certificate/ledger/activeepic/physicalmodel/threshold/historicalbundle change, commit/push/PR/merge/rebase/OD-3/full assurance/fullsuite/standalone mutation campaign. Bounded owner-review readiness PASS_WITH_EVIDENCE; OD-3/merge BLOCKED_BY_OWNER; formal GenesisStep0/Phase3.5 UNVERIFIED. Supported Linux3.11/3.12 and separately authorized final-source certification remain necessary.

## 2026-10-19 -- Deep scientific defect audit (read-only) and owner-authorized reproductions R-03..R-06

- Audited source: `D:/forge-main-337519d1`, branch `fix/p0-scientific-correctness-2026-10-18`, `abed661f` (PR #169), tree
  `7f965f0d`, tracked-file hash index `bf233a73` (5,289 files). Evidence and reports:
  `docs/work/evidence/deep_audit_2026_10_19/` (manifest `94d75936`); summary `docs/work/DEEP_SCIENTIFIC_DEFECT_AUDIT_2026_10_19.md`.
- Method: five independent read-only reviewers plus three adversarial cross-reviewers. No pytest, benchmark, mutation,
  assurance or Genesis run. Stdlib-only derivation scripts ran under `python -I -S`; these are derivations, not test evidence.
- Register: 26 findings (6 MAJOR FDA-01..06, 20 MINOR) and 8 observations; none labelled BLOCKER.
- Executed (owner-authorized, once each, sequentially; real FORGE functions at `abed661f`):
  - Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="<scratch>/repro/bootstrap;D:/forge-main-337519d1/src;D:/forge-main-337519d1" OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 600 C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B <script>`, cwd = scratch. Interpreter: CPython 3.14.2, NumPy 2.5.2, SciPy 1.18.1, Pint 0.25.3. Bootstrap `sitecustomize.py`: `platform._wmi = None` only.
  - R-04 `r04_mcp_uq.py`: exit 0, 2.118 s. FDA-04 REPRODUCED (n=4/k=3 and n=32/k=17 gave a zero-width `completed` interval); FDA-14 REPRODUCED (realised mass 0.7125 / 0.9203 against a stated 0.95). Control OK.
  - R-05 `r05_vacuous_pair.py`: exit 0, 0.187 s. FDA-05 REPRODUCED: one vacuous pair scored `indistinguishable_hit` +1.0 in both the evaluator and the escrow, for two mutually exclusive truths. Four controls OK.
  - R-06 `r06_spurious_cap.py`: exit 0, 0.165 s. FDA-06 REPRODUCED for the capping function (spurious credit 1.0 uncapped; discoverable capped). The full `lift_decision` was not run. Control OK.
  - R-03 `r03_material_arbitration.py`: exit 0, 0.796 s. FDA-03 REPRODUCED (conflicting 300 K sources gave interpolated 25.0 or 20.0 by claim-id order; coverage `conflicted=False`). Control OK.
  - Failures: none. The source hash index was identical before and after every run, and no `.pyc` was written in the repository.
- NOT RUN: R-01 (FDA-01 replay UQ), R-02 (FDA-02 state clock) and R-07..R-26, by owner stop. FDA-01 and FDA-02 remain SOURCE_PROVEN only.
- Windows 3.14 is not the certification platform; nothing here is certified. No source, test, contract, certificate or benchmark identity changed.
- Owner decisions open: ODC-* in `evidence/deep_audit_2026_10_19/closure/SCIENTIFIC_FINDINGS_OWNER_DECISIONS.md`. FDA-05 and FDA-06 must be closed before any Genesis-lite scoring freeze; B-LEAK remains a formal-measurement blocker.


## 2026-10-19 — BUY-01: FDA-04 / FDA-14 / B26 repair of the MCP probabilistic UQ tool (local, uncommitted)

Worktree `D:/forge-buy01`, branch `fix/buy01-fda04-fda14-qmc` from `origin/main` `d3c9cd45`. No commit, push, PR,
merge, dependency install, recertification or epic change. The candidate patch in the 2026-10-19 handoff was read
as reference and NOT applied: it used scrambled LHS (points no longer on midpoints, so its FDA-14 test fed midpoints
by hand instead of the sampler), kept the absolute sigma conversion, and wrote no spread unit for offset-scale outputs.

Change (`src/engcore/mcp/probabilistic_uq.py`, `src/engcore/mcp/server.py`):
- Design: `scipy.stats.qmc.LatinHypercube(scramble=False)` from `np.random.default_rng(20261019)`; each column an
  independent seeded permutation of stratum midpoints. A design with a rank-identical or rank-reversed column pair is
  refused (`cannot represent independence`). `sample_design()` records sampler identity (algorithm, seed, SciPy and
  NumPy versions) and the realised max |pairwise rank correlation|; the server returns it as `sample_design`.
- Quantiles: `np.quantile(..., method="hazen")`; a tail below 0.5/n returns `sample_resolution_insufficient`.
  Intervals carry `mass_semantics: nominal_empirical_quantile_mass_not_coverage`; `does_not_include` adds calibrated
  coverage and the quantile estimate's sampling error.
- Units: a normal sigma must be a spread unit (`require_spread_unit`) and is converted with
  `magnitude_as_spread_in`; the output standard uncertainty on an offset scale is written in the base unit.
- Schemas: `engineering_probabilistic_uq/2`, `engineering_uncertainty_answer/2`; the server's incomplete branch no
  longer hard-codes `/1`. Nothing in the tree reads `/1` back.

Failing-first: 11 new tests in `tests/mcp/test_probabilistic_uq.py` failed on unmodified source for the intended
reasons (R-04 zero width; constant pair sums at n=4 for k=3/5/17; no sampler record; 0.920 mass; n=4 not refused;
schema /1; `2 degC` sigma accepted; `2 delta_degC` sigma refused by the old absolute conversion; spread written as
degF). One existing assertion moved from type-7 (301.5/304.5) to Hazen (301/305). `tests/mcp/test_server.py`
gained schema and sampler assertions.

Executed (Windows, `phyx/.venv` Python 3.14.2, SciPy 1.18.1, NumPy 2.5.2, pint 0.25.3 -- NOT the supported 3.11/3.12):
- R-04 original script on unmodified worktree: REPRODUCED (identical to the audit's R-04.out).
- `python -m pytest tests/mcp/test_probabilistic_uq.py -q` before repair: 11 failed, 6 passed; after: 17 passed.
- `python -m pytest tests/mcp/test_server.py tests/mcp/test_probabilistic_uq.py tests/mcp/test_scenario_uq.py -q -n 4`: 60 passed.
- R-04 cases after repair (`r04_after.py`, scratch): n=32 k=17 x15+x16 completed, sd 0.414; n=4 0.95 refused for
  resolution; n=20/32/40 realise 0.95 exactly for Y=X0.
- Census (fixed seed, n=4..256): design refusals only at k=5 n=4; k=10 n=4,6; k=17 n=4,5,6. Realised max |rho| for
  admitted designs with n>=32 reaches 0.45 (k=2) and 0.53 (k=17). A fixed seed is not independence; the bound is ODC-04a.
- `python tools/forge_check.py --changed --base origin/main --workers 4` (195 affected modules; expensive tests
  listed, not run): 50 failed, 4536 passed, 84 skipped, 2 errors, exit 1. The identical pytest argument list on a
  pristine `origin/main` worktree (`D:/forge-buy01-base`): 50 failed, 4523 passed, 84 skipped, 2 errors. Failure and
  error node sets are identical (`comm` empty both ways); the +13 passes are the new tests. The shared failures
  (durable campaign, phase2 coupling, phase3.5 WS2 migration, core certificate/guards, mutation startup, symlink,
  offline revalidation, battery blind-readiness errors) are pre-existing on this Windows/3.14 host, not caused here.

Not done / owner decisions: ODC-04a refusal bound on realised |rho| (currently only |rho|=1 refused); ODC-04b
relocation of the computation from `engcore.mcp` to `engcore.uq` (O-4); ODC-14a minimum-n rule (implemented 0.5/n,
the clip boundary; the audit's example 1/n would refuse the default 32 x 0.95 call); ODC-14b label wording; schema
bump approval; OD-3 hardened recertification (forge_check classifies server.py and both test files
certification_pinned). Supported-Python run NOT RUN. Scientific coverage calibration NOT RUN.

Owner decision 2026-10-19: **ODC-14a approved as implemented** — refuse a central mass whose tail lies below 0.5/n
(`sample_resolution_insufficient`). No code change was needed. ODC-04a, ODC-04b, ODC-14b and OD-3 remain open.

ODC-04a evidence and proposal (no code change): `docs/work/proposals/ODC_04A_DESIGN_CORRELATION_BOUND.md`.
Executed scratch scripts `odc04a_census.py`, `odc04a_checks.py` and `odc04a_nonlinear.py` against the worktree
design generator (Python 3.14.2, SciPy 1.18.1, NumPy 2.5.2; exit 0 each). Findings:
- The shipped design's realised rank correlation behaves like random permutations. At k=17, n=32: max |rho| 0.47,
  lambda_min 0.15, worst linear-output sd ratio 0.39.
- Under any fixed bound, admission is non-monotone in n.
- One Iman–Conover pass (identity target) keeps the midpoint LHS marginals and costs ~1 ms at n=256. With
  lambda_min >= 0.64 it admits every n >= 7/10/24/45/52 for k = 2/5/10/17/25.
- SciPy random-cd achieves the same at 0.2–1.4 s per design, and needs n >= 49/104 for k = 17/25.
- Decorrelation cuts the worst additive-output sd error from 0.24 to 0.05 (IC) or 0.02 (CD). It does not reduce the
  Ishigami (nonlinear) error, which stays at ~0.17–0.18. The bound therefore guards linear outputs only.
- Recommended: Option D (IC re-pairing + refuse n <= k or lambda_min < 0.64, and report the lambda band). This is a
  risk-policy choice for the owner and is not implemented.

Owner decision 2026-10-19: **ODC-04a approved, Option D**. Iman–Conover re-pairing; refuse n <= k or
lambda_min < 0.64; report the lambda band. Implemented failing-first in `D:/forge-buy01`, uncommitted.

- `probabilistic_uq.py`:
  - `_pair_for_independence`: one Iman–Conover pass to the identity target. It keeps every column's values; a design
    whose score correlation is not positive definite is returned unchanged, so the bound still refuses it.
  - `_rank_eigenvalues` and `_assessed_design` feed both `sample_design` and `build_deterministic_samples`.
  - `MINIMUM_DESIGN_LAMBDA = 0.64` and `PAIRING = "iman_conover_identity_vdw/1"`, recorded in the sampler identity.
  - `sample_design` now carries `lambda_min`, `lambda_max`, `linear_output_sd_ratio_band`, `minimum_lambda`,
    `bound_scope: design_dependence_bound_linear_outputs_only` and `admitted`.
  - The exact |rho| = 1 pair check is removed; the bound subsumes it.
  - Schema stays `/2`, which is unreleased. The `server.py` tool description is updated.
- Tests (`tests/mcp/test_probabilistic_uq.py`):
  - The R-04 trigger (n=32, k=17) is now refused; the same pair completes at n=64 with sd > 0.1.
  - Property test over n in 4..256 for k in {2, 3, 5, 10, 17}: every admitted design has lambda_min >= 0.64,
    computed from the sample values independently of the module, and has no cancelling pair.
  - Added: n <= k refused; midpoint strata kept at (32, 5), (64, 10) and (128, 17); band reported and matching the
    samples; a reversed pair fails closed.
- Failing-first: `python -m pytest tests/mcp/test_probabilistic_uq.py -q` on the pre-Option-D code gave 9 failed, 14
  passed, each for the intended reason. After the change: 23 passed.
- `python -m pytest tests/mcp/test_server.py tests/mcp/test_probabilistic_uq.py tests/mcp/test_scenario_uq.py -q -n 4`:
  66 passed.
- Production admission (`sample_design`, n in 4..256), each k given as admitted/total, then the smallest N with every
  n >= N admitted, then whether n=32 is admitted:
  - k=2: 252/253, 7, yes
  - k=3: 250/253, 7, yes
  - k=5: 247/253, 10, yes
  - k=10: 235/253, 24, yes
  - k=17: 225/253, 45, no
  - k=25: 209/253, 52, no

  These are identical to the proposal's IC census.
- `python tools/forge_check.py --changed --base origin/main --workers 4`: 52 failed, 4665 passed, 84 skipped,
  2 errors, exit 1. The selection grew because the new docs pulled in more modules: `test_v2_blindfold.py`,
  `test_multiphysics_window_control.py` and the battery_1rc benchmark tests.
  - 50 failures and 2 errors are identical to the earlier pristine-`origin/main` (`d3c9cd45`) baseline.
  - The other 2 (`test_v2_blindfold.py::test_the_subprocess_escrow_keeps_its_secrets_in_the_child`,
    `test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable`)
    fail identically on a fresh pristine `origin/main` worktree, run serially: 2 failed, 50 passed in both trees.
  - Neither file references `engcore.mcp`. No failure is attributable to this change.
- Still open: ODC-04b (move the computation to `engcore.uq`), ODC-14b (label wording), OD-3 recertification
  (certification-pinned files), a supported-Python 3.11/3.12 run, and owner approval to commit.

### 2026-10-19 — BUY-01 pre-PR scientific closure (local, not pushed)

Branch `fix/buy01-fda04-fda14-qmc`: `17e2edd5` (BUY-01 + ODC-04a/14a), then `428993b1` (ODC-14b + ODC-04a wording),
on base `origin/main` `d3c9cd45`.

**ODC-14b (interval semantics), decided and implemented.** What the code computes, per output quantity: the Hazen
central quantile range of n equal-weight model outputs over the sample design drawn from the declared inputs, at
the requested mass. It is not a Bayesian credible interval (there is no posterior), not a confidence interval (no
repeated-sampling statement) and not a prediction interval (no observation noise).

Each interval record now carries:
- `requested_central_mass`;
- `credible_mass`, kept as the /1 field and input-parameter name, an alias in /2;
- `interpretation`: kind `empirical_central_quantile_interval`, quantile rule `hazen`,
  `coverage_guaranteed: false` and `coverage_calibrated: false`.

`conditional_on` names the realised finite design, and `does_not_include` says "calibrated coverage of any interval".
Refusal reasons, the tool description, README.md and docs/mcp/README.md no longer say "predictive interval" or
"nominal coverage". The public names `credible_mass`, `predictive_intervals` and `predictive_support_not_admitted`
are kept for compatibility, and their meaning is stated in `interpretation`.

**ODC-04a semantics.** `sample_design` is labelled `role: sampling_design_dependence_diagnostic`,
`bound_scope: linear_outputs_only`. Its `does_not_establish` lists output accuracy (including for nonlinear outputs),
calibrated coverage, model validity, and uncertainty beyond the declared inputs. The tool description says the
diagnostic is not evidence of accuracy, calibrated uncertainty or model validity. The threshold (0.64) and the
refusal behaviour are unchanged; nothing was retuned. Added `design_sha256` (the exact unit-design bytes) for replay
identity.

**ODC-04b (move the computation to a UQ-owned module), DEFERRED to its own bounded PR.** Measured:
`tools.test_impact.classify` gives any new file under `src/engcore/uq/` the class CERTIFICATION_PINNED
(`certified:predictive_representation`), while `src/engcore/mcp/probabilistic_uq.py` has no recertification reason.
Moving the code would bring uncertified code into certified scope and add certified-import edges. That is an
architecture and certification change, separable from the FDA-04/14 numerical claim, and it does not change the
semantics. Not part of BUY-01.

**Tests.**
- Failing-first: with the new test file in a temporary worktree at `17e2edd5`, 6 failed and 20 passed. The wording
  scanner caught "not calibrated coverage" in the old description and "predictive interval" in the old refusal reason.
- At `428993b1`, `tests/mcp/test_probabilistic_uq.py`: 26 passed.
- Windows `.venv` Python 3.14.2 (NumPy 2.5.2, SciPy 1.18.1, pint 0.25.3):
  `python -m pytest tests/mcp/test_server.py tests/mcp/test_probabilistic_uq.py tests/mcp/test_scenario_uq.py -q -n 4`
  gave 69 passed.

**Supported Python at `428993b1`**, from WSL clean tree `/mnt/d/forge-buy01` (engcore imported from
`/mnt/d/forge-buy01/src`), using the read-only venvs of `~/forge-hostile-remediation/.forge/venvs`:
`PYTHONPATH=$WT/src:$WT python -m pytest tests/mcp/test_probabilistic_uq.py tests/mcp/test_server.py tests/mcp/test_scenario_uq.py -q -rfEs -p no:cacheprovider`
(script `D:/ftmp-buy01/wsl_supported.sh`, logs `D:/ftmp-buy01/supported/`).

| Python | NumPy | SciPy | Pint | pytest | Result |
|---|---|---|---|---|---|
| 3.11.17 | 2.4.6 | 1.17.1 | 0.25.3 | 9.1.1 | 69 passed, 0 failed, 0 skipped, exit 0 |
| 3.12.3 | 2.5.4 | 1.18.1 | 0.26.1 | 9.1.1 | 69 passed, 0 failed, 0 skipped, exit 0 |

The design digests for (n, k) = (32, 10), (32, 17), (64, 17) and (256, 25) are identical on 3.11, 3.12 and Windows
3.14 (`8c086da7…`, `2155c284…`, `eae91243…`, `9375f59e…`). `lambda_min` differs only in the last place (eigensolver
rounding), and no admission changed.

R-04 cases (`r04_after.py`) on 3.11 and 3.12:
- n=4 k=3 and n=32 k=17 are refused by the design guard; the zero-width completed interval no longer occurs.
- The n=32 k=2 control completes with sd 0.401.
- Y=X0 realises 0.95 at n=20, 32 and 40, and n=4 at 0.95 is refused for resolution.

**Changed-file gate at `428993b1`** (Windows 3.14.2):
`python tools/forge_check.py --changed --base origin/main --workers 4` gave 52 failed, 4705 passed, 84 skipped and
2 errors (exit 1). The identical pytest argument list on a pristine `origin/main` worktree gave 52 failed, 4683
passed, 84 skipped and 2 errors.
- The failure and error node sets are identical (54 = 54; `comm` empty in both directions).
- The +22 passes are the added items: the two changed test files collect 66 items here and 44 on main.
- The gate's classes: README files doc_only, `probabilistic_uq.py` scientific_shared, `server.py` and both test files
  certification_pinned. Merge therefore requires OD-3.

**Not done:** OD-3 hardened recertification, the full FAST/SCIENTIFIC tiers on Linux, a push, a PR and a merge.
Coverage calibration and scientific validation were not run; the guard and intervals are not claimed to give either.

## 2026-10-20 — FAST runtime profiling (owner-authorized, in progress)

Base: remote main `8ec97064c35144405e3eba53a4282e90f8593b1c` (checked with
`git ls-remote origin refs/heads/main`). Managed branch `codex/fast-runtime-profile`.
Measurements use an independent, self-contained Linux clone at
`/home/dev_kaeem/forge-fast-runtime-20261020`, initialized from an existing local
clone plus a local Git bundle; no remote writes or dependency installs.
Interpreter: `/home/dev_kaeem/forge-hostile-remediation/.forge/venvs/3.12/bin/python`
(Python 3.12.3, pytest 9.1.1, NumPy 2.5.4, SciPy 1.18.1). Common environment:
`PYTHONPATH=/home/dev_kaeem/forge-fast-runtime-20261020/src:/home/dev_kaeem/forge-fast-runtime-20261020`,
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`; bytecode caching enabled.
Evidence prefix E = `/home/dev_kaeem/forge-fast-runtime-evidence-20261020`.
These are developer performance diagnostics, not certification or physical validation.

- Command: `python tools/forge_check.py --changed --base HEAD --workers 4`
  Result: PASS, 94 passed in 3.03s; exit 0. Log: E/initial-changed.log.
- Command: `python -m pytest -m 'not expensive' -q -n 4 --dist loadfile -p no:cacheprovider -p tools.test_timing --timing-report=E/baseline-n4.json --junitxml=E/baseline-n4.xml --basetemp=E/tmp-baseline-n4 --durations=25`
  Result: FAIL, 64 failed, 11873 passed, 176 skipped, 2 warnings in 794.91s;
  exit 1. Checkout stayed clean. The complete failure names are in E/baseline-n4.log
  and XML. Relevant existing failures include test_core_certificate::test_the_certificate_describes_this_tree,
  test_phase2_field_transfer, test_phase2_external_coupling, test_phase2_review_regressions,
  test_phase35_ws2_electrothermal_migration, test_phase35_ws3_conjugate_interface,
  test_mutation_population_v4::test_every_folded_mutation_still_matches_the_source_it_names
  and core-freeze v3/v4 tests. No acceptance or new-regression conclusion yet.
- Measured bottleneck: tests/test_p0_conservation_policy.py consumed 746.875s
  of test-phase time, dominated by 512-cell cases (85.7–95.1s each).
- Command: `python -m cProfile -o E/conservation128.prof -m pytest 'tests/test_p0_conservation_policy.py::test_independent_energy_accounting_on_each_mesh[equilibrium-128]' -q -p no:cacheprovider --basetemp=E/tmp-profile128`
  Result: PASS, 1 passed in 13.47s; exit 0. Profiling adds overhead, so this
  duration is not compared directly with unprofiled timings. Profile: 136 mesh
  accessor calls, 7611 version_id calls, 1155584 LineageCell1D.to_dict calls;
  the sparse provider _execute took about 0.004s cumulative.
- Added bounded-access regression before implementation change.
  Command: `python -m pytest tests/test_m1c_transient_fv.py::test_coordinate_conversion_does_not_revalidate_the_whole_mesh_per_vertex -q -p no:cacheprovider --basetemp=E/tmp-failing-first`
  Result: EXPECTED FAIL, 1 failed in 1.36s, exit 1. Checked mesh accesses grew
  from 10 (4 cells) to 22 (16 cells). This is a performance regression proof,
  not a scientific correctness failure.
- Candidate: obtain the checked adapter.mesh.grid once during coordinate
  conversion, outside the per-node comprehension. No persistent cache, tolerance,
  numerical method, mesh size, test tier or assertion removed. Later live guards
  remain intact. Provider backend implementation digest changes with source bytes
  by existing design; serialization schemas are unchanged.

Setup failure: a PowerShell here-string piped directly into bash preserved CR in
one scratch directory name. Renamed that exact task directory, then stripped CR
at the shell input boundary for subsequent scripts. No scientific run used the
misnamed directory. A first ACTIVE_PLAN patch failed exact-context matching and
wrote nothing; retried using the header-only context.

### Candidate verification milestone

- Command: `python tools/forge_check.py --changed --base HEAD --workers 4`
  Result: FAIL, 11 failed, 2345 passed, 2 skipped in 136.46s; exit 1.
  The exact 11 FAILED node IDs are a subset of the unchanged FAST baseline's
  64 failures (set subtraction empty), saved in E/changed-failure-comparison.json.
  Relevant names: test_core_semantic_invariants::test_every_reader_that_writes_a_schema_also_checks_one;
  test_electrothermal_vertical::test_l3_no_relaxation_appears_anywhere_in_the_module;
  test_core_guards::test_no_gate_lets_its_caller_set_the_threshold_it_awards_a_level_against;
  six tests in test_phase2_coupling_authority; and both certificate tests
  test_the_certificate_describes_this_tree / test_the_certificate_records_the_v1_relationship_truthfully.
  No new FAILED node ID in this affected selection. Full log: E/changed-after.log.
- Command: `python -m pytest tests/test_m1c_transient_fv.py tests/test_p0_conservation_policy.py -q -n 4 --dist loadfile -p no:cacheprovider --basetemp=E/tmp-targeted-after --durations=10`
  Result: PASS, 91 passed in 106.97s, exit 0. Includes the new bounded-access
  regression, all unchanged 48 global conservation cases and existing stale-state,
  provider mutation, residual and manufactured-solution checks. No tests removed
  or moved between tiers. Representative 512-cell energy checks now take about
  9.9–10.5s (baseline full-run examples 86–95s); these isolated test durations are
  diagnostic, not a substitute for the full before/after wall-time comparison.
- Independent read-only scientific review using `.claude/skills/forge-scientific-review/SKILL.md`:
  PASS (static review only; reviewer ran no tests). No authority weakening found:
  access stays through the checked public boundary, the local reference is used
  only during serial conversion, and later storage/lineage/configuration checks
  remain live. No uncertainty or scientific validation promotion.
- For a clean-tree full comparison, the TWO candidate code/test files were
  committed only inside the disposable Linux measurement clone. The managed
  review worktree remains uncommitted. No remote publication. Exact scratch SHA
  is in E/candidate-commit.txt; original baseline SHA remains 8ec97064.
- Full candidate FAST, same n=4 and flags as baseline: IN PROGRESS at this entry.
  SCIENTIFIC, FULL, mutations and hardened recertification: NOT RUN. The new test
  is certification_pinned (assurance_suites); integration still needs the normal
  gates and owner-run recertification. No certificate or frozen artifact changed.

### Completed FAST before/after comparison

- Candidate measurement-clone commit: `cc5b7c6ebccdc255f1e17d5f9a3ef14f2f0e3671`.
  Managed branch remains `codex/fast-runtime-profile`, uncommitted and unpublished.
- Command: `python -m pytest -m 'not expensive' -q -n 4 --dist loadfile -p no:cacheprovider -p tools.test_timing --timing-report=E/after-n4.json --junitxml=E/after-n4.xml --basetemp=E/tmp-after-n4 --durations=25`
  Result: FAIL, 64 failed, 11874 passed, 176 skipped, 2 warnings in 295.49s;
  exit 1. Candidate measurement checkout stayed clean. Relevant failures are
  EXACTLY the baseline 64, including the previously named certificate, phase2,
  phase3.5 and core-freeze failures; no failure repaired or hidden by this task.
- Automated JUnit multiset comparison: all 12,113 original test cases retain
  exactly their outcomes, zero removed cases, zero changed common outcomes.
  Sole addition: test_coordinate_conversion_does_not_revalidate_the_whole_mesh_per_vertex,
  PASSED. Detailed comparison and file SHA-256 values: E/result.json.
- Existing timing plugin wall: 794.495s -> 295.006s, a 62.87% reduction / 2.69x
  speedup in this measured pair, both n=4, loadfile, BLAS threads1. The conservation
  module's summed phases: 746.875s -> 108.176s. Sparse solve and all original
  assertions, meshes, tolerances, unknown uncertainty and scientific policies unchanged.
- Limitation: one sequential before/after pair, not a universal performance guarantee.
  Initial startup was colder (18.045s vs6.925s), accounting for about11s of the
  roughly499s wall reduction; most savings are in eliminated per-vertex whole-mesh
  verification. No n=8 trial was needed after the measured source bottleneck was found.
- Evidence mirrored to `D:/forge-fast-runtime-evidence-20261020/`: baseline-n4 and
  after-n4 logs/JSON/JUnit, failing-first, profile, changed gate, targeted log,
  changed-failure-comparison.json, comparison.txt and result.json. Summarizer is
  outside the repository. These artifacts are performance diagnostics only.
- `git diff --check`: PASS (exit0; only CRLF-normalization warning for appended
  PROGRESS text). SCIENTIFIC / FULL / mutation populations / recertification: NOT RUN.
  This task is complete as a bounded performance improvement, NOT merge-ready
  assurance. No frozen artifact, certificate, capability maturity or CI policy edited.

### Branch publication authorized (2026-10-20)

Owner explicitly requested publishing the measured FAST improvement to a branch
before inspecting further performance opportunities. No additional test run is
needed for publication: source/test bytes still match the executed candidate
SHA-256 values in `docs/work/evidence/fast_runtime_2026_10_20.json`. That compact
summary is now tracked so the measurement survives loss of scratch directories.
Full logs remain at the recorded external evidence paths. Publication does not
assert merge readiness, successful FAST, certification or scientific validation.
The 64 baseline failures and remaining integration gates are unchanged.

### Publication confirmed; next quick opportunities inspected

- `git push --set-upstream origin codex/fast-runtime-profile`: SUCCESS; remote
  `refs/heads/codex/fast-runtime-profile` independently read back with
  `git ls-remote` at `57651035372acb39d4b95d1135b563cca9a24350`.
  No PR or merge. Measured source/test bytes are unchanged.
- Read-only follow-up inspection (NOT IMPLEMENTED / NOT BENCHMARKED):
  1. MeshVersion1D.to_dict constructs _material and then version_id constructs
     it again. Candidate: eliminate duplicate serialization within ONE operation,
     preserving schema, exact canonical bytes, subclass behavior and live tamper
     detection; do not add a persistent trusted-record cache.
  2. Current FAST still spends about103s in each of test_m1c_transient_fv and
     test_core_freeze_v4_manifest. A single manufactured refinement test consumes
     about70s. Preserve its steps, meshes and assertions; investigate repeated
     lineage/snapshot work rather than weakening the test or the certificate.
  3. Existing bounded developer worker selection (6/8) is a configuration trial,
     not a new implementation. Historical scaling evidence exists, but current
     n=4 -> n=8 performance and complete outcome equivalence remain NOT RUN.
- No additional performance claim follows from this static inspection. The only
  new measured improvement remains the previous n=4 before/after result.
  No additional tests run for this documentation-only publication record.

## 2026-10-20 — Restore ACTIVE_PLAN's Active-epic line (main eb113ab7 regression)

Branch `fix/active-plan-epic-line` from `origin/main` `eb113ab7`. PR #173 inserted its "Current bounded task — FAST
runtime profiling" section above the "Active epic: ..." paragraph, so
`tests/test_capability_completion.py::test_the_governance_documents_name_the_ledgers_active_epic` (reads line 3) failed
on main. The paragraph is moved back directly under `# Active Plan`; the FAST section follows it unchanged. One-file,
byte-for-byte move (LF only); no other text changed. The same fix exists on the local Genesis-lite branch
`feat/genesis-lite-v03-amendment-draft` (`3bab1715`); this branch carries it for main alone.

- `PYTHONPATH=<worktree>/src;<worktree> TMPDIR=D:/tmp/aplan-fix .venv/Scripts/python.exe -m pytest
  tests/test_capability_completion.py -q -p no:cacheprovider --basetemp=D:/tmp/aplan-fix/bt`: 28 passed (Windows,
  repo venv).
- Same environment, `.venv/Scripts/python.exe tools/forge_check.py --regression --workers 4`: 279 passed, exit 0.
- FAST / SCIENTIFIC / FULL tiers and recertification: NOT RUN (documentation-only change). Not pushed; no PR.

## 2026-10-20 — Reviewed branch publication and active-epic repair

Owner requested publishing all work and merging reviewed unmerged branches, explicitly excluding preserve/* and wip/*. This supersedes older no-push/no-merge instructions for this publication task only; it does not authorize formal measurement, freeze or waive scientific/certification gates. Origin main was eb113ab7e74580d47e6aa1210d02e45a49124724. Isolated integration worktree; shared checkouts untouched.

Merged fix/active-plan-epic-line locally: exact paragraph move to restore the ledger epic to line3. No production/test/certification bytes changed. Runtime for checks: repository Windows venv, Python 3.14.2. These local results do not substitute for 3.11/3.12 scientific assurance.

Cwd: `C:\Users\dev_kaeem\.codex\worktrees\review-unmerged-work\wonderful-gould-1c576f`. Environment: `{"PYTEST_ADDOPTS": "--basetemp=D:/tmp/merge-review-docs/bt", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\src;C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f", "TMPDIR": "D:/tmp/merge-review-docs"}`.

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest tests/test_capability_completion.py -q -p no:cacheprovider`

Exit 0; elapsed 0.663630299968645 seconds.

Cwd: `C:\Users\dev_kaeem\.codex\worktrees\review-unmerged-work\wonderful-gould-1c576f`. Environment: `{"PYTEST_ADDOPTS": "--basetemp=D:/tmp/merge-review-docs/bt", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\src;C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f", "TMPDIR": "D:/tmp/merge-review-docs"}`.

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main`

Exit 1; elapsed 21.811875500017777 seconds.

Cwd: `C:\Users\dev_kaeem\.codex\worktrees\merge-main-control\wonderful-gould-1c576f`. Environment: `{"PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f", "TMPDIR": "D:/tmp/merge-main-control"}`.

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest -q tests/test_repository_architecture.py tests/test_core_api_layering.py tests/test_scientific_regression_manifest.py tests/test_forge_check.py tests/test_agent_workflow_contract.py tests/test_capability_completion.py benchmarks/battery_1rc_closure/tests/test_battery_1rc_closure.py benchmarks/battery_1rc_crosscell/tests/test_battery_1rc_crosscell.py benchmarks/battery_1rc_identifiability/tests/test_battery_1rc_identifiability.py tests/foundations/test_v2_blindfold.py tests/test_multiphysics_window_control.py --basetemp=D:/tmp/merge-main-control/bt`

Exit 1; elapsed 13.028979999944568 seconds.

Targeted:28 passed. Changed-file gate:2 failed,217 passed. Exact same selected node set against pristine eb113ab7:3 failed,216 passed. New failing nodes: NONE. Removed failing node: tests/test_capability_completion.py::test_the_governance_documents_name_the_ledgers_active_epic. Common failing nodes:

- tests/foundations/test_v2_blindfold.py::test_the_subprocess_escrow_keeps_its_secrets_in_the_child (child interpreter cannot import engcore.blindfold in this Windows environment).
- tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable (7 subdivisions vs expected8).

The whole gate is NOT green; no baseline failure was suppressed. Full tiers and recertification NOT RUN for this documentation-only repair.

Publication: complete current Mind/demo/diagnostic/CP2 work preserved byte-identically (251 files) in 1b90f94c on codex/mind-development-evidence-2026-10-20, draft PR175 stacked on PR174. CP2 remains94failed/28passed, no merge-readiness claim. Original pinned logs/patch evidence contain whitespace; authored-source diff check passes, historical bytes were not rewritten. Published local-only Mind, M1D, OD-CAP-0 and active-plan-fix branch tips without force-push.

Branch review: legacy Genesis/planning documents must not replace strengthened contracts; M1D needs a port preserving current conservation semantics; OD-CAP-0 test edits require current applicable gates; Genesis isolation and OD3 remain blockers. Old certificate-only tips must not replace the current certificate. Main-equivalent patches and nested branch histories were identified separately. Existing unrelated dirty worktrees were inventoried and left untouched.

Trial merge of claude/domain-real-data was aborted after its tests:1failed/12passed; failing node benchmarks/domain_real_data/tests/test_domain_real_data.py::test_repository_scan_is_current. Its historical scan differs from current tree; no historical evidence was regenerated to silence it. Exact command:

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest benchmarks/domain_real_data/tests/test_domain_real_data.py -q -p no:cacheprovider --basetemp=D:/tmp/merge-review-domain/bt`

Cwd `C:\Users\dev_kaeem\.codex\worktrees\review-unmerged-work\wonderful-gould-1c576f`; environment `{"PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\src;C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f", "TMPDIR": "D:/tmp/merge-review-domain"}`; exit1. Read-only independent scientific review returned CHANGES REQUIRED for the combined scientific branches; no unreviewed wholesale merge. Branch inventory, exact receipts and conflict previews are retained in the publication audit package.

Follow-up verification on documentation head d293fa2e: an intended selection listing used `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main --list`. This flag still executes pytest; TMPDIR/basetemp were not set in that invocation. Exit1:2failed,199passed,18setup PermissionErrors in12.93s. This was an invocation error, not discarded evidence. Exact failing/error node names are preserved in the publication audit list-run-lastfailed.json; no environment permissions were changed.

Corrected repeat: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main`, environment `{"PYTEST_ADDOPTS": "--basetemp=D:/tmp/merge-review-final/bt", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\src;C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f", "TMPDIR": "D:/tmp/merge-review-final"}`, same cwd as above. Exit1:2failed/217passed/0errors in10.42s. Exactly the two baseline failing nodes listed above; no new failures. Authored documentation diff check passed. This final addition records that execution only; no code/tests changed.


## 2026-10-20 - PR176 merged; reconcile already-integrated branch histories

Owner explicitly approved PR176 in chat; merged via GitHub merge-commit API with expected head1e109c667018be219f6da1df8bc7049caa11ebb9. Returned merge SHA3213bb35b2e222c5eddd86012aa8e179cee6c4a6; fetched origin/main matches. No test or OD3 waiver.

The complete27-line historical section added by docs/main-check-2026-10-13 is byte-present in main PROGRESS (Python substring assertion executed). git cherry origin/main origin/codex/critical-production-closure reports four equivalent commits and no unique commit; origin/feat/multiphysics-lifecycle-foundation reports one equivalent/no unique. Merged these three histories individually. Conflicting historical PROGRESS/MCP files were retained at current-main bytes only after those equivalence checks. git diff --cached --exit-code executed after each resolution (exit0); the final tree at93c6f21 equals3213bb35's tree exactly. No source, certificate, workflow or old evidence changed. These are ancestry reconciliations, not newly implemented capabilities.

Domain-data trial at3213bb35+a80b4df5: exact command C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest benchmarks/domain_real_data/tests/test_domain_real_data.py -q -p no:cacheprovider --basetemp=D:/tmp/domain-reconcile-red; PYTHONPATH=checkout/src;checkout, TMPDIR=D:/tmp. Result1failed12passed0.45s, exit1, test_repository_scan_is_current. Historical tree replay of a80b4df5 reconstructs the old scan exactly; its SHA256 remains a26fe3c3b9fd7bc5b0cb6f3d158dcd4997f27ec977ab8275e1a7db2e027768c5. Independent review identified prefix-derived false provenance for new files; do not simply regenerate the old snapshot. Domain branch not merged.

Verification on reconciliation tree93c6f21 plus documentation: first targeted command `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest tests/test_capability_completion.py -q -p no:cacheprovider`, PYTHONPATH=checkout/src;checkout, TMPDIR=D:/tmp/history-reconcile, PYTEST_ADDOPTS=--basetemp=D:/tmp/history-reconcile/bt, returned27passed/1setup error0.30s: test_a_superseded_schema_is_refused_not_read, missing parent temp directory (WinError3). Created that directory only, then executed `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main` with the same environment:217passed/2failed10.92s, exit1. Exact failed nodes: tests/foundations/test_v2_blindfold.py::test_the_subprocess_escrow_keeps_its_secrets_in_the_child and tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable. Same219node set and two failures as accepted PR176; zero new failures, zero removed failures. All28capability tests passed within corrected gate. Full suites and OD3 NOT RUN; no green-gate claim.


## 2026-10-20 - Domain inventory reconciliation: red first, provenance boundary repaired

Base3213bb35 (approved PR176 merged), trial merge a80b4df5. Original domain suite command: C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest benchmarks/domain_real_data/tests/test_domain_real_data.py -q -p no:cacheprovider --basetemp=D:/tmp/domain-reconcile-red. PYTHONPATH=checkout/src;checkout; TMPDIR=D:/tmp. Result1failed12passed0.45s exit1, test_repository_scan_is_current.

Added six boundary regressions, then executed same interpreter -m pytest benchmarks/domain_real_data/tests/test_inventory_boundary.py -q -p no:cacheprovider --basetemp=D:/tmp/domain-boundary-red. Result6failed0.10s exit1: three new-path cases inherited DERIVED/REAL_MEASURED, altered measurement inherited REAL_MEASURED, historical replay/identity API absent. These were real red runs before implementation.

Implementation binds archival commit/tree/scanner/report; replays original scan without overwriting it. Live classification no longer grants origin from a prefix to new or changed data. Current coverage/measurement tests read the live inventory. Original dataset/report bytes preserved. Post-change command: same interpreter -m pytest benchmarks/domain_real_data/tests -q -p no:cacheprovider --basetemp=D:/tmp/domain-boundary-fixed; same environment. Result18passed2failed1.83s exit1. Remaining failures: test_synthetic_data_is_never_called_measured (433unknowns) and test_current_repository_inventory_has_no_unreviewed_provenance. Unknowns are not relabeled just to pass. Full assurance/OD3/formal runs NOT RUN. Merge remains BLOCKED pending explicit current provenance reconciliation. Receipts: shared side-session-notes domain-reconcile-2026-10-20/{red,boundary-red,fixed}.{json,txt}; live-inventory.json enumerates exact candidates.

Owner explicitly approved PR177; merged through GitHub with expected headc85f3f7708a8cfaac2ce25a871b45279f7b30dd5. Remote merge31192784a946a3f379422da11d8a2bcf867f62ce fetched. The three already-present branch histories are now ancestors of main. No scientific source changed in that PR.

Owner selected full provenance audit of433files, not a narrower inventory scope. Two independent read-only slice reviews covered245benchmark and157other candidates; parent examined31measurement/reduction/flagship records. Exact declarations bind433artifacts:400DERIVED,22SYNTHETIC,8REFERENCE_ONLY,3REAL_MEASURED. Secondary157-file review-set digest independently matched670c92e9d91935c300ef374c32f63e533170190e16da47ef84cf4b43ff3ef97e. Chen2020 raw SHA256/MD5/length checked against existing manifest; reduced battery role hashes and matching prereg identities checked (closure usesv2). No upstream fetch or raw-data regeneration.

Reviewer Unicode and assume-unchanged counterexamples: command same repository interpreter -m pytest benchmarks/domain_real_data/tests/test_inventory_boundary.py -q -p no:cacheprovider --basetemp=D:/tmp/domain-review-red returned2failed7passed1.28s. Corrected NUL path handling, raw-byte identity and pinned classification source; full domain then21passed2failed6.84s, with433coverage unknowns still explicit. Added5declaration-binding tests: same interpreter -m pytest benchmarks/domain_real_data/tests/test_provenance_declarations.py -q -p no:cacheprovider --basetemp=D:/tmp/domain-declarations-red returned5failed0.10s (missing API); implemented explicit path/artifact/source digest checks, duplicate refusal and required dataset-record references; --basetemp=D:/tmp/domain-declarations-fixed returned5passed0.05s. Added positive historical-control and immutable archived-source test.

After explicit433-file audit: C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest benchmarks/domain_real_data/tests -q -p no:cacheprovider --basetemp=D:/tmp/domain-audited; TMPDIR=D:/tmp; result30passed10.63s exit0. Captured commands/logs preserved as Markdown in docs/work/evidence/domain_inventory_reconciliation_2026_10_20/. Historical21non-code artifacts matched a80b4df5 byte-for-byte. No certificate, certified source, thresholds, formal Genesis run or candidate behavior changed.

Pre-existing scientific finding from provenance review: benchmarks/battery_1rc_closure/evaluate.py::applicable_acceptance retains FAIL when out_of_domain>0. Existing test encodes that behavior. Origin declarations explicitly mark such rejection inadmissible as scientific contradiction; existing evidence bytes remain preserved. This audit does not repair or endorse that scientific acceptance rule.

## 2026-10-20 - Domain provenance final review corrections

Final review reproduced a Git-index/working-tree mismatch in artifact, current producer and review manifest: all3 regression cases failed before repair. Explicit declarations now require stage-0 regular-file identity and raw working bytes to agree, in addition to SHA256 bindings. Archived sources remain bound to their specified immutable Git object. Five locally authored analytical metadata records were corrected REFERENCE_ONLY->DERIVED after independent reviewer agreement; final433 counts405DERIVED22SYNTHETIC3REFERENCE_ONLY3REAL_MEASURED. Earlier400/8 counts above describe the superseded pre-review classification.

The original FAST candidate remains unchanged at tree85b4c044ced35350e6cc583d0ca99821a82394ed (base3213bb35, pending domain merge). To preserve that running measurement, copied its exact index tree into local merge snapshotd5876407c02c4c409bc44f97445dac6247b4539b without changing the measured worktree or HEAD. Final fixes are isolated in codex/domain-inventory-reviewed-2026-10-20. Restored ACTIVE_PLAN historical UTF-8 bytes from main31192784 and retained current domain addition; preserved main's newer PR177 history in PROGRESS.

External trial of the proposed patch: repository interpreter -m pytest D:/tmp/domain-index-trial/benchmarks/domain_real_data/tests -q -p no:cacheprovider --basetemp=D:/tmp/domain-index-trial-bt returned9passed1.70s. This was a copied scanner/test trial, not the integration gate. Final worktree's full domain suite then returned33passed13.00s, including all3 formerly failing staged-identity regressions.

Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest C:/Users/dev_kaeem/AppData/Roaming/Claude/side-session-notes/local_dac3224f-3028-46a9-ab85-20d361143aa4/domain-reconcile-2026-10-20/test_staged_declarations.py -q -p no:cacheprovider --basetemp=D:/tmp/domain-index-red-recorded/bt`

Cwd: `C:/Users/dev_kaeem/.codex/worktrees/review-unmerged-work/wonderful-gould-1c576f`; environment: `{"TMPDIR": "D:/tmp/domain-index-red-recorded", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\review-unmerged-work\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/review-unmerged-work/wonderful-gould-1c576f"}`. Exit 1; elapsed 1.664s. Full output: evidence/domain_inventory_reconciliation_2026_10_20/index-red-recorded.md.

Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest benchmarks/domain_real_data/tests -q -p no:cacheprovider --basetemp=D:/tmp/domain-index-fixed/bt`

Cwd: `C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f`; environment: `{"TMPDIR": "D:/tmp/domain-index-fixed", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\domain-inventory-final\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f"}`. Exit 0; elapsed 13.512s. Full output: evidence/domain_inventory_reconciliation_2026_10_20/index-fixed.md.

Post-PR177 GitHub runs were read live at merge31192784: Tests39474579471 and Branch Policy39474579541 both failure. Scope/reproduce/layout/benchmark/tests-gate and branch-policy jobs expose no executed steps; downstream scientific/mutations/certificate-child/FAST jobs skipped. Cause remains UNVERIFIED; no CI-green or policy-enforcement claim. Local FAST candidate and pristine-main runs still in progress at this entry. No gate bypass, certified-source change, recertification, formal measurement or freeze.

## 2026-10-20 - Domain PR178 full FAST comparison and review

PR https://github.com/sharq-labs/forge/pull/178 published as DRAFT from measured source0047321df0522cbc78bb0a7160aace434699c093. Main control31192784a946a3f379422da11d8a2bcf867f62ce. Independent scientific review PASS (read-only),433 declarations checked;21 historical non-code artifacts byte-identical;43 changed paths at measured source, zero recertification triggers.

The initial two sequential FAST runs were interrupted and cannot establish outcomes; raw partial logs and exact commands/exits retained externally, with interrupted-runs.md describing both. One brief baseline invocation omitted --dist loadfile and was stopped with no captured final result; corrected invocation below matches the final gate's scheduler. No test was excluded to obtain the final comparison.

- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main --workers 4`
  Cwd `C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/domain-final-gate", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\domain-inventory-final\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f", "PYTEST_ADDOPTS": "--basetemp=D:/tmp/domain-final-gate/bt"}`; exit1; elapsed509.451s. Summary:         assert run.returncode == 1 and "1 failed, 1 passed" in run.stdout  # the failure stays a failure; 185 failed, 11725 passed, 235 skipped, 74 warnings, 22 errors in 499.53s (0:08:19). Full node list in `final-changed-gate.md`.

- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest -q -n 4 --dist loadfile -m not expensive --basetemp=D:/tmp/domain-main-loadfile/bt`
  Cwd `C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/domain-main-loadfile", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f"}`; exit1; elapsed431.538s. Summary:         assert run.returncode == 1 and "1 failed, 1 passed" in run.stdout  # the failure stays a failure; 185 failed, 11692 passed, 235 skipped, 74 warnings, 22 errors in 430.69s (0:07:10). Full node list in `main-fast-loadfile.md`.

- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest --collect-only -q -m not expensive --basetemp=D:/tmp/final-collection/bt`
  Cwd `C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/final-collection", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\domain-inventory-final\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f"}`; exit0; elapsed14.822s. Summary: 12147/12729 tests collected (582 deselected) in 12.59s. Full node list in `final-collection.md`.

- Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest --collect-only -q -m not expensive --basetemp=D:/tmp/main-collection/bt`
  Cwd `C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/main-collection", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f"}`; exit0; elapsed14.906s. Summary: 12114/12696 tests collected (582 deselected) in 12.60s. Full node list in `main-collection.md`.


Exact selection comparison:12114 unchanged main nodes,33 added domain nodes,0 removed; shared-node digestda86790a515371f61a87e10946c74e54f5c29154a3b46103815aa8300b834120. Initial helper omitted flagships/providers; corrected parser included all12147/12114 nodes and asserted those totals before comparison.

Exact failing/error node comparison: 0 new, 0 removed, 0 changed failure/error labels. Complete sorted sets and raw-log SHA256s in final-changed-gate-comparison.md. This is not a green gate: baseline failures/errors remain unresolved and are explicitly disclosed for owner review. No test/OD3 bypass or unsupported certification claim.

Preservation classifier helper initially passed a list to its single-path API and raised AttributeError; corrected per-path invocation returned zero recertification paths. Earlier artifacts and scientific behavior unchanged. Final current task: full433-file origin audit completed, PR178 awaits owner review of the concrete change and the failing baseline; no merge performed.

Final documentation check: C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe docs/ai/check_docs.py; cwd final domain worktree, TMPDIR=D:/tmp/domain-doc-check, PYTHONPATH=checkout/src;checkout. Exit0, AI_DOCS: PASS (7documents; metadata/local paths only),0.071s. git diff --check also exit0. Only Markdown documentation/receipts changed after measured0047321d; no source or test edits.

## 2026-10-20 - PR178 merged; assurance history reconciliation

Owner explicitly approved PR178 with the documented completed FAST baseline comparison. Marked ready and merged through GitHub with expected head922745bdf65f5c3d33f589d191f40fc9b24e5461. Merge94aab1f664e79515322a29d203fb02d2d2d9c874 fetched; local origin/main matches. Audit of433files completed; no scientific correctness/certification promotion.

Next branch origin/docs/assurance-performance-investigation tip8862cb5391f3a7bd12fb200d4fa65a2b0ed1b2a1: exact original397-line report is a byte substring of main's report, whose historical-source warning is retained. Report SHA256153ff34e5c621832093b5745ae6fd453132f79eb19ce058346833d7596a45125. All55added PROGRESS lines, including separating blank line, are byte-present on main; SHA2563b6e41361964704281df72e648035ff5290c05b331b75d17bc2656c812f458fe. Python byte assertions executed successfully. Normal merge produced two historical documentation conflicts; retained verified current-main bytes in both. git diff --cached --exit-code returned0. Merge485e272 and base94aab1f6 share exact treeadb7aae9152dd571d098d738958376b44e2110af. Only subsequent task/progress documentation additions differ. No old queue restored, no performance recommendations executed. Changed-file gate and final review pending.

Assurance-history independent read-only review PASS: exact merge-parent/tree identity,397-line report containment,55-line progress containment and unchanged historical warning verified. Executed changed-file gate219nodes:217passed2failed9.75s. Pristine main94aab1f6 same219nodes:217passed2failed10.92s. Exact failed-node sets equal (zero new/removed); failures are tests/foundations/test_v2_blindfold.py::test_the_subprocess_escrow_keeps_its_secrets_in_the_child (isolated Python cannot import engcore.blindfold) and tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable (7versus8 subdivisions). Neither gate is green; no source or test alteration. Commands/receipts:

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main`

Cwd `C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/assurance-history-gate", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f", "PYTEST_ADDOPTS": "--basetemp=D:/tmp/assurance-history-gate/bt"}`; exit1; elapsed13.666233700001612s.

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest -q tests/test_repository_architecture.py tests/test_core_api_layering.py tests/test_scientific_regression_manifest.py tests/test_forge_check.py tests/test_agent_workflow_contract.py tests/test_capability_completion.py benchmarks/battery_1rc_closure/tests/test_battery_1rc_closure.py benchmarks/battery_1rc_crosscell/tests/test_battery_1rc_crosscell.py benchmarks/battery_1rc_identifiability/tests/test_battery_1rc_identifiability.py tests/foundations/test_v2_blindfold.py tests/test_multiphysics_window_control.py --basetemp=D:/tmp/assurance-history-main/bt`

Cwd `C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/assurance-history-main", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\domain-inventory-final\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f"}`; exit1; elapsed11.699759900104254s.

Post-PR178 automatic checks inspected at94aab1f6: Tests39481352938 and Branch Policy39481352941 failed with zero job steps exposed; downstream FAST/scientific/mutations/certificate-child skipped. Cause UNVERIFIED; no CI-green or branch-policy-enforcement claim. No gates bypassed or branch rules changed.

## 2026-10-20 - PR179 merged; archive-only documentation reconciliation

Owner explicitly approved PR179. GitHub merge used expected headffc3a8992c18b89e8204a7495db5d13d32ba7058; returned8b29fc076ba5a9af6e591b5e7acb380ca83ee4f2, fetched and verified. Its automatic Tests39481975853 and Branch Policy39481975898 both reported failure; no green-CI claim.

Read-only review established historical archiving is permitted without adopting superseded scientific wording. Four branches each affect Markdown only. Extracted exact git diff --binary --full-index <merge-base-with-8b29fc07> <source-tip> -- before merging. Preserved those bytes in separate historical.patch archives with source/base IDs, byte lengths and SHA256; wrappers explicitly say not applied, no scientific or execution authority. Kept every live document at pre-merge bytes while reconciling each branch ancestry. This is archive-only preservation, not adoption or full behavioral integration. No source, benchmark, live scientific contract or certificate change.

The earlier fix-bisect reviewer used default abbreviated-index diff (4314bytes/e4f38c...); archived full-index diff is4378bytes/bf3e65... by its explicitly stated command. Both describe the same original change; no historical test was rerun or promoted.

Archive receipts:

```json
[
  {
    "name": "fix-bisect-table",
    "tip": "1cd5ca6c18a4efed4a9c2780b762eff73751d391",
    "base": "2f7e2ef0d5a48e5d828c1fb5bc12a56a601b5d02",
    "before": "8b29fc076ba5a9af6e591b5e7acb380ca83ee4f2",
    "commit": "14f5c5075d60083371cb2dacc1372ea0a1c65d15",
    "paths": [
      "NEEDS.md"
    ],
    "patch_sha256": "bf3e65bd6ac7faa1d278d684a543ba9811f4d8c532ec933facd1c2e7ec76103e",
    "bytes": 4378,
    "merge_exit": 1,
    "merge_output": "Auto-merging docs/project/needs.md\nCONFLICT (content): Merge conflict in docs/project/needs.md\nAutomatic merge failed; fix conflicts and then commit the result.\n"
  },
  {
    "name": "evidence-v11",
    "tip": "9a34727e40cddad9b58f004e6ee4626fc0f3fda6",
    "base": "c3837690537a443b6b9d58b500c6db0b27429d74",
    "before": "14f5c5075d60083371cb2dacc1372ea0a1c65d15",
    "commit": "91eda4f24b44534a30f8b35be39c67c0af413da8",
    "paths": [
      "NEEDS.md"
    ],
    "patch_sha256": "c8cdbc1e9056eb49be26034a7f5ef5cbc269af5945a10eaa9037a7b77cffd64f",
    "bytes": 4691,
    "merge_exit": 1,
    "merge_output": "Auto-merging docs/project/needs.md\nCONFLICT (content): Merge conflict in docs/project/needs.md\nAutomatic merge failed; fix conflicts and then commit the result.\n"
  },
  {
    "name": "blind-rediscovery-benchmark-v1",
    "tip": "4872b10b15e7d4b41a19a965998765d9884963f5",
    "base": "4634eba2bb947bbcce0f54406464766ea08167d9",
    "before": "91eda4f24b44534a30f8b35be39c67c0af413da8",
    "commit": "b2c59bbc552d76c14135675c2bc921572c567de3",
    "paths": [
      "docs/discovery/FORGE_GENESIS.md"
    ],
    "patch_sha256": "eeb8d22c02c1ad903872895a6d9fa453e22f8eba66eab9eb0d78d0f20da7ce88",
    "bytes": 38393,
    "merge_exit": 1,
    "merge_output": "Auto-merging docs/discovery/FORGE_GENESIS.md\nCONFLICT (add/add): Merge conflict in docs/discovery/FORGE_GENESIS.md\nAutomatic merge failed; fix conflicts and then commit the result.\n"
  },
  {
    "name": "big-13-flagship-demonstrations",
    "tip": "6dfc60b0d88abeb465e9cea43fea8c7a32282d0d",
    "base": "ac600555e5b2b4c824b05d815eae4ae18e895cc7",
    "before": "b2c59bbc552d76c14135675c2bc921572c567de3",
    "commit": "0297363215fa85073bb946649166425010823309",
    "paths": [
      "docs/architecture/README.md",
      "docs/architecture/design_synthesis.md",
      "docs/architecture/mechanistic_discovery.md",
      "docs/project/FORGE_MASTER_PLAN.md",
      "docs/work/ACTIVE_PLAN.md",
      "docs/work/PROGRESS.md"
    ],
    "patch_sha256": "bd9f84e9c0055db757e418949f1cff95b6e92fe6931254c9fa16d791e048e852",
    "bytes": 48669,
    "merge_exit": 1,
    "merge_output": "Auto-merging docs/architecture/README.md\nCONFLICT (content): Merge conflict in docs/architecture/README.md\nAuto-merging docs/architecture/design_synthesis.md\nCONFLICT (add/add): Merge conflict in docs/architecture/design_synthesis.md\nAuto-merging docs/project/FORGE_MASTER_PLAN.md\nCONFLICT (content): Merge conflict in docs/project/FORGE_MASTER_PLAN.md\nAuto-merging docs/work/ACTIVE_PLAN.md\nCONFLICT (content): Merge conflict in docs/work/ACTIVE_PLAN.md\nAuto-merging docs/work/PROGRESS.md\nCONFLICT (content): Merge conflict in docs/work/PROGRESS.md\nAutomatic merge failed; fix conflicts and then commit the result.\n"
  }
]
```

Archive independent review PASS at02973632: all4payloads reproduced byte-identically, wrappers/hash/base/ancestry/links verified; each merge only added its two archive files. No live scientific contracts, tests, source or policies changed. Reviewer ran git diff --check and observed exit1 because exact raw Git patches contain single-space context lines; those bytes are intentionally preserved, not normalized. Authored documentation is checked separately; no claim that raw-payload whitespace check passed.

Changed-file gate217passed2failed (219nodes); pristine main8b29fc07 exactsame219nodes217passed2failed8.92s. Same failed nodes as preceding history gate: subprocess escrow module import, window subdivision7versus8. Zero new/removed failed nodes; no green gate. Exact receipts:

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main`

Cwd `C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/archive-doc-gate", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f", "PYTEST_ADDOPTS": "--basetemp=D:/tmp/archive-doc-gate/bt"}`; exit1; elapsed12.023089699912816s.

`C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -m pytest -q tests/test_repository_architecture.py tests/test_core_api_layering.py tests/test_scientific_regression_manifest.py tests/test_forge_check.py tests/test_agent_workflow_contract.py tests/test_capability_completion.py benchmarks/battery_1rc_closure/tests/test_battery_1rc_closure.py benchmarks/battery_1rc_crosscell/tests/test_battery_1rc_crosscell.py benchmarks/battery_1rc_identifiability/tests/test_battery_1rc_identifiability.py tests/foundations/test_v2_blindfold.py tests/test_multiphysics_window_control.py --basetemp=D:/tmp/archive-doc-main/bt`

Cwd `C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f`; env `{"TMPDIR": "D:/tmp/archive-doc-main", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\domain-inventory-final\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/domain-inventory-final/wonderful-gould-1c576f"}`; exit1; elapsed9.596498799975961s.


## 2026-10-20 — agent configuration archive and post-PR180 CI diagnosis
Base main67585300; archive merge ce32f6a6. Owner authorized continuing review, not automatic merge or OD3. No source/config/test behavior changed. Exact source delta42088 bytes SHA256409329d709dce4878fbe1f7269709b16b22254e365111e65c9156894e498046b.

### agent-archive-gate
Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main`
CWD: `C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f`
Environment: `{"TMPDIR": "D:/tmp/agent-archive-gate", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f", "PYTEST_ADDOPTS": "--basetemp=D:/tmp/agent-archive-gate/bt"}`
Result:94 passed; exit0; wall seconds 9.46724779997021. Output SHA256 `855ffe277d9873091431c6b907203b110686f72306d4914d9a224d8b849a18f7`. No failures. Raw output and metadata: `docs/work/evidence/branch_ci_investigation_2026_10_20/agent-archive-gate.txt` and `.json`.

### agent-archive-final-gate
Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe tools/forge_check.py --changed --base origin/main`
CWD: `C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f`
Environment: `{"TMPDIR": "D:/tmp/agent-archive-final", "PYTHONPATH": "C:\\Users\\dev_kaeem\\.codex\\worktrees\\merge-main-control\\wonderful-gould-1c576f\\src;C:/Users/dev_kaeem/.codex/worktrees/merge-main-control/wonderful-gould-1c576f", "PYTEST_ADDOPTS": "--basetemp=D:/tmp/agent-archive-final/bt"}`
Result:94 passed; exit0; wall seconds 9.618442600010894. Output SHA256 `f75e069f24587ae62416522acbc9e5c5498e672480338a60c39a06ef6fa6e4c4`. No failures. Raw output and metadata: `docs/work/evidence/branch_ci_investigation_2026_10_20/agent-archive-final-gate.txt` and `.json`.

Live GitHub Tests39488053735 and Branch Policy39488053796 failed with empty step metadata; dependent jobs reported skipped. Logs for branch-policy118853558670 and scope118853560388 returned404 BlobNotFound. Annotations unavailable through connector; browser signed out. Root cause UNVERIFIED pending owner-provided annotation. No billing diagnosis, workflow repair or hosted rerun claimed. Formal, full assurance and OD3 NOT RUN.

## 2026-10-20 - Genesis-lite v0.3 clean rebuild on restored main (N-1 open)

PR #182 restored main to 12862b0b (tree 9e84851a, identical to pre-#174 main 9f1c24f1). Branch `feat/genesis-lite-v03-clean-n1` was rebuilt from 12862b0b without re-merging `feat/genesis-lite-v03-escrow-fda05` (b4fbb1d5) or `codex/mind-development-evidence-2026-10-20` (5935958c). Both remain preservation history.

Brought forward as byte copies in transfer commit 32f8854d; no file was edited:
- From 1cb5e187, the Genesis tip before PR #175 was stacked on it. All 32 paths are unchanged through b4fbb1d5:
  - `benchmarks/genesis_lite/v0_3/` (16 files);
  - the v0.3 preregistration and its pin (026f538d);
  - `src/engcore/blindfold/pair_bound.py`;
  - `docs/discovery/GENESIS_LITE_V0_3_AMENDMENT_DECISION_RECORD.md` and its DOCSET line;
  - the three preregistration-pinned evidence records: power study 9ad27938, D5 deployment 519f3669, D7 timing pilot 3759ff33;
  - three v0.3 test modules (amendment, blockers, escrow_fda05) and two helpers (`stateful_arms.py`, `vacuous_arm.py`).
- From 1b90f94c (PR #175), only the N-1 failing-first files: `test_genesis_lite_v0_3_container_isolation.py`, `test_genesis_lite_v0_3_container_contract.py` and `container_isolation_probe.py`. They need no environment variable and no source-SHA pin, although the contract fixtures carry a pinned image digest. One contract test is Linux-only. The 32f8854d message calls them "platform-independent"; that is true of all but that one test.

A separate commit adds a dated status correction (§6 plus a banner) to the decision record. Its inherited header and §1/§4 status claims (READY_TO_FREEZE_PENDING_OWNER, FDA-18 residual "closed by D5", P-1/P-2 "FIXED by D5", "D5 verified") contradict `readiness.LEDGER`. No D1-D7 decision text was changed. §6 also records an open owner decision: the N-1 tests presuppose a Podman container launcher and a pinned local image, but the recorded D5 decision is option A1 (rootless namespaces). The owner must record that D5 amendment before the N-1 repair.

Excluded:
- `engcore.mind.minimal`, `benchmarks/genesis_lite_mind`, `tests/genesis_lite_mind`;
- the three `tools/forge_*` Mind/demo scripts and `test_blindfold_demo.py`;
- the Blindfold demo and Mind discovery docs;
- the 269 PR #175 evidence files: Mind diagnosis 129, Mind readiness 34, checkpoint-2 47, public demo 13, branch merge review 46;
- the two Podman runtime rigs:
  - `test_genesis_lite_v0_3_container_runtime.py` needs a local image, `/home/dev_kaeem/forge-card/Containerfile` and `FORGE_CHECKPOINT_SOURCE_SHA`;
  - `test_genesis_lite_v0_3_readonly_inventory.py` asserts `source_sha == 1cb5e187`;
  - both are Linux-only. The docstring of `test_genesis_lite_v0_3_container_isolation.py` still mentions those sibling rigs.
- the PR #174/#175 ACTIVE_PLAN and PROGRESS narrative.

Evidence binding. All three evidence records are HISTORICAL_ONLY for their recorded heads: power study 20f3d379, D5 a4d73dd4, D7 f7df8968. f7df8968 is reachable from no ref. D5 and D7 REQUIRE_RERUN and REQUIRE_REPIN after the N-1 repair. Nothing was regenerated.

Status: D5 = NOT_PROVEN; FDA-18 residual = NOT_PROVEN; N-1 = OPEN; formal campaign FORBIDDEN. `pair_bound.py` is the only certified-scope change against main (verdict_authority area, ADDED). It stays UNCERTIFIED until OD-3. No formal run, freeze, OD-3 or certification happened.

Tests ran on Windows, using the shared venv with `PYTHONPATH=D:/forge-genesis-clean/src;D:/forge-genesis-clean`:
- `python -m pytest -q -p no:cacheprovider -n 4 -rfEs tests/genesis_lite` at 32f8854d: 90 failed, 292 passed, 1 skipped, identical in both runs. All 90 failures are N-1 failing-first:
  - 73 in container_contract, all `MISSING_VALIDATION_CONTRACT`;
  - 17 in container_isolation: the fresh-container argv, seven security flags, four private tmpfs mounts, read-only binds, image digest, deployment verification, runtime-failure-before-admission and the private-/tmp counterexample.
  - The shared-directory positive control passed. It is a filesystem control, not a mounted Podman volume.
  - Skipped: `test_probe_uses_fd_mount_and_distinguishes_absence_error_and_obscured` (Linux fdinfo; NOT RUN).
- `python -m benchmarks.genesis_lite.v0_3.readiness` at 32f8854d and fb23bc35: BLOCKED_TECHNICAL on exactly the three NOT_PROVEN rows. 177 v0.3 tests passed at the clean HEAD, and evaluator and escrow agreed on 48 of 48 cases.
- `python -m pytest tests/test_core_certificate.py tests/test_certified_dependency_closure.py tests/test_recertification_scope.py tests/test_certificate_verdict_scope.py`: 2 failed, 241 passed, 2 skipped at both 32f8854d and the PR #182 revert commit 504ef32f, whose tree equals 12862b0b. The two failures already exist on main (OD-3 drift):
  - `test_core_certificate.py::test_the_certificate_describes_this_tree`;
  - `test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully`.
  The verifier output differs from main only by `ADDED: src/engcore/blindfold/pair_bound.py`.
- FAST, SCIENTIFIC, FULL and hardened recertification: NOT RUN. `python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py --check` reproduced the historical REPOSITORY_SCAN.json on both trees. It exits 1 on both:
  - main tree (504ef32f): 6 live UNKNOWN_PROVENANCE files, all under `branch_ci_investigation_2026_10_20`;
  - this branch: 11. The 5 extra are `genesis_lite_v0_3.json`, `docs/ai/DOCSET.txt`, and the D5, D7 and power-study `result.json` files.
  No provenance declaration was added; that is a separate reviewed edit to `CURRENT_PROVENANCE.json`. No test or workflow runs this scan.

## 2026-10-21 - D5-A1b implemented; N-1 evidence pinned and BLOCKED by host device nodes (N-1 open)

Owner decisions (2026-10-21, in session):
- **D5-A1b.** Rootless Podman per-card isolation supersedes A1 for the formal deployment. The fifth review showed the hand-built namespace probe had not proven cross-card state isolation outside /tmp.
- **D7 head preserved.** The annotated local tag `evidence/d7-timing-pilot-head-2026-10-20` now points at f7df8968. It is not pushed. D7 stays HISTORICAL_ONLY / REQUIRES_RERUN / REQUIRES_REPIN_AFTER_N1.
- **Device nodes: "Keep strict: block".** Rootless crun bind-mounts six host character devices read-write into every container (/dev/null, zero, full, random, urandom, tty). They get no exemption.

Branch `feat/genesis-lite-v03-clean-n1` (D:/forge-genesis-clean), on top of 5b30c09b:

| Commit | Content |
|---|---|
| d2d0cb4b | Implementation (below). |
| c09b0ef5 | The cgroup-root reconciliation fix. |
| a1935b72 | First evidence pin and the decision record. |
| 754f6cdb | Read-only review fixes (MAJOR-1 and minors). |
| 4ec70275 | Evidence re-pin. |

Implementation:
- `container_evidence.py`: the pure validator for the 64-case N-1 contract.
- `container_probe.py`: the in-container probe, which uses the validator's own parser.
- `isolation.py`: the A1b launcher, card removal, and the collection and verification of container evidence.
- `deployment_attacks.py`: `cross_card_state` is never REFUSED from one directory, and `verify_deployment` needs container evidence that PASSED.
- `formal.deployment_problems`: fresh A/B/C container evidence must PASS before admission, on a clean committed tree. A production run refuses a caller-supplied check.
- `harness.py`: per-card container name, environment forwarding and removal on close.
- `readiness.py`: the D5 rows and the D7 evidence row follow their pinned evidence.
- `container/Containerfile`: byte copy of the pinned image's build file.
- Preregistration regenerated; still DRAFT.

Tests:
- The A1 launcher tests were replaced by A1b equivalents.
- One positive-control assertion changed from REFUSED to UNTESTABLE. The sibling N-1 test forbids REFUSED from a tmp parent, and a probe cannot tell the two inputs apart.

Failed approaches, recorded so later sessions do not repeat them:
1. A strict validator compared the card's mount view with the operator's host-side view field for field. Every real run failed on the cgroup2 root, which the kernel reports relative to the reader's cgroup namespace. Fixed by tolerating exactly that field on cgroup rows.
2. The launcher options tried did not remove the six device binds: `/dev` as a read-only tmpfs only drops devpts and mqueue. No other launcher configuration was tested, so this is a finding about this launcher, not a proof about rootless Podman.
3. UNC access to the WSL distro is unavailable (hardened). Files go in through `wsl.exe` stdin, and shell variables in inline `bash -c` strings get expanded early, so use `bash -s` scripts.

Evidence. `docs/work/evidence/genesis_lite_v0_3_d5_a1b_deployment_2026_10_21/result.json`, sha256 590bfa4f..., from a clean clone of 754f6cdb on the formal machine. It was pinned at 4ec70275 and superseded by the d4ead0b2 run (see the addendum).
- The verdict is `verified: false`.
- Container evidence is BLOCKED solely by DEVICE_NODE_WRITABLE_MOUNT and UNDECLARED_WRITABLE_MOUNT, on the six devices in each of cards A, B and C. Every other contract check held.
- 11 of 12 channels are REFUSED. `cross_card_state` is UNTESTABLE, and every probe has power.
- The c09b0ef5 run (5ccccd42) is kept under `superseded-c09b0ef5/`.

Status: D5 = NOT_PROVEN; FDA-18 residual = NOT_PROVEN; N-1 = OPEN; formal campaign FORBIDDEN. `src/`, `certification/` and `.github/` are untouched in this range. `pair_bound.py` stays the only certified-scope change against main. No formal run, freeze, OD-3 or certification happened.

Commands run. Windows uses the shared venv with `PYTHONPATH=D:/forge-genesis-clean/src;D:/forge-genesis-clean`. Linux uses `~/venvs/forge312`, inside a fresh clone.

| Where | Commit | Command | Result |
|---|---|---|---|
| Windows | 4ec70275 | `python -m pytest -q -p no:cacheprovider -n 4 -rfEs tests/genesis_lite` | 388 passed, 2 skipped (both Linux-only fdinfo tests) |
| Linux | d2d0cb4b | `python -m pytest -q -p no:cacheprovider -n 4 tests/genesis_lite` | 384 passed, 1 failed: the D5 evidence test, which waited for the A1b evidence |
| Linux | a1935b72 | same | 387 passed, 0 skipped |
| Linux | a1935b72 | `python -m benchmarks.genesis_lite.v0_3.readiness` | BLOCKED_TECHNICAL on the three D5 rows plus D7 timing pilot evidence (REQUIRES_RERUN); 293 v0.3 tests passed; agreement 48/48 |
| Linux | c09b0ef5 | `python -m benchmarks.genesis_lite.v0_3.isolation --out result.json --cards 2` | exit 1, BLOCKED (superseded) |
| Linux | 754f6cdb | same | exit 1, BLOCKED (pinned) |
| Windows | a1935b72 | certificate verifier render diff against the transfer commit | identical (only `ADDED pair_bound.py` against main) |

NOT RUN: FAST, SCIENTIFIC, FULL, hardened recertification, the D7 timing pilot rerun and any formal campaign.

Addendum (2026-10-21), second review pass and re-pin:
- The second read-only pass found 0 BLOCKER, 1 MAJOR and 5 MINOR. MAJOR-1 was only partly closed by 754f6cdb, and that commit's message overclaimed: a read-only bind of a whole host tmpfs (such as a socket directory) or of the host's procfs is labelled "container" or "kernel" and was never checked.
- d4ead0b2 replaces that rule with an allowlist for every read-only row, by target and filesystem and whatever the backing label. It also adds:
  - binds tied to their kept tree by device and root;
  - userdata tied to this container id;
  - Podman's fixed default mask lists;
  - normalised volume sources;
  - an exact-sentinel `cross_card_state` upgrade.
- The verification was re-run from a clean clone of d4ead0b2. `result.json` sha256 29c72411... is now pinned, with the same verdict: BLOCKED solely by the six host device nodes. No undeclared read-only mount was found, and 11 of 12 channels were REFUSED.
- The runs at 754f6cdb (590bfa4f) and c09b0ef5 (5ccccd42) are kept under `superseded-*/`.
- Tests: on Windows at the re-pin commit, `python -m pytest -q -p no:cacheprovider -n 4 -rfEs tests/genesis_lite` gave 388 passed, 2 skipped (Linux-only). The Linux run at 9a4b53c6 gave 390 passed, 0 skipped, with readiness BLOCKED_TECHNICAL on the three D5 rows and the D7 evidence row.
- NOT RUN: FAST, SCIENTIFIC, FULL, hardened recertification, the D7 rerun and any formal campaign.
- Third read-only pass at e7e35546: 0 BLOCKER, 0 MAJOR (MAJOR-1 closed), 2 MINOR. Both MINORs stay OPEN, and both must be fixed (followed by a re-run and re-pin) before any D5-A1b evidence that PASSES is pinned:
  1. Some allowlist rows check only fstype and root. Needed: a card-view root of `/` for `/sys/fs/cgroup`, the read-only `/proc` re-binds on the device of the card's own `/proc` row, and the masks and `/dev` as fresh `size=0k` or unique-device tmpfs. Without this, a host-configuration mount at the same target as one of Podman's own, such as a host procfs at `/proc/sys`, could pass.
  2. Each kept tree needs exactly one row at its target, with `bound[path] == host`.
  Neither can be produced by the current launcher. The current evidence is BLOCKED by the device nodes regardless.
- Linux at e7e35546 (fresh clone): `python -m pytest -q -p no:cacheprovider -n 4 tests/genesis_lite` gave 390 passed, 0 skipped. `python -m benchmarks.genesis_lite.v0_3.readiness` gave BLOCKED_TECHNICAL on the three D5 rows and the D7 evidence row; 296 v0.3 tests passed, agreement 48/48. The tree was clean afterwards and no container was left.
- Hardening of the third-pass MINORs (owner request, 2026-10-21; strict device rule kept), in ad55b7c5:
  - Podman's own read-only mounts are now tied to device, root and size:
    - `/sys/fs/cgroup` needs card-view root `/`;
    - the `/proc` re-binds must be on the device of the card's own `/proc`;
    - masks must be empty `size=0k` tmpfs on a device no other row of the card uses;
    - `/dev` must be a tmpfs on its own device;
    - every allowlisted target holds exactly one row.
  - Each kept tree has exactly one row, bound exactly once from exactly its host path. Two `--volume` entries at one target are refused.
- Before the re-run, the then-pinned d4ead0b2 evidence was re-validated with the new validator on Windows, by running `validate_container_evidence(result["container_evidence"], expected=result["container_expected"])` in the shared venv. It gave BLOCKED with reasons exactly DEVICE_NODE_WRITABLE_MOUNT and UNDECLARED_WRITABLE_MOUNT: 36 details, none of any other kind.
- Re-run on the formal machine from a clean clone of ad55b7c5: `python -m benchmarks.genesis_lite.v0_3.isolation --out result.json --cards 2`, exit 1, wall time 275.3 s. Pinned at 261b7703: `result.json` sha256 a9bc4c64.... It has the same verdict, BLOCKED solely by the six host device nodes, and every read-only row passes the tightened ties. The tree was clean before and after, and no container was left. The d4ead0b2 run is kept under `superseded-d4ead0b2/`.
- Tests:
  - Windows at 261b7703: `python -m pytest -q -p no:cacheprovider -n 4 -rfEs tests/genesis_lite` gave 388 passed, 2 skipped (Linux-only).
  - Linux at 261b7703 (fresh clone): the same suite gave 390 passed, 0 skipped. `python -m benchmarks.genesis_lite.v0_3.readiness` gave BLOCKED_TECHNICAL on the three D5 rows and the D7 evidence row; 296 v0.3 tests passed, agreement 48/48.
- Fourth read-only pass: 0 BLOCKER, 0 MAJOR, 2 MINOR. Both third-pass MINORs are closed, and the pinned evidence re-derives. MINOR-B (this PROGRESS record) is done here. One item stays OPEN and must be fixed (followed by a re-run and re-pin) before any D5-A1b evidence that PASSES is pinned:
  - **MINOR-A.** A host procfs or sysfs mounted at `/proc` or `/sys` itself would pass, because every re-bind and mask tie is relative to that row.
  - Fix: the probe records PID-namespace evidence (`NSpid`, or what PID 1 is), or the operator compares the card's `/proc` and `/sys` devices with the host's own.
  - It needs a host-configuration mount that replaces Podman's own `/proc`, which the current launcher does not produce.
- NOT RUN: FAST, SCIENTIFIC, FULL, hardened recertification, the D7 rerun and any formal campaign.
- MINOR-A fixed (owner request, 2026-10-21; strict device rule kept), in 12baeb04: the evidence must now prove that the card's `/proc` and `/sys` are its own.
  - **Probe** (`pid_namespace`): through its `/proc`, the card is PID 1 with NSpid exactly `["1"]`, in a PID namespace other than the operator's (PID_NAMESPACE_NOT_PRIVATE otherwise).
  - **Operator** (`host_pseudo_devices`): the card's `/proc` and `/sys` are not on the operator's own procfs and sysfs devices (HOST_PSEUDO_FS_VISIBLE otherwise).
  - **Positive control**: a container given the host procfs at `/hostproc` must show the host PID first (PID_NAMESPACE_CONTROL_FAILED otherwise).
  - **Contract fixture**: extended with these fields only. Nothing was removed.
- Lab on the formal machine (`exp4.sh` via `bash -s`):
  - a card sees NSpid `["1"]` and 1 process; through the host procfs, NSpid `["22255","1"]` and 31 processes;
  - card `/proc` 0:87 against host 0:59, and card `/sys` 0:88 against host 0:22.
- Test change in `test_o1_lift_decision_passes_the_keyed_stream_to_the_monte_carlo_p`:
  - **Failure:** after the regeneration, Windows `pytest` of that test failed 3 times out of 3 with `2 == 3`, meaning two of the three Monte-Carlo p values coincided.
  - **Why:** the stream key includes the preregistration digest, so every regeneration re-rolls a coincidence of about 1 %, as 4296d535 noted for the nonce.
  - **Fix:** the test now requires the three streams to be distinct and the p values not all equal. The direct assertion that each root's stream reaches `sign_flip_p` is kept.
- Re-run on the formal machine from a clean clone of 12baeb04: `python -m benchmarks.genesis_lite.v0_3.isolation --out result.json --cards 2`, exit 1, wall time 277.4 s. Pinned at bb52c12f: `result.json` sha256 967f089e....
  - Every card: PID 1, NSpid `["1"]`, 1 process, PID namespace not the operator's; `/proc` and `/sys` on devices other than 0:59 and 0:22.
  - Control: NSpid `["22858","1"]`, 28 processes.
  - Verdict unchanged: BLOCKED solely by the six host device nodes. 11 of 12 channels REFUSED.
  - The tree was clean before and after, and no container was left. The ad55b7c5 run is kept under `superseded-ad55b7c5/`.
- Tests:
  - Windows at bb52c12f: `python -m pytest -q -p no:cacheprovider -n 4 -rfEs tests/genesis_lite` gave 389 passed, 3 skipped (Linux-only).
  - Linux at bb52c12f (fresh clone): the same suite gave 392 passed, 0 skipped. `python -m benchmarks.genesis_lite.v0_3.readiness` gave BLOCKED_TECHNICAL on the three D5 rows and the D7 evidence row; 298 v0.3 tests passed, agreement 48/48.
- Fifth read-only pass: 0 BLOCKER, 0 MAJOR, 1 MINOR (this PROGRESS record, done here). MINOR-A is closed. No review item remains open before a PASS pin; the strict device rule is what blocks.
- Untested branches, recorded as NOTES:
  - the "no /proc row" path;
  - malformed or UNKNOWN `host_devices` values;
  - a control with NSpid ≥ 2 but only 1 visible process.
- NOT RUN: FAST, SCIENTIFIC, FULL, hardened recertification, the D7 rerun and any formal campaign.

## 2026-10-21 — Prompt 3: D5-A1b STATELESS_DEVICE contract; D5 pin reverted after hostile review (BLOCKER 1)

Branch `feat/genesis-lite-v03-clean-n1` (D:/forge-genesis-clean), local, unpushed. Started from `0805a861` (clean).

- **Owner device policy (2026-10-21).** A shared writable character device may be admitted only on executed
  evidence, per device, from {/dev/null 1:3, zero 1:5, full 1:7, random 1:8, urandom 1:9, tty 5:0}. It is recorded in
  decision record §8 and in the D5 text of the preregistration.
- **`2e2a9d1b` (kept).**
  - `device_contract.py`: `stateless_device/1`, a per-device validator plus a static scientific-randomness screen.
  - `container_probe.py`: the device observation.
  - `container_evidence.py`: contract/3.
  - `isolation.py`: selected-message trials, a shared-file channel control, a pty-allocated tty control and the
    pinned kernel.
  - The four saved items:
    1. a missing `/proc` or `/sys` row is EVIDENCE_INCOMPLETE;
    2. malformed or unknown operator device records block;
    3. the host-procfs control needs both signals;
    4. the O-1 keyed-stream test proves distinct streams and per-stream recomputation, with no p-difference
       requirement.
- **`f8bf7ed7` (kept).** `timing_pilot/2` refuses to time anything unless the pre-admission container check passes,
  and records that check.
- **D5 run (reverted).**
  - From a clean bundle clone of `2e2a9d1b` on the formal machine:
    `python -m benchmarks.genesis_lite.v0_3.isolation --out result.json --cards 2`, exit 0, 278.5 s.
  - Result: `verified: true`, six devices ADMITTED, 12/12 channels REFUSED; sha256 `b3bc0b64…`. Pinned at `b1fbefbf`.
- **D7 run (reverted).**
  - From a clean clone of `f8bf7ed7`: `python -m benchmarks.genesis_lite.v0_3.timing_pilot --out result.json
    --campaigns 10`, exit 0, 681.5 s.
  - MEASURED 67.9 s per world set (±0.46). ESTIMATED 90.5 h with replay, 45.2 h for the operator's run.
    sha256 `6f6b1418…`. Pinned at `99959b09`.
- **Verification at `99959b09` (Linux, clean clones).**
  - FAST `pytest -q -m "not expensive" -n 4`: 71 failed, 12064 passed, 217 skipped, 8 errors.
  - The same command at `0805a861`: 71 failed, 11975 passed, 217 skipped, 8 errors. The failure sets are identical
    (79 ids, all pre-existing, in phase1/phase2/phase35, core freeze/certificate, offline_revalidation and
    domain_real_data).
  - `tools/forge_check.py --regression --workers 4`: 279 passed.
  - `python -m benchmarks.genesis_lite.v0_3.readiness`: READY_TO_FREEZE_PENDING_OWNER, 0 technical blockers,
    agreement_cases 48. This verdict is now known to be wrong (see below).
  - `pytest tests/genesis_lite -n 4`: Linux 481 passed; Windows 477 passed, 4 skipped.
- **Hostile read-only review of `99959b09`: 1 BLOCKER, 2 MAJOR, 7 MINOR, 5 NOTE.**
  - **BLOCKER 1, confirmed on the formal machine.** A formal card can change persistent metadata of the shared host
    device nodes without opening them, and the change is visible to later cards. This is a cross-card state channel.
    The STATELESS_DEVICE trials compared metadata only around write() and never tested it, so all six devices were
    ADMITTED wrongly. The D5 PASS is therefore invalid. (The confirming test changed the six host nodes' timestamps
    on the WSL machine; harmless, until restart.)
  - **Failed approaches, do not repeat.**
    - `--device /dev/null:/dev/null:r`: the mount stays rw, and the channel remains.
    - `--mount type=bind,src=/dev/null,dst=/dev/null,ro`: Podman stacks its own rw bind on top, and the channel
      remains.
  - **Open.**
    - MAJOR 1: the reachable-device walk only counts unreadable directories (3 per card) and ignores lstat errors.
    - MAJOR 2: the formal attempt keeps only the pre-admission verdict, not its device evidence.
    - The MINORs:
      - the RNG counters have no power on 6.6 (fixed at 256);
      - the tty control is weak, and its id is null;
      - host-to-card observation is not tested;
      - D7 binds only 7 files;
      - the gate takes the bound-file list from the evidence;
      - the admission-nonce allowlist text is wrong (the nonce also enters `master_for`);
      - None seeds pass the screen.
- **Reverted (owner, 2026-10-21).** `e0e73e81` reverts `99959b09`, and `3d62b494` reverts `b1fbefbf`.
  - The pins are back to D5 `967f089e…` (12baeb04, BLOCKED) and D7 `3759ff33…` (2026-10-20).
  - `readiness.deployment_status()` = NOT_PROVEN (schema /3 is not /4, REQUIRES_RERUN), and
    `timing_pilot_status()` = NOT_PROVEN (REQUIRES_RERUN).
  - The revert also drops two follow-ups those commits held. Re-apply both with the next D5 pin:
    - the readiness "isolation boundary (D5)" row had no required tests;
    - the escrow readiness test hard-codes BLOCKED.
- **Tests at `3d62b494` (Windows).** `python -m pytest -q -p no:cacheprovider -n 4 tests/genesis_lite`: 476 passed,
  4 skipped, 1 failed. The failure is `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code`: the
  pinned D5 evidence measured older code, which is the correct red until D5 is re-run.
- **Status.** D5 = NOT_PROVEN, N-1 = OPEN, D7 = REQUIRES_RERUN. BLOCKED_WITH_PRECISE_EVIDENCE.
- **Owner direction needed** before any further device work: how, or whether, the six device nodes can be made
  non-state-carrying or inaccessible under rootless Podman. If not, D5 stays blocked on this runtime.
- **NOT RUN.** SCIENTIFIC, FULL, hardened recertification (the classifier flags it as owner-run), OD-3, any formal
  campaign, Budget × Noise.

### 2026-10-21 (later): owner decision ADMIT_ONLY_PROVEN_STATELESS_SUBSET — BLOCKED_WITH_PRECISE_EVIDENCE

- **Decision received.**
  - Admit only null 1:3, zero 1:5 and full 1:7, as proven STATELESS_DEVICE endpoints.
  - Make random 1:8, urandom 1:9 and tty 5:0 inaccessible, with Podman's `--security-opt mask=`.
  - Recorded in decision record §9.
- **Blocked before implementation.** BLOCKER 1 was confirmed on the formal launcher (in this session, before the
  revert) for all six nodes, null, zero and full included. Masking random, urandom and tty does not address it for
  the admitted three. The decision's own requirement that a fresh Card B cannot recover a value left by Card A
  therefore cannot be met with any configuration shown so far.
- **Not done.** No masking flag was added and no D5 or D7 run was made, so there is no new evidence. The device work
  is stopped pending a way to close BLOCKER 1 for null, zero and full, or an owner decision on it.
- **Done.**
  - `61150afd` re-applies the two lost fixes: the readiness "isolation boundary (D5)" row names exact tests, with a new
    test that no D5 row verifies without them all passing; and the escrow readiness test derives its status.
  - The saved edge cases were already closed in `2e2a9d1b`: `test_d5_a_missing_proc_or_sys_row_*`,
    `test_d5_malformed_or_unknown_host_device_values_block`, `test_d5_the_host_procfs_control_cannot_pass_on_one_signal`
    and the rewritten `test_o1_lift_decision_passes_the_keyed_stream_to_the_monte_carlo_p`.
- **Tests (Windows, at `61150afd`).** `python -m pytest -q -p no:cacheprovider -n 4 tests/genesis_lite`: 477 passed,
  4 skipped, 1 failed. The failure is `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code`, a
  correct red because the pinned D5 evidence measured older code.
- **Status.** D5 = NOT_PROVEN, N-1 = OPEN, D7 = REQUIRES_RERUN.
- **NOT RUN.** Linux suite at `61150afd`, FAST, SCIENTIFIC, regression, readiness CLI, D5, D7, review, OD-3.

### 2026-10-21 (later): owner decision CHANGE_RUNTIME_BOUNDARY — current runtime closed as BLOCKED

- **Branch.** `feat/genesis-lite-v03-clean-n1` from `d8e0eb29` (clean), local, unpushed.
- **Not done.** No device experiment, no D5 or D7 run, no policy change.
- **Decision.** The rootless Podman formal-card runtime is closed as **BLOCKED_BY_D5_DEVICE_BOUNDARY**. A replacement
  runtime is not selected.
- **Records.**
  - Decision record §10: the evidence taxonomy, the dated corrections, the gate, the preservation table (with the
    open Prompt 3 review findings classified) and the status.
  - The owner-facing comparison: `docs/discovery/GENESIS_LITE_V0_3_D5_RUNTIME_BOUNDARY_HANDOFF.md`.
  - A dated correction in the D5-A1b evidence README.
- **Evidence taxonomy.**
  - **MEASURED.** The `2e2a9d1b` run (`b3bc0b64…`, reverted; `git show b1fbefbf:docs/work/evidence/genesis_lite_v0_3_d5_a1b_deployment_2026_10_21/result.json`)
    recovered no selected message. In all 30 decoder reads under `container_evidence.cards[*].devices` and
    `device_trials`, each two-flag `found` list is all false. Its detector did not exercise BLOCKER 1, so it neither proves nor disproves it
    (NOT_MEASURED_BY_CURRENT_DETECTOR).
  - **STATIC_REVIEW.** BLOCKER 1, classified BLOCKER; its scope is all six writable device nodes.
  - **FORMAL_MACHINE_CONFIRMATION.** The implementer's confirmation on the formal launcher was ad hoc and unpinned.
    No artifact was kept, and it is not a selected-message measurement.
- **Dated corrections (2026-10-21) of the Prompt 3 and subset entries above.** Their wording is kept as written.
  - "This is a cross-card state channel" is a STATIC_REVIEW finding with a FORMAL_MACHINE_CONFIRMATION. No channel
    was measured, and recovery of a selected message was not demonstrated.
  - "all six devices were ADMITTED wrongly" and "The D5 PASS is therefore invalid" mean that the admissions and the
    PASS do not stand, because their detector did not exercise BLOCKER 1. They do not mean that the detector measured
    a channel.
  - "and the channel remains", said twice under "Failed approaches", records the implementer's ad-hoc re-checks of
    the finding (FORMAL_MACHINE_CONFIRMATION). Those re-checks are not detector results, and no channel was measured.
  - "how, or whether, the six device nodes can be made non-state-carrying" presumes state that was not measured.
    Read it as: closing BLOCKER 1's scope with MEASURED evidence.
  - In the subset entry, "BLOCKER 1 was confirmed on the formal launcher ... for all six nodes" is a
    FORMAL_MACHINE_CONFIRMATION, and "cannot be met" means cannot be shown met.
  - Device identity alone proves no channel.
- **Gate (`readiness.py`).** `BOUNDARY_FINDINGS` keys BLOCKER 1 by finding and scope. An earlier draft in this task
  keyed it by runtime name, so renaming `isolation.DEPLOYMENT` would have cleared it (review MAJOR-1). That failed
  approach is not to be repeated.
  - The finding is open for every runtime until the pinned D5 evidence holds `boundary_findings["BLOCKER 1"]`. That
    section must say MEASURED, name a declared detector (none is declared) and give a closing result for each of the
    six nodes.
  - `runtime_boundary_problems()` also requires the evidence to name the selected runtime. A missing or malformed
    field blocks and never raises.
  - D5 rows report NOT_PROVEN with `D5_RUNTIME_BOUNDARY_NOT_PROVEN`. The D7 evidence row stays a blocker while the D5
    evidence leaves the finding open, or while the pilot names another runtime.
  - `check()` adds `d5_runtime_boundary`, which reflects the D5 evidence only.
  - Two new tests are required tests of their rows (D5 ×3, D7 evidence):
    - `test_d5_the_selected_runtime_with_an_open_boundary_finding_never_verifies`;
    - `test_d7_a_pilot_on_a_superseded_or_blocked_runtime_is_a_blocker`.
  - Two existing tests now include the boundary:
    - `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code`;
    - `test_d7_timing_pilot_evidence_is_pinned_and_a_stale_pilot_is_a_blocker`.
  - `test_d5_the_selected_message_trials_decide_the_cross_card_channel` gets a dated docstring correction. Its name
    is pinned.
  - The preregistration "readiness P-1 / P-2" text records the decision. The preregistration was regenerated
    (DRAFT, sha256 `992bf0eb…`).
- **Gate output (first draft only).** The direct call
  `python -c "from benchmarks.genesis_lite.v0_3 import readiness as r; o = r.check(); print(o['status'], o['d5_runtime_boundary'])"`
  ran on the first draft of the gate. It reported BLOCKED_TECHNICAL with reason `D5_RUNTIME_BOUNDARY_NOT_PROVEN`. It
  is a function call without test evidence, not the readiness CLI. The current gate's direct output: **NOT RUN**.
- **Tests (Windows, narrow, uncommitted tree on `d8e0eb29`, after the review fixes).**
  `PYTHONPATH="D:/forge-genesis-clean/src;D:/forge-genesis-clean" python -m pytest -p no:cacheprovider
  --basetemp=D:/forge-genesis-tmp/bt7 -q -rA <15 node ids>` gave 64 passed and 1 failed (rerun after the round-2 fixes).
  - **Node ids.** They cover:
    - the 2 new tests and the 2 changed status tests;
    - `test_d5_a_missing_proc_or_sys_row_is_incomplete_evidence_and_never_passes`;
    - `test_d5_malformed_or_unknown_host_device_values_block`;
    - `test_d5_a_device_with_a_wrong_identity_is_blocked`;
    - `test_d5_unknown_device_paths_and_aliases_block`;
    - `test_d5_the_host_procfs_control_cannot_pass_on_one_signal`;
    - `test_d5_the_selected_message_trials_decide_the_cross_card_channel`;
    - `test_o1_lift_decision_passes_the_keyed_stream_to_the_monte_carlo_p` (no p-difference assertion; checked by
      reading the test);
    - `test_v0_3_is_a_draft_identity_that_amends_v0_2`;
    - `test_readiness_every_d5_row_names_its_tests_and_needs_them_passed`;
    - `test_readiness_required_tests_match_the_test_files`;
    - `test_readiness_with_the_escrow_half_has_no_technical_row_left`.
  - **The failure.** `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code` fails at its schema
    assertion (the pinned evidence is `/3`, not `/4`). This is the known red since `3d62b494`, so that test's new
    lines are not reached on this tree.
- **Review round 1 (read-only agent, static).** 0 BLOCKER, 1 MAJOR, 7 MINOR, 8 NOTE.
  - **Fixed.**
    - MAJOR-1: findings keyed by scope.
    - MINOR-1: the malformed runtime field.
    - MINOR-2: the corrections above.
    - MINOR-3 to MINOR-5: handoff family 4, the card-count label and the Podman reference point.
    - MINOR-6: the open review findings classified.
    - MINOR-7: the §7 correction cites 10.1 B and C.
    - NOTEs 3 to 8: the record path, the sources for C, the test docstring, the replay-factor assumption, the field
      scope and the wording alignment.
  - **Left as noted.**
    - NOTE-1: the edited D5 test is unreached while it is red.
    - NOTE-2: `status == BLOCKED` alone does not discriminate. The row-level assertions do.
- **Review round 2 (same agent, static).** 0 BLOCKER, 0 MAJOR, 3 MINOR, 7 NOTE. Every round-1 fix was confirmed.
  - **Fixed.**
    - MINOR-a: the gate checks the closure's declared type only. Declaring a detector must add a re-derivation test.
    - MINOR-b: the `found` count wording.
    - MINOR-c: the docstring says mechanism, not scope.
    - NOTE-2: the incomplete-closure cases were added to the test.
    - NOTE-3: the D7 own-closure case was added.
    - NOTE-5: the tuple assertions.
    - NOTE-6: the cross-pilot caveat and the unit.
    - NOTE-7: this heading.
  - **Left.**
    - NOTE-1: the round-1 NOTE-1 and NOTE-2 stay accepted.
    - NOTE-4: pre-existing crashes on a non-mapping top-level doc or `provenance`. The bytes are pinned, and the
      failure is a crash, so it is fail-closed.
- **Status.** D5 = NOT_PROVEN. N-1 = OPEN. CURRENT_ROOTLESS_PODMAN_RUNTIME = BLOCKED_BY_D5_DEVICE_BOUNDARY. D7 =
  REQUIRES_RERUN after a replacement runtime is selected.
- **NOT RUN.** The full `tests/genesis_lite`, the Linux suite, FAST, SCIENTIFIC, regression, the readiness CLI, D5,
  D7, OD-3, any freeze, certification, formal campaign or Budget × Noise.

## 2026-10-21 — BR-D5-RUNTIME-01: replacement runtime selection spike

- **Result: SELECT_RUNTIME_FOR_D5_IMPLEMENTATION, status RUNTIME_SELECTED_FOR_IMPLEMENTATION.** The selected family is
  3a: a rootful crun 1.14.1 container per card, run inside the formal WSL2 VM. The launcher builds each card's
  private device tmpfs: mknod'd null, zero and full only; random, urandom and tty absent. The card gets a user
  namespace, no capabilities, Podman's seccomp profile and a read-only rootfs from the pinned image.
  - Report: `docs/discovery/GENESIS_LITE_V0_3_D5_RUNTIME_SELECTION_SPIKE.md`.
  - Probe evidence is outside the repo in `D:\forge-d5-runtime-spike\` (`SHA256SUMS` sha256 `e92f0efa…`). It is
    synthetic cards only and unpinned: spike evidence, not D5 evidence.
- **MEASURED in the spike (executed this session on the formal machine).**
  - The closed rootless Podman runtime leaks a selected bit through `utimensat(UTIME_NOW)` on all six host nodes,
    24/24 trials.
  - A misconfigured 3a launcher that shares one device tmpfs leaks 24/24 (the detector has power).
  - The 3a candidate leaks nothing: the guess was 0 in all trials, ro and rw; random, urandom and tty are ENOENT.
  - Per-card overhead for 3a: median 0.011 s, p95 0.012 s, worst 0.024 s (n=1000, `/bin/true`).
  - Closed Podman: median 0.133 s, p95 0.155 s (n=200).
  - Bare nested-KVM VM floor: 0.028 s / 0.040 s (n=1000).
  - Cleanup failures and residue: 0 in 1,601 timed 3a cards.
- **Found while probing (carry into the implementation).**
  - crun's `maskedPaths` binds the HOST `/dev/null` over `/proc/kcore`, `/proc/keys`, `/proc/latency_stats` and
    `/proc/timer_list`. That makes them read-only aliases of a BLOCKER-1 node, and the closed Podman runtime has the
    same aliases.
  - systemd's shared `/` propagates the card's `/dev/shm` mount back to the host unless the card tmpfs is made
    private.
  - Sequential cards reuse identical `st_dev`/`st_ino`, so the device contract must not prove privacy by inode
    identity.
- **Rejected.**
  - Family 1 via Hyper-V: needs elevation, and the WSL launcher cannot drive it (interop disabled).
  - Family 4 (Blindfold): `unshare` leaves the host `/dev`.
  - Family 2 is the fallback if a root launcher is refused. It is not probed beyond the KVM floor, because it needs
    downloads.
- **Failed approach, do not repeat.** `wsl.exe -- bash -c '...$VAR...'` re-parses through the login shell: `$VAR`
  expanded empty and a root command wrote `/rootfs`, `/scripts` and `/kvm_floor` at the WSL root (removed). Feed
  scripts on stdin (`wsl.exe -u root -- bash -s < script.sh`). Automount is off, so `/mnt/d` is empty in WSL.
- **Status unchanged.** D5 = NOT_PROVEN, N-1 = OPEN, D7 = REQUIRES_RERUN, and BLOCKER 1 is open: no detector is
  declared and nothing is pinned.
- **NOT RUN.** D5, D7, the D5 contract and attack channels, `tests/genesis_lite`, FAST, SCIENTIFIC, regression, the
  readiness CLI, freeze, certification, formal runs and Budget × Noise. No implementation, push or install.

## 2026-10-21 — 3a launcher implementation: paused before any code change

- The owner approved family 3a with a declared root launch. Implementation stopped before any code change, because a
  safety classifier interrupted the work on the attack-suite and power-control part of the deployment verification.
  Those parts need the owner, or a narrower scope. The tree is unchanged apart from this entry.
- **Baseline test run (Windows, at `4c2bed58`):**
  `PYTHONPATH="D:/forge-genesis-clean/src;D:/forge-genesis-clean" python -m pytest tests/genesis_lite -q -n 4 -p no:cacheprovider --basetemp D:/forge-d5-impl/bt/base0 -rs`
  gave 2 failed, 478 passed, 4 skipped (Linux-only).
  - Failed: `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code` (the known red; schema /4
    against the pinned /3).
  - Failed: `test_d5_scientific_randomness_is_explicitly_seeded_and_the_screen_has_power`. Not investigated.
- **NOT RUN.** The Linux suite, FAST, SCIENTIFIC, regression, D5 and D7.

## 2026-10-21 — Prompt 5A (3a runtime abstraction): baseline classified, stopped again before any code change

- **Baseline rerun (Windows, at `c3947b9c`):**
  `PYTHONPATH="D:/forge-genesis-clean/src;D:/forge-genesis-clean" .venv/Scripts/python.exe -m pytest tests/genesis_lite -q -n 4 -p no:cacheprovider --basetemp D:/forge-d5-impl/bt/base1 -rs`
  gave 2 failed, 478 passed, 4 skipped (Linux-only). The failures are the same two as above.
- **`test_d5_scientific_randomness_is_explicitly_seeded_and_the_screen_has_power`: CURRENT_CODE_DEFECT.**
  - The screen reports `benchmarks/genesis_lite/v0_3/readiness.py:391: names an RNG device`, twice.
  - That line is `BOUNDARY_FINDINGS["BLOCKER 1"]["scope"]`. It spells `/dev/random` and `/dev/urandom` as literals.
    It was added in 839af190, and the 61150afd readiness file had no such literal.
  - `readiness.py` is not in `device_contract.DEVICE_PATH_FILES`. The screen is right and the test is right.
  - Suggested fix, not applied: take the scope from `device_contract.DEVICES` rather than adding readiness to
    `DEVICE_PATH_FILES`. It touches a preregistration-pinned file, so the DRAFT preregistration must be regenerated.
- **`test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code`:** STALE_EVIDENCE_FAILURE. It is the
  expected red until a family-3a D5 package is executed and pinned. Not touched.
- **Stopped.** A safety classifier interrupted the session while it was planning the 3a launcher, root-helper and
  evidence work. Following the prompt's rule, nothing blocked was retried or rephrased. No code, test or pin changed;
  this entry is the only edit.
- **NOT RUN.** Every 3a contract, device-contract V2, evidence-schema, pre-admission and readiness test (none exists),
  the evaluator/escrow agreement, the Linux suite, FAST, SCIENTIFIC, regression, D5, D7, OD-3 and formal runs.

## 2026-10-21 — Randomness-screen defect fixed (`93785e93`); family 3a still not implemented

- **Fix.** The six-device scope in `readiness.BOUNDARY_FINDINGS["BLOCKER 1"]` is now `tuple(device_contract.DEVICES)`.
  `DEVICE_PATH_FILES` is unchanged, and the selected runtime is unchanged.
- **New regression test.** `test_d5_the_boundary_scope_is_the_device_contract_and_passes_the_randomness_screen`:
  - the scope equals `device_contract.DEVICES`;
  - readiness is not in `DEVICE_PATH_FILES`;
  - the screen finds nothing in readiness;
  - planting the literal scope back into a copy of readiness gives exactly the two original findings.

  The test is added to the two D5 rows of `REQUIRED_TESTS` beside the screen test.
- **DRAFT v0.3 preregistration regenerated** (readiness.py is identity-pinned): `992bf0eb…` → `e2ac2f7b…`. Still DRAFT.
  Nothing else in the tree named the old digest.
- **Tests (Windows, this session):**
  - The targeted run (`-k` on the screen test, the new test and the two boundary-finding tests) gave 4 passed.
  - `PYTHONPATH="D:/forge-genesis-clean/src;D:/forge-genesis-clean" .venv/Scripts/python.exe -m pytest tests/genesis_lite -q -n 4 -p no:cacheprovider --basetemp D:/forge-d5-impl/bt/fix3 -rf`
    gave 1 failed, 480 passed, 4 skipped (Linux-only).
  - The one failure is `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code`, the stale D5
    evidence. It is preserved unchanged.
- **NOT RUN.** The Linux suite, FAST, SCIENTIFIC, regression, the readiness CLI, D5, D7, OD-3 and formal runs. Family 3a
  remains unimplemented: D5 NOT_PROVEN, N-1 OPEN, D7 REQUIRES_RERUN.

## 2026-10-21 - Prompt 5A section 2: family-3a scaffold; BLOCKED_WITH_PRECISE_EVIDENCE

- **Result: BLOCKED_WITH_PRECISE_EVIDENCE.** The scaffold is in `benchmarks/genesis_lite/v0_3/family3a.py`, with tests in
  `tests/genesis_lite/test_genesis_lite_v0_3_family3a.py`. Execution readiness is blocked by two reasons, and nothing else:
  - `ROOT_HELPER_NOT_IMPLEMENTED`: the only root helper in the tree is `UnimplementedRootHelper`. Every `identity()` and
    `start()` call refuses, and nothing falls back to another runtime. The low-level helper (the spike section 6.1 steps,
    run as root through `wsl.exe -u root`) was not written. It must be a separately reviewed program, pinned by
    `helper_sha256`.
  - `CONFIG_UNPINNED`: `runtime_sha256` (the crun binary), `rootfs_tree_sha256`, `seccomp_sha256` and `helper_sha256`
    are not measured. They can only be measured as root on the formal machine. The spike's rootfs export (`7d1ab3c8...`)
    is one instance, not a pin.
- **What exists (synthetic tests only, not runtime proof).**
  - `RuntimeConfig`: typed, frozen and without defaults. `UNPINNED` blocks and never matches. The policy fields (device
    sets, cgroup allowlist, capabilities, propagation, ro rootfs, root launch) cannot be widened.
  - `CardSpec` and `Family3aLauncher`: a card names `proposer_host` or `container_probe`, never a command line. The args
    are absolute paths only, and the environment is `PYTHONDONTWRITEBYTECODE=1` only.
  - The `RootHelper` protocol: the helper takes only a `helper_request` (schema, mode, config digest, card), which has no
    argv, command, shell or script field. The power-control mode runs the probe only. A result without a complete
    cleanup record, or with residue, is refused.
  - Device Contract v2 (`stateless_device/2`) and evidence schema `family3a_evidence/1`, with a validator
    (`validate_evidence`) that re-derives every node from raw records and never raises:
    - null, zero and full are PRIVATE_TO_CARD only when each node is chr, has its exact rdev and mode 0666, sits on the
      card's own `/dev` tmpfs and has ctime and mtime inside the card's window;
    - cards are separated by at least 10 ms;
    - the timestamp detector (`utimensat_timestamp_selected_bit/1`) recovers nothing in at least 12 trials per bit, and
      the shared-tmpfs power control recovers every bit in at least 4 trials per bit;
    - the other three nodes are ABSENT only when they are missing from `/dev` and give ENOENT;
    - no devtmpfs row, no row from the host devtmpfs, no shared propagation and no walked device node anywhere;
    - privacy never uses st_dev/st_ino equality (the baseline reuses one of each across every card);
    - a stored verdict field is `STORED_VERDICT_NOT_EVIDENCE`, and the output's `boundary_findings["BLOCKER 1"]` has
      readiness's `_closed` shape.
  - `pre_admission`: config, then helper, then identity, then evidence, then validation. It stops at the first failure
    and takes no root or registry. `execution_readiness` and the read-only CLI report
    `READY_FOR_FAMILY_3A_EXECUTION` or `BLOCKED_WITH_PRECISE_EVIDENCE`.
- **Deliberately not done.**
  - No pinned file changed: the module is not in `V0_3_FILES`, `DEVICE_PATH_FILES` or `formal.deployment_problems`, and
    no detector is declared in `readiness.BOUNDARY_FINDINGS`. Wiring it in is the next step, and that step regenerates the
    DRAFT preregistration.
  - The preregistration is unchanged (DRAFT, sha256 `e2ac2f7b...`).
  - The stale D5 evidence test is untouched.
- **Tests (Windows, this session):**
  - `PYTHONPATH="D:/forge-genesis-clean/src;D:/forge-genesis-clean" .venv/Scripts/python.exe -m pytest tests/genesis_lite/test_genesis_lite_v0_3_family3a.py -q -p no:cacheprovider --basetemp D:/forge-d5-impl/bt/f3a5`
    first failed at collection (ImportError, the failing-first state), then gave 15 passed.
  - A targeted apply/revert mutation script (scratchpad, not committed) applied 10 guard mutants. Two survived the
    first round (the host-devtmpfs device id and the coarse-clock gap) and got a dedicated case each. After that, all 10
    were killed and the source was restored byte-identical.
  - `PYTHONPATH=... python -m pytest tests/genesis_lite -q -n 4 -p no:cacheprovider --basetemp D:/forge-d5-impl/bt/f3a-full -rfs`
    gave 1 failed, 495 passed, 4 skipped (Linux-only). The failure is
    `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code`, the preserved stale evidence red.
  - `python -m benchmarks.genesis_lite.v0_3.family3a` returned exit 1 with `BLOCKED_WITH_PRECISE_EVIDENCE`
    `['CONFIG_UNPINNED', 'ROOT_HELPER_NOT_IMPLEMENTED']`; the identity stage was NOT_REACHED.
- **Status unchanged.** D5 = NOT_PROVEN, N-1 = OPEN, D7 = REQUIRES_RERUN, BLOCKER 1 open.
- **NOT RUN.** The Linux suite, FAST, SCIENTIFIC, regression, the readiness CLI, D5, D7, any card launch, any root
  command, freeze, certification, formal runs and Budget x Noise. Nothing was pushed.

## 2026-10-21 - Family-3a root helper written, installed and measured; READY_FOR_FAMILY_3A_EXECUTION

- **Result: READY_FOR_FAMILY_3A_EXECUTION.** `python -m benchmarks.genesis_lite.v0_3.family3a` measured the identity
  through the real helper: config PASS, helper PASS, identity PASS, exit 0. Readiness to execute is not D5 evidence:
  D5 = NOT_PROVEN, N-1 = OPEN, D7 = REQUIRES_RERUN, BLOCKER 1 open.
- **The helper.** `benchmarks/genesis_lite/v0_3/family3a_helper.py` is one self-contained standard-library file, pinned
  by its sha256.
  - It runs as root only: a non-root launch was measured as `REFUSED`, exit 2.
  - Its operations are fixed: `identity`, `install-rootfs`, `configure-kept`, `run`, `residue` and `control-teardown`.
    None takes a command.
  - It runs only `/usr/bin/crun`, `/usr/bin/mount` and `/usr/bin/umount`, never a shell. An AST test pins this.
  - `run` takes one hex-encoded request and re-checks it with its own strict validator. A corpus test shows that this
    validator refuses exactly what `family3a.helper_request_problems` refuses.
  - One card follows the spike's 6.1 steps:
    - a private tmpfs with mknod'd null, zero and full, an empty `shm` and an empty mask file;
    - `/dev` bound ro, nosuid, noexec (rw only in the shared-tmpfs power control);
    - /proc files masked from the tmpfs, never by crun's `maskedPaths`;
    - rprivate propagation, a userns map to 100000, empty caps and no_new_privs;
    - Podman's seccomp profile in OCI form, a device cgroup allowing only 1:3, 1:5 and 1:7, and a read-only rootfs;
    - the kept tree and venv bound ro at `/forge/tree` and `/forge/venv`.

    Cleanup always runs, in a `finally`, and its residue counts are reported.
  - The client (`WslRootHelper`) calls `wsl.exe -d Ubuntu-24.04 -u root --exec /usr/bin/python3 -I
    /var/lib/forge-f3a/helper.py <op>`. `--exec` skips the login shell, which fixes the `$VAR` re-parse failure recorded
    earlier.
  - Card arguments must now lie under `/forge/tree` or `/forge/venv` (`family3a.KEPT_ROOTS`).
- **Operator actions on the formal machine (this session, the declared root launch).**
  - The helper was installed at `/var/lib/forge-f3a/helper.py` (root:root 0644) with `--exec install`, `dd` and
    `chmod`. Its installed sha256 equals the repository file: `661d765c...`.
  - As dev_kaeem, `podman export` of `localhost/forge-card@sha256:89847920...` gave `/home/dev_kaeem/f3a-rootfs.tar`
    (113,242,112 bytes, sha256 `7d1ab3c8...`, the spike's instance byte for byte). It is left in place as the install
    source.
  - As root, `helper.py install-rootfs` extracted it to `/var/lib/forge-f3a/rootfs`, then a second time from scratch.
  - `configure-kept` was NOT run, so no kept tree is configured and `run` refuses until one is.
- **The four pins (MEASURED, `family3a.PINNED_CONFIG`).** They were measured by `identity` twice, and again after the
  re-extraction, with identical results:
  - `runtime_sha256 = bd8ad7e7...` (`/usr/bin/crun` 1.14.1; also equals `sha256sum /usr/bin/crun`);
  - `rootfs_tree_sha256 = d1b07cbc...` (`tree_digest`: path, mode, owner and content; no times or inodes);
  - `seccomp_sha256 = 0c424aa4...` (the canonical JSON of the OCI-form profile for kernel 6.6.87.2);
  - `helper_sha256 = 661d765c...`. A test pins it to the helper file, so a helper edit fails until it is re-measured
    and re-pinned.
- **Tests (Windows, this session).**
  - `PYTHONPATH="D:/forge-genesis-clean/src;D:/forge-genesis-clean" .venv/Scripts/python.exe -m pytest tests/genesis_lite/test_genesis_lite_v0_3_family3a.py -q -p no:cacheprovider --basetemp D:/forge-d5-impl/bt/f3b2`
    gave 22 passed.
  - Mutation, helper: a targeted apply/revert script applied 10 mutants. The first round was invalid twice, and those
    results are not counted:
    - a path typo collected no tests;
    - every mutant was killed only by the helper-digest pin test.

    With the pin test deselected, 9 of 10 were killed. The tree digest's mode bits survived and got a chmod case; after
    that, 10 of 10 were killed. The source was restored byte-identical.
  - Mutation, client: the earlier 10 mutants of `family3a.py` were all still killed.
  - `PYTHONPATH=... python -m pytest tests/genesis_lite -q -n 4 -p no:cacheprovider --basetemp D:/forge-d5-impl/bt/f3b-full -rfs`
    gave 1 failed, 502 passed, 4 skipped (Linux-only). The failure is the preserved stale-evidence
    `test_d5_deployment_evidence_is_pinned_rederived_and_measured_this_code`.
- **Not exercised.** The helper's `run`, `residue` and `control-teardown` operations have never run on the formal
  machine. No card was launched, so the 6.1 steps are reviewed and unit-tested but not executed. That is the next step,
  after `configure-kept` with a WSL-native tree at this commit.
- **Unchanged.** The DRAFT preregistration (`e2ac2f7b...`), `V0_3_FILES`, `DEVICE_PATH_FILES`, `readiness.py`,
  `formal.py` and the stale D5 test.
- **NOT RUN.** D5, D7, any card, the Linux suite, FAST, SCIENTIFIC, regression, the readiness CLI of `readiness.py`,
  freeze, certification, formal runs and Budget x Noise. Nothing was pushed.
