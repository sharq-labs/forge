# Final Scientific Integration Verification — 2026-10-18

**PASS_WITH_EVIDENCE within the tested developer scope; current-record archive readback remains unresolved and blocks dependent claims.**

D1, D2 and D3 were explicitly approved by the owner, verified against exact proposal/preimage hashes and applied without expanding scope. A fresh census met D2's condition before application. The prior Phase0 stop is preserved in [historical preflight](evidence/final_integration_phase0_blocked_2026_10_18.md); it is not retroactively called a pass. No integration prerequisite was bypassed.

## 1. Exact source and approved application

Worktree `D:/forge-main-337519d1`, branch `fix/post-merge-remediation-2026-10-18`, HEAD `93ed64b0292e9fea714ac83affb64b71488ac050` plus the recorded uncommitted source. HEAD alone does not identify the tested tree. All tested scientific jobs and the archive diagnostic share one aggregate source identity; full before/after maps cover src/tests/tools Python, certification JSON, completion policy/ledger, program contract and freeze policy. Every job's map is unchanged, and final bytes match that map. The pre-application environment/census jobs have their own accurately separated source identity.

The32 existing modified/untracked files were copied with hashes before application. D1 changes only its status-specific test expectations, failed-predecessor PASS/FAIL negative coverage and two policy lines. The checker itself is unchanged. D2 changes EXPECTED_MODELS19→20/comment only. D3 adds the anchored issuance-key diagnostic to BOTH existing assertions; it keeps exception type, tampering fixture, transfer and coarsen calls. No new production source change was made in this integration turn; earlier approved P0 changes remain.

Exact application/approval record, patch hashes and pre/postimages: [application](evidence/final_integration_approved_2026_10_18/application.json). [Owner dispositions](FINAL_OWNER_DISPOSITIONS_2026_10_18.md) records actual approved/applied status. Creation of that document alone never granted authorization. Final scientific source identity:

`5f7c2171abca8e915bfc5102d5eb286d06d140bdfd6c6e1f0d4e99ed9547b3df` over1464 indexed files.

- `src/engcore/claims/execution.py`: `54c493324f1f958c647b70a93795f2581a8a3fa3b058980023c9b889916f3f06`
- `src/engcore/claims/replay/bundle.py`: `c0831464c9e00c3cb6262a418623b0e046b7d38f5b9a7f4d597095aa463aced5`
- `src/engcore/domains/thermal_models/conduction1d_transient_fv.py`: `6596154d9dce909d9149e9fbae08540b00e26bef73e00fb192460a8cddb23273`
- `src/engcore/scientific/composition/conversion.py`: `24ee129177191a01ce5a0cf8e22e34762af3df782fc829ab2ee1f301abef15b9`
- `tests/test_capability_completion.py`: `33e771423239b94595b3d6059c3336c594c878b6dde4fd59b4f19bfa4c7caadf`
- `tests/test_core_guards.py`: `67ff9b71e4d9bc99b66c4b1f3867f9d0358ec6f6c5d40d80a7a92d9f1f5215b8`
- `tests/test_m1a_mesh_lineage.py`: `138ad98e4ca64e0c491067301969f53b7fa523a50e275aac2fe3e3087e8f870f`
- `tests/test_p0_conservation_policy.py`: `f1a4d3dd2c5bc6158ba5dab5965d8001143d24f33f8d22d745a8522ef8240560`
- `docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md`: `46df957e9d170cba855f794d28413b7faf2a0d1ef2761f5b74e7e593f351c781`
- `tools/capability_maturity.py`: `75b89c187f5cbcc9e8746537eb62b140a2be0cc33b88e776272f71973dbd124d`

## 2. Environment and execution discipline

Existing project interpreter `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe`: CPython3.14.2, NumPy2.5.2, SciPy1.18.1, Pint0.25.3, pytest9.1.1, MCP2.1.1. The actual census resolves engcore to `D:/forge-main-337519d1/src/engcore/__init__.py`. No dependency or shared environment was changed.

Plain SciPy/Pint import freshly reproduced the WMI hang, timing out after12.004s; preserved traceback enters stdlib platform._wmi_query. Only that task-owned probe was terminated by its bounded timeout. Subsequent jobs use task-local sitecustomize `platform._wmi=None`, which invokes the actual stdlib Windows fallback and fabricates no platform values. BLAS threads1, PYTHONDONTWRITEBYTECODE1, task/src/root/tests-claims PYTHONPATH and unique forward-slash pytest basetemps are recorded per job. Current packages/interpreter metadata came from the executed census, not an assumed shared environment.

The complete conservation pack ran once, unchanged, with a1200-second subprocess limit. Other explicitly authorized suites ran on the same source; no duplicate conservation pack, reduced parameter population, full suite, full FAST tier, standalone mutation campaign or full assurance was launched. The fixed forge_check regression kept its existing selection, including its existing small sentinel. Wall time is measured; CPU/RSS and performance attribution are not claimed. Source snapshots bracket each command.

## 3. Complete executed command matrix

All rows include exact interpreter/argv, working state, env, before/after source indexes and complete log SHA256 in [machine evidence](evidence/final_scientific_integration_approved_2026_10_18.json). Counts are not summed across overlapping suites. A diagnostic exit0 is not a registry-compatibility PASS; the import timeout is not a passing check.

| Run | Exact command | Exit / status | Counts/result | Wall seconds | Complete log |
| --- | --- | --- | --- | ---: | --- |
| env-plain | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -c "import faulthandler; faulthandler.dump_traceback_later(5); import scipy.sparse,pint; print('scientific imports available')"` | None / BLOCKED_TIMEOUT | WMI import timeout; no test counts | 12.004 | [env-plain](../work/evidence/final_integration_approved_2026_10_18/env-plain.log) |
| census-before | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B D:/forge-main-337519d1/.pytest-review-temp/owner-dispositions-2026-10-18/census.py` | 0 / EXECUTED | Complete20 census; full-registry readback refusal retained | 5.048 | [census-before](../work/evidence/final_integration_approved_2026_10_18/census-before.log) |
| targeted-paths | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -p final_path_audit -vv tests/test_capability_completion.py tests/test_m1a_mesh_lineage.py::test_nested_record_tampering_poisoned_lineage_is_fail_closed` | 0 / EXECUTED | ============================= 29 passed in 49.40s ============================= | 50.035 | [targeted-paths](../work/evidence/final_integration_approved_2026_10_18/targeted-paths.log) |
| discovery-gates | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/test_core_guards.py -k "discovery_found or solver_discovery"` | 0 / EXECUTED | 3 passed, 273 deselected, 12 warnings in 6.39s | 7.470 | [discovery-gates](../work/evidence/final_integration_approved_2026_10_18/discovery-gates.log) |
| claims-replay-final | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/claims/test_claims_assessment.py tests/claims/test_quantitative_uq.py tests/claims/test_external_evidence.py tests/claims/test_sensitivity_robustness_challenge.py tests/claims/test_impact_replay.py tests/claims/test_scientific_diagnostics.py tests/claims/test_sria_context_authority.py tests/claims/test_p0_replay_execution_authority.py` | 0 / EXECUTED | 175 passed in 23.03s | 24.012 | [claims-replay-final](../work/evidence/final_integration_approved_2026_10_18/claims-replay-final.log) |
| unified-conservation-48 | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -vv --durations=12 tests/test_p0_conservation_policy.py` | 0 / EXECUTED | ======================= 48 passed in 811.21s (0:13:31) ======================== | 811.703 | [unified-conservation-48](../work/evidence/final_integration_approved_2026_10_18/unified-conservation-48.log) |
| m1abc-final | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q tests/test_m1c_transient_fv.py tests/test_m1b_vertex_dual_state.py tests/test_m1a_mesh_lineage.py` | 0 / EXECUTED | 124 passed in 123.16s (0:02:03) | 123.817 | [m1abc-final](../work/evidence/final_integration_approved_2026_10_18/m1abc-final.log) |
| fixed-regression-final | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B tools/forge_check.py --regression` | 0 / EXECUTED | 279 passed in 13.48s | 14.310 | [fixed-regression-final](../work/evidence/final_integration_approved_2026_10_18/fixed-regression-final.log) |
| compatibility-final | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B -m pytest -p no:cacheprovider -q -rs tests/test_core_api_snapshot.py tests/test_core_api_serialization.py tests/test_core_api_layering.py tests/test_core_freeze_policy.py tests/test_certified_dependency_closure.py tests/test_post_merge_import_smoke.py` | 0 / EXECUTED | 153 passed, 1 skipped in 34.92s | 35.436 | [compatibility-final](../work/evidence/final_integration_approved_2026_10_18/compatibility-final.log) |
| archive-readback-investigation | `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B D:/forge-main-337519d1/.pytest-review-temp/final-integration-approved-2026-10-18/archive_readback_probe.py` | 0 / EXECUTED | Known current-/2 readback REFUSED; M1C readback succeeds (diagnostic only) | 1.346 | [archive-readback-investigation](../work/evidence/final_integration_approved_2026_10_18/archive-readback-investigation.log) |

## 4. Authority, replay and intended negative paths

Claims/replay suite:175 passed, no skips. It includes all seven previously failing named suites plus the P0 execution-authority controls. Repeated refusals/incomplete assessments cannot grant VERIFIED; mismatched run identities and changed solver values are detected. Caller values do not replace sealed reports; missing UQ remains unknown/insufficient; verification cannot satisfy a physical-validation requirement; wrong charter/decision/context are refused. Structural CredibilityEvidenceError/InvalidModelRealization remain defects, while expected input/execution refusals remain insufficient.

Gate/M1A targeted run:29 passed. A task-local observer traced only the selected approved negative-control calls, without modifying tests or runtime. [Reachability evidence](evidence/final_integration_approved_2026_10_18/negative-control-paths.json) records all three missing-M1 branches, both failed-M1→downstream PASS/FAIL parameter cases and their checker lines. It also records the tampered transfer at test174 and subsequent coarsen at176, with `_IssuedRecords.verify`'s exact conflict refusal at mesh_adaptation.py224 executed twice. The formerly unreached coarsen assertion now has direct executed coverage. The subsequent complete parent pack runs without that observer.

This confirms the intended refusal paths rather than merely renamed tests. BLOCKED_WITH_EVIDENCE still requires decided predecessors, evidence and next action; it cannot grant PASS, maturity or scientific support. The checker and ledger are unchanged. The tampered lineage keeps refusing while corrupted; no irreversible poison flag or attacker-restoration guarantee is inferred.

## 5. Unified conservation and M1A/M1B/M1C

Unified pack: ======================= 48 passed in 811.21s (0:13:31) ========================; 811.703s wall, limit1200s. All48 cases passed together in one process invocation on the identical final source bytes.

The48 tests retain every N=4,16,32,64,128,256,512; original fixed1e-7J leak and shifted counterexample; equilibrium and redistribution; heterogeneous conductivity/storage/area; sources, insulated/prescribed-flux boundaries; datum/timestep changes; nonfinite/overflow controls; high-Fourier stress. No parameter, leak control or expensive combination was removed from the approved48-case pack, and no tolerance changed. The corrected gross-exchange expectation stays3.75W with original rel1e-7, distinct from signed net2.75W. Previous42/6 then6 results remain historical and are not substituted for this single execution.

The global policy uses Fraction arithmetic over finite represented inputs with declared atol+rtol*exchange; interior face magnitudes cannot inflate its global budget. The legacy matrix allowance remains local only. Exact evaluation is not exact physics or solver accuracy, experimental validation, model discrepancy closure or known uncertainty. High-Fourier tests may refuse at any numerical stage and do not prove global-gate reachability or acceptance of all legitimate roundoff. Factor-based inf/nan/overflow controls do not cover all finite-input overflow. No end-to-end cost attribution to Fraction/setup is made; prior kernel timings are not a whole-runtime profile.

Full M1A/M1B/M1C pack:124 passed, no failures/skips. M1C construction uses the existing thermal capability and realization0.2.0 with model0.1.0, unchanged equations/tolerances. Manufactured spatial/temporal, refinement and conservation studies ran. M1B weighted-transfer and M1A lineage/ancestry/refusal controls ran; tampered downstream coarsening is separately traced above. These are mathematical/software verification, not experimental validation or M1D completion.

## 6. Registry and fixed regression

Fresh pre-application census:20 unique model keys, no import failures/optional absences, one object/serialized digest per key across aliases. Historical19 comparison has exactly one addition `thermal.conduction1d.transient_piecewise_linear@0.1.0`, none removed. The realization0.2.0 is not another physical model.17 realization keys construct a registry with nonempty capabilities and resolvable model references; no new capability identifier was invented. Census inventory and aliases are fully embedded in machine evidence. Other counts16 reserving/96 condition names/63 reserved names and the11-solver pin remain unchanged.

Post-application selected discovery/solver tests:3 passed,273 deselected. Full capability-completion tests ran in the29 targeted pack. Fixed bounded regression:279 passed, zero failures/errors/skips. It was the existing exact `python -B tools/forge_check.py --regression` selection; it was not replaced with a smaller pack. The prior missing-M1 BLOCKED diagnostic mismatch,19-versus20 pin mismatch and M1A regex mismatch are no longer failing in this final source. Original failure logs remain preserved.

## 7. Compatibility and separate archive defect

Requested compatibility pack:153 passed,1 skipped. Explicit skip: `tests/test_certified_dependency_closure.py:441`, this Windows platform cannot create symbolic links. That path has no successful execution evidence here. Public snapshot, sampled serialization/determinism, layering, freeze/dependency and three fresh-process import checks executed; this does not certify every instance of every current scientific record.

Separate [archive-readback investigation](FROZEN_MODEL_ARCHIVE_READBACK_INVESTIGATION_2026_10_18.md) reproduces failure for `thermal.conduction1d.linear_diffusion@0.1.0`, current scientific_model_definition/2 with null exclusions. Both direct model and registry reconstruction refuse; positive M1C controls read successfully. Deliberate legacy/1 omission refusal is evidenced by an existing fixture, but the shipped current/2 object's failure conflicts with current-format roundtrip promises. Frozen source receives a module-scoped authoring exemption; ordinary portable readers do not. No missing exclusions are silently declared empty, and no false support was demonstrated.

**Archive compatibility: FAIL_WITH_EVIDENCE. Scientific impact remains UNCLASSIFIED and blocking for dependent portable archive/registry/reconstruction claims.** No archive repair, exemption widening, identity change, schema change or historical artifact regeneration was performed. Do not reinterpret the153 passing aggregate tests as a PASS for this demonstrated failure.

Static dependent-path tracing: the inspected certification registry source probe imports/hashes model objects, the claims replay registry is CapabilityRegistry, and existing synthetic Genesis baseline uses Blindfold expressions/universes/escrow/evaluator records. None of those exact inspected paths was shown to decode this frozen model. This is not qualification of arbitrary plugins, future arms or every certification consumer. Full assurance/OD-3 and Genesis measurement were not run. The known defect blocks dependent claims; shared package names alone do not prove dependence of independent baseline measurements.

## 8. Independent final-source review

All reviews were read-only on actual applied source and recorded final indexes; no reviewer executed tests or edited source.

- A+D `p0_authority`: no BLOCKER/MAJOR/MINOR in applied authority/replay/gate correction; exact application postimages match; no evidence/UQ/applicability weakening; read path trace confirms intended controls. OBSERVATION: harness identity changed and remains uncertified.
- B+C `p0_conservation`: no new BLOCKER/MAJOR in exact global policy/M1C/census/M1A; hashes match unchanged before/after source; retained stress/roundoff/nonfinite coverage limits. Execution of unified48 is main-agent evidence, not inferred from review.
- Separate `closure_review`: pre-existing current-record compatibility defect with conflicting contracts, not merely harmless documentation. Dependent scientific impact UNCLASSIFIED; no blanket synthetic-Genesis dependency demonstrated. No archive change approved.

Final read-only report review independently checked all10 durable log hashes, all1464 indexed current files, before/after equality and the canonical source identity. Numerical review read the actual48-pass log and parent124-pass log; neither reviewer executed tests. No new report-integrity BLOCKER/MAJOR was found. A static PASS is not test execution, owner disposition of the archive contract or certification.

## 9. Preservation and certification impact

All three approved patches stay uncommitted. Application snapshots preserve the32 starting modified/untracked files; earlier P0/post-merge/owner-analysis/preflight manifests and negative logs remain. The earlier blocked preflight report is copied unchanged before updating this current report. No unrelated checkout/process or shared package was altered.

No certification manifests, maturity ledger, active epic, governing physical equations, tolerances or historical bundles changed. D1 clarifies existing policy only. D2 changes certificate-pinned tests/test_core_guards.py harness identity (core_certificate.py521; current_core_v2.json11282), and earlier P0 claims execution/replay/conversion source is trust-sensitive/pinned. All such working source remains UNCERTIFIED. Passing freeze/API tests do not refresh source attestations or make old evidence attest new bytes.

OD-3 preparation may use this concrete evidence and archive-impact analysis for owner review. Formal readiness still requires archive-contract/dependent-scope disposition where relevant, separate authorization, clean committed final source, supported Linux Python3.11/3.12 dependencies, required normal integration/hardened recertification and policy checks. OD-3, full assurance, full integration tiers/full suite, standalone mutation campaign, historical bundle regeneration, commit/push/PR/merge/rebase are NOT RUN/performed here.

## 10. Readiness matrix

| Component | Evidence | Tests | Scientific risk | Status |
| --- | --- | --- | --- | --- |
| Evidence Authority | Bound result/report controls and source identity |175 claims passed | Bounded scope only; no experimental validation inferred | PASS_WITH_EVIDENCE |
| Replay Integrity | Changed outputs/identity/context and repeated-refusal controls |175 claims passed | Does not qualify dependent frozen-model archive reader | PASS_WITH_EVIDENCE |
| Conservation | Single complete unchanged pack | 48 passed in one execution | Represented-input arithmetic and stress limits above | PASS_WITH_EVIDENCE |
| M1C | Existing capability, realization0.2/model0.1 |124 parent tests passed | Applicability/validation unknown; no M1D claim | PASS_WITH_EVIDENCE |
| M1A/M1B Integration | Lineage/weighted transfer, both tampering calls traced |124 parent + targeted controls passed | No irreversible poison guarantee | PASS_WITH_EVIDENCE |
| Discovery Registry | Complete20 census and exact approved pin |3 selected discovery tests passed | Inventory not scientific validity; reader defect separate | PASS_WITH_EVIDENCE |
| Gate Contracts | Checker preserved, no false prerequisite PASS |29 targeted;279 regression passed | Governance evidence never scientific evidence | PASS_WITH_EVIDENCE |
| Bounded Regression | Existing fixed selection |279 passed | No full-suite qualification | PASS_WITH_EVIDENCE |
| Compatibility requested pack | Snapshot/sampled serialization/layers/freeze/imports |153 passed,1 symlink skip | Skip uncovered; no universal instance-readback claim | PASS_WITH_EVIDENCE |
| Frozen current-model archive compatibility | Direct+registry current/2 refusal | Diagnostic reproduces failure | Scientific impact UNCLASSIFIED; dependent claims blocked | FAIL_WITH_EVIDENCE |
| Owner-review readiness | Exact approved applied diff, source-bound bounded evidence | Results above | Review must retain archive defect and platform limits | PASS_WITH_EVIDENCE |
| OD-3 Readiness | Final certification source/evidence absent | OD-3 NOT RUN | Archive-dependent scope and certification decisions; Linux3.11/3.12 absent | BLOCKED_BY_OWNER |
| Genesis-lite Step0 Readiness | Static existing-baseline nondependency only | No formal measurement/isolation qualification here | Step0 exit/isolation record not established; dependent archive claims blocked | UNVERIFIED |
| Merge Readiness | Bounded checks only; uncommitted/uncertified | Normal full tiers/OD-3 NOT RUN | Integration/certification/archive disposition and owner authorization remain | BLOCKED_BY_OWNER |
| Phase3.5 Closure | Broader owner/program gates untouched | Not established by bounded verification | Passing pack cannot promote maturity | UNVERIFIED |

Existing Genesis preparation remains within its current scope. Formal freeze/measurement requires the documented Step0 exit: PASS, or complete six-question GOVERNANCE_ONLY isolation records preserving red evidence and labelling outputs uncertified. SCIENTIFIC_CORRECTNESS/UNCLASSIFIED issues remain blocking for dependent claims. This report neither declares the archive issue globally governance-only nor imposes a blanket dependency on unrelated synthetic baseline paths. It grants no new capability, benchmark architecture or scientific authority.

**Answer:** The source is verified within the explicitly bounded numerical/software integration scope, subject to the listed coverage limits; it is not certified or universally archive-compatible. The known frozen-model current-record compatibility defect remains unresolved for dependent claims. Final certification additionally lacks separately authorized clean-source supported-platform assurance/OD-3. Genesis formal measurement lacks an established Step0 exit and qualification of its exact intended scope; static nondependency is not readiness evidence.
