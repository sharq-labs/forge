"""Test tiering for Crafty.

This file assigns execution-tier markers. It contains **no fixtures and no
scientific logic**, it never changes what a test asserts, and it never skips,
deselects or reorders anything — it only labels tests so a developer can choose
a subset to run. Every test still runs in the FULL suite.

Why the labels live here rather than as ``@pytest.mark`` decorators
--------------------------------------------------------------------

Two test modules are **SHA-256 pinned by frozen experiments**:

    experiments/electrical_e2/e2_config.py  pins  tests/test_sria_e1_electrical.py
    experiments/electrical_e3/e3_config.py  pins  tests/test_sria_e2_model_adequacy.py

Those digests are what makes "E1 was not edited under E2" a checkable claim.
Adding a decorator to either file would change its bytes and break the pin, and
both files need tier labels. Applying every label from here keeps the mechanism
uniform and leaves all 72 existing test files byte-identical.

The two markers
---------------

``expensive``
    The test executes scientific work whose cost is measured in seconds:
    it reproduces a frozen experiment, drives a domain solver, or runs a design
    study. Excluded from FAST.

``campaign``
    A subset of ``expensive``: a large design/discovery campaign or a full
    stiff-solver verification ladder run to its budget. These are the handful of
    tests that dominate the suite. Excluded from SCIENTIFIC, included in FULL.

The criterion is **behavioural, not chronometric**. A test is labelled because
of the kind of work it performs, and the measured cost is recorded only as
corroboration. Cheap scientific tests are deliberately *not* labelled: the
electrical DC solver tests in ``tests/domains/electrical/`` execute real domain
numerics and stay in FAST, because that execution costs milliseconds and the
coverage is worth having after every edit.

Why whole modules, and not individual tests
-------------------------------------------

The frozen-experiment modules memoize their experiment in a module-level global
(``_RESULT`` in E2/E3/the electrical demo) or in the experiment package itself
(``t1_run.forward_map`` returns a cached object — ``test_t2_uses_t1s_forward_maps_unchanged``
asserts identity with ``is``). The run is therefore a **shared module cost**,
charged to whichever test reaches it first.

That was measured, not assumed. An earlier per-test classification excluded the
individually slowest tests and the suite barely moved: the cost simply hopped to
the next test in the module. Labelling per module is what actually avoids the
work.

Each such module keeps an allowlist of **static guards** — tests that only read
files and compare digests, scan source for forbidden imports, or check that
nothing wrote to ``src/``. Those cost nothing, they are the checks most worth
running after every edit, and they never touch the memoized result. The
allowlists are verified two ways: ``test_tier_classification.py`` asserts every
name still exists, and FAST's measured runtime would jump immediately if an
allowlisted test did trigger an experiment.

See docs/TESTING.md for the tiers and the commands that select them.
"""

from __future__ import annotations

import pytest

# --------------------------------------------------------------------------
# `campaign` — the giants. Measured sequential cost on this machine in
# brackets; see docs/TESTING.md for the machine and the caveat that wall-clock
# on it carries a 9-14% spread for identical code.
# --------------------------------------------------------------------------

CAMPAIGN_TESTS: dict[str, str] = {
    "tests/systems/aerospace/test_multirotor_mvr1.py"
    "::test_full_studies_a_and_b_use_same_universe_and_a_reproduces_mvr0": (
        "two full 1000-candidate multirotor studies (A and B), pinning their "
        "exact population counts [~261 s, 46% of the whole suite]"
    ),
    "tests/systems/aerospace/test_multirotor_mvr0.py"
    "::test_1000_candidate_vertical_slice_runs_end_to_end": (
        "a full 1000-candidate reference study end to end [~103 s]"
    ),
    "tests/domains/kinetics/test_cstr_inference_admissibility.py"
    "::test_r7_usable_single_solve_is_rejected_without_sequence_validation": (
        "solves the R7 oscillatory regime (20001 output points) before "
        "checking the admissibility refusal [~33 s]. The sibling R8 test keeps "
        "the adapter's refusal path in SCIENTIFIC at negligible cost"
    ),
    "tests/domains/kinetics/test_cstr_domain.py"
    "::test_the_gate_withholds_reference_levels_without_tolerance_independence": (
        "drives the full five-rung tolerance ladder plus the cross-method arm "
        "on the strongly stiff regime [~32 s]"
    ),
}

# --------------------------------------------------------------------------
# `expensive` — modules whose tests execute a frozen experiment, a domain
# solver, or a design study. Everything in the module is labelled except the
# named static guards, which only read and hash files.
# --------------------------------------------------------------------------

EXPENSIVE_MODULES: dict[str, str] = {
    "tests/test_thermal_t1_fidelity_inference.py": "reproduces the T1 fidelity-inference experiment",
    "tests/test_thermal_t2_repeated_draw_calibration.py": "reproduces the T2 repeated-draw calibration experiment",
    "tests/test_thermal_t3_decision_aware_fidelity.py": "reproduces the T3 decision-aware fidelity experiment",
    "tests/test_kinetics_k1.py": "reproduces the K1 regime sweep",
    "tests/test_sria_e1_electrical.py": "reproduces the frozen E1 electrical run",
    "tests/test_sria_e2_model_adequacy.py": "reproduces the frozen E2 model-adequacy run",
    "tests/test_sria_e3_adequacy_obligation.py": "reproduces the frozen E3 adequacy-obligation run",
    "tests/test_electrical_v01_demo.py": "reproduces the electrical V0.1 demo run",
    "tests/test_sria_s11_transport_calibration.py": "reproduces the S1.1 transport calibration",
    "tests/test_sria_v01_certification_path.py": "rebuilds the V0.1 campaign over the E2/E3 grid inference before routing",
    "tests/test_sria_falsification_transport.py": "runs the falsification-transport policy comparison",
    "tests/domains/kinetics/test_cstr_domain.py": "runs CSTR verification gates and stiffness measurements",
    "tests/test_heterogeneous_ngspice.py": "launches a real external ngspice process ~30 times",
    "tests/domains/kinetics/test_cstr_solver_work.py": "counts solver work by running verification gates",
    "tests/domains/kinetics/test_cstr_inference_admissibility.py": "solves CSTR regimes to test inference admissibility",
    "tests/domains/kinetics/test_cstr_reference_scan.py": "runs the steady-state reference scan across regimes",
    "tests/domains/kinetics/test_k2_truth_admissibility.py": "replays seeded K2 observations across the K1.5 boundary",
    "tests/domains/kinetics/test_k3_configuration.py": "solves K3 truth holdouts against the K1.5 boundary",
    "tests/systems/aerospace/test_multirotor_mvr0.py": "runs multirotor reference design studies",
    "tests/systems/aerospace/test_multirotor_mvr1.py": "runs target-driven multirotor design studies",
}

#: Tests inside an expensive module that stay in FAST. Each only reads files,
#: hashes bytes, or parses source — none reaches the memoized experiment.
STATIC_GUARDS: dict[str, frozenset[str]] = {
    # HETERO-NGSPICE. The tests that only read source, scan records or check
    # types launch nothing and stay in FAST; the ones that drive the external
    # provider do not.
    "tests/test_heterogeneous_ngspice.py": frozenset(
        {
            "test_d_the_coupling_code_is_identical_between_the_two_runs",
            "test_h_universal_core_gained_nothing_and_knows_no_provider",
            "test_l_the_adapter_never_branches_on_provider_text",
            "test_m2_the_realization_records_name_no_solver_and_no_backend",
            "test_m3_the_grain_limitation_is_visible_rather_than_hidden",
            "test_j2_the_invocation_is_configuration_and_reads_the_environment",
            "test_g6_supports_does_not_claim_what_prepare_refuses",
            "test_r1_the_adapter_is_local_and_no_provider_framework_exists",
            "test_r2_no_parser_result_wrapper_survived",
            "test_r3_the_configuration_record_is_more_than_an_argv_tuple",
            "test_r4_no_execution_result_record_was_created",
            "test_r5_the_netlist_builder_is_a_function",
            "test_r6_three_realizations_are_the_minimum_the_contract_permits",
        }
    ),
    "tests/test_thermal_t1_fidelity_inference.py": frozenset(
        {
            "test_decision_path_never_imports_the_grader_truth",
            "test_frozen_thermal_solver_digests_match",
            "test_every_thermal_source_file_is_pinned",
        }
    ),
    "tests/test_thermal_t2_repeated_draw_calibration.py": frozenset(
        {
            "test_t1_and_shared_harness_digests_match",
            "test_decision_path_never_imports_a_grader_truth",
        }
    ),
    "tests/test_thermal_t3_decision_aware_fidelity.py": frozenset(
        {
            "test_t2_digests_match",
            "test_t1_digests_still_match_through_t2s_pins",
            "test_decision_path_never_imports_a_grader_truth",
        }
    ),
    "tests/test_kinetics_k1.py": frozenset(
        {
            "test_k1_does_not_import_or_write_any_frozen_experiment",
            "test_the_frozen_thermal_and_electrical_digests_still_match",
        }
    ),
    "tests/test_sria_e2_model_adequacy.py": frozenset(
        {
            "test_2_e1_frozen_files_are_unchanged",
        }
    ),
    "tests/test_electrical_v01_demo.py": frozenset(
        {
            "test_3_frozen_experiment_artifacts_are_unchanged",
            "test_4_demo_touches_no_production_source",
        }
    ),
    "tests/systems/aerospace/test_multirotor_mvr0.py": frozenset(
        {
            "test_multirotor_logic_does_not_leak_into_frozen_general_design_layer",
        }
    ),
    "tests/systems/aerospace/test_multirotor_mvr1.py": frozenset(
        {
            "test_no_mvr1_logic_leaks_into_frozen_general_design_layer",
        }
    ),
}


def normalized_nodeid(nodeid: str) -> str:
    """Node id with forward slashes, so the tables read the same on Windows."""
    return nodeid.replace("\\", "/")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Attach tier markers. Never reorders, deselects or skips anything."""
    for item in items:
        nodeid = normalized_nodeid(item.nodeid)
        module = nodeid.split("::", 1)[0]

        campaign_reason = CAMPAIGN_TESTS.get(nodeid)
        if campaign_reason is not None:
            item.add_marker(pytest.mark.campaign(reason=campaign_reason))
            item.add_marker(pytest.mark.expensive(reason=campaign_reason))
            continue

        module_reason = EXPENSIVE_MODULES.get(module)
        if module_reason is None:
            continue
        if item.name in STATIC_GUARDS.get(module, frozenset()):
            continue

        item.add_marker(pytest.mark.expensive(reason=module_reason))
