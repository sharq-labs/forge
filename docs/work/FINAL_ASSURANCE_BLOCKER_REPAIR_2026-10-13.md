# Final assurance blocker repair — 2026-10-13

**FINAL_ASSURANCE_STILL_BLOCKED**. Scanner and model-measurement snapshot repaired; empirical execution, supported qualification and owner recertification remain blocked. Nothing pushed or merged.

Starting origin/main: `5d73e8f5118aa845f1957decc5aae986e72476a9`; source tree `ed305a44e69429fe06bb1e92954237aadd005080`. Branch `fix/final-assurance-blockers`, dedicated `D:/forge-assurance-fix`. Current correction source commit: `781a6492a35a85c09c447c21495b017421d3b057`. Final documentation commit is recorded by git history; it is not a certificate child or a qualified source result.

## Blockers

| Blocker | Before | Root cause | Fix | Verification | Status |
|---|---|---|---|---|---|
| `.forge/venvs` scanner | FAIL | Recursive filesystem scan includes ignored installed third-party sources | Git ownership inventory; tracked files override runtime exclusions; link/path/refusal checks | Exact original test fails on clean main with Latin1 venv reproduction, passes on repair; scoped 17 passed/1 skipped | Fixed locally; supported matrix pending |
| Benchmark digest #1 — empirical | FAIL | Stale 55-file source snapshot identified, but fresh rebuild cannot execute ngspice discovery through WSL | Original pin restored; no empirical repair claimed | Fresh standalone fails during import at `wsl which ngspice`, 60 s timeout; no artifacts rebuilt | E. UNRESOLVED |
| Benchmark digest #2 — model-measurement | FAIL | 55-file source snapshot differs from current 196-file source tree | Documented source-snapshot re-pin only | Fresh private rebuild executed; six reports differ only by CRLF, canonical JSON/numerical content identical; exact rebuild test passes after re-pin | B. STALE PIN / STALE EXPECTATION; metadata fixed |
| Python 3.11 FAST | 2 failures previously | Scanner plus stale certificate on prior main measurement | Scanner fixed; certificate unchanged | Current supported rerun NOT RUN: WSL cannot start | Blocked |
| Python 3.12 FAST | 2 failures previously | Same prior-main failures | Same | Current supported rerun NOT RUN | Blocked |
| Python 3.12 SCIENTIFIC | 2 failures previously | Same prior-main failures | Same | Current supported rerun NOT RUN | Blocked |
| FULL | 4 failures previously | Exact prior-main IDs attributed below | Two local repairs; empirical unresolved; certificate stale | FULL3.12 rerun NOT RUN | Blocked; no current count claimed |
| Windows baseline | 256 failed / 27 errors | Missing extras, POSIX/filesystem assumptions, 3.14/fresh-process behavior, optional Cantera compatibility | Clustered every failure; no mass test changes | 283 report IDs mapped; Cantera pair reproduces on preRound3 | Classified with limits |
| Recertification | REFUSED previously | Prior scanner failure; now incomplete qualification and unresolved empirical execution | No fabricated receipt or certificate | Current owner run NOT RUN under Task2 E stop condition | Blocked |
| Certificate verifier | FAIL | Certificate still covers old source commit | No new certificate generated | Fresh diagnostic verifier FAILED; exact certificate test fails alone on clean main | Blocked |

## Digest attribution

Both original tests pin `src/engcore/scientific/**/*.py` by sorted relative path, null separator and SHA256(file bytes), then SHA256 the concatenation. They do not digest the benchmark's numerical output and these constants are explicitly not certificates.

| Item | Value |
|---|---|
| Original expected digest, both audits | `715e6a6e625c1e1406f4e080ea664cdcfca0b15b61e58fc86cfb13710f2e0092` |
| Current Git-byte digest | `b9c4b76eb32ef726f5fab6f9f409556edf09247f63e19f0d9c86b5e9d9b3acd6` |
| Current Windows disk digest | Same `b9c4…` |
| LF-normalized disk digest | Same `b9c4…`; source mismatch is not CRLF |
| Pin-setting commit | `889d399a48f9fa21584b3571deb91d253c17f730` — third re-pin |
| First divergence | `b843a07b5fca4ea4bdc9dad4cf3415ed61b0418c` — Core API inventory |
| Pinned/current Python file counts | 55 / 196 |

Every changed/new scientific-tree file has both per-file hashes in external `digest-attribution.json`. Changes predate Rounds1–3; this repair modifies no file under `src/`.

**Model-measurement: class B.** Its exact test is `benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates`. Before repair, the private builder writes all seven artifact JSONs, then the test fails with passed9 instead of10. The sole content difference is MV-10's source-integrity digest/matches/verdict and passed10→9, failed1→2. VALIDATION_RESULTS, RESIDUAL_ANALYSIS, MODEL_ACCOUNTING, FINDINGS, FALSIFICATION and CONSISTENCY_AUDIT are LF-normalized byte-identical and canonical-JSON-identical. Individual original/rebuilt SHA256s: `model-measurement-artifact-bytes.json`. No observed solver number, tolerance or scientific verdict changed. The expected source snapshot is stale, not evidence of a numerical-output regression in this measured scope.

The authoritative update procedure is in the existing comments of both audit `build_gates.py` files: re-pin this non-certificate source snapshot when the Core moves. Commit889d399a performs this exact two-constant metadata procedure. Applied it only to model-measurement, preserving every published artifact and the intentionally failed MV-7 scientific finding.

**Empirical: class E.** Exact ID: `benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates`. Static byte attribution identifies an old source pin, but the fresh test times out during `reference.spice._argv()` import, before `build_gates.build()`. Scientific output equivalence therefore remains unknown. Its original expected digest remains unchanged. No raw pin repair is accepted on static identity evidence alone under the user's stricter task requirement.

## Correction of an attribution mistake

The first repair commit updated both pins after a comparison of private artifact directories. That comparison incorrectly interpreted the empirical fixture's unchanged copies as freshly rebuilt output. Its import had timed out, all empirical copied timestamps were0 and no output was rewritten. The empirical pin was restored in commit781a6492; the final diff against main contains no empirical helper change.

Corrected comparison `rebuild-comparison-corrected.json` explicitly marks empirical `NOT_REBUILT`, model-measurement `REBUILT`, and checks required rewritten files before comparing outputs. The independent reviewer recorded a HIGH attribution defect, resolved by withdrawing empirical equivalence and restoring the pin. Corrected-scope review verdict: PASS. Review is not executed qualification or scientific validation.

## The previous FULL's exact four IDs

| Test ID | Reproduces alone? | Reproduces on main? | Category | Root cause | Action |
|---|---|---|---|---|---|
| `tests/test_change_impact.py::test_the_old_gap_a_domain_models_own_tests_are_now_selected` | Yes with the ignored Latin1 venv file | Yes on clean 5d73 main control | KNOWN BASELINE | Unowned third-party source scanned | Ownership repair; exact after test PASS |
| `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` | Yes, 1failed in0.37s | Yes on clean main control | CERTIFICATE DRIFT | Certified bytes differ from stored target | Owner recertification only after complete supported qualification |
| `benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates` | Yes before, PASS after | Yes before on clean main control | STALE BENCHMARK PIN | Old source snapshot flips MV-10 integrity verdict | Metadata re-pin; published data retained |
| `benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates` | Current standalone blocked by WSL timeout | Prior complete3.12 main run had source-pin failure; current original assertion not reached | ENVIRONMENT | ngspice WSL discovery cannot execute; source-pin/output attribution incomplete | Leave pin unchanged, classE; stop final recertification |

These standalone checks used the explicitly documented diagnostic environment below. They do not replace the requested FULL3.12 rerun. The previous measured main result was10607 passed/4failed/157skipped; it is not a current branch result.

## Windows baseline clusters

The saved Windows FAST JUnit contains256 failures +27 errors, total283 reports. All report IDs/messages and clusters are retained in `windows-clusters.json`. A cluster is not an automatic waiver.

| Root-cause cluster | Count | Representative test | Supported CI effect |
|---|---:|---|---|
| POSIX-only API / platform assumption | 12 | `tests.test_mutation_workspace::test_local_telemetry_is_outside_manifest_and_cannot_verify_as_receipt` | No matching failures in previous Linux supported matrix. |
| Python 3.14 API/fresh-process environment | 9 | `tests.test_core_freeze_manifest::test_the_command_line_verifier_agrees_with_the_function` | No matching failures in previous supported matrix except separate stale certificate. |
| Windows interpreter ownership representation | 2 | `tests.test_mutation_startup::test_environment_snapshot_is_independent_of_parent_and_each_child` | No matching failures in previous Linux supported matrix. |
| Windows link/permission/path cleanup behavior | 9 | `tests.test_mutation_workspace::test_seed_symlink_and_git_external_pointer_are_refused` | No matching failures in previous Linux supported matrix; one real-link creation test also skipped in this repair. |
| Windows mutation workspace ownership / reparse checks | 114 | `tests.test_mutation_workspace::test_manifest_is_complete_deterministic_and_includes_git` | No matching failures in previous Linux supported matrix; Windows filesystem-specific failures remain red. |
| fixture checkout byte representation (.gitignore) | 6 | `tests.test_local_assurance::test_source_gate_orchestration_preserves_checkout[None-1]` | No matching failures in previous Linux supported matrix; not accepted as product-tree dirtiness. |
| missing MCP / dependent collection helper | 11 | `::tests.domains.battery.test_audit_domains_battery_pulse` | No matching failures in previous supported matrix with exact mcp extra. |
| missing cryptography / authority extra | 115 | `tests.foundations.test_v2_credibility_vector::test_the_projection_is_complete_and_a_fully_evidenced_claim_meets_high` | No matching failures in previous supported CI-equivalent matrix; its mcp extra installs cryptography. |
| optional Cantera / NumPy compatibility | 2 | `providers.cantera.tests.test_cantera_provider::test_proof_b_adiabatic_equilibrium_with_mechanism_bytes_bound` | Provider absent and skipped in previous supported CI-extra environment; installed-provider compatibility not established. |
| stale certificate | 1 | `tests.test_core_certificate::test_the_certificate_describes_this_tree` | YES: exact supported-version failing test and verifier drift. |
| subprocess escrow handshake | 2 | `tests.foundations.test_escrow_boundary::test_the_subprocess_escrow_resumes_its_journal_but_stays_unproven` | No matching failures in previous supported matrix; precise environmental attribution remains limited. |

The missing dependencies are absent in the primary Windows environment; prior isolated CI extras `.[dev,mcp,oracles]` install cryptography and the correct MCP SDK. POSIX APIs, symlink privilege and Windows mutation workspace checks explain large independent clusters. The two Cantera tests reproduce on clean preRound3 `9ca337f9` with the same installed provider: `SolutionArray` raises NumPy's referenced-array resize ValueError, and the transient result lacks a temperature series. This is an optional-provider compatibility defect/baseline, not a Round3 change; Linux CI-extra environments skip that unavailable provider, so no installed-provider success is inferred.

Two escrow handshakes retain limited root-cause attribution; they are explicitly open environmental/process questions. No claim is made that every Windows failure is harmless or that Windows compatibility is complete. The package declares Python>=3.11 with no upper bound; Python3.14 is outside the CI acceptance matrix, which does not waive its advertised compatibility debt.

## Environment and execution limitations

Windows launcher lists3.14.2 and3.10, no native3.11/3.12. Previously measured WSL seed interpreters are3.11.16 and3.12.14; they are inaccessible in this repair session. Even WSL echo and shutdown stall. Normal `Restart-Service Winmgmt` cannot open the service. User explicitly authorized WSL/WMI restart; elevation attempts exited1 without a restart log or receipt. Both services still report Running; that does not prove a successful restart.

Fresh Python3.14 scientific import stack: `platform._wmi_query → _win32_ver → win32_ver → uname/system → flexcache.BasicPythonHeader → Pint → engcore.scientific.units`. Separate NumPy2.4.3/SciPy1.18.0 import succeeds. This is a measured import/environment block, not a failed numerical test or a new source regression. Normal `forge_check --changed` and several ordinary local test attempts remain INCOMPLETE, not passes.

For diagnosis only, external `diagnostic_no_wmi.py` selects CPython's existing native Windows fallback by making WMI unavailable inside that process. It edits no installed dependency, repository runtime, test assertion, tolerance or system setting. Native Windows version is observed directly. These diagnostic results are labeled throughout and are NOT supported-matrix assurance, an owner receipt, certification or physical validation. Tests with fresh subprocesses may still hit the normal WMI block.

## Executed checks and exact limits

All raw commands and output logs live under `D:/forge-assurance-fix-evidence/`.

- Before repair, scope tests: `py -3.14 -m pytest tests/test_impact_repository_scope.py -q --basetemp=D:/forge-assurance-fix-evidence/before-temp` →5failed/8passed/1skipped. Initial nonexistent basetemp-parent fixture errors were a driver error, corrected before this result.
- Focused final scope tests: explicit3.14 `pytest_entry.py -p no:faulthandler tests/test_impact_repository_scope.py -vv -s --basetemp=.../scope-trace-temp` →17passed/1skipped in2.02s. Real directory-link creation is unavailable on Windows; link refusal, path escape, foreign Git root, nonregular input and dangling metadata are also tested without that privilege.
- Existing impact tests: `pytest_entry.py -p no:faulthandler tests/test_change_impact.py -q --basetemp=.../graph-timeout-temp` →68passed in11.32s.
- Corrected scanner + existing impact/tool diagnostic: `diagnostic_no_wmi.py tests/test_impact_repository_scope.py tests/test_change_impact.py tests/test_forge_impact.py -q --basetemp=.../local-complete-temp --junitxml=.../local-complete.xml` →89passed/1skipped in13.67s.
- Exact scanner main/after pair: `diagnostic_no_wmi.py tests/test_change_impact.py::test_the_old_gap_a_domain_models_own_tests_are_now_selected -q` with real-main-repro/real-fixed-repro external temp/XML → main1failed in6.72s; repair1passed in7.54s.
- Before source re-pin, both rebuild selectors on clean main control, diagnostic temp `benchmark-fallback-temp` →2failed in63.65s. Empirical is import timeout, not a completed rebuild; model-measurement is stale MV-10 pin.
- After re-pin on clean source5d3dd047, same selectors, temp `benchmark-after-temp` →1passed(model-measurement),1failed(empirical WSL timeout) in62.96s.
- Standalone optional Cantera pair on9ca337f9: diagnostic temp `cantera-baseline-temp` →2failed/1warning in1.91s.
- Exact certificate test on clean main: diagnostic temp `certificate-main-temp` →1failed in0.37s.
- Fresh diagnostic `core_certificate --verify` on source5d3dd047 →FAILED, target39d43456, aggregateb697c9d4. First external wrapper lacked root/src sys.path; corrected driver read this worktree, not another editable install.
- `git diff --exit-code origin/main -- src/ experiments/ certification/ tests/api/ tests/test_sria_e1_electrical.py tests/test_sria_e2_model_adequacy.py` →exit0. Benchmark JSON changed-name list empty. `git diff --check` →exit0.

Supported3.11 FAST,3.12 FAST/SCIENTIFIC/FULL, current regression pack, owner recertification, certificate-only child commit and post-recertification verification: NOT RUN in this repair. Empirical classE independently prohibits final recertification. Previous-session counts are contextual evidence only.

## Certificate and scientific safety

Certificate before/after target remains `39d43456cab918ed0748efe7f5b0ff5781474ffa`; before/after SHA256 `c22a012147c26183031b32b0e016c80ef86218ef3cd1664361be47d4cf2f186b`. No certificate or owner evidence file was generated. The documented eventual procedure is Local Assurance prepare/run, reserved certificate-only child, then verify; a documentation/fix commit is not that child.

No scientific runtime file, scientific verdict logic, Trust authority, evidence admission, applicability, UQ semantics, Mind behavior, solver equation/numerics, frozen experiment result, benchmark JSON, manifest, certificate, pinned API or experiment test was changed. The remaining benchmark edit is a source-snapshot expectation only. Missing qualification remains missing.

Local commits:5d3dd047 (scanner, tests and provisional pins);781a6492 (restore unproved empirical pin); final documentation commit records this correction. Final files versus main: tools/test_impact.py, tests/test_impact_repository_scope.py, benchmarks/model_measurement_validation/audit/build_gates.py, docs/work/ACTIVE_PLAN.md, docs/work/PROGRESS.md, this report. No empirical helper diff remains.

Resume from this branch after the authorized host environment recovery can be completed: run the empirical rebuild with actual ngspice, establish fresh artifact provenance/content and a permitted pin disposition, run the exact supported matrix/FULL/regression, then invoke authoritative owner recertification. Do not weaken assertions, skip new failures, reuse copied artifacts as execution evidence, or start another performance round.
