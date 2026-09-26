# Flagship C - Lid-Driven Cavity CFD Benchmark

Statement labels: **FACT** a checkable statement about the run artifacts - **REFERENCE DATA** taken from an external source with provenance - **ASSUMPTION** declared, not evidenced - **MODEL OUTPUT** a provider's computed value - **CORROBORATION** independent solvers agreeing (never validation) - **VALIDATION** comparison with a reference or measurement, stated with its scope (a numerical benchmark is not an experiment).

`request 573e9a4cdf8b5081  plan 3956b33a45b6dd55  result 4e9c9b64d727f458`

## 1. Engineering question

[FACT] Do two independent CFD codes, given exactly the same declared cavity, fluid records and Reynolds number, predict the same flow; how does each converge under refinement; and how close does each come to the published Ghia et al. (1982) centerline benchmark?

## 2. System definition

[FACT] 2-D lid-driven square cavity, side 0.1 m, water at 20 degC / 1 atm, lid speed set so that Re = 100 exactly (U = Re nu / L = 0.0010034 m/s), N x N cells with N = [20, 40, 80]. One BIG 12 request: `fluid_properties` (CoolProp) -> `openfoam_N` / `su2_N` -> `compare_N` (whole-field OpenFOAM vs SU2) -> `convergence`.

## 3. Assumptions

[ASSUMPTION] Incompressible laminar Newtonian flow, constant properties, 2-D, steady end state (OpenFOAM: transient icoFoam marched until the last write interval changes by less than 1e-7 m/s; SU2: pseudo-time until log10 rms(p) < -10). Declared comparison rules: SU2 nodal velocity is mapped to OpenFOAM cell centres by the mean of the four cell corners; profiles are sampled piecewise-linearly with the wall values closing each line.

## 4. Inputs and sources

[REFERENCE DATA] Water density 998.207 kilogram / m ** 3 and viscosity 0.0010016 Pa * second are CoolProp equation-of-state values (provider-derived property records, not measurements), and both CFD codes receive the same records. [REFERENCE DATA] Ghia, Ghia & Shin (1982), J. Comput. Phys. 48(3) 387-411, Tables I and II, Re = 100 columns: bf95994ba4b13061.. (transcription digests in the record). A NUMERICAL benchmark (multigrid finite difference, 129 x 129), not an experiment; only the 17-point Re = 100 columns are stored, with attribution; the paper and the transcription files are not copied; the u column and the v column agree with a second independent public transcription. The numbers were NOT checked against the printed paper itself (only against the two public transcriptions), so their fidelity to the paper is an unverified assumption.

## 5. Providers and models

[FACT] Providers executed: coolprop 8.0.0, openfoam v2412, su2 8.5.0. OpenFOAM v2412 `icoFoam` (PISO, Gauss linear, Euler); SU2 8.5.0 `INC_NAVIER_STOKES` (FDS, MUSCL, implicit Euler pseudo-time). Both are process providers behind the same argv-only boundary; each input file and executable is content-bound.

## 6. Applicability

[FACT] Both adapters refuse Re >= 1000 (declared laminar bound); this case has Re = 100. The Ghia reference applies at Re = 100 only (envelope [99, 101]) and its applicability is evaluated, not assumed.

## 7. Execution

[FACT] SUCCEEDED; provider wall times (operational): OpenFOAM 2.2 s, 4.2 s, 15.9 s; SU2 2.0 s, 2.5 s, 11.8 s for N = [20, 40, 80]. 8 recorded provider executions.

## 8. Results

[MODEL OUTPUT] u(0.5, 0.5)/U at 80x80: OpenFOAM -0.2081, SU2 -0.1952; primary-vortex centre (grid resolution) OpenFOAM (0.6187, 0.7437), SU2 (0.6187, 0.7312) in x/L, y/L. Velocity fields, kinematic / gauge pressure, and centerline profiles are exported (VTU + CSV) in the run bundle. Pressure is NOT compared between the codes: OpenFOAM reports kinematic pressure p/rho and SU2 gauge pressure in Pa with different reference constants.

## 9. Verification

[FACT] Verification pyramid position:

- **L1 reached** - units, material-record digests, provider bindings and identities checked by BIG 12 preflight
- **L2 attempted not reached** - net flux through each mid-plane relative to U L (criterion 0.001, fixed before the run): {'openfoam': 0.00014267869136348632, 'su2': 0.006249425270081174}. NOT MET by ['su2'] (its sampled profile is not mass-conserving to the criterion; cause not investigated)
- **L3 not available** - there is no closed-form solution of the cavity at Re = 100 to compare with
- **L4 attempted not reached** - [20, 40, 80] cells per side. Predeclared criterion (max centerline error against the BENCHMARK decreases monotonically for both codes and both lines): NOT MET - flags {'ghia_u_max_error_of': 0.0, 'ghia_v_max_error_of': 0.0, 'ghia_u_max_error_su2': 1.0, 'ghia_v_max_error_su2': 1.0}. It is benchmark-relative, so it also folds in the benchmark's own truncation error; an intrinsic reading (successive changes of a fixed quantity) is recorded beside it as post hoc, never in its place
- **L5 attempted not reached** - OpenFOAM vs SU2 on identical declared inputs, whole field, 3 % of lid speed fixed before any run (the BIG 11 criterion, not loosened): NOT MET - the codes disagree, most near the lid; the disagreement is the result. The lower-half comparisons were chosen after seeing this and are recorded as post hoc observations only
- **L6 reached** - Ghia et al. (1982) Re = 100 centerlines, a NUMERICAL benchmark, at the finest mesh, tolerance 0.02 of lid speed fixed before the run: {'openfoam': True, 'su2': True}. Agreement would support this configuration's numerics only; it is not experimental validation
- **L7 not available** - no experimental data for this cavity was integrated

## 10. Cross-provider results

[CORROBORATION] NOT achieved. The pre-declared whole-field criterion (3 % of lid speed, the BIG 11 criterion, not loosened) is NOT MET at any mesh:

| mesh | whole-field max diff (of U) | at y/L | POST-HOC lower-half max diff | OpenFOAM err u | OpenFOAM err v | SU2 err u | SU2 err v |
|---|---|---|---|---|---|---|---|
| 20x20 | 0.2603 | 0.9750 | 0.0491 | 0.0127 | 0.0088 | 0.0514 | 0.0453 |
| 40x40 | 0.2446 | 0.9875 | 0.0268 | 0.0027 | 0.0086 | 0.0246 | 0.0187 |
| 80x80 | 0.2393 | 0.9937 | 0.0144 | 0.0044 | 0.0090 | 0.0112 | 0.0070 |

The largest differences are always in the cell layer next to the moving lid (y/L > 0.97) and they do NOT shrink with refinement (26 %, 24 %, 24 % of lid speed). The lower-half region was chosen AFTER the whole-field result and is labelled post hoc; it can never count as corroboration. **Interpretation, not established:** part of the disagreement is likely an artifact of the declared mapping (the 4-corner mean of SU2 nodal values includes the lid nodes at U, while OpenFOAM's cell-centre value sits half a cell below the lid in a steep boundary layer); this was not tested. The disagreement is reported as the result.

## 11. Reference comparison

[MODEL OUTPUT] Comparison with a NUMERICAL benchmark (not an experiment); scope: the Re = 100 centerlines, finest mesh, criterion 0.02 of lid speed fixed before the run: ghia_openfoam_80 MET (0.0090); ghia_su2_80 MET (0.0112). [VALIDATION] None: this is not an experimental comparison. It supports the numerics of these codes at Re = 100 for this configuration only and says nothing outside it. The reference envelope covers Re and the square-cavity aspect ratio; geometry details and boundary conditions are described in the record, not enforced by it.

## 12. Uncertainty

[FACT] Known input uncertainty: none. UNKNOWN (never zero): fluid state (declared 20 degC, 1 atm); lid speed and cavity size (declared); water density and viscosity: CoolProp equation-of-state values, uncertainty not propagated. Model discrepancy: NOT QUANTIFIED: incompressible laminar model, 2-D idealisation, no discretisation-error bound (only a grid study), each code's own scheme error. The benchmark itself carries its own discretisation error (129 x 129), so an error against it cannot be expected to fall to zero: the OpenFOAM error against Ghia is 0.0127, 0.0027, 0.0044 (u line) - not monotone, and the pre-declared monotonicity criterion is reported NOT MET.

## 13. Constraint and conservation checks

[FACT] `b_flux_openfoam` (max_midplane_flux) **SATISFIED** (margin 0.0008573 dimensionless); `b_flux_su2` (max_midplane_flux) **VIOLATED** (margin -0.005249 dimensionless) (the flux constraint is bound to the finest mesh of EACH code, on the unsigned maximum over both mid-planes). [MODEL OUTPUT] Net mid-plane flux relative to U L at 80x80: OpenFOAM 1.43e-04, SU2 6.25e-03 (criterion 0.001 fixed before the run; level 2 reads attempted not reached; NOT met by su2).

## 14. Negative control

[FACT] Unsupported regime: Re = 1500 -> OpenFOAM FAILED (ProviderRefusal: Re = 1500 >= 1000: the laminar icoFoam choice is refused), SU2 FAILED, no benchmark quantity available. Incompatible benchmark: the same Ghia data applied to a Re = 10 case is `not_applicable` (reynolds = 10 dimensionless is outside the reference range [99, 101]); a perfect number would not rescue it.

## 15. Scientific status

[FACT] Credibility verdict (existing authority): **insufficient_evidence**. Verification ladder (from the run): L1 reached; L2 attempted not reached; L3 not available; L4 attempted not reached; L5 attempted not reached; L6 reached; L7 not available; reference level: published_numerical_benchmark (a comparison with a numerical benchmark, not an experiment). What this flagship shows is that Forge exposes the disagreement and the failed criteria instead of tuning them away; it validates nothing physical.

## 16. Known limitations

[FACT] One geometry and one Reynolds number; a numerical (not experimental) benchmark with its own truncation error; the whole-field mapping likely contributes to the near-lid disagreement (untested); pressure is not compared; the vortex diagnostics are at grid resolution; numerical uncertainty is unquantified (only a grid study); OpenFOAM and SU2 use different discretisations (cell-centred vs vertex-based), so 'identical inputs' does not mean identical numerics.

## 17. Reproduction command

```bash
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'cd /mnt/d/forge-b13 && FORGE_PY_ENV=sci source tools/wsl_env.sh && python -m forge_flagships cavity --out /mnt/d/ftmp/cavity'
```
Tests: `python -m pytest flagships/tests/test_flagship_cavity.py` in the `sci` environment (OpenFOAM and SU2 via `FORGE_PROVIDER_ENVS`).

## Engineering summary (generated from the run)

```text
SYSTEM
  Lid-driven cavity, Re = 100, water 20 degC, ['20x20', '40x40', '80x80'] cells (re100)
EXECUTION
  SUCCEEDED
KEY OUTPUTS
  Water density: 998.207 kilogram / meter ** 3   [uncertainty UNKNOWN (not quantified)]
  Lid velocity for the declared Re: 0.0010034 meter / second   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM max centerline error vs Ghia 20x20: 0.0126729 dimensionless   [uncertainty UNKNOWN (not quantified)]
  SU2 max u-centerline error vs Ghia 20x20: 0.0514271 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM vs SU2 whole-field max difference 20x20 (of lid speed): 0.260311 dimensionless   [uncertainty UNKNOWN (not quantified)]
  ...where the two differ most (y/L) 20x20: 0.975 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM max centerline error vs Ghia 40x40: 0.00270574 dimensionless   [uncertainty UNKNOWN (not quantified)]
  SU2 max u-centerline error vs Ghia 40x40: 0.0246283 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM vs SU2 whole-field max difference 40x40 (of lid speed): 0.244641 dimensionless   [uncertainty UNKNOWN (not quantified)]
  ...where the two differ most (y/L) 40x40: 0.9875 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM max centerline error vs Ghia 80x80: 0.00444171 dimensionless   [uncertainty UNKNOWN (not quantified)]
  SU2 max u-centerline error vs Ghia 80x80: 0.0112104 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM vs SU2 whole-field max difference 80x80 (of lid speed): 0.239295 dimensionless   [uncertainty UNKNOWN (not quantified)]
  ...where the two differ most (y/L) 80x80: 0.99375 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM u(0.5,0.5)/U 80x80: -0.208131 dimensionless   [uncertainty UNKNOWN (not quantified)]
  SU2 u(0.5,0.5)/U 80x80: -0.195174 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM vortex centre x/L 80x80: 0.61875 dimensionless   [uncertainty UNKNOWN (not quantified)]
  OpenFOAM vortex centre y/L 80x80: 0.74375 dimensionless   [uncertainty UNKNOWN (not quantified)]
  SU2 vortex centre x/L 80x80: 0.61875 dimensionless   [uncertainty UNKNOWN (not quantified)]
  SU2 vortex centre y/L 80x80: 0.73125 dimensionless   [uncertainty UNKNOWN (not quantified)]
CONSTRAINTS
  b_flux_openfoam (max_midplane_flux): SATISFIED  (margin 0.0008573 dimensionless)
  b_flux_su2 (max_midplane_flux): VIOLATED  (margin -0.005249 dimensionless)
VERIFICATION
  L1 reached: units, material-record digests, provider bindings and identities checked by BIG 12 preflight
  L2 attempted not reached: net flux through each mid-plane relative to U L (criterion 0.001, fixed before the run): {'openfoam': 0.00014267869136348632, 'su2': 0.006249425270081174}. NOT MET by ['su2'] (its sampled profile is not mass-conserving to the criterion; cause not investigated)
  L3 not available: there is no closed-form solution of the cavity at Re = 100 to compare with
  L4 attempted not reached: [20, 40, 80] cells per side. Predeclared criterion (max centerline error against the BENCHMARK decreases monotonically for both codes and both lines): NOT MET - flags {'ghia_u_max_error_of': 0.0, 'ghia_v_max_error_of': 0.0, 'ghia_u_max_error_su2': 1.0, 'ghia_v_max_error_su2': 1.0}. It is benchmark-relative, so it also folds in the benchmark's own truncation error; an intrinsic reading (successive changes of a fixed quantity) is recorded beside it as post hoc, never in its place
  L5 attempted not reached: OpenFOAM vs SU2 on identical declared inputs, whole field, 3 % of lid speed fixed before any run (the BIG 11 criterion, not loosened): NOT MET - the codes disagree, most near the lid; the disagreement is the result. The lower-half comparisons were chosen after seeing this and are recorded as post hoc observations only
  L6 reached: Ghia et al. (1982) Re = 100 centerlines, a NUMERICAL benchmark, at the finest mesh, tolerance 0.02 of lid speed fixed before the run: {'openfoam': True, 'su2': True}. Agreement would support this configuration's numerics only; it is not experimental validation
  L7 not available: no experimental data for this cavity was integrated
REFERENCE COMPARISONS
  numerical_benchmark_comparison_not_validation_grant: ghia_openfoam_80 MET (0.009028 dimensionless; tolerance 0.02 dimensionless)
  numerical_benchmark_comparison_not_validation_grant: ghia_su2_80 MET (0.01121 dimensionless; tolerance 0.02 dimensionless)
UNCERTAINTY
  known input uncertainty: none stated
  UNKNOWN input uncertainty: fluid state (declared 20 degC, 1 atm), lid speed and cavity size (declared), water density and viscosity: CoolProp equation-of-state values, uncertainty not propagated
  model discrepancy: NOT QUANTIFIED: incompressible laminar model, 2-D idealisation, no discretisation-error bound (only a grid study), each code's own scheme error
  model applicability: laminar regime declared for Re < 1000 by both adapters; this case has Re = 100
  benchmark applicability: Ghia et al. (1982) applies at Re = 100 only; this case is Re = 100
SCIENTIFIC STATUS
  insufficient_evidence - derived by the existing credibility authority; the runtime supplies no validity record and no validation check, and this summary adds none
TRACE
  complete
```
