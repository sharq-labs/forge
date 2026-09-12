# Contract Guard Expansion & Semantic Mutation Closure

## 1. Final decision

**CONTRACT GUARD ASSURANCE CERTIFIED**

Scope, exactly: *record↔runtime semantic consistency protection* across the
shipped model surface. This is **not** a statement that the science is
correct. It is a statement that if a future developer changes what a shipped
model claims, or changes what it actually does, the repository fails a test.

All eight CG gates PASS. 15 of 15 planted semantic mutations were caught with
the control GREEN. No valid mutant survived. No record↔runtime contradiction
remains open. No executable scientific code changed this round.

## 2. Starting state

Taken from the machine-readable artifacts of the previous round, not from its
prose:

| Fact | Value | Source |
|---|---|---|
| Shipped models | 16 | `contract_integrity/CONTRACT_SURFACE.json` |
| Condition instances | 64 | same |
| Claims inventoried | 457 | same |
| Models with an executable contract guard | **1** (`thermal.lumped.first_order_capacity`) | `contract_integrity/FINDINGS.json` → `guard_coverage` |
| Models without | 15 | same |
| Semantic contract mutations | 5 | `contract_integrity/SEMANTIC_CONTRACT_MUTATION.json` |
| Detected | 4 | same |
| Surviving | 1 — **SC5** | same |

**SC5, exactly as the previous round defined it.** In
`src/engcore/domains/thermal_models/lumped.py`, the `heat_capacity` condition's
published description changes from

> `"Strictly positive; zero capacity has no dynamics."`

to

> `"Any capacity, including zero, is supported."`

while the structured bound stays `minimum=0.0, minimum_inclusive=False`. The
lie is an applicability claim widened past what the condition enforces: the
bound still refuses zero, the record now advertises it. The previous round
recorded the expected detector as *"(no guard known — expected SURVIVOR)"*.

## 3. Model guard matrix

Generated, not typed: `CONTRACT_GUARD_MATRIX.json` is written by
`audit/build_matrix.py` from the guards that actually run, so it cannot drift
from the suite it describes.

- 16 models assessed
- 16/16 have an executable material contract surface
- **16/16 fully guarded on every dimension applicable to them**
- 0 partially guarded, 0 unguarded, 0 blocked by ambiguous semantics

## 4. Material contract dimensions

128 cells (16 models × 8 dimensions). **88 applicable, 88 guarded, 40
NOT_APPLICABLE, 0 NOT_GUARDED, 0 BLOCKED.** The denominator that matters is 88,
not 128.

| Dim | Meaning | GUARDED | NOT_APPLICABLE | Why not applicable |
|---|---|---|---|---|
| A | required/optional inputs | 15 | 1 | `electrical.dc.kcl` declares no caller-supplied input: its one input is a solved node voltage |
| B | UNKNOWN/refusal prerequisites | 16 | 0 | — |
| C | applicability | 16 | 0 | — |
| D | route selection | 1 | 15 | only `thermal.lumped.first_order_capacity` offers a caller alternative routes to the same quantity |
| E | cross-check/evidence claims | 1 | 15 | all 8 cross-check clauses in the shipped surface are on that same model |
| F | reason/result agreement | 16 | 0 | — |
| G | capability declarations | 16 | 0 | — |
| H | state/control requirements | 7 | 9 | nine records declare no evolving state and no control input |

A claim was treated as **material** when changing it could cause a caller to
predict the wrong thing about: whether the model applies, what inputs are
required, whether a result is SUPPORTED / UNKNOWN / REFUSED, whether a
cross-check was performed, which route is used, or whether a capability is
available. Cosmetic wording was not guarded and is not counted.

### What "guarded" means here

> A model counts as GUARDED on a dimension only when an executable test
> connects its **published record** to the **actual guarded runtime
> semantics**, such that the test fails if either side drifts. Unit tests of
> the implementation, the existence of a record, a snapshot containing its
> text, and passing a benchmark do **not** count: none of them fails when the
> record and the runtime stop agreeing.

## 5. Guard implementation

`benchmarks/contract_guard/tests/test_contract_guard.py` — 18 tests, all
generic. There is no per-model fixture and no per-condition expected value
written down anywhere: every assertion is derived from the shipped records and
checked against real runtime calls, so a model or condition added tomorrow is
covered tomorrow. Sixteen near-identical test files were deliberately not
written.

| Module | Dimension | Mechanism | Volume |
|---|---|---|---|
| `guard/records.py` | — | reads the 16 shipped records and their 64 conditions from the 8 declaring modules | 64 conditions, all with structured bounds |
| `guard/enforcement.py` | C | walks each declared edge from far-inside to far-outside through `assess_validity` | **353 probes, 0 disagreements** |
| `guard/prose.py` | C | extracts the claim a description makes, turns it into values, executes them | **156 claims, 0 disagreements** |
| `guard/prerequisites.py` | A, B, D, E | re-runs the Contract Integrity claim map and constructor probes live | **110 UNKNOWN checks + 91 input checks, 0 disagreements** |
| `guard/constructors.py` | A, H | adds the DC element/rating constructor probes the previous round lacked | 6 systems now build, previously 5 |
| `guard/capabilities.py` | G | every declared capability must be served by a registered solver | 16 models, 0 unserved |

Two structural guards close the "new thing arrives unguarded" hole:
`test_no_shipped_condition_is_missing_from_the_claim_map` and
`test_nothing_declared_derives_nothing_unless_the_record_says_so`.

The Contract Integrity artifacts are **read-only inputs** to this round. Their
audit machinery is imported and re-executed; none of their files is rewritten.

## 6. Guard falsification evidence

`CONTRACT_MUTATION.json`, produced by `audit/contract_mutation.py`. Each
mutation is planted in a **temporary copy** of the repository, never in the
working tree, and one named guard is run against it.

- Control on the unmutated copy: **GREEN**
- **15 planted defects, 15 caught, 0 missed, 0 invalid**
- Every guard family targeted was falsified; no guard is called effective
  without a demonstrated RED.

| Class | Mutants | Caught |
|---|---|---|
| RECORD_TOO_BROAD | 3 | 3 |
| RECORD_TOO_NARROW | 3 | 3 |
| STRUCTURED_BOUND_DRIFT | 1 | 1 |
| RUNTIME_ENFORCEMENT_DRIFT | 1 | 1 |
| UNKNOWN_PROMISE_INVERSION | 2 | 2 |
| INPUT_OBLIGATION_DRIFT | 1 | 1 |
| PREREQUISITE_DISSOLVED | 1 | 1 |
| UNMAPPED_CONDITION | 1 | 1 |
| REFUSAL_SEMANTICS_DRIFT | 1 | 1 |
| CAPABILITY_UNSERVED | 1 | 1 |

All planted defects are reverted by construction: the mutation runner copies
the tree into a `TemporaryDirectory`, mutates the copy, and discards it. The
working tree is verified clean by gate CG-7.

## 7. SC5 root cause

1. **What promise SC5 alters.** An applicability claim: the set of values a
   caller is told the model accepts.
2. **What runtime behaviour contradicts it.** `heat_capacity`'s
   `RangeCondition` has `minimum=0.0, minimum_inclusive=False`, so
   `assess_validity` reports zero as OUTSIDE_VALIDATED_DOMAIN. The record now
   advertises zero as supported.
3. **Why the previous checker missed it.** Two independent blind spots.
   The certified 79-mutant harness drops STRING tokens from `_code_digest` and
   `test_every_mutation_changes_executable_code` refuses prose-only mutations
   — by design, and it is why 79/79 says nothing about contract integrity. The
   Contract Integrity layer looked at UNKNOWN-prerequisite clauses, and SC5
   makes no claim about prerequisites; nothing connected a record's *prose*
   to the runtime's *acceptance decision* at all.
4. **Which of the listed causes it is.** A **missing runtime probe driven by a
   missing applicability mapping**. Not a too-weak oracle and not a bad
   mutation: the mutation is a perfectly good lie that nothing was looking for.
5. **The general class.** APPLICABILITY DRIFT — the published applicability of
   a model and the applicability the runtime enforces disagree, in either
   direction, with or without a number being edited.

## 8. Closing the class (not the string)

`guard/prose.py` implements the smallest general mechanism that detects the
class. It does **not** special-case SC5's text, and it does not compare prose
against the structured bound (regex against record, which could only ever prove
the record self-consistent). It reads a *claim* out of the description, turns
that claim into concrete values, and puts those values through the real
`assess_validity` call:

- **RECORD_TOO_BROAD** — prose says a value is in scope, the runtime refuses it.
- **RECORD_TOO_NARROW** — prose says a value is out of scope, the runtime accepts it.

The mapping from English to claims is explicit, reviewable and
machine-readable: a table of restrictive patterns (`strictly positive`,
`non-negative`, `in (a, b]`, `within a factor of N`, and leading-clause
comparisons) and a table of permissive patterns (`including zero … supported`,
`any … is supported`, `no lower bound`, `unbounded below`). Both live in the
module as data with the reasoning next to them.

Two rules keep it from inventing claims:

1. Numeric bounds are read only from the **leading clause** of a description,
   because record convention states the condition's own bound first. This is
   what stops `convection_property_range_utilization` — whose later prose says
   "exactly Pr >= 0.6", a statement about the Prandtl number — from producing
   a false accusation against the ratio.
2. A bare "unbounded" or "unrestricted" is **not** in the permissive table. DC's
   `lumped_electrical_length` says "lambda is unbounded" while bounding its own
   ratio at 0.1; matching the word alone produced a confident false finding on
   the first draft.

Result on the live tree: **156 prose claims executed, 0 disagreements**, and
48 of 64 conditions restate their bound in prose with every restatement
matching the structured bound exactly.

**Proof SC5 is now detected.** CGM-1 reproduces SC5's text change verbatim and
`test_no_record_advertises_applicability_the_runtime_refuses` goes RED. CGM-2
and CGM-3 plant the same lie in `electrical.dc` and `kinetics.cstr` and are
caught by the same guard with no new code, which is what makes this a class
fix. CGM-4, CGM-5 and CGM-6 plant the opposite direction and are caught by
`test_no_record_disclaims_applicability_the_runtime_grants`.

## 9. Semantic mutation catalog and results

See §6 for the table and `CONTRACT_MUTATION.json` for the full record
(id, class, file, the drift in words, the guard, and the pytest tail).

- Total valid mutants: **15**
- Detected: **15**
- Survivors: **0**
- Invalid / DID_NOT_APPLY: **0**

This catalog is **additive and independent**. It does not touch, extend or
renumber the certified 79-mutant code suite, does not redefine its digest, and
its counts are never merged with it.

One mutation needed re-aiming during the round, which is recorded here rather
than tidied away. CGM-12 (an assembler inventing a Fourier number from an empty
declaration set) was first pointed at the UNKNOWN-prerequisite guard and
**survived**. Investigation showed why: `internal_fourier_number` publishes no
"UNKNOWN unless" clause — it is a conservative screen — so the claim map
correctly holds no declarations for it and the prerequisite review performs
zero checks on it. The claim map was not defective (all 17 of its entries
without declarations belong to conditions with no UNKNOWN clause). The gap was
a real one on the *guard* side: nothing asserted that an empty declaration set
derives nothing. `test_nothing_declared_derives_nothing_unless_the_record_says_so`
was added for it, with the one published exception — DC's electrical length,
settled by the model's own scope — allowed precisely because the record says so.

## 10. New real defects

**None.** No SHIPPED_CONTRACT_INTEGRITY, RUNTIME_IMPLEMENTATION_DEFECT,
TEST_DEFECT or AMBIGUOUS_PRODUCT_SEMANTICS finding arose. No production file
was changed.

Two **AUDIT_DEFECT**s in this round's own probes were found and fixed, and are
reported because a guard that was briefly wrong is worth knowing about:

- **CGA-1.** The first prose extractor split the leading clause at any `.`,
  which cut `<= 0.1` down to `<= 0` and produced four false RECORD_TOO_NARROW
  findings. Fixed by treating a separator between two digits as a decimal
  point. (The other two first-draft false positives are described in §8.)
- **CGA-2.** The DC rating probe withheld `rated_power` while keeping the two
  derating-line temperatures, and read the resulting refusal as the record
  calling `rated_power` optional while the runtime required it. The record
  documents the coupling — both temperatures "require a rated_power for the
  line to pass through" — so the probe was testing the coupling rule, not
  optionality. Fixed by withholding the derating line as a group.

Neither is a Core defect. The Core behaved correctly in both cases.

## 11. Existing scientific assurance status

Kept strictly separate, as two statements:

- **Executable-code mutation assurance: 79/79 RED, CONTROL GREEN** — unchanged
  and unrerun. `tests/mutation_guards.py` and its 79 mutants are untouched,
  their digest is not redefined, and none of this round's counts is merged
  into that number.
- **Semantic-contract mutation assurance: 15/15 material semantic mutants
  detected** — this round, separate catalog, separate file.

Executable scientific code did **not** change this round. The certified
scientific-core tree digest, computed by the recipe
`certification/current_core_v1.json` publishes, is
`82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507` — identical
to the certified value. No file under `src/` was modified, so the expensive
scientific benchmarks (Hard DEV, Battery DEV) were not rerun: there is no
executable change for them to re-measure. The FAST tier was run and is green
(3834 passed, 3 skipped).

## 12. Frozen artifact integrity

**No Blind V2 frozen/sealed artifact path changed.** This is a path-restricted
claim and is not a claim that the repository-wide diff is empty.

Proof: every one of the **30** artifacts named in
`benchmarks/blind_v2/FREEZE.json` was re-hashed and compared with the SHA-256
that manifest records. **30/30 byte-identical, 0 missing, 0 changed.** The check
is re-run by `audit/build_gates.py` and its result is gate CG-8.

`benchmarks/contract_integrity/*` is likewise unmodified: this round reads and
re-executes its audit modules and writes nothing into that directory. All new
files are under `benchmarks/contract_guard/`.

## 13. Remaining limitations

Stated plainly, because the numbers above are only worth the caveats under them:

1. **16 of 64 conditions state no numeric claim in prose** that this checker
   can execute (the constant-rate CSTR conditions have empty descriptions; the
   others explain *why* a bound exists without restating the number). Those
   conditions are still fully covered on dimension C by the structured
   enforcement probes; what is not covered is a prose↔runtime cross-check,
   because there is no prose claim to cross-check. Demanding one would make
   this a style checker.
2. **Only 41 of 91 declared inputs are probed by withholding them at the
   public constructor.** The other 50 are not constructor-addressable: they reach the
   model through the validity context, and their obligations are probed there
   instead — withhold it, and the condition must go UNKNOWN rather than the
   model refusing. That is a weaker statement than a constructor refusal and is
   counted separately in the matrix notes.
3. **Dimensions D and E rest on one model.** Only `thermal.lumped` offers
   alternative routes and cross-check claims today. Fifteen NOT_APPLICABLE
   cells on each are honest, but they also mean those two guards have exactly
   one subject; a second model with routes would be their first real test.
4. **The prose extractor reads a convention, not English.** It assumes a
   record's leading clause states that condition's own bound. A record that
   breaks the convention yields no claim rather than a wrong one — it
   under-fires by design — but a record could be made misleading in a way this
   mechanism does not see, for instance by stating an applicability claim only
   in a later sentence and in words the permissive table does not contain.
5. **Guarding is not correctness.** Every guard here asks whether the record
   and the runtime agree. Both could agree and both be wrong about the physics.
   That question belongs to the certification and blind-challenge rounds, not
   to this one.

## 14. Exact certification scope

This round certifies **record↔runtime semantic consistency protection** for the
16 shipped model records, across the 88 material contract dimensions applicable
to them.

It does **not** certify full scientific correctness, numerical accuracy,
validity of the underlying physics, or fitness for any particular use. It does
not extend, restate or re-derive the certified scientific-core certification,
whose scope and limits stand exactly as published.

The question the round was asked to answer:

> If a future developer changes what a shipped model CLAIMS, or changes what it
> actually DOES, will the repository automatically detect that the two no
> longer agree?

For the 88 material dimensions in the matrix: **yes**, demonstrated by 15
planted drifts, each caught by a named guard, with the control green — and with
the four limitations in §13 stated as the boundary of that yes.
