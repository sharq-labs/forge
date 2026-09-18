# Scientific Decision Readiness — Sprint 3: Evidence Dependency Closure

## Goal

Prevent multiple evidence records derived from the same upstream source from
being interpreted as independent corroboration.

The sprint does not reject dependent evidence. Two analyses of one dataset can
both be useful and can both remain in ScientificBelief. What they cannot do is
silently become two independent source votes.

## Evidence lineage contract

SRIA Evidence now carries:

- `source_refs`: atomic upstream source identities such as datasets,
  observations or parent runs;
- `source_closure_complete`: an explicit statement of whether the listed
  ancestry is complete.

The default is deliberately:

`source_closure_complete = False`

Absence of a known dependency is not proof of independence.

Every Evidence record also has a derived `independence_roots` view containing
its producing run plus any explicit source roots.

## Identity semantics

Lineage is **record identity**, not claim content.

Two independent experiments may assert exactly the same scientific claim, so
their `content_hash` should remain equal.

Changing source ancestry or changing a closure from incomplete to complete
changes the Evidence record identity.

For legacy records with no lineage fields, the historical record-hash formula
is preserved exactly.

## Production bridge

The CredibilityEvidenceReport -> SRIA bridge carries a known
`parent_run_id` into `source_refs` when one is present.

It does **not** mark the closure complete. The credibility report currently
cannot prove that it knows every dataset/observation ancestor, so claiming a
complete closure there would create the exact false-independence path this
sprint exists to close.

## ScientificBelief semantics

`contributions(belief_key)` remains the complete record inventory.

It is explicitly not an independence count.

New views:

- `independence_groups(belief_key)`
- `independent_source_count(belief_key)`

### Fail-closed rule

If any active contribution has an incomplete source closure, all contributions
to that belief key form one dependency group for independence purposes.

Once every active contribution declares a complete closure, grouping is by
overlapping source roots.

The relation is transitive:

```
Evidence A -> dataset:a
Evidence B -> dataset:a + dataset:b
Evidence C -> dataset:b

A, B and C = one dependency group
```

This prevents the graph from being defeated by inserting one intermediate
derived artifact between two records.

## Validation-level authority hardening discovered while closing the sprint

The pre-Sprint-3 full recertification exposed a separate trust issue introduced
during Sprint 1: after ValidationLevel obligations became executable, any
registered critic could emit a check named `validation_level:...` and satisfy
the obligation.

That is now closed.

`CriticRegistration` carries an explicit `validation_level_issuer`
capability which is part of the critic-registry digest.

Only assessments from critics registered with that capability may resolve
ValidationLevel obligations.

`CredibilityReportCritic` is currently the reviewed issuer. A normal
registered numerical/process/domain critic with a matching check name cannot
mint a validation level.

## T3 recertification census fixes

The NAFEMS T3 execution vertical is now explicitly included in the repository's
load-bearing audits:

- model discovery: 16 -> 17 models;
- validity-condition census: 77 -> 92 conditions;
- reserved derived names remain unchanged;
- three T3 local execution checks are recorded as establishing no
  ValidationLevel;
- the evidentiary audit now records BENCHMARK_VALIDATED as occupied through the
  external repository-pinned NAFEMS oracle, not through a local self-check.

## Tests

`tests/test_sria_evidence_lineage.py` pins:

1. lineage changes record identity but not scientific claim identity;
2. legacy record hashes remain stable when no lineage is present;
3. source roots and completeness survive serialization;
4. incomplete closures never prove multiple independent sources;
5. a shared atomic source forms one group;
6. complete disjoint source closures form separate groups;
7. source overlap is transitively closed.

`tests/test_scientific_decision_readiness_sprint0.py` now treats SDR-07 as a
required passing invariant rather than an expected failure.

## What remains deliberately unsolved

This sprint does not:

- decide how conflicting independent groups should be weighted;
- invent majority voting;
- infer dataset identity from filenames or prose;
- claim lineage completeness for production paths that cannot prove it;
- add a generic AI claim-assessment API.

Those are separate decisions. The result of this sprint is narrower: Forge can
now represent and conservatively group dependency ancestry without silently
counting derivative records as independent sources.
