# Scientific Capability Completion Matrix

Generated from docs/project/scientific_capability_completion.json.
A capability is not complete because a class or file exists.

Active completion epic: engrt.numerical_foundations (research program)

Stages: FOUNDATION -> FUNCTIONAL -> EVIDENCE_BACKED -> PRODUCTION_READY.

| Capability | Declared | Computed max | Real data | Validation | UQ closure | Claims | Domain Pack | Next blockers |
|---|---|---|---|---|---|---|---|---|
| battery.thevenin_1rc | FUNCTIONAL | FUNCTIONAL | YES | NO | NO | NO | NO | independent_validation |
| battery.rint | FUNCTIONAL | FUNCTIONAL | NO | NO | NO | YES | YES | real_data, independent_validation, measurement_uq, benchmark_metrics |
| thermal.nafems_t3 | EVIDENCE_BACKED | EVIDENCE_BACKED | N/A | YES | YES | YES | NO | domainpack_integration |
| electrical.electrothermal | FUNCTIONAL | FUNCTIONAL | NO | NO | NO | YES | NO | real_data, calibration, independent_validation, measurement_uq |
| kinetics.cstr | FOUNDATION | FOUNDATION | NO | NO | NO | NO | NO | provenance_replay |
| claims.model_form_discrepancy | FUNCTIONAL | FUNCTIONAL | NO | YES | YES | NO | N/A | real_data, benchmark_metrics |
| platform.domain_pack | FUNCTIONAL | FUNCTIONAL | N/A | NO | YES | NO | N/A | independent_validation, benchmark_metrics |

## Research programs

| Program | Gate | Status | Requires | Next action |
|---|---|---|---|---|
| engrt.numerical_foundations | DV0 | MISSING | - | when the owner authorizes it, run the DV tables of docs/work/DEFERRED_VALIDATION.md; building the other gates does not wait for it |
| engrt.numerical_foundations | M1 | MISSING | - | build per the program contract (M1) now (build-first); decide the gate only on executed evidence |
| engrt.numerical_foundations | M2 | MISSING | M1 | build per the program contract (M2) now (build-first); the gate is decided only after M1 PASS |
| engrt.numerical_foundations | E1 | MISSING | - | build per the program contract (E1) now (build-first); decide the gate on executed WSL FEniCSx evidence |
| engrt.numerical_foundations | E2 | MISSING | - | build the two window sessions per the program contract (E2) now (build-first); decide the gate on an executed coupled run |
| engrt.numerical_foundations | E3 | MISSING | M1 | build per the program contract (E3) now (build-first); the gate is decided only after M1 PASS |

## Policy

A capability epic is finished only when its computed stage reaches PRODUCTION_READY; a research-program epic when every program gate is decided.
Until then, horizontal expansion into new capability foundations outside the epic's scope is paused unless an explicit exception is recorded.
A research program has gates, not maturity stages. A research result never promotes a capability.
Every MISSING gate must carry a concrete next action. NOT_APPLICABLE requires a rationale.

