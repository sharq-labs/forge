# Independent M1B scientific architecture static review

Reviewer /root/m1b_review, read-only forge-scientific-reviewer, 2026-10-18.
Applied .claude/skills/forge-scientific-review/SKILL.md. Architecture reviewed before
code. Final source/test review after corrections. No reviewer execution/imports/tests.
Static PASS is not scientific verification, validation or certification.

## A. Scope

Read M1B decision, vertex_state.py, test_m1b_vertex_dual_state.py, parent lineage/state
transfer, A-3 mapping/semantics, bulk storage and existing source provenance contracts.

## B. Authority boundary

Normalized source bytes establish artifact binding only. Caller KnowledgeSource labels
do not grant applicability, measured status, validation or evidence. Versioned adapter
admission grants bounded state operations only.

## C. Applicability and model use

Explicit placement, exact semantic meanings, support versions and storage laws govern
admission. Unsupported vertex interpolation, affine quantities, missing provenance and
underdetermined reconstruction refuse. No thermal-specific law in generic kernel.

## D. Verification / validation

Receipts separate constructed integral arithmetic from pointwise accuracy and physical
validation. No transient solver or M1 completion claim. IMPLEMENTED / UNVERIFIED /
UNCERTIFIED; authored fixtures do not count as solver-backed verification.

## E. Uncertainty

Derived conversions/transfers retain UNKNOWN. Missing channels do not become zero;
source classification cannot upgrade UNKNOWN.

## F. Evidence / context / policy

Storage conversion requires matching contexts. No evidence-admission or risk-policy
authority added. Legacy transient refusal intact; versioned state-only admission explicit.

## G. Provenance / replay

Local issuance, content verification and recursive ancestry protect records. Audit
exports cannot grant authority. Mesh changes invalidate fields/coefficients/resources;
unsafe post-change failure poisons adapter. External resources/concurrency unsupported.

## H. Adversarial test coverage

Written: geometry/counts, unequal dual supports, density/amount distinction, conservation,
explicit storage/discontinuities, exact semantic/context mismatch, provenance substitution,
missing authority, stale/cloned records, real corrupt/missing bytes, false residual,
unit conversion, cache/history invalidation and unsafe transition. All NOT RUN.

## I. Findings

| Severity | File / symbol | Smallest counterexample | Correction / regression |
| --- | --- | --- | --- |
| MEDIUM, resolved | vertex_state.py::convert_storage | Density meanings sharing one conserved quantity could use same law | Exact optional density semantics in law identity and normalized bytes; test_storage_requires_exact_declared_density_meaning_not_only_same_amount |
| MEDIUM, resolved | vertex_state.py::_require_parents | Delete old support issuance after deriving and transferring a current state; read previously succeeded | Recursively require supports/geometry/mesh lineage and dual/primal invalidation issuance; six missing-authority cases |

Both corrections inspected. No unresolved scientific-authority/evidence-integrity defect
found in bounded scope. Physical source qualification, nonlinear storage, variable-area
quadrature, durable recovery and transient solving remain outside adapter guarantee.

## J. Verdict

PASS
