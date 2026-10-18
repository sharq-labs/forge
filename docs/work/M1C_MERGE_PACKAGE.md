# Draft PR-ready M1C package: transient vertex FV/Backward Euler

Suggested title: `Add bounded transient nonuniform vertex FV conduction with sparse execution`
Branch codex/m1c-transient-fv-1d, exact base
9b092d563507b0de3563c4209d42d6fc0772ea0a. Future draft targets codex/m1b-vertex-dual-state.
main -> #159 -> #160 -> #161 -> #162 -> M1B Draft#165 -> M1C local.
Checkpoint#158 independent. M1B published against M1A; earlier PRs untouched.
M1C local package only; no automatic publication or merge.
IMPLEMENTED / UNVERIFIED / UNCERTIFIED; NOT INTEGRATION-READY.

## Proposed description

Add a distinct transient Fourier model/vertex FV realization alongside unchanged
steady conduction. Use M1B intensive nodal temperature and integrated energy on
exact issued dual supports. Integrate explicit region storage and area over dual
volumes; form shared opposite face powers through series k*A resistances and sourced
contacts. No implicit area/rho/cp defaults or arithmetic averaging of conductivity jumps.

Backward Euler advances one exact declared window/dt. Both boundaries and volumetric
sources are mandatory. Positive storage admits transient both-Neumann. Dirichlet
endpoints retain half-volume energy and record reconstructed reservoir reactions.
Power-scaled sparse equations, explicit endpoint constraints and row/global residuals
admit actual provider output; actual totals distinguish internal faces, boundary
exchange and volumetric sources. Recovered Dirichlet reactions are not independent
physical conservation evidence.

Reuse MaterialPropertySet/MaterialState, KnowledgeSource, existing applicability/UQ
and numerical provider/execution records. Phase-constant scalar properties only;
physical mode refuses assumed properties and all modes reject interpolation/ranges.
Source hashes establish byte origin binding, not empirical validity. Actual source
claims remain caller-curated; the adapter does not prove parsing correctness or truth.

Sparse-only SuperLU provider uses FORGE's NumericalProvider protocol without existing
provider conditioning densification. Identity binds implementation/SuperLU bytes and
NumPy/SciPy versions. Steps bind exact grid/support, initial/current state/storage,
materials, BC/source, clock/window/dt and execution/build identities. Failed solve,
invalid output, conservation refusal or partial publication poisons continuation.
Residuals/UNKNOWN conditioning and uncertainty never become certified error bounds.

## Exact changed-file inventory relative to M1B

| File | Purpose |
| --- | --- |
| src/engcore/domains/thermal_models/conduction1d_transient_fv.py | New domain model/realization, declared materials/contacts, sparse provider, fixed-mesh BE session and step receipts |
| tests/test_m1c_transient_fv.py | Synthetic analytical, independent balance/refinement and adversarial designs, NOT RUN |
| docs/work/M1C_ARCHITECTURE_DECISION.md | Preimplementation formulation/compatibility decision, final corrected admission and census hold |
| docs/work/M1C_COMPATIBILITY_MATRIX.md | Exact affected/dependency references and integration impact |
| docs/work/M1C_STATIC_REVIEW.md | Independent A-J architecture/scientific static PASS with resolved findings |
| docs/work/M1C_MERGE_PACKAGE.md | This package and decisions/limits |
| docs/work/ACTIVE_PLAN.md | Current bounded task/stack and integration hold |
| docs/work/DEFERRED_VALIDATION.md | DV-129..132, NOT RUN |
| docs/work/PROGRESS.md | Publication, implementation/review corrections and actual static check results |

## Integration hold and owner decisions

M1C-C1: new required model is discovered by existing test_core_guards walker; static
expected population20 conflicts with certification-pinned EXPECTED_MODELS19
(lines199,534). No test execution or observed failure claimed. Do not hide the model,
weaken the guard or silently update a certified pin. Owner compatibility approval for
an intentional 19->20 count update and separate OD-3/certification handling is required
before integration. Other unexecuted compatibility failures may remain unknown.

Execution of DV-129..132 and predecessor recipes needs separate authorization. Real
physical sources, material envelope/phase qualification and boundary/source measurement
standing need actual owner/domain inputs; synthetic fixtures do not supply them.
Existing model applicability remains UNKNOWN. No Core Freeze change is proposed.

## Independent conservation and numerical study design

Specified Neumann/source cases compare independently computed continuous geometry
and external power totals to sums of returned energy; they do not reuse internal
balance helpers. Homogeneous Fourier face tests separately evaluate -(kA)dT/dx.
Dirichlet reaction test checks endpoint half-volume storage and face power but is
explicitly an algebraic reaction check. Uniform exponential manufactured transient
isolates BE order; sine profile uses exact analytical dual-average source for spatial
refinement. Expected orders/tolerances authored before execution, never tuned to runs.
Independent review PASS after two HIGH and one MEDIUM corrections; tests NOT RUN.

## Scientific limitations and M1D

One fixed 1D mesh, serial session. Positive phase-constant scalar material inputs;
constant per-region geometry, no lateral/spreading loss. Variable cross-sections are
quasi-1D series approximations, not general 3D solutions. Contacts require positive
integrated K/W resistance strictly inside an edge; no explicit jump at an existing
vertex, interface capacity or transient contact law. Linear zero-reference E=C*T,
no latent heat, nonlinear/state-dependent/anisotropic properties or multiphase.
Piecewise constant per-step regional sources/BCs are evaluated by declared BE end
values; no hidden time interpolation. Smooth-case spatial study is no global accuracy
guarantee at jumps/contacts. Phase-only input qualification is a declared mathematical
scope, not proven physical applicability. Geometry/physical input truth is not authenticated.

Read access to implementation and SuperLU binary is required for provider build identity;
backend packaging/import support and every numerical expectation remain UNVERIFIED.
Conditioning and numerical/model discrepancy stay UNKNOWN. Energy closure is numerical
arithmetic, never pointwise accuracy, experimental validation or certification.

M1D still must integrate time-window adaptation decisions, conservative remaps, solver
rebuild, cache/coupling acceleration invalidation, complete adaptive receipts, rollback
and adaptive numerical studies. M1C supplies none of those. Failed sessions must be
recreated explicitly; no silent retry or recovery claim. Full M1 requires executed
contextual evidence and CDAR fixtures plus owner gate decision; no maturity promotion.
