# Scientific Decision Readiness Audit — Sprint 0 FINAL

Base: PR #48 head `b9d8165a663f6a602707e32b9f36193792a8d24c`  
Audit branch: `claude/scientific-decision-readiness-audit`

## Sprint objective

Determine whether Forge can carry a scientific question/result into
decision-grade evidence without inventing confidence, duplicating existing
contracts, or losing applicability/validation/uncertainty semantics between
the Scientific Core/MCP and SRIA.

Sprint 0 is an **audit/falsification sprint**, not a feature sprint.

## Final status

| ID | Final status | Reach | Owner | Result |
|---|---|---|---|---|
| SDR-01 | **OPEN** | production | Transport Core↔SRIA | No production adapter converts a `ScientificResult` / `CredibilityEvidenceReport` into SRIA `Evidence`. |
| SDR-02 | **OPEN** | SRIA | Context/Decision | `context_ref` changes evidence content identity, but `belief_key` is context-blind and the ref is opaque/unvalidated. |
| SDR-03 | **OPEN** | SRIA | Assurance | Charter `ValidationLevel` requirements become obligations, but `Arbiter.decide()` explicitly cannot evaluate them. |
| SDR-04 | **PARTIAL / MCP CLOSED** | production | MCP + Transport | Verification-only cannot satisfy a required VALIDATED basis inside MCP. End-to-end preservation into SRIA is still absent because SDR-01 is open. |
| SDR-05 | **OPEN** | production | Domain + Transport | Battery emits quantitative outputs with no per-value uncertainty mapping in the production report. |
| SDR-06 | **OPEN** | production | Evidence/Data | Trusted production oracle declarations are intentionally empty. External validation is representable but not currently earnable from curated production authority. |
| SDR-07 | **OPEN** | SRIA | Evidence | No generic evidence ancestry/dependency closure exists; shared source observations cannot be detected generically for double-counting control. |
| SDR-08 | **OPEN / RELEASE BLOCKER** | certification | Core | Core V4 reference posterior is not currently byte-re-derivable from current models; pinned digest mismatch remains inherited. |
| SDR-09 | **PARTIAL / SAFE BASE** | SRIA | Belief | Conflicting claims remain distinct records/content identities and are not silently averaged. Generic claim adjudication/fusion is intentionally absent. |
| SDR-10 | **OPEN** | AI boundary | MCP/Transport | Public AI runtime has capability description + system-specific run tools only; no cross-domain claim/context/decision assessment tool exists. |

## Key falsifications

### 1. Production and decision assurance are two separate trust paths

Current production path:

```text
ScientificProblem
    -> Domain Solver
    -> ScientificResult
    -> CredibilityEvidenceReport
    -> MCP response
```

Current SRIA path:

```text
Candidate Evidence
    -> Critics
    -> Arbiter
    -> Admission Authority
    -> Belief Update Gateway
    -> ScientificBelief
    -> Decision/VoI machinery
```

There is no supported production bridge between the two.

### 2. Do NOT build a second decision system

SRIA already has:

- `CampaignCharter`
- `TerminalDecision`
- `TerminalUtility`
- `ConfidenceRequirement`
- `ValidationObligation`
- `ClaimBinding`
- `UncertaintyDeclaration`
- `UncertaintyBudget`
- critic/arbiter/admission/gateway trust chain

The missing capability is closure and binding, not another decision ontology.

### 3. Verification vs validation is already correctly fail-closed in MCP

Executable probe:

```text
nominal electrothermal report
verdict = SUPPORTED
evidence_basis = VERIFICATION_ONLY
```

Requiring:

```text
required_evidence_basis = VALIDATED
```

correctly produces:

```text
INSUFFICIENT_EVIDENCE
```

This semantic is a foundation to preserve, not redesign.

### 4. Context is part of evidence identity but not belief grouping

Two otherwise-identical SRIA evidence records with different `context_ref`
produce different `content_hash` values.

However:

```text
belief_key = claim_type | claim_binding.key
```

does not include context. Therefore evidence from screening/certification or
different operating contexts can share a contribution key.

No current automatic fusion makes this a present numerical corruption, but it
is a blocker for future generic claim adjudication/planning.

### 5. Charter confidence requirements do not close through the Arbiter

`obligations_from_charter()` translates required `ValidationLevel` entries
into `validation_level:...` obligations.

`Arbiter.decide()` then explicitly marks those obligations as:

```text
recorded but not evaluated in M3; cannot be certified
```

This is a concrete missing link, not a naming/design gap.

### 6. Battery has a production uncertainty break

The production battery report exposes:

- `terminal_voltage`
- `final_state_of_charge`
- `heat_generation`
- `final_temperature`

but does not carry a per-value `uncertainty` entry for them.

For a future quantitative decision, the safe interpretation is UNKNOWN, never
zero or “good enough”.

### 7. External validation authority is not production-ready

The core oracle architecture is strong:

- analytic reference;
- benchmark dataset;
- experimental dataset;
- content-addressed evidence;
- operating-point binding;
- validation-level semantics.

But the repository-owned trusted oracle declaration map is empty by design.

So Forge can represent external evidence today, but production runs cannot yet
earn external validation from a reviewed trusted authority.

### 8. Evidence closure is still missing

SRIA records `provenance_ref`, but `Evidence` has no generic ancestry or
source-observation dependency closure.

Two downstream derived artifacts therefore cannot generically prove whether
they are independent corroboration or two views of the same source data.

### 9. Conflict is preserved correctly

Two claims over the same belief key with different values produce different
content and record hashes. SRIA does not silently average them.

This is the correct base behavior.

What is intentionally not present is a universal rule such as:

```text
2 supports > 1 contradiction
```

and Sprint 0 does not invent one.

### 10. The AI-facing API is still execution-first

The public MCP transport registers:

- `describe_capabilities`
- `run_electrothermal`
- `run_battery`

There is no generic boundary for:

```text
question
+ claim
+ context / operating regime
+ terminal decision
+ required evidence
-> scientific assessment
```

That should come after the trust bridge is closed.

## Ownership map

| Capability | Correct owner |
|---|---|
| Scientific quantities, problems, models, results | Scientific Core |
| Model applicability | Scientific Core + Domain definitions |
| Numerical validation/verification checks | Solver/Domain + Core result contracts |
| Credibility report and evidence basis | MCP/consumer boundary |
| Scientific claim semantics | Domain + SRIA binding |
| Candidate evidence lifecycle | SRIA |
| Assurance obligations | SRIA |
| Terminal decision / utility | SRIA |
| Evidence admission / belief write authority | SRIA |
| Production Core→SRIA conversion | **New Transport adapter** |
| Per-domain UQ generation | Domain solver |
| Generic UQ representation | Core/SRIA |
| Oracle authority/content pins | Core Evidence/Data authority |
| External benchmark/experimental datasets | Domain Evidence/Data |
| AI planner / generic assessment API | Transport/Orchestration |
| CFD/Mechanics/Aero physics | Domain packs, not Core |

## Minimal implementation order for Sprint 1+

### P0 — Bridge result to evidence

Build an explicit adapter:

```text
CredibilityEvidenceReport
    -> Candidate SRIA Evidence
```

It must derive, not copy freely:

- quantity/value/units;
- run/provenance identity;
- domain-pack identity;
- evidence basis;
- uncertainty;
- exact context/decision binding.

No manual duplicate numeric payload should be required.

### P0 — Close validation obligations

Teach assurance to evaluate an existing charter-required
`ValidationLevel` from trusted evidence/assessment records.

Do not introduce a second confidence scale.

### P0 — Typed context binding

First attempt to compose from existing identities:

- `CampaignCharter.digest`
- `TerminalDecision.decision_id`
- operating-regime identity
- claim binding

Only add a new `ContextOfUse` contract if this composition cannot express the
needed scientific meaning without unvalidated prose.

### P0 — UQ closure

Every quantitative output must carry one of:

- quantified uncertainty;
- bounded uncertainty;
- explicit UNKNOWN;
- explicit NOT_APPLICABLE with rationale.

Silence is not a valid uncertainty state at the decision boundary.

### P0 — Trusted external evidence

Admit a deliberately tiny curated oracle set for one flagship domain using
reviewed source change + content digest + stable reference.

Start small and strong.

### P1 — Evidence dependency closure

Add source-observation ancestry sufficient to detect shared evidence and prevent
false independence/double counting.

### P1 — Generic claim assessment API

After the chain is closed, add a generic AI-facing assessment boundary above
domain execution.

### P2 — Domain expansion

Only then expand Mechanics / CFD / Aerodynamics / broader PDE.

## Do not build

Sprint 0 explicitly rejects these as premature or duplicative:

- a second validation vocabulary;
- a second terminal-decision system;
- a universal scalar confidence score;
- an arbitrary numeric ModelRisk formula;
- automatic natural-language claim inference in the truth path;
- evidence voting/majority rules;
- “ICH M15 compliant” claims;
- CFD/Mechanics/Aerodynamics before decision-to-evidence closure;
- blindly regenerating the failed reference-posterior digest.

## Tests

File:

`tests/test_scientific_decision_readiness_sprint0.py`

Pinned findings:

- SDR-01: no production Core/MCP→SRIA bridge;
- SDR-02: context-blind belief key;
- SDR-03: validation-level obligations not evaluable;
- SDR-05: battery quantitative uncertainty chain incomplete;
- SDR-06: no trusted production external oracle;
- SDR-07: no first-class evidence dependency closure;
- SDR-10: no cross-domain AI decision tool.

Positive invariants:

- SDR-04: verification-only fails a VALIDATED intended-use requirement;
- SDR-09: conflicting claims remain distinct records and are not collapsed.

## Sprint 0 exit decision

**COMPLETE as an audit/falsification sprint.**

All ten preregistered areas were either reproduced as surviving gaps or narrowed
to existing behavior that already works. No new core concept is justified
without first closing the concrete links above.

The inherited Core V4 reproducibility mismatch remains a release blocker and is
explicitly outside this audit sprint's implementation scope.
