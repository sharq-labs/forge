# Model-to-Measurement Validation

**Decision: EMPIRICAL VALIDATION EXPOSED MODEL MISMATCHES — HARDENING REQUIRED.**

With a coverage qualification that belongs in the same breath as the verdict:
**3 of 16 shipped models have any measured or reference-measurement evidence at
all** in this environment. The mismatch is real, measured, replicated on a
second cell and corroborated by a second experiment on ten more — and it sits
inside a regime none of the model's own validity conditions excludes. That is
what makes it a hardening item rather than a curiosity. But nobody should read
this verdict as a statement about the other thirteen models, which were not
tested against measurement because there was nothing to test them against.

---

## 1. What this round asked

Not "does the arithmetic agree with itself" — round 5 answered that. Not "does
the Core solve the problem it was given" — round 6 answered that. This round
asked the one question neither could: **where credible measured evidence
exists, does the model reproduce it inside its claimed regime and inside a
tolerance fixed before anyone looked?**

---

## 2. Model coverage

| Model | Evidence level | Calibration | Validation | Held-out | Result |
|---|---|---|---|---|---|
| battery.cell.rint_ocv | LEVEL 2 | 9 | 0 | 46 | **EMPIRICAL_PARTIAL** |
| electrical.material.linear_tcr_resistance | LEVEL 3 | 1 | 371 | 679 | **EMPIRICAL_PARTIAL** |
| electrical.material.rated_linear_tcr_resistance | LEVEL 3 (law only) | — | — | — | **EMPIRICAL_PARTIAL** |
| electrical.dc.kcl | LEVEL 4 (prior round) | — | — | — | REFERENCE_VALIDATED_ONLY |
| electrical.dc.resistor_ohm | LEVEL 4 (prior round) | — | — | — | REFERENCE_VALIDATED_ONLY |
| electrical.dc.ideal_voltage_source | LEVEL 4 (prior round) | — | — | — | REFERENCE_VALIDATED_ONLY |
| electrical.dc.ideal_current_source | LEVEL 4 (prior round) | — | — | — | REFERENCE_VALIDATED_ONLY |
| electrical.dc.regulated_voltage_source | LEVEL 4 (prior round) | — | — | — | REFERENCE_VALIDATED_ONLY |
| electrical.dc.self_heated_resistor | LEVEL 4 (prior round) | — | — | — | REFERENCE_VALIDATED_ONLY |
| thermal.lumped.first_order_capacity | none | — | — | — | EMPIRICAL_EVIDENCE_NOT_ESTABLISHED |
| thermal.conduction1d.linear_diffusion | none | — | — | — | EMPIRICAL_EVIDENCE_NOT_ESTABLISHED |
| battery.cell.coulomb_counting | none usable | — | — | — | EMPIRICAL_EVIDENCE_NOT_ESTABLISHED |
| battery.cell.constant_current_runtime | none usable | — | — | — | EMPIRICAL_EVIDENCE_NOT_ESTABLISHED |
| battery.cell.peukert_capacity_derating | none usable | — | — | — | EMPIRICAL_EVIDENCE_NOT_ESTABLISHED |
| kinetics.cstr.nonisothermal_first_order | none | — | — | — | EMPIRICAL_EVIDENCE_NOT_ESTABLISHED |
| kinetics.cstr.nonisothermal_first_order_constant_rate | none | — | — | — | EMPIRICAL_EVIDENCE_NOT_ESTABLISHED |

**3 partial, 6 reference-only, 7 with no empirical evidence established, 0
empirically validated within scope, 0 model-level mismatches.**

Zero in the strongest column is the honest outcome. `battery.cell.rint_ocv`
would have earned it on the strength of case MV-B alone; it does not, because
the same model on the same measurement fails in its other configuration.

---

## 3. Evidence provenance

Outbound access here reaches **two hosts**: `raw.githubusercontent.com` and
PyPI. NIST, DOI resolution, Zenodo, arXiv, OSTI and the standards publishers —
including IEC's own sample PDF of 60751 — are all blocked by the egress proxy,
by `curl` and by the fetch tool alike. Each was probed and the result recorded
rather than assumed.

**Accepted, and used:**

| ID | What | Level | Provenance |
|---|---|---|---|
| **S-OCV** | 24-hour open-circuit-voltage relaxation, 8 cells, 6 chemistries, 30 traces | **LEVEL 2** | DOI 10.21227/651q-8v82 · Voicilă, Enache, Vîlciu, Serițan · POLITEHNICA Bucharest · CC BY 4.0 · companion paper in *Batteries* 11(5) 186 |
| **S-DCHG** | Constant-current discharge curves, 10 LiFePO4 cells, 30 curves, 1 s sampling | **LEVEL 2** | DOI 10.21227/cm0f-jg66 · same laboratory · CC BY 4.0 |
| **S-PT100** | 1051-point platinum resistance table, −200 to +850 °C | **LEVEL 3** | DIN 43760 / IEC 751 relation, transcribed in `drhaney/pt100rtd` |
| **S-CODATA** | Molar gas constant | LEVEL 3 | scipy 1.17.1 CODATA 2022 table, carried from round 6 — **used for nothing** |

Every file is hashed in `EVIDENCE_PROVENANCE.json` and re-hashed by a standing
test. S-CODATA appears with an empty `used_for` on purpose: it fixes a constant
the CSTR model is *handed*. Counting it as evidence for the reactor would be
counting evidence for an input as evidence for the model.

**Searched and rejected, with reasons:** an unattributed CSTR saponification
experiment (no author, no date, no uncertainty, raw data in an undocumented
binary); PyBaMM's half-cell electrode potentials (they describe a different
model); PyBaMM's "example" equivalent-circuit tables (no provenance at all);
teaching-repository cooling curves (both lumped parameters would have to be
fitted from the data meant to validate them); ngspice (a solver, not a
measurement); and every blocked host.

---

## 4. Calibration and validation

**10 calibration rows, 371 validation rows, 725 held-out rows. No leakage.**

Every parameter handed to the Core is listed in `CALIBRATION_SPLITS.json` with
where its value came from. The design that matters is MV-A's: the affine chord
has exactly two degrees of freedom, both are consumed by two measured
endpoints, and **zero free parameters remain**. Every interior state of charge
is then an out-of-sample prediction of a model with nothing left to adjust.

Calibration rows carry no verdict. Their residual is zero by construction — the
point *is* the parameter — and letting them read as passes would put free wins
into every summary. A standing test enforces it.

---

## 5. Metrics, tolerances and uncertainty

Four cases, all fixed in `METRIC_PLAN.json` before any comparison ran. Every
pass rule is stated against the **expanded (k = 2) measurement uncertainty**,
assembled in `audit/evidence.py` from the instruments the datasets publish plus
one term measured from the data.

The budget follows the chemistry rather than assuming one number. An error in
state of charge is not an error in voltage until it is multiplied by how fast
the voltage moves with state of charge there, so the local slope is taken from
the neighbouring measured points. On a LiFePO4 plateau the term nearly
vanishes; at the ends it is an order of magnitude larger. The result is a
per-point uncertainty running from **0.8 mV to 8.4 mV**.

Residual relaxation is measured, not assumed zero: the worst trace was still
moving at **1.7 mV/hour** when it was stopped, and that enters its own point's
budget.

---

## 6. What the measurements said

### MVF-1 — the affine chord misses measured open-circuit voltage

Declared endpoints from the measurement itself: 2.8473 V at 0 % SOC,
3.3890 V at 100 %. Ten held-out states of charge:

| | MAE | RMSE | max | bias | inside uncertainty | worst / its own U |
|---|---|---|---|---|---|---|
| APR (BATT_001) | 175.3 mV | 194.2 mV | **293.4 mV** | −175.3 mV | **0 of 10** | **217×** |
| BSE (BATT_002), replicate | 108.6 mV | 110.0 mV | 129.5 mV | −108.6 mV | 0 of 4 | 151× |

Against a measurement uncertainty of a few millivolts. Every residual carries
the same sign and falls monotonically from the bottom of the range to the top:
**structure, not scatter**.

MV-18 alternatives, ruled out in writing: not a unit error (the residual is
exactly zero at 100 % and grows smoothly downward — a scale error moves every
point together); not a parameter error (there were only two parameters and both
came from the measurement); no initial or boundary condition exists in a
resting cell; not dataset interpretation (SOC is set by the experiment's own
conditioning, and the read point is pinned by an integrity check); not
measurement uncertainty (two orders of magnitude too small); no numerical error
in one algebraic expression.

**Second, independent line of evidence** — MV-D. Under a constant current the
chord model *forces* the terminal voltage to be affine in time. The
least-squares straight line is therefore the best any chord configuration could
achieve, for any endpoints, capacity, efficiency or resistance. Across **30
measured discharges of 10 different cells** from a separate dataset with its
own DOI, the departure from that best line is **65 to 172 mV RMS**, worst
excursion 1.18 V. That is a parameter-free lower bound, and it needs no
knowledge of the discharge current — which this dataset does not record.

**Is the model family inadequate? No — and that is the finding's most important
qualification.** The record's own text says the chord governs *"unless the cell
declares a curve for it, in which case the curve governs"*. Case MV-B exercises
that route on the same cell and passes. The family is adequate; its **default
configuration** is not adequate for this chemistry.

### MVF-2 — nothing would have warned the caller

`battery.cell.rint_ocv` carries eleven validity conditions: C-rate, SOC window,
temperature, resistance drift, self-heating, polarization, terminal voltage.
**Not one bears on whether the affine chord describes the cell.** A caller may
declare a chord for a cell whose measured curve departs from it by 293 mV and
receive no signal at all.

What the evidence supports is that such a condition would have something to act
on. What it does not settle is what the condition should be: a bound on the
chord residual needs a measured curve to compute against, which is exactly what
a caller who declared a chord does not have. That is a design question for
whoever owns the battery domain, and it is recorded as one rather than
legislated here. **No production code was changed.**

### The declared-curve route passes

Five measured samples as the curve, two held out:

| SOC | measured | Core | residual | tolerance | |
|---|---|---|---|---|---|
| 0.4 | 3.2990 V | 3.2823 V | −16.7 mV | 85.0 mV | pass |
| 0.6 | 3.3020 V | 3.3103 V | +8.3 mV | 9.7 mV | pass |

Both inside the preregistered rule. Stated precisely: **a five-sample declared
curve reproduces held-out measured open-circuit voltage to about 1 part in 200
of the cell's voltage, not to measurement precision** — the residuals are 7.7×
and 3.4× the measurement uncertainty. The tolerance at SOC 0.4 is loose because
the interpolation bound is driven by the sharp knee near the bottom of the
range, and `METRIC_PLAN.json` predicted that weakness before the case ran.

### Hysteresis, an excluded effect, measured

The model excludes hysteresis. Charge- and discharge-conditioned open-circuit
voltages at the same state of charge differ by **at most 9.6 mV**. Reported
rather than folded into the residual: a model that says it does not represent
an effect should be told how big that effect was.

### MVF-3 / MVF-4 — the platinum comparison

The linear law against the 1051-point reference table. The preregistered rule —
deviation must equal the omitted quadratic term to within 5 % — **fails at 6 of
371 scored entries, all between 30 and 48 °C**.

The cause is not the model. `METRIC_PLAN.json` set the scored interval's lower
bound at 30 °C from the table's *stated* ±0.005 Ω quantisation. The table's
*measured* scatter against any quadratic is **0.0154 Ω, 3.1× that**, and at
30 °C that is 29 % of the term being tested. The rule and its result stand
unedited, as the plan requires; a labelled secondary analysis reports the same
5 % rule from 50 °C upward, where **all 351 entries pass** at a worst metric of
0.0463.

The reference data's scatter is itself a finding (MVF-4). No Callendar–Van
Dusen pair reproduces the table to its stated resolution — the pre-1995 DIN
43760 pair is ruled out at 0.22 Ω.

**What the scatter does not undermine is the coefficients.** Fitting A and B to
the table returns **3.908276e-3** and **−5.775048e-7**, against the previous
round's independently recited 3.9083e-3 and −5.775e-7: agreement to **6 and 8
parts per million**. Two artifacts that never saw each other corroborate the
pair.

**The strongest positive result in the round** is the residual's shape. A linear
law compared against a quadratic reference must leave a quadratic residual of
exactly |B|·R₀ = 5.775e-5 Ω/°C². The least-squares curvature of the 371 scored
residuals is **5.7765e-5** — four significant figures. The model drops exactly
the term the algebra says it drops.

And the measured applicability boundary, which is what a user actually needs:

| the linear law stays within | over |
|---|---|
| 0.005 Ω (the table's quantisation) | −10 … +6 °C |
| 0.1 Ω (0.26 °C equivalent) | −41 … +41 °C |
| 1.0 Ω (2.6 °C equivalent) | −120 … +131 °C |

### MVF-5 — three battery models, one missing column

`S-DCHG` has exactly the shape `coulomb_counting`, `constant_current_runtime`
and `peukert_capacity_derating` need: three constant-current rates, ten cells,
cutoff times, documented instruments. It **does not record the discharge
current**. Its labels read as 1C, C/2 and C/3; its durations are 1.0 h, 4.0 h
and 8.8 h, contradicting that by more than a factor of two.

Deriving the currents from the durations and the nominal capacity was refused.
The delivered capacity at each rate is *precisely what Peukert's law predicts*,
so using it as an input would be assuming the answer, and the resulting
agreement would be arithmetic dressed as evidence.

---

## 7. Residual shape

All four cases show systematic structure, and each is accounted for:

- **MV-A / MV-A-replicate** — the finding itself; MVF-1 says so.
- **MV-C** — expected and *required*. A residual with no structure here would
  mean the omitted term was not what the algebra says it is.
- **MV-D** — departures from a straight line are magnitudes and cannot change
  sign; the drift with discharge duration is reported instead.

No case shows structure that no finding accounts for. That is gate MV-8.

---

## 8. Falsifying the auditor

Eight controlled failures planted in what the Core returns or in the result
set's own bookkeeping. **8 caught, 0 missed.** Nothing under `src/` was touched.

| | plant | caught by |
|---|---|---|
| MVM-1 | +5 % systematic bias on every open-circuit voltage | residual leaves tolerance |
| MVM-2 | slope 2 % too steep, exact at the reference point | the ratio metric, 6 → 371 failures |
| MVM-3 | every voltage ×1000 | residual leaves tolerance |
| MVM-4 | relaxed value read at 1 h instead of 24 h | the read-point check, 0 → 19 offences |
| MVM-5 | a calibration point duplicated into the held-out set | the leakage check |
| MVM-6 | measurement uncertainty set to zero | refused outright |
| MVM-7 | an out-of-scope row relabelled as validation | the applicability check |
| MVM-8 | a failing held-out point relabelled as calibration | the split check |

**MVM-5, MVM-7 and MVM-8 change no residual at all.** They are the reason
`audit/integrity.py` exists, and they are the faults a validation round is most
likely to commit without noticing.

---

## 9. Gates

| | | |
|---|---|---|
| MV-1 | MODEL SURFACE COMPLETE | PASS |
| MV-2 | SOURCE PROVENANCE | PASS |
| MV-3 | APPLICABILITY | PASS |
| MV-4 | CALIBRATION INDEPENDENCE | PASS |
| MV-5 | METRIC VALIDITY | PASS |
| MV-6 | UNCERTAINTY HONESTY | PASS |
| **MV-7** | **EMPIRICAL AGREEMENT** | **FAIL** |
| MV-8 | RESIDUAL SHAPE | PASS |
| MV-9 | AUDITOR FALSIFICATION | PASS |
| MV-10 | PREVIOUS ASSURANCE PRESERVED | PASS |
| MV-11 | FROZEN EVIDENCE PRESERVED | PASS |

**10 of 11 gates passed.** MV-7 is expected to fail and failing it *is* the
round's result: MVF-1 stands, inside a regime the model does not exclude. A
gate that passed by reclassifying a measured mismatch as out of scope would be
worth nothing.

MV-4 passes with one declared discrepancy: the split check reports every
difference from the preregistered counts, and the one-row difference at MV-C is
allowed through only because finding MVF-7 names it. Nothing passes because it
is small.

---

## 10. Audit mistakes

Five, all mine, all found by running the machinery rather than by reading it.

| | what |
|---|---|
| **MVF-7** | `VALIDATION_SPLIT.json` counts the 0 °C table entry twice — once as MV-C's calibration row and once inside the held-out range — giving 680 held-out and a total of 1052 for a 1051-entry table. The preregistered file is left as committed; the integrity check reports the one-row discrepancy every run and gate MV-4 passes it only because a finding names it. |
| **MVF-3** | The MV-C scored interval was derived from the reference table's *stated* precision before the table had been parsed. Its measured scatter is 3.1× larger. Rule preserved, result preserved, secondary analysis labelled. |
| **MVF-8a** | The falsification harness compared a single-case plant against a whole-round baseline and reported four spurious misses. |
| **MVF-8b** | Its first time-shift plant stretched the discharge time axis — which leaves the residual of a straight-line fit *exactly* unchanged and could never have been caught. Replaced with the fault an extraction actually makes. |
| **MVF-8c** | The platinum table parser read 1069 and then 1054 entries for a 1051-entry table: it ran past the array terminator, then swallowed the digits of a trailing comment. It now refuses any length but 1051. |

One more, caught before it reached a verdict: MV-A's calibration rows initially
carried `within_tolerance: true`, because their residual is zero by
construction. Two free passes in a summary of ten points.

---

## 11. Models without empirical evidence

Seven, named with the reason rather than left blank:

- **thermal.lumped.first_order_capacity** — no measured transient with
  independently known C and hA. A bare temperature–time series would force both
  parameters to be fitted from the data meant to validate them.
- **thermal.conduction1d.linear_diffusion** — and the harder obstacle is that
  the quantity it predicts, the decay of an exactly half-sine initial profile,
  is not one an experiment produces.
- **battery.cell.coulomb_counting**, **constant_current_runtime**,
  **peukert_capacity_derating** — MVF-5, the missing current column.
- **kinetics.cstr.nonisothermal_first_order** — the one measured reactor
  experiment found was rejected at the provenance lock.
- **kinetics.cstr.nonisothermal_first_order_constant_rate** — declared in the
  repository as a comparison approximation, not a claim about a physical system.
  There is nothing external for it to be right or wrong about.

The six `electrical.dc` models are separate: they have LEVEL 4 evidence from
round 6 at 6e-13, and no physical measurement. Reading ngspice output and
calling it a measurement is the move this round's consistency audit rejects by
name.

---

## 12. Previous assurance

Certified core digest `82558f5b…d97d2507` — **unchanged**. No file under `src/`
or `tests/` modified. No earlier round's artifacts touched; round 6's
`scipy_codata.py` is read for the provenance record and nothing else.

`pytest tests` — 3,836 passed, 3 skipped. The seven benchmark guard suites
collect 237 tests between them and pass together; 33 of those are this round's,
34 with the full rebuild included.

---

## 13. Remaining limitations

- **Coverage is 3 of 16.** Everything above concerns a battery open-circuit
  curve and a platinum resistance relation. It says nothing measured about
  thermal, kinetics or DC.
- **No LEVEL 1 evidence is claimed.** Both battery datasets are raw
  measurement, which would argue for LEVEL 1, but this audit neither performed
  nor witnessed the experiments and reaches them as published records. LEVEL 2
  is the conservative reading and is the one used.
- **S-PT100 is a transcription**, not the licensed standard, and a standardised
  relation rather than a measurement of a specimen. It is corroborated two ways
  and it is still not the document.
- **Two cells, one chemistry.** MVF-1 is established for LiFePO4. A chemistry
  with a more nearly affine curve would show a smaller departure, and this round
  has no measurement of one.
- **MVF-2 is unresolved by design.** What an applicability condition for the
  chord should be is a domain decision, and this round deliberately did not
  make it.

---

## 14. The exact validation claim

> Against 24-hour relaxed open-circuit-voltage measurements of two LiFePO4
> cells (DOI 10.21227/651q-8v82, CC BY 4.0), `battery.cell.rint_ocv` configured
> with a **declared measured curve** reproduces both held-out states of charge
> inside a tolerance of the expanded measurement uncertainty plus the declared
> interpolation error, with residuals of 8 and 17 mV. Configured with its
> **default affine chord** and both endpoints taken from the same measurement,
> it misses all ten held-out states of charge by a mean of 175 mV and a maximum
> of 293 mV — 217 times the expanded uncertainty of the worst point — with a
> systematic, single-signed, monotone residual; replicated on a second cell and
> bounded below independently by 30 constant-current discharges of ten further
> cells (DOI 10.21227/cm0f-jg66). No validity condition of that model bears on
> which configuration is appropriate.
>
> Against the 1051-point DIN 43760 / IEC 751 platinum resistance relation,
> `electrical.material.linear_tcr_resistance` deviates by exactly the quadratic
> term it omits: the residual's fitted curvature is 5.7765e-5 Ω/°C² against the
> 5.775e-5 the algebra requires. The preregistered 5 % rule fails at 6 of 371
> scored entries, all below 48 °C, where the reference table's own 0.0154 Ω
> scatter exceeds the quantity being measured; from 50 °C upward all 351
> entries pass.
>
> **No other shipped model was compared against any measurement, because no
> credible measured evidence for the quantity it predicts was reachable from
> this environment.**

---

## 15. Reproducing

```
PYTHONPATH=benchmarks/model_measurement_validation .venv/bin/python -m audit.build_gates
.venv/bin/python -m pytest benchmarks/model_measurement_validation/tests -q
```
