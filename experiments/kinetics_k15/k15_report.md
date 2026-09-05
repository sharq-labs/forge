# K1.5 — Kinetics inference-admissibility boundary: results

Status: **PASS / FROZEN**

- experiment ID: `K1.5`
- preregistration commit: `22078c713bf3ed0d7353c17b303a8aa61479a7df`
- implementation checkpoint tested: `159850913dfaf6724d00823b56e646c9af0d4869`
- environment observed for confirmatory run: Python 3.14.2, Windows/AMD64

## Scientific question

Can shared numerical inference be prevented from consuming bare arrays, ordinary solver outputs, or a merely usable `ScientificResult`, while permitting only domain-interpreted, provenance-bearing, sequence-validated numerical predictions?

**Answer: yes, for the preregistered Kinetics/CSTR boundary tested here.**

## Confirmatory evidence

### K1.5-specific suite

Command:

```text
py -m pytest tests\domains\kinetics\test_cstr_inference_admissibility.py -q
```

Observed result:

```text
5 passed in 36.23s
```

The five checks establish the preregistered boundary:

1. the shared guard rejects NumPy arrays and mappings of bare floats;
2. a bare `ScientificResult` is rejected even when `is_usable == True`;
3. construction is rejected when only single-solve validation is supplied and `NUMERICALLY_CONVERGED` was not established by a sequence;
4. H1, the preregistered cooled holdout, is admitted with typed `Quantity` observables, source provenance, physics binding, and sequence-level `NUMERICALLY_CONVERGED`;
5. the frozen K1 negative controls behave as predicted: R7 is rejected despite single-solve usability because its sequence does not establish numerical adequacy, and R8 is rejected because the domain marks the completed result scientifically unusable.

### K1/CSTR regression

Command:

```text
py -m pytest tests\domains\kinetics\test_cstr_domain.py tests\domains\kinetics\test_cstr_solver_work.py -q
```

Observed result:

```text
141 passed in 50.09s
```

This confirms the K1.5 boundary did not regress the existing K1 CSTR domain and solver-work contracts exercised by those suites.

### Full repository regression

The first full-suite attempt produced eight setup errors caused by a Windows pytest temp-directory permission failure at:

```text
C:\Users\dev_kaeem\AppData\Local\Temp\pytest-of-dev_kaeem
```

Those were environment/setup errors, not test failures. Re-running the same repository suite with a writable project-local `--basetemp` produced:

```text
1286 passed, 4 warnings in 187.31s (0:03:07)
```

The four warnings are existing scikit-learn Gaussian-process convergence warnings from `tests/test_smoke.py`; they are warnings, not failures.

The count is consistent with the previous 1281-test repository baseline plus the five new K1.5 tests.

## Acceptance criteria

- **A1 PASS** — bare numerical arrays/mappings cannot cross the shared inference boundary.
- **A2 PASS** — a bare `ScientificResult`, including one with `is_usable == True`, cannot cross the boundary.
- **A3 PASS** — a numerical prediction cannot be admitted unless its sequence report has actually attained `ValidationLevel.NUMERICALLY_CONVERGED`.
- **A4 PASS** — domain interpretation remains owned by the CSTR adapter; shared inference does not interpret CSTR metrics itself.
- **A5 PASS** — admitted observables remain typed `Quantity` values with domain-owned units.
- **A6 PASS** — admitted predictions retain source `ScientificResult` provenance and are bound to the reactor physics fingerprint.
- **A7 PASS** — H1, frozen before execution, is admitted under the unchanged K1 numerical-verification threshold.
- **A8 PASS** — R7 is rejected despite single-solve usability, proving `is_usable` is necessary but insufficient for numerical inference.
- **A9 PASS** — R8 is rejected because a completed integration outside the scientific validity envelope is not admissible inference input.
- **A10 PASS** — K1 regression and the full repository regression pass.

## Frozen architectural conclusion

For numerical forward predictions entering inference, the repository now enforces this minimum chain:

```text
domain declaration
    -> ScientificResult
    -> domain usability
    -> sequence-level numerical verification
    -> domain observable interpretation
    -> provenance + physics binding
    -> AdmissibleNumericalPrediction
    -> shared inference
```

A successful solver call, a populated metric array, or `ScientificResult.is_usable` alone is not sufficient.

This boundary is deliberately narrower than a general Scientific Study Runtime. K1.5 does not add posterior inference, parameter estimation, generic UQ, experiment design, model competition, GPU/CPU scheduling semantics, or autonomous scientific agents.

## What K1.5 does not show

- no parameter inference has been performed yet;
- no posterior has been computed;
- no identifiability claim has been established;
- no uncertainty calibration claim has been established;
- no physical experiment or real-reactor validation has been performed;
- no claim is made that every future analytic/non-numerical inference path must require `NUMERICALLY_CONVERGED`;
- no performance result changes scientific admissibility.

K1.5 is therefore frozen as a **scientific input-boundary milestone**, and K2 may build multi-parameter inference on top of it without weakening this boundary.
