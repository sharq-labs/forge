# FAST failure baseline, classified (recorded 2026-10-20, written 2026-10-23)

This is a **comparison aid**, not a skip list, not a deselect list and not scientific evidence.
Nothing may read it to skip, deselect, xfail or admit a test, and a run that reproduces every
node below is still a **failing** run. No registry state (KNOWN_BASELINE_FAILURE, ENVIRONMENTAL, ...)
is assigned here; assigning one is an owner decision. The classes below describe the recorded
evidence and the mechanism found by static reading on `12862b0b`. Tests were **NOT RUN** to write this file.

Use: compare your run's failure set with the set below for the same platform. A failing node that
is not listed is **new** until shown otherwise. A listed node that now passes may be fixed; re-run it
before saying so.

## Sources

| Set | Platform | Code | Command | Result | Evidence |
|---|---|---|---|---|---|
| Linux | WSL2 Ubuntu 24.04, CPython 3.12.3 (`.forge/venvs/3.12`) | `8ec97064` plus the conservation performance fix (clone `cc5b7c6e`). Over `src tests tools flagships providers certification .github pyproject.toml experiments` this equals `12862b0b`, except that `benchmarks/domain_real_data/` (4 test modules) was added later and was not in the run. The two fix files match `12862b0b` byte for byte (sha256 in `docs/work/evidence/fast_runtime_2026_10_20.json`). | `python -m pytest -m 'not expensive' -q -n 4 --dist loadfile -p no:cacheprovider ...` (PROGRESS.md, 2026-10-20 FAST runtime entry) | 64 failed, 11,874 passed, 176 skipped; the run on `8ec97064` failed the same 64 nodes | JUnit mirrored off-tree at `D:/forge-fast-runtime-evidence-20261020/after-n4.xml` (sha256 `4ff7945a701ebb6734851de7c8e112ba73f0f85c28acd57bc2024ca802c79c8c`) |
| Windows | Windows 11, CPython 3.14.2 | not recorded (a `main` control worktree, 2026-10-20) | `-q -n 4 --dist loadfile -m "not expensive"` | 185 failed + 22 errors = 207 nodes, 431.5 s | `docs/work/evidence/domain_inventory_reconciliation_2026_10_20/main-fast-loadfile.md` |
| GitHub CI, last run that executed steps | ubuntu-24.04, Python 3.11 and 3.12 | `e193e573` (2026-10-14, PR #142 merge) | `tests.yml` jobs | fast 3.12 and fast 3.11: 1 failed (`tests/test_core_certificate.py::test_the_certificate_describes_this_tree`); scientific: the same 1; reproduce (Docker): 161 failed; mutations cancelled at the 6 h cap | Tests run 38544091505; job logs read 2026-10-23. No job has run a step since (Actions billing; ACTIVE_PLAN OD-25) |

All 64 Linux nodes are among the 207 Windows nodes. The other 143 failed only on Windows.

## Linux 64, by class

| Class | Nodes | Mechanism (static reading) | Owner path |
|---|---:|---|---|
| OD3_DRIFT | 8 | The stored certificate describes `05522b59`: it lacks the `system_runtime_dependencies` area, and the V4 deep surface differs from the pinned one | OD-3 recertification |
| STALE_CERTIFIED_MUTANT | 2 | Mutant N60d targets `if level<policy.minimum_level:` in `planning.py::plan_verification`, which `56cd0e01` removed (predicted in DEFERRED_VALIDATION DV-41). No mutant covers the replacement rule at `planning.py:91` | owner decision + OD-3 |
| GUARD_VS_CODE | 3 | `test_core_guards`: a bare-float threshold (`*_atol`) in `conduction1d_transient_fv.py`. `test_core_semantic_invariants`: readers in `mesh_adaptation`, `conservation`, `multiphysics/conservation` and `fields/definition` skip the schema check. `test_electrothermal_vertical`: `omega` / `relaxation_factor` in `systems/electrothermal/coupled.py` | scientific-design decision; never relax the guard |
| BEHAVIOUR_VS_TEST | 49 | Phase 1/2/3.5 tests merged in #157 as "tests NOT RUN" now meet the semantic refusals added by #159 (`98da0c02`), #160 (`4f239fa7`) and #161 (`1f43c59e`) | scientific-design decision per module |
| UNRESOLVED | 2 | Offline revalidation replays NOT_REPRODUCIBLE on a clean tree in all 3 recorded runs; the cause is not established | investigate |

The 54 nodes outside OD3_DRIFT and UNRESOLVED are deterministic and have stayed on `main` through more than
20 merges. They are regressions to triage, not a baseline to accept.

| Node | Class |
|---|---|
| `tests/test_interface_flux_execution.py::test_unqualified_direct_mapper_escape_and_stale_support_refuse` | BEHAVIOUR_VS_TEST |
| `tests/test_multiphysics_window_control.py::test_step_size_memory_halves_the_repeated_rejections_and_keeps_every_window_stable` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_a_constant_field_maps_to_the_same_constant` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_a_non_convex_quadrilateral_is_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_a_signed_field_that_integrates_to_zero_is_conserved_without_division_by_zero` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_a_source_partly_outside_the_target_support_is_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_a_target_outside_the_source_support_is_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_hexahedral_cells_are_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_node_fields_are_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_offset_scale_units_are_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_structured_remap_between_unequal_cell_counts_per_axis` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_structured_remap_matches_hand_computed_overlaps` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_conservative_cell_mapping.py::test_unequal_triangles_are_weighted_by_their_overlap_area` | BEHAVIOUR_VS_TEST |
| `tests/test_phase1_coupling_convergence_coverage.py::test_a_self_loop_is_a_lagged_edge` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_coupling_authority.py::test_a_relaxed_native_plan_is_built_with_torn_only_relaxation` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_coupling_authority.py::test_an_iteration_limit_is_not_completed_on_both_paths` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_coupling_authority.py::test_the_runtime_build_keeps_every_produced_result` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_coupling_authority.py::test_the_runtime_build_reaches_the_native_outcome_iterations_and_values[nominal]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_coupling_authority.py::test_the_runtime_build_reaches_the_native_outcome_iterations_and_values[two_stage]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_coupling_authority.py::test_the_torn_edges_are_exactly_the_edges_the_runtime_requires_criteria_on` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_external_coupling.py::test_a_crashed_provider_is_a_classified_refusal_not_a_numerical_failure` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_external_coupling.py::test_a_field_coupled_run_maps_the_flux_conservatively_and_records_it` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_external_coupling.py::test_a_flux_mapped_by_nearest_site_is_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_external_coupling.py::test_a_numerical_non_convergence_keeps_its_retryable_type` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_external_coupling.py::test_the_authority_refuses_mock_external_participants_unless_allowed` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_external_coupling.py::test_the_contract_is_honoured_by_a_conservative_flux_and_a_consistent_temperature` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_field_transfer.py::test_a_constant_maps_to_the_same_constant_between_two_tetrahedralizations_of_a_cube` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_field_transfer.py::test_a_degenerate_tetrahedron_is_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_field_transfer.py::test_a_vector_field_is_remapped_component_by_component` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_field_transfer.py::test_tetrahedral_remap_conserves_the_integral_and_stays_within_the_source_range` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_field_transfer.py::test_the_same_tetrahedra_in_another_order_map_as_a_permutation` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_review_regressions.py::test_a_redundant_forward_tear_is_refused` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_review_regressions.py::test_a_tampered_plan_with_a_forward_tear_is_refused_by_the_runtime_build` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[1]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[2]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase2_review_regressions.py::test_no_admissible_plan_of_the_series_pack_reaches_the_forward_tear_refusal[3]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws2_electrothermal_migration.py::test_a_refused_transfer_is_a_recorded_stop_on_both_paths` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws2_electrothermal_migration.py::test_a_relaxed_plan_requires_criteria_on_the_torn_edges_only` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws2_electrothermal_migration.py::test_an_iteration_limit_reproduces_the_native_final_iterate` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[nominal]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[nominal_relaxed]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[two_stage]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws2_electrothermal_migration.py::test_the_candidate_reproduces_the_native_loop[two_stage_relaxed]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws3_conjugate_interface.py::test_an_explicit_plan_is_admitted_only_as_satisfied_to_its_splitting_error` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws3_conjugate_interface.py::test_an_honest_graph_is_admitted_and_states_both_conditions_and_what_it_does_not_establish` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws3_conjugate_interface.py::test_an_implicit_plan_must_measure_both_interface_edges` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws3_conjugate_interface.py::test_the_receiver_sign_flips_with_the_declared_normal` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws3_conjugate_interface.py::test_wrong_interface_semantics_are_refused[<lambda>-conservatively]` | BEHAVIOUR_VS_TEST |
| `tests/test_phase35_ws3_conjugate_interface.py::test_wrong_interface_semantics_are_refused[<lambda>-heat flux dimension]` | BEHAVIOUR_VS_TEST |
| `tests/test_core_guards.py::test_no_gate_lets_its_caller_set_the_threshold_it_awards_a_level_against` | GUARD_VS_CODE |
| `tests/test_core_semantic_invariants.py::test_every_reader_that_writes_a_schema_also_checks_one` | GUARD_VS_CODE |
| `tests/test_electrothermal_vertical.py::test_l3_no_relaxation_appears_anywhere_in_the_module` | GUARD_VS_CODE |
| `tests/test_core_certificate.py::test_the_certificate_describes_this_tree` | OD3_DRIFT |
| `tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully` | OD3_DRIFT |
| `tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies` | OD3_DRIFT |
| `tests/test_core_freeze_v3_manifest.py::test_core_freeze_v4_is_the_contract_that_binds_on_this_tree` | OD3_DRIFT |
| `tests/test_core_freeze_v4_manifest.py::test_once_assured_the_full_verification_holds` | OD3_DRIFT |
| `tests/test_core_freeze_v4_manifest.py::test_the_deep_surface_carries_methods_and_member_positions` | OD3_DRIFT |
| `tests/test_core_freeze_v4_manifest.py::test_the_tree_keeps_the_core_freeze_v4_contract` | OD3_DRIFT |
| `tests/test_core_scientific_audit_batch56.py::test_r69_the_v4_surface_records_the_methods_the_digests_could_not_see` | OD3_DRIFT |
| `tests/test_core_scientific_audit_batch55.py::test_r67_every_folded_mutation_still_matches_the_live_source_exactly_once` | STALE_CERTIFIED_MUTANT |
| `tests/test_mutation_population_v4.py::test_every_folded_mutation_still_matches_the_source_it_names` | STALE_CERTIFIED_MUTANT |
| `tests/claims/test_offline_revalidation.py::test_offline_verification_never_returns_verified` | UNRESOLVED |
| `tests/claims/test_offline_revalidation.py::test_replay_re_earns_what_offline_verification_cannot` | UNRESOLVED |

## Windows-only 143, by module

These failed in the Windows run and not in the Linux run. "not attributed" means no mechanism was
established; do not assume it is environmental.

| Module | Nodes | Mechanism |
|---|---:|---|
| `tests/test_mutation_workspace.py` | 72 | Linux-only harness (`tools/certification/mutation_workspace.py`: `O_NOFOLLOW`, `prctl`) |
| `tests/test_formal_xdist.py` | 24 | not attributed |
| `tests/foundations/test_escrow_boundary.py` | 15 | POSIX isolation (`blindfold/isolation.py:77` `os.geteuid`, `unshare`) |
| `tests/foundations/test_authority_durable_campaign.py` | 10 | POSIX ledger lock (`authority/ledger.py:277` `import fcntl`) |
| `tests/test_local_assurance.py` | 7 | Linux-only tool (`local_assurance.py:117-122` refuses non-Linux) |
| `tests/foundations/test_authority_integrity.py` | 4 | POSIX key custody and ledger (`authority/keys.py:212` `os.geteuid`; `ledger.py:277`) |
| `tests/test_mutation_startup.py` | 3 | not attributed |
| `flagships/tests/test_battery_blind_readiness.py` | 2 | not attributed |
| `tests/foundations/test_escrow_isolation.py` | 2 | POSIX isolation (`blindfold/isolation.py`) |
| `tests/foundations/test_v2_blindfold.py` | 1 | POSIX isolation (`blindfold/isolation.py`) |
| `tests/test_change_impact.py` | 1 | `symlink_to` needs a privilege: `OSError: [WinError 1314]` (observed 2026-10-23) |
| `tests/test_repository_ownership.py` | 1 | not attributed |
| `tests/test_test_timing.py` | 1 | worktree and basetemp on different drives (PROGRESS.md, 2026-10-17) |

<details><summary>All 143 Windows-only node ids</summary>

- `flagships/tests/test_battery_blind_readiness.py::test_the_dry_run_records_every_abstention_with_its_rule_inputs`
- `flagships/tests/test_battery_blind_readiness.py::test_the_dry_run_walks_the_whole_chain_without_claiming_anything`
- `tests/foundations/test_authority_durable_campaign.py::test_a_campaign_resumes_exactly_after_restart`
- `tests/foundations/test_authority_durable_campaign.py::test_a_dropped_journal_tail_after_the_operators_anchor_is_refused`
- `tests/foundations/test_authority_durable_campaign.py::test_a_journal_signed_in_a_compromise_window_cannot_be_resumed`
- `tests/foundations/test_authority_durable_campaign.py::test_a_mutation_around_the_journal_is_refused_not_lost`
- `tests/foundations/test_authority_durable_campaign.py::test_a_second_exposure_issuer_cannot_fork_or_squat_the_campaign`
- `tests/foundations/test_authority_durable_campaign.py::test_a_verdict_judged_before_restart_is_the_same_verdict_after`
- `tests/foundations/test_authority_durable_campaign.py::test_another_key_or_issuer_cannot_resume_or_extend_the_campaign`
- `tests/foundations/test_authority_durable_campaign.py::test_foreign_journal_entries_cannot_squat_or_brick_a_campaign`
- `tests/foundations/test_authority_durable_campaign.py::test_restart_detects_dropped_reordered_or_rewritten_operations`
- `tests/foundations/test_authority_durable_campaign.py::test_the_same_campaign_id_cannot_restart_its_multiplicity_count`
- `tests/foundations/test_authority_integrity.py::test_a_key_is_registered_only_by_its_holder_in_its_providers_class`
- `tests/foundations/test_authority_integrity.py::test_a_second_writer_or_a_failed_append_never_forks_the_ledger`
- `tests/foundations/test_authority_integrity.py::test_key_material_placement`
- `tests/foundations/test_authority_integrity.py::test_persistence_restart_and_tamper_detection`
- `tests/foundations/test_escrow_boundary.py::test_a_deleted_journal_refuses_to_start`
- `tests/foundations/test_escrow_boundary.py::test_a_log_read_is_single_use_across_restarts`
- `tests/foundations/test_escrow_boundary.py::test_a_replaced_history_at_the_same_length_is_refused`
- `tests/foundations/test_escrow_boundary.py::test_a_replaced_universe_refuses_to_start`
- `tests/foundations/test_escrow_boundary.py::test_a_rolled_back_or_restored_journal_is_caught_by_a_durable_client_checkpoint`
- `tests/foundations/test_escrow_boundary.py::test_a_tampered_journal_refuses_to_start_and_a_truncated_one_is_caught_by_the_client`
- `tests/foundations/test_escrow_boundary.py::test_budgets_submissions_and_query_ids_survive_an_escrow_restart`
- `tests/foundations/test_escrow_boundary.py::test_clients_always_pin_the_escrow_key_and_integrity_is_not_a_refusal`
- `tests/foundations/test_escrow_boundary.py::test_noise_after_a_rollback_is_not_reproduced_for_another_request`
- `tests/foundations/test_escrow_boundary.py::test_requests_are_capability_bound_and_never_carry_the_credential`
- `tests/foundations/test_escrow_boundary.py::test_responses_are_signed_and_bound_to_their_request`
- `tests/foundations/test_escrow_boundary.py::test_storage_is_private_and_outside_the_repository`
- `tests/foundations/test_escrow_boundary.py::test_the_escrow_never_asserts_a_verified_boundary_and_query_keys_are_unambiguous`
- `tests/foundations/test_escrow_boundary.py::test_the_subprocess_escrow_resumes_its_journal_but_stays_unproven`
- `tests/foundations/test_escrow_boundary.py::test_unauthenticated_requests_never_touch_a_campaign`
- `tests/foundations/test_escrow_isolation.py::test_the_isolated_deployment_reports_exactly_what_it_established`
- `tests/foundations/test_escrow_isolation.py::test_the_leak_detector_catches_a_planted_partial_copy`
- `tests/foundations/test_v2_blindfold.py::test_the_subprocess_escrow_keeps_its_secrets_in_the_child`
- `tests/test_change_impact.py::test_f7_a_tree_with_a_refused_entry_narrows_nothing`
- `tests/test_formal_xdist.py::test_an_unconfirmed_xdist_kill_is_not_credit`
- `tests/test_formal_xdist.py::test_confirmation_needs_the_pristine_tree_plus_exactly_the_declared_edit`
- `tests/test_formal_xdist.py::test_confirmation_reads_the_name_from_the_nodeid_not_the_message`
- `tests/test_formal_xdist.py::test_every_infrastructure_defect_refuses[linked]`
- `tests/test_formal_xdist.py::test_formal_run_credits_only_with_a_clean_sentinel[absent]`
- `tests/test_formal_xdist.py::test_formal_run_credits_only_with_a_clean_sentinel[clean]`
- `tests/test_formal_xdist.py::test_formal_run_credits_only_with_a_clean_sentinel[crash]`
- `tests/test_formal_xdist.py::test_formal_run_credits_only_with_a_clean_sentinel[stale]`
- `tests/test_formal_xdist.py::test_import_refusal_attempts_stay_serial_with_a_serial_control`
- `tests/test_formal_xdist.py::test_main_threads_workers_and_confirms_only_under_xdist`
- `tests/test_formal_xdist.py::test_named_alone_control_refuses_a_copy_changed_between_its_runs`
- `tests/test_formal_xdist.py::test_named_alone_control_selects_by_the_rule_and_voids_a_failing_guard[0]`
- `tests/test_formal_xdist.py::test_named_alone_control_selects_by_the_rule_and_voids_a_failing_guard[1]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[-11--WorkspaceError]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[0-1 passed\n-False]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[1-FAILED tests/t.py::test_guard[a] - boom\n-False]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[1-tests/t.py F\n==================== short test summary info ====================\nFAILED tests/t.py::test_guard[a] - boom\n========== 1 failed in 0.10s ==========\n-True]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[1-tests/t.py F\n==================== short test summary info ====================\nFAILED tests/t.py::test_other - boom\n========== 1 failed in 0.10s ==========\n-False]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[2-Interrupted\n-False]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[3-INTERNALERROR\n-WorkspaceError]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[4-usage\n-WorkspaceError]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[5-no tests ran\n-False]`
- `tests/test_formal_xdist.py::test_serial_confirmation_only_credits_a_named_failure_alone[timeout--False]`
- `tests/test_formal_xdist.py::test_serial_formal_run_has_no_xdist`
- `tests/test_local_assurance.py::test_child_exit_during_forced_kill_preserves_stream_error`
- `tests/test_local_assurance.py::test_source_gate_orchestration_preserves_checkout[None-1]`
- `tests/test_local_assurance.py::test_source_gate_orchestration_preserves_checkout[None-2]`
- `tests/test_local_assurance.py::test_source_gate_orchestration_preserves_checkout[formal_mutations_1-1]`
- `tests/test_local_assurance.py::test_source_gate_orchestration_preserves_checkout[formal_mutations_1-2]`
- `tests/test_local_assurance.py::test_source_gate_orchestration_preserves_checkout[v4_mutations_3-1]`
- `tests/test_local_assurance.py::test_source_gate_orchestration_preserves_checkout[v4_mutations_3-2]`
- `tests/test_mutation_startup.py::test_environment_snapshot_is_independent_of_parent_and_each_child`
- `tests/test_mutation_startup.py::test_interpreter_replacement_is_refused_with_same_size`
- `tests/test_mutation_startup.py::test_venv_interpreter_symlink_spelling_is_preserved`
- `tests/test_mutation_workspace.py::test_ambiguous_owner_retains_worker_and_blocks_next_attempt`
- `tests/test_mutation_workspace.py::test_authenticated_clean_dirty_candidates_are_not_recopied[mode-only]`
- `tests/test_mutation_workspace.py::test_authenticated_clean_dirty_candidates_are_not_recopied[unchanged-hint]`
- `tests/test_mutation_workspace.py::test_changed_sigchld_during_drain_retains_and_refuses`
- `tests/test_mutation_workspace.py::test_cli_scratch_existing_user_artifacts_are_never_cleared`
- `tests/test_mutation_workspace.py::test_concurrent_shards_have_distinct_mutable_state`
- `tests/test_mutation_workspace.py::test_contamination_before_attempt_invalidates_without_entering`
- `tests/test_mutation_workspace.py::test_dedicated_process_contract_refuses_detectable_competing_owners[children]`
- `tests/test_mutation_workspace.py::test_dedicated_process_contract_refuses_detectable_competing_owners[kernel-threads]`
- `tests/test_mutation_workspace.py::test_dedicated_process_contract_refuses_detectable_competing_owners[sigchld-handler]`
- `tests/test_mutation_workspace.py::test_dedicated_process_contract_refuses_detectable_competing_owners[sigchld-mask]`
- `tests/test_mutation_workspace.py::test_dedicated_process_contract_refuses_detectable_competing_owners[subreaper]`
- `tests/test_mutation_workspace.py::test_descendant_drain_timeout_is_not_a_mutation_verdict`
- `tests/test_mutation_workspace.py::test_detached_children_are_drained_after_adoption`
- `tests/test_mutation_workspace.py::test_diagnostic_atomic_replacement_cannot_overwrite_link_target[symlink]`
- `tests/test_mutation_workspace.py::test_diagnostic_parent_substitution_is_ignorable_without_outside_write`
- `tests/test_mutation_workspace.py::test_dirty_hints_do_not_hide_unrelated_same_size_and_restored_timestamp_bytes`
- `tests/test_mutation_workspace.py::test_drain_failure_stage_retains_worker_and_cannot_authorize_reuse`
- `tests/test_mutation_workspace.py::test_failure_restores_then_cleans_owned_workspace[KeyboardInterrupt]`
- `tests/test_mutation_workspace.py::test_failure_restores_then_cleans_owned_workspace[OSError]`
- `tests/test_mutation_workspace.py::test_formal_control_first_single_population_and_guard_transcript`
- `tests/test_mutation_workspace.py::test_formal_infrastructure_exit_cannot_earn_transcript_credit[-9]`
- `tests/test_mutation_workspace.py::test_formal_infrastructure_exit_cannot_earn_transcript_credit[3]`
- `tests/test_mutation_workspace.py::test_formal_infrastructure_exit_cannot_earn_transcript_credit[4]`
- `tests/test_mutation_workspace.py::test_formal_infrastructure_exit_cannot_earn_transcript_credit[5]`
- `tests/test_mutation_workspace.py::test_invalid_dirty_hint_poisoning_refuses_next_attempt`
- `tests/test_mutation_workspace.py::test_known_target_restore_is_sparse_but_worker_sha_remains_complete`
- `tests/test_mutation_workspace.py::test_lifecycle_failure_diagnostics_preserve_exact_mutation_and_stage`
- `tests/test_mutation_workspace.py::test_linked_artifacts_and_repository_local_storage_are_refused`
- `tests/test_mutation_workspace.py::test_local_telemetry_is_outside_manifest_and_cannot_verify_as_receipt`
- `tests/test_mutation_workspace.py::test_manifest_is_complete_deterministic_and_includes_git`
- `tests/test_mutation_workspace.py::test_mid_walk_failure_still_reports_entries_already_scanned`
- `tests/test_mutation_workspace.py::test_mutation_changes_worker_only_and_repairs_exact_bytes`
- `tests/test_mutation_workspace.py::test_new_index_cannot_mask_seed_link_or_type_contamination[file-directory]`
- `tests/test_mutation_workspace.py::test_new_index_cannot_mask_seed_link_or_type_contamination[hardlink]`
- `tests/test_mutation_workspace.py::test_new_index_cannot_mask_seed_link_or_type_contamination[same-size-seed]`
- `tests/test_mutation_workspace.py::test_next_mutation_observes_pristine_identity`
- `tests/test_mutation_workspace.py::test_pristine_index_is_reused_without_retaining_file_bytes`
- `tests/test_mutation_workspace.py::test_restore_failure_cannot_issue_a_verdict_or_start_next_attempt`
- `tests/test_mutation_workspace.py::test_restore_repairs_all_contamination_types[deleted]`
- `tests/test_mutation_workspace.py::test_restore_repairs_all_contamination_types[git]`
- `tests/test_mutation_workspace.py::test_restore_repairs_all_contamination_types[mode]`
- `tests/test_mutation_workspace.py::test_restore_repairs_all_contamination_types[replaced-directory]`
- `tests/test_mutation_workspace.py::test_restore_repairs_all_contamination_types[unexpected]`
- `tests/test_mutation_workspace.py::test_restore_streams_seed_without_content_cache`
- `tests/test_mutation_workspace.py::test_seed_mismatch_stops_before_first_restore_and_next_attempt[bytes]`
- `tests/test_mutation_workspace.py::test_seed_mismatch_stops_before_first_restore_and_next_attempt[deleted]`
- `tests/test_mutation_workspace.py::test_seed_mismatch_stops_before_first_restore_and_next_attempt[directory]`
- `tests/test_mutation_workspace.py::test_seed_mismatch_stops_before_first_restore_and_next_attempt[hardlink]`
- `tests/test_mutation_workspace.py::test_seed_mismatch_stops_before_first_restore_and_next_attempt[mode]`
- `tests/test_mutation_workspace.py::test_seed_mismatch_stops_before_first_restore_and_next_attempt[symlink]`
- `tests/test_mutation_workspace.py::test_seed_mismatch_stops_before_first_restore_and_next_attempt[unexpected]`
- `tests/test_mutation_workspace.py::test_seed_permissions_are_read_only_and_cleanup_never_follows_substituted_directory`
- `tests/test_mutation_workspace.py::test_seed_restore_open_descriptor_is_closed_on_write_failure`
- `tests/test_mutation_workspace.py::test_seed_symlink_and_git_external_pointer_are_refused`
- `tests/test_mutation_workspace.py::test_seed_tampering_refuses_restore`
- `tests/test_mutation_workspace.py::test_sparse_repair_does_not_chmod_through_symlink_ancestor`
- `tests/test_mutation_workspace.py::test_string_path_snapshot_equals_the_pathlib_manifest_and_counters`
- `tests/test_mutation_workspace.py::test_substituted_artifact_root_cannot_clear_user_basetemp`
- `tests/test_mutation_workspace.py::test_telemetry_counter_accounting_failure_cannot_change_workspace_identity`
- `tests/test_mutation_workspace.py::test_undrained_descendant_refuses_without_restoration_or_cleanup`
- `tests/test_mutation_workspace.py::test_v4_failure_paths_restore_before_next_mutation[application-refusal]`
- `tests/test_mutation_workspace.py::test_v4_failure_paths_restore_before_next_mutation[no-report]`
- `tests/test_mutation_workspace.py::test_v4_failure_paths_restore_before_next_mutation[timeout]`
- `tests/test_mutation_workspace.py::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[-9]`
- `tests/test_mutation_workspace.py::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[2]`
- `tests/test_mutation_workspace.py::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[3]`
- `tests/test_mutation_workspace.py::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[4]`
- `tests/test_mutation_workspace.py::test_v4_infrastructure_exit_cannot_earn_named_junit_kill[5]`
- `tests/test_mutation_workspace.py::test_v4_population_once_and_existing_transcript_contract`
- `tests/test_mutation_workspace.py::test_v4_restore_failure_never_returns_killed`
- `tests/test_mutation_workspace.py::test_worker_symlink_is_removed_without_touching_source`
- `tests/test_repository_ownership.py::test_a_symlink_is_refused_never_followed`
- `tests/test_test_timing.py::test_the_plugin_records_telemetry_and_never_changes_an_outcome`

</details>

## Not in either recorded set: `benchmarks/domain_real_data` (observed 2026-10-23)

The Linux run predates `benchmarks/domain_real_data/`. On pristine `12862b0b` (Windows 11, CPython 3.14.2,
`-n 4 --dist loadfile -m "not expensive"`, run 2026-10-23 for this file) two of its tests fail. Both have one cause:
6 tracked files have no reviewed row in `benchmarks/domain_real_data/CURRENT_PROVENANCE.json`.

- `benchmarks/domain_real_data/tests/test_domain_real_data.py::test_current_repository_inventory_has_no_unreviewed_provenance`
- `benchmarks/domain_real_data/tests/test_domain_real_data.py::test_synthetic_data_is_never_called_measured` (`assert 6 == 0`)

Unreviewed files: `docs/work/evidence/branch_ci_investigation_2026_10_20/` `agent-archive-final-gate.json`,
`agent-archive-final-gate.txt`, `agent-archive-gate.json`, `agent-archive-gate.txt`, `jobs-39488053735.json`,
`jobs-39488053796.json`. The fix is a provenance review of those files, never a test change.

## Known nondeterminism that can look like a baseline change

- Open in certified gates: the wall-clock growth guards in `tests/test_core_performance_guards.py` (`GROWTH_BAND = 25`; one CI run reached 32.3x), and `tests/test_formal_xdist.py::test_real_xdist_infrastructure_failure_never_earns_credit[worker_lost_before_target-reasons1]` (Linux; fails under CPU load, passes alone).
- Before calling a node FLAKY, sweep the hidden inputs that turned two earlier "flakes" into deterministic bugs: `COLUMNS`, `PYTHONHASHSEED`, `-n`, machine load, and the drive layout of the worktree and basetemp.

## Refresh rule

When a new pristine-`main` run is recorded, replace this file with a new dated one rather than editing rows.
Record the tested commit, the exact command, the platform and the JUnit sha256.
