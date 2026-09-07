# Evidentiary levels across the domains

An audit of every passing validation check in `src/engcore/domains/**` that
establishes no `ValidationLevel`, following `NEEDS.md` §1.8b. Each is placed in
exactly one of three categories:

**Scope, and how it grew.** The first pass covered `battery/**` and
`electrical/**` excluding `ngspice.py`, and audited eleven rows. This pass
extends it to every domain except the byte-frozen `domains/thermal/`, which
adds `ngspice.py`, `kinetics/cstr/`, `thermal_models/conduction1d_schemes.py`
and `thermal_models/lumped.py` — ten more rows. Rows from the first pass are
kept verbatim where they still hold and are marked **(revised)** where this
pass changed them.

| | |
|---|---|
| **earnable now** | the evidence that justifies a level was built this round |
| **earnable later** | the evidence is achievable, and what it costs is stated |
| **never earnable by this check** | no rearrangement of *this* check earns a level, and why |

**The standard applied**, taken from
`domains/thermal/conduction1d/validation.py` and from the lumped model's
reference comparison added in the same round as this audit:

1. the reference must be reached by a route that shares no code and no derived
   quantity with the thing it checks;
2. the tolerance must be stated and its size argued;
3. a disagreement must FAIL, never degrade into a level-free pass;
4. an unavailable reference must be NOT_RUN, never a pass.

A check that only confirms the solver reproduced its own algebra earns nothing.
That is the correct outcome for most of the checks below, and saying so is the
point of the table rather than a shortfall in it.

---

## Counts

| Category | Count | of which added this pass |
|---|---|---|
| earnable now (implemented) | **1** | **0** |
| earnable later | **4** | **1** |
| never earnable by this check | **16** | **9** |
| **total audited** | **21** | **10** |

**Checks that pass today while establishing nothing: 16.** That is the number
the audit exists to report, and the arithmetic behind it is: 21 rows, minus the
4 whole-report routes, minus `metric_dimensions` (which now establishes
`DIMENSIONALLY_VALID`), leaves 17 check rows; minus `cell_step_evaluated`,
which is emitted only on the unsuccessful path and so never passes, leaves 16.
Fifteen are in the *never* category and one — `rint_terminal_residual` — is
*earnable later*.

One more sits outside `domains/**` and is visible in the product's own default
run: `declared_limits_are_mutually_consistent`, assembled at the MCP boundary.
It is not in the 16 because it is out of scope, and it is reasoned about under
*Found while auditing* so the next pass over that boundary does not start
cold.

**Nothing was earnable now in this pass, and that is the finding rather than a
shortfall.** The first pass had one: `material.py` gained a `metric_dimensions`
check with a reference outside the solver's arithmetic. Every check added to
the audit this pass is an admissibility screen, a satisfied-constraint check or
a solver reporting on itself, and the two that are neither — the whole-report
routes for the DC domain and for the conduction schemes — are blocked on cost
or on a frozen file rather than on anyone's willingness. Each is priced below.
Awarding a level to any of them would be the move the rule exists to prevent.

Two further findings from the first pass that are not in any category — one
check that establishes a level it may not have earned, and one record
inconsistency — are recorded under *Found while auditing*, joined by three
from this pass.

---

## Which rungs are occupied, measured

`ValidationLevel` has six members besides the `UNVERIFIED` sentinel. Measured
by running the solvers rather than read off the source:

| Level | Occupied | By what |
|---|---|---|
| `DIMENSIONALLY_VALID` | **yes** | `dc/validation.py`, `battery/solver.py`, `material.py`, `cstr/validation.py`, `conduction1d_schemes.py`, and the frozen conduction solver |
| `NUMERICALLY_CONVERGED` | **yes** | `dc/validation.py`'s linear residual; `cstr`'s `tolerance_independence`; the frozen conduction solver's refinement study |
| `ANALYTICALLY_VERIFIED` | **yes** | `thermal_models/lumped.py`'s series-recurrence reference; `cstr`'s `analytic_invariant_agreement` |
| `CROSS_SOLVER_VALIDATED` | **yes** | `cstr`'s `independent_steady_state_agreement` |
| `BENCHMARK_VALIDATED` | **no** | nothing, anywhere |
| `EXPERIMENTALLY_VALIDATED` | **no** | nothing, anywhere |

**Four of six, and the two empty ones are empty for a reason that no amount of
work in this repository will change.** `BENCHMARK_VALIDATED` requires a curated
reference benchmark — a published problem with published answers, maintained by
somebody who is not us — and this repository has none and is not in a position
to certify one. `EXPERIMENTALLY_VALIDATED` requires a laboratory measurement of
a physical article, and there is no laboratory, no article and no instrument
anywhere in this project. **Neither is earnable later either**, and neither is
listed with a cost, because a cost would imply a route. Saying that plainly is
worth more than finding a reading of "benchmark" loose enough to fit a test
suite, which is exactly what `dc/models.py` and `cstr/problem.py` already
refuse in their own words when they set `validation_status` to
`SELF_CONSISTENT`.

**The gap between a domain's ladder and a report's ladder.** The DC solver's
own report attains two levels, measured. The electro-thermal report the MCP
boundary assembles carries **three checks and one level** — the DC solver's six
checks are not among them, because that report is built around the thermal
sub-result. That is not a level anybody failed to earn; it is evidence that
exists and does not travel. Recorded under *Found while auditing*.

---

## The table

### Battery — `src/engcore/domains/battery/solver.py`

| Check | Category | Decision |
|---|---|---|
| `coulomb_balance_residual` | **never earnable by this check** | The trajectory is affine. `evaluate_step` computes `z = z0 - I t / (eta Q)`, and the check evaluates `\|dz/dt + I / (eta Q)\|` on it, which is zero by algebra. `NEEDS.md` §1.8b proposed "an independent integration of `dz/dt`", and that does not help twice over: a constant right-hand side is integrated exactly by *any* method, including forward Euler in one step, so an "independent" march is the same three multiplications in a different order and detects nothing this residual does not; and `NUMERICALLY_CONVERGED` is unavailable regardless, because the solver has no discretization to refine — the same argument the lumped model's reference module sets out at length. The check does real work as a guard against a flipped sign or a dropped efficiency. It is not evidence, and there is no version of it that is. |
| `rint_terminal_residual` | **earnable later** | Genuinely earnable, and `NEEDS.md` §1.8b names the route: the Rint model *is* a circuit — one ideal source at `OCV(z)` in series with `R_int` — and `electrical/dc` solves circuits by MNA assembly and LU factorization, sharing no arithmetic with `evaluate_step`. Agreement would be `CROSS_SOLVER_VALIDATED` by this repository's own definition of that level (`kinetics/cstr/validation.py`: different equations, different algorithm, separate implementation). **What it costs is not the code.** It would be the first domain→domain import in `src/engcore/domains/` — cross-domain composition lives in `systems/` today, and nothing under `domains/` imports a sibling. Hosting it in `systems/` instead keeps the boundary but puts the check outside the solver's own `validate()`, so it never reaches the `ValidationReport` the credibility package reads. That is an architecture decision, not a check. A second, smaller caveat: the circuit topology would have to be transcribed by hand into a `Circuit` record, and that transcription is the thing most likely to be wrong and the thing the comparison cannot check. **(revised)** Since the first pass, `scientific/consensus.py` landed and removes about half the cost: declaring two routes independent, comparing them and awarding the level is now core machinery rather than something this check would have to invent — `electrical/dc_consensus.py` is a worked example of the declaration. What is left is exactly the part that was never code: somebody has to import the electrical domain from the battery domain, and the topology transcription is still the thing the comparison cannot check. Category unchanged. |
| `cell_step_evaluated` | **never earnable by this check** | Emitted only on the unsuccessful path, where its outcome is `FAIL`. It never passes, so it is not in scope: a level on it would be unreachable code. |

`metric_dimensions` (`solver.py`) already establishes `DIMENSIONALLY_VALID` and
is not audited here — it is the pattern the row below was built from.

### Electrical — `src/engcore/domains/electrical/material.py`

| Check | Category | Decision |
|---|---|---|
| `resistance_strictly_positive` | **never earnable by this check** | An admissibility bound. Confirming a number lies in the range the surrounding linear DC formulation accepts is not verification against anything, and the module's own docstring has always said so. Left at `establishes=None`, with the detail string extended to say that no rearrangement of it would help. |
| *(new)* `metric_dimensions` | **earnable now — DONE** | This solver's report attained nothing, which made every credibility package built on a resistance evaluation `INSUFFICIENT_EVIDENCE`; it is the second casualty named in `NEEDS.md` §1.8b. Resolved the only way the standard allows: not by relabelling the admissibility check but by adding one with a reference outside the solver's arithmetic. The `ModelOutputSpec` on `LINEAR_TCR_MODEL` / `RATED_LINEAR_TCR_MODEL` declares the metric's dimension; the solver did not write it, and a metric extracted into the wrong unit disagrees with it. Earns `DIMENSIONALLY_VALID`. Tests in `tests/domains/electrical/test_material_validation.py` displace the declared exemplar and confirm the check fails — which is what says it is reading the record rather than itself. |

### Electrical DC — `src/engcore/domains/electrical/dc/validation.py`

The report here already attains `DIMENSIONALLY_VALID` and
`NUMERICALLY_CONVERGED`, so none of these four blocks a verdict. They are
audited because §1.8b lists them.

| Check | Category | Decision |
|---|---|---|
| `kirchhoff_current_law` | **never earnable by this check** | The strongest check in this file and still unlevellable. It rebuilds signed branch currents from the component list rather than re-reading a row of the MNA matrix, so it can catch a wrong conductance stamp — genuinely independent *reconstruction*. But what it establishes is that the solution satisfies a conservation law, not that it agrees with an independently obtained solution, and today's `ValidationLevel` has no member for that. The code already says so at `dc/validation.py:358-365`. Inventing one is explicitly refused: §1.8b's closing paragraph is right that adding a level so more reports clear the bar is the move the rule exists to prevent, and four checks wanting one is an argument about convenience, not about evidence. |
| `voltage_source_relation` | **never earnable by this check** | Same category and same reason. Recomputes `V+ - V- - Vs` from the source records. A satisfied constraint, not an independent solution. |
| `power_balance` | **never earnable by this check** | Tellegen's theorem over absorbed power, reconstructed from the element list. It is a *necessary* condition on any consistent solution and holds for a wrong answer that is wrong consistently — a mis-stamped conductance changes both the voltage and the power it implies. No level fits. |
| `resistor_metric_consistency` | **never earnable by this check** | The weakest of the four and honest about it in its own docstring: the current is derived here as `I = V/R`, so `V - I·R` vanishes by construction and to rounding. It guards a defective metric-extraction path. It is not evidence about the solution, and cannot be made into any. |
| *(the whole report)* — a closed-form comparison | **earnable later** | The one route to `ANALYTICALLY_VERIFIED` in this domain: for a series-parallel-reducible topology the node voltages have a closed form, and graph reduction is a genuinely different algorithm from matrix factorization. It would be `NOT_RUN` on any circuit that is not reducible — a bridge, for instance — which mirrors `cstr/reference.py`'s `invariant_is_exact` guard and is the honest shape. Cost: a series-parallel reduction with a reducibility test, roughly 150 lines plus tests, in a new `dc/reference.py` that must not import `mna` or `solver`. |
| *(the whole report)* — native vs ngspice | **earnable later** | `NEEDS.md` §1.8b's suggestion, and defensible: the two paths share `assemble` but not the solve, so agreement would be `CROSS_SOLVER_VALIDATED`. Cost is environmental rather than architectural — the check can only run where a provider is present, so it is `NOT_RUN` on most machines, and `ngspice.py` is where it would have to live. **(revised)** Half-built since the first pass. `electrical/dc_consensus.py` declares both routes, their shared components and the tolerance, and `CrossSolverConsensus.to_check` emits the `ValidationCheck` that carries the level — that is the architecture, done, with the independence argument written down rather than assumed. It is still `earnable later` for two reasons, both unchanged: the provider has to be installed for the comparison to run at all, and the consensus is a statement *between* two results, so no solver's own `validate()` is in a position to make it — which leaves it outside the `ValidationReport` the credibility package reads. |

---

### Electrical DC — `src/engcore/domains/electrical/ngspice.py`

Excluded from the first pass; audited here. Both checks pass in any run that
produces a report at all.

| Check | Category | Decision |
|---|---|---|
| `realization_precondition_non_singular` | **never earnable by this check** | The most valuable check in the adapter and still unlevellable, which is the clearest illustration in this table of what a level is and is not. It tests `rank(A) = size(A)` — a property of the assembled matrix alone — because on a structurally singular circuit the provider returns an exact zero vector that satisfies every equation, and *no check over `(A, x)` can see it*. Its own docstring makes that argument. But what it establishes is that the problem was well posed, not that the answer agrees with anything: it is a precondition, in the same category as `resistance_strictly_positive`, and a precondition is what you check *before* there is evidence to have. There is no rearrangement of a rank test that becomes a comparison. |
| `provider_element_metric_consistency` | **never earnable by this check** | Reconciles the provider's own current and power channels against its own voltage channel and Crafty's declared `R`. Cross-*channel* consistency inside one route's answer, not agreement with a second route — a provider wrong about the operating point is wrong consistently across all three channels and passes. Two further reasons it could not carry a level even if the physics were stronger: the admission gate already refuses anything that violates these relations, so by the time a report exists the check **can only pass**, and a check that cannot fail is not evidence; and its own docstring records that an earlier form of this milestone had the check and no gate, detected a corrupted provider power correctly, and changed nothing. |

### Kinetics CSTR — `src/engcore/domains/kinetics/cstr/validation.py`

Excluded from the first pass; audited here. **This domain occupies four rungs**
— `DIMENSIONALLY_VALID`, `NUMERICALLY_CONVERGED`, `ANALYTICALLY_VERIFIED` and
`CROSS_SOLVER_VALIDATED` — more than any other in the repository, so the three
rows below are what is left after the earnable evidence was already taken.

| Check | Category | Decision |
|---|---|---|
| `integration_reported_success` | **never earnable by this check** | The integrator's own report that it finished. This is the canonical non-evidence: a library asserting its own success is the one claim that cannot be checked by reading the claim, and the whole architecture of this repository exists because a converged solve is not a validated result. Useful — a `FAIL` here stops everything downstream — and unlevellable at any level, in any rearrangement. |
| `trajectory_finite` | **never earnable by this check** | No NaN and no infinity in the marched states. An admissibility screen on the output, the direct analogue of `field_finite` below and of `resistance_strictly_positive` above. It confirms the answer is a number; a level is a claim about *which* number. |
| `state_physically_admissible` | **never earnable by this check** | Concentrations non-negative and the temperature inside the declared envelope. Stronger than `trajectory_finite` because it reads the physics rather than the floating point, and still an admissibility screen: a trajectory can be admissible at every point and wrong at every point. The same category as `power_balance` — a necessary condition that a consistently wrong answer satisfies. |

### Thermal models — `src/engcore/domains/thermal_models/conduction1d_schemes.py`

Excluded from the first pass; audited here. Not the frozen conduction solver —
`domains/thermal/` is byte-pinned and out of scope — but the scheme-carrying
solver beside it, which attains `DIMENSIONALLY_VALID` and nothing else.

| Check | Category | Decision |
|---|---|---|
| `field_finite` | **never earnable by this check** | max\|u\| is a number. As above. |
| `amplitude_decay` | **never earnable by this check** | The discrete maximum principle: diffusion cannot amplify, so max\|u\| may not exceed the initial amplitude of 1. A genuinely good check — it is a property of the *equation* rather than of any scheme, so it catches a scheme run outside its stability envelope without being told which scheme ran. It is still not evidence about the answer. **Stability is not convergence**: Lax equivalence needs consistency as well, and this check establishes neither consistency nor a refinement sequence. A stable scheme marching a wrong problem decays exactly as obediently. There is no level for "did not blow up", and inventing one would make `NUMERICALLY_CONVERGED` mean two different things. |
| `boundary_conditions_held` | **never earnable by this check** | The homogeneous Dirichlet values are held to 1e-14. The scheme imposing its own constraint, read back — the same shape as `voltage_source_relation` in the DC table and the same verdict for the same reason: a satisfied constraint is not an independently obtained solution. |
| *(the whole report)* — a refinement study | **earnable later** | The one route to `NUMERICALLY_CONVERGED` here, and the module already says so: `discretization_convergence` is emitted `NOT_RUN` with the detail *"convergence under refinement is a claim about a sequence of solves and cannot be established by one"*, which is the correct shape and the honest one. The frozen conduction solver does exactly this and is the pattern to copy. **Cost: a report becomes N solves rather than one**, since the sequence has to refine `dx` and `dt` together and recover an observed order of accuracy — and for the explicit FTCS scheme the stability constraint ties `dt` to `dx²`, so halving `dx` quarters `dt` and each refinement level costs four times the work rather than two. That is a real decision about what a solve costs, not a missing function. **Explicitly rejected as an alternative**: comparing a single coarse march against a closed-form solution of the same PDE. Such a form is available and the route is genuinely independent, but the difference between it and the march is the scheme's *truncation error*, which is O(dt) rather than round-off, so the tolerance would have to be a truncation-error estimate — and any tolerance loose enough to let a coarse run pass would be a bound chosen from the answer. That is the failure mode this repository has already paid for three times, in `Fo = 0.2`, in beryllium's `θ_D/3` and in `Damköhler ≤ 10`. |

### Thermal models — `src/engcore/domains/thermal_models/lumped.py`

| Check | Category | Decision |
|---|---|---|
| `lumped_balance_residual` | **never earnable by this check** | Referred to in prose throughout the first pass and never given a row; it gets one here. It evaluates \|C dT/dt − Q + hA(T − T_amb)\| on the closed form that solves that balance, so it vanishes by construction to rounding — self-consistency, and its own detail string says so. **This is the row that shows the rule working as intended.** When `SUPPORTED` began requiring at least one attained level, this solver's reports became `INSUFFICIENT_EVIDENCE`, correctly. The response was not to relabel this check: it was to build `lumped_reference.py`, an independent series recurrence sharing only the governing equation, whose `analytic_reference_agreement` earns `ANALYTICALLY_VERIFIED`. This check still establishes nothing, and still should. |

---

## Found while auditing

Neither is a `establishes=None` check, so neither belongs in the table. Both
are recorded rather than acted on.

**`linear_system_residual` awards `NUMERICALLY_CONVERGED` from a linear
residual** (`dc/validation.py:157-165`). The frozen conduction validation
refuses exactly this, in its opening paragraphs: *"The linear residual of a
direct sparse factorization sits at round-off in every run, coarse or fine, so
treating it as convergence would certify the 8-cell solve exactly as
confidently as the 512-cell one."*

The DC case is not identical — the MNA system is the exact statement of the
circuit's Kirchhoff laws rather than a discretization of a continuum, so there
is no discretization error for a refined solve to reveal. But that cuts the
other way: with nothing to refine, there is no sequence whose limit could be
examined, and the level is *not applicable* rather than *attained* — the same
conclusion the lumped model reached this round about its own closed form.

Recommendation: move it to `establishes=None` with a detail string saying the
system is solved exactly and there is nothing to converge. The report would
still attain `DIMENSIONALLY_VALID`, so no verdict moves and no package
downgrades. **Not changed here** — un-awarding a level from a solver this
widely used is a decision to take deliberately, not a side effect of an audit,
and it is recorded in `NEEDS.md` for that decision.

**A failing `metric_dimensions` used to carry `establishes`.** Both
`battery/solver.py` and the new check in `material.py` set the level
unconditionally. `ValidationReport.attained_levels` filters on `passed`, so no
verdict was ever affected — but a serialized check reading `"outcome": "fail"`
beside `"establishes": "dimensionally_valid"` contradicts itself for any reader
who does not already know about that filter. Both are now conditional on the
outcome. No behaviour change.

---

## Found while auditing — second pass

Three, none of them a `establishes=None` check, so none belongs in the table.
All three are recorded rather than acted on: each would change a file this pass
does not own.

**The DC solver's evidence does not reach the report a caller reads.** Measured:
`solve_circuit` produces six checks attaining `DIMENSIONALLY_VALID` and
`NUMERICALLY_CONVERGED`; the electro-thermal report the MCP boundary assembles
carries three checks attaining `ANALYTICALLY_VERIFIED`, and none of the DC six
is among them. The report is built around the thermal sub-result and the
electrical solve contributes its *values* and its *validity assessments* but
not its *validation*. That is not a level anybody failed to earn — it is
evidence that exists, in this process, in this run, and does not travel. It is
also why the ladder looks emptier from the product's default example than it is
from inside the repository. The fix is at the boundary (`mcp/problem.py`),
which this pass does not own.

**No new evidence can reach the DC domain's own report either.** Both the
checks and the assembly live in `dc/validation.py`, and `dc/solver.py` calls
it; both files are frozen by name. So the first pass's *"a closed-form
comparison ... in a new `dc/reference.py`"* cannot be wired even once it is
written, and would sit beside the domain the way `dc_consensus.py` does. That
raises the cost of that row above what the first pass estimated: it is no
longer 150 lines plus tests, it is 150 lines plus tests plus a decision about
where a frozen solver's report may grow. Recorded on the row rather than
silently absorbed.

**`declared_limits_are_mutually_consistent` passes and establishes nothing**,
and it is one of the three checks in the product's own default run. It compares
two of the caller's declarations against each other — a melting temperature
above a maximum operating temperature — which makes it the same shape as a
`CrossLimitCondition` rather than a check over a result. Its verdict would be
**never earnable by this check**: nothing was computed and nothing was compared
against an independent route, so there is nothing for a level to be about. It
is not in the counts because it lives in `mcp/problem.py`, outside this audit's
`domains/**` scope, and is noted here so the next pass over that boundary finds
it already reasoned about.

