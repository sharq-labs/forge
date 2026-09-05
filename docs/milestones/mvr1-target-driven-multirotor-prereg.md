# MVR1 - Target-Driven Multirotor Study V0.1 preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Starting frozen checkpoint: `f1409e474f554b17a83be6c73d5bdfdc8cefd0a5`

Local preregistration inspection basis: `02482ad` (`dev`), whose latest commit is `MVR0: add executable reference-study harness`. The requested starting checkpoint was not present in the local object database during preregistration, so this document records the requested checkpoint verbatim and freezes MVR1 against the inspected MVR0 implementation on `dev`.

## Purpose

MVR1 tests whether the frozen multirotor system pack can execute caller-supplied typed scientific study specifications without source-code changes for every new study.

MVR0 used one hard-coded reference study:

- payload mass: `0.50 kg`
- minimum hover endurance: `15 min`
- maximum takeoff mass: `3.00 kg`
- maximum disk loading: `120 N/m^2`

MVR1 covers only the typed/programmatic study-specification layer:

caller requirements -> typed multirotor study specification -> existing multirotor system pack -> D2 candidate generation -> candidate ScientificTwins -> scientific evaluation -> target assessment -> Pareto/archives -> scientific summary

Natural language input, LLM orchestration, adaptive optimization, discovery memory and recombination remain outside this milestone.

## Scientific questions

Q1. Can one frozen multirotor system pack execute different caller-supplied studies without source-code changes?

Q2. Does changing payload correctly change physical scientific outputs?

Q3. Can target thresholds change target pass/fail without changing scientific validity semantics?

Q4. Can the same candidate ScientificTwin be evaluated in more than one study while keeping exact result attribution?

Q5. Can Study A reproduce frozen MVR0 results exactly?

Q6. What happens under the stricter Study B?

Q7. Does the experiment expose a need for a future generic Study Contract, or is the system-specific contract sufficient for now?

Q7 is not pre-decided. MVR1 must let the experiment pull architecture rather than introducing a generic Core abstraction in advance.

## Architecture boundary

MVR1 may add system-specific code only where it is needed to support typed multirotor studies, expected under:

- `src/engcore/systems/aerospace/multirotor/`
- `experiments/multirotor_mvr1/`
- targeted MVR1 tests

The frozen general layers must not acquire multirotor semantics:

- `engcore.design`
- D0/D1/D2 contracts
- `engcore.scientific.twins`
- Scientific Core result/provenance contracts
- MVR0 source and experiment contracts

No `if system == "multirotor"` or equivalent product branching may be introduced in general design infrastructure.

MVR1 should introduce the smallest system-owned contract sufficient for this experiment. The expected shape is a `MultirotorStudySpecification` or equivalent under the multirotor system pack. Do not introduce a generic Core `StudySpecification` unless MVR1 evidence proves it necessary.

## Study specification contract

The MVR1 contract must explicitly separate two semantic classes.

### Operating condition

`payload_mass` is a study/operating condition. It changes the scientific computation itself:

- total mass
- hover thrust
- ideal induced power
- electrical hover power
- hover endurance
- disk loading
- margins derived from those values

It must not be treated as only a target threshold.

### Target requirements

The following are target/acceptance requirements:

- `minimum_hover_endurance`
- `maximum_takeoff_mass`
- `maximum_disk_loading`

They assess outputs after scientific evaluation. They must not alter Scientific Core validity, solver status, D1 `SelectionEligibility`, D2 candidate generation, candidate identity or Twin identity.

### Typed validation

Every study field must be a finite unit-compatible scientific quantity at the system boundary:

- `payload_mass` compatible with `kg`
- `minimum_hover_endurance` compatible with `s`
- `maximum_takeoff_mass` compatible with `kg`
- `maximum_disk_loading` compatible with `N/m^2`

All four values must be strictly positive. Construction must fail closed for missing values, non-finite magnitudes, incompatible units or non-positive values.

For deterministic identity and output, the specification must normalize to canonical units:

- `payload_mass`: `kg`
- `minimum_hover_endurance`: `s`
- `maximum_takeoff_mass`: `kg`
- `maximum_disk_loading`: `N/m^2`

## Exact Study A - MVR0 reproduction

Study A is a backward scientific reproduction of MVR0:

```json
{
  "payload_mass": {"magnitude": 0.5, "units": "kg"},
  "minimum_hover_endurance": {"magnitude": 900.0, "units": "s"},
  "maximum_takeoff_mass": {"magnitude": 3.0, "units": "kg"},
  "maximum_disk_loading": {"magnitude": 120.0, "units": "N/m^2"}
}
```

Because MVR0 has already been observed and frozen, the expected reproduction summary is a regression expectation, not a new hypothesis:

- accepted candidates: `1000`
- rejected proposals: `671`
- reference-target passes: `93`
- global Pareto members: `26`
- rotor distribution:
  - `4 -> 335`
  - `6 -> 333`
  - `8 -> 332`

Study A must use the same system pack, design space, deterministic D2 generation semantics, target assessment semantics and Pareto semantics as MVR0.

## Exact Study B - user-driven challenge

Study B is the caller-supplied challenge study:

```json
{
  "payload_mass": {"magnitude": 1.0, "units": "kg"},
  "minimum_hover_endurance": {"magnitude": 1500.0, "units": "s"},
  "maximum_takeoff_mass": {"magnitude": 4.0, "units": "kg"},
  "maximum_disk_loading": {"magnitude": 120.0, "units": "N/m^2"}
}
```

No pass count, Pareto count, winner or metric range is preregistered for Study B. Zero target-pass candidates is an allowed scientific outcome. The purpose is to observe how a changed caller-supplied operating condition and target set affect the exact same deterministic scientific design process.

## Study identity semantics

MVR1 must create deterministic system-owned study identity before evaluation.

The identity must be derived from a canonical payload that includes at least:

- schema name for the multirotor study specification
- schema version
- normalized operating conditions
- normalized target requirements
- frozen multirotor reference model id/version
- frozen design-space id/version
- frozen generation semantics when reporting a complete run summary

The canonical identity payload must be deterministic JSON with sorted keys, normalized units and no ambient process state. The study id must be a stable digest of that canonical payload, for example:

`multirotor-study-v0.1:sha256:<hex-digest>`

Any scientifically relevant study field change must change the study identity. Study A and Study B must have different study identities.

The study identity is not a candidate identity and not a Twin identity. It is the binding for the conditions and questions under which a candidate Twin was evaluated.

## Candidate/Twin/Study distinction

The candidate ScientificTwin represents the candidate vehicle design. It must not be recreated merely because target thresholds changed.

The same D2 candidate and candidate ScientificTwin may be evaluated under multiple studies:

- Twin #37 under Study A payload `0.50 kg`
- Twin #37 under Study B payload `1.00 kg`

These are the same candidate design and Twin identity, but their payload-dependent scientific results can differ. MVR1 must therefore bind every payload-dependent `ScientificResult` and every `DesignEvaluation` to the exact study identity that produced it.

MVR1 must not modify D1 only to add multirotor study semantics. Prefer a system-owned study binding in `ScientificResult.provenance.metadata`, `ScientificResult.metadata` and/or the MVR1 evaluation wrapper, with tests proving that cross-study substitution fails closed.

At minimum, result attribution must answer:

which exact normalized study specification produced this evaluation?

## Target-assessment semantics

For each valid scientific evaluation, MVR1 computes:

```text
mass_margin = maximum_takeoff_mass - total_mass
endurance_margin = hover_endurance - minimum_hover_endurance
disk_loading_margin = maximum_disk_loading - disk_loading
```

`reference_target_pass` is true iff all three margins are greater than or equal to zero.

Target pass/fail remains separate from:

- ScientificResult validity
- solver convergence/status
- validation level
- physical feasibility
- safety
- certification
- D1 `SelectionEligibility`

Successfully computed attributable evaluations remain D1 `ELIGIBLE` for comparison even when they fail the user target. This preserves partial successes and prevents target thresholds from erasing the comparison universe.

## Frozen model assumptions

MVR1 must reuse the frozen MVR0 reference assumptions. Do not improve the physics in this milestone.

Environment and system constants:

- air density: `1.225 kg/m^3`
- gravitational acceleration: `9.80665 m/s^2`
- usable battery fraction: `0.80`
- base hover efficiency: `0.72`
- auxiliary electrical load: `25 W`

Battery specific-energy classes:

- `conservative = 160 Wh/kg`
- `standard = 220 Wh/kg`
- `high = 280 Wh/kg`

Frame classes:

- `light = 0.35 kg`
- `standard = 0.55 kg`
- `rugged = 0.80 kg`

Other MVR0 benchmark coefficients remain unchanged:

- frame radius coefficient: `0.35 kg/m per rotor`
- fixed avionics mass: `0.18 kg`
- motor + ESC mass: `0.085 kg` per rotor
- rotor/propeller mass: `0.025 kg` per rotor
- guard mass: `0.035 kg` per rotor when enabled
- guard hover-efficiency multiplier: `0.94` when enabled

Reference hover physics remains:

```text
P_i = T^(3/2) / sqrt(2 * rho * A)
disk_loading = T / A
```

This remains a benchmark/reference model only.

## Frozen design-space semantics

MVR1 reuses the frozen MVR0 design space. Do not expand or tune the space after seeing MVR1 results.

Variables:

- `rotor_count`: integer `4..8`; multirotor gate admits only `{4, 6, 8}`
- `rotor_radius`: continuous `0.09..0.20 m`
- `battery_energy`: continuous `120..450 Wh`
- `battery_specific_energy_class`: categorical `conservative | standard | high`
- `frame_class`: categorical `light | standard | rugged`
- `prop_guards`: boolean

If a requested target is impossible inside this design space, zero target-pass candidates is a valid scientific outcome.

## Generation plan

MVR1 reuses deterministic D2 generation semantics:

- accepted candidate count: `1000`
- strategy: `halton_v1`
- generation: `0`
- attempt budget: `3000`
- no adaptive search
- no optimization-driven generation
- no CandidateCodec changes
- no recombination
- no discovery memory

The same generated candidate universe should be usable across Study A and Study B so that payload and target effects are isolated from candidate-generation changes.

## Pareto semantics

MVR1 preserves the frozen MVR0 global objective semantics:

1. minimize `total_mass`
2. maximize `hover_endurance`
3. minimize `hover_electrical_power`

There is no weighted score, no target-pass filtering before Pareto, no LLM ranking and no hidden normalization.

A target-failing candidate may legitimately be Pareto-optimal. Global Pareto construction uses the complete eligible evaluation universe for that study.

## CLI demonstration boundary

MVR1 should include a minimal executable user-facing experiment interface, conceptually:

```powershell
py -m experiments.multirotor_mvr1.run `
  --payload-kg 1.0 `
  --min-endurance-min 25 `
  --max-mass-kg 4.0 `
  --max-disk-loading 120
```

Exact CLI spelling may be chosen during implementation.

The CLI is only an input adapter. It must convert raw user input into typed scientific quantities before entering the multirotor scientific system. No scientific calculation may be performed by CLI parsing logic. No natural-language parsing or LLM interpretation is allowed.

The deterministic JSON output must include at least:

- study specification
- study identity
- generated candidate count
- rejected proposal count
- target-pass count
- Pareto member count
- rotor distribution
- metric ranges

The output must not call candidates physically validated designs.

## Acceptance criteria

A1. No frozen MVR0, D0, D1, D2 or ScientificTwin semantic modifications.

A2. Typed unit-safe study specification with finite, compatible, strictly positive quantities.

A3. Explicit distinction between operating condition (`payload_mass`) and target thresholds.

A4. Deterministic study identity from canonical normalized study payload.

A5. Exact study/result attribution for every payload-dependent scientific result.

A6. Cross-study result substitution fails closed.

A7. Study A reproduces frozen MVR0 result summary: `1000` accepted candidates, `671` rejected proposals, `93` target passes, `26` global Pareto members and rotor distribution `4 -> 335`, `6 -> 333`, `8 -> 332`.

A8. Study B executes with the same system pack without source edits or generation changes.

A9. Payload changes the scientific computation itself, including total mass, thrust, power, endurance and disk loading.

A10. Target thresholds remain separate from scientific validity.

A11. All scientifically valid attributable evaluations remain comparison-eligible regardless of target pass.

A12. Global Pareto uses the complete eligible evaluation universe.

A13. No weighted score, hidden target filtering, hidden normalization or LLM ranking.

A14. Zero Study-B target passes is allowed.

A15. Deterministic rerun produces identical summary for an identical study specification and generation plan.

A16. Study identities differ when scientifically relevant study fields differ.

A17. CLI/raw inputs are converted to typed quantities at the boundary.

A18. No physical-validation/status inflation.

A19. Targeted MVR1 tests pass.

A20. Full repository regression passes before freeze.

A21. MVR1 records runtime for the 1000-candidate studies; expensive exact archive construction is successor evidence, not a scientific failure.

A22. The same candidate/Twin identity can appear in Study A and Study B while each study's result identity and study binding remain distinct.

## Explicit non-claims

MVR1 must never claim that any result is:

- flight ready
- safe
- certified
- physically validated
- real-world proof
- a globally optimal aircraft
- a production vehicle recommendation

The model remains an analytic reference benchmark under frozen assumptions.

## Deferred work

The following are explicitly deferred:

- natural-language parsing
- LLM orchestration
- automatic System Pack selection
- adaptive candidate generation
- Bayesian optimization
- rich partial-success memory
- component elites
- compatibility graph
- recombination
- Generation 1
- novelty search
- failure knowledge
- next-experiment planner
- surrogates
- CFD
- blade-element models
- motor/ESC maps
- battery sag
- thermal model
- structures
- control/stability
- real hardware validation
- generic Study Contract unless MVR1 proves it necessary

## Performance

MVR0 revealed a P3 scaling issue: exact archive construction is `O(N^2)`.

MVR1 must not redesign archives. It must record runtime for the deterministic studies. If archive construction remains expensive, classify that as successor evidence, not as a failure of the MVR1 scientific question.

## Freeze rules

This preregistration is frozen before implementation.

MVR1 implementation may not weaken this document's acceptance criteria to make results pass. If implementation reveals that the contract is insufficient, the gap must be recorded as a deviation or successor milestone rather than silently changing frozen MVR0, D0, D1, D2 or ScientificTwin semantics.

Only this preregistration document is created in this turn. MVR1 implementation stops here until a later milestone.

## Architectural concern discovered during preregistration

The inspected MVR0 implementation already has a `MultirotorTargetSpec` that includes both `payload_mass` and acceptance thresholds. That worked for MVR0 because the study was hard-coded, but MVR1 must avoid preserving that name/semantics unchanged if it would continue to imply that payload is merely a target. The smallest rigorous MVR1 direction is a system-owned study specification that separates operating conditions from target requirements while preserving existing D1/Twin bindings and adding system-level study identity attribution.
