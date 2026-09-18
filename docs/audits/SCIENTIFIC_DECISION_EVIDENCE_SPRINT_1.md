# Scientific Decision-to-Evidence Bridge — Sprint 1

Base: Scientific Decision Readiness Sprint 0 (PR #49)

## Objective

Close the first production P0 path discovered by Sprint 0:

```text
CredibilityEvidenceReport
    -> SRIA Evidence
    -> registered assurance critic
    -> charter ValidationLevel obligation
    -> Arbiter decision
```

without duplicating Scientific Core or SRIA decision semantics and without
promoting missing uncertainty or model discrepancy into confidence.

## Implemented contracts

### 1. Honest model-form uncertainty

`DiscrepancyKind.UNKNOWN` is now representable.

The bridge uses UNKNOWN when the production report contains no explicit
model-form discrepancy statement. It never substitutes `ZERO_DECLARED`.

The domain discrepancy critic treats UNKNOWN as INCONCLUSIVE and
assurance-blocking, not as refutation.

### 2. Context binding from existing SRIA identities

No new ContextOfUse object was introduced.

The bridge derives a stable `context_ref` from:

- `CampaignCharter.campaign_id`
- exact `CampaignCharter.digest`
- charter version
- an existing terminal decision id
- optional operating-context reference

The same context ref is added as a reserved `ClaimBinding` qualifier so
bridged belief keys are context-sensitive.

### 3. Claim value is derived, not copied

`evidence_from_credibility_report()` accepts a `value_name` but never a
scientific value or unit. Those are read from `report.values[value_name]`.

The resulting candidate evidence pins:

- report run identity;
- producing provenance run;
- exact report digest;
- credibility verdict;
- evidence basis;
- attained validation levels;
- decision context identity.

### 4. UQ translation is conservative

Per-value uncertainty is mapped to an SRIA channel only from its own
`UncertaintySource`.

- known source -> corresponding SRIA channel;
- source-attributed UNKNOWN -> explicit UNKNOWN in that channel;
- no uncertainty -> undeclared channels stay UNKNOWN;
- quantified UNSPECIFIED -> refused;
- quantified COMBINED -> refused until decomposed.

### 5. ValidationLevel obligations are executable

`Arbiter.decide()` no longer hard-codes `validation_level:...` as
unevaluable.

A registered `CredibilityReportCritic` re-reads the source report's attained
levels and emits exact named checks:

```text
validation_level:<level>
```

The Arbiter resolves these through its existing named-check mechanism.

The critic does not grant a level; it transports the level the credibility
report already earned.

### 6. Report/evidence binding is rechecked

The process critic verifies:

- claim quantity exists in the report;
- value and units match the report;
- evidence provenance matches report provenance;
- claim context qualifier matches evidence context;
- evidence pins the exact report digest.

A mismatched bridge record blocks assurance.

## End-to-end acceptance cases

The Sprint 1 test suite covers:

1. claim value/units/provenance are derived from the report;
2. two decision contexts produce different evidence and belief keys;
3. invalid terminal decision ids are refused;
4. default model discrepancy is UNKNOWN;
5. an actually attained validation level satisfies the charter and reaches
   `AssuranceVerdict.VALID`;
6. an unattained external-validation level yields
   `AssuranceVerdict.INCONCLUSIVE`;
7. tampered claim/report binding is refused by the registered critic;
8. missing Battery uncertainty is explicit UNKNOWN at the decision boundary;
9. quantified uncertainty with no source is refused instead of guessed;
10. an `INSUFFICIENT_EVIDENCE` credibility report cannot be promoted to a
    VALID SRIA decision.

## Still open after Sprint 1

Sprint 1 intentionally does not claim to close all Sprint 0 findings:

- Battery domain still does not produce per-value UQ; the bridge only preserves
  the gap honestly.
- trusted external oracle declarations remain empty.
- evidence dependency/ancestry closure remains open.
- hand-built SRIA evidence can still use a context-blind belief key; bridged
  production evidence is protected by the reserved context qualifier.
- no generic AI claim-assessment MCP tool yet.
- inherited Core V4 reference-posterior reproducibility mismatch remains a
  release blocker.

## Non-goals

- no new physics domain;
- no scalar confidence score;
- no automatic natural-language claim inference;
- no ICH M15 compliance claim;
- no automatic model-risk formula;
- no fake UQ defaults.
