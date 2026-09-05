# MVR0 — Multirotor Reference Vertical Slice V0.1 preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Starting stable checkpoint: `c597d6ef061f3fafa921035a2608d77a48050608` (D2 PASS/FROZEN)

## Purpose

Run the first concrete target-driven system-pack vertical slice through the frozen D0/D1/D2 design stack.

MVR0 must demonstrate, without changing general design-core semantics, that one real composite system family can:

1. declare a mixed typed `DesignSpace`;
2. enforce system-owned structural generation constraints through the D2 `ProposalGate` boundary;
3. generate approximately 1000 unique `CandidateProposal` / `DesignCandidate` / candidate `ScientificTwin` identities;
4. evaluate every generated candidate with an explicit, attributable scientific reference model;
5. assess a fixed target specification separately from scientific-result validity;
6. build deterministic D1 Pareto and scoped-elite archives that preserve plural/partial success.

This is a **reference analytic benchmark**, not a certified aircraft-design model and not a physical-validation claim.

## Architecture boundary

MVR0 is the first concrete System Pack experiment.

System-specific code may live under:

- `src/engcore/systems/aerospace/multirotor/`
- `experiments/multirotor_mvr0/`

Reusable rotor-hover physics, if introduced, belongs under reusable scientific-domain code such as:

- `src/engcore/domains/fluids/aerodynamics/`

The following frozen general layers must not acquire multirotor/product branching:

- `engcore.design`
- `engcore.scientific.twins`
- D0/D1/D2 contracts
- Scientific Core result/provenance contracts

No `if system == "multirotor"` or equivalent is permitted in general design infrastructure.

## Frozen benchmark target

The first benchmark target is deliberately explicit and modest. It exists to exercise the architecture, not to assert a universal aircraft requirement.

Reference environment / mission:

- payload mass: `0.50 kg`
- minimum reference hover endurance: `15 min`
- maximum reference takeoff mass: `3.00 kg`
- maximum reference disk loading: `120 N/m^2`
- air density: `1.225 kg/m^3`
- gravitational acceleration: `9.80665 m/s^2`
- usable battery-energy fraction: `0.80`
- baseline hover drivetrain / rotor efficiency factor: `0.72`
- auxiliary electrical load: `25 W`

These constants must be recorded as model inputs/assumptions. They are not inferred by an LLM.

## Frozen mixed design space

MVR0 uses all four D0/D2 variable kinds.

### 1. `rotor_count`

- kind: `INTEGER`
- role: `DESIGN`
- unit: `dimensionless`
- bounds: inclusive `4 .. 8`

D2 may generate 4, 5, 6, 7 or 8. The multirotor System Pack owns an opaque generation constraint that admits only even rotor counts `{4, 6, 8}` for this benchmark.

The constraint reference is frozen as:

`multirotor:even-rotor-count:v1`

This demonstrates that D2 does not learn or interpret product semantics itself.

### 2. `rotor_radius`

- kind: `CONTINUOUS`
- role: `DESIGN`
- unit: `m`
- bounds: `0.09 .. 0.20 m`

### 3. `battery_energy`

- kind: `CONTINUOUS`
- role: `DESIGN`
- unit: `Wh`
- bounds: `120 .. 450 Wh`

### 4. `battery_specific_energy_class`

- kind: `CATEGORICAL`
- role: `DESIGN`
- unit: `dimensionless`
- categories:
  - `conservative`
  - `standard`
  - `high`

The reference-model mapping is frozen prospectively as:

- conservative: `160 Wh/kg`
- standard: `220 Wh/kg`
- high: `280 Wh/kg`

These are benchmark class coefficients, not catalog-component claims.

### 5. `frame_class`

- kind: `CATEGORICAL`
- role: `DESIGN`
- unit: `dimensionless`
- categories:
  - `light`
  - `standard`
  - `rugged`

Reference base masses:

- light: `0.35 kg`
- standard: `0.55 kg`
- rugged: `0.80 kg`

The reference frame radius coefficient is frozen as `0.35 kg/m per rotor` multiplied by rotor radius and rotor count.

These are benchmark coefficients, not structural certification.

### 6. `prop_guards`

- kind: `BOOLEAN`
- role: `DESIGN`
- unit: `dimensionless`

Reference benchmark effects:

- guard mass: `0.035 kg` per rotor when enabled;
- hover-efficiency multiplier: `0.94` when enabled.

## Other fixed reference mass coefficients

The MVR0 reference system composition uses:

- payload: benchmark target payload above;
- avionics / fixed system mass: `0.18 kg`;
- motor + ESC mass: `0.085 kg` per rotor;
- rotor / propeller mass: `0.025 kg` per rotor.

These are intentionally simple explicit coefficients to exercise coupled mass / disk-area / power / endurance behavior. They are not hardware-catalog truth.

## Reference scientific model

### Rotor hover momentum relation

For total hover thrust `T`, air density `rho`, and total actuator disk area `A`, the reusable reference hover model computes ideal induced power:

`P_i = T^(3/2) / sqrt(2 * rho * A)`

where:

- `T = m * g`
- `A = N * pi * R^2`

The model is limited to steady hover and an ideal uniform actuator-disk approximation.

### System electrical hover power

The system pack computes reference electrical hover power as:

`P_electric = P_i / eta + P_aux`

where:

- base `eta = 0.72`;
- with prop guards: `eta = 0.72 * 0.94`;
- `P_aux = 25 W`.

This is a reference coupling model, not motor/ESC/propeller-map validation.

### Battery mass

`m_battery = E_battery / specific_energy_class`

with compatible energy/specific-energy units.

### Reference endurance

`endurance = usable_battery_energy / P_electric`

where usable energy is `0.80 * battery_energy`.

### Reference disk loading

`disk_loading = T / A`

## Explicit scientific assumptions / exclusions

Every MVR0 evaluation must explicitly carry assumptions including:

- steady hover only;
- uniform actuator-disk momentum-theory approximation;
- no forward-flight aerodynamics;
- no rotor-rotor interference correction;
- no propeller blade-element map;
- no motor/ESC efficiency map;
- no battery voltage sag or thermal model;
- no structural stress/buckling/fatigue analysis;
- no flight-control/stability analysis;
- no acoustic model;
- no propeller tip-Mach constraint;
- benchmark mass and efficiency coefficients are synthetic/reference coefficients, not catalog evidence;
- target satisfaction is valid only under this reference model.

MVR0 must never describe a candidate as physically validated, certified, safe, flight-ready or experimentally proven.

## Candidate Scientific Twin boundary

Every accepted D2 proposal must materialize as one exact `ScientificTwin(kind=CANDIDATE)`.

The candidate Twin should contain the exact typed design declarations used by the system pack and model references sufficient to identify the reference model family.

D2 generation-binding rules remain authoritative for Proposal → Candidate → Twin internal identity.

MVR0 does not modify the Scientific Twin contract.

## Population generation

The reference experiment requests:

- accepted population count: `1000`
- D2 generation: `0`
- strategy: `halton_v1`
- deterministic candidate prefix: `mvr0`
- explicit attempt budget: `3000`

Odd `rotor_count` proposals are rejected by the system-owned gate and consume attempts normally.

The run fails closed if D2 cannot produce exactly 1000 unique accepted candidates within the attempt budget.

## Scientific result metrics

Every accepted candidate must produce one attributable `ScientificResult` with at least these unit-bearing values:

- `total_mass`
- `battery_mass`
- `total_disk_area`
- `disk_loading`
- `ideal_induced_power`
- `hover_electrical_power`
- `hover_endurance`
- `mass_margin`
- `endurance_margin`
- `disk_loading_margin`

Positive target margins indicate passing the corresponding benchmark requirement; negative margins indicate failure.

ScientificResult provenance must include the D1 `ResultBinding` for the exact candidate / Twin / DesignSpace identity.

Analytic evaluation uses `ConvergenceState.NOT_APPLICABLE`; this must not be reworded as solver convergence or validation proof.

## Target assessment boundary

Target satisfaction is a separate system-level assessment over explicit result metrics:

A candidate meets the frozen MVR0 reference target iff all are true under the reference model:

- `mass_margin >= 0`
- `endurance_margin >= 0`
- `disk_loading_margin >= 0`

This boolean assessment is not a Scientific Core validation level and is not physical evidence.

A candidate may fail the target while still being a scientifically attributable/evaluable candidate and therefore remain useful for Pareto or scoped partial-success analysis.

## D1 selection-eligibility policy for MVR0

All successfully computed, attributable reference-model evaluations are explicitly `SelectionEligibility.ELIGIBLE` for MVR0 archive construction, with a reason that archive eligibility means only that the reference-model evaluation is available for comparison.

MVR0 must **not** equate D1 eligibility with target satisfaction, physical feasibility, safety or validation.

This separation is required so partial successes that miss one target requirement are not erased before scoped-elite analysis.

## Objectives

The global MVR0 Pareto archive uses exactly three objectives:

1. minimize `total_mass` in `kg`;
2. maximize `hover_endurance` in `s`;
3. minimize `hover_electrical_power` in `W`.

No weights, normalization or scalar winner are introduced.

## Scoped partial-success archives

MVR0 must create at least these D1 scoped archives from the same attributable evaluation universe:

- `multirotor:mass` — minimize `total_mass`;
- `multirotor:endurance` — maximize `hover_endurance`;
- `multirotor:hover-power` — minimize `hover_electrical_power`.

Scoped membership means only non-dominance under that declared objective subset. It is not compatibility proof or system-level superiority.

## Experiment outputs

The targeted experiment/test must make it possible to report deterministically:

- generated candidate count;
- rejected proposal count;
- count by rotor count;
- reference-target pass count;
- Pareto archive member count;
- each scoped-elite member count;
- representative metric ranges for mass/endurance/power/disk loading;
- exact candidate/Twin/evaluation identities for archive members.

No target-pass count or winning candidate is preregistered in advance.

A zero target-pass result is scientifically acceptable if it is what the frozen model produces.

## Explicitly deferred

Not part of MVR0 V0.1:

- real motor/propeller/battery catalogs;
- blade-element/momentum or CFD validation;
- forward-flight mission simulation;
- thermal/electrical dynamic battery models;
- motor/ESC operating maps;
- control/stability simulation;
- structural finite-element analysis;
- geometry/topology design grammar;
- conditional variables;
- adaptive generation;
- recombination;
- novelty search;
- uncertainty propagation / calibration for this model;
- multi-fidelity promotion;
- physical prototype validation;
- claiming one archive member is the globally best multirotor;
- changing D0/D1/D2 semantics.

Missing concepts discovered by this experiment must become successor milestones rather than retroactive exceptions in frozen design contracts.

## Acceptance criteria

### A1 — system-pack separation

All multirotor-specific logic stays outside general D0/D1/D2 infrastructure. Frozen general design contracts contain no multirotor branching.

### A2 — reusable scientific-model separation

If the ideal rotor-hover relation is introduced as shared physics, it is placed under reusable scientific-domain code rather than hidden inside generic design code.

### A3 — exact mixed design-space generation

D2 produces exactly 1000 unique accepted mixed-type candidates under the frozen design space and gate, with valid Proposal → Candidate → Twin identity.

### A4 — system-owned gate

The general D2 layer never learns that even rotor counts are a multirotor rule; the exact opaque constraint reference is owned by the system pack.

### A5 — attributable scientific evaluation

Every generated candidate receives one `ScientificResult` with unit-bearing metrics, explicit assumptions/provenance, and exact D1 result binding to candidate/Twin/design-space identity.

### A6 — analytic-model honesty

Analytic reference results use `NOT_APPLICABLE` solver convergence and do not claim numerical-solver validation, physical validation, certification or safety.

### A7 — target assessment separation

Reference-target pass/fail is computed from explicit margins and remains separate from Scientific Core validation and D1 selection eligibility.

### A8 — plural-success preservation

D1 Pareto and scoped archives are built from the full successfully evaluated comparison universe, so candidates that miss one benchmark requirement can still survive as partial successes.

### A9 — no hidden scalar winner

Global comparison is exact D1 Pareto on mass/endurance/power only; no weighted score, normalization or LLM ranking is introduced.

### A10 — deterministic rerun

For the same frozen code/benchmark, candidate identities, target assessments, Pareto membership and scoped-elite membership are deterministic.

### A11 — scientific-domain boundary

Reference rotor-hover physics uses explicit unit-aware inputs and fails closed on non-positive mass/disk area/air density or nonphysical efficiency values.

### A12 — practical 1000-candidate vertical slice

A targeted test/experiment evaluates the complete 1000-candidate population and produces the deterministic archive/target summary without manually injecting candidate records.

### A13 — frozen milestone protection

D0, D1, D2, Scientific Twin V0.1 and prior scientific milestones remain semantically unchanged.

### A14 — regression safety

Targeted MVR0 tests and then the full repository regression must pass before MVR0 can be frozen.

## Failure policy

If this experiment reveals that true multirotor work requires conditional design variables, catalog identity, compatibility graphs, higher-fidelity rotor physics, multi-fidelity escalation or richer target contracts, those become explicit successor preregistrations.

Do not make MVR0 pass by weakening frozen D0/D1/D2 semantics or by silently upgrading this analytic benchmark into a physical-truth claim.
