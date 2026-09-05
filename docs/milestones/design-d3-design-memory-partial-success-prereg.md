# D3 — Scientific Design Memory / Partial Success V0.1 preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Starting stable checkpoint: `4a5f58408b597beae852c99f0ea4e53201cf99f0` (MVR1 PASS/FROZEN)

Revision: **hardened before implementation.** Every experiment-outcome-affecting rule below is frozen. Remaining open items are architectural only and are explicitly marked as such. No D3 implementation exists at the time of this freeze.

## Purpose

Add the smallest domain-neutral layer that can **retain, attribute and re-serve partial scientific success** across evaluations, studies and generations.

Frozen D1 preserves plural success only as exact Pareto membership and scoped elite membership. MVR0 and MVR1 produced direct evidence that this is insufficient for a discovery workflow:

- MVR0 scoped single-objective archives retained exactly one exact extreme member per scope, discarding every near-extreme design;
- MVR0 observed a target dimension (endurance) that did not discriminate at all, so target pass/fail carried almost no retained information;
- MVR1 demonstrated that the *same* candidate can be a target failure under one Study and a target pass under another, because operating conditions change physics while thresholds only assess it.

D3 is therefore about **memory of why a design was interesting**, not about optimization.

D3 is not an optimizer, not an adaptive generation policy, not a recommender, not a surrogate model, not an LLM interpretation layer, and not a scientific validation engine.

## Architectural boundary

D3 may depend on frozen domain-neutral contracts from D0/D1/D2 and the Scientific Core:

- `DesignSpace` / `DesignSpaceReference`;
- `DesignCandidate` / `DesignCandidateReference`;
- `DesignPopulation`;
- `DesignEvaluation`, `ResultBinding`, `SelectionEligibility`;
- objective projection and exact Pareto dominance;
- `ScientificTwin` / `TwinKind`;
- typed `ScientificValue`, `Quantity`, `IntegerValue`, `CategoricalValue`, `BooleanValue`;
- deterministic serialization / scientific errors.

D3 must not import or branch on:

- concrete `engcore.domains` packages;
- any system pack, including the frozen multirotor pack;
- MVR0/MVR1 physics or target semantics;
- SRIA campaign policy;
- a concrete optimizer backend;
- an LLM provider;
- web/API/database frameworks.

The multirotor system pack must remain removable without modifying D3, and D3 must be usable by a kinetics or HVAC pack that never existed at D3 freeze time.

## Relationship to frozen milestones

D0/D1/D2, Scientific Twin, K-series, MVR0 and MVR1 remain **frozen**. D3 must not:

- widen frozen D1 archive semantics in place;
- retrofit retention policy into frozen Pareto/elite archives;
- alter `SelectionEligibility`;
- alter MVR1 Study identity, attribution or the physical consistency gate;
- change what any frozen milestone already recorded as a result.

D3 adds a **new adjacent layer**. Where D3 needs richer retention than frozen D1 offers, it builds a separate memory record referencing frozen D1 objects rather than mutating them.

## Two-layer separation

D3 freezes an explicit separation. Every D3 concept belongs to exactly one layer.

### Layer A — scientifically attributable observation

Layer A is what was actually evaluated and is attributable to exactly one D1 evaluation. Layer A is immutable and is never a function of any policy, threshold, tolerance, cap or ordering.

Layer A consists of:

- candidate / design-space / evaluation / `ResultBinding` / scope attribution;
- the exact typed assignments of the candidate;
- the exact typed objective values under the scope's declared objective projection;
- exact D1 Pareto membership within the scope;
- exact D1 scoped elite membership within the scope;
- explicitly defined distance-to-reference facts (§ Tolerance semantics), which are numeric observations, not judgements.

### Layer B — retention / classification policy

Layer B is what a caller-declared policy *decided about* Layer A. Layer B is derived, replaceable, and never a scientific claim.

Layer B consists of:

- retention reason membership;
- assessment contexts (threshold sets) and the classifications derived under them;
- cap application and the retained/discarded split.

### The open architectural question D3 must answer

D3 V0.1 **does not pre-decide** whether Layer B should become stored scientific state or should be reproducibly derived from stored Layer A on demand.

The experiment tests this: the implementation must be able to reconstruct the complete Layer B result **from stored Layer A plus the declared policy alone**, byte-identically, without reading any stored Layer B. Gate A13 enforces this. If rederivation is exact, storing Layer B is an optimization; if it is not, the prereg's layer split was wrong and that is a reportable D3 finding.

## Scientific questions

Preserved unchanged from the original preregistration.

**Q1 — Is partial success representable domain-neutrally?**
Can "this design was nearly good, in this specific respect, under these specific conditions" be recorded exactly, without the general layer knowing what the respect or the condition physically means?

**Q2 — Is retained partial success attributable?**
Can every retained memory entry be traced back to exactly one attributable D1 evaluation, one candidate, one design space, and (where present) one study context — with no ambiguity about which physics produced it?

**Q3 — Does memory survive changing assessment without lying?**
When thresholds change but physics does not (MVR1 semantics), does a memory entry recorded under one assessment remain truthful, or does it silently become a false claim?

**Q4 — Does memory survive changing physics without conflating?**
When operating conditions change and physics *does* change, does D3 keep the two records distinct rather than merging them into one apparently-comparable population?

**Q5 — Is retention bounded and deterministic?**
Can retention be capped without the discarded/retained split becoming order-dependent or implementation-dependent?

**Q6 — Does memory avoid status inflation?**
Does retention of a near-miss ever get read as feasibility, validation, adequacy, safety, optimality or truth?

**Q7 — What is actually lost by exact-Pareto-only retention?**
Quantitatively, on a frozen reference population: how many scientifically valid, D1-eligible evaluations carrying near-extreme or near-threshold behavior are discarded by frozen D1 archives alone?

Q7 is the empirical motivation question. Q1–Q6 are the contract questions.

## Scope frozen for D3

### 1. Scope identity

A `DesignMemoryScope` declares the exact conditions under which its entries are mutually comparable:

- exact `DesignSpaceReference`;
- exact objective projection identity, including for each objective its identifier, canonical unit and optimization direction (`MINIMIZE` or `MAXIMIZE`);
- an exact context reference (which MVR1-style studies would populate with study identity).

**Scope identity is deterministic** and is the digest over the canonical deterministic serialization of exactly those three components, in that order.

**Scope equality is exact digest equality.** No partial, fuzzy, subset or compatible-unit matching exists.

D3 must refuse to compare, dominate-check, co-retain or merge entries whose scope identity differs. Every such attempt raises. There is no permissive path.

Scope attribution must round-trip exactly: serializing and deserializing a scope reproduces the identical scope identity digest.

This is the D3 answer to MVR1's central semantic result: **changed operating conditions produce a different scope; changed thresholds do not.** Thresholds are never part of scope identity.

### 2. Memory entry

An immutable `DesignMemoryEntry` records Layer A only:

- exact `DesignCandidateReference`;
- exact `DesignSpaceReference`;
- exact evaluation identity and `ResultBinding` of the single attributable evaluation;
- exact scope identity;
- the exact typed assignments of the candidate;
- the exact typed objective values under the scope projection;
- a deterministic entry digest.

**Entry digest coverage is frozen (closes U2):** the digest covers Layer A only — attribution, assignments, objective values and scope identity. It does **not** cover retention reasons, tolerances, thresholds, assessment contexts, policy or cap outcome.

Consequence: no Layer B change can ever alter an entry digest. Re-assessment (E3) is digest-invariant by construction.

An entry is a **record of a past attributable evaluation**. It is not evidence, not a recommendation, not a prediction, and not a claim about any other design space or condition.

### 3. Eligible evaluation set

The **eligible set** of a scope is the set of D1 evaluations that are D1 `SelectionEligibility`-eligible, attributable to that exact scope, and whose objective values are all finite under the scope projection.

Every retention predicate below is computed over the eligible set of one scope. An evaluation carrying a non-finite objective value under the scope projection is a **fail-closed error at scope construction**, not a silent exclusion.

### 4. Frozen retention reasons

D3 V0.1 freezes exactly six retention reasons. Each is defined below with required inputs, exact predicate, dimensional rules, boundary behavior and layer classification.

Rules that apply to all six:

- **Reason membership is computed over the complete eligible set, before any cap is applied.** Capacity never changes classification (§ Cap semantics).
- **Reasons are independent and non-exclusive.** An entry may carry any subset of the six. Reasons are recorded as an unordered set; they are never ranked, counted into a score, or used to order entries.
- Every reason predicate is a pure deterministic function of the eligible set and the declared policy. No reason depends on insertion order.

Notation: for objective `k`, `v_k(e)` is the entry's exact objective value in the scope's canonical unit for `k`; `dir_k ∈ {MINIMIZE, MAXIMIZE}` is the declared direction.

---

**R1 — `PARETO_MEMBER`**

- *Required inputs:* the eligible set; the scope objective projection.
- *Predicate:* the entry is a member of the exact frozen-D1 non-dominated set over all objectives of the scope projection, computed over the complete eligible set.
- *Units:* comparison uses each objective's canonical unit; no cross-objective arithmetic.
- *Boundary:* exact D1 dominance semantics, unchanged. Exact ties are non-dominating, so all tied members are members.
- *Simultaneity:* may co-occur with any other reason.
- *Capacity independence:* yes — computed pre-cap.
- *Layer:* **A** (observation). Membership is a fact about the eligible set.

---

**R2 — `SCOPED_ELITE`**

- *Required inputs:* the eligible set; the scope objective projection; a caller-declared non-empty set of elite scopes, each a non-empty subset of the scope's objective identifiers.
- *Predicate:* for a declared elite scope `S`, the entry is a member of the exact frozen-D1 non-dominated set computed over exactly the objectives in `S`. The entry carries `SCOPED_ELITE` if this holds for at least one declared `S`. The set of qualifying `S` is recorded.
- *Units:* per-objective canonical units.
- *Boundary:* exact D1 semantics; exact ties all qualify.
- *Simultaneity:* may co-occur with any other reason; may qualify under multiple `S`.
- *Capacity independence:* yes.
- *Layer:* **A** (observation).

---

**R3 — `NEAR_EXTREME`** — precisely, *within declared absolute distance of the observed per-objective extreme*

- *Required inputs:* the eligible set; the scope projection; a caller-declared `extreme_tolerance` map from objective identifier to an absolute typed tolerance (§ Tolerance semantics). Objectives absent from the map are not evaluated for this reason.
- *Extreme definition:* for objective `k`, `x_k = min over the eligible set of v_k` if `dir_k = MINIMIZE`, else `max`. The extreme is the observed extreme of the eligible set — never a bound, target or ideal.
- *Predicate:* the entry qualifies for objective `k` iff `|v_k(e) − x_k| <= tol_k`, with both values in `k`'s canonical unit. The entry carries `NEAR_EXTREME` if this holds for at least one objective in the map. The qualifying objective identifiers and the exact computed distances `|v_k(e) − x_k|` are recorded as Layer A facts.
- *Units:* `tol_k` must have exactly the dimension of objective `k`. Dimension mismatch is a fail-closed error.
- *Boundary:* comparison is **inclusive** (`<=`). The extreme itself has distance `0` and therefore always qualifies when `k` is in the map, including when `tol_k = 0`.
- *Simultaneity:* may co-occur with any other reason.
- *Capacity independence:* yes.
- *Layer:* the **distance is Layer A**; the **qualification against `tol_k` is Layer B**.

---

**R4 — `NEAR_THRESHOLD`** — precisely, *within declared absolute distance of a caller-declared assessment threshold, on either side*

- *Required inputs:* the scope projection; an assessment context declaring a `threshold` map from objective identifier to an absolute typed threshold value, and a `threshold_tolerance` map from objective identifier to an absolute typed tolerance. An objective must appear in both maps or in neither; appearing in exactly one is a fail-closed error.
- *Predicate:* the entry qualifies for objective `k` iff `|v_k(e) − t_k| <= tol_k`, in `k`'s canonical unit. The entry carries `NEAR_THRESHOLD` if this holds for at least one declared objective. The qualifying objectives, the exact signed margins `v_k(e) − t_k`, and the assessment context identity are recorded.
- *Units:* `t_k` and `tol_k` must each have exactly the dimension of objective `k`. Mismatch is fail-closed.
- *Boundary:* comparison is **inclusive** (`<=`). Both sides of the threshold qualify symmetrically — a passing near-miss and a failing near-miss are both retained, deliberately. Exactly meeting the threshold (`margin = 0`) qualifies.
- *Sign:* the *predicate* is symmetric (uses `|·|`). The *recorded margin* is signed and directional, so pass/fail side is recoverable without re-deriving it from the predicate.
- *Simultaneity:* may co-occur with any other reason; may qualify under multiple objectives and, across E3, under multiple assessment contexts.
- *Capacity independence:* yes.
- *Layer:* the **signed margin is Layer A** relative to a declared threshold; the **qualification is Layer B**, attributable to a named assessment context.

---

**R5 — `DIVERSITY_REPRESENTATIVE`**

- *Required inputs:* the eligible set; a caller-supplied deterministic partition function mapping an entry's exact typed assignments to an **opaque partition key** (a byte string). D3 never inspects, parses, orders by meaning, or derives partition keys itself (closes U4: keys are caller-declared, D3 stays neutral).
- *Predicate:* within each partition key present in the eligible set, exactly one entry qualifies: the entry that is **first under the frozen identity ordering** (§ Tie-break rule). Every partition present in the eligible set contributes exactly one representative.
- *Units:* none; keys are opaque bytes compared by exact equality.
- *Boundary:* a partition of size one yields that entry. Partition key collisions are, by definition, the same partition. An empty partition cannot occur.
- *Simultaneity:* may co-occur with any other reason.
- *Capacity independence:* yes — representatives are chosen over the complete eligible set, before any cap.
- *Layer:* the **partition key is Layer A** (a deterministic function of recorded assignments); the **representative selection is Layer B**.

---

**R6 — `EXPLICIT`**

- *Required inputs:* a caller-supplied set of `(candidate reference, evaluation identity, non-empty reason string)` triples.
- *Predicate:* the entry qualifies iff its `(candidate reference, evaluation identity)` pair appears in the declared set. The reason string is recorded verbatim. A triple naming a pair absent from the eligible set is a fail-closed error, not a silent no-op.
- *Units:* none.
- *Boundary:* exact identity match only; no prefix, alias or partial matching.
- *Simultaneity:* may co-occur with any other reason.
- *Capacity independence:* yes.
- *Layer:* **B** (policy). `EXPLICIT` is caller intent and asserts nothing scientific.

---

No other retention reason exists in D3 V0.1. A system pack needing a seventh must obtain it through a successor milestone.

### 5. Tolerance semantics (frozen)

**Absolute only.** D3 V0.1 has **no relative tolerance and no Core default tolerance.** There is no scientifically defensible generic relative tolerance across arbitrary objectives — the zero-reference case (`x_k = 0` or `t_k = 0`) makes a fraction either undefined or silently infinite in reach, and the correct choice is domain knowledge D3 does not possess. Tolerance is therefore **explicit caller-supplied study policy**, exactly like MVR1 target thresholds.

Frozen rules:

- **Representation:** an absolute typed value (`Quantity` for dimensional objectives, exact dimensionless value for dimensionless ones). Relative fractions, percentages, ratios, standard deviations, quantiles and rank-based tolerances are **not permitted** in V0.1.
- **Dimensional behavior:** a tolerance's dimension must exactly equal its objective's dimension. Mismatch is fail-closed at policy validation, before any entry is examined.
- **Canonical normalization:** the tolerance, the reference (extreme or threshold) and the objective value are each converted **once** to the objective's declared canonical unit at policy/scope validation time. All comparisons happen in canonical units on already-converted values. No comparison performs a unit conversion.
- **Sign behavior:** a tolerance must be `>= 0`. Negative is fail-closed. Predicates use `|value − reference|`, so tolerance reach is symmetric; recorded margins remain signed.
- **Zero-reference behavior:** a reference of exactly `0` is ordinary and needs no special case, because tolerance is absolute. A tolerance of exactly `0` is permitted and means exact equality in canonical units.
- **Non-finite behavior:** a non-finite (`NaN`/`±inf`) tolerance, threshold or objective value is fail-closed. Non-finite objective values are already excluded at scope construction (§3).
- **Comparison:** exact `<=` on the canonical-unit values. No epsilon is added by D3; if a caller wants slack, that slack *is* the tolerance.

Tolerance semantics are frozen **before** E1/E6 execution and must not be revised after observing retained counts.

### 6. Retention cap semantics (frozen)

- **Cap is per scope and global within that scope.** It is not partitioned by reason, by objective, or by partition key. Per-reason quotas do not exist in V0.1.
- **Preregistered experimental cap: `250` entries per scope**, for E1, E2 and E6 (a 1000-candidate eligible set, so the cap binds meaningfully at one quarter of the population).
- **Classification precedes capacity.** All six reason predicates are evaluated over the complete eligible set before the cap is consulted. The cap **never** changes which reasons an entry carries. A discarded entry is still classified.
- **Multiple reasons do not increase retention priority.** Reason count is never used to order or prioritize entries. This is deliberate: counting reasons would be a hidden scalar score.
- **Unconditional retention:** entries carrying `PARETO_MEMBER` or `SCOPED_ELITE` (the two pure Layer-A observation reasons) are unconditionally retained.
- **Overflow behavior:** the retained set is constructed as — tier 1: all unconditionally-retained entries; tier 2: all remaining entries carrying at least one reason. Within each tier, entries are ordered by the frozen identity ordering (§7). The retained set is the first `cap` entries of tier 1 followed by tier 2 in that order. If the count of tier-1 entries **exceeds** the cap, D3 **fails closed** with an explicit error; it never drops an unconditionally-retained entry, and never silently raises the cap.
- **Discarded entries remain observable.** The memory record carries, for the complete pre-cap eligible set: the total eligible count, the per-reason census, the count of entries carrying at least one reason, the retained count, the discarded-but-classified count and the exact identities of discarded-but-classified entries. E1/E6 statistics are computed from these pre-cap figures, so the cap tests bounded memory without distorting the scientific result.

### 7. Deterministic tie-break rule (frozen — closes U5)

**Identity ordering, scientific-preference-neutral.**

Entries are ordered by ascending lexicographic comparison of the byte sequence formed by the canonical deterministic serialization of the tuple:

`(candidate reference, evaluation identity)`

compared as UTF-8 code-unit sequences, candidate reference first, evaluation identity as the exact tie-break for the (contract-forbidden but defensively handled) case of equal candidate references.

Frozen properties:

- the ordering never reads an objective value, margin, distance, reason set, reason count or assessment outcome;
- it introduces no scalar objective, weighted score or implicit preference direction;
- it is a strict total order on the eligible set, because `(candidate reference, evaluation identity)` is unique per entry by A3;
- it is therefore independent of insertion order, which is what makes A5 achievable rather than assumed.

Objective-aware tie-breaking is **rejected for V0.1**. If E1/E6 demonstrate that identity ordering discards a class of entries that a defensible neutral rule would keep, that is a recorded D3 finding and a successor milestone — not a retrospective edit to this rule.

### 8. Assessment-change semantics (frozen)

An `AssessmentContext` is a named, immutable, deterministically-identified declaration of a threshold map and a threshold-tolerance map over the scope's objectives. Its identity is the digest of its canonical serialization.

Frozen rules:

- an assessment context is **Layer B** and is **never** part of scope identity;
- applying a new assessment context **never** recomputes, re-evaluates or re-records physics — the frozen D1 evaluation and the Layer A entry, including its digest, are unchanged and remain valid;
- every `NEAR_THRESHOLD` qualification and every recorded margin is **attributable to exactly one named assessment context**; a margin without a context reference cannot exist;
- classifications under different assessment contexts coexist. A later context never overwrites, supersedes or invalidates an earlier one;
- no mutable label exists. Reclassification produces a **new attributable classification record**, never an edit of an old observation. An old observation can therefore never be silently converted into a new scientific claim;
- an assessment context declaring an objective absent from the scope projection is fail-closed.

### 9. No status inflation

Retention means only: *an explicit, caller-declared retention rule matched an attributable evaluation.*

D3 must never describe a retained entry as feasible, validated, adequate, safe, optimal, promising, recommended, or true. Non-retention must never be described as refuted, infeasible or invalid.

The words *near*, *close*, *interesting*, *good*, *useful* and *strong* carry no D3 semantics. Where `NEAR_EXTREME` and `NEAR_THRESHOLD` appear as names, their meaning is exhausted by their frozen predicates in §4 and by nothing else.

### 10. Determinism and persistence

For the same D3 implementation, scope, policy, assessment contexts and offered evaluation set, the retained entry set, discarded set, per-reason census, entry digests, scope identity and serialized memory record must be byte-deterministic and round-trip without scientific type loss.

D3 does not claim cross-version cryptographic authenticity of arbitrary caller-supplied objects. Same-reference content mutation of `ScientificTwin` and `DesignSpace` remains **open Core identity/integrity debt inherited from MVR1** and is explicitly out of D3 scope.

## Experiment definition

Preserved from the original preregistration; parameters now fully bound.

### E1 — domain-neutral synthetic retention experiment

A synthetic, domain-neutral mixed design space with a deterministic analytic objective set (at least two objectives with declared opposing directions, so the Pareto front is non-degenerate).

- generate `1000` candidates via frozen D2 `halton_v1`;
- evaluate all under frozen D1 into one D3 scope;
- construct the frozen D1 exact Pareto archive and scoped elite archives;
- declare an explicit policy: `extreme_tolerance` and `threshold_tolerance` maps for every objective, one assessment context, a partition function, and an `EXPLICIT` set;
- classify the complete eligible set under all six frozen predicates;
- apply cap `250` under the frozen overflow rule;
- record: eligible count, per-reason census, Pareto count, scoped elite count, entries carrying ≥1 reason, retained count, retained-but-not-D1-archived count, discarded-but-classified count, unclassified count.

Primary purpose: Q1, Q5, Q7.

### E2 — insertion-order invariance experiment

Re-run E1 classification and retention under at least three distinct deterministic permutations of the offered evaluation order, including exact reverse order.

Assert byte-identical retained set, discarded set, per-reason census and serialized memory record.

Primary purpose: Q5.

### E3 — assessment-change experiment (physics fixed)

Take the E1 scope unchanged. Apply a second, stricter assessment context.

- no physics is recomputed and no D1 evaluation is re-run;
- every Layer A entry digest is asserted unchanged;
- the original assessment context's classifications remain present and unmodified;
- new `NEAR_THRESHOLD` qualifications are computed from recorded values and are attributable to the new context identity;
- scope identity is asserted unchanged, since thresholds are not part of scope identity.

Primary purpose: Q3; validates §8.

### E4 — condition-change experiment (physics changed)

Construct a second scope with a different declared context reference and a genuinely different objective outcome for the same candidates.

- scope identities differ;
- entries from scope 1 and scope 2 are never co-retained;
- cross-scope dominance comparison, merge and co-classification each fail closed;
- both scopes remain independently attributable and round-trip exactly.

Primary purpose: Q2, Q4. This is the domain-neutral analogue of the MVR1 Study A / Study B result and must be expressible without importing MVR1.

### E5 — attribution adversarial experiment

Attempt to insert or classify a memory entry whose claimed evaluation identity, candidate reference, scope identity, or recorded objective values disagree with the attributable D1 evaluation.

Every such attempt must fail closed, including the case where the forged entry is **internally coherent** — the MVR1 lesson that coherent metadata is not evidence of correct attribution.

Primary purpose: Q2 under adversarial conditions.

### E6 — reference-population evidence run

Execute E1 at the frozen `1000`-candidate scale with the frozen cap `250` and record exact counts as the D3 frozen reference numbers, in the same style as the MVR0 1000-candidate outcome.

This produces the quantitative answer to Q7.

## Success / failure gates

### A1 — domain neutrality

D3 contains no concrete domain/system-pack imports and no product-specific branches. Removing every system pack leaves D3 fully testable.

### A2 — frozen milestone protection

D0/D1/D2, Scientific Twin, K-series, MVR0 and MVR1 source semantics are unmodified. D3 references frozen objects; it does not mutate or widen them.

### A3 — exact attribution

Every entry resolves to exactly one attributable D1 evaluation with an exact `ResultBinding`, one candidate, one design space and one scope. `(candidate reference, evaluation identity)` is unique within a scope. Mismatched or forged attribution fails closed (E5).

### A4 — representable partial success

All six frozen predicates in §4 are computable with exact typed values and caller-declared tolerances/thresholds, with no D3-invented defaults (E1).

### A5 — order invariance

Retained set, discarded set, per-reason census and serialized record are byte-identical across all tested insertion permutations (E2).

### A6 — bounded retention fails closed

Classification is complete pre-cap; cap application never alters reason membership; tier-1 overflow raises rather than dropping an unconditionally-retained entry (E1, E2).

### A7 — assessment/physics separation

Re-assessment under a new context changes derived classification only. Layer A entries, entry digests and scope identity are unchanged, and every new classification is attributable to the new context (E3).

### A8 — scope separation

Cross-scope co-retention, merge and dominance comparison fail closed; scope identity is deterministic and round-trips exactly (E4).

### A9 — no status inflation

No D3 API, field name, docstring or serialized value asserts feasibility, validation, adequacy, safety, optimality or truth for a retained entry, or refutation for a discarded one.

### A10 — deterministic round-trip

Memory scopes, policies, assessment contexts and entries serialize deterministically and round-trip without scientific type loss.

### A11 — quantified retention evidence

E6 produces exact recorded pre-cap counts for eligible evaluations, per-reason census, Pareto members, scoped elites, retained entries, retained-but-not-D1-archived entries and discarded-but-classified entries at 1000-candidate scale.

### A12 — regression safety

Targeted D3 tests pass and the full repository regression remains green.

### A13 — Layer B rederivability

The complete Layer B result (reason membership, classifications, retained/discarded split) is reconstructible byte-identically from stored Layer A plus the declared policy and assessment contexts alone, without reading any stored Layer B.

A13 is the gate that lets the experiment *answer* the stored-vs-derived architectural question rather than the preregistration presupposing it. A13 failing is a genuine finding, not a defect to be patched by widening what Layer A stores after the fact.

**Failure gate:** any of A1, A2, A3, A5, A6, A8 failing is a blocking D3 failure.

A11 producing a retained-but-not-D1-archived count of zero is **not** a failure — it is a valid observed outcome and a successor design signal, and must not trigger retrospective rewriting of the frozen predicates, tolerances, cap or ordering.

## Unresolved architectural decisions

Only decisions that **cannot** change an experimental outcome remain open. Each closed item records where it was closed.

**Open — genuinely architectural:**

**U1 — storage substrate.** Whether D3 memory persists through the existing Core campaign-persistence mechanism, a separate append-only record, or remains in-process with deterministic serialization only. Does not affect classification, retention, permutation invariance or counts.

**U6 — scope context representation.** Whether the context reference is an opaque byte string or a structured reference. Open **only** because both satisfy the frozen §1 semantics: deterministic scope identity, exact digest equality, fail-closed cross-scope comparison, exact round-trip. Either representation yields identical E4 outcomes.

**U7 — cross-scope read surface.** Whether V0.1 exposes any read path spanning scopes. Open **only** because A8 already forbids cross-scope comparison, merge and co-retention regardless of what is listable. Listing is not comparison; no read-surface choice can change an experimental result.

**U8 — future adaptive-generation read API.** Whether D3 exposes a read interface shaped for a future generation policy, or deliberately none in V0.1.

**Also open:** concrete storage technology; generic external persistence architecture. Neither affects any gate.

**Closed by this revision:**

- **U2 — entry identity:** closed in §2. Digest covers Layer A only; Layer B never affects it. (Directly determined A7/E3.)
- **U3 — tolerance representation:** closed in §5. Absolute typed values only; no relative form; no Core default; caller-supplied study policy. (Directly determined which entries qualify.)
- **U4 — diversity partition ownership:** closed in §4/R5. Caller-declared opaque keys; D3 derives nothing. (Directly determined R5 membership.)
- **U5 — deterministic tie-break ordering:** closed in §7. Identity-only lexicographic ordering; objective-aware ordering rejected for V0.1. (Directly determined E2/A5 and cap survival.)
- **Layer A / Layer B split:** frozen as a *definition* (§ Two-layer separation); the stored-vs-derived question remains genuinely open and is tested by A13 rather than pre-answered.

## Falsifiability check

An independent implementer working only from this document has no remaining freedom that could materially change:

- **which entries qualify** — all six predicates, their inputs, inclusivity, dimensional rules and fail-closed cases are frozen (§4, §5);
- **which entries survive the cap** — cap value, scope, pre-cap classification, tier structure, overflow failure and the prohibition on reason-count priority are frozen (§6);
- **permutation invariance** — the ordering is a strict total order on identity alone, reading no objective value (§7);
- **E6 retained counts** — population size, generator, cap, policy shape and the pre-cap statistics definition are frozen (§6, E1, E6);
- **A3/A5/A6/A7/A8/A11 outcomes** — attribution uniqueness, order invariance, cap failure mode, digest invariance under re-assessment, scope identity equality and the recorded statistic set are each frozen above.

Remaining implementer freedom is confined to storage substrate, context-reference representation, read-surface breadth and API shape — none of which appear in any predicate, ordering, count or gate.

## Explicitly deferred

Successor milestones, not D3 V0.1 acceptance requirements:

- adaptive or memory-directed candidate generation;
- Bayesian / evolutionary / mixed-variable optimization;
- surrogate models trained on memory;
- relative, statistical, quantile or rank-based tolerances;
- per-reason retention quotas or partitioned caps;
- objective-aware or preference-aware tie-breaking;
- novelty search;
- multi-fidelity promotion policy;
- uncertainty-directed retention;
- cross-design-space transfer or analogy;
- LLM interpretation of retained entries;
- Generation 1 lineage semantics;
- SRIA integration;
- Core identity/integrity content hashing for `ScientificTwin` and `DesignSpace` (inherited MVR1 debt);
- `O(N^2)` archive/Pareto scaling work (inherited MVR0/MVR1 P3);
- any concrete system pack integration, including multirotor.

## Failure policy

If a concrete system pack later reveals a missing retention concept, add it through a successor milestone.

Do not insert domain-specific retention reasons, tolerances or scope rules into D3 after observing a concrete product implementation, and do not rewrite this preregistration — in particular the six predicates, the tolerance semantics, the cap semantics or the tie-break rule — after observing D3 experiment results.
