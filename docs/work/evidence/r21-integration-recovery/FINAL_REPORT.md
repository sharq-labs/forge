# R21 integration recovery — BLOCKED

Measured and independently reviewed source: `d05abfdf8216eda24a6235a9c7565d276f9a7fcc`. Final source tree was clean
before and after the official run. A subsequent documentation-only checkpoint records
this result; it does not turn the refused run into a receipt for another SHA.
BR1.1's historical bounded closure is retained. No new Big Rock or scientific
implementation was started. No remote changes were made.

## Result

Official local assurance refused at FAST311: **59 failed, 12,922 passed, 176 skipped**
in240.65s; wrapper265.02s, exit1. `LOCAL_ASSURANCE: REFUSED`,
`REFUSAL_KIND: EXPECTED_ASSURANCE_REFUSAL`, **`SAFE_TO_PUSH: NO`**.
Dependency guard passed. The59 failure IDs exactly match the shared Round20 set;
none of the four additional first-run failure IDs remains. This is an identity
comparison across different runs/runtimes, not proof that every diagnostic or cause
is identical. Skip admission did not run; the176 skips are not claimed admitted.

FAST312, SCIENTIFIC312, campaigns, regression, formal/V4/trust mutation shards,
source receipt construction, certificate generation, certificate-only child and
child verification were **NOT RUN** after the official runner stopped at FAST311.
The authorized workflow remains incomplete. No old logs were substituted for it.

## Blocker disposition

| Blocker | Root cause | Exact remediation | Reproduction evidence | Verification result | Reviewer decision | Source SHA | Final status |
|---|---|---|---|---|---|---|---|
| PROGRESS conflict | Divergent valid histories | Merge main and preserve both appended blocks verbatim | merge-proof.json; original conflict | Both blocks independently recovered; no source/test changes | Technical PASS |41663479|RESOLVED LOCALLY|
| Unknown provenance |1210 missing declarations plus stale DOCSET; older debt included |Explicit per-path hashes, source/custody records; preserve scanner |Two failures with1211unknown; exact historical456→1202 delta746 |33tests pass; current unknown0;746paths individually classified |Technical PASS |5d98271a; finald05abfdf|RESOLVED|
| Scope/retention audit |~122MB current changed files and repeated evidence |Retain evidence, classify measured reductions correctly, bounded secret/history scan |1812files/121624072bytes at41663479;692unpublishedblobs;173duplicategroups |Zero heuristic credential candidates; no deletion/relocation of scientific evidence |Technical PASS; limits explicit |41663479|AUDITED, retention preserved|
| Runtime bootstrap layout |Owned tools outside existing environment boundary looked like source |Place only owned bootstrap/provider tools under.forge/venvs; preserve initial failure |Ownership and impact failures in firstFAST311; partiallocationfix alsofailed |Bothfocusedcontrols pass; absent from finalFAST failures |No scanner weakening |d05abfdf|RESOLVED|
| Required-runtime integrity tests |3.11JSON depth limit; supported Pint versions have different registry fingerprints |Independent readability oracle; additive full-fingerprint/version/digest-qualified reference |Two firstFAST311 failures; dual-runtime probes |44pass1deselect each runtime; provenance33pass; absent finalfailures |Technical PASS; oldseal unchanged |d05abfdf|RESOLVED|
| Local assurance receipt |Required FAST311 still has59 failures |Owner-authorized separate scientific/Core remediation, then new reviewed immutable source and full workflow |Official finalfailure record andJUnit; complete IDs below |REFUSED, SAFE_TO_PUSH:NO; no receipt/child |Publication BLOCKED by mandatory gate |d05abfdf|BLOCKED|
| Private protection/merge restrictions |Protection API403; repo permits squash/rebase alongside merge |Owner enables supported private-protection plan and authorizes enforcing committed branch policy |GitHub says upgrade toPro or makepublic; no visibility change requested |Protection not enforceable through current API; no settings changed |Owner decision required |Remote184=d40aff44|BLOCKED|
| Independent approval |Only collaborator is author sharq-labs; botreview COMMENTED |Owner adds/names independent human reviewer; request review of final eligible SHA only after assurance clears |Collaborator/review API reads |No APPROVED human review; no review requested of stalehead |AI reviews do not satisfy policy |Remote184=d40aff44|BLOCKED|
| Publication/main integration |Mandatory assurance/governance gates unmet |After all gates, normalFFpush of solebranch, finaleligiblePRreview, merge and postmerge checks |PR184 stillOPEN atd40aff44, mergeablefalse/dirty remotely;185ancestor alreadyproven |No push, merge, superseded closure or certificate change |BLOCKED |Local source d05abfdf|NOT PERFORMED|

## Exact owner decisions needed

1. Authorize a **separate bounded scientific/Core triage and remediation task** for
   the59 listed required failures, explicitly addressing any OD-3/frozen-artifact
   changes it needs. The current certificate-only authorization does not authorize
   that work. Thermal, conservation/coupling, frozenCore/mutation and replay repairs
   cannot be smuggled into R21. No waiver, skip, looser threshold or renamed pass is
   proposed. Concrete blockers include the thermal caller-threshold guard,
   missing-schema reader guard and staleN60d mutation target (zero source matches).
2. Enable a private-repository protection capability supported by GitHub. The API
   specifically names GitHubPro; the account-plan field was null, so no exact
   current subscription is inferred. Keep visibility unchanged. Then explicitly
   authorize applying the committed branch policy, including required independent
   approval and merge-commit-only restrictions. No purchase or policy change was made.
3. Add/name an independent **human GitHub login** for the eventual eligible review.
   Only author`sharq-labs` is currently listed. An AI technical PASS or COMMENTED bot
   review is not APPROVED. Hosted checks for a future final remote SHA remain
   unassessed until a permitted push; no mandatory gate is waived.

## Commands and evidence

The final official command was:

```bash
.forge/venvs/3.12/bin/python -m tools.certification.local_assurance run --python311 .forge/venvs/3.11/bin/python --python312 .forge/venvs/3.12/bin/python --workers 4 --mutation-workers 2
```

WSL Ubuntu24.04; CPython3.11.17 and3.12.3; locally extracted ngspice42. Numerical
library thread counts1. Full argv/environment/timings, initial and final logs,
package freezes and source identities are preserved in `/home/dev_kaeem/br11-r21/`.
Runtime locations now lie under the checkout's ignored`.forge/venvs/`; no unrelated
worktree or system installation was modified. Python was supplied through uv's
[documented managed Python mechanism](https://docs.astral.sh/uv/guides/install-python/).
No physical-model validation, scientific certification or formal proof is claimed.

Final official failure record:
`.forge/assurance/d05abfdf8216eda24a6235a9c7565d276f9a7fcc/local-assurance-failure.json`

SHA-256:`38a31d6f20f325e4ceed36dc4c45c49df8853c98b83a2a2dba3b9504444e9f21`.

FinalJUnit SHA-256:`3a85ff8f217b87779a8b1e1005550ebcc5db7d41c5238a93ad94d2d7939615b4`.

Initial source5d98271a and its63-failure record remain preserved. The initial
bootstrap-location failure is not hidden; the partial ngspice-only move still
failed on Pythonlinks, and the complete environment-root correction passed.

## Remaining failure IDs

These are the59 observed mandatory failures, not a claim that every one is a
production scientific defect. Full diagnostics remain in officialJUnit and
`/home/dev_kaeem/br11-r21/final-fast311-failure-details.json`.

- `tests/claims/test_offline_revalidation.py::test_offline_verification_never_returns_verified`
- `tests/claims/test_offline_revalidation.py::test_replay_re_earns_what_offline_verification_cannot`
- `tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds`
- `tests/test_core_freeze_v4_manifest.py::test_the_deep_surface_carries_methods_and_member_positions`
- `tests/test_core_guards.py::test_no_gate_lets_its_caller_set_the_threshold_it_awards_a_level_against`
- `tests/test_core_scientific_audit_batch55.py::test_r67_every_folded_mutation_still_matches_the_live_source_exactly_once`
- `tests/test_core_scientific_audit_batch56.py::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see`
- `tests/test_core_semantic_invariants.py::test_every_reader_that_writes_a_schema_also_checks_one`
- `tests/test_electrothermal_vertical.py::test_l3_no_relaxation_appears_anywhere_in_the_module`
- `tests/test_interface_flux_execution.py::test_unqualified_direct_mapper_escape_and_stale_support_refuse`
- `tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable`
- `tests/test_mutation_population_v4.py::test_every_folded_mutation_still_matches_the_source_it_names`
- `tests/test_phase1_conservative_cell_mapping.py::test_a_constant_field_maps_to_the_same_constant`
- `tests/test_phase1_conservative_cell_mapping.py::test_a_non_convex_quadrilateral_is_refused`
- `tests/test_phase1_conservative_cell_mapping.py::test_a_signed_field_that_integrates_to_zero_is_conserved_without_division_by_zero`
- `tests/test_phase1_conservative_cell_mapping.py::test_a_source_partly_outside_the_target_support_is_refused`
- `tests/test_phase1_conservative_cell_mapping.py::test_a_target_outside_the_source_support_is_refused`
- `tests/test_phase1_conservative_cell_mapping.py::test_hexahedral_cells_are_refused`
- `tests/test_phase1_conservative_cell_mapping.py::test_node_fields_are_refused`
- `tests/test_phase1_conservative_cell_mapping.py::test_offset_scale_units_are_refused`
- `tests/test_phase1_conservative_cell_mapping.py::test_structured_remap_between_unequal_cell_counts_per_axis`
- `tests/test_phase1_conservative_cell_mapping.py::test_structured_remap_matches_hand_computed_overlaps`
- `tests/test_phase1_conservative_cell_mapping.py::test_unequal_triangles_are_weighted_by_their_overlap_area`
- `tests/test_phase1_coupling_convergence_coverage.py::test_a_self_loop_is_a_lagged_edge`
- `tests/test_phase2_coupling_authority.py::test_a_relaxed_native_plan_is_built_with_torn_only_relaxation`
- `tests/test_phase2_coupling_authority.py::test_an_iteration_limit_is_not_completed_on_both_paths`
- `tests/test_phase2_coupling_authority.py::test_the_runtime_build_keeps_every_produced_result`
- `tests/test_phase2_coupling_authority.py::test_the_runtime_build_reaches_the_native_outcome_iterations_and_values[nominal]`
- `tests/test_phase2_coupling_authority.py::test_the_runtime_build_reaches_the_native_outcome_iterations_and_values[two_stage]`
- `tests/test_phase2_coupling_authority.py::test_the_torn_edges_are_exactly_the_edges_the_runtime_requires_criteria_on`
- `tests/test_phase2_external_coupling.py::test_a_crashed_provider_is_a_classified_refusal_not_a_numerical_failure`
- `tests/test_phase2_external_coupling.py::test_a_field_coupled_run_maps_the_flux_conservatively_and_records_it`
- `tests/test_phase2_external_coupling.py::test_a_flux_mapped_by_nearest_site_is_refused`
- `tests/test_phase2_external_coupling.py::test_a_numerical_non_convergence_keeps_its_retryable_type`
- `tests/test_phase2_external_coupling.py::test_the_authority_refuses_mock_external_participants_unless_allowed`
- `tests/test_phase2_external_coupling.py::test_the_contract_is_honoured_by_a_conservative_flux_and_a_consistent_temperature`
- `tests/test_phase2_field_transfer.py::test_a_constant_maps_to_the_same_constant_between_two_tetrahedralizations_of_a_cube`
- `tests/test_phase2_field_transfer.py::test_a_degenerate_tetrahedron_is_refused`
- `tests/test_phase2_field_transfer.py::test_a_vector_field_is_remapped_component_by_component`
- `tests/test_phase2_field_transfer.py::test_tetrahedral_remap_conserves_the_integral_and_stays_within_the_source_range`
- `tests/test_phase2_field_transfer.py::test_the_same_tetrahedra_in_another_order_map_as_a_permutation`
- `tests/test_phase2_review_regressions.py::test_a_redundant_forward_tear_is_refused`
- `tests/test_phase2_review_regressions.py::test_a_tampered_plan_with_a_forward_tear_is_refused_by_the_runtime_build`
- `tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[1]`
- `tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[2]`
- `tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[3]`
- `tests/test_phase35_ws2_electrothermal_migration.py::test_a_refused_transfer_is_a_recorded_stop_on_both_paths`
- `tests/test_phase35_ws2_electrothermal_migration.py::test_a_relaxed_plan_requires_criteria_on_the_torn_edges_only`
- `tests/test_phase35_ws2_electrothermal_migration.py::test_an_iteration_limit_reproduces_the_native_final_iterate`
- `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[nominal]`
- `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[nominal_relaxed]`
- `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[two_stage]`
- `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[two_stage_relaxed]`
- `tests/test_phase35_ws3_conjugate_interface.py::test_an_explicit_plan_is_admitted_only_as_satisfied_to_its_splitting_error`
- `tests/test_phase35_ws3_conjugate_interface.py::test_an_honest_graph_is_admitted_and_states_both_conditions_and_what_it_does_not_establish`
- `tests/test_phase35_ws3_conjugate_interface.py::test_an_implicit_plan_must_measure_both_interface_edges`
- `tests/test_phase35_ws3_conjugate_interface.py::test_the_receiver_sign_flips_with_the_declared_normal`
- `tests/test_phase35_ws3_conjugate_interface.py::test_wrong_interface_semantics_are_refused[<lambda>-conservatively]`
- `tests/test_phase35_ws3_conjugate_interface.py::test_wrong_interface_semantics_are_refused[<lambda>-heat flux dimension]`
