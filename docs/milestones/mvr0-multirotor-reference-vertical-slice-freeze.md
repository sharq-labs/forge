# MVR0 — Multirotor Reference Vertical Slice V0.1 freeze

Status: **PASS / FROZEN**

Milestone ID: `MVR0`

## Frozen identities

- Starting stable checkpoint (D2 PASS/FROZEN): `c597d6ef061f3fafa921035a2608d77a48050608`
- MVR0 preregistration commit: `9fb8a2efcde3657fc00c130f95505803cb3f5bfb`
- Final MVR0 implementation source tested before freeze record: `02482ad15a3dfa9a21a644c4c36756695277a6ef`
- Preregistration: `docs/mvr0-multirotor-reference-vertical-slice-prereg.md`

The MVR0 preregistration remained **FROZEN BEFORE IMPLEMENTATION** and was not rewritten after observing tests, generated candidate results, or adversarial review findings.

## Scope actually delivered

MVR0 is the first concrete target-driven System Pack vertical slice through frozen D0/D1/D2 contracts.

Delivered behavior:

- mixed typed multirotor `DesignSpace` using continuous, integer, categorical and boolean variables;
- system-owned opaque even-rotor generation constraint;
- D2 deterministic `halton_v1` initial population generation;
- exact Proposal → DesignCandidate → candidate ScientificTwin materialization;
- reusable ideal actuator-disk hover physics under `engcore.domains.fluids.aerodynamics`;
- composite multirotor reference mass / disk-area / power / endurance model under `engcore.systems.aerospace.multirotor`;
- exact D1 ResultBinding in every evaluation result provenance;
- explicit target assessment separate from D1 selection eligibility and Scientific Core validation;
- exact global D1 Pareto archive;
- scoped D1 elite archives for mass, endurance and hover power;
- deterministic 1000-candidate end-to-end experiment harness.

MVR0 remains an analytic **reference benchmark**. It is not CFD, structural FEA, motor-map validation, battery electrochemistry, control/stability validation, flight certification or a physical aircraft-safety claim.

## Frozen benchmark target

- payload mass: `0.50 kg`
- minimum reference hover endurance: `15 min` (`900 s`)
- maximum reference takeoff mass: `3.00 kg`
- maximum reference disk loading: `120 N/m^2`
- air density: `1.225 kg/m^3`
- gravity: `9.80665 m/s^2`
- usable battery energy fraction: `0.80`
- baseline hover efficiency factor: `0.72`
- auxiliary electrical load: `25 W`

These are explicit benchmark inputs/assumptions, not LLM-derived numerical truth.

## Frozen mixed design space

- `rotor_count`: integer, `4 .. 8`, with system-owned gate admitting `{4, 6, 8}`;
- `rotor_radius`: continuous, `0.09 .. 0.20 m`;
- `battery_energy`: continuous, `120 .. 450 Wh`;
- `battery_specific_energy_class`: categorical `conservative | standard | high`;
- `frame_class`: categorical `light | standard | rugged`;
- `prop_guards`: boolean.

Opaque constraint id:

`multirotor:even-rotor-count:v1`

The even-rotor rule remains owned by the multirotor System Pack; frozen D2 contains no multirotor semantics.

## Scientific reference-model boundary

Reusable ideal hover physics uses:

`P_i = T^(3/2) / sqrt(2 * rho * A)`

and:

`disk_loading = T / A`

where total hover thrust is `m*g` and total actuator area is `N*pi*R^2`.

System electrical hover power is:

`P_electric = P_i / eta + P_aux`

and reference endurance is:

`endurance = usable_battery_energy / P_electric`

with explicit Wh→seconds conversion.

The independent adversarial review found the equations, dimensional handling, efficiency direction, mass/thrust relation, disk area, battery specific-energy mapping and target-margin signs consistent with the frozen preregistration.

## Scientific honesty boundary

Every scientific result is explicitly bounded by assumptions including steady hover, uniform actuator-disk theory and absence of rotor-interference, blade-element, forward-flight, motor-map, battery-dynamic, thermal, structural, control/stability and acoustic validation.

Analytic results use `ConvergenceState.NOT_APPLICABLE`.

MVR0 does not claim:

- physical validation;
- flight readiness;
- safety certification;
- globally optimal multirotor design;
- experimentally proven aircraft performance.

## Target-assessment boundary

Reference target pass/fail is derived only from explicit result margins:

- mass margin;
- endurance margin;
- disk-loading margin.

Target satisfaction remains separate from:

- Scientific Core validation status;
- D1 `SelectionEligibility`;
- feasibility in unmodelled physics;
- safety;
- certification;
- truth.

D1 eligibility means only that one attributable analytic evaluation is available for archive comparison.

## 1000-candidate experiment outcome

The frozen implementation source `02482ad15a3dfa9a21a644c4c36756695277a6ef` produced:

- accepted candidates: `1000`;
- rejected proposals: `671`;
- rotor-count distribution:
  - 4 rotors: `335`;
  - 6 rotors: `333`;
  - 8 rotors: `332`;
- reference-target pass count: `93`;
- global Pareto members: `26`;
- scoped elite members:
  - `multirotor:mass`: `1`;
  - `multirotor:endurance`: `1`;
  - `multirotor:hover-power`: `1`.

Metric ranges:

- disk loading: `31.86753677322779 .. 382.9807384964284 N/m^2`;
- hover electrical power: `167.94356317443598 .. 847.4588523112939 W`;
- hover endurance: `909.7402200713137 .. 4709.465485688354 s`;
- total mass: `2.113753959109021 .. 5.832724288980338 kg`.

All 671 rejections were system-gate odd-rotor rejections during this frozen run.

## Observed scientific/design signals

### Endurance target non-discrimination

The minimum generated endurance was `909.7402200713137 s`, above the frozen `900 s` target. Therefore endurance did not discriminate candidates in this particular frozen population.

This is a **valid observed outcome and successor-experiment design signal**, not an MVR0 bug and not a reason to rewrite the frozen target retrospectively.

### Scoped single-objective archive size

Each single-objective scoped archive retained one exact extreme member. This is expected under frozen D1 exact Pareto semantics when there are no exact ties.

If future discovery workflows need to retain many partial successes, richer elite-retention semantics must be introduced through a successor milestone rather than by rewriting frozen D1 or MVR0.

## Adversarial review

Independent adversarial review verdict:

**SAFE TO PROCEED**

Blocking findings:

- P0: none;
- P1: none;
- P2: none.

Non-blocking P3:

- exact archive construction is quadratic and already contributes significant runtime;
- 10k/100k populations will likely require successor performance work such as work-avoidance, cached objective projection or semantically equivalent archive acceleration;
- this is a scaling concern, not current scientific incorrectness.

Review acceptance status before full regression:

- A1-A13: PASS;
- A14: PARTIAL only because full repository regression was still pending.

Final review recommendation:

**PROCEED TO FULL REGRESSION**

## Targeted test gate

MVR0 targeted suite against implementation source `02482ad15a3dfa9a21a644c4c36756695277a6ef`:

- `7 passed`;
- `0 failed`;
- `0 errors`;
- original user run wall time: `98.84 s`;
- independent review reproduction reported `122.19 s`.

The suite includes a complete 1000-candidate generation/evaluation/archive vertical slice.

## Full regression gate

Full repository regression executed against exact implementation source `02482ad15a3dfa9a21a644c4c36756695277a6ef`:

- `1385 passed`;
- `4 warnings`;
- `0 failed`;
- `0 errors`;
- wall time: `323.78 s` (`0:05:23`).

The four warnings are the existing scikit-learn Gaussian-process `ConvergenceWarning` messages from `tests/test_smoke.py`; they are not MVR0 failures.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A1 — system-pack separation | PASS |
| A2 — reusable scientific-model separation | PASS |
| A3 — exact mixed design-space generation | PASS |
| A4 — system-owned gate | PASS |
| A5 — attributable scientific evaluation | PASS |
| A6 — analytic-model honesty | PASS |
| A7 — target-assessment separation | PASS |
| A8 — plural-success preservation | PASS |
| A9 — no hidden scalar winner | PASS |
| A10 — deterministic rerun | PASS |
| A11 — scientific-domain boundary | PASS |
| A12 — practical 1000-candidate vertical slice | PASS |
| A13 — frozen milestone protection | PASS |
| A14 — regression safety | PASS |

## Frozen milestone protection

The implementation diff from frozen D2 checkpoint `c597d6ef061f3fafa921035a2608d77a48050608` to tested MVR0 source `02482ad15a3dfa9a21a644c4c36756695277a6ef` adds only MVR0 preregistration, experiment harness, reusable fluids/aerodynamics code, multirotor System Pack code and MVR0 tests.

No existing D0/D1/D2/Scientific Twin frozen source semantics were modified.

## Explicit successor work

MVR0 does not attempt to add:

- user-language target parsing;
- target-driven AI orchestration;
- real motor/propeller/battery catalogs;
- catalog compatibility graphs;
- conditional variables;
- richer partial-success retention;
- recombination or mutation;
- adaptive generation;
- novelty search;
- multi-fidelity escalation;
- uncertainty propagation/calibration for the MVR0 model;
- forward-flight simulation;
- blade-element, CFD, FEA or control/stability validation;
- physical prototype validation;
- large-population archive-performance optimization.

These remain successor milestones pulled by future concrete experiments.

## Frozen outcome

MVR0 is **PASS / FROZEN**.

The milestone demonstrates that the frozen scientific/design stack can execute a concrete mixed-variable system-pack study from DesignSpace through D2 generation, candidate Scientific Twins, attributable scientific evaluation, explicit benchmark assessment and D1 Pareto/scoped archives for a 1000-candidate population while preserving scientific-status boundaries.

Future extensions must be introduced through successor milestones rather than rewriting MVR0 after observing downstream behavior.
