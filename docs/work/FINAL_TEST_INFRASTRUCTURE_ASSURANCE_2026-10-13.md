# Final test infrastructure assurance closeout — 2026-10-13

Status: **TEST_INFRASTRUCTURE_FINAL_ASSURANCE_BLOCKED**.

Measured source: `5d73e8f5118aa845f1957decc5aae986e72476a9` (current origin/main, checked before and after the runs; matches the requested SHA).
Source tree: `ed305a44e69429fe06bb1e92954237aadd005080`.
No source implementation or frozen artifact was changed. This report and the appended work records are documentation only and are not a certification child.

## Results

| Check | Result | Details |
|---|---|---|
| Starting main SHA | MATCH | 5d73e8f5118aa845f1957decc5aae986e72476a9 |
| Python 3.11 FAST | FAIL | 10,185 JUnit cases; 10,026 passed, 2 failed, 0 errors, 157 skipped; 140.22 s |
| Python 3.12 FAST | FAIL | 10,185 cases; 10,026 passed, 2 failed, 0 errors, 157 skipped; 132.22 s |
| Python 3.12 SCIENTIFIC | FAIL | 10,758 cases; 10,599 passed, 2 failed, 0 errors, 157 skipped; 234.26 s |
| Current regression pack | PASS | Windows Python 3.14: 256 passed; 20.72 s wall (17.51 s pytest); Linux 3.12: 256 passed, 11.21 s wall |
| Primary Windows FAST | FAIL | 10,056 JUnit reports; 9,563 passed, 256 failed, 27 errors, 210 skipped; 222.20 s; 6 collection error reports included |
| FULL | FAIL | Unrestricted supported Python 3.12: 10,768 cases, 10,607 passed, 4 failed, 0 errors, 157 skipped; 147.29 s; no xfail/xpass |
| Primary Windows FULL | INCOMPLETE | Stalled around 79%; controller had no remaining workers; stopped, empty final XML; no trustworthy final counts |
| New failures | BLOCKED attribution | Supported tiers add no unexplained failure after the baseline scanner control. Windows adds 111 IDs to saved baseline's 172; same-environment baseline stalled, so no global zero-regression claim |
| Frozen artifacts changed unexpectedly | 0 | All 5,514 tracked Windows files hashed before/after: byte drift 0. Linux complete-tier snapshots also byte drift 0. Certificate digest unchanged |
| Tree clean after tests | PASS | git status --porcelain empty; authoritative assert_clean_tree PASS on Windows and Linux, including Linux after owner refusal |
| Recertification | REFUSED | Authoritative local_assurance run --repository sharq-labs/forge; fast311: 10,005 passed, 1 failed, 157 skipped; later gates not reached |
| Certificate verifier | FAIL | Before and fresh process after refusal: old certificate does not describe this source tree |
| Final certified SHA/tree | NOT CURRENT MAIN | Stored certificate names 39d43456cab918ed0748efe7f5b0ff5781474ffa; no new certificate or certification child produced |

Wall times include the external runner's process and integrity work. Windows and Linux ran in separate trees, with overlapping execution; these timings are telemetry, not performance comparisons. Peak memory was not measured during the accepted runs. JUnit cases are selected execution reports; skipped cases are included. No skipped optional-provider suite is claimed exercised or validated.

## Supported-environment failures

FAST 3.11, FAST 3.12 and SCIENTIFIC 3.12 have exactly these IDs:

- `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` — CERTIFICATE DRIFT.
- `tests/test_change_impact.py::test_the_old_gap_a_domain_models_own_tests_are_now_selected` — KNOWN BASELINE, reproduced on clean pre-Round-3 `9ca337f9` using the documented environment preparation, on both 3.11 and 3.12.

FULL additionally has:

- `benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates` — KNOWN BASELINE.
- `benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates` — KNOWN BASELINE.

The two rebuild failures are recorded in current docs/TESTING.md and Round 2 PROGRESS as pinned scientific-core digest drift. They rebuild privately; the complete run changed zero tracked bytes. The scanner's `_SKIP_DIRS` does not exclude `.forge`; preparation puts third-party Python code under `.forge/venvs`, and the real graph's no-unparseable-files assertion encounters encoding/version syntax there. The same scanner and failing test exist before Round 3. No exclusion was added to make the gate pass.

The Windows primary environment differs from the previous timing environment: pytest 9.0.2 versus prior 9.1.1, absent cryptography and MCP distribution metadata, and installed optional Cantera. Missing `mcp.types`, POSIX-only APIs, Windows symlink privileges, CRLF/seed identity and fresh-process import failures are environmental observations, not physical-model validation results. Two Cantera failures are OPTIONAL PROVIDER; their regression attribution remains unresolved because the direct baseline diagnostic also stalled. Exact IDs, messages and a classification for every failure report are in `D:/forge-final-assurance-evidence/failure-classifications.json`. Saved baseline JUnit and failure lists are preserved beside it.

## Environment and authoritative procedure

Windows 11 Pro 10.0.26200, 24 logical CPUs, 34,070,192,128 bytes RAM (31.73 GiB). Primary installed interpreter: Python 3.14.2, pytest 9.0.2, xdist 3.8.0. Windows launcher also lists 3.10; 3.11/3.12 are unavailable on Windows. Bare `python` resolves to the Microsoft Store alias and cannot execute. Explicit launcher/interpreter paths were used.

WSL Ubuntu, Linux 6.6.87.2-microsoft-standard-WSL2, glibc 2.39, 24,031 MiB memory visible, no swap. Existing seed interpreters: 3.11.16 (sci) and 3.12.14 (battery). Isolated `.forge/venvs/3.11` and `.forge/venvs/3.12`: pytest 9.1.1, xdist 3.8.0. Both installed exactly `.[dev,mcp,oracles]` through the repository preparation command; complete pip freezes and provider probe are in the evidence directory. ngspice is `/usr/bin/ngspice`; optional providers unavailable in these isolated environments remain declared skips.

Documentation/tooling discovered before execution: docs/TESTING.md, docs/assurance/LOCAL_ASSURANCE.md, .github/workflows/tests.yml, .github/workflows/recertify-hardened-core.yml, tools/certification/local_assurance.py, core_certificate.py, core_freeze_v4.py, recertification_scope.py and certificate_lineage.py. Commands were reported to the user before test/certificate execution. Current workflows designate Local Assurance as authoritative and are manual references; no remote CI result or branch policy update is claimed.

Authoritative workflow: `python -m tools.certification.local_assurance prepare`, `run`, certificate-only child with reserved subject `certification: recertify hardened core`, then `verify`. A standalone `core_certificate --build`, an invented receipt, or manual dispatch is not used as a substitute.

Preparation used explicit seed paths:

```bash
/home/dev_kaeem/mm/root/envs/battery/bin/python -m tools.certification.local_assurance prepare --python311 /home/dev_kaeem/mm/root/envs/sci/bin/python --python312 /home/dev_kaeem/mm/root/envs/battery/bin/python
```

The owner execution command was:

```bash
.forge/venvs/3.12/bin/python -m tools.certification.local_assurance run --repository sharq-labs/forge
```

It returned exit 1, LOCAL_ASSURANCE: REFUSED, SAFE_TO_PUSH: NO. Failed gate: fast311. The only failing test was the known scanner failure. Its built-in certificate/freeze deferrals were unchanged; no extra test was deselected. Formal/V4/Trust mutations, campaign and later owner gates were NOT RUN because the runner stopped at its first failed gate. The certificate-only commit and local_assurance verify are NOT RUN because no certificate was generated.

Failure receipt SHA-256: `a1965de5a5495082706237ba7c5c6c4e251fffff812ab92286b6cf272ecde488`.
Certificate before and after SHA-256: `c22a012147c26183031b32b0e016c80ef86218ef3cd1664361be47d4cf2f186b`.
Expected certificate aggregate: `30702e0e7e14a3c2085e530af6b9821a1082767fe438e5052a635c28b8dd0a6b`.
Current aggregate: `b697c9d4413da45c26fd4fed0939a6cd8b171ddea5400b53c63b858cc7940bcf`.
Drift: 15 certified files in certification_control, execution_trust, harness, inference_admission and runtime_dependencies. The certificate file itself was not changed.

Fresh process after refusal: core_certificate --verify FAILED; core_freeze_v4 --verify FAILED only at certificate.verifies on Python 3.12; forge_check --regression 256 passed in 7.40 s; assert_clean_tree PASS. These are post-attempt checks, not successful post-recertification verification.

## Commands and evidence

External evidence: `D:/forge-final-assurance-evidence/` (JUnit, raw logs, pip freezes, hashes, provider inventory, failure classifications, owner failure receipt and argv/result inventory). Linux source worktree: `/home/dev_kaeem/forge-final-assurance`; Linux baseline: `/home/dev_kaeem/forge-final-assurance-baseline`; Windows source: `D:/forge-final-assurance`; Windows baseline: `D:/forge-final-assurance-baseline`. Linux worktrees use an isolated bare clone sharing source objects read-only; the original dirty checkout is untouched. Exact argv and outcomes: `executed-commands-and-results.json`; major environment rules: FORGE_IMPACT_CACHE=off, Linux CRAFTY_NGSPICE_ARGV=ngspice; Windows retry PYTEST_ADDOPTS uses a unique forward-slash basetemp outside the repo.

Tests ran the repository commands, including:

```bash
python -m pytest tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared -q
python -m pytest -m "not expensive" -q -n 4 --dist loadfile --deselect tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared
python -m pytest -m "not campaign" -q -n 4 --dist loadfile --deselect tests/test_core_guards.py::test_every_dependency_the_tree_reaches_for_is_declared --deselect tests/test_heterogeneous_ngspice.py::test_a_the_provider_is_a_real_external_process --deselect tests/test_heterogeneous_ngspice.py::test_g2_a_genuine_non_zero_exit_is_a_provider_failure --deselect tests/test_heterogeneous_ngspice.py::test_j_relocating_the_provider_leaves_the_result_byte_identical --deselect benchmarks/model_measurement_validation/tests/test_model_measurement_validation.py::test_rebuilding_everything_reproduces_the_published_gates --deselect benchmarks/empirical_validation/tests/test_empirical_validation.py::test_rebuilding_everything_reproduces_the_published_gates
python tools/forge_check.py --regression
python -m pytest -q -n 8 --dist loadfile
python -m tools.certification.core_certificate --verify
python -m tools.certification.core_freeze_v4 --verify
python -m tools.certification.assert_clean_tree
```

JUnit output arguments were appended outside the repo. Dependency guard passed separately on all three interpreters. FULL on supported 3.12 used no marker selection/deselection. No parallel/sequential contradictory verdict was established; the Windows incomplete run cannot supply sequential semantics or a success claim.

## Failed approaches and limits

- Initial Windows-created worktree could not be used by Linux Git because its .git file points to a Windows absolute path; documented prepare refused. A Linux-created dedicated worktree at the same SHA resolved this without touching the user's dirty checkout.
- Windows default pytest temp directory was inaccessible: initial regression 252 passed + four fixture errors; FAST/FULL exited 3 before tests. Dedicated basetemp resolved it.
- The first basetemp retry used backslashes, stripped by option parsing, and produced an untracked temp directory. Integrity check stopped immediately; tracked drift remained 0. Deletion was rejected by automatic approval review; the folder was moved intact outside the worktree. Forward-slash retry passed 256 regression tests and left the tree clean.
- Initial owner command could not infer the repository from a local clone origin; explicit supported --repository resolved this.
- Windows FULL stalled, had no remaining xdist workers and produced an empty XML. Same-environment baseline FAST stalled too; it was stopped after 510.82 s. Diagnostic process identities and stop actions were recorded before termination. These runs are INCOMPLETE, not failing-test skips or accepted assurance evidence. The external runner could not parse the empty FULL XML, so its final FULL result is recorded here separately.
- Windows pip process-tool installation and direct Cantera baseline diagnostic also stalled. Only task-owned processes were stopped. No system configuration, existing provider environment, original checkout, tolerance, pinned expectation or freeze manifest was changed.

## Scientific safety and next required action

This closeout changed no scientific verdict logic, evidence admission, applicability semantics, uncertainty semantics, Trust/authority rules, Mind behavior, solver numerical behavior or frozen experiment results. No scientific validation or readiness is claimed by software test passes. No certificate was updated, committed or pushed; no force push occurred.

Blocking next work: resolve the scanner's interaction with the documented .forge environment under a separate bounded infrastructure repair, investigate the incomplete Windows controls/optional Cantera failures if Windows assurance is required, rerun the exact current-source gates, and run the complete authoritative owner sequence. The four supported FULL failures remain red; they are not hidden or weakened.

Additional final Linux all-file hash replay was INCOMPLETE because a new WSL invocation stalled and was stopped. The completed per-tier hash snapshots and fresh post-owner assert_clean_tree PASS remain the Linux integrity evidence. Windows final all-file replay completed with 5514 tracked files, drift0. A read-only Windows WMI process query also stalled; task-owned query processes were stopped.
