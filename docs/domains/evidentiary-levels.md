# Evidentiary levels in the battery and electrical domains

An audit of every passing validation check in `src/engcore/domains/battery/**`
and `src/engcore/domains/electrical/**` (excluding `ngspice.py`) that
establishes no `ValidationLevel`, following `NEEDS.md` §1.8b. Each is placed in
exactly one of three categories:

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

| Category | Count |
|---|---|
| earnable now (implemented this round) | **1** |
| earnable later | **3** |
| never earnable by this check | **7** |
| **total audited** | **11** |

Two further findings that are not in any category — one check that establishes
a level it may not have earned, and one record inconsistency — are recorded
under *Found while auditing*.

---

## The table

### Battery — `src/engcore/domains/battery/solver.py`

| Check | Category | Decision |
|---|---|---|
| `coulomb_balance_residual` | **never earnable by this check** | The trajectory is affine. `evaluate_step` computes `z = z0 - I t / (eta Q)`, and the check evaluates `\|dz/dt + I / (eta Q)\|` on it, which is zero by algebra. `NEEDS.md` §1.8b proposed "an independent integration of `dz/dt`", and that does not help twice over: a constant right-hand side is integrated exactly by *any* method, including forward Euler in one step, so an "independent" march is the same three multiplications in a different order and detects nothing this residual does not; and `NUMERICALLY_CONVERGED` is unavailable regardless, because the solver has no discretization to refine — the same argument the lumped model's reference module sets out at length. The check does real work as a guard against a flipped sign or a dropped efficiency. It is not evidence, and there is no version of it that is. |
| `rint_terminal_residual` | **earnable later** | Genuinely earnable, and `NEEDS.md` §1.8b names the route: the Rint model *is* a circuit — one ideal source at `OCV(z)` in series with `R_int` — and `electrical/dc` solves circuits by MNA assembly and LU factorization, sharing no arithmetic with `evaluate_step`. Agreement would be `CROSS_SOLVER_VALIDATED` by this repository's own definition of that level (`kinetics/cstr/validation.py`: different equations, different algorithm, separate implementation). **What it costs is not the code.** It would be the first domain→domain import in `src/engcore/domains/` — cross-domain composition lives in `systems/` today, and nothing under `domains/` imports a sibling. Hosting it in `systems/` instead keeps the boundary but puts the check outside the solver's own `validate()`, so it never reaches the `ValidationReport` the credibility package reads. That is an architecture decision, not a check. A second, smaller caveat: the circuit topology would have to be transcribed by hand into a `Circuit` record, and that transcription is the thing most likely to be wrong and the thing the comparison cannot check. |
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
| *(the whole report)* — native vs ngspice | **earnable later** | `NEEDS.md` §1.8b's suggestion, and defensible: the two paths share `assemble` but not the solve, so agreement would be `CROSS_SOLVER_VALIDATED`. Cost is environmental rather than architectural — the check can only run where a provider is present, so it is `NOT_RUN` on most machines, and `ngspice.py` is where it would have to live. |

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
