# Forge Work Progress

This file is persistent engineering memory for long-running AI-assisted work.
Keep it concise and factual. Do not use it as a release note or marketing log.

## Current branch / PR

- Branch: `feat/big-13-flagship-demonstrations` (base `6054ac44`, the BIG 12 HEAD); previously `feat/big-12-end-to-end-runtime`, `feat/big-10-multitimescale`
- PR: none opened; verify GitHub before making a current PR claim.
- Base: `main`
- Strategic contract: `docs/project/FORGE_MASTER_PLAN.md`
- Current execution authority: `docs/work/ACTIVE_PLAN.md`

## 2026-09-26 BIG 13 — Flagship Engineering Demonstrations (BUILD phase; read this first)

Branch `feat/big-13-flagship-demonstrations`, base `6054ac44811cec26e074ad5be275396cccfd3b13` (the BIG 12 HEAD), worktree `D:/forge-b13`. Reports: `docs/flagships/`
(index `README.md`, four per-flagship reports, `runs/` = the complete verifiable bundles the reports were generated from). Design note: `docs/architecture/engineering.md`.
BIG 14 NOT STARTED.

### What exists
- `src/engcore/engineering/` (non-Core, registered in `tests/test_core_api_layering.py`): `reference.py` (reference records with kind / provenance / applicability envelope /
  comparable quantities; `PredeclaredCriterion`; `ReferenceComparison`, DERIVED from reference + criterion + stated conditions + value - nothing about its outcome is stored - with the tolerance read as a SPREAD), `ladder.py` (7-level verification
  ladder = report vocabulary; every `EvidenceLink` carries the record it names and its digest is re-derived), `summary.py` (`EngineeringSummary`, status only from `trust_handoff`),
  `bundle.py` (`write_bundle` / `verify_bundle`), `fieldio.py` (VTU), `report.py` (17 required sections, statement labels).
- `flagships/forge_flagships/`: `battery_cooling.py` (A), `thermo_mechanical.py` (B), `cavity_cfd.py` (C), `chem_thermal.py` (D), `reports.py`, `__main__.py`, `data/` (Ghia Re=100 excerpt,
  NIST WebBook excerpt, `predeclared_criteria.json`). Every flagship is one BIG 12 `SystemRunRequest` run by the generic `SystemExecutor` (`test_flagship_portfolio.py` checks from the source that no
  flagship defines its own runtime).
- BIG 12 generalisations (each tested in `tests/test_system_runtime_big13_additions.py`): `NodeCall.execution_identity`; `MultiphysicsAuthority(extractors=, artifacts=)`.
- Provider adapter additions (additive): CalculiX and Code_Aster `execute_thermoelastic` (+ deck/mesh generators, element-stress parsers), Cantera enthalpy / element-mass-fraction / thermo-range scalars,
  PyBaMM coupling `capacity_fade` + dense series logging, FEniCSx `descriptor.py` (it was undiscoverable), `pde.cases.ThermoelasticPlaneStressProblem`, `pde.postprocess` stress recovery,
  `tools/wsl_env.sh`.

### Results (from the runs behind `docs/flagships/runs/`; every scientific status is `insufficient_evidence`)
- A battery + cooling + lifecycle (PyBaMM 26.8, TESPy 0.11.2; BIG 9 coupling, BIG 10 multi-timescale, 56 represented days from 4 resolved): fresh peak cell temperature 301.28 K, day-56 aged 304.06 K;
  capacity fade 0.0518 (limit 0.10); end-of-discharge voltage shift caused by degradation -0.0337 V vs +0.0054 V from environment drift; the `hot` case violates temperature and fade constraints (fade 0.112).
- B thermo-mechanical plate (FEniCSx 0.11, CalculiX 2.23, Code_Aster 18.1.7 on one mesh and one shared FEniCSx temperature field): hot end 351.05 K, max displacement 3.654e-5 m (three codes agree to 0.023 %),
  mid-plate axial stress -55.21 MPa = the bar-theory value, peak von Mises 59.8-60.0 MPa (mesh-dependent, order 0.7, NOT claimed converged).
- C lid-driven cavity Re = 100 (OpenFOAM v2412, SU2 8.5.0): both codes within 0.02 of lid speed of Ghia et al. 1982 (numerical benchmark) at 80x80 (OpenFOAM 0.0090, SU2 0.0112) - and the two codes DISAGREE with each
  other by 24-26 % of lid speed in the cell layer next to the lid at every mesh (BIG 11 criterion 3 %, not loosened); part of that is probably the declared corner-mean mapping (untested).
- D methane/air + water loop (Cantera 3.2.0 / GRI-Mech 3.0, TESPy 0.11.2): adiabatic flame temperature 2225.5 K, heat to remove 26.48 kW, cooling water +21.1 K; Hess's-law LHV consistency 0.229 kJ/mol against 0.5.

### Criteria NOT met as written (kept visible; tolerances were not changed)
1. A window-refinement study: tolerances met, but successive differences GROW as the coupling window shrinks (0.0032 K then 0.0080 K; 1.2e-6 V then 1.3e-5 V; 2.2e-4 W then 2.9e-3 W); the monotone requirement was added after
   the first review together with the third level (labelled in the pre-registration). L4 not reached; cause not investigated.
2. B convergence order >= 0.9 for the mid-plate stress: the quantity is at solver noise (1e-9 relative), so no order exists; a labelled post hoc noise-aware reading is met and does not replace the outcome.
3. C whole-field OpenFOAM vs SU2 (3 % of lid speed) NOT MET at 20/40/80; the lower-half readings are post hoc only.
4. C benchmark error monotone under refinement NOT MET for OpenFOAM (0.0127, 0.0027, 0.0044): it folds in the benchmark's own truncation error.
5. C SU2 mid-plane flux 6.2e-3 against 1e-3 NOT MET (cause not investigated); the constraint now reports `b_flux_su2` VIOLATED beside `b_flux_openfoam` SATISFIED.
6. D discrete ignition-time criterion (1 %): the sampling spacing is 1.4-7.2 % of the ignition delay, so it cannot be met by a converged solution; a post hoc parabola-refined reading is labelled beside it.
- Changed AFTER seeing results, each labelled in `predeclared_criteria.json` with the tolerance unchanged: D heating value evaluated at 300 K (298.15 K is below the mechanism's stored thermo range; the offset is bounded
  at 0.018 kJ/mol); B equilibrium-diagnostic force floor (a load-blind solve gave a zero spread that passed); C flux constraint bound for both codes on an unsigned residual. Git cannot show that the constants preceded the
  first execution (the first commit was made after it); that rests on this record.

### Failed approaches / gotchas (do not repeat)
- Long bash heredocs / `'''` write nothing or mangle; use the Write tool for patch scripts. The bash tool halves backslashes in heredocs.
- Nested same-quote f-strings parse on Windows Python 3.14 and fail on the WSL 3.11 envs; check syntax with `python -c ast.parse` INSIDE each env (`D:/ftmp/syn311.py`).
- Slicing a source file between two `str.index` results is only safe if the second index is AFTER the first: an early `allowed = {` match duplicated `write_bundle` in `bundle.py` (caught by the tests). Assert `i < j`.
- CalculiX / Code_Aster need `FORCE_PROVIDER_ENVS`; FEniCSx JIT needs the env `bin` on PATH (`tools/wsl_env.sh`); Code_Aster stress output must use logical unit 30 (unit 9 is redefined -> job error).
- BIG 12 Gate G test had assumed CalculiX unavailable; it now `monkeypatch.delenv("FORGE_PROVIDER_ENVS")`.
- A request with no environment needs `environment_absent_reason`; two executable components need a declared `ComponentConnection` (an energy-balance interface for reactor -> jacket) or the topology is refused.
- A blanket `str.replace` of a prose word ("predeclared") also rewrote a FILE NAME in the README (`predeclared_criteria.json`); replace phrases, then grep for the identifier. Bundles are hashed: regenerate them after ANY change to what a summary renders.
- The whole-result digest includes provider wall time, so two runs of one flagship have different result digests; request and plan digests and `compare_runs` are the replay identity.

### Scientific review (read-only `forge-scientific-reviewer`), dispositions
Round 1 (static, CHANGES REQUIRED; 3 HIGH, 15 MEDIUM, many LOW):
- H1 refused node's side-store table reached L3 and the bundle -> FIXED (L3 gated on a SUCCEEDED receipt; `committed_artifacts`; `write_bundle` refuses unreferenced files; tests). H2 ladder guards only for L5-7 -> FIXED for every level (class, outcome, post-hoc)
  and, after round 2, links carry their records. H3 L1 unconditional -> FIXED (`contract_integrity_entry(report, result)`; refusals named).
- M1 criteria as prose -> `predeclared_criteria.json` pinned by `test_flagship_portfolio.py`. M2 displacement tolerance scale -> disclosed (6.2 % of the peak; observed 0.023 %). M3/M4 static prose and stale report -> regenerated from runs; more generated in round 2.
  M5 README/PROGRESS -> this entry, `runs/`, tests that tie each report to its bundle. M6 uncertainty guards -> discrepancy must be UNKNOWN / NOT QUANTIFIED, unknown list required when outputs are UNKNOWN. M7 comparison guards -> non-negative, not_applicable judges nothing,
  round 2: spread conversion, quantity binding; round 3: the comparison is derived, not issued. M8 envelopes -> stated as flagship-authored. M9 cross-request evidence -> gated on a succeeded run, notes name it. M10 identity -> every case parameter is in the request (tested);
  `verify_bundle` extended in round 2. M11 tautological checks -> disclosed in level notes and README. M12 LHV range check -> `thermo_range` declared on the node (evaluated at 300 K). M13 labelling -> `reference_level_reached`, data-consistency class. M14 -> A L4 relabelled, C benchmark-relative criterion disclosed. M15 -> tests added.
Round 2 (focused re-review of the round-1 batch; CHANGES REQUIRED: 2 HIGH, 9 MEDIUM, LOW):
- H-A D level 3 reached on partial evidence -> FIXED (`level3_entry`: every declared check must have run and been met; note built from links; tests incl. degraded cases).
- H-B `verify_bundle` did not close a fully regenerated manifest -> FIXED (request/result/plan re-derived, verdict re-derived by `trust_handoff`, ladder rebuilt with every guard, evidence-record digests re-derived,
  every comparison must name a bundled reference, `summary.txt` bound by hash; a missing file is a refusal; tests regenerate the WHOLE manifest). The manifest stays unkeyed: an adversary who rebuilds every file passes; authenticity needs the `bundle_digest` recorded elsewhere.
- M1 unresolvable links -> FIXED (records inline; `build_summary` cross-checks comparisons and references). M2 offset-unit hazard -> FIXED (`magnitude_as_spread_in`). M3 quantity binding -> FIXED (`comparable_quantities`). M4 zero spread from a load-blind solve -> FIXED (force floor).
  M5 A L2/L3 interface consistency -> NOT changed in code; disclosed in notes, report and README (no independent cell-side conservation check exists). M6 static prose -> the flagged sentences are now generated; some remain typed (below).
  M7 cross-request evidence not shipped -> partly: the study / limit records are inline in `summary.json`; their provider bindings are NOT compared with the main request. M8 cavity constraint signed and cherry-picked -> FIXED. M9 PROGRESS/README/timestamp claim -> FIXED / re-worded.
- LOW fixed: duplicate ladder level refused, `inf` flux no longer crashes, 1e30 sentinel removed, fieldio / report legend wording, README provider order, NASA envelope-authorship wording. LOW not fixed: `UncertaintyStatement` is a substring guard; `report.py` label check is per section not per claim;
  `[CORROBORATION]` label on sections that say it is not reached; D/Ghia envelopes are flagship-authored (now stated); NASA reference is bundled in refused runs though never compared.
Round 3 (focused re-review of the round-2 batch; CHANGES REQUIRED: 1 HIGH, 5 MEDIUM, LOW):
- H1 a level promotion in `summary.json` still verified (the digests, the text and the manifest were refreshed consistently) -> FIXED for everything that can be re-derived: an evidence link's digest now covers kind, classification and outcome;
  `ReferenceComparison` has no settable outcome / applicability / kind (all derived from reference + criterion + stated conditions + value) and `verify_bundle` REBUILDS every comparison from its bundled reference; level 1 is re-derived from the
  result's own preflight; key outputs / execution / providers are checked against the result; `summary.txt` is re-rendered from `summary.json`; every comparison must be cited by the ladder; levels 5-7 need a link OF the matching kind. NOT re-derivable
  (documented in `bundle.py`, `docs/architecture/engineering.md`, the README): levels 2-4 evidence that is not a comparison and the constraint / conservation lines are recorded judgments; the manifest is unkeyed; a reference no comparison cites is bound only by
  the manifest. Tests regenerate the WHOLE manifest, refresh the text and every digest, and still expect refusal (status, text, request, plan, key output, level 1, provider list, a promoted comparison level, a re-kinded reference).
- M1 summary text only hash-bound -> FIXED (re-rendered). M2 L6/L7 gate was a string -> FIXED (kind gate). M3 issuer token bypass via `dataclasses.replace` -> FIXED (nothing forgeable is stored; conditions are recorded and re-derived).
- M4 B builders dropped failing evidence / level 5 raised -> FIXED (`level2_entry` is a pure builder with provider-free tests; a failed exact-limit request is recorded as a not_met link; level 5 records an unmet stress comparison as ATTEMPTED_NOT_REACHED).
- M5 docs exceeded tests -> the `battery_hot` bundle is now verified by a test; "fixed before the first run" replaced by "pre-registered" (defined in the README and engineering.md: listed in `predeclared_criteria.json` and pinned by a test; git cannot show it preceded the first run);
  the Ghia "not checked against the printed paper" caveat and the flagship-authored envelopes are stated inside the shipped reference records.
- LOW fixed: duplicate-level guard reachable (`VerificationLadder(tuple(entries))`), D/B level-2 `closed` truthiness, dead filter in `cavity_cfd`, static prose derived (C cross-provider text, A per-case statuses, D section-10 label, B level-5 note and benchmark applicability, D applicability wording,
  A level-4 literals), `b_flux_su2` VIOLATED asserted by the cavity suite. LOW not fixed: `comparable_quantities` is a name tag (units are not compared with the tolerance unit); the conditions handed to `compare_to_reference` are literals retyped in the flagship
  (the bar-theory and Hess envelopes end exactly at the case value, disclosed in their records); the exact-limit / mesh-study / window-study requests are not shipped (only their records, inside the summary); a NaN flux raises (fail-closed).
Round 4 (focused re-review of the round-3 batch; CHANGES REQUIRED: 1 HIGH, 4 MEDIUM, LOW):
- H-1 level 5 (provider comparisons) neither re-derived nor bound to the run -> FIXED (`check_provider_comparison`: two different providers, executions the result recorded, post-hoc flag matches the classification, a purely absolute tolerance's
  outcome follows from its maximum difference, a relative tolerance is refused; applied in `build_summary` and `verify_bundle`; a test promotes level 5 in a consistently rewritten bundle and expects refusal).
- M-1 comparison INPUTS (difference, conditions, tolerance, `compared_identity`) recorded, not derived -> a documented limit (`bundle.py`, `engineering.md`); not fixable generically. M-2 uncertainty and trace not re-run -> FIXED (guards re-run, an emptied UNKNOWN list refused,
  trace re-derived from the result; `trace_observable` is stored). M-3 envelope-authorship claim false for 4 of 7 records -> FIXED (stated in each record's `extraction`). M-4 C level 5 all-or-nothing -> FIXED (`level5_entry`: a missing level is a not_met link; provider-free tests).
- LOW fixed: B level 4 crash on a failed mesh level (`level4_entry`, tested); D level 2 dropped readings; `verify_bundle` raises `BundleRefused` for every failure (malformed result / request included); level 1 names waived applicability; the summary text covers notes and material provenance;
  D level-2 note and benchmark applicability are conditional; the B report's noise reason is computed from the failing quantities; the cavity key-output label and waiver wording; stale docstrings; "predeclared" prose -> "pre-registered". Provider-backed tests for a failed exact-limit request and an unmet stress comparison.
- LOW not fixed: conditions retyped as literals in the flagships (Hess 300 K, B 40 K, C aspect ratio); `plan.json` is compared with the result's own plan, not recompiled from the request; the `battery_hot` column is bound to no report identity; the exact-limit / mesh-study / window-study requests are not shipped.
- Round 5: NOT RUN. **The round-4 fix batch was NOT re-reviewed**; it is covered by the tests listed below only. Four review rounds each found a lower-severity residual in the bundle-authenticity area, whose real limit (an unkeyed manifest) is documented.

### Verification actually executed (this session; TMPDIR=D:/ftmp, `--basetemp=D:/fbt`, venv python on Windows, WSL conda envs for providers)
Windows (no provider), `TMPDIR=D:/ftmp`, main-checkout venv python, `PYTHONPATH="D:/forge-b13/src;D:/forge-b13;D:/forge-b13/flagships;<providers/*>"`, `--import-mode=importlib -p no:cacheprovider --basetemp=D:/fbt`, final tree (the commit that carries this entry):
- `pytest tests/test_system_runtime_contracts.py tests/test_system_runtime_executor.py tests/test_system_runtime_checkpoint.py tests/test_system_runtime_review_fixes.py tests/test_system_runtime_big13_additions.py tests/test_engineering_contracts.py tests/test_core_api_layering.py tests/test_repository_architecture.py flagships/tests/test_flagship_ladders.py flagships/tests/test_flagship_portfolio.py flagships/tests/test_thermoelastic_adapters.py` -> **208 passed**.
  New/rewritten: `tests/test_engineering_contracts.py` 35 (incl. fully regenerated-manifest attacks and a promoted level 5), `tests/test_system_runtime_big13_additions.py` 4, `flagships/tests/test_flagship_portfolio.py` 26 (14 functions, parametrized; re-verifies all 8 committed bundles and ties each report to its bundle digests), `test_flagship_ladders.py` 7 (provider-free level builders), `test_thermoelastic_adapters.py` 7.
- `python tools/forge_check.py --changed` -> exit 0, **149 passed** (it ran one pytest command, the fixed regression pack).
Real providers, WSL conda envs (`tools/wsl_env.sh`; `MSYS_NO_PATHCONV=1 wsl.exe -e bash pt.sh <env> ...`), flagship suites on the FINAL flagship / engineering code:
- env `fenicsx`: `flagships/tests/test_flagship_thermo_mechanical.py flagships/tests/test_thermoelastic_adapters.py` -> **20 passed** (24.8 s; includes the failed-exact-limit-request and unmet-stress-comparison tests).
- env `sci`: `flagships/tests/test_flagship_chemistry.py flagships/tests/test_flagship_cavity.py` -> **15 passed** (95.7 s).
- env `battery`: `flagships/tests/test_flagship_battery.py` -> **11 passed** (475.9 s).
Provider-adapter suites (no adapter, `system_runtime` or `pde` file changed after these runs; `git diff --stat 492da36a HEAD -- providers src/engcore/system_runtime src/engcore/pde` is empty):
- env `fenicsx`: `providers/calculix/tests providers/code_aster/tests providers/fenicsx/tests` (with the adapter and flagship-B suites) -> 50 passed; env `sci`: `providers/cantera/tests providers/tespy/tests providers/coolprop/tests` (with chemistry / cavity) -> 24 passed, `providers/openfoam/tests providers/su2/tests` -> 5 passed;
  env `battery`: `providers/pybamm/tests` (includes the BIG 12 real battery system test) -> 17 passed (351 s).
- First battery run of the first fix batch: **1 failed** (`test_window_refinement...` asserted the study MET). The study is NOT met (successive differences grow); the test now asserts that outcome and L4 ATTEMPTED_NOT_REACHED. Tolerances were not touched.
- Reports and bundles regenerated from real runs: `python -m forge_flagships.reports <battery|structure|cavity|chemistry> --docs docs/flagships --bundles docs/flagships/runs` in the matching env.
- **NOT RUN:** full FAST, full SCIENTIFIC, mutation shards, hardened recertification, CI / GitHub workflows, `forge_check --regression`; `providers/openmodelica/tests`, `providers/precice/tests` (untouched); no PR opened.

### Remaining gaps (BIG 14+)
- No uncertainty is quantified anywhere: every output is UNKNOWN and model discrepancy is NOT QUANTIFIED for all four; no experimental data was compared (the NASA PCoE pack is considered, applicability UNKNOWN, not compared).
- A: no independent cell-side conservation check; L2/L3 rest on one interface identity; window study not converging (cause unknown); Chen2020 applicability to this duty unknown; representative-day error unquantified.
- B: one shared mesh and temperature field (corroborates implementations only, FEniCSx/Code_Aster share a formulation); peak von Mises slow convergence and the CalculiX difference (0.023 %) not explained; no numerical thermo-structural benchmark integrated.
- C: near-lid disagreement and SU2 flux miss unexplained (mapping artifact untested); Ghia values transcribed from public sources, NOT checked against the printed paper.
- D: one chemistry provider; kinetic validity range of GRI-Mech 3.0 not established; no ignition-delay or flame data compared.
- Ladder / bundle: evidence records are self-consistent, not authenticated; the manifest is unkeyed.
- Optional flagship E (environmental degradation) not built.

## 2026-09-26 BIG 12 — End-to-End System Runtime (BUILD phase; read this first)

Branch `feat/big-12-end-to-end-runtime`, base `7da8d02e` (BIG 10/11 tree; `main` does not contain BIG 10/11), worktree `D:/forge-b12`.
New package `src/engcore/system_runtime/` (3.6k lines, non-Core, registered in `tests/test_core_api_layering.py`). Design: `docs/architecture/system_runtime.md`.

### What exists
- `SystemRunRequest` (content-bound: system/scenario/timeline/environment/material digests, initial state, nodes, observables, provider bindings, model selections, constraint observations; digest excludes label/workspace/budget), `SystemState` (authoritative, digest chain, atomic `advance`), `SystemExecutionPlan` (deterministic DAG + digest, derived nodes `env.*`/`mat.*`/`constraint.*`), `preflight` (READY / DEFERRED_CHECKS / REFUSED, never "validated"), `SystemExecutor` (PENDING/RUNNING/SUCCEEDED/REFUSED/FAILED/BLOCKED; dependency-based BLOCKED; independent branches still run; applicability is checked on the solved state BEFORE commit, so a refused step is rolled back), `SystemRunResult` (per-observable AVAILABLE/BLOCKED/REFUSED/FAILED/UNKNOWN, transitive `trace_result`), `assess_constraints` / `assess_conservation` / `trust_handoff` (existing `CredibilityEvidenceReport`; no new verdict enum), `SystemCheckpoint` + `verify_checkpoint` + resume, `compare_runs` (identity replay / numerical reproducibility / `scientific_validation="not_assessed"`), optional exact-identity `ExecutionCache`.
- Authorities: `CallbackAuthority`, `ProviderAuthority`, `MultiphysicsAuthority` (delegates to BIG 9 `MultiphysicsRuntime`), `MultiscaleAuthority` (delegates to BIG 10 `MultiTimescaleRuntime`; resume uses its `MacroCheckpoint`). No coupling loop, clock, scheduler or verdict is re-implemented.
- Real reference system: PyBaMM <-> TESPy (BIG 9) plus PyBaMM aging through BIG 10 / BIG 4 lifecycle, executed through the system runtime (`providers/pybamm/tests/test_system_runtime_battery.py`).

### Failed approaches / gotchas recorded
- Trace initially listed only direct-input lineage -> made transitive. Preflight refused checkpoints for stateless authorities -> rule is `supports_checkpoint or stateless`.
- Bash heredocs containing `'''` write nothing and stop the script; use the Write tool for patch scripts.
- Provider tests need `PYTHONPATH=src:.:providers/pybamm:providers/tespy` inside WSL or all 8 skip silently (`8 skipped`); and `MSYS_NO_PATHCONV=1` for `wsl.exe` paths.
- A `scientific_digest` that included the run-bound staleness `stamp` made two identical runs differ; the stamp is now excluded (`_verify_stored` compares the stamp directly, never through the digest).
- A separate first-pass rule "every binding of a provider must match" is what preflight does; an executor rule of "any binding matches" is only reachable across providers. The M3 test therefore uses two providers.

### Scientific review (read-only `forge-scientific-reviewer`), dispositions
Round 1 (9 HIGH/MEDIUM clusters, all fixed with tests in `tests/test_system_runtime_review_fixes.py`): H1 model selection required per executable instance + `trust_handoff` refuses a foreign request; H2 committed state uncertainty comes from the solve; H3 supplied content verified against its filing digest, material owner/state link; H4 checkpoint forgeries (initial-state chain, tip state, payload digest, completeness flag); H5 pending authority checkpoint promoted only after commit; H6 quantified output uncertainty from UNKNOWN inputs refused unless `accounts_for_input_uncertainty`; M1 waiver / `within` needs evidence digest; M2 partial run not silently assembled; M3-M7 provider binding match, plan-order restore, scenario-end/paused/NaN time, commit taint, cross-run cache reuse + stateful-never-cached + trace `reuse` link.
Round 2 (focused re-review of that batch: CHANGES REQUIRED, 1 HIGH + 5 MEDIUM + LOW):
- HIGH constraint limit chosen by the request -> FIXED (preflight + `assess_constraints` require the definition to equal the system's own; observation must name the bound constraint).
- MEDIUM state-borne UNKNOWN not gated -> FIXED (same gate on proposed state values). Waiver invisible -> FIXED (`APPLICABILITY_WAIVED` finding, `TrustInputs.waived_applicability`, credibility notes; trust inputs re-derived on load). Checkpoint conditional checks -> FIXED (history == committing-receipt chain, undeclared payload, deleted stateful declaration, non-boolean flags; `supports_checkpoint` authorities must declare state). Result derived fields -> FIXED (unknown-uncertainty outputs, applicability reports, waivers re-derived).
- LOW conflicting applicability reports -> FIXED. Four vacuous tests -> tightened.
- NOT FIXED, recorded: (a) model selection is a declared label, not bound to the authority/provider that executed (`trust_handoff` puts it in `provenance.models`); (b) the "declare or waive applicability" rule covers state-committing nodes only, output nodes still need none; (c) a `MultiscaleAuthority` resume stage with no `depends_on` on its producing stage reuses its own previous run's checkpoint (hidden instance state not in the node identity); (d) commit-taint residuals: wall-budget REFUSED branch does not taint, non-committing state readers after a tainted commit still run, `blocked_by` holds free text, derived-node cache reuse has no trace link; (e) waiver text and `within` evidence digest are format-checked only.
- The round-2 fix batch itself was NOT re-reviewed (a third review was not run).

### Verification actually executed (this session)
All with `TMPDIR=D:/ftmp`, main-checkout venv python, `PYTHONPATH="D:/forge-b12/src;D:/forge-b12"`, worktree `D:/forge-b12`:
- `pytest tests/test_system_runtime_contracts.py` 28 passed; `..._executor.py` 39 passed; `..._checkpoint.py` 11 passed; `..._review_fixes.py` 34 passed (HEAD `21a2c75c`).
- `pytest tests/test_core_api_layering.py tests/test_repository_architecture.py` + the four above: 129 passed.
- `python tools/forge_check.py --changed`: 149 passed.
- Real providers, WSL `battery` env (PyBaMM 26.8, TESPy 0.11.2): `providers/pybamm/tests/test_system_runtime_battery.py` 8 passed in 207 s (after the round-2 fixes).
- Earlier at `4e8252ce`, a wider focused regression showed 4 failures that were reproduced identically on a pristine base worktree; that wider set was NOT re-run at the final HEAD.
- **NOT RUN:** full FAST, full SCIENTIFIC, mutation shards, hardened recertification, `--regression` pack, CI. Conservation was demonstrated on toy core fixtures only, not on independent provider terms. Gate J (resource budget) on real providers not run. No multi-process preCICE participant was involved.

## 2026-09-26 BIG 11 — Solver Provider Expansion (BUILD phase; read this first)

Branch `feat/big-10-multitimescale` (continued, per instruction), base HEAD `d5f4b393`, worktree `D:/forge-big10`.

### Pre-BIG 11: final BIG 10 review
`forge-scientific-reviewer` (read-only): CHANGES REQUIRED, 9 findings that would block new providers; all fixed
with tests (`tests/test_multiscale_review_fixes.py::test_b1..b9`):
provider versions in a fast result must equal the identity's, and the reference systems now report
INSTALLED versions (numpy/scipy/dolfinx), not labels; one state contract per declared participant (empty
contracts are never "complete"); DECLARED_INITIAL repetition requires the resolved period's fast state to
return within a declared tolerance; output units and claimed history features/resolution are enforced
against the fast-system identity (declared `output_semantics`); `field_mapping` undeclared -> MAPPING
UNKNOWN; results echo `consumed_slow_state_digest` and every SLOW variable declares bound/not_consumed;
the fast-system identity is snapshotted at construction; LEADING_PERIOD requires the declaration that time
enters only through the request.  Aggregation refuses mixed-unit tiles.  Non-blocking, recorded: point-sample /
cycle inputs are only refused for repetition (not coverage-checked for fully resolved runs); unkeyed
checkpoints; `OutputSeries` keeps an ALL-features default for direct `aggregate()` calls (the runtime path
enforces declared features).

### Architecture (`src/engcore/providers/`, non-Core, registered)
- `catalog.py`: descriptive `ProviderCapability` (classification `descriptive_capability_not_applicability`),
  `ProviderRegistry` (`discover` in id order, `require(id, version=)` -> exactly that provider or
  `ProviderUnavailable`; no ranking, no fallback), probes for Python distributions (version + RECORD digest)
  and executables (exact resolved path + sha256 + parsed version; no version -> unavailable),
  `default_registry()` never raises. `python -m engcore.providers [--json]` lists discovery.
- `identity.py`: `ProviderExecutionIdentity.from_content` (provider id/version/digest, adapter, problem,
  generated configuration, input bytes, output request, window, environment, state, and
  `provider_dependencies`; NaN refused). Result-changing dependencies are identity: declared Python
  dependencies by RECORD digest (PyBaMM: casadi, pybammsolvers; TESPy: CoolProp) and process providers by
  a digest of their conda environment's package set (`conda_environment_digest`); `ProviderStatus.digest`
  combines them, `ProviderStatus.executable_digest` is the executable file alone.
- `process.py`: argv-only `ProcessInvocation` (absolute executable, digest, explicit env, timeout, sanitized
  names), `ProcessWorkspace` (fresh dir, run once or a declared `run_sequence`, process-group kill on timeout,
  outputs = regular files THIS run created/changed, `read_output` digest-verified; stale / foreign / input /
  symlinked files refused; the executable is re-hashed at launch against `executable_digest`).
- `records.py`: `ProviderExecutionRecord` (`provider_computation_not_evidence`, UNKNOWN uncertainty, failed
  records expose nothing, requested outputs must exist, non-finite refused).
- `compare.py`: `compare_providers(decl, a, a_output, b, b_output, *, a_select, b_select)` takes execution
  RECORDS (provider, BIG 6 numerical, BIG 8 PDE; stand-ins refused) and reads values AND units from them
  through a declared, digest-bound `OutputSelection` (rows / component / linear weights); refuses the same
  provider, any shared declared dependency / identical provider environment, and a side that declares no
  dependency set (independence UNKNOWN); tolerance is a spread
  (degC -> K delta), relative tolerance on an offset scale refused, compared values digest-bound,
  `post_hoc=True` -> `post_hoc_solver_corroboration_not_validation`; otherwise
  `solver_corroboration_not_validation`.
- Bounded additions elsewhere: `materials/fluids.py` (`FluidIdentity`, `FluidState`, `FluidPropertyRecord`,
  classification `provider_derived_property_not_measurement`); `pde/cases.py` (provider-neutral
  `PlaneStressProblem`/`RegionMaterial` shared by CalculiX and Code_Aster); `domains/battery/throughput_fade.py`.
- Architecture decision recorded: `tests/test_heterogeneous_ngspice.py::test_r1` pinned "no provider
  framework"; its preregistration (docs/milestones/heterogeneous-ngspice-prereg.md §4.2) deferred one with the
  named trigger "a second external provider whose process-execution needs actually overlap". BIG 11 fired it
  (five process providers share `providers.process`). R1 now asserts the trigger condition, that the provider
  tree imports no domain, and that the ngspice adapter stays local.

### Provider environments (exact)
WSL Ubuntu, micromamba 2.9.0, conda-forge, under `~/mm/root/envs` (`FORGE_PROVIDER_ENVS`):
`sci` (py3.11: cantera 3.2.0, coolprop 6.7.0 -> replaced by pip CoolProp 8.0.0 when `pip install tespy`
ran, tespy 0.11.2, pybamm 24.1 [conda resolver picked it; its `initial_soc` path calls `np.trapz`, removed in
numpy 2.4.6 -> UNUSABLE; not used for proofs; since the dependency-identity fix the registry reports it
UNAVAILABLE there because `pybammsolvers` is absent]); `battery` (py3.12: pybamm 26.8.0.0, numpy 2.5.3, scipy
1.18.1, tespy 0.11.2 + CoolProp 8.0.0 via pip); `calculix` (ccx 2.23); `openfoam` (openfoam.com v2412); `su2`
(8.5.0); `openmodelica` (omc v1.27.1-cmake); `code_aster` (18.1.7); `fenicsx` (from BIG 10; + c-compiler).
Elmer: no conda-forge package and no sudo for apt -> UNAVAILABLE.

### Executed providers and proofs (all runs in this session)
| Proof | Provider(s) | Result |
|---|---|---|
| A battery | PyBaMM 26.8 (SPM, Chen2020 by name, set content digest bound) | 1C 30 min discharge (SOC 0.9 -> 0.4, V down, T up); balanced cycle returns SOC 0.7; 10 Ah from 50 % SOC -> FAILED record (cut-off, infeasible); 273 K vs 318 K isothermal: colder ends lower V; capacity-fade mapping changes cell + identity; ambient/current from exact BIG 3/BIG 2 records |
| B chemistry | Cantera 3.2.0, gri30.yaml bytes bound | adiabatic CH4/air equilibrium 2150-2300 K band; IdealGasConstPressureReactor 1400 K, 50 ms: ignites (>2400 K), CH4 burned out; edited mechanism bytes = new identity |
| C thermophysical / system | CoolProp 8.0.0, TESPy 0.11.2 | water 25 C density 997.05 kg/m3 (IAPWS-95 EOS value), k 0.607; two-phase quality; out-of-range -> UNKNOWN record; TESPy chain: dh*m = 5000 W to 1e-9, outlet 43.92 C; impossible network -> FAILED |
| D second engineering solvers | CalculiX 2.23, OpenFOAM v2412, SU2 8.5.0, Code_Aster 18.1.7, OpenModelica 1.27.1 | all executed through the process boundary (see below) |
| E cross-provider | FEniCSx vs CalculiX; Code_Aster vs CalculiX; OpenModelica vs SciPy solve_ivp; OpenFOAM vs SU2 (record-bound API; OpenFOAM runs now demand steadiness <= 1e-7 m/s over the last write interval) | plane stress right-edge ux: max rel 0.156 % (both FEniCSx and Code_Aster differ from CalculiX by the identical 7.77e-7 m -- CalculiX expands 2-D elements to 3-D wedges; observation, not proven cause); lumped ODE: max 3.07e-6 K; CFD: declared-before-looking whole-field 3 % of lid speed FAILED (max 24.6 %, lid-adjacent); lower half (region chosen POST HOC) within 3 %: 20x20 2.70e-6 m/s, 40x40 1.44e-6 m/s; grid study lower-half max 2.55 % / 1.41 % / 0.75 % of lid speed at 20/40/80 cells, near-lid ~10 % at every N |
| F multiphysics | PyBaMM <-> TESPy on the BIG 9 runtime | 6 x 600 s windows IMPLICIT, all converged, iterations [10, 8, 12, 11, 10, 10]; SOC 0.567 -> 0.233 -> rest -> 0.567; final heat 0.479 W, cell 296.11 K; coolant inlet from BIG 3 channel |
| G multi-timescale | PyBaMM as BIG 10 FastSystem | 56 days represented / 8 days resolved (8 weekly windows, weight 7), 192 hourly PyBaMM segments; fade 0 -> 0.0385 (monotone); counterfactual day 1 with day-56 state: end-of-discharge V 3.7094 -> 3.6978 V; 10 PyBaMM executions, 26.1 s |
| H environment / material | PyBaMM (ambient), TESPy (coolant inlet), CalculiX + Code_Aster (BIG 5 E/nu records -> material cards), OpenFOAM + SU2 (CoolProp water records -> nu, rho, mu) | provenance digests carried into identities |
| I unavailable | registry + all 9 adapters in the core venv | `ProviderUnavailable`, never ImportError, never substitution |
| J stale output | process boundary (core), CalculiX (stale job.dat), OpenFOAM (stale 99999/ time dir) | refused; notably `postProcess -latestTime` picked the planted stale dir and Forge refused the result -> adapter now asks for the exact end time |

Runtime metrics (operational, not a ranking): CalculiX 82 nodes/132 CPS3 ~0.01 s process; Code_Aster same mesh
1.26 s; OpenFOAM cavity 20x20 1000 steps 0.41 s, 40x40 3000 steps 2.35 s, 80x80 15.5 s; SU2 20x20 1.8-1.9 s
(149-191 it), 40x40 3.4 s (389 it), 80x80 26.8 s (1361 it); OpenModelica compile+simulate ~5 s; PyBaMM 1-h
4-step probe 0.08 s solve (import 7.8 s); Cantera equilibrium + reactor < 1 s.

### Failed approaches / findings (do not repeat)
- `pybamm` with `cantera`+`coolprop` in one conda solve -> PyBaMM 24.1 + NumPy 2.4.6 (broken `np.trapz`); use a
  dedicated env.  `pip install tespy` replaced conda CoolProp 6.7.0 by 8.0.0 (recorded).
- numpy 2 `repr(np.float64)` is `np.float64(x)`: broke generated CalculiX decks (exit 201; failed closed).
- Isothermal PyBaMM reports zero heat unless "calculate heat source for isothermal models" is set.
- A 10 A x 30 min load from SOC 0.9 on a 5 Ah cell hits the cut-off: PyBaMM stops early and Forge refuses.
- SU2 8.5 `OUTPUT_FILES=(CSV)` writes no volume CSV here; `RESTART_ASCII` -> `restart.csv`.
- `omc --version` prints `v1.27.1-cmake`; the first parser required an "OpenModelica" prefix -> unavailable.
- License strings first written from memory were wrong for OpenFOAM (GPL-3.0-only) and SU2 conda build
  (GPL-2.0-or-later): descriptors now quote installed package metadata.
- After binding the conda env digest into `ProviderStatus.digest`, adapters still passed that COMBINED digest as
  the executable's digest; the new launch-time re-hash refused every process provider ("changed since
  discovery"). Fixed with a separate `executable_digest`. The re-hash did its job on the first run.
- `CP.set_reference_state("Water", "IIR")` raises (IIR's 0 C lies below water's triple point 273.16 K);
  the pinning test uses NBP.
- `SolverIdentity` names its field `version`, not `solver_version`.

### Open non-blocking gaps (BIG 11)
- Bounded case families only: OpenFOAM/SU2 lid-driven cavity; OpenModelica lumped thermal capacitance;
  CalculiX/Code_Aster linear plane stress on triangles; TESPy source->heat exchanger->sink chains.
- Code_Aster adapter parses displacement only; SU2/OpenFOAM pressures differ in convention (Pa vs m2/s2) and
  are not compared.
- PyBaMM parameter sets are provider-bundled literature data (content-digested), not Forge-sourced data;
  the capacity-fade -> LAM mapping is a declared approximation.
- TESPy is not independent of CoolProp; `compare_providers` now refuses that pair structurally.
- Registry `available` cannot detect a broken library build (PyBaMM 24.1 case); executions fail closed.
- Root `pyproject.toml` extras were NOT changed (providers are separate distributions); `[battery]` etc.
  extras remain a packaging decision.
- Provider processes run on Linux/WSL only here; the Windows core env only exercises the boundary.
- Elmer UNAVAILABLE; SUNDIALS contract only; standalone PETSc provider not run.
- A `ProviderExecutionRecord` can be constructed directly with an invented identity; the type is a contract,
  not proof of execution. In-process records are bound to the COMPARING process's environment digest.
- CoolProp's range check sees only the EOS Tmin/Tmax/pmax; transport correlations can be narrower.
- `segments_from_records` refuses record changes (interval edges, samples, non-step interpolation) inside a
  segment rather than splitting segments; PyBaMM `coupling.py` reads the caller's `current_at` at window start.
- Dependency identity covers declared dependencies and conda package sets, not system libraries outside the env.

### BIG 11 scientific review (forge-scientific-reviewer, read-only)
First review: CHANGES REQUIRED, no BLOCKER. HIGH: (1) comparison accepted stand-in objects, caller-stated
units and provider-id overrides; (2) a degC tolerance was converted as a point; (3) independence ignored
shared dependencies; (4) PyBaMM segments sampled only segment starts; (5) library identity lacked dependency
digests. MEDIUM: (6) declared-before-looking had no structural form; (7) executable not re-hashed at launch,
env libraries undigested, symlinked outputs admitted; (8) wall time in the CoolProp request, random workspace
path in the Code_Aster `.export`; (9) no CoolProp range check, process-global reference state outside identity;
(10) PyBaMM fast-system contract hid reset state; (11) `RegionMaterial` provenance any string, thickness /
empty groups unchecked. LOW: (12) echo-check wording; (13) provider defaults in `BatteryFastSystem`, coupling
initial iterate outside identity; (14) OpenFOAM steadiness only a metric, pressure semantics; (15) compression
of non-extensive domain aggregates, `_value_digest` truncation, Cantera cross-file mechanism refs, vacuous
CalculiX tag check.
Fixes (all with tests): 1-3, 6 in `providers/compare.py` (+ `tests/test_provider_boundary.py`); 4 refusal
(`test_pybamm_provider.py`); 5, 7 via `ProviderStatus.dependencies` / `executable_digest`, conda env digest,
launch re-hash, symlink exclusion; 8 request without wall time, workspace-relative `.export`; 9 `DEF` pinned per
call + EOS range -> UNKNOWN (`test_coolprop_provider.py`); 10 `ParticipantStateContract.reset_state` (in
identity); 11 digest-shaped provenance, thickness > 0, non-empty groups, one material per region; 12 docstring;
13 keyword args without defaults, initial iterate in configuration; 14 `steady_tolerance` (run fails when not
met) + kinematic-pressure semantics recorded; 15 all four (`tests/test_big11_review_fixes.py`,
`test_cantera_provider.py`).

Focused re-review of the fixes:
CHANGES REQUIRED, no BLOCKER. Confirmed FIXED: 2, 5, 6, 7, 8, 9, 10, 12, 14, 13 (fast system) and the `compress_history` part of 15. It found five MEDIUM items left open or introduced:
- (1) compared values were still caller arrays;
- (3) Forge-internal records and process providers without `FORGE_PROVIDER_ENVS` counted as independent by default;
- (4) sampled ambient channels were read at segment starts only;
- (11) `RegionMaterial` accepted any 64-hex string, unbound to E and nu, and Code_Aster did not refuse overlapping or colliding regions;
- (15, new) `aggregate()` summed a non-extensive domain aggregate across several weight-1 tiles.

All five are fixed with tests:
- `OutputSelection` (rows / component / declared linear weights, digest-bound): `compare_providers` reads values AND units from the records, and the caller passes no numbers.
- `shared_dependencies` returns "independence UNKNOWN" when either side declares no dependency set.
- In-process records, and every Python-library provider, carry `python-environment` (the digest of the interpreter's distribution set plus conda records); identical environments are refused.
- `segments_from_records` refuses sampled channels that are not step-hold/none or that have samples inside a segment.
- `RegionMaterial(region, E_record, nu_record)` holds the BIG 5 `ResolvedProperty` objects themselves (KNOWN, right property id).
- Code_Aster refuses overlapping or colliding region groups.
- `aggregate()` returns UNKNOWN for a non-extensive domain aggregate over more than one tile.
- LOW, also fixed: `reset_state` is omitted from `to_dict` when empty, so earlier contract digests do not move.

Open LOW items, recorded rather than fixed:
- A `ProviderExecutionRecord` can still be constructed directly with an invented identity; the record type is the contract, not a proof of execution.
- The environment digest of an in-process record is the comparing process's environment.
- `FastSystemIdentity` names providers by (id, version) only.
- OpenFOAM `blockMesh` / `postProcess` are hashed when the invocation is built, not at discovery.
- Hard links are not excluded.
- CoolProp has no pmin or Hmass range check, and the process-global reference state is not thread-safe.
- `reset_state` vs `declared_state` overlap is unchecked.
- The coupling's 0.1 W initial heat iterate is an adapter constant (recorded in configuration).
- PyBaMM `current_at` in `coupling.py` is sampled at window start (the caller's callable must be constant per coupling window).
- `_value_digest` falls back to `repr` for some interpolant types.
- The Cantera cross-file check is a regex heuristic.
- `ProviderExecutionIdentity` schema stays `/1` (the module is new in BIG 11; no stored records).

A second re-review of these follow-up fixes was NOT run.

### Verification (focused only; full FAST / SCIENTIFIC / mutation / recertification NOT RUN, deferred to BIG 14-15)
- WSL `sci` env: `pytest --import-mode=importlib -q -p no:cacheprovider providers/coolprop/tests providers/cantera/tests
  providers/tespy/tests providers/openfoam/tests providers/su2/tests providers/openmodelica/tests` (+ boundary in a
  `tests/test_provider_boundary.py`) — PASS, 30 passed (the 14 boundary tests incl. the symlink test run there).
  Earlier runs this session: 8 failed (combined digest passed as executable digest; IIR reference state), then 2 failed
  (`solver_version` attribute; the 4-cell stale-output OpenFOAM case inherited a steadiness demand) — fixed; final
  run after the re-review fixes: 30 passed.
- WSL `battery` env: `pytest ... providers/pybamm/tests` — PASS, 9 passed (Proofs A, F, G, H + sampled-channel
  refusal; two earlier runs failed on the new test's own fixture: sample quantity id, sample outside validity).
- WSL `fenicsx` env: `pytest ... providers/fenicsx/tests providers/precice/tests providers/calculix/tests
  providers/code_aster/tests` — PASS, 38 passed.
- Windows core venv: `pytest -q -n 4 <focused list> tests/test_numerical_foundation.py tests/test_spatial_core.py
  tests/test_provider_boundary.py tests/test_big11_review_fixes.py tests/test_multiscale_review_fixes.py` — 1967 passed,
  9 failed, 3 skipped, 1 error (final tree). Failure set = pre-existing baseline (test_core_freeze_manifest descendant, 2 core_guards,
  3 numerical_foundation, 2 spatial_core, test_verdict_monotonicity import error) + `test_the_tree_is_core_freeze_v1`
  on `tree.clean` only (uncommitted files; re-run after commit below). `test_heterogeneous_ngspice::test_r1` passes.
- `python tools/forge_check.py --changed` — PASS, 149 passed. `python -m compileall -q src providers tests` — OK.
  `git diff --cached --check` — clean; no CRLF in staged files.
- After commit `ae605fbc` (clean tree): `pytest -q tests/test_core_freeze_manifest.py` — 21 passed, 1 skipped, 1 failed;
  `test_the_tree_is_core_freeze_v1` PASSES; the one failure is the pre-existing baseline
  `test_a_descendant_that_keeps_the_contract_still_verifies`.

## 2026-09-25 BIG 10 — Multi-timescale Runtime (BUILD phase)

Branch `feat/big-10-multitimescale` created from `main` @ `e3ae778a` (it did not exist locally or
on origin; the shared checkout was on stale `2b76017f`, so a worktree `D:/forge-big10` was used).

### Environment (exact)
- Core env: Windows, `.venv` Python 3.14.2, numpy 2.5.2, scipy 1.18.1, pint 0.25.3.
- FEniCSx env rebuilt in WSL Ubuntu (no `/opt/mm` here, no sudo): micromamba 2.9.0 ->
  `~/mm/root/envs/fenicsx` (conda-forge, Python 3.11): dolfinx **0.11.0**, petsc4py **3.25.5**,
  pyprecice/preCICE **3.4.0**. First run failed: FFCx JIT needs a C compiler (`gcc` missing) ->
  `micromamba install c-compiler` (gcc 15.2.0) and PATH/CC set in the runner.

### BIG 9 re-review (before BIG 10)
`forge-scientific-review`: CHANGES REQUIRED, five BIG 10 blockers. Fixed:
- B10-2 `execution/multiphysics/runtime.py`: implicit residual measured on the relaxed increment
  (omega * r) -> now on the UNRELAXED transfer H(x_k) - x_k (Jacobi and serial); no fallback.
  Test: omega=0.05 no longer "converges" at x=0.25 K when the fixed point is 10 K.
- B10-3: events from a participant not declared `event_capable` refused; event alignment requires
  deterministic checkpoints of every participant (plan admission already refused the latter).
- B10-4: every STEP-input sample instant and operating-condition segment start is a window
  boundary (an event-shifted grid delivered them late); float-grid slivers snapped.
- B10-1 `coupling/adapters.py`: `provider_participant` now advances declared `evolved_state`
  (FAST) from the solve's `next_state`, refuses a solve that returns held (SLOW) state, digests
  value+unit+uncertainty, and carries an explicit `ParticipantStateContract`
  (DECLARED_COMPLETE with a basis, or NOT_ESTABLISHED).
- B10-5: resume is provided at macro boundaries by BIG 10 `MacroCheckpoint`; each fast execution
  is a fresh coupled run, so runtime-internal mid-run resume is not needed by BIG 10 (gap below).
- Found while running: `ConvergenceCriterion` with a watt tolerance produced `numpy.bool_`
  (pint returns NumPy scalars) -> `satisfied = bool(...)` in `convergence.py`.
Non-blocking BIG 9 items left open: N1 IDENTITY edge + consumer-side mapping reports
`coupling_error_bound == 0.0`; N2 event-aligned inner non-convergence relabelled; N3 parameter
bindings not recorded for replay; N4 preCICE peer process not killed on early return; N5
absolute-OR-relative acceptance; N6 heater TCR law has no declared temperature range. N7 (PROGRESS
said relaxation 0.5; the gate-B test uses 0.7) is corrected here: gate B used relaxation **0.7**.
Changed certified-scope files (`execution/multiphysics/runtime.py`, `convergence.py`): bug fixes
that are stricter (fail-closed); hardened recertification is still owed (BIG 14-15).

### Architecture (`src/engcore/multiscale/`, non-Core, registered)
Orchestration only; reuses BIG 2 `Timeline`/`TimeWindow`/events/histories, BIG 3
`EnvironmentTimeline`, BIG 4 `DegradationModel`/`DegradationStepRecord` (new
`evaluate_degradation_step` shared with `evaluate_degradation`; new `PHYSICS_AGGREGATE` input,
`AggregateRequirement`, `HistoryFeature`, `StepStatus.INSUFFICIENT_HISTORY`), BIG 5
`MaterialState`/resolve, BIG 6/8 providers and the BIG 9 `MultiphysicsRuntime` behind a
`FastSystem` contract (no dolfinx/preCICE import in `multiscale`).
- `scales.py` ScaleHierarchy (FAST/OPERATIONAL/SLOW roles; domain-declared state ownership).
- `windows.py` MacroStepPolicy (adaptation rules DEFAULT/AFTER_ELAPSED/NEAR_THRESHOLD, event
  SPLIT/REFUSE, StateChangeLimit with explicit scale, ThresholdWatch), RepresentativePolicy /
  RepresentativeWindow (exact rational weight = represented/resolved; whole-period tiling + resolved
  remainder; declared assumptions/applicability; measured input deviation vs declared periodicity
  tolerances), AdaptationDecision, RefinementDecision.
- `aggregation.py` OutputSeries, AggregationSpec/Record (integral, time-weighted mean, extrema,
  cycle count, histogram, dwell-above, domain-defined), preserved/lost features, repetition drops
  ORDER/EXTREMA, gaps -> UNKNOWN, `compress_history` (derived, one spec, never gains features).
- `fast.py` FastSystemIdentity (providers, graph fingerprint, contracts, material bindings, purity
  declaration), FastExecutionRequest (identity = exact content), FastExecutionResult,
  `check_material_reresolution`.
- `approximation.py` ledger of 7 separate components (numerical, time integration, mapping,
  aggregation, representative window, model uncertainty, model discrepancy); no score.
- `checkpoint.py` MacroCheckpoint (self-verifying serialize/deserialize).
- `runtime.py` MultiTimescaleRuntime (run/resume), MacroStepRecord chain, accounting,
  `compare_resume`.
- Domain probe `domains/electrical/resistance_drift.py`: Arrhenius-equivalent-time domain
  aggregator (needs DWELL; per-sample temperature range 273.15-473.15 K) and linear drift model.
  `HeaterCircuit.root_method` added (default `hybr` keeps BIG 9 identity).

### Scientific review of BIG 10
`forge-scientific-review`: CHANGES REQUIRED (F1-F4 HIGH, F5-F13 MEDIUM, F14-F16 LOW). Fixed:
F1 repetition measured against the resolved period's inputs (declared tolerances; rejection ->
refine); F2 read-only state snapshots to fast systems and in records/checkpoints; F3 ledger from
cumulative (checkpointed) accounting + ledger in `compare_resume`; F4 cycle counts UNKNOWN when a
cycle may straddle a boundary / repetition does not close; F5 whole-period tiling; F6 extrema of a
repeated window UNKNOWN, nothing admitted that preserves nothing; F7 fast-state validation +
declared fast state in identity; F8 TERMINATION stops, unapplied STATE_CHANGE_REQUEST refused; F10
declared purity gates reuse + consumed environment/timeline digests checked; F11 any exception is a
refusal that keeps checkpoints; F12 compression requires one spec and honours the statistic; F13
Arrhenius applicability per sample temperature, board property re-resolved at the solved
temperature bound; F14 run_id check + "corruption, not forgery" docstring; F15 no relaxed fallback.
Partial: F9 (classification/attribute/digest check and a `multiscale-macro:` run_id prefix; a
serialized binding-kind discriminator needs a schema-version decision). Focused re-review (read-only, static): F2-F8, F10-F15 confirmed FIXED; it found N1 (HIGH) the
periodicity check compared only at repeated-entry starts, N2 (HIGH) point-sample channels and cycle
histories were never measured, N3 (MEDIUM) a caller-edited checkpoint counter could make the ledger
claim "no repetition", N4 (LOW) events exactly at the horizon end ignored, N5 (LOW) cached results
not re-verified, N6 (MEDIUM) FEniCSx alloy range never checked. All fixed with tests: comparison at
the union of both periods' change points; LEADING_PERIOD refused while point-sample channels or
cycle histories exist; resumed ledgers never report REPRESENTATIVE_WINDOW NOT_APPLICABLE and
checkpoint counters must match exactly; end-of-horizon TERMINATION/STATE_CHANGE_REQUEST act; cache
entries re-verified by digest; alloy re-resolved at the solved plate min/max (illustrative
273.15-600 K fixture set). F9 digest now must be hex. Not re-reviewed after these fixes.

### Executed proofs (all numbers from runs in this session)
Reference system (illustrative fixtures): heater on a two-region plate / lumped board in a
DECLARED cyclic damp-heat chamber program (hourly; shaped after IEC 60068-2-30 Db, conformance not
claimed, source kind `design_assumption`; upper temperature +0.25 K/day; program change = BIG 2
DISCONTINUITY at day 30.5); heater 10 V 06-18 h / 2 V standby (USAGE history). Slow state: board
`moisture_content` (wetness-dose uptake) and heater `resistance_drift` (Arrhenius equivalent time
from the fast heater-temperature DWELL history). Fast: BIG 9 implicit coupling, 1 h coupling windows.

**B / F — 63-day long horizon (FEniCSx 0.11.0 plate + SciPy `lm` circuit, 60 ohm series):**
completed; represented **63 d** vs resolved **14 d** (1,209,600 s); **13** macro windows, **15**
representative executions (13 repeated, weights 7/2/3; remainders resolved), **336** real coupled
FEniCSx+SciPy windows, 2,767 coupling iterations, 1 event split (window ends at day 30.5),
2 adaptation changes (7 d -> 2 d near the moisture breakpoint 0.05 -> 7 d), threshold crossing
localized in a 2-day window, 0 rejections, 0 cache reuses, wall 42.8-53.4 s. Moisture 0 -> 0.0817,
drift 0 -> 0.0115, board k re-resolved every window 0.0350 -> 0.0529 W/(m K) (SOURCED ->
INTERPOLATED). Same day-0 window/environment/usage with day-63 slow state changes the heater
temperature by up to **3.96 K** (counterfactual execution). Lumped+SciPy (core env): same
partition/counts, 2,678 iterations, moisture 0.0816, drift 0.173 (1 ohm series), wall 16.9 s.
**A — 72 h:** reference = 3 x 1-day fully resolved macro windows (72 h resolved); multi-timescale =
one 3-day window, 1 day repeated x3 (24 h resolved). Moisture identical (environment dose integrated
from the full BIG 3 history in both). Drift: FEniCSx ref 3.1966e-4 vs ms 3.1706e-4 (-0.81 %);
lumped ref 1.0394e-2 vs ms 1.0593e-2 (+1.91 %; the missing daily drift feed-forward dominates the
+0.25 K/day ambient rise). Recorded as observations against a MORE TEMPORALLY RESOLVED NUMERICAL
REFERENCE, not bounds; REPRESENTATIVE_WINDOW stays UNKNOWN.
**C:** event at day 4 + 7 h -> window ends exactly there; `event_handling=refuse` -> run refused,
no step, no checkpoint.
**D:** drift model bound to a time-weighted MEAN temperature -> `insufficient_history` (DWELL lost),
run stopped, drift stays 0; Arrhenius aggregator refuses a mean-only source series; a histogram is
refused for an ORDER-requiring input.
**E:** checkpoint -> JSON -> fresh runtime (and, core env, a separate OS process) -> continuation:
`compare_resume` matched (all macro-step digests, final state, accounting, ledger). FEniCSx:
1 + 3 steps over 21 days with a fresh gmsh mesh/provider; lumped: 12-day pause of a 28-day run.
Also: NOT_ESTABLISHED completeness -> run continues, resume refused; tampered payload and foreign
policy refused; a failed step keeps the previous checkpoint.

### Failed approaches (do not repeat)
- `HeaterCircuit` with SciPy 1.18 `hybr` refuses ~6 % of states of its LINEAR KVL residual after
  reaching it to 1e-16 ("not making good progress"), independent of xtol/initial guess; `lm` has
  zero such refusals -> `root_method` field, BIG 10 uses `lm`.
- 0 V standby: `hybr` refuses the trivial root -> declared 2 V standby.
- BIG 6 `UnitBoundary(scale=100)` expects NORMALIZED operands; physical operands gave 22,334 K.
- FEniCSx plate (insulating board half) at 1 ohm: mean 588 K; at 15/25/35 ohm the plate maximum
  (496.6 K at 25 ohm, ~480 K at 35 ohm) left the declared 473.15 K board-data range -> refused
  (correct). A 1.0 W declared initial power iterate overshot the range in the first iterate ->
  0.1 W. 60 ohm keeps the hottest day at a 408.8 K board bound.
- First "baseline" comparison run imported the modified `src` (sed missed PYTHONPATH) -> redone
  with a dedicated runner; recorded here so the invalid result is not reused.

### Open non-blocking gaps (BIG 10)
- Representative selection is LEADING_PERIOD only (no clustering/typical-day selection); weights
  are whole periods; no quantified representative-window error (UNKNOWN); one observation per
  scenario/horizon only.
- Slow state is held constant inside a macro window for the fast physics (no intra-window
  feed-forward) -- the 72 h lumped discrepancy (+1.9 %) is exactly this.
- Fast participants in the proofs are quasi-static (steady per coupling window); no transient
  fast state was exercised with real providers (toy system covers CARRY/DECLARED policies).
- Board conductivity data are illustrative and DECLARED temperature-independent over 273-473 K;
  alloy k looked up at a DECLARED 450 K (temperature dependence not iterated). Environment is a
  declared test-chamber scenario, not a measured dataset.
- F9 partial (no serialized binding-kind discriminator on DegradationStepRecord).
- Macro-step events: DISCONTINUITY/SCHEDULED split; TERMINATION stops; STATE_CHANGE_REQUEST is
  refused (no transition authority yet); state-dependent regime changes beyond declared
  thresholds are not detected.
- Point-sample environment channels and cycle histories are not measurable for periodicity yet:
  representative repetition is refused while they exist.
- Checkpoint digest is unkeyed (detects corruption, not forgery); runtime-internal mid-run
  resume of a coupled run (B10-5 in the BIG 9 sense) not built.

### Verification (BUILD-phase focused checks only)
2026-09-25
command: `python -m compileall -q src/engcore/multiscale src/engcore/coupling src/engcore/scenarios src/engcore/execution/multiphysics src/engcore/domains/electrical tests/multiscale_reference.py` — PASS
command: `pytest -q -n 4 tests/test_multiscale_review_fixes.py tests/test_multiscale_runtime.py tests/test_big9_review_runtime_fixes.py` — PASS, 42 passed (final; includes a separate-process resume)
command: `pytest -q -n 4 <13 multiphysics/lifecycle/coupling test files> tests/test_multiscale_review_fixes.py tests/test_core_guards.py tests/test_pde_contracts.py tests/test_spatial_core.py tests/test_numerical_foundation.py tests/test_environment_engine.py` — final: 1946 passed, 9 failed, 1 error. The same 8 failures + 1 collection error occur on a pristine `e3ae778a` worktree run with its own `src` (environmental in this py3.14 venv): test_verdict_monotonicity (ImportError), test_core_freeze_manifest::test_a_descendant_that_keeps_the_contract_still_verifies, test_core_guards::{test_the_bare_install_the_readme_documents_is_the_one_that_must_be_green, test_the_domain_names_were_derived_from_the_packages_not_listed}, test_numerical_foundation::{test_nonlinear_failure_withholds_the_last_iterate, test_nonlinear_root_two_methods_agree_with_exact_jacobian, test_problem_level_refusals}, test_spatial_core::{test_duplicate_facet_and_flattening_are_refused, test_meshio_roundtrip_preserves_identity}. The one extra failure, test_core_freeze_manifest::test_the_tree_is_core_freeze_v1, failed only its `tree.clean` check (uncommitted files); re-run after the commit: see below.
command (WSL conda env, `PYTHONPATH=src:providers/fenicsx:providers/precice:.`): `pytest --import-mode=importlib -q -p no:cacheprovider providers/fenicsx/tests providers/precice/tests` — PASS, 35 passed (BIG 8/9 suites + 4 BIG 10 FEniCSx proofs; real preCICE 3.4.0 run included). Earlier runs in this session: 18 failed before `c-compiler` (environment), 1 failed on a wrong Proof E assertion (steps != executions with remainder tiles; fixed).
command: `python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --cached --check` — PASS (no CRLF in added files)
command (after commit 5b5d17f5, clean tree): `pytest -q tests/test_core_freeze_manifest.py` — 21 passed, 1 skipped, 1 failed (test_a_descendant_that_keeps_the_contract_still_verifies); its 27 check outcomes are identical to the pristine e3ae778a run except the HEAD sha, i.e. the same pre-existing (baseline) failure. test_the_tree_is_core_freeze_v1 now PASSES.
NOT RUN: full FAST, full SCIENTIFIC, `forge_check.py --regression`, mutation shards, hardened
recertification (owed: certified-scope `execution/multiphysics/runtime.py` and `convergence.py`
changed), full CI.

### Readiness
Forge evolves a 63-day system (Time + Environment + real FEniCSx/SciPy coupled fast physics +
aggregation + lifecycle + material feed-forward + event refinement + checkpoint/resume) resolving
14 of 63 days. BIG 11 not started.

## 2026-09-25 BIG 9 — Generic Multiphysics Runtime + preCICE (BUILD phase)

Pre-BIG 9 rerun of `forge-scientific-review` on BIG 8 final fixes: no blocker.
BIG 8 gap "iterate identity" is closed by `engcore.coupling.provider_participant`
rebuilding each provider problem per iterate (distinct execution identities).

Built (engine = existing `execution/multiphysics` MultiphysicsRuntime; no parallel framework):
- `src/engcore/coupling/` (non-Core, registered): provider_participant, field/scalar
  ports, SpatialField<->FieldRecord adapters, consumer-side BIG 7 `mapped_input`,
  CouplingExecutionLog. Failed provider record -> CouplingRefusal (window refused,
  no fields); coupling outputs carry UNKNOWN uncertainty; initial iterates labelled
  `declared_initial_iterate_not_a_result`.
- `domains/electrical/heater_circuit.py` (SciPy root KVL with linear TCR, refuses R<=0).
- PDE: `PDEProblem.field_inputs`, template THERMOELASTIC_PLANE_STRESS, FEniCSx branch.
- `providers/precice` (`forge_precice`, pyprecice/preCICE **3.4.0**, conda-forge):
  Forge contract -> rendered preCICE v3 XML (serial-implicit, absolute measures,
  constant relaxation, initialized exchanges), two OS processes over sockets.
- Fix: `SpatialMesh.core_support` treated an empty caller store as falsy (`or`) -> `is None`.

Gate status (all executed in this session in the fenicsx env unless marked):
A one-way thermal->thermoelastic PASS; B two-way FEniCSx heat <-> SciPy circuit,
relaxation 0.7 (corrected in BIG 10; was misrecorded as 0.5), residual history, 16 iterations, T=379.28 K, P=6.4434 W PASS;
C NTC non-convergent case refused PASS; D two gmsh meshes (0.02/0.03) with explicit
BIG 7 mapping (NOT_CONSERVATIVE, in provenance), unmapped/wrong-unit edges refused PASS;
E FEniCSx + SciPy + lumped/preCICE providers PASS; F BIG 2 TimeWindow PASS;
G BIG 3 hourly_environment ambient preserved, UNKNOWN refused PASS; H BIG 4 lifecycle
moisture changes next coupled run PASS; I conservation audit FAILS at 1e-9 W
(relaxed received vs dissipated differ 2.8e-8 W, asserted) and passes at 1e-6 W —
a diagnostic, not validation; J **real preCICE 3.4.0 execution PASS**: 15 implicit
iterations, T=377.3349 K, P=6.4758 W, matches independent brentq fixed point to 1e-6;
max_iterations=3 refused although preCICE continues.

Initial preCICE failures (recorded): children could not import forge_precice
(relative PYTHONPATH with temp cwd) -> absolute import roots; first participant read
T=0 (no initial data) -> `initialize="true"` on exchanges.

BIG 9 review (`forge-scientific-reviewer`, read-only, no tests): CHANGES REQUIRED.
Fixed blockers: (1) units at preCICE boundary were assumed -> MODEL_UNITS declared per
driver model, contract exchange units must match, refused before launch (test degC);
(2) caller-supplied acceptance callable -> Forge re-evaluates both declared models
(`fixed_point_residuals`) against each exchange's absolute limit. Also fixed: empty /
inconsistent window logs refused, duplicate quantities refused, `result_digest` added.
Non-blocking gaps: runtime ConvergenceCriterion accepts absolute OR relative (tests
use relative=0); participant held-state completeness not enforced (closure state could
break replay); preCICE provider scalar-only, single rank, one mesh vertex; lumped
thermal resistance and efficiency=1.0 joule conversion are DECLARED assumptions;
runtime BILINEAR mapping only structured, so unstructured mapping is consumer-side.

Commands executed (this session):
- `PYTHONPATH=src:providers/precice:providers/fenicsx timeout 1500 /opt/mm/root/envs/fenicsx/bin/python -m pytest --import-mode=importlib -q -p no:cacheprovider providers/fenicsx/tests providers/precice/tests` -> 28 passed (before review fixes)
- `PYTHONPATH=src:providers/precice timeout 900 /opt/mm/root/envs/fenicsx/bin/python -m pytest --import-mode=importlib -q -p no:cacheprovider providers/precice/tests` -> 6 passed (after review fixes)
- `PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_spatial_core.py tests/test_pde_contracts.py tests/test_core_api_layering.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py` -> 53 passed
- `PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_core_guards.py -k dependenc` -> 6 passed
- `python tools/forge_check.py --changed` -> 149 passed
- `git diff --check` -> clean
NOT RUN: full FAST/SCIENTIFIC tiers, mutation shards, recertification, full CI.

## 2026-09-25 BIG 8 — PDE / FEM Provider Layer (BUILD phase; read this first)

### Pre-check
BIG 7 re-review at `99f1c1b`: PASS WITH NON-BLOCKING GAPS, no PDE blocker.
Adopted: COMPUTED spatial fields now require provenance; PDE layer declares
facet roles.

### Environment (exact)
- dolfinx has no pip wheel; FEniCS PPA blocked by egress policy (403);
  micro.mamba.pm blocked (403). Worked: micromamba 2.9.0 from GitHub releases
  -> `/opt/mm/micromamba create -n fenicsx -c conda-forge python=3.11
  fenics-dolfinx petsc4py mpich pint numpy scipy sympy python-gmsh meshio pytest`.
- Versions: dolfinx 0.11.0, basix 0.11.0, ufl 2026.1.0, PETSc/petsc4py 3.25.5,
  gmsh 4.15.2, meshio 5.3.5, Python 3.11.
- Architecture decision (after a failed attempt): putting dolfinx/basix/ufl/
  mpi4py imports in `src/engcore/pde` tripped the certified dependency guard
  (`tests/test_core_guards.py`, referenced by certification manifests) because
  `fenics-*` distribution names differ from import names and are not pip
  installable. Instead of editing a certified guard or hiding imports, the
  provider moved to a separate distribution `providers/fenicsx`
  (`forge-fenicsx-provider`, own pyproject declaring `fenics-dolfinx`, etc.).

### Scientific review
BIG 8 review: CHANGES REQUIRED (no formal BLOCKER). Fixed: facet overlap
between role groups refused (defense-in-depth; BIG 7 meshes already cannot
overlap), schedule times must be window start or declared breakpoints with
unit checks, execution records verify COMPUTED provenance of their fields,
coefficient slots carry admissible ranges (k, c, E, t, h > 0; 0 <= nu < 0.5),
transient discrete-bound violations are reported as diagnostics warnings,
P2 node mapping tested against the analytic solution. Not re-reviewed.

### Open non-blocking gaps
- 2D affine triangles only; P1/P2 Lagrange; no hexahedra, 3D, mixed cells,
  nonlinear materials, contact, remeshing, moving meshes, mortar/cohesive
  interfaces.
- Inactive PETSc options (e.g. ksp_rtol with preonly) enter identity; PETSc
  prints "Option left" warnings.
- Transient: constant step, backward Euler only; boundary values piecewise
  constant per segment; source terms not exercised.
- No heat-flux post-processing (reaction/flux integrals) yet; refinement study
  compares interface temperature only; no asymptotic convergence claim.
- Provider runs only in the conda env; core CI covers contracts only.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/pde providers/fenicsx/forge_fenicsx` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_pde_contracts.py tests/test_spatial_core.py tests/test_numerical_foundation.py tests/test_materials_engine.py tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_core_api_layering.py tests/test_field_values.py tests/test_field_records.py` — PASS, 211 passed
command: `PYTHONPATH=src:providers/fenicsx /opt/mm/root/envs/fenicsx/bin/python -m pytest --import-mode=importlib -q -p no:cacheprovider providers/fenicsx/tests tests/test_pde_contracts.py tests/test_spatial_core.py tests/test_lifecycle_engine.py` — PASS, 61 passed (16 real FEniCSx/PETSc solves)
command: `PYTHONPATH=src python -m pytest ... tests/test_core_guards.py -k dependenc` — PASS, 6 passed
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI (CI has no FEniCSx environment).

### Readiness
Gate A-F executed for real. Forge takes its own mesh/material/time/
environment/lifecycle records, runs FEniCSx/PETSc, and returns
provenance-bound BIG 7 fields; the solver holds no scientific authority.
BIG 9 not started.

## 2026-09-25 BIG 7 — Field + Mesh Core (BUILD phase)

### Pre-check
BIG 6 re-review at `e70cc2d`: no spatial blocker; found a real ODE bug (after
a segment with an interior output time, the next segment restarted from the
last OUTPUT state instead of the breakpoint state). Fixed in `ee7dbcb` with a
ramp test; `compare_executions` now requires equal output keys and compares
trajectories.

### Architecture
- Reuses Core spatial authority: `scientific.fields.UnstructuredMesh`
  (byte-content fingerprint), `data.mesh.UnstructuredMeshData` (validation,
  canonical metres), `FieldDefinition`/`FieldValue`/`FieldRecord`.
  `engcore.spatial` adds tags, facets, groups, frames, richer field
  semantics, material binding and mappings.
- Environment: gmsh 4.15.2 and meshio 5.3.5 installed this session
  (`pip install gmsh meshio`); gmsh needed system GL libraries
  (`apt-get install libglu1-mesa libxcursor1 libxinerama1 libxft2`).
  Declared as optional extra `mesh`.
- Failed approaches: meshio Gmsh-4 writer needs entity tables matching
  geometrical tags (KeyError) -> Gmsh 2.2 format used; OCC bounding boxes are
  padded (~1e-7) so a 1e-9 tolerance found no boundary curves -> tolerance
  1e-5*min(L,H) and empty sides refused; Core bulk encoder refuses `<d`
  buffers from Gmsh -> native byte order normalized at the mesh boundary.

### Scientific review
BIG 7 review: PASS WITH NON-BLOCKING GAPS (no BLOCKER). Fixed anyway:
hand-built regions must match a declared group; meshio read refuses dropping
non-zero z; group dimensions must be cell or facet; duplicate facets
refused; `to_core` refuses tensor/mapped/resolved/assumed fields; P1
interpolation requires P1 (lagrange/1/C0) data. Not re-reviewed.

### Open non-blocking gaps
- Facets are not checked to lie on the outer boundary (interfaces allowed);
  BIG 8 must not treat every facet group as an outer boundary.
- One cell type per mesh; hexahedral facets unsupported; no 3D measures.
- Gmsh determinism only shown for one version/platform; BIG 8 must bind to
  mesh digest, not generator options.
- No conservative cell->cell remap; P1 interpolation is O(N*M) brute force.
- Coordinate frames: cartesian only, no declared transforms between frames.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/spatial src/engcore/numerical` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_spatial_core.py tests/test_numerical_foundation.py tests/test_materials_engine.py tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_core_api_layering.py tests/test_field_coefficient_spike.py tests/test_field_composition.py tests/test_field_ir_ceiling.py tests/test_field_profile_limit.py tests/test_field_profiled_conditions.py tests/test_field_profiles.py tests/test_field_records.py tests/test_field_values.py` — PASS, 346 passed
command: `PYTHONPATH=src python -m pytest ... tests/test_core_guards.py -k dependenc` — PASS, 6 passed
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI.

### Readiness
Exact meshes, regions/boundaries, unit-aware framed fields, safe mappings
and material bindings exist independently of any PDE solver. BIG 8 not started.

## 2026-09-25 BIG 6 — Mathematical / Numerical Foundation (BUILD phase)

### Pre-check
BIG 5 re-review at `05c4b2c`: no numerical blocker; one HIGH path fixed first
(interpolation between ASSUMED points was labelled INTERPOLATED -> now
refused; wrong-dimension conditions are inadmissible instead of raising).

### Architecture
- Existing numerical authority found and reused: `scientific.solvers.protocol`
  (SolverIdentity, SolverSettings, ConvergenceState, RawSolverOutput),
  `scientific.numerics` (health, conditioning, stability),
  `solvers.admission.require_finite`. `engcore.numerical` is a kernel layer
  beneath domain solvers, not a parallel solver framework.
- Environment: numpy 2.4.6, scipy 1.17.1 present; SymPy 1.14.0 installed this
  session (`pip install sympy`) and declared as optional extra `symbolic`;
  `petsc` extra declared (petsc4py not installed). SUNDIALS: contract only;
  a first attempt probed `scikits.odes` and was removed because an unused
  import of an undeclarable distribution tripped the dependency guard and the
  provider would not use it anyway.

### Scientific review
BIG 6 review: CHANGES REQUIRED for one BLOCKER, fixed: LINEAR problem
identity with a declared digest did not hash its arrays (two matrices, one
identity) -> operand digest now always in identity. Also fixed: bridge keeps
failure reason/termination message; objective value no longer mislabelled
as residual; GMRES re-checks true residual; missing tolerance -> typed
refusal before work; minimize tolerances restricted per method; bitwise
determinism claim removed; PETSc preconditioner must be explicit; ODE output
times strictly after start and coverage verified. Not re-reviewed.

### Open non-blocking gaps
- Callable operators (ODE/root/optimization) have declared (attested) identity.
- `NOT_APPLICABLE` direct solves through Core admission are not yet tested end to end.
- Sparse problems > 2000 unknowns report no condition estimate.
- No DAE execution; SUNDIALS/PETSc execution not exercised here.
- Event *detection* (state-dependent events) is not supported; only declared
  breakpoints are bridged.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/numerical src/engcore/materials` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_numerical_foundation.py tests/test_materials_engine.py tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_core_api_layering.py tests/test_min_foundation_electrothermal.py` — PASS, 201 passed
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_core_guards.py -k dependenc` — PASS, 6 passed (earlier FAIL on undeclared `scikits`, fixed as above)
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI, PETSc/SUNDIALS execution.

### Readiness
Linear (3 providers), nonlinear (SymPy operator, 2 methods), ODE (2 methods,
BIG 2 window, BIG 5 material parameter, breakpoint bridging) and optimization
execute through provider-neutral contracts with fail-closed diagnostics.
BIG 7 not started.

## 2026-09-25 BIG 5 — Scientific Data + Materials (BUILD phase)

### Pre-check
BIG 4 re-review at `a2578a6`: PASS WITH NON-BLOCKING GAPS, no materials
blocker. Its MEDIUM items (per-input + state applicability; chain state link)
were fixed inside BIG 5's identity design.

### Architecture decisions
- `scientific.knowledge` is the data authority (claims, sources, snapshots,
  ingestion receipts, supersession). BIG 5 adds no source/claim/dataset record;
  it binds claims to exact material + applicability and resolves them.
- Constitutive models (e.g. `domains/electrical/material.py` R(T)) stay
  `ScientificModelDefinition`; `materials` holds sourced data only.
- Source alignment decision: `KnowledgeSource` is canonical for scientific
  data; `EnvironmentSource` stays an environment-input record. Both are read
  through `SourceIdentity` (a view). A serialized merge is deferred; it would
  change the `environment_source` contract and needs an explicit decision.
- Applicability is identity: `DegradationModelIdentity.applicability` and
  `.state_ranges` are serialized fields, so changing authorization changes
  the digest (replaces the BIG 4 "bounds not in identity" gap).

### Scientific review
BIG 5 review: CHANGES REQUIRED for one HIGH finding, fixed: interpolation
mixed units across tabulated points (now all positions in the state
condition's unit; test with degC/K points). Also fixed: ASSUMED datum now
resolves as ASSUMED, breakpoints dimension-checked at construction. Not re-reviewed.

### Open non-blocking gaps
- No production (non-test) participant yet constructs `MaterialState` and
  calls `resolve`; the closed material loop is proven in tests with a
  reference insulation participant. Domain physics adoption is future work.
- Removing one of two conflicting data turns UNKNOWN into KNOWN (refusal to
  arbitrate); should be reconciled with "removing evidence must not increase
  assurance" via `scientific.knowledge.conflicts`.
- Only single-variable LINEAR interpolation; no multi-variable tables, no
  explicitly authorized extrapolation.
- Fixture data are illustrative (issuer says so); no real open dataset is
  ingested yet (NIST/NASA/PyBaMM providers are future adapters).
- `QuantityHistory.integrate` still labels its bound STANDARD (BIG 2 gap).

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/materials src/engcore/scenarios src/engcore/domains/battery/aging.py src/engcore/domains/corrosion src/engcore/domains/hygrothermal` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_materials_engine.py tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py tests/oracles/test_oracle_battery.py` — PASS, 300 passed
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI.

### Readiness
A material property resolves from exact identity/state/source/applicability
and changes future computation (moisture -> conductivity -> heat flux).
BIG 6 not started.

## 2026-09-25 BIG 4 — Lifecycle / Degradation Engine (BUILD phase)

### Pre-check
`forge-scientific-review` re-run on BIG 2 + BIG 3 at `5584c57`: PASS WITH
NON-BLOCKING GAPS, no lifecycle blocker. Its advice (bind environment digest
in lifecycle records; do not treat SAMPLED as evidence) is built into BIG 4.
Open from it: required-kind placeholders carry empty source/classification
(explicit, but not a named "unsourced" label).

### Architecture
- `engcore.scenarios.lifecycle`: contracts + `evaluate_degradation`,
  `carry_forward`, `LifecycleChain`, `run_lifecycle`. Reuses
  `InitialStateDefinition/Value/Receipt`, `StateTransitionReceipt` end values,
  `MultiphysicsRuntime.run(initial_state=...)`, `Timeline` histories and
  `EnvironmentTimeline`; no new timeline/state/provenance authority.
- `EnvironmentTimeline.window_mean` (interval channels only; affine allowed;
  uncertainty UNKNOWN with the correlation-free bound stated in notes).
- Reference probes (uncalibrated, not validated): `domains/battery/aging.py`
  `CalendarCycleCapacityFade`; `domains/corrosion/thickness_loss.py`
  `LinearDoseThicknessLoss`. Chosen because they differ in drivers (mean
  temperature + cycle count vs. wetness + chloride doses) and state
  (capacity vs. thickness). `domains/**` is outside the certified core; no
  pinned file changed.

### Closed-loop proof (executed)
Three one-day windows through the real `MultiphysicsRuntime`: battery
capacity fades each window and the next window's state-of-charge swing
(2 A * 24 h / capacity) grows accordingly; wall thickness decreases and the
next window's heat flux (k dT / thickness) grows. `LifecycleChain.verify`
confirms every window acknowledged the degraded state.

### Scientific review
BIG 4 review: no BLOCKER; findings fixed: (1) verify ignored uncertainty,
(2) window_mean labelled a bound as STANDARD, (3) empty applicability meant
"everywhere", (4) chains could mix models, (5) executor could run another
window, (6) carry_forward could drop degraded state. Fixes tested; not re-reviewed.

### Open non-blocking gaps
- Applicability bounds are not part of `DegradationModelIdentity`; two models
  differing only in bounds share an identity (found by a failing test).
- `QuantityHistory.integrate` (BIG 2) still labels its correlation-free bound
  STANDARD (notes say UPPER BOUND); `window_mean` now uses UNKNOWN — align.
- Prior state is not range-checked (e.g. non-positive thickness).
- No uncertainty propagation through degradation models (always UNKNOWN).
- Loop is per participant; multi-participant/multi-model lifecycles and
  degradation inside a single long run (sub-window feed-forward) are not built.
- Point-sample channels give no dose/mean by design; lifecycle needs interval data.
- `EnvironmentSource` vs P4 dataset provenance alignment still open.
- Reference probes: linear/window-additive forms, Jensen gap, uncalibrated.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/scenarios src/engcore/domains/battery/aging.py src/engcore/domains/corrosion` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_lifecycle_engine.py tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py tests/oracles/test_oracle_battery.py` — PASS, 281 passed
command: `PYTHONPATH=src python -m pytest ... tests/oracles/test_oracle_battery.py tests/test_solver_lifecycle_state_isolation.py tests/test_world_runtime_sprint1.py` — PASS, 130 passed
command: `PYTHONPATH=src python -m pytest ... $(ls tests/test_*battery*.py)` — INVALID: glob matched nothing, pytest collected the whole tree and stopped on 6 known duplicate-basename collection errors (2 skipped). Not a test result.
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 149 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI.

### Readiness
Closed loop demonstrated: Time + Environment + Usage/Cycles -> Degradation ->
State transition -> changed future physics. BIG 5 not started.

## 2026-09-25 BIG 2 gap closure + BIG 3 — Environment Engine (BUILD phase)

### BIG 2 gaps closed
- Same-instant: `TimePoint` stores exact rational seconds from
  `repr(magnitude) * repr(unit factor)` (`SAME_INSTANT_RULE`); `0.1 hour ==
  360 s`, `360.0000000000001 s != 360 s`, no epsilon. Known limit (fail-closed):
  non-decimal magnitudes (1/3 hour) do not merge with 1200 s.
- Input ownership: first attempt stored `input_series_digests` on the
  timeline; the re-review showed it was forgeable (any caller could supply a
  digest). **Failed approach, removed.** Now `input_value_at(scenario, ...)`
  recomputes the presented scenario's digest and reads its composed schedule.
- Mistake recorded: removing a helper by slicing to the next `def` deleted the
  `SAME_INSTANT_RULE` block; restored in a follow-up commit.
- BIG 2 re-review verdict: no blocker for BIG 3 after the ownership fix.

### BIG 3 architecture
`src/engcore/scenarios/environment.py` — see ACTIVE_PLAN BIG 3 checklist.
Reuses `Timeline`, `TimePoint`, `TimeWindow`, EXPOSURE `QuantityHistory`,
scenario digest and `NamedQuantity`; adds no clock or state authority.

### BIG 3 scientific review
First review: CHANGES REQUIRED. Fixed: B1 (BLOCKER) LINEAR interpolated across
a discontinuity exactly at the upper sample; N1 circular kinds (wind direction)
now refuse LINEAR; N2 each value carries its source classification; N3
`verify_state` re-derives a deserialized state; N4 `source()` raised
StopIteration. Fixes covered by tests; not re-reviewed.

### Open non-blocking gaps (BIG 2 + BIG 3)
- `required` pairs have no context; a channel in another context satisfies
  coverage (its own value still appears under its context).
- `EnvironmentSource` is a new source-identity record; align with P4 dataset
  provenance/licensing when that lands.
- No interpolated dose from point samples (deliberate); lifecycle needs interval data.
- No spatial interpolation between locations; one timeline basis only.
- Markers-before-order-sensitive precedence at a shared instant is a convention.
- `canonical_digest` duplication (frozen Core decision needed).
- Runtime does not emit/restore `TimelineCheckpoint`s.

### Verification (BUILD-phase smoke only)
2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/scenarios` — PASS
command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_environment_engine.py tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py` — PASS, 228 passed (includes two executable environment scenarios: coastal exposure day, climb profile)
command: `PYTHONPATH=src python tools/forge_check.py --changed` — PASS, 40 passed
command: `git diff --check` — PASS
NOT RUN: `forge_check.py --regression`, FAST, SCIENTIFIC, mutation shards,
recertification, full suite, CI.

### Readiness
BIG 3 produces a deterministic, provenance-bound environmental history
(`EnvironmentTimeline.history/state_at/dose`, digest-bound to scenario,
timeline and sources). Ready to start BIG 4 Lifecycle.

## 2026-09-25 BIG 2 — Time Engine foundation (BUILD phase)

Strategy change: build the big architecture first; only focused smoke checks
during the build. The full FAST / SCIENTIFIC / mutation / recertification
campaign is deferred until after the architecture, real scenarios, a
scientific/numerical review and a stale-test audit.

### Architecture added

`src/engcore/scenarios/timeline.py` (non-Core package `scenarios`, which is
the existing transient authority; nothing new in the frozen Core):

- `TimeBasis` (ELAPSED with a named origin, or ABSOLUTE_UTC with the fixed
  epoch; no default clock), `TimePoint` (cross-basis ordering refused),
  `TimeWindow` (HALF_OPEN = scenario segment ownership, CLOSED for horizons).
- `TimelineEvent` + `order_events`: synchronization markers commute;
  DISCONTINUITY / STATE_CHANGE_REQUEST / TERMINATION at a shared instant need
  explicit distinct sequences or are refused. Events are markers, not evidence.
- `QuantityHistory` (USAGE/EXPOSURE, piecewise-constant only): gaps are
  UNKNOWN; integrals over gaps or affine units are UNKNOWN; the integral
  uncertainty is the correlation-free bound sum(sigma_i*dt_i), labelled an
  UPPER BOUND, source kind carried only when shared.
- `CycleHistory`: indices start at 0 and never skip; counts outside the
  recorded span are UNKNOWN; partial cycles are listed, never fractionally counted.
- `Timeline`: binds a `ScenarioSpecification` digest (`from_scenario`) and one
  `MultiphysicsRunRecord` (`bind_run`, records `run_id`); holds existing
  `StateTransitionReceipt`s verbatim and enforces per-participant digest and
  time chaining; every receipt must carry the timeline's scenario digest.
  `state_at` is KNOWN only at recorded boundaries.
- `input_value_at`: unsupported interpolation, method mismatch and LINEAR
  across a declared discontinuity are refused.
- `TimelineCheckpoint` (prefix digest + existing `CheckpointRecord`s; refused
  inside a record window, at an order-sensitive event, or for a participant
  state the timeline has no record of) and `compare_replay` (refuses a prefix
  with no execution-produced record; classified
  `replay_consistency_not_validation`).

### Scientific review

`forge-scientific-review` (read-only, no tests executed) returned CHANGES
REQUIRED on the first cut. Fixed: (1) scenario/run binding bypass via empty
digests and cross-run mixing; (2) unrecorded time counted as zero cycles;
(3) integral bound mislabelled / promoted to COMBINED; (4) checkpoints for
unrecorded participant state; (5) replay passing on declared-only content and
prefix omitting history kind/unit/cycle kind/horizon end/checkpoints;
(6) checkpoint ambiguity check only in one constructor; (8, partial) reached
event instant not checked against its schedule. The fixes were not re-reviewed.

### Open design gaps (not fixed; record before BIG 3 consumes the timeline)

- Same-instant grouping uses exact float seconds after unit normalization;
  0.1 hour vs 360 s may differ in the last ulp and escape the ambiguity check.
- Markers are sorted before order-sensitive events at the same instant; that
  precedence is a convention, not a declared rule.
- `input_value_at` does not verify the series belongs to the bound scenario.
- `canonical_digest` duplicates `sria/decision/replay.py` and
  `claims/_records.py`; consolidating into `scientific.serialization` touches
  frozen Core and needs a freeze decision.
- The integral treats each entry as exactly constant; representation error is
  not quantified (stated in the uncertainty notes, not modelled).
- The runtime does not yet emit `TimelineCheckpoint`s or restore from them;
  only one basis per timeline (no declared basis mapping / multi-rate).

### Verification (BUILD-phase smoke only)

2026-09-25
command: `PYTHONPATH=src python -m compileall -q src/engcore/scenarios`
result: PASS

command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q -p no:cacheprovider tests/test_time_engine.py tests/test_stateful_multiphysics_runtime.py tests/test_scenario_contracts.py tests/test_multidomain_science_hardening.py tests/test_core_api_layering.py tests/test_system_topology.py tests/test_min_foundation_electrothermal.py tests/test_electrothermal_vertical.py`
result: PASS — 194 passed (34 in `test_time_engine.py`)

command: `PYTHONPATH=src python tools/forge_check.py --changed`
result: PASS — 40 passed (architecture/layering gate set)

command: `git diff --check`
result: PASS

command: `PYTHONPATH=src python -m pytest --import-mode=importlib -q tests/test_core_freeze_*manifest.py`
result: FAIL — 15 failed, identically on clean `main` @ `2b76017f` (stash
test). Cause: this session's shallow clone lacks historical commits the freeze
verifiers `git show` (e.g. `af43c896`). Environmental, not caused by BIG 2.

NOT RUN: `forge_check.py --regression`, FAST tier, SCIENTIFIC tier, mutation
shards, hardened-core recertification, full repository test suite, CI.

### Next BIG step

BIG 3 — Environment Engine: provider-neutral `EnvironmentState` /
`EnvironmentTimeline` built on `Timeline` + `QuantityHistory(EXPOSURE)`, with
source, units, uncertainty, interpolation and validity bound to every
environmental quantity. Close the timeline gaps above that BIG 3 depends on
(scenario ownership of input series; same-instant tolerance) first.

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
