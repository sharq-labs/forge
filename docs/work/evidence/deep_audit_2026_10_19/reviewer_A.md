# Reviewer A: Scientific Authority, Replay, Evidence, Provenance

Target: `D:/forge-main-337519d1`, HEAD `abed661f0d551f352e7a2c451d0df7fcc22bde5c`. Read-only. I ran no FORGE code, no
pytest and no Python against the repo. I used only Read/Grep and read-only `git`/`grep`/`sed` through Bash. None of
the findings below is EXECUTED_REPRODUCED.

Path I traced: `claims/assessment.py` (assess_claim, _build_record, verify_assessment) -> `claims/planning.py`
(run_id derivation) -> `claims/execution.py` (execute_plan, binding_problems) -> `credibility/sria_bridge.py` ->
`claims/verdict.py` -> `claims/revalidation.py` -> `claims/replay/bundle.py` (verify_bundle, replay_bundle,
_compare_replay_nodes, _has_bound_replay_result). Side branches: `claims/uq_studies.py`, `numerical_uq.py`,
`parameter_uq.py`, `governance/policy.py`, `context.py`, `sources.py`, `multiplicity.py`, `credibility/evidence.py`
(derive_verdict, attained_levels_of), the duplicate replay paths in `assembly/replay.py`, `assembly/replay_catalog.py`,
`assembly/certification.py`, `system_runtime/replay.py`, `scientific/replay_core/*`, `sria/decision/replay.py`, and
`providers/records.py` / `compare.py`.

All cited files are listed in `certification/current_core_v2.json`, so every repair below is certified-area work and
needs OD-3-style recertification.

---

## A-01: Replay can never return VERIFIED for a grounded or policy-bound claim record

- **new_or_known:** NEW. Nothing in the known lists or `docs/work` covers it, and no test replays a grounded bundle.
  I grepped `tests/claims/test_nl_*` and `tests/mcp/test_caller_authored_criteria.py` for replay calls and found none.
- **1 ID:** A-01
- **2 Category:** replay / authority-path inconsistency (fails closed).
- **3 Exact file:line:**
  - `src/engcore/claims/replay/bundle.py:742-749`: `replay_bundle` calls `assess_claim(record["claim"], registry,
    external=..., empirical_observations=..., model_form_qualification=..., trust=trust)` and passes no
    `criteria_authority`.
  - `src/engcore/claims/assessment.py:616`: the record's block is
    `criteria_authority or CALLER_AUTHORED_CRITERIA`.
  - `src/engcore/product/runtime.py:325` is the production path. It builds records with
    `criteria_authority=grounded_criteria(...)`.
  - `src/engcore/claims/replay/bundle.py:557-564` reports missing and unexpected keys as differences.
- **4 Governing contract:** the `replay_bundle` docstring (`bundle.py:691-698`) says the inputs the record was built
  from "are reconstructed from the study records and supplied to the fresh assessment rather than silently
  disappearing during replay". The module docstring says VERIFIED is "the only status that is publishable support".
  `assessment.py:645-647` tells callers to use `prepare_simulation` / `run_proposed_simulation` "to have criteria
  grounded".
- **5 Invariant violated:** none of the CLAUDE.md rules is weakened, because this fails closed. The violated property
  is availability of the replay contract. A record from the recommended product path can never earn the only
  publishable status.
- **6 Root cause:** the criteria-authority block is an input to `_build_record`, the same as the empirical
  observations and the qualification. Replay reconstructs those two (`_study_replay_inputs`) but drops this one.
- **7 Minimal triggering conditions:** any assessment made with `criteria_authority` set to `grounded` or
  `policy_bound`, bundled with `make_bundle` and replayed with `replay_bundle`.
- **8 Expected vs observed:**
  - Expected: the stored block is re-verified (verify_bundle already re-grounds it, `assessment.py:928`), passed to
    the fresh assessment, and the result is VERIFIED when the physics reproduces.
  - Observed, by trace: the fresh record carries `CALLER_AUTHORED_CRITERIA`. `_compare_replay_nodes` reports
    `/criteria_authority: missing fields [...]`, `unexpected fields [...]` and
    `/criteria_authority/authority: 'grounded' -> 'caller_authored'`. The result is always NOT_REPRODUCIBLE.
- **9 Reasoning:**
  1. `verify_bundle` succeeds, because `_verify_criteria_authority` re-grounds the block.
  2. `replay_bundle` then builds the fresh record with the default block.
  3. The two `criteria_authority` mappings have different key sets, so `differences` is non-empty.
  4. Line 777 therefore returns NOT_REPRODUCIBLE. No branch avoids this.
- **10 Evidence class:** SOURCE_PROVEN.
- **11 Affected:** every claim assessed through `product/runtime.py:prepare/run_proposed` (the NL adapter), and any
  record with `policy_bound` criteria.
- **12 False-support risk:** none, because it fails closed. There is an operational risk: a NOT_REPRODUCIBLE result on
  a genuine grounded record reads as a reproducibility failure of the physics.
- **13 Replay/provenance impact:** replay verification is unusable for the product's grounded records. The
  difference text misattributes the cause.
- **14 Compatibility impact:** none for the fix. Pass the verified block through. No schema change.
- **15 Certification impact:** `claims/replay/bundle.py` is certified (current_core_v2.json:11664), so the fix needs
  recertification.
- **16 Genesis impact:** none.
- **17 Minimal reproduction plan (not executed):**
  1. Use a test that builds a grounded assessment, as `tests/claims/test_nl_criteria_provenance.py` does.
  2. Call `make_bundle(a, registry)`, then `replay_bundle(bundle, registry)`.
  3. Expected: NOT_REPRODUCIBLE, with differences under `/criteria_authority`.
  - Cost is about 1 s. It needs a tmp basetemp and touches no shared state.
- **18 Smallest correct repair:** in `replay_bundle`, pass `criteria_authority=_plain(record["criteria_authority"])`
  to `assess_claim`. `verify_bundle` has already re-grounded it, and `assess_claim` re-verifies it again at
  `assessment.py:794`. Add a test that a grounded bundle replays VERIFIED and that a tampered grounded block is still
  TAMPERED.
- **19 Owner approval:** yes, a certified-file change (OD-3 recertification).
- **20 Self-challenge:** "Replay deliberately judges under caller-authored criteria." This does not survive. The
  verdict does not read `criteria_authority` (`assess_claim` docstring: "It decides nothing in the verdict"), so
  re-supplying it cannot raise support. Dropping it only guarantees a mismatch.

---

## A-02: The meaning of VERIFIED disagrees with its documentation, and ReplayResult carries no verdict

- **new_or_known:** NEW. The known P0 item fixed matching refusals. This item concerns what VERIFIED is documented to
  mean once that fix is in place.
- **1 ID:** A-02
- **2 Category:** contract ambiguity: replay status vs scientific verdict.
- **3 Exact file:line:**
  - `src/engcore/claims/replay/bundle.py:37-38` ("``VERIFIED`` ... is the only status that is publishable support").
  - `bundle.py:646-653`: `ReplayResult` has `status`, `differences` and `compared_numbers`, with no verdict.
  - `bundle.py:656-662` (`_has_bound_replay_result`: "An executed result can still have an insufficient scientific
    verdict").
  - `tests/claims/test_p0_replay_execution_authority.py:51-62` pins VERIFIED for an INSUFFICIENT_EVIDENCE record.
  - `assessment.py:862` and `revalidation.py:51,82` repeat that only replay is "publishable support".
- **4 Governing contract:**
  - `P0_SCIENTIFIC_CORRECTNESS_CLOSURE.md` §2: "Reproducibility does not grant scientific support."
  - The module docstring calls VERIFIED publishable support.
- **5 Invariant violated, at risk via consumers:**
  - "Verification does not become validation."
  - "UNKNOWN never improves an answer." An INSUFFICIENT or CONTRADICTED record carries a `VERIFIED` status whose
    documented meaning is "publishable support".
- **6 Root cause:** reproducibility status and support status share one word ("VERIFIED"). The result object does not
  carry the verdict it reproduced, so a consumer cannot tell "reproduced INSUFFICIENT" from "reproduced SUPPORTED".
- **7 Minimal triggering conditions:** replay any bound record whose verdict is INSUFFICIENT_EVIDENCE or CONTRADICTED.
  The test above already does this.
- **8 Expected vs observed:**
  - Expected: a reproducibility status that does not claim support, or a ReplayResult that carries the reproduced
    verdict.
  - Observed: `ReplayResult(VERIFIED, (), n)` with no verdict, and documentation that VERIFIED is publishable support.
- **9 Reasoning:** `_has_bound_replay_result` deliberately admits insufficient verdicts, and the pinned test confirms
  it. Lines 776-778 return VERIFIED whenever there are no differences. The returned object omits `record["verdict"]`.
- **10 Evidence class:** CONTRACT_AMBIGUITY. The code behaviour is SOURCE_PROVEN; the defect is the contradiction
  between the documentation and the result shape.
- **11 Affected:** every consumer of `replay_bundle`. There are no in-repo runtime consumers, because the module is a
  view by design.
- **12 False-support risk:** low. It needs an external consumer that reads the documented meaning.
- **13 Replay/provenance impact:** a replay attestation reads as support.
- **14 Compatibility impact:** adding `verdict` to `ReplayResult` is additive, but `to_dict` changes shape.
- **15 Certification impact:** certified file.
- **16 Genesis impact:** none.
- **17 Minimal reproduction plan:** the existing test `test_real_bound_insufficient_result_replays_without_becoming_supported`
  already demonstrates it (about 2 s).
- **18 Smallest correct repair:**
  - Change the docstrings to say "VERIFIED = reproduced; publishable only together with the reproduced verdict".
  - Add `verdict: str | None` to `ReplayResult`, taken from the replayed record.
- **19 Owner approval:** yes, certified file and public result shape.
- **20 Self-challenge:** "VERIFIED is clearly reproducibility; nobody reads it as support." The repository's own
  docstrings read it as support in four places, so this does not survive.

---

## A-03: The multiphysics replay gate compares only final scalar magnitudes, so certification passes COMPUTATIONAL_REPLAY_VERIFIED without re-earning UQ, validation, verification or field outputs

- **new_or_known:** NEW consequence. `docs/work/PROGRESS.md:5209` (BR11) notes that `compare_runs` "skips
  underscore-prefixed outputs" and found "No defect". That review considered only `_concurrency` and `_window_control`.
  This item is not in the compact known list.
- **1 ID:** A-03
- **2 Category:** replay compares partial fields; stale or historical evidence keeps its standing.
- **3 Exact file:line:**
  - `src/engcore/assembly/replay.py:531-546` (`_scalar_outputs`):
    - it drops every `_`-prefixed key;
    - it drops every non-Mapping value and every Mapping without a numeric `magnitude` (so every `FieldRecord`,
      `scientific/fields/result.py:305-322`, which has no `magnitude`);
    - it keeps the magnitude and discards `units`.
  - Its docstring claims field and `_` blocks are "still covered by the identity comparisons below". That is false:
    the identity tuple at `:557-571` covers only graph and plan fingerprints, scenario digest, window count and
    `ended_at`.
  - `replay.py:614-638` is the only numeric comparison.
  - `replay.py:688` compares `authorized.run` against `replayed.run`. The fresh `replayed.system_validation`,
    `.system_uncertainty` and `.system_verification` (recomputed at `assembly/multiphysics.py:960-1044`) are never
    compared.
  - `assembly/certification.py:546-566`: the replay gate is satisfied by `replay.certifies(...)`. The UQ, validation
    and verification gates read the original `authorized` record (`certification.py:500-520` and nearby).
- **4 Governing contract:** the `assembly/replay.py` module docstring says replay exists because a roundtrip passes
  "a solver that has since changed its answer". It also says "Replay refuses rather than degrades". `ReplayStatus.
  REPLAYED_MATCH` is documented as "every compared quantity agreed", and the gate is named
  COMPUTATIONAL_REPLAY_VERIFIED.
- **5 Invariant violated:**
  - "Evidence must remain bound to the exact context / decision it was produced for".
  - Stale evidence after an upstream change: the certificate's UQ, validation and verification findings come from
    the stored run, and the replay that re-executed the run never checked them.
- **6 Root cause:** the comparison was designed for scalar coupling outputs. The `_` skip was added to tolerate
  nondeterministic diagnostics, but it is a blanket rule. It also removes `_uncertainty` (per-port output UQ),
  `_edge_uncertainty` and `_coupling_error`, and the authorized-run-level results are not compared at all.
- **7 Minimal triggering conditions:** an `AuthorizedMultiphysicsRun` (fresh, or read through `from_dict`) whose
  re-execution yields:
  - identical final scalar magnitudes (within rel 1e-9), but
  - a different `_uncertainty`, `_edge_uncertainty`, `_coupling_error`, field output, output unit, or
    system_validation / system_uncertainty / system_verification result.

  A typical cause is a code change inside a validation or UQ implementation that does not move the pack authority
  digests. Code identity is not in those digests (BR-15 residual).
- **8 Expected vs observed:**
  - Expected: REPLAYED_MISMATCH, enumerating the differing uncertainty or validation records (or, for nondeterministic
    blocks, an explicit declared exclusion list).
  - Observed, by trace: `differences == ()`, so the status is REPLAYED_MATCH, `certifies()` returns `()`, and the
    COMPUTATIONAL_REPLAY_VERIFIED gate passes. The certificate then records UQ, validation and verification gates
    satisfied from the stored, non-reproduced results.
- **9 Reasoning:**
  1. `compare_runs` builds `differences` only from the five identity labels, the four receipt and termination checks,
     and `_scalar_outputs` keys.
  2. No code path reads `final_outputs["_uncertainty"]`, `FieldRecord.reference.digest` or `replayed.system_*`.
  3. `ReplayEvidence.replayed_run_digest` covers the replayed run's full content, but it is only required to differ
     from the original (`replay.py:233-238`). It is never compared with anything.
  4. Conservation is the exception: `require_conservation` runs in the replayed run's `__post_init__`
     (`multiphysics.py:235-240`). A required-balance failure therefore makes replay REFUSED_UNREPRODUCIBLE, and
     conservation is not part of this finding.
- **10 Evidence class:** SOURCE_PROVEN that these fields are never compared and that the gate passes when only they
  differ. STATIC_SUSPICION on how often production triggers occur. No production composition pack currently emits
  field outputs; scalar-only electrothermal packs are affected through `_uncertainty` and `system_*`.
- **11 Affected:** `system.electrothermal_*` composition packs, `certify_authorized_multiphysics_run`, and the
  `forge.multiphysics.production/2` profile.
- **12 False-support risk:** medium. The gate attests "computational replay verified" over evidence it did not
  reproduce, and the certificate's UQ and validation standing can be historical.
- **13 Replay/provenance impact:** a replay attestation is broader than the comparison behind it, and the docstring
  misstates the coverage.
- **14 Compatibility impact:** the fix changes `comparison_digest` content for runs that gain compared fields, and
  therefore the ReplayEvidence seals of new replays. Historical seals stay valid as records.
- **15 Certification impact:** `assembly/replay.py` (:11781), `assembly/certification.py` (:11778) and
  `assembly/multiphysics.py` (:11780) are certified.
- **16 Genesis impact:** none directly. Multiphysics certification is not on the Genesis Step-0 path.
- **17 Minimal reproduction plan (not executed):**
  1. In a test, take `_authorized("x")` as in `tests/test_scientific_trust_sprint2.py`.
  2. Build `replayed` with `execute_authorized_graph_plan`.
  3. Construct a copy of `replayed.run` whose `final_outputs["_uncertainty"]` is replaced by an UNKNOWN record. Use
     `MultiphysicsRunRecord.from_dict` / `to_dict`, editing only `_uncertainty`.
  4. Call `compare_runs(authorized.run, edited, DEFAULT_REPLAY_POLICY)`.
  5. Expected: `(n, ())`, no differences.
  - Second variant: substitute `replayed.system_validation` with a failing result and observe that `compare_runs`
    never sees it.
  - Cost is about 5-10 s. It writes no shared state.
- **18 Smallest correct repair:**
  - Replace the blanket `_` skip with an explicit allow-list of nondeterministic diagnostic keys (`_concurrency`,
    `_window_control`, `_acceleration` if justified).
  - Compare `_uncertainty`, `_edge_uncertainty` and `_coupling_error` exactly, or under the policy tolerance for
    numeric leaves.
  - Compare FieldRecord `reference.digest`, or field summaries under tolerance.
  - Compare scalar `units` exactly.
  - Compare `replayed.system_validation`, `system_uncertainty` and `system_verification` against the authorized run's,
    as differences.
  - Correct the docstring at `replay.py:532-538`.
- **19 Owner approval:** yes (certified area, seal identity of new replays).
- **20 Self-challenge:** "The UQ and validation are deterministic functions of the scalar outputs, so equal scalars
  imply equal UQ." This does not survive. The producers are separate implementations (`producer.implementation(run)`,
  `protocol.execute(...)`) that read more than the final scalars, such as window histories. The replay exists to
  catch implementations that changed. "The BR11 review already accepted the skip": it accepted it for `_concurrency`
  and `_window_control` only, and never considered `_uncertainty` or `system_*`.

---

## A-04: Golden replay tolerances use absolute unit conversion (the R-48 / I-22 defect is still present in this file)

- **new_or_known:** variant_of the R-48 / I-22 tolerance-as-difference defect, which was fixed in
  `scientific/oracles.py:287-318` and `units/quantity.py:706-731,1257-1282`. What is new: `assembly/replay_catalog.py`
  never received the fix. It is not in the compact known list.
- **1 ID:** A-04
- **2 Category:** units: a spread converted as a point.
- **3 Exact file:line:**
  - `src/engcore/assembly/replay_catalog.py:77-84`: `converted = self.tolerance.to(self.expected.units)`, with only a
    sign check and no `require_spread_unit`.
  - `replay_catalog.py:429-437` compares `error <= tolerance.to(expected.units).magnitude`.
- **4 Governing contract:** the `require_spread_unit` docstring ("A SPREAD -- a tolerance ... needs a scale whose zero
  is zero").
- **5 Invariant violated:** a golden replay with an offset-unit tolerance becomes a meaningless pass or fail, so
  "Verification does not become validation" is at risk through a spurious golden pass.
- **6 Root cause:** the absolute `.to()` is used instead of `magnitude_as_spread_in`, and the unit is never refused.
- **7 Minimal triggering conditions:** a `GoldenReplayOutput` with expected in kelvin and tolerance
  `Quantity(0.5, "degC")`. The tolerance becomes 273.65 K, so any prediction within 273 K passes. The reverse case
  (expected in degC, tolerance in kelvin) becomes negative and is refused, which fails closed.
- **8 Expected vs observed:** expected a refusal of the affine tolerance unit, or a slope conversion. Observed: the
  tolerance is silently inflated by 273.15.
- **9 Reasoning:** `degC -> K` adds 273.15 for a point, so 0.5 degC converts to 273.65 K, which is non-negative and
  accepted. This is the same arithmetic the oracle module documents as the audited failure.
- **10 Evidence class:** SOURCE_PROVEN for the code path. The production consequence is latent: the
  `builtin_golden_replay_catalog` (`:549-631`) states every tolerance in kelvin, ohm or watt.
- **11 Affected:** `assembly/domainpacks.py:381-383` consumes the builtin catalog. Any future catalog is exposed.
- **12 False-support risk:** low today, high if a catalog entry is ever written with a degC tolerance.
- **13 Replay/provenance impact:** golden regression detection.
- **14 Compatibility impact:** none for the builtin catalog.
- **15 Certification impact:** `assembly/replay_catalog.py` is certified (:11782).
- **16 Genesis impact:** none.
- **17 Minimal reproduction plan:** construct `GoldenReplayOutput("t", "k", Quantity(300,"kelvin"), Quantity(0.5,"degC"))`
  and read `.tolerance`. Expected: 273.65 K. Cost is under 1 s and needs no state.
- **18 Smallest correct repair:** call `require_spread_unit(self.tolerance.units)`, then store
  `Quantity(self.tolerance.magnitude_as_spread_in(self.expected.units), self.expected.units)`. Use the same reader at
  `:430-437`.
- **19 Owner approval:** yes (certified file). No behavioural change for the builtin catalog.
- **20 Self-challenge:** "Only builtin entries exist, all in K." True today, so this is MINOR and latent. The
  repository fixed exactly this pattern elsewhere as a scientific defect, and this copy was missed.

---

## A-05: Offline verification does not re-derive the execution view's identity fields

- **new_or_known:** NEW. `tests/claims/test_offline_revalidation.py:128-133` edits only `execution.run_id` together
  with the plan's `run_id`; the plan check catches that combination. No test edits the execution view alone.
- **1 ID:** A-05
- **2 Category:** stored records supply their own provenance fields.
- **3 Exact file:line:**
  - `src/engcore/claims/assessment.py:873-899`: `verify_assessment` reads `view = record["execution"]` and checks
    only `outcome` and `binding_problems`.
  - `assessment.py:518` writes `"execution": dict(execution)` verbatim into the rebuilt record, so the comparison at
    `:931` is tautological for this block.
  - `assessment.py:297-309` turns `view["condition_repairs"]` into `MOVE_INSIDE_VALIDITY` repair actions with
    `source="domain_repair:..."`.
- **4 Governing contract:** the `verify_assessment` docstring: "Read an assessment record back by re-deriving every
  part of it." `_execution_view` (`assessment.py:748-759`) shows that `run_id`, `plan_digest`, `capability_id`,
  `instance` and `report_run_id` are pure functions of the plan and the report.
- **5 Invariant violated:** "Evidence must remain bound to the exact context / decision it was produced for". An
  offline-consistent record can name another run or plan in its execution view. "A proposed corrective action never
  guarantees support" is also affected, because caller text is attributed to `domain_repair:` authority.
- **6 Root cause:** the execution view is treated as data and is not re-derived.
- **7 Minimal triggering conditions:** in a genuine bundle, change `record.execution.run_id`, `plan_digest`,
  `report_run_id` or `capability_id`, or add `condition_repairs` entries. Recompute the unkeyed bundle digest.
- **8 Expected vs observed:**
  - Expected: TAMPERED.
  - Observed, by trace: `verify_bundle` returns the same SCIENTIFICALLY_REVALIDATED or REPLAY_REQUIRED status as the
    genuine record, now naming a different run or plan or carrying injected domain-repair actions.
  - `replay_bundle` still refuses VERIFIED: `_compare_replay_nodes` reports the field difference, and
    `_has_bound_replay_result` requires `execution.report_run_id == run_id == result.report_run_id`.
- **9 Reasoning:** nothing between lines 873 and 931 compares `view["run_id"]` with `plan.run_id`,
  `view["plan_digest"]` with `plan.digest`, or `view["report_run_id"]` with `report.run_id`. `_build_record` copies
  the view, so the rebuilt and stored records agree.
- **10 Evidence class:** SOURCE_PROVEN.
- **11 Affected:** every claims bundle under `verify_bundle`, and MCP and product readers that show offline standing.
- **12 False-support risk:** low. Offline standing is documented as never publishable, and replay catches it.
- **13 Replay/provenance impact:** offline provenance fields are unauthenticated. This contradicts "re-derives every
  part".
- **14 Compatibility impact:** genuine records already satisfy the stricter check, because `_execution_view`
  produces exactly these values. No schema change.
- **15 Certification impact:** `claims/assessment.py` is certified (:11621, :11796).
- **16 Genesis impact:** none.
- **17 Minimal reproduction plan:** take the `t3` fixture bundle, set `record.execution.plan_digest = "0"*64`, apply
  `_redigest`, and call `verify_bundle`. Expected: the same non-TAMPERED status as the genuine bundle. Cost is about
  3 s.
- **18 Smallest correct repair:** in `verify_assessment`, after the report is read, require:
  - `view.run_id == plan.run_id`
  - `view.plan_digest == plan.digest`
  - `view.capability_id == plan.capability_id`
  - `view.instance == plan.instance`
  - `view.report_run_id == (report.run_id if report else None)`

  Accept `condition_repairs` only as the domain's own re-derivable output, or do not label them `domain_repair`
  offline.
- **19 Owner approval:** yes (certified file).
- **20 Self-challenge:** "The offline status already says the report may be another run's." That disclaimer covers
  the report's numerics. It does not cover the record's own execution view contradicting its own plan, which is a
  plain internal inconsistency that verification claims to catch. MINOR.

---

## (a) Hypotheses I could not confirm (not promoted to findings)

1. **`binding_problems` skips** (`claims/execution.py:115-124`). A stated input is not checked when:
   - two claim paths map to one model input (multi-instance capabilities); or
   - the report's provenance does not record the input; or
   - the stated value is not a Quantity.

   A consequence needs an executor that ignores its case. The case is built from the same inputs
   (`planning.py:354-355`), so I found no reachable path. It is defense-in-depth only.
2. **Global coupling of tolerated drift** (`replay/bundle.py:767-769`). Any accepted numeric drift anywhere licenses
   every `report_digest`, `content_hash` and `evidence_record_hash` change anywhere. A variant run's report could
   change unseen while its public fields (verdict, usable, value) match. I found no case where this hides a
   verdict-relevant change.
3. **`system_runtime/replay.compare_runs`.** Two runs whose every node FAILED identically give
   `identity_replay=True`, `numerical_reproducibility=True` and `bitwise_identical=True` (the vacuous `all()` over
   empty outputs). This is the same shape as the known refusal-replay defect. It is exported but used by nothing in
   `src/`, and `scientific_validation` is fixed to "not_assessed". Consumer impact is unconfirmed.
4. **`providers/compare.OutputSelection`.** Affine weights of 0 or more can average opposite-sign nodal differences
   down to zero. The selection is declared and digest-bound, so this is not caller-silent.
5. **`parameter_uq` channel set by declaration.** The EPISTEMIC_PARAMETER channel is quantified from caller-declared
   input distributions, so a near-zero declared sigma satisfies a policy demand for that channel. This is documented
   as "a declaration, never evidence" (`parameter_uq.py:3-8`) and lives in caller-authored criteria. It is a design
   question, not a code defect.
6. **Organization profiles.** `DecisionContext` accepts any non-builtin `EvidencePolicyProfile`
   (`governance/policy.py:337-344`), so the risk bar can be caller-defined. This is documented and digest-bound.

## (b) Areas inspected and found sound

- **The P0 bound-result fix** (`bundle.py:656-680, 770-775`).
  - Stored "completed" or "bound" flags cannot earn VERIFIED by themselves: the replayed record is freshly executed
    and must match the stored one exactly, and both must pass the bound check.
  - Run identity is `claim-{core_digest[:16]}` (`planning.py:171,505`), and the core digest covers the case, models,
    capability digest and steps, so unrelated results cannot share a run id short of a 64-bit collision.
  - NaN: `math.isclose(nan, nan)` is False, and `nan != nan`. Both fail closed. Tolerance is
    `math.isclose(rel, abs)`, which is scale-aware.
- **Verdict monotonicity** (`credibility/evidence.py:787-901`).
  - NOT_SUPPORTED takes precedence over INSUFFICIENT.
  - An empty input is INSUFFICIENT.
  - Unknown enum members raise.
  - Attained levels are re-derived (GUARD 2/21, VAL-01).
  - Removing a check or a validity record can only lower the verdict.
- **Claim comparison** (`claims/verdict.py`).
  - An unquantified, COMBINED or misattributed channel gives NOT_EVALUATED.
  - A STANDARD record without k is unusable.
  - The band is a conservative linear sum.
  - Contradiction shares the support bar (`admissible`).
- **Context binding** (`claims/context.py`): context_ref, subject, run, capability, discrepancy and value are all
  checked.
- **Policy** (`governance/policy.py:433-451`): it only adds requirements, and monotonicity is enforced at
  construction.
- **CredibilityReportCritic** (`sria_bridge.py:244-260`) counts only planned checks for required levels.
- **Numerical UQ** (`numerical_uq.py:187-235`): the GCI/Richardson algebra is correct. The order is `min(p_obs,
  p_formal)` (conservative), Fs is 1.25, and a 64-ulp round-off floor gives UNKNOWN.
- **Parameter UQ** (`parameter_uq.py:293-320`): any unusable sample gives UNKNOWN, and Wilks gamma is correct.
- **Offline revalidation** (`revalidation.py`): oracle re-comparison, band-invariance of the verdict, and
  run-internal levels marked REPLAY_REQUIRED.
- **`assembly/replay` seal/certifies binding** (`:263-336, :456-495`): there is no re-wrapping and no foreign-run
  reuse.
- **`sria/decision/replay.py`**: exact manifest match, and no fallback to the current model.
