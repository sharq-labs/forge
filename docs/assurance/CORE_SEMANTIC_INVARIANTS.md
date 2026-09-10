# Core semantic invariants

An audit of the **current** Core's public contracts, driven by eight questions
asked of the production code rather than of the documentation. Each was proved
or rejected independently, with a minimal reproduction first and a production
change only where the reproduction showed a defect.

Four defects were proved and repaired. Four questions resolved to *no defect*,
and those are recorded here at the same length, because an audit that only
writes down what it changed leaves the next reader to redo the rest of it.

Nothing in `benchmarks/` moved: Hard DEV 1362/1400 and battery 272/280, both
with identical case-set and split digests, before and after.

---

## The battery denominator, asked first because the number looked wrong

Historical reports say **389/400**; this round measures **272/280**. It is a
**split change**, and nothing else:

* `benchmarks/hard/cases_battery` still holds 400 cases and has not been
  touched since `fad99ff`.
* `benchmarks/hard/split_battery.json` was added in `695dd6a` (2026-09-09):
  `n_total 400, n_dev 280, n_holdout 120`, 30 % sealed, and its
  `case_set_digest` matches the corpus as measured today.
* `--split dev` therefore scores 280 seats. The 389/400 figures predate the
  split and were taken over the whole corpus.

The arithmetic agrees: 11 battery false rejects over 400, 8 of them in dev.
Nothing was changed to recover the old denominator. One piece of stale prose is
worth knowing about: `ORACLE_REGISTER.md` still says the battery corpus has
"400 cases, no sealed split".

---

## Proved and repaired

### 1. A result could declare one model at two versions — P1

`ScientificResult.models` carries `(model_id, version)` pairs. `validity`,
`validity_not_assessed`, `validity_of`, `non_assessment_reason` and
`unassessed_models` are all keyed by **model id alone**.

```
models            : (('same-model', '1'), ('same-model', '2'))
validity keys     : ['same-model']
validity_of(...)  : in_domain          <- answers for BOTH versions
unassessed_models : ()                 <- and reports no gap
"same-model@1"    : REFUSED as naming a model this result does not declare
```

`ModelRegistry` keys on `(model_id, version)`, so two versions are first-class
there, and `ProvenanceRecord` compares its models against binding keys with the
version intact. Only the result collapsed them. No shipped model has a second
version today, so no producer exercised it — but the constructor is public and
the state is reachable.

**Fixed** by refusing the declaration at construction. The alternative — keying
validity by `(id, version)` — was rejected on evidence, not on size: it changes
the serialized shape of every result ever written and the signature of four
public accessors, to express a state no producer emits and no consumer reads.
A registry *holds* versions; a run *uses* one, and a system described by two
versions of one model is not a coherent claim to begin with.

The refusal is on two *versions*, not on a repeated entry: the same model listed
twice at the same version is one claim written down twice, and still builds.

### 2. A semantic flag could be a string, and `"false"` meant True — P1

Three different behaviours across five boolean fields in one module:

| field | before |
|---|---|
| `RangeCondition.conservative_screen` | refused a non-bool (correct) |
| `FlagCondition.expected` | **`bool(value)`** — `"false"` became `True` |
| `RangeCondition.minimum_inclusive` / `maximum_inclusive` | stored raw, unchecked |
| `CrossLimitCondition.minimum_inclusive` / `maximum_inclusive` | stored raw, unchecked |

Both halves change a verdict:

```
maximum_inclusive=False    at x=1.0 -> outside_validated_domain
maximum_inclusive="false"  at x=1.0 -> in_domain          (a string is truthy)

FlagCondition(expected=False)    flag=False -> in_domain
FlagCondition(expected="false")  flag=False -> outside_validated_domain
```

**The wire format already said this was a defect.** `RangeCondition.from_dict`
refuses `{"maximum_inclusive": "false"}` with *"a serialized scientific
declaration is refused rather than guessed"*, while the constructor stored it —
so a record could be built in memory that this module's own reader will not
accept. That is not one contract; it is two.

**Fixed** with `_declared_bool`, the constructor-side twin of the `_strict_bool`
the wire path already used, applied to all five flags. It refuses rather than
coerces, because `bool("false")` is `True` and the two candidate readings of
`"false"` are opposites — there is nothing safe to guess between them.

### 3. Two registries wrote a versioned schema and read anything — P2

```
ModelRegistry       writes 'model_registry/1'
  reads 'garbage/999'     -> ACCEPTED
  reads <no schema key>   -> ACCEPTED
  reads 'model_registry/99' -> ACCEPTED
RealizationRegistry writes 'realization_registry/1'   (identically)
```

Walked rather than guessed: 183 classes in the tree implement `from_dict`, and
174 apply the exact-schema rule. Of the nine that did not, six emit no schema of
their own (nested sub-records whose parent checks) and one — `MultirotorStudyBinding`
— applies the rule by hand rather than through the helper. These two were the
scientific-core exceptions, emitting a version they never checked, which is
precisely the failure a version exists to prevent.

**Fixed** with `require_schema` in both, and `ModelRegistry`'s inline schema
string replaced by a named constant so writer and reader cannot disagree. The
schema values are unchanged; nothing is bumped.

### 4. A declared count was silently truncated — P2

`ScientificDataReference.__post_init__` ran `count = int(self.count)`:

```
count=1.9  -> 1     count=True -> 1     count='1' -> 1
count='1.2' -> bare ValueError, not a scientific refusal
ScientificDataReference(count=1.9) == ScientificDataReference(count=1)  ->  True
```

`count` is part of this record's equality, which its own docstring calls *"a
scientific question and never a storage one"*. The repository already states
what an integer declaration is: `IntegerValue` requires `isinstance(int)` and
explicitly refuses `bool`, because bool is an int subclass and accepting it
erases the distinction the union exists to keep. `count` disagreed with it.

**Fixed** by applying that same rule, and by removing the `int(...)` from
`from_dict`, which was pre-coercing around the constructor on the one path a
foreign payload takes. Zero is still a legal count.

---

## Proved *not* to be defects

### `is_usable` — behaviour correct, one axis unguarded

`is_usable` is *converged (or not applicable), and no validation check failed*.
Validity does not participate. The evidence says this is deliberate and not an
oversight:

* `transportable()` in the coupling boundary says in its own docstring that it
  deliberately does **not** use this property, and why;
* `AdmissibleNumericalPrediction` uses it as one gate and layers a separate
  sequence-level `NUMERICALLY_CONVERGED` requirement on top;
* `test_core_v02_invariants.py` pins the full 6×4 convergence × validation truth
  table;
* there are three call sites in `src/`, and none reads it as validity. (The
  `is_usable` hits under `sria/decision/` are a different class — `ScoreComponent`
  — sharing the name.)

So: **option 1, current behaviour is correct.** What was missing is that the
*third* axis was pinned by nothing — a future edit could fold validity in, or a
caller start reading it as validity, with no test objecting. Four parametrised
cases now assert independence in both directions.

### Capability layers — DEBT_ONLY

| concept | type | means | producer | consumer |
|---|---|---|---|---|
| `ScientificProblem.required_capabilities` | `frozenset[str]` | **solver** capability names | callers, domain problem builders | `ScientificSolver.support_gap` |
| `ScientificModelDefinition.required_capabilities` | `frozenset[str]` | **solver** capability names | every shipped model, as `SolverCapability.name` | `ModelRegistry.list(capability=…)` |
| `ModelRealizationDefinition.required_capabilities` | `frozenset[ScientificCapability]` | **scientific** capability | realizations | realization registry |
| `ModelRealizationDefinition.provided_capabilities` | `frozenset[ScientificCapability]` | **scientific** capability | realizations | realization registry |
| `ModelRealizationDefinition.required_solver_capabilities` | `frozenset[SolverCapabilityId]` | **solver** capability | realizations | `solver_capability_gap` |
| `ScientificSolver.capabilities` | `SolverCapability` | **solver** capability | adapters | `support_gap` |

So **yes**: `required_capabilities` names two different concepts depending on
the record, and is a typed enum on one of them and a bare string on the other
two. That is real debt.

It is **not** a wrong-support-decision defect. `support_gap` computes
`requested - declared` and refuses on any leftover, so every mismatch this
ambiguity can produce is fail-closed: a scientific identifier written where a
solver one belongs is refused, never coincidentally admitted.

One genuine strictness inconsistency was found and deliberately **not** changed:
the string fields skip `_canonical_capability_name`, so a model may declare
`"  spaced out  "` where `SolverCapabilityId` would refuse it, and
`"Mechanics:X"` and `"mechanics:x"` are two capabilities to `ModelRegistry.list`.
Both outcomes are a model that silently matches nothing — fail-closed again.
Tightening the model field to the *scientific* grammar would be actively wrong:
every shipped model populates it from `SolverCapability.name`, whose grammar is
deliberately looser so that historical unnamespaced records stay readable.

### `ScientificVariable` kinds — CONTRACT_GAP, and the rule already exists

| declaration | type | `design/sampling.py` |
|---|---|---|
| CONTINUOUS + categories | **REFUSED** | — |
| BOOLEAN + physical unit and bounds | accepted | refused |
| CATEGORICAL + numeric bounds | accepted | refused |
| INTEGER + fractional bounds | accepted | refused |
| INTEGER + bounds containing no integer (0.2 … 0.8) | accepted | refused |

The type enforces exactly one cross-field rule — categories belong to
categorical variables, both directions. Every other rule I was about to propose
**already exists**, in `design/sampling.py` and `design/space.py`, at the only
place that consumes these kinds: dimensionless, integer-valued bounds, no
numeric bounds on categorical or boolean, and a value whose type matches its
kind.

So the contract is split: the type carries the declaration, a consumer carries
the rule. That is a real gap — a second consumer inherits no refusal — and it
is not a defect today, because there is no second consumer. The variable's own
docstring says V0 only *represents* the non-continuous kinds and defers
mixed-variable search, so moving the rules onto the type would be a decision
about a deferred feature rather than a repair. Pinned as-is instead, so that
closing it is something somebody decides.

### Unit invariance — the semantic half holds; the rest is floating point

Equivalent declarations reach the same verdict for temperature (`293.15 K` /
`20 degC`), time (`120 s` / `2 minute`), resistance (`1000 ohm` / `1 kiloohm`)
and power, with the bound written either way **and** the value written either
way, on both `RangeCondition` and the ratio-producing `CrossLimitCondition`.

One case is not invariant. `_within` converts the value into the **bound's**
unit, and:

```
1 kWh      -> 3600000.0 J          (exact)
3600000 J  -> 0.9999999999999999 kWh
```

so a value exactly on an inclusive maximum lands one ulp outside it when the
bound was written in kWh. The obvious repair — normalise both operands onto the
dimension's base unit, as the ratio path already does — **was measured and is
not a repair.** Over 3,200 same-state round-trips across eight unit families:

| comparison basis | exact at the boundary |
|---|---|
| value → bound's unit (current) | 2,919 / 3,200 (91.2 %) |
| both → base unit (candidate) | 3,036 / 3,200 (94.9 %) |
| …of which the candidate is **worse** | 48 cases |

Neither basis is invariant, so there is no basis to switch to. This is a
property of floating-point unit conversion, not a defect in the comparison, and
`_within` already declares itself "Exact; no tolerance applied". Changing it
would have perturbed the arithmetic of every validity comparison in the
repository — 9 of the 72 shipped bounds are written in a non-base unit — in
exchange for trading one set of inexact pairs for another. Recorded and
asserted rather than "fixed".

---

## Semantic duplication worth knowing about

Only the duplicates that can drift are listed; none is causing a defect, and
none was refactored in this round.

* **Boolean decoding** was stated three ways in `definition.py` — `_strict_bool`
  on the wire, an inline `isinstance` for one flag, and `bool()` for another.
  This is the duplication that *was* the defect; it is now one helper per side.
* **Schema admission** is `require_schema` in 174 readers and a hand-rolled
  comparison in `MultirotorStudyBinding`. The new guard checks the rule, not the
  helper, so the hand-rolled one passes honestly.
* **Variable-kind legality** lives in `design/sampling.py`, not on
  `ScientificVariable`. See above.
* **`is_usable`** names two unrelated predicates — `ScientificResult` and
  `ScoreComponent`. Harmless, and worth knowing before grepping for callers.

---

## What now guards this

`tests/test_core_semantic_invariants.py` — 98 tests, in FAST. Written over
derived populations wherever one exists: the boolean cases come from
`dataclasses.fields`, so a flag added later is covered without editing the file,
and the schema guard walks every `from_dict` in the tree rather than listing the
ones somebody remembered.

Four mutations were added to `tests/mutation_guards.py` (76 total) and each is
RED for the guard it names:

| id | restores | killed by |
|---|---|---|
| `G25a` | one model at two versions | `test_a_result_cannot_declare_one_model_at_two_versions` |
| `G25b` | a non-boolean semantic flag | `test_a_semantic_flag_refuses_anything_that_is_not_a_boolean` |
| `G25c` | a registry that reads any schema | `test_a_registry_refuses_a_schema_it_did_not_write` |
| `G25d` | a silently truncated count | `test_a_declared_count_is_never_silently_coerced` |
