# D2 — Mixed-Variable Candidate Generation V0.1 freeze

Status: **PASS / FROZEN**

Milestone ID: `D2`

## Frozen identities

- Starting stable checkpoint (D1 PASS/FROZEN): `6de57f3e8c3602087a2f81911df82613fb373b97`
- Final D2 implementation source tested before freeze record: `9452276880a6287574dc3c6d5f2bfb68948d1542`
- D2 preregistration: `docs/design-d2-mixed-generation-prereg.md`

The D2 preregistration remained **FROZEN BEFORE IMPLEMENTATION** and was not rewritten after observing tests or adversarial review findings.

## Scope actually delivered

D2 establishes the first domain-neutral initial-population generation layer above frozen D0/D1 contracts.

Delivered contracts and behavior:

- `CandidateGenerationPlan`
- `CandidateProposal`
- `GenerationStrategy.HALTON_V1`
- `MixedVariableSampler`
- `ProposalDecision`
- `ProposalGate`
- `TwinMaterializer`
- `ProposalRejection`
- `CandidateGenerationBatch`
- deterministic typed assignment digesting
- deterministic generation binding attached to candidate `ScientificTwin` metadata
- strict generation-binding parser and validator
- explicit Twin/proposal-only generation-binding validator
- exact Proposal → DesignCandidate → ScientificTwin correspondence validation
- concrete `DesignSpace` validation at the batch boundary
- explicit plan-attempt-window validation
- exact D1 population coherence validation
- duplicate typed-assignment prevention
- finite fully-discrete cardinality checking
- deterministic unscrumbled Halton V0.1 baseline
- generation of all four existing design variable kinds: continuous, integer, categorical and boolean

D2 does not evaluate scientific objectives, rank designs, perform Bayesian/evolutionary optimization, implement adaptive search, recombine candidates, choose system physics, infer feasibility, certify safety, invoke LLM scientific judgment, or implement a concrete system pack.

## Scientific typing boundary

D2 preserves the frozen `ScientificValue` representation:

- continuous → `Quantity`
- integer → `IntegerValue`
- categorical → `CategoricalValue`
- boolean → `BooleanValue`

D2 does not convert mixed design variables into untyped scientific primitives for persistent records.

`DesignSpace.validate_assignments(...)` remains the authority for structural/type/design-space assignment coherence.

D2-specific searchability rules are stricter than D0 representability and fail closed when a V0.1 generation mapping would be undefined or unsafe.

## Frozen optimizer-adapter boundary

The existing Scientific Core `CandidateCodec` remains unchanged and continuous-only.

D2 mixed-variable **generation** does not claim mixed-variable **optimization** capability.

No frozen scientific adapter was silently widened.

## Halton V0.1 boundary

D2 uses one baseline initial-population strategy:

- strategy id: `halton_v1`
- deterministic
- unscrumbled
- no hidden random state
- source sequence indices begin at explicit `sequence_start >= 1`

The strategy is a deterministic baseline, not a claim of global optimality for all future design spaces.

Discrete aliasing may produce duplicate typed assignments; duplicates consume attempts and are not emitted.

## Generation-plan boundary

`CandidateGenerationPlan` declares:

- population id;
- exact `DesignSpaceReference`;
- requested accepted candidate count;
- generation zero;
- sequence start;
- finite attempt budget;
- strategy id;
- candidate-id prefix.

A successful `CandidateGenerationBatch` proves every accepted proposal lies inside the exact half-open attempt window:

`sequence_start <= sequence_index < sequence_start + attempt_budget`

A proposal whose candidate id is syntactically valid but whose sequence index lies outside that window is rejected.

Attempt-budget exhaustion fails closed rather than returning a partial population as success.

## Constraint/admission boundary

D0 `constraint_refs` remain opaque identifiers.

If a `DesignSpace` declares constraint references, D2 requires a caller-owned `ProposalGate` whose declared constraint-reference set exactly matches the design-space set.

D2 never interprets the scientific meaning of those references.

Gate acceptance means only that the explicit caller-owned generation/admission rule accepted the proposal. It does **not** mean:

- physically feasible;
- validated;
- safe;
- adequate;
- true;
- optimal;
- experimentally supported.

Rejected proposals require non-empty reasons.

## Scientific Twin materialization boundary

The general D2 layer does not invent system-specific equations, models, declarations or topology.

A caller-owned `TwinMaterializer` creates a `ScientificTwin` for an accepted proposal.

D2 verifies that:

- the returned object is a `ScientificTwin`;
- `TwinKind` is `CANDIDATE`;
- Twin references are unique inside the successful generated batch;
- the Twin carries deterministic D2 generation-binding metadata;
- that metadata matches the exact proposal identity;
- the corresponding `DesignCandidate` references the exact Twin;
- proposal/candidate assignments and assignment digest agree exactly.

This proves **internal D2 generation identity** under the declared non-cryptographic trust model.

It does not prove that the caller-owned materializer selected physically correct system models or declarations. That remains future system/domain validation work.

## Generation-binding boundary

D2 generation binding contains exactly:

- `candidate_id`
- `design_space_id`
- `design_space_version`
- `sequence_index`
- `strategy`
- `assignment_digest`

The parser validates canonical field types and values, including:

- non-empty canonical string identifiers;
- integer `sequence_index >= 1` with booleans rejected;
- known generation strategy;
- exactly 64 lowercase hexadecimal digest characters.

The API distinguishes:

- `validate_twin_generation_binding(twin, proposal)` — Twin/proposal identity only;
- `validate_generation_binding(twin, proposal, candidate)` — full proposal/candidate/Twin correspondence.

The full validator requires a concrete `DesignCandidate`.

## Concrete DesignSpace batch boundary

Adversarial review demonstrated that self-consistent proposal/candidate/Twin records could otherwise be internally coherent while containing an invalid assignment universe.

The final D2 `CandidateGenerationBatch` therefore carries a concrete `DesignSpace` and requires:

- concrete design-space identity exactly matches the plan reference;
- the design space is searchable under D2 V0.1 rules;
- every proposal passes `proposal.validate_against(design_space)`;
- every candidate passes `candidate.validate_against(design_space)`;
- each proposal/candidate pair uses the exact typed assignment universe declared by that concrete design space.

This closes missing-variable, undeclared-variable, wrong-type, out-of-bound, invalid-category and wrong-design-space-version construction holes.

This is structural/type/design-space coherence only; it is not a domain-physics feasibility claim.

## Proposal → Candidate → Twin identity boundary

Successful batch construction is order-independent but identity-strict.

Tuple reordering does not change identity. For each candidate id D2 proves:

1. exact proposal candidate id;
2. exact design-space id/version;
3. exact typed assignments;
4. exact assignment digest;
5. exact sequence index within the generation-plan attempt window;
6. exact generation strategy;
7. generation zero with no parents;
8. candidate operator matches generation strategy;
9. exact `TwinReference`;
10. exact Twin generation binding;
11. exact population membership.

Cross-wired candidate/Twin pairs, wrong assignments, duplicate proposal ids, duplicate candidate ids, duplicate Twin references, missing/extra population members and mismatched design spaces fail closed.

## Duplicate and finite-cardinality boundary

D2 does not emit duplicate typed assignment digests inside one successful generated population.

For fully discrete design spaces, exact finite cardinality is computed under D2 V0.1 searchability rules.

If requested count exceeds exact cardinality, generation fails before claiming sufficient unique candidates exist.

A requested count equal to exact finite cardinality is supported when the explicit attempt budget is sufficient to reach all unique decoded assignments.

Duplicate decoding and gate rejection both consume the explicit attempt budget.

## Determinism boundary

For the same:

- D2 implementation;
- concrete design-space declaration;
- generation plan;
- caller gate behavior;
- caller Twin-materializer behavior;

the generated proposal sequence, accepted sequence indices, candidate ids, typed assignments and assignment digests are deterministic.

D2 does not claim to make arbitrary stateful/non-deterministic caller code deterministic, and it does not claim cross-version cryptographic reproducibility.

## Adversarial review history

### First independent D2 review

Verdict: **SAFE WITH REQUIRED HARDENING**

Blocking findings:

1. `CandidateGenerationBatch` proved matching counts/sets but not exact per-candidate Proposal → Candidate → Twin correspondence.
2. `generation_binding_payload()` validated JSON shape but not sufficiently strict field semantics/correspondence against a concrete proposal/candidate.

Required action: **FIX BEFORE FULL REGRESSION**.

Hardening added strict per-identity correspondence, strict generation-binding parsing and `validate_generation_binding(...)`.

### Second independent D2 review

Verdict: **SAFE WITH REQUIRED HARDENING**

First review closure:

- original batch identity proof: PARTIALLY CLOSED;
- generation-binding validation: CLOSED.

New blocking findings:

1. a direct batch could accept a proposal whose `sequence_index` was outside the generation plan's legal attempt window;
2. a self-consistent proposal/candidate/Twin triple could carry an assignment universe invalid against the actual `DesignSpace` because the batch carried only a `DesignSpaceReference`.

A non-blocking API clarity concern also noted that a full-correspondence validator should not accept an omitted candidate.

Required action: **FIX BEFORE FULL REGRESSION**.

Hardening added:

- concrete `DesignSpace` to `CandidateGenerationBatch`;
- concrete proposal/candidate design-space validation;
- exact half-open attempt-window validation;
- separate Twin/proposal-only and full triple generation-binding validators;
- adversarial regression tests for the demonstrated holes.

### Final closure review

Verdict: **SAFE TO PROCEED**

Closure results:

- out-of-plan sequence-index P1: CLOSED;
- invalid-assignment-universe P1: CLOSED;
- validator API clarity P2: CLOSED;
- new blocking P0/P1 findings: NONE.

Affected criteria re-evaluated by the closure review:

- A3: PASS
- A8: PASS
- A9: PASS
- A11: PASS

Final recommendation: **PROCEED TO FULL REGRESSION**.

## Targeted test gates

### Initial D2 targeted suite

Against initial D2 source `6cbe5a4a6101a3de80ab55282060e773af590941`:

- `16 passed`
- `0 failed`
- `0 errors`
- wall time: `1.98 s`

This included a synthetic generation of `1000` mixed candidates.

### First hardened targeted suite

Against hardened source `956ae1abb7ba3a088a67de1aba600d5cb8906a37`:

- `24 passed`
- `0 failed`
- `0 errors`
- wall time: `2.29 s`

### Final hardened targeted suite

Against final implementation source `9452276880a6287574dc3c6d5f2bfb68948d1542`:

- `27 passed`
- `0 failed`
- `0 errors`
- wall time: `2.78 s`

The final targeted suite includes adversarial coverage for:

- Proposal/Candidate/Twin cross-wiring;
- wrong candidate assignments;
- malformed generation-binding fields;
- Twin version mismatch;
- negative integer search ranges;
- finite discrete exact-cardinality generation;
- proposal round-trip requiring explicit concrete design-space validation;
- out-of-plan sequence index;
- self-consistent invalid assignment universe;
- wrong population membership;
- 1000-candidate mixed generation;
- frozen continuous-only `CandidateCodec` protection;
- domain neutrality.

## Full regression gate

Full repository regression executed against final D2 implementation source `9452276880a6287574dc3c6d5f2bfb68948d1542`:

- `1378 passed`
- `4 warnings`
- `0 failed`
- `0 errors`
- wall time: `190.91 s` (`0:03:10`)

The four warnings are the existing scikit-learn Gaussian-process `ConvergenceWarning` messages from `tests/test_smoke.py`; they are not D2 failures.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A1 — domain neutrality | PASS |
| A2 — frozen adapter protection | PASS |
| A3 — four-kind mixed generation | PASS |
| A4 — searchability fails closed | PASS |
| A5 — deterministic low-discrepancy baseline | PASS |
| A6 — explicit constraints | PASS |
| A7 — no status inflation | PASS |
| A8 — exact Twin binding | PASS, within D2 non-cryptographic internal-identity trust model |
| A9 — population exactness | PASS |
| A10 — duplicate/cardinality safety | PASS |
| A11 — deterministic persistent records | PASS |
| A12 — practical 1000-candidate test | PASS |
| A13 — regression safety | PASS |

## Frozen milestone protection

The D2 implementation diff from frozen D1 touches only:

- `docs/design-d2-mixed-generation-prereg.md`
- `docs/design-d2-mixed-generation-freeze.md`
- `src/engcore/design/__init__.py`
- `src/engcore/design/generation.py`
- `src/engcore/design/sampling.py`
- `tests/test_design_d2_mixed_generation.py`

Frozen K1, K1.5, K2, Scientific Twin V0.1, K3, K3.1, K4, D0 and D1 scientific semantics remain unchanged.

The existing Scientific Core `CandidateCodec` remains continuous-only.

No concrete domain/system package was introduced by D2.

## Explicitly not part of D2

The following remain successor work and must not be retrofitted into frozen D2 after observing the first real system pack:

- conditional-variable activation/deactivation;
- adaptive generation based on D1 evaluations;
- Bayesian/evolutionary/mixed-variable optimization;
- Sobol/LHS generation strategy portfolio;
- component compatibility graphs;
- recombination/mutation operators;
- novelty search;
- uncertainty-directed generation;
- multi-fidelity promotion policy;
- Scientific Design Memory;
- SRIA integration;
- any concrete system pack;
- derived-candidate parent lineage;
- proof that a system pack materialized scientifically correct equations/models;
- cryptographic/content-addressed artifact authenticity.

## Successor pull principle

After D2, development should not continue adding generic design/discovery machinery without a system experiment requiring it.

The next practical milestone should be pulled by the first real system vertical slice, expected to be a multirotor/aerospace system pack that composes reusable scientific domains and uses D2 generation + D1 evaluation/archives.

The intended direction is:

User/engineering requirements
→ system design specification
→ mixed `DesignSpace`
→ system-owned constraint gate
→ many candidate `ScientificTwin(kind=CANDIDATE)` records
→ scientific evaluation
→ D1 Pareto/scoped archives
→ preserved partial successes

If that vertical slice reveals a missing conditional/topology/compatibility concept, introduce it through a new preregistered successor milestone instead of inserting a system-specific exception into D2.

## Frozen outcome

D2 is **PASS / FROZEN**.

The milestone now provides deterministic domain-neutral mixed-variable initial population generation with explicit attempt budgets, exact typed assignments, explicit system-owned constraint admission, exact candidate/Twin identity, concrete design-space validation, duplicate/cardinality safety and preserved frozen scientific boundaries.

Generation success remains a structural/internal identity statement — not scientific feasibility, validation, safety, adequacy, optimality or truth.
