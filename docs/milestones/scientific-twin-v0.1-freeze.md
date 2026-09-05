# Scientific Twin V0.1 — freeze record

Status: **PASS / FROZEN**

Milestone ID: `TWIN-V0.1`

Frozen preregistration commit: `fc3d27cdbf8600c69ded3c6d5186789c1ef24346`

Tested implementation head: `709dde3ceae708e3c6e61e05a3560f7365edfed7`

Starting stable baseline: K2 PASS/FROZEN at `5dceeb4e3ad1437c5c01aa993ac85942989c7c88`.

## Decision

Scientific Twin V0.1 satisfies its frozen acceptance criteria and is accepted as the domain-neutral scientific system-instance input contract for future studies.

The milestone is intentionally a declaration/foundation contract. It does not claim quantified uncertainty, model adequacy, evidence admission, online synchronization, autonomous discovery, cross-domain coupling, or physical validation.

## What is frozen

The accepted V0.1 contract provides:

- immutable, versioned `ScientificTwin` identity;
- `CONCEPT`, `REFERENCE`, `CANDIDATE`, `CALIBRATED`, `ENSEMBLE`, and `DERIVED` kinds;
- versioned `ModelReference` bindings;
- typed scientific declarations through existing Scientific Core value contracts;
- datum roles for parameter, state, operating condition, and control;
- deterministic schema-versioned serialization and exact round-trip;
- explicit evidence/calibration references without pretending opaque references are already admitted evidence;
- explicit parent lineage;
- `scientific_context()` built only from typed declarations, excluding metadata;
- fail-closed invariants for identity, model uniqueness, duplicate declaration names, calibrated evidence, ensemble cardinality, and derived lineage.

## Acceptance evidence

Targeted Scientific Twin suite on Windows / Python 3.14:

```text
10 passed in 0.92s
```

Command:

```powershell
py -m pytest -q tests/test_scientific_twin_v01.py --basetemp="$PWD\.pytest_tmp_twin"
```

Full repository regression on the same implementation head:

```text
1300 passed, 4 warnings in 175.43s (0:02:55)
```

Command:

```powershell
py -m pytest -q --basetemp="$PWD\.pytest_tmp_twin_full"
```

The four warnings are the pre-existing scikit-learn Gaussian-process convergence warnings from `tests/test_smoke.py`; there were no test failures or errors.

## Frozen acceptance criteria

| Criterion | Result |
|---|---|
| T1 — construct all preregistered twin kinds | **PASS** |
| T2 — reject blank identity/version and duplicate model references | **PASS** |
| T3 — reject bare numeric scientific datum values | **PASS** |
| T4 — reject duplicate/colliding declaration names | **PASS** |
| T5 — calibrated twin requires calibration evidence | **PASS** |
| T6 — ensemble requires at least two distinct model references | **PASS** |
| T7 — derived twin requires parent lineage | **PASS** |
| T8 — deterministic serialization and exact round-trip | **PASS** |
| T9 — scientific context excludes metadata side channels | **PASS** |
| T10 — full existing regression remains green | **PASS** |

## Scientific boundary

The twin is now the stable answer to **what specific scientific system instance is the study about?**

`ScientificProblem` remains the answer to **what does the study ask to compute?**

Future K3/K4/Study Runtime work must enrich or bind around this boundary rather than collapsing the two concepts.

## Next milestone

Proceed to K3 — Quantified Uncertainty. K3 should attach quantified belief/uncertainty to scientific predictions and twin-relevant state/parameters without mutating the frozen Twin V0.1 semantics post hoc.

Any future extension to the Twin contract must use a successor version or an explicitly preregistered change; this V0.1 freeze record and preregistration remain historical evidence.
