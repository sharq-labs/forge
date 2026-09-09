# What Forge says, and what Forge can establish

Two audits in one file, because they answer the same question from opposite
ends: the independence audit asks what the record can represent, and the claim
audit asks whether the words attached to it promise more than that.

Nothing here renames a public symbol. Where a name is judged too strong the
recommendation is recorded and the migration is left to a round that can plan
one.

---

## 1. Independence capability matrix

`CROSS_SOLVER_VALIDATED` is awarded when three things hold: the routes agreed
within a declared threshold, every required output was produced by every route,
and the routes were **independent**. The first two are computed. The third is
read off a declaration.

What a `SolveRoute` can carry: `route_id`, `solver` (a `SolverIdentity` of
`solver_id`/`version`/`backend`), `components` (a frozenset of
`SharedComponent`), `notes`.

| Signal | Representable? | Recorded? | Compared? | Used in verdict? |
|---|---|---|---|---|
| route id | YES | YES | uniqueness only | no |
| declared component set | YES | YES | **YES** — set intersection | **YES — this is the whole verdict** |
| solver id | YES | YES | YES → `shared_solver_identities` | **no**, by design |
| solver version | YES | YES | YES, as part of the identity | no |
| backend | YES | YES | YES, as part of the identity | no |
| model | no | no | no | no |
| realization | no | no | no | no |
| numerical method | only as a declared component | if declared | if declared | if declared |
| solver family | **no** | no | no | no |
| provider | **no** | no | no | no |
| execution settings | `SolverSettings` exists in the solver protocol but is **not on `SolveRoute`** | no | no | no |
| cached output / source | **no** | no | no | no |
| input lineage | in `ProvenanceRecord`, but consensus never sees it | no | no | no |
| shared artifacts | only as a declared component | if declared | if declared | if declared |

**The verdict rests on exactly one signal**, and it is the one nothing can
check. Everything else is either absent from the record or recorded and
deliberately unused.

### Assessment

| Question | Answer |
|---|---|
| same solver instance | can earn the level. Reported in `shared_solver_identities`, does not disqualify — a documented decision, pinned by `test_a_shared_solver_identity_is_reported_without_being_judged` |
| same solver family | not representable |
| same provider | not representable |
| same backend | recorded; does not disqualify |
| same realization | not representable |
| same numerical method | only if someone declares it |
| same cached output | not representable — two routes served one cache are indistinguishable from two that computed |
| same source evidence | not representable |
| same training/source lineage | not representable |

### Verdict on the semantics: **B — NAME/CLAIM TOO STRONG**

Not C (contract defect) and not D (capability gap in the sense of a bug). The
mechanism does exactly what its module docstring says, and that docstring is
unusually candid — it states in plain text that "a level can be earned by two
routes that carry the same solver identity, share an underlying provider, or
were served the same cached result". The default is *not* independent; silence
earns nothing; a shared component defeats the whole consensus; a caller-supplied
threshold awards nothing. This is a well-built mechanism.

The mismatch is in the **name**. `CROSS_SOLVER_VALIDATED` reads, to anyone who
has not read the module, as "two independent solvers validated this". What was
actually established is:

> routes that **declared** disjoint components agreed within a **declared**
> tolerance on a **declared** output set.

The smallest sound reading is **agreement across declared routes**. That is
defensible from the record without any new capability.

**Recommendation, not applied:** do not rename in this round. A rename touches
a serialized enum in `cross_solver_consensus/2` records and would need a schema
version and a migration. What can be done cheaply and should be: make the
*reason* string and the evidence lines say "declared-independent" wherever they
currently say "independent", so a reader of a report meets the qualifier
without having to find the module.

### Residual risk

Independence is only as good as the declaration, and nothing can tell a careless
declaration from a careful one. The record carries the declaration so a reviewer
who disagrees can see it — which converts an invisible risk into a visible one,
and does not close it.

---

## 2. Claim vs capability

| Claim, as written | Where | Actual capability | Mismatch |
|---|---|---|---|
| `CROSS_SOLVER_VALIDATED` | `ValidationLevel` | agreement between routes whose independence is declared | **YES** — see above |
| "independent" (consensus prose) | `consensus.py` | declared, never inferred; the module says so repeatedly | none — the prose is accurate and self-limiting |
| `ANALYTICALLY_VERIFIED` | `ValidationLevel` | on the reference path: a closed form agrees with a series recurrence in the same repository | **PARTIAL** — "analytically verified" suggests an external analytic solution. The check's own detail says "code verification… and not physical validation", so the record is honest even where the level name is generous |
| "Scientific Core" | package docstring | domain-neutral contracts; owns representation, not numerics — and says so | none |
| "validated" in `outside_validated_domain` | `ValidityStatus` | outside the domain the model **declares**; nothing validated that declaration | **PARTIAL** — reads as "someone validated this domain"; means "the declaration's range was exceeded" |
| "universal" | not used in `src/` | — | none found |
| "proven" / "trusted" | not used as a claim in `src/` | — | none found |
| catch rate 99.8 % (hard dev) | `results_hard.json` | true against unchanged truth, and **partly unearned**: in the `small_overshoot` family 4 of 49 scored catches fire on an unrelated condition | **YES** — the headline figure does not distinguish a catch from a coincidence |
| catch rate 100 % (battery) | `results_battery.json` | unearned, and the scorer says so in its own source: no battery case can reach SUPPORTED because the lumped body accepts no applicability declaration | none — disclosed at the point of measurement |
| "verification" (`lumped_balance_residual`) | check detail | the closed form satisfies the balance it solves | none — the detail says "no physical validation and no coupled-convergence claim" |
| `registry_fingerprint` "the value a record can cite" | `quantity.py` | **was** a per-process address hash; now reproducible across processes | closed this round |

### The pattern

The prose in this repository is consistently more careful than the identifiers.
Every overstatement found is in a **name** — an enum member or a status — and
every one of them is qualified accurately in the docstring or detail string
next to it. That is a good failure mode and a real one: names travel into
reports, dashboards and slide decks; docstrings do not.

For acquisition diligence the honest summary is: *the mechanisms do what the
code says they do, and two level names promise more than the mechanisms
establish.*

---

## 3. Scored catches that are coincidences

Worth separating from everything above because it affects a headline number.

The benchmark scores a case as caught when the verdict matches. It does not ask
whether the condition the truth names is the condition that fired. The landed
adjudication event already performs this check by hand under
`independent_violation_search`; nothing performs it automatically.

Measured on the dev split for one family:

| `adv_unsound:small_overshoot` | count |
|---|---|
| scored as caught | 49 / 50 |
| caught by the declared catcher | **45** |
| caught by an unrelated condition | 4 (U01000, U01769, U01940, U01830) |

**Recommendation:** have `score_hard.py` report a *declared-catcher* rate beside
the exact-verdict rate wherever `should_be_caught_by` names a condition the
report can identify. That is a scorer change, not a truth change, and it would
have surfaced this without a hand audit. Not done in this round — the scorer is
benchmark tooling and the round's rule is to leave the benchmark alone.
