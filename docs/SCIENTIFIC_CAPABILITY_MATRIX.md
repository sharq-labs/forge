# Scientific Capability Completion Matrix

Generated from docs/project/scientific_capability_completion.json.
A capability is not complete because a class or file exists.

Active completion epic: battery.thevenin_1rc

Stages: FOUNDATION -> FUNCTIONAL -> EVIDENCE_BACKED -> PRODUCTION_READY.

| Capability | Declared | Computed max | Real data | Validation | UQ closure | Claims | Domain Pack | Next blockers |
|---|---|---|---|---|---|---|---|---|
| battery.thevenin_1rc | FOUNDATION | FOUNDATION | NO | NO | NO | NO | NO | execution, provenance_replay |
| battery.rint | FUNCTIONAL | FUNCTIONAL | NO | NO | NO | YES | YES | real_data, independent_validation, measurement_uq, benchmark_metrics |
| thermal.nafems_t3 | EVIDENCE_BACKED | EVIDENCE_BACKED | N/A | YES | YES | YES | NO | domainpack_integration |
| electrical.electrothermal | FUNCTIONAL | FUNCTIONAL | NO | NO | NO | YES | NO | real_data, calibration, independent_validation, measurement_uq |
| kinetics.cstr | FOUNDATION | FOUNDATION | NO | NO | NO | NO | NO | provenance_replay |
| claims.model_form_discrepancy | FUNCTIONAL | FUNCTIONAL | NO | YES | YES | NO | N/A | real_data, benchmark_metrics |
| platform.domain_pack | FUNCTIONAL | FUNCTIONAL | N/A | NO | YES | NO | N/A | independent_validation, benchmark_metrics |

## Policy

The active epic is finished only when its computed stage reaches PRODUCTION_READY.
Until then, horizontal expansion into new capability foundations is paused unless an explicit exception is recorded.
Every MISSING gate must carry a concrete next action. NOT_APPLICABLE requires a rationale.

