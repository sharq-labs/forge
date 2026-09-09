# ScientificClaim and ContextOfUse — a design report, not an implementation

> **Result ≠ Claim.** `temperature = 350 K` is a result. *"The design stays
> below its safe thermal limit under operating condition X"* is a claim. The
> platform validates the first and has no vocabulary for the second.

**Status: DESIGN ONLY. Nothing here is implemented.** This document exists
because the round that produced it required the smallest sound contracts to be
*proposed and assessed* rather than built, and the assessment came back: the
integration is not yet demonstrably minimal. §6 says exactly what would have to
be true first.

---

## 1. What the current code already does

The core is further along than "results only". Four of the five pieces a claim
needs already exist, under other names, and none of them is a placeholder.

| Claim concept | Existing contract | What it already carries | What is missing for a claim |
|---|---|---|---|
| the question | `ScientificProblem` | variables, parameters, objectives, constraints, models, required capabilities | it is a *specification of a computation*, not a question with an answer condition. `ConstraintDefinition` is the closest thing to a decidable question and is evaluated against one result. |
| the operating regime | `ValidityDomain` + `ValidityAssessment` | conditions, per-condition outcomes, four typed UNKNOWN reasons, a prerequisite DAG | applicability is asserted **per model**, not per claim. Nothing says which regime the *claim* is about, so two claims over one run share one applicability verdict. |
| the answer | `ScientificResult` | values with units, per-model validity, uncertainty (now dimensionally bound), convergence, provenance | a result reports *what was computed*. It has no field for *what that entails*. |
| the evidence | `ValidationReport` / `ValidationCheck` / `ValidationLevel` / `CrossSolverConsensus` | outcomes, residual vs tolerance, levels that must be earned, declared independence, declared required outputs | evidence attaches to a **result**, never to a proposition. `establishes` names a *level*, not a *claim*. |
| the attribution | `ProvenanceRecord` | run, models, solvers, execution bindings, transfers, typed inputs | complete for a computation. A claim would need to name the *decision* it was made for, which nothing records. |

**The single most important observation:** `ValidationLevel` is already an
evidence-strength vocabulary, and `CrossSolverConsensus` already models
*"this evidence supports this level, and only under these declared conditions"*.
A claim layer is a generalisation of a mechanism that exists, not a new one.

**The second most important:** the core already refuses to let a strong verdict
be asserted rather than derived — `ValidationReport._require_every_level_earned`,
`CrossSolverConsensus.from_dict`, `ValidityAssessment` since this round. Any
claim contract must inherit that discipline or it will be the weakest link.

---

## 2. The four proposed contracts, at their minimum

Deliberately small. Each is a record with identity, serialization and a derived
verdict — the shape every contract in this core already has.

### 2.1 `ScientificQuestion`

```
question_id     : str
statement       : str                 # prose, for a human
subject         : str                 # the metric or entity it is about
decidable_by    : tuple[str, ...]     # result value names that can answer it
```

Not a `ConstraintDefinition`. A constraint is `metric OP bound` evaluated
against one result; a question is the thing a constraint *operationalises*, and
several constraints — or several runs — may bear on one question.

### 2.2 `ContextOfUse`

The load-bearing contract, and the reason this cannot be bolted on.

```
context_id        : str
operating_regime  : Mapping[str, ScientificValue]   # the declared point/envelope
population        : str            # which system/instance this is about
decision          : str            # what will be done with the answer
required_accuracy : Quantity | None
risk_tolerance    : str            # what a wrong answer costs
```

`operating_regime` reuses the `ScientificValue` union — the same one provenance
now records, which is what makes a context expressible at all. **Validity
becomes relative to a context** rather than absolute: a model IN_DOMAIN for a
screening decision and OUTSIDE for a certification decision is not a
contradiction, and today there is no way to say it.

### 2.3 `ScientificClaim`

```
claim_id    : str
question    : ScientificQuestion
context     : ContextOfUse
proposition : str                  # what is asserted
status      : ClaimStatus          # SUPPORTED / CONTRADICTED / INSUFFICIENT / UNTESTED
```

`status` **derived, never asserted** — from the `EvidenceRelationship` records
below, by the same recompute-and-verify rule `ValidityAssessment` now obeys.

### 2.4 `EvidenceRelationship`

```
claim_id   : str
result_id  : str
relation   : SUPPORTS | CONTRADICTS | INCONCLUSIVE | NOT_APPLICABLE
basis      : str                    # why this result bears on this claim
strength   : ValidationLevel | None # reuses the existing vocabulary
```

`NOT_APPLICABLE` is the member that earns its place: a result computed outside
the claim's `ContextOfUse` is **not weak evidence, it is not evidence**, and a
relation set without that member would let an out-of-context run dilute a claim
rather than be excluded from it.

---

## 3. Where these connect

```
ScientificQuestion ──> ScientificClaim <── ContextOfUse
                            │
                            │ EvidenceRelationship (many)
                            ▼
                      ScientificResult ──> ValidationReport ──> ValidationLevel
                            │                                        ▲
                            ├──> ValidityAssessment ──────────────────┘
                            └──> ProvenanceRecord
```

* **ScientificProblem** — a question is *upstream* of a problem: the problem is
  how you go about answering it. A `question_id` on the problem is additive.
* **ScientificResult** — unchanged. A result must not know which claims cite it,
  or it becomes unstable as claims are added; the relationship record owns the
  edge.
* **Applicability** — `ValidityDomain.assess` would take the context's
  `operating_regime` as its context mapping. **This already works**: `assess`
  accepts a `Mapping[str, Any]` and the regime is one.
* **Validation** — `ValidationLevel` becomes the `strength` of a relationship.
  No new strength vocabulary.
* **Provenance** — unchanged. A claim's provenance is the union of its cited
  results' provenance, derived rather than stored.
* **MCP, later** — the natural boundary output becomes *"here is the claim, its
  context, and every result for and against"* rather than a verdict per run.

---

## 4. Compatibility impact

| Change | Kind | Impact |
|---|---|---|
| four new records | additive | no existing record changes |
| `question_id` on `ScientificProblem` | additive, optional | `scientific_problem` schema bump; absent = no question declared |
| `ValidityDomain.assess` given a regime | **none** | already accepts a mapping |
| `ValidationLevel` as `strength` | **none** | reuse |
| `ScientificResult` | **none** | deliberately untouched |

No breaking migration is implied. That is the strongest argument *for* the
design and it is not sufficient, which §6 explains.

---

## 5. What this design deliberately does not do

* **No claim inference.** Nothing derives a claim from a result. The relation is
  declared, for the reason `CrossSolverConsensus` refuses to infer independence:
  a wrong answer awards support nobody earned and reads identically to a right
  one.
* **No claim algebra.** No conjunction, entailment or propagation between
  claims. Every one of those is a place to manufacture support.
* **No natural-language proposition parsing.** `proposition` is prose for a
  human. A parser here would be a source of confident misreadings.

---

## 6. Why this is not implemented, and what would change that

Three blockers. None is about effort.

**1. `ContextOfUse` has no producer.** Every field would be typed by hand at a
call site. The platform has no notion of a *decision* — nothing in the tree
knows what a result will be used for — so `decision`, `risk_tolerance` and
`required_accuracy` would be free-text fields nothing checks and nothing reads.
A contract whose fields no producer fills and no consumer reads is decoration,
and it is worse than absent because it *looks* like the platform models context.

**2. `ClaimStatus` has no derivation rule yet.** `ValidityAssessment` is
coherent because `classify_conditions` is a *decidable* rule over its own
fields. The claim analogue is not obvious: how many SUPPORTS outweigh one
CONTRADICTS, and does a `CROSS_SOLVER_VALIDATED` support outrank two
`UNVERIFIED` ones? **That is a scientific ground-truth decision, not a code
decision.** Guessing it would put an unearned verdict at the top of the stack —
exactly what this round spent its effort removing one layer down.

**3. No second consumer.** One boundary (MCP) would use it, and a contract with
one consumer is a refactor of that consumer wearing a core contract's clothes.
`ValidityDomain` was worth generalising because several domains declare
conditions; nothing yet makes several claims.

**What would unblock it, concretely:**

* a real decision context with a caller that populates it — an actual "may I
  ship this" flow, not a test fixture;
* a written adjudication rule for `ClaimStatus`, decided the way the thermal
  screen was decided in `benchmarks/hard/ADJUDICATIONS.json`: stated, argued,
  and recorded before any code depends on it;
* two independent claim producers, so the contract is generalised from two
  cases rather than extrapolated from one.

**Recommended next step**: implement `ContextOfUse` **alone**, as the
operating-regime carrier for `ValidityDomain.assess`. It is the one piece with a
real producer today (every applicability call already builds that mapping ad
hoc), it needs no new derivation rule, and it makes validity context-relative —
which is most of the scientific value — without asserting a claim verdict
nobody has defined how to earn.
