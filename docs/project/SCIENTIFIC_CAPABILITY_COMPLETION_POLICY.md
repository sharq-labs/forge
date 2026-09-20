# Scientific Capability Completion Policy

Forge now distinguishes **having a foundation** from **having a complete capability**.

## Stages

1. **FOUNDATION**  
   Scientific definition, applicability boundary, implementation, and regression tests exist.

2. **FUNCTIONAL**  
   The capability additionally executes end to end, is verified, has explicit failure behavior, and is replay/provenance-aware.

3. **EVIDENCE_BACKED**  
   The functional capability additionally has the required real/external evidence path, calibration when applicable, independent validation, measurement uncertainty when applicable, and quantitative benchmark metrics.

4. **PRODUCTION_READY**  
   Remaining applicable uncertainty channels are closed, model discrepancy is handled where relevant, claims/planning integration is complete, the domain is integrated through the Domain Pack contract when domain-owned, and documentation is complete.

A stage is cumulative. A capability cannot skip an earlier incomplete gate.

## Gate semantics

- **PASS** requires repository evidence.
- **MISSING** requires a concrete next action.
- **NOT_APPLICABLE** requires a rationale. It must never mean "not implemented yet" or "unknown".

The machine-readable source of truth is:

`docs/project/scientific_capability_completion.json`

The human matrix is generated from it:

`docs/SCIENTIFIC_CAPABILITY_MATRIX.md`

The checker is:

`python -m tools.capability_maturity`

To regenerate the matrix after a reviewed ledger change:

`python -m tools.capability_maturity --write`

## Active epic rule

The current active epic is **battery.thevenin_1rc**.

Until its computed stage reaches **PRODUCTION_READY**, horizontal expansion into new capability foundations is paused by policy. Work on defects, stabilization, verification infrastructure, or prerequisites of the active epic is still allowed. Starting a genuinely new capability foundation requires an explicit reviewed exception in the PR rationale.

This is intentionally a repository-development policy, not scientific evidence and not a verdict rule.

## Why this exists

The anti-pattern being prevented is:

Feature -> foundation -> tests -> merge -> move to another feature

The required pattern is:

Capability -> foundation -> functional execution -> evidence -> UQ/benchmark closure -> production integration -> done

Small PRs are still encouraged. The restriction is on abandoning the active epic, not on forcing all work into one large pull request.
