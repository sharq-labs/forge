# Reviewer B — Numerical Analysis, Conservation, Mesh and Solver Semantics

Target: `D:/forge-main-337519d1` (HEAD `abed661f`). Read-only audit. No FORGE code was executed, no pytest was
run, nothing was imported from the repository. The scripts below are stdlib-only and ran under
`python.exe -I -S`. Their output is **independent derivation**. None of it is `EXECUTED_REPRODUCED`.

Scratch scripts (independent derivations):
- `b_dc_common_mode.py`: DC residual gate and KCL under a common-mode offset (exact `Fraction` arithmetic).
- `b_ftcs_window.py`: FTCS past r = 1/2, emulating `_BandedBackend.explicit_stepper` one operation at a time.
- `b_point_roundtrip.py`: round-trip of point ranges declared in mixed units (degC and K) in binary64.

Findings, ordered by severity: B-01 MAJOR, B-02/B-03/B-04/B-05 MINOR, B-06/B-07 OBSERVATION.

---

## B-01 — Material interpolation silently picks between conflicting tabulated sources

1. **ID** B-01 · `new_or_known`: **NEW** (I grepped the known-findings docs for "arbitrat" and "interpolat". The only hit is the BR15 table row that states the invariant.)
2. **Category**: Materials property evaluation / interpolation. Authority: source arbitration.
3. **File:line**: `src/engcore/materials/properties.py:272` (data sorted by `claim_id`), `:329-342` (point collection), `:347` (stable sort by position), `:348-353` (`below[-1]`, `above[0]`), `:363-367` (interpolated value).
4. **Governing contract**: module docstring `properties.py:14-15` says "two admissible data -> UNKNOWN (sources are not arbitrated)". `resolve` refuses that case at a tabulated point (`:319-321`). `docs/work/BR15_AUTHORITY_CLOSURE.md:54` classifies `materials/properties.py` as AUTHORITY_CRITICAL: "sources are never arbitrated". Test `tests/test_materials_engine.py:150` covers only the case where the state sits exactly on the point.
5. **Invariant violated**: "sources are never arbitrated" (BR15). The CLAUDE.md rule "Caller assertions ... are not scientific evidence" is also touched, because the ordering of an identifier decides which measurement is used.
6. **Root cause**: the interpolation branch builds `points` from every point datum along the rule's variable. It never checks whether two data share one position. `points.sort(key=p[0])` is stable, and `self.data` is sorted by `claim_id`. So among duplicates, `below[-1]` takes the datum with the lexicographically largest `claim_id` and `above[0]` takes the smallest. The other datum is dropped without any record.
7. **Minimal trigger**: one `MaterialPropertySet` containing an `InterpolationRule("k","temperature","linear")` and three data:
   - "a": a point at 300 K, k = 10 W/m/K
   - "b": a point at 300 K, k = 20 W/m/K, from a different source
   - "c": a point at 400 K, k = 30 W/m/K

   The state is T = 350 K. No guard refuses this. `KnowledgeSnapshot` (`scientific/knowledge/snapshot.py:21-34`) refuses only duplicate ids, and `MaterialPropertySet.__post_init__` refuses only a repeated `claim_id`.
8. **Expected vs observed**:
   - **Expected**: UNKNOWN. The bracket end at 300 K is contested, exactly as it is at T = 300 K.
   - **Observed** (traced by hand):
     - No datum admits 350 K, so `admitted` is empty.
     - All three data are points. After sorting, the order is (300,a), (300,b), (400,c).
     - `lo` is b, so the result is 20 + 0.5·(30−20) = **25 W/m/K, INTERPOLATED, status "known"**.
     - Datum a is not listed in `claim_digests`.
     - If the claim ids are swapped, the answer becomes 20.
   - At T = 300 K the same set returns UNKNOWN "several data admit this state; sources are not arbitrated". So moving the state one ulp turns a refusal into a known value.
9. **Independent reasoning**: linear interpolation between adjacent data is a function only when the abscissae are distinct. With repeated abscissae the bracket end has more than one ordinate. Picking one ordinate is arbitration, and here the tie-break is an identifier, not a scientific criterion. The refusal at the point (`:319-321`) shows the design treats coincident data as unresolvable. The interpolation branch contradicts that.
10. **Evidence class**: **SOURCE_PROVEN**. Path traced: `resolve` → `:309` → `:312-313` → `:322` → `:329-342` → `:345-353` → `:363-367` → `_result(..., INTERPOLATED, ...)`.
11. **Affected**:
    - Every consumer of `MaterialPropertySet.resolve` that accepts INTERPOLATED.
    - `spatial/fields.py:197-216` (`RegionMaterialMap.property_field` accepts any `status == "known"`).
    - `pde/cases.py:42,89` (accepts any known `ResolvedProperty`).
    - `materials/coverage.py:186`.
    - M1C (`conduction1d_transient_fv.py:137-139`) is not affected: it admits SOURCED only.
12. **False-support risk**: **medium**. The value is labelled INTERPOLATED and carries UNKNOWN uncertainty, so no uncertainty is invented. But a contested material value enters a PDE coefficient field as a known number, and the provenance names only one source.
13. **Replay/provenance**: `claim_digests` and `sources` omit the discarded datum. A replay reproduces the same arbitrary choice, and the record cannot show that a conflict existed.
14. **Compatibility**: a repair that refuses the case changes the outcome only for sets with coincident points. No serialization change is needed.
15. **Certification**: `src/engcore/materials/properties.py` **is in** `certification/current_core_v2.json`. A fix needs recertification (OD-3 path).
16. **Genesis impact**: none.
17. **Reproduction plan (NOT executed)**: one pytest function in `tests/test_materials_engine.py` style that builds the three data above and asserts `resolve("k", state(350 K)).status == "unknown"`. Cost is under 1 s. It currently gives `known`/25. It needs `--basetemp` on D: (memory note) and no network.
18. **Smallest repair (proposal)**: in `resolve`, after `points` is built, refuse when two points share a position (`p[0]` equal as `Fraction`), or at least when they share a position and their values differ. Return UNKNOWN with "several tabulated data at <x>; sources are not arbitrated". Apply the same rule to every point, not only the bracket ends: the bracket must also be adjacent.
19. **Owner approval**: yes. This is a change to a certified file (OD-3 recertification).
20. **Self-challenge**: "A property-set author should never put two conflicting data at one point." But the module already handles exactly that situation at the point itself. The set is built from a snapshot of independent sources, where coincident tabulations are normal (handbook against vendor). The defect is that the two branches of the same function disagree. **Survives.**

---

## B-02 — Mixed-unit point data turn into slivers and are skipped by interpolation (float `==` after conversion)

1. **ID** B-02 · `new_or_known`: **variant_of: D1-5** (float `==` after unit conversion). D1-5 is about the M1C region ends. This is a different site, with a different consequence: a sourced datum is silently left out of a bracket.
2. **Category**: unit conversion / exact comparison / interpolation.
3. **File:line**:
   - `src/engcore/materials/ranges.py:71-74` (construction), `:78` (`unit` is the lower bound's unit), `:80-82` (`is_point` uses float `==` after `magnitude_in`).
   - `materials/properties.py:331-333` (a non-point datum is skipped).
4. **Governing contract**:
   - `ranges.py:46-47`: "A point (lower == upper, both inclusive) is a valid range: the value a tabulated datum was stated at."
   - `properties.py:16-17`: interpolation runs "strictly between two tabulated points".
   - `InterpolationRule` docstring (`:176`): "Only LINEAR between adjacent point data".
5. **Invariant**: "Removing evidence must not increase assurance". A sourced datum is dropped without trace, and the answer is a confident interpolation that ignores it.
6. **Root cause**: whether a range is a point is decided by binary64 equality after an affine conversion. 26.85 degC and 300 K are the same temperature, but `Quantity(300,"K").magnitude_in("degC")` is (300 − 273.15) = 26.850000000000023, which is not 26.85. (This assumes pint's offset conversion `(v − offset)/scale`.)
7. **Minimal trigger**:
   - Datum M is declared as `ApplicabilityRange("temperature", lower=Quantity(26.85,"degC"), upper=Quantity(300,"K"))`. Construction succeeds because the upper bound converts above the lower one. `is_point` is False.
   - Two more point data sit at 280 K and 350 K, and a linear rule is declared.
   - The state is 310 K.
8. **Expected vs observed**:
   - **Expected**: interpolate between 300 K (M) and 350 K. Alternatively, refuse the ambiguous declaration.
   - **Observed**: M is skipped at `properties.py:332`. M does not admit 310 K. The result interpolates between 280 K and 350 K and ignores the sourced datum at 300 K, with no note.
   - In the opposite declaration order (lower in K, upper in degC), the range is refused at construction ("upper is below lower"). That direction fails closed.
9. **Independent derivation** (`b_point_roundtrip.py`), over one-decimal degC values from −50.0 to 1000.0 (10,501 values):
   - Lower in degC, upper in K: **4,756 become non-point slivers** (silently excluded) and 533 are refused.
   - Lower in K, upper in degC: 2,809 are refused and none become slivers.
10. **Evidence class**: **SOURCE_PROVEN** for the code path. The conversion values are independently derived; pint itself was not executed.
11. **Affected**: every `MaterialPropertySet` with an `InterpolationRule` whose point data mix affine units. `ApplicabilityRange.is_point` callers.
12. **False-support risk**: **low–medium**. The value is labelled INTERPOLATED with UNKNOWN uncertainty, but the interpolant spans across evidence it should have used.
13. **Replay**: deterministic, but the record does not say the datum was skipped.
14. **Compatibility**: no record format change.
15. **Certification**: `materials/ranges.py` **and** `materials/properties.py` are in `current_core_v2.json`.
16. **Genesis**: none.
17. **Reproduction plan (NOT executed)**: a unit test in `tests/test_materials_engine.py` with the three data above. Assert the result interpolates between 300 K and 350 K, or that it refuses. Cost under 1 s.
18. **Repair (proposal)**:
    - Decide whether a range is a point with exact arithmetic in one canonical ratio-scale unit, for example `_exact(lower,"K") == _exact(upper,"K")` through the existing `_exact`.
    - Or refuse point ranges whose bounds use different units.
    - In interpolation, refuse when a non-point datum on the rule's variable lies inside the bracket, instead of skipping it.
19. **Owner approval**: yes (certified files).
20. **Self-challenge**: "Nobody declares a point with two different units." The test suite already exercises mixed-unit points across data (`test_interpolation_with_mixed_unit_points_uses_one_unit`), so mixed units are an anticipated input. The silent skip, rather than a refusal, is the defect. **Survives as MINOR.**

---

## B-03 — DC residual gate awards NUMERICALLY_CONVERGED to a corrupted solution under a common-mode offset

1. **ID** B-03 · `new_or_known`: **variant_of: D1-3** (scaling by the datum or offset). This is a new site, the DC MNA gate. NUM-01's own corrupted-midpoint example comes back once a common-mode voltage is added.
2. **Category**: convergence detection / residual scaling. Residual mistaken for accuracy.
3. **File:line**: `src/engcore/domains/electrical/dc/validation.py:288-335` (`check_linear_residual`). The row scale `np.abs(A) @ np.abs(x) + np.abs(z)` is at `:300`. The level award is at `:329-331`.
4. **Governing contract**: `validation.py:83-93` (NUM-01). It says each bound is relative to the quantity it judges. It cites a corrupted divider midpoint (0.5 V → 0.6 V) that the old absolute bound let through, and states the relative bound now fails it. The docstring at `:293` says the check answers "did the backend actually solve the system it was given?".
5. **Invariant**: "Verification does not become validation". More narrowly, "a residual is not an error bound" (OD-32 family).
6. **Root cause**: the per-row bound is the componentwise (Oettli–Prager) backward error, `|r_i| ≤ rtol·(|A||x|+|z|)_i`. Its scale includes `G·|V_i|`, the absolute node potentials. The KCL row residual measures `G·(potential differences)`. With a large common-mode potential, the allowed corruption of a potential difference grows with `V_cm`, not with the current that flows.
7. **Minimal trigger**:
   - Circuit: ideal sources hold node a at `V_cm + 1 mV` and node c at `V_cm`. Two 1 Ω resistors run a–m and m–c.
   - Corrupt `V_m` by +0.1 mV, which is a **20 % error** in both branch currents. This is NUM-01's own corruption ratio.
   - Reachability: the gate is applied to whatever solution vector the backend returns. Its stated purpose is to catch a backend that did not solve.
8. **Expected vs observed** (`b_dc_common_mode.py`, exact Fractions):

   | V_cm | row m: \|r\| | row m: tol | residual gate | KCL check |
   |---|---|---|---|---|
   | 0 V | 2.0e-4 | 4.4e-12 | FAIL | FAIL |
   | 1 kV | 2.0e-4 | 8.0e-6 | FAIL | FAIL |
   | 1 MV | 2.0e-4 | 8.0e-3 | **PASS (awards NUMERICALLY_CONVERGED)** | FAIL |

   At 1 kV the gate lets through about a 0.8 % current corruption: allowed δ ≈ 4e-6 V against a 0.5 mV drop.
9. **Independent reasoning**: componentwise backward error ω ≤ 1e-9 bounds the forward error of the branch currents only through the componentwise condition number. That number grows like `V_cm/ΔV` because of cancellation in `G(V_i − V_j)`. A backward-error gate certifies that the solve was backward-stable at the 1e-9 level. It does not certify that the reported currents are right, and NUM-01 says it does.
10. **Evidence class**: **SOURCE_PROVEN** (formula traced). The counterexample is an independent derivation.
11. **Affected**:
    - `electrical.dc` results (`solver.py:323-347` → `build_validation_report`).
    - The electrothermal production capability, which pins the native MNA route (`product/capabilities.py:421-425`).
    - `ValidationReport.attained_levels` (`scientific/results/validation.py:1106-1127`) lists NUMERICALLY_CONVERGED even when another check FAILs.
12. **False-support risk**: **low**. The independent KCL check in the same report FAILs, so `status` is FAIL. But `claims(NUMERICALLY_CONVERGED)` is True on that report. With SciPy's backward-stable `gesv` the corruption does not arise in practice.
13. **Replay**: none.
14. **Compatibility**: tightening changes the gate version (`DC_CONVERGENCE_THRESHOLDS` 0.2.0 → 0.3.0) and the pins in `engcore.domains`.
15. **Certification**: `domains/electrical/dc/validation.py` **is in** `current_core_v2.json`.
16. **Genesis**: none.
17. **Reproduction plan (NOT executed)**:
    - Build the circuit with `DCCircuit`, solve it, then hand `build_validation_report` the solution with `V_m += 1e-4`.
    - Expect `linear_system_residual` to PASS, `kirchhoff_current_law` to FAIL, and `report.claims(NUMERICALLY_CONVERGED)` to be True.
    - Cost under 1 s. No external tools.
18. **Repair (proposal)**: award the level only if the independent KCL and voltage-source reconstructions also PASS. Alternatively, measure KCL rows against `rtol·Σ|branch currents|`, the scale `check_kcl` already uses, instead of `|A||x|`.
19. **Owner approval**: yes (certified file, threshold version).
20. **Self-challenge**: "Backward error is the textbook acceptance test for a direct solve." True. But NUM-01 explicitly claims to catch corrupted solutions relative to the quantity being judged, and it does not under a common-mode offset. KCL catches it, so impact is limited. **Survives as MINOR.**

---

## B-04 — FTCS run outside its stability envelope can return a garbage field with every check passing

1. **ID** B-04 · `new_or_known`: **NEW**. I found no hit in the known docs. It is related in spirit to "model applicability precedes evidence-bearing execution" for realizations.
2. **Category**: time-step dependence / stability detection / applicability.
3. **File:line**: `src/engcore/domains/thermal_models/conduction1d_schemes.py`:
   - `:813-846`: `solve_with_realization(require_admissible=False)` is the default and does not record the realization verdict.
   - `:553-569`: only a non-finite value is detected.
   - `:604-651`: the "amplitude_decay" check with bound `max|u| ≤ 1 + 1e-9`.
   - `:893-899`: `validity` assesses only the model, not the realization.
4. **Governing contract**: the `validate` docstring at `:604-610` says the maximum-principle check "is the one that matters here... it can catch a scheme used outside its stability envelope without being told about schemes".
5. **Invariant**: "Model applicability precedes evidence-bearing execution". The realization's applicability (FTCS needs r ≤ 1/2, as the module's own `_APPLICABILITY` table says) is neither enforced by default nor carried on the `ScientificResult`.
6. **Root cause**:
   - The initial data `sin(πx/L)` is a discrete eigenvector, so unstable modes are seeded only by round-off (about 1e-16).
   - They grow like |1 − 4r|^k while the fundamental decays.
   - The check compares `max|u|` with the initial amplitude 1, not with the decayed fundamental. So there is a window of steps where the noise is O(fundamental) but `max|u| < 1`.
7. **Minimal trigger** (`b_ftcs_window.py`, emulating `_BandedBackend.explicit_stepper`):

   | n_cells | r | step k | max\|u\| | error vs exact discrete fundamental | fundamental amplitude |
   |---|---|---|---|---|---|
   | 20 | 0.55 | 209 | 0.113 | 0.057 | 0.058 |
   | 40 | 0.75 | 52 | 0.875 | 0.093 | 0.786 |

   - At n = 20, r = 0.55, step 209 the error is about 100 % of the fundamental.
   - At n = 40, r = 0.75, step 52 the error is about 12 %.
   - 17 steps at r = 0.55 and 2 steps at r = 0.75 fall in this window.
8. **Expected vs observed**:
   - **Expected**: a result whose midpoint value is not the solution must not read CONVERGED with all checks PASS and an IN_DOMAIN validity.
   - **Observed** (traced): `convergence=CONVERGED`. `field_finite` PASS, `amplitude_decay` PASS, `boundary_conditions_held` PASS. `dimensional_consistency` PASS, which establishes DIMENSIONALLY_VALID. `validity` is IN_DOMAIN for the model's α condition. Nothing in the result says r > 1/2 was outside the realization's envelope; only `metadata.fourier_number` records r.
9. **Independent reasoning**: FTCS amplification of mode k is `1 − 4r sin²(kπ/2n)`. For r > 1/2 the highest mode exceeds 1 in magnitude. Round-off noise ε·g^k overtakes the fundamental g₁^k at k ≈ ln(1/ε)/ln(g/g₁), which is well before it overtakes 1. The scripts confirm the window exists.
10. **Evidence class**: **SOURCE_PROVEN** for the gate logic and default. The corrupted-yet-PASS trajectory is an independent derivation (operation-faithful emulation, not FORGE execution).
11. **Affected**: the `thermal.conduction1d.linear_diffusion` realizations R2 (FTCS) via `solve_with_realization`. I found no `src` caller other than the module itself (`grep solve_with_realization` in `src` returns nothing). Reachable from tests, experiments and the MODEL0-R differential study.
12. **False-support risk**: **low** today (no production capability routes here); medium if this path is wired to claims.
13. **Replay**: n/a.
14. **Compatibility**: recording the realization assessment on the result adds a field (identity change for R2 results).
15. **Certification**: `conduction1d_schemes.py` **is in** `current_core_v2.json`.
16. **Genesis**: none.
17. **Reproduction plan (NOT executed)**:
    - Find a `ConductionSlab` with n_cells = 20, r = 0.55 and n_steps = 209, with L, α and end_time chosen to give that r.
    - Run `solve_with_realization(slab, EXPLICIT_REALIZATION, run_id="x")`.
    - Compare `full[mid]` with `g1**209`. Expect every check PASS and an error of about 100 % of the fundamental.
    - Cost under 1 s.
18. **Repair (proposal)**: have `solve_with_realization` attach the realization assessment, for example as validity or a FAIL/NOT_RUN check named `realization_applicability`. Stop describing `amplitude_decay` as a stability detector, or compare against the decayed fundamental `g1**n` instead of 1.
19. **Owner approval**: yes (certified file; MODEL0-R evidence).
20. **Self-challenge**: "`require_admissible=False` is deliberate, so the inadmissible case can be observed." The docstring says so. But the result it returns carries no statement that it was inadmissible, and the module claims the amplitude check catches instability. Both are false for the window shown. **Survives as MINOR.**

---

## B-05 — The PDE "operator is singular" guard does not cover partially-restrained vector problems

1. **ID** B-05 · `new_or_known`: **NEW**.
2. **Category**: Dirichlet/Neumann assembly / boundary-condition sufficiency.
3. **File:line**:
   - `src/engcore/pde/contracts.py:426-427`: "no Dirichlet or Robin condition: the operator is singular".
   - `:255`: `components` selects which displacement components a vector Dirichlet fixes.
   - Provider applies only the listed components: `providers/fenicsx/forge_fenicsx/__init__.py:177-182`.
4. **Governing contract**:
   - The message at `:427` implies its converse: one Dirichlet condition makes the operator non-singular.
   - CLAUDE.md: "Missing boundary conditions are never silently defaulted."
5. **Invariant**: a solve whose solution is not unique must not be admitted as CONVERGED.
6. **Root cause**: the check is `any(bc.kind in (DIRICHLET, ROBIN))`. For `linear_elasticity_plane_stress` and `linear_thermoelasticity_plane_stress`, a single `components=(0,)` Dirichlet on one edge removes x-translation and rotation but leaves y-translation as a zero-energy mode.
7. **Minimal trigger**: a plane-stress plate with `roller("left",(0,))` and traction or traction-free on the other edges, and the bottom roller left out. The flagship (`flagships/forge_flagships/thermo_mechanical.py:183-185`) declares both rollers, so it is not affected.
8. **Expected vs observed**:
   - **Expected**: refusal, because the restraint is insufficient.
   - **Observed**: construction is admitted. Downstream, the result depends on the declared solver:
     - LU (`preonly`/`lu`) fails on the zero pivot.
     - A Krylov solver on a consistent singular SPD system (zero net y-load) converges to the minimum-norm solution and passes the `residual_rtol` check (`forge_fenicsx accept`, `:204-206`). That yields a CONVERGED displacement field with an arbitrary rigid y-offset.
9. **Independent reasoning**: plane-stress stiffness K has null space {rigid translations tx, ty, rotation θ}. Constraining u_x on a vertical line removes tx and θ (θ gives u_x = −θ(y−y0), which is non-zero on the line) but not ty. A consistent singular system has infinitely many solutions, and a residual test cannot tell them apart.
10. **Evidence class**: guard incompleteness is **SOURCE_PROVEN**. The end-to-end CONVERGED-with-non-unique-displacement outcome is **STATIC_SUSPICION**: it depends on the external dolfinx/PETSc behaviour, which I did not execute.
11. **Affected**: PDE vector templates through any provider (FEniCSx, CalculiX, Code_Aster adapters).
12. **False-support risk**: **low–medium**. Stresses are unaffected by rigid modes. Displacement QoIs are not unique.
13. **Replay**: n/a.
14. **Compatibility**: an extra refusal for previously admitted, ill-posed problems.
15. **Certification**: `pde/contracts.py` is **not** in `current_core_v2.json`.
16. **Genesis**: none.
17. **Reproduction plan (NOT executed)**:
    - Construct the PDEProblem above in WSL `~/mm/root/envs/fenicsx` with ksp `cg`/pc `jacobi`.
    - Expect CONVERGED, and `u_y` minimum-norm rather than physically determined.
    - Cost: seconds. Needs the WSL FEniCSx env.
18. **Repair (proposal)**:
    - For vector templates, require that the union of restrained components across Dirichlet groups covers every component.
    - Require at least one group restraining a component on a facet set that is not collinear with that component's direction (which removes rotation).
    - Otherwise refuse with "rigid-body modes are not removed".
    - The transient scalar pure-Neumann refusal is over-strict but fails closed (see OBSERVATION list).
19. **Owner approval**: no (uncertified). A design review of the restraint rule is advisable.
20. **Self-challenge**: "Users are responsible for sufficient supports; LU will fail anyway." That holds only if LU is chosen. The guard exists precisely to refuse singular operators, and its message overstates what it checks. **Survives as MINOR.**

---

## B-06 (OBSERVATION) — Naming a subset of quantities closes the run-level splitting source

- **File:line**: `execution/multiphysics/numerical_error.py:343-361`. A supplied `SplittingErrorEstimate` replaces the single `run:splitting` UNQUANTIFIED source with one source per named quantity.
- **Effect**: estimating only a benign quantity A moves `verdict` from INCOMPLETE to ESTIMATED, even though quantity B's splitting error was never assessed. Removing B from `quantities` raises the verdict, which conflicts in spirit with "Removing evidence must not increase assurance".
- **Why OBSERVATION**: `claims/coupling_numerical.py:164-177` vetoes on any ESTIMATED source. No claim channel is improved, so only the assessment label is affected. SOURCE_PROVEN, risk none/low. `new_or_known`: NEW. Not certified.
- **Repair**: keep `run:splitting` UNQUANTIFIED for unnamed outputs, or scope the verdict to the named quantities.

## B-07 (OBSERVATION) — M1C per-step absolute conservation allowance accumulates with step count

- **File:line**: `conduction1d_transient_fv.py:511-513`. `exact_allowance = atol + rtol·exchange` applies per step, and there is no session-level cumulative gate.
- **Effect**: over N steps the admitted cumulative leak is N·atol plus rtol times the total exchange, so halving dt doubles the absolute part. This is the time-step analogue of the fixed N² mesh floor.
- **Status**: not claimed as a run-level bound. There is no production consumer (grep: only tests). STATIC (the design is clear), risk none today. Not certified.

---

## (a) Hypotheses I could not confirm, or that I downgraded

- **`SciPyMinimizeProvider` silent SciPy defaults** (`numerical/providers.py:181-188`). A declared `{xatol}` alone leaves SciPy's default fatol = 1e-4 in force (and vice versa), and the default is not in the execution identity. Nelder–Mead stops only when both hold (AND), so a default only adds a condition and never loosens acceptance. Downgraded to an identity/reproducibility nit.
- **`adapt_resolution` optional stopping** (`claims/adaptive_resolution.py:165-186`). The GCI is re-applied after every new level and the run stops at the first QUANTIFIED triple. Multiple looks raise the chance that a pre-asymptotic triple happens to match `|p − p_formal| ≤ tol`. This is a statistical concern; I did not quantify it.
- **`ElectricalDCSolver.solve`** uses `warnings.catch_warnings()` (`dc/solver.py:207-209`), which is process-global (providers.py:101-102 notes the same hazard). Under concurrent Jacobi, another thread could reset the `LinAlgWarning → error` filter, and an ill-conditioned solve would then pass silently. Concurrency is outside my area and was not traced.
- **The DC cross-solver consensus (`dc_consensus.py:116-129`)** under high common mode: ngspice's 13 printed digits make derived resistor voltages disagree by more than 1e-9 relative. That fails closed (a false FAIL, not false support).
- **The M1C local diagnostic allowance** (`:492`) still contains a Σ|A||x| term that grows like N² (because Σg ∝ N²). It cannot relax the exact global gate, and the row check already bounds each local residual. Known D1-2/N² family; not re-reported.

## (b) Areas inspected and found sound (with reasoning)

- **DampedNewton (`numerical/nonlinear.py`)**:
  - The Armijo slope −2φ is correct for φ = ½‖W F‖² with J·dx = −F, because ∇φ·dx = (WF)ᵀ W J dx = −‖WF‖².
  - Forward-difference columns divide by the representable step `probe[j] − x[j]`. A zero step gives a non-finite column, which is classified NON_FINITE.
  - Step stagnation never counts as convergence (`:387`).
  - `classify_history` cannot fire on the converging step: a STAGNATING or DIVERGING verdict would need an earlier measure ≤ atol, which would already have ended the loop.
  - The condition check uses the stricter of the declared limit and the default.
- **The Hager/Higham estimator (`numerical/core.py:613-635`)** is a valid lower bound. The alternating vector has ‖b‖₁ = 1.5n, hence the 2/(3n) factor. A κ₁ lower bound above the threshold proves ill-conditioning; one below it is reported unresolved.
- **GCI (`claims/numerical_uq.py`)**:
  - p = ln((f3−f2)/(f2−f1))/ln r.
  - Richardson f1 + (f1−f2)/(r^p−1).
  - Fs = 1.25.
  - Sign change refused as oscillatory; ratio ≤ 1 refused as not shrinking.
  - p_used = min(p_obs, p_formal) is conservative.
  - r is declared and integer. `RefinementStudy.ladder` divides cell counts (NAFEMS uses cells, h = L/n), so the h ratio is exactly r, with no node-count (N−1) bias. NAFEMS refines space and time together by 2 with CN, so the leading error h²+dt² scales by r².
- **Splitting Richardson (`splitting.py`)**: base error |d1|·2^p/(2^p−1) follows from e(h) = C h^p. p = log2(d1/d2) with sign and shrink refusals.
- **Aitken (`relaxation.py:213-227`)**: Küttler–Wall formula. **IQN-ILS / IMVJ (`acceleration.py:246-271`)**: x_{k+1} = x̃_k + W c with c = argmin‖V c + r‖ in the D-weighted norm, and J = J₀ + (W − J₀V)(DV)⁺D. Consistent signs.
- **Conservative remap (`mapping.py`, `cell_mapping.py`)**:
  - The density and integrated operators are correct under full coverage.
  - Sutherland–Hodgman inside test s ≥ 0 matches a CCW clip.
  - The tetrahedron intersection vertex enumeration (vertex-in, edge×facet both ways) is complete for convex polytopes.
  - `kron(Oy,Ox)` ordering matches `outer(sy,sx)`.
  - Both coverage directions are enforced; offset-scale conserved units are refused.
- **`map_cells_1d`, `interval_transfer`, `vertex_state`**: the totals use the correct measure factor `(unit)·m`, and the affine conversion is applied before the overlap averaging, which commutes. The dual-grid split issues are the known OD-33/D3-2/D3-3.
- **Thomas (`conduction1d_nonuniform.py`)**:
  - Pivots stay positive with a Dirichlet row of diagonal 1 or with a flux end (pivot₁ = g₁ > 0).
  - The exactness claim for constant k and quadratic u holds, because the dual face is at the cell midpoint, where the central difference of a quadratic is exact.
  - The inward-flux sign is correct.
- **`mesh_adaptation`**: the non-uniform three-point u″ is exact for quadratics, the P1 bound h²/8·max|u″| is correct, Doerfler marking is deterministic, and the bisection representability guard is present.
- **`field_measures`**: P1 lumped weights are area/3 and volume/4, and the Q1 tensor trapezoid on rectangles is exact.
- **`pde/postprocess.py`**: P1 shape gradients, the plane-stress constitutive law with thermal strain on the normal components only, G = E/(2(1+ν)), and the plane-stress von Mises formula are all correct.
- **`lumped_reference.py`**: the recurrence term_{n+1} = −term_n·y/(n+1) and the alternating remainder bound hold for y ≤ 0.5. Rounding errors contract because the flow-map derivative is e^{−y} < 1.
- **MNA (`dc/mna.py`)**: the stamps and source-current sign convention are consistent with KCL "sum leaving = 0". The KCL reconstruction in `validation.py` is independent of the matrix.
- **M1C (`conduction1d_transient_fv.py`)**:
  - The Backward Euler assembly is correct.
  - Series edge resistance and dual capacity follow from the overlaps.
  - The Dirichlet row is scaled into power units.
  - The Neumann area is the end region's.
  - The exact `Fraction` global gate is correctly formed. Its D1-2 limitation is known.
- **GCL rules (`moving_mesh.py:69-75`)**: on a simplex V(τ) has degree d, so the rule must be exact to degree d−1. Midpoint violates this on tetrahedra, as stated.
- **ODE provider (`providers.py:204-253`)**: integration is split per breakpoint segment. `t in outs` exact membership is safe because `solve_ivp` returns `t_eval` values verbatim, and a final coverage check fails closed.
