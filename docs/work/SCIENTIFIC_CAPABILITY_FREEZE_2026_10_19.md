---
ai_schema_version: 1
doc_id: FORGE-SCIENTIFIC-CAPABILITY-FREEZE-20261019
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: 8ec97064c35144405e3eba53a4282e90f8593b1c
evidence_level: STATIC_REVIEW
last_reviewed: 2026-10-19
supersedes: none
---

# FORGE — High-Yield Scientific Capability Freeze (CAP-01 / CAP-02 / CAP-03)

> **Status: PROPOSED design. It is not approved, not implemented and not executed.** No test, benchmark or assurance
> command was run for this report. Every code fact below comes from static reading of `origin/main`
> `8ec97064c35144405e3eba53a4282e90f8593b1c` (PR #172, BUY-01, merged), read in a detached read-only worktree
> `D:/forge-capfreeze-8ec97064`. The primary checkout `D:\forge-main-337519d1` is on
> `fix/p0-scientific-correctness-2026-10-18` at `abed661f`, **28 commits behind** that `origin/main`, and has untracked BVB/FDA
> reports. Nothing in it was modified except this one new, untracked file.
>
> Statements about PETSc, OpenMDAO, OpenTURNS, Dakota and SUNDIALS come from reference knowledge of those projects.
> They were **not re-fetched in this session**. Before any external API name below is coded, it is checked against the
> pinned release (Wave D entry condition).
>
> **Governance blocker (OD-CAP-0).** None of the three capabilities is inside the active epic's `allowed_scope`
> (`engrt.numerical_foundations`, `docs/project/scientific_capability_completion.json:917`). Three concurrent
> exceptions would trip the Completion Policy's anti-loophole rule. Placing the code under `src/engcore/numerical/**`
> just to fit that scope would be the loophole the rule forbids. Execution therefore starts with one owner decision
> (§7 Wave 0).

---

## 1. Executive Capability Table

| Capability | Current FORGE maturity | New additions | Reused existing components | External engines | Priority | Estimated implementation package |
|---|---|---|---|---|---|---|
| **CAP-01 Derivative Authority** | Not a ledger capability (no stage). One converged, frozen FD Jacobian (`hybrid_uq/sensitivity.py`, V2/V3, byte-pinned) that serves calibration UQ only. A single-step, unverified FD in `claims/analysis/sensitivity.py`. Analytic Jacobians exist inside solvers (SymPy, CSTR, heater, closed-form thermal partials) but are never records. No provider returns a derivative. No total derivative over any graph. | **11** (P0 5, P1 4, P2 2) | 14 | SymPy, SciPy (already in the tree); PETSc TS (P2, existing provider) | **P0** | Wave A + part of B (first package, §10). Then B, F. About 3 PRs. |
| **CAP-02 Reliability Engineering** | Absent. UQ yields intervals, never `P(limit violated)`. Ratings are encoded as model validity conditions, so today a rating violation looks the same as a refusal (`mcp/probabilistic_uq.py` refuses the whole study). `ConstraintDefinition` and `guard_band` exist; distributions exist only as uniform/normal in the claims and MCP layers. | **12** (P0 6, P1 4, P2 2) | 13 | OpenTURNS (WRAP, new, P1); Dakota (optional P2, existing provider env); SciPy | **P0 core / P1 engine** | Waves C, D. About 2–3 PRs. |
| **CAP-03 Generic Inverse Problems** | The generic core exists but is frozen: `engcore.inference` (V1) and `engcore.hybrid_uq` (V2/V3). It infers **parameters only**. The four-statement split (converged / identifiable / held-out / coverage) exists only in `studies/calibration_study.py`, hard-wired to TCR. The battery identifiability machinery is copied across three `benchmarks/` scripts. | **11** (P0 6, P1 3, P2 2) | 17 | SciPy (already wrapped by `calibrate`); Dakota LEARN only | **P0** | Wave E, then F. About 2 PRs. |

All 34 additions are new code that **wraps** frozen owners. **No P0 change edits a frozen symbol or a byte-pinned
file.** One P0 item, I5, adds a file in the certified `adequacy/**` area, which makes it OD-3. That item and every P1/P2
edit to a certified file are listed per wave (§7). `tests/test_core_api_layering.py` and `studies/calibration_study.py`
do not appear in `certification/current_core_v2.json` (checked statically).

**Correction (2026-10-19, found while drafting OD-CAP-0).** Every wave still needs owner-run OD-3:

* `tools/certification/recertification_scope.py` declares the `assurance_suites` trigger over `tests/**`, so any
  added or edited test invalidates the certificate until the gates are re-executed. FE-1 is included.
* `tests/test_core_api_layering.py` is the Core Freeze V1 reference `layering_and_package_classification`. Its
  V1-recorded sha256 (`fd83ea5d…`, `certification/core_freeze_v1.json`) already differs from the file at
  `8ec97064` (`5e2017f6…`).
* `pyproject.toml` is the `dependency_manifest` trigger (Wave D).

`python tools/forge_check.py --changed` reports these classes.

---

## 2. CAP-01 Derivative Authority

### 2.1 Current FORGE → gap

| Fact (file:line at `8ec97064`) | Consequence |
|---|---|
| `hybrid_uq/sensitivity.py:99` `central_difference`: nested step halving from `1e-5·range`, Richardson-style acceptance `err ≤ 1e-3·size + roundoff`, one-sided at bounds. It refuses non-convergence (`_DerivativeNotConverged` :91) and returns `(base, J, steps, one_sided, evaluations)`. | Scientifically sound. **Keep it and do not replace it.** It returns no error estimate, only "tolerance met". |
| `LocalSensitivity` :192: the Jacobian of predicted observations w.r.t. inference coordinates. `method ∈ {central_difference, supplied}` (:242). A supplied J is re-verified column by column against fresh FD to 1e-2 (:351). Frozen V2/V3, schema `hybrid_uq.local_sensitivity/1`, byte-pinned (`certification/current_core_v2.json:11516`). | It is bound to an `ObservationSet` and a calibration. It cannot describe "dT/dq of a QoI" or "dy/dx through a coupled system", and it carries no per-entry derivative unit. |
| `claims/analysis/sensitivity.py:135` `sensitivity_study`: one-shot central FD at 1% step, **no convergence check**, derivative unit not recorded. Feeds repair hypotheses (`diagnostics.py:360-424`). | Unverified derivatives reach diagnostics. Diagnostics are allowed to be hypotheses, but the record does not say the number is unverified. |
| Analytic sources exist but are not records: `numerical/symbolic.py:58` (exact SymPy Jacobian, identity `symbolic_srepr`), `compositionpacks/references/thermal_resistance.py:176-194` (closed-form ∂T/∂q, ∂T/∂g, ∂T/∂c, ∂T/∂T_amb, ∂T/∂T0), `domains/kinetics/cstr/solver.py:249`, `domains/electrical/heater_circuit.py:89`. | Free, independent second methods for cross-checking FD, unused for that purpose. |
| `providers/catalog.py:51` `ProviderCapability` has no derivative flag. `providers/records.py:53` `ProviderExecutionRecord.arrays` can carry arrays. No provider returns a Jacobian. | The provider boundary exists; only the derivative semantics are missing. |
| `PhysicsGraph` (`scientific/multiphysics/graph.py:138`, SCCs :499) and `SystemExecutionPlan` (`system_runtime/plan.py:123`, topological nodes) exist. Coupled solves are partitioned fixed points (`plan.py:503`). IQN-ILS holds an *approximate* inverse Jacobian (`execution/multiphysics/acceleration.py`). **No chain rule or total derivative anywhere.** | Total-derivative assembly needs no new graph. It must never admit the IQN approximation as a derivative. |
| `Quantity.__truediv__` refuses affine scales (`scientific/units/quantity.py:1361`); `spread_unit` (`system_runtime/plan.py:40`). | Derivative units can be derived honestly: dT/dq in K/W, never in degC/W. |

**Gap:** there is no canonical record of *a derivative of a named output, with respect to a named variable, at a bound
point, by an identified method, with its units, numerical error and verification standing*. As a result, FD, analytic,
symbolic and future provider derivatives cannot be compared, chained or admitted through one rule.

### 2.2 Decisions

* **BUILD:** the canonical derivative record, its units and coordinates, the cross-method verification, the admission
  boundary for provider derivatives, and total-derivative assembly over the existing graphs. These are authority, so
  FORGE owns them.
* **BUY (already in the tree):** SymPy for exact symbolic derivatives, SciPy for linear solves, and the existing FD engine.
* **LEARN from OpenMDAO:** the separation of *partials* (declared per component: exact, fd or cs) from *totals*
  (assembled by solving the unified derivatives equation with a linear solver), and `check_partials`/`check_totals`
  as FD-vs-declared comparisons. FORGE copies the pattern, not the framework.
* **WRAP later (P2), PETSc TSForward/TSAdjoint:** tangent and adjoint ODE parameter sensitivities through the
  existing PETSc provider (`numerical/providers.py:261`). FORGE consumes them; it never integrates adjoints itself.
* **SUNDIALS: DEFER.** The stub exists (`numerical/providers.py:307`). PETSc TS answers the same design question.

**Where total-derivative assembly belongs:** in a function over the **existing** structures, not in a new graph.

* A feed-forward DAG uses the chain rule in `SystemExecutionPlan.nodes` topological order. Each node's partials are
  keyed by `(node_id, output, input)`.
* A cyclic block uses `PhysicsGraph.strongly_connected_components` and the implicit-function form
  `(I − ∂F/∂y)·dy/dx = ∂F/∂x`. It is solved by the existing `SciPyLinearProvider`, at a *converged* coupled state
  bound by digest.
* Edge units come from `PortDefinition`. The assembly record stores the graph fingerprint and the partial-record
  digests. **A missing partial refuses the assembly; it never becomes zero.**

### 2.3 Additions

| ID | Addition | Existing owner reused | New/extended symbol | Scientific purpose | BUY/WRAP/LEARN/BUILD | Provider | Tests |
|---|---|---|---|---|---|---|---|
| D1 | Canonical derivative record | `Quantity`, `Uncertainty` (`source=NUMERICAL`), `ParameterIdentity`, `CanonicalProblem`/`ProblemBinding`, `ProviderExecutionIdentity`, `providers.identity.content_digest` | `quantitative.derivatives.DerivativeRecord` (schema `quantitative.derivative/1`), `DerivativeKind {PARTIAL, TOTAL}`, `DerivativeMethod {FD_CONVERGED, FD_SINGLE_STEP, CLOSED_FORM, SYMBOLIC, PROVIDER_TANGENT, PROVIDER_ADJOINT, CHAIN_RULE}`; `of: OutputRef`, `wrt: VariableRef` (shared, §5) | One identity for "∂(what)/∂(what), where, how, in what units, with what error". Binding to point, problem and model. | BUILD | — | A-D2, A-D7 |
| D2 | Converged-FD source adapter | `hybrid_uq.sensitivity.central_difference` and `LocalSensitivity` (read-only import; the frozen file is not edited) | `from_local_sensitivity(ls)`, `converged_partial(evaluator, point, …)` | Lifts the existing verified FD into records for *any* scalar/vector QoI evaluator, not only calibration observations. Error is stated as the acceptance bound (`≤1e-3` in the weighted norm), labelled "tolerance met", never "estimated error". | BUILD (adapter) | in-process | A-D1, A-D6 |
| D3 | Analytic and symbolic sources | `numerical.symbolic.SymbolicSystem.callables` and its `OperatorIdentity`; closed-form partials in `compositionpacks/references/thermal_resistance.py` | `from_symbolic_system(...)`, `from_closed_form(model_ref, partials, …)` | A second, independent method family, with no installs. | BUY (SymPy, existing) | in-process | A-D1, A-D4 |
| D4 | Cross-method verification | `providers.compare.ComparisonDeclaration` (declare-before-compare digest) and `shared_dependencies` (independence) | `DerivativeChallengeDeclaration`, `verify_derivative(a, b, decl) → DerivativeVerification {AGREE, DISAGREE, NOT_COMPARABLE}` | Admits a derivative as cross-checked only when two *different method families* agree within a tolerance declared before seeing results. Disagreement → REFUSED for downstream use. Agreement is numerical corroboration, never validation. | BUILD (LEARN `check_partials`) | — | A-D4, A-D5 |
| D5 | Coordinates and units | `ParameterTransform {IDENTITY, LOG}`, `Quantity` division and conversion, `spread_unit` | `DerivativeRecord.in_coordinates(...)`, `derivative_unit(of_unit, wrt_unit)` | Converts d/d ln x = x·d/dx and unit rescaling exactly. An affine `wrt` uses its delta unit; an affine result unit is refused. Every transform's identity is recorded. | BUILD | — | A-D2, A-D3 |
| D6 | Provider derivative boundary | `ProviderExecutionRecord.arrays`, `ProviderExecutionIdentity`; `ProviderCapability` gains a trailing `derivative_outputs: tuple[str, ...] = ()` (serialized only when non-empty, so existing capability digests are unchanged) | `derivative_from_provider_record(record, declaration)` | A provider *may compute* a tangent or adjoint. FORGE admits it only if names, units, shape, point and identity match the declaration. It is UNVERIFIED until D4. | BUILD boundary | any qualified provider | A-D11 |
| D7 | Total derivative on a DAG | `SystemExecutionPlan`/`PlanNode` order, `QuantityDependency` units | `assemble_total_derivative(plan, partials) → DerivativeRecord(kind=TOTAL, method=CHAIN_RULE)` + `TotalDerivativeAssembly` | dQoI/dx through a composed system, checked against whole-system FD. | BUILD (LEARN OpenMDAO totals) | — | A-D8 |
| D8 | Total derivative across a coupled cycle | `PhysicsGraph.strongly_connected_components`, `CouplingEdge`/`PortDefinition`, `SciPyLinearProvider` | same function, cyclic branch; reasons `PARTIAL_MISSING`, `ILL_CONDITIONED_COUPLING`, `NOT_AT_CONVERGED_STATE`, `APPROXIMATE_JACOBIAN_NOT_ADMITTED` | Sensitivity of a coupled converged solution via the implicit-function theorem, with an explicit refusal of the IQN approximation. | BUILD | — | A-D9 |
| D9 | Bridge into Hybrid UQ | `local_gaussian_posterior(..., sensitivity=)`, `_bind_supplied_sensitivity` (frozen; re-verifies by FD) | `to_supplied_local_sensitivity(record)` | Lets a cross-checked analytic or provider Jacobian enter the frozen V2 route through its **existing** trust boundary, with no frozen change. | BUILD (adapter) | — | A-D10 |
| D10 | Claims sensitivity labelled honestly (P2) | `claims/analysis/sensitivity.py` (certified `verdict_authority`) | the `ParameterSensitivity` value is wrapped in a `DerivativeRecord(method=FD_SINGLE_STEP)` with an UNVERIFIED standing and a derivative unit; an optional converged route through D2 | Stops an unverified one-shot FD from looking authoritative in diagnostics. | BUILD | — | new A-D12 (step-halving changes the number → reported) |
| D11 | PETSc tangent/adjoint provider (P2) | `numerical/providers.py:261` PETSc provider, `providers.catalog` probes | adapter producing `PROVIDER_TANGENT` / `PROVIDER_ADJOINT` records | Scalable ODE parameter sensitivities for large p; FORGE verifies them against D2 on small cases. | WRAP | PETSc TS via petsc4py (`petsc` extra) | A-D11 against a manufactured ODE |

**Scores** (Impact, Reuse, Cost [1 = cheap], Leverage, Risk [1 = low]):

| ID | Imp | Reuse | Cost | Lev | Risk | Class |
|---|---|---|---|---|---|---|
| D1 | 5 | 4 | 2 | 5 | 2 | **P0** |
| D2 | 4 | 5 | 1 | 4 | 1 | **P0** |
| D3 | 4 | 5 | 2 | 4 | 2 | **P0** |
| D4 | 5 | 4 | 2 | 5 | 2 | **P0** |
| D5 | 4 | 4 | 2 | 4 | 2 | **P0** |
| D6 | 4 | 4 | 3 | 4 | 3 | P1 |
| D7 | 4 | 3 | 3 | 4 | 3 | P1 |
| D8 | 4 | 3 | 4 | 4 | 4 | P1 |
| D9 | 3 | 5 | 2 | 3 | 2 | P1 |
| D10 | 3 | 4 | 3 | 3 | 3 | P2 (certified claims file → OD-3) |
| D11 | 4 | 3 | 5 | 3 | 4 | P2 (needs a qualified PETSc environment) |

### 2.4 First minimal slice

D1 + D2 + D3 + D4 + D5, plus D6's admission function **without** the `ProviderCapability` field (so no certified file is
touched). The scientific fixture is `thermal_resistance.analytical_terminal_state`, a real FORGE closed-form model:
converged FD against closed-form partials for q, g, c, T_amb and T0. The details are in §10.

### 2.5 Standing semantics

A `DerivativeRecord` **never carries a caller-supplied standing**. Standing comes only from the functions that produce
it:

* A converged FD record alone is `ADMITTED` with the qualifier `SINGLE_METHOD_CONVERGED`. This is exactly the authority
  the frozen V2 route already grants, so nothing regresses.
* D4 agreement adds `CROSS_METHOD_AGREEMENT`.
* An FD_SINGLE_STEP record gets `REVIEW`.
* A disagreement, non-convergence or binding mismatch gets `REFUSED`.

None of these is a scientific verdict, and sensitivity is never causality.

---

## 3. CAP-02 Reliability Engineering

### 3.1 Current FORGE → gap

| Fact | Consequence |
|---|---|
| No limit-state, failure-probability, FORM/SORM, design-point or importance-sampling code. `sria/decision/utility.py:370` "failure_probability" is computational failure. | Entirely new semantics. |
| `scientific/ir/constraints.py:136` `ConstraintDefinition(name, metric, operator, bound, tolerance)`; `ConstraintCheck` with a margin. | Reuse as the limit declaration. |
| `uq/budget`: correlation-aware RSS that refuses an undeclared correlation; `require_positive_semidefinite_correlation` (`matrix.py:30`); `guard_band`. No distributions in `uq/`. | Dependence refusal already exists as a pattern; input distributions do not exist at Core level. |
| Distributions: `claims/parameter_uq.py:72` (NORMAL/UNIFORM, independent PCG64, Wilks), `mcp/probabilistic_uq.py` (uniform/normal, LHS + Iman–Conover, refuses anything except `"independent"`). Both sit *above* the Core. | Two parallel vocabularies already. Reliability must not add a third. One Core-level input model is needed, with the others adapted to it later. |
| **Ratings are validity conditions:** `dc_applicability.py:543` `element_hot_spot_utilization ≤ 1`, `dc/models.py:477/513/696`. A sample over a rating → OUTSIDE_VALIDATED_DOMAIN → `mcp/probabilistic_uq.py:309-323` refuses the whole study. | **The most important design finding.** A rating exceedance today is indistinguishable from model inapplicability. Reliability needs a declared, owner-approved way to tell "the event happened" from "the model cannot speak here" (OD-REL-1). |
| `ValidityDomain.assess` (`scientific/models/definition.py:1496`) is a pure function of a context. | Per-sample applicability classification is possible without changing the core. |
| Model discrepancy: `hybrid_uq` `MODEL_DISCREPANCY_NOT_MODELLED`; `sria/uncertainty.py` `DiscrepancyKind` (claims layer). | Reliability must state "conditional on the model being exact" unless a discrepancy term is declared. |
| Dakota 6.16 already runs in a provider environment (`providers/discovery/dakota_runner.py`, raw output, no authority). OpenTURNS is NOT_INSTALLED, LGPL-3+ (untracked BVB licence audit row). | One engine is available now, the other needs an install decision. |

**Gap:** nothing turns a declared input model plus a declared engineering limit into `P(g(X) ≤ 0)` with its method
error, an independent challenge, and refusal semantics.

### 3.2 Decisions

* **WRAP OpenTURNS** for the numerical reliability algorithms: FORM (iHLRF/SQP/Cobyla), SORM (Breitung, Hohenbichler,
  Tvedt), importance sampling at the design point, subset sampling, and Nataf/Gaussian-copula transforms. The
  integration is in-process and lazily imported: the limit state is a FORGE callable that OpenTURNS calls through
  `PythonFunction`. Every `g` evaluation goes through FORGE's classifier and ledger, so FORGE, not OpenTURNS, counts
  the outcomes.
* **BUILD** the limit state, input-model semantics, study declaration, per-sample applicability classification,
  result record, challenge rule and refusal. Also **BUILD crude Monte Carlo with an exact Clopper–Pearson interval**
  (SciPy `beta`; about 30 lines). It is the *independent* challenge path. Using OpenTURNS's own MC to check OpenTURNS's
  FORM would not be independent.
* **Dakota: optional WRAP (P2).** Its `local_reliability` method is a second FORM implementation, run as a subprocess
  with a fork driver. It is also the fallback if OD-REL-2 refuses OpenTURNS in-process. The GSL/GPL boundary stays
  subprocess-only (BVB L-3).
* **Never** let a reliability result create a claim. Claims and MCP reachability are prohibited before the capability
  is FUNCTIONAL.

### 3.3 The six separated quantities

| Quantity | Where it lives | Rule |
|---|---|---|
| Input uncertainty | `ProbabilisticInputModel` marginals, each with `UncertaintySource` (MEASUREMENT / PARAMETER / …) and a cited basis | No basis → REFUSED. Never defaulted. |
| Measurement uncertainty | Only through a calibration posterior (CAP-03 → R9) or a marginal with `source=MEASUREMENT` | Never mixed into model discrepancy. |
| Model uncertainty | An optional additive discrepancy term on `g` with a declared distribution; otherwise the qualifier `MODEL_DISCREPANCY_UNMODELLED` | Unmodelled ≠ zero. Pf is then explicitly conditional on an exact model and is **not** a bound. |
| Failure probability | `ReliabilityResult.failure_probability` + the method's own interval | MC: Clopper–Pearson. FORM/SORM: approximation class, no statistical CI. |
| Engineering safety factor | `ReliabilityResult.deterministic_margin` (capacity/demand at the nominal point) | Reported beside Pf, never converted into or out of it. |
| Scientific support | **None produced.** | A later claims-layer kind decides. Risk policy sets the target Pf; it is never evidence. |

### 3.4 Required behaviours

| Situation | Behaviour |
|---|---|
| A UQ distribution is unsupported | `REFUSED (DISTRIBUTION_UNSUPPORTED)` before any evaluation (0 evaluations). |
| Input dependence is unknown | `REFUSED (DEPENDENCE_UNKNOWN)`. Independence is accepted only as `INDEPENDENT_DECLARED` with a basis. A Gaussian copula needs a PSD correlation (`require_positive_semidefinite_correlation`). |
| The limit state is discontinuous | FORM: `REVIEW (LIMIT_STATE_NOT_DIFFERENTIABLE)`, detected by a D2 non-convergence at the iterate or by an OpenTURNS non-convergence. MC still reports its interval. FORM's number is never the headline. |
| FORM and MC disagree | `REVIEW (METHOD_DISAGREEMENT)`. Both are reported, never averaged. Disagreement means FORM Pf lies outside the MC Clopper–Pearson 99% interval, or |β_FORM − β_MC| exceeds the declared tolerance. |
| The design point falls outside applicability | FORM result `REFUSED (DESIGN_POINT_OUTSIDE_APPLICABILITY)`. The study can fall back to an MC bracket with standing REVIEW. |
| Model validity is insufficient | A sample whose validity is anything other than satisfied (apart from the limit's own declared rating condition, per OD-REL-1) is `NOT_ASSESSABLE`. Pf is a bracket `[CP_lo(n_fail/n), CP_hi((n_fail+n_NA)/n)]`. If the upper bound exceeds the target, the standing is REVIEW. The sample count n is fixed in the digest-bound study declaration, so dropping NOT_ASSESSABLE samples cannot tighten the bound (removing evidence must not increase assurance). |
| Zero failures observed | Report only the one-sided upper bound `1 − α^(1/n)`. No point estimate and no β. |

Note on the design point when the rating *is* the limit (OD-REL-1): the FORM design point lies on `g = 0`, that is,
utilization exactly 1. That is **inside** the closed validity condition `≤ 1`. So FORM is evaluable at the boundary
even though the failure-side samples are not inside it.

### 3.5 Additions

| ID | Addition | Existing owner reused | New/extended symbol | Purpose | Engine/provider | Verification |
|---|---|---|---|---|---|---|
| R1 | Limit state | `ConstraintDefinition`/`ConstraintOperator`, `Quantity` | `quantitative.reliability.LimitState(constraint, limit_source, capacity_marginal=None, rating_conditions=())` | A declared engineering limit with a cited source. `g = capacity − demand` in a ratio-scale unit. Optional uncertain capacity. Names the validity conditions it *is*. | FORGE | A-R1, A-R8 |
| R2 | Probabilistic input model (shared, §5) | `UncertaintySource`, `require_positive_semidefinite_correlation`, `ParameterTransform` | `quantitative.inputs.ProbabilisticInputModel`, `Marginal`, `MarginalKind {NORMAL, LOGNORMAL, UNIFORM, TRUNCATED_NORMAL}`, `Dependence {INDEPENDENT_DECLARED, GAUSSIAN_COPULA, UNKNOWN}` | One Core-level input model for reliability, inverse priors and later the claims/MCP adapters. | FORGE | A-R4, A-R5 |
| R3 | Per-sample applicability classification | `ValidityDomain.assess`/`ValidityAssessment`, `DomainValidityContext` | `SampleOutcome {SAFE, FAILED, NOT_ASSESSABLE}`, `classify_sample(...)` | Separates "the limit was exceeded" from "the model cannot speak", per OD-REL-1. | FORGE | A-R9 |
| R4 | Study declaration | `CanonicalProblem`, `content_digest` | `ReliabilityStudy(limit_state, inputs, model_binding, primary_method, challenge_method, n_declared, target_cov, seed, tolerance)` | Pre-declared, digest-bound method plan and budget. Results with a different n or plan are refused. | FORGE | A-R9 (tamper) |
| R5 | Result record | `Uncertainty`, `hybrid_uq` `MODEL_DISCREPANCY_NOT_MODELLED` | `ReliabilityResult` (Pf, interval, β = −Φ⁻¹(Pf), design point in physical and standard space, importance factors α², counts by outcome, `deterministic_margin`, qualifiers, `Standing`) | Keeps all six quantities of §3.3 apart. | FORGE | A-R11, A-R12 |
| R6 | Crude MC + Clopper–Pearson | SciPy `stats.beta`, NumPy PCG64 seeded from the study digest | `run_monte_carlo(study, evaluator)` | The independent challenge, and the only method trusted with zero-failure bounds. | FORGE (BUILD, trivial) | A-R1, A-R10 |
| R7 | OpenTURNS provider | `ProviderCapability`, `python_package_probe`, `distribution_digest`, `ProviderExecutionIdentity` | `openturns_reliability(study, evaluator, method ∈ {FORM, SORM, IS_AT_DESIGN_POINT, SUBSET})` | Mature FORM/SORM/IS/subset with FORGE-owned evaluation accounting. | **WRAP OpenTURNS** | A-R1..A-R3, A-R6, A-R7 |
| R8 | Challenge rule + design-point verification | D2 `converged_partial`, R6 | `challenge_reliability(primary, challenge, decl)`; re-evaluates `g(x*)`, checks the KKT alignment `u* ∥ −∇G(u*)` with a D-record gradient, multistart uniqueness | Catches false FORM convergence, multiple design points and non-smooth limits. | FORGE | A-R3, A-R6, A-R7, A-R8 |
| R9 | Posterior and measurement inputs; discrepancy | `LocalGaussianPosterior` covariance (inference coordinates, LOG → lognormal), `RoutedPredictiveUncertainty` | `inputs_from_posterior(posterior)`, `DiscrepancyTerm` | Calibrated-parameter uncertainty (CAP-03) becomes a reliability input. Discrepancy is either declared or qualified as unmodelled. | FORGE | A-R11 |
| R10 | Electrothermal demonstration | `product/problem.py:3158` `example_electrothermal_payload` (Bourns PWR220T-20, permissible element temperature 428.15 K), `dc_applicability.element_hot_spot_utilization` | `domains/electrical/reliability_binding.py` (domain adapter; no new physics, not reachable from claims or MCP) | UQ → declared limit state → Pf → independent challenge on a real, sourced component limit. | OpenTURNS FORM vs FORGE MC | §8 demo gate |
| R11 | System event (P2) | R1, R6, R7 | `SeriesEvent(limit_states)` (union of the three ratings) | Pf for any rating exceeded. | OpenTURNS `UnionEvent` / MC | analytic two-limit case |
| R12 | Dakota second implementation (P2) | `claims/discovery_providers.run_provider` pattern, `providers.process.run_bounded` | `dakota_local_reliability(study)` (subprocess, fork driver) | Cross-implementation corroboration of FORM; fallback if OD-REL-2 refuses OpenTURNS. | WRAP Dakota | A-R1 |

**Scores:**

| ID | Imp | Reuse | Cost | Lev | Risk | Class |
|---|---|---|---|---|---|---|
| R1 | 5 | 4 | 2 | 4 | 2 | **P0** |
| R2 | 5 | 3 | 3 | 5 | 3 | **P0** |
| R3 | 5 | 4 | 3 | 4 | 4 | **P0** (needs OD-REL-1) |
| R4 | 4 | 4 | 2 | 3 | 2 | **P0** |
| R5 | 5 | 3 | 2 | 4 | 2 | **P0** |
| R6 | 4 | 4 | 1 | 3 | 1 | **P0** |
| R7 | 5 | 2 | 4 | 3 | 4 | P1 (install/licence OD-REL-2) |
| R8 | 5 | 3 | 3 | 4 | 3 | P1 |
| R9 | 4 | 4 | 3 | 5 | 3 | P1 |
| R10 | 4 | 4 | 3 | 3 | 3 | P1 (OD-REL-3) |
| R11 | 3 | 3 | 2 | 2 | 2 | P2 |
| R12 | 2 | 4 | 3 | 2 | 3 | P2 |

### 3.6 Minimal first engineering demonstration (R10)

* **Model:** the existing electrothermal example (resistor on an aluminium plate, LMR51430 source). Nothing new in
  physics.
* **Limit state:** `g = 1 − element_hot_spot_utilization`. The limit source is the Bourns PWR220T-20 datasheet record
  already cited in `product/problem.py`.
* **Inputs:** ambient temperature, supply voltage, resistance tolerance and element-to-body thermal resistance. Their
  distributions and bases are declared and preregistered **before** any run (OD-REL-3), and the scenario is not
  tuned afterwards to produce a convenient Pf.
* **Method:** FORM (OpenTURNS) as primary, crude MC as challenge. The MC n comes from the declared target CoV *after*
  a timed run of the forward model; that per-run cost is **UNMEASURED** today.
* **Expected honest outcomes:** `ADMITTED` with the qualifiers `CONDITIONAL_ON_INPUT_MODEL` and
  `MODEL_DISCREPANCY_UNMODELLED`, or `REVIEW`. Never a claim.
* **Why not a motor:** `systems/products/motor.py:41` names `winding_temperature_limit` only as a template parameter.
  There is no motor thermal model.

---

## 4. CAP-03 Generic Inverse Problems

### 4.1 Current FORGE → gap

| Fact | Consequence |
|---|---|
| `inference/`, frozen V1: `ParameterIdentity` (`parameters.py:161`), `CalibrationParameterSet` (:355), `GaussianObservation`/`ObservationSet` (`grid.py:38/96`, sigma required, spread unit), `CalibrationSpec` (`calibration.py:134`), `calibrate` (TRF `least_squares`), `CalibrationResult` (:263, deliberately no verdict field), `IdentifiabilityStatus` (:73), `assess_identifiability` (:931, frozen thresholds 0.95 / 1e6 / 1.0 / 8, which callers can only tighten), `ObservationSplit` (`split.py:127`, leakage refusals). | A strong, frozen, parameter-only core. **Do not build a second one.** |
| `hybrid_uq`, frozen V2/V3: local-Gaussian route with multistart, nonlinearity/bound/tail gates, `RoutedIdentifiability`, `route_uncertainty → HybridUQResult`. | Solution uncertainty and route validity already exist. |
| `studies/calibration_study.py`: the **four separate statements** (converged / identifiable / held-out / coverage), `held_out_verdict` (:258, χ² + bias tests, INCONCLUSIVE below n=7). It imports `domains.electrical.material` (TCR). | This is the inverse-study shape, but domain-bound. Its held-out scoring belongs in `adequacy` (layer 5, "held-out scoring", `tests/test_core_api_layering.py:34`). |
| Battery: `domains/battery/calibration.py` is a generic-shaped OCV adapter (byte-pinned). The 1RC identifiability and closure code lives only in `benchmarks/battery_1rc_*` (profile likelihood, block bootstrap, on-bound check, preregistered outcome strings), copied three times. | Promotable patterns, but the benchmarks themselves are untouchable (frozen preregistrations). |
| Targets: parameters only. Initial state is a declared input (`Thevenin1RCInitialState`, `RestedOcvCondition`). No source, boundary or field inversion. MCMC, regularization and Kalman: NOT FOUND. | Typed targets are honest only as **finite-dimensional declared model inputs**. |
| Parallel vocabularies: `uq/budget/identifiability.py:6` (condition number only), `scientific/corpus/calibration.py:59` `Identifiability`. | Do not use them. Record a mapping only. |
| `compositionpacks/references/thermal_resistance.py`: closed form `T(t) = T_s + (T0 − T_s)·e^(−g·t/c)`, `T_s = T_amb + q/g`, with analytic partials. | A real model with every honest target kind: PARAMETER/MATERIAL (g, c), INITIAL_STATE (T0), BOUNDARY_VALUE (T_amb), SOURCE_TERM (q). Steady-only data confound q and g, which gives a non-identifiable twin for free. |

**Gap:** there is no declaration that binds *which unknowns of which kind* to *which observations of which model
outputs*, with a sealed held-out set and an explicit method, and no result that keeps optimizer convergence,
identifiability, solution uncertainty, held-out adequacy and discrepancy on separate axes outside the TCR study.

### 4.2 Decisions

* **BUILD:** an `InverseProblem` declaration and an `InverseSolution` composite that **compose** `CalibrationSpec`,
  `calibrate`, `assess_identifiability` / `RoutedIdentifiability`, `route_uncertainty` and `ObservationSplit`. Frozen
  code is not edited.
* **LEARN from Dakota:** keep calibration *terms* (residuals) separate from calibration *data* (experimental values with
  declared variance types: scalar, diagonal, matrix). Treat configuration (state) variables as experiment conditions,
  and model discrepancy as an explicit opt-in, never implicit.
* **WRAP: nothing new.** SciPy is already wrapped by `calibrate`. Bayesian engines (emcee, PyMC, Dakota
  `bayes_calibration`) and PETSc TAO are DEFER.
* **First implementation without rewriting working code:**
  1. Re-express the TCR study (`studies/calibration_study.py`) through the generic path and require digest-equal
     `CalibrationResult` / `IdentifiabilityReport` (an equivalence proof).
  2. The `thermal_resistance` reference as an identifiable / non-identifiable pair.
  3. The battery OCV adapter (`ocv_forward_evaluator`) wrapped unchanged.

### 4.3 The five separated axes (`InverseSolution`)

| Axis | Source record (existing) | Values | Absent means |
|---|---|---|---|
| Optimizer convergence | `CalibrationResult.status` + `termination_reason` | CONVERGED / FAILED | — (always run) |
| Identifiability | `IdentifiabilityReport` or `RoutedIdentifiability`; optional profile (I7) and pre-data FIM (I8) | IDENTIFIABLE / WEAKLY / NOT (weakest of those run) | NOT_ASSESSED → REVIEW |
| Solution uncertainty | `HybridUQResult` / `RouteClaim` | SUPPORTED / DOWNGRADED / REFUSED | NOT_RUN → REVIEW |
| Held-out adequacy | `HeldOutValidation` (`held_out_verdict`) | PASS / FAIL / INCONCLUSIVE | NOT_RUN → REVIEW |
| Model discrepancy | `MODEL_DISCREPANCY_NOT_MODELLED` | NOT_MODELLED / declared | qualifier only |

**Standing rule (monotone, weakest axis wins):**

* `REFUSED` if the optimizer FAILED, if any claimed target is NOT_IDENTIFIABLE, if the route is REFUSED, or if held-out
  FAILED (model rejected for prediction).
* `REVIEW` if any target is WEAKLY identifiable, the route is DOWNGRADED, or any axis is INCONCLUSIVE or NOT_RUN.
* `ADMITTED` (with qualifiers) only otherwise.

No axis upgrades another, and there is no "success" field.

### 4.4 Additions

| ID | Addition | Existing owner reused | New/extended symbol | Purpose | Provider boundary | Tests |
|---|---|---|---|---|---|---|
| I1 | Inverse problem declaration | `CalibrationSpec`, `NoiseModel`, `CalibrationParameterSet`, `CanonicalProblem`; preregistration and dataset manifest **referenced by digest only** (they live in the claims layer) | `quantitative.inverse.InverseProblem(forward_binding, targets, observations, noise, split_digest, method, prereg_digest)` | One digest-bound statement of what is inferred, from what, by what, with which sealed held-out set. | method id only | A-I5 |
| I2 | Typed targets | `ParameterIdentity` (+ `ParameterBounds`, `ParameterTransform`) | `InverseTarget(kind, model_input, identity)`, `TargetKind {PARAMETER, MATERIAL_PROPERTY, INITIAL_STATE, BOUNDARY_VALUE, SOURCE_TERM, FIELD}`; **FIELD is always REFUSED** | Finite-dimensional unknowns of declared model inputs. A target the model does not declare as a settable input → `REFUSED (TARGET_NOT_A_DECLARED_MODEL_INPUT)`. | — | A-I6, A-I7 |
| I3 | Observation binding | `GaussianObservation`, `observation_content_digest`, `studies._require_declared_sigma` pattern, `FieldObservationOperator` (EXPERIMENTAL) | `ObservationBinding(observation_key, output: OutputRef, operator, sigma_source)` | Unit compatibility with the model output is checked **before** any forward evaluation. A missing or unsourced sigma → refused, never 1. | — | A-I4, A-I8 |
| I4 | Composite solution + standing | `CalibrationResult`, `IdentifiabilityReport`, `RoutedIdentifiability`, `HybridUQResult`, `HeldOutValidation` | `InverseSolution`, `InverseReason`, shared `Standing` (§5) | The §4.3 separation, made structural. | — | A-I2, A-I3, A-I10 |
| I5 | Held-out independence wiring | `ObservationSplit` (+ `require_scored_against_held_out`), `scientific/corpus/dataset.HoldoutLedger`, `held_out_verdict` **hoisted** to `adequacy/held_out.py` with an identity-preserving re-export in `calibration_study.py` | `solve_inverse_problem(...)` sequencing | The held-out set is sealed (digest in I1) before calibration and scored only after. The hoist removes the core → domains import. | — | A-I5, A-I10 |
| I6 | First instances | `calibration_study` TCR path, `thermal_resistance.analytical_terminal_state`, `domains/battery/calibration.ocv_forward_evaluator` | test-level bindings only | Proves the abstraction reproduces existing results (digest equality) and handles every honest target kind. | SciPy TRF via `calibrate` | A-I1, A-I2, A-I12 |
| I7 | Profile-likelihood identifiability | `calibrate` (nuisance re-optimization), `assess_identifiability` thresholds (tighten only) | `profile_likelihood(problem, target, grid)`; identified iff ΔNLL ≥ χ²₁,₀.₉₅/2 = 1.92 on both sides within bounds | A non-Gaussian identifiability check, promoted from the benchmark idea with a likelihood-ratio threshold (the benchmark's ≥10% SSE rule stays where it is). | SciPy | A-I9 |
| I8 | Pre-data identifiability from derivatives | D1/D2 records, frozen `hybrid_uq.identifiability.classify` | `design_identifiability(problem, design, nominal)` (FIM = JᵀΣ⁻¹J) | Predicts weak identifiability of a planned experiment before data. Feeds experiment design. | — | A-I11 |
| I9 | Inverse method boundary | `CalibrationSpec.method`, `MultistartPolicy`, `run_provider` pattern | `InverseMethod {BOUNDED_LS_TRF, POSTERIOR_GRID, LOCAL_GAUSSIAN}` (+ future ids, refused until wrapped) | A method returns estimates only. FORGE re-derives identifiability and UQ through its own routes and never trusts an optimizer's covariance. | the declared method | A-I3, A-I12 |
| I10 | Gaussian prior / Tikhonov (P2) | `scientific/corpus/calibration.PriorSource`, R2 marginals | `PriorDeclaration`, explicit prior-residual block (never pseudo-observations) | Regularized parameter inversion with a cited prior. It needs its own route because `gaussian_grid_posterior` is uniform-prior only. | SciPy `least_squares` (direct) | prior-dominance test |
| I11 | Coupled identifiability (P2) | D7/D8 total derivatives, I8 | `coupled_identifiability(graph, partials, design)` | Detects parameters confounded across subsystems (Genesis §13.10). | — | two-subsystem confounded case |

**Scores:**

| ID | Imp | Reuse | Cost | Lev | Risk | Class |
|---|---|---|---|---|---|---|
| I1 | 5 | 4 | 2 | 4 | 2 | **P0** |
| I2 | 4 | 4 | 2 | 4 | 3 | **P0** |
| I3 | 4 | 5 | 2 | 4 | 2 | **P0** |
| I4 | 5 | 5 | 2 | 4 | 2 | **P0** |
| I5 | 4 | 5 | 2 | 3 | 3 | **P0** (the hoist touches a certified V1 area → OD-INV-1 / OD-3) |
| I6 | 4 | 5 | 3 | 3 | 2 | **P0** |
| I7 | 4 | 3 | 3 | 3 | 3 | P1 |
| I8 | 4 | 4 | 2 | 4 | 2 | P1 |
| I9 | 3 | 4 | 2 | 3 | 2 | P1 |
| I10 | 3 | 3 | 3 | 2 | 4 | P2 |
| I11 | 4 | 3 | 4 | 4 | 4 | P2 |

---

## 5. Shared Architecture

**Dependency graph (derived from the code, not forced):**

```text
inference (frozen) ─┬─> quantitative.refs / standing / inputs ──┬─> derivatives ──┬─> inverse (I8, I11)
hybrid_uq (frozen) ─┤                                             │                 └─> reliability (R8 design-point check)
uq (frozen)        ─┤                                             ├─> reliability (R1–R7) <── inverse posterior (R9)
providers          ─┘                                             └─> inverse (I1–I7, I9)
```

* Reliability's core (R1–R6) does **not** need Derivative Authority. Only its verification (R8) does. So Wave C runs in
  parallel with Wave B.
* Inverse problems need derivatives only for I8 and I11. The core (I1–I6) runs on the frozen routes.
* The arrow "inverse → parameter uncertainty → reliability" is real and goes through R9
  (`LocalGaussianPosterior` → `ProbabilisticInputModel`).

**One new package, one layer slot, one certification area.** The proposal is a single package
`src/engcore/quantitative/`, placed at layer 8 in `tests/test_core_api_layering.py` (above `studies`):

* Subpackages: `derivatives/`, `reliability/`, `inverse/`.
* Shared modules: `refs.py`, `standing.py`, `inputs.py`.
* It may import `scientific`, `data`, `inference`, `uq`, `hybrid_uq`, `adequacy`, `providers` and `numerical`. It must
  not import `claims`, `sria`, `mcp`, `domains`, `product` or `systems`.
* Domain bindings live in `domains/`, which sits above it.
* When the capability reaches FUNCTIONAL, it gets one new certification `ScopeArea` (`CORE_CERTIFIED`) and one OD-3,
  instead of one per wave (OD-CAP-1).

**Shared primitives, designed once:**

| Primitive | Composes (existing) | Used by |
|---|---|---|
| `OutputRef(model: ModelReference, quantity, unit, conditions_digest)` | `ModelReference`, `Quantity` units, the observation key convention `cond:obs` | D1 `of`, R1 demand, I3 binding |
| `VariableRef(kind, identity, transform)`; kinds `PARAMETER / INPUT / STATE / INITIAL_STATE / BOUNDARY_VALUE / SOURCE_TERM` | `ParameterIdentity`, `ParameterTransform` | D1 `wrt`, R2 marginals, I2 targets |
| `Standing(outcome: StandingOutcome {ADMITTED, REVIEW, REFUSED}, reasons, qualifiers)` + `weakest(...)` | `RouteClaim` ordering (pattern only) | D-, R-, I-results. **One** enum, per-capability closed reason enums, no "SUPPORTED" member. |
| `ProbabilisticInputModel` | `UncertaintySource`, PSD correlation check | R2, R9, I10; later adapters for `claims/parameter_uq` and `mcp/probabilistic_uq` (adapters only, not rewrites) |
| Challenge declaration (declare-before-compare, independence) | `providers.compare.ComparisonDeclaration`, `shared_dependencies` | D4, R8 |
| Content identity | `providers.identity.content_digest`, `ProviderExecutionIdentity` | every record |
| Provider execution | `ProviderCapability`, probes, `run_bounded` / `run_provider` pattern | D6, D11, R7, R12 |

**Duplicates explicitly prevented:**

* No new uncertainty vocabulary (`Uncertainty` and `UncertaintySource` are reused).
* No new identifiability enum (the frozen `IdentifiabilityStatus` is reused, and the `uq/budget` and corpus variants
  are recorded as non-canonical).
* No second graph (`SystemExecutionPlan` and `PhysicsGraph` are reused).
* No new evidence or validation record: none of these capabilities produces Evidence or a `ValidationLevel`.
* No second distribution vocabulary going forward.

---

## 6. BUY / WRAP / LEARN / BUILD Matrix

| External project | Capability | Decision | What we use | What we explicitly do NOT use |
|---|---|---|---|---|
| **OpenTURNS** (LGPL-3+, not installed) | CAP-02 | **WRAP** (P1), in-process lazy import, optional extra, OD-REL-2 | FORM, SORM, importance sampling at the design point, subset sampling, Nataf/Gaussian-copula iso-probabilistic transforms, event/threshold machinery | distribution *fitting* as evidence; its probability as a verdict; metamodels (kriging/PCE) as qualified surrogates; its sensitivity analysis; its own MC as the independent challenge |
| **Dakota** (LGPL-2.1+, conda build links GSL GPL-3+; executes in the provider env) | CAP-03, CAP-02 | **LEARN** (inverse architecture); optional **WRAP** (P2, `local_reliability`, subprocess only) | calibration terms vs data with variance types, configuration variables, explicit discrepancy opt-in; a second FORM implementation | `bayes_calibration` posteriors as FORGE posteriors; any Dakota output as UQ authority; in-process bundling |
| **OpenMDAO** | CAP-01 | **LEARN** | partials vs totals; unified derivatives equation solved by a linear solver; `check_partials` / `check_totals` | the framework, its Problem/Group model, drivers, its derivative coloring |
| **PETSc** (petsc4py, existing provider; L-2 licence variant caveat) | CAP-01 | **WRAP** (P2) | TSForward tangent and TSAdjoint adjoint sensitivities, `RHSJacobianP` | TAO optimizers as calibration; its convergence reason as scientific acceptance; DMPlex |
| **SUNDIALS** | CAP-01 | **DEFER** | — (CVODES/IDAS answer no question PETSc TS leaves open; the stub stays) | — |
| SciPy / SymPy (already dependencies) | all | **BUY** (existing) | `least_squares` (via `calibrate`), `stats.beta`/`norm`, linear solves; exact symbolic Jacobians | `least_squares` covariance / `jac` as identifiability evidence |

---

## 7. Implementation Waves

| Wave | Content | Depends on | Certified files touched | OD-3 |
|---|---|---|---|---|
| 0 | Owner decisions | — | none | — |
| A | Shared primitives + D1, D2, D3, D5 + D6 admission function (no catalog edit) + D4 | OD-CAP-0, OD-CAP-1 | no certified source; new tests (`tests/**`) and `tests/test_core_api_layering.py` (Core Freeze V1 reference) | yes (tests) |
| B | D6 catalog field, D9 bridge | A | `providers/catalog.py`, tests | yes |
| C | R1–R6 (MC only) | A (refs, standing, inputs); OD-REL-1 for R3 | no certified source; tests | yes (tests) |
| D | R7–R10 (OpenTURNS, challenge, posterior inputs, demo) | C, A (D2 for R8), OD-REL-2, OD-REL-3 | `pyproject.toml` optional extra (`dependency_manifest` trigger), tests | yes |
| E | I1–I6 | A; OD-INV-1 for the I5 hoist | `adequacy/held_out.py` (new in a V1 area), `studies/calibration_study.py` (re-export), tests | yes |
| F | D7, D8, I7, I8, I9, R9 if not done | A, B, E | no certified source; tests | yes (tests) |
| G (P2) | D10, D11, R11, R12, I10, I11 | as listed | `claims/analysis/sensitivity.py` (D10), tests | yes |

### Wave 0 — owner decisions (no code)

| ID | Decision | Recommendation |
|---|---|---|
| **OD-CAP-0** (blocking) | Scope authority. The three capabilities are outside `engrt.numerical_foundations.allowed_scope`. | One reviewed ledger change (ledger + checker + `tests/test_capability_completion.py` + PR template) that adds `src/engcore/quantitative/**` and three gates (DA-1, RE-1, IP-1) to the program, bound by the CDAR physics-agnostic rule. The alternative is to name it as the next epic. **Not** three exceptions, and **not** placement under `numerical/**`. |
| **OD-CAP-1** | Layer slot 8 for `quantitative`, and one future certification ScopeArea | Approve the slot now; the area at FUNCTIONAL. |
| **OD-REL-1** | Is a sample that violates only the limit's own declared *rating* condition, with every physics-validity condition satisfied, FAILED (rather than NOT_ASSESSABLE)? | Yes, but only for conditions the domain declares as ratings (`dc_applicability` names them). The sign of `g` beyond a rating is trusted only where physics validity holds. |
| **OD-REL-2** | OpenTURNS: version pin, in-process LGPL-3+ use, vendored `.so` licence inventory (BVB: UNVERIFIED), install location | Optional extra `reliability = ["openturns==<pinned>"]` after the inventory; the Dakota subprocess is the fallback. |
| **OD-REL-3** | Demo input distributions and their sources, preregistered | Owner names the bases (datasheet tolerances, a declared ambient scenario). |
| **OD-INV-1** | Hoist `HeldOutValidation`/`HeldOutMetrics`/`held_out_verdict` into `adequacy/held_out.py` with identity-preserving re-exports | Yes (same class objects, enum values unchanged). |

**Exit:** OD-CAP-0 and OD-CAP-1 decided. The others are decided before their wave.

### Wave A — shared primitives and the derivative record

* **New files:**
  * `src/engcore/quantitative/__init__.py`, with the layer contract in its docstring;
  * `quantitative/refs.py`, `quantitative/standing.py`;
  * `quantitative/derivatives/__init__.py`, `record.py`, `sources.py`, `transforms.py`, `verification.py`, `provider.py`.
* **Edited:** `tests/test_core_api_layering.py`, to add `"quantitative"` at index 8 and a "must not import domains/claims" assertion.
* **Tests:** `tests/quantitative/test_refs.py`, `test_standing.py`; `tests/quantitative/derivatives/test_record.py`,
  `test_fd_source.py`, `test_symbolic_source.py`, `test_closed_form_thermal.py`, `test_transforms.py`,
  `test_verification.py`, `test_provider_admission.py`.
* **Exit:**
  * A-D1..A-D7 and A-D11 executed, with the exact command and result appended to PROGRESS;
  * `python tools/forge_check.py --changed` failure set equal to pristine `origin/main`;
  * no frozen snapshot or byte-pinned file changed (`git diff --stat` shows only new files plus the layering test).

### Wave B — provider flag and Hybrid UQ bridge

* **Edited:** `src/engcore/providers/catalog.py`, adding the trailing `derivative_outputs` field, emitted only when
  non-empty.
* **New:** `quantitative/derivatives/bridge.py`.
* **Tests:** `test_bridge_hybrid_uq.py` (A-D10), `tests/providers/test_capability_derivative_outputs.py` (existing
  capability digests unchanged).
* **Exit:** A-D10 passes; capability digest stability is shown; OD-3 recorded as pending.

### Wave C — reliability core

* **New:** `quantitative/inputs.py`; `quantitative/reliability/__init__.py`, `limit_state.py`, `study.py`,
  `classify.py`, `montecarlo.py`, `result.py`.
* **Tests:** `tests/quantitative/reliability/test_inputs.py` (A-R4, A-R5, PSD), `test_limit_state.py`,
  `test_classify.py` (A-R9), `test_montecarlo.py` (A-R1 MC, A-R2 MC, A-R7 MC, A-R10), `test_result_axes.py`
  (A-R11, A-R12).
* **Exit:** every MC acceptance number in §8 met; zero evaluations on every pre-evaluation refusal.

### Wave D — OpenTURNS, challenge and demonstration

* **Entry conditions:** OD-REL-1, OD-REL-2 and OD-REL-3 decided; OpenTURNS API names checked against the pinned
  release; provider tests governed by the existing skip-admission rule. Provider-environment tests must not appear as
  unexpected skips in hardened runs, and there are no xfails.
* **New:** `quantitative/reliability/openturns_provider.py`, `challenge.py`, `posterior_inputs.py`;
  `src/engcore/domains/electrical/reliability_binding.py`.
* **Edited:** `pyproject.toml` (optional extra).
* **Tests:** `test_openturns_form.py` (A-R1..A-R3, A-R6..A-R8), `test_challenge.py`, `test_posterior_inputs.py`;
  `tests/domains/electrical/test_reliability_demo.py`.
* **Exit:** analytic gates met. The demo result is recorded as a design finding, not as evidence, and no ledger stage
  is asserted.

### Wave E — inverse abstraction

* **New:** `quantitative/inverse/__init__.py`, `problem.py`, `binding.py`, `solution.py`, `run.py`;
  `src/engcore/adequacy/held_out.py`.
* **Edited:** `src/engcore/studies/calibration_study.py`, which keeps `HeldOutValidation`, `HeldOutMetrics` and
  `held_out_verdict` as re-exports of the same objects.
* **Tests:** `tests/quantitative/inverse/test_problem.py` (A-I4, A-I6, A-I7, A-I8), `test_solution_axes.py`
  (A-I2, A-I3, A-I10), `test_tcr_equivalence.py` (A-I12), `test_thermal_reference_inverse.py` (A-I1),
  `test_battery_ocv_instance.py`, `test_held_out_independence.py` (A-I5); plus the existing calibration-study tests
  unchanged.
* **Exit:** TCR digest equality; existing calibration-study test files unchanged and their outcomes recorded; OD-3
  pending.

### Wave F — cross-capability

* **New:** `quantitative/derivatives/assembly.py`; `quantitative/inverse/profile.py`, `design_identifiability.py`,
  `methods.py`.
* **Tests:** A-D8, A-D9, A-I9, A-I11.
* **Exit:** chain-rule and coupled totals agree with whole-system FD; I8's prediction is confirmed by the post-data
  route on the same design.

### Wave G — P2 follow-ups

D10, D11, R11, R12, I10, I11, each with its own acceptance test listed in §2–§4.

---

## 8. Acceptance Tests

All are numerical and scientific, all are executed, and none is a mock presented as a real run. They use fixed seeds.
Expensive coverage campaigns carry the `expensive` marker.

### Derivative Authority

| ID | Case | Pass criterion |
|---|---|---|
| A-D1 | `thermal_resistance` closed-form ∂T/∂{q, g, c, T_amb, T0} vs converged FD (D2) at 5 seeded points | relative column error ≤ 2·10⁻³; the FD record's stated tolerance covers the true error at every point |
| A-D2 | Units | ∂P[W]/∂V[V] → W/V; rescaling to mW/V gives exactly ×10³; wrt degC is stored per kelvin (delta); a degC result unit is refused |
| A-D3 | Log coordinates | ∂y/∂ln x = x·∂y/∂x to 10⁻¹² relative (analytic); FD in log vs natural agree within 10⁻³ |
| A-D4 | Analytic partial deliberately scaled ×1.05 | DISAGREE → REFUSED; a tolerance declared after the results → refused (digest order) |
| A-D5 | FD vs FD with a different step | NOT_COMPARABLE as a cross-method check (same method family) |
| A-D6 | `|x|` at 0 and a step function | FD non-convergence propagates as REFUSED; no number is emitted |
| A-D7 | A record used at a different point or problem digest | refused |
| A-D8 | Two-node DAG `y = g(h(x))` | chain-rule total vs whole-system FD ≤ 10⁻³; one missing partial → REFUSED (not zero) |
| A-D9 | Two-participant linear cycle `y1 = a·y2 + b·x`, `y2 = c·y1` | dy1/dx = b/(1 − ac) to 10⁻¹⁰; `ac → 1` → ILL_CONDITIONED_COUPLING; an IQN-approximate input → APPROXIMATE_JACOBIAN_NOT_ADMITTED |
| A-D10 | A cross-checked analytic record → supplied `LocalSensitivity` | accepted by the frozen `_bind_supplied_sensitivity`; a perturbed copy is refused **by the frozen code itself** |
| A-D11 | Test-local provider record (labelled synthetic) carrying a derivative array | admitted only with matching names, units, shape, point and identity; UNVERIFIED until D4 |

### Reliability

| ID | Case | Pass criterion |
|---|---|---|
| A-R1 | g = R − S, R ~ N(10, 1), S ~ N(10 − 3√2, 1), independent: β = 3, Pf = Φ(−3) = 1.3499·10⁻³ | FORM β within 10⁻⁶ relative; α² = (0.5, 0.5) within 10⁻⁶; MC n = 2·10⁵: the Clopper–Pearson 99% interval contains 1.3499·10⁻³ |
| A-R2 | ln R − ln S, lognormal with σ_ln = 0.1 each, β = 3 | FORM exact in standard space (β within 10⁻⁶); MC interval contains Φ(−3) |
| A-R3 | Parabolic `g(u) = 3 − u1 + 0.1·u2²` (κ = 0.2) | SORM (Breitung) within 5% of Gauss–Hermite quadrature of the exact Pf; FORM vs MC flagged METHOD_DISAGREEMENT → REVIEW, never averaged |
| A-R4 | Dependence UNKNOWN | REFUSED, 0 evaluations |
| A-R5 | An undeclared marginal kind, or a non-PSD correlation | REFUSED, 0 evaluations |
| A-R6 | Step limit state | FORM → REVIEW (LIMIT_STATE_NOT_DIFFERENTIABLE); MC interval contains 1 − Φ(c) |
| A-R7 | Symmetric series `g = min(3 − u1, 3 + u1)`: Pf = 2Φ(−3) = 2.6998·10⁻³ | multistart FORM → REVIEW (MULTIPLE_DESIGN_POINTS); the MC (n = 2·10⁵) interval contains 2Φ(−3) and excludes Φ(−3) |
| A-R8 | A validity range `u1 ≤ 2.5` with the design point at u1 = 3 | FORM REFUSED (DESIGN_POINT_OUTSIDE_APPLICABILITY) even though a number was computed |
| A-R9 | 1% of samples NOT_ASSESSABLE (independent of g); target Pf 10⁻³ | bracket upper ≥ CP_hi((n_f + n_NA)/n) → REVIEW; a result with n ≠ n_declared, or a tampered sample ledger, is refused |
| A-R10 | Zero failures in n = 3000 | only an upper bound, 1 − 0.05^(1/3000) ≈ 9.98·10⁻⁴; no point Pf and no β |
| A-R11 | Discrepancy unmodelled | qualifier present; the reliability package has no import path to `claims` (AST check) |
| A-R12 | Nominal safety factor | `deterministic_margin` reported; Pf unchanged by it; no field converts between them |
| Demo | Electrothermal, PWR220T-20 hot-spot limit | preregistered inputs; FORM vs MC challenge executed; outcome ADMITTED (with qualifiers) or REVIEW recorded honestly; per-run cost measured first |

### Inverse Problems

| ID | Case | Pass criterion |
|---|---|---|
| A-I1 | Thermal reference, unknown g, c (MATERIAL), T0 (INITIAL_STATE); 30 observations, σ = 0.1 K over [0, 3τ] | CONVERGED, IDENTIFIABLE; each estimate within 3 posterior sd of truth; `expensive`: 200 datasets, the Wilson interval of 95% coverage contains 0.95 |
| A-I2 | Steady-state data only, q and g unknown | CONVERGED **and** NOT_IDENTIFIABLE → REFUSED, with both axes visible |
| A-I3 | Single-exponential fit to a two-time-constant truth | CONVERGED + IDENTIFIABLE + held-out FAIL → REFUSED (MODEL_REJECTED_HELD_OUT) |
| A-I4 | Observation in V bound to an output in K | refused with 0 forward evaluations |
| A-I5 | Held-out shares a condition_id or content digest, or is declared after calibration | `DataLeakageError` / refused |
| A-I6 | INITIAL_STATE target on a model without a settable T0 | REFUSED (TARGET_NOT_A_DECLARED_MODEL_INPUT) |
| A-I7 | FIELD target | REFUSED (FIELD_INVERSION_UNSUPPORTED) |
| A-I8 | Sigma missing, or stated in delta-degC | missing → refused; 0.1 delta-degC equals 0.1 K |
| A-I9 | Profile likelihood | A-I1: rise ≥ 1.92 on both sides; A-I2: flat (< 1.92) → NOT identifiable, consistent with the local route |
| A-I10 | Remove held-out observations; held-out n < 7 | standing never improves; INCONCLUSIVE → REVIEW |
| A-I11 | Pre-data FIM, all t < 0.05τ | c, g predicted WEAKLY or NOT identifiable before data, confirmed post-data |
| A-I12 | TCR study through the generic path | `CalibrationResult` and `IdentifiabilityReport` digests equal those of `calibration_study` |

---

## 9. Deferred Work

**Not to be built by FORGE, ever.** These are consumed from providers when a named claim needs them:

* adjoint and tangent ODE/DAE integrators, and checkpointed trajectories (PETSc TS);
* automatic differentiation engines;
* FORM/SORM optimizers (HL-RF/iHLRF) and Nataf/Rosenblatt transforms;
* importance and subset sampling;
* copula libraries;
* MCMC samplers;
* nonlinear least-squares and trust-region optimizers;
* PDE-constrained optimization (TAO);
* field regularization and regularization-parameter selection (L-curve, GCV);
* Kalman / data-assimilation filters;
* polynomial chaos and kriging metamodels;
* Sobol/Morris estimators.

**Deferred ideas (with triggers):**

| # | Idea | Why deferred | Trigger |
|---|---|---|---|
| 1 | SUNDIALS CVODES/IDAS provider | PETSc TS covers it | a DAE claim PETSc cannot serve |
| 2 | FEniCSx / dolfinx PDE adjoints | no field-derivative claim; E-gates first | an E1/E2 claim needing dJ/dk(x) |
| 3 | Complex-step derivatives | models are not complex-safe (`Quantity`) | a complex-safe model family |
| 4 | AD (JAX etc.) | dependency and identity cost | a measured FD cost bottleneck |
| 5 | Global sensitivity (Sobol/Morris, SALib) | sensitivity ≠ causality; no consuming decision | an experiment-design claim that needs it |
| 6 | Retaining `calibrate`'s `outcome.jac` | frozen V1 contract; D2 reconstructs it | Core Freeze V5 review |
| 7 | Claims/MCP probability-of-exceedance claim kind | prohibited before FUNCTIONAL | CAP-02 FUNCTIONAL + ledger |
| 8 | Time-variant reliability (outcrossing, PHI2) | needs a stochastic-process input model | a degradation/lifecycle claim |
| 9 | RBDO (reliability-based design optimization) | needs R-core plus the synthesis track | Track B synthesis milestone |
| 10 | Metamodel-based reliability (AK-MCS) | qualified-surrogate semantics absent | a qualified-ROM contract |
| 11 | Bayesian updating of Pf | needs I10 priors + R9 | after I10 |
| 12 | Additional marginal families (Weibull, Gumbel, …) | no sourced need | a cited limit or input that needs one |
| 13 | FIELD inversion | no field prior/regularization contract | a field-observation claim |
| 14 | MCMC posterior route (emcee/PyMC/Dakota) | grid + local routes cover current p | p beyond the grid cap with a non-Gaussian posterior |
| 15 | State estimation / Kalman | no sequential-data claim | a digital-twin tracking claim |
| 16 | Dakota `bayes_calibration` wrap | LEARN is enough now | item 14 |
| 17 | PETSc TAO for inversion | SciPy TRF is adequate at current scale | measured scale need |
| 18 | Consolidating `uq/budget/identifiability.py` and the corpus `Identifiability` | frozen/byte-pinned; a mapping record is enough | Core Freeze V5 |

---

## 10. Recommended First Execution Package

**Package FE-1: "Derivative record with one cross-method path".** Prerequisite: OD-CAP-0 and OD-CAP-1. No install and
no edit to a frozen or certified source file.

1. **Shared primitives.**
   * New: `src/engcore/quantitative/__init__.py`, `refs.py` (`OutputRef`, `VariableRef`, `VariableKind`),
     `standing.py` (`StandingOutcome`, `Standing`, `weakest`).
   * Edited: `tests/test_core_api_layering.py`, slot 8.
2. **D1 + D5.** `quantitative/derivatives/record.py`: `DerivativeRecord`, `DerivativeKind`, `DerivativeMethod`,
   `derivative_unit`, `in_coordinates`; schema `quantitative.derivative/1`; digest via `content_digest`.
3. **D2.** `quantitative/derivatives/sources.py::from_local_sensitivity` and `converged_partial`. These call
   `hybrid_uq.sensitivity.central_difference` read-only.
4. **D3.** `sources.py::from_symbolic_system` (SymPy `SymbolicSystem`) and `from_closed_form` (thermal reference
   partials).
5. **D4.** `quantitative/derivatives/verification.py`: the declare-before-compare challenge, method-family
   independence, `DerivativeVerification`.
6. **D6 (admission only).** `quantitative/derivatives/provider.py::derivative_from_provider_record`. The
   `ProviderCapability` field waits for Wave B.
7. **Tests:** A-D1, A-D2, A-D3, A-D4, A-D5, A-D6, A-D7, A-D11 under `tests/quantitative/`.
8. **Gate commands** (run, recorded verbatim in PROGRESS, failure set compared with pristine `origin/main`):
   `python tools/forge_check.py --changed`, then the targeted
   `python -m pytest tests/quantitative tests/test_core_api_layering.py -q`. Run them with the repository venv
   interpreter and a redirected temp dir.
9. **Exit:**
   * every listed acceptance criterion met;
   * zero changed bytes in frozen or certified files;
   * `forge-scientific-review` read-only review of the standing semantics (§2.5);
   * no ledger stage asserted;
   * OD-3 is still required: FE-1 adds tests (`assurance_suites`, `tests/**`) and edits the V1 reference
     `tests/test_core_api_layering.py`. FE-1 changes no frozen symbol and no certified source file.

**Next packages in order:** FE-2 = Wave C (reliability core, MC only; needs OD-REL-1). FE-3 = Wave E (inverse core;
needs OD-INV-1 + OD-3). FE-4 = Wave B + Wave D. FE-5 = Wave F.

---

**TOTAL proposed substantive additions:** 34 (P0 17, P1 11, P2 6). CAP-01 11, CAP-02 12, CAP-03 11.

**TOTAL reused FORGE components:** 31. The two claims-layer records (`Preregistration`, `MeasurementDatasetManifest`)
are referenced by digest only and are not counted.

1. `Quantity` + spread/affine helpers
2. `Uncertainty`/`UncertaintySource`
3. `ParameterIdentity`/`ParameterTransform`/`CalibrationParameterSet`
4. `GaussianObservation`/`ObservationSet`
5. `CalibrationSpec`/`calibrate`/`CalibrationResult`/`NoiseModel`
6. `assess_identifiability`/`IdentifiabilityReport`/`IdentifiabilityStatus`
7. `central_difference`/`LocalSensitivity`/supplied-J boundary
8. `local_gaussian_posterior`/`LocalGaussianPosterior`/`MultistartPolicy`/`RoutedIdentifiability`/`classify`
9. `route_uncertainty`/`HybridUQResult`/`RouteClaim`/`MODEL_DISCREPANCY_NOT_MODELLED`
10. `ObservationSplit`/`DataLeakageError`
11. `held_out_verdict`/`HeldOutValidation`/`HeldOutMetrics`
12. `HoldoutLedger`
13. `PriorSource`
14. `ValidityDomain.assess`/`ValidityAssessment`
15. `ConstraintDefinition`/`ConstraintOperator`
16. `ProviderExecutionIdentity`
17. `ProviderExecutionRecord`
18. `ProviderCapability` + probes/`distribution_digest`
19. `ComparisonDeclaration`/`shared_dependencies`
20. `CanonicalProblem`/`ProblemBinding`
21. `SymbolicSystem`
22. `SciPyLinearProvider`/`NumericalProvider`
23. `SystemExecutionPlan`/`PlanNode`
24. `PhysicsGraph` SCCs/`CouplingEdge`/`PortDefinition`
25. `require_positive_semidefinite_correlation`
26. `content_digest`
27. `run_bounded`/`run_provider` pattern
28. `thermal_resistance` closed form + partials
29. `ocv_forward_evaluator`
30. the electrothermal example + `element_hot_spot_utilization`
31. the PETSc and Dakota provider paths

**TOTAL external engines:** 5. SciPy and SymPy are existing BUYs. OpenTURNS is a new WRAP and the only new dependency.
PETSc (WRAP, P2) and Dakota (LEARN + optional WRAP, P2) are existing provider paths. SUNDIALS and OpenMDAO bring no
engine (DEFER and LEARN).

**TOTAL new canonical abstractions:** 14. `OutputRef`, `VariableRef`, `Standing`, `ProbabilisticInputModel`,
`DerivativeRecord`, `DerivativeVerification`, `TotalDerivativeAssembly`, `LimitState`, `ReliabilityStudy`,
`ReliabilityResult`, `InverseProblem`, `InverseTarget`, `ObservationBinding`, `InverseSolution`.

**TOTAL deferred ideas:** 18 (§9), plus 12 never-build algorithm families.
