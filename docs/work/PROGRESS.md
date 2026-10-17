# Forge Work Progress

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

## Assurance environment recovery — 2026-10-13, environment only

No production, certificate, branch or scientific change. WSL (2.6.3) had been unresponsive
(only `wsl --version` answered; WMI also timing out); after an out-of-session service recovery
`wsl --status` / `wsl -l -v` answer (Ubuntu, forge-runner; both v2). `D:\WSL` (the .wslconfig
swapFile parent and forge-runner BasePath) was missing; recreated empty so the VM can create
swap. forge-runner's ext4.vhdx was not found on C:/D:/K: and is NOT recovered.

Linux clone: `/home/dev_kaeem/forge-hostile-remediation` (git clone --no-local of this branch),
HEAD 4b0ad013fd51119fe36346e613805edd477c5dbd, fix/hostile-review-p0-p1, porcelain empty before and after.
Interpreters: python3.11 3.11.17 (~/.local/bin -> forge-assurance pythons), python3.12 3.12.3 (/usr/bin).

Commands executed (WSL Ubuntu 24.04.3, TMPDIR outside repo):
- `python3.12 -m tools.certification.local_assurance prepare --python311 $(command -v python3.11) --python312 $(command -v python3.12)`: exit 0, `LOCAL_ASSURANCE_PREPARE: PASS`, ngspice-42 found; envs `.forge/venvs/3.11`, `.forge/venvs/3.12`.
- `.forge/venvs/3.12/bin/python tools/forge_check.py --help`: exit 0.
- `.forge/venvs/3.12/bin/python -m pytest --collect-only -q -p no:cacheprovider`: exit 0, 10768 tests collected in 16.01s.
- `.forge/venvs/3.12/bin/python -m tools.certification.core_certificate --verify`: exit 1, FAILED; certified 39d43456cab9 vs HEAD 4b0ad013; drift areas certification_control, execution_trust, harness, inference_admission, runtime_dependencies (same as round 1). Verify only; no certificate built.
- `.forge/venvs/3.12/bin/python tools/forge_check.py --regression`: exit 0, 256 passed in 7.13s.

FAST/SCIENTIFIC/FULL on 3.11/3.12, mutations, local_assurance run, recertification: NOT RUN.
