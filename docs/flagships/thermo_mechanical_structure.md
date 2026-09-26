# Flagship B - Thermo-Mechanical Structure

Statement labels: **FACT** a checkable statement about the run artifacts - **REFERENCE DATA** taken from an external source with provenance - **ASSUMPTION** declared, not evidenced - **MODEL OUTPUT** a provider's computed value - **CORROBORATION** independent solvers agreeing (never validation) - **VALIDATION** comparison with a reference or measurement, stated with its scope (a numerical benchmark is not an experiment).

`request 9ced744352e29c36  plan 26808b19e864cb9b  result 133e3b6220393432`

## 1. Engineering question

[FACT] A plate takes a heat load into one end and rejects it at the other. How does its temperature field deform it, how hard must a restraint push back, and do independent structural solvers agree?

## 2. System definition

[FACT] A symmetric half of an aluminium plate, 200 x 40 mm, 5 millimeter, plane stress, one structured P1 triangle mesh (80 x 16 cells; nodes 1377). Heat flux 40000 W/m2 in at x = 0, sink at 303.15 K at x = L, other edges adiabatic. Structure: rollers at both ends (u_x = 0 at x = 0 and x = L), symmetry at y = 0, top free - the plate cannot lengthen, so it is compressed. One BIG 12 request: `thermal` (FEniCSx steady conduction) -> `struct_fenicsx` / `struct_calculix` / `struct_code_aster` (same mesh, same temperature field, same material records) -> three pairwise comparison nodes. Bulk fields travel outside the request (an exchange keyed by the producing execution's identity); the request sees scalars and digests.

## 3. Assumptions

[ASSUMPTION] Small-strain linear thermoelasticity, isotropic constant properties, plane stress, stress-free temperature 293.15 K, 2-D symmetric-half idealisation, prescribed flux and sink temperature.

## 4. Inputs and sources

[ASSUMPTION] Material: illustrative typical values for 6061 aluminium - E = 68.9 GPa, nu = 0.33, alpha = 23.6e-6 /K, k = 167 W/(m K) - declared as ASSUMED BIG 5 records (NOT from a controlled datasheet, NOT measured). Every provider's material card is generated from those exact records (their digests are in the request). [FACT] Mesh, BCs, flux and geometry are declared in `flagships/forge_flagships/thermo_mechanical.py` and hashed into the request.

## 5. Providers and models

[FACT] Providers executed: calculix 2.23, code_aster 18.1.7, fenicsx 0.11.0. FEniCSx: `linear_thermoelasticity_plane_stress` template (BIG 8), P1, PETSc LU with a true-residual acceptance test. CalculiX: CPS3 plane-stress elements, `*EXPANSION, ZERO=T_ref`, nodal `*TEMPERATURE` (new adapter method `execute_thermoelastic`). Code_Aster: `C_PLAN`, `AFFE_VARC` on a nodal temperature field, stress from `SIEF_ELGA` (the adapter previously parsed displacement only). Stress for FEniCSx is recovered from its displacement with the same constitutive law (`engcore.pde.postprocess`).

## 6. Applicability

[FACT] The thermal node checks every solved temperature against the declared property range [250.0, 450.0] K (the property records are constants declared for that range); outside it the node is REFUSED and every structural node is BLOCKED. [ASSUMPTION] Small-strain, linear-elastic response is assumed. [MODEL OUTPUT] Peak thermal strain alpha (T_max - T_ref) = 1.37e-03 and the mid-plate mechanical strain |sigma|/E = 8.01e-04 (both << 1); peak von Mises 60 MPa against the declared illustrative yield 275 MPa (the elastic model itself is never checked against yield - that is the stress constraint).

## 7. Execution

[FACT] Flagship case: SUCCEEDED in 1.2 s of provider wall time; 4 provider executions. Preflight: deferred_checks with 3 non-blocking findings (the applicability WAIVERS on the structural nodes are stated, not hidden).

## 8. Results

[MODEL OUTPUT] Hot end 351.054 K, sink end 303.15 K (max deviation from the exact linear conduction profile: 3.6e-10 K); max displacement 3.65392e-05 m (FEniCSx) / 3.65408e-05 m (CalculiX) / 3.65392e-05 m (Code_Aster); mid-plate axial stress -5.52075e+07 Pa / -5.52075e+07 Pa / -5.52075e+07 Pa; peak von Mises 5.98166e+07 Pa / 5.99678e+07 Pa / 5.98166e+07 Pa (the peak is NOT claimed converged - see Verification). Heat in 4 watt, heat out 4 watt. Fields (temperature, displacement, von Mises) are exported as VTU files in the run bundle (presentation artifacts, not evidence).

## 9. Verification

[FACT] Verification pyramid position:

- **L1 reached** - units, material-record digests, provider bindings and identities checked by BIG 12 preflight; deferred to the solved state: ['thermal:property_range']
- **L2 reached** - heat in = heat out (exact for a linear profile, so a weak check on its own); the axial force through three sections is constant to within a relative spread of 2.8e-09 for all three solvers (criterion 0.001, pre-registered; read only where the mean force is at least 0.1 of the thermal force scale, observed 0.71) - the more informative diagnostic
- **L3 reached** - evidence from OTHER requests for the two exact uniform-temperature limits (request digests a957a5497dd7.., d555683f47c1..) and from this run for bar theory: uniform_free_exact MET (2.6e-13 vs 1e-06); uniform_constrained_exact MET (2.4e-13 vs 1e-06); bar_theory_mid_plate MET (2.6e-09 vs 0.03)
- **L4 attempted not reached** - four uniformly refined meshes, each a separate BIG 12 request (evidence from OTHER requests). Predeclared criterion (monotone, observed order >= 0.9 for mid-plate displacement AND stress, every provider): NOT MET - ['sxx_mid_code_aster', 'sxx_mid_fenicsx']. Observed orders of the mid-length displacement {'fenicsx': 1.9986794843229, 'calculix': 1.9925184186308693, 'code_aster': 1.9986794828219003}; last relative change of the mid-plate stress {'fenicsx': '3.0e-11', 'calculix': '1.6e-09', 'code_aster': '3.0e-11'} (at solver noise, so an order is undefined for it). Peak von Mises (FEniCSx, MPa) over the meshes [58.917, 59.409, 59.817, 60.06], observed orders {'fenicsx': 0.74, 'calculix': 0.69, 'code_aster': 0.74}: it is NOT claimed converged and the cause of its slow behaviour was not investigated
- **L5 reached** - three structural implementations agree on displacement and CalculiX/Code_Aster on element stress within tolerances pre-registered: CORROBORATION, not validation. Scale of the criterion: displacement tolerance 2.26e-06 m = 6.2 % of the peak displacement (it was set from the free-growth scale, which is larger than this restrained plate's response); observed worst difference 8.41e-09 m (0.023 %). All three solve the same P1 plane-stress discretisation on one mesh from ONE shared FEniCSx temperature field, so this corroborates the implementations, not the discretisation or the thermal solution, and FEniCSx/Code_Aster share one formulation
- **L6 not available** - no published thermo-structural numerical benchmark was integrated for this problem
- **L7 not available** - no measured deformation or stress data for this plate exists

[FACT] Exact uniform-temperature limits (each through BIG 12): free growth u = alpha dT (x, y) max relative error by provider {'fenicsx': 2.571247472088901e-13, 'calculix': 1.4356490631428816e-16, 'code_aster': 2.0127799865263202e-13}; fully restrained sigma_xx = -E alpha dT {'fenicsx': 2.443372920290787e-13, 'calculix': 0.0, 'code_aster': 2.4445184303331175e-13} (criterion 1e-06, pre-registered).

[MODEL OUTPUT] Mesh study through BIG 12 (mid-length displacement, mid-plate stress, peak von Mises):

| mesh | nodes | ux_mid FEniCSx | ux_mid CalculiX | ux_mid Code_Aster | sxx_mid FEniCSx (MPa) | vm_max FEniCSx (MPa) |
|---|---|---|---|---|---|---|
| 20x4 | 105 | 2.790824e-05 | 2.791838e-05 | 2.790824e-05 | -55.207466 | 58.917 |
| 40x8 | 369 | 2.789204e-05 | 2.789579e-05 | 2.789204e-05 | -55.207466 | 59.409 |
| 80x16 | 1377 | 2.788798e-05 | 2.789002e-05 | 2.788798e-05 | -55.207466 | 59.817 |
| 160x32 | 5313 | 2.788696e-05 | 2.788857e-05 | 2.788696e-05 | -55.207466 | 60.060 |

Observed orders: ux_mid_fenicsx: 2.00, vm_max_fenicsx: 0.74, ux_mid_calculix: 1.99, vm_max_calculix: 0.69, ux_mid_code_aster: 2.00, vm_max_code_aster: 0.74. **Pre-registered criterion (monotone, order >= 0.9 for mid-plate displacement AND stress, every provider): NOT MET** - failing: ['sxx_mid_code_aster', 'sxx_mid_fenicsx']. Reason: the last relative change of the mid-plate stress over the finest two meshes is 1.6e-09, which is at the level of solver noise, so an observed order is not defined for it. A post-hoc noise-aware reading (labelled post hoc, added after seeing the outcome) is met; it does not replace the predeclared outcome.

## 10. Cross-provider results

[CORROBORATION] Pairwise agreement, criteria pre-registered (1 % of the free thermal growth scale alpha dT L for displacement, 1 % of E alpha dT for stress): FEniCSx-CalculiX max |du| 8.4093e-09 m, FEniCSx-Code_Aster 1.06726e-18 m, CalculiX-Code_Aster 8.4093e-09 m; element stress CalculiX-Code_Aster max 232364 Pa. FEniCSx and Code_Aster agree to 2.9e-14 of the peak displacement (they share the plane-stress P1 formulation, so this is close to one algorithm run twice); CalculiX differs by 0.023 % of the peak displacement, consistent with the BIG 11 observation that CalculiX expands 2-D elements to 3-D wedges (an observation, not a proven cause). All three solve the SAME discretisation from ONE shared FEniCSx temperature field, so this is corroboration of the implementations - not of the discretisation, not of the thermal solution, and not validation. The criterion's scale: the displacement tolerance is 6.2 % of the peak displacement (set from the free-growth scale), far looser than what was observed.

## 11. Reference comparison

[FACT] Analytic references only: (1) uniform-temperature free growth, (2) uniform-temperature restrained stress, (3) bar theory for the mid-plate stress with an axial gradient (its envelope is declared by the flagship with no external source, and this plate sits on the inclusive aspect-ratio edge; the observed agreement is far tighter than its 3 % tolerance, so it cannot discriminate a 1 % error), all labelled ANALYTIC; uniform_free_exact MET (2.57e-13 vs 1e-06); uniform_constrained_exact MET (2.44e-13 vs 1e-06); bar_theory_mid_plate MET (2.64e-09 vs 0.03). [VALIDATION] None: no published thermo-structural numerical benchmark and no measured data for this plate were integrated. The NAFEMS material in the repository is thermal only (T3, 1-D transient conduction) and does not exercise this problem.

## 12. Uncertainty

[FACT] Known input uncertainty: none. UNKNOWN (never zero): heat flux and sink temperature (declared); stress-free temperature (declared); E, nu, alpha, k (ASSUMED illustrative records); plate thickness and geometry (declared). Model discrepancy: NOT QUANTIFIED: linear small-strain plane-stress idealisation, isotropic constant properties, 2-D symmetric-half model (unknown, not zero). Discretisation error is characterised only by the mesh study, not bounded.

## 13. Constraint and conservation checks

[FACT] `b_disp` (max_displacement) **SATISFIED** (margin 6.346e-05 meter); `b_vm` (max_von_mises) **SATISFIED** (margin 7.768e+07 pascal). [MODEL OUTPUT] Thermal energy: heat in vs heat out residual 6.8e-11 watt (tolerance 4.0e-06). Equilibrium diagnostic (axial force through three sections): largest relative spread 2.8e-09 (criterion 0.001), mean force 0.71 of the thermal force scale (read only at or above 0.1, so a solve that ignored the load cannot pass).

## 14. Negative control

[FACT] Over-range load (a heat load that drives the plate above the declared property range): thermal node REFUSED - the solved state left applicability (property_range: plate temperature [303.15, 590.58] K against the declared property range [250.0, 450.0] K); the step is not committed; all three structural nodes BLOCKED; every structural observable and both constraints UNAVAILABLE.

## 15. Scientific status

[FACT] Credibility verdict (existing authority): **insufficient_evidence**. Verification ladder (from the run): L1 reached; L2 reached; L3 reached; L4 attempted not reached; L5 reached; L6 not available; L7 not available; reference level: none. Level 5, where reached, is corroboration of the implementations only. This flagship demonstrates coupled thermo-mechanical execution, exact-limit verification, a mesh study (see its predeclared outcome above) and independent-implementation corroboration. It validates nothing physical.

## 16. Known limitations

[FACT] Illustrative material records; 2-D linear thermoelasticity only; one geometry; no reference benchmark beyond analytic limits; the peak von Mises value is mesh-dependent (order < 1) and not claimed converged and its cause was not investigated; CalculiX and the other two differ by a small difference not explained in detail; FEniCSx stress is recovered, not native; the property range is a declared envelope; the three solvers share one discretisation and one temperature field.

## 17. Reproduction command

```bash
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash -c 'cd /mnt/d/forge-b13 && FORGE_PY_ENV=fenicsx source tools/wsl_env.sh && python -m forge_flagships structure flagship --out /mnt/d/ftmp/structure_flagship --extras'
```
Cases: `flagship`, `over_range`, `uniform_free`, `uniform_constrained`. Tests: `python -m pytest flagships/tests/test_flagship_thermo_mechanical.py` in the `fenicsx` environment (CalculiX and Code_Aster are found through `FORGE_PROVIDER_ENVS`).

## Engineering summary (generated from the run)

```text
SYSTEM
  Heated aluminium plate, constrained, 80x16 P1 mesh (flagship)
EXECUTION
  SUCCEEDED
KEY OUTPUTS
  Hot-end temperature: 351.054 kelvin   [uncertainty UNKNOWN (not quantified)]
  Sink-end temperature: 303.15 kelvin   [uncertainty UNKNOWN (not quantified)]
  Max displacement (FEniCSx): 3.65392e-05 meter   [uncertainty UNKNOWN (not quantified)]
  Max displacement (CalculiX): 3.65408e-05 meter   [uncertainty UNKNOWN (not quantified)]
  Max displacement (Code_Aster): 3.65392e-05 meter   [uncertainty UNKNOWN (not quantified)]
  Mid-plate axial stress (FEniCSx): -5.52075e+07 pascal   [uncertainty UNKNOWN (not quantified)]
  Mid-plate axial stress (CalculiX): -5.52075e+07 pascal   [uncertainty UNKNOWN (not quantified)]
  Mid-plate axial stress (Code_Aster): -5.52075e+07 pascal   [uncertainty UNKNOWN (not quantified)]
  Peak von Mises (FEniCSx): 5.98166e+07 pascal   [uncertainty UNKNOWN (not quantified)]
  Peak von Mises (CalculiX): 5.99678e+07 pascal   [uncertainty UNKNOWN (not quantified)]
  Max |displacement| difference FEniCSx-CalculiX: 8.4093e-09 meter   [uncertainty UNKNOWN (not quantified)]
  Max |displacement| difference FEniCSx-Code_Aster: 1.06726e-18 meter   [uncertainty UNKNOWN (not quantified)]
  Max |stress| difference CalculiX-Code_Aster: 232364 pascal   [uncertainty UNKNOWN (not quantified)]
CONSTRAINTS
  b_disp (max_displacement): SATISFIED  (margin 6.346e-05 meter)
  b_vm (max_von_mises): SATISFIED  (margin 7.768e+07 pascal)
CONSERVATION
  thermal_energy: closed residual 6.823e-11 watt (tolerance 4.000e-06)
VERIFICATION
  L1 reached: units, material-record digests, provider bindings and identities checked by BIG 12 preflight; deferred to the solved state: ['thermal:property_range']
  L2 reached: heat in = heat out (exact for a linear profile, so a weak check on its own); the axial force through three sections is constant to within a relative spread of 2.8e-09 for all three solvers (criterion 0.001, pre-registered; read only where the mean force is at least 0.1 of the thermal force scale, observed 0.71) - the more informative diagnostic
  L3 reached: evidence from OTHER requests for the two exact uniform-temperature limits (request digests a957a5497dd7.., d555683f47c1..) and from this run for bar theory: uniform_free_exact MET (2.6e-13 vs 1e-06); uniform_constrained_exact MET (2.4e-13 vs 1e-06); bar_theory_mid_plate MET (2.6e-09 vs 0.03)
  L4 attempted not reached: four uniformly refined meshes, each a separate BIG 12 request (evidence from OTHER requests). Predeclared criterion (monotone, observed order >= 0.9 for mid-plate displacement AND stress, every provider): NOT MET - ['sxx_mid_code_aster', 'sxx_mid_fenicsx']. Observed orders of the mid-length displacement {'fenicsx': 1.9986794843229, 'calculix': 1.9925184186308693, 'code_aster': 1.9986794828219003}; last relative change of the mid-plate stress {'fenicsx': '3.0e-11', 'calculix': '1.6e-09', 'code_aster': '3.0e-11'} (at solver noise, so an order is undefined for it). Peak von Mises (FEniCSx, MPa) over the meshes [58.917, 59.409, 59.817, 60.06], observed orders {'fenicsx': 0.74, 'calculix': 0.69, 'code_aster': 0.74}: it is NOT claimed converged and the cause of its slow behaviour was not investigated
  L5 reached: three structural implementations agree on displacement and CalculiX/Code_Aster on element stress within tolerances pre-registered: CORROBORATION, not validation. Scale of the criterion: displacement tolerance 2.26e-06 m = 6.2 % of the peak displacement (it was set from the free-growth scale, which is larger than this restrained plate's response); observed worst difference 8.41e-09 m (0.023 %). All three solve the same P1 plane-stress discretisation on one mesh from ONE shared FEniCSx temperature field, so this corroborates the implementations, not the discretisation or the thermal solution, and FEniCSx/Code_Aster share one formulation
  L6 not available: no published thermo-structural numerical benchmark was integrated for this problem
  L7 not available: no measured deformation or stress data for this plate exists
REFERENCE COMPARISONS
  analytic_limit_comparison_verifies_implementation_only: uniform_free_exact MET (2.571e-13 dimensionless; tolerance 1e-06 dimensionless)
  analytic_limit_comparison_verifies_implementation_only: uniform_constrained_exact MET (2.445e-13 dimensionless; tolerance 1e-06 dimensionless)
  analytic_limit_comparison_verifies_implementation_only: bar_theory_mid_plate MET (2.637e-09 dimensionless; tolerance 0.03 dimensionless)
UNCERTAINTY
  known input uncertainty: none stated
  UNKNOWN input uncertainty: heat flux and sink temperature (declared), stress-free temperature (declared), E, nu, alpha, k (ASSUMED illustrative records), plate thickness and geometry (declared)
  model discrepancy: NOT QUANTIFIED: linear small-strain plane-stress idealisation, isotropic constant properties, 2-D symmetric-half model (unknown, not zero)
  model applicability: thermal solution checked against the declared property range [250.0, 450.0] K on every run; small strain and linear elasticity are assumed (the peak thermal strain is reported)
  benchmark applicability: analytic references only (bar_theory_mid_plate, uniform_constrained_exact, uniform_free_exact); analytic references are not numerical benchmarks and not experiments
SCIENTIFIC STATUS
  insufficient_evidence - derived by the existing credibility authority; the runtime supplies no validity record and no validation check, and this summary adds none
TRACE
  complete
```
