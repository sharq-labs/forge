# Core API Freeze Policy

<!--
  PART T. This document is EXECUTABLE: `tests/test_core_freeze_policy.py` parses
  it and fails when it stops matching the code. Every number, digest, file path
  and classification name below is checked. Editing prose here is free; editing
  a fact is a test failure until the code agrees.
-->

## FROZEN-STATE

| key | value |
| --- | --- |
| schema | `engcore.api_snapshot/1` |
| frozen symbols | `194` |
| frozen digest | `f18aa806d594016c04b3f9ace6b0817969e8042febd22324f6eb8a95aef6f487` |
| experimental symbols | `11` |
| total public symbols | `205` |
| deprecated symbols | `0` |

**Core Freeze V4 (2026-09-18).** The digest above moved from
`c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929`, which Core Freeze V1 recorded, and
the 2026-09-16 scientific core re-audit is why: 31 improvements added new enum members, new trailing
dataclass fields with defaults and new keyword arguments with defaults. The count did not move -- the
same `194` symbols, in the same seven modules -- and **every** difference from the V1 surface **as V1
committed it** is one of those additive kinds, proved difference by difference by
`tools.certification.core_freeze_v4.additive_only_problems` and recorded in
`certification/core_freeze_v4.json`. A digest that moves without that proof beside it is a broken
contract, which is what §10 has always said.

The frozen digest is the compatibility number. It is a SHA-256 over the
canonical bytes of the frozen snapshot, and two processes on two machines
compute it identically: nothing that varies — an address, a path, a timestamp,
a hash seed, a dict insertion order — is allowed into the bytes.

---

## 1. What is frozen

The frozen contract is the `194` symbols recorded in
`tests/api/frozen_api_snapshot.json`, exported from exactly seven canonical
modules:

```
engcore.scientific   engcore.data       engcore.inference   engcore.uq
engcore.adequacy     engcore.execution  engcore.studies
```

A symbol is frozen **at** its canonical module. The same object reachable
through a deeper path (`engcore.inference.parameters.ParameterIdentity`) is an
implementation detail and carries no promise; `engcore.inference` is the
contract.

What is frozen about each symbol is its **shape**, not its behaviour:

- that the name exists, in that module;
- its kind (function, class, dataclass, enum, exception, constant, alias);
- its full signature, including parameter **kind** — positional-only,
  positional-or-keyword, keyword-only, var-positional, var-keyword — and every
  default value;
- for a dataclass: its field names, in order;
- for an enum: its members and their values;
- for an exception: its inheritance chain within `engcore`;
- for a type alias: the members of the union, by name.

## 2. What is NOT frozen

**Experimental symbols** (`11`). Recorded in
`api_snapshot.EXPERIMENTAL_MODULES` and `api_snapshot.EXPERIMENTAL_SYMBOLS`,
each with a written reason. They are still snapshotted, so a change to one is
still visible; they are simply not a promise. They are excluded from the frozen
digest rather than merely labelled, so that editing the flagship study cannot
look like a compatibility event. The day nobody believes that alarm is the day
a real one goes unnoticed.

**Non-Core packages** (`7`): `domains`, `systems`, `sria`, `design`, `credibility`, `mcp`,
`claims`.
They live under `engcore` and are not part of the Core API. Recorded in
`tests/test_core_api_layering.py::NON_CORE_PACKAGES`, because a package that is
neither frozen nor experimental nor excluded is an accidental public surface.

**Anything not exported from a canonical module.** A name reachable only by
importing a submodule directly is internal, regardless of whether it starts
with an underscore.

**Behaviour, performance, and numerical output.** This policy is about the
shape of the API. A solver that returns a better answer through the same
signature has not broken it.

## 3. What counts as a compatibility event

Each of these moves the frozen digest, and each has a guard that fails:

| event | guard |
| --- | --- |
| a frozen symbol is removed or renamed | `test_the_public_api_matches_the_pinned_snapshot` |
| a required argument is added or removed | `test_parameter_kinds_and_defaults_are_unchanged` |
| a default value changes | `test_parameter_kinds_and_defaults_are_unchanged` |
| a keyword-only argument becomes positional | `test_parameter_kinds_and_defaults_are_unchanged` |
| an enum member or value changes | `test_enum_members_and_values_are_unchanged` |
| a public dataclass field is removed or reordered | `test_public_dataclass_fields_keep_their_order` |
| an exception's base changes | `test_the_exception_roots_are_exactly_the_seven_recorded` |
| a symbol is deprecated | `test_deprecating_a_symbol_does_move_the_frozen_digest` |
| a new exception family appears | `test_the_exception_roots_are_exactly_the_seven_recorded` |
| a layer imports one above it | `test_no_core_package_imports_one_above_it` |
| a Core package reaches a non-Core one | `test_no_core_package_imports_a_non_core_one` |
| a new package appears unclassified | `test_every_package_under_engcore_is_classified_core_or_not` |
| the wheel stops matching the source | `benchmarks/core_api_stability/audit/wheel_parity.py` |

**Adding** a new symbol, a new enum member, or a new keyword argument with a
default is NOT a compatibility event for existing callers — but it still moves
the frozen digest, and still has to be a decision. That is deliberate: the
digest answers "did the contract change", not "did the contract break".

## 4. Versioning

- **MAJOR** — a frozen symbol is removed, renamed, or changed in a way that
  breaks an existing call. The only version in which a removal may happen.
- **MINOR** — the frozen surface grows: new symbols, new enum members, new
  defaulted arguments. Existing callers are unaffected.
- **PATCH** — the frozen digest does not move.

## 5. Deprecation lifecycle

Registry: `api_snapshot.DEPRECATED_SYMBOLS`. Currently **empty**, and that
emptiness is the claim: nothing in the frozen Core API is on its way out.

Every entry carries all five of `reason`, `replacement`, `category`, `since`,
`removal`. `replacement` may be `None` — "there is no replacement" is a real
answer, and a completely different one from having forgotten to write it.

- `category` must be `DeprecationWarning` or a subclass, never `UserWarning`.
  Python silences `DeprecationWarning` by default outside `__main__`, which is
  what a library wants: the application author sees it on request, the end user
  is not warned about code they did not write.
- `removal` must name a MAJOR version, and must be later than `since`. A
  removal scheduled for a minor is not a deprecation, it is a breaking change
  with a warning attached.
- A deprecated symbol stays **inside** the frozen snapshot. If deprecation
  removed it, the later deletion would not move the frozen digest, and the
  removal — the only step a caller's program can notice — would be the one part
  of the lifecycle that passed silently.
- An EXPERIMENTAL symbol cannot be deprecated. You cannot withdraw a promise
  you never made.

## 6. Serialization and identity

Two separate freezes, deliberately not one:

**Serialization.** `61` frozen records round-trip through `to_dict` /
`from_dict`; the rest are export-only. The schema string on every payload is
checked on the way back in, so an unknown version is a refusal rather than a
silently mis-parsed record.

**Legacy formats.** Eight frozen readers accept older schema versions, each
through an explicit tuple of exact version strings — never a range:
`ScientificResult` (`/1`–`/4`), `ProvenanceRecord` (`/1`–`/4`),
`CrossSolverConsensus` (`/1`–`/3`), and `RawSolverOutput`,
`ScientificModelDefinition`, `ValidityAssessment`, `QuantityDependency`,
`QuantityTransfer` (`/1`, `/2`). Every other reader accepts exactly its current
version. The table is part of Core Freeze V1: the freeze manifest derives it
from each reader's source and the verifier fails if a declared version is
dropped. Adding a new accepted version is not a break; removing one is.

**Scientific identity.** A digest is computed over a canonical field set with
`sort_keys=True, separators=(",", ":"), allow_nan=False`. MATERIAL fields enter
the digest; NON-MATERIAL ones (display labels, descriptions) must not. Both
directions are tested in pairs: a material change must move the digest, a
non-material change must not.

## 7. Packaging

Packages are DISCOVERED (`[tool.setuptools.packages.find] where = ["src"]`),
never listed. `src` is not a distributed package name and `src.engcore` is not
a second package identity.

The installed wheel is proved to expose the same frozen API as the source, by
a probe running under `python -S -E` that asserts `engcore.__file__` lives under
the install target before importing anything else. `-S` matters: `python -I`
implies `-E` but does NOT skip site-packages, where this checkout's editable
`.pth` hook lives, so `-I` would import the checkout and pass while proving
nothing.

## 8. Changing something frozen

1. Make the change.
2. Run the API suites. They fail, and the diff names what moved.
3. Decide whether it is MAJOR, MINOR, or not a compatibility event.
4. Regenerate:
   `python -X utf8 -m engcore.api_snapshot --frozen > tests/api/frozen_api_snapshot.json`
5. Update the FROZEN-STATE table at the top of this document.
6. Record the event, with the reason, in the commit.

Step 5 is not bookkeeping. `tests/test_core_freeze_policy.py` reads that table
and fails until it matches the code, which is what keeps this document from
becoming a description of a version of the Core that no longer exists.

## 9. What this policy does not promise

- That `except ScientificCoreError` catches everything the Core raises. It does
  not: there are **seven** exception roots, found by audit rather than assumed.
  Each family is catchable by its own base, and that is the property a caller
  can rely on.
- That experimental symbols will survive, keep their shape, or be deprecated
  before they change.
- That non-Core packages (`domains`, `systems`, `sria`, `design`, `mcp`,
  `claims`) have any stability guarantee at all.
- Anything about behaviour, numerical results, or performance.

## 10. Core Freeze V1

The contract described above is frozen as **Core Freeze V1**, tagged
`v1.0-core-freeze`. It is executable, not prose:

```
python -m tools.certification.core_freeze --verify
```

The manifest is `certification/core_freeze_v1.json`; the assurance that
certified it, and the commit it was run on, are in
`certification/core_freeze_v1_assurance.json`. The verifier reads both and
compares them with the tree; it never regenerates what it expects.

On the freeze commit every check binds, down to the bytes of `src/`. On a
**later** commit the byte-level checks become informational and the CONTRACT
checks still bind: the frozen API digest, the experimental set, the
serialization inventory and legacy table, the identity reference digests, the
declared ordering of results and failures, and the exception families. A later
commit that fails a contract check is not a descendant of Core Freeze V1.

**Allowed without breaking the freeze**

- bug fixes that preserve frozen behaviour
- internal refactors that preserve frozen contracts
- performance improvements that preserve exact semantics
- new tests
- documentation
- new Domain work
- new optional internal implementations

**Requires a Core compatibility review**

- removing or renaming a frozen symbol
- changing a signature, including required or default arguments
- changing enum members or values
- breaking a supported serialization format, current or legacy
- changing material digest semantics or evidence identity semantics
- changing trust or admission semantics
- removing public result fields
- changing stable exception classes or their family roots

**Requires a new Core Freeze version**

Any *intentional* incompatible change to the frozen contract. A review that
concludes a change is incompatible does not make it compatible; it makes it
Core Freeze V2.

## 11. Experimental surfaces under the freeze

Experimental public surfaces are **excluded** from Core Freeze V1. They stay
importable, and they stay visibly classified EXPERIMENTAL in the API snapshot.
**EXPERIMENTAL != FROZEN**: an experimental symbol may change without violating
the frozen API.

Promotion of an experimental symbol requires, in order:

1. an explicit API review;
2. a compatibility review;
3. tests;
4. inclusion in a later freeze manifest.

What is forbidden is the silent version: removing a symbol from
`EXPERIMENTAL_SYMBOLS` or `EXPERIMENTAL_MODULES` so that it lands in the frozen
digest. The frozen digest then no longer matches Core Freeze V1, and the
verifier fails — which is the intended outcome, not an obstacle to route around.

## 12. Core Freeze V2 (additive)

Core Freeze V2, tagged `v2.0-core-freeze`, ADDS one canonical module and changes nothing above. Every number in
the FROZEN-STATE table at the top of this document is still the V1 contract and still binds: the V1 frozen
digest does not move, the V1 verifier still passes, and V1 history is not rewritten.

| key | value |
| --- | --- |
| added canonical module | `engcore.hybrid_uq` |
| V2 frozen snapshot | `tests/api/v2_frozen_api_snapshot.json` |
| V2 manifest | `certification/core_freeze_v2.json` |
| V2 verifier | `python -m tools.certification.core_freeze_v2 --verify` |
| API design | `docs/CORE_V2_API_DESIGN.md` |

The V2 surface is `api_snapshot.build(modules=api_snapshot.V2_CANONICAL_MODULES)`. The V2 verifier binds on:

- Core Freeze V1 still verifying;
- every V1 frozen entry being byte-identical inside V2;
- the V2 frozen digest and pinned snapshot;
- the V2 serialization inventory and identity reference digests;
- the route vocabulary;
- the thin-ridge repair still being in force.

A later commit that fails any of these is not a descendant of Core Freeze V2.

Since Core Freeze V3 (section 13) the V2 serialization contract is superseded for descendants; the V2
manifest, assurance and tag remain the record of that freeze and are never rewritten.

## 13. Core Freeze V3 (hardened routed uncertainty)

The main adversarial audit of 2026-09-15 found Hybrid UQ records accepted while contradicting their own
numbers. The fixes re-derive every route claim from the carried numbers on read, commit the multistart policy
actually used, and cover the log-likelihood in the grid digest. Core Freeze V2's identity references are
literal records of exactly the refused kind, so the V2 serialization contract cannot hold on a correct tree.
Under section 10 an incompatible change is a new freeze: Core Freeze V3, tagged `v3.0-core-freeze`.

| key | value |
| --- | --- |
| frozen API | unchanged: the V2 surface and pinned V2 snapshot bytes, the V1 frozen digest above |
| V3 manifest | `certification/core_freeze_v3.json` |
| V3 verifier | `python -m tools.certification.core_freeze_v3 --verify` |
| superseded | the Core Freeze V2 serialization inventory and identity references (history untouched) |
| audit | `docs/audits/MAIN_AUDIT_2026-09-15.md` |

The V3 verifier binds on:

- Core Freeze V1 still verifying, with its manifest unchanged;
- the Core Freeze V2 manifest bytes unchanged (history, recorded by digest);
- the live frozen API surface being exactly the one Core Freeze V2 recorded, so V3 moves no shape;
- the V3 serialization inventory and identity reference digests, over records consistent with their numbers;
- the V2 identity references still being refused by the hardened readers;
- the route vocabulary and the thin-ridge repair;
- the certificate covering every area in which the audit found a false accept.

Shape changes the audit showed are needed are NOT part of V3. They are stated in the V3 manifest as deferred
non-claims and require their own compatibility review and freeze.
