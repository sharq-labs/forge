# A-3: declared field-kind mapping proposal (separate follow-up)

Status: PROPOSED / NOT IMPLEMENTED / NOT RUN. This document authorizes no mapping
change. A-1/A-2/A-13 typed scalar work does not close A-3 or permit typed field execution.
Core review is required before changing shared FieldMapper semantics or deciding M2/E2.

## Unequal-cell counterexample, preregistered before implementation

One-dimensional source intervals [0,1], [1,4] have measures (1,3); target
intervals [0,2], [2,4] have measures (2,2). Overlap matrix, source rows/target columns:

```text
O = [[1, 0],
     [1, 2]]
```

Conserved integrated source amounts Q=(2,6) sum to 8. The correct target amounts
are (4,4): Q'_j = sum_i Q_i O_ij / source_measure_i. Feeding Q into today's density
formula instead gives (4,6), whose sum is 10. That wrong answer still conserves the
measure-weighted integral 20, demonstrating why a small remap residual cannot establish
that the declared physical quantity was conserved.

For conserved source density rho=(2,2), rho'_j = sum_i rho_i O_ij / target_measure_j
gives (2,2). Its measure-weighted integral is 8 on both meshes. Density and integrated
amount require distinct rules even on exactly the same geometry.

An intensive state (for example values 300 and 400) is transferred by a declared
consistent interpolation, not promoted to a conserved quantity. An overlap average
would yield (350,400) here, but its measure integral is not a physical conservation
claim. For conduction, conserved energy requires the declared material/storage law;
Core must not infer energy from temperature, kelvin units or a heat capacity default.

## Proposed generic contract

- Field kind: conserved density, conserved integrated amount or intensive. Bind it to
  existing FieldDefinition/support identity through an explicitly versioned record;
  do not overload semantic role strings or infer it from units/location/components.
- Density declares the geometric measure unit and conserved quantity; integrated amount
  declares the conserved quantity itself. Rate and surface-flux semantics are explicit,
  with no automatic time integration or normal inference.
- Apply scalar/vector component rules only in an admitted common frame. Normal fluxes
  need a separately applied orientation/projection contract; component conservation alone
  does not establish momentum or equal-and-opposite interface conservation.
- Admit complete source AND target coverage, positive finite measures, known topology
  and supported cell geometry before transfer. Refuse partial coverage, affine-scale
  conserved inputs, stale mesh/field identity and unsupported tensor/frame semantics.
- Record support versions, declared kind, actual operator, source/target totals, residual
  and units. Residuals remain diagnostics, never numerical error bounds or physical validation.
- Mesh changes invalidate fields, transfer operators and coupling acceleration history.
  Coarsening requires recorded lineage; no nearest-match topology or state repair.

## Compatibility and execution plan for the next bounded task

1. Decide versioned shared field-kind representation, old-reader refusal and whether legacy
   conservative_cell remains explicitly density-only or refuses until migrated.
2. Review material graph/field/operator digest changes, cached operators, adaptive histories,
   every FieldMapper caller, scalar/vector/component behavior and frozen/certified scope.
3. Implement only declared scalar 1D overlap transfer first; M1 may use its local declared
   kind. Promote shared 2D FieldMapper/M2 behavior only after the compatibility review.
4. Write and separately authorize tests for the exact unequal-cell examples above, reversed
   remap, constant preservation, signed zero-total quantities, nonuniform splits/coarsening,
   incomplete coverage, affine units, identity tampering and stale supports/history.
5. Add 2D unequal-area and vector-frame tests before extending M2/E2. Record numerical
   refinement separately from conservation; do not choose tolerances after seeing results.

Open owner/design decisions: field-kind schema and legacy admission policy; density measure
dimension; sign/normal projection ownership; supported vector/tensor scope; separate numerical
error estimation. No missing uncertainty or model discrepancy becomes zero.
