# Calibration, UQ & Held-Out Validation — Sprint 8

> **STATUS: IN PROGRESS.** Phases 1–2 complete and recorded below. The verdict
> section is deliberately absent until the work it would describe exists.

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
