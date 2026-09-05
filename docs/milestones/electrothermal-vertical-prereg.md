# ELECTRO-THERMAL VERTICAL PROOF — Preregistration

**Milestone:** `ET-VERTICAL` — the first genuine **closed-loop** multiphysics
execution proof.
**Kind:** vertical execution milestone. It is not `COUPLE0`, not a coupling
platform, and not the heterogeneous-provider proof.
**Decision status target:** at most `PROPOSED`.
**Evidence target:** at most `L1 EXERCISED`. `L2` is **excluded in advance** — see §14.
**Date:** 2026-09-02
**Branch:** `electrothermal-vertical-proof`
**Preregistered before implementation.** Everything below was written before any
source file was added or edited on this branch. The working tree was verified
clean at `caa4ed5`.

> **This file is immutable.** It records what was committed to *before* results
> were observed. Executed results, deviations, corrections, adversarial findings
> and the final classification go in
> `docs/electrothermal-vertical-evidence.md` and nowhere else.
>
> This is **not** a freeze document.

**Canonical milestones verified present before this document was written:**

| Milestone | Decision | Evidence | Record |
|---|---|---|---|
| `DATA-BOUNDARY0` | `PROPOSED` | `L1 EXERCISED` | master context §56, `docs/data-boundary0-evidence.md` |
| `MODEL0-R` differential | `DESIGN-FROZEN` | `L2 DIFFERENTIATED` (scoped) | master context §58, `docs/model0r-differential-evidence.md` |
| `MIN-FOUNDATION-ET` | `PROPOSED` | `L1 EXERCISED` (record); `L0 REASONED` (deferrals) | master context §64, `docs/min-foundation-electrothermal-evidence.md` |

---

# 1. The single question

> Can Crafty **execute** a real two-way electro-thermal coupling loop, reach and
> record coupled convergence correctly, and preserve
> model / realization / solver / provenance semantics — **without domain-specific
> logic leaking into universal core**?

The previous milestone *represented* the loop and deliberately refused to close
it: `run_open_loop_pass` performs one electrical solve, one thermal step, and
evaluates `R(T₁)` **without feeding it back**. This milestone feeds it back.

Nothing else is decided. This milestone does not define `COUPLE0`, `FIELD0`,
`TOPO0`, `SYSTEM0`, `MAT0`, physical connectors, mesh transfer, interpolation,
waveform relaxation, Newton or Jacobian coupling, adaptive relaxation, external
provider abstraction, API/MCP, or HVAC.

---

# 2. Hypotheses

## H1 — primary

> The existing Crafty scientific contracts plus the `MIN-FOUNDATION-ET`
> foundation are **sufficient** to execute a real two-way coupled simulation
> with explicit coupling convergence and correct provenance, requiring **at most
> a minimal universal coupling/execution concept**.

"Minimal" is quantified in advance: **at most one new universal semantic record**
under `src/engcore/scientific/`. Two or more falsifies H1 as stated and must be
reported as a falsification, not re-described as a success.

**The predicted number is zero.** See §3.

## H0 — null, and it is allowed to win

> **H0(A)** — closing the loop exposes a missing architectural distinction that
> cannot be represented safely with the current contracts without one of:
> domain-specific orchestration inside universal core; metadata or string
> conventions; incorrect convergence semantics (coupling convergence inferred
> from, or written into, solver convergence); a duplicated instance authority
> alongside `ScientificTwin`; or a larger new abstraction than one record.
>
> **H0(B)** — the loop closes only because the executing code secretly knows it
> is electro-thermal: remove the electrical/thermal knowledge and the coupling
> machinery no longer determines anything.

**H0(A) is a legitimate outcome and is recorded as a result, not repaired.** A
milestone whose every abstraction survives unchallenged is to be treated as
suspect.

## Stopping condition, declared before results

If the **G0 gate** of §7 passes — i.e. a deterministic reader can derive an
executable order *and* every value needed to start it from the serialized
records alone — then no plan record of any kind is required anywhere, plain
function arguments suffice, and the milestone records that as the result.

---

# 3. Reviewer verdict, and the option selected before implementation

`architecture-decision-reviewer` was run **before this document**, on the
decision *"What is the minimum execution concept required to close this specific
electro-thermal loop?"*, comparing:

* **A** — domain-level orchestration only; zero new universal records; the
  typed coupling records live in the electro-thermal **system pack**.
* **B1** — a minimal universal fixed-point concept (pre-execution plan record +
  post-execution outcome record) under `engcore/scientific/`, loop in the pack.
* **B2** — B1 plus a universal executor taking a solve-callback protocol.
* **C** — a generic coupling graph / runtime.
* **D0** — a plain `converged: bool`, no typed record anywhere.
* **P** — express the coupling verdict as a `ValidationCheck` on the existing
  `ValidationReport`.

**Verdict: ACCEPT WITH CHANGES, selecting A.**

The reasoning that decided it, recorded here because it constrains what may be
built: there is **no universal reader** of coupling-execution information in the
repository — no planner, no compiler, no scheduler — and all three are
explicitly deferred. Reuse by a second coupled pair is therefore an `L0
REASONED` argument, which is the same standard under which
`MIN-FOUNDATION-ET` honestly refused to promote ten of its eleven deferrals.
`MIN-FOUNDATION-ET` added its one universal record because a **measurement**
(5 / 4 / 5 dimensionally admissible sources, one target invisible) showed that no
reader could recover the fact. No analogous measurement exists here. Meanwhile
the two future systems nearest the commercial target — 2:1 fan-in on one body,
and fluid+thermal convective transport where upstream/downstream is a runtime
property of the sign of the mass flow — both bend or break the shape B would
freeze now.

`D0` was rejected because a bare boolean cannot distinguish *the criterion was
met* from *the budget ran out one iteration short*. `P` was rejected because
`ValidationReport.attained_levels` is a claim about **scientific evidence**, and
a coupling verdict there merges coupling convergence with scientific validity —
the exact collapse this milestone exists to prevent.

## 3.1 The eleven required changes, carried into this preregistration

Each is binding. Numbering is the reviewer's.

1. **Never compute the coupling change with `Quantity` arithmetic and never
   compare it with `Quantity.compare`.** Compare magnitudes in one explicitly
   named unit fixed for the run, and **refuse an offset (non-ratio-scale) unit**
   for that unit and for the tolerance.
2. **Do not reuse `ConvergenceState`** for the coupling outcome. Mint a small
   pack-local enum with only the members actually executed.
3. **The tear, the seed, the tolerance and the budget live in a typed,
   frozen, schema-tagged, round-tripping pre-execution record** — not in kwargs.
   The tolerance is a `Quantity`, dimension-checked against the torn edge.
4. **Do not derive the tear or the seed from existing records**, and do not add a
   rule that would.
5. **Derive the change from the torn edge, and name it for what it is** — an
   *iterate change*, not a *residual*.
6. **The `while` loop stays in `engcore.systems.electrothermal`.** No
   solve-callback protocol is added to core.
7. **Record the ordered iterate trace, not just a final verdict.**
8. **Absolute tolerance only.** No relative criterion in this milestone.
9. **The coupled outcome may not be written into** `ScientificResult.convergence`,
   `RawSolverOutput.convergence`, `ValidationLevel` /
   `ValidationReport.attained_levels`, `SolverSettings.tolerances`,
   `ProvenanceRecord.tolerances`, or any `metadata` / `diagnostics` /
   `artifacts` mapping.
10. **Preregister the promotion criterion** that would make these records
    universal — §15.
11. **Cycle detection, if added, is a pure reporting function and must not
    choose a tear.**

## 3.2 Two facts verified against the running code before this document was written

Both are stated here because they are *inputs* to the design, and because
verifying a reviewer's claim rather than accepting it is the point.

**(a) The offset-unit hazard is real, not theoretical.** Executed against the
repository's own `Quantity`:

```text
Quantity(71.12,'degC').compare(Quantity(26.85,'degC'))  ==  44.27
Quantity(0.001,'kelvin').magnitude_in('degC')           == -273.149
dimensionality('degC') == dimensionality('kelvin')      ==  [temperature]
```

A tolerance declared in kelvin, compared against a change carried in `degC`,
converts to **−273.149** and every iteration "converges" immediately.
`dependency.py`'s own docstring explicitly sanctions a `degC` source satisfying
a `kelvin` dependency, so the path is reachable. Required change 1 is therefore
implemented as a **refusal**, and the refusal is dimension-agnostic:

> a unit is admissible as a comparison unit iff
> `Quantity(0.0, u).magnitude_in(base(u)) == 0.0`,
> where `base(u)` is pint's base unit for that dimension.

Verified in advance: `kelvin`, `rankine`, `watt`, `ohm`, `1/kelvin`,
`joule/kelvin` pass; `degC` (273.15) and `degF` (255.372) are refused. Note that
`rankine` correctly passes — the rule tests for a ratio scale, not for a
temperature unit, and contains no temperature knowledge.

**(b) An existing test already constrains where a universal record could go.**
`tests/test_min_foundation_electrothermal.py::test_f2` pins
`engcore.scientific.composition.__all__` to exactly four names. Fail condition
§12.9 forbids editing it. This is recorded as a **constraint discovered**, not as
the reason A was selected: the reviewer's argument stands without it, and a
passing test must never be allowed to decide an architecture.

---

# 4. The scientific system under test

## 4.1 Equations

One conductor with a linear temperature coefficient of resistance, dissipating
into a lumped thermal body that exchanges with a single ambient, supplied by an
ideal DC voltage source.

```text
property    R(T)   = R_ref · (1 + α · (T − T_ref))                      [ohm]
electrical  I      = V / R          (single element across an ideal source)
            P      = I² R = V² / R                                      [watt]
thermal     C dT/dt = P − hA · (T − T_amb)
            T_ss    = T_amb + P / (hA)                                  [kelvin]
            τ       = C / (hA)                                          [second]
            T_end   = T_ss + (T₀ − T_ss) · exp(−t_dur / τ)              [kelvin]
```

The electrical side is the **existing, unmodified** `engcore.domains.electrical.dc`
MNA path. The property and thermal sides are the **existing, unmodified**
`MIN-FOUNDATION-ET` modules. Nothing in §4 is new physics; what is new is that
the loop is closed.

## 4.2 The closed loop

```text
        seed T⁽⁰⁾
            ↓
    ┌── T⁽ⁿ⁾ ──▶ R(T⁽ⁿ⁾) ──▶ electrical solve ──▶ P⁽ⁿ⁾ ──▶ thermal solve ──┐
    │                                                                       │
    └──────────────────── T⁽ⁿ⁺¹⁾  ◀── iterate change |T⁽ⁿ⁺¹⁾ − T⁽ⁿ⁾| ◀──────┘
```

**Iteration n ≥ 2 solves the electrical problem at a resistance the previous
thermal solve produced.** That is the entire difference from
`MIN-FOUNDATION-ET`, and TEST A exists to assert it.

## 4.3 Three candidate loop semantics — one chosen, one confirmatory, one rejected

The thermal problem publishes **three kelvin-valued quantities that a dimension
check cannot tell apart**:

| Endpoint | Namespace | Time level |
|---|---|---|
| `temperature` | problem variable, `role=STATE` | t₀ |
| `final_temperature` | result metric | t = duration |
| `steady_state_temperature` | result metric | t → ∞ |

Three candidate loop semantics follow, and the choice is preregistered:

* **(i) PRIMARY — implicit one-interval transient coupling.** Source endpoint
  `final_temperature`; `T₀` and `duration` held fixed across iterations. The
  fixed point is the self-consistent end-of-interval state. This is the primary
  configuration for CASES A, B, C1, E and F.
* **(ii) CONFIRMATORY — coupled steady state.** Source endpoint
  `steady_state_temperature`. `T₀` and `duration` do not enter the answer; the
  fixed point is the exact solution of the coupled algebraic system. Run as a
  second configuration with **one field changed and no code changed**.
* **(iii) REJECTED, AND NAMED AS THE TRAP — time marching.** Advancing `T₀` to
  the previous iteration's `T_end` each pass. This is **not** a coupling
  iteration: the iterate would be a *time level*, and `|T⁽ⁿ⁺¹⁾ − T⁽ⁿ⁾|` would be
  a time-stepping increment. Reporting it as coupling convergence would collapse
  coupling iteration into time integration. **It is a fail condition (§12.11)
  that the implementation performs time marching under the name of coupling.**

**(i) and (ii) differ by 3.376 K on identical inputs** (§10). That difference is
the milestone's sharpest single measurement: two endpoints of the same
dimension, in the same problem, produce different converged physics, and only
the enumerated *name* distinguishes them. It is the executed consequence of the
`MIN-FOUNDATION-ET` falsifier finding D-1, which separated `temperature` from
`final_temperature` before commit.

## 4.4 Declared approximation

Configuration (i) evaluates `R` at the **end-of-interval** temperature and holds
it constant over the interval. That is an implicit (backward) statement over one
interval and carries a first-order coupling error which **is not quantified
here**. Configuration (ii) carries no such error: at steady state `T` is
constant and `R(T)` is unambiguous. This is declared as an assumption on the
records, not buried.

## 4.5 Uniqueness — the claim CASE B is allowed to make

Substituting the steady balance into the property law, with `x = R(T) > 0`:

```text
(hA / R_ref) · x²  +  hA · x · (α·T_ref − 1 − α·T_amb)  −  α · V²  =  0
```

a quadratic in `x` whose leading coefficient is positive and whose constant term
is `−αV² < 0` for `α > 0`. It therefore has **exactly one positive root**. The
physically admissible coupled steady state is unique for every configuration
with `α > 0`, `hA > 0`, `R_ref > 0`, `V ≠ 0`.

**For `α < 0` the constant term is positive and two positive roots are
possible** — a stable and an unstable operating point. Uniqueness is therefore
claimed **only for `α > 0`**, and CASE C2 deliberately uses `α < 0`.

## 4.6 A contraction result, predicted in advance

Differentiating the steady-state fixed-point map `g(T) = T_amb + V²/(hA·R(T))`
and eliminating `V²` at the fixed point:

```text
|g'(T*)|  =  α (T* − T_amb) / (1 + α (T* − T_ref))
```

`|g'| < 1  ⟺  α (T_ref − T_amb) < 1`. But `R(T_amb) = R_ref(1 + α(T_amb − T_ref)) > 0`
is **the same condition**. Hence:

> **Prediction P-C.** For a linear-TCR conductor with `α > 0`, the coupled
> fixed-point map is a contraction at its fixed point *exactly when* the
> resistance is positive at ambient. Every configuration that violates it is
> already refused by the domain for having a non-positive resistance.
> **No relaxation can be forced by this system for `α > 0`.**

For configuration (i) the map is contracted further by `1 − exp(−t_dur/τ) ∈ (0,1)`.

This prediction is falsifiable: it is checked by measuring the observed
convergence ratio against the closed form (TEST L).

---

# 5. The coupling convergence policy — fixed before coding

| Item | Decision |
|---|---|
| **Quantity compared** | The quantity transported by the **torn** dependency. In every case here: temperature. |
| **Unit** | `kelvin`. One unit is fixed for the whole run; both sides are converted to it by `magnitude_in` before subtraction. |
| **Criterion** | **Absolute only.** `max over torn edges of |x⁽ⁿ⁾ − x⁽ⁿ⁻¹⁾| ≤ tol`. |
| **Tolerance** | `1e-6 kelvin`. |
| **Budget** | `max_iterations = 50` (nominal); overridden per case where the case is *about* the budget. |
| **Non-convergence behaviour** | The loop **stops and returns a record** whose outcome is `ITERATION_LIMIT_REACHED`, carrying the full trace and the final iterate change. It does **not** raise. |
| **Sub-solve failure** | **Not** caught, **not** reported as non-convergence. A domain guard refusing an inadmissible value is an execution failure and propagates. Conflating the two is exactly the collapse §6 forbids. |
| **Declaration error** | A dependency that cannot be bound (wrong dimension, missing quantity) is refused **before the first iteration**, by raising. It is a malformed declaration, not a scientific finding. |

## 5.1 Why `1e-6 kelvin`, chosen a priori

* It is ~7½ orders of magnitude below the coupled temperature rise (≈ 38.6 K),
  and far below any physically meaningful thermal measurement resolution.
* It is ~7 orders **above** double-precision round-off at 340 K
  (`eps · 340 ≈ 7.5e-14 K`), so it is attainable and is not a round-off race.
* The predicted contraction ratio is ≈ 0.129, so the criterion costs ≈ 10
  iterations. **It was not chosen to make a test pass**: a tolerance chosen for
  that purpose would be loose, and this one is tight enough to require nine
  iterations more than the previous milestone performed.

## 5.2 Why no relative criterion

A relative criterion divides by a value, and is meaningless wherever the zero of
the scale is conventional — `degC`, gauge pressure. **Nothing in any Crafty
record states whether a quantity's zero is physical.** A record that offered a
relative tolerance would be offering a criterion it cannot police. For the
self-heating problem specifically, the physically meaningful scale is the
temperature *rise above ambient*, not the absolute kelvin value, so a relative
criterion on absolute `T` would also be misleading. Absolute only; recorded as a
deferral with its reason, not as an omission.

## 5.3 The comparison belongs to coupling execution

The criterion is **not** a property of the electrical solver, the thermal
solver, or the property evaluator. None of them can see the other side. It lives
on the coupling plan and nowhere else. Writing it into `SolverSettings.tolerances`
or `ProvenanceRecord.tolerances` is a fail condition (§12.5).

---

# 6. Three things that must not collapse

Preserved explicitly, and each asserted by a test:

```text
Numerical convergence  ≠  Coupling convergence  ≠  Scientific validity
```

* The electrical MNA solve reports `ConvergenceState.CONVERGED`.
* The property evaluation and the thermal step report
  `ConvergenceState.NOT_APPLICABLE` — closed-form evaluation neither converges
  nor fails to.
* **Neither implies that the coupled system converged.** CASE C executes a run
  in which every sub-solve succeeds and coupling convergence is `False`.
* **Coupled convergence does not imply the model is valid.** CASE F executes a
  run that converges to `T* ≈ 499 K` while the property model's declared
  validity domain is `200–450 K`. The coupling outcome does not touch, overwrite
  or upgrade any `ValidationReport`, and `assess_resistance_validity` still
  reports the model inapplicable.

---

# 7. The G0 and G1 gates — built and executed FIRST

`MODEL0-R` finding D4 recorded a preregistered gate that was *analysed* rather
than *executed*. `MIN-FOUNDATION-ET` fixed that by building its N0 gate first.
The same discipline applies here: both gates below are **built and run before
any coupling record is written**, and each result is a count.

## 7.1 G0 — is the declared dependency set executable as declared?

> A deterministic reader is given only the serialized records — the three
> problems, the three `QuantityDependency` records, the twin, the models and the
> realizations. It must return (a) an execution order and (b) an initial value
> for every quantity needed to start. It may not parse the internal structure of
> a quantity name, may not read orchestration source, and may not consult an LLM.

* **Gate passes** → no plan record is needed anywhere; kwargs suffice; H1 wins
  in its strongest form and §2's stopping condition applies.
* **Gate fails** → the failure is reported as **measured counts**, not as an
  argument: the number of admissible topological orders, the number of
  admissible tears, and, for each candidate tear, the number of records that
  supply a seed for it.

### Predicted G0 outcome, with the numbers stated in advance

**Predicted: the gate FAILS, with counts 0 / 3 / 0.**

* **Admissible topological orders: 0.** The three dependencies form one cycle of
  length 3 (`electrical → thermal → property → electrical`).
* **Admissible tears: 3.** Every edge of a 3-cycle yields a valid order when
  removed; nothing in any record ranks them.
* **Records supplying a seed, for each of the three tears: 0.**
  `build_resistance_problem` declares `temperature` as `role=STATE` with **no
  initial condition**; the thermal problem's initial condition is on
  `temperature` (t₀), a **deliberately different endpoint** from
  `final_temperature`, severed by falsifier finding D-1 precisely so that one
  name cannot denote two time levels. `unresolved_inputs()` reports the set to
  account for and its own docstring disclaims completeness for configured
  parameters.

**If any count comes back as 1 rather than 0 / 3 / 0 — i.e. the order or the
seed is genuinely determined — no plan record is added and the result is
recorded as such.** This is the falsifiable part of the prediction.

**A rule that would select a tear is forbidden (required change 4).** The only
rule that selects one here — "tear the edge whose target already carries a
value" — keys on the DC domain modelling resistance as a configured
`ScientificParameter`, which `unresolved_inputs`' own docstring records as an
**undeclared** modelling accident. Promoting an accident to an execution law is
the C-2 leak class: a structural assumption in generic code containing no domain
word.

## 7.2 G1 — does anything here need a *universal* reader?

> Count the consumers inside `src/engcore/scientific/` that would read a
> coupling plan or a coupling outcome.

**Predicted: 0.** There is no planner, no execution-plan compiler and no
scheduler in the repository, and all three are deferred. **If the count is ≥ 1,
option A falls and a universal record is forced** — that outcome is admissible
and must be reported.

---

# 8. What will be built

## 8.1 Placement

| Item | Location | New? |
|---|---|---|
| Coupling records + the loop | `src/engcore/systems/electrothermal/coupled.py` (**new file**) | new module |
| Package exports | `src/engcore/systems/electrothermal/__init__.py` | edited (exports only) |
| Tests | `tests/test_electrothermal_vertical.py` (**new file**) | new |

`src/engcore/systems/electrothermal/resistor_body.py` is **not edited**. Its
`test_j` walks that module's AST and asserts no `While` node, exactly one
`solve_circuit` call, and the absence of the identifiers `relax`,
`fixed_point`, `rollback`, `iterate`, `residual`. The open-loop pass remains
exactly what the previous milestone committed, and this milestone is additive
beside it.

**Nothing under `src/engcore/scientific/` is added or edited** — predicted, and
a fail condition if violated beyond one record (§12.1).

## 8.2 The typed records, named in advance so scope cannot expand after results

All pack-local. All frozen dataclasses, all schema-tagged, all round-tripping.

```text
CouplingOutcome                    enum, members limited to those EXECUTED
    CRITERION_MET
    ITERATION_LIMIT_REACHED

TornEndpoint                       electrothermal_torn_endpoint/1
    dependency     : QuantityDependency     the edge that is cut
    initial_value  : Quantity               the seed for its TARGET

FixedPointCouplingPlan             electrothermal_fixed_point_plan/1
    plan_id            : str
    dependencies       : tuple[QuantityDependency, ...]
    torn               : tuple[TornEndpoint, ...]
    absolute_tolerance : Quantity
    max_iterations     : int

CoupledIteration                   electrothermal_coupled_iteration/1
    index                  : int
    results                : tuple[ScientificResult, ...]
    largest_iterate_change : Quantity

CoupledRun                         electrothermal_coupled_run/1
    plan, outcome, iterations, final_largest_change,
    converged_values, provenance
```

### Invariants fixed in advance

* Every `TornEndpoint.dependency` must be a member of `plan.dependencies`.
* **All torn edges must share one dimension**, and `absolute_tolerance` must
  carry that dimension. A plan with torn edges of **mixed** dimension is
  **refused**, because one scalar tolerance cannot serve them and **no record
  states a normalization**. The refusal is the honest statement of the limit.
* `absolute_tolerance` must be finite and strictly positive.
* `max_iterations ≥ 1`.
* The comparison unit and the tolerance unit must be **ratio-scale** (§3.2a).
* `TornEndpoint.initial_value` must carry the transported dimension.
* Association is **structural** everywhere: `TornEndpoint` pairs an edge with its
  seed in one record rather than by position in two parallel tuples. This is the
  `ExecutionBinding` rule (`MODEL0-R` finding D2) applied one level out.

### Three reductions performed *before* writing, and recorded here

Recorded in the preregistration so that they cannot be presented afterwards as
discoveries:

1. **`CouplingTransfer(dependency, value)` — designed and dropped.** The value
   that crossed each edge at iteration *n* is
   `iteration.result_for(dep.source_problem_id).values[dep.source_quantity]`.
   It is derivable from records the iteration already carries, so it is an
   accessor, not a record.
2. **`IterateChange(endpoint, previous, current)` — designed and dropped.** The
   previous value is iteration *n−1*'s transported value on the same edge, and
   the plan's seed for *n = 1*. Derivable.
3. **`CouplingResidual` as a name — dropped.** It is an *iterate change*, not
   the residual of any equation (required change 5). preCICE defines its
   measures on the exchanged coupling data; OpenMDAO's block-Gauss-Seidel
   default is the iterate difference and had to add `use_apply_nonlinear` later
   because the two are different quantities. Naming it precisely now costs
   nothing.

## 8.3 What the loop is forbidden to contain

No relaxation factor, no damping, no line search, no Aitken/Anderson
acceleration, no rollback, no checkpointing, no event handling, no time
synchronization, no scheduler, no participant registry, no transfer operator, no
interpolation, no mesh, no field, no external provider, no concurrency.

**§15 governs relaxation specifically:** if the loop oscillates or fails to
converge for a configuration whose physics is admissible, the milestone **stops**
and relaxation is preregistered as a separate mini-decision before any `omega`
is written. Prediction P-C (§4.6) says this will not be needed for `α > 0`.

---

# 9. Reduction attacks — run after it works, and allowed to delete

Per brief §18. For **every** new type in §8.2, the question is:

> Can this be replaced by `ScientificProblem` + `QuantityDependency` + a plain
> deterministic function, without losing coupling-convergence semantics,
> provenance, identity, inspectability, reuse, or the separation of
> numerical / coupling / scientific validity?

The named attacks, fixed in advance:

| # | Attack | Target |
|---|---|---|
| R1 | Plain kwargs `(seed=…, tol=…, max_iter=…)` instead of `FixedPointCouplingPlan` | the plan record |
| R2 | `converged: bool` instead of `CouplingOutcome` | the enum |
| R3 | Two parallel tuples `torn` / `seeds` instead of `TornEndpoint` | the pairing record |
| R4 | A `float` tolerance instead of a `Quantity` | the tolerance's type |
| R5 | Fields on `QuantityDependency` instead of a separate plan | the whole design |
| R6 | `ScientificResult.metadata` / `RawSolverOutput.diagnostics` for the trace | banned channels |
| R7 | `ProvenanceRecord` alone as the coupling record | pre- vs post-execution |
| R8 | Derive `largest_iterate_change` rather than store it | the trace field |

**At least one type must be deleted or demonstrably survive a serious attempt.**
R2 is expected to be the closest call: at two enum members the enum is one step
from a boolean, and the evidence document must either defend it or delete it.

---

# 10. Executed cases, with predicted values stated in advance

All predictions below were computed **analytically, before implementation**, from
the equations of §4.1 in a throwaway script that imports nothing from `engcore`.
The implementation must reproduce them.

Nominal declaration, reusing `MIN-FOUNDATION-ET`'s numbers so the two milestones
are directly comparable:

```text
conductor  R_ref = 10 Ω @ T_ref = 293.15 K,  α = 0.00393 K⁻¹
body       C = 2.5 J/K,  hA = 0.05 W/K,  T_amb = 300 K,  T₀ = 300 K,  t_dur = 120 s
supply     V = 5 V
plan       torn edge = D2 (thermal.final_temperature → property.temperature)
           seed = 300 K,  tol = 1e-6 K,  max_iterations = 50
```

### CASE A — nominal convergent case (configuration (i))

**Predicted: `CRITERION_MET` after 10 iterations.**

| n | T⁽ⁿ⁾ in [K] | R(T⁽ⁿ⁾) [Ω] | P [W] | T_end out [K] | \|ΔT\| [K] |
|---|---|---|---|---|---|
| 1 | 300.000000000 | 10.269205000 | 2.434463038 | 344.272270673 | 4.427e+01 |
| 2 | 344.272270673 | 12.009105237 | 2.081753761 | 337.858026420 | 6.414e+00 |
| 3 | 337.858026420 | 11.757025438 | 2.126388186 | 338.669732046 | 8.117e-01 |
| 4 | 338.669732046 | 11.788925469 | 2.120634325 | 338.565094379 | 1.046e-01 |
| … | | | | | |
| 9 | 338.577014354 | 11.785281664 | 2.121289988 | 338.577018039 | 3.685e-06 |
| 10 | 338.577018039 | 11.785281809 | 2.121289962 | 338.577017565 | **4.741e-07** |

**Converged `T* = 338.577018 K`, `R* = 11.785282 Ω`, `P* = 2.121290 W`.**

> **Iteration 1 reproduces `MIN-FOUNDATION-ET`'s open-loop pass exactly**
> (`R = 10.269205 Ω`, `P = 2.434463 W`, `T₁ = 344.272271 K`), and iteration 2
> performs the second electrical solve that milestone explicitly refused. That
> correspondence is asserted by TEST A2.

### CASE A2 — the same loop, one endpoint changed (configuration (ii))

Source endpoint `steady_state_temperature` instead of `final_temperature`.
**No code change; one field.**

**Predicted: `CRITERION_MET` after 11 iterations, `T* = 341.953436 K`,
`R* = 11.917975 Ω`, `P* = 2.097672 W`.**

**Difference from CASE A: 3.376418 K.** Same dimension, same problem, same
records, different physics — separated only by the enumerated metric name.

### CASE B — different initial state, same equilibrium

Configuration (i), seeds `250 K` and `440 K`.

| Seed | Predicted outcome | Predicted `T*` | Iterations |
|---|---|---|---|
| 250 K | `CRITERION_MET` | 338.577018 K | 11 |
| 440 K | `CRITERION_MET` | 338.577018 K | 10 |
| 300 K (CASE A) | `CRITERION_MET` | 338.577018 K | 10 |

All three must agree to within `2 · tol`. **Uniqueness is claimed only under the
`α > 0` condition proved in §4.5, and the evidence document must say so.**

### CASE C1 — deliberate non-convergence by iteration budget

Nominal, `max_iterations = 2`, `tol = 1e-6 K`.

**Predicted: `ITERATION_LIMIT_REACHED` after 2 iterations, final iterate change
`6.414 K`.** Every sub-solve succeeds: electrical `CONVERGED`, property and
thermal `NOT_APPLICABLE`. **Coupling convergence is `False`.**

### CASE C2 — deliberate non-convergence by physics

A negative-TCR conductor at a **non-contracting** operating point, chosen so that
`|g'| = 1` exactly at the fixed point:

```text
α = −0.004 K⁻¹,  T_ref = 300 K,  R_ref = 10 Ω,  hA = 0.04 W/K,  T_amb = 300 K, V = 5 V
configuration (ii);  seed 300 K;  tol = 1e-6 K;  max_iterations = 50
```

The double root is at `Δ* = 1/(2|α|) = 125 K`, i.e. `T* = 425 K`, `R* = 5 Ω`, and
`|g'(T*)| = 1.0` exactly. The iterate creeps as `Δ_n = 250·n/(n+1) / 2`,
so the change decays as `O(1/n²)` and no reachable budget converges it.

**Predicted: `ITERATION_LIMIT_REACHED` after 50 iterations, final iterate change
`4.902e-02 K`.** Every iterate lies in `[300 K, 422.55 K]` — **inside** the
property model's declared validity domain `200–450 K` — and every resistance
lies in `[5.10 Ω, 10.00 Ω]`, strictly positive. So the configuration is
scientifically admissible throughout and **every sub-solve succeeds**.

This is the case brief §16 CASE C mandates: *individual solver success may be
true BUT coupling convergence is false*, on legitimate physics rather than an
artificial cap.

### CASE D — broken / incompatible dependency, rejected before execution

Four sub-cases, all expected to raise **before the first iteration**:

| # | Malformation | Predicted detection |
|---|---|---|
| D-i | `V:n1` [volt] declared as the source of `heat_input` [watt] | `WRONG_DIMENSION` from `check_against` |
| D-ii | A source quantity no record enumerates | `MISSING` from `check_against` |
| D-iii | Tolerance in `watt` for a `kelvin` torn edge | refused at plan construction |
| D-iv | Two torn edges of **different** dimensions under one tolerance | refused at plan construction |

D-iii and D-iv are checkable **only because the tolerance is a typed `Quantity`
on a typed record**. A `float` kwarg cannot be checked at all — this is the
executed justification for reduction attack R4.

### CASE E — multiplicity stress

**Two conductors in series across one source, each with its own thermal body.**
Series rather than parallel, deliberately: across an ideal source, parallel
elements do not interact, and the multiplicity would not be exercised. In
series, heating `R1` changes `I`, which changes `P2`, which changes `T2` — the
two coupling cycles are genuinely coupled through the circuit.

```text
conductor 1  R_ref = 10 Ω @ 293.15 K,  α = 0.00393 K⁻¹
conductor 2  R_ref = 20 Ω @ 293.15 K,  α = 0.00060 K⁻¹
body 1       C = 2.5 J/K,  hA = 0.05 W/K   (τ = 50 s)
body 2       C = 5.0 J/K,  hA = 0.02 W/K   (τ = 250 s)
supply       V = 12 V,  t_dur = 120 s,  T_amb = T₀ = 300 K
plan         TWO torn edges, one per body;  seeds 300 K;  tol = 1e-6 K
```

**Predicted: `CRITERION_MET` after 8 iterations**, with

```text
T1* = 328.898146 K   R1* = 11.404902 Ω   P1* = 1.589064 W
T2* = 355.089513 K   R2* = 20.743274 Ω   P2* = 2.890195 W
I*  = 0.373271562 A
```

**The identity questions this case is built to answer, with predictions:**

* One electrical problem enumerates **both** `R:R1` and `R:R2` as parameters, and
  one electrical result publishes **both** `resistor_power:R1` and
  `resistor_power:R2`. **Predicted: `(problem_id, quantity_name)` disambiguates
  them and no aliasing occurs** — because the *domain* names per instance, and
  the record references the enumerated name without ever parsing it.
* **Predicted: no `ComponentInstance` concept is forced.** If one is, exactly
  what became ambiguous is recorded.
* **Predicted: a single scalar tolerance suffices here only because both torn
  edges carry the same dimension.** The mixed-dimension case is refused (D-iv),
  and the absence of a normalization rule is recorded as a known unknown, not
  filled.
* **Predicted: fan-in remains unrepresented.** This case is 2:2, not 2:1. Two
  sources on one target still check clean with no combination rule, exactly as
  `MIN-FOUNDATION-ET` `test_b8` measured. Nothing is invented to fix it.

### CASE F — converged, and scientifically invalid

```text
nominal conductor;  hA = 0.04 W/K,  C = 2.5 J/K,  t_dur = 600 s,  V = 12 V
configuration (i);  seed 300 K;  tol = 1e-6 K;  max_iterations = 50
```

**Predicted: `CRITERION_MET` after 25 iterations, `T* = 498.994793 K`,
`R* = 18.089700 Ω`, `P* = 7.960331 W`.**

`T*` lies **outside** `LINEAR_TCR_MODEL`'s declared validity domain
(`200–450 K`). Predicted simultaneously:

* coupling outcome: `CRITERION_MET`;
* every sub-solve: succeeded, with a passing `ValidationReport`;
* `assess_resistance_validity`: the model is **not** applicable at `T*`;
* the coupling outcome writes nothing into any `ValidationReport` and upgrades
  no `ValidationLevel`.

Three independent verdicts, one run. This is the executed form of §6.

---

# 11. Required tests

| ID | Test |
|---|---|
| **A** | **Real closed loop.** At least two coupling iterations occur, and the resistance the electrical solve consumed at iteration *n ≥ 2* is the resistance the previous iteration's thermal solve produced. Asserted against the electrical result's own `provenance.inputs`, not against the runner's variables. |
| **A2** | **Continuity with the previous milestone.** Iteration 1 of CASE A reproduces `run_open_loop_pass`'s numbers to `rel=1e-12`, and iteration 2 is the second electrical solve that milestone did not perform. |
| **B** | **Coupling convergence is explicit.** It has a dedicated typed representation. Asserted: it is not in any `metadata`, `diagnostics` or `artifacts` mapping anywhere on the path; it is not `ScientificResult.convergence`; and it is not computed from the sub-solves' `ConvergenceState` values. |
| **C** | **Solver convergence ≠ coupling convergence.** CASE C1 and CASE C2: every sub-solve reports success while the coupling outcome is `ITERATION_LIMIT_REACHED`. |
| **D** | **Scientific validity remains separate.** CASE F: coupling converged, sub-solves valid, model outside its declared validity domain; no `ValidationReport` on the path is touched by the coupling outcome. |
| **E** | **Provenance.** Every executed path preserves canonical `model → realization → solver` `ExecutionBinding`s, at arity > 1 across three solvers, deduplicated and order-independent. No participant tuple is reconstructed positionally. |
| **F** | **Dependency feedback cycle.** The dependency set contains both `electrical → thermal` and `thermal → electrical` and is traversable to a cycle by a records-only reader, with no name parsing. |
| **G** | **Dimensional incompatibility.** CASE D-i and D-ii are refused before execution. |
| **H** | **Multiplicity.** CASE E: no silent aliasing; every endpoint distinct; the two power metrics and the two resistance parameters are separately identified. |
| **I** | **No domain leakage.** `src/engcore/scientific/**` gains no file and no edit; the existing lexical scans still pass; and the new pack module is checked for the reverse leak — that it imports no `engcore.scientific` internals beyond published contracts. |
| **J** | **No bulk-data regression.** No array is inlined into `ScientificResult`, `diagnostics`, `metadata` or `artifacts`. The trace is typed and `O(max_iterations)`. |
| **K** | **Existing milestones green.** `DATA-BOUNDARY0`, `MODEL0-R` differential and `MIN-FOUNDATION-ET` tests all still pass, **unedited**. Baselines to be met: FULL **1682**, FAST **1187** passed / 495 deselected. |
| **L** | **The contraction prediction P-C.** The measured convergence ratio matches `α(T*−T_amb)/(1+α(T*−T_ref))` (times `1−e^{−t/τ}` for configuration (i)) to within 1 %, and the `α<0` case measures `|g'| = 1`. |
| **M** | **Offset units are refused.** A plan whose comparison or tolerance unit is `degC` or `degF` is refused; `kelvin` and `rankine` are accepted. The refusal contains no temperature vocabulary. |
| **N** | **The twin is not the runtime state.** The `ScientificTwin` is not mutated, not re-versioned per iteration, and is not an input to the loop. The number of twin versions that *would* be required if it were the runtime authority is measured and recorded. |
| **O** | **Serialization.** Every new record round-trips deterministically and rejects an unknown schema string. No existing schema version moves. |
| **P** | **Time-marching trap.** The runner does not advance the thermal problem's initial condition between iterations; `T₀` is identical in every iteration's thermal provenance. |

Plus the two gate tests of §7 (`G0`, `G1`), whose outcomes are evidence either
way.

---

# 12. Fail conditions

Declared before implementation. Any one means the milestone did not succeed as
specified, and the evidence document says so plainly.

1. More than **one** new universal semantic record under `src/engcore/scientific/`
   is required (falsifies H1 as stated). **Predicted: zero.**
2. Any existing serialized schema version is bumped.
3. A domain-specific branch or domain literal (`electrical`, `thermal`,
   `resistor`, `joule`, `resistance`, or any equivalent including a units-based
   domain sniff) appears anywhere under `src/engcore/scientific/`.
4. Coupling convergence is **inferred from** the sub-solves' `ConvergenceState`
   values, or a new `ConvergenceState` member is added.
5. The coupling outcome or tolerance is written into `ScientificResult.convergence`,
   `RawSolverOutput.convergence`, `ValidationLevel`,
   `ValidationReport.attained_levels`, `SolverSettings.tolerances`,
   `ProvenanceRecord.tolerances`, or any `metadata` / `diagnostics` / `artifacts`
   mapping.
6. Only one electrical → thermal pass runs, or the updated resistance is computed
   and never reused in a later electrical solve.
7. A second authority for scientific instance state is created alongside
   `ScientificTwin`, or the twin is mutated to carry runtime iteration state.
8. Component identity aliases silently in CASE E.
9. Any pre-existing test is edited, weakened, skipped, reordered, or has a
   tolerance loosened; or `resistor_body.py` is edited; or any file under
   `src/engcore/domains/thermal/` or `src/engcore/domains/electrical/dc/` changes;
   or any frozen digest moves.
10. Relaxation, damping or acceleration is added without the separate
    preregistration §15 requires.
11. The implementation performs **time marching** (advancing the thermal initial
    condition between iterations) and reports the resulting increment as coupling
    convergence.
12. A generic coupling framework — scheduler, participant registry, transfer
    operators, pluggable convergence policies — is required to make the proof
    pass.

---

# 13. Change policy and frozen artifacts

* `src/engcore/scientific/**` — **no file added, no file edited.** Predicted.
* `src/engcore/domains/thermal/**` — byte-pinned by T1/T2/T3; untouched.
* `src/engcore/domains/electrical/dc/**` — untouched.
* `src/engcore/domains/thermal_lumped.py`, `src/engcore/domains/electrical/material.py`
  — untouched. The coupled loop must run against the modules as the previous
  milestone committed them. If it cannot, that is a finding, not a licence to
  edit them.
* `src/engcore/systems/electrothermal/resistor_body.py` — untouched.
* All pre-existing test files — untouched.
* `docs/data-boundary0-*.md`, `docs/model0r-differential-*.md`,
  `docs/min-foundation-electrothermal-*.md` — untouched.
* This preregistration, after its own commit.

`ModelRealizationDefinition` remains `DESIGN-FROZEN` and gains no field. The
open applicability-envelope question (`model0r-differential-evidence.md` §4) is
**not** decided here; this milestone may collect evidence about it and must not
resolve it.

---

# 14. Evidence ceiling, declared before running

```text
Decision status ceiling:   PROPOSED
Evidence ceiling:          L1 EXERCISED
```

**`L2 DIFFERENTIATED` is excluded in advance and may not be awarded.** Two
domains are not two consumers. `L2` requires two **materially different**
consumers that could have disagreed, and every configuration here is one
electro-thermal skeleton written by one author on one day. `L3 STRESSED` is not
claimable at all.

**Per-claim levels are required**, not one level for the milestone. Stated in
advance:

* The new coupling records, if any survive: at most `PROPOSED / L1 EXERCISED`.
* `MODEL0-R`'s model/realization/solver separation remains `DESIGN-FROZEN /
  L2 DIFFERENTIATED`. This milestone does not upgrade it.
* `QuantityDependency` remains `L1` **unless this milestone materially
  strengthens its evidence** — and the evidence document must say what changed if
  it claims so. Executing the declared set, rather than merely declaring it, is a
  candidate strengthening; being executed by *one* runner is not differentiation.
* Anything not exercised gains **zero** evidence and must be recorded as such —
  named in advance: fan-in combination, mixed-dimension coupling norms, field or
  tensor endpoints, bidirectional/acausal transport, external providers,
  concurrency, restart from persisted state, and coupling across more than two
  domains.

---

# 15. Relaxation — a separate decision, not a knob

Per brief §15 and master context §60.

If any admissible configuration oscillates or fails to converge **and relaxation
would be required to make it converge**, the implementation **stops**. Relaxation
is then a newly forced architectural and numerical decision and must be
preregistered as its own mini-decision — the quantity relaxed, the policy, why a
fixed `omega` is defensible, and what evidence sets it — **before** any `omega` is
written.

Silently tuning a relaxation factor until a demonstration converges is a fail
condition (§12.10). Prediction P-C (§4.6) states that for `α > 0` this will not
arise; if it does, P-C is falsified and that is the finding.

---

# 16. Promotion criterion — what would make these records universal

Recorded in advance so that DEFER is a decision and not drift.

> The coupling plan and outcome records become candidates for promotion into
> `engcore/scientific/` when a **second, materially different coupled consumer** —
> a different domain pair, or a 2:1 fan-in on one body — can be written **against
> the first consumer's published records without editing them**, and its plan and
> outcome have the same shape.

That is the `L1 → L2` test of master context §55.2, and it is the only thing
that would make "reuse" evidence rather than an argument. Until then, these are
system-pack records and are labelled as such.

---

# 17. Stop rule

Stop as soon as the closed loop executes, the required cases and tests of §10–§11
are complete, the reduction attacks of §9 are executed, and the falsification
pass is complete.

Do **not** continue into: `HETEROGENEOUS REAL PROVIDER PROOF`, API/MCP, HVAC,
`FIELD0`, `TOPO0`, generic physical connectors, preCICE integration, or a
coupling platform of any kind.

Per master context §60: at most **two** adversarial rounds. If material
uncertainty survives both, obtain executable evidence through a spike rather than
a third round of argument.

**The next milestone is the `HETEROGENEOUS REAL PROVIDER PROOF`.** It is not
begun here.
