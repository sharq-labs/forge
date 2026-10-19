# Frozen-model archive-readback investigation — 2026-10-18

**Read-only investigation. Archive behavior unchanged. Scientific impact remains UNCLASSIFIED and blocking for dependent archive/reconstruction claims.**

This is the separately authorized investigation accompanying D1/D2/D3 integration. It does not approve an archive repair, re-freeze records, infer exclusions or regenerate historical evidence. The known compatibility failure is distinct from the approved census correction. No false scientific support was demonstrated; the failing reader refuses before it can grant standing.

## Exact reproduction and identity

Shipped model: `thermal.conduction1d.linear_diffusion@0.1.0`, constructed as DIFFUSION_MODEL in `src/engcore/domains/thermal/conduction1d/problem.py:93`. The physical model identity is unchanged. Its current `scientific_model_definition/2` payload contains `exclusions: null`. Both direct `ScientificModelDefinition.from_dict(DIFFUSION_MODEL.to_dict())` and a one-model `ModelRegistry.from_dict(ModelRegistry((DIFFUSION_MODEL,)).to_dict())` refuse with InvalidScientificProblem: model declares no exclusions. The model's source assumptions do not become a portable exclusions declaration automatically.

Positive diagnostic control uses M1C `thermal.conduction1d.transient_piecewise_linear@0.1.0`, whose explicit exclusions allow both direct and registry readback. This does not establish portability of the frozen model or every other scientific record.

Command: `C:/Users/dev_kaeem/Downloads/Compressed/phyx/.venv/Scripts/python.exe -B D:/forge-main-337519d1/.pytest-review-temp/final-integration-approved-2026-10-18/archive_readback_probe.py`. Exit0; 1.346s wall; source indexes unchanged=True. Exit0 means the diagnostic captured both outcomes, NOT a compatibility PASS. Exact Python/environment/source/log hashes are in the [integration manifest](evidence/final_scientific_integration_approved_2026_10_18.json). Complete [probe](evidence/final_integration_approved_2026_10_18/archive_readback_probe.py) and [log](evidence/final_integration_approved_2026_10_18/archive-readback-investigation.log) are preserved.

## Governing contracts and root cause

1. `docs/CORE_FREEZE_POLICY.md:160–172` describes61 frozen current-format roundtrippable records and exact supported legacy schema versions. `tests/test_core_api_serialization.py:8–12` states byte-identical current-format roundtrip. ScientificModelDefinition belongs to the roundtrippable family; selected sample coverage is not proof of every instance.
2. `tests/test_model0r_realization_foundation.py:935–943,1000–1017` explicitly accepts the cost of refusing legacy `/1` records predating exclusions. That legacy omission refusal is intentional and has a concrete negative fixture. It is not sufficient explanation for a shipped current `/2` object's readback failure.
3. `src/engcore/domains/__init__.py:83–99` gives the original frozen thermal constructing module an undeclared-exclusions exemption because its source is pinned. `models/definition.py:2057–2084,2160–2174` discovers that exemption from caller-module context, not from verified portable provenance.
4. `models/definition.py:2423–2441` writes null for NOT_DECLARED; `:2449–2480` maps null/missing back to NOT_DECLARED and calls the same constructor. Ordinary reader callers lack the original module's exemption and are refused.
5. The class's broad archive-readability prose at `definition.py:2110–2123` and guard prose at `tests/test_core_guards.py:3594–3604` conflict with actual admission behavior. These are documentation/contract inconsistencies alongside a current-format compatibility defect. The implementation is fail-closed and preserves missing-as-unknown; that does not make the roundtrip promise satisfied.

Reader source and the19 historic model-definition source files were unchanged between the historical19 snapshot `89b9e7c3` and this remediation. The refusal predates D1/D2/D3. The full20-model registry diagnostic already failed on this frozen object; other19 individual model readers succeeded. No historical runtime/certificate is claimed newly verified by that source comparison.

## Impact and applicability

| Area | Established impact | Limit / status |
| --- | --- | --- |
| Portable model/registry reconstruction | This current object, or a registry containing it, cannot read its own exported payload through ordinary readers | FAIL_WITH_EVIDENCE; scientific impact UNCLASSIFIED, dependent claims blocked |
| Provenance and scientific identity | Source object/key and exported content remain available; no substitute identity or inferred exclusions granted | No proof of successful archival reconstruction; preserve provenance rather than editing old artifacts |
| Scientific authority | Reader refuses before returning the incomplete record; no false SUPPORTED demonstrated | Do not weaken admission or globally classify GOVERNANCE_ONLY |
| Replay paths that decode this model | Reconstruction prerequisite fails | Block any exact replay/compatibility claim that depends on this reader |
| Existing claims replay | CapabilityRegistry and assessment reconstruction, not this ModelRegistry decoder | Inspected static path plus final claims tests apply to that scope only; no universal archive independence claim |
| Existing certification registry source probe | Imports declaration objects and hashes source modules | No call to model-definition decoder identified in that exact path; full assurance/OD-3 NOT RUN |
| Existing Genesis-lite baseline | Synthetic Blindfold universe/proposal/escrow/evaluator records | No decoder identified in this baseline path; static nondependency only, not arbitrary plugins or formal Step0 qualification |

## Concrete certification/replay dependency tracing

- `tools/certification/core_certificate.py:1450–1490` registry source probe imports domain declarations and hashes their source; it does not deserialize the model records. No blanket conclusion about every future assurance consumer follows.
- `tools/certification/local_assurance.py:477–501` uses the normal FAST population, which includes existing compatibility controls; FAST/full assurance were not run by this investigation.
- `tests/test_core_guards.py:632–641` round-trips RESERVING models only. Frozen diffusion has no derived/reserving names (`domains/thermal/conduction1d/problem.py:138–160`), so that passing population omits this object. Aggregate compatibility can pass while this specific readback still fails.
- `scientific/ir/problem.py:521–523` decodes a ModelReference rather than an embedded ScientificModelDefinition. `scientific/replay_core/bundle.py:55–59` decodes ArtifactIdentity and RuntimeEnvironment. These reader names do not establish use of the failing decoder.
- `claims/replay/bundle.py:280–324` reconstructs capability declarations/assessments. Its registry is CapabilityRegistry; sharing the word registry does not make it this failing ModelRegistry path.

## Concrete Genesis-lite baseline dependency tracing

`benchmarks/genesis_lite/harness.py:190–230` run_one/_run → run_campaign at281 → `engcore/blindfold/roles.py:315` → escrow synthetic universe generation (`escrow.py:357`) → stored proposals and separate answer-key evaluator (`harness.py:293–310`). The inspected baseline uses Blindfold expressions, synthetic universes and escrow records. No model-definition/ModelRegistry decoding was identified there. This is a static nondependency argument for those existing baseline paths; no Genesis run, arm/plugin qualification, isolation proof, preregistration freeze or formal measurement was executed here.

An unrelated archive failure is not a basis to assert every independent benchmark is scientifically dependent on it. Conversely, absence of that call in the inspected baseline does not grant Step0 PASS, certify same-account isolation or qualify future scientific arms. Exact intended inputs and benchmark identities must remain bound when Step0 is decided.

## Independent findings and disposition

Independent read-only `closure_review` classified this as a pre-existing current-record compatibility defect with unresolved dependent impact. Explicit `/1` refusal is intentional; current `/2` roundtrip failure and broad readability promises are a separate contract inconsistency. The reviewer traced the certification, claims and Genesis paths above and found no evidence that the existing synthetic baseline invokes this reader. No edits/imports/tests were executed by that reviewer.

**Finding: MAJOR for dependent current-format archive/readback compatibility. Scientific impact: UNCLASSIFIED; dependent claims BLOCKED.** This is not globally GOVERNANCE_ONLY and is not evidence of false scientific support. It remains unresolved; no blanket compatibility or certification PASS follows from aggregate tests.

Owner decision required before repair: define the supported portable contract for source-exempt records carrying unknown exclusions. Any proposal must preserve missing information honestly and cannot invent exclusions, silently copy source-module privilege to arbitrary payloads, weaken validation/admission, edit byte-pinned source or rewrite old bundles. A new version/deprecation/explicit readable-but-not-admissible design would require its own scientific and compatibility review; none is selected or implemented here.

The authorized D1/D2/D3 and independent bounded verification may be reported within their tested scope. This known readback issue remains an explicit limitation and blocker for dependent claims. A newly discovered authority-granting defect would require stopping the affected work rather than changing its contract; none was established by this investigation.
