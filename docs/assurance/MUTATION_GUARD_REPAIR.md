# Mutation guard repair

`tests/mutation_guards.py` is the file that decides whether the guards in this
repository are checks or decoration. It removes one guard from a copy of the
tree, runs the suites that should notice, and calls a green result a finding.

The closing sweep of the blind challenge reported **64 of 64 applied mutations
red, 0 green, and 5 that did not apply** — and recorded, rather than fixed, that
those five guards were therefore verified by nobody. This is that round.

It did not stop at five. Measuring the harness instead of reasoning about it
found that the copied tree had been **red before any mutation was applied** for
twenty commits, which makes two of the sixty-four reds worthless and the rest
unattributable.

---

## What was wrong, and how each was established

### 1. The copy was red on its own — every result was contaminated

`_COPIED` names what the scratch tree needs to be a faithful copy. It listed
`src`, `tests`, `experiments`, `docs` and `pyproject.toml`. It did not list
`benchmarks`.

`tests/test_blind_challenge_guards.py` imports `benchmarks.blind`. GUARD 19
excuses a top-level name it can find on the path and reports every other one as
an undeclared dependency, so with no `benchmarks/` in the copy,
`test_every_dependency_the_tree_reaches_for_is_declared` failed **in every
mutated tree and in an unmutated one**.

Established by running the three target suites on an unmutated copy:

```
FAILED tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared
E   these are imported and not declared in pyproject.toml:
E       benchmarks -- e.g. tests/test_blind_challenge_guards.py:481 (3 sites)
1 failed, 301 passed
```

**Consequence.** `G19a` and `G19b` — the two mutations written to verify GUARD
19 — had that test as their *only* failure. Both were reported RED and neither
was evidence of anything: the test they relied on was already failing. The
other sixty-two had at least one genuinely relevant failure beside it, so their
conclusions survive, but no result from that harness could say which failure
was the mutation's doing.

This is the third time this tuple has done this. The comments beside it record
`experiments` and `docs` being added after the same mistake, both times with
reasoning about what a faithful copy needs. So the fix is not a third comment:
`_control` now **runs the target suites on an unmutated copy before any
mutation**, and a red control ends the round instead of quietly making every
mutation red for free.

### 2. Two mutations were reported under an id belonging to two mutations

`G8a` and `G8b` each named two entries — one electrical, one over the unit
registry. The runner writes its work tree at `mut_<id>`, so the second of each
pair deleted the first's tree before running, and the summary counted both with
nothing saying that two different files were reported under one name.

The units pair is renamed `G8d`/`G8e`, because the electrical three are cited by
id in `docs/reviews/2026-09-07-adversarial-review.md`. Worth recording while
renaming: GUARD 8 *is* the units guard, so it is the renamed pair that is named
for its guard and `G8a`–`G8c` that are historical labels on electrical
mutations. `_validate_declarations` now refuses a duplicate id outright.

### 3. The five that did not apply

| id | intended invariant | root cause of DID_NOT_APPLY | classification |
|---|---|---|---|
| `G2f` | a report re-applies GUARD 2's rule to the checks it was handed | anchored a two-line window; `6238531` inserted GUARD 21's re-check between the two lines | PATTERN_DRIFT |
| `G2g` | `attained_levels` re-applies it on the read | same insertion, same shape | PATTERN_DRIFT |
| `G22a` | a dependent condition is not evaluated until its gate holds | **never applied at any commit** — reconciled from a working tree whose gate tested the established set; `03125e0` landed the negative `unmet` form | PATTERN_DRIFT |
| `G22b` | a blocked dependent is reported as a gap, not a finding | same origin; reporting also moved into a second pass, so the name it targeted sits at another indentation | PATTERN_DRIFT |
| `G22c` | a `requires` naming an absent sibling is refused | same origin; `c9b3eba` replaced the rescan with a requirements index | PATTERN_DRIFT |

None is `SEMANTICALLY_OBSOLETE` and none is `STRUCTURALLY_ELIMINATED`: every
one of the five decisions still exists and is still reachable. The drift is
textual in all five cases.

**The G22 three were checked rather than assumed.** `git log -S` finds no
revision of `definition.py` containing `if set(condition.requires) <=
established:` or `missing = sorted(set(required) - known)`, and
`unknown.append(condition.name)` has never stood at the indentation `G22b`
named. Counting each pattern at `6238531^`, `6238531`, `03125e0`, `695dd6a`,
`52963eb` and `HEAD` gives `1,0,0,0,0,0` for the `G2` pair and `0` everywhere
for the `G22` three. So GUARD 23 has never had a verified mutation.

### 4. Two mutations did not do what they said

Both were red, and both were red for something other than their stated claim —
the vacuity this file exists to refuse, one level up.

* `G14a` passed `exclusions=None`, which is not a model that forgot to declare
  but a **type the field never accepts**, and died on `TypeError: 'NoneType'
  object is not iterable`. Its description said the tree sweep was what
  noticed. It was not, and it structurally cannot be: a model that stops
  declaring exclusions is refused at construction, so its module never imports
  and the sweep never runs. It now deletes the declaration, and the refusal is
  what meets it.
* `G14d` deleted the whole `is NOT_DECLARED` branch, which does not make
  exclusions optional — it makes an undeclared one fall into the `else` and
  iterate the sentinel. The single exempted model in the tree died on
  `TypeError: '_NotDeclared' object is not iterable`, and the claim "omitting
  them is accepted at construction instead of refused" was never exercised,
  because omitting them was not accepted. It now mutates the **exemption
  test**, which is the decision the description names.

### 5. One mutation was killed by a broken import and not by a guard

`G8a` breaks a domain module's import on purpose, and the guard that must
notice is an assertion in `test_core_guards.py` — which collected fine. Two
other target modules import that domain transitively, pytest interrupted on
their collection errors, and **zero tests ran**. The mutation was red on the
exit code and the guard was never asked. The runner now passes
`--continue-on-collection-errors`.

---

## What the harness does now that it did not

* **A control run.** The target suites, on an unmutated copy, before anything
  is believed. A red control ends the round.
* **A relevance check.** Every mutation declares the test that must be among
  the failures. A red suite without it is reported `RED (NOT THE GUARD)` and
  fails the round exactly as a green one does. This is what makes "72 of 72
  red" a claim about guards rather than about exit codes — and it is what
  caught `G21a` declaring the wrong guard, `G14d` declaring the wrong guard,
  and `G1f` declaring a refusal it no longer produces.
* **A kill mechanism per mutation**, in `EVIDENCE`, refused at load time if it
  is one of `IMPORT_OR_SYNTAX_FAILURE`, `UNRELATED_FAILURE` or `OTHER`.
* **A refusal is told from a broken import.** A mutation whose suite collects
  nothing is evidence only if it declared `REFUSED_AT_IMPORT` *and* the
  exception lines carry no `SyntaxError`, `ImportError`, `ModuleNotFoundError`
  or `NameError`. The mutated file must also parse, checked with `ast` before
  the suite is run.
* **Timeout is not redness.** `TEST_TIMEOUT` is 2400 s and a timeout is
  reported as `HARNESS TIMEOUT` — an absence of evidence, which fails the round
  without being counted as a kill.
* **Fail-closed on everything.** Duplicate id, missing kill mechanism, a
  mutation with no result, a green, a timeout, an unrelated red, or one of the
  five repaired ids gone missing.
* **Scoped targeting.** `file` may carry `::Class.function`, resolved with
  `ast`, and the text search is confined to that span. It exists because `G2f`
  and `G2g` must remove a call that appears twice in one module, and pinning
  the neighbouring line to disambiguate is what killed them. That is the whole
  of the AST here and it must not grow into a mutation framework.

`tests/test_mutation_harness.py` runs the cheap half on every FAST invocation:
all 72 mutations applied to the live source **in memory**, each landing exactly
once and changing executable tokens. It cannot say whether a mutation is
*killed* — only the slow harness can — but it turns "the pattern went stale"
from a discovery months later into a test failure in the commit that moved the
code.

---

## One guard gap, found by a repaired mutation

`G22c` removes the refusal that finds a `requires` naming no sibling. The
witness says it is not vacuous:

```
original: ModelValidityError: condition 'dep' requires ['absent'], which is not
          a condition of this validity domain...
mutant:   ModelValidityError: validity conditions ['dep'] form a dependency
          cycle. There is no order in which each is evaluated after...
```

Both refuse. Both raise `ScientificCoreError`. The guard asserted
`pytest.raises(ScientificCoreError)` and nothing else, so **for the whole life
of GUARD 23 this check could have been deleted and no test would have said
so** — and a caller would have been sent to break a cycle that does not exist.

No production code was wrong; the current refusal is correct. What was missing
was the assertion that distinguishes it, and
`test_a_dependency_that_cannot_be_satisfied_is_refused_at_construction` now
carries it. `G22c` was green until that line and is red after it.

---

## Non-vacuity, witnessed

Each repaired or new mutation was run against one minimal input on the original
source and on the mutated source. Both answers, side by side:

| id | original | mutant |
|---|---|---|
| `G2f` | refuses a tampered check at construction | accepts it |
| `G2g` | withholds the level on the read | awards `dimensionally_valid` |
| `G22a` | `dep` unknown, gate violated | `dep` **satisfied**, gate violated |
| `G22b` | `dep` reported unknown | `dep` reported satisfied |
| `G22c` | "requires `['absent']`, which is not a condition" | "form a dependency cycle" |
| `G24a` | `20 degC` parses to 293.15 K | `UnitCompatibilityError` |
| `G24b` | ratio `in_domain` | ratio `outside_validated_domain` |
| `G24c` | refuses `degC` as a coupling tolerance | admits it |

`G24a`–`G24c` are new, and cover the two unit semantics `benchmarks/blind/v1`
found: a declaration may state a temperature in degrees Celsius, a ratio of two
declarations needs a ratio scale, and the places that deliberately refuse an
affine scale still refuse it. A defect found by a benchmark and fixed once is a
defect nothing is watching, and both fixes are a single branch —
which is exactly what a later refactor straightens out.
`tests/test_offset_unit_declaration.py` joins `TARGETS` for them.

---

## Result

| | before | after |
|---|---|---|
| declared | 69 | 72 |
| unique ids | 67 | 72 |
| applied | 64 | 72 |
| red **by the guard they name** | unmeasurable | 72 |
| green | 0 | 0 |
| did not apply | 5 | 0 |
| timeout / error | 0 | 0 |
| unclassified | 69 | 0 |
| control suite | never run | green |

Kill mechanisms: 30 `CONTRACT_REFUSAL`, 8 `VALIDATION_INVARIANT`, 7 each
`SCIENTIFIC_ASSERTION`, `VALIDITY_INVARIANT` and `SERIALIZATION_INVARIANT`, 6
each `LAYERING_INVARIANT` and `PROVENANCE_INVARIANT`, 1 `TYPE_INVARIANT`. None
is a syntax or import breakage and none is an unrelated failure — both are
refused at load time and detected at run time.

`LAYERING_INVARIANT` is an addition to the categories and is recorded as one.
Six mutations attack guards that police the **tree** — what the core may know,
what SRIA may import, what a clean install must contain — rather than a
scientific record, and filing those under `OTHER` would mark six real guards as
unproven.

## What this still cannot verify

`TARGETS` is a hand-maintained list of three suites, and a guard written into a
module not named there is verified by nobody however clean the summary looks.
It cannot be derived — which suite covers which guard is a fact about intent —
so it stays written down, and the rule for the next person is unchanged.

GUARD 17's prose reach is still outside this harness: `_code_digest` drops
`COMMENT` and `STRING` tokens by a deliberate decision, so a mutation writing a
forbidden term into a docstring is refused as CHANGED NO CODE before any suite
runs. It was exercised by hand and the note in `mutation_guards.py` records how.
