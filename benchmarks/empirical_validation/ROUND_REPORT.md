# Empirical and Independent-Problem Validation

**Verdict: INDEPENDENT-PROBLEM VALIDATION PASSED — AVAILABLE EXTERNAL EVIDENCE AGREES.**

Not "empirical validation passed". That phrase requires measured or published
benchmark data across the model surface, and this environment has none. What
this round establishes is narrower and is stated as such: all sixteen shipped
models solve a problem that was specified without any engcore type, and every
piece of external evidence that does exist here — one independently written
circuit simulator, one published standard, one hashed constants table — agrees.
Nine of the sixteen models finish the round marked
`EMPIRICAL_EVIDENCE_NOT_ESTABLISHED`, and that is the finding for them, not a
gap that was papered over.

---

## The question this round was set up to answer

The previous round compared engcore against independently written mathematics
and found 255 oracle-backed rows and no disagreement. It also recorded a gap it
could not close: all five repository route pairs came back `PARTIAL`, because
while none of them shared numerics, **every one of them shared the problem
statement**. Both sides were handed the same declaration object.

That leaves one specific way to be wrong:

```
  declaration (possibly wrong)
        |                |
     solver A         solver B
        |                |
     answer A   ===   answer B      <-- agreement proves nothing about
                                        whether the declaration was right
```

This round removes that. Every comparison now begins at a **raw fixture**: a
plain JSON object of physical quantities, with the unit written into the key
name, containing no engcore type and no pre-derived quantity. Two adapters read
it. Adapter A builds the engcore declaration. Adapter B builds the reference
problem. **They do not import each other, and adapter B does not import
engcore.** Every unit factor and every derived quantity is written out twice,
once in each file.

---

## What was found

### The headline numbers

| | |
|---|---|
| Models on the surface | 16 of 16, each with at least one independent-construction case |
| Primary comparison rows | 140, of which 0 disagree |
| Held-out rows | 47, of which 0 disagree |
| Problem-construction fields compared | 153: 129 EXACT, 24 TRANSFORMED_CORRECTLY, 0 ALTERED, 0 LOST, 0 AMBIGUOUS |
| Rows against ngspice 42 (LEVEL 4) | 18, worst relative difference 6.0e-13 |
| Rows against published reference data (LEVEL 3) | 10, worst 3.2e-5 (the IEC 60751 recitation check) |
| Rows against mathematics written in this round (LEVEL 5) | 112, worst 2.8e-7 |
| Construction mutations | 5 of 5 detectable ones detected; 2 blind ones blind exactly as predicted |
| Harness fault injections | 6 of 6 caught; control clean |
| Gates | 11 of 11 PASS |
| Core digest | unchanged; no file under `src/` or `tests/` was modified |

### The strongest single result

Against **ngspice 42**, run as a separate process on a netlist emitted from the
raw fixture by a module that imports neither engcore nor either adapter, every
node voltage in five circuits agrees with engcore to **6.0e-13 relative or
better**. The preregistered tolerance was 2e-6.

Getting there required correcting something about the *oracle*, not the Core.
On ngspice's default output format the agreement sat at 1.06e-6 — just inside
the tolerance, and easy to report as "agrees". It does not: ngspice's default
`print` carries six decimal places, so on a two-volt node that 1e-6 *is the
printf*, not a difference between two solvers. Tightening ngspice's Newton
tolerances changed nothing at all, which ruled out its stopping rule. Raising
its printed precision to twelve significant figures moved the agreement by a
factor of 1.7 million. The preregistered number was not changed; what changed
is that the comparison now measures the solvers.

The plan's stated *justification* for that tolerance — "ngspice prints seven
significant figures" — was wrong, and is corrected in `ERROR_SHAPE.json` rather
than quietly restated.

### The most important result

**IPM-7.** The same simulator, on the same circuit, reaches opposite
conclusions depending only on where its problem came from.

A thousandfold fault was planted in the problem construction: the fixture's
kilohms read as ohms. Two netlists were then produced for that same circuit.

| netlist emitted from | ngspice vs the Core | fault visible? |
|---|---|---|
| the raw fixture | 99.9% apart | **yes** |
| the engcore declaration | 1.1e-8 apart | **no** |

A netlist generated from the Core's own declaration inherits the Core's
construction faults and can only ever confirm them. This is the reason
`reference/spice.py` reads `fixtures/circuits.json` and refuses to accept an
engcore object, and it is now evidenced rather than asserted.

The circuit for this test is deliberately current-driven. In a resistive
divider every node voltage depends only on the *ratio* of the resistances, so
scaling them all by a thousand changes nothing and neither netlist could have
seen it — the first attempt at this mutation used a divider and proved nothing.

### The blindness this round was built to remove, demonstrated

**IPM-6.** A lumped body's conductance `hA` was derived once — wrongly, with
the cm²→m² factor omitted — and handed to *both* branches. Both solvers then
agreed to round-off about a body whose conductance was out by a factor of
10,000. The undetected temperature error was **53.1 K**.

Nothing in any comparison can see a fault in a number that neither branch
computed. That is precisely why the fixtures in this round carry a film
coefficient and an area rather than a conductance, and why `C = m c_p`,
`hA = h A`, `alpha = k/(rho c_p)`, `R_ref = rho L / A` and
`beta = -dH/(rho c_p)` are each written out twice.

### Question A answered on its own

Before any solver output was compared, every physical quantity was traced from
the fixture into the engcore declaration and compared against what adapter B
computed independently. 153 fields: **129 bit-identical, 24 agreeing to
unit-conversion round-off, none altered, none lost, none ambiguous.**

The fixtures are deliberately not in SI. The unit chain actually exercised:
mAh, mV, mOhm, mA, kΩ, mW, minutes, L, L/min, mol/L, g/cm³, J/g/K, kJ/mol,
kJ/min/K, nΩ·m, mm, mm², cm², ppm/K, °C, K/W. A fixture already written in
joules per kelvin would have tested no unit handling at all, which is most of
what a caller depends on.

### Question B answered where evidence exists, and refused where it does not

| Evidence available | Models | Result |
|---|---|---|
| `YES` — ngspice or IEC 60751 bears on the model | 5 | agrees |
| `PARTIAL` — the law is externally attested, no external number at this operating point | 2 | consistent |
| `NO` — no external evidence exists here | 9 | `EMPIRICAL_EVIDENCE_NOT_ESTABLISHED` |

Nine of sixteen is the honest number. Writing `YES` because a model agrees with
mathematics written in this round would be exactly the confusion the round was
set up to avoid.

---

## The external evidence, itemised

### ngspice 42 — LEVEL 4

An independently written circuit simulator, three decades old, invoked as a
separate process. Its problem statement comes from the raw fixture through
`reference/spice.py`, which carries its own kΩ and mV factors. 18 node-voltage
comparisons across five circuits, including one whose reference node is neither
first in the list nor named `gnd` and whose only voltage source has neither leg
on it. Worst disagreement 6.0e-13.

### IEC 60751 platinum — LEVEL 3

The linear TCR model is the first-order truncation of the standard's
Callendar-Van Dusen quadratic. Requiring it to reproduce the quadratic would be
testing a claim the record does not make. What *is* required, and was
preregistered before any comparison ran, is that its deviation equal the
omitted term `|B| t² / (1 + A t)` to within 5 percent, at eight temperatures
from 50 °C to 400 °C.

Worst result: **3.74 percent**, at the top of the range. The deviation itself
grows by a factor of 31 across that range, so this is not one coincidence — it
is the same functional form tracked across a factor of thirty. And the residual
is itself explained: once divided by the next term of the same expansion it is
constant to 3.6 percent.

The coefficients are **recited** from the published standard, not retrieved
from a licensed copy — no host serving one is reachable under this
environment's network policy. `EVIDENCE_PROVENANCE.json` says so in those
words. They are cross-validated against the standard's own published ratio
W(100) = 1.3851: recomputed from the recited A and B it is 1.385055, agreeing
to 3.25e-5, inside the 3.61e-5 that half of the last printed digit of a
five-figure number allows. A one-unit transcription error in A or B would move
this by more than that. It is a consistency check on the recitation and **not a
substitute for the document**, and the artifact states that too.

The comparison table stops at 400 °C rather than the standard's 850 °C. The
reason is the tolerance's own algebra, not the Core: `|B|t²/(1+At)` is itself an
approximation to the exact truncation error, and past roughly 400 °C the two
diverge by more than the preregistered 5 percent. At 850 °C the prediction is
10.7 percent light. The bound was set from that arithmetic before any Core
result was produced.

### CODATA 2022 — LEVEL 3

The molar gas constant, from a hashed local copy of scipy 1.17.1's constants
table (`sha256 005317bc…`, 202,549 bytes, identified in the file as CODATA
2022). The Core stores 8.314462618; CODATA gives 8.31446261815324. The
truncation is **1.84e-11 relative**, inside the preregistered 1e-9.

scipy's *constants* are used; scipy's *solvers* are not, and cannot be —
`scipy.linalg.solve`, `scipy.integrate.solve_ivp`, `scipy.optimize.brentq` and
`scipy.sparse.linalg` are all reachable from the Core, so the reference branch
is barred from them. `numpy.linalg.solve` is barred too: it dispatches to the
same LAPACK driver.

### What is not here

**No LEVEL 1 measurement and no LEVEL 2 benchmark dataset.** There is no
measured cooling curve, no measured discharge dataset, no measured concentration
trajectory. `nist.gov` returns 403 through this environment's proxy. No number
in this round is labelled a measurement, and none was invented to fill a column.

---

## Independence, established rather than asserted

`INDEPENDENCE_GRAPH.json` walks the import graph of every module the reference
branch reaches.

| branch | modules in closure | engcore modules reached | verdict |
|---|---|---|---|
| branch A (engcore) | 71 | 62 | PARTIALLY_INDEPENDENT — it *is* the Core |
| branch B (reference) | 2 | 0 | FULLY_INDEPENDENT_AFTER_RAW_FIXTURE |
| reference numerics | 2 | 0 | FULLY_INDEPENDENT_AFTER_RAW_FIXTURE |
| reference linear algebra | 2 | 0 | FULLY_INDEPENDENT_AFTER_RAW_FIXTURE |
| ngspice problem statement | 1 | 0 | FULLY_INDEPENDENT_AFTER_RAW_FIXTURE |

A tracer that reports "no dependency found" is worth nothing until it has been
shown to find one. The previous round's tracer had an off-by-one in its
relative-import arithmetic that returned a closure of size one for every
module, which made everything look independent of everything. So this one
carries a self-check: branch A reaches engcore through imports written *inside
function bodies*, and the tracer must find all 62 of them before its silence
about branch B is believed. It does.

### What is shared, and why it has to be

Three things, each stated rather than left out:

1. **The raw fixture files.** Unavoidable: the two branches must be given the
   same physical problem or they are not comparable. What is shared is a
   statement of the physics, carrying no derived quantity and no engcore type.
2. **The modified nodal analysis *formulation* for DC.** It is the formulation
   the field uses, and ngspice uses it too. Not shared: the matrix assembly,
   the ordering of unknowns, the linear solver, and the unit conversion. This
   is a real limit on the DC independence claim and is recorded as one.
3. **`math.exp` and `math.sin`.** They encode nobody's physics.

---

## Is the error the right *shape*, or merely the right size once?

A single comparison inside a tolerance says the answer was close at one
operating point. `ERROR_SHAPE.json` sweeps.

**The slab.** Backward Euler in time, central differences in space. The
predicted relative error is `λ²t·dt/2 + λt(π dx/L)²/12`, derived from the two
schemes. Refining dt at fixed dx and then dx at fixed dt, across ten grids,
the ratio of observed to predicted error stays in **[1.0006, 1.0180]** against
a preregistered band of [0.5, 1.5].

Observed orders, with the *other* variable's error floor subtracted first:

- spatial: 2.018, 2.004, 1.997, 1.985 (expected 2)
- temporal: 1.004, 1.002, 1.001, 1.000 (expected 1)

Subtracting the floor matters: the previous round read a clean second-order
scheme as order 1.61 because a constant first-order time error was still
sitting in the ladder.

A third route, an explicit forward-time centred-space march at r = 1/4, was
also checked against its *own* predicted error before being used as a reference
for anything: ratio **1.000002**. Its time error carries the opposite sign to
the implicit scheme's, so the two marches are compared through the difference
their schemes predict — ratio 1.0010 — rather than through a bound that would
have had to be padded.

**The DC solves.** The disagreements track `κ·ε` and nothing else: at worst
0.0007 of the round-off expectation, on systems with condition numbers from 10.7
to 5,289.

---

## Falsifying the harness

A comparison that reports agreement is worth nothing until it has been shown to
report disagreement. Six faults were injected into what the Core hands back —
the Core itself is never modified — and the ordinary comparison re-run over the
ordinary metrics and the preregistered tolerances.

| | injection | rows | caught |
|---|---|---|---|
| F-0 | control, nothing injected | 136 | 0 disagreements — clean |
| F-1 | every temperature biased +5% | 5 | 5 |
| F-2 | resistance-temperature slope 2% too steep | 9 | 8 |
| F-3 | one circuit of five shifted by 1 ppm | 103 | 4 |
| F-4 | every battery value ×1000 | 9 | 9 |
| F-5 | reactor integrated 1% past the end time | 5 | 3 |
| F-6 | every resistor current's sign inverted | 103 | 17 |

The rows that survive each injection are stated rather than hidden behind a
total. F-2 leaves the recitation cross-check agreeing, because that row does not
involve the Core. F-5 leaves two rows agreeing — the invariant-ceiling
inequality and the gas-constant comparison — neither of which depends on the end
time. Those are correct behaviour, not blind spots.

F-4 is the reason one row in this round exists in the form it does. The Peukert
invariant check originally survived a thousandfold scaling, because it compared
the reference branch's own capacity against the reference branch's own product
and never touched the Core at all. Finding that took an injection; it would not
have shown up in any amount of agreement.

---

## The report checked against the artifacts

`CONSISTENCY_AUDIT.json` reads every artifact in this directory and the report
that quotes them, and checks nineteen quoted numbers **in context** — each value
has to appear within a window that also matches the thing it describes, because
a checker that only asked whether the digit `9` occurred somewhere would pass
almost anything. It also scans the prose for five specific forms of reasoning
this round is not allowed to use, among them calling agreement with its own
mathematics empirical, and calling an external solver independent without saying
where its problem statement came from.

It refuses to return `CONSISTENT` until it has first demonstrated that it can
fail: one digit in this report is changed in memory, and the checker must notice.
It does. **0 inconsistencies, 0 forbidden patterns, checker verified falsifiable.**

---

## Out of sample

`fixtures/holdout.json` was written at the same time as the primary fixtures
and not looked at until fixtures, adapters, metrics and tolerances were frozen
and the primary set had run clean. **47 rows, 0 disagreements, no tolerance and
no fixture touched.**

Nothing in this round is calibrated, so there is no train/test split to protect.
The holdout guards a different failure: a harness quietly shaped by the one case
it was developed against. Agreement here is out-of-sample for the *harness*, not
for any model, and is reported as that.

Regimes only the holdout reaches: a body heated from *below* ambient through
several time constants; a slab on a grid an order of magnitude coarser; a 1C
discharge carried past the voltage cutoff; a conductor *below* its reference
temperature, where the linear correction is negative; a network whose only
source is a voltage source with a shunt current source at the far node; a
reactor started hot and lean with a colder jacket; platinum temperatures between
the tabulated points.

**One disclosed edit.** The holdout's battery duration was corrected from 6 to
15 minutes before any holdout result was produced, because at 6 minutes the case
does not reach the cutoff its own note claimed it reached — the note and the
numbers disagreed. The correction is recorded inside `fixtures/holdout.json`
itself.

---

## Calibration and validation

**No model parameter was fitted to anything in this round.** Every comparison is
therefore validation. Every fixture value is either an independently chosen
physical quantity or a published reference coefficient recorded in
`EVIDENCE_PROVENANCE.json`. Had any value been chosen to make a comparison pass,
it would be calibration and could not appear as evidence.

Every tolerance traces to a source's precision, a derived error term, or exact
algebra. None was widened after a result was seen. Two were added after
preregistration and are flagged as such in `audit/tolerances.py` rather than
folded in with the rest:

- the IEC 60751 recitation band, 3.6e-5, derived by the printed-precision rule
  the plan had already stated for ngspice — the plan committed to the check and
  printed no number for it;
- the applicability-utilization band, 1e-12, the same exact-algebra band every
  other exact algebraic case in the plan carries.

---

## Defects found in this round

**All five were in the audit. The Core had none.**

| | what |
|---|---|
| EVA-1 | The reference KCL check applied the current source's contribution with the wrong sign, reporting normalised residuals of 2.0, 1.49 and 1.22 on the three circuits that have one. Inside the source the current runs `from → to`, so at the `from` node it *leaves*. Fixed before any verdict was recorded; residuals are now ≤ 1.1e-15. |
| EVA-2 | The cross-scheme slab comparison was written as a *bound* — the sum of the two predicted errors — and failed by 0.1%, because the leading-order prediction is itself only accurate to O(dt). Replaced with the metric the plan had already preregistered: observed difference over predicted difference, using the two schemes' oppositely signed time errors. Ratio 1.0010. |
| EVA-3 | The current-source power comparison assumed a delivered-power convention. engcore reports power *absorbed* and subtracts it to build its delivered total — consistent, and visible in `delivered -= absorbed`, but the metric key `current_source_power` does not carry the sign. The comparison now states the convention and tests under it, with an added row that recovers the declared current from the Core's own power and voltages. |
| EVA-4 | The Peukert invariant row named the Core in its `core_value` field but computed its `observed` from the reference branch alone, so it could not fail. Caught by injection F-4. Now evaluates `I^k t` at the Core's own effective capacity. |
| EVA-5 | IPM-7 was first written against a resistive divider, whose node voltages depend only on the ratio of the resistances — so a thousandfold scaling of all of them is invisible to *every* route and the mutation demonstrated nothing. Moved to a current-driven network, where node voltages are `I·R` and the scale is observable. |

**One observation about the Core, not a defect.** The DC metric keys
`source_power`, `current_source_power` and `total_source_delivered_power` use
two different sign conventions — absorbed for the first two, delivered for the
third — and only the third says so in its name. The values are correct and
mutually consistent, and the code makes the relation explicit. A reader working
from the metric key alone could get the sign wrong; this audit did, once.

---

## What this round does not establish

- **That any model is empirically validated.** Nine of sixteen have no external
  evidence at all in this environment, and the two marked PARTIAL have an
  externally attested *law* with no external number constraining it at the
  operating point used here. Only five have external evidence bearing on them
  directly.
- **That the IEC 60751 coefficients are the current edition's.** They are a
  recitation, cross-validated against a ratio from the same recitation. That is
  a consistency check, not a document.
- **That the models are right about the physical world.** An affine open-circuit
  voltage curve is the Core's declared model of a cell; a measured cell would
  falsify the *cell*, not the implementation. This round validates that engcore
  solves the problem it was given, correctly, in the units it was given.
- **That DC independence is total.** The reference solve shares the modified
  nodal analysis formulation with the Core, as does ngspice. The assembly,
  unknown ordering, linear solver and unit conversion are independent; the
  formulation is not.
- **That agreement here says anything about a fault reaching both branches
  pre-derived.** IPM-6 puts a number on exactly how blind that is: 53.1 K.

---

## Reproducing

```
PYTHONPATH=benchmarks/empirical_validation .venv/bin/python -m audit.build_gates
.venv/bin/python -m pytest benchmarks/empirical_validation/tests -q
```

The first rebuilds every artifact in this directory from scratch — including
`CONSISTENCY_AUDIT.json`, which checks the numbers quoted above against the
files they came from and refuses to pass unless it has first demonstrated, on a
deliberately corrupted copy of this report, that it can fail — ngspice runs
included, in about 50 seconds. The second runs 60 standing guards over the
published artifacts and over the independence properties that would silently
stop being true under a refactor.

`.venv/bin/python -m pytest tests -q -m "not expensive and not campaign"` —
3,836 passed, 3 skipped. `pytest benchmarks` across all six assurance rounds —
204 passed.

Nothing under `src/` or `tests/` was modified. The certified core digest
`82558f5b…d97d2507` is unchanged.
