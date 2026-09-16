# K1 adjudication: acceptance criterion A6 is unmet under the corrected level rule

Status: **k1_results.json is superseded on A6** (and on the level predictions of
R1, R2, R3, R6a and R6b). Nothing in the frozen K1 record is edited: the config
hash, `k1_config_frozen.json`, `k1_results.json` and `k1_report.md` still record
what K1 measured at its frozen commit. This file records how that measurement
reads under the level rule in force now. Machine-readable twin:
`ADJUDICATION_A6.json`.

## The criterion

A6, as preregistered in `k1_config.py`: *"the verification gate awards
ANALYTICALLY_VERIFIED on at least one regime from the exact reaction-free
invariant, and CROSS_SOLVER_VALIDATED on at least one regime from the
independent algebraic steady state"*.

K1 recorded A6 as met: the gate awarded `cross_solver_validated` on R1, R2, R3,
R6a and R6b through `independent_steady_state_agreement`.

## What changed, and why

Commit `da159f9` (audit finding IND-04, consensus stream; merged into
`claude/main-audit-fixes` in `add7ff6`) removed that award. The steady-state
reference is not an independent solver:

* it is fed the same derived accessors the integrator's right-hand side is
  assembled from (`run.chemistry.beta_m3_k_per_mol`, `run.gamma_per_s`,
  `run.operation.dilution_rate_per_s`), so the two share arithmetic;
* it is not routed through a pinned consensus or oracle, which the strongest
  levels now require (VAL-01, `319b2e5`);
* a bracketed numerical root is not a closed form.

`independent_steady_state_agreement` is still run and still FAILs on
disagreement, but it establishes no level.

## Consequence

* **A6: unmet.** The CROSS_SOLVER_VALIDATED half cannot be met by any K1
  regime, because no K1 check can now issue that level. The
  ANALYTICALLY_VERIFIED half is not what changed: the reaction-free invariant
  check still issues that level under the current rule
  (`tests/domains/kinetics/test_cstr_domain.py` asserts it on an adiabatic
  gate); K1 itself was not re-run for this adjudication.
* **Level predictions of R1, R2, R3, R6a, R6b: unmet.** Each preregistered
  `cross_solver_validated` among its predicted levels.
* `acceptance_all_met` and `predictions_all_met` in `k1_results.json` read
  `true`; under the corrected rule both are `false`.
* Every other K1 criterion and prediction is untouched by this change.

Re-deriving K1 under the corrected rule is a K1 version increment, which is not
done here.

## Also records the old level

`benchmarks/perf_runtime_audit/baseline_k1_solver_calls.json` is an archived
performance baseline that lists `cross_solver_validated` among the gate's
attained levels for the regimes above. It is a work/timing record, not an
evidentiary one, and it is left as archived; read its level fields as the
pre-`da159f9` rule.
