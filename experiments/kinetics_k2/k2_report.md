# K2 — Multi-parameter Arrhenius inference final science report

Status: **PASS / FROZEN**

Experiment ID: `K2`

Scientific source commit: `eab5879e8c17d5c1cf8f697f0eb2e57816cc99b5`

Frozen preregistration commit: `824a4167a7ebead813dc3b023b9ace31742e3789`

K1.5 frozen inference-admissibility boundary: `f479777d67295355fbf3fcf7877cd834d30eee99`

K2 freeze checkpoint commit: `9affbcedd2e21a9ccbff4e3d103afc96a95c9625`.

## Scope

K2 is the first scored multi-parameter Bayesian inference milestone for the Kinetics/CSTR domain. It tests whether two correlated Arrhenius parameters can be recovered from noisy multi-condition observations while preserving the K1.5 inference-admissibility boundary and whether the frozen three-condition study improves identifiability relative to the deliberately weak C2-only control.

K2 does **not** claim physical validation, calibrated solver/model uncertainty, model competition, experiment design, or digital-twin state estimation. Those remain outside the frozen K2 scope.

## Frozen scored run

Primary scored execution used the frozen `61 x 61` Cartesian reference grid (`3,721` parameter points) and the frozen source commit above.

The original parallel forward grid produced:

- parameter points: `3,721`
- admitted points: `3,686 / 3,721`
- admissible fraction: `0.9905939263638807`
- condition evaluations attempted: `11,163`
- admitted condition evaluations: `11,128 / 11,163`
- rejected condition evaluations: `35`
- workers: `24`
- forward wall time: `1357.49 s` (`22m 37.49s`)

The scored CPU parity run reused the source-bound verified forward cache, then independently rebuilt the full `3,721`-point serial reference with one worker for A9.

Command used:

```powershell
py .\experiments\kinetics_k2\k2_run.py `
  --reuse-forward-cache `
  --cpu-parity
```

The verified cache was bound to the exact K2 source commit, preregistration, parameter grid, condition declarations, parameter names, and observation columns before reuse.

## Primary multi-condition posterior

Parameter order: `log_k0`, `e_over_r_k`.

- posterior mean: `[20.979314794931746, 8775.076414950117]`
- posterior std: `[0.15202805349527396, 49.51789691706498]`
- MAP: `[21.03027718267895, 8791.666666666666]`
- 95% marginal credible interval for `log_k0`: `[20.646513000513277, 21.03027718267895]`
- 95% marginal credible interval for `e_over_r_k`: `[8666.666666666666, 8791.666666666666] K`
- covariance:

```text
[[0.02311252904956188, 7.527989120383729],
 [7.527989120383729, 2452.022115089074]]
```

- covariance determinant: `0.001812168548599421`
- posterior correlation: `0.9999840117764515`
- admissible fraction: `0.9905939263638807`

The posterior remains strongly correlated, as expected for the Arrhenius pair, but the multi-condition design sharply contracts the ridge.

## Weak C2-only posterior

- posterior mean: `[21.07347982427268, 8806.143839722085]`
- posterior std: `[1.1959411184598971, 388.8372838352901]`
- MAP: `[21.414041364844625, 8916.666666666666]`
- 95% marginal credible interval for `log_k0`: `[18.727692089684908, 22.949098093507324]`
- 95% marginal credible interval for `e_over_r_k`: `[8041.666666666667, 9416.666666666666] K`
- covariance:

```text
[[1.4302751588231097, 465.0223121929614],
 [465.02231219296146, 151194.43330040597]]
```

- covariance determinant: `3.891264620109364`
- posterior correlation: `0.9999910028010043`
- admissible fraction: `0.9905939263638807`

## Identifiability finding

Relative to the weak C2-only control, the frozen three-condition study reduced the marginal standard deviations by approximately:

- `log_k0`: `7.87x`
- `e_over_r_k`: `7.85x`

The weak/multi posterior covariance-determinant ratio is approximately `2147.3x`.

This is evidence of a substantially narrower joint posterior under the frozen multi-condition design. It is not evidence that the Arrhenius parameters are decorrelated: the posterior correlation remains close to `1`.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A1 — truth-condition admissibility | **PASS** |
| A2 — finite normalized posterior | **PASS** |
| A3 — truth in both 95% marginal credible intervals | **PASS** |
| A4 — posterior-mean point accuracy | **PASS** |
| A5 — identifiability gain vs weak C2 | **PASS** |
| A6 — ridge reduction vs weak C2 | **PASS** |
| A7 — repeated recovery across frozen seeds | **PASS** |
| A8 — deterministic replay | **PASS** |
| A9 — serial/parallel CPU execution parity | **PASS** |
| A10 — GPU parity if GPU path enabled | **NOT ENABLED / NOT REQUIRED FOR THIS CPU REFERENCE FREEZE** |

The preregistration makes A10 conditional: GPU parity is mandatory only if a GPU posterior/likelihood path is enabled for K2. GPU speedup itself is optional.

## A9 execution-parity conclusion

The expensive one-time serial reference completed all `3,721 / 3,721` parameter points and the runner reported:

`A9_cpu_execution_parity: True`

Therefore the accelerated parallel CPU path is accepted for K2 under the frozen parity rule. No scientific threshold, condition, prior, observation, or acceptance rule was changed after observing the result.

## Full regression gate

The report-bearing `dev` head was tested on Windows with a repository-local pytest base temp to avoid an unrelated operating-system permission failure in the default user temp directory.

Command:

```powershell
py -m pytest -q --basetemp="$PWD\.pytest_tmp"
```

Result:

```text
1290 passed, 4 warnings in 193.26s (0:03:13)
```

The four warnings are the existing scikit-learn Gaussian-process convergence warnings from `tests/test_smoke.py::test_engine_runs`.

The earlier run that reported `1282 passed, 8 errors` did not contain code-test failures: all eight errors occurred during pytest fixture setup because Windows denied access to `C:\Users\dev_kaeem\AppData\Local\Temp\pytest-of-dev_kaeem`. Re-running with an explicit repository-local `--basetemp` completed all tests successfully.

## Final scored runner status

The scored runner emitted:

```text
STATUS: PASS_PENDING_OPTIONAL_GPU_OR_FREEZE_REVIEW
```

and saved the authoritative machine-readable result locally as:

```text
experiments/kinetics_k2/artifacts/k2_results.json
```

The large forward cache and local scored artifacts are execution artifacts, not replacements for the source-bound scientific report.

## Freeze decision

**K2 is PASS / FROZEN.**

Basis:

- frozen preregistration remained unchanged;
- A1 through A9 all passed;
- A10 was not enabled and is therefore not a blocker under the preregistration;
- the full repository regression suite completed cleanly with `1290 passed` and no failures/errors;
- the scientific implementation used for the scored result remains bound to source commit `eab5879e8c17d5c1cf8f697f0eb2e57816cc99b5`.

Post-freeze performance work is a separate optimization/hardening activity. It must preserve frozen K2 scientific outputs, admissibility semantics, posterior meaning, and declared parity tolerances.