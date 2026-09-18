# Scientific Decision Readiness — Sprint 2: Trusted Scientific Authority

## Goal

Turn external validation from a representational capability into repository-owned
scientific authority without letting a caller grant itself validation.

Sprint 2 deliberately separates two questions:

1. **Is this external evidence trusted and content-pinned?**
2. **Does a Forge solver actually solve the same problem and reproduce it?**

This sprint closes (1) for the first curated benchmark. It does not claim (2)
for the existing frozen conduction1d solver, because that solver implements a
different initial/boundary-value problem.

## First admitted benchmark: NAFEMS P18.T3

The repository now carries one reviewed external thermal benchmark record:

- oracle id: `nafems.p18.t3.transient_heat_1d`
- version: `1`
- kind: `BENCHMARK_DATASET`
- target: temperature at the declared probe and end time
- published target: 36.6 degC, stored as 309.75 K
- target location: 0.08 m
- end time: 32 s
- bar length: 0.1 m
- conductivity: 35 W/(m K)
- density: 7200 kg/m^3
- specific heat: 440.5 J/(kg K)
- boundary law parameters and zero lateral/internal heat declarations are part
  of the operating-point identity.

Reviewed public reproductions:

- NAFEMS P18.T3, *The Standard NAFEMS Benchmarks*, Rev. 3 (1990).
- Altair SimSolid verification case SS-V:3070.
- MOOSE NAFEMS T3 verification example.

The public target is reported to one decimal degree Celsius. The oracle stores
an absolute tolerance of +/-0.05 K as a **recording-precision envelope**. This
is not represented as an original NAFEMS acceptance criterion.

## Authority model

The domain evidence pack is:

`src/engcore/domains/thermal_models/nafems_t3_oracle.py`

The repository-owned authority pin remains in:

`src/engcore/scientific/oracles.py`

These are intentionally separate.

The domain file contains the scientific content. The Core registry contains a
static declaration of the exact:

- oracle id/version;
- kind;
- SHA-256 evidence digest;
- bibliographic reference.

The registry does not compute its pin from the domain module at import time.
That would make a content edit silently update its own authority.

Production callers still have no registration API.

## Operating-point closure

The oracle observation declares the complete quantitative point needed to
identify the benchmark case. `OracleEvidenceSet.compare` already enforces:

- stated comparison conditions must match the evidence conditions;
- the prediction must name a ScientificResult;
- the result must carry the compared metric;
- the result provenance must carry the same operating-point inputs;
- a contradiction yields NOT_RUN, not a weaker PASS;
- missing authority withholds the validation level.

Therefore a numerically identical temperature from another material, time,
location or boundary declaration cannot earn P18.T3 validation.

## Content-tamper closure

Authority is over exact content, not an oracle name.

Tests pin that:

- changing the target while retaining the trusted identity is rejected by
  content-digest verification;
- rebuilding the same oracle id/version with a changed tolerance creates a new
  digest and therefore has no authority;
- an unreviewed record may still be compared, but it earns no validation level.

## Validation semantics

Only an exact, repository-pinned benchmark comparison at the exact bound
operating point may establish:

`ValidationLevel.BENCHMARK_VALIDATED`

The benchmark does **not** establish:

- experimental validation;
- validation for arbitrary thermal problems;
- validation for the existing normalized-sine conduction1d problem;
- a universal accuracy threshold;
- uncertainty quantification.

## Why the current conduction1d solver is not connected to T3

The frozen Forge conduction1d benchmark solves a normalized diffusion problem
with:

- homogeneous zero Dirichlet ends;
- a single-mode sinusoidal initial condition;
- a dimensionless field.

NAFEMS T3 instead uses a physical-temperature transient bar with a prescribed
time-varying boundary temperature.

Sharing the words "1D transient conduction" is not scientific equivalence.
Sprint 2 refuses to bridge them.

A later domain-integration change may add a T3-compatible problem/solver path.
Only that path may attempt to earn the benchmark level.

## Tests

`tests/oracles/test_trusted_nafems_t3.py` verifies:

1. content digest is review-pinned;
2. repository authority recognises the exact record;
3. exact target + exact point earns BENCHMARK_VALIDATED;
4. wrong stated operating point earns no level;
5. correct stated point cannot hide a result computed at another point;
6. target tampering is rejected;
7. same oracle name/version with changed content has no authority.

Sprint-0 finding SDR-06 is changed from expected-failure to a required passing
invariant.

## Exit status

Sprint 2 closes the **authority** half of SDR-06.

The first production-trusted external benchmark now exists. Forge still must
add a scientifically matching domain execution path before it can claim that
its own thermal solver has passed NAFEMS T3.
