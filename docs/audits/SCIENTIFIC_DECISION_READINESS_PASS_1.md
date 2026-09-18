# Scientific Decision Readiness Audit — Sprint 0 / Pass 1

Branch: `claude/scientific-decision-readiness-audit`
Base: PR #48 head `b9d8165a663f6a602707e32b9f36193792a8d24c`

This pass maps the existing production Scientific Core/MCP path against SRIA's
decision/evidence path. It intentionally does not implement fixes.

## Executive finding

Forge already owns most of the *pieces* needed for decision-grade scientific
evidence, but they are split across two architectures:

- production execution and credibility: Scientific Core -> MCP;
- research decision and assurance: SRIA.

The highest-risk gap is not the absence of another generic “model risk” object.
It is **decision-to-evidence closure**: the production credibility report is
not currently a source of SRIA evidence, and SRIA assurance cannot yet evaluate
a charter's requested `ValidationLevel`.

That means adding new domains first would multiply the number of paths that
need bridging without closing the trust chain.

## Findings

| ID | Status | Reach | Owner | Finding |
|---|---|---|---|---|
| SDR-01 | **OPEN** | production | Transport/Core↔SRIA | No production bridge turns a `CredibilityEvidenceReport` / `ScientificResult` into SRIA `Evidence`. SRIA remains outside the verification path. |
| SDR-02 | **PARTIAL** | SRIA | SRIA | `Evidence.context_ref` is part of scientific-content identity, but it is an opaque string. `Arbiter.decide()` does not receive a `CampaignCharter`, terminal decision, or typed Context-of-Use contract. |
| SDR-03 | **OPEN** | SRIA decision path | SRIA | Charter confidence requirements become `validation_level:...` obligations, but `Arbiter.decide()` explicitly records them as **not evaluable in M3**. There is also no derived Model-Influence × Consequence rule; assurance policy is declared by the campaign. |
| SDR-04 | **PARTIAL** | MCP good / end-to-end open | Core + Transport | MCP preserves verification-vs-validation via `evidence_basis`, `required_evidence_basis`, and explicit verification-only guidance. That semantic does not currently travel into SRIA because SDR-01 is open. |
| SDR-05 | **PARTIAL** | both layers, no bridge | Core + SRIA | MCP carries per-value uncertainty including `source_kind`; SRIA owns decomposed uncertainty channels and budgets. No production adapter proves that the same uncertainty declaration survives end-to-end. |
| SDR-06 | **OPEN** | production | Evidence/Data | The production trusted-oracle declaration registry is intentionally empty. The architecture can represent analytic/benchmark/experimental evidence, but production cannot currently earn authority from a repository-pinned external oracle. |
| SDR-07 | **OPEN** | SRIA/design | SRIA | Evidence dependency closure is explicitly recorded as unimplemented in SRIA V0.1. Independent-looking downstream artifacts can therefore not yet prove they are independent observations. Current production MCP is not using SRIA, so present production reach is limited. |
| SDR-08 | **OPEN / BLOCKER** | certification | Core | Inherited `scientific312` reference-posterior digest mismatch means one pinned scientific reference is not currently re-derivable byte-for-byte. Do not regenerate blindly. |
| SDR-09 | **PARTIAL** | SRIA | SRIA | Conflict visibility is strong: belief stores contributions separately and does not silently average them. A generic derived claim standing over conflicting contributions is deliberately absent. |
| SDR-10 | **OPEN** | AI boundary | Transport/MCP | Public runtime is system execution (`describe_capabilities`, electrothermal, battery), not a generic “assess this scientific claim in this context for this decision” boundary. |

## What is already stronger than the initial gap list suggested

### Claim/result binding is not empty

SRIA already refuses an assessment as support for a QOI/parameter claim when
the assessed `ScientificResult` does not contain the claimed quantity/value
(with unit conversion and declared tolerance handled explicitly). The remaining
SDR-01 problem is therefore **production claim creation/transport**, not the
absence of claim-result integrity inside SRIA.

### Decision semantics already exist

`CampaignCharter` already has:

- terminal decisions;
- confidence requirements;
- acceptance criteria;
- immutable amendment history and digest binding.

The M4 decision layer already requires a terminal objective and declared utility
before formal value-of-information is available. A new generic decision object
would duplicate real code.

### Context identity is partly load-bearing

`Evidence.context_ref` participates in SRIA's scientific content hash. Editing
the context changes evidence identity. The missing part is the authority and
semantics of the context reference: nothing proves that an arbitrary string is
the exact decision/context the assurance policy was derived for.

### Verification vs validation is explicit in production

The MCP credibility layer already distinguishes evidence basis and can demand
`VALIDATED` instead of accepting verification-only support. It also tells AI
consumers that a `SUPPORTED` result may still be verification-only. Do not
replace this with a second vocabulary.

## The P0 chain that must close before domain expansion

```text
Scientific question / decision context
        |
        v
ScientificProblem
        |
        v
Domain model + solver
        |
        v
ScientificResult
        |
        v
CredibilityEvidenceReport
        |
        |   CURRENT GAP: no production bridge
        v
SRIA Evidence / ClaimBinding
        |
        v
Critics + UncertaintyBudget
        |
        v
Obligations derived from exact charter
        |
        |   CURRENT GAP: ValidationLevel obligations not evaluable
        v
Arbiter decision
        |
        v
ScientificBelief / terminal decision
```

## P0 implementation candidates — not approved yet

The audit does **not** decide the exact API, but the smallest implementation
sequence to test next is:

1. **Transport adapter, not a new truth system.**
   Define one explicit boundary that derives candidate SRIA evidence from a
   production credibility report while preserving run identity, claim quantity,
   units, uncertainty source and evidence basis. No free-form copy of a result
   value is allowed.

2. **Typed context/decision binding at the bridge.**
   Reuse `CampaignCharter.digest`, `TerminalDecision.decision_id`, and
   existing `context_ref` identity before introducing a new ContextOfUse
   record. Add a new record only if these cannot encode operating regime +
   intended use without prose.

3. **Evaluate validation-level obligations.**
   Close the existing TODO rather than inventing another confidence scale.
   A charter that requires `EXPERIMENTALLY_VALIDATED` must be able to prove
   or refuse it from the evidence/assessment record.

4. **Uncertainty translation with no semantic collapse.**
   Map Core/MCP uncertainty source kinds into SRIA channels only when the
   mapping is scientifically valid; otherwise preserve UNKNOWN and block a
   quantitative claim.

5. **Trusted external evidence.**
   Admit a tiny curated production oracle set by reviewed source change and
   content digest. Start with one flagship domain; do not bulk-populate weak
   “references”.

6. **Generic AI claim-assessment boundary.**
   Add only after the chain above can produce a decision-grade answer without
   manual trust injection.

## Do not build yet

- a second `ScientificResult`;
- a second validation-level vocabulary;
- a scalar universal “confidence score”;
- a ModelRisk number derived from arbitrary labels;
- a duplicate utility/decision engine;
- CFD/Mechanics/Aerodynamics before the evidence bridge is proven;
- “ICH M15 compliant” branding.

## Tests added in this pass

`tests/test_scientific_decision_readiness_sprint0.py` pins three surviving
structural findings as strict expected failures:

- the production tree has no SRIA bridge;
- charter `ValidationLevel` obligations are not evaluable by the Arbiter;
- production has no trusted external oracle declaration.

These tests are deliberately about existing semantic gaps, not about a chosen
class name for the eventual fix.

## Next audit pass

Pass 2 should build two executable traces:

1. Electrothermal: one verification-only `SUPPORTED` report carried into a
   decision that requires real-world validation. Expected answer:
   **INSUFFICIENT_EVIDENCE**, with the missing basis preserved.
2. Battery: one quantitative claim whose uncertainty contains at least one
   UNKNOWN scientific channel. Expected answer: the quantitative terminal
   claim cannot be certified.

Only after those traces are reproducible should Sprint 1 implement the bridge.


## Pass 2 — executable production traces

### SDR-04 / Electrothermal — CLOSED at MCP, still open end-to-end

A production electrothermal example already reaches a `SUPPORTED` credibility
verdict on **VERIFICATION_ONLY** evidence. The audit test then reuses the same
report but declares `required_evidence_basis="VALIDATED"`.

Expected and pinned behavior:

```text
SUPPORTED + VERIFICATION_ONLY
        |
        | intended use now requires VALIDATED evidence
        v
INSUFFICIENT_EVIDENCE
```

This is the correct fail-closed semantic and must be preserved by the future
Core/MCP -> SRIA bridge. Therefore SDR-04 is not “build a new verification vs
validation vocabulary”; it is “do not lose the vocabulary already present when
the report becomes decision evidence”.

Test:
`test_sdr04_verification_only_support_cannot_satisfy_a_validated_use`.

### SDR-05 / Battery — OPEN production UQ closure

The production battery assembler constructs a
`CredibilityEvidenceReport` with final quantitative values:

- `terminal_voltage`
- `final_state_of_charge`
- `heat_generation`
- `final_temperature`

but does not pass a per-value `uncertainty` mapping. The report therefore
inherits the empty default.

This is a stronger and more concrete gap than “SRIA needs more UQ”: the
decision layer cannot honestly translate a missing production declaration into
a quantified SRIA channel. The only safe interpretation is UNKNOWN, and that
translation does not exist yet.

Strict expected-failure test:
`test_sdr05_battery_quantitative_values_close_the_uncertainty_chain`.

### CI note

No pull-request workflow run was associated with commit
`31f83bf75a688479f30cddb84b3411290939ec63` because this audit branch is not
yet a PR and the repository's relevant workflow is PR-triggered. No CI result is
claimed for the new audit tests yet.
