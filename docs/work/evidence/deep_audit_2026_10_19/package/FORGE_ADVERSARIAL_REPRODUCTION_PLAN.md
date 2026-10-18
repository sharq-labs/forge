# FORGE Adversarial Reproduction Plan — 2026-10-19

**Nothing in this plan has been executed.** Each reproduction runs FORGE code, so each needs **separate owner
authorization** before it runs. A reproduction that confirms a finding upgrades it to EXECUTED_REPRODUCED. A
reproduction that fails to trigger the finding must be recorded as NOT_REPRODUCED, together with the failing trace.
No result may be credited as PASS before it has been executed.

## Common isolation contract (all R-xx)

- **Source.** `D:/forge-main-337519d1` at HEAD `abed661f`. Re-check `git rev-parse HEAD`, `git status --porcelain`, and the SHA-256 of every file the reproduction imports, both before and after the run. Refuse to run if anything has drifted.
- **Write no files in the repository.** Reproduction scripts live in a fresh scratch directory `<S>/repro/`. Set `PYTHONDONTWRITEBYTECODE=1` and pass `-B`. The cwd is `<S>/repro`. Any pytest basetemp uses a forward-slash path in scratch.
- **Interpreter.** `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe`. This is the venv the P0 report recorded: CPython 3.14.2, NumPy 2.5.2, SciPy 1.18.1, Pint 0.25.3.
- **Environment:**
  - `PYTHONPATH=<S>/repro/bootstrap;D:/forge-main-337519d1/src;D:/forge-main-337519d1`. On Windows the separator must be a semicolon.
  - `bootstrap/sitecustomize.py` contains only `import platform; platform._wmi = None`. This is the WMI-hang workaround that P0 independently established.
  - Set `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS` and `OMP_NUM_THREADS` to `1`.
- **Check the import.** First print `engcore.__file__`; it must resolve to the D: worktree.
- **Record keeping.** Record argv, exit code, wall time, stdout/stderr SHA-256 and the source-hash map in `<S>/repro/<id>.json`. Append the command and result to `docs/work/PROGRESS.md` **only if the owner authorizes that write**.
- **Limits.** Each command gets a timeout. Do not fan out in parallel (memory note: SciPy wedges after parallel runs). Do not run against the hold-out or the formal grid.

Command template:

```bash
cd "<S>/repro" && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="<S>/repro/bootstrap;D:/forge-main-337519d1/src;D:/forge-main-337519d1" OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 600 "C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe" -B <script>.py
```

Each script must also contain a **negative control**: the same operation on an input that should pass. That shows
the harness is not refusing everything.

## Priority reproductions

| ID | Finding | Script content (to be authored and reviewed before execution) | Expected result if the finding is real | Negative control | Cost estimate |
|---|---|---|---|---|---|
| R-01 | FDA-01 | Reuse the existing authorized-run fixture behind `tests/test_scientific_trust_sprint2.py` (the replay-gate tests near :818–:1502). (1) Execute an authorized multiphysics GraphPlan with a quantified `external_uncertainty` on one planned input port. (2) Call `replay_authorized_graph_plan(..., external_uncertainty=None)`. (3) Print `status`, `differences`, the original vs replayed `_uncertainty` blocks, and the certification replay-gate status. | `REPLAYED_MATCH` with no differences, even though the `_uncertainty` blocks differ (quantified vs UNKNOWN). The certification UQ gate is still satisfied. | Replay with the identical `external_uncertainty` gives `REPLAYED_MATCH` with equal blocks. Changing an input value gives a difference. | 1–3 min, single process |
| R-02 | FDA-02 | Build on the system-runtime fixtures (e.g. `tests/test_system_runtime_big13_additions.py`, `tests/multiscale_reference.py`). Use a one-participant linear-ODE MultiphysicsAuthority (dx/dt = 1, plan [0,10] s) and two ordered committing nodes on the same owner. Execute and print the committed state's time and x after each node. Variant: plan [100,200] s from a state at t = 0. | Both nodes succeed. The final state is x = 20 at t = 10 (true value 10). The variant commits t = 200 with no refusal. | A single node gives x = 10 at t = 10. | 1–2 min |
| R-03 | FDA-03 | Use the `tests/test_materials_engine.py` pattern (`InterpolationRule("thermal_conductivity","temperature","linear")`, ~:109). Build a PropertySet with two SOURCED point data at 300 K (10 and 20 W/m/K, distinct claim ids and sources) and one at 400 K (30). Resolve at 350 K and print the derivation, value, status and `claim_digests`. Swap the claim ids and repeat. Also resolve at 300 K, and run `materials/coverage` on the set. | 350 K gives INTERPOLATED 25, then 20 after the swap. The datum missing from the digests is the one not selected. 300 K gives UNKNOWN ("not arbitrated"). Coverage lists no conflict. | A set with no coincident data gives a unique interpolation that does not depend on the ids. | < 30 s |
| R-04 | FDA-04, FDA-14 | Call `build_deterministic_samples(inputs, sample_count=4, dependence="independent")` with three uniform inputs [0,1] in the same unit. Form Y = X1 + X2 directly from the sample strings, with no solver involved. Feed synthetic `answers` (verdict "supported") into `predictive_intervals(..., credible_mass=0.95)`. Repeat at n = 32 with 17 inputs (Y = X15 + X16) and with 1 input, using a monotone Y = X0. | Y is constant, sd = 0, and lower = upper with status "completed". For one monotone input, [lower, upper] covers the quantile mass 0.920 (n = 32) and 0.7125 (n = 4). | Y = X0 + X1 at n = 32 with 2 inputs gives a nonzero sd. | < 10 s (pure functions; MCP server not started) |
| R-05 | FDA-05 | Use the stdlib-only evaluator `benchmarks/genesis_lite/evaluator/score.py::score_universe` on a **synthetic** INDISTINGUISHABLE entry built in the script. It must not come from the escrow root, pilot worlds, `cases_hard` or the formal grid. Submit the vacuous pair A = L(1+K s), B = L/(1+K s) with K = 1e-4 and s built from the entry's box, where L is the true in-box law. Mirror the test through `blindfold.escrow._assess_pair` on a synthetic `HiddenWorld`. | Outcome `indistinguishable_hit` with full credit. The escrow `_assess_pair` gives `hit=True`. | A pair whose outside spread is within tolerance of the truth's branch gives the same hit. An honest refusal earns 0.5. A pair that disagrees in-box by more than σ misses. | < 10 s |
| R-06 | FDA-06 | Feed synthetic `RunRecord` dicts to `analysis._capped` / `lift_decision`. Use one candidate arm with credit 1.0 on an out-of-family `spurious_correlate` world and a reference at 0. | The candidate's spurious credit is not capped, and the lift includes it. | The same configuration on `discoverable` is capped. | < 10 s |

## Secondary reproductions (lower priority; same contract)

| ID | Finding | Outline | Expected | Cost |
|---|---|---|---|---|
| R-07 | FDA-07 | Load a stored claims bundle record. Edit the `execution.run_id` and `plan_digest`, recompute the unkeyed bundle digest, then call `verify_assessment`. | SCIENTIFICALLY_REVALIDATED or REPLAY_REQUIRED, not TAMPERED. | < 30 s |
| R-08 | FDA-08 | `make_bundle` on a grounded record from `product/runtime.py`'s recommended path, then `replay_bundle`. | NOT_REPRODUCIBLE every time. | 1 min |
| R-09 | FDA-09 | Existing `tests/claims/test_p0_replay_execution_authority.py:51-62` already pins VERIFIED for INSUFFICIENT. Read the outcome together with the `bundle.py:37-38` docstring; this is a contract decision, not a code reproduction. | Documentation conflict. | 0 (static) |
| R-10 | FDA-10 | Two-participant explicit staggered coupling with q_n = n W and a declared `CoupledConservation`. Print the per-window balance residual and the consumed-value residual computed independently. | Recorded residual 0 J; independent residual 1 J per window. | 1–2 min |
| R-11 | FDA-11 | Run with a parameter binding, then `replay` without it. | Replay does not refuse. If outputs move, the assembly replay reports a difference. | 1 min |
| R-12 | FDA-12 | DC divider a–m–c with a 1 mV drop and the midpoint corrupted by 0.1 mV. Run `validation.py` at 0 V, 1 kV, 25 kV and 1 MV common mode. | Residual check PASS at ≥ ~25 kV; KCL FAIL; NUMERICALLY_CONVERGED in `attained_levels`. | < 30 s |
| R-13 | FDA-13 | FTCS `solve_with_realization` with n = 20 and r = 0.55, `require_admissible` left at its default, for 200 steps. Print checks per step against the analytic decayed mode. | Every check PASS up to the step where max\|u\| > 1, with error far above the fundamental. | < 30 s |
| R-15 | FDA-15 | Call the Halton start generator for p = 6 and p = 10 (pure function) and print the last two coordinates. | Collinear starts as derived. | < 5 s |
| R-16 | FDA-16 | Symbolic-regression search on a pure-noise target (sd 0.01, 60 datasets, fixed seeds). | ~27–31% SURVIVED_HOLDOUT; a survivor ranked top in every dataset. | 1–3 min |
| R-17 | FDA-17 | `mapping.py` point location on the reflex quad (0,0),(2,0),(2,2),(1.5,0.5) at (1,0.6). | Reported inside; the REFUSE policy does not fire. | < 10 s |
| R-18 | FDA-18 | Pilot-scope only, **owner go-ahead required**: a stateful exclusivity arm on `gl-pilot` worlds, labelled non-formal. | Measured gain, or none. | ~1–7 min (pilot rung) |
| R-19 | FDA-19 | Static: list the Genesis-lite secret inventory (root file, derived seeds, `runs.jsonl`) against what `isolation_probe` scans. | Not covered. | 0 |
| R-24 | FDA-24 | WSL FEniCSx env (`~/mm/root/envs/fenicsx`, c-compiler on PATH): vector elasticity with a lone x-roller, Krylov solver. | CONVERGED displacement with an arbitrary y offset, or a solver failure. | 2–5 min; WSL |
| R-26 | FDA-26 | WSL PyBaMM env: Flagship A nodes starting at 56 days. | The refusal "origin zero"; run PARTIAL. | 5–10 min; WSL |

## Execution log (owner-authorized 2026-10-19: R-03, R-04, R-05, R-06 only)

Common runner: `../repro/run.sh <ID> <script>`. Scripts: `../repro/r0{3,4,5,6}_*.py`. Bootstrap:
`../repro/bootstrap/sitecustomize.py`, containing only `platform._wmi = None`. Interpreter: phyx `.venv` CPython
3.14.2, NumPy 2.5.2, SciPy 1.18.1, Pint 0.25.3. `engcore` resolved to `D:\forge-main-337519d1\src\engcore`.

| Order | ID | Exit | Wall s | stdout SHA-256 (prefix) | Source hash before = after | New .pyc in repo | Verdict | Controls |
|---|---|---|---|---|---|---|---|---|
| 1 | R-04 | 0 | 2.118 | `184a33f4765b97ce` | yes (`bf233a73…`) | 0 | REPRODUCED (FDA-04, FDA-14) | OK |
| 2 | R-05 | 0 | 0.187 | `e555856efad14cc9` | yes | 0 | REPRODUCED (FDA-05) | OK (4/4) |
| 3 | R-06 | 0 | 0.165 | `ba7b5a95c205bae5` | yes | 0 | REPRODUCED (FDA-06; capping function scope) | OK |
| 4 | R-03 | 0 | 0.796 | `b271275bf287f73e` | yes | 0 | REPRODUCED (FDA-03) | OK |

Two deviations from the plan text, both minor:
- **R-05** used one hand-built synthetic world with two alternative truths, not a random population. The question
  is mechanism, not hit rate; X3's population estimate (0.771) stays an independent derivation.
- **R-06** exercised `world_credits`, `out_of_family` and `_capped`. It did not run the full `lift_decision`, which
  needs the complete registered-arm coverage over the formal grid.

No stop condition fired. Not run: R-01, R-02, R-07..R-26.

## Order and stop rules

1. Run R-04, R-05, R-06 and R-03 first. They are cheap pure-function reproductions with no solver or provider.
2. Then run R-01 and R-02, the system fixtures.
3. Stop after the first unexpected result, such as a negative control that fails. Record it and ask the owner before continuing.
4. Do not change any tolerance, fixture, test or source to make a reproduction run.
5. A reproduction never authorizes a repair. Each repair needs its own approval and, for certified files, OD-3.
