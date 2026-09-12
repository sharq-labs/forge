# Calibration, UQ & Held-Out Validation — Sprint 8

> **VERDICT: CALIBRATION & UQ HARDENING COMPLETE.** §1 states it and §16
> states what it does not cover.

---

## 2. Existing inference / UQ — the reuse table

The instruction was to inspect before adding, and not to create competing
abstractions. Inspecting first changed the shape of this round substantially:
**most of the pipeline Sprint 8 asks for is already built**, guarded, and
certified. What is missing is narrower and more specific than the phase list
implies.

The pipeline that already exists, end to end:

```
ObservationSet(dataset_id)                     inference/grid.py
    ↓  forward solves
AdmissibleNumericalPrediction                  inference/admissibility.py
    ↓  require_admissible_numerical_prediction
AdmittedForwardRow  →  AdmittedForwardTable    inference/grid.py
    ↓  gaussian_grid_posterior
PosteriorGrid(dataset_id)                      inference/grid.py
    ↓  posterior_predictive_uq
QuantifiedPredictiveResult                     uq/predictive.py
    ↓  assess_predictive_observation
PredictiveObservationAssessment                adequacy/predictive.py
    ↓  compare_log_predictive_scores
ModelScoreComparison                           adequacy/predictive.py
```

| Capability (phase) | Existing? | Where | Reuse / Extend / Missing |
|---|---|---|---|
| Observation with declared σ and units (7) | **yes** | `inference/grid.py` `GaussianObservation` | **reuse** — σ>0, unit-compatibility with the value, and a `condition_id:observable_name` key all enforced at construction |
| Dataset identity (4) | **yes** | `ObservationSet.dataset_id`, `.subset(..., dataset_id=)` | **reuse** — duplicate observation keys already refused |
| Calibration ⇄ held-out **overlap** refusal (4, 17) | **no** | — | **MISSING** — `subset` can produce two sets sharing an observation and nothing objects |
| Numerical-admissibility boundary (8) | **yes** | `inference/admissibility.py` | **reuse** — refuses `ScientificResult` directly; demands sequence-level `NUMERICALLY_CONVERGED` |
| Forward evaluation integrity (8) | **yes** | `AdmittedForwardRow` | **reuse** — no field-level constructor; every admitted value carries its admission ref |
| Likelihood / objective (7) | **yes** | `gaussian_grid_posterior` | **reuse** — exact discrete posterior, residuals formed in the observation's own unit |
| Calibration method (9) | **yes** | `gaussian_grid_posterior` + `PosteriorGrid.map_point` | **reuse** — one method, already the "smallest robust route" the phase asks for |
| Parameter **identity** (6) | **no** | `parameter_names: tuple[str, ...]` | **MISSING** — parameters are bare display strings. No unit, no bounds, no model association. This is the single largest gap |
| Parameter uncertainty (12) | **yes** | `PosteriorGrid.covariance`, `.correlation`, `.marginal_interval` | **reuse** — full posterior, not a Laplace approximation |
| Identifiability measures (11) | **partly** | `.covariance`, `.correlation`, `summary()['covariance_determinant']` | **extend** — the numbers exist; nothing *classifies* them into identifiable / weak / none |
| Predictive uncertainty (13) | **yes** | `uq/predictive.py` `posterior_predictive_uq` | **reuse** — exact Gaussian-mixture CDF/quantiles, declared credible level |
| Uncertainty decomposition (14) | **yes** | `uq/predictive.py` | **reuse** — already separates epistemic/parameter from observation noise, and says in its own docstring that no model-discrepancy term is invented |
| Predictive admission conditioning | **yes** | `uq/admission.py` | **reuse** — declared unsupported-mass budget, fails closed above it |
| Held-out scoring (15) | **yes** | `adequacy/predictive.py` | **reuse** — exact finite Gaussian-mixture log predictive score |
| Evidence identity + tamper refusal (17, 20) | **yes** | `PredictiveEvidenceIdentity` | **reuse** — carries `heldout_dataset_id`, `posterior_dataset_id`, `twin`, observed value, σ, unit; SHA-256 digest verified on deserialization |
| Model comparison (18) | **yes** | `compare_log_predictive_scores` | **reuse** — refuses a pair whose evidence identities differ in any field |
| Sweep execution (8, 22) | **yes** | `execution/sweep.py` `run_sweep` | **reuse** — Sprint 7's engine; solver isolation, case identity, failure policy |
| Interval coverage study (16) | **no** | — | **MISSING** |
| Model-misspecification demonstration (18) | **no** | — | **MISSING** |
| Failure-semantics vocabulary (19) | **no** | — | **MISSING** |
| Seeded reproducibility (21) | **n/a so far** | — | the grid route is **deterministic**; there is no stochastic step to seed yet |
| Field observation operator (23) | **no** | — | **MISSING** |

### Two things the inventory changed

**`adequacy/` is an orphan, and says so.** Its own `__init__` states it is not
on the verification path and is imported by nothing under `src/` — its only
consumer is `tests/test_k4_model_adequacy.py`. It is nonetheless **certified**,
as the `evidence_identity` area. So it is reusable and guarded, but wiring it
into a workflow changes its status from orphan to load-bearing, and that is a
decision this round should make deliberately rather than by accident.

**Certified scope matters for what this round may touch.**

| area | paths | classification |
|---|---|---|
| `inference_admission` | `src/engcore/inference/**` | **CORE_CERTIFIED** |
| `evidence_identity` | `src/engcore/adequacy/**` | **CORE_CERTIFIED** |
| `core` | `src/engcore/scientific/**` | **CORE_CERTIFIED** |
| `uq` | `src/engcore/uq/**` | **explicitly OUT** — "representation only; it computes nothing a verdict rests on" |

Anything this round adds to `inference/` or `adequacy/` turns the certificate
red and requires a reissue (Phase 28). `uq/` does not. That is a constraint on
*where* new code goes, and it is a real one — it should not be satisfied by
putting code in `uq/` to dodge certification.

---

## 3. Flagship model

**`electrical.material.linear_tcr`** — temperature-dependent conductor
resistance.

```
R(T) = R_ref · (1 + α_TCR · (T − T_ref))
```

| | |
|---|---|
| calibrated | `reference_resistance` (**ohm**), `temperature_coefficient` (**1/kelvin**) |
| fixed | `reference_temperature` (**kelvin**) |
| declared validity | 200 K – 450 K (`TCR_MIN_TEMPERATURE`, `TCR_MAX_TEMPERATURE`) |
| observable | `resistance` (ohm) |

Chosen over battery, thermal and CSTR because it is the only candidate that
serves **four** distinct phases without contrivance:

- **Phase 26 (independent oracle).** The model is linear in `(R_ref, R_ref·α)`,
  so ordinary least squares has a closed form. The recovered parameters can be
  derived independently of the optimizer, in a few lines, rather than by
  re-running the thing under test.
- **Phase 11 (identifiability).** `R_ref` and `α` are well separated over a
  wide temperature span and strongly correlated over a narrow one, because a
  narrow span cannot distinguish the intercept from the slope. Identifiable and
  weakly-identifiable cases are then the *same model on different designs* —
  not two different models — which is the honest comparison.
- **Phase 18 (misspecification).** The model is explicitly a **linearization**
  and knows it: it carries `LINEARIZATION_BAND`, `LINEARIZATION_EXCURSION_RATIO`
  and `DEBYE_TEMPERATURE`, and the empirical round already records a "linear TCR
  truncation comparison". Generating truth with curvature and fitting the linear
  form is this model's own declared limitation, not an invented strawman.
- **Phases 5–7 (units).** Two calibrated parameters in **different units**
  (ohm, 1/kelvin), which is what makes "same label, different unit → not the
  same parameter" a test with something to bite on.

It is also cheap: a closed-form forward evaluation, so 10 000 forward
evaluations for Phase 22 cost seconds rather than hours.

**Not the 2-D PDE**, per the instruction. The field-observation spike
(Phase 23) will reach a field model through a declared observation operator
without making it the flagship.

---

## 1. FINAL VERDICT

**CALIBRATION & UQ HARDENING COMPLETE.**

The four numbers that matter, first:

### 1.1 True vs recovered parameters

| parameter | true | recovered | abs error | rel error | in standard errors |
|---|---|---|---|---|---|
| `reference_resistance` | **1.257 Ω** | **1.25964037 Ω** | 2.640e-03 | 0.21 % | **1.67 s.e.** |
| `temperature_coefficient` | **0.00393 /K** | **0.0039053371 /K** | 2.466e-05 | 0.63 % | **1.06 s.e.** |

The tolerance is **4 s.e.**, derived from the declared σ = 0.002 Ω and the
design, fixed before the run. The closed-form OLS oracle independently returns
`1.25964037` and `0.0039053371` — agreement to 1e-6 relative, by a completely
different route.

### 1.2 Identifiable vs weakly identifiable

Same model, two **designs** — the honest comparison, because two different
models would differ for reasons other than identifiability.

| | wide span (300–440 K) | narrow span (299–301.5 K) |
|---|---|---|
| verdict | **`PARAMETERS_IDENTIFIABLE`** | **`PARAMETERS_WEAKLY_IDENTIFIABLE`** |
| max \|correlation\| | 0.908 | **0.997** |
| relative 95 % width, `R_ref` | 0.0045 | 0.021 |
| relative 95 % width, `α` | **0.022** | **0.926** |
| condition number | 2.64e+04 | 1.25e+04 |
| effective sample size | 14.4 | 13.6 |
| grid step / posterior σ | 0.600 | 0.605 |

The weak case's interval for α is **93 % of α itself**. It is not reported as
precise.

### 1.3 Nominal vs measured predictive coverage

| | |
|---|---|
| nominal | **0.95** |
| measured | **0.930** |
| Wilson 95 % interval | **[0.9067, 0.9478]** |
| repetitions | **200** |
| intervals evaluated | **600** |
| verdict | **`UNCERTAINTY_CALIBRATED`** |

Stated plainly because it matters: the Wilson interval **does not contain
0.95**. Measured coverage is slightly and detectably below nominal. The verdict
is `CALIBRATED` because the pre-declared acceptance band is ±0.05 and
[0.9067, 0.9478] overlaps [0.90, 1.00] — the threshold was fixed before the
study ran and has not been moved since.

The residual ~2 points are a property of the method, not of the grid: coverage
was measured at grid steps of 0.857, 0.600, 0.400 and 0.300 σ and at a wider
span, and sat at **0.9389 every time**. A uniform prior truncated at ±6 s.e.
discards a little tail mass, which narrows intervals slightly. See §16.

### 1.4 Misspecified-model held-out result

Truth carries a **+8e-6 /K²** quadratic term the fitted linear law cannot
represent.

```
CALIBRATION_CONVERGED  +  PARAMETERS_IDENTIFIABLE  +  HELD_OUT_VALIDATION_FAIL
```

| | well-specified | misspecified |
|---|---|---|
| calibration status | `CALIBRATION_CONVERGED` | **`CALIBRATION_CONVERGED`** |
| identifiability | `PARAMETERS_IDENTIFIABLE` | **`PARAMETERS_IDENTIFIABLE`** |
| calibration objective | 2.328 | 129.9 |
| held-out verdict | `HELD_OUT_VALIDATION_PASS` | **`HELD_OUT_VALIDATION_FAIL`** |
| held-out RMSE | 0.00137 Ω | **0.02165 Ω** (15.8×) |
| held-out MAE | 0.00112 Ω | 0.01676 Ω |
| standardized residuals | −0.51, +0.05, −0.75 | **+1.33, −5.39, +13.00** |
| χ² (3 dof) | 0.820, p = 0.845 | **199.7, p = 4.8e-43** |
| interval coverage | 3/3 | **1/3** |

**The fit succeeded completely and the model is still wrong.** Nothing in the
calibration layer could have told you which had happened.

The residual **pattern** is the tell, and its shape is specific: +, −, + across
310 / 350 / 420 K. A least-squares line fitted to a quadratic does not miss in
one direction — it sits above the data mid-range and below it at both ends. The
U-shape is the classical truncation signature. That assertion was first written
as "all residuals share a sign", which is **wrong**, and the run said so.

---

## 4. Architecture — the dependency direction

```
scientific/   primitives: units, results, validation, twins, fields
    ↓
inference/    admission (numerical + analytic), observations, split,
              parameter identity, grid posterior, CALIBRATION RESULT
    ↓
uq/           posterior-predictive uncertainty
    ↓
adequacy/     held-out predictive scoring, evidence identity
    ↓
studies/      orchestration  ← NEW, and the only layer above adequacy
```

Every arrow runs one way, and two consequences were deliberate:

- **`inference.calibration` does not import `execution`.** It takes a
  caller-supplied `ForwardEvaluator`; the orchestration layer supplies one
  backed by `run_sweep`. Pulling the sweep down into a certified inference
  module to serve one caller would have inverted the direction.
- **`adequacy/` stays imported by nothing below it.** The arrow this round adds
  points **down** from `studies/` into `adequacy/`. The orphan is now reachable
  without becoming a dependency of anything it used to sit above.

Nothing was placed in `studies/` to avoid certification: parameter identity,
the split guard, the analytic admission route and the calibration result all
went into **certified** `inference/`, and each of them turned the certificate
red.

---

## 5. The analytic admission route

The flagship is closed-form, and `require_admissible_numerical_prediction`
demands `claims(NUMERICALLY_CONVERGED)` — where `ValidationReport.claims` is
**exact membership, not a ladder**. Measured, not assumed: the production TCR
solver reports `ConvergenceState.NOT_APPLICABLE` and attains exactly
`{DIMENSIONALLY_VALID}`. Its own docstring calls that "the smallest honest
level this solver can attain", and `admissibility.py`'s header had already
refused the alternative in advance — *"Future analytic inference paths need not
pretend that numerical tolerance convergence applies to them."*

So `AdmissibleAnalyticPrediction` admits on what a closed form can earn. **The
load-bearing part is what it refuses:** a prediction claiming
`NUMERICALLY_CONVERGED` is rejected outright, so the analytic route cannot
become a weaker back door for numerical results that failed the stronger bar.
The two routes are disjoint by construction, and every admitted value records
which one it crossed (`analytic|…` / `numerical|…`).

The option **not** taken: building the forward table field-level, as the
existing unit tests do. The constructor permits it and only requires an
admission-ref *string*, so the calibration would have merely *asserted* it
crossed a boundary. That is the "green result that proves nothing" this
repository exists to prevent.

---

## 6. False precision, found by walking into it

The first grid spanned ±0.25 Ω at σ = 0.002 Ω — far coarser than the
likelihood — so the entire posterior landed on **one point**: zero covariance,
correlation numerically 1.0, a 95 % credible interval of **zero width**, and
ESS = **1.0 over 1681 points**. A naive reading calls that an exquisitely
determined parameter, and the error points toward false certainty.

`assess_identifiability` now refuses such a posterior, and the refusal is
labelled `GRID_TOO_COARSE_FOR_INFERENCE` — deliberately **not** a member of
`IdentifiabilityStatus`, because it is a statement about the instrument and
putting it in the same enum would invite reading it as a scientific verdict.

**The refusal requires two conditions, and case C proves why.** A weakly
identified posterior has ESS **5.87 — below the threshold** — while its grid
step is 0.6 σ. An ESS-only rule would have refused it, told the reader to
refine a grid that is already fine, and buried a real weak-identifiability
finding behind a numerical complaint. The discriminator is **grid step relative
to posterior width**:

| | ESS | step/σ | diagnosis |
|---|---|---|---|
| A resolved | 14.4 | 0.600 | verdict: `IDENTIFIABLE` |
| B collapsed | 1.0 | **≥ 1.0** | **exception**: `GRID_TOO_COARSE_FOR_INFERENCE` |
| C weakly identified | **5.87** | 0.605 | verdict: `WEAKLY_IDENTIFIABLE` |

B and C differ in **kind**: one is refused, the other is answered.

---

## 7. Why strong correlation is still identifiable

The wide-span case is `IDENTIFIABLE` at |r| = 0.908, and the verdict says why
in its own text rather than leaving a reader to wonder whether the classifier
missed it.

**The discriminator is the marginal width, not the correlation.** Correlation
says a ridge exists; it does not say the ridge is long. Two parameters can be
strongly correlated and both still pinned to a fraction of a percent — a
well-conditioned ridge, not an unidentified one. Conversely a parameter whose
95 % interval exceeds its own value is not determined however cleanly its
posterior factorises. Correlation and conditioning are corroborating evidence
that explain the *shape*.

Classifying on correlation alone would have called the wide-span design
unidentified at |r| = 0.91 while its parameters are known to better than 2.2 %.

---

## 8. Uncertainty decomposition

Three sources, named individually in every result. At held-out condition T6:

| source | value |
|---|---|
| `PARAMETER_UNCERTAINTY` | σ = 1.257e-03 Ω, interval [1.340082, 1.344977] |
| `MEASUREMENT_UNCERTAINTY` | σ = 2.000e-03 Ω (declared) |
| total | σ = 2.362e-03 Ω, interval [1.337899, 1.347159] |
| `MODEL_DISCREPANCY_NOT_MODELLED` | — |

`total == hypot(parameter, measurement)` is **checked**, not assumed. The
parameter interval is strictly inside the total interval at every held-out
condition. No discrepancy term is fitted, assumed, or absorbed into either — so
a systematically wrong model shows up as held-out failure rather than as a
quietly inflated σ that makes the failure disappear.

---

## 9. Leakage probes

All refused. The one that matters is the fourth, which no label comparison can
see:

| probe | result |
|---|---|
| held-out observation also in calibration | refused (shared key) |
| posterior built from the held-out dataset | refused, and the message names it |
| two halves sharing a `dataset_id` | refused |
| **same reading relabelled into the other half** | **refused (content digest)** |
| held-out scored against the wrong identity | refused |
| calibration/validation aliasing one source | refused |

The content digest covers observable, value and σ in canonical units, and
deliberately **not** `condition_id` (the point is relabelling) nor `source_ref`
(the same reading imported twice is still the same reading). Two distinct
measurements of a continuous quantity producing bit-identical value *and* σ is
a copy, not a coincidence; a study with genuine exact replicates declares it,
and the flag is part of the split digest so it cannot be set unnoticed.

`partition()` takes **condition** ids, not observation keys: splitting within
one condition leaks through the physics even though no key is shared, so there
is no argument that expresses it.

---

## 10. Field observation spike

An observation is declared in the units of the **world**; the array index is
**derived** from whichever mesh it is applied to.

The claim, stated as physics before it is stated as a refusal: node (2,2) of a
5×5 mesh over 40 mm is x = 20 mm; node (2,2) of a 9×9 mesh over the same extent
is x = 10 mm. **Same integers, different place, different temperature.** An
operator recorded as `field[2, 2]` would have reported both as one measurement.

- binds to one support by **fingerprint**, not `mesh_id` — two discretisations
  routinely share an id
- applying it to another mesh is a **refusal**, not a silent answer
- re-declaring the same *physical* probe against the refined mesh reads the
  **same temperature** — the property an index cannot have
- a probe falling between nodes reports how far it snapped
- serializable, with a tamper-checked digest

Three kinds: probe at a declared location, mean over a declared region, maximum
over the whole support. No PDE was calibrated.

---

## 11. Reproducibility

Both halves tested, because only one is obvious.

- **Same seed** → the same serialized record, field for field (wall time
  excepted). The coverage study is a pure function of its seed schedule.
- **Different seed** → different numbers that stay *statistically* consistent:
  over 20 seeds the recovered parameters are centred on the truth to within
  3 s.e. of the mean and scatter within a factor of two of the predicted
  standard error.

A study that reproduced exactly *because it ignored its seed* passes the first
test and fails the second.

---

## 12. Performance

| | |
|---|---|
| single calibration | 6 forward evaluations, **131 ms** |
| coverage study | **793 800** forward evaluations |
| wall time | **98.4 s** |
| throughput | **8 066 evaluations/sec** |

Every evaluation runs the production solver and crosses the analytic admission
boundary — building a real `ScientificResult` with provenance each time. No
optimisation was attempted: nothing was blocked.

Execution goes through Sprint 7's `run_sweep`, one case per repetition, not a
second loop written here.

---

## 13. Mutations — CAL / UQ / VAL

**CONTROL GREEN. 12/12 killed. No survivors. No stale patterns.**

| id | guard broken | verdict |
|---|---|---|
| CAL-1 | calibration/held-out overlap stops being refused | KILLED |
| CAL-2 | a parameter's unit stops being part of its identity | KILLED |
| CAL-3 | a value outside declared physical bounds is accepted | KILLED |
| CAL-4 | held-out validation always passes | KILLED |
| CAL-5 | the posterior's dataset identity stops being checked | KILLED |
| UQ-1 | the declared observation σ is dropped | KILLED |
| UQ-2 | the posterior reports zero parameter covariance | KILLED |
| UQ-3 | one uncertainty source stops being named | KILLED |
| UQ-4 | nominal coverage reported as though measured | KILLED |
| UQ-5 | a collapsed grid may claim precise parameters | KILLED |
| VAL-1 | the calibration half is scored as held out | KILLED |
| VAL-2 | evidence identity stops distinguishing evidence | KILLED |

A targeted apply/revert script, **not** entries in `tests/mutation_guards.py`:
that runner is inside certified scope and pinned, so a guard written this round
cannot join `MUTATIONS` without invalidating the snapshot. These are **not**
part of the certified 79 and are never added to it.

Each mutation names the **one** test that kills it, so a guard that stopped
biting shows as a survivor rather than as a smaller number. Every edit is
applied to real bytes and the restore is verified by SHA-256 against the bytes
read before it.

---

## 14. Scientific equivalence

Established three ways rather than asserted:

1. `src/engcore/scientific/**` and `src/engcore/domains/**` are
   **byte-identical** to the commit this sprint began at.
2. **Nothing** under either imports `engcore.inference` or `engcore.studies` —
   the dependency direction is one-way, so the changed code cannot reach them.
3. **1066** representative domain tests pass: DC, battery, CSTR, thermal
   scalar, field records/values, 2-D conduction and its convergence ladder.

The only pre-existing behaviour this round changed is inside `inference/`: the
admission-ref format now leads with the route, and
`AdmissibleNumericalPrediction.to_dict()` gained an `admission_route` key.
Neither is on any domain output path.
