# Sprint 10 — Core Hygiene & API Stability

Round root: `benchmarks/core_api_stability/`
Base commit: `973083e` · Branch: `claude/core-api-stability-sprint-10`

---

## 1. FINAL VERDICT

**CORE API STABILITY COMPLETE — EXPERIMENTAL SURFACES REMAIN**

Eleven symbols are public and deliberately not frozen, each with a written
reason: eight under `engcore.studies` and three field-observation symbols under
`engcore.inference`. Neither is a blocker — both are *recorded decisions* that
the Core does not promise them — but the verdict names them rather than
rounding up to "COMPLETE — READY FOR FREEZE", because a reader who sees the
shorter verdict would reasonably assume the whole public surface is frozen and
it is not.

Everything the round set out to close is closed. The frozen contract is
defined, pinned, digested, proved identical in the installed wheel, and held by
21 mutations that all fail when the guard is broken. The domain boundary was
never crossed.

**Ready for FINAL CORE FREEZE: YES** — of the 194 frozen symbols. See §37.

---

## 2. BASELINE

| | |
|---|---|
| base commit | `973083e` (Sprint 9 close) |
| FAST at base | green |
| FULL at base | green |
| certificate at base | VALID |
| domain digest at base | `81bcc7f8527833a138009a2d9b19f11aefade2537315a6e33bcacdbbc3ce9a85` |

---

## 3. DOMAIN BOUNDARY

`src/engcore/domains/**` was READ-ONLY for this round. Proved three ways, each
of which fails differently — the runner is
`benchmarks/core_api_stability/audit/domain_boundary.py`.

| check | result |
|---|---|
| `DOMAIN_START_DIGEST` | `81bcc7f8527833a138009a2d9b19f11aefade2537315a6e33bcacdbbc3ce9a85` |
| `DOMAIN_END_DIGEST` | `81bcc7f8527833a138009a2d9b19f11aefade2537315a6e33bcacdbbc3ce9a85` |
| identical | **YES** |
| `git diff 973083e -- src/engcore/domains` | **EMPTY** |
| files under `domains/` | 49, unchanged |
| regression suites | **11 suites, 355 tests, all green** |

The start digest is read out of git at `973083e` rather than from a number
recorded by hand at the start of the round. A number I wrote down earlier would
be a claim about the past, and the past is exactly what is being checked.

The third check is the one that is not redundant. Content equality says the
domain *sources* did not change; it cannot say whether the Core underneath them
still supports them. A Core change that breaks a domain would pass both digest
checks and is precisely what this boundary exists to make visible.

**No `CORE_ABSTRACTION_BLOCKER` was hit.** No Core cleanup this round required
a Domain source change.

---

## 4. PUBLIC API INVENTORY

Runner: `benchmarks/core_api_stability/audit/inventory.py` → `INVENTORY.json`

| package | `__all__` | reachable | difference |
|---|---|---|---|
| `engcore.scientific` | 118 | 132 | 14 |
| `engcore.data` | 11 | 15 | 4 |
| `engcore.inference` | 42 | 48 | 6 |
| `engcore.uq` | 7 | 9 | 2 |
| `engcore.adequacy` | 8 | 9 | 1 |
| `engcore.execution` | 11 | 12 | 1 |
| `engcore.studies` | 8 | 9 | 1 |
| **totals** | **205** | **234** | **29** |

All 29 differences are **submodule names**. Importing `engcore.scientific.units`
binds `units` on the parent package; that is Python's import machinery, not
accidental API, and removing it is not possible without breaking imports.

**Exactly one genuine leak existed, and it is gone.** `engcore.scientific`
exported the name `annotations` — a `__future__._Feature` object — because the
package `__init__` carried `from __future__ import annotations`. An AST walk
over that file found zero annotated assignments, zero annotated arguments and
zero return annotations across its 17 statements, so the directive changed
nothing about how the module compiled and did nothing but bind a public name.
Removed, with the reasoning left in place as a comment. Modules under the
package that *do* carry annotations keep their own future import.

---

## 5. FROZEN SYMBOLS

**194**, pinned in `tests/api/frozen_api_snapshot.json`.

| | |
|---|---|
| schema | `engcore.api_snapshot/1` |
| frozen digest | `c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929` |
| full digest (frozen + experimental) | recorded in `full_api_snapshot.json` |

What is frozen about each symbol is its **shape**: the name and its module; the
kind; the full signature including parameter KIND and every default; dataclass
field names in order; enum members and values; exception ancestry within
`engcore`; union members of a type alias.

Parameter kind is in the contract on purpose. Moving an argument from
keyword-only to positional-or-keyword breaks no existing call, and is still a
change to what the Core promises — `API-3` proves the guard catches it.

---

## 6. EXPERIMENTAL SYMBOLS

**11**, each with a written reason, in `api_snapshot.EXPERIMENTAL_MODULES` and
`api_snapshot.EXPERIMENTAL_SYMBOLS`.

**`engcore.studies` — 8 symbols** (whole module)
`TCR_MODEL_REF`, `TcrTruth`, `build_tcr_parameter_set`, `ols_reference_estimate`,
`synthesize_tcr_observations`, `tcr_forward_evaluator`, `tcr_forward_table`,
`tcr_prediction`

One flagship study's scaffolding, created in Sprint 8 for the linear-TCR
calibration example. Freezing it would commit the Core to a demonstration's API
forever, and a later study would either be stuck with this one's shape or have
to break a frozen contract.

**`engcore.inference` — 3 symbols** (Part M finding)
`FieldObservationOperator`, `FieldObservationKind`, `FieldObservationError`

These were classified FREEZE, and `field_observation.py`'s own docstring opens
with "A spike, deliberately". Classification was per-MODULE, and
`engcore.inference` is a genuine Core contract — so the only two things the
mechanism could express were "freeze the spike" and "stop exporting it", and
both are wrong. Classification is now per-symbol as well.

The reason recorded is not the docstring, it is the shape: a location is
spelled `probe_x`/`probe_y`, there is no `probe_z`, and resolution runs through
`StructuredMesh.node_index(i, j)`. The frozen contract would be **unable to
express an observation of a 3-D field at all** — not a gap you fill by adding
an argument, because the frozen spelling would already be wrong.

Experimental symbols are **excluded** from the frozen digest rather than merely
labelled. If they shared a digest, every edit to the study example would look
like a compatibility event, and the day nobody believes that alarm is the day a
real one goes unnoticed. `test_an_experimental_symbol_cannot_move_the_frozen_digest`
demonstrates the separation rather than asserting it.

---

## 7. INTERNALIZED SYMBOLS

**1.** `annotations`, from `engcore.scientific` — see §4.

No other symbol was internalized, because no other candidate was found. The
inventory's remaining 29 namespace-vs-`__all__` differences are all submodules.

---

## 8. DEPRECATED SYMBOLS

**0.** `api_snapshot.DEPRECATED_SYMBOLS` is empty, and that emptiness is the
claim rather than an absence of policy: nothing in the frozen Core API is on
its way out. See §21.

---

## 9. CANONICAL IMPORTS

Seven canonical modules; a symbol is frozen **at** one of them, and the same
object reachable through a deeper path is an implementation detail.

```
engcore.scientific  engcore.data     engcore.inference  engcore.uq
engcore.adequacy    engcore.execution  engcore.studies
```

| check | result |
|---|---|
| every frozen symbol importable from its canonical module | PASS |
| no frozen symbol's `module` or `defined_in` starts with `src.` | PASS |
| `CANONICAL_MODULES` == the seven Core layers | PASS |
| `src.engcore.x is engcore.x` (no twin classes) | PASS |
| `src.engcore` importable from the wheel | **False** (correct) |

`src.engcore` is an **unsupported checkout alias**, classified rather than
frozen. It is importable in a checkout because `pyproject` puts `"."` on
`pythonpath`, and eleven SHA-256-pinned experiment files still spell it that
way, so it cannot simply be removed. Object identity holding today is a useful
property — it is what stops a second package identity existing — and is
explicitly **not** a promise that the spelling is supported.

**Every package under `engcore` is now classified.** Five are recorded as
non-Core with reasons (`domains`, `systems`, `sria`, `design`, `mcp`). Before
this round a sixth appearing would have been neither frozen nor experimental
nor excluded — just unclassified, which is how an accidental public surface
starts. `test_every_package_under_engcore_is_classified_core_or_not` now fails
until someone decides.

---

## 10. API SNAPSHOT

`src/engcore/api_snapshot.py` — in the **package**, not in `tests/`, because it
has to run against the installed wheel from a process with no source checkout
on `sys.path`. A snapshot tool that only exists in the repository can compare
the repository against itself.

Nothing that varies may enter the bytes: no memory address or `repr` embedding
one, no filesystem path, no timestamp or pid, no dict insertion or set
iteration order, no `PYTHONHASHSEED`-dependent value. Defaults are rendered by
`_render_default` rather than `repr` for exactly this reason.

| | |
|---|---|
| frozen | 194 symbols, `c80e6418…` |
| full | 205 symbols, 11 experimental |
| comparison | over `canonical_bytes`, never over the file's formatting |
| guard suite | `tests/test_core_api_snapshot.py`, 17 tests |

Two things the snapshot did **not** originally record, both found this round
and both now closed:

- **Non-finite floats.** `IdentifiabilityReport.effective_sample_size` defaults
  to `float("nan")`, and the snapshot emitted the bare token `NaN` — valid for
  Python's `json`, not valid JSON, unreadable by a conforming parser. Now
  rendered as `{"kind": "literal", "type": "float", "non_finite": …}`, with
  `allow_nan=False` so the next one is a failure rather than a bad file.
- **Default factories.** The record said `has_default_factory: true` and
  stopped. That is identical for `default_factory=tuple` and
  `default_factory=list` — a change that hands every caller who omits the
  argument a mutable object instead of an immutable one, with the frozen digest
  not moving. 33 frozen fields were invisible this way. See §17.

The CLI also contradicted itself: it emitted canonical one-line bytes while the
pinned files are pretty-printed for review and the regeneration instruction
pointed at it. Following that instruction would have replaced a 345 kB
reviewable contract with a single line. The CLI now pretty-prints; both
`--digest` flags stay canonical, because those *are* the bytes.

---

## 11. SERIALIZATION INVENTORY

`tests/test_core_api_serialization.py`, 46 tests. Inventory pinned at
**61 round-trippable / 16 export-only** across the frozen population.

Fixtures are **built through public constructors**, never hand-written dicts. A
hand-written fixture tests the reader against a picture of the writer; a
constructed one tests the writer and the reader against each other, which is
the property a consumer actually depends on.

| check | result |
|---|---|
| every canonical payload round-trips | PASS |
| every canonical payload is strict JSON | PASS |
| at least half the fixtures carry a schema marker | PASS |
| every export-only record is deliberate | PASS |

`FieldObservationOperator` still round-trips and always did; the inventory is
over the FROZEN population, so the count moved from 62 to 61 when Part M
reclassified it. What changed is what the Core *promises* round-trips.

---

## 12. LEGACY FORMAT POLICY

The Core supports older payload versions, explicitly and narrowly.

| record | accepted schema versions |
|---|---|
| `ScientificResult` | `scientific_result/1 … /4` |
| `ProvenanceRecord` | `provenance_record/1 … /4` |
| `CrossSolverConsensus` | `cross_solver_consensus/1 … /3` |
| `ModelDefinition` | `scientific_model_definition/1`, `/2` |
| `ValidityAssessment` | `validity_assessment/1`, `/2` |
| `RawSolverOutput` | `raw_solver_output/1`, `/2` |
| `QuantityDependency`, `QuantityTransfer` | `/1`, `/2` |

Everything else goes through `require_schema`, which accepts exactly one
version and refuses anything else by name.

The policy has a shape worth stating: `require_schema_any` takes a **tuple of
exact strings**, not a version range, a comparison, or a migration framework. A
version is admitted only because somebody checked that this reader handles it.
A range would admit versions that do not exist yet, which is the failure
`require_schema` existed to prevent.

`SER-2` proves the refusal is load-bearing: making `require_schema` a no-op
fails 10 tests, not 1.

---

## 13. DIGEST / IDENTITY STABILITY

Scientific digests are SHA-256 over a canonical field set serialized with
`sort_keys=True, separators=(",", ":"), allow_nan=False`.

| property | result |
|---|---|
| identical across fresh processes (3 hash seeds) | PASS |
| identical twice in one process | PASS |
| no digest payload contains a path or an address | PASS |
| frozen API digest identical in fresh processes | PASS |

**MATERIAL vs NON-MATERIAL**, tested in pairs so neither direction can rot:

| change | must move the digest | result |
|---|---|---|
| a different model | yes | PASS |
| a different unit | yes | PASS |
| a different mesh | yes | PASS |
| the observed value, for evidence identity | yes | PASS |
| the same range expressed in another unit | **no** | PASS |
| a display description on a field operator | **no** | PASS |
| parameter declaration order | **no** | PASS |

`SER-3` is worth recording because its first version **survived, correctly**.
It dropped `"unit"` from `IDENTITY_FIELDS`, which drives `differences()`;
`ParameterIdentity.digest` hashes `_canonical()`, which lists `"unit"`
unconditionally. The mutation changed a *report*, not an *identity*, so the
identity test had nothing to notice — it did not do what its own description
said. Retargeted at `_canonical()`, it kills.

---

## 14. DEPENDENCY HYGIENE

`tests/test_core_api_contracts.py` and the widened `tests/test_core_guards.py`.

| check | result |
|---|---|
| every third-party import is declared somewhere | PASS |
| no runtime module reaches a benchmark-only dependency | PASS |
| declared-but-unreached | exactly `{pytest-xdist, scikit-learn}` |
| the three named packages are in the right groups | PASS |

**The blind spot Sprint 9 deferred is closed.** The existing guard checked one
direction — that everything imported is declared. Nothing checked that
everything *declared* is reachable, so a dependency could be added to
`pyproject` and never used, or used only by a benchmark while being declared as
a runtime requirement.

Closing it required widening `_reached_modules()` to include `benchmarks/`,
which in turn required reading `sys.path` mutations out of each round's files
**and its sibling `conftest.py`**, resolving path literals against both the
repo root and the round root. `DEP-2` proves it bites: removing `jsonschema`
from the new `benchmarks` extra fails.

Two distributions are declared and legitimately unreached, and are named rather
than excluded: `pytest-xdist` (a pytest plugin, loaded by the runner, never
imported) and `scikit-learn` (an optional comparison dependency).

---

## 15. CORE LAYERING

```
scientific → data → inference → uq → adequacy → studies
```

`execution` is deliberately **off** that ladder: it may import `scientific` and
`data` only, and only `studies` may import it. A sweep engine is orchestration,
not a scientific layer, and putting it on the ladder would let it reach
inference and adequacy.

| check | result |
|---|---|
| no Core package imports one above it | PASS |
| `scientific` imports no other Core package | PASS |
| `inference` reaches nothing above itself | PASS |
| the import graph is acyclic | PASS |
| no Core package reaches a non-Core one | PASS (one recorded allowance) |

Checked against **every module**, not just each package's `__init__`.

**The rule was wrong twice, and the code was right both times.** The first
version flagged `studies → execution`, which is the correct direction. The
second version forbade every Core→non-Core edge and flagged
`studies/tcr.py → domains.electrical` — also correct: `studies` is the top layer
and composing a domain is its entire job. Narrowed to one recorded allowance
(`studies` may reach `domains`, nothing else), with a second test asserting the
allowance stays that narrow, because an allowance that silently widens is worse
than no rule.

---

## 16. EXCEPTION CONTRACTS

**Seven roots, found by audit rather than assumed.** `except ScientificCoreError`
does **not** catch everything the Core raises.

| root | frozen descendants |
|---|---|
| `scientific.errors.ScientificCoreError` | 13 |
| `inference.grid.InferenceProblemError` | 4 |
| `data.errors.BulkDataError` | 3 |
| `inference.admissibility.InferenceAdmissibilityError` | 1 |
| `inference.parameters.ParameterIdentityError` | 1 |
| `adequacy.predictive.ModelAdequacyError` | 1 |
| `uq.predictive.UQProblemError` | 1 |
| **total** | **24** |

`InferenceProblemError` has a fifth member, `FieldObservationError`, which is
classified EXPERIMENTAL — this table walks the frozen population.

| check | result |
|---|---|
| the roots are exactly the seven recorded | PASS |
| every public exception descends from one of them | PASS |
| every public exception is an `Exception` | PASS |
| no public exception is a bare builtin alias | PASS |

**Deliberately not unified this round.** Reparenting twelve exception classes
onto one base is a behaviour change for every caller who currently catches a
family, and it is not an API-hygiene change — it is a redesign. Recorded as it
is, with the count pinned, so an eighth family appearing is a decision someone
has to make.

`EXC-1` proves the pin matters: reparenting `UnitCompatibilityError` onto
`ValueError` means `except ScientificCoreError` silently stops catching unit
mismatches, and the guard fails.

---

## 17. PUBLIC DEFAULTS

| | |
|---|---|
| frozen parameters carrying a default | **617** |
| mutable defaults (`list`/`dict`/`set`/`bytearray`) | **0** |
| frozen dataclass fields using a default factory | **33** |
| anonymous (lambda) factories | **0** |

Zero mutable defaults, and a guard now holds that — the value of "there are
none" is entirely in it staying true. `def f(x=[])` gives every call the same
list, and one caller appending to it changes what the next caller receives.

**The hole this round found.** The snapshot recorded `has_default_factory: true`
and nothing more, which is identical for `default_factory=tuple` and
`default_factory=list`. Swapping one for the other hands every caller who omits
the argument a mutable object instead of an immutable one, and a different type
in an `isinstance` check — and the frozen digest would not have moved. All 33
fields were invisible this way.

Now recorded as `module:qualname`, **statically**: taking a snapshot must not
execute package code, so the factory is named rather than called. A guard
rejects anonymous factories, because those are ones the snapshot can say exist
but not what they produce. `DEF-1` proves it bites.

---

## 18. DETERMINISM

| check | result |
|---|---|
| frozen digest identical under `PYTHONHASHSEED` 0, 1, random | PASS |
| scientific digests identical across fresh processes | PASS |
| the same digest produced twice in one process | PASS |
| no digest payload contains a path or an address | PASS |
| canonical bytes reject non-finite floats | PASS (`allow_nan=False`) |

`DET-1` removes the sort from the snapshot builder and the pinned comparison
fails, so the ordering is load-bearing rather than incidental.

---

## 19. WHEEL / SOURCE PARITY

`benchmarks/core_api_stability/audit/wheel_parity.py` → `WHEEL_PARITY.json`

| | |
|---|---|
| wheel built from | `git archive HEAD`, so only committed bytes ship |
| artefact | `crafty-0.4.0-py3-none-any.whl` |
| installed files | 426 (209 python modules) |
| top-level names in the wheel | `engcore`, `crafty-0.4.0.dist-info` |
| source frozen digest | `c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929` |
| wheel frozen digest | `c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929` |
| **FROZEN API PARITY** | **MATCH**, 194 / 194 |
| `src.engcore` importable from the wheel | **False** |

Packages are DISCOVERED (`[tool.setuptools.packages.find] where = ["src"]`),
never listed. An explicit list is where `src` would be reintroduced as a
distributed name, so the guard asserts the `find` mechanism itself.

---

## 20. ISOLATED WHEEL PROOF

The trap, carried from Sprint 9 and re-proved here: **`python -I` implies `-E`
but does NOT skip `site-packages`**, where this venv's editable hook for the
checkout lives. Run that way, `import engcore` resolves to the CHECKOUT and
every assertion passes while proving nothing.

So the probe runs `python -S -E`. `-S` means `site.py` never runs, so the
editable `.pth` hook is never registered; the install target is inserted by an
explicit launcher and `site-packages` is *appended* after it for the runtime
dependencies (appending a directory does not process its `.pth` files).

And the launcher **asserts provenance before it does anything else**:

```
where = pathlib.Path(engcore.__file__).resolve()
if not str(where).startswith(str(TARGET.resolve())):
    raise SystemExit(2)
```

Confirmed at `D:\fwheel_api\install\engcore\__init__.py`. Without that check
the failure is silent, which is the entire reason it is there.

---

## 21. DEPRECATION POLICY

`api_snapshot.DEPRECATED_SYMBOLS` — **empty**. `tests/test_core_api_deprecation.py`,
18 tests.

Written now precisely *because* there are no deprecations. A deprecation policy
written on the day of the first deprecation is written by somebody who wants to
ship that deprecation, and it gets shaped to permit whatever they were about to
do. Written against an empty registry it is shaped by nothing.

Every entry must carry all five of `reason`, `replacement`, `category`,
`since`, `removal`. `replacement` may be `None` — "there is no replacement" is
a real answer and a completely different one from having forgotten to write
one, which is why the FIELD is required and the VALUE may be `None`.

Rules, all enforced:

- `category` must be `DeprecationWarning` or a subclass, never `UserWarning`.
  Python silences `DeprecationWarning` by default outside `__main__`: the
  application author sees it on request, and the end user of an application
  that happens to depend on this Core is not warned about code they did not
  write. Tested on real warnings rather than asserted as a convention.
- `removal` must be a MAJOR version, later than `since`. A removal scheduled
  for a minor is not a deprecation, it is a breaking change with a warning.
- **A deprecated symbol stays INSIDE the frozen snapshot.** Dropping it on
  deprecation is the tempting alternative and is exactly backwards: the later
  deletion would then not move the frozen digest, so the removal — the only
  step a caller's program can notice — would be the one part of the lifecycle
  that passed silently.
- **An EXPERIMENTAL symbol cannot be deprecated.** You cannot withdraw a
  promise you never made.

The whole mechanism runs end to end against a **synthetic** entry injected into
the registry, which is what makes an empty policy testable.

---

## 22. FREEZE POLICY

`docs/CORE_FREEZE_POLICY.md`, enforced by `tests/test_core_freeze_policy.py`
(16 tests).

Prose does not fail a build, so the document is worth exactly its agreement
with the code. The test parses it and checks: the frozen digest, all four
symbol counts, the schema string, the round-trip count, the seven canonical
modules, the five non-Core packages, the seven exception roots, the
compatibility-event table (every row must cite a guard), every file path it
names, and every guard-test name it cites. The state table must also **add up**,
so it cannot be half-updated.

It caught its own first bug immediately: the regeneration command in step 4
omitted `--frozen`, so a maintainer following it would have written the FULL
snapshot over the frozen contract. There is now a test asserting that exact
string.

Versioning: MAJOR for a removal or a break (the only version a removal may
happen in); MINOR for growth; PATCH when the frozen digest does not move.
Adding a symbol is *not* a break and still moves the digest — the digest
answers "did the contract change", not "did the contract break".

---

## 23. SPRINT 10 MUTATIONS

`benchmarks/core_api_stability/audit/mutations.py` → `MUTATIONS.json`

**CONTROL GREEN. 21/21 written mutations KILLED. 21/23 including the two
requested-but-unwritable, which stay in the denominator.**

| id | what it breaks | verdict |
|---|---|---|
| API-1 | a frozen export removed from `__all__` | KILLED |
| API-2 | a frozen default changed | KILLED |
| API-3 | keyword-only becomes positional-or-keyword | KILLED |
| API-4 | an enum member removed | KILLED |
| API-5 | a public dataclass field order changed | KILLED |
| SER-1 | canonical field ordering dropped | KILLED |
| SER-2 | a schema version mismatch ignored | KILLED |
| SER-3 | a MATERIAL field dropped from a digest | KILLED |
| SER-4 | a NON-MATERIAL label starts affecting a digest | KILLED |
| DEP-1 | a forbidden upward dependency (inference → execution) | KILLED |
| DEP-2 | a benchmark dependency becomes undeclared | KILLED |
| M-1 | a Core package below `studies` reaches a non-Core one | KILLED |
| M-2 | symbol-level classification emptied, spike re-enters | KILLED |
| S-1 | a deprecation registered with no replacement | KILLED |
| T-1 | the policy states a frozen digest that is not real | KILLED |
| T-2 | the policy's state table no longer adds up | KILLED |
| DEF-1 | a default FACTORY swapped for a different type | KILLED |
| ALIAS-1 | a runtime module imports the checkout alias | KILLED |
| ALIAS-2 | an exempt file grows a second use of the alias | KILLED |
| DET-1 | nondeterministic ordering enters a canonical digest | KILLED |
| EXC-1 | a frozen exception reparented onto a builtin | KILLED |

**Recorded, never dropped — 2 classified `INVALID_MUTATION`:**

- **PKG-1** "exclude a frozen module from the wheel". Packaging is DISCOVERED,
  so there is no per-module list to delete a line from; a mutation would have
  to replace the discovery mechanism rather than break a guard. Covered
  directly instead: wheel parity asserts SOURCE == WHEEL over all 194 frozen
  symbols, so a missing module changes the wheel digest.
- **PKG-2** "allow the source checkout to satisfy a missing wheel module".
  Not expressible as a source edit — it is a property of how the PROBE runs.
  Proved positively instead (§20).

Two mutations were **mis-aimed and found by running them**. SER-3 survived
because it mutated `IDENTITY_FIELDS` rather than `_canonical()` (§13). EXC-1
was STALE because it patterned on a `raise` site whose indentation had moved,
and its property is about the exception ROOT anyway. Both retargeted; both now
kill. A survivor that turns out to be a bad mutation is recorded as such rather
than quietly deleted.

Kept separate from the certified 79 for the standing reason:
`tests/mutation_guards.py` is inside certified scope and pinned, so a guard
written this round cannot join `MUTATIONS` without invalidating the snapshot.
**The two numbers are never added together.**

---

## 24. DOMAIN REGRESSION

Eleven suites, **355 tests, all green**, run through the changed Core.

| suite | result |
|---|---|
| `test_electrical_v01_demo.py` | 17 passed |
| `test_kinetics_k1.py` | 30 passed |
| `test_conduction2d.py` | 30 passed |
| `test_conduction2d_assembly.py` | 33 passed |
| `test_conduction2d_convergence.py` | 9 passed |
| `test_thermal_t1_fidelity_inference.py` | 33 passed |
| `test_thermal_t2_repeated_draw_calibration.py` | 34 passed |
| `test_thermal_t3_decision_aware_fidelity.py` | 37 passed |
| `test_min_foundation_electrothermal.py` | 47 passed |
| `test_electrothermal_vertical.py` | 62 passed |
| `test_sria_e1_electrical.py` | 23 passed |

---

## 25. FAST

`pytest tests -n 4 -m "not expensive and not campaign"`

**4879 passed, 4 skipped, 0 failed** on the final tree.

Two intermediate FAST runs earlier in the round reported 4873 passed with the
two stale-certificate failures standing. Those are superseded by this one, run
after the Part R commit and before the reissue.

---

## 26. FULL

`pytest tests -n 4`

**5427 passed, 4 skipped, 0 failed** on the certified tree — the final run,
after the certificate reissue. Nothing in the suite is red.

Two earlier FULL runs stood at 5421 and 5425 passed with the two
stale-certificate failures, which is what a round looks like before its
certificate is reissued.

The first FULL run of the round was red on
`test_no_unpinned_file_spells_the_frozen_namespace` — and it was right. The two
new ALIAS mutation *definitions* name `src.engcore` in order to insert it, in a
`benchmarks/` file the scan covers. That is the guard working, not an
exception to it; the file joined the second exemption list with its count.

That failure had been latent since the round's first commit. Per-file suites
were run throughout and this one was not among them, which is the argument for
running FULL before declaring anything final rather than after.

---

## 27. GUARDS

| suite | result |
|---|---|
| `tests/test_core_guards.py` (CERTIFIED) | 247 passed |
| `tests/test_core_api_snapshot.py` | 17 passed |
| `tests/test_core_api_contracts.py` | 19 passed |
| `tests/test_core_api_layering.py` | 13 passed |
| `tests/test_core_api_serialization.py` | 46 passed |
| `tests/test_core_api_deprecation.py` | 18 passed |
| `tests/test_core_freeze_policy.py` | 16 passed |
| `tests/test_trust_boundary_package_identity.py` | 9 passed |

---

## 28. EI / RI / FM / SP

**Carried forward, NOT re-measured this round**, and labelled as such.

| family | total | killed | survivors |
|---|---|---|---|
| EI — evidence pairing integrity | 10 | 10 | 0 |
| RI — route independence authority | 12 | 11 | 1 (RI2b) |
| FM — field and mesh records | 8 | 8 | 0 |
| SP — spatial profiles | 10 | 10 | 0 |
| | **40** | **39** | **1** |

RI2b is a **known equivalent mutant**, proven equivalent in Sprint 3 by running
the mutation in memory: the verdict gate already excludes a shared
implementation, so removing the second check changes no reachable behaviour. It
is recorded as a survivor rather than excluded from the count.

**Why carrying forward is defensible here, stated so it can be disputed:** the
only Core *source* changes this round were the removal of a no-op
`from __future__ import annotations` from `engcore/scientific/__init__.py` and
the addition of `src/engcore/api_snapshot.py`, a new module nothing else
imports. Neither touches the evidence, route, field/mesh or spatial-profile
surfaces these families mutate. Everything else this round is tests, benchmarks
and documentation.

---

## 29. 79-MUTANT HARNESS

**CONTROL GREEN. 79/79 killed. 0 survivors.**

| | |
|---|---|
| runner | `tests/mutation_guards.py` |
| command | `python -X utf8 tests/mutation_guards.py <scratch-dir>` |
| control | GREEN — **470 passed** against an unmutated copy |
| total | 79 |
| killed | **79** |
| survivors | **0** |
| log | 34 876 bytes, sha256 `f3d9d34e0e9317d7db20119655b1a0cf5789aacaa85ed484b7a44ed4c1edb67c` |

**Re-run, not carried forward, because the certified POPULATION changed.** Two
files inside certified scope were edited this round:
`src/engcore/scientific/__init__.py` (the future-import removal) and
`tests/test_core_guards.py` — which is in the HARNESS area, meaning it is one
of the four suites *every one of the 79 mutants is run against*. "79/79 killed"
is a statement about exact bytes; a changed suite means the sentence has to be
re-earned rather than repeated.

The control is not a formality. It runs the four target suites against an
**unmutated** copy of the tree, so that a red result below is the mutation
being caught rather than the copy being broken.

**The tree was static for the whole run.** The harness started at `6c445e4`;
the only working-tree change while it ran was `ROUND_REPORT.md`, a markdown
file under `benchmarks/`. `git diff --name-only 6c445e4..HEAD` filtered to
certified scope and to the four target suites returns nothing.

**Kept separate from the 21 Sprint 10 mutations and never added to them.**
Different populations, different scopes, different meanings — 79 is a
certified number about the scientific core, 21 is a round-local number about
API guards.

---

## 30. WHEEL

Built, installed and probed in isolation. See §19 and §20. **MATCH.**

---

## 31. CERTIFICATE

**Reissued once, at the end of the round, on a clean tree. VERIFY: OK.**

| | |
|---|---|
| certified files | 76 |
| aggregate digest | `619f43f7d1625f19c9a6bb98b401d79f4f9907695836a3dd2f4b72cc48927ca5` |
| certified commit | `b32f67d7ad16c1e535da4997c6db3858ed62fc4e` |
| `--verify` | **certificate matches the tree — OK** |
| `tests/test_core_certificate.py` | **28 passed, 1 skipped** |

A reissue was *necessary*, not housekeeping: two files inside certified scope
changed (§29). No digest was hand-edited; the certificate was built by the tool
and verified by the tool.

**A first build attempt was discarded.** It used `--allow-dirty` to pick up the
still-uncommitted assurance file, and marked itself diagnostic — its own
verifier refused it with *"this certificate was built with `--allow-dirty` and
is marked diagnostic; it does not certify a commit"*. That refusal is the
mechanism working. The assurance file was committed and the certificate built
again on a clean tree, which is the one that stands.

The certificate embeds the Sprint 10 assurance document
(`certification/sprint10_assurance.json`): the 79-mutant result, the 8 suite
runs, the harness identity digests, the frozen API digest, wheel parity, and
the domain boundary digests. The carried-forward families (EI/RI/FM/SP and the
Sprint 9 runtime families) are marked `re_measured_this_round: false` **inside
the document**, with the reason, rather than left for a reader to infer.

`tests/test_core_certificate.py` was red for the whole round — 2 failed, 26
passed — and is green after the reissue. That red is recorded in the assurance
document's `certification_suite` entry, because the suites are measured before
the certificate is written and the certificate suite necessarily fails at
measure time. Stating it is better than quietly re-measuring it afterwards.

---

## 32. DOMAIN DIGEST

`81bcc7f8527833a138009a2d9b19f11aefade2537315a6e33bcacdbbc3ce9a85` at both ends.
See §3.

---

## 33. FILES CHANGED

**22 files.** Zero under `src/engcore/domains/`.

**New — runtime (1)**
`src/engcore/api_snapshot.py`

**Modified — runtime (2)**
`src/engcore/scientific/__init__.py` (the one genuine leak), `pyproject.toml`
(the `benchmarks` extra)

**New — tests (7)**
`tests/api/frozen_api_snapshot.json`, `tests/api/full_api_snapshot.json`,
`tests/test_core_api_snapshot.py`, `tests/test_core_api_contracts.py`,
`tests/test_core_api_layering.py`, `tests/test_core_api_serialization.py`,
`tests/test_core_api_deprecation.py`, `tests/test_core_freeze_policy.py`

**Modified — tests (2)**
`tests/test_core_guards.py` (CERTIFIED — dependency reachability),
`tests/test_trust_boundary_package_identity.py` (the second exemption list)

**New — docs (1)**
`docs/CORE_FREEZE_POLICY.md`

**New — benchmarks (8)**
the four audit runners and their four JSON artefacts

---

## 34. COMMITS

| | |
|---|---|
| `b843a07` | inventory, classify and pin the public Core API |
| `4275af3` | canonical imports, package identity, layer direction |
| `d703232` | close the benchmark dependency blind spot Sprint 9 deferred |
| `a08f807` | close the eight points — alias, experimental, deps, exceptions |
| `c5105f7` | serialization policy, material identity, digest determinism |
| `16a2329` | wheel parity and the isolated-import proof |
| `3f9002f` | make the Sprint 10 mutation matrix say what it claims |
| `da40797` | Part M — classify the experimental surface, all of it |
| `1dd6ce1` | Parts S and T — deprecation policy, and a freeze policy that fails |
| `a75f5e3` | Part V — prove the domain boundary held, three ways |
| `ab8ee0e` | Part R — record WHICH default factory, and the alias exemption |
| `6c445e4` | re-run wheel parity on the Part R tree |

---

## 35. PUSH

Branch `claude/core-api-stability-sprint-10` → `origin` (`sharq-labs/forge`).

`git diff --stat origin/main HEAD` is **exactly this round**: 23 files, zero
under `src/engcore/domains/`. `origin/main` carries four merge commits this
branch does not, all of them merges of branches whose content is already in
this lineage — `973083e` is an ancestor of `origin/main`.

Push result and the remote/local HEAD comparison are recorded below the table
in §35 RESULT.

---

## 36. REMAINING CORE BLOCKERS

**None.**

Three things are deliberately left open, and none of them blocks a freeze:

1. **Eleven experimental symbols** (§6). Recorded decisions that the Core does
   not promise them, not unfinished work. Freezing either population would be
   the mistake.
2. **Seven exception roots, not one** (§16). Unifying them is a behaviour
   change for every caller who catches a family — a redesign, not API hygiene.
   Recorded and pinned so an eighth cannot appear quietly.
3. **`src.engcore` remains importable in a checkout** (§9). Eleven
   SHA-256-pinned experiment files spell it, so removing it means re-pinning
   frozen artefacts. Classified as unsupported, proved to be the same objects,
   proved absent from the wheel.

---

## 37. READY FOR FINAL CORE FREEZE?

**YES**, for the 194 frozen symbols.

The contract is defined, pinned by digest, reviewable as pretty-printed JSON,
compared over canonical bytes, proved byte-identical in a wheel imported with
no checkout on `sys.path`, layered acyclically, free of mutable defaults,
deterministic across hash seeds, and held by 21 mutations every one of which
kills. The deprecation and freeze policies exist before they are needed and
both fail when the code disagrees with them. The domain boundary was never
crossed.

The eleven experimental symbols are outside that freeze **by decision**, which
is what the verdict in §1 says rather than rounding away.
