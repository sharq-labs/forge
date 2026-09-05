# ELECTRO-THERMAL VERTICAL PROOF — Evidence

**Milestone:** `ET-VERTICAL`
**Decision status:** `PROPOSED`
**Evidence:** `L1 EXERCISED` for the executed loop; **per-claim levels in §14, several of which are `L0` or zero.**
**Falsifier verdict:** SURVIVES WITH REQUIRED CHANGES. No `BLOCKER`. **Three `BREAKING-RISK` findings, all closed before commit.**
**Date of this record:** 2026-09-02
**Branch:** `electrothermal-vertical-proof`

> **Temporal boundary.** `docs/electrothermal-vertical-prereg.md` is the
> preregistration: committed at `81d9b9b`, before any source file was added or
> edited on this branch, and immutable. **This** document was written after
> execution. Deviations, corrections, adversarial findings and the final
> classification live here and nowhere else.
>
> This is **not** a freeze document.

---

# 1. Result against the preregistered hypotheses

**H1 is supported in its strongest form, and the prediction that made it
strongest — zero new universal records — held. H0(A) loses. H0(B) is
*partially proven*, and that is the milestone's most important finding.**

Prereg §2 permitted at most one new universal semantic record under
`src/engcore/scientific/` and predicted zero. **Zero were added. No file under
`src/engcore/scientific/` was created or edited.** The only pre-existing file
touched anywhere in the repository is
`src/engcore/systems/electrothermal/__init__.py`: **48 lines added, 0 removed,
exports only.**

The loop closes. Iteration *n ≥ 2* solves the electrical problem at a resistance
the previous thermal solve produced, asserted against the electrical result's
own `provenance.inputs` rather than against a variable of the runner.

## 1.1 H0(B) — partially proven, and precisely where

> **H0(B)** — the loop closes only because the executing code secretly knows it
> is electro-thermal.

The **lexical and branch-level** form of the attack fails outright:

* `run_fixed_point` contains no domain word, no domain conditional and no
  reconstruction fallback, asserted over its AST with docstrings stripped. Its
  *signature* was domain-typed in a first draft and was refactored so that it is
  not: it takes problems, a plan, and a `Mapping[problem_id -> callable]`.
* Deleting one declared edge stops the loop dead (`test_h0b`). There is no rule
  that reconstructs a transport from a name.
* Changing **one enumerated `source_quantity`** moves the converged physics by
  **3.376418 K** with no code change (`test_a3`).
* A tribology cycle is built, ordered, planned and serialized with no
  electro-thermal import (`test_i4`).

The **structural** form succeeds, and the falsifier found it:

> `run_fixed_point` carried an unstated assumption — **at most one incoming edge
> per `(problem, quantity)`** — true of exactly the 1:1 topology built first.
> `inputs` was a dict keyed by `target_quantity`, so two edges into one endpoint
> resolved silently to whichever was declared last. The run still returned
> `CRITERION_MET`, on a different physical system, with nothing in the record
> saying an edge had been discarded.

It contains no domain word, so `test_i3`'s AST scan **structurally could not**
have caught it. This is `MIN-FOUNDATION-ET` finding C-2 reproduced one layer out,
and it is the strongest evidence for H0(B) in the milestone.

**Closed before commit** by refusal rather than by a combination rule: a plan
whose dependencies put two edges into one endpoint is now rejected, in the same
voice as the mixed-dimension refusal, because *no record states whether they sum,
override or split*. The fan-in gap stays measured and unfilled (`test_h4`); the
loop simply can no longer fill it by accident (`test_h4b`).

---

# 2. The gates, executed before any coupling record was written

`MODEL0-R` finding D4 recorded a preregistered gate that was *analysed* rather
than *executed*. Both gates below were built and run first, and both results are
counts.

## 2.1 G0 — is the declared dependency set executable as declared?

**Predicted 0 / 3 / 0. Measured 0 / 3 / 0.**

| Measurement | Predicted | Observed |
|---|---|---|
| Admissible topological orders over the three problems | 0 | **0** |
| Admissible single-edge tears | 3 | **3** |
| Records supplying a seed for each candidate tear (conditions) | 0 | **0** |

The graph is one cycle of length 3:

```text
electrical_dc:… ──▶ thermal-lumped-R1 ──▶ resistance-tcr-R1 ──▶ electrical_dc:…
```

**Why no record supplies a seed, measured rather than argued.**
`build_resistance_problem` declares `temperature` as `role=STATE` with **no
initial condition** and no boundary condition. The thermal problem's initial
condition is on `temperature` (t₀) — a **deliberately different endpoint** from
`final_temperature`, severed by `MIN-FOUNDATION-ET` falsifier finding D-1 so that
one name cannot denote two time levels.

**One apparent seed, and why it is not one.** Counting quantity-valued
`ScientificParameter`s as well as conditions, exactly **one** of the three tears
has a candidate: `R:R1`, the target of the resistance edge. Its value is
whatever the caller passed to `coupled_problems` to build the electrical problem
— an arbitrary placeholder, not a physical initial state. A rule of the form
*"tear the edge whose target already carries a value"* would uniquely select
that edge, keying on the DC domain modelling a computed quantity as configuration
— which `unresolved_inputs`' own docstring records as an **undeclared**
modelling accident. Promoting an accident to an execution law is exactly the
C-2 leak class. **No such rule was written** (prereg required change 4).

## 2.2 G1 — does anything need a universal reader?

**Predicted 0. Measured 0.**

`src/engcore/scientific/**` yields **19 occurrences across 18 lines** of
planner / scheduler / orchestration / coupling / relaxation vocabulary, and **0
executable identifiers** once docstrings and comments are stripped from the AST.
Every one of the eighteen is prose declaring the reader's absence:

```text
experiments/experiment.py:3    Deliberately not a scheduler. No threads, no processes, no distribution
realizations/registry.py:14    selection belongs to a planner that does not exist
composition/__init__.py:26     Nothing here executes, schedules, transfers, interpolates, relaxes or converges
composition/dependency.py:47   no schedule and no execution order. Every one of those belongs to a
composition/dependency.py:49   would have decided the shape of a coupling engine on the evidence of one
```

Two of the eighteen are not about coupling at all — `ir/constraints.py` uses
*"relaxes"* of a numerical bound — which is itself worth recording: a lexical
gate over prose is a weak instrument, and this one is reported with its
denominator rather than as a bare pass.

**This is the measurement that decided option A.** `MIN-FOUNDATION-ET` added its
one universal record because a count showed no reader could recover the fact it
carried. There is no analogous count here, and *"a second coupled pair could
reuse this"* is an argument at `L0`, which is the level under which that
milestone honestly refused to promote ten of its eleven deferrals.

---

# 3. Reviewer verdict, and where it was wrong

`architecture-decision-reviewer`, on *"What is the minimum execution concept
required to close this specific electro-thermal loop?"*, comparing six options
(A, B1, B2, C, D0 and a `ValidationReport` placement). Verdict: **ACCEPT WITH
CHANGES, selecting A** — domain-level orchestration, zero new universal records.

All eleven required changes were carried into the preregistration and honoured.
Two of its findings were **verified against running code before implementation
began**, and one of those verifications later turned out to be an over-claim:

* **Verified and true:** `Quantity(0.001,"kelvin").magnitude_in("degC")` is
  `-273.149`, and `dimensionality("degC") == dimensionality("kelvin")`.
* **Verified and true:** `tests/test_min_foundation_electrothermal.py::test_f2`
  pins `engcore.scientific.composition.__all__` to four names, so a universal
  record placed there would have broken a pre-existing test. Recorded as a
  **constraint discovered**, explicitly not as the reason A was selected.
* **Over-claimed — see §12, deviation D2.** The reviewer's stated failure mode
  for the offset hazard is unreachable in the shipped code, and the guard
  protects something different and narrower than the argument for it said.

The reviewer's own weakest assumption — *"whether the Picard loop converges at
this operating point without relaxation… only execution resolves"* — was settled
by execution and by a closed form: see §6.

---

# 4. The system executed

## 4.1 Equations

```text
property    R(T)   = R_ref · (1 + α · (T − T_ref))                      [ohm]
electrical  I      = V / ΣR                       (series, ideal source)
            P_i    = I² R_i                                             [watt]
thermal     C dT/dt = P − hA · (T − T_amb)
            T_ss    = T_amb + P / (hA)                                  [kelvin]
            τ       = C / (hA)                                          [second]
            T_end   = T_ss + (T₀ − T_ss) · exp(−t_dur / τ)              [kelvin]
```

Electrical: the **existing, unmodified** `engcore.domains.electrical.dc` MNA
path. Property and thermal: the **existing, unmodified** `MIN-FOUNDATION-ET`
modules. No physics was written for this milestone.

## 4.2 The loop

```text
        seed T⁽⁰⁾
            ↓
    ┌── T⁽ⁿ⁾ ──▶ R(T⁽ⁿ⁾) ──▶ electrical solve ──▶ P⁽ⁿ⁾ ──▶ thermal solve ──┐
    │                                                                       │
    └──────────────────── T⁽ⁿ⁺¹⁾  ◀── iterate change |T⁽ⁿ⁺¹⁾ − T⁽ⁿ⁾| ◀──────┘
```

Gauss–Seidel over the torn cycle. The execution order is **computed, not
written**: cut the torn edges, topologically sort the remainder. For the
two-stage system that yields

```text
resistance-tcr-R1 · resistance-tcr-R2 · electrical_dc:… · thermal-lumped-R1 · thermal-lumped-R2
```

and the loop never states it.

## 4.3 Convergence policy

| Item | Decision |
|---|---|
| Quantity compared | the quantity transported by the **torn** edge — temperature |
| Unit | `kelvin`; both sides converted by `magnitude_in` before subtraction |
| Criterion | **absolute only**, `max over torn edges of |x⁽ⁿ⁾ − x⁽ⁿ⁻¹⁾| ≤ tol` |
| Tolerance | `1e-6 kelvin` |
| Budget | 50 (nominal) |
| Non-convergence | returns a record with `ITERATION_LIMIT_REACHED` and the full trace; does **not** raise |
| Sub-solve failure | **not caught**, not reported as non-convergence |
| Declaration error | refused before the first iteration, by raising |

No relative criterion: a relative tolerance divides by a value and is meaningless
wherever the zero of the scale is conventional, and **no Crafty record states
whether a quantity's zero is physical**. Recorded as a deferral with its reason.

---

# 5. Executed cases — every preregistered number reproduced

All values below are from the **final tree**, after every falsifier correction.
The predictions were computed analytically before implementation, in a script
importing nothing from `engcore`. **No prediction was falsified and none was
adjusted.**

| Case | Predicted | Observed | Match |
|---|---|---|---|
| **A** nominal | `CRITERION_MET`, 10 iterations, `T* = 338.577018 K` | `criterion_met`, 10, **338.577017565 K** | ✓ |
| **A2** steady endpoint | `CRITERION_MET`, 11, `T* = 341.953436 K` | `criterion_met`, 11, **341.953435805 K** | ✓ |
| **A vs A2** | 3.376418 K apart | **3.376418240 K** | ✓ |
| **B1** seed 250 K | `CRITERION_MET`, 11, same `T*` | `criterion_met`, 11, **338.577017638 K** | ✓ |
| **B2** seed 440 K | `CRITERION_MET`, 10, same `T*` | `criterion_met`, 10, **338.577017716 K** | ✓ |
| **C1** budget 2 | `ITERATION_LIMIT_REACHED`, change `6.414 K` | `iteration_limit_reached`, 2, **6.414244 K** | ✓ |
| **C2** marginal, α<0 | `ITERATION_LIMIT_REACHED`, 50, change `4.902e-2 K` | `iteration_limit_reached`, 50, **4.901961e-02 K** | ✓ |
| **D** four malformations | refused before iteration 1 | all four refused | ✓ |
| **E** two stages in series | `CRITERION_MET`, 8, `T1* = 328.898146`, `T2* = 355.089513` | `criterion_met`, 8, **328.898146247 / 355.089513105 K** | ✓ |
| **F** converged & invalid | `CRITERION_MET`, 25, `T* = 498.994793 K`, outside validity | `criterion_met`, 25, **498.994793108 K**, `outside_validated_domain` | ✓ |

## 5.1 CASE A — the iteration trace

| n | T⁽ⁿ⁾ in [K] | R(T⁽ⁿ⁾) [Ω] | P [W] | T_end out [K] | \|ΔT\| [K] |
|---|---|---|---|---|---|
| 1 | 300.000000000 | 10.269205000 | 2.434463038 | 344.272270673 | 4.427227e+01 |
| 2 | 344.272270673 | 12.009105237 | 2.081753761 | 337.858026420 | 6.414244e+00 |
| 3 | 337.858026420 | 11.757025438 | 2.126388186 | 338.669732046 | 8.117056e-01 |
| 4 | 338.669732046 | 11.788925469 | 2.120634325 | 338.565094379 | 1.046377e-01 |
| 5 | 338.565094379 | 11.784813209 | 2.121374311 | 338.578551504 | 1.345713e-02 |
| 6 | 338.578551504 | 11.785342074 | 2.121279115 | 338.576820299 | 1.731205e-03 |
| 7 | 338.576820299 | 11.785274038 | 2.121291361 | 338.577043003 | 2.227039e-04 |
| 8 | 338.577043003 | 11.785282790 | 2.121289785 | 338.577014354 | 2.864899e-05 |
| 9 | 338.577014354 | 11.785281664 | 2.121289988 | 338.577018039 | 3.685450e-06 |
| 10 | 338.577018039 | 11.785281809 | 2.121289962 | 338.577017565 | **4.741020e-07** |

**Iteration 1 reproduces `MIN-FOUNDATION-ET`'s open-loop pass to `rel=1e-12`**
(`R = 10.269205`, `P = 2.434463`, `T₁ = 344.272271`), and **iteration 2 is the
second electrical solve that milestone explicitly refused to perform**, consuming
`R(T₁) = 12.009105 Ω` — the exact value it computed and threw away. Asserted in
`test_a2`.

**The circuit changed every iteration.** Ten distinct circuit fingerprints across
ten iterations, under one stable `problem_id`. The endpoint survives iteration;
the problem *record* does not.

## 5.2 The sharpest single measurement

The thermal problem publishes three kelvin-valued quantities that no dimension
check can separate:

```text
temperature               problem variable, role=STATE     t₀
final_temperature         result metric                    t = duration
steady_state_temperature  result metric                    t → ∞
```

Selecting the second gives `T* = 338.577018 K`. Selecting the third gives
`T* = 341.953436 K`. **One field of one record, no code change, 3.376418 K of
different physics**, and both dependencies `check_against` clean.

That is the executed consequence of `MIN-FOUNDATION-ET` finding D-1, which
separated `temperature` from `final_temperature` before commit. Had the names
still collided, the loop would have transported a different time level with
nothing — not a dimension check, not a binding check — able to notice.

## 5.3 CASE C2 — non-convergence on legitimate physics

A negative-TCR conductor at its **double root**, where the fixed-point map is
exactly non-contracting:

```text
α = −0.004 K⁻¹, T_ref = T_amb = 300 K, R_ref = 10 Ω, hA = 0.04 W/K, V = 5 V
double root at Δ* = 1/(2|α|) = 125 K  →  T* = 425 K, R* = 5 Ω, |g'(T*)| = 1.0 exactly
```

* 50 iterations, final iterate change **4.901961e-02 K**, five orders above
  tolerance.
* Measured convergence ratio at n = 50: **0.9608**, approaching 1 as `O(1/n)`.
* Every iterate in `[300 K, 422.55 K]` — **inside** the property model's declared
  validity domain — and every resistance in `[5.10 Ω, 10.00 Ω]`, strictly
  positive.
* **Every sub-solve reported success in all fifty iterations**:
  `{converged, not_applicable}`.

Nothing is capped artificially. Coupling convergence is `False` while numerical
convergence is `True` fifty times over.

## 5.4 CASE F — three verdicts, one run

`T* = 498.994793 K`, converged in 25 iterations. Simultaneously:

| Verdict | Value |
|---|---|
| coupling outcome | `CRITERION_MET` |
| every sub-solve's `ConvergenceState` | `CONVERGED` / `NOT_APPLICABLE` |
| every sub-solve's `ValidationReport.status` | not `FAIL` |
| `assess_resistance_validity(T*)` | **`OUTSIDE_VALIDATED_DOMAIN`**, violating `temperature` |
| `ValidationLevel`s attained | unchanged; nothing upgraded |

`LINEAR_TCR_MODEL` declares validity over 200–450 K. The coupled system converges
to 499 K. **Coupled convergence does not imply the model is valid**, and the
record says all three things separately.

---

# 6. Prediction P-C — the contraction result

Prereg §4.6 predicted, from a closed form:

> For a linear-TCR conductor with `α > 0`, the coupled fixed-point map is a
> contraction at its fixed point **exactly when** the resistance is positive at
> ambient. No relaxation can be forced by this system for `α > 0`.

Both halves reduce to `α(T_ref − T_amb) < 1`, which is also the condition
`R(T_amb) > 0`. Every configuration violating it is already refused by the domain
for having a non-positive resistance.

**Measured.**

| Configuration | Predicted ratio | Measured ratio |
|---|---|---|
| A, `final_temperature` | 0.128642 | **0.1286415** |
| A2, `steady_state_temperature` | 0.138343 | **0.1383431** |
| C2, α < 0 at the double root | 1.0 | **0.9608** at n=50, → 1 |

**No relaxation was required, and none was written.** Prereg §15's separate
mini-decision was not triggered. `test_l3` asserts over the module's AST that the
identifiers `omega`, `relax`, `damp`, `aitken`, `anderson`, `rollback` and
`checkpoint` appear nowhere.

---

# 7. What was built, and what it cost

Everything is in **one new module of a system pack**. Nothing under
`src/engcore/scientific/` was added or edited.

| Item | Location |
|---|---|
| the loop and its records | `src/engcore/systems/electrothermal/coupled.py` (new, 1 598 lines) |
| tests | `tests/test_electrothermal_vertical.py` (new, 62 tests) |
| exports | `src/engcore/systems/electrothermal/__init__.py` (+48, −0) |

`resistor_body.py` is **byte-unchanged**; its AST guard — no `While` node, exactly
one `solve_circuit` call, no `iterate`/`residual`/`relax` identifier — still
passes, re-asserted here as `test_k`.

## 7.1 The pack-local records

| Record | Schema | What it carries |
|---|---|---|
| `CouplingOutcome` | enum, 2 members | `CRITERION_MET`, `ITERATION_LIMIT_REACHED` |
| `TornEndpoint` | `electrothermal_torn_endpoint/1` | one cut edge **paired structurally** with its seed |
| `FixedPointCouplingPlan` | `electrothermal_fixed_point_plan/1` | dependencies, torn edges, `Quantity` tolerance, budget |
| `CoupledIteration` | `electrothermal_coupled_iteration/1` | index, results, `largest_iterate_change` |
| `CoupledRun` | `electrothermal_coupled_run/1` | plan, outcome, trace, final values, provenance |

Domain packs already mint schema strings (`electrical_dc_circuit/1`), so a typed,
serialized, round-tripping, inspectable record does **not** have to live in core.
That removes the usual argument for promoting it.

**No existing schema version moved.** `quantity_dependency/1`,
`provenance_record/2`, `execution_binding/1`, `scientific_result/2` and
`raw_solver_output/2` are pinned unchanged by `test_o3`.

## 7.2 Abstractions designed and dropped

Three **before writing**, recorded in the preregistration so they could not be
presented afterwards as discoveries:

* **`CouplingTransfer(dependency, value)`** — the value that crossed each edge is
  `iteration.result_for(dep.source_problem_id).values[dep.source_quantity]`.
  Derivable; became an accessor.
* **`IterateChange(endpoint, previous, current)`** — the previous value is
  iteration *n−1*'s transported value on the same edge, and the seed for *n = 1*.
  Derivable.
* **`CouplingResidual` as a name** — it is an *iterate change*, not the residual
  of any equation. Nothing here computes a residual, so nothing here may be named
  for one.

One **during the adversarial pass**:

* **`_electrical_result` returning `(result, circuit)`** — the circuit had no
  caller. Deleted.

## 7.3 Reduction attacks (prereg §9), all executed

| # | Attack | Result |
|---|---|---|
| R1 | kwargs instead of `FixedPointCouplingPlan` | **Fails.** Three properties lost, each asserted: pre-execution checkability, serializability, and the ability to refuse a tolerance that does not fit the edge |
| R2 | `converged: bool` instead of `CouplingOutcome` | **SUCCEEDS.** See §7.4 |
| R3 | two parallel tuples instead of `TornEndpoint` | **Fails.** Reversing `dependencies` leaves the answer identical only because the pairing is structural; on a fan-in graph a positional form would flip |
| R4 | `float` tolerance instead of `Quantity` | **Fails, and both failures shown.** A bare `1e-6` is compatible with a watt-valued edge, an affine scale and a mixed-dimension plan; the typed tolerance refuses all three |
| R5 | fields on `QuantityDependency` | **Fails.** Byte-identical dependency records drive two runs with different tolerances, budgets and *outcomes*. The policy is a property of the study, not of the declaration — and it would bump `quantity_dependency/1` against an exact-match reader |
| R6 | `metadata` / `diagnostics` for the trace | **Fails.** Banned channel; `test_b2` asserts the verdict appears exactly once, at the run's top level |
| R7 | `ProvenanceRecord` as the plan | **Fails, decisively.** Provenance requires a `run_id`; the plan is fully checkable with nothing executed |
| R8 | derive `largest_iterate_change` rather than store it | **Succeeds on information, kept as measurement.** `test_r8` re-derives it from the trace and the seed and asserts they agree to `rel=1e-15`. Retained as the record of what the loop actually compared |

**Prereg §9's bar — "at least one type must be deleted or demonstrably survive a
serious attempt" — was met by the three pre-writing reductions and by R2.**

## 7.4 R2 in full: the enum survives a reduction it lost

`test_r2` executes the reduction and reports the honest result: **at two members
the enum carries no fact a boolean does not.** Both reachable runs are
distinguishable by one bit, and nothing in this milestone reads the outcome for
anything else. A sub-solve failure produces *no record at all*, so there is no
third state to name.

**It is kept anyway**, on a naming argument recorded at `L0 REASONED`: a field
named `converged` on a coupling record, in a codebase where `convergence` already
names a solver's own termination and where the same word is a preregistered fail
condition (§12.4), is the collapse the milestone exists to prevent. The falsifier
independently reached the same conclusion and classified deletion as unnecessary.

**This is the weakest new type in the milestone and the first candidate for
deletion if a third member is never earned.** Recorded as such rather than
defended.

---

# 8. QuantityDependency — stressed, and the verdict

Prereg §7 required attacking it, not reusing it successfully and declaring
victory.

| Stress | Result |
|---|---|
| **Feedback cycle** | Executed. Both directions present; the cycle closes by traversal with no name parsing (`test_f`). The graph reader returns **zero** admissible orders |
| **Deterministic source/target identification** | Held. Every transported value is looked up as `result_of(source_problem_id).values[source_quantity]`. **No metric name is constructed, parsed or inferred inside the iteration** |
| **Ordering independence** | Held, and it is stronger than it looks. `current` is updated only after a complete sweep, so every torn edge uses the previous iterate for the whole sweep. The iterate sequence is **identical for every admissible topological order**; the sorted tie-break is a determinism device, not a semantic choice. CASE E has four admissible orders and all four give the same numbers |
| **Dimensional incompatibility** | Refused before execution (`test_g`), by dimension and never by unit string |
| **More than one dependency into one target** | **Refused.** See §1.1 — this was where the loop broke, and the refusal is the correction |
| **Two configurations differing only in `source_quantity`** | Executed: 3.376418 K apart |
| **Arity 2** | Executed: six edges, six distinct source endpoints, six distinct target endpoints, no aliasing |

**Is `problem_id + quantity name + unit` still sufficient?**

**Yes, at every case executed here — and the reason is inherited rather than
supplied.** `(problem_id, quantity)` disambiguates at arity 2 because the
*electrical domain* embeds the component id in the quantity name (`R:R1` vs
`R:R2`, `resistor_power:R1` vs `resistor_power:R2`) while the record never parses
it. Where a domain packs many instances into one problem *without* per-instance
naming, the deferred component-instance concept returns immediately. That
condition is unchanged from `MIN-FOUNDATION-ET` known unknown 2, and the DC
domain is still the domain that would trigger it.

**No typed `QuantityIdentity` or `Endpoint` was created.** Nothing forced one.

**Evidence movement:** `QuantityDependency` is now **executed** rather than
declared, at arity 2, transporting two different metrics of one problem. That is
a real strengthening *within* `L1`. It is **not** differentiation: there is one
runner, and prereg §14's own bar — *"being executed by one runner is not
differentiation"* — is not met. It stays `L1`.

## 8.1 One near-duplicate hazard, met for the first time

`MIN-FOUNDATION-ET` known unknown 6 predicted that no collection type owns
dependency-set invariants and that *"two near-duplicate records are both valid and
undetected"*. The first executed instance appeared here: the plan tested torn-edge
membership by **whole-record equality** and computed the uncut set by a
**four-field quad**, so two records differing only in `unit_exemplar` were
distinct for one purpose and identical for the other — tearing one would have
dropped both from the sweep.

Closed by one notion of edge identity used everywhere (`edge_key`), plus the
duplicate-endpoint refusal, which now catches the near-duplicate as a second edge
into one endpoint (`test_x2`).

---

# 9. Multiplicity and identity — the verdict

**CASE E: two conductors in series, two thermal bodies, one circuit, one source.**
Series deliberately: across an ideal source, parallel elements do not interact and
a multiplicity case in which the instances cannot influence each other exercises
nothing. In series, heating `R1` changes `I`, which changes `P2`, which changes
`T2`.

Converged in 8 iterations:

```text
T1* = 328.898146 K   R1* = 11.404902 Ω   P1* = 1.589064 W
T2* = 355.089513 K   R2* = 20.743274 Ω   P2* = 2.890195 W
I*  = 0.373271562 A
```

**Verdict: no `ComponentInstance` is forced. Nothing aliased.**

* One electrical problem enumerates **both** `R:R1` and `R:R2`.
* One electrical result publishes **both** `resistor_power:R1` and
  `resistor_power:R2`.
* Six dependencies, six distinct source endpoints, six distinct target endpoints.
* A system declaring two stages under one `component_id` is **refused at
  construction**, not discovered in the numbers.
* Two torn edges of the **same dimension** are served by one scalar tolerance
  under a max-norm. Two torn edges of **different** dimensions are **refused**,
  because no record states a normalization between them. That refusal is the
  measured boundary of the single-scalar criterion (`test_g4`).

**Fan-in (2:1) remains unrepresented, and is now refused rather than silently
resolved.** Two sources on one target still check clean as *records*
(`test_h4`) — that gap is `MIN-FOUNDATION-ET`'s and is deliberately unfilled —
but a *plan* containing them is rejected (`test_h4b`). Nothing was invented to
combine them.

---

# 10. ScientificTwin — the verdict, and it is uncomfortable

Prereg §11 TEST N asked whether the twin is the scientific instance description,
mutable runtime state, execution history, or provenance/configuration.

**Answer: it is the scientific instance description, and this milestone provides
essentially no evidence for that, because the twin is read by nothing.**

What is true and asserted: `build_coupled_twin` is deterministic; it is **not** a
parameter of `run_fixed_point_coupling`; the string `twin` does not appear
anywhere in the serialized run; the twin declares the instance's t₀ state once and
is never re-versioned. Carrying the iterate would have required **11 twin versions
for one 120-second interval** in CASE A alone.

**What that is worth as evidence: almost nothing, and the falsifier said so.**
`build_coupled_twin` has exactly one caller — the test that asserts it is not
used. **Nothing could have made TEST N fail.** "The twin is not the runtime state"
is not a falsifiable invariant as tested; it is a statement that an object no code
reads is not read.

This is `MIN-FOUNDATION-ET` finding C-6 repeated at greater length.
**`ScientificTwin` as instance authority gains zero evidence for the second
consecutive milestone**, and the correct reading is that a separate ephemeral
runtime-state object was **not needed** — the iterate is one `Quantity` per torn
endpoint plus a counter, and the trace record is the history — rather than that
the twin was tested and held.

---

# 11. Provenance, model / realization / solver

**Preserved, at arity > 1, across three solvers.**

CASE A's run-level `ProvenanceRecord`: **5 `ExecutionBinding`s, 5 models, 3
solvers, 2 realizations**. CASE E: 5 bindings, 3 solvers over 5 problems.

| Model | Realization | Solver |
|---|---|---|
| `electrical.material.linear_tcr_resistance` | `…linear_tcr_resistance.closed_form` | `engcore.electrical.linear_tcr_evaluator` |
| `thermal.lumped.first_order_capacity` | `…first_order_capacity.closed_form` | `engcore.thermal.lumped_closed_form` |
| `electrical.dc.kcl` | *(none — honest)* | `engcore.electrical.dc.mna` |
| `electrical.dc.resistor_ohm` | *(none)* | `engcore.electrical.dc.mna` |
| `electrical.dc.ideal_voltage_source` | *(none)* | `engcore.electrical.dc.mna` |

`realization=None` is a **real answer**, not a gap: the DC solver predates
`MODEL0-R` and declared no realization, and manufacturing one would put a claim
into the record its author never made. At 5 models and 3 solvers no positional
zip of participant sets is possible, so the association is structural or it does
not exist.

**Bindings are unioned across every iteration, not taken from the last.** For this
consumer both give the same five, because every sweep binds the same
participants — but `run_fixed_point` is generic, and an executor that changed
realization mid-run would otherwise be omitted from the run-level record.
Corrected on the falsifier's F-7.

Every one of the 30 per-iteration results in CASE A carries its own
`ProvenanceRecord` with a unique `run_id` and its own solver identity.

---

# 12. Deviations from the preregistration

Recorded here because a preregistration whose every clause survives contact with
execution was probably not specific enough.

## D1 — TEST L's closed form was imprecise for configuration (i)

Prereg §4.6 derives `|g'| = α(T*−T_amb)/(1 + α(T*−T_ref))` by eliminating `V²` at
the **steady-state** fixed point. TEST L's parenthetical then proposed reusing it
for configuration (i) "times `1−e^{−t/τ}`". That is wrong by ~10 %: configuration
(i) converges to a different `T*` (338.577 K, not 341.953 K), so the elimination
step does not apply there.

**The underlying prediction is unaffected** and is asserted directly:
`|g'| = (1−e^{−t/τ}) · V²αR_ref/(hA R(T*)²)` — measured `0.1286415` against
predicted `0.128642`. The identity form is checked in configuration (ii), where
it was derived: measured `0.1383431` against `0.138343`. **P-C holds; its stated
form was over-general.**

## D2 — prereg §3.2(a) over-states what the offset guard prevents

§3.2(a) justifies the ratio-scale refusal with: *"A tolerance declared in kelvin,
compared against a change carried in `degC`, converts to −273.149 and every
iteration converges immediately."*

**That path is unreachable in the shipped code.** The comparison unit *is* the
tolerance's unit, so `plan.absolute_tolerance.magnitude_in(unit)` is an identity
conversion, and both sides of the difference are converted into the same unit
before subtraction — where an affine offset cancels algebraically. Required
change 1's *first* half ("compare in one unit fixed for the run") closes the
arithmetic hazard by itself.

**The guard still earns its place, for a different and narrower reason.**
`largest_iterate_change` is a **difference** stored in a type that means an
absolute value; `Quantity` draws no interval/ratio distinction. A consumer holding
a `4.7e-7 degC` delta and calling `.to("kelvin")` gets `273.15`. The refusal is
what keeps the *stored record* convertible. Module docstrings and the
`CoupledIteration` docstring now say exactly this instead of what §3.2(a) said.

## D3 — prereg §5's "refused before the first iteration" does not cover an *under-declared* composition

§5 promises that a dependency that cannot be bound is refused before iteration 1.
An **omitted** edge is a different case and is **not records-refusable**: core's
own `externally_imposed` cannot distinguish an ambient legitimately imposed by
the environment from a heat source someone forgot. Both read identically, and
`unresolved_inputs`' docstring says so.

**Measured rather than papered over.** `FixedPointCouplingPlan.unsupplied()`
reports `{ambient_temperature}` for the correct composition and
`{ambient_temperature, heat_input}` for one missing the heat edge — so the
information *is* available before execution — but nothing can decide on it, and
the failure therefore surfaces from the executor (`test_x6`, `test_h0b`).

## D4 — prereg §9 lists eight reduction attacks; R6 has no dedicated test

R6 (`metadata`/`diagnostics` as the trace channel) is covered by `test_b2` and
`test_j` rather than by a test named for it. Recorded rather than back-filled.

---

# 13. Falsifier findings and resolutions

`architecture-falsifier`, primary attack *"prove that this electro-thermal
vertical only works because the coupling code secretly knows it is
electro-thermal."* Verdict: **SURVIVES WITH REQUIRED CHANGES**. No `BLOCKER`.

| # | Finding | Class | Resolution |
|---|---|---|---|
| **F-1** | `inputs` keyed by `target_quantity` in a dict: two edges into one endpoint resolve silently to the last declared, and a torn seed applied after the incoming loop **overwrites** a transported value. Contains no domain word, so the AST scan structurally could not see it | **BREAKING-RISK** | **Fixed before commit.** The plan refuses duplicate target endpoints among its dependencies and among its torn edges, in the same voice as the mixed-dimension refusal (`test_h4b`). The gap stays measured (`test_h4`), unfilled |
| **F-2** | `converged_values` was populated identically on both exit paths, so an `ITERATION_LIMIT_REACHED` run carried an unconverged iterate under a field named *converged* — one name meaning two things, `MIN-FOUNDATION-ET` D-1's exact economics | **BREAKING-RISK** | **Fixed.** Renamed `final_values`, matching the existing `final` / `final_iterate_change` accessors (`test_x8`) |
| **F-3** | The same field was keyed by `f"{problem_id}::{quantity}"`, and **both components already contain colons** — a key that must be parsed to be read, which is the string convention `dependency.py` refuses | **BREAKING-RISK** | **Fixed.** `final_values` is keyed by the `(problem_id, quantity)` pair and serialized as records, never joined. `ProvenanceRecord.inputs` is `Mapping[str, Quantity]` in frozen core, so its composite key remains and is now **documented in the module** rather than silent |
| **F-16** | `cycle_edges` asked `execution_order` for its settled set — which that function discards whenever no order exists — so on any cyclic graph it reported **every** edge as cyclic. Right on a pure 3-cycle, wrong for `A→B, B→C, C→B` | IMPLEMENTATION-CONCERN (outright defect) | **Fixed.** Computed by peeling in-degree-0 and out-degree-0 nodes (`test_x1`, four graphs) |
| **F-9** | Two different edge-identity notions in one record (§8.1) | IMPLEMENTATION-CONCERN | **Fixed.** One `edge_key` everywhere (`test_x2`) |
| **F-4** | The one place that *composes* results had none of the pairing guards every domain has: no executor-coverage check, no duplicate-`problem_id` guard, no check that a returned result's `problem_id` matches the problem asked for. The next milestone is an external provider | IMPLEMENTATION-CONCERN | **Fixed.** All three guards added (`test_x3`) |
| **F-17** | `nominal_plan` selects the tear by `target_quantity == mat.TEMPERATURE` under a docstring saying *"stated, never inferred"* — and `mat.TEMPERATURE` and `lump.TEMPERATURE` are **both** `"temperature"`, so the filter would also cut an edge onto the thermal t₀ state: time marching wearing the name of coupling | IMPLEMENTATION-CONCERN | **Fixed two ways.** The docstring now says what the function does; and `check_against` refuses to seed an endpoint a declared initial or boundary condition already determines (`test_x4`) |
| **F-7** | Run provenance took bindings from the last iteration only | IMPLEMENTATION-CONCERN | **Fixed.** Unioned across all iterations (`test_x5`) |
| **F-15** | `CoupledRun` type-checked nothing; `from_dict` with empty `iterations` constructed fine and then `final` raised `IndexError` | IMPLEMENTATION-CONCERN | **Fixed.** Four refusals, matching its siblings (`test_x7`) |
| **F-6** | Stage↔problem association was **positional** across three functions (`problems[1:1+n]`, `problems[1+n:1+2n]`) — the D2 defect committed inside the module that argues against it, and `coupled_dependencies` is exported | IMPLEMENTATION-CONCERN | **Fixed.** One `stage_problems()` states the correspondence; the other functions look up by id and refuse a problem set that does not contain a stage's problems |
| **F-8** | `test_j` asserted "nothing bulk is inlined" while iterating `result.metadata` — not `result.provenance.metadata`, where `solve_circuit` parks the full canonical circuit on **every** solve | IMPLEMENTATION-CONCERN | **Measured, not fixed.** See §15.3. `test_j2` now measures the growth: **~16 kB per iteration**, 162 kB for CASE A (10 iterations), **790 kB for CASE C2 (50)**. Not a DATA-BOUNDARY0 violation — `data_references` and `artifacts` are empty throughout — but the same growth pattern one level up. The DC domain is not editable under this milestone's change policy |
| **F-11** | `is_ratio_scale` calls pint's `get_base_units`, reaching past the `Quantity` contract | IMPLEMENTATION-CONCERN | **Recorded and mitigated, not removed.** The contract publishes no way to name a dimension's base unit. A published-contract pairwise check (`shares_origin`) was added as an additional plan invariant; the backend call remains, is the module's only one, is in a system pack, and is documented in the function |
| **F-14** | A difference stored in a type that means an absolute value | IMPLEMENTATION-CONCERN | **Documented.** See §12 D2 |
| **F-12** | TEST N cannot fail (§10) | IMPLEMENTATION-CONCERN (evidence calibration) | **Restated, not dressed up.** §10 and §14 record zero evidence for the twin |
| **F-5** | An under-declared composition reaches iteration 1 as a bare `KeyError` | IMPLEMENTATION-CONCERN | **Measured.** §12 D3; `unsupplied()` added as a reporter (`test_x6`) |
| **F-10** | The iteration scheme is recorded only as prose in `provenance.assumptions` | ADDITIVE-FUTURE-EXTENSION | **Deliberately not taken.** A second scheme would force it; none exists. Recorded in §15 |
| **F-13** | The scalar assumption is now hardened into an executed signature | ADDITIVE-FUTURE-EXTENSION | Inherited and declared; §15 |
| **F-18** | A shipped docstring and the immutable preregistration cite an OpenMDAO claim not present in this repository's own study documents | IMPLEMENTATION-CONCERN (evidence hygiene) | **Fixed in the code.** The docstring now argues from the definitions themselves and cites nothing external. The preregistration is immutable and still carries it; recorded here |

## 13.1 Attacks that were run and did not land

Recorded because a falsifier that finds only hits is not being read carefully.

* **Ordering ambiguity changing the answer.** It cannot: `current` updates only
  after a complete sweep, so the iterate sequence is identical for every
  admissible topological order. CASE E has four; all four agree.
* **The comparison arithmetic being wrong on an affine scale.** It is not — the
  offset cancels. (This is what makes §12 D2 an over-claim rather than a defect.)
* **The max-norm being the wrong aggregation.** L∞ over same-dimension scalars is
  the strictest choice; mixed dimensions are refused rather than normalized.
* **Deleting `CouplingOutcome`.** §7.4.
* **Domain leakage into `engcore/scientific`.** The dependency-direction and
  vocabulary guards hold; `composition.__all__` is still four names; the pack
  imports only published contracts plus four utilities.
* **Registry / global-singleton trap.** Explicit typed dispatch table, fresh
  registries per call, solvers constructed per call, nothing registered globally.
* **Time marching under the name of coupling.** `test_p`: every iteration's
  thermal provenance records `T₀ = 300.0 K` and `duration = 120.0 s`.
* **The coupling verdict leaking into a validation or solver channel.**
  `run.provenance.tolerances == {}`, `metadata == {}`, the verdict string appears
  exactly once in the serialized run, and CASE F executes the three-verdict
  separation for real.
* **`PhysicsGraph ≠ ExecutionPlan`.** Held: `test_r5` drives two runs with
  different tolerances, budgets and outcomes from byte-identical dependency
  records.

---

# 14. Architecture fitness (master context §59)

| # | Question | Answer |
|---|---|---|
| 1 | Frozen core contract or schema changed? | **No.** `test_o3` pins five existing schema strings. Four new schemas are minted in the **pack** namespace |
| 2 | Serialized records required migration? | **No.** Nothing existing moved |
| 3 | Domain-specific branch added to universal core? | **No.** No file under `engcore/scientific` was added or edited at all |
| 4 | Provider identity leaked upward? | **One, recorded:** `is_ratio_scale` calls pint's `get_base_units` (F-11). In a system pack, not core |
| 5 | Untyped metadata used as an escape hatch? | **No.** The verdict appears once, at the run's top level |
| 6 | Existing abstraction duplicated? | **No, and three were reused:** `QuantityDependency`, `BindingIssue` via `check_against`, and `externally_imposed` |
| 7 | New semantic abstraction required? | **In universal core: none.** In the pack: five, of which one (`CouplingOutcome`) lost its reduction and is kept on a naming argument |
| 8 | Frozen invariant violated? | **No.** `domains/thermal/` and `domains/electrical/dc/` untouched; `resistor_body.py` byte-unchanged and its AST guard re-asserted |
| 9 | Implementable from the published contract alone? | **Almost.** The pack needed `resistance_name` from a non-exported DC submodule — inherited finding C-11, unchanged, and reduced by reusing the sibling's `RESISTOR_POWER_METRIC` rather than re-deriving it a third time |
| — | Could another domain pair use the shape without reading this code? | **Ordered and planned, not executed.** `test_i4` builds a tribology cycle importing nothing electro-thermal, and its plan orders and round-trips — but it is never run. One runner exists |

**Core Edit Ratio**, secondary diagnostic only: **48 added lines, 0 removed** in
one system-pack `__init__.py` — the sole edit to any pre-existing file — against
1 598 new pack lines and 1 958 test lines. Nothing above rests on it.

## 14.1 Evidence level, per claim

**Ceiling honoured: `PROPOSED` / at most `L1 EXERCISED`. `L2` is not claimed and
is excluded by the preregistration.**

| Claim | Level | Why |
|---|---|---|
| The closed loop executes and coupled convergence is reached and recorded | **`L1 EXERCISED`** | Ten cases, every preregistered number reproduced |
| Coupling convergence has a dedicated typed representation, not inferred from participants | **`L1 EXERCISED`** | CASE C1 and C2: every sub-solve succeeds in fifty iterations that did not converge |
| Numerical ≠ coupling ≠ scientific validity | **`L1 EXERCISED`** | CASE F: three independent verdicts, one run |
| Provenance preserves model → realization → solver at arity > 1 over 3 solvers | **`L1 EXERCISED`** | 5 bindings, 2 realizations, 3 solvers, unioned across iterations |
| The transported endpoint — not its dimension — carries the physics | **`L1 EXERCISED`** | 3.376418 K, one field |
| `QuantityDependency` executed rather than declared, at arity 2 | **`L1`, strengthened within the level** | One runner. Prereg §14's own bar for differentiation is not met |
| The loop contains no domain vocabulary or conditional | **`L1`, narrowly** | Tested over stripped ASTs. **F-1 proves a structural leak can contain no domain word**, so the honest claim is "no domain vocabulary or conditional leakage, tested lexically and structurally at the topologies executed" |
| Prediction P-C (contraction ⟺ R(T_amb) > 0 for α > 0) | **`L1 EXERCISED`** | Measured against the closed form in three configurations, to 1 % |
| Arity 2 does not force a component-instance concept | **`L1 EXERCISED`** | CASE E; and the reason it holds is inherited from the DC domain's per-instance naming, not supplied here |
| **`CouplingOutcome` as a type rather than a boolean** | **`L0 REASONED`** | The reduction succeeded; kept on a naming argument |
| **`ScientificTwin` as instance authority** | **`L0`, zero evidence — second consecutive milestone** | Read by nothing; TEST N could not fail (§10) |
| **The pack-local placement is correct** | **`L0 REASONED`** | It rests on G1's count of zero universal readers *today*. A planner arriving would overturn it |
| **These records would be reusable by a second coupled pair** | **`L0 REASONED`** | `test_i4` orders and serializes a tribology plan; it never executes one |
| Fan-in combination | **zero** | Refused, not solved |
| Mixed-dimension coupling norms | **zero** | Refused, not normalized |
| Field / tensor endpoints, bidirectional and acausal transport | **zero** | Not representable; correctly untouched |
| External providers, concurrency, restart from persisted state, > 2 domains | **zero** | Not exercised |

**What this milestone has is an executable proof, not an architectural proof.**
It shows the structure runs for cases differing in *parameter* (α sign, seed,
budget, duration, voltage), in *arity* (1 and 2 stages), and in *one enumerated
name*. Every case that differs in *kind* — fan-in, acausal, runtime-directed,
field-valued, asynchronous, external-session, distributed — bends or breaks, and
none was executed.

---

# 15. Known unknowns carried forward

1. **Fan-in has no combination rule, and is now refused rather than silently
   resolved.** Two edges into one endpoint are individually valid records; a plan
   containing them is rejected. Filling this is a combination rule, and inventing
   one from one consumer would be a coupling engine decided on no evidence.
2. **A mixed-dimension coupling criterion has no normalization.** One scalar
   tolerance serves two torn edges only because both transport kelvin. Refused
   otherwise.
3. **The serialized run grows ~16 kB per iteration.** `solve_circuit` writes the
   full `circuit.canonical_dict()` into `ProvenanceRecord.metadata` on every
   solve, and the trace retains every result: 162 kB for 10 iterations, **790 kB
   for 50**. Bounded by the budget, `O(iterations × topology)` in bytes. Not a
   DATA-BOUNDARY0 violation, and not fixable here — the DC domain is not editable
   under this milestone's change policy.
4. **A failed sub-solve leaves no record at all.** The semantics are deliberate
   (an execution failure is not a failure to converge), but the consequence is
   that a run failing at iteration 37 of 50 loses the ordered trace that required
   change 7 exists to preserve.
5. **The iteration scheme is prose.** `"Gauss-Seidel fixed-point iteration over a
   torn dependency cycle"` is a string in `provenance.assumptions`. The tolerance,
   the tear and the budget are typed; the method is not. A second scheme would
   force it; none exists.
6. **Solver lifetime is one call.** A fresh solver is constructed per problem per
   iteration — affordable only for closed-form participants. A provider with
   session state (a licensed session, an FMU retaining internal state) would be
   reset every iteration. **This is the sharpest edge facing the next milestone.**
7. **Restart from persisted state is numerically exact but has no concept.**
   Gauss–Seidel here is memoryless and the initial condition never advances, so
   seeding a fresh run from a persisted `final_values` reproduces the
   continuation — but nothing names that operation.
8. **`unsupplied()` reports; it cannot refuse.** An ambient legitimately imposed
   by the environment and a forgotten heat source read identically.
9. **The scalar assumption is now in an executed signature.**
   `Mapping[str, Quantity]` and a float max-norm presuppose one scalar per name.
   A field, tensor or distribution endpoint has no representation and no norm.
10. **`is_ratio_scale` depends on the units backend.** One call to pint's
    `get_base_units`, in a system pack, documented.
11. **`ProvenanceRecord.inputs` still carries a composite `"{problem}::{quantity}"`
    key**, because that field is `Mapping[str, Quantity]` in frozen core.
    Documented rather than silent.
12. **Two role vocabularies still have no mapping** (`VariableRole` vs
    `TwinDatumRole`). Unchanged from `MIN-FOUNDATION-ET` known unknown 10.
13. **Nothing heterogeneous, external, concurrent, distributed or at scale.** All
    code here was written by one author on one day.

---

# 16. Tests

All figures from the **final tree**, after every falsifier correction.

| Suite | Command | Result |
|---|---|---|
| Targeted | `pytest tests/test_electrothermal_vertical.py -q` | **62 passed** |
| FAST | `pytest tests/ -m "not expensive" -q` | **1249 passed**, 495 deselected |
| FULL | `pytest tests/ -q` | **1744 passed**, 0 failed |

Baseline before this milestone: **1682 FULL / 1187 FAST**.
`1682 + 62 = 1744` and `1187 + 62 = 1249`. **No pre-existing test was edited,
weakened, skipped, reordered or re-toleranced**, and none broke.

*(A local `--basetemp` is required on this machine: tests using `tmp_path` error
with `PermissionError` against the default Windows temp root. Environment, not
code — the same condition `MODEL0-R` and `MIN-FOUNDATION-ET` recorded.)*

Coverage against prereg §11: gates `G0` (`test_gate_g0`, `g0b`), `G1`
(`test_gate_g1`); TEST A (`test_a`, `a1`, `a2`, `a3`), B (`test_b`, `b2`, `b3`),
C (`test_c1`, `c2`), D (`test_d`), E (`test_e`, `e2`), F (`test_f`), G
(`test_g`–`g6`), H (`test_h`, `h2`, `h3`, `h4`, `h4b`), I (`test_i`–`i4`), J
(`test_j`, `j2`), L (`test_l`, `l2`, `l3`), M (`test_m`, `m2`), N (`test_n`), O
(`test_o`–`o3`), P (`test_p`); reductions `test_r1`–`r5`, `r7`, `r8`; H0(B)
(`test_h0b`); falsifier corrections `test_x1`–`x8`; regression boundary
(`test_k`, `k2`, `k3`).

## 16.1 Fail conditions (prereg §12)

All twelve checked, **none tripped**.

§12.1 (≤ 1 universal record) — **zero**. §12.2 (no schema bumped) — `test_o3`.
§12.3 (no domain branch in core) — `test_i`, with the F-1 caveat in §14.1.
§12.4 (outcome not inferred; no `ConvergenceState` member) — `test_b`, `test_b3`.
§12.5 (no banned channel) — `test_b2`. §12.6 (loop genuinely closes) — `test_a`.
§12.7 (no second instance authority; twin not mutated) — `test_n`.
§12.8 (no aliasing) — `test_h2`, `test_h3`. §12.9 (no pre-existing test edited)
— counts above; `test_k`. §12.10 (no relaxation) — `test_l3`.
§12.11 (no time marching) — `test_p`, `test_x4`. §12.12 (no generic framework)
— one module, one dispatch table, no registry, no scheduler.

---

# 17. Final decision and status

```text
Decision status:   PROPOSED
Evidence:          L1 EXERCISED  (per claim — §14.1; several claims are L0 or zero)
Milestone:         COMPLETE
```

**Verdict: KEEP.** The loop closes, coupled convergence is explicitly and
separately represented, provenance survives, and universal core gained nothing.

The null hypothesis was given a real chance on both halves. H0(A) lost on two
counts — 0/3/0 and 0 universal readers. **H0(B) partially won**: the loop carried
a structural assumption about topology that no domain scan could see, and the
2:1 case it broke on is one of the two systems nearest the commercial target. It
was closed by a refusal rather than by a rule, so the gap remains measured and
unfilled.

**Not frozen.** `PROPOSED` means these records are being built on and may be
revised. The promotion criterion is preregistered (§16 of the prereg) and is not
met: **a second, materially different coupled consumer written against these
records without editing them.** Until then they are system-pack records and are
labelled as such.

The five pack-local types stand in this order of confidence:
`TornEndpoint` and `FixedPointCouplingPlan` (forced by a measured gate),
`CoupledIteration` and `CoupledRun` (forced by the requirement to record a trace
rather than a verdict), and `CouplingOutcome` (kept on a naming argument after
losing its reduction, and the first candidate for deletion).

---

# 18. Exact next milestone

# `HETEROGENEOUS REAL PROVIDER PROOF`

**Not started here.** It requires its own preregistration, written before any
source file is added or edited.

The questions it inherits, sharpened by this milestone:

1. **Solver lifetime.** A fresh solver per problem per iteration is affordable
   only for closed-form participants. A provider with session state is reset
   every sweep (§15.6).
2. **Result identity.** `run_fixed_point` now refuses a result whose
   `problem_id` does not match the problem asked for — a guard added specifically
   because an external adapter is the producer most likely to return its own
   identity (F-4).
3. **Failure channel.** The executor signature is total and infallible by type. A
   provider that fails at iteration 37 destroys the trace (§15.4).
4. **Asynchrony.** The dispatch table is synchronous. No await point, no future,
   no partial completion.
5. **Whether a second consumer makes these records universal.** The promotion
   criterion is written down and is the only thing that would turn "reusable"
   from an argument into evidence.
