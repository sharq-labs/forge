# Sprint 3 — Battery + Thermal Flagship

Branch `claude/battery-thermal-flagship-sprint-3` · base `origin/main @ d28c150e`

```bash
python benchmarks/battery_thermal_flagship_s3/harness/acquire.py --archive <archive.zip>
python benchmarks/battery_thermal_flagship_s3/harness/prereg.py
python benchmarks/battery_thermal_flagship_s3/harness/vendor.py
python benchmarks/battery_thermal_flagship_s3/harness/ocv.py
python benchmarks/battery_thermal_flagship_s3/harness/emit_ocv_module.py
python benchmarks/battery_thermal_flagship_s3/harness/calibrate.py
python benchmarks/battery_thermal_flagship_s3/harness/campaign.py --splits calibration validation --out CAMPAIGN_VALIDATION.json
python benchmarks/battery_thermal_flagship_s3/harness/flagship.py
python benchmarks/battery_thermal_flagship_s3/harness/campaign.py --splits calibration validation locked_holdout --open-holdout --out CAMPAIGN_HOLDOUT.json
python benchmarks/battery_thermal_flagship_s3/harness/gate_a.py
python benchmarks/battery_thermal_flagship_s3/harness/report.py
```

---

## 1. Verdict

**SPRINT 3 BATTERY + THERMAL FLAGSHIP: NOT YET PASSED**

Temperature passes Gate A on the locked holdout. Voltage does not: MAE is inside
its limit, RMSE and P95 are not.

| Gate A, locked holdout, cases inside declared applicability | measured | limit | |
|---|---|---|---|
| `terminal_voltage` MAE | 38.42 mV | 40.00 mV | **PASS** |
| `terminal_voltage` RMSE | 62.40 mV | 50.00 mV | **FAIL** |
| `terminal_voltage` P95 | 108.13 mV | 90.00 mV | **FAIL** |
| `terminal_voltage` max | 675.06 mV | reported, not gated | — |
| `cell_temperature` MAE | 1.29 K | 2.50 K | **PASS** |
| `cell_temperature` RMSE | 1.65 K | 3.00 K | **PASS** |
| `cell_temperature` P95 | 3.27 K | 5.00 K | **PASS** |
| `cell_temperature` max | 5.93 K | reported, not gated | — |
| `state_of_charge` | **NOT INDEPENDENTLY VALIDATED** | — | — |

Every threshold above was written in the first preregistration commit
(`1297648e`) and no amendment touched one.

### What the failure is

It is one cell out of three.

| holdout cell | voltage MAE | voltage RMSE | voltage P95 | temperature RMSE |
|---|---|---|---|---|
| B0007 | 17.6 mV | 20.5 mV | 36.2 mV | 0.60 K |
| B0036 | 12.7 mV | 17.3 mV | 36.5 mV | *not admitted* |
| **B0044** | **78.8 mV** | **99.7 mV** | **171.1 mV** | 2.12 K |

Two of the three holdout cells are predicted at about 20 mV RMSE, a third of the
limit. B0044 is four times worse and carries the aggregate over it.

B0044 delivers **8.4 % less charge** than B0042, the calibration cell its
parameter set was fitted on — the largest such gap among the six split cells,
and the next largest (−6.3 %) sits in the validation split, which passed. The
model's charge state is a fraction of a **declared constant basis**, so a cell
whose usable charge differs from the one its parameters were fitted on is
evaluated at the wrong point on the open-circuit voltage curve throughout its
discharge. That is not a surprise the model hid: `battery.cell.electrothermal_1rc`
lists *"any dependence of the usable capacity on temperature or rate — the
charge state basis is a constant"* among its exclusions, and the preregistration
amendment that fixed the basis said this difference would show up as a voltage
residual at a common charge state. It did.

Nothing was refitted after the holdout was opened, and no threshold was revised.

---

## 2. Data

**NASA Ames Prognostics Center of Excellence, Li-ion Battery Aging Data Set.**
One archive, `sha256 82302a7d…`, 209 708 670 bytes, retrieved from
`phm-datasets.s3.amazonaws.com`. Commercial 18650 cells, 2 Ah rated, cycled to
end of life in a temperature-controlled chamber.

2 798 discharge trajectories inspected, 2 369 retained by a screen that reads
measurements and no model: finite channels, strictly increasing time, a sampling
interval that can resolve the polarization relaxation, a plausible delivered
capacity, and a load that is recognisably one level. The square-wave cells
(B0025–B0028) are excluded because their 20 s period is sampled at about 10 s —
the profile cannot be reconstructed between samples, so a schedule built from it
would be invented rather than measured.

From those, the preregistered selection takes 63 in-band trajectories across 11
cells and 38 guardrail trajectories across 18 cells. Three in-band trajectories
belong to an experiment group with no independent cell and carry no campaign
case, so 98 of the 101 reach the corpus.

Two further screens, both model-free:

- **Replicate thermal screen.** Among the seven cells discharged at 2 A in the
  20–30 °C band, six show a median temperature rise of 13.6–15.6 K and B0036
  shows 2.2 K. Its cell temperature is not admitted as an observation; its
  terminal voltage still is, because the electrical channels are unaffected.
- **Full-charge screen.** One B0038 trajectory begins at rest at 4.053 V, which
  the open-circuit voltage authority places at a charge state of 0.88, not 1.
  Asserting a full-charge initial condition there would charge the model for an
  error in the initial condition. Not admitted.

### Splits

The independence unit is **one physical cell**. Assignment is by position within
each experiment group, cells ordered by identifier — outcome-blind, and nothing
about how well any cell is predicted enters it.

| | cells |
|---|---|
| calibration | B0005, B0018, B0033, B0038, B0042 |
| validation (in band) | B0006, B0034, B0043 |
| **locked holdout (in band)** | **B0007, B0036, B0044** |
| guardrail, declared outside | B0029–B0032, B0039, B0040, B0045–B0056 |

No cell appears in two splits. The corpus refuses a group that straddles the
calibration boundary, which is what caught B0038's out-of-band trajectories:
that cell already supplies calibration evidence, so its guardrail trajectories
were dropped rather than allowed to be both the fit and a test of it.

---

## 3. What the model is given, and what it never sees

**Given:** the measured load current at every sample instant, held between
samples; the ambient temperature; the measured cell temperature **at the first
instant only**; and the charge protocol's full-charge initial state.

**Never given:** any measured terminal voltage at any instant; any measured cell
temperature after the first; the cycle's own delivered capacity.

The prediction is a coupled electrothermal march over the whole trajectory — up
to 3 690 s and 336 coupling windows — from those inputs alone. Every executed
run passed the composition's own cross-domain validation, and 58 of 60 stopped
at the declared charge-state floor with a recorded termination rather than
running to the horizon.

---

## 4. The model

`battery.cell.electrothermal_1rc@0.1.0`, executed by
`system.battery_electrothermal@1` through Forge's authorized multiphysics path.

```
   measured current I(t)
            |
            v
  charge state  z = 1 - q / Q_basis          Q_basis = 2 Ah, declared constant
            |
            v
  OCV(z)  declared curve  --.
                             \
  R0(T) Arrhenius  ---------- +--> V = OCV(z) - I R0(T) - v_p
                             /
  RC branch  R1(T), C1  ----'
            |
            v
  Qdot = I^2 R0(T) + I <v_p>        irreversible only
            |
            v
  lumped body  C_th, hA, T_ambient
            |
            v
  cell temperature T  ---------> back into R0(T), R1(T)
```

The last arrow is what makes this a cycle rather than a one-way march, and it is
a real edge in the blueprint, not a description.

**What it does not contain**, stated on the record and not approximated:
reversible entropic heat `I T dU/dT`; ageing; hysteresis; a second diffusion
time constant; any temperature axis on the open-circuit voltage; any dependence
of usable capacity on temperature or rate; charge acceptance; internal
temperature gradients.

### Open-circuit voltage authority

A pseudo-OCV, from the charge and discharge branches of **single calibration
cells** — the discharge and the charge that follows it, minutes apart, same
cell, same chamber. Averaging the two branches cancels the ohmic and
polarization drop to first order without mixing cells or rates:

```
OCV(z)   = (I_c V_d(z) + I_d V_c(z)) / (I_c + I_d)
R_eff(z) = (V_c(z) - V_d(z)) / (I_c + I_d)
```

21 knots over `z ∈ [0.0922, 1.0]`, linear interpolation, **extrapolation
refused**. The top knot, at full charge, is a directly measured relaxed voltage
(4.1885 V) rather than a reconstruction. Every interior knot carries at least
seven calibration pairs; the interval was shortened until that held, which is
why the curve declines below `z = 0.092` instead of answering there from one
trajectory. No validation or holdout cell contributed a single knot.

It is **not** an equilibrium OCV: branch averaging does not cancel the
hysteresis between the two directions, and the branches are not at identical
temperature. Its own interquartile scatter across calibration pairs is carried
into the uncertainty budget.

### Parameters

Seven, fitted **per experiment group** on that group's calibration cells only,
then applied to that group's independent cells — a transfer between different
physical cells, not a per-cell refit.

The unit is a group because the thermal conductance is a property of the cell's
boundary, not its chemistry. Driving the lumped body with the dissipation the
**measured** voltage implies — no electrical parameter involved at all — fits
every calibration cell to under 1 K and returns hA = 0.039–0.050 W/K for the
cells in one set of campaigns and 0.103–0.121 W/K for those in another: a factor
of 2.4, with no overlap. One value fits neither.

| | FY08Q4 | 33_34_36 | 41_42_43_44 | 38_39_40 |
|---|---|---|---|---|
| fitted on | B0005, B0018 | B0033 | B0042 | B0038 |
| R0 at 298.15 K | 0.0910 Ω | 0.1642 Ω | 0.1087 Ω | 0.1896 Ω |
| C_th | 55.7 J/K | 97.5 J/K | 69.4 J/K | 99.9 J/K |
| hA | 0.0566 W/K | 0.0944 W/K | 0.0589 W/K | 0.1107 W/K |
| produces a claim | yes | yes | yes | **no** |

38_39_40 has no validation or locked-holdout cell, so its set is never applied
to independent evidence and makes no claim. Its trajectories carry no campaign
case.

Every parameter carries a standard error from the fit's own Jacobian and an
identifiability verdict. The thermal pair and R0 are **identified** in every
group; the polarization parameters are **weak** or **unidentified** in most,
and the record says so rather than presenting seven confident numbers.

---

## 5. Results

### Predictions, by split

| metric | calibration | validation | **locked holdout** |
|---|---|---|---|
| voltage n | 1 287 | 863 | 1 051 |
| voltage MAE | 24.4 mV | 24.5 mV | 38.4 mV |
| voltage RMSE | 42.2 mV | 40.3 mV | 62.4 mV |
| voltage P95 | 78.2 mV | 58.4 mV | 108.1 mV |
| temperature n | 1 287 | 863 | 674 |
| temperature MAE | 0.68 K | 0.66 K | 1.29 K |
| temperature RMSE | 1.06 K | 0.90 K | 1.65 K |
| temperature P95 | 2.59 K | 1.79 K | 3.27 K |

Validation — cells no fit ever saw — meets every Gate A criterion. The holdout
does not, for the single-cell reason in §1.

Core's own comparison over the holdout campaign: 5 428 pass, 597 fail, **8 465
correct refusals and zero unexpected ones**, refusal accuracy 1.0.

Pass fractions: calibration 0.923, independent **0.958** when the independent
evidence is the validation split alone, and **0.884** once the holdout is
included. The drop is B0044 and nothing else.

Core's diagnosis on both campaigns is `INSUFFICIENT_EVIDENCE` with confidence
`none`. Its stated reason — "independent evidence agrees with the model within
the reviewed tolerances" — is a per-case reading and is *not* the whole story
here: the aggregate Gate A on the holdout fails, and it fails because one cell's
residuals are large rather than because many cells are marginally off. So the
correct reading of that verdict is narrow: **no model-form inadequacy is
attributed on this evidence**, which is neither a claim of adequacy nor a
substitute for the Gate A result above.

### Residual structure

Failure clusters, over the whole campaign:

| dimension | bin | failed / scored |
|---|---|---|
| c_rate | [1.25, 2.5) /h | 212 / 732 (**29 %**) |
| c_rate | [0.25, 1.25) /h | 55 / 3 374 (1.6 %) |
| measured cell temperature | [318, 333) K | 58 / 168 (**35 %**) |
| measured cell temperature | [303, 318) K | 188 / 2 346 (8 %) |
| measured cell temperature | [288, 303) K | 23 / 1 786 (1.3 %) |
| depth of discharge | [0.6, 0.8) | 73 / 710 (10 %) |

The model fails where it is hot and fast. Both bins are the same runs — the 4 A
discharges self-heat to 55 °C — so the two clusters are not independent
evidence of two defects.

On the holdout specifically, the rest phase is worse than the loaded phase
(voltage MAE 59 mV against 38 mV): a single RC branch has one relaxation time
constant and the measured tails have more than one. That is a declared
exclusion, and it is visible rather than smoothed over.

### Validation envelope

`terminal_voltage`, over depth of discharge × measured cell temperature ×
C-rate. A cell is **supported** only with zero failures in it.

- **Supported:** 8 cells, all at `c_rate ∈ [0.25, 1.25)` or rest, with cell
  temperature below 303 K.
- **Failed:** 10 cells — every 2C cell, and the 1C cells once the cell warms
  past 30 °C.
- **Untested:** 132 cells. The grid is declared, not fitted to where the
  evidence fell, so it reports what was never reached.

The flagship run's query point — 10 % discharged, 1C, cell at 25 °C — is
classified `SUPPORTED`. Two further points are classified and reported rather
than left implicit, and both come back `OUTSIDE_VALIDATED_ENVELOPE`: half
discharged at 1C with the cell at 35 °C, and 30 % discharged at 2C.

### Applicability

| | |
|---|---|
| **INSIDE** | ambient 20–30 °C; load 0.5–4.5 A; charge state ≥ 0.2737; discharge and rest only; cycle index ≤ 40 |
| **OUTSIDE** | ambient below 15 °C or above 35 °C; charge state below 0.2737; any current below the declared rest band (i.e. charge) |
| **UNDECLARED** | any other cell chemistry, format or fixture — no evidence here speaks to one |

The charge-state floor is the lowest knot of the OCV authority whose
interquartile scatter across calibration pairs is inside the frozen 50 mV
acceptance tolerance. Below the first such knot the authority disagrees with
itself by more than the campaign's own definition of agreement. A separate,
model-free check agrees: the longest measured relaxations at end of discharge
sit up to 370 mV from the curve below `z = 0.23`, in both directions.

The composition refuses at preflight, before any state advances. All 19
out-of-band trajectories were declined by
`battery_electrothermal.ambient_at_or_below_declared_ceiling` — the pack's own
predicate, not a harness opinion.

### Uncertainty

| channel | status |
|---|---|
| parameter | **quantified.** Seven standard errors from the fit's Jacobian enter as STANDARD/PARAMETER external uncertainties; the composition propagates them through its own monolithic reference. The UQ channel matrix is enforceable and complete. |
| measurement | **UNKNOWN.** This archive states no accuracy for any channel. No acceptance tolerance here is a source-reported spread and no observation carries a SOURCE_REPORTED uncertainty. |
| numerical | **bounded, not distributed.** The refinement study measures how far the answer moves under subdivision (0.104 mV, 0.0017 K) and the bound is reported; no distribution is produced. |
| model form | **UNKNOWN.** Core's diagnosis is `INSUFFICIENT_EVIDENCE`, which is not a quantified model-form uncertainty, and none is claimed. |

### Numerical credibility

| check | outcome | |
|---|---|---|
| convergence | **SATISFIED** | every coupling window converged; no participant step reported otherwise |
| refinement | **SATISFIED** | halving then quartering each measured interval moves voltage by 0.104 mV and temperature by 0.0017 K, against a tenth of each acceptance tolerance (5 mV, 0.3 K); and each step is about half the previous one, as a first-order splitting should be |
| conservation | **SATISFIED** | the heat the cell reports equals the heat the body consumes in every window, and the energy deposited over the run equals what the body stored plus what it rejected |

### Replay

`REPLAYED_MATCH`. An actual second execution of the authorized plan against
authority that still matches the digests the plan was pinned to — not a
serialization round trip.

### Certification

Production policy **satisfied** with no recorded gaps. Full Trust **satisfied**.
The certification record verifies. All eleven gates pass, including
`uq_channel_completeness`, `computational_replay_verified`,
`validation_envelope_supported` and `independent_verification_passed`.

The certification is about the flagship run and the point it makes a claim at.
It is not a statement that Gate A passed; Gate A is a separate, frozen
acceptance policy over the locked holdout, and it did not.

---

## 6. Holdout governance

Opened through the Sprint 2 ledger, which records the opening and binds it to
the normalized dataset digest and one evaluation id.

There were **two** evaluations, and the reason is recorded rather than hidden.
The first was scored on a parameter set fitted against a march that applied the
composition's declared rest band differently from the authorized path — on nine
of twenty-seven calibration trajectories the fitting march aborted on channel
noise and contributed only a penalty. The defect was found by the
march-equivalence regression test, which requires a march and an authorized run
of the same trajectory to agree to 1e-12. **No holdout residual, metric or case
was involved in finding it or in deciding the fix.**

A corrected model is a new evaluation, not a second opening of the old one, so
it was registered under its own id (`…holdout.v4`). Both results are in
`RESULT.json`. They agree: the first gave voltage MAE 38.85 / RMSE 62.51 / P95
108.14 mV and the same temperature pass, so the correction changed the
parameters but not the verdict.

No threshold was revised after either opening, and no parameter was chosen by
looking at a holdout residual.

---

## 7. Limitations, separated

### Scientific limitation

- **A constant charge-state basis cannot carry cell-to-cell capacity spread.**
  This is the Gate A failure. An 8 % capacity gap between a cell and the
  calibration cell of its group costs about 80 mV of MAE. Fixing it means either
  a per-cell capacity — which needs a measurement of the cell before predicting
  it, and this campaign deliberately gives the model nothing of the kind — or a
  capacity-aware charge-state definition, which is a new model version.
- **One RC branch, one time constant.** The measured relaxation tails have more
  than one, and the rest-phase residuals are twice the loaded-phase ones.
- **No entropic heat.** The irreversible term is the whole heat source. The term
  is of the same order at low rate and changes sign with direction and charge
  state; no entropy coefficient is measured for these cells, so it is declared
  absent rather than set to zero.
- **The OCV authority is a pseudo-OCV.** It carries the hysteresis of the
  branches it was averaged from and has no temperature axis.
- **Constant resistance in charge state.** The measured branch difference runs
  from 0.127 Ω at high charge to over 0.30 Ω near empty; the model has one value
  per group. This is most of why the failure clusters at high depth of discharge.

### Engineering limitation

- The thermal parameters are fitted per experiment group because they are
  fixture properties. A new fixture needs its own calibration cells; nothing
  here says how few.
- The composition's coupling is explicit and staggered, so the cell is evaluated
  at the previous window's temperature. The refinement study bounds what that
  costs on this grid; it is not bounded in general.
- The calibration march is a separate implementation from the authorized path,
  kept honest by a 1e-12 equivalence test. That test is the only thing standing
  between the two, as this round demonstrated.

### Missing data

- **No instrument accuracy.** The archive states none, so the measurement
  channel of the uncertainty budget is UNKNOWN and every acceptance threshold
  rests on engineering relevance instead.
- **No independent state-of-charge reference.** The archive's per-cycle
  `Capacity` is measured on the very discharge being predicted, and comparing a
  coulomb counter against a coulomb counter tests nothing. SOC is not validated
  and is not claimed to be.
- **No 4 A cell in the locked holdout.** Only three cells carry a 4 A discharge
  in the declared band, and two are needed for calibration and validation. The
  holdout therefore licenses the 1C corner only, and the 2C corner is validated
  but not holdout-tested.
- **No entropy coefficient, and no fixture description.** Both would turn
  declared exclusions into modelled physics.

### Future improvement

- A capacity-aware charge state, and a holdout re-run as a newly governed
  evaluation — not this one.
- A second RC branch, which the rest-phase residual structure supports asking
  for and does not by itself justify.
- Charge-state-dependent resistance, which the branch-difference measurement
  already characterises without any model.
- Promote the independent monolithic route from composition verification to a
  cross-solver consensus, which would let
  `electrothermal_terminal_residual` earn a level instead of establishing
  nothing.

---

## 8. Provenance chain

```
archive sha256 82302a7d…
   -> member .mat sha256 per trajectory
      -> vendored selected_trajectories.json
         -> normalized ReferenceDataset digest e43b943b…
            -> reviewed acceptance tolerances (frozen at 1297648e)
               -> ValidationCampaign report digest
                  -> coverage -> ValidationEnvelope
                     -> authorized run + replay + numerical evidence
                        -> certification record (verified)
```

Every link is a digest in `RESULT.json`, and every one of them is checked by
the code that consumes it rather than asserted here.
