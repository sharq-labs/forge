# Final Owner Dispositions — 2026-10-18

**D1/D2/D3 EXPLICITLY OWNER-APPROVED AND EXACT PATCHES APPLIED. Final integration authorized; execution results remain separate.**

The owner subsequently approved these exact three scopes and authorized final bounded integration. The reviewed patch SHA256 and preimages matched, git apply --check succeeded, and only the approved patches were applied. A fresh complete census confirmed the same20 identities and sole M1C model addition before D2. Application evidence is in .pytest-review-temp/final-integration-approved-2026-10-18/application.json and the final integration manifest. Archive behavior remains unapproved for change. The analysis below preserves its original evidence limits; execution results must be read from the subsequent integration report.

## Source and evidence boundaries

Worktree `D:/forge-main-337519d1`; branch `fix/post-merge-remediation-2026-10-18`; HEAD `93ed64b0292e9fea714ac83affb64b71488ac050` plus existing uncommitted P0 changes. Production/test/policy/ledger/certification bytes are preserved. Exact proposed patches have current preimage SHA256 and applicability-check results in [analysis evidence](evidence/final_owner_disposition_analysis_2026_10_18.json). `git apply --check` checks applicability only; it applies no patch and executes no test.

Existing reports: [P0 closure](P0_SCIENTIFIC_CORRECTNESS_CLOSURE.md), [original verification](POST_MERGE_REMEDIATION_VERIFICATION.md), [blocked final preflight](FINAL_SCIENTIFIC_INTEGRATION_VERIFICATION.md). Their test outcomes remain historical to their recorded bytes/environments. Main author performed the narrowly scoped read-only census/registry probe below; independent reviewers performed static inspection only.

## Decision table

| Decision | Evidence | Recommended exact change | Scientific risk | Compatibility impact | Owner approval needed |
| --- | --- | --- | --- | --- | --- |
| D1 Gate dependency contract | Program contract and checker agree; general-policy sentence and test diagnostic conflict | FINAL_D1_GATE_CONTRACT.patch: branch diagnostic by status, retain3 statuses; add downstream PASS/FAIL control after failed M1; clarify policy clause | Low if checker and evidence/maturity requirements stay unchanged; BLOCKED never grants PASS | Test node name/count changes and policy clarification only; no runtime/schema/ledger change | APPROVED; APPLIED |
| D2 OD-31 census | Complete current20; historical19; only added M1C physical model@0.1.0; no collisions/import loss | FINAL_D2_OD31_MODEL_CENSUS.patch: EXPECTED_MODELS19→20 and explanatory comment only | Census is coverage, not model validity or certification; reader limitation below stays visible | Changes certificate-pinned test harness; no model/realization identity change | APPROVED; APPLIED |
| D3 M1A tampered lineage | Exact existing trace refuses changed issuance key before narrower regex; second control unreached | FINAL_D3_M1A_LINEAGE_REFUSAL.patch: add only anchored registry-key integrity message to both existing regexes | Retain refusal type and both calls; no generic refusal acceptance or integrity-guard reorder | Test expectation only; production diagnostics/records unchanged | APPROVED; APPLIED |

## D1 — Gate dependency contract

### Root cause and authority

`docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md:25–30` explicitly distinguishes decisions: PASS and FAIL require each prerequisite PASS; BLOCKED_WITH_EVIDENCE requires each prerequisite decided (PASS, FAIL or BLOCKED_WITH_EVIDENCE), plus repository evidence and next action. `tools/capability_maturity.py:185–200` implements this distinction. DEFERRED/MISSING are not decided prerequisites. Dependencies order decisions, not implementation work.

`docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md:61` over-broadly says a gate can be decided only after prerequisites passed; its own line64 explicitly permits BLOCKED after prerequisites are decided. The program-specific explicit contract, policy line64, implementation and positive test at `tests/test_capability_completion.py:188–203` agree. The older migration proposal is historical design evidence, not authority to replace the current explicit contract.

The failing parameter at `tests/test_capability_completion.py:169–174` constructs E3 BLOCKED while M1 is MISSING. The checker correctly rejects it with `needs 'M1' decided first`; the test wrongly demands `PASS first`. The proposed change does not allow that blocked decision: the missing predecessor remains rejected.

### Executed evidence already available

P0 `bounded-regression-post-numerical`: exit1,277 passed/1 failed,13.86s pytest /14.943s wall. Exact failure: `tests/test_capability_completion.py::test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes[BLOCKED_WITH_EVIDENCE]`. Complete command, env/source/log hash are in P0 machine evidence. No new gate tests were run in this analysis. The positive failed-M1→blocked-M2 case and negative failed-M1→FAIL-M2 case already exist; the proposal additionally covers downstream PASS explicitly.

### Exact proposed change, impacts and review

```diff
--- a/tests/test_capability_completion.py
+++ b/tests/test_capability_completion.py
@@ -167,11 +167,12 @@
 
 
 @pytest.mark.parametrize("status", ["PASS", "FAIL", "BLOCKED_WITH_EVIDENCE"])
-def test_a_gate_cannot_be_decided_before_the_gate_it_requires_passes(status) -> None:
+def test_a_gate_cannot_be_decided_before_its_required_gate_is_ready(status) -> None:
     def decide_e3(d):
         e3 = next(g for g in _program(d)["gates"] if g["id"] == "E3")
         e3.update(status=status, evidence=["docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md"])
-    assert any("needs 'M1' PASS first" in e for e in _with(decide_e3))
+    required_state = "decided" if status == "BLOCKED_WITH_EVIDENCE" else "PASS"
+    assert any(f"needs 'M1' {required_state} first" in e for e in _with(decide_e3))
 
 
 def test_a_deferred_gate_may_wait_on_an_open_requirement() -> None:
@@ -185,7 +186,8 @@
     assert any("the owner names the next epic" in e for e in _with(decide_all))
 
 
-def test_every_decided_gate_needs_evidence_and_blocked_follows_a_failed_requirement() -> None:
+@pytest.mark.parametrize("downstream_status", ["PASS", "FAIL"])
+def test_every_decided_gate_needs_evidence_and_blocked_follows_a_failed_requirement(downstream_status) -> None:
     blocked_without_evidence = _with(lambda d: _program(d)["gates"][0].update(status="BLOCKED_WITH_EVIDENCE"))
     assert any("BLOCKED_WITH_EVIDENCE requires evidence" in e for e in blocked_without_evidence)
     evidence = ["docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md"]
@@ -199,7 +201,7 @@
     def m1_failed_m2_failed(d):
         gates = {g["id"]: g for g in _program(d)["gates"]}
         gates["M1"].update(status="FAIL", evidence=evidence)
-        gates["M2"].update(status="FAIL", evidence=evidence)
+        gates["M2"].update(status=downstream_status, evidence=evidence)
     assert any("needs 'M1' PASS first" in e for e in _with(m1_failed_m2_failed))
 
 
--- a/docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md
+++ b/docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md
@@ -58,8 +58,8 @@
 
 The ledger's `active_epic` may name a capability (maturity stages, 19 gates) or a research program
 (`research_programs`). A research program has **gates, not maturity stages** (`PASS`, `FAIL`, `MISSING`,
-`BLOCKED_WITH_EVIDENCE`, `DEFERRED_BY_OWNER`); a gate is decided only after every gate it requires passed; PASS and
-FAIL need existing evidence; a program carries no maturity vocabulary. Gate dependencies order DECISIONS only:
+`BLOCKED_WITH_EVIDENCE`, `DEFERRED_BY_OWNER`); PASS and FAIL may be decided only after every required gate passed;
+every decided gate needs existing evidence; a program carries no maturity vocabulary. Gate dependencies order DECISIONS only:
 any work inside a program's scope may be built at any time, before any gate (including a validation gate) is run.
 Every decided gate cites existing evidence; BLOCKED_WITH_EVIDENCE is allowed once the gates it requires are decided.
 A program contract may carry acceptance requirements that bind every gate (for `engrt.numerical_foundations`: the
```

No checker branch, decided set, evidence validation, next action, public schema, active epic, ledger status, maturity computation or scientific verdict changes. Neither BLOCKED nor governance policy becomes scientific evidence. PASS and FAIL still require prerequisite PASS; blocked chains cannot promote capability maturity. New negative coverage changes one existing test into two parameter cases and renames the erroneous diagnostic-test node.

No literal direct pin for these proposed files was found in `current_core_v2.json`; this is not a dependency-closure exemption or recertification result. Normal final-source classification/integration and later authorized certification still apply to the existing trust-sensitive tree. No certificate edit is proposed.

Independent `p0_authority` finding: MAJOR contract/test inconsistency for this preflight, no reason to alter checker semantics. Final exact-patch and approval-boundary review found no remaining scientific-authority defect in the proposal (static PASS); no application or passing-test claim follows. Recommended exactly the status-specific diagnostic, scoped policy clarification and explicit failed-prerequisite→PASS/FAIL controls. Static review, no tests.

**Owner approval question D1:** Approve applying only `FINAL_D1_GATE_CONTRACT.patch`, preserving the existing checker and all PASS/FAIL, evidence, next-action, maturity and ledger semantics, while correcting the status-specific diagnostic, clarifying the policy sentence and adding explicit downstream PASS/FAIL refusal coverage after failed M1? **Answer: APPROVED by owner in the subsequent D1/D2/D3 authorization; exact patch APPLIED.**

## D2 — OD-31 discovery census

### Root cause, historical comparison and authoritative contract

`tests/test_core_guards.py:154–182` walks imported engcore modules, collecting unique ScientificModelDefinition `(model_id,version)` keys. Lines190–199 require an exact census rather than a floor. Lines529–546 additionally require a complete import population, unchanged domains and exact condition/reservation counts. It does not count realization versions, solver providers or capability identifiers.

Historical pin provenance: commit `89b9e7c3` explicitly moves the model count to19 for steady_variable_conductivity. Git/AST inspection of that exact snapshot enumerates19 module model declarations. Current imported records enumerate20. Set difference is exactly `thermal.conduction1d.transient_piecewise_linear@0.1.0`, with no removed key. Independent reviewer also inspected `337519d1` and `93ed64b0`, where this model is already declared. The committed M1C module's invalid realization prevented complete import; correcting that declaration restored visibility of its model. The physical model addition explains19→20. The realization version0.2.0 itself adds no model and cannot justify counting a second realization as a new model.

### Actual20 versus historical19 inventory

All rows marked existing occur in the historical snapshot. Object-count and serialized-alias consistency were checked across loaded engcore module attributes, independently of the walk's setdefault deduplication.

| Model key | Historical19 | Current20 |
| --- | --- | --- |
| `battery.cell.constant_current_runtime@0.1.0` | existing | present;1 object,1 serialized digest |
| `battery.cell.coulomb_counting@0.1.0` | existing | present;1 object,1 serialized digest |
| `battery.cell.peukert_capacity_derating@0.1.0` | existing | present;1 object,1 serialized digest |
| `battery.cell.rint_ocv@0.1.0` | existing | present;1 object,1 serialized digest |
| `battery.cell.thevenin_1rc@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.dc.ideal_current_source@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.dc.ideal_voltage_source@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.dc.kcl@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.dc.regulated_voltage_source@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.dc.resistor_ohm@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.dc.self_heated_resistor@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.material.linear_tcr_resistance@0.1.0` | existing | present;1 object,1 serialized digest |
| `electrical.material.rated_linear_tcr_resistance@0.1.0` | existing | present;1 object,1 serialized digest |
| `kinetics.cstr.nonisothermal_first_order@0.1.0` | existing | present;1 object,1 serialized digest |
| `kinetics.cstr.nonisothermal_first_order_constant_rate@0.1.0` | existing | present;1 object,1 serialized digest |
| `thermal.conduction1d.linear_diffusion@0.1.0` | existing | present;1 object,1 serialized digest |
| `thermal.conduction1d.steady_variable_conductivity@0.1.0` | existing | present;1 object,1 serialized digest |
| `thermal.conduction1d.transient_piecewise_linear@0.1.0` | absent — sole addition | present;1 object,1 serialized digest |
| `thermal.lumped.first_order_capacity@0.1.0` | existing | present;1 object,1 serialized digest |
| `thermal.nafems_t3.transient_heat_1d@1.0.0` | existing | present;1 object,1 serialized digest |

### Narrowly executed census and registry evidence

The read-only probe imports the existing discovery module but calls no pytest test function. It uses the existing project venv with process-local `platform._wmi=None`, whose need was independently established by the preserved P0 probes; no new WMI qualification or shared environment change is claimed. Python3.14.2, NumPy2.5.2, SciPy1.18.1, Pint0.25.3, pytest9.1.1, MCP2.1.1; engcore resolves to the D: worktree. Controlled BLAS threads1 and PYTHONDONTWRITEBYTECODE are recorded with exact command/logs in analysis evidence. This is not numerical or physical validation.

Completed diagnostic probe: exit0,5.858s wall.20 models; no model import failures or optional absences. Exactly one object and one serialized model digest per key across module aliases: no hidden conflicting duplicate model definition found in this population. ModelRegistry construction succeeds and every get(id,version) returns the original record.17 unique realization records construct a RealizationRegistry; their provided capabilities are nonempty, model references resolve into these20 models, and repeated aliases have consistent serialized records. Not every physical model must have exactly one realization; no extra realization is invented to balance counts.

M1C realizes `thermal.conduction1d.transient_piecewise_linear@0.1.0` as `...vertex_fv_be@0.2.0`, providing the existing `thermal:transient_conduction_1d` from `conduction1d_schemes.py:142`. That capability is already used by implicit/explicit diffusion realizations. The declared quasi-1D linear phase-constant FV/backward-Euler equations match its semantics; its sourced applicability remains UNKNOWN and validation remains UNVALIDATED. No capability validity or physical truth is inferred from discovery.

Other current counters:16 reserving models,96 validity context names,63 derived reserved names. These match their unchanged pins. Existing targeted discovery execution had2 passed/1 failed/273 deselected; only19-versus20 was red. Prior solver discovery passed; the11-solver pin is unchanged and no new solver test ran here.

**Preserved negative readback observation:** the first diagnostic attempt exited1 in4.107s because full ModelRegistry.from_dict(to_dict()) refuses `thermal.conduction1d.linear_diffusion@0.1.0` with InvalidScientificProblem: no declared exclusions. The completed diagnostic captures rather than hides this outcome; individual readers accept19 other models, including M1C. Registry-wide roundtrip is therefore NOT PASS.

Root of that separate limitation: `domains/__init__.py:83–99` grants the byte-pinned thermal T1 source a module-scoped undeclared-exclusions exemption; `scientific/models/definition.py:2057–2084,2160–2174` resolves that construction context. Serialization writes null exclusions; `from_dict` at2449–2480 deliberately reconstructs NOT_DECLARED and refuses when called outside that exempt module. The reader does not grant the source exemption to a portable payload. This is fail-closed; no missing exclusions became an empty claim. The old guard docstring at3597–3604 still describes broader archive readability and disagrees with the reader's explicit refusal. Preserve this compatibility/contract observation for separate review; do not claim unrestricted registry roundtrip, change frozen source, add exemptions, or repair the reader in this count proposal. It does not change the independently established census20 or justify a different pin.

### Exact proposed pin correction, impacts and review

```diff
--- a/tests/test_core_guards.py
+++ b/tests/test_core_guards.py
@@ -196,7 +196,7 @@
 #: directions and has to be updated deliberately, which is the moment somebody
 #: looks at the new record. `tests/test_pin_portability.py:_pinned_paths` is
 #: the pattern: derive the population, then assert its size.
-EXPECTED_MODELS = 19  # 19: thermal.conduction1d.steady_variable_conductivity (2026-10-17)
+EXPECTED_MODELS = 20  # 20: thermal.conduction1d.transient_piecewise_linear (M1C, 2026-10-18)
 EXPECTED_RESERVING_MODELS = 16  # 16: battery.cell.thevenin_1rc
 # 64 -> 67 and 46 -> 49 in the capability-boundary round, which added one
 # condition to each of three records: linear_resistance_ratio on the
```

No change to16/96/63/11, model/realization definitions, scientific thresholds, validity, exclusions, optional-import rules, uniqueness guards or registry semantics. The20 pin is justified for exact population coverage only. It neither repairs nor certifies the separate registry-reader limitation.

Compatibility: test-harness population expectation changes, not public runtime identity or serialization. Certification impact is direct: `tools/certification/core_certificate.py:521` includes `tests/test_core_guards.py` in the pinned harness and `certification/current_core_v2.json:11282` records its older hash. Updating this test moves harness identity, so existing certificate cannot attest the final changed source. Do not regenerate that manifest or any old bundle; later final-source OD-3 remains separately authorized.

Independent `closure_review`: static/history review independently established historical19/current declarations20, sole added M1C physical model and unchanged other19 definition sources; warned correctly that setdefault needs independent collision checks. Current probe meets the population/alias-consistency conditions. Final exact-patch/census review found no blocking discrepancy in the count proposal. Readback limitation is retained as an OBSERVATION requiring separate compatibility/contract review, with unsuccessful roundtrip evidence, not swept into a registry-compatibility PASS. The reader source is unchanged from the historical19 snapshot. No reviewer ran tests.

**Owner approval question D2:** Approve applying only `FINAL_D2_OD31_MODEL_CENSUS.patch` to record20 rather than19 scientifically defined model keys, accepting the documented future harness-certification impact, with all other pins, identities, frozen artifacts and registry-reader limitations preserved? **Answer: APPROVED by owner in the subsequent D1/D2/D3 authorization; exact patch APPLIED.**

## D3 — M1A tampered-lineage refusal

### Root cause and contract trace

The issuance contract binds issued object identity and a content snapshot. `LineageCell1D.cell_id/record_id` in `numerical/mesh_adaptation.py:246–252` includes parent_id; Bisection1D and nested mesh/change IDs incorporate that child content. `_IssuedRecords.verify():221–225` requires recomputed record_id to equal the issuance-registry key before checking the stored object/snapshot in require(). A changed parent_id therefore changes these derived IDs; it is not an unchanged record with an alternate label.

The test at `tests/test_m1a_mesh_lineage.py:167–176` deliberately uses object.__setattr__ to mutate an issued child's parent_id. transfer_state→`interval_transfer.py:217`→_guard:132→`mesh_adaptation.py:362`→_IssuedRecords.verify:224 raises `conflicting issued mesh registry key`. This is the earliest correct integrity refusal, before the narrower `unissued, substituted or tampered mesh record` branch. coarsen also starts with the same _guard (`interval_transfer.py:210–212`). Moving the guard or weakening issuance to obtain the old message would be wrong.

The old regex is incomplete for this current guard order. Production behavior is fail-closed; the first test failure is diagnostic matching, not successful transfer of tampered data. The retained corrupted lineage keeps refusing; there is no separate irreversible poison flag. This test does not establish protection after an attacker restores the original bytes.

### Executed evidence already available

P0 parent integration `m1c-and-parent-integration-final`: exit1,123 passed/1 failed,121.56s pytest /122.201s wall (exact command/environment/log hash in P0 machine evidence). Full trace proves the first transfer raises the exact integrity exception and regex matching fails. The second coarsen assertion is consequently NOT RUN within that failed test. No downstream success is inferred. No new M1A tests were executed in this analysis.

### Exact proposed assertion and impacts

```diff
--- a/tests/test_m1a_mesh_lineage.py
+++ b/tests/test_m1a_mesh_lineage.py
@@ -170,9 +170,9 @@
     original = state(runtime)
     split = refine(runtime)
     object.__setattr__(split.change.bisections[0].children[0], "parent_id", "forged")
-    with pytest.raises(NumericalRefusal, match="tampered|unissued"):
+    with pytest.raises(NumericalRefusal, match=r"tampered|unissued|^conflicting issued mesh registry key$"):
         runtime.transfer_state(original, split)
-    with pytest.raises(NumericalRefusal, match="tampered|unissued"):
+    with pytest.raises(NumericalRefusal, match=r"tampered|unissued|^conflicting issued mesh registry key$"):
         runtime.coarsen(split.change.bisections, max_ratio=10)
 
 
```

This retains both old integrity diagnostics and adds only the exact anchored registry-key message, preserving NumericalRefusal type, deliberate mutation, transfer call and subsequent coarsen call. Generic `conflicting`, arbitrary NumericalRefusal, skip/xfail and removed controls are not proposed. The future targeted test must execute both calls without escaping their raises contexts; the complete M1A and parent packs must then run to credit later controls. This proposal alone proves neither execution nor passing outcomes. The contract still refuses missing ancestry, foreign/substituted objects, illegal geometry, stale states and unknown issuance; those surrounding tests are not altered.

No production API/schema/ID/message/guard-order change. Static search found no literal direct pin for this test in current_core_v2.json; that does not prove a complete certified dependency exemption. Normal classification/integration remains required; no certificate/bundle regeneration is proposed.

Independent `p0_conservation`: read-only full guard trace and actual failure log agree; no production integrity defect found in this path. Recommended adding the anchored message to BOTH regexes, preserving all negative controls, and explicitly withholding credit for coarsen until execution. OBSERVATION: no irreversible poison-flag claim. Final exact-patch/document review found no BLOCKER or MAJOR. No reviewer tests/edits.

**Owner approval question D3:** Approve applying only `FINAL_D3_M1A_LINEAGE_REFUSAL.patch`, adding the exact anchored issuance-key conflict alternative to both existing integrity-refusal assertions while retaining every negative-control operation and all production behavior? **Answer: APPROVED by owner in the subsequent D1/D2/D3 authorization; exact patch APPLIED.**

## Approval and next-step boundary

D1/D2/D3 are explicitly approved and their exact reviewed patches are applied. Final Scientific Integration Verification is also explicitly authorized in this owner turn; Phase0 checks actual source hashes and prerequisites rather than relying on document existence. No approval is inferred from unrelated decisions. Prior analysis and its pending state are preserved in the pre-application snapshot.

Archive behavior, scientific model/realization identities, physical thresholds, ledger/maturity and certification manifests are unchanged by D1/D2/D3. No commit, push, merge, PR, rebase, historical bundle regeneration, OD-3 or full assurance is authorized. All final tests and readiness claims require their own executed evidence. The separate archive-readback investigation is read-only; unresolved scientific impact remains UNCLASSIFIED and blocks dependent claims.
