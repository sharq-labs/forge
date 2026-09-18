# Scientific Decision Readiness Audit — Sprint 0

Base branch: PR #48 head `b9d8165a663f6a602707e32b9f36193792a8d24c`

## Question

Can Forge take a real scientific question or claim, bind it to an intended decision/context, execute or assess the relevant models, carry applicability/verification/validation/uncertainty into evidence, and produce a decision whose strength is justified by the evidence — without a caller manually inventing trust?

This sprint is an audit/falsification round. It does **not** add new scientific domains and it does **not** pre-decide new core types.

## Why this sprint first

The repository already contains overlapping pieces that must be mapped before anything new is added:

- Scientific Core: `ScientificProblem`, `ScientificResult`, model validity, validation, provenance, requirements, UQ records.
- MCP: production-facing electrothermal and battery credibility reports.
- SRIA: `CampaignCharter`, `TerminalDecision`, utility/VoI, evidence admission, `ClaimBinding`, uncertainty budgets, assurance obligations, belief history.
- A design-only `ScientificClaim` / `ContextOfUse` proposal.
- Oracle and independent-evidence infrastructure.

The critical architectural fact is that SRIA is deliberately above and disconnected from the production verification path. The audit must determine what should be bridged, what should stay separate, and which apparent gaps are already solved under another name.

## Scope

Two existing production-facing verticals are used as probes:

1. Electrothermal — because it can produce a nominal credibility report and exposes verification-vs-validation semantics.
2. Battery — because it is multi-model/multi-domain and already exposes honest evidence gaps.

No Mechanics, CFD, aerodynamics, FEM, or new solver integration is part of Sprint 0.

## Audit invariants

### SDR-01 — Claim production is not manual
A production `ScientificResult` / credibility report must be able to become evidence about a named scientific claim without a caller copying a value into an unrelated free-form payload.

Falsification probe: change the manually asserted claim value while keeping the assessed result unchanged. The system must refuse the relationship or make the gap explicit at the production bridge.

### SDR-02 — Decision/context identity is load-bearing
Evidence used for a terminal decision must be bound to the exact decision/context it was assessed for.

Probe: reuse valid evidence under another decision, operating regime, required tolerance, or amended charter. If the same evidence retains full standing without an explicit transport justification, record a finding.

### SDR-03 — Evidence requirements scale with intended use
A low-consequence exploratory use and a high-consequence terminal decision must not silently use the same assurance policy merely because the numerical result is identical.

Audit first; do not invent `ModelRisk` fields. Determine whether existing terminal utility, confidence requirements, acceptance criteria and obligations can express and *derive* the necessary change. If policy remains caller-selected without a binding derivation, record the gap.

### SDR-04 — Verification cannot stand in for reality validation
A result with only verification evidence must never be presented as validated against the world.

Probe the complete path: Core result -> credibility report -> SRIA evidence -> assurance decision -> belief/decision. Record where evidence basis is preserved, downgraded, or lost.

### SDR-05 — Uncertainty closes end-to-end
A quantitative decision must identify the required uncertainty channels and prove which are quantified, bounded, unknown, or not applicable.

Trace Core `Uncertainty` -> credibility report -> SRIA `UncertaintyDeclaration` -> `UncertaintyBudget` -> obligation/decision. Any manual reinterpretation, dropped source kind, or missing production bridge is a finding.

### SDR-06 — External authority is real, not representational
Benchmark/experimental validation must be earnable only from curated external evidence whose identity/content is pinned.

Audit the production oracle registry, benchmark evidence, and MCP path. Distinguish “the architecture can represent external evidence” from “a production result can actually earn it.”

### SDR-07 — Evidence dependency closure prevents double counting
Two downstream artifacts derived from the same source observations must not count as independent corroboration unless independence is established.

The SRIA V0.1 design already records evidence closure as unimplemented. Reproduce the strongest concrete double-counting case reachable with current contracts and classify reach.

### SDR-08 — Reproducibility is a release gate
Every pinned scientific reference used to justify a claim must be re-derivable from the current models.

Inherited baseline blocker at the branch point: `scientific312` fails because rebuilt Core V4 reference posteriors produce digest `7176ef65...` while the pinned record declares `8c21374c...`. This is not fixed in Sprint 0; it is recorded as a prerequisite to certification and must be resolved before a later implementation branch is considered merge-ready.

### SDR-09 — Conflicting evidence remains a decision input, not hidden averaging
Multiple accepted evidence records that support and contradict the same belief key must remain distinguishable. Determine whether the current belief/decision layer can derive a defensible claim standing or only store contributions.

No universal voting or score is to be invented in this sprint.

### SDR-10 — AI-facing path can ask the scientific question
Audit whether an external AI can ask “is this claim supported for this context and decision?” through a generic production boundary.

Current MCP exposes domain-specific execution tools. Determine the smallest bridge/API needed above them; do not add a generic planner in this sprint.

## Method

For every SDR item:

1. Locate the existing contracts and their declared semantics.
2. Build the smallest adversarial reproduction.
3. Mark the item **CLOSED**, **PARTIAL**, **OPEN**, or **REFUTED**.
4. Classify reach as production, MCP-only, SRIA-only, library-only, or design-only.
5. Identify the owning layer: Core, SRIA, Domain, Transport, or Evidence/Data.
6. Do not change a threshold or scientific rule to make a test pass.
7. Where a new concept appears necessary, first prove no existing contract can carry the meaning.

## Required outputs

- One audit report with a finding table and reproductions.
- Strict regression/xfail tests for every surviving finding before implementation.
- A Core/SRIA/Domain/Transport ownership map.
- A minimal implementation sequence ordered by scientific risk, not convenience.
- Explicit “do not build” decisions for duplicate concepts.
- A separate note identifying which findings are prerequisites for new domains such as Mechanics/CFD and which are independent of domain expansion.

## Exit criteria

Sprint 0 is complete only when:

- every SDR item is reproduced or refuted;
- no proposed fix depends on an untested assumption about another layer;
- the existing `ScientificClaim/ContextOfUse` design is either retired, revised, or justified against SRIA’s existing decision/evidence contracts;
- we know whether decision-risk semantics can be expressed by existing utility/charter/obligation contracts or require one new contract;
- we have one end-to-end trace for electrothermal and one for battery;
- inherited scientific reproducibility failures are separately identified and not hidden by the new work.

## Non-goals

- No new domain physics.
- No CFD/aerodynamics.
- No generic MCMC/HMC engine.
- No new “compliance” claim with ICH M15 or any external standard.
- No scalar risk score invented from prose.
- No automatic claim inference from natural language.
- No merging SRIA downward into the Scientific Core.

The sprint exists to discover the minimum honest bridge from scientific computation to decision-grade evidence before implementation expands the surface.
