# Independent M1C scientific architecture static review

2026-10-18. Reviewer /root/m1c_review, read-only forge-scientific-reviewer.
Applied .claude/skills/forge-scientific-review/SKILL.md. Architecture reviewed before
code; final implementation/tests reread after corrections. No reviewer commands,
imports, numerical execution or tests. Static PASS is not scientific evidence.

## A. Scope

M1C decision, new thermal implementation/tests, M1B adapter, materials/provider
contracts, Core Freeze and model-discovery guard.

## B. Authority boundary

Numerical execution separate from evidence. Caller declarations, normalized source
artifacts and admission enums grant neither validation nor model applicability.

## C. Applicability and model use

Model applicability UNKNOWN. Physical-input mode refuses assumed properties;
synthetic assumptions retain classification. Unsupported material dependence and
multiphase cases refuse. Domain thermal instance does not modify generic kernel.

## D. Verification / validation

Half-volume storage retained with Dirichlet reservoir reactions explicitly distinguished
from measured flux. Positive C/dt regularizes both-Neumann transient. Manufactured
comparisons are mathematical verification designs, NOT RUN; no full M1 or M1D claim.

## E. Uncertainty

Output uncertainty UNKNOWN, conditioning unresolved. Algebraic residuals do not
become error bounds, certification or validation.

## F. Evidence / context / policy

Context binds initial state, material declarations, geometry, clock and formulation.
No evidence/verdict path or maturity promotion; admission does not become evidence.

## G. Provenance / replay

Material source payload hashes/resolution, exact storage identity/live bytes,
provider build and current state checked. Failed attempts poison continuation.
Audit exports grant no restored solver/lineage authority. No M1D rollback guarantee.

## H. Adversarial test coverage

Written independent external balances, half-volume reactions, unequal geometry,
series/contact resistance, manufactured refinement, material/source/time refusal,
stale state, false residual/problem substitution and partial publication poisoning.
All NOT RUN. No executed order, convergence or conservation result is claimed.

## I. Findings

| Severity | File/symbol | Smallest counterexample | Correction / test |
| --- | --- | --- | --- |
| HIGH, resolved | conduction1d_transient_fv.py::TransientConduction1D._step | Huge interior storage RHS hides wrong endpoint in global norm; reaction closes endpoint balance tautologically | Power-scaled rows, row-wise power residual and explicit endpoint temperature tolerance; test_wrong_dirichlet_cannot_hide_behind_large_storage_norm |
| HIGH, resolved | same module::_configuration/_guard | Replace storage handle with current issued 2*C law; published energy disagrees with assembly accounting | Exact storage identity, actual J/K coefficient bytes and initial clock bound; test_replacement_storage_or_initial_clock_cannot_change_energy_and_boundary_policy |
| MEDIUM, resolved | test_missing_boundary_source_and_forcing_provenance_refuse | Helper default turns left=None into valid zero flux | Direct missing-boundary step invocation |

Corrections inspected, no remaining scientific-authority/evidence-integrity defect
identified within implemented scope. Integration hold stays explicit: model census
pin19 at tests/test_core_guards.py:199,534 versus new model20. No count/pin edited.
This static review does not establish integration readiness or scientific verification.

## J. Verdict

PASS
