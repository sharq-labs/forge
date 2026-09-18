# Scientific Decision Readiness — Sprint 1

## Goal

Close the first production-to-decision gaps found by Sprint 0 without inventing
a second trust system.

## Implemented

### 1. Credibility report -> SRIA Evidence bridge

New module:

`src/engcore/mcp/sria_bridge.py`

The bridge derives a QOI claim from a production
`CredibilityEvidenceReport`.

A caller may choose which report quantity becomes the claim, but cannot supply
another value. The claim value and units are read directly from the report.

The bridge requires:

- evidence id;
- domain-pack ref;
- non-empty context ref;
- explicit model-discrepancy declaration.

It refuses to assume zero model-form discrepancy.

### 2. Exact report identity binding

Candidate Evidence records the SHA-256 digest of the exact credibility report
inside scientific claim content.

`CredibilityReportCritic` records the same digest in trusted assessment
provenance.

The Arbiter refuses an assessment whose report digest does not match the report
that produced the Evidence, even when both reports reuse the same run id.

The digest is deliberately NOT part of the belief grouping key, so independent
runs can still corroborate the same claim in the same context.

### 3. Context-aware belief grouping

`Evidence.belief_key` now includes `context_ref` when it is present.

This prevents evidence for different intended uses from sharing one belief
group while preserving the historical key for legacy records whose context is
blank.

### 4. ValidationLevel obligations are executable

`obligations_from_charter()` already emitted:

`validation_level:<level>`

but the Arbiter previously hard-coded these obligations as unevaluable.

That exception is removed.

`CredibilityReportCritic` emits trusted checks with the same vocabulary for
every ValidationLevel, so the existing generic check-resolution path now
decides the obligation.

No new confidence scale was added.

### 5. Battery uncertainty is explicit

The production battery report now attaches one `Uncertainty.UNKNOWN` record
to each quantitative output:

- terminal_voltage
- final_state_of_charge
- heat_generation
- final_temperature

No numeric uncertainty was invented. The change only replaces silence with the
explicit scientific state already supported by the Core.

## Trust properties

The implementation preserves these constraints:

1. Core never imports SRIA.
2. The bridge lives at the MCP consumer boundary.
3. A caller cannot replace a report value while creating evidence.
4. A caller cannot silently choose an uncertainty channel for an unattributed
   quantified uncertainty.
5. COMBINED uncertainty is not filed into one SRIA channel.
6. Validation levels reach the Arbiter through a registered critic, not mutable
   Evidence metadata.
7. Evidence for different contexts has different belief keys.
8. Evidence from the same context across independent runs can still share a
   belief key.
9. Same run id is insufficient to substitute another credibility report.

## Closed Sprint-0 findings

- SDR-01: production Core/MCP -> SRIA bridge — **closed for QOI simulation evidence**.
- SDR-02: context-blind belief grouping — **closed**.
- SDR-03: ValidationLevel obligations unevaluable — **closed through trusted critic checks**.
- SDR-04: verification-vs-validation semantics — **preserved**.
- SDR-05: battery quantitative uncertainty silence — **closed as explicit UNKNOWN**.

## Still open

- SDR-06: trusted production external oracle authority.
- SDR-07: evidence dependency/ancestry closure.
- SDR-08: inherited Core V4 reference-posterior reproducibility blocker.
- SDR-09: generic conflict adjudication/fusion remains intentionally absent.
- SDR-10: generic AI scientific-claim assessment boundary.

## Next implementation order

1. Trusted external oracle admission for one flagship domain.
2. Evidence dependency closure / shared-source detection.
3. Generic claim-assessment API above domain execution.
4. Only then broader domain expansion.
