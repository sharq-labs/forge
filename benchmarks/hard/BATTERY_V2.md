# Battery benchmark V2

Battery V2 is the current benchmark contract for the production Battery
vertical. It supersedes `cases_battery/` + `results_battery.json` as a
quality measurement; those files remain historical evidence of the CAP-02
transition.

## Why a new version

Battery V1's answer key predates three production facts now enforced by the
runtime:

1. corrected coulomb counting removes charge as `I*dt/(eta*Q)`;
2. a declared pulse is screened at its own duration/current and can move the
   binding voltage cutoff;
3. the coupled thermal model now receives and is assessed against an explicit
   applicability declaration during every executed march step.

Editing V1's expected labels in place would destroy the evidence that exposed
those changes. V2 therefore produces a new case-set identity.

## Independent truth rules

`generate_battery.py` remains stdlib-only and does not import `engcore`.
For V2 it independently recomputes the continuous battery conditions plus:

- `pulse_polarization_unmodelled_fraction =
  min(f, 1-f)`, `f=1-exp(-t_pulse/tau)`;
- pulse terminal voltage from `OCV(z)-I_pulse*R_int`;
- pulse cutoff shift
  `z_cut(I_pulse)-max(z_cutoff_declared,z_cut(I_continuous))`;
- the corrected coulomb-counting trajectory.

The CAP-02 polarization condition is a conservative screen. Crossing its
ceiling makes the truth verdict `INSUFFICIENT_EVIDENCE`; it is not rewritten
as a physical contradiction.

## Complete coupled verdict

Every V2 case includes `thermal.applicability`. The declaration is built so
the forced-convection correlation reproduces the declared cell-to-ambient
conductance, while geometry, radiation, material and excursion conditions have
explicit evidence. The scorer therefore evaluates Battery V2 from
`report.verdict` over battery **and** lumped-thermal models.

Battery V1 remains reproducible through the legacy scoped path only when a
case does not carry `benchmark_version: 2`.

## Reproduce

```bash
cd benchmarks/hard
python generate_battery.py \
  --out cases_battery_v2 \
  --index index_battery_v2.json

python score_hard.py \
  --src ../../src \
  --cases cases_battery_v2 \
  --results results_battery_v2.json \
  --workers 4
```

Do not publish a V2 percentage until those commands have produced the V2 case
set and score record. A generated score belongs to the exact case-set digest
written beside it.
