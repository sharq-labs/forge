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
| reference kinds | `scientific.oracles.OracleKind` (analytic / benchmark / experimental) | `ReferenceRecord`: provenance, applicability envelope, `role`, comparable quantities, content identity |
| tolerance comparison | - | `PredeclaredCriterion`, `ReferenceComparison` (DERIVED from reference + criterion + stated conditions + value), `compare_to_reference`; a comparison against a reference that does not apply is `not_applicable` (judges nothing) |
| provider comparison | `providers.compare_providers` (`solver_corroboration_not_validation`) | `EvidenceLink.of_provider_comparison` |
| run identity | BIG 12 request / plan / result digests | `write_bundle` / `verify_bundle` |
| fields | BIG 7 `SpatialMesh` / `SpatialField` | `write_vtu` (presentation artifact, not evidence) |

## Rules enforced in code

* "Pre-registered" means: listed in `flagships/forge_flagships/data/predeclared_criteria.json` and pinned by a test. Git cannot show that a
  criterion preceded the first run of a flagship (the first commit was made after it); that ordering rests on `docs/work/PROGRESS.md`.
* A ladder level is REACHED only by evidence links whose outcome is `met`, that are not post hoc, and whose class fits the level
  (1 contract integrity, 2 conservation residual, 3 analytic-limit or reference-data-consistency comparison, 4 convergence,
  5 solver corroboration, 6 numerical-benchmark comparison, 7 experimental comparison). Levels 5, 6 and 7 additionally need a link OF
  the matching kind (a provider comparison; a reference comparison), not only the class string. Solver agreement cannot reach 6 or 7; a
  numerical benchmark cannot reach 7. A post-hoc reading may be recorded beside a level that is NOT reached and never on one that is.
* Every evidence link carries the record it names, and its digest covers the link's kind, classification and outcome as well as the
  record. A ladder is rebuilt from its serialized form with every guard running again.
* A `ReferenceComparison` has no settable outcome, applicability, kind or classification: they are derived from the reference, the
  criterion, the conditions the flagship states and the compared difference (a difference is converted as a SPREAD, so a 5 K difference
  against a 1 degC tolerance is not met). A comparison rebuilds from its bundled reference; a criterion may only bind to a quantity the
  reference declares comparable.
* `build_summary` requires every ladder link that claims to be a reference comparison to BE one of the supplied comparisons, every
  supplied comparison to be cited by the ladder (a not-met comparison cannot be shipped and left out), and every comparison's reference
  to be supplied.
* Level 1 (`contract_integrity_entry`) is reached only if neither the preflight nor the run was REFUSED; it names the checks deferred
  to the solved state and any node REFUSED on the solved state.
* A reference's applicability is `within` only if every declared envelope condition is known and inside; a missing condition or a
  missing envelope is `unknown`. The envelopes of the reference records in this repository are AUTHORED by the flagships (stated in each
  record), not read from the sources.
* An `UncertaintyStatement` states model discrepancy as UNKNOWN / NOT QUANTIFIED (there is no quantified-discrepancy record in this
  layer), and must name the UNKNOWN inputs whenever any output's uncertainty is UNKNOWN.
* A run bundle contains only artifacts a SUCCEEDED node's receipt references (name and sha256). `verify_bundle` re-hashes every file and
  RE-DERIVES: the result and request (their own digests), the plan, the scientific status (`trust_handoff`), `summary.txt` (re-rendered
  from `summary.json`), the summary's key outputs / execution / providers against the result, level 1 (from the result's own preflight),
  every reference comparison (rebuilt from its bundled reference), every provider comparison (two different providers, executions the result recorded, a post-hoc flag
  that matches its classification, an outcome that follows from its maximum difference for a purely absolute tolerance), the uncertainty statement, the trace, and the ladder
  (every guard; every link digest).

## What the bundle check does NOT establish

* Evidence for levels 2-4 that is not a comparison (a conservation residual, a mesh or window study, an equilibrium diagnostic) and the
  constraint and conservation lines are JUDGMENTS the flagship recorded with their records; they cannot be re-derived from the bundle.
* The manifest is unkeyed. Someone who consistently rewrites `summary.json`, `summary.txt` and the manifest together produces a bundle
  that verifies. Authenticity needs the `bundle_digest` recorded somewhere its author cannot edit (a commit, a signed report).
* The INPUTS of a reference comparison (compared difference, stated conditions, tolerance, `compared_identity`) are stated by the flagship; the bundle re-derives
  what follows from them, not the inputs. A relative-tolerance provider comparison cannot be re-derived from its aggregate and is refused.
* The free-text notes and the level notes are recorded prose, bound to the record only through the re-rendered text.
* A reference no comparison cites is bound only by the manifest.
* The exact-limit, mesh-study and window-study requests behind levels 3 and 4 are separate BIG 12 requests; their records are inside the
  summary but their provider bindings are not compared with the main request's.

## BIG 12 generalizations BIG 13 needed (each minimal, each tested in `tests/test_system_runtime_big13_additions.py`)

* `NodeCall.execution_identity`: the run-independent identity of the executing node, equal to what a consumer sees as
  `InputValue.producer_identity`, so an authority can key side data (a field held in a bulk store) to exactly its own execution.
* `MultiphysicsAuthority(extractors=, artifacts=)`: scalars derived from a coupled run's own histories (uncertainty stays UNKNOWN) and
  artifacts referenced by digest.
