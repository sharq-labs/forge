# Post-merge remediation verification — 2026-10-18

## 1. Executive summary

**Final recommendation: BLOCKED_BY_SCIENTIFIC_CORRECTNESS.** Verification was executed; remediation closure was not achieved. No program gate, maturity stage, active epic, certificate, scientific threshold or evidence bundle was changed.

The conservation exchange scale correctly excludes interior faces and uses a maximum rather than adding redistribution to external exchange. However, the separate arithmetic floor grows as N² on fixed-length uniform meshes. An independently derived, executed diagnostic of the unchanged production admission statements rejects a 1e-7 J closed-system leak at 4 cells and accepts it at 256/512 cells. This fails the requested mesh-independent admission criterion. The diagnostic is source-extracted arithmetic, **not an end-to-end M1C solve**: the module cannot construct its realization because `provided_capabilities` is empty. Fixing that declaration changes scientific identity and needs a compatibility/owner decision; the guard was not bypassed.

A bounded import-order correction restores fresh scientific imports. Executed positive evidence includes Newton/robustness (79), OD-30/scenario/multiscale (83), checkpoint integrity (55), semantic/field-kind (56), and compatibility (150 passed, 1 skipped). Other packs fail. The final bounded scientific regression remains **19 failed, 256 passed, 3 errors**. These counts are separate command results, not a deduplicated test population and not physical validation.

Merge readiness: **blocked**. Certification readiness: **not eligible yet**. Phase 3.5 closure: **not ready**. Genesis-lite benchmark/governance preparation is allowed; scored readiness depends on G0 scientific-integrity classification and resolution/isolation. A2 new Mind capability work remains owner-gated.

## 2. Exact state and execution evidence

Initial target: `D:/forge-main-337519d1`, branch `fix/post-merge-remediation-2026-10-18`, clean, HEAD `93ed64b0292e9fea714ac83affb64b71488ac050`, direct parent/base `337519d1944bd52c5711a657a926ad855ac8d868`. `git merge-base --is-ancestor 337519d1 HEAD` succeeded; parent/base also confirmed by `git log -1 --format='%H %P %s'`. No unexpected initial changes were found. The stale primary checkout was read initially for supplied contracts only; all task changes/tests occurred in the specified remediation worktree.

**Inventory deviation:** the commit has 23 files, but **8 source, 9 tests, 6 documentation/proposal files**, not the reported 8/10/5. The exact original inventory and base/commit/working source SHA-256 values are in [the evidence record](evidence/post_merge_2026_10_18.json).

### Environment diagnosis

Executable: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe`, CPython 3.14.2, Windows 11 AMD64. Existing base environment: NumPy 2.4.3, SciPy 1.18.0, Pint 0.25.3, pytest 9.0.2. Existing shared project environment: Python 3.14.2, NumPy 2.5.2, SciPy 1.18.1, Pint 0.25.3, pytest 9.1.1. No package was installed, upgraded or edited.

Bounded probes reproduced SciPy and Pint import hangs in both existing dependency trees. `faulthandler.dump_traceback_later(12)` captured blocking `platform._wmi_query` -> `_wmi.exec_query`; SciPy reaches it through NumPy testing/platform.machine, Pint through flexcache/platform.system. Plain NumPy with BLAS threads=1 imported. WSL `wsl.exe --list --quiet` timed out after 25 seconds. The initial CIM process query also stalled and its own command was interrupted; no unrelated process was terminated. `Get-Process python*` observed 14 processes including six project-venv executable paths. Exact session ownership/command lines could not be established because CIM/WMI was blocked, so the shared environment was treated as in use.

Task-local `.pytest-review-temp/post-merge-verification/bootstrap/sitecustomize.py` contains only:

```python
import platform
platform._wmi = None
```

This permits the standard-library Windows fallback (`sys.getwindowsversion`/registry), without inventing a platform value or changing scientific code. Imports then completed in 0.707 seconds. Child test processes inherit the task-local bootstrap through PYTHONPATH. Test environment also sets OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1 and PYTHONDONTWRITEBYTECODE=1. PYTHONPATH is bootstrap plus this target's `src`; pytest adds its configured repository paths. Base site initialization includes an unrelated promptsim editable path; target imports resolved into this worktree. This is **developer verification on 3.14, not the required 3.11/3.12 certification environment**.

Sampled installed RECORD checks found no mismatches for package `__init__.py`/METADATA and SuperLU entries in both environments (36 NumPy, 104 SciPy, 16 Pint and 9 pytest-related entries each). This is a partial package-integrity check, not an exhaustive installation guarantee. No evidence establishes resource contention as the cause; both independent dependency trees reached the same WMI stack.

All seven original recipe commands ran first and each exited 2 during collection with the same repository import cycle. They are preserved as `recipe-1` through `recipe-7`, not overwritten by later runs. The cycle is conversion -> models/structured_validity -> fields/definition -> semantics -> partially initialized conversion. The correction publishes existing LossPath before importing existing ValidityStatus. Independent static compatibility review found unchanged symbols, signatures, schema bytes, tolerance and serialization semantics; fresh-process regression cases were added. This changes certified source bytes and remains subject to OD-3.

### Commands and outcomes

All commands below use the executable above from the target worktree. The machine-readable evidence contains full argv, environment, source revision, exit code, wall time, summary, failure names and log SHA-256. Full stdout/stderr remains under `D:/forge-main-337519d1/.pytest-review-temp/post-merge-verification/`. Each command has a 180-second subprocess timeout. No pytest command timed out. Diagnostic import/WSL timeouts are BLOCKED, never PASS.

The seven exact remediation recipes are unchanged apart from selecting the explicit working Python executable. Initial runs used pristine source; corrected runs used HEAD plus the uncommitted import-order fix. Later task-specific temp directories are an environment-only rerun, not a reduced selection.

| Evidence ID | Result | Exit | Wall seconds |
|---|---|---:|---:|
| recipe-1 | 1 error in 0.92s | 2 | 1.597 |
| recipe-2 | 1 error in 1.11s | 2 | 1.765 |
| recipe-3 | 1 error in 1.90s | 2 | 2.548 |
| recipe-4 | 1 error in 1.54s | 2 | 2.128 |
| recipe-5 | 1 error in 1.80s | 2 | 2.505 |
| recipe-6 | 1 error in 1.46s | 2 | 2.106 |
| recipe-7 | 1 error in 2.39s | 2 | 3.207 |
| corrected-recipe-1 | 5 failed, 4 passed in 1.91s | 1 | 2.566 |
| corrected-recipe-2 | 2 failed, 1 passed, 271 deselected, 12 warnings in 6.39s | 1 | 7.544 |
| corrected-recipe-3 | 79 passed in 1.43s | 0 | 2.098 |
| corrected-recipe-4 | 1 failed, 41 passed in 1.88s | 1 | 2.553 |
| corrected-recipe-5 | 1 error in 1.88s | 2 | 2.665 |
| corrected-recipe-6 | 1 failed, 67 passed, 1 warning in 1.45s | 1 | 2.027 |
| corrected-recipe-7 | 83 passed in 63.55s (0:01:03) | 0 | 64.277 |
| bounded-1 | selection only; no tests executed | 0 | 16.301 |
| bounded-2 | 1 failed, 84 passed in 11.92s | 1 | 12.540 |
| bounded-3 | 19 failed, 251 passed, 8 errors in 11.62s | 1 | 12.629 |
| bounded-4 | exact Fraction replay: 7 / 4 subdivisions | 0 | 0.084 |
| bounded-5 | 2 failed, 87 passed, 1 warning in 2.50s | 1 | 3.199 |
| final-bounded-1 | 19 failed, 256 passed, 3 errors in 11.85s | 1 | 12.795 |
| final-bounded-2 | 55 passed in 1.63s | 0 | 2.254 |
| final-bounded-3 | 56 passed in 1.32s | 0 | 1.974 |
| final-bounded-4 | 150 passed, 1 skipped in 29.87s | 0 | 30.625 |

Exact commands (each evidence ID has its own log):

- **recipe-1**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase2_review_regressions.py`
- **recipe-2**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"`
- **recipe-3**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_newton_domain_errors.py tests/test_phase3_br13_numerical_stability.py tests/numerical/test_robust_nonlinear.py`
- **recipe-4**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_phase1_sparse_correctness.py tests/test_interface_flux_execution.py`
- **recipe-5**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- **recipe-6**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase3_br14_iqn_imvj.py tests/test_multiphysics_window_control.py`
- **recipe-7**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_od30_multiscale_authority_identity.py tests/test_system_runtime_scenario_identity.py tests/test_system_runtime_multiscale_identity.py tests/test_multiscale_review_fixes.py`
- **corrected-recipe-1**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase2_review_regressions.py`
- **corrected-recipe-2**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"`
- **corrected-recipe-3**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_newton_domain_errors.py tests/test_phase3_br13_numerical_stability.py tests/numerical/test_robust_nonlinear.py`
- **corrected-recipe-4**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/numerical/test_phase1_sparse_correctness.py tests/test_interface_flux_execution.py`
- **corrected-recipe-5**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- **corrected-recipe-6**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase3_br14_iqn_imvj.py tests/test_multiphysics_window_control.py`
- **corrected-recipe-7**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_od30_multiscale_authority_identity.py tests/test_system_runtime_scenario_identity.py tests/test_system_runtime_multiscale_identity.py tests/test_multiscale_review_fixes.py`
- **bounded-1**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --changed --dry-run`
- **bounded-2**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_post_merge_import_smoke.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py`
- **bounded-3**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- **bounded-4**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -I docs/work/proposals/od22_replay.py`
- **bounded-5**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_phase1_coupling_convergence_coverage.py tests/test_electrothermal_vertical.py tests/architecture/test_cross_domain_fixtures.py`
- **final-bounded-1**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B tools/forge_check.py --regression`
- **final-bounded-2**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_checkpoint_integrity_hardening.py tests/test_external_participant_checkpoints.py tests/test_provider_participant_checkpoints.py`
- **final-bounded-3**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/architecture/test_quantity_semantics.py tests/test_declared_field_kind_mapping.py`
- **final-bounded-4**: `C:/Users/dev_kaeem/AppData/Local/Python/pythoncore-3.14-64/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py`

For final-bounded-1..4, the exact additional PYTEST_ADDOPTS settings are in the evidence JSON (Windows backslash paths; archive caveat below). For future runs use forward slashes: `PYTEST_ADDOPTS=--basetemp=D:/forge-main-337519d1/.pytest-review-temp/post-merge-verification/<unique-evidence-ID>-temp`. This removed five PermissionError fixture errors from the first regression run; it did not resolve 19 failures or three CredibilityEvidenceReport fixture/type errors. All other counts have zero skipped cases unless explicitly recorded. Compatibility's one skip is not counted as coverage; its exact identity was not emitted by that command and is not inferred.

`forge_check --changed --dry-run` selected the full FAST tier because of shared reach. The full tier was **NOT RUN**, as prohibited. The explicitly authorized fixed `--regression` pack was executed, including its fixed adversarial sentinel tests; no full mutation campaign was started.

### Failure classification

- Repository import cycle: executed collection failure, fixed structurally; source bytes in the cycle were unchanged by the original remediation relative to base. No same-environment base suite was run, so no broad baseline-equivalence claim is made.
- M1C invalid realization: scientific declaration/integration failure, not dependency installation. Required provided capability is absent; solver-backed Batch D evidence unavailable.
- Forward-tear suite: five failures, including the newly authored tampered-record test. Earlier quantity-meaning admission prevents the fixture reaching the intended guard. The historical claim that the new test protects the guard is withdrawn on this executed evidence.
- Discovery: two failures because the M1C module refuses import. Runtime discovery has not confirmed 20 models; do not apply the 19->20 pin based on this run.
- Interface suite: one failure matches an obsolete `A-4` error string; the actual refusal is `field meanings, kinds or measures differ; explicit transformation required`. This is fail-closed behavior, not demonstrated false admission. The test's remaining assertions are not covered by that failed execution.
- Parent mesh suite: tampered lineage is refused as `conflicting issued mesh registry key`; test expects `tampered|unissued`. Conservative refusal is observed; downstream assertions in this test remain unexecuted.
- OD-22: actual runtime returned seven subdivisions; Fraction replay separately returned seven without memory/four with growth. Old assertion remains red and unchanged.
- OD-23/24: prohibited-relaxation assertion and self-loop expected-admission assertion fail; no semantic owner decision silently taken.
- Fixed regression: final failure names below. Multiple claim paths refuse or lack reports because the bridge rejects the report type; changed-result replay unexpectedly reports VERIFIED in its adversarial test. These are **UNCLASSIFIED scientific-authority blockers**, not declared environment-only or proven false scientific support. Diagnose the exact bridge/report identity and replay contract before accepting any dependent evidence. Gate dependency test also conflicts with BLOCKED_WITH_EVIDENCE semantics. No fixes to claim/trust/maturity behavior were made.

## 3. Independent scientific correctness review

### Conservation

The finite-volume equation is `C_i*delta_T_i/dt = Q_left-Q_right+p_i`. Summing cancels interior faces. Both `sum(abs(C*delta_T))` and `dt*(abs(b0)+abs(b1)+sum(abs(p)))` have units J; their maximum avoids adding the same exchange twice. Neither term uses an arbitrary temperature datum. This is a valid relative policy scale; an energy balance still cannot independently validate the physical coefficients or the governing model.

**New counterexample:** the additional floor `64*eps*dt*sum(abs(A)@abs(T)+abs(rhs))` includes interior conductances through the row magnitudes. For a unit-length insulated slab, k=c=A=1, T=300 K, dt=0.1 s and N equal cells, its equilibrium value is `64*eps*(600+120*N*N)` J. The source-extracted production block and independently derived expression agree:

| Cells | Floor (J) | Uniform injected leak (J) | Balance admission |
|---:|---:|---:|---|
| 4 | 3.5811e-11 | 1.0000002e-7 | rejected |
| 32 | 1.7548e-9 | 1.0000002e-7 | rejected |
| 128 | 2.7948e-8 | 1.0000002e-7 | rejected |
| 256 | 1.1177e-7 | 1.0000002e-7 | admitted |
| 512 | 4.4704e-7 | 1.0000002e-7 | admitted |

All rows satisfy the source's row allowance with residual_rtol=1e-8; relative residual is approximately 3.3e-10. The leak exceeds the declared 1e-9 J absolute allowance by 100x. Exchange remains approximately 1e-7 J throughout; the floor causes the admission change. This is numerical evidence against mesh-independent conservation admission. It does **not** establish an executed complete M1C record or physical validation.

Reproduce with `python -B docs/work/evidence/post_merge_2026_10_18_energy_probe.py` in a working scientific environment. Executed locally using the documented Python/bootstrap, exit 0; raw results in `energy-probe.log` and the durable evidence JSON. Diagnostic-specific wall time was not separately isolated. No tolerance was altered after seeing results. A justified backward-error/conservation-floor design and adversarial mesh/datum tests are required before correction; adjusting the factor or expected outcome for this example is not a scientific resolution. Static additional risk: exchange/arithmetic/allowance are not explicitly checked for finiteness, so overflow needs a separate adversarial study.

Weighted transfer's overlap integral has a sound independent interpretation: amount in each source dual is distributed proportional to integral(c*A) over overlaps. The M1B heterogeneous-uniform preservation, distribution receipts and unit-refusal tests ran successfully within bounded-2; its only failure is in M1A. Receipt weight remains a declared assumption, not verified material authority. Uniform preservation is not physical validation or a general transfer-error bound. M1D has not adopted this primitive in this tree.

### Recovery, history and replay

The new finalization and pre-participant validation tests passed within corrected-recipe-6. Per-participant finalization preserves the primary exception and tries later participants. Re-entrant run refusal retires state. The checkpoint pack's 55 passing cases cover failed/partial restore retirement and same-object recovery contracts, not real external solver qualification. Pre-existing initialization/initial-transfer/initial-identity failures occur before the main finalization try/finally; retirement is conservative, cleanup is not guaranteed on those paths. Do not claim all aborted runs finalize.

IMVJ nested begin-window staged-discard tests passed. They cover the acceleration lifecycle directly; there is still no combined runtime IMVJ plus event-alignment fixture in the remediation. Rational replay and actual runtime agree on OD-22's seven/four counts. Verification is not experimental validation.

### Identity and evidence

OD-30's helper derives the authority's own fast-state declaration, snapshots it and enforces it against returned records. The 83-case identity/scenario/multiscale pack passed; no inference that this closes OD-29 follows. Inner run digests and series source identities remain unresolved self-reported values. An echoed request context is not evidence of the context actually executed.

`cell-cooling-aging` is constructed with explicit fast state (`flagships/forge_flagships/battery_cooling.py:597`); correcting that binding changes its regenerated authority digest. Stored bundles may remain historically self-consistent because engineering bundle verification reads stored payloads; current-authority replay/resume compatibility is distinct. **Committed battery bundle verification/replay was NOT RUN**, and no bundles were regenerated. Old authority-bound requests/checkpoints require explicit compatibility handling and are expected to refuse mismatch safely. Initial-slow identity still omits domain keys and depends on iteration order; FAILED-vs-REFUSED remains open.

Independent read-only reviewers separately assessed numerical/recovery behavior and governance/identity. The import fix received independent static compatibility review. Their review is not test execution; all executed results in this report came from the primary runner. No scientific contracts were broadened to obtain a passing test.

## 4. Owner decision matrix

In the final three blocker columns, “dependent” means work/claims using that affected path. “Yes” under merge means it prevents an unconditional closure recommendation, not a claim that every isolated defect-fix PR must solve the entire roadmap. All listed decisions remain open; no automatic owner approval is inferred.

| OD | Exact defect/question; scientific impact | Implementation/evidence now | Remaining uncertainty and recommended disposition | Blocks merge closure | Blocks Phase 3.5 closure | Blocks Genesis-lite | Explicit owner approval |
|---|---|---|---|---|---|---|---|
| 22 | 8 vs 7 subdivisions; replay contract consistency | Runtime and independent Fraction replay produce 7/4; unchanged test fails | Approve proposed 7 expectation with final horizon-cut derivation; no runtime change | Yes, red regression disposition | Yes until disposition | Not inherently; preserve failure | Yes, existing contract conflict |
| 23 | Native relaxation contradicts doc/test/§12.10; equivalence authority | Relaxation implementation present; exact L3 assertion fails | Prefer runtime RelaxationPolicy as sole authority; review migration/identity first | Yes | Yes | Dependent electrothermal path | Yes |
| 24 | Self-loop refused by graph but test expects lagged edge | Exact self-loop regression fails with refusal | Retain graph refusal and approve test-contract correction | Yes | Yes | No new self-loop capability needed | Yes |
| 26 | Invalid nominal and tampered fixtures fail before forward-tear guard; unchecked tampered plans | 5 failures; new guard test also fails at quantity meanings | Review fixture semantics; approve replacement only once guard reached; A2b revalidation still unresolved | Yes | Yes | Dependent runtime-adapter claims | Yes |
| 29 | Inner fast execution records are not resolved; echoed inputs cannot prove provenance | Not fixed; passing outer identity tests do not supply inner evidence | Versioned resolvable-record contract, or scientifically demonstrated isolation; ghost-run admission not executed here | Yes for scientific closure | Yes for affected runtime assurance | Dependent fast-system claims; G0 needs classification/isolation | Yes, FastSystem compatibility |
| 30 | Authority fast-state/history identity; FAILED vs REFUSED; slow-state domain identity | Fast-state half implemented and tested in 83-case pack; other halves unchanged | Accept bounded fix only after certification; decide failure taxonomy and slow-state compatibility separately; old battery authority bundles are historical | Yes, certification and remaining decisions | Yes | Dependent authority claims | Yes for remaining decisions/compatibility |
| 31 | Model discovery count 19 vs static20; guard/certificate pin | Pin unchanged; discovery fails importing invalid M1C realization | First approve correct capability/realization declaration, then execute full discovery and review 19->20 pin plus OD-3; no pin applied | Yes | Yes | Census alone need not block preparation; invalid declaration blocks dependent runs | Yes |
| 32 | Initial nonlinear failure outcome, heterogeneous residual meanings, missing linear disclaimer, constructed orientation diagnostic | Newton behavior tested; legacy DIVERGED retained; orientation limitation test passes but interface suite has one separate refusal-string failure | Decide each serialization/outcome change independently; do not treat residual as error bound or orientation validation | Yes for full closure decisions; bounded unchanged semantics may remain | Yes | Dependent interpretations; can exclude paths with evidence | Yes |
| 33 | M1D must supply c*A-weighted transfer or refuse heterogeneity | Primitive tested; M1D commit5fd797dd not ancestor (git exit1); integrated consumer absent | Dependency satisfied only at primitive level; adaptive heterogeneous integration pending | No for isolated primitive remediation | Yes, M1 incomplete | No for independent Blindfold preparation; blocks adaptive claims | Yes, integrate vs homogeneous-only |
| 34 | O(N²) issued-record verification vs tamper detection | Full sweep retained; no performance measurement | Keep it; optimize only after measurement and equivalent tamper detection review | No | No scientific gate pass inferred; performance may defer | No absent measured budget failure | Yes before changing verification semantics |

New conservation-floor and invalid-realization findings are scientific-design/identity decisions associated with Batch D and OD-31/33, not newly invented closed OD entries. Regression bridge/replay failures remain UNCLASSIFIED and blocking until diagnosed. No open decision is marked DEFERRED_BY_OWNER without actual owner disposition.

## 5. Certification impact and OD-3 preparation

The current SCOPE includes numerical and multiscale source even where the old certificate does not explicitly enumerate every new file. Do not repeat the earlier assumption that only three source paths matter. Seven original changed source paths are current-scope, plus this session's `scientific/composition/conversion.py`; domain conduction also affects model/realization production identities. The complete original/working source digests follow in the appendix. The existing certificate explicitly pins execution runtime and authorities, and providers has production-registry pins. All changed tests and the new subprocess regression need harness-scope review on the intended final source.

Compatibility obligations: frozen symbols/signatures/schema behavior, default receipt identity, new declared weighted receipt payload, M1C implementation reference0.2.0, changed authority digest and old checkpoint/request behavior, new acceleration history events, changed singular-failure records, dependency closure and exact discovery census. Preserve historic bundles/certificate manifests. Compatibility tests here passed with one skip; current-tree certification does not follow.

OD-3 is **NOT RUN**. The branch is not eligible: unresolved scientific counterexample and realization declaration, red target/regression checks, no supported Linux3.11/3.12 evidence, no clean committed final source (edits intentionally uncommitted), and no final-owner decisions. Do not start recertification merely because its commands are documented.

After separate authorization and closure of those prerequisites, follow `docs/assurance/LOCAL_ASSURANCE.md` exactly:

```bash
python -m tools.certification.local_assurance prepare \
  --python311 /path/to/python3.11 --python312 /path/to/python3.12
# Use an owner-approved, clean committed source tree; record SOURCE_SHA and tree SHA.
# Verify imports using the prepared runner's absolute path from /tmp.
(cd /tmp && /absolute/checkout/.forge/venvs/3.12/bin/python -E -s -P -c "import pint, numpy, scipy")
.forge/venvs/3.12/bin/python -m pytest benchmarks -m "not expensive" -q -rs -p no:cacheprovider
.forge/venvs/3.12/bin/python -m tools.certification.local_assurance run \
  --python311 .forge/venvs/3.11/bin/python \
  --python312 .forge/venvs/3.12/bin/python
# Preserve .forge/assurance/<SOURCE_SHA>/evidence/ and its hash manifest.
# Only after SOURCE_PASS and separately authorized commit:
git add certification/current_core_v2.json
git commit -m "certification: recertify hardened core"
.forge/venvs/3.12/bin/python -m tools.certification.local_assurance verify
```

Linux with ngspice is required. Source PASS is not certificate-child PASS or push authorization. Full tiers, campaigns and formal mutation shards belong to that later separately authorized run; none were launched in this session. No push/PR/merge is authorized here even if a later tool prints SAFE_TO_PUSH.

## 6. Phase 3.5 closure matrix

Canonical ledger remains unchanged: DV0, M1, M2, E1, E2, E3 are **MISSING**, each with empty evidence. The review's BLOCKED_WITH_EVIDENCE labels below describe observed readiness, not edits to ledger statuses. A program gate is not a capability maturity stage. No row is VALIDATED, CERTIFIED or PRODUCTION_READY.

| Scope | Evidence-supported review status | Blocker / next action |
|---|---|---|
| DV0 | BLOCKED_WITH_EVIDENCE; canonical MISSING | Bounded regression red; full deferred register not executed. Decide from every DV row present at decision time, not stale range titles. DV0 is not G0 and blocks no building. |
| M1 | IMPLEMENTED in slices / partially TESTED / BLOCKED_WITH_EVIDENCE | M1A refusal-string failure, M1B positive tests, invalid M1C realization and mesh-floor counterexample; M1D absent. No integrated adaptive rollback/study evidence. |
| M2 | IMPLEMENTED foundations only; canonical MISSING | No executed conforming-refinement/conservation acceptance here; M1 dependency must pass for PASS/FAIL decision (decided dependency for blocked decision); A-3/architecture acceptance also required. |
| E1 | BLOCKED_WITH_EVIDENCE; canonical MISSING | Real nonlinear FEniCSx manufactured execution not run; declarations are not provider evidence. |
| E2 | Partial interface implementation TESTED; canonical MISSING | Real FEniCSx/OpenFOAM planar CHT not run; independent receiver flux/source balances unresolved; A-4 review required. |
| E3 | Foundations only; canonical MISSING | Moving mesh kinematics do not establish ALE transport/GCL. Real moving-boundary/rollback evidence missing; M1 decision dependency. |
| Checkpoint integrity | TESTED: 55 passed | Real provider qualification not established; pre-main-try finalize gap remains. |
| Semantic compatibility | TESTED: 56 semantic/field-kind and150 compatibility passed,1 skipped | Five electrothermal fixture failures show integration conflict; report/bridge identity regression unresolved. No skipped case counted as evidence. |
| Field transfer/interface physics | Partially TESTED; BLOCKED_WITH_EVIDENCE for closure | Weighted primitive tested; interface rejection-message failure; orientation diagnostic is constructed, not independent flux truth; real CHT absent. |
| Batch D | BLOCKED_WITH_EVIDENCE | Production solve unavailable; conservation floor independently fails mesh criterion. Neither IMPLEMENTED nor AST parsing establishes verification. |
| Batch E | TESTED for bounded cases; not full closure | 67 passed/1 failed in IMVJ+window pack; OD22 red is explained but not dispositioned. No runtime-level IMVJ/event test; initialization cleanup gap. |
| Owner decisions | OPEN / BLOCKED_WITH_EVIDENCE | Matrix above; no owner deferral or epic change automatically entered. |

Architectural RC/spring/mixing fixtures ran within bounded-5 and had no reported failure; this establishes design-probe execution only, not support for those domains or closure of M1-E3. No missing foundations were relabelled NOT_APPLICABLE.

## 7. Shortest safe transition to Blindfold Genesis

Begin immediately: existing-harness scoring/preregistration review, equal-budget baseline definitions, leakage controls, cost measurement preparation and evidence inventory. This is already allowed A1 measurement/governance work; do not add a new hypothesis generator, planner, belief store or scientific provider.

Before relying on scored Genesis results: resolve or demonstrate isolation of conservation/realization, unresolved fast-run provenance and bridge/replay authority defects for every used path; complete the G0 six-question scientific/governance classification; preserve all negative results; obtain final intended-source certification through the authorized process, or isolate a proven GOVERNANCE_ONLY certification blocker under the complete six-question circuit-breaker contract, preserve its red result and label outputs uncertified. SCIENTIFIC_CORRECTNESS and UNCLASSIFIED defects remain blocking. Stale certification is not automatically GOVERNANCE_ONLY because identity/provenance and claim effects are still unresolved. Do not claim G0 exit now.

M2, E1, real E2 and E3 may remain unfinished for a benchmark using existing Blindfold substrate that demonstrably does not use those paths. That does not close Phase 3.5. Finish/classify the integrity defects before expanding numerical scope. Recommend preparing an owner-reviewed Genesis transition proposal, rather than forcing all unused foundations to PASS or expanding Phase3.5 now.

For A2, a separate owner-approved reviewed PR must change the canonical ledger `active_epic`, its `tests/test_capability_completion.py` pin and `.github/pull_request_template.md`, with the target research-program contract/allowed scope and explicit dispositions of unfinished gates. Alternatively one narrow exception needs every Completion Policy field and anti-loophole review. Merely editing ACTIVE_PLAN or this report cannot change the epic. No such change was made.

## 8. Final merge recommendation

**BLOCKED_BY_SCIENTIFIC_CORRECTNESS**

The executed admission counterexample directly contradicts the requested mesh-independent conservation criterion; invalid M1C scientific declaration prevents full Batch D verification, and unresolved trust/provenance/regression failures prevent G0 closure. Independent static review and successful subsets do not erase these results. Certification and owner decisions are additional blockers. The work is actionable for owner review, but the branch is not honestly merge-ready or Phase3.5-complete.

All edits are uncommitted on the existing remediation branch. No push, PR, merge, history rewrite, bundle regeneration, dependency installation, reboot, unrelated-process termination or OD-3 was performed.

## Appendix: original remediation inventory

```text
docs/work/ACTIVE_PLAN.md
docs/work/PROGRESS.md
docs/work/REMEDIATION_2026-10-18.md
docs/work/proposals/A1_core_guards_model_count.patch
docs/work/proposals/OD22_window_control_subdivisions.patch
docs/work/proposals/od22_replay.py
src/engcore/domains/thermal_models/conduction1d_transient_fv.py
src/engcore/execution/multiphysics/acceleration.py
src/engcore/execution/multiphysics/runtime.py
src/engcore/multiscale/runtime.py
src/engcore/numerical/nonlinear.py
src/engcore/numerical/providers.py
src/engcore/numerical/vertex_state.py
src/engcore/system_runtime/authorities.py
tests/numerical/test_newton_domain_errors.py
tests/numerical/test_phase1_sparse_correctness.py
tests/test_interface_flux_execution.py
tests/test_m1b_vertex_dual_state.py
tests/test_m1c_transient_fv.py
tests/test_od30_multiscale_authority_identity.py
tests/test_phase2_review_regressions.py
tests/test_phase3_br14_iqn_imvj.py
tests/test_system_runtime_scenario_identity.py
```

## Appendix: affected source digests

- `src/engcore/domains/thermal_models/conduction1d_transient_fv.py`
  - base: `89df68aa5e8e2097b073cbddadd4d1f48b9004a1e7eaf5dac5c0c9b43d858e3e`
  - remediation commit: `ccdb257657fd2c9408590d6b8ca2f426c660ee0f7bb1a259345a6cd2088fbda3`
  - reviewed working source: `ccdb257657fd2c9408590d6b8ca2f426c660ee0f7bb1a259345a6cd2088fbda3`
- `src/engcore/execution/multiphysics/acceleration.py`
  - base: `103ab082f17bd099f4d06ea9cca3540e86eaff576948cc70ff633485b96711f5`
  - remediation commit: `29c2aa57c7713bb312c75b6be397854471d2e73e037e579a31c131cda5d6b637`
  - reviewed working source: `29c2aa57c7713bb312c75b6be397854471d2e73e037e579a31c131cda5d6b637`
- `src/engcore/execution/multiphysics/runtime.py`
  - base: `1b41e78f6ed8ceea235d41e1db1e2720fa766041944dc251e0b3a94f5294576b`
  - remediation commit: `8c57e5d5cf696eb60341ecac801462355afae57c76537ecab2cf4ae9c68374d4`
  - reviewed working source: `8c57e5d5cf696eb60341ecac801462355afae57c76537ecab2cf4ae9c68374d4`
- `src/engcore/multiscale/runtime.py`
  - base: `eed6345e251d5f72fd25aa278e4ec33b4e37d0c31e5150ebd1eeb986cc683f7a`
  - remediation commit: `d603a368c6dda5fa6c491079f425981f055ed659b25dcd2469fac04d4e62b6e2`
  - reviewed working source: `d603a368c6dda5fa6c491079f425981f055ed659b25dcd2469fac04d4e62b6e2`
- `src/engcore/numerical/nonlinear.py`
  - base: `ce07d66e4657c7955694db4c9bc002f27e50f4483447cb8ae328457f1807febf`
  - remediation commit: `d4a839a1d487c6af9e35976a525810bc8d5af31d1f688bde71660a135b26abfd`
  - reviewed working source: `d4a839a1d487c6af9e35976a525810bc8d5af31d1f688bde71660a135b26abfd`
- `src/engcore/numerical/providers.py`
  - base: `6fd9a73b6525892e450bb3ad882da1d2599949901636b02cd9e55729cdc087d5`
  - remediation commit: `12913d652b2700e51d14ed66a79831b3beaa26b2f6f25b8d98b325fa0ea249e1`
  - reviewed working source: `12913d652b2700e51d14ed66a79831b3beaa26b2f6f25b8d98b325fa0ea249e1`
- `src/engcore/numerical/vertex_state.py`
  - base: `a1889c937cba868fc305e18751dc916d7871f1ff2f597771635d8bc36e4d0979`
  - remediation commit: `49e34045b2c5b5d908f2e1ba80e24c826c2e728348dc163b75ed3dd4e5ba927d`
  - reviewed working source: `49e34045b2c5b5d908f2e1ba80e24c826c2e728348dc163b75ed3dd4e5ba927d`
- `src/engcore/system_runtime/authorities.py`
  - base: `5e451a374c4173f39fe1727871852049d18098d693ebe58f0ee17a3464278c0c`
  - remediation commit: `24e3c29082d2df613dac83f933fa57d412f8748e013d1cc1ca92b312351c7949`
  - reviewed working source: `24e3c29082d2df613dac83f933fa57d412f8748e013d1cc1ca92b312351c7949`
- `src/engcore/scientific/composition/conversion.py`
  - base: `6eda5ba7a01304dcd53077ac64654735dfca0fedf7d6378b8165604f630a0be8`
  - remediation commit: `6eda5ba7a01304dcd53077ac64654735dfca0fedf7d6378b8165604f630a0be8`
  - reviewed working source: `24ee129177191a01ce5a0cf8e22e34762af3df782fc829ab2ee1f301abef15b9`

## Appendix: final bounded regression failure names

```text
FAILED tests/test_capability_completion.py::test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes[BLOCKED_WITH_EVIDENCE]
FAILED tests/claims/test_claims_assessment.py::test_a_t3_claim_at_the_benchmark_point_is_supported_with_benchmark_validation
FAILED tests/claims/test_claims_assessment.py::test_the_value_compared_is_the_reports_never_the_callers
FAILED tests/claims/test_claims_assessment.py::test_a_violated_comparison_without_the_required_evidence_is_not_a_contradiction
FAILED tests/claims/test_claims_assessment.py::test_verification_cannot_satisfy_a_validation_requirement
FAILED tests/claims/test_quantitative_uq.py::test_an_interval_that_crosses_the_boundary_is_insufficient[tolerance_band]
FAILED tests/claims/test_quantitative_uq.py::test_an_interval_that_crosses_the_boundary_is_insufficient[threshold]
FAILED tests/claims/test_quantitative_uq.py::test_removing_uq_evidence_cannot_improve_the_verdict
FAILED tests/claims/test_quantitative_uq.py::test_numerical_uq_cannot_satisfy_model_form
FAILED tests/claims/test_quantitative_uq.py::test_parameter_uq_cannot_satisfy_a_numerical_demand
FAILED tests/claims/test_external_evidence.py::test_offered_external_evidence_never_changes_the_verdict_or_the_levels
FAILED tests/claims/test_sensitivity_robustness_challenge.py::test_a_challenge_never_changes_the_verdict
FAILED tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected[study]
FAILED tests/claims/test_impact_replay.py::test_any_edit_to_a_bundle_is_detected[value]
FAILED tests/claims/test_impact_replay.py::test_replay_detects_a_changed_solver_result
FAILED tests/claims/test_scientific_diagnostics.py::test_model_form_gap_becomes_a_root_cause_and_a_non_guaranteed_corrective_action
FAILED tests/claims/test_scientific_diagnostics.py::test_admissible_model_data_mismatch_is_diagnosed_without_becoming_model_form_uq
FAILED tests/claims/test_scientific_diagnostics.py::test_sensitivity_can_rank_repair_hypotheses_but_never_establish_causality
FAILED tests/claims/test_scientific_diagnostics.py::test_sealed_sensitivity_from_another_assessment_is_refused
ERROR tests/claims/test_sria_context_authority.py::test_same_qoi_same_value_wrong_charter_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_wrong_decision_id_cannot_become_valid
ERROR tests/claims/test_sria_context_authority.py::test_same_evidence_changed_context_cannot_become_valid
```

## Appendix: exact files changed by this verification session

These are additional to the committed remediation inventory above; all remain uncommitted.

- `src/engcore/scientific/composition/conversion.py` — import-order correction only.
- `tests/test_post_merge_import_smoke.py` — three fresh-process import regressions.
- `docs/work/POST_MERGE_REMEDIATION_VERIFICATION.md` — review report.
- `docs/work/evidence/post_merge_2026_10_18.json` — execution/diagnostic metadata, failure names and source digests.
- `docs/work/evidence/post_merge_2026_10_18_energy_probe.py` — reproducible source-extracted conservation diagnostic and independent analytic comparison.
- `docs/work/ACTIVE_PLAN.md` — bounded verification findings and unresolved next actions; no epic/gate change.
- `docs/work/REMEDIATION_2026-10-18.md` — evidence addendum preserving original static census.
- `docs/work/PROGRESS.md` — commands/results/failures and environmental diagnosis.

Full local logs and bootstrap scripts remain under ignored `.pytest-review-temp/post-merge-verification/`. Final-bounded PYTEST_ADDOPTS used Windows backslashes (exact strings in JSON); pytest's argument splitting removed those backslashes and created two task-specific `forge-main-337519d1.pytest-review-temppost-merge-verificationfinal-bounded-*-temp` directories in the target root. These generated directories were preserved by moving them into the ignored evidence directory after verification. The run still isolated its temp paths and removed five default-temp errors; no test selection changed. Use forward slashes for future PYTEST_ADDOPTS paths.

Independent report review corrected an overstrict certification prerequisite in §7: canonical governance permits isolation of a proven GOVERNANCE_ONLY certificate blocker with the complete circuit-breaker record. That alternative is unavailable for current unresolved scientific/unclassified defects. No other actionable issue was reported by the independent static patch/report reviewer.
