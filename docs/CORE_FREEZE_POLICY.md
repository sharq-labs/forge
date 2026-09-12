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
| frozen digest | `a8468936ef0a0bfd3fe3b32783e8957372e41f88e4e4d425076e23a905f8616a` |
| experimental symbols | `11` |
| total public symbols | `205` |
| deprecated symbols | `0` |

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

**Non-Core packages** (`5`): `domains`, `systems`, `sria`, `design`, `mcp`.
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
- That non-Core packages (`domains`, `systems`, `sria`, `design`, `mcp`) have
  any stability guarantee at all.
- Anything about behaviour, numerical results, or performance.
