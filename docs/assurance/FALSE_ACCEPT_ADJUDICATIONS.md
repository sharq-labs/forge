# The two remaining hard false accepts, traced

`U00204` and `U01001` are the only two false accepts left on the hard
benchmark's dev split (1360/1400 exact, catch 1157/1159, FA 2, FR 0).

Both were traced stage by stage from the case file to the verdict. **Neither is
a code defect.** Both are proposals to correct benchmark ground truth, and
under this round's rule nothing here has been applied: the case files, the
expected verdicts, the split and every digest are untouched. Each section ends
with what would have to be decided, and by whom.

Format follows the landed events in `benchmarks/hard/ADJUDICATIONS.json`,
including its `independent_violation_search` — the check for whether a case is
caught by a condition *other* than the one its truth names.

---

## U00204 — `runaway`

| | |
|---|---|
| label | `inconsistent_inputs` |
| expected verdict | `NOT_SUPPORTED` (**unchanged**) |
| actual verdict | `SUPPORTED` |
| declared catcher | `thermal runaway` |
| stated reason | "alpha = 0.05 /K: the electro-thermal loop does not contract. A design that runs away…" |
| proposed classification | **`GROUND_TRUTH_PROBLEM`** |

### Stage trace

| Stage | Observed |
|---|---|
| Coupling | `CRITERION_MET`, 123 iterations of a 200 limit, largest change 8.54e-7 K against a 1e-6 K tolerance |
| Values | `final_temperature` 355.7382 K, `steady_state_temperature` 355.9132 K, `time_constant` 136.43 s |
| Applicability | all six models `in_domain`; no condition violated, none unknown |
| Validation | 3 checks, all pass; `analytic_reference_agreement` establishes `analytically_verified` |
| Verdict | `SUPPORTED` |

**First divergence: none inside Forge.** Every stage does what it claims. The
divergence is between the case's stated reason and the case's own physics.

### Why the stated reason does not describe this case

The steady state of a linear-TCR conductor at constant voltage is a quadratic:
`hA (T − T_amb) · R₀ (1 + α (T − T_ref)) = V²`. Solved exactly for U00204 it has
two real roots:

| root | T | R(T) | residual | physical |
|---|---|---|---|---|
| + | **355.832577 K** | +285.789 Ω | 1.1e-13 W | yes |
| − | 202.644 K | −243.700 Ω | 1.1e-13 W | no (negative resistance) |

The naive fixed-point map `T ← T_amb + V²/(R(T)·hA)` has `|f′| = 39.3` at the
seed — which is why an iteration started there thrashes — and `|f′| = 0.853` at
the root, so **the root is attracting**. The generator's own
`steady_temperature()` converges to 355.8325773546051 in **179 iterations**. It
does not return `None`.

So `shape_runaway` did not keep this draw because the loop failed to contract.
It kept it because of its other arm:

```python
t = steady_temperature(p["v"], p["r0"], p["alpha"], p["t_ref"], p["hA"], p["t_amb"])
if t is not None and abs(t - p["_t_ss"]) < 100:
    return None
```

`_t_ss` is set once in the base draw and **never refreshed after `alpha` is
overwritten**, so the surviving condition is "changing alpha moved the steady
state by ≥ 100 K". That is a different statement from "the design runs away",
and the reason text asserts the latter.

The design is also benign at that operating point — every declared limit is
clear by a wide margin:

| quantity | value | limit | utilisation |
|---|---|---|---|
| temperature | 355.83 K | 1163.53 K ceiling | 0.31 |
| temperature | 355.83 K | 1963.53 K melting | 0.18 |
| dissipation | 1.356 W | 10.861 W rated | 0.12 |
| current | 0.0689 A | 0.5516 A max | 0.12 |
| voltage | 19.69 V | 59.07 V max | 0.33 |
| \|T − T_ref\| | 62.68 K | 721.27 K band | 0.09 |

A positive temperature coefficient is self-limiting: resistance rises with
temperature, dissipation falls. This design cannot run away.

### Independent violation search (dev split, 26 `runaway` cases)

| population | count | Forge |
|---|---|---|
| no physical steady state exists (α < 0) | 21 | `TRANSFER_REFUSED` → `NOT_SUPPORTED` — correct |
| a stable steady state exists (α > 0) | 5 | 4 still `TRANSFER_REFUSED`; **U00204** converges |

No condition on any model in U00204's report is violated or unknown. There is
no independent violation to fall back on.

### What would have to be decided

Whether `runaway` truth should be assigned from *the existence and stability of
a physical operating point* rather than from *whether one particular naive
iteration found it inside its budget*. The recommended repair is to the
generator's selection criterion and reason text, not to Forge:

* keep the draw when `physical_root(...) is None` — genuinely no operating
  point;
* refresh `_t_ss` after `alpha` is overwritten, so the ≥100 K arm compares
  like with like, and give the cases it keeps a reason that says what it
  actually tested.

**This requires regenerating cases, which re-draws the hold-out.** It is
therefore not a change this round can make, and not one to make casually. Until
it is decided, U00204 stands as a case whose expected verdict this repository
can no longer justify.

---

## U01001 — `adv_unsound:small_overshoot`

| | |
|---|---|
| label | `limit_exceeded` |
| expected verdict | `NOT_SUPPORTED` (**unchanged**) |
| actual verdict | `SUPPORTED` |
| declared catcher | `operating_temperature_utilization` |
| stated reason | "Over the ceiling by 0.174 K. Small, and still over." |
| proposed classification | **`GROUND_TRUTH_PROBLEM`**, with a documentation defect in Forge |

### Stage trace

| Stage | Observed |
|---|---|
| Coupling | `CRITERION_MET`, 8 iterations, largest change 1.45e-7 K against 1e-6 K |
| Values | `final_temperature` **428.0257 K**, `steady_state_temperature` **428.2819 K**, τ 44.81 s |
| Declared ceiling | `maximum_operating_temperature` **428.1228 K** |
| Applicability | all six `in_domain`; `operating_temperature_utilization` **satisfied** |
| Verdict | `SUPPORTED` |

**First divergence: stage 6, applicability.** `operating_temperature_utilization`
is evaluated at the endpoint the run reaches (428.0257 K), which is *below* the
ceiling. The generator sized the ceiling against the **asymptote**:
`p["t_max"] = p["_t_ss"] - uniform(0.1, 0.5)`.

The payload declares `duration = 268.86 s = 6 τ`, so the marched run covers
`1 − e⁻⁶` of the way and stops 0.256 K short of the asymptote — more than the
0.174 K by which the ceiling was undercut. The body never reaches the ceiling
inside the mission the case declares.

### The evidence that settles which convention is right

Moving the ceiling to the peak `max(T₀, T_ss)` was measured across the whole dev
split. 28 cases sit between the two conventions (peak above the ceiling,
endpoint at or below it):

| effect of moving the ceiling to the peak | cases |
|---|---|
| **fixed** (wrong now, right under peak) | **1** — U01001 |
| **broken** (right now, wrong under peak) | **18** |
| unchanged | 9 |

All 18 that would break are `compound:horizon+tmax` cases expecting
`INSUFFICIENT_EVIDENCE` — precisely the family the landed
`2026-09-09.internal-fourier-number.screen` adjudication ruled on: under the
Fourier floor "the criterion observed nothing… NOT_SUPPORTED asserts evidence
against a design; these cases had none to assert." Reading the ceiling at the
asymptote would convert all 18 into `NOT_SUPPORTED` and contradict that landed
decision.

**So the endpoint convention is correct, and already adjudicated.** U01001's
expected truth is inconsistent with it. This is the same defect class the
generator's own `endpoint_temperature` docstring documents for *power ratings*
(case `S00709`, `NEEDS.md` B.6) — "sizing a rating against the asymptote and
then declaring a horizon the run stops short of states a rating the design does
not actually meet" — corrected there for `rated_power`, never applied to
`t_max`.

### Independent violation search (dev split, 50 `small_overshoot` cases)

| | count |
|---|---|
| scored as caught | 49 |
| **caught by the declared catcher** | **45** |
| caught by an unrelated condition | **4** — U01000, U01769, U01940, U01830 |
| not caught | 1 — U01001 |

The four are the finding worth carrying forward on its own. Their endpoints are
*also* below the ceiling and their `operating_temperature_utilization` is
*also* satisfied — they are counted as catches because
`radiation_to_convection_ratio` or a sibling happened to fail. Under an
asymptote reading all five behave identically; the score distinguishes them by
accident. **The family's real detection rate for its declared defect is 45/50,
not 49/50.**

### The Forge-side defect this exposed (not fixed here)

Two hard material ceilings in one report use different operating points:

| condition | evaluated at | documented as |
|---|---|---|
| `melting_temperature_utilization` | `max(T₀, T_ss)` | "bounds the whole trajectory including horizons the caller has not yet asked for" |
| `operating_temperature_utilization` | `T(duration)` | "a hard material limit rather than a modelling tolerance" |

Both are "the body must never get this hot". Nothing in the code or docs
reconciles them, and `derived_material_quantities` gives a binding-instant
parameter to the *floor* (`coldest_temperature`) and the *band*
(`furthest_temperature`) but **not** to the ceiling — the only path-dependent
condition of the three that cannot be told where it binds.

The measurement above says the endpoint is the right choice, so this is a
**documentation defect, not a behavioural one**, and changing the behaviour
would cost 17 net dev cases. It is recorded here rather than repaired because
writing the distinction down is what stops the next reader from "fixing" it.

### What would have to be decided

Whether `small_overshoot` should size `t_max` against `endpoint_temperature()`
— which the generator already computes, and already uses for ratings — instead
of `_t_ss`. That is the same one-line class of change made for `S00709`, and
like U00204 it regenerates cases and therefore re-draws the hold-out.

---

## Summary

| case | old expected | old actual | new expected | new actual | root cause | fix |
|---|---|---|---|---|---|---|
| U00204 | `NOT_SUPPORTED` | `SUPPORTED` | `NOT_SUPPORTED` (unchanged) | `SUPPORTED` (unchanged) | `GROUND_TRUTH_PROBLEM` — reason describes a non-contracting loop; the loop contracts, to a stable root the generator's own solver finds | **stopped**; proposal above |
| U01001 | `NOT_SUPPORTED` | `SUPPORTED` | `NOT_SUPPORTED` (unchanged) | `SUPPORTED` (unchanged) | `GROUND_TRUTH_PROBLEM` — ceiling sized against the asymptote; the endpoint convention is the one a landed adjudication requires | **stopped**; proposal above |

No benchmark file, expected verdict, split or digest was modified. The dev
figures are identical before and after this round.
