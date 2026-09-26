# Engineering output layer (BIG 13)

`src/engcore/engineering/` (non-Core, registered in `tests/test_core_api_layering.py`) sits above `engcore.system_runtime`. It
executes nothing, solves nothing, and adds no trust vocabulary. It turns a BIG 12 run into something an engineer can read,
compare with a reference, and hand to someone else.

```text
SystemRunResult (BIG 12) ──┬─> ConstraintAssessment / ConservationAssessment (BIG 12)
                           ├─> trust_handoff -> CredibilityVerdict            the ONLY scientific status shown
                           ├─> VerificationLadder (levels 1-7)               report vocabulary, not an authority
                           ├─> ReferenceRecord / PredeclaredCriterion / ReferenceComparison
                           └─> EngineeringSummary  -> run bundle (files + manifest) -> flagship report
```

## Reuse map

| Need | Reused | Added here |
|---|---|---|
| scientific status | `credibility.CredibilityVerdict` via `trust_handoff` | nothing: the summary prints the existing verdict |
| reference kinds | `scientific.oracles.OracleKind` (analytic / benchmark / experimental) | `ReferenceRecord`: provenance, applicability envelope, `role`, content identity |
| tolerance comparison | - | `PredeclaredCriterion`, `compare_to_reference`; a comparison against a reference that does not apply is `not_applicable` (judges nothing) |
| provider comparison | `providers.compare_providers` (`solver_corroboration_not_validation`) | `EvidenceLink.of_provider_comparison` |
| run identity | BIG 12 request / plan / result digests | `write_bundle` / `verify_bundle` |
| fields | BIG 7 `SpatialMesh` / `SpatialField` | `write_vtu` (presentation artifact, not evidence) |

## Rules enforced in code

* A ladder level is REACHED only by evidence links whose outcome is `met`, that are not post hoc, and whose class fits the level
  (1 contract integrity, 2 conservation residual, 3 analytic-limit or reference-data-consistency comparison, 4 convergence,
  5 solver corroboration, 6 numerical-benchmark comparison, 7 experimental comparison). Solver agreement cannot reach 6 or 7; a
  numerical benchmark cannot reach 7. A post-hoc reading may be recorded beside a level that is NOT reached and never on one that is.
  The ladder cannot verify that a link's digest belongs to a real record; flagships build links from real records.
* Level 1 (`contract_integrity_entry`) is reached only if neither the preflight nor the run was REFUSED, and it names the checks that
  were deferred to the solved state.
* A reference's applicability is `within` only if every declared envelope condition is known and inside; a missing condition or a
  missing envelope is `unknown`.
* A compared difference is a non-negative magnitude; a signed value would read as `met`.
* An `UncertaintyStatement` states model discrepancy as UNKNOWN / NOT QUANTIFIED (there is no quantified-discrepancy record in this
  layer), and must name the UNKNOWN inputs whenever any output's uncertainty is UNKNOWN.
* A run bundle contains only artifacts a SUCCEEDED node's receipt references (name and sha256); `verify_bundle` re-hashes every file,
  re-derives the result identity, and re-checks the summary, every reference and every artifact against it, so a regenerated manifest
  cannot launder an edited file. The manifest is unkeyed: this detects accidental and casual edits, not an adversary who rebuilds the
  whole bundle consistently.

## BIG 12 generalizations BIG 13 needed (each minimal, each tested in `tests/test_system_runtime_big13_additions.py`)

* `NodeCall.execution_identity`: the run-independent identity of the executing node, equal to what a consumer sees as
  `InputValue.producer_identity`, so an authority can key side data (a field held in a bulk store) to exactly its own execution.
* `MultiphysicsAuthority(extractors=, artifacts=)`: scalars derived from a coupled run's own histories (uncertainty stays UNKNOWN) and
  artifacts referenced by digest.
