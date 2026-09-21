# Sprint 3 — S3.1 Battery Authority Gap Map

Read from source at `d28c150e`, not from README claims. Every "current
implementation" cell names the module that actually holds the behaviour.

| Capability | Current implementation | Scientifically usable? | Missing | Action |
|---|---|---|---|---|
| SOC dynamics | `domains/battery/solver.py` (`evaluate_step`), `thevenin.py` (`evaluate_thevenin_step`) — coulomb counting `z1 = z0 - I dt / (eta Q)`, refuses leaving `[0,1]` rather than clipping | Yes | nothing for CC; no charge branch | Reuse; extend sign handling for rest/charge in the flagship kernel |
| OCV | `cell.CellSpecification.open_circuit_voltage` → `context.open_circuit_voltage`; chord between two endpoints, or a `DeclaredCurve` | Yes | no temperature axis; no dataset-derived curve for the flagship cell | Build a declared OCV authority from calibration data (S3.6); keep the curve record as-is |
| OCV extrapolation policy | `scientific/models/curves.DeclaredCurve.evaluate` returns `IN_DOMAIN` / `OUTSIDE_VALIDATED_DOMAIN` / `UNKNOWN`; value is `None` unless in domain | Yes — already fails closed | nothing | Reuse unchanged |
| R0 / internal resistance | `cell.CellSpecification.internal_resistance` — one constant scalar | Partly | no temperature dependence | Add Arrhenius `R0(T)` in the flagship kernel; the constant path is untouched |
| 1-RC Thevenin dynamics | `domains/battery/thevenin.py` — exact closed form for one constant-current interval | Yes as a kernel | single step only; discharge-only (negative current refused); no trajectory driver; no thermal coupling; explicitly **not** in any pack (`domainpacks/builtin_battery.py` says so) | Build the flagship kernel on the same equations, with rest/charge admitted and temperature-dependent parameters |
| Polarization voltage | `thevenin.TheveninState.polarization_voltage` | Yes | not carried as runtime state across a coupled run | Carry as participant state in the new execution pack |
| Terminal voltage | `thevenin.evaluate_thevenin_step` → `OCV - I R0 - v_p`; `solver.evaluate_step` → `OCV - I R_int` | Yes | — | Reuse the 1-RC form |
| Coulomb counting | `models.COULOMB_COUNTING_MODEL` + solver | Yes | — | Reuse |
| Peukert effects | `models.PEUKERT_DERATING_MODEL` | Yes | rate-dependent capacity only; not part of the Thevenin path | **Out of scope for the flagship** — not claimed |
| Heat generation | `solver.cell_heat_generation` → `I^2 R_int` only | Partly | no polarization heat; no entropic term | Flagship uses irreversible heat `I^2 R0 + v_p I` (both measurable losses); entropic heat declared absent |
| Thermal models | `domains/thermal_models/lumped.py` — first-order lumped body, public API | Yes | — | Reuse as the thermal participant's physics |
| Electrothermal coupling | `domains/battery/coupling.py` `run_self_heating_discharge` — sequential march, explicitly **one-way** (`CouplingDirection.ONE_WAY`) because `R_int` is constant | Partly | no two-way coupling; not a multiphysics-runtime path; bypasses CompositionPack/ExecutionPack | Build a genuine cyclic CompositionPack: `T → R(T) → Q̇ → T` |
| Parameter handling | `domains/battery/calibration.py` — OCV-at-rest observations through the frozen `calibrate`; `scientific/corpus/calibration.py` — `CalibratedParameterSet` with bounds, identifiability, dataset digest | Yes for the record; no for trajectories | no trajectory-fitting objective | Fit through a new objective; record in the existing `CalibratedParameterSet` |
| Initial state | `thevenin.TheveninState`; scenario `StateSnapshot`/`StateVariable` | Yes | — | Reuse |
| Time stepping | `execution/multiphysics/runtime.py` — coupling windows, scheduled events cut window boundaries (`target = min(end, t+width, next_event)`) | Yes | — | Drive the measurement grid with `ScenarioEvent`s |
| Measured input profiles | `scenarios/contracts.py` — `TimeSeriesInput` (`STEP` / `LINEAR`), `ComposedInputSchedule`, wired through `execute_authorized_graph_plan` | Yes | no battery input binding exists | Declare `battery.load_current` as a scheduled external input |
| Units | `scientific/units/quantity.Quantity` everywhere | Yes | — | Reuse |
| Validity limits | `context.CellLimits`, `models.*` validity conditions, `ValidityStatus` | Yes | limits are about the Rint models, not the flagship | Declare the flagship's own applicability |
| Dataset ingestion | `claims/adapters/nasa_battery_aging.py` — NASA samples → `DatasetObservation` (claims corpus, 2-way split only) | Partly | produces claims records, not `scientific.corpus.ReferenceDataset`; `claims.DatasetSplit` has no `LOCKED_HOLDOUT` | Add a corpus-side adapter; leave the claims adapter alone |
| Split governance | `scientific/corpus/dataset.py` — `DatasetSplit` (3-way incl. `LOCKED_HOLDOUT`), `HoldoutRelease`, `HoldoutOpening`, `HoldoutLedger`, independence-group straddle refusal | Yes | — | Reuse; independence unit = physical cell |
| Validation campaign | `scientific/corpus/campaign.py` — `run_campaign`, `compare_observation` | Yes | — | Reuse |
| Coverage / clustering | `scientific/corpus/coverage.py` — `build_coverage_by_metric`, `cluster_failures` | Yes | — | Reuse |
| Envelope / applicability | `scientific/corpus/envelope.py` — `ValidationEnvelope`, `ValidationQueryPoint`, `Applicability` | Yes | — | Reuse |
| Numerical evidence | `scientific/corpus/numerical.py` — `NumericalCheck`, `CheckOutcome` | Yes | — | Reuse |
| Replay | `assembly/replay.py` — `replay_authorized_graph_plan` | Yes | — | Reuse |
| Certification | `assembly/certification.py` — `assess_authorized_multiphysics_run`, `certify_authorized_multiphysics_run` | Yes | — | Reuse |

## What is deliberately not duplicated

`engcore.domains.battery.thevenin` already states the 1-RC equations correctly
and refuses to clip state. The flagship kernel does **not** restate them: it
imports `evaluate_thevenin_step`'s equations by reusing the same closed form and
adds only what the flagship needs — a temperature argument, admitted rest/charge
segments, and heat generation. Nothing in `solver.py`, `cell.py`, `context.py`
or `models.py` is modified.

## What is deliberately not promoted

`domainpacks/builtin_battery.py` says the 1-RC kernel "joins a pack when it
passes its own calibration/validation gate, not before". Sprint 3 builds that
gate. The kernel is promoted into a **new** composition pack whose manifest
names the evidence, and `battery.cell@1` is left exactly as it is.
