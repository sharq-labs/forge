# D1 — Design Evaluation, Population and Selection Archives V0.1 freeze

Status: **PASS / FROZEN**

Milestone ID: `D1`

## Frozen identities

- Starting stable checkpoint (D0 PASS/FROZEN): `15b6002bdb924a3ddae32ba507a4138495a4bc5b`
- Hardened D1 tested source before freeze record: `5f6d33ecc28c677573af631b02f74bdb0c8bc4eb`
- D1 preregistration: `docs/design-d1-evaluation-archives-prereg.md`

The D1 preregistration remained frozen before implementation and was not rewritten after observing tests or adversarial review findings.

## Scope actually delivered

D1 establishes a domain-neutral bridge from D0 candidate identity to attributable evaluation and deterministic plural-success archives.

Delivered contracts and behavior:

- `DesignPopulation`
- `DesignEvaluationReference`
- `DesignEvaluation`
- `FidelitySelection`
- `ProjectedObjective`
- objective projection through the existing `ScientificResult` / `Quantity` contracts
- exact pairwise Pareto dominance
- `ParetoArchive`
- `ScopedEliteArchive`
- deterministic serialization / round-trip support
- explicit candidate/Twin/design-space result binding through provenance metadata
- archive revalidation against concrete evaluation evidence on deserialization
- concrete-candidate population validation boundary
- evaluation-level fidelity validation boundary

D1 does not generate candidates, optimize a design space, assign domain meaning to fidelity rungs, perform recombination, implement system packs, invoke LLMs, or infer scientific truth from archive membership.

## Scientific attribution boundary

Every `DesignEvaluation` binds:

1. one exact `DesignCandidateReference`;
2. one exact `TwinReference`;
3. one exact `DesignSpaceReference`;
4. one complete `ScientificResult`;
5. producer-side binding metadata recorded in the result provenance for the same candidate/Twin/design-space identity.

Construction and deserialization fail closed when this binding is missing or mismatched.

This proves internal attribution under D1's declared non-cryptographic trust model. It is not cryptographic artifact authenticity, hash-based evidence immutability, or external tamper proofing.

## Selection eligibility boundary

D1 never silently promotes any of the following into design eligibility, feasibility, truth, safety, validation or optimality:

- `ScientificResult.is_usable`
- solver convergence
- validation level
- uncertainty
- posterior/inference state
- archive membership

`SelectionEligibility` remains explicit caller-supplied decision state. Non-unknown decisions require reasons.

## Pareto semantics

D1 uses exact deterministic Pareto dominance only.

A dominates B iff:

- A is no worse on every declared objective; and
- A is strictly better on at least one declared objective.

The implementation respects `MINIMIZE` and `MAXIMIZE`, uses the existing `Quantity` unit-conversion contract, and contains:

- no epsilon;
- no hidden tolerance;
- no weighted sum;
- no normalization;
- no scalar winner;
- no LLM judgment.

Distinct ties and non-dominated trade-offs are preserved.

## Archive persistence trust boundary

`ParetoArchive.build(...)` and `ScopedEliteArchive.build(...)` compute membership from concrete eligible evaluations.

Deserialization no longer accepts arbitrary member references as verified archive truth. `from_dict(...)` requires concrete evaluation evidence and revalidates/recomputes membership against that evidence.

D1 does not yet bind persisted archives to cryptographic digests of the exact original evaluation payloads. That stronger evidence/artifact binding remains successor work.

## Population boundary

`DesignPopulation` remains a declaration of candidate membership for one generation and design-space reference.

`validate_candidates(...)` provides the concrete validation boundary for:

- exact member id set;
- design-space identity;
- generation coherence;
- duplicate/missing/extra candidate rejection.

D1 does not generate population members.

## Fidelity boundary

`FidelitySelection` stores only:

- `ladder_id`
- `ladder_version`
- `rung_id`

It assigns no domain-specific meaning to a rung. `DesignEvaluation.validate_fidelity(...)` validates the selection against a supplied `FidelityLadder`.

## Domain-neutrality boundary

The D1 layer contains no concrete product/system/domain ranking logic or conditionals for drone, aircraft, HVAC, battery, motor, propeller, wing, compressor, reactor, kinetics, thermal, electrical or similar semantics.

`scope_ref` remains opaque to the general design layer.

A future system pack remains removable without changing D1.

## Adversarial review history

### First independent review

Verdict: **SAFE WITH REQUIRED HARDENING**

Primary findings:

- result-to-candidate/Twin/design-space attribution was not proven;
- archive deserialization trusted persisted member references without sufficient evidence;
- population lacked a concrete-candidate integrity validation boundary;
- fidelity selection could remain unvalidated inside an evaluation;
- D1 mapping immutability required hardening/clarification.

Those findings were addressed without modifying the frozen preregistration or frozen scientific-core semantics.

### Second independent adversarial review

Verdict: **SAFE TO PROCEED**

First-review closure:

- result attribution: CLOSED
- archive deserialization trust boundary: CLOSED
- population concrete-candidate validation: CLOSED
- fidelity validation: CLOSED
- top-level D1 metadata mutability concern: PARTIALLY CLOSED / non-blocking under inherited Scientific Core shallow-mapping semantics

Final recommendation from the second review: **PROCEED TO FULL REGRESSION**.

Non-blocking successor concerns identified by review:

- persisted archives bind source evaluation ids/evidence but not cryptographic digests of exact original evaluation payloads;
- nested `ScientificResult.provenance.metadata` remains shallowly mutable under existing Scientific Core semantics;
- population identity is currently candidate-id based and does not independently encode Twin identity in `DesignCandidateReference`.

These are explicitly deferred rather than retrofitted into frozen D1 semantics.

## Targeted test gate

Hardened D1 targeted suite against source `5f6d33ecc28c677573af631b02f74bdb0c8bc4eb`:

- `15 passed`
- `0 failed`
- `0 errors`
- wall time: `1.26 s`

The targeted suite covers the core D1 contracts including attribution mismatch, archive tampering/revalidation, population validation, fidelity validation, unit compatibility/conversion, deterministic archive behavior and serialization round-trip.

## Full regression gate

Full repository regression executed against hardened D1 source `5f6d33ecc28c677573af631b02f74bdb0c8bc4eb`:

- `1351 passed`
- `4 warnings`
- `0 failed`
- `0 errors`
- wall time: `198.94 s` (`0:03:18`)

The four warnings are the existing scikit-learn Gaussian-process `ConvergenceWarning` messages from `tests/test_smoke.py`; they are not D1 failures.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A1 — domain neutrality | PASS |
| A2 — attributable evaluation | PASS, within D1 non-cryptographic trust model |
| A3 — no scientific-status inflation | PASS |
| A4 — objective projection exactness | PASS |
| A5 — exact deterministic dominance | PASS |
| A6 — Pareto archive order invariance | PASS |
| A7 — preserve plural success | PASS |
| A8 — scoped partial-success boundary | PASS |
| A9 — population identity | PASS, with successor note on candidate-reference richness |
| A10 — fidelity generality | PASS |
| A11 — deterministic round-trip | PASS, with successor note on deep evidence immutability |
| A12 — regression safety | PASS |

## Frozen milestone protection

The D1 diff from frozen D0 touches only:

- `docs/design-d1-evaluation-archives-prereg.md`
- `docs/design-d1-evaluation-archives-freeze.md`
- `src/engcore/design/__init__.py`
- `src/engcore/design/evaluation.py`
- `src/engcore/design/population.py`
- `src/engcore/design/archives.py`
- `tests/test_design_d1_evaluation_archives.py`

Frozen scientific semantics of K1, K1.5, K2, Scientific Twin V0.1, K3, K3.1, K4 and D0 are unchanged.

The existing `Quantity` contract remains `Quantity.magnitude` + `Quantity.units`; no core Quantity API change was made.

## Explicitly not part of D1

The following remain successor work:

- candidate generation;
- mixed-variable search/encoding;
- conditional-variable activation;
- Sobol/LHS/DOE/evolutionary/Bayesian population generation;
- compatibility graphs;
- recombination operators;
- novelty/failure archives beyond current explicit eligibility state;
- multi-fidelity escalation policy;
- cryptographic/content-addressed evidence binding;
- Scientific Design Memory;
- SRIA integration;
- any concrete system pack;
- automatic top-N promotion.

## Frozen outcome

D1 is **PASS / FROZEN**.

The milestone preserves plural design success while maintaining explicit scientific attribution, exact unit-aware objective projection, exact Pareto semantics, explicit eligibility, verifiable archive reconstruction, domain neutrality and frozen Scientific Twin boundaries.

Any future extension must be introduced through a successor milestone instead of rewriting D1 after observing downstream system-pack behavior.
