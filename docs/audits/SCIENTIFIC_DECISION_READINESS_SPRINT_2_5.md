# Scientific Decision Readiness — Sprint 2.5: NAFEMS T3 Execution Vertical

## Goal

Connect the repository-reviewed NAFEMS P18.T3 external authority from Sprint 2
to a real Forge execution path, then carry the earned validation level through
the credibility and SRIA decision layers.

This sprint is intentionally narrow. It proves one complete scientific path
before adding more domains or more benchmark families.

## Scientific case

The executable path implements the revised NAFEMS T3 one-dimensional transient
heat-conduction benchmark:

- uniform bar length: 0.1 m;
- width/depth: 0.01 m;
- conductivity: 35 W/(m K);
- density: 7200 kg/m^3;
- specific heat: 440.5 J/(kg K);
- initial temperature: 0 degC;
- left boundary: 0 degC;
- right boundary: 100 sin(pi t / 40) degC;
- zero lateral heat flux;
- zero internal heat generation;
- target point: x = 0.08 m;
- target time: t = 32 s;
- published target: 36.6 degC.

Internally absolute temperatures are represented in kelvin.

## Execution implementation

New domain module:

`src/engcore/domains/thermal_models/nafems_t3.py`

It owns:

- a benchmark-specific `ScientificModelDefinition`;
- an exact operating-point validity domain;
- a Crank-Nicolson finite-difference execution;
- provenance containing the complete T3 operating point;
- explicit UNKNOWN output uncertainty;
- a refinement-sensitivity check;
- the repository-pinned external-oracle comparison.

The benchmark physics is intentionally not caller-configurable. Only numerical
resolution is configurable.

This prevents a caller from changing material properties, boundary conditions
or the probe location while still asking for NAFEMS T3 authority.

## Numerical method

The solve uses:

- second-order central differences in space;
- Crank-Nicolson time integration;
- banded linear solve through `scipy.linalg.solve_banded`.

Default reported resolution:

- 160 spatial cells;
- 640 time steps.

Companion sensitivity resolution:

- 80 spatial cells;
- 320 time steps.

At these settings the implementation produces approximately:

- reported result: 36.60014 degC;
- companion result: 36.59123 degC;
- absolute refinement delta: 0.00891 K.

The refinement gate requires the companion delta to remain below 0.025 K,
half of the 0.05 K recording-precision envelope used by the external oracle.

The refinement check deliberately establishes **no ValidationLevel**. It is a
numerical sensitivity finding, not a substitute for an external benchmark.

## External validation

After the ScientificResult is built, the repository-pinned NAFEMS T3 oracle
compares the result at the exact operating point.

Only that check may establish:

`ValidationLevel.BENCHMARK_VALIDATED`

The result does not label a linear-system residual or a refinement difference
as external validation.

## Layering

The domain layer returns only `ScientificResult`.

The MCP boundary owns credibility assembly in:

`src/engcore/mcp/nafems_t3.py`

This preserves the dependency direction:

`Scientific domain -> ScientificResult -> MCP consumer -> SRIA`

The scientific domain does not import SRIA or MCP evidence machinery.

## End-to-end path

The executable path is now:

```
NAFEMS T3 fixed scientific problem
        |
        v
Crank-Nicolson thermal execution
        |
        v
ScientificResult
        |
        +--> refinement sensitivity
        |
        v
Repository-trusted NAFEMS T3 oracle
        |
        v
BENCHMARK_VALIDATED
        |
        v
CredibilityEvidenceReport
        |
        v
SRIA Evidence
        |
        v
CredibilityReportCritic
        |
        v
Arbiter
        |
        v
Charter requirement:
BENCHMARK_VALIDATED
```

## Decision semantics

The MCP wrapper requires `BENCHMARK_VALIDATED` when assembling the
credibility report.

The end-to-end test then creates a campaign charter that also requires
`BENCHMARK_VALIDATED`.

The SRIA bridge derives the QOI from the credibility report. A registered
`CredibilityReportCritic` exposes the level to the Arbiter, and the confidence
obligation is satisfied only because the trusted oracle check actually attained
that level.

The SRIA test uses an explicit `CONSTRAINED_PRIOR` model-discrepancy
declaration. It does not declare zero model-form discrepancy and it does not
claim that Forge has quantified model-form uncertainty.

## Tests

New test module:

`tests/domains/thermal_models/test_nafems_t3_vertical.py`

It pins:

1. the computed T3 target within the repository-reviewed oracle envelope;
2. model applicability at the exact benchmark point;
3. external benchmark validation is attained;
4. refinement sensitivity is separate from the external level;
5. numerical grids must preserve the x=0.08 m probe node;
6. the credibility report requires and attains BENCHMARK_VALIDATED;
7. the level reaches SRIA and satisfies the Arbiter's charter obligation.

## What this proves

Once the tests and certification gates pass, Forge has one complete,
repository-pinned demonstration of:

**execute -> verify numerics -> compare external benchmark -> earn external
validation -> form evidence -> satisfy an explicit decision requirement.**

It does not prove universal thermal validity, experimental validation, or
quantified uncertainty. Those claims remain outside this sprint.
