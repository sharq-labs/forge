# Post-merge remediation, 2026-10-18: master defect table

Source revision: `337519d1944bd52c5711a657a926ad855ac8d868` (origin/main, PR #167). Worktree `D:/forge-main-337519d1`.

All evidence below is **static** (source reading, `git` history, hand derivation, one pure-`Fraction` replay).
No pytest, no solve, no provider workload was run. Rows marked "census" come from four read-only review agents
and were not re-derived line by line in this session, except where "spot-checked" is stated. Import-time
discovery was attempted for A1 and could not run: on this host `import pint` / `import scipy.sparse` do not return
(the import wedge recorded for this machine; ~25 idle `python.exe` processes from other sessions are present).

Status vocabulary: FIXED / VERIFIED, FIXED / NOT RUN, CONFIRMED / UNFIXED, INVESTIGATION REQUIRED,
OWNER DECISION REQUIRED, SCIENTIFICALLY UNVERIFIED, CERTIFICATION PENDING.

## Master table

| ID | Component | Defect | Sev | Evidence | Target files | Proposed fix | Status |
|---|---|---|---|---|---|---|---|
| A1 | Model discovery guard | `EXPECTED_MODELS = 19`; tree has 20 (`thermal.conduction1d.transient_piecewise_linear@0.1.0` added by M1C). Reserving 16, conditions 96, reserved 63, solvers 11 do not move | Med (red guard) | CONFIRMED_FROM_CODE (static count: 19 at `89b9e7c3`, 20 at HEAD; diff adds one construction, no `prepare`/`supports`) | `tests/test_core_guards.py:199` | `docs/work/proposals/A1_core_guards_model_count.patch` (19 -> 20), not applied | OWNER DECISION REQUIRED (OD-31) / CERTIFICATION PENDING |
| A2 | Forward-tear guard (OD-26) | Existing test builds a mixed-dimension plan; `FixedPointCouplingPlan.__post_init__` refuses it at `dataclasses.replace`, before `runtime_equivalent` -> the guard is never reached. Test-design defect; the guard is defensive code reachable only by a tampered/deserialized-unchecked record | Low | CONFIRMED_FROM_CODE (ids sort `electrical_dc:` < `resistance-tcr-` < `thermal-lumped-`; tampered order P,E,T makes heat edge forward) | `tests/test_phase2_review_regressions.py` | New tampered-record test added; original kept for owner decision | FIXED / NOT RUN (new test); OWNER DECISION REQUIRED (old test) |
| A2b | `runtime_equivalent` trusts frozen plan | A tampered plan with mixed dimensions whose tears are all backward is not re-validated | Low | CONFIRMED_FROM_CODE | `systems/electrothermal/runtime_adapter.py:153-181` | Re-validate via `type(plan).from_dict(plan.to_dict())` or an explicit check; certified file -> OD-3 | CONFIRMED / UNFIXED |
| B1a | MultiscaleAuthority identity (OD-30) | `initial_fast_state` not in identity payload; two authorities differing only in it share `identity_digest` (request, plan, replay identity) | High | CONFIRMED_FROM_CODE (spot-checked `authorities.py:462-470`) | `system_runtime/authorities.py` | Same payload shape, corrected value: `declared_fast_state` is the authority's own declaration (`MultiTimescaleRuntime.declared_fast_state_digest`); an authority declaring none over a never-run runtime keeps its digest; no version key (it would move every digest). Flagship `cell-cooling-aging` digest moves on regeneration; committed bundles still verify | FIXED / NOT RUN / CERTIFICATION PENDING |
| B1b | same | Payload embeds runtime's current `declared_fast_state` -> digest depends on whether a shared runtime ran before construction | High | CONFIRMED_FROM_CODE (census) | `authorities.py:462`; `multiscale/runtime.py:333,346,499,504` | Same fix as B1a | FIXED / NOT RUN / CERTIFICATION PENDING |
| B1d | FAILED vs REFUSED | Pre-run identity refusals reported FAILED in both authorities | Low | CONTRACT_CONFLICT (weak) | `authorities.py` | Pre-run -> `refused`, post-run mismatch stays `failed` | OWNER DECISION REQUIRED (OD-30) |
| B2a | Fast-system inner runs (OD-29) | `run_ids` / `run_digests` / `series.source_digest` never resolved; echoed digests can be copied from the request; a ghost run digest passes outer admission | High | CONFIRMED_FROM_CODE (census; attack inferred, not executed) | `multiscale/runtime.py:439-487`, `multiscale/fast.py` | Versioned FastSystem contract returning resolvable inner records | OWNER DECISION REQUIRED (OD-29) |
| B2c | Flagship cooling fast system | Inner runs use the plant's build-time scenario digest, never compared with `request.scenario_digest` | Med | CONFIRMED_FROM_CODE (census) | `flagships/forge_flagships/battery_cooling.py:215,279,372,572` | Pass/compare the request scenario | CONFIRMED / UNFIXED |
| B2d | Provider refs side channel | Provider refs reach the node through `fast.refs[...]`; pybamm refs carry an empty record digest | Med | CONFIRMED_FROM_CODE (census) | `battery_cooling.py:387-397`; `system_runtime/executor.py:418-432` | Derive refs from resolvable inner records | CONFIRMED / UNFIXED |
| B3a | MultiphysicsAuthority (OD-27 gap) | Authorized scenario read from mutable `call.context` at execute; nothing snapshotted at preflight (MultiscaleAuthority does snapshot) | Med | CONFIRMED_FROM_CODE (census) | `authorities.py:107-111,228-231,277` | Snapshot per node at preflight, compare at execute (un-preflighted direct calls keep OD-27 only) | FIXED / NOT RUN / CERTIFICATION PENDING |
| B3c | Held checkpoint cleared early | Fresh stage clears the held checkpoint before the run is admitted (conservative direction) | Low | CONFIRMED_FROM_CODE (census) | `authorities.py:643-681` | Clear after admission or fix the docstring | CONFIRMED / UNFIXED |
| B3d | `initial_slow` digest | Omits domain keys; depends on dict order | Low | CONFIRMED_FROM_CODE (census) | `authorities.py:464-469` | Hash sorted `{domain:{var:value}}` (with B1 version bump) | OWNER DECISION REQUIRED (with OD-30) |
| C1-1 | Newton `_EVALUATION_ERRORS` | `ValueError` catch swallows programming errors (shape mismatch, `LinAlgError` is a `ValueError`) -> DIVERGED/NON_FINITE instead of propagating | Med | CONFIRMED_FROM_CODE (spot-checked `nonlinear.py:98,137,346`) | `numerical/nonlinear.py` | Narrow to `ArithmeticError` + exact-type `ValueError` with a CPython `math`/`cmath` domain text (3.14 texts probed on this interpreter) | FIXED / NOT RUN |
| C1-2 | Armijo trial points | A bug firing only at trial points is backtracked like a domain violation; the solve can end CONVERGED with one warning | Med | CONFIRMED_FROM_CODE (census) | `nonlinear.py:234-250` | Same narrowing; count trial failures | FIXED / NOT RUN |
| C1-3 | Robust chain / acceptance | Programming errors re-run across chained methods; `acceptance_measure` mapped them to `inf` | Med | CONFIRMED_FROM_CODE (census) | `numerical/robust.py:166-183`; `nonlinear.py` `acceptance_measure` | Follows C1-1 (chain needs no change: provider now raises) | FIXED / NOT RUN |
| C1-4 | Initial-point failure | Labelled DIVERGED with zero iterations | Low | CONTRACT_CONFLICT: `tests/test_phase3_br13_numerical_stability.py::test_a_non_finite_residual_is_a_classified_numerical_failure` pins DIVERGED at the initial point | `nonlinear.py:260,323` | FAILED + distinct reason; needs that test changed with it | OWNER DECISION REQUIRED (OD-32) |
| C1-5 | Recorded condition | Recomputed with default 1e12, not the declared limit | Low | CONFIRMED_FROM_CODE | `nonlinear.py` `diagnostics()` | Classify against `min(declared condition_limit, 1e12)`: a tighter limit is the stated bar, a looser one never upgrades the label (review M1: policy is not evidence) | FIXED / NOT RUN (still evaluated at the last Jacobian, x_{k-1}) |
| C2-1 | `residual_norm` meaning | Relative 2-norm, absolute 2-norm and L-inf share one key | Med | CONFIRMED_FROM_CODE (census) | `numerical/providers.py`, `nonlinear.py`, `core.py:589` | Add `residual_measure` label: changes `NumericalDiagnostics` serialization of every record (certified `core.py`) | OWNER DECISION REQUIRED (OD-32) |
| C2-2 | Linear providers | No `RESIDUAL_IS_NOT_AN_ERROR_BOUND` note (Newton has it) | Low | CONFIRMED_FROM_CODE (census) | `providers.py` | Add the note: changes every linear record's digest; the constant lives in uncertified `health.py`, which certified `providers.py` may not import | OWNER DECISION REQUIRED (OD-32) |
| C2-3 | Singular `spsolve` | Exactly singular factor reported as "residual check failed" | Low | CONFIRMED_FROM_CODE | `providers.py` `SciPyLinearProvider` | Non-finite SuperLU solution -> FAILED "numerically singular matrix"; warning not suppressed (`catch_warnings` is process-global, unsafe under concurrent Jacobi); single `splu` deferred to F1-c | FIXED / NOT RUN / CERTIFICATION PENDING |
| C2-4/5 | GMRES stop; unresolved conditioning | Correct: non-converged GMRES cannot be CONVERGED; unresolved never reported well-conditioned | - | CONFIRMED_FROM_CODE (census) | - | - | no defect |
| C3-1 | Interface "oriented" residual | Algebraically equals the unsigned mapping residual; cannot detect a wrong normal/orientation | Med | CONFIRMED_FROM_CODE (census, algebra) | `execution/multiphysics/mapping.py:983-1011` | Relabel in provenance (record identity, certified file) or add an independent receiver-flux check. Limitation now pinned by `test_the_oriented_integral_residual_is_not_an_orientation_check` | OWNER DECISION REQUIRED (OD-32) |
| C3-2 | Interface plane geometry | `plane_origin/u/v` only check normals; the mapping assumes both meshes' (x, y) are the plane's (u, v) | Low | Downgraded: both conventions must declare the same `coordinate_frame` (`interface_transfer.py:63`), so an axis swap needs a false frame declaration. Assumption undocumented | `scientific/fields/interface_transfer.py` | Document the chart assumption (not edited here: `scientific/` docstrings are string-count pinned) | CONFIRMED / UNFIXED (doc) |
| C3-3 | CONTINUOUS vs EQUAL_AND_OPPOSITE | Same sign rule for both | - | Not a defect: flux-vector continuity gives q.n_t = (n_s.n_t)(q.n_s), which is the applied `so*to*sign(n_s.n_t)` for both relations; existing parametrized test pins the four cases | - | - | no defect |
| C3-4 | Conservation mechanics | Exact overlap weights, partial-coverage refusal, no rescaling: correct | - | CONFIRMED_FROM_CODE (census) | - | - | no defect |
| C3-5 | `interface_flux_balance` | IndexError on a window with no iterations | - | Not reachable: `CouplingWindowRecord.__post_init__` refuses an empty `iterations` (`scientific/multiphysics/report.py`) | - | - | no defect |
| D1-1 | M1C BE/FV assembly | Matches `C_i(T^{n+1}-T^n)/dt = Q_{i-1/2}-Q_{i+1/2}+S_i`; series resistance, half volumes, Neumann sign, Dirichlet reaction correct | - | CONFIRMED_FROM_CODE (census, hand derivation) | - | - | no defect (SCIENTIFICALLY UNVERIFIED: tests NOT RUN) |
| D1-2 | M1C energy admission | Energy check is algebraically the row residual; cannot catch a wrong C or g | Med | CONFIRMED_FROM_CODE (census) | `conduction1d_transient_fv.py:425-440` | Independent recomputation in tests (hand-integrated C with an area jump; exact two-material steady state) | FIXED / NOT RUN (test-side; the in-solver check stays a consistency check) |
| D1-3 | M1C tolerance scale | Scaled by absolute energy `sum|C*T|` (0 K reference): accepted imbalance grows with temperature level | Med | CONFIRMED_FROM_CODE (hand example: 1e-7 J leak in a closed slab admitted at rtol 1e-6) | `conduction1d_transient_fv.py` energy admission | `atol + rtol*max(sum|C*dT|, dt*(|boundary|+|sources|)) + 64*eps*dt*sum(|A||T|+|b|)` (no interior faces: they cancel and would grow with n; floor is machine precision, not the solver tolerance); `conservation_rtol` in (0, 1); implementation reference 0.1.0 -> 0.2.0 | FIXED / NOT RUN |
| D1-5 | M1C input boundary | Region/grid ends compared with exact float `==` after unit conversion | Low | CONFIRMED_FROM_CODE (census) | `:320,372` | Relative tolerance | CONFIRMED / UNFIXED |
| D3-1 | M1D | Not in this tree (`codex/m1d-adaptive-transient` 5fd797dd not an ancestor) | Info | CONFIRMED_FROM_CODE | - | Bounded integration plan | INVESTIGATION REQUIRED |
| D3-2 | Dual energy transfer | Piecewise-constant energy per length across a c*A change: uniform T not preserved after refine on heterogeneous material (global energy conserved, heat moved). M1D's `from_transfer` relies on it | High (for M1D) | CONFIRMED_FROM_CODE (census, hand derivation) | `numerical/vertex_state.py:430-453` | Optional declared `AmountDistribution1D` on `transfer_state` (split by integral of the storage weight); default and existing receipts unchanged. M1D must pass the c*A weight when it reconstructs temperature | FIXED / NOT RUN (primitive in M1B; M1D integration open) |
| D3-3 | Refine/coarsen round trip | Not the identity on dual energies; each cycle adds transfer diffusion | Med | CONFIRMED_FROM_CODE (census) | `vertex_state.py`, `mesh_adaptation.py` | Declare order; sibling-sum coarsening | CONFIRMED / UNFIXED |
| E1 | Window subdivision (OD-22) | Exact rational replay: 7 subdivisions without memory (final [7/4,2] is horizon-cut to 1/4 s), 4 with growth 2; `plan.py:407-411` contract supports 7; test asserts 8 since BR11 | Med (false red) | CONTRACT_CONFLICT, test side (census replay; assertion spot-checked) | `tests/test_multiphysics_window_control.py:298` | Test -> 7 with corrected comment: `docs/work/proposals/OD22_window_control_subdivisions.patch` (not applied); evidence `docs/work/proposals/od22_replay.py` (pure Fraction, re-derived in this session: 7 / 4) | OWNER DECISION REQUIRED (OD-22) |
| E2 | Electrothermal relaxation (OD-23) | `relaxation_factor` contradicts docstring, test_l3 and §12.10; no double relaxation today; adapter recomputes the relaxation formula post-run | Med | CONTRACT_CONFLICT | `systems/electrothermal/coupled.py`, `runtime_adapter.py` | MultiphysicsRuntime RelaxationPolicy as sole authority | OWNER DECISION REQUIRED (OD-23) |
| E3 | Self-loop edges (OD-24) | graph refuses; BR1 test expects lagged edge; plan.py docstring mentions self-loops | Med | CONTRACT_CONFLICT | `scientific/multiphysics/graph.py:319-324` | Keep refusal; rewrite the test to expect it | OWNER DECISION REQUIRED (OD-24) |
| E4-2 | IQN-IMVJ nested window | Outer staged approximation dropped without a log entry | Low | CONFIRMED_FROM_CODE (census) | `execution/multiphysics/acceleration.py:141-145` | `had_staged` captured before clearing, passed to `_discard` | FIXED / NOT RUN |
| E4-3 | `run()` finally | One participant's `finalize` raising skips the others and masks the original exception | Low | CONFIRMED_FROM_CODE | `runtime.py` (certified) | `_finalize_all`: every participant finalized; failures noted on the propagating exception, or raised together | FIXED / NOT RUN / CERTIFICATION PENDING |
| E4-4 | `_fail_closed_run` | Argument refusals before any participant call retire every participant | Low | CONFIRMED_FROM_CODE | `runtime.py` (certified) | `_participants_touched` flag: a refusal before the first participant call does not retire; everything else still does | FIXED / NOT RUN / CERTIFICATION PENDING |
| F1-a..d | Condition-number overhead | Dense SVD before every dense solve; sparse n<=1000 densified + SVD; n>1000 two LUs; Newton recomputes per iteration and on exit | Med | PERFORMANCE_HYPOTHESIS (call graph CONFIRMED_FROM_CODE) | `numerical/core.py:603-690`, `providers.py`, `nonlinear.py` | F1-d: exit diagnostic reuses the admission estimate when it is the same computation (same matrix object, same threshold) -- output-identical. F1-a/b/c and the per-iteration estimate: NOT changed (see "Proposals awaiting measurement") | F1-d FIXED / NOT RUN (not measured); F1-a/b/c CONFIRMED / UNFIXED |
| F2-1 | SparseFVProvider identity | Re-hashes module source (30.7 kB) and `_superlu` binary (426 kB) on every `.identity` access, ~4 per step | Low | PERFORMANCE_HYPOTHESIS | `conduction1d_transient_fv.py` | Computed once at import (same bytes, same digest); now names the code the process loaded, so an on-disk edit after import no longer reads as configuration drift | FIXED / NOT RUN (not measured) |
| F2-3 | Private SciPy import | `scipy.sparse.linalg._dsolve._superlu` at module top: a SciPy move breaks MODEL/REALIZATION import | Low-Med | SCIENTIFIC_RISK | `conduction1d_transient_fv.py` | Guarded import -> `available()` False, `unavailable_reason` recorded | FIXED / NOT RUN |
| F2-4 | Issued-record re-verification | Every step re-verifies all issued records: O(N^2) over N steps | Med | PERFORMANCE_HYPOTHESIS | `numerical/mesh_adaptation.py` `_IssuedRecords.verify` | NOT changed: incremental verification would stop detecting a later tamper of an older record (a weakening); needs a design decision and a measurement | OWNER DECISION REQUIRED (OD-34) |
| F3-1..4 | Multiphysics runtime | Quadratic window-control log scan; double checkpoint per window; overlap matrix and mesh fingerprint rebuilt per transfer; per-iteration diagnostics retained | Low-Perf | PERFORMANCE_HYPOTHESIS | `execution/multiphysics/runtime.py`, `mapping.py` | F3-1: reverse scan to the window's block (ordering invariant, output-identical). F3-2..4 NOT changed | F3-1 FIXED / NOT RUN / CERTIFICATION PENDING (not measured); F3-2..4 CONFIRMED / UNFIXED |
| X-1 | ACTIVE_PLAN | OD-28 row duplicated (old and updated text) | Info | CONFIRMED_FROM_CODE | `docs/work/ACTIVE_PLAN.md` | Drop the stale row | CONFIRMED / UNFIXED |

## Batch A result

| ID | Root cause | Files changed | Tests authored | Tests executed | Result | Remaining risk |
|---|---|---|---|---|---|---|
| A1 | M1C added a model; the exact-count guard was not moved (certification-pinned file) | `docs/work/proposals/A1_core_guards_model_count.patch` (new, not applied); `ACTIVE_PLAN.md` (OD-31) | none | none (import discovery blocked by host wedge) | OWNER DECISION REQUIRED / CERTIFICATION PENDING | Counts are static; confirm with `test_the_discovery_found_exactly_the_repository` once the host imports again |
| A2 | Test fixture is refused by the plan constructor before the guard; guard reachable only by a tampered record | `tests/test_phase2_review_regressions.py` (+1 test, `import copy`); `ACTIVE_PLAN.md` (OD-26 note) | `test_a_tampered_plan_with_a_forward_tear_is_refused_by_the_runtime_build` | parse only (`ast.parse`) | FIXED / NOT RUN | Old test still fails until owner decides; A2b (no re-validation of a tampered plan) open |

Detection argument for A2: with the forward-tear block removed, `runtime_equivalent(system, tampered)` continues to
`check_against` (the heat endpoint is not determined by a declared condition) and builds, so `pytest.raises(match="run
forward")` fails. The test also pins its own fixture (the constructor refuses the set; the edge is forward in the
derived order), so a change in id sorting or plan validation fails it loudly instead of letting it pass vacuously.

## Batch C result

| ID | Root cause | Files changed | Tests authored | Tests executed | Result | Remaining risk |
|---|---|---|---|---|---|---|
| C1-1/2/3 | `_EVALUATION_ERRORS` caught every `ValueError`, so shape mismatches, `LinAlgError` and caller bugs became NON_FINITE / backtracked trial points | `src/engcore/numerical/nonlinear.py` (not certification-pinned) | `test_newton_domain_errors.py`: allowlist guard (8 real interpreter errors incl. NaN-to-int), programming errors propagate (3 x 2 methods), Jacobian error, trial-point bug, chain, acceptance re-evaluation | `ast.parse` only | FIXED / NOT RUN | Allowlist is CPython-text-based; an unlisted domain text propagates (stricter). Every `ArithmeticError` is still classified (pre-existing, review N1) |
| C1-5 | Recorded condition used the undeclared 1e12 default | `nonlinear.py` | looser limit never upgrades (pin); tighter limit is the recorded bar (detects) | `ast.parse` only | FIXED / NOT RUN | Condition still evaluated at the last Jacobian (x_{k-1}) |
| C2-3 | Exactly singular SuperLU factor named "residual check failed" | `src/engcore/numerical/providers.py` (certified, already drifted) | `test_phase1_sparse_correctness.py::test_an_exactly_singular_sparse_direct_solve_is_named_singular_not_a_residual_failure` | `ast.parse` only | FIXED / NOT RUN / CERTIFICATION PENDING | MatrixRankWarning still emitted (process-global filter unsafe under concurrent Jacobi) |
| C3-1 | Oriented residual re-applies the contract sign | none (certified `mapping.py`) | `test_interface_flux_execution.py::test_the_oriented_integral_residual_is_not_an_orientation_check` (limitation pin) | `ast.parse` only | OWNER DECISION REQUIRED (OD-32) | No independent orientation check exists |
| C3-3, C3-5 | - | none | none | - | no defect (sign derivation; record invariant) | - |

Independent static review of the A+C diff (read-only agent): **PASS**, no BLOCKER/MAJOR. Acted on: M1 (looser
`condition_limit` upgraded the recorded label -> `min(limit, 1e12)`), M2 (`int`/`floor` of a NaN the residual
produced -> classified, with a test), M3 (comment), N2 (count text says "domain or range error"). N4 (old OD-26 test)
stays with the owner. Detecting tests per the review: Newton :136/:141/:149/:170/:176/:184, the tighter-limit
condition test, sparse singular; the allowlist, C3-1 and OD-26 tests pass on the pre-change tree by design.

## Batch D result

| ID | Root cause | Files changed | Tests authored | Tests executed | Result | Remaining risk |
|---|---|---|---|---|---|---|
| D1-3 | Energy admission scaled by 0 K-referenced energy | `domains/thermal_models/conduction1d_transient_fv.py` (not pinned) | `test_m1c_transient_fv.py`: datum invariance 300 vs 3000 K; 1e-7 J closed-slab leak admitted by the old scale, refused now; rtol bounds | `ast.parse` only | FIXED / NOT RUN | Balance check is still algebraically the row residual sum (D1-2): a consistency check, not independent verification. Floor dominates at large Fourier numbers (labelled) |
| D1-2 | No independent reference for heterogeneous C, g or steady state | tests only | hand-integrated C with an area jump + equilibrium; exact two-material steady state (300, 301, 301.3) K with reaction -5 W | `ast.parse` only | FIXED / NOT RUN (test-side) | No combined space-time MMS; spatial order still bounded only by ratio > 2.7 |
| D3-2 | M1B dual transfer splits amounts by length inside a dual; across a jump in c*A a uniform T becomes (300, 450, 257.1, 300) | `numerical/vertex_state.py` (not pinned): `AmountDistribution1D`, `transfer_state(distribution=...)`, receipt carries the whole distribution when declared | `test_m1b_vertex_dual_state.py`: length split characterised; weighted split keeps 300 K; coverage, construction and placement refusals | `ast.parse` only | FIXED / NOT RUN | The weight is a declared assumption not checked against registered storage; M1D (`codex/m1d-adaptive-transient`, not in main) must adopt it (OD-33) |

Independent static review of Batch D: **CHANGES REQUIRED** (1 MAJOR, 3 MINOR), all acted on. MAJOR: including
interior face powers in the exchange scale made the tolerance grow with node count, and sum|C*dT| + dt*|boundary|
double-counted; now the max of internal redistribution and external energy, faces excluded, with an honest rtol
comment. MINOR: receipt now carries the whole distribution (not a digest); weight unit normalized and refused when
unparsable; test docstring numbers corrected. NOTE acted on: implementation reference version bumped. Not acted on:
a test that equivalent unit spellings share one identity (pint's canonical string order unverified without running).

## Batch E result

| ID | Root cause | Files changed | Tests authored | Tests executed | Result | Remaining risk |
|---|---|---|---|---|---|---|
| E4-2 | `begin_window` cleared `_staged` before deciding whether anything was dropped | `execution/multiphysics/acceleration.py` (not pinned) | `test_phase3_br14_iqn_imvj.py`: staged drop is logged; nothing logged when nothing was staged | `ast.parse` only | FIXED / NOT RUN | New `imvj_discarded` event (and reworded reason) appears only in IMVJ runs with event alignment; no committed fixture combines them. No runtime-level IMVJ+event test (review MINOR-3) |
| E4-3 | `finalize` loop had no per-participant guard | `execution/multiphysics/runtime.py` (certified) | failing finalize does not skip the next; a failing finalize never replaces the window's exception (noted on it) | `ast.parse` only | FIXED / NOT RUN / CERTIFICATION PENDING | Pre-existing: a refusal between participant initialization and the main `try` (e.g. "unknown edges") still skips finalize (review MINOR-2). On the success path a provider's finalize failure now surfaces as `MultiphysicsExecutionError` with the original as cause |
| E4-4 | Every refusal retired the participants, including argument checks that ran no participant code | `runtime.py` (certified): `_participants_touched` flag; re-entrancy guard (review MINOR-1) | three pre-participant refusals leave the runtime usable; a refusal after initialization still retires; a nested run is refused and retires | `ast.parse` only | FIXED / NOT RUN / CERTIFICATION PENDING | The exempt span is verified statically only (review: no participant code before the flag) |
| E1 / OD-22 | Test expects 8; contract and an exact-rational replay give 7 | `docs/work/proposals/OD22_window_control_subdivisions.patch`, `od22_replay.py` (new, not applied) | none | replay script only (pure `fractions`) | OWNER DECISION REQUIRED | - |

Independent static review of Batch E: **PASS**, no BLOCKER/MAJOR; it re-derived 7 / 4 for OD-22 independently.
Acted on: MINOR-1 (a re-entrant `run()` could reset the outer run's fail-closed flag -> re-entrancy guard that
retires, with a test), NOTE (discard reason now names staged as well as carried). Recorded, not changed: MINOR-2
(pre-existing finalize gap before the main `try`; closing it re-indents a large certified block), MINOR-3 (no
runtime-level IMVJ + event test).

## Batch B result

| ID | Root cause | Files changed | Tests authored | Tests executed | Result | Remaining risk |
|---|---|---|---|---|---|---|
| B1a/B1b (OD-30) | The identity payload took `declared_fast_state` from the runtime as it stood at construction | `multiscale/runtime.py` (not pinned): pure `declared_fast_state_digest`, shared `_normalized_state`; `system_runtime/authorities.py` (certified): payload value is the authority's own declaration, fast state snapshotted, every returned record must declare the stated fast state | `tests/test_od30_multiscale_authority_identity.py` (new): differing fast states differ; history-independence; helper equals the runtime's own derivation; empty declaration keeps the pre-OD-30 value; misstated digest refused on the record; caller mapping mutation has no effect; runtime without the helper refused | `ast.parse` only | FIXED / NOT RUN / CERTIFICATION PENDING | Flagship `cell-cooling-aging` digest moves on regeneration; stored pre-OD-30 requests/checkpoints for it are then refused (`AUTHORITY_IDENTITY_MISMATCH`, fail-safe). B1d (FAILED vs REFUSED) and B3d (`initial_slow` keys) not changed |
| B3a | `MultiphysicsAuthority` read the authorized scenario from the mutable context at execute only | `authorities.py` (certified): per-node preflight snapshot, checked before and after `run_kwargs` | `test_system_runtime_scenario_identity.py`: scenario swapped after preflight is refused and nothing advances; an un-preflighted direct call keeps OD-27 only | `ast.parse` only | FIXED / NOT RUN / CERTIFICATION PENDING | Snapshot is per authority instance, not per request (two interleaving executors on one instance: OD-27 only) |

Independent static review of Batch B: **PASS**, no BLOCKER/MAJOR; it confirmed the helper is byte-identical to the
runtime's own derivation and that no existing multiscale test or committed bundle depends on the old value. Acted on:
MINOR-1 (stated fast state now enforced on every record, and snapshotted), MINOR-2 (pre-change-failing tests added; the
boundary test says it is one), NOTE-2/4 (docstring precision; B3a check also before `run_kwargs`). Recorded: NOTE-1
(per-instance snapshot), NOTE-3 (stored pre-OD-30 flagship requests/checkpoints are refused after regeneration).

Design decision taken (user instructed OD-30 to proceed): no `identity_version` key. A version key would move every
multiscale digest, including the ones that were already correct; keeping the payload shape and correcting the value
moves exactly the digests that misstated the fast state.

## Batch F result (no measurement was authorized or possible: no speedup is claimed)

| ID | Root cause | Files changed | Tests authored | Tests executed | Result | Remaining risk |
|---|---|---|---|---|---|---|
| F2-1 | Build identity re-hashed two files on every access | `conduction1d_transient_fv.py` | identity equals an independent recomputation of the same digest and reads no file per access | `ast.parse` only | FIXED / NOT RUN (not measured) | An on-disk edit after import no longer refuses as drift (that refusal named code the process was not running); stale `.pyc` with unchanged mtime/size still undetected, as before |
| F2-3 | Private SciPy import at module top | same | subprocess with the private module removed: model imports, provider unavailable with a reason | `ast.parse` only | FIXED / NOT RUN | - |
| F1-d | Exit diagnostic repeated the admission estimate | `numerical/nonlinear.py` | call-counting: one estimate when thresholds match; recomputed against the stricter bar when the declared limit is looser | `ast.parse` only | FIXED / NOT RUN (not measured) | Per-iteration estimate + LU (two factorizations) unchanged: proposal F1-d (rest) |
| F3-1 | Full-log scan per window | `execution/multiphysics/runtime.py` (certified) | none new (existing step-size-memory test covers the behaviour) | `ast.parse` only | FIXED / NOT RUN / CERTIFICATION PENDING (not measured) | Relies on the log-order invariant (proven statically by the reviewer) |

Independent static review of Batch F: **PASS**, no BLOCKER/MAJOR; the reviewer proved the F3-1 ordering invariant
and the byte-identity of the F2 digest. Acted on: MINOR-1 (docstring overclaimed "the code this process executes"),
MINOR-2 (a build-digest read failure at import now makes the provider unavailable instead of the module
unimportable), MINOR-3 (subprocess test timeout), NOTE (recorded condition is that of the Jacobian as admitted).

## Proposals awaiting measurement (Batch F; nothing below was changed)

Each needs a measurement on an un-wedged host before it is worth a certified-file change, and two need an
output-equality check because they could change the bits of an existing successful record.

| ID | Proposal | Why not done now | Measurement to decide it (cold and warm runs reported separately) |
|---|---|---|---|
| F1-a | Dense LU provider: `scipy.linalg.lu_factor` once, solve with it, condition by `gecon` on the same factors | Replaces the exact 2-norm number (SVD) with a 1-norm estimate: a semantics change to the recorded condition, certified `providers.py`/`core.py` | time of `condition_of` vs `np.linalg.solve` for dense n = 100, 500, 1000, 2000 at cond 1e2 / 1e8 / 1e14; fraction of `execute` time |
| F1-b | GMRES on sparse n <= 1000: stop densifying + SVD per call (report unresolved, or use the Arnoldi Hessenberg) | Changes a recorded exact number into unresolved/estimated (semantics); certified | same sizes, tridiagonal and 5-point Laplacian; GMRES time vs `condition_of` time |
| F1-c | Sparse direct n > 1000: one `splu`, solve with it, Hager on the same factor | `spsolve` (gssv, possibly UMFPACK) and `splu(...).solve` are not guaranteed bit-identical: must verify outputs equal on a corpus first; certified | factorization count (monkeypatch) and wall time, n = 2e3..2e5; byte-equality of `x` against the current path |
| F1-d (rest) | Newton: one factorization per iteration for both admission estimate and step | Same as F1-a/c (dense SVD vs LU estimate semantics) | per-iteration time split for n = 50, 500, 1000 with `condition_limit` declared |
| F2-4 | `_IssuedRecords.verify` incremental | Would stop detecting a later in-place tamper of an older issued record (tests pin detection): a weakening unless replaced by an equivalent (e.g. verify the ancestry an operation reads + a periodic full sweep) | step time at step 10 / 100 / 1000 of an M1C session; confirm O(N) per step |
| F3-2 | Pass outer checkpoints into `_window`; skip iteration-1 restore when nothing advanced | Restore/replay is part of the determinism contract; certified | checkpoint/restore counts and time per window, implicit + window control |
| F3-3 | Cache the conservative overlap matrix per (edge, source fingerprint, target fingerprint) for a run; memo mesh fingerprints | A cache keyed wrongly would reuse a stale overlap: needs the content-identity key reviewed; certified `mapping.py` | profile of `mapping.py` per transfer on 2D meshes of 1e3..1e5 cells |
| F3-4 | Keep only last-iteration mapping diagnostics (or a digest) | Changes `CouplingIterationRecord` content (record identity) | memory per run vs windows x iterations x edges |

## Commands to run once execution is authorized and the host imports again

```bash
python -B -m pytest -p no:cacheprovider -q tests/test_phase2_review_regressions.py
python -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"
python -B -m pytest -p no:cacheprovider -q tests/numerical/test_newton_domain_errors.py tests/test_phase3_br13_numerical_stability.py tests/numerical/test_robust_nonlinear.py
python -B -m pytest -p no:cacheprovider -q tests/numerical/test_phase1_sparse_correctness.py tests/test_interface_flux_execution.py
python -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py
python -B -m pytest -p no:cacheprovider -q tests/test_phase3_br14_iqn_imvj.py tests/test_multiphysics_window_control.py
python -B -m pytest -p no:cacheprovider -q tests/test_od30_multiscale_authority_identity.py tests/test_system_runtime_scenario_identity.py tests/test_system_runtime_multiscale_identity.py tests/test_multiscale_review_fixes.py
```
